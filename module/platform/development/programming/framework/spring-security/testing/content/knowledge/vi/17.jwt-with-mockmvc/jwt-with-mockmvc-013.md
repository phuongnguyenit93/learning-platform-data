# Không dùng JWT giả lập để kết luận chữ ký hoặc hạn token đã được kiểm tra

## 1. Bài toán và giới hạn cần hiểu

Trong kiểm thử Spring Security, `MockMvc` giúp gửi yêu cầu HTTP qua ứng dụng Servlet mà không cần khởi động một máy chủ HTTP bên ngoài. Thư viện `spring-security-test` cung cấp `SecurityMockMvcRequestPostProcessors.jwt()` để tạo nhanh danh tính được xác thực bằng JWT giả. Cách này rất tiện để kiểm tra các quy tắc phân quyền, ví dụ người có quyền `SCOPE_reports:read` được phép vào `GET /api/reports`.

Nhưng một kết quả `200 OK` khi dùng `with(jwt())` **không chứng minh** rằng ứng dụng đã xác minh:

- Chữ ký của JWS/JWT và khóa ký có đáng tin hay không.
- Thuật toán ký được cho phép hay không, bao gồm việc từ chối `alg: none`.
- Thời điểm hết hạn `exp` và thời điểm chưa có hiệu lực `nbf`.
- Nhà phát hành `iss`, đối tượng nhận `aud`, hoặc quy tắc claim riêng.
- Token đã bị thu hồi hay chưa, hoặc quy trình đăng xuất OAuth2/OIDC đã vô hiệu hóa token hay chưa.

Với module `SPRING_SECURITY_TESTING`, mục tiêu bài học là biết dùng **MockMvc để kiểm chứng phân quyền bằng JWT giả** và biết cách viết **kiểm thử xác thực Bearer token thật qua filter chain và JwtDecoder**. Hai loại test có giá trị khác nhau; không nên dùng bằng chứng của loại này để kết luận thay loại kia.

Sau bài này, người học có thể:

1. Giải thích sự khác nhau giữa `jwt()` và gửi header `Authorization: Bearer ...`.
2. Kiểm thử endpoint được cho phép hoặc bị từ chối với scope/authority giả.
3. Tạo JWS ký thật để kiểm tra chữ ký sai, token hết hạn và sai issuer.
4. Phân biệt `401 Unauthorized` do xác thực thất bại với `403 Forbidden` do thiếu quyền.
5. Nhận diện tình huống mock decoder hoặc tắt filter khiến test bảo mật cho kết quả sai lệch.

## 2. Hai đường đi trong Spring Security

**Đường đi JWT giả lập (Spring Security Test):** Khi gọi `mockMvc.perform(get(...).with(jwt()))`, request post-processor tạo `Jwt`/`JwtAuthenticationToken` giả lập rồi thiết lập `SecurityContext` thích hợp cho kiểm thử. Mã kiểm tra quyền vẫn có thể chạy, nhưng test không gửi chuỗi JWT ký số để `JwtDecoder` xác minh.

**Đường đi Bearer thật (OAuth2 Resource Server):** Khi gửi `Authorization: Bearer eyJ...` với filter chain được bật, `BearerTokenAuthenticationFilter` trích bearer token; `JwtAuthenticationProvider` dùng `JwtDecoder` để kiểm tra JWS và các token validator đã cấu hình. Chỉ sau khi token được chấp nhận, Spring Security mới tạo authentication và kiểm tra authorities.

~~~mermaid
flowchart TD
    A["MockMvc .with(jwt())"] --> B["Spring Security Test gắn JwtAuthenticationToken giả"]
    B --> C["SecurityContext / kiểm tra quyền"]
    D["HTTP Authorization: Bearer <JWS>"] --> E["BearerTokenAuthenticationFilter"]
    E --> F["JwtAuthenticationProvider → JwtDecoder"]
    F --> G{"Chữ ký và claim hợp lệ?"}
    G -- "Không" --> H["401 Unauthorized"]
    G -- "Có" --> C
    C --> I{"Có authority yêu cầu?"}
    I -- "Không" --> J["403 Forbidden"]
    I -- "Có" --> K["200 OK / controller"]
~~~

