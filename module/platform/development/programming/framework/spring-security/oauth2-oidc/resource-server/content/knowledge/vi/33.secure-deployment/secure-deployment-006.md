# Bảo vệ thông tin xác thực introspection và quy trình luân chuyển

Khi Spring Security Resource Server xác minh opaque access token, nó thường gọi một **introspection endpoint** của Authorization Server. Request này có hai loại thông tin cần được bảo vệ riêng:

- **Access token của người dùng hoặc client:** token mà Resource Server cần hỏi trạng thái.
- **Thông tin xác thực của chính Resource Server:** client ID và client secret (hoặc cơ chế client authentication khác) dùng để chứng minh với Authorization Server rằng ứng dụng có quyền gọi introspection endpoint.

Hai loại credential có vòng đời và mục đích khác nhau. Client secret introspection không phải access token của người dùng, không phải secret ký JWT và cũng không phải mật khẩu của người dùng. Nó là credential của một OAuth client đại diện cho Resource Server. Nếu credential này bị lộ, attacker có thể mạo danh Resource Server để hỏi trạng thái token hoặc truy cập các khả năng khác mà client registration được cấp.

Bảo vệ credential introspection vì vậy cần cả cấu hình tối thiểu quyền, lưu trữ secret an toàn, TLS, kiểm soát log, quy trình rotation có overlap, rollback và kiểm thử sau khi đổi secret. Việc thay secret phải được phối hợp với Authorization Server và tất cả instance Resource Server đang chạy.

## 1. Introspection là gì và ai xác thực với ai?

Theo OAuth 2.0 Token Introspection (RFC 7662), Resource Server gửi token tới endpoint do Authorization Server công bố để hỏi token có active hay không và lấy các metadata được phép trả về.

Ví dụ một request introspection:

~~~http
POST /oauth2/introspect HTTP/1.1
Host: auth.example.com
Authorization: Basic <resource-server-client-credentials>
Content-Type: application/x-www-form-urlencoded

token=<access-token>&token_type_hint=access_token
~~~

Có hai credential xuất hiện trong request:

| Giá trị | Đại diện cho ai? | Mục đích |
| --- | --- | --- |
| Client ID/secret trong HTTP Basic | Resource Server (OAuth client đã đăng ký) | Xác thực ứng dụng gọi introspection endpoint |
| token trong form body | Caller/user/service đã nhận access token | Để Authorization Server tra cứu trạng thái và claims của token |

Authorization Server xác thực Resource Server trước, sau đó mới đánh giá token được gửi trong tham số token. Resource Server không được nhầm hai danh tính này với nhau.

Ví dụ, orders-api có thể được đăng ký làm confidential client chỉ để gọi introspection. Request đó mang client ID của orders-api và secret tương ứng, trong khi tham số token là access token của user user-42 hoặc service orders-worker.

### Client secret introspection không phải signing key

- JWT signing key là private key hoặc secret mà issuer dùng để ký token.
- JWT verification key là public key hoặc secret mà Resource Server dùng để xác minh chữ ký theo profile.
- Introspection client secret xác thực Resource Server với introspection endpoint.
- User password là thông tin đăng nhập của người dùng tại Authorization Server.

Đổi introspection client secret thường không làm thay đổi chữ ký JWT đã phát hành và cũng không tự động thu hồi access token của người dùng. Nó thay đổi khả năng Resource Server xác thực với endpoint introspection.

## 2. Vì sao introspection credential có giá trị cao?

Nếu attacker lấy được client secret của Resource Server, họ có thể thử:
- Gọi introspection endpoint dưới danh nghĩa ứng dụng.
- Tra cứu trạng thái token mà client registration được phép introspect.
- Tìm hiểu claims/subject/client metadata mà endpoint trả về.
- Tạo tải lớn lên Authorization Server bằng các request introspection.
- Lạm dụng các grant hoặc API khác nếu cùng client registration được cấp quyền vượt nhu cầu.
- Dùng secret để mạo danh Resource Server trong hệ thống khác nếu secret bị tái sử dụng.

Phạm vi thiệt hại phụ thuộc Authorization Server và quyền client registration. Vì vậy, mỗi Resource Server nên có client identity riêng hoặc một phạm vi chia sẻ được kiểm soát, chỉ được cấp quyền introspection cần thiết.

Không dùng một client secret chung cho mọi microservice nếu có thể cấp credential riêng. Nếu orders-api bị compromise, credential riêng giúp giới hạn ảnh hưởng và cho phép rotation độc lập.

## 3. Nguyên tắc cấp quyền tối thiểu cho introspection client

Tạo một OAuth client registration dành riêng cho Resource Server. Chỉ cấp:
- Quyền gọi introspection endpoint cần thiết.
- Quyền xem loại token/claims mà API thực sự cần.
- Audience hoặc resource scope theo chính sách của Authorization Server nếu sản phẩm hỗ trợ.
- Mạng truy cập từ workload/namespace được phép nếu AS có network policy.

