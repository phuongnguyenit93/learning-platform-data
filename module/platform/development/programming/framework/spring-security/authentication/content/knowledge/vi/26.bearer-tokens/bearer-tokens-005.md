# JWK Set, thay đổi khóa và giới hạn tin cậy nguồn khóa khi xác thực Bearer JWT

## 1. Vì sao resource server cần JWK Set?

Một API nhận `Authorization: Bearer <access-token>` phải quyết định **token có thật sự do nhà phát hành được tin cậy cấp và dành cho API này không**. Khi access token ở dạng **JWT được ký bằng thuật toán bất đối xứng**, Authorization Server/Identity Provider giữ **private key** để ký, còn Resource Server dùng **public key** tương ứng để kiểm tra chữ ký. *JSON Web Key (JWK)* là cách biểu diễn khóa dưới dạng JSON; *JWK Set (JWKS)* là một tập các JWK, thường được phát qua HTTPS.

Một JWK Set có thể chứa **nhiều public key đang được chấp nhận đồng thời** để có thể thay đổi khóa ký mà không làm mọi access token còn hạn mất hiệu lực ngay. Nhưng **tải được JWKS chưa đủ để tin nó**: ứng dụng phải giới hạn chặt **nguồn khóa**, khóa nào được chọn, thuật toán, issuer, audience, thời hạn và quyền được cấp.

Mục tiêu sau bài học:

1. Đọc cấu trúc `JWK`/`JWKS`, hiểu ý nghĩa `kid`, `kty`, `alg`, `use`, `n`, `e` và vì sao JWK public không chứa khóa ký bí mật.
2. Mô tả được chuỗi xác minh từ JWT/JWS → chọn khóa trong **JWKS đáng tin cậy** → kiểm tra chữ ký → kiểm tra claims → áp dụng authorization.
3. Thực hiện được **key rotation có giai đoạn chồng lấn**: công bố khóa mới, bắt đầu ký bằng khóa mới, giữ khóa cũ cho token còn hạn rồi mới thu hồi.
4. Phân biệt **rotation định kỳ** với **private-key compromise** cần thu hồi khẩn cấp.
5. Thiết lập Spring Boot 3 / Spring Security 6 Resource Server, ràng buộc `issuer-uri`, `jwk-set-uri`, `audiences` và thuật toán.
6. Từ chối đúng trường hợp `kid` giả, `jku`/`x5u` do client chỉ định, JWKS sai issuer, khóa không khớp, cache cũ và token sai audience.

**Phạm vi:** ví dụ dùng Bearer **JWT có chữ ký JWS** (RS256); nếu access token là chuỗi opaque, Resource Server thường dùng introspection tới Authorization Server, không thể lấy “khóa từ JWKS” để kiểm tra chữ ký một opaque token bất kỳ.

## 2. JWK và JWKS thực sự chứa những gì?

Theo **RFC 7517**, một JWK Set là JSON object có thuộc tính `keys` kiểu mảng. Ví dụ hai public RSA key do **cùng một issuer được tin cậy** công bố:

```json
{
  "keys": [
    {
      "kty": "RSA",
      "use": "sig",
      "alg": "RS256",
      "kid": "signing-2026-01",
      "n": "<base64url-public-modulus-of-key-1>",
      "e": "AQAB"
    },
    {
      "kty": "RSA",
      "use": "sig",
      "alg": "RS256",
      "kid": "signing-2026-02",
      "n": "<base64url-public-modulus-of-key-2>",
      "e": "AQAB"
    }
  ]
}
```

**Đây là JSON mẫu để giải thích trường dữ liệu**, hai giá trị `n` là placeholder nên không tạo được RSA public key thật. Trong thực tế `n` là modulus RSA được mã hóa Base64URL, còn `e` thường là RSA exponent 65537 (Base64URL `AQAB`).

| Trường | Ý nghĩa | Điều cần kiểm tra |
| --- | --- | --- |
| `keys` | Danh sách JWK có thể được công bố đồng thời | Chỉ tải từ nguồn JWKS đã được cấu hình đáng tin cậy |
| `kty` | Loại khóa, ví dụ `RSA`, `EC`, `OKP`, `oct` | Phù hợp thuật toán cho phép; không dùng khóa symmetric lẫn asymmetric |
| `kid` | Key ID giúp tìm **khóa ứng viên** | Case-sensitive; không phải bằng chứng tin cậy, không phải định danh issuer toàn cục |
| `use` | Mục đích sử dụng, thường `sig` (ký/xác minh) hoặc `enc` | Không dùng khóa mã hóa cho mục đích ký tùy tiện |
| `key_ops` | Những thao tác được phép, ví dụ `verify` | Nếu có phải nhất quán mục đích và chính sách |
| `alg` | Gợi ý thuật toán khóa, ví dụ `RS256` | Không để trường này tự quyết định tập thuật toán được phép trong ứng dụng |
| `n`, `e` | Public RSA modulus và exponent | Dùng để dựng public key RSA, không phải private key |
| `crv`, `x`, `y` | Tham số khóa elliptic curve khi `kty=EC` | Chỉ chọn curve/algorithm được chính sách cho phép |
| `x5c`, `x5t`, `x5u` | Chứng chỉ và thông tin tham chiếu X.509 tùy chọn | Không tự động tin bất kỳ URL/chứng chỉ nào chỉ vì nó xuất hiện trong JSON/header |

