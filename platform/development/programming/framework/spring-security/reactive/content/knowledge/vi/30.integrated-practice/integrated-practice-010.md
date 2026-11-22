# Đánh giá thiết kế từ mô hình đe dọa đến kiểm thử và triển khai — Spring Security Reactive

> **Bài thực hành tổng hợp:** đánh giá một hệ thống WebFlux từ yêu cầu nghiệp vụ, mô hình đe dọa, lựa chọn kiểm soát bảo mật, triển khai Spring Security, kiểm thử các nhánh bị từ chối đến kế hoạch phát hành và vận hành. Ví dụ dùng Java 17+, Spring Boot 3.x và Spring Security 6.x; đối chiếu BOM/API khi sử dụng các phiên bản mới. Các tên miền, tenant, token và tài khoản được minh họa bằng dữ liệu giả.

## 1. Tư duy đánh giá: chứng minh một thuộc tính bảo mật

Một bản thiết kế đạt yêu cầu khi trả lời được sáu câu hỏi có bằng chứng:

1. **Bảo vệ cái gì?** Dữ liệu, hành động và tính chất nào quan trọng: bí mật, toàn vẹn, sẵn sàng, khả năng truy vết, tách biệt tenant?
2. **Ai và cái gì được tin?** Browser, reverse proxy, identity provider (IdP), resource server, database và HTTP downstream đi qua những ranh giới nào?
3. **Kẻ tấn công có thể làm gì?** Chưa đăng nhập, có token hợp lệ của tenant khác, sở hữu client độc hại, có quyền gọi API nhiều lần, hoặc khiến một dependency không phản hồi.
4. **Kiểm soát đặt ở đâu?** Xác minh token, scope/role, kiểm tra ownership, CSRF/CORS, bảo vệ dữ liệu, timeout, rate limit, secrets, audit và hardening.
5. **Kiểm thử chứng minh được gì?** Mỗi threat có ít nhất một phép thử âm tính (tấn công bị từ chối) và bằng chứng kỹ thuật; mock không được đánh tráo với phép kiểm thực tế về crypto/network.
6. **Có thể triển khai an toàn không?** Cấu hình theo môi trường, quan sát dấu hiệu tấn công, rollout/rollback, xoay khóa, kiểm soát thay đổi và kế hoạch xử lý sự cố.

**Không đánh giá chỉ bằng việc “đã bật Spring Security” hoặc HTTP `200`.** Có thể xác thực thành công nhưng trả đơn hàng của tenant khác; có thể chặn route nhưng gửi bearer token đến sai downstream; có thể sử dụng WebFlux nhưng chặn toàn bộ Netty event loop bằng JDBC đồng bộ.

Đầu ra của một cuộc review gồm: sơ đồ data flow/trust boundary, danh sách tài sản, threat register, security decisions, bảng kiểm thử có kết quả, bằng chứng cấu hình deployment và các rủi ro còn lại có người chịu trách nhiệm.

## 2. Case study và giả định rõ ràng

Thiết kế một **Orders API** chạy trên Spring WebFlux. Dữ liệu đơn hàng thuộc nhiều tenant; người dùng hoặc service được xác thực bằng access token do IdP tổ chức cấp.

Các endpoint của bài:

| Endpoint | Ý nghĩa | Chính sách dự kiến |
| --- | --- | --- |
| `GET /public/ping` | Probe công khai không chứa dữ liệu vận hành nhạy cảm | Cho phép anonymous |
| `GET /api/orders/{id}` | Xem một đơn hàng | JWT hợp lệ, scope `orders.read` **và** đơn hàng thuộc tenant trong token |
| `GET /api/admin/metrics` | Chỉ số nghiệp vụ nhạy cảm minh họa | JWT hợp lệ, scope `admin.read` |
| Các endpoint/method chưa công bố | Không có nhu cầu nghiệp vụ | **Deny by default** |

Đây là phạm vi của **ví dụ code chạy được** ở mục 7. Một hệ thống thật có thể bổ sung `POST /api/orders`, thanh toán, cập nhật trạng thái, OAuth2 Client tới downstream, session browser hoặc GraphQL; các rủi ro đó được đánh giá ở những mục riêng, **không mặc nhiên coi chúng đã được triển khai trong demo**.

Giả định và yêu cầu:

- Token định dạng JWT Bearer đặt trong `Authorization`, issuer tin cậy, audience phải dành cho Orders API (ví dụ `orders-api`), thời gian hiệu lực còn hợp lệ. Production xác minh signature bằng trust/JWKS của issuer, không dựa vào chuỗi claim không được xác thực.
- Claim `tenant_id` do IdP tin cậy cấp theo identity đã được phân quyền. Client **không được** tự chọn tenant bằng query/header rồi được ứng dụng tin ngay.
- Scope từ token được Spring Security chuyển thành authority dạng `SCOPE_orders.read` hoặc `SCOPE_admin.read` với cấu hình mặc định phù hợp. Nếu IdP dùng claim tùy biến, phải cấu hình converter và kiểm thử riêng.
- Trong demo, đơn hàng lưu ở bộ nhớ để tập trung vào kiểm soát security. Production phải dùng repository có truy vấn lọc tenant, audit, transaction và bảo vệ DB thích hợp.
- Sample API không sử dụng cookie để xác thực, không chứa form login hoặc HTTP session. Do đó có thể đánh giá việc tắt CSRF **riêng** cho Bearer-only API; nếu bổ sung cookie/browser flow, phải thiết kế lại CSRF trước khi triển khai.
- Không có định danh khách hàng thật, secret thật hoặc service network thật trong ví dụ.

### Chọn tiêu chí nghiệm thu trước khi viết code

| Thuộc tính | Điều kiện chấp nhận |
| --- | --- |
| Authentication | Anonymous bị từ chối tại protected route; token đã hết hạn, sai chữ ký, issuer hoặc audience bị từ chối ở phép thử thực |
| Authorization (endpoint) | Chỉ authority đúng scope được gọi route |
| Authorization (object) | User tenant A không đọc được order của tenant B ngay cả khi có `orders.read` |
| Fail closed | Route/method không khai báo bị từ chối; thiếu `tenant_id` không mặc định thành “mọi tenant” |
| Privacy | Không tiết lộ tên/chi tiết order khác tenant qua body, status hoặc log |
| Availability | Auth filter, DB và downstream không làm nghẽn event loop; có timeout/backpressure/rate limit thích hợp |
| Operations | Secret được cấp ngoài mã nguồn, lỗi cấu hình khiến startup fail an toàn, log không chứa token/PII |

## 3. Data flow diagram và các trust boundary

