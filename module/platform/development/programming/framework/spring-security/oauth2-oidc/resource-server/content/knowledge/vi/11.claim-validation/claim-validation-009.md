# Giữ validator mặc định khi thêm yêu cầu mới

Khi triển khai **Spring Security OAuth 2.0/OIDC Resource Server**, một API thường xác thực JWT access token do Authorization Server/Identity Provider (IdP) phát hành. Ban đầu ứng dụng có thể chỉ cấu hình `issuer-uri`, sau đó phát sinh các yêu cầu bổ sung như:

- Chỉ chấp nhận access token dành cho chính API (`aud`).
- Bắt buộc có `tenant_id` hoặc chỉ nhận token từ một nhóm tenant.
- Giới hạn thời lượng token (`exp - iat`) hoặc tuổi token.
- Bắt buộc token đúng profile/loại, ví dụ JWT access token chứ không phải OIDC ID token.
- Từ chối token có claim không nhất quán với hợp đồng.

Khi viết thêm một `OAuth2TokenValidator<Jwt>`, lỗi dễ gặp là **thay thế toàn bộ bộ validator trước đó** bằng validator mới. API tưởng đã tăng cường bảo mật, nhưng lại có thể vô tình bỏ qua kiểm tra `exp`, `nbf`, `iss` hoặc các ràng buộc mặc định khác do Spring Security áp dụng trong cách dựng decoder trước đó.

Nguyên tắc của bài:

> **Thêm quy tắc kiểm tra claim bằng cách hợp thành với bộ validator mặc định của đúng hợp đồng, không ghi đè mù quáng.** Ký số, issuer, thời hạn, audience và quyền nghiệp vụ là những điều kiện độc lập, cần duy trì cùng nhau.

Bài viết sử dụng **Servlet Resource Server, Spring Security 6+/Spring Boot 3+** làm nền tảng cho các ví dụ Java. API/class và mặc định có thể khác giữa các phiên bản; khi dùng một version cụ thể, phải xác định bộ validator đã được framework áp dụng và các thay đổi mà custom decoder mang lại.

## 1. Một JWT hợp lệ phải vượt qua nhiều lớp kiểm chứng

Một request vào Orders API:

```http
GET /api/orders/ord-123 HTTP/1.1
Host: orders.example.com
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
```

Access token có thể mang payload:

```json
{
  "iss": "https://idp.example.com/realms/shop",
  "sub": "user-842",
  "aud": ["orders-api"],
  "iat": 1893456000,
  "nbf": 1893456000,
  "exp": 1893459600,
  "scope": "orders.read",
  "tenant_id": "tenant-a"
}
```

Các giá trị trong ví dụ chỉ để học, không phải JWT đã được ký. Resource Server cần đánh giá nhiều điều kiện:

| Lớp | Câu hỏi cần trả lời | Thành phần xử lý thường gặp |
|---|---|---|
| Trích xuất credential | Bearer token nằm ở đâu trong HTTP request? | `BearerTokenResolver` |
| Mật mã | JWT có chữ ký hợp lệ theo khóa và thuật toán được phép? | `JwtDecoder` / Nimbus JOSE |
| Issuer | Token có do nhà phát hành được tin cậy cấp? | `JwtIssuerValidator` hoặc validator tương đương |
| Thời gian | Token có hết hạn hoặc chưa tới thời điểm hiệu lực? | `JwtTimestampValidator` |
| Audience | Token có được cấp cho `orders-api`? | Validator audience theo hợp đồng |
| Claim bổ sung | Tenant, loại token, tuổi token hoặc ràng buộc khác có đúng? | Custom `OAuth2TokenValidator<Jwt>` |
| Quyền endpoint | Token có authority `SCOPE_orders.read`? | `AuthorizationManager` / HTTP security |
| Quyền tài nguyên | User/tenant có được xem đơn hàng `ord-123`? | Service/domain policy |

Những bước này không thể thay thế cho nhau. Ví dụ, token có `aud=orders-api` nhưng đã hết hạn thì phải bị từ chối. Token có chữ ký đúng và chưa hết hạn nhưng `aud=payments-api` cũng phải bị từ chối tại Orders API. Một token hợp lệ có scope `orders.read` vẫn không mặc định cho quyền xem đơn hàng của tenant khác.

### 1.1. Authentication và authorization khác nhau

```mermaid
flowchart TD
    A["HTTP Bearer request"] --> B["BearerTokenAuthenticationFilter"]
    B --> C["JwtDecoder"]
    C --> D{"JWS signature, trusted key,<br/>algorithm đúng?"}
    D -->|"Không"| X["401: invalid token"]
    D -->|"Có"| E{"Default validators:<br/>issuer, timestamp, ...?"}
    E -->|"Không"| X
    E -->|"Có"| F{"Custom validators:<br/>audience, tenant, token age, ...?"}
    F -->|"Không"| X
    F -->|"Có"| G["JwtAuthenticationToken / SecurityContext"]
    G --> H{"Scope + quyền tài nguyên?"}
    H -->|"Không"| Y["403 hoặc policy từ chối"]
    H -->|"Có"| Z["Controller / Service"]
```

Việc giữ validator mặc định thuộc **lớp xác thực và kiểm tra hợp đồng access token**. Nó không thay thế `authorizeHttpRequests`, `@PreAuthorize` hoặc chính sách owner/tenant của nghiệp vụ.

## 2. Validator trong Spring Security hoạt động như thế nào?

Spring Security cung cấp interface:

```java
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;

public interface OAuth2TokenValidator<T> {
    OAuth2TokenValidatorResult validate(T token);
}
```

Khi dùng để kiểm tra JWT, loại tham số thường là `Jwt`. Một validator:

- Nhận đối tượng JWT đã được decoder xử lý theo luồng xác thực tương ứng.
- Đánh giá một hoặc nhiều điều kiện, ví dụ `aud` chứa tên API.
- Trả về `OAuth2TokenValidatorResult.success()` nếu điều kiện thỏa.
- Trả về `OAuth2TokenValidatorResult.failure(...)` nếu không thỏa.

Đây là một **hợp đồng trả kết quả**, không phải một HTTP filter. Validator không đọc `Authorization` header, không ký JWT, không sửa nội dung token để làm nó hợp lệ và không quyết định quyền trên từng entity trong database.

### 2.1. Một validator audience đơn giản

```java
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;

public final class RequiredAudienceValidator
        implements OAuth2TokenValidator<Jwt> {

    private final String requiredAudience;

    public RequiredAudienceValidator(String requiredAudience) {
        this.requiredAudience = requiredAudience;
    }

    @Override
    public OAuth2TokenValidatorResult validate(Jwt jwt) {
        if (jwt.getAudience().contains(requiredAudience)) {
            return OAuth2TokenValidatorResult.success();
        }
        return OAuth2TokenValidatorResult.failure(
            new OAuth2Error(
                "invalid_token",
                "JWT audience is not accepted by this API",
                null
            )
        );
    }
}
```

`jwt.getAudience()` cung cấp tập audience; một JWT có thể biểu diễn `aud` bằng chuỗi hoặc mảng theo chuẩn. Kiểm tra thành viên theo giá trị **chính xác**, không dùng so khớp một phần như `aud.contains("orders")` trên JSON raw hay chỉ so domain gần giống.

