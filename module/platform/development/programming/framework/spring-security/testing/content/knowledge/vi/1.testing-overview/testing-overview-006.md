# Giả lập token khác với kiểm tra chữ ký hoặc introspection thật

## Mục tiêu học tập

Khi kiểm thử API bảo vệ bằng bearer token, một bài test có thể tạo sẵn người dùng JWT giả lập rồi nhận `200 OK`. Kết quả đó chứng minh ứng dụng cấp quyền đúng cho **danh tính đã được dựng trong test**; nó chưa chứng minh token gửi qua HTTP có chữ ký hợp lệ, chưa hết hạn, đúng issuer hay được authorization server chấp nhận.

Sau bài học này, bạn có thể:

- Phân biệt **giả lập JWT/opaque token** với việc gửi bearer token qua quy trình xác thực thực tế.
- Hiểu điều mà `jwt()`, `mockJwt()`, `opaqueToken()` và `mockOpaqueToken()` thiết lập trong bài test.
- Viết kiểm thử Servlet với `MockMvc` và Reactive với `WebTestClient` cho cả token giả lập lẫn token thực.
- Kiểm tra chữ ký JWT, thời hạn, issuer, audience và ánh xạ claim thành authority.
- Kiểm thử OAuth2 Token Introspection bằng endpoint giả lập, phân biệt phản hồi `active=true` và `active=false`.
- Biết giới hạn của kiểm thử OAuth2/OIDC login mock và chọn phạm vi tích hợp cần thiết.

Bài này thuộc module **SPRING_SECURITY_TESTING**, tập trung vào kiểm chứng xác thực, phân quyền và bảo vệ HTTP bằng `spring-security-test` trên ứng dụng Servlet và Reactive.

## 1. Hai câu hỏi khác nhau khi API nhận bearer token

Giả sử API `GET /api/orders` chỉ chấp nhận access token có quyền `orders.read`. Có hai câu hỏi cần kiểm tra:

1. **Token có được chấp nhận là bằng chứng danh tính hợp lệ không?** Với JWT, server phải kiểm tra chữ ký và các claim xác thực như thời hạn, issuer, audience theo chính sách. Với opaque token, server thường hỏi authorization server qua introspection endpoint để biết token còn hoạt động hay không.
2. **Danh tính sau xác thực có được phép gọi API không?** Server kiểm tra authorities, scope, role và các điều kiện phân quyền khác.

Một bài test chỉ quan tâm câu hỏi thứ hai có thể bỏ qua câu hỏi thứ nhất bằng cách tạo sẵn một đối tượng authentication. Đây là cách làm hữu ích để viết test phân quyền nhanh, nhưng phải gọi đúng tên: **token giả lập** hoặc **authentication giả lập**.

### 1.1. JWT và opaque token khác nhau ở bước xác minh

| Đặc điểm | JWT | Opaque access token |
| --- | --- | --- |
| Hình dạng | Thường là chuỗi có các phần header, payload và signature được mã hóa dạng Base64URL. | Chuỗi token không có cấu trúc claim mà resource server có thể tự đọc và tin cậy. |
| Cách resource server xác minh | Giải mã, xác minh chữ ký bằng khóa tin cậy và kiểm tra claim/validator. | Gửi token đến introspection endpoint của authorization server. |
| Thành phần Spring Security | `JwtDecoder` và `JwtAuthenticationConverter`. | `OpaqueTokenIntrospector`. |
| Kiểm tra token không hợp lệ | Chữ ký sai, hết hạn, issuer/audience không hợp lệ hoặc claim không đáp ứng chính sách. | Introspection trả `active: false`, endpoint lỗi hoặc phản hồi không hợp lệ. |
| Dữ liệu quyền | Thường lấy từ claim như `scope`, `scp`, `roles` rồi ánh xạ thành authority. | Lấy từ dữ liệu introspection như `scope`, `username`, `sub`. |
| Bài test mock phổ biến | `jwt()` / `mockJwt()`. | `opaqueToken()` / `mockOpaqueToken()`. |

