# Đọc claim chưa xác minh chỉ để chọn chiến lược, không để cấp quyền

Trong hệ thống **Spring Security OAuth 2.0/OIDC Resource Server** phục vụ **nhiều tenant**, một API có thể tiếp nhận access token từ nhiều Authorization Server hoặc từ nhiều realm của cùng nền tảng định danh. Resource Server cần quyết định **decoder/khóa/issuer policy nào** sẽ dùng để xác minh token trước khi tạo `Authentication`.

Một cách triển khai thường gặp là **đọc sơ bộ claim `iss` (issuer) từ JWT chưa được xác minh** để tìm đúng cấu hình xác thực. Bước này đôi khi khiến người đọc lo lắng: “Nếu payload JWT có thể do attacker tự sửa, sao lại đọc `iss` trước khi kiểm tra chữ ký?”

Câu trả lời nằm ở việc phân biệt **dùng dữ liệu chưa tin cậy để định tuyến** và **dùng dữ liệu chưa tin cậy để quyết định quyền**:

- **Có thể đọc claim chưa xác minh làm *hint* để chọn trong một danh sách chiến lược xác minh đã được máy chủ phê duyệt trước.** Việc lựa chọn này **không tạo principal, không tạo authorities, không cho truy cập API**.
- **Không được dùng claim chưa xác minh để cấp quyền, xác định tenant đã được chấp nhận, chọn URL khóa tùy ý hoặc bỏ qua bước kiểm tra chữ ký/issuer/audience.** Giá trị được tin cậy chỉ xuất hiện **sau khi token đã vượt toàn bộ xác thực cần thiết**.

Đây là chủ đề của bài **“Đọc claim chưa xác minh chỉ để chọn chiến lược, không để cấp quyền”**, thuộc chương **Nhiều tenant**. Bài đi từ mô hình tin cậy, kỹ thuật chọn decoder và cách cấu hình Spring Security Servlet/WebFlux đến các tình huống tấn công cross-tenant, kiểm thử và vận hành issuer registry.

> **Phạm vi:** OAuth 2.0 **access token** được Resource Server nhận qua `Authorization: Bearer ...`. OIDC **ID token** dùng cho OIDC client không đương nhiên được phép làm access token của API. Các URL, ID và tên tenant ở đây là ví dụ giả lập, không phải dịch vụ thật.

## 1. Vì sao Resource Server cần định tuyến xác thực?

Giả sử một API chung xử lý dữ liệu của ba tenant:

| Tenant | Trusted issuer | Resource audience |
|---|---|---|
| North | `https://login.example.test/realms/north` | `orders-api` |
| South | `https://login.example.test/realms/south` | `orders-api` |
| Partner | `https://identity.partner.test/tenant/acme` | `orders-api` |

Client gửi:

~~~http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Authorization: Bearer <JWT_ACCESS_TOKEN>
~~~

Resource Server không thể dùng *bất kỳ* public key nào trong hệ thống để chấp nhận mọi JWT. Nó cần biết token dự định đến từ issuer nào để:

1. Chọn **trusted JWKS/public key** tương ứng.
2. Chọn **đúng tập thuật toán JWS được phép**.
3. Kiểm tra claim `iss` có đúng issuer đã chọn.
4. Kiểm tra `aud`/`azp`/`client_id`/token type theo hợp đồng của issuer và Resource Server.
5. Chuyển những claims **đã xác minh** thành principal và authorities.
6. Kiểm tra tenant/resource ownership và quyền thao tác nghiệp vụ.

Một JWT ký JWS dạng compact thường có ba phần:

~~~text
BASE64URL(JOSE_HEADER).BASE64URL(JWT_CLAIMS).BASE64URL(JWS_SIGNATURE)
~~~

Payload thường dễ đọc bằng Base64URL decode. **Dễ đọc không có nghĩa đáng tin**: một attacker có thể tạo chuỗi có cấu trúc JWT và tự ghi:

~~~json
{
  "iss": "https://login.example.test/realms/north",
  "sub": "admin",
  "tenant_id": "north",
  "scope": "orders.read orders.delete",
  "aud": ["orders-api"]
}
~~~

mà không có khả năng ký token bằng khóa thật của issuer North. Trước bước xác minh chữ ký, cả `iss`, `sub`, `tenant_id`, `scope` và `aud` đều là **dữ liệu do người gửi kiểm soát**.

### 1.1. Điều được phép làm với `iss` chưa xác minh

~~~text
JWT chưa verified:
    iss = "https://login.example.test/realms/north"
              |
              v
Tìm EXACT issuer trong trusted registry do server kiểm soát
              |
       +------+------+
       |             |
    Không có       Có chính xác
       |             |
       v             v
     Từ chối      Chọn decoder North
                       |
                       v
               Xác minh JWS + claims
                       |
                +------+------+
                |             |
               Sai           Đúng
                |             |
                v             v
             Từ chối     Tạo Authentication
                           rồi phân quyền
~~~

**Tư duy đúng:** `iss` chưa xác minh là một **routing hint** tương tự việc đọc một nhãn trên một kiện hàng **trước khi** kiểm tra niêm phong. Nhãn giúp biết phải đưa kiện hàng tới bộ phận kiểm tra nào; nhãn **không chứng minh** nội dung kiện hàng đã được kiểm định.

### 1.2. Điều tuyệt đối không được làm

~~~text
JWT chưa verified:
    scope = "orders.delete"
    tenant_id = "north"
              |
              v
Tạo GrantedAuthority("SCOPE_orders.delete")   ← SAI
Tin user thuộc tenant north                 ← SAI
Cho qua GET/DELETE ở Orders API             ← SAI
~~~

Nếu hệ thống cấp quyền như vậy, attacker chỉ cần sửa payload, không cần có khóa của Authorization Server.

## 2. Phân biệt bốn mức độ tin cậy

Thay vì coi token là “đã tin” hoặc “chưa tin” một cách mơ hồ, hãy chia rõ các giai đoạn:

| Giai đoạn | Bên xử lý | Trạng thái dữ liệu | Có thể làm gì? |
|---|---|---|---|
| **T0: nhận chuỗi** | Bearer token resolver | Chuỗi HTTP header chưa tin | Kiểm tra giới hạn kích thước, định dạng Bearer, chuẩn bị authentication |
| **T1: parse sơ bộ** | Issuer/tenant strategy resolver | Claims/header **chưa verified** | Chọn **trong trusted allowlist** hoặc từ chối |
| **T2: xác minh** | `JwtDecoder` / `ReactiveJwtDecoder` | JWS + issuer/time/audience/profile được xác minh theo policy | Trả `Jwt` đã được xác minh hoặc lỗi |
| **T3: phân quyền** | Authentication converter, authorization managers, domain services | Principal/authorities từ kết quả xác minh | Cho phép/từ chối hành động trên endpoint và dữ liệu |

Lỗi bảo mật xuất hiện khi một ứng dụng đi tắt từ **T1 → T3**.

### 2.1. Parse không phải verify

Hai dòng code này mang ý nghĩa khác nhau:

~~~java
// Chỉ PARSE, chưa có bằng chứng token đáng tin.
var parsed = com.nimbusds.jwt.JWTParser.parse(token);
String issuerHint = parsed.getJWTClaimsSet().getIssuer();
~~~

~~~java
// VERIFY qua Spring Security decoder có key/validator tin cậy.
Jwt verifiedJwt = decoder.decode(token);
~~~

Ở WebFlux, `ReactiveJwtDecoder.decode(token)` trả `Mono<Jwt>` và phải được subscribe để thực sự chạy:

~~~java
Mono<Jwt> verifiedJwt = reactiveDecoder.decode(token);
~~~

Không được dựa vào `JWTParser` để làm claims validator thay thế JWS verification. `issuerHint` chỉ đủ để **tìm chiến lược**, không đủ để định danh user, tenant hoặc scope.

### 2.2. Mọi claim trước xác minh đều không đáng tin

| Claim/header chưa xác minh | Có thể dùng để chọn thứ gì? | Không được dùng để làm gì? |
|---|---|---|
| `iss` | Tra issuer trong registry đã phê duyệt | Kết luận issuer thực sự đã ký token |
| `kid` | Gợi ý chọn key **trong trusted JWKS** | Tự tải URL key do token cung cấp |
| `alg` | Dùng để xem có thuộc allowlist không | Cho token tự chọn thuật toán trust bất kỳ |
| `tenant_id` | Gợi ý lookup tenant **trong registry** nếu policy thiết kế như vậy | Khẳng định principal thuộc tenant hoặc có quyền đọc tenant |
| `aud` | Có thể hỗ trợ chọn trong cấu hình resource **đã tin cậy** nếu thực sự cần | Bỏ audience validation hoặc tin scope vì aud tự khai |
| `scope`, `roles` | **Không nên dùng cho security routing** thông thường | Tạo `GrantedAuthority` trước verification |
| `sub` | Không cần để chọn decoder | Tạo user identity trước verification |
| `jku`, `x5u` | Không nên cho phép quyết định URL tin cậy | Thực hiện outbound HTTP tới URL attacker chỉ định |

Ngay cả một claim trùng chính xác với giá trị trong trusted registry cũng **chưa phải kết quả xác minh**. Nó chỉ giúp tìm verifier đã được cấu hình. Nếu chữ ký của token sai thì vẫn phải bị từ chối.

## 3. Hai ranh giới: chọn chiến lược và xác minh bằng chiến lược

~~~mermaid
flowchart TD
    C["Client gửi Bearer JWT"] --> P["Parse tối thiểu iss chưa verified"]
    P --> A{"Iss có nằm trong trusted issuer registry?"}
    A -->|Không| X["Reject: không trust token"]
    A -->|Có| D["Chọn decoder được đăng ký cho issuer đó"]
    D --> V{"JWS + alg + iss + exp/nbf + aud + profile hợp lệ?"}
    V -->|Không| X
    V -->|Có| T["Jwt đã verified"]
    T --> M["Map authorities từ claims đã verified"]
    M --> B{"Tenant request có khớp tenant được xác nhận?"}
    B -->|Không| F["Deny: cross-tenant"]
    B -->|Có| R["HTTP/method/object authorization"]
    R --> O["Trả dữ liệu nếu có quyền"]
~~~

**Không có đường nối từ “parse `iss`” sang “map authorities”**. Tất cả quyền đi qua xác minh token và policy tenant.

### 3.1. Nếu attacker giả mạo `iss` của tenant North?

Ví dụ attacker tự tạo JWT với:

~~~json
{
  "iss": "https://login.example.test/realms/north",
  "tenant_id": "north",
  "scope": "orders.admin"
}
~~~

Resolver thấy `iss` trùng registry nên **chọn decoder North**. Nhưng attacker không có private key ký của North, vì vậy decoder từ chối JWS. Đây là hành vi **đúng**: cho phép một dữ liệu chưa tin cậy ảnh hưởng tới **lựa chọn bộ kiểm tra**, nhưng **không cho phép dữ liệu đó ảnh hưởng tới kết quả kiểm tra**.

### 3.2. Nếu attacker ghi `iss` thành một URL do họ sở hữu?

Ví dụ:

~~~json
{
  "iss": "https://attacker.example.test/issuer",
  "scope": "orders.admin"
}
~~~

Nếu hệ thống làm:

~~~java
// PHẢN VÍ DỤ: không tạo decoder từ URL issuer tùy ý.
JwtDecoder decoder = JwtDecoders.fromIssuerLocation(issuerHint);
return decoder.decode(token);
~~~

thì attacker có thể tự vận hành issuer và khóa ký của họ, từ đó cố khiến API chấp nhận token **không thuộc các issuer được cấp phép**. Ngoài ra URL tùy ý có thể gây **SSRF**, lạm dụng DNS/redirect, truy vấn endpoint nội bộ và tiêu hao connection pool.

**Chính sách đúng:** `issuerHint` phải được so khớp với issuer đã được **đăng ký/phê duyệt từ trước**. Không tự động tin issuer mới chỉ vì token tự khai báo một địa chỉ.

### 3.3. “Trusted registry” là gì?

Một registry tin cậy là cấu hình được **server-side kiểm soát**:

~~~text
https://login.example.test/realms/north
    → trusted JWKS: https://login.example.test/realms/north/jwks
    → allowed algorithms: RS256
    → accepted audience: orders-api
    → tenant binding: north

https://login.example.test/realms/south
    → trusted JWKS: https://login.example.test/realms/south/jwks
    → allowed algorithms: RS256
    → accepted audience: orders-api
    → tenant binding: south
~~~

Danh sách này được quản trị qua cấu hình, hệ quản trị tenant được bảo vệ hoặc quy trình onboarding có phê duyệt. Nó **không phải** một danh sách issuer được tự động “học” từ những JWT vừa đi qua API.