Validator này có ích, nhưng **không tự kiểm tra issuer và thời hạn**. Nếu đưa nó vào decoder bằng cách thay toàn bộ validator đang dùng, Resource Server có thể mất những kiểm tra cần thiết khác.

### 2.2. Các validator độc lập phải cùng đúng

Ví dụ hợp đồng Orders API:

```text
issuer đúng = https://idp.example.com/realms/shop
audience bắt buộc = orders-api
token chưa hết hạn
token không ở trước nbf
tenant_id bắt buộc
JWT profile đúng loại access token
```

Một token chỉ được chấp nhận khi **tất cả điều kiện bắt buộc** đều đúng. Với mô hình hợp thành validator, phép kiểm chứng mang ý nghĩa logic:

```text
VALID =
  signatureValid
  AND issuerValid
  AND timeValid
  AND audienceValid
  AND customClaimsValid
```

`OAuth2TokenValidator` có thể được dùng để kiểm tra claim sau khi phần mật mã của decoder đã xử lý. Không dùng custom claim validator để “bù” cho một bộ giải mã bỏ qua chữ ký hoặc cho phép thuật toán không đáng tin.

## 3. Bộ validator mặc định là gì?

Spring Security có helper quan trọng:

```java
JwtValidators.createDefault()
JwtValidators.createDefaultWithIssuer(trustedIssuer)
```

Trong các cấu hình JWT Resource Server thông dụng:

- `JwtValidators.createDefault()` tạo các validator nền tảng được Spring Security xem là mặc định cho phiên bản đang dùng.
- `JwtValidators.createDefaultWithIssuer(issuer)` bổ sung ràng buộc issuer được chỉ định cùng những validator nền tảng.
- Kiểm tra **thời gian JWT** thông qua `JwtTimestampValidator`, thường gồm các mốc `exp` và `nbf` khi áp dụng theo hợp đồng/claim hiện diện.
- Các yêu cầu khác như kiểm tra loại token/JWT profile có thể phụ thuộc phiên bản/framework setup, ví dụ cấu hình JOSE `typ` và các validator type. Không nên sao chép danh sách “mặc định chắc chắn chỉ có hai validator” để dùng cho mọi phiên bản.

Điểm cốt lõi là sử dụng helper phù hợp, thay vì tự suy luận rồi dựng lại một bộ validator thủ công quá hẹp:

```java
OAuth2TokenValidator<Jwt> defaults =
    JwtValidators.createDefaultWithIssuer(trustedIssuer);
```

Với API chỉ tin một issuer cụ thể, phiên bản `WithIssuer` giúp biểu đạt ranh giới tin cậy. Nếu bạn tạo decoder từ JWK Set URI nhưng không thiết lập issuer validator, **chữ ký đúng bằng một khóa được chọn không tự đồng nghĩa claim `iss` được đối chiếu với issuer mà API mong đợi**.

### 3.1. Signature verification không phải claim validation

`NimbusJwtDecoder` xác minh chữ ký JWS bằng khóa/tập khóa tin cậy và những ràng buộc JOSE. Bộ `OAuth2TokenValidator<Jwt>` kiểm tra các điều kiện của token như issuer, thời hạn và audience.

```text
JWT từ client
    |
    v
NimbusJwtDecoder:
    parse + verify JWS với key/algorithm tin cậy
    |
    v
OAuth2TokenValidator<Jwt>:
    issuer, exp, nbf, audience, chính sách bổ sung...
    |
    v
Verified Jwt / JwtAuthenticationToken
```

Một token có chữ ký đúng mà `exp` đã hết hạn phải bị từ chối. Ngược lại, một token có claim `exp` hợp lệ nhưng chữ ký sai cũng phải bị từ chối. Không nên dùng `JwtDecoder` “chỉ parse” hoặc decode Base64 payload để thay decoder xác minh chữ ký thực sự.

### 3.2. Có phải mọi JWT đều bắt buộc có exp, nbf, iat, iss?

**Không thể suy ra chỉ từ RFC 7519.** JWT specification định nghĩa ý nghĩa các registered claims, nhưng sự hiện diện và yêu cầu bắt buộc do **token profile và hợp đồng API** quyết định. JWT access token theo RFC 9068 có các quy định chặt hơn JWT tùy ý.

Vì vậy, hãy phân biệt:

1. **Validator mặc định** xử lý các claim được hỗ trợ khi chúng hiện diện và những điều kiện mặc định của framework.
2. **Hợp đồng ứng dụng/token profile** có thể yêu cầu một số claim phải luôn có, chẳng hạn issuer, audience hoặc expiration.
3. **Custom validator** có thể bổ sung kiểm tra sự hiện diện/quan hệ giữa các claim đó.

Không được tự tin rằng mọi claim đã được bắt buộc hiện diện chỉ vì chọn `JwtValidators.createDefault()`. Khi cần profile access token cụ thể, phải đối chiếu điều kiện của profile đó và thêm validator tương ứng.

## 4. Sai lầm điển hình: setJwtValidator thay thế chứ không tự động nối thêm

Giả sử code tạo decoder JWT:

```java
NimbusJwtDecoder decoder =
    NimbusJwtDecoder.withIssuerLocation(trustedIssuer).build();
```

Developer muốn thêm audience nên viết:

```java
// KHÔNG NÊN: vô tình thay toàn bộ bộ validator được dùng.
decoder.setJwtValidator(new RequiredAudienceValidator("orders-api"));
```

Vấn đề: `NimbusJwtDecoder#setJwtValidator(...)` dùng validator bạn truyền để kiểm tra JWT; đây là thao tác **thiết lập/thay thế validator**, không phải hàm có semantics “append to existing defaults”.

Hệ quả có thể là decoder giờ chỉ kiểm tra audience ở lớp `OAuth2TokenValidator`, khiến các ràng buộc như issuer và thời gian vốn có trong bộ validator cũ **không còn được áp dụng theo cách dự kiến**. Chữ ký vẫn có thể được kiểm chứng, nhưng chỉ kiểm chứng chữ ký là không đủ bảo vệ Resource Server.

### 4.1. Lỗi còn khó thấy khi token thử nghiệm đều hợp lệ

Nếu test chỉ dùng token:

```json
{
  "iss": "https://idp.example.com/realms/shop",
  "aud": ["orders-api"],
  "exp": 1893459600
}
```

và token đang còn hạn, test có thể vẫn thành công sau khi thay validator. Lỗi chỉ bộc lộ khi có token **đúng audience nhưng hết hạn**, hoặc **đúng audience nhưng sai issuer** mà chữ ký vẫn có thể được kiểm chứng trong phạm vi khóa mà decoder tin.

Do đó yêu cầu “thêm audience validator” phải được hiểu là **giữ nguyên các điều kiện cũ, sau đó thêm audience**, không phải thay hẳn tập kiểm tra.

### 4.2. Cách làm đúng: hợp thành bằng DelegatingOAuth2TokenValidator

`DelegatingOAuth2TokenValidator` kết hợp nhiều `OAuth2TokenValidator<T>` theo quan hệ logic **AND**: token thành công khi các validator thành phần đều thành công.