### 1.2. Luồng xử lý thực tế và luồng mock

~~~mermaid
flowchart TD
    A["Authorization: Bearer ..."] --> B["BearerTokenAuthenticationFilter / WebFilter"]
    B --> C{"Loại token"}
    C -->|JWT| D["JwtDecoder: chữ ký + validators"]
    C -->|Opaque| E["OpaqueTokenIntrospector: HTTP introspection"]
    D --> F{"Token hợp lệ?"}
    E --> F
    F -->|Không| X["401 Unauthorized"]
    F -->|Có| G["Authentication + authorities"]
    G --> H["Authorization: scope / role / policy"]
    H -->|Được phép| I["Controller / Handler"]
    H -->|Bị từ chối| Y["403 Forbidden"]
    M["jwt() / mockJwt() / opaqueToken()"] -. "Dựng authentication trong test" .-> G
~~~

Đường nét đứt biểu thị cơ chế mock: bài test thiết lập authentication ở phía ứng dụng để kiểm tra các bước sau đó. Nó không thực hiện bước xác minh token ở đầu luồng.

## 2. Mock JWT trong Servlet: jwt() kiểm tra điều gì?

Thư viện `spring-security-test` cung cấp request post-processor `jwt()` cho `MockMvc`. Tiện ích này tạo một JWT và authentication giả lập gắn với request để test có thể kiểm tra URL authorization hoặc logic phía sau.

