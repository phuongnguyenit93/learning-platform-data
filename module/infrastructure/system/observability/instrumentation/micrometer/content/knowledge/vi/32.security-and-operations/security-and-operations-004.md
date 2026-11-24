# TLS, chính sách mạng và quyền gửi dữ liệu tới hệ thống nhận

Micrometer giúp ứng dụng Java ghi nhận metrics, nhưng dữ liệu chỉ có ích khi được chuyển đến đúng hệ thống nhận và được bảo vệ trong suốt quá trình truyền. Metrics có thể tiết lộ tên service, route, trạng thái giao dịch, cấu trúc dependency, lưu lượng và tình trạng nội bộ. Endpoint export vì vậy cần được bảo vệ như một giao diện vận hành có quyền truy cập riêng.

Khi thiết kế đường truyền metrics, cần trả lời ba câu hỏi:

1. **Ai kết nối với ai?** Prometheus thường chủ động scrape endpoint của ứng dụng; với registry push hoặc OTLP, ứng dụng chủ động gửi dữ liệu đến collector/backend.
2. **Kết nối có được bảo vệ không?** TLS xác thực máy chủ và mã hóa đường truyền; mTLS có thể xác thực cả client.
3. **Bên gửi có được phép gửi hoặc đọc dữ liệu không?** Cần xác thực danh tính, phân quyền, chính sách mạng và giới hạn endpoint.

TLS, network policy và authorization giải quyết các lớp khác nhau. Chỉ bật HTTPS chưa đủ để giới hạn ai được scrape; chỉ có NetworkPolicy chưa mã hóa dữ liệu; token hợp lệ cũng không nên được gửi qua kết nối không được bảo vệ.

## 1. Xác định mô hình truyền metrics trước khi cấu hình bảo mật

Micrometer hỗ trợ nhiều kiểu registry. Cách bảo vệ phụ thuộc vào hướng truyền dữ liệu.

| Mô hình | Bên khởi tạo kết nối | Endpoint cần bảo vệ | Quyền cần cấp |
|---|---|---|---|
| Prometheus pull | Prometheus kết nối đến ứng dụng | `/actuator/prometheus` hoặc endpoint scrape tương ứng | Prometheus được phép đọc metrics của service |
| OTLP push qua collector | Ứng dụng kết nối đến OpenTelemetry Collector | OTLP receiver của collector | Workload được phép gửi telemetry đến collector |
| Registry push trực tiếp | Ứng dụng kết nối đến metrics backend | API ingest của backend | Service identity được phép ghi metrics vào đúng project/account |
| Pushgateway | Ứng dụng hoặc job kết nối đến Pushgateway | API Pushgateway | Job được phép ghi nhóm metrics được quản lý |

Trong mô hình Prometheus pull, ứng dụng không cần chủ động gửi metrics ra Prometheus. Prometheus truy cập endpoint export của ứng dụng theo lịch scrape.

Trong mô hình OTLP hoặc push registry, ứng dụng cần quyền egress đến receiver. Collector có thể tiếp tục chuyển tiếp dữ liệu đến backend bằng một kết nối khác; quyền gửi của ứng dụng và quyền gửi của collector nên được quản lý riêng.

Không mở cả ingress và egress rộng chỉ vì chưa xác định được mô hình. Hãy lập sơ đồ luồng dữ liệu và chỉ cấp quyền cho các đích, cổng và danh tính cần thiết.

## 2. Phân biệt TLS, mTLS, xác thực và phân quyền

| Cơ chế | Bảo vệ điều gì? | Ví dụ |
|---|---|---|
| TLS | Mã hóa dữ liệu trên đường truyền và xác thực certificate của server | Prometheus xác minh certificate của ứng dụng |
| Mutual TLS (mTLS) | TLS hai chiều; server cũng xác minh certificate của client | Ứng dụng chỉ nhận kết nối từ Prometheus có client certificate hợp lệ |
| HTTP authentication | Xác minh danh tính ở tầng ứng dụng | Bearer token hoặc OAuth2 access token |
| Authorization | Quyết định danh tính được làm gì | Chỉ role `METRICS_SCRAPER` được đọc endpoint Prometheus |
| Network policy | Giới hạn nguồn/đích có thể kết nối ở tầng mạng | Chỉ namespace monitoring được vào cổng management |
| Secret management | Bảo vệ token, private key và password | Kubernetes Secret hoặc secret manager |

