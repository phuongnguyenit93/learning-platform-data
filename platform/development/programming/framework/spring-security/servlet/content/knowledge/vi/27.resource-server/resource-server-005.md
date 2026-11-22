# JwtDecoder, JWK Set và thay đổi khóa ký trong Spring Security Resource Server

> **Ngữ cảnh:** Spring Security **Servlet** (Spring MVC, Spring Boot 3.x, Spring Security 6.x). API đóng vai trò **OAuth 2.0 Resource Server**, nhận access token dạng JWT qua HTTP `Authorization: Bearer`. Bài này giải thích từ cách `JwtDecoder` tin cậy khóa công khai trong JWK Set đến chiến lược **rotation** khóa ký không gián đoạn; kèm cấu hình Java 17+, ví dụ Spring Boot và các phép kiểm thử bảo mật. Không nhầm Resource Server với Authorization Server — API chỉ **xác minh** token, không phát hành token hoặc tự sở hữu private signing key của nhà cung cấp danh tính.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Trình bày JWT có những thành phần nào, vì sao phải xác minh **chữ ký lẫn claims**, và vai trò của `JwtDecoder` trong Spring Security Servlet.
2. Phân biệt **JWK** (một khóa, thường là khóa công khai), **JWK Set/JWKS** (tập khóa) và `kid` (chỉ là gợi ý chọn khóa), cùng `alg` (thuật toán) và `use`.
3. Chọn cách cấu hình `issuer-uri`, `jwk-set-uri` hoặc `JwtDecoder` tùy chỉnh; hiểu ưu/nhược điểm của discovery, ràng buộc issuer, audience và thời gian.
4. Lập kế hoạch luân chuyển khóa **publish → ký bằng khóa mới → chờ token cũ hết hạn → gỡ khóa cũ**, kể cả thời gian cache và độ lệch đồng hồ.
5. Xử lý sự cố `unknown kid`, JWKS endpoint không truy cập được, signature invalid, sai `iss`/`aud`, token hết hạn và khóa bị lộ.
6. Kiểm thử riêng quyết định **authorization** của API, chữ ký/claims của decoder và tình huống **rotation thực sự với remote JWK Set**, không xem test `jwt()` giả lập là bằng chứng crypto đã hoạt động.

## 2. Đặt vấn đề: Resource Server nhận một Bearer JWT

Ví dụ người dùng gọi API:

```http
GET /api/orders HTTP/1.1
Host: api.example.com
Authorization: Bearer eyJhbGciOiJSUzI1NiIsImtpZCI6ImtleS1iIn0...
```

Giá trị sau `Bearer` trong ví dụ chỉ là đoạn minh họa rút gọn, **không phải JWT hoàn chỉnh**. Một JWT ký bằng JWS dạng compact có ba phần Base64URL:

```text
BASE64URL(JOSE_header).BASE64URL(claims).BASE64URL(signature)
```

JOSE header có thể chứa:

```json
{
  "typ": "JWT",
  "alg": "RS256",
  "kid": "key-b"
}
```

Payload có các claims: `iss` (issuer), `sub` (subject), `aud` (audience), `exp` (expiration), `nbf` (not before), `iat` (issued at), `scope` hoặc `scp` tùy hợp đồng identity provider.

**Cảnh báo cốt lõi:** hai phần đầu chỉ được **mã hóa Base64URL**, không được mã hóa bí mật; ai cầm token có thể giải mã nội dung. Token không trở nên đáng tin chỉ vì chuỗi có cấu trúc JWT hoặc `sub` trông giống tài khoản thật. Phải xác minh chữ ký bằng khóa của issuer đáng tin **và** kiểm tra claims theo chính sách của API.

### Ba câu hỏi độc lập phải trả lời

| Câu hỏi | Cơ chế | Nếu bỏ qua |
| --- | --- | --- |
| Token có được issuer đáng tin ký bằng khóa phù hợp? | Chữ ký JWS, khóa và thuật toán được allowlist; `JwtDecoder` | Có thể nhận token giả hoặc token đã bị sửa. |
| Token có thuộc **đúng issuer, đúng API, còn thời hạn**? | `iss`, `aud`, `exp`, `nbf` và các validator | Token của ứng dụng khác, môi trường khác hoặc đã hết hạn có thể được chấp nhận. |
| Caller có quyền gọi endpoint này? | `JwtAuthenticationConverter`/mapping authorities và `authorizeHttpRequests` | Token hợp lệ về mặt kỹ thuật nhưng thiếu scope/role vẫn đọc được dữ liệu. |

**Bearer** nghĩa là ai có token có khả năng sử dụng token trong phạm vi quyền của nó. JWT đã ký không tự bảo vệ khỏi mất cắp/replay; cần TLS, lưu trữ an toàn, thời hạn phù hợp và cơ chế thu hồi khi rủi ro đòi hỏi.

## 3. Các thành phần trong Spring Security Servlet

Một request bình thường đi qua các thành phần theo mô hình đơn giản:

```mermaid
flowchart TD
    A["HTTP Authorization: Bearer JWT"] --> B["BearerTokenAuthenticationFilter"]
    B --> C["JwtAuthenticationProvider"]
    C --> D["JwtDecoder / NimbusJwtDecoder"]
    D --> E["Đọc JOSE alg + kid"]
    E --> F["JWK Set từ issuer/JWKS endpoint"]
    F --> G{"Chữ ký + thời gian + issuer + audience hợp lệ?"}
    G -- Không --> H["Authentication failure → 401"]
    G -- Có --> I["JwtAuthenticationConverter → authorities"]
    I --> J{"Authorization cho endpoint?"}
    J -- Thiếu scope/role --> K["403 Forbidden"]
    J -- Được phép --> L["Controller xử lý request"]
```

Đây là sơ đồ khái niệm, không phải toàn bộ class/method call stack trong mọi cấu hình.

**Vai trò cụ thể:**

- `BearerTokenAuthenticationFilter` trích Bearer token theo quy tắc HTTP authentication đã cấu hình. Nó không tự chứng thực JWT.
- `JwtAuthenticationProvider` dùng `JwtDecoder` để xác minh token và tạo Spring Security authentication phù hợp.
- `JwtDecoder` là giao diện với phương thức `Jwt decode(String token) throws JwtException`; Spring Security thường dùng `NimbusJwtDecoder` cho JWT ký theo JWS.
- `NimbusJwtDecoder` dùng chức năng JOSE/JWK của Nimbus để tìm khóa phù hợp, kiểm tra chữ ký và chạy `OAuth2TokenValidator<Jwt>`.
- `JwtAuthenticationConverter` biến claims thành principal và granted authorities. Mặc định thường chuyển `scope` hoặc `scp` sang authority với tiền tố `SCOPE_`; chính sách role tùy chỉnh phải được thiết kế tường minh.
- `SecurityFilterChain` áp đặt quyền như `hasAuthority("SCOPE_orders.read")`. Có chữ ký đúng không đồng nghĩa có quyền.

