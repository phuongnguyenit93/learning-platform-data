# JwtDecoder và opaque token introspection

Một ứng dụng Invoice Web được cấp access token để gọi Invoice API. Có hai cách triển khai Resource Server (RS) phổ biến:

- **JWT access token:** Authorization Server (AS) phát một token có chữ ký mà API có thể kiểm tại chỗ bằng **`JwtDecoder`** và khóa xác minh tin cậy của AS.
- **Opaque/reference access token:** Client nhận một chuỗi không mang claims có thể tự đọc; API gửi token tới **OAuth 2.0 introspection endpoint** của AS để biết token có còn `active` hay không và lấy metadata cần thiết.

Ví dụ: kẻ tấn công sao chép access token còn hạn từ log. Nếu Invoice API chỉ kiểm JWT offline, nó có thể tiếp tục nhận bản sao token tới `exp` dù người dùng đã logout và AS đã revoke refresh token. Nếu Invoice API sử dụng introspection, AS có thể phản hồi `active=false` khi access token bị thu hồi, nhưng **cache, độ trễ và lỗi kết nối AS** vẫn ảnh hưởng khả năng ngăn dùng lại. Với cả hai phương án, **`active=true` hay chữ ký JWT đúng không đồng nghĩa request có quyền truy cập mọi hóa đơn**.

Đây là bài **“JwtDecoder và opaque token introspection”** thuộc chương **Resource server** của module **Security Token Security Fundamentals**. Mục tiêu là nắm chính xác mô hình tin cậy AS–Client–RS, chọn chiến lược kiểm token, cấu hình **Spring Security 6 / OAuth2 Resource Server** bằng `JwtDecoder` hoặc `OpaqueTokenIntrospector`, xác minh issuer, audience, scope, expiry, token type và trạng thái revoke, đồng thời bảo vệ token khỏi lộ lọt, replay, downgrade và confused deputy.

**Nguyên tắc xuyên suốt:** **Resource Server phải xác thực token và tự thực thi authorization ở boundary của chính API.** Không được chỉ dựa vào việc gateway/Client “đã login”, token có ba đoạn cách nhau bằng dấu chấm, hoặc introspection trả HTTP 200.

## 1. Ranh giới tin cậy: OAuth client không phải nơi quyết định API được phép

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng An
    participant C as Invoice Web / Client
    participant AS as Authorization Server
    participant RS as Invoice Resource Server
    U->>C: Đăng nhập và yêu cầu xem hóa đơn
    C->>AS: OAuth 2.0 / OIDC authorization flow
    AS-->>C: Access token A1
    C->>RS: GET /invoices/42 + Authorization Bearer A1
    alt JWT access token
        RS->>RS: JwtDecoder: JWS signature, issuer, time, audience, profile
    else Opaque access token
        RS->>AS: POST introspection(A1) với RS authentication
        AS-->>RS: JSON active + metadata
    end
    RS->>RS: Kiểm scope, client/subject, tenant và quyền trên invoice 42
    RS-->>C: 200 dữ liệu hoặc 401/403
~~~

| Vai trò | Trách nhiệm chính | Không được suy |
|---|---|---|
| **Authorization Server / OpenID Provider** | Xác thực/ủy quyền theo flow, phát access/refresh token, công bố trusted metadata/JWKS, có thể introspect/revoke | AS không thay RS kiểm quyền trên từng object |
| **OAuth Client** | Nhận/lưu/gửi token trong phạm vi grant; với OIDC có thể xử lý ID token để login | Client không được tự cấp quyền cho Invoice API bằng claim tự khai |
| **Resource Server (API)** | Kiểm access token, issuer/audience/scope/time/token purpose, sender binding/revoke nếu cần và **business authorization** | Token hợp lệ không đồng nghĩa mọi resource được phép |
| **Bearer token holder** | Trình token bằng `Authorization: Bearer` | Ai có chuỗi Bearer có thể thử dùng lại; không chứng minh người gửi là client gốc |

### Access token khác ID token và refresh token

- **Access token:** Credential client gửi tới **RS**; token phải dành cho đúng audience/resource, có scope và các kiểm soát thích hợp.
- **ID token:** Do OP phát cho **Relying Party** để chứng minh authentication theo OIDC. **Không được dùng ID token thay access token tại API** dù cũng là JWT có chữ ký hợp lệ.
- **Refresh token:** Client gửi tới **AS token endpoint** để xin access token mới theo policy. **Không gửi refresh token tới API**.

Client có thể không biết claims của access token: opaque token và JWE (mã hóa cho RS) đều có thể khiến access token là một chuỗi không đọc được với client. **RS vẫn cần kiểm đúng token profile/issuer/audience**, không chỉ giải mã thành công.

## 2. Khi nào dùng `JwtDecoder`, khi nào dùng introspection?

| Tiêu chí | `JwtDecoder` cho JWT có chữ ký | Opaque token introspection |
|---|---|---|
| **Hình thức token** | Thường JWT compact JWS (3 segments) theo profile | Opaque/reference string; cấu trúc không có ý nghĩa với RS |
| **Nguồn bằng chứng** | JWS signature + AS trusted keys + claims | AS introspection trả response cho RS được xác thực |
| **Kết nối AS trên mỗi request** | Không cần nếu đã có key hợp lệ trong cache | Thường cần, trừ cache introspection có chính sách rõ |
| **Lọc token đã revoke trước expiry** | **Không tự động** khi kiểm JWT offline | Có thể nhận `active=false` sớm nếu AS cập nhật và cache không stale |
| **Khả năng tiếp tục khi AS outage** | Có thể kiểm token còn hạn bằng key cache | Phụ thuộc cache/result còn hợp lệ; thường phải fail closed |
| **Chi phí/latency** | Cryptographic verification ở RS; JWKS refresh định kỳ | Network RTT, AS capacity, cache và auth cho introspection |
| **Claims bị client/proxy đọc** | JWS payload có thể decode, không bí mật | Opaque không tiết lộ claims cho client |
| **Quyền kiểm ở RS** | Phải kiểm scope/audience/tenant/object dù signature đúng | Phải kiểm scope/audience/tenant/object dù active=true |
| **Thay đổi policy/revoke** | Token cũ có claims bất biến; thêm state nếu cần | AS có thể phản ánh trạng thái token/grant tại thời điểm kiểm |
| **Bảo vệ trước token bị sao chép** | Bearer token còn hạn có thể replay | Bearer token active cũng có thể replay |

**Không chọn chỉ vì token “trông giống JWT”**. Một bearer string có dấu chấm cũng có thể là opaque token theo contract; một RS configured cho opaque token không cần cố parse token thành JWT. Lựa chọn nên được **đăng ký theo issuer, client/resource và API trust profile**, không dựa vào sniffing token do attacker gửi.

### Câu hỏi quyết định ban đầu

1. AS cấp **JWT access token hay reference token** cho audience này?
2. RS có trusted issuer/JWKS và hỗ trợ profile/chữ ký tương ứng không?
3. **Revocation SLO** là bao lâu? Nếu cần chặn trước `exp`, JWT offline có đủ không?
4. Latency/QPS/availability của introspection endpoint có đủ cho mọi API requests không?
5. Token có thể chứa claims nhạy cảm không nên để browser/client/proxy đọc không?
6. RS cần **scope, audience, tenant, sender binding, account status** từ nguồn nào?
7. Khi AS outage/JWKS rotation/introspection timeout, API phải fail như thế nào?

Không có lựa chọn “tốt nhất cho mọi hệ thống”: JWT thường hợp với kiểm offline hiệu quả; opaque thuận lợi cho state/revocation tập trung, nhưng có dependency vào AS.

## 3. JWT: phân biệt decode, verify, validate và authorize

Chuỗi JWS compact thường gồm:

~~~text
BASE64URL(header).BASE64URL(payload).BASE64URL(signature)
~~~

Ví dụ payload **chưa phải JWT đã ký**:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "user:an",
  "aud": ["invoice-api"],
  "client_id": "invoice-web",
  "scope": "invoice:read",
  "iat": 1800000000,
  "nbf": 1800000000,
  "exp": 1800000300,
  "jti": "at-unique-example-01"
}
~~~

**Base64URL decode** chỉ làm claims dễ đọc hơn, **không chứng minh claims đáng tin**. Cần tách bốn thao tác:

| Thao tác | Làm gì? | Có đủ để cấp quyền không? |
|---|---|---|
| **Decode** | Giải mã Base64URL thành JSON/bytes | **Không**; attacker tự tạo JSON được |
| **Verify** | Kiểm JWS signature theo thuật toán và AS verification key tin cậy | Chưa: token vẫn có thể sai issuer/audience/expiry/type |
| **Validate** | Kiểm profile, `iss`, `aud`, `exp`, `nbf`, `iat`, `typ`/token purpose, binding và policy | Chưa: cần quyền thao tác cụ thể |
| **Authorize** | Kiểm `scope`/authority, tenant, user/client, object ownership và nghiệp vụ | Chỉ allow khi mọi điều kiện liên quan đạt |

### `JwtDecoder` thật sự đảm nhiệm phần nào?

Trong **Spring Security**, `JwtDecoder` là interface chuyển token string thành đối tượng `Jwt` **sau khi xử lý kiểm chứng/validation theo cấu hình decoder**. `NimbusJwtDecoder` dựa trên Nimbus JOSE+JWT cho parsing/JWS cryptographic verification và validators. **Không tự giả định một `JwtDecoder` bất kỳ luôn kiểm audience, token type, tenant hoặc quyền object**.

~~~text
Request Authorization: Bearer A1
   |
   v
BearerTokenAuthenticationFilter
   |
   v
JwtAuthenticationProvider -> JwtDecoder.decode(A1)
   |
   +-- parse JOSE / verify trusted key and allowed alg
   +-- configured Jwt validators (issuer/time/audience/...)
   |
   v
JwtAuthenticationToken + mapped authorities
   |
   v
SecurityFilterChain authorization + application authorization
~~~

Nếu decoder chỉ verify chữ ký nhưng không check audience, Invoice API có thể nhận token hợp lệ do cùng AS phát **cho Payroll API**. Đó là **token substitution/cross-resource authorization bug**.

## 4. Trusted issuer/JWKS, `alg` và `kid`

Khi RS dùng JWS, nó phải biết **issuer tin cậy** và tập khóa xác minh qua cấu hình/registration:

~~~text
Trusted issuer: https://auth.example.test
Trusted JWKS:   https://auth.example.test/oauth2/jwks
Allowed JWS algs for this profile: RS256
Expected token audience: invoice-api
Expected resource-server access-token purpose: OAuth access token
~~~