Ví dụ giả định ứng dụng có endpoint yêu cầu `SCOPE_orders.read`:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class JwtMockMvcTest {

    @Autowired
    MockMvc mvc;

    @Test
    void jwtWithRequiredScopeCanReadOrders() throws Exception {
        mvc.perform(get("/api/orders")
                .with(jwt().jwt(jwt -> jwt
                    .claim("sub", "linh")
                    .claim("scope", "orders.read"))))
            .andExpect(status().isOk());
    }

    @Test
    void jwtWithoutRequiredScopeIsDenied() throws Exception {
        mvc.perform(get("/api/orders")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_profile.read"))))
            .andExpect(status().isForbidden());
    }
}
~~~

Ví dụ giả định security configuration có quy tắc `hasAuthority("SCOPE_orders.read")` cho endpoint và controller trả `200` khi được phép.

Có hai cách setup thường gặp:

- `jwt().jwt(...)` chỉnh sửa các claim của JWT giả lập. Khi dùng cấu hình authority converter mặc định, claim scope có thể được ánh xạ thành authority có tiền tố `SCOPE_`.
- `jwt().authorities(...)` truyền thẳng authorities cho authentication mock. Cách này hữu ích khi chỉ muốn cô lập quy tắc phân quyền, nhưng bỏ qua bước ánh xạ claim sang authority.

**Điều jwt() chứng minh:** với principal/claims/authorities đã dựng, Spring Security áp dụng chính sách truy cập của request như mong đợi.

**Điều jwt() không chứng minh:**

- Bearer token được đọc và phân tích đúng từ header HTTP.
- Chữ ký JWT được xác minh bằng public key đáng tin cậy.
- Token hết hạn, sai issuer hoặc sai audience bị từ chối.
- JWK Set được tải/cập nhật đúng hoặc việc xoay khóa hoạt động.
- Bộ chuyển đổi claim tùy biến của ứng dụng được thực thi, nếu test đã truyền authorities trực tiếp.
- Authorization server đã thực sự phát hành token đó.

### 2.1. Vì sao mock JWT có thể làm test xanh dù decoder bị cấu hình sai?

Trong test trên, `jwt()` tạo authentication giả lập. Nếu bạn cấu hình sai URL JWKS, đặt public key không đúng hoặc decoder không kiểm tra issuer, test phân quyền vẫn có thể xanh vì nó không cần decoder để xác minh bearer token.

Vì vậy, nên đặt tên test đúng phạm vi:

- `jwtWithRequiredScopeCanReadOrders`: test phân quyền với JWT mock.
- `signedBearerTokenIsAcceptedByResourceServer`: test đường xác minh JWT thực.
- `tokenSignedByUnknownKeyIsRejected`: test xác minh chữ ký.

Tên test giúp reviewer hiểu bằng chứng nào đang được tạo ra.

## 3. Mock JWT trong Reactive: mockJwt() cũng bỏ qua decoder

Với WebFlux, `SecurityMockServerConfigurers.mockJwt()` dùng cùng ý tưởng: thiết lập JWT authentication giả lập cho `WebTestClient` gắn vào mock server/application context.

Ví dụ ứng dụng WebFlux có endpoint `GET /api/orders` và yêu cầu scope `orders.read`:

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.*;

@SpringBootTest
class ReactiveJwtMockTest {

    @Autowired
    ApplicationContext context;

    WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @Test
    void jwtWithScopeCanReadOrders() {
        client.mutateWith(mockJwt()
                .jwt(jwt -> jwt.claim("scope", "orders.read")))
            .get().uri("/api/orders")
            .exchange()
            .expectStatus().isOk();
    }

    @Test
    void jwtWithoutScopeIsDenied() {
        client.mutateWith(mockJwt()
                .authorities(new SimpleGrantedAuthority("SCOPE_profile.read")))
            .get().uri("/api/orders")
            .exchange()
            .expectStatus().isForbidden();
    }
}
~~~

Đây là ví dụ cho một ứng dụng **WebFlux riêng** đã có `SecurityWebFilterChain`. Nó kiểm tra phân quyền Reactive với JWT mock. Nếu muốn kiểm tra chữ ký, thời hạn hoặc issuer của bearer token, phải gửi token qua header `Authorization` để resource server gọi `ReactiveJwtDecoder` thực tế.

Không dùng `mockJwt()` để kết luận rằng ứng dụng xác minh JWT thật thành công. Khi `WebTestClient` gọi server ở cổng thật, mock principal trong process test cũng không tự truyền qua mạng; hãy gửi token thật cho server.

## 4. Kiểm tra JWT thật: chữ ký, thời hạn, issuer và audience

Một test xác minh JWT thực cần đi qua các thành phần sau:

1. Gửi header `Authorization: Bearer <token>`.
2. Bearer token filter lấy token từ request.
3. `JwtDecoder` xác minh chữ ký bằng khóa tin cậy.
4. Validators kiểm tra các claim xác thực như `exp`, `nbf`, `iss` và `aud` theo cấu hình.
5. JWT hợp lệ được chuyển thành `JwtAuthenticationToken`, rồi authorization kiểm tra quyền.

### 4.1. Cấu hình resource server dùng JWT

Ví dụ cấu hình Servlet:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.core.*;
import org.springframework.security.oauth2.jwt.*;
import org.springframework.security.web.SecurityFilterChain;

import java.security.interfaces.RSAPublicKey;

@Configuration
class JwtResourceServerConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }

    @Bean
    JwtDecoder jwtDecoder(RSAPublicKey trustedPublicKey) {
        NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withPublicKey(trustedPublicKey).build();

        OAuth2TokenValidator<Jwt> audienceValidator = jwt ->
            jwt.getAudience().contains("orders-api")
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error("invalid_token",
                        "Required audience is missing", null));

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                new JwtTimestampValidator(),
                new JwtIssuerValidator("https://issuer.test"),
                audienceValidator
            )
        );

        return decoder;
    }
}
~~~

Ví dụ trên dùng public key RSA được cấp cho test context. Trong môi trường thực, public key có thể được lấy từ JWKS endpoint thông qua cấu hình issuer hoặc JWK Set URI. Validator được khai báo rõ để test không vô tình bỏ qua issuer và audience.

