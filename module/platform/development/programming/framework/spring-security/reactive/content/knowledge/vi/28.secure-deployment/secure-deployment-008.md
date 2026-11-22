# Ứng xử an toàn khi JWK, introspection hoặc dịch vụ phân quyền không sẵn sàng (Spring Security Reactive)

## 1. Mục tiêu và bối cảnh

Một Resource Server viết bằng **Spring Boot 3.x, Spring WebFlux và Spring Security 6.x** thường phải tin vào một hoặc nhiều dịch vụ bảo mật bên ngoài. Khi những dịch vụ ấy bị timeout, DNS/TLS lỗi, HTTP 429/5xx, trả dữ liệu bất thường hoặc đang bảo trì, ứng dụng vẫn phải giữ nguyên ranh giới truy cập.

Ba phụ thuộc thường gặp:

- **JWK Set (JWKS)**: chứa public key từ Identity Provider (IdP) dùng để kiểm tra chữ ký JSON Web Token (JWT). Nếu key hợp lệ đã có trong cache, JWT có thể được xác minh **cục bộ** trong một số trường hợp dù IdP đang offline.
- **Token introspection**: Resource Server hỏi IdP token có `active=true` hay không. Khi không nhận được câu trả lời tin cậy, không có bằng chứng cho thấy token còn hiệu lực.
- **Dịch vụ phân quyền/PDP (Policy Decision Point)**: sau khi xác thực, ứng dụng hỏi “subject S có được làm action A trên resource R không?”. Nếu không có quyết định **permit** hợp lệ, hành động được bảo vệ không được chạy.

Kết quả học tập: phân biệt **invalid token**, **forbidden** và **dependency unavailable**; áp dụng **fail closed**; cấu hình JWT/opaque token; xây dựng `ReactiveAuthorizationManager` từ chối khi PDP lỗi; biết giới hạn của cache, retry và circuit breaker; thiết kế kiểm thử cùng metrics/alert.

**Bất biến bảo mật:** không cấp quyền bằng cách bỏ xác minh chữ ký, bỏ kiểm tra thời hạn token, mặc định token `active=true`, hoặc lấy một lần permit cũ không còn được kiểm chứng. Fail closed nghĩa là không thực hiện hành động nhạy cảm khi chưa đủ bằng chứng, không có nghĩa mọi lỗi kỹ thuật bắt buộc trả HTTP 403.

## 2. Xác thực và phân quyền phải được tách biệt

```text
HTTP request đến Spring WebFlux
  |
  +-- Route thật sự public? --------> Áp dụng policy public đã khai báo
  |
  +-- Route bảo vệ
        |
        +-- Authentication: JWT hoặc opaque token
        |     |
        |     +-- Token xác minh được ----> Authentication đáng tin
        |     +-- Invalid / không xác minh được ---> KHÔNG cấp quyền
        |
        +-- Authorization: local rule và/hoặc PDP
              |
              +-- Quyết định permit hợp lệ ---> Được phép tiếp tục
              +-- Deny / lỗi / không có kết quả ---> KHÔNG cấp quyền
```

Một JWT hợp lệ chỉ chứng minh token được cấp theo quy tắc xác thực đang áp dụng; nó **không tự động cho phép** tạo đơn, xóa bản ghi, đọc tài nguyên tenant khác hoặc thực thi giao dịch. Ngược lại, lỗi của PDP không khiến token đột nhiên thành “invalid”. Hai giai đoạn nên có mã lỗi và telemetry riêng.

| Tình huống | Kết luận bảo mật | HTTP thường dùng |
| --- | --- | --- |
| Không có token, token sai chữ ký, hết hạn, sai issuer/audience; introspection trả `active=false` | Chưa xác thực hợp lệ | `401 Unauthorized` |
| Có Authentication nhưng thiếu scope/role hoặc PDP trả deny | Không đủ quyền | `403 Forbidden` |
| Không thể lấy khóa cần thiết; introspection timeout; PDP mất kết nối | **Không đủ bằng chứng để cấp quyền** | Có thể chủ động thiết kế `503 Service Unavailable`; mặc định framework/cách bắt lỗi có thể trả mã khác |
| Request thuộc route công khai được chấp thuận trước | Không cần xác thực theo chính sách của route đó | Xử lý thông thường |