Trong resource server chỉ dùng Bearer token và không dựa vào cookie đăng nhập, `401 Unauthorized` thường biểu thị không có/không xác thực được credential; `403 Forbidden` biểu thị đã được xác thực nhưng thiếu quyền cho tài nguyên. Ứng dụng có custom entry point/handler có thể định hình JSON lỗi khác nhau.

## 4. JWK, JWK Set, kid và thuật toán

### 4.1. JWK là dữ liệu mô tả khóa

**JSON Web Key (JWK)** là biểu diễn JSON của một khóa crypto theo JOSE. Một **JWK Set (JWKS)** chứa mảng `keys`:

```json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "key-a",
      "use": "sig",
      "alg": "RS256",
      "n": "BASE64URL_MODULUS_A",
      "e": "AQAB"
    },
    {
      "kty": "RSA",
      "kid": "key-b",
      "use": "sig",
      "alg": "RS256",
      "n": "BASE64URL_MODULUS_B",
      "e": "AQAB"
    }
  ]
}
```

Đoạn JSON này là **sơ đồ minh họa**, hai chuỗi `BASE64URL_MODULUS_*` chỉ thể hiện vị trí modulus chứ **không phải khóa RSA hợp lệ**; endpoint thực tế bắt buộc công bố các giá trị Base64URL chuẩn của public key.

Các trường thường gặp:

| Trường | Ý nghĩa |
| --- | --- |
| `kty` | Loại khóa, ví dụ `RSA` hoặc `EC`. |
| `kid` | Key ID hỗ trợ lựa chọn khóa trong tập; cần duy nhất trong bối cảnh ký của issuer tại một thời điểm. |
| `use` | Mục đích sử dụng, ví dụ `sig` để ký/xác minh; có thể vắng theo hợp đồng provider. |
| `alg` | Thuật toán mà khóa được dùng, ví dụ `RS256`; metadata không thay thế allowlist thuật toán của Resource Server. |
| `n`, `e` | RSA public modulus và public exponent. |
| `crv`, `x`, `y` | Các tham số public của EC JWK khi dùng thuật toán thích hợp. |
| `x5c` / `x5t` | Có thể chứa certificate chain/thumbprint; không đồng nghĩa API được phép tin một CA tùy ý do token đưa tới. |

Resource Server nên lấy **public verification keys** từ JWKS. **Tuyệt đối không công bố** các trường private như `d` của RSA hay secret đối xứng `k` trên JWKS công khai. JWT ký không phải JWT mã hóa; không đưa PII hay bí mật vào claims chỉ vì có chữ ký.

### 4.2. kid là gợi ý, không phải bằng chứng tin cậy

Khi token báo `kid=key-b`, decoder dùng nó để tìm ứng viên phù hợp trong **JWK Set của issuer đã cấu hình**. Token không được phép tự chọn một URL tải khóa bất kỳ. Đừng xây logic:

```java
// Không làm như sau: ví dụ phản-pattern, KHÔNG có tính bảo mật.
String jwksUrl = request.getParameter("jwks");
```

Một token/HTTP request do client gửi không được chỉ định endpoint tin cậy để server tải khóa xác minh; nếu làm vậy có thể gây SSRF hoặc chấp nhận khóa do attacker kiểm soát. Các JOSE header `jku`, `x5u`, `jwk` nếu được hỗ trợ bởi một implementation nào đó cũng không được tự động coi là nguồn tin cậy ngoài chính sách allowlist.

**Đổi `kid` không đổi khóa crypto**. Hai khóa khác nhau có thể được đặt cùng một `kid` do lỗi vận hành, gây cache nhầm và kết quả xác minh khó dự đoán. Khi rotation, tạo **key pair mới và kid mới**, không tái sử dụng kid quá sớm.

### 4.3. alg phải được kiểm soát từ server

Header `alg` là dữ liệu bên trong JWT do client đưa tới. API phải **giới hạn thuật toán cho phép** tương thích với hợp đồng issuer và loại khóa. Không chấp nhận `alg: none` cho JWT dùng làm access token ký, không tự nâng hoặc đổi giữa HS256 và RS256 theo header chưa được kiểm tra.

Với RSA, `RS256` là RSA PKCS#1 v1.5 + SHA-256; `PS256` là RSA-PSS + SHA-256 và **không tự động hoán đổi được**. Với EC, `ES256` dùng ECDSA P-256; thuật toán phải khớp issuer/khóa. Nếu provider đổi thuật toán khi luân chuyển, Resource Server cần cấu hình và kiểm thử tương ứng; **không nới allowlist tới tất cả thuật toán** để che lỗi triển khai.

## 5. Cấu hình JwtDecoder: issuer-uri, jwk-set-uri hay bean riêng?

### 5.1. Chỉ dùng issuer-uri: discovery thuận tiện

Với nhà cung cấp OIDC/OAuth2 tương thích discovery và endpoint metadata:

```properties
spring.security.oauth2.resourceserver.jwt.issuer-uri=https://identity.example.org/realms/production
```

Trong cấu hình tự động mặc định của Boot/Spring Security, metadata của issuer giúp tìm endpoint JWKS và decoder thiết lập xác minh `iss`. Khi tài liệu/provider và thư viện hỗ trợ, đây là lựa chọn đơn giản, ít hardcode đường dẫn JWKS.

**Cân nhắc khả dụng:** với cách khởi tạo dựa trên issuer discovery, một số phiên bản/cấu hình có thể phụ thuộc khả năng truy cập metadata lúc startup. Đừng giả định mọi biến thể đều khởi động được khi issuer offline; kiểm thử hành vi của phiên bản thực tế.

### 5.2. issuer-uri + jwk-set-uri: không cần discovery ở startup

```properties
spring.security.oauth2.resourceserver.jwt.issuer-uri=https://identity.example.org/realms/production
spring.security.oauth2.resourceserver.jwt.jwk-set-uri=https://identity.example.org/realms/production/protocol/openid-connect/certs
```

Ở cấu hình auto-config thích hợp, dùng `jwk-set-uri` cụ thể giúp Resource Server biết trực tiếp URL JWKS, tránh phụ thuộc metadata discovery khi khởi tạo, **vẫn giữ validation issuer** nhờ `issuer-uri`. Khi thực sự decode một JWT có chữ ký, API vẫn phải có khóa public phù hợp (từ cache hoặc JWKS endpoint); không vì bỏ discovery mà hết phụ thuộc vào IdP/JWKS network.

