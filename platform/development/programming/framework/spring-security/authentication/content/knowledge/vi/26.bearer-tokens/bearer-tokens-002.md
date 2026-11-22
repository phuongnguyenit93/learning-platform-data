# OAuth2 Resource Server tiếp nhận và xác thực token trong Spring Security

## 1. Mục tiêu

Một API nhận request có header `Authorization: Bearer <access-token>` phải quyết định **token có được cấp bởi nguồn đáng tin, có hiệu lực, dành cho API này và mang quyền phù hợp hay không**. Spring Security cung cấp **OAuth2 Resource Server** để làm việc này: giải mã/xác minh JWT hoặc gọi token introspection với opaque token, dựng `Authentication`, sau đó áp dụng authorization.

Bài học thuộc chủ đề **Bearer token** của module Spring Security - authentication. Sau bài học, bạn có thể:

- Giải thích vai trò của Resource Server (RS) so với Authorization Server (AS) và OAuth2 Client.
- Theo dõi đường đi từ Bearer header đến `BearerTokenAuthenticationFilter`, provider, `SecurityContext` và quyền truy cập.
- Phân biệt xác minh **JWT ký số** với **opaque token qua introspection**.
- Kiểm chữ ký, issuer, audience, hạn dùng, scope/authority; tránh các kiểu token confusion.
- Dựng API Spring Boot 3.x / Spring Security 6.x / Java 17+ và kiểm thử 401, 403, 200.
- Hiểu giới hạn của token validation đối với tenant, account status, dữ liệu nghiệp vụ, key rotation, thu hồi token và WebFlux.

Ví dụ chính sử dụng **Spring MVC/Servlet**. Mẫu WebFlux được phân biệt riêng. Resource Server **không tự cấp access token**, không thay thế Authorization Server và không tự cung cấp trang login.

## 2. Resource Server trong mô hình OAuth2

Có ba vai trò cần phân biệt:

| Vai trò | Trách nhiệm |
| --- | --- |
| **Authorization Server** | Xác thực/cấp quyền theo luồng thích hợp, phát access token, có thể công bố JWKS và introspection endpoint |
| **Client** | Nhận access token theo quyền được cấp rồi gửi token tới API đích |
| **Resource Server** | Bảo vệ API, xác minh access token và chỉ cho phép thao tác có quyền phù hợp |

Ví dụ nhân viên dùng một ứng dụng đọc báo cáo. AS phát một access token có audience `reports-api` và scope `reports.read` cho client. Client gửi:

```http
GET /api/reports HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
```

Spring Security kiểm tra token trước khi controller truy cập dữ liệu báo cáo. Có token hợp lệ **chưa đủ** để đọc báo cáo của bất kỳ tenant hoặc người dùng nào: hệ thống còn phải kiểm tra ownership và chính sách nghiệp vụ.

Dòng xử lý:

```text
Client
  │ Bearer access token qua HTTPS
  ▼
Spring Security Filter Chain
  │ Trích xuất credential
  ▼
AuthenticationManager / Provider
  │ JWT decoder hoặc opaque introspector
  ▼
Authenticated principal + GrantedAuthorities
  │
  ▼
AuthorizationFilter / @PreAuthorize / domain policy
  │
  ├── Đủ quyền → Controller/Service
  └── Thiếu quyền → Từ chối request
```

**Bearer** nghĩa là bên giữ được token có khả năng sử dụng nó khi không có bảo vệ sender-constrained bổ sung. Vì thế truyền qua HTTPS, giữ token an toàn, giảm thời gian sống và tránh lưu token trong log/URL là yêu cầu thiết yếu.

## 3. Token được đọc và xử lý như thế nào?

Trong Servlet stack, Spring Security cung cấp `BearerTokenAuthenticationFilter`. Bộ lọc thường dùng `BearerTokenResolver` để đọc header `Authorization: Bearer ...`, sau đó tạo `BearerTokenAuthenticationToken` **chưa xác thực**.

Luồng JWT:

```text
HTTP Authorization: Bearer eyJ...
          ↓
BearerTokenAuthenticationFilter
          ↓ BearerTokenAuthenticationToken
AuthenticationManager (thường là ProviderManager)
          ↓
JwtAuthenticationProvider
          ├── JwtDecoder (ví dụ NimbusJwtDecoder)
          │   ├── Kiểm chữ ký và public JWK
          │   └── Validate issuer, timestamps, audience và policy
          └── JwtAuthenticationConverter
                 └── scopes/claims → GrantedAuthorities
          ↓
JwtAuthenticationToken (authenticated)
          ↓
SecurityContextHolder
          ↓
Authorization rules → API Controller
```

Nếu token là opaque và cấu hình introspection, provider tương ứng là `OpaqueTokenAuthenticationProvider`, dùng `OpaqueTokenIntrospector` để hỏi Authorization Server. Kết quả thường là `BearerTokenAuthentication` chứa `OAuth2AuthenticatedPrincipal`.

Không tự dựng filter bằng `request.getHeader("Authorization").substring(7)`: framework đã xử lý header không hợp lệ, sai scheme và nhiều kiểu lỗi theo Bearer Token specification. Theo mặc định, token nằm trong **Authorization header**. Không khuyến khích token trong query string vì URL dễ lộ qua history, access logs, Referer và công cụ giám sát.

### Authentication khác Authorization

**Authentication** trả lời “token có hợp lệ và có thể tin theo cấu hình của API không?”. **Authorization** trả lời “principal đã xác thực có được thực hiện thao tác này trên tài nguyên này không?”.

Một token có issuer, chữ ký và audience hợp lệ nhưng thiếu scope `reports.read` vẫn phải bị từ chối khi yêu cầu đọc báo cáo. Trong trường hợp thường gặp, thiếu token hoặc token sai → HTTP **401**; token hợp lệ nhưng thiếu authority → HTTP **403**.

## 4. JWT: chữ ký, claims và các điều kiện bắt buộc

JWT access token thường có dạng `header.payload.signature` (JWT được ký bằng JWS). Có thể giải mã Base64URL để đọc claims **mà không có private key**, vì vậy payload **không phải nội dung được mã hóa bí mật**. Việc đọc được payload **không chứng minh** token đáng tin.

Ví dụ payload minh họa (không phải JWT có thể sử dụng):

```json
{
  "iss": "https://idp.example.test/realm/training",
  "sub": "person-42",
  "aud": ["reports-api"],
  "scope": "reports.read reports.write",
  "iat": 1761000000,
  "nbf": 1761000000,
  "exp": 1761003600
}
```

Các trường quan trọng:

| Kiểm tra | Mục tiêu |
| --- | --- |
| Chữ ký + thuật toán | Bảo đảm dữ liệu được ký bằng khóa tin cậy và thuật toán được phép; từ chối `alg=none`, khóa/thuật toán không hợp lệ |
| `iss` | Đúng issuer mà API cho phép; không nhận token của issuer tùy ý |
| `aud` | Có audience/resource identifier của **API này**, không nhận token dành cho API khác |
| `exp` | Token còn hạn, kể cả cấu hình sai lệch đồng hồ hợp lý |
| `nbf` | Token đã đến thời điểm được phép sử dụng |
| `iat` | Thời điểm cấp, đối chiếu các quy tắc phát hành nếu hệ thống yêu cầu |
| `scope` hoặc `scp` | Phạm vi đã cấp, được chuyển thành authorities |
| `sub` / `client_id` | Chủ thể là người dùng hoặc client application; giải thích theo grant type và hợp đồng AS |
| `typ`, token profile | Kiểm đúng loại access token nếu policy/AS yêu cầu, tránh nhầm ID token |

**Sai audience là lỗi rất thường gặp.** Một JWT do AS tin cậy phát cho `inventory-api` có thể có chữ ký và `exp` hợp lệ, nhưng `reports-api` **không** được nhận chỉ vì cùng issuer. Kiểm scope không thay thế kiểm audience.

