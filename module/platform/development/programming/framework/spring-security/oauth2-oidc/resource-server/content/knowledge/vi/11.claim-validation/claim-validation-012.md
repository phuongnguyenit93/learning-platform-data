# Không dùng kiểm tra claims thay cho xác minh chữ ký hoặc nguồn token

Trong **Spring Security OAuth 2.0/OIDC Resource Server**, một access token có thể mang các claim rất thuyết phục: **iss** trỏ tới Authorization Server đúng, **aud** khớp API, **exp** chưa hết hạn, **scope** chứa quyền cần thiết và **sub** là mã người dùng có thật. Tuy nhiên, **kiểm những claim đó không đủ để kết luận token hợp lệ**.

Lý do: claim chỉ là dữ liệu do token mang theo. Người gửi request có thể tự tạo một JWT mới và ghi mọi giá trị vào payload. Nếu API chỉ Base64URL-decode và so sánh các claim mà không xác minh **chữ ký và nguồn phát hành token đáng tin cậy**, kẻ tấn công có thể giả mạo một token vốn chưa từng được Authorization Server cấp.

Một quy trình xác thực JWT đúng cần tách bốn câu hỏi:

1. **Đọc được cấu trúc không?** Parse JOSE header và JWT claims.
2. **Ai có quyền phát hành token này?** Kiểm chữ ký/MAC bằng khóa được liên kết với issuer tin cậy.
3. **Token có phù hợp với API này ngay bây giờ không?** Kiểm **iss**, **aud**, **exp**, **nbf**, loại token và các quy tắc nhận token.
4. **Chủ thể có quyền thực hiện hành động này trên dữ liệu này không?** Kiểm scope, role, permission, tenant, ownership và domain policy.

Trong Spring Security, **JwtDecoder** được cấu hình đúng đảm nhiệm xác thực JWT trước khi claims được chuyển thành **Authentication**. Với **opaque token**, nguồn tin cậy được xác lập bằng **introspection** tới Authorization Server đáng tin cậy thay vì tự kiểm chữ ký JWT.

## 1. Claims là lời khai, không phải bằng chứng

Giả sử Orders API chỉ cho phép token thỏa mãn các điều kiện:

~~~text
Trusted issuer:    https://login.example.com/realms/shop
Audience:          orders-api
Required scope:    orders.read
~~~

Một payload có thể trông như sau:

~~~json
{
  "iss": "https://login.example.com/realms/shop",
  "sub": "user-123",
  "aud": ["orders-api"],
  "iat": 1893450000,
  "exp": 1893456000,
  "scope": "orders.read",
  "tenant_id": "tenant-a"
}
~~~

Nếu ứng dụng chỉ đọc JSON và kiểm:

~~~text
iss == trustedIssuer       -> true
aud contains orders-api    -> true
exp > currentTime          -> true, giả sử tại thời điểm kiểm tra
scope contains orders.read -> true
tenant_id == tenant-a      -> true
~~~

thì một JWT **do kẻ tấn công tự viết** vẫn có thể vượt qua những phép so sánh đó. Người gửi không cần private key của Authorization Server để tự đặt các giá trị trong JSON.

Các lớp bảo mật phải được hiểu riêng:

| Lớp | Kiểm gì? | Nếu bỏ lớp này |
|---|---|---|
| **Parse** | Định dạng JWS/JWT, Base64URL, JSON | Không thể đọc token một cách có cấu trúc |
| **Verify** | Chữ ký/MAC đúng với khóa thuộc nguồn tin cậy | Token tự ký/giả mạo có thể được chấp nhận |
| **Validate** | Issuer, audience, thời hạn, token type và điều kiện tiếp nhận | Token thật nhưng sai mục đích/hết hạn có thể được nhận |
| **Authorize** | Quyền đối với thao tác và tài nguyên cụ thể | Người dùng được truy cập vượt quyền |

**Kiểm iss không thay thế verify. Kiểm aud không thay thế verify. Kiểm exp không thay thế verify.** Ngược lại, chữ ký hợp lệ cũng **không thay thế** kiểm issuer, audience và thời hạn.

## 2. Vì sao đọc được JWT không có nghĩa xác thực được?

JWT ký bằng JWS Compact Serialization thường có ba phần:

~~~text
BASE64URL(protected-header).BASE64URL(payload).BASE64URL(signature)
~~~

Ví dụ JOSE header:

~~~json
{
  "alg": "RS256",
  "kid": "shop-sign-2026-11",
  "typ": "at+jwt"
}
~~~

Ví dụ payload:

~~~json
{
  "iss": "https://login.example.com/realms/shop",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 1893456000
}
~~~

**Base64URL là encoding, không phải encryption.** Người giữ một JWS JWT thông thường có thể giải mã header và payload để đọc dữ liệu mà không có khóa bí mật. JWS bảo vệ nội dung bằng **chữ ký**, không che giấu nội dung khỏi người cầm token.

Với thuật toán **RS256**, Authorization Server dùng **RSA private key** ký trên signing input:

~~~text
ASCII(BASE64URL(header) + "." + BASE64URL(payload))
~~~

Resource Server dùng **RSA public key thuộc issuer tin cậy** để verify chữ ký. Nếu ai đó sửa **scope = orders.read** thành **scope = orders.write** nhưng không tạo được chữ ký tương ứng, verification phải thất bại.