`JwtTimestampValidator` kiểm tra các mốc thời gian như `exp` và `nbf` theo quy tắc của nó. `JwtIssuerValidator` kiểm tra issuer. Validator tùy biến kiểm tra audience `orders-api`. Chữ ký được decoder kiểm tra trước khi token được dùng làm authentication.

### 4.2. Tạo token kiểm thử có chữ ký

Đối với test tích hợp, hãy tạo cặp khóa RSA riêng cho môi trường test. Giữ private key trong fixture kiểm thử và cấu hình ứng dụng chỉ tin public key tương ứng. Không dùng khóa production hoặc secret thật trong test.

Có thể tạo token ký bằng `JwtEncoder`. Ví dụ helper minh họa:

~~~java
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.*;

import java.time.Instant;
import java.util.List;

String createToken(
        JwtEncoder encoder,
        Instant issuedAt,
        Instant expiresAt,
        String issuer,
        List<String> audience) {

    JwtClaimsSet claims = JwtClaimsSet.builder()
        .issuer(issuer)
        .subject("linh")
        .issuedAt(issuedAt)
        .expiresAt(expiresAt)
        .audience(audience)
        .claim("scope", "orders.read")
        .build();

    JwsHeader header = JwsHeader.with(SignatureAlgorithm.RS256).build();

    return encoder.encode(
        JwtEncoderParameters.from(header, claims)
    ).getTokenValue();
}
~~~

`JwtEncoder` trong fixture được tạo từ private key test; `JwtDecoder` của ứng dụng chỉ tin public key tương ứng. Để tạo token sai chữ ký, dùng **một cặp khóa khác** để ký nhưng vẫn gửi token đến decoder đang tin public key ban đầu. Token vẫn có cấu trúc hợp lệ nhưng chữ ký không xác minh được.

### 4.3. Gửi token qua header để đi qua decoder

