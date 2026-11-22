# JWK, JWK Set, JWKSource và khóa phục vụ ký token

## 1. Bối cảnh và mục tiêu

Trong **OAuth 2.0/OpenID Connect (OIDC) Authorization Server** xây dựng bằng **Spring Security**, **Spring Authorization Server** và **Spring Boot**, access token dạng JWT thường được ký bằng khóa riêng của Authorization Server. Resource Server dùng khóa công khai tương ứng để xác minh chữ ký trước khi tin các claims như issuer, audience, subject, scope và thời hạn.

Để các thành phần trao đổi khóa theo một định dạng thống nhất, hệ sinh thái JOSE sử dụng **JSON Web Key (JWK)** và **JSON Web Key Set (JWKS)**:

- **JWK** mô tả một khóa mật mã cùng metadata cần thiết để sử dụng khóa.
- **JWK Set** là tập hợp nhiều JWK, thường được công bố tại một endpoint để client và Resource Server lấy các khóa công khai.
- **JWKSource** là abstraction cung cấp các khóa theo một bộ chọn (selector), thường được dùng bởi encoder ký JWT và JWK Set endpoint.
- **Signing key** là khóa dùng để tạo chữ ký JWS; với mô hình bất đối xứng, private key được giữ tại Authorization Server còn public key được công bố cho bên xác minh.

Ví dụ xuyên suốt: Authorization Server phát hành JWT access token cho <code>orders-web</code>. Token có header chứa <code>kid</code> để nhận diện khóa ký. Orders API tải JWKS từ Authorization Server, tìm public key có <code>kid</code> tương ứng, xác minh chữ ký, rồi kiểm tra issuer, audience, expiry và scope. Khi Authorization Server xoay khóa, API cần nhận public key mới mà vẫn xác minh được token cũ còn hạn.

Sau bài học, bạn có thể:

1. Phân biệt JWK, JWK Set, JWKS endpoint và <code>JWKSource&lt;SecurityContext&gt;</code>.
2. Hiểu các trường JWK như <code>kty</code>, <code>use</code>, <code>alg</code>, <code>kid</code> và các tham số public/private.
3. Tạo JWK RSA cho mục đích ký JWT và cấu hình nguồn khóa cho Spring Authorization Server.
4. Giải thích mối quan hệ giữa <code>JWKSource</code>, <code>JwtEncoder</code>, <code>JwtGenerator</code> và JWK Set endpoint.
5. Công bố public JWK qua endpoint và discovery metadata để Resource Server lấy khóa xác minh.
6. Xây dựng quy trình rotation, giữ khóa cũ trong giai đoạn tương thích và loại bỏ khóa an toàn.
7. Bảo vệ private key bằng secret manager, KMS hoặc HSM, xử lý sự cố compromise và kiểm thử rotation.

**Phạm vi phiên bản:** Ví dụ Java dùng API Spring Authorization Server 1.x/Spring Security 6.x trên Servlet stack. Các bản Spring Security mới tích hợp Authorization Server có thể thay đổi package hoặc cách cấu hình. Nimbus JOSE + JWT là thư viện JOSE thường được Spring Security sử dụng; hãy kiểm tra dependency/version của ứng dụng trước khi copy ví dụ.

## 2. JWK và JWK Set là gì?

### 2.1. JWK: biểu diễn một khóa

JWK là cấu trúc JSON mô tả một khóa theo RFC 7517. Một JWK RSA công khai dùng để xác minh chữ ký có thể trông như sau:

~~~json
{
  "kty": "RSA",
  "use": "sig",
  "alg": "RS256",
  "kid": "as-signing-2026-01",
  "n": "base64url-encoded-modulus",
  "e": "AQAB"
}
~~~

Đây là dữ liệu minh họa; <code>n</code> và <code>e</code> không phải giá trị khóa thật. Các trường:

| Trường | Ý nghĩa |
| --- | --- |
| <code>kty</code> | Loại khóa, ví dụ <code>RSA</code>, <code>EC</code>, <code>OKP</code> hoặc <code>oct</code>. |
| <code>use</code> | Mục đích sử dụng, thường <code>sig</code> cho ký/xác minh hoặc <code>enc</code> cho mã hóa/giải mã. |
| <code>alg</code> | Thuật toán JOSE dự kiến, ví dụ <code>RS256</code> hoặc <code>ES256</code>. |
| <code>kid</code> | Key ID, giúp bên nhận chọn đúng khóa trong một tập nhiều khóa. |
| <code>n</code>, <code>e</code> | Tham số public của RSA: modulus và public exponent. |

Không phải mọi trường đều bắt buộc cho mọi loại JWK. Các tham số private như <code>d</code>, <code>p</code>, <code>q</code>, <code>dp</code>, <code>dq</code>, <code>qi</code> trong RSA hoặc <code>d</code> trong EC/OKP phải được bảo vệ. Một public JWK RSA chỉ cần các tham số công khai thích hợp; **không đưa private parameters vào JWKS công khai**.

### 2.2. JWK Set: một tập hợp các khóa

JWK Set là một JSON object chứa mảng <code>keys</code>. Ví dụ khi Authorization Server đang công bố khóa hiện tại và khóa cũ để xác minh token chưa hết hạn:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "use": "sig",
      "alg": "RS256",
      "kid": "as-signing-2026-02",
      "n": "public-modulus-for-new-key",
      "e": "AQAB"
    },
    {
      "kty": "RSA",
      "use": "sig",
      "alg": "RS256",
      "kid": "as-signing-2025-12",
      "n": "public-modulus-for-previous-key",
      "e": "AQAB"
    }
  ]
}
~~~

Một JWKS có thể chứa nhiều khóa vì hệ thống cần hỗ trợ nhiều thuật toán, nhiều issuer key hoặc giai đoạn rotation. Thứ tự phần tử không nên được dùng để quyết định khóa nào là khóa hiện tại; hãy dựa vào <code>kid</code>, <code>alg</code> và chính sách xác minh.

### 2.3. JWK, JWK Set và JWKS endpoint khác nhau