**Điểm dễ sai:** chỉ cấu hình `jwk-set-uri` mà không bật validator issuer thích hợp có thể khiến API không xác minh `iss` theo kỳ vọng. Tương tự, chữ ký đúng nhưng `aud` dành cho API khác vẫn là token không nên chấp nhận.

### 5.3. Tự khai báo JwtDecoder

Khi cần allowlist thuật toán, audience, custom claim validation hoặc policy kiểm soát rõ ràng, có thể khai báo bean `JwtDecoder`. Lúc đó bean tự quản chịu trách nhiệm validator, do đó không nên nghĩ các property auto-config của Boot sẽ tự kết hợp thay bạn.

Chọn **một nơi cấu hình decoder chính** cho mỗi security chain/issuer; tránh vừa khai báo bean tùy chỉnh vừa trông chờ Boot âm thầm tạo decoder khác. Nếu có **nhiều issuer**, dùng thiết kế phân giải theo issuer/tenant đáng tin và xác minh từng issuer riêng; không tạo một decoder tin tất cả mọi JWKS.

## 6. Ví dụ chạy được: Spring Boot Resource Server với NimbusJwtDecoder

Demo dùng **Java 17+, Maven, Spring Boot 3.3.0/Spring Security 6.x**. API có hai endpoint:

- `GET /public/ping`: không yêu cầu token, trả `ok`.
- `GET /api/orders`: cần token có chữ ký hợp lệ, `iss`, `aud`, thời gian hợp lệ và quyền `SCOPE_orders.read`; trả chuỗi theo subject.

Để gọi `/api/orders` bằng token thật cần một **Authorization Server thật** có JWKS HTTPS và phát token tương thích. Maven project tự biên dịch được; `mvn test` bên dưới chạy offline bằng authentication giả lập và **không chứng minh đã liên lạc IdP**. Mọi domain ví dụ phải được thay bằng thông tin issuer hợp lệ của môi trường bạn kiểm soát khi triển khai.

### 6.1. Cấu trúc dự án

```text
jwt-rotation-resource-server/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/jwt/
    │   │   ├── ResourceServerApplication.java
    │   │   ├── SecurityConfig.java
    │   │   └── ApiController.java
    │   └── resources/
    │       └── application.properties
    └── test/
        └── java/demo/jwt/
            ├── ResourceServerSecurityTest.java
            └── LocalSignatureTest.java
```

### 6.2. Maven dependencies

**`pom.xml`**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.0</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>jwt-rotation-resource-server</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

**`src/main/resources/application.properties`**

```properties
server.port=8080

# Cấu hình trust do SERVER nắm giữ, không lấy từ request/header JWT.
app.security.jwt.issuer=https://identity.example.org/realms/production
app.security.jwt.jwk-set-uri=https://identity.example.org/realms/production/protocol/openid-connect/certs
app.security.jwt.audience=orders-api
```

Các domain trong ví dụ là tên minh họa và không phải IdP đang hoạt động. Trước khi kiểm thử token thật, thay ba giá trị bằng issuer/JWKS/audience do Authorization Server của bạn cung cấp. Đảm bảo `issuer` trong config đúng **chính xác** claim `iss` của token — bao gồm scheme, host, port và path.

**`src/main/java/demo/jwt/ResourceServerApplication.java`**

```java
package demo.jwt;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ResourceServerApplication {
    public static void main(String[] args) {
        SpringApplication.run(ResourceServerApplication.class, args);
    }
}
```

### 6.3. JwtDecoder kiểm tra chữ ký, issuer, audience và timestamp

**`src/main/java/demo/jwt/SecurityConfig.java`**

```java
package demo.jwt;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/ping").permitAll()
                .requestMatchers("/api/orders")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().denyAll())
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .csrf(csrf -> csrf.disable())
            .oauth2ResourceServer(oauth ->
                oauth.jwt(Customizer.withDefaults()))
            .build();
    }

    @Bean
    JwtDecoder jwtDecoder(
            @Value("${app.security.jwt.issuer}") String issuer,
            @Value("${app.security.jwt.jwk-set-uri}") String jwkSetUri,
            @Value("${app.security.jwt.audience}") String audience) {

        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(jwkSetUri)
            .jwsAlgorithm(SignatureAlgorithm.RS256)
            .build();

        OAuth2TokenValidator<Jwt> issuerAndTime =
            JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> audienceValidator = jwt ->
            jwt.getAudience().contains(audience)
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        "invalid_token",
                        "Audience is not accepted",
                        null));

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                issuerAndTime, audienceValidator));

        return decoder;
    }
}
```

**Giải thích từng điểm quan trọng:**

1. `withJwkSetUri(jwkSetUri)` chỉ nguồn khóa public tin cậy do server cấu hình. Nimbus sẽ dùng JWK Set phù hợp để xác minh chữ ký token. **Không xây URL JWKS từ `kid`/`iss` chưa được xác minh hoặc tham số request.**
2. `jwsAlgorithm(SignatureAlgorithm.RS256)` giới hạn thuật toán ký được decoder chấp nhận theo hợp đồng demo. Nếu IdP dùng `PS256` hoặc `ES256`, cần cấu hình khác tương ứng **sau khi xác minh hợp đồng của issuer**.
3. `JwtValidators.createDefaultWithIssuer(issuer)` thêm validator chuẩn (bao gồm thời gian như `exp`/`nbf` theo cấu hình mặc định và `iss`); `DelegatingOAuth2TokenValidator` kết hợp thêm kiểm tra `aud`.
4. Audience được xem là **danh sách**. Token có `aud` dành cho ứng dụng khác bị từ chối dù có signature và issuer hợp lệ.
5. `hasAuthority("SCOPE_orders.read")` kiểm tra scope. Spring Security mặc định có thể ánh xạ `scope`/`scp` từ JWT sang `SCOPE_...`, nhưng nếu IdP dùng claims riêng như `roles`/`permissions`, phải viết `JwtAuthenticationConverter` hoặc authorities converter có kiểm thử và không mặc nhiên tin format lạ.
6. `STATELESS` phù hợp cho API Bearer thuần túy: mỗi request xác thực theo token, không tạo session login ứng dụng. `csrf.disable()` trong **demo này chỉ hợp lý vì authentication không dựa vào cookie tự động đính kèm**. Nếu cùng chain có session-cookie/form browser hoặc endpoint dùng ambient credentials, cần đánh giá và giữ CSRF protection thích hợp, không sao chép cấu hình này sang app hỗn hợp.
7. `oauth2ResourceServer(...jwt(...))` không biến API thành OAuth2 Client hay Authorization Server. Không cấp token và không biết private signing key.
8. Khi bạn tự khai báo `@Bean JwtDecoder`, các validation logic là trách nhiệm của bean đó. Đừng trông chờ Spring Boot tự thêm một audience validator khác vào bean custom.