~~~java
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class JwtValidationIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    JwtTestTokens tokens;

    @Test
    void validSignedBearerTokenIsAccepted() throws Exception {
        String token = tokens.validToken();

        mvc.perform(get("/api/orders")
                .header("Authorization", "Bearer " + token))
            .andExpect(status().isOk());
    }

    @Test
    void tokenSignedByUnknownKeyIsRejected() throws Exception {
        String token = tokens.signedByDifferentKey();

        mvc.perform(get("/api/orders")
                .header("Authorization", "Bearer " + token))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void expiredTokenIsRejected() throws Exception {
        String token = tokens.expiredToken();

        mvc.perform(get("/api/orders")
                .header("Authorization", "Bearer " + token))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void tokenWithWrongIssuerIsRejected() throws Exception {
        String token = tokens.tokenFromOtherIssuer();

        mvc.perform(get("/api/orders")
                .header("Authorization", "Bearer " + token))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void tokenWithWrongAudienceIsRejected() throws Exception {
        String token = tokens.tokenForOtherAudience();

        mvc.perform(get("/api/orders")
                .header("Authorization", "Bearer " + token))
            .andExpect(status().isUnauthorized());
    }
}
~~~

`JwtTestTokens` là fixture tự xây dựng từ `JwtEncoder` và các cặp khóa test; các phương thức phải tạo đúng biến thể tương ứng:

- `validToken()`: ký bằng private key được tin, thời hạn còn hiệu lực, issuer và audience đúng.
- `signedByDifferentKey()`: ký bằng private key khác.
- `expiredToken()`: ký bằng khóa được tin nhưng đặt `exp` trong quá khứ.
- `tokenFromOtherIssuer()`: chữ ký hợp lệ, issuer sai.
- `tokenForOtherAudience()`: chữ ký hợp lệ, audience không chứa `orders-api`.

Như vậy, các test lỗi issuer/audience không bị nhầm thành lỗi chữ ký. Chúng chứng minh từng validator được áp dụng riêng. Nếu ứng dụng cố ý trả mã khác qua authentication entry point tùy biến, hãy điều chỉnh expected status theo hợp đồng thực tế; với cấu hình bearer resource server mặc định, token không hợp lệ thường dẫn đến `401 Unauthorized`.

### 4.4. Kiểm tra converter ánh xạ scope thành authority

Chữ ký đúng chưa đủ để request được phép. Token còn cần có claim quyền đúng và converter phải ánh xạ nó theo chính sách.

Ví dụ test JWT mock với `.authorities(...)` truyền thẳng authority sẽ **bỏ qua converter**. Nếu mục tiêu là kiểm tra converter tùy biến, hãy unit test converter riêng; sau đó thêm test tích hợp dùng token đã ký và gửi qua bearer filter để kiểm tra kết quả mapping trong toàn luồng.

| Test | Cách setup | Điều được chứng minh |
| --- | --- | --- |
| Converter unit test | Tạo `Jwt` trong bộ nhớ và gọi converter. | Claim được ánh xạ thành authority đúng. |
| Authorization mock test | `jwt().authorities(...)`. | Chính sách truy cập xử lý authority giả lập đúng. |
| Signed JWT integration test | Bearer header + decoder + converter thật. | Chữ ký/validators, mapping và phân quyền kết hợp đúng. |

## 5. Opaque token: mock principal khác với introspection endpoint

Với opaque token, resource server không tự xác minh chữ ký hoặc đọc claim bên trong. Nó gửi token đến **OAuth2 Token Introspection Endpoint** để hỏi authorization server. Phản hồi thường có trường `active` và có thể chứa `sub`, `scope`, `client_id`, `exp`, `aud` cùng thông tin khác.

### 5.1. Mock opaque token trong MockMvc

`opaqueToken()` của Spring Security Test tạo sẵn authentication cho request Servlet. Ví dụ:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.opaqueToken;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OpaqueTokenMockMvcTest {

    @Autowired
    MockMvc mvc;

    @Test
    void activeOpaquePrincipalWithScopeCanReadOrders()
            throws Exception {
        mvc.perform(get("/api/orders")
                .with(opaqueToken()
                    .attributes(attrs -> attrs.put("sub", "linh"))
                    .authorities(new SimpleGrantedAuthority(
                        "SCOPE_orders.read"))))
            .andExpect(status().isOk());
    }

    @Test
    void opaquePrincipalWithoutScopeIsDenied()
            throws Exception {
        mvc.perform(get("/api/orders")
                .with(opaqueToken()
                    .authorities(new SimpleGrantedAuthority(
                        "SCOPE_profile.read"))))
            .andExpect(status().isForbidden());
    }
}
~~~

Đây là kiểm thử **phân quyền sau introspection** với authentication giả lập. Nó không gửi request đến introspection endpoint, không kiểm tra client authentication và không xác minh authorization server trả `active: true`.

### 5.2. Mock opaque token trong WebFlux

Trong ứng dụng Reactive, dùng `mockOpaqueToken()` với `WebTestClient` gắn application context:

~~~java
client.mutateWith(mockOpaqueToken()
        .attributes(attrs -> attrs.put("sub", "linh"))
        .authorities(new SimpleGrantedAuthority("SCOPE_orders.read")))
    .get().uri("/api/orders")
    .exchange()
    .expectStatus().isOk();
~~~

Ví dụ này giả định biến `client` đã được tạo với `bindToApplicationContext(...)` và `springSecurity()`. Nó có cùng giới hạn với `opaqueToken()` của Servlet: dựng principal và quyền trong test, không gọi introspection server.

### 5.3. Kiểm thử introspection thật qua một endpoint HTTP giả lập

Để kiểm tra resource server thực sự gửi token đến introspection endpoint, hãy chạy ứng dụng với `OpaqueTokenIntrospector` thật và trỏ endpoint tới một HTTP mock server cục bộ trong test. Ví dụ cấu hình Spring Boot:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: http://localhost:9099/introspect
          client-id: test-resource-server
          client-secret: test-secret
~~~

Security filter chain cần bật opaque token resource server:

~~~java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyRequest().authenticated())
        .oauth2ResourceServer(oauth2 ->
            oauth2.opaqueToken(Customizer.withDefaults()))
        .build();
}
~~~

