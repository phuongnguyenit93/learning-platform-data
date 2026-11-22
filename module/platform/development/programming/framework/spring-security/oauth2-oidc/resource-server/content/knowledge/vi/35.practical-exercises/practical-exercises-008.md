# Luân chuyển khóa trong môi trường thử nghiệm khi token cũ vẫn còn hạn

## 1. Bài toán: đổi signing key mà không làm hỏng token đang lưu hành

JWT access token được ký bằng private key của Authorization Server (AS). Resource Server (RS) lấy public key từ JWKS endpoint để xác minh chữ ký. Khi AS thay signing key, token mới được ký bằng key mới, trong khi các token đã phát hành bằng key cũ có thể vẫn còn hạn.

Giả sử AS đang ký bằng khóa **K1**. Một ứng dụng vừa nhận access token T1, có thời hạn thêm 12 phút. Sau đó đội vận hành muốn chuyển sang khóa **K2**. Nếu xóa public key K1 khỏi JWKS ngay khi bắt đầu ký bằng K2, một RS chưa cache K1 hoặc vừa refresh JWKS có thể không xác minh được T1. Người dùng đang có token hợp lệ sẽ nhận 401 dù token chưa hết hạn.

Cách luân chuyển thông thường là công bố public key mới trước, giữ đồng thời public key cũ và mới trong một khoảng overlap, chuyển AS sang ký bằng key mới, rồi chỉ gỡ key cũ sau khi các token được ký bằng key đó không còn hợp lệ.

Trong bài thực hành này, ta mô phỏng quy trình bằng hai cặp RSA key, một JWKS endpoint thử nghiệm và một Spring Security JWT decoder. Ta kiểm tra cả token cũ lẫn token mới trong thời gian overlap, mô phỏng việc gỡ key cũ và quan sát khác biệt giữa decoder đã cache khóa với một instance mới.

**Nguyên tắc quan trọng:** token cũ còn hạn phải tiếp tục xác minh được trong một đợt rotation bình thường. Việc thay signing key không tự làm token cũ hết hạn và cũng không tự thu hồi token.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích quan hệ giữa private signing key, public verification key, kid và JWKS.
2. Lập timeline publish, overlap, switch và retire key.
3. Tạo hai cặp RSA key cho môi trường thử nghiệm.
4. Dựng JWKS endpoint có thể thay đổi nội dung trong lúc test.
5. Phát hành token cũ bằng K1 và token mới bằng K2.
6. Dùng cùng một JwtDecoder để xác minh token qua giai đoạn rotation.
7. Hiểu cache JWKS và hành vi khi decoder gặp unknown kid.
8. Kiểm tra token cũ còn hạn, token hết hạn và token dùng key đã bị gỡ.
9. Mô phỏng nhiều Resource Server instance có cache khác nhau.
10. Phân biệt rotation định kỳ với xử lý khẩn cấp khi private key bị compromise.

---

## 2. Các thành phần trong bài lab

### 2.1. Sơ đồ

~~~mermaid
flowchart TD
    AS[Authorization Server test] -->|Ký token mới bằng K2| T2[Access token mới]
    AS -->|Đã phát hành trước đó bằng K1| T1[Access token cũ]
    JWKS[JWKS endpoint test] -->|Public K1 + K2| RS1[Resource Server A]
    JWKS -->|Public K1 + K2| RS2[Resource Server B]
    T1 --> RS1
    T2 --> RS1
    T1 --> RS2
    T2 --> RS2
    RS1 --> V1[Signature + issuer + audience + time]
    RS2 --> V2[Signature + issuer + audience + time]
~~~

AS giữ private key để ký. JWKS chỉ công bố public key. RS không cần và không được nhận private key của AS.

Trong bài lab, một tiến trình test đóng vai AS và một HTTP server cục bộ đóng vai JWKS endpoint. Điều này giúp thay đổi danh sách public key có thể kiểm soát được. Không dùng private key thật hoặc endpoint production trong thử nghiệm.

### 2.2. Những giá trị cố định

Dùng một issuer và một audience xuyên suốt bài lab:

~~~text
Issuer:
https://issuer.test.example

Audience:
orders-api

JWKS URI:
http://127.0.0.1:<test-port>/jwks

Key cũ:
kid = rsa-key-1

Key mới:
kid = rsa-key-2

Algorithm:
RS256
~~~

JWKS URI dùng HTTP loopback chỉ để đơn giản hóa test cục bộ. Môi trường thật phải dùng HTTPS, xác minh TLS certificate và quản lý endpoint bằng cấu hình tin cậy.

Issuer không đổi khi rotation. Audience cũng không đổi. Việc luân chuyển signing key chỉ thay key dùng để ký và tập public key được công bố.

### 2.3. Trạng thái trước khi bắt đầu

Ban đầu:

- AS ký token bằng K1.
- JWKS chứa public K1.
- RS đã có thể tải public K1.
- Token T1 được ký bằng private K1 và còn hạn.
- K2 đã được tạo trong lab nhưng chưa được công bố.

| Thành phần | Trạng thái ban đầu |
|---|---|
| AS active signing key | K1 |
| JWKS | K1 |
| Resource Server cache | Có thể chứa K1 |
| Token T1 | Ký bằng K1, còn hạn |
| K2 | Chưa publish |

---

## 3. Timeline rotation đúng cách

### 3.1. Bốn giai đoạn

~~~mermaid
sequenceDiagram
    participant AS as Authorization Server
    participant J as JWKS endpoint
    participant RS as Resource Server
    participant C as Client

    Note over AS,J: Giai đoạn 1: K1 đang hoạt động
    AS->>C: Phát T1 ký bằng K1
    C->>RS: Gọi API với T1
    RS->>J: Tải JWKS chứa K1
    RS-->>C: API response

    Note over AS,J: Giai đoạn 2: Publish K2, giữ K1
    AS->>J: Công bố K1 + K2
    RS->>J: Refresh JWKS
    Note over RS: RS có thể xác minh cả K1 và K2

    Note over AS,J: Giai đoạn 3: Switch signer
    AS->>C: Phát T2 ký bằng K2
    C->>RS: Gọi API với T2
    RS-->>C: API response
    C->>RS: Gọi API với T1 còn hạn
    RS-->>C: API response

    Note over AS,J: Giai đoạn 4: Retire K1 sau overlap
    AS->>J: Gỡ K1, chỉ giữ K2
    RS->>J: Refresh theo cache policy