```java
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;

OAuth2TokenValidator<Jwt> defaults =
    JwtValidators.createDefaultWithIssuer(trustedIssuer);

OAuth2TokenValidator<Jwt> audience =
    new RequiredAudienceValidator("orders-api");

OAuth2TokenValidator<Jwt> composed =
    new DelegatingOAuth2TokenValidator<>(defaults, audience);

decoder.setJwtValidator(composed);
```

Ở đây `setJwtValidator` vẫn **thay** validator nội bộ của decoder, nhưng thứ được thay vào đã bao gồm:

- Bộ kiểm tra mặc định đúng issuer.
- Bộ kiểm tra audience mới.

**Mẫu quan trọng nhất:**

```java
decoder.setJwtValidator(
    new DelegatingOAuth2TokenValidator<>(
        JwtValidators.createDefaultWithIssuer(trustedIssuer),
        extraValidator
    )
);
```

Điều này dễ đọc và giảm nguy cơ vô tình bỏ những kiểm tra nền tảng. Đừng xây `DelegatingOAuth2TokenValidator<>(extraValidator)` rồi cho rằng nó tự phát hiện các validator khác ở decoder.

## 5. Ví dụ đầy đủ: giữ mặc định khi thêm kiểm tra audience

Giả sử Orders API chỉ nhận JWT access token:

```yaml
# application.yml
app:
  security:
    issuer: https://idp.example.com/realms/shop
    audience: orders-api
```

Và Spring Security 6+:

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
public class JwtDecoderConfiguration {

    @Bean
    JwtDecoder jwtDecoder(
            @Value("${app.security.issuer}") String trustedIssuer,
            @Value("${app.security.audience}") String requiredAudience) {

        // Issuer này do ứng dụng cấu hình, không được lấy tùy ý
        // từ JWT chưa xác thực gửi đến.
        NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withIssuerLocation(trustedIssuer).build();

        OAuth2TokenValidator<Jwt> defaults =
            JwtValidators.createDefaultWithIssuer(trustedIssuer);

        OAuth2TokenValidator<Jwt> audience = jwt ->
            jwt.getAudience().contains(requiredAudience)
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        "invalid_token",
                        "Unexpected access-token audience",
                        null
                    )
                );

        OAuth2TokenValidator<Jwt> allValidators =
            new DelegatingOAuth2TokenValidator<>(
                defaults,
                audience
            );

        // Thay validator bằng TỔ HỢP mặc định + audience,
        // không thay bằng audience đơn lẻ.
        decoder.setJwtValidator(allValidators);
        return decoder;
    }
}
```

Một `SecurityFilterChain` sử dụng decoder đã đăng ký có thể viết:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ResourceServerSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/health").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
```

Spring Security sẽ dùng `JwtDecoder` bean mà application cung cấp cho JWT Resource Server chain khi không có decoder khác được chỉ định trực tiếp ở DSL. Vì `@Bean JwtDecoder` này là custom, Spring Boot thường **không tạo decoder JWT mặc định thứ hai**. Do đó ứng dụng chịu trách nhiệm cấu hình đầy đủ validators của bean tự tạo.

Các đảm bảo trong ví dụ:

1. Decoder lấy metadata/khóa từ issuer **đã được cấu hình tin cậy**.
2. Chữ ký và ràng buộc JOSE được xác minh bởi decoder.
3. `JwtValidators.createDefaultWithIssuer` giữ các kiểm tra mặc định và issuer.
4. Audience phải có `orders-api`.
5. Sau xác thực, endpoint kiểm tra `SCOPE_orders.read` hoặc `SCOPE_orders.write`.
6. Service vẫn phải kiểm tra quyền owner/tenant với từng đơn hàng.

### 5.1. Vì sao không lấy issuer từ jwt.getIssuer() để cấu hình decoder?

Sai về trust boundary:

```java
// Anti-pattern khái niệm:
String issuer = decodeUnverifiedPayload(token).getIssuer();
JwtDecoder decoder = JwtDecoders.fromIssuerLocation(issuer);
```

Mọi người gửi đều có thể tự đặt `iss` trong JWT chưa xác thực. Nếu API chấp nhận một issuer/JWKS từ URL do token cung cấp, attacker có thể điều khiển nguồn khóa mà API tin. Issuer tin cậy phải được **cấu hình hoặc chọn từ allowlist đã quản trị**, sau đó claim `iss` thực tế phải được validator so khớp.

### 5.2. Với API chỉ nhận một audience

Trong ví dụ `jwt.getAudience().contains(requiredAudience)` chấp nhận token có audience:

```json
{ "aud": ["orders-api"] }
```

hoặc:

```json
{ "aud": ["orders-api", "another-api"] }
```

Miễn là hợp đồng cho phép multi-audience, đây là cách xử lý phù hợp. Nếu API **bắt buộc audience chỉ chứa chính nó**, phải thêm policy rõ:

```java
boolean exactOnlyAudience =
    jwt.getAudience().size() == 1 &&
    jwt.getAudience().contains(requiredAudience);
```

Đó là yêu cầu **mạnh hơn** so với “audience có chứa orders-api”, và cần được thống nhất với Authorization Server. Không ngầm từ chối multi-audience nếu token profile thật sự cho phép; cũng không ngầm cho phép multi-audience nếu hợp đồng API yêu cầu tách biệt các tài nguyên.

## 6. Khi dùng auto-configuration của Spring Boot, có cần custom JwtDecoder không?

Không phải mọi yêu cầu claim mới đều đòi viết bean `JwtDecoder`. Với các phiên bản Spring Boot hiện đại, có thể cấu hình audience bằng property:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.com/realms/shop
          audiences:
            - orders-api
