# Kiểm soát cache JWKS và xử lý client chưa cập nhật khóa

> **Chương:** JWK và quản lý khóa  
> **Module:** `SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER`  
> **Mục tiêu module:** Học cách thiết kế, cấu hình, bảo mật, kiểm thử và vận hành OAuth 2.0/OpenID Connect Authorization Server bằng Spring Security và Spring Authorization Server trong ứng dụng Spring Boot.  
> **Phạm vi kỹ thuật:** Spring Boot 3.x, Spring Security 6.x và Spring Authorization Server 1.x trên Servlet stack. Các ví dụ tập trung vào JWT/JWKS và `NimbusJwtDecoder`; API cụ thể cần đối chiếu với phiên bản đang triển khai.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **JWK**, **JWKS**, `kid` và khóa ký đang hoạt động.
2. Giải thích vì sao Resource Server, OIDC Client và reverse proxy có thể giữ bản JWKS cũ sau khi Authorization Server xoay khóa.
3. Thiết kế vòng đời xoay khóa theo ba giai đoạn **pre-publish → switch signing key → retire old key**.
4. Cấu hình cache JWKS trong Spring Security/Nimbus và hiểu ảnh hưởng của TTL, cache invalidation, HTTP cache, CDN và nhiều instance.
5. Xử lý token có `kid` chưa được consumer biết mà vẫn giữ nguyên yêu cầu xác minh chữ ký.
6. Chẩn đoán lỗi sau khi đổi khóa, phân biệt cache stale với issuer, audience, algorithm, JWK selection và chữ ký không hợp lệ.
7. Xây dựng quy trình xoay khóa thường kỳ và quy trình ứng phó khi khóa riêng bị lộ.
8. Viết test cho key rollover, cache miss, unknown `kid`, JWKS endpoint outage, token cũ/mới và client chưa cập nhật khóa.

**Nguyên tắc quan trọng:** Khi JWT mang `kid` mới mà consumer chưa có public key tương ứng, cách xử lý an toàn là **làm mới JWKS từ nguồn đã tin cậy theo cơ chế có giới hạn rồi xác minh lại**. Nếu vẫn không có khóa hoặc chữ ký không hợp lệ, phải từ chối token. Không bỏ xác minh chữ ký, không tin `jku` do token tự khai và không chấp nhận mọi khóa chỉ để tránh lỗi 401.

## 2. JWK, JWKS và kid là gì?

### 2.1. JWK là một khóa, JWKS là tập khóa

- **JWK (JSON Web Key):** biểu diễn một khóa mật mã và các thuộc tính mô tả khóa, ví dụ loại khóa RSA/EC, thuật toán, mục đích sử dụng.
- **JWKS (JSON Web Key Set):** đối tượng JSON có mảng `keys` chứa một hoặc nhiều JWK.
- **`kid` (Key ID):** định danh một khóa trong JWK Set. JWT thường đặt `kid` trong protected header để bên xác minh tìm đúng public key.
- **Private key:** dùng để ký JWT, chỉ được giữ trong vùng bảo mật của Authorization Server (AS).
- **Public key:** được công bố qua JWKS để Resource Server (RS) hoặc OIDC Relying Party (RP) xác minh chữ ký.

Ví dụ JWKS rút gọn:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "as-signing-2026-10",
      "use": "sig",
      "alg": "RS256",
      "n": "PUBLIC_MODULUS_BASE64URL",
      "e": "AQAB"
    },
    {
      "kty": "RSA",
      "kid": "as-signing-2026-11",
      "use": "sig",
      "alg": "RS256",
      "n": "NEXT_PUBLIC_MODULUS_BASE64URL",
      "e": "AQAB"
    }
  ]
}
~~~

Các giá trị modulus là placeholder, không phải khóa có thể sử dụng. Trong ví dụ, AS công bố hai public key để consumer có thể xác minh JWT được ký bởi khóa cũ hoặc khóa mới trong giai đoạn chuyển tiếp.

**JWKS công khai không được chứa private key parameters** như `d` của RSA, `p`, `q`, `dp`, `dq`, `qi` hoặc private key material tương ứng của EC/OKP. Endpoint JWKS chỉ công bố phần public của các khóa ký.

### 2.2. JWT header sử dụng kid thế nào?

Một JWT ký JWS có protected header tương tự:

~~~json
{
  "alg": "RS256",
  "kid": "as-signing-2026-11",
  "typ": "JWT"
}
~~~

Khi nhận JWT, consumer:

1. Đọc header theo quy tắc JWS.
2. Dùng `kid` để chọn public JWK tương ứng trong JWKS đã lấy từ issuer tin cậy.
3. Kiểm tra key type, use/key operations, thuật toán được cho phép và cấu hình decoder.
4. Xác minh chữ ký.
5. Kiểm tra issuer, audience, thời hạn và các claim/policy khác.

`kid` chỉ là **định danh để chọn khóa**, không phải bằng chứng token đáng tin. Kẻ tấn công có thể tự viết header với `kid` bất kỳ; consumer vẫn phải xác minh chữ ký bằng public key tin cậy.

### 2.3. kid phải duy nhất cho từng key material

Khi tạo khóa ký mới, nên cấp `kid` mới. Không tái sử dụng `kid` cho một cặp khóa khác.

Nếu tái sử dụng `kid`, consumer có thể:

- Tiếp tục dùng public key cũ từ cache.
- Không nhận ra rằng cùng ID nay đại diện key material khác.
- Không refresh JWKS trong trường hợp cache lookup vẫn tìm thấy một JWK cùng `kid`.
- Trả lỗi signature invalid dù JWKS endpoint đã được cập nhật.

Quy tắc thực hành: **một key material có một kid ổn định; key material mới có kid mới**. Không dùng timestamp có thể trùng hoặc giá trị dễ bị tái sử dụng trong quy trình tự động.

## 3. Ai cache JWKS?

Trong hệ thống OAuth2/OIDC, “client chưa cập nhật khóa” thường là bên **tiêu thụ JWT**, không nhất thiết là OAuth2 Client gọi token endpoint.

