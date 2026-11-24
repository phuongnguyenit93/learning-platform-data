# Xử lý key rotation qua JWKS

## Mục tiêu dự án

Bạn sẽ xây dựng một lab gồm **Authorization Server mô phỏng** và **Resource Server** để thực hành xoay khóa ký JWT qua JSON Web Key Set (JWKS). Dự án mô phỏng vòng đời khóa bình thường: tạo khóa mới, công bố public key, chuyển signer sang khóa mới, duy trì khóa cũ trong giai đoạn overlap rồi gỡ khóa cũ sau khi token liên quan hết hiệu lực.

Một hệ thống xác minh JWT phân tán có thể cache JWKS ở nhiều resource server. Nếu authorization server chuyển sang ký bằng khóa mới trước khi public key mới được công bố và có thời gian phân phối, request hợp lệ có thể bị từ chối. Nếu xóa khóa cũ quá sớm, token đã phát hành có thể bị từ chối không nhất quán giữa các API. Nếu giữ khóa cũ quá lâu, phạm vi tin cậy và rủi ro khi khóa bị lộ tăng lên.

Sau dự án, bạn có thể:

- Tạo cặp RSA signing key và định danh từng khóa bằng **kid**.
- Công bố JWKS chỉ chứa public key, trong khi private key được giữ riêng.
- Cấu hình resource server lấy JWKS và xác minh JWT theo issuer/audience.
- Thực hiện rotation theo giai đoạn publish, overlap, switch signer và retire.
- Kiểm tra cache, unknown kid, thời hạn token và hành vi khi JWKS lỗi.
- Phân biệt rotation định kỳ với xử lý khẩn cấp khi private key bị compromise.
- Ghi nhận sự kiện vận hành và thiết kế rollback không làm sống lại khóa đã bị lộ.

## 1. Bài toán và kiến trúc lab

Xây dựng hai ứng dụng:

- **issuer-lab:** phát hành access token JWT và cung cấp JWKS endpoint.
- **orders-api:** nhận Bearer access token, tải public key từ JWKS và bảo vệ endpoint đơn hàng.

Trong lab, khóa RSA được tạo trong bộ nhớ để dễ quan sát. Production phải dùng KMS/HSM hoặc hệ thống quản lý khóa tương đương; không lưu private key trong source code, container image, repository hoặc JWKS.

~~~mermaid
flowchart LR
    C["Client"] -->|"1. Xin access token"| I["Issuer Lab"]
    I -->|"2. JWT ký bằng private key K1/K2"| C
    C -->|"3. Bearer JWT"| API["Orders API"]
    API -->|"4. GET JWKS"| I
    I -->|"5. Public keys: K1/K2"| API
    API -->|"6. Verify signature + claims"| API
    API -->|"7. Protected response"| C
~~~

### Luồng xác minh

JWT header chứa thuật toán và **kid**. Resource server dùng kid để tìm public key tương ứng trong JWKS đã lấy từ issuer tin cậy. Sau khi xác minh chữ ký, API còn phải kiểm tra issuer, audience, thời hạn, loại token và quyền.

Ví dụ header:

~~~json
{
  "alg": "RS256",
  "kid": "orders-signing-2026-01",
  "typ": "JWT"
}
~~~

Ví dụ claims:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "user-42",
  "aud": ["orders-api"],
  "scope": "orders:read",
  "iat": 1893456000,
  "exp": 1893456300
}
~~~

Nếu triển khai JWT access token theo RFC 9068, dùng token type at+jwt và tuân thủ toàn bộ profile tương ứng. Ví dụ lab có thể dùng typ=JWT nếu chỉ minh họa JWT tổng quát; resource server production phải kiểm tra đúng profile access token đã thống nhất.

### Công nghệ gợi ý

- Java 17 hoặc phiên bản dự án hỗ trợ.
- Spring Boot và Spring Security OAuth2 Resource Server.
- Nimbus JOSE + JWT để tạo RSA JWK, ký JWT và xuất JWKS.
- JUnit 5 và WireMock cho integration test HTTP.
- Gradle hoặc Maven theo cấu trúc dự án.

