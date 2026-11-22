# Máy chủ JWKS, metadata, introspection thử nghiệm và vòng đời tài nguyên

Kiểm chứng tích hợp một Spring Security OAuth 2.0 Resource Server cần nhiều hơn một JWT được dựng trong unit test. Ứng dụng thực tế phải tìm metadata của Authorization Server, tải public keys từ JWKS endpoint hoặc gọi introspection endpoint, xác minh token và xử lý những thay đổi theo thời gian như key rotation, cache, timeout và server ngừng hoạt động.

Trong test tích hợp, có thể dựng các HTTP server cục bộ đóng vai trò **OIDC/OAuth Authorization Server metadata endpoint**, **JWKS endpoint** và **token introspection endpoint**. Các server thử nghiệm trả response có kiểm soát để test toàn bộ HTTP boundary mà không phụ thuộc IdP bên ngoài.

Một test environment tốt cần chứng minh:

- Resource Server lấy đúng metadata và JWKS URI đã cấu hình.
- JWT được ký bằng private key tương ứng với public key trên JWKS được chấp nhận.
- JWT sai chữ ký, `kid`, issuer, audience hoặc thời hạn bị từ chối.
- Key rotation hoạt động theo cache và overlap window đã thiết kế.
- Opaque token được introspect đúng endpoint, đúng client authentication và đúng form request.
- Token inactive, introspection lỗi, timeout hoặc response sai contract được xử lý an toàn.
- Test server, port, key, cache và authorized resources được khởi tạo/đóng đúng vòng đời, kể cả khi test chạy song song.

> **Mục tiêu:** kiểm tra hợp đồng HTTP giữa Resource Server và hệ thống identity. Test dùng server cục bộ và key riêng cho test; không phụ thuộc tài khoản, token hay private key của môi trường thật.

## 1. Kiến trúc test tích hợp

Một bộ test có thể dựng các endpoint sau:

| Endpoint thử nghiệm | Vai trò | Response chính |
| --- | --- | --- |
| `/.well-known/openid-configuration` | OIDC Provider Configuration | `issuer`, `jwks_uri`, endpoint metadata |
| `/.well-known/oauth-authorization-server` | OAuth Authorization Server Metadata theo RFC 8414 | `issuer`, `jwks_uri`, endpoint metadata |
| `/oauth2/jwks` | JWK Set | Public JWK dùng xác minh chữ ký |
| `/oauth2/introspect` | Token Introspection theo RFC 7662 | `active`, scope, subject, audience và metadata |

Đây là ví dụ issuer ở root path để dễ hình dung URL. Nếu issuer có path, discovery URL tuân theo quy tắc của OIDC Discovery hoặc RFC 8414 tương ứng; test phải stub đúng URL mà phiên bản Spring/Nimbus đang gọi.

~~~mermaid
flowchart TD
    T["MockMvc / Integration test"]
    RS["Spring Security Resource Server"]
    DISC["Metadata test server"]
    JWKS["JWKS test server"]
    INT["Introspection test server"]
    KEY["RSA / EC test key pair"]
    FIX["Token fixtures"]

    T -->|"Bearer JWT"| RS
    RS -->|"Discovery GET"| DISC
    DISC -->|"jwks_uri"| RS
    RS -->|"JWKS GET"| JWKS
    KEY --> JWKS
    KEY --> FIX
    FIX -->|"signed JWT"| T
    T -->|"Bearer opaque-token"| RS
    RS -->|"Introspection POST"| INT
    INT -->|"active + claims"| RS
~~~

Trong thực tế, một MockWebServer/WireMock instance có thể phục vụ nhiều endpoint; hoặc mỗi endpoint chạy trên server riêng. Dùng một server với dispatcher thường giúp test đơn giản hơn, còn tách server hữu ích khi muốn mô phỏng các dependency có lifecycle/availability khác nhau.

## 2. Chọn test server và quản lý port

Có thể dùng:

- **MockWebServer** từ OkHttp: server HTTP nhỏ, queue response, đọc request đã nhận, dễ kiểm tra method/header/body.
- **WireMock**: stub theo URL, method, header, body; hỗ trợ scenario, delay, fault và dynamic port.
- **Testcontainers**: chạy một IdP thật hoặc container phục vụ JWKS/metadata/introspection khi cần kiểm tra tương tác gần production.
- **HTTP server nhúng của JDK**: đủ cho fixture rất nhỏ, nhưng cần tự viết routing, request parsing và cleanup.

Không dùng port cố định như `8089` trong test suite. Hai test process hoặc hai worker có thể cùng chạy và chiếm port của nhau. Hãy yêu cầu OS cấp port động:

~~~java
MockWebServer server = new MockWebServer();
server.start(); // MockWebServer tự chọn port trống

String baseUrl = server.url("/").toString();
String issuer = baseUrl.substring(0, baseUrl.length() - 1);
String jwksUri = server.url("/oauth2/jwks").toString();
~~~

Đoạn code trên minh họa cách lấy URL. Với issuer thực tế, phải bảo đảm giá trị issuer trong metadata và claim iss của JWT khớp chính xác với issuer đã cấu hình; không tự thêm/bỏ dấu slash tùy tiện.

### 2.1. Tránh race condition khi khởi động

Trước khi tạo Spring ApplicationContext, test server cần:

1. Bind thành công vào port động.
2. Sẵn sàng nhận HTTP request.
3. Có metadata/JWKS/introspection response phù hợp với scenario.
4. Đăng ký URL động vào Spring properties hoặc test configuration.

Không khởi động server bất đồng bộ rồi lập tức tạo context trong khi port chưa listen. Tránh Thread.sleep() cố định; dùng lifecycle hook hoặc readiness check có timeout.

### 2.2. Ví dụ lifecycle với JUnit

~~~java
import okhttp3.mockwebserver.MockWebServer;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;

class ResourceServerIntegrationTest {

    static final MockWebServer identityServer = new MockWebServer();

    @BeforeAll
    static void startIdentityServer() throws Exception {
        identityServer.start();
        // Cài dispatcher hoặc enqueue các response cần cho suite.
    }

    @AfterAll
    static void stopIdentityServer() throws Exception {
        identityServer.shutdown();
    }
}
~~~

Với Spring Test, kết hợp `@DynamicPropertySource` để đưa URL được cấp động vào context:

~~~java
@DynamicPropertySource
static void resourceServerProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.security.oauth2.resourceserver.jwt.issuer-uri",
            ResourceServerIntegrationTest::issuer);
}
~~~

Trong ví dụ đầy đủ, issuer() trả về issuer URL từ server đã start. Bảo đảm server được khởi động trước khi Spring đọc dynamic properties. Có thể dùng JUnit extension hoặc một static test fixture tự quản lý để bảo đảm thứ tự lifecycle.

### 2.3. Một server dùng chung hay mỗi test một server?

