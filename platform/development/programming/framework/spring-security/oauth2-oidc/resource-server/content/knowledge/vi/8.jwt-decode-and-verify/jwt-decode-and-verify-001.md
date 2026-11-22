# JwtDecoder và sự khác nhau giữa phân tích cú pháp với xác minh

Trong **Spring Security OAuth 2.0/OIDC Resource Server**, API thường nhận access token qua HTTP header:

~~~http
GET /api/orders/42 HTTP/1.1
Host: orders-api.example.com
Authorization: Bearer eyJhbGciOiJSUzI1NiIsImtpZCI6...
~~~

Access token có thể là JWT chứa các claim như **iss**, **sub**, **aud**, **exp** và **scope**. JWT ký theo dạng JWS thường cho phép người cầm token giải mã Base64URL phần payload và đọc JSON ngay lập tức. Vì vậy một nhầm lẫn nguy hiểm là cho rằng **đọc được payload nghĩa là đã xác thực được token**.

**Phân tích cú pháp chỉ cho thấy token tuyên bố điều gì; xác minh chữ ký mới cho biết nội dung đó có được bảo vệ bởi khóa đáng tin cậy hay không; validation quyết định token có hợp lệ đối với API ở thời điểm hiện tại hay không.** Sau ba bước này, ứng dụng mới thực hiện authorization cho endpoint và dữ liệu cụ thể.

Spring Security cung cấp **JwtDecoder** làm ranh giới xử lý JWT. Với cấu hình JWT Resource Server thông thường, **NimbusJwtDecoder** vừa parse JWT, vừa kiểm chữ ký, vừa áp dụng các validator đã cấu hình. Tên “decoder” vì vậy mang nghĩa rộng hơn thao tác Base64URL decode đơn thuần.

## 1. Bốn hoạt động khác nhau: parse, verify, validate, authorize

| Hoạt động | Mục đích | Ví dụ | Giới hạn |
|---|---|---|---|
| **Parse / decode cú pháp** | Tách phần header, payload, signature; đọc dữ liệu JSON | Thấy **sub = user-123**, **scope = orders.read** | Chưa xác minh dữ liệu có thật hay đã bị sửa |
| **Verify chữ ký/MAC** | Kiểm cơ chế bảo vệ mật mã bằng khóa và thuật toán được tin cậy | Kiểm chữ ký RS256 với RSA public key của issuer | Chữ ký đúng chưa chứng minh token dành cho API này |
| **Validate claims** | Kiểm **iss**, **aud**, **exp**, **nbf**, token type và chính sách tiếp nhận | Từ chối token audience **payments-api** ở Orders API | Token hợp lệ chưa chứng minh người dùng được đọc mọi đơn hàng |
| **Authorize thao tác/tài nguyên** | Kiểm quyền nghiệp vụ, role/scope, tenant, owner, trạng thái tài nguyên | **orders.read** và đơn 42 thuộc phạm vi người dùng | Cần diễn ra ở endpoint/service/domain policy thích hợp |

Một số ví dụ cho thấy rõ sự khác biệt:

1. Payload chứa **ROLE_ADMIN**, nhưng do người gửi tự chỉnh JSON: parse vẫn thành công; chữ ký **không hợp lệ**.
2. Token được issuer ký hợp lệ nhưng **aud** là một API khác: chữ ký **hợp lệ**, claim validation **không đạt**.
3. Token có **iss/aud/exp** hợp lệ, đã được cấp **orders.read** nhưng đang đọc đơn của tenant khác: token được xác thực, authorization theo tài nguyên **không đạt**.

Như vậy, một JWT có JSON hợp lệ không phải bằng chứng đăng nhập, và một JWT ký đúng cũng chưa phải giấy phép truy cập dữ liệu bất kỳ.

## 2. Cấu trúc JWT/JWS giúp hiểu vì sao dễ bị nhầm

JWT ký theo **JWS Compact Serialization** thường có ba phần, ngăn bởi dấu chấm:

~~~text
BASE64URL(protected-header).BASE64URL(payload).BASE64URL(signature)
          phần 1                    phần 2                 phần 3
~~~

Ví dụ protected header sau khi giải mã:

~~~json
{
  "alg": "RS256",
  "typ": "at+jwt",
  "kid": "shop-sign-2026-11"
}
~~~

Ví dụ payload sau khi giải mã:

~~~json
{
  "iss": "https://login.example.com/realms/shop",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 1893456000,
  "tenant_id": "tenant-a"
}
~~~

Đây là các đoạn JSON **minh họa**, không phải một JWT đã ký có thể gọi API. Ý nghĩa:

- **alg** là thuật toán chữ ký token khai báo dùng, ví dụ RS256.
- **kid** là định danh gợi ý chọn public key từ một JWKS đáng tin cậy.
- **typ** chỉ loại token/profile; **at+jwt** thường dùng cho JWT access token theo RFC 9068.
- **iss** là issuer mà token tuyên bố phát hành.
- **sub** là định danh chủ thể trong ngữ cảnh issuer.
- **aud** là đối tượng nhận dự kiến, ở ví dụ là **orders-api**.
- **exp** là thời gian hết hạn dạng NumericDate.
- **scope** mô tả những scope đã được cấp theo chính sách OAuth2 của issuer.
- **tenant_id** là claim tùy biến, chỉ có thể dùng theo một hợp đồng tin cậy và kiểm quyền nghiệp vụ tương ứng.

Chữ ký JWS được tạo trên **chính signing input** gồm hai đoạn Base64URL đầu tiên, nối bằng dấu chấm:

~~~text
ASCII(BASE64URL(protected-header) + "." + BASE64URL(payload))
~~~

Nếu payload bị sửa từ **orders.read** thành **orders.write** mà không tạo lại chữ ký bằng khóa thích hợp, bước verify phải thất bại.

**Base64URL không phải encryption.** Bất kỳ ai giữ một JWS JWT thông thường đều có thể đọc header và payload dù không có private key. JWT signature bảo vệ tính toàn vẹn/xác thực, không che giấu claims. Tránh đặt mật khẩu, secret hoặc dữ liệu riêng tư không cần thiết vào payload.

### 2.1. Không phải mọi Bearer token đều là JWT ba phần

- **JWS Compact Serialization** thường có ba phần.
- **JWE Compact Serialization** thường có năm phần và mã hóa dữ liệu; việc giải mã cần thuật toán/khóa thích hợp.
- **Nested JWT** có thể kết hợp JWS và JWE.
- **Opaque token** có thể chỉ là chuỗi ngẫu nhiên; Resource Server thường xác minh bằng introspection.

**JwtDecoder** dùng cho JWT theo định dạng mà implementation hỗ trợ. Với opaque token, Spring Security sử dụng cơ chế **OpaqueTokenIntrospector**, không được tự tách token theo dấu chấm rồi suy ra nội dung.

## 3. Chỉ Base64URL decode JWT là chưa xác thực

Một đoạn Java thuần túy để quan sát payload:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Base64;

public final class UntrustedJwtViewer {

    // Chỉ để minh họa cấu trúc. KHÔNG dùng để xác thực hoặc cấp quyền.
    public static String readUntrustedPayload(String compactJws) {
        String[] parts = compactJws.split("\\.", -1);
        if (parts.length != 3) {
            throw new IllegalArgumentException("Expected a three-part JWS");
        }
        byte[] bytes = Base64.getUrlDecoder().decode(parts[1]);
        return new String(bytes, StandardCharsets.UTF_8);
    }
}
~~~

Đoạn này có thể đọc một payload như:

~~~json
{
  "sub": "attacker",
  "scope": "orders.read orders.write",
  "role": "ADMIN",
  "exp": 4102444800
}
~~~

Nhưng người gửi **tự tạo được toàn bộ payload**. Việc decode thành UTF-8 và parse thành JSON chỉ cho biết chuỗi là dữ liệu có cú pháp hợp lệ. Dấu chấm, Base64URL và JSON không bảo vệ khỏi giả mạo.

**Không** viết logic như sau:

~~~java
// SAI: claims chưa được xác minh.
String payload = UntrustedJwtViewer.readUntrustedPayload(rawBearerToken);
Map<String, Object> claims = readJson(payload);
String role = (String) claims.get("role");
grantRole(role);
~~~

Đây là đoạn mã minh họa **lỗi thiết kế**, trong đó **readJson** và **grantRole** là tên giả định. Dù thư viện JSON thật có tốt đến đâu, quyền được lấy từ dữ liệu do người gửi tự khai. Kẻ tấn công có thể sửa role hoặc scope và gửi lại token giả.

Cách đúng là để Resource Server xác minh token bằng **JwtDecoder** rồi mới tạo **Authentication/GrantedAuthority** từ những claims đã được chấp nhận.

## 4. Giao diện JwtDecoder của Spring Security

Giao diện trung tâm nằm trong package **org.springframework.security.oauth2.jwt**:

~~~java
public interface JwtDecoder {
    Jwt decode(String token) throws JwtException;
}
~~~

Đây là dạng rút gọn để giải thích contract của API. Trong runtime:

- **Input** là chuỗi compact JWT.
- **Output** là đối tượng **Jwt** chứa token value, headers, claims và các accessor của Spring Security.
- **Thất bại** được báo bằng **JwtException** hoặc subtype thích hợp.

**NimbusJwtDecoder** là implementation quen thuộc trong Servlet JWT Resource Server. Nó dùng Nimbus JOSE + JWT để xử lý cấu trúc JOSE, xác minh chữ ký bằng khóa đáng tin cậy và chạy các **OAuth2TokenValidator<Jwt>** được cấu hình.