| Khái niệm | Vai trò |
| --- | --- |
| **JWK** | Một khóa cùng metadata. |
| **JWK Set** | Tập hợp nhiều JWK trong một cấu trúc JSON. |
| **JWKS** | Cách viết tắt phổ biến của JSON Web Key Set; không phải một loại khóa riêng. |
| **JWKS endpoint** | URL HTTP mà Authorization Server công bố để trả public JWK Set. |
| **JWKSource** | API phía server cung cấp khóa cho encoder/filter theo selector; không phải URL HTTP. |

Ví dụ, <code>https://auth.example.com/oauth2/jwks</code> có thể là JWKS endpoint, còn <code>JWKSource&lt;SecurityContext&gt;</code> là bean Java trong ứng dụng Authorization Server.

## 3. Khóa ký token: public key và private key

### 3.1. Mô hình chữ ký bất đối xứng

Với JWS dùng thuật toán bất đối xứng như RS256:

~~~mermaid
flowchart LR
    A["Authorization Server"] --> B["JWT Header + Claims"]
    B --> C["Ký bằng RSA private key"]
    C --> D["JWT: header.payload.signature"]
    D --> E["Client / Resource Server"]
    E --> F["Lấy public key từ JWKS"]
    F --> G["Xác minh chữ ký + kiểm tra claims"]
~~~

Private key chỉ dùng trong vùng tin cậy của Authorization Server để ký. Public key có thể được công bố để Resource Server xác minh. Người có public key **không thể suy ra private key** nếu thuật toán và kích thước khóa được chọn an toàn.

**JWT ký không đồng nghĩa JWT được mã hóa.** JWS compact thường có ba phần phân tách bằng dấu chấm; header và payload có thể đọc được sau Base64URL decoding. Không đưa mật khẩu, client secret, private key hoặc dữ liệu nhạy cảm không cần thiết vào JWT chỉ vì token đã được ký.

### 3.2. Ký khác mã hóa

| Mục đích | JWK metadata thường gặp | Khả năng |
| --- | --- | --- |
| Ký JWS | <code>use=sig</code>, thuật toán JWS như <code>RS256</code> | Bên nhận xác minh tính toàn vẹn và nguồn ký. |
| Mã hóa JWE | <code>use=enc</code>, thuật toán/key management và content encryption phù hợp | Bảo vệ tính bí mật của nội dung cho bên nhận. |

Bài này tập trung vào **khóa ký access token/ID Token**. Không dùng public/private signing key để thay thế tùy tiện cho key encryption; cũng không dùng <code>alg=none</code> hoặc thuật toán yếu để làm cho việc triển khai đơn giản hơn.

### 3.3. Chọn loại khóa và thuật toán

| Loại khóa/thuật toán | Ghi chú |
| --- | --- |
| RSA + RS256 | Phổ biến, tương thích rộng; nên dùng modulus ít nhất 2048 bit, cân nhắc 3072 bit theo chính sách. |
| EC P-256 + ES256 | Chữ ký ngắn hơn; cần các thư viện và Resource Server hỗ trợ đúng curve/algorithm. |
| Ed25519/EdDSA | Có thể phù hợp cho hệ thống hỗ trợ; cần xác minh mức tương thích của toàn bộ stack và chính sách triển khai. |
| HMAC như HS256 | Cùng secret được chia sẻ giữa bên ký và xác minh; không phù hợp mô hình công bố JWKS public cho nhiều Resource Server độc lập nếu không muốn chia sẻ quyền ký. |

Không chọn thuật toán dựa trên header do token gửi đến. Resource Server phải cấu hình allow-list thuật toán tin cậy, đồng thời kiểm tra key type/curve/use phù hợp. Đối với Authorization Server có nhiều Resource Server, chữ ký bất đối xứng thường thuận lợi hơn vì chỉ public key được phân phối.

## 4. Các tham số JWK quan trọng

### 4.1. Metadata chung

| Tham số | Ý nghĩa và lưu ý |
| --- | --- |
| <code>kty</code> | Loại khóa. Phải phù hợp thuật toán và các tham số khóa. |
| <code>kid</code> | Định danh duy nhất trong phạm vi key set theo chính sách. Cần thay khi tạo khóa mới. |
| <code>use</code> | <code>sig</code> cho signing/verification, <code>enc</code> cho encryption/decryption. |
| <code>key_ops</code> | Các thao tác được phép, ví dụ <code>sign</code>, <code>verify</code>, <code>encrypt</code>, <code>decrypt</code>. Phải tương thích với <code>use</code>. |
| <code>alg</code> | Thuật toán JOSE dự kiến; không phải bằng chứng rằng bên nhận phải chấp nhận thuật toán đó. |
| <code>kid</code> | Được đặt trong JWT protected header để bên xác minh chọn key tương ứng. |
| <code>x5c</code> | Certificate chain nếu có; phải kiểm tra trust/certificate policy riêng. |
| <code>x5t</code>, <code>x5t#S256</code> | Thumbprint của certificate theo quy ước tương ứng. |

Trong danh sách trên, <code>kid</code> được nhắc lại vì đây là trường thường gây lỗi khi rotation. Không tái sử dụng một <code>kid</code> cho hai khóa khác nhau: Resource Server có thể cache key theo ID và xác minh nhầm hoặc không làm mới đúng khóa.

### 4.2. Tham số RSA

Public JWK RSA thường chứa:

- <code>n</code>: modulus.
- <code>e</code>: public exponent.

Private JWK RSA có thể còn chứa:

- <code>d</code>: private exponent.
- <code>p</code>, <code>q</code>: các thừa số nguyên tố.
- <code>dp</code>, <code>dq</code>, <code>qi</code>: tham số CRT.

Các trường private **không được xuất hiện trong response JWKS công khai**. Không in một JWK object đầy đủ vào log debug nếu object đó có private key.

### 4.3. Public JWK và private JWK

Một JWK được dựng từ cặp RSA key có thể chứa cả public và private material ở phía server:

~~~java
RSAKey signingJwk = new RSAKey.Builder(publicKey)
    .privateKey(privateKey)
    .keyID("as-signing-2026-01")
    .keyUse(KeyUse.SIGNATURE)
    .algorithm(JWSAlgorithm.RS256)
    .build();

JWK publicOnly = signingJwk.toPublicJWK();
~~~

<code>signingJwk</code> có private key để server ký; <code>publicOnly</code> chỉ giữ phần công khai. Phía endpoint công khai chỉ được trả public representation. Không serialize <code>signingJwk</code> nguyên trạng vào HTTP response hoặc cấu hình client.

## 5. JWKSource là gì và được dùng như thế nào?

### 5.1. Hợp đồng JWKSource

<code>JWKSource&lt;C&gt;</code> là abstraction của Nimbus JOSE + JWT để cung cấp các khóa phù hợp một <code>JWKSelector</code> và một context tùy chọn. Với Spring Authorization Server, kiểu thường gặp là:

~~~java
JWKSource<SecurityContext>
~~~

Selector mô tả tiêu chí cần tìm, ví dụ khóa RSA dùng cho chữ ký với thuật toán RS256 và/hoặc một <code>kid</code> cụ thể. Nguồn khóa trả về những JWK phù hợp. Điều này cho phép encoder chọn private key ký token và JWK Set endpoint phục vụ public keys theo cách thống nhất.

| Thành phần | Trách nhiệm |
| --- | --- |
| <code>JWKSet</code> | Giữ tập JWK. |
| <code>JWKSelector</code> | Mô tả điều kiện lọc khóa. |
| <code>JWKSource</code> | Trả danh sách JWK phù hợp selector. |
| <code>ImmutableJWKSet</code> | Implementation đơn giản đọc từ một JWK Set cố định. |
| Key repository/KMS adapter | Implementation động lấy khóa từ kho quản lý hoặc HSM/KMS. |

### 5.2. ImmutableJWKSet cho demo

~~~java
@Bean
JWKSource<SecurityContext> jwkSource() {
    RSAKey rsaKey = generateRsaSigningKey();
    JWKSet jwkSet = new JWKSet(rsaKey);
    return new ImmutableJWKSet<>(jwkSet);
}
~~~

<code>generateRsaSigningKey()</code> là helper được định nghĩa ở phần kế tiếp. Ví dụ này tiện cho học tập nhưng **không phù hợp production nếu tạo khóa mới mỗi lần ứng dụng khởi động**: sau restart, token JWT cũ có thể không còn public key tương ứng để xác minh.

### 5.3. JWKSource không phải chỉ là một file JSON

Một file JWKS public có thể dùng để xác minh, nhưng server còn cần private key ký. Trong thực tế, JWKSource có thể:

- Đọc JWK private từ keystore hoặc secret manager có kiểm soát.
- Truy vấn metadata public và dùng thao tác ký từ KMS/HSM.
- Cung cấp đồng thời khóa active và các public key cũ trong giai đoạn rotation.
- Lọc khóa theo <code>kid</code>, thuật toán, key use và trạng thái.

Nếu dùng KMS/HSM, không nhất thiết phải export private key ra Java heap. Có thể cần một <code>JwtEncoder</code> hoặc adapter ký riêng tương thích với hệ thống khóa. Thiết kế phải bảo đảm JWK public metadata và thao tác ký trỏ tới **cùng một key material**; nếu không, chữ ký sinh ra không khớp public key được công bố.

## 6. Tạo RSA signing key bằng Java

### 6.1. Ví dụ sinh khóa cho môi trường demo

~~~java
static RSAKey generateRsaSigningKey() {
    try {
        KeyPairGenerator generator =
            KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);

        KeyPair keyPair = generator.generateKeyPair();
        RSAPublicKey publicKey =
            (RSAPublicKey) keyPair.getPublic();
        RSAPrivateKey privateKey =
            (RSAPrivateKey) keyPair.getPrivate();

        return new RSAKey.Builder(publicKey)
            .privateKey(privateKey)
            .keyID(UUID.randomUUID().toString())
            .keyUse(KeyUse.SIGNATURE)
            .algorithm(JWSAlgorithm.RS256)
            .build();
    } catch (GeneralSecurityException ex) {
        throw new IllegalStateException(
            "Cannot generate RSA signing key", ex);
    }
}
~~~

Đoạn code dùng <code>KeyPairGenerator</code> của Java và builder Nimbus. Cần import các kiểu từ <code>java.security</code>, <code>java.security.interfaces</code> và <code>com.nimbusds.jose.jwk</code>. UUID <code>kid</code> chỉ là ví dụ; production nên dùng ID ổn định, duy nhất, có quy tắc quản lý và audit.

**Không sinh lại khóa mỗi lần deploy production.** Nếu khóa chỉ nằm trong bộ nhớ, restart sẽ làm mất khả năng xác minh JWT đã ký bằng khóa trước. Hãy nạp khóa đã được tạo và lưu bền vững qua secret manager, keystore bảo vệ hoặc KMS/HSM. Tạo khóa mới là một quy trình quản trị có kiểm soát.

### 6.2. Bean JWKSource dùng trong Spring Authorization Server

Với một khóa demo:

~~~java
@Bean
JWKSource<SecurityContext> jwkSource() {
    RSAKey rsaKey = generateRsaSigningKey();
    JWKSet jwkSet = new JWKSet(rsaKey);
    return new ImmutableJWKSet<>(jwkSet);
}
~~~

Spring Authorization Server có thể sử dụng bean <code>JWKSource&lt;SecurityContext&gt;</code> để cấu hình ký JWT và JWK Set endpoint. Trong ứng dụng thực, thay phần tạo khóa demo bằng cách đọc khóa đã quản lý; không để mỗi instance tự sinh một cặp khóa riêng rồi cùng công bố một issuer nhưng JWKS không nhất quán.

### 6.3. Tạo JwtDecoder cho các chức năng cần xác minh JWT

Trong các cấu hình cần <code>JwtDecoder</code>, ví dụ bật OIDC UserInfo hoặc các endpoint cần xác minh JWT:

~~~java
@Bean
JwtDecoder jwtDecoder(JWKSource<SecurityContext> jwkSource) {
    return OAuth2AuthorizationServerConfiguration
        .jwtDecoder(jwkSource);
}
~~~

Đây là cách cấu hình thường gặp trong Spring Authorization Server. Không nhầm <code>JwtDecoder</code> của Authorization Server với decoder ở Resource Server: hai thành phần có thể dùng chung issuer/JWK nhưng mục đích, audience validation và policy có thể khác nhau.

## 7. Kết nối JWKSource với JwtEncoder và JwtGenerator

### 7.1. Chuỗi tạo JWT

Spring Authorization Server dùng token generator để tạo token theo grant và token type. Với JWT:

1. Provider xác minh authorization grant và tạo <code>OAuth2TokenContext</code>.
2. <code>JwtGenerator</code> nhận context và tạo <code>JwtEncodingContext</code>.
3. Customizer có thể thêm claims/JWS header trong context.
4. <code>JwtEncoder</code> encode và ký JWT.
5. Kết quả được lưu trong <code>OAuth2Authorization</code> và trả về client theo token response.

<code>JwtEncoder</code> là abstraction ký/encode JWT. Trong cấu hình Nimbus thường dùng <code>NimbusJwtEncoder</code> với <code>JWKSource&lt;SecurityContext&gt;</code>. <code>JwtGenerator</code> không tự sinh key; nó cần encoder và nguồn khóa tương thích.

### 7.2. Chọn đúng key khi có nhiều JWK

Khi JWK Set chứa nhiều khóa, việc chọn khóa ký phải xác định được **một private key phù hợp** với thuật toán và metadata của JWT. <code>kid</code> trong protected header giúp Resource Server tìm public key tương ứng sau khi token đã được phát hành. Đừng giả định chỉ thêm nhiều JWK vào set là mọi encoder sẽ tự chọn “khóa mới nhất” theo thứ tự mảng.

Với Nimbus encoder, selector được tạo dựa trên header/algorithm và JWKSource. Nếu nhiều private keys cùng khớp selector, encoder có thể không xác định được một khóa duy nhất. Thiết kế nên:

- Có đúng một signing key active cho mỗi thuật toán/selector đang dùng, hoặc
- Cấu hình selection rõ ràng theo <code>kid</code>/policy của encoder tương thích, và
- Kiểm thử header <code>kid</code> thực tế khớp public JWK được công bố.

Không đặt <code>kid</code> tùy ý trong customizer mà không bảo đảm JWKSource có private key tương ứng. Ngược lại, không công bố một JWK public có <code>kid</code> trùng khóa khác.

### 7.3. Ví dụ tổng hợp cấu hình endpoint

~~~java
@Configuration
@EnableWebSecurity
class AuthorizationServerConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain authorizationServerChain(HttpSecurity http)
            throws Exception {
        OAuth2AuthorizationServerConfigurer authorizationServer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

        http
            .securityMatcher(authorizationServer.getEndpointsMatcher())
            .with(authorizationServer, Customizer.withDefaults())
            .authorizeHttpRequests(authorize ->
                authorize.anyRequest().authenticated());

        return http.build();
    }

    @Bean
    AuthorizationServerSettings authorizationServerSettings() {
        return AuthorizationServerSettings.builder()
            .issuer("https://auth.example.com")
            .jwkSetEndpoint("/oauth2/jwks")
            .build();
    }
}
~~~

Đây là phần cấu hình endpoint và issuer; ứng dụng còn cần RegisteredClientRepository, authorization services, token generator, JWKSource, user authentication và các bean liên quan. <code>getEndpointsMatcher()</code> chọn endpoint do Authorization Server quản lý. Path <code>/oauth2/jwks</code> là mặc định phổ biến và được ghi rõ ở đây để dễ đọc; nếu thay đổi, cập nhật discovery metadata và Resource Server.

Khi có bean <code>JWKSource&lt;SecurityContext&gt;</code>, Spring Authorization Server có thể cấu hình JWK Set endpoint. Endpoint trả **public JWK Set** để bên nhận xác minh; hãy kiểm tra response triển khai thực tế và bảo đảm không có private parameters. Không tự tạo một controller trả toàn bộ JWK object nội bộ.

## 8. JWKS endpoint và discovery metadata

### 8.1. JWK Set endpoint

Một JWKS endpoint công khai có thể trả:

~~~http
GET /oauth2/jwks HTTP/1.1
Host: auth.example.com
Accept: application/jwk-set+json, application/json
~~~

Response rút gọn:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: public, max-age=...

{
  "keys": [
    {
      "kty": "RSA",
      "use": "sig",
      "alg": "RS256",
      "kid": "as-signing-2026-01",
      "n": "public-modulus",
      "e": "AQAB"
    }
  ]
}
~~~

Header cache cụ thể phụ thuộc server/proxy. Public JWKS thường được cache để giảm tải; thời gian cache ảnh hưởng trực tiếp đến tốc độ Resource Server nhận biết khóa mới hoặc khóa bị thu hồi.

### 8.2. Discovery chỉ ra jwks_uri

OAuth Authorization Server Metadata theo RFC 8414 và OIDC Discovery công bố metadata như <code>issuer</code>, endpoint giao thức và <code>jwks_uri</code>. Client/Resource Server nên lấy URL JWKS từ discovery metadata của **issuer được cấu hình tin cậy**, thay vì hard-code một host do token cung cấp.

~~~json
{
  "issuer": "https://auth.example.com",
  "jwks_uri": "https://auth.example.com/oauth2/jwks",
  "token_endpoint": "https://auth.example.com/oauth2/token"
}
~~~

Đây là JSON minh họa, lược bỏ các metadata khác. Khi triển khai OIDC, endpoint discovery OIDC có path và metadata theo OpenID Connect Discovery; không tự giả định metadata RFC 8414 và OIDC hoàn toàn cùng một tài liệu ở mọi cấu hình.

### 8.3. Kiểm tra public JWKS

Khi triển khai hoặc sau mỗi lần rotation, xác nhận:

- Response là JSON JWK Set với mảng <code>keys</code>.
- Mỗi khóa công khai có <code>kid</code> duy nhất theo chính sách.
- <code>kty</code>, <code>use</code> và <code>alg</code> phù hợp.
- Không có <code>d</code>, <code>p</code>, <code>q</code>, <code>dp</code>, <code>dq</code>, <code>qi</code> hoặc private material tương đương.
- Issuer trong discovery đúng với issuer của JWT.
- <code>jwks_uri</code> sử dụng HTTPS và hostname được tin cậy.
- Resource Server có thể tải set, chọn đúng key và xác minh token thật.

Không cho phép Resource Server tự tải <code>jku</code>/<code>x5u</code> tùy ý từ JWT header nếu chưa có policy rõ ràng; điều đó có thể mở ra SSRF hoặc key substitution. Trust anchor phải là issuer/JWKS URI đã cấu hình hoặc discovery đã xác minh.

## 9. Resource Server xác minh JWT bằng JWKS

### 9.1. Cách xác minh

JWT access token ký bằng private key có header minh họa:

~~~json
{
  "alg": "RS256",
  "kid": "as-signing-2026-01",
  "typ": "JWT"
}
~~~

Resource Server đọc <code>kid</code>, tìm JWK tương ứng trong JWKS đã tải, rồi dùng public key để xác minh chữ ký. Nếu không có key phù hợp, nó có thể refresh JWKS theo chính sách và thử lại. Chữ ký hợp lệ chỉ chứng minh token được ký bởi private key tương ứng; **chưa chứng minh token dành cho API này**.

Sau khi xác minh chữ ký, Resource Server còn phải kiểm tra:

1. <code>iss</code> trùng issuer tin cậy.
2. <code>aud</code> chứa resource server/API hiện tại.
3. <code>exp</code>, <code>nbf</code> (nếu có) và clock skew hợp lệ.
4. Thuật toán ký thuộc allow-list và tương thích key.
5. Scope/authority đủ cho request tài nguyên.
6. Các policy bổ sung như tenant, token type, client hoặc trạng thái revocation nếu kiến trúc yêu cầu.

### 9.2. Cấu hình Resource Server dùng issuer

Một cách cấu hình phổ biến trong Spring Security:

~~~java
@Bean
JwtDecoder jwtDecoder() {
    return JwtDecoders.fromIssuerLocation(
        "https://auth.example.com");
}
~~~

Decoder có thể dùng discovery metadata để tìm JWK Set URI và tạo decoder phù hợp. Cấu hình thực tế nên bổ sung validator cho audience và các policy riêng của API. Không chỉ xác minh chữ ký mà bỏ qua <code>aud</code>; token hợp lệ cho Orders API không nhất thiết hợp lệ cho Billing API.

### 9.3. Lỗi khi kid không tìm thấy

Những nguyên nhân thường gặp:

- Resource Server đang cache JWKS cũ, chưa tải public key mới.
- Authorization Server đã bắt đầu ký bằng khóa mới trước khi công bố public key.
- <code>kid</code> trong JWT không trùng <code>kid</code> ở JWKS.
- Nhiều JWK có cùng <code>kid</code> hoặc metadata <code>alg</code>/<code>use</code> không tương thích.
- Reverse proxy/cache trả JWKS cũ hoặc response không đúng issuer.
- Khóa private được dùng để ký không tương ứng với public key đang công bố.

Không sửa lỗi bằng cách tắt signature validation hoặc chấp nhận token khi không tìm được key. Cần sửa quy trình phân phối khóa và cache.

## 10. Rotation khóa ký an toàn

### 10.1. Vì sao phải giữ public key cũ?

Khi một token được ký bằng key K1, token đó vẫn cần public key K1 để xác minh cho đến khi token hết hạn hoặc bị vô hiệu hóa bằng cơ chế khác. Nếu Authorization Server xóa K1 khỏi JWKS ngay khi bắt đầu ký bằng K2, Resource Server không thể xác minh các token K1 còn hợp lệ.

### 10.2. Quy trình rotation thông thường

~~~mermaid
flowchart TD
    A["Đang ký bằng K1; JWKS công bố K1 public"] --> B["Tạo K2 trong KMS/HSM hoặc kho khóa an toàn"]
    B --> C["Công bố public K2 trong JWKS"]
    C --> D["Chờ cache/replica Resource Server nhận K2"]
    D --> E["Chuyển signing active sang K2"]
    E --> F["Ký token mới với kid=K2"]
    F --> G["Giữ public K1 trong JWKS"]
    G --> H["Đợi token K1 hết hạn + clock skew + cache margin"]
    H --> I["Gỡ public K1 khỏi JWKS theo policy"]
    I --> J["Lưu trữ/huỷ private K1 theo quy trình quản trị"]
~~~

Thứ tự **pre-publish public key mới trước khi ký bằng private key mới** giúp Resource Server có thời gian tải khóa. Việc giữ public key cũ bảo đảm token cũ còn hạn tiếp tục xác minh được.

### 10.3. Các mốc cần tính khi bỏ key cũ

Không chỉ chờ <code>accessTokenTimeToLive</code>. Xác định:

- Token cuối cùng được ký bằng K1 phát hành lúc nào.
- Thời hạn dài nhất của mọi loại JWT dùng K1 (access token, ID Token hoặc JWT khác).
- Clock skew validator ở Resource Server.
- Thời gian cache JWKS và độ trễ phân phối qua CDN/proxy.
- Các client/API offline có thể giữ metadata cũ trong bao lâu.
- Các token có lifetime dài hoặc profile đặc biệt nào không.

Chỉ loại public K1 sau khi mọi token cần xác minh bằng nó đã hết hiệu lực theo policy, cộng khoảng đệm hợp lý. Nếu có JWT có thời hạn dài hơn dự kiến, phải đưa nó vào kế hoạch.

### 10.4. Ví dụ JWK Set có hai khóa

Trong giai đoạn rotation, JWKSource có thể chứa private key K2 active để ký và public key K1 để xác minh token cũ. Một cách biểu diễn nội bộ:

~~~java
JWKSet signingAndVerificationSet =
    new JWKSet(List.of(
        activePrivateKeyK2,
        previousPublicKeyK1
    ));

JWKSource<SecurityContext> jwkSource =
    new ImmutableJWKSet<>(signingAndVerificationSet);
~~~

Đây là mô hình minh họa cho kho khóa cố định. <code>activePrivateKeyK2</code> là JWK chứa private material để ký; <code>previousPublicKeyK1</code> phải là public-only JWK. Encoder phải chọn đúng K2 khi ký, còn JWK Set endpoint chỉ công bố public representation của cả K1 và K2. Nếu encoder không xác định được đúng một private key, hãy cấu hình key selection rõ ràng; không dựa vào thứ tự <code>List</code>.

Trong production, nguồn khóa thường là động và được quản lý tập trung; thay vì tạo một ImmutableJWKSet mới bằng tay trong mỗi lần rotation, có thể cập nhật kho khóa/version có kiểm soát và bảo đảm mọi instance nhìn thấy cùng trạng thái.

### 10.5. Emergency rotation khi private key bị lộ

Nếu nghi ngờ private key K1 bị compromise:

1. Kích hoạt quy trình incident response và hạn chế quyền truy cập KMS/HSM/kho bí mật.
2. Ngừng dùng K1 để ký; tạo K2 mới trong vùng tin cậy.
3. Công bố public K2, chuyển signer sang K2 theo quy trình khẩn cấp.
4. Loại public K1 khỏi JWKS để Resource Server không tiếp tục tin token ký bằng key đã lộ, sau khi đánh giá tác động và khả năng cache.
5. Yêu cầu Resource Server làm mới JWKS hoặc invalidate cache theo cách vận hành; cache cũ có thể vẫn chấp nhận token K1 trong một khoảng thời gian.
6. Xác định token/authorization bị ảnh hưởng, thu hồi theo khả năng introspection/denylist hoặc các biện pháp ứng dụng.
7. Điều tra phạm vi truy cập private key, log/audit, backup và các hệ thống đã nhận key.

Với JWT xác minh offline, xóa public key khỏi JWKS **không bảo đảm mọi Resource Server ngừng chấp nhận token ngay lập tức** vì public key có thể đã được cache. Nếu cần ngắt quyền tức thì, phải có cơ chế bổ sung như introspection, denylist hoặc kiểm tra trạng thái tập trung và SLA đồng bộ rõ ràng.

## 11. Lưu trữ và bảo vệ private key

### 11.1. Không lưu private key trong source code

Không:

- Commit PEM, JWK private hoặc keystore có mật khẩu/khóa riêng vào Git.
- Đặt private key trong <code>application.yml</code>, Docker image hoặc biến môi trường không được bảo vệ.
- In JWK đầy đủ, private key hoặc secret vào log/exception/metrics.
- Dùng cùng một private key cho dev, test, staging và production.
- Cho tất cả developer/service có quyền đọc private key chỉ để kiểm thử JWT.

### 11.2. Lựa chọn lưu trữ

| Giải pháp | Khi phù hợp | Điều cần bảo vệ |
| --- | --- | --- |
| Keystore được bảo vệ | Ứng dụng quy mô nhỏ/vừa, key lifecycle đơn giản. | File, password, filesystem permission, backup và quyền mount. |
| Secret manager | Hạ tầng cloud/container cần phân quyền và audit. | IAM, secret version, rotation và quyền đọc. |
| KMS | Cần thao tác ký được kiểm soát, audit và tách key khỏi app. | IAM policy, key policy, rate limit và availability. |
| HSM | Yêu cầu bảo vệ key vật lý/tuân thủ cao. | HSM cluster, backup/restore, operator roles và quy trình ceremony. |

KMS/HSM có thể cho phép ký mà không xuất private key. Khi đó cần một <code>JwtEncoder</code> hoặc crypto adapter tương thích với API ký của hệ thống; <code>JWKSource</code> vẫn cần cung cấp public metadata để Resource Server xác minh.

### 11.3. Phân quyền và audit

Chia quyền rõ:

- Runtime signer chỉ có quyền ký bằng key active, không có quyền export private key.
- Dịch vụ public JWKS chỉ cần public key metadata.
- Người quản trị rotation có quyền tạo/kích hoạt key theo workflow phê duyệt.
- Resource Server chỉ tải JWKS, không cần quyền truy cập private key.
- Quyền backup/restore phải có audit, mã hóa và quy trình kiểm tra khôi phục.

Định kỳ kiểm tra ai có quyền gọi signing operation, số lượng request ký bất thường, key version đang active và thời điểm rotation gần nhất.

## 12. Kiểm thử JWK, JWKS và chữ ký

### 12.1. Unit test JWK không chứa private material ở public view

Ví dụ với Nimbus:

~~~java
@Test
void publicJwkDoesNotExposePrivateKey() {
    RSAKey privateJwk = generateRsaSigningKey();

    RSAKey publicJwk = privateJwk.toPublicJWK();

    assertThat(publicJwk.isPrivate()).isFalse();
    assertThat(publicJwk.getKeyID())
        .isEqualTo(privateJwk.getKeyID());
    assertThat(publicJwk.getModulus())
        .isEqualTo(privateJwk.getModulus());
}
~~~

Test này kiểm tra chuyển đổi JWK phía Java. Vẫn cần kiểm tra **HTTP response JWKS thật** để xác nhận endpoint/proxy không vô tình trả private parameters.

### 12.2. Integration test ký và xác minh

Một bài test có thể:

1. Tạo RSA JWK test và JWKSource.
2. Dùng <code>JwtEncoder</code>/<code>JwtGenerator</code> ký một access token JWT.
3. Đọc header <code>kid</code> và <code>alg</code>.
4. Lấy public JWK tương ứng từ JWKS endpoint.
5. Dùng <code>JwtDecoder</code> xác minh chữ ký và kiểm tra issuer/audience/expiry.
6. Thử đổi payload nhưng giữ signature cũ; xác minh phải thất bại.

