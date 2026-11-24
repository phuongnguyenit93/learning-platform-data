# WireMock discovery và JWKS

## Mục tiêu

Trong OAuth 2.0/OIDC, resource server thường cần đọc metadata của identity provider (IdP) để tìm endpoint cung cấp khóa công khai, sau đó tải JSON Web Key Set (JWKS) nhằm xác minh chữ ký JWT. Nếu integration test gọi thẳng IdP thật, kết quả có thể phụ thuộc mạng, trạng thái môi trường, dữ liệu tài khoản và lịch xoay khóa.

**WireMock** cho phép dựng một IdP giả qua HTTP trong phạm vi test. Ta kiểm soát được discovery metadata, JWKS, lỗi mạng và quá trình thay đổi khóa, trong khi vẫn dùng thư viện JWT thật để kiểm tra chữ ký.

Sau bài này, bạn có thể:

- Phân biệt discovery metadata với JWKS và giải thích quan hệ giữa `issuer` và `jwks_uri`.
- Dùng WireMock mô phỏng discovery endpoint và JWKS endpoint.
- Tạo JWT bằng khóa riêng chỉ dùng trong test và xác minh bằng public key được WireMock cung cấp.
- Kiểm thử issuer, audience, `kid`, chữ ký và các tình huống xoay khóa.
- Mô phỏng metadata/JWKS sai định dạng, thiếu trường, timeout và lỗi HTTP.
- Xác minh ứng dụng từ chối token khi không thể thiết lập chuỗi tin cậy.

## 1. Discovery và JWKS giải quyết hai việc khác nhau

Giả sử API `orders-api` tin cậy issuer:

`https://identity.example.test`

Resource server cần biết public key nào dùng để xác minh JWT. Thay vì cấu hình thủ công từng khóa, ứng dụng có thể lấy metadata từ discovery endpoint. Metadata chỉ ra `jwks_uri`, tức URL chứa các khóa công khai.

~~~mermaid
sequenceDiagram
    participant API as Resource Server
    participant META as Discovery Endpoint
    participant JWKS as JWKS Endpoint
    participant CLIENT as Client

    API->>META: GET OpenID Provider Metadata
    META-->>API: issuer, jwks_uri, metadata
    API->>JWKS: GET jwks_uri
    JWKS-->>API: JSON Web Key Set
    CLIENT->>API: Bearer JWT (header có kid)
    API->>API: Chọn public key theo kid
    API->>API: Verify signature và claims
    API-->>CLIENT: Cho phép hoặc từ chối
~~~

Hai tài nguyên có vai trò riêng:

| Thành phần | Ví dụ | Mục đích |
| --- | --- | --- |
| Issuer | `https://identity.example.test` | Định danh nhà phát hành token |
| Discovery metadata | `/.well-known/openid-configuration` | Công bố cấu hình của OpenID Provider |
| `jwks_uri` | `/oauth2/jwks` | Địa chỉ lấy các public key |
| JWKS | JSON chứa `keys[]` | Cung cấp public key, `kid`, thuật toán và metadata khóa |
| JWT header | `{"alg":"RS256","kid":"signing-key-2026"}` | Gợi ý chọn khóa trong JWKS |
| JWT claims | `iss`, `aud`, `sub`, `exp` | Thông tin issuer, bên nhận, chủ thể và thời hạn |

**Discovery không xác minh JWT.** Nó giúp ứng dụng tìm cấu hình và khóa. Sau đó thư viện JWT mới dùng khóa thích hợp để xác minh chữ ký; ứng dụng còn phải kiểm tra issuer, audience, thời gian và token profile.

**JWKS không chứa private key.** Authorization server giữ private key để ký token. Resource server nhận public key để xác minh. Không bao giờ đưa private key production vào discovery document hoặc JWKS.

### Ví dụ discovery metadata

Với issuer gốc `https://identity.example.test`, metadata có thể trông như sau:

~~~json
{
  "issuer": "https://identity.example.test",
  "jwks_uri": "https://identity.example.test/oauth2/jwks",
  "authorization_endpoint": "https://identity.example.test/oauth2/authorize",
  "token_endpoint": "https://identity.example.test/oauth2/token",
  "id_token_signing_alg_values_supported": ["RS256"]
}
~~~

Resource server thường cần `issuer` và `jwks_uri` để xác minh JWT. Các trường khác phục vụ những luồng OAuth/OIDC tương ứng; API không cần gọi authorization endpoint hay token endpoint chỉ để kiểm tra chữ ký access token.