~~~

Quy trình gồm:

1. **Publish:** đưa public K2 vào JWKS cùng public K1.
2. **Warm-up/propagation:** cho các RS nhận biết K2.
3. **Switch:** AS bắt đầu ký token mới bằng private K2.
4. **Retire:** gỡ public K1 sau khi token ký bằng K1 hết thời hạn hợp lệ.

Không gỡ K1 ở bước publish. Cũng không bắt đầu ký K2 trước khi public K2 được công bố và các RS có cơ hội nhận key mới.

### 3.2. Tính thời điểm gỡ key cũ

Một cách tính bảo thủ:

\[
t_{remove(K1)} \geq t_{lastIssue(K1)} + maxTokenLifetime + clockSkew + propagationMargin
\]

Trong đó:

- **t_lastIssue(K1):** thời điểm cuối cùng AS phát hành token bằng K1.
- **maxTokenLifetime:** thời hạn access token tối đa có thể được cấp bằng K1.
- **clockSkew:** độ lệch đồng hồ mà RS cho phép.
- **propagationMargin:** khoảng dự phòng cho cache, nhiều instance và quá trình triển khai.

Nếu hệ thống ghi nhận được thời điểm hết hạn lớn nhất của mọi token K1 đã phát hành, có thể dùng mốc đó thay cho phép tính bảo thủ từ thời điểm phát hành cuối cùng:

\[
t_{remove(K1)} \geq max(exp_{K1}) + clockSkew + propagationMargin
\]

Không chỉ dựa vào TTL mặc định của client. Hãy tính theo chính sách token thực tế, gồm refresh flow có thể tiếp tục phát hành access token bằng K1 cho tới khi AS switch signer.

### 3.3. Ví dụ timeline

Giả sử:

| Sự kiện | Thời điểm minh họa |
|---|---|
| AS phát hành token cuối cùng bằng K1 | 10:00 |
| Maximum access-token lifetime | 20 phút |
| Allowed clock skew | 60 giây |
| Propagation/cache margin | 5 phút |
| Sớm nhất có thể retire K1 | Sau 10:26 |

Các con số chỉ minh họa. Hệ thống thật cần lấy maximum lifetime và clock skew từ cấu hình đang áp dụng. Nếu AS vẫn phát hành token K1 sau 10:00, phải tính lại mốc.

### 3.4. Token cũ không tự được ký lại

T1 đã được ký bằng K1. Khi AS chuyển sang K2:

- T1 vẫn giữ chữ ký của K1.
- T1 vẫn có kid của K1.
- T1 vẫn còn hạn cho tới exp, nếu các điều kiện khác hợp lệ.
- T2 được ký bằng K2 và mang kid của K2.

Không có thao tác nào thay chữ ký của T1 thành chữ ký K2. Nếu muốn token cũ không còn được dùng, cần cơ chế revoke/denylist hoặc rút ngắn vòng đời theo thiết kế; chỉ đổi active signing key không đủ.

---

## 4. Chuẩn bị project thử nghiệm

### 4.1. Dependency

Ví dụ Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
    implementation 'org.springframework.boot:spring-boot-starter-web'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Spring Security OAuth2 JOSE sử dụng Nimbus JOSE + JWT để xử lý JWT/JWK. Nếu test code import các lớp Nimbus nhưng build không expose dependency qua module đang dùng, khai báo test dependency tương ứng theo BOM của dự án thay vì tự ghim một phiên bản không tương thích.

Ví dụ import Nimbus thường dùng:

~~~java
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.JWSHeader;
import com.nimbusds.jose.JOSEObjectType;
import com.nimbusds.jose.crypto.RSASSASigner;
import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.KeyUse;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.SignedJWT;
~~~

### 4.2. Tạo hai cặp RSA key

Trong test, tạo K1 và K2 độc lập:

~~~java
static KeyPair generateRsaKeyPair() throws GeneralSecurityException {
    KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
    generator.initialize(2048);
    return generator.generateKeyPair();
}

KeyPair keyPair1 = generateRsaKeyPair();
KeyPair keyPair2 = generateRsaKeyPair();
~~~

Mỗi key pair gồm:

- Private key: chỉ dùng để ký token trong test.
- Public key: được đưa vào JWKS để Resource Server xác minh.

Không dùng lại cùng một cặp key cho hai kid. kid phải phân biệt hai khóa khác nhau.

### 4.3. Tạo public JWK

~~~java
static RSAKey publicJwk(KeyPair pair, String kid) {
    return new RSAKey.Builder((RSAPublicKey) pair.getPublic())
        .keyID(kid)
        .algorithm(JWSAlgorithm.RS256)
        .keyUse(KeyUse.SIGNATURE)
        .build();
}

RSAKey publicKey1 = publicJwk(keyPair1, "rsa-key-1");
RSAKey publicKey2 = publicJwk(keyPair2, "rsa-key-2");
~~~

JWKS chỉ chứa public JWK:

~~~java
String jwksWithK1 = new JWKSet(publicKey1).toString();

String jwksWithBoth = new JWKSet(
    List.of(publicKey1, publicKey2)
).toString();

String jwksWithK2 = new JWKSet(publicKey2).toString();
~~~

Không gọi toJSONString/toString trên JWK chứa private key để tạo response JWKS. Hãy tạo public JWK riêng bằng public key hoặc dùng toPublicJWK() trước khi serialize.

---

## 5. Dựng JWKS endpoint cục bộ có thể thay đổi

### 5.1. Vì sao cần endpoint động?

Để test rotation, ta cần thay response JWKS theo các giai đoạn:

- Ban đầu trả K1.
- Overlap trả K1 và K2.
- Sau retire chỉ trả K2.

Một HTTP endpoint trong test cho phép cập nhật nội dung JWKS bằng AtomicReference. Nimbus decoder sẽ lấy JWKS từ URL đó theo cơ chế cache của thư viện.

### 5.2. Ví dụ với JDK HttpServer

Đoạn sau là test fixture dùng JDK HttpServer:

~~~java
import com.sun.net.httpserver.HttpServer;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.io.OutputStream;
import java.util.concurrent.atomic.AtomicReference;

AtomicReference<String> currentJwks =
    new AtomicReference<>(jwksWithK1);