| Cách tổ chức | Ưu điểm | Rủi ro/chi phí |
| --- | --- | --- |
| Server per test class | Khởi động nhanh hơn, fixture ổn định, ít port | Phải reset state/queue giữa các test |
| Server per test method | Cách ly state tốt, dễ test lỗi riêng | Khởi động nhiều lần, test chậm |
| Server suite-wide | Tiết kiệm tài nguyên | Dễ rò state, response queue và key giữa test |
| Testcontainers per suite/class | Gần môi trường thật | Startup/cleanup nặng hơn, cần Docker |

Chọn phạm vi theo state mà test thay đổi. Test key rotation, response delay hoặc introspection inactive thường cần state riêng; không nên để thứ tự test quyết định response mà test khác nhận được.

## 3. Dựng OIDC metadata server

Khi cấu hình `issuer-uri`, Resource Server có thể cần discovery metadata để tìm `jwks_uri`. OIDC Discovery sử dụng Provider Configuration; OAuth Authorization Server Metadata được chuẩn hóa trong RFC 8414. Metadata response phải có issuer chính xác và địa chỉ JWKS hợp lệ.

Response OIDC minh họa:

~~~json
{
  "issuer": "http://127.0.0.1:49152",
  "jwks_uri": "http://127.0.0.1:49152/oauth2/jwks",
  "authorization_endpoint": "http://127.0.0.1:49152/oauth2/authorize",
  "token_endpoint": "http://127.0.0.1:49152/oauth2/token",
  "response_types_supported": ["code"],
  "subject_types_supported": ["public"],
  "id_token_signing_alg_values_supported": ["RS256"]
}
~~~

Các endpoint authorization/token trong ví dụ là metadata bổ sung; Resource Server JWT decoder chủ yếu cần issuer và JWKS URI. Không phải test Resource Server nào cũng cần dựng authorization endpoint.

### 3.1. Stub metadata response

Với MockWebServer, có thể enqueue response:

~~~java
String issuer = identityServer.url("/").toString();
if (issuer.endsWith("/")) {
    issuer = issuer.substring(0, issuer.length() - 1);
}
String jwksUri = identityServer.url("/oauth2/jwks").toString();

String metadata = """
    {
      "issuer": "%s",
      "jwks_uri": "%s"
    }
    """.formatted(issuer, jwksUri);

identityServer.enqueue(new MockResponse()
    .setHeader("Content-Type", "application/json")
    .setBody(metadata));
~~~

Đây là cách queue response đơn giản cho một request. Khi test discovery, hãy kiểm tra path mà client thực sự gọi và dùng dispatcher nếu một server phải phục vụ cả metadata lẫn JWKS. Không giả định mọi Spring/Nimbus version dùng cùng một discovery URL cho issuer có path.

### 3.2. Các trường hợp metadata cần kiểm thử

| Scenario | Metadata server trả về | Kỳ vọng |
| --- | --- | --- |
| Discovery thành công | issuer đúng, jwks_uri hợp lệ | Decoder khởi tạo/tải key được |
| Issuer mismatch | issuer khác issuer cấu hình | Discovery/validation thất bại |
| Thiếu jwks_uri | Metadata không có field bắt buộc | Không thể lấy signing keys |
| URI không hợp lệ | jwks_uri sai định dạng | Khởi tạo hoặc fetch key thất bại |
| Metadata 404 | Endpoint discovery không tồn tại | Không thể discovery |
| Metadata 500 | IdP metadata server lỗi | Startup/fetch fail theo cấu hình |
| Timeout | Server không trả lời | Request/context fail theo timeout |
| JSON lỗi | Body không parse được | Discovery thất bại |
| Content-Type sai | Response không phải JSON hợp lệ | Client có thể từ chối parse |

### 3.3. Kiểm tra issuer chính xác

Issuer là identifier, không phải URL để tùy ý normalize. Các giá trị sau có thể không tương đương theo hợp đồng:

~~~text
https://id.example.test/realms/shop
https://id.example.test/realms/shop/
http://id.example.test/realms/shop
~~~

Test cần dùng cùng giá trị trong:

- Spring property `issuer-uri`.
- Metadata `issuer`.
- Claim `iss` của access token.

Đừng tự bỏ dấu slash hoặc đổi scheme chỉ để làm test pass. Nếu reverse proxy tạo issuer public khác internal address, metadata và token phải dùng issuer public ổn định.

### 3.4. Discovery và cấu hình JWKS URI trực tiếp

Có hai kiểu test khác nhau:

**Discovery path:** cấu hình `issuer-uri`, stub metadata endpoint, xác nhận Resource Server tìm được `jwks_uri`.

**Direct JWKS path:** cấu hình `jwk-set-uri` trực tiếp, test decoder tải JWKS mà không phụ thuộc discovery metadata. Nếu đồng thời cấu hình `issuer-uri` và `jwk-set-uri` theo Spring Boot, ứng dụng vẫn có thể kiểm tra issuer trong token trong khi không cần discovery để tìm JWKS.

Không dùng test direct JWKS để kết luận metadata discovery hoạt động. Đây là hai đường cấu hình khác nhau.

## 4. Dựng JWKS endpoint và ký JWT test

JWKS là JSON Web Key Set, chứa public keys mà Resource Server dùng để xác minh chữ ký JWT. Một key thường có `kty`, `kid`, `use`, `alg` và các public parameters. Không đưa private parameters như RSA `d`, `p`, `q` hoặc EC private scalar vào JWKS response.

Ví dụ JWKS RSA:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "orders-test-key-1",
      "use": "sig",
      "alg": "RS256",
      "n": "<base64url-modulus>",
      "e": "AQAB"
    }
  ]
}
~~~

### 4.1. Tạo RSA key pair riêng cho test

~~~java
KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
generator.initialize(2048);
KeyPair keyPair = generator.generateKeyPair();

RSAPublicKey publicKey = (RSAPublicKey) keyPair.getPublic();
RSAPrivateKey privateKey = (RSAPrivateKey) keyPair.getPrivate();
~~~

Private key chỉ dùng để ký fixture trong test. JWKS endpoint chỉ publish public key. Mỗi test suite nên tạo key riêng hoặc dùng key fixture test được version-control; không bao giờ dùng private key production.

### 4.2. Tạo JWK và JWKS bằng Nimbus

~~~java
import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.RSAKey;

RSAKey signingJwk = new RSAKey.Builder(publicKey)
    .privateKey(privateKey)
    .keyID("orders-test-key-1")
    .algorithm(com.nimbusds.jose.JWSAlgorithm.RS256)
    .keyUse(com.nimbusds.jose.jwk.KeyUse.SIGNATURE)
    .build();

JWKSet publicJwkSet =
        new JWKSet(signingJwk.toPublicJWK());

String jwksJson = publicJwkSet.toString();
~~~

Khi dựng public JWKS, dùng `toPublicJWK()` trước khi serialize. Không serialize `signingJwk` đầy đủ vì object đó có private key.

Stub endpoint:

~~~java
identityServer.enqueue(new MockResponse()
    .setHeader("Content-Type", "application/json")
    .setBody(publicJwkSet.toString()));