Các tham số private RSA như `d`, `p`, `q`, `dp`, `dq`, `qi` **không được công bố** trong public JWKS. Authorization Server phải giữ private key trong kho bí mật an toàn, tốt hơn có KMS/HSM tùy yêu cầu. Khóa kiểu `oct` là **symmetric secret**; không đưa khóa này lên JWKS công khai.

Một endpoint minh họa: `https://login.example.test/tenant-a/.well-known/jwks.json`. **Đường dẫn JWKS cụ thể không được chuẩn hóa chung cho mọi nhà cung cấp**. Client phải lấy địa chỉ từ cấu hình đáng tin hoặc metadata của issuer đã được cấu hình, như OIDC Discovery/RFC 8414. Đừng tự nối đường dẫn `/.well-known/jwks.json` cho mọi provider rồi giả định đúng.

### JWT header chỉ chọn khóa ứng viên

Header của một JWT được ký có thể mang:

```json
{
  "typ": "at+jwt",
  "alg": "RS256",
  "kid": "signing-2026-02"
}
```

`typ=at+jwt` là minh họa cho profile JWT access token (RFC 9068), **không bắt buộc mọi JWT access token của mọi provider đều có giá trị đó**. Quan trọng: trước khi xác minh chữ ký, **header chưa được xác thực**. Giá trị `kid` có thể do attacker tùy ý đặt. Nó chỉ giúp thư viện tìm một khóa **trong tập khóa mà resource server đã quyết định tin cậy**; nó không cho phép JWT “tự đăng ký” khóa mới.

JWT có cấu trúc `base64url(header).base64url(payload).base64url(signature)`. Với RS256, bytes được ký/xác minh là **hai segment đầu với dấu chấm ở giữa**. Việc decode JSON payload để xem `sub`, `roles` hoặc `iss` **không chứng minh token hợp lệ**; phải verify trước rồi mới tin các claim.

## 3. Quy trình xác minh Bearer JWT đúng ranh giới

Giả sử API chỉ tin issuer `https://login.example.test/tenant-a`, audience `api://orders`, và thuật toán `RS256`.

```text
HTTP request: Authorization: Bearer <JWT>
           |
           v
BearerTokenAuthenticationFilter (Spring Security)
           |
           v
JwtAuthenticationProvider / JwtDecoder
           |
           | 1. Chỉ dùng issuer + jwkSetUri đã được cấu hình tin cậy
           | 2. JWT header alg phải thuộc allowlist (RS256 trong ví dụ)
           | 3. kid chọn khóa ứng viên từ JWKS của đúng issuer
           | 4. Verify chữ ký trên JWS signing input
           | 5. Validate iss, aud, exp, nbf và claims cần thiết
           v
JwtAuthenticationToken + authorities
           |
           | 6. Kiểm tra scope, route, tenant, quyền nghiệp vụ
           v
Controller nếu toàn bộ điều kiện đạt
```

Điều kiện **đều cần**, không thay nhau:

- **Chữ ký:** chứng minh payload được ký bởi private key khớp một public key **đã được tin cậy cho issuer này**. Không chứng minh mọi claim phù hợp với API của bạn.
- **Issuer `iss`:** phải đúng issuer mà ứng dụng **đã cấu hình trước**. Không nhận `iss` bất kỳ rồi theo nó tải JWKS từ Internet.
- **Audience `aud`:** phải chứa định danh API này, ví dụ `api://orders`. Token ký đúng nhưng cấp cho một API khác **không được dùng**.
- **Thời hạn:** xác minh `exp` và `nbf`, clock skew chỉ ở mức hợp lý; nếu dựa vào `iat`, `jti`, `typ`, token type, lifetime hoặc revocation, phải xác định thêm chính sách cụ thể.
- **Thuật toán:** ứng dụng có allowlist, ví dụ RS256; không chấp nhận `alg=none` hay “algorithm confusion” HS256/RS256. Thư viện phải gắn kiểu khóa với thuật toán được phép.
- **Authorization:** `scope`/`scp`, `roles`, tenant, owner/resource permission được kiểm tra **sau authentication**; chữ ký hợp lệ không cấp quyền admin tự động.

Trong Spring Security Resource Server, `JwtDecoder` nhận nhiệm vụ verify/validate; `JwtAuthenticationConverter` ánh xạ scope sang authorities (mặc định `SCOPE_...`), rồi cấu hình `SecurityFilterChain` xử lý authorization.

### Một ví dụ cần bác bỏ

Token A có chữ ký hợp lệ từ **Issuer A**, nhưng `aud=api://billing` trong khi request đến Orders API. Nếu ứng dụng chỉ kiểm tra chữ ký và `exp` thì token có thể bị dùng nhầm đối tượng nhận (cross-audience token substitution). Phải kiểm tra `aud=api://orders` để từ chối A. Tương tự, token do Issuer B phát không được chấp nhận chỉ vì Issuer B cũng có endpoint JWKS và `kid` giống Issuer A.

## 4. Nguồn khóa tin cậy được xác định như thế nào?

**Tin một khóa ≠ tin một chuỗi JSON.** Theo RFC 7517 và RFC 8725, độ tin cậy đến từ cách ứng dụng **thiết lập mối quan hệ giữa issuer, URL/metadata và khóa**, sau đó giới hạn token nào được chấp nhận.

### 4.1. Cấu hình issuer làm trust anchor

Với OAuth2/OIDC, resource server thường có cấu hình tĩnh/được quản trị:

```text
trusted issuer: https://login.example.test/tenant-a
expected aud:   api://orders
allowed alg:    RS256
JWKS endpoint:  https://login.example.test/tenant-a/keys
```