HttpServer jwksServer = HttpServer.create(
    new InetSocketAddress("127.0.0.1", 0),
    0
);

jwksServer.createContext("/jwks", exchange -> {
    byte[] body = currentJwks.get()
        .getBytes(StandardCharsets.UTF_8);

    exchange.getResponseHeaders().set(
        "Content-Type",
        "application/jwk-set+json"
    );

    exchange.sendResponseHeaders(200, body.length);

    try (OutputStream output = exchange.getResponseBody()) {
        output.write(body);
    }
});

jwksServer.start();

String jwksUri =
    "http://127.0.0.1:" +
    jwksServer.getAddress().getPort() +
    "/jwks";
~~~

Sau test, luôn dừng server:

~~~java
@AfterEach
void stopJwksServer() {
    if (jwksServer != null) {
        jwksServer.stop(0);
    }
}
~~~

Trong project modular, JDK HttpServer thuộc module jdk.httpserver. Nếu module descriptor của test không đọc module đó, cần khai báo module phù hợp hoặc dùng mock HTTP server mà project đã có.

### 5.3. Cập nhật JWKS theo từng giai đoạn

~~~java
// Trạng thái ban đầu
currentJwks.set(jwksWithK1);

// Publish K2, vẫn giữ K1
currentJwks.set(jwksWithBoth);

// Sau khi overlap kết thúc
currentJwks.set(jwksWithK2);
~~~

Thay đổi response tại endpoint không có nghĩa mọi RS instance lập tức thấy nội dung mới. Decoder có thể giữ JWKS trong cache. Bài lab phải kiểm tra cả cache hit, cache miss và instance mới.

---

## 6. Phát hành token bằng từng key

### 6.1. Tạo JWT có kid rõ ràng

Một access token cần có issuer, subject, audience, thời gian và scope. Header cần có kid trỏ tới key đã dùng ký.

~~~java
static String issueToken(
        KeyPair signingKey,
        String kid,
        Instant expiresAt) throws Exception {

    Instant now = Instant.now();

    JWSHeader header = new JWSHeader.Builder(JWSAlgorithm.RS256)
        .keyID(kid)
        .type(JOSEObjectType.JWT)
        .build();

    JWTClaimsSet claims = new JWTClaimsSet.Builder()
        .issuer("https://issuer.test.example")
        .subject("user-417")
        .audience("orders-api")
        .issueTime(Date.from(now.minusSeconds(5)))
        .expirationTime(Date.from(expiresAt))
        .claim("scope", "orders.read")
        .build();

    SignedJWT jwt = new SignedJWT(header, claims);

    jwt.sign(new RSASSASigner(
        (RSAPrivateKey) signingKey.getPrivate()
    ));

    return jwt.serialize();
}
~~~

Phát hành T1 bằng K1:

~~~java
String oldToken = issueToken(
    keyPair1,
    "rsa-key-1",
    Instant.now().plus(Duration.ofMinutes(15))
);
~~~

Phát hành T2 bằng K2:

~~~java
String newToken = issueToken(
    keyPair2,
    "rsa-key-2",
    Instant.now().plus(Duration.ofMinutes(15))
);
~~~

Trong test, thời gian có thể được điều khiển bằng Clock cố định để tránh test phụ thuộc thời điểm chạy. Ví dụ trên dùng Instant.now() cho dễ đọc; suite thực tế nên tạo helper nhận issuedAt và expiresAt rõ ràng.

### 6.2. Không thay kid mà giữ nguyên chữ ký

kid là metadata để chọn key, không phải chữ ký. Nếu đổi header kid từ rsa-key-1 sang rsa-key-2 mà không ký lại JWT bằng private K2, chữ ký sẽ không hợp lệ.

Token mới phải được ký thực sự bằng private key tương ứng với public key được công bố dưới kid mới.

### 6.3. Kiểm tra private key không xuất hiện trong JWKS

JWKS endpoint của Resource Server chỉ cần public verification keys. Test có thể parse response và xác nhận không có các private RSA parameters như d, p, q, dp, dq, qi.

Không log hoặc commit private key test. Dù chỉ là key thử nghiệm, hãy giữ nó trong memory hoặc thư mục test được quản lý và xóa theo vòng đời môi trường.

---

## 7. Cấu hình JwtDecoder dùng JWKS endpoint thử nghiệm

### 7.1. Decoder với algorithm và validators rõ ràng

~~~java
static JwtDecoder createDecoder(String jwksUri) {
    NimbusJwtDecoder decoder =
        NimbusJwtDecoder.withJwkSetUri(jwksUri)
            .jwsAlgorithm(SignatureAlgorithm.RS256)
            .build();

    OAuth2TokenValidator<Jwt> issuerAndTime =
        JwtValidators.createDefaultWithIssuer(
            "https://issuer.test.example"
        );

    OAuth2TokenValidator<Jwt> audience = jwt -> {
        if (jwt.getAudience().contains("orders-api")) {
            return OAuth2TokenValidatorResult.success();
        }

        return OAuth2TokenValidatorResult.failure(
            new OAuth2Error(
                "invalid_token",
                "Token audience is not orders-api",
                null
            )
        );
    };

    decoder.setJwtValidator(
        new DelegatingOAuth2TokenValidator<>(
            issuerAndTime,
            audience
        )
    );

    return decoder;
}
~~~

Decoder này:

- Lấy public key từ JWKS URI đã cấu hình.
- Chỉ cho phép RS256.
- Xác minh issuer.
- Xác minh timestamp mặc định.
- Kiểm tra audience dành cho orders-api.

Trong Spring Security, JwtDecoder là API đồng bộ cho Servlet Resource Server. Với WebFlux, dùng NimbusReactiveJwtDecoder và ReactiveJwtDecoder; logic trust policy giống nhau nhưng kết quả decode là Mono<Jwt>.

### 7.2. Tạo decoder một lần và tái sử dụng

~~~java
JwtDecoder decoder = createDecoder(jwksUri);
~~~

Trong production, decoder nên có lifecycle dùng chung thay vì tạo mới cho mỗi request. Việc tạo decoder mới liên tục có thể làm mất cache và tăng JWKS fetch.

Trong test, tạo decoder một lần để quan sát hành vi của cache qua các giai đoạn. Sau đó tạo decoder mới riêng khi muốn mô phỏng một Resource Server instance vừa khởi động.