| Thành phần | Trách nhiệm |
|---|---|
| **JwtDecoder** | Hợp đồng decode và validate JWT |
| **NimbusJwtDecoder** | Implementation dựa trên Nimbus JOSE/JWT, cấu hình nguồn khóa và thuật toán |
| **Jwt** | Biểu diễn token đã được decoder chấp nhận, gồm claims/headers |
| **JwtValidators** | Tạo tập validator tiêu chuẩn, trong đó có kiểm issuer và timestamps |
| **OAuth2TokenValidator<Jwt>** | Kiểm một điều kiện trên Jwt, có thể tổ hợp nhiều validator |
| **JwtAuthenticationProvider** | Dùng JwtDecoder để xác thực Bearer JWT |
| **JwtAuthenticationConverter** | Chuyển Jwt được chấp nhận thành Authentication và authorities |
| **SecurityFilterChain** | Cấu hình xác thực, xử lý yêu cầu và phân quyền HTTP |

**Cảnh báo về chữ “decoder”:** Trong Spring Security, JwtDecoder chuẩn không đơn thuần chuyển Base64URL thành JSON. Ngược lại, nếu tự tạo một implementation **JwtDecoder** chỉ parse JSON rồi trả về **Jwt**, lập trình viên đã phá vỡ trách nhiệm xác minh token của chính interface đó. Framework không tự kiểm lại chữ ký giúp một custom decoder thiếu an toàn.

### 4.1. Decode thành công chưa đồng nghĩa được đọc mọi tài nguyên

Giả sử decoder trả về Jwt có claim **scope = orders.read**. Converter mặc định thường ánh xạ scope thành authority **SCOPE_orders.read**. Endpoint có thể yêu cầu:

~~~java
.requestMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
~~~

Điều kiện này chỉ kiểm quyền ở mức loại thao tác. Service vẫn phải kiểm chủ sở hữu, tenant, quyền được giao và trạng thái của **đơn hàng số 42**. JWT signature và JwtDecoder không thể thay thế chính sách nghiệp vụ.

## 5. JwtDecoder nằm ở đâu trong quá trình xác thực Bearer token?

Với Servlet Resource Server, hành trình logic thường là:

~~~mermaid
flowchart TD
    A[Request chứa Authorization: Bearer] --> B[BearerTokenAuthenticationFilter]
    B --> C[AuthenticationManager và JwtAuthenticationProvider]
    C --> D[JwtDecoder.decode]
    D --> E[Parse header/payload chưa tin cậy]
    E --> F[Chọn khóa và thuật toán từ cấu hình tin cậy]
    F --> G{Chữ ký JWS hợp lệ?}
    G -->|Không| X[Authentication thất bại: 401]
    G -->|Có| H{Các validators đạt?}
    H -->|Không| X
    H -->|Có| I[JwtAuthenticationConverter]
    I --> J[JwtAuthenticationToken / GrantedAuthority]
    J --> K{Đủ quyền endpoint và dữ liệu?}
    K -->|Không| L[403 hoặc 404 theo chính sách]
    K -->|Có| M[Controller / Service xử lý]
~~~

Theo từng bước:

1. **BearerTokenAuthenticationFilter** nhận token từ HTTP request theo cơ chế Bearer.
2. **JwtAuthenticationProvider** được dùng trong cấu hình JWT Resource Server.
3. Provider gọi **JwtDecoder.decode()**.
4. Decoder kiểm cấu trúc, thuật toán, chữ ký và validators được cấu hình.
5. Sau khi decoder trả Jwt hợp lệ, **JwtAuthenticationConverter** ánh xạ claims thành principal và authorities.
6. Authorization ở web/method/service quyết định có được truy cập hay không.

Nếu decoder ném **JwtException**, yêu cầu bị xử lý như thất bại xác thực; với Bearer API thông thường sẽ là **401 Unauthorized**. Nếu xác thực thành công nhưng thiếu quyền thường là **403 Forbidden**.

Flowchart là mô tả logic, không phải thứ tự mọi phương thức nội bộ cho mọi phiên bản Spring Security. Ranh giới bảo mật cần giữ là **không chấp nhận claims để cấp quyền trước bước xác minh JWT**.

## 6. “Xác minh JWT” cần xác minh những gì?

### 6.1. Chữ ký và thuật toán được cho phép

Với token **RS256**:

- Authorization Server dùng **private key RSA** để ký.
- Resource Server dùng **public key RSA** từ nguồn tin cậy để verify.
- API không cần private key của issuer.

Với **ES256**, cách làm tương tự nhưng dùng EC key và ECDSA. Với **HS256**, cả bên ký và bên xác minh dùng chung khóa HMAC bí mật, nên phạm vi bảo vệ key khác với mô hình public key.

