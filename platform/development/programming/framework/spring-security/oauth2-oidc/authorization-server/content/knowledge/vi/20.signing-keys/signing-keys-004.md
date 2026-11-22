# JWK Set Endpoint và các trường khóa công khai được phép công bố

Trong OAuth 2.0 và OpenID Connect (OIDC), Authorization Server thường ký JWT access token hoặc ID Token bằng khóa riêng. Resource Server và Relying Party cần lấy khóa công khai tương ứng để xác minh chữ ký. **JSON Web Key (JWK)** mô tả một khóa mật mã bằng JSON; **JSON Web Key Set (JWKS)** là tập các JWK; **JWK Set Endpoint** là endpoint mà Authorization Server công bố để bên nhận token tải tập khóa công khai.

Vấn đề quan trọng khi triển khai không chỉ là tạo một cặp RSA/EC key. Hệ thống phải công bố **đúng các trường công khai**, giữ tuyệt đối bí mật phần private key, gắn **kid ổn định** cho từng khóa, công bố khóa mới/cũ trong giai đoạn rotation, và bảo đảm Resource Server có thể xác minh token trong khi khóa được thay đổi.

Bài học thuộc chương **JWK và quản lý khóa** của module **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER**. Nội dung hướng dẫn thiết kế, cấu hình, bảo mật, kiểm thử và vận hành **Spring Security, Spring Authorization Server và Spring Boot**, tập trung vào JWK Set Endpoint và những trường JWK được phép công bố.

> **Quy tắc an toàn:** Public JWKS chỉ chứa **khóa công khai và metadata công khai cần thiết**. Không bao giờ đưa RSA/EC/OKP private parameters hoặc symmetric secret vào endpoint này. Khóa riêng dùng để ký phải được bảo vệ trong keystore, HSM, KMS hoặc kho bí mật tương đương.

## 1. Vì sao Authorization Server cần JWK Set Endpoint?

Giả sử Authorization Server tại https://identity.example.com phát hành JWT có chữ ký RS256. Khi orders-api nhận access token, API cần biết public key nào xác minh chữ ký. Thay vì chia sẻ thủ công public key cho mọi Resource Server, AS công bố một URL JWKS:

~~~http
GET /oauth2/jwks HTTP/1.1
Host: identity.example.com
Accept: application/json
~~~

Response minh họa:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "use": "sig",
      "alg": "RS256",
      "kid": "rsa-signing-2026-01",
      "n": "BASE64URL_ENCODED_RSA_MODULUS",
      "e": "AQAB"
    }
  ]
}
~~~

Resource Server tải JWKS, chọn khóa theo kid của JWT header, sau đó xác minh chữ ký bằng public key. JWKS **không phải nơi lưu token**, không chứa authorization code và không chứa private key. Endpoint thường được phép truy cập công khai để các API và RP có thể lấy khóa mà không cần đăng nhập người dùng.

### 1.1. Các thành phần liên quan

| Thành phần | Ý nghĩa | Vai trò |
|---|---|---|
| **JWK** | JSON mô tả một khóa mật mã | Biểu diễn public/private key và metadata theo loại khóa |
| **JWK Set (JWKS)** | JSON object có mảng keys | Công bố một hoặc nhiều JWK |
| **JWK Set Endpoint** | HTTP endpoint trả JWKS | Cho Resource Server/RP lấy public keys |
| **JWK Source** | Nguồn khóa mà AS dùng | Cung cấp khóa cho token encoder và endpoint tùy cấu hình |
| **kid** | Key ID | Giúp chọn đúng khóa trong JWKS khi verify token |
| **jwks_uri** | URL JWKS trong metadata | Cho client/resource server discovery endpoint khóa |
| **Private key** | Phần bí mật của key pair | Dùng ký token, không công bố |
| **Public key** | Phần công khai của key pair | Dùng xác minh chữ ký, có thể công bố |

### 1.2. JWK Set Endpoint không phải endpoint đăng nhập

JWK Set Endpoint không xác thực người dùng, không cấp token và không yêu cầu consent. Nó công bố public key để các bên đã tin cậy issuer có thể xác minh chữ ký. Việc endpoint không cần browser login **không có nghĩa** bất kỳ issuer nào cũng đáng tin: Resource Server phải cấu hình issuer tin cậy, xác minh chữ ký, thời hạn, audience và claims theo policy.

## 2. Cấu trúc JWK Set và JWK

Theo RFC 7517, JWK Set là một JSON object có member keys, giá trị là một mảng JWK:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "rsa-key-2026-a",
      "use": "sig",
      "alg": "RS256",
      "n": "PUBLIC_MODULUS",
      "e": "AQAB"
    },
    {
      "kty": "EC",
      "kid": "ec-key-2026-b",
      "use": "sig",
      "alg": "ES256",
      "crv": "P-256",
      "x": "PUBLIC_X_COORDINATE",
      "y": "PUBLIC_Y_COORDINATE"
    }
  ]
}
~~~

Đây là JSON minh họa với giá trị rút gọn, **không phải khóa thật**. Một JWKS có thể chứa nhiều khóa cùng lúc, ví dụ khóa hiện hành và khóa cũ còn cần để verify token chưa hết hạn.

### 2.1. kty là trường bắt buộc

kty (Key Type) xác định họ khóa. Những giá trị thường gặp:

| kty | Loại khóa | Trường public chính |
|---|---|---|
| RSA | RSA | n, e |
| EC | Elliptic Curve | crv, x, y |
| OKP | Octet Key Pair, ví dụ Ed25519 | crv, x |
| oct | Symmetric key | k là secret, **không công bố trong public JWKS** |

Không phải mọi kty đều phù hợp với mọi thuật toán JWS. Ví dụ RS256 dùng RSA; ES256 dùng EC P-256; EdDSA dùng khóa OKP phù hợp. Thuật toán và loại khóa phải tương thích.

### 2.2. JWKS không có thứ tự ưu tiên khóa

Mảng keys là tập khóa, consumer không nên suy ra khóa hiện hành chỉ vì một phần tử đứng đầu. Resource Server phải chọn khóa dựa trên kid, loại khóa, thuật toán và policy đã cấu hình. Nếu JWT không có kid trong khi JWKS có nhiều khóa phù hợp, việc chọn khóa có thể không xác định hoặc bị từ chối; thiết kế phát hành token nên gắn kid rõ ràng.

### 2.3. Một JWKS có thể chứa nhiều mục đích khóa

Một AS có thể sử dụng nhiều key pair cho mục đích khác nhau:

- Khóa ký JWT access token;
- Khóa ký OIDC ID Token;
- Khóa mã hóa Request Object hoặc token nếu triển khai hỗ trợ;
- Khóa thuộc thuật toán hoặc môi trường khác.

Không đưa mọi khóa trong kho nội bộ ra public JWKS. Chỉ công bố public key thực sự cần cho consumer xác minh token, kèm metadata để phân biệt mục đích.

## 3. Các trường JWK công khai được phép công bố

RFC 7517 định nghĩa các trường JWK chung. Một trường được chuẩn cho phép xuất hiện **không có nghĩa** mọi ứng dụng nên đưa nó vào mọi key. AS chỉ công bố những metadata cần thiết, chính xác và không tiết lộ bí mật.

| Trường | Ý nghĩa | Có thể công bố? | Lưu ý |
|---|---|---|---|
| kty | Loại khóa | **Có, bắt buộc** | Ví dụ RSA, EC, OKP |
| kid | Key ID | **Có** | Nên có để chọn khóa khi rotation |
| use | Mục đích sử dụng khóa | **Có** | sig cho signing/verification; enc cho encryption |
| key_ops | Các thao tác được phép | **Có** | Với public signing key thường là verify |
| alg | Thuật toán dự kiến | **Có** | Ví dụ RS256, PS256, ES256 |
| x5u | URL chứa X.509 certificate/chain | Có điều kiện | Chỉ dùng URL tin cậy; có rủi ro fetch ngoài ý muốn |
| x5c | X.509 certificate chain dạng Base64 DER | Có điều kiện | Chứng chỉ chứa public key; không chứa private key |
| x5t | SHA-1 thumbprint của certificate | Có điều kiện | Dùng để định danh certificate, không phải bí mật |
| x5t#S256 | SHA-256 thumbprint của certificate | Có điều kiện | Dạng tên member chính xác theo RFC |
| n, e | RSA modulus và public exponent | **Có** | Thành phần public của RSA |
| crv, x, y | Curve và public coordinates của EC | **Có** | x, y là tọa độ public |
| crv, x | Curve và public key bytes của OKP | **Có** | Ví dụ Ed25519 |
| d, p, q, dp, dq, qi, oth | Thành phần private của RSA | **Không** | Không đưa vào public JWKS |
| d | Private scalar của EC/OKP | **Không** | Không công bố |
| k | Symmetric key material của oct | **Không** | Là secret thực sự |

### 3.1. use — mục đích của khóa

use thường có hai giá trị:

- sig: khóa dùng cho chữ ký và xác minh chữ ký;
- enc: khóa dùng cho mã hóa/giải mã.

Với public key dùng xác minh JWT ký số, thường đặt use là sig. Không đặt use là enc cho khóa chỉ dùng ký token. Nếu một khóa được sử dụng cho nhiều mục đích, hãy cân nhắc tách key pair để giảm nhầm lẫn và rủi ro cross-protocol.

### 3.2. key_ops — thao tác được phép

key_ops là mảng thao tác mật mã, ví dụ:

~~~json
{
  "kty": "RSA",
  "kid": "rsa-verify-01",
  "use": "sig",
  "key_ops": ["verify"],
  "alg": "RS256",
  "n": "PUBLIC_MODULUS",
  "e": "AQAB"
}
~~~

Public key chỉ cần thao tác verify trong ví dụ này. Private key ở phía AS có thể thực hiện sign, nhưng **không công bố JWK chứa key_ops sign kèm private material**.

RFC 7517 khuyến nghị không dùng use và key_ops đồng thời. Nếu một implementation công bố cả hai, chúng phải nhất quán. Ví dụ use sig phải phù hợp với key_ops verify cho public verification key.

### 3.3. alg — thuật toán dự kiến

alg mô tả thuật toán JWA mà khóa được dự định dùng, ví dụ:

| Thuật toán | Loại khóa | Mục đích |
|---|---|---|
| RS256 | RSA | RSASSA-PKCS1-v1_5 với SHA-256 |
| PS256 | RSA | RSASSA-PSS với SHA-256 |
| ES256 | EC P-256 | ECDSA với SHA-256 |
| EdDSA | OKP phù hợp | Edwards-curve signature theo JWA |

Resource Server phải cấu hình **allowlist thuật toán** và xác minh tương thích với issuer/key. Không tin alg trong JWT header một cách mù quáng, không chấp nhận none, và không để attacker ép verifier chuyển từ asymmetric algorithm sang HMAC/shared secret.

### 3.4. kid — định danh khóa

kid là chuỗi định danh khóa, thường xuất hiện trong JWT protected header:

~~~json
{
  "alg": "RS256",
  "kid": "rsa-signing-2026-01",
  "typ": "JWT"
}
~~~

Verifier đọc kid, tìm JWK có kid tương ứng trong JWKS đã tải, rồi xác minh chữ ký. kid:

- Nên duy nhất trong phạm vi JWK Set tại cùng thời điểm;
- Phải ổn định trong suốt vòng đời của key pair;
- Không nên tái sử dụng cho một key pair khác sau rotation;
- Không phải mật khẩu, không phải private key và không nhất thiết là fingerprint mật mã.

Không đổi kid của cùng một key pair tùy tiện giữa các lần khởi động, vì cache và token đã phát hành có thể không còn tìm được khóa tương ứng.

## 4. Public fields và private fields theo từng loại khóa

### 4.1. RSA

JWK RSA public key dùng các trường:

~~~json
{
  "kty": "RSA",
  "kid": "rsa-signing-2026-01",
  "use": "sig",
  "alg": "RS256",
  "n": "BASE64URL_MODULUS",
  "e": "AQAB"
}
~~~

- n: modulus của RSA;
- e: public exponent;
- d: private exponent;
- p, q: hai prime factors;
- dp, dq, qi: các CRT private parameters;
- oth: thông tin private bổ sung trong multi-prime RSA.

**Chỉ n và e là thành phần RSA public cơ bản.** Các trường d, p, q, dp, dq, qi, oth không được xuất hiện trong public JWKS. Một private RSA JWK thường có thể chứa tất cả các trường trên để AS ký token, nhưng public endpoint phải trả public projection.

### 4.2. Elliptic Curve (EC)

Ví dụ EC P-256:

~~~json
{
  "kty": "EC",
  "kid": "ec-signing-2026-01",
  "use": "sig",
  "alg": "ES256",
  "crv": "P-256",
  "x": "BASE64URL_PUBLIC_X",
  "y": "BASE64URL_PUBLIC_Y"
}
~~~