~~~

Nếu dùng dispatcher, trả JWKS cho path `/oauth2/jwks` và metadata cho discovery path; đừng dựa vào thứ tự queue response khi test có thể phát nhiều request.

### 4.3. Ký access token cho Resource Server

`NimbusJwtEncoder` có thể ký JWT bằng JWK source chứa private key test:

~~~java
JWKSource<SecurityContext> jwkSource =
        new ImmutableJWKSet<>(new JWKSet(signingJwk));

JwtEncoder encoder = new NimbusJwtEncoder(jwkSource);

Instant now = Instant.now();
JwtClaimsSet claims = JwtClaimsSet.builder()
    .issuer(issuer)
    .subject("alice-42")
    .audience(List.of("orders-api"))
    .issuedAt(now.minusSeconds(5))
    .notBefore(now.minusSeconds(5))
    .expiresAt(now.plusSeconds(300))
    .claim("scope", "orders.read")
    .build();

JwsHeader header = JwsHeader
    .with(SignatureAlgorithm.RS256)
    .keyId("orders-test-key-1")
    .build();

String token = encoder.encode(
    JwtEncoderParameters.from(header, claims)).getTokenValue();
~~~

Các imports cần dùng từ Nimbus và Spring Security JOSE:

~~~java
import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jose.jwk.source.ImmutableJWKSet;
import com.nimbusds.jose.jwk.source.JWKSource;
import com.nimbusds.jose.proc.SecurityContext;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.JwtClaimsSet;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.JwtEncoderParameters;
import org.springframework.security.oauth2.jwt.JwsHeader;
import org.springframework.security.oauth2.jwt.NimbusJwtEncoder;
~~~

Header `kid` phải khớp key ID trong JWKS. Nếu `kid` không khớp key nào, decoder không thể chọn signing key thích hợp và phải từ chối token.

### 4.4. Kiểm thử chữ ký và key selection

Các test cơ bản:

| Token | JWKS | Kết quả |
| --- | --- | --- |
| Ký bằng private key A, `kid=A` | Public key A | Signature pass |
| Ký bằng private key B, `kid=B` | Chỉ có public key A | Signature fail |
| Ký bằng A, `kid=unknown` | Public key A với `kid=A` | Không tìm thấy key theo `kid`; từ chối |
| Ký bằng A, `kid=A` | JWKS rỗng | Từ chối |
| `alg=none` | Có public RSA key | Từ chối |
| Ký bằng thuật toán không nằm trong allowlist | JWKS có key tương ứng | Từ chối theo decoder policy |

Không chỉ test JWT signature hợp lệ. Test `kid` sai và key không tin cậy giúp xác nhận decoder không tự chấp nhận token chỉ vì payload có claims đúng.

### 4.5. Nối metadata/JWKS server với Spring Resource Server

Với cấu hình Boot, có thể trỏ issuer về test server:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: ${TEST_ISSUER_URI}
~~~

Trong test, truyền giá trị động bằng `@DynamicPropertySource` hoặc test properties. Khi context khởi tạo, Spring/Nimbus sẽ discovery metadata rồi lấy JWKS theo `jwks_uri`.

Nếu test trực tiếp decoder:

~~~java
NimbusJwtDecoder decoder = NimbusJwtDecoder
    .withIssuerLocation(issuer)
    .build();

decoder.setJwtValidator(
    JwtValidators.createDefaultWithIssuer(issuer));
~~~

Với direct JWKS test:

~~~java
NimbusJwtDecoder decoder = NimbusJwtDecoder
    .withJwkSetUri(jwksUri)
    .jwsAlgorithm(SignatureAlgorithm.RS256)
    .build();

decoder.setJwtValidator(
    JwtValidators.createDefaultWithIssuer(issuer));
~~~

Hai cấu hình minh họa hai đường khởi tạo khác nhau. `withJwkSetUri` không tự discovery metadata; nếu cần issuer validation, vẫn gắn validator issuer rõ ràng.

### 4.6. Kiểm tra request thực sự tới JWKS

Sau khi gọi endpoint Resource Server bằng token JWT:

~~~java
RecordedRequest metadataRequest = identityServer.takeRequest();
RecordedRequest jwksRequest = identityServer.takeRequest();

assertThat(metadataRequest.getMethod()).isEqualTo("GET");
assertThat(metadataRequest.getPath()).contains("openid-configuration");
assertThat(jwksRequest.getMethod()).isEqualTo("GET");
assertThat(jwksRequest.getPath()).isEqualTo("/oauth2/jwks");
~~~

Đây là ví dụ khi metadata discovery được cấu hình và server queue response theo đúng thứ tự. Với dispatcher hoặc nhiều request đồng thời, kiểm tra request theo path thay vì giả định thứ tự. Có thể dùng `takeRequest(timeout, unit)` để tránh test treo vô hạn nếu server không nhận request.

## 5. Key rotation và JWKS cache

Key rotation là một trong những lý do quan trọng để dựng JWKS test server. Authorization Server có thể phát token bằng key mới trong khi Resource Server vẫn giữ JWKS cũ trong cache. Một thiết kế an toàn cần overlap window để các token ký bằng key cũ còn hiệu lực được xác minh trong lúc các instance cập nhật key set.

Ví dụ:

~~~text
Thời điểm t0:
  JWKS = [key-A]
  token-A được ký bằng private-A

Thời điểm t1:
  JWKS = [key-A, key-B]
  AS bắt đầu ký token mới bằng private-B

Thời điểm t2:
  Các Resource Server đã tải JWKS mới
  token-A và token-B đều xác minh được

Thời điểm t3:
  Token ký bằng key-A đã hết hạn + overlap window đã qua
  JWKS = [key-B]
~~~

### 5.1. Giữ key cũ trong thời gian overlap

Không xóa key A khỏi JWKS ngay khi bắt đầu ký bằng key B. Các access token đã phát hành bằng A vẫn có thể còn hạn. Nếu JWKS không còn A trong khi token A vẫn được chấp nhận, request hợp lệ sẽ bị 401.

Thời gian overlap cần xét:

- Thời hạn tối đa của access token cũ.
- Clock skew được Resource Server chấp nhận.
- JWKS cache TTL và thời gian refresh.
- Độ trễ propagation giữa các instance/region.
- Khả năng rollback về key cũ.

### 5.2. Mô phỏng rotation bằng dispatcher

Một test server có thể giữ JWKS hiện hành trong `AtomicReference`:

~~~java
AtomicReference<JWKSet> currentJwks =
        new AtomicReference<>(new JWKSet(keyA.toPublicJWK()));

identityServer.setDispatcher(new Dispatcher() {
    @Override
    public MockResponse dispatch(RecordedRequest request) {
        if ("/oauth2/jwks".equals(request.getPath())) {
            return new MockResponse()
                .setHeader("Content-Type", "application/json")
                .setHeader("Cache-Control", "public, max-age=5")
                .setBody(currentJwks.get().toString());
        }
        return new MockResponse().setResponseCode(404);
    }
});
~~~

