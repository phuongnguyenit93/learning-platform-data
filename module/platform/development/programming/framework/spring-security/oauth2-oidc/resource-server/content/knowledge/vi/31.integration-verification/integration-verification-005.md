# Từ chối ID token hoặc token dành cho API khác theo hợp đồng

## 1. Mục tiêu: chữ ký hợp lệ vẫn chưa đủ

Một JWT có thể được ký đúng bởi Authorization Server, có issuer đáng tin và còn hạn, nhưng Resource Server vẫn phải từ chối nếu token đó không được phát hành để gọi API này.

Hai trường hợp cần phân biệt:

1. **OIDC ID token** được phát hành cho OIDC client để xác nhận kết quả đăng nhập. Nó không phải access token để gọi Resource Server.
2. **Access token dành cho API khác** có thể là access token hợp lệ, nhưng audience/resource của nó không khớp API đang nhận request.

Ví dụ hệ thống có ba thành phần:

```text
OIDC client:       web-client
Orders API:        orders-api
Inventory API:     inventory-api

ID token:
  aud = web-client
  purpose = xác nhận đăng nhập cho web-client

Access token A:
  aud = orders-api
  purpose = gọi Orders API

Access token B:
  aud = inventory-api
  purpose = gọi Inventory API
```

Nếu Orders API nhận ID token hoặc Access token B, nó phải từ chối dù chữ ký có thể được xác minh bằng cùng public key của issuer.

**Quy tắc cốt lõi:** xác minh chữ ký trả lời “token có được ký bởi key đáng tin không?”. Kiểm tra audience và token profile trả lời “token này có được phát hành để dùng tại API hiện tại không?”. Resource Server phải làm cả hai.

## 2. ID token và access token có mục đích khác nhau

OpenID Connect xây dựng trên OAuth 2.0 và bổ sung ID token để truyền kết quả xác thực người dùng tới Relying Party (OIDC client).

| Đặc điểm | ID token | Access token |
| --- | --- | --- |
| Mục đích | Xác nhận thông tin authentication cho OIDC client. | Cấp quyền truy cập protected resource. |
| Audience điển hình | Client ID của ứng dụng đăng nhập. | Identifier của Resource Server/API. |
| Bên sử dụng chính | OIDC client/Relying Party. | Resource Server. |
| Claim thường gặp | iss, sub, aud, exp, iat; có thể có nonce, auth_time, at_hash, azp. | iss, sub, aud, exp, iat, scope/scp; có thể có client_id, jti, cnf. |
| Quyết định được phép gọi API? | Không tự cấp quyền gọi API. | Có thể được dùng làm credential API nếu vượt mọi validation và authorization policy. |

Ví dụ ID token:

```json
{
  "iss": "https://login.example.test",
  "sub": "user-123",
  "aud": ["web-client"],
  "exp": 1893456000,
  "iat": 1893452400,
  "nonce": "login-request-nonce",
  "auth_time": 1893452300
}
```

Ví dụ access token dành cho Orders API:

```json
{
  "iss": "https://login.example.test",
  "sub": "user-123",
  "aud": ["orders-api"],
  "exp": 1893456000,
  "iat": 1893452400,
  "scope": "orders:read orders:write"
}
```

Hai token có thể cùng issuer, cùng subject và được ký bằng cùng key. Chúng vẫn có mục đích và audience khác nhau.

### 2.1. ID token không phải access token chỉ vì cả hai đều là JWT

JWT là định dạng biểu diễn claims có chữ ký hoặc mã hóa. Nó không tự xác định mục đích của token. Một ID token và một access token có thể đều là compact JWS:

```text
base64url(header).base64url(payload).base64url(signature)
```

Do đó, kiểm tra “parse được JWT” hoặc “signature hợp lệ” không đủ để quyết định token có được dùng ở API hay không.

### 2.2. Không gửi ID token tới Resource Server

OIDC client dùng ID token để xác minh authentication response theo OIDC contract. Khi gọi API, client phải dùng access token được cấp cho resource đó:

```http
GET /api/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token-for-orders-api>
```

Không gửi ID token trong Authorization header. Việc ID token có sub, tên người dùng hoặc email không biến nó thành API credential.

## 3. Audience là ranh giới giữa các API

Claim aud xác định recipient hoặc recipients mà JWT được phát hành cho. Resource Server phải so sánh audience đã được xác minh với identifier của chính API.

Ví dụ:

```json
{
  "iss": "https://login.example.test",
  "aud": ["inventory-api"],
  "scope": "inventory:read"
}
```

Inventory API có thể chấp nhận token này nếu các kiểm tra khác đạt. Orders API phải từ chối vì audience không chứa orders-api.

### 3.1. Audience khác issuer

| Claim | Câu hỏi |
| --- | --- |
| iss | Ai phát hành token? |
| aud | Token dành cho resource/recipient nào? |
| sub | Token đại diện cho subject nào? |
| scope hoặc scp | Token cho phép những hành động nào theo authorization contract? |

Một token có iss đúng nhưng aud sai vẫn phải bị từ chối.

### 3.2. Không dùng azp thay cho aud

Trong OIDC ID token, azp (authorized party) xác định party mà token được phát hành cho trong một số trường hợp, đặc biệt khi ID token có nhiều audiences. Nó không phải audience của Resource Server.

