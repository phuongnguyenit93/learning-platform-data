# Actuator endpoint bị 401

Một monitoring agent gọi /actuator/prometheus nhưng nhận HTTP 401 Unauthorized. Ứng dụng vẫn xử lý business API bình thường, health probe có thể vẫn chạy, còn dashboard metrics bắt đầu xuất hiện khoảng trống. Tình huống này thường liên quan đến authentication: request không có credentials, credentials hết hạn/sai, token không được chấp nhận hoặc request đi qua security chain không như dự kiến.

HTTP 401 cho biết server yêu cầu xác thực hoặc không chấp nhận thông tin xác thực đã gửi. Nó khác HTTP 403, thường có nghĩa caller đã được xác thực nhưng thiếu quyền. Tuy nhiên, cấu hình bảo mật có thể cố ý che giấu endpoint bằng 404; vì vậy cần kiểm tra cả response, security logs, endpoint exposure và routing thay vì kết luận chỉ từ status code.

Bài **Actuator endpoint bị 401** thuộc chương **Chẩn đoán sự cố** của module **SPRING_BOOT_OBSERVABILITY**. Module tập trung thiết lập observability cho Spring Boot bằng Micrometer Observation, metrics, logs và distributed tracing; học context propagation, tag/cardinality, exporter, sampling và liên kết tín hiệu để điều tra lỗi, độ trễ và hành vi ứng dụng trên môi trường thực.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích ý nghĩa của HTTP 401 và phân biệt với 403/404.
- Xác định authentication mechanism bảo vệ Actuator endpoint.
- Kiểm tra Spring Security filter chains và matcher order.
- Chẩn đoán credentials, JWT scopes, Basic authentication và service identity.
- Phân biệt application port với management port trong quá trình điều tra.
- Xử lý health probes và Prometheus scraper có identity riêng.
- Kiểm tra CSRF, proxy headers và TLS khi chúng liên quan tới request.
- Dùng logs, curl và integration tests để xác nhận nguyên nhân.

## 2. 401 có nghĩa gì?

HTTP 401 Unauthorized thường xuất hiện khi request chưa được authenticate hoặc credentials không hợp lệ. Server có thể gửi WWW-Authenticate header để chỉ ra authentication scheme được yêu cầu.

| Status | Ý nghĩa thường gặp | Ví dụ |
| --- | --- | --- |
| 200 | Request được chấp nhận và xử lý | Scraper đọc được metrics |
| 401 | Chưa xác thực hoặc credentials không hợp lệ | Thiếu bearer token hoặc Basic credentials sai |
| 403 | Đã xác thực nhưng không đủ quyền | Token hợp lệ nhưng thiếu SCOPE_metrics.read |
| 404 | Endpoint không tồn tại, chưa expose hoặc bị che giấu | Actuator path sai hoặc endpoint không được expose |
| 503 | Service/endpoint không sẵn sàng theo response policy | Health endpoint báo trạng thái unavailable |

Đừng đổi tất cả 401 thành permitAll() để dashboard hoạt động. Trước tiên xác định caller là ai, endpoint cần quyền gì và request đang được xử lý bởi filter chain nào.

## 3. Xác nhận đúng endpoint và đúng port

Trước khi điều tra authentication, xác nhận request đi tới đúng management endpoint:

- Actuator có trong application dependencies không?
- Endpoint đã được expose qua web chưa?
- Base path có phải /actuator hay đã đổi thành /manage?
- Management server dùng chung application port hay có port riêng?
- Request có đi qua ingress, gateway hoặc service mesh không?

Ví dụ application và management server dùng chung port:

```text
Application API:  http://localhost:8080/api/orders
Actuator:         http://localhost:8080/actuator/health
Prometheus:       http://localhost:8080/actuator/prometheus
```

Ví dụ management server chạy port riêng:

```text
Application API:  http://localhost:8080/api/orders
Actuator:         http://localhost:8081/actuator/health
Prometheus:       http://localhost:8081/actuator/prometheus
```

Gọi nhầm port có thể dẫn tới response từ một server hoặc security policy khác. Kiểm tra Kubernetes Service targetPort, container port và Prometheus scrape target.

## 4. Kiểm tra endpoint exposure