| Thành phần | Vì sao cần JWKS? | Ví dụ cache |
| --- | --- | --- |
| Resource Server | Xác minh JWT access token | `NimbusJwtDecoder`, cache trong process |
| OIDC Client / Relying Party | Xác minh chữ ký ID token | OIDC ID token decoder và thư viện JOSE |
| API Gateway | Xác minh token trước khi chuyển tiếp | JWKS cache riêng của gateway |
| Service mesh / sidecar | Xác minh JWT ở lớp mạng | Cache theo issuer/JWKS URI |
| Reverse proxy / CDN | Phân phối endpoint JWKS nhanh hơn | HTTP cache, edge cache |
| Nền tảng xác minh tập trung | Dùng chung public keys cho nhiều service | Cache phân tán hoặc cache nội bộ |

Một OAuth2 Client chỉ gọi token endpoint để nhận access token **không nhất thiết** phải đọc JWKS. Nhưng nếu nó là OIDC RP xác minh ID token, hoặc đồng thời đóng vai trò Resource Server, nó cũng cần cập nhật public key.

### 3.1. Các lớp cache có thể độc lập

~~~mermaid
flowchart TD
    AS["Authorization Server<br/>JWKSource / JWKS endpoint"]
    CDN["CDN / Reverse proxy<br/>HTTP cache"]
    RS1["Resource Server A<br/>NimbusJwtDecoder cache"]
    RS2["Resource Server B<br/>NimbusJwtDecoder cache"]
    GW["API Gateway<br/>JWKS cache"]
    RP["OIDC Relying Party<br/>ID token decoder cache"]

    AS --> CDN
    CDN --> RS1
    CDN --> RS2
    CDN --> GW
    CDN --> RP
    AS -.->|"Có thể gọi trực tiếp"| RS1
    AS -.->|"Có thể gọi trực tiếp"| RS2
~~~

Xóa cache ở AS **không tự xóa** cache ở CDN, gateway, RS hoặc RP. Khi điều tra lỗi sau rotation, cần biết mỗi consumer đang lấy JWKS từ URL nào và giữ cache ở đâu.

## 4. Vì sao cache JWKS có thể gây lỗi sau khi xoay khóa?

Giả sử AS đang ký JWT bằng khóa `K1`, public key có `kid=k1`. Một RS đã tải JWKS và cache K1. Sau đó AS chuyển sang ký token mới bằng `K2` với `kid=k2`.

Nếu consumer vẫn chỉ có JWKS cũ:

- JWT mới có header `kid=k2`.
- Decoder tìm `k2` trong cache nhưng không thấy.
- Consumer có thể yêu cầu làm mới JWKS; nếu refresh chưa thành công hoặc cache/proxy trả dữ liệu cũ, không có public key tương ứng.
- Xác minh chữ ký không thể hoàn tất; request thường bị từ chối như token không hợp lệ.

~~~mermaid
sequenceDiagram
    autonumber
    participant AS as Authorization Server
    participant CDN as CDN / JWKS Cache
    participant RS as Resource Server

    AS->>CDN: JWKS chứa K1 (kid=k1)
    CDN-->>RS: Trả JWKS cũ
    Note over RS: Cache local giữ K1
    AS->>AS: Chuyển sang ký bằng K2 (kid=k2)
    AS-->>RS: JWT mới có kid=k2
    RS->>RS: Không tìm thấy k2 trong cache
    RS->>CDN: Refresh JWKS
    alt Cache/proxy đã cập nhật
        CDN->>AS: Fetch JWKS mới
        AS-->>CDN: K1 + K2
        CDN-->>RS: JWKS mới
        RS->>RS: Xác minh chữ ký bằng K2
    else Cache vẫn cũ hoặc endpoint lỗi
        CDN-->>RS: JWKS cũ / lỗi fetch
        RS-->>AS: Token bị từ chối ở API
    end
~~~

Đây là lý do cần **công bố public key mới trước khi dùng private key mới để ký token**. Nếu đổi khóa ký và JWKS cùng một thời điểm, consumer có thể nhận JWT trước khi public key được phân phối.

### 4.1. Ba loại lỗi cần phân biệt

| Lỗi quan sát | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Unknown `kid` | Consumer chưa tải JWKS chứa key mới | So JWT header với JWKS đang được consumer dùng |
| Signature invalid với `kid` đã tìm thấy | Sai key material, tái sử dụng kid, token bị sửa hoặc cache giữ key cũ cùng kid | So public key, kid và key rotation history |
| JWKS fetch timeout/5xx | AS, mạng, DNS, TLS, proxy hoặc CDN lỗi | Gọi JWKS URL trực tiếp từ môi trường consumer |
| Issuer invalid | JWT `iss` khác issuer được cấu hình | Kiểm tra issuer/forwarded headers |
| Audience invalid | Token không dành cho API này | Kiểm tra `aud` và audience validator |
| Algorithm rejected | Token dùng thuật toán không nằm trong allowlist | So header `alg` với policy decoder |

Không quy mọi lỗi 401 sau rotation cho cache. Một token có `kid` đúng vẫn có thể sai chữ ký, issuer, audience, expiry hoặc thuật toán.

## 5. Chiến lược xoay khóa ba giai đoạn

Quy trình an toàn có ba giai đoạn:

1. **Pre-publish:** công bố public key mới vào JWKS nhưng vẫn ký bằng khóa cũ.
2. **Switch signing key:** chuyển AS sang ký token mới bằng private key mới, giữ public key cũ để xác minh token còn hạn.
3. **Retire old key:** chỉ gỡ public key cũ sau khi token ký bằng khóa cũ đã hết thời hạn được chấp nhận và các consumer đã có đủ thời gian cập nhật.

~~~mermaid
flowchart LR
    A["Giai đoạn 1<br/>JWKS: K1 + K2<br/>Signer: K1"]
    B["Giai đoạn 2<br/>JWKS: K1 + K2<br/>Signer: K2"]
    C["Giai đoạn 3<br/>JWKS: K2<br/>Signer: K2"]

    A -->|"Consumer cache có thời gian nhận K2"| B
    B -->|"Token ký K1 hết hạn + margin"| C
~~~

### 5.1. Giai đoạn 1 — Pre-publish public key mới

AS thêm JWK public của K2 vào JWKS, tiếp tục ký token bằng K1.

Ví dụ:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "signing-k1",
      "use": "sig",
      "alg": "RS256",
      "n": "PUBLIC_K1",
      "e": "AQAB"
    },
    {
      "kty": "RSA",
      "kid": "signing-k2",
      "use": "sig",
      "alg": "RS256",
      "n": "PUBLIC_K2",
      "e": "AQAB"
    }
  ]
}
~~~

