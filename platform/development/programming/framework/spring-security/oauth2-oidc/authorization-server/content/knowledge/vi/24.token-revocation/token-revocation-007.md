# Giới hạn thu hồi tức thời đối với JWT được Resource Server xác minh cục bộ

## 1. Vấn đề cốt lõi: JWT hợp lệ về mặt mật mã chưa chắc còn được phép sử dụng

Trong hệ thống **OAuth 2.0/OpenID Connect Authorization Server** xây dựng bằng **Spring Security, Spring Authorization Server và Spring Boot**, Authorization Server (AS) có thể phát **JWT access token** đã ký. Resource Server (RS) chỉ cần lấy public key từ JWKS, kiểm tra chữ ký và các claim như `iss`, `aud`, `exp`, `nbf`, `scope` để cho phép hoặc từ chối request.

Cách xác minh **cục bộ (offline validation)** có lợi: ít request tới AS, giảm độ trễ, dễ mở rộng nhiều API. Tuy nhiên, khi AS thu hồi một access token qua Revocation Endpoint hoặc quản trị viên khóa tài khoản, JWT đã phát **không đổi nội dung hoặc chữ ký**, và Resource Server offline **không tự biết** trạng thái mới đó.

Ví dụ:

- 09:00: AS phát JWT access token có `exp` lúc 09:15.
- 09:03: user đăng xuất và client gọi `POST /oauth2/revoke` để thu hồi token.
- 09:07: người giữ bản sao JWT cũ gửi request tới RS, vốn chỉ kiểm tra chữ ký, `iss`, `aud` và `exp`.
- Nếu không có lớp kiểm tra trạng thái thu hồi bổ sung, RS **có thể vẫn chấp nhận JWT** cho đến khi token hết hạn, tùy clock skew và các điều kiện authorization khác.

Đây **không phải lỗi của JWT signature**. Chữ ký chứng minh token không bị sửa và do khóa hợp lệ ký; nó không chứa thông tin động về quyết định thu hồi tại AS sau thời điểm phát hành.

Trong module **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER**, mục tiêu là học cách thiết kế, cấu hình, bảo mật, kiểm thử và vận hành OAuth 2.0/OpenID Connect Authorization Server bằng Spring Security và Spring Authorization Server trong ứng dụng Spring Boot. Bài thuộc chương **Revocation**, tập trung vào **giới hạn thu hồi tức thời khi Resource Server xác minh JWT cục bộ** và cách chọn chính sách tương ứng với yêu cầu an toàn.

### Kết quả học tập

Sau bài học, bạn có thể:

1. Phân biệt **token revocation tại AS**, **JWT offline validation tại RS**, **token introspection** và **logout/session invalidation**.
2. Giải thích vì sao HTTP 200 từ Revocation Endpoint **không có nghĩa** mọi RS đã chặn JWT ngay.
3. Đánh giá giới hạn của access token TTL ngắn, denylist theo `jti`, introspection, authorization version và push-event invalidation.
4. Thiết kế mô hình hybrid giữ JWT signature validation nhưng kiểm tra trạng thái thu hồi ở API khi cần.
5. Cấu hình mẫu Spring Security 6.x và Spring Authorization Server 1.5.x, tránh vô hiệu hóa kiểm tra chữ ký, issuer, audience và thời hạn.
6. Định nghĩa thời gian thu hồi mục tiêu, quan sát propagation/cache delay và viết test cho nhiều RS instances.

**Phạm vi ví dụ:** Spring Boot 3.x, Spring Security 6.x và Spring Authorization Server 1.5.x trên Servlet stack. Các phiên bản mới hơn có thể khác API; trước khi đưa code mẫu vào production, đối chiếu dependency, API và chính sách bảo mật thực tế.

## 2. Hai nguồn sự thật khác nhau

### 2.1. JWT là ảnh chụp quyền tại thời điểm phát hành

JWT access token có thể mang:

```json
{
  "iss": "https://auth.example.com",
  "sub": "user-184",
  "aud": ["orders-api"],
  "iat": 1794820200,
  "exp": 1794821100,
  "jti": "at-9f2b7c32",
  "scope": "orders.read"
}
```

Giá trị minh họa trên không phải token thật. Một RS cục bộ có thể xác minh:

| Kiểm tra | Nguồn dữ liệu | Có phát hiện revocation xảy ra sau khi token phát hành? |
| --- | --- | --- |
| Chữ ký JWT | Public JWK/JWKS đã biết | **Không** |
| `iss` (issuer) | Claim JWT + cấu hình trusted issuer | **Không** |
| `aud` (audience) | Claim JWT + audience API | **Không** |
| `exp`/`nbf` | Claim JWT + đồng hồ RS | **Không**; chỉ kiểm tra hạn dùng theo thời gian |
| `scope`/roles | Claims đã ký + policy RS | **Không**; role/scope có thể lỗi thời |
| `jti` chưa bị thu hồi | Denylist hoặc trạng thái bên ngoài JWT | **Có, nếu RS thực sự tra cứu nguồn cập nhật** |
| Introspection `active` | AS/token state hiện tại | **Có, theo độ mới của AS và cache** |

Điểm quyết định là **RS có hỏi hoặc đồng bộ trạng thái mới ở đâu khác ngoài JWT hay không**. Chỉ có chữ ký, thời hạn và claims bất biến thì không thể biết một lệnh thu hồi mới xảy ra.

### 2.2. Authorization Server giữ trạng thái authorization/token

Spring Authorization Server dùng `OAuth2AuthorizationService` để lưu và tra cứu `OAuth2Authorization`, bao gồm authorization grant, token metadata và trạng thái token. Khi revocation được xử lý, state tại AS được cập nhật theo implementation/policy.

Hai implementation thường gặp:

- `InMemoryOAuth2AuthorizationService`: phù hợp development hoặc test; state không được chia sẻ bền vững giữa các node theo mặc định.
- `JdbcOAuth2AuthorizationService`: lưu authorization trong database; phù hợp hơn để nhiều AS instances truy cập cùng state khi được thiết kế giao dịch, index và vận hành đúng.

Lưu ý: **database lưu revoked token không tự động tham gia vào quá trình xác minh JWT cục bộ ở RS**. RS phải dùng introspection, shared denylist, event stream hoặc một cơ chế kiểm tra state khác nếu muốn thay đổi quyết định trước `exp`.

## 3. Sơ đồ: điều gì xảy ra khi revoke JWT?

```mermaid
sequenceDiagram
    autonumber
    participant Client as OAuth Client
    participant AS as Authorization Server
    participant State as OAuth2AuthorizationService
    participant RS as Resource Server (JWT offline)
    Client->>AS: POST /oauth2/token (grant hợp lệ)
    AS->>State: Lưu authorization/token state
    AS-->>Client: JWT access token (exp 09:15)
    Client->>RS: GET /orders + Bearer JWT
    RS->>RS: Xác minh chữ ký + iss/aud/exp/scope
    RS-->>Client: 200
    Client->>AS: POST /oauth2/revoke (09:03)
    AS->>State: Đánh dấu token bị thu hồi
    AS-->>Client: 200 OK
    Note over AS,RS: Không có một thông điệp thu hồi tự động được gửi tới RS offline
    Client->>RS: Gửi lại JWT cũ (09:07)
    RS->>RS: Chữ ký và exp vẫn hợp lệ
    RS-->>Client: Có thể vẫn 200 nếu không kiểm tra state ngoài JWT
```

**Hai sự kiện không đồng nghĩa**:

- **AS revoke thành công:** AS không còn coi token này hợp lệ theo revocation state và policy.
- **RS lập tức từ chối:** chỉ xảy ra khi RS đã quan sát trạng thái thu hồi hoặc khi token hết hạn/không còn đáp ứng policy khác.

Một quy trình đăng xuất hoàn chỉnh phải xét cả token state, phiên trình duyệt/BFF và việc RS xác minh token ra sao.