| Request | Chữ ký được kiểm tra? | `exp`/`nbf` được decoder kiểm tra? | Quy tắc phân quyền có thể chạy? |
| --- | --- | --- | --- |
| `get(...).with(jwt())` | Không | Không | Có |
| `get(...).with(jwt().authorities(...))` | Không | Không | Có, với authority giả |
| `get(...).header("Authorization", "Bearer " + signedJwt)` | Có, nếu filter và decoder thật được cấu hình | Có, theo validators đã bật | Có, sau khi token hợp lệ |
| `get(...).header("Authorization", "Bearer " + invalidJwt)` | Decoder thử xác thực và từ chối | Phụ thuộc token có đọc được đến bước validator | Không được vào controller khi xác thực thất bại |

**Nguyên tắc:** một test chỉ chứng minh hành vi của thành phần mà request thực sự đi qua. Có một đối tượng `Jwt` trong `SecurityContext` chưa có nghĩa decoder hoặc thư viện mật mã đã chạy.

## 3. Ứng dụng Servlet mẫu để kiểm thử

Giả sử ứng dụng có endpoint `GET /api/reports` chỉ cho phép authority `SCOPE_reports:read`. Một bộ dependency Spring Boot phù hợp:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Security filter chain:

~~~java
@Configuration
@EnableWebSecurity
class ApiSecurityConfig {
    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/reports")
                    .hasAuthority("SCOPE_reports:read")
                .anyRequest().authenticated())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()));
        return http.build();
    }
}
~~~

Controller:

~~~java
@RestController
class ReportsController {
    @GetMapping("/api/reports")
    String reports() {
        return "confidential-report";
    }
}
~~~

Các kiểu Java quan trọng là `HttpSecurity`, `SecurityFilterChain`, `HttpMethod`, `SessionCreationPolicy`, `Customizer` và các annotation Spring. Ứng dụng resource server JWT cần cấu hình một `JwtDecoder` phù hợp. Trong phần 6, chúng ta cung cấp decoder thật với khóa thử nghiệm để kiểm tra được đường đi Bearer mà không phụ thuộc Identity Provider bên ngoài.

Khi chạy với Spring Boot, dùng `@SpringBootTest` và `@AutoConfigureMockMvc` để tích hợp các filter bảo mật. Nếu tự tạo MockMvc qua `MockMvcBuilders.webAppContextSetup(...)`, cần áp dụng `springSecurity()`. Không dùng `@AutoConfigureMockMvc(addFilters = false)` trong test xác thực token.

## 4. Dùng `jwt()` đúng mục đích: kiểm tra quyền

`jwt()` tạo authentication giả rất nhanh. Có thể kiểm thử hai nhánh cho phép và từ chối:

~~~java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
@Import(LocalJwtTestConfig.class)
class MockJwtAuthorizationTests {
    @Autowired
    MockMvc mockMvc;

    @Test
    void validScopeAllowsAccess() throws Exception {
        mockMvc.perform(get("/api/reports")
                    .with(jwt().jwt(builder -> builder
                        .subject("learner")
                        .claim("scope", "reports:read"))))
               .andExpect(status().isOk())
               .andExpect(content().string("confidential-report"));
    }

    @Test
    void missingScopeIsForbidden() throws Exception {
        mockMvc.perform(get("/api/reports")
                    .with(jwt().jwt(builder -> builder
                        .subject("learner")
                        .claim("scope", "profile"))))
               .andExpect(status().isForbidden());
    }
}
~~~

Mặc định, `JwtGrantedAuthoritiesConverter` chuyển `scope: "reports:read"` thành authority `SCOPE_reports:read`. Với `scope: "profile"`, người dùng vẫn được **giả lập là đã xác thực** nhưng không được đọc báo cáo, vì vậy kỳ vọng `403` chứ không phải `401`.

Khi cần bỏ qua phép chuyển đổi scope và chủ động đặt authorities, có thể dùng:

~~~java
mockMvc.perform(get("/api/reports")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_reports:read"))))
       .andExpect(status().isOk());
~~~

Test này chỉ chứng minh luật phân quyền xử lý authority đã có. Nó **không chứng minh converter đã chuyển claims thành authorities đúng**, vì quyền đã được cung cấp trực tiếp. Để kiểm tra converter riêng, dùng test trực tiếp cho converter hoặc yêu cầu Bearer thực đi qua cơ chế chuyển đổi.

### 4.1. Phản ví dụ quan trọng: token giả đã hết hạn vẫn có thể nhận 200

~~~java
import java.time.Instant;
import org.springframework.security.oauth2.jwt.Jwt;

@Test
void expiredSyntheticJwtCanStillPassAuthorization() throws Exception {
    Instant now = Instant.now();

    Jwt syntheticJwt = Jwt.withTokenValue("not-a-real-signed-jws")
            .header("alg", "none")
            .subject("learner")
            .issuedAt(now.minusSeconds(1_200))
            .expiresAt(now.minusSeconds(600))
            .claim("scope", "reports:read")
            .build();

    mockMvc.perform(get("/api/reports")
                .with(jwt().jwt(syntheticJwt)))
           .andExpect(status().isOk());
}
~~~

Trong ví dụ này, token value thậm chí không phải JWS hợp lệ và `exp` cách hiện tại 10 phút. Test vẫn có thể nhận `200` vì `jwt()` đã tạo authentication giả mang scope phù hợp, không gọi decoder để kiểm tra hạn hoặc chữ ký.

Đây là **hành vi bình thường của công cụ giả lập**. Kết luận đúng là: luật phân quyền chấp nhận principal có scope `reports:read`. Kết luận sai là: hệ thống production cho phép token không có chữ ký hoặc đã hết hạn.

## 5. Phân biệt những lỗi liên quan đến JWT

| Điều kiện | Kết quả mặc định thường gặp trong API Bearer | Ý nghĩa |
| --- | --- | --- |
| Không gửi bearer token cho endpoint bảo vệ | `401 Unauthorized` | Chưa được xác thực |
| JWS ký bởi khóa không được tin cậy | `401 Unauthorized` | Xác minh chữ ký thất bại |
| JWT đã hết hạn hoặc chưa đến `nbf` | `401 Unauthorized` | Timestamp validator từ chối |
| JWT sai `iss` hoặc `aud` mà ứng dụng có kiểm tra | `401 Unauthorized` | Token validation thất bại |
| JWT hợp lệ nhưng thiếu scope/role | `403 Forbidden` | Đã xác thực nhưng không được cấp quyền |
| `with(jwt())` có scope phù hợp | Có thể `200 OK` | Đã giả lập authentication; chưa chứng minh token hợp lệ về mặt mật mã |

Các mã trên áp dụng cho cấu hình resource-server với entry point và access-denied handler chuẩn. Nếu dự án tùy biến response, phải dùng hợp đồng HTTP thực tế để quyết định assertion.

## 6. Cấu hình ký và xác minh token thật cho test

Để viết test không phụ thuộc dịch vụ ngoài, ta tạo token JWS ký bằng **HS256** với `NimbusJwtEncoder`, rồi giải mã bằng `NimbusJwtDecoder`. Cấu hình bên dưới **chỉ dùng trong ví dụ kiểm thử**. Trong hệ thống thực sử dụng RSA/ECDSA và JWK Set URI của Identity Provider, phải dùng decoder/khóa tin cậy tương ứng.

### 6.1. Decoder không bị mock

~~~java
import java.nio.charset.StandardCharsets;
import javax.crypto.SecretKey;
import javax.crypto.spec.SecretKeySpec;

import com.nimbusds.jose.jwk.source.ImmutableSecret;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.jose.jws.MacAlgorithm;
import org.springframework.security.oauth2.jwt.*;

@TestConfiguration(proxyBeanMethods = false)
class LocalJwtTestConfig {

    static final String ISSUER = "https://issuer.example.test";

    static final SecretKey TRUSTED_KEY = new SecretKeySpec(
            "0123456789abcdef0123456789abcdef"
                .getBytes(StandardCharsets.UTF_8),
            "HmacSHA256");

    static final SecretKey OTHER_KEY = new SecretKeySpec(
            "abcdef0123456789abcdef0123456789"
                .getBytes(StandardCharsets.UTF_8),
            "HmacSHA256");

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder = NimbusJwtDecoder
                .withSecretKey(TRUSTED_KEY)
                .macAlgorithm(MacAlgorithm.HS256)
                .build();

        decoder.setJwtValidator(
                JwtValidators.createDefaultWithIssuer(ISSUER));
        return decoder;
    }

    @Bean
    JwtEncoder jwtEncoder() {
        return new NimbusJwtEncoder(new ImmutableSecret<>(TRUSTED_KEY));
    }
}
~~~