Đường dẫn discovery phụ thuộc loại metadata và issuer. Với issuer không có path, OpenID Connect Discovery thường dùng `/.well-known/openid-configuration` tại host. Khi issuer có path, quy tắc tạo URL có khác biệt giữa các chuẩn discovery; hãy để thư viện theo chuẩn tạo URL hoặc cấu hình URL chính xác theo tài liệu IdP. Trong test, stub đúng URL mà thư viện thực sự gọi, không tự giả định mọi issuer đều có cùng quy tắc nối chuỗi.

## 2. JWKS và `kid`

Một JWKS chứa mảng `keys`. Ví dụ RSA public key:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "use": "sig",
      "kid": "signing-key-2026",
      "alg": "RS256",
      "n": "public-modulus-base64url",
      "e": "AQAB"
    }
  ]
}
~~~

Các trường thường gặp:

- `kty`: loại khóa, ví dụ `RSA` hoặc `EC`.
- `use`: mục đích của khóa, thường là `sig` cho ký/xác minh.
- `kid`: định danh khóa. JWT header thường mang `kid` để resource server tìm khóa tương ứng.
- `alg`: thuật toán gắn với khóa nếu được công bố.
- `n`, `e`: thành phần public key RSA ở dạng Base64URL.
- Với EC, các trường khóa có cấu trúc khác, ví dụ `crv`, `x`, `y`.

`kid` là chỉ dẫn chọn khóa, **không phải bằng chứng tin cậy**. Server phải lấy khóa từ JWKS của issuer đã được cấu hình tin cậy và xác minh chữ ký. Không tải URL do JWT tự khai báo trong `jku` hoặc `x5u` nếu ứng dụng không có một chính sách tin cậy rõ ràng cho các header đó.

Một JWKS có thể công bố nhiều khóa trong giai đoạn xoay khóa: khóa cũ để xác minh token còn hiệu lực, khóa mới để xác minh token vừa phát hành. Không giả định JWKS luôn chỉ có một phần tử.

## 3. WireMock trong integration test

WireMock tạo HTTP server cục bộ và cho phép định nghĩa phản hồi theo URL, header, method hoặc body. Trong bài này, ta dùng nó để mô phỏng:

- Discovery endpoint trả về metadata.
- JWKS endpoint trả về public key.
- Các phản hồi lỗi như 404, 500, JSON không hợp lệ hoặc endpoint chậm.
- JWKS thay đổi khi issuer xoay khóa.

WireMock kiểm soát **HTTP dependency**. Nó không thay thế `JwtDecoder`, không giả lập kết quả chữ ký thành công và không chứng minh ứng dụng xác minh JWT đúng. Muốn test chuỗi thật, cần tạo JWT ký bằng private key test và để decoder xác minh bằng public key lấy qua WireMock.

### Dependency minh họa

Ví dụ dùng JUnit 5, WireMock và Spring Security OAuth2 Resource Server. Chọn phiên bản tương thích với Spring Boot/Spring Security của dự án:

~~~xml
<dependency>
    <groupId>org.wiremock</groupId>
    <artifactId>wiremock</artifactId>
    <version>WIREMOCK_VERSION</version>
    <scope>test</scope>
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
    <scope>test</scope>
</dependency>
~~~

Các ví dụ bên dưới giả định Java hỗ trợ text block và một phiên bản WireMock tương thích với API JUnit/server được dùng. Nếu dự án quản lý dependency bằng Gradle, khai báo các dependency tương ứng trong source set test.

### Khởi tạo server động

~~~java
import static com.github.tomakehurst.wiremock.client.WireMock.*;
import static com.github.tomakehurst.wiremock.core.WireMockConfiguration.wireMockConfig;

import com.github.tomakehurst.wiremock.WireMockServer;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;

class DiscoveryAndJwksIntegrationTest {

    private WireMockServer wireMock;

    @BeforeEach
    void startWireMock() {
        wireMock = new WireMockServer(wireMockConfig().dynamicPort());
        wireMock.start();
    }

    @AfterEach
    void stopWireMock() {
        if (wireMock != null) {
            wireMock.stop();
        }
    }

    // Các test và helper được đặt trong class này.
}
~~~

Dùng cổng động để tránh xung đột khi chạy test song song hoặc trên CI. Không cố định cổng production, không cần mở kết nối Internet. Mỗi test nên tự dựng server và dọn dẹp sau khi chạy.