Đừng tuyên bố Spring Security mặc định tự chuyển mọi lỗi mạng thành 503. Status phụ thuộc exception, bộ lọc, cấu hình entry point/denied handler/gateway và phiên bản framework. **Không bao giờ xử lý lỗi 401/403/503 bằng cách mở quyền truy cập.**

## 3. Khi JWK Set không sẵn sàng: đánh giá khóa và token riêng biệt

### 3.1 JWKS không cần được gọi lại cho mọi JWT

Với cấu hình JWT, Spring Security dùng public key lấy từ JWK Set của IdP để xác minh chữ ký, sau đó kiểm tra các yêu cầu về `iss`, `exp`, `nbf`, `aud` và thuật toán theo cấu hình. Các scope thường được ánh xạ thành authority `SCOPE_...`.

Khi JWKS offline:

1. **JWT ký bằng key K1 đã cache, K1 còn đáng tin**: vẫn có thể xác minh cục bộ chữ ký và claim. Chỉ tiếp tục khi đầy đủ ràng buộc token và authorization đều đạt.
2. **JWT có `kid=K2` chưa xuất hiện trong cache**: không thể chứng minh chữ ký bằng khóa tin cậy, vì vậy từ chối; ghi nhận lỗi tải JWKS hoặc cache miss.
3. **JWT dùng K1 nhưng signature sai / hết hạn / sai audience**: từ chối dù cache còn key.
4. **Cache không có khóa nào hoặc chỉ còn khóa bị thu hồi**: không xác thực token chỉ vì dịch vụ khóa đang tắt.

**Phải phân biệt “JWKS không có mặt” với “public key phù hợp vẫn hiện diện trong cache hợp lệ”.** Cache JWKS có cơ chế TTL, refresh, rotation và thu hồi theo triển khai; không được tự chọn “stale forever” để bảo toàn availability, vì một public key đã bị thu hồi có thể tiếp tục được tin cậy. Không có một TTL an toàn duy nhất cho mọi hệ thống.

### 3.2 Cấu hình JWT Resource Server cho WebFlux

Cần `spring-boot-starter-webflux` và `spring-boot-starter-oauth2-resource-server`. Ví dụ file **`application-jwt.yml`** (chọn profile JWT khi chạy, URL là giả định):

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.com/realms/demo
          jwk-set-uri: https://idp.example.com/realms/demo/jwks.json
          audiences:
            - payments-api
```

`issuer-uri` giữ việc xác minh `iss`, `jwk-set-uri` chỉ định endpoint key set để không phải discover địa chỉ JWKS từ metadata lúc khởi động. Cấu hình auto của Spring Security reactive có cơ chế khởi tạo/discovery trì hoãn trong những trường hợp thích hợp; nếu tự tạo `ReactiveJwtDecoder`, phải kiểm tra việc tạo bean có gây gọi mạng ngay ở startup hay không. **Ứng dụng start thành công không đồng nghĩa request JWT đầu tiên sẽ thành công khi JWKS lỗi.**

Không bao giờ:

- Chấp nhận JWT khi chưa verify signature, hoặc tin thuật toán tùy ý như `alg=none`.
- Tin URL `jku` do header token không tin cậy chỉ định, thay cho JWK URI từ cấu hình tin cậy.
- Bỏ kiểm tra `iss`, `aud`, thời hạn token hoặc key rotation chỉ để giảm lỗi.
- Đưa token/secret/private key vào log khi chẩn đoán sự cố.
- Đọc token như dữ liệu đã được xác thực chỉ vì có thể parse Base64 payload của nó.

Nếu JWT cần bị thu hồi gần thời gian thực, hãy thiết kế cơ chế revocation phù hợp từ đầu (ví dụ introspection, token lifetime ngắn hoặc cơ chế thu hồi được quản lý); **chỉ có JWT signature hợp lệ không cho biết token có vừa bị thu hồi ở IdP hay không**.

### 3.3 Key rotation trong lúc sự cố

Ví dụ: IdP chuyển từ K1 sang K2. Request mang token K1 còn hạn có thể được xử lý bằng K1 đã cache nếu chính sách cho phép. Request mang token K2 phải từ chối khi chưa tải được K2; sau khi endpoint JWKS phục hồi, decoder cần làm mới key set và thử lại trong request mới. Kiểm tra cả trường hợp K1 bị thu hồi khẩn cấp và cửa sổ stale-cache được cho phép. Không “đoán” khóa từ token hoặc bỏ verification.

## 4. Introspection không sẵn sàng: “unknown” không phải “active”

Opaque access token thông thường phải được Resource Server xác nhận qua `ReactiveOpaqueTokenIntrospector` và endpoint introspection. Khi phản hồi hợp lệ có `active=true`, có thể dựng `Authentication` và authority từ thuộc tính đã xác nhận. Nếu phản hồi `active=false`, token không còn hiệu lực.

Ví dụ **`application-opaque.yml`**, chỉ dùng khi hệ thống chọn phương thức introspection (tách khỏi cấu hình JWT phía trên):

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://idp.example.com/oauth2/introspect
          client-id: "REPLACE_WITH_RUNTIME_CLIENT_ID"
          client-secret: "REPLACE_WITH_SECRET_MANAGER_VALUE"
```

