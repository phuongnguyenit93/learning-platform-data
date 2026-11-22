# Kiểm thử JwtAuthenticationConverter và validator riêng theo hợp đồng

Trong Spring Security Servlet Resource Server, xử lý JWT có hai nhiệm vụ khác nhau:

1. **Xác minh token có được chấp nhận hay không**: chữ ký, thuật toán, issuer, thời hạn, audience và những điều kiện theo hợp đồng với Authorization Server.
2. **Chuyển JWT đã được xác minh thành Authentication**: ánh xạ scope/role thành GrantedAuthority, chọn principal name và tạo kiểu Authentication mà ứng dụng cần.

Spring Security tách hai nhiệm vụ này thành hai thành phần chính:

- `JwtDecoder` giải mã, xác minh chữ ký và chạy `OAuth2TokenValidator<Jwt>`.
- `JwtAuthenticationConverter` chuyển `Jwt` đã được decoder chấp nhận thành `AbstractAuthenticationToken`; converter này thường dùng một converter con để tạo danh sách `GrantedAuthority`.

Vì vậy, kiểm thử converter không chứng minh validator đúng; kiểm thử validator cũng không chứng minh scope/role được ánh xạ đúng. Bài này xây dựng một hợp đồng token cụ thể, viết converter và validator riêng, rồi kiểm thử chúng ở cấp unit, MockMvc và integration qua filter chain.

> **Bất biến:** Chỉ JWT đã qua chữ ký và toàn bộ validator mới được chuyển thành Authentication. Converter không được dùng để bù cho issuer/audience/token-profile validation bị thiếu. Ngược lại, validator không nên cố ánh xạ quyền nghiệp vụ; nó chỉ quyết định token có đáp ứng hợp đồng xác thực hay không.

## 1. Xác định hợp đồng JWT trước khi viết test

Giả sử Orders API nhận access token JWT từ một Authorization Server. Hợp đồng của API quy định:

| Claim/header | Ví dụ | Quy tắc |
| --- | --- | --- |
| JOSE `alg` | `RS256` | Chỉ chấp nhận thuật toán chữ ký được cấu hình |
| `iss` | `https://identity.example.test/realms/shop` | Phải khớp issuer tin cậy |
| `aud` | `["orders-api"]` | Phải chứa audience của Orders API |
| `exp` | Unix timestamp | Token chưa hết hạn |
| `nbf` | Unix timestamp | Token đã đến thời điểm có hiệu lực |
| `sub` | `alice-42` | Bắt buộc, không rỗng |
| `scope` | `orders.read orders.cancel` | Chuỗi scope cách nhau bằng khoảng trắng |
| `roles` | `["ORDER_ADMIN"]` | Claim role nội bộ theo hợp đồng riêng |
| `token_use` | `access` | Chỉ access token mới được chấp nhận |
| `tenant_id` | `tenant-A` | Bắt buộc nếu API yêu cầu một tenant context |

Ví dụ JWT payload minh họa:

~~~json
{
  "iss": "https://identity.example.test/realms/shop",
  "sub": "alice-42",
  "aud": ["orders-api"],
  "iat": 1893456000,
  "nbf": 1893456000,
  "exp": 1893459600,
  "scope": "orders.read orders.cancel",
  "roles": ["ORDER_ADMIN"],
  "token_use": "access",
  "tenant_id": "tenant-A"
}
~~~

Các tên claim ở trên là **hợp đồng ví dụ**, không phải tất cả đều là claim bắt buộc của OAuth 2.0/OIDC. Đặc biệt `roles`, `token_use` và `tenant_id` là quy ước do Authorization Server và Resource Server thống nhất. Test phải phản ánh đúng profile token đang dùng; không tự giả định mọi issuer đều phát cùng cấu trúc.

### 1.1. Ba converter khác nhau trong pipeline

Trong Spring Security, từ “converter” có thể chỉ nhiều bước:

| Thành phần | Đầu vào → đầu ra | Vai trò | Nơi kiểm thử |
| --- | --- | --- | --- |
| `MappedJwtClaimSetConverter` | Claim map → claim map đã chuẩn hóa | Chuyển kiểu/điều chỉnh claims khi decoder dựng Jwt | Unit/decoder test nếu có custom mapping |
| `JwtGrantedAuthoritiesConverter` hoặc converter authority riêng | `Jwt` → `Collection<GrantedAuthority>` | Đọc scope/role và tạo authorities | Unit test mapping |
| `JwtAuthenticationConverter` | `Jwt` → `AbstractAuthenticationToken` | Tạo Authentication, principal và authorities | Unit test converter + filter-chain test |

`JwtDecoder` còn có bước validation trước khi converter Authentication được gọi:

~~~mermaid
flowchart TD
    A["Authorization: Bearer <token>"]
    B["BearerTokenAuthenticationFilter"]
    C["JwtAuthenticationProvider"]
    D["JwtDecoder"]
    E["Verify JWS signature / trusted algorithm"]
    F["OAuth2TokenValidator<Jwt>"]
    G{"All validators succeed?"}
    H["JwtAuthenticationConverter"]
    I["Jwt -> authorities converter"]
    J["JwtAuthenticationToken / custom Authentication"]
    K["SecurityContextHolder"]
    X["Authentication failure / 401"]

    A --> B --> C --> D --> E --> F --> G
    G -->|No| X
    G -->|Yes| H --> I --> J --> K
~~~

Nếu validator thất bại, converter Authentication không nên được chạy. Đây là một assertion quan trọng trong integration test: **token sai audience phải bị chặn trước khi code mapping quyền được thực thi**.

### 1.2. Phân biệt validation và authorization

| Kiểm tra | Lớp phù hợp |
| --- | --- |
| Chữ ký, issuer, thời hạn, audience, token type | JwtDecoder / OAuth2TokenValidator |
| Claim bắt buộc theo token contract | OAuth2TokenValidator |
| `scope` thành `SCOPE_orders.read` | Granted-authorities converter |
| `roles` thành `ROLE_ORDER_ADMIN` | Granted-authorities converter |
| Chọn principal name | JwtAuthenticationConverter / principal converter |
| Endpoint yêu cầu `SCOPE_orders.read` | HttpSecurity authorization |
| User thuộc tenant và sở hữu order | Business/resource authorization |

Không dùng converter để chấp nhận token sai issuer chỉ vì nó có role cần thiết. Không dùng validator để quyết định Alice có được đọc Order 42 hay không; đó là quyền trên resource.

## 2. Tạo bộ converter theo hợp đồng

### 2.1. Ánh xạ scope và role riêng biệt

Giả sử Authorization Server phát `scope` theo OAuth2 và `roles` theo domain contract. Ta muốn:

~~~text
scope = "orders.read orders.cancel"
    -> SCOPE_orders.read
    -> SCOPE_orders.cancel

roles = ["ORDER_ADMIN", "ORDER_AUDITOR"]
    -> ROLE_ORDER_ADMIN
    -> ROLE_ORDER_AUDITOR
~~~

Không nên gộp scope và role thành một namespace chung. `SCOPE_orders.read` biểu thị delegated permission từ access token; `ROLE_ORDER_ADMIN` là role theo ứng dụng và cần được cấp/diễn giải theo hợp đồng riêng.

Spring Security cung cấp `JwtGrantedAuthoritiesConverter` để đổi scope hoặc claim authority thành `GrantedAuthority`. Khi cần đọc nhiều claim, dùng `DelegatingJwtGrantedAuthoritiesConverter`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.resource.authentication.DelegatingJwtGrantedAuthoritiesConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;
import org.springframework.core.convert.converter.Converter;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;

import java.util.Collection;

@Configuration
class JwtAuthorityConfiguration {

    @Bean
    Converter<Jwt, Collection<GrantedAuthority>> jwtAuthoritiesConverter() {
        JwtGrantedAuthoritiesConverter scopes =
                new JwtGrantedAuthoritiesConverter();
        // Mặc định đọc scope/scp và dùng prefix SCOPE_.

        JwtGrantedAuthoritiesConverter roles =
                new JwtGrantedAuthoritiesConverter();
        roles.setAuthoritiesClaimName("roles");
        roles.setAuthorityPrefix("ROLE_");

        return new DelegatingJwtGrantedAuthoritiesConverter(
                scopes, roles);
    }
}
~~~