Tránh cấp thêm:
- client_credentials access token cho API nghiệp vụ nếu không cần.
- Quyền gọi token endpoint để xin token thay mặt user.
- Quyền quản trị client hoặc user.
- Quyền đọc claims nhạy cảm không liên quan.
- Quyền introspect mọi loại token nếu AS có thể giới hạn.

Một số Authorization Server dùng cùng client registration cho nhiều chức năng hoặc không cung cấp permission riêng cho introspection. Khi đó, ghi nhận giới hạn của sản phẩm và giảm thiểu rủi ro bằng client riêng, secret riêng, network restriction, rate limit và monitoring.

### Một client cho mỗi Resource Server

~~~text
Authorization Server
  |
  +-- orders-api-introspection
  |      +-- client ID riêng
  |      +-- secret riêng
  |      +-- chỉ dùng bởi Orders API
  |
  +-- billing-api-introspection
  |      +-- client ID riêng
  |      +-- secret riêng
  |      +-- chỉ dùng bởi Billing API
  |
  +-- reporting-api-introspection
         +-- client ID riêng
         +-- secret riêng
         +-- chỉ dùng bởi Reporting API
~~~

Nếu nhiều instance của cùng một Resource Server chạy trong một cluster, chúng có thể dùng chung một client registration của ứng dụng đó, nhưng secret phải được cấp qua secret management và giới hạn theo workload identity. Việc dùng chung secret giữa các service không liên quan làm tăng phạm vi ảnh hưởng khi một service bị lộ.

## 4. Client authentication tại introspection endpoint

RFC 7662 yêu cầu introspection endpoint được bảo vệ bằng cơ chế authorization phù hợp. Cách phổ biến là confidential client authentication bằng HTTP Basic qua TLS.

~~~http
Authorization: Basic base64(client_id:client_secret)
~~~

Base64 chỉ là encoding, không phải encryption. TLS là bắt buộc để bảo vệ credential trên đường truyền. Không gửi client secret qua HTTP không mã hóa.

Các cơ chế khác có thể được Authorization Server hỗ trợ:
- client_secret_post: client ID/secret trong form body.
- private_key_jwt: client ký assertion bằng private key đã đăng ký.
- Mutual TLS client authentication.
- Cơ chế client authentication đặc thù của nhà cung cấp.

**Không phải mọi Spring Security version hoặc cấu hình Boot đều hỗ trợ mọi phương thức này qua property mặc định.** Constructor thông dụng của NimbusOpaqueTokenIntrospector nhận introspection URI, client ID và client secret, thường dùng HTTP Basic. Nếu AS yêu cầu private_key_jwt, mTLS hoặc phương thức khác, cần kiểm tra API của version đang dùng và cấu hình custom introspector/client authentication tương ứng. Không đổi tên property hoặc giả định Boot tự chuyển sang phương thức khác.

### Không đưa secret vào URL

Không cấu hình dạng:

~~~text
https://client-id:client-secret@auth.example.com/oauth2/introspect
~~~

Không đặt secret trong query string. URL có thể xuất hiện trong proxy logs, tracing, browser history hoặc telemetry. Dùng cơ chế client authentication được hỗ trợ và TLS.

## 5. Cấu hình Spring Boot cho opaque token

Spring Boot cung cấp các property Resource Server opaque token phổ biến:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://auth.example.com/oauth2/introspect
          client-id: orders-api-introspection
          client-secret: <secret-injected-at-runtime>
~~~

Giá trị secret-injected-at-runtime là placeholder mô tả giá trị được inject từ secret store; không ghi literal placeholder này vào production config. Với Spring Boot, có thể dùng externalized configuration, environment variable được secret manager inject hoặc file/config tree theo cơ chế được phiên bản Boot hỗ trợ.

Ví dụ property name môi trường tương ứng thường theo dạng:

~~~text
SPRING_SECURITY_OAUTH2_RESOURCESERVER_OPAQUETOKEN_INTROSPECTION_URI
SPRING_SECURITY_OAUTH2_RESOURCESERVER_OPAQUETOKEN_CLIENT_ID
SPRING_SECURITY_OAUTH2_RESOURCESERVER_OPAQUETOKEN_CLIENT_SECRET
~~~

Tên property và binding cần được xác nhận với Spring Boot version của dự án. Tránh đưa secret trực tiếp vào file YAML được commit.

### Servlet Resource Server