Tên miền trên chỉ là mẫu. Nếu dùng discovery, thư viện tìm tài liệu metadata **cho issuer đã cấu hình** và đọc `jwks_uri` từ đó. Phải verify TLS/certificate, đúng host và issuer metadata; cấu hình redirect, DNS và network egress cần tránh bị trỏ sang nguồn không đáng tin.

Một endpoint JWKS có thể trả 200 OK và JSON đúng chuẩn nhưng vẫn **không đáng tin** nếu không thuộc issuer được cho phép. Nếu attacker có thể thay URL JWKS hoặc phản hồi qua TLS proxy không an toàn, attacker có thể thay public key, rồi tự ký token giả mà ứng dụng chấp nhận.

### 4.2. Không để JWT yêu cầu tải khóa theo ý nó

Một JWT/JWS header có thể chứa:

- `kid`: chỉ định danh khóa ứng viên, phải so trong **JWKS được ứng dụng tin**.
- `jku`: URL JWKS do header gợi ý.
- `x5u`: URL chứng chỉ.
- `jwk`: public key nhúng trực tiếp trong header.
- `x5c`: chứng chỉ nhúng.

**Không tự động tin hoặc fetch `jku`/`x5u` lấy từ token chưa xác minh.** Làm vậy có thể tạo lỗ hổng **SSRF**, gọi tới mạng nội bộ/metadata service, hoặc để attacker host JWKS chứa khóa do chính attacker tạo rồi ký token giả. Nếu use case đặc biệt buộc dùng các header này, phải có allowlist nguồn chặt, xác minh sở hữu khóa/chứng chỉ theo trust policy và tuyệt đối không chuyển cookie/Authorization header ra URL tùy ý. Cách mặc định an toàn của API là **bỏ qua URL khóa nằm trong JWT** và chỉ dùng nguồn cấu hình.

Tương tự, `jwk` nhúng trong token **không tự trở thành khóa tin cậy**; “token nói hãy tin khóa của tôi” là chu trình tự xác nhận vô nghĩa. Chuỗi chứng chỉ trong `x5c` không mặc nhiên an toàn nếu không kiểm tra PKIX chain và quan hệ issuer phù hợp.

### 4.3. Kid collision và algorithm confusion

- `kid` phân biệt chữ hoa/thường, không đảm bảo duy nhất giữa các provider. Tên như `key-1` có thể tồn tại ở cả Issuer A và B. Key lookup phải **được giới hạn trong key set của issuer đã chọn**.
- Đừng chèn `kid` chưa lọc vào path/file name/SQL/LDAP query; RFC 8725 lưu ý injection qua `kid`. Cách thông dụng là để thư viện JWT chọn khóa từ tập đã tải.
- Tập thuật toán được phép là quyết định **từ cấu hình ứng dụng**. Không đọc `alg=HS256` rồi lấy public RSA key làm HMAC secret; không chấp nhận `alg=none`; không coi trường `alg` của một JWK attacker kiểm soát là chính sách.
- Dùng public key và private key đúng mục đích: public key xác minh chữ ký bất đối xứng, không ký được token; private key phải ở issuer.
- JWKS có thể chứa khóa dùng `enc` cho mã hóa, không áp dụng làm khóa xác minh chữ ký `sig`.

## 5. Spring Boot 3.x / Spring Security 6.x: cấu hình Resource Server

### 5.1. Dependency

Tạo ứng dụng Spring Boot 3.x (Java 17+, Servlet/Spring MVC). Trong project Gradle có Spring Boot plugin/dependency management, bổ sung:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Spring Boot starter Resource Server cung cấp thành phần xác thực Bearer JWT và JOSE/JWT. Code sau **không cần tự viết parser, tải JWKS, tạo `PublicKey` hoặc kiểm tra signature thủ công**.

### 5.2. Cách A: issuer discovery

Trong `src/main/resources/application.yml`:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.test/tenant-a
          audiences: api://orders
          jws-algorithms: RS256
```

Khi provider hỗ trợ OIDC Discovery hoặc OAuth Authorization Server Metadata, Spring có thể tìm metadata từ `issuer-uri`, lấy `jwks_uri` và sử dụng public keys để verify chữ ký, đồng thời validate `iss`. `audiences` yêu cầu audience thuộc API hiện tại; `jws-algorithms` giới hạn thuật toán chấp nhận. URL `example.test` là placeholder, nên chỉ chạy được sau khi dùng issuer thật.

Đừng coi việc decoder trả về payload có `sub` là đủ: các validator mới quyết định `Jwt` đã đáng tin và phù hợp tài nguyên.

### 5.3. Cách B: pin JWKS URI đồng thời giữ issuer và audience

Nếu muốn API có JWKS URL cố định hoặc không cần discovery lúc khởi động:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.test/tenant-a
          jwk-set-uri: https://login.example.test/tenant-a/keys
          audiences: api://orders
          jws-algorithms: RS256
```

Khi cung cấp đồng thời `issuer-uri` và `jwk-set-uri`, Spring Boot dùng URI trực tiếp thay bước tìm endpoint qua metadata và **vẫn validate claim `iss`**. Thực tế thời điểm kết nối JWKS, hoạt động cache và refresh phụ thuộc phiên bản/cấu hình decoder. **Đừng chỉ cấu hình JWKS mà quên issuer và audience**: việc một public key verify được chữ ký là chưa đủ để quyết định token này dành cho hệ thống bạn.

Hai mẫu là **hai lựa chọn triển khai**, không cần cấu hình hai Resource Server trùng nhau. URI JWKS phải do operator quản lý theo issuer; không lấy từ `iss`, `kid` hoặc `jku` do request tự khai mà không qua chính sách tin cậy.