crv, x, y là thông tin public. d là private scalar và **không được công bố**. Tọa độ phải được mã hóa theo quy tắc JWK, không lấy chuỗi hex tùy ý rồi đưa thẳng vào JSON.

### 4.3. Octet Key Pair (OKP)

Với Ed25519, public JWK có dạng:

~~~json
{
  "kty": "OKP",
  "kid": "ed25519-signing-2026-01",
  "use": "sig",
  "alg": "EdDSA",
  "crv": "Ed25519",
  "x": "BASE64URL_PUBLIC_KEY"
}
~~~

x là public key bytes; d là private key bytes và không được xuất hiện trong public JWKS. Phải bảo đảm thư viện, JWA profile và Resource Server hỗ trợ thuật toán tương ứng.

### 4.4. Symmetric key (oct)

Ví dụ cấu trúc JWK đối với symmetric key:

~~~json
{
  "kty": "oct",
  "kid": "hmac-key-01",
  "alg": "HS256",
  "k": "BASE64URL_SECRET_KEY_MATERIAL"
}
~~~

Trường k **chính là secret**. Không bao giờ công bố JWK kiểu oct chứa k tại JWK Set Endpoint công khai. Với kiến trúc Authorization Server và nhiều Resource Server độc lập, chữ ký bất đối xứng thường phù hợp hơn: AS giữ private key để ký, các RS chỉ nhận public key để verify. Nếu dùng HMAC, mọi bên có secret đều có khả năng ký token, làm tăng phạm vi tin cậy.

## 5. X.509 certificate và thumbprint

JWK có thể kèm metadata liên quan chứng chỉ:

| Trường | Mô tả | Lưu ý |
|---|---|---|
| x5u | URL tới X.509 certificate/chain | Consumer có thể fetch URL; chỉ công bố endpoint do tổ chức kiểm soát |
| x5c | Mảng certificate dạng Base64 DER | Certificate chứa public key và thông tin chứng chỉ |
| x5t | SHA-1 thumbprint của certificate | Không phải secret; legacy compatibility |
| x5t#S256 | SHA-256 thumbprint của certificate | Thuộc tính thumbprint mạnh hơn SHA-1 |

### 5.1. x5c không phải private key

Một X.509 certificate công khai có thể được phân phối qua JWKS. Nó chứa public key và metadata như subject, issuer, validity, serial, extensions và chữ ký của CA. **Private key tương ứng không nằm trong certificate**. Tuy vậy, việc công bố certificate vẫn tiết lộ metadata hạ tầng, nên chỉ công bố chain cần thiết.

### 5.2. Cẩn trọng với x5u

Nếu JWK công bố x5u, consumer có thể tải certificate từ URL đó theo implementation. URL cần thuộc domain tin cậy, dùng HTTPS, không thay đổi nội dung ngoài kiểm soát và không trỏ tới địa chỉ nội bộ tùy tiện. Resource Server không nên cho token header tự khai jku/x5u tùy ý quyết định nơi tải khóa; hãy lấy JWKS URI từ issuer đã cấu hình/discovery tin cậy.

### 5.3. Thumbprint không thay thế kid

kid là key identifier được issuer đặt để lựa chọn khóa; x5t/x5t#S256 là thumbprint của certificate. Chúng có thể phục vụ mục đích khác nhau. Không tự tính thumbprint rồi giả định nó luôn bằng kid; hai trường chỉ giống nhau khi deployment quy định rõ.

## 6. Những gì tuyệt đối không được công bố

Public JWKS không được chứa:

- RSA private exponent d;
- RSA factors p, q và CRT values dp, dq, qi, oth;
- EC/OKP private scalar/bytes d;
- Symmetric key material k;
- Private key PEM/PKCS#8 hoặc keystore password;
- Secret của KMS/HSM, credential truy cập key vault;
- Metadata nội bộ không cần thiết có thể tiết lộ đường dẫn, tài khoản, topology hoặc thông tin vận hành nhạy cảm.

Một sai sót nghiêm trọng là gọi toJSONString() trên private JWK/JWKSet rồi trả thẳng cho HTTP endpoint. **Private JWK có thể được dùng nội bộ để ký token; public JWKS phải là public-only representation.**

### 6.1. Public projection

Với Nimbus JOSE/JWT, JWK có API tạo public projection như toPublicJWK() và JWK Set có cách tạo public set tương ứng. Dùng đúng API của thư viện thay vì tự xóa một vài field bằng chuỗi JSON:

~~~java
// Ví dụ minh họa với Nimbus JOSE + JWT.
JWK privateSigningKey = loadPrivateSigningKey();

JWK publicSigningKey = privateSigningKey.toPublicJWK();

JWKSet publicJwkSet = new JWKSet(publicSigningKey);
String jsonForPublication = publicJwkSet.toString();
~~~

loadPrivateSigningKey() đại diện cho cơ chế đọc khóa từ keystore/KMS; không phải API có sẵn. Đoạn mã minh họa public projection, không thay thế endpoint chính thức của Spring Authorization Server. Với nhiều key, tạo JWK Set từ danh sách các public projection.

### 6.2. Kiểm tra tự động trước khi publish

Một validation job có thể kiểm tra:

1. Mọi JWK công bố có kty hợp lệ và kid duy nhất;
2. Không có trường private theo từng loại khóa;
3. Không có JWK oct chứa k;
4. use, key_ops, alg nhất quán;
5. RSA modulus/curve/coordinate có kích thước và format phù hợp;
6. Khóa được phép công bố và thuộc đúng issuer/environment;
7. JWKS không chứa khóa thử nghiệm hoặc key từ tenant khác.

Không chỉ kiểm tra tên field; hãy parse JWK bằng thư viện JOSE và xác minh public projection từ key material.

## 7. JWK Set Endpoint trong Spring Authorization Server

Spring Authorization Server sử dụng **JWKSource<SecurityContext>** làm nguồn khóa JWK. Khi cấu hình nguồn khóa phù hợp, token generator có thể sử dụng key material để ký JWT; JWK Set Endpoint cung cấp public keys cho consumer. Đường dẫn mặc định thường là **/oauth2/jwks**, có thể cấu hình thông qua AuthorizationServerSettings trong phiên bản hỗ trợ.

### 7.1. Tạo RSA key pair cho môi trường demo

Ví dụ dưới đây sinh khóa RSA trong bộ nhớ để minh họa:

~~~java
private static KeyPair generateRsaKey() throws GeneralSecurityException {
    KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
    generator.initialize(2048);
    return generator.generateKeyPair();
}
~~~

RSA 2048 là mức phổ biến được hỗ trợ rộng; policy tổ chức có thể yêu cầu kích thước lớn hơn hoặc thuật toán khác. **Không dùng cách sinh khóa mới mỗi lần ứng dụng production khởi động**, vì khi restart, AS sẽ mất private key cũ trong khi token cũ vẫn còn hạn.

### 7.2. Khai báo JWKSource

Ví dụ Nimbus JWKSource dùng RSA public/private key:

~~~java
@Bean
JWKSource<SecurityContext> jwkSource() throws GeneralSecurityException {
    KeyPair keyPair = generateRsaKey(); // Demo only; production loads managed key.

    RSAPublicKey publicKey = (RSAPublicKey) keyPair.getPublic();
    RSAPrivateKey privateKey = (RSAPrivateKey) keyPair.getPrivate();

    RSAKey rsaJwk = new RSAKey.Builder(publicKey)
        .privateKey(privateKey)
        .keyUse(KeyUse.SIGNATURE)
        .algorithm(JWSAlgorithm.RS256)
        .keyID("rsa-signing-demo-01")
        .build();

    JWKSet privateJwkSet = new JWKSet(rsaJwk);

    return (selector, context) -> selector.select(privateJwkSet);
}
~~~

Trong ví dụ, privateJwkSet được giữ **bên trong AS** để signer dùng private key. Khi công bố JWKS, endpoint phải trả **public projection**, không trả trực tiếp chuỗi private JWK này. Spring Authorization Server/Nimbus endpoint chính thức thực hiện logic công bố theo integration của phiên bản; nếu tự viết endpoint, phải chủ động chuyển thành public JWK Set và kiểm thử không rò private fields.

keyID("rsa-signing-demo-01") là giá trị cố định chỉ để minh họa. Production phải lấy kid từ key-management system/metadata ổn định, không sinh một ID khác mỗi lần restart cho cùng key.

### 7.3. Cấu hình đường dẫn JWK Set Endpoint

Có thể khai báo AuthorizationServerSettings:

~~~java
@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
        .issuer("https://identity.example.com")
        .jwkSetEndpoint("/oauth2/jwks")
        .build();
}
~~~

Đoạn cấu hình minh họa issuer và path; các endpoint khác dùng mặc định của phiên bản nếu không được override. Đường dẫn công khai cuối cùng còn phụ thuộc reverse proxy/context path. **Issuer phải khớp chính xác** với claim iss trong token và metadata mà Resource Server sử dụng.

### 7.4. SecurityFilterChain và khả năng truy cập

Khung Authorization Server chain thường dùng:

~~~java
@Bean
@Order(1)
SecurityFilterChain authorizationServerChain(HttpSecurity http)
        throws Exception {
    OAuth2AuthorizationServerConfigurer authorizationServer =
        OAuth2AuthorizationServerConfigurer.authorizationServer();

    http.securityMatcher(authorizationServer.getEndpointsMatcher())
        .with(authorizationServer, Customizer.withDefaults())
        .authorizeHttpRequests(auth ->
            auth.anyRequest().authenticated());

    return http.build();
}
~~~

Đây là khung filter chain; cần cấu hình các bean khác như RegisteredClientRepository, OAuth2AuthorizationService, issuer, JWKSource và chain login. Endpoint JWKS phải **có thể được Resource Server/consumer tải mà không cần user login** theo thiết kế public key distribution. Kiểm tra matcher/filter order của đúng phiên bản để không vô tình bảo vệ JWK Set Endpoint bằng form login hoặc redirect HTML.

Không mở public các endpoint quản trị key, upload key hoặc rotate key chỉ vì JWKS là endpoint public. **Chỉ GET public JWKS được công bố**; thao tác quản trị private key cần phân quyền và bảo vệ riêng.

## 8. Discovery và jwks_uri

Resource Server không nên hardcode một URL do token không tin cậy cung cấp. Nó cần biết **issuer tin cậy** và lấy endpoint keys từ metadata của issuer.

### 8.1. OAuth 2.0 Authorization Server Metadata

RFC 8414 định nghĩa metadata có thể chứa jwks_uri:

~~~json
{
  "issuer": "https://identity.example.com",
  "authorization_endpoint": "https://identity.example.com/oauth2/authorize",
  "token_endpoint": "https://identity.example.com/oauth2/token",
  "jwks_uri": "https://identity.example.com/oauth2/jwks"
}
~~~

### 8.2. OpenID Connect Discovery

Nếu AS bật OIDC Provider Configuration, tài liệu OpenID Provider metadata tại đường dẫn discovery tương ứng cũng công bố jwks_uri. jwks_uri là URL để consumer lấy JWK Set; **không phải một khóa**, cũng không phải URL mà JWT header tự quyết định.

### 8.3. Cấu hình Spring Resource Server

Một Resource Server có thể cấu hình issuer:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.com
~~~

Spring Security dùng metadata của issuer để tìm JWKS URI và xác minh issuer trong JWT theo cấu hình. Nếu muốn chỉ rõ JWKS URI, có thể cấu hình jwk-set-uri tương ứng; vẫn phải duy trì kiểm tra iss để tránh chỉ xác minh chữ ký từ một URL mà không ràng buộc issuer.

Ví dụ:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.com
          jwk-set-uri: https://identity.example.com/oauth2/jwks
~~~

Chỉ đặt jwk-set-uri không nên khiến ứng dụng bỏ qua issuer validation. Hãy kiểm tra behavior của phiên bản Spring Security/Boot và cấu hình validator nếu tự tạo JwtDecoder.

## 9. Resource Server chọn public key nào?

JWT JWS có protected header, ví dụ:

~~~json
{
  "alg": "RS256",
  "kid": "rsa-signing-2026-01",
  "typ": "JWT"
}
~~~

Khi verify:

1. Resource Server đã biết issuer/JWKS URI tin cậy.
2. Nó lấy hoặc sử dụng JWKS đã cache.
3. Đọc kid trong protected header.
4. Chọn public JWK phù hợp với kid, kty, alg và verifier policy.
5. Xác minh chữ ký.
6. Tiếp tục kiểm tra issuer, thời gian, audience và claims/quyền.

**Chữ ký hợp lệ chỉ chứng minh token được ký bằng private key tương ứng**, không tự chứng minh token dành cho API hiện tại hoặc có scope cần thiết.

### 9.1. kid không tìm thấy trong cache