Khi thêm tenant/issuer mới, cần xác nhận metadata/trust, khóa, audience, token profile, ownership và lifecycle trước khi tenant được chuyển sang trạng thái active.

## 4. Ba mô hình multi-tenant cần phân biệt

Không phải mọi kiến trúc nhiều tenant đều cần đọc `iss` chưa xác minh để chọn decoder.

### 4.1. Mỗi tenant có một issuer riêng

~~~text
Tenant north → iss=https://login.example.test/realms/north
Tenant south → iss=https://login.example.test/realms/south
Tenant west  → iss=https://identity.partner.test/west
~~~

Đây là mô hình rõ nhất để dùng issuer resolver: **`iss` là routing hint**, từng issuer có trust configuration tương ứng. Sau khi decoder được chọn, JWT phải được kiểm tra **đúng issuer đó**.

Ví dụ JWT của North:

~~~json
{
  "iss": "https://login.example.test/realms/north",
  "sub": "user-123",
  "aud": ["orders-api"],
  "tenant_id": "north",
  "scope": "orders.read",
  "exp": 1933459200
}
~~~

Giá trị `exp` chỉ mang tính minh họa. Dù `tenant_id` là `north`, Resource Server vẫn phải so khớp tenant trong token **đã xác minh** với tenant mà request yêu cầu, và nếu cần so khớp cả ánh xạ issuer ↔ tenant.

### 4.2. Nhiều tenant dùng chung một issuer

~~~text
Tenant north ─┐
Tenant south ─┼── iss=https://login.example.test/company
Tenant west  ─┘
~~~

Trong trường hợp này, **`iss` không đủ để chọn chính sách tenant** vì mọi tenant dùng chung issuer và public keys. Có thể dùng cùng một decoder đã được cấu hình tin cậy rồi đọc claim `tenant_id` **sau xác minh**, kiểm tra tenant binding và quyền dữ liệu.

Nếu cần chọn một policy per-tenant trước decode bằng `tenant_id` chưa xác minh, policy phải vẫn là **một lựa chọn hạn chế trong trusted registry**, và final validation phải kiểm tra signed tenant claim phù hợp lựa chọn. Đừng biến `tenant_id` chưa xác minh thành quyền truy cập tenant đó.

### 4.3. Chọn tenant dựa trên đường dẫn/hostname

Ví dụ:

~~~http
GET /tenants/north/orders/42 HTTP/1.1
Host: api.example.test
Authorization: Bearer <JWT>
~~~

Path có thể quyết định **tenant đang được request**, nhưng **không chứng minh người gọi thuộc tenant đó**. Authentication vẫn phải xác minh token, còn authorization so khớp tenant request với identity đã xác minh.

Nếu dùng hostname như `north.api.example.test` làm tenant selector, cần cấu hình trusted host routing/gateway rõ ràng. Không được tin tùy tiện `Host` hoặc `X-Forwarded-Host` từ client như một bằng chứng quyền; forward headers chỉ đáng tin khi được proxy tin cậy chuẩn hóa.

### 4.4. Ma trận mô hình và trust boundary

| Kiến trúc | Dữ liệu có thể định tuyến trước verify | Bằng chứng phải có sau verify |
|---|---|---|
| Một issuer mỗi tenant | `iss` chưa xác minh để chọn decoder trong allowlist | Chữ ký đúng issuer, `aud`, thời gian, tenant binding |
| Một issuer cho mọi tenant | Thường không cần định tuyến bằng claim | Chữ ký issuer chung, `tenant_id` hợp lệ, quyền tenant |
| Tenant trong path | URL path để chọn application context | Token đã verified được phép truy cập tenant path |
| Tenant từ trusted reverse proxy | Context được gateway phê duyệt/kiểm soát | Token đã verified có binding với tenant context |
| Nhiều issuer + nhiều loại token | Hint phù hợp trust registry, hoặc endpoint/chain riêng | Mỗi profile được verifier riêng xác nhận đầy đủ |

**Đọc sơ bộ** là một công cụ điều phối. Nó không loại bỏ trách nhiệm **xác minh** và **phân quyền tenant** trong bất kỳ mô hình nào.

## 5. Ví dụ Spring Security Servlet: chỉ chấp nhận issuer đã tin cậy

Spring Security cung cấp `JwtIssuerAuthenticationManagerResolver` cho tình huống Resource Server chấp nhận JWT từ nhiều issuer. Thay vì tự đọc claim/parse token trong một filter tùy ý, có thể dùng resolver được framework cung cấp và tạo danh sách issuers tin cậy.

### 5.1. Dependencies

Ví dụ ứng dụng Spring Boot Servlet / Spring MVC:

~~~gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

JWT verification cũng cần thư viện JOSE phù hợp; starter Resource Server của các phiên bản Boot hiện đại thường kéo theo dependency cần thiết. Nếu tự khai báo modules, cần kiểm tra `spring-security-oauth2-jose` và phiên bản Nimbus tương thích.

### 5.2. Dùng `fromTrustedIssuers(...)`

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.resource.authentication.JwtIssuerAuthenticationManagerResolver;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class MultiIssuerServletSecurity {

    private static final String NORTH =
        "https://login.example.test/realms/north";
    private static final String SOUTH =
        "https://login.example.test/realms/south";

    @Bean
    JwtIssuerAuthenticationManagerResolver issuerResolver() {
        return JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(
            NORTH,
            SOUTH
        );
    }

    @Bean
    SecurityFilterChain apiSecurity(
            HttpSecurity http,
            JwtIssuerAuthenticationManagerResolver issuerResolver)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().denyAll()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.authenticationManagerResolver(issuerResolver))
            .build();
    }
}
~~~

Ví dụ dùng API `fromTrustedIssuers(...)` có trong các phiên bản Spring Security hiện đại; khi xây với phiên bản cũ, cần kiểm tra factory/constructor tương ứng thay vì sao chép tên method không có trong dependency đang dùng.

### 5.3. Trình tự hoạt động

Khi JWT từ client có `iss=NORTH`:

1. Resolver đọc issuer hint từ JWT **chưa được xác minh**.
2. Resolver kiểm tra issuer hint có nằm trong **hai issuer strings đã tin cậy** không.
3. Nếu không thuộc danh sách: từ chối authentication, **không gọi URL lạ**.
4. Nếu là North: chọn/tạo authentication manager và decoder cho issuer North.
5. Decoder dùng trust configuration của North để xác minh JWS và claims, bao gồm issuer tương ứng.
6. Nếu JWT thật sự do North phát hành và token validators đạt: tạo principal/authorities.
7. HTTP authorization kiểm tra `SCOPE_orders.read`, service tiếp tục kiểm tra tenant/object ownership.

`JwtIssuerAuthenticationManagerResolver` giải quyết vấn đề **chọn authentication manager**; nó không tự quyết định mọi chính sách audience, tenant ownership hoặc token profile riêng của API. Trong sản phẩm, phải bổ sung những kiểm tra này theo hợp đồng mỗi issuer.

### 5.4. Không gắn `JwtDecoder` toàn cục rồi giả định resolver dùng nó

Nếu ứng dụng vừa khai báo `@Bean JwtDecoder`, vừa dùng `authenticationManagerResolver(...)`, cần biết **authentication manager nào thực sự được resolver chọn**. Đừng mặc định validator đã gắn trên một decoder bean khác được mọi manager do resolver tạo ra sử dụng.

Ví dụ audience validator gắn vào bean decoder A sẽ **không tự truyền** đến decoder B được tạo bởi resolver. Vì vậy, khi muốn kiểm tra audience cho tất cả issuer, cần:

- Cấu hình validator trên **từng decoder/manager thực sự được resolver chọn**, hoặc
- Dùng một cơ chế kiểm tra dựa trên token **đã xác minh** và nằm trong pipeline authentication/authorization theo hợp đồng, **không** dựa vào claim chưa xác minh.

Phần tiếp theo minh họa cách xây các authentication manager theo registry, chủ động quản lý issuer/audience.

## 6. Ví dụ Servlet có registry decoder và audience validator riêng

Khi mỗi issuer có JWKS URI, thuật toán hoặc audience riêng, Resource Server có thể tạo một **map các authentication manager đã cấu hình trước**. Claim `iss` được parse sơ bộ **chỉ để tra map**; mỗi manager vẫn phải xác minh token.

### 6.1. Trước tiên, tạo manager cho một issuer tin cậy

~~~java
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationProvider;

final class IssuerManagers {

    static AuthenticationManager jwtManager(
            String issuer,
            String jwksUri,
            String requiredAudience) {

        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(jwksUri)
            .jwsAlgorithm(SignatureAlgorithm.RS256)
            .build();

        OAuth2TokenValidator<Jwt> audienceValidator = jwt ->
            jwt.getAudience().contains(requiredAudience)
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        "invalid_token",
                        "JWT audience not accepted",
                        null
                    )
                );

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(issuer),
                audienceValidator
            )
        );

        JwtAuthenticationProvider provider =
            new JwtAuthenticationProvider(decoder);

        return provider::authenticate;
    }
}
~~~

Ở đây:

- `issuer` và `jwksUri` phải được lấy từ **registry tin cậy**, không trực tiếp từ JWT.
- `SignatureAlgorithm.RS256` là allowlist minh họa; thuật toán thực tế phải theo token profile của issuer.
- `JwtValidators.createDefaultWithIssuer(...)` áp issuer và các kiểm tra mặc định về thời gian theo phiên bản.
- `audienceValidator` bảo đảm token được cấp cho `orders-api` hoặc audience được cấu hình.
- `setJwtValidator(...)` **thay** bộ validators hiện tại, nên phải ghép những validators cần thiết thay vì chỉ dùng audience.
- `JwtAuthenticationProvider` sẽ chỉ tạo `Authentication` khi decoder xác minh thành công.

Đây là thành phần Servlet, không phải WebFlux: `JwtAuthenticationProvider` và `AuthenticationManager` dạng đồng bộ.

### 6.2. Registry ánh xạ issuer → manager

~~~java
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationManager;

@Configuration
class TrustedIssuerManagerRegistry {

    @Bean
    Map<String, AuthenticationManager> trustedIssuerManagers() {
        return Map.of(
            "https://login.example.test/realms/north",
            IssuerManagers.jwtManager(
                "https://login.example.test/realms/north",
                "https://login.example.test/realms/north/jwks",
                "orders-api"
            ),
            "https://login.example.test/realms/south",
            IssuerManagers.jwtManager(
                "https://login.example.test/realms/south",
                "https://login.example.test/realms/south/jwks",
                "orders-api"
            )
        );
    }
}
~~~

Map này được xây từ **danh sách cố định do server sở hữu**. Không có mục “mọi issuer khác thì tự tạo decoder” và không có URL được lấy từ header/claims chưa xác minh.

Khi registry được quản lý từ database/onboarding service, yêu cầu vẫn giống hệt: **chỉ các record ACTIVE đã được duyệt** mới được làm nguồn trust; issuer record do client tự thêm hoặc chưa kiểm duyệt không được tham gia xác thực.

### 6.3. Cho resolver chỉ chọn manager đã đăng ký

Spring Security có các cơ chế resolver hỗ trợ lựa chọn theo issuer trong registry. Một dạng phổ biến theo các phiên bản hỗ trợ là:

~~~java
// Ý tưởng gắn registry làm nguồn manager cho từng issuer.
JwtIssuerAuthenticationManagerResolver resolver =
    new JwtIssuerAuthenticationManagerResolver(
        issuer -> trustedIssuerManagers.get(issuer)
    );
~~~

Đây là ví dụ về constructor nhận function/`AuthenticationManagerResolver<String>` được sử dụng ở một số phiên bản Spring Security. Hãy đối chiếu chữ ký constructor với dependency thực tế: các phiên bản mới ưu tiên factory `fromTrustedIssuers(...)` cho danh sách issuer; cách inject custom manager có thể dùng API tương đương hoặc giải pháp resolver riêng.

**Ranh giới bảo mật quan trọng không phụ thuộc tên factory:** nếu `trustedIssuerManagers.get(issuer)` không có entry, không được tự động tạo manager mới từ URL issuer bất kỳ. Không được trả về một manager mặc định chấp nhận tất cả token.

### 6.4. Không lấy `scope` chưa xác minh để chọn manager

Phản ví dụ:

~~~java
// PHẢN VÍ DỤ: token tự khai scope để chọn manager yếu hơn.
if (unverifiedClaims.getStringClaim("scope").contains("admin")) {
    return managerWithoutAudienceValidation;
}
return ordinaryManager;
~~~