`TRUSTED_KEY` và `OTHER_KEY` là khóa công khai trong tài liệu bài tập, tuyệt đối không dùng làm khóa sản xuất. `JwtDecoder` ở đây chạy thật: xác minh chữ ký bằng khóa tin cậy và kiểm tra validator timestamp/issuer. `JwtValidators.createDefaultWithIssuer(...)` bao gồm bộ kiểm tra timestamp mặc định cùng validator issuer.

Lưu ý: nhiều ứng dụng đã có bean `JwtDecoder`. Trong trường hợp đó, test phải thay thế bean bằng cơ chế test configuration của dự án, tránh tạo bean xung đột. **Không mock `JwtDecoder.decode(...)` trả về một `Jwt` có sẵn** nếu mục tiêu là kiểm tra chữ ký, vì khi ấy bạn lại bỏ qua bước xác minh mật mã.

### 6.2. Hàm tạo JWS ký thật

~~~java
import java.time.Instant;
import org.springframework.security.oauth2.jose.jws.JwsHeader;
import org.springframework.security.oauth2.jose.jws.MacAlgorithm;
import org.springframework.security.oauth2.jwt.*;

static String sign(
        JwtEncoder encoder,
        String issuer,
        Instant issuedAt,
        Instant expiresAt,
        String scope) {

    JwtClaimsSet claims = JwtClaimsSet.builder()
            .issuer(issuer)
            .subject("learner")
            .issuedAt(issuedAt)
            .expiresAt(expiresAt)
            .claim("scope", scope)
            .build();

    return encoder.encode(JwtEncoderParameters.from(
            JwsHeader.with(MacAlgorithm.HS256).build(),
            claims)).getTokenValue();
}
~~~

`sign(...)` là helper đặt trong lớp test tích hợp ở mục 7. Để xác minh JWS, gửi **giá trị chuỗi token vừa ký** vào `Authorization: Bearer ...`. Đừng thêm `with(jwt())` trong cùng request: điều đó khiến kết quả không còn phản ánh rõ đường xác thực bearer cần kiểm thử.

## 7. Ca tích hợp: xác nhận chữ ký, hạn token và quyền

Các test dưới đây sử dụng ứng dụng `/api/reports` ở mục 3, `LocalJwtTestConfig` ở mục 6.1 và hàm `sign(...)` ở mục 6.2. Bổ sung hàm `sign` vào lớp test:

~~~java
import java.time.Instant;
import com.nimbusds.jose.jwk.source.ImmutableSecret;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpHeaders;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.NimbusJwtEncoder;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
@Import(LocalJwtTestConfig.class)
class BearerJwtVerificationTests {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    JwtEncoder encoder;

    // Đặt hàm static sign(...) từ mục 6.2 trong lớp này.

    @Test
    void validSignedTokenIsAccepted() throws Exception {
        Instant now = Instant.now();
        String token = sign(encoder,
                LocalJwtTestConfig.ISSUER,
                now.minusSeconds(60),
                now.plusSeconds(900),
                "reports:read");

        mockMvc.perform(get("/api/reports")
                    .header(HttpHeaders.AUTHORIZATION, "Bearer " + token))
               .andExpect(status().isOk())
               .andExpect(content().string("confidential-report"));
    }

    @Test
    void tokenSignedByAnotherKeyIsRejected() throws Exception {
        JwtEncoder untrusted = new NimbusJwtEncoder(
                new ImmutableSecret<>(LocalJwtTestConfig.OTHER_KEY));
        Instant now = Instant.now();
        String token = sign(untrusted,
                LocalJwtTestConfig.ISSUER,
                now.minusSeconds(60),
                now.plusSeconds(900),
                "reports:read");

        mockMvc.perform(get("/api/reports")
                    .header(HttpHeaders.AUTHORIZATION, "Bearer " + token))
               .andExpect(status().isUnauthorized());
    }

    @Test
    void expiredTokenIsRejected() throws Exception {
        Instant now = Instant.now();
        String token = sign(encoder,
                LocalJwtTestConfig.ISSUER,
                now.minusSeconds(1_200),
                now.minusSeconds(600),
                "reports:read");

        mockMvc.perform(get("/api/reports")
                    .header(HttpHeaders.AUTHORIZATION, "Bearer " + token))
               .andExpect(status().isUnauthorized());
    }