Hai giá trị trên **chỉ là placeholder**; tuyệt đối không đặt client-secret thật trong source control. Ở production dùng biến môi trường/secret manager và cơ chế cung cấp credential được phê duyệt. HTTPS phải kiểm chứng chứng chỉ và hostname của IdP.

| Phản hồi introspection | Diễn giải | Xử lý |
| --- | --- | --- |
| `active=true`, schema và các thuộc tính cần thiết hợp lệ | Đã xác minh token | Có thể chuyển tiếp sang authorization |
| `active=false` | Không hợp lệ / có thể đã thu hồi | Từ chối authentication, thường 401 |
| HTTP 401/403 từ introspection endpoint | Có thể credential của **resource server** gửi tới IdP bị sai | Từ chối, báo lỗi vận hành; không mặc định là credential người dùng sai |
| Timeout/DNS/TLS/HTTP 429 hoặc 5xx | Không biết token còn hoạt động không | Từ chối, phân loại `dependency_unavailable` |
| HTTP 200 nhưng JSON thiếu `active`, trống hoặc sai schema | Phản hồi không cung cấp bằng chứng hợp lệ | Từ chối và ghi lỗi giao thức |

Mã minh họa cách **giới hạn thời gian xử lý** khi dự án đã có một `ReactiveOpaqueTokenIntrospector` tin cậy:

```java
import java.time.Duration;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;

// Đây là method minh họa, chưa phải class Java chạy độc lập.
ReactiveOpaqueTokenIntrospector withDeadline(
        ReactiveOpaqueTokenIntrospector delegate) {
    return token -> delegate.introspect(token)
            .timeout(Duration.ofMillis(500));
}
```

Hàm wrapper chỉ trả principal nếu introspector gốc hoàn thành xác thực thành công. Timeout tạo lỗi, **không được** biến thành `OAuth2AuthenticatedPrincipal` mặc định. Hãy đặt cả connect/response timeout thích hợp cho HTTP client, không dựa duy nhất vào `Mono.timeout`; 500 ms chỉ là ví dụ và phải theo SLO thực tế.

Cảnh báo về cache: **positive introspection cache** có thể giữ token `active=true` sau khi token bị revoke hoặc quyền thay đổi. Chỉ cache nếu tài liệu thiết kế cho phép revocation lag, có TTL hữu hạn gắn với thời hạn token, khóa cache đủ ngữ cảnh và kế hoạch invalidation. Nếu yêu cầu xác nhận active gần thời gian thực, **không dùng kết quả cũ làm fallback khi IdP down**.

## 5. PDP (dịch vụ phân quyền) không sẵn sàng: không có permit thì không thực thi

Khi một endpoint dùng quyền động từ policy service bên ngoài, luồng đúng là:

1. Spring Security xác thực token và xác định danh tính đáng tin cậy.
2. API gọi PDP với **subject + action + resource + tenant/context cần thiết** qua kênh tin cậy.
3. Chỉ kết quả `permit=true` hợp lệ, gắn đúng request, mới cho phép truy cập; `permit=false` là từ chối.
4. Nếu PDP timeout/5xx, trả JSON sai/thiếu `permit`, hoặc không có quyết định, ứng dụng **không thực thi hành động**.

**Không sử dụng** quy tắc “PDP lỗi thì authenticated user nào cũng được truy cập”. Đã đăng nhập không có nghĩa có quyền đọc dữ liệu tenant khác, thực hiện giao dịch hoặc thay đổi quyền của người khác.