Consumer có thể tải JWKS mới và cache cả K1, K2 trước khi bất kỳ token nào dùng K2 xuất hiện.

**Thời gian pre-publish** cần dài ít nhất bằng khoảng cache/propagation lớn nhất có thể ảnh hưởng đến consumer, cộng thời gian retry/vận hành hợp lý. Nếu CDN có TTL 10 phút, decoder có cache 15 phút và có service chỉ refresh theo chu kỳ, không nên chuyển signer ngay sau vài giây. Cần đo/biết TTL thực tế thay vì dùng một khoảng mặc định không có căn cứ.

### 5.2. Giai đoạn 2 — Chuyển signer sang K2

Khi đủ thời gian phân phối, AS chuyển private signing key active sang K2:

- JWT mới có `kid=signing-k2`.
- JWKS vẫn công bố cả K1 và K2.
- Consumer cũ đã có K2 sẽ xác minh được token mới.
- Consumer chưa cập nhật có thể gặp unknown kid; decoder cần refresh JWKS từ URL tin cậy.
- JWT cũ ký bằng K1 vẫn phải được xác minh trong thời gian còn hiệu lực.

Không gỡ K1 ngay khi bắt đầu ký bằng K2. Các token đã phát hành bằng K1 có thể vẫn còn hợp lệ ở RS/RP.

### 5.3. Giai đoạn 3 — Retire K1

Chỉ gỡ public key K1 khỏi JWKS sau khi:

- Không còn token hợp lệ cần xác minh bằng K1.
- Đã qua TTL tối đa của access token/ID token ký bằng K1.
- Đã tính clock skew/leeway của các consumer.
- Đã tính propagation delay, rollout và consumer chậm cập nhật.
- Không có workload hợp lệ nào còn dùng token cũ.
- Quy trình rollback/incident đã được xem xét.

Ví dụ công thức lập kế hoạch:

~~~text
retire_after >=
    last_issuance_time_using_K1
  + maximum_lifetime_of_tokens_signed_by_K1
  + maximum_clock_skew_or_validation_leeway
  + rollout_and_propagation_margin
~~~

Đây là công thức vận hành để xác định **mốc sớm nhất có thể xem xét retire**, không phải công thức chuẩn cố định của RFC. Nếu token có TTL khác nhau theo client, phải dùng lifetime lớn nhất còn được chấp nhận. Nếu có ID token dài hạn hoặc token đặc thù, phải tính cả chúng.

### 5.4. Không để JWKS thiếu khóa cũ khi token cũ còn hạn

Nếu gỡ K1 quá sớm, RS đã refresh JWKS sẽ không còn public key để xác minh JWT cũ. Điều này gây lỗi hàng loạt dù token chưa hết hạn.

Một số consumer vẫn giữ K1 trong cache và tạm thời xác minh được, trong khi consumer khác đã tải JWKS mới thì thất bại. Hệ thống có thể tạo ra hành vi **không nhất quán giữa các instance**. Vì vậy overlap phải được tính theo token lifetime và rollout, không chỉ theo việc AS đã chuyển signer.

## 6. Cấu hình JWKS endpoint ở Spring Authorization Server

### 6.1. JWKSource là nguồn khóa của AS

Spring Authorization Server dùng `JWKSource<SecurityContext>` để cung cấp key material cho quá trình ký JWT và endpoint JWK Set. Với cấu hình thông thường, endpoint mặc định là `/oauth2/jwks` khi JWK source được cấu hình và endpoint được bật theo settings.

Mô hình bean khái niệm:

~~~java
@Bean
JWKSource<SecurityContext> jwkSource(KeyMaterialProvider keyMaterialProvider) {
    // Load JWKSet từ kho khóa bền vững/KMS/HSM do ứng dụng quản lý.
    // JWKSet cần chứa private key material trong vùng ký tin cậy,
    // và các public keys cần công bố trong JWKS.
    JWKSet jwkSet = keyMaterialProvider.loadSigningKeySet();

    return (jwkSelector, securityContext) ->
        jwkSelector.select(jwkSet);
}
~~~

`KeyMaterialProvider` là abstraction do ứng dụng tự xây, không phải bean Spring có sẵn. Trong production, không lưu private key trong source code, không tạo khóa ngẫu nhiên mới ở mỗi lần khởi động và không chia sẻ private key qua JWKS endpoint.

### 6.2. Công bố public keys, giữ private keys ở AS

Một JWK RSA private có thể chứa `d`, `p`, `q` và các tham số bí mật. Khi endpoint trả JWKS, response chỉ được chứa public representation.

Với Nimbus JOSE, public view của một JWK có thể được tạo bằng `toPublicJWK()`; với JWK Set có `toPublicJWKSet()`. Spring Authorization Server quản lý response endpoint theo implementation của nó, nhưng đội vận hành vẫn phải kiểm tra response thực tế:

- Chỉ có public parameters.
- Có key đang ký token mới.
- Có key cũ trong giai đoạn overlap.
- `kid` duy nhất và khớp JWT header.
- `use`/`key_ops`/`alg` phù hợp signing/verification.
- Không lộ private RSA/EC/OKP parameters.

### 6.3. JWK Set endpoint và issuer metadata

OIDC/OAuth authorization server metadata có thể công bố `jwks_uri` để consumer biết endpoint JWKS chính thức. Consumer nên dùng metadata của issuer tin cậy hoặc cấu hình JWKS URI qua cấu hình quản trị.

Không lấy JWKS URL từ claim `jku`/`x5u` trong JWT không tin cậy. Nếu token được phép tự khai URL khóa, attacker có thể khiến consumer tải public key do attacker kiểm soát và tạo chữ ký giả theo key đó.

## 7. Cache JWKS trong Spring Security và Nimbus

### 7.1. Decoder lấy JWKS từ URL tin cậy

Spring Security có thể cấu hình Resource Server với `issuer-uri` để discovery issuer và JWKS URI, hoặc `jwk-set-uri` được cấu hình trực tiếp.

Ví dụ application properties:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.test
          jwk-set-uri: https://auth.example.test/oauth2/jwks
~~~

Dùng cả issuer và JWK Set URI trong những phiên bản Spring Boot hỗ trợ cách cấu hình này có thể giúp chỉ định trực tiếp endpoint khóa mà vẫn giữ issuer validation. Hãy xác minh hành vi property binding của version đang dùng. Nếu tự khai báo `JwtDecoder` bean, phải tự cấu hình validator tương ứng.

