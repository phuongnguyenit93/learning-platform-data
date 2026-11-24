# Tránh lộ thông tin xác thực trong URL, log và metadata

Trong hệ thống Spring Cloud Service Discovery, ứng dụng thường phải kết nối tới Eureka, Consul và các service nội bộ. Những kết nối này có thể cần password, API key, bearer token hoặc Consul ACL token. Nếu đặt credential trực tiếp trong URL, ghi toàn bộ header vào log hoặc đưa secret vào service metadata, thông tin có thể bị sao chép sang proxy, dashboard, trace, registry và nhiều consumer khác.

Nguyên tắc an toàn là chỉ truyền credential qua cơ chế xác thực phù hợp, lưu secret trong nguồn quản lý bí mật, giới hạn quyền đọc và không ghi secret vào log hay metadata. Bài học này tập trung vào ba nơi dễ rò rỉ nhất — URL, log và metadata — đồng thời trình bày cách cấu hình, quan sát, xoay vòng và xử lý khi credential đã bị lộ.

## 1. Credential có thể bị lộ ở đâu?

Một credential không chỉ xuất hiện trong mã nguồn. Nó có thể đi qua nhiều thành phần trong một request hoặc quá trình đăng ký service:

```mermaid
flowchart TD
    SECRET[Secret source / Secret Manager]
    APP[Spring Boot application]
    URL[URL / query string]
    HEADER[Authorization header]
    LOG[Application and access logs]
    PROXY[Proxy / gateway / load balancer]
    TRACE[APM / trace / error report]
    REG[Consul / Eureka registry]
    META[Service metadata and tags]

    SECRET --> APP
    APP --> URL
    APP --> HEADER
    URL --> LOG
    URL --> PROXY
    URL --> TRACE
    HEADER --> LOG
    HEADER --> PROXY
    HEADER --> TRACE
    APP --> META
    META --> REG
    REG --> TRACE
```

Các đường rò rỉ thường gặp:

- Query string được ghi vào access log, reverse proxy, CDN, APM hoặc lịch sử công cụ kiểm thử.
- URL có dạng `https://user:password@host` xuất hiện trong exception, cấu hình đã dump hoặc log kết nối.
- HTTP wire logging ghi `Authorization`, `Cookie`, `X-Consul-Token` hoặc request/response body.
- Service metadata và tag được hiển thị trong Consul UI, Eureka Dashboard hoặc API registry, rồi được nhiều consumer đọc lại.
- Actuator `env`, `configprops`, heap dump, thread dump hoặc trang debug để lộ giá trị cấu hình.
- Trace baggage, span tag, metric label hoặc error report mang theo query parameter hay header nhạy cảm.
- Credential được commit vào Git, đưa vào Docker image, manifest, file `.env` hoặc lệnh shell.

TLS bảo vệ dữ liệu trên đường truyền, nhưng không ngăn secret xuất hiện trong log, trace, dashboard hoặc file cấu hình. Vì vậy, mã hóa kết nối cần đi cùng kiểm soát dữ liệu nhạy cảm.

## 2. Không đặt credential trong URL

### 2.1. Tránh userinfo trong URL

Không dùng URL có username/password:

```text
https://service-user:SuperSecret123@eureka.internal.example/eureka/
```

Phần `service-user:SuperSecret123@` là userinfo. URL có thể được lưu nguyên dạng trong cấu hình, exception, log hoặc công cụ giám sát. Khi copy URL để chẩn đoán, credential cũng có thể bị gửi nhầm cho người khác.

Hãy giữ URL chỉ chứa scheme, host, port và path:

```yaml
eureka:
  client:
    service-url:
      defaultZone: ${EUREKA_SERVER_URL:https://eureka.internal.example/eureka/}
```

