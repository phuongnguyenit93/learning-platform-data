# Kiểm thử decoder, introspector hoặc nhà cung cấp danh tính ngoài các giả lập trong Spring Security Servlet

## 1. Vì sao kiểm thử HTTP chỉ bằng mock authentication là chưa đủ?

Trong **Spring Security Servlet Resource Server**, ứng dụng thường nhận `Authorization: Bearer <access-token>`, xác thực access token rồi dùng `Authentication` và authorities để quyết định quyền. Các bài test bằng `@WithMockUser`, `jwt()` hoặc `opaqueToken()` của `spring-security-test` rất hữu ích, nhưng chúng thường **tạo authentication thử nghiệm trực tiếp**. Chúng không nhất thiết gọi bộ kiểm chứng JWT hay endpoint introspection thật.

Ví dụ, một controller được bảo vệ bằng `hasAuthority("SCOPE_reports.read")` có thể vượt qua test:

~~~java
mvc.perform(get("/api/reports")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_reports.read"))))
    .andExpect(status().isOk());
~~~

Đây là đoạn nằm trong một test đã có `MockMvc mvc` và static imports phù hợp. Test này chứng minh **authorization** được thực thi với principal/authority giả lập. Nó **không chứng minh**:

- Access token có chữ ký hợp lệ, thuật toán ký được cho phép hoặc khóa ký đúng.
- `iss` khớp nhà phát hành được tin cậy và `aud` chứa API hiện tại.
- `exp`, `nbf`, clock skew được kiểm tra đúng.
- Spring Security đọc HTTP Bearer header và kích hoạt `JwtDecoder` thực tế.
- Opaque token đã được gửi tới introspection endpoint và nhận `active=true`.
- Client credentials của resource server khi introspect hoạt động.
- Cấu hình discovery/JWKS hoặc identity provider (IdP) vẫn hoạt động qua TLS, proxy và key rotation.

Nếu tất cả test đều “gắn sẵn người dùng đã đăng nhập”, một resource server có thể pass test dù production từ chối mọi access token, bỏ sót audience validation hoặc không truy cập được JWKS.

**Mục tiêu bài:** xây dựng một chiến lược kiểm thử theo tầng để vừa có test nhanh, vừa xác minh đường đi authentication thực tế, và cuối cùng kiểm tra hợp đồng với **nhà cung cấp danh tính bên ngoài**. Các ví dụ hướng tới **Java 17+, Spring Boot 3.x, Spring Security 6.x, Spring MVC/Servlet và JUnit 5**. Tên domain, client ID và token trong bài đều là dữ liệu học tập; không có request nào được tuyên bố đã chạy trên một IdP thực tế.

## 2. Nắm đúng ba lớp kiểm thử

| Lớp | Cách thực hiện | Xác minh được | Chưa xác minh được |
| --- | --- | --- | --- |
| A. Giả lập authentication | `@WithMockUser`, `jwt()`, `opaqueToken()` | URL authorization, method authorization, role/scope mapping giả định, business response | Chữ ký, decoder/introspector, network, credential và IdP |
| B. Thực thi authentication component | Gửi Bearer JWT thật vào `MockMvc` với `JwtDecoder` thật; hoặc gọi `OAuth2TokenIntrospector` thật qua local HTTP stub | Token parsing, signature/claims/expiry, Bearer filter, HTTP introspection request/response, status/challenge | Chính sách và vận hành của IdP thực tế, external TLS/JWKS/rotation thực |
| C. Tích hợp ngoài giả lập | Ứng dụng kết nối IdP dành cho test/staging hoặc môi trường container IdP thực | Discovery, ký/cấp token thật, public keys, scopes, issuer/audience, introspection, rotation/revocation theo hợp đồng | Không thể chứng minh tuyệt đối mọi tình huống production hoặc khả năng chịu tải bằng một test |

Không nên bỏ hẳn lớp A: test giả lập chạy nhanh, ổn định và cho lỗi rõ ràng khi policy thay đổi. Thay vào đó, **bổ sung đủ lớp B và C** cho các ranh giới bảo mật quan trọng.

Một ma trận tối thiểu:

| Tình huống | JWT decoder thật | Opaque introspector thật | IdP tích hợp |
| --- | --- | --- | --- |
| Token hợp lệ và có quyền | Decode/verify chữ ký, map scope | Gửi request introspection, parse active/scope | Nhận token từ IdP và gọi API |
| Không mang token | Bearer authentication entry point | Bearer authentication entry point | Kiểm tra 401 thực tế qua proxy |
| Token bị sửa/chữ ký sai | Bắt buộc test | Không áp dụng chữ ký JWT theo opaque contract | IdP/JWKS production-like |
| `exp` quá hạn / `nbf` chưa đến | Bắt buộc test khi dùng JWT | Introspection response/validation tùy contract | Token lifetime thật và skew |
| Issuer/audience không đúng | Bắt buộc khi API có trust boundary | Thường dựa vào policy introspection và claims | Sai IdP/sai client/sai resource |
| `active=false` | Không áp dụng | Bắt buộc test | Thu hồi token thật |
| Scope không đủ | 403 sau authentication | 403 sau introspection | Scope/consent/claims từ IdP |
| JWKS unavailable/rotate | Test qua HTTP JWKS stub | Không áp dụng trừ thiết kế lai | Test rotate key và cache/độ trễ |
| Endpoint introspection 401/5xx/timeout | Không áp dụng | Bắt buộc test | Cấu hình client secret, TLS, khả năng chịu lỗi |

## 3. Đường đi thực của HTTP Bearer trong Servlet

Resource Server dùng JWT thông thường:

~~~text
HTTP request: Authorization: Bearer eyJ...
          │
          ▼
Spring Security Servlet FilterChainProxy
          │
          ▼
BearerTokenAuthenticationFilter
          │  resolve Bearer token
          ▼
AuthenticationManager
          │
          ▼
JwtAuthenticationProvider
          │
          ├─ JwtDecoder: parse + kiểm chữ ký + validate claims
          │
          └─ JwtAuthenticationConverter: đổi claims/scope → authorities
          │
          ▼
Authentication trong SecurityContext
          │
          ▼
authorizeHttpRequests / @PreAuthorize / business checks
          │
          ├─ allowed ───────────► controller
          └─ denied ────────────► AccessDeniedHandler
~~~

Với opaque token, đường giữa thay bằng `OpaqueTokenAuthenticationProvider` và `OAuth2TokenIntrospector`. Bộ introspector hỏi một endpoint thuộc authorization server hoặc một service kiểm token đáng tin. Mặc định, authorization server trả thuộc tính như `active`, `scope`, `sub`, `exp`; response còn phải được xử lý theo contract của nhà cung cấp và cấu hình Spring Security.

**Các khẳng định phải tách biệt:**

- **401 Unauthorized**: chưa có credentials thích hợp hoặc token bị từ chối; Bearer challenge có thể có `invalid_token`.
- **403 Forbidden**: authentication đã đạt nhưng thiếu quyền phù hợp, ví dụ `SCOPE_reports.read`; có thể có `insufficient_scope` khi đúng ngữ cảnh.
- **400 Bad Request**: một số lỗi cú pháp Bearer như `invalid_request`, phụ thuộc nơi phát hiện.
- **5xx / unavailable**: service xác thực phụ thuộc bị lỗi. Không được giả mọi lỗi network thành “token sai”; client cần phân biệt credential error với sự cố vận hành.
- **HTTP status của `MockMvc`** phụ thuộc filter chain, handlers và policy được cấu hình trong test; hãy khẳng định các thuộc tính thuộc về đúng tầng.

Đối với JWT, **chỉ đọc được payload không nghĩa là đã xác minh JWT**. Các chuỗi Base64URL trong header/payload ai cũng có thể tạo; kiểm tra chữ ký với khóa công khai phù hợp, issuer, audience, timestamps và các claims cần thiết mới thiết lập trust.

## 4. Thiết lập Spring Boot Resource Server cho bài test JWT

Ví dụ ứng dụng dùng JWT và chỉ mở endpoint báo cáo khi token có `SCOPE_reports.read`. Project build qua Gradle; không chạy các file Spring bằng JDK thuần vì còn cần Spring, Nimbus JOSE/JWT, JUnit và Servlet runtime.

### 4.1. Dependencies

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Boot BOM quản lý phiên bản tương thích nếu dự án áp plugin/dependency management của Spring Boot. Không thêm thư viện JWT tự viết để “test cho nhanh”. Spring Security Resource Server JWT sử dụng Nimbus JOSE/JWT qua dependencies thích hợp.

Các file Java ví dụ thuộc package `com.example.demo`.

### 4.2. Entry point của ứng dụng

File `DemoApplication.java`:

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 4.3. SecurityFilterChain

File `SecurityConfig.java`:

~~~java
package com.example.demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .sessionManagement(s -> s
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public").permitAll()
                .requestMatchers("/api/reports")
                    .hasAuthority("SCOPE_reports.read")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth -> oauth
                .jwt(Customizer.withDefaults()));

        return http.build();
    }
}
~~~