---

## 8. Bài test chính: token cũ và mới cùng hợp lệ trong overlap

### 8.1. Chuẩn bị trạng thái ban đầu

1. Tạo K1 và K2.
2. JWKS ban đầu chỉ chứa public K1.
3. Khởi động endpoint.
4. Tạo decoder D1 trỏ vào JWKS URI.
5. Phát hành T1 bằng private K1, exp còn ở tương lai.
6. Decode T1 để D1 tải và cache JWKS có K1.

~~~java
currentJwks.set(jwksWithK1);

JwtDecoder decoder = createDecoder(jwksUri);

String oldToken = issueToken(
    keyPair1,
    "rsa-key-1",
    Instant.now().plus(Duration.ofMinutes(15))
);

Jwt oldJwt = decoder.decode(oldToken);

assertEquals("user-417", oldJwt.getSubject());
~~~

Bước decode đầu tiên cũng làm nóng đường đi key retrieval. Nếu muốn kiểm tra cold start, hãy tạo decoder mới cho mỗi test case và ghi nhận số lần endpoint JWKS được gọi.

### 8.2. Publish public K2 nhưng giữ K1

~~~java
currentJwks.set(jwksWithBoth);
~~~

Tạo T2 bằng K2:

~~~java
String newToken = issueToken(
    keyPair2,
    "rsa-key-2",
    Instant.now().plus(Duration.ofMinutes(15))
);
~~~

Dùng chính decoder D1 để xác minh T2:

~~~java
Jwt newJwt = decoder.decode(newToken);

assertEquals("user-417", newJwt.getSubject());
~~~

Khi D1 chưa có K2 trong cache, Nimbus JWK source có thể refresh JWKS để tìm kid mới. Hãy kiểm tra hành vi refresh với phiên bản Nimbus/Spring Security mà project đang dùng; đừng giả định cache sẽ cập nhật ngay chỉ vì endpoint đã đổi response.

### 8.3. Xác minh T1 vẫn dùng được

~~~java
Jwt oldJwtAfterPublish = decoder.decode(oldToken);

assertEquals("user-417", oldJwtAfterPublish.getSubject());
~~~

K1 vẫn nằm trong JWKS, nên token cũ tiếp tục xác minh được. Đây là điều kiện cốt lõi của overlap.

### 8.4. Kết quả mong đợi

| Token | kid | JWKS trong overlap | Kết quả |
|---|---|---|---|
| T1 | rsa-key-1 | K1 + K2 | Chấp nhận nếu còn hạn và claims hợp lệ |
| T2 | rsa-key-2 | K1 + K2 | Chấp nhận nếu còn hạn và claims hợp lệ |
| T1 đổi header kid thành K2 nhưng không ký lại | rsa-key-2 | K1 + K2 | Từ chối chữ ký |
| Token ký bằng key không có trong JWKS | unknown-key | K1 + K2 | Từ chối |
| T2 sai audience | rsa-key-2 | K1 + K2 | Từ chối |
| T1 hết hạn | rsa-key-1 | K1 + K2 | Từ chối do timestamp |

Overlap không làm nới issuer, audience, signature hoặc expiry validation. Nó chỉ bảo đảm RS có public key cần thiết cho các token đã được phát hành hợp lệ.

---

## 9. Mô phỏng gỡ K1 khi token cũ vẫn còn hạn

### 9.1. Thay JWKS chỉ còn K2

~~~java
currentJwks.set(jwksWithK2);
~~~

T1 vẫn chưa hết hạn nhưng key K1 đã bị gỡ khỏi JWKS. Một Resource Server mới chưa cache K1 sẽ không thể tìm thấy public key để xác minh T1. Request đó phải bị từ chối vì chữ ký không thể được xác minh bằng trusted key source hiện tại.

Tuy nhiên, D1 có thể đang cache public K1. Nó có thể tiếp tục xác minh T1 cho tới khi cache refresh/expire hoặc key bị invalidate theo implementation. Vì vậy, kết quả giữa các node có thể khác nhau trong giai đoạn cache chưa đồng bộ.

### 9.2. So sánh decoder đã cache với decoder mới

~~~java
// D1 đã từng tải JWKS có K1.
assertDoesNotThrow(() -> decoder.decode(oldToken));

// D2 mô phỏng một Resource Server instance mới.
JwtDecoder freshDecoder = createDecoder(jwksUri);

assertThrows(
    JwtException.class,
    () -> freshDecoder.decode(oldToken)
);
~~~

Assertion đầu chỉ minh họa khả năng cache giữ key cũ; nó phụ thuộc cache policy và thời điểm refresh của thư viện. Không dùng nó như cam kết rằng mọi phiên bản Nimbus đều giữ key trong một khoảng cố định.

Assertion thứ hai kiểm tra instance mới chỉ nhìn thấy JWKS hiện tại có K2. Vì T1 vẫn mang kid K1, decoder mới không có key phù hợp và phải từ chối.

Nếu muốn test chính xác việc D1 từ chối sau khi cache refresh, cần điều khiển cache/refresh trong test hoặc tạo một decoder mới sau khi JWKS chỉ còn K2. Không dựa vào Thread.sleep để chờ một TTL không được kiểm soát.

### 9.3. Bài học vận hành

Gỡ key khỏi JWKS không đảm bảo mọi RS lập tức quên public key đó. Mỗi instance có thể có cache riêng, và cache policy của Nimbus/JWK source có thể khác theo phiên bản hoặc cấu hình.

Với rotation định kỳ, giải pháp đúng là không gỡ K1 trước khi token ký bằng K1 hết hạn. Với key compromise, cần quy trình khẩn cấp có thể bao gồm:

- Gỡ key khỏi JWKS.
- Kích hoạt refresh/invalidation cache trên tất cả RS.
- Thu hồi hoặc chặn token liên quan.
- Rút ngắn thời hạn token hoặc áp dụng denylist/introspection tùy kiến trúc.
- Theo dõi request còn dùng kid bị compromise.

Không dựa vào việc JWKS endpoint đã thay đổi để kết luận toàn bộ cluster đã nhận thay đổi.

---

## 10. Kiểm tra token cũ hết hạn trong khi K1 vẫn còn được publish