## 4. RFC 7009 quy định những gì?

**RFC 7009 — OAuth 2.0 Token Revocation** định nghĩa Revocation Endpoint để client yêu cầu AS vô hiệu hóa token không còn cần sử dụng.

### 4.1. Request và response của endpoint

Client gửi HTTP POST, thông thường với `application/x-www-form-urlencoded`, xác thực client phù hợp và tham số:

```http
POST /oauth2/revoke HTTP/1.1
Host: auth.example.com
Authorization: Basic BASE64_CLIENT_CREDENTIALS_PLACEHOLDER
Content-Type: application/x-www-form-urlencoded

token=TOKEN_PLACEHOLDER&token_type_hint=access_token
```

- `token`: bắt buộc, giá trị token muốn thu hồi.
- `token_type_hint`: tùy chọn, ví dụ `access_token` hoặc `refresh_token`; chỉ là gợi ý để server tra cứu, không phải bằng chứng token thuộc loại đó.
- Endpoint phải được bảo vệ bằng HTTPS/TLS và client authentication/authorization phù hợp. Không ghi raw token, Authorization header hoặc request form body vào log.

**Kết quả thành công:**

```http
HTTP/1.1 200 OK
Cache-Control: no-store
Pragma: no-cache
```

Theo RFC 7009, server trả **HTTP 200** cả khi token đã được thu hồi thành công **lẫn khi client gửi token không hợp lệ**. Đây là chủ ý tránh biến endpoint thành công cụ dò token; response body không mang bằng chứng về sự tồn tại hoặc mức độ lan truyền của token. Một lỗi như `invalid_client` vẫn có thể phát sinh nếu client authentication thất bại; đừng hiểu rằng mọi request đều bắt buộc trả 200.

### 4.2. Thu hồi access token và refresh token

RFC 7009 yêu cầu implementation hỗ trợ thu hồi **refresh token** và khuyến nghị hỗ trợ thu hồi **access token**. Việc cascade token liên quan phụ thuộc chính sách:

| Hành động | Hệ quả kỳ vọng | Không nên suy luận |
| --- | --- | --- |
| Revoke refresh token | AS không được dùng refresh token đó để phát token mới | JWT access token đã phát trước đó tự biến mất khỏi tất cả RS |
| Revoke access token | AS ghi nhận token bị thu hồi theo implementation/policy | Mọi JWT offline RS sẽ gọi lại AS để xác minh |
| Revoke refresh token và AS hỗ trợ access token revocation | RFC khuyến nghị AS cũng vô hiệu các access token thuộc cùng grant | Mọi AS/RS hiện thực hóa cascade giống nhau |
| Revoke access token | AS có thể revoke refresh token cùng grant theo policy | Cascade là hành vi bắt buộc và không cần test |

Một HTTP 200 chỉ có ý nghĩa về protocol handling; client và RS **không** được coi đó là bằng chứng rằng tất cả token liên quan đã hết khả năng truy cập trong mọi nơi.

### 4.3. “Immediately invalidated” có nghĩa gì trong hệ phân tán?

RFC 7009 mô tả token bị vô hiệu khi AS xử lý revocation, nhưng cũng lưu ý **propagation delay** giữa những thành phần biết trạng thái thu hồi. Với token tự chứa và RS kiểm tra offline, AS không thể buộc một RS đọc lại state chỉ thông qua việc thay đổi database.

Vì thế cần phân biệt:

1. **Tính hiệu lực theo chính sách của AS:** token bị đánh dấu không còn active.
2. **Thời điểm RS nhận biết:** phụ thuộc introspection, cache, event hoặc TTL.
3. **Request đang xử lý:** request đã được RS xác thực và bắt đầu xử lý trước revoke có thể kết thúc sau revoke, nếu hệ thống không thiết kế cơ chế ngắt/kiểm tra lại.

Không thể tuyên bố “mọi API ngừng chấp nhận token tại đúng thời điểm nhấn logout” nếu không có thiết kế đồng bộ và các giả định mạnh về mạng, cache và in-flight requests.

## 5. Vì sao xác minh JWT cục bộ không nhận biết revocation?

### 5.1. Resource Server xác minh gì?

Luồng JWT thường có:

```mermaid
flowchart TD
    A["HTTP Authorization: Bearer JWT"] --> B["BearerTokenAuthenticationFilter"]
    B --> C["JwtAuthenticationProvider / JwtDecoder"]
    C --> D{"Chữ ký hợp lệ với JWK?"}
    D -->|"Không"| X["401 invalid_token"]
    D -->|"Có"| E{"Issuer, audience, nbf, exp hợp lệ?"}
    E -->|"Không"| X
    E -->|"Có"| F{"Scope/role/policy API hợp lệ?"}
    F -->|"Không"| Y["403 forbidden"]
    F -->|"Có"| G["Cho phép xử lý request"]
    Note["Không có bước tra cứu revocation nếu chưa cấu hình"] -.-> C
```

JWT vốn là dữ liệu đã ký và **bất biến**. AS có thể sửa record `OAuth2Authorization`, nhưng RS không tự động thực hiện `OAuth2AuthorizationService.findByToken(...)` hoặc gọi endpoint thu hồi khi giải mã.

JWKS cũng không phải cơ sở dữ liệu token. Nó cung cấp public keys để kiểm tra chữ ký; không chứa danh sách access token đã bị revoke.

### 5.2. Cửa sổ rủi ro khi không kiểm tra state

Giả sử token còn thời gian `T_remaining` tại thời điểm revoke. Với RS chỉ kiểm tra JWT và không có check trạng thái:

```text
Khoảng còn có thể được chấp nhận xấp xỉ =
  max(0, thời điểm hết hạn JWT - thời điểm revoke)
  + dung sai thời gian/độ lệch clock của RS (nếu có).
```

Nếu JWT còn 12 phút và RS không dùng cơ chế revocation bổ sung, attacker nắm token vẫn có **cửa sổ truy cập có thể kéo dài gần 12 phút**, thậm chí thêm clock tolerance. Đây là **giới hạn bảo mật của kiến trúc offline**, không phải một cấu hình Spring có thể bật để tự động cập nhật token đã ký.

Tài liệu nên diễn đạt “RS vẫn có thể chấp nhận JWT” thay vì “RS chắc chắn sẽ cho qua”: token còn có thể bị từ chối do audience, scope, IP policy, resource ownership hoặc các kiểm tra khác.

### 5.3. Logout, revoke và thu hồi phiên không giống nhau

| Sự kiện | Thay đổi trực tiếp | Tác động tới JWT access token tại RS offline |
| --- | --- | --- |
| User logout khỏi web app/BFF | Xóa local session/cookie hoặc browser session | Không tự làm JWT access token mất hiệu lực |
| OIDC RP-Initiated Logout | Kết thúc phiên đăng nhập ở OP theo cơ chế OIDC | Không đồng nghĩa mọi access token JWT bị từ chối |
| Revoke refresh token | Chặn khả năng refresh từ token đó | JWT access token cũ có thể còn hiệu lực |
| Revoke access token tại AS | Cập nhật trạng thái token của AS | RS offline không tự thấy thay đổi |
| Disable user/tenant | Cập nhật user/tenant/policy state | RS offline có thể còn claims snapshot cũ |
| Xóa public JWK hoặc quay vòng khóa | Ảnh hưởng khả năng xác minh chữ ký | Có thể ảnh hưởng nhiều token cùng khóa; còn tùy cache và khóa cũ |

Trong sự cố đánh cắp token, hãy xử lý **cả refresh token và access token**, cũng như phiên ứng dụng, theo threat model và chính sách incident response.

## 6. Các kiến trúc để giảm thời gian chấp nhận JWT đã thu hồi

Không có một lựa chọn tối ưu cho mọi hệ thống. Thiết kế phải bắt đầu từ **thời gian tối đa được phép tiếp tục chấp nhận token sau khi revoke** và mức độ sẵn sàng của hệ thống kiểm tra state.