## 4. Tạo khóa test và JWT có chữ ký thật

Để kiểm tra JWKS, test cần một cặp khóa:

- Private key chỉ dùng để ký JWT trong test.
- Public key được công bố qua endpoint JWKS giả.

Ví dụ dùng Nimbus JOSE + JWT:

~~~java
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.JWSHeader;
import com.nimbusds.jose.crypto.RSASSASigner;
import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jose.jwk.gen.RSAKeyGenerator;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.SignedJWT;

import java.util.Date;

RSAKey signingKey = new RSAKeyGenerator(2048)
    .keyID("test-key-1")
    .generate();

String publicJwks = new JWKSet(signingKey.toPublicJWK()).toString();
~~~

`publicJwks` chỉ chứa public key. Private key nằm trong `signingKey` và chỉ được dùng trong bộ test.

Tạo access token:

~~~java
String createAccessToken(
    RSAKey signingKey,
    String issuer,
    String audience,
    String keyId
) throws Exception {
    Date now = new Date();

    JWTClaimsSet claims = new JWTClaimsSet.Builder()
        .issuer(issuer)
        .subject("user-42")
        .audience(audience)
        .issueTime(now)
        .notBeforeTime(new Date(now.getTime() - 5_000))
        .expirationTime(new Date(now.getTime() + 300_000))
        .claim("scope", "orders:read")
        .build();

    JWSHeader header = new JWSHeader.Builder(JWSAlgorithm.RS256)
        .keyID(keyId)
        .build();

    SignedJWT jwt = new SignedJWT(header, claims);
    jwt.sign(new RSASSASigner(signingKey));

    return jwt.serialize();
}
~~~

Để cô lập từng điều kiện, test nên giữ nguyên private key, issuer, thời gian và token profile; chỉ thay một yếu tố như `kid`, `aud` hoặc `iss`. Khi test chữ ký sai, tạo token ký bằng một cặp khóa khác mà public key không có trong JWKS.

## 5. Stub discovery và JWKS

Với issuer gốc chạy tại WireMock, test có thể dựng metadata và JWKS như sau:

~~~java
String issuer = wireMock.baseUrl();
String jwksUri = issuer + "/oauth2/jwks";

wireMock.stubFor(get(urlEqualTo("/.well-known/openid-configuration"))
    .willReturn(okJson("""
        {
          "issuer": "%s",
          "jwks_uri": "%s"
        }
        """.formatted(issuer, jwksUri))));

wireMock.stubFor(get(urlEqualTo("/oauth2/jwks"))
    .willReturn(okJson(publicJwks)));
~~~

Các điểm cần giữ nhất quán:

1. `issuer` trong discovery phải bằng chính xác issuer mà ứng dụng cấu hình tin cậy.
2. `jwks_uri` phải trỏ đến endpoint WireMock đang stub.
3. JWT phải có `iss` khớp issuer đó.
4. `kid` trong JWT header phải khớp một khóa trong JWKS.
5. Chữ ký JWT phải được tạo bằng private key tương ứng với public key trong JWKS.
6. `aud` phải là audience của resource server nếu test đang kiểm tra luồng chấp nhận token.

Discovery metadata không nhất thiết phải chứa toàn bộ endpoint OAuth để resource server xác minh JWT. Chỉ stub các trường mà thư viện và cấu hình thực tế yêu cầu. Nếu thư viện gửi request đến một URL discovery khác, hãy kiểm tra request thực tế và sửa stub theo chuẩn mà thư viện đang dùng.

### Tạo decoder từ issuer

Với Spring Security, `JwtDecoders.fromIssuerLocation` có thể tạo decoder dựa trên issuer metadata:

~~~java
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtDecoders;

JwtDecoder decoder = JwtDecoders.fromIssuerLocation(issuer);

String token = createAccessToken(
    signingKey,
    issuer,
    "orders-api",
    "test-key-1"
);

Jwt decoded = decoder.decode(token);

assertThat(decoded.getSubject()).isEqualTo("user-42");
assertThat(decoded.getIssuer().toString()).isEqualTo(issuer);
~~~

Đoạn này minh họa luồng discovery → JWKS → xác minh chữ ký và các validator mặc định của decoder. **Cần cấu hình audience validator riêng** cho resource server nếu framework/configuration hiện tại chưa thực hiện kiểm tra audience. Không coi việc decode thành công là bằng chứng `aud` đúng.