**`src/main/java/demo/jwt/ApiController.java`**

```java
package demo.jwt;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiController {
    @GetMapping("/public/ping")
    public String ping() {
        return "ok";
    }

    @GetMapping("/api/orders")
    public String orders(@AuthenticationPrincipal Jwt jwt) {
        return "orders for " + jwt.getSubject();
    }
}
```

Controller cố ý chỉ đọc `sub` và không trả token. Production cần phân quyền trên resource cụ thể (ví dụ từng đơn hàng thuộc đúng tenant/account), chứ một scope chỉ xác minh quyền tổng quát. JWT subject không nhất thiết là username có thể hiển thị cho người dùng.

### 6.4. Chạy ứng dụng và kiểm tra request

Tại thư mục `jwt-rotation-resource-server`:

```bash
mvn test
mvn spring-boot:run
```

Thử request không cần token:

```bash
curl -i http://localhost:8080/public/ping
```

Kỳ vọng HTTP `200` và body:

```text
ok
```

Thử request được bảo vệ:

```bash
curl -i http://localhost:8080/api/orders
```

Kỳ vọng HTTP `401` với cơ chế Bearer challenge phù hợp. Khi đã có **JWT thật** do đúng issuer phát hành, có audience và scope yêu cầu:

```bash
curl -i http://localhost:8080/api/orders \
  -H "Authorization: Bearer $ACCESS_TOKEN"
```

Trên Bash, `$ACCESS_TOKEN` là biến môi trường bạn tự cấp an toàn từ phiên thử nghiệm; không ghi token thật vào README, source code, git hoặc log. Với token hợp lệ của subject `alice` và authority `SCOPE_orders.read`, body của demo:

```text
orders for alice
```

Nếu token hết hạn, không có chữ ký hợp lệ, không đúng issuer/audience, hoặc thiếu scope, response sẽ là 401 hoặc 403 theo vị trí thất bại. Không cho client tự chọn JWK endpoint, đổi thuật toán hoặc vô hiệu validation để "làm cho demo chạy".

## 7. Kiểm thử bằng MockMvc: routing và authorization

**`src/test/java/demo/jwt/ResourceServerSecurityTest.java`**

```java
package demo.jwt;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ResourceServerSecurityTest {
    @Autowired
    MockMvc mvc;

    @Test
    void publicPingWorksWithoutToken() throws Exception {
        mvc.perform(get("/public/ping"))
            .andExpect(status().isOk())
            .andExpect(content().string("ok"));
    }

    @Test
    void protectedEndpointRequiresAuthentication() throws Exception {
        mvc.perform(get("/api/orders"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void validPrincipalWithScopeCanReadOrders() throws Exception {
        mvc.perform(get("/api/orders")
                .with(jwt()
                    .jwt(token -> token.subject("alice"))
                    .authorities(
                        new SimpleGrantedAuthority("SCOPE_orders.read"))))
            .andExpect(status().isOk())
            .andExpect(content().string("orders for alice"));
    }

    @Test
    void authenticatedButMissingScopeIsForbidden() throws Exception {
        mvc.perform(get("/api/orders")
                .with(jwt()
                    .jwt(token -> token.subject("alice"))
                    .authorities(
                        new SimpleGrantedAuthority("SCOPE_profile"))))
            .andExpect(status().isForbidden());
    }
}
```

Các test này kiểm tra **ủy quyền khi đã có JwtAuthenticationToken mô phỏng**, nhưng `jwt()` từ `spring-security-test` **bỏ qua bước parse chữ ký và không gọi remote JWKS**. Vì vậy test 200/403 kể trên không thể chứng minh chữ ký, `iss` hay `aud` được xác minh đúng. Đây là điểm quan trọng khi QA: test security chain cần tách khỏi test decoder.

## 8. Test JwtDecoder bằng khóa RSA tạo tại chỗ

Có thể kiểm tra **chữ ký và claims thật** offline bằng cách tạo RSA key pair trong JUnit, ký token bằng `NimbusJwtEncoder`, rồi giải mã với `NimbusJwtDecoder.withPublicKey`. Test này **không gọi remote JWK Set**, nên không đại diện cho cache/rotation JWKS; nó bổ sung bằng chứng độc lập về signature validation.

**`src/test/java/demo/jwt/LocalSignatureTest.java`**

```java
package demo.jwt;

import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jose.jwk.source.ImmutableJWKSet;
import com.nimbusds.jose.proc.SecurityContext;
import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtClaimsSet;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.JwtEncoderParameters;
import org.springframework.security.oauth2.jwt.JwtException;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.JwsHeader;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.oauth2.jwt.NimbusJwtEncoder;

import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;
import java.time.Instant;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class LocalSignatureTest {
    private static final String ISSUER =
        "https://identity.example.org/realms/production";

    private static KeyPair rsa() throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        return generator.generateKeyPair();
    }

    private static String signedToken(
            KeyPair pair, String audience) {
        RSAKey key = new RSAKey.Builder(
                (RSAPublicKey) pair.getPublic())
            .privateKey((RSAPrivateKey) pair.getPrivate())
            .keyID("test-rsa-a")
            .build();

        ImmutableJWKSet<SecurityContext> source =
            new ImmutableJWKSet<>(new JWKSet(key));
        JwtEncoder encoder = new NimbusJwtEncoder(source);

        Instant now = Instant.now();
        JwtClaimsSet claims = JwtClaimsSet.builder()
            .issuer(ISSUER)
            .subject("alice")
            .audience(List.of(audience))
            .issuedAt(now)
            .expiresAt(now.plusSeconds(300))
            .claim("scope", "orders.read")
            .build();

        JwsHeader header = JwsHeader
            .with(SignatureAlgorithm.RS256)
            .keyId("test-rsa-a")
            .build();

        return encoder.encode(
            JwtEncoderParameters.from(header, claims))
            .getTokenValue();
    }

    private static NimbusJwtDecoder decoder(RSAPublicKey publicKey) {
        NimbusJwtDecoder d = NimbusJwtDecoder
            .withPublicKey(publicKey)
            .build();

        OAuth2TokenValidator<Jwt> audience = jwt ->
            jwt.getAudience().contains("orders-api")
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        "invalid_token", "Audience mismatch", null));

        d.setJwtValidator(new DelegatingOAuth2TokenValidator<>(
            JwtValidators.createDefaultWithIssuer(ISSUER), audience));

        return d;
    }

    @Test
    void validSignatureIssuerAndAudienceAccepted() throws Exception {
        KeyPair pair = rsa();
        String token = signedToken(pair, "orders-api");

        Jwt jwt = decoder((RSAPublicKey) pair.getPublic()).decode(token);
        assertEquals("alice", jwt.getSubject());
    }

    @Test
    void validSignatureWithWrongAudienceRejected() throws Exception {
        KeyPair pair = rsa();
        String token = signedToken(pair, "another-api");

        assertThrows(JwtException.class, () ->
            decoder((RSAPublicKey) pair.getPublic()).decode(token));
    }

    @Test
    void signatureFromDifferentKeyRejected() throws Exception {
        KeyPair signer = rsa();
        KeyPair unrelated = rsa();
        String token = signedToken(signer, "orders-api");

        assertThrows(JwtException.class, () ->
            decoder((RSAPublicKey) unrelated.getPublic()).decode(token));
    }
}
```