### 5.4. SecurityFilterChain áp dụng Bearer authentication + scope

Tạo `src/main/java/com/example/api/ApiSecurityConfig.java`:

```java
package com.example.api;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/api/orders/**")
                            .hasAuthority("SCOPE_orders.read")
                        .anyRequest().authenticated())
                // Chỉ với API xác thực bằng Bearer header, không dùng cookie.
                .csrf(AbstractHttpConfigurer::disable)
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .oauth2ResourceServer(oauth2 -> oauth2
                        .jwt(Customizer.withDefaults()))
                .build();
    }
}
```

Ở cấu hình ví dụ, endpoint `/api/orders/**` cần scope `orders.read`. Spring Resource Server ánh xạ `scope`/`scp` thành authority có prefix `SCOPE_` theo quy ước mặc định. **CSRF bị tắt chỉ vì đây là API thuần Bearer header và không dùng session cookie để xác thực request**. Nếu cùng ứng dụng có browser form login/cookie, phải thiết kế riêng security chain và CSRF protection phù hợp; không tắt toàn hệ thống theo phản xạ.

Tạo `src/main/java/com/example/api/OrdersController.java`:

```java
package com.example.api;

import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrdersController {

    @GetMapping("/api/orders")
    public Map<String, String> orders(@AuthenticationPrincipal Jwt jwt) {
        return Map.of(
                "subject", jwt.getSubject(),
                "issuer", jwt.getIssuer().toString());
    }
}
```

Project cần class `@SpringBootApplication` trong package `com.example.api` hoặc package cha để Spring scan hai class này. Nếu có token JWT còn hạn, được ký bằng khóa trong JWKS của issuer đúng, audience chứa `api://orders` và scope chứa `orders.read`, request:

```http
GET /api/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer <signed-access-token>
```

có thể trả `200 OK`. Nếu token thiếu/hỏng chữ ký/hết hạn/sai issuer/sai audience, Resource Server thường trả `401 Unauthorized` với Bearer challenge. Nếu **token hợp lệ** nhưng thiếu authority `SCOPE_orders.read`, Spring Security trả `403 Forbidden`. Không in access token nguyên văn vào log.

### 5.5. Khi tự tạo JwtDecoder, phải giữ đủ validators

Spring Boot có thể tự tạo `JwtDecoder` dựa trên các property ở trên. Nếu bạn tự khai báo `@Bean JwtDecoder` hoặc chỉ gọi `NimbusJwtDecoder.withJwkSetUri(...).build()`, bạn đã thay đường auto configuration; **không được giả định issuer/audience validators của Boot vẫn tự áp dụng cho bean mới**.

Đoạn class sau là một **phương án thay thế** cho Boot auto-config ở mục 5.2/5.3, minh họa rõ ràng giới hạn thuật toán và kiểm tra claim. Dùng cùng `SecurityFilterChain` nhưng chỉ nên có **một** nguồn tạo `JwtDecoder`:

```java
package com.example.api;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
public class ExplicitJwtDecoderConfig {

    private static final String ISSUER =
            "https://login.example.test/tenant-a";
    private static final String JWKS =
            "https://login.example.test/tenant-a/keys";
    private static final String AUDIENCE = "api://orders";

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder = NimbusJwtDecoder.withJwkSetUri(JWKS)
                .jwsAlgorithm(SignatureAlgorithm.RS256)
                .build();

        OAuth2TokenValidator<Jwt> issuerAndTime =
                JwtValidators.createDefaultWithIssuer(ISSUER);

        OAuth2TokenValidator<Jwt> audience = jwt ->
                jwt.getAudience().contains(AUDIENCE)
                        ? OAuth2TokenValidatorResult.success()
                        : OAuth2TokenValidatorResult.failure(
                                new OAuth2Error("invalid_token",
                                        "Unexpected audience", null));

        decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(
                        issuerAndTime, audience));

        return decoder;
    }
}
```

Ý nghĩa: JWKS là **nguồn khóa được operator chọn**, RS256 là **thuật toán được phép**, còn validator kiểm tra issuer/thời gian và audience. `JwtValidators.createDefaultWithIssuer` chứa validator chuẩn liên quan đến issuer và thời gian. Nếu hệ thống cần quy tắc `typ`, `azp`, tenant, `jti`, token lifetime hoặc custom scopes thì bổ sung chính sách thích hợp, **không bỏ các validator chuẩn**.

## 6. Key rotation định kỳ: công bố trước, ký sau, thu hồi cuối

Hãy gọi hai cặp RSA khóa ký là **K1** (cũ) và **K2** (mới). JWK Set chỉ công bố **public** K1/K2; private key giữ tại issuer. Các token đã phát với K1 vẫn có thể còn hiệu lực cho đến hết `exp`.

| Mốc | Issuer ký token mới bằng | JWKS public keys | API phải xử lý |
| --- | --- | --- | --- |
| T0 — bình thường | Private K1 | Public K1 | Token K1 hợp lệ được chấp nhận |
| T1 — chuẩn bị chuyển | Private K1 | **Public K1 + K2** | API có thời gian refresh cache và biết K2 |
| T2 — bắt đầu ký mới | **Private K2** | **Public K1 + K2** | Token K1 còn hạn và token K2 đều được verify |
| T3 — hết cửa sổ token K1 | Private K2 | **Public K1 + K2** cho tới khi không còn token K1 hợp lệ | Không đột ngột gỡ K1 khi token K1 còn hạn |
| T4 — dọn khóa cũ | Private K2 | Chỉ public K2 | Token K1 bị từ chối; K2 tiếp tục hợp lệ |