Đây là một test quan trọng để tách hai cơ chế:

- **Key availability:** RS có public key để kiểm tra chữ ký hay không?
- **Token validity:** token còn nằm trong thời gian hợp lệ hay không?

Ngay cả khi K1 vẫn có trong JWKS, token T1 phải bị từ chối sau exp.

Tạo token ký bằng K1 nhưng đã hết hạn:

~~~java
String expiredOldToken = issueToken(
    keyPair1,
    "rsa-key-1",
    Instant.now().minus(Duration.ofMinutes(1))
);

assertThrows(
    JwtException.class,
    () -> decoder.decode(expiredOldToken)
);
~~~

Test này chứng minh giữ public K1 trong overlap không làm token cũ sống vô thời hạn. Timestamp validator vẫn áp dụng cho mọi token, bất kể kid nào.

Nếu dùng clock cố định trong test, tạo issuedAt/exp theo cùng Clock. Tránh phụ thuộc vào thời gian thực để test biên exp và clock skew.

### 10.1. Kiểm tra clock skew

RS có thể cho phép một khoảng lệch đồng hồ để tránh từ chối token do clock drift nhỏ. Hãy cấu hình và kiểm thử giá trị clock skew rõ ràng.

Ví dụ khởi tạo validator timestamp với skew được chọn:

~~~java
JwtTimestampValidator timestampValidator =
    new JwtTimestampValidator(Duration.ofSeconds(30));
~~~

Kết hợp validator timestamp với issuer, audience và policy còn lại theo API version đang dùng. Clock skew không phải lý do để giữ K1 lâu hơn tùy ý; nó là một phần của phép tính thời điểm retire key.

---

## 11. Mô phỏng nhiều Resource Server instance

### 11.1. Vì sao cần test nhiều node?

Mỗi RS instance có thể:

- Khởi động ở thời điểm khác nhau.
- Tải JWKS lần đầu ở thời điểm khác nhau.
- Có cache K1/K2 khác nhau.
- Gặp unknown kid vào thời điểm khác nhau.
- Không truy cập được JWKS trong một khoảng thời gian.
- Được deploy hoặc restart trong khi rotation diễn ra.

Một test chỉ dùng một decoder không thể mô phỏng hết các khác biệt đó.

### 11.2. Kịch bản hai node

Giả sử:

- Node A đã cache JWKS chỉ có K1.
- AS publish K1 + K2.
- Node B khởi động sau khi publish và tải cả hai key.
- AS chuyển signer sang K2.
- Node A gặp token K2 và cần refresh.
- Node B xác minh cả T1 và T2 từ cache.
- Sau overlap, JWKS chỉ còn K2 và node mới không xác minh T1.

Bảng kiểm tra:

| Thời điểm | JWKS | Node A | Node B |
|---|---|---|---|
| Trước publish | K1 | Có K1 | Có thể chưa khởi động |
| Sau publish | K1 + K2 | Cache cũ K1 | Tải K1 + K2 |
| Sau switch | K1 + K2 | Refresh khi gặp kid K2 | Xác minh T1/T2 |
| Sau retire | K2 | Có thể còn cache K1 tạm thời | Refresh/expire theo policy |
| Sau cache convergence | K2 | Chỉ dùng K2 | Chỉ dùng K2 |

### 11.3. Kiểm thử bằng hai decoder độc lập

Trong test, tạo hai decoder riêng:

~~~java
JwtDecoder nodeA = createDecoder(jwksUri);
JwtDecoder nodeB = createDecoder(jwksUri);
~~~

Cho nodeA decode T1 trước khi publish K2 để nó cache K1. Sau đó publish K1 + K2, cho nodeB khởi động và decode cả T1/T2. Tiếp tục gửi T2 tới nodeA để quan sát refresh khi gặp unknown kid.

Sau khi retire K1, tạo nodeC mới để xác nhận T1 không còn được xác minh từ JWKS hiện tại. Nếu muốn test cache convergence của nodeA/nodeB, phải kiểm soát rõ cache và refresh behavior thay vì chờ ngẫu nhiên.

### 11.4. Đồng bộ cấu hình và rollout

Trong môi trường thật, kiểm tra:

- Mọi RS instance dùng cùng issuer và JWKS URI.
- Không có instance cũ trỏ tới endpoint khác.
- Egress tới JWKS endpoint hoạt động từ mọi network zone.
- Cache refresh không bị chặn bởi proxy/CDN sai policy.
- Rollout AS và RS không tạo khoảng thời gian key chưa được publish.
- Autoscaled instance mới có thể tải JWKS hiện hành.
- Dashboard có thể nhận biết node nào chưa thấy kid mới.

---

## 12. Kiểm thử JWKS unavailable và unknown kid

### 12.1. JWKS endpoint tạm thời lỗi

Khi public key đã được cache, một số request có thể tiếp tục xác minh bằng key đã biết trong lúc JWKS endpoint lỗi. Nhưng token dùng kid mới chưa được cache có thể thất bại.

Test hai tình huống:

| Trạng thái | Kết quả cần kiểm tra |
|---|---|
| Token K1, cache đã có K1, JWKS endpoint tạm thời down | Có thể tiếp tục xác minh theo cache/library behavior |
| Token K2, cache chưa có K2, JWKS endpoint down | Không thể xác minh nếu không có trusted K2 |
| Instance mới, JWKS down, token K1 | Không có key để xác minh; từ chối |
| JWKS endpoint trả JSON malformed | Không chấp nhận key response lỗi |

Không biến lỗi tải JWKS thành bỏ qua signature verification.

### 12.2. Unknown kid không được kích hoạt tin cậy tùy ý

Một token có thể gửi kid ngẫu nhiên. RS có thể thực hiện refresh JWKS theo behavior của JWK source. Cần tránh để hàng loạt unknown kid tạo tải không giới hạn lên AS/JWKS endpoint.

Theo dõi:

- Unknown-kid rate.
- JWKS fetch count.
- JWKS fetch latency.
- Refresh failures.
- Decoder failures.
- Số request chờ refresh.

Không tải key từ jku/x5u do token cung cấp để giải quyết unknown kid. kid chỉ được dùng để tìm key trong nguồn đã tin cậy.

### 12.3. Chống cache stampede

Nếu nhiều request cùng gặp kid mới, một số implementation có thể phối hợp refresh hoặc có nhiều lần fetch tùy cache/source. Đo behavior thật của version đang dùng.