Nếu kẻ tấn công tự ký lại JWT bằng private key của họ, chữ ký có thể khớp với **public key của họ**. Điều đó cũng **chưa đủ**: Resource Server phải kiểm key đó có được issuer ủy quyền ký access token hay không.

### 2.1. Parse payload bằng Java chỉ là thao tác dữ liệu

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Base64;

public final class UntrustedJwtViewer {

    // CHỈ đọc cú pháp để minh họa, KHÔNG dùng để xác thực hay cấp quyền.
    public static String readPayloadWithoutVerification(String compactJws) {
        String[] parts = compactJws.split("\\.", -1);
        if (parts.length != 3) {
            throw new IllegalArgumentException("Expected three JWS parts");
        }
        byte[] bytes = Base64.getUrlDecoder().decode(parts[1]);
        return new String(bytes, StandardCharsets.UTF_8);
    }
}
~~~

Đoạn code này **không**:

- Xác minh signature/MAC.
- Kiểm nguồn khóa hoặc issuer được tin cậy.
- Kiểm thuật toán đã được phép.
- Kiểm **iss**, **aud**, **exp**, **nbf** hoặc token profile.
- Kiểm scope/role/tenant/ownership có được cấp hợp pháp hay không.

Một token giả chứa JSON hợp lệ vẫn có thể được hàm này trả về. Việc thêm JSON parser để chuyển payload thành Map/DTO không tạo thêm bất kỳ bằng chứng xác thực nào.

Một anti-pattern thường gặp:

~~~java
// SAI: pseudocode minh họa lỗi bảo mật.
String token = getBearerToken(request);
Map<String, Object> claims =
    parseJson(UntrustedJwtViewer.readPayloadWithoutVerification(token));

if (trustedIssuer.equals(claims.get("iss"))
        && claimHasScope(claims, "orders.write")) {
    allowOrderModification();
}
~~~

Những hàm **getBearerToken**, **parseJson**, **claimHasScope** và **allowOrderModification** chỉ là tên minh họa, không phải một API Spring Security hoàn chỉnh. Vấn đề là **mọi điều kiện đang sử dụng claim chưa được xác thực**.

Thêm **exp** hoặc **aud** vào biểu thức if không sửa lỗi. Cần thay phần xác thực bằng một **JwtDecoder có verification thực sự**.

## 3. Kịch bản tấn công: token giả nhưng claims đều khớp

Một người gửi request trái phép có thể:

1. Tự tạo một payload JWT với **iss** giống issuer thật.
2. Tự điền **aud = orders-api** và **scope = orders.write**.
3. Đặt **exp** ở tương lai và **sub** của người có quyền quản trị.
4. Gắn một signature vô nghĩa, dùng **alg = none** trong một triển khai yếu, hoặc tự ký bằng khóa riêng.
5. Gửi token qua header **Authorization: Bearer**.

~~~mermaid
sequenceDiagram
    participant X as Kẻ tấn công
    participant API as Resource Server cấu hình lỗi
    X->>X: Tạo JWT giả có iss, aud, scope, exp như ý
    X->>API: Authorization: Bearer JWT giả
    API->>API: Parse JSON, so sánh các claims
    Note over API: Không verify nguồn/chữ ký token
    API-->>X: Truy cập trái phép
~~~

**Các claim khớp với cấu hình không thể làm một JWT tự tạo trở thành JWT do issuer phát hành.**

Trong Resource Server đúng, token giả phải bị từ chối **trước khi claims được dùng để tạo principal/GrantedAuthority**.

### 3.1. Kiểm issuer từ payload có thể bị giả mạo

~~~java
// SAI nếu claims chưa qua xác thực.
if ("https://login.example.com/realms/shop".equals(claims.get("iss"))) {
    authenticateUser();
}
~~~

Bất kỳ ai cũng có thể đặt chuỗi issuer đó trong JSON. **iss là điều kiện cần để phân biệt issuer, không phải một chữ ký số.**

### 3.2. Kiểm audience không chứng minh token thật

Một payload có thể được chỉnh thành:

~~~json
{
  "aud": ["orders-api", "payments-api"]
}
~~~

Nếu server chỉ kiểm **aud contains orders-api**, token giả cũng đạt. Audience cần được kiểm **sau khi đã xác minh nguồn/chữ ký**. Ngược lại, token thật được ký đúng nhưng có audience dành cho API khác vẫn phải bị từ chối.

### 3.3. Kiểm thời gian cũng không ngăn giả mạo

Kẻ tấn công có thể tự đặt **exp** trong tương lai. Kiểm thời gian có ý nghĩa khi claims đã được bảo vệ bởi một cơ chế xác thực token đáng tin cậy. Token ký đúng nhưng hết hạn phải bị từ chối; token giả với exp còn hạn cũng phải bị từ chối.

### 3.4. Scope/role/tenant là dữ liệu quyền được mang trong token

JWT payload có thể chứa:

~~~json
{
  "scope": "orders.read orders.write",
  "roles": ["ADMIN"],
  "tenant_id": "tenant-a",
  "email_verified": true
}
~~~