**Tại sao phải công bố trước (pre-publish)?** Resource Server thường cache JWKS. Nếu issuer bắt đầu ký ngay bằng K2 khi các API chỉ biết K1, nhiều request sẽ bị 401 do `kid` mới chưa có trong cache. Cần công bố K2 trước, theo dõi cache refresh/fetch success, rồi mới dùng private K2 ký token.

**Tại sao phải giữ khóa cũ thêm một thời gian?** JWT access token ký bằng K1 **không được ký lại chỉ vì rotation**. Khi token còn hạn, API cần public K1 để xác minh. Cửa sổ chồng lấn phụ thuộc **thời hạn token cũ tối đa**, clock skew, cách cache/refresh JWKS, retry và độ trễ phân phối. Không có một con số phút cố định đúng cho mọi hệ thống.

**Dùng `kid` riêng cho mỗi public key** và tránh tái sử dụng cùng kid cho khóa mới trong một issuer. Nếu K2 cũng mang kid “K1”, cache có thể giữ public key cũ nhưng issuer ký bằng private key mới, gây lỗi xác minh khó chẩn đoán.

Cách tính thực tế khi lập lịch: nếu access token K1 được phát sát thời điểm T2 và sống tối đa 15 phút với clock skew cho phép 60 giây, thì giữ public K1 **ít nhất qua thời điểm token cuối cùng được phát bằng K1 hết hiệu lực**, cộng ngân sách vận hành cần thiết. Cần biết **thời điểm token K1 cuối cùng đã phát**, không chỉ thời điểm K2 được công bố.

## 7. Thu hồi khẩn khi private key bị lộ

Rotation định kỳ có mục tiêu **không gián đoạn**; khi private K1 bị lộ, mục tiêu đổi thành **ngăn token giả do attacker ký**. Giữ public K1 để token cũ vẫn pass là rủi ro có thật.

Quy trình xử lý tình huống nghi bị compromise:

1. Ngừng sử dụng private K1 để ký, cô lập vật liệu khóa, xác định phạm vi ảnh hưởng và phát hành K2 an toàn.
2. Gỡ hoặc vô hiệu hóa **public K1 trong nguồn khóa đáng tin** càng nhanh càng hợp lý; bắt buộc lưu ý **cache JWKS của các resource server có thể vẫn còn K1**.
3. Có kế hoạch invalidation/refresh cache và chính sách fail closed cho các API. Đừng chỉ xóa K1 trên endpoint rồi khẳng định tất cả API đã ngừng tin K1.
4. Chấp nhận việc các token còn hạn ký bằng K1 **có thể bị từ chối**; yêu cầu người dùng/client lấy token mới qua luồng an toàn.
5. Nếu mức bảo đảm cần thu hồi tức thì trước TTL, cân nhắc denylist `jti`, introspection/thu hồi qua hệ thống tập trung, giảm token lifetime, thay trust configuration hoặc cơ chế kiểm soát bổ sung. Các cơ chế này phải được thiết kế trước; JWT self-contained chỉ có `exp` không cung cấp revocation tức thời.
6. Quan sát tỷ lệ lỗi 401/403, những API instance vẫn còn tin K1 và kiểm tra log/sự kiện khóa để phát hiện token giả hoặc ảnh hưởng vận hành.

**Không có giải pháp “xóa key khỏi JWKS là revoke tức thì mọi token”.** Từ góc nhìn Resource Server, token đã ký có thể tiếp tục verify bằng public K1 còn trong cache cho đến khi cache hết hạn/bị vô hiệu hóa hoặc chính sách chặn bổ sung có hiệu lực.

## 8. Cache và khả dụng của JWKS: khi nào refresh, khi nào từ chối?

Spring Security Resource Server dùng thư viện JWT/JWK có cơ chế cache và cập nhật khóa; theo tài liệu Spring Security, nó có thể tự cập nhật khóa khi Authorization Server công bố khóa mới. **Thời điểm refresh/TTL/behavior khi gặp kid lạ phụ thuộc phiên bản thư viện, decoder và cấu hình cache**, vì vậy hãy kiểm chứng thực tế, không assume “unknown kid luôn fetch ngay”.

| Tình huống | Hành vi đúng của Resource Server | Điều cần quan sát |
| --- | --- | --- |
| JWT có kid K1 và K1 có trong trusted cache | Verify chữ ký bằng K1 rồi validate claims | Token hợp lệ mới được nhận |
| JWT có kid K2 mới, cache còn K1 | Có thể cần lấy JWKS mới; nếu chưa có trusted K2 thì **fail closed** | Refresh attempt, cache age, HTTP lỗi, 401 tạm thời |
| JWKS server trả 5xx/timeout | Không được bỏ qua signature verification; chính sách sử dụng cached trusted keys (nếu còn hiệu lực) cần rõ | Tỷ lệ 401, JWKS fetch failures, TTL |
| JWKS trả JSON sai/thiếu keys | Từ chối token chưa có khóa đáng tin; cảnh báo vận hành | Parse error, empty set, schema mismatch |
| JWKS bị thay toàn bộ ngoài lịch | Cảnh báo change/unexpected kid; xác minh nguồn/incident | Dấu vết publication và thay đổi key set |
| Token alg không cho phép | Từ chối, không thử mọi thuật toán/khóa bừa bãi | JWT decode failure |
| Key K1 bị thu hồi nhưng server cache K1 | Có thể vẫn verify chữ ký token K1 đến khi cache bị vô hiệu hóa | Cần cơ chế forced refresh/deny policy |