TLS không tự cấp quyền đọc metrics. Một client có thể hoàn tất TLS handshake nhưng vẫn nhận HTTP 401 hoặc 403 nếu thiếu credential hoặc không có quyền.

mTLS xác minh certificate client ở tầng transport. Hệ thống vẫn cần quy tắc ánh xạ danh tính certificate sang quyền đọc hoặc ghi. Không nên coi mọi certificate được ký bởi cùng CA đều có quyền giống nhau nếu CA đó cấp cho nhiều loại workload.

## 3. Bảo vệ endpoint scrape của Spring Boot Actuator

Với Prometheus registry, endpoint thường là:

```text
/actuator/prometheus
```

Chỉ expose endpoint cần thiết:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,prometheus
```

Exposure chỉ làm endpoint có thể được publish qua web layer. Nó không thay thế authentication hoặc authorization.

Một cách cô lập endpoint quản trị là dùng cổng management riêng:

```yaml
server:
  port: 8080

management:
  server:
    port: 8443
  endpoints:
    web:
      exposure:
        include: health,prometheus
```

Khi dùng cổng riêng, cấu hình firewall hoặc NetworkPolicy để chỉ Prometheus và các thành phần vận hành được phép truy cập cổng management. Cổng ứng dụng phục vụ người dùng không nên vô tình expose endpoint metrics.

Không bind management server ra mọi interface nếu kiến trúc triển khai không cần điều đó. Địa chỉ bind, service type, ingress và load balancer phải phù hợp với mạng nội bộ dành cho scraping.

## 4. Bật TLS cho management endpoint

Nếu management server dùng cổng riêng, Spring Boot có thể cấu hình SSL cho management server. Ví dụ dưới đây dùng PKCS12 keystore được mount từ secret volume:

```yaml
management:
  server:
    port: 8443
    ssl:
      enabled: true
      key-store: file:/run/secrets/metrics-server.p12
      key-store-type: PKCS12
      key-store-password: ${METRICS_KEYSTORE_PASSWORD}
      key-alias: metrics
```

Giá trị password trong ví dụ là placeholder môi trường. Trong ứng dụng thật, inject giá trị từ secret manager hoặc secret volume theo cơ chế của nền tảng. Không commit password, private key hoặc keystore chứa private key vào repository.

Certificate server cần:

- Chưa hết hạn và có chuỗi CA tin cậy.
- SAN khớp hostname mà Prometheus dùng để kết nối.
- Có mục đích sử dụng phù hợp cho TLS server authentication.
- Được rotate trước khi hết hạn.
- Có private key được giới hạn quyền đọc ở mức process cần thiết.

Client phải xác minh certificate và hostname. Không dùng cấu hình bỏ qua xác minh certificate để làm cho scrape hoạt động. Nếu hostname mismatch, sửa DNS/target hoặc cấp certificate có SAN đúng.

Nếu yêu cầu mTLS, management server cần truststore chứa CA phát hành client certificate và bật yêu cầu client certificate. Ví dụ phần bổ sung:

```yaml
management:
  server:
    ssl:
      trust-store: file:/run/secrets/prometheus-client-truststore.p12
      trust-store-type: PKCS12
      trust-store-password: ${PROMETHEUS_TRUSTSTORE_PASSWORD}
      client-auth: need
```

Ở tầng ứng dụng, tiếp tục ánh xạ certificate/client principal sang quyền đọc endpoint. `client-auth: need` yêu cầu client trình certificate hợp lệ khi bắt tay TLS; nó không tự cấp authority `SCOPE_metrics.read`.

## 5. Cấu hình Prometheus scrape qua HTTPS

Ví dụ Prometheus scrape endpoint management bằng HTTPS và bearer token:

```yaml
scrape_configs:
  - job_name: order-service
    scheme: https
    metrics_path: /actuator/prometheus
    static_configs:
      - targets:
          - order-service.app.svc:8443
    bearer_token_file: /etc/prometheus/secrets/order-service-metrics-token
    tls_config:
      ca_file: /etc/prometheus/certs/metrics-ca.crt
      server_name: order-service.app.svc
