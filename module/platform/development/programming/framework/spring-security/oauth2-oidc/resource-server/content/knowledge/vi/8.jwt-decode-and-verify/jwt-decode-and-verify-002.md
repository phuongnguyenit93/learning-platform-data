# NimbusJwtDecoder và các nguồn cung cấp khóa

Khi một API Spring Security nhận **OAuth 2.0 Bearer Access Token** dưới dạng JWT, nó phải biết **dùng khóa nào để xác minh chữ ký** và **những claim nào cần kiểm tra** trước khi cho request truy cập tài nguyên. Thành phần đảm nhiệm phần lớn công việc này trong Spring Security Servlet là **NimbusJwtDecoder**.

Có nhiều cách cung cấp khóa cho decoder: để nó tìm **JWK Set** từ metadata của issuer, cấu hình trực tiếp **JWK Set URI**, tải **RSA public key** cố định, hoặc dùng **shared secret** cho JWT ký HMAC. Mỗi cách có mô hình tin cậy, vận hành và giới hạn riêng.

Bài học tập trung vào **JWT Access Token tại Resource Server** trong ngữ cảnh **Spring Boot 3.x, Spring Security 6.x, Java 17+ và Spring MVC/Servlet**. Những ví dụ về URI, key ID và token đều là dữ liệu minh họa, cần thay bằng cấu hình của nhà phát hành thật.

## 1. NimbusJwtDecoder làm gì?

Spring Security định nghĩa interface `JwtDecoder` với nhiệm vụ nhận chuỗi JWT và trả về đối tượng `Jwt` đã qua xử lý, hoặc ném `JwtException` nếu không thể chấp nhận token. **NimbusJwtDecoder** là triển khai dựa trên thư viện **Nimbus JOSE + JWT**.

Trong một Resource Server sử dụng JWT, đường đi thường là:

~~~text
Client
  |
  | GET /api/orders
  | Authorization: Bearer <access-token>
  v
Spring SecurityFilterChain
  |
  v
BearerTokenAuthenticationFilter
  |
  v
JwtAuthenticationProvider
  |
  v
NimbusJwtDecoder
  |-- đọc header/payload JWT
  |-- xác minh chữ ký/MAC với khóa được tin cậy
  |-- thực hiện các OAuth2TokenValidator<Jwt>
  |   (issuer, thời hạn, audience, token profile...)
  v
JwtAuthenticationToken trong SecurityContext
  |
  v
AuthorizationFilter / Method Security
  |-- scope / authority
  |-- quyền tenant, quyền dữ liệu nghiệp vụ
  v
Controller hoặc từ chối request
~~~

**Giải mã (decode) không đồng nghĩa xác thực.** Bất kỳ ai cũng có thể tách ba đoạn của một JWT dạng JWS và Base64url-decode payload để **đọc** claim. API chỉ có thể **tin** các claim sau khi decoder xác minh token bằng khóa/thuật toán đã được cấu hình tin cậy và các validator kiểm tra ngữ cảnh của API.

Một JWT ký số thường có ba đoạn:

~~~text
BASE64URL(JOSE_HEADER).BASE64URL(CLAIMS).BASE64URL(SIGNATURE)
~~~

Ví dụ các cấu trúc JSON bên trong token:

~~~json
{
  "alg": "RS256",
  "kid": "key-2026-01",
  "typ": "at+jwt"
}
~~~

~~~json
{
  "iss": "https://login.example.test/realms/demo",
  "sub": "employee-123",
  "aud": ["orders-api"],
  "exp": 1893456000,
  "scope": "orders.read"
}
~~~

**alg**, **kid**, **typ** thuộc JOSE header; **iss**, **sub**, **aud**, **exp**, **scope** thuộc claims. Hai đoạn JSON trên chưa phải một JWT hợp lệ vì không có chữ ký thật. JWT dạng JWS **không mã hóa nội dung**; payload vẫn đọc được. JWE là cơ chế mã hóa khác và không mặc nhiên được hỗ trợ bởi cấu hình JWT Resource Server thông thường.

## 2. Chọn nguồn khóa: sơ đồ quyết định

~~~text
Authorization Server cấp token theo định dạng nào?
  |
  +-- Opaque Access Token
  |      -> OAuth2 Resource Server opaqueToken()
  |      -> introspection; không dùng NimbusJwtDecoder để xác minh JWS
  |
  +-- JWT Access Token ký số
         |
         +-- IdP công bố metadata OIDC / Authorization Server?
         |      -> issuer-uri / JwtDecoders.fromIssuerLocation()
         |
         +-- Đã biết trước JWK Set URI đáng tin cậy?
         |      -> jwk-set-uri / NimbusJwtDecoder.withJwkSetUri()
         |
         +-- Chỉ có một RSA public key cố định?
         |      -> public-key-location / NimbusJwtDecoder.withPublicKey()
         |
         +-- JWT dùng khóa đối xứng HMAC đã thỏa thuận?
                -> NimbusJwtDecoder.withSecretKey()
~~~

| Nguồn khóa | Cách cấu hình | Điểm mạnh | Điểm cần kiểm soát |
| --- | --- | --- | --- |
| **Issuer metadata** | `issuer-uri`, `JwtDecoders.fromIssuerLocation`, `withIssuerLocation` | Tìm JWK Set qua metadata; phù hợp IdP chuẩn, hỗ trợ nhiều public keys và rotation. | Issuer phải đáng tin cậy, discovery/network phụ thuộc cấu hình, kiểm tra `iss`. |
| **JWK Set URI trực tiếp** | `jwk-set-uri`, `withJwkSetUri` | Biết chính xác endpoint khóa; có thể tách discovery lúc khởi động. | JWK URI phải cấu hình an toàn; cần chủ động giữ validator issuer/audience. |
| **RSA public key cố định** | `public-key-location`, `withPublicKey` | Không cần tải JWK qua mạng lúc xác minh. | Đổi khóa cần cập nhật triển khai/cấu hình; chọn thuật toán và kiểm tra claims phù hợp. |
| **Shared secret HMAC** | `withSecretKey` | Phù hợp hệ thống kiểm soát chặt hai phía ký/xác minh. | Mỗi bên có secret đều có khả năng tạo MAC hợp lệ; yêu cầu bảo vệ/phân phối secret nghiêm ngặt. |