Đoạn code này giữ prefix mặc định `SCOPE_` cho scope và chỉ thêm `ROLE_` cho claim `roles`. Nếu Authorization Server phát `roles` dạng chuỗi thay vì collection, cần điều chỉnh converter theo đúng kiểu claim; không âm thầm parse mọi kiểu dữ liệu.

### 2.2. Không đổi scope thành ROLE_ chỉ để làm test pass

`JwtGrantedAuthoritiesConverter.setAuthorityPrefix("ROLE_")` thay đổi prefix của authorities mà converter đó tạo. Nếu dùng nó cho scope, `orders.read` sẽ thành `ROLE_orders.read`; điều này làm lẫn scope với role và có thể khiến rule `hasAuthority("SCOPE_orders.read")` không còn khớp.

Giữ namespace tách biệt:

~~~java
.hasAuthority("SCOPE_orders.read")
.hasRole("ORDER_ADMIN")
~~~

`hasRole("ORDER_ADMIN")` tương đương kiểm tra authority `ROLE_ORDER_ADMIN`. Trong test, assertion nên kiểm tra đúng chuỗi authority để phát hiện thay đổi prefix ngoài ý muốn.

### 2.3. Converter Authentication hoàn chỉnh

`JwtAuthenticationConverter` nhận converter authorities và tạo `JwtAuthenticationToken`. Ví dụ:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.convert.converter.Converter;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;

import java.util.Collection;

@Configuration
class JwtAuthenticationConfiguration {

    @Bean
    JwtAuthenticationConverter jwtAuthenticationConverter(
            Converter<Jwt, Collection<GrantedAuthority>> authoritiesConverter) {

        JwtAuthenticationConverter converter =
                new JwtAuthenticationConverter();
        converter.setJwtGrantedAuthoritiesConverter(authoritiesConverter);
        converter.setPrincipalClaimName("sub");
        return converter;
    }
}
~~~

Với cấu hình này:

- `Authentication.getPrincipal()` mặc định là đối tượng `Jwt`.
- `Authentication.getName()` lấy giá trị claim được chọn làm principal name, ở đây là `sub`.
- `Authentication.getAuthorities()` chứa scope và role sau khi converter ánh xạ.

Không nhầm principal name với internal user ID trừ khi hợp đồng ứng dụng quy định rõ. Nếu cần principal domain riêng, dùng `setJwtPrincipalConverter(...)` hoặc một converter trả về `AbstractAuthenticationToken` phù hợp; đừng sửa claim `sub` để ép nó thành username nội bộ.

### 2.4. Custom Converter khi cần Authentication type riêng

Khi ứng dụng cần gắn tenant hoặc một principal wrapper, có thể triển khai `Converter<Jwt, AbstractAuthenticationToken>`:

~~~java
import java.util.Collection;
import org.springframework.core.convert.converter.Converter;
import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.security.core.GrantedAuthority;

final class ContractJwtAuthenticationConverter
        implements Converter<Jwt, AbstractAuthenticationToken> {

    private final Converter<Jwt, Collection<GrantedAuthority>> authorities;

    ContractJwtAuthenticationConverter(
            Converter<Jwt, Collection<GrantedAuthority>> authorities) {
        this.authorities = authorities;
    }

    @Override
    public AbstractAuthenticationToken convert(Jwt jwt) {
        String subject = jwt.getSubject();
        if (subject == null || subject.isBlank()) {
            // Claim này nên được kiểm tra bằng validator trước đó.
            throw new IllegalArgumentException("JWT subject is required");
        }

        String tenant = jwt.getClaimAsString("tenant_id");
        if (tenant == null || tenant.isBlank()) {
            throw new IllegalArgumentException("JWT tenant_id is required");
        }

        Collection<GrantedAuthority> mapped = authorities.convert(jwt);
        return new JwtAuthenticationToken(
                jwt, mapped, subject);
    }
}
~~~

Đây là ví dụ cho thấy converter có thể chọn principal name và authority. Trong production, các claim bắt buộc như `sub` và `tenant_id` nên được từ chối bởi validator, để mọi đường sử dụng decoder đều áp dụng cùng hợp đồng. Converter có thể giả định các invariant ấy đã được bảo đảm; nếu vẫn kiểm tra lại để bảo vệ boundary, không nên dùng exception nghiệp vụ tùy tiện rồi coi đó là validation chuẩn.

Gắn converter vào Servlet filter chain:

~~~java
@Bean
SecurityFilterChain api(HttpSecurity http,
                       Converter<Jwt, AbstractAuthenticationToken> converter)
        throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyRequest().authenticated())
        .oauth2ResourceServer(resourceServer -> resourceServer
            .jwt(jwt -> jwt.jwtAuthenticationConverter(converter)))
        .build();
}
~~~

Nếu dùng bean `JwtAuthenticationConverter` mặc định, truyền bean đó vào DSL. Nếu thay bằng custom converter, kiểu generic phải tương thích với API của phiên bản Spring Security đang dùng.

## 3. Viết validator riêng theo token contract

`OAuth2TokenValidator<Jwt>` nhận một `Jwt` và trả `OAuth2TokenValidatorResult`. Validator không ký lại token và cũng không xác minh JWS signature; việc đó thuộc `JwtDecoder`. Validator kiểm tra các thuộc tính/claims sau khi decoder đã parse token.

### 3.1. Giữ validators mặc định

Với issuer cố định, `JwtValidators.createDefaultWithIssuer(issuer)` cung cấp bộ kiểm tra mặc định, gồm issuer và timestamp claims như `exp`/`nbf`. Có thể ghép validator riêng bằng `DelegatingOAuth2TokenValidator`.

~~~java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtClaimValidator;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtDecoders;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.JwtClaimNames;

@Configuration
class JwtDecoderConfiguration {

    private static final String ISSUER =
            "https://identity.example.test/realms/shop";

    @Bean
    JwtDecoder jwtDecoder() {
        var decoder = (org.springframework.security.oauth2.jwt.NimbusJwtDecoder)
                JwtDecoders.fromIssuerLocation(ISSUER);

        OAuth2TokenValidator<Jwt> standard =
                JwtValidators.createDefaultWithIssuer(ISSUER);

        OAuth2TokenValidator<Jwt> audience =
                new JwtClaimValidator<List<String>>(
                    JwtClaimNames.AUD,
                    aud -> aud != null && aud.contains("orders-api"));

        OAuth2TokenValidator<Jwt> accessTokenUse =
                new JwtClaimValidator<String>(
                    "token_use",
                    "access"::equals);

        OAuth2TokenValidator<Jwt> subject =
                new JwtClaimValidator<String>(
                    JwtClaimNames.SUB,
                    sub -> sub != null && !sub.isBlank());

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                standard, audience, accessTokenUse, subject));
        return decoder;
    }
}
~~~

`setJwtValidator` thay validator đang gắn trên decoder. Vì vậy ví dụ phải ghép `standard` với validator riêng. Nếu chỉ gọi:

~~~java
decoder.setJwtValidator(customAudienceValidator);
~~~

thì có thể vô tình bỏ issuer/time validation đã được cấu hình trước đó. Đây là lỗi rất phổ biến khi thêm kiểm tra audience.

Trong Spring Boot, có thể cấu hình audience bằng property `spring.security.oauth2.resourceserver.jwt.audiences` nếu chỉ cần allowlist audience tĩnh. Dùng validator riêng khi hợp đồng phức tạp hơn hoặc cần kiểm tra nhiều claim tùy biến.

### 3.2. Validator cho claim tenant theo contract

Một validator riêng có thể kiểm tra claim bắt buộc có đúng kiểu và không rỗng:

~~~java
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;