Xử lý authentication bằng cơ chế mà Eureka client và hạ tầng của phiên bản đang dùng hỗ trợ, chẳng hạn TLS/mTLS hoặc HTTP authentication được cấu hình riêng. Một số cách tích hợp Eureka có thể chấp nhận Basic credentials trong userinfo của URL; nếu hệ thống cũ bắt buộc dùng cách đó, phải lấy giá trị từ secret source, kiểm soát log và có kế hoạch chuyển sang cơ chế không nhúng secret vào URL.

### 2.2. Tránh token trong query string hoặc path

Không truyền token theo các dạng:

```text
https://consul.internal/v1/catalog/services?token=SECRET_TOKEN
https://api.internal/services/SECRET_TOKEN/status
```

Query string và path thường được ghi vào access log và telemetry. Một URL có thể được lưu ở browser history, proxy cache, monitoring event hoặc exception report.

Với Consul HTTP API, truyền ACL token qua header `X-Consul-Token`:

```bash
curl \
  -H "X-Consul-Token: ${CONSUL_HTTP_TOKEN}" \
  "https://consul.internal.example/v1/catalog/services"
```

Với API hỗ trợ OAuth2, truyền access token trong header:

```http
GET /api/orders HTTP/1.1
Host: order.internal.example
Authorization: Bearer <access-token>
```

Header cũng là dữ liệu nhạy cảm và có thể bị ghi vào wire log. Chỉ dùng header khi client, proxy và hệ thống quan sát đã được cấu hình để không ghi giá trị xác thực.

### 2.3. Không gửi credential trong URL ngay cả khi dùng HTTPS

HTTPS mã hóa request trên mạng, nhưng URL vẫn có thể được ghi tại endpoint client, reverse proxy, gateway, server access log, APM hoặc công cụ debug. Nếu token nằm trong query string, mọi thành phần có quyền đọc URL có thể nhìn thấy token sau khi TLS được giải mã ở điểm kết thúc kết nối.

Nếu API chỉ hỗ trợ token qua query string, hãy xem xét thay đổi API hoặc đặt một gateway adapter có khả năng xác thực header và chuyển tiếp an toàn. Chỉ dùng query token như ngoại lệ được đánh giá rủi ro, với token ngắn hạn, scope hẹp và cơ chế redaction trên toàn bộ đường đi.

## 3. Đưa credential ra khỏi source code và cấu hình commit

Không ghi password, ACL token, API key hoặc private key trực tiếp vào `application.yml`:

```yaml
# Không an toàn: secret nằm trong file cấu hình có thể được commit.
spring:
  cloud:
    consul:
      token: "consul-production-secret"
```

Thay vào đó, tham chiếu tới property được cấp từ môi trường bảo mật:

```yaml
spring:
  cloud:
    consul:
      host: ${CONSUL_HOST:localhost}
      port: ${CONSUL_PORT:8500}
      token: ${CONSUL_HTTP_TOKEN}

payment:
  api:
    base-url: ${PAYMENT_API_URL:https://payment.internal.example}
    token: ${PAYMENT_API_TOKEN}
```

Placeholder chỉ tách giá trị secret khỏi file commit. Secret vẫn cần được cung cấp an toàn cho process và không được in ra log. Với Spring Cloud Consul, hãy xác minh property name và cách cấu hình token theo đúng phiên bản starter đang dùng.

### 3.1. Dùng Secret Manager hoặc nền tảng quản lý secret

Các nguồn cấp secret thường gặp:

- Secret manager của cloud provider hoặc hệ thống như HashiCorp Vault.
- Kubernetes Secret được bảo vệ bằng RBAC và encryption at rest, hoặc được đồng bộ từ secret manager bằng external-secrets controller.
- Secret file được mount read-only vào container.
- Biến môi trường do hệ thống triển khai cấp, nếu đó là phương án phù hợp với threat model và công cụ vận hành.

Không bake secret vào Docker image hoặc ghi secret vào manifest được lưu trong Git. Hạn chế người có quyền `exec` vào Pod, đọc environment, đọc file mount hoặc xem cấu hình runtime.

### 3.2. Dùng config tree cho secret được mount thành file