**Không có lựa chọn nào khiến decoder tự hiểu quyền nghiệp vụ.** Dù chữ ký hợp lệ, API vẫn phải kiểm tra **issuer, audience, thời hạn, token profile và quyền**; một Access Token của API khác không nên được chấp nhận chỉ vì cùng IdP.

## 3. Dependency: Resource Server và JOSE

Trong dự án Spring Boot Gradle (Groovy DSL) có dependency management:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Starter Resource Server của các bản Spring Boot 3.x phổ biến đã đưa các dependency xử lý JWT/JOSE cần thiết vào dependency tree. Nếu cấu hình bằng module Spring Security thủ công, JWT Resource Server thường cần **cả**:

~~~groovy
implementation 'org.springframework.security:spring-security-oauth2-resource-server'
implementation 'org.springframework.security:spring-security-oauth2-jose'
~~~

**spring-security-oauth2-resource-server** cung cấp cơ chế Bearer token và tích hợp security; **spring-security-oauth2-jose** chứa các lớp JWT decoder/JOSE. Không ghép các version ngẫu nhiên khi Spring Boot BOM đang quản lý dependency. Một API chỉ dùng opaque token có thể không cần giải mã JWS, mặc dù starter có thể vẫn mang JOSE như dependency chuyển tiếp.

## 4. Nguồn khóa số 1: tìm JWK Set qua issuer

Đây thường là cách đơn giản nhất khi Authorization Server/OpenID Provider hỗ trợ metadata discovery tiêu chuẩn.

### 4.1. Cấu hình bằng Spring Boot