    @Test
    void wrongIssuerIsRejected() throws Exception {
        Instant now = Instant.now();
        String token = sign(encoder,
                "https://different-issuer.example.test",
                now.minusSeconds(60),
                now.plusSeconds(900),
                "reports:read");

        mockMvc.perform(get("/api/reports")
                    .header(HttpHeaders.AUTHORIZATION, "Bearer " + token))
               .andExpect(status().isUnauthorized());
    }

    @Test
    void validTokenWithoutScopeIsForbidden() throws Exception {
        Instant now = Instant.now();
        String token = sign(encoder,
                LocalJwtTestConfig.ISSUER,
                now.minusSeconds(60),
                now.plusSeconds(900),
                "profile");

        mockMvc.perform(get("/api/reports")
                    .header(HttpHeaders.AUTHORIZATION, "Bearer " + token))
               .andExpect(status().isForbidden());
    }

    @Test
    void noBearerHeaderIsUnauthorized() throws Exception {
        mockMvc.perform(get("/api/reports"))
               .andExpect(status().isUnauthorized());
    }
}
~~~

Những ca trên tạo **JWS có cấu trúc hợp lệ** để thử chữ ký sai. Gửi chuỗi `"Bearer garbage"` và nhận `401` mới chỉ chứng minh decoder từ chối một token không đọc được; chưa đủ để chứng minh đã thực thi phép xác minh chữ ký. Token ký bằng `OTHER_KEY` vượt qua bước parsing nhưng phải bị từ chối bởi decoder tin cậy `TRUSTED_KEY`.

**Kiểm thử dương tính là bắt buộc:** nếu chỉ có các ca nhận `401`, có thể toàn bộ cấu hình decoder đang từ chối mọi request. Ca token được ký đúng trả `200` chứng minh ít nhất một luồng xác thực hợp lệ hoạt động; sau đó các ca sai chữ ký, hết hạn và sai issuer mới có ý nghĩa rõ ràng.

## 8. Một số validator và tình huống nâng cao

### 8.1. Thời điểm `nbf` và dung sai đồng hồ

Spring Security dùng `JwtTimestampValidator` để kiểm tra thời gian hiệu lực. Validator có thể chấp nhận một độ lệch đồng hồ nhỏ (mặc định thường khoảng 60 giây); vì vậy test nên dùng mốc lệch nhiều phút. Ví dụ token chưa được phép sử dụng:

~~~java
Instant now = Instant.now();
JwtClaimsSet claims = JwtClaimsSet.builder()
        .issuer(LocalJwtTestConfig.ISSUER)
        .subject("learner")
        .issuedAt(now)
        .notBefore(now.plusSeconds(600))
        .expiresAt(now.plusSeconds(1_800))
        .claim("scope", "reports:read")
        .build();
~~~

Ký token bằng encoder thật, gửi Bearer header, mong đợi `401`. Không thử `nbf` bằng cách đặt claim cho `jwt()` rồi suy luận về validator; helper giả lập không thực hiện validation đó.

### 8.2. Kiểm tra audience khi ứng dụng yêu cầu

`JwtValidators.createDefaultWithIssuer(...)` không đồng nghĩa mọi audience đều được kiểm tra theo yêu cầu riêng của API. Ví dụ hệ thống chỉ tin token có `aud` chứa `reports-api` thì cần validator bổ sung:

~~~java
OAuth2TokenValidator<Jwt> audienceValidator =
        new JwtClaimValidator<List<String>>(
            JwtClaimNames.AUD,
            aud -> aud != null && aud.contains("reports-api"));

decoder.setJwtValidator(
        new DelegatingOAuth2TokenValidator<>(
            JwtValidators.createDefaultWithIssuer(ISSUER),
            audienceValidator));
~~~

Import các type `OAuth2TokenValidator`, `JwtClaimValidator`, `JwtClaimNames`, `DelegatingOAuth2TokenValidator` và `java.util.List`. Sau đó bổ sung ca `aud: ["another-api"]` bị từ chối và `aud: ["reports-api"]` được chấp nhận nếu các điều kiện khác hợp lệ. Token thiếu audience cũng phải bị từ chối theo chính sách này.