Để chứng minh HTTP dependency đã được sử dụng:

~~~java
wireMock.verify(getRequestedFor(
    urlEqualTo("/.well-known/openid-configuration")
));

wireMock.verify(getRequestedFor(
    urlEqualTo("/oauth2/jwks")
));
~~~

Một số thư viện cache discovery metadata hoặc JWKS. Nếu test dùng chung decoder giữa nhiều test, request có thể không được gửi lại mỗi lần. Muốn kiểm tra lần tải đầu, tạo decoder mới hoặc fixture độc lập cho test; không viết assertion rằng mỗi lần decode bắt buộc phải tải JWKS.

## 6. Kiểm tra issuer, audience và chữ ký

Discovery và JWKS chỉ cung cấp dữ liệu để xác minh. Resource server vẫn cần kiểm tra:

- Chữ ký bằng khóa được chọn từ JWKS của issuer tin cậy.
- `iss` chính xác bằng issuer đã cấu hình.
- `aud` chứa định danh resource server được chấp nhận.
- `exp`, `nbf` và các điều kiện thời gian theo policy.
- Token đúng loại/profile API chấp nhận.
- Scope/role trước khi thực hiện thao tác nghiệp vụ.

Ví dụ cấu hình thêm audience validator với Spring Security:

~~~java
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

NimbusJwtDecoder decoder =
    NimbusJwtDecoder.withIssuerLocation(issuer).build();

OAuth2TokenValidator<Jwt> issuerAndTime =
    JwtValidators.createDefaultWithIssuer(issuer);

OAuth2TokenValidator<Jwt> audience =
    new AudienceValidator("orders-api");

decoder.setJwtValidator(
    new DelegatingOAuth2TokenValidator<>(issuerAndTime, audience)
);
~~~

`AudienceValidator` ở đây là validator so khớp claim `aud` với API. Nếu ứng dụng đã có validator cho token profile, thời gian hoặc tenant policy, hãy kết hợp các validator cần thiết; không vô tình thay thế validator mặc định bằng một validator chỉ kiểm tra audience.

### Ma trận test tối thiểu

| Tình huống | Discovery/JWKS | JWT | Kết quả |
| --- | --- | --- | --- |
| Khóa đúng, issuer đúng | Thành công | Chữ ký hợp lệ, `kid` có trong JWKS | Qua xác minh; tiếp tục audience/authorization |
| Audience sai | Thành công | Chữ ký và issuer đúng, `aud` của API khác | 401 |
| Issuer sai | Discovery của issuer tin cậy | Chữ ký hợp lệ nhưng `iss` khác | 401 |
| `kid` không tồn tại | JWKS hợp lệ | Không tìm được khóa tương ứng | 401 |
| Chữ ký sai | JWKS hợp lệ | Ký bằng private key khác | 401 |
| Token hết hạn | JWKS hợp lệ | `exp` trong quá khứ | 401 |
| Token chưa có hiệu lực | JWKS hợp lệ | `nbf` ở tương lai ngoài clock skew | 401 |
| Discovery lỗi | Không lấy được metadata | Token bất kỳ | Không xác thực được |
| JWKS lỗi | Metadata đọc được nhưng key endpoint lỗi | Token bất kỳ | Không xác thực được |

Khi test audience mismatch, hãy dùng token ký bằng đúng private key, issuer đúng và thời hạn hợp lệ. Nếu token đồng thời sai chữ ký và audience, test không chứng minh audience validator đã chạy.

## 7. Kiểm thử lỗi discovery

Một discovery document sai có thể khiến ứng dụng chọn nhầm issuer hoặc không tìm được JWKS. Dùng WireMock để mô phỏng từng lỗi riêng:

| Trường hợp | Phản hồi WireMock | Kỳ vọng |
| --- | --- | --- |
| Endpoint không tồn tại | 404 | Khởi tạo decoder hoặc xác thực thất bại |
| IdP tạm lỗi | 500 | Không chấp nhận token khi chưa có trust configuration hợp lệ |
| JSON sai cú pháp | Body JSON hỏng | Metadata không được sử dụng |
| Thiếu `issuer` | Metadata thiếu trường | Từ chối cấu hình |
| Thiếu `jwks_uri` | Metadata không có URL khóa | Không thể xác minh JWT |
| `issuer` không khớp | Metadata trả issuer khác | Từ chối vì issuer mismatch |
| `jwks_uri` không hợp lệ | URI sai định dạng | Không tải được khóa |
| Phản hồi chậm | Delay vượt timeout | Xác thực thất bại theo timeout policy |

