# Phụ thuộc Resource Server, JOSE và kiểm thử bảo mật

Một ứng dụng Spring Boot bảo vệ API bằng **OAuth 2.0 Bearer Access Token** cần ba phần hoạt động đồng bộ: **dependency Resource Server**, công cụ **JOSE/JWT** phù hợp với cách phát hành token, và **kiểm thử bảo mật** chứng minh ứng dụng chỉ chấp nhận token hợp lệ, đúng audience và đủ quyền truy cập.

Bài học đi từ khâu khởi tạo đến kiểm thử, dùng ví dụ **Spring Boot 3.x, Spring Security 6.x, Java 17+ và Spring MVC (Servlet)**. Nếu dùng phiên bản mới hơn hoặc khác nhánh, đối chiếu thuộc tính cấu hình và các starter mà phiên bản đó hỗ trợ. Ví dụ minh họa một API đơn hàng nhận Bearer token do Authorization Server bên ngoài phát hành.

## 1. Xác định đúng vai trò trước khi thêm dependency

Trong hệ thống OAuth 2.0/OIDC:

| Thành phần | Vai trò | Cấu hình Spring Security thường gặp |
| --- | --- | --- |
| **Authorization Server / OpenID Provider** | Xác thực, ủy quyền và phát hành token. | Dịch vụ riêng như Keycloak hoặc Spring Authorization Server. |
| **OAuth 2.0 Client / OIDC Client** | Đưa người dùng đi đăng nhập, nhận authorization code và token. | `spring-boot-starter-oauth2-client`, `oauth2Login()`. |
| **Resource Server** | Nhận Bearer Access Token trong yêu cầu HTTP, kiểm tra token và quyền truy cập API. | `spring-boot-starter-oauth2-resource-server`, `oauth2ResourceServer()`. |

Ví dụ client gọi:

~~~http
GET /api/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer ACCESS_TOKEN
Accept: application/json
~~~

Resource Server cần xác định: token có hợp lệ không, được **issuer nào** phát hành, có còn hiệu lực không, **audience** có chứa API này không và có **scope orders.read** không. Sau đó API còn có thể kiểm tra quyền đối với từng đơn hàng hoặc tenant.

Một API chỉ nhận Bearer token **không bắt buộc** có màn hình OIDC Login hoặc `oauth2Login()`. Ngược lại, OIDC Login trên website cũng **không tự biến mọi request đến API thành một Bearer request hợp lệ**. Nếu một backend đảm nhận cả hai, phải cấu hình security chain phù hợp cho mỗi khu vực.

## 2. Dependency cho Resource Server

### 2.1. Gradle

Trong dự án Spring Boot đã quản lý các phiên bản dependency qua plugin/BOM:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Ý nghĩa:

- **spring-boot-starter-web**: Spring MVC, HTTP controller và servlet runtime.
- **spring-boot-starter-security**: Spring Security, filter chain và cơ chế authorization.
- **spring-boot-starter-oauth2-resource-server**: xác thực Bearer token; trong các bản Spring Boot 3.x phổ biến, starter cũng kéo theo module **JOSE** để hỗ trợ JWT.
- **spring-boot-starter-test**: JUnit 5, Spring Test và công cụ assertion.
- **spring-security-test**: hỗ trợ tích hợp security với MockMvc và các request post processors như `jwt()`, `opaqueToken()`.

Không cần tự ghi version của từng Spring Security artifact nếu đang dùng dependency management của Spring Boot. Ghép các bản module không tương thích dễ gây lỗi lúc khởi động hoặc khi chạy test.

### 2.2. Maven

Tương đương, trong dự án đã dùng Spring Boot parent hoặc BOM:

~~~xml
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
~~~

Chỉ chọn **Gradle hoặc Maven** theo build tool của dự án.

### 2.3. Resource Server và JOSE là hai module khác nhau

Khi cấu hình Spring Security bằng module thủ công thay vì starter Boot, trường hợp JWT thường cần cả:

~~~groovy
dependencies {
    implementation 'org.springframework.security:spring-security-oauth2-resource-server'
    implementation 'org.springframework.security:spring-security-oauth2-jose'
}
~~~

| Module | Công việc |
| --- | --- |
| **spring-security-oauth2-resource-server** | Hỗ trợ lọc Bearer token, xác thực request, cấu hình Resource Server và integration với SecurityContext. |
| **spring-security-oauth2-jose** | Hỗ trợ JWT/JWS, decoder, xử lý chữ ký và claims; dùng các thư viện JOSE/JWT phù hợp. |