### 8.3. Kiểm tra thuật toán, `kid` và key rotation

Với JWK Set từ Identity Provider, decoder phải chọn khóa được tin cậy và chỉ cho phép các thuật toán mong đợi. Hệ thống nên kiểm chứng token ký bằng khóa lạ, token khai báo thuật toán không được cho phép, trường hợp `kid` không tìm thấy, và việc đổi khóa. Không suy luận một JWT `alg: none` là an toàn chỉ vì nó có đủ hai phần header/payload hoặc các claim nhìn có vẻ hợp lệ.

### 8.4. Logout và token revocation

JWT stateless còn hạn và được ký hợp lệ có thể tiếp tục được sử dụng sau logout, **trừ khi hệ thống có quy tắc thu hồi riêng**: denylist theo `jti`, thay đổi version, hủy session liên kết hoặc cơ chế kiểm tra tại authorization server. Decoder cơ bản không tự biết người dùng vừa logout. Với OAuth2/OIDC, logout local không mặc nhiên đồng nghĩa access token đã bị thu hồi ở Identity Provider. Hãy viết integration test cho chính cơ chế revocation hoặc OIDC logout khi có yêu cầu đó; `jwt()` giả lập không chứng minh được.

## 9. Phân biệt `401`, `403` và `200`

| Test | Đường đi | Kết quả | Điều có thể kết luận |
| --- | --- | --- | --- |
| `with(jwt())` có scope phù hợp | Authentication giả | `200` | Chính sách phân quyền cho phép scope đó |
| `with(jwt())` thiếu scope | Authentication giả | `403` | Chính sách từ chối người đã xác thực nhưng thiếu quyền |
| Bearer ký đúng, còn hạn, đúng issuer/scope | Decoder thật | `200` | Luồng xác thực bearer hợp lệ hoạt động |
| Bearer ký bằng khóa khác | Decoder thật | `401` | Chữ ký không được chấp nhận |
| Bearer có `exp` quá khứ | Decoder thật | `401` | Timestamp validation đang được áp dụng |
| Bearer sai issuer | Decoder thật | `401` | Validator issuer đang được áp dụng |
| Bearer hợp lệ nhưng thiếu scope | Decoder thật | `403` | Xác thực thành công, phân quyền thất bại |
| Không có Bearer token | Filter chain bảo vệ endpoint | `401` | Endpoint yêu cầu authentication |

Nên kiểm tra phản hồi HTTP, nội dung cần thiết và các điều kiện trước/sau request. Trường hợp bảo mật đặc thù có thể bổ sung khẳng định header `WWW-Authenticate` theo hợp đồng API. Tránh so khớp nguyên văn toàn bộ lỗi do decoder tạo vì thông báo có thể thay đổi theo phiên bản và cách cấu hình entry point.

## 10. Những lỗi thường gặp

| Cách làm | Vấn đề | Hướng xử lý |
| --- | --- | --- |
| Dùng `with(jwt())` rồi tuyên bố đã kiểm tra chữ ký | Không có quá trình decode Bearer token | Gửi token thật vào `Authorization` |
| Đặt `exp` quá khứ trên `Jwt` giả rồi chờ `401` | Fake authentication bỏ qua timestamp validation | Dùng JWS ký thật, exp đủ xa trong quá khứ |
| Dùng `jwt().authorities(...)` để kiểm thử claim converter | Authorities đã được đặt trực tiếp | Kiểm tra converter riêng hoặc JWT thật |
| Mock `JwtDecoder.decode(...)` và kiểm tra token sai chữ ký | Decoder giả có thể luôn trả `Jwt` hợp lệ | Dùng `NimbusJwtDecoder` thật và khóa test |
| Tắt Spring Security filters trong MockMvc | Không còn luồng resource server thực | Giữ filters được áp dụng, hoặc `apply(springSecurity())` |
| Chỉ có các test token sai trả `401` | Decoder có thể từ chối mọi token | Thêm ca token hợp lệ trả `200` |
| Dùng `@WithMockUser` để kiểm tra header Bearer | Principal được tạo giả trước khi phân tích token | Dùng request không có user mock |
| Kết luận `403` là token sai hoặc hết hạn | `403` thường là thiếu quyền | Kiểm tra riêng `401` và `403` |
| Test JWT có scope mà không xác minh filter chain được áp dụng | Đường đi có thể chỉ là controller thuần | Bảo đảm cấu hình security và ca không token nhận `401` |