Giữ các phiên bản Spring Security và Nimbus tương thích với dependency management hiện tại. Các API builder có thể khác nhẹ giữa các phiên bản; giữ nguyên nguyên tắc xác minh và test ngay trên phiên bản thực tế.

## 2. Quy tắc bảo mật trước khi bắt đầu

1. Chỉ cho phép thuật toán đã cấu hình, ví dụ RS256; không lấy thuật toán từ token rồi chấp nhận tùy ý.
2. Mỗi khóa có kid duy nhất trong phạm vi issuer và không tái sử dụng kid cho khóa khác.
3. JWKS chỉ công bố public key. Không có private RSA parameters như d, p, q, dp, dq, qi hoặc oth.
4. Resource server chỉ lấy JWKS từ issuer/URL được cấu hình tin cậy. Không tải khóa từ jku hoặc x5u do JWT tự khai báo.
5. Xác minh chính xác iss, aud, thời hạn và token profile; chữ ký hợp lệ không tự chứng minh token dành cho API hiện tại.
6. Private key phải có quyền truy cập tối thiểu, audit, backup/restore và quy trình rotation riêng.
7. Không ghi private key, access token hoặc refresh token vào log.
8. Nếu không thể xác minh chữ ký bằng khóa tin cậy, resource server fail closed.

## 3. Thiết kế vòng đời khóa

Dùng bốn trạng thái logic cho mỗi signing key:

| Trạng thái | Có trong JWKS? | Được ký token mới? | Mục đích |
| --- | --- | --- | --- |
| PREPARED | Chưa hoặc đang chờ publish | Không | Đã tạo khóa và kiểm tra trước khi sử dụng |
| ACTIVE_SIGNING | Có | Có | Khóa hiện tại dùng để ký token mới |
| VERIFY_ONLY | Có | Không | Khóa cũ còn cần để xác minh token đã phát hành |
| RETIRED | Không | Không | Khóa đã rời khỏi trust set sau khi hết nhu cầu xác minh |

Một khóa chỉ nên có một vai trò signer hiện tại tại một thời điểm. Khi chuyển signer, thay đổi phải nguyên tử trong key manager để không có request nào ký bằng private key K2 nhưng ghi kid của K1, hoặc ngược lại.

### Thứ tự rotation bình thường

~~~mermaid
stateDiagram-v2
    [*] --> K1_Signing
    K1_Signing --> K1_Overlap: Publish K2
    K1_Overlap --> K2_Signing: Switch signer to K2
    K2_Signing --> K2_Only: K1 tokens expired
    K2_Only --> Retired: Remove K1 from JWKS
~~~

| Giai đoạn | JWKS công bố | Khóa ký token mới | Token cần còn xác minh |
| --- | --- | --- | --- |
| Ban đầu | K1 | K1 | Token ký K1 |
| Publish overlap | K1 + K2 | K1 | Token ký K1 |
| Switch signer | K1 + K2 | K2 | Token K1 cũ và token K2 mới |
| Retire K1 | K2 | K2 | Token K2; token K1 đã hết hạn |
| Hoàn tất | K2 | K2 | Token mới ký K2 |

**Điểm mấu chốt:** công bố K2 trước khi dùng K2 để ký. Sau đó giữ K1 cho đến khi token cuối cùng ký bằng K1 đã hết hiệu lực theo thời gian và clock skew của hệ thống.

### Tính thời điểm gỡ K1

Không chỉ tính từ thời điểm switch signer. Cần tìm thời điểm hết hạn lớn nhất của mọi access token đã ký bằng K1:

~~~text
lastK1TokenExpiry = max(exp của token đã phát hành bằng K1)

removeK1After >=
    lastK1TokenExpiry
    + maximumClockSkew
    + operationalPropagationMargin
~~~

Nếu hệ thống bảo đảm TTL tối đa cho access token, có thể ước lượng bằng:

~~~text
switchTime
+ maximumAccessTokenLifetime
+ maximumClockSkew
+ propagationMargin
~~~

Công thức dựa trên switchTime chỉ đúng nếu không còn request nào ký bằng K1 sau thời điểm đó và TTL có giới hạn được thực thi. Với hệ thống có nhiều issuer instance hoặc queue phát hành token, cần xác minh tất cả signer đã chuyển sang K2.

JWKS cache cũng cần được tính đến. Resource server có thể tiếp tục giữ K1 trong cache sau khi K1 bị gỡ khỏi JWKS. Vì vậy, chỉ xóa K1 khỏi endpoint không đảm bảo mọi instance ngừng tin K1 ngay lập tức. Trong rotation bình thường, đợi token K1 hết hạn trước khi gỡ giúp tránh việc một instance refresh sớm từ chối token trong khi instance khác vẫn xác minh được.

## 4. Tạo RSA key và public JWK

Dùng Nimbus JOSE + JWT trong lab. Ví dụ tạo khóa RSA 2048 bit với kid riêng:

~~~java
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.jwk.KeyUse;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jose.jwk.gen.RSAKeyGenerator;

RSAKey createSigningKey(String kid) throws Exception {
    return new RSAKeyGenerator(2048)
        .keyID(kid)
        .keyUse(KeyUse.SIGNATURE)
        .algorithm(JWSAlgorithm.RS256)
        .generate();
}

RSAKey key1 = createSigningKey("orders-signing-2026-01");
RSAKey key2 = createSigningKey("orders-signing-2026-02");
~~~

RSAKey trong bộ nhớ của issuer chứa cả private và public parameters. Chỉ dùng toPublicJWK() khi công bố:

~~~java
import com.nimbusds.jose.jwk.JWKSet;
import java.util.List;

String jwksJson = new JWKSet(
    List.of(key1.toPublicJWK(), key2.toPublicJWK())
).toString();
~~~

Khi đang ở giai đoạn ban đầu, JWKS chỉ chứa K1. Khi chuẩn bị overlap, công bố K1 và K2. Không đưa private JWK JSON của key1 hoặc key2 ra endpoint vì có thể làm lộ private key.

### Kiểm tra JWKS trước khi publish

- Mỗi public JWK có kty=RSA, use=sig, alg=RS256 và kid đúng.
- Có các thành phần public như n, e.
- Không có d, p, q, dp, dq, qi, oth.
- Không có hai key dùng cùng kid.
- JWKS JSON parse được và chứa đúng số key dự kiến.
- Endpoint trả đúng Content-Type JSON và không cache quá lâu ngoài policy.

## 5. Dựng JWKS endpoint trong issuer-lab

Ví dụ Spring controller trả public JWKS:

~~~java
import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.RSAKey;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.Map;

@RestController
class JwksController {

    private final KeyRing keyRing;

    JwksController(KeyRing keyRing) {
        this.keyRing = keyRing;
    }