**Bằng chứng mà test này tạo ra:** issuer/audience đúng và chữ ký đúng được nhận; audience sai bị từ chối dù chữ ký đúng; khóa public không khớp từ chối chữ ký. Đây là test dùng RSA thật trong JVM, không dùng `jwt()` giả lập. **Chưa chứng minh** JWKS HTTP, TTL của JWK cache, đổi `kid` hay sự hiện diện của khóa mới qua network.

Maven test mặc định chạy với Java 17 và không cần khóa của nhà cung cấp thật, vì test tự tạo RSA key pair. Kết quả chuẩn của JUnit thành công là test suite **pass**; không giả định số dòng log Maven cố định giữa môi trường/phiên bản.

## 9. Rotation khóa ký: chạy song song khóa cũ và khóa mới

Khóa ký là một phần của hợp đồng bảo mật giữa **Authorization Server** và **Resource Server**. Authorizer giữ **private key**, dùng để ký token; Resource Server lấy **public key** từ JWKS để xác minh. Rotation là quá trình thay khóa mà không vô tình làm tất cả token đang còn hạn bị 401.

### 9.1. Timeline triển khai an toàn

Giả sử issuer hiện ký token bằng RSA key có `kid=key-a` và JWT access token có tuổi tối đa 15 phút. Issuer chuẩn bị `key-b` mới.

| Giai đoạn | Hành động ở Authorization Server/JWKS | Hành vi Resource Server |
| --- | --- | --- |
| T0 — đang chạy | Ký bằng private `key-a`; JWKS công bố public `key-a`. | Token `kid=key-a` xác minh bằng key-a. |
| T1 — publish trước | JWKS công bố **cả key-a và key-b**, nhưng tiếp tục ký bằng key-a. | Decoder có thể tải trước key-b qua refresh/cache; token cũ vẫn hợp lệ. |
| T2 — đổi ký | Issuer bắt đầu ký token mới bằng private `key-b`; JWKS vẫn chứa **cả hai public key**. | Token cũ key-a và token mới key-b cùng được chấp nhận nếu claims hợp lệ và cache có/đã tải khóa tương ứng. |
| T3 — chờ đủ cửa sổ | Không phát hành token mới ký key-a; tiếp tục giữ cả hai public key qua TTL token cũ, clock skew, JWKS propagation/cache và hệ thống có độ trễ. | Token key-a còn hợp lệ theo `exp` vẫn xác minh được; token key-b tiếp tục hoạt động. |
| T4 — thu hồi bình thường | Gỡ public key-a khi chắc chắn không còn token key-a hợp lệ cần hỗ trợ; tiếp tục ký key-b. | Cache có thể chưa refresh lập tức. Việc xóa key không bảo đảm mọi node ngay lập tức từ chối token cũ. |

**Không đổi thứ tự:** nếu chuyển sang ký `key-b` trước khi JWK Set công bố key-b, Resource Server có thể trả `401 invalid_token` vì `kid` chưa được nhận diện. Nếu xóa `key-a` quá sớm, mọi token key-a còn hạn có thể bất ngờ bị 401 khi cache refresh.

Với ví dụ TTL 15 phút, không kết luận "đợi đúng 15 phút là đủ" mà phải xét **token cuối cùng ký key-a**, clock skew/validator và các tầng cache/CDN, JWKS refresh. Không có công thức số phút cố định áp dụng cho mọi triển khai; phải đo chính sách issuer thực tế và thời hạn tối đa của token.

### 9.2. Thực tế decoder chọn khóa và cache

Khi nhận JWT `kid=key-b`, thư viện JOSE/JWK cố tìm khóa có `kid`/`kty`/`alg`/`use` phù hợp trong tập khóa tin cậy. Tùy Nimbus/Spring Security version và cache implementation, một `kid` mới chưa có trong bộ nhớ có thể kích hoạt tải lại JWKS; **không dựa vào một thời gian refresh cố định chưa được kiểm tra**.

Các trường hợp đáng lưu ý:

- JWKS bị cache ở **Resource Server**, cũng có thể ở CDN/proxy hoặc network client. Khi issuer thay đổi JWKS, các node có thể nhìn thấy tập khóa ở thời điểm khác nhau.
- Nếu provider tái sử dụng **cùng kid** cho khóa mới, cache cũ có thể khiến token mới bị signature invalid dù `kid` trông "đúng". Dùng kid mới và publish-before-use.
- Khi remove key-a, cache có thể tiếp tục giữ public key-a trong một thời gian. Token key-a đã hết `exp` vẫn phải bị từ chối nhờ timestamp validator, nhưng **đừng coi xóa JWKS là cơ chế thu hồi tức thời**.
- Nếu JWKS endpoint offline mà decoder đã có khóa trong cache, một số token có thể tiếp tục được xác minh; token dùng kid mới hoặc cache hết hạn có thể thất bại. Xây availability test cho cả warm-cache/cold-start/unknown-kid.
- Dù JWK Set từ HTTPS và có TLS hợp lệ, **issuer metadata/JWKS endpoint phải là nguồn được server cấu hình tin cậy**. Không biến token chưa xác minh thành URL tùy ý để tránh SSRF/remote key injection.
- Không nên cho tất cả node liên tục poll JWKS dồn dập khi lỗi; kết hợp caching, timeout, retry/backoff và giám sát phù hợp theo cấu hình thư viện.

### 9.3. Rotate định kỳ khác với xử lý khóa bị lộ

**Rotation bình thường:** issuer có thể giữ khóa cũ đủ lâu để token còn sống tiếp tục hoạt động. Trải nghiệm người dùng ít gián đoạn.

