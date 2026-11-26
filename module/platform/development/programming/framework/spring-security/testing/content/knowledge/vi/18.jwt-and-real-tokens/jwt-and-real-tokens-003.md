# Kiểm thử JWT có chữ ký sai, khóa không phù hợp và thuật toán bị từ chối

Khi API dùng OAuth2 Resource Server với JWT, một request có header `Authorization: Bearer <token>` chỉ được coi là đã xác thực sau khi token vượt qua các bước kiểm tra của `JwtDecoder`. Dù payload có `sub`, `scope` hay `roles` trông hợp lệ, chữ ký sai hoặc thuật toán không được tin cậy phải khiến request bị từ chối.

Trong module **SPRING_SECURITY_TESTING**, ta kiểm chứng hành vi bảo vệ HTTP thực tế trên **Servlet/MockMvc** và **Reactive/WebTestClient**. Bài này tập trung vào ba nhóm lỗi: **chữ ký không xác minh được**, **dùng sai khóa xác minh**, và **thuật toán ký không thuộc danh sách được chấp nhận**. Các công cụ như `jwt()`, `mockJwt()` hoặc `@WithMockUser` vẫn có vai trò trong kiểm thử phân quyền, nhưng chúng không thực hiện phép xác minh chữ ký của một bearer token thật.

## 1. Chữ ký của JWT dùng để bảo vệ điều gì?

Một JWT dạng **JWS compact** thường gồm ba phần được nối bằng dấu chấm:

`BASE64URL(header).BASE64URL(payload).BASE64URL(signature)`

Ví dụ header:

~~~json
{
  "typ": "JWT",
  "alg": "RS256",
  "kid": "access-key-2026-01"
}
~~~

Payload có thể chứa các claim:

~~~json
{
  "iss": "https://issuer.example.test",
  "sub": "alice",
  "aud": "orders-api",
  "scope": "orders:read",
  "iat": 1790000000,
  "exp": 1890000000
}
~~~

*Các giá trị thời gian ở đây chỉ minh họa cấu trúc claim, không phải dữ liệu dùng trong bộ test bên dưới.*

Với JWS, thông điệp được ký là **hai phần đầu dưới dạng Base64URL, kèm dấu chấm phân tách**. Chữ ký xác nhận rằng nội dung ấy được tạo bằng khóa ký tương ứng với khóa xác minh được tin cậy. Việc đọc được header/payload bằng Base64URL **không đồng nghĩa** chữ ký đã hợp lệ; dữ liệu chưa được xác minh vẫn phải xem là không đáng tin.

Các thuật toán thường gặp:

| Nhóm | Ví dụ | Khóa ký | Khóa xác minh |
| --- | --- | --- | --- |
| HMAC (đối xứng) | `HS256` | Secret chung | Chính secret chung đó |
| RSA (bất đối xứng) | `RS256`, `RS512` | RSA private key | RSA public key tương ứng |
| RSA-PSS (bất đối xứng) | `PS256` | RSA private key | RSA public key, cơ chế PSS tương ứng |
| ECDSA (bất đối xứng) | `ES256` | EC private key | EC public key đúng đường cong |

**Khóa phù hợp** nghĩa là vừa đúng loại khóa/thuật toán, vừa đúng cặp khóa hoặc secret được bên phát hành được tin cậy sử dụng. Một RSA public key khác, dù có cùng độ dài, không xác minh được chữ ký do private key ban đầu tạo ra.

Không nên nhầm các điều kiện:

- **Chữ ký bị sửa:** một byte trong token bị thay đổi, nên xác minh thất bại.
- **Sai khóa:** chữ ký vẫn là chữ ký mật mã hợp lệ, nhưng được tạo bằng private key *khác* public key mà API tin cậy.
- **Không tìm được khóa theo `kid`:** trong hệ thống JWKS, decoder không tìm thấy khóa được phép tương ứng; `kid` là gợi ý chọn khóa, không phải bằng chứng tin cậy.
- **Thuật toán bị từ chối:** header yêu cầu `RS512`, `HS256` hoặc `none` trong khi API chỉ chấp nhận `RS256`. Dù khóa hợp lệ ở một thuật toán khác, token vẫn phải bị từ chối.