**JWT ký số không tự động bị vô hiệu hóa ngay khi user logout hoặc account bị khóa.** Nếu chỉ kiểm chữ ký và `exp`, token có thể tiếp tục hợp lệ đến khi hết hạn. Hệ thống cần thời hạn token phù hợp, revocation/denylist hoặc introspection nếu muốn phản ánh thu hồi trước hạn.

## 5. JWT so với opaque token

| Thuộc tính | JWT local validation | Opaque token introspection |
| --- | --- | --- |
| Hình dạng | Dữ liệu claims + chữ ký, thường là ba phần | Chuỗi không được giải nghĩa trực tiếp tại RS |
| Cách xác minh | `JwtDecoder` kiểm chữ ký + claims theo JWK và validator | `OpaqueTokenIntrospector` hỏi AS về `active` và metadata |
| Mạng mỗi request | Thường không, trừ lúc tải/refresh JWK | Thường có request đến introspection endpoint |
| Thu hồi token | Cần chính sách riêng, có thể chưa cập nhật ngay | Có thể thấy trạng thái thu hồi nhanh hơn tùy AS/cache |
| Principal sau xác thực | Thường `JwtAuthenticationToken` / `Jwt` | Thường `BearerTokenAuthentication` / `OAuth2AuthenticatedPrincipal` |
| Ánh xạ scope | `SCOPE_<scope>` theo convention | `SCOPE_<scope>` theo convention |

**Không nhầm định dạng với cách xác minh.** Một JWT cũng có thể được introspect để kiểm tra revocation; một opaque token không có JWT payload cho RS tự đọc. Chọn phương án theo hợp đồng AS, mức độ tin cậy, độ trễ, khả năng thu hồi và bảo vệ API.

## 6. Cấu hình Resource Server JWT trong Spring Boot 3

Ví dụ dưới đây dùng Java 17+, Spring Boot 3.x, Spring Security 6.x, Spring MVC. Dự án có Gradle wrapper, plugin Spring Boot và dependency management chuẩn; Authorization Server/JWKS tồn tại bên ngoài ứng dụng.

### 6.1. Dependencies

Đoạn `dependencies` trong `build.gradle`:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Starter resource server kéo các thành phần để kiểm Bearer JWT. Nếu khai báo các thư viện Spring Security thủ công, JWT còn cần `spring-security-oauth2-jose` ngoài `spring-security-oauth2-resource-server`.

### 6.2. Issuer, JWKS URL và audience

Tạo `src/main/resources/application.yml`:

```yaml
security:
  jwt:
    issuer: ${JWT_ISSUER}
    jwk-set-uri: ${JWT_JWK_SET_URI}
    audience: ${JWT_AUDIENCE}
```

Ba khóa `security.jwt.*` ở đây là **custom properties của ví dụ**, được tiêm vào `JwtDecoder` bean ở phần 6.3. Chúng không tự động kích hoạt resource server nếu thiếu cấu hình Java bên dưới.

Giá trị môi trường có thể như sau:

```bash
export JWT_ISSUER='https://idp.example.test/realm/training'
export JWT_JWK_SET_URI='https://idp.example.test/realm/training/protocol/openid-connect/certs'
export JWT_AUDIENCE='reports-api'
```

URL chứa `example.test` **chỉ để minh họa**, không phải Authorization Server hoạt động. Thực tế phải xác định chính xác issuer (khớp `iss`), đường dẫn JWKS do AS công bố và audience AS cấp cho API. **Không tự lấy JWKS URI hoặc issuer đáng tin từ query/header hoặc từ JWT chưa kiểm chứng.**

### 6.3. Java source hoàn chỉnh

Các tệp cùng package `com.example.resourceapi`, nằm trong `src/main/java/com/example/resourceapi/`.

**`ResourceApiApplication.java`**

```java
package com.example.resourceapi;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ResourceApiApplication {
    public static void main(String[] args) {
        SpringApplication.run(ResourceApiApplication.class, args);
    }
}
```

**`SecurityConfig.java`**