Ví dụ `application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.test/realms/demo
          audiences:
            - orders-api
~~~

Ý nghĩa:

1. **issuer-uri:** định danh issuer mà Resource Server tin cậy. Spring Security có thể khám phá metadata thích hợp để lấy **jwks_uri**.
2. **jwks_uri:** địa chỉ JWK Set do metadata của issuer mô tả, nơi công bố public keys.
3. **audiences:** yêu cầu claim **aud** chứa **orders-api** trên những bản Spring Boot hỗ trợ thuộc tính này. Nếu phiên bản không có cấu hình tương ứng, cần thêm audience validator.

Trong luồng khám phá metadata, decoder sử dụng thông tin do **issuer đã cấu hình** công bố, ví dụ:

~~~text
Issuer đã tin cậy
  https://login.example.test/realms/demo
       |
       v
OIDC / Authorization Server metadata
  "issuer": "https://login.example.test/realms/demo"
  "jwks_uri": "https://login.example.test/realms/demo/protocol/openid-connect/certs"
       |
       v
JWK Set (public keys)
       |
       v
Xác minh JWS, sau đó kiểm tra JWT claims
~~~

Đây là **luồng cấu hình và sử dụng khóa**, không có nghĩa mọi Bearer request đều tải metadata từ đầu. Decoder và tầng cache thường tái sử dụng thông tin khóa. Cách khởi tạo, fetch/caching và thời điểm kết nối cụ thể phụ thuộc phiên bản/cấu hình; cần tính đến việc issuer hoặc endpoint khóa không sẵn sàng.

**Không** nhận một token bất kỳ, đọc `iss` từ payload chưa xác minh rồi dùng URL đó như issuer tin cậy. Nếu một Resource Server cần nhận nhiều issuer, mọi issuer phải được cấp phép bằng quy tắc rõ ràng.

### 4.2. Khởi tạo bằng JwtDecoders.fromIssuerLocation

Nếu cần chủ động tạo bean decoder:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtDecoders;

@Configuration
public class JwtDecoderConfig {

    private static final String ISSUER =
        "https://login.example.test/realms/demo";

    @Bean
    JwtDecoder jwtDecoder() {
        return JwtDecoders.fromIssuerLocation(ISSUER);
    }
}
~~~

`JwtDecoders.fromIssuerLocation` thực hiện khám phá endpoint thích hợp và thiết lập decoder với các validator cần thiết để kiểm tra issuer theo cấu hình framework. **Audience của API vẫn cần được kiểm tra thêm**, trừ khi được áp dụng bằng cấu hình có hiệu lực.

Với cách này, nếu muốn gắn audience validator vào decoder cụ thể, thường thuận tiện hơn khi sử dụng trực tiếp **NimbusJwtDecoder** và `setJwtValidator` (ở mục 8).

### 4.3. Tự dùng NimbusJwtDecoder.withIssuerLocation

Trong Spring Security 6.1+, builder hỗ trợ:

~~~java
NimbusJwtDecoder decoder =
    NimbusJwtDecoder.withIssuerLocation(
        "https://login.example.test/realms/demo").build();
~~~

**Điểm cần nhớ:** khi tự tạo decoder bằng builder, hãy **cấu hình validators tường minh**; đừng giả định việc builder biết issuer URI luôn có nghĩa đã áp chính sách issuer và audience chính xác cho API:

~~~java
decoder.setJwtValidator(
    JwtValidators.createDefaultWithIssuer(
        "https://login.example.test/realms/demo"));
~~~

Đoạn cấu hình trên bổ sung các validator mặc định, bao gồm kiểm tra issuer; nếu API cần audience thì phải kết hợp thêm validator (mục 8).

## 5. Nguồn khóa số 2: JWK Set URI được cấu hình trực tiếp

Trường hợp biết chính xác nơi lấy public keys, Resource Server có thể dùng **JWK Set URI** mà không cần dựa vào issuer metadata discovery để tìm URI đó.

### 5.1. Spring Boot: issuer-uri kết hợp jwk-set-uri

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.test/realms/demo
          jwk-set-uri: https://login.example.test/realms/demo/protocol/openid-connect/certs
          audiences:
            - orders-api
~~~

**jwk-set-uri** chỉ endpoint chứa public keys; **issuer-uri** giữ trách nhiệm ràng buộc token với issuer hợp lệ. Khai báo JWK URI tường minh có thể tránh yêu cầu kết nối đến metadata discovery endpoint lúc Resource Server khởi động, tùy cách cấu hình và phiên bản.

**Đừng chỉ cấu hình khóa mà quên nguồn phát hành.** Cùng một khóa có thể được dùng trong nhiều ngữ cảnh, hoặc một kẻ tấn công có thể cố đưa token với claims hợp lệ về mặt định dạng nhưng issuer/audience không phù hợp.

### 5.2. Cấu trúc JWK Set

Ví dụ biểu diễn **public** RSA JWK Set (giá trị `n` đã rút gọn để dễ đọc):

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "key-2026-01",
      "use": "sig",
      "alg": "RS256",
      "n": "PUBLIC_RSA_MODULUS_BASE64URL",
      "e": "AQAB"
    },
    {
      "kty": "RSA",
      "kid": "key-2026-02",
      "use": "sig",
      "alg": "RS256",
      "n": "ANOTHER_PUBLIC_RSA_MODULUS_BASE64URL",
      "e": "AQAB"
    }
  ]
}
~~~

Đây là dữ liệu **minh họa, không phải RSA keys có thể dùng để xác minh token**.

- **kty:** loại khóa, ví dụ RSA.
- **kid:** key identifier dùng để phân biệt và chọn khóa phù hợp.
- **n**, **e:** các tham số public key của RSA.
- **use**, **alg:** metadata mô tả mục đích/thuật toán dự kiến; Resource Server vẫn phải **giới hạn thuật toán theo chính sách tin cậy**, không tự mở rộng sang mọi thuật toán được nguồn bên ngoài gợi ý.
- **keys:** mảng cho phép công bố nhiều public keys cùng lúc để chuyển đổi khóa.

Một JWK Set công khai để xác minh RSA **không được chứa private key material** như tham số riêng tư `d`. Authorization Server giữ private key bí mật để ký.

### 5.3. NimbusJwtDecoder.withJwkSetUri

Khi muốn cấu hình bằng Java:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
public class JwksDecoderConfig {

    private static final String ISSUER =
        "https://login.example.test/realms/demo";
    private static final String JWKS_URI =
        "https://login.example.test/realms/demo/protocol/openid-connect/certs";

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(JWKS_URI)
            .jwsAlgorithm(SignatureAlgorithm.RS256)
            .build();

        decoder.setJwtValidator(
            JwtValidators.createDefaultWithIssuer(ISSUER));

        return decoder;
    }
}
~~~

Bean này minh họa **chữ ký và issuer**. Để bảo vệ API thực, bổ sung **audience validator** như mục 8; không coi đây là policy hoàn chỉnh chỉ vì token đã được ký.

Đặc biệt, **withJwkSetUri(JWKS_URI)** cho biết nơi lấy khóa nhưng tự nó **không nên được xem là cam kết issuer hợp lệ**. Hãy đặt validator rõ ràng trong decoder tùy chỉnh, hoặc sử dụng Boot configuration đảm bảo các ràng buộc tương ứng.

### 5.4. Vì sao JWK Set URI phải được tin cậy?

JWK Set là nguồn **khóa xác minh**. Nếu kẻ tấn công kiểm soát nguồn khóa, họ có thể tạo cặp khóa mới, ký token giả và để hệ thống xác minh chữ ký bằng public key của họ. Vì vậy:

- Cấu hình URI từ nguồn quản lý đáng tin cậy; dùng HTTPS và xác minh TLS.
- Không dùng tùy ý token header `jku` hoặc `x5u`, hay claim `iss` chưa xác minh, để tự động tải khóa ở URL do client chỉ định.
- Không chọn JWK Set URI dựa trên request parameter, tenant ID tự do hoặc header không tin cậy.
- Khi hỗ trợ nhiều issuer, dùng danh sách issuer/JWK đã cấp phép và ràng buộc chúng với nhau.
- Xem xét lỗi mạng, timeout, caching và key rotation để không cấp quyền khi khóa chưa được xác minh.

## 6. Nguồn khóa số 3: RSA public key cố định

Không phải hệ thống nào cũng cung cấp discovery hoặc JWK Set endpoint. Nếu API được cấp một **RSA public key** đáng tin cậy, có thể dùng trực tiếp để xác minh JWS.

### 6.1. Cấu hình public-key-location của Spring Boot

Ví dụ đặt public key dạng PEM tại **src/main/resources/keys/access-token-pub.pem**, sau đó:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          public-key-location: classpath:keys/access-token-pub.pem
          audiences:
            - orders-api
~~~

Đây là ví dụ về **nguồn khóa**. Tùy phiên bản Boot và cách cấu hình, hãy bảo đảm issuer và các validator cần thiết thực sự được áp dụng. Nếu API cần kiểm tra `iss` cụ thể, có thể khai báo decoder tùy chỉnh như dưới đây để tập trung đầy đủ điều kiện vào một nơi.

Khóa công khai có thể được lưu ở classpath hoặc cấu hình được quản lý khác; nó **không phải private key của issuer**. Không lưu private signing key ở Resource Server chỉ để xác minh RSA signatures.

### 6.2. NimbusJwtDecoder.withPublicKey

Giả sử ứng dụng đã nạp public key tin cậy thành đối tượng **RSAPublicKey**:

~~~java
import java.security.interfaces.RSAPublicKey;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
public class StaticRsaDecoderConfig {

    private static final String ISSUER =
        "https://login.example.test/realms/demo";

    @Bean
    JwtDecoder jwtDecoder(RSAPublicKey trustedPublicKey) {
        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withPublicKey(trustedPublicKey)
            .build();

        decoder.setJwtValidator(
            JwtValidators.createDefaultWithIssuer(ISSUER));

        return decoder;
    }
}
~~~

Bean **trustedPublicKey** là một phụ thuộc cần được cấu hình để đọc từ PEM hoặc nguồn key management đã kiểm soát. Đoạn code cho thấy cách dùng decoder khi **đã có RSAPublicKey**, chưa phải ứng dụng chạy độc lập. Bổ sung audience validator như mục 8 nếu API chỉ chấp nhận token dành cho mình.

**Khi nào phù hợp?** Dịch vụ nội bộ nhỏ, khóa được cấp và quản lý chặt, ít thay đổi hoặc hệ thống có cơ chế phân phối bản cập nhật khóa an toàn.

**Giới hạn chính:** một public key cố định **không tự hỗ trợ nhiều khóa đồng thời để rotation** như JWK Set. Khi Authorization Server đổi signing key, Resource Server cần được cập nhật theo quy trình rollout, nếu không token mới có thể bị trả 401. Với yêu cầu rotation thường xuyên, JWK Set phù hợp hơn.

### 6.3. Thuật toán phải tương thích nguồn khóa

`withPublicKey` nhận **RSAPublicKey**. Nó không phải builder chung để nhập mọi loại khóa EC, EdDSA hoặc bí mật đối xứng. Nếu nhà phát hành dùng thuật toán khác, cần cấu hình decoder/JWK phù hợp với thuật toán và chính sách ứng dụng, không thử chuyển đổi khóa một cách tùy tiện.

## 7. Nguồn khóa số 4: shared secret cho HMAC

Với JWS sử dụng thuật toán HMAC như **HS256**, bên phát hành và bên xác minh cùng biết một **secret key**. Spring Security có thể xác minh token bằng `NimbusJwtDecoder.withSecretKey`.

Khác biệt bảo mật quan trọng so với RSA:

| RSA / ECDSA bất đối xứng | HMAC đối xứng |
| --- | --- |
| Authorization Server ký bằng private key. | Authorization Server tạo MAC bằng shared secret. |
| Resource Server xác minh bằng public key, không thể tự tạo chữ ký bằng public key. | Resource Server có shared secret; ai nắm secret đều có thể tạo MAC hợp lệ. |
| Public JWK Set có thể chia sẻ công khai khi chỉ chứa public parameters. | Secret phải tuyệt đối giữ kín; **không** công bố trong JWK Set công khai. |
| Phù hợp khi nhiều Resource Server chỉ cần xác minh. | Cần đặc biệt cẩn trọng khi chia sẻ secret cho nhiều dịch vụ. |

### 7.1. Ví dụ withSecretKey

Ví dụ Java sử dụng secret được nạp từ biến môi trường ở dạng Base64, dành cho môi trường tin cậy do tổ chức kiểm soát:

~~~java
import java.util.Base64;
import javax.crypto.SecretKey;
import javax.crypto.spec.SecretKeySpec;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.jose.jws.MacAlgorithm;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
public class HmacDecoderConfig {

    private static final String ISSUER =
        "https://login.example.test/realms/demo";

    @Bean
    SecretKey jwtSharedSecret() {
        String base64Secret = System.getenv("JWT_HMAC_SECRET_BASE64");
        if (base64Secret == null || base64Secret.isBlank()) {
            throw new IllegalStateException("Missing JWT HMAC secret");
        }

        byte[] keyBytes = Base64.getDecoder().decode(base64Secret);
        if (keyBytes.length < 32) {
            throw new IllegalStateException("HS256 key must be at least 256 bits");
        }

        return new SecretKeySpec(keyBytes, "HmacSHA256");
    }

    @Bean
    JwtDecoder jwtDecoder(SecretKey jwtSharedSecret) {
        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withSecretKey(jwtSharedSecret)
            .macAlgorithm(MacAlgorithm.HS256)
            .build();

        decoder.setJwtValidator(
            JwtValidators.createDefaultWithIssuer(ISSUER));

        return decoder;
    }
}
~~~

Đây là **phương án thay thế cho JWT ký HMAC**, không khai báo đồng thời với bean JWT decoder RSA/JWKS trong cùng chain nếu không có thiết kế định tuyến rõ ràng. Đoạn mã cũng cần audience validator (mục 8) để ràng buộc token với API.

Độ dài secret cho HS256 phải phù hợp tiêu chuẩn và chính sách bảo mật; ví dụ kiểm tra tối thiểu 32 byte. Trong hệ thống thật, ưu tiên secret manager/KMS, phân quyền đọc bí mật tối thiểu, cơ chế luân chuyển khóa, không đưa secret vào repository, log, error report hoặc test fixture công khai. Base64 **chỉ là encoding**, không phải cơ chế bảo mật bí mật.

**Không** tự chọn HS256 nếu Authorization Server đang ký RS256. Resource Server phải có thỏa thuận chính xác về token profile và thuật toán; tuyệt đối không chuyển qua HMAC chỉ vì gặp token kiểm tra RSA thất bại.

## 8. Decoder xác minh chữ ký chưa đủ: issuer, audience và thời hạn

Một decoder đáng tin cậy cần hai lớp:

1. **Kiểm tra mật mã:** chữ ký/MAC đúng với khóa được chấp nhận và thuật toán được cho phép.
2. **Kiểm tra ngữ nghĩa của JWT:** issuer, audience, thời gian, token profile và các ràng buộc của API.

### 8.1. Các claim đặc biệt

| Claim/header | Cần kiểm tra gì? | Lưu ý |
| --- | --- | --- |
| **iss** | Trùng issuer đã tin cậy. | Không lấy issuer chưa xác minh làm danh sách tin cậy tự động. |
| **aud** | Chứa Resource Server hiện tại, ví dụ **orders-api**. | **aud** có thể là một string hoặc mảng string theo RFC 7519. |
| **exp** | Token chưa hết hạn. | NumericDate tính theo giây từ Unix epoch; có thể áp clock skew nhỏ. |
| **nbf** | Token đã đến thời điểm bắt đầu hiệu lực. | Cần chú ý đồng hồ hệ thống. |
| **iat** | Thời điểm phát hành, dùng khi profile/chính sách yêu cầu. | Không tự coi iat là thời điểm hết hạn. |
| **typ** (JOSE header) | Kiểu JWT phù hợp profile nếu được yêu cầu. | **at+jwt** có thể được yêu cầu trong RFC 9068; không phải claim trong payload. |
| **scope/scp** | Có các quyền cần thiết sau khi authentication hợp lệ. | Quyền API là bước authorization; không thay kiểm tra audience. |

Spring Security JWT Resource Server thường có validator mặc định cho timestamp và issuer khi được cấu hình bằng issuer. **Audience cần được cấu hình tường minh** theo nhu cầu API. Việc tự viết decoder bằng builder có thể thay logic auto-configuration của Boot, vì thế nên khai báo rõ tập validator.

### 8.2. Ví dụ decoder hoàn chỉnh với issuer + audience

Ví dụ bean sử dụng JWK Set URI trực tiếp, đồng thời giới hạn RS256 và kiểm tra issuer/audience:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
public class OrdersJwtDecoderConfig {

    private static final String ISSUER =
        "https://login.example.test/realms/demo";
    private static final String JWKS =
        "https://login.example.test/realms/demo/protocol/openid-connect/certs";
    private static final String AUDIENCE = "orders-api";

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(JWKS)
            .jwsAlgorithm(SignatureAlgorithm.RS256)
            .build();

        OAuth2TokenValidator<Jwt> audienceValidator = jwt -> {
            if (jwt.getAudience().contains(AUDIENCE)) {
                return OAuth2TokenValidatorResult.success();
            }
            return OAuth2TokenValidatorResult.failure(
                new OAuth2Error(
                    "invalid_token",
                    "Token audience is not accepted",
                    null));
        };

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(ISSUER),
                audienceValidator));

        return decoder;
    }
}
~~~

Trong ví dụ:

- **withJwkSetUri(JWKS):** lấy public keys từ endpoint tin cậy.
- **jwsAlgorithm(RS256):** chỉ chấp nhận thuật toán chữ ký đã thống nhất.
- **createDefaultWithIssuer(ISSUER):** áp dụng bộ kiểm tra mặc định về issuer và timestamp.
- **audienceValidator:** yêu cầu token dành cho API này.

Nếu ứng dụng còn yêu cầu loại token cụ thể hoặc tenant, thêm validators/chính sách được định nghĩa rõ. Trường **aud** không thay thế authorization dựa trên scope, role và quyền đối với bản ghi.

**Quan trọng:** khi gọi `decoder.setJwtValidator(...)`, các validator trước đó có thể bị thay thế bằng bộ mới. Đừng đặt chỉ một audience validator rồi vô tình bỏ kiểm tra issuer/time; hãy kết hợp qua `DelegatingOAuth2TokenValidator`.

### 8.3. Một bean JwtDecoder có thể thay auto-configuration

Nếu đã tự định nghĩa bean `JwtDecoder`, Spring Boot thường nhường quyền tạo decoder cho bean đó. Vì vậy:

- Đừng giả định `application.yml` có `audiences` là audience validator chắc chắn đã được áp dụng lên decoder tùy chỉnh.
- Nếu dùng builder tự tạo, đảm bảo issuer/audience/clock và thuật toán đều được cấu hình trong bean thực sự.
- Tránh có nhiều bean `JwtDecoder` cùng cạnh tranh khi không có cấu hình chọn bean rõ ràng.
- Nếu không có lý do tùy biến, cấu hình Boot bằng `issuer-uri`, `jwk-set-uri`, `audiences` có thể đơn giản và ít lỗi hơn.

## 9. Điều khiển thuật toán tin cậy

Theo tài liệu Spring Security cho cấu hình JWT phổ biến, NimbusJwtDecoder mặc định tin cậy **RS256** khi chưa cấu hình thuật toán khác. Có thể thay đổi theo nhà phát hành, ví dụ RS512:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          jwk-set-uri: https://login.example.test/oauth2/jwks
          jws-algorithms:
            - RS512
~~~

Nếu dùng builder Java:

~~~java
NimbusJwtDecoder decoder = NimbusJwtDecoder
    .withJwkSetUri("https://login.example.test/oauth2/jwks")
    .jwsAlgorithm(SignatureAlgorithm.RS512)
    .build();
~~~

Mỗi ví dụ chỉ minh họa **chính sách thuật toán**; vẫn cần kiểm tra issuer/audience qua validator. Khi token do issuer dùng ES256/EC keys hay thuật toán khác, cấu hình khóa và thuật toán phải tương ứng. Không dựa hoàn toàn vào trường **alg** do token gửi để tự động chấp nhận mọi thuật toán.

**Algorithm confusion** là nhóm lỗi xảy ra khi verifier tin sai loại khóa/thuật toán, dẫn đến kiểm tra chữ ký không đúng ranh giới bảo mật. Kiểm soát bằng cách **chốt nguồn khóa tin cậy, danh sách thuật toán cho phép và token profile**, không dùng fallback tự động từ bất đối xứng sang HMAC hoặc chấp nhận `alg: none`.

## 10. Caching, key rotation và độ sẵn sàng của nhà phát hành

### 10.1. Vì sao JWK Set thường có nhiều public keys?

Authorization Server không thể giữ cùng một signing key mãi mãi. Khi rotation:

~~~text
Giai đoạn A: JWKS có key-1; issuer ký JWT bằng key-1
Giai đoạn B: JWKS công bố key-1 và key-2
Giai đoạn C: issuer bắt đầu ký JWT mới bằng key-2
Giai đoạn D: JWT ký key-1 hết hiệu lực
Giai đoạn E: JWKS loại key-1 theo kế hoạch
~~~

Nhờ **kid** và nhiều public keys trong JWKS, Resource Server có cơ hội kiểm tra cả JWT cũ còn hiệu lực và JWT mới mà không phải deploy khóa cho từng API.

Nhưng rotation còn phụ thuộc **thời hạn token, cache, thời điểm công bố khóa và hành vi fetch lại JWK Set**. Không loại khóa cũ quá sớm khi vẫn còn token hợp lệ được ký bằng khóa đó, trừ trường hợp sự cố cần thu hồi ngay với chiến lược tương ứng.

### 10.2. Cache của decoder

Nimbus/Spring Security có cơ chế cache JWK Set để tránh request mạng cho mỗi Bearer token. Tài liệu Spring Security của một số phiên bản mô tả cache JWK Set trong bộ nhớ khoảng **5 phút** mặc định; thời gian và chính sách thực tế tùy phiên bản, cache provider và cấu hình.

Nếu cần kiểm soát cache ở mức Spring:

~~~java
import org.springframework.cache.CacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Bean
JwtDecoder jwtDecoder(CacheManager cacheManager) {
    return NimbusJwtDecoder
        .withJwkSetUri("https://login.example.test/oauth2/jwks")
        .cache(cacheManager.getCache("jwks"))
        .build();
}
~~~

Ví dụ trên chỉ mô tả **cách chọn cache**, chưa thêm issuer/audience validators. Nếu cấu hình cache riêng, cần đảm bảo cache đã tồn tại, có chiến lược TTL/eviction phù hợp và không dùng một cache không phân biệt giữa các JWK Set URI khác nhau. Khi sử dụng cache provider, thêm dependency và cấu hình tương ứng.

**Không** nên giảm thời gian cache xuống bằng 0 một cách tùy tiện: nó có thể làm mọi request phụ thuộc mạng/IdP và làm tăng tải JWKS. Cũng không để cache quá lâu đến mức rotation không được phản ánh kịp. Lựa chọn phụ thuộc khả năng rotation, SLA và thời hạn Access Token.

### 10.3. Nếu JWKS endpoint không sẵn sàng?

Cần phân biệt:

- Khi decoder **đã cache đủ public key** cho token đang được kiểm tra, có thể tiếp tục xác minh theo chính sách cache.
- Khi gặp **kid mới chưa có khóa**, decoder có thể cần tải lại JWK Set. Nếu không thể lấy khóa đáng tin cậy, token không được chấp nhận.
- Khi khởi động mà yêu cầu discovery chưa truy cập được, ứng dụng có thể gặp lỗi tùy cách tạo decoder; cấu hình JWK URI trực tiếp có thể giảm phụ thuộc discovery lúc startup nhưng **không xóa phụ thuộc mạng khi cần lấy khóa**.
- Khi issuer thu hồi/đổi khóa khẩn cấp, các node với cache khác nhau có thể cập nhật khác thời điểm; cần kế hoạch vận hành và giám sát.

Nguyên tắc an toàn: **không chuyển sang chế độ bỏ xác minh chữ ký khi JWKS gặp sự cố**. Cũng không cho phép lấy khóa từ host bất kỳ để “sửa lỗi 401 cho nhanh”.

## 11. Định tuyến nhiều issuer, nhiều tenant

Một Resource Server đôi khi phục vụ nhiều tenant, mỗi tenant có Authorization Server riêng hoặc issuer URI riêng. Khi đó một decoder với một issuer không đủ.

Có thể dùng cơ chế resolver phù hợp, chẳng hạn **JwtIssuerAuthenticationManagerResolver** trong Spring Security Servlet, để chọn AuthenticationManager theo issuer **đã được cho phép**.

Ý tưởng:

~~~text
Request mang Bearer JWT
         |
         v
Đọc claim iss ban đầu chỉ để CHỌN nhánh
         |
         v
Issuer có thuộc allowlist?
    |               |
   Không            Có
    |               |
   401        Chọn decoder/keys
                     |
                     v
            Xác minh chữ ký JWT
            Kiểm tra lại iss
            Kiểm tra audience API
            Kiểm tra thời hạn/scope
                     |
                     v
                Cho phép / từ chối
~~~

**Việc đọc issuer từ token chưa xác thực chỉ là bước định tuyến, không phải bước cấp quyền.** Resolver phải giới hạn những issuer được tin cậy từ cấu hình/nguồn quản trị; không tự tạo decoder hoặc tải metadata/JWK từ mọi issuer URL do người gọi nhập. Nếu một issuer chung phục vụ nhiều tenant, có thể cần validator riêng cho tenant, resource và token profile.

Khi một API chấp nhận nhiều issuer, các claim riêng như `roles`, `tenant_id` hay `permissions` có thể mang nghĩa khác nhau. Không tự trộn quyền giữa các nguồn phát hành nếu chưa có contract mapping và chính sách bảo mật rõ ràng.

## 12. Ghép decoder vào SecurityFilterChain

Một cấu hình Resource Server cơ bản theo **Spring Security 6.x**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth ->
                oauth.jwt(Customizer.withDefaults()));

        return http.build();
    }
}
~~~

Ở đây decoder do Boot tạo từ cấu hình JWT hoặc bean `JwtDecoder` tùy chỉnh được đưa vào luồng Resource Server. Khi request không có token hoặc token bị bác ở bước authentication, API thường trả **401 Unauthorized**. Token xác thực được nhưng thiếu `SCOPE_orders.read` thường gặp **403 Forbidden** khi gọi GET endpoint tương ứng.

Chú ý:

- **scope → authority:** Spring Security thường ánh xạ claim `scope` hoặc `scp` sang authorities tiền tố **SCOPE_**. Nếu issuer phát hành role custom, cần converter hoặc quy tắc authorization tường minh.
- **STATELESS:** request được xác thực bằng Bearer token thay vì session.
- **CSRF disabled:** trong ví dụ này chỉ phù hợp API thuần Bearer header. Nếu cùng ứng dụng có OIDC Login và session cookie cho browser, cần bảo vệ CSRF phù hợp theo từng security chain.
- **Resource authorization:** scope hợp lệ không đồng nghĩa user được đọc mọi đơn hàng; API còn có thể phải kiểm tra tenant, chủ sở hữu và permission trên bản ghi.

Không gửi **ID Token** của OIDC Login làm Bearer Access Token cho API. ID Token thường có **audience là OIDC client ID**, còn Access Token phải hướng tới Resource Server.

## 13. Kiểm thử NimbusJwtDecoder với các nguồn khóa

### 13.1. Phân biệt test giả lập và test xác minh thật

**spring-security-test** hỗ trợ `jwt()` trong MockMvc:

~~~java
mockMvc.perform(get("/api/orders/42")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read"))))
    .andExpect(status().isOk());
~~~

Đây là cách tốt để thử **authorization rules**, nhưng nó đặt Authentication giả lập vào SecurityContext và **không yêu cầu NimbusJwtDecoder xác minh chữ ký**. Kể cả đặt `aud` sai trong principal giả lập, test vẫn có thể thành công vì không qua decoder.

Muốn xác nhận **chữ ký, issuer, audience, expiration**, cần test `JwtDecoder.decode(token)` với JWT **được ký thật bằng khóa test**, hoặc kiểm thử tích hợp qua Bearer filter với JWK Set fixture.

### 13.2. Ví dụ unit test với RSA key pair chỉ dùng cho test

Ví dụ JUnit 5 sau sinh RSA key pair trong test, ký JWT bằng private key test rồi xác minh bằng `NimbusJwtDecoder.withPublicKey`. Đây là kiểm thử decoder độc lập, không truy cập Authorization Server bên ngoài:

~~~java
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.JWSHeader;
import com.nimbusds.jose.crypto.RSASSASigner;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.SignedJWT;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;
import java.time.Instant;
import java.util.Date;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtException;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class NimbusDecoderTest {

    private static final String ISSUER =
        "https://login.example.test/realms/demo";

    private KeyPair trustedPair;
    private NimbusJwtDecoder decoder;

    @BeforeEach
    void setUp() throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        trustedPair = generator.generateKeyPair();

        decoder = NimbusJwtDecoder
            .withPublicKey((RSAPublicKey) trustedPair.getPublic())
            .build();

        OAuth2TokenValidator<Jwt> audience = jwt ->
            jwt.getAudience().contains("orders-api")
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error("invalid_token", "Invalid audience", null));

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(ISSUER), audience));
    }

    private static String signed(
            KeyPair signer, String issuer, String audience,
            Instant expiration) throws Exception {
        JWTClaimsSet claims = new JWTClaimsSet.Builder()
            .issuer(issuer)
            .subject("user-123")
            .audience(audience)
            .issueTime(Date.from(Instant.now().minusSeconds(60)))
            .expirationTime(Date.from(expiration))
            .claim("scope", "orders.read")
            .build();

        SignedJWT jwt = new SignedJWT(
            new JWSHeader(JWSAlgorithm.RS256), claims);
        jwt.sign(new RSASSASigner(
            (RSAPrivateKey) signer.getPrivate()));
        return jwt.serialize();
    }

    @Test
    void validTokenIsAccepted() throws Exception {
        String token = signed(
            trustedPair, ISSUER, "orders-api",
            Instant.now().plusSeconds(600));
        assertEquals("user-123", decoder.decode(token).getSubject());
    }

    @Test
    void wrongAudienceIsRejected() throws Exception {
        String token = signed(
            trustedPair, ISSUER, "billing-api",
            Instant.now().plusSeconds(600));
        assertThrows(JwtException.class, () -> decoder.decode(token));
    }

    @Test
    void wrongIssuerIsRejected() throws Exception {
        String token = signed(
            trustedPair, "https://untrusted.example.test", "orders-api",
            Instant.now().plusSeconds(600));
        assertThrows(JwtException.class, () -> decoder.decode(token));
    }

    @Test
    void expiredTokenIsRejected() throws Exception {
        String token = signed(
            trustedPair, ISSUER, "orders-api",
            Instant.now().minusSeconds(3600));
        assertThrows(JwtException.class, () -> decoder.decode(token));
    }

    @Test
    void unknownKeyIsRejected() throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        KeyPair untrustedPair = generator.generateKeyPair();
        String token = signed(
            untrustedPair, ISSUER, "orders-api",
            Instant.now().plusSeconds(600));
        assertThrows(JwtException.class, () -> decoder.decode(token));
    }
}
~~~

Trong test này:

- **validTokenIsAccepted** cho biết public key tin cậy xác minh được chữ ký của token ký bằng private key tương ứng và các claims qua validator.
- **wrongAudienceIsRejected** chứng minh audience validator có tác dụng.
- **wrongIssuerIsRejected** chứng minh decoder không nhận issuer khác.
- **expiredTokenIsRejected** dùng token hết hạn từ lâu hơn clock skew nhỏ thông thường.
- **unknownKeyIsRejected** chứng minh public key không đúng thì chữ ký bị bác.

Test này **không** chứng minh discovery/JWKS tải qua mạng hoặc rotation hoạt động. Để kiểm tra JWK Set, dựng HTTP endpoint test cục bộ trả JWK Set chứa public key fixture, sau đó chạy decoder **withJwkSetUri** hoặc test server thông qua Bearer filter.

### 13.3. Kiểm thử riêng khi dùng JWK Set URI

Một bộ test tích hợp hữu ích nên bao gồm:

| Kịch bản | Kỳ vọng |
| --- | --- |
| JWT ký bằng key-1 đang có trong JWKS | Được decoder chấp nhận nếu claims hợp lệ. |
| JWT có `kid` không có trong JWKS | Từ chối token khi không tìm được khóa phù hợp. |
| JWT ký bởi private key không tương ứng JWKS | Từ chối vì xác minh chữ ký thất bại. |
| JWKS có key-1 và key-2 trong giai đoạn rotation | Token của cả hai khóa được xử lý theo chính sách. |
| Thuật toán JWT không nằm trong danh sách được phép | Từ chối thay vì tự nới lỏng thuật toán. |
| JWK endpoint mất kết nối khi cần khóa chưa cache | Không cấp quyền khi chưa xác minh được. |
| JWT có audience của API khác | 401 sau khi validator audience từ chối. |
| JWT hợp lệ nhưng thiếu scope | 403 tại endpoint cần scope đó. |

Nên dùng key pair/issuer/JWK server **chỉ dành cho test**, không dùng private key production hoặc Access Token của người dùng thật. Kiểm thử với JWKS fixture giúp xác minh luồng tải và chọn khóa; unit test `withPublicKey` chỉ chứng minh logic decoder với một khóa.

## 14. Quan sát và xử lý lỗi

### 14.1. JWT không hợp lệ trả lỗi gì?

Một request không có Bearer token hoặc mang token không thể xác thực thường nhận **401 Unauthorized** từ Resource Server:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
~~~

Token có chữ ký/claims hợp lệ nhưng thiếu quyền đối với endpoint thường nhận **403 Forbidden**. Chi tiết `WWW-Authenticate` có thể bổ sung mã lỗi chuẩn theo ngữ cảnh. Không trả raw JWT, key material, exception message nội bộ hoặc stack trace trong body/header gửi về client.

### 14.2. Triệu chứng và hướng điều tra

| Triệu chứng | Nguyên nhân có thể | Điểm cần xem |
| --- | --- | --- |
| Khởi động lỗi khi dùng issuer | Metadata endpoint không truy cập được, issuer URI sai, TLS hoặc discovery không phù hợp. | Issuer được cấu hình, metadata/JWKS URL, kết nối/TLS. |
| 401 với token mới sau khi rotation | JWK Set/cache chưa có signing key mới, `kid` không phù hợp. | JWKS có công bố public key mới? cache/TTL/refresh? |
| 401 dù chữ ký hợp lệ | Sai `iss`, `aud`, `exp`, `nbf`, token profile hoặc thuật toán. | Token được cấp cho API nào, validator có cấu hình đúng không? |
| Token HS256 bị bác bởi decoder RSA | Không khớp thuật toán và loại khóa. | Contract phát hành token, `withSecretKey` so với `withPublicKey`/JWKS. |
| Token của API khác được chấp nhận | Thiếu hoặc không áp dụng audience validator. | Decoder thực sự được dùng; bean tùy chỉnh có ghi đè auto-config không? |
| 403 sau khi JWT đã qua decoder | Thiếu authority/scope hoặc quyền trên tài nguyên. | Claim `scope/scp`, JwtAuthenticationConverter, policy endpoint. |
| Lúc được lúc không giữa các node | Cache JWKS/rotation/config khác nhau, đồng hồ lệch, issuer không đồng nhất. | Config từng node, key cache, clock skew, thời gian triển khai. |

Khi debug, **không dán token thật vào công cụ giải mã công khai** và không đưa nguyên header Authorization vào log, URL, ticket hoặc thông báo lỗi. Có thể dùng request ID riêng, loại lỗi đã chuẩn hóa, `kid` hoặc metadata kiểm soát phù hợp để xác định nguyên nhân mà không lộ credential.

### 14.3. Các nhầm lẫn nên tránh

1. **“withJwkSetUri đã kiểm tra issuer.”** Nó chỉ lựa chọn nguồn khóa; phải bảo đảm issuer validator thực sự có hiệu lực.
2. **“Token đúng chữ ký thì gọi mọi API cùng issuer được.”** Phải xác minh **audience** của chính Resource Server và quyền cụ thể.
3. **“JwtDecoders.fromIssuerLocation và NimbusJwtDecoder.withIssuerLocation giống hệt mọi mặc định.”** Khi tự dựng bằng builder, cần kiểm soát rõ tập validators; factory và Boot auto-config có thể bổ sung logic mặc định.
4. **“JWK Set phải chứa private key.”** JWK Set công khai để xác minh chữ ký bất đối xứng chỉ nên chứa **public keys**.
5. **“kid là giá trị bí mật/chứng cứ tin cậy.”** kid là nhãn chọn khóa; độ tin cậy đến từ **nguồn khóa được cấu hình** và xác minh chữ ký.
6. **“Giữ một public key mãi thì tự hỗ trợ rotation.”** Với khóa cố định, thay signing key thường đòi hỏi cập nhật API.
7. **“Có HMAC secret thì API chỉ có thể verify.”** Bất kỳ bên nào có shared secret đều có thể tính MAC; cần bảo vệ secret như signing credential.
8. **“JWKS gặp lỗi thì bỏ qua xác minh để tránh downtime.”** Không được cấp quyền khi chưa xác minh được token.
9. **“Decode Base64url là xác minh JWT.”** Đọc payload không đủ; phải kiểm tra khóa, chữ ký, issuer, audience, thời hạn và chính sách.
10. **“JWT hợp lệ đồng nghĩa có quyền đọc dữ liệu.”** Authorization theo scope, tenant, owner và policy là bước riêng.

## 15. Gợi ý lựa chọn nguồn khóa trong dự án

| Hoàn cảnh | Phương án thường phù hợp |
| --- | --- |
| IdP/OIDC Provider chuẩn, có issuer metadata và JWKS | **issuer-uri**; nếu cần tùy biến, dùng **JwtDecoders.fromIssuerLocation** hoặc **NimbusJwtDecoder.withIssuerLocation** kèm validators. |
| API đã được cung cấp JWK Set URI ổn định, cần giảm phụ thuộc discovery khi khởi động | **issuer-uri + jwk-set-uri** hoặc **withJwkSetUri** với issuer/audience validators. |
| Nhà phát hành chỉ cung cấp RSA public key cố định | **public-key-location** hoặc **withPublicKey**, có kế hoạch cập nhật khóa khi rotation. |
| Nhà phát hành sử dụng HS256 và hai phía có ranh giới tin cậy chung | **withSecretKey**, secret đủ mạnh, lưu qua secret manager, không phân phối tùy tiện. |
| Token opaque, nhà phát hành yêu cầu introspection | **oauth2ResourceServer().opaqueToken()**, không dùng NimbusJwtDecoder cho luồng đó. |
| Nhiều issuer/tenant | Resolver với **allowlist issuer**, decoder/validator theo từng nguồn tin cậy. |

Quy trình triển khai thực tế:

1. **Xác định token profile**: JWT/JWS hay opaque, issuer, audience, thuật toán, thời hạn, scope và token type.
2. **Xác định nguồn khóa tin cậy**: metadata issuer, JWK Set URI, RSA public key hoặc shared secret; dùng đúng cơ chế tương ứng.
3. **Cấu hình decoder + validators**: chữ ký, issuer, audience, exp/nbf và ràng buộc bổ sung.
4. **Cấu hình authorization**: endpoint, HTTP method, scope/authorities và quyền nghiệp vụ.
5. **Kiểm thử âm tính**: sai chữ ký, key, issuer, audience, thời hạn, thuật toán, thiếu scope và lỗi nguồn khóa.
6. **Chuẩn bị vận hành**: key rotation, cache, timeout, TLS, quản lý secret và logging không lộ token.

**Ghi nhớ:** **NimbusJwtDecoder** chỉ đáng tin khi nó lấy khóa từ **nguồn đã được cấp phép** và áp đúng **các validators cho API**. Chọn nguồn khóa giải quyết câu hỏi “chữ ký này có thuộc nhà phát hành mà ta tin không?”; kiểm tra claims và authorization tiếp tục giải quyết “token này có được cấp cho API và thao tác hiện tại không?”.

## Tài liệu tham khảo

- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html).
- [Spring Security — NimbusJwtDecoder Java API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/NimbusJwtDecoder.html).
- [Spring Security — OAuth 2.0 Resource Server Bearer Tokens](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/bearer-tokens.html).
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515).
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517).
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519).
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725).
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068).