Trong test, thay JWKS:

~~~java
currentJwks.set(new JWKSet(
    keyA.toPublicJWK(),
    keyB.toPublicJWK()));
~~~

Sau đó ký token mới bằng private key B với `kid` riêng. Khi decoder cần refresh JWKS theo cache/unknown-kid behavior, token B phải được xác minh nếu public key B đã được publish.

Đoạn code minh họa stateful fixture; các biến `keyA`/`keyB` là JWK test được tạo riêng. Để test deterministic, cấu hình cache có TTL biết trước hoặc tạo decoder mới cho mỗi scenario. Không dựa vào `Thread.sleep(5000)` để hy vọng cache tự hết hạn.

### 5.3. Test rotation theo các mốc

| Scenario | JWKS | Token | Kỳ vọng |
| --- | --- | --- | --- |
| Trước rotation | A | token-A | Pass |
| JWKS có overlap | A + B | token-A | Pass |
| JWKS có overlap | A + B | token-B | Pass sau khi decoder biết key B |
| Sau overlap | B | token-B | Pass |
| Sau overlap | B | token-A còn hạn | Fail nếu A đã bị loại khỏi key set/cache đã refresh; đây là tín hiệu overlap quá ngắn nếu token vẫn phải được chấp nhận |
| JWKS endpoint lỗi tạm thời | Cache có A | token-A | Kết quả phụ thuộc cache còn hiệu lực; kiểm tra đúng policy và không giả định luôn pass/fail |

### 5.4. Hiểu cache khi viết test

Decoder có thể cache JWK Set. Vì vậy:

- JWKS server đổi response không có nghĩa decoder thấy key mới ngay lập tức.
- Token có `kid` chưa biết có thể kích hoạt refresh tùy thư viện/version và cache implementation.
- Một decoder mới có thể tải key set ngay cả khi decoder cũ vẫn dùng cache cũ.
- HTTP `Cache-Control` và cache được cấu hình trong decoder cần được kiểm tra theo đúng stack.
- Test nên kiểm soát cache/TTL hoặc dùng decoder mới để cô lập scenario.

Không assert một con số request JWKS cố định nếu cache policy chưa được cấu hình rõ. Nếu cần kiểm thử cache behavior, hãy cấu hình cache có clock/test control hoặc test riêng lớp cache.

### 5.5. Kiểm tra private key không bị publish

Ngoài việc ký được token, test fixture có thể kiểm tra public JWKS JSON không chứa private parameters:

~~~java
String jwks = new JWKSet(keyA.toPublicJWK()).toString();

assertThat(jwks).doesNotContain("\"d\"");
assertThat(jwks).doesNotContain("\"p\"");
assertThat(jwks).doesNotContain("\"q\"");
~~~

Đây là kiểm tra bảo vệ fixture; public JWKS phải chỉ chứa public material. Không serialize JWK có private parameters lên endpoint test chỉ để tiện cho encoder.

## 6. Dựng token introspection server cho opaque token

Opaque access token không tự chứa claims có thể xác minh cục bộ như JWT. Resource Server gửi token tới **introspection endpoint** để Authorization Server trả metadata về trạng thái và quyền của token.

RFC 7662 quy định request introspection bằng HTTP POST với tham số form `token`. Endpoint thường yêu cầu client authentication; response có `active` và có thể có `scope`, `sub`, `aud`, `iss`, `exp`, `client_id` cùng các claims khác theo hợp đồng.

Request minh họa:

~~~http
POST /oauth2/introspect HTTP/1.1
Host: identity.example.test
Authorization: Basic <client-credentials>
Content-Type: application/x-www-form-urlencoded

token=opaque-token-value
~~~

Response active:

~~~json
{
  "active": true,
  "scope": "orders.read orders.cancel",
  "client_id": "shop-web",
  "sub": "alice-42",
  "aud": ["orders-api"],
  "iss": "https://identity.example.test/realms/shop",
  "exp": 1893459600,
  "username": "alice"
}
~~~

Response inactive:

~~~json
{
  "active": false
}
~~~

`active=false` có nghĩa token không được coi là active theo Authorization Server. Không được tạo Authentication chỉ vì request có một chuỗi token.

### 6.1. Cấu hình opaque token Resource Server

Ví dụ Servlet:

~~~java
@Bean
SecurityFilterChain api(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyRequest().authenticated())
        .oauth2ResourceServer(resourceServer -> resourceServer
            .opaqueToken(opaque -> opaque
                .introspectionUri(
                    "http://127.0.0.1:49152/oauth2/introspect")
                .introspectionClientCredentials(
                    "orders-api-test", "test-secret")))
        .build();
}
~~~

URL và client credentials trong ví dụ chỉ dành cho test. Trong ứng dụng thật, lấy secret từ secret manager hoặc cơ chế client authentication phù hợp.

Spring Security cũng cho phép cung cấp bean `OpaqueTokenIntrospector` tùy chỉnh. Cách này hữu ích khi cần wrap introspector mặc định để áp dụng policy bổ sung, metrics hoặc mapping principal theo contract.

### 6.2. Stub introspection response

Với MockWebServer:

~~~java
identityServer.enqueue(new MockResponse()
    .setHeader("Content-Type", "application/json")
    .setBody("""
        {
          "active": true,
          "scope": "orders.read",
          "sub": "alice-42",
          "aud": ["orders-api"],
          "iss": "https://identity.example.test/realms/shop"
        }
        """));
~~~

Trong test, gửi opaque token:

~~~java
mvc.perform(get("/api/orders")
        .header(HttpHeaders.AUTHORIZATION, "Bearer opaque-token-value"))
    .andExpect(status().isOk());
~~~

Nếu introspector được cấu hình đúng, Spring gửi POST đến endpoint, đọc response và tạo Authentication cho request. Cần kiểm tra request đã nhận để chắc chắn đúng token được gửi và đúng client authentication được dùng.

### 6.3. Xác minh form body và client authentication

Có thể lấy request:

~~~java
RecordedRequest request = identityServer.takeRequest();

assertThat(request.getMethod()).isEqualTo("POST");
assertThat(request.getPath()).isEqualTo("/oauth2/introspect");
assertThat(request.getHeader("Content-Type"))
    .contains("application/x-www-form-urlencoded");
assertThat(request.getBody().readUtf8())
    .contains("token=opaque-token-value");
~~~

Nếu client authentication dùng HTTP Basic, kiểm tra header theo test contract. Không hardcode secret production trong test assertion hoặc output log. Một số AS hỗ trợ `client_secret_post`, `private_key_jwt` hoặc mTLS; test phải phản ánh phương thức mà ClientRegistration/introspector đang dùng.

### 6.4. Scope và authority từ introspection

Spring Security mặc định chuyển scope trong introspection principal thành authorities có prefix `SCOPE_`. Ví dụ:

~~~json
{
  "active": true,
  "scope": "orders.read orders.cancel"
}
~~~

Authorities mong đợi:

~~~text
SCOPE_orders.read
SCOPE_orders.cancel
~~~

Nếu Authorization Server trả claim quyền khác hoặc cấu trúc lồng nhau, dùng custom `OpaqueTokenIntrospector`/principal mapping theo contract. Đừng giả định mọi field của introspection response đều tự động trở thành GrantedAuthority.

### 6.5. Audience và issuer với opaque token

Không nên mặc định mọi introspector tự áp dụng cùng bộ kiểm tra issuer/audience như JWT decoder. Introspection response cung cấp claims theo contract của AS; nếu Resource Server cần ràng buộc `iss`, `aud`, token profile hoặc tenant cụ thể, hãy xác minh behavior của introspector đang dùng và bổ sung một wrapper/validator rõ ràng khi cần.

Ví dụ wrapper về mặt ý tưởng:

~~~java
final class ContractOpaqueTokenIntrospector
        implements OpaqueTokenIntrospector {

    private final OpaqueTokenIntrospector delegate;

    ContractOpaqueTokenIntrospector(OpaqueTokenIntrospector delegate) {
        this.delegate = delegate;
    }

    @Override
    public OAuth2AuthenticatedPrincipal introspect(String token) {
        OAuth2AuthenticatedPrincipal principal =
                delegate.introspect(token);

        String issuer = principal.getAttribute("iss");
        if (!"https://identity.example.test/realms/shop".equals(issuer)) {
            throw new BadOpaqueTokenException("Unexpected token issuer");
        }

        Object audience = principal.getAttribute("aud");
        if (!(audience instanceof Collection<?> values)
                || !values.contains("orders-api")) {
            throw new BadOpaqueTokenException("Unexpected token audience");
        }
        return principal;
    }
}
~~~

Đây là ví dụ contract wrapper; imports gồm `OpaqueTokenIntrospector`, `OAuth2AuthenticatedPrincipal`, `BadOpaqueTokenException` và `Collection`. Nếu AS không trả issuer/audience, cần thống nhất cách xác định resource binding với AS thay vì tự suy diễn từ `active=true`.

### 6.6. Introspection negative cases

| Scenario | Response/server behavior | Kỳ vọng |
| --- | --- | --- |
| Token active | `active=true`, scope đủ | Authentication thành công |
| Token inactive | `active=false` | 401 |
| Response thiếu `active` | Không đáp ứng RFC 7662 contract | Không chấp nhận |
| Response JSON lỗi | Body không parse được | Authentication thất bại |
| Client credentials sai | 401/403 từ introspection server | Resource Server không authenticate token |
| Endpoint 404/500 | HTTP error | Request không được coi là authenticated |
| Timeout/connection refused | Không kết nối được | Fail closed theo error handling |
| Scope thiếu | Active nhưng thiếu authority | Authentication có thể thành công; endpoint trả 403 |
| Audience sai | Active nhưng không dành cho API này | Custom contract validator phải từ chối nếu policy yêu cầu |
| Expired token | AS trả inactive hoặc policy custom từ chối | 401 |

Không trả `active=true` cho mọi token trong test fixture. Điều đó biến introspection server thành một fake trust provider quá dễ dãi và che lỗi truyền token.

## 7. Kiểm thử introspection failure và revocation

Introspection có một đặc tính khác JWT local validation: Resource Server phụ thuộc một HTTP service bên ngoài để biết trạng thái token. Test cần mô phỏng cả kết quả nghiệp vụ lẫn lỗi hạ tầng.

### 7.1. Token inactive và token không tồn tại

Khi token không còn hiệu lực, AS trả:

~~~json
{
  "active": false
}
~~~

Resource Server phải từ chối authentication. Dùng hai opaque token riêng trong test:

~~~text
opaque-active-001   -> active=true
opaque-revoked-002  -> active=false
~~~

Một dispatcher có thể chọn response dựa trên form body:

~~~java
identityServer.setDispatcher(new Dispatcher() {
    @Override
    public MockResponse dispatch(RecordedRequest request) {
        if (!"/oauth2/introspect".equals(request.getPath())) {
            return new MockResponse().setResponseCode(404);
        }

        String body = request.getBody().readUtf8();
        if (body.contains("token=opaque-active-001")) {
            return jsonResponse("""
                {"active":true,"scope":"orders.read","sub":"alice-42"}
                """);
        }
        if (body.contains("token=opaque-revoked-002")) {
            return jsonResponse("{\"active\":false}");
        }
        return jsonResponse("{\"active\":false}");
    }
});
~~~

`jsonResponse` là helper của test trả về `MockResponse` có `Content-Type: application/json`. Trong code thực, parse form body bằng decoder URL-encoded thay vì chỉ tìm chuỗi con nếu token có ký tự cần encode.

### 7.2. Revocation giữa hai request

Test một vòng đời token:

1. Introspection server trả `active=true`.
2. Gửi request đầu tiên, Resource Server cho phép.
3. Thay state của test server thành `active=false`.
4. Gửi request thứ hai bằng cùng opaque token.
5. Xác nhận request thứ hai bị từ chối theo behavior của introspector/cache đang dùng.

Không mặc định thay đổi response ở server sẽ được nhìn thấy ngay nếu ứng dụng có cache introspection tùy chỉnh. Nếu có cache, test phải kiểm tra TTL, invalidation và revocation delay. Nếu không có cache, mỗi request thường tạo một introspection call; hãy kiểm tra bằng request recorder.

### 7.3. Lỗi transport và HTTP

Các trường hợp nên dựng riêng:

- HTTP 401/403 từ introspection endpoint vì client authentication không hợp lệ.
- HTTP 404 vì endpoint URI sai.
- HTTP 429 vì rate limit.
- HTTP 500/503 vì Authorization Server tạm thời lỗi.
- Response chậm hơn client timeout.
- Connection reset hoặc server đóng socket giữa response.
- JSON bị cắt cụt hoặc sai kiểu dữ liệu.

Không biến lỗi introspection thành một principal mặc định. Nếu Resource Server không thể xác minh opaque token, request không được coi là authenticated. Error response công khai nên giữ thông tin tối thiểu, trong khi logs/metrics nội bộ phân loại được lỗi transport, client authentication và inactive token.

### 7.4. Timeout cần có giới hạn

Test timeout nên đặt ngưỡng rõ ràng cho HTTP client của introspector và test suite:

~~~java
identityServer.enqueue(new MockResponse()
    .setHeadersDelay(2, TimeUnit.SECONDS)
    .setHeader("Content-Type", "application/json")
    .setBody("{\"active\":true,\"scope\":\"orders.read\"}"));
~~~

Ví dụ này mô phỏng server trả headers chậm. Client timeout cần nhỏ hơn thời gian delay để test lỗi timeout. Không dùng delay dài để kiểm thử; một vài giây là đủ và test method nên có timeout để suite không bị treo.