```

Trong ví dụ:

- `scheme: https` yêu cầu TLS.
- `ca_file` cung cấp CA để Prometheus xác minh certificate server.
- `server_name` là hostname được dùng để xác minh SAN và SNI.
- `bearer_token_file` cung cấp token để xác thực ở tầng HTTP.

Token file cần được mount từ secret store và có quyền đọc tối thiểu. Không ghi token vào log, dashboard, cấu hình công khai hoặc command line dễ bị lộ qua process listing.

Nếu service yêu cầu mTLS, Prometheus có thể gửi thêm client certificate:

```yaml
tls_config:
  ca_file: /etc/prometheus/certs/metrics-ca.crt
  server_name: order-service.app.svc
  cert_file: /etc/prometheus/certs/prometheus-client.crt
  key_file: /etc/prometheus/secrets/prometheus-client.key
```

Certificate client và private key cần được quản lý như credential. Server phải tin cậy CA phát hành client certificate và có chính sách xác định certificate nào được phép truy cập endpoint.

Không cấu hình `insecure_skip_verify: true` trong môi trường production. Cấu hình đó vô hiệu hóa xác minh certificate server và làm giảm khả năng chống giả mạo endpoint.

## 6. Phân quyền endpoint bằng Spring Security

Ngay cả khi endpoint chỉ nằm trên management port, vẫn cần xác thực và phân quyền ở tầng HTTP. Ví dụ dưới đây cho phép health endpoint công khai trong mạng đã kiểm soát, chỉ cho token có authority `SCOPE_metrics.read` đọc Prometheus endpoint và từ chối các actuator endpoint khác:

```java
import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ActuatorSecurityConfiguration {

    @Bean
    SecurityFilterChain applicationSecurity(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(EndpointRequest.to("health")).permitAll()
                .requestMatchers(EndpointRequest.to("prometheus"))
                    .hasAuthority("SCOPE_metrics.read")
                .requestMatchers(EndpointRequest.toAnyEndpoint()).denyAll()
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults())
            )
            .build();
    }
}
```

Ví dụ giả định ứng dụng đã cấu hình JWT decoder hoặc issuer phù hợp. Token của Prometheus cần có scope `metrics.read`; token của workload khác không nên tự động có scope đó.

Nếu hệ thống dùng API key, Basic Authentication hoặc X.509 thay cho JWT, áp dụng cơ chế tương ứng và giới hạn quyền vào đúng endpoint. Khi tùy chỉnh Spring Security, phải kiểm tra cả request của ứng dụng và actuator; một SecurityFilterChain chỉ match actuator mà không có chain khác có thể để các request còn lại không được bảo vệ như mong muốn.

## 7. Giới hạn dữ liệu được expose

Metrics endpoint thường không cần mọi actuator endpoint. Hãy expose đúng danh sách:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,prometheus
```

Tránh expose không cần thiết các endpoint có thể cung cấp cấu hình, environment, bean inventory, heap dump, thread dump hoặc thông tin nội bộ khác. Quyền truy cập các endpoint nhạy cảm cần được xem xét riêng, không dùng chung role scrape metrics.

Metrics cũng có thể chứa thông tin nhạy cảm nếu instrumentation dùng tag sai. Trước khi export, rà soát:

- Không có access token, API key, password hoặc session ID.
- Không có email, số điện thoại hoặc dữ liệu định danh cá nhân.
- Không có URL đầy đủ chứa ID động hoặc query string nhạy cảm.
- Không có SQL, exception message hoặc payload tùy ý làm tag.
- Tên service, environment, region và tenant group chỉ chứa giá trị được phép công bố.

Không đưa secret vào tag hoặc description. Việc che endpoint không sửa được một meter đã chứa dữ liệu nhạy cảm trong label values.

## 8. NetworkPolicy cho Prometheus pull và OTLP push

Trong Kubernetes, NetworkPolicy có thể giới hạn pod nào được kết nối đến management port và ứng dụng được kết nối đến OTLP collector nào.

Ví dụ dưới đây minh họa service vừa được Prometheus scrape ở cổng 8443, vừa gửi OTLP đến collector cổng 4317:

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: order-service-telemetry
  namespace: app
spec:
  podSelector:
    matchLabels:
      app.kubernetes.io/name: order-service
  policyTypes:
    - Ingress
    - Egress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: monitoring
          podSelector:
            matchLabels:
              app.kubernetes.io/name: prometheus
      ports:
        - protocol: TCP
          port: 8443
  egress:
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: observability
          podSelector:
            matchLabels:
              app.kubernetes.io/name: otel-collector
      ports:
        - protocol: TCP
          port: 4317
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: kube-system
          podSelector:
            matchLabels:
              k8s-app: kube-dns
      ports:
        - protocol: UDP
          port: 53
        - protocol: TCP
          port: 53