Endpoint phải được tạo và expose trước khi caller có thể truy cập qua HTTP. Ví dụ allow-list:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
```

Exposure không cấp quyền truy cập; nó chỉ đưa endpoint ra web surface. Nếu endpoint không được expose, kết quả thường là 404. Nếu endpoint đã expose nhưng Security yêu cầu authentication, request thiếu credentials có thể nhận 401.

Khi điều tra, kiểm tra runtime configuration của đúng profile và deployment. Không giả định file YAML local đang là cấu hình production.

## 5. Kiểm tra Spring Security filter chain

Khi Spring Security có mặt, request Actuator được xử lý bởi một hoặc nhiều SecurityFilterChain. Kiểm tra:

1. Chain nào match request path/management context?
2. Có chain nào match rộng như /** hoặc /actuator/** đứng trước chain dự kiến không?
3. Authentication mechanism nào được bật: Basic, JWT resource server, session hay mTLS?
4. Request matcher có đúng base path và port/context không?
5. Có custom authentication entry point trả 401 không?

Ví dụ policy same-port dùng JWT resource server:

```java
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
        .oauth2ResourceServer(oauth2 -> oauth2.jwt())
        .build();
}
```

Đây là ví dụ minh họa; cú pháp DSL có thể khác theo Spring Security version. Ứng dụng cần cấu hình JWT decoder/issuer và authority mapping. Matcher cụ thể nên đứng trước matcher tổng quát. Nếu /actuator/** được đặt trước rule Prometheus, request có thể bị áp dụng OPS rule trước.

### Vì sao request hợp lệ vẫn nhận 401?

Các nguyên nhân phổ biến:

- Authorization header không được gửi hoặc bị proxy loại bỏ.
- Token hết hạn, sai issuer, audience hoặc chữ ký.
- Basic credentials sai hoặc bị rotate nhưng scraper vẫn dùng secret cũ.
- JWT được authenticate nhưng custom entry point hoặc filter chain khác xử lý request.
- Scraper gọi management port nhưng credentials chỉ được cấu hình cho application route.
- Identity provider/JWK endpoint không truy cập được nên token không xác minh được.

Nếu token đã được xác thực nhưng thiếu role/scope, thường là 403. Hãy kiểm tra security logs để phân biệt authentication failure với authorization denial.

## 6. Kiểm tra credentials từ đúng caller

Thử request trực tiếp từ môi trường tương tự scraper:

```bash
curl -i http://localhost:8081/actuator/prometheus
```

Nếu endpoint yêu cầu bearer token:

```bash
curl -i \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  http://localhost:8081/actuator/prometheus
```

Nếu dùng HTTP Basic:

```bash
curl -i -u "$METRICS_USER:$METRICS_PASSWORD" \
  http://localhost:8081/actuator/prometheus
```

Không paste token/password thật vào ticket, terminal log được chia sẻ hoặc chat. Dùng secret test, biến môi trường an toàn hoặc workload identity. Chạy kiểm tra từ pod/host có cùng network path với Prometheus để loại trừ khác biệt về DNS, proxy và service routing.

### Đọc response headers

```bash
curl -sS -D - -o /dev/null \
  http://localhost:8081/actuator/prometheus
```

Quan sát status, WWW-Authenticate, Location nếu có redirect, Server và các request IDs phục vụ correlation. Không kết luận từ header Server một mình; proxy có thể thay đổi response headers.

## 7. Health probe và Prometheus scraper có nhu cầu khác nhau

Không nên dùng chung policy cho mọi caller:

| Caller | Nhu cầu | Policy gợi ý |
| --- | --- | --- |
| Kubernetes probe | Đọc health status cần thiết | Cho phép đúng health path hoặc dùng probe identity |
| Prometheus scraper | Đọc metrics exposition | Token/scope riêng hoặc mTLS |
| Operator | Truy cập diagnostics được phê duyệt | Role OPS hoặc authority tương đương |
| Application user | Business API | Không tự có quyền Actuator |

Ví dụ health status có thể được phép đọc trong khi details chỉ dành cho caller được authorize:

```yaml
management:
  endpoint:
    health:
      show-details: when-authorized
      probes:
        enabled: true
```

Property và response behavior phụ thuộc Spring Boot version/security setup. Kiểm tra health group paths, base path và security matchers. Không permit mọi Actuator subpaths chỉ để Kubernetes probe hoạt động.

## 8. Management port riêng và nhiều SecurityFilterChain

Khi cấu hình:

```yaml
server:
  port: 8080
management:
  server:
    port: 8081