final class RequiredTenantClaimValidator
        implements OAuth2TokenValidator<Jwt> {

    private final OAuth2Error error = new OAuth2Error(
            "invalid_token",
            "Required tenant claim is missing or invalid",
            null);

    @Override
    public OAuth2TokenValidatorResult validate(Jwt jwt) {
        Object value = jwt.getClaims().get("tenant_id");
        if (value instanceof String tenant && !tenant.isBlank()) {
            return OAuth2TokenValidatorResult.success();
        }
        return OAuth2TokenValidatorResult.failure(error);
    }
}
~~~

Thêm validator vào chuỗi:

~~~java
OAuth2TokenValidator<Jwt> contract =
        new DelegatingOAuth2TokenValidator<>(
            standard, audience, accessTokenUse,
            subject, new RequiredTenantClaimValidator());
decoder.setJwtValidator(contract);
~~~

Validator này chỉ xác nhận token có một tenant claim đúng cấu trúc. Nó **không** chứng minh người dùng có membership trong tenant, cũng không quyết định user có được đọc một order cụ thể hay không. Membership và resource authorization vẫn thuộc application/domain policy.

### 3.3. Phân biệt audience và scope

Một token có scope đúng nhưng audience sai vẫn phải bị từ chối:

~~~json
{
  "aud": ["billing-api"],
  "scope": "orders.read"
}
~~~

`orders.read` không có nghĩa token được phát cho Orders API. Audience validator phải kiểm tra đích token; scope authorization chỉ chạy sau khi authentication thành công.

### 3.4. Kiểm tra access-token profile và typ

Một số Authorization Server tuân theo **RFC 9068 JWT Profile for OAuth 2.0 Access Tokens**, trong đó token type và các claim profile được quy định cụ thể. Không tự áp dụng quy tắc `typ` cho mọi JWT: OIDC ID token, access token và JWT nội bộ có profile khác nhau.

Với token theo RFC 9068, Spring Security cung cấp `JwtValidators.createAtJwtValidator()`. Tài liệu Spring Security minh họa việc tạo decoder với `validateTypes(false)` rồi dùng builder này để kiểm tra audience, client ID và issuer:

~~~java
NimbusJwtDecoder decoder = NimbusJwtDecoder
    .withIssuerLocation(issuer)
    .validateTypes(false)
    .build();

decoder.setJwtValidator(
    JwtValidators.createAtJwtValidator()
        .issuer(issuer)
        .audience("orders-api")
        .clientId("shop-web")
        .build());
~~~

Đây là lựa chọn cho profile RFC 9068 theo contract; đừng sao chép `validateTypes(false)` vào decoder của token profile khác mà không hiểu tác động. Nếu Authorization Server dùng claim riêng như `token_use=access`, validator tùy biến cần phản ánh chính xác contract đó.

### 3.5. Timestamp và clock skew

Spring Security dùng `JwtTimestampValidator` để kiểm tra cửa sổ hiệu lực. Mặc định clock skew của Resource Server là 60 giây; có thể điều chỉnh theo yêu cầu đồng bộ thời gian:

~~~java
OAuth2TokenValidator<Jwt> timeAndIssuer =
    new DelegatingOAuth2TokenValidator<>(
        new JwtTimestampValidator(Duration.ofSeconds(60)),
        new JwtIssuerValidator(issuer));
~~~

Nếu tự tạo chuỗi validator, nhớ giữ cả timestamp và issuer. Không tăng skew lớn để che lỗi đồng hồ hệ thống; hãy đồng bộ NTP và chọn tolerance theo SLA/threat model. Test nên bao gồm token vừa hết hạn, token chưa đến `nbf` và token trong khoảng skew được chấp nhận.

### 3.6. Validation không phải claim-set mapping

`MappedJwtClaimSetConverter` chạy trong decoder để chuẩn hóa/điều chỉnh kiểu hoặc nội dung claim khi tạo `Jwt`. Nó khác `OAuth2TokenValidator`:

- Claim-set converter: chuyển đổi biểu diễn dữ liệu.
- Validator: quyết định token có đáp ứng hợp đồng hay không.
- Authentication converter: biến token đã được chấp nhận thành principal/authorities.

Không dùng claim-set converter để sửa một issuer hoặc audience sai thành giá trị hợp lệ. Không map một claim thiếu thành role admin mặc định.

## 4. Thiết kế test theo từng lớp

| Lớp test | Đầu vào | Thành phần được kiểm tra | Không chứng minh được |
| --- | --- | --- | --- |
| Unit authority converter | Jwt dựng trong test | Scope/role mapping, prefix, duplicate handling | Signature/issuer/audience validation |
| Unit JwtAuthenticationConverter | Jwt dựng trong test | Authentication type, principal name, authorities | Filter chain/decoder thực tế |
| Unit validator | Jwt dựng trong test | Claim contract và kết quả success/failure | Chữ ký JWT/JWKS |
| Decoder test | JWT ký thật hoặc JWT lỗi | Signature + validator chain | HTTP endpoint authorization |
| MockMvc với `jwt()` | Mock Jwt | Controller, route/method authorization, claims | JwtDecoder và chữ ký; converter Authentication thực tế có thể bị bypass |
| MockMvc với Authorization header + decoder | JWT test token qua filter | Filter → provider → decoder → converter → authorization | JWKS/network production nếu dùng public key local |
| End-to-end với test IdP/JWKS | Token phát hành từ test AS | Hợp đồng thực tế giữa AS và Resource Server | Các issuer không nằm trong test |

Không có một loại test nào thay thế tất cả. Hãy chọn tầng theo câu hỏi cần trả lời.

## 5. Unit test cho authority converter

### 5.1. Dựng Jwt test

Một helper có thể tạo Jwt không cần ký vì đây là test logic chuyển đổi:

~~~java
import java.time.Instant;
import java.util.List;
import org.springframework.security.oauth2.jwt.Jwt;

final class JwtFixtures {

    static Jwt validContractJwt() {
        Instant now = Instant.now();
        return Jwt.withTokenValue("test-token")
            .header("alg", "RS256")
            .issuer("https://identity.example.test/realms/shop")
            .subject("alice-42")
            .audience(List.of("orders-api"))
            .issuedAt(now)
            .notBefore(now.minusSeconds(5))
            .expiresAt(now.plusSeconds(600))
            .claim("scope", "orders.read orders.cancel")
            .claim("roles", List.of("ORDER_ADMIN"))
            .claim("token_use", "access")
            .claim("tenant_id", "tenant-A")
            .build();
    }
}
~~~

Jwt dựng bằng builder không phải JWT đã được ký. Chỉ dùng nó để kiểm thử converter/validator trực tiếp; không dùng fixture này để kết luận signature validation hoạt động.

### 5.2. Kiểm tra mapping scope và role

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.Collection;
import org.junit.jupiter.api.Test;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.server.resource.authentication.DelegatingJwtGrantedAuthoritiesConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

class JwtAuthoritiesConverterTest {

    @Test
    void mapsScopesAndRolesIntoSeparateAuthorityNamespaces() {
        JwtGrantedAuthoritiesConverter scopes =
                new JwtGrantedAuthoritiesConverter();

        JwtGrantedAuthoritiesConverter roles =
                new JwtGrantedAuthoritiesConverter();
        roles.setAuthoritiesClaimName("roles");
        roles.setAuthorityPrefix("ROLE_");

        var converter =
                new DelegatingJwtGrantedAuthoritiesConverter(scopes, roles);

        Collection<GrantedAuthority> authorities =
                converter.convert(JwtFixtures.validContractJwt());

        assertThat(authorities)
            .extracting(GrantedAuthority::getAuthority)
            .contains("SCOPE_orders.read",
                      "SCOPE_orders.cancel",
                      "ROLE_ORDER_ADMIN");
    }
}
~~~

Test này xác nhận converter đọc đúng claim và prefix. Không nên chỉ assert số lượng authorities; assert chuỗi cụ thể giúp bắt lỗi đổi prefix hoặc đọc nhầm claim.

### 5.3. Kiểm tra claim role không đúng kiểu

Nếu contract yêu cầu `roles` là collection string, cần test dữ liệu lỗi:

~~~java
Jwt malformedRoles = Jwt.withTokenValue("test-token")
    .header("alg", "RS256")
    .claim("roles", "ORDER_ADMIN,ORDER_AUDITOR")
    .build();
~~~

Không mặc định `JwtGrantedAuthoritiesConverter` sẽ parse chuỗi phân tách dấu phẩy theo ý muốn. Hoặc contract quy định role là collection, hoặc viết converter riêng có parsing rõ ràng. Nếu kiểu claim sai khiến token không còn đúng contract, có thể từ chối bằng validator; nếu đây chỉ là dữ liệu quyền optional, converter phải xử lý theo chính sách đã định và không cấp thêm quyền.

### 5.4. Kiểm tra không nâng quyền ngoài danh sách cho phép

Nếu claim `roles` đến từ issuer nhưng ứng dụng chỉ tin một tập role nhất định, lọc bằng allowlist:

~~~java
private static final Set<String> ALLOWED_ROLES =
        Set.of("ORDER_ADMIN", "ORDER_AUDITOR");
~~~

Unit tests cần đưa vào `PLATFORM_ADMIN` hoặc `SUPERUSER` và xác nhận không tự biến thành authority nội bộ nếu role đó không nằm trong contract. Không tin một claim tên `roles` chỉ vì chữ ký JWT hợp lệ; nội dung claim vẫn cần được hiểu theo policy issuer.

## 6. Unit test JwtAuthenticationConverter

Kiểm tra cả ba thuộc tính quan trọng:

- Authentication type.
- Principal/name semantics.
- Authorities sau khi map.

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.DelegatingJwtGrantedAuthoritiesConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;

class JwtAuthenticationConverterTest {

    @Test
    void createsJwtAuthenticationWithExpectedPrincipalAndAuthorities() {
        Jwt jwt = JwtFixtures.validContractJwt();

        JwtGrantedAuthoritiesConverter scopes =
                new JwtGrantedAuthoritiesConverter();
        JwtGrantedAuthoritiesConverter roles =
                new JwtGrantedAuthoritiesConverter();
        roles.setAuthoritiesClaimName("roles");
        roles.setAuthorityPrefix("ROLE_");

        JwtAuthenticationConverter converter =
                new JwtAuthenticationConverter();
        converter.setJwtGrantedAuthoritiesConverter(
                new DelegatingJwtGrantedAuthoritiesConverter(scopes, roles));
        converter.setPrincipalClaimName("sub");

        var authentication = converter.convert(jwt);

        assertThat(authentication)
            .isInstanceOf(JwtAuthenticationToken.class);
        assertThat(authentication.getName()).isEqualTo("alice-42");
        assertThat(authentication.getPrincipal()).isSameAs(jwt);
        assertThat(authentication.getAuthorities())
            .extracting(GrantedAuthority::getAuthority)
            .contains("SCOPE_orders.read", "ROLE_ORDER_ADMIN");
    }
}
~~~

Ví dụ cho thấy một `Jwt` duy nhất được truyền vào converter rồi principal mặc định giữ đúng đối tượng đó.

### 6.1. Kiểm tra principal claim riêng

Nếu contract quy định `preferred_username` là principal name:

~~~java
Jwt jwt = Jwt.withTokenValue("test-token")
    .header("alg", "RS256")
    .subject("immutable-subject-42")
    .claim("preferred_username", "alice")
    .build();

JwtAuthenticationConverter converter =
        new JwtAuthenticationConverter();
converter.setPrincipalClaimName("preferred_username");

var authentication = converter.convert(jwt);
assertThat(authentication.getName()).isEqualTo("alice");
assertThat(authentication.getPrincipal()).isSameAs(jwt);
~~~

Đây chỉ thay tên hiển thị của principal trong Authentication. Nó không thay `sub` đã được xác minh trong JWT. Nếu subject là khóa định danh ổn định cho audit/identity mapping, giữ nguyên claim đó trong token và dùng đúng trường theo contract.

### 6.2. Kiểm tra custom Authentication converter

Nếu dùng `ContractJwtAuthenticationConverter` ở mục 2.4, test:

- Jwt có `sub` và `tenant_id` đúng: tạo token Authentication.
- Thiếu `sub`/tenant: validator phải từ chối trước; converter unit test có thể xác nhận defensive check.
- Authorities được truyền đầy đủ và không tự thêm role.
- `getName()` đúng với subject đã chọn.

Unit test converter không nên gọi Authorization Server, database hoặc HTTP. Nếu converter có lookup phụ thuộc DB, tách resolver thành service riêng và mock service đó; sau đó có integration test cho đường authentication thực.

## 7. Unit test cho OAuth2TokenValidator

### 7.1. Test validator audience

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtClaimNames;
import org.springframework.security.oauth2.jwt.JwtClaimValidator;

class AudienceValidatorTest {

    private final OAuth2TokenValidator<Jwt> validator =
            new JwtClaimValidator<List<String>>(
                JwtClaimNames.AUD,
                aud -> aud != null && aud.contains("orders-api"));

    @Test
    void acceptsTokenForOrdersApi() {
        Jwt jwt = Jwt.withTokenValue("test")
            .header("alg", "RS256")
            .audience(List.of("orders-api"))
            .build();

        assertThat(validator.validate(jwt).hasErrors()).isFalse();
    }

    @Test
    void rejectsTokenForAnotherAudience() {
        Jwt jwt = Jwt.withTokenValue("test")
            .header("alg", "RS256")
            .audience(List.of("billing-api"))
            .build();

        assertThat(validator.validate(jwt).hasErrors()).isTrue();
    }
}
~~~

Đây là unit test cho validator thuần. Nó không kiểm tra chữ ký, issuer hay thời hạn; những điều kiện đó thuộc decoder và các validator khác trong chuỗi.

### 7.2. Test validator tenant

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.jwt.Jwt;

class RequiredTenantClaimValidatorTest {

    private final RequiredTenantClaimValidator validator =
            new RequiredTenantClaimValidator();

    @Test
    void acceptsNonBlankTenant() {
        Jwt jwt = Jwt.withTokenValue("test")
            .header("alg", "RS256")
            .claim("tenant_id", "tenant-A")
            .build();

        assertThat(validator.validate(jwt).hasErrors()).isFalse();
    }

    @Test
    void rejectsMissingTenant() {
        Jwt jwt = Jwt.withTokenValue("test")
            .header("alg", "RS256")
            .build();

        assertThat(validator.validate(jwt).hasErrors()).isTrue();
    }

    @Test
    void rejectsWrongTenantClaimType() {
        Jwt jwt = Jwt.withTokenValue("test")
            .header("alg", "RS256")
            .claim("tenant_id", 42)
            .build();

        assertThat(validator.validate(jwt).hasErrors()).isTrue();
    }
}
~~~

### 7.3. Test validator theo token profile

Với claim `token_use`, test ít nhất:

| Giá trị | Kỳ vọng |
| --- | --- |
| `access` | Thành công |
| `id` | Thất bại |
| `refresh` | Thất bại |
| null/thiếu | Thất bại |
| kiểu dữ liệu không phải String | Thất bại |

Nếu contract dùng `typ=at+jwt` theo RFC 9068, dùng validator/profile builder tương ứng và kiểm thử header type riêng. Không gộp hai profile khác nhau thành một validator “linh hoạt” chấp nhận cả ID token và access token.

## 8. MockMvc test với jwt() cho authorization

Spring Security Test cung cấp `SecurityMockMvcRequestPostProcessors.jwt()` để tạo một mock JWT authentication. Cách này rất hữu ích khi muốn tập trung vào:

- Endpoint có yêu cầu đúng scope/role hay không.
- Controller đọc claim/principal như mong đợi không.
- Method security hoặc request authorization có từ chối authority thiếu không.

Ví dụ:

~~~java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@Test
void allowsRequestWhenRequiredScopeIsPresent() throws Exception {
    mvc.perform(get("/api/orders")
            .with(jwt()
                .jwt(token -> token
                    .issuer("https://identity.example.test/realms/shop")
                    .subject("alice-42")
                    .audience(List.of("orders-api"))
                    .claim("scope", "orders.read")
                    .claim("tenant_id", "tenant-A"))
                .authorities(new SimpleGrantedAuthority(
                    "SCOPE_orders.read"))))
        .andExpect(status().isOk());
}

@Test
void deniesRequestWhenRequiredScopeIsMissing() throws Exception {
    mvc.perform(get("/api/orders")
            .with(jwt()
                .jwt(token -> token
                    .subject("alice-42")
                    .claim("scope", "profile.read"))
                .authorities(new SimpleGrantedAuthority(
                    "SCOPE_profile.read"))))
        .andExpect(status().isForbidden());
}
~~~

Đây là **mock Authentication**, không phải một JWT JWS đã được ký. Theo tài liệu Spring Security, JWT mặc định của request post processor có header `alg=none`. Nó không đi qua chữ ký/JWKS validation của `JwtDecoder`. Khi truyền `authorities(...)`, test đang chỉ định authorities cho Authentication; nếu truyền converter vào overload này, đó là converter `Jwt -> Collection<GrantedAuthority>`, không chứng minh bean `JwtAuthenticationConverter` đang được cấu hình trong filter chain chạy đúng.

Vì vậy:

- Dùng `jwt()` để test route/method authorization và cách controller sử dụng claims.
- Unit test trực tiếp `JwtAuthenticationConverter` để test Authentication mapping.
- Dùng request có `Authorization: Bearer ...` đi qua filter chain với decoder thật hoặc decoder mock để test wiring của converter.
- Dùng signed token/real decoder để test signature và validator contract.

### 8.1. Test authorities theo claim converter

Nếu chỉ muốn kiểm tra converter authorities trong request post processor, Spring Security Test cho phép:

~~~java
.with(jwt().authorities(jwtAuthoritiesConverter))
~~~

Đây là một test hữu ích cho mapping scope/role. Nhưng nó vẫn không chứng minh `JwtAuthenticationConverter` bean, `JwtDecoder` hoặc custom validators đang được wiring trong production chain.

### 8.2. Khi nào dùng authentication() thay vì jwt()?

`authentication(authentication)` cho phép cài trực tiếp một Authentication tự tạo vào request. Nó phù hợp khi endpoint nhận một custom Authentication type hoặc test muốn kiểm soát toàn bộ principal/authorities. Giống `jwt()`, cách này bỏ qua quá trình giải mã/validation token thật; không dùng để chứng minh decoder.

## 9. Kiểm thử decoder với JWT ký thật

Để kiểm thử signature và validator cùng lúc, tạo cặp RSA riêng cho test:

- Test encoder ký token bằng private key.
- Test decoder chỉ nhận public key tương ứng.
- Gắn validator chain thật vào decoder.
- Gọi `decode(tokenValue)` và kiểm tra token hợp lệ hoặc exception.

Không dùng private key production trong test. Không dùng `alg=none` để giả lập một token hợp lệ.

### 9.1. Cấu hình decoder bằng public key test

~~~java
import java.security.interfaces.RSAPublicKey;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;

RSAPublicKey publicKey = (RSAPublicKey) testKeyPair.getPublic();
NimbusJwtDecoder decoder =
        NimbusJwtDecoder.withPublicKey(publicKey).build();

decoder.setJwtValidator(
    new DelegatingOAuth2TokenValidator<>(
        JwtValidators.createDefaultWithIssuer(ISSUER),
        audienceValidator,
        accessTokenUseValidator,
        new RequiredTenantClaimValidator()));
~~~

Đây là cấu hình test decoder cục bộ; nó xác minh chữ ký bằng public key test thay vì gọi JWKS. Validator chain vẫn phải kiểm tra issuer/time và các claim contract. Nếu production dùng JWKS, cần thêm integration test riêng với test JWKS endpoint để xác nhận key discovery/rotation.

### 9.2. Tạo JWT ký bằng Nimbus JwtEncoder

~~~java
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;
import java.time.Instant;
import java.util.List;

import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jose.jwk.source.ImmutableJWKSet;
import com.nimbusds.jose.jwk.source.JWKSource;
import com.nimbusds.jose.proc.SecurityContext;

import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.JwtClaimsSet;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.JwtEncoderParameters;
import org.springframework.security.oauth2.jwt.JwsHeader;
import org.springframework.security.oauth2.jwt.NimbusJwtEncoder;

static KeyPair generateRsaKeyPair() {
    try {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        return generator.generateKeyPair();
    } catch (java.security.GeneralSecurityException ex) {
        throw new IllegalStateException(ex);
    }
}

static JwtEncoder encoderFor(KeyPair keyPair) {
    RSAKey jwk = new RSAKey.Builder(
            (RSAPublicKey) keyPair.getPublic())
        .privateKey((RSAPrivateKey) keyPair.getPrivate())
        .keyID("test-key")
        .build();

    JWKSource<SecurityContext> source =
            new ImmutableJWKSet<>(new JWKSet(jwk));
    return new NimbusJwtEncoder(source);
}

static String signedAccessToken(
        JwtEncoder encoder, String audience, String tokenUse) {
    Instant now = Instant.now();

    JwtClaimsSet claims = JwtClaimsSet.builder()
        .issuer(ISSUER)
        .subject("alice-42")
        .audience(List.of(audience))
        .issuedAt(now.minusSeconds(2))
        .notBefore(now.minusSeconds(2))
        .expiresAt(now.plusSeconds(300))
        .claim("scope", "orders.read")
        .claim("roles", List.of("ORDER_ADMIN"))
        .claim("token_use", tokenUse)
        .claim("tenant_id", "tenant-A")
        .build();

    JwsHeader header = JwsHeader
        .with(SignatureAlgorithm.RS256)
        .keyId("test-key")
        .build();

    return encoder.encode(
        JwtEncoderParameters.from(header, claims)).getTokenValue();
}
~~~

`ISSUER` là hằng số test trùng với issuer validator. Tạo encoder thứ hai từ một KeyPair khác để phát token có chữ ký không được decoder tin cậy.

Nếu test cần thay scope hoặc các claims theo scenario, có thể dùng một helper nhận scope:

~~~java
static String signedTokenWithClaims(
        JwtEncoder encoder,
        String audience,
        String tokenUse,
        String scope) {
    Instant now = Instant.now();
    JwtClaimsSet claims = JwtClaimsSet.builder()
        .issuer(ISSUER)
        .subject("alice-42")
        .audience(List.of(audience))
        .issuedAt(now.minusSeconds(2))
        .notBefore(now.minusSeconds(2))
        .expiresAt(now.plusSeconds(300))
        .claim("scope", scope)
        .claim("roles", List.of("ORDER_ADMIN"))
        .claim("token_use", tokenUse)
        .claim("tenant_id", "tenant-A")
        .build();

    JwsHeader header = JwsHeader
        .with(SignatureAlgorithm.RS256)
        .keyId("test-key")
        .build();
    return encoder.encode(
        JwtEncoderParameters.from(header, claims)).getTokenValue();
}
~~~

### 9.3. Test validator pass/fail sau khi signature đúng

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidationException;

class SignedJwtDecoderTest {

    @Test
    void acceptsSignedTokenThatMatchesTheContract() {
        String token = signedAccessToken(
                trustedEncoder, "orders-api", "access");

        var jwt = decoder.decode(token);

        assertThat(jwt.getSubject()).isEqualTo("alice-42");
        assertThat(jwt.getAudience()).contains("orders-api");
        assertThat(jwt.getClaimAsString("tenant_id"))
            .isEqualTo("tenant-A");
    }

    @Test
    void rejectsSignedTokenWithWrongAudience() {
        String token = signedAccessToken(
                trustedEncoder, "billing-api", "access");

        assertThatThrownBy(() -> decoder.decode(token))
            .isInstanceOf(JwtValidationException.class);
    }

    @Test
    void rejectsSignedIdTokenProfile() {
        String token = signedAccessToken(
                trustedEncoder, "orders-api", "id");

        assertThatThrownBy(() -> decoder.decode(token))
            .isInstanceOf(JwtValidationException.class);
    }