Spring Security documentation mô tả **NimbusJwtDecoder** mặc định chỉ tin **RS256** trong cấu hình JWT Resource Server thông thường, và có cách cấu hình thêm thuật toán khác khi issuer thực sự sử dụng chúng.

Không được vì header token ghi **alg = HS256** mà tự động đổi từ RSA verify sang HMAC. Không chấp nhận **alg = none** nếu hệ thống yêu cầu JWT ký số. Không cho token tự chọn bộ thuật toán mà Resource Server chấp nhận. Những lỗi này có thể dẫn tới **algorithm confusion**.

### 6.2. Khóa công khai và JWKS

Một JWT có thể mang **kid** trong JOSE header, ví dụ:

~~~json
{
  "alg": "RS256",
  "kid": "shop-sign-2026-11"
}
~~~

Resource Server dùng **kid** như một chỉ dẫn tra cứu khóa trong **JWKS của issuer đã cấu hình tin cậy**. Nó không được phép lấy JWKS từ bất kỳ URL nào do JWT chưa xác thực khai báo trong **jku** hoặc **x5u**.

Nếu ứng dụng tự tin **jku** do kẻ tấn công gửi, họ có thể ký JWT bằng private key của họ, công bố public key của họ rồi bảo API dùng chính public key đó để “xác minh”. Việc cho phép tải URL chưa tin cậy còn có thể gây SSRF.

Để bảo vệ chuỗi tin cậy:

- Pin issuer/JWKS URI qua cấu hình server hoặc danh sách issuer được phép.
- Kết nối metadata/JWKS bằng HTTPS, xác minh chứng chỉ.
- Chỉ chấp nhận khóa, loại khóa và thuật toán thích hợp.
- Hỗ trợ rotation với public key cũ/mới trong một khoảng chuyển tiếp.
- Không cho phép bypass signature verification khi JWKS lỗi hoặc chưa có **kid** tương ứng.

### 6.3. Issuer: token do đúng nơi phát hành?

Claim **iss** phải khớp issuer mà API tin cậy.

~~~text
Issuer cấu hình: https://login.example.com/realms/shop

JWT iss hợp lệ: https://login.example.com/realms/shop
JWT iss bị từ chối: https://login.example.com/realms/another
~~~

**Chữ ký hợp lệ với một khóa bất kỳ** chưa đủ. Cần xác định khóa thuộc issuer được API ủy thác. Trong hệ thống đa issuer/multi-tenant, mỗi nguồn tin cậy có thể có JWKS khác nhau; **kid** có thể trùng giữa các issuer, nên không tra cứu theo kid toàn cục mà bỏ qua issuer.

### 6.4. Audience: token có dành cho Resource Server này?

Một issuer có thể phát hành JWT cho nhiều API. Orders API cần từ chối token ký đúng nhưng:

~~~json
{
  "aud": ["payments-api"]
}
~~~

Nếu API yêu cầu **orders-api**, điều kiện audience phải xác nhận danh sách **aud** bao gồm giá trị đó.

Một sai lầm thường gặp là cấu hình mỗi **issuer-uri**, mặc định có validation issuer/timestamps, nhưng quên cấu hình **audiences** của API. Một JWT ký đúng do issuer phát hành vẫn có thể bị dùng lạc đối tượng nhận.

### 6.5. Thời gian: exp, nbf và iat

| Claim | Ý nghĩa | Ví dụ quy tắc |
|---|---|---|
| **exp** | Thời điểm token hết hạn | Không chấp nhận token sau exp, xét dung sai clock skew phù hợp |
| **nbf** | Token chưa hợp lệ trước thời điểm này | Không chấp nhận token quá sớm |
| **iat** | Thời điểm token được phát hành | Có thể dùng trong chính sách tuổi token, nhưng không thay thế exp/nbf |

Spring Security dùng các validator thời gian, chẳng hạn **JwtTimestampValidator**, và có cơ chế cấu hình dung sai lệch đồng hồ. Không tăng clock skew quá lớn chỉ để “sửa” lỗi hết hạn; cần đồng bộ clock giữa Authorization Server và Resource Server.

JWT ký đúng nhưng hết hạn vẫn phải bị từ chối. Nếu ứng dụng cần thu hồi quyền ngay trong lúc token chưa hết hạn, phải xem xét chính sách token lifetime, introspection, revocation hoặc kiểm quyền động phù hợp.

### 6.6. Token type và profile

Một OIDC **ID Token** cũng có thể là JWT được ký bằng khóa của OpenID Provider. Tuy nhiên, nó dùng cho **OIDC client** để xác minh sự kiện đăng nhập; Resource Server cần **access token** đúng mục đích.

Phải kiểm **audience** và những yêu cầu token type/profile mà API và issuer thống nhất. Trong hệ sinh thái dùng RFC 9068, JWT access token có các yêu cầu riêng, có thể dùng **typ = at+jwt**. Nếu cần bắt buộc profile này, phải cấu hình validator phù hợp; việc chỉ đọc typ trong payload/header chưa xác minh không đủ.