```

Đây là ví dụ theo label và port giả định. Cần thay namespace, pod labels, port và DNS labels theo cluster thực tế. NetworkPolicy có hiệu lực phụ thuộc CNI hỗ trợ enforcement.

Khi policy chọn `Ingress` và `Egress`, các luồng khác có thể bị chặn nếu chưa có rule cho database, service discovery, API nghiệp vụ hoặc dependency khác. Hãy hợp nhất các luồng hợp lệ cần thiết vào chính sách của workload. Kubernetes NetworkPolicy có tính additive giữa các policy áp dụng cho pod; một policy allow khác có thể mở thêm luồng.

Nếu service chỉ dùng Prometheus pull, không cần rule egress đến OTLP collector. Nếu service chỉ push OTLP, không cần mở ingress scrape port cho Prometheus. Chỉ cấp cả hai khi ứng dụng thực sự dùng cả hai mô hình.

## 9. Cấu hình bảo mật cho OTLP metrics push

Với OTLP push, ứng dụng kết nối đến receiver của collector. Endpoint phải dùng TLS và cơ chế xác thực được collector/backend hỗ trợ.

Ví dụ cấu hình Spring Boot cho OTLP metrics exporter (cần đối chiếu prefix và thuộc tính với phiên bản Spring Boot/Micrometer đang dùng):

```yaml
management:
  otlp:
    metrics:
      export:
        url: https://otel-collector.observability.svc:4318/v1/metrics
        step: 30s
        headers:
          Authorization: Bearer ${OTLP_METRICS_TOKEN}
```

Token được inject khi deploy từ secret store. Không lưu token thật trong file YAML hoặc source control. Collector cần xác minh credential và chỉ chấp nhận dữ liệu từ workload được cấp quyền.

Với OTLP/gRPC, endpoint và port thường khác OTLP/HTTP. Không nhầm cổng 4317 của gRPC với cổng 4318 của HTTP; cấu hình exporter phải khớp receiver đang bật. Nếu collector dùng CA nội bộ, cấu hình trust material cho JVM/exporter để xác minh certificate của collector. Cách cung cấp truststore hoặc SSL bundle phụ thuộc exporter và phiên bản.

Nếu dùng registry push khác như Datadog hoặc New Relic, cấu hình API key, endpoint, TLS và quyền project theo hướng dẫn của registry tương ứng. Micrometer không có một property chung áp dụng cho mọi backend.

## 10. Cấp quyền tối thiểu cho workload

Danh tính gửi metrics nên được tách theo service hoặc nhóm service. Không dùng một API key quản trị chung cho mọi ứng dụng.

Một thiết kế quyền tối thiểu có thể gồm:

- Service A chỉ ghi metrics vào project hoặc tenant của Service A.
- Service B dùng credential riêng và chỉ ghi vào namespace được cấp.
- Prometheus chỉ đọc endpoint scrape đã khai báo.
- Collector chỉ gửi telemetry đến backend đích được cho phép.
- Dashboard user chỉ đọc dữ liệu thuộc phạm vi được cấp.
- Operator có quyền thay đổi cấu hình credential nhưng không cần quyền truy cập dữ liệu nghiệp vụ không liên quan.

Nếu backend hỗ trợ workload identity, cloud IAM hoặc service account token ngắn hạn, ưu tiên cơ chế đó hơn API key dài hạn. Nếu phải dùng API key, tạo key riêng theo workload, đặt expiry/rotation và giới hạn quyền ingest.

Không cấp quyền ghi metrics đồng nghĩa quyền quản trị dashboard hoặc xóa dữ liệu. Ghi telemetry và quản trị backend là hai quyền khác nhau.

## 11. Quản lý certificate và secret

Certificate và credential cần có vòng đời rõ ràng:

1. Cấp certificate từ CA tin cậy của tổ chức hoặc nhà cung cấp.
2. Lưu private key và token trong secret manager hoặc secret volume.
3. Cấp quyền đọc chỉ cho process cần sử dụng.
4. Ghi nhận ngày hết hạn và owner.
5. Rotate trước hạn, tránh thay đổi đồng thời mọi workload.
6. Xác minh kết nối sau rotation.
7. Thu hồi credential cũ sau khi các bên đã chuyển sang credential mới.

Với certificate, kiểm tra chain, SAN, key usage, thời gian hệ thống và truststore. Với token, kiểm tra audience, issuer, expiry, scope và project/resource được phép ghi.

Không ghi secret vào log, exception message, metric tag, trace attribute hoặc endpoint debug. Khi khởi động, log chỉ nên ghi trạng thái cấu hình an toàn như “OTLP authentication configured”, không ghi giá trị token hoặc private key.

## 12. Bảo vệ đường truyền giữa collector và backend

Nếu ứng dụng gửi đến collector, dữ liệu còn có thể đi tiếp đến metrics backend hoặc tracing backend. TLS giữa ứng dụng và collector không tự bảo vệ chặng collector đến backend.

Hãy lập danh sách từng hop:

```text
Application
   | TLS + workload credential
   v