### 5.1 Ví dụ Spring Security WebFlux với `ReactiveAuthorizationManager`

Ví dụ Java 17+ sau là **một class cấu hình** dành cho ứng dụng Boot 3.x/Spring Security 6.x; nó không chạy độc lập. Cần có `@SpringBootApplication`, cấu hình JWT từ mục 3 và API PDP tương ứng. Tệp `src/main/java/demo/ApiSecurityConfig.java`:

```java
package demo;

import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.ReactiveAuthorizationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authorization.AuthorizationContext;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Configuration
@EnableWebFluxSecurity
public class ApiSecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http,
            ReactiveAuthorizationManager<AuthorizationContext> policyManager) {
        return http
                .authorizeExchange(exchange -> exchange
                        .pathMatchers("/healthz").permitAll()
                        .pathMatchers("/sensitive/**").access(policyManager)
                        .anyExchange().denyAll())
                .oauth2ResourceServer(oauth2 ->
                        oauth2.jwt(Customizer.withDefaults()))
                .build();
    }

    @Bean
    ReactiveAuthorizationManager<AuthorizationContext> policyManager(
            WebClient.Builder builder) {
        WebClient pdp = builder
                .baseUrl("https://pdp.internal.example")
                .build();

        return (authentication, context) -> authentication
                .flatMap(auth -> pdp.post()
                        .uri("/v1/decisions")
                        .bodyValue(new PdpRequest(
                                auth.getName(),
                                "read:sensitive",
                                context.getExchange().getRequest()
                                        .getPath().value()))
                        .retrieve()
                        .bodyToMono(PdpResponse.class)
                        .timeout(Duration.ofMillis(300))
                        .map(reply -> new AuthorizationDecision(
                                Boolean.TRUE.equals(reply.permit())))
                        .defaultIfEmpty(new AuthorizationDecision(false))
                        .onErrorReturn(new AuthorizationDecision(false)))
                .defaultIfEmpty(new AuthorizationDecision(false));
    }

    public record PdpRequest(String subject, String action, String resource) {}
    public record PdpResponse(Boolean permit) {}
}
```

Giả định hợp đồng PDP: HTTP `POST /v1/decisions` nhận JSON với `subject`, `action`, `resource`; trả JSON `{"permit":true}` hoặc `{"permit":false}`. URL và action chỉ minh họa; trong ứng dụng thật, mTLS/service credential, tenant, HTTP method, object ID, policy version và dữ liệu nghiệp vụ phải được xác thực, ràng buộc, gửi đúng ngữ cảnh, tránh mở quyền do đặt action cố định cho nhiều nghiệp vụ.

**Vì sao code fail closed:**

- `Boolean.TRUE.equals(...)` chỉ cho phép chính xác `true`; `null` hoặc `false` đều từ chối.
- `defaultIfEmpty(new AuthorizationDecision(false))` chặn phản hồi rỗng hoặc luồng authentication không có giá trị.
- `onErrorReturn(new AuthorizationDecision(false))` chặn timeout, lỗi kết nối, 4xx/5xx và lỗi parse JSON; nó **không cho phép** fallback sang granted.
- `anyExchange().denyAll()` mặc định từ chối mọi route chưa được khai báo. `/healthz` là ví dụ một route public có chủ đích; ứng dụng cần tự định nghĩa endpoint.
- `WebClient`/`Mono` giữ luồng reactive và không gọi `.block()` trên event loop.

Ở demo, một request đã được xác thực nhưng PDP lỗi sẽ thường bị **403** vì nhận `AuthorizationDecision(false)`. Điều này **không có nghĩa** lỗi PDP là “user thiếu quyền”: phải ghi metric/log kỹ thuật riêng. Nếu sản phẩm cần trả 503 để chỉ sự cố phụ thuộc, thiết kế lỗi và HTTP response riêng ở tầng phù hợp, kiểm thử chặt để đảm bảo **không có đường xử lý nghiệp vụ** trước khi phát response. Không biến deny thành allow chỉ để đổi mã HTTP.

Nếu Resource Server chọn opaque token thay JWT, cấu hình SecurityWebFilterChain tương ứng là:

```java
// Thay nhánh oauth2ResourceServer(...jwt...) trong ví dụ trên:
.oauth2ResourceServer(oauth2 ->
        oauth2.opaqueToken(Customizer.withDefaults()))
```