Một attacker có thể tự ghi `scope=admin` để vào nhánh có policy yếu. Ngay cả khi cả hai nhánh vẫn verify chữ ký, việc chọn **một tập validators lỏng hơn dựa vào claim chưa xác minh** có thể gây rủi ro chênh lệch trust và token confusion. Nên định tuyến theo **trusted issuer/profile/endpoint policy**, sau đó áp đầy đủ validation và authorization.

## 7. Spring Security WebFlux: issuer resolver trong ứng dụng phản ứng

WebFlux không dùng `HttpSecurity`/`SecurityFilterChain` của Servlet. Nó dùng `ServerHttpSecurity`/`SecurityWebFilterChain`, `ReactiveAuthenticationManager` và `ReactiveJwtDecoder`. Nhưng quy tắc tin cậy vẫn như nhau: **routing hint chưa verified chỉ được chọn một manager đáng tin; manager thực sự verify rồi mới tạo authentication**.

### 7.1. Dependencies WebFlux

~~~gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

Không dùng các bean Servlet `SecurityFilterChain` thay thế cho `SecurityWebFilterChain` trong một reactive application. Khi dự án trộn Spring MVC và WebFlux starters, phải xác định rõ application type đang chạy để không kiểm thử nhầm pipeline.

### 7.2. `JwtIssuerReactiveAuthenticationManagerResolver`

Trong phiên bản Spring Security hỗ trợ factory `fromTrustedIssuers(...)`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.server.resource.authentication.JwtIssuerReactiveAuthenticationManagerResolver;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
class MultiIssuerReactiveSecurity {

    private static final String NORTH =
        "https://login.example.test/realms/north";
    private static final String SOUTH =
        "https://login.example.test/realms/south";

    @Bean
    JwtIssuerReactiveAuthenticationManagerResolver
    trustedReactiveIssuerResolver() {
        return JwtIssuerReactiveAuthenticationManagerResolver
            .fromTrustedIssuers(NORTH, SOUTH);
    }

    @Bean
    SecurityWebFilterChain api(
            ServerHttpSecurity http,
            JwtIssuerReactiveAuthenticationManagerResolver resolver) {

        return http
            .authorizeExchange(auth -> auth
                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyExchange().denyAll()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.authenticationManagerResolver(resolver))
            .build();
    }
}
~~~

Trong cấu hình này, resolver có thể đọc `iss` chưa verified để chọn **một trong hai issuer**. Nó không được cấp quyền chỉ vì có `iss=NORTH`. Mỗi manager phải xác minh JWT với issuer/key/validators tương ứng.

Tùy phiên bản Spring Security, constructor/factory của resolver reactive có thể khác; mục đích của đoạn code là dùng **API trusted-issuer**, không phải tự động tin một issuer bất kỳ được khai báo trong token. Nếu phiên bản không có factory tương ứng, triển khai resolver bằng trusted registry với cùng tính chất fail-closed.

### 7.3. Vì sao không `Mono.just(...)` từ claim chưa xác minh?

Phản ví dụ WebFlux:

~~~java
// PHẢN VÍ DỤ: tạo principal từ dữ liệu chưa verify.
return Mono.just(
    new UsernamePasswordAuthenticationToken(
        unverifiedClaims.getSubject(),
        token,
        List.of(new SimpleGrantedAuthority("SCOPE_orders.read"))
    )
);
~~~

`Mono` chỉ là một phương tiện biểu diễn kết quả bất đồng bộ. Việc dùng Reactor **không tự làm dữ liệu trở nên đáng tin**. Nếu `unverifiedClaims` chưa qua decoder, đoạn code vẫn cấp quyền sai dù nó chạy trong pipeline reactive.

### 7.4. Tạo reactive manager có audience validator riêng

Một helper minh họa:

~~~java
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.server.resource.authentication.JwtReactiveAuthenticationManager;

final class ReactiveIssuerManagers {

    static ReactiveAuthenticationManager create(
            String trustedIssuer,
            String trustedJwksUri,
            String requiredAudience) {

        NimbusReactiveJwtDecoder decoder =
            NimbusReactiveJwtDecoder
                .withJwkSetUri(trustedJwksUri)
                .jwsAlgorithm(SignatureAlgorithm.RS256)
                .build();

        OAuth2TokenValidator<Jwt> audience = jwt ->
            jwt.getAudience().contains(requiredAudience)
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        "invalid_token",
                        "Wrong resource audience",
                        null
                    )
                );

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(trustedIssuer),
                audience
            )
        );

        return new JwtReactiveAuthenticationManager(decoder);
    }
}
~~~

Với manager này, JWT do North phát hành **không thể tự nhận là South** và được chấp nhận qua decoder South chỉ bằng cách sửa `iss`, vì chữ ký và issuer/time/audience validators phải khớp trust configuration của South.

Nếu nhiều issuer có audience khác nhau, cấu hình mỗi manager với audience tương ứng. Nếu issuer phát hành access token theo profile riêng (như `typ=at+jwt`, `client_id`, `tenant_id` hoặc yêu cầu `exp` tồn tại), phải bổ sung validator tương ứng vào chính decoder của issuer đó.

### 7.5. Không block event loop chỉ để chọn issuer

Nếu trusted registry nằm trong database, không nên gọi JDBC blocking hoặc HTTP client đồng bộ trực tiếp trong Reactive issuer resolver trên event-loop. Có thể:

- Giữ một **snapshot registry trong memory** được cập nhật an toàn.
- Dùng một repository/client **reactive** cho dữ liệu registry khi cần.
- Nếu buộc có thao tác blocking, điều phối trên bounded scheduler đúng cách và giới hạn tải.

Nhưng cần nhớ: hiệu năng tốt không làm nới trust policy. Một cache registry chứa issuer **đã bị vô hiệu hóa** có thể ảnh hưởng authentication, nên cần cách invalidation/versioning và một ranh giới freshness phù hợp.

### 7.6. Một issuer với nhiều tenant trên WebFlux

Nếu tất cả tenant cùng một issuer, thông thường dùng một `ReactiveJwtDecoder` với issuer/audience validators, sau đó kiểm tra tenant sau authentication. Đừng tạo hàng trăm decoder dựa trên `tenant_id` chưa xác minh khi khóa và issuer đều giống nhau mà không có lý do thiết kế.

Một pattern service:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import reactor.core.publisher.Mono;

Mono<Boolean> tokenAllowsTenant(
        Authentication authentication,
        String requestedTenant) {

    if (!(authentication instanceof JwtAuthenticationToken jwtAuth)
            || !authentication.isAuthenticated()) {
        return Mono.just(false);
    }

    // Jwt ở đây đã do ReactiveJwtDecoder xác minh.
    String verifiedTenant =
        jwtAuth.getToken().getClaimAsString("tenant_id");

    return Mono.just(
        requestedTenant != null
            && requestedTenant.equals(verifiedTenant)
    );
}
~~~

Ví dụ method nhận `Authentication` **đã qua Spring Security authentication**. Nó minh họa tenant binding sau verify, không phải một authorization policy hoàn chỉnh: nếu principal có nhiều tenant hợp lệ, cần xử lý tenant membership bằng claims đã xác minh hoặc hệ thống quyền tin cậy; còn phải kiểm tra quyền trên bản ghi/order cụ thể.

Không lấy `authentication.getName()` rồi coi đó là tenant ID; `sub` và tenant là hai khái niệm khác nhau.

## 8. Chọn issuer chưa xác minh không được bỏ qua kiểm tra issuer sau đó

Giả sử resolver làm:

~~~text
unverified iss = north → chọn decoder North
~~~

Điều gì sẽ xảy ra nếu decoder North chỉ kiểm tra JWS signature mà không kiểm tra claim `iss`?

Trong một số kiến trúc nhiều issuer có **khóa được chia sẻ hoặc key trust sai phạm vi**, token ký bởi một issuer khác vẫn có thể vượt signature verification. Nếu không kiểm tra issuer **đã xác minh**, API có nguy cơ trộn token profiles.

### 8.1. Vì sao phải xác minh `iss` sau khi chọn decoder?

Trust policy tối thiểu nên là:

~~~text
issuer hint chọn North manager
AND JWT signature valid bằng trusted North keys
AND verified iss == configured North issuer
AND token time valid
AND aud/resource phù hợp Orders API
AND token type/profile phù hợp
~~~

Issuer hint chỉ là điều kiện chọn strategy, không thể thay thế điều kiện **verified issuer**.

### 8.2. Nếu hai issuer dùng chung key?

Một số môi trường có thể tái sử dụng cùng signing key ở nhiều realm/tenant. Điều này không được xem là lý tưởng cho mọi threat model, nhưng nếu tồn tại thì **signature verification riêng không phân biệt nguồn phát hành**. Resource Server phải kiểm tra issuer và token profile nghiêm ngặt, đồng thời tenant mapping sau verification.

Không kết luận “key đúng → token chắc thuộc North”. Một key là bằng chứng theo **phạm vi được cấu hình tin cậy**, còn claim issuer được xác minh phải phù hợp với phạm vi đó.

### 8.3. Audience và issuer là các điều kiện độc lập

Ví dụ:

~~~json
{
  "iss": "https://login.example.test/realms/north",
  "aud": ["billing-api"],
  "scope": "orders.read"
}
~~~

Token có issuer North, chữ ký và thời gian đúng nhưng audience là Billing API. **Orders API không được nhận token chỉ vì issuer đã được allowlist**. Cần kiểm tra resource audience và token type/profile theo hợp đồng.

### 8.4. Một route của South được gọi bằng token North

Request:

~~~http
GET /tenants/south/orders/42 HTTP/1.1
Authorization: Bearer <VALID_NORTH_ACCESS_TOKEN>
~~~

Sau khi token được xác minh bởi North decoder, nó có thể là một authentication **hợp lệ**. Nhưng yêu cầu truy cập tenant South phải bị từ chối nếu principal không có quyền South:

~~~text
Token: verified issuer=north, verified tenant=north
Request: tenant=south

Authentication: thành công đối với North JWT
Tenant authorization: từ chối cross-tenant
~~~

Đó là lý do **multi-tenant authorization** phải so khớp tenant ở đường dẫn/record với token **đã verified** và policy nghiệp vụ, thay vì giả định “token hợp lệ ở bất kỳ issuer tin cậy nào cũng được truy cập mọi tenant”.

## 9. Tenant binding phải xảy ra sau xác thực

Có ít nhất ba khái niệm khác nhau:

1. **Tenant được yêu cầu**: từ route, tên miền, request parameter hoặc resource record.
2. **Tenant được token xác nhận**: từ claim đã được decoder verify, hoặc từ issuer-to-tenant mapping đã được server tin cậy.
3. **Tenant mà principal có quyền truy cập**: được xác định theo identity, membership, role, consent và business policy.

Ba giá trị này không tự động bằng nhau. Một user có thể thuộc nhiều tenant, một issuer có thể phục vụ nhiều tenant, và một token có thể được phát hành theo policy không cho phép truy cập tenant yêu cầu.

### 9.1. Ví dụ Spring MVC: guard tenant sau authentication

Giả sử hợp đồng đơn giản: **mỗi issuer thuộc đúng một tenant** và JWT có claim `tenant_id` xác nhận lại tenant đó. Ta có thể định nghĩa guard:

~~~java
import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.stereotype.Component;

@Component("tenantAccess")
public class TenantAccess {

    private static final Map<String, String> TENANT_ISSUER = Map.of(
        "north", "https://login.example.test/realms/north",
        "south", "https://login.example.test/realms/south"
    );

    public boolean allowed(
            Authentication authentication,
            String requestedTenant) {

        if (!(authentication instanceof JwtAuthenticationToken jwtAuth)
                || !authentication.isAuthenticated()
                || requestedTenant == null) {
            return false;
        }

        Jwt verifiedJwt = jwtAuth.getToken();
        String expectedIssuer = TENANT_ISSUER.get(requestedTenant);
        String tokenTenant =
            verifiedJwt.getClaimAsString("tenant_id");

        return expectedIssuer != null
            && verifiedJwt.getIssuer() != null
            && expectedIssuer.equals(verifiedJwt.getIssuer().toString())
            && requestedTenant.equals(tokenTenant);
    }
}
~~~

`JwtAuthenticationToken` trong guard chỉ được tin nếu nó đến từ **Spring Security JWT authentication pipeline thật**, không phải một object mà client được phép tự tạo. Trong test chỉ dùng `Jwt.withTokenValue(...)` để test riêng guard logic thì phải ghi rõ đó **không phải test signature**.

### 9.2. Dùng method authorization

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@Configuration
@EnableMethodSecurity
class MethodSecurityConfiguration {}

@RestController
class TenantOrdersController {

    private final TenantOrderService orders;