### 7.5. Không ghi token thật vào request log

MockWebServer giữ request body để assertion. Trong test fixture chỉ dùng token giả, không dùng access token từ môi trường dev/staging. Nếu test framework in request khi fail, tránh token value có ý nghĩa hoặc secret thật trong output.

## 8. Dùng Testcontainers khi cần IdP thật

MockWebServer/WireMock phù hợp để test contract HTTP và các trường hợp lỗi có kiểm soát. Khi cần xác nhận tương tác với một Authorization Server thực tế, có thể chạy IdP trong Testcontainers.

Ví dụ khung:

~~~java
@Testcontainers
@SpringBootTest
class RealIdentityProviderIntegrationTest {

    @Container
    static final GenericContainer<?> identityProvider =
        new GenericContainer<>("example-identity-server:test")
            .withExposedPorts(8080)
            .waitingFor(Wait.forHttp("/health/ready"));

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add("spring.security.oauth2.resourceserver.jwt.issuer-uri",
            RealIdentityProviderIntegrationTest::issuer);
    }

    static String issuer() {
        return "http://" + identityProvider.getHost() + ":"
            + identityProvider.getMappedPort(8080) + "/realms/test";
    }
}
~~~

Đây là skeleton; image, port, health endpoint và issuer path phải theo IdP được chọn. Không dùng image placeholder này như một IdP có sẵn. Cần cấu hình realm/client/key/metadata test trong container trước khi Spring context khởi tạo.

Testcontainers hữu ích khi muốn kiểm tra discovery endpoint thực tế của IdP, cách IdP publish JWKS và `kid`, token profile/claims mà IdP phát hành, introspection client authentication, key rotation/revocation theo tính năng thật của IdP.

Nhược điểm là test chậm và phụ thuộc Docker/image availability. Không cần khởi động container thật cho mọi test negative case; giữ các lỗi HTTP chi tiết ở MockWebServer/WireMock.

## 9. Vòng đời tài nguyên test và Spring ApplicationContext

Một integration test có thể tạo nhiều tài nguyên cùng lúc:

| Tài nguyên | Khởi tạo | Cleanup |
| --- | --- | --- |
| MockWebServer/WireMock | BeforeAll/JUnit extension | Shutdown/stop |
| Testcontainers | Container extension | Stop container |
| RSA/EC key pair | Test fixture setup | Giải phóng reference; không publish private key |
| JWKS mutable state | BeforeEach hoặc fixture reset | Reset về key set ban đầu |
| Introspection response state | BeforeEach | Reset token status/response |
| Executor/scheduler | Test configuration | Shutdown và await termination |
| Temporary directory | JUnit `@TempDir` | JUnit tự dọn |
| HTTP client/connection pool | Spring bean/test fixture | Đóng khi context kết thúc |
| Cache | Test setup | Clear hoặc tạo cache mới |

### 9.1. Dùng lifecycle hook phù hợp

Thông thường:

- `@BeforeAll`: khởi động server dùng chung cho class, tạo key fixture.
- `@BeforeEach`: reset JWKS/introspection scenario, request log và mutable state.
- `@AfterEach`: xóa state riêng của test nếu không được reset ở lần kế tiếp.
- `@AfterAll`: dừng server, container và executor.

JUnit extension có thể quản lý start/stop để giảm code trong test class. Dù dùng extension hay hook, bảo đảm resource cleanup chạy cả khi assertion fail hoặc test bị exception.

### 9.2. Spring Test context cache và server lifetime

Spring Test có thể cache ApplicationContext để tái sử dụng giữa các test class có cấu hình tương thích. Điều này tạo một rủi ro: test class đóng MockWebServer trong `@AfterAll`, nhưng context còn được cache và test class khác dùng lại decoder/introspector trỏ tới port đã đóng.

Các cách xử lý:

- Giữ test server sống lâu bằng một shared fixture có lifecycle tương thích với context cache.
- Dùng context riêng và đánh dấu `@DirtiesContext` khi cần đóng dependency cùng context.
- Dùng JUnit extension quản lý resource theo scope phù hợp.
- Không stop server trước khi các bean/client trong context dùng xong.

Đừng mặc định `@AfterAll` luôn đồng nghĩa Spring context đã bị hủy. Test server lifetime và context lifetime cần được thiết kế cùng nhau.

### 9.3. Cách ly state khi chạy song song

Test chạy song song có thể làm lẫn:

- Response queue của MockWebServer.
- JWKS state đang rotation.
- Introspection token state active/revoked.
- Request recorder/assertion.
- Cache decoder dùng chung.
- Port và test properties.

Ưu tiên server per class hoặc per test với state độc lập. Nếu dùng server chung, route response theo path và token/test identifier; không phụ thuộc thứ tự request. Có thể tắt parallel execution cho nhóm test dùng mutable singleton fixture nếu chưa thể cách ly an toàn.

### 9.4. Tránh test phụ thuộc thứ tự

Không viết:

~~~java
server.enqueue(activeResponse);
server.enqueue(inactiveResponse);
~~~

rồi giả định test A luôn chạy trước test B. Khi JUnit đổi thứ tự hoặc chạy song song, response có thể bị tiêu thụ sai. Dùng dispatcher theo request body/path hoặc reset queue/state trong `@BeforeEach`.

### 9.5. Readiness và cleanup

Một test server được start không có nghĩa ứng dụng giả lập đã sẵn sàng. Nếu chạy container:

- Dùng health/readiness check có timeout.
- Chờ endpoint metadata/JWKS thực sự trả response.
- Chỉ sau đó mới khởi tạo Spring context.
- Khi kết thúc, đóng server/container và các executor.

Không dùng vòng lặp vô hạn hoặc `Thread.sleep()` cố định để chờ. Readiness check phải có timeout và thông báo rõ endpoint nào không sẵn sàng.



## 10. Kịch bản tích hợp JWT end-to-end

Một test hoàn chỉnh cho JWT nên xác nhận cả HTTP request, discovery/JWKS và authorization endpoint. Luồng ví dụ:

1. Start MockWebServer trên port động.
2. Tạo RSA key pair A và public JWKS chứa key A.
3. Stub metadata với issuer đúng và `jwks_uri` trỏ về server.
4. Stub JWKS endpoint trả public key A.
5. Cấu hình Spring Resource Server bằng `issuer-uri` động.
6. Ký JWT bằng private key A, `kid` đúng, issuer/audience/scope đúng.
7. Gửi JWT qua MockMvc bằng Authorization header.
8. Xác nhận response thành công và request metadata/JWKS đã đến server.
9. Gửi token ký bằng key B hoặc sai audience và xác nhận bị từ chối.
10. Dừng Spring context/test server theo lifecycle đã thiết kế.