Spring Boot hỗ trợ import cấu hình dạng config tree. Ví dụ, secret được mount tại `/run/secrets/payment.api.token`:

```yaml
spring:
  config:
    import: "optional:configtree:/run/secrets/"
```

Tên file trong thư mục config tree được ánh xạ thành tên property; file `payment.api.token` cung cấp property `payment.api.token`. Ứng dụng có thể inject property đó như các nguồn cấu hình khác mà không ghi giá trị vào `application.yml`.

Đường dẫn mount và quyền file phải giới hạn cho user chạy ứng dụng. Không in nội dung file secret trong startup log hoặc diagnostic endpoint.

## 4. Truyền credential bằng header trong Spring

Ví dụ sử dụng `WebClient` với bearer token lấy từ externalized configuration:

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class PaymentClientConfiguration {

    @Bean
    WebClient paymentWebClient(
            WebClient.Builder builder,
            @Value("${payment.api.base-url}") String baseUrl,
            @Value("${payment.api.token}") String token) {
        return builder
                .baseUrl(baseUrl)
                .defaultHeaders(headers -> headers.setBearerAuth(token))
                .build();
    }
}
```

URL chỉ chứa địa chỉ service. Token được gửi trong `Authorization` header khi client gọi API. Trong ứng dụng lớn, có thể dùng Spring Security OAuth2 Client để lấy và làm mới access token thay vì giữ một bearer token tĩnh trong thời gian dài.

Không log object `WebClient`, header collection, request specification hoặc cấu hình bean nếu chúng có thể chứa token. Khi bật HTTP wiretap để debug, phải kiểm tra thư viện đang dùng có ghi header/body hay không và chỉ bật trong môi trường kiểm thử với dữ liệu giả.

### 4.1. Gọi Consul HTTP API

Ví dụ dùng header riêng của Consul:

```bash
curl \
  -H "X-Consul-Token: ${CONSUL_HTTP_TOKEN}" \
  -H "Accept: application/json" \
  "https://consul.internal.example/v1/health/service/order-service?passing"
