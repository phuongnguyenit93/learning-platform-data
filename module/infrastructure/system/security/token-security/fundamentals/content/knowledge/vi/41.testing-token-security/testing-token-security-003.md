# Test issuer mismatch

> **Chương:** Testing token security  
> **Phạm vi:** Kiểm thử mô hình tin cậy và xác thực access token trong OAuth 2.0/OIDC; phát hiện token có issuer không đúng với authorization server mà resource server đã cấu hình tin cậy.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích ý nghĩa bảo mật của claim `iss` và lý do resource server phải so khớp nó với issuer đã cấu hình.
2. Phân biệt issuer mismatch với lỗi chữ ký, sai audience, token hết hạn và thiếu scope.
3. Viết unit test cho issuer validator và test dùng JWT được ký thật để kiểm tra `JwtDecoder`.
4. Xác minh request mang token sai issuer bị từ chối trước khi chạy nghiệp vụ.
5. Thiết kế kiểm thử cho hệ thống có nhiều issuer mà không mở rộng miền tin cậy theo dữ liệu do token không đáng tin cung cấp.

## 1. Issuer là một phần của mô hình tin cậy

Trong JWT, claim `iss` (issuer) xác định bên phát hành token. Ví dụ:

~~~json
{
  "iss": "https://identity.example.com",
  "sub": "user-42",
  "aud": ["orders-api"],
  "exp": 1900000900,
  "scope": "orders.read"
}
~~~

Một resource server có thể được cấu hình chỉ tin token do `https://identity.example.com` phát hành. Khi nhận token, nó phải kiểm tra chữ ký theo khóa thuộc issuer đáng tin cậy và xác minh claim `iss` khớp với issuer đã cấu hình.

**Issuer mismatch** xảy ra khi giá trị `iss` trong token khác với issuer mà resource server chấp nhận. Ví dụ, API chỉ tin `https://identity.example.com` nhưng token khai báo `https://login.attacker.example`. Token phải bị từ chối ở bước xác thực, kể cả khi token chưa hết hạn và có scope phù hợp.

Có hai dữ kiện cần kiểm tra riêng:

- **Nguồn khóa ký đáng tin:** resource server lấy khóa xác minh từ cấu hình/JWKS thuộc issuer được tin cậy. Chữ ký chứng minh token được ký bởi khóa tương ứng.
- **Issuer claim khớp cấu hình:** claim `iss` trong token phải khớp issuer mong đợi. Chữ ký hợp lệ không thay thế phép kiểm tra này.

Claim `iss` chỉ là dữ liệu nằm trong token. Một kẻ tấn công có thể tự tạo payload ghi `iss` bằng bất kỳ chuỗi nào. Vì thế, không thể chỉ đọc claim rồi kết luận token đến từ issuer đó.

### Chuỗi xác thực access token

~~~mermaid
flowchart TD
    A["HTTP request có Bearer token"] --> B["Đọc header và xác định thuật toán / key id"]
    B --> C["Xác minh chữ ký bằng khóa của issuer được cấu hình tin cậy"]
    C -->|Sai chữ ký / khóa| X["401 Unauthorized"]
    C -->|Chữ ký hợp lệ| D["Kiểm tra iss khớp issuer mong đợi"]
    D -->|Issuer mismatch| X
    D -->|Khớp| E["Kiểm tra exp, nbf, aud và profile token"]
    E -->|Không hợp lệ| X
    E -->|Hợp lệ| F["Tạo Authentication"]
    F --> G["Kiểm tra scope, role, tenant và quyền tài nguyên"]
    G -->|Thiếu quyền| H["403 Forbidden"]
    G -->|Được phép| I["Thực hiện nghiệp vụ"]
~~~

Thứ tự thực thi cụ thể có thể phụ thuộc decoder và cấu hình, nhưng các điều kiện bảo mật phải được bảo đảm. Không để request chạy nghiệp vụ trước khi token vượt qua xác thực.

## 2. Phân biệt issuer mismatch với các lỗi token khác

Các lỗi sau đều có thể khiến token bị từ chối, nhưng nguyên nhân và mục tiêu kiểm thử khác nhau:

| Trường hợp | Điều kiện sai | Ý nghĩa |
| --- | --- | --- |
| Issuer mismatch | `iss` không khớp issuer được cấu hình | Token không thuộc miền issuer mà API chấp nhận |
| Signature invalid | Chữ ký không xác minh được bằng khóa tin cậy | Token bị sửa hoặc được ký bằng khóa không được tin |
| Unknown signing key | `kid` không ánh xạ được tới khóa hợp lệ | Không tìm thấy khóa tương ứng; có thể liên quan xoay vòng khóa hoặc token lạ |
| Audience mismatch | `aud` không chứa định danh API | Token được phát hành cho resource server khác |
| Expired token | `exp` đã qua | Token hết thời hạn |
| Not-before violation | Thời điểm hiện tại trước `nbf` | Token chưa được phép sử dụng |
| Invalid algorithm/profile | Thuật toán hoặc định dạng không nằm trong chính sách | Token không tuân thủ profile mà API chấp nhận |
| Missing scope | Token xác thực hợp lệ nhưng thiếu quyền thao tác | Người gọi không được phép thực hiện hành động |

Không gộp tất cả thành một test tên “invalid token”. Nếu test issuer mismatch vô tình thất bại vì chữ ký sai, test đó chưa chứng minh issuer validator hoạt động.

**Mẹo cô lập lỗi:** tạo một token có chữ ký hợp lệ bằng khóa kiểm thử mà decoder tin cậy, đặt `iss` thành issuer khác rồi xác nhận decoder từ chối do validation. Cách này cô lập phép so khớp issuer. Một test riêng dùng khóa khác để kiểm tra xác minh chữ ký.

Trong hệ thống thật, issuer khác thường cũng có JWKS/key riêng. Resource server không được lấy khóa từ issuer lạ chỉ vì token tự khai báo `iss` đó.

## 3. Cấu hình issuer validation trong Spring Security

Nếu dùng Spring Boot Resource Server, có thể cấu hình issuer URI:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.com
~~~

Với cấu hình Resource Server tiêu chuẩn, Spring Security dùng issuer để khám phá metadata và khóa xác minh theo cơ chế tương ứng, đồng thời cài đặt validation cho issuer và thời hạn token. Trong hệ thống thực tế, endpoint metadata/JWKS phải đến từ hạ tầng identity provider mà tổ chức đã xác minh và cấu hình tin cậy.

Nếu tự tạo `JwtDecoder`, cần gắn validator issuer rõ ràng. Ví dụ:

~~~java
@Bean
JwtDecoder jwtDecoder(RSAPublicKey trustedPublicKey) {
    NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withPublicKey(trustedPublicKey)
            .build();

    decoder.setJwtValidator(
            JwtValidators.createDefaultWithIssuer(
                    "https://identity.example.com"
            )
    );

    return decoder;
}
~~~

`JwtValidators.createDefaultWithIssuer` kết hợp kiểm tra thời gian token với kiểm tra issuer. Nếu ứng dụng dùng validator tùy chỉnh, phải giữ các kiểm tra mặc định cần thiết thay vì vô tình thay thế chúng bằng một validator chỉ kiểm tra một claim.

Issuer cần được cấu hình theo đúng hợp đồng của authorization server. Theo quy tắc so sánh issuer của JWT, giá trị là chuỗi có phân biệt chữ hoa/chữ thường. Không tự ý chuẩn hóa URI trong lúc kiểm tra. Các chuỗi sau phải được coi là khác nhau nếu cấu hình/issuer phát hành không quy định chúng tương đương:

~~~text
https://identity.example.com
https://identity.example.com/
http://identity.example.com
https://identity.example.com/tenant-a
~~~

Không bỏ dấu slash cuối, đổi HTTP thành HTTPS, đổi chữ hoa/chữ thường hay thay path để “sửa” claim. Cấu hình issuer phải khớp chính xác với giá trị mà identity provider công bố và phát hành.

### Kiểm tra audience độc lập

Issuer trả lời câu hỏi “ai phát hành token?”. Audience (`aud`) trả lời “token được phát hành cho resource server nào?”. API orders có thể yêu cầu `aud` chứa `orders-api`.

Một token có issuer hợp lệ nhưng chỉ dành cho `billing-api` vẫn phải bị từ chối tại orders API. Ngược lại, audience đúng cũng không bù được issuer sai. Nên có test riêng cho từng điều kiện để kết quả test chỉ ra chính xác ranh giới tin cậy nào đang được bảo vệ.

## 4. Viết test với JWT được ký thật

Một test chỉ dựng đối tượng `Jwt` bằng builder hoặc dùng `jwt()` của Spring Security Test có thể hữu ích khi kiểm tra authorization ở tầng controller. Tuy nhiên, các cách đó thường bỏ qua bước decode token và xác minh chữ ký/issuer trong Resource Server filter chain.