Khi JWT mới có kid mà cache JWKS chưa có:

- Consumer có thể refresh JWKS theo cơ chế thư viện;
- Nếu key mới vẫn không có trong response, token phải bị từ chối;
- Không được fallback sang bất kỳ key nào khác chỉ để “cho request chạy”;
- Cần giám sát unknown-kid để phát hiện rotation lỗi hoặc token giả mạo.

Tránh refresh JWKS không giới hạn theo mỗi request có kid lạ, vì attacker có thể gây **JWKS refresh storm**. Dùng cache, refresh throttling và timeout hợp lý.

### 9.2. kid trùng nhau

Hai key khác nhau cùng kid có thể khiến verifier chọn nhầm hoặc xử lý không nhất quán. Mỗi JWK Set nên bảo đảm kid duy nhất trong phạm vi set; không tái sử dụng ID cho key pair mới khi key cũ vẫn còn được công bố.

### 9.3. Token không có kid

Một JWK Set chỉ có một khóa phù hợp có thể cho phép một số verifier chọn khóa theo thuật toán, nhưng không nên dựa vào hành vi này trong hệ thống rotation. Với nhiều key, token không có kid có thể không xác định được khóa và bị từ chối. **AS nên phát kid nhất quán** trong JWT header.

## 10. Rotation: công bố khóa cũ và khóa mới

Khóa ký không nên tồn tại mãi. Khi rotation, AS phải thay private signing key và cập nhật public JWKS mà không làm các Resource Server từ chối token hợp lệ đã phát trước đó.

### 10.1. Vì sao không xóa khóa cũ ngay?

Giả sử:

- Khóa K1 ký token tới 10:00;
- AS chuyển sang ký token mới bằng K2 lúc 10:00;
- Token cũ ký bằng K1 còn hiệu lực đến 10:10.

Nếu JWKS bỏ K1 ngay lúc 10:00, Resource Server mới tải JWKS sẽ không xác minh được token cũ dù token vẫn trong exp. Vì vậy, **giữ public K1 trong JWKS trong khoảng overlap** đủ dài cho token cũ hết hạn và cache consumer cập nhật.

### 10.2. Quy trình rotation đề xuất

~~~mermaid
flowchart TD
    A[Đang ký bằng K1; JWKS có K1] --> B[Tạo K2 trong KMS/HSM hoặc keystore]
    B --> C[Publish public K2 vào JWKS, vẫn giữ K1]
    C --> D[Đợi consumer tải K2; kiểm tra key visibility]
    D --> E[Chuyển signer sang private K2; JWT mới có kid K2]
    E --> F[Giữ public K1 trong overlap window]
    F --> G[Token K1 hết hạn + cache grace hoàn tất]
    G --> H[Loại public K1 khỏi JWKS]
    H --> I[Hủy/archival private K1 theo key lifecycle]
~~~

Trình tự trên là **rotation bình thường**. Nếu K1 bị compromise, không thể chờ overlap như lịch thường: phải ngừng ký bằng K1, loại/deny key theo incident response và chấp nhận cần xử lý các token đang mang chữ ký K1 theo mức rủi ro. Kế hoạch khẩn cấp khác kế hoạch rotation định kỳ.

### 10.3. Tính thời gian overlap

Khoảng overlap cần xét:

- Thời hạn tối đa của token ký bằng K1;
- Clock skew được chấp nhận ở Resource Server;
- Cache TTL/refresh behavior của JWKS consumer;
- Độ trễ replication/deployment;
- Thời gian request đang xử lý hoặc hệ thống downstream còn giữ token;
- SLA vận hành khi consumer không thể tải JWKS.

Không đặt overlap chỉ bằng TTL của access token nếu cache JWKS hoặc clock skew có thể khiến consumer vẫn cần K1 lâu hơn.

### 10.4. Không xoay kid mà không xoay key

Nếu cùng key pair nhưng kid thay đổi, token cũ vẫn chứa kid cũ. Khi JWKS chỉ công bố ID mới, verifier không thể tìm key cũ theo header token. Khi key pair thay đổi, cấp kid mới; khi key pair không đổi, giữ kid ổn định.

## 11. Bảo vệ private key và nguồn khóa trong production

Ví dụ sinh RSA key trong bean chỉ phù hợp học tập/test. Production cần quản lý vòng đời private key:

| Nguồn khóa | Khi phù hợp | Kiểm soát |
|---|---|---|
| Java KeyStore (PKCS12/JKS) | Hạ tầng ứng dụng quản lý keystore | Bảo vệ password, file permissions, backup, rotation |
| HSM | Khóa ký cần bảo vệ bằng phần cứng | Access policy, audit, HA và quy trình backup/restore |
| Cloud KMS | Hạ tầng cloud có key management | IAM tối thiểu, key version, signing permission, audit |
| Secret manager + encrypted key | Hệ thống nhỏ hơn có kho bí mật được quản lý | Mã hóa, phân quyền, rotation, tránh lộ trong env/log |
| Ephemeral in-memory key | Unit test/dev ngắn hạn | Không dùng cho production hoặc token cần sống qua restart |

### 11.1. Tách quyền ký và quyền đọc public key

- Chỉ Authorization Server hoặc signing service được cấp quyền sign.
- Resource Server chỉ cần public key để verify.
- Không cấp private key cho tất cả microservices “để tiện”.
- Endpoint JWKS không phải endpoint lấy private key.
- Nếu KMS hỗ trợ sign operation, AS có thể ký mà private key không xuất khỏi KMS; public key vẫn được công bố qua JWKS.

### 11.2. Phân tách môi trường

Không dùng cùng key pair cho development, staging và production nếu có thể tránh. Mỗi issuer/environment nên có key set riêng; nếu staging private key bị lộ, không được ảnh hưởng khả năng giả mạo token production. Metadata issuer và JWKS URI phải chỉ rõ môi trường.

### 11.3. Quyền đọc JWKS và quyền quản trị key

JWKS public có thể đọc rộng rãi, nhưng các thao tác sau cần phân quyền nghiêm:

- Upload hoặc đăng ký key pair;
- Chọn signing key hiện hành;
- Thu hồi key;
- Thay đổi kid, alg, use, key purpose;
- Thay đổi KMS key policy hoặc service identity;
- Export private key/backup.

Không dùng một endpoint public JWKS làm giao diện quản trị. Tách API quản trị và yêu cầu xác thực mạnh/audit.

## 12. Thuật toán, key type và chính sách xác minh