```

Token không xuất hiện trong URL. Cần bảo đảm shell history, process inspection, CI log và proxy không ghi lại giá trị header. Tránh dùng `curl -v` hoặc `--trace` trong terminal/CI production vì các tùy chọn này có thể in request header.

### 4.2. Kết nối Eureka

Giữ `defaultZone` sạch credential:

```yaml
eureka:
  client:
    service-url:
      defaultZone: ${EUREKA_SERVER_URL:https://eureka.internal.example/eureka/}
```

Authentication cho Eureka phụ thuộc phiên bản client, HTTP transport và hạ tầng bảo vệ endpoint. Ưu tiên TLS/mTLS hoặc cơ chế xác thực được hỗ trợ và cấu hình riêng. Nếu buộc phải dùng HTTP Basic theo cơ chế URL userinfo của một client cũ, coi URL đó là secret: không log, không hiển thị trong Actuator, lấy từ secret manager và lên kế hoạch thay thế.

## 5. Không đưa secret vào service metadata, tag hoặc instance ID

Metadata của Eureka và Consul được thiết kế để mô tả instance, không phải để lưu credential. Metadata có thể được trả về trong discovery response, hiển thị trong dashboard, sao chép giữa registry peer hoặc được consumer đọc.

Ví dụ metadata an toàn:

```yaml
eureka:
  instance:
    metadata-map:
      zone: zone-a
      version: v2
      runtime: kubernetes
```

Ví dụ không an toàn:

```yaml
eureka:
  instance:
    metadata-map:
      api-token: "secret-token-value"
      database-password: "db-password"
      consul-acl-token: "consul-token-value"
```

Với Consul, tags và metadata cũng có thể được đọc qua Catalog/Health API. Không đưa secret vào `tags`, `meta`, service name, node name, instance ID hoặc check output.

Nên dùng metadata cho các giá trị không nhạy cảm, có ích cho discovery hoặc vận hành:

- `zone`, `region`, `cluster`, `namespace`.
- `version`, `build`, `protocol`.
- Nhóm chức năng hoặc capability không chứa thông tin bí mật.

Không dùng metadata để truyền token giữa provider và consumer. Nếu consumer cần credential để gọi provider, cấp credential riêng qua secret manager hoặc workload identity; discovery chỉ cung cấp địa chỉ và thông tin định tuyến.

## 6. Log an toàn: ghi điều cần chẩn đoán, bỏ dữ liệu xác thực

Log hữu ích để điều tra sự cố, nhưng không nên ghi toàn bộ request/response. Một log an toàn thường chỉ cần service name, route template, status code, duration, trace ID và một định danh correlation không nhạy cảm.

Ví dụ log nên dùng:

```java
log.info(
    "Dependency call service={} method={} route={} status={} durationMs={} traceId={}",
    "payment-service",
    "POST",
    "/payments",
    statusCode,
    durationMs,
    traceId
);
```

Tránh log trực tiếp:

```java
// Không an toàn: có thể chứa query token, userinfo hoặc dữ liệu nhạy cảm.
log.info("Request URL: {}", request.getRequestURL());
log.debug("Headers: {}", requestHeaders);
log.debug("Request body: {}", requestBody);
```

`request.getRequestURL()` không nhất thiết chứa query string trong Servlet API, nhưng URL hoặc path vẫn có thể mang dữ liệu nhạy cảm. Không dựa vào một API getter để bảo đảm dữ liệu đã được làm sạch; hãy log route template do ứng dụng kiểm soát và loại bỏ query/body mặc định.

### 6.1. Những trường cần redaction

Khi cần log header hoặc cấu hình để chẩn đoán, hãy áp dụng allowlist và redaction ở logger/collector. Các trường thường cần che:

| Trường | Xử lý |
| --- | --- |
| `Authorization` | Không ghi giá trị; nếu cần chỉ ghi loại scheme như `Bearer` hoặc `Basic`. |
| `Proxy-Authorization` | Che toàn bộ. |
| `X-Consul-Token` | Che toàn bộ. |
| `Cookie`, `Set-Cookie` | Che toàn bộ hoặc loại khỏi log. |
| `access_token`, `refresh_token`, `id_token` | Không ghi query/body value. |
| `api_key`, `api-key`, `client_secret`, `password` | Che toàn bộ. |
| Private key, certificate material, secret file content | Không log. |

Redaction nên được thực hiện ở nhiều lớp: ứng dụng, reverse proxy/API gateway, log collector và APM. Một bộ lọc regex đơn lẻ không thể bảo đảm che mọi cách viết, encoding hoặc tên field; ưu tiên không thu thập dữ liệu nhạy cảm ngay từ đầu.

### 6.2. Hạn chế HTTP wire logging

Trong production:

- Không bật debug/wiretap ghi toàn bộ request và response nếu chưa có redaction đã kiểm chứng.
- Không log tất cả header hoặc body chỉ để tìm lỗi kết nối.
- Không đưa token vào exception message hoặc custom error response.
- Không dump `Environment`, `ConfigurationProperties`, HTTP client config hoặc bean graph ra log.
- Khi cần debug, dùng request ID, status, duration, route template và thông tin lỗi đã làm sạch.

### 6.3. Bảo vệ log và trace sau khi ghi

Ngay cả log đã redaction vẫn có thể chứa hostname nội bộ, service topology hoặc định danh khách hàng. Hãy giới hạn quyền đọc, thời gian lưu giữ, khả năng export và quyền truy vấn log. Trace baggage/span attribute cũng cần cùng chính sách; không đưa token hoặc header nhạy cảm vào baggage vì chúng có thể được truyền qua nhiều service.

## 7. Bảo vệ endpoint chẩn đoán và cấu hình runtime

Spring Boot Actuator có các endpoint hỗ trợ quan sát cấu hình và trạng thái. Những endpoint như `env`, `configprops`, `heapdump`, `threaddump` hoặc `loggers` có thể tiết lộ thông tin nội bộ nếu expose hoặc cấp quyền quá rộng.

Chỉ expose endpoint cần thiết:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info
  endpoint:
    health:
      show-details: never
```

Nếu cần `env`, `configprops` hoặc endpoint quản trị khác trong môi trường nội bộ, phải bảo vệ bằng authentication/authorization, network policy và quyền tối thiểu. Spring Boot có cơ chế sanitization cho một số giá trị nhạy cảm, nhưng không nên xem đó là lý do để mở endpoint cấu hình ra mạng công khai. Kiểm tra hành vi sanitization và endpoint exposure theo phiên bản đang dùng.

Không đưa secret vào error response, startup banner, health detail, metric label hoặc log khi ứng dụng không thể phân giải placeholder. Lỗi cấu hình nên cho biết tên property bị thiếu, không in giá trị bí mật.

## 8. Quản lý vòng đời credential

Credential an toàn cần được cấp, giới hạn, xoay vòng và thu hồi có quy trình:

1. **Cấp riêng theo workload:** mỗi service hoặc môi trường có token riêng, không dùng chung token quản trị cho toàn hệ thống.
2. **Quyền tối thiểu:** token chỉ có quyền đọc service/health hoặc đăng ký đúng service cần thiết; không cấp quyền quản trị nếu ứng dụng chỉ discovery.
3. **Thời hạn phù hợp:** ưu tiên token ngắn hạn hoặc workload identity khi hệ thống hỗ trợ.
4. **Lưu trữ tập trung:** secret manager hoặc secret store được bảo vệ; không commit vào Git, image hoặc artifact.
5. **Xoay vòng:** cấp credential mới, cập nhật workload, xác minh request thành công, rồi thu hồi credential cũ.
6. **Audit:** theo dõi ai cấp, đọc, thay đổi và thu hồi credential.
7. **Thu hồi khi không dùng:** xóa token của instance hoặc pipeline đã kết thúc vòng đời.

Với Consul ACL, tạo token theo policy phù hợp với tác vụ. Consumer chỉ đọc catalog/health không nên dùng token có quyền ghi hoặc quản trị. Provider đăng ký service cần quyền giới hạn vào service/node tương ứng theo mô hình ACL đã thiết kế.

Với Eureka, bảo vệ server bằng TLS và cơ chế authentication phù hợp với client/server version. Không coi việc Eureka không có ACL theo cùng mô hình Consul là lý do để mở registry công khai; cần kiểm soát mạng và danh tính client.

## 9. Xử lý khi credential đã bị lộ

Nếu token xuất hiện trong URL, log, metadata, trace hoặc repository, hãy coi credential đó đã bị lộ. Xóa chuỗi khỏi một file không làm credential cũ mất hiệu lực.

Quy trình xử lý:

1. Xác định loại credential, service/tenant liên quan, phạm vi quyền và thời gian có thể bị lộ.
2. Cấp token/credential thay thế với quyền tối thiểu.
3. Cập nhật secret source và triển khai lại hoặc refresh workload đang dùng credential.
4. Xác minh request hợp lệ bằng credential mới.
5. Thu hồi credential cũ ngay khi các consumer cần thiết đã chuyển đổi; nếu nguy cơ cao, thu hồi khẩn cấp và chấp nhận gián đoạn có kiểm soát.
6. Kiểm tra audit log để tìm truy cập bất thường trong khoảng thời gian credential có thể bị lộ.
7. Hạn chế truy cập log/trace chứa secret, xử lý bản sao và retention theo quy trình incident response của tổ chức.
8. Loại secret khỏi source/config history nếu cần, nhưng vẫn phải rotate/revoke vì Git history và bản sao có thể còn tồn tại.
9. Tìm nguyên nhân gốc: URL logging, wiretap, metadata, debug endpoint, CI output hoặc secret injection.

Không gửi token bị lộ vào ticket, chat hoặc lệnh shell để nhờ người khác kiểm tra. Khi báo cáo, chỉ nêu loại credential, hệ thống bị ảnh hưởng, thời điểm và ID tham chiếu không nhạy cảm.

## 10. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Token xuất hiện trong access log | Token nằm trong query string hoặc path | Chuyển sang header; cấu hình proxy không ghi query khi không cần; rotate token đã lộ. |
| Password xuất hiện trong Eureka URL ở exception | URL dùng userinfo `user:password@host` | Dùng URL không chứa credential và cơ chế authentication riêng; redaction log trong thời gian chuyển đổi. |
| Consul token xuất hiện trong shell/CI log | Dùng `curl -v`, `--trace` hoặc echo biến môi trường | Truyền token qua header nhưng tắt verbose trace; dùng secret masking và kiểm soát process/log. |
| Token xuất hiện trong Eureka/Consul metadata | Dùng metadata làm kênh truyền credential | Xóa metadata nhạy cảm, rotate token và cấp secret qua secret manager. |
| Actuator hiển thị property có secret | Expose `env`/`configprops` hoặc cấu hình sanitization chưa phù hợp | Thu hẹp endpoint exposure, bảo vệ quyền truy cập và xác minh sanitization. |
| APM trace có Authorization header | Instrumentation thu thập header hoặc baggage không lọc | Tắt capture header nhạy cảm và cấu hình denylist/allowlist ở agent. |
| Secret vẫn hoạt động sau khi xóa khỏi YAML | Credential chưa bị revoke; giá trị còn trong Git history hoặc runtime | Rotate/revoke credential và cập nhật mọi workload liên quan. |
| Log redaction bỏ sót biến thể tên field | Chỉ dùng regex đơn giản hoặc casing không đầy đủ | Dùng allowlist logging, chuẩn hóa key và kiểm thử nhiều dạng encoding/casing. |

## 11. Checklist bảo mật trước khi triển khai

- URL không chứa userinfo, password, API key hoặc token trong query/path.
- Token được truyền qua header hoặc cơ chế identity được hỗ trợ; kết nối dùng TLS/mTLS phù hợp.
- Secret được lấy từ secret manager, Kubernetes Secret được bảo vệ hoặc config tree; không nằm trong source/image.
- Consul ACL token có policy tối thiểu và được tách theo workload.
- Eureka endpoint được giới hạn mạng và có authentication/TLS phù hợp.
- Service metadata, tag, instance ID và health output không chứa secret.
- Application log, access log, proxy log, wire log và APM không thu thập header/body nhạy cảm.
- Actuator endpoint cấu hình và quản trị không được expose công khai.
- Log/trace có quyền đọc và retention được kiểm soát.
- Có quy trình rotation, revocation, audit và xử lý credential lộ.

## 12. Ghi nhớ

- Không đặt credential trong URL userinfo, query string hoặc path; URL thường được sao chép vào log, proxy, trace và công cụ debug.
- Dùng `Authorization` header hoặc header riêng như `X-Consul-Token`, kết hợp TLS và redaction.
- Placeholder trong `application.yml` chỉ tham chiếu secret; secret thực tế phải đến từ nguồn quản lý an toàn.
- Service metadata, tags và instance ID là dữ liệu có thể được registry/consumer đọc; không dùng chúng làm secret store.
- Log theo allowlist: route template, status, duration và trace ID; không log raw URL, header, body hoặc toàn bộ cấu hình.
- Bảo vệ Actuator và hệ thống log/APM; không dựa hoàn toàn vào sanitization mặc định.
- Khi credential bị lộ, rotate/revoke trước, rồi xử lý bản sao log/source và điều tra audit.

## Tài liệu tham khảo

- [OWASP: Information Exposure Through Query Strings in URL](https://owasp.org/www-community/vulnerabilities/Information_exposure_through_query_strings_in_url)
- [OWASP: Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [OWASP: Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
- [Spring Boot: Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Boot: Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Consul: ACL Tokens](https://developer.hashicorp.com/consul/docs/security/acl)