Không dùng azp để thay thế audience của API. azp có thể được kiểm tra trong OIDC client khi xác minh ID token, nhưng không biến ID token thành access token.

### 3.3. Audience có thể là string hoặc array

JWT có thể biểu diễn aud bằng một string hoặc một danh sách string. Spring Security chuẩn hóa claim này qua:

```java
List<String> audiences = jwt.getAudience();
```

So sánh theo phần tử chính xác:

```java
boolean intendedForOrders =
        jwt.getAudience().contains("orders-api");
```

Không dùng substring:

```java
// SAI: orders-api-admin cũng chứa chuỗi orders-api.
boolean wrong =
        jwt.getAudience().toString().contains("orders-api");
```

### 3.4. Membership hay chỉ chấp nhận một audience?

Có hai policy thường dùng:

**Membership:** token được chấp nhận nếu danh sách aud chứa identifier của API:

```java
boolean allowed =
        jwt.getAudience().contains("orders-api");
```

**Exact-single audience:** token phải có đúng một audience và audience đó là API:

```java
boolean allowed =
        jwt.getAudience().size() == 1
        && jwt.getAudience().contains("orders-api");
```

Membership phù hợp khi AS contract cho phép một access token có nhiều recipients. Exact-single chặt hơn và hữu ích khi tổ chức yêu cầu token riêng cho từng API. Hãy chọn policy có chủ đích, thống nhất với AS và áp dụng giống nhau trong mọi instance.

## 4. Hợp đồng token của Resource Server

Trước khi viết validator, cần xác định API chấp nhận loại access token nào. Một hợp đồng thực tế thường mô tả:

| Thành phần | Ví dụ hợp đồng cho Orders API |
| --- | --- |
| Trusted issuer | https://login.example.test |
| Audience/resource | orders-api |
| Token format | JWT ký bằng RS256, hoặc opaque token qua introspection |
| Token purpose/profile | Access token; nếu dùng RFC 9068 thì yêu cầu profile JWT access token tương ứng |
| Required scope | orders:read cho GET, orders:write cho POST |
| Lifetime | Có exp, thời hạn tối đa theo policy |
| Time claims | Kiểm tra exp, nbf và clock skew |
| Subject | sub theo định danh người dùng/service đã thống nhất |
| Optional constraints | client_id, cnf, tenant, actor/delegation claims |

Resource Server không nên chấp nhận token chỉ vì nó được ký bởi một issuer quen thuộc. Issuer có thể phát hành nhiều loại token cho nhiều client và resource khác nhau.

### 4.1. Không đoán token type từ một claim tùy ý

Một số Authorization Server thêm claim riêng như token_use, typ, client_id hoặc resource. Các claim đó chỉ có giá trị nếu AS và Resource Server đã thống nhất contract.

Không có một claim vendor-specific chung cho mọi OAuth server. Nếu AS phát hành token_use=access, có thể kiểm tra claim đó như một phần profile riêng. Không tự giả định mọi issuer đều phát hành claim này.

### 4.2. RFC 9068 và typ=at+jwt

RFC 9068 định nghĩa profile JWT access token. Với profile này, JOSE header sử dụng media type at+jwt hoặc application/at+jwt để nhận diện JWT access token:

```json
{
  "typ": "at+jwt",
  "alg": "RS256",
  "kid": "access-key-1"
}
```

Nếu AS cam kết RFC 9068, Resource Server có thể yêu cầu typ theo profile này. Nhưng không được áp dụng yêu cầu đó một cách mù quáng cho issuer dùng profile JWT access token khác hoặc legacy tokens không triển khai RFC 9068.

Ngay cả khi có typ=at+jwt, vẫn phải kiểm tra issuer, audience, thời hạn, chữ ký và scope. Header type không tự cấp quyền.

## 5. Những điều không đủ để chấp nhận token

| Kiểm tra đơn lẻ | Vì sao chưa đủ |
| --- | --- |
| JWT parse thành công | Token có thể malformed về mặt profile, sai chữ ký hoặc sai recipient. |
| Chữ ký hợp lệ | Token có thể là ID token hoặc access token dành API khác. |
| iss đúng | Cùng issuer có thể phát hành token cho nhiều client/API. |
| sub tồn tại | Subject không chứng minh token là access token hoặc dành cho API này. |
| scope có orders:read | Token có thể được cấp cho resource khác; scope không thay audience. |
| azp đúng | Authorized party trong OIDC context không thay thế API audience. |
| exp còn hiệu lực | Token chưa hết hạn vẫn có thể sai loại hoặc sai audience. |
| active=true từ introspection | Token active vẫn có thể dành cho resource khác hoặc không có quyền cần thiết. |

Resource Server cần xác minh toàn bộ hợp đồng trước khi tạo authenticated principal.

## 6. Cấu hình JWT Resource Server với issuer và audience validator

Spring Security có thể xác minh chữ ký qua JWKS và chạy các OAuth2TokenValidator trước khi tạo JwtAuthenticationToken.