### 7.2. Tùy chỉnh NimbusJwtDecoder và cache

Ví dụ Java dùng Spring Cache:

~~~java
@Bean
JwtDecoder jwtDecoder(Cache jwkSetCache) {
    NimbusJwtDecoder decoder = NimbusJwtDecoder
        .withJwkSetUri("https://auth.example.test/oauth2/jwks")
        .jwsAlgorithm(SignatureAlgorithm.RS256)
        .cache(jwkSetCache)
        .build();

    OAuth2TokenValidator<Jwt> issuerValidator =
        JwtValidators.createDefaultWithIssuer(
            "https://auth.example.test");

    decoder.setJwtValidator(issuerValidator);
    return decoder;
}
~~~

Các import chính:

~~~java
import org.springframework.cache.Cache;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
~~~

`jwkSetCache` phải là cache đã được cấu hình trong ứng dụng, có TTL/eviction phù hợp và quan sát được. Đoạn này chỉ minh họa cách truyền cache vào builder; nó không tự tạo cache manager hoặc đặt TTL. API `cache(...)` và chi tiết cache phụ thuộc phiên bản Spring Security/Nimbus đang dùng, nên hãy compile/test trên version thực tế.

**Không đặt cache TTL quá dài rồi trông chờ rotation hoạt động tức thời.** Ngược lại, không đặt TTL cực ngắn khiến mọi API request liên tục gọi JWKS endpoint, tăng latency và tạo tải lên AS.

### 7.3. Thêm audience validation

Cache đúng không có nghĩa JWT đã được phép truy cập API. Ví dụ bổ sung validator audience:

~~~java
@Bean
JwtDecoder jwtDecoder(Cache jwkSetCache) {
    NimbusJwtDecoder decoder = NimbusJwtDecoder
        .withJwkSetUri("https://auth.example.test/oauth2/jwks")
        .jwsAlgorithm(SignatureAlgorithm.RS256)
        .cache(jwkSetCache)
        .build();

    OAuth2TokenValidator<Jwt> issuer =
        JwtValidators.createDefaultWithIssuer(
            "https://auth.example.test");

    OAuth2TokenValidator<Jwt> audience = jwt -> {
        if (jwt.getAudience().contains("booking-api")) {
            return OAuth2TokenValidatorResult.success();
        }
        OAuth2Error error = new OAuth2Error(
            "invalid_token",
            "Required audience is missing",
            null);
        return OAuth2TokenValidatorResult.failure(error);
    };

    decoder.setJwtValidator(
        new DelegatingOAuth2TokenValidator<>(issuer, audience));
    return decoder;
}
~~~

Ví dụ này yêu cầu `RS256` và `booking-api` theo policy minh họa. Nếu AS phát token bằng thuật toán khác, phải cấu hình allowlist đúng và nhất quán. Không tự đọc `alg` từ JWT rồi cho phép mọi thuật toán. Issuer, audience và expiry vẫn phải được xác minh sau khi public key đã được tìm thấy.

### 7.4. Cache không nhất thiết chỉ nằm trong một JVM

Có thể dùng:

- Cache cục bộ trong mỗi Resource Server.
- Cache Spring dùng Caffeine/Ehcache hoặc provider phù hợp.
- Cache phân tán, nếu có nhu cầu vận hành thực sự.
- HTTP cache của CDN/reverse proxy.
- Cache nội bộ của thư viện JOSE/Nimbus.

Không cần ép mọi hệ thống dùng một distributed cache. Cache cục bộ thường đơn giản và hiệu quả; điều cần thiết là **TTL, refresh-on-miss, quan sát và rollout key được thiết kế rõ**.

## 8. TTL, HTTP Cache và CDN

### 8.1. Cache-Control của JWKS

JWKS là public key material nên có thể được cache. AS/gateway có thể dùng HTTP response headers như:

- `Cache-Control: public, max-age=...`.
- `ETag` và `If-None-Match` cho conditional GET nếu endpoint/proxy hỗ trợ.
- `Last-Modified`/`If-Modified-Since` nếu có hỗ trợ.
- Chính sách CDN TTL phù hợp với key rotation và incident response.

Không có một TTL đúng cho mọi hệ thống. Chọn TTL phải cân bằng:

| TTL | Ưu điểm | Rủi ro |
| --- | --- | --- |
| Quá ngắn | Consumer sớm nhận key mới | Nhiều request tới AS/CDN, latency, tải tăng |
| Vừa phải | Giảm tải và vẫn có cửa sổ cập nhật hợp lý | Cần quy trình pre-publish/refresh |
| Quá dài | Ít request JWKS | Unknown kid kéo dài, key compromise khó xử lý đồng bộ |

Không đặt `stale-if-error` hoặc cơ chế cache stale vô hạn mà không đánh giá. Nếu cache giữ JWKS cũ mãi khi AS lỗi, hệ thống có thể tiếp tục xác minh các key đã bị thu hồi theo sự cố. Nếu fail closed quá sớm, một sự cố mạng ngắn có thể làm API từ chối toàn bộ token cần key mới. Đây là quyết định risk/availability cần được ghi rõ.

### 8.2. Cache ở CDN có thể che giấu cập nhật từ AS

Tình huống:

1. AS đã publish K1 + K2.
2. CDN vẫn cache JWKS cũ chỉ có K1.
3. Consumer fetch từ CDN và nhận JWKS cũ.
4. AS bắt đầu ký bằng K2.
5. Consumer không xác minh được JWT mới dù endpoint origin đã đúng.

Điều tra phải so sánh response từ:

- JWKS endpoint trực tiếp của AS trong mạng tin cậy.
- JWKS URL mà consumer thực sự gọi.
- CDN POP/edge liên quan.
- Nội dung cache trong decoder (nếu có cách quan sát an toàn).

Không chỉ mở URL từ laptop rồi kết luận mọi consumer nhận cùng response.

### 8.3. Không nên dựa vào thao tác purge thủ công duy nhất

Purge CDN có thể giúp đẩy key mới nhanh hơn, nhưng không giải quyết cache cục bộ trong mỗi JVM, gateway hoặc OIDC RP. Quy trình rotation cần có thời gian pre-publish đủ dài và cơ chế refresh hợp lệ. Purge chỉ là một bước vận hành bổ trợ.