Để kiểm thử issuer validation, hãy tạo JWT có chữ ký bằng khóa RSA kiểm thử và đưa chuỗi compact token trực tiếp vào `JwtDecoder` đang cấu hình. Ví dụ dưới đây dùng Nimbus encoder để ký token trong bộ nhớ; không cần gọi identity provider bên ngoài.

Các dependency kiểm thử thường dùng:

~~~gradle
testImplementation("org.springframework.boot:spring-boot-starter-test")
testImplementation("org.springframework.security:spring-security-test")
~~~

Ví dụ JUnit 5, AssertJ và Spring Security OAuth2 JOSE:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

import com.nimbusds.jose.JOSEException;
import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jose.jwk.gen.RSAKeyGenerator;
import com.nimbusds.jose.jwk.source.ImmutableJWKSet;
import com.nimbusds.jose.jwk.source.JWKSource;
import com.nimbusds.jose.proc.SecurityContext;

import org.junit.jupiter.api.Test;

import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtClaimsSet;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.JwtEncoderParameters;
import org.springframework.security.oauth2.jwt.JwtException;
import org.springframework.security.oauth2.jwt.JwtValidationException;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.JwsHeader;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.oauth2.jwt.NimbusJwtEncoder;

class IssuerMismatchTest {

    private static final String TRUSTED_ISSUER =
            "https://identity.example.test";

    private static final String OTHER_ISSUER =
            "https://untrusted.example.test";

    private static final String AUDIENCE = "orders-api";

    @Test
    void acceptsTokenFromConfiguredIssuer() throws Exception {
        RSAKey trustedKey = newTestKey();
        JwtDecoder decoder = decoderFor(trustedKey);

        String token = signedToken(trustedKey, TRUSTED_ISSUER);
        Jwt jwt = decoder.decode(token);

        assertThat(jwt.getClaimAsString("iss"))
                .isEqualTo(TRUSTED_ISSUER);
        assertThat(jwt.getAudience()).contains(AUDIENCE);
    }

    @Test
    void rejectsTokenWithDifferentIssuer() throws Exception {
        RSAKey trustedKey = newTestKey();
        JwtDecoder decoder = decoderFor(trustedKey);

        // Cùng khóa tin cậy để cô lập lỗi issuer claim.
        // Chữ ký hợp lệ nhưng iss không khớp cấu hình.
        String token = signedToken(trustedKey, OTHER_ISSUER);

        assertThatThrownBy(() -> decoder.decode(token))
                .isInstanceOf(JwtValidationException.class);
    }

    @Test
    void rejectsTokenSignedByUntrustedKey() throws Exception {
        RSAKey trustedKey = newTestKey();
        RSAKey attackerKey = newTestKey();
        JwtDecoder decoder = decoderFor(trustedKey);

        // Issuer đúng nhưng chữ ký được tạo bằng khóa khác.
        String token = signedToken(attackerKey, TRUSTED_ISSUER);

        assertThatThrownBy(() -> decoder.decode(token))
                .isInstanceOf(JwtException.class);
    }

    private static JwtDecoder decoderFor(RSAKey trustedKey)
            throws JOSEException {
        NimbusJwtDecoder decoder = NimbusJwtDecoder
                .withPublicKey(trustedKey.toRSAPublicKey())
                .signatureAlgorithm(SignatureAlgorithm.RS256)
                .build();

        decoder.setJwtValidator(
                JwtValidators.createDefaultWithIssuer(TRUSTED_ISSUER)
        );

        return decoder;
    }

    private static String signedToken(RSAKey signingKey, String issuer)
            throws JOSEException {
        JWKSource<SecurityContext> jwkSource =
                new ImmutableJWKSet<>(new JWKSet(signingKey));

        JwtEncoder encoder = new NimbusJwtEncoder(jwkSource);
        Instant now = Instant.now();

        JwtClaimsSet claims = JwtClaimsSet.builder()
                .issuer(issuer)
                .subject("user-42")
                .audience(List.of(AUDIENCE))
                .issuedAt(now.minusSeconds(5))
                .expiresAt(now.plusSeconds(300))
                .claim("scope", "orders.read")
                .build();

        JwsHeader header = JwsHeader
                .with(SignatureAlgorithm.RS256)
                .keyId(signingKey.getKeyID())
                .build();

        return encoder.encode(
                JwtEncoderParameters.from(header, claims)
        ).getTokenValue();
    }