    TenantOrdersController(TenantOrderService orders) {
        this.orders = orders;
    }

    @GetMapping("/tenants/{tenantId}/orders/{orderId}")
    @PreAuthorize(
        "hasAuthority('SCOPE_orders.read') and " +
        "@tenantAccess.allowed(authentication, #tenantId)"
    )
    OrderView get(
            @PathVariable String tenantId,
            @PathVariable String orderId) {

        return orders.loadForTenant(tenantId, orderId);
    }
}
~~~

Đây là mẫu **tách phần tenant permission và controller**, không phải class Java có thể chạy một mình vì `TenantOrderService` và `OrderView` là types của ứng dụng cần được triển khai. Việc gắn `@EnableMethodSecurity` phải phù hợp với cấu hình Servlet của dự án; với WebFlux sử dụng reactive method security tương ứng.

Quan trọng hơn, `orders.loadForTenant(tenantId, orderId)` phải truy vấn/kiểm tra **order thực sự thuộc tenant đó**, không chỉ dựa vào ID mà client gửi. Nếu domain service tìm order bằng ID toàn cục và trả ngay dữ liệu của tenant khác thì guard dựa trên URL có thể vẫn bị bypass ở tầng bản ghi.

### 9.3. Query phải giữ tenant trong điều kiện truy cập dữ liệu

Một cách suy nghĩ an toàn:

~~~sql
SELECT id, tenant_id, status, total
FROM orders
WHERE id = :orderId
  AND tenant_id = :verifiedTenantContext;
~~~

`:verifiedTenantContext` phải có căn cứ từ **authentication đã verified + policy user/tenant**. Nếu query chỉ dùng:

~~~sql
SELECT * FROM orders WHERE id = :orderId;
~~~

thì việc controller đã nhận `tenantId` ở URL không tự đảm bảo record thuộc tenant đó. Cần object-level authorization và các chính sách multi-tenant data isolation khác của hệ thống.

### 9.4. Nếu một user được phép vào nhiều tenant?

Không nên ép mọi ứng dụng vào quy tắc “token chỉ có đúng một `tenant_id`”. Nếu hợp đồng cho phép một principal truy cập nhiều tenant, cần xác định:

- Issuer/subject identity đã được verify.
- Claims membership/tenant list **đã ký và có thể kiểm tra**, hoặc một entitlement service đáng tin.
- Scope/role của principal **trong từng tenant**, không phải role toàn cục không hạn chế.
- Tenant nào request đang chọn và có phải là một trong các tenant được phép không.
- Quyền trên tài nguyên cụ thể và độ tươi của quyền nếu membership có thể thay đổi.

Phản ví dụ:

~~~text
Verified JWT:
  tenant_ids = ["north", "south"]
  global role = "ADMIN"

Sai:
  ADMIN có quyền với tất cả tenant bất kể context

Đúng:
  tenant request = south
  issuer/profile hợp lệ
  principal có membership/permission south
  action có scope/role hợp lệ trong south
  record thực sự thuộc south
~~~

Nếu hệ thống chỉ dùng một scope string `orders.read` mà không gắn tenant context, cần quyết định nó có nghĩa toàn cục hay chỉ trong tenant được token/resource xác nhận. Đừng suy ra quyền đa tenant từ một scope không có ngữ cảnh.

## 10. Định danh người dùng đa issuer: `sub` chưa đủ

Trong OAuth/OIDC, claim `sub` thường là subject identifier trong namespace của issuer. Hai Authorization Server khác nhau **có thể cấp cùng một giá trị `sub` cho hai người khác nhau**.

Ví dụ:

~~~text
Issuer North: iss=https://login.example.test/realms/north
              sub=123

Issuer South: iss=https://login.example.test/realms/south
              sub=123
~~~

Hai token này **không tự chứng minh là cùng một con người**. Nếu Resource Server xây khóa user chỉ từ `sub`, dữ liệu tenant có thể bị trộn.

### 10.1. Identity nên được hiểu trong namespace issuer

Một khóa identity cơ bản:

~~~text
IdentityKey = (verifiedIssuer, verifiedSubject)
~~~

Ví dụ:

~~~java
record PrincipalKey(String issuer, String subject) {}

PrincipalKey fromVerifiedJwt(Jwt jwt) {
    if (jwt.getIssuer() == null || jwt.getSubject() == null) {
        throw new IllegalArgumentException("Required identity claim missing");
    }
    return new PrincipalKey(
        jwt.getIssuer().toString(),
        jwt.getSubject()
    );
}
~~~

Đoạn method này **chỉ nhận Jwt đã được decoder xác minh** trong context đáng tin. Nó không phải lý do để lấy `iss`/`sub` từ raw JWT parser và tạo `PrincipalKey` trước authentication.

Trong hệ thống có identity federation hoặc account linking, việc liên kết nhiều issuer về cùng một account phải được thực hiện bằng **quy trình tin cậy riêng**, không chỉ bằng việc `sub`/email trùng nhau.

### 10.2. Không dùng email làm tenant identity mặc định

Một email trong JWT có thể đổi theo thời gian, không luôn được xác minh trong mọi issuer hoặc không ổn định như subject ID. Không mặc định:

~~~text
email=user@example.test
  → có quyền đối với tenant example
~~~

Mọi mapping email/domain → tenant/role phải do policy được phê duyệt xác định và dùng claims đã verify, không phải một heuristic lấy từ token chưa kiểm tra.

## 11. Thứ tự quyết định: authentication, tenant authorization, domain authorization

Một API bảo vệ nên đi qua ba cửa:

~~~mermaid
flowchart TD
    A["Request + Bearer token"] --> B["Routing hint chỉ để chọn trusted decoder"]
    B --> C{"Xác minh JWT thành công?"}
    C -->|Không| X["Reject authentication"]
    C -->|Có| D["Principal từ verified claims"]
    D --> E{"Principal được phép vào requested tenant?"}
    E -->|Không| Y["Deny tenant authorization"]
    E -->|Có| F{"Có scope/permission cho operation?"}
    F -->|Không| Y
    F -->|Có| G{"Resource thuộc tenant/owner được phép?"}
    G -->|Không| Y
    G -->|Có| H["Trả dữ liệu / thực hiện action"]
~~~

| Lớp | Câu hỏi | Dữ liệu được dùng |
|---|---|---|
| Routing | Verifier nào được phép kiểm tra token này? | Hint chưa verified + trusted registry |
| Authentication | Issuer/key/signature/claims có đáng tin không? | Decoder, validators, trusted keys |
| Tenant authorization | Identity có quyền trong tenant được yêu cầu không? | Verified claims + trusted membership/tenant policy |
| HTTP authorization | API operation đòi scope/role nào? | `GrantedAuthority` từ authenticated principal |
| Domain authorization | Record có thuộc tenant/subject được phép? | DB trusted resource ownership + identity đã verify |

Không được gộp hai hàng đầu thành kết luận “nếu tìm thấy decoder thì đã xác thực”. Một issuer thuộc registry chỉ có nghĩa hệ thống **biết cách kiểm tra token của issuer đó**, không có nghĩa mọi token tự ghi issuer đó đều hợp lệ.

### 11.1. Ví dụ phân loại lỗi

| Tình huống | Tầng thất bại | Kết quả thường gặp |
|---|---|---|
| `iss` không thuộc registry | Authentication routing | 401 |
| `iss` có trong registry nhưng JWS sai | Decoder authentication | 401 |
| JWT ký đúng nhưng `aud` sai | JWT validator authentication | 401 |
| JWT ký đúng, issuer/time đúng nhưng thiếu scope | HTTP authorization | 403 |
| JWT hợp lệ của North truy cập tenant South không được phép | Tenant authorization | 403 hoặc 404 theo API anti-enumeration policy |
| JWT có scope đúng nhưng order thuộc tenant khác | Domain/object authorization | Từ chối theo policy |
| JWKS endpoint không khả dụng và không có trusted cached key | Không thể xác minh | Không xác thực; HTTP status tùy lỗi hạ tầng |

**Không dùng mỗi status code để chứng minh chính xác verifier đã chạy**. Test cần kiểm tra đúng security chain và positive control tương ứng.

## 12. Nếu tự parse claim trước xác minh, phải giới hạn chặt

Spring Security có các issuer resolvers hỗ trợ phân tuyến. Nếu kiến trúc bắt buộc phải viết selector riêng, hãy coi nó là một thành phần **xử lý đầu vào chưa tin cậy ở trước authentication**.

### 12.1. Ví dụ selector chỉ tra trusted registry

Đoạn Java sau minh họa **chỉ bước chọn manager** cho một JWT compact JWS; nó không thay thế toàn bộ OAuth 2.0 Resource Server filter:

~~~java
import java.text.ParseException;
import java.util.Map;

import com.nimbusds.jwt.JWTParser;
import com.nimbusds.jwt.SignedJWT;

import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2Error;

final class TrustedIssuerChooser {

    private final Map<String, AuthenticationManager> managers;
    private static final int MAX_EXAMPLE_TOKEN_CHARS = 8192;

    TrustedIssuerChooser(
            Map<String, AuthenticationManager> trustedManagers) {
        this.managers = Map.copyOf(trustedManagers);
    }

    AuthenticationManager choose(String token) {
        if (token == null || token.isBlank()
                || token.length() > MAX_EXAMPLE_TOKEN_CHARS) {
            throw invalidToken();
        }

        try {
            // PARSE ONLY: chưa xác minh chữ ký!
            var jwt = JWTParser.parse(token);
            if (!(jwt instanceof SignedJWT signedJwt)) {
                throw invalidToken();
            }

            String issuerHint =
                signedJwt.getJWTClaimsSet().getIssuer();

            AuthenticationManager trusted =
                managers.get(issuerHint);
            if (trusted == null) {
                throw invalidToken();
            }

            // Không tạo Authentication từ unverified claims.
            return trusted;
        } catch (ParseException | IllegalArgumentException ex) {
            throw invalidToken();
        }
    }

    private static OAuth2AuthenticationException invalidToken() {
        return new OAuth2AuthenticationException(
            new OAuth2Error("invalid_token")
        );
    }
}
~~~

`managers` phải chứa các managers **đã được server đăng ký và cấu hình**. Sau khi chọn, Spring Security authentication pipeline phải truyền raw token tới manager đó để xác minh JWS và claims. Mã trên **không** phải một authentication provider và **không cấp quyền**.

Giới hạn `8192` là **tham số ví dụ**, không phải giới hạn chuẩn OAuth/JWT. Hệ thống phải chọn giới hạn theo kích thước token profile thực tế, proxy/web-server header limits, hiệu năng parse và risk policy. JWT rất lớn hoặc JSON đầu vào bất thường có thể chiếm CPU/memory trước xác minh; cần bounds ở gateway/server và parser.

### 12.2. Không có issuer trong registry thì từ chối ngay

~~~text
Token claim chưa verified:
    iss=https://unknown.example.test/issuer

Trusted manager registry:
    North → manager North
    South → manager South

Lookup = null → Reject
~~~

Không thêm fallback tự gọi `JwtDecoders.fromIssuerLocation(issuerHint)` khi map thiếu issuer. Một URL chưa được xác minh không được phép trở thành nguồn trust/khóa. Ngoài nguy cơ chấp nhận token của issuer do attacker kiểm soát, hành vi đó còn có thể tạo SSRF và key-cache resource exhaustion.

### 12.3. Parse lỗi phải fail closed

Các trường hợp cần từ chối:

- Chuỗi không phải JWT compact thuộc profile chấp nhận.
- Không parse được Base64URL/JSON/JOSE.
- `iss` vắng mặt, rỗng, sai kiểu hoặc không nằm trong allowlist.
- Token vượt giới hạn kích thước/hình dạng đầu vào.
- Token là JWE/opaque nhưng resolver hiện tại chỉ có hợp đồng cho JWS và chưa có strategy phù hợp.

Không dự đoán issuer từ `scope`/`email`/`sub` hoặc chấp nhận một manager “generic” dễ dãi khi không phân tuyến được.

### 12.4. Đối sánh issuer chính xác

Hai chuỗi sau không nhất thiết là cùng issuer:

~~~text
https://login.example.test/realms/north
https://login.example.test/realms/north/
~~~

Không tự bỏ dấu slash, sửa host, đổi path hoặc “gần giống là được” mà không theo issuer contract. Trusted registry, metadata discovery và claim `iss` sau verify phải nhất quán. Việc issuer thay đổi URI là thay đổi trust policy cần review.

### 12.5. Hạn chế thông tin leak từ lỗi selector

Không trả cho client danh sách issuer có trong registry hoặc JWKS endpoint nội bộ. Response Bearer authentication nên có thông tin đủ dùng nhưng không tiết lộ private configuration. Trong metrics, chỉ dùng issuer alias **đã match trusted registry**; không dùng raw issuer/token/subject chưa xác minh làm label.