**sub**, **tenant_id**, role và permissions cũng phải có ý nghĩa được quy định rõ. Email, profile hoặc tên miền email không tự biến thành quyền nghiệp vụ.

## 7. Cấu hình JwtDecoder qua Spring Boot

Một API Spring MVC thường bắt đầu với Spring Boot starter dành cho **OAuth2 Resource Server**, để Boot quản lý các module Spring Security và JOSE.

| Thế hệ Spring Boot | Resource Server starter |
|---|---|
| **Spring Boot 3.x** | **spring-boot-starter-oauth2-resource-server** |
| **Spring Boot 4.x** | **spring-boot-starter-security-oauth2-resource-server** |

Với JWT, bên dưới cần Spring Security OAuth2 Resource Server và thành phần **spring-security-oauth2-jose**. Khi dùng starter được Boot quản lý, các dependency này được phối hợp phù hợp với release line; tránh pin riêng Security module khác thế hệ.

### 7.1. Issuer URI và audience

Trong **application.yml**:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com/realms/shop
          audiences:
            - orders-api
~~~

Khi không có bean JwtDecoder tự viết thay thế, Spring Boot/Spring Security có thể auto-configure decoder dùng metadata/JWKS của issuer được tin cậy, xác minh chữ ký, issuer và thời hạn. Property **audiences** trong các bản Boot hỗ trợ thiết lập audience cho API.

Giá trị ví dụ phải được thay bằng thông số phát hành token thật. **issuer-uri không có nghĩa tự động sinh scope hay quyền nghiệp vụ**, và phải xác nhận thuộc tính cấu hình tương ứng với Spring Boot release đang dùng.

### 7.2. Chỉ định JWK Set URI

Có thể đặt JWKS URI rõ ràng:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com/realms/shop
          jwk-set-uri: https://login.example.com/realms/shop/protocol/openid-connect/certs
          audiences:
            - orders-api
~~~

**jwk-set-uri** cho biết nơi tải public keys, còn **issuer-uri** vẫn cần để kiểm **iss**. Nếu chỉ có JWKS URI mà bỏ validator issuer, một cấu hình tự viết có thể không đủ chính sách để phân biệt đúng issuer.

Không đưa JWKS URI vào query parameter rồi cho client tự chọn. Nguồn khóa thuộc trust configuration của Resource Server.