Nếu đã thêm starter Boot và dependency tree có JOSE, **không cần khai báo trùng**. Nếu chỉ thêm `spring-security-oauth2-resource-server` thủ công mà quên JOSE, phần xác minh JWT có thể thiếu các lớp cần thiết.

Với **opaque token**, Resource Server thường dùng introspection thay vì JWT decoder. Dù starter có thể chứa JOSE transitively, sự hiện diện của JAR không bắt ứng dụng phải giải mã JWT.

Các lệnh tham khảo để xem dependency tree:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./mvnw dependency:tree
~~~

Trên Windows có thể dùng `.\gradlew.bat` hoặc `.\mvnw.cmd` tùy dự án. Hai lệnh là **phương pháp kiểm tra dependency**, không phải bước viết code bắt buộc.

## 3. JOSE, JWT, JWS, JWE, JWK và JWA

**JOSE** (JSON Object Signing and Encryption) là họ đặc tả để biểu diễn, ký và mã hóa dữ liệu JSON. Các khái niệm thường gặp:

| Thuật ngữ | Nội dung | Vai trò với Resource Server |
| --- | --- | --- |
| **JWT** (JSON Web Token) | Token mang các claims như issuer, subject, audience, thời hạn và scope. | Payload mô tả thông tin xác thực/ủy quyền được token mang theo. |
| **JWS** (JSON Web Signature) | Biểu diễn dữ liệu và chữ ký/MAC để kiểm tra tính toàn vẹn, tính xác thực nguồn ký. | JWT Access Token ký số thường dùng JWS compact. |
| **JWE** (JSON Web Encryption) | Biểu diễn dữ liệu đã được mã hóa để giữ bí mật nội dung. | Không mặc nhiên được giải mã chỉ vì bật `oauth2ResourceServer().jwt()`. |
| **JWK** (JSON Web Key) | Biểu diễn khóa dưới dạng JSON. | JWK Set endpoint có thể công bố public keys để xác minh chữ ký. |
| **JWA** (JSON Web Algorithms) | Tập thuật toán sử dụng cho JWS/JWE. | Ví dụ RS256; verifier phải giới hạn thuật toán được tin cậy. |

JWT được ký dạng JWS compact thường có ba phần:

~~~text
BASE64URL(JOSE_HEADER).BASE64URL(JWT_CLAIMS).BASE64URL(SIGNATURE)
~~~

Ví dụ JOSE Header:

~~~json
{
  "alg": "RS256",
  "kid": "rsa-key-2026",
  "typ": "at+jwt"
}
~~~

Ví dụ payload claims của Access Token:

~~~json
{
  "iss": "https://identity.example.test/realms/demo",
  "sub": "employee-123",
  "aud": ["orders-api"],
  "iat": 1893452400,
  "nbf": 1893452400,
  "exp": 1893456000,
  "scope": "orders.read"
}
~~~

**alg**, **kid** và **typ** là header parameters, không phải JWT claims. **iss**, **sub**, **aud**, **exp** là claims; **scope** là trường thường dùng trong OAuth Access Token profile. Hai khối JSON chỉ là ví dụ minh họa và chưa cấu thành JWT có chữ ký hợp lệ.

**JWT được ký không đồng nghĩa được mã hóa.** Nội dung payload JWS có thể được đọc sau khi giải mã Base64url. Không đưa private key, mật khẩu hoặc thông tin cá nhân không cần thiết vào claims.

### 3.1. Khóa bất đối xứng và JWK Set

Khi issuer ký Access Token bằng RS256:

1. Authorization Server giữ **private key** để ký.
2. Resource Server sử dụng **public key** tương ứng để xác minh.
3. Public keys có thể được công bố dưới dạng JWK Set tại một địa chỉ HTTPS do hệ thống tin cậy cấu hình.
4. Header **kid** giúp chọn khóa trong JWK Set, đặc biệt khi luân chuyển khóa.

Ví dụ URI minh họa của Keycloak:

~~~text
https://identity.example.test/realms/demo/protocol/openid-connect/certs
~~~

Resource Server **không cần** giữ private key để xác minh chữ ký bất đối xứng. Không tự tin địa chỉ JWK do client gợi ý trong token chưa xác minh; phải lấy từ issuer/discovery hoặc cấu hình đã được hệ thống tin cậy.

Thuật toán do header `alg` khai báo **không tự động được phép**: cấu hình decoder phải giới hạn thuật toán và khóa tin cậy. Không chấp nhận `alg: none` hay thay thuật toán theo dữ liệu không đáng tin cậy.

### 3.2. Chuỗi xử lý Bearer JWT

~~~text
HTTP Authorization: Bearer <token>
             |
             v
BearerTokenAuthenticationFilter
             |
             v