## 13. Threat model: những tấn công khai thác claim chưa xác minh

### 13.1. Forged issuer và attacker-controlled JWKS

Một attacker có thể:

1. Tạo Authorization Server giả tại `https://evil.example.test`.
2. Công bố JWKS với public key của chính họ.
3. Ký JWT có `iss=https://evil.example.test`, `scope=orders.admin`.
4. Gửi Bearer JWT này tới Resource Server.

Nếu API tự discovery mọi issuer do token khai báo, nó có nguy cơ tự tin key của attacker. Chính sách an toàn:

~~~text
unverified iss = https://evil.example.test
    |
    v
trusted registry contains issuer?
    |
    +-- NO --> reject, không gọi discovery/JWKS
~~~

Một issuer hint tùy ý dùng làm URL HTTP còn có nguy cơ **Server-Side Request Forgery (SSRF)** tới metadata service, loopback, private network hoặc endpoints nội bộ. Các outbound JWKS/discovery requests chỉ được phép tới nguồn đã được phê duyệt; cần giới hạn kết nối, timeout và TLS trust.

### 13.2. Key confusion giữa issuer

Hai issuer có thể công bố một JWK với cùng `kid`, chẳng hạn `kid=key-1`. `kid` không phải namespace toàn cục và không tự chứng minh token thuộc issuer nào.

Trust phải được phân tách:

~~~text
Issuer North:
    JWKS North
    allowed algorithms North
    expected iss North

Issuer South:
    JWKS South
    allowed algorithms South
    expected iss South
~~~

Không dùng một cache keys không phân tách issuer rồi chọn public key tùy ý chỉ vì `kid` trùng. Cũng không kết luận JWS hợp lệ đồng nghĩa đúng issuer nếu nhiều tenant tái sử dụng cùng signing key; cần kiểm tra `iss` đã xác minh.

### 13.3. Role/scope escalation bằng payload tự sửa

~~~json
{
  "iss": "https://login.example.test/realms/north",
  "sub": "attacker",
  "scope": "orders.read orders.admin"
}
~~~

Nếu code tạo `SCOPE_orders.admin` từ raw JWT claims trước verify, attacker không cần private signing key để leo thang quyền. **Chỉ map authorities từ verified JWT** do decoder trả về, và chỉ trong trust scope issuer/profile đã được phép.

### 13.4. Tenant spoofing

Một attacker có thể ghi:

~~~json
{
  "iss": "https://login.example.test/realms/north",
  "tenant_id": "south",
  "scope": "orders.read"
}
~~~

`tenant_id=south` chưa verified chỉ là text do attacker cung cấp. Nếu token được ký thực sự bởi North với claim South, cũng **không tự có quyền South**: cần xác định North có thẩm quyền cấp membership tenant South không theo federation policy/issuer registry. Nhiều hệ thống chỉ cho issuer North cấp quyền North.

### 13.5. Token confusion: ID token thay access token

OIDC ID token có thể có issuer và JWS signature hợp lệ nhưng `aud` là client application, không phải Resource Server. Nếu API chỉ kiểm tra issuer/key mà bỏ audience và token profile, ID token có thể bị dùng sai mục đích.

~~~text
Required:
    signature valid
AND issuer trusted
AND aud contains expected Resource Server
AND token type/profile fits access token contract
AND time claims valid
AND operation has required scope/permission
~~~

Nếu token profile áp RFC 9068, có thể cần rule riêng cho `typ=at+jwt` và claims bắt buộc. Không mặc định mọi JWT cùng issuer đều là OAuth access token dành cho API.

### 13.6. Algorithm confusion

Không cho JWT tự chọn bất kỳ JWS `alg` theo header chưa verified:

~~~text
Trusted North decoder: RS256 only

Incoming alg=none        → reject
Incoming alg=HS256       → reject
Incoming RS256 wrong sig → reject
Incoming unsupported alg → reject
~~~

JOSE header chưa verified chỉ hỗ trợ tìm candidate key trong **bộ key/algorithms đã được server cho phép**. Không tự tải `jku`/`x5u` URL từ header và tin public key trả về.

### 13.7. Fallback từ verifier mạnh sang verifier yếu

~~~java
// PHẢN VÍ DỤ: JWT không verify được lại cho qua parser.
try {
    return signedJwtDecoder.decode(token);
} catch (Exception failure) {
    return insecureClaimsReader.createAuthentication(token);
}
~~~

Không được “thử mọi xác thực cho đến khi một cách chấp nhận”. Đường fallback nếu có phải là cơ chế tin cậy được thiết kế trước, không bỏ signature/audience/issuer validation; lỗi xác thực không được biến thành thành công.

### 13.8. DDoS bằng issuer ngẫu nhiên

Nếu mỗi `iss` mới tạo một decoder/JWKS HTTP client và được cache vĩnh viễn:

~~~text
iss=random-1...
iss=random-2...
...
iss=random-100000...
~~~

Attacker có thể làm đầy memory, connection pools và metadata cache. Allowlist issuer có số lượng kiểm soát giúp reject nhanh các issuer lạ. Với registry động, cần giới hạn số issuer hoạt động, TTL/cache eviction, concurrency, onboarding authorization và rate limiting.

### 13.9. Host/header spoofing

Nếu tenant được lấy từ `Host` hoặc `X-Forwarded-Host`, cần rõ trusted reverse proxy/gateway chịu trách nhiệm chuẩn hóa headers. Client có thể tự gửi:

~~~http
X-Forwarded-Host: south.api.example.test
~~~

Giá trị này không chứng minh caller có quyền vào tenant South. Chỉ dùng trusted routing context để chọn tenant, sau đó vẫn đối chiếu JWT đã verified và domain permissions.

### 13.10. Replay JWT đúng issuer nhưng sai resource

JWT của North có `aud=billing-api` và `scope=orders.read` không được Orders API chấp nhận chỉ vì có issuer North. Audience binding ngăn access token dành cho một API bị replay tới API khác. Đây là lỗi mà **issuer allowlist một mình không giải quyết**.

### 13.11. Leak dữ liệu bản ghi dù JWT đúng

Một JWT đã verified cho tenant North với `SCOPE_orders.read` vẫn không cấp quyền đọc order thuộc South. Cần truy vấn/kiểm tra owner/tenant tại domain layer và không dùng order ID do client gửi để bỏ qua isolation.

### 13.12. Log raw JWT/claims

Không ghi toàn bộ JWT, bearer header, unverified claims, JWK secrets hoặc full identity vào logs/traces. Ngay cả claim chưa verified cũng có thể chứa PII hoặc payload attacker chủ động tạo để làm bẩn logs. Dùng request ID, issuer alias trong registry và loại lỗi đã chuẩn hóa thay thế.

## 14. Chọn theo `iss`, tenant path hay strategy khác?

| Kiểu chọn | Dữ liệu nhận biết trước verify | Khi nào phù hợp? | Bằng chứng sau verify |
|---|---|---|---|
| Issuer resolver | `iss` chưa verified | Một endpoint nhận token của nhiều issuer | Chữ ký + `iss` + audience/token type + tenant policy |
| Path-based resolver | `/tenants/{id}/...` | API tách URL theo tenant | Chữ ký từ issuer đã map, tenant permission và resource ownership |
| Trusted host routing | Host được gateway phê duyệt | Dịch vụ có subdomain per tenant | JWT verified phù hợp tenant/host context |
| Một decoder chung | Không cần claim routing | Nhiều tenant cùng issuer/keys | Signed tenant claim và membership/authorization |
| Introspection resolver | Trusted endpoint/tenant context | Opaque tokens hoặc token profile đòi introspection | Response active và metadata từ endpoint tin cậy |

Trong hệ thống nhiều issuer, không nên dùng `kid` thay cho `iss` vì `kid` chỉ có nghĩa trong trust scope của JWKS. Nếu chọn strategy theo tenant path, nhớ rằng **path là yêu cầu của client**, không phải bằng chứng user thuộc tenant đó.

### 14.1. Lựa chọn dựa trên route cũng cần verify

~~~text
GET /tenants/south/orders
    → trusted route registry chọn verifier South
    → Bearer JWT do North ký
    → verifier South kiểm tra issuer/key
    → reject
~~~

Không phải vì URL chứa chữ “south” mà người gọi được cấp membership South. Nó chỉ chọn **bộ kiểm tra thích hợp**.

### 14.2. Với opaque token không có `iss` đọc được

Một opaque access token ngẫu nhiên thường không cung cấp issuer claim có thể parse trước verification. Do đó có thể chọn introspection endpoint từ trusted tenant route/host/client context hoặc từ một authorization gateway/service tin cậy, rồi gọi `OpaqueTokenIntrospector`.

Không thử mọi issuer introspection endpoint và chấp nhận endpoint nào trả `active=true` nếu không có hợp đồng rõ ràng; cách đó có thể tạo token confusion, SSRF, leak Bearer credentials và tăng tải. Việc xác minh token opaque vẫn phải dựa vào **trust policy đã biết**, không phải khả năng đoán định dạng token.

## 15. Kiểm thử ranh giới routing hint và authentication

Một bộ test đa tenant cần chứng minh **hai điều riêng biệt**:

1. Claim `iss` chưa verified chỉ được chọn **verifier trong registry**; issuer lạ phải bị từ chối trước khi discovery/JWKS request.
2. Verifier được chọn **thực sự kiểm tra chữ ký, issuer, audience, thời gian**; token đã verify vẫn phải qua tenant và domain authorization.

Nếu test chỉ dùng `mockJwt()`, `Jwt.withTokenValue(...)` hoặc mock `JwtDecoder` trả một principal tùy ý thì **không chứng minh chữ ký JWT được kiểm tra**. Test authentication phải dùng JWT có chữ ký thật bằng khóa thử nghiệm và decoder thật, qua HTTP Bearer filter chain hoặc unit test decoder trực tiếp.

### 15.1. Ma trận tình huống với North và South

Giả sử mỗi issuer có RSA key pair riêng và mỗi decoder yêu cầu `aud=orders-api`.

| Case | Token / request | Resolver chọn | Kết quả mong đợi |
|---|---|---|---|
| T01 | North JWT ký đúng, `iss=NORTH`, GET tenant North | North manager | 200 nếu đủ quyền |
| T02 | South JWT ký đúng, `iss=SOUTH`, GET tenant South | South manager | 200 nếu đủ quyền |
| T03 | JWT giả `iss=NORTH` nhưng ký bằng wrong key | North manager | **401** vì chữ ký |
| T04 | North signer ký JWT tự ghi `iss=SOUTH` | South manager | **401** vì không đạt South trust |
| T05 | JWT tự ghi `iss=https://evil.example.test` | Không manager | **401**; không gọi key URL của attacker |
| T06 | JWT không có `iss` | Không manager | **401** |
| T07 | JWT malformed | Không manager | **401** |
| T08 | North JWT ký đúng, `aud=billing-api` | North manager | **401** vì audience |
| T09 | North JWT đúng key nhưng `exp` đã hết hạn | North manager | **401** vì thời gian |
| T10 | North JWT hợp lệ, chỉ có `scope=orders.create` | North manager | **403** vì thiếu scope đọc |
| T11 | North JWT hợp lệ, GET tenant South | North manager | **403/404** theo tenant policy |
| T12 | JWT đúng tenant path, truy cập order thuộc tenant khác | Manager đúng issuer | Từ chối ở domain layer |
| T13 | JWT bị đổi `tenant_id` sau khi ký | Manager theo `iss` | **401** do signature mismatch |
| T14 | Issuer bị vô hiệu hóa trong trusted registry | Không manager | **401** dù token cũ ký đúng |
| T15 | Request không có Bearer token | Không auth | **401** trên protected API |

Đây là những HTTP statuses thông thường, có thể thay đổi theo entry point, security chain và anti-enumeration policy. Kiểm chứng quan trọng hơn mã lỗi là **không principal/authority nào được tạo từ claims chưa verify** và **không token nào thuộc issuer khác được vượt trust policy**.

### 15.2. Mỗi negative case chỉ thay một điều kiện

Một JWT vừa sai signature, issuer, audience và expiry có thể bị từ chối ngay ở bước đầu tiên; HTTP 401 **không chứng minh từng validator**. Để test riêng audience, hãy ký JWT bằng **private key đúng**, dùng issuer/time/scope hợp lệ và chỉ thay `aud`.