## 9. Consumer gặp kid mới: refresh rồi xác minh lại

### 9.1. Hành vi mong muốn

Khi JWT có `kid` mà cache hiện tại không chứa:

1. Consumer nhận diện không có key phù hợp.
2. Consumer thử làm mới JWKS từ **URI đã được cấu hình tin cậy** theo cơ chế thư viện.
3. Sau khi tải thành công, consumer tìm lại key theo `kid` và các thuộc tính phù hợp.
4. Consumer xác minh chữ ký bằng thuật toán được allowlist.
5. Consumer tiếp tục xác minh issuer, audience, expiry và claims.
6. Nếu không tìm thấy key hoặc fetch thất bại, consumer từ chối token.

Một số implementation Nimbus Remote JWK Set có thể làm mới JWKS khi không tìm thấy key phù hợp trong cache. Hành vi chính xác, retry, cache và concurrency phải kiểm tra theo version/cấu hình. **Không giả định mọi JWT decoder hoặc gateway đều tự refresh ngay lập tức.**

### 9.2. Không tìm thấy kid sau refresh

Kết quả an toàn:

~~~text
JWT kid = signing-k3
Cached JWKS: k1, k2
Refresh JWKS từ issuer URI tin cậy
Fetched JWKS: k1, k2

Không tìm thấy signing-k3
=> Reject token
=> Ghi metric unknown_kid
=> Không bỏ signature validation
~~~

Không chấp nhận JWT chỉ vì `iss` đúng hoặc vì AS có cùng domain. Nếu không có public key phù hợp, không thể chứng minh chữ ký.

### 9.3. Nếu refresh JWKS thất bại do mạng

Phân biệt hai trường hợp:

- **Token dùng kid đã cache và key còn được policy chấp nhận:** decoder có thể tiếp tục xác minh bằng cache còn hiệu lực, tùy cache policy.
- **Token dùng kid mới chưa có trong cache:** không có key để xác minh, phải từ chối token đó. Có thể retry theo backoff/health policy, nhưng không bỏ chữ ký.

Không biến một lỗi fetch JWKS thành `permitAll()` hoặc chấp nhận token không xác minh. Nếu availability là ưu tiên cao, hãy cải thiện JWKS endpoint, CDN, cache và rollout thay vì hạ chuẩn xác thực.

### 9.4. Chống refresh storm do unknown kid

Attacker có thể gửi hàng loạt JWT giả với `kid` ngẫu nhiên để kích hoạt refresh JWKS, gây tải lên AS. Consumer/gateway nên:

- Có single-flight hoặc coalescing để nhiều request cùng unknown kid dùng chung một lần fetch.
- Giới hạn tần suất refresh khi liên tục gặp unknown kid.
- Có negative cache ngắn hạn hoặc cooldown có kiểm soát.
- Không cho `kid` quyết định URL cần fetch.
- Đặt timeout, retry/backoff và giới hạn response size.
- Ghi metric/alert khi unknown kid tăng bất thường.
- Vẫn cho phép refresh hợp lệ khi key mới được pre-publish/rollout.

Negative cache quá dài có thể chặn chính key mới vừa được publish; phải cân bằng cooldown với kế hoạch pre-publish.

## 10. Quy trình rotation thường kỳ cho Spring Authorization Server

### 10.1. Trước khi rotation

- Xác định issuer và JWKS URI mà từng consumer đang dùng.
- Kiểm kê Resource Server, OIDC RP, gateway, sidecar và CDN.
- Đo TTL của decoder cache và HTTP/CDN cache.
- Kiểm tra access token/ID token lifetime lớn nhất.
- Kiểm tra clock skew/leeway của consumer.
- Chuẩn bị key pair mới trong kho khóa an toàn, tạo `kid` mới.
- Xác minh thuật toán/key size/curve theo policy.
- Có kế hoạch rollback signer và cập nhật JWKS.

### 10.2. Trong khi rotation

1. Publish public K2 cùng K1 trong JWKS.
2. Xác minh endpoint origin trả cả hai public keys.
3. Xác minh response từ CDN/proxy và một nhóm consumer representative.
4. Chờ đủ pre-publish window.
5. Chuyển AS signer sang private K2.
6. Phát một JWT thử nghiệm có `kid=k2` và xác minh ở mọi nhóm consumer.
7. Theo dõi unknown-kid, signature-invalid, 401/5xx và JWKS fetch metrics.
8. Giữ K1 để xác minh token cũ.

### 10.3. Sau khi rotation

- Đợi token cuối cùng ký K1 hết hạn cùng clock skew và margin.
- Xác nhận không còn workload hợp lệ cần K1.
- Gỡ K1 khỏi JWKS theo đợt nếu có nhiều issuer/consumer.
- Giữ audit record của key ID, thời điểm publish, activate, retire và người/quy trình phê duyệt.
- Không xóa private K1 khỏi backup/secure key lifecycle cho tới khi retention/incident policy cho phép.
- Cập nhật tài liệu vận hành và test cho lần rotation sau.

### 10.4. Runbook dạng trạng thái

| Trạng thái | JWKS | Signing key | Điều kiện chuyển bước |
| --- | --- | --- | --- |
| Stable | K1 | K1 | Chuẩn bị K2 |
| Pre-published | K1 + K2 | K1 | Cache/consumer đã có thời gian nhận K2 |
| Switched | K1 + K2 | K2 | Tất cả token K1 đã hết hạn theo policy |
| Retired | K2 | K2 | Hoàn tất kiểm tra consumer |
| Emergency | Theo incident policy | Khóa an toàn mới | Có kế hoạch revoke/deny compromised key |

## 11. Khi client/Resource Server chưa cập nhật khóa

### 11.1. Cách xử lý theo mức độ ảnh hưởng