Các điểm vận hành:

- Dùng HTTPS xác thực chứng chỉ, timeout hợp lý, giới hạn kích thước phản hồi JWKS và số khóa, rate limiting/backoff cho request refresh. Không cho mỗi JWT có random kid khiến hệ thống liên tục gọi outbound tới server.
- Có thể dùng HTTP cache semantics như `Cache-Control`/`ETag` **nếu cách client/decoder hỗ trợ**, nhưng hành vi chính xác phải được kiểm chứng. Tùy chỉnh cache không được khiến khóa đã bị thu hồi bị tin vô thời hạn.
- Tách lỗi mạng JWKS khỏi lỗi JWT sai chữ ký để điều tra; **không ghi JWT đầy đủ** khi bật debug.
- Quản lý nhiều instance/region: các instance có cache tuổi khác nhau; canary test K2 trên từng vùng trước khi đổi ký.
- Kiểm tra retry/recovery và cảnh báo khả dụng cho provider; một JWKS endpoint bị lỗi kéo dài có thể làm token mới không được xác minh.

## 9. Ví dụ Java 17 độc lập: public JWK và vòng đời K1 → K2

Ví dụ sau tạo RSA keypair trong bộ nhớ, xuất **chỉ public modulus/exponent** thành một cấu trúc tương đương JWK và dùng chữ ký RS256 để mô phỏng ba giai đoạn rotation. Nó dùng **JDK 17+ thuần**, không phụ thuộc Spring và không phát access token có thể dùng thật.

**Giới hạn bài thực hành:** lớp `DemoJws` chỉ giữ lại nội dung đã ký, kid và chữ ký, không có parser JSON/JWT production, không validate `iss`/`aud`/`exp` hoặc network trust. Học xong phải dùng `JwtDecoder` của thư viện duy trì, **không sao chép ví dụ này thành bộ xác minh JWT production**.

Lưu thành `JwkRotationDemo.java`:

```java
import java.math.BigInteger;
import java.nio.charset.StandardCharsets;
import java.security.KeyFactory;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.Signature;
import java.security.interfaces.RSAPublicKey;
import java.security.spec.RSAPublicKeySpec;
import java.util.Arrays;
import java.util.Base64;
import java.util.HashMap;
import java.util.Map;

public class JwkRotationDemo {

    record PublicJwk(String kid, String n, String e) {}
    record DemoJws(String kid, String signingInput, byte[] signature) {}

    static String b64url(byte[] value) {
        return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(value);
    }

    static String unsigned(BigInteger value) {
        byte[] bytes = value.toByteArray();
        if (bytes[0] == 0) {
            bytes = Arrays.copyOfRange(bytes, 1, bytes.length);
        }
        return b64url(bytes);
    }

    static PublicJwk publicJwk(String kid, PublicKey key) {
        RSAPublicKey rsa = (RSAPublicKey) key;
        return new PublicJwk(
                kid, unsigned(rsa.getModulus()),
                unsigned(rsa.getPublicExponent()));
    }

    static PublicKey toPublicKey(PublicJwk jwk) throws Exception {
        BigInteger n = new BigInteger(
                1, Base64.getUrlDecoder().decode(jwk.n()));
        BigInteger e = new BigInteger(
                1, Base64.getUrlDecoder().decode(jwk.e()));
        return KeyFactory.getInstance("RSA")
                .generatePublic(new RSAPublicKeySpec(n, e));
    }

    static DemoJws sign(String kid, PrivateKey privateKey)
            throws Exception {
        String header = "{\"alg\":\"RS256\",\"kid\":\"" + kid + "\"}";
        String payload = "{\"sub\":\"alice\"}";

        String input = b64url(header.getBytes(StandardCharsets.UTF_8))
                + "."
                + b64url(payload.getBytes(StandardCharsets.UTF_8));

        Signature rs256 = Signature.getInstance("SHA256withRSA");
        rs256.initSign(privateKey);
        rs256.update(input.getBytes(StandardCharsets.US_ASCII));

        return new DemoJws(kid, input, rs256.sign());
    }

    // Chỉ minh họa dùng kid tìm trong trust store cố định.
    // Production phải parse JWT an toàn và validate mọi claim.
    static boolean verify(DemoJws token, Map<String, PublicJwk> trusted)
            throws Exception {
        PublicJwk jwk = trusted.get(token.kid());
        if (jwk == null) {
            return false;
        }

        Signature rs256 = Signature.getInstance("SHA256withRSA");
        rs256.initVerify(toPublicKey(jwk));
        rs256.update(
                token.signingInput().getBytes(StandardCharsets.US_ASCII));
        return rs256.verify(token.signature());
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);

        KeyPair old = generator.generateKeyPair();
        KeyPair next = generator.generateKeyPair();
        KeyPair attacker = generator.generateKeyPair();

        PublicJwk k1 = publicJwk("k-2026-01", old.getPublic());
        PublicJwk k2 = publicJwk("k-2026-02", next.getPublic());

        DemoJws oldToken = sign(k1.kid(), old.getPrivate());
        DemoJws newToken = sign(k2.kid(), next.getPrivate());
        DemoJws forged = sign(k2.kid(), attacker.getPrivate());

        Map<String, PublicJwk> trusted = new HashMap<>();

        // T0: chỉ có K1 trong trusted JWKS.
        trusted.put(k1.kid(), k1);
        System.out.println("oldBefore=" + verify(oldToken, trusted));

        // T1/T2: K1 + K2 được công bố trong giai đoạn chồng lấn.
        trusted.put(k2.kid(), k2);
        System.out.println("oldOverlap=" + verify(oldToken, trusted));
        System.out.println("newOverlap=" + verify(newToken, trusted));

        // Attacker đặt cùng kid=K2 nhưng dùng private key khác.
        System.out.println("forgedSameKid=" + verify(forged, trusted));

        // T4: gỡ K1 khỏi trusted set sau khi token cũ hết hạn.
        trusted.remove(k1.kid());
        System.out.println("oldAfter=" + verify(oldToken, trusted));
        System.out.println("newAfter=" + verify(newToken, trusted));
    }
}
```