Ví dụ metadata issuer mismatch:

~~~java
wireMock.stubFor(get(urlEqualTo("/.well-known/openid-configuration"))
    .willReturn(okJson("""
        {
          "issuer": "https://attacker.example.test",
          "jwks_uri": "%s/oauth2/jwks"
        }
        """.formatted(wireMock.baseUrl()))));
~~~

Ứng dụng không được chấp nhận metadata chỉ vì endpoint trả HTTP 200. Giá trị `issuer` phải khớp chính xác issuer mà server đang tin cậy. Nếu metadata không khớp, không được âm thầm thay issuer cấu hình bằng giá trị nhận được.

### Không để discovery trở thành SSRF

Issuer và discovery URL là dữ liệu thuộc trust configuration. Không nhận một issuer tùy ý từ query parameter hoặc JWT rồi gọi URL đó trực tiếp. Nếu kẻ tấn công điều khiển được URL discovery hoặc `jwks_uri`, server có thể bị ép truy cập địa chỉ nội bộ.

Các biện pháp:

- Chỉ cho phép issuer đã đăng ký trong cấu hình server.
- Dùng HTTPS và kiểm tra TLS trong production.
- Kiểm soát host/egress của `jwks_uri` theo chính sách IdP.
- Không theo redirect đến host không được phép nếu thư viện/client cho phép cấu hình.
- Đặt connect/read timeout, giới hạn kích thước response và xử lý lỗi rõ ràng.
- Không dùng header `jku`/`x5u` của JWT làm URL thay thế cho JWKS tin cậy.

Trong test, WireMock chạy HTTP localhost là lựa chọn phù hợp để cô lập mạng; điều này không có nghĩa production nên bỏ TLS.

## 8. Kiểm thử lỗi JWKS và chọn khóa

JWKS endpoint có thể trả dữ liệu hợp lệ về HTTP nhưng không có khóa cần thiết. Các test quan trọng:

| Trường hợp | JWKS hoặc token | Kỳ vọng |
| --- | --- | --- |
| JWKS rỗng | `{"keys":[]}` | Không tìm thấy khóa; từ chối token |
| JWKS sai JSON | Body không parse được | Không xác minh được |
| JWKS 500 | Server lỗi | Không xác minh được nếu không có khóa cache hợp lệ theo policy |
| `kid` lạ | Token có `kid` không tồn tại | Từ chối sau quy trình refresh hợp lệ của thư viện |
| Khóa sai loại | JWT RS256 nhưng JWKS không có khóa RSA phù hợp | Từ chối |
| Thuật toán không cho phép | Token dùng thuật toán ngoài policy | Từ chối |
| Nhiều khóa | JWKS có khóa cũ và mới | Chọn đúng khóa theo `kid` |
| Chữ ký không khớp | `kid` có tồn tại nhưng token ký bằng khóa khác | Từ chối |

Ví dụ stub JWKS rỗng:

~~~java
wireMock.stubFor(get(urlEqualTo("/oauth2/jwks"))
    .willReturn(okJson("""
        {"keys": []}
        """)));
~~~

Ví dụ endpoint lỗi:

~~~java
wireMock.stubFor(get(urlEqualTo("/oauth2/jwks"))
    .willReturn(aResponse()
        .withStatus(503)
        .withHeader("Content-Type", "application/json")
        .withBody("""
            {"error":"temporarily_unavailable"}
            """)));
~~~

Không nên bắt mọi exception rồi trả về một `Jwt` giả để test tiếp. Lỗi đọc JWKS phải khiến xác minh thất bại, trừ trường hợp thư viện còn một khóa cache hợp lệ và policy cho phép dùng khóa đó.

## 9. Kiểm thử xoay khóa (key rotation)

Trong vận hành, IdP có thể thay khóa ký. Một giai đoạn chuyển tiếp thường có cả khóa cũ và khóa mới trong JWKS:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "use": "sig",
      "kid": "key-old",
      "alg": "RS256",
      "n": "old-public-modulus",
      "e": "AQAB"
    },
    {
      "kty": "RSA",
      "use": "sig",
      "kid": "key-new",
      "alg": "RS256",
      "n": "new-public-modulus",
      "e": "AQAB"
    }
  ]
}
~~~