Ứng dụng trong ví dụ chỉ có GET. Nếu thêm POST/PUT/DELETE, cần đánh giá **CSRF theo mô hình credentials**: với API stateless chỉ nhận Bearer header có thể dùng policy riêng; với session cookie/browser không được tắt CSRF toàn cục một cách máy móc. Việc `STATELESS` không thay thế permission check.

File `ReportController.java`:

~~~java
package com.example.demo;

import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ReportController {

    @GetMapping("/api/public")
    public Map<String, String> publicInfo() {
        return Map.of("status", "public");
    }

    @GetMapping("/api/reports")
    public Map<String, String> reports() {
        return Map.of("status", "ok");
    }
}
~~~

Cấu hình production có thể dùng:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://issuer.example.test/realms/demo
~~~

Domain này là **ví dụ**. Khi dùng issuer discovery thật, Spring Security có thể truy xuất metadata/JWKS theo cấu hình và phiên bản. Cần cấu hình bổ sung **audience validation** nếu API đòi `aud=reports-api`; kiểm issuer/expiry không có nghĩa mặc định mọi JWT decoder đã kiểm đúng audience mong muốn.

Trong test tiếp theo, bean `JwtDecoder` **chỉ dành cho test** sẽ thay việc cần truy cập issuer bên ngoài. Nó thực sự xác minh chữ ký với một cặp khóa sinh trong test, chứ không giả lập `JwtDecoder.decode(...)`.

## 5. Kiểm thử JWT thật bằng MockMvc và cặp RSA sinh trong test

### 5.1. Khác biệt so với .with(jwt())

Thay vì:

~~~java
mvc.perform(get("/api/reports").with(jwt()))
~~~

hãy tạo một JWT **có chữ ký số** rồi gửi như HTTP header:

~~~http
GET /api/reports HTTP/1.1
Authorization: Bearer <signed-jwt-created-in-test>
~~~

Khi đó `BearerTokenAuthenticationFilter` lấy token từ header, `JwtAuthenticationProvider` gọi `JwtDecoder`, chữ ký và validators được thực thi, rồi scope mới được chuyển thành authority.