Có thể giảm rủi ro bằng cách:

- Publish K2 trước khi AS bắt đầu ký.
- Warm-up key mới ở RS nếu hệ thống có cơ chế hỗ trợ.
- Dùng cache và HTTP client có lifecycle dùng chung.
- Giới hạn retry/refresh theo khả năng của thư viện.
- Tránh deploy/restart toàn bộ RS cùng lúc nếu không cần thiết.

Không tự tạo một refresh loop vô hạn khi gặp unknown kid.

---

## 13. Bài test tổng hợp bằng JUnit

### 13.1. Các helper cần có

Một test fixture hoàn chỉnh có thể gom các helper:

~~~java
class SigningKeyRotationTests {

    static final String ISSUER =
        "https://issuer.test.example";

    static final String AUDIENCE = "orders-api";

    KeyPair keyPair1;
    KeyPair keyPair2;

    RSAKey publicKey1;
    RSAKey publicKey2;

    AtomicReference<String> currentJwks;
    HttpServer jwksServer;
    String jwksUri;

    JwtDecoder decoder;

    @BeforeEach
    void setUp() throws Exception {
        keyPair1 = generateRsaKeyPair();
        keyPair2 = generateRsaKeyPair();

        publicKey1 = publicJwk(keyPair1, "rsa-key-1");
        publicKey2 = publicJwk(keyPair2, "rsa-key-2");

        currentJwks = new AtomicReference<>(
            new JWKSet(publicKey1).toString()
        );

        startJwksServer();

        decoder = createDecoder(jwksUri);
    }

    @AfterEach
    void tearDown() {
        if (jwksServer != null) {
            jwksServer.stop(0);
        }
    }
}
~~~

Các helper startJwksServer(), generateRsaKeyPair(), publicJwk(), issueToken() và createDecoder() được trình bày ở các mục trước. Có thể chuyển chúng thành test utility để tái sử dụng trong các test rotation khác.

### 13.2. Test overlap

~~~java
@Test
void acceptsOldAndNewTokensDuringOverlap() throws Exception {
    String oldToken = issueToken(
        keyPair1,
        "rsa-key-1",
        Instant.now().plus(Duration.ofMinutes(10))
    );

    assertEquals(
        "user-417",
        decoder.decode(oldToken).getSubject()
    );

    currentJwks.set(
        new JWKSet(List.of(publicKey1, publicKey2)).toString()
    );

    String newToken = issueToken(
        keyPair2,
        "rsa-key-2",
        Instant.now().plus(Duration.ofMinutes(10))
    );

    assertEquals(
        "user-417",
        decoder.decode(newToken).getSubject()
    );

    assertEquals(
        "user-417",
        decoder.decode(oldToken).getSubject()
    );
}
~~~

Test này kiểm tra mục tiêu chính: cùng một decoder có thể xác minh token cũ và token mới trong giai đoạn overlap, với điều kiện JWKS refresh hoạt động theo version đang dùng.

### 13.3. Test token cũ hết hạn

~~~java
@Test
void rejectsExpiredOldTokenEvenWhenOldKeyIsPublished() throws Exception {
    currentJwks.set(
        new JWKSet(List.of(publicKey1, publicKey2)).toString()
    );

    String expiredToken = issueToken(
        keyPair1,
        "rsa-key-1",
        Instant.now().minus(Duration.ofMinutes(1))
    );

    assertThrows(
        JwtException.class,
        () -> decoder.decode(expiredToken)
    );
}
~~~

Test xác nhận public key cũ vẫn có trong JWKS không làm vô hiệu hóa exp validation.

### 13.4. Test token cũ sau khi retire K1

~~~java
@Test
void freshDecoderCannotVerifyOldKidAfterRetirement() throws Exception {
    String oldToken = issueToken(
        keyPair1,
        "rsa-key-1",
        Instant.now().plus(Duration.ofMinutes(5))
    );

    currentJwks.set(new JWKSet(publicKey2).toString());

    JwtDecoder freshDecoder = createDecoder(jwksUri);

    assertThrows(
        JwtException.class,
        () -> freshDecoder.decode(oldToken)
    );
}
~~~

Token vẫn còn hạn trong test, nhưng public K1 không còn được cung cấp bởi JWKS. Decoder mới không thể xác minh chữ ký. Đây là mô phỏng tình huống retire quá sớm và giải thích vì sao token cũ sẽ bị lỗi trên một số instance.

Không dùng test này làm mục tiêu mong muốn của rotation bình thường. Trong production, chỉ retire K1 sau khi token cũ đã hết hạn theo policy.

---

## 14. Kiểm tra Spring Security HTTP endpoint

### 14.1. Gắn decoder vào Servlet Resource Server

~~~java
@Bean
SecurityFilterChain apiSecurity(
        HttpSecurity http,
        JwtDecoder decoder) throws Exception {

    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyRequest().denyAll()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(jwt -> jwt.decoder(decoder))
        )
        .build();
}
~~~

Controller test:

~~~java
@RestController
class OrdersController {

    @GetMapping("/api/orders")
    Map<String, String> orders(Authentication authentication) {
        return Map.of("subject", authentication.getName());
    }
}
~~~

Khi test bằng MockMvc, gửi access token thực được ký bởi K1/K2 qua Authorization header. Không dùng mock jwt() nếu mục tiêu là kiểm tra chữ ký và key rotation, vì mock authentication bỏ qua decoder.

### 14.2. Kiểm tra status

| Request | Kết quả mong đợi |
|---|---|
| T1 ký bằng K1 trong overlap | 200 |
| T2 ký bằng K2 trong overlap | 200 |
| T1 hết hạn, K1 vẫn publish | 401 |
| T1 còn hạn nhưng K1 đã retire, decoder mới | 401 |
| T2 sai audience | 401 |
| Token ký bằng private key không có public key trong JWKS | 401 |
| Token hợp lệ nhưng thiếu SCOPE_orders.read | 403 |

401 phản ánh authentication thất bại. 403 phản ánh token đã xác thực nhưng không đủ authority. Giữ hai trường hợp riêng để chẩn đoán rotation failure chính xác.

### 14.3. WebFlux