Với JWE (JWT được mã hóa), định dạng và quy trình giải mã khác JWS compact ba phần. Bài này kiểm thử **JWT được ký bằng JWS**, loại phổ biến khi Resource Server xác minh access token.

## 2. Quy trình xác thực JWT của Spring Security

Trên Servlet, `BearerTokenAuthenticationFilter` lấy bearer token từ request và chuyển tới `JwtAuthenticationProvider`. Provider dùng `JwtDecoder` để giải mã, xác minh chữ ký và thực thi các validator. Nếu thành công, Spring Security tạo `JwtAuthenticationToken` với authorities từ claim, sau đó mới quyết định quyền truy cập endpoint.

Trong WebFlux, chuỗi xử lý dùng các thành phần Reactive tương ứng như `AuthenticationWebFilter` và `ReactiveJwtDecoder`. Ý nghĩa kiểm tra vẫn là: token phải được xác minh trước khi request được chấp nhận là đã xác thực.

~~~mermaid
flowchart TD
    A["GET /api/me với Authorization: Bearer"] --> B{"Có bearer token?"}
    B -->|Không| C["401: chưa xác thực"]
    B -->|Có| D["JwtDecoder / ReactiveJwtDecoder"]
    D --> E{"Chữ ký, khóa, thuật toán và các validator hợp lệ?"}
    E -->|Không| F["401: invalid_token"]
    E -->|Có| G["Tạo Authentication từ JWT"]
    G --> H{"Đủ quyền endpoint?"}
    H -->|Không| I["403: access denied"]
    H -->|Có| J["Controller xử lý request"]
~~~

Trong cấu hình Bearer Resource Server thông thường, chữ ký sai, khóa không khớp hoặc thuật toán bị cấm trả **`401 Unauthorized`** và thường đi kèm `WWW-Authenticate: Bearer`. Token đã xác thực nhưng thiếu authority cho endpoint thường nhận **`403 Forbidden`**. Cấu hình riêng của ứng dụng có thể thay đổi chi tiết phản hồi; test nên xác nhận hợp đồng HTTP của chính ứng dụng.

Đừng đánh đồng lỗi chữ ký với các kiểm tra claim: `exp` hết hạn, `nbf` chưa có hiệu lực, `iss` không đúng hoặc `aud` không được chấp nhận có thể cũng dẫn tới `401`, nhưng nguyên nhân nằm ở validator. Bài test cần dùng các claim hợp lệ để cô lập lỗi chữ ký hoặc thuật toán.

## 3. Vì sao `jwt()` không thể dùng để kiểm tra chữ ký?

Spring Security Test cung cấp các cách giả lập JWT hữu ích để kiểm tra authorization:

~~~java
mockMvc.perform(get("/api/me")
        .with(jwt().jwt(jwt -> jwt
            .subject("alice")
            .claim("scope", "orders:read"))))
    .andExpect(status().isOk());
~~~

Ở đây `jwt()` của `SecurityMockMvcRequestPostProcessors` cài sẵn danh tính JWT phục vụ kiểm thử. Nó không gửi chuỗi JWS ký thật qua `Authorization` và không yêu cầu decoder xác minh chữ ký. Vì thế, test trên chỉ chứng minh controller và các quy tắc authorization hoạt động với một danh tính JWT đã được giả lập.

Tương tự, `mockJwt()` trong `SecurityMockServerConfigurers` gắn một authentication giả lập vào `WebTestClient` đã được cấu hình cho Spring Security. Nó không chứng minh hệ thống từ chối JWT sai chữ ký. `@WithMockUser` còn tạo một principal dạng người dùng, không phải kiểm thử quy trình xác minh bearer token.

Để kiểm tra ba trường hợp của bài này, hãy:

1. Tạo chuỗi JWT/JWS **ký thật** bằng một thư viện JOSE.
2. Cấu hình một `JwtDecoder` chỉ tin cậy **public key** và **thuật toán** xác định.
3. Gửi chuỗi token qua header `Authorization: Bearer ...`.
4. Xác minh request bị chặn ở HTTP khi chữ ký/khóa/thuật toán không hợp lệ.