OpenTelemetry Collector
   | TLS + backend-specific credential
   v
Metrics Backend
```

Mỗi hop cần:

- Endpoint và port cụ thể.
- TLS validation và CA trust.
- Danh tính client.
- Quyền ingest theo project/tenant.
- Network egress/ingress rule.
- Retry, queue và giới hạn dữ liệu.
- Logging không làm lộ credential.

Nếu collector nhận OTLP từ nhiều namespace, không nên dùng một receiver mở cho toàn cluster nếu không có xác thực và giới hạn mạng. Dùng receiver listener nội bộ, mTLS hoặc authentication extension phù hợp với khả năng triển khai.

## 13. Retry, queue và quyền gửi không thành công

Bảo mật tốt không có nghĩa dữ liệu luôn được gửi thành công. Token hết hạn, certificate hết hạn, DNS lỗi, NetworkPolicy sai hoặc receiver quá tải đều có thể làm export thất bại.

Cần theo dõi:

- Export request thất bại hoặc bị từ chối.
- HTTP 401/403 do credential hoặc authorization.
- TLS handshake error và certificate validation failure.
- Timeout, connection refused và DNS failure.
- HTTP 429 hoặc 5xx từ receiver/backend.
- Queue đầy, retry exhausted hoặc dropped telemetry nếu exporter/collector cung cấp các chỉ số này.

Không retry vô hạn với tốc độ cao khi nhận 401/403; credential sai cần được sửa. Với 429 hoặc lỗi tạm thời, dùng retry/backoff theo cơ chế exporter/collector. Giới hạn queue và memory để telemetry không làm cạn heap của ứng dụng.

Metrics export cũng có thể tạo feedback loop nếu lỗi export được ghi bằng chính exporter đang lỗi. Dùng log hoặc health signal độc lập cho các lỗi nghiêm trọng của telemetry pipeline.

## 14. Kiểm tra TLS và quyền truy cập

Có thể kiểm tra certificate chain và hostname bằng OpenSSL:

```bash
openssl s_client \
  -connect order-service.app.svc:8443 \
  -servername order-service.app.svc \
  -CAfile metrics-ca.crt
```

Kiểm tra HTTP endpoint bằng CA tin cậy và credential được cấp:

```bash
curl --cacert metrics-ca.crt \
  --header "Authorization: Bearer $METRICS_TOKEN" \
  https://order-service.app.svc:8443/actuator/prometheus