Những trường này **không phải** nguồn độc lập chứng minh quyền. Chỉ sau khi token đã được xác thực, API mới nên áp dụng converter/policy để suy ra quyền phù hợp. Kể cả token hợp lệ, scope OIDC **openid**, **profile**, **email** không tự biến thành quyền nghiệp vụ.

## 4. “Nguồn token” có ba nghĩa cần tách biệt

| Cách hiểu | Ví dụ | Có chứng minh token thật không? |
|---|---|---|
| **Nguồn của HTTP request** | Browser, mobile app, service hoặc API Gateway gửi Bearer token | **Không**; địa chỉ gửi không chứng minh issuer ký token |
| **Issuer token tự khai** | JSON claim **iss** trong JWT chưa verify | **Không**; người gửi có thể tự điền |
| **Issuer/nguồn khóa được API tin cậy** | **issuer-uri** và JWKS/key source được cấu hình trên server | **Có thể dùng làm trust anchor** khi kết hợp verification và validation |

Việc request đến bằng **HTTPS** bảo vệ Bearer token trên đường truyền nhưng không chứng minh token do Authorization Server cấp. Tương tự, một proxy chuyển tiếp JWT không khiến JSON trong JWT tự trở nên đáng tin.

Nếu tổ chức ủy thác authentication cho một gateway, backend cần một **giao thức/ranh giới tin cậy** để xác nhận thông tin đã được gateway xử lý (ví dụ chặn đường truy cập trực tiếp, mTLS, header nội bộ do gateway ghi đè, cơ chế ký/chứng thực thông điệp). Không được tin một header danh tính chỉ vì client gửi đúng tên trường.

## 5. Nguồn khóa phải ràng buộc với issuer tin cậy

Resource Server thường biết issuer URI **trước khi xử lý request**:

~~~text
https://login.example.com/realms/shop
~~~

Spring Security có thể dùng issuer đó để khám phá metadata OIDC/OAuth2, tìm **jwks_uri** và tải public JWKS qua HTTPS. Khóa công khai dùng verify chữ ký đến từ nguồn đã được xác lập qua cấu hình và metadata của issuer, **không phải từ một yêu cầu tùy ý của người gửi JWT**.

~~~mermaid
flowchart TD
    C[Issuer tin cậy trong cấu hình] --> M[Metadata discovery qua HTTPS]
    M --> J[jwks_uri trong metadata đáng tin]
    J --> K[JWKS chứa public keys]
    T[Bearer JWT] --> P[Parse header/claims chưa tin cậy]
    P --> S[Chọn key theo kid trong JWKS tin cậy]
    K --> S
    S --> V{Signature hợp lệ với allowed alg?}
    V -->|Không| X[401]
    V -->|Có| Q{iss, aud, time và profile hợp lệ?}
    Q -->|Không| X
    Q -->|Có| A[Kiểm quyền endpoint và dữ liệu]
~~~

Public key có thể được công bố rộng rãi; **nguồn công bố và ràng buộc nó với issuer mới là vấn đề tin cậy**. Một public key của kẻ tấn công vẫn có thể verify chữ ký do chính kẻ đó tạo.

### 5.1. kid chỉ là gợi ý chọn khóa

JWT header có thể chứa:

~~~json
{
  "alg": "RS256",
  "kid": "sign-2026-11"
}
~~~

Kẻ tấn công có thể tự điền **kid**. Decoder dùng kid để tìm khóa **trong tập khóa đã được issuer tin cậy công bố**. Nếu chữ ký không khớp khóa tìm được, token bị từ chối.

Không cho **kid** tự quyết định đường dẫn file, SQL query hoặc hostname lấy key. Không chọn khóa theo **kid** toàn cục mà quên phân biệt issuer trong hệ thống multi-tenant.

### 5.2. jku, jwk, x5u hoặc x5c không tự đáng tin

JWS hỗ trợ các JOSE Header Parameters:

- **jku**: URL chứa một JSON Web Key Set.
- **jwk**: một JWK được đính kèm trong header.
- **x5u**: URL chứa chuỗi chứng chỉ X.509.
- **x5c**: chuỗi chứng chỉ X.509 nhúng trong header.
- **x5t/x5t#S256**: thumbprint hỗ trợ nhận diện certificate.

Trong JWT đến từ bên ngoài, các giá trị này **không tự tạo trust anchor**.

Một anti-pattern rất nguy hiểm:

~~~text
JWT header.jku = https://attacker.example/keys.json

Resource Server:
  1. Tải URL từ jku.
  2. Lấy public key của attacker.
  3. Kiểm chữ ký do attacker ký và thấy kết quả đúng.
  4. Tin luôn payload giả mạo issuer, audience, scope.
~~~

Đây là **key substitution**. Nếu cho fetch URL bất kỳ từ JWT header, còn có nguy cơ **SSRF**. Một HTTPS URL có certificate TLS hợp lệ chỉ chứng minh điều kiện bảo vệ kênh tới hostname đó, **không** chứng minh hostname được phép ký OAuth access token của issuer thật.

### 5.3. Xác minh chữ ký đúng với khóa nào?

Có hai câu hỏi độc lập:

1. Chữ ký có khớp với public key đang dùng hay không?
2. Public key đó có thuộc **issuer đã được API cho phép phát hành token** hay không?