```java
package com.example.resourceapi;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET, "/api/reports")
                        .hasAuthority("SCOPE_reports.read")
                        .anyRequest().authenticated())
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .csrf(AbstractHttpConfigurer::disable)
                .oauth2ResourceServer(resource -> resource
                        .jwt(Customizer.withDefaults()))
                .build();
    }

    @Bean
    JwtDecoder jwtDecoder(
            @Value("${security.jwt.jwk-set-uri}") String jwkSetUri,
            @Value("${security.jwt.issuer}") String issuer,
            @Value("${security.jwt.audience}") String audience) {

        NimbusJwtDecoder decoder =
                NimbusJwtDecoder.withJwkSetUri(jwkSetUri).build();

        OAuth2TokenValidator<Jwt> issuerAndTime =
                JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> audienceRule = token ->
                token.getAudience().contains(audience)
                        ? OAuth2TokenValidatorResult.success()
                        : OAuth2TokenValidatorResult.failure(
                                new OAuth2Error(
                                        "invalid_token",
                                        "Required audience is missing",
                                        null));

        decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(
                        issuerAndTime, audienceRule));
        return decoder;
    }
}
```

**Lý do của từng cấu hình:**

1. `oauth2ResourceServer(...jwt(...))` gắn thành phần kiểm Bearer JWT vào Servlet SecurityFilterChain, dùng `JwtDecoder` bean ở đây.
2. `NimbusJwtDecoder.withJwkSetUri(...)` xác minh chữ ký bằng khóa công khai từ JWK Set đáng tin; không cần hay nên đặt **private signing key của AS** ở RS.
3. `JwtValidators.createDefaultWithIssuer(...)` áp dụng validator issuer và thời gian mặc định. `audienceRule` được **kết hợp**, không thay thế issuer/time, bằng `DelegatingOAuth2TokenValidator`.
4. `reports.read` được ánh xạ theo convention thành `SCOPE_reports.read`. Điều kiện `hasAuthority(...)` áp dụng **authorization** sau khi authentication hợp lệ.
5. `SessionCreationPolicy.STATELESS` đúng với API chỉ chấp nhận Bearer token trong ví dụ. `csrf(AbstractHttpConfigurer::disable)` **chỉ thích hợp ở đây vì API không dùng cookie hoặc browser session làm credential**. Nếu kết hợp UI login/cookie, phải phân tích CSRF và chia security chain phù hợp.
6. `anyRequest().authenticated()` bảo vệ các URL không được cho phép rõ ràng. Trong hệ thống thật, định nghĩa chi tiết policy cho các endpoint ghi/sửa/xóa và dữ liệu đa tenant.

**`ReportController.java`**

```java
package com.example.resourceapi;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ReportController {

    @GetMapping("/api/reports")
    public String reports() {
        return "report: permitted";
    }
}
```

Các tệp Java là chương trình Spring Boot hoàn chỉnh về wiring Resource Server trong project được cấu hình đúng. Phần cấp access token/JWKS do AS ngoài ứng dụng chịu trách nhiệm. Controller chỉ chạy sau khi các filter cho qua request.

### 6.4. Test thủ công với access token từ AS

Chạy từ thư mục project:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Sau khi AS thực sự cấp token **cho audience `reports-api`** có scope `reports.read`, có thể thử:

```bash
curl -i http://localhost:8080/api/reports
curl -i -H 'Authorization: Bearer <VALID_ACCESS_TOKEN>' http://localhost:8080/api/reports
```

Placeholder cần thay bằng token thật trong môi trường test. Đừng commit token, copy vào tài liệu công khai hoặc đưa vào lịch sử shell dùng chung.

Với token hợp lệ, endpoint trả HTTP 200, body kỳ vọng:

```text
report: permitted
```

Request thiếu token thường nhận 401. Token chữ ký đúng nhưng audience sai/hết hạn vẫn bị từ chối; token đã xác thực mà thiếu scope `reports.read` thường nhận 403. Đây là **kết quả kỳ vọng theo cấu hình**, không phải stdout/HTTP đã quan sát từ AS trong bài này. Trên mạng thực tế, sử dụng HTTPS.

## 7. Cấu hình tự động với issuer-uri