Mock server có thể trả một phản hồi introspection theo chuẩn, ví dụ:

~~~json
{
  "active": true,
  "sub": "linh",
  "username": "linh",
  "scope": "orders.read profile.read",
  "client_id": "mobile-app",
  "token_type": "Bearer"
}
~~~

Test gửi bearer token bình thường:

~~~java
@Test
void activeOpaqueTokenIsIntrospectedAndAccepted() throws Exception {
    mvc.perform(get("/api/orders")
            .header("Authorization", "Bearer opaque-token-123"))
        .andExpect(status().isOk());

    // Đồng thời verify mock server nhận POST /introspect,
    // có token cần introspect và client authentication đúng.
}
~~~

Đối với token không hoạt động, mock endpoint trả:

~~~json
{
  "active": false
}
~~~

và test kỳ vọng:

~~~java
@Test
void inactiveOpaqueTokenIsRejected() throws Exception {
    mvc.perform(get("/api/orders")
            .header("Authorization", "Bearer revoked-token"))
        .andExpect(status().isUnauthorized());
}
~~~

Có thể dùng WireMock, MockWebServer hoặc HTTP stub server tương đương để:

- Xác nhận resource server gửi đúng HTTP method/path tới introspection endpoint.
- Xác nhận token được truyền trong request body theo định dạng introspection.
- Xác nhận client authentication được gửi theo cấu hình.
- Trả phản hồi `active: true` và xác minh scope được ánh xạ thành authority.
- Trả `active: false` hoặc lỗi endpoint để kiểm tra ứng dụng từ chối token theo cách phù hợp.

Đây là kiểm thử **tích hợp với introspection endpoint giả lập**. Nó chạy HTTP client và `OpaqueTokenIntrospector` của ứng dụng, nhưng không chứng minh authorization server bên ngoài thực sự quản lý trạng thái thu hồi token đúng. Để kiểm chứng nhà cung cấp danh tính thật, cần một bài contract/integration riêng với môi trường test của nhà cung cấp đó.

## 6. OAuth2 Login và OIDC Login mock cũng không xác minh token thật

Các tiện ích `oauth2Login()` và `oidcLogin()` của Spring Security Test giúp thiết lập principal đã đăng nhập để kiểm tra logic phía ứng dụng. Chúng phù hợp khi controller/service dùng các thuộc tính như tên, email, subject hoặc authorities sau khi đăng nhập.

Chúng không tự thực hiện toàn bộ OAuth2 Authorization Code Flow hoặc OIDC:

- Không chuyển trình duyệt sang authorization endpoint của nhà cung cấp.
- Không kiểm tra callback, `state` và `nonce` theo một phiên giao dịch thực.
- Không xác minh chữ ký ID token từ JWKS thật.
- Không trao đổi authorization code lấy token ở token endpoint thật.
- Không chứng minh UserInfo endpoint hoặc session/cookie của ứng dụng vận hành đúng.

Nếu muốn kiểm tra ứng dụng hiển thị hồ sơ theo principal OIDC, `oidcLogin()` là đủ cho bài test logic sau đăng nhập. Nếu muốn kiểm tra ID token được ký bởi issuer, `nonce`, redirect URI hoặc code exchange, hãy dựng một IdP test/stub phù hợp hoặc dùng môi trường integration của nhà cung cấp.

Cần đặt tên test thể hiện phạm vi:

| Tên test gợi ý | Phạm vi |
| --- | --- |
| `oidcPrincipalCanReadOwnProfile` | Logic ứng dụng với principal OIDC mock. |
| `idTokenSignedByTrustedIssuerIsAccepted` | Xác minh ID token theo cấu hình issuer/decoder của ứng dụng. |
| `authorizationCodeCallbackValidatesStateAndNonce` | Luồng callback/transaction của OAuth2/OIDC. |