```

Khi ứng dụng chưa có custom decoder và đủ điều kiện auto-configuration, Spring Boot có thể dựng `JwtDecoder` kèm các ràng buộc issuer, thời gian và audience theo các property được hỗ trợ.

Điểm lợi: không cần gọi `setJwtValidator` bằng tay, giảm nguy cơ đánh mất kiểm tra mặc định. Đây thường là lựa chọn đơn giản nhất khi **yêu cầu mới chỉ là một thuộc tính Spring Boot đã hỗ trợ trực tiếp**.

### 6.1. Bean custom làm Boot nhường chỗ

Quy tắc cần nhớ:

| Trạng thái ứng dụng | Ý nghĩa |
|---|---|
| Chỉ cấu hình `issuer-uri`/`audiences`, không có `JwtDecoder` custom | Boot có thể tạo decoder với validators theo properties |
| Có `@Bean JwtDecoder` do developer viết | Boot thường không tạo decoder mặc định; code custom phải tự giữ validators |
| Có custom `SecurityFilterChain` nhưng chưa có `JwtDecoder` bean | Boot vẫn có thể tạo decoder; chain phải bật `oauth2ResourceServer().jwt()` |
| Chain chỉ bật `httpBasic()` dù có decoder | Decoder có thể tồn tại nhưng không tự được Bearer filter dùng |
| Chain chỉ định `jwt.decoder(customDecoder)` trực tiếp | Chain dùng decoder được chỉ định; thay property Boot có thể không thay hành vi đó |

**Tạo một bean chỉ cho audience có thể là quá mức cần thiết nếu property `audiences` đã đáp ứng hợp đồng.** Nhưng nếu phải kiểm tra tenant, tuổi token hoặc claim profile tùy biến, có thể cần decoder/validator do ứng dụng điều khiển.

### 6.2. Đừng nhầm issuer-uri, jwk-set-uri và audiences

| Cấu hình | Trách nhiệm |
|---|---|
| `issuer-uri` | Khai báo nhà phát hành tin cậy và tạo điều kiện kiểm tra claim `iss` |
| `jwk-set-uri` | Chỉ định nguồn public keys để xác minh JWS signature |
| `audiences` | Ràng buộc token được phát hành cho những audience API yêu cầu |

Khi chỉ cấu hình `jwk-set-uri`, API biết **lấy khóa ở đâu** nhưng không nhất thiết có **ràng buộc issuer** được thiết lập bằng một issuer rõ ràng. Nếu ứng dụng yêu cầu cả hai, phải cấu hình `issuer-uri` hoặc validator issuer độc lập.

Đồng thời, việc có issuer hợp lệ không tự động bảo đảm audience được kiểm tra trong mọi phiên bản/cách dựng decoder. Hợp đồng phải quy định rõ từng giá trị.

## 7. Thêm nhiều validator: audience, tenant và độ tuổi token

Một Resource Server có thể cần ba điều kiện bổ sung:

1. Audience phải chứa `orders-api`.
2. Claim `tenant_id` phải hiện diện và thuộc nhóm tenant API được cấu hình cho phép.
3. Access token không được quá cũ so với `iat` và phải có `iat` theo hợp đồng.

Các validator này **không thay** kiểm tra issuer, expiration hoặc not-before.

### 7.1. Validator tenant

```java
import java.util.Set;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;

public final class AllowedTenantValidator
        implements OAuth2TokenValidator<Jwt> {

    private final Set<String> allowedTenants;

    public AllowedTenantValidator(Set<String> allowedTenants) {
        this.allowedTenants = Set.copyOf(allowedTenants);
    }

    @Override
    public OAuth2TokenValidatorResult validate(Jwt jwt) {
        String tenant = jwt.getClaimAsString("tenant_id");

        if (tenant != null && allowedTenants.contains(tenant)) {
            return OAuth2TokenValidatorResult.success();
        }

        return OAuth2TokenValidatorResult.failure(
            new OAuth2Error(
                "invalid_token",
                "Token tenant is not accepted",
                null
            )
        );
    }
}
```

Việc cho phép một tenant **ở cấp token** có thể hữu ích khi API chỉ phục vụ nhóm tenant cố định. Nhưng quyền xem từng record vẫn là bài toán nghiệp vụ: token của `tenant-a` không tự có quyền với mọi record trong `tenant-a` nếu chính sách owner/role còn giới hạn.

Nếu một API thực sự hỗ trợ tất cả tenant thuộc issuer, có thể không cần một allowlist tenant tĩnh; khi đó hãy kiểm tra sự nhất quán tenant/subject và kiểm soát truy cập ở tầng nghiệp vụ thay vì nhét mọi policy vào validator JWT.

### 7.2. Validator tuổi token

Giả sử hợp đồng yêu cầu `iat` tồn tại, thời điểm phát hành không được vượt quá thời gian hiện tại quá giới hạn clock skew, và tuổi token không quá 15 phút.

```java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;

public final class TokenAgeValidator implements OAuth2TokenValidator<Jwt> {

    private final Clock clock;
    private final Duration maxAge;
    private final Duration allowedClockSkew;

    public TokenAgeValidator(
            Clock clock,
            Duration maxAge,
            Duration allowedClockSkew) {
        this.clock = clock;
        this.maxAge = maxAge;
        this.allowedClockSkew = allowedClockSkew;
    }

    @Override
    public OAuth2TokenValidatorResult validate(Jwt jwt) {
        Instant issuedAt = jwt.getIssuedAt();
        Instant now = Instant.now(clock);

        if (issuedAt == null) {
            return invalid("Required iat claim is missing");
        }
        if (issuedAt.isAfter(now.plus(allowedClockSkew))) {
            return invalid("iat is unexpectedly in the future");
        }
        if (issuedAt.isBefore(now.minus(maxAge).minus(allowedClockSkew))) {
            return invalid("Token age exceeds policy");
        }
        return OAuth2TokenValidatorResult.success();
    }

    private static OAuth2TokenValidatorResult invalid(String description) {
        return OAuth2TokenValidatorResult.failure(
            new OAuth2Error("invalid_token", description, null)
        );
    }
}
```

Ở đây `Clock` được truyền vào để dễ kiểm soát thời gian trong unit test. `maxAge` và `allowedClockSkew` phải được chọn có chủ đích. `JwtTimestampValidator` vẫn chịu trách nhiệm kiểm tra `exp`/`nbf` theo quy tắc mặc định; validator ở trên bổ sung **điều kiện về `iat` và tuổi token**, không thay thế timestamp validator.

Lưu ý hai ý khác nhau:

- **Tuổi token hiện tại:** `now - iat`; một token được phát hành lâu nhưng `exp` chưa hết vẫn có thể bị từ chối theo policy max age.
- **Thời lượng phát hành:** `exp - iat`; policy này giới hạn khoảng thời gian mà IdP đã gán cho token, không hoàn toàn đồng nghĩa tuổi hiện tại.

Nếu hợp đồng cần cả hai, phải kiểm tra cả hai bằng điều kiện rõ ràng. Không nhầm `iat` với lần đăng nhập tương tác gần nhất của người dùng; OAuth refresh/token exchange có thể cấp token mới mà không có đăng nhập mới.

### 7.3. Tổ hợp ba validator mới với mặc định

```java
import java.time.Clock;
import java.time.Duration;
import java.util.Set;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;

OAuth2TokenValidator<Jwt> defaults =
    JwtValidators.createDefaultWithIssuer(trustedIssuer);

OAuth2TokenValidator<Jwt> combined =
    new DelegatingOAuth2TokenValidator<>(
        defaults,
        new RequiredAudienceValidator("orders-api"),
        new AllowedTenantValidator(Set.of("tenant-a", "tenant-b")),
        new TokenAgeValidator(
            Clock.systemUTC(),
            Duration.ofMinutes(15),
            Duration.ofSeconds(30)
        )
    );

decoder.setJwtValidator(combined);
```

Tổng thể: **mỗi điều kiện thêm vào làm phạm vi token được chấp nhận hẹp hơn**, thay vì làm mất các điều kiện cũ. Nếu tổ hợp cho kết quả lỗi, decoder từ chối token theo đường xác thực JWT.

Đừng dùng nhiều token validator để mô phỏng logic quyền trên database: khi một đơn hàng được chuyển chủ sở hữu, sự kiện đó không tự đổi claim trong JWT. Cần kiểm tra policy ở tầng tài nguyên.

## 8. Khi cần thay đổi clock skew, vẫn phải giữ issuer và các ràng buộc khác

Spring Security có `JwtTimestampValidator`, cho phép cấu hình độ lệch đồng hồ phù hợp với hệ thống. Ví dụ:

```java
import java.time.Duration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtIssuerValidator;
import org.springframework.security.oauth2.jwt.JwtTimestampValidator;