| Phương án | Cách hoạt động | Độ mới của revocation | Chi phí/điểm yếu |
| --- | --- | --- | --- |
| JWT offline + TTL ngắn | RS chỉ kiểm tra JWT, token hết hạn nhanh | Trễ tối đa gần bằng thời gian token còn hạn và clock skew | Rất nhanh, ít phụ thuộc AS; **không phải thu hồi tức thời** |
| JWT + online introspection mỗi request | RS hỏi AS/token state về `active` | Có thể phản ánh revoke khi AS đã cập nhật state; còn độ trễ mạng và in-flight requests | Tăng latency/QPS; phụ thuộc khả dụng AS |
| JWT + introspection cache | RS cache kết quả `active` | Trễ thêm thời gian cache còn hiệu lực | Giảm QPS nhưng có stale active cache |
| JWT + distributed denylist | RS kiểm tra `jti`/token hash trong shared store sau khi xác minh JWT | Phụ thuộc độ trễ cập nhật và query cache/store | Cần storage tin cậy, key/TTL nhất quán, fail-closed |
| JWT + push revocation events | AS phát sự kiện; RS cập nhật local denylist | Eventual consistency; độ trễ bus, consumer lag, restart/replay | Nhanh khi ổn định; không bảo đảm tức thời nếu có phân vùng mạng |
| JWT + authorization version | JWT chứa version; RS đối chiếu version mới nhất | Nếu RS hỏi shared state mỗi request thì kịp thời; nếu cache thì vẫn trễ | Cần thiết kế scope version và quyền thu hồi hàng loạt |
| Opaque/reference + introspection | Token là tham chiếu; RS hỏi AS để nhận state | Thường thuận tiện cho kiểm tra `active`/revoke | Đánh đổi latency, AS availability và caching |
| DPoP/mTLS-bound access token | RS yêu cầu proof sở hữu private key | Giảm khả năng dùng lại token bị đánh cắp | **Không** tự làm token hết hiệu lực sau revoke |

**Quy tắc lựa chọn nhanh:** nếu nghiệp vụ chấp nhận token tiếp tục được sử dụng một khoảng ngắn sau revoke, JWT có TTL ngắn có thể đủ. Nếu phải chặn một access token trước khi hết hạn, RS cần **một nguồn trạng thái cập nhật bổ sung**: introspection, denylist hoặc policy state check. Nếu SLA rất chặt, kiến trúc còn phải xác định cache, retry, timeout, failover và yêu cầu nhất quán của nguồn dữ liệu.

### 6.1. Phương án A — Access token ngắn hạn, refresh token được quản lý

Chọn access token TTL tương đối ngắn, ví dụ vài phút theo đánh giá rủi ro. Client dùng refresh token để xin token mới; AS có thể chặn refresh khi user logout hoặc refresh token bị revoke.

```mermaid
flowchart LR
    C["OAuth Client"] -->|"JWT AT: TTL ngắn"| RS["Resource Server offline"]
    C -->|"Refresh token khi cần"| AS["Authorization Server"]
    AS -->|"Kiểm tra refresh token state"| S[("OAuth2AuthorizationService")]
    C -.->|"Logout/revoke refresh"| AS
    AS -.->|"Chặn lần refresh tiếp theo"| C
    RS -.->|"JWT cũ còn có thể được chấp nhận tới exp"| C
```

Ưu điểm: giữ API nhanh, AS không phải xử lý introspection theo từng request. Nhược điểm: **không bảo đảm access token bị từ chối tức thời**. Sau revoke refresh token, JWT access token cũ còn trong tay attacker có thể được dùng tới hạn, dù client hợp pháp đã xóa token.

Ví dụ cấu hình `TokenSettings` cho một `RegisteredClient`:

```java
import java.time.Duration;
import org.springframework.security.oauth2.server.authorization.settings.TokenSettings;

TokenSettings tokenSettings = TokenSettings.builder()
        .accessTokenTimeToLive(Duration.ofMinutes(5))
        .refreshTokenTimeToLive(Duration.ofDays(7))
        .reuseRefreshTokens(false)
        .build();
```

Đây chỉ là ví dụ về **token policy**, không có nghĩa mọi client đều nên được phát refresh token 7 ngày. TTL và rotation phụ thuộc client type, grant, thiết bị, policy bảo mật và thiết kế detection. `reuseRefreshTokens(false)` yêu cầu phát refresh token mới trong những flow cho phép refresh, **không tự thu hồi access token JWT đã phát trước đó ở RS offline**.

**Không chọn TTL dựa trên cảm giác**: với phiên nhạy cảm, hãy định lượng cửa sổ attacker còn có thể sử dụng token; với thiết bị mạng chập chờn, cần tính cả độ trễ refresh và tải AS.

### 6.2. Phương án B — Introspection mỗi request, kể cả token format là JWT

Theo **RFC 7662**, Resource Server gọi Token Introspection Endpoint của AS để hỏi token có `active` hay không. Phản hồi có thể có:

```json
{
  "active": true,
  "scope": "orders.read",
  "client_id": "orders-web",
  "sub": "user-184",
  "exp": 1794821100
}
```

Sau khi token bị thu hồi và AS cập nhật state, phản hồi thường là:

```json
{
  "active": false
}
```

Đây là **mẫu JSON minh họa**, không phải cam kết rằng AS sẽ trả đủ claims trên hoặc cơ sở dữ liệu luôn cập nhật tức thời giữa nhiều node. Đối với token không active, AS không nên tiết lộ thông tin token nhạy cảm ngoài những gì chuẩn cho phép.

Điểm quan trọng: **JWT access token vẫn có thể được introspect**. Spring Security Resource Server có thể sử dụng cấu hình `opaqueToken` để gửi token dưới dạng chuỗi tới Introspection Endpoint, bất kể token đó thực tế có cấu trúc JWT hay opaque.

Ví dụ cấu hình Spring Boot 3.x / Spring Security 6.5:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://auth.example.com/oauth2/introspect
          client-id: orders-api-introspector
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
```

Trong Java security chain:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/actuator/health").permitAll()
            .anyRequest().hasAuthority("SCOPE_orders.read"))
        .oauth2ResourceServer(oauth -> oauth
            .opaqueToken(Customizer.withDefaults()));
    return http.build();
}
```

Tên tính năng là `opaqueToken` vì RS dùng giao thức **introspection** thay vì giải mã JWT cục bộ. Token có thể vẫn là JWT. Trong cấu hình này, **RS tin vào kết quả kiểm tra của AS**, và không mặc nhiên tự chạy chữ ký JWT/issuer/audience validator như cấu hình `jwt()`. Phải kiểm thử AS introspection thực sự xác minh token, kiểm tra trạng thái revoked, issuer, audience/resource, scope và phân quyền đúng. Cũng cần giới hạn người được phép gọi introspection và bảo vệ credentials bằng secret manager/TLS.

**Điều kiện để nhận biết revocation:** token state tại AS phải hỗ trợ việc đánh dấu token không active, RS thực sự gọi introspection với token đúng, và không có cache `active=true` kéo dài hơn mức chấp nhận. Nếu custom AS introspection không đọc revocation state, chuyển RS sang introspection vẫn chưa giải quyết bài toán.

### 6.3. Phương án C — Denylist theo jti hoặc fingerprint

Giữ JWT offline signature validation, nhưng RS thực hiện **một bước phụ** tra trạng thái thu hồi:

1. AS phát access token với `jti` duy nhất; RS hiểu quy ước `iss + jti`.
2. Khi revoke, AS xác định `jti` hoặc fingerprint token và ghi bản ghi “revoked” vào store dùng chung.
3. RS trước khi cho phép request phải kiểm tra `jti` có bị revoke không.
4. Store giữ entry ít nhất đến khi mọi RS sẽ không còn chấp nhận JWT theo `exp` và tolerance tương ứng.