| Tình huống | Biểu hiện | Hướng xử lý |
| --- | --- | --- |
| Một instance bị stale cache | Một phần traffic 401, instance khác thành công | Refresh/evict JWKS cache ở instance bị lỗi, kiểm tra TTL |
| CDN trả JWKS cũ | Nhiều consumer cùng không thấy kid mới | Purge/invalidate edge cache, kiểm tra origin và max-age |
| Decoder không refresh on unknown kid | Token mới bị từ chối dù origin đã có key | Cấu hình refresh/cache đúng hoặc cập nhật thư viện |
| Consumer dùng sai JWKS URI | Fetch một issuer/environment khác | Kiểm tra discovery metadata và cấu hình issuer |
| Consumer dùng kid cũ nhưng signature sai | Kid bị reuse hoặc key material không đồng bộ | Tạo kid mới, kiểm tra JWK thumbprint/key pair |
| Consumer pin public key tĩnh | Không tự tải JWKS | Triển khai quy trình phân phối/cập nhật trust store |
| Consumer chặn thuật toán mới | Key có nhưng decoder không cho alg | Thống nhất algorithm allowlist trước rotation |
| Consumer bỏ qua issuer/audience | Token có chữ ký nhưng dùng sai nơi | Cấu hình validators, không hạ validation |

### 11.2. Các bước hỗ trợ client cập nhật

1. Lấy header JWT đã loại bỏ token payload nhạy cảm hoặc dùng công cụ nội bộ để đọc riêng `kid` và `alg`.
2. Lấy JWKS mà client thực sự truy cập từ chính môi trường client.
3. So sánh `kid` trong JWT với `kid` trong JWKS.
4. Kiểm tra HTTP cache headers, CDN Age, ETag, DNS và TLS.
5. Kiểm tra decoder cache TTL và cách refresh khi unknown kid.
6. Nếu an toàn, evict cache hoặc restart một instance theo quy trình; tránh restart hàng loạt gây gián đoạn.
7. Gửi lại request bằng token mới sau khi key được cập nhật.
8. Nếu vẫn lỗi, xác minh chữ ký, issuer, audience, alg và thời hạn; không kết luận là cache chỉ từ status 401.

**Không yêu cầu client tải một public key qua email/chat rồi import thủ công** nếu kiến trúc dự kiến dùng JWKS. Nếu buộc phải pin key, phải có kênh phân phối key được xác thực, quy trình rotation và rollback riêng.

### 11.3. Client không thể cập nhật ngay: có nên tiếp tục dùng khóa cũ?

Với rotation thường kỳ, có thể duy trì K1 trong JWKS và chưa phát token K2 cho tới khi consumer đủ thời gian cập nhật. Nếu K2 đã active nhưng một client cũ chưa hỗ trợ, có thể tạm hoãn rollout hoặc nâng cấp client theo kế hoạch.

**Không ký song song hai access token cho cùng một request** chỉ để chiều một client không cập nhật trừ khi protocol/application được thiết kế rõ. Không đưa cả private key vào client để nó tự xác minh hoặc ký token.

Với incident khóa bị lộ, mức ưu tiên khác: phải vô hiệu khóa compromised và chấp nhận một số client cũ bị từ chối. Không giữ khóa bị lộ chỉ để tương thích.

## 12. Xử lý khóa bị compromise

### 12.1. Emergency rotation khác rotation thường kỳ

Nếu private signing key K1 bị lộ, attacker có thể tự tạo JWT có chữ ký hợp lệ theo public K1 cho tới khi consumer không còn tin K1 hoặc có biện pháp chặn khác.

Chỉ thêm K2 và chuyển signer sang K2 **không đủ** nếu attacker vẫn có thể ký bằng K1 và consumer vẫn tin public K1.

Quy trình ứng phó có thể gồm:

1. Kích hoạt incident response và xác định phạm vi khóa/issuer/client/token bị ảnh hưởng.
2. Ngừng sử dụng private K1 ngay; cô lập/revoke key trong KMS/HSM/secure store.
3. Tạo K2 từ môi trường sạch, công bố public key K2 và chuyển signer.
4. Gỡ public K1 khỏi JWKS khẩn cấp theo incident policy.
5. Purge cache CDN/proxy và yêu cầu các consumer refresh JWKS.
6. Invalidate/denylist token liên quan nếu có token registry; cân nhắc introspection/online validation hoặc rút ngắn thời hạn token.
7. Thông báo và theo dõi các client/RS chưa cập nhật; fail closed cho token ký K1.
8. Điều tra log, audit và nguồn lộ khóa; rotate các credential liên quan nếu có khả năng bị truy cập cùng lúc.
9. Ghi lại quyết định, thời gian, phạm vi và kiểm tra sau incident.

### 12.2. Cache làm chậm hiệu lực của việc gỡ key

Khi K1 bị xóa khỏi JWKS origin:

- CDN có thể vẫn trả response cũ.
- Decoder có thể còn K1 trong memory cache.
- Một số consumer có thể không refresh cho tới khi TTL hết.
- JWT giả ký bằng K1 có thể vẫn được chấp nhận bởi consumer giữ public key K1, nếu token còn qua các validators khác.

Do đó emergency response cần **chủ động purge/invalidate cache** và có cơ chế consumer refresh/deny compromised `kid`. Không thể dựa vào việc cập nhật JWKS origin rồi giả định mọi nơi đã nhận thay đổi tức thì.

### 12.3. JWT self-contained không có revocation tức thì mặc định

Nếu RS chỉ xác minh JWT cục bộ bằng public key, nó có thể tiếp tục chấp nhận token đã ký hợp lệ trước đó cho đến khi `exp` hoặc key bị loại khỏi cache/allowlist. Thu hồi refresh token không tự vô hiệu access token JWT đã phát.

Với API nhạy cảm, cân nhắc:

- Access token TTL ngắn.
- Denylist theo `jti` hoặc token version trong tình huống phù hợp.
- Introspection/opaque token cho nhu cầu kiểm soát trạng thái online.
- Kiểm tra account/authorization state cho thao tác rủi ro cao.
- Key ID denylist khi cần chặn toàn bộ token ký bởi một key compromise.

Mỗi cơ chế có chi phí availability, latency và vận hành riêng.

## 13. Kiểm thử JWKS cache và rotation

### 13.1. Ma trận kiểm thử