Nếu câu thứ hai chưa được trả lời bằng trust policy độc lập, câu thứ nhất không đủ. Vì vậy, **chỉ verify chữ ký với một khóa bất kỳ không mạnh hơn đáng kể so với chỉ kiểm claims** nếu attacker được tự chọn key.

## 6. Giới hạn thuật toán ký, không làm theo alg của người gửi

Header JWS mang **alg** do token khai báo. Resource Server phải chủ động **allowlist** thuật toán và loại khóa theo hợp đồng với issuer.

Ví dụ chính sách:

~~~text
Trusted issuer:  https://login.example.com/realms/shop
Trusted JWKS:    https://login.example.com/realms/shop/certs
Accepted JWS:    RS256
~~~

Một token khai báo **HS256**, **none** hoặc thuật toán khác không được làm API tự động thay chính sách xác minh.

Những lỗi cần tránh:

| Lỗi | Hậu quả |
|---|---|
| Chấp nhận **alg = none** trong API yêu cầu signed JWT | Có thể nhận token không chữ ký |
| Để JWT tùy chọn mọi thuật toán | Có nguy cơ algorithm confusion |
| Dùng RSA public key như secret cho HMAC theo logic lỗi | Có thể tạo token giả không cần private RSA key |
| Không ràng buộc kty/alg/key-use | Có thể dùng loại khóa sai mục đích |
| Bỏ verify khi không tìm thấy kid | Không còn bảo đảm authenticity |

Spring Security dùng **NimbusJwtDecoder** có khả năng giới hạn thuật toán và nguồn JWKS. Hãy cấu hình chúng theo issuer và profile token thực tế; không nới lỏng chỉ để một token sai cấu trúc có thể đi qua.

## 7. Spring Boot Resource Server: issuer-uri, jwk-set-uri và audiences

Một cấu hình JWT Resource Server thông dụng:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com/realms/shop
          audiences:
            - orders-api
~~~

Ý nghĩa:

- **issuer-uri** chọn issuer đáng tin cậy, hỗ trợ discovery và kiểm issuer.
- Spring Security có thể lấy metadata và public JWKS của issuer để verify chữ ký.
- **audiences** yêu cầu token được phát hành cho **orders-api**.
- Token không hợp lệ về chữ ký, nguồn hoặc những claims cần kiểm phải bị từ chối.

Các địa chỉ chỉ là ví dụ. Phiên bản Spring Boot/Spring Security khác nhau có thể có cấu hình hỗ trợ cụ thể khác nhau; hãy dùng property phù hợp với bản dự án.

### 7.1. Chỉ định trực tiếp jwk-set-uri khi cần

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com/realms/shop
          jwk-set-uri: https://login.example.com/realms/shop/protocol/openid-connect/certs
          audiences:
            - orders-api
~~~

**jwk-set-uri ở đây là giá trị do hệ thống quản trị**, không phải lấy từ **jku** do token chưa verify mang theo.

Giữ **issuer-uri** giúp tránh trường hợp chỉ xác minh chữ ký bằng một tập khóa rồi quên kiểm **iss**. **audiences** vẫn cần để phân biệt token dành cho API nào.

### 7.2. Dependency của Resource Server

| Spring Boot | Starter OAuth2 Resource Server |
|---|---|
| **3.x** | **spring-boot-starter-oauth2-resource-server** |
| **4.x** | **spring-boot-starter-security-oauth2-resource-server** |

JWT Resource Server sử dụng các module Spring Security OAuth2 Resource Server và JOSE phù hợp theo dependency management của Spring Boot. Tránh ghép các major Spring Security khác nhau một cách thủ công.

## 8. JwtDecoder là ranh giới xác thực JWT trong Spring Security

Với **Servlet Resource Server**, luồng thông dụng:

~~~mermaid
flowchart LR
    R[Authorization: Bearer] --> B[BearerTokenAuthenticationFilter]
    B --> P[JwtAuthenticationProvider]
    P --> D[JwtDecoder]
    D -->|Signature/validators lỗi| E[401]
    D -->|Hợp lệ| C[JwtAuthenticationConverter]
    C --> A[JwtAuthenticationToken]
    A --> F[Authorize HTTP/method/resource]
    F -->|Thiếu quyền| X[403/404]
    F -->|Đủ quyền| O[Controller và service]
~~~

**JwtDecoder** không phải Base64URL decoder đơn giản. Với **NimbusJwtDecoder** được cấu hình đúng, decoder thực hiện kiểm chứng mật mã và áp dụng **OAuth2TokenValidator<Jwt>**. Chỉ khi decode thành công, Spring Security mới nên chuyển claims thành principal và authorities.