## 7. Chọn đúng cách test theo câu hỏi cần trả lời

| Câu hỏi | Cách test phù hợp | Tránh kết luận quá mức |
| --- | --- | --- |
| Người có scope này có gọi được API không? | `jwt()` / `mockJwt()` với scope hoặc authority phù hợp. | Không kết luận chữ ký token được xác minh. |
| Người không có scope có bị từ chối không? | Cặp mock JWT có/không authority, kiểm tra `403`. | Đảm bảo test không bị chặn vì CSRF hoặc điều kiện khác. |
| Claim scope có được ánh xạ đúng không? | Unit test `JwtAuthenticationConverter`/authority converter. | Không kết luận filter chain dùng đúng converter nếu chưa tích hợp. |
| JWT chữ ký sai có bị từ chối không? | Bearer header thật qua `JwtDecoder` với key tin cậy. | Không dùng `jwt()` cho câu hỏi này. |
| JWT hết hạn/issuer/audience sai có bị từ chối không? | Ký token test có claim sai, gửi qua decoder và validators. | Phải bảo đảm chữ ký vẫn hợp lệ để cô lập validator cần thử. |
| Opaque token active/inactive xử lý đúng không? | `opaqueToken()` cho phân quyền; HTTP introspection stub cho tích hợp. | Mock principal không gọi introspection endpoint. |
| Resource server gửi client authentication đúng không? | Introspection stub kiểm tra HTTP request thực tế. | Không kết luận IdP bên ngoài vận hành đúng. |
| OAuth2/OIDC principal được dùng đúng không? | `oauth2Login()` / `oidcLogin()`. | Không kết luận code flow, state, nonce hoặc chữ ký ID token đã được xác minh. |
| Token thật từ IdP test có được chấp nhận không? | Integration test với issuer/JWKS/introspection test thực. | Không dùng credential hoặc dữ liệu production trong test. |

## 8. Các lỗi thường gặp khi trộn mock và xác thực thật

### 8.1. Gửi Authorization: Bearer ... nhưng test vẫn dùng jwt()

Nếu request vừa có bearer header vừa gắn `jwt()`, bài test có thể đang sử dụng authentication được thiết lập bởi test post-processor. Không nên ghép hai cách nếu mục tiêu là xác minh decoder. Để test token thật, chỉ gửi bearer header và để resource server tự xác thực.

### 8.2. Truyền authorities trực tiếp rồi kết luận claim converter đúng

`jwt().authorities(...)` và `opaqueToken().authorities(...)` cho phép chỉ định quyền trực tiếp. Chúng bỏ qua việc ánh xạ claim/scope. Test converter riêng, sau đó test tích hợp với token thật để xác nhận converter được nối vào resource server.

### 8.3. Dùng JWT có chữ ký nhưng decoder không kiểm tra issuer/audience

Chữ ký hợp lệ chỉ chứng minh token được ký bằng khóa tương ứng. Ứng dụng vẫn có thể cần giới hạn issuer, audience, thời hạn, thuật toán và các claim khác. Hãy cấu hình validators và viết token test có chữ ký hợp lệ nhưng từng claim sai.

### 8.4. Dùng token ký bằng khóa khác nhưng vô tình kiểm tra sai nguyên nhân

Khi muốn test issuer, hãy ký token bằng khóa được tin và chỉ thay issuer. Khi muốn test audience, chỉ thay audience. Khi muốn test chữ ký, giữ claim hợp lệ và đổi khóa ký. Mỗi test nên thay đổi một điều kiện chính để lỗi có nguyên nhân rõ.

### 8.5. Mock introspector rồi kết luận HTTP introspection hoạt động

Một bean `OpaqueTokenIntrospector` mock trả `OAuth2AuthenticatedPrincipal` không phát sinh request HTTP. Cách này phù hợp cho unit hoặc test phân quyền; nó không kiểm tra endpoint, body, client authentication, timeout hoặc phản hồi introspection. Muốn kiểm tra HTTP client, dùng introspector thật trỏ tới stub server.