Để test issuer validator, cần JWT có signature mà decoder test có thể xác minh, rồi kiểm tra `iss` không đúng issuer đã cấu hình. Nếu North và South dùng hai keys khác nhau, test “North signer nhưng `iss=SOUTH`” chủ yếu chứng minh **khóa/manager isolation**; nó không tự chứng minh issuer validator của South hoạt động vì signature đã fail trước.

### 15.3. Kiểm chứng không outbound tới issuer lạ

Giả sử registry chỉ có:

~~~text
NORTH → trusted JWKS North
SOUTH → trusted JWKS South
~~~

JWT có `iss=https://evil.example.test` phải bị reject **trước** khi có network request đến URL đó. Trong integration test có thể dùng HTTP mock server/network interceptor để xác nhận **không có request discovery/JWKS tới một domain không nằm trong allowlist**. Chỉ assert 401 là chưa đủ để chứng minh không xảy ra SSRF attempt trước khi lỗi.

### 15.4. Tenant binding sau authentication

~~~text
JWT A:
    verified issuer = North
    verified tenant_id = north
    verified scope = orders.read
Request:
    GET /tenants/south/orders
Expected:
    deny South

JWT B:
    verified issuer = South
    verified tenant_id = south
    verified scope = orders.read
Request:
    GET /tenants/south/orders
Expected:
    allow khi đủ quyền domain
~~~

Nếu strategy chọn decoder theo `iss`, JWT A có thể **authentication thành công** rồi **tenant authorization từ chối**. Nếu API chọn decoder bằng path South, JWT A có thể bị **authentication từ chối** bởi verifier South. Hai thiết kế khác nhau nhưng cả hai đều phải chặn cross-tenant access.

### 15.5. Test một issuer dùng chung cho nhiều tenant

Với issuer chung:

~~~text
Issuer = https://login.example.test/company
Signed JWT tenant_id=north
Request tenant_id=south
~~~

Đây không phải lỗi decoder: chữ ký/issuer/audience có thể hợp lệ. Kết quả phải bị từ chối **ở tenant authorization**. Ngoài ra cần test user có membership nhiều tenant theo policy, scope có tenant context và object ownership.

## 16. JUnit test: token giả issuer hint nhưng không qua chữ ký

Ví dụ tiếp theo kiểm tra ranh giới **issuer selector → JWT authentication manager** trực tiếp. Nó sử dụng `TrustedIssuerChooser` ở mục 12, manager xây bằng `NimbusJwtDecoder` thật và RSA key pairs riêng cho hai issuer. Đây là **unit/integration test tại authentication provider**, không phải HTTP filter-chain test; HTTP integration cần thêm `MockMvc`/`WebTestClient` ở tầng ứng dụng.

### 16.1. Test fixture ký JWT bằng khóa thử nghiệm

~~~java
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;
import java.time.Instant;
import java.util.Date;
import java.util.List;
import java.util.Map;

import com.nimbusds.jose.JOSEObjectType;
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.JWSHeader;
import com.nimbusds.jose.crypto.RSASSASigner;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.SignedJWT;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.server.resource.authentication.BearerTokenAuthenticationToken;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class UnverifiedIssuerHintTest {

    static final String NORTH =
        "https://login.example.test/realms/north";
    static final String SOUTH =
        "https://login.example.test/realms/south";

    KeyPair northKeys;
    KeyPair southKeys;
    TrustedIssuerChooser chooser;

    @BeforeEach
    void setUp() throws Exception {
        KeyPairGenerator generator =
            KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);

        northKeys = generator.generateKeyPair();
        southKeys = generator.generateKeyPair();

        Map<String, AuthenticationManager> managers = Map.of(
            NORTH, IssuerManagers.jwtManagerWithPublicKeyForTest(
                (RSAPublicKey) northKeys.getPublic(), NORTH, "orders-api"),
            SOUTH, IssuerManagers.jwtManagerWithPublicKeyForTest(
                (RSAPublicKey) southKeys.getPublic(), SOUTH, "orders-api")
        );
        chooser = new TrustedIssuerChooser(managers);
    }

    private String signedToken(
            KeyPair keyPair,
            String issuer,
            String tenant,
            String audience,
            String scope) throws Exception {

        Instant now = Instant.now();

        JWTClaimsSet claims = new JWTClaimsSet.Builder()
            .issuer(issuer)
            .subject("test-user")
            .audience(List.of(audience))
            .claim("tenant_id", tenant)
            .claim("scope", scope)
            .issueTime(Date.from(now.minusSeconds(30)))
            .expirationTime(Date.from(now.plusSeconds(300)))
            .build();

        SignedJWT jwt = new SignedJWT(
            new JWSHeader.Builder(JWSAlgorithm.RS256)
                .type(JOSEObjectType.JWT)
                .keyID("test-key")
                .build(),
            claims
        );

        jwt.sign(new RSASSASigner(
            (RSAPrivateKey) keyPair.getPrivate()));
        return jwt.serialize();
    }

    private Authentication authenticate(String token) {
        AuthenticationManager selected = chooser.choose(token);
        return selected.authenticate(
            new BearerTokenAuthenticationToken(token));
    }

    @Test
    void validNorthJwtIsAuthenticated() throws Exception {
        String token = signedToken(
            northKeys, NORTH, "north", "orders-api", "orders.read");

        Authentication result = authenticate(token);
        assertThat(result).isInstanceOf(JwtAuthenticationToken.class);
        assertThat(result.isAuthenticated()).isTrue();
        assertThat(result.getAuthorities())
            .extracting("authority")
            .contains("SCOPE_orders.read");
    }

    @Test
    void forgedNorthHintWithUntrustedSignerIsRejected()
            throws Exception {
        // Token nói iss=NORTH nhưng được ký bằng SOUTH private key.
        String token = signedToken(
            southKeys, NORTH, "north", "orders-api", "orders.read");

        assertThatThrownBy(() -> authenticate(token))
            .isInstanceOf(OAuth2AuthenticationException.class);
    }

    @Test
    void northSignerCannotImpersonateSouthIssuer()
            throws Exception {
        String token = signedToken(
            northKeys, SOUTH, "south", "orders-api", "orders.read");

        assertThatThrownBy(() -> authenticate(token))
            .isInstanceOf(OAuth2AuthenticationException.class);
    }

    @Test
    void unknownIssuerHintDoesNotSelectManager()
            throws Exception {
        String token = signedToken(
            northKeys,
            "https://evil.example.test/issuer",
            "north",
            "orders-api",
            "orders.read");

        assertThatThrownBy(() -> chooser.choose(token))
            .isInstanceOf(OAuth2AuthenticationException.class);
    }

    @Test
    void wrongAudienceIsRejectedEvenWithTrustedSigner()
            throws Exception {
        String token = signedToken(
            northKeys, NORTH, "north", "billing-api", "orders.read");

        assertThatThrownBy(() -> authenticate(token))
            .isInstanceOf(OAuth2AuthenticationException.class);
    }
}
~~~

Để các tests trên có phương thức hỗ trợ `jwtManagerWithPublicKeyForTest(...)`, thêm helper **chỉ dùng trong test**:

~~~java
import java.security.interfaces.RSAPublicKey;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationProvider;

// Có thể đặt trong class helper IssuerManagers ở phần 6.
static AuthenticationManager jwtManagerWithPublicKeyForTest(
        RSAPublicKey publicKey,
        String expectedIssuer,
        String expectedAudience) {

    NimbusJwtDecoder decoder = NimbusJwtDecoder
        .withPublicKey(publicKey)
        .signatureAlgorithm(SignatureAlgorithm.RS256)
        .build();

    OAuth2TokenValidator<Jwt> audienceValidator = jwt ->
        jwt.getAudience().contains(expectedAudience)
            ? OAuth2TokenValidatorResult.success()
            : OAuth2TokenValidatorResult.failure(
                new OAuth2Error(
                    "invalid_token",
                    "JWT audience not accepted",
                    null
                )
            );

    decoder.setJwtValidator(
        new DelegatingOAuth2TokenValidator<>(
            JwtValidators.createDefaultWithIssuer(expectedIssuer),
            audienceValidator
        )
    );

    return new JwtAuthenticationProvider(decoder)::authenticate;
}
~~~

Đây là **method bổ sung vào class helper**; nếu copy thành một file Java riêng thì phải bọc method trong class phù hợp. Trong production, các khóa tin cậy có thể đến từ HTTPS JWKS; test dùng public keys tĩnh để cô lập verification khỏi network.

### 16.2. Điều mà test thực sự chứng minh

Khi `chooser.choose(token)` thấy `iss=NORTH`, nó có thể trả manager North **trước khi xác minh chữ ký**. Nhưng test `forgedNorthHintWithUntrustedSignerIsRejected` chứng minh bước tiếp theo vẫn bắt buộc:

~~~text
Token signed by South private key
JWT payload iss=NORTH
      |
      v
Chooser selects North manager
      |
      v
North NimbusJwtDecoder verifies using North public key
      |
      v
Signature invalid → Authentication fails
~~~

Đây chính là **sự khác nhau giữa chọn chiến lược và cấp quyền**. Tương tự, token đã ký đúng North key nhưng sai audience vẫn phải bị từ chối.

### 16.3. Những điều test chưa chứng minh

Các test này chưa gọi:

- HTTP `BearerTokenAuthenticationFilter` hoặc `AuthorizationFilter`.
- Controller `/tenants/{tenantId}/orders`.
- Truy vấn object ownership trong database.
- JWKS HTTP discovery/rotation.
- Reverse proxy host/path routing.

Do đó nên bổ sung **HTTP integration tests** và domain authorization tests tương ứng. Không kết luận từ một unit test selector rằng cả API nhiều tenant đã an toàn.

### 16.4. Test nào nên thêm cho HTTP chain?

Ví dụ `MockMvc`:

~~~java
// JWT được ký THẬT bằng RSA private key thử nghiệm.
mockMvc.perform(
        get("/tenants/north/orders/42")
            .header("Authorization", "Bearer " + validNorthJwt))
    .andExpect(status().isOk());

mockMvc.perform(
        get("/tenants/north/orders/42")
            .header("Authorization", "Bearer " + forgedNorthJwt))
    .andExpect(status().isUnauthorized());

mockMvc.perform(
        get("/tenants/south/orders/42")
            .header("Authorization", "Bearer " + validNorthJwt))
    .andExpect(status().isForbidden());
~~~

Đây là **test outline**, giả định controller thực tồn tại, security chain chứa resolver thật, test data/service có record được phép cho case đầu và tenant guard từ mục 9. Kết quả case South có thể là 404 nếu anti-enumeration policy che sự tồn tại resource. Không gắn `jwt()` request post-processor của Spring Security Test nếu mục tiêu là xác minh RSA signature thật; post-processor đó mô phỏng authentication và có thể bỏ qua decoder.

### 16.5. WebFlux test phải dùng `WebTestClient` thật

Trong reactive application, cách tiếp cận tương tự:

~~~java
webTestClient.get()
    .uri("/tenants/north/orders/42")
    .headers(headers -> headers.setBearerAuth(validNorthJwt))
    .exchange()
    .expectStatus().isOk();

webTestClient.get()
    .uri("/tenants/north/orders/42")
    .headers(headers -> headers.setBearerAuth(forgedNorthJwt))
    .exchange()
    .expectStatus().isUnauthorized();
~~~

Đảm bảo WebFlux test context dùng `JwtIssuerReactiveAuthenticationManagerResolver` và **NimbusReactiveJwtDecoder thật**, không `mockJwt()`. Có thể kiểm tra riêng `Mono<Jwt>` của decoder bằng `StepVerifier` để tách cryptographic validation khỏi HTTP wiring.

## 17. Vận hành trusted issuer registry

Trusted issuer registry là **ranh giới tin cậy** giữa unverified claim và một verifier được phép sử dụng. Dù lưu bằng file cấu hình hay database, nó phải được quản trị như **security configuration**, không phải một tùy chọn người dùng tự khai.

### 17.1. Quy trình onboarding issuer

~~~mermaid
flowchart TD
    A["Tenant đề nghị onboarding"] --> B["Xác thực quyền quản trị tenant"]
    B --> C["Phê duyệt issuer URL và ownership"]
    C --> D["Thẩm định metadata, TLS, JWKS, allowed algorithms"]
    D --> E["Định nghĩa audience, scopes, token profile, tenant mapping"]
    E --> F["Kiểm thử token hợp lệ và không hợp lệ"]
    F --> G["Chuyển issuer sang ACTIVE"]
    G --> H["Giám sát khóa, metadata, lỗi và offboarding"]
~~~

Một user chỉ gửi `https://my-new-idp.example.test` không đủ để API tự thêm issuer đó vào allowlist. Việc người đó tự vận hành IdP và ký JWT đúng bằng khóa của họ **không phải bằng chứng doanh nghiệp đã chấp nhận tin IdP đó**.

