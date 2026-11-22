# Tải JWKS qua HTTPS và kiểm tra nguồn đã được cho phép

Khi một **Spring Security OAuth 2.0 Resource Server** tiếp nhận Bearer Access Token dạng JWT, nó cần khóa để kiểm tra chữ ký của token. Với các thuật toán ký bất đối xứng như RS256, ES256, Authorization Server giữ **private key** để ký còn Resource Server lấy **public key** từ một **JSON Web Key Set (JWKS)**. JWKS thường được công bố tại một HTTPS endpoint.

Chỉ sử dụng URL bắt đầu bằng `https://` **chưa đủ** để tin cậy JWKS. Hệ thống còn phải xác định **đó có phải nguồn khóa được phép cho đúng issuer hay không**, kiểm tra kết nối TLS, giới hạn nơi HTTP client có thể truy cập và không để một request hoặc token chưa được xác minh tự ý quyết định địa chỉ tải khóa.

Bài học này giải thích cách **tải JWKS qua HTTPS**, xây dựng ranh giới tin cậy đối với **JWKS endpoint**, cấu hình **Spring Boot + NimbusJwtDecoder**, kiểm soát nguy cơ đổi nguồn khóa/SSRF, và vận hành cache cùng vòng đời khóa. Ví dụ dùng **Spring Boot 3.x, Spring Security 6.x, Java 17+**, một API Servlet nhận JWT Access Token do Authorization Server phát hành.

## 1. JWKS là gì và vì sao Resource Server cần tải nó?

**JWK (JSON Web Key)** là cấu trúc JSON biểu diễn một khóa. **JWK Set** chứa một mảng JWK ở thuộc tính `keys`. Authorization Server có thể công bố các khóa công khai để Resource Server xác minh chữ ký JWS mà không phải nhận private signing key.

Ví dụ JSON minh họa cho một JWK Set:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "rsa-2026-a",
      "use": "sig",
      "alg": "RS256",
      "n": "PUBLIC_MODULUS_A_BASE64URL",
      "e": "AQAB"
    },
    {
      "kty": "RSA",
      "kid": "rsa-2026-b",
      "use": "sig",
      "alg": "RS256",
      "n": "PUBLIC_MODULUS_B_BASE64URL",
      "e": "AQAB"
    }
  ]
}
~~~

Các giá trị `n` là placeholder, không phải khóa có thể dùng để xác minh token. Ý nghĩa các trường:

| Trường | Ý nghĩa | Khi dùng trong Resource Server |
| --- | --- | --- |
| `keys` | Mảng các JWK. | Có thể chứa nhiều public key để hỗ trợ luân chuyển khóa. |
| `kty` | Loại khóa, ví dụ `RSA` hoặc `EC`. | Phải tương thích thuật toán JWS được chấp nhận. |
| `kid` | Key identifier. | Hỗ trợ tìm khóa phù hợp; **không phải bằng chứng nguồn khóa đáng tin**. |
| `use` | Mục đích, ví dụ `sig`. | Giúp diễn giải khóa dùng để xác minh chữ ký. |
| `alg` | Thuật toán dự kiến, ví dụ `RS256`. | Decoder phải tuân thủ thuật toán đã được **cấu hình tin cậy**, không tự tin mọi thuật toán được công bố. |
| `n`, `e` | Tham số public RSA key. | Dùng xác minh RSA signatures. |

Khi JWKS được công bố công khai cho chữ ký bất đối xứng, nó **chỉ nên chứa thông tin public key**. Tham số riêng tư như `d` không được xuất hiện trong public JWK Set. Private key vẫn do bên phát hành quản lý an toàn.

### 1.1. JWT trỏ tới key bằng cách nào?

Một JWT dạng JWS compact thường có cấu trúc:

~~~text
BASE64URL(JOSE_HEADER).BASE64URL(JWT_CLAIMS).BASE64URL(SIGNATURE)
~~~

JOSE header có thể như sau:

~~~json
{
  "alg": "RS256",
  "kid": "rsa-2026-b",
  "typ": "at+jwt"
}
~~~

Resource Server đọc `kid` để chọn khóa trong **JWKS mà nó đã tin cậy**, rồi dùng public key đó xác minh chữ ký. Điều này khác hoàn toàn với việc tin một URL mới do token tự cung cấp. Kẻ gửi token có thể tự viết `kid`, `alg` hoặc các header tùy chọn; **mức độ tin cậy nằm ở nguồn khóa được cấu hình và kết quả xác minh**, không nằm ở những chuỗi trong header.

### 1.2. Ba khái niệm thường bị nhầm lẫn

| Khái niệm | Câu hỏi được giải quyết |
| --- | --- |
| **HTTPS/TLS** | Tôi có đang trao đổi dữ liệu với endpoint phù hợp với tên máy chủ và qua kênh được bảo vệ không? |
| **JWKS nguồn tin cậy** | Endpoint mà tôi đang kết nối có thực sự được hệ thống **cho phép cung cấp khóa** cho issuer này không? |
| **JWT validation** | Token đã được ký bằng khóa được tin cậy và các claim như `iss`, `aud`, `exp`, `nbf` có đáp ứng yêu cầu của API không? |

Ba lớp này bổ sung nhau. Chỉ có chứng chỉ HTTPS hợp lệ không chứng minh một JWKS thuộc issuer mà API tin cậy. Chỉ có chữ ký hợp lệ không chứng minh JWT dành cho API hiện tại. Chỉ có scope đúng không thay thế xác minh nguồn phát hành.

## 2. Mô hình tin cậy: từ issuer đến JWKS và JWT

Giả sử API `orders-api` chấp nhận token của một Authorization Server:

~~~text
Issuer được tin cậy:
  https://login.example.test/realms/demo

JWKS URI được cho phép:
  https://login.example.test/realms/demo/protocol/openid-connect/certs

Audience của API:
  orders-api
~~~

Chuỗi xử lý mong muốn:

~~~text
              Cấu hình tin cậy của Resource Server
              -------------------------------------
              issuer = https://login.example.test/realms/demo
              jwks   = https://login.example.test/.../certs
              aud    = orders-api
              alg    = RS256
                              |
                              v
                        HTTPS/TLS kết nối
                              |
                              v
                  JWKS endpoint đã được cho phép
                              |
                  trả public keys / JWK Set
                              |
                              v