| Token signing algorithm | JWK key type | Public members thường dùng | Lưu ý |
|---|---|---|---|
| RS256 / PS256 | RSA | n, e | Kiểm tra modulus đủ mạnh, allowlist đúng |
| ES256 | EC | crv=P-256, x, y | Curve và thuật toán phải khớp |
| EdDSA | OKP | crv, x | Chỉ dùng khi thư viện và verifier hỗ trợ |
| HS256 | oct | k | k là secret, không công bố public JWKS |

### 12.1. Không dùng alg do token tự chọn

Verifier phải có policy thuật toán cho issuer, ví dụ chỉ cho phép RS256. Không chấp nhận:

- alg=none;
- HMAC khi issuer được thiết kế dùng RSA/EC mà verifier lại dùng public key như HMAC secret;
- Thuật toán yếu hoặc không còn được policy chấp thuận;
- JWK từ issuer khác hoặc URL do token header tự chỉ định.

### 12.2. use, key_ops và alg phải nhất quán

Ví dụ public signing JWK:

~~~json
{
  "kty": "RSA",
  "kid": "rsa-verify-01",
  "use": "sig",
  "key_ops": ["verify"],
  "alg": "RS256",
  "n": "PUBLIC_MODULUS",
  "e": "AQAB"
}
~~~

Không đưa key_ops sign vào public JWK để gợi ý consumer ký bằng khóa public. Nếu trường alg không được công bố, verifier vẫn phải có allowlist và xác định thuật toán theo cấu hình tin cậy.

### 12.3. Một key cho nhiều thuật toán?

Không nên mặc nhiên dùng một key pair cho nhiều thuật toán/đích khác nhau. Nếu cùng key có nhiều alg hoặc mục đích, cần kiểm tra profile, JWA constraints và cách consumer lựa chọn. Tách key theo mục đích/algorithm thường dễ kiểm toán, rotation và thu hồi hơn.

## 13. Cache JWKS và khả năng sẵn sàng

Resource Server thường cache JWKS để không tải endpoint ở mọi API request. Điều này cải thiện latency và giảm tải, nhưng ảnh hưởng trực tiếp đến key rotation.

### 13.1. Cache quá lâu

Nếu JWKS cache quá lâu, consumer có thể không thấy K2 khi AS bắt đầu ký token mới bằng K2. JWT mới mang kid=K2 sẽ bị từ chối. Khi rotation, cần:

1. Publish public K2 trước;
2. Đợi thời gian để consumer refresh/cache K2;
3. Sau đó mới ký token mới bằng K2.

### 13.2. Cache quá ngắn

Cache quá ngắn gây nhiều request tới JWKS endpoint, tăng độ phụ thuộc network và tạo tải khi nhiều service đồng thời refresh. Cần TTL hợp lý, HTTP cache headers (ví dụ Cache-Control, ETag/conditional requests nếu hỗ trợ), timeout và retry có giới hạn.

**Không giả định Spring Authorization Server luôn trả một TTL cache cụ thể** cho mọi phiên bản/cấu hình. Hãy kiểm tra HTTP response thực tế và cấu hình reverse proxy/CDN nếu có.

### 13.3. Unknown kid và refresh storm

Nếu mỗi request với kid lạ đều kích hoạt tải JWKS, attacker có thể gửi nhiều JWT giả với kid ngẫu nhiên để làm quá tải AS. Consumer nên có refresh throttling/single-flight, timeout, giới hạn retry và từ chối token khi không tìm thấy key sau lần refresh hợp lý.

### 13.4. JWKS endpoint không khả dụng

Khi JWKS endpoint tạm ngừng:

- Consumer đã cache public key có thể tiếp tục verify token theo policy/cache;
- Consumer khởi động mới hoặc gặp kid chưa cache có thể không verify được;
- Không fallback sang một issuer/key tùy ý;
- Cần HA, backup, monitoring và kế hoạch phục hồi endpoint.

Không dùng cache stale vô hạn nếu key có thể đã bị compromise; freshness policy cần cân bằng tính sẵn sàng và khả năng thu hồi key.

## 14. JWK Set Endpoint và OIDC/OAuth metadata

Một hệ thống nên công bố metadata nhất quán:

| Metadata | Ý nghĩa |
|---|---|
| issuer | Định danh issuer, phải khớp claim iss |
| jwks_uri | URL JWK Set Endpoint |
| authorization_endpoint | Endpoint authorization |
| token_endpoint | Endpoint cấp token |
| revocation_endpoint | Endpoint thu hồi token nếu hỗ trợ |
| introspection_endpoint | Endpoint introspection nếu hỗ trợ |
| pushed_authorization_request_endpoint | PAR endpoint nếu hỗ trợ |

Discovery giúp client/Resource Server tìm endpoint mà không hardcode tùy tiện. Tuy nhiên, **discovery metadata phải lấy từ issuer tin cậy**; không lấy jwks_uri từ một token không tin cậy hoặc query parameter của caller.

### 14.1. Issuer URL phải ổn định

Nếu AS đổi issuer hoặc reverse proxy tạo URL khác giữa metadata và JWT iss, Resource Server có thể từ chối token. Cần cấu hình public issuer chính xác, xử lý forwarded headers từ proxy tin cậy và test metadata/JWKS từ góc nhìn bên ngoài cluster.

### 14.2. Không dùng jku trong token header làm trust anchor

JWT có thể chứa header như jku hoặc x5u; không để token tự chọn một URL tùy ý để verifier tải key. Resource Server phải dùng JWKS URI từ issuer đã cấu hình/discovery tin cậy, hoặc cơ chế trust được provision rõ ràng.

## 15. Kiểm thử JWK Set Endpoint

Kiểm thử cần chứng minh **endpoint trả public-only JWKS**, token được ký bằng private key tương ứng và Resource Server xác minh được token qua kid. Một HTTP 200 đơn lẻ chưa đủ.

### 15.1. Ma trận kiểm thử