Đây là kiểm thử tích hợp chuỗi lọc bảo mật. Nó không cần gọi nhà cung cấp danh tính thật hoặc chia sẻ private key sản xuất; cặp khóa thử nghiệm được tạo ngay trong test.

## 4. Chuẩn bị môi trường Servlet và decoder chỉ chấp nhận RS256

Với ứng dụng Spring Boot dùng Spring MVC, cần các starter Security, OAuth2 Resource Server và bộ test phù hợp. Ví dụ Gradle Kotlin DSL:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-security")
    implementation("org.springframework.boot:spring-boot-starter-oauth2-resource-server")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.security:spring-security-test")
}
~~~

Spring Security Resource Server hỗ trợ Nimbus JOSE + JWT trong stack JWT; lớp `SignedJWT` và `RSASSASigner` dưới đây dùng để **tạo token thử nghiệm**, còn `NimbusJwtDecoder` dùng để **xác minh token**.

Ví dụ tích hợp đầy đủ có thể đặt trong test source của ứng dụng Servlet. Nó dựng một ứng dụng Spring Boot tối thiểu riêng cho test, tạo một cặp RSA 2048-bit, cấu hình decoder chỉ chấp nhận `RS256` và bảo vệ hai endpoint:

- `GET /api/me`: chỉ cần một JWT xác thực thành công.
- `GET /api/write`: yêu cầu authority `SCOPE_orders:write`; token thử nghiệm chỉ có `scope = orders:read`.

~~~java
import com.nimbusds.jose.JOSEException;
import com.nimbusds.jose.JOSEObjectType;
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.JWSHeader;
import com.nimbusds.jose.crypto.MACSigner;
import com.nimbusds.jose.crypto.RSASSASigner;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.PlainJWT;
import com.nimbusds.jwt.SignedJWT;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpHeaders;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.NoSuchAlgorithmException;
import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;
import java.time.Instant;
import java.util.Base64;
import java.util.Date;
import java.util.Map;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest(classes = JwtSignatureMvcTest.TestApp.class)
@AutoConfigureMockMvc
class JwtSignatureMvcTest {

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @Import({TestSecurity.class, MeController.class, KeyFixture.class})
    static class TestApp { }