**Sự cố private key bị lộ:** ưu tiên chặn người có khóa bị lộ ký token giả. Có thể cần **ngừng chấp nhận key-a sớm**, kể cả khiến token hợp lệ cũ bị 401, dùng cơ chế emergency revoke/invalidate token/session và thông báo khách hàng. Bởi cache phân tán, gỡ key trên JWKS **không tự đảm bảo từ chối ngay** trên mọi Resource Server. Nếu rủi ro đòi hỏi hiệu lực tức thời, phải có cơ chế điều phối/đẩy cấu hình, buộc cache refresh/restart theo kế hoạch, chính sách denylist/epoch hoặc token introspection tùy kiến trúc, và kiểm chứng sau rollout.

Private signing key **không** nằm trong Resource Server hay repo API. Nơi giữ private key phải được kiểm soát (ví dụ KMS/HSM hoặc secret management phù hợp); quyền phát hành, audit, thao tác rotate và quyền đọc public JWKS tách biệt.

### 9.4. Sơ đồ các mốc key-a/key-b

```mermaid
sequenceDiagram
    participant AS as Authorization Server
    participant JWKS as JWKS endpoint
    participant RS as Resource Server
    Note over AS,RS: T1 — pre-publish public key-b
    AS->>JWKS: Public keys [key-a, key-b]
    AS-->>RS: Token cũ ký key-a
    RS->>JWKS: Lấy/refresh public key-a
    JWKS-->>RS: Keys [key-a, key-b]
    RS->>RS: Verify token key-a
    Note over AS,RS: T2 — bắt đầu ký key-b
    AS-->>RS: Token mới ký key-b
    RS->>JWKS: Lookup/refresh nếu cần
    JWKS-->>RS: Public key-b
    RS->>RS: Verify token key-b
    Note over AS,RS: T3 — chờ token key-a hết hạn và cache đồng bộ
    AS->>JWKS: Chỉ công bố public key-b
```

Sơ đồ không thể hiện tất cả token do client trung gian gửi hay số lần refresh thực. Nó minh họa **nguyên tắc có hai khóa public cùng tồn tại trong cửa sổ chuyển đổi**.

## 10. Ví dụ thuần Java 17: đúng/sai chữ ký khi thay public key

Đoạn dưới chạy **không cần Spring, Maven, IdP hoặc mạng**. Nó minh họa toán học nền tảng của rotation RSA: chữ ký tạo bởi private `key-a` chỉ kiểm tra đúng với public `key-a`, không đúng với public `key-b`. Đây **không phải** implementation JWT parser/JWKS client, vì tự viết JWT verifier cho production rất dễ sai.

Lưu thành file **`KeyRotationIntuition.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PublicKey;
import java.security.Signature;
import java.util.LinkedHashMap;
import java.util.Map;

public class KeyRotationIntuition {
    static KeyPair generate() throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        return generator.generateKeyPair();
    }

    static byte[] sign(KeyPair pair, byte[] data) throws Exception {
        Signature signature = Signature.getInstance("SHA256withRSA");
        signature.initSign(pair.getPrivate());
        signature.update(data);
        return signature.sign();
    }

    static boolean verify(PublicKey publicKey, byte[] data, byte[] signature)
            throws Exception {
        Signature verifier = Signature.getInstance("SHA256withRSA");
        verifier.initVerify(publicKey);
        verifier.update(data);
        return verifier.verify(signature);
    }

    public static void main(String[] args) throws Exception {
        KeyPair oldKey = generate();
        KeyPair newKey = generate();
        byte[] payload = "signed payload".getBytes(StandardCharsets.UTF_8);
        byte[] sigOld = sign(oldKey, payload);
        byte[] sigNew = sign(newKey, payload);

        Map<String, PublicKey> published = new LinkedHashMap<>();
        published.put("key-a", oldKey.getPublic());
        System.out.println("before: old token passes = "
                + verify(published.get("key-a"), payload, sigOld));

        published.put("key-b", newKey.getPublic());
        System.out.println("overlap: old token passes = "
                + verify(published.get("key-a"), payload, sigOld));
        System.out.println("overlap: new token passes = "
                + verify(published.get("key-b"), payload, sigNew));
        System.out.println("wrong key verifies old signature = "
                + verify(published.get("key-b"), payload, sigOld));

        published.remove("key-a");
        System.out.println("after retirement: old kid present = "
                + published.containsKey("key-a"));
    }
}
```

Biên dịch/chạy với Java 17+:

```bash
javac KeyRotationIntuition.java
java KeyRotationIntuition
```

**Stdout chính xác** (không phụ thuộc các key pair RSA ngẫu nhiên vì chỉ in giá trị boolean):

```text
before: old token passes = true
overlap: old token passes = true
overlap: new token passes = true
wrong key verifies old signature = false
after retirement: old kid present = false
```

Chú ý khác biệt giữa demo này với JWT thực: chưa có `iss`, `aud`, `exp`, kid lookup qua JWKS, HTTPS, cache và CSRF/authorization; mã này chỉ giải thích *tại sao* hai public key phải cùng hiện diện khi token ký bởi hai private key khác nhau cùng đang lưu hành.

## 11. Kiểm thử rotation thực sự với JWKS HTTP

Để chứng minh chu kỳ đổi khóa trên Resource Server, cần test ở cấp tích hợp với một **HTTP JWKS test endpoint** bạn kiểm soát và JWT được ký bằng hai RSA key khác nhau. Có thể dùng local mock HTTP server/WireMock/MockWebServer; test phải gọi **JwtDecoder thật với JWK Set URI** chứ không dùng `jwt()`.

Một test plan tối thiểu:

| Tình huống | JWKS mà test server công bố | Token | Kết quả mong đợi |
| --- | --- | --- | --- |
| Baseline | `[key-a]` | Chữ ký key-a, `kid=key-a`, claims hợp lệ | Decode thành công. |
| Prepublish | `[key-a,key-b]` | Token cũ key-a | Vẫn hợp lệ. |
| Sau switch | `[key-a,key-b]` | Token mới key-b | Hợp lệ khi decoder nạp được key-b. |
| Chữ ký giả | `[key-a,key-b]` | Header `kid=key-b` nhưng ký bằng private không liên quan | Bị từ chối. |
| Sai issuer | `[key-a,key-b]` | Đúng chữ ký nhưng `iss` sai | Bị từ chối. |
| Sai audience | `[key-a,key-b]` | Đúng chữ ký nhưng `aud` là API khác | Bị từ chối. |
| Hết hạn | `[key-a,key-b]` | `exp` đã qua, xét clock skew | Bị từ chối. |
| JWKS outage | Tắt endpoint network | Token đã cache / kid chưa gặp | Quan sát hành vi theo cache cụ thể, **không mặc định kết quả giống nhau**. |
| Retire | `[key-b]`, cache cũ đã refresh/evict | Token key-a | Bị từ chối do không còn khóa tin cậy, dù chưa exp. |
| Sai thuật toán | `[key-a,key-b]` | Header `alg` ngoài allowlist | Bị từ chối. |