    @GetMapping(
        value = "/.well-known/jwks.json",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    Map<String, Object> jwks() {
        List<RSAKey> publicKeys = keyRing.keysPublishedForVerification()
            .stream()
            .map(RSAKey::toPublicJWK)
            .toList();

        return new JWKSet(publicKeys).toJSONObject();
    }
}
~~~

KeyRing là thành phần quản lý trạng thái khóa của lab. Phương thức keysPublishedForVerification() chỉ trả các khóa được phép công bố, ví dụ K1 khi ban đầu, K1+K2 trong overlap và K2 sau khi retire K1.

Endpoint JWKS không cần xác thực người dùng vì resource server cần đọc public key; tuy nhiên cần giới hạn rate, dùng HTTPS trong production, có cache header phù hợp và chỉ trả đúng public key đã duyệt.

Ví dụ cache header cho JWKS:

~~~http
Cache-Control: public, max-age=300
Content-Type: application/json
~~~

max-age ở ví dụ chỉ minh họa. Chọn TTL theo tần suất rotation, yêu cầu propagation, khả năng refresh khi unknown kid và tải của issuer. TTL quá dài làm chậm nhận khóa mới hoặc khóa bị gỡ; TTL quá ngắn tăng request đến issuer.

## 6. Ký access token bằng active key

Key manager phải trả về một cặp nhất quán gồm private key và kid của cùng một key record. Không đọc active key và active kid từ hai cấu hình độc lập có thể thay đổi giữa chừng.

Ví dụ dùng Nimbus:

~~~java
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.JWSHeader;
import com.nimbusds.jose.crypto.RSASSASigner;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.SignedJWT;

import java.time.Instant;
import java.util.Date;

String issueAccessToken(RSAKey activeKey) throws Exception {
    Instant now = Instant.now();

    JWTClaimsSet claims = new JWTClaimsSet.Builder()
        .issuer("https://identity.example.test")
        .subject("user-42")
        .audience("orders-api")
        .issueTime(Date.from(now))
        .notBeforeTime(Date.from(now.minusSeconds(5)))
        .expirationTime(Date.from(now.plusSeconds(300)))
        .claim("scope", "orders:read")
        .build();

    JWSHeader header = new JWSHeader.Builder(JWSAlgorithm.RS256)
        .keyID(activeKey.getKeyID())
        .build();

    SignedJWT jwt = new SignedJWT(header, claims);
    jwt.sign(new RSASSASigner(activeKey));

    return jwt.serialize();
}
~~~

Ví dụ access token sống 5 phút để giới hạn thời gian sử dụng khi bị lộ. TTL production cần dựa trên threat model, yêu cầu trải nghiệm và khả năng revoke. Nếu dùng RFC 9068, cần thêm đúng token type và claims bắt buộc của profile.

Khi signer chuyển từ K1 sang K2, hàm phát hành phải lấy cả private key K2 và kid K2 từ cùng một snapshot/version của key manager. Token đã ký phải luôn mang kid của public key tương ứng.

## 7. Cấu hình orders-api xác minh từ JWKS

Resource server cần lấy JWKS URI từ trust configuration của issuer. Không xây URL từ claim chưa xác thực trong token.

Ví dụ Spring Security:

~~~java
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

NimbusJwtDecoder decoder =
    NimbusJwtDecoder.withJwkSetUri(
        "https://identity.example.test/.well-known/jwks.json"
    ).build();

OAuth2TokenValidator<Jwt> issuerAndTime =
    JwtValidators.createDefaultWithIssuer(
        "https://identity.example.test"
    );

OAuth2TokenValidator<Jwt> audience =
    new AudienceValidator("orders-api");

decoder.setJwtValidator(
    new DelegatingOAuth2TokenValidator<>(issuerAndTime, audience)
);
~~~

AudienceValidator là validator ứng dụng định nghĩa để kiểm tra aud chứa đúng orders-api. Giữ các validator mặc định về thời gian và issuer. Nếu dự án có validator riêng cho token type, tenant hoặc access-token profile, ghép chúng vào chuỗi validation thay vì thay thế bằng một validator đơn lẻ.

Một endpoint cần scope có thể dùng authority được map từ claim scope:

~~~java
@GetMapping("/api/orders")
@PreAuthorize("hasAuthority('SCOPE_orders:read')")
List<OrderDto> listOrders() {
    return orderService.listOrders();
}
~~~

Khi token có chữ ký hợp lệ nhưng audience là billing-api, API vẫn phải từ chối. Khi audience đúng nhưng thiếu orders:read, token qua authentication nhưng không đủ quyền cho endpoint.

## 8. Thực hành rotation theo từng giai đoạn

### Giai đoạn 0 — Baseline với K1

- Tạo K1 với kid=orders-signing-2026-01.
- Key manager đánh dấu K1 là ACTIVE_SIGNING.
- JWKS chỉ công bố public K1.
- Issuer phát hành token có header kid K1.
- Orders API lấy JWKS và xác minh token.

Kết quả mong đợi: token ký K1 được chấp nhận; token giả mạo hoặc sai issuer/audience bị từ chối.

### Giai đoạn 1 — Tạo và publish K2

- Tạo K2 với kid mới.
- K2 ở trạng thái PREPARED; chưa dùng ký token.
- JWKS trả cả public K1 và public K2.
- Chờ các resource server refresh JWKS theo cache policy; xác minh mọi API quan trọng đã thấy K2.
- K1 vẫn là ACTIVE_SIGNING.

Không chuyển signer ngay trong cùng thao tác publish nếu resource server có cache và không đảm bảo refresh khi gặp unknown kid. Thời gian chờ phải dựa trên max-age, refresh policy, propagation và quan sát thực tế.

### Giai đoạn 2 — Switch signer sang K2

- Thực hiện chuyển active signer nguyên tử sang K2.
- K2 thành ACTIVE_SIGNING.
- K1 chuyển thành VERIFY_ONLY.
- JWKS tiếp tục công bố K1 và K2.
- Phát token mới và xác minh header kid là K2.
- Xác minh token K1 cũ vẫn được chấp nhận khi còn hạn.

Trong giai đoạn overlap, cả hai public key đều cần tồn tại trong JWKS. Không xóa K1 ngay sau khi K2 bắt đầu ký.

### Giai đoạn 3 — Retire K1

- Tìm thời điểm hết hạn lớn nhất của token đã ký bằng K1.
- Chờ đến sau thời điểm đó cộng clock skew và propagation margin.
- Xác minh không còn signer instance nào dùng K1.
- Gỡ public K1 khỏi JWKS.
- K1 chuyển RETIRED; private key được lưu hoặc hủy theo key retention policy.
- Xác minh token K2 vẫn hợp lệ và token K1 đã hết hạn.

Không giữ private key cũ chỉ vì public key còn được cache. Việc lưu, archive hoặc hủy private key phải theo chính sách quản lý khóa và yêu cầu audit; nếu không còn mục đích ký/khôi phục, hạn chế quyền và xử lý theo quy trình đã phê duyệt.

## 9. Ma trận kiểm thử bắt buộc

| ID | Trạng thái JWKS | Token | Kết quả mong đợi |
| --- | --- | --- | --- |
| K01 | K1 | Ký K1, kid=K1, claims đúng | Chấp nhận |
| K02 | K1 | Ký bằng khóa khác nhưng kid=K1 | Từ chối chữ ký |
| K03 | K1 | kid không tồn tại | Từ chối sau refresh/lookup hợp lệ |
| K04 | K1+K2 | Token K1 còn hạn | Chấp nhận |
| K05 | K1+K2 | Token K2 mới | Chấp nhận |
| K06 | K1+K2 | kid=K2 nhưng ký bằng private K1 | Từ chối chữ ký |
| K07 | K1+K2 | Đúng chữ ký nhưng aud=billing-api | Từ chối |
| K08 | K1+K2 | Đúng chữ ký nhưng iss sai | Từ chối |
| K09 | K1+K2 | alg ngoài allowlist | Từ chối |
| K10 | K2 sau retire | Token K2 còn hạn | Chấp nhận |
| K11 | K2 sau retire | Token K1 còn hạn do test fixture cố tình giữ | Từ chối sau khi JWKS refresh; ghi nhận tác động cache |
| K12 | JWKS lỗi/timeout, không có key cache phù hợp | Token có kid chưa biết | Fail closed |
| K13 | K1+K2 | JWKS có kid trùng cho hai public key | Từ chối cấu hình/không publish |
| K14 | K1+K2 | JWKS chứa private parameter | Test publish phải thất bại |

K11 là test hành vi khi gỡ khóa trước khi token cũ hết hạn. Trong rotation bình thường, không triển khai giai đoạn này; test nhằm giúp hiểu vì sao gỡ key sớm có thể tạo lỗi không nhất quán. Sau khi K1 token hết hạn, token đó phải bị từ chối dù public key K1 còn trong cache, vì kiểm tra exp vẫn phải được thực hiện.

### Unit test cho public-only JWKS

~~~java
import static org.junit.jupiter.api.Assertions.*;

import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.RSAKey;
import org.junit.jupiter.api.Test;

class JwksPublicationTest {