Và sử dụng cấu hình `opaquetoken` từ mục 4. Không giả định khi có cả `jwt` và `opaquetoken` trong YAML, Spring tự chọn chính sách phù hợp; phải thiết kế đường xác thực rõ ràng.

### 5.2 Điều cần bổ sung khi dùng PDP thực

- **Bảo vệ liên lạc API–PDP**: HTTPS/mTLS, service identity, xác minh endpoint, không tin endpoint URL do request người dùng cung cấp.
- **Ràng buộc dữ liệu policy**: authority, tenant, resource, action, chủ thể và phiên bản policy phải tương ứng request; không tái dùng kết quả permit từ request khác.
- **Chống replay hoặc nhầm response** nếu giao thức PDP yêu cầu: correlation/nonce và kiểm tra hợp đồng.
- **Cấp quyền ở điểm phù hợp**: nếu policy phụ thuộc dữ liệu trong database, tránh time-of-check/time-of-use và bảo vệ thao tác nhạy cảm ở service/repository cần thiết.
- **Telemetry**: thêm metric và log phân biệt PDP deny thật với PDP unavailable; không log bearer token, client-secret hoặc toàn bộ response có dữ liệu cá nhân.
- **CSRF riêng cho thao tác ghi**: ví dụ `/sensitive/**` có thể được gọi GET; nếu có POST/PUT và ứng dụng dùng cookie/session browser, vẫn phải xử lý CSRF theo cơ chế xác thực. Không tắt CSRF toàn ứng dụng chỉ để thử PDP.

## 6. Timeout, retry, circuit breaker, bulkhead và cache

### 6.1 Reactive không đồng nghĩa tự có timeout an toàn

Dùng `WebClient` và operator `Mono.timeout(...)` hoặc cấu hình HTTP client để chặn lời gọi phụ thuộc kéo dài vô hạn. Giới hạn cả thời gian connect, TLS, response và pool; chọn deadline theo SLO toàn tuyến. Ví dụ 300/500 ms trong bài chỉ để thể hiện cú pháp, không phải giá trị chuẩn cho mọi hạ tầng.

Retry phải có **ngân sách tổng**, giới hạn số lần, backoff/jitter và phân loại lỗi: có thể retry một số timeout/429/5xx nếu hợp đồng endpoint cho phép; **không retry** JWT sai chữ ký, `active=false`, policy `deny` hoặc credential sai. Một POST tới PDP/introspection chỉ retry khi hành vi thực sự idempotent hoặc nhà cung cấp xác nhận an toàn. Tránh nhiều tầng gateway/client/API/IdP cùng retry làm bùng lưu lượng trong sự cố.

Circuit breaker **open** nên giúp hệ thống giảm tải bằng cách từ chối các request phụ thuộc; tuyệt đối không chuyển open → permit. Bulkhead/concurrency limit giúp một PDP chậm không làm nghẽn toàn bộ Reactor event loop. Không gọi blocking SDK hoặc `Thread.sleep()` trong event loop; nếu phụ thuộc là blocking, dùng scheduler chuyên biệt có giới hạn và kiểm thử tải.

### 6.2 Không gộp mọi cache thành một

| Cache | Có thể duy trì gì khi dependency lỗi? | Rủi ro chính |
| --- | --- | --- |
| **JWKS cache** | Khả năng xác minh chữ ký cho token dùng key tin cậy đã biết | Key rotation/thu hồi, TTL quá dài |
| **Positive introspection cache** | Tạm chấp nhận trạng thái active đã xác nhận trước đó, chỉ khi chính sách cho phép | Token đã bị revoke, quyền đổi trước khi TTL hết |
| **PDP permit cache** | Tạm tái dùng quyết định cùng subject/action/resource, chỉ theo hợp đồng đã phê duyệt | Quyền cũ, tenant lẫn nhau, resource đã đổi, cache key thiếu ngữ cảnh |
| **PDP deny cache** | Có thể giảm tải khi quyền chưa thay đổi | Từ chối người dùng đã được cấp quyền hợp lệ sau đó |

Không dùng `last known permit` vô thời hạn, không dùng cache token thiếu giới hạn tuổi, không lấy response permit cho resource A để cấp cho B. Nếu cần availability đặc biệt, phải có thiết kế rủi ro/TTL/invalidation được duyệt; fail-open mặc định là lỗ hổng.