Để test "retire" đáng tin cậy, cần kiểm soát cache/lifecycle hoặc tạo decoder mới sau khi mock JWKS đã đổi. Nếu cache còn giữ key-a, test có thể tiếp tục chấp nhận token key-a; đây là **hành vi cache** cần quan sát và thiết kế, không phải lý do nới validation. Không dùng `Thread.sleep` một khoảng tùy tiện để đoán TTL cache chưa được cấu hình.

Nếu dùng Spring Boot trong integration test, trỏ `app.security.jwt.jwk-set-uri` về URI của local mock server trước khi khởi tạo `JwtDecoder`. Ghi rõ test đang kiểm chứng **JWKS remote** (khác hẳn MockMvc `jwt()` và `withPublicKey` ở phần trước). Mỗi test nên tạo key pair mới, kid riêng, và tách chính sách issuer/audience khỏi thử nghiệm cache.

## 12. Phân biệt thay khóa ký, thu hồi token và version claims

Thay đổi key pair là cơ chế vận hành **trust/key material**, không phải giải pháp đơn giản cho tất cả bài toán authorization:

- **Key rotation:** thay khóa ký và public verification keys; token cũ có thể tiếp tục hợp lệ đến `exp` khi key cũ còn được tin cậy.
- **Revoke access token:** yêu cầu vô hiệu hóa một token hoặc một nhóm token **trước `exp`**. JWT tự chứa đã được phát hành không tự truy vấn trạng thái revoke. Cần lifetime ngắn, `jti` denylist, session/version epoch, introspection hoặc kiến trúc token phù hợp mức rủi ro.
- **Đổi quyền:** scope/role trong JWT có thể đã được phát hành; Resource Server thường không nhìn thấy thay đổi quyền ngay nếu không có cơ chế kiểm tra live state/revocation. Cân nhắc token TTL và dữ liệu phân quyền cục bộ.
- **Thay signing algorithm:** là thay contract giữa issuer và verifier. Có thể cần chuyển từ RSA sang EC/PSS; cập nhật allowlist có kiểm thử, public key type và claim validation, không để token tự quyết.
- **Thay issuer / multi-tenant:** mỗi issuer phải được ràng buộc với một tập khóa riêng và validator issuer/audience phù hợp; không dùng JWKS chung không có kiểm soát để hợp thức hóa mọi token.

Một token có `kid` không tồn tại **không nên** được tự chấp nhận "tạm thời" trong lúc JWKS lỗi. Fail closed đối với xác minh credential là nguyên tắc cơ bản: trả lỗi và giám sát thay vì bỏ kiểm tra chữ ký.

## 13. Vận hành an toàn: JWKS endpoint, cache, latency và alerts

### 13.1. Nguồn tin cậy và transport

1. Dùng **HTTPS** cho JWKS và issuer metadata trong production; xác minh chứng chỉ TLS, DNS và quyền sở hữu endpoint.
2. Giới hạn outbound HTTP của Resource Server đến **những JWKS endpoint đã được cấu hình/allowlist**; không tải URL từ `jku`/`x5u` hoặc request của client.
3. JWKS chỉ xuất bản **public keys**; private signing keys giữ ở IdP/KMS/HSM, không gửi qua public endpoint, không đặt trong image container của Resource Server.
4. Các proxy/CDN cache JWKS cần chính sách TTL/ETag hợp lý. Khi rotation, verify dữ liệu cache từng tầng; lúc xảy ra sự cố, việc thay response origin có thể chưa đủ.
5. Giới hạn timeout, kết nối, retry/backoff và quan sát lỗi HTTP 404/5xx/TLS theo thư viện/client thực tế. Đừng để mỗi request token xấu tạo bão tải JWKS.

### 13.2. Monitoring

Ghi nhận các loại lỗi đã **ẩn token và dữ liệu nhạy cảm**:

- `invalid_token` do parse, signature, missing key/unknown kid, timestamp, issuer hoặc audience.
- JWKS fetch latency, HTTP errors, cache hit/miss/refresh và số lần request sau rotation nếu instrument được.
- Tỷ lệ 401/403 theo endpoint và phiên bản triển khai, tách authorization failure với authentication failure.
- Phân bố `kid` trong token **theo giá trị đã kiểm soát/được chuẩn hóa** để xem key-a đã giảm xuống hay chưa; header kid đến từ token chưa tin cậy nên không dùng làm key metric thả nổi không giới hạn/cardinality cao.
- Thời gian phát token cuối bằng khóa cũ, maximum JWT TTL, clock skew và cache expiry để chọn mốc retirement.

**Không log raw JWT, Authorization header, private key, public key nội bộ không cần thiết, token exchange hay payload có PII**. Có thể log loại lỗi, issuer/tenant đã được xác minh theo whitelist, endpoint và correlation ID nếu đã được kiểm soát.

### 13.3. Runbook khi chuẩn bị rotation

1. Xác nhận issuer/JWKS endpoint và phạm vi API phụ thuộc; inventory các Resource Server, gateway, cache và các thư viện decoder.
2. Sinh key pair mới trong hệ thống quản lý khóa, gán **kid mới**; xác minh JWKS công bố **public** key-b trước khi bật ký mới.
3. Giám sát nhiều Resource Server: mỗi node có thể tải được key-b trong khi vẫn xác minh token key-a. Chạy staging test với cả hai loại token.
4. Đổi signing key tại Authorization Server sang key-b, giữ key-a trong JWKS.
5. Theo dõi tỷ lệ 401, unknown kid, signature invalid, cache fetch và token còn được ký key-a từ các issuer instance cũ (tránh split-brain rollout).
6. Đợi đủ cửa sổ token max TTL + skew + replication/cache hợp lý; xác nhận issuer instance đã ngừng ký key-a.
7. Loại key-a theo chính sách, xác minh mọi node sau cache refresh, kiểm tra 401 cho token không còn được chấp nhận và vẫn 200 cho token key-b hợp lệ.
8. Ghi nhận audit, rollback plan, thời gian và người phê duyệt; không bật lại private key cũ nếu nguyên nhân rotation là lộ khóa.

## 14. Các lỗi phổ biến và cách chẩn đoán