JwtTimestampValidator timestamp =
    new JwtTimestampValidator(Duration.ofSeconds(30));

JwtIssuerValidator issuer =
    new JwtIssuerValidator(trustedIssuer);

OAuth2TokenValidator<Jwt> audience =
    new RequiredAudienceValidator("orders-api");

decoder.setJwtValidator(
    new DelegatingOAuth2TokenValidator<>(
        timestamp,
        issuer,
        audience
    )
);
```

**Đây là mẫu cấu hình kiểm tra thời gian/issuer/audience tường minh khi có lý do phải điều khiển timestamp validator.** Nó cần xem xét thêm các validator mặc định khác của phiên bản Spring Security hiện tại (đặc biệt các ràng buộc JWT type/profile) trước khi dùng làm thay thế production.

Vì `setJwtValidator` thay toàn bộ tổ hợp, tự viết lại chỉ gồm `timestamp + issuer + audience` có thể bỏ một số validator khác nếu version/framework đang cung cấp nhiều hơn. **Khi chỉ muốn thêm audience hoặc tenant, ưu tiên `createDefaultWithIssuer` + extra validator.** Khi phải thay đổi chính cách kiểm tra timestamp, cần tái dựng **đầy đủ** tập policy theo phiên bản và hợp đồng, không chỉ copy một ví dụ cũ.

### 8.1. Clock skew có giới hạn bảo mật

Một Resource Server có đồng hồ lệch vài giây với IdP có thể từ chối token vừa phát hành hoặc chưa tới `nbf`. Cho phép chênh lệch nhỏ là thực tế. Tuy nhiên:

- Skew lớn làm mở rộng khoảng thời gian JWT được chấp nhận quanh mốc `exp` và `nbf`.
- Không dùng skew lớn để che lỗi đồng bộ thời gian hệ thống.
- Chính sách nên được thống nhất giữa các API có cùng hợp đồng.
- Đồng bộ giờ máy chủ (NTP) và quan sát độ lệch thực tế quan trọng hơn việc nới validator tùy tiện.

## 9. Không chỉ thêm claim: còn phải giữ loại token và profile đúng

Một Authorization Server có thể cấp:

- **Access token** cho Resource Server.
- **OIDC ID token** cho OIDC client.
- Những JWT khác cho logout, authorization response hoặc giao thức nội bộ.

Một số token có cùng `iss` và chữ ký xác minh bằng cùng tập key, nhưng **mục đích và audience khác nhau**. Vì thế API phải phân biệt token profile/loại token theo hợp đồng, không chấp nhận một JWT chỉ vì chữ ký đúng.

Ví dụ:

```text
OIDC ID token:
  aud = shop-web
  mục đích = client xử lý kết quả đăng nhập

OAuth access token:
  aud = orders-api
  mục đích = Orders API bảo vệ tài nguyên
```

Ngay cả khi dùng `JwtValidators.createDefaultWithIssuer`, bạn vẫn cần đối chiếu các yêu cầu token type, `aud` và profile access token đang được chấp nhận. Các kiểm tra mặc định liên quan `typ` có thể thay đổi theo version/đường dựng decoder; không thay chúng bằng một kiểm tra tự viết quá rộng.

### 9.1. Header typ không tự chứng minh token là access token

Ví dụ JWS header:

```json
{
  "alg": "RS256",
  "typ": "at+jwt",
  "kid": "issuer-key-1"
}
```

`typ` là tín hiệu về loại JWT, nhưng header này do bên gửi token cung cấp và chỉ trở thành phần dữ liệu đáng tin trong bối cảnh **chữ ký JWS và token profile được xác minh đúng**. Không dùng một điều kiện string như `typ == "at+jwt"` để thay thế issuer, audience, thời gian và signature verification.

Nếu áp dụng RFC 9068 JWT access token profile, Resource Server cần kiểm tra đúng những claim và token type mà profile yêu cầu, với API/validator phù hợp phiên bản. Hợp đồng mạnh hơn không có nghĩa phá bỏ các kiểm tra nền tảng.

### 9.2. JWE hoặc opaque token không đi qua cùng JWT validator theo mặc định

`OAuth2TokenValidator<Jwt>` phù hợp khi Resource Server có `Jwt` đã được decoder xử lý theo hợp đồng. Nếu access token được kiểm tra qua **opaque-token introspection**, Spring Security sử dụng `OpaqueTokenIntrospector` và principal/authorities khác; `JwtDecoder#setJwtValidator` không tự được áp vào opaque chain.

Với **JWE/nested JWT**, ứng dụng cần một processor có thể giải mã/kiểm chứng đúng định dạng rồi trả `Jwt` đáng tin, hoặc dùng introspection phù hợp. Không dùng `JwtValidators` để che việc chưa xác minh chữ ký JWS bên trong hay chưa có hợp đồng decryption/issuer authentication.

## 10. Khi có nhiều issuer: giữ validator theo từng issuer

Một số API nhận access token từ nhiều IdP/realm tin cậy. Sai lầm thường gặp là tạo một decoder chung cho mọi issuer rồi chỉ thêm audience:

```text
Token A: iss = https://idp-a.example.com
Token B: iss = https://idp-b.example.com
```

Nếu API thật sự tin cả A và B, mỗi issuer có thể có:

- JWKS URI hoặc key set riêng.
- Tập thuật toán ký được phép riêng.
- Claim mapping, scope format và chính sách tenant riêng.
- Validator issuer và profile riêng.

Không chọn bất kỳ issuer nào theo `iss` chưa xác thực rồi tự động tải khóa từ URL đó. Cần một **danh sách issuer được tin cậy**, một resolver/decoder được thiết kế cho đa issuer và các validator tương ứng.

Mô hình khái niệm:

```mermaid
flowchart TD
    A["Bearer JWT"] --> B{"iss có nằm trong<br/>trusted-issuer allowlist?"}
    B -->|"Không"| X["Từ chối"]
    B -->|"Có"| C["Chọn decoder/keys tin cậy<br/>đã cấu hình cho issuer"]
    C --> D["Xác minh chữ ký"]
    D --> E["Default validators<br/>của issuer đó"]
    E --> F["Audience, tenant, profile<br/>của API"]
    F --> G["Authorization"]
```

Trong kiến trúc này, “giữ validator mặc định” nghĩa là **mỗi nhánh issuer vẫn phải kiểm tra issuer và thời gian**, không được vì phải hỗ trợ nhiều IdP mà bỏ issuer validator hoàn toàn.

### 10.1. Dùng audience giống nhau chưa đủ làm hai issuer tương đương

Token từ issuer không tin cậy có thể tự khai báo `aud=orders-api`. Vì thế audience là điều kiện **bổ sung sau ranh giới issuer**, không phải thay cho issuer.

Tương tự, một claim `sub=user-42` từ hai issuer khác nhau không bảo đảm là cùng một người dùng. Khi ánh xạ vào tài khoản nội bộ, cần xét cặp issuer/subject hoặc cơ chế identity linking rõ ràng.