Client -- Bearer JWT --> NimbusJwtDecoder
                              |
                    Chọn public key phù hợp
                    Kiểm tra JWS signature
                    Kiểm tra iss, aud, exp, nbf
                              |
                              v
                    JwtAuthenticationToken
                              |
                    Kiểm tra scope/authority
                    Kiểm tra quyền tài nguyên
                              |
                       Cho phép / từ chối
~~~

**Issuer** và **JWKS URI** không nhất thiết là cùng một hostname hay cùng đường dẫn. Một tổ chức có thể đặt Authorization Server ở hostname công khai và phân phối JWKS qua một endpoint nội bộ đã được quản lý. Nhưng mối quan hệ **issuer → nguồn khóa được phép** phải được xác định bằng cấu hình tin cậy, không suy đoán từ Bearer token chưa được xác minh.

## 3. Vì sao chỉ HTTPS là chưa đủ?

Giả sử token có JOSE header:

~~~json
{
  "alg": "RS256",
  "kid": "key-of-attacker",
  "jku": "https://keys.attacker.example.test/jwks.json"
}
~~~

Trường `jku` trong JOSE là một tham chiếu tới JWK Set URI. Nếu một triển khai tự viết thấy `jku` và **tự động tải khóa từ địa chỉ đó**, một bên không được tin cậy có thể công bố public key của họ, ký JWT bằng private key tương ứng và cố khiến hệ thống xác minh bằng khóa do họ cung cấp.

Endpoint do bên gửi token chỉ định vẫn có thể là **HTTPS thật với chứng chỉ hợp lệ**. TLS chỉ chứng minh đường kết nối phù hợp với hostname của endpoint đó; nó không biến hostname bất kỳ thành **Authorization Server đã được cấp phép**.

Đây là một dạng **thay thế nguồn khóa (key-source substitution)**; tùy cách phần mềm xử lý URL, nó còn có thể dẫn tới **server-side request forgery (SSRF)**, ví dụ gửi yêu cầu HTTP từ Resource Server đến mạng nội bộ hoặc endpoint metadata của hạ tầng.

### 3.1. Các nguồn dữ liệu có thể bị kiểm soát từ bên ngoài

| Giá trị | Ai có thể kiểm soát? | Ứng dụng an toàn nên làm gì? |
| --- | --- | --- |
| JWT header `kid` | Bên gửi token có thể tự soạn. | Chỉ dùng để chọn key **trong JWKS đã được cho phép**. |
| JWT header `jku` hoặc `x5u` | Có thể do người tạo token gửi. | Không tự động tải từ URL trong token chưa được xác minh. |
| JWT claim `iss` | Có thể tự giả mạo trước khi xác minh chữ ký. | Dùng để chọn nhánh theo **allowlist issuer** nếu cần; sau đó xác minh lại issuer. |
| HTTP query, path, header chứa `jwksUrl` | Client tùy ý thay đổi. | Không dùng làm JWKS URI cho decoder đang xác thực chính request ấy. |
| Metadata của issuer | Phụ thuộc endpoint discovery. | Chỉ khám phá issuer được phép; kiểm soát TLS và endpoint JWKS được trả về. |
| `jwk-set-uri` trong cấu hình vận hành | Quản trị viên/hệ thống triển khai quản lý. | Định nghĩa từ nguồn cấu hình đáng tin cậy, áp allowlist và egress policy. |

**Không phải cứ đọc claim `iss` là đã tin claim đó.** Một resolver nhiều issuer có thể đọc `iss` chưa xác thực để tìm decoder, nhưng phải đối chiếu allowlist trước khi tạo/tải decoder, rồi xác minh chữ ký và kiểm tra lại `iss` trong token đã được xử lý.

### 3.2. Những URL trông giống “được phép” nhưng không được chấp nhận

Giả sử chính sách chỉ cho:

~~~text
https://login.example.test/realms/demo/protocol/openid-connect/certs
~~~

Những ví dụ dưới đây **không được tự động xem là tương đương**:

~~~text
http://login.example.test/realms/demo/protocol/openid-connect/certs
https://login.example.test.attacker.example/realms/demo/protocol/openid-connect/certs
https://login.example.test@attacker.example/jwks.json
https://login.example.test:9443/other-keys
https://attacker.example/redirect-to-login-jwks
https://127.0.0.1:8443/admin/keys
https://169.254.169.254/latest/meta-data/
~~~

Các URL trên minh họa lỗi về **scheme, hostname, userinfo, port, redirect hoặc đích mạng nội bộ**. Chúng không phải địa chỉ dùng trong cấu hình hoạt động. Chính sách “URL chỉ cần bắt đầu bằng `https://login.example.test`” là không phù hợp vì có thể nhận nhầm hostname dài hơn.

## 4. Cấu hình Spring Boot: tải JWKS trực tiếp qua HTTPS và vẫn kiểm tra issuer

### 4.1. Dependency

Ví dụ Gradle (Groovy DSL) cho Spring Boot ứng dụng Servlet:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Starter Resource Server thông thường cung cấp các thành phần xử lý Bearer token và kéo theo **Spring Security JOSE** để xử lý JWT. Nếu không dùng starter và cấu hình từng module, JWT Resource Server thường cần cả `spring-security-oauth2-resource-server` và `spring-security-oauth2-jose` với phiên bản tương thích.

### 4.2. application.yml

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

Ý nghĩa:

- **`issuer-uri`**: Resource Server yêu cầu claim `iss` đúng với issuer tin cậy.
- **`jwk-set-uri`**: decoder biết trước nơi lấy JWK Set. Với cơ chế tự cấu hình tương ứng, không phải khám phá metadata chỉ để tìm `jwks_uri`.
- **`audiences`**: yêu cầu claim `aud` chứa `orders-api` trên những phiên bản Spring Boot hỗ trợ thuộc tính này; nếu phiên bản chưa hỗ trợ, cần audience validator riêng.
- Việc xác minh chữ ký/claims thực hiện bởi Spring Security JWT decoder và validator đã cấu hình.

**Tại sao vẫn khai báo `issuer-uri`?** Nếu chỉ cấu hình `jwk-set-uri`, decoder biết nguồn khóa nhưng không có chính sách issuer từ thuộc tính đó. API cần xác định issuer được tin cậy, vì public keys có thể được sử dụng trong nhiều ngữ cảnh.

Ví dụ cấu hình **thiếu ràng buộc issuer**:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          jwk-set-uri: https://login.example.test/realms/demo/protocol/openid-connect/certs
~~~