```

Management endpoints có thể đi qua management web context/server riêng. Cách áp dụng security chain và matcher phụ thuộc Spring Boot/Spring Security version và cấu hình ứng dụng. Kiểm tra request matcher dành cho management server nếu version hỗ trợ; tránh dựa vào header Host do caller có thể tự đặt.

Một lỗi thường gặp là security chain của application API yêu cầu JWT, trong khi probe gọi management port không gửi token. Một lỗi khác là chain riêng chỉ áp dụng cho management context nhưng matcher sai nên request rơi vào chain khác.

Network policy vẫn cần giới hạn management port. Port riêng không tự động xác thực caller hoặc làm endpoint an toàn.

## 9. CSRF, CORS, proxy và TLS

### CSRF và CORS

Prometheus scraper và Kubernetes probe thường là machine-to-machine clients, không phải browser. CORS không chặn server-to-server request và không thay thế authentication. CSRF chủ yếu liên quan tới browser-based authenticated requests; không tắt CSRF toàn ứng dụng chỉ để sửa lỗi scrape.

Nếu security chain bật CSRF và endpoint có method thay đổi trạng thái, có thể gặp 403 do CSRF token thiếu. Với GET scrape endpoint, 401 thường chỉ ra authentication; vẫn cần xem response và security logs để xác nhận.

### Reverse proxy và Authorization header

Ingress/gateway có thể loại bỏ hoặc ghi đè Authorization header, chuyển request sang sai upstream hoặc áp dụng auth middleware riêng. So sánh request tại client, gateway và application logs; không log giá trị token. Kiểm tra proxy configuration để bảo toàn header cần thiết và tránh chuyển tiếp credentials tới upstream không đáng tin cậy.

### TLS và mTLS

Nếu dùng mTLS, server có thể yêu cầu client certificate. Certificate hết hạn, không nằm trong trust chain hoặc không được map thành identity có thể làm authentication thất bại. Kiểm tra certificate chain, SAN, expiry, truststore và client identity mapping. Với bearer token, TLS vẫn cần thiết để bảo vệ token khi truyền qua network.

## 10. Quy trình điều tra theo thứ tự

Thực hiện các bước sau để thu hẹp nguyên nhân:

1. **Ghi nhận request:** URL, port, method, timestamp, source identity và status; không lưu secret.
2. **Xác nhận endpoint:** Actuator dependency, exposure, base path và management port.
3. **Thử từ cùng network:** gọi endpoint từ pod/host tương tự scraper.
4. **Kiểm tra authentication:** header có được gửi, token còn hạn, issuer/audience/signature đúng không?
5. **Kiểm tra filter chain:** matcher nào match, chain order và entry point nào tạo 401?
6. **Kiểm tra authorization:** caller có authority/role cần thiết không? Nếu đã authenticate nhưng thiếu quyền, response thường là 403.
7. **Kiểm tra intermediary:** ingress, service mesh, reverse proxy, TLS/mTLS và header forwarding.
8. **Kiểm tra recovery:** sau khi sửa, xác nhận scraper scrape thành công và time series tiếp tục được cập nhật.

### Log cần tìm

Tùy logging level và Security version, có thể tìm authentication entry point/provider failure, JWT decoder/issuer/JWK validation errors, authority mapping/authorization decision, request path/selected filter chain và proxy upstream/TLS errors.

Chỉ bật debug logging có thời hạn trong môi trường phù hợp. Security debug logs có thể chứa metadata nhạy cảm; không bật kéo dài ở production nếu chưa đánh giá.

## 11. Kiểm thử để ngăn lỗi tái diễn

Integration tests nên xác nhận cả caller hợp lệ và không hợp lệ:

```java
@Test
void metricsEndpointAcceptsMetricsAuthority() throws Exception {
    mockMvc.perform(get("/actuator/prometheus")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_metrics.read")
            )))
        .andExpect(status().isOk());
}