## 11. Khi có custom Authentication converter, validator còn cần không?

`JwtAuthenticationConverter` hoặc custom authority converter dùng để biến JWT đã xác thực thành `Authentication` và `GrantedAuthority`. Ví dụ:

```text
JWT scope = orders.read
      |
      v
JwtGrantedAuthoritiesConverter
      |
      v
GrantedAuthority = SCOPE_orders.read
```

Converter và validator làm hai việc khác nhau:

| Thành phần | Trách nhiệm |
|---|---|
| `JwtDecoder` | Xác minh chữ ký/chuẩn JOSE và tạo `Jwt` |
| `OAuth2TokenValidator<Jwt>` | Kiểm tra hợp đồng claim để quyết định có nhận token hay không |
| `JwtAuthenticationConverter` | Chuyển JWT đã nhận thành Authentication/principal/authorities |
| HTTP/method authorization | Kiểm tra authorities và rule endpoint |
| Business service | Quyết định quyền với tài nguyên cụ thể |

Nếu custom converter đổi tên principal từ `sub` sang `preferred_username`, điều đó không tự động kiểm tra rằng claim ấy luôn hiện diện, thuộc issuer đúng hoặc phù hợp hợp đồng. Nếu custom validator bổ sung tenant, converter cũng không tự biến tenant thành quyền truy cập từng object.

### 11.1. Không dùng converter làm chỗ từ chối token sai hợp đồng

Một converter có thể ánh xạ authority, nhưng những ràng buộc **token được chấp nhận hay không** nên nằm ở decoder/validator tương ứng khi có thể. Nếu một claim không hợp lệ khiến token phải bị từ chối ngay, nên thể hiện bằng `OAuth2TokenValidatorResult.failure` thay vì âm thầm tạo Authentication thiếu authority rồi hy vọng mọi endpoint đều chặn.

## 12. Cách xử lý lỗi: invalid_token và HTTP response

Khi custom claim validator trả lỗi, ví dụ:

```java
return OAuth2TokenValidatorResult.failure(
    new OAuth2Error(
        "invalid_token",
        "Required audience is missing",
        null
    )
);
```

`JwtDecoder` từ chối JWT theo luồng authentication. Ở một API bearer thông thường, token không hợp lệ dẫn đến **HTTP 401 Unauthorized** với challenge Bearer do các thành phần Spring Security xử lý.

Ngược lại, token xác thực thành công nhưng không đủ scope cho endpoint có thể bị **HTTP 403 Forbidden**:

```text
JWT hợp lệ:
  iss = trustedIssuer
  aud = orders-api
  exp còn hạn
  scope = orders.read

Request:
  POST /api/orders

Policy:
  POST cần SCOPE_orders.write

=> Authentication thành công, authorization từ chối.
```

Đừng đẩy các quyền nghiệp vụ vào issuer/audience validator một cách vô tội vạ để mọi quyền thiếu đều trở thành `invalid_token`. Việc phân biệt **token không đúng hợp đồng** với **token đúng nhưng không đủ quyền thao tác** giúp API và client xử lý 401/403 rõ ràng.

Thông điệp lỗi JWT validator nên đủ ý nghĩa để vận hành, nhưng không cần chứa raw token, khóa bí mật, đầy đủ claims cá nhân hoặc thông tin xác minh quá chi tiết trả cho client.

## 13. Kiểm thử validators theo từng điều kiện

Để chứng minh một tổ hợp đúng yêu cầu, cần tách **unit test của validator** và **integration test của toàn bộ JWT decoder/filter chain**.

### 13.1. Unit test: validate một Jwt đã được tạo

Ví dụ giả lập `Jwt` làm đầu vào trực tiếp cho bộ validators:

```java
import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;

import static org.assertj.core.api.Assertions.assertThat;

class JwtClaimsValidatorTest {

    private final String issuer =
        "https://idp.example.com/realms/shop";

    private final OAuth2TokenValidator<Jwt> validators =
        new DelegatingOAuth2TokenValidator<>(
            JwtValidators.createDefaultWithIssuer(issuer),
            new RequiredAudienceValidator("orders-api")
        );

    private Jwt token(
            String actualIssuer,
            List<String> audiences,
            Instant expiresAt) {
        Instant now = Instant.now();
        return Jwt.withTokenValue("test-token")
            .header("alg", "RS256")
            .claim("iss", actualIssuer)
            .claim("sub", "user-842")
            .audience(audiences)
            .issuedAt(now.minusSeconds(60))
            .notBefore(now.minusSeconds(60))
            .expiresAt(expiresAt)
            .build();
    }

    @Test
    void acceptsCorrectIssuerAudienceAndTime() {
        Jwt jwt = token(
            issuer,
            List.of("orders-api"),
            Instant.now().plusSeconds(300));

        assertThat(validators.validate(jwt).hasErrors()).isFalse();
    }

    @Test
    void rejectsWrongAudience() {
        Jwt jwt = token(
            issuer,
            List.of("payments-api"),
            Instant.now().plusSeconds(300));

        assertThat(validators.validate(jwt).hasErrors()).isTrue();
    }

    @Test
    void rejectsExpiredToken() {
        Jwt jwt = token(
            issuer,
            List.of("orders-api"),
            Instant.now().minusSeconds(600));

        assertThat(validators.validate(jwt).hasErrors()).isTrue();
    }

    @Test
    void rejectsWrongIssuer() {
        Jwt jwt = token(
            "https://other-idp.example.com",
            List.of("orders-api"),
            Instant.now().plusSeconds(300));

        assertThat(validators.validate(jwt).hasErrors()).isTrue();
    }
}
```

Các test trên chỉ chứng minh **validator trên đối tượng Jwt** hoạt động theo những điều kiện kiểm tra. Token string `test-token` không có chữ ký thật. Đây **không phải** bài test mật mã, JWKS discovery, HTTP Bearer parsing hoặc toàn bộ Resource Server.

Lưu ý khi test thời gian: `JwtTimestampValidator` có thể cho phép một clock skew mặc định; để kiểm tra hết hạn chắc chắn, test dùng mốc quá khứ đủ xa thay vì token chỉ quá hạn một vài mili giây. Với validator dùng `Clock` tự tiêm, có thể dùng `Clock.fixed(...)` để test ranh giới thời gian ổn định.

### 13.2. Integration test: JWT thực sự đi qua decoder

Ở mức tích hợp cần kiểm tra:

- Token ký bằng private key tương ứng public key tin cậy được chấp nhận.
- Chữ ký sai hoặc thuật toán không được phép bị từ chối.
- `iss` sai bị từ chối.
- `aud` sai bị từ chối dù chữ ký đúng.
- `exp` hết hạn hoặc `nbf` tương lai bị từ chối.
- Token hợp lệ nhưng thiếu `SCOPE_orders.read` nhận phản hồi phân quyền tương ứng.
- Route public và route protected dùng đúng `SecurityFilterChain`.

Có thể sử dụng một signing key test, decoder trỏ đến JWKS test hoặc một test double có ranh giới rõ. Đừng đưa private key test hay token thực vào tài liệu/log production.