    @Configuration
    static class TestSecurity {
        @Bean
        SecurityFilterChain security(HttpSecurity http) throws Exception {
            return http
                .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/api/write")
                        .hasAuthority("SCOPE_orders:write")
                    .requestMatchers("/api/me").authenticated()
                    .anyRequest().denyAll())
                .oauth2ResourceServer(oauth2 ->
                    oauth2.jwt(Customizer.withDefaults()))
                .build();
        }
    }

    @RestController
    static class MeController {
        @GetMapping("/api/me")
        Map<String, String> me(JwtAuthenticationToken authentication) {
            return Map.of("subject", authentication.getToken().getSubject());
        }

        @GetMapping("/api/write")
        String write() {
            return "WRITE";
        }
    }

    @TestConfiguration
    static class KeyFixture {
        @Bean
        KeyPair acceptedKeyPair() throws NoSuchAlgorithmException {
            KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
            generator.initialize(2048);
            return generator.generateKeyPair();
        }

        @Bean
        JwtDecoder jwtDecoder(KeyPair acceptedKeyPair) {
            return NimbusJwtDecoder
                .withPublicKey((RSAPublicKey) acceptedKeyPair.getPublic())
                .signatureAlgorithm(SignatureAlgorithm.RS256)
                .build();
        }
    }

    @Autowired
    MockMvc mockMvc;

    @Autowired
    KeyPair acceptedKeyPair;

    // Tất cả test dùng claims hợp lệ để cô lập vấn đề chữ ký/thuật toán.
    private static JWTClaimsSet claims() {
        Instant now = Instant.now();
        return new JWTClaimsSet.Builder()
            .issuer("https://issuer.example.test")
            .subject("alice")
            .claim("scope", "orders:read")
            .issueTime(Date.from(now.minusSeconds(60)))
            .expirationTime(Date.from(now.plusSeconds(300)))
            .build();
    }

    private static String signRsa(
            RSAPrivateKey privateKey, JWSAlgorithm algorithm)
            throws JOSEException {
        SignedJWT jwt = new SignedJWT(
            new JWSHeader.Builder(algorithm)
                .type(JOSEObjectType.JWT)
                .build(),
            claims());
        jwt.sign(new RSASSASigner(privateKey));
        return jwt.serialize();
    }

    private static KeyPair newRsaKeyPair() throws NoSuchAlgorithmException {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        return generator.generateKeyPair();
    }

    private void expectInvalidBearer(String token) throws Exception {
        mockMvc.perform(get("/api/me")
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + token))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                HttpHeaders.WWW_AUTHENTICATE, containsString("Bearer")));
    }

    @Test
    void tokenWithCorrectRsaKeyAndRs256IsAccepted() throws Exception {
        String token = signRsa(
            (RSAPrivateKey) acceptedKeyPair.getPrivate(),
            JWSAlgorithm.RS256);

        mockMvc.perform(get("/api/me")
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + token))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.subject").value("alice"));
    }

    @Test
    void tamperedSignatureIsRejected() throws Exception {
        String original = signRsa(
            (RSAPrivateKey) acceptedKeyPair.getPrivate(),
            JWSAlgorithm.RS256);

        String[] parts = original.split("\\.");
        byte[] signature = Base64.getUrlDecoder().decode(parts[2]);
        signature[0] ^= 0x01; // Đổi đúng 1 bit trong phần signature.

        String tampered = parts[0] + "." + parts[1] + "." +
            Base64.getUrlEncoder().withoutPadding()
                .encodeToString(signature);

        expectInvalidBearer(tampered);
    }

    @Test
    void signingWithAnotherPrivateKeyIsRejected() throws Exception {
        KeyPair untrusted = newRsaKeyPair();
        String token = signRsa(
            (RSAPrivateKey) untrusted.getPrivate(),
            JWSAlgorithm.RS256);

        // Chữ ký RS256 hợp lệ với key khác, nhưng decoder chỉ tin
        // public key của acceptedKeyPair.
        expectInvalidBearer(token);
    }

    @Test
    void rs512IsRejectedWhenOnlyRs256IsTrusted() throws Exception {
        String token = signRsa(
            (RSAPrivateKey) acceptedKeyPair.getPrivate(),
            JWSAlgorithm.RS512);

        // Cùng RSA key nhưng thuật toán khác danh sách cho phép.
        expectInvalidBearer(token);
    }

    @Test
    void hs256CannotReplaceAnRs256Signature() throws Exception {
        byte[] hmacSecret = new byte[32]; // Secret dùng riêng trong test.
        SignedJWT token = new SignedJWT(
            new JWSHeader(JWSAlgorithm.HS256), claims());
        token.sign(new MACSigner(hmacSecret));

        expectInvalidBearer(token.serialize());
    }

    @Test
    void unsignedAlgNoneTokenIsRejected() throws Exception {
        String unsigned = new PlainJWT(claims()).serialize();
        expectInvalidBearer(unsigned);
    }

    @Test
    void validJwtWithoutRequiredScopeGets403() throws Exception {
        String token = signRsa(
            (RSAPrivateKey) acceptedKeyPair.getPrivate(),
            JWSAlgorithm.RS256);

        mockMvc.perform(get("/api/write")
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + token))
            .andExpect(status().isForbidden());
    }
}
~~~

Đây là **fixture ứng dụng Servlet riêng**; khi đưa vào dự án đã có cấu hình Security, hãy dùng hoặc điều chỉnh cấu hình thực tế để không có hai nguồn `SecurityFilterChain` xung đột. Các khóa RSA được tạo trong test và không được lưu thành secret của dự án. `Map.of` cần Java 9 trở lên, còn kiểm thử Spring Boot hiện đại thường dùng Java mới hơn.

### Vì sao từng ca tạo ra kết quả mong đợi?