AS công bố public verification keys qua JWKS. Một JWK công khai có thể có `kid`, `kty`, `use=sig`, `alg=RS256` và RSA public components. **AS signing private key không được công khai trên JWKS**.

### `kid` không phải chứng cứ tin cậy

~~~json
{
  "alg": "RS256",
  "kid": "as-sig-v4",
  "typ": "at+jwt"
}
~~~

Header này có thể được **bất kỳ attacker nào tự viết**, nên `kid` chỉ là **gợi ý chọn khóa trong trusted key set**, không phải lệnh cho RS tải public key từ URL tùy ý.

**Tránh các kiểu xử lý sai:**

~~~text
BAD:
  read JWT header
  load key from header.jku / header.x5u / attacker-chosen URL
  verify signature with that key
  accept claims as if AS signed

GOOD:
  choose preconfigured issuer / JWKS authority
  restrict accepted algorithms and key purpose
  select matching kid from trusted JWKS/keyring
  verify signature and required claims
~~~

Các header như `jku`/`x5u` hoặc embedded `jwk` có thể làm xuất hiện **SSRF/key substitution** nếu dùng không theo trust policy. Cần loại bỏ thuật toán `none`, chặn confusion giữa HS256/RS256 và không cho header `alg` tự mở rộng allowlist.

### Key rotation

AS thường cần xoay khóa ký. Quy trình an toàn:

1. Công bố public verification key mới trong **trusted JWKS**.
2. Đợi RS/JWKS caches nhận khóa mới trước khi phát JWT với `kid` mới, nếu cần.
3. AS bắt đầu ký bằng key mới; RS chấp nhận các key versions đúng policy.
4. Giữ key xác minh cũ cho **tokens đã phát còn hợp lệ** trong migration window, trừ khi key bị compromise.
5. Retire key cũ khi không còn token hợp lệ hoặc theo incident response.

Nếu RS cache JWKS quá lâu và không thấy key mới, token hợp lệ có thể bị từ chối gây outage. **Không giải quyết bằng việc bỏ signature verification** hoặc tự chấp nhận mọi `kid` lạ.

### `issuer-uri` và `jwk-set-uri` trong Spring

- Dùng **`issuer-uri`** giúp framework/Boot lấy metadata từ **địa chỉ issuer tin cậy**, suy JWKS URI và áp issuer validation khi auto-config đúng.
- Dùng **`jwk-set-uri`** trỏ trực tiếp trusted JWKS endpoint; có thể giảm phụ thuộc vào discovery lúc khởi động, nhưng phải **tự bảo đảm issuer validator đúng** nếu chỉ cấu hình JWKS.
- Một số phiên bản Spring Boot cho phép khai báo cả `issuer-uri` và `jwk-set-uri` để không cần gọi discovery ở startup nhưng vẫn kiểm issuer. **Phải kiểm phiên bản/configuration contract**, không suy từ tên property.

**Không lấy `issuer-uri`/`jwk-set-uri` trực tiếp từ `iss` trong token chưa xác minh**, nếu hệ thống không có cơ chế multi-tenant trust registry nghiêm ngặt. Một RS chỉ tin issuer A không được tự động tin issuer B chỉ vì B tự khai trong payload.

## 5. Claims bắt buộc kiểm ở Resource Server

| Claim/thuộc tính | Kiểm gì? | Hậu quả nếu thiếu kiểm |
|---|---|---|
| **`iss`** | Khớp **exact** trusted issuer, đúng tenant/trust registry | JWT từ issuer khác có thể bị nhận nhầm |
| **`aud`** | Chứa **ID của RS/resource đích** | Token cấp cho API A dùng ở API B |
| **`exp`** | Token chưa hết hạn theo clock RS và leeway nhỏ phù hợp | Token cũ bị replay vô hạn |
| **`nbf`** | Token không được dùng trước thời điểm hợp lệ | Chấp nhận trước thời hạn |
| **`iat`** | Issued-at hợp lý; max-lifetime nếu profile yêu cầu | Token được phát quá dài hoặc sai thời gian |
| **`typ`/token profile** | Đây là OAuth access token theo registration, không phải ID token | Token purpose confusion |
| **`scope`/`scp`** | Quyền được AS cấp, so tokenized chính xác | Nhầm scopes hoặc cấp quyền vượt mức |
| `client_id` | Client được cấp token, đặc biệt M2M/delegation policy | Không áp được client-specific policy |
| `sub` | End-user subject hoặc workload subject theo grant/profile | Nhầm user với service account |
| `cnf` / sender binding | DPoP/mTLS proof/chứng chỉ khớp token | Token sender-constrained bị dùng như Bearer thuần |
| `jti` / grant status | Audit, denylist hoặc revocation nếu kiến trúc yêu cầu | Không thu hồi sớm token JWT đã phát |
| **Tenant/object context** | Quyền trên invoice ID/owner/organization thực tế | IDOR/BOLA dù JWT hợp lệ |

### `exp` và leeway

JWT NumericDate thường tính bằng **Unix seconds**. Với clock tolerance `δ`:

~~~text
if now >= exp + δ:
  reject

if nbf exists and now + δ < nbf:
  reject
~~~

**Leeway có thể kéo dài acceptance sau `exp`**, nên phải giới hạn phù hợp với access-token lifetime. Không tự chọn 5 phút clock skew cho access token sống 2 phút. Nếu profile yêu cầu max lifetime, so `exp - iat` với policy; không tin browser clock hay token response `expires_in` để RS bỏ kiểm `exp`.

### Audience là authorization boundary

~~~text
JWT #A:
  iss=https://auth.example.test
  aud=invoice-api
  scope=invoice:read
  -> Invoice API có thể kiểm tiếp.

JWT #B:
  iss=https://auth.example.test
  aud=payroll-api
  scope=invoice:read
  -> Invoice API MUST REJECT wrong audience.
~~~

`scope=invoice:read` **không thay `aud`**. Một issuer có thể cấp cùng tên scope cho nhiều resources; RS phải ràng buộc token đúng resource.

### Scope không phải quyền cuối cùng

Một JWT có `scope=invoice:read` cho phép thao tác thuộc lớp nghiệp vụ đó nhưng không mặc định cho An xem **mọi** hóa đơn:

~~~text
GET /invoices/INV-42
  token.valid = true
  token.scope includes invoice:read
  invoice.owner = user:Binh
  authenticated subject = user:An

Correct outcome:
  deny (unless explicit delegated entitlement exists).
~~~

RS vẫn kiểm subject/tenant/resource ownership. Nếu route cần quyền admin hoặc cross-tenant delegation, phải có một **authorization model riêng**, không diễn dịch `scope` là chủ sở hữu dữ liệu.

## 6. Spring Boot 3 / Spring Security 6: cấu hình JWT Resource Server

Ví dụ cấu hình application properties/YAML cho một API **chỉ chấp nhận JWT access tokens**:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.test
          jwk-set-uri: https://auth.example.test/oauth2/jwks
~~~

Đây là **URL minh họa**; trong môi trường thực, JWKS URI phải đúng discovery/registration của issuer. Cấu hình issuer+JWKS phụ thuộc Spring Boot version, cần test startup/issuer validation. **Việc set các properties này không tự đảm bảo audience, object permission hoặc sender proof được kiểm**.