`SecurityMockMvcRequestPostProcessors.jwt()` rất hữu ích để kiểm tra HTTP authorization bằng `JwtAuthenticationToken` giả lập, nhưng có thể **không chạy qua việc xác minh chữ ký và claim thật của `JwtDecoder`**. Vì vậy, chỉ dùng `mockMvc.perform(...).with(jwt())` chưa đủ chứng minh bộ validator được kết nối đúng với Resource Server.

### 13.3. Trường hợp “test mới đúng, policy cũ hỏng”

Một tình huống dễ xảy ra khi sửa code:

```text
Trước thay đổi:
  token hết hạn -> 401
  token sai issuer -> 401

Sau khi chỉ set audienceValidator:
  token đúng audience, hết hạn -> bất ngờ được chấp nhận
  token đúng audience, sai issuer -> kiểm tra issuer có thể mất
```

Đó là lỗi hồi quy của **bộ validator bị thay thế**. Cách phòng là lưu rõ tập điều kiện nền tảng và kiểm chứng rằng khi thêm claim mới, các tình huống cũ vẫn bị từ chối.

## 14. Các biến thể cấu hình và giới hạn cần nhớ

### 14.1. Decoder tạo trực tiếp từ issuer

```java
NimbusJwtDecoder decoder =
    NimbusJwtDecoder.withIssuerLocation(trustedIssuer).build();

decoder.setJwtValidator(
    new DelegatingOAuth2TokenValidator<>(
        JwtValidators.createDefaultWithIssuer(trustedIssuer),
        new RequiredAudienceValidator("orders-api")
    )
);
```

Đây là mẫu điển hình khi API quản lý decoder và một issuer tin cậy.

### 14.2. Decoder tạo từ JWKS URI cố định

```java
NimbusJwtDecoder decoder =
    NimbusJwtDecoder.withJwkSetUri(trustedJwkSetUri).build();

decoder.setJwtValidator(
    new DelegatingOAuth2TokenValidator<>(
        JwtValidators.createDefaultWithIssuer(trustedIssuer),
        new RequiredAudienceValidator("orders-api")
    )
);
```

Ở đây cả `trustedJwkSetUri` và `trustedIssuer` được ứng dụng quản lý. Không coi JWKS URL lấy từ token là nguồn tin cậy. Khi dùng JWKS URI trực tiếp, việc thêm issuer validator tường minh là quan trọng.

### 14.3. Chỉ dùng createDefault khi không có issuer?

```java
OAuth2TokenValidator<Jwt> defaults =
    JwtValidators.createDefault();
```

Helper này có thể hữu ích trong một hợp đồng JWT không yêu cầu issuer theo cùng cách, hoặc khi issuer được kiểm chứng ở một thành phần khác đã được cấu hình đúng. Nhưng **đối với OAuth 2.0 Resource Server tin một Authorization Server xác định**, bỏ kiểm tra `iss` chỉ để code ngắn hơn thường làm giảm ranh giới tin cậy.

Không sử dụng `createDefault()` thay `createDefaultWithIssuer(...)` trong API có issuer cố định rồi giả định hai bộ có cùng chính sách.

### 14.4. DSL thay decoder tại chain

```java
.oauth2ResourceServer(oauth2 -> oauth2
    .jwt(jwt -> jwt.decoder(customDecoder)))
```

Khi chọn một decoder cụ thể ngay trên DSL, các cấu hình mặc định trong context/property có thể không còn là nơi quyết định validator của chain đó. Nếu ứng dụng có nhiều chain, mỗi chain phải được xét độc lập:

```text
/api/orders/**   -> JwtDecoder A -> issuer A + audience orders-api
/api/payments/** -> JwtDecoder B -> issuer B + audience payments-api
```

Đừng giả định mọi chain dùng chung decoder hoặc validator chỉ vì ứng dụng có một cấu hình `issuer-uri` trong YAML.

### 14.5. Không dùng custom validator để làm mềm các kiểm tra mặc định

Một validator mới có mục đích “cho phép khi audience match” không thể sửa lỗi issuer sai. Không nên viết:

```text
if (aud == "orders-api") ACCEPT
else RUN_DEFAULT_VALIDATORS
```

Đây là logic **OR** nguy hiểm: chỉ cần audience đúng là bỏ qua các ràng buộc khác. Tổ hợp cần là **AND**, trừ khi một hợp đồng bảo mật được thiết kế rõ ràng có các nhánh loại token riêng, mỗi nhánh vẫn tự kiểm chứng đầy đủ.

## 15. Trường hợp thực tế và quyết định đúng

### Tình huống A — Bổ sung audience cho API