| Ca thử | Thuật toán header | Khóa thực sự ký token | Khóa decoder tin cậy | Kết quả |
| --- | --- | --- | --- | --- |
| Đối chứng hợp lệ | `RS256` | Private key A | Public key A | `200` |
| Signature đổi 1 bit | `RS256` | Private key A, signature đã bị sửa | Public key A | `401` |
| Private key khác | `RS256` | Private key B | Public key A | `401` |
| Sai thuật toán | `RS512` | Private key A | Public key A, chỉ `RS256` | `401` |
| Thuật toán HMAC | `HS256` | HMAC secret | RSA public key, chỉ `RS256` | `401` |
| Token không ký | `none` | Không có chữ ký | RSA public key, chỉ `RS256` | `401` |
| Đủ xác thực nhưng thiếu scope | `RS256` | Private key A | Public key A | `403` |

Một số lỗi khác cũng có thể trả `401`. Test có **đối chứng dương `200`**, claims chưa hết hạn và cùng cấu hình decoder, nhờ đó những ca âm tính có ý nghĩa hơn so với chỉ gọi một endpoint và kiểm tra tất cả đều bị từ chối.

Với `RS512`, token được ký bằng *đúng* private key A. Nếu decoder vẫn chấp nhận token này dù cấu hình chỉ cho `RS256`, chính sách thuật toán sẽ bị phá vỡ. Ca thử đó đặc biệt hữu ích để bắt lỗi người viết đã cấu hình tập thuật toán quá rộng.

## 5. Khóa không phù hợp: phân biệt sai loại, sai cặp và sai nguồn

Ba kiểu lỗi khóa cần quan sát riêng:

**Sai cặp khóa RSA.** API tin cậy public key A, trong khi token được ký bằng private key B. Hai cặp khóa đều đúng định dạng RSA; chỉ một cặp tạo chữ ký phù hợp. Ca `signingWithAnotherPrivateKeyIsRejected` ở trên kiểm chứng trực tiếp tình huống này.

**Sai loại khóa hoặc thuật toán.** Token `HS256` cần secret HMAC; decoder được cấu hình cho public key RSA với `RS256` sẽ từ chối ngay. Không nên nhận một key từ token rồi tự thử mọi thuật toán để tìm cách xác minh thành công. Điều đó có thể tạo ra lỗi *algorithm confusion*, đặc biệt khi vô tình coi bytes của RSA public key như secret HMAC.

**Sai nguồn khóa.** Ứng dụng dùng issuer/JWKS có thể nhìn thấy nhiều `kid`. Việc có trường `kid` trong JOSE header **không biến khóa thành đáng tin**; decoder chỉ được lấy khóa qua một tập nguồn đã cấu hình, chẳng hạn JWKS endpoint HTTPS của issuer tin cậy. Không được tải tùy ý URL do token chỉ định hoặc tự động tin khóa nằm trong header.

Với decoder một RSA public key như ví dụ trên, `kid` **không phải điều kiện tra cứu khóa**. Vì vậy, việc đổi `kid` trong header ở kiểu decoder này không chứng minh được logic “không tìm thấy `kid`”. Muốn kiểm thử `kid` thật sự, phải dùng decoder với JWKS hoặc bộ chọn khóa theo `kid`.

### Kịch bản kiểm thử JWKS và luân chuyển khóa

Trong hệ thống thực, nhà phát hành có thể công bố nhiều public key dưới dạng JWKS:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "key-old",
      "use": "sig",
      "alg": "RS256",
      "n": "<RSA modulus Base64URL>",
      "e": "AQAB"
    },
    {
      "kty": "RSA",
      "kid": "key-new",
      "use": "sig",
      "alg": "RS256",
      "n": "<RSA modulus Base64URL>",
      "e": "AQAB"
    }
  ]
}
~~~

Các giá trị `n` ở đây là chỗ giữ chỗ, chưa phải một JWKS hợp lệ để chạy ứng dụng. Trong bài kiểm thử JWKS, hãy tạo cặp khóa thử nghiệm và dựng JWKS hợp lệ từ **public keys**, ví dụ qua một HTTP server giả lập chạy nội bộ. Những ca quan trọng gồm:

| Tình huống | Điều cần chứng minh |
| --- | --- |
| `kid=key-old`, ký đúng bằng private key cũ còn tin cậy | Token hợp lệ khi public key cũ còn trong JWKS |
| `kid=key-new`, ký đúng bằng private key mới | Token hợp lệ sau khi JWKS của test công bố khóa mới |
| `kid=unknown` | Không xác minh được token bằng khóa tin cậy; HTTP bị từ chối |
| `kid=key-old` nhưng token ký bằng private key khác | Không chỉ dựa vào `kid`; chữ ký không khớp vẫn bị từ chối |
| Khóa cũ đã bị xóa khỏi tập tin cậy | Token cũ bị từ chối khi decoder đã cập nhật dữ liệu khóa |
| JWKS trả lỗi hoặc chưa được cập nhật | Ứng dụng không được chấp nhận token chỉ vì không lấy được khóa |

Cần tính đến **cache JWKS**: thay đổi nội dung endpoint không nhất thiết làm decoder nhận khóa mới ngay. Khi kiểm thử key rotation, kiểm soát cache, thời gian cập nhật hoặc tạo decoder mới để có kết quả xác định; không dùng độ trễ mạng ngoài môi trường làm cơ chế đồng bộ test.

Nếu dùng `NimbusJwtDecoder.withJwkSetUri(...)`, hãy gắn URI tới JWKS thử nghiệm, cấu hình thuật toán được tin cậy và điều kiện issuer/audience theo chính sách Resource Server. Có thể dùng MockWebServer hoặc WireMock để phục vụ JWKS mà không phụ thuộc vào IdP sản xuất.

## 6. Các điểm cần bảo vệ khi cấu hình thuật toán

Trong JOSE, `alg` nằm ở header do bên gửi token kiểm soát. API có thể *đọc* header để biết token đang yêu cầu thuật toán nào, nhưng **không được tự động tin** thuật toán đó. Decoder phải quyết định trước những thuật toán nào được phép.

Các nguyên tắc thiết kế kiểm thử:

1. **Chỉ cho phép thuật toán đã phê duyệt.** Ví dụ API dự kiến `RS256` thì test phải từ chối `HS256`, `RS512` và `none`. Nếu nghiệp vụ cần nhiều thuật toán, liệt kê rõ chúng và test cả bộ đã được cho phép.
2. **Không suy quyền tin cậy từ `kid`, `jku` hoặc `jwk` do token gửi lên.** Những trường này không được biến thành cách chọn nguồn khóa không kiểm soát.
3. **Không trộn secret HMAC với RSA public key.** Một API vốn dùng chữ ký bất đối xứng không được vô tình chuyển sang xác minh HMAC bằng bytes của public key.
4. **Kiểm tra issuer, audience, thời gian và type của token theo yêu cầu hệ thống.** Chữ ký đúng chỉ chứng minh token được ký bằng khóa được chấp nhận; chưa đủ chứng minh token được cấp *cho API này*.
5. **Kiểm tra scope/authority sau khi xác thực thành công.** `401` là thất bại xác thực; `403` là bị từ chối quyền trong trường hợp đã có danh tính hợp lệ.

Trong Spring Security, `NimbusJwtDecoder` và `NimbusReactiveJwtDecoder` cho phép xây dựng decoder dựa trên public key hoặc JWKS và giới hạn thuật toán chữ ký; ví dụ `.signatureAlgorithm(SignatureAlgorithm.RS256)` thể hiện chính sách mong muốn. Với triển khai dùng nhiều thuật toán, hãy đọc kỹ ngữ nghĩa các phương thức thêm thuật toán của builder đang sử dụng, rồi xác minh bằng test âm tính tương ứng.

## 7. Reactive: kiểm thử bearer token ký thật bằng WebTestClient

Trong ứng dụng Spring WebFlux, giữ nguyên tư duy test nhưng cấu hình `SecurityWebFilterChain` và `ReactiveJwtDecoder`. Ví dụ cấu hình tối thiểu, giả sử đã có bean `KeyPair acceptedKeyPair` thử nghiệm tương tự phần Servlet:

~~~java
@Configuration
@EnableWebFluxSecurity
class ReactiveResourceServerSecurity {