```text
[User / API client — untrusted]
         |
         | HTTPS, Bearer JWT, input {id}
         v
[Edge / API Gateway / WAF]  -- rate-limit, TLS, size caps -->
         |
         | Boundary A: external client -> internal ingress
         v
[WebFlux Orders API]
   ├─ SecurityWebFilterChain: verify JWT, issuer/audience/time, route scopes
   ├─ Controller: validate input + tenant ownership
   ├─ Reactive service: business rules + audit
   └─ Reactive repository: tenant-scoped DB query
         |                           |
         | Boundary B: app -> DB     | Boundary C: app -> external service
         v                           v
[Orders DB]                   [Payment/Inventory API]
         ^
         |
[Identity Provider] -- Boundary D: token issue / JWKS trust -->
         |
[Workload identity / Secret Manager] -- Boundary E: secret distribution
```

Phân tích mỗi ranh giới:

- **A — internet đến ingress/API:** mọi header, body, path, bearer token có thể bị giả mạo. Gateway giảm tải, nhưng ứng dụng vẫn phải xác minh authentication và object-level authorization; không tin `X-User`, `X-Tenant` chỉ vì request tới từ proxy nếu không có trust contract mạnh.
- **B — ứng dụng đến database:** DB chứa dữ liệu nhiều tenant; chỉ query theo `id` mà không theo tenant có thể vi phạm phân tách. Dùng bind parameters, tenant-scoped query, least privilege và khi thích hợp thêm row-level security.
- **C — ứng dụng đến downstream:** host/redirect có thể bị điều khiển gây SSRF hoặc lộ Bearer; WebClient phải giới hạn destination, timeout và chỉ cấp token đúng audience.
- **D — IdP đến API:** token có signature/`iss`/`aud`/`exp`/`nbf`/algorithm/JWK phù hợp, scope và claim tenant đáng tin. `mockJwt()` trong unit test không chứng minh bất kỳ thuộc tính mật mã nào.
- **E — secret distribution:** client secret, DB password, private key (nếu có), trust credentials và JWT verification keys cần đường cấp, rotation và audit. Resource Server thường chỉ cần public JWKS, không cần private signing key.

### Xác định attacker capability

Dùng ít nhất ba vai để diễn tập:

1. **Anonymous:** không có token, có thể dò endpoint/method, spam request, thêm headers/JSON độc hại.
2. **User hợp lệ của tenant A:** có access token với `orders.read`, cố truy cập order thuộc tenant B; có thể thử đổi ID, header tenant, query hoặc token claim chưa được ký.
3. **Client đã bị compromise hoặc credential bị lộ:** có token/secret thực với scope hạn chế, cố truy cập privilege lớn hơn, tái sử dụng refresh token hoặc gọi tới downstream qua đường dẫn do mình điều khiển.

Không mặc định tin client chỉ vì request là “nội bộ” hoặc có JWT. Authentication nói *ai đang gọi*; authorization quyết định *được phép làm gì với đối tượng cụ thể*.

## 4. Mô hình đe dọa bằng STRIDE và risk register

STRIDE là khung gợi ý, không phải danh sách đầy đủ. Dùng **Spoofing, Tampering, Repudiation, Information disclosure, Denial of service, Elevation of privilege** để lần theo từng data flow. Thêm rủi ro đặc thù API như Broken Object Level Authorization (BOLA), token audience confusion, SSRF và lộ state giữa reactive requests.

Ví dụ risk register trước khi áp dụng kiểm soát:

| ID | Đường tấn công và tài sản | STRIDE | Rủi ro ban đầu | Kiểm soát cần thiết | Phép thử/bằng chứng |
| --- | --- | --- | --- | --- | --- |
| T01 | Token giả, sai issuer, sai audience truy cập Orders API | S/E | Cao | JWT signature + `iss` + `aud` + thời gian + trust JWKS | Signed-invalid/wrong-aud tests, decoder integration |
| T02 | User tenant A đoán ID order của tenant B | I/E | Rất cao | Scope **và** tenant-scoped authorization mỗi object | Cross-tenant request trả 404/403 theo policy, không lộ body |
| T03 | Caller không có `orders.read` gọi protected route | E | Cao | `SecurityWebFilterChain`, deny by default | JWT thiếu scope → 403 |
| T04 | Client gửi `X-Tenant: victim`, app tin header | S/T/E | Cao | Tenant từ identity đáng tin; không tin header/query | Thay header không đổi tenant authorization |
| T05 | WebClient tự gửi token của Orders API tới host độc hại | I | Cao | Fixed destination/allowlist, token đúng audience, không auto-forward | Mock downstream bắt headers; kiểm SSRF |
| T06 | Browser dùng cookie gọi POST cross-site | T | Cao khi có cookie | CSRF protection, cookie flags và CORS policy | Browser-form/CSRF negative tests |
| T07 | Flood API làm nghẽn Reactor Netty hoặc pool DB | D | Cao | Rate limit ở edge, timeout, bounded concurrency, non-blocking I/O | Load/soak tests, event-loop lag, p99 |
| T08 | Token, PII, secret rò qua log/tracing/Actuator | I/R | Cao | Redaction, structured audit, limit management exposure | Log scan, endpoint exposure review |
| T09 | JWK/client secret bị đổi hoặc còn version cũ | S/T | Cao | Workload identity, version/rotation, JWKS cache policy, audit | Key rotation/revocation staging rehearsal |
| T10 | Thiếu audit khiến không thể truy vết hành động admin | R | Trung bình–Cao | Audit event bất biến, correlation/request ID, retained access controls | Test audit fields và retention |
| T11 | Thư viện JDBC/SDK chặn event loop trong auth filter | D | Cao | Reactive driver hoặc `boundedElastic` ở boundary blocking | BlockHound (nếu hỗ trợ), thread/load metrics |
| T12 | Route mới được thêm nhưng quên rule bảo vệ | E | Cao | `anyExchange().denyAll()`; review matcher/actuator mapping | Test unknown route và CI security review |

Cột “rủi ro ban đầu” chỉ là **ước lượng theo ngữ cảnh case study**, không phải phép tính tự động. Trong review thật, ghi **likelihood**, **impact**, hiện trạng kiểm soát, **residual risk**, mức ưu tiên, owner, deadline và quyết định chấp nhận/chặn phát hành. Một bảng có 12 hàng không thay thế khảo sát code, kiến trúc mạng và chính sách dữ liệu thật.

### Phương pháp chấm ưu tiên thực tế

1. Xét **mức độ ảnh hưởng:** mất dữ liệu nhiều tenant, leo quyền admin, compromise IdP thường nghiêm trọng hơn lỗi từ chối một request đơn lẻ.
2. Xét **khả năng khai thác:** endpoint công khai, ID dễ đoán, API không kiểm quyền đối tượng và key bị lộ làm tăng likelihood.
3. Xét **khả năng phát hiện và hồi phục:** audit thiếu, dữ liệu nhạy cảm bị sao chép ra ngoài hoặc key khó rotate làm tăng tác hại.
4. Ưu tiên sửa **T01–T04, T12** trước khi mở traffic thật; kiểm tra lại score sau khi triển khai kiểm soát.
5. Với residual risk còn cao, yêu cầu owner và quyết định rõ ràng; **không** đánh dấu pass chỉ vì unit test đã chạy.