Không chỉ decode Base64URL rồi khẳng định token hợp lệ. Decode không xác minh chữ ký.

### 12.3. Ma trận kiểm thử rotation

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Token ký bằng K1, JWKS có public K1 | Resource Server xác minh thành công nếu claims hợp lệ. |
| JWKS có K1 và K2, token mới ký K2 | Resource Server chọn đúng K2 theo <code>kid</code>. |
| Công bố K2 trước khi bắt đầu ký K2 | Resource Server có thể tải public key trước khi nhận token mới. |
| Token K1 còn hạn, K1 vẫn trong JWKS | Token cũ tiếp tục được xác minh. |
| Xóa K1 khi token K1 còn hạn | Test phải phát hiện Resource Server không thể xác minh sau khi cache được làm mới; quy trình không được xóa sớm. |
| JWT có <code>kid</code> không tồn tại | Bị từ chối; không fallback sang khóa bất kỳ. |
| Hai JWK cùng <code>kid</code> | Deployment validation thất bại hoặc cảnh báo nghiêm trọng. |
| Public JWKS chứa <code>d</code> hoặc private RSA params | Security test thất bại. |
| Thuật toán trong JWT ngoài allow-list | Resource Server từ chối. |
| JWK <code>use</code>/<code>alg</code> không phù hợp | Không dùng khóa cho chữ ký đó. |
| JWKS bị cache quá lâu trong rotation | Kiểm tra cache policy và quy trình refresh. |
| Issuer JWT khác issuer cấu hình | Resource Server từ chối dù chữ ký hợp lệ. |
| Audience không đúng API | Resource Server từ chối. |
| KMS không khả dụng | Không phát token ký lỗi/không chữ ký; báo lỗi và giám sát. |

### 12.4. Test endpoint và discovery

Với <code>MockMvc</code> hoặc HTTP integration test:

- GET <code>/.well-known/openid-configuration</code> khi OIDC được bật và kiểm tra <code>jwks_uri</code>.
- GET Authorization Server metadata theo RFC 8414 nếu được cấu hình, kiểm tra issuer và JWK Set URI.
- GET <code>/oauth2/jwks</code>, xác minh status/content type và public-only JWK fields.
- Xác minh JWKS chứa cả khóa mới và cũ trong giai đoạn rotation.
- Sau khi gỡ key cũ, xác minh response không còn key đó theo thời điểm chính sách.
- Kiểm tra reverse proxy/cache không phục vụ response của issuer hoặc môi trường khác.

Không dùng một test endpoint trả JSON giả làm bằng chứng <code>JWKSource</code>, <code>JwtEncoder</code> và Resource Server đã được kết nối đúng.

## 13. Lỗi thường gặp và cách chẩn đoán

### Lỗi 1: Tạo key mới mỗi lần restart

**Triệu chứng:** Token vừa phát hành trước restart không xác minh được sau khi server khởi động lại.

**Nguyên nhân:** Khóa cũ chỉ nằm trong RAM và bị thay bằng cặp mới.

**Cách xử lý:** Dùng key storage bền vững; giữ public key cũ trong JWKS đến khi token tương ứng hết hạn.

### Lỗi 2: JWKS công khai chứa private key

**Triệu chứng:** JSON response có <code>d</code>, <code>p</code>, <code>q</code> hoặc private parameter.

**Nguyên nhân:** Controller tự serialize JWK đầy đủ thay vì public representation.

**Cách xử lý:** Dùng JWK Set endpoint của framework hoặc chỉ xuất <code>toPublicJWK()</code>/<code>toPublicJWKSet()</code>; thêm test quét private fields.

### Lỗi 3: JWT có kid nhưng JWKS không có key đó

**Triệu chứng:** Resource Server báo không tìm được signing key.

**Nguyên nhân:** Kid sai, key chưa được pre-publish, JWKS cache cũ hoặc signer dùng key khác với JWKSource.

**Cách xử lý:** Kiểm tra JWT header, JWKS, active key ID, cache và mapping KMS.

### Lỗi 4: JWKS có nhiều private key phù hợp

**Triệu chứng:** Encoder không chọn được một signing key duy nhất hoặc phát sinh lỗi encoding.

**Nguyên nhân:** Nhiều khóa khớp selector/algorithm mà không có selection policy rõ.

**Cách xử lý:** Chỉ có một private signing key active phù hợp hoặc định tuyến key rõ ràng theo kid/encoder; vẫn giữ public key cũ cho verify.

### Lỗi 5: Resource Server tin chữ ký nhưng không kiểm tra audience

**Triệu chứng:** Token của Orders API được dùng gọi Billing API.

**Nguyên nhân:** Chỉ xác minh chữ ký/issuer mà thiếu audience validation.

**Cách xử lý:** Cấu hình audience validator và scope/authorization policy riêng cho từng Resource Server.

### Lỗi 6: Xóa key cũ ngay khi kích hoạt key mới

**Triệu chứng:** Các API lỗi xác minh token cũ ngay sau rotation.

**Nguyên nhân:** Không chờ access/ID token cũ hết hạn và cache đồng bộ.

**Cách xử lý:** Pre-publish key mới, chuyển signer, giữ public key cũ qua khoảng tương thích rồi mới retire.

### Lỗi 7: Nhầm JWKSource với JWKS URL

**Triệu chứng:** Cấu hình encoder nhận URL HTTP hoặc Resource Server nhận bean Java.

**Nguyên nhân:** Nhầm abstraction trong ứng dụng với endpoint công bố khóa.

**Cách xử lý:** Server dùng <code>JWKSource</code>; client/Resource Server lấy JWKS qua URL được discovery công bố.

### Lỗi 8: Dùng HMAC nhưng công bố secret qua JWKS

**Triệu chứng:** Resource Server có thể ký token giả vì nhận được shared secret.

**Nguyên nhân:** Nhầm secret xác minh HMAC với public key.

**Cách xử lý:** Không công bố symmetric secret; dùng asymmetric signing khi nhiều bên độc lập cần xác minh.