| Triệu chứng | Nguyên nhân cần xem | Biện pháp |
| --- | --- | --- |
| Tất cả token bị 401 ngay sau deploy | Issuer/JWKS sai, audience chưa đúng, thuật toán khác, TLS/DNS/proxy lỗi. | So sánh claim `iss`/`aud`, cấu hình decoder và JWKS thật; không tắt validation. |
| Chỉ token có `kid` mới bị 401 | JWKS chưa publish key mới, CDN cache, node chưa refresh, kid trùng. | Publish-before-sign, quan sát JWKS từ từng node, đổi kid mới duy nhất. |
| Token key-a còn hạn bị 401 sau rotation | Gỡ public key-a sớm, cache refresh ra JWKS chỉ chứa key-b. | Giữ overlap đủ lâu trong rotation bình thường; khác với emergency revoke. |
| Token key-a vẫn được nhận sau khi gỡ khóa | Decoder/proxy giữ cache cũ hoặc token vẫn có chữ ký hợp lệ theo khóa cache. | Kiểm chứng cache refresh/eviction, TTL token; triển khai revoke chủ động nếu cần chặn tức thời. |
| Chữ ký hợp lệ nhưng audience sai | Decoder chỉ kiểm tra signature hoặc issuer. | Bổ sung validator `aud` với audience ứng dụng đúng. |
| Token từ môi trường test được nhận ở prod | Cùng key/issuer hoặc thiếu issuer/audience validation, trust quá rộng. | Tách issuer/keys/audiences theo môi trường và xác minh nghiêm ngặt. |
| HTTP 403 dù token hợp lệ | Không có `SCOPE_orders.read`, converter khác claims, hoặc rule phân quyền quá chặt. | Kiểm tra authority mapping và rule endpoint; không nghi ngờ signature khi request đã authenticated. |
| Signature invalid sau thay algorithm | Decoder allowlist RS256 còn issuer ký PS256/ES256. | Đồng bộ hợp đồng thuật toán và test; không cho phép tất cả algorithm. |
| 401 ngẫu nhiên giữa các pod | JWKS/cache khác nhau, proxy khác nhau, đồng hồ lệch, node issuer không đồng bộ. | So sánh kid, time, JWKS và cache của từng pod; đồng bộ đồng hồ và rollout. |
| Startup không qua khi IdP offline | Discovery ở startup hoặc network dependency cụ thể. | Cân nhắc issuer-uri + jwk-set-uri, readiness/startup strategy và cache theo hệ thống. |
| Đọc được payload JWT nhưng không thể gọi API | Decode Base64URL không đồng nghĩa token được ký/được phép. | Dùng `JwtDecoder` xác minh đầy đủ; kiểm tra claims và authorities. |

### Quy trình debug có thứ tự

1. Ghi lại request method/path, response 401 hay 403 và loại lỗi ở server; **không công khai raw token**.
2. Kiểm tra token đến API là access token đúng loại cho Resource Server, không phải ID Token/refresh token.
3. Quan sát header `alg`/`kid` và claims `iss`/`aud`/`exp` một cách an toàn để xác định nhóm lỗi; nhớ rằng chúng chưa đáng tin trước khi verify.
4. Xác nhận nguồn JWKS do server cấu hình, TLS, HTTP status, key `kid`, `kty` và `alg` có tương thích hay không.
5. Nếu chữ ký đúng, kiểm tra validator issuer/audience/time; nếu JWT được xác thực nhưng 403, kiểm tra scope/authority mapping và quyền dữ liệu.
6. Nếu chỉ xảy ra sau rotation, đối chiếu timeline publish/sign/retire, cache TTL và các issuer instance đang ký.
7. Viết test regression cho cả key-a/key-b và claim âm tính, tránh sửa bằng cách tắt verifier hoặc mở rộng trust.

## 15. Câu hỏi tự kiểm tra

**1. Có nên gửi private key vào JWKS để Resource Server kiểm tra JWT không?**

**Không.** Với chữ ký bất đối xứng, issuer dùng private key để ký và công bố public key để Resource Server xác minh. Đưa private key vào JWKS làm mất toàn bộ ranh giới an toàn.

**2. `kid` của JWT có đảm bảo token đến từ issuer đúng không?**

**Không.** Client có thể tạo bất cứ `kid` nào. Decoder chỉ dùng kid chọn khóa trong **tập khóa đã được cấu hình tin cậy**, sau đó vẫn phải xác minh signature/claims.

**3. Vì sao chỉ cấu hình `jwk-set-uri` chưa đủ?**

Có URL khóa không đồng nghĩa có validator issuer, audience và các business constraints cần thiết. Phải bảo đảm các điều kiện đó hiện diện trong decoder và authorization rule.

**4. Khi đổi khóa, có được gỡ ngay public key cũ khỏi JWKS không?**

Với **rotation bình thường**, không nếu vẫn có token ký khóa cũ còn hạn. Cần overlap. Với **khóa bị lộ**, có thể chấp nhận gián đoạn để giảm rủi ro nhưng phải xử lý cả caching và revoke chủ động.

**5. Test `with(jwt())` có chứng minh JWKS rotation không?**

Không. Nó giúp kiểm tra authorization khi đã có principal mô phỏng; chưa thử JWS signature, remote JWKS, cache hay issuer/audience validation của decoder.

**6. Xóa key-a khỏi JWKS có làm tất cả token key-a bị vô hiệu ngay tức thì không?**

Không chắc. Một số decoder có thể còn cache public key-a. Đó không phải một cơ chế revocation có thời gian thực được đảm bảo.

## 16. Ghi nhớ

- `JwtDecoder` xác thực **JWT** bằng public key từ JWK Set và validator claims; mặc định không cấp token.
- `kid` là gợi ý **chọn** khóa trong tập tin cậy; `alg` phải có allowlist; **signature + issuer + audience + thời gian + authorization** là các lớp độc lập.
- Dùng `issuer-uri` để tận dụng discovery khi thích hợp; dùng thêm `jwk-set-uri` khi muốn kiểm soát nguồn JWKS và giảm dependency discovery startup; với bean custom phải tự cấu hình validator chính xác.
- Rotation bình thường luôn theo thứ tự: **công bố public key mới trước → ký token mới → overlap khóa cũ/khóa mới → nghỉ khóa cũ khi hết cửa sổ hợp lệ**.
- JWKS caching/timeout/proxy khiến việc thay khóa có độ trễ; đừng hứa rollback/retirement/revocation tức thời mà không có cơ chế kiểm chứng.
- Test đủ ba tầng: **MockMvc authorization**, **decoder signature/claims**, và **integration với remote JWKS thực/mock có kiểm soát**.

**Nguyên tắc thiết kế:** Resource Server không tin header tự khai của JWT; nó tin **issuer và key source do server cấu hình**, xác minh crypto/claims trước khi chuyển sang quyết định cấp quyền. Khóa ký có vòng đời độc lập với phiên người dùng và việc thu hồi token; cần vận hành rotation dựa trên dữ liệu token TTL và cache, không chỉ đổi một trường `kid`.