## 5. Đưa mô hình đe dọa thành quyết định thiết kế

### 5.1. Xác thực JWT đúng trust contract

Resource Server WebFlux sử dụng `oauth2ResourceServer(oauth2 -> oauth2.jwt(...))`, cấu hình issuer/JWKS để kiểm signature. Đối với nhiều ứng dụng, Spring Security kiểm những thuộc tính chuẩn như thời hạn và issuer khi cấu hình đúng; **audience là hợp đồng của ứng dụng và cần validation tường minh** nếu resource phải chỉ chấp nhận token dành cho nó.

Không chấp nhận JWT chỉ vì parse được Base64 payload. Không tự tin `alg: none`, không tin `kid` như đường dẫn để lấy khóa tùy ý, và không dùng token `id_token` của OpenID Connect như access token cho một API chỉ vì cùng định dạng JWT.

Nếu IdP phát opaque token thay vì JWT, dùng token introspection phù hợp với cơ chế kiểm tra và cache/timeout có kiểm soát; không ép giải mã opaque token như JWT.

### 5.2. Phân tầng authorization: route + đối tượng + hành động

- **Route:** `GET /api/orders/{id}` đòi `SCOPE_orders.read`.
- **Đối tượng:** order được phép đọc khi tenant đáng tin trên principal bằng tenant của order và các business constraints khác (ví dụ order chỉ dành cho một user trong cùng tenant).
- **Mức dữ liệu:** repository nên query bằng cả `id` và `tenant_id`, tránh load bản ghi của tenant khác rồi mới lọc sau khi đã tạo side effect/log dữ liệu.
- **Mọi đường đi:** nếu có export/batch/job/event handler hoặc admin endpoint khác, không cho phép đi vòng qua service/domain authorization.

Một claim `tenant_id` có mặt trong JWT không bảo đảm nó đúng **nếu chưa xác minh token**; một user có `orders.read` không tự có quyền đọc **mọi** order trong mọi tenant. Đừng dùng `X-Tenant-ID` từ client làm căn cứ phân quyền trừ khi có cơ chế identity-bound delegation đã được thiết kế và kiểm tra.

### 5.3. CSRF và CORS theo loại credential

- **Bearer-only API**: không dựa vào cookie tự gửi theo trình duyệt, nên có thể tắt CSRF cho phần API đó sau khi xác nhận mọi route trong chain đều thỏa điều kiện. Ví dụ code sau cố tình thuộc trường hợp này.
- **Browser session, form login, OAuth2 login có cookie**: không tắt CSRF một cách máy móc; kiểm tra phương thức thay đổi state, cookie `SameSite`/`Secure`/`HttpOnly` và cách cấp/gửi CSRF token.
- **CORS**: chỉ là kiểm soát browser đối với cross-origin response, **không phải cơ chế authentication hay firewall**. Configure allowed origins/methods/headers cụ thể; kiểm preflight `OPTIONS` trước khi yêu cầu bearer nếu ứng dụng phục vụ browser. Không coi “không CORS” là ngăn client/server khác gọi API.
- Nếu có nhiều security chain, tách rõ browser và Bearer API; review thứ tự `securityMatcher`, không cho một chain `permitAll` bắt nhầm route nhạy cảm.

### 5.4. Reactive execution và side effects

- Không gọi `.block()` trong controller, `WebFilter`, `ReactiveAuthenticationManager` hoặc callback Netty; trả `Mono`/`Flux` và compose error/cancellation.
- Dùng R2DBC/async HTTP client khi hợp lý. Nếu SDK bắt buộc blocking, bọc `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` ở **source**, kèm timeout ở SDK, giới hạn concurrency và giám sát queue.
- Authentication/tenant identity qua `@AuthenticationPrincipal` hoặc `ReactiveSecurityContextHolder`, không dùng `SecurityContextHolder` ThreadLocal để suy ra principal.
- API trả `404` cho order không tồn tại và order bị chặn vì tenant khác trong demo; đây là policy giúp giảm enumeration, **không thay thế** chính sách logging/audit việc cố truy cập trái phép.
- WebClient có thể retry; với tác vụ tạo đơn/charge payment phải dùng **idempotency key** và điều kiện retry đúng. Không retry POST gây side effect chỉ vì HTTP request timeout.

### 5.5. Secrets, network và dependency

- Cấp credential DB, OAuth2 client secret, private key qua secret manager/config tree/env kiểm soát. Không commit secret, đưa vào image hoặc log; dùng workload identity, cấp quyền theo workload và môi trường.
- KMS/HSM cho key material nhạy cảm nếu yêu cầu; Resource Server chỉ nên giữ public/JWKS verification material, không tự lưu JWT private signing key.
- WebClient chỉ gọi fixed HTTPS base URL/hostname được duyệt, validate redirect/destination, giới hạn outbound network. Không dùng URL do client nhập thẳng vào `WebClient.uri(...)` để fetch server-side.
- Khi service-to-service dùng OAuth2, chọn `OAuth2AuthorizedClient`/grant/client registration đúng audience downstream. Không tự forward incoming JWT tới mọi downstream như một header mặc định.
- Dependency kiểm CVE/SBOM, container chạy least privilege, TLS/mTLS theo network architecture, hạn chế egress, giới hạn Actuator và management plane.

## 6. Mapping threat → acceptance criteria → bằng chứng

Mỗi quyết định cần ba mặt: **policy**, **test**, **vận hành**.

| Mã | Bằng chứng trước merge | Bằng chứng trước production | Dấu hiệu theo dõi khi chạy |
| --- | --- | --- | --- |
| T01 | Tests route anonymous, wrong scope; decoder validation test riêng | Test JWT có chữ ký sai/`iss`/`aud` sai với IdP/JWKS staging | 401/`invalid_token` tăng, JWKS fetch/rotation error |
| T02 | `WebTestClient` cross-tenant 404, không lộ body | DB integration tenant-scoped query, test migration/schema | Cross-tenant access attempts, policy-deny audit |
| T03/T12 | Route scope tests và deny-by-default | Scan public URLs, gateway paths, methods | 403 spike, unexpected reachable endpoints |
| T04 | Gắn `X-Tenant` giả không đổi kết quả | Test proxy trust policy và forwarding sanitization | Spoofed tenant headers, suspicious request patterns |
| T05 | ExchangeFunction/MockWebServer assert host/token header | Egress allowlist/TLS/certificate và token audience | Egress destination anomalies, OAuth errors |
| T06 | CSRF tests nếu có cookie; CORS preflight tests | Browser integration với Origin thực | CSRF rejects/CORS errors sau rollout |
| T07/T11 | Bounded timeout, no `block()` review, load test | p95/p99, event-loop lag, DB pool saturation thresholds | Latency, rejected rate-limit, scheduler queue |
| T08/T09/T10 | Log scanning + secrets tests + audit schema | Rotation rehearsal, access/RBAC/Actuator review | Secret access audit, token/key failures, audit gaps |