Ví dụ cấu hình Servlet:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class OrdersResourceServerConfiguration {

    private static final String ISSUER =
            "https://login.example.test";
    private static final String JWKS_URI =
            "https://login.example.test/oauth2/jwks";
    private static final String API_AUDIENCE =
            "orders-api";

    @Bean
    NimbusJwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder =
                NimbusJwtDecoder.withJwkSetUri(JWKS_URI).build();

        OAuth2TokenValidator<Jwt> issuerAndTime =
                JwtValidators.createDefaultWithIssuer(ISSUER);

        OAuth2TokenValidator<Jwt> audience = jwt -> {
            if (jwt.getAudience().contains(API_AUDIENCE)) {
                return OAuth2TokenValidatorResult.success();
            }

            OAuth2Error error = new OAuth2Error(
                    "invalid_token",
                    "Token is not intended for Orders API",
                    null);

            return OAuth2TokenValidatorResult.failure(error);
        };

        decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(
                        issuerAndTime,
                        audience));

        return decoder;
    }

    @Bean
    SecurityFilterChain api(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers("/public/**").permitAll()
                        .requestMatchers(HttpMethod.GET, "/api/orders/**")
                            .hasAuthority("SCOPE_orders:read")
                        .requestMatchers(HttpMethod.POST, "/api/orders/**")
                            .hasAuthority("SCOPE_orders:write")
                        .anyRequest().authenticated())
                .oauth2ResourceServer(oauth2 -> oauth2
                        .jwt(Customizer.withDefaults()))
                .build();
    }
}
```

Ví dụ trên dùng trực tiếp JWKS URI và tự gắn issuer/time validator cùng audience validator. Nếu dùng issuer-uri discovery, có thể tạo decoder theo issuer rồi gắn validator audience tương tự. Dù chọn cách nào, phải giữ issuer validation.

Ví dụ dùng Servlet HttpSecurity. Ứng dụng WebFlux cần cấu hình ServerHttpSecurity và SecurityWebFilterChain; không dùng HttpSecurity trong reactive stack.

### 6.1. Vì sao cần JwtValidators.createDefaultWithIssuer?

Validator mặc định theo issuer giữ các kiểm tra thời gian mặc định và xác nhận iss khớp issuer tin cậy. Audience validator bổ sung kiểm tra token dành Orders API.

Không thay thế validator mặc định bằng một validator chỉ kiểm tra aud, vì khi đó có thể bỏ sót issuer/time checks.

### 6.2. Tách audience validator thành hàm riêng

```java
static OAuth2TokenValidator<Jwt> audienceValidator(
        String expectedAudience) {

    return jwt -> jwt.getAudience().contains(expectedAudience)
            ? OAuth2TokenValidatorResult.success()
            : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                            "invalid_token",
                            "Unexpected token audience",
                            null));
}
```

Tách validator giúp reuse cùng một contract trong nhiều cấu hình và test trực tiếp. Mỗi Resource Server phải truyền audience riêng của nó; không dùng một constant chung cho toàn bộ APIs nếu các resource có ranh giới khác nhau.

## 7. Kiểm tra token profile theo RFC 9068 khi AS hỗ trợ

Nếu Authorization Server phát hành JWT access token theo RFC 9068, có thể yêu cầu typ=at+jwt hoặc application/at+jwt:

```java
static OAuth2TokenValidator<Jwt> accessTokenTypeValidator() {
    return jwt -> {
        Object typ = jwt.getHeaders().get("typ");

        boolean validType =
                "at+jwt".equalsIgnoreCase(String.valueOf(typ))
                || "application/at+jwt".equalsIgnoreCase(
                        String.valueOf(typ));

        if (validType) {
            return OAuth2TokenValidatorResult.success();
        }

        return OAuth2TokenValidatorResult.failure(
                new OAuth2Error(
                        "invalid_token",
                        "Expected an RFC 9068 access token",
                        null));
    };
}
```

Ghép validator này với issuer/time và audience:

```java
decoder.setJwtValidator(
        new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(ISSUER),
                audienceValidator("orders-api"),
                accessTokenTypeValidator()));