Chạy trong thư mục chứa file:

```bash
javac JwkRotationDemo.java
java JwkRotationDemo
```

Stdout xác định (khóa sinh ngẫu nhiên nên bytes khác nhau mỗi lần, nhưng kết quả boolean giữ nguyên):

```text
oldBefore=true
oldOverlap=true
newOverlap=true
forgedSameKid=false
oldAfter=false
newAfter=true
```

Giải thích từng kết quả:

- `oldBefore=true`: một JWS ký bằng private K1 xác minh được bằng public K1.
- `oldOverlap=true` và `newOverlap=true`: trong giai đoạn cả hai khóa được công bố, token đã ký bằng mỗi private key đều có khóa xác minh đúng.
- `forgedSameKid=false`: attacker đổi header kid thành tên K2 nhưng **không có private K2**, chữ ký không qua. `kid` không phải quyền được cấp phép.
- `oldAfter=false`: khi K1 bị loại khỏi **tập khóa đáng tin cậy**, verifier không còn chấp nhận chữ ký của token K1 trong mini-lab.
- `newAfter=true`: K2 tiếp tục hoạt động.

Bài lab dùng `DemoJws.kid` như thông tin đã có, **không tự cài parser cho token nhận từ Internet**. Verify thực tế phải kiểm tra cấu trúc JWS, protected header, thuật toán, public key trust, issuer, audience, lifetime và scopes; Java `Signature` đơn lẻ không giải quyết hết.

## 10. Kiểm chứng end-to-end khi phát hành hoặc xoay khóa

Trên môi trường test có Authorization Server phát JWT RSA thật và JWKS do mình quản lý, nên tạo ít nhất các test độc lập sau. Không chỉ mock `JwtDecoder` trả về một `Jwt` có sẵn, vì như vậy bỏ qua chữ ký/JWKS mà bài cần kiểm chứng.

| Ca | Dữ liệu/khóa đầu vào | Kỳ vọng |
| --- | --- | --- |
| K1 ban đầu | JWKS=[K1], JWT do private K1 ký, iss/aud/scope đúng | 200 cho endpoint được phép |
| Prepublish K2 | JWKS=[K1,K2], vẫn ký K1 | Token K1 tiếp tục 200 |
| Bắt đầu ký K2 | JWKS=[K1,K2], JWT K2, cache mới được cập nhật | Token K2 200, K1 còn hạn vẫn 200 |
| Sau expiry K1 | JWKS=[K2], K1 không còn trong trusted cache | Token K1 401; K2 200 |
| Forged kid | JWT mang kid K2 nhưng ký bằng private attacker | 401 |
| Kid không tồn tại | JWT mang kid không có trong trusted JWKS | 401; tuyệt đối không tự chọn public key từ token |
| Wrong issuer | Token ký đúng nhưng `iss` không được allow | 401 |
| Wrong audience | Token ký đúng nhưng `aud=api://billing` | 401 |
| Expired / nbf future | Token chữ ký đúng nhưng `exp` đã qua / `nbf` chưa đến | 401 (ngoài clock skew cho phép) |
| Wrong alg | `alg=none`, HS256 hoặc thuật toán không allow | 401 |
| Missing scope | Token chữ ký/claims hợp lệ nhưng thiếu `orders.read` | 403 |
| Malicious jku | JWT thêm `jku=https://attacker.example.test/keys` | Không fetch nguồn ngoài allowlist; JWT không được attacker tự làm tin |
| JWKS 5xx | Cache cũ có K1, request K2 mới | Không bypass chữ ký; quan sát lỗi refresh, fail closed nếu không có key |
| Emergency retire | Key K1 bị nghi lộ, cập nhật deny policy/refresh cache | Các instance dần/ngay lập tức theo cơ chế incident đã thiết kế phải từ chối K1 |
| Multi-issuer | Token Issuer B ký hợp lệ, nhưng API chỉ trust Issuer A | 401 ngay cả khi kid trùng tên |

Với những test “401” cần xác minh nguyên nhân **là validation thực**, không phải controller chưa khởi động, kết nối TLS lỗi chung hoặc MockMvc gắn sẵn principal. Để test signed JWT thực, sử dụng keypair riêng, mock HTTPS JWKS endpoint hoặc Authorization Server test, cấu hình Spring Resource Server trỏ tới mock issuer do test kiểm soát. Phép thử chỉ dùng `jwt()` mock principal của Spring Security Test giúp kiểm authorization nhưng **không chứng minh JWKS rotation hoạt động**.

### Quan sát mà không lộ bí mật