Ví dụ **định nghĩa release gate**:

- Không còn rủi ro Critical/High chưa có biện pháp xử lý hoặc chấp thuận chính thức theo policy.
- Các test phân quyền âm tính bắt buộc pass (anonymous, wrong scope, missing tenant, cross-tenant, admin, unknown route).
- JWT validation thật, egress, CSRF/CORS theo flow và load/timeout đã được diễn tập ở môi trường thích hợp.
- Có owner, link đến evidence pipeline, kết quả kiểm tra logs/secrets và kế hoạch rollback.
- Chỉ chốt pass khi evidence **có thật**; nếu chưa chạy staging/load test, ghi “chưa kiểm chứng”, không tự suy diễn từ unit test.

## 7. Bài thực hành Java 17+: WebFlux Orders API với phân quyền nhiều tầng

Mục này tạo **một demo nhỏ thực thi được trong dự án Spring Boot 3.x**. Mỗi class ghi đúng file riêng, package `demo.review`. Các token test là giả; test trong mục 8 dùng `mockJwt()` để chứng minh authorization logic, còn validation cryptographic ở mục 9.

### 7.1. Dependencies và khởi động

Trong `build.gradle.kts` của dự án đã sử dụng Spring Boot plugin/BOM và Java 17, thêm:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-webflux")
    implementation("org.springframework.boot:spring-boot-starter-security")
    implementation("org.springframework.boot:spring-boot-starter-oauth2-resource-server")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.security:spring-security-test")
}
```

Không thêm `spring-boot-starter-web` vào demo. Với Spring Boot 3, các import ở dưới dùng package `org.springframework.boot.test.autoconfigure.web.reactive` cho `@AutoConfigureWebTestClient`; version 4 có thể tổ chức các module test auto-configuration khác, cần đối chiếu API/BOM thực tế.

Tạo file `src/main/java/demo/review/ReviewApplication.java`:

```java
package demo.review;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReviewApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReviewApplication.class, args);
    }
}
```

### 7.2. Cấu hình authorization: scope trên route, deny mặc định

File `src/main/java/demo/review/ApiSecurity.java`:

```java
package demo.review;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class ApiSecurity {
    @Bean
    SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
        return http
                .securityContextRepository(
                        NoOpServerSecurityContextRepository.getInstance())
                // Chỉ phù hợp API Bearer stateless, không dùng cookie/form.
                .csrf(ServerHttpSecurity.CsrfSpec::disable)
                .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                .authorizeExchange(routes -> routes
                        .pathMatchers(HttpMethod.GET, "/public/ping")
                            .permitAll()
                        .pathMatchers(HttpMethod.GET, "/api/orders/**")
                            .hasAuthority("SCOPE_orders.read")
                        .pathMatchers(HttpMethod.GET, "/api/admin/metrics")
                            .hasAuthority("SCOPE_admin.read")
                        .anyExchange().denyAll())
                .oauth2ResourceServer(oauth2 -> oauth2.jwt(
                        Customizer.withDefaults()))
                .build();
    }
}
```

Chú ý:

- Rule cụ thể đặt trước `anyExchange().denyAll()`, bảo vệ các endpoint không khai báo.
- `SCOPE_orders.read`/`SCOPE_admin.read` là dạng authority của resource server JWT với converter scope mặc định; khi IdP cấp scopes dưới claim khác phải cấu hình converter.
- `NoOpServerSecurityContextRepository` phù hợp thiết kế Bearer stateless của demo, nhưng không được dùng như “mẹo” bỏ session cho browser login.
- Demo chưa bật CORS cho SPA; production phải cấu hình riêng theo Origin/headers/methods được duyệt và test preflight.
- Demo chưa có bean `ReactiveJwtDecoder` production; sử dụng `issuer-uri`/`jwk-set-uri`/custom validator trong cấu hình production ở mục 9. Test ở mục 8 cấp decoder giả chỉ cho test và dùng mock JWT.

### 7.3. Repository demo: lưu hai order khác tenant

File `src/main/java/demo/review/InMemoryOrders.java`:

```java
package demo.review;

import java.util.Map;

import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public class InMemoryOrders {
    private final Map<String, Order> orders = Map.of(
            "ord-a", new Order("ord-a", "tenant-a", "camera"),
            "ord-b", new Order("ord-b", "tenant-b", "keyboard"));

    public Mono<Order> findById(String id) {
        return Mono.defer(() -> Mono.justOrEmpty(orders.get(id)));
    }

    public record Order(String id, String tenantId, String label) {
    }
}
```

Đây là fixture in-memory bất biến để minh họa logic; không có JDBC/JPA/network blocking. **Production** nên dùng API truy vấn lọc cả tenant, ví dụ tên ý tưởng `findByIdAndTenantId(id, tenantId)` với R2DBC, để dữ liệu tenant khác không đi vào service trước khi kiểm quyền. Không dùng Map fixture làm benchmark hoặc giải pháp storage thật.

### 7.4. Kiểm tra ownership bằng identity đáng tin

File `src/main/java/demo/review/OrderController.java`:

```java
package demo.review;

import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Mono;

@RestController
public class OrderController {
    private final InMemoryOrders orders;

    public OrderController(InMemoryOrders orders) {
        this.orders = orders;
    }

    @GetMapping("/public/ping")
    public Mono<String> ping() {
        return Mono.just("pong");
    }

    @GetMapping("/api/orders/{id}")
    public Mono<OrderResponse> getOrder(
            @PathVariable String id,
            @AuthenticationPrincipal Jwt jwt) {
        String tenant = (jwt == null)
                ? null
                : jwt.getClaimAsString("tenant_id");

        // Không cho thiếu tenant claim trở thành quyền toàn cục.
        if (tenant == null || tenant.isBlank()) {
            return Mono.error(new ResponseStatusException(
                    HttpStatus.FORBIDDEN));
        }

        return orders.findById(id)
                .filter(order -> tenant.equals(order.tenantId()))
                .map(order -> new OrderResponse(order.id(), order.label()))
                // Không phân biệt “không có” và “khác tenant”.
                .switchIfEmpty(Mono.error(new ResponseStatusException(
                        HttpStatus.NOT_FOUND)));
    }

    @GetMapping("/api/admin/metrics")
    public Mono<String> adminMetrics() {
        return Mono.just("admin-ok");
    }