Một số ứng dụng sử dụng `@WebMvcTest` cắt bớt context. Lúc đó phải nhập đúng security configuration và bean cần thiết. Nếu dùng `MockMvcBuilders.standaloneSetup(controller)` đơn thuần, mặc định không có đầy đủ filter chain, vì thế không phù hợp để chứng minh kết quả xác minh chữ ký.

## 11. So sánh với Reactive `WebTestClient`

Module `SPRING_SECURITY_TESTING` còn bao gồm ứng dụng Reactive. Ý nghĩa giới hạn của JWT giả lập giống nhau, nhưng API khác:

| Servlet (`MockMvc`) | Reactive (`WebTestClient`) | Mục tiêu |
| --- | --- | --- |
| `.with(jwt())` | `.mutateWith(mockJwt())` | Giả lập authentication để kiểm tra quyền |
| `.header(HttpHeaders.AUTHORIZATION, "Bearer " + token)` | `.headers(h -> h.setBearerAuth(token))` | Gửi bearer dạng chuỗi thật |
| `JwtDecoder` | `ReactiveJwtDecoder` | Xác minh chữ ký và token validation |
| `SecurityMockMvcRequestPostProcessors` | `SecurityMockServerConfigurers` | Hỗ trợ test từng công nghệ |

Ví dụ kiểm thử phân quyền Reactive:

~~~java
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockJwt;

client.mutateWith(mockJwt().jwt(jwt -> jwt
            .subject("learner")
            .claim("scope", "reports:read")))
      .get()
      .uri("/api/reports")
      .exchange()
      .expectStatus().isOk();
~~~

Ví dụ trên **không** chứng minh token qua `ReactiveJwtDecoder`. Muốn kiểm tra chữ ký và hạn token trên WebFlux, hãy bật hỗ trợ `springSecurity()` cho WebTestClient gắn mock server, cấu hình decoder thực, rồi gửi token ký thật bằng Bearer header. Với WebFlux cũng cần các ca token hợp lệ và token sai chữ ký/hết hạn tương ứng.

## 12. Bộ kiểm thử tối thiểu được đề xuất

Chia bộ test theo điều thực sự cần kiểm tra:

1. **Phân quyền endpoint:** nhanh và tập trung, dùng `jwt()` với nhiều scope/role; kiểm tra `200`/`403`.
2. **Tích hợp Resource Server:** dùng Bearer token ký thật; kiểm tra decoder, chuyển claims thành authorities và endpoint.
3. **Bảo mật token:** thêm sai chữ ký, sai issuer, hết hạn, `nbf` tương lai, audience/algorithm không hợp lệ theo cấu hình.
4. **Vận hành danh tính:** kiểm tra key rotation, JWK, revocation, OAuth2/OIDC logout nếu hệ thống có các chức năng ấy.

Một bộ hồi quy gọn cần tối thiểu: JWT giả có quyền (`200`), JWT giả thiếu quyền (`403`), JWT ký đúng còn hạn (`200`), JWS ký sai khóa (`401`), JWT hết hạn (`401`), JWT thật thiếu scope (`403`). Hai loại test bổ trợ nhau và phát hiện các lỗi khác nhau.

Khi đọc một test JWT, câu hỏi quan trọng nhất là: **request đang được gắn sẵn một `Authentication` giả hay đang gửi chuỗi bearer để Spring Security tự xác thực?** Nếu là trường hợp đầu, test không thể chứng minh chữ ký hay thời hạn token đã được kiểm tra, dù nó nhận `200 OK`.

## 13. Tài liệu tham khảo

- [Spring Security — Testing OAuth 2.0 Resource Server với MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html): cách dùng `jwt()` và JWT giả lập.
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): decoder, xác minh token và mapping scopes.
- [Spring Security — SecurityMockMvcRequestPostProcessors](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/test/web/servlet/request/SecurityMockMvcRequestPostProcessors.html): các request post-processors, gồm `jwt()`.
- [Spring Security — JwtValidators](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/JwtValidators.html): validators chuẩn cho JWT.
- [Spring Security — OAuth 2.0 Reactive Testing](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html): `mockJwt()` với WebTestClient.