Cấu hình trên có thể xác minh chữ ký dựa vào public keys, nhưng **không nên giả định nó sẽ kiểm tra `iss` giống cấu hình có `issuer-uri`**. Khi không khai báo issuer URI, phải bổ sung validator issuer theo cách khác.

### 4.3. Khác nhau giữa issuer discovery và JWKS URI trực tiếp

Với chỉ `issuer-uri`, Spring Security có thể sử dụng OIDC Provider Metadata hoặc OAuth 2.0 Authorization Server Metadata để tìm **`jwks_uri`**:

~~~json
{
  "issuer": "https://login.example.test/realms/demo",
  "jwks_uri": "https://login.example.test/realms/demo/protocol/openid-connect/certs"
}
~~~

Khi biết trước URI JWKS, cấu hình trực tiếp giúp tránh phụ thuộc vào bước **discovery để xác định endpoint khóa**. Tuy nhiên, việc cần kết nối mạng để lấy JWK mới/cập nhật khóa, chính sách cache và thời điểm tải phụ thuộc phiên bản thư viện và cách cấu hình.

| Tình huống | Nguồn JWKS | Ràng buộc `iss` |
| --- | --- | --- |
| Chỉ `issuer-uri` với auto-config phù hợp | Tìm qua metadata của issuer. | Có từ issuer tin cậy. |
| Chỉ `jwk-set-uri` | URI trực tiếp. | **Phải chủ động xác minh** nếu API có một issuer cố định. |
| `issuer-uri` + `jwk-set-uri` | URI trực tiếp. | Có từ issuer đã khai báo trong auto-config tương ứng. |
| Tự tạo `NimbusJwtDecoder.withJwkSetUri` | URI trực tiếp do code/config truyền vào. | Tạo `JwtValidators.createDefaultWithIssuer` và các validators khác tường minh. |

Chỉ để HTTPS endpoint JWKS khả dụng **không đồng nghĩa Resource Server có thể hoạt động offline hoàn toàn**. Decoder vẫn phải lấy khóa cần thiết khi cache chưa có, khi `kid` mới xuất hiện hoặc khi cần làm mới JWK Set.

## 5. Thiết kế allowlist cho nguồn JWKS

“Allowlist” là tập những nguồn được quản trị phê duyệt để cung cấp khóa. Có nhiều mức kiểm soát:

1. **Danh sách issuer được phép:** những `iss` nào API chấp nhận.
2. **Ánh xạ issuer → JWKS endpoint:** từng issuer được lấy khóa từ endpoint nào.
3. **Kiểm soát URL chính xác:** scheme, host, port, path và query theo chính sách.
4. **Kiểm soát kết nối outbound:** mạng/firewall/proxy của Resource Server chỉ cho phép kết nối tới đích được phê duyệt.
5. **Kiểm soát TLS:** chứng chỉ và hostname hợp lệ, truststore được quản lý, không tắt xác minh.

Không có một bước kiểm tra chuỗi URL nào thay thế được tất cả các lớp trên. Ví dụ, kiểm tra host trên chuỗi URL ở tầng ứng dụng có thể bị ảnh hưởng bởi DNS, redirect hoặc proxy; cần phối hợp cấu hình kết nối và network policy.

### 5.1. Allowlist URI chính xác hay chỉ cho phép domain?

| Cách kiểm tra | Ưu điểm | Rủi ro / điều kiện |
| --- | --- | --- |
| **So sánh chính xác HTTPS JWKS URI** | Khó nhận nhầm hostname/path/port; phù hợp một issuer cố định. | Khi endpoint thay đổi cần cập nhật cấu hình theo quy trình. |
| **Allowlist hostname + scheme/port/path** | Linh hoạt cho nhiều realm/tenant được quản lý. | Phải kiểm soát chính xác path, suffix, redirect và DNS; không dùng `startsWith`. |
| **Wildcard rộng cho nhiều domain** | Dễ cấu hình lúc ban đầu. | Mở rộng bề mặt tin cậy; nếu một host con bị chiếm quyền có thể thành nguồn khóa giả. |
| **Tự tin mọi HTTPS JWKS URL** | Có vẻ thuận tiện cho tenant động. | **Không phù hợp**: kẻ ngoài có thể chọn một HTTPS host hợp lệ và cung cấp khóa của họ. |

Với API chỉ tin một issuer, **cố định JWKS URI được phép** thường là phương án rõ ràng. Với đa issuer, duy trì **bản đồ issuer → JWKS URI** đã được phê duyệt; thay đổi mapping phải được kiểm soát như thay đổi chính sách bảo mật.

### 5.2. Ví dụ so sánh allowlist URI ở tầng cấu hình

Giả sử một thành phần của ứng dụng nhận JWKS URL từ cấu hình triển khai được quản lý, **không phải** từ HTTP request. Ta có thể kiểm tra URL trước khi tạo decoder:

~~~java
import java.net.URI;
import java.util.Set;

public final class TrustedJwksEndpoints {

    private static final Set<String> ALLOWED_URI_STRINGS = Set.of(
        "https://login.example.test/realms/demo/protocol/openid-connect/certs"
    );

    private TrustedJwksEndpoints() {}

    public static URI requireApproved(String configuredUrl) {
        URI uri = URI.create(configuredUrl);

        if (!"https".equalsIgnoreCase(uri.getScheme())
                || uri.getHost() == null
                || uri.getUserInfo() != null
                || uri.getRawQuery() != null
                || uri.getRawFragment() != null
                || !ALLOWED_URI_STRINGS.contains(configuredUrl)) {
            throw new IllegalArgumentException(
                "JWKS endpoint is not approved");
        }

        return uri;
    }
}
~~~

Ví dụ trên chọn **so khớp chuỗi URI chính xác theo chính sách**, tránh cho URL có query/fragment/userinfo hoặc địa chỉ khác đi qua. Trong ứng dụng nhiều môi trường, allowlist có thể được cấp từ cấu hình triển khai do tổ chức kiểm soát; vẫn phải được phê duyệt trước. Nếu cần quy tắc URI linh hoạt hơn, dùng parser URI và policy đã được thiết kế, không so sánh prefix đơn giản.

**Giới hạn của ví dụ:** xác nhận URI ở cấp ứng dụng **không tự chặn HTTP redirect hoặc DNS rebinding**. Nó cũng không bảo đảm proxy, egress gateway và thư viện HTTP đang kết nối đúng địa chỉ được cấp phép. Cần phối hợp kiểm soát outbound ở hạ tầng và hành vi HTTP client (mục 7).