    @Bean
    SecurityWebFilterChain webFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchange -> exchange
                .pathMatchers("/api/me").authenticated()
                .anyExchange().denyAll())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }

    @Bean
    ReactiveJwtDecoder reactiveJwtDecoder(KeyPair acceptedKeyPair) {
        return NimbusReactiveJwtDecoder
            .withPublicKey((RSAPublicKey) acceptedKeyPair.getPublic())
            .signatureAlgorithm(SignatureAlgorithm.RS256)
            .build();
    }
}

@RestController
class ReactiveMeController {

    @GetMapping("/api/me")
    Mono<Map<String, String>> me(
            @AuthenticationPrincipal Jwt jwt) {
        return Mono.just(Map.of("subject", jwt.getSubject()));
    }
}
~~~

Các import chính gồm `org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity`, `org.springframework.security.config.web.server.ServerHttpSecurity`, `org.springframework.security.web.server.SecurityWebFilterChain`, `org.springframework.security.oauth2.jwt.ReactiveJwtDecoder`, `org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder`, `org.springframework.security.core.annotation.AuthenticationPrincipal` và `reactor.core.publisher.Mono`.

Ví dụ kiểm thử gửi token thật tới ứng dụng Reactive chạy trên cổng ngẫu nhiên:

~~~java
@SpringBootTest(webEnvironment =
    SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class JwtSignatureWebFluxTest {

    @Autowired
    WebTestClient client;

    @Autowired
    KeyPair acceptedKeyPair;

    @Test
    void signedWithTrustedKeyIsAccepted() throws Exception {
        String validToken = signRsa(
            (RSAPrivateKey) acceptedKeyPair.getPrivate(),
            JWSAlgorithm.RS256);

        client.get().uri("/api/me")
            .headers(h -> h.setBearerAuth(validToken))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.subject").isEqualTo("alice");
    }

    @Test
    void signedWithUntrustedKeyIsRejected() throws Exception {
        KeyPair other = newRsaKeyPair();
        String invalidToken = signRsa(
            (RSAPrivateKey) other.getPrivate(),
            JWSAlgorithm.RS256);

        client.get().uri("/api/me")
            .headers(h -> h.setBearerAuth(invalidToken))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void unapprovedAlgorithmIsRejected() throws Exception {
        String invalidToken = signRsa(
            (RSAPrivateKey) acceptedKeyPair.getPrivate(),
            JWSAlgorithm.RS512);

        client.get().uri("/api/me")
            .headers(h -> h.setBearerAuth(invalidToken))
            .exchange()
            .expectStatus().isUnauthorized();
    }
}
~~~

Đoạn Reactive này sử dụng lại các helper `signRsa(...)` và `newRsaKeyPair()` của fixture Servlet ở mục 4; khi đặt thành file test độc lập, hãy chuyển chúng sang một lớp tiện ích trong `src/test`. Dự án Reactive cũng cần starter WebFlux, Resource Server và các dependency kiểm thử tương ứng. Chỉ chạy ví dụ này trong **ngữ cảnh WebFlux** có cấu hình Resource Server Reactive; không ghép đồng thời MVC và WebFlux vào cùng test context.

Khi `WebTestClient` gửi Bearer header thông thường, token đi qua decoder Reactive. Ngược lại, nếu bạn dùng `mutateWith(mockJwt())` trên client được gắn với Spring Security, test chỉ đặt một danh tính giả lập. Sự khác biệt giữa hai cách tương đương với `jwt()` và request Bearer thật trong MockMvc.

## 8. Chẩn đoán kết quả test và nguyên nhân ẩn bên dưới

Với mã `401`, client thường không biết cụ thể token bị từ chối do chữ ký hay do thiếu issuer. Điều này là hành vi tốt: ứng dụng tránh công khai cấu hình khóa hoặc lý do chi tiết không cần thiết. Trong test, ta có thể dùng dữ liệu fixture để biết chắc token đang vi phạm điều kiện nào.

| Dấu hiệu | Nguyên nhân cần điều tra | Cách kiểm chứng |
| --- | --- | --- |
| Token hợp lệ cũng bị `401` | Decoder dùng sai public key, thiếu claims hoặc validator khác | Chạy đối chứng dương với key A + RS256 + claims hợp lệ |
| Token ký bằng key B được `200` | Tập khóa tin cậy quá rộng, cấu hình decoder khác mong đợi hoặc filter bị bỏ qua | Kiểm tra decoder thực sự được inject và filter chain đang áp dụng |
| Token `RS512` được `200` dù chính sách chỉ có `RS256` | Thuật toán ngoài chính sách đang được cho phép | Kiểm tra danh sách thuật toán decoder và ca test âm tính |
| Token `HS256` được `200` ở API RSA-only | Có thể tồn tại lỗi cấu hình chấp nhận secret hoặc algorithm confusion | Kiểm tra cơ chế chọn khóa và thuật toán, không tin header token |
| Token sai chữ ký nhận `403` | Request có thể đã được xác thực bằng cơ chế khác, hoặc bị chặn trước bởi một filter khác | Cô lập Resource Server, xem SecurityContext và thứ tự filter |
| Mọi request nhận `200` dù token sai | Kiểm thử có thể đã bỏ qua security filter hoặc đang dùng `jwt()` mock | Dùng request Bearer thật và bảo đảm filter chain được áp dụng |
| Test JWKS lúc qua lúc không | Cache JWKS, key rotation hoặc phụ thuộc server ngoài | Dùng JWKS giả lập ổn định, chủ động kiểm soát cache |

Ở mã nguồn application, log chẩn đoán của Spring Security/Nimbus trong môi trường kiểm thử có thể giúp xác định decoder đang từ chối vì điều kiện nào. Không nên đưa raw token, private key, access token sản xuất hoặc toàn bộ claim nhạy cảm vào log. Chỉ kiểm tra thông tin cần thiết như `kid`, nhóm thuật toán, trạng thái xác minh và loại lỗi đã được xử lý.

**Không dùng exception message như một hợp đồng HTTP cố định.** Lỗi do thư viện JOSE/Nimbus có thể khác nhau giữa các phiên bản; cùng một lỗi chữ ký có thể được ánh xạ thành `invalid_token` ở tầng Resource Server. Các assert ổn định hơn thường là status `401`, header Bearer khi hợp đồng yêu cầu, và không có body thành công.

## 9. Bài thực hành và các ca kiểm thử cần hoàn thành

1. **Đối chứng dương:** tạo token `RS256` bằng private key A, cấu hình decoder với public key A và xác nhận `GET /api/me` trả `200` với `sub=alice`.
2. **Signature tampering:** sửa một byte signature của cùng token, giữ nguyên header/payload và kiểm tra `401`.
3. **Khóa không khớp:** ký `RS256` với private key B nhưng vẫn cấu hình decoder bằng public key A. Kiểm tra `401`.
4. **Thuật toán bị cấm:** ký `RS512` bằng đúng private key A và xác nhận decoder chỉ chấp nhận `RS256` vẫn từ chối. Thử thêm `HS256` và `none`.
5. **Đã xác thực nhưng thiếu quyền:** dùng token `RS256` hợp lệ chỉ có `orders:read` để gọi endpoint yêu cầu `orders:write` và xác nhận `403`.
6. **Phân biệt test mock:** viết test `jwt()` hoặc `mockJwt()` trả `200` trên endpoint cần xác thực, rồi giải thích vì sao kết quả này không chứng minh chữ ký của bearer token thật.
7. **JWKS tùy chọn:** phục vụ hai RSA public keys cùng `kid` khác nhau, kiểm tra token được ký đúng và token có `kid` lạ; mô phỏng rotate key và quan sát cache.
8. **So sánh Servlet và Reactive:** lặp ba ca cốt lõi (hợp lệ, ký bằng key B, dùng `RS512`) với `MockMvc` và `WebTestClient`, đảm bảo mỗi test đi qua security chain đúng stack.

Hoàn thành bài này, người học phải tự chứng minh được rằng **một payload JWT có vẻ hợp lệ không đủ tạo authentication**. Bộ lọc Resource Server chỉ cho phép request tiếp tục khi decoder tin cậy **chữ ký, khóa, thuật toán và các validator**; sau đó hệ thống mới dùng claims/authorities để quyết định quyền HTTP.