```

**Chỉ bật typ validator khi issuer cam kết RFC 9068.** Nếu access token hiện tại của hệ thống không dùng profile này, yêu cầu at+jwt sẽ từ chối cả access token hợp lệ theo contract khác. Dù không kiểm tra typ, API vẫn phải kiểm tra audience và các claims/profile đã thống nhất.

## 8. ID token bị từ chối như thế nào?

Giả sử OIDC client có ID token:

```json
{
  "iss": "https://login.example.test",
  "sub": "user-123",
  "aud": ["web-client"],
  "exp": 1893456000,
  "iat": 1893452400,
  "nonce": "browser-login-nonce",
  "auth_time": 1893452300
}
```

Orders API yêu cầu audience orders-api. Kết quả:

```text
Signature verification: pass
Issuer validation:      pass
Timestamp validation:   pass
Audience validation:    fail (web-client != orders-api)
Authentication:         reject
HTTP result:            401 Unauthorized
```

Đây là điểm quan trọng: test phải dùng ID token có **chữ ký hợp lệ** để chứng minh API từ chối nó vì token không dành cho API. Nếu chỉ dùng một chuỗi JWT malformed, test có thể thất bại ở bước parse và không chứng minh audience policy.

### 8.1. Không dựa vào nonce để phân biệt token

nonce trong ID token ràng buộc authentication response với yêu cầu đăng nhập OIDC. Nó không phải cơ chế audience validation cho Resource Server.

Không kết luận:

- Có nonce thì chắc chắn là ID token.
- Không có nonce thì chắc chắn là access token.

Hãy dùng token profile và audience contract. Một access token có thể có custom claim tên nonce; một ID token có thể không chứa nonce trong một số flow.

### 8.2. Không dựa vào at_hash để biến ID token thành access token

at_hash trong ID token ràng buộc ID token với access token trong một số OIDC flows. Nó không thay thế audience của Resource Server và không cho phép gửi ID token làm Bearer credential tới API.

## 9. Token dành cho API khác bị từ chối

Giả sử Orders API và Inventory API dùng cùng issuer. Token được cấp cho Inventory:

```json
{
  "iss": "https://login.example.test",
  "sub": "user-123",
  "aud": ["inventory-api"],
  "scope": "inventory:read",
  "exp": 1893456000
}
```

Orders API nhận token này:

```text
Signature verification: pass
Issuer validation:      pass
Timestamp validation:   pass
Audience validation:    fail (inventory-api != orders-api)
Authentication:         reject
HTTP result:            401 Unauthorized
```

Không được chấp nhận token này chỉ vì nó có scope tên gần giống hoặc vì cùng issuer. Resource Server phải kiểm tra đúng audience của nó.

### 9.1. Scope không thay audience

Ví dụ token:

```json
{
  "aud": ["inventory-api"],
  "scope": "orders:read"
}
```

Ngay cả khi scope chứa orders:read, token vẫn dành Inventory API theo audience. Orders API phải từ chối. Scope là quyền chức năng; audience là recipient.

### 9.2. Không tự đổi audience tại Resource Server

Resource Server không được lấy token dành Inventory rồi tự coi nó là token Orders vì subject hoặc scope phù hợp. Muốn gọi API khác, client cần lấy token mới theo flow được AS hỗ trợ, chẳng hạn token exchange với target hợp lệ.

## 10. Audience validation với opaque access token

Không phải access token nào cũng là JWT. Với opaque token, Resource Server gọi introspection endpoint và nhận metadata về trạng thái token.

Ví dụ response:

```json
{
  "active": true,
  "iss": "https://login.example.test",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders:read",
  "exp": 1893456000
}
```

active=true chỉ nói token còn active theo Authorization Server. Resource Server vẫn phải kiểm tra audience, scope và metadata theo contract.

### 10.1. Bọc OpaqueTokenIntrospector để kiểm tra audience

Ví dụ decorator:

```java
import java.util.Collection;

import org.springframework.security.oauth2.core.OAuth2IntrospectionException;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.NimbusOpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

OpaqueTokenIntrospector ordersIntrospector(
        String introspectionUri,
        String clientId,
        String clientSecret) {

    OpaqueTokenIntrospector delegate =
            new NimbusOpaqueTokenIntrospector(
                    introspectionUri, clientId, clientSecret);

    return token -> {
        OAuth2AuthenticatedPrincipal principal =
                delegate.introspect(token);

        Object aud = principal.getAttribute("aud");
        boolean intendedForOrders =
                aud instanceof String value
                        ? "orders-api".equals(value)
                        : aud instanceof Collection<?> values
                                && values.contains("orders-api");

        if (!intendedForOrders) {
            throw new OAuth2IntrospectionException(
                    "Token is not intended for Orders API");
        }

        return principal;
    };
}
```

Đây là ví dụ minh họa cho introspection response có aud dạng string hoặc collection. Cấu hình bean thực tế phải lấy URI/client credentials từ configuration hoặc secret manager, không truyền chúng từ request caller.

Nếu AS dùng attribute khác để biểu diễn audience/resource binding, hãy triển khai đúng introspection contract của AS. Không tự suy luận audience từ scope.

### 10.2. Introspection không được bỏ qua token purpose

Resource Server phải biết introspection endpoint đang xác minh access token. Nếu AS có thể trả active=true cho nhiều loại security token, contract cần một thuộc tính token purpose/type đáng tin cậy hoặc endpoint/policy chỉ introspect access token.

Không dùng active=true đơn lẻ để chấp nhận ID token.

## 11. HTTP status: 401 hay 403?

Phân biệt lỗi authentication và authorization:

| Tình huống | Kết quả thường dùng | Ý nghĩa |
| --- | --- | --- |
| Gửi ID token thay access token | **401 Unauthorized** | Credential không hợp lệ cho Resource Server. |
| Gửi access token dành API khác | **401 Unauthorized** | Token không được phát hành cho API hiện tại. |
| Sai chữ ký/issuer/hết hạn | **401 Unauthorized** | Authentication không thành công. |
| Token đúng issuer/audience nhưng thiếu scope | **403 Forbidden** | Token hợp lệ nhưng không đủ quyền cho operation. |
| Token đúng nhưng user không có quyền trên object/tenant | **403** hoặc **404** theo API contract | Domain authorization từ chối. |
| Không gửi Bearer token tới endpoint protected | **401 Unauthorized** | Không có credential để authenticate. |

Không trả 403 cho token sai audience chỉ để che giấu lỗi cấu hình. Resource Server chưa xác thực được credential dành cho mình, nên 401 là semantics phù hợp.

### 11.1. Không để business controller xử lý token sai

Khi signature, issuer, audience hoặc token profile validation thất bại, request phải dừng ở authentication layer. Controller không được chạy với principal chưa xác minh.

Trong test, có thể dùng mock service và verify không có lời gọi nghiệp vụ khi token sai audience:

```java
verify(orderService, never()).findOrders(any());
```

Điều này chứng minh request bị chặn trước khi business action xảy ra.

## 12. Kiểm thử tích hợp: phải gửi signed Bearer token thật

Để kiểm tra hợp đồng token, dùng:

- RSA/EC key pair chỉ dành cho test.
- Mock JWKS endpoint chỉ công bố public key test.
- Compact JWS được ký bằng private key test.
- MockMvc chạy với đầy đủ Spring Security filter chain.
- HTTP header Authorization: Bearer <token>.

Không dùng with(jwt()) cho test này vì helper dựng sẵn JwtAuthenticationToken, bỏ qua JwtDecoder, chữ ký và audience validation.

### 12.1. Test factory tạo token có chữ ký

Ví dụ với Nimbus JOSE:

```java
import com.nimbusds.jose.JOSEException;
import com.nimbusds.jose.JOSEObjectType;
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.JWSHeader;
import com.nimbusds.jose.crypto.RSASSASigner;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jose.jwk.gen.RSAKeyGenerator;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.SignedJWT;