### 10.1. Ví dụ test request JWT

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class JwksBackedResourceServerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void acceptsTokenSignedByKeyPublishedInJwks() throws Exception {
        String token = tokenSignedByKeyA();

        mvc.perform(get("/api/orders")
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + token))
            .andExpect(status().isOk());
    }

    @Test
    void rejectsTokenSignedByKeyNotPublishedInJwks() throws Exception {
        String token = tokenSignedByKeyB();

        mvc.perform(get("/api/orders")
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + token))
            .andExpect(status().isUnauthorized());
    }
}
~~~

Các helper `tokenSignedByKeyA()` và `tokenSignedByKeyB()` ký JWT với cùng claim contract nhưng private keys khác nhau. JWKS server chỉ publish public key A. Bài test này kiểm tra chữ ký qua JWKS, không chỉ claim mapping.

### 10.2. Test discovery metadata mismatch

Đặt metadata `issuer` khác issuer đã cấu hình, rồi khởi tạo decoder hoặc gọi protected endpoint. Kỳ vọng discovery/decoder thất bại; không sửa claim `iss` trong token để che mismatch.

Test riêng trường hợp `jwks_uri` trỏ đến endpoint 404 hoặc timeout. Điều này giúp phân biệt lỗi discovery với lỗi verify token.

### 10.3. Test metadata discovery và direct JWKS riêng biệt

Không dùng cùng một test để tuyên bố cả hai đường hoạt động:

- Test A dùng `issuer-uri` và yêu cầu metadata discovery.
- Test B dùng `jwk-set-uri` trực tiếp và vẫn gắn issuer validator nếu contract cần.

Khi test A thất bại nhưng test B pass, lỗi có thể nằm ở discovery path/metadata response. Khi cả hai fail, kiểm tra JWKS, signing key và token claims.

## 11. Kịch bản tích hợp opaque token end-to-end

Một test opaque token hoàn chỉnh nên:

1. Start introspection server trên port động.
2. Cấu hình Resource Server với đúng introspection URI và client authentication test.
3. Stub response `active=true` với scope/audience/issuer phù hợp.
4. Gửi opaque token trong Authorization header.
5. Kiểm tra request introspection là POST, form body chứa đúng token và client auth đúng.
6. Xác nhận scope tạo ra authority cần thiết.
7. Chuyển token thành inactive và gửi lại.
8. Xác nhận Resource Server từ chối.

### 11.1. Active token được chấp nhận

~~~java
@Test
void acceptsActiveOpaqueTokenWithRequiredScope() throws Exception {
    introspectionFixture.respondFor(
        "opaque-active-001",
        """
        {
          "active": true,
          "scope": "orders.read",
          "sub": "alice-42",
          "aud": ["orders-api"],
          "iss": "https://identity.example.test/realms/shop"
        }
        """);

    mvc.perform(get("/api/orders")
            .header(HttpHeaders.AUTHORIZATION,
                "Bearer opaque-active-001"))
        .andExpect(status().isOk());
}
~~~

`introspectionFixture` là fixture do test định nghĩa để cấu hình dispatcher/state; nó không phải class Spring Security có sẵn.

### 11.2. Inactive token bị từ chối

~~~java
@Test
void rejectsInactiveOpaqueToken() throws Exception {
    introspectionFixture.respondFor(
        "opaque-revoked-002",
        "{\"active\":false}");

    mvc.perform(get("/api/orders")
            .header(HttpHeaders.AUTHORIZATION,
                "Bearer opaque-revoked-002"))
        .andExpect(status().isUnauthorized());
}
~~~

### 11.3. Active nhưng thiếu scope

~~~java
@Test
void activeOpaqueTokenWithoutRequiredScopeIsForbidden()
        throws Exception {
    introspectionFixture.respondFor(
        "opaque-profile-only",
        """
        {
          "active": true,
          "scope": "profile.read",
          "sub": "alice-42",
          "aud": ["orders-api"]
        }
        """);

    mvc.perform(get("/api/orders")
            .header(HttpHeaders.AUTHORIZATION,
                "Bearer opaque-profile-only"))
        .andExpect(status().isForbidden());
}
~~~

Token active nghĩa là authentication có thể thành công; thiếu scope là authorization failure. Không assert 401 cho mọi trường hợp introspection response không cho phép endpoint.

## 12. Chẩn đoán lỗi trong test server

| Triệu chứng | Nguyên nhân thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| Context không khởi tạo khi dùng `issuer-uri` | Discovery URL sai, metadata server chưa sẵn sàng, issuer mismatch | Request path, response body, issuer chính xác |
| JWT luôn 401 dù claims đúng | JWKS không có key phù hợp, `kid` sai, signature sai, alg không được phép | Đọc JOSE header, JWKS public key, key ID |
| JWT đầu tiên pass, token key mới fail | Decoder còn cache JWKS cũ hoặc key mới chưa được publish | Cache TTL, refresh behavior, overlap set |
| Token cũ fail ngay sau rotation | Key cũ bị xóa quá sớm hoặc cache/instance chưa đồng bộ | Token expiry, skew, overlap window |
| Metadata pass nhưng JWKS request không xuất hiện | Decoder chưa được gọi hoặc đang dùng cache | Trigger protected request, kiểm tra decoder lifecycle |
| JWKS request xuất hiện nhiều lần | Cache chưa được cấu hình/đã hết hạn, nhiều decoder instance | Cache scope, context count, key selection |
| Opaque token luôn 401 | `active=false`, introspection URI/client auth sai, response lỗi | Recorded POST, body, auth scheme, response |
| Opaque token pass dù scope không đúng | Route không yêu cầu scope hoặc test stub cấp scope nhầm | Security rule, introspection fixture |
| Revoked token vẫn pass | Cache introspection còn hiệu lực hoặc fixture chưa đổi response | Cache TTL/invalidation, request recorder |
| Test pass riêng lẻ nhưng fail cả suite | Server/state/cache bị chia sẻ hoặc cleanup quá sớm | Context cache, parallel mode, dispatcher reset |
| Test treo | Request server không phản hồi hoặc `takeRequest()` chờ vô hạn | Timeout HTTP, bounded request wait, server readiness |
| Test chạy trên CI fail ngẫu nhiên | Port cố định, race startup, readiness phụ thuộc thời gian | Dynamic port, lifecycle hook, readiness timeout |

## 13. Những nguyên tắc bảo mật khi dựng identity test server

### 13.1. Chỉ dùng key và token test

- Tạo private key riêng cho test.
- JWKS endpoint chỉ trả public key.
- Token test có subject giả và thời hạn ngắn.
- Không đọc token/private key từ biến môi trường production.
- Không in Authorization header hoặc introspection request body vào log khi test fail.

### 13.2. Metadata/JWKS URL phải nằm trong trust boundary

Resource Server không nên lấy `jwks_uri` từ một JWT chưa xác minh hoặc từ dữ liệu do caller điều khiển. Issuer và metadata source phải được cấu hình/allowlist. Trong test, URL trỏ về loopback/dynamic port do test fixture quản lý.

Khi chạy test container, dùng network riêng và không expose test identity server ra mạng công cộng. Nếu test cần HTTPS, dùng certificate test và trust store test riêng; không tắt TLS validation để làm request pass.