| Kịch bản | Kết quả cần xác minh |
|---|---|
| GET JWK Set Endpoint | Trả JSON object có keys array |
| Không có login cookie | Public JWKS vẫn truy cập được theo thiết kế |
| RSA signing key | Chỉ công bố kty, kid, n, e và metadata cần thiết |
| EC signing key | Chỉ công bố crv, x, y và metadata |
| OKP signing key | Chỉ công bố crv, x và metadata |
| Private RSA field xuất hiện | Test phải **fail** |
| EC/OKP private d xuất hiện | Test phải **fail** |
| Symmetric JWK oct/k xuất hiện | Test phải **fail** |
| kid trùng | Từ chối cấu hình hoặc phát hiện lỗi trước publish |
| use/key_ops mâu thuẫn | Validation phải phát hiện |
| alg không được cho phép | Resource Server từ chối token |
| JWT có kid hợp lệ | Verifier chọn đúng public key và verify |
| JWT có kid lạ | Refresh JWKS có kiểm soát rồi từ chối nếu không tìm thấy |
| Rotation K1 → K2 | Consumer verify được token cũ và token mới trong overlap |
| Loại K1 quá sớm | Test phát hiện token cũ bị lỗi verify |
| JWKS endpoint outage | Consumer hành xử đúng cache/fail policy |
| Metadata jwks_uri sai issuer | Integration test phải phát hiện mismatch |
| JWT aud sai | RS từ chối dù chữ ký đúng |

### 15.2. MockMvc test endpoint trả JWKS