```

Không dùng `curl -k` để bỏ qua xác minh certificate trong kiểm thử nghiệm thu. Nếu muốn kiểm tra endpoint yêu cầu authentication, thử request không có token và xác nhận server trả 401; dùng token thiếu scope để xác nhận 403; dùng token đúng quyền để xác nhận 200.

Với NetworkPolicy, kiểm tra từ đúng namespace/pod nguồn. Một lệnh curl từ laptop hoặc pod quản trị có thể thành công trong khi Prometheus pod vẫn bị chặn vì nguồn mạng khác nhau.

## 15. Phân biệt lỗi kết nối và lỗi quyền

| Hiện tượng | Lớp có thể gây lỗi | Hướng kiểm tra |
|---|---|---|
| DNS lookup thất bại | DNS/network | Service name, namespace, DNS egress |
| Connection refused | Service/port/listener | Management port, target port, pod readiness |
| Timeout | NetworkPolicy, route, firewall hoặc receiver quá tải | Luồng nguồn/đích, packet path, timeout |
| TLS unknown CA | Trust configuration | CA file, truststore, chain |
| Hostname mismatch | Certificate identity | SAN và hostname target |
| Certificate expired | Certificate lifecycle | NotAfter, rotation và clock |
| HTTP 401 | Authentication | Token, issuer, expiry, header |
| HTTP 403 | Authorization | Scope, role, service identity |
| HTTP 404 | Path/exposure | Metrics path và Actuator exposure |
| HTTP 429 | Ingest quota/rate limit | Backend quota và retry/backoff |
| HTTP 5xx | Receiver/backend | Receiver health, capacity và exporter retry |

Không giải quyết lỗi TLS bằng cách tắt certificate verification; không giải quyết 403 bằng cách cấp quyền quản trị toàn hệ thống. Hãy xác định đúng lớp đang từ chối kết nối và sửa đúng cấu hình.

## 16. Kiểm tra hoạt động sau triển khai

Với Prometheus pull, kiểm tra:

- Target có trạng thái `UP`.
- Scrape endpoint trả HTTP 200.
- Scrape duration và số samples nằm trong dự kiến.
- Series có label set đúng, không chứa dữ liệu nhạy cảm.
- Token/certificate rotation không làm target mất kết nối.

Ví dụ PromQL kiểm tra target:

```promql
up{job="order-service"}
```

Có thể theo dõi thêm:

```promql
scrape_duration_seconds{job="order-service"}
```

Với OTLP push, kiểm tra metric của exporter/collector về request accepted, rejected, failed, queue size và dropped telemetry theo đúng phiên bản collector. Tên metric của collector có thể thay đổi theo component và cấu hình; hãy khám phá endpoint telemetry của collector thay vì đoán tên.

Không chỉ kiểm tra một lần khi vừa deploy. Hãy xác minh sau restart, sau rotate token/certificate và khi receiver tạm thời không khả dụng.

## 17. Checklist bảo mật trước khi phát hành

- [ ] Đã xác định mô hình pull hay push cho từng luồng metrics.
- [ ] Endpoint management chỉ được expose trên mạng cần thiết.
- [ ] Chỉ expose health và metrics endpoint thực sự cần.
- [ ] TLS được bật và client xác minh certificate server.
- [ ] SAN khớp hostname dùng để kết nối.
- [ ] mTLS được bật khi yêu cầu xác thực client ở tầng transport.
- [ ] HTTP authentication và authorization giới hạn đúng service identity.
- [ ] Prometheus token hoặc OTLP credential được lưu trong secret manager.
- [ ] NetworkPolicy chỉ cho phép nguồn/đích và port cần thiết.
- [ ] Egress policy vẫn cho phép dependency hợp lệ như DNS và backend nghiệp vụ.
- [ ] Không có secret hoặc dữ liệu cá nhân trong metric tags.
- [ ] Collector-to-backend hop cũng được bảo vệ.
- [ ] Có quy trình rotation, expiry và thu hồi credential.
- [ ] Retry/backoff và queue có giới hạn.
- [ ] Đã kiểm tra 401, 403, TLS failure và NetworkPolicy từ đúng workload.
- [ ] Có cảnh báo khi scrape hoặc export bị gián đoạn.

Metrics là một giao diện vận hành có thể tiết lộ cấu trúc và trạng thái nội bộ của hệ thống. Hãy xác định hướng truyền dữ liệu trước, bảo vệ từng hop bằng TLS, giới hạn đường mạng bằng policy và cấp quyền đọc/ghi theo danh tính tối thiểu. Với Prometheus pull, bảo vệ endpoint scrape của ứng dụng; với OTLP hoặc registry push, bảo vệ receiver và credential egress. Kiểm tra certificate, token, authorization, rotation và trạng thái export định kỳ để dữ liệu quan sát vừa sẵn có vừa được gửi đến đúng hệ thống nhận.

## Tài liệu tham khảo

- [Spring Boot Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html) — exposure và bảo vệ endpoint quản trị.
- [Spring Boot SSL](https://docs.spring.io/spring-boot/reference/features/ssl.html) — cấu hình SSL và certificate trong Spring Boot.
- [Prometheus Configuration](https://prometheus.io/docs/prometheus/latest/configuration/configuration/) — scrape configuration, TLS và authentication.
- [Kubernetes Network Policies](https://kubernetes.io/docs/concepts/services-networking/network-policies/) — giới hạn ingress và egress theo pod/namespace.
- [OpenTelemetry Collector Security](https://opentelemetry.io/docs/security/config-best-practices/) — bảo vệ receiver, exporter và telemetry pipeline.