    @Test
    void rejectsTokenSignedByAnUntrustedKey() {
        String token = signedAccessToken(
                attackerEncoder, "orders-api", "access");

        assertThatThrownBy(() -> decoder.decode(token))
            .isInstanceOf(org.springframework.security.oauth2.jwt.JwtException.class);
    }
}
~~~

Đây là skeleton test: `decoder`, `trustedEncoder` và `attackerEncoder` được tạo trong test fixture/configuration. Trường hợp sai chữ ký có thể ném `BadJwtException` hoặc một subtype `JwtException` tùy decoder; không khóa test vào một thông báo lỗi nội bộ cụ thể.

### 9.4. Phân biệt signature failure và validation failure

| Test case | Chữ ký | Validator | Kết quả |
| --- | --- | --- | --- |
| Token hợp lệ | Đúng | Tất cả pass | Decode thành công |
| Audience sai | Đúng | Audience fail | `JwtValidationException` |
| `token_use` sai | Đúng | Profile validator fail | `JwtValidationException` |
| Tenant claim thiếu | Đúng | Required-claim validator fail | `JwtValidationException` |
| Token hết hạn | Đúng | Timestamp validator fail | `JwtValidationException` |
| Chữ ký bằng key khác | Sai với trusted key | Không đến bước validator hợp lệ | `JwtException` |

Không gộp mọi lỗi thành “JWT sai chữ ký”. Trong vận hành, signature failure và claim-contract failure có nguyên nhân khác nhau; response công khai vẫn nên giữ thông tin tối thiểu, còn metrics/log nội bộ có thể phân loại theo error code mà không ghi token.

## 10. MockMvc integration test qua Resource Server filter chain

Để chứng minh `JwtAuthenticationConverter` thực sự được gọi, gửi HTTP request với Authorization header và để Spring Security chạy pipeline bình thường. Không cài sẵn Authentication bằng `jwt()` hoặc `authentication()` trong test này.

Một cấu hình test tối thiểu cần:

- `SecurityFilterChain` sử dụng `oauth2ResourceServer().jwt(...)`.
- `JwtDecoder` thật (có thể dùng public key test local).
- `JwtAuthenticationConverter` được nối vào DSL.
- Controller test đọc `Authentication.getName()` hoặc principal.
- MockMvc bật Spring Security filter chain.

Ví dụ endpoint:

~~~java
@RestController
class TestOrdersController {

    @GetMapping("/api/orders")
    String orders(Authentication authentication) {
        return authentication.getName();
    }
}
~~~

Cấu hình chain:

~~~java
@Bean
SecurityFilterChain testApi(
        HttpSecurity http,
        JwtDecoder decoder,
        JwtAuthenticationConverter converter) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/orders")
                .hasAuthority("SCOPE_orders.read")
            .anyRequest().denyAll())
        .oauth2ResourceServer(resourceServer -> resourceServer
            .jwt(jwt -> jwt
                .decoder(decoder)
                .jwtAuthenticationConverter(converter)))
        .build();
}
~~~

Với test configuration ở mục 9, MockMvc gửi token được ký bằng private key test:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class JwtAuthenticationHttpTest {

    @Autowired MockMvc mvc;
    @Autowired JwtEncoder trustedEncoder;

    @Test
    void validSignedTokenPassesThroughDecoderAndConverter()
            throws Exception {
        String token = signedAccessToken(
                trustedEncoder, "orders-api", "access");

        mvc.perform(get("/api/orders")
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + token))
            .andExpect(status().isOk())
            .andExpect(content().string("alice-42"));
    }
}
~~~

Đây là skeleton kết hợp với test controller, decoder, encoder và filter chain ở các mục trước. Trong dự án thực, dùng test application context phù hợp (ví dụ `@WebMvcTest` + `@Import` hoặc `@SpringBootTest`) và bảo đảm filter chain đang được bật.

### 10.1. Test validator chặn trước converter

Với token có chữ ký đúng nhưng audience sai, decoder phải từ chối request trước khi converter được dùng. Có thể dùng spy/mock bean cho converter hoặc service để quan sát:

~~~java
@Test
void wrongAudienceIsRejectedBeforeControllerRuns() throws Exception {
    String token = signedAccessToken(
            trustedEncoder, "billing-api", "access");

    mvc.perform(get("/api/orders")
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + token))
        .andExpect(status().isUnauthorized());

    verify(orderService, never()).listOrders(any());
}
~~~

`orderService` là dependency mock của controller trong test. Kỳ vọng chính là controller/service không chạy khi decoder từ chối token. Nếu muốn chứng minh trực tiếp converter không được gọi, inject spy cho converter và verify không có invocation; cách khai báo spy tùy phiên bản Spring Boot/Spring Test đang dùng.

### 10.2. Test thiếu scope là 403, không phải validator failure

Token đúng issuer, signature, audience, tenant và token type nhưng chỉ có `profile.read`:

~~~java
@Test
void validTokenWithoutRequiredScopeIsForbidden() throws Exception {
    String token = signedTokenWithClaims(
            trustedEncoder,
            "orders-api",
            "access",
            "profile.read");

    mvc.perform(get("/api/orders")
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + token))
        .andExpect(status().isForbidden());
}
~~~

Trong test này decoder/converter thành công; request bị chặn ở authorization vì thiếu `SCOPE_orders.read`. Đây là khác biệt quan trọng giữa **401 authentication failure** và **403 authorization denial**.

### 10.3. Test token invalid không được converter “cứu”

Không viết converter theo kiểu:

~~~java
if (jwt.getAudience().isEmpty()) {
    return new JwtAuthenticationToken(jwt, ADMIN_AUTHORITIES);
}
~~~

Validator phải từ chối audience thiếu/sai. Converter chỉ ánh xạ claims theo contract. Test sai audience phải assert 401 và không gọi controller/service.

## 11. Ma trận kiểm thử hợp đồng

| Mã | Token fixture | Lớp kỳ vọng fail/pass | HTTP kỳ vọng |
| --- | --- | --- | --- |
| C01 | Chữ ký đúng, issuer đúng, audience đúng, scope đúng | Pass decoder + converter + authorization | 200 |
| C02 | Chữ ký đúng, issuer khác | Issuer validator | 401 |
| C03 | Chữ ký đúng, audience khác | Audience validator | 401 |
| C04 | Chữ ký sai/khóa không tin cậy | Signature verification | 401 |
| C05 | `exp` đã qua | Timestamp validator | 401 |
| C06 | `nbf` ở tương lai ngoài skew | Timestamp validator | 401 |
| C07 | Thiếu `sub` | Required-claim validator | 401 |
| C08 | Thiếu `tenant_id` | Contract validator | 401 |
| C09 | `token_use=id` | Access-token profile validator | 401 |
| C10 | Scope đúng, role đúng | Authority converter | Authentication có đủ authorities |
| C11 | Scope thiếu | Request authorization | 403 |
| C12 | Role claim chứa role không allowlist | Role mapping policy | Không tạo privileged authority |
| C13 | `roles` sai kiểu dữ liệu | Contract validator/converter policy | Fail theo contract |
| C14 | Hai scope trùng hoặc lặp | Authority converter | Không cấp thêm quyền; kết quả ổn định |
| C15 | JWT hợp lệ nhưng tenant/resource không thuộc caller | Domain authorization | 403/404 theo API policy |
| C16 | Claim optional vắng mặt | Theo contract đã định | Không tự tạo authority |

Không phải tất cả case đều có cùng status. Sai token/claim contract thường là 401; token hợp lệ nhưng thiếu scope thường là 403; resource không thuộc quyền có thể trả 403 hoặc 404 theo disclosure policy.

## 12. Kiểm tra converter được wiring vào filter chain

Unit test trực tiếp converter chỉ chứng minh object converter làm việc. Cần thêm một test chứng minh `JwtAuthenticationProvider` thực sự gọi converter đã cấu hình.

Có hai cách phổ biến:

### 12.1. Dùng decoder mock để cô lập converter wiring