JwtAuthenticationProvider / JwtDecoder
             |
             +-- kiểm tra chữ ký với khóa tin cậy
             +-- kiểm tra iss, exp, nbf theo cấu hình
             +-- kiểm tra aud của chính API
             +-- kiểm tra profile/type/claims bổ sung nếu cần
             |
             v
JwtAuthenticationToken
             |
             v
AuthorizationFilter / Method Security
             |
             +-- scope và quyền tài nguyên đủ -> controller
             +-- chưa xác thực được token -> thường 401
             +-- token hợp lệ nhưng thiếu quyền -> thường 403
~~~

Một JWT đúng chữ ký vẫn có thể **sai audience**, hết hạn hoặc không có scope cần thiết. Chữ ký hợp lệ không thay thế authorization.

## 4. Cấu hình JWT Resource Server

### 4.1. Cấu hình tối thiểu với issuer và audience

Ví dụ `src/main/resources/application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.test/realms/demo
          audiences:
            - orders-api
~~~

- **issuer-uri** chỉ nhà phát hành được Resource Server tin cậy; decoder có thể dùng cơ chế discovery phù hợp để tìm metadata/JWK Set.
- **audiences** yêu cầu token được phát hành cho **orders-api**. Một số phiên bản Spring Boot hỗ trợ trực tiếp thuộc tính này; với phiên bản không hỗ trợ, dùng audience validator tùy chỉnh.
- Spring Security JWT decoder xác minh chữ ký, các ràng buộc thời gian và issuer theo cấu hình. **Đừng giả định API tự kiểm tra audience nếu chưa xác nhận cấu hình hoặc validator thực tế.**

Một Authorization Server có thể phát hành token dành cho nhiều API. Nếu API không kiểm tra audience, nó có nguy cơ chấp nhận token dành cho hệ thống khác.

### 4.2. Cấu hình JWK Set URI tường minh

Khi đã biết JWK Set URI và muốn không phụ thuộc vào việc khám phá metadata mỗi khi thiết lập decoder:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.test/realms/demo
          jwk-set-uri: https://identity.example.test/realms/demo/protocol/openid-connect/certs
          audiences:
            - orders-api
~~~

Giữ **issuer-uri** để kiểm tra claim **iss**. Cấu hình `jwk-set-uri` nói Resource Server lấy public keys ở đâu; nó **không tự thay thế kiểm tra issuer**. Thời điểm tải metadata/JWK, cache và làm mới khóa phụ thuộc decoder cùng phiên bản đang sử dụng.

### 4.3. Tự định nghĩa audience validator khi cần

Đây là **phương án thay thế** khi phiên bản Boot chưa cung cấp `audiences` hoặc ứng dụng có chính sách riêng:

~~~java
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
public class JwtValidationConfig {

    private static final String ISSUER =
        "https://identity.example.test/realms/demo";

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withIssuerLocation(ISSUER).build();

        OAuth2TokenValidator<Jwt> audience = jwt ->
            jwt.getAudience().contains("orders-api")
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        "invalid_token",
                        "Unexpected token audience",
                        null));

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(ISSUER),
                audience));

        return decoder;
    }
}
~~~

`JwtValidators.createDefaultWithIssuer` giữ những kiểm tra chuẩn về issuer và thời hạn; validator riêng bổ sung audience. Nếu tự định nghĩa `JwtDecoder`, Spring Boot có thể không dùng decoder auto-configured nữa. **Các validator bắt buộc phải nằm trong decoder thực sự được dùng**. Khi triển khai, đưa issuer/audience thành cấu hình theo môi trường thay vì cố định như ví dụ học tập.

## 5. SecurityFilterChain và API minh họa

Ví dụ API thuần Bearer, không dùng session cookie để xác thực:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth ->
                oauth.jwt(Customizer.withDefaults()));

        return http.build();
    }
}
~~~

- `oauth2ResourceServer(...jwt(...))` yêu cầu Spring Security xác thực Bearer JWT.
- `SessionCreationPolicy.STATELESS` thể hiện API không dựa vào HTTP session.
- `csrf(...disable)` chỉ phù hợp trong ví dụ **API thuần Bearer header**. Với ứng dụng web xác thực bằng cookie, phải cân nhắc CSRF riêng.
- `GET /api/orders` yêu cầu **SCOPE_orders.read**; `POST /api/orders` yêu cầu **SCOPE_orders.write**.
- `anyRequest().denyAll()` đóng các endpoint chưa được khai báo trong ví dụ.

Spring Security thường ánh xạ scope trong JWT, như `"scope": "orders.read orders.write"`, thành authorities **SCOPE_orders.read** và **SCOPE_orders.write**. Với claim custom như `roles` hoặc `permissions`, cần quy tắc chuyển đổi riêng, không mặc nhiên được cấp mọi quyền.

Controller thử nghiệm:

~~~java
import java.util.List;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
public class OrdersController {

    @GetMapping
    Map<String, Object> list(@AuthenticationPrincipal Jwt jwt) {
        return Map.of(
            "subject", jwt.getSubject(),
            "orders", List.of());
    }

    @PostMapping
    ResponseEntity<Map<String, String>> create() {
        return ResponseEntity.status(HttpStatus.CREATED)
            .body(Map.of("status", "created"));
    }
}
~~~

Đây là controller học tập, chưa xử lý lưu dữ liệu hay quyền sở hữu đơn hàng. Một hệ thống thật còn phải kiểm tra tenant, chủ sở hữu và chính sách nghiệp vụ sau khi token đã được xác thực.

## 6. Opaque Token: không dùng JOSE decoder như JWT

Không phải Access Token nào cũng là JWT. Nếu Authorization Server phát hành **opaque token**, API thường gọi **introspection endpoint** để biết token còn `active` và có thuộc tính/quyền nào.

Ví dụ cấu hình, với thông tin xác thực introspection được cung cấp qua biến môi trường:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://identity.example.test/oauth2/introspect
          client-id: REPLACE_WITH_ENV_CONFIGURATION
          client-secret: REPLACE_WITH_ENV_CONFIGURATION
~~~

Hai placeholder phải được thay bằng cơ chế cấu hình bí mật an toàn; không lưu client secret thật vào source code. Trong `SecurityFilterChain`, nhánh Resource Server dùng:

~~~java
.oauth2ResourceServer(oauth ->
    oauth.opaqueToken(Customizer.withDefaults()))
~~~

Đây là đoạn thay thế trong HttpSecurity DSL, không phải tệp Java đứng riêng.

| JWT | Opaque token |
| --- | --- |
| Dùng JwtDecoder và JOSE/JWS để xác minh chữ ký. | Dùng introspection để kiểm tra token từ nhà phát hành. |
| Có thể xác minh cục bộ dựa trên public key đã có. | Thường phụ thuộc endpoint introspection theo cấu hình. |
| Principal thường là `Jwt`. | Principal thường là `OAuth2AuthenticatedPrincipal`. |
| MockMvc có `jwt()`. | MockMvc có `opaqueToken()`. |

Không bật `jwt()` và kỳ vọng opaque token được giải mã. Tương tự, API nhận JWT không nên đổi sang introspection một cách ngẫu nhiên nếu nhà phát hành không hỗ trợ.

## 7. Hai tầng kiểm thử bảo mật phải tách bạch

**Kiểm thử authorization** hỏi: API có chặn đúng request không có quyền, và có cho phép đúng method/scope không?

**Kiểm thử token validation** hỏi: JwtDecoder có từ chối chữ ký giả, issuer sai, audience sai, token quá hạn hoặc thuật toán không được phép không?

Đây là hai loại bằng chứng khác nhau:

| Tầng | Công cụ | Kiểm tra được | Chưa kiểm tra được |
| --- | --- | --- | --- |
| HTTP/authorization | MockMvc + `jwt()`, `opaqueToken()` | Phân quyền theo route, method, authority; trạng thái 401/403/200/201. | Chữ ký JWT và việc JwtDecoder thực sự bác token giả. |
| Mapping claims | Test converter `JwtAuthenticationConverter` | Scope/custom claims được đổi thành authorities theo quy tắc. | Token có được issuer tin cậy ký hay không. |
| JWT decoder | JWT ký bằng khóa test + NimbusJwtDecoder | Chữ ký, issuer, audience, thời hạn, custom validators. | HTTP filter, tải khóa qua JWK Set, chính sách endpoint nếu test riêng decoder. |
| Opaque introspection | Stub `OpaqueTokenIntrospector` hoặc introspection endpoint cục bộ | Trạng thái active, mapping attributes, lỗi mạng/timeout. | Hành vi Authorization Server thực ngoài fixture. |
| HTTP tích hợp | MockMvc hoặc HTTP server + JWT ký thật + JWK Set fixture | Đường Bearer filter, decoder, validators, authorization và HTTP response. | Vận hành production của nhà phát hành nếu không thử riêng. |

Ma trận tối thiểu cho API mẫu:

| Request | Token / quyền | Kết quả mong đợi |
| --- | --- | --- |
| GET /api/orders | Không có token | **401 Unauthorized** |
| GET /api/orders | Bearer token không hợp lệ | **401 Unauthorized** |
| GET /api/orders | Token hợp lệ, chỉ có **orders.write** | **403 Forbidden** |
| GET /api/orders | Token hợp lệ, có **orders.read** | **200 OK** |
| POST /api/orders | Token hợp lệ, chỉ có **orders.read** | **403 Forbidden** |
| POST /api/orders | Token hợp lệ, có **orders.write** | **201 Created** |
| GET /api/orders | JWT chữ ký đúng nhưng audience khác API | **401 Unauthorized** |
| GET /api/orders | JWT hết hạn hoặc chữ ký sai | **401 Unauthorized** |

Thông thường **401** là chưa xác thực được yêu cầu; **403** là yêu cầu đã xác thực nhưng không đủ quyền. Các response nên có challenge phù hợp như `WWW-Authenticate: Bearer` khi áp dụng, không tiết lộ token hoặc chi tiết nội bộ.

## 8. Kiểm thử HTTP bằng MockMvc và spring-security-test

`SecurityMockMvcRequestPostProcessors.jwt()` tạo một Authentication kiểu JWT cho request test, thuận tiện khi thử quyền **SCOPE_orders.read** hoặc **SCOPE_orders.write** mà không cần gọi IdP.

Ví dụ:

~~~java
mockMvc.perform(get("/api/orders")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read"))))
    .andExpect(status().isOk());
~~~

**Ranh giới quan trọng:** `jwt()` không đưa JWT ký thật qua `JwtDecoder`. Nó mô phỏng principal đã xác thực nên **không thể** chứng minh decoder kiểm tra chữ ký, issuer hoặc audience đúng. Khi ép authorities bằng `jwt().authorities(...)`, test cũng **không chứng minh** converter của ứng dụng ánh xạ claims đúng.

### 8.1. Ví dụ lớp test authorization

Với cấu hình và controller ở mục 5, có thể tạo `OrdersSecurityTest.java`:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpHeaders;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.BadJwtException;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@Import(OrdersSecurityTest.TestDecoderConfig.class)
class OrdersSecurityTest {

    @Autowired
    MockMvc mockMvc;

    @TestConfiguration
    static class TestDecoderConfig {
        @Bean
        JwtDecoder jwtDecoder() {
            // Chỉ dùng trong test authorization, không dùng ở production.
            return value -> {
                throw new BadJwtException("Synthetic test decoder");
            };
        }
    }

    @Test
    void missingTokenGets401() throws Exception {
        mockMvc.perform(get("/api/orders"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void rejectedTokenGets401() throws Exception {
        mockMvc.perform(get("/api/orders")
                .header(HttpHeaders.AUTHORIZATION, "Bearer invalid-token"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void readScopeCanRead() throws Exception {
        mockMvc.perform(get("/api/orders")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.read"))))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.orders").isArray());
    }

    @Test
    void writeScopeAloneCannotRead() throws Exception {
        mockMvc.perform(get("/api/orders")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.write"))))
            .andExpect(status().isForbidden());
    }

    @Test
    void readScopeAloneCannotCreate() throws Exception {
        mockMvc.perform(post("/api/orders")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.read"))))
            .andExpect(status().isForbidden());
    }

    @Test
    void writeScopeCanCreate() throws Exception {
        mockMvc.perform(post("/api/orders")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.write"))))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.status").value("created"));
    }
}
~~~

**TestDecoderConfig** giúp context có một JwtDecoder phục vụ test mà không cần Authorization Server thật. Decoder giả luôn từ chối chuỗi Bearer thực được gửi qua header; các request `with(jwt())` có Authentication tạo sẵn nên không đi qua xác minh token. Nếu ứng dụng đã định nghĩa một bean `JwtDecoder` khác, cần điều chỉnh cấu hình test để tránh trùng bean; mẫu này giả định decoder production được Boot auto-configure.

Không đem decoder giả này vào mã production. Bộ test trên chủ yếu chứng minh **quy tắc HTTP authorization**, còn xác minh chữ ký/claims cần test decoder riêng.

### 8.2. Vì sao @WithMockUser chưa đủ?

`@WithMockUser` tạo user giả trong Spring Security Test. Nó hữu ích để thử method security dựa trên user/role chung, nhưng **không mô tả đầy đủ Jwt principal, Bearer token, claims hoặc JwtDecoder**.

Với controller nhận `@AuthenticationPrincipal Jwt`, dùng `jwt()` sẽ sát cấu trúc Resource Server hơn. Nếu dùng custom `JwtAuthenticationConverter` cho roles/permissions, phải có **test riêng cho converter** thay vì chỉ tạo thủ công authority rồi kết luận mapping đúng.

## 9. Kiểm thử JwtDecoder bằng JWT có chữ ký thật

Để thử **chữ ký RS256, issuer, audience và thời hạn** một cách độc lập với mạng, tạo RSA key pair chỉ dùng trong test. Test ký JWT bằng **private key**, cho NimbusJwtDecoder xác minh bằng **public key** tương ứng, rồi đổi claims hoặc khóa để kiểm tra hành vi từ chối.

Ví dụ JUnit 5 sử dụng các lớp Nimbus JOSE/JWT đã có trong nhánh dependency JOSE:

~~~java
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.JWSHeader;
import com.nimbusds.jose.crypto.RSASSASigner;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.SignedJWT;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;
import java.time.Instant;
import java.util.Date;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtException;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class JwtDecoderValidationTest {

    private static final String ISSUER =
        "https://identity.example.test/realms/demo";

    private KeyPair trustedKeys;
    private NimbusJwtDecoder decoder;

    @BeforeEach
    void setUp() throws Exception {
        trustedKeys = newRsaKeys();
        decoder = NimbusJwtDecoder
            .withPublicKey((RSAPublicKey) trustedKeys.getPublic())
            .build();

        OAuth2TokenValidator<Jwt> audienceValidator = jwt ->
            jwt.getAudience().contains("orders-api")
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error("invalid_token", "Invalid audience", null));

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(ISSUER),
                audienceValidator));
    }

    private static KeyPair newRsaKeys() throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        return generator.generateKeyPair();
    }

    private static String signedToken(
            KeyPair signingKeys,
            String issuer,
            String audience,
            Instant expiration) throws Exception {

        JWTClaimsSet claims = new JWTClaimsSet.Builder()
            .issuer(issuer)
            .subject("employee-123")
            .audience(audience)
            .issueTime(Date.from(Instant.now().minusSeconds(60)))
            .notBeforeTime(Date.from(Instant.now().minusSeconds(60)))
            .expirationTime(Date.from(expiration))
            .claim("scope", "orders.read")
            .build();

        SignedJWT token = new SignedJWT(
            new JWSHeader(JWSAlgorithm.RS256), claims);
        token.sign(new RSASSASigner(
            (RSAPrivateKey) signingKeys.getPrivate()));
        return token.serialize();
    }

    @Test
    void validJwtPasses() throws Exception {
        String token = signedToken(
            trustedKeys, ISSUER, "orders-api",
            Instant.now().plusSeconds(600));

        Jwt jwt = decoder.decode(token);
        assertEquals("employee-123", jwt.getSubject());
    }

    @Test
    void wrongAudienceIsRejected() throws Exception {
        String token = signedToken(
            trustedKeys, ISSUER, "other-api",
            Instant.now().plusSeconds(600));

        assertThrows(JwtException.class, () -> decoder.decode(token));
    }

    @Test
    void wrongIssuerIsRejected() throws Exception {
        String token = signedToken(
            trustedKeys, "https://untrusted.example.test", "orders-api",
            Instant.now().plusSeconds(600));

        assertThrows(JwtException.class, () -> decoder.decode(token));
    }

    @Test
    void expiredJwtIsRejected() throws Exception {
        String token = signedToken(
            trustedKeys, ISSUER, "orders-api",
            Instant.now().minusSeconds(3600));

        assertThrows(JwtException.class, () -> decoder.decode(token));
    }

    @Test
    void unknownSigningKeyIsRejected() throws Exception {
        KeyPair otherKeys = newRsaKeys();
        String token = signedToken(
            otherKeys, ISSUER, "orders-api",
            Instant.now().plusSeconds(600));

        assertThrows(JwtException.class, () -> decoder.decode(token));
    }
}
~~~

Test này xác minh **đường chữ ký và JwtDecoder với public key test**, đồng thời kiểm tra issuer, audience và exp. Thời hạn trong bài test expired được đặt lùi một giờ để tránh sai lệch do một khoảng clock skew nhỏ. Không sử dụng private key hay Access Token production làm fixture.

**Giới hạn:** Decoder được tạo trực tiếp bằng public key nên test chưa kiểm tra metadata discovery, JWK Set HTTP, cache, luân chuyển khóa hoặc Bearer filter. Các phần đó cần integration test.

### 9.1. Thí nghiệm minh họa giới hạn của jwt() trong MockMvc

~~~java
mockMvc.perform(get("/api/orders")
        .with(jwt()
            .jwt(token -> token.audience("other-api"))
            .authorities(new SimpleGrantedAuthority("SCOPE_orders.read"))))
    .andExpect(status().isOk());
~~~

Request vẫn có thể trả **200** vì helper `jwt()` đã đặt Authentication hợp lệ trong SecurityContext. Không có chuỗi JWS thật được JwtDecoder kiểm tra. Muốn chứng minh token sai audience bị từ chối, **gọi JwtDecoder thực** như mục 9 hoặc gửi JWT đã ký qua header vào test HTTP sử dụng decoder thực.

## 10. Kiểm thử tích hợp với JWK Set cục bộ

Để thử toàn bộ đường đi HTTP với JWT thực, có thể dựng **JWK Set endpoint test cục bộ** chứa public key test, ký JWT bằng private key test, sau đó cấu hình Resource Server dùng issuer/JWK URI của fixture.

~~~text
JUnit/Test fixture
  |-- RSA private key test: ký JWT
  |-- JWK Set HTTP test endpoint: công bố RSA public key
  |
  v
MockMvc hoặc HTTP test
  Authorization: Bearer <JWT ký thật>
  |
  v
BearerTokenAuthenticationFilter
  |
  v
NimbusJwtDecoder -> JWK Set -> chữ ký/iss/aud/exp
  |
  v
Scope/authorization -> Controller hoặc 401/403
~~~

Nên thử các kịch bản:

1. Thiếu header hoặc header Bearer sai định dạng.
2. Chữ ký không đúng, khóa lạ hoặc `kid` không có trong JWK Set.
3. `exp` đã qua, `nbf` chưa đến, issuer hoặc audience sai.
4. Thuật toán/header không thuộc profile được phép; tuyệt đối không chấp nhận unsigned JWT.
5. Token đúng chữ ký nhưng thiếu scope/role hoặc không có quyền trên tài nguyên.
6. JWK endpoint gặp lỗi hoặc không sẵn sàng: ứng dụng không được cấp quyền chỉ vì chưa xác minh được token.
7. Luân chuyển khóa JWK Set nếu hệ thống có yêu cầu hỗ trợ rotation.
8. ID Token có audience của OIDC Client bị gửi nhầm đến API: Resource Server phải từ chối theo audience/profile.

Kiểm thử tích hợp này bổ sung cho test decoder độc lập; tránh phụ thuộc Authorization Server production, token thật và mạng bên ngoài.

## 11. Kiểm thử opaque token bằng spring-security-test

Với Resource Server cấu hình opaque token, dùng `opaqueToken()` để mô phỏng Authentication khi thử authorization:

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.opaqueToken;

mockMvc.perform(get("/api/orders")
        .with(opaqueToken().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read"))))
    .andExpect(status().isOk());
~~~

Giống `jwt()`, helper này **không chứng minh** token thực đã đi qua introspection endpoint. Nếu cần kiểm tra xác thực opaque token, thử `OpaqueTokenIntrospector` với dữ liệu phản hồi mock hoặc introspection HTTP test server, bao gồm:

- Token **active=true** và có quyền phù hợp.
- Token **active=false**, không tồn tại hoặc bị thu hồi.
- Introspection client credentials sai.
- Timeout/lỗi mạng và hành vi từ chối phù hợp.
- Claim/scope trả về có đúng contract với API hay không.

Không thử chữ ký RS256 của một opaque token vốn không được Resource Server giải mã bằng JWT decoder.

## 12. Kiểm thử quyền trên tài nguyên và method security

Đi qua JWT authentication **chưa chứng minh** người gọi được đọc một bản ghi cụ thể. Ví dụ token có `orders.read` cho tenant A có thể phải bị chặn khi gọi API tenant B.

Nếu API có `@PreAuthorize`, thêm cấu hình method security:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
~~~

Ví dụ nghiệp vụ cần đối chiếu `tenant_id` từ JWT với tenant của đơn hàng và quyền sở hữu tài nguyên, không chỉ đọc claim để hiển thị. Khi có converter custom cho `roles`/ `permissions`, viết test riêng để chứng minh tên claim, kiểu JSON và quy tắc mapping thành authorities là đúng. Một test `jwt().authorities(...)` không bao phủ converter custom đó.

Các trường hợp có ích: truy cập ngang tenant, truy cập đơn hàng của user khác, thao tác POST chỉ có scope GET, thay đổi thông tin định danh trong URL và các tài nguyên đã bị thu hồi quyền.

## 13. Các lỗi triển khai thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Chỉ thêm OAuth 2.0 Client starter | API chưa có Bearer token authentication. | Thêm Resource Server starter và cấu hình phù hợp. |
| Thêm Resource Server module thủ công nhưng thiếu JOSE | Không đủ lớp xử lý JWT/JWS. | Bổ sung `spring-security-oauth2-jose` cùng dependency management tương thích. |
| Chỉ xác minh chữ ký, bỏ qua audience | Token của API khác có thể bị nhận nhầm. | Kiểm tra `aud` bằng thuộc tính hoặc custom validator, và test thực tế. |
| Tự khai báo JwtDecoder làm mất validator mặc định | Có thể bỏ qua issuer/thời hạn nếu cấu hình sai. | Kết hợp validator mặc định và tùy chỉnh, viết negative tests. |
| Chỉ test bằng `jwt()` rồi tuyên bố “JWT signature an toàn” | Test không đi qua decoder. | Thêm test JWT ký thật với decoder hoặc integration HTTP. |
| Chỉ test success case | Bỏ sót 401/403, hết hạn, token sai audience. | Có cả positive và negative tests ở mỗi tầng cần thiết. |
| `@WithMockUser` thay mọi JWT test | Không chứng minh principal Bearer JWT/claims. | Dùng `jwt()`, test converter và decoder đúng mục đích. |
| Tắt CSRF toàn ứng dụng dù dùng session cookie | Web có thể mất bảo vệ CSRF cần thiết. | Áp dụng chính sách CSRF theo từng authentication flow. |
| Test phụ thuộc IdP thật | Chậm, dễ không ổn định, có thể dùng secret thật. | Dùng RSA/JWK/introspection fixture cục bộ. |
| Ghi token vào URL, log hoặc lỗi | Bearer credential bị rò rỉ. | Dùng Authorization header qua TLS, lọc log và tránh phản chiếu token. |

### 13.1. Phân biệt lỗi 401 và 403

Với Resource Server thông thường:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
~~~

Thường xuất hiện nếu không có Bearer token hoặc token không thể xác thực.

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
~~~

Thường xuất hiện khi token đã được xác thực nhưng thiếu quyền. Chi tiết header có thể phụ thuộc cấu hình và tình huống; khi tùy chỉnh `AuthenticationEntryPoint` hoặc `AccessDeniedHandler`, giữ mã HTTP và challenge phù hợp mà không trả token, exception thô hoặc stack trace cho client.

### 13.2. Không nhận diện JWT chỉ bằng ba đoạn văn bản

Một chuỗi có dấu chấm chưa chứng minh là JWT đáng tin. Resource Server phải sử dụng decoder và validator chính thức, giới hạn thuật toán/khóa được phép và chỉ tin issuer/audience đã cấu hình. Việc dùng Base64url decoder tự viết để đọc claims **không phải bước xác thực**.

## 14. Quy trình triển khai từ khởi tạo đến kiểm thử

1. **Thống nhất hợp đồng với Authorization Server:** JWT hay opaque, issuer, JWK Set/introspection URI, audience, scope, thuật toán, thời hạn và token profile.
2. **Chọn dependency đúng:** Resource Server starter; JOSE cho JWT; Spring Security Test cho kiểm thử. Không trộn version tùy ý.
3. **Thiết lập token validation:** issuer, chữ ký, thời hạn, audience và các yêu cầu của profile; không cấp quyền khi không xác minh được.
4. **Thiết lập HTTP authorization:** method, route, scope và quyền trên dữ liệu; xác định nơi nào cần session/CSRF.
5. **Viết MockMvc tests:** anonymous 401, token sai 401, thiếu scope 403, có scope 200/201; kiểm tra quyền đọc và ghi riêng.
6. **Viết JwtDecoder tests:** token thật được ký bằng khóa test; thử đúng/sai issuer, audience, expiration và signing key.
7. **Viết integration test khi cần:** JWK Set endpoint hoặc introspection cục bộ, kiểm tra Bearer filter và hành vi HTTP hoàn chỉnh.
8. **Bảo vệ vận hành:** HTTPS, không log token, không lộ khóa/claims nhạy cảm qua thông báo lỗi, chuẩn bị cho luân chuyển khóa và lỗi IdP.

**Điều cần ghi nhớ:** `spring-boot-starter-oauth2-resource-server` mở đường xử lý Bearer token; **JOSE** giúp xác minh JWT đã ký; **security tests** phải chứng minh cả việc endpoint áp quyền đúng và decoder không nhận token không đáng tin. Một test dùng `jwt()` là công cụ rất tốt cho authorization, nhưng phải bổ sung xác minh chữ ký và claims nếu muốn kết luận về độ an toàn của JWT Resource Server.

## Tài liệu tham khảo

- [Spring Security — OAuth 2.0 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html).
- [Spring Security — JWT Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html).
- [Spring Security — Opaque Token Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html).
- [Spring Security — Testing OAuth 2.0 with MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html).
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515).
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517).
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519).
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725).
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068).