Ban đầu:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.com/realms/shop
```

Yêu cầu mới: `aud` phải chứa `orders-api`.

**Hướng đơn giản:** sử dụng property `spring.security.oauth2.resourceserver.jwt.audiences` nếu version Boot hỗ trợ và không có decoder custom thay thế. **Hướng custom:** dùng `createDefaultWithIssuer` + audience validator qua `DelegatingOAuth2TokenValidator`. Không gọi `setJwtValidator(audienceOnly)`.

### Tình huống B — Bổ sung tenant_id

Yêu cầu mới: access token phải có `tenant_id` thuộc tập tenant do API quản lý. Tạo validator tenant rồi **hợp thành** với issuer/time/audience. Đồng thời kiểm tra tenant trong database ở tầng nghiệp vụ; validator token không tự giải quyết mọi trường hợp truy cập chéo tenant.

### Tình huống C — Token có exp còn hạn nhưng iat quá cũ

Ứng dụng thêm max-age validator theo `iat` và `Clock`. Giữ `JwtTimestampValidator` để tiếp tục kiểm tra `exp`/`nbf`. Nếu `iat` thiếu mà profile yêu cầu có, từ chối. Không lấy `iat` làm thay thế cho `exp`.

### Tình huống D — Chỉ định jwk-set-uri vì không muốn discovery lúc startup

API dùng một JWKS URI đã được cấu hình. Có thể vẫn giữ issuer validator bằng `JwtValidators.createDefaultWithIssuer`. Cách lấy khóa và cách kiểm tra issuer là hai mục đích khác nhau. Không loại issuer chỉ vì đã chỉ định nguồn khóa chính xác.

### Tình huống E — Resource Server chấp nhận nhiều IdP

Không dùng một validator `audience == orders-api` làm điều kiện tin cậy chung. Chọn decoder theo **allowlist issuer đáng tin**, giữ issuer/time/profile validators của từng decoder, rồi áp audience của API.

### Tình huống F — Thay JwtDecoder để thử JWE hoặc format đặc thù

Nếu thay decoder hoàn toàn, tất cả điều kiện về chữ ký/giải mã, issuer, audience, thời gian và loại token phải được kiểm chứng theo hợp đồng. `JwtValidators.createDefaultWithIssuer` là thành phần kiểm tra claim hữu ích, **không thay thế** một JWE/JWS processor mật mã đáng tin.

## 16. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách làm đúng |
|---|---|---|
| `setJwtValidator(new AudienceValidator(...))` rồi tin default vẫn chạy | Có thể mất issuer/timestamp validators | Hợp thành default + audience |
| Có `@Bean JwtDecoder` nhưng vẫn tin Boot tự gắn `audiences` vào mọi decoder | Cấu hình claim có thể bị bỏ qua | Gắn validators rõ trong decoder custom |
| Chỉ cấu hình `jwk-set-uri` rồi nghĩ issuer đã được xác minh | Mất ranh giới nhà phát hành nếu không kiểm tra `iss` | Thêm issuer validator đúng hợp đồng |
| Nhận ID token vì chữ ký/issuer đúng | Token substitution giữa OIDC client và API | Kiểm tra audience, loại token, token profile |
| So audience bằng chuỗi con | Nhận nhầm resource audience | So giá trị audience chính xác |
| Dùng `scope` thay audience | Token dành cho API khác có thể bị dùng sai | Kiểm tra `aud` riêng với scope |
| Xem `sub` là quyền sở hữu mọi bản ghi | Rò rỉ dữ liệu giữa người dùng/tenant | Kiểm tra owner/tenant ở business service |
| Bỏ `exp` vì đã có validator tuổi `iat` | Có thể nhận token hết hạn | Giữ timestamp validator |
| Bỏ `nbf` khi sửa clock skew | Nhận token chưa tới hiệu lực | Duy trì kiểm tra not-before |
| Chỉ dùng `isAuthenticated` trong service | Anonymous có thể bị hiểu nhầm | Dùng authorization/trust resolver |
| Thay validator type/profile bằng kiểm tra `typ` tự viết sơ sài | Cross-token confusion | Giữ profile validators theo version/hợp đồng |
| Tự cấu hình issuer từ `iss` chưa xác thực | Trust JWKS của attacker | Trusted issuer allowlist từ cấu hình |
| Dùng `@WithMockUser` và nghĩ đã test JWT decoder | Bỏ qua signature/claims validation | Phân biệt validator unit test và decoder integration test |
| Log raw JWT khi validator trả lỗi | Có thể lộ bearer credential | Log metadata/lý do chung, không log token |

## 17. Quy trình thiết kế khi thêm yêu cầu kiểm tra claim

Một thay đổi như “kiểm tra thêm audience” nên được triển khai theo thứ tự tư duy sau:

1. **Đọc hợp đồng hiện tại:** issuer, token profile, thuật toán, JWKS, thời gian, audience và các yêu cầu mặc định đang có.
2. **Xác định yêu cầu mới:** kiểm tra claim nào, điều kiện pass/fail nào, claim có bắt buộc hiện diện không?
3. **Xem cấu hình framework có hỗ trợ trực tiếp không:** ví dụ `spring.security.oauth2.resourceserver.jwt.audiences` trong Boot.
4. **Nếu custom decoder:** giữ bộ validator nền tảng bằng `JwtValidators.createDefaultWithIssuer(trustedIssuer)` khi phù hợp.
5. **Hợp thành thay vì thay thế:** dùng `DelegatingOAuth2TokenValidator<>(defaults, custom1, custom2, ...)`.
6. **Giữ signature verification đúng:** decoder/JWKS/algorithm phải được cấu hình từ nguồn tin cậy, không lấy từ payload chưa xác thực.
7. **Tách quyền nghiệp vụ:** claim validation từ chối token sai hợp đồng; HTTP/method/domain authorization xử lý thiếu quyền.
8. **Xác định các tình huống âm:** hết hạn, chưa hiệu lực, sai issuer, sai audience, thiếu claim mới, sai token profile, thiếu scope.
9. **Quan sát không làm lộ credential:** log hợp lý, không đưa JWT raw/secret vào lỗi.
10. **Đối chiếu phiên bản:** kiểm tra default validators, builder và khả năng auto-configuration trên Spring Security/Boot của project.

### 17.1. Sơ đồ quyết định

```mermaid
flowchart TD
    A["Cần kiểm tra claim mới"] --> B{"Boot hỗ trợ property trực tiếp<br/>và decoder vẫn auto-config?"}
    B -->|"Có"| C["Cấu hình property tương ứng"]
    B -->|"Không"| D["Cung cấp hoặc cấu hình JwtDecoder"]
    D --> E["Lấy default validators<br/>với trusted issuer"]
    E --> F["Viết custom validator theo hợp đồng"]
    F --> G["DelegatingOAuth2TokenValidator<br/>(defaults AND customs)"]
    G --> H["setJwtValidator(combined)"]
    C --> I["JWT authentication + HTTP authorization"]
    H --> I
    I --> J["Business authorization<br/>owner / tenant / object"]
```

Nếu buộc phải **thay đổi bản thân một validator mặc định** (chẳng hạn kiểm tra timestamp với skew khác), cần hiểu rõ **mọi validator mặc định còn lại** của phiên bản cụ thể để không xóa các bảo đảm khác khi dựng tổ hợp mới. Đây là ngoại lệ cần thiết kế có chủ đích; không phải cách mặc định cho mọi yêu cầu bổ sung.

## 18. Tổng kết

```text
JWT từ HTTP request
    |
    v
Verify signature + trusted keys + allowed algorithms
    |
    v
Default claim validators (issuer, time, profile theo version)
    |
    AND
    |
    v
Custom claim validators (audience, tenant, max age...)
    |
    v
JwtAuthenticationToken
    |
    v
Scope/authority checks
    |
    v
Business permissions for the requested resource
```

**Điểm cần nhớ nhất: `NimbusJwtDecoder#setJwtValidator(...)` thiết lập bộ validator được sử dụng; nó không phải lời gọi “thêm một validator vào cuối danh sách mặc định”.** Khi muốn mở rộng hợp đồng access token, hãy giữ các validator nền tảng bằng helper phù hợp như `JwtValidators.createDefaultWithIssuer(...)` rồi hợp thành với `DelegatingOAuth2TokenValidator`.

Điều kiện mới chỉ tăng bảo mật khi **mọi điều kiện cũ vẫn được giữ**. Kiểm tra audience không được đánh đổi kiểm tra issuer; kiểm tra tenant không được đánh đổi kiểm tra thời hạn; kiểm tra token type không được đánh đổi kiểm tra chữ ký; và mọi claim đã xác thực vẫn không thể thay thế phân quyền trên từng tài nguyên.

## Tài liệu tham khảo

- [Spring Security Reference — JWT Resource Server (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): cấu hình decoder và validators.
- [Spring Security Reference — OAuth 2.0 Resource Server (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html): luồng xác thực bearer token.
- [Spring Security API — JwtValidators](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/jwt/JwtValidators.html): `createDefault`, `createDefaultWithIssuer`.
- [Spring Security API — NimbusJwtDecoder](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/jwt/NimbusJwtDecoder.html): `setJwtValidator` và decoder builder.
- [Spring Security API — DelegatingOAuth2TokenValidator](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/core/DelegatingOAuth2TokenValidator.html): tổ hợp các token validators.
- [Spring Security API — JwtTimestampValidator](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/jwt/JwtTimestampValidator.html): kiểm tra thời hạn và độ lệch đồng hồ.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): ý nghĩa claims chuẩn.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): issuer, audience, thuật toán và phân biệt loại JWT.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): profile và các yêu cầu của OAuth JWT access token.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): nhận bearer credential và cách trả lỗi.