### 5.3. Không nhập URL từ token rồi “kiểm tra cho có”

Ví dụ sai về thiết kế:

~~~java
// KHÔNG LÀM: token chưa được xác minh có thể bị người gửi kiểm soát.
String jwksUrl = unverifiedJwtHeader.get("jku");
JwtDecoder decoder = NimbusJwtDecoder
    .withJwkSetUri(jwksUrl)
    .build();
~~~

Điều này biến bên gửi token thành người chọn nguồn khóa được xác minh. Tương tự, không nên lấy một URL tùy ý từ `iss` chưa kiểm tra rồi cho phép tải issuer metadata/JWKS từ đó.

Trong ứng dụng Spring Security thông thường, `NimbusJwtDecoder.withJwkSetUri(...)` nhận **URI do ứng dụng cấu hình**. Hãy giữ ranh giới đó, tránh xây cơ chế động nhận `jku`, `x5u` hoặc tham số `jwksUrl` do client gửi.

## 6. Cấu hình NimbusJwtDecoder với nguồn JWKS được phép

Nếu cần tự tạo bean thay vì dùng Spring Boot auto-configuration, có thể kiểm tra allowlist rồi thiết lập decoder cùng các validators.

Ví dụ này sử dụng thuộc tính tùy chỉnh **`app.security.jwt.jwks-uri`** do hệ thống triển khai cấu hình; nó không phải thuộc tính auto-config của Spring Boot:

~~~yaml
app:
  security:
    jwt:
      jwks-uri: https://login.example.test/realms/demo/protocol/openid-connect/certs
~~~

Bean Java:

~~~java
import java.net.URI;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
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
public class ApprovedJwksDecoderConfig {

    private static final String TRUSTED_ISSUER =
        "https://login.example.test/realms/demo";
    private static final String API_AUDIENCE = "orders-api";

    @Bean
    JwtDecoder jwtDecoder(Environment environment) {
        String configuredUrl = environment.getRequiredProperty(
            "app.security.jwt.jwks-uri");
        URI trustedJwks =
            TrustedJwksEndpoints.requireApproved(configuredUrl);

        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(trustedJwks.toString())
            .jwsAlgorithm(SignatureAlgorithm.RS256)
            .build();

        OAuth2TokenValidator<Jwt> audienceValidator = jwt ->
            jwt.getAudience().contains(API_AUDIENCE)
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        "invalid_token",
                        "JWT audience is not accepted",
                        null));

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(TRUSTED_ISSUER),
                audienceValidator));

        return decoder;
    }
}
~~~

Với hai class Java trong ví dụ:

- **`requireApproved`** chỉ cho phép endpoint JWKS thuộc allowlist.
- **`withJwkSetUri`** lấy public keys từ endpoint đã chọn.
- **`jwsAlgorithm(RS256)`** giới hạn thuật toán xác minh theo hợp đồng với issuer.
- **`createDefaultWithIssuer`** giữ kiểm tra issuer và các điều kiện JWT mặc định như thời hạn.
- **`audienceValidator`** yêu cầu token được phát hành cho `orders-api`.

Nếu tự khai báo bean **`JwtDecoder`**, Spring Boot thường không tạo decoder auto-configured khác. Vì vậy, không nên chỉ dựa vào thuộc tính `issuer-uri` hoặc `audiences` trong YAML mà **quên đặt validators trong decoder tùy chỉnh**.

**Đây là mã minh họa cho môi trường có một issuer và một JWKS endpoint.** Khi triển khai cần định nghĩa mapping cho từng môi trường, network egress policy và hành vi HTTP client. Giá trị issuer, audience và allowed URI trong ví dụ phải được thay bằng hợp đồng token thực tế.

### 6.1. Tại sao có cả issuer validator nếu đã xác minh chữ ký?

JWT này có thể được ký đúng bởi khóa trong JWKS nhưng có các claim:

~~~json
{
  "iss": "https://another-issuer.example.test",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 1893456000
}
~~~

Việc chữ ký hợp lệ **không cho phép bỏ qua claim `iss`**. Để chấp nhận token, issuer phải đúng nhà phát hành được tin cậy; audience cũng phải đúng API hiện tại. Nếu một khóa bị dùng chung giữa nhiều hệ thống, ràng buộc issuer càng quan trọng.

Khi gọi **`setJwtValidator`**, phải đưa các quy tắc cần thiết vào bộ validator cuối cùng. Không chỉ đặt một validator audience rồi vô tình làm mất kiểm tra issuer/thời hạn.

### 6.2. Bật Resource Server trong SecurityFilterChain