import java.time.Instant;
import java.util.Date;
import java.util.List;

final class TestAccessTokenFactory {

    static RSAKey newKey(String kid) throws JOSEException {
        return new RSAKeyGenerator(2048)
                .keyID(kid)
                .generate();
    }

    static String sign(
            RSAKey key,
            String issuer,
            List<String> audiences,
            String scope,
            String typ) throws JOSEException {

        Instant now = Instant.now();

        JWTClaimsSet claims = new JWTClaimsSet.Builder()
                .issuer(issuer)
                .subject("user-123")
                .audience(audiences)
                .issueTime(Date.from(now))
                .expirationTime(Date.from(now.plusSeconds(300)))
                .claim("scope", scope)
                .build();

        JWSHeader header = new JWSHeader.Builder(JWSAlgorithm.RS256)
                .keyID(key.getKeyID())
                .type(new JOSEObjectType(typ))
                .build();

        SignedJWT jwt = new SignedJWT(header, claims);
        jwt.sign(new RSASSASigner(key.toPrivateKey()));
        return jwt.serialize();
    }
}
```

Với RFC 9068 access token, truyền typ là at+jwt hoặc application/at+jwt. Để tạo ID token fixture, dùng header type phù hợp OIDC provider đang mô phỏng và audience là client ID. Nếu test chỉ nhằm chứng minh audience, hãy không bật validator type riêng trong fixture đó hoặc assert riêng từng nguyên nhân.

### 12.2. Cấp JWKS test từ public key

```java
String jwksJson =
        new JWKSet(testSigningKey.toPublicJWK()).toString();
```

JWKS không được chứa private key. Private key chỉ nằm trong test process để ký JWT.

### 12.3. Gửi token qua MockMvc

```java
mockMvc.perform(get("/api/orders")
        .header(
                HttpHeaders.AUTHORIZATION,
                "Bearer " + compactJwt))
        .andExpect(status().isOk());
```

Test application context phải dùng decoder thật trỏ tới mock JWKS endpoint, không thay JwtDecoder bằng mock. Khi đó request đi qua Bearer filter, authentication provider, decoder, signature verification và validators.

## 13. Các test bắt buộc cho ID token và token API khác

Giả sử test issuer là https://issuer.test, key ký test đã được công bố trong JWKS và API đang kiểm tra orders-api.

### 13.1. Positive: access token đúng audience

```java
String ordersToken = TestAccessTokenFactory.sign(
        trustedKey,
        TEST_ISSUER,
        List.of("orders-api"),
        "orders:read",
        "at+jwt");

mockMvc.perform(get("/api/orders")
        .header(HttpHeaders.AUTHORIZATION, "Bearer " + ordersToken))
        .andExpect(status().isOk());
```

Token có chữ ký tin cậy, issuer đúng, audience Orders và scope phù hợp nên có thể được chấp nhận.

### 13.2. Negative: ID token của web client

ID token fixture phải được ký bằng cùng test issuer key để tránh test chỉ thất bại vì signature:

```java
String idToken = TestAccessTokenFactory.sign(
        trustedKey,
        TEST_ISSUER,
        List.of("web-client"),
        "openid profile",
        "JWT");

mockMvc.perform(get("/api/orders")
        .header(HttpHeaders.AUTHORIZATION, "Bearer " + idToken))
        .andExpect(status().isUnauthorized());
```

Test này chứng minh ID token có issuer/chữ ký hợp lệ nhưng audience là OIDC client, không phải Orders API, nên bị từ chối. Trong fixture thực tế có thể thêm nonce, auth_time và các claims OIDC phù hợp; các claim đó không thay đổi audience decision.

### 13.3. Negative: access token dành Inventory API

```java
String inventoryToken = TestAccessTokenFactory.sign(
        trustedKey,
        TEST_ISSUER,
        List.of("inventory-api"),
        "inventory:read",
        "at+jwt");

mockMvc.perform(get("/api/orders")
        .header(
                HttpHeaders.AUTHORIZATION,
                "Bearer " + inventoryToken))
        .andExpect(status().isUnauthorized());