## 7. Các anti-pattern cần loại bỏ

**Sai: outage được diễn giải thành cho phép.**

```java
// Minh họa nguy hiểm: requestPermissionFromPdp trả Mono<Boolean>
return requestPermissionFromPdp()
        .onErrorReturn(true);
```

**Đúng về quyết định truy cập: chỉ PDP hợp lệ mới cấp quyền.**

```java
// Minh họa phương thức, không chạy độc lập
return requestPermissionFromPdp()
        .timeout(java.time.Duration.ofMillis(300))
        .onErrorReturn(false)
        .defaultIfEmpty(false);
```

Để vận hành tốt hơn, kết hợp fail-closed với việc ghi nhận lỗi riêng (timeout/5xx/parse/denied), không gộp hết thành “user không có quyền” trên dashboard.

Các lỗi khác:

- Tắt xác thực JWT/CSRF hoặc dùng `anyExchange().permitAll()` trong production khi IdP đang lỗi.
- Thấy JWT parse được thì chấp nhận dù không có khóa verify đáng tin.
- Khi introspection lỗi, dựng một principal giả có role mặc định hoặc coi token chưa bị từ chối là active.
- Cho rằng JWK cache còn K1 thì mọi JWT mang `kid` bất kỳ đều hợp lệ.
- Log bearer token, JWT đầy đủ, introspection secret hoặc nguyên policy payload để debug.
- Cache toàn bộ response PDP không phân biệt subject, tenant, action, resource và phiên bản policy.
- Retry vô hạn, block event loop, hoặc tăng timeout đến mức request treo lâu không có deadline.
- Bỏ qua kiểm tra quyền tại service nội bộ chỉ vì gateway đã từng xác thực request.

## 8. Kiểm thử hỏng dịch vụ và tính bất biến bảo mật

Dùng stub/mocked IdP, JWKS và PDP, chặn mạng hoặc inject latency. Các kỳ vọng bên dưới phải được kiểm chứng ở **HTTP response, metrics và side effects**, không chỉ unit test lớp policy.

| Điều kiện kiểm thử | Kỳ vọng |
| --- | --- |
| JWT ký K1 hợp lệ, cache có K1, sau đó JWKS offline | Có thể xác thực nếu cache/key còn tin cậy, tất cả claim/permission vẫn được kiểm tra |
| JWT dùng K2 chưa cache, JWKS offline | Không xác thực, không thực thi nghiệp vụ |
| JWT signature sai, hết hạn hoặc sai issuer/audience | Không xác thực dù JWKS online |
| Introspection trả `active=false` | Không xác thực, thường 401 |
| Introspection timeout/429/5xx, TLS lỗi, JSON thiếu `active` | Không xác thực; ghi dependency error, không fake active |
| PDP `permit=true` đúng ngữ cảnh | Chỉ request khớp policy được thực thi |
| PDP `permit=false` | Không thực thi nghiệp vụ, thường 403 |
| PDP timeout/500/204/JSON thiếu permit | Không thực thi, có metric outage và mã HTTP theo hợp đồng |
| PDP trả permit của subject/resource khác | Không coi là permit hợp lệ |
| Dependency hồi phục, key đổi, policy đổi | Chỉ token và quyết định hiện hành có hiệu lực; không để lại bypass |
| Stress test khi PDP/IdP chậm | Deadline, giới hạn retry, breaker/bulkhead bảo vệ tài nguyên |
| Endpoint public đã định nghĩa | Tiếp tục đúng phạm vi public; không vô tình mở endpoint protected |

**Đặc biệt với thao tác thay đổi dữ liệu**, kiểm tra database, outbox, broker, payment gateway và downstream: không có side effect nào khi bước authentication/authorization bị từ chối. Nếu retry request nghiệp vụ, cần idempotency key riêng; retry không được lặp giao dịch.

Một kịch bản kiểm tra mang tính hợp đồng:

```text
Given:
  Token JWT được xác thực hợp lệ
  GET /sensitive/orders/42 phải hỏi PDP
  PDP không trả lời trong deadline

When:
  Gửi request vào Resource Server WebFlux

Then:
  Không trả dữ liệu bí mật hoặc thực thi thao tác yêu cầu quyền
  Có telemetry phân biệt "pdp_unavailable" với "pdp_denied"
  Không lộ Authorization header, token hoặc secret trong log
  Mã HTTP khớp chính sách đã kiểm thử (ví dụ 403 khi fallback deny)
```