### Lỗi 9: Tin kid do client gửi để chọn khóa tin cậy

**Triệu chứng:** Attacker điều khiển key source hoặc làm server tải khóa từ URL không tin cậy.

**Nguyên nhân:** Dùng <code>kid</code>/<code>jku</code>/<code>x5u</code> từ JWT chưa xác minh làm trust anchor.

**Cách xử lý:** Chỉ chọn trong JWKSource/JWKS đã gắn với issuer tin cậy và thuật toán allow-list.

## 14. Vận hành và quản trị khóa

### 14.1. Quy trình vòng đời khóa

Quản trị signing key cần quy trình có owner:

1. **Tạo:** sinh key trong KMS/HSM hoặc môi trường được bảo vệ; cấp ID và metadata duy nhất.
2. **Kiểm tra:** xác minh public key, thuật toán, kích thước/curve, key usage và mapping signer.
3. **Pre-publish:** công bố public JWK mới và chờ các Resource Server nhận.
4. **Kích hoạt:** chuyển signer sang key mới; ghi nhận thời điểm, người/automation thực hiện.
5. **Theo dõi:** kiểm tra JWT <code>kid</code>, lỗi signature, JWKS cache và token issuance.
6. **Retire:** chờ token cũ hết hạn và cache margin; gỡ public JWK cũ.
7. **Archive/destroy:** xử lý private key cũ theo policy, backup, audit và yêu cầu pháp lý.

### 14.2. Cấu hình cache JWKS

Cache giúp Resource Server không phải tải JWKS ở mọi request. Nhưng cache quá dài làm chậm việc nhận key mới và key bị compromise; cache quá ngắn gây tải và phụ thuộc availability của Authorization Server.

Hãy chọn cache TTL theo:

- Tần suất rotation dự kiến.
- Max lifetime của JWT.
- Số lượng Resource Server/instance.
- CDN/reverse proxy và thời gian propagation.
- Cơ chế refresh khi nhận <code>kid</code> chưa biết.
- Quy trình emergency key removal.

Không giả định mọi Resource Server sẽ tự làm mới JWKS ngay khi thấy kid lạ; hành vi cache/refresh phụ thuộc decoder và HTTP cache. Kiểm thử cụ thể với phiên bản Spring Security đang triển khai.

### 14.3. Metrics và cảnh báo

Những tín hiệu hữu ích:

- Số token phát hành theo <code>kid</code> và thuật toán.
- Thời điểm key active được thay đổi.
- Số lượng JWK công khai, key sắp hết hạn hoặc thiếu public counterpart.
- Tỷ lệ lỗi signature, unknown kid, issuer/audience mismatch.
- Lỗi KMS/HSM signing, độ trễ và quota.
- Thời điểm public JWKS được cập nhật ở các node/edge.
- Sự kiện truy cập bất thường tới private key/signing operation.

Log chỉ nên ghi metadata an toàn như kid, client ID theo policy, request ID và mã lỗi; không log raw JWT nếu không cần, không log private JWK hoặc credential.

## 15. Bài tập thực hành

Bạn đang xây dựng Authorization Server cho hai Resource Server: <code>orders-api</code> và <code>billing-api</code>. JWT access token được ký bằng RSA; hai API dùng chung issuer nhưng yêu cầu audience khác nhau. Hệ thống cần rotation khóa mỗi quý và có ba instance Authorization Server.

1. Tạo một RSA JWK với <code>kty</code>, <code>use</code>, <code>alg</code>, <code>kid</code> và public/private parameters. Giải thích phần nào được phép xuất hiện trên JWKS.
2. Tạo <code>JWKSet</code> và <code>JWKSource&lt;SecurityContext&gt;</code> dùng <code>ImmutableJWKSet</code> cho demo.
3. Kết nối JWKSource với <code>JwtEncoder</code>/<code>JwtGenerator</code> và JWK Set endpoint của Spring Authorization Server.
4. Dùng discovery metadata để lấy <code>jwks_uri</code>; cấu hình Resource Server xác minh issuer, signature, audience và scope.
5. Thiết kế hai token có audience khác nhau; chứng minh token Orders không được Billing API chấp nhận dù cùng ký bằng một key.
6. Mô tả rotation K1 → K2: thời điểm pre-publish, chuyển signer, giữ public K1 và điều kiện gỡ K1.
7. Kiểm thử token K1 còn hạn trong lúc JWKS có cả K1 và K2; kiểm tra header <code>kid</code> của token mới.
8. Mô phỏng cache JWKS cũ và unknown kid, xác định cách refresh an toàn.
9. Thiết kế KMS/HSM adapter để private key không phải export vào Java heap; nêu cách đảm bảo public JWK khớp key ký.
10. Xây runbook emergency rotation khi private key bị lộ và giải thích vì sao JWT offline có thể vẫn được chấp nhận trong thời gian cache.

**Tiêu chí đạt:** Có thể giải thích và chứng minh rằng **Authorization Server ký bằng private key được bảo vệ**, **Resource Server chỉ nhận public JWK từ issuer tin cậy**, **kid liên kết đúng token với public key**, và **rotation không làm hỏng token còn hiệu lực ngoài kế hoạch**.

## 16. Tài liệu đối chiếu

- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): cấu trúc JWK, JWK Set và các tham số key.
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515): chữ ký JOSE, protected header và xác minh.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): cấu trúc JWT và claims.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): metadata issuer và JWKS URI.
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html): discovery metadata và <code>jwks_uri</code>.
- [Spring Authorization Server — Core Model Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): JWKSource, JwtEncoder và token generation.
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): JWK Set endpoint và cấu hình Authorization Server.
- [Spring Authorization Server — Getting Started](https://docs.spring.io/spring-authorization-server/reference/getting-started.html): cấu hình <code>JWKSource&lt;SecurityContext&gt;</code> và <code>JwtDecoder</code>.
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): xác minh JWT qua issuer/JWK Set URI.
- [Nimbus JOSE + JWT](https://connect2id.com/products/nimbus-jose-jwt): API JWK/JWKSet/JWKSource và xử lý JOSE trong Java.