```

Token là access token hợp lệ theo profile, nhưng recipient sai. Đây là test quan trọng để chứng minh Resource Server không chấp nhận token chỉ vì cùng issuer và cùng chữ ký.

### 13.4. Negative: đúng audience nhưng thiếu scope

```java
String noReadScope = TestAccessTokenFactory.sign(
        trustedKey,
        TEST_ISSUER,
        List.of("orders-api"),
        "orders:write",
        "at+jwt");

mockMvc.perform(get("/api/orders")
        .header(
                HttpHeaders.AUTHORIZATION,
                "Bearer " + noReadScope))
        .andExpect(status().isForbidden());
```

Ở đây authentication đã thành công: token dành Orders API. Request GET yêu cầu orders:read, nhưng token chỉ có orders:write, nên authorization trả 403.

### 13.5. Negative: issuer khác

Ký token bằng test key được tin cậy nhưng đặt iss khác. Chữ ký có thể hợp lệ, nhưng issuer validator phải từ chối:

```java
String wrongIssuer = TestAccessTokenFactory.sign(
        trustedKey,
        "https://other-issuer.test",
        List.of("orders-api"),
        "orders:read",
        "at+jwt");

mockMvc.perform(get("/api/orders")
        .header(HttpHeaders.AUTHORIZATION, "Bearer " + wrongIssuer))
        .andExpect(status().isUnauthorized());