Đây là test scenario, **không phải output do Spring Security tự sinh**.

## 9. Quan sát hệ thống và quy trình vận hành

Nên theo dõi:

- `jwks_fetch_failure`, `unknown_kid`, tuổi cache JWK và số token verify thất bại theo nhóm nguyên nhân; không đặt token raw làm nhãn metric.
- Introspection latency, timeout, 429, 5xx, lỗi xác thực credential của Resource Server, tỷ lệ `active=false`.
- PDP `permit/deny/unavailable`, latency, timeout, breaker open, fallback deny, số lượng request đang chờ.
- Tỷ lệ HTTP 401/403/503, phân biệt **token_invalid**, **access_denied**, **security_dependency_unavailable**.
- SLO và thời gian sự cố của từng dependency để điều chỉnh timeout/retry hợp lý.

Trong Reactor/WebFlux, một request có thể chạy trên nhiều thread, nên cần correlation ID/tracing để ghép sự kiện, không chỉ dựa thread name. Dữ liệu log cần redaction, quyền truy cập và retention chặt; không ghi JWT đầy đủ, bearer token, client-secret, mã PIN hoặc PII không cần thiết. Labels metrics nên có cardinality thấp; không gắn subject hay URL chứa ID tùy ý lên mỗi time series.

**Runbook khi sự cố:**

1. Xác định dependency và lỗi cụ thể: DNS/TLS, mạng, 429/5xx, credential, JWKS rotation, cache miss hay policy service timeout.
2. Xác nhận protected routes vẫn từ chối khi chưa có bằng chứng; kiểm tra error/metric, không bật `permitAll` để hạ số lỗi.
3. Giới hạn retry, kiểm tra breaker, pool, latency và traffic burst; giữ `liveness` độc lập nếu được thiết kế để tránh restart loop.
4. Sửa mạng, secret, issuer/JWKS endpoint, key rotation hoặc PDP; không ghi secret vào chat/log runbook.
5. Khi phục hồi, thử token đúng/sai, policy allow/deny, timeout; xác nhận cache refresh và không còn cơ chế bypass.
6. Ghi nguyên nhân, số request bị từ chối do outage, tác động người dùng và cải tiến SLO, alert, TTL, timeout, độ rộng dependency.

Readiness probe nên phản ánh khả năng phục vụ phù hợp kiến trúc nhưng cân nhắc việc **toàn bộ cluster cùng rời load balancer** khi một IdP/PDP chung mất kết nối. Liveness không nhất thiết bị fail chỉ vì IdP offline.

## 10. Checklist đưa vào production

- [ ] Mọi endpoint nhạy cảm đều yêu cầu xác thực và authorization; route public chỉ có khi thiết kế cho phép.
- [ ] JWT kiểm tra chữ ký, nguồn khóa, `iss`, `aud`, `exp/nbf`; JWKS cache/rotation/thu hồi có chính sách.
- [ ] Opaque token chỉ thành authenticated với introspection thành công và dữ liệu hợp lệ.
- [ ] PDP chỉ cấp quyền khi có kết quả `permit=true` gắn đúng subject/action/resource.
- [ ] Timeout, retry, circuit breaker và HTTP client được giới hạn; outage không bao giờ biến thành allow.
- [ ] Cache permit/active, nếu có, có TTL, cache key và revocation SLA được phê duyệt.
- [ ] Mã 401/403/503 được kiểm thử trên đúng cấu hình; telemetry phân biệt invalid/deny/outage.
- [ ] Không có side effects khi authorization chưa đạt; retry nghiệp vụ có idempotency.
- [ ] Secret và token không xuất hiện trong response/log/metrics; kết nối IdP/PDP được bảo vệ.
- [ ] Có bài thử fault injection, alert/dashboard và runbook phục hồi.

## Tài liệu chính thức

- Spring Security — Reactive Resource Server JWT: https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html
- Spring Security — Reactive Resource Server Opaque Token: https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html
- Spring Security — Authorize ServerHttpRequest: https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html
- Spring Security — OAuth2 Resource Server trên WebFlux: https://docs.spring.io/spring-security/reference/reactive/oauth2/index.html
- Spring Boot 3.3 — Spring Security Resource Server configuration: https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html
- Reactor — Handling Errors: https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html