### 13.3. Test fail closed

Các lỗi sau không được biến thành authentication thành công:

- Metadata không tin cậy hoặc sai issuer.
- JWKS không tải được và không có cache hợp lệ.
- Không tìm được key hoặc signature sai.
- Introspection response inactive hoặc không hợp lệ.
- Introspection endpoint không sẵn sàng.
- Required claims không đáp ứng contract.

Nếu cache còn một key set hợp lệ, behavior khi JWKS endpoint tạm thời lỗi phụ thuộc cache policy. Test cần phản ánh chính sách đã chọn, không tự giả định luôn fail closed tức thì nếu decoder có thể dùng cache hợp lệ.

## 14. Checklist kiểm chứng tích hợp

### Metadata

- [ ] Issuer trong config, metadata và token claim khớp chính xác.
- [ ] Discovery path đúng với OIDC Discovery/RFC 8414 và issuer path.
- [ ] Metadata có `jwks_uri` hợp lệ.
- [ ] Kiểm tra metadata 404, 500, timeout, JSON lỗi và issuer mismatch.
- [ ] Có test riêng cho discovery và direct JWKS URI.

### JWKS/JWT

- [ ] Tạo key pair riêng cho test.
- [ ] JWKS chỉ chứa public keys.
- [ ] Token được ký bằng private key đúng và có `kid` tương ứng.
- [ ] Test key không tin cậy, `kid` thiếu/sai, JWKS rỗng và algorithm không được phép.
- [ ] Test cache và key rotation với overlap window.
- [ ] Không giả định JWKS update có hiệu lực ngay lập tức.
- [ ] Test token cũ và token mới trong giai đoạn rotation.

### Introspection

- [ ] Request là POST form với token parameter.
- [ ] Client authentication khớp cấu hình.
- [ ] Response `active=true` và `active=false` đều được test.
- [ ] Test thiếu `active`, JSON lỗi, HTTP error và timeout.
- [ ] Scope mapping được kiểm tra.
- [ ] Issuer/audience/tenant được kiểm tra theo contract nếu cần.
- [ ] Test revocation và cache invalidation.

### Resource lifecycle

- [ ] Dùng port động.
- [ ] Server sẵn sàng trước Spring context.
- [ ] Test state được reset giữa các test.
- [ ] Không phụ thuộc thứ tự chạy hoặc shared response queue.
- [ ] Server/container/executor được đóng khi kết thúc.
- [ ] Xử lý Spring ApplicationContext cache và server lifetime.
- [ ] Parallel tests được cách ly.
- [ ] Có bounded timeout cho HTTP request/readiness.

## 15. Tình huống thực hành

**A.** Resource Server dùng `issuer-uri`, nhưng test chỉ stub `/oauth2/jwks`. Test có chứng minh metadata discovery không?

Không. Cần stub đúng discovery metadata endpoint, trả issuer và `jwks_uri`, sau đó xác nhận decoder thực sự gọi JWKS.

**B.** Token được ký đúng bằng key A nhưng header `kid` là key B. Có nên chấp nhận vì public key A có trong JWKS?

Không. `kid` giúp decoder chọn key. Nếu không tìm được key phù hợp với header, token phải bị từ chối.

**C.** JWKS endpoint đã thêm key B nhưng token B vẫn 401 ngay sau đó. Nguyên nhân có thể là gì?

Decoder đang dùng JWK Set cache cũ hoặc chưa refresh. Kiểm tra cache TTL, unknown-key refresh behavior và đảm bảo key B được publish trước khi AS ký token bằng B.

**D.** Có thể xóa key A khỏi JWKS ngay khi bắt đầu ký bằng B không?

Không nếu token ký bằng A vẫn còn hạn và cần được chấp nhận. Giữ key cũ trong overlap window phù hợp với token lifetime, skew, cache và propagation.

**E.** Introspection trả `active=true` nhưng scope chỉ có `profile.read`; endpoint yêu cầu `SCOPE_orders.read`. Kết quả nên là gì?

Authentication có thể thành công, nhưng authorization phải trả 403 vì thiếu scope.

**F.** Introspection endpoint timeout. Resource Server có thể cho phép request vì token đã được gửi lên không?

Không. Không xác minh được opaque token thì không thể tạo authenticated principal chỉ từ token string.

**G.** Test class đóng MockWebServer ở `@AfterAll`, nhưng class khác dùng lại Spring context và request tới port cũ. Vì sao?

Spring Test có thể cache ApplicationContext sau khi class đầu kết thúc. Server lifetime ngắn hơn context lifetime. Dùng shared fixture hoặc hủy context phù hợp trước khi stop server.

**H.** Test chạy riêng lẻ pass nhưng chạy song song fail do response active/inactive bị tráo. Cần thay đổi gì?

Dùng dispatcher dựa trên token/path, fixture riêng hoặc reset state; không dùng response queue dùng chung phụ thuộc thứ tự.

**I.** Có cần Testcontainers cho mọi test JWKS/introspection không?

Không. MockWebServer/WireMock phù hợp cho contract và negative cases. Dùng IdP container khi cần xác minh hành vi thực tế của nhà cung cấp.

**J.** Public JWKS có thể chứa private RSA parameter `d` để test ký token tiện hơn không?

Không. Encoder giữ private key trong fixture; endpoint JWKS chỉ publish `toPublicJWK()`.

---

## Kết luận

Máy chủ JWKS, metadata và introspection thử nghiệm giúp kiểm tra đúng ranh giới HTTP giữa Spring Security Resource Server và Authorization Server. Với JWT, test cần dựng metadata discovery hoặc JWKS URI, tạo cặp khóa riêng, publish public JWK, ký token và kiểm tra chữ ký, `kid`, issuer, audience cùng key rotation/cache. Với opaque token, test cần mô phỏng RFC 7662 POST, client authentication, response active/inactive, scope mapping, revocation và lỗi transport.

Vòng đời test server cũng là một phần của tính đúng đắn. Dùng port động, readiness có timeout, fixture cô lập, reset state và cleanup rõ ràng; đồng thời đồng bộ lifetime của server với Spring ApplicationContext cache. Test phải phân biệt lỗi token với lỗi hạ tầng, tránh phụ thuộc thứ tự và không cho phép một dependency không sẵn sàng biến thành authentication thành công.

## Tài liệu tham khảo

1. [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
2. [Spring Security — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html)
3. [Spring Security — Testing OAuth 2.0 Resource Servers](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html)
4. [OpenID Connect Discovery 1.0 — Provider Configuration](https://openid.net/specs/openid-connect-discovery-1_0.html)
5. [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414.html)
6. [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517.html)
7. [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515.html)
8. [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662.html)
9. [OkHttp MockWebServer](https://square.github.io/okhttp/5.x/mockwebserver/)
10. [WireMock Documentation](https://wiremock.org/docs/)
11. [Testcontainers for Java](https://java.testcontainers.org/)