```

Test này tách issuer validation khỏi signature verification.

## 14. Test type validator riêng nếu dùng RFC 9068

Nếu API contract bắt buộc RFC 9068:

| Token | typ | aud | Kết quả |
| --- | --- | --- | --- |
| Access token theo RFC 9068 | at+jwt hoặc application/at+jwt | orders-api | Có thể chấp nhận. |
| ID token | JWT hoặc type theo OIDC provider | web-client | Từ chối. |
| JWT không phải access-token profile | JWT | orders-api | Từ chối theo type policy. |
| Access token RFC 9068 của Inventory | at+jwt | inventory-api | Từ chối do audience. |

Không nên dựa duy nhất vào typ. Một ID token có audience sai vẫn phải bị từ chối ngay cả khi một issuer không tuân theo header type convention. Ngược lại, một JWT có typ=at+jwt nhưng audience sai cũng phải bị từ chối.

## 15. Ma trận kiểm thử tích hợp

| Case | Token | Signature | Issuer | Audience | Scope | Kết quả |
| --- | --- | --- | --- | --- | --- | --- |
| INT-01 | Access token Orders | Hợp lệ | Đúng | orders-api | orders:read | 2xx |
| INT-02 | ID token Web Client | Hợp lệ | Đúng | web-client | Không phải API scope | 401 |
| INT-03 | Access token Inventory | Hợp lệ | Đúng | inventory-api | inventory:read | 401 |
| INT-04 | Access token Orders | Hợp lệ | Sai | orders-api | orders:read | 401 |
| INT-05 | Access token Orders | Sai | Đúng | orders-api | orders:read | 401 |
| INT-06 | Access token Orders | Hợp lệ | Đúng | orders-api | Thiếu orders:read | 403 |
| INT-07 | Access token Orders | Hợp lệ | Đúng | Audience khác | orders:read | 401 |
| INT-08 | Access token Orders | Hợp lệ | Đúng | orders-api | Đúng nhưng hết hạn | 401 |
| INT-09 | Access token đa audience | Hợp lệ | Đúng | Có orders-api và API khác | Đủ | Theo policy membership/exact-single |
| INT-10 | Token thiếu aud | Hợp lệ | Đúng | Không có | Có scope | 401 |
| INT-11 | RFC 9068 access token | Hợp lệ | Đúng | orders-api | Đủ | 2xx nếu profile được bật |
| INT-12 | JWT type khác | Hợp lệ | Đúng | orders-api | Đủ | 401 nếu RFC 9068 type validator được bật |
| INT-13 | Opaque token active, đúng audience | Introspection thành công | Đúng | orders-api | Đủ | 2xx |
| INT-14 | Opaque token active, audience khác | Introspection thành công | Đúng | inventory-api | Đủ | 401 |
| INT-15 | Opaque token inactive | Không active | — | — | — | 401 |

### 15.1. Kiểm tra controller không chạy

Với token sai audience hoặc ID token, ngoài status 401 nên xác nhận service nghiệp vụ không được gọi:

```java
verify(orderService, never()).findOrders(any());
```

Điều này bảo đảm token sai bị chặn ở authentication layer trước khi controller/service xử lý dữ liệu.

### 15.2. Kiểm tra đúng status code

Đừng chỉ assert is4xxClientError(). Hãy kiểm tra:

- Token không được xác thực: 401.
- Token được xác thực nhưng thiếu scope: 403.

Hai kết quả này thể hiện hai lỗi khác nhau và ảnh hưởng cách client xử lý.

## 16. Kiểm thử opaque token qua introspection

Nếu API dùng opaque access token, test không nên cố decode token như JWT. Hãy mock introspection endpoint và cho nó trả các metadata khác nhau.

### 16.1. Token active và đúng audience

```json
{
  "active": true,
  "iss": "https://login.example.test",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders:read",
  "exp": 1893456000
}
```

Kỳ vọng: introspector trả principal, authority converter ánh xạ scope, API cho phép GET.

### 16.2. Token active nhưng audience của API khác

```json
{
  "active": true,
  "iss": "https://login.example.test",
  "sub": "user-123",
  "aud": ["inventory-api"],
  "scope": "inventory:read",
  "exp": 1893456000
}
```

Kỳ vọng: introspection delegate báo active, nhưng audience decorator từ chối. Không tạo Authentication cho Orders API.

### 16.3. Token inactive

```json
{
  "active": false
}
```

Kỳ vọng: introspector từ chối trước khi audience check. Không được coi một token inactive là hợp lệ chỉ vì response có claim khác.

### 16.4. Test token type theo AS contract

Nếu introspection response có claim riêng hoặc metadata token type, hãy kiểm tra nó theo contract. Không tự giả định mọi AS trả token_type hoặc token_use với cùng semantics. Nếu AS có thể introspect cả ID token, Resource Server cần một quy tắc rõ ràng để chỉ chấp nhận access token.

## 17. Token exchange khi cần gọi API khác

Nếu Orders API cần gọi Inventory API, không gửi token Orders tới Inventory và không nới audience validator để cả hai API cùng chấp nhận mọi token.

Có thể dùng OAuth 2.0 Token Exchange (RFC 8693) nếu AS hỗ trợ:

```text
subject_token = access token dành orders-api
audience = inventory-api
scope = inventory:read
```

AS xác minh client, subject, actor và target rồi cấp token mới có audience phù hợp. Inventory API vẫn kiểm tra audience của chính nó.

Nếu token exchange không được hỗ trợ, client phải dùng flow/credential khác đã được thiết kế cho Inventory API, chẳng hạn client credentials cho workload nếu nghiệp vụ không cần user delegation.

**Không giải quyết lỗi sai audience bằng cách bỏ audience validation.**

## 18. Các lỗi triển khai thường gặp

1. **Chỉ xác minh chữ ký:** token có thể được issuer ký hợp lệ nhưng là ID token hoặc access token dành API khác.
2. **Dùng ID token gọi API:** ID token dành OIDC client; dùng access token dành Resource Server.
3. **Chấp nhận token chỉ vì cùng issuer:** cùng issuer có thể phát hành nhiều loại token cho nhiều audiences.
4. **Dùng scope thay audience:** scope mô tả quyền; audience mô tả recipient.
5. **Dùng azp thay aud:** azp không phải audience của Resource Server.
6. **So sánh audience bằng substring:** có thể chấp nhận nhầm orders-api-admin; dùng exact membership hoặc exact-single policy.
7. **Cho phép nhiều audience không chủ đích:** token đa audience có thể được dùng tại nhiều resource.
8. **Bỏ issuer validator khi thêm audience validator:** hai validator bổ sung nhau.
9. **Dựa vào typ cho mọi issuer:** at+jwt hữu ích khi AS phát hành theo RFC 9068; legacy profile có thể không dùng nó.
10. **Dùng with(jwt()) để chứng minh token sai bị từ chối:** helper dựng authentication sẵn và bỏ qua decoder.
11. **Mock JwtDecoder trong integration test:** mock decoder không xác minh chữ ký, issuer hoặc audience.
12. **Chỉ test token malformed:** cần token có chữ ký hợp lệ nhưng sai audience để chứng minh audience policy.
13. **Chấp nhận opaque token chỉ vì active=true:** active không có nghĩa dành API này.
14. **Để token sai vào controller:** authentication phải thất bại trước business handler.

## 19. Quan sát và vận hành

Khi token bị từ chối, log nên ghi nguyên nhân ở mức an toàn:

```text
event=oauth2_authentication_failed
reason=invalid_audience
resource=orders-api
issuer=https://login.example.test
request_id=...
```

Không log raw access token, ID token, Authorization header hoặc toàn bộ JWT claims có PII.

Metrics có thể phân loại invalid_signature, invalid_issuer, invalid_audience, expired_token, invalid_token_profile, insufficient_scope và introspection_inactive. Không dùng token value hoặc sub làm metric label vì có thể tạo high cardinality và làm lộ dữ liệu. Dùng API/resource identifier và error category ổn định.

### 19.1. Không trả chi tiết nội bộ cho caller

HTTP response thường nên dùng Bearer challenge tổng quát:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
```

Không trả raw token, issuer signing key ID nội bộ, stack trace hoặc toàn bộ claims trong error_description. Chi tiết hơn có thể nằm trong telemetry đã redaction.

## 20. Checklist triển khai

- [ ] Xác định trusted issuer chính xác.
- [ ] Xác định audience/resource identifier của API.
- [ ] Xác định token profile mà AS phát hành.
- [ ] Phân biệt ID token và access token trong client/API contract.
- [ ] Xác minh JWS signature bằng trusted JWKS hoặc introspection cho opaque token.
- [ ] Kiểm tra issuer và thời hạn.
- [ ] Kiểm tra audience bằng exact membership hoặc exact-single policy.
- [ ] Không dùng azp, sub, scope hoặc active=true thay audience.
- [ ] Kiểm tra scope/authority sau authentication.
- [ ] Chỉ bắt buộc typ=at+jwt khi AS dùng RFC 9068.
- [ ] Test ID token có chữ ký hợp lệ nhưng audience là client ID → 401.
- [ ] Test access token có chữ ký hợp lệ nhưng audience là API khác → 401.
- [ ] Test token đúng audience nhưng thiếu scope → 403.
- [ ] Test sai issuer/chữ ký/hết hạn → 401.
- [ ] Test opaque token active nhưng sai audience → 401.
- [ ] Assert controller/business service không chạy khi authentication thất bại.
- [ ] Không log token hoặc claims nhạy cảm.