```mermaid
flowchart TD
    C["Client gửi Bearer JWT"] --> RS["Resource Server"]
    RS --> SIG{"Chữ ký + iss/aud/exp hợp lệ?"}
    SIG -->|"Không"| DENY["401 invalid_token"]
    SIG -->|"Có"| KEY["Lấy issuer + jti từ token đã xác minh"]
    KEY --> STORE[("Shared revoked-jti store")]
    STORE --> REVOKED{"Có trong denylist?"}
    REVOKED -->|"Có"| DENY
    REVOKED -->|"Không"| SCOPE{"Scope + resource policy đạt?"}
    SCOPE -->|"Có"| ACCEPT["Cho phép request"]
    SCOPE -->|"Không"| FORBIDDEN["403 forbidden"]
    AS["Authorization Server"] -->|"Revoke event / atomic record"| STORE
```

**Denylist phải đáng tin cậy**:

- Cache/store dùng chung giữa mọi RS instances; dữ liệu cập nhật theo issuer/region.
- Không xóa bản ghi trước khi JWT hết hạn đối với toàn bộ RS, kể cả clock skew.
- Quy trình write phải được xác nhận bền vững trước khi tuyên bố token đã bị chặn theo SLA.
- Nếu store không truy cập được, chọn fail-closed đối với endpoint nhạy cảm; đừng tự cho phép vì “không tìm thấy entry” khi lookup bị timeout.
- Giới hạn kích thước, rate limit và key schema; không lưu raw bearer token trong log/store nếu không cần.
- Nếu `jti` không được phát hoặc không duy nhất, phải thiết kế migration/fingerprint và bảo đảm lookup không nhầm token.

Sử dụng `jti` không làm chính nó trở thành secret, nhưng nó có thể là ID tương quan; tránh in tràn lan vào metrics/log. Với token hash, dùng digest ổn định đủ mạnh của **toàn bộ raw token** hoặc một HMAC phục vụ indexing; không lưu plaintext token như một “cache key cho tiện”.

### 6.4. Phương án D — Sự kiện thu hồi (push) và local state cache

AS phát sự kiện khi token/authorization bị thu hồi; các RS instances hoặc một edge authorization service nhận sự kiện và cập nhật local cache.

Ưu điểm: độ trễ kiểm tra API thấp nếu cache local. Hạn chế: **eventual consistency**. Một RS bị mất kết nối bus có thể tiếp tục chấp nhận token cũ; sự kiện mất trong lúc deploy có thể khiến local state sai lâu dài.

Để vận hành đúng:

- Event có ID, issuer, token identifier, thời điểm revoke/expiration và version.
- Consumer xử lý idempotent, có durable replay/offset, resync sau restart.
- Theo dõi consumer lag và thời điểm RS bắt kịp high-water mark.
- Nếu yêu cầu chặn trong vài giây, định nghĩa xử lý khi RS tụt quá SLA (fail-closed hoặc fallback online lookup).
- Không phát raw access token qua message broker nếu chỉ cần hash/ID.

**Thời điểm AS phát event không phải thời điểm tất cả RS nhận event**. Không cam kết zero-delay dựa trên push event đơn thuần.

### 6.5. Phương án E — Authorization/session version

AS lưu version hoặc timestamp thay đổi quyền theo user, client hoặc authorization. JWT mang claim như `authz_version` và RS đối chiếu version hiện tại.

Ví dụ:

```json
{
  "sub": "user-184",
  "authz_version": 12,
  "aud": ["orders-api"],
  "exp": 1794821100
}
```

Khi user bị khóa hoặc revoke toàn bộ sessions, tăng version lên 13. RS đọc state hiện tại thấy token version 12 → từ chối.

**Lưu ý thiết kế:** nếu RS lấy version từ cache 60 giây, độ trễ nhận biết vẫn có thể 60 giây. Version theo user giúp thu hồi nhiều token cùng lúc nhưng có thể làm mọi thiết bị đăng xuất; version theo authorization/client/session giúp nhắm mục tiêu chính xác hơn nhưng phức tạp hơn. Không dùng một version global cho mọi tài khoản khi chỉ cần thu hồi một phiên.

### 6.6. Khi nào nên chọn opaque token?

Nếu bắt buộc kiểm soát trạng thái token theo từng request và AS/Introspection Service có thể chịu tải, **opaque/reference token** thường dễ quản trị hơn: giá trị token chỉ tham chiếu tới state ở AS. RS introspect thay vì dựa vào claims tự chứa.

Tuy nhiên:

- Introspection vẫn có thể bị cache và tạo độ trễ.
- AS outage/timeout phải có fail policy.
- Các API cần bảo đảm `active` là trạng thái thật của đúng token và client/resource.
- Opaque token không tự động che giấu rủi ro bị đánh cắp bearer token; vẫn cần TLS và scope/TTL phù hợp.
- Việc chuyển JWT → opaque ảnh hưởng API configuration, monitoring, scale và phân quyền.

## 7. Xây dựng cam kết thời gian thu hồi (revocation SLA)

### 7.1. Định nghĩa “thu hồi trong N giây” cho chính xác

Một SLA nên viết rõ:

> Sau khi sự kiện revoke được AS xác nhận ở thời điểm T0, mọi request mới bắt đầu xác thực tại RS thuộc phạm vi X phải bị từ chối chậm nhất ở T0 + N giây, trừ những trường hợp đã liệt kê trong failure model.

Không được hiểu “mọi request đang chạy bị dừng ngay lập tức” nếu API không có cơ chế ngắt transactional work hoặc kiểm tra lại ở thời điểm commit.

Một ước lượng ngân sách trễ khi dùng event/caching:

```text
T_observed_revoke =
  T_AS_commit
  + T_event_propagation
  + T_RS_consumer_lag
  + T_lookup_cache_staleness
  + T_clock_tolerance / processing effects
```

Đây là cách chia nguồn trễ **để đo đạc và đặt budget**, không phải công thức bảo đảm upper bound cứng; các trễ có thể chồng lấp, và network partition không có giới hạn hữu hạn nếu thiếu fail-safe. Với TTL-only, trễ chấp nhận JWT phụ thuộc thời hạn còn lại chứ không phụ thuộc event propagation.

### 7.2. Phân nhóm mức yêu cầu

| Mục tiêu nghiệp vụ | Thiết kế gợi ý | Điểm phải kiểm thử |
| --- | --- | --- |
| Chấp nhận trễ một vài phút | JWT TTL ngắn + revoke refresh | Cửa sổ tối đa từ revoke đến `exp`, RS clock skew |
| Chặn trước hết hạn trong khoảng chục giây | Shared denylist/introspection có cache TTL nhỏ hoặc push + fallback | Cache staleness, propagation lag, RS failure mode |
| Chặn sát thời điểm request mới | Introspection/live state check hoặc central authorization decision | AS availability, latency, race với revoke commit, in-flight requests |
| Thu hồi quyền khẩn cấp xuyên nhiều vùng | Tùy kiến trúc: central authoritative state + fail-closed + revoke propagation | Region isolation, event replay, data replication và kiểm thử chaos |

Không có “JWT offline + không gọi state + thu hồi từng token tức thời” như một tổ hợp khả thi. Muốn biết một thay đổi sau khi JWT được ký, RS phải nhận thông tin mới từ nơi khác hoặc token phải tự hết hạn.

### 7.3. Độ trễ cache là một phần của security contract

Nếu introspection trả `active=true` và RS cache 5 phút, token bị revoke ngay sau khi cache entry được tạo có thể tiếp tục được chấp nhận gần 5 phút. **Thời hạn cache kết quả introspection không được đánh đồng với access token TTL**.

Đối với hệ thống yêu cầu SLA 30 giây:

- Cache `active=true` với TTL dài hơn 30 giây thường không phù hợp nếu không có invalidation đáng tin cậy.
- Độ trễ propagation, đồng bộ nhiều node và timeout còn phải được cộng vào budget.
- Cache negative `active=false` cũng cần policy riêng để tránh tạo lỗi dai dẳng khi token state thay đổi theo cơ chế đặc biệt; thường revoked token phải được xem như terminal.
- Chọn fail-open/fail-closed theo yêu cầu bảo mật từng endpoint, ghi rõ hành vi khi AS hoặc cache bị lỗi.

### 7.4. Đừng bỏ qua requests in flight

Một request có thể vượt qua JWT validator lúc 09:02:59, rồi AS revoke lúc 09:03:00, nhưng request vẫn ghi dữ liệu lúc 09:03:05. Nếu nghiệp vụ phải bảo đảm không có thay đổi dữ liệu sau revoke, việc xác minh token đầu request là chưa đủ: cần thêm transaction-level authorization check hoặc distributed coordination ở điểm commit.

Đây là yêu cầu mạnh hơn “mọi request mới sau N giây bị từ chối”. Tránh hứa hẹn hai loại bảo đảm như nhau.

## 8. Spring Authorization Server: Revocation Endpoint và token state

### 8.1. Những thành phần tham gia

Spring Authorization Server cung cấp Revocation Endpoint theo RFC 7009. Với cấu hình mặc định, endpoint thường là `POST /oauth2/revoke`; path có thể được đổi bằng `AuthorizationServerSettings`.

| Thành phần | Trách nhiệm |
| --- | --- |
| `OAuth2TokenRevocationEndpointFilter` | Nhận request revocation thuộc SecurityFilterChain AS |
| `OAuth2TokenRevocationAuthenticationConverter` | Đọc thông tin token, token type hint và client context |
| `OAuth2TokenRevocationAuthenticationProvider` | Xử lý revocation với authenticated client và authorization/token state |
| `OAuth2AuthorizationService` | Lưu/tra cứu authorization và trạng thái token |
| `OAuth2TokenRevocationEndpointConfigurer` | Cho phép tùy biến request converter, providers, handlers |
| `OAuth2TokenIntrospectionEndpointFilter` | Xử lý introspection, là một endpoint riêng |
| `OAuth2TokenGenerator` | Tạo token khi grant hợp lệ; không phải nơi truyền thông tin revoke tới RS |

Những thành phần này điều phối thay đổi **trạng thái tại AS**. Chúng không mặc nhiên cấu hình thêm một revocation-state lookup trong `JwtDecoder` của mọi Resource Server.

### 8.2. Cấu hình AS theo mặc định

Ví dụ dưới đây minh họa thiết lập SecurityFilterChain AS cùng issuer và đường revocation:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configurers.OAuth2AuthorizationServerConfigurer;
import org.springframework.security.oauth2.server.authorization.settings.AuthorizationServerSettings;
import org.springframework.security.web.SecurityFilterChain;

@Bean
@Order(1)
SecurityFilterChain authorizationServerChain(HttpSecurity http)
        throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

    http
        .securityMatcher(authorizationServer.getEndpointsMatcher())
        .with(authorizationServer, Customizer.withDefaults())
        .authorizeHttpRequests(authorize ->
            authorize.anyRequest().authenticated());

    return http.build();
}

@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
            .issuer("https://auth.example.com")
            .tokenRevocationEndpoint("/oauth2/revoke")
            .tokenIntrospectionEndpoint("/oauth2/introspect")
            .build();
}
```

**Đây là ví dụ một phần**; ứng dụng thật còn cần signing keys, client repository, authentication/login chain, authorization services, token policy và các cấu hình flow liên quan. Đừng tự thay toàn bộ revocation provider bằng controller `@PostMapping("/oauth2/revoke")` chỉ để “đổi trạng thái” rồi bỏ qua authentication, token ownership và semantics của RFC.

### 8.3. Bảo vệ trạng thái AS trong triển khai nhiều node

Với một AS cluster:

- Dùng một backend authorization state có độ bền và nhất quán đáp ứng mục tiêu, thay vì mỗi node giữ một bộ `InMemoryOAuth2AuthorizationService` riêng.
- Kiểm tra transaction commit trước khi xem revocation đã được ghi nhận; không chỉ dựa vào việc handler đã gửi HTTP response.
- Xác minh `OAuth2TokenIntrospectionEndpointFilter` đọc cùng trạng thái mới sau revoke.
- Nếu có event/outbox, thiết kế commit và event publication để không mất revocation event khi ứng dụng crash giữa hai bước.
- Nếu revoke access token đồng thời với refresh flow, test race giữa hai operation để không phát thêm token trái policy.
- Giữ client authentication, HTTPS và log redaction tại Revocation Endpoint và Introspection Endpoint.

Trong Spring Authorization Server, việc token đã bị AS đánh dấu inactive **cần được kiểm thử thực tế qua introspection**; không giả định rằng JSON JWT còn chữ ký hợp lệ thì introspection sẽ tự trả active hoặc inactive theo cách bạn mong đợi khi sử dụng custom persistence/provider.

### 8.4. Giới hạn của việc tùy biến success handler

`OAuth2TokenRevocationEndpointConfigurer` cho phép thay response handler hoặc authentication provider. **Success handler chạy ở điểm protocol response**, không tự bảo đảm mọi RS đã thấy thay đổi. Nếu cần đồng bộ denylist/event, tích hợp vào application service xử lý revocation với transactional/outbox semantics phù hợp, rồi định nghĩa **thời điểm acknowledgment** cho SLA.

Tránh fire-and-forget revocation event rồi trả thông báo “đã ngăn token trên mọi API” khi chưa có cơ chế xác nhận downstream. Không log raw token để xây dựng event payload.

## 9. Ví dụ Spring Security: JWT validator kết hợp denylist

Mẫu dưới đây dành cho kiến trúc **JWT signature validation tại RS + kiểm tra trạng thái revoked theo jti trong shared store**. Đây là ví dụ có chủ ý phân tách storage API, không phải code có sẵn của Spring Authorization Server.

### 9.1. Giao diện tra cứu state

```java
public interface RevokedJwtLookup {

    // True khi token thuộc issuer và jti đã được đánh dấu thu hồi.
    // Implementation cần timeout rõ ràng, xử lý lỗi fail-closed
    // cho endpoint nhạy cảm và không log raw token.
    boolean isRevoked(String issuer, String jti);
}
```

Implementation có thể dùng Redis, database hoặc một dịch vụ authorization-state chuyên biệt. **Không cài mặc định** `isRevoked(...)` luôn trả `false` khi Redis timeout; như vậy tạo fail-open khó quan sát.

### 9.2. Validator kết hợp chữ ký, claims và revocation

```java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Bean
JwtDecoder jwtDecoder(RevokedJwtLookup revokedLookup) {
    String issuer = "https://auth.example.com";
    String audience = "orders-api";

    NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri("https://auth.example.com/oauth2/jwks")
            .build();

    OAuth2TokenValidator<Jwt> audienceValidator = jwt -> {
        boolean valid = jwt.getAudience() != null
                && jwt.getAudience().contains(audience);
        return valid
                ? OAuth2TokenValidatorResult.success()
                : invalid("Token không dành cho orders-api");
    };

    OAuth2TokenValidator<Jwt> revocationValidator = jwt -> {
        String jti = jwt.getId();
        if (jti == null || jti.isBlank()) {
            // Với policy yêu cầu jti bắt buộc, thiếu jti là invalid.
            return invalid("Token không có jti");
        }
        return revokedLookup.isRevoked(issuer, jti)
                ? invalid("Token đã bị thu hồi")
                : OAuth2TokenValidatorResult.success();
    };

    decoder.setJwtValidator(new DelegatingOAuth2TokenValidator<>(
            JwtValidators.createDefaultWithIssuer(issuer),
            audienceValidator,
            revocationValidator
    ));

    return decoder;
}