### 17.2. Registry record cần thể hiện policy

~~~yaml
tenantId: north
status: ACTIVE
issuer: https://login.example.test/realms/north
jwksUri: https://login.example.test/realms/north/jwks
allowedJwsAlgorithms:
  - RS256
requiredAudiences:
  - orders-api
acceptedTokenProfile: access-token
authoritiesClaim: scope
authoritiesPrefix: SCOPE_
approval: security-reviewed
~~~

Đây là **schema ứng dụng minh họa**, không phải properties Spring Boot mặc định. Mỗi record phải được kiểm soát thay đổi và chỉ được kích hoạt khi có phê duyệt/verification theo chính sách.

### 17.3. Các trạng thái có thể dùng

| Trạng thái | Ý nghĩa | Được chọn ở production? |
|---|---|---|
| `PENDING` | Chưa phê duyệt | Không |
| `TESTING` | Chỉ được thử trong môi trường có kiểm soát | Không |
| `ACTIVE` | Issuer đã được xác minh và cho phép | Có |
| `SUSPENDED` | Tạm ngừng tin vì sự cố hoặc policy | Không |
| `RETIRED` | Ngừng hợp tác/hết lifecycle | Không |

Không tự chuyển `PENDING` thành `ACTIVE` sau khi nhận được JWT có signature hợp lệ từ chính issuer đó. Chữ ký chỉ chứng minh token được ký bằng một key, không chứng minh server chủ động tin issuer.

### 17.4. Gỡ issuer khi token còn hạn

Nếu tenant bị suspended, vẫn có thể tồn tại JWT `exp` chưa hết. Muốn dừng chấp nhận issuer đó, Resource Server phải cập nhật registry và cache manager/decoder theo freshness policy:

- Cập nhật registry version hoặc snapshot atomically.
- Có invalidation/refresh trên từng instance.
- Không giữ manager trusted vô hạn sau khi registry đã ngừng issuer.
- Có metric trạng thái đồng bộ và khả năng phát hiện instance lag.
- Test JWT ký đúng nhưng issuer đã chuyển sang `SUSPENDED`.

**Thay đổi trust registry** khác với **key rotation**: một issuer có thể vẫn trusted khi public keys đổi, hoặc bị suspended dù public key của nó vẫn hợp lệ.

### 17.5. Lazy discovery có trade-off vận hành

Một resolver có thể tạo decoder lần đầu khi nhận JWT có `iss` trusted:

~~~text
first JWT for North
   → issuer North có trong allowlist
   → create/retrieve North manager
   → discovery/JWKS fetch khi cần
   → JWS + claims verification
~~~

Điều này giảm yêu cầu mọi issuer phải sẵn sàng khi startup, nhưng có thể tăng độ trễ request đầu tiên. Nên đặt timeout, concurrency limits, bounded caches, quan sát first-request latency, và không tạo nhiều managers cho cùng issuer khi traffic đồng thời.

Nếu discovery/JWKS tạm outage và không có trusted cached key thì **không thể xác minh token**, không được lấy việc issuer có trong registry làm lý do tạm chấp nhận.

### 17.6. JWKS/discovery URL phải nằm trong trust policy

Trusted issuer URI không phải giấy phép gửi HTTP tới mọi URL mà một JWT chưa verified tự khai. Metadata retrieval cần TLS, trusted egress, chính sách redirect và giới hạn request. Với issuer partner bên ngoài, có thể cần allowlist/pinning JWKS URI theo hợp đồng bảo mật.

## 18. Cache và đồng bộ issuer managers không làm lỏng xác minh

Một Resource Server có nhiều tenant có thể cache:

- Trusted issuer registry snapshot.
- Decoder/authentication manager per issuer.
- JWK Sets/public keys.
- Issuer metadata/discovery response.
- Một số policy về audience, token type và scope mapping.

Cần phân biệt cache **cấu hình tin cậy** với cache **dữ liệu chưa xác minh**.

### 18.1. Cache chỉ sau khi issuer thuộc allowlist

~~~text
ĐÚNG:
    unverified issuer hint
       → trusted registry lookup
       → issuer ACTIVE?
       → create/reuse approved decoder

SAI:
    every unique unverified iss
       → create decoder / HTTP client
       → cache forever
~~~

Nếu cache mọi `iss` ngẫu nhiên, một attacker có thể tạo hàng trăm nghìn keys làm đầy memory, connection pools và metadata caches. Chỉ issuer **đã được phê duyệt và còn ACTIVE** mới được tạo manager, với giới hạn cardinality và concurrency phù hợp.

### 18.2. Cache keys khác với cache authentication

~~~text
JWKS/public-key cache:
    vẫn verify JWS signature của JWT mới

Authentication cache:
    có thể reuse principal của một token đã xác minh
    cần lifecycle, expiry, revocation, sender-binding policy riêng
~~~

Một decoder dùng trusted cached public key **không bỏ qua signature verification**. Nhưng cache `Authentication` theo `sub` hay issuer hint chưa verified có thể tạo lỗi quyền nghiêm trọng. Nếu thiết kế authentication caching, cache key phải dựa trên token/verified identity và có kiểm soát expiry, audience, revocation và ngữ cảnh tenant.

### 18.3. Issuer suspended trong khi snapshot vẫn cũ

Một registry snapshot không được cập nhật có thể khiến API tiếp tục tin issuer đã bị ngừng. Cần có ranh giới freshness của trust registry: polling có TTL, push invalidation, version check hoặc một phương án đồng bộ phù hợp.

Nếu policy buộc dừng issuer gần thời gian thực, hệ thống phải có kế hoạch khi một instance không thể tải registry mới. Không được tự dùng cấu hình cũ vô hạn khi nguồn tin cậy đã có thể bị thu hồi.

### 18.4. Khả năng cô lập lỗi theo issuer

Nếu South JWKS trả 503 trong khi North khỏe:

~~~text
North → trusted cached key available → verify North JWT bình thường
South → no trusted key available      → fail closed for South
~~~

Một sự cố South không nhất thiết cần làm toàn API North ngừng xác thực. Có thể tách pools, timeouts và circuit breaker theo issuer alias/endpoint tin cậy. Nhưng không dùng issuer URL chưa verified từ JWT làm metric label vô hạn hoặc làm nguồn SSRF khi điều tra.

### 18.5. Quyền quản trị registry

Các hành động như thêm issuer, đổi `jwksUri`, cho phép HS256, bỏ audience validator hoặc ánh xạ scope admin có thể mở rộng tập token được API tin. Chúng cần phân quyền, audit và approval phù hợp; không để một tenant admin không đủ thẩm quyền tự sửa trust policy chung của các tenant khác.

## 19. Tình huống tấn công theo từng bước

Giả sử attacker là user hợp lệ của South và muốn đọc Orders của North. Attacker có JWT ký hợp lệ:

~~~json
{
  "iss": "https://login.example.test/realms/south",
  "sub": "user-777",
  "tenant_id": "south",
  "aud": ["orders-api"],
  "scope": "orders.read"
}
~~~

### 19.1. Sửa claim issuer/tenant nhưng giữ chữ ký

Attacker sửa payload:

~~~json
{
  "iss": "https://login.example.test/realms/north",
  "sub": "user-777",
  "tenant_id": "north",
  "aud": ["orders-api"],
  "scope": "orders.read"
}
~~~

nhưng vẫn dùng JWS signature cũ.

~~~text
Unverified iss=NORTH
    → resolver chọn North manager
    → North decoder verify JWS
    → signature mismatch
    → từ chối authentication
~~~

Việc resolver đã chọn North **không cấp quyền North**; chỉ là đã chọn bộ kiểm tra đúng theo hint.

### 19.2. Giữ JWT South hợp lệ, đổi URL North

~~~http
GET /tenants/north/orders/42
Authorization: Bearer <VALID_SOUTH_JWT>
~~~

Theo kiến trúc chọn decoder bằng `iss`:

~~~text
Unverified iss=SOUTH
    → resolver chọn South manager
    → South decoder verify JWS/claims thành công
    → identity = (South issuer, user-777)
    → requested tenant = north
    → tenant authorization từ chối
~~~

JWT **có thể hợp lệ ở authentication**, nhưng người gọi vẫn không có quyền tenant North. Nếu API chọn decoder bằng tenant path, request có thể bị North decoder từ chối ở authentication. Hai lựa chọn đều phải ngăn việc đọc dữ liệu North.

### 19.3. Tự dựng issuer mới và khóa riêng

~~~text
Attacker owns evil.example.test
JWT iss=https://evil.example.test
JWT signed using attacker's own private key
    → issuer not in trusted registry
    → reject before discovery/JWKS
~~~

Không “tiện tay hỗ trợ multi-issuer” bằng cách tạo decoder từ mọi URL do Bearer JWT khai báo.

### 19.4. Có token North thật nhưng order thuộc South

Ngay cả khi attacker được cấp một JWT North thật với `SCOPE_orders.read`, record `orderId=42` thuộc South vẫn phải được chặn ở domain layer. Kiểm tra issuer/tenant tại authentication không thay thế query tenant isolation và object ownership.

**Kết quả thiết kế đúng:** token chỉ cung cấp *gợi ý chọn verifier* trước khi xác minh; **quyền truy cập chỉ được quyết định từ verified identity, verified permissions và tenant/domain policy**.

## 20. Những sai lầm triển khai thường gặp

### 20.1. “Đọc `iss` từ JWT rồi tạo decoder tức là đã xác minh”

Sai. `JWTParser.parse(...)` chỉ đọc nội dung do client cung cấp. Việc chọn decoder là **bước chuẩn bị**, decoder còn phải verify signature, issuer, audience, token type, expiry và claims bắt buộc. Một JWT tự ghi `iss=NORTH` có thể được **đưa tới North decoder** nhưng vẫn phải bị từ chối khi signature không hợp lệ.

### 20.2. “Nếu issuer có URL hợp lệ thì cứ discovery”

Sai. Bất kỳ attacker nào cũng có thể vận hành một HTTPS issuer với JWKS do họ kiểm soát. Chỉ issuer **đã có trong trusted registry** mới được phép tham gia authentication. URL trông hợp lệ không phải điều kiện đủ; gọi bất kỳ URL nào còn tăng nguy cơ SSRF.

### 20.3. “Chữ ký đúng thì không cần so khớp issuer”

Sai. Một số hệ thống có key reuse, key cache cấu hình sai hoặc nhiều token profiles dùng cùng keys. Phải kiểm tra `iss` đã verified bằng validator gắn trên decoder tương ứng. Key selection không thay thế issuer validation.

### 20.4. “Issuer đúng thì không cần audience”

Sai. Cùng một issuer có thể phát hành token cho Billing, Orders và Admin APIs. JWT dành cho Billing không được Orders API chấp nhận chỉ vì cùng signer. Phải kiểm tra `aud`/resource và token profile theo hợp đồng.

### 20.5. “Claim `tenant_id` tự khai xác định quyền tenant”

Sai. Trước verify claim này có thể do attacker tự ghi. Sau verify, nó vẫn phải phù hợp issuer-to-tenant mapping, membership/entitlement policy và requested tenant. Một issuer không có thẩm quyền cấp quyền South không thể tự mở tenant South chỉ vì ký một claim có giá trị `south`.

### 20.6. “`sub` giống nhau ở hai issuer là cùng user”

Sai. `sub` thường có phạm vi định danh theo issuer. Dùng cặp **(verified issuer, verified subject)** hoặc một cơ chế account linking tin cậy; không merge users/tenant memberships theo `sub` trùng.

### 20.7. “Nếu JWT không parse được thì cho vào fallback validator nhẹ hơn”

Sai. Một fallback thiếu chữ ký/audience/token type tạo downgrade risk. Các access token formats khác nhau chỉ nên được xử lý theo **trusted routing contract** đã định nghĩa. Không thử nhiều phương án cho đến khi có một phương án dễ dãi chấp nhận.

### 20.8. “`kid` là đủ để biết issuer”

Sai. `kid` không phải global identifier và có thể trùng giữa issuers. Nó chỉ gợi ý khóa trong **trusted JWK Set của issuer đã chọn**. Không tải public key từ `jku` hoặc `x5u` chưa trusted.

### 20.9. “Thêm issuer mới khi token đầu tiên tới là tiện nhất”

Sai. Đó là **trust-on-first-use từ client-controlled input** và thường không phù hợp khi Resource Server phải chỉ tin issuers được phê duyệt. Onboarding cần xác định quyền sở hữu, metadata, key, audience, roles, resource policy và lifecycle.

### 20.10. “Đặt `permitAll()` rồi tự kiểm tra claim trong controller”