    @Test
    void publishesPublicKeysOnly() throws Exception {
        RSAKey key = createSigningKey("key-test-1");

        JWKSet jwks = new JWKSet(key.toPublicJWK());
        String json = jwks.toString();

        assertTrue(json.contains("key-test-1"));
        assertFalse(json.contains("\"d\""));
        assertFalse(json.contains("\"p\""));
        assertFalse(json.contains("\"q\""));
    }
}
~~~

Test trên là kiểm tra cơ bản. Có thể parse JWKS thành JWKSet rồi xác minh mọi key không có private parameters thay vì chỉ tìm chuỗi JSON. Dùng key fixture tạo trong test; không dùng private key production.

### Integration test với WireMock

Dùng WireMock để kiểm soát JWKS endpoint:

1. Stub JWKS chỉ chứa K1.
2. Khởi tạo decoder mới và xác minh token K1.
3. Thay response thành K1+K2.
4. Kiểm tra resource server tải JWKS mới và xác minh token K2.
5. Thay response thành K2.
6. Làm mới decoder/cache theo cơ chế test được kiểm soát và xác minh hành vi sau khi retire K1.
7. Stub 500, timeout, JSON lỗi và JWKS rỗng; xác minh token chưa có key không được chấp nhận.

Decoder có thể cache JWKS. Không giả định mỗi request sẽ gọi endpoint. Để kiểm tra lần tải đầu, tạo decoder mới. Để kiểm tra refresh khi kid lạ, dùng đúng cache/refresh behavior của thư viện và verify request WireMock. Không phụ thuộc cứng vào số request nếu thư viện có thể retry hoặc cache.

## 10. Cache và unknown kid

Resource server thường cache JWKS để giảm network request. Khi gặp token có kid chưa biết, một số implementation có thể refresh key set; hành vi này phụ thuộc thư viện và cấu hình.

Cần kiểm tra:

- JWKS cache TTL và HTTP cache header có thống nhất không.
- Khi kid mới xuất hiện, decoder có refresh JWKS không.
- Có giới hạn refresh để tránh attacker gửi nhiều kid ngẫu nhiên gây request storm không.
- Khi JWKS endpoint timeout, key cache cũ còn được dùng trong trường hợp nào.
- Khi key bị gỡ, thời gian tối đa resource server còn giữ key là bao lâu.
- Nhiều instance có cùng trust configuration và cache policy không.

Không để mỗi token có kid ngẫu nhiên kích hoạt một request không giới hạn đến issuer. Cần rate limit hoặc refresh throttling theo khả năng thư viện. Không dùng lỗi fetch JWKS làm lý do bỏ xác minh chữ ký.

### Cache và thời điểm publish K2

Giả sử JWKS cache có TTL 5 phút. Nếu issuer publish K2 rồi lập tức ký bằng K2, resource server còn cache K1 có thể không tìm thấy K2. Nếu thư viện refresh ngay khi unknown kid, token có thể vẫn thành công, nhưng không nên dựa vào hành vi chưa được xác minh.

Phương án an toàn cho rotation định kỳ:

1. Publish K2 cùng K1.
2. Chờ ít nhất khoảng phân phối/cache cần thiết theo policy.
3. Quan sát hoặc kiểm tra các resource server đã nhận K2.
4. Sau đó mới switch signer.

TTL thực tế phải được xác định theo HTTP caching, thư viện, gateway và thời gian triển khai. Không dùng một con số cố định cho mọi hệ thống.

## 11. Rollback và xử lý khẩn cấp

### Rollback khi K2 có lỗi vận hành

Nếu K2 không được resource server chấp nhận do lỗi cấu hình hoặc triển khai, và K1 chưa bị compromise:

- Chuyển signer về K1 bằng thao tác có kiểm soát.
- Giữ cả K1 và K2 trong JWKS nếu đã phát hành token bằng K2.
- Khắc phục discovery/JWKS/cache/configuration.
- Chỉ retire K2 sau khi token ký K2 hết hạn hoặc đã được xử lý bằng revoke policy.
- Ghi lại thời điểm, người thực hiện, lý do và kết quả rollback.

Không xóa K2 ngay khi rollback nếu đã có token ký bằng K2 còn hạn. Các resource server vẫn cần public K2 để xác minh token đó.

### Khi private key bị compromise

Đây không phải rotation định kỳ. Nếu private key K1 bị lộ, attacker có thể ký token giả bằng K1. Không chờ access token K1 hết hạn theo quy trình overlap thông thường.

Quy trình khẩn cấp cần được thiết kế và diễn tập riêng:

1. Dừng ký bằng K1 ngay lập tức.
2. Chuyển sang khóa sạch K2 và xác nhận private K2 chưa bị ảnh hưởng.
3. Gỡ K1 khỏi JWKS theo incident policy.
4. Làm mới/invalidate cache ở resource server bằng cơ chế vận hành đã chuẩn bị.
5. Revoke hoặc từ chối token ký K1 qua denylist, introspection, issuer policy hoặc cơ chế khẩn cấp phù hợp.
6. Đánh giá refresh token/session liên quan và yêu cầu xác thực lại khi cần.
7. Bảo toàn audit evidence, điều tra phạm vi compromise và xoay các secret liên quan nếu có dấu hiệu lộ rộng hơn.
8. Ghi lại thời gian phát hiện, thời gian ngừng ký, thời gian các resource server ngừng tin K1 và các khoảng trễ còn lại.

Gỡ K1 khỏi JWKS không bảo đảm tất cả resource server ngừng tin K1 ngay lập tức vì cache có thể còn giữ public key. Vì vậy, cần có cơ chế cache invalidation hoặc policy khẩn cấp ở từng trust boundary. Không tuyên bố đã revoke toàn bộ token nếu chưa có bằng chứng từ resource server.

## 12. Observability cho key rotation

Ghi security/operational event cho từng bước:

| Event | Khi nào ghi |
| --- | --- |
| signing_key_created | Key mới được tạo và đăng ký |
| jwks_key_published | Public key mới xuất hiện trong JWKS |
| signing_key_activated | Key mới trở thành active signer |
| signing_key_demoted | Key cũ chuyển sang verify-only |
| jwks_key_removed | Public key cũ được gỡ khỏi JWKS |
| signing_key_retired | Key đã kết thúc vòng đời |
| jwks_publish_failed | Không thể publish JWKS đúng policy |
| key_rotation_rollback | Rotation được rollback có kiểm soát |

Metric gợi ý:

- Số lần JWKS fetch success/failure.
- Số JWT validation failure theo reason enum.
- Số request gặp unknown kid.
- Thời gian publish đến khi resource server xác nhận thấy key mới.
- Thời gian rotation từ publish đến switch signer.
- Số khóa đang được publish và số signer đang active.

kid là định danh public, nhưng không nên dùng giá trị tùy ý do request cung cấp làm metric label. Dùng issuer alias, environment và outcome có cardinality giới hạn; kid có thể ghi trong audit event nếu cần điều tra.

Không log private key, access token hoặc refresh token. Audit event cần có actor/service, timestamp, key reference, action, result và correlation ID theo policy.

## 13. Deliverables và tiêu chí hoàn thành

Dự án cần có các thành phần:

~~~text
key-rotation-lab/
  issuer-lab/
    keyring/
    token/
    jwks/
  orders-api/
    security/
    orders/
  integration-tests/
    jwks/
    rotation/
    failure/
  docs/
    rotation-runbook.md
~~~

Cấu trúc trên là gợi ý; có thể dùng multi-module Gradle hoặc hai Spring Boot application riêng.

### Deliverables

1. Key manager có trạng thái PREPARED, ACTIVE_SIGNING, VERIFY_ONLY, RETIRED.
2. JWKS endpoint chỉ công bố public key.
3. Token issuer ký bằng active key và đặt đúng kid.
4. Orders API xác minh chữ ký, issuer, audience, thời hạn và scope.
5. Integration test mô phỏng publish K2, overlap, switch signer và retire K1.
6. Test cache/unknown kid, JWKS failure và key mismatch.
7. Rotation runbook ghi rõ điều kiện publish, switch, remove, rollback và emergency.
8. Audit event/metric đủ để theo dõi tiến trình và lỗi.

### Acceptance criteria

- Token K1 được xác minh khi JWKS có K1.
- Sau khi publish K1+K2 và resource server đã nhận K2, token K2 được xác minh.
- Trong giai đoạn overlap, token K1 cũ còn hạn và token K2 mới đều được xác minh.
- Sau khi K1 token hết hạn và K1 bị gỡ, token K2 vẫn hợp lệ.
- Token sai issuer, audience, chữ ký, thuật toán hoặc kid bị từ chối.
- JWKS không bao giờ chứa private key parameters.
- Khi JWKS không thể cung cấp khóa chưa biết, API không bỏ qua xác minh.
- Rotation và rollback không tạo hai signer active ngoài ý muốn.
- Không có token/private key trong log, metric hoặc trace.
- Runbook phân biệt rotation định kỳ với emergency compromise.

## 14. Checklist triển khai production

- [ ] Signing key được tạo trong KMS/HSM hoặc môi trường quản lý khóa được bảo vệ.
- [ ] Mỗi key có kid duy nhất và algorithm allowlist rõ ràng.
- [ ] JWKS chỉ chứa public JWK.
- [ ] K2 được publish trước khi trở thành signer.
- [ ] Resource server đã nhận K2 trước khi switch signer.
- [ ] K1 tiếp tục được publish trong overlap.
- [ ] Đã xác định last expiry của token K1 và maximum clock skew.
- [ ] Không gỡ K1 trước khi token K1 hết hạn trong rotation bình thường.
- [ ] JWKS cache TTL, unknown kid refresh và rate limiting đã được kiểm thử.
- [ ] Issuer, audience, token type, time và signature đều được validate.
- [ ] Có test nhiều API/resource server và nhiều instance.
- [ ] Có rollback plan giữ lại key dùng để xác minh token còn hạn.
- [ ] Có emergency key compromise procedure và cache invalidation plan.
- [ ] Có audit event và alert cho publish/switch/remove failures.
- [ ] Không ghi private key, access token hoặc refresh token vào telemetry.

## Ghi nhớ

- JWKS là nơi công bố public key; private key chỉ ở issuer/signing infrastructure.
- kid giúp chọn khóa, không tự tạo niềm tin.
- Rotation bình thường theo thứ tự **publish K2 → overlap K1/K2 → switch signer → chờ K1 token hết hạn → remove K1**.
- Resource server có thể cache JWKS; phải kiểm thử TTL và unknown kid refresh.
- Khi rollback, giữ public key của mọi token còn hạn.
- Khi private key bị compromise, dùng emergency procedure; không áp dụng thời gian chờ của rotation định kỳ.
- Chữ ký hợp lệ chưa đủ: luôn kiểm tra issuer, audience, thời gian, token type và authorization.

### Tiêu chuẩn tham khảo

- **RFC 7517 — JSON Web Key (JWK):** cấu trúc JWK và JWKS.
- **RFC 7515 — JSON Web Signature (JWS):** chữ ký JWT và header kid.
- **RFC 7519 — JSON Web Token (JWT):** claims iss, aud, iat, exp, nbf.
- **RFC 8725 — JWT Best Current Practices:** issuer/audience validation, algorithm restrictions và key trust.
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** profile JWT access token.
- **OpenID Connect Discovery:** metadata và jwks_uri của OpenID Provider.
- **Spring Security Resource Server JWT documentation:** cấu hình decoder, JWKS và validators.
- **Nimbus JOSE + JWT documentation:** tạo RSA JWK, ký JWT và xuất JWKS.