Thay `JwtDecoder` bằng mock trả về một Jwt fixture, nhưng gửi request bằng Authorization header để request vẫn đi qua Bearer filter và provider:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class JwtConverterWiringTest {

    @Autowired MockMvc mvc;
    @MockBean JwtDecoder jwtDecoder;

    @Test
    void bearerRequestUsesConfiguredAuthenticationConverter()
            throws Exception {
        Jwt jwt = JwtFixtures.validContractJwt();
        given(jwtDecoder.decode("test-token")).willReturn(jwt);

        mvc.perform(get("/api/orders")
                .header(HttpHeaders.AUTHORIZATION, "Bearer test-token"))
            .andExpect(status().isOk())
            .andExpect(content().string("alice-42"));
    }
}
~~~

Trong test này, `JwtDecoder` đã bị mock nên chữ ký, issuer và validator thật không được kiểm tra. Mục tiêu riêng của nó là chứng minh filter/provider gọi decoder rồi sử dụng converter được nối trong `SecurityFilterChain`. Nếu cần verify converter invocation trực tiếp, dùng spy cho bean converter và xác nhận nó nhận đúng Jwt.

Spring Boot/Spring Framework có thể dùng `@MockBean` hoặc `@MockitoBean` tùy phiên bản. Dùng annotation phù hợp với test stack của dự án; ý tưởng test không phụ thuộc tên annotation.

### 12.2. Dùng decoder thật để kiểm tra cả pipeline

Test mạnh hơn là cấu hình `NimbusJwtDecoder` với public key test, gửi JWT đã ký qua:

~~~http
GET /api/orders HTTP/1.1
Authorization: Bearer <signed-jwt>
~~~

Request đi qua:

1. `BearerTokenAuthenticationFilter` lấy token.
2. `JwtAuthenticationProvider` gọi decoder.
3. Decoder xác minh chữ ký và chạy validators.
4. Khi token hợp lệ, provider gọi `JwtAuthenticationConverter`.
5. Authentication được đưa vào SecurityContext.
6. Request authorization kiểm tra scope/role.

Với token audience sai nhưng chữ ký đúng, test phải nhận 401 và converter/controller không chạy. Với token hợp lệ nhưng thiếu scope, converter vẫn chạy, sau đó authorization trả 403.

### 12.3. Test thứ tự validator trước converter

Nếu dùng spy/mock cho converter:

~~~java
@Test
void invalidAudienceDoesNotReachAuthenticationConverter()
        throws Exception {
    String token = signedAccessToken(
            trustedEncoder, "billing-api", "access");

    mvc.perform(get("/api/orders")
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + token))
        .andExpect(status().isUnauthorized());

    verify(authenticationConverter, never()).convert(any(Jwt.class));
}
~~~

`authenticationConverter` là spy được inject đúng bean mà filter chain sử dụng. Test này kiểm tra invariant quan trọng: **validator fail thì converter không có cơ hội tạo Authentication**.

## 13. Kiểm thử lỗi và hợp đồng thay đổi

### 13.1. 401 và 403 phải được phân biệt

| Kết quả | Nguyên nhân | Converter có chạy không? |
| --- | --- | --- |
| 401 không có token | Không có credential | Không |
| 401 chữ ký sai | Decoder không xác minh được token | Không |
| 401 issuer/audience/exp/token profile sai | Validator từ chối | Không |
| 200 | Token hợp lệ và authorization cho phép | Có |
| 403 thiếu scope | Authentication hợp lệ nhưng thiếu authority | Có |
| 403 role không đủ | Authentication hợp lệ nhưng role policy từ chối | Có |
| 403/404 sai tenant hoặc owner | Domain authorization từ chối | Có |

Không test bằng cách chỉ kiểm tra status cho mọi trường hợp. Với các ca 401, xác nhận controller/service không được gọi; với 403, xác nhận authentication đã thành công nhưng authority/resource policy không đủ.

### 13.2. Kiểm tra lỗi converter không bị nuốt

Nếu converter có thể phát sinh lỗi do dữ liệu claim không hợp lệ, test phải bảo đảm lỗi không biến thành một Authentication mặc định với quyền rộng. Cách tốt hơn là validator kiểm tra claim bắt buộc trước, còn converter là hàm mapping có đầu vào đã được bảo đảm.

Tránh các fallback nguy hiểm:

~~~java
try {
    return mapAuthorities(jwt);
} catch (RuntimeException ex) {
    return List.of(new SimpleGrantedAuthority("ROLE_ADMIN"));
}
~~~

Nếu dữ liệu quyền không thể diễn giải, fail closed theo contract. Không trả danh sách quyền mặc định có đặc quyền.

### 13.3. Kiểm tra contract khi Authorization Server đổi claim

Giả sử IdP chuyển từ `scope` sang `scp` hoặc đổi `roles` từ collection thành chuỗi. Không nên âm thầm sửa converter để chấp nhận mọi hình dạng mà chưa có versioning contract.

Nên có fixtures đại diện cho:

- Token profile hiện hành.
- Token profile cũ trong thời gian chuyển tiếp nếu còn được chấp nhận.
- Token có claim thiếu hoặc sai kiểu.
- Token từ issuer khác nhưng cùng tên claim.

Nếu phải hỗ trợ hai schema trong migration, định nghĩa rõ ưu tiên và thời hạn loại bỏ schema cũ. Test bảo đảm một claim xấu không thể ghi đè quyền từ claim tin cậy khác.

### 13.4. Test nhiều issuer và tenant

Nếu API chấp nhận nhiều issuer, mỗi issuer có thể có claim naming/role semantics khác nhau. Dùng validator/decoder riêng theo issuer allowlist và converter tương ứng, hoặc chuẩn hóa contract một cách tường minh sau khi issuer được xác minh.

Negative tests:

- Issuer không nằm trong allowlist.
- Issuer A phát claim `roles` với semantics khác issuer B.
- Token tenant A chứa role chỉ có ý nghĩa trong tenant B.
- Hai issuer cùng `sub` nhưng không cùng identity.
- Claim tenant thiếu hoặc sai kiểu.

Không chọn converter hoặc JWKS URL dựa trên issuer chưa được xác minh từ payload. Việc định tuyến multi-issuer phải dùng danh sách trust đã cấu hình.

## 14. Lỗi thường gặp khi viết test

**Dùng `@WithMockUser` để test JWT claims.** Annotation này tạo user authentication đơn giản, không kiểm tra Jwt principal, claims hay JwtAuthenticationConverter. Dùng nó khi endpoint chỉ cần một generic UserDetails principal; dùng JWT test support hoặc signed token khi code phụ thuộc Jwt.

**Dùng `jwt()` rồi kết luận decoder/validator đã chạy.** Request post processor tạo mock Jwt/Authentication và không kiểm tra JWS signature hoặc JWKS. Phải có decoder test và signed-token integration test.

**Chỉ test authority count.** Hai authority có thể sai prefix hoặc sai tên. Assert chính xác `SCOPE_...` và `ROLE_...`.

**Đổi toàn bộ prefix thành ROLE_.** Scope và role có ý nghĩa khác nhau; giữ namespace riêng.

**Thêm audience validator nhưng quên default validators.** `setJwtValidator` thay validator hiện tại; compose default issuer/time validators với custom validators.

**Test token audience sai bằng `jwt()` và mong 401.** Vì mock JWT không đi qua decoder, audience validator không chạy. Dùng validator unit test hoặc signed token qua decoder.

**Dùng token giả `alg=none` để kiểm tra chữ ký.** Fixture này chỉ dùng cho converter/authorization unit tests. Signature tests cần JWS thật và public key tin cậy.

**Đưa authorization nghiệp vụ vào converter.** Converter nên map identity/authorities. Tenant membership và quyền trên resource cần kiểm tra ở service/method authorization.

**Dùng validator để map role.** Validator chỉ accept/reject token contract; authority converter mới tạo GrantedAuthority.

**Chấp nhận claim thiếu bằng default admin.** Claim thiếu hoặc không hợp lệ phải fail closed theo contract; không tự nâng quyền.