### 8.6. Cho rằng introspection stub kiểm chứng authorization server thật

Stub server chỉ phản hồi theo kịch bản test. Nó kiểm tra client của resource server và cách ứng dụng xử lý response. Quy tắc thu hồi token, lưu trạng thái active, quyền client hoặc sự sẵn sàng của IdP thật cần kiểm tra riêng.

### 8.7. Kỳ vọng 403 cho token không hợp lệ

Token không hợp lệ thường bị từ chối ở bước xác thực và trả `401 Unauthorized`. `403 Forbidden` thường dành cho một authentication hợp lệ nhưng thiếu quyền. Đừng nhầm hai kết quả này khi viết assertion.

### 8.8. Quên rằng WebFlux dùng decoder/introspector Reactive

Trong WebFlux, cần cấu hình và kiểm tra `ReactiveJwtDecoder` hoặc `ReactiveOpaqueTokenIntrospector` theo stack Reactive. Test với `mockJwt()` chỉ xác nhận downstream authorization; nó không kiểm tra reactive decoder hay reactive introspection HTTP client.

## 9. Bài thực hành tổng hợp

Tạo một resource server test có endpoint `GET /api/orders` yêu cầu `SCOPE_orders.read`. Hoàn thành các bước sau:

1. **Mock JWT:** dùng `MockMvc` và `jwt()` để kiểm tra scope được phép và scope bị từ chối. Ghi rõ test này không gọi decoder.
2. **Converter:** unit test claim `scope` thành authority. Thử claim thiếu, nhiều scope, chuỗi rỗng và claim sai định dạng theo hợp đồng ứng dụng.
3. **JWT thật:** tạo cặp khóa RSA test, cấu hình decoder với public key và gửi bearer token đã ký qua header. Kiểm tra token hợp lệ được chấp nhận.
4. **Chữ ký:** ký token bằng một private key khác, giữ nguyên issuer/audience/thời hạn hợp lệ, rồi xác minh server từ chối.
5. **Validators:** tạo token có chữ ký đúng nhưng hết hạn, issuer sai hoặc audience sai. Mỗi test chỉ thay một claim.
6. **Mock opaque token:** dùng `opaqueToken()` để thử quyền mà không gọi introspection.
7. **Introspection stub:** chạy HTTP stub trả `active: true` có scope và `active: false`; gửi bearer token qua ứng dụng và xác minh request introspection được phát đi.
8. **Reactive:** lặp lại một ca JWT mock và một ca JWT thật bằng `WebTestClient` trong ứng dụng WebFlux riêng. Nếu cần opaque token, dùng reactive introspector và stub tương ứng.

**Tiêu chí hoàn thành:** bạn có thể chỉ ra rõ test nào chỉ dựng authentication, test nào gọi decoder, test nào gửi request introspection, và test nào kiểm tra chính sách quyền sau xác thực.

## 10. Ghi nhớ

`jwt()`, `mockJwt()`, `opaqueToken()` và `mockOpaqueToken()` là những công cụ hiệu quả để tạo danh tính giả lập, kiểm tra authorities và xác minh quyết định phân quyền. Chúng giúp bài test nhanh, ổn định và tập trung vào logic sau xác thực.

Kiểm tra chữ ký JWT cần bearer token đi qua `JwtDecoder` và validators thực tế. Kiểm tra opaque token cần bearer token đi qua `OpaqueTokenIntrospector` và có thể dùng HTTP stub để xác minh request/response introspection. OAuth2/OIDC login mock kiểm tra logic với principal đã đăng nhập; nó không thay thế bài test protocol hoặc xác minh token từ issuer.

Một báo cáo kiểm thử chính xác phải nói rõ **token đã được giả lập hay được xác minh, thành phần nào thực thi việc xác minh và bằng chứng đó bao phủ đến đâu**.