Thiết kế test địa phương có hai thành phần:

1. Test tạo một cặp **RSA key pair** trong memory và dùng private key ký JWT qua `NimbusJwtEncoder`.
2. Test cung cấp **`NimbusJwtDecoder` thật** dùng public key tương ứng và validators về issuer, audience, timestamps.

Như vậy có thể kiểm tra signature/claims mà **không** cần nhà cung cấp danh tính online ở mỗi lần chạy. Dù vậy vẫn chưa kiểm tra discovery, JWKS cache/rotation, TLS hoặc contract của IdP thật — những phần đó thuộc lớp tích hợp tiếp theo.

### 5.2. Full integration test (Java 17+, Spring Boot 3.x)

File `RealJwtHttpTest.java` dưới `src/test/java/com/example/demo/`. Nó sử dụng controller và security config ở mục 4.

~~~java
package com.example.demo;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;
import java.time.Instant;
import java.util.List;

import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jose.jwk.source.ImmutableJWKSet;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpHeaders;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtClaimsSet;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.JwtEncoderParameters;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.JwsHeader;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.oauth2.jwt.NimbusJwtEncoder;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
@Import(RealJwtHttpTest.LocalJwtKeys.class)
class RealJwtHttpTest {

    private static final String ISSUER =
        "https://issuer.example.test";
    private static final String AUDIENCE = "reports-api";

    @Autowired
    MockMvc mvc;

    @Autowired
    JwtEncoder encoder;

    // Tạo JWT thật, không dùng jwt() request post-processor.
    private String signedToken(String issuer, String audience,
                               String scope, long expiresInSeconds) {
        Instant now = Instant.now();
        JwtClaimsSet claims = JwtClaimsSet.builder()
            .issuer(issuer)
            .subject("alice")
            .audience(List.of(audience))
            .issuedAt(now.minusSeconds(120))
            .notBefore(now.minusSeconds(5))
            .expiresAt(now.plusSeconds(expiresInSeconds))
            .claim("scope", scope)
            .build();

        JwsHeader header = JwsHeader
            .with(SignatureAlgorithm.RS256)
            .keyId("local-test-key")
            .build();

        return encoder.encode(
            JwtEncoderParameters.from(header, claims))
            .getTokenValue();
    }