Test nên mô phỏng các giai đoạn:

1. **Trước xoay khóa:** JWKS chỉ có `key-old`; token ký bằng khóa cũ được chấp nhận.
2. **Giai đoạn overlap:** JWKS có cả `key-old` và `key-new`; token ký bằng cả hai khóa được chấp nhận nếu các claims hợp lệ.
3. **Sau xoay khóa:** JWKS chỉ còn `key-new`; token mới được chấp nhận khi decoder đã tải bộ khóa mới.
4. **Khóa không còn được công bố:** token ký bằng `key-old` phải bị từ chối sau khi cache được làm mới và khóa cũ không còn được tin cậy.

Ví dụ thay response JWKS:

~~~java
import java.util.List;

wireMock.stubFor(get(urlEqualTo("/oauth2/jwks"))
    .willReturn(okJson(new JWKSet(
        List.of(
            oldSigningKey.toPublicJWK(),
            newSigningKey.toPublicJWK()
        )
    ).toString())));
~~~

Sau đó đổi stub sang chỉ `newSigningKey.toPublicJWK()` và kiểm tra hành vi của decoder theo cache policy của thư viện.

### Lưu ý về cache

JWKS client thường cache key set để giảm request. Vì vậy:

- Một token ký bằng khóa cũ có thể vẫn xác minh được trong thời gian khóa cũ còn ở cache.
- Khi gặp `kid` chưa biết, một số thư viện có thể chủ động refresh JWKS; hành vi và thời điểm refresh phụ thuộc thư viện.
- Không viết test phụ thuộc cứng vào số lần HTTP request nếu cache chưa được kiểm soát.
- Dùng decoder mới hoặc cấu hình cache test riêng khi cần xác minh lần tải đầu.
- Với test refresh, kiểm tra kết quả xác thực sau khi refresh theo API/cache behavior của thư viện; không giả định mọi thư viện refresh giống nhau.
- Chính sách cache cần cân bằng hiệu năng với thời gian thu hồi khóa. Xóa khóa khỏi JWKS không đảm bảo mọi resource server ngừng dùng khóa ngay lập tức.

Nếu cần thu hồi token ngay lập tức, chỉ xoay khóa có thể không đủ do cache và thời hạn token. Cần cân nhắc thời hạn access token, introspection, denylist hoặc cơ chế thu hồi phù hợp với kiến trúc.

## 10. Kiểm tra hành vi fail closed

Một resource server không được chấp nhận token khi không thể xác minh chữ ký bằng trust configuration hợp lệ. Test cần chứng minh các lỗi dependency không khiến ứng dụng chuyển sang chế độ tin token.

Các tình huống:

- Discovery endpoint không truy cập được khi cần khởi tạo decoder.
- JWKS endpoint timeout hoặc trả lỗi và cache không có khóa phù hợp.
- JWKS không chứa `kid` của token.
- Discovery trả issuer khác với issuer đã cấu hình.
- JWKS được tải nhưng chữ ký không khớp.
- Token có `alg` ngoài danh sách cho phép.

Trong từng trường hợp, kỳ vọng là request được từ chối; controller và service nghiệp vụ không chạy. Không dùng public key nhúng trong token, không bỏ kiểm tra chữ ký và không chấp nhận mọi issuer để "khôi phục dịch vụ".

Có thể kiểm tra side effect bằng mock service hoặc database test:

~~~java
mockMvc.perform(get("/api/orders")
        .header("Authorization", "Bearer " + tokenWithUnknownKid))
    .andExpect(status().isUnauthorized());

verify(orderService, never()).listOrders(any());
~~~

Nếu lỗi discovery/JWKS xảy ra trong giai đoạn ứng dụng khởi động, test phải xác minh ứng dụng không khởi động ở trạng thái xác thực yếu. Nếu discovery/JWKS được tải lazy khi request đến, test phải xác minh request thất bại và không tạo side effect.

## 11. Những lỗi thường gặp khi viết test