Nếu không cần custom decoder, Spring Boot hỗ trợ cấu hình JWT Resource Server bằng issuer URI:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/realm/training
```

Khi có starter và cấu hình `oauth2ResourceServer(...jwt(...))` thích hợp, Spring Security có thể khám phá metadata/JWKS theo issuer và xác minh chữ ký, `iss`, `exp`, `nbf`. Tuy vậy, **phải kiểm tra audience theo yêu cầu API**; không giả định issuer-uri đã xác minh mọi audience.

Có thể khai báo `jwk-set-uri` khi muốn tách cấu hình khóa khỏi discovery, nhưng không vì vậy được bỏ issuer/time validators. Với các phiên bản Spring Boot/Security khác nhau, thời điểm discovery, tải khóa hoặc startup coupling có thể khác; dùng tài liệu đúng phiên bản và kiểm thử IdP tạm thời không sẵn sàng. Khi đã tự khai báo `JwtDecoder` bean như phần 6.3, bean đó là nguồn cấu hình xác minh chính, không trông đợi Boot tự kết hợp các thiết lập một cách không được bảo đảm.

## 8. Scopes và GrantedAuthorities

Với JWT có claims:

```json
{
  "sub": "alice",
  "scope": "reports.read reports.write"
}
```

Spring Security thường tạo các authorities:

```text
SCOPE_reports.read
SCOPE_reports.write
```

Do đó rule:

```java
.requestMatchers(HttpMethod.GET, "/api/reports")
.hasAuthority("SCOPE_reports.read")
```

là đoạn DSL bên trong `authorizeHttpRequests`. Nó **khác** `hasRole("ADMIN")`, vốn thông thường tìm `ROLE_ADMIN`. Không tự coi `scope=admin` là `ROLE_ADMIN` nếu hệ thống không có ánh xạ quyền được thiết kế và kiểm soát.

Khi provider dùng claim khác, có thể tùy biến `JwtGrantedAuthoritiesConverter` và `JwtAuthenticationConverter`. Ví dụ **đoạn mã thay cho cấu hình jwt mặc định**, đặt trong phương thức tạo filter chain sau khi bổ sung imports tương ứng:

```java
JwtGrantedAuthoritiesConverter permissions =
        new JwtGrantedAuthoritiesConverter();
permissions.setAuthoritiesClaimName("permissions");
permissions.setAuthorityPrefix("PERMISSION_");

JwtAuthenticationConverter converter = new JwtAuthenticationConverter();
converter.setJwtGrantedAuthoritiesConverter(permissions);

http.oauth2ResourceServer(resource -> resource
        .jwt(jwt -> jwt.jwtAuthenticationConverter(converter)));
```

Import:

```java
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;
```

Đoạn này không phải class độc lập; chỉ cấu hình khi AS có hợp đồng claim `permissions` đáng tin và API định nghĩa chính sách rõ ràng. Nếu ứng dụng cần kiểm quyền trên đối tượng (report thuộc tenant nào, chủ sở hữu nào), scope chỉ là điều kiện ban đầu; service vẫn phải kiểm tra bằng danh tính đã xác minh và dữ liệu nghiệp vụ.

Với client-credentials grant, token có thể đại diện **ứng dụng client** thay vì một nhân viên; không tự giả định mọi bearer token đều có một local user.

## 9. Test MockMvc: phân biệt 401, 403 và thành công

Trong `src/test/java/com/example/resourceapi/ResourceApiSecurityTest.java`:

```java
package com.example.resourceapi;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = {
        "security.jwt.issuer=https://idp.example.test/realm/training",
        "security.jwt.jwk-set-uri=https://idp.example.test/jwks",
        "security.jwt.audience=reports-api"
})
@AutoConfigureMockMvc
class ResourceApiSecurityTest {

    @Autowired
    MockMvc mvc;