## 21. Câu hỏi tự kiểm tra

**1. ID token dùng để làm gì?** Xác nhận kết quả authentication cho OIDC client/Relying Party.

**2. Access token dùng để làm gì?** Cấp quyền truy cập protected resource theo scope/policy.

**3. Vì sao không gửi ID token tới Resource Server?** Audience và purpose của ID token dành cho OIDC client, không phải API.

**4. Chữ ký JWT hợp lệ có đủ để chấp nhận token không?** Không. Còn phải kiểm tra issuer, audience, thời hạn, profile và authorization.

**5. Claim nào xác định token dành API nào?** aud, theo audience contract của Resource Server.

**6. iss và aud khác nhau thế nào?** iss xác định issuer; aud xác định recipient.

**7. azp có thay được aud không?** Không. azp là authorized party trong OIDC context.

**8. Scope có thay audience không?** Không. Scope mô tả quyền; audience mô tả resource.

**9. Khi sai audience nên trả status nào?** Thường 401 vì credential không hợp lệ cho Resource Server.

**10. Khi token đúng audience nhưng thiếu scope?** 403.

**11. Có thể chấp nhận nhiều audience không?** Có nếu contract cho phép; phải chọn membership hoặc exact-single policy rõ ràng.

**12. typ=at+jwt có luôn bắt buộc không?** Chỉ khi token profile của AS cam kết RFC 9068.

**13. nonce có chứng minh token là ID token không?** Không; nonce ràng buộc OIDC authentication response.

**14. Opaque token active=true có đủ không?** Không. Vẫn kiểm tra audience/resource và scope.

**15. jwt() trong MockMvc có kiểm tra audience từ token ký thật không?** Không. Nó tạo JwtAuthenticationToken giả lập.

**16. Test nào chứng minh API từ chối ID token?** Gửi ID token được ký bằng trusted test key, có issuer hợp lệ nhưng audience là client ID, qua full Bearer filter chain và assert 401.

**17. Test nào chứng minh API từ chối token của API khác?** Gửi access token ký hợp lệ, cùng issuer, nhưng aud là identifier của API khác.

**18. Vì sao phải test 403 riêng?** Để chứng minh authentication thành công và authorization từ chối do thiếu scope.

**19. Nếu Orders cần gọi Inventory thì làm gì?** Lấy token dành Inventory bằng token exchange hoặc flow service credential được thiết kế; không bỏ audience validation.

**20. Vì sao cần kiểm tra business service không được gọi?** Để bảo đảm token sai bị chặn trước khi có side effect.

## 22. Tài liệu tham khảo

- **OpenID Connect Core 1.0 — ID Token:** định nghĩa ID token, iss, sub, aud, azp, nonce và cách client xác minh ID token. https://openid.net/specs/openid-connect-core-1_0.html
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** access-token profile, typ=at+jwt, audience và claims. https://www.rfc-editor.org/rfc/rfc9068
- **RFC 8725 — JSON Web Token Best Current Practices:** algorithm verification, issuer/audience validation và chống nhầm lẫn giữa các loại JWT. https://www.rfc-editor.org/rfc/rfc8725
- **RFC 7519 — JSON Web Token (JWT):** semantics của iss, sub, aud, exp, nbf, iat. https://www.rfc-editor.org/rfc/rfc7519
- **RFC 7662 — OAuth 2.0 Token Introspection:** trạng thái và metadata của opaque token. https://www.rfc-editor.org/rfc/rfc7662
- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** Bearer authentication và lỗi invalid_token/insufficient_scope. https://www.rfc-editor.org/rfc/rfc6750
- **Spring Security Reference — Servlet OAuth 2.0 Resource Server JWT:** decoder, issuer, JWKS và JWT validation. https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html
- **Spring Security Reference — Servlet OAuth 2.0 Resource Server Opaque Token:** introspection và opaque token validation. https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html
- **Spring Security Reference — Testing OAuth 2.0:** MockMvc và jwt() request post-processor. https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html

## 23. Kết luận

Resource Server phải từ chối ID token và access token dành cho API khác theo đúng token contract. Một chữ ký hợp lệ chỉ chứng minh token được ký bằng key tin cậy; nó không chứng minh token là access token hoặc được phát hành cho API đang nhận request.

Với JWT, hãy xác minh chữ ký, issuer, thời hạn, audience và token profile; với opaque token, hãy kiểm tra introspection state cùng audience/resource và scope. ID token thường có audience là OIDC client, còn access token phải mang audience của Resource Server. Khi audience sai, authentication thất bại và API thường trả 401; khi token đúng audience nhưng thiếu scope, authorization trả 403.

Kiểm thử quan trọng nhất là dùng **token có chữ ký hợp lệ nhưng sai recipient**: một ID token có aud=web-client và một access token có aud=inventory-api đều phải bị Orders API từ chối qua full Bearer filter chain. Sau đó dùng token aud=orders-api nhưng thiếu scope để chứng minh 403. Những test này xác nhận API tuân thủ hợp đồng token ở cả ranh giới xác thực lẫn phân quyền.