### SecurityFilterChain và chính sách route

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
@EnableWebSecurity
class InvoiceApiSecurity {
    @Bean
    SecurityFilterChain invoiceJwtChain(HttpSecurity http)
            throws Exception {
        http
            .securityMatcher("/api/invoices/**")
            // CHỈ dành cho API nhận Bearer header, KHÔNG chấp nhận
            // session/refresh cookie làm credential ở các routes này.
            .csrf(csrf -> csrf.disable())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/invoices/**")
                    .hasAuthority("SCOPE_invoice:read")
                .requestMatchers(HttpMethod.POST, "/api/invoices/**")
                    .hasAuthority("SCOPE_invoice:write")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(withDefaults()));
        return http.build();
    }
}
~~~

Với **JWT Bearer token thuần trong `Authorization` header**, endpoint không dựa vào ambient browser cookie để xác thực, nên threat model CSRF khác session-cookie apps. Nếu cùng ứng dụng còn có BFF cookie-authenticated routes, **không vô hiệu hóa CSRF toàn cục chỉ vì đã cấu hình Resource Server**. Cấu hình chính xác cho nhiều filter chains cần kiểm thứ tự matcher và default catch-all chain.

### Mapping authorities

Mặc định, Spring Security thường map scopes (từ `scope` hoặc `scp` theo converter) thành authorities dạng `SCOPE_invoice:read`. Nhưng:

- AS có thể dùng claim khác hoặc custom format; cần cấu hình **`JwtAuthenticationConverter`/`JwtGrantedAuthoritiesConverter`** nếu profile thực tế khác.
- Không so substring để tìm scope: `invoice:read-all` **không đồng nghĩa** `invoice:read`.
- Một số issuer đặt roles/permissions trong nested claims; không tự map mọi vai trò chưa được kiểm vào `ROLE_ADMIN`.
- Path-based authority vẫn không thay object-level authorization ở service/repository.

**Các Spring class names và config là ví dụ cho Spring Security 6.x**, cần đối chiếu dependency/phiên bản thật trong project trước khi dùng nguyên xi.

## 7. Tùy biến `JwtDecoder`: issuer, audience và clock skew

Mục này tập trung vào phần dễ bỏ sót: **decoder mặc định thường không biết audience cụ thể của Invoice API**.

~~~java
import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtIssuerValidator;
import org.springframework.security.oauth2.jwt.JwtTimestampValidator;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
class TrustedInvoiceJwtDecoderConfig {
    private static final String ISSUER =
        "https://auth.example.test";
    private static final String JWKS =
        "https://auth.example.test/oauth2/jwks";
    private static final String AUDIENCE = "invoice-api";

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withJwkSetUri(JWKS)
                .jwsAlgorithm(SignatureAlgorithm.RS256)
                .build();

        OAuth2TokenValidator<Jwt> audienceValidator = jwt -> {
            if (jwt.getAudience() == null ||
                !jwt.getAudience().contains(AUDIENCE)) {
                return OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        "invalid_token",
                        "Unexpected audience",
                        null));
            }
            return OAuth2TokenValidatorResult.success();
        };

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                new JwtIssuerValidator(ISSUER),
                new JwtTimestampValidator(Duration.ofSeconds(10)),
                audienceValidator));
        return decoder;
    }
}
~~~

### Kiểm từng lớp của ví dụ

1. **Trusted JWKS URI** là cấu hình cố định; không lấy từ JWT `iss`/`kid` do client đưa vào.
2. **`jwsAlgorithm(RS256)`** chỉ cho phép thuật toán đã chọn theo profile; không tin header tự yêu cầu `none` hoặc HS256.
3. **Issuer validator** so `iss` với issuer đã đăng ký.
4. **Timestamp validator** kiểm thời hạn; ở đây ví dụ dùng 10 giây clock skew, **không phải con số chuẩn bắt buộc**.
5. **Audience validator** yêu cầu token dành cho `invoice-api`; một JWT ký đúng cho `payroll-api` bị từ chối.
6. **Token-purpose validation** (chẳng hạn `typ=at+jwt` với RFC 9068) và max issued lifetime có thể cần **validators/JOSE header policy riêng**. Đoạn code chưa tự thực hiện toàn bộ yêu cầu RFC 9068.
7. **OAuth scope mapping** và object authorization xảy ra **sau decode**; không gắn chúng nhầm thành “signature verification”.

**Cảnh báo:** Khi tự gọi `setJwtValidator`, bạn có thể **ghi đè** validator chain mặc định của decoder. Cần khai báo **đầy đủ** những validators ứng dụng cần và test; không chỉ thêm audience validator rồi vô tình bỏ issuer/expiry validation. Ví dụ đã khai issuer và timestamp rõ ràng, nhưng production còn phải bổ sung profile/purpose/tenant policy tương ứng.

## 8. Opaque token introspection theo RFC 7662

**Opaque token** là một chuỗi mà RS **không được tự giả định ý nghĩa nội bộ**. Nó có thể là reference tới grant/token record của AS, hoặc một giá trị khác mà AS hiểu. RS thường hỏi AS qua **OAuth 2.0 Token Introspection (RFC 7662)**.

### Request từ RS tới AS

~~~http
POST /oauth2/introspect HTTP/1.1
Host: auth.example.test
Authorization: Basic <redacted-introspection-client-credential>
Content-Type: application/x-www-form-urlencoded
Accept: application/json

token=<percent-encoded-opaque-access-token>&token_type_hint=access_token
~~~

- **`token`** là tham số **bắt buộc**; RS gửi nguyên token mà client trình, URL-encode trong **form body**, không đặt vào query.
- **`token_type_hint`** là **tùy chọn**; giá trị như `access_token` chỉ giúp AS tối ưu tra cứu, **không phải bằng chứng** token thuộc loại đó.
- RS **phải được AS cho phép truy cập introspection endpoint**, theo client authentication/IAM/registration thích hợp. Basic là một cách minh họa; có thể dùng mTLS hoặc cơ chế khác AS hỗ trợ.
- Dùng **HTTPS/TLS** và verify AS endpoint/certificate. Introspection request chứa **raw bearer token**; không log URL, body hoặc HTTP Authorization credential.
- **Không dùng token của chính caller làm credentials gọi introspection** nếu AS profile yêu cầu RS authentication tách biệt.

### Response cho token active

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "active": true,
  "iss": "https://auth.example.test",
  "sub": "user:an",
  "client_id": "invoice-web",
  "token_type": "Bearer",
  "scope": "invoice:read invoice:export",
  "aud": ["invoice-api"],
  "iat": 1800000000,
  "nbf": 1800000000,
  "exp": 1800000300,
  "jti": "token-reference-illustrative-001"
}
~~~

**`active` là member bắt buộc kiểu JSON boolean theo RFC 7662**; các trường khác phụ thuộc AS và quyền của RS:

| Member | Kiểu/ý nghĩa | Kiểm hoặc sử dụng thế nào? |
|---|---|---|
| **`active`** | Boolean: token hiện được AS coi là active | **Chỉ `true` thực sự** mới được kiểm tiếp; `false` → từ chối |
| `scope` | Chuỗi các scope **cách nhau bởi khoảng trắng** | Tách chính xác từng scope, không so substring |
| `client_id` | OAuth client được cấp token | Kiểm client policy nếu API cần |
| `username` | Tên hiển thị/username, tùy chọn | **Không lấy làm subject authority chính** khi `sub`/issuer model khác |
| `token_type` | Loại token, thường `Bearer` | Kiểm theo profile, **không** coi mọi token là access token phù hợp |
| `exp`/`iat`/`nbf` | NumericDate, thường Unix seconds | Kiểm expiry/not-before/max lifetime khi có và theo contract |
| `sub` | Subject theo issuer | Không đồng nhất với client ID; binding user/tenant |
| `aud` | Audience; có thể là **string hoặc mảng strings** | Invoice API chỉ nhận audience dành cho chính mình |
| `iss` | Issuer/token authority, nếu AS cung cấp | Khớp expected issuer khi có; trust endpoint được pin từ trước |
| `jti` | Token ID có thể được AS cung cấp | Audit, revocation/denylist khi cần; không phải CSRF token |

Các fields như `cnf` (proof-of-possession binding), roles, tenant, consent hoặc custom entitlements **không mặc định có** trong RFC 7662 response. Chỉ sử dụng nếu AS/RS có **schema và trust contract rõ ràng**.

### Response cho token không active

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"active": false}
~~~

Hai HTTP responses trên **không ấn định chính sách cache** để tập trung vào `active`. Trong triển khai thật, **phải tuân header `Cache-Control` và hợp đồng AS**: nếu AS yêu cầu `no-store`, RS không được cache response; chỉ cân nhắc cache khi policy/HTTP directives cho phép và không vượt `exp` hoặc revocation SLO.

AS nên tránh tiết lộ claims nhạy cảm của inactive token. Token có thể **không tồn tại**, **hết hạn**, **bị revoke**, **không thuộc authority này** hoặc không còn được AS coi là active theo policy.

**HTTP 200 của introspection không có nghĩa token được phép dùng.** Quyết định phụ thuộc **`active` và các metadata/authorization checks**:

~~~text
HTTP 200 + {"active": false}  -> REJECT TOKEN.
HTTP 200 + {"active": true}   -> CHECK issuer/audience/scope/time/permissions.
HTTP 401 from introspection   -> RS authentication/config error; NOT "active".
HTTP 500/timeout              -> validation unavailable; FAIL CLOSED.
Malformed JSON / no active    -> REJECT / operational error, NEVER default true.
~~~

Về mặt RFC, invalid/inactive token có response `active=false`; **AS không có nghĩa vụ tiết lộ nguyên nhân**. Không expose thông tin “token này từng tồn tại và thuộc tài khoản X” từ token lookup cho caller không được phép.

## 9. Introspection response là thông tin đáng tin có giới hạn, không phải authorization cuối

Một RS chỉ được tin **response từ đúng AS introspection endpoint**, sau khi TLS và credentials của RS được kiểm đúng. **Ngay cả khi `active=true`**, RS vẫn phải kiểm ý nghĩa của token đối với API:

~~~text
AS says:
  active = true
  scope = invoice:read
  aud = invoice-api
  sub = user:an

Invoice API request:
  GET /api/invoices/INV-42

Business data:
  invoice INV-42 owned by user:binh, tenant=other-org

Result:
  DENY because object-level permission not granted.
~~~

### Phân biệt authentication, authorization và token state

| Câu hỏi | Cơ chế | Ai trả lời? |
|---|---|---|
| Token có do đúng issuer phát không? | JWS signature/issuer hoặc AS introspection trust | RS và AS |
| Token còn được AS chấp nhận không? | JWT expiry + state nếu có, hoặc introspection `active` | RS và/hoặc AS |
| Token dành cho API này không? | `aud`/resource policy | **RS** |
| Token mang scope nào? | Verified JWT/introspection `scope` | AS cấp, RS diễn giải |
| Caller có quyền xem Invoice 42? | ACL/tenant/ownership/business policy | **RS** |
| Có thể sử dụng bản sao token không? | Sender-binding, replay protection, revocation | RS/AS theo profile |

**Không coi `client_id` là `sub`:** trong client credentials grant, token có thể đại diện cho service/workload chứ không có người dùng cuối. Với user-delegated grant, `sub` có thể là user, `client_id` là ứng dụng nhận quyền; RS cần kiểm đúng actor và delegation semantics.

### Không mặc định mọi introspection response đều có `aud`/`iss`

RFC 7662 cho phép các metadata tùy chọn; một AS có thể trả `active=true` cùng `scope` nhưng không đưa `aud`/`iss` vào response. RS phải có **hợp đồng bảo mật trước**:

- Nếu API bắt buộc **audience isolation**, cần AS cung cấp/đảm bảo audience theo cách RS kiểm được. **Không tự coi thiếu `aud` là wildcard toàn hệ thống**.
- Nếu `iss` vắng, RS vẫn chỉ gọi **endpoint AS đã pin** và có thể coi issuer theo endpoint/registration được tin cậy, **nếu contract cho phép**; không suy từ token string hay caller header.
- Nếu thiếu `scope` hoặc một claim được route yêu cầu, **không tự cấp quyền mặc định**. Từ chối hoặc mapping rất hạn chế theo policy đã xác định.
- Không áp ý nghĩa `username`, `tenant` hay `role` ngoài contract khi provider custom claims không có schema ổn định.

### Dạng audience và scope

~~~json
{
  "active": true,
  "aud": "invoice-api",
  "scope": "invoice:read invoice:export"
}
~~~

và:

~~~json
{
  "active": true,
  "aud": ["invoice-api", "search-api"],
  "scope": "invoice:read"
}
~~~

đều là **dạng metadata có thể xuất hiện**. Validator phải kiểm `aud` **theo schema thực** và so exact membership, không so `contains("invoice")` với JSON/string bất kỳ. Với scope, dùng tokenizer theo khoảng trắng thành **những giá trị chính xác**, không phân quyền dựa `scope.contains("read")`.

## 10. Spring Boot 3 / Spring Security 6: Opaque Token Resource Server

Với một API **chỉ nhận opaque access token**, Spring Boot có thể cấu hình:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://auth.example.test/oauth2/introspect
          client-id: invoice-resource-server
          client-secret: <secret-from-secure-deployment-configuration>
~~~

**Không đặt client secret thật trong YAML commit lên Git.** Giá trị trên chỉ là placeholder tài liệu; production nên dùng secret manager/IAM/environment injection được bảo vệ. Introspection credentials là credential của **RS khi gọi AS**, không phải public `client_id` của Invoice Web.

### SecurityFilterChain cho opaque token

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
class OpaqueInvoiceApiSecurity {
    @Bean
    SecurityFilterChain opaqueInvoiceChain(HttpSecurity http)
            throws Exception {
        http
            .securityMatcher("/opaque-api/invoices/**")
            // Chỉ an toàn khi route KHÔNG dùng browser cookie auth.
            .csrf(csrf -> csrf.disable())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET,
                    "/opaque-api/invoices/**")
                    .hasAuthority("SCOPE_invoice:read")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2
                .opaqueToken(withDefaults()));
        return http.build();
    }
}
~~~

Khi resource server xử lý request Bearer, Spring Security sử dụng một **`OpaqueTokenIntrospector`** để gọi AS/kiểm token theo cấu hình. Kết quả thường được ánh xạ thành authenticated principal và authorities (như `SCOPE_invoice:read`), nhưng **mỗi AS có thể khác schema claim** và ứng dụng phải kiểm thật.

**Lưu ý cấu hình:** Nếu bạn có **nhiều Resource Server chains trong cùng app**, Boot auto-configuration và beans introspector/decoder có thể cần được wiring tường minh; ví dụ `jwt` và `opaqueToken` ở đây trình bày **hai kiểu API tách biệt**. Không copy cả hai class vào một ứng dụng rồi giả định bean discovery, matcher ordering và default catch-all đều đúng.

### Khi cần custom introspector

Một `OpaqueTokenIntrospector` tùy biến hoặc decorator thường cần:

1. Gọi **trusted AS endpoint** với credentials RS và TLS đúng policy.
2. Chấp nhận chỉ response `active=true`, dữ liệu đúng JSON schema.
3. Kiểm audience/issuer/time/token type và metadata còn thiếu theo security contract.
4. Chuyển scopes/authorities theo mapping được AS/RS thống nhất.
5. Cache có giới hạn TTL/revocation SLO, bảo vệ dữ liệu response và fail closed khi lỗi.
6. Nếu token sender-constrained, kiểm proof/chứng chỉ **ở request hiện tại**, không chỉ nhìn `cnf`.

Không biến custom introspector thành một **bộ giải mã JWT bằng Base64** rồi tin các claims đó. Với opaque token, AS là authority về trạng thái; với JWT offline, trusted cryptographic verification là nền tảng.

## 11. Spring `JwtAuthenticationToken` và opaque principal khác nhau ở đâu?

Spring Security tách **validation** và **representation của authenticated principal**:

~~~text
JWT pipeline:
  BearerTokenAuthenticationFilter
     -> JwtAuthenticationProvider
     -> JwtDecoder
     -> JwtAuthenticationToken

Opaque pipeline:
  BearerTokenAuthenticationFilter
     -> OpaqueTokenAuthenticationProvider
     -> OpaqueTokenIntrospector
     -> BearerTokenAuthentication (principal attributes/authorities)
~~~

### Không ép code business phụ thuộc sai token format

Ví dụ một controller viết:

~~~java
// Chỉ phù hợp khi route thật sự dùng JwtAuthenticationToken.
// Với opaque token, principal object có dạng khác.
// @AuthenticationPrincipal Jwt jwt
~~~

Nếu cùng một service có **cả JWT và opaque endpoints**, không nên để business logic đọc `Jwt` hoặc `BearerTokenAuthentication` tùy ý ở mọi nơi. Hãy chuyển kết quả xác thực thành một **domain identity** có kiểu rõ:

~~~java
record VerifiedCaller(
    String issuer,
    String subject,
    String oauthClientId,
    String tenantId,
    java.util.Set<String> scopes
) {}
~~~

Một **trusted adapter** lấy từ đã-verify JWT hoặc introspection result, kiểm mandatory fields, rồi tạo `VerifiedCaller`. Controller/service dùng identity đó để kiểm ownership/quyền, không lấy subject/tenant từ query params do browser tự khai.

### Đừng đồng nhất các ý nghĩa

- `Authentication.getName()` có thể dựa trên `sub` hoặc một claim khác theo converter, **không phải chứng minh tenant/user ownership**.
- `JwtAuthenticationToken` và `BearerTokenAuthentication` chỉ biểu diễn token đã đi qua **configured authentication pipeline**, không chứng minh business permission.
- `SCOPE_invoice:read` là authority có nguồn từ scopes; custom mapping có thể thay prefix. Security review phải chắc quyền không bị “mở rộng” lúc mapping.
- **Access token secret** có thể vẫn tồn tại trong authentication object hoặc logs nếu bạn in toàn bộ object. Không log raw credentials.

## 12. Cache introspection: độ trễ, revocation và đồng nhất giữa các node

Mỗi request gọi AS introspection có thể tăng latency/tải. Cache `active=true` giúp hiệu năng nhưng tạo một **cửa sổ token bị revoke vẫn còn được RS nhận**.

### Ví dụ timeline

~~~text
10:00:00 AS phát opaque access token A1 (expires 10:05:00).
10:00:30 RS introspects A1 -> active=true.
10:00:30 RS caches active=true for 30 seconds.
10:00:35 User/security team revokes A1 at AS.
10:00:40 Attacker replays A1 against RS.
         RS may use cached active=true until 10:01:00.
10:01:01 RS introspects again -> active=false.
         RS rejects A1.
~~~

**RFC 7662 cho phép RS cache introspection response với cân nhắc bảo mật**, nhưng **không được cache vượt token `exp` khi `exp` được cung cấp**. Không dùng cache không thời hạn hoặc tự mở rộng TTL vì AS outage.

### TTL policy minh họa

\[
TTL_{\mathrm{cache}} =
\max\left(0,\min\left(
TTL_{\mathrm{configured}},
T_{\mathrm{exp}} - T_{\mathrm{now}} - \Delta
\right)\right)
\]

`Δ` là safety margin phù hợp clock skew/network; nếu AS không cung cấp `exp`, cần **policy riêng cho token type/issuer** và TTL conservative. Độ dài TTL phải được chọn theo **revocation propagation SLO**: muốn chặn trong 10 giây thì một cache `active=true` trong 60 giây mà không có invalidation **không đáp ứng**.

### Những yếu tố phải nằm trong cache scope

~~~text
IntrospectionCacheKey {
  tokenDigest: HMAC(cacheSecret, accessTokenBytes)
  trustedAs: "https://auth.example.test"
  rsIdentity: "invoice-api"
  tokenProfile: "opaque-access-v1"
  policyVersion: "v3"
}
~~~

- Không đặt **raw access token** làm cache key bị xuất ra logs/metrics.
- Introspection có thể trả **claims khác nhau tùy quyền của caller RS**; cache phải phân vùng theo AS/RS identity và contract.
- Positive-cache `active=true` giữ thông tin nhạy cảm (`sub`, scopes, tenant) nên phải có ACL, encryption-at-rest nếu cần, TTL và audit.
- Negative-cache `active=false` có thể giúp chống DoS, nhưng không nên cache quá lâu nếu hệ thống có semantics token activation khác hoặc risk policy không cho phép; tránh tạo oracle cho attacker.
- Nếu revoke event tới RS sau một response đang bay về, phải tránh **stale active=true ghi đè terminal revoke state**.

### Cache expiry khác token expiry

~~~text
Token expires at 10:05.
Cache active response expires at 10:01.

After 10:01:
  RS must introspect again (or reject if policy requires fresh status).

After 10:05:
  RS must reject even if stale cache incorrectly says active=true.
~~~

Nếu request bắt đầu ngay trước expiry rồi xử lý kéo dài, transaction authorization có thể cần đánh giá thêm tại commit tùy nghiệp vụ; **token `exp` không tự rollback một nghiệp vụ đang chạy**.

## 13. Xử lý lỗi: `401`, `403`, `429`, `503` và `active=false`

Từ chối token và từ chối quyền là hai loại sự kiện khác nhau. Trong nhiều trường hợp:

| Tình huống | Hành động RS phù hợp | Giải thích |
|---|---|---|
| Không có Bearer token cho route protected | **401 Unauthorized** với Bearer challenge | Cần authentication |
| JWT signature sai/alg không cho phép | **401 `invalid_token`** | Token không hợp lệ |
| JWT hết `exp`/`nbf` chưa tới | **401 `invalid_token`** | Timing validation fail |
| JWT sai `iss`/`aud`/token type | **401 `invalid_token`** | Token không dành RS này |
| Opaque introspection trả `active=false` | **401 `invalid_token`** | AS không coi token active |
| JWT/introspection hợp lệ, thiếu scope | **403 `insufficient_scope`** khi phù hợp | Đã authenticated nhưng không đủ quyền |
| Authenticated, thiếu quyền trên object/tenant | **403** hoặc **404** theo privacy/resource policy | Không phơi bày tài nguyên của người khác |
| AS introspection 401 do RS secret sai | **Fail closed**, thường lỗi upstream/`503` và alert | **Không** coi RS credential error là token inactive hoặc active |
| AS introspection 429/timeout/5xx | **Fail closed**, `503` nếu validation unavailable theo API contract | Không cho request qua vì AS lỗi |
| JWKS unavailable nhưng key cached còn hợp lệ | Có thể tiếp tục verify JWT với trusted cache theo policy | Không fetch arbitrary key |
| JWKS/key mới chưa xuất hiện | Reject token chưa verify, alert rotation issue | Không bỏ kiểm JWS |
| DPoP/mTLS proof thiếu/sai | Reject theo sender-constrained profile | Access token active không đủ |

### Bearer challenge

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="invoice-api", error="invalid_token"
Cache-Control: no-store
~~~

Đối với thiếu scope:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="invoice-api", error="insufficient_scope", scope="invoice:read"
~~~

Các header minh họa theo **RFC 6750**; thực tế server nên tránh lộ quá nhiều chi tiết về account/token và tuân API security policy. Nếu introspection service bị lỗi, **không báo chính xác token đó đã revoked** khi không có bằng chứng `active=false`; phân loại là validation unavailable và alert operations.

### Vì sao `active=false` không giống HTTP 401 từ AS?

~~~text
Introspection HTTP 200:
  {"active": false}
  -> AS evaluated token and says inactive.

Introspection HTTP 401:
  RS failed to authenticate to AS, or unauthorized to introspect.
  -> No trustworthy token state obtained.
  -> Must NOT infer active or inactive solely from this HTTP status.
~~~

AS và RS cần thiết kế retry/backoff, rate limiting và circuit breaker hợp lý. Retry không được vô hạn, không đặt raw tokens vào retry queue/logs, và không tăng TTL của stale `active=true` vượt security policy.

## 14. Java/Spring: kiểm audience và issuer từ introspection principal

Spring Security tách việc **lấy kết quả introspection** khỏi **authorization policy của RS**. Sau khi một delegate introspector đã liên hệ AS và xử lý `active`, RS có thể dùng decorator để buộc các claims theo contract của **Invoice API**.

### Một `OpaqueTokenIntrospector` decorator minh họa

~~~java
import java.time.Clock;
import java.time.Instant;
import java.util.Collection;
import java.util.Objects;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

final class InvoiceClaimsCheckingIntrospector
        implements OpaqueTokenIntrospector {

    private final OpaqueTokenIntrospector delegate;
    private final Clock clock;

    InvoiceClaimsCheckingIntrospector(
            OpaqueTokenIntrospector delegate,
            Clock clock) {
        this.delegate = Objects.requireNonNull(delegate);
        this.clock = Objects.requireNonNull(clock);
    }

    @Override
    public OAuth2AuthenticatedPrincipal introspect(String token) {
        // Delegate phải xác thực với đúng AS và từ chối active=false.
        OAuth2AuthenticatedPrincipal principal =
            delegate.introspect(token);

        // Contract ví dụ: AS bắt buộc trả iss, aud, exp.
        Object issuer = principal.getAttribute("iss");
        Object audience = principal.getAttribute("aud");
        Object expires = principal.getAttribute("exp");

        if (!"https://auth.example.test".equals(issuer)) {
            throw invalidToken("Unexpected token issuer");
        }
        if (!containsAudience(audience, "invoice-api")) {
            throw invalidToken("Unexpected token audience");
        }

        Instant expiry = normalizeExpiry(expires);
        if (expiry == null || !clock.instant().isBefore(expiry)) {
            throw invalidToken("Expired or unbounded token");
        }

        // Delegate / framework mapping có thể cung cấp SCOPE_...;
        // service/controller vẫn phải kiểm invoice ownership.
        return principal;
    }

    private static boolean containsAudience(
            Object value, String expected) {
        if (value instanceof String s) {
            return expected.equals(s);
        }
        if (value instanceof Collection<?> values) {
            return values.contains(expected);
        }
        return false;
    }

    private static Instant normalizeExpiry(Object raw) {
        if (raw instanceof Instant instant) {
            return instant;
        }
        if (raw instanceof Number numericDate) {
            return Instant.ofEpochSecond(numericDate.longValue());
        }
        return null;
    }

    private static OAuth2AuthenticationException invalidToken(
            String detail) {
        return new OAuth2AuthenticationException(
            new OAuth2Error("invalid_token", detail, null));
    }
}
~~~

**Đây là ví dụ về adapter, không phải toàn bộ introspection implementation.** Nó yêu cầu **AS contract cụ thể** trong đó `iss`, `aud` và `exp` đều có mặt (dù RFC 7662 cho phép một số claims tùy chọn). Nếu AS không trả đủ, hãy **sửa hợp đồng hoặc dùng một cơ chế authoritative khác**, không bỏ qua audience/isolation chỉ để request chạy.

### Các giới hạn cần kiểm kỹ

1. **`delegate.introspect(token)` phải thực sự gọi đúng AS, dùng TLS, xác thực RS và loại `active=false`**. Không viết delegate tự trả fake principal từ JSON client.
2. **Number `exp` dùng Unix seconds**; tùy version/framework, claim có thể được normalize thành `Instant`, kiểu số hoặc kiểu khác. **Không chấp nhận mọi String tự parse thành thời gian** nếu chưa có schema.
3. Đoạn `normalizeExpiry` phục vụ minh họa; nếu provider dùng fractional NumericDate, schema/precision và overflow phải được xử lý chặt hơn.
4. Code không kiểm `scope` theo route, `token_type`/`client_id`, tenant, proof-of-possession hoặc tình trạng revoke đến muộn sau khi cache. Các bước đó cần thêm.
5. Khi cần leeway, AS/RS phải có contract và clock synchronization; ví dụ cố ý **strict now before exp**, không cộng grace period vô hạn.
6. Thông điệp exception chi tiết chỉ phục vụ minh họa; production có thể cần thông báo `invalid_token` chung cho caller và ghi audit nguyên nhân đã khử nhạy cảm.
7. Custom bean `OpaqueTokenIntrospector` phải được wiring đúng vào Spring OAuth2 Resource Server; **không tạo circular bean** khi wrap bean mặc định. Đảm bảo không vô tình có thêm một filter chain cho JWT nhận sai route.

### Adapter nên giải quyết cái gì, authorization layer giải quyết cái gì?

~~~text
Introspector/decorator:
  token active, issuer, audience, exp, token class,
  trusted claims normalization, optional client policy.

SecurityFilterChain method authorization:
  SCOPE_invoice:read, SCOPE_invoice:write.

Application service/repository:
  invoice belongs to subject/tenant;
  actor delegation matches business rules;
  transaction allowed under domain policy.
~~~

**Không nhét toàn bộ logic phân quyền hóa đơn vào introspection HTTP client**. Token validation phải dùng được giữa các routes, còn quyền object/business thay đổi theo request/resource cụ thể.

## 15. Một ứng dụng phải nhận cả JWT và opaque token thì thiết kế ra sao?

Tình huống thường gặp:

~~~text
/api/public-invoices/**:
  JWT access token issued by AS A.

/api/payroll/**:
  opaque reference token issued by AS B.

Same Spring process:
  2 trust profiles; different issuer, audience, token format,
  scopes, introspection endpoint and authorities.
~~~

**Không nên viết “JWT có 3 đoạn ⇒ decode offline; không thì introspect” làm chính sách xác thực mặc định.** Attacker kiểm chuỗi token có thể ép một request đi nhánh validation dễ dãi hơn (**format/downgrade confusion**).

### Phương án A: tách service/route và SecurityFilterChain

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
class TwoTokenProfiles {
    @Bean
    @Order(1)
    SecurityFilterChain jwtRoutes(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/jwt-api/**")
            // Chỉ cho routes Bearer-header-only, không có cookie auth.
            .csrf(csrf -> csrf.disable())
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .oauth2ResourceServer(rs -> rs.jwt(withDefaults()));
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain opaqueRoutes(HttpSecurity http)
            throws Exception {
        http
            .securityMatcher("/opaque-api/**")
            // Không áp dụng nếu một route dùng session/refresh cookie.
            .csrf(csrf -> csrf.disable())
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .oauth2ResourceServer(rs -> rs.opaqueToken(withDefaults()));
        return http.build();
    }

    @Bean
    @Order(3)
    SecurityFilterChain remainingRoutes(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth.anyRequest().denyAll());
        return http.build();
    }
}
~~~

**Chỉ là cấu trúc routing minh họa**. Mỗi chain cần chính sách **scope/role**, session/CSRF thích hợp, CORS, rate limits và đúng decoder/introspector beans. Một ứng dụng **đang thực sự có cả hai profiles** có thể cần cấu hình `JwtDecoder` và `OpaqueTokenIntrospector` tường minh thay vì dựa vào Boot auto-configuration; kiểm kỹ matcher precedence và tránh conflicts với các security chains có sẵn.

### Phương án B: lựa chọn theo trusted issuer/resource registration

Trong một API gateway hoặc token-validation service đa issuer, có thể chọn verifier theo **định tuyến trusted context** hoặc một **allowlisted issuer registry**:

~~~text
Trusted route /api/invoice/**:
  expected issuer AS-A
  expected token profile JWT RS256
  expected audience invoice-api

Trusted route /api/payroll/**:
  expected AS-B introspection endpoint
  expected token profile opaque reference
  expected audience payroll-api

Caller cannot choose validation mode by:
  ?tokenType=opaque
  X-Validation-Mode: skip-jwt
  JWT header alg/kid from untrusted token
~~~

Nếu cần hỗ trợ **nhiều issuer trên cùng route**, sử dụng Spring/OAuth architecture như `AuthenticationManagerResolver` với **trusted issuer allowlist** và tách grant/policy rõ; không cho một attacker tự khai issuer bất kỳ rồi RS tự lấy JWKS/introspection endpoint qua Internet.

### Hai token validation modes không đồng nghĩa hai security levels

Một JWT issuer A và opaque issuer B có thể có metadata claims và semantics khác nhau. Không map:

~~~text
AS-A scope "admin"  ==  AS-B scope "admin"
~~~

trừ khi có chính sách quyền chung đã được review. Nên normalize vào domain permissions theo issuer/client/resource, không sao chép tùy ý authority names xuyên security domains.

## 16. DPoP, mTLS: `JwtDecoder`/introspection không tự chống Bearer replay

**Chữ ký JWT hợp lệ** và **introspection `active=true`** đều có thể xảy ra với **bản sao Bearer access token**. Nếu attacker sao chép chuỗi token, họ có thể dùng nó trong thời gian hiệu lực nếu RS không yêu cầu proof người gửi.

~~~text
10:00 AS issues access token A1, expires 10:05.
10:01 Attacker obtains A1 from a diagnostic log.
10:02 Attacker sends Authorization: Bearer A1.

JWT RS offline:
  signature/claims valid -> may accept without sender proof.

Opaque RS introspection:
  AS returns active=true -> may accept without sender proof.
~~~

### DPoP (RFC 9449)

Với **DPoP-bound token**, AS có thể ràng buộc token với public key thumbprint qua `cnf.jkt`. RS kiểm DPoP proof **cho từng HTTP request**:

~~~http
GET /api/invoices/INV-42 HTTP/1.1
Host: invoice.example.test
Authorization: DPoP <access-token>
DPoP: <signed-proof-jwt>
~~~

RS cần verify:

- Chữ ký DPoP proof với public key và thumbprint khớp `cnf.jkt` của token/introspection metadata.
- `htm` khớp HTTP method, `htu` khớp URI mục tiêu theo normalization rules.
- `iat` tươi mới và `jti` không bị reuse trong replay window, nonce nếu server yêu cầu.
- `ath` khớp hash access token đang được trình tại RS.
- Access token vẫn đúng issuer/audience/expiry/scope và object permission.

**Spring Security JWT decoder hoặc opaque introspector chỉ giải quyết một phần token validation.** Không giả định chỉ bật `oauth2ResourceServer().jwt()` hoặc `opaqueToken()` là mặc nhiên có **DPoP proof verification**. Cần extension/component phù hợp profile và phiên bản security framework.

### mTLS certificate-bound token (RFC 8705)

Khi AS cấp token ràng buộc với client certificate, `cnf.x5t#S256` mô tả certificate thumbprint. RS phải kiểm **chứng chỉ thực sự xuất hiện trong TLS client authentication** hoặc thông tin do **trusted ingress** thiết lập có bảo vệ, so với binding token.

Nếu TLS terminate ở gateway, backend không được tin `X-Client-Cert` do public client tự gửi; gateway phải **strip/overwrite headers**, xác thực certificate và bảo vệ đường truyền tới backend bằng trust boundary chặt.

### Short lifetime và revocation vẫn cần thiết

DPoP/mTLS giảm tác hại của **token string bị sao chép đơn lẻ**, nhưng không tự chữa XSS/lộ signing key, không mở thêm quyền và không thay `exp`/revocation policy. Một access token sender-constrained vẫn có thể bị dùng nếu kẻ tấn công có cả token và private key/chứng chỉ phù hợp.

## 17. Cache JWKS khác cache introspection

Hai cache trông giống “giảm gọi AS” nhưng **lưu hai loại dữ liệu và có rủi ro khác nhau**:

| Cache | Chứa gì? | Vấn đề chính |
|---|---|---|
| **JWKS public key cache** | AS public verification keys và metadata tin cậy | Không nhận key mới khi rotate, giữ trust key bị compromise quá lâu |
| **Introspection response cache** | Token `active` và claims/scope/audience tương ứng | Revoked token còn bị coi `active=true`, claims nhạy cảm bị lưu quá lâu |
| **Authorization decision cache** | Quyết định user/client được phép object/action | Ownership/roles/tenant hoặc payment policy thay đổi mà cache stale |

### JWKS cache không làm JWT hết hiệu lực

Khi AS revoke một JWT access token trong token store nhưng RS chỉ kiểm signature bằng **JWKS cache**, RS không tự biết `jti` đã revoked. Kéo JWKS về mỗi request cũng **không** giúp nếu public signing key vẫn hợp lệ: **key trust khác token state**.

### Introspection cache không bảo vệ nếu thiếu audience

Một RS cache `active=true` chung cho mọi APIs có thể vô tình chấp nhận token của audience khác. Cache key/trust context phải kết hợp **AS, RS, token digest, policy**; sau cache hit vẫn kiểm metadata và route authorization.

### Authorization decision cache không thay token validation

Ngay cả khi hệ thống cache `user:an canReadInvoice:42=true`, một request dùng token đã hết `exp` hoặc bị revoke phải bị từ chối. Business ACL cache có TTL/eviction riêng và phải kiểm correlation với subject/tenant và thời điểm quyết định.

## 18. Tối ưu hiệu năng mà không phá security contract

Một RS xử lý 10.000 requests/giây sẽ có những cân nhắc khác nhau:

~~~text
JWT offline:
  validate signature/claims locally
  cache trusted JWKS, not raw credentials
  cost: crypto CPU, key rotation and revoke propagation

Opaque introspection:
  validate token at AS
  cost: network RTT, AS capacity, auth and caching
  benefit: central token state at check time
~~~

### Các kỹ thuật

1. **JWT:** Dùng cryptography library đã được kiểm; allowlist algorithms; cache trusted JWKS theo metadata/policy; không fetch JWKS mỗi request.
2. **Opaque:** Dùng HTTP client connection pooling, timeouts, concurrency limits, rate limits và retry budget; không gửi token vào telemetry.
3. **Cache introspection:** TTL ngắn/không vượt `exp`, phù hợp revoke SLO; invalidate khi có revoke events và bảo vệ claims trong cache.
4. **Resilience:** Circuit breaker và error budget, nhưng **không fail open** khi AS không có response đáng tin.
5. **Load shedding:** Giới hạn introspection concurrency để AS không bị overload do attacker gửi hàng nghìn bearer strings không tồn tại.
6. **Consistent authorization:** Scope/tenant/object checks sau token authentication, kể cả cache hit.
7. **Testing:** Benchmark p50/p95/p99 cho các loại tokens, kiểm key rotation, AS outage và revoked-token acceptance window.

### Không giả định JWT luôn “không chạm AS”

JWT decoder vẫn có thể gọi AS/JWKS endpoint khi chưa có key, cache hết hạn hoặc issuer key rotate. “Offline validation” nghĩa là **không cần hỏi AS về trạng thái của từng token trong đường request thông thường**, không có nghĩa **hoàn toàn không phụ thuộc key distribution**.

### Không dùng introspection làm cơ chế trả toàn bộ user profile

Chỉ đưa các claims RS cần để quyết định token và authorization; AS không nên trả toàn bộ PII/consent history/credentials. Một introspection endpoint có thể kiểm quyền caller RS để giới hạn response; log và cache cần tuân chính sách data minimization.

## 19. Những sai lầm khiến Resource Server chấp nhận token nguy hiểm

| Sai lầm | Tấn công/lỗi có thể xảy ra | Cách khắc phục |
|---|---|---|
| Chỉ Base64 decode JWT, không verify signature | Attacker tự khai `sub=admin` | JwtDecoder thật với trusted alg/key |
| Dùng `alg` từ token để chọn bất kỳ verifier | Algorithm confusion/downgrade | Pin allowed algorithms từ registration |
| Tải JWKS từ `jku` trong token | SSRF/key substitution | Trusted JWKS URI/issuer allowlist |
| So `iss` bằng substring/suffix | Token từ issuer giống tên được nhận nhầm | Exact issuer matching |
| Không kiểm `aud` | Token dành cho API khác được nhận | Expected audience exact membership |
| Không kiểm token purpose | ID token dùng như API access token | Profile/`typ`/issuer/token class validation |
| Tin `scope` từ body/query | Attacker tự nâng quyền | Chỉ dùng verified JWT/introspection claims |
| So scope bằng substring | `invoice:read-all` khớp `invoice:read` sai | Split scope và exact match |
| JWT hết hạn nhưng leeway lớn | Token cũ replay kéo dài | Clock sync, skew nhỏ và boundary tests |
| Chỉ tin `active=true` | Sai audience/object/tenant vẫn được cho qua | RS authorization checks |
| HTTP 200 introspection = active | AS trả `{"active":false}` vẫn được nhận | Parse Boolean `active` đúng |
| HTTP 401 introspection = invalid token đơn giản | Che AS credential/config lỗi | Fail closed + operational alert |
| AS timeout → allow request | Bỏ authentication khi hệ thống yếu | Cache hợp lệ theo policy hoặc 503 |
| Cache active=true quá `exp` | Expired token được nhận | Cache TTL bounded by exp |
| Cache introspection cross-audience | Token của RS khác được dùng | Cache key includes trusted RS context |
| Negative introspection response bị dùng như principal | Principal giả được tạo | Chỉ tạo authenticated principal từ active=true |
| `client_id` bị coi là `sub` | Workload bị gán thành user | Phân biệt grant/actor/user delegation |
| Không kiểm owner/tenant/object | IDOR/BOLA | Object-level authorization |
| Một decoder chung tin mọi issuer trên Internet | Unknown issuer accepted/SSRF | Allowlisted issuer registry |
| JWT route fallback opaque introspection tùy token | Token format downgrade | Profile routing dựa trusted config |
| RS introspection secret hardcode | Lộ credential truy cập AS | Secret manager, IAM, rotation |
| Raw Bearer token trong logs/cache keys | Token theft/replay | Redaction/HMAC digest/secure cache |
| DPoP token được nhận như Bearer | Proof-of-possession bị vô hiệu | DPoP-bound checks bắt buộc |
| mTLS thumbprint từ HTTP header caller | Client giả certificate binding | Trusted ingress và TLS client auth |
| Logout cookie xong tin access token đã chết | JWT offline có thể vẫn sống | Revoke/denylist/introspection policy |
| RS không xử lý key rotation | Tokens mới bị 401, người dùng gián đoạn | Trusted JWKS refresh, rollout planning |
| Thêm `JwtDecoder` custom nhưng làm mất validators | Issuer/expiry bypass | Compose full validator chain |
| Spring `permitAll()` vô tình áp route API | API không cần token | Deny-by-default route security |
| Cookie token và Bearer header cùng tồn tại không kiểm | CSRF/auth confusion | Rõ credential source và CSRF guard |
| Rate limit chỉ dựa `sub` chưa verify | Attacker điều khiển sub/DoS | Verify trước, dùng trusted keys/identity |

**Một lỗi nhỏ ở boundary token validation có thể phá toàn bộ tầng authorization.** Phải có negative tests để bảo đảm những thông tin do attacker kiểm soát không trở thành authority.

## 20. Ma trận kiểm thử JWT decoder và opaque introspection

Thiết lập kiểm thử:

~~~text
Trusted Authorization Server: https://auth.example.test
Trusted JWKS:                 https://auth.example.test/oauth2/jwks
Resource Server:              invoice-api
Required read scope:          invoice:read
User:                         user:an
Invoice owner:                user:an

JWT profile:
  accepted alg: RS256
  expected issuer: https://auth.example.test
  expected audience: invoice-api
  access token max lifetime: 5 min (policy minh họa)

Opaque profile:
  introspection-uri: https://auth.example.test/oauth2/introspect
  RS client credential: securely provisioned
  expected active=true, aud=invoice-api, issuer trusted
  positive cache TTL: 20 s (ví dụ)
~~~

| Ca kiểm thử | Dữ liệu/tình huống | Kết quả cần đạt |
|---|---|---|
| **JWT đúng profile** | RS256/JWKS đúng, `iss/aud/exp/scope` hợp lệ | Qua authentication, tiếp tục object authorization |
| **JWT thiếu chữ ký** | Attacker tạo 2 segments hoặc `alg=none` | Reject, không chấp nhận unsigned JWT |
| **JWT chữ ký sai** | Thay một byte payload | Reject `invalid_token` |
| **JWT ký bằng key khác** | Public key attacker tự đưa | Reject |
| **`kid` không thuộc trusted JWKS** | Header tham chiếu key lạ | Reject, không remote-fetch theo input |
| **`jku`/`x5u` attacker** | Header có URL ngoài allowlist | Không SSRF/không dùng attacker key |
| **`alg` HS256 trong profile RS256** | Algorithm confusion attempt | Reject |
| **JWT malformed header** | JSON sai cấu trúc | Reject |
| **JWT số segment bất thường** | 4 hoặc 5 segments cho JWS expected | Reject theo token profile, không fallback opaque |
| **JWE gửi nhầm JWS route** | Token mã hóa nhưng JWT decoder không hỗ trợ | Reject/định tuyến đúng profile; không bỏ verify |
| **JWT `iss` sai** | Issuer khác dù chữ ký được verify bằng key nhầm | Reject exact issuer |
| **JWT `iss` dạng giống tên** | `https://auth.example.test.evil.invalid` | Reject, không substring |
| **JWT `aud` sai** | `payroll-api` | Reject |
| **JWT `aud` có nhiều entries** | Mảng chứa `invoice-api` theo profile được phép | Chấp nhận audience nếu contract cho phép, tiếp tục kiểm khác |
| **JWT thiếu `aud`** | Payload không có resource audience | Reject |
| **JWT thiếu `exp`** | Token không có expiry trong access-token profile | Reject theo contract |
| **JWT hết hạn** | `now >= exp`, skew=0 | Reject |
| **JWT `nbf` tương lai** | Not-before chưa đạt | Reject |
| **JWT `iat` tương lai sai** | Issued-at ngoài tolerance | Reject theo policy |
| **JWT lifetime quá dài** | `exp - iat` vượt 5 phút | Reject theo max-lifetime policy |
| **Clock lệch giữa replicas** | RS A chấp nhận, RS B từ chối cùng token ngoài skew | Test fail, đồng bộ thời gian |
| **JWT ID token dùng làm access token** | `aud=invoice-web` hoặc sai `typ` | Reject token purpose/audience |
| **JWT refresh token gửi API** | Token khác loại nhưng có claims | Reject token type |
| **JWT scope đúng** | `invoice:read` có mặt | Qua scope check, tiếp tục object ACL |
| **JWT scope thiếu** | Chỉ `invoice:export` | `403 insufficient_scope` |
| **JWT scope substring** | `invoice:read-all` vs `invoice:read` | Không match substring |
| **JWT scope từ body** | Caller gửi `{"scope":"admin"}` | Không nâng quyền từ input |
| **JWT subject sai** | Token thuộc Bình, invoice của An | Reject theo object-level permission |
| **JWT tenant sai** | `tenant=B` trong request tenant A | Reject |
| **JWT client credentials** | Token của service không có end-user | Chỉ áp workload authorization, không gán user giả |
| **JWT revoked nhưng chưa hết hạn** | RS chỉ offline verify và không có revoke state | Test chứng minh cửa sổ acceptance; phải có mechanism nếu SLO yêu cầu |
| **JWT JWKS key mới** | AS rotate đúng quy trình | RS refresh trusted JWKS rồi verify được |
| **JWT key cũ bị compromise** | RS vẫn cache public key | Incident policy phải khóa trust và revoke/denylist khi cần |
| **JWT JWKS unreachable** | Trusted key đã cache còn hợp lệ | Verify theo cache/key policy, không fail open cho unknown kid |
| **Opaque token active** | AS returns valid `active=true` + required claims | Qua authentication rồi kiểm quyền |
| **Opaque `active=false`** | AS HTTP 200 body inactive | Reject 401 |
| **Opaque unknown token** | Introspection trả `active=false` | Reject, không lộ token tồn tại hay không |
| **Opaque đã expired** | AS trả `active=false` hoặc `exp` quá hạn | Reject |
| **Opaque đã revoked** | AS cập nhật token state | Introspection mới trả inactive; RS từ chối |
| **Opaque `active="true"`** | JSON string thay boolean | Reject schema, không ép chuỗi thành true |
| **Opaque thiếu `active`** | AS JSON không có field | Reject, không default true |
| **Opaque `active=null`** | Không phải boolean | Reject |
| **Opaque response malformed** | HTML/JSON sai/thiếu Content-Type theo contract | Reject/operational error |
| **Opaque HTTP 200** | Body `active=false` | Không coi status 200 là token active |
| **Opaque introspection HTTP 401** | RS credential sai | Fail closed, alert config, không cho request qua |
| **Opaque introspection HTTP 403** | RS không có quyền introspect | Fail closed, alert permission |
| **Opaque introspection 429** | AS throttling | Fail closed hoặc valid cache theo policy, backoff |
| **Opaque introspection 5xx** | AS lỗi | Không biến lỗi thành active=true |
| **Opaque introspection timeout** | Không biết trạng thái token | Fail closed/503 theo contract |
| **Opaque TLS/certificate lỗi** | Endpoint AS bị MITM hoặc certificate sai | Fail closed |
| **Opaque RS credential leak** | Attacker có introspection client secret | Rotate/contain, hạn quyền và audit |
| **Opaque wrong audience** | `active=true` nhưng `aud=payroll-api` | Reject |
| **Opaque missing mandatory audience** | AS không trả `aud` nhưng route yêu cầu | Reject hoặc sửa AS/RS contract |
| **Opaque issuer mismatch** | `iss` khác trusted issuer | Reject |
| **Opaque no issuer by contract** | AS không trả `iss`, nhưng endpoint pin trong registry | Chỉ được dùng nếu contract/trust policy có thay thế rõ |
| **Opaque scope string** | `"invoice:read invoice:export"` | Split exact tokens |
| **Opaque scope malformed** | Array khi contract yêu cầu string | Reject hoặc normalize theo contract explicit |
| **Opaque `aud` string** | `"invoice-api"` | Exact match |
| **Opaque `aud` list** | `["invoice-api","search-api"]` | Membership exact và policy multi-aud |
| **Opaque `exp` kiểu sai** | ISO string thay NumericDate/Instant expected | Reject schema, không tự đoán |
| **Opaque cache còn `active=true` sau revoke** | Cache TTL 20 s | Đo revocation lag và SLO; không tuyên bố instant |
| **Opaque cache quá `exp`** | RS cố nhận token sau expiry vì cache | Reject, test fail khi vượt exp |
| **Opaque cache cross-RS** | RS B dùng cache response dành RS A | Reject, cache key/context isolation |
| **Opaque stale response race** | Revoke event rồi response active cũ tới muộn | State không bị active=true ghi đè |
| **Opaque cache rò thông tin** | Claims/raw token ở metrics/shared Redis | Security/privacy test fail |
| **Opaque token dùng ở JWT route** | Token không có JWS signature | Reject theo profile |
| **JWT dùng ở opaque-only route** | AS introspection của route không chấp nhận | Reject, không tự fallback local decode |
| **DPoP-bound token không proof** | Token valid nhưng proof thiếu | Reject |
| **DPoP proof dùng lại** | Trùng `jti` trong proof replay window | Reject |
| **DPoP `ath` không khớp** | Proof thuộc token A2, request gửi A1 | Reject |
| **mTLS certificate sai** | Token bound cert khác | Reject |
| **BFF cookie route không CSRF** | Browser tự gửi session cookie | Security test fail; thêm CSRF guard |
| **401 vs 403** | Token không hợp lệ vs thiếu scope | Error taxonomy đúng, không lộ claims |
| **Authorization by object** | Token hợp lệ nhưng user không có quyền Invoice 42 | Reject ở service/repository |
| **Token trong logs** | Authorization header xuất hiện trong APM | Redaction test fail |
| **Unknown issuer multi-tenant** | Token tự khai issuer mới | Không auto-fetch JWKS, reject |
| **Wrong JWT converter mapping** | `role=admin` tự ý map thành `ROLE_ADMIN` | Reject/mapping theo issuer trust profile |

### Test concurrency và failover

~~~text
Test A — introspection revoke race:
  T0: RS starts introspection for A1.
  T1: AS revokes A1, RS receives revoke event.
  T2: earlier HTTP response active=true arrives.
  Assert: old response cannot overwrite terminal revoke state.

Test B — JWT key rotation across replicas:
  T0: AS publishes new key K2.
  T1: RS-1 cached K2; RS-2 still has K1 only.
  T2: AS starts signing K2.
  Assert: rollout strategy prevents unexpected valid-token outage.

Test C — introspection AS outage:
  T0: RS cache has active=true with TTL 10 seconds.
  T1: AS unreachable.
  T2: cached entry expires.
  Assert: RS does not extend active=true indefinitely.

Test D — cross-audience cache:
  T0: RS-A introspects A1 under its credentials.
  T1: RS-B receives same A1 but expected audience differs.
  Assert: RS-B cannot blindly reuse RS-A decision.
~~~

### Kiểm thử tích hợp cần đo điều gì?

Ngoài HTTP response, phải **kiểm dữ liệu không bị thay đổi** khi token bị từ chối, không có downstream call phát sinh khi authentication fail, raw token không rơi vào log, và latency/key-rotation/revocation SLO đáp ứng mục tiêu. Một test chỉ assert `401` mà API vẫn ghi database trước đó **chưa đạt**.

## 21. Tình huống thực hành: Invoice API chuyển từ JWT sang opaque token

Một doanh nghiệp có:

~~~text
AS: https://auth.example.test
Invoice API: audience invoice-api
Invoice Web: client_id invoice-web
Required scope: invoice:read
Access-token TTL: 5 phút
Authorization logic: tenant + invoice owner

Trước migration:
  AS cấp JWT RS256, RS JwtDecoder verify offline.

Sau migration:
  AS cấp opaque reference token, RS introspects qua RFC 7662.

Yêu cầu security:
  Logout/account lock phải chặn token ở API trong tối đa 15 giây.
~~~

**Câu 1. Vì sao JWT decoder không tự đáp ứng revoke SLO 15 giây?**

Vì JWT signature và `exp` **không mang trạng thái revoke động**. Một JWT phát trong 5 phút có thể còn được RS kiểm offline cho tới expiry. Cần denylist/introspection/event enforcement hoặc thay token design.

**Câu 2. Chuyển sang opaque token có bảo đảm revoke tức thì không?**

Không. AS có thể trả `active=false` sau revoke, nhưng RS có thể đang cache `active=true`. Nếu cache TTL 60 giây và không có invalidation, **không đáp ứng SLO 15 giây**. Cần cache policy/event push phù hợp và đo thực tế.

**Câu 3. Nếu introspection trả HTTP 200 với `{"active":false}`, API nên làm gì?**

Từ chối access token, thường `401 invalid_token`. Không coi HTTP 200 là xác nhận token được phép.

**Câu 4. Nếu AS introspection HTTP 401 vì RS client secret hết hạn, có coi token user không hợp lệ không?**

Không suy được token state. RS authentication tới AS đã thất bại, nên API phải **fail closed**, alert credential/config và trả lỗi dịch vụ phù hợp cho caller theo contract.

**Câu 5. Nếu AS trả `active=true` và `scope=invoice:read` nhưng `aud=payroll-api`, có được dùng không?**

Không. RS phải kiểm audience đúng Invoice API. Scope không thay resource binding.

**Câu 6. Nếu AS trả `active=true` nhưng không có `aud` thì sao?**

Theo RFC 7662, metadata này có thể tùy chọn. Nhưng nếu security contract của Invoice API yêu cầu audience, **không được tự coi thiếu aud là universal token**. Cần sửa AS contract hoặc có phương án authoritative alternate đã đăng ký.

**Câu 7. Nếu user An có token hợp lệ nhưng gọi Invoice của Bình?**

Từ chối nếu không có delegation/entitlement. `JwtDecoder` hoặc introspection chỉ xác thực token; quyền trên **từng object** do Invoice API thực thi.

**Câu 8. Một token có dấu chấm nên tự động đưa vào JwtDecoder, token khác thì introspect được không?**

Không nên. Format sniffing bằng input attacker là **điểm downgrade/confusion**. Routing nên dựa vào trusted issuer/resource/token profile registration hoặc SecurityFilterChain tách biệt.

**Câu 9. Nếu attacker có bản sao opaque access token đang active, introspection có ngăn attacker không?**

Không tự động. Với **Bearer** token, attacker có thể dùng bản sao cho tới khi token bị revoke/hết hạn, trừ khi RS yêu cầu sender-binding. Opaque chỉ làm token khó đọc claims, không ngăn replay.

**Câu 10. DPoP giúp gì khi attacker chỉ sao chép token string?**

Token có `cnf.jkt` và request yêu cầu DPoP proof hợp lệ, nên attacker thiếu private key không tự tạo proof mới được. RS phải kiểm proof **ngoài** decoder/introspector.

**Câu 11. Có thể cache introspection response đến `exp` để giảm tải AS không?**

Không mặc nhiên. Cache quá dài có thể vi phạm **revoke-lag SLO**. TTL phải thỏa đồng thời token expiry, security SLO, cache-control/AS contract và khả năng invalidation.

**Câu 12. JWT `kid` mới mà RS chưa lấy JWKS mới: có được bỏ signature check trong một phút không?**

Không. Phải reject token chưa verify được và khắc phục trusted key rollout/discovery. Không tự fetch khóa từ attacker-controlled URL hoặc fail open.

**Câu 13. Scope `invoice:read` được Spring map thành gì?**

Thông thường là authority `SCOPE_invoice:read` theo default mapping, nếu AS trả claims đúng format. Cần kiểm converter thực tế và ứng dụng vẫn kiểm tenant/object.

**Câu 14. Sau migration, log đang ghi toàn bộ HTTP body của introspection request: nguy cơ?**

Body chứa **raw access token**; nếu log bị lộ, attacker có credential để replay. Phải redact/không ghi payload, kiểm APM/proxy và xử lý rò token qua revoke/incident response.

**Câu 15. BFF dùng session cookie từ browser rồi tự gửi Bearer token sang Invoice API. CSRF có biến mất không?**

Không. Invoice API có thể chỉ nhận Bearer header, nhưng **BFF nhận cookie tự động gửi** nên cần CSRF guard ở BFF trước khi gọi API. Resource Server vẫn có quyền kiểm audience/scope/subject riêng.

## 22. Checklist triển khai `JwtDecoder` và opaque introspection

1. **Xác định token contract:** JWT access token, opaque reference hay JWE được AS/RS đăng ký rõ, không đoán bằng dấu chấm?
2. **Trusted issuer:** RS có issuer allowlist exact theo resource/tenant, không tin `iss` tự khai?
3. **Trusted JWKS URI:** Lấy từ registration/discovery đáng tin, chống SSRF qua `kid`/`jku`/`x5u`?
4. **JWS algorithm allowlist:** Không nhận `none`/alg lạ/algorithm confusion, key purpose đúng?
5. **Signature verification thật:** Dùng `JwtDecoder`/JOSE library, không chỉ Base64 decode?
6. **Issuer validation:** `iss` khớp AS đã đăng ký; nhiều issuer có trust registry cụ thể?
7. **Audience validation:** `aud` chứa đúng RS; token dành API khác không được dùng?
8. **Expiry/time:** `exp`, `nbf`, `iat` và clock skew được kiểm; max issued lifetime nếu policy yêu cầu?
9. **Token purpose/profile:** Không chấp nhận ID token hoặc refresh token tại RS; `typ`/RFC 9068 theo contract?
10. **Scope mapping:** `scope` hoặc `scp` đúng schema, map `SCOPE_*` chính xác, không substring/role escalation?
11. **Client/subject semantics:** Phân biệt user-delegated với client_credentials; không dùng `client_id` như end-user identity?
12. **Object authorization:** Tenant/owner/ACL/business permission được RS kiểm tại API boundary?
13. **Opaque introspection HTTPS:** POST form body, không đặt token trong URL, TLS AS verification nghiêm ngặt?
14. **Introspection credentials:** RS xác thực với AS bằng cơ chế được cấp quyền; secret manager/IAM/rotation và audit?
15. **`active` strict boolean:** Chỉ `true` mới qua, `false`/missing/null/string → reject?
16. **Opaque metadata schema:** Audience string/list, scope string, NumericDate, issuer và token type được kiểm theo AS contract?
17. **Không mặc định claims tùy chọn:** Thiếu aud/exp/scope cần fail theo policy hoặc có authoritative substitute rõ?
18. **Không tin HTTP 200:** Phải parse body; introspection 401/403/429/5xx không coi token active?
19. **Outage fail-closed:** Không bỏ kiểm token khi AS/JWKS unavailable; chỉ dùng trusted cache còn hợp lệ theo policy?
20. **Cache introspection an toàn:** Positive TTL bounded by `exp` và revoke SLO, per-RS policy key, revoke invalidation, stale race prevention?
21. **JWKS rotation:** Key mới được công bố trước phát, key cũ retire theo lifetime/incident, không bỏ verify để chữa outage?
22. **Denylist/introspection cho JWT nếu cần:** JWT offline không tự biết revoke trước `exp`; security SLO được đo?
23. **DPoP/mTLS sender binding:** Với `cnf`, RS xác minh proof/chứng chỉ request; không chỉ kiểm token signature/active?
24. **Bearer transport:** Ưu tiên `Authorization` header qua TLS, không raw token ở URL, log, analytics hoặc error trace?
25. **Không tự nhận JWT/opaque theo caller input:** Validation mode theo trusted route/issuer/resource policy?
26. **Spring FilterChain đúng matcher:** JWT/opaque routes tách bạch, order rõ, catch-all deny và không mở `permitAll()` sai?
27. **CSRF theo credential transport:** Routes Bearer-header-only khác BFF/cookie-authenticated; không disable CSRF cho session cookie routes?
28. **Decoder custom không bỏ validator:** `setJwtValidator` giữ issuer/timestamp/audience/purpose theo security requirements?
29. **Introspector custom đúng trust:** Delegate kiểm `active`/AS authentication; decorator chỉ map claims tin cậy và enforce policy?
30. **Error taxonomy:** 401 token invalid, 403 thiếu quyền, 503 validation service unavailable; không lộ token existence?
31. **Resilience/QPS:** JWKS caches, introspection connection pools/timeouts/backoff/rate limits và AS capacity được kiểm?
32. **Negative tests bắt buộc:** Wrong alg/kid/iss/aud/exp, token type, active=false, malformed JSON, outage, cache stale, DPoP replay, cross-tenant?
33. **Monitoring/privacy:** Log reason/category, issuer alias và correlation ID có ACL; không log tokens/introspection secrets/PII không cần?
34. **Incident playbook:** Key compromise, AS downtime, token theft, refresh/revoke propagation và cross-API token replay có runbook?

**Ghi nhớ:** **`JwtDecoder` xác minh JWT access token bằng chữ ký và các validators cấu hình; `OpaqueTokenIntrospector` hỏi Authorization Server xem reference token còn `active` và có metadata gì.** JWT thuận lợi khi kiểm offline nhưng **không tự biết revocation trước expiry**; introspection có thể phản ánh token state mới hơn nhưng chịu **latency, cache và availability**. Cả hai cơ chế đều phải bảo đảm **issuer, audience, expiry, token purpose, scopes và sender binding khi cần**. Quyết định cuối cùng trên **tenant/object/business permission thuộc Resource Server**, không phải thuộc định dạng token.

### Chuẩn và tài liệu tham khảo

- **RFC 6749 — The OAuth 2.0 Authorization Framework:** access/refresh tokens, AS/Client/RS roles, grants và scope.
- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** `Authorization: Bearer`, `invalid_token`, `insufficient_scope`, 401/403 và token leakage risks.
- **RFC 7662 — OAuth 2.0 Token Introspection:** `POST`/`token`/`token_type_hint`, `active` boolean, optional claims, confidentiality, caching và introspection endpoint authorization.
- **RFC 7009 — OAuth 2.0 Token Revocation:** thu hồi token/grant, ảnh hưởng RS verification khi có cơ chế cập nhật trạng thái.
- **RFC 7519 — JSON Web Token (JWT):** claims `iss`, `aud`, `exp`, `nbf`, `iat`, `jti` và NumericDate.
- **RFC 7515 — JSON Web Signature (JWS):** compact serialization, JOSE headers, signature verification và key selection.
- **RFC 7517 — JSON Web Key (JWK):** JWKS, `kid`, public verification key và key purposes.
- **RFC 7518 — JSON Web Algorithms (JWA):** JOSE algorithms, key types và algorithm security policy.
- **RFC 8725 — JSON Web Token Best Current Practices:** JWT confusion, key/algorithm attacks, substitution và explicit validation rules.
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** `at+jwt`, claims/typing và Resource Server verification requirements.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** token theft, sender constraints, audience restriction, replay và refresh token security.
- **RFC 8707 — Resource Indicators for OAuth 2.0:** phát token dành đúng audience/resource.
- **RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP):** sender-bound tokens, `cnf.jkt`, `jti`/`htm`/`htu`/`ath` và nonce.
- **RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens:** `cnf.x5t#S256` và token-certificate binding.
- **OpenID Connect Core 1.0:** ID token vs OAuth access token, issuer/audience, authentication event và client validation.
- **Spring Security Reference — OAuth 2.0 Resource Server JWT:** `JwtDecoder`, `NimbusJwtDecoder`, `JwtAuthenticationProvider`, validators, scope authorities và key discovery.
- **Spring Security Reference — OAuth 2.0 Resource Server Opaque Token:** `OpaqueTokenIntrospector`, introspection URI/credentials, principal authorities và customization.
- **OWASP OAuth 2.0 Cheat Sheet, Authorization Cheat Sheet và API Security Top 10:** bearer security, access-control boundaries, BOLA/IDOR, logging và secure token lifecycle.