| Ca kiểm thử | Thiết lập | Kết quả mong đợi |
| --- | --- | --- |
| Stable key | JWKS có K1, JWT ký K1 | Consumer xác minh thành công |
| Pre-publish | JWKS có K1 + K2, signer vẫn K1 | Token K1 vẫn hợp lệ; consumer tải được K2 |
| Switched signer | Signer K2, JWKS vẫn có K1 + K2 | Token K2 xác minh được; token K1 còn hạn vẫn hợp lệ |
| Unknown kid | Token có kid K3 chưa publish | Consumer refresh có giới hạn, vẫn không tìm thấy thì từ chối |
| Stale local cache | Cache chỉ có K1, token dùng K2 | Refresh JWKS và xác minh lại nếu endpoint có K2 |
| Stale CDN | Origin có K2, CDN chưa có | Phát hiện qua response thực tế, purge/update edge |
| JWKS endpoint timeout | Cache có K1, token dùng K1 | Hành vi theo cache policy; không bỏ signature |
| JWKS endpoint timeout với K2 | Cache chưa có K2 | Từ chối token K2, retry/backoff an toàn |
| Same kid, different key | Tái sử dụng kid sai quy tắc | Test phải phát hiện signature/key mismatch; quy trình cấm reuse kid |
| Wrong algorithm | Token alg ngoài allowlist | Từ chối |
| Wrong issuer | JWT iss không khớp | Từ chối |
| Wrong audience | JWT aud dành cho API khác | Từ chối |
| Old key retirement sớm | Gỡ K1 khi token K1 còn hạn | Test phát hiện token hợp lệ bị lỗi |
| Old key retired đúng hạn | K1 token hết hạn + margin | Token K2 tiếp tục hoạt động |
| Emergency K1 compromise | Gỡ K1/purge cache | Consumer ngừng tin token K1 theo incident policy |
| Multi-instance decoder | Một instance cache mới, một stale | Phát hiện lỗi phân mảnh và xác minh rollout |
| OIDC ID token rotation | RP nhận ID token kid mới | RP cập nhật JWKS và verify issuer/audience/nonce |
| JWKS private key leak | Kiểm tra response endpoint | Không có private parameters |

### 13.2. Test lấy JWKS qua HTTP

Dùng integration test hoặc test environment để:

1. Gọi JWKS endpoint thực tế và parse `keys`.
2. Assert public key K1/K2 có đúng `kid`.
3. Assert không có private RSA parameters (`d`, `p`, `q`, `dp`, `dq`, `qi`).
4. Lấy JWT do AS phát, đọc `kid` và `alg`.
5. Xác minh chữ ký với public key tương ứng từ JWKS.
6. Xác minh issuer/audience/expiry độc lập.

Không chỉ assert HTTP 200; một JWKS response trả JSON rỗng hoặc thiếu key vẫn có thể là lỗi vận hành.

### 13.3. Test cache miss và refresh

Thiết kế test với JWKS server giả lập có thể đổi response theo thời gian:

- Lần đầu trả K1, consumer tải và cache.
- Thay response thành K1 + K2.
- Gửi JWT có kid K2.
- Kiểm tra decoder có fetch JWKS mới theo behavior đã cấu hình/version.
- Xác minh token K2.
- Tiếp tục trả JWKS không có K3 và gửi JWT K3; xác minh decoder từ chối.
- Mô phỏng JWKS endpoint 503/timeout; xác minh hành vi cache và fail closed cho unknown key.

Đây là kiểm thử behavior thư viện, nên pin version Spring Security/Nimbus trong build. Không giả định refresh-on-unknown-kid có hành vi giống nhau ở mọi phiên bản.

### 13.4. Test không được bỏ qua signature validation

Không mock `JwtDecoder` thành “always valid” trong bài test rotation rồi kết luận cache hoạt động. Cần test với JWK thật/giả có private/public key tương ứng và token ký thật để chứng minh key selection + signature verification.

## 14. Theo dõi và chẩn đoán trong production

### 14.1. Metric nên có

| Metric | Mục đích |
| --- | --- |
| JWKS fetch count/latency | Biết consumer có refresh quá thường xuyên hoặc endpoint chậm |
| JWKS fetch failures theo status | Phát hiện mạng, TLS, DNS, CDN, AS outage |
| Unknown kid count | Phát hiện consumer stale hoặc token bất thường |
| Signature verification failures | Phân biệt lỗi key, token giả hoặc algorithm |
| JWKS cache age/TTL remaining | Quan sát độ mới của key material |
| 401 theo instance/issuer/client group | Tìm lỗi chỉ xảy ra ở một consumer |
| Key publish/activate/retire events | Audit key lifecycle |
| CDN cache age / invalidation status | Phát hiện edge đang trả response cũ |
| Token issuance theo kid | Xác định token mới đang ký bằng key nào |

Không đưa raw JWT hoặc token payload nhạy cảm vào metrics labels. Có thể log `kid` vì nó là định danh key công khai, nhưng cần kiểm soát cardinality và dữ liệu từ header chưa tin cậy.

### 14.2. Log sự kiện rotation

Nên ghi nhận:

- Issuer và JWKS URI đã cấu hình.
- `kid` được publish, active signer, retire.
- Thời điểm và phiên bản deployment.
- Cache purge/invalidation và kết quả.
- Consumer groups đã xác minh.
- Error rate trước/sau switch.
- Người/quy trình phê duyệt và liên kết incident/change ticket.

Không ghi private key material, raw access token hoặc client secret.

### 14.3. Bảng chẩn đoán nhanh

| Triệu chứng | Bước kiểm tra đầu tiên |
| --- | --- |
| Chỉ một pod 401 sau rotation | So sánh cache state, image/version và JWKS response của pod đó |
| Tất cả pod 401 token mới | So token kid với JWKS origin và CDN |
| Chỉ gateway 401, service nội bộ thành công | Gateway có cache/issuer/JWKS URI riêng |
| OIDC login fail nhưng API access token thành công | RP có thể cache JWKS hoặc validate ID token khác |
| Token cũ fail ngay sau rotation | Public key cũ đã bị gỡ quá sớm hoặc issuer/alg thay đổi |
| Unknown kid tăng đột biến | Kiểm tra rotation, issuer mismatch hoặc JWT giả gây refresh storm |
| Signature invalid dù kid tồn tại | Kiểm tra kid reuse, key material, alg và token bị sửa |
| JWKS 200 nhưng decoder vẫn lỗi | Response thực tế có key đúng? cache có stale? key use/alg có match? |

## 15. Các sai lầm thường gặp