    @Test
    void signedJwtWithExpectedClaimsIsAccepted()
            throws Exception {
        mvc.perform(get("/api/reports")
                .header(HttpHeaders.AUTHORIZATION,
                    "Bearer " + signedToken(
                        ISSUER, AUDIENCE, "reports.read", 300)))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("ok"));
    }

    @Test
    void missingTokenIsUnauthorized() throws Exception {
        mvc.perform(get("/api/reports"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                HttpHeaders.WWW_AUTHENTICATE,
                containsString("Bearer")));
    }

    @Test
    void expiredJwtIsRejectedBeforeAuthorization()
            throws Exception {
        mvc.perform(get("/api/reports")
                .header(HttpHeaders.AUTHORIZATION,
                    "Bearer " + signedToken(
                        ISSUER, AUDIENCE, "reports.read", -60)))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void wrongIssuerIsRejected() throws Exception {
        mvc.perform(get("/api/reports")
                .header(HttpHeaders.AUTHORIZATION,
                    "Bearer " + signedToken(
                        "https://other.example.test",
                        AUDIENCE, "reports.read", 300)))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void wrongAudienceIsRejected() throws Exception {
        mvc.perform(get("/api/reports")
                .header(HttpHeaders.AUTHORIZATION,
                    "Bearer " + signedToken(
                        ISSUER, "another-api", "reports.read", 300)))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void validJwtWithoutRequiredScopeIsForbidden()
            throws Exception {
        mvc.perform(get("/api/reports")
                .header(HttpHeaders.AUTHORIZATION,
                    "Bearer " + signedToken(
                        ISSUER, AUDIENCE, "profile.read", 300)))
            .andExpect(status().isForbidden());
    }

    @Test
    void changedSignatureFailsCryptoVerification()
            throws Exception {
        String valid = signedToken(
            ISSUER, AUDIENCE, "reports.read", 300);

        String[] pieces = valid.split("\\.");
        // Đổi byte đầu chữ ký dạng Base64URL,
        // không sửa header/payload đã được ký.
        String signature = pieces[2];
        pieces[2] = (signature.charAt(0) == 'A' ? "B" : "A")
            + signature.substring(1);
        String forged = String.join(".", pieces);

        mvc.perform(get("/api/reports")
                .header(HttpHeaders.AUTHORIZATION,
                    "Bearer " + forged))
            .andExpect(status().isUnauthorized());
    }

    @TestConfiguration
    static class LocalJwtKeys {

        @Bean
        KeyPair testKeyPair() throws Exception {
            KeyPairGenerator generator =
                KeyPairGenerator.getInstance("RSA");
            generator.initialize(2048);
            return generator.generateKeyPair();
        }

        @Bean
        JwtEncoder jwtEncoder(KeyPair pair) {
            RSAKey jwk = new RSAKey.Builder(
                    (RSAPublicKey) pair.getPublic())
                .privateKey((RSAPrivateKey) pair.getPrivate())
                .keyID("local-test-key")
                .build();

            return new NimbusJwtEncoder(
                new ImmutableJWKSet<>(new JWKSet(jwk)));
        }

        @Bean
        JwtDecoder jwtDecoder(KeyPair pair) {
            NimbusJwtDecoder decoder = NimbusJwtDecoder
                .withPublicKey((RSAPublicKey) pair.getPublic())
                .build();

            OAuth2TokenValidator<Jwt> audience = jwt ->
                jwt.getAudience().contains(AUDIENCE)
                    ? OAuth2TokenValidatorResult.success()
                    : OAuth2TokenValidatorResult.failure(
                        new OAuth2Error(
                            "invalid_token",
                            "Unexpected audience",
                            null));

            decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(
                    JwtValidators.createDefaultWithIssuer(ISSUER),
                    audience));
            return decoder;
        }
    }
}
~~~

**Đây là integration test ở mức Spring application context và Servlet filter chain**; không có Mockito mock `JwtDecoder`, không dùng `jwt()` shortcut. Cặp khóa RSA được tạo trong test, private key không ra khỏi JVM. Method `changedSignatureFailsCryptoVerification` sửa một ký tự đầu chữ ký nhằm làm chữ ký sai thay vì thay claims rồi kỳ vọng decoder bỏ qua chữ ký.

Các test khẳng định:

- JWT đúng chữ ký, issuer, audience, hạn và scope → 200 từ controller.
- Không token, JWT hết hạn/sai issuer/sai audience/sai signature → 401.
- JWT **đúng về authentication** nhưng thiếu `SCOPE_reports.read` → 403.

**Giới hạn cần nhận biết:** bài test với `NimbusJwtDecoder.withPublicKey(...)` không gọi endpoint JWKS/metadata. Nó chưa kiểm tra việc ứng dụng tìm public key thật, cache keys, chọn `kid` hoặc chịu key rotation. Phần đó cần một integration test `NimbusJwtDecoder.withJwkSetUri(...)` với HTTP JWKS server hoặc kết nối IdP test thật.

Đừng trả lời “đã test IdP end-to-end” chỉ vì tạo JWT cục bộ rồi decode được. Điều đã được chứng minh ở đây là **JWT cryptographic validation và authentication/authorization pipeline** trong ứng dụng, với policy validation do test thiết lập.

### 5.3. Run và đọc kết quả

Chạy trong dự án Gradle có các file ví dụ và dependency ở trên:

~~~bash
./gradlew test --tests com.example.demo.RealJwtHttpTest
~~~

Trên Windows:

~~~powershell
.\gradlew.bat test --tests com.example.demo.RealJwtHttpTest
~~~

Dự án Maven tương đương có thể chạy `./mvnw -Dtest=RealJwtHttpTest test`. Những ví dụ này là **lệnh cần chạy trong project**, không phải stdout đã thực sự nhận được. Kết quả phụ thuộc phiên bản Boot/Security, cấu hình context, các bean khác và môi trường. Nếu context trùng nhiều JwtDecoder/SecurityFilterChain, cần điều chỉnh để test dùng đúng bean và chain mục tiêu.

**Không hardcode expected stdout của Gradle**, vì số lượng test và log thay đổi. Lời khẳng định cần thiết là các assertions thực sự chạy trên HTTP Bearer filter và decoder thật.

## 6. Kiểm thử JWT bằng JWKS endpoint HTTP thay cho public key hardcode

Trường hợp production phổ biến là resource server lấy public keys theo URL **JWKS**. Khác test `withPublicKey(...)`, cấu hình `withJwkSetUri(...)` có thể thực hiện HTTP tới endpoint để lấy public keys và chọn key theo `kid` khi xác minh JWT.

Các mốc kiểm thử có giá trị:

1. Tạo cặp RSA key A trong test, public key xuất thành JWK với `kid="key-a"`. Chỉ public key được trả ở endpoint JWKS; **không đưa private key ra HTTP**.
2. Chạy HTTP test server cục bộ trả `{"keys":[{...public JWK...}]}` tại `/jwks`.
3. Tạo `NimbusJwtDecoder.withJwkSetUri("http://127.0.0.1:<port>/jwks").build()` làm bean test và gửi JWT ký bởi key A, header có `kid="key-a"`.
4. Kiểm tra decoder gọi JWKS, dùng key đúng và trả 200 nếu token/claims hợp lệ.
5. Ký một token bằng key B không có trong JWKS hoặc sai `kid`: response phải từ chối, không chấp nhận fallback tùy tiện.
6. Khi IdP rotate key, cập nhật JWKS phù hợp và kiểm tra behavior sau khi cache làm mới; không giả định decoder fetch mỗi request hoặc cache hết hạn ngay. Việc làm mới có thể phụ thuộc JWKS cache policy/phiên bản.

JWKS test trên loopback giúp phát hiện lỗi URL, HTTP client và xử lý key set mà test RSA trực tiếp không chạm tới. Nó **vẫn là local fake IdP endpoint**; chỉ kiểm tra hợp đồng JWKS bạn đã dựng, không kiểm chứng metadata hoặc policy thật của IdP bên ngoài.

Một sai lầm nguy hiểm là tắt issuer/audience validation để “JWT ký bằng test key pass”. Test key và test claim nên phù hợp policy, còn policy production phải giữ chặt. Nếu ứng dụng định nghĩa custom `JwtDecoder`, hãy chắc chắn bạn không vô tình thay mất validators mặc định về thời gian hoặc issuer khi gắn audience validator.

### Về thuật toán ký và key confusion

- Chỉ nhận những thuật toán được cấu hình cho trust contract, ví dụ RS256 nếu thực tế issuer dùng RS256. Không dựa vào trường `alg` trong token như một lựa chọn tin cậy của caller.
- Không chấp nhận `alg=none` vì “test token không ký cho nhanh”.
- Không chấp nhận một JWT được ký bởi key của issuer khác dù `sub` và `scope` trông hợp lệ.
- Không suy diễn `kid` là URL và tự tải khóa từ địa chỉ attacker-controlled; chỉ lấy JWKS từ nguồn đã cấu hình/được tin cậy.
- Kiểm tra `iss`, `aud` và `exp/nbf` có ý nghĩa đối với **API này**. Một JWT ký đúng nhưng audience thuộc client khác vẫn phải bị từ chối.

## 7. Kiểm thử OAuth2TokenIntrospector thật qua HTTP nội bộ

### 7.1. Khi nào dùng opaque token?

Opaque access token là chuỗi mà resource server không tự xác minh chữ ký/claims như JWT. Thay vào đó resource server hỏi **introspection endpoint** theo OAuth 2.0 Token Introspection (RFC 7662). Authorization server quyết định token có active hay không và trả metadata thích hợp.

Spring Security Servlet có thể cấu hình:

~~~java
http.oauth2ResourceServer(oauth -> oauth
    .opaqueToken(Customizer.withDefaults()));
~~~

Đây là **đoạn trong cấu hình `HttpSecurity`**, cần import `Customizer`/các class và bean introspector phù hợp. Trong ứng dụng thật cấu hình introspection URI cùng client credentials theo hệ thống phát hành token:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://issuer.example.test/oauth2/introspect
          client-id: resource-server-client
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
~~~

Đây là ví dụ Boot property, `${...}` là placeholder lấy secret từ env/secret manager sau khi điền cấu hình thực tế. Không commit secret vào Git hoặc lưu introspection response có token trong logs.

Một shortcut thường thấy:

~~~java
mvc.perform(get("/api/reports")
        .with(opaqueToken().authorities(
            new SimpleGrantedAuthority("SCOPE_reports.read"))))
    .andExpect(status().isOk());
~~~

Test đó **không gọi `OAuth2TokenIntrospector.introspect(token)`**. Nó giả tạo principal đã được xác thực. Để test introspection, cần dùng implementation thật và quan sát request/response HTTP.

### 7.2. Test protocol HTTP bằng một local introspection endpoint

Ví dụ sau dùng HTTP server có sẵn trong JDK (module `jdk.httpserver`) để làm **stub của authorization server**. Nó không mock interface `OAuth2TokenIntrospector`: implementation `NimbusOpaqueTokenIntrospector` thật phải gửi HTTP POST, gửi client authentication và xử lý response.

File `IntrospectionHttpTest.java` trong package `com.example.demo`:

~~~java
package com.example.demo;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.Arrays;
import java.util.Base64;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.NimbusOpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

class IntrospectionHttpTest {

    private HttpServer server;
    private OpaqueTokenIntrospector introspector;

    @BeforeEach
    void startServer() throws IOException {
        server = HttpServer.create(
            new InetSocketAddress("127.0.0.1", 0), 0);

        server.createContext("/introspect", exchange -> {
            try {
                String authorization = exchange
                    .getRequestHeaders()
                    .getFirst("Authorization");

                String expected = "Basic " + Base64.getEncoder()
                    .encodeToString(
                        "resource-client:local-secret".getBytes(
                            StandardCharsets.UTF_8));

                if (!"POST".equals(exchange.getRequestMethod())
                    || !expected.equals(authorization)) {
                    send(exchange, 401, "{}");
                    return;
                }

                String form = new String(
                    exchange.getRequestBody().readAllBytes(),
                    StandardCharsets.UTF_8);

                String token = Arrays.stream(form.split("&"))
                    .filter(p -> p.startsWith("token="))
                    .findFirst()
                    .map(p -> URLDecoder.decode(
                        p.substring(6), StandardCharsets.UTF_8))
                    .orElse("");

                if (!"active-token".equals(token)) {
                    send(exchange, 200, "{\"active\":false}");
                    return;
                }

                long exp = Instant.now().plusSeconds(300)
                    .getEpochSecond();

                send(exchange, 200,
                    "{\"active\":true,\"sub\":\"alice\","
                    + "\"client_id\":\"client-1\","
                    + "\"scope\":\"reports.read\","
                    + "\"exp\":" + exp + "}");
            } finally {
                exchange.close();
            }
        });

        server.start();
        String uri = "http://127.0.0.1:"
            + server.getAddress().getPort()
            + "/introspect";

        introspector = new NimbusOpaqueTokenIntrospector(
            uri, "resource-client", "local-secret");
    }

    private static void send(HttpExchange exchange, int code,
                             String body) throws IOException {
        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set(
            "Content-Type", "application/json");
        exchange.sendResponseHeaders(code, bytes.length);
        exchange.getResponseBody().write(bytes);
    }

    @AfterEach
    void stopServer() {
        if (server != null) {
            server.stop(0);
        }
    }

    @Test
    void activeTokenProducesPrincipalAndScope() {
        OAuth2AuthenticatedPrincipal principal =
            introspector.introspect("active-token");

        assertEquals("alice", principal.getAttribute("sub"));
        assertTrue(principal.getAuthorities().stream().anyMatch(
            a -> "SCOPE_reports.read".equals(a.getAuthority())));
    }

    @Test
    void inactiveTokenIsRejected() {
        assertThrows(BadOpaqueTokenException.class,
            () -> introspector.introspect("revoked-token"));
    }
}
~~~

**Kết quả mà test này dự định xác minh:** client gửi HTTP POST tới một endpoint local, sử dụng Basic client authentication, chuyển token trong request body form-encoded và xử lý phản hồi `active=true/false`. Nó không khẳng định đã gọi một provider thật.

**Giới hạn:** đây là test **component-level introspector**; nó không tự chứng minh `BearerTokenAuthenticationFilter`, security chain và controller hoạt động với opaque token. Nếu cần đủ lớp HTTP của resource server, tạo một `@SpringBootTest @AutoConfigureMockMvc` với bean `OpaqueTokenIntrospector` trỏ đến stub và gửi header `Authorization: Bearer active-token` qua `MockMvc`; assert 200/401/403 theo policy. Khi đó mock chỉ nằm ở HTTP endpoint **bên ngoài**, không nằm ở API introspector.

Nếu build tool không resolve module `jdk.httpserver` của JDK, cấu hình test JVM với `--add-modules jdk.httpserver` hoặc dùng WireMock/MockWebServer có dependency phù hợp. Trong production không dùng HTTP thường cho introspection: bắt buộc đánh giá TLS, credential handling, endpoint auth, timeout và network policy.

### 7.3. Kiểm thử lỗi của introspection endpoint

Một suite đầy đủ nên đổi stub response theo từng tình huống:

| Response của introspection endpoint | Kỳ vọng |
| --- | --- |
| HTTP 200, `{"active":true,...}` với scopes phù hợp | Principal được nhận; authorization kiểm quyền |
| HTTP 200, `{"active":false}` | Token bị từ chối |
| HTTP 200, active true nhưng thiếu scope | Token được xác thực nhưng route cần scope sẽ 403 |
| HTTP 401 từ introspection endpoint | Client authentication/resource server credentials sai; không nhầm với token user hết hạn |
| HTTP 500/503, timeout, TLS failure | Lỗi hạ tầng/service; không coi là token active |
| HTTP 200 nhưng JSON không hợp lệ/thiếu trường cần | Từ chối hoặc báo lỗi phù hợp, **fail closed** |
| Token khác nhưng cùng user | Không mặc định tái sử dụng kết quả không kiểm chứng |

**Không kết luận chỉ từ “200 response”**: RFC 7662 thường dùng HTTP 200 cho introspection thành công kể cả khi token không active. Ý nghĩa nằm ở `active=true/false`, không phải HTTP status của introspection HTTP call.

Cần kiểm tra **authorization server-specific claims**: một số IdP trả `scope`, `client_id`, `aud`, `exp` khác nhau. Resource server chỉ nên dựa vào thuộc tính đã được thỏa thuận và kiểm chứng; không tự thêm quyền nếu response thiếu scope.

Nếu hệ thống cache introspection result để giảm tải, phải test TTL, revocation window và khóa cache theo đúng token. Caching `active=true` quá lâu có thể cho phép token đã bị thu hồi tiếp tục có hiệu lực. Cân nhắc hành vi khi introspection service unavailable: hệ thống bảo mật nhạy cảm thường **fail closed**.

## 8. Khi nào phải kiểm thử với IdP thực sự?

Local signed-JWT và local introspection stub chỉ chứng minh **một phần hợp đồng** mà bạn đã dựng. Khi IdP thật thay đổi issuer, thuật toán ký, endpoint path, claim mapping hoặc quyền client, ứng dụng có thể lỗi dù mock và local tests đều xanh.

**Tầng tích hợp IdP test** nên dùng một trong hai cách:

- **IdP test/staging do tổ chức kiểm soát**: client registration riêng, issuer riêng, access scopes/roles riêng, certificate và secrets do secret manager cấp. Không chạy test tự động với tài khoản hoặc token production.
- **IdP chạy trong môi trường cô lập (ví dụ container)**: có metadata OIDC/OAuth2, JWKS, grant/token endpoint và introspection đúng như hợp đồng. Nên cố định phiên bản image/container và dữ liệu realm/client để test tái lập được. Đây là IdP thực thi thật nhưng có thể vẫn khác provider production.

Các bước kiểm thử tích hợp có ý nghĩa:

1. **Provision client dành cho test:** đăng ký client/resource server với redirect URI hoặc service grant, scopes và audience chính xác; dùng quyền tối thiểu.
2. **Truy xuất metadata hoặc cấu hình endpoint:** xác minh issuer URI, token URI, introspection URI, JWKS URI và TLS certificates theo nhà cung cấp.
3. **Lấy token thật theo grant phù hợp:** client credentials cho service-to-service; authorization code/PKCE cho user interactive; không hardcode mật khẩu người dùng trong test.
4. **Gọi Resource Server HTTP thực tế** với access token qua `Authorization: Bearer ...`, assert status, body tối thiểu và absence of sensitive data.
5. **Sai issuer hoặc audience:** dùng token của một môi trường/client/API khác và xác minh bị từ chối, không chấp nhận nhờ chữ ký từ key nằm trong một kho tin cậy quá rộng.
6. **Sai scope/role:** token hợp lệ nhưng thiếu quyền trả 403; cấp đúng scope mới có quyền. Test mapping claims theo cấu hình IdP thật.
7. **Hết hạn/thu hồi:** dùng token ngắn hạn và token bị thu hồi hoặc `active=false`; xác minh cache, refresh/re-auth logic không bypass revocation.
8. **Key rotation:** thêm key mới, xoay `kid`, giữ old key theo grace period hợp đồng; xác minh decoder dùng JWKS/cache và xử lý thời điểm old key biến mất.
9. **Lỗi availability:** đóng đường tới IdP hoặc mô phỏng timeout/DNS/TLS error; ứng dụng không fail open, không leak credential/stack trace.
10. **Cleanup:** xóa test users, revoke test tokens/clients khi thích hợp, không để test tạo credentials tồn tại lâu hoặc gây side effect trên hệ thống thật.

**Kết luận kiểm thử:** token đã được *provider thật* cấp và resource server chấp nhận mới kiểm tra được **hợp đồng giữa hai hệ thống**, chứ không chỉ một test key do chính ứng dụng tạo ra.

### 8.1. Test run ở CI và lịch chạy

Không nên buộc mọi pull request gọi IdP staging công cộng để chạy toàn bộ test authentication. Một phân lớp thực tế:

- **Mỗi commit/PR:** unit policy tests, `MockMvc` với JWT ký local/decoder thật, introspector với stub HTTP loopback. Không có secrets production, chạy nhanh và lặp lại được.
- **Pipeline tích hợp / pre-release:** container IdP hoặc environment ephemeral, kiểm tra metadata/JWKS, actual token issuance, introspection protocol và sự tương thích phiên bản.
- **Smoke test staging định kỳ/đợt triển khai:** kiểm tra IdP vendor thực tế, TLS/redirect/callback, scopes, role/audience và availability contract.

Việc phân tầng giúp CI không dễ bị flaky vì network, nhưng vẫn bảo đảm những lỗi cấu hình integration quan trọng không lọt qua.

### 8.2. Token của IdP thực tế thường phải có audience rõ ràng

Một JWT có chữ ký đúng và `iss` đáng tin có thể được cấp cho **API khác**. Nếu resource server chấp nhận mọi audience, token dùng ở hệ thống A có thể bị replay sang hệ thống B. Test phải chứng minh token khác audience bị từ chối.

Spring Security cung cấp validators có thể cấu hình để kiểm issuer, timestamp và audience; **đừng giả định `issuer-uri` tự suy ra mọi audience cần kiểm**. Tương tự, OAuth scopes không tương đương quyền trên mọi resource: action cụ thể còn phải kiểm user/tenant/owner.

## 9. Kiểm thử HTTP status, challenge và phần không nên tiết lộ

Với Bearer authentication của Resource Server, quan sát cả status và `WWW-Authenticate`, không chỉ body:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
~~~

Khi token không hợp lệ, response có thể kèm mã chuẩn:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

Khi token hợp lệ nhưng thiếu scope, response có thể là:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
~~~

Các ví dụ là **hình thức minh họa**, không phải response byte-for-byte cố định. Spring Security còn có thể thêm `realm` và các tham số khác, và behavior bị ảnh hưởng bởi entry point, AccessDeniedHandler hoặc proxy. Không assert một chuỗi header chính xác khi hệ thống có policy cho phép nhiều biểu diễn hợp lệ.

Kiểm tra an toàn:

- Không xuất access token, refresh token, client secret, private RSA key hoặc Authorization header trong response hoặc logs.
- Không đưa raw `JwtException.getMessage()` hay introspection HTTP body nhạy cảm ra `error_description`.
- Đối với guest, 401 giúp client biết cần Bearer token; token đúng nhưng thiếu quyền mới chuyển tới 403.
- Một 401 từ **introspection endpoint do client auth sai** là lỗi upstream/service integration; đừng báo cho end user rằng access token của họ đã chắc chắn hết hạn.
- Khi IdP không liên lạc được, xử lý lỗi server-side an toàn, có correlation ID, alert/metrics và retry giới hạn, không vô hạn retry hoặc chấp nhận mọi token khi offline.

Trong test, có thể dùng assertions kiểm tra header **không chứa chuỗi chẩn đoán riêng**, nhưng không cần hiện token ra test report. Khi cần log để debug, chỉ log route template, request ID, error category, issuer đã cấu hình và status, tránh log PII hoặc claims nhạy cảm.

## 10. Phân biệt bốn câu hỏi thường bị trộn trong test

### 10.1. “Người dùng đã xác thực chưa?”

Test authentication/decoder/introspector: chữ ký hoặc introspection, token active, expiry, issuer, audience. Nếu không đạt, không tạo authenticated principal tin cậy.

### 10.2. “Principal có authority cần thiết không?”

Test converter/authorization mapping: claim `scope="reports.read"` có thể được convert thành `SCOPE_reports.read` theo convention. Nếu IdP trả `roles`, `groups` hoặc namespaced claims thay vì `scope`, cần custom `JwtAuthenticationConverter`/introspector mapping theo hợp đồng. Đừng thêm authority thẳng trong test rồi coi converter đã được kiểm.

### 10.3. “Principal có quyền với đúng resource không?”

Ngay cả token `reports.read` cũng không có nghĩa Alice xem được mọi report của Bob hay mọi tenant. Service phải kiểm quyền sở hữu/ACL/tenant và test dữ liệu thật ở ranh giới nghiệp vụ. JWT validation và scopes mới là điều kiện cần.

### 10.4. “IdP hoạt động đúng hợp đồng không?”

Chỉ tích hợp thật với metadata/JWKS, cấp token, introspection, TLS và lifecycle mới kiểm được. Một local HTTP stub chỉ xác minh **kỳ vọng của resource server về giao thức**, không xác minh nhà cung cấp luôn trả đúng dữ liệu.

Đây là lý do không thể thay một suite tích hợp bằng câu “test jwt() cho ra 200”.

## 11. Những lỗi kiểm thử phổ biến và cách nhận biết

| Triệu chứng | Nguyên nhân hay gặp | Hướng sửa |
| --- | --- | --- |
| Test JWT pass với `jwt()` nhưng production mọi token trả 401 | Test bypass decoder hoặc sai `issuer-uri`/JWKS | Gửi signed JWT qua Bearer header với decoder thật; thêm test IdP |
| JWT sai audience vẫn được chấp nhận | Chưa có audience validator, hoặc test chỉ mock authority | Thêm validator và negative test wrong-aud |
| JWT hết hạn vẫn cho 200 trong test | Dùng mock authentication không có exp validation | Test token ký thật với exp quá hạn |
| Token sai signature không bị test phát hiện | Không dùng cryptographic validator | Tamper chữ ký hoặc dùng untrusted signer trên decoder thật |
| JWT đúng chữ ký nhưng thiếu scope cho 403 không được kiểm | Chỉ test parse JWT | Test converter + HTTP authorization với token thiếu scope |
| Token `active=false` vẫn pass test opaqueToken() | Post-processor bypass introspector | Test `NimbusOpaqueTokenIntrospector` qua HTTP trả active=false |
| Introspection HTTP 200 nên test tưởng token hợp lệ | Bỏ qua thuộc tính `active` trong response | Khẳng định semantics active=true/false |
| Resource Server luôn gọi IdP thật ở unit test | Không tách local integration fixture | Dùng test JWT key hoặc local introspection server, E2E ở stage riêng |
| CI bị fail ngẫu nhiên khi JWKS cache/rotate | Test phụ thuộc timer/network/key state không kiểm soát | Fixture keys và fake clock/cache rõ ràng; thêm E2E định kỳ |
| Introspection trả 401 do client secret sai | Nhầm client authentication của resource server với token của người dùng | Kiểm client ID/secret, auth method, URL và TLS |
| Test tạo JWT “signed” nhưng không chạy Bearer filter | Gọi `decoder.decode(...)` trực tiếp, bỏ HTTP security chain | Bổ sung `MockMvc` với Authorization header thật |
| Test có HTTP 401 nhưng không biết do đâu | Proxy/Basic auth thay Resource Server entry point | Quan sát `WWW-Authenticate` và logs ở đúng tầng |
| Test scope có quyền nhưng user xem sai tenant | Authorization chỉ theo scope, thiếu object-level check | Test ACL/owner/tenant ở service/resource layer |
| Test viết secret vào report hay code | In token/JWK private key hoặc commit fixture bí mật | Chỉ dùng key ephemeral, secret manager, redaction |
| Startup Resource Server lỗi khi chạy offline | IdP discovery hoặc JWKS availability trong test | Tiêm test decoder rõ ràng, kiểm external discovery ở tầng tích hợp |

### Khi nào dùng Mockito mock đúng cách?

Mockito mock `JwtDecoder` hoặc `OAuth2TokenIntrospector` có thể phù hợp với **test xử lý ngoại lệ, controller, service nhanh**. Ví dụ muốn test khi decoder throw lỗi mà không quan tâm chữ ký số. Nhưng phải ghi đúng phạm vi test: **error handling với mock**, không được gắn nhãn “JWT validation integration test”.

Trong test component thật, có thể mock repository/downstream service, nhưng **không mock chính decoder/introspector đang được kiểm tra**. Trong test E2E IdP, đừng thay IdP bằng stub rồi tuyên bố đã xác minh TLS/issuer discovery của vendor.

## 12. Checklist nghiệm thu dành cho Resource Server Servlet

- [ ] Có test policy nhanh bằng `jwt()/opaqueToken()/@WithMockUser` nhưng không xem chúng là bằng chứng crypto/introspection.
- [ ] Có `MockMvc` gửi `Authorization: Bearer <JWT có chữ ký thật>` và dùng `JwtDecoder` thật.
- [ ] Có case JWT hợp lệ, mất token, exp/nbf sai, issuer/audience sai, signature sai, scope thiếu, scope đủ.
- [ ] Đã kiểm scope/claims converter hoạt động với **claims đến từ token thật**, không chỉ authorities được gán bằng mock.
- [ ] Nếu dùng JWKS remote, đã test metadata/JWK URL, `kid`, không đúng key, key rotation/cache và endpoint unavailable.
- [ ] Nếu dùng opaque token, đã chạy `OAuth2TokenIntrospector` thật qua HTTP với active true/false, client credentials, error/timeout.
- [ ] Có test toàn bộ `BearerTokenAuthenticationFilter → Authentication → authorization → controller`; component test riêng không thay HTTP test.
- [ ] Có test hợp đồng với IdP thử nghiệm, actual token issuance, issuer/aud/scopes, refresh/revocation theo grant phù hợp.
- [ ] Phân biệt 400/401/403/5xx và kiểm `WWW-Authenticate` phù hợp với cơ chế Bearer đang dùng.
- [ ] Không có token/secret/private key/claims nhạy cảm bị log hoặc lộ trong response/CI artifacts.
- [ ] Chạy test security âm tính, timeout/retry, concurrent request, multi-tenant, key rotation trước khi phát hành.
- [ ] Môi trường test dùng secrets/clients riêng, HTTPS với IdP thật và cleanup tự động.
- [ ] Kết quả test nêu rõ lớp A, B hay C; không diễn đạt vượt quá những thành phần thực sự đã chạy.

**Kết luận:** `@WithMockUser`, `jwt()` và `opaqueToken()` giúp kiểm authorization nhanh, nhưng **không thay** kiểm thử authentication thật. Để đánh giá Spring Security Servlet Resource Server đầy đủ, cần test JWT qua **JwtDecoder với chữ ký/validators thật**, opaque token qua **OAuth2TokenIntrospector và HTTP introspection thật**, rồi xác minh **hợp đồng issuer/JWKS/grants/claims/revocation** với nhà cung cấp danh tính ngoài giả lập. Mỗi tầng có giá trị riêng và phải được báo cáo đúng giới hạn.