| Lỗi | Vì sao không đủ | Cách sửa |
| --- | --- | --- |
| Mock `JwtDecoder` trả JWT hợp lệ | Bỏ qua discovery, JWKS và chữ ký | Dùng decoder thật và JWT ký bằng khóa test |
| Chỉ stub JWKS, không test discovery | Không kiểm tra metadata có trỏ đúng JWKS hay không | Stub và verify cả hai endpoint |
| JWT không có chữ ký thật | Không kiểm tra việc chọn public key | Ký bằng private key test |
| `kid` không khớp JWKS | Test luôn thất bại trước khi kiểm tra logic mong muốn | Đồng bộ `kid` hoặc thay đổi có chủ đích |
| Metadata issuer khác token issuer | Test có thể thất bại vì nhiều nguyên nhân | Cố định issuer đúng, chỉ thay yếu tố đang kiểm tra |
| Chỉ assert HTTP 401 | Không chứng minh không có side effect | Verify controller/service/database không chạy |
| Dùng issuer thật trên Internet | Test phụ thuộc mạng và IdP bên ngoài | Dùng issuer localhost của WireMock |
| Dùng chung decoder giữa test xoay khóa | Cache làm kết quả khó dự đoán | Cô lập decoder/cache hoặc kiểm tra cache theo hợp đồng |
| Tin rằng xóa key khỏi JWKS có hiệu lực tức thì | Public key có thể còn trong cache | Kiểm tra cache lifetime và refresh behavior |
| Bỏ qua audience vì chữ ký đúng | Token dành cho API khác vẫn có thể được chấp nhận | Gắn audience validator riêng |
| Dùng HTTP localhost cho production | Không bảo vệ metadata/JWKS trên mạng thật | Dùng HTTPS và TLS validation trong production |

## 12. Checklist hoàn tất integration test

- [ ] WireMock chạy bằng cổng động và được dọn dẹp sau test.
- [ ] Discovery metadata trả `issuer` đúng và `jwks_uri` trỏ đúng endpoint giả.
- [ ] JWKS chỉ công bố public key, có `kid` khớp JWT.
- [ ] JWT được ký bằng private key test thật.
- [ ] Decoder thật thực hiện discovery, tải JWKS và xác minh chữ ký.
- [ ] Test xác minh issuer, audience, thời gian và token profile.
- [ ] Có test issuer mismatch, audience mismatch, unknown `kid` và chữ ký sai.
- [ ] Có test discovery 404/500, metadata hỏng/thiếu trường và JWKS lỗi.
- [ ] Có test nhiều khóa và key rotation theo cache policy.
- [ ] Lỗi discovery/JWKS khiến xác thực thất bại, không fallback sang trust không an toàn.
- [ ] Request bị từ chối không chạy controller/service hoặc tạo side effect.
- [ ] Không dùng token, private key hoặc JWKS production trong fixture.
- [ ] Production dùng HTTPS, issuer allowlist, timeout và chính sách cache phù hợp.

## Ghi nhớ

- Discovery metadata trả lời **lấy cấu hình và JWKS ở đâu**; JWKS trả lời **public key nào có thể dùng để xác minh chữ ký**.
- `kid` chỉ giúp chọn khóa; độ tin cậy đến từ issuer đã cấu hình, metadata/JWKS được lấy qua kênh tin cậy và chữ ký được xác minh.
- WireMock mô phỏng HTTP; decoder và chữ ký vẫn phải chạy thật trong integration test.
- Test token sai cần cô lập một điều kiện tại một thời điểm để kết quả chỉ ra đúng nguyên nhân.
- Cache JWKS ảnh hưởng thời điểm nhận biết khóa mới hoặc khóa bị loại bỏ; test phải phản ánh cache policy thực tế.
- Khi discovery hoặc JWKS không thể cung cấp khóa đáng tin cậy, resource server phải fail closed.

### Tiêu chuẩn và tài liệu tham khảo

- **OpenID Connect Discovery:** metadata của OpenID Provider và `jwks_uri`.
- **RFC 8414 — OAuth 2.0 Authorization Server Metadata:** cơ chế discovery metadata cho authorization server.
- **RFC 7517 — JSON Web Key (JWK):** định dạng JWK và JWKS.
- **RFC 7515 — JSON Web Signature (JWS):** cấu trúc chữ ký và header như `kid`.
- **RFC 7519 — JSON Web Token (JWT):** claims như `iss`, `aud`, `exp`, `nbf`.
- **RFC 8725 — JWT Best Current Practices:** ràng buộc issuer, audience, thuật toán và cách tránh nhầm lẫn token.
- **Spring Security Resource Server JWT documentation:** cấu hình issuer discovery, JWKS và validator cho JWT.
- **WireMock documentation:** stub HTTP, verify request và kiểm thử lỗi dependency.