    private static RSAKey newTestKey() throws JOSEException {
        return new RSAKeyGenerator(2048)
                .keyID(UUID.randomUUID().toString())
                .generate();
    }
}
~~~

Hai test âm tính chứng minh hai lớp khác nhau:

- `rejectsTokenWithDifferentIssuer`: chữ ký có thể xác minh, nhưng claim `iss` không khớp issuer đã cấu hình. Decoder phải ném `JwtValidationException`.
- `rejectsTokenSignedByUntrustedKey`: claim issuer đúng nhưng chữ ký không được tạo bằng khóa tin cậy. Decoder phải từ chối token.

Test dương tính rất quan trọng. Nếu decoder từ chối mọi token, hai test âm tính vẫn xanh nhưng hệ thống không sử dụng được. Test dương tính chứng minh token có issuer đúng, chữ ký đúng và thời hạn hợp lệ được chấp nhận.

Đây là ví dụ test ở tầng decoder. Nó không kiểm tra việc Spring Security gắn decoder vào HTTP filter chain; phần đó cần một test tích hợp riêng.

## 5. Kiểm thử qua HTTP Resource Server

Sau khi đã có test decoder, nên có ít nhất một test tích hợp để xác nhận request thực tế mang Bearer token sai issuer nhận HTTP 401 và không gọi service nghiệp vụ.

Ví dụ cấu trúc kiểm thử với MockMvc (các bean và endpoint phụ thuộc ứng dụng):

~~~java
@Test
void requestWithIssuerMismatchReturns401() throws Exception {
    String token = signedToken(testSigningKey, OTHER_ISSUER);

    mockMvc.perform(get("/api/orders")
            .header("Authorization", "Bearer " + token))
        .andExpect(status().isUnauthorized());

    verifyNoInteractions(orderService);
}
~~~

Điều kiện để test này có ý nghĩa:

- `mockMvc` phải chạy cùng Spring Security filter chain thật của ứng dụng.
- `JwtDecoder` trong context phải là decoder được cấu hình issuer validation và phải tin khóa kiểm thử tương ứng.
- `signedToken` phải trả về compact JWT có chữ ký thật.
- Không dùng `SecurityMockMvcRequestPostProcessors.jwt()` trong test này, vì helper đó tạo sẵn authentication và bỏ qua bước decode Bearer token.
- Service được mock để xác nhận request bị chặn trước khi nghiệp vụ được gọi.

Kết quả mong đợi là **401 Unauthorized** vì token không vượt qua xác thực. HTTP 403 thường dành cho trường hợp đã xác thực thành công nhưng thiếu quyền thực hiện hành động. Không trả 403 cho issuer mismatch vì điều đó có thể làm lộ rằng API đã chấp nhận danh tính/token ở một mức nào đó.

Response không cần tiết lộ chi tiết issuer nào được tin cậy. Log nội bộ có thể ghi mã lỗi như `invalid_issuer`, tên resource server và request correlation ID; tuyệt đối không ghi nguyên Bearer token hoặc refresh token.

## 6. Hệ thống có nhiều issuer

Một hệ thống có thể tích hợp nhiều identity provider, ví dụ issuer nội bộ và issuer của đối tác. Trong trường hợp này, “issuer hợp lệ” phải được xác định bằng **allow-list cấu hình trước**:

| Issuer được cấu hình | JWKS/metadata được tin cậy | Audience được phép |
| --- | --- | --- |
| `https://id.company.example` | Endpoint khóa do công ty quản lý | `orders-api` |
| `https://partner-id.example` | Endpoint khóa đã được phê duyệt của đối tác | `orders-api` |

Khi nhận token, hệ thống chọn cấu hình xác thực trong danh sách tin cậy rồi kiểm tra chữ ký, issuer, audience và chính sách tương ứng. Không được lấy claim `iss` chưa xác thực rồi tự động tải metadata/JWKS từ URL đó. Cách làm này có thể mở ra SSRF, làm rối miền tin cậy hoặc cho phép kẻ tấn công đưa khóa của mình vào quá trình xác thực.

Với Spring Security, có thể dùng cơ chế resolver cho nhiều issuer, nhưng resolver phải chỉ chấp nhận các issuer đã được phê duyệt và gắn từng issuer với cấu hình xác thực riêng. Không biến mọi URL có trong `iss` thành issuer được phép.