Ví dụ một API chỉ nhận Bearer Access Token:

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
    SecurityFilterChain apiFilterChain(HttpSecurity http)
            throws Exception {
        http
            .securityMatcher("/api/**")
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

Trong hệ thống này, `JwtDecoder` đã cấu hình sẽ xác minh token trước khi Spring Security kiểm tra **`SCOPE_orders.read`** hoặc **`SCOPE_orders.write`**. Việc vô hiệu hóa CSRF trong ví dụ chỉ phù hợp với API thuần Bearer header không dùng session cookie; với OIDC Login cho web cần thiết kế CSRF theo từng security chain.

JWKS URI là **cấu hình của Resource Server**, không được lấy từ JWT hoặc từ header của request đang cần xác minh.

## 7. Bảo vệ đường tải JWKS: TLS, redirect, DNS và egress

### 7.1. Sử dụng HTTPS với xác minh chứng chỉ thực

HTTP client truy cập JWKS cần kiểm tra:

1. URI dùng **`https`**, không tự chuyển sang HTTP khi HTTPS lỗi.
2. Chứng chỉ máy chủ hợp lệ theo **truststore** mà runtime được phép dùng.
3. **Hostname verification** khớp host của URL. Chứng chỉ hợp lệ cho host khác không đủ.
4. Chuỗi chứng chỉ còn trong thời hạn và không bị từ chối theo chính sách TLS của hệ thống.
5. Truststore, CA doanh nghiệp, reverse proxy TLS hoặc mTLS (nếu dùng) được quản lý bởi hạ tầng và theo quy trình vận hành.

Không dùng `TrustManager` chấp nhận mọi chứng chỉ hoặc tắt hostname verification chỉ để “hết lỗi SSL”. Điều đó khiến TLS mất chức năng xác thực endpoint. Nếu hệ thống dùng CA nội bộ, cấu hình truststore tin đúng CA nội bộ thay vì chấp nhận mọi chứng chỉ.

**Certificate pinning** có thể hữu ích trong một số mô hình đặc biệt nhưng tăng chi phí rotation; không phải yêu cầu mặc định cho mọi Resource Server. Trong đa số triển khai, cần xác thực TLS chuẩn, mapping endpoint được phép và kiểm soát egress rõ ràng.

### 7.2. HTTP redirects có thể thay đổi đích cuối

Giả sử URI được phép là:

~~~text
https://login.example.test/keys
~~~

nhưng server trả `302 Location: https://other-host.example.test/keys`. Nếu HTTP client tự theo redirect mà không kiểm tra đích mới, **kết nối thực tế có thể đi tới nguồn chưa được duyệt**.

Thiết kế an toàn nên:

- **Không cho phép redirect** khi tải JWKS nếu không có nhu cầu đã được phê duyệt; hoặc
- Chỉ cho phép redirect theo chính sách nghiêm ngặt, kiểm tra **mỗi đích mới** (scheme/host/port/path) và áp network egress policy ở từng kết nối.

Một URL vượt qua allowlist ở lần kiểm tra ban đầu **không bảo đảm redirect tiếp theo cũng được phép**. Hành vi redirect thực tế phụ thuộc HTTP client nằm dưới Nimbus/Spring Security và cấu hình ứng dụng; cần thiết lập rõ ở tầng HTTP client hoặc egress gateway.

### 7.3. DNS và đích mạng thực

Một hostname được phép có thể resolve thành nhiều IP tùy thời điểm. Mô hình đe dọa cần xét:

- DNS bị sửa hoặc điều hướng sai.
- DNS rebinding: host ban đầu trỏ IP được phép, sau đó đổi sang địa chỉ khác.
- Kết nối tới loopback, mạng nội bộ, link-local hoặc các địa chỉ metadata dịch vụ đám mây.
- HTTP proxy hoặc service mesh thay đổi đường outbound so với dự kiến.

Không nên tự kiểm tra một lần `InetAddress.getByName` rồi tin rằng mọi kết nối về sau đều dùng đúng IP đó. Việc bảo vệ đầy đủ cần **network policy, firewall/egress proxy và kiểm soát DNS** nhất quán với chính sách tải JWKS. Có thể kết hợp xác minh hostname bằng TLS và chặn outbound tới mạng không được phép.

Với một dịch vụ chỉ cần gọi IdP/JWKS, cấu hình egress cho phép **những đích cần thiết** giúp giảm khả năng SSRF nếu mã ứng dụng có lỗi. Allowlist URI ở Java và egress policy ở hạ tầng là **hai lớp bảo vệ độc lập**.

### 7.4. Giới hạn timeout, kích thước và tải

Tải JWKS là một hoạt động HTTP từ Resource Server tới dịch vụ khác. Cần quan tâm:

- **Connection timeout** và **read timeout** để tránh giữ tài nguyên quá lâu khi endpoint lỗi.
- Giới hạn số lượng kết nối và yêu cầu tải lại để tránh gây tải bất thường.
- Giới hạn response size và số lượng/định dạng JWK theo khả năng hạ tầng và HTTP client.
- Giới hạn loại nội dung, JSON parsing và việc xử lý response lỗi.
- Cache public keys để không gọi JWKS trên mỗi request.

Hành vi mặc định, API cấu hình HTTP client và thời gian cache có thể khác nhau giữa các phiên bản Spring Security/Nimbus. Khi cần chính sách riêng, dùng HTTP client do ứng dụng cấu hình và tích hợp với `NimbusJwtDecoder` theo API của phiên bản sử dụng. **Không tùy ý tăng timeout rất lớn hoặc tắt kiểm tra TLS để xử lý lỗi kết nối.**

## 8. Khi dùng issuer discovery, có cần kiểm tra jwks_uri được metadata trả về?

**Có, nguồn JWKS vẫn phải nằm trong ranh giới tin cậy được thiết kế.** Dù bắt đầu từ một issuer đã được cho phép, hệ thống vẫn đang đọc địa chỉ `jwks_uri` từ metadata được tải qua mạng.

Ví dụ metadata:

~~~json
{
  "issuer": "https://login.example.test/realms/demo",
  "jwks_uri": "https://keys.example.test/oauth2/jwks"
}
~~~

JWKS trên host khác **không tự động là sai**: Authorization Server có thể công bố khóa trên một hostname chuyên dụng. Nhưng nếu yêu cầu an toàn của tổ chức chỉ cho `login.example.test`, phải phê duyệt rõ host `keys.example.test` hoặc dùng cấu hình JWKS URI cố định thích hợp.

Các câu hỏi cần xác định khi thiết kế:

- Metadata được tải từ **issuer được phép** và qua HTTPS hợp lệ không?
- Giá trị `issuer` trong metadata có khớp issuer được cấu hình không?
- `jwks_uri` có nằm trong tập endpoint nguồn khóa được cho phép không?
- HTTP client tải metadata/JWKS có thể đi theo redirect ra ngoài allowlist không?
- Egress policy có chặn nguồn không được phép kể cả khi cấu hình ứng dụng sai không?

Nếu cần kiểm soát **rất chặt địa chỉ JWKS**, việc cấu hình `issuer-uri` cùng **`jwk-set-uri` chính xác** thường đơn giản để quản trị hơn. Nó tách việc *định danh issuer* khỏi việc *chọn endpoint cung cấp khóa*, đồng thời tránh phải chấp nhận mọi `jwks_uri` động.

## 9. Multi-tenant và nhiều issuer: allowlist theo cặp issuer – JWKS

Trong hệ thống nhiều tenant hoặc nhiều nhà phát hành, một Resource Server có thể chấp nhận token từ nhiều Authorization Server:

~~~text
Issuer A: https://login-a.example.test/realms/a
JWKS A:   https://login-a.example.test/realms/a/certs

Issuer B: https://login-b.example.test/realms/b
JWKS B:   https://login-b.example.test/realms/b/certs
~~~

Không nên thay một issuer cố định bằng chiến lược:

~~~text
JWT.iss -> tự ghép URL /.well-known/... -> tải keys -> tin issuer
~~~

với mọi URI mà client đưa vào. Nếu làm vậy, kẻ ngoài có thể tự dựng issuer riêng cùng public keys của họ rồi làm Resource Server xác thực token giả.

Thay vào đó, hệ thống có thể quản lý bảng:

| Issuer được phép | JWKS URI được phép | API audiences áp dụng |
| --- | --- | --- |
| `https://login-a.example.test/realms/a` | `https://login-a.example.test/realms/a/certs` | `orders-api` |
| `https://login-b.example.test/realms/b` | `https://login-b.example.test/realms/b/certs` | `orders-api` |

Một resolver nhiều issuer, ví dụ cơ chế phù hợp như **`JwtIssuerAuthenticationManagerResolver`** trong Spring Security Servlet, có thể chọn AuthenticationManager/decoder cho các issuer được **cho phép trước**. Claim `iss` chưa xác minh chỉ dùng để chọn đường xử lý theo allowlist, **không dùng làm chứng cứ xác thực**.

~~~text
Bearer JWT
   |
   v
Đọc iss chưa xác minh để chọn nhánh
   |
   v
Issuer nằm trong allowlist?
   | Không                 | Có
   v                       v
Từ chối             Chọn decoder/JWKS đã phê duyệt
                           |
                           v
                  HTTPS/TLS + egress controls
                           |
                           v
                  Kiểm tra chữ ký
                  Kiểm tra lại iss
                  Kiểm tra aud, exp, nbf
                           |
                           v
                      Authorization
~~~

**Tránh chia sẻ cache nguồn khóa giữa các issuer theo chỉ mỗi `kid`**. Hai issuer khác nhau có thể chọn cùng giá trị `kid`; khóa tin cậy luôn phải gắn với **nguồn JWKS/issuer** tương ứng. Điều kiện về scope/roles/tenant cũng có thể khác giữa các issuer, cần quy ước chuyển đổi riêng.

## 10. Caching và vòng đời khóa

### 10.1. Vì sao cần cache JWKS?

Resource Server thường nhận rất nhiều Bearer requests. Nếu mỗi request lại tải JWKS:

- Độ trễ xác thực tăng do phụ thuộc mạng.
- Authorization Server/JWKS endpoint dễ quá tải.
- Bất kỳ sự cố mạng nào cũng có thể ảnh hưởng nhiều request.
- Một nguồn không được kiểm soát có thể trở thành điểm để gây kiệt tài nguyên.

Nimbus/Spring Security có cơ chế cache JWK Set tùy phiên bản và cấu hình. Mục tiêu là **tái sử dụng các public keys đã được kiểm tra**, đồng thời **làm mới khi cần** để đáp ứng thay đổi khóa.

Cache giúp giảm tải nhưng **không thay thế allowlist hoặc HTTPS**. Public key từng được tải từ nguồn sai vẫn có thể nguy hiểm nếu bị cache lâu.

### 10.2. Quy trình rotation đúng

Ví dụ issuer dùng khóa `key-A`, sau đó chuyển sang `key-B`:

~~~text
T0: JWKS công bố key-A; token ký bằng key-A
T1: JWKS công bố cả key-A và key-B
T2: Authorization Server bắt đầu ký token mới bằng key-B
T3: Resource Server tiếp tục nhận token cũ key-A còn hạn
T4: Token key-A cuối cùng hết hạn (hoặc bị xử lý theo chính sách)
T5: JWKS loại key-A
~~~

Việc công bố **key-B trước khi dùng key-B để ký** giúp decoder có cơ hội cập nhật JWKS và tránh chặn token mới trong giai đoạn chuyển tiếp. Giữ **key-A** trong thời gian token cũ còn hiệu lực giúp hệ thống tiếp tục xác minh những token đó.

Trong trường hợp khóa bị lộ, kế hoạch thu hồi khẩn cấp có thể khác luồng rotation bình thường: phải cân nhắc giảm thời gian token còn được chấp nhận, cập nhật JWKS/caches, ngăn lạm dụng và có thể thay đổi chính sách xác thực.

### 10.3. Điều gì xảy ra nếu JWKS endpoint ngừng hoạt động?

| Trạng thái | Hành vi kỳ vọng |
| --- | --- |
| Decoder đã có public key tin cậy trong cache cho token đang xét | Có thể xác minh tiếp theo chính sách cache/TTL hiện hành. |
| Decoder cần một public key chưa cache | Phải lấy từ JWKS đáng tin cậy; nếu không thể, **không chấp nhận token chưa được xác minh**. |
| JWKS trả dữ liệu sai định dạng hoặc không có key phù hợp | Từ chối token tương ứng và ghi nhận lỗi vận hành an toàn. |
| JWKS đổi sang endpoint mới ngoài allowlist | Chặn việc đổi nguồn tự phát; cần cập nhật chính sách và cấu hình đã phê duyệt. |
| JWKS được trả từ nguồn khác qua redirect | Không tự tin redirect; phải áp chính sách đã thiết kế cho đích cuối. |

Không chuyển sang cách “chỉ decode payload và kiểm tra `exp`” khi JWKS lỗi. Đây là việc **bỏ xác minh chữ ký** và biến token tự khai thành credential được tin.

### 10.4. Quyền truy cập của token thay đổi trong thời gian sống

JWKS là cơ chế **xác minh khóa ký**, không phải cơ sở dữ liệu quyền truy cập theo thời gian thực. Một JWT đã ký hợp lệ vẫn có thể mang các quyền đã được cập nhật ở hệ thống gốc, cho đến khi token hết hạn hoặc Resource Server có cơ chế kiểm tra bổ sung. Vì vậy, việc rotation JWKS **không tự động thu hồi mọi token** và kiểm tra `scope` không thay thế các quy tắc truy cập dữ liệu cần tính hiện thời.

## 11. Kiểm thử ranh giới HTTPS và allowlist

Kiểm thử nên chứng minh hai nhóm riêng:

1. **Kiểm thử chính sách nguồn JWKS:** chỉ URL/issuer được phê duyệt mới được dùng để nạp khóa; không theo redirect hoặc URL ngoài allowlist; TLS phải được xác minh.
2. **Kiểm thử xác minh JWT:** với nguồn khóa đúng, chữ ký/issuer/audience/thời hạn/thuật toán phải được kiểm tra, và authorization vẫn dựa trên scope/roles.

### 11.1. Ma trận tình huống

| Tình huống | Kết quả mong đợi |
| --- | --- |
| URI HTTPS chính xác thuộc allowlist, chứng chỉ/hostname hợp lệ | Được phép tải JWKS và xác minh JWT theo cấu hình. |
| JWKS URI dùng HTTP | Từ chối ở cấu hình/chính sách; không hạ cấp TLS. |
| URL có hostname gần giống nguồn tin cậy | Không thuộc allowlist, không tải khóa. |
| URL chứa userinfo hoặc port/path ngoài quy định | Không được coi là nguồn khóa đã được phép. |
| JWKS endpoint hợp lệ nhưng redirect sang host lạ | Không theo redirect trái chính sách. |
| Hostname được phép resolve tới mạng/đích bị cấm | Egress policy chặn kết nối; không tự cấp quyền. |
| Chứng chỉ TLS sai hostname, hết hạn hoặc CA không được tin | Không bỏ qua certificate/hostname verification. |
| Token header có `jku` hoặc `x5u` trỏ endpoint khác | Không tải khóa từ URL đó. |
| JWT có `kid` lạ nhưng JWKS không có key phù hợp | Xác thực token thất bại. |
| JWT ký đúng nhưng issuer không thuộc allowlist | Từ chối JWT. |
| JWT ký đúng, issuer đúng nhưng audience khác API | Từ chối JWT. |
| JWT đúng và có `orders.read` | Đi tiếp tới authorization của GET tương ứng. |
| JWT hợp lệ nhưng thiếu `orders.read` | Thường **403** tại endpoint yêu cầu scope đó. |
| JWKS tạm thời không truy cập được, decoder chưa có khóa | Không bỏ xác minh, xử lý lỗi an toàn. |

### 11.2. Unit test cho allowlist cấu hình

Với helper `TrustedJwksEndpoints` ở mục 5:

~~~java
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class TrustedJwksEndpointsTest {

    @Test
    void approvedUriIsAccepted() {
        var uri = TrustedJwksEndpoints.requireApproved(
            "https://login.example.test/realms/demo/protocol/openid-connect/certs");

        assertEquals("https", uri.getScheme());
    }

    @Test
    void httpAndUnexpectedHostsAreRejected() {
        assertThrows(IllegalArgumentException.class, () ->
            TrustedJwksEndpoints.requireApproved(
                "http://login.example.test/realms/demo/protocol/openid-connect/certs"));

        assertThrows(IllegalArgumentException.class, () ->
            TrustedJwksEndpoints.requireApproved(
                "https://login.example.test.attacker.example/jwks.json"));
    }

    @Test
    void queryStringIsNotPartOfApprovedUri() {
        assertThrows(IllegalArgumentException.class, () ->
            TrustedJwksEndpoints.requireApproved(
                "https://login.example.test/realms/demo/protocol/openid-connect/certs?x=1"));
    }
}
~~~

Test này xác minh **so khớp URL cấu hình ở Java**. Nó không tạo HTTP connection, vì vậy **không kiểm tra TLS, DNS, redirect hoặc egress**. Những điều đó cần test tầng mạng/HTTP client và chính sách triển khai tương ứng.

### 11.3. Kiểm thử JwtDecoder bằng khóa test

Trong test JWT decoder, tạo một RSA key pair chỉ dùng cho test, ký JWT bằng private key test và xác minh bằng public key test hoặc JWKS endpoint cục bộ. Cần có kịch bản:

- **Đúng chữ ký + issuer + audience + thời hạn:** decode thành công.
- **Sai chữ ký:** decoder từ chối dù claims có vẻ hợp lệ.
- **Sai issuer nhưng chữ ký đúng:** decoder từ chối nhờ issuer validator.
- **Sai audience nhưng chữ ký/issuer đúng:** decoder từ chối nhờ audience validator.
- **`exp` đã qua hoặc `nbf` chưa đến:** decoder từ chối.
- **`kid` không khớp khóa nào trong JWKS:** không thể xác minh và phải từ chối.
- **Algorithm khác cấu hình:** không được tự chuyển sang một thuật toán mới chỉ vì header yêu cầu.

**MockMvc `jwt()`** của `spring-security-test` thuận tiện để thử endpoint authorization, nhưng nó tạo Authentication giả lập và **không buộc NimbusJwtDecoder kiểm tra chữ ký/JWKS**. Muốn kiểm tra đường nạp khóa, phải dùng **JWT ký thật qua decoder** hoặc integration test gửi JWT vào `Authorization: Bearer` với JWKS server giả lập.

### 11.4. Integration test với JWKS HTTP server cục bộ

Thiết kế kiểm thử có thể như sau:

~~~text
Test fixture
  |-- Tạo RSA private/public key pair chỉ dành cho test
  |-- Công bố public key tại JWKS endpoint test
  |-- Ký các JWT có claims đúng/sai theo từng case
  |
  v
HTTP request: Authorization: Bearer <signed-test-jwt>
  |
  v
Spring BearerTokenAuthenticationFilter
  |
  v
NimbusJwtDecoder.withJwkSetUri(test JWKS endpoint)
  |
  +-- lấy JWKS
  +-- xác minh chữ ký
  +-- kiểm tra issuer/audience/thời hạn
  |
  v
SecurityFilterChain: scope và policy -> 200 / 401 / 403
~~~

Nếu test JWKS dùng localhost/HTTP, hãy giữ ngoại lệ **chỉ trong môi trường test cô lập**, không áp dụng cho cấu hình production. Với kiểm thử bảo mật TLS, sử dụng HTTPS test endpoint với certificate/CA fixture phù hợp và xác minh rằng kết nối sai chứng chỉ bị từ chối. Không dùng khóa hoặc Access Token production trong test.

## 12. Quan sát, ghi log và xử lý lỗi an toàn

Resource Server cần có tín hiệu để nhận biết lỗi JWKS hoặc rotation nhưng không làm lộ credential. Những dữ liệu vận hành có thể ghi:

- **Loại lỗi**: JWKS connection failure, TLS verification failure, unknown key ID, issuer mismatch, audience mismatch, expired token.
- **Tên dịch vụ/issuer đã được cấu hình** và mã nhận diện cấu hình đã kiểm soát, khi được phép.
- **Request ID** do hệ thống sinh và timestamp.
- **Số lượng lỗi theo nhóm**, latency tải JWKS, tỷ lệ 401/403, tỷ lệ cache hit/miss nếu thư viện cho phép theo dõi.
- **Tình trạng JWKS endpoint đã được phép**, ví dụ lỗi kết nối, DNS hoặc chứng chỉ.

Không ghi:

- Nguyên JWT hoặc header `Authorization`.
- Client secret, refresh token, private signing key hoặc thông tin TLS key store nhạy cảm.
- Toàn bộ request/response HTTP nếu chúng có thể chứa token hoặc dữ liệu ngoài kiểm soát.
- Mọi chuỗi URL chưa được xác thực do token/client gửi dưới dạng một endpoint “đáng tin” trong log hoặc monitoring.

### 12.1. HTTP 401 khác HTTP 403

Với Resource Server được cấu hình đúng:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
~~~

thường xuất hiện khi không có token hoặc token không thể xác thực (chữ ký sai, issuer/audience sai, token hết hạn...). Một JWT đã được xác thực nhưng thiếu quyền cho endpoint có thể nhận:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
~~~

Giá trị chi tiết trong `WWW-Authenticate` có thể tùy trường hợp/framework. Không phản chiếu raw exception, URL nội bộ nhạy cảm, stack trace hoặc token vào error body.

### 12.2. Một kịch bản vận hành

**Tình huống:** Authorization Server bắt đầu ký bằng khóa `rsa-2026-b`, nhưng một số instance Resource Server vẫn chỉ có khóa `rsa-2026-a` trong cache.

Các bước điều tra:

1. Xác minh JWKS endpoint **đã được phép** thực sự công bố cả khóa cũ và mới trong giai đoạn chuyển tiếp.
2. Kiểm tra `kid` của token lỗi và danh sách public keys đã công bố bằng công cụ vận hành an toàn, **không ghi nguyên token**.
3. Kiểm tra TLS, egress connectivity, refresh/cache timing của từng instance.
4. Xác nhận issuer/audience/thời hạn vẫn đúng; một lỗi 401 có thể đến từ validator khác, không chỉ khóa.
5. Khắc phục việc phân phối/cập nhật khóa theo kế hoạch rotation, giữ nguyên nguyên tắc **không nhận token khi không xác minh được**.

Nếu JWKS URI bị đổi sang một hostname mới, phải cập nhật danh sách nguồn được phép qua quy trình cấu hình đã kiểm soát. Không tự động bổ sung hostname mới chỉ vì một JWT hoặc error response gợi ý.

## 13. Những hiểu nhầm cần tránh

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| “JWKS dùng HTTPS là an toàn tuyệt đối.” | HTTPS xác thực kết nối với hostname; endpoint còn phải **được cho phép cung cấp khóa** cho issuer. |
| “JWT có `jku` thì Resource Server phải tải URL đó.” | Không tải nguồn khóa do token chưa xác minh tự chọn; dùng issuer/JWKS được quản lý. |
| “`kid` là chứng cứ nhà phát hành.” | `kid` chỉ là định danh khóa; độ tin cậy đến từ **nguồn JWKS** và chữ ký được xác minh. |
| “Hostname bắt đầu bằng domain tin cậy là đủ.” | So sánh prefix dễ nhận nhầm hostname, userinfo, port, path; dùng URI parsing và allowlist rõ. |
| “Chặn URL tại Java là đã chặn mọi SSRF.” | Redirect, DNS, proxy và egress thực tế phải được kiểm soát riêng. |
| “Có JWKS đúng thì khỏi kiểm tra issuer.” | Nguồn khóa và claim `iss` là hai ràng buộc khác nhau. |
| “Issuer đúng nghĩa là JWT được phép gọi mọi API.” | Cần kiểm tra **audience** và authorization theo scope/permission. |
| “Dùng `jwk-set-uri` trực tiếp nghĩa là không bao giờ cần mạng.” | Decoder vẫn phải lấy public key khi chưa cache hoặc key mới xuất hiện. |
| “Có một public key thì key rotation tự hoạt động.” | Rotation cần công bố nhiều khóa đúng thời điểm, cache refresh và chính sách hết hạn. |
| “JWKS lỗi thì cho token đi qua để bảo đảm uptime.” | Không chấp nhận token chưa xác minh; xử lý sự cố vận hành mà giữ ranh giới tin cậy. |
| “JWT được ký thì payload được giữ bí mật.” | JWT dạng JWS có payload đọc được; tránh chứa dữ liệu nhạy cảm không cần thiết. |
| “MockMvc `jwt()` đã test JWKS.” | Nó kiểm tra behavior với Authentication giả lập; muốn test JWKS phải qua decoder/HTTP thật. |

## 14. Quy trình triển khai thực tế

1. **Xác định hợp đồng token:** issuer, audience Resource Server, loại JWT/JWS, thuật toán, thời hạn, scope và yêu cầu token profile.
2. **Công bố nguồn khóa đáng tin:** chọn JWKS HTTPS endpoint thuộc quyền quản lý của Authorization Server/đơn vị được phê duyệt; không đưa private key vào public JWKS.
3. **Lập allowlist issuer → JWKS:** cố định URI hoặc quản lý mapping được kiểm soát; không nhận URL từ client/token.
4. **Cấu hình Spring Security:** `issuer-uri` + `jwk-set-uri` và audience trong phiên bản Boot hỗ trợ, hoặc `NimbusJwtDecoder` với issuer/audience validators rõ ràng.
5. **Cấu hình TLS và egress:** xác thực hostname/chứng chỉ, giới hạn outbound, xử lý redirect, DNS và proxy theo chính sách.
6. **Cấu hình vòng đời khóa:** TTL/cache, công bố khóa trước rotation, duy trì khóa cũ khi token còn hạn, xử lý outage an toàn.
7. **Kiểm thử âm tính:** HTTP, URL ngoài allowlist, redirect ra host lạ, lỗi TLS, `jku` lạ, chữ ký sai, issuer/audience sai, khóa mới chưa có và quyền thiếu.
8. **Vận hành và giám sát:** theo dõi lỗi xác minh và JWKS connectivity mà không lộ JWT, secret hoặc dữ liệu riêng tư.

**Nguyên tắc cuối cùng:** Resource Server chỉ được dùng **public keys lấy từ nguồn JWKS đã được cấp phép**, tải qua **HTTPS/TLS được xác minh**, đồng thời kiểm tra **issuer, audience, thời hạn và quyền truy cập**. Một nguồn khóa sai có thể khiến chữ ký “hợp lệ” trở nên vô nghĩa; một nguồn khóa đúng cũng không thay thế chính sách chấp nhận token dành riêng cho API.

## Tài liệu tham khảo

- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html).
- [Spring Security — NimbusJwtDecoder API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/NimbusJwtDecoder.html).
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517).
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515).
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519).
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414).
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725).
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068).
- [OWASP — Server Side Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html).