**Assert nguyên văn error message của decoder.** Thông điệp có thể thay đổi theo version/provider. Ưu tiên exception type/error code/status và xác nhận side effect không xảy ra.

**Không test scope thiếu.** Token có thể hoàn toàn hợp lệ nhưng không được phép gọi endpoint. Cần test riêng 403 sau khi authentication thành công.

**Không test converter chưa được wiring.** Unit test bean có thể pass trong khi filter chain vẫn dùng converter mặc định. Gửi Authorization header thật qua MockMvc và xác nhận principal/authorities.

**Dùng một decoder mock cho tất cả test rồi kết luận toàn bộ bảo mật đã được kiểm tra.** Mock decoder bỏ qua chữ ký và validators. Giữ riêng test wiring và test decoder thật.

## 15. Checklist bàn giao test suite

### Hợp đồng token

- [ ] Ghi rõ issuer, audience, thuật toán, thời hạn và access-token profile.
- [ ] Ghi rõ claim bắt buộc, kiểu dữ liệu và quy tắc rỗng/null.
- [ ] Phân biệt scope, role, tenant và claim định danh.
- [ ] Xác định claim nào là bắt buộc và claim nào chỉ là optional metadata.
- [ ] Có fixtures cho token đúng và từng dạng token sai theo contract.

### Validator/decoder

- [ ] Signature được kiểm tra bằng public key/JWKS tin cậy.
- [ ] Chỉ chấp nhận thuật toán đã cấu hình.
- [ ] Issuer validator được giữ khi thêm custom validator.
- [ ] Audience validator khớp đúng Resource Server.
- [ ] Timestamp validator và clock skew được cấu hình có chủ đích.
- [ ] Token type/profile và claim bắt buộc được kiểm tra.
- [ ] Custom validator trả lỗi fail closed khi thiếu/sai claim.
- [ ] Unit tests bao phủ success/failure; decoder test bao phủ signed token.

### Converter/Authentication

- [ ] Scope được ánh xạ thành authority prefix đúng.
- [ ] Role được ánh xạ riêng và chỉ từ claim được tin theo contract.
- [ ] Principal name có semantics rõ ràng.
- [ ] Principal object đúng kiểu controller/method security mong đợi.
- [ ] Converter không cấp role mặc định khi claim sai/thiếu.
- [ ] Unit test kiểm tra chính xác authority strings và Authentication type.
- [ ] Filter-chain test chứng minh converter được wiring.

### Servlet/MockMvc integration

- [ ] Dùng `jwt()` cho authorization tests có chủ đích, không dùng để giả lập signature validation.
- [ ] Gửi Authorization header để test Bearer filter/provider/decoder/converter chain.
- [ ] Có test signed JWT qua decoder thật.
- [ ] Có test chữ ký sai, issuer sai, audience sai, token hết hạn và claim contract sai.
- [ ] Có test token hợp lệ nhưng thiếu scope/role trả 403.
- [ ] Khi token bị từ chối, controller/service không được gọi.
- [ ] Không assert thông báo lỗi nội bộ dễ thay đổi giữa các phiên bản.

## 16. Tình huống thực hành

**Tình huống A.** Một token có chữ ký đúng, issuer đúng, scope `orders.read` nhưng `aud` là `billing-api`. Converter có nên tự thêm `SCOPE_orders.read` và cho request qua không?

**Không.** Audience validator phải từ chối token trước khi converter chạy. Scope đúng không biến token dành cho Billing API thành token dành cho Orders API.

**Tình huống B.** Unit test `JwtAuthenticationConverter` pass và tạo đúng `ROLE_ORDER_ADMIN`. Có thể kết luận filter chain production dùng converter này không?

**Chưa.** Cần test request Authorization header qua MockMvc/Servlet filter chain và xác nhận bean converter đã được wiring vào `oauth2ResourceServer().jwt(...)`.

**Tình huống C.** MockMvc dùng `jwt()` với token fixture có claim `iss` và `aud` sai nhưng request vẫn qua authentication. Vì sao?

`jwt()` tạo mock JWT Authentication để test authorization; nó không gọi decoder và không chạy signature/issuer/audience validators. Dùng unit test validator hoặc signed token qua decoder thật.

**Tình huống D.** Thêm audience validator bằng `decoder.setJwtValidator(audienceValidator)`. Sau đó token hết hạn vẫn được chấp nhận. Lỗi ở đâu?

Đã thay validator mặc định và bỏ timestamp validation. Ghép `JwtValidators.createDefaultWithIssuer` với custom audience validator bằng `DelegatingOAuth2TokenValidator`.

**Tình huống E.** Token hợp lệ nhưng thiếu `SCOPE_orders.read` nhận 403. Converter có lỗi không?

Không nhất thiết. Decoder và converter có thể chạy đúng; authorization từ chối vì thiếu authority. Cần kiểm tra authority list và policy route.

**Tình huống F.** Claim `roles` chứa `PLATFORM_ADMIN` nhưng ứng dụng không có role này trong allowlist. Có nên map nguyên văn thành `ROLE_PLATFORM_ADMIN`?

Không mặc định. Chỉ map role được contract và policy ứng dụng cho phép; token ký hợp lệ không có nghĩa mọi role string đều được ứng dụng cấp quyền.

**Tình huống G.** Custom converter phát hiện thiếu `tenant_id` và tự gán `tenant-default`. Có an toàn không?

Chỉ nếu contract quy định rõ default tenant và việc gán đó không làm tăng quyền. Với API yêu cầu tenant context, nên từ chối bằng validator; không tự suy diễn tenant.

**Tình huống H.** JWT signature sai nhưng claim scope có `orders.cancel`. Request có thể chạy tới service không?

Không. Decoder phải từ chối trước converter và authorization; service không được thực thi.

**Tình huống I.** Converter unit test thành công nhưng signed-token integration test trả 401 vì issuer mismatch. Có nên bỏ issuer validator để test pass?

Không. Unit test kiểm tra mapping; integration test đang phát hiện token không đáp ứng trust contract. Sửa issuer/config/token fixture theo hợp đồng đúng.

**Tình huống J.** Authorization Server đổi `roles` từ list thành chuỗi comma-separated. Cần sửa gì?

Thay đổi contract có kiểm soát: cập nhật converter hoặc validator theo schema mới, thêm fixtures cho migration window và test không tạo role ngoài allowlist. Không chấp nhận mọi hình dạng dữ liệu một cách ngầm định.

---

## Kết luận

Kiểm thử `JwtAuthenticationConverter` và validator riêng cần được chia theo trách nhiệm. **Validator/decoder quyết định JWT có được tin hay không** dựa trên chữ ký, issuer, thời hạn, audience và claim contract. **Authentication converter quyết định token đã được tin sẽ trở thành principal và authorities nào**. Authority converter là lớp con chuyên ánh xạ scope/role; nó không thay validator và không quyết định quyền trên từng resource.

Hãy dùng unit tests để kiểm tra mapping scope/role, principal name và từng validator; dùng `jwt()` trong MockMvc để kiểm tra authorization/controller khi không cần ký token; dùng Authorization header qua filter chain để kiểm tra converter wiring; và dùng JWT ký thật qua `JwtDecoder` để xác minh signature cùng validator contract. Một bộ test tốt phải phân biệt **401 do authentication/token contract thất bại** với **403 do token hợp lệ nhưng thiếu quyền**, đồng thời chứng minh request bị từ chối không chạy vào nghiệp vụ.

## Tài liệu tham khảo

1. [Spring Security 7.1 — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
2. [Spring Security 7.1 — Testing OAuth 2.0 / JWT with MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html)
3. [Spring Security API — JwtValidators](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/JwtValidators.html)
4. [Spring Security API — OAuth2TokenValidator](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/core/OAuth2TokenValidator.html)
5. [Spring Security API — DelegatingOAuth2TokenValidator](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/core/DelegatingOAuth2TokenValidator.html)
6. [RFC 9068 — JSON Web Token (JWT) Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068.html)
7. [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519.html)