    @Test
    void missingTokenIsUnauthorized() throws Exception {
        mvc.perform(get("/api/reports"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void authenticatedWithReadScopeCanAccess() throws Exception {
        mvc.perform(get("/api/reports")
                .with(jwt().authorities(
                        new SimpleGrantedAuthority("SCOPE_reports.read"))))
                .andExpect(status().isOk())
                .andExpect(content().string("report: permitted"));
    }

    @Test
    void authenticatedWithoutReadScopeIsForbidden() throws Exception {
        mvc.perform(get("/api/reports")
                .with(jwt().authorities(
                        new SimpleGrantedAuthority("SCOPE_other"))))
                .andExpect(status().isForbidden());
    }
}
```

Chạy:

```bash
./gradlew test
```

Kỳ vọng cả ba test pass trong một project Boot 3.x cấu hình như trên. **Giới hạn:** helper `jwt()` của `spring-security-test` đưa `Authentication` giả lập vào request; **không kiểm chữ ký JWT, `iss`, `aud`, thời hạn hay JWK từ AS thật**. Vì vậy những test này chứng minh security rule/controller, chưa chứng minh JWT decoder đúng.

Để kiểm tra end-to-end đường xác thực, chạy test HTTP có `Authorization: Bearer <jwt-thực-được-ký-bằng-khóa-test>` qua `BearerTokenAuthenticationFilter` và `JwtDecoder`, cùng một JWKS test server được kiểm soát. Cần phủ: chữ ký sửa, thuật toán sai, issuer sai, audience khác, hết hạn, chưa tới `nbf`, `kid` không khớp, JWKS rotation, token hợp lệ thiếu scope và AS/JWKS không sẵn sàng. Không dùng private key production cho test.

## 10. Nhánh opaque token với introspection

Một số AS phát opaque access token; RS không thể tự giải mã/kiểm chữ ký. Khi đó dùng OAuth2 token introspection endpoint. Ví dụ **cấu hình thay thế nhánh JWT**, vẫn giữ dependency Resource Server:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://idp.example.test/oauth2/introspect
          client-id: ${INTROSPECTION_CLIENT_ID}
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
```

Và thay đoạn `.jwt(Customizer.withDefaults())` trong DSL bằng:

```java
.oauth2ResourceServer(resource -> resource
        .opaqueToken(Customizer.withDefaults()))
```

Đây là đoạn mã cấu hình, không phải class độc lập. Nhánh opaque dùng `OpaqueTokenAuthenticationProvider` và `OpaqueTokenIntrospector`; token được gửi đến endpoint introspection cùng thông tin client xác thực. Ví dụ response minh họa:

```json
{
  "active": true,
  "sub": "person-42",
  "client_id": "web-client",
  "scope": "reports.read"
}
```

AS trả `active=false` khi token không còn hợp lệ theo chính sách của mình; Resource Server từ chối. Khi `active=true`, Spring Security có thể ánh xạ scope thành `SCOPE_reports.read` để authorization.

**Cần kiểm tra cả audience/resource và policy của API trong introspection workflow.** Một token active ở AS không mặc nhiên được dùng cho mọi RS. Nếu endpoint không trả đủ metadata, cần ràng buộc resource ở AS hoặc thêm logic kiểm tra tin cậy phù hợp.

Introspection thường có round trip mạng trên mỗi request, nên cần timeout, metrics, rate limit, circuit breaker/backoff hợp lý và quyết định cache TTL. Cache tăng thông lượng nhưng có thể làm chậm phát hiện token bị thu hồi. Không log token hoặc introspection client secret. Nếu dùng introspection để kiểm một token có hình dạng JWT, Spring Security vẫn xử lý theo **nhánh introspection/opaque**, không tự đổi sang `JwtAuthenticationToken`.

## 11. Mã trạng thái 401, 403 và header phản hồi

| Tình huống | Thường trả | Giải thích |
| --- | --- | --- |
| Thiếu token ở endpoint protected | 401 | Chưa có Authentication |
| JWT hỏng, chữ ký sai, issuer/audience sai, hết hạn | 401 | Token không xác thực được |
| Bearer token hợp lệ nhưng không có scope cần thiết | 403 | Authentication thành công, Authorization bị từ chối |
| Token hợp lệ, có quyền, policy dữ liệu cho phép | 2xx | Controller được thực thi |
| AS/introspection không sẵn sàng | Lỗi xác thực/hạ tầng cần xử lý riêng | Không được cho request đi qua khi chưa xác minh |

Cơ chế bearer theo RFC 6750 có thể gửi `WWW-Authenticate: Bearer` cùng error như `invalid_token` hoặc `insufficient_scope` khi phù hợp. Không hardcode mọi lỗi thành cùng HTTP status nếu ứng dụng có custom `AuthenticationEntryPoint`/`AccessDeniedHandler`; test hành vi thực tế của filter chain đang triển khai.

**Fail closed** khi không thể xác thực. Nhưng logging/metrics vẫn cần phân biệt token thực sự sai với lỗi mạng đi tới JWKS/introspection, tránh quy chụp sự cố vận hành thành lỗi người dùng.

## 12. Sai lầm bảo mật phổ biến

1. **Chỉ Base64-decode JWT và tin payload.** Dữ liệu chưa xác minh có thể do attacker tự tạo. Dùng `JwtDecoder` và validator đúng.
2. **Bỏ audience validation.** JWT hợp lệ của một resource khác có thể được nhận nhầm. AS phải phát token đúng audience và RS phải kiểm.
3. **Tin mọi issuer hoặc JWK URL do client khai.** Token chưa xác minh không thể tự chọn nguồn khóa đáng tin. Dùng allowlist/config an toàn.
4. **Dùng ID token thay access token.** OIDC ID token dành cho relying party, không phải bearer access token dành cho API.
5. **Nhầm scope với role nội bộ.** `SCOPE_reports.read` không tự đồng nghĩa `ROLE_ADMIN`.
6. **Chỉ kiểm `authenticated()` khi có dữ liệu nhiều tenant.** Cần scope và quyền truy cập đối tượng.
7. **Tắt CSRF toàn hệ thống khi ứng dụng vẫn dùng session/cookie.** Thiết kế chain riêng cho API bearer và UI browser.
8. **Đặt bearer token trong URL hoặc log.** Token có thể bị tái sử dụng bởi ai lấy được.
9. **Không quản lý key rotation/cache.** JWKS thay đổi hoặc IdP bị lỗi có thể làm gián đoạn API.
10. **Coi `jwt()` MockMvc là test chữ ký.** Nó bypass decoder; bổ sung integration test JWT thật.
11. **Chỉ kiểm `exp` và bỏ trạng thái account.** JWT có thể còn hạn khi tài khoản bị khóa; phải có revocation/account policy.
12. **Tin “scope=admin” từ token sai issuer/audience.** Authorization chỉ có ý nghĩa sau authentication đã được chứng minh.

## 13. Multi-issuer và gateway

Khi API chấp nhận tokens từ nhiều AS/tenant, cần cấu hình một tập issuer được tin rõ ràng và chọn `AuthenticationManager`/decoder phù hợp. Có thể dùng cơ chế `AuthenticationManagerResolver<HttpServletRequest>` hoặc hỗ trợ nhiều issuer của Spring Security; điều quan trọng là **issuer allowlist**, xác minh chữ ký sau khi chọn, audience đúng cho API và tenant isolation.

Việc đọc claim `iss` **trước** verification để chọn decoder chỉ là thao tác định tuyến, không phải chấp nhận claim đó là thật. Không lấy một URL bất kỳ trong `iss` chưa xác thực rồi đi tải khóa theo yêu cầu client.

Nếu API nằm sau gateway đã kiểm token, hệ thống cần xác định rõ backend có còn kiểm bearer hay tin danh tính được chuyển tiếp qua kết nối đã bảo vệ (mTLS, network isolation, header strip/overwrite). Một `X-User` do client tự gửi không phải bảo đảm xác thực. Cũng không chuyển token từ API A sang API B khi audience chỉ dành cho A; cần token exchange hoặc flow cấp token đúng resource khi cần.

## 14. Vận hành và giới hạn

- **Bảo vệ token:** TLS, storage an toàn, không log bearer token, không chia sẻ secret/JWK private key.
- **Tài nguyên:** JWT signature verification tiêu tốn CPU; introspection tiêu tốn network và AS capacity. Đo latency/p95/p99, timeout, JWKS cache, error rates.
- **Đồng bộ thời gian:** `exp`/`nbf` phụ thuộc đồng hồ; dùng clock skew nhỏ hợp lý, không biến nó thành gia hạn token tùy ý.
- **Quyền:** token có scope đúng vẫn cần object-level authorization, kiểm tra tenant và business policy.
- **CORS:** kiểm soát origin của browser, nhưng CORS không phải authentication và không cản non-browser clients.
- **Rate limit:** giới hạn lạm dụng và đảm bảo AS/JWKS không bị quá tải bởi request token sai.
- **Revocation:** cân nhắc short-lived access token, introspection, denylist hoặc kiểm trạng thái nội bộ theo nhu cầu; lựa chọn có ảnh hưởng tới độ trễ thu hồi và thông lượng.
- **Token profile:** khi AS theo RFC 9068 hoặc định dạng riêng, RS cần kiểm các claim/phân loại token được hợp đồng yêu cầu; không chỉ dựa vào chữ ký.

## 15. WebFlux khác ở đâu?

Code Spring MVC ở trên dùng `HttpSecurity`, `SecurityFilterChain` và `JwtDecoder`. Ứng dụng Spring WebFlux dùng `ServerHttpSecurity`, `SecurityWebFilterChain` và `ReactiveJwtDecoder` hoặc `ReactiveOpaqueTokenIntrospector`. Ranh giới tin cậy, kiểm issuer/audience, chữ ký, scope và authorization về bản chất tương tự nhưng API/lifecycle là reactive.

Đoạn WebFlux **chỉ minh họa cấu hình**, chưa phải class chạy độc lập và cần decoder/validation thực:

```java
@Bean
SecurityWebFilterChain api(ServerHttpSecurity http) {
    return http
            .authorizeExchange(exchanges -> exchanges
                    .pathMatchers("/api/**").authenticated()
                    .anyExchange().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2
                    .jwt(Customizer.withDefaults()))
            .build();
}
```

Các kiểu nằm trong `org.springframework.security.config.web.server.ServerHttpSecurity`, `org.springframework.security.web.server.SecurityWebFilterChain` và `org.springframework.security.config.Customizer`. Không copy `HttpSecurity` vào WebFlux hoặc dùng `JwtDecoder` Servlet như một `ReactiveJwtDecoder`.

## 16. Bài tập và kết luận

Thử các tình huống sau trong môi trường test có AS/JWKS kiểm soát:

1. Tạo access token có chữ ký hợp lệ, đúng issuer/scope nhưng `aud=inventory-api`. Tại sao `reports-api` phải từ chối?
2. Gửi token đúng audience nhưng thiếu `reports.read`. Phân tích bước nào trả lỗi và dự kiến 401 hay 403.
3. Kiểm thử JWT sai chữ ký, hết hạn, sai `nbf`, JWKS key rotation và tình huống IdP không sẵn sàng.
4. So sánh latency của JWT local validation với opaque introspection. Thử revoke token để thấy sự khác biệt.
5. Thêm tenant-based access rule ở service. Giải thích vì sao scope `reports.read` không đủ để xem report của tenant khác.
6. Phân biệt `oauth2Login()`, `oauth2Client()` và `oauth2ResourceServer()` trong ứng dụng có cả website và API.

Điều quan trọng cần nhớ: **Resource Server xác minh và áp quyền đối với access token nhận được.** JWT cần chữ ký/issuer/audience/time và quyền; opaque cần introspection cùng metadata/phân quyền đáng tin. Authentication và authorization là hai bước riêng; cả hai đều cần đúng để API an toàn.

**Tài liệu tham khảo chính thức:**

- [Spring Security 6.5 – OAuth2 Resource Server](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/index.html)
- [Spring Security 6.5 – JWT](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html)
- [Spring Security 6.5 – Opaque Token](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/opaque-token.html)
- [Spring Security 6.5 – Bearer Tokens](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/bearer-tokens.html)
- [RFC 6750 – Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750), [RFC 7662 – Token Introspection](https://www.rfc-editor.org/rfc/rfc7662), [RFC 9068 – JWT Access Token Profile](https://www.rfc-editor.org/rfc/rfc9068).