| Sai lầm | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| Đổi signer và gỡ key cũ cùng lúc | JWT cũ chưa hết hạn bị từ chối | Pre-publish, overlap và retire sau |
| Dùng lại `kid` cho key mới | Consumer có thể giữ key cũ cùng ID | Kid mới cho mỗi key material |
| Publish K2 sau khi đã ký JWT K2 | Consumer chưa có public key | Publish trước và chờ cache/propagation |
| Đặt cache TTL quá dài | Consumer giữ JWKS cũ lâu | TTL phù hợp và có refresh-on-miss |
| Đặt TTL quá ngắn | JWKS endpoint bị gọi liên tục | Cân bằng cache và rollout |
| Chỉ purge CDN | Cache cục bộ vẫn stale | Kiểm tra cả decoder/gateway/RP |
| Tin `jku` trong JWT | Attacker có thể chỉ định key server | Dùng JWKS URI cấu hình tin cậy |
| Chấp nhận token khi không có public key | Bỏ xác minh chữ ký | Fail closed |
| Cho phép mọi `alg` từ header | Algorithm confusion/downgrade | Pin allowlist thuật toán |
| Xóa K1 trước khi token K1 hết hạn | Token hợp lệ bị lỗi | Chờ max token lifetime + skew + margin |
| Giữ K1 bị compromise vì tương thích | Attacker tiếp tục ký token giả | Emergency revoke, purge cache, fail closed |
| Nhầm unknown kid với audience invalid | Sửa cache không giải quyết lỗi | Chẩn đoán theo từng validator |
| Chỉ test JWKS 200 | Có thể thiếu key/private key leak | Parse và xác minh nội dung JWKS |
| Chỉ test một RS instance | Không phát hiện cache phân mảnh | Test nhiều instance/consumer |
| Không test OIDC RP | API chạy nhưng login OIDC fail | Test cả ID token signature rotation |

## 16. Câu hỏi tự kiểm tra

**Câu 1.** JWK và JWKS khác nhau thế nào?

**Đáp án:** JWK biểu diễn một khóa; JWKS là tập các JWK, thường được công bố qua endpoint để consumer xác minh JWT.

**Câu 2.** `kid` có phải secret hoặc bằng chứng chữ ký hợp lệ không?

**Đáp án:** Không. Nó chỉ định danh key để lựa chọn public JWK; consumer vẫn phải xác minh chữ ký và các claim.

**Câu 3.** Vì sao cần publish public K2 trước khi AS bắt đầu ký bằng K2?

**Đáp án:** Để Resource Server/OIDC RP có thời gian tải và cache key mới trước khi nhận JWT mang kid K2.

**Câu 4.** Khi chuyển signer sang K2, có thể gỡ public K1 ngay không?

**Đáp án:** Không nếu token ký bằng K1 còn trong thời hạn được chấp nhận. Cần giữ K1 trong giai đoạn overlap và retire sau TTL lớn nhất, clock skew và margin.

**Câu 5.** Consumer nhận JWT có kid không tìm thấy sau khi refresh JWKS thì làm gì?

**Đáp án:** Từ chối token, ghi metric/diagnostic và xử lý refresh/retry có giới hạn. Không bỏ signature validation.

**Câu 6.** Purge CDN có xóa cache JWKS trong NimbusJwtDecoder của mọi JVM không?

**Đáp án:** Không. CDN và cache cục bộ là các lớp độc lập; cần quản lý từng lớp.

**Câu 7.** Vì sao không nên tái sử dụng kid khi thay key material?

**Đáp án:** Consumer có thể dùng cache cũ vì vẫn tìm thấy cùng kid, gây chọn sai public key và lỗi signature. Mỗi key material mới cần kid mới.

**Câu 8.** Khi private key bị compromise, có nên giữ public key trong JWKS tới khi mọi token hết hạn như rotation thường kỳ không?

**Đáp án:** Không nhất thiết. Emergency response phải ưu tiên loại bỏ niềm tin vào khóa compromised, purge cache và chấp nhận từ chối token ký bằng khóa đó.

**Câu 9.** JWT signature hợp lệ có đủ để Resource Server chấp nhận token không?

**Đáp án:** Không. Còn phải kiểm tra issuer, audience, expiry, algorithm, scopes và policy nghiệp vụ.

## 17. Checklist trước khi vận hành rotation

- [ ] JWK Set chỉ công bố public key material.
- [ ] Mỗi key material có `kid` riêng và ổn định.
- [ ] JWT dùng thuật toán nằm trong allowlist.
- [ ] Consumer lấy JWKS từ issuer/JWKS URI tin cậy, không lấy URL từ JWT header.
- [ ] Đã kiểm kê decoder, gateway, OIDC RP, CDN và cache layers.
- [ ] TTL của local cache và HTTP/CDN cache được biết và đo.
- [ ] Public K2 được pre-publish trước khi switch signer.
- [ ] K1 được giữ trong overlap khi token cũ còn hạn.
- [ ] Mốc retire tính token lifetime lớn nhất, clock skew và rollout margin.
- [ ] Có test unknown kid, cache miss, fetch outage, signature invalid và issuer/audience.
- [ ] Có cách quan sát kid, JWKS fetch, cache age và signature failure.
- [ ] Có quy trình purge/evict cache theo từng consumer khi cần.
- [ ] Có runbook emergency khi private key compromise.
- [ ] Không chấp nhận token khi không xác minh được chữ ký.
- [ ] Multi-instance AS/RS dùng key set và cache policy nhất quán.
- [ ] Đã test cả JWT access token và OIDC ID token nếu hệ thống hỗ trợ OIDC.

## 18. Tài liệu tham khảo và kết luận

Tài liệu chuẩn và tài liệu framework:

- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517)
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515)
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html)
- [Spring Authorization Server — Core Model and Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html)
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html)
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — NimbusJwtDecoder API](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/jwt/NimbusJwtDecoder.html)
- [Nimbus JOSE + JWT — Remote JWK Set](https://connect2id.com/products/nimbus-jose-jwt/examples/remote-jwk-set)

**Kết luận:** Cache JWKS giúp consumer không phải tải public keys ở mọi request, nhưng nó tạo ra độ trễ cập nhật khi AS xoay khóa. Quy trình an toàn là **publish public key mới trước, chuyển signer sau, giữ key cũ cho tới khi token cũ hết hạn rồi mới retire**. Khi consumer gặp `kid` mới, hãy refresh JWKS từ URI tin cậy và xác minh lại; nếu không có key hoặc chữ ký sai, từ chối token. Quản lý đồng thời cache cục bộ, CDN, issuer metadata, algorithm allowlist và emergency revocation sẽ giúp hệ thống OAuth 2.0/OIDC duy trì xác minh JWT ổn định trong cả rotation thường kỳ lẫn sự cố khóa bị lộ.