Với WebFlux, cấu hình ReactiveJwtDecoder và SecurityWebFilterChain. Khi test bằng WebTestClient, gửi compact token được ký thật để đi qua decoder.

Nếu test chỉ dùng mockJwt(), test đang kiểm tra authorization rule sau khi Authentication đã được dựng sẵn; nó không xác minh JWKS fetch, kid selection hay signature verification.

---

## 15. Rotation định kỳ khác với key compromise

### 15.1. Rotation định kỳ

Mục tiêu là chuyển signing key mà không làm gián đoạn token đang lưu hành:

- Publish public key mới.
- Giữ public key cũ.
- Đảm bảo RS nhận key mới.
- Chuyển AS sang ký bằng key mới.
- Chờ toàn bộ token K1 hết hạn cộng skew/margin.
- Gỡ public K1.

Trong trường hợp này, overlap là cần thiết.

### 15.2. Key compromise

Nếu private K1 bị lộ, attacker có thể ký token giả bằng K1. Khi đó việc giữ K1 trong JWKS để bảo đảm token cũ không bị gián đoạn có thể duy trì khả năng xác minh token giả.

Cần xử lý như security incident:

1. Ngừng ký bằng K1.
2. Gỡ K1 khỏi JWKS hoặc đánh dấu key bị revoke theo khả năng hệ thống.
3. Buộc refresh/invalidate cache trên mọi RS.
4. Revoke token liên quan bằng introspection/denylist hoặc cơ chế phù hợp.
5. Kiểm tra token được ký trong khoảng thời gian compromise.
6. Cân nhắc rút ngắn maximum token lifetime và phát hành lại token.
7. Theo dõi request dùng kid K1.
8. Ghi nhận incident và xác nhận tất cả node đã hội tụ.

Trong tình huống compromise, không áp dụng overlap window thông thường một cách máy móc. Ưu tiên là ngừng tin key bị lộ, đồng thời xử lý tác động lên người dùng có token hợp lệ.

### 15.3. Giới hạn của việc xóa key khỏi JWKS

Nếu RS đã cache K1, xóa K1 khỏi JWKS có thể không làm node đó từ chối ngay lập tức. Cần hiểu cache policy, cách refresh và khả năng invalidation của decoder/JWK source.

Nếu yêu cầu emergency revocation nhanh, cần một cơ chế đã được thiết kế và kiểm thử để làm mới cache hoặc từ chối kid bị compromise. Restart tất cả node có thể là biện pháp vận hành nhưng không nên là giả định duy nhất nếu hệ thống cần thời gian phản ứng ngắn.

---

## 16. Các lỗi thường gặp trong bài lab

| Sai lầm | Hệ quả | Cách xử lý |
|---|---|---|
| Gỡ K1 ngay khi publish K2 | Token K1 còn hạn có thể bị từ chối | Giữ K1 trong overlap |
| AS ký K2 trước khi publish public K2 | RS chưa có key để xác minh token mới | Publish/warm-up trước switch |
| Đổi kid nhưng không ký lại JWT | Chữ ký không khớp | Ký token mới bằng private K2 |
| Dùng cùng key pair cho hai kid | Không mô phỏng được rotation thực | Tạo hai key pair độc lập |
| Đưa private JWK vào JWKS | Rò rỉ signing key | Chỉ publish public JWK |
| Tạo decoder mới mỗi request | Mất cache và tăng fetch | Dùng decoder singleton/managed bean |
| Chỉ test một RS instance | Bỏ sót cache khác nhau giữa node | Test nhiều decoder độc lập |
| Nghĩ JWKS update có hiệu lực ngay | Node có thể giữ cache cũ | Kiểm tra refresh/cache convergence |
| Dùng Thread.sleep để chờ cache | Test flaky | Điều khiển cache/Clock và dùng test endpoint |
| Giữ K1 mãi mãi | Tăng thời gian tin cậy key cũ | Retire theo maximum token lifetime |
| Gỡ K1 khi còn token cũ hợp lệ | Một số RS không xác minh được token | Tính mốc retire bằng exp/skew/margin |
| Coi đổi signer là revoke token cũ | Token cũ vẫn có thể dùng | Dùng revocation policy riêng nếu cần |
| Không test exp khi K1 vẫn publish | Có thể bỏ sót timestamp validation | Test token hết hạn độc lập |
| Chỉ test token mới | Không phát hiện lỗi overlap | Test T1 và T2 song song |
| Unknown kid thì tải jku từ token | Mở trust source tùy ý | Chỉ dùng JWKS URI tin cậy |
| Cache refresh thất bại nhưng bỏ qua signature | Fail-open | Từ chối token không xác minh được |
| Xóa K1 sau compromise nhưng quên cache | Node cũ có thể tiếp tục tin K1 | Có cache invalidation/incident procedure |

---

## 17. Checklist hoàn thành lab

### Chuẩn bị

- [ ] Tạo K1 và K2 bằng hai RSA key pair riêng.
- [ ] Gán kid duy nhất cho mỗi key.
- [ ] Chỉ publish public JWK.
- [ ] Dựng JWKS endpoint test có thể thay response.
- [ ] Cấu hình decoder với issuer, audience và RS256 allowlist.
- [ ] Tạo T1 ký bằng K1 và xác nhận còn hạn.

### Publish và switch

- [ ] JWKS ban đầu chỉ có K1.
- [ ] RS xác minh được T1.
- [ ] Publish K1 + K2.
- [ ] RS nhận biết K2.
- [ ] AS phát hành T2 ký bằng K2.
- [ ] RS xác minh được T2.
- [ ] RS vẫn xác minh được T1.

### Retire

- [ ] Tính thời điểm retire từ token K1 cuối cùng, maximum lifetime, skew và margin.
- [ ] Không retire K1 khi token K1 còn hạn theo policy.
- [ ] Kiểm tra token hết hạn bị từ chối dù K1 vẫn publish.
- [ ] Sau retire, instance mới không xác minh token K1.
- [ ] Kiểm tra cache cũ có thể cần refresh/invalidation.
- [ ] Xác nhận T2 tiếp tục hợp lệ.

### Vận hành

- [ ] Test ít nhất hai RS instance/cache độc lập.
- [ ] Test JWKS endpoint unavailable.
- [ ] Test unknown kid và malformed JWKS.
- [ ] Theo dõi key fetch, unknown kid, 401 và decoder errors.
- [ ] Có quy trình riêng cho key compromise.
- [ ] Không log token hoặc private key.