private static OAuth2TokenValidatorResult invalid(String description) {
    return OAuth2TokenValidatorResult.failure(
            new OAuth2Error("invalid_token", description, null));
}
```

**Cách sử dụng:** đặt các method trên trong một `@Configuration` class của Resource Server (sắp xếp access modifiers/bean wiring theo dự án). Đây là code minh họa cho policy, cần thêm imports và dependency phù hợp phiên bản trước khi chạy dự án. Decoder xác minh chữ ký bằng JWKS; validator tổng hợp tiếp tục kiểm tra các claims mặc định gồm issuer/thời gian, audience của API và state revoked. Trong ứng dụng thật còn cần algorithm constraints, scopes/authorities và resource-level authorization.

**Thứ tự bảo mật quan trọng:** chỉ tin `iss/jti` sau khi JWT đã được giải mã và xác minh chữ ký; trong ví dụ, lookup dùng issuer cố định từ cấu hình tin cậy để tạo namespace, không dùng giá trị issuer tự chọn từ input chưa được kiểm tra. Không tự viết parser base64 rồi lấy `jti` để query store và quyết định cho phép nếu chưa xác minh chữ ký.

**Lưu ý failure mode:** nếu `revokedLookup.isRevoked(...)` ném lỗi I/O, đây không phải `not revoked`. Cần chính sách fail-closed và mapping exception phù hợp (có thể trả 503 nếu hệ thống authorization-state đang lỗi); đừng nuốt exception rồi trả token hợp lệ. Tùy SLA, dùng timeout, retry có giới hạn và circuit breaker với hành vi mặc định **từ chối** cho API nhạy cảm.

### 9.3. Ghi denylist: TTL và namespace

Khi AS/Revocation Service nhận token đã xác minh:

```text
key    = "revoked:" + hash(issuer) + ":" + hash(jti)
value  = true
expiry = exp + maxResourceServerClockSkew + operationalSafetyMargin
```

Trong triển khai:

- Đặt TTL dựa trên `exp` **của chính token** và dung sai clock của mọi RS. Không đặt 10 giây tùy tiện cho JWT còn hạn 15 phút.
- Dùng token identifier ổn định và duy nhất; nếu JWT legacy thiếu `jti` thì cân nhắc hash của toàn bộ token sau khi xác thực.
- Không ghi token nguyên văn vào log, cache key hoặc audit event.
- Có kiểm thử với nhiều issuer và nhiều `jti` để tránh trùng namespace.
- Đánh dấu revoke idempotent; gọi revoke lặp lại không tạo trạng thái trái ngược.
- Không ghi `revoked=false` vì timeout/no response; chỉ cho phép khi có **negative lookup đáng tin cậy**.

**Đây không phải built-in tính năng tự bật của `JwtDecoder`**. Chính sách ghi denylist ở AS và đọc ở RS đều phải được nối vào flow thực, không chỉ thêm một validator tại RS mà quên thông báo revoke sang store.

### 9.4. Kiểm thử custom validator đúng tầng

Khi dùng `SecurityMockMvcRequestPostProcessors.jwt()` trong unit test, Spring Security Test có thể thiết lập authentication giả thay vì chạy decoder thực tế. Vì vậy test với `jwt()` **không chứng minh** custom `JwtDecoder` đã thực hiện revoked-jti lookup.

Cần ít nhất hai nhóm test:

1. **Unit test decoder/validator**: tạo JWT đã qua ký/fixture đúng phiên bản hoặc kiểm thử riêng validator, giả lập `RevokedJwtLookup` true/false/timeout; kiểm tra issuer/audience/exp.
2. **Integration test request HTTP thực**: gọi API với JWT test ký bằng key của AS test, kiểm tra RS xử lý token qua `BearerTokenAuthenticationFilter` và cấu hình decoder thật. Sau khi revoke, request mới phải trả 401 trong SLA.

Không dùng token production trong test log; không in nguyên JWT/Authorization header trong assertion failure.

## 10. Những giải pháp dễ bị hiểu nhầm là thu hồi JWT tức thời

### 10.1. Xóa hoặc xoay khóa ký JWT

Một đề xuất thường gặp là “xóa JWK cũ để token đang lưu hết hiệu lực”. Đây không phải cách thu hồi một access token người dùng thông thường:

- Nhiều JWT được ký cùng một private key. Nếu Resource Server không còn tin public key, **nhiều token hợp lệ** có thể bị từ chối cùng lúc.
- RS có thể đang cache JWKS; xóa public key khỏi JWKS endpoint **không bảo đảm** mọi RS loại bỏ khóa khỏi cache ngay.
- Rotation bình thường thường giữ public key cũ đủ lâu để các token đã ký còn hạn được xác minh; chính điều đó khiến rotation bình thường **không** giúp revoke một JWT đơn lẻ.
- Đổi key đột ngột có thể tạo downtime, tăng lỗi 401 trên hàng loạt API và làm lệch trạng thái các node.

**Key rotation là phương án quan trọng khi khóa ký bị lộ**, cần runbook khẩn cấp và khả năng ép các RS cập nhật trust store/JWK cache. Không dùng nó thay `jti` denylist/introspection để phục vụ logout của một user.

### 10.2. Xóa token khỏi database

Việc xóa một record khỏi `OAuth2AuthorizationService` có thể ngăn AS tìm thấy token và làm introspection phản ánh inactive theo implementation; nhưng JWT ở RS offline vẫn có payload và chữ ký hợp lệ. Nếu AS thay đổi state nhưng RS không đọc state đó, hành vi API không đổi cho tới `exp`.

Ngoài ra, xóa toàn bộ authorization record có thể làm mất dữ liệu audit, quản lý grant và các token liên quan. Ưu tiên quy trình revoke/invalidate đúng protocol và retention policy thay vì xóa thẳng database không có đánh giá.

### 10.3. Logout khỏi Authorization Server

Kết thúc cookie/session đăng nhập tại AS không tự làm Resource Server loại JWT access token đã phát. Cần phân biệt browser session, OAuth client session/BFF cookie, refresh token và access token. Trong OIDC, OP logout và token revocation là hai vấn đề liên quan nhưng **không thay thế lẫn nhau**.

### 10.4. Đổi role hoặc khóa tài khoản

JWT có claim `roles`, `scope` hay `tenant_id` là snapshot. Nếu RS chỉ dùng những claim đã ký và user bị gỡ role sau khi token phát hành, RS vẫn có thể sử dụng role cũ. Nếu nghiệp vụ cần quyền mới nhất:

- Rút ngắn access token TTL.
- Kiểm tra current authorization/account state.
- Dùng authorization version/epoch với lookup có kiểm soát.
- Dùng introspection hoặc policy engine tại resource-level authorization.

Không xem việc “thay đổi role trong database người dùng” như bằng chứng JWT đang lưu trong client đã được cập nhật.

### 10.5. DPoP hoặc mTLS-bound token

DPoP và certificate-bound access token hạn chế việc kẻ khác chỉ có token value sử dụng lại token khi không sở hữu khóa tương ứng. Đây là **sender constraint**, không phải cơ chế báo cho RS rằng AS đã thu hồi token. Nếu private key hoặc client runtime cũng bị chiếm, token vẫn cần revocation và freshness strategy riêng.

## 11. Chọn phương án theo threat model

### 11.1. Câu hỏi kiến trúc cần trả lời

Trước khi chọn JWT hay opaque token, nhóm thiết kế cần trả lời:

1. Sự kiện nào phải chặn ngay: user logout, mất thiết bị, tài khoản bị khóa, thay role, rút quyền tenant, client secret bị lộ?
2. Cần thu hồi **một access token**, một authorization grant, toàn bộ token của user, hay một client/service account?
3. Mức trễ chấp nhận được sau khi AS xác nhận revoke là bao lâu?
4. Có bao nhiêu RS instances, region, CDN/API gateway và cache trung gian?
5. Trong trường hợp network partition hoặc introspection service lỗi, API nên từ chối hay chấp nhận tạm?
6. Có request không idempotent/long-running cần kiểm tra lại quyền trước khi commit không?
7. Access token có `jti` duy nhất, `aud` hạn chế và `exp` hợp lý không?
8. Hệ thống có chấp nhận tải và latency của lookup mỗi request không?

### 11.2. Minh họa một quyết định

Giả sử API đọc catalog công khai chấp nhận token còn hiệu lực tối đa 5 phút sau revoke, còn API chuyển tiền bắt buộc kiểm tra trạng thái tài khoản/token gần thời điểm request:

| API | Cách kiểm soát minh họa | Vì sao |
| --- | --- | --- |
| Catalog/low-risk read | JWT TTL ngắn, offline signature verification | Tối ưu throughput; rủi ro stale authorization thấp |
| Customer profile | JWT TTL ngắn + denylist cache hoặc introspection | Dữ liệu cá nhân cần độ mới cao hơn |
| Payment approval | Online authorization-state check, policy engine và kiểm tra lại trước commit khi cần | Hậu quả thay đổi dữ liệu cao; cần rõ failure mode |
| Admin/tenant management | Introspection hoặc distributed denylist, kiểm tra tenant/status và quyền hiện tại | Role/tenant changes cần hiệu lực nhanh |

Đây là phân loại minh họa, **không phải** chuẩn yêu cầu các loại API phải dùng cùng thiết kế này. Doanh nghiệp cần threat modeling, SLA, compliance và kiểm thử tải/thất bại trước khi chốt.

### 11.3. Những phép đo cần có

Sử dụng các timestamp an toàn:

```text
T_request_revoke     = lúc AS bắt đầu xử lý revoke
T_committed          = lúc token state đã được commit
T_ack                = lúc client nhận 200
T_rs_last_accept     = lần cuối RS chấp nhận token đã revoke
T_rs_first_reject    = lần đầu RS từ chối token đó
T_event_consumed     = lúc RS xử lý event (nếu có)
```

Độ trễ thực tế có thể đo bằng `T_rs_first_reject - T_committed` với traffic kiểm thử đủ dày; nhưng nếu chỉ gửi request mỗi 10 giây, phép đo không xác định thời điểm chính xác hơn độ phân giải đó. Không lưu nguyên bearer token trong telemetry; dùng test token identifier có chính sách redaction.

Với event-based cache, cần metric consumer lag, cache age, missed event, cache read timeout, AS introspection latency, 401/403 distribution và JWT verifier failures theo issuer/audience.

## 12. Ma trận kiểm thử thu hồi JWT end-to-end

| ID | Kịch bản | Kết quả mong đợi |
| --- | --- | --- |
| R01 | JWT hợp lệ, trước khi revoke | RS cho phép nếu chữ ký, `iss`, `aud`, `exp` và scope đúng |
| R02 | Revoke access token, RS chỉ kiểm tra JWT offline | Chứng minh RS **có thể** tiếp tục chấp nhận tới `exp` nếu không có state lookup |
| R03 | Revoke refresh token | Không dùng được refresh token để xin access token mới; JWT cũ được đánh giá theo chính sách riêng |
| R04 | Revoke token không tồn tại/hết hạn | RFC 7009 success có thể là 200; không tiết lộ token tồn tại |
| R05 | Client authentication sai tại revoke endpoint | Không revocation trái phép, trả OAuth error phù hợp |
| R06 | `token_type_hint` sai | AS vẫn thực hiện lookup theo chuẩn; hint không là cơ sở tin cậy |
| R07 | Revoke JWT rồi introspection | Introspection của cùng JWT phản ánh `active=false` khi state đã cập nhật |
| R08 | JWT đúng chữ ký nhưng sai `aud` | RS từ chối dù chưa revoke |
| R09 | JWT sai issuer/chữ ký/expired | RS từ chối dù denylist báo không revoked |
| R10 | JWT bị revoke, có denylist entry | RS từ chối request mới trước `exp` |
| R11 | JWT thiếu `jti` trong hệ thống yêu cầu jti | Validator từ chối hoặc áp dụng legacy fingerprint policy đã định |
| R12 | JWT của issuer A có jti giống issuer B | Namespace không làm lẫn revocation |
| R13 | Denylist entry hết hạn trước JWT | Test phát hiện và ngăn replay token bị revoke |
| R14 | Ghi denylist idempotent | Revoke lặp lại không làm token active lại |
| R15 | RS nhiều node, cùng token revoked | Mọi node quan sát cùng trạng thái theo SLA |
| R16 | AS nhiều node, cùng token | Revocation state/introspection nhất quán theo deployment policy |
| R17 | RS bị phân vùng khỏi denylist | Hành vi fail-closed/fallback được kiểm thử, không im lặng fail-open |
| R18 | Introspection service timeout/503 | RS áp dụng failure policy; không giả định token vẫn active |
| R19 | Introspection cache `active=true` lâu | Độ trễ revoke được đo và nằm trong budget |
| R20 | Event bus consumer tạm ngừng rồi phục hồi | Replay/resync event, không mất revocation state |
| R21 | Event đến trùng hoặc đảo thứ tự | Consumer idempotent và versioning không làm token active lại |
| R22 | User logout browser | Session bị đóng; chính sách access/refresh token được kiểm thử độc lập |
| R23 | User bị gỡ role/tenant | Token cũ và authorization-state check hành xử theo SLA đã định |
| R24 | Access token TTL ngắn | RS từ chối sau `exp` kể cả khi AS không sẵn sàng |
| R25 | RS clock lệch trong giới hạn cho phép | Token expiry và denylist TTL tính đúng tolerance |
| R26 | Key rotation bình thường | JWT đã phát còn xác minh theo policy đến expiry |
| R27 | Emergency key compromise | Runbook ép cập nhật trust và phạm vi token ảnh hưởng được kiểm thử |
| R28 | Request đã pass auth trước revoke, commit sau | Hành vi in-flight request được xác định, không hứa chặn khi chưa hỗ trợ |
| R29 | Test chỉ dùng MockMvc `jwt()` | Không coi là bằng chứng `JwtDecoder`/denylist thực sự chạy |
| R30 | Test bằng signed JWT thật và HTTP filter chain | Token bị revoke bị từ chối tại RS theo đúng chính sách |
| R31 | Token trong log, trace, audit, test report | Không có raw bearer/refresh token hoặc client secret |
| R32 | Revocation Endpoint trả 503 | Client giả định token vẫn có thể tồn tại và retry theo chính sách an toàn |

### 12.1. Kiểm thử thời gian và concurrency

Để đo SLA, test nên có:

- Test token TTL đủ dài để quan sát revocation trước `exp`.
- Nhiều client/RS instances, nhiều region khi hệ thống production có multi-region.
- Đồng hồ giả hoặc đồng hồ đã đồng bộ, timestamp được thu thập nhất quán.
- Tần suất request đủ cao để đo cửa sổ chấp nhận sau revoke.
- Concurrent request với revocation và refresh để tìm race condition.
- Kịch bản AS/downstream cache/event bus mất kết nối.
- Assertions rằng tất cả RS thuộc phạm vi đều ngừng chấp nhận token trong SLA, thay vì chỉ một node.

Với JWT offline thuần túy, bài test kỳ vọng phải ghi nhận giới hạn: token còn có thể được chấp nhận khi `exp` chưa tới. **Không sửa kết quả test bằng cách chủ động chặn token trong mock rồi tuyên bố đã giải quyết production**.

### 12.2. Kiểm thử không làm lộ credential

Revocation request body chứa raw token cần thu hồi. Trong test:

- Dùng token giả do test AS cấp, không dùng production access/refresh token.
- Không in `Authorization` header hoặc form parameter `token`.
- Không chụp body request/response có bearer token vào ticket/CI artifact công khai.
- Nếu cần correlation, dùng `jti` test hoặc HMAC identifier không thể đảo ra token.
- Bảo vệ introspection client secret bằng environment secret manager.

## 13. Runbook khi phát hiện JWT bị đánh cắp

Giả sử một access token đã xuất hiện trong debug log của gateway.

### 13.1. Hành động ưu tiên

1. **Chặn nguồn lộ token:** vô hiệu capture/logging ở đúng gateway/filter/APM; giữ chứng cứ sự cố theo quy trình.
2. **Xác định phạm vi:** issuer, client, subject/authorization, audience, scope, `jti` và `exp`; không phát tán raw token trong ticket.
3. **Thu hồi credential liên quan:** revoke refresh token/authorization và access token ở AS theo chính sách; rotate client credentials nếu bị lộ.
4. **Chặn access token tại RS:** nếu RS có introspection/denylist thì đẩy state và xác nhận; nếu không, dựa vào TTL hoặc kích hoạt biện pháp khẩn cấp có đánh giá phạm vi.
5. **Kiểm tra abuse:** resource access logs đã redaction, IP/device patterns, high-risk API operations và transaction audit.
6. **Theo dõi tới khi hết hạn:** bảo đảm token không được chấp nhận ngoài dự kiến và đánh giá token khác cùng authorization.
7. **Khắc phục gốc:** bổ sung redaction, test regression, policy TTL/revocation và cập nhật playbook.

Không coi HTTP 200 tại Revocation Endpoint là dấu hiệu đã hoàn thành toàn bộ các bước trên nếu RS vẫn offline.

### 13.2. Khi phải dùng emergency key rotation

Nếu **private signing key** bị lộ, phạm vi ảnh hưởng có thể bao gồm **mọi token được ký bằng key đó**. Cần kế hoạch:

- Tạo/triển khai khóa an toàn mới; khóa cũ bị đánh dấu không còn tin cậy.
- Xác định đúng các RS có thể cache JWKS hoặc dùng trust store nội bộ.
- Phối hợp ép cập nhật trust cache và kiểm tra JWT cũ thật sự bị từ chối.
- Truyền thông về khả năng gián đoạn/token re-issue và quan sát lỗi 401.
- Không chỉ xóa key ở AS rồi tuyên bố tất cả RS đã biết.

Đây là quy trình ứng phó sự cố khóa ký, không nên áp dụng hằng ngày cho user logout hoặc role change.

## 14. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “Revoke trả 200 nghĩa là mọi API từ chối JWT ngay.” | RFC 7009 thành công tại AS; RS offline không tự biết state mới. |
| “JWT có chữ ký hợp lệ nghĩa là chưa revoke.” | Chữ ký chỉ bảo đảm tính toàn vẹn/xuất xứ, không cho biết revocation. |
| “Xóa authorization record sẽ xóa JWT trên thiết bị.” | JWT tự chứa vẫn tồn tại; RS offline có thể chấp nhận tới exp. |
| “Thu hồi refresh token vô hiệu mọi access token cũ.” | Ngăn refresh mới không đồng nghĩa RS cục bộ chặn JWT cũ. |
| “Logout khỏi web là revoke mọi token.” | Browser session/BFF cookie và access/refresh token là các state khác nhau. |
| “Opaque token bảo đảm revoke tức thời ở mọi nơi.” | Phụ thuộc introspection, state consistency, cache và failure mode. |
| “Cấu hình `opaqueToken` chỉ dùng được với token opaque thật.” | Spring có thể introspect cả JWT dưới dạng chuỗi token. |
| “Introspection tự động kiểm tra audience/resource như `JwtDecoder`.” | Phải kiểm thử AS policy và Resource Server authorization thực tế. |
| “Đặt TTL 5 phút tức là revoke ngay.” | Token còn có thể được dùng tới exp; TTL chỉ giới hạn cửa sổ. |
| “Denylist trong HashMap của một RS là đủ cho cluster.” | Node khác không thấy; cần state consistency/shared cache. |
| “Redis timeout nghĩa là token không có trong denylist.” | Lỗi lookup khác negative lookup; thiết kế fail-closed. |
| “Push event được phát là mọi node đã nhận.” | Eventual consistency, mất event hoặc lag cần cơ chế phục hồi. |
| “Xóa JWK là cách revoke một user.” | Có thể ảnh hưởng nhiều token, JWKS cache làm kết quả không tức thời. |
| “Spring Security Test `jwt()` chứng minh decoder revoked-jti.” | Mock authentication có thể bỏ qua decoder; cần signed-token integration test. |
| “Token bị revoke thì mọi request đang xử lý phải dừng.” | Cần cơ chế authorization/transaction check bổ sung khi commit. |

## 15. Checklist trước khi triển khai production

**Protocol và Authorization Server**

- [ ] Revocation Endpoint tuân RFC 7009: POST, xác thực client, không leak token.
- [ ] HTTP 200 khi token revoked hoặc token không hợp lệ, không tiết lộ token existence.
- [ ] Phân biệt revoke access token/refresh token và cascade policy.
- [ ] Token state được lưu bền vững/nhất quán trong AS cluster.
- [ ] Introspection của JWT revoked thực sự trả `active=false` theo implementation.
- [ ] Token endpoint, revocation và introspection dùng HTTPS và logging redaction.

**Resource Server**

- [ ] RS kiểm tra chữ ký, `iss`, `aud`, `exp`, `nbf` và scope/resource policy.
- [ ] Kiến trúc ghi rõ JWT offline thuần túy **không** có per-token immediate revocation.
- [ ] Nếu yêu cầu revoke trước exp, RS dùng introspection, denylist hoặc current policy state.
- [ ] Denylist có key namespace, TTL, multi-node propagation và fail-closed policy.
- [ ] Introspection cache TTL phù hợp revocation SLA; AS outage được xử lý an toàn.
- [ ] JWKS rotation không được nhầm với per-token revoke.

**Vận hành và kiểm thử**

- [ ] Có một revocation SLA với định nghĩa rõ request mới/in-flight, phạm vi region/node.
- [ ] Có ma trận kiểm thử logout, revoke, role change, client compromise và refresh race.
- [ ] Test với signed JWT thực và HTTP filter chain, không chỉ security test principal mock.
- [ ] Có cảnh báo event lag, cache failure, introspection latency, token revocation propagation.
- [ ] Không lưu raw token trong logs, traces, metric labels và test artifacts.
- [ ] Có incident runbook với từng bước revoke, RS enforcement và emergency key rotation.

## 16. Tài liệu tham khảo

- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): request, response 200, token cascade và ghi chú implementation cho self-contained tokens.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): `active`, introspection response và cache state.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): claims và validation của JWT access token.
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519): `iss`, `aud`, `exp`, `nbf`, `jti`.
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700): access token/refresh token security và bảo vệ authorization.
- [Spring Authorization Server 1.5.x — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): Revocation Endpoint, Introspection Endpoint, filters/providers và extension points.
- [Spring Authorization Server 1.5.x — Core Model Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): `OAuth2AuthorizationService` và token state.
- [Spring Authorization Server 1.5.x — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): `AuthorizationServerSettings` và default endpoint paths.
- [Spring Security 6.5 — Resource Server JWT](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html): xác minh JWT cục bộ và validators.
- [Spring Security 6.5 — Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/opaque-token.html): dùng introspection với opaque token **hoặc JWT**.

**Kết luận:** Revocation Endpoint thay đổi **trạng thái token tại Authorization Server**, trong khi JWT được Resource Server xác minh cục bộ vẫn là một dữ liệu đã ký, có thể được chấp nhận cho đến khi hết hạn. Do đó, **không thể bảo đảm thu hồi JWT tức thời chỉ bằng RFC 7009 hoặc xóa record tại AS**. Nếu cần chặn token trước `exp`, Resource Server phải đọc thêm trạng thái cập nhật qua introspection, denylist hoặc chính sách authorization; mỗi giải pháp đều cần mô hình cache, propagation và fail-closed rõ ràng. Thiết kế đúng bắt đầu từ **thời gian thu hồi mục tiêu, threat model và kiểm thử trên mọi RS**, không phải từ kỳ vọng rằng JWT signature tự phản ánh một lệnh revoke mới.