    public record OrderResponse(String id, String label) {
    }
}
```

**Hai rào chắn độc lập:** Spring Security filter kiểm scope trước khi gọi handler; controller kiểm `tenant_id` trước khi tạo response. Nếu bỏ filter, tenant A có thể gọi route không đúng scope. Nếu bỏ ownership filter, bất kỳ user có `orders.read` cũng có thể đọc cả tenant B.

Ở ứng dụng thật, phải kiểm thêm claim issuer/audience đã validate, trạng thái tenant, quyền theo user/role/order, phương thức truy vấn và audit. Không lưu thông tin tenant vào một static field/ThreadLocal dùng chung; identity truyền trong reactive request context.

## 8. Kiểm thử âm tính bằng `WebTestClient` và `mockJwt()`

Demo test xác nhận behavior theo hợp đồng HTTP, tách hoàn toàn khỏi authorization server. `mockJwt()` đưa một `JwtAuthenticationToken` giả vào Spring Security Test; nó **không xác minh signature, thời hạn, issuer, audience hoặc JWKS**. Vì vậy phải bổ sung decoder/IdP test thật ở mục 9.

Tạo file `src/test/java/demo/review/ReviewApiTest.java`:

```java
package demo.review;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.security.oauth2.jwt.BadJwtException;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.core.publisher.Mono;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockJwt;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureWebTestClient
@Import(ReviewApiTest.TestDecoder.class)
class ReviewApiTest {
    @Autowired
    WebTestClient client;

    // Test only: tránh auto-config cố truy cập issuer qua mạng.
    @TestConfiguration(proxyBeanMethods = false)
    static class TestDecoder {
        @Bean
        ReactiveJwtDecoder reactiveJwtDecoder() {
            return token -> Mono.error(
                    new BadJwtException("Use mockJwt for this test"));
        }
    }

    @Test
    void publicRouteIsAvailableAnonymously() {
        client.get().uri("/public/ping")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("pong");
    }