### Bộ test cho multi-issuer

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Token từ issuer A, chữ ký và audience hợp lệ | Chấp nhận theo policy A |
| Token từ issuer B đã allow-list, chữ ký và audience hợp lệ | Chấp nhận theo policy B |
| Token khai báo issuer C chưa allow-list | Từ chối |
| Token khai báo issuer A nhưng ký bằng khóa của B | Từ chối |
| Issuer A đúng nhưng audience chỉ dành cho API khác | Từ chối |
| Issuer B hợp lệ nhưng tenant claim không có quyền truy cập tenant được yêu cầu | Xác thực token thành công, phân quyền tenant từ chối |
| Issuer hợp lệ nhưng scope không đủ | Xác thực thành công, trả 403 cho thao tác bị cấm |

Issuer và tenant là hai chiều khác nhau. Một identity provider có thể phát hành token cho nhiều tenant; xác thực issuer thành công không chứng minh chủ thể có membership trong tenant đang truy cập. Hãy kiểm thử tenant boundary độc lập sau khi token đã được xác thực.

## 7. Kiểm thử opaque access token

Opaque token không chứa payload JWT để resource server tự xác minh `iss`. API thường gửi token đến introspection endpoint đã cấu hình để nhận trạng thái và thuộc tính token.

Các điểm kiểm thử gồm:

- Introspection endpoint phải thuộc authorization server đã được cấu hình tin cậy và được gọi qua kênh bảo mật.
- Nếu phản hồi có `active: false`, API từ chối token.
- Nếu hệ thống có nhiều issuer, phải biết token được introspect trong miền issuer nào; không chọn endpoint tùy ý dựa trên dữ liệu không tin cậy.
- RFC 7662 cho phép một số thuộc tính trong introspection response là tùy chọn. Không giả định mọi server đều trả claim `iss`; nếu ứng dụng cần issuer trong phản hồi, phải quy định rõ hợp đồng và kiểm tra nó.
- Token opaque có trạng thái, scope, audience và tenant phải được kiểm tra theo hợp đồng tương tự access token JWT.

Có thể mock introspection server trong test tích hợp để kiểm tra response active, issuer (nếu hợp đồng có), audience và scope. Không nên mock trực tiếp lớp authorization ở controller rồi kết luận introspection đã được kiểm thử.

## 8. Các lỗi khiến test issuer mismatch cho kết quả sai

**Chỉ kiểm tra chuỗi claim:** test gọi `jwt.getClaimAsString("iss")` rồi so sánh bằng AssertJ. Test này chỉ xác minh dữ liệu trong object; nó không chứng minh decoder từ chối token sai issuer.

**Dùng token không có chữ ký hợp lệ:** decoder có thể từ chối vì chữ ký trước khi chạy issuer validator. Test âm tính sẽ xanh vì lý do sai. Hãy dùng khóa tin cậy để cô lập issuer mismatch.

**Dùng mock authentication trong test HTTP:** helper `jwt()` của Spring Security Test tạo authentication sẵn, bỏ qua việc Resource Server xác minh Bearer token. Dùng test decoder hoặc gửi token ký thật qua filter chain.

**Chỉ có test âm tính:** cấu hình issuer sai hoặc decoder luôn từ chối mọi token cũng làm test âm tính pass. Luôn có test dương tính với issuer đúng.

**Dùng cùng một biến cho issuer và audience:** hai claim có mục đích khác nhau. Test cần thay đổi từng điều kiện độc lập để phát hiện lỗi validator.

**Tải JWKS theo issuer chưa xác thực:** test có thể vô tình gọi URL ngoài dự kiến hoặc dùng khóa của attacker. Fixture kiểm thử nên tạo key trong bộ nhớ hoặc dùng JWKS server cục bộ được cấu hình rõ.

**Bỏ qua thời gian token:** token test có `exp` đã qua hoặc `nbf` ở tương lai sẽ bị từ chối trước khi kiểm tra được issuer. Tạo token có thời hạn hợp lệ, và dùng clock cố định nếu bộ test cần kết quả thời gian ổn định.

**Chỉ kiểm tra JWT:** nếu ứng dụng chấp nhận cả opaque token, cần test introspection theo đúng cơ chế triển khai.

## 9. Ma trận kiểm thử đề xuất

Một bộ test issuer tối thiểu nên có các trường hợp sau:

| ID | Token / cấu hình | Kết quả mong đợi | Lớp cần kiểm tra |
| --- | --- | --- | --- |
| ISS-01 | Issuer đúng, chữ ký đúng, thời hạn hợp lệ | Decode thành công | JwtDecoder |
| ISS-02 | Issuer khác, ký bằng khóa kiểm thử được tin cậy | JwtValidationException | Issuer validator |
| ISS-03 | Issuer đúng, ký bằng khóa không tin cậy | Token exception | Signature verification |
| ISS-04 | Issuer đúng, audience sai | Token bị từ chối | Audience validator |
| ISS-05 | Issuer đúng, token hết hạn | Token bị từ chối | Timestamp validator |
| ISS-06 | Issuer đúng, token chưa đến `nbf` | Token bị từ chối | Timestamp validator |
| ISS-07 | Issuer có dấu slash cuối khác cấu hình | Từ chối nếu chuỗi không khớp | Issuer validator |
| ISS-08 | Issuer không nằm trong allow-list | Từ chối, không tải JWKS từ URL lạ | Multi-issuer resolver |
| ISS-09 | HTTP Bearer token sai issuer | 401, service không được gọi | Security filter chain |
| ISS-10 | Token issuer hợp lệ nhưng scope thiếu | 403 cho endpoint cần scope | Authorization |
| ISS-11 | Token issuer hợp lệ nhưng tenant không khớp | Từ chối theo tenant policy | Tenant authorization |
| ISS-12 | Opaque token inactive hoặc introspection không đáng tin | Từ chối | Introspection client |

Không nhất thiết mọi ca đều đặt trong cùng một lớp test. Chia test theo validator, decoder, filter chain và policy giúp biết chính xác tầng nào đang lỗi.

## 10. Bài tập thực hành

**Bối cảnh:** API `orders-api` chỉ tin issuer `https://id.company.test`. Một request gửi JWT có:

~~~json
{
  "iss": "https://partner.example.test",
  "sub": "alice",
  "aud": ["orders-api"],
  "exp": 1900000900,
  "scope": "orders.read"
}
~~~

Giả sử token có chữ ký hợp lệ bằng khóa kiểm thử mà decoder đang tin cậy, và thời hạn vẫn còn hiệu lực.

1. Vì sao API vẫn phải từ chối token này dù audience và scope phù hợp?
2. Thiết kế một test âm tính cô lập issuer validation và một test dương tính.
3. Nếu đổi token để `iss` đúng nhưng chữ ký được tạo bằng private key khác, lỗi nào được kiểm tra?
4. Nếu token có issuer hợp lệ nhưng tenant claim không khớp tenant trong route, request nên bị chặn ở tầng nào?
5. Vì sao test HTTP dùng `jwt()` không chứng minh Resource Server đã từ chối issuer mismatch?

**Gợi ý đáp án:**

1. Issuer không thuộc miền tin cậy của API; audience/scope không thay thế issuer validation.
2. Dùng cùng khóa RSA tin cậy cho hai token, chỉ đổi `iss`; token issuer đúng phải decode thành công, token issuer khác phải ném `JwtValidationException`.
3. Kiểm tra xác minh chữ ký, không phải issuer claim.
4. Sau xác thực token, lớp authorization tenant phải kiểm tra active tenant và quyền trên tài nguyên; không được coi issuer hợp lệ là quyền truy cập tenant.
5. Helper tạo authentication trực tiếp và bỏ qua decoder/filter xử lý Bearer token; cần gửi compact JWT ký thật qua filter chain.

## Ghi nhớ

- `iss` phải khớp chính xác issuer được resource server cấu hình tin cậy.
- Claim issuer là dữ liệu cần xác minh; bản thân claim không chứng minh nguồn phát hành.
- Chữ ký, issuer, audience, thời hạn và scope là những điều kiện riêng biệt; test riêng từng điều kiện.
- Dùng JWT ký thật để kiểm tra decoder và filter chain; mock authentication chỉ phù hợp với test authorization ở tầng cao hơn.
- Với nhiều issuer, chỉ chấp nhận danh sách đã phê duyệt và gắn đúng metadata/JWKS/audience cho từng issuer.
- Issuer hợp lệ không đồng nghĩa tenant hợp lệ hoặc chủ thể có quyền trên mọi tài nguyên.

### Tài liệu tham khảo

- [RFC 7519 — JSON Web Token (JWT), mục 4.1.1 Issuer](https://www.rfc-editor.org/rfc/rfc7519#section-4.1.1)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