### 7.3. SecurityFilterChain kiểm quyền sau decode

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public/**").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            );

        return http.build();
    }
}
~~~

Ví dụ dành cho **Spring Security Servlet**, không phải WebFlux. Nếu token đúng nhưng thiếu scope **orders.read**, endpoint bị chặn. Nếu có scope nhưng đơn thuộc tenant khác, service/domain policy vẫn cần từ chối.

Không tự tạo authorities từ JSON request body hay một token chưa qua JwtDecoder. Trong luồng mặc định, **JwtAuthenticationConverter** làm việc với Jwt đã được provider chấp nhận.

## 8. Tự tạo NimbusJwtDecoder và gắn validators

Có trường hợp phải tùy chỉnh decoder để chỉ định thuật toán, dùng JWKS URL cụ thể hoặc thêm điều kiện audience/token profile. Ví dụ sau sử dụng Spring Security API và chỉ chấp nhận **RS256**, issuer tin cậy, thời gian hợp lệ cùng audience **orders-api**.

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
class JwtDecoderConfig {

    private static final String ISSUER =
        "https://login.example.com/realms/shop";

    private static final String JWK_SET_URI =
        "https://login.example.com/realms/shop/protocol/openid-connect/certs";

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(JWK_SET_URI)
            .jwsAlgorithm(SignatureAlgorithm.RS256)
            .build();

        OAuth2TokenValidator<Jwt> issuerAndTime =
            JwtValidators.createDefaultWithIssuer(ISSUER);

        OAuth2TokenValidator<Jwt> audience = jwt ->
            jwt.getAudience().contains("orders-api")
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        "invalid_token",
                        "Token was not issued for orders-api",
                        null
                    )
                );

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(issuerAndTime, audience)
        );

        return decoder;
    }
}
~~~

Ý nghĩa:

1. **withJwkSetUri(...)** lấy public key từ endpoint được Resource Server cấu hình.
2. **jwsAlgorithm(RS256)** giới hạn thuật toán chữ ký chấp nhận.
3. **JwtValidators.createDefaultWithIssuer** áp dụng validation tiêu chuẩn, bao gồm thời gian và issuer.
4. Validator **audience** kiểm token được phát hành cho Orders API.
5. **DelegatingOAuth2TokenValidator** tổ hợp các điều kiện cần đồng thời đạt.
6. Decoder trả Jwt khi token đạt yêu cầu, hoặc báo lỗi nếu không đạt.

**Cảnh báo với custom bean:** Khi tự định nghĩa **@Bean JwtDecoder**, bean đó có thể thay thế decoder do Boot auto-configure. Đừng giả định các thuộc tính cấu hình JWT trong **application.yml** vẫn tự động thêm mọi validator vào custom decoder. Phải thiết lập issuer, audience, token type và những điều kiện cần thiết một cách tường minh.

### 8.1. Không thay validator mà quên các điều kiện mặc định

Ví dụ vấn đề:

~~~java
NimbusJwtDecoder decoder = NimbusJwtDecoder
    .withJwkSetUri(jwkSetUri)
    .build();

// SAI VỀ THIẾT KẾ NẾU BỎ TOÀN BỘ issuer/timestamp validators:
// decoder.setJwtValidator(onlyMyCustomValidator);
~~~

**setJwtValidator** đặt validator cho decoder. Nếu developer chỉ gắn một rule custom mà bỏ validator tiêu chuẩn, có thể vô tình không kiểm **iss**, **exp/nbf** theo kỳ vọng. Khi cần thêm rule, hãy tổ hợp nó với những validators mặc định/issuer cần thiết.

### 8.2. Custom decoder cũng có thể ảnh hưởng thời điểm tải metadata

Spring Security và Spring Boot có cơ chế khám phá issuer/JWKS, cache key và có thể hoãn một số thao tác mạng đến request đầu tiên tùy cấu hình. Khi thay decoder, hành vi startup, timeout và cache có thể khác. Trong production cần kiểm cấu hình kết nối HTTPS, JWKS key rotation, metadata caching và cách hệ thống xử lý khi Authorization Server tạm thời không truy cập được. Không giải quyết mất kết nối JWKS bằng cách chấp nhận token chưa xác minh.

## 9. Phân biệt phương thức “decode” ở các thư viện JWT

Tên method không đủ để hiểu mức bảo mật của kết quả:

| Thao tác | Có kiểm chữ ký? | Có kiểm claims theo chính sách API? |
|---|---|---|
| Tách chuỗi bằng dấu chấm | Không | Không |
| Base64URL decode header/payload | Không | Không |
| JSON parser chuyển payload thành Map/DTO | Không | Không |
| JWT parser chỉ dựng đối tượng cú pháp | Không, nếu thư viện chưa chạy verifier | Không |
| JWS verifier với key tin cậy | Có thể kiểm chữ ký | Thường cần validator claim riêng |
| **NimbusJwtDecoder.decode** được cấu hình đúng | Có, với JWT/JWS được hỗ trợ | Có, theo bộ validators đã cấu hình |
| **JwtAuthenticationConverter** | Không tự kiểm chữ ký | Ánh xạ authorities, không thay JwtDecoder |

Một số thư viện bên ngoài dùng tên **parseSignedClaims**, **verify**, **decode** hoặc **claims** khác nhau. Khi đánh giá code, hãy hỏi:

- Đâu là lời gọi kiểm **JWS signature/MAC** thực sự?
- Key/algorithm đến từ nguồn nào và được tin cậy theo chính sách nào?
- Validator **iss/aud/exp/nbf** được chạy ở đâu?
- Đối tượng claims trả ra đã qua những bước nào?
- Nếu lỗi thì method ném exception, trả trạng thái không hợp lệ hay vẫn trả JSON?

Không tự tạo **Jwt** hay **JwtAuthenticationToken** từ dữ liệu chưa xác minh rồi coi đã an toàn. Mọi ranh giới authentication phải giữ đúng contract xác thực token.

## 10. Ví dụ tấn công bằng chỉnh sửa payload

Giả sử token hợp lệ ban đầu có:

~~~json
{
  "sub": "user-123",
  "scope": "orders.read",
  "aud": ["orders-api"]
}
~~~

Kẻ tấn công lấy payload, thay bằng:

~~~json
{
  "sub": "user-123",
  "scope": "orders.read orders.write",
  "aud": ["orders-api"]
}
~~~

rồi Base64URL encode lại và gửi token với signature cũ.

Kết quả cần có:

| Bước | Kết quả |
|---|---|
| Tách ba phần token | Có thể thành công |
| Đọc JSON | Có thể thành công; thấy thêm **orders.write** |
| Dùng chữ ký cũ kiểm trên signing input mới | **Thất bại** |
| NimbusJwtDecoder | Báo token không hợp lệ |
| Spring Security authentication | Không tạo authenticated principal cho token bị sửa |
| Gọi endpoint cần quyền ghi | **Từ chối**, thường 401 vì token giả |

Nếu API chỉ parse claim **scope** mà không verify, request có thể được cấp quyền ghi dù kẻ tấn công không hề có private key. Vì vậy, **parse được JSON là điều kiện cực kỳ yếu**, không có ý nghĩa xác thực.

Không tự hiện thực thuật toán verify chữ ký theo cách thủ công cho ứng dụng production. Hãy sử dụng framework/thư viện JOSE đáng tin cậy và cấu hình đúng nguồn khóa, issuer, audience.

## 11. Hiểu đúng phản hồi 401 và 403

| Trường hợp | Xác minh / phân quyền | HTTP thường gặp |
|---|---|---|
| Không gửi Bearer token | Không có xác thực | **401** |
| Token sai cấu trúc JWT | Parse thất bại | **401** |
| Payload hợp lệ nhưng signature không đúng | Cryptographic verification thất bại | **401** |
| Signature đúng, issuer không được tin | Issuer validation thất bại | **401** |
| Signature đúng, audience là API khác | Audience validation thất bại | **401** |
| Token hết hạn hoặc chưa đến nbf | Time validation thất bại | **401** |
| JWT được xác thực nhưng không có **orders.read** | Authorization không đạt | **403** |
| JWT có scope nhưng không được xem đơn hàng cụ thể | Resource policy không đạt | **403**, hoặc **404** theo chính sách che giấu |
| JWT hợp lệ, đủ scope và quyền theo bản ghi | Điều kiện đạt | Endpoint tiếp tục thực hiện, có thể trả **200** |

Với Bearer API, phản hồi 401 thường mang header **WWW-Authenticate: Bearer**. Mã thực tế có thể thay đổi theo cấu hình exception handling. Cần phân biệt token sai để sửa cấu hình xác thực, với token thiếu quyền để sửa chính sách/role mapping đúng cách.

Không sửa 401 bằng cách bỏ signature/audience validator, và không sửa 403 bằng **permitAll()** cho endpoint nhạy cảm.

## 12. Kiểm thử JwtDecoder thật và mock JWT là hai mục tiêu khác nhau

Spring Security Test có request post-processor **jwt()** để đưa một principal/JWT mô phỏng vào SecurityContext trong kiểm thử Servlet. Đây là cách phù hợp để kiểm authorization, nhưng **không nhất thiết chạy JwtDecoder thật**.

Ví dụ minh họa:

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@Test
void allowsReadScopeInWebRule() throws Exception {
    mockMvc.perform(get("/api/orders/42")
            .with(jwt().authorities(() -> "SCOPE_orders.read")))
        .andExpect(status().isOk());
}
~~~

Đoạn test rút gọn giả sử đã có **mockMvc**, controller, fixture đơn hàng và policy phù hợp để trả 200. Nếu chưa có dữ liệu, test thực tế có thể trả 404 dù người dùng đủ quyền. Ý nghĩa chính: **mock jwt() kiểm Security rule, không chứng minh rằng token giả sẽ bị JwtDecoder từ chối**.

Các lớp kiểm thử nên được phân biệt:

1. **Web/method authorization test**: mock JwtAuthenticationToken để thử yêu cầu scope/role/tenant và kết quả 403.
2. **Decoder test**: dùng **JWT thực sự được ký bằng key test**, hoặc token đã bị chỉnh sửa, sai audience/issuer, hết hạn để kiểm **JwtDecoder.decode**.
3. **HTTP integration test**: gửi Bearer token test qua filter chain cùng issuer/JWKS giả lập đáng tin cậy để kiểm 401/403 và authority mapping.
4. **Vận hành**: kiểm JWKS qua HTTPS, chứng chỉ, key rotation, cache và timeout trong môi trường thực tế.

Ví dụ mang tính định hướng cho decoder test:

~~~java
// validSignedToken: JWT đã ký bằng private key của test issuer.
// tamperedToken: token bị sửa payload nhưng không ký lại.

Jwt jwt = jwtDecoder.decode(validSignedToken);

assertThrows(
    JwtException.class,
    () -> jwtDecoder.decode(tamperedToken)
);
~~~

Đây là **pseudocode trích từ bối cảnh test**; các biến test cần được tạo trong fixture và chạy với JwtDecoder có cấu hình key/issuer/audience kiểm thử. Không commit access token thật vào source hay log.

Nếu chỉ sử dụng mock **jwt()**, cả bộ test vẫn có thể xanh dù custom JwtDecoder ở production bỏ signature verification. Đây là lý do cần xác minh ranh giới decoder thực sự bằng test phù hợp khi triển khai.

## 13. Những nhầm lẫn phổ biến cần tránh

### 13.1. JWT chữ ký hợp lệ nhưng bị dùng sai API

Issuer có thể phát token cho nhiều resource. Orders API phải từ chối token **aud = analytics-api**, dù cùng issuer và chữ ký đúng. Kiểm **aud** là cách chống token substitution.

### 13.2. Tin dữ liệu từ JWT trước khi xác minh

Payload JSON, **iss**, **kid**, **jku**, scope và tenant_id có thể bị kẻ tấn công tùy chỉnh trước khi chữ ký được kiểm. Không dùng chúng để cấp quyền, tải URL bất kỳ hay truy vấn key store không kiểm soát.

### 13.3. Nhầm ID Token với Access Token

OIDC ID Token chứa thông tin đăng nhập cho client, trong khi Resource Server cần access token đúng audience/token profile. Hai loại có thể cùng là JWT và cùng được issuer ký, nhưng không được hoán đổi tùy tiện.

### 13.4. Bỏ qua thời hạn vì token ký đúng

Nếu **exp** đã qua hoặc **nbf** chưa tới, token không được dùng. Chữ ký chỉ chứng minh nội dung còn nguyên vẹn theo key được tin cậy, không làm token có hiệu lực vô thời hạn.

### 13.5. Tự viết JwtDecoder chỉ parse JSON

Custom decoder phải thực hiện xác minh JWT và claims theo contract. Trả về **new Jwt(...)** từ Map do client gửi không đạt yêu cầu bảo mật, kể cả lớp Java được tạo ra có tên giống Jwt do Nimbus trả về.

### 13.6. Coi **SCOPE_*** là quyền tự động cho mọi dữ liệu

Spring Security ánh xạ scope thành authorities để tiện phân quyền. Nó không tự hiểu tenant, chủ sở hữu bản ghi hoặc chính sách nghiệp vụ. Những điều kiện này phải được kiểm tại Resource Server.

### 13.7. Ghi nguyên token để debug lỗi xác thực

Bearer token là credential có thể bị tái sử dụng. Không đưa token vào URL, access log, trace, exception report, ticket lỗi hoặc file README. Ghi request ID, mã lỗi tổng quát và thông tin vận hành đã giảm thiểu nhạy cảm.

### 13.8. Cho phép mọi thuật toán hoặc JWKS tùy ý

Một JWKS có public key không tự đáng tin. Nguồn khóa phải thuộc cấu hình server/issuer tin cậy và thuật toán phải được cho phép. Nguyên tắc được nhấn mạnh trong **RFC 8725 — JWT Best Current Practices**.

## 14. Quy trình triển khai an toàn cho một Resource Server

Ví dụ ràng buộc dự án:

~~~text
Issuer:          https://login.example.com/realms/shop
Audience:        orders-api
Allowed alg:     RS256
API scope:       orders.read
Business rule:   Chỉ đọc đơn được phép trong tenant của người dùng
~~~

Quy trình:

1. Client gửi **Authorization: Bearer** qua HTTPS.
2. Resource Server chọn **JwtDecoder** được cấu hình để kiểm JWT access token.
3. Decoder parse token nhưng chưa tin claims, chọn thuật toán/khóa từ issuer/JWKS đáng tin cậy.
4. Decoder kiểm **JWS signature**; token bị sửa hoặc giả mạo bị từ chối.
5. Decoder chạy validators: **iss**, **aud**, **exp**, **nbf**, token type/profile và ràng buộc khác đã quy định.
6. Spring Security ánh xạ Jwt hợp lệ sang **JwtAuthenticationToken** và authorities.
7. Web/method authorization kiểm **SCOPE_orders.read**.
8. Domain policy kiểm tenant, ownership, membership và trạng thái đơn hàng trước khi trả dữ liệu.

Khi thiết kế hoặc review, những câu hỏi quan trọng là: nguồn khóa từ đâu, thuật toán nào được phép, ai gắn issuer/audience validators, decoder custom có đầy đủ không, những test nào chạy decoder thật, quyền trên từng tài nguyên được kiểm ở đâu và token có bị ghi vào log không.

## Kết luận

**Phân tích cú pháp** JWT chỉ đọc điều mà token đang tuyên bố. **Xác minh chữ ký** kiểm xem header/payload có được bảo vệ bằng khóa và thuật toán tin cậy. **Validation** kiểm token đúng issuer, audience, thời hạn và mục đích sử dụng. **Authorization** quyết định chủ thể có được thực hiện hành động trên tài nguyên cụ thể không.

Với Spring Security OAuth2 JWT Resource Server, **JwtDecoder** là ranh giới cốt lõi để xác thực token: **NimbusJwtDecoder** được cấu hình đúng thực hiện nhiều hơn Base64URL decode, và chỉ trả **Jwt** khi token vượt qua các kiểm tra của decoder. Đừng cấp quyền từ JSON chưa xác minh, đừng bỏ audience/issuer validators khi tạo custom decoder và đừng xem chữ ký hợp lệ là quyền truy cập toàn bộ dữ liệu.

### Tài liệu tham khảo

- [Spring Security Reference — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security API — JwtDecoder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/JwtDecoder.html)
- [Spring Security API — NimbusJwtDecoder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/NimbusJwtDecoder.html)
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 7515 — JSON Web Signature](https://www.rfc-editor.org/rfc/rfc7515)
- [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