---

## 18. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao cần giữ K1 trong JWKS sau khi AS bắt đầu ký bằng K2?

**Trả lời:** Token đã phát hành bằng K1 có thể còn hạn. RS cần public K1 để xác minh chữ ký của những token đó trong overlap window.

**Câu 2.** Có cần thay issuer khi rotate signing key không?

**Trả lời:** Không. Issuer định danh AS và giữ nguyên. Rotation thay signing key và tập public key được công bố.

**Câu 3.** kid có thay thế chữ ký không?

**Trả lời:** Không. kid chỉ giúp chọn public key. Token mới phải được ký bằng private key tương ứng.

**Câu 4.** Khi nào có thể retire K1?

**Trả lời:** Sau khi không còn token K1 nào hợp lệ, cộng clock skew và propagation/cache margin. Dùng maximum exp hoặc thời điểm phát hành K1 cuối cùng cộng maximum token lifetime.

**Câu 5.** Vì sao một node có thể chấp nhận T1 sau khi K1 đã bị gỡ khỏi JWKS?

**Trả lời:** Node có thể vẫn cache public K1. Cache không nhất thiết được invalidated ngay khi endpoint thay đổi.

**Câu 6.** Một node mới có thể từ chối T1 dù token chưa hết hạn không?

**Trả lời:** Có. Nếu JWKS hiện tại không còn K1, node mới không có public key để xác minh chữ ký T1.

**Câu 7.** Giữ K1 trong JWKS có làm token sống lâu hơn exp không?

**Trả lời:** Không. Timestamp validator vẫn từ chối token đã hết hạn.

**Câu 8.** Nếu JWKS endpoint down và RS chưa có K2 thì sao?

**Trả lời:** RS không thể xác minh token K2 bằng trusted key chưa có. Nó phải từ chối token đó thay vì bỏ qua signature verification.

**Câu 9.** Có thể dùng cùng key pair cho K1 và K2 nhưng đổi kid không?

**Trả lời:** Không nên. Việc đó không tạo rotation thực và làm test không phát hiện lỗi key selection.

**Câu 10.** Rotation định kỳ và key compromise khác nhau ở điểm nào?

**Trả lời:** Rotation định kỳ cần overlap để token cũ tiếp tục hoạt động. Key compromise cần ngừng tin key bị lộ nhanh, refresh cache và xử lý token đã ký bằng key đó.

**Câu 11.** Có nên tạo JwtDecoder mới cho mỗi request để thấy JWKS mới không?

**Trả lời:** Không. Decoder nên được quản lý và tái sử dụng. Việc tạo mới mỗi request gây mất cache và tăng tải JWKS.

**Câu 12.** Vì sao cần test nhiều RS instance?

**Trả lời:** Mỗi node có thể có cache và thời điểm refresh khác nhau. Test một node không phát hiện được sự không đồng nhất trong cluster.

**Câu 13.** Nếu T1 còn hạn nhưng K1 đã bị retire theo kế hoạch thì lỗi 401 có phải hành vi mong muốn không?

**Trả lời:** Không. Đó là dấu hiệu retire quá sớm hoặc có token K1 được phát hành muộn hơn dự kiến. Với planned rotation, phải giữ K1 cho tới khi token cũ hết hạn.

**Câu 14.** Nếu K1 bị compromise thì có phải tiếp tục overlap cho tới khi token cũ hết hạn không?

**Trả lời:** Không nhất thiết. Phải xử lý theo incident policy, gỡ key, refresh cache và revoke/chặn token liên quan. Giữ key bị compromise có thể cho phép attacker tiếp tục ký token giả.

**Câu 15.** Bài lab đã chứng minh điều gì?

**Trả lời:** Nó chứng minh RS có thể xác minh token cũ và mới trong overlap khi cả hai public key được tin cậy; token hết hạn vẫn bị từ chối; và việc retire key ảnh hưởng đến khả năng xác minh token cũ tùy cache state của từng node.

---

## 19. Tài liệu tham khảo

- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517.html): JWK, JWKS, kid, key use và public key representation.
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515.html): JOSE header, signing input và chữ ký JWT.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519.html): issuer, audience, exp và các claim thời gian.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725.html): xác minh thuật toán, issuer, audience và xử lý JWT an toàn.
- [Spring Security — JWT Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JwtDecoder, issuer-uri, jwk-set-uri và JWK retrieval.
- [Spring Security — Reactive JWT Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html): ReactiveJwtDecoder và xác minh JWT trên WebFlux.
- [Spring Security API — NimbusJwtDecoder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/NimbusJwtDecoder.html): cấu hình decoder Servlet.
- [Nimbus JOSE + JWT](https://connect2id.com/products/nimbus-jose-jwt): API tạo JWK, JWKS, ký JWT và xử lý remote JWK source.

API và cache behavior có thể thay đổi theo phiên bản Spring Security/Nimbus. Hãy kiểm tra đúng dependency đã resolve trong project và chạy bài lab trên cùng version sẽ triển khai.

---

## 20. Ghi nhớ

Luân chuyển signing key an toàn cần có khoảng overlap để Resource Server tiếp tục xác minh token cũ trong khi bắt đầu nhận token mới.

- **Publish trước:** đưa public K2 vào JWKS cùng K1 trước khi AS ký token bằng K2.
- **Switch sau:** chỉ chuyển signer khi RS có thể lấy public K2.
- **Giữ key cũ:** tiếp tục publish K1 cho tới khi mọi token ký bằng K1 hết hạn, cộng clock skew và propagation margin.
- **Retire có kiểm soát:** gỡ K1 sau overlap; kiểm tra cache của từng RS instance.
- **Giữ validation:** issuer, audience, algorithm, signature và exp vẫn phải được xác minh ở mọi giai đoạn.
- **Test nhiều node:** cache khác nhau có thể tạo kết quả khác nhau trong thời gian hội tụ.
- **Xử lý compromise riêng:** nếu private key bị lộ, ưu tiên ngừng tin key, invalidation cache và revoke token liên quan thay vì duy trì overlap thông thường.

Rotation hoàn tất khi AS ký bằng K2, mọi RS xác minh được token K2, token K1 đã hết thời hạn hợp lệ và K1 được retire theo policy.