Cấu hình security chain có thể dùng opaque token:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ApiSecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/**").authenticated()
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 ->
                oauth2.opaqueToken(Customizer.withDefaults()))
            .build();
    }
}
~~~

Spring Boot auto-configuration có thể cung cấp introspector dựa trên property. Nếu tự khai báo OpaqueTokenIntrospector, kiểm tra bean precedence và bảo đảm cấu hình client authentication không bị bỏ qua ngoài ý muốn.

### WebFlux Resource Server

Với reactive application, security chain có thể dùng:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
class ReactiveApiSecurityConfiguration {

    @Bean
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/api/**").authenticated()
                .anyExchange().denyAll())
            .oauth2ResourceServer(oauth2 ->
                oauth2.opaqueToken(Customizer.withDefaults()))
            .build();
    }
}
~~~

Reactive Resource Server dùng ReactiveOpaqueTokenIntrospector. Không gọi introspection đồng bộ bằng cách dùng block() trên event loop. Nếu cần custom client authentication hoặc HTTP client, chọn reactive implementation phù hợp với version Spring Security đang chạy.

## 6. Inject secret từ secret manager

Secret nên được quản lý bên ngoài source code và artifact. Một số lựa chọn:
- Vault hoặc secret manager của cloud provider.
- Kubernetes Secret được mã hóa at rest và kiểm soát RBAC, tốt hơn nữa là tích hợp external secret operator/CSI driver.
- Secret store của nền tảng triển khai.
- File secret mount với quyền filesystem tối thiểu.
- Workload identity để lấy secret từ secret manager mà không cần lưu credential truy cập secret store dài hạn trong image.

Ví dụ luồng:

~~~text
Secret Manager
      |
      | cấp secret cho workload identity
      v
Kubernetes / runtime secret integration
      |
      | inject environment hoặc mount file
      v
Spring Boot configuration binding
      |
      v
OpaqueTokenIntrospector
      |
      | HTTPS + client authentication
      v
Authorization Server introspection endpoint
~~~

### Quy tắc lưu trữ

- Không commit client secret vào Git, kể cả branch riêng hoặc file mẫu.
- Không đóng gói secret vào Docker image, JAR, Helm chart hoặc ConfigMap.
- Không ghi secret vào script build, command line hoặc CI log.
- Không đặt secret trong URL hoặc query string.
- Không chia sẻ secret qua ticket, chat, email hoặc tài liệu không có kiểm soát.
- Giới hạn người và workload được đọc secret.
- Bật encryption at rest và audit log ở secret store.
- Dùng secret riêng theo môi trường: dev, staging, production.
- Có owner, ngày phát hành, ngày rotation và quy trình thu hồi.
- Không tái sử dụng secret giữa ứng dụng không liên quan.

Kubernetes Secret mặc định được biểu diễn Base64 trong manifest/API; Base64 không phải encryption. Cần bật encryption at rest trong control plane, giới hạn RBAC, tránh commit manifest chứa secret và ưu tiên tích hợp secret manager nếu phù hợp.

### Environment variable có phải nơi lưu trữ lý tưởng?

Environment variable thường tiện cho Spring Boot externalized configuration, nhưng có thể bị lộ qua process inspection, diagnostic dump, crash report hoặc cấu hình vận hành sai. Nếu nền tảng hỗ trợ, mount secret thành file với quyền truy cập hạn chế hoặc dùng config tree/secret integration. Nếu dùng environment variable, giới hạn quyền đọc process/environment và không dump toàn bộ environment vào log.

Không truyền secret bằng command line argument như --spring...client-secret=...; command line có thể xuất hiện trong process listing, shell history hoặc process supervisor metadata.

## 7. Không làm lộ secret qua logging và diagnostics

Một số nguồn rò rỉ thường gặp:
- Log request/response HTTP đầy đủ.
- Debug logging của OAuth client hoặc HTTP client.
- Wiretap ghi header/body.
- Spring Boot Actuator env, configprops hoặc endpoint diagnostics.
- Exception chứa request body hoặc authorization header.
- Distributed tracing ghi header Authorization.
- APM agent thu thập HTTP headers.
- Heap dump, thread dump hoặc crash dump.
- CI/CD logs khi render config hoặc chạy test.

### Header cần redaction

Tối thiểu phải che:
- Authorization của request introspection (client Basic credentials).
- token trong form body introspection.
- Access token trong request đến Resource Server nếu logging middleware ghi headers.
- client_secret, password, refresh_token và các secret tương đương.
- DPoP proof hoặc JWT claims nhạy cảm nếu không cần thiết.

Redaction cần áp dụng ở proxy, application logger, tracing/APM và log pipeline. Chỉ che ở một tầng không đủ nếu tầng khác ghi raw request.

### Actuator và cấu hình

Nếu bật Actuator:
- Chỉ expose endpoint cần thiết.
- Bảo vệ management endpoint bằng network policy và authentication.
- Kiểm tra sanitization cho property nhạy cảm.
- Không mở env hoặc configprops công khai.
- Không coi sanitization mặc định là lý do để expose endpoint cho mọi người.
- Kiểm thử endpoint diagnostics để bảo đảm client secret bị che.

Không log object cấu hình chứa secret bằng toString(). Không log exception chain nếu nó có thể chứa header/body nhạy cảm mà chưa redaction.

## 8. Bảo vệ kết nối tới introspection endpoint

Client authentication không bảo vệ được secret nếu kết nối bị nghe lén hoặc TLS bị cấu hình sai.

Yêu cầu:
- Dùng HTTPS với hostname đúng.
- Xác minh certificate chain và hostname của Authorization Server.
- Dùng trust store được quản lý; không tắt hostname verification.
- Không dùng trust-all SSL context trong production.
- Chỉ cho workload kết nối đến introspection host/path được allowlist.
- Hạn chế egress network theo namespace/service identity nếu nền tảng hỗ trợ.
- Đặt connect/read/response timeout.
- Kiểm soát redirect; không gửi client credential theo redirect tới host khác.
- Giới hạn connection pool và concurrency.
- Theo dõi TLS handshake, certificate expiry và lỗi trust.

Nếu dùng proxy outbound, xác định proxy có terminate TLS hay không, proxy có nhìn thấy Basic credentials/token không và ai có quyền truy cập proxy logs. Một proxy nội bộ cũng là trust boundary.

### Không gửi token trong query string

RFC 7662 sử dụng POST với token trong request body. Tránh GET URL dạng:

~~~text
GET /oauth2/introspect?token=<access-token>
~~~

Query string dễ bị ghi vào access log, reverse proxy log, tracing và monitoring. Dùng POST form encoding theo introspection protocol.

## 9. Timeout, retry và lỗi introspection

Introspection là một dependency runtime. Nếu endpoint không phản hồi, Resource Server không thể tự suy ra token còn active hay không.

Cần cấu hình:
- Connect timeout.
- TLS handshake timeout.
- Response/read timeout.
- Connection pool acquisition timeout.
- Tổng deadline cho introspection.
- Retry budget nhỏ, có backoff và jitter nếu lỗi tạm thời.
- Rate limit để tránh request storm khi AS chậm.
- Circuit breaker nếu phù hợp kiến trúc.

Không retry vô hạn. Một request API bị treo quá lâu có thể giữ connection, memory và worker resources.

### Phân biệt token inactive với dependency failure

| Tình huống | Ý nghĩa | Cách xử lý |
| --- | --- | --- |
| Introspection trả active: false | AS xác nhận token không active | Từ chối token |
| Introspection trả active: true | AS xác nhận token active | Tiếp tục validation/authorization theo profile |
| HTTP 401/403 từ introspection | Client authentication/authorization có vấn đề | Điều tra credential/registration; không coi là token user inactive một cách tùy tiện |
| HTTP 429 | AS rate limit | Tôn trọng Retry-After nếu có, giảm concurrency |
| HTTP 5xx/timeout/TLS/DNS | Không thể xác định trạng thái token | Fail closed, cảnh báo dependency |
| Response JSON sai schema | Không thể tin kết quả | Fail closed |
| Thiếu active hoặc kiểu dữ liệu sai | Response không đạt contract | Fail closed |

Không được coi lỗi mạng là active: true. Không fallback sang cho phép request chỉ vì introspection endpoint tạm lỗi. Nếu API cần trả 503 cho dependency outage thay vì 401 authentication failure, triển khai exception mapping rõ ràng theo contract của ứng dụng và test hành vi đó. Status mặc định có thể phụ thuộc exception type, Spring Security version và entry point tùy chỉnh.

### Retry có thể làm quá tải Authorization Server

Nếu mỗi API request tạo introspection call và tất cả instance retry ngay khi AS trả 503, outage có thể thành retry storm. Dùng exponential backoff có jitter, giới hạn số lần retry và concurrency. Với synchronous Servlet introspection, bảo vệ request threads và connection pool; với WebFlux, giữ xử lý non-blocking.

## 10. Cache introspection và tác động tới revocation

Introspection thường được gọi theo request hoặc theo cache miss tùy cấu hình. Caching giảm latency và tải AS, nhưng làm chậm khả năng nhìn thấy token bị thu hồi.

Ví dụ:
- Token được introspect lúc 10:00 và trả active.
- Resource Server cache kết quả trong 5 phút.
- Authorization Server revoke token lúc 10:01.
- Nếu cache không được invalidate, Resource Server có thể tiếp tục dùng kết quả active đến khi entry hết hạn.

Do đó, TTL cache phải dựa trên:
- SLA revocation của hệ thống.
- Thời hạn token còn lại (exp) nếu có.
- Độ nhạy của API.
- Tần suất revoke.
- Khả năng invalidate cache khi AS có event.
- Số request introspection và capacity của AS.

Một giới hạn TTL có thể được mô tả:

~~~text
cache_ttl = min(configured_max_ttl, token_expiry - now, revocation_freshness_budget)
~~~

Đây là quy tắc thiết kế, không phải property có sẵn trong mọi Spring Security version.

### Cache active và inactive

- Cache active: true có thể khiến revocation bị trễ; TTL cần ngắn theo yêu cầu.
- Cache active: false trong thời gian ngắn có thể giảm lặp request token đã bị từ chối, nhưng cần tránh khóa nhầm token mới do cache key collision.
- Không cache lỗi mạng/5xx như thể token inactive hoặc active.
- Không dùng TTL vượt quá token expiry.
- Dùng token hash làm cache key thay vì raw token nếu cache system cho phép.
- Bảo vệ cache store và hạn chế quyền đọc dữ liệu.
- Không log cache key nếu nó có thể tái tạo hoặc liên kết tới token.

Spring Security không nên được giả định có cache introspection theo TTL cụ thể trong mọi cấu hình. Nếu cần cache, triển khai wrapper OpaqueTokenIntrospector hoặc ReactiveOpaqueTokenIntrospector phù hợp version, rồi test expiry, revocation và concurrency.

## 11. Quy trình rotation secret có overlap

Rotation an toàn cần bảo đảm các instance cũ và mới không cùng mất khả năng introspect trong lúc rollout.

Mô hình tốt nhất khi Authorization Server cho phép hai secret còn hiệu lực đồng thời cho cùng một client registration:

~~~text
Giai đoạn 1:
  AS chấp nhận secret A
  Tất cả Resource Server dùng A

Giai đoạn 2:
  AS tạo secret B và vẫn chấp nhận A
  Resource Server chưa đổi, request vẫn dùng A

Giai đoạn 3:
  Secret store cập nhật sang B
  Resource Server instance mới/được reload dùng B
  AS chấp nhận cả A và B

Giai đoạn 4:
  Xác minh toàn bộ instance đã dùng B
  Không còn request introspection dùng A

Giai đoạn 5:
  AS thu hồi A
  Chỉ B còn hiệu lực
~~~

### Các bước thực hiện

1. **Kiểm tra khả năng AS:** xác nhận có hỗ trợ nhiều secret active/credential version cho cùng client hay không.
2. **Tạo secret mới:** tạo B, đặt thời hạn/owner và lưu vào secret manager.
3. **Giữ secret cũ:** chưa thu hồi A.
4. **Cập nhật secret store:** chuyển reference/value của workload sang B.
5. **Rollout có kiểm soát:** restart/reload instance theo batch; tránh restart toàn fleet đồng thời.
6. **Xác minh:** theo dõi introspection success, auth failure, client ID, deployment revision và secret version identifier không nhạy cảm.
7. **Xác nhận không còn A:** dùng audit log phía AS hoặc secret version telemetry; không log raw secret.
8. **Thu hồi A:** chỉ sau khi tất cả instance đã chuyển và rollback window kết thúc.
9. **Ghi nhận:** thời điểm tạo, triển khai, xác minh và revoke trong change record.
10. **Kiểm tra sau rotation:** request opaque token hợp lệ vẫn hoạt động; token inactive vẫn bị từ chối.

Overlap giúp tránh downtime trong rollout. Thời gian overlap phải đủ cho deployment, autoscaling, pod restart và rollback window nhưng không kéo dài không cần thiết.

## 12. Khi Authorization Server chỉ cho phép một secret

Một số nhà cung cấp chỉ cho một client secret active tại một thời điểm. Nếu đổi secret sẽ vô hiệu hóa secret cũ ngay lập tức, rolling deployment có thể tạo trạng thái:
- Instance cũ vẫn dùng A.
- AS chỉ chấp nhận B.
- Instance cũ không introspect được.
- Instance mới dùng B hoạt động.

Trong trường hợp này, cân nhắc tạo **client registration thứ hai**:

~~~text
orders-api-introspection-v1 -> client ID A, secret A
orders-api-introspection-v2 -> client ID B, secret B
~~~

Quy trình:
1. Đăng ký client v2 với quyền introspection tương đương và tối thiểu.
2. Lưu secret v2 vào secret manager.
3. Deploy Resource Server dùng client v2 theo batch.
4. Xác nhận mọi instance dùng v2 và introspection thành công.
5. Giữ v1 trong rollback window nếu chính sách cho phép.
6. Thu hồi v1 và xóa secret v1 khỏi secret store sau khi hết rollback window.

Khi dùng client ID mới, cần kiểm tra AS có áp dụng permission, audience, policy hoặc rate limit theo client registration hay không. Không giả định v2 tự có cùng quyền với v1.

Nếu không thể có overlap và cũng không thể có client registration thứ hai, cần lên kế hoạch maintenance window hoặc cutover có kiểm soát. Không thu hồi secret cũ trước khi workload đã sẵn sàng chuyển sang secret mới.

## 13. Rollback khi secret mới có lỗi

Rollback chỉ an toàn khi credential cũ vẫn còn được AS chấp nhận.

Trước khi bắt đầu rotation, ghi rõ:
- Secret version hiện tại.
- Secret version mới.
- Client registration.
- Các instance/namespace sử dụng credential.
- Thời điểm bắt đầu và kết thúc overlap.
- Điều kiện rollback.
- Người/role có quyền revoke credential.

Nếu B không hoạt động:
1. Dừng rollout tiếp theo.
2. Xem lỗi HTTP từ introspection endpoint và audit log AS.
3. Kiểm tra client ID, authentication method, secret version, TLS và endpoint.
4. Nếu A vẫn active, chuyển workload về A.
5. Xác minh introspection phục hồi trên tất cả instance.
6. Giữ B để điều tra hoặc revoke theo incident policy.
7. Chỉ kết thúc overlap khi đã có credential hoạt động ổn định.

Không rollback sang secret A nếu A đã bị compromise hoặc đã bị revoke vì sự cố bảo mật. Trong tình huống đó, dùng credential mới được tạo lại và xử lý incident theo quy trình khẩn cấp.

## 14. Rotation tự động và secret versioning

Secret manager có thể hỗ trợ:
- Tạo version mới.
- Gắn alias/current version.
- Phân phối secret đến workload.
- Audit ai đọc/rotate/revoke.
- Expiry và notification.
- Rollback version nếu credential cũ vẫn active.

Một quy trình tự động có thể gồm:

~~~text
Scheduled rotation trigger
        |
        v
Create new credential at Authorization Server
        |
        v
Store new secret version
        |
        v
Update workload secret reference
        |
        v
Roll out Resource Server instances
        |
        v
Verify introspection success across fleet
        |
        v
Revoke old credential
        |
        v
Close rotation record
~~~

Không tự động revoke secret cũ ngay sau khi tạo secret mới. Cần có bước xác minh rollout và một khoảng overlap đã được phê duyệt.

### Rotation không đồng nghĩa với reload tự động

Cập nhật Kubernetes Secret hoặc secret manager value không đảm bảo mọi Spring Boot application tự nhận giá trị mới. Cần xác nhận:
- Secret được inject qua environment hay mounted file.
- Environment variable có được cập nhật trong process đang chạy không (thông thường process environment không tự đổi).
- Spring configuration có hỗ trợ reload hay không.
- Pod có cần restart để đọc secret mới.
- Connection/client object có giữ credential cũ trong memory hay không.
- Secret rotation controller có restart workload theo version/checksum hay không.

Với environment variable, thường cần rollout/restart pod để process nhận giá trị mới. Với mounted file, file có thể được cập nhật nhưng application không tự reload nếu không có cơ chế hỗ trợ. Không đánh dấu rotation hoàn tất chỉ vì secret store đã có version mới.

## 15. Rotation khẩn cấp khi secret bị lộ

Khi nghi ngờ client secret introspection bị compromise, ưu tiên chặn khả năng sử dụng secret cũ:
1. Xác định client registration và phạm vi các workload đang dùng secret.
2. Tạo credential mới hoặc client registration thay thế theo AS capability.
3. Cập nhật secret store và triển khai workload.
4. Thu hồi credential bị lộ theo incident decision; nếu nguy cơ cao, có thể phải revoke ngay và chấp nhận gián đoạn introspection.
5. Theo dõi các lần authentication thất bại và request đáng ngờ tới introspection endpoint.
6. Kiểm tra audit log AS để xác định client credential bị sử dụng từ đâu.
7. Kiểm tra log/tracing/heap dump/CI artifact có thể đã lưu secret.
8. Xóa hoặc hạn chế quyền truy cập các artifact có secret theo quy trình incident.
9. Đánh giá token/claims đã bị introspect có thể đã bị truy cập trái phép hay không.
10. Ghi nhận nguyên nhân và cải thiện secret distribution/redaction.

Không gửi secret mới qua cùng kênh đã làm lộ secret cũ. Không giữ secret bị compromise active chỉ để tránh downtime nếu threat model yêu cầu revoke ngay.

## 16. Phân biệt rotation client secret và rotation access token

| Thao tác | Thay đổi điều gì? | Tác động điển hình |
| --- | --- | --- |
| Rotate introspection client secret | Credential Resource Server dùng để xác thực với AS | Instance dùng secret cũ có thể không gọi được introspection sau khi secret cũ bị revoke |
| Revoke access token | Trạng thái token caller tại AS | Introspection trả inactive theo propagation/cache policy |
| Rotate JWT signing key | Key AS dùng ký JWT | Resource Server cần JWKS key mới và xử lý overlap/cache |
| Rotate mTLS client certificate | Certificate/private key của client | Cần cập nhật TLS identity/trust và có thể token binding |
| Rotate DPoP key | Key proof-of-possession của client | Token bound với key cũ không tự chuyển sang key mới |

Không dùng thao tác rotate secret introspection để xử lý token bị đánh cắp; hai mục tiêu khác nhau. Tương tự, revoke access token không thay thế việc thu hồi client secret đã lộ.

## 17. Kiểm thử introspection credential và rotation

Cần test ở nhiều tầng.

### Unit/configuration test

- Property binding nhận đúng introspection URI và client ID.
- Secret được lấy từ secret source mong đợi.
- Không có default secret yếu trong production profile.
- Không log object chứa credential.
- Custom introspector dùng đúng authentication method.
- Timeout/retry được áp dụng như thiết kế.

Không in giá trị secret trong assertion failure. Có thể xác nhận secret version ID hoặc mock invocation mà không ghi raw value.

### HTTP integration test với introspection stub

Dùng WireMock, MockWebServer hoặc HTTP server thử nghiệm để kiểm tra:
- POST đến đúng endpoint.
- Token nằm trong form body, không nằm trong query string.
- Client authentication được gửi đúng method.
- active: true tạo principal và authorities phù hợp.
- active: false bị từ chối.
- Sai client secret nhận response lỗi.
- 429/5xx/timeout được xử lý theo policy.
- TLS trust/hostname được xác minh trong test HTTPS nếu cần.

Nếu dùng default Nimbus introspector, kiểm tra request thực tế để xác nhận HTTP Basic theo constructor/configuration đang dùng. Nếu custom introspector dùng private_key_jwt hoặc mTLS, test riêng client assertion/certificate behavior.

### Rotation test

| Bước | Authorization Server | Resource Server | Kỳ vọng |
| --- | --- | --- | --- |
| Trước rotation | Chỉ A active | Tất cả dùng A | Introspection thành công |
| Tạo B | A và B active | Vẫn dùng A | Không gián đoạn |
| Rollout một phần | A và B active | Một số dùng B, còn lại A | Cả hai nhóm hoạt động |
| Rollout hoàn tất | A và B active | Tất cả dùng B | Không còn request bằng A |
| Revoke A | Chỉ B active | Tất cả dùng B | Introspection tiếp tục thành công |
| Thử credential A | A revoked | Test client dùng A | AS từ chối |
| Thử credential B | B active | Test client dùng B | AS chấp nhận |

Test không cần dùng secret production. Dùng client registration và credential test riêng.

### Test cache sau revoke token

Nếu có introspection cache:
- Cache active response.
- Revoke token tại stub/AS.
- Xác nhận behavior trước và sau TTL.
- Kiểm tra invalidation event nếu có.
- Xác nhận outage không biến thành active.
- Xác nhận cache key không lưu raw token.

## 18. Monitoring và cảnh báo

Theo dõi theo client registration/issuer alias, tránh label chứa secret hoặc raw token.

| Chỉ số | Dấu hiệu cần quan sát |
| --- | --- |
| Introspection success rate | Giảm đột ngột sau rotation |
| HTTP 401/403 từ AS | Client ID/secret hoặc permission sai |
| Introspection 429/5xx | Rate limit hoặc AS outage |
| Introspection latency | AS chậm, connection pool bão hòa |
| Timeout/connect/TLS error | Network, trust store hoặc endpoint |
| Active/inactive count | Thay đổi bất thường trong token population |
| Authentication failure tại API | Caller token invalid hoặc introspection dependency lỗi |
| Credential version đang chạy | Xác định instance còn dùng version cũ |
| Instance rollout progress | Xác nhận fleet đã chuyển secret |
| Secret read/audit events | Phát hiện truy cập bất thường |

Không tạo metric label theo client secret version nếu mỗi lần rotate sinh cardinality vô hạn; có thể dùng một label version bounded hoặc log event có cấu trúc. Không ghi raw secret.

### Alert hữu ích

- Tỷ lệ introspection 401/403 vượt ngưỡng sau deployment.
- Introspection latency p95/p99 tăng.
- Tỷ lệ timeout/5xx vượt ngưỡng.
- Instance còn dùng secret version cũ sau thời gian overlap.
- Secret sắp hết hạn hoặc sắp đến lịch rotation.
- Có request introspection từ nguồn mạng ngoài workload được phép.
- AS trả 429 liên tục.
- Actuator/log pipeline phát hiện property nhạy cảm chưa được sanitize.

## 19. Checklist triển khai an toàn

Trước production:
- [ ] Có client registration riêng cho Resource Server.
- [ ] Client chỉ có quyền introspection cần thiết.
- [ ] Client ID/secret không nằm trong source code hoặc image.
- [ ] Secret được lưu trong secret manager hoặc store được bảo vệ.
- [ ] Secret khác nhau giữa dev, staging và production.
- [ ] TLS hostname và certificate validation được bật.
- [ ] Introspection endpoint được allowlist.
- [ ] Token gửi bằng POST body, không qua URL.
- [ ] Authorization header, form body và exception logs được redaction.
- [ ] Actuator/diagnostics được bảo vệ.
- [ ] Timeout, retry budget và concurrency limit được cấu hình.
- [ ] Lỗi introspection không dẫn đến fail-open.
- [ ] Cache TTL đáp ứng revocation SLA.
- [ ] Có quy trình overlap hoặc client registration thứ hai.
- [ ] Có rollback plan trước khi revoke credential cũ.
- [ ] Có test xác nhận mọi instance dùng credential mới.
- [ ] Có audit và alert cho secret access/rotation.

Trong rotation:
- [ ] Tạo secret mới và lưu vào secret manager.
- [ ] Giữ secret cũ active trong overlap.
- [ ] Deploy theo batch.
- [ ] Xác minh success rate và credential version toàn fleet.
- [ ] Chỉ revoke secret cũ sau khi xác nhận.
- [ ] Xóa quyền truy cập secret cũ và đóng change record.

## 20. Những lỗi thường gặp

**“Client secret introspection là access token của user.”** Không. Secret xác thực Resource Server với AS; token trong form body là token cần introspect.

**“Base64 Basic Auth đã mã hóa secret.”** Không. Base64 chỉ encode; cần TLS để bảo vệ trên đường truyền.

**“Có thể ghi request introspection ở DEBUG.”** Không nếu logger ghi Authorization header hoặc form body chứa token. Cần redaction xuyên suốt application, proxy và tracing.

**“Lưu secret trong ConfigMap hoặc Git private là đủ.”** Không. Dùng secret store, RBAC, encryption at rest và audit.

**“Chỉ cập nhật Kubernetes Secret là process đang chạy nhận secret mới.”** Không nhất thiết. Environment variable và object đã bind có thể giữ giá trị cũ; cần rollout/reload được xác nhận.

**“Thu hồi secret cũ ngay khi tạo secret mới.”** Có thể làm các instance chưa rollout xong mất khả năng introspect. Dùng overlap hoặc client registration thay thế.

**“Secret mới lỗi thì luôn rollback secret cũ.”** Không nếu secret cũ đã bị compromise/revoke. Rollback phải theo trạng thái tin cậy của credential.

**“Introspection timeout nghĩa token inactive.”** Không. Đó là dependency failure; không thể kết luận trạng thái token.

**“AS lỗi thì cho request qua để giữ availability.”** Không. Không có kết quả introspection đáng tin thì không được coi token active.

**“Cache active response lâu để giảm tải.”** TTL dài làm chậm nhận biết revocation. Chọn theo freshness/revocation SLA.

**“Rotate client secret sẽ revoke mọi access token.”** Không. Đây là credential của introspection client; token lifecycle là việc riêng.

**“Một secret cho mọi microservice giúp quản lý dễ hơn.”** Nó mở rộng blast radius và khiến rotation khó khoanh vùng.

## 21. Quy trình vận hành đề xuất

1. **Đăng ký client riêng:** tạo confidential client cho từng Resource Server hoặc nhóm có cùng boundary.
2. **Giới hạn quyền:** chỉ cấp quyền introspection và metadata cần thiết.
3. **Chọn authentication method:** dùng HTTP Basic qua TLS nếu phù hợp; xác nhận support trước khi chọn private_key_jwt hoặc mTLS.
4. **Lưu secret an toàn:** secret manager, workload identity, file mount hoặc integration phù hợp.
5. **Inject runtime:** Spring Boot nhận property qua externalized config; không commit secret.
6. **Cấu hình Resource Server:** dùng opaque token introspection với endpoint và client credentials đúng version.
7. **Bảo vệ HTTP:** TLS validation, endpoint allowlist, timeout, pool và redaction.
8. **Xác định cache policy:** TTL theo revocation freshness, không cache lỗi và không lưu raw token làm key.
9. **Thiết kế rotation:** overlap hai secret hoặc tạo client registration thứ hai.
10. **Thực hiện rollout:** update secret store, restart/reload theo batch và xác minh từng instance.
11. **Thu hồi credential cũ:** chỉ sau khi toàn fleet dùng credential mới và rollback window kết thúc.
12. **Theo dõi:** success rate, AS status, latency, secret version, audit và alert.
13. **Diễn tập sự cố:** secret leak, AS outage, bad rotation, rollback và emergency revoke.

**Điểm cần nhớ:** Introspection client secret xác thực **Resource Server** với Authorization Server; access token trong request body là token cần tra cứu. Bảo vệ secret bằng client registration riêng, quyền tối thiểu, secret manager, TLS và redaction toàn bộ log/diagnostics. Khi rotation, ưu tiên hai credential cùng active trong một khoảng overlap; nếu AS không hỗ trợ, dùng client registration mới để cutover theo batch. Chỉ thu hồi credential cũ sau khi xác nhận toàn bộ instance đã dùng credential mới, trừ tình huống compromise cần revoke khẩn cấp. Introspection outage phải fail closed; không coi lỗi dependency là token active.