@Test
void metricsEndpointRejectsAnonymousCaller() throws Exception {
    mockMvc.perform(get("/actuator/prometheus"))
        .andExpect(status().isUnauthorized());
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

Ví dụ cần Spring Security Test, MockMvc và JWT test support. Kết quả 404 có thể xuất hiện nếu endpoint không được expose hoặc management path khác; cấu hình integration test phải tương ứng application context thật.

Ngoài test controller/security, kiểm thử scrape end-to-end từ Prometheus hoặc một client test trong cùng network. Xác nhận scrape target UP, sample timestamp tiếp tục tiến và dashboard không còn khoảng trống.

## 12. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Prometheus nhận 401 | Thiếu token hoặc scraper chưa cấu hình credentials | Kiểm tra scrape auth config và secret reference |
| Token có vẻ hợp lệ nhưng vẫn 401 | Expired, issuer/audience/signature sai hoặc JWK unavailable | Kiểm tra decoder logs và identity provider |
| Health probe nhận 401 | Health path bị bảo vệ bằng authentication | Tạo probe rule/identity tối thiểu |
| Prometheus nhận 403 | Đã authenticate nhưng thiếu metrics scope | Kiểm tra granted authorities và matcher |
| Endpoint trả 404 | Sai port/base path hoặc chưa expose | Kiểm tra Actuator exposure và management config |
| Local curl thành công, scraper thất bại | Secret, DNS, proxy hoặc network path khác nhau | Test từ scraper pod và so sánh request path |
| Authorization header mất sau ingress | Proxy không forward header | Kiểm tra gateway/ingress policy |
| Chỉ management port lỗi | Management security chain/address/port mapping sai | Kiểm tra management context và service targetPort |
| Basic auth ngừng hoạt động sau rotation | Scraper vẫn dùng secret cũ | Cập nhật secret và xác minh rollout |
| mTLS handshake thất bại | Certificate hết hạn hoặc trust chain sai | Kiểm tra client/server certificate và truststore |
| CSRF trả 403 | Request bị CSRF protection chặn | Kiểm tra method, CSRF matcher và security logs |
| Scrape thành công nhưng dashboard vẫn trống | Query/labels hoặc scrape interval sai | Kiểm tra raw series và Prometheus targets |

### Checklist sau khi sửa

1. Request từ đúng scraper identity trả 200.
2. Caller thiếu credentials nhận status theo policy dự kiến.
3. Caller authenticated nhưng thiếu role nhận 403.
4. Health probe chỉ đọc được dữ liệu tối thiểu.
5. Management endpoints vẫn giới hạn trong network dự kiến.
6. Prometheus target chuyển UP và scrape samples mới xuất hiện.
7. Không có credentials/token trong logs hoặc test output.

## 13. Thực hành: sửa lỗi Prometheus scrape nhận 401

**Bối cảnh:** order-service expose /actuator/prometheus trên management port 8081. Sau một lần rotate secret, Prometheus target chuyển DOWN với HTTP 401. Application API trên port 8080 vẫn hoạt động.

### Phần A — Thu thập bằng chứng

1. Ghi lại thời điểm scrape fail và target URL.
2. Xác nhận port 8081 và path /actuator/prometheus.
3. Kiểm tra scrape configuration đang dùng secret reference nào.
4. Kiểm tra application security logs và authentication failure reason.
5. Xác minh proxy/service có forward Authorization header hay không.

### Phần B — Khắc phục và xác minh

1. Cập nhật scraper sang credential mới bằng secret manager.
2. Kiểm tra token/identity có authority metrics-read phù hợp.
3. Xác nhận filter chain của management server match đúng request.
4. Gọi endpoint từ môi trường test với cùng identity.
5. Kiểm tra Prometheus target chuyển UP và samples mới được ingest.
6. Thu hồi credential cũ sau khi rollout hoàn tất.

### Phần C — Câu hỏi tự đánh giá

1. HTTP 401 khác 403 ở giai đoạn nào của security flow?
2. Vì sao application API hoạt động không chứng minh management endpoint hoạt động?
3. Làm sao xác định request đi qua SecurityFilterChain nào?
4. JWT có thể bị từ chối dù chữ ký hợp lệ vì những lý do nào?
5. Vì sao Prometheus scraper nên có identity riêng?
6. Khi nào 404 cho biết endpoint chưa expose?
7. CORS có giải quyết lỗi 401 của scraper không?
8. Reverse proxy có thể làm mất authentication như thế nào?
9. Những log nào giúp phân biệt authentication failure và authorization denial?
10. Làm thế nào chứng minh lỗi đã được khắc phục end-to-end?

## 14. Ghi nhớ

**Actuator endpoint bị 401** thường là vấn đề authentication: credentials thiếu, sai, hết hạn hoặc request đi qua security chain không như dự kiến. Hãy xác nhận đúng endpoint, port, base path và exposure trước; sau đó kiểm tra caller identity, Authorization header, token validation, filter chain và proxy/TLS. Phân biệt 401 với 403 để biết lỗi nằm ở authentication hay authority mapping.

Thiết kế quyền riêng cho health probes, Prometheus scraper và operator. Dùng credentials/workload identity được quản lý an toàn, không ghi token vào logs và không mở permitAll() cho toàn bộ Actuator chỉ để sửa scrape. Kiểm thử 200/401/403 và xác minh scrape từ đúng network path. Sau khi khắc phục, xác nhận target UP, samples mới được ingest và dashboard tiếp tục cập nhật. Quy trình dựa trên bằng chứng giúp khôi phục telemetry mà vẫn giữ management endpoints được bảo vệ.