- Theo dõi nhóm lỗi: `invalid_token` do chữ ký/issuer/audience/expiry, unknown kid, JWKS fetch failed, 401 và 403.
- Ghi metrics về **số lần refresh JWKS, cache age, endpoint availability, tập kid đang công bố**; tránh log cả token hoặc toàn bộ Authorization header.
- Khi chuyển K2, theo dõi phân phối key từng instance/region; khi xóa K1, xác nhận những instance còn giữ cache K1 đã được xử lý.
- Dùng correlation ID của request và sự kiện phiên bản key set, nhưng không cho untrusted kid bơm dữ liệu vào tên metric vô hạn làm nổ cardinality.

## 11. Lỗi phổ biến và chẩn đoán

| Hiện tượng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| 401 sau khi issuer bắt đầu ký K2 | JWKS chưa công bố K2, cache chưa refresh, dùng lại kid cũ | Prepublish K2, bảo đảm cache/discovery và kiểm tra kid |
| 401 chỉ trên một số instance | Cache JWKS các instance khác tuổi, network/egress khác nhau | Kiểm tra cache/refresh từng instance và khả dụng nguồn JWKS |
| “JWT signature valid” nhưng API vẫn từ chối | Sai `iss`/`aud`/`exp`/scope hoặc policy | Phân biệt 401 authentication với 403 authorization |
| Token từ issuer khác vẫn vào được | Tin JWKS quá rộng hoặc thiếu issuer/audience binding | Mỗi issuer gắn JWKS, algorithm, audience policy |
| Kẻ ngoài tự ký token rồi pass | API tin `jku`/`jwk` do JWT cung cấp | Chỉ dùng nguồn khóa cấu hình đáng tin và verify chính sách |
| Token `alg=none` vẫn pass | Cho JWT chọn thuật toán hoặc decoder tùy biến thiếu kiểm | Allowlist thuật toán, dùng thư viện được duy trì |
| JWKS leak private key | Trộn public JWKS với private JWK chứa `d` | Tách kho bí mật, rotate key khẩn và điều tra |
| Gỡ K1 quá sớm | Token K1 vẫn trong hạn và Resource Server cần K1 | Giữ overlap đủ đến expiry nếu rotation bình thường |
| Gỡ K1 mà vẫn nhận token K1 | Cache khóa cũ chưa hết hạn hoặc decoder dùng key store khác | Invalidate cache, cập nhật trust policy, audit config |
| JWKS down → mọi token fail | Thiếu key cache hợp lệ, hết TTL, network timeout | Thiết kế availability/cache/fail closed và SLO |
| Dùng ID Token làm Bearer API token | Lẫn loại JWT, sai audience/typ/token purpose | Tách ID Token và access token; verify audience/token profile |
| Tự viết `JwtDecoder` rồi mất issuer validation | Bean custom thay Boot auto-config | Gắn `JwtValidators.createDefaultWithIssuer` và aud validator |

**Cần phân biệt token revoked với signing key retired.** Xóa public key làm **mọi token ký bằng key đó** không còn verify sau khi các verifier cập nhật. Thu hồi **một** access token cụ thể thường cần cơ chế khác như denylist `jti`, introspection hoặc token lifetime ngắn; không thể xóa cả key chỉ để thu hồi một token mà không ảnh hưởng các token khác.

## 12. Checklist đánh giá mức tin cậy nguồn khóa

1. **Nguồn JWKS:** URL/issuer được xác định trước bởi cấu hình hoặc metadata của issuer đã tin; TLS/certificate, DNS/redirect/egress được quản trị; không tự nhận URL khóa theo JWT header.
2. **Khóa:** chỉ công bố public key, private key bảo vệ riêng; kiểm tra `kty`, `use/key_ops`, `alg` phù hợp; `kid` chỉ chọn ứng viên trong tập đúng issuer.
3. **JWT:** verify chữ ký JWS, allowlist thuật toán, validate `iss`, `aud`, `exp`, `nbf`, token type/claim cần thiết; tránh HS/RS confusion và `none`.
4. **Ủy quyền:** scope/role/tenant/quyền tài nguyên được quyết định riêng, sau khi authentication pass.
5. **Rotation thường kỳ:** K2 được công bố **trước** khi ký; K1+K2 cùng xuất hiện trong overlap; chỉ gỡ K1 sau hạn token cuối cùng và ngân sách clock/cache phù hợp.
6. **Sự cố khóa:** có phương án ngừng tin K1, refresh/invalidate cache, cân đối downtime và thu hồi access token có thể giả mạo.
7. **Cache/khả dụng:** thời gian refresh, unknown kid, timeout, rate limit, lỗi JWKS, nhiều instance và fail closed đã được test.
8. **Nhiều issuer:** mỗi issuer có trust policy riêng; không chung kho public keys để chấp nhận token tùy ý; kid không duy nhất toàn hệ thống.
9. **Negative tests:** sai kid/signature/alg/issuer/audience/exp, attacker `jku`, key rotation ở cache cũ và khóa bị thu hồi đều có kết quả kiểm chứng.

Nếu chỉ nhớ một quy trình: **Chọn issuer tin cậy trước → tải JWKS thuộc issuer đó → dùng kid chọn ứng viên, verify chữ ký theo thuật toán allowlist → kiểm tra claims và quyền → quản lý rotation cùng cache và incident.** Một JWT tự cung cấp “khóa để tin tôi” không được làm thay bước đầu tiên.

### Tài liệu chuẩn

- [RFC 7517 — JSON Web Key (JWK), JWK Set, Key Provenance and Trust](https://www.rfc-editor.org/rfc/rfc7517)
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515)
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 8725 — JWT Best Current Practices; algorithm verification, key provenance, jku/x5u risks](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [Spring Security 6.5 — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html)
- [Spring Security 6.5 — Bearer Token Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/bearer-tokens.html)