    @Test
    void protectedRouteRejectsAnonymous() {
        client.get().uri("/api/orders/ord-a")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void ownerCanReadOwnOrderWithCorrectScope() {
        client.mutateWith(mockJwt().jwt(jwt -> jwt
                    .subject("alice")
                    .claim("scope", "orders.read")
                    .claim("tenant_id", "tenant-a")))
                .get().uri("/api/orders/ord-a")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.id").isEqualTo("ord-a")
                .jsonPath("$.label").isEqualTo("camera");
    }

    @Test
    void userCannotReadOtherTenantsOrder() {
        client.mutateWith(mockJwt().jwt(jwt -> jwt
                    .subject("alice")
                    .claim("scope", "orders.read")
                    .claim("tenant_id", "tenant-a")))
                .get().uri("/api/orders/ord-b")
                .exchange()
                .expectStatus().isNotFound();
    }

    @Test
    void missingReadScopeIsForbiddenEvenForOwner() {
        client.mutateWith(mockJwt().jwt(jwt -> jwt
                    .claim("scope", "orders.write")
                    .claim("tenant_id", "tenant-a")))
                .get().uri("/api/orders/ord-a")
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void missingTenantClaimIsForbidden() {
        client.mutateWith(mockJwt().jwt(jwt -> jwt
                    .claim("scope", "orders.read")
                    .claims(claims -> claims.remove("tenant_id"))))
                .get().uri("/api/orders/ord-a")
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void fakeClientTenantHeaderCannotBypassTenantCheck() {
        client.mutateWith(mockJwt().jwt(jwt -> jwt
                    .claim("scope", "orders.read")
                    .claim("tenant_id", "tenant-a")))
                .get().uri("/api/orders/ord-b")
                .header("X-Tenant-ID", "tenant-b")
                .exchange()
                .expectStatus().isNotFound();
    }

    @Test
    void adminRequiresItsOwnScope() {
        client.mutateWith(mockJwt().jwt(jwt -> jwt
                    .claim("scope", "orders.read")
                    .claim("tenant_id", "tenant-a")))
                .get().uri("/api/admin/metrics")
                .exchange()
                .expectStatus().isForbidden();

        client.mutateWith(mockJwt().jwt(jwt -> jwt
                    .claim("scope", "admin.read")
                    .claim("tenant_id", "tenant-a")))
                .get().uri("/api/admin/metrics")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("admin-ok");
    }
}
```

Chạy trong project đã có wrapper/BOM: `./gradlew test --tests demo.review.ReviewApiTest`; trên Windows: `gradlew.bat test --tests demo.review.ReviewApiTest`. Kết quả mong đợi: **8 phương thức `@Test` pass**, không có stdout ứng dụng bắt buộc. `@SpringBootTest` yêu cầu sample app cùng package được scan, dependency có đủ WebFlux/Security/JWT và phiên bản test tương thích. Class `TestDecoder` chỉ được dùng trong test; khi test với HTTP token thật, thay nó bằng decoder được cấu hình bằng issuer/JWKS.

**Giới hạn chính xác của các assertions:**

- `401` nghĩa là không có authentication hợp lệ ở route cần đăng nhập.
- `403` nghĩa là authentication có mặt nhưng không thỏa rule/claim nghiệp vụ.
- `404` của order tenant khác là chính sách ứng dụng đã chọn để không tiết lộ tồn tại bản ghi. Để chắc chắn không lộ body/metadata, kiểm thêm response và log, không chỉ status.
- `mockJwt()` chỉ mô phỏng principal/authorities. Để kiểm thử converter custom hoặc JWT signature thật, phải dùng test riêng không tạo mock authentication sẵn.
- Demo dùng in-memory repo; không chứng minh R2DBC query đã bind tenant đúng hoặc DB có row-level security.

### Bổ sung một ca kiểm “route mới không được phép”

Ví dụ thêm một controller `GET /private/debug` chỉ trong môi trường test, gọi bằng JWT có scope `orders.read` và mong `403` vì `anyExchange().denyAll()`. Nếu endpoint **chưa tồn tại**, response `404` do không có handler không đủ chứng minh deny-by-default cho một endpoint mới; cần test trên route thực sự được đăng ký. Đây là sự khác nhau giữa **không tìm thấy route** và **route tồn tại nhưng bị security chặn**.

## 9. Xác thực JWT thật và giới hạn của test mock

Khi đưa API lên môi trường thật, phải cấu hình resource-server trust. Ví dụ `application-prod.yml` (các giá trị do runtime cung cấp):

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: ${ORDERS_JWT_ISSUER}
```

Issuer hợp lệ phải có metadata/JWKS và TLS trust phù hợp. Spring Security có cơ chế xác minh issuer/time/signature theo decoder. **Audience dành riêng cho Orders API vẫn phải được bảo đảm**, ví dụ bằng validator custom; không coi `issuer-uri` tự ràng buộc mọi audience.

Mẫu cấu hình **thay thế** cho production decoder, cho phép check issuer và audience tường minh. Đây là **mảnh cấu hình** cần đặt trong `@Configuration` của production, với properties `app.security.jwt-issuer` và `app.security.jwks-uri` được cung cấp; nếu thêm bean này, hãy thống nhất nguồn decoder để không cấu hình hai bean trùng nhau:

```java
@Bean
ReactiveJwtDecoder ordersJwtDecoder(
        @Value("${app.security.jwt-issuer}") String issuer,
        @Value("${app.security.jwks-uri}") String jwksUri) {

    NimbusReactiveJwtDecoder decoder =
            NimbusReactiveJwtDecoder.withJwkSetUri(jwksUri).build();

    OAuth2TokenValidator<Jwt> issuerAndTime =
            JwtValidators.createDefaultWithIssuer(issuer);

    OAuth2TokenValidator<Jwt> audience = jwt ->
            jwt.getAudience().contains("orders-api")
                    ? OAuth2TokenValidatorResult.success()
                    : OAuth2TokenValidatorResult.failure(
                            new OAuth2Error(
                                    "invalid_token",
                                    "Unexpected token audience",
                                    null));

    decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                    issuerAndTime, audience));
    return decoder;
}
```

Các imports của mảnh này (gộp vào class cấu hình tương ứng):

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
```

Production phải kiểm tra thêm quy tắc allowed JWS algorithms, key lifecycle, JWKS cache, clock skew, issuer/audience contract và các claim tenant/role theo chính sách IdP. Lấy `jwksUri` từ **cấu hình deployment đáng tin**, không nhận từ token hoặc request input tùy ý. Nếu IdP dùng tenant mapping phức tạp, thêm converter/validator hoặc authorization service, không chỉ dựa vào string claim.

Ma trận test riêng cho decoder và integration:

| Token hoặc tình huống | Kỳ vọng |
| --- | --- |
| JWT được ký bằng private key test issuer đúng, `aud=orders-api`, còn hạn | Request theo policy được chấp nhận |
| Ký bằng private key lạ | `401 invalid_token` |
| `iss` khác issuer tin cậy | `401` |
| `aud` không có `orders-api` | `401` |
| `exp` quá khứ / `nbf` tương lai vượt allowance | `401` |
| Header `alg` bất hợp lệ/không được phép | `401` |
| JWKS/key rotation | Key mới được chấp nhận; token cũ được xử lý theo TTL/revocation policy |
| IdP/JWKS tạm không sẵn sàng | Behavior theo cache/timeouts được kiểm tra; không bypass verification |

Những phép thử này phải sử dụng **JWT thực đã ký** với key test và decoder thật, hoặc integration environment có IdP/JWKS test kiểm soát. Không dùng `mockJwt()` để kết luận đã xác minh signature, expiry hay issuer. Phải ghi rõ lớp test nào chứng minh điều gì.

## 10. Kiểm thử tích hợp, dữ liệu và luồng downstream

### 10.1. Database/multi-tenant isolation

Đối với R2DBC/PostgreSQL production, kiểm thử query chỉ cho phép đúng tenant, kể cả khi client đoán ID của tenant khác. Một truy vấn minh họa được bind parameter (SQL diễn tả ý tưởng, tùy dialect/schema):

```sql
SELECT id, tenant_id, label
FROM orders
WHERE id = :orderId AND tenant_id = :tenantId;
```

Chỉ dùng bind parameters qua R2DBC `DatabaseClient`/repository, không nối thẳng user input vào SQL. Nếu DB bật row-level security, cần test với **đúng DB role ứng dụng**; connection pool/session state tenant phải được đặt, reset và cô lập đúng. Kiểm tra truy vấn cross-tenant và concurrency, tránh giả định “đã lọc trong controller” là đủ.

### 10.2. WebClient và token outbound

Nếu service gọi Payment/Inventory:

- Chỉ cho phép hostname/HTTPS base URI đã duyệt; không để `orderId` hoặc callback URL do client nhập thành host tùy ý.
- Với OAuth2 Client, kiểm thử đúng client registration, `OAuth2AuthorizedClient` và **token audience/scope của downstream**, tránh forward nguyên incoming bearer tới host khác.
- Dùng MockWebServer/WireMock hoặc fake `ExchangeFunction` để assert request method, URI, header Authorization và không gửi secret/token sang host ngoài scope.
- Kiểm tra xử lý downstream `401/403`, `429`, `5xx`, timeout và cancellation; phân biệt outbound `401` với user inbound thiếu quyền.
- Nếu bổ sung `POST` tạo giao dịch, yêu cầu idempotency key, deduplication ở storage và retry policy tránh double charge.

### 10.3. Session, CSRF, CORS, browser

Nếu sau này có browser login cookie:

- Dùng `WebSession`/Spring Session reactive phù hợp; đừng mang `HttpSession`/servlet filter sang WebFlux.
- Test cookie `Secure`/`HttpOnly`/`SameSite`, session fixation, logout, expired session và chia sẻ session giữa nhiều Pod nếu cần.
- Bật bảo vệ CSRF theo flow; negative test POST/DELETE thiếu CSRF token phải bị chặn.
- CORS: test request preflight và request thật với origin được duyệt và không được duyệt; không bật wildcard với credentials.
- Tách chain bearer-only và browser stateful với matcher/order rõ, để CSRF disable của API không áp dụng nhầm route dùng cookie.

### 10.4. Chặn luồng và độ bền

Các điểm phải kiểm tra trong call graph: `.block()`/`.blockFirst()` trên event loop, `Thread.sleep`, JDBC/JPA, `RestTemplate`, đồng bộ hóa lâu, SDK/KMS gọi blocking, `CompletableFuture.join`, file I/O lớn. Lựa chọn reactive API hoặc offload đúng boundary bằng `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())`; có limits theo DB/downstream. Chạy load test có tình huống chậm/timeout để đo p95/p99 và event-loop lag, không suy throughput từ unit test.

## 11. Ma trận kiểm thử hoàn chỉnh từ PR đến staging

| Lớp kiểm thử | Trường hợp trọng tâm | Có thể dùng công cụ | Giới hạn chứng cứ |
| --- | --- | --- | --- |
| Unit/domain | Ownership rules, tenant missing, validators/DTO | JUnit 5, StepVerifier | Không kiểm Security filter hoặc HTTP routing |
| WebFlux security slice/integration | `401/403/404/200`, scopes, method, default deny, CSRF/CORS phù hợp | `WebTestClient` + Spring Security Test | `mockJwt()` không chứng minh crypto |
| JWT decoder integration | Signature, issuer, audience, expiry, algorithms, JWKS rotation | Signed test JWT + decoder thật/mock JWKS HTTP | Không chứng minh deployment firewall/RBAC |
| Data integration | R2DBC query tenant-scoped, duplicate/idempotency, transactions | Testcontainers/DB cô lập | Không thể thay bằng Map repository |
| HTTP downstream | Bearer forwarding, host allowlist, retries/timeouts | MockWebServer/WireMock | Không tự chứng minh TLS prod/IdP thật |
| Browser integration | Cookie session, CSRF, CORS preflight, redirect/logout | Test browser/HTTP integration | Cần flow browser thật |
| Security pipeline | Secret scanning, SCA/SBOM, linters, image scanner | CI tooling | Scanner có false negatives/positives |
| Dynamic/security checks | BOLA, injection, SSRF, request floods, access bypass | Authorized DAST/pentest trên staging | Chỉ chạy trong phạm vi môi trường được cấp phép |
| Performance/soak | Event-loop saturation, latency, DB pool, retry storms | Load generator + metrics | Không thay thế kiểm security logic |
| Deployment rehearsal | Secret rotation, JWKS, canary/rollback, recovery | Staging tương tự production | Không được báo PASS nếu chỉ có thiết kế trên giấy |

**Đừng gộp “JWT mock pass” với “JWT trust verified”.** Hai quyết định này phải có evidence độc lập. Mỗi test nên ghi: môi trường, phiên bản, commit/artefact, dữ liệu fixture, kết quả, log/trace đã redact và link CI.

## 12. Review checklist theo từng thay đổi

Trước khi approve một pull request có ảnh hưởng security, reviewer nên trả lời:

**Security model và quyền truy cập**

- Route mới có chính sách explicit không? `anyExchange().denyAll()` có còn hoạt động?
- Scope là thuộc tính của **token đã xác minh** hay chỉ là string request đưa lên?
- Mọi truy vấn đối tượng có lọc đúng tenant/owner hoặc kiểm domain policy không?
- Có thể truyền tenant khác bằng path/header/query/body để vượt kiểm quyền không?
- Quyền admin và các hành động thay đổi trạng thái có thêm business approval/audit cần thiết không?
- Với multiple `SecurityWebFilterChain`, chain precedence có làm lộ route không?

**Input và output**

- Path/query/body được validate kích thước, định dạng và các ràng buộc hợp đồng?
- DB query dùng bind parameters; không dynamic SQL/script/path traversal do user control?
- Error response không tiết lộ sự tồn tại của bản ghi tenant khác, stack trace, token hay credential?
- Dữ liệu nhạy cảm được tối thiểu hóa trong JSON/audit/traces; không log nguyên `Authorization`?

**Reactive và dependency**

- Không có blocking call trên Netty event loop; no fire-and-forget `subscribe()` trong handler/filter?
- Downstream có timeout, giới hạn concurrency, circuit breaker/retry hợp lý, không gửi token sai audience?
- Session được quản lý bằng WebFlux APIs, authentication theo Reactor Context?
- Exception được map đúng: unauthorized `401`, authenticated-but-denied `403`, object not visible `404` theo policy?

**Deployment**

- Secret lấy qua approved secret store/identity; không hardcode, không build-arg/image leak?
- Có test rotate/revoke key, TLS trust và network egress? Cấu hình staging/prod có khác về auth không?
- Actuator chỉ expose endpoint cần thiết và có bảo vệ; log/metrics không chứa token/PII?
- Có câu trả lời rõ cho “phát hiện sai phân quyền sau rollout thì rollback/thu hồi token ở đâu”?

## 13. Triển khai an toàn và quan sát kết quả

### 13.1. Cấu hình môi trường

- **Production**: issuer/JWKS/audience trust, HTTPS/TLS, workload identity, DB credentials và downstream URLs lấy từ config quản lý ngoài source code.
- **Fail fast** với giá trị cấu hình bắt buộc thiếu; không dùng default `dev-password` hoặc issuer giả ở production.
- Hạn chế quyền đọc secret theo Pod/service account, tắt dump env, hạn chế `/actuator/env` và `/actuator/configprops`, kiểm tra logs/CI artifact.
- Cấu hình proxy trusted headers để scheme/host/redirect đúng nhưng không tin `X-Forwarded-*` trực tiếp từ internet khi proxy chưa sanitize.
- Phân quyền mạng vào DB/IdP và egress tới downstream được duyệt; private key của signer không nằm trong resource-server image.

### 13.2. Pipeline trước deploy

```text
Commit / PR
  -> code review + threat changes identified
  -> secret scan + dependency scan + SAST
  -> unit + WebFlux authorization negative tests
  -> JWT decoder + R2DBC + HTTP downstream integration
  -> build immutable artifact + provenance/SBOM
  -> staging: DAST authorized + load/timeout + secret/key rehearsal
  -> approve release gates + canary
  -> monitor + expand rollout / rollback
```

Mỗi gate cần lưu bằng chứng. **Không yêu cầu chạy tất cả load/pentest trên mỗi commit**; chọn cadence phù hợp rủi ro và lịch phát hành, nhưng một bản release nhạy cảm phải có kết quả còn hiệu lực. Một dependency vulnerability được chấp thuận tạm thời phải có lý do, owner, thời hạn và mitigation.

### 13.3. Điều quan sát sau rollout

- Tỷ lệ `401` và `403` theo endpoint/tenant đã **ẩn danh phù hợp**, không ghi raw token.
- Các lần cố truy cập cross-tenant, method mới bất thường, request rate vượt baseline, `429` từ gateway.
- Lỗi xác minh JWT, JWKS fetch/cache, issuer downtime, certificate expiry, đồng hồ máy chủ.
- p95/p99 latency, event-loop lag, boundedElastic queue, R2DBC connection pool, downstream timeout/retry.
- Secret manager audit truy cập bất thường, key/secret rotation status, thay đổi access policy.
- Trace ID/correlation ID không chứa user personal data nhạy cảm; audit giữ user/tenant reference theo retention/permission, không để token.

Theo dõi **đường bảo mật** và **độ sẵn sàng** cùng nhau: tỉ lệ 401 tăng có thể do token hết hạn hợp lệ hoặc issuer/key rotation lỗi; 403 tăng có thể do rule scope sai hoặc tấn công BOLA. Chỉ kết luận sau khi kiểm chứng nguồn dữ liệu/triage.

### 13.4. Canary, rollback và sự cố

- Canary trên một phần traffic, kiểm soát feature/routing, so sánh `401/403/5xx`, p99 và hành vi cross-tenant.
- Nếu release có bypass auth, cách ly route/traffic, rollback artifact, tắt quyền/tokens có nguy cơ, điều tra audit; **rollback code không thu hồi dữ liệu đã bị đọc**.
- Với lộ client secret/private key, rotate/revoke tại hệ thống cấp phát, chặn credential cũ, xem lại log/image/Git history và downstream permissions.
- Với JWT signing key rotation, phối hợp `kid`, JWKS caching, TTL token và cửa sổ overlap; không xóa public key cũ sớm gây lỗi tất cả token còn hợp lệ, trừ tình huống compromise cần thu hồi khẩn.
- Khi deploy schema/DB policy liên quan tenant, cần rollback tương thích dữ liệu, test transaction và quyền của DB role thật.

## 14. Các anti-pattern thường làm review thất bại

| Anti-pattern | Vì sao nguy hiểm | Thiết kế/kiểm thử sửa |
| --- | --- | --- |
| `.anyExchange().permitAll()` như default rồi bảo vệ vài route | Route mới dễ bị public | Default deny và test route thực được đăng ký |
| Chỉ kiểm `hasAuthority("SCOPE_orders.read")` | Scope không xác định order thuộc tenant nào | Object-level/tenant-level authorization |
| Tin `X-Tenant-ID` từ client | Có thể giả mạo tenant | Tenant lấy từ verified principal/authorization service |
| `mockJwt()` pass nên tuyên bố signature safe | Mock bỏ qua decoding crypto | JWT signed-invalid tests riêng |
| Không validate `aud` | Token được cấp cho resource khác có thể được chấp nhận | Audience validator theo API contract |
| Chỉ dùng CORS để chặn truy cập | HTTP non-browser vẫn gọi được | JWT, authorization, network controls |
| Tắt CSRF cho mọi flow | Cookie/browser credential có thể bị CSRF | Chia chain theo credential và test |
| `Mono.just(jdbcDao.load(id))` | JDBC chạy ngay, có thể block event loop | R2DBC hoặc `fromCallable + boundedElastic` |
| Tự `subscribe()` trong filter để audit/auth | Side effect chạy ngoài response chain, có thể race/mất context | Compose publisher với reactive operators |
| WebClient forward incoming Authorization mọi host | Lộ token và confused deputy | Chọn outgoing client/token đúng audience + host allowlist |
| Log full JWT, request body/headers để debug | Lộ secret/PII | Redaction, structured audit allowlist |
| Không test thiếu tenant claim | Có thể fail-open | Missing-claim → 403 |
| Tin staging bằng vài unit test | Mất ranh giới network/DB/IdP thật | Integration/load/rotation rehearsal |
| Giữ signing private key ở resource server | Tăng bề mặt compromise | Xác minh bằng public JWKS, private key ở signer |
| Retry payment POST vô điều kiện | Trùng giao dịch khi timeout sau commit | Idempotency/deduplication và retry contract |

## 15. Mẫu báo cáo review có thể sử dụng

```markdown
# Security Design Review: Orders API
## Scope
- Release/commit:
- Data classification and tenant model:
- Included endpoints, services and deployment environments:
- Explicit exclusions:

## Trust boundaries
- Client -> Gateway -> WebFlux
- WebFlux -> IdP/JWKS
- WebFlux -> DB
- WebFlux -> downstream and secret manager

## Threat register
| ID | Asset | Threat | Likelihood | Impact | Control | Test | Owner | Residual risk |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |

## Security decisions
- JWT issuer/audience/expiry/algorithm and key lifecycle:
- Route and object authorization:
- CSRF/CORS/session:
- Input validation and downstream token:
- Reactor nonblocking and quotas:
- Secrets, logging, audit, deployment:

## Evidence
- PR/CI authorization tests:
- Decoder signature/issuer/audience tests:
- DB tenant isolation:
- Downstream/SSRF/timeout checks:
- Staging/browser/load/key rotation:
- Vulnerability/secrets scan:
- Monitoring/rollback rehearsal:

## Release decision
- PASS / CONDITIONAL / BLOCK
- Unresolved risks, owners and due dates:
- Reviewer and approval record:
```

Đây là **biểu mẫu**; các trường trống dành cho review thật, không phải tình trạng của demo hay hệ thống đang triển khai. Một quyết định `CONDITIONAL` chỉ hợp lệ nếu policy cho phép, có owner, mitigation, thời hạn và phạm vi chấp nhận. Nếu token validation/tenant isolation chưa được kiểm thực tế, thông thường cần chặn mở traffic production.

## 16. Bài tập tự đánh giá

1. Một JWT hợp lệ của tenant A có scope `orders.read` nhưng gọi `GET /api/orders/ord-b` thuộc tenant B. Hãy chỉ ra **hai lớp authorization** liên quan và status kỳ vọng.
2. Vì sao thêm `X-Tenant-ID: tenant-b` vào request không được thay tenant identity của JWT?
3. Nếu `mockJwt()` cho phép request có claim `iss=evil`, kết luận nào **không được phép** rút ra từ test đó?
4. Vì sao `issuer-uri` riêng lẻ chưa chắc chứng minh `aud=orders-api` đã được validate?
5. Một frontend dùng cookie session gửi POST qua browser. Có thể sao chép cấu hình `csrf(disable)` của Bearer-only demo không? Cần kiểm thử gì?
6. Khi request đến Payment API bị timeout sau khi server đã charge, vì sao retry không có idempotency key là nguy hiểm?
7. Phép thử nào xác nhận API không trả order của tenant khác **ngay cả khi** user đã qua route-level scope check?
8. Khi route mới `GET /api/orders/export` được thêm, cần review matcher/default deny và authorization object-level như thế nào?
9. Vì sao `Mono.just(jpaRepository.findById(...))` không làm JDBC thành non-blocking?
10. Hãy viết ba gate quan trọng nhất để quyết định mở canary của hệ thống có dữ liệu nhiều tenant và giải thích bằng chứng tương ứng.

## Nguồn học tập và chuẩn đối chiếu

- Spring Security — Reactive WebFlux Security: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Security — Reactive OAuth2 Resource Server JWT: https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html
- Spring Security — Reactive Testing OAuth2/JWT: https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html
- Spring Security — Reactive CSRF: https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html
- Spring Framework — WebFlux Testing: https://docs.spring.io/spring-framework/reference/testing/webtestclient.html
- Spring Framework — WebFlux concurrency model: https://docs.spring.io/spring-framework/reference/web/webflux/new-framework.html
- OWASP — API Security Top 10 (BOLA, Broken Auth, SSRF, Misconfiguration): https://owasp.org/API-Security/
- OWASP — ASVS (yêu cầu xác minh bảo mật ứng dụng): https://owasp.org/www-project-application-security-verification-standard/
- OWASP — Threat Modeling: https://owasp.org/www-community/Threat_Modeling

> Khi dùng trong một dự án thật, thay thông tin giả bằng cấu hình môi trường được cấp quyền, đối chiếu Spring Boot/Security version hiện hành và thu thập **bằng chứng đã chạy** trước khi kết luận kiểm soát nào đạt yêu cầu. Kiểm thử giả lập token, storage hay gateway chỉ chứng minh các tầng mà nó thực sự chạy qua.