Ví dụ khung kiểm thử:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class JwkSetEndpointTests {

    @Autowired
    MockMvc mvc;

    @Test
    void jwksEndpointReturnsPublicKeySet() throws Exception {
        mvc.perform(get("/oauth2/jwks")
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.keys").isArray())
            .andExpect(jsonPath("$.keys[0].kty").value("RSA"))
            .andExpect(jsonPath("$.keys[0].kid").isNotEmpty())
            .andExpect(jsonPath("$.keys[0].n").isNotEmpty())
            .andExpect(jsonPath("$.keys[0].e").isNotEmpty())
            .andExpect(jsonPath("$.keys[0].d").doesNotExist())
            .andExpect(jsonPath("$.keys[0].p").doesNotExist())
            .andExpect(jsonPath("$.keys[0].q").doesNotExist());
    }
}
~~~

Đây là **khung test** cần imports, JWKSource bean, signing key fixture và cấu hình SecurityFilterChain. Test giả định khóa đầu tiên là RSA; nếu JWKS có nhiều key/không bảo đảm thứ tự, nên tìm phần tử theo kid thay vì cố định index [0]. Cần bổ sung kiểm tra EC/OKP/symmetric keys nếu ứng dụng hỗ trợ.

### 15.3. Kiểm thử public projection ở mức JWK

Một unit test bổ sung có thể parse response thành Nimbus JWKSet, rồi xác minh:

~~~java
JWKSet publicSet = JWKSet.parse(jwksJson);

for (JWK jwk : publicSet.getKeys()) {
    assertThat(jwk.isPrivate()).isFalse();
    assertThat(jwk.getKeyID()).isNotBlank();
    assertThat(jwk.getKeyType()).isNotNull();
}
~~~

Đây là minh họa với Nimbus JOSE/JWT; cần xác nhận API của version thư viện trong dự án. isPrivate() là một kiểm tra hữu ích nhưng không thay việc kiểm tra schema/field theo từng key type. Với oct, cần đảm bảo không có key material k được công bố.

### 15.4. Kiểm thử end-to-end ký và xác minh

1. Phát một JWT access token từ AS bằng private key K1.
2. Đọc JWT header, xác minh kid=K1.
3. Tải JWKS từ public endpoint và tìm JWK có K1.
4. Dùng public key đó verify chữ ký.
5. Xác minh thêm iss, exp, aud, scope và token profile.
6. Rotation sang K2, lặp lại với token mới; token K1 vẫn verify trong overlap.
7. Sau khi K1 được loại bỏ, kiểm thử token K1 đã hết hạn không còn cần được chấp nhận; xác minh behavior theo cache policy.

Không chỉ test bằng cách gọi JwtDecoder đã được mock; cần một integration test dùng public JWKS endpoint thật hoặc môi trường tương đương.

## 16. Quan sát và vận hành

| Metric/event | Mục tiêu | Lưu ý |
|---|---|---|
| JWKS request count/latency | Biết mức sử dụng và hiệu năng endpoint | Phân biệt consumer bình thường và refresh storm |
| Unknown kid | Phát hiện rotation sai hoặc token giả | Không log toàn bộ token |
| Signature verification failures | Phát hiện token sai key/issuer/alg | Phân loại clock/issuer/rotation |
| Active signing key ID | Biết AS đang ký bằng key nào | Chỉ log kid, không log private material |
| Rotation started/completed | Theo dõi overlap và loại key cũ | Ghi audit ai phê duyệt |
| JWKS publish version | So sánh các node/cache | Không dùng private key fingerprint trong metric công khai |
| KMS/HSM signing failures | Theo dõi khả năng phát token | Cảnh báo latency/error và fallback policy |
| Key expiry/certificate expiry | Tránh cert hết hạn ngoài dự kiến | Alert trước theo quy trình |

### 16.1. Audit key lifecycle

Các hành động tạo, import, activate, deactivate, rotate, revoke hoặc destroy key cần audit: actor quản trị, key ID, algorithm, purpose, thời điểm, approval/change ticket và kết quả. **Không ghi private key, keystore password, HSM credential hoặc raw secret** vào audit.

### 16.2. Khi phát hiện private key bị lộ

Incident response cần:

1. Dừng dùng key bị compromise để ký token mới;
2. Tạo/activate key mới và cập nhật JWKS theo quy trình khẩn cấp;
3. Đánh giá token đã phát dưới kid bị lộ;
4. Thu hồi/deny token hoặc giảm TTL theo SLA và khả năng RS;
5. Thông báo/cập nhật consumer cache và xử lý unknown kid;
6. Điều tra nguồn lộ, quyền truy cập KMS/HSM, backup và pipeline;
7. Lưu audit và bằng chứng theo chính sách.

Trong incident, **không giữ public key cũ chỉ để tránh lỗi tương thích nếu private key đã bị compromise và attacker có thể ký token giả**. Quyết định loại bỏ khẩn cấp cần đi cùng cơ chế từ chối token ký bằng key đó; nếu chỉ xóa khỏi JWKS nhưng RS vẫn cache key, một số consumer có thể tiếp tục tin token giả cho tới khi cache hết hạn.

## 17. Những lỗi triển khai thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Trả nguyên private JWKSet ra endpoint | Lộ private key, attacker ký token giả | Chỉ publish public projection |
| Công bố d, p, q, dp, dq, qi, oth | Lộ RSA private material | Field validation theo loại key |
| Công bố EC/OKP d | Lộ private scalar/bytes | Loại bỏ private fields |
| Công bố oct.k | Lộ secret cho mọi consumer | Không publish symmetric key trong public JWKS |
| Dùng một key pair cho mọi môi trường | Compromise lan sang production | Tách key/issuer theo environment |
| Sinh key mới mỗi lần restart | Token cũ không verify được | Lưu key bền vững trong KMS/HSM/keystore |
| kid thay đổi ngẫu nhiên | Consumer không tìm được key cho token cũ | kid ổn định theo key pair |
| Xóa key cũ ngay khi rotate | JWT cũ lỗi signature | Overlap theo token TTL và cache |
| Không công bố K2 trước khi ký bằng K2 | RS chưa biết public key mới | Publish → warm cache → switch signer |
| Tin jku/x5u do token chỉ định | SSRF/key substitution | JWKS URI từ issuer trust anchor |
| Chỉ kiểm tra chữ ký, bỏ audience | Token API A dùng được ở API B | Validate aud và scope |
| Dùng oct trong public JWKS | Lộ secret cho phân tán | Dùng asymmetric signing cho phân tán |
| alg không allowlist | Algorithm confusion/downgrade | Allowlist theo issuer/resource |
| JWKS endpoint yêu cầu user login | Resource Server không tải được key | Cho phép đọc public JWKS theo thiết kế |
| Unknown kid gây fetch vô hạn | JWKS refresh DoS | Cache, throttling, timeout |
| Chỉ test HTTP 200 | Không phát hiện private field hoặc rotation bug | Test schema, verify token và rotation |

## 18. Checklist trước khi đưa JWK Set Endpoint vào production

1. **Key source:** private key được lưu trong KMS/HSM/keystore có phân quyền, backup và rotation?
2. **Public-only:** JWKS không chứa d, RSA CRT fields, EC/OKP d hoặc symmetric k?
3. **Key metadata:** kty, kid, use, key_ops, alg tương thích và có kid duy nhất?
4. **Key purpose:** khóa ký và khóa mã hóa được phân biệt, không dùng sai mục đích?
5. **Endpoint:** public JWKS GET hoạt động không cần login, không mở API quản trị key?
6. **Discovery:** jwks_uri lấy từ issuer tin cậy và khớp endpoint thực tế?
7. **Issuer:** metadata issuer khớp chính xác claim iss và public URL sau proxy?
8. **Verifier:** RS kiểm tra signature, issuer, algorithm allowlist, expiry, audience và scope?
9. **Rotation:** publish key mới trước khi ký, giữ key cũ đủ overlap, không tái sử dụng kid?
10. **Cache:** có TTL/refresh throttling, xử lý unknown kid, outage và stale key?
11. **Multi-node:** tất cả AS node có key set nhất quán và signing key hiện hành giống nhau?
12. **Incident response:** có thể ngừng ký bằng key compromised, loại key và xử lý token đã phát?
13. **Testing:** endpoint response public-only, end-to-end verify và rotation đều có test?
14. **Audit:** thay đổi key được ghi nhận nhưng private material không xuất hiện trong log?

## 19. Bài tập vận dụng

**Tình huống A — Public JWKS lộ private key.** Một response có kty=RSA, n, e, d, p, q. Hãy giải thích mức độ nghiêm trọng, các hành động incident response và vì sao chỉ xóa field khỏi endpoint chưa đủ nếu private key đã bị tải.

**Tình huống B — Rotation K1 sang K2.** Access token ký bằng K1 có TTL 10 phút, JWKS cache tối đa 30 phút. Khi nào nên publish K2, chuyển signer và loại K1? Nêu các điều kiện bổ sung về clock skew/replication.

**Tình huống C — Unknown kid.** API nhận hàng nghìn token giả với kid ngẫu nhiên. Làm sao refresh JWKS có giới hạn mà vẫn nhận biết key mới hợp lệ?

**Tình huống D — Hai Resource Server.** orders-api và billing-api cùng tin issuer. Vì sao chữ ký hợp lệ chưa đủ để billing-api chấp nhận token dành cho orders-api?

**Gợi ý:** A là compromise private key: ngừng ký, rotate khẩn cấp, xử lý token KID cũ và cache. B cần publish K2 trước, đợi consumer nhận key, switch signer, giữ K1 ít nhất theo token lifetime cộng cache/clock/replication margin. C dùng cache, single-flight/throttle, timeout và từ chối nếu key vẫn không tồn tại. D phải kiểm tra audience, scope và quyền API.

## 20. Tổng kết

**JWK Set Endpoint** công bố tập **public JWK** để Resource Server và OIDC Relying Party xác minh chữ ký token do Authorization Server phát hành. JWK Set là JSON object có mảng keys; mỗi JWK cần kty và có thể có kid, use, key_ops, alg, certificate metadata cùng các public parameters theo loại khóa.

Với **RSA**, public parameters chính là n và e; với **EC** là crv, x, y; với **OKP** là crv, x. Những trường private như RSA d/p/q/dp/dq/qi/oth, EC/OKP d và symmetric oct.k tuyệt đối không được xuất hiện trong public JWKS.

Trong **Spring Authorization Server**, JWKSource<SecurityContext> cung cấp nguồn khóa cho token generation và JWK Set Endpoint trong phiên bản/cấu hình hỗ trợ. Production cần lưu private key an toàn, giữ kid ổn định, công bố jwks_uri qua metadata tin cậy, và rotation theo quy trình **publish key mới → chuyển signer → giữ key cũ trong overlap → loại key cũ khi an toàn**.

Resource Server phải xác minh chữ ký cùng issuer, thời hạn, audience, thuật toán và scope. JWK Set Endpoint là thành phần public của trust distribution, nhưng **trust anchor vẫn là issuer đã được cấu hình tin cậy**, không phải bất kỳ URL hoặc key nào do token tự khai.

## 21. Tài liệu tham khảo

- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): JWK/JWK Set, kty, use, key_ops, alg, kid, X.509 fields và public/private parameters.
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518): RSA, EC, HMAC và thuật toán JWS/JWE.
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515): protected header, kid, thuật toán và xác minh chữ ký.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): jwks_uri, issuer và discovery metadata.
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html): OpenID Provider metadata và jwks_uri.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): JWT access token profile và validation.
- [Spring Authorization Server Reference](https://docs.spring.io/spring-authorization-server/reference/): JWKSource, token generation, AuthorizationServerSettings và JWK Set Endpoint.
- [Spring Security Resource Server — JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): issuer/JWK Set URI, JwtDecoder và validation.
- [Nimbus JOSE + JWT](https://connect2id.com/products/nimbus-jose-jwt): JWK/JWKSet, public projection và JOSE implementation.