Sai khi dùng để thay Bearer authentication của protected API. Một controller đọc raw JWT chưa verified và dùng `scope` để trả dữ liệu có thể bypass toàn bộ Spring Security pipeline. Cần để authentication filter/decoder xử lý token trước khi business logic chạy.

### 20.11. “Mock `Jwt` object đủ để kiểm chứng bảo mật”

Sai. `mockJwt()` và `Jwt.withTokenValue(...)` phù hợp cho tests authorization, nhưng không chứng minh JWT có signature/issuer/audience đúng. Multi-tenant authentication tests cần các JWT **được ký thật bằng test keys** và decoder thật.

### 20.12. “Một token có scope admin thì được làm admin mọi tenant”

Không tự đúng. Một quyền có thể chỉ có ý nghĩa trong issuer/tenant cụ thể. Cần mapping quyền theo context, không sử dụng role toàn cục nếu token profile không bảo đảm quyền xuyên tenant.

### 20.13. “Registry chỉ cần cập nhật database, cache không quan trọng”

Sai. Instances giữ managers/issuer snapshots lâu hơn thời gian suspension có thể vẫn chấp nhận token của issuer đã bị thu hồi. Cần invalidation/refresh/freshness policy và kiểm thử trạng thái registry thay đổi.

### 20.14. “Mọi exception authentication đều là token sai”

Không hẳn. Wrong signature/audience/expiry là lỗi token, còn JWKS discovery timeout/503, TLS lỗi hoặc cấu hình issuer sai có thể là lỗi vận hành. Dù trường hợp nào, Resource Server **không tạo authenticated principal khi chưa đủ bằng chứng**, nhưng telemetry/HTTP status phải được phân loại phù hợp.

### 20.15. “URL có tenant North chứng minh caller thuộc North”

Sai. URL/host là **requested context**, không phải membership. Phải đối chiếu context đó với token đã verified và domain policy.

## 21. Câu hỏi tự kiểm tra

### Câu 1. Có được đọc `iss` từ JWT chưa verified không?

**Có, nếu chỉ để chọn verifier trong trusted allowlist.** Claim `iss` lúc này chỉ là routing hint. Không được cấp principal/authorities/quyền từ nó trước khi chữ ký, issuer, audience và claims được xác minh.

### Câu 2. Nếu `iss` trùng trusted issuer nhưng JWT có chữ ký sai thì sao?

Resolver có thể chọn đúng manager cho issuer đó, nhưng decoder phải **từ chối authentication**. Việc một issuer có trong allowlist không chứng minh token cụ thể do issuer ấy ký.

### Câu 3. Có thể tự tạo `JwtDecoder` từ mọi `iss` gặp trong token không?

**Không** đối với Resource Server có trust boundary chặt. Issuer phải được phê duyệt trong registry trước. Tự discovery URL từ token có thể tạo trust injection, SSRF và DoS.

### Câu 4. Sau khi JWT verify, có thể dùng `scope` và `tenant_id` ngay để cấp quyền mọi tài nguyên không?

**Không.** Claims đã verify là dữ liệu đáng tin theo issuer/profile, nhưng vẫn phải map quyền đúng ngữ cảnh, kiểm tra audience, tenant membership và quyền trên từng resource. Token đúng không có nghĩa “truy cập mọi record”.

### Câu 5. JWT North hợp lệ gọi `/tenants/south/orders` thì sao?

Nếu chọn verifier theo `iss`, authentication của North có thể thành công rồi **tenant authorization từ chối**. Nếu chọn verifier theo path South, authentication có thể từ chối do token không thuộc South trust. Dù kiến trúc nào, không được trả dữ liệu tenant South nếu principal không có quyền.

### Câu 6. Nếu mọi tenant dùng chung issuer thì có cần issuer resolver per tenant?

Thường **không cần** nếu cùng decoder/key/profile. Có thể xác minh JWT bằng issuer chung, rồi kiểm tra signed `tenant_id` và membership/permissions sau authentication. Chỉ thêm tenant-specific strategy khi có nhu cầu trust/policy thực sự.

### Câu 7. Tại sao `kid` chưa verified không thể làm issuer key?

`kid` chỉ là nhãn chọn khóa trong một JWK Set, có thể trùng hoặc bị attacker tự đặt. Phải chọn **trusted JWKS của issuer** trước, sau đó dùng `kid` để lựa chọn khóa trong tập đã tin.

### Câu 8. Hai JWT từ hai issuer có cùng `sub=123` có phải cùng user?

Không thể kết luận. Identity thường được phân biệt bởi **(issuer, subject)**. Việc liên kết account giữa issuers phải do hệ thống tin cậy thực hiện.

### Câu 9. Khi JWKS issuer đã được allowlist nhưng outage, có cho token qua không?

Không có trusted key/validator result thì **không xác thực thành công**. Có thể dùng trusted cached key còn hiệu lực theo policy; không chuyển sang đọc raw claims và cấp quyền.

### Câu 10. Nếu `JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers` đã chạy, API có tự kiểm tra tenant ownership và audience không?

Không được mặc định. Issuer resolver chọn manager, còn issuer/audience/token profile validation phải được xác định đúng trong decoder và domain authorization phải kiểm tra tenant/resource ownership. Cần test những điều kiện đó riêng.

### Câu 11. Có được dùng `iss` chưa verified làm metric label không?

Không nên dùng giá trị raw từ client vì attacker có thể tạo vô hạn nhãn, làm tăng cardinality và đưa dữ liệu không tin vào observability. Dùng issuer alias từ registry khi lookup thành công, hoặc nhãn `unknown` cho issuer không được nhận.

### Câu 12. Vì sao không chỉ test với `mockJwt()`?

`mockJwt()` bỏ qua cryptographic verification để kiểm tra authorization. Nó không chứng minh resolver chọn đúng decoder, chữ ký sai bị từ chối hoặc audience/issuer validators hoạt động. Dùng test JWT có signature thật và decoder thực cho authentication.

## 22. Checklist cho Resource Server nhiều tenant

### 22.1. Chọn chiến lược và trusted issuer registry

- [ ] Có danh sách trusted issuers được quản trị server-side.
- [ ] Chỉ issuer ở trạng thái ACTIVE được phép chọn manager.
- [ ] Unverified `iss` được dùng **duy nhất làm routing hint**, không tạo `Authentication`.
- [ ] Không tự discovery/JWKS từ URL issuer chưa phê duyệt.
- [ ] Issuer lookup có semantics chính xác, không tự normalize URI tùy tiện.
- [ ] Unknown/malformed/missing issuer bị từ chối.
- [ ] Có giới hạn kích thước JWT và chi phí parse ở pre-auth boundary.
- [ ] Không tự fallback sang verifier yếu hơn khi parse/verify thất bại.
- [ ] Không dùng unverified `scope`, `roles`, `sub` hoặc `tenant_id` để cấp quyền.
- [ ] Nếu chọn theo path/host, đó chỉ là context selector, không phải quyền tenant.

### 22.2. Kiểm tra JWT thực sự

- [ ] Mỗi issuer manager có trusted key/JWKS đúng phạm vi.
- [ ] Allowed JWS algorithms được giới hạn theo issuer profile.
- [ ] Chữ ký JWT được verify bằng thư viện/decoder đáng tin.
- [ ] Claim `iss` sau verify phải đúng issuer đã chọn.
- [ ] `aud` được kiểm tra đúng Resource Server.
- [ ] `exp`/`nbf`/thời gian và claims bắt buộc được kiểm tra.
- [ ] Token type/profile được xác định; không lấy ID token làm access token.
- [ ] `setJwtValidator(...)` không làm mất validators mặc định ngoài ý muốn.
- [ ] `kid` chỉ chọn key trong trusted JWKS, không quyết định issuer toàn cục.
- [ ] Lỗi JWKS/discovery không làm bỏ xác minh.

### 22.3. Phân quyền tenant và dữ liệu

- [ ] Principal/authorities được tạo **sau** JWT verification.
- [ ] Identity có namespace issuer, ví dụ (verified issuer, verified subject).
- [ ] Issuer-to-tenant mapping được quản trị đáng tin.
- [ ] Signed `tenant_id` được đối chiếu với requested tenant theo hợp đồng.
- [ ] Nếu principal có nhiều tenant, membership/permission phải được kiểm tra theo tenant.
- [ ] HTTP/method authorization dùng scope/role đúng prefix và nguồn tin cậy.
- [ ] Order/resource thuộc tenant/owner thực sự được kiểm tra tại service/DB.
- [ ] Role admin không tự áp cho mọi tenant nếu profile không cho phép.
- [ ] Response không tiết lộ dữ liệu tenant khác hoặc raw token/claims nhạy cảm.

### 22.4. Kiểm thử

- [ ] Có positive control: JWT đúng issuer/key/audience/time/scope được nhận.
- [ ] Có JWT ký wrong key nhưng `iss` trùng trusted issuer → reject.
- [ ] Có JWT ký đúng key nhưng audience/issuer/expiry sai → reject.
- [ ] Có issuer chưa đăng ký → reject và không gọi URL lạ.
- [ ] Có token hợp lệ của North yêu cầu tenant South → deny.
- [ ] Có JWT hợp lệ nhưng thiếu scope → deny authorization.
- [ ] Có test object-level cross-tenant access → deny.
- [ ] HTTP test thật đi qua security chain/decoder, không chỉ `mockJwt()`.
- [ ] Có test resolver/manager selection nếu ứng dụng có custom routing.
- [ ] Có test issuer suspended và registry cache refresh nếu registry động.

### 22.5. Vận hành

- [ ] Issuer onboarding/offboarding có approval và audit.
- [ ] Registry và manager caches có TTL/freshness/invalidation policy.
- [ ] JWKS/discovery HTTP clients có TLS, timeout và egress controls.
- [ ] Không tạo manager không giới hạn từ attacker-supplied issuers.
- [ ] Metrics dùng issuer alias có cardinality hữu hạn.
- [ ] Không log raw Bearer token, credentials hoặc unverified claims.
- [ ] Một issuer/JWKS outage không biến unknown JWT thành authenticated token.
- [ ] Có quy trình key rotation, token TTL overlap và issuer suspension.

## 23. Sơ đồ tổng hợp: không có đường tắt từ unverified claims tới quyền

~~~mermaid
flowchart LR
    U["Raw Bearer JWT"] --> H["Parse unverified iss"]
    H --> L{"Trusted registry allowlist?"}
    L -->|No| X["Reject"]
    L -->|Yes| S["Select registered decoder"]
    S --> V{"Verify signature, alg, iss, aud, time, profile?"}
    V -->|No| X
    V -->|Yes| J["Verified JWT"]
    J --> A["Create Authentication + authorities"]
    A --> T{"Allowed in requested tenant?"}
    T -->|No| D["Deny"]
    T -->|Yes| O{"Scope and object ownership valid?"}
    O -->|No| D
    O -->|Yes| R["Access protected resource"]
~~~

Trong luồng trên, **unverified issuer chỉ có một tác dụng hợp lệ: giúp chọn bộ kiểm tra nằm trong danh sách tin cậy**. Mọi bước ảnh hưởng đến identity, tenant, scope, role, resource owner và response dữ liệu đều nằm **sau** kết quả xác minh của decoder.

### Một quy tắc ghi nhớ

~~~text
Before JWT verification:
    issuer/tenant/header = hint, not authority

After JWT verification:
    claims = evidence within a trusted issuer/token profile

After authorization:
    access = decision for this tenant, action and resource
~~~

Trong hệ thống nhiều tenant, chọn đúng decoder là điều kiện cần, **không phải quyết định cấp quyền**. Chính sách an toàn kết hợp **trusted issuer allowlist**, **JWT signature và claims validation**, **tenant binding**, **scope-based authorization** và **object-level access control**.

## Tài liệu tham khảo

- [Spring Security — Multitenancy, Servlet Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/multitenancy.html)
- [Spring Security — Multitenancy, Reactive Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/multitenancy.html)
- [Spring Security — Servlet OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — Reactive OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html)
- [Spring Security — JwtIssuerAuthenticationManagerResolver API](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/server/resource/authentication/JwtIssuerAuthenticationManagerResolver.html)
- [Spring Security — JwtIssuerReactiveAuthenticationManagerResolver API](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/server/resource/authentication/JwtIssuerReactiveAuthenticationManagerResolver.html)
- [Spring Security — NimbusJwtDecoder API](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/jwt/NimbusJwtDecoder.html)
- [Spring Security — NimbusReactiveJwtDecoder API](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/jwt/NimbusReactiveJwtDecoder.html)
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515)
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517)
- [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html)
- [OWASP — API Security Top 10](https://owasp.org/API-Security/editions/2023/en/0x11-t10/)
- [OWASP — Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html)