### 8.1. SecurityFilterChain minh họa

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public/**").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            );

        return http.build();
    }
}
~~~

Đây là ví dụ Servlet/MVC, không phải WebFlux. Scope **orders.read** trong token đã được xác thực có thể được converter mặc định ánh xạ thành **SCOPE_orders.read**. Cấp scope này **không tự cấp quyền đọc mọi đơn hàng**; service/domain policy vẫn phải kiểm tenant và chủ sở hữu.

### 8.2. Đừng tự xây dựng Authentication từ claims chưa verify

Một controller tự Base64URL-decode JWT, đọc role rồi tạo **JwtAuthenticationToken** đã bỏ qua ranh giới authentication. Tên lớp **Jwt** hay **JwtAuthenticationToken** không khiến dữ liệu do người gửi tự viết trở nên đáng tin.

Đối với request thực tế, hãy để **JwtAuthenticationProvider** gọi **JwtDecoder** được cấu hình nguồn khóa và validators đúng. Những Jwt giả lập dành cho test có thể hữu ích để kiểm rule, nhưng không được hiểu là chứng cứ verification đã diễn ra.

## 9. Tự tạo NimbusJwtDecoder cần cả chữ ký và claim validators

Trong một số trường hợp, API cần chủ động giới hạn thuật toán hoặc định nghĩa validator audience. Ví dụ dưới đây chọn **trusted JWKS URI**, chỉ cho phép **RS256**, kiểm issuer/timestamps cùng audience:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
class JwtDecoderConfig {

    private static final String ISSUER =
        "https://login.example.com/realms/shop";

    private static final String JWKS_URI =
        "https://login.example.com/realms/shop/protocol/openid-connect/certs";

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(JWKS_URI)
            .jwsAlgorithm(SignatureAlgorithm.RS256)
            .build();

        OAuth2TokenValidator<Jwt> issuerAndTime =
            JwtValidators.createDefaultWithIssuer(ISSUER);

        OAuth2TokenValidator<Jwt> audience = jwt ->
            jwt.getAudience().contains("orders-api")
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        "invalid_token",
                        "Token audience does not include orders-api",
                        null
                    )
                );

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(issuerAndTime, audience)
        );
        return decoder;
    }
}
~~~

Ý nghĩa của từng phần:

| Cấu hình | Mục đích |
|---|---|
| **withJwkSetUri** | Lấy public keys từ một nguồn đã được tin cậy |
| **jwsAlgorithm(RS256)** | Chỉ chấp nhận thuật toán ký phù hợp |
| **createDefaultWithIssuer** | Tạo những kiểm tra mặc định và issuer/timestamp |
| **audience validator** | Yêu cầu access token dành cho Orders API |
| **DelegatingOAuth2TokenValidator** | Kết hợp điều kiện cần đồng thời thỏa |
| **decode** | Trả Jwt đã được decoder chấp nhận hoặc ném JwtException |

Nếu tự tạo **@Bean JwtDecoder**, Spring Boot có thể không tự bổ sung các validators đã cấu hình qua property vào decoder tùy chỉnh. Khi đó ứng dụng chịu trách nhiệm giữ đủ **iss**, **aud**, **exp/nbf**, thuật toán, token type/profile và những điều kiện cần thiết.

### 9.1. Một custom JwtDecoder chỉ parse JSON vẫn không an toàn

~~~java
// PSEUDOCODE MÔ TẢ CÁCH LÀM SAI, không phải lớp hoàn chỉnh.
class ClaimsOnlyJwtDecoder implements JwtDecoder {

    @Override
    public Jwt decode(String token) {
        Map<String, Object> claims = parseJwtPayloadWithoutSignature(token);

        checkIssuer(claims);
        checkAudience(claims);
        checkExpiration(claims);

        return createJwtWithUntrustedClaims(token, claims);
    }
}
~~~

Các hàm trong ví dụ chỉ là tên giả định minh họa. Decoder này vẫn chấp nhận JWT tự tạo có claims đúng, bởi nó chưa hề kiểm signature hay nguồn khóa. **Thêm bao nhiêu claim validator cũng không thay thế được verification.**

Không tự viết parser/crypto thủ công cho production nếu có thể dùng Spring Security/Nimbus JOSE được bảo trì.

### 9.2. Thay validator phải giữ những kiểm tra mặc định

~~~java
NimbusJwtDecoder decoder = NimbusJwtDecoder
    .withJwkSetUri(trustedJwksUri)
    .build();

// SAI nếu chỉ giữ custom scope rule mà làm mất issuer/time validators.
decoder.setJwtValidator(onlyCustomScopeValidator);
~~~

Trong ví dụ trên, chữ ký vẫn có thể được Nimbus kiểm, nhưng **iss** và thời hạn có thể không còn được kiểm theo policy mà ứng dụng mong đợi. Hãy tổ hợp custom validator với validator mặc định, issuer, audience và token profile cần thiết.

Tóm lại có hai lỗi khác nhau: **không kiểm chữ ký** và **chỉ kiểm chữ ký nhưng quên claims**. Cả hai đều phải được xử lý.

## 10. JWT thật nhưng sai audience hoặc sai loại token vẫn phải bị từ chối

Một token được ký bằng private key thật của issuer vẫn có thể không hợp lệ đối với Orders API.

Ví dụ JWT:

~~~json
{
  "iss": "https://login.example.com/realms/shop",
  "aud": ["payments-api"],
  "scope": "payments.read",
  "exp": 1893456000
}
~~~

Chữ ký có thể hợp lệ, **iss** có thể đúng, nhưng **aud** là **payments-api**. Orders API yêu cầu **orders-api** phải từ chối token.

Tương tự, **OIDC ID Token** có thể là JWT do cùng OpenID Provider ký. ID Token chủ yếu dành cho OIDC Client, không tự biến thành access token để gọi Resource Server. Cần kiểm **aud**, token type/profile, chẳng hạn các yêu cầu của **RFC 9068** đối với JWT access token khi hệ sinh thái dùng profile này.

Claims **sub**, **email**, **email_verified**, **openid**, **profile** có thể hữu ích về danh tính nhưng không tự tạo quyền nghiệp vụ.

## 11. Với opaque token, xác minh nguồn qua introspection

OAuth2 không yêu cầu mọi access token đều là JWT. **Opaque token** có thể là một chuỗi không chứa cấu trúc JWT mà Resource Server có thể tự xác minh.

Trong mô hình đó, Resource Server sử dụng **introspection endpoint được cấu hình tin cậy** và thông tin xác thực thích hợp để yêu cầu Authorization Server xác nhận token.

~~~mermaid
sequenceDiagram
    participant C as OAuth Client
    participant RS as Resource Server
    participant AS as Trusted Authorization Server
    C->>RS: Authorization: Bearer opaque-token
    RS->>AS: POST introspection qua HTTPS và client authentication
    AS-->>RS: active=true và token metadata
    RS->>RS: Kiểm active, aud/scope và chính sách thích hợp
    RS-->>C: Cho phép hoặc từ chối
~~~

Điểm khác nhau:

| JWT ký số | Opaque token |
|---|---|
| Kiểm chữ ký với key được issuer tin cậy công bố | Gọi introspection endpoint của AS đáng tin cậy |
| Có thể đọc claims JWT sau verification | Lấy token metadata từ introspection response |
| Thường dùng JwtDecoder | Thường dùng OpaqueTokenIntrospector |
| Không được tin Base64URL-decoded JSON chưa verify | Không được tin kết quả giả từ endpoint do client tùy ý chỉ định |

Ví dụ cấu hình Spring Boot, với placeholders cho secret environment:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://login.example.com/oauth2/introspect
          client-id: example-introspection-client
          client-secret: configure-secret-outside-source-control
~~~

Hai giá trị client identity/secret là minh họa, **không đặt credential thật trong source control**. Dùng secret manager hoặc biến môi trường được bảo vệ, cấu hình HTTPS và xác minh certificate của introspection endpoint.

Kết quả **active=true** chỉ đáng tin khi đến từ **AS đã được API tin cậy qua giao thức introspection được bảo vệ**. Tương tự chữ ký JWT, chỉ có một JSON body chứa active và scope là chưa đủ nếu nguồn phản hồi không đáng tin.

Một số hệ thống có JWT nhưng vẫn sử dụng introspection để kiểm active/revocation; vấn đề cần hiểu là **có một phương thức xác thực token do issuer ủy quyền**, không phải chỉ có JSON claims.

## 12. Không dùng trust vào reverse proxy thay cho xác minh token

Giả sử backend nhận:

~~~http
Authorization: Bearer <access-token>
X-Authenticated-User: admin
X-User-Roles: ADMIN
~~~

Nếu một client bên ngoài có thể tự gửi **X-Authenticated-User** hoặc **X-User-Roles**, backend không được dùng chúng làm bằng chứng danh tính. Header có vẻ hợp lệ không khác mấy so với JWT claims có vẻ hợp lệ nhưng chưa xác minh.

Có hai kiến trúc có thể lựa chọn:

**A. Resource Server tự xác thực token:** API Gateway chuyển tiếp access token qua kết nối được bảo vệ; Spring Security kiểm chữ ký/JWKS hoặc introspection như bình thường.

**B. Gateway được ủy quyền xác thực:** Gateway xác thực token, rồi chuyển một ngữ cảnh danh tính nội bộ qua cơ chế bảo vệ độc lập; backend chặn truy cập trực tiếp, xác thực kết nối từ gateway và chỉ tin những header/claims nội bộ đã được gateway ghi đè theo chính sách. Cần tài liệu hóa trust boundary và kiểm quyền nghiệp vụ ở backend.

**Một token được chuyển qua HTTPS hoặc mạng private không tự trở nên hợp lệ.** HTTPS ngăn nghe lén trên chặng truyền; nó không chứng minh JWT payload do issuer đáng tin cậy phát hành.

## 13. Phân biệt HTTP 401 và 403

Các trường hợp thường gặp trong Bearer Resource Server:

| Trường hợp | Lỗi chính | HTTP thường gặp |
|---|---|---|
| Thiếu Bearer token | Chưa xác thực | **401** |
| Token không đúng cấu trúc JWT | Parse thất bại | **401** |
| Claims đúng nhưng chữ ký sai | Authentication thất bại | **401** |
| JWT ký bằng khóa attacker rồi tự khai issuer thật | Nguồn khóa không đáng tin | **401** |
| Chữ ký đúng, issuer sai | Claim validation | **401** |
| Chữ ký đúng, audience sai | Claim validation | **401** |
| Token hết hạn hoặc chưa đến thời điểm nbf | Claim validation | **401** |
| Token hợp lệ, thiếu **orders.read** | Authorization | **403** |
| Token hợp lệ, đủ scope nhưng đơn thuộc tenant khác | Resource authorization | **403** hoặc **404** theo chính sách |
| Token hợp lệ, scope và quyền dữ liệu đều đúng | Đạt authentication/authorization | API tiếp tục xử lý, có thể **200** |

Với Bearer API, 401 thường kèm **WWW-Authenticate: Bearer**. Cách xử lý chính xác phụ thuộc cấu hình exception handling.

Không sửa 401 do JWT giả bằng cách bỏ signature verification. Không sửa 401 sai audience bằng cách bỏ audience validator. Không sửa 403 thiếu quyền bằng cách mở endpoint thành **permitAll()**.

## 14. Kiểm thử phải phân biệt mock claims với xác minh thật

Spring Security Test có **jwt() request post-processor** cho Servlet tests. Nó tiện để mô phỏng Authentication và kiểm web/method authorization, nhưng trong cách dùng thông thường **không chạy JwtDecoder thật để verify chữ ký**.

Ví dụ:

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@Test
void allowsReadScope() throws Exception {
    mockMvc.perform(get("/api/orders/42")
            .with(jwt().authorities(() -> "SCOPE_orders.read")))
        .andExpect(status().isOk());
}
~~~

Đoạn test rút gọn giả định có **mockMvc**, controller và fixture trả 200. Nó có thể kiểm rule **SCOPE_orders.read**, nhưng **không chứng minh API từ chối chữ ký giả**.

Để kiểm đúng ranh giới xác thực token, cần có các loại test khác nhau:

1. **Authorization test** với mock principal/authorities để thử scope, role, tenant và ownership.
2. **JwtDecoder test** dùng các JWT được ký bằng private key của test issuer và những JWT đã bị sửa/giả.
3. **HTTP integration test** gửi Bearer token thật qua security chain với issuer/JWKS test được cấu hình tin cậy.
4. **Operational test** kiểm TLS, JWKS cache, rotation, introspection endpoint và fail-closed behavior.

Ví dụ ý tưởng cho JwtDecoder test:

~~~java
// Pseudocode: fixture cung cấp token và public key/JWKS kiểm thử.
Jwt jwt = jwtDecoder.decode(validSignedToken);

assertThrows(JwtException.class,
    () -> jwtDecoder.decode(tamperedPayloadToken));

assertThrows(JwtException.class,
    () -> jwtDecoder.decode(attackerSignedToken));

assertThrows(JwtException.class,
    () -> jwtDecoder.decode(wrongAudienceToken));
~~~

Ở đây **validSignedToken** là token được ký bởi private key của issuer test; **tamperedPayloadToken** bị sửa payload mà không ký lại; **attackerSignedToken** dùng một key không nằm trong tập khóa tin cậy; **wrongAudienceToken** có chữ ký đúng nhưng aud không phù hợp. Test phải được nối tới JwtDecoder thật và các validator tương ứng.

### 14.1. Một case đặc biệt hữu ích: claims đúng, signature sai

Tạo JWT giả có payload:

~~~json
{
  "iss": "https://login.example.com/realms/shop",
  "sub": "admin",
  "aud": ["orders-api"],
  "scope": "orders.read orders.write",
  "exp": 4102444800
}
~~~

JWT này phải bị **từ chối** nếu chữ ký không khớp key được issuer tin cậy ủy quyền. Case này phát hiện rõ nhất lỗi “chỉ kiểm claims”.

Không commit access token thật hoặc private signing key production vào repository/test fixture. Chỉ dùng test keys/tokens dành cho môi trường thử nghiệm.

## 15. Lỗi thiết kế thường gặp

### 15.1. Controller tự parse JWT

Controller đọc **Authorization**, split token, decode payload rồi dùng role/scope để ra quyết định. Cách này bỏ qua JwtAuthenticationProvider/JwtDecoder. Phải để Spring Security xác thực access token rồi mới lấy Authentication đã được thiết lập.

### 15.2. Custom JwtDecoder chỉ tạo Jwt từ JSON

Nếu triển khai JwtDecoder tự viết chỉ parse JSON và kiểm vài claims, interface có tên đúng nhưng trust boundary bị phá vỡ. Không dùng một object Jwt do chương trình tự dựng từ input chưa verify làm bằng chứng authentication.

### 15.3. Kiểm signature bằng khóa do token tự chọn

**jku**, **jwk**, **x5u** hoặc một URL được ghép từ **kid** không được tự động thay trusted JWKS. Việc chữ ký khớp khóa của attacker không chứng minh nguồn issuer hợp lệ.

### 15.4. Bỏ issuer hoặc audience validator sau khi verify

Một JWT được issuer ký đúng nhưng **aud = payments-api** không được Orders API chấp nhận. Ngược lại, token từ issuer không được phép cũng phải bị từ chối ngay cả khi claims khác trông đúng.

### 15.5. Bỏ hết hạn vì chữ ký hợp lệ

Chữ ký đúng có thể vẫn tồn tại sau **exp**. Timestamps, clock skew thích hợp và revocation policy là vấn đề độc lập với signature verification.

### 15.6. Dùng ID Token như access token

OIDC ID Token thường dành cho client xác minh đăng nhập; nó không mặc nhiên là token ủy quyền gọi API. Cần audience/token type/profile đúng. Cùng một issuer hoặc cùng JWKS không đủ để hoán đổi hai loại token.

### 15.7. Token qua gateway nên bỏ verify

Chỉ bỏ kiểm token ở backend nếu đã thiết kế và chứng minh một trust delegation thay thế có ranh giới rõ ràng. Không dựa vào IP private, forwarded header hoặc tên upstream để tự cấp Authentication.

### 15.8. Khi JWKS lỗi thì chấp nhận claims

Nếu Resource Server không thể xác minh token bằng khóa tin cậy, không được chuyển sang “parse để dùng tạm”. Tận dụng cache/rotation hợp lệ theo thiết kế, nhưng phải **fail closed** khi thiếu bằng chứng xác thực.

### 15.9. Ghi raw Bearer token vào log

Bearer token có thể bị tái sử dụng khi còn hiệu lực. Không log raw JWT, Authorization header, refresh token, ID Token hoặc introspection client secret. Nên ghi request ID, mã lỗi tổng quát và metadata ít nhạy cảm theo chính sách.

## 16. Quy trình phân tích một request Bearer token

Giả sử Orders API công bố:

~~~text
Issuer:       https://login.example.com/realms/shop
Trusted JWKS: https://login.example.com/realms/shop/certs
Allowed alg:  RS256
Audience:     orders-api
Scope read:   orders.read
Scope write:  orders.write
Data policy:  chỉ thao tác đơn trong tenant được cấp quyền
~~~

Một request **POST /api/orders/42/approve** đến API được xử lý theo các bước:

**Bước 1 — Nhận Bearer token.** Sự hiện diện của header Authorization không phải bằng chứng token hợp lệ.

**Bước 2 — Parse cấu trúc JOSE/JWT.** Header và claims ban đầu chỉ là dữ liệu chưa được tin cậy.

**Bước 3 — Chọn nguồn khóa.** Decoder chỉ tìm public key trong trusted JWKS/issuer, không chấp nhận key do token tự chỉ định.

**Bước 4 — Xác minh signature.** Nếu token bị sửa hoặc được ký bằng key không tin cậy, trả 401.

**Bước 5 — Validate claims.** Kiểm issuer, audience, exp, nbf, token type/profile. Nếu token ký đúng nhưng dành cho API khác, vẫn trả 401.

**Bước 6 — Tạo Authentication.** Chỉ dùng claims đã được decoder chấp nhận để tạo principal và authorities.

**Bước 7 — Authorization.** Kiểm scope cần cho thao tác approve, rồi kiểm đơn hàng có thuộc tenant/owner và trạng thái nghiệp vụ cho phép hay không.

**Bước 8 — Thực thi nghiệp vụ.** Chỉ sau các lớp kiểm tra trên mới thay đổi dữ liệu.

Quy trình này giữ rõ bốn ranh giới: **đọc dữ liệu → xác minh nguồn/chữ ký → kiểm claims → cấp quyền thực tế**.

## 17. Các câu hỏi cần trả lời khi review Resource Server

1. Token là **JWT/JWS**, **JWE** hay **opaque**? Cơ chế xác thực nào thực sự phù hợp?
2. Issuer được tin cậy đến từ **cấu hình/allowlist** hay từ giá trị **iss** bất kỳ trong token?
3. Public keys lấy từ **JWKS URI tin cậy** hay từ **jku/jwk/x5u** mà token tự nêu?
4. API giới hạn **alg** và loại khóa được chấp nhận như thế nào?
5. **JwtDecoder** có thực sự verify chữ ký không, hay custom implementation chỉ parse JSON?
6. Bộ validator đã kiểm **iss**, **aud**, **exp**, **nbf** và token type/profile chưa?
7. Custom decoder có vô tình thay thế hoặc bỏ các validators mặc định không?
8. Opaque token được introspect qua **endpoint đáng tin** và kết quả **active** có được kiểm đúng không?
9. Scope/role/permissions có được lấy từ **Authentication đã xác thực** không?
10. Quyền tenant, owner, membership và trạng thái bản ghi được kiểm ở đâu?
11. Các test đã dùng JWT **claims đúng nhưng chữ ký giả** chưa?
12. Khi JWKS hoặc introspection unavailable, hệ thống có từ chối token chưa xác minh không?
13. Có log/token leaks hoặc trust headers do client tự gửi qua proxy không?

## Kết luận

**Kiểm tra claims không thể thay thế xác minh chữ ký hoặc nguồn token.** Claim **iss** là một chuỗi mà token tự khai. Claim **aud** cho biết đối tượng nhận mà token tuyên bố. Claim **exp** cho biết thời gian hiệu lực được ghi trong payload. Claim **scope** mô tả quyền được ghi trong token. **Không claim nào tự chứng minh Authorization Server đã phát hành token ấy**.

Với **JWT/JWS**, Spring Security Resource Server cần trusted issuer/JWKS, thuật toán được phép, signature verification qua **JwtDecoder**, rồi mới chạy claims validation và authorization. Với **opaque token**, cần kết quả introspection từ Authorization Server tin cậy chứ không phải JSON tùy ý. Ngay cả token được xác thực vẫn phải được kiểm audience, thời hạn, token type và quyền nghiệp vụ đối với tài nguyên cụ thể.

### Tài liệu tham khảo

- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html)
- [Spring Security API — JwtDecoder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/JwtDecoder.html)
- [Spring Security API — NimbusJwtDecoder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/NimbusJwtDecoder.html)
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515)
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
