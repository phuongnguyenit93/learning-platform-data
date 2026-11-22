# Đọc nội dung token để chẩn đoán không đồng nghĩa đã xác minh token

Khi phát triển **Spring Security OAuth 2.0 OIDC Resource Server**, lập trình viên thường cần mở một JWT access token để xem `iss`, `aud`, `scope`, `exp` hoặc `kid` nhằm chẩn đoán lỗi. Thao tác đó hữu ích nhưng có một ranh giới bảo mật bắt buộc phải nhớ:

> **Đọc được header và payload của JWT chỉ chứng minh rằng các phần này có thể được giải mã thành dữ liệu. Nó không chứng minh token do Authorization Server tin cậy phát hành, không bị sửa đổi, còn hiệu lực hoặc được phép dùng tại API hiện tại.**

Trong một JWT dạng JWS thông dụng, phần header và payload được **Base64URL encode**, không phải mã hóa bí mật. Bất kỳ ai có chuỗi token đều có thể đọc các claim mà không cần private key hay public key. Việc **xác minh chữ ký (signature verification)** và **kiểm tra chính sách claim (claim validation)** là những bước riêng, phải do thành phần đáng tin cậy của Resource Server thực hiện.

Bài học tập trung vào cách phân biệt ba hành động **decode → verify → authorize**, những điều có thể hoặc không thể kết luận từ JWT chưa xác minh, và cách làm đúng trong Spring Security.

## 1. Một tình huống debug rất dễ gây hiểu nhầm

Giả sử client gọi API quản lý đơn hàng:

~~~http
GET /api/orders HTTP/1.1
Host: api.example.com
Authorization: Bearer eyJhbGciOiJSUzI1NiIsImtpZCI6ImtleS0xIn0...
~~~

Developer sao chép JWT vào công cụ giải mã và thấy nội dung giả định:

~~~json
{
  "iss": "https://idp.example.com/realms/shop",
  "sub": "alice",
  "aud": ["orders-api"],
  "scope": "orders.read orders.write",
  "exp": 2000000000
}
~~~

Những dữ liệu này **có thể giúp đặt giả thuyết**: token trông như dành cho `orders-api`, có scope đọc/ghi đơn hàng và có thời điểm hết hạn trong tương lai. Nhưng chưa thể kết luận rằng API phải trả `200 OK`.

Một kẻ tấn công hoàn toàn có thể tự tạo payload giống hệt như trên rồi Base64URL encode. Nếu không ký được bằng khóa đúng của issuer, token đó phải bị Resource Server từ chối. Ngay cả token có chữ ký hợp lệ cũng có thể bị từ chối vì **sai issuer, sai audience, quá hạn, chưa đến thời điểm hiệu lực hoặc không đáp ứng chính sách ứng dụng**.

| Hành động | Biết được điều gì? | Chưa chứng minh được điều gì? |
|---|---|---|
| **Decode** header/payload | Token *tự khai báo* thuật toán, chủ thể, quyền, thời gian | Nguồn phát hành, tính toàn vẹn, hiệu lực và quyền thật |
| **Verify** chữ ký/MAC | Dữ liệu được bảo vệ bằng khóa hợp lệ theo thuật toán và cấu hình tin cậy | Token còn hạn, dành cho API này hoặc đủ quyền |
| **Validate** claim | Token phù hợp các điều kiện như `iss`, `aud`, `exp`, `nbf`, loại token | Người dùng có quyền trên bản ghi/tài nguyên cụ thể |
| **Authorize** request | Một thao tác được phép theo principal, authorities và chính sách | Không có nghĩa các thao tác khác cũng được cho phép |

Trong tài liệu Spring Security, từ “decode” trong tên **`JwtDecoder`** có phạm vi rộng hơn “giải mã Base64URL”: implementation của `JwtDecoder` có trách nhiệm xử lý JWT theo cấu hình xác minh/validation. Không được đồng nhất nó với `Base64.getUrlDecoder()`.

## 2. JWT nằm trong họ tiêu chuẩn JOSE

**JOSE (JSON Object Signing and Encryption)** là họ tiêu chuẩn mô tả cách bảo vệ dữ liệu JSON bằng chữ ký, MAC hoặc mã hóa. Khi làm việc với JWT, cần phân biệt một số khái niệm:

- **JWT (JSON Web Token, RFC 7519):** cấu trúc token chứa các claim.
- **JWS (JSON Web Signature, RFC 7515):** bảo vệ tính toàn vẹn/nguồn ký bằng chữ ký số hoặc MAC.
- **JWE (JSON Web Encryption, RFC 7516):** bảo vệ bí mật nội dung bằng mã hóa.
- **JWK (JSON Web Key, RFC 7517):** biểu diễn khóa mật mã dưới dạng JSON.
- **JWA (JSON Web Algorithms, RFC 7518):** định nghĩa các định danh thuật toán dùng trong JOSE.

Access token JWT của Resource Server thường là một **signed JWT được biểu diễn dưới dạng JWS Compact Serialization**:

~~~text
<base64url(protected-header)>.<base64url(payload)>.<base64url(signature)>
~~~

Ba phần phân cách bằng dấu chấm:

~~~text
eyJhbGciOiJSUzI1NiIsImtpZCI6ImtleS0xIn0
.
eyJpc3MiOiJodHRwczovL2lkcC5leGFtcGxlLmNvbSJ9
.
<signature-segment>
~~~

Đây chỉ là minh họa cấu trúc; các đoạn rút gọn không phải một JWT dùng để xác thực.

### Header của JWS nói gì?

Ví dụ header sau khi Base64URL decode:

~~~json
{
  "alg": "RS256",
  "kid": "key-2026-01",
  "typ": "at+jwt"
}
~~~

- `alg` **tự khai báo** thuật toán bảo vệ JWS, chẳng hạn `RS256`.
- `kid` **tự khai báo** gợi ý định danh khóa cần dùng để kiểm tra chữ ký.
- `typ` **tự khai báo** loại đối tượng; `at+jwt` là dấu hiệu profile JWT access token theo RFC 9068, khi issuer sử dụng profile này.

Header là **đầu vào chưa đáng tin trước khi xác minh**, kể cả khi nó trông đúng với hệ thống. Resource Server không nên nhìn `alg=RS256` rồi mặc nhiên tin rằng token đã được ký RS256; cũng không nên nhìn `kid` rồi gọi bất kỳ địa chỉ khóa nào do token gợi ý.

### Payload của JWT nói gì?

Ví dụ payload:

~~~json
{
  "iss": "https://idp.example.com/realms/shop",
  "sub": "alice",
  "aud": ["orders-api"],
  "iat": 1980000000,
  "nbf": 1980000000,
  "exp": 2000000000,
  "scope": "orders.read",
  "client_id": "shop-web"
}
~~~

Đây là các **claim** do token tự mang theo. Trước xác minh, mọi claim đều chỉ là **dữ liệu được đọc từ nguồn không tin cậy**. Chẳng hạn `sub=alice` chưa đủ để xác nhận request thuộc Alice, và `scope=orders.read` chưa tạo quyền đọc đơn hàng.

### Signature không giống payload

Với JWS dùng `RS256`, Authorization Server thường ký bằng private key; Resource Server xác minh bằng public key tin cậy. Chữ ký phụ thuộc vào **chính xác nội dung được ký**, bao gồm phần header và payload đã được mã hóa theo dạng JWS.

~~~text
Base64URL(header) + "." + Base64URL(payload)
                   |
              thuật toán ký
                   |
               signature
~~~

Nếu sửa payload từ `orders.read` thành `orders.write` mà không có khả năng ký hợp lệ, dữ liệu vẫn có thể Base64URL decode bình thường, nhưng **xác minh chữ ký phải thất bại**.

**Chữ ký không phải mã hóa bí mật:** người có JWT dạng JWS có thể đọc payload mà không cần khóa. Vì vậy không đưa mật khẩu, session secret hoặc dữ liệu nhạy cảm không cần thiết vào JWT.

## 3. Decode Base64URL thực sự làm gì?

Base64URL là cách biến dữ liệu nhị phân thành ký tự phù hợp với URL/token. Nó có thể đảo ngược mà không cần biết khóa bí mật.

Ví dụ đơn giản:

~~~text
eyJzdWIiOiJhbGljZSJ9
          |
    Base64URL decode
          v
{"sub":"alice"}
~~~

Mọi chương trình có hàm Base64URL decoder đều làm được. Điều kiện “đọc được JSON hợp lệ” chỉ chứng minh định dạng dữ liệu có vẻ hợp lý.

### Đoạn Java chỉ dùng cho mục đích chẩn đoán

Ví dụ dưới đây đọc header và payload **của một JWS compact ba phần**. Nó **không thực hiện xác minh chữ ký, không xác minh issuer, audience, hết hạn hoặc scope**:

~~~java
package com.example.security.debug;

import java.nio.charset.StandardCharsets;
import java.util.Base64;

public final class JwtInspectOnly {

    private JwtInspectOnly() {
    }

    public static void inspectUntrusted(String compactJws) {
        String[] parts = compactJws.split("\\.", -1);

        if (parts.length != 3) {
            throw new IllegalArgumentException(
                "Expected a three-part compact JWS");
        }

        System.out.println("UNTRUSTED header: " + base64UrlDecode(parts[0]));
        System.out.println("UNTRUSTED payload: " + base64UrlDecode(parts[1]));
    }

    private static String base64UrlDecode(String segment) {
        byte[] bytes = Base64.getUrlDecoder().decode(segment);
        return new String(bytes, StandardCharsets.UTF_8);
    }
}
~~~

Code này thích hợp để **khám phá cấu trúc token giả lập trong môi trường phát triển có kiểm soát**. Nó chưa kiểm tra JSON schema, không giới hạn kích thước input và không xác minh bất cứ thuộc tính bảo mật nào của token. Vì vậy không dùng nó làm bộ xử lý xác thực, middleware phân quyền hoặc endpoint “debug JWT” công khai.

Trong hệ thống thật, tránh `System.out.println` với token hoặc claim nhạy cảm vì stdout có thể được thu thập vào log tập trung. Khi cần điều tra, chỉ trích xuất đúng những trường ít nhạy cảm được phép ghi nhận và đặt nhãn rõ ràng là **unverified**.

### Một phép thử tư duy: payload giả vẫn đọc được

Cho hai payload:

~~~json
{
  "sub": "alice",
  "scope": "orders.read"
}
~~~

và:

~~~json
{
  "sub": "admin",
  "scope": "orders.write"
}
~~~

Cả hai đều có thể chuyển sang Base64URL hợp lệ. Một chương trình chỉ decode sẽ hiển thị cả hai. Nó không thể biết payload nào được issuer ký, payload nào đã bị sửa và payload nào chỉ là chuỗi do người gửi tự chế.

Chính **quá trình xác minh mật mã cùng chính sách kiểm tra claim** mới tạo ra khác biệt giữa dữ liệu “token tự nói” và dữ liệu mà Resource Server có thể tin trong hệ thống.

## 4. Vì sao JWT decoder trên website hoặc trình duyệt có thể gây hiểu nhầm?

Một công cụ hiển thị JWT thường thực hiện được ba việc với độ tin cậy khác nhau:

1. **Tách ba đoạn** bằng dấu chấm.
2. **Giải mã Base64URL** header/payload.
3. **Có thể** xác minh signature nếu được cấu hình khóa và thuật toán phù hợp; nhiều công cụ chỉ decode mặc định.

UI hiển thị nội dung dễ đọc hoặc thông báo “JWT decoded” không phải bằng chứng token đã xác minh. Thậm chí một công cụ báo “signature verified” cũng chưa đảm bảo token đúng `iss`, `aud`, `exp` hoặc đúng loại token mà **Resource Server này** chấp nhận.

Khi chẩn đoán:

- Ưu tiên công cụ chạy **cục bộ/offline** với token thử nghiệm, không nhập access token đang có hiệu lực vào website không được phép sử dụng.
- Không dán token vào ticket, chat, screenshot, issue tracker hoặc log.
- Kiểm tra xem công cụ có **thật sự dùng khóa công khai đáng tin** hay chỉ đang hiển thị chuỗi JSON.
- Coi mọi dữ liệu chưa xác minh là **untrusted claims**, kể cả trường có tên quen thuộc như `role`, `scope`, `email`.
- Nếu token là opaque string hoặc JWE, thao tác tách ba đoạn rồi Base64URL decode payload có thể không áp dụng.

**Một công cụ debug không phải là trust anchor.** Trust anchor là nguồn khóa, issuer và chính sách xác minh được Resource Server cấu hình từ hệ thống tin cậy.

## 5. Xác minh chữ ký: bước nào biến dữ liệu thành đáng tin?

Xét JWT do Authorization Server phát hành. Với thuật toán ký bất đối xứng thông dụng:

~~~text
Authorization Server                         Resource Server
      |                                             |
      | Private key: ký JWT                         |
      |                                             |
      +------------- JWT -------------------------->|
                                                    |
                                        Lấy public key tin cậy
                                        từ cấu hình / JWKS của AS
                                                    |
                                        Xác minh chữ ký của JWT
                                                    |
                                             true / false
~~~

Sau khi chọn được thuật toán được phép và khóa phù hợp, Resource Server thực hiện phép kiểm tra mật mã. **Chỉ khi phép kiểm tra thành công**, header/payload mới có cơ sở tin rằng nội dung chưa bị thay đổi so với lúc được ký bởi một bên có khóa phù hợp.

Tuy nhiên, kiểm tra chữ ký vẫn chưa đủ. Cần biết **khóa thuộc issuer nào** và **token có được dùng cho API hiện tại không**.

### JWK Set và `kid`

Authorization Server có thể công bố các public key tại **JWKS endpoint**. Ví dụ JWK Set minh họa:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "key-2026-01",
      "use": "sig",
      "alg": "RS256",
      "n": "<base64url-rsa-modulus>",
      "e": "AQAB"
    }
  ]
}
~~~

Resource Server dùng `kid` từ header như một **gợi ý để chọn khóa** trong **bộ khóa đã được cấu hình tin cậy**. Riêng `kid` không chứng minh quyền phát hành. Nếu client gửi token có `kid=some-random-key`, server không được tự động tin hoặc tự tạo khóa mới từ giá trị đó.

Các header như `jku` hoặc `x5u` có thể đề xuất URL chứa khóa/chứng chỉ trong một số định dạng JOSE. Trong API Resource Server, **không tự động fetch các URL tùy ý do token chỉ định**. Làm vậy có thể dẫn tới tin nhầm khóa của attacker hoặc tấn công SSRF. Phải áp dụng chính sách về issuer, nguồn khóa và thuật toán từ cấu hình tin cậy.

### Kiểm tra thuật toán

Dù header ghi `"alg": "RS256"`, ứng dụng vẫn cần chính sách chỉ chấp nhận những thuật toán đã thỏa thuận với issuer.

Các lỗi thiết kế từng xuất hiện trong hệ sinh thái JWT gồm:

- Vô tình chấp nhận JWT **không có chữ ký**, chẳng hạn header `alg=none`, trong nơi bắt buộc signed access token.
- **Algorithm confusion**: coi khóa công khai RSA như shared secret của HMAC khi token tự đổi `alg` từ `RS256` sang `HS256`.
- Cho token tự quyết định thuật toán và nguồn khóa ngoài chính sách tin cậy.
- Dùng khóa yếu hoặc sai mục đích.

[RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725) yêu cầu ứng dụng xác định tập thuật toán được phép và kiểm tra thuật toán thực hiện đúng với khai báo cũng như mục đích của khóa. Trong Resource Server cần signed JWT, phải từ chối trường hợp không đáp ứng hợp đồng ký, kể cả token đọc được payload hợp lệ.

**Không tự viết lại thuật toán JWS hoặc tin header `alg` để chọn cơ chế xử lý nguy hiểm.** Dùng implementation JOSE được bảo trì và cấu hình whitelist thuật toán, khóa và issuer theo chuẩn.

## 6. Claim validation: chữ ký đúng vẫn có thể bị từ chối

Giả sử đã xác minh đúng chữ ký. Resource Server tiếp tục đánh giá các claim theo **hợp đồng access token**.

| Claim | Câu hỏi xác minh | Nguy cơ nếu bỏ qua |
|---|---|---|
| `iss` — issuer | Token có đến từ Authorization Server mà API tin cậy không? | Chấp nhận token từ miền/tenant/AS khác |
| `aud` — audience | Token có dành cho API này không? | Dùng token của API A để gọi API B |
| `exp` — expiration | Token đã hết hạn chưa? | Chấp nhận token ngoài vòng đời cho phép |
| `nbf` — not before | Token đã bắt đầu có hiệu lực chưa? | Chấp nhận token sớm hơn thời điểm được phép |
| `iat` — issued at | Có đáp ứng chính sách thời gian phát hành nếu ứng dụng yêu cầu không? | Khó áp dụng chính sách token age hoặc bất thường thời gian |
| `typ` / loại token | Đây có phải access token mà API chấp nhận, không phải token loại khác? | Nhầm ID token, refresh token hoặc JWT dùng mục đích khác |
| `scope` / `scp` | Những quyền nào thực sự được issuer cấp? | Ánh xạ quyền sai hoặc cấp quyền vượt mức |
| `sub` / `client_id` | Principal/client nào được issuer mô tả? | Nhầm người dùng và client; sai mô hình quyền |
| Claim tùy biến | Tenant, tổ chức, cơ chế xác thực có phù hợp policy không? | Vượt ranh giới tenant hoặc sai điều kiện nghiệp vụ |

Các claim không nhất thiết đều phải xuất hiện trong mọi định dạng access token. **Những claim cần thiết và cách validate phụ thuộc profile, issuer và contract của API**. Ví dụ, với JWT access token theo RFC 9068, `typ` mang giá trị phù hợp giúp tránh nhầm mục đích token, nhưng chỉ đọc `typ` là chưa đủ; phải xác minh token và áp dụng chính sách loại token.

### Chữ ký đúng nhưng sai audience

Một Authorization Server có thể phát hành hai token cùng ký bằng một bộ khóa:

~~~json
{
  "iss": "https://idp.example.com/realms/shop",
  "aud": ["inventory-api"],
  "scope": "inventory.read"
}
~~~

và:

~~~json
{
  "iss": "https://idp.example.com/realms/shop",
  "aud": ["orders-api"],
  "scope": "orders.read"
}
~~~

Cả hai có thể có chữ ký hợp lệ. Tuy nhiên `orders-api` phải từ chối token chỉ dành cho `inventory-api`. Việc chỉ nhìn chữ ký hợp lệ mà bỏ qua `aud` có thể mở đường cho **token substitution / cross-service token confusion**.

### `exp` không tự được kiểm tra bằng cách đọc JSON

Một công cụ decode có thể hiển thị:

~~~json
{
  "exp": 1700000000
}
~~~

Đọc được con số này không có nghĩa đã so sánh với thời gian hiện tại, kiểm soát lệch đồng hồ hay xác định token còn hiệu lực. Thời điểm `exp` được biểu diễn dưới dạng NumericDate theo chuẩn JWT, thường là số giây tính từ Unix epoch. Công cụ debug có thể đổi nó sang thời gian để người vận hành đọc; **quyết định chấp nhận phải nằm ở validator đáng tin**, không nằm ở UI debug.

### ID token không trở thành access token vì đều là JWT

Trong OIDC, **ID token** phục vụ OIDC Client (relying party). **Access token** phục vụ Resource Server. Một ID token có `sub`, `iss`, `aud` và chữ ký hợp lệ vẫn không thể tùy tiện dùng để gọi API nếu audience/mục đích của nó không dành cho API đó.

Cần thiết lập chính sách tách loại token; với JWT Access Token Profile, có thể kiểm tra profile và type thích hợp. Nhãn `typ` chỉ là một trong nhiều tín hiệu cần kiểm tra, không thay được chữ ký và audience.

## 7. Ngữ nghĩa “decode” trong Spring Security khác decode Base64URL

Spring Security cung cấp `org.springframework.security.oauth2.jwt.JwtDecoder`. Interface có phương thức:

~~~java
Jwt decode(String token) throws JwtException;
~~~

Tên phương thức là `decode`, nhưng contract của decoder dành cho JWT Resource Server là xử lý JWT theo **cấu hình xác minh và validation**. Ví dụ `NimbusJwtDecoder` sử dụng cơ chế JOSE để kiểm tra chữ ký và các validator được cấu hình để đánh giá claim.

Trong hệ thống dùng Spring Boot, cấu hình đúng sẽ dẫn tới luồng khái quát:

~~~text
HTTP request
    |
    v
Authorization: Bearer <compact-JWT>
    |
    v
BearerTokenAuthenticationFilter
    |
    v
JwtAuthenticationProvider
    |
    v
JwtDecoder (thường NimbusJwtDecoder)
    |
    +-- kiểm tra cấu trúc/token
    +-- chọn thuật toán/khóa phù hợp từ nguồn tin cậy
    +-- xác minh chữ ký
    +-- áp dụng Jwt validators (issuer, thời gian, audience...)
    |
    v
JwtAuthenticationToken được xác thực
    |
    v
SecurityContext
    |
    v
Authorization rules / method security
    |
    v
Controller / service
~~~

Nếu xác minh thất bại, request thông thường không tạo được principal JWT đã xác thực và bị xử lý theo nhánh lỗi authentication.

### Cấu hình một JWT Resource Server đúng hướng

Với ứng dụng Spring Boot sử dụng Servlet/Spring MVC, khai báo starter phù hợp:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

`application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.com/realms/shop
          audiences:
            - orders-api
~~~

- `issuer-uri` xác định issuer tin cậy và hỗ trợ khám phá metadata/JWKS theo cơ chế của Spring Security/Authorization Server.
- `audiences` yêu cầu JWT dành cho Resource Server này. Thuộc tính này được hỗ trợ trong các phiên bản Spring Boot hiện đại; nếu ứng dụng dùng phiên bản không hỗ trợ, cần cấu hình audience validator riêng.
- Không chấp nhận issuer/JWKS URI do request hoặc header JWT tự đề xuất.
- Nếu AS không hỗ trợ khám phá metadata hoặc cần cấu hình rõ JWKS, có thể dùng `jwk-set-uri` đáng tin cậy kèm issuer và các validator cần thiết.

Ví dụ filter chain:

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()));

        return http.build();
    }
}
~~~

Trong cấu hình này, **authentication diễn ra trước authorization**: API không đọc `scope` từ token chưa xác minh rồi tự quyết định quyền truy cập. Với các claim scope chuẩn mà Spring hỗ trợ, `scope=orders.read` thường trở thành authority `SCOPE_orders.read` sau khi JWT được xác thực.

Đối với ứng dụng có session/cookie hoặc CSRF considerations, điều chỉnh các chính sách HTTP phù hợp với kiến trúc riêng; đoạn ví dụ này chỉ tập trung vào đường xử lý JWT.

### Đọc claim từ principal đã xác thực

Controller có thể nhận `Jwt` đã qua quá trình xác thực của Resource Server:

~~~java
package com.example.orders.api;

import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class IdentityController {

    @GetMapping("/api/me")
    public Map<String, Object> me(@AuthenticationPrincipal Jwt jwt) {
        return Map.of(
            "subject", jwt.getSubject(),
            "issuer", jwt.getIssuer().toString()
        );
    }
}
~~~

Ví dụ này giả định route được bảo vệ, token JWT hợp lệ và issuer là claim được yêu cầu theo policy. Claim lấy từ `Jwt` đã được Resource Server xây dựng sau xác thực đáng tin hơn dữ liệu giải mã thủ công từ một chuỗi chưa kiểm tra.

Tuy vậy, **principal đã xác thực không thay thế kiểm tra phân quyền trên dữ liệu**. Ngay cả token mang `sub=alice` và `SCOPE_orders.read`, service vẫn phải kiểm tra Alice có được đọc đơn hàng cụ thể hay không.

### Tự gọi `JwtDecoder` trong Java

Nếu thực sự cần validate token tại một boundary được thiết kế rõ ràng (ví dụ xử lý một message có chứa access token theo contract nội bộ), có thể dùng `JwtDecoder` được cấu hình với issuer/khóa/validators thích hợp:

~~~java
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtException;

public final class JwtValidationExample {

    private final JwtDecoder jwtDecoder;

    public JwtValidationExample(JwtDecoder jwtDecoder) {
        this.jwtDecoder = jwtDecoder;
    }

    public String validatedSubject(String untrustedToken) {
        try {
            Jwt verifiedAndValidated = jwtDecoder.decode(untrustedToken);
            return verifiedAndValidated.getSubject();
        } catch (JwtException ex) {
            throw new IllegalArgumentException(
                "JWT failed configured verification/validation", ex);
        }
    }
}
~~~

Tên biến `verifiedAndValidated` trong ví dụ có điều kiện: **decoder phải được cấu hình đúng**. Nếu tự thay `JwtDecoder` bằng một implementation tùy biến chỉ parse payload, không thể gán cho kết quả độ tin cậy như trên. Trong controller HTTP thông thường, nên để Spring Security filter chain xác thực và lấy principal từ `SecurityContext` thay vì decode lại token thủ công.

## 8. Một lỗi bảo mật kinh điển: tin payload đã decode trong filter tự viết

Giả sử ứng dụng viết filter như sau:

~~~java
// SAI: chỉ là pseudocode để chỉ ra lỗi thiết kế
String token = resolveBearerToken(request);
String payloadJson = base64UrlDecode(token.split("\\.")[1]);
String role = jsonObject(payloadJson).getString("role");

if ("ADMIN".equals(role)) {
    allowAdminRequest();
}
~~~

Đoạn code sai vì:

1. Client có thể tự tạo JSON có `role=ADMIN`.
2. Client có thể Base64URL encode JSON đó mà không cần biết khóa ký.
3. Filter đã dùng dữ liệu chưa xác minh làm căn cứ phân quyền.
4. Một chữ ký sai hoặc không tồn tại không cản trở đường xử lý này nếu filter không verify.

Dạng sai tương tự:

~~~java
// SAI: parse untrusted claim rồi đưa vào SecurityContext
String userId = parseJwtWithoutVerification(token).get("sub");
Authentication authentication =
    createTrustedAuthentication(userId);
SecurityContextHolder.getContext().setAuthentication(authentication);
~~~

Trong kiến trúc Spring Security, không được tự gắn `Authentication` có trạng thái đáng tin nếu chỉ mới parse token. Hãy để `JwtAuthenticationProvider` và `JwtDecoder` đã cấu hình thực hiện xác minh/validation trước, sau đó ánh xạ authorities theo các claim được tin cậy.

### Lỗi đối lập: chữ ký đúng nhưng bỏ kiểm tra audience

Một hệ thống có thể xác minh chữ ký JWT bằng public key của tổ chức nhưng không kiểm tra `aud`, dẫn đến chấp nhận token vốn được cấp cho API khác.

Ví dụ:

~~~text
JWT: iss=https://idp.example.com
     aud=reporting-api
     scope=reports.read
     signature=valid

orders-api:
     signature=valid
     issuer=trusted
     audience NOT validated     <-- thiếu kiểm tra
~~~

Không thể kết luận token này dành cho `orders-api`. **Xác minh chữ ký và xác minh mục đích sử dụng đều là điều kiện riêng cần có.**

## 9. Không nhầm lỗi xác minh mật mã với lỗi phân quyền

Khi client nhận `401` hoặc `403`, việc decode token có thể gợi ý nguyên nhân nhưng không quyết định kết luận.

| Hiện tượng | Decode thấy gì? | Kiểm tra cần làm trên Resource Server |
|---|---|---|
| Token thiếu hoặc header sai | Không có token để đọc, hoặc chuỗi không đúng định dạng | Bearer token resolver, filter chain, endpoint bắt buộc xác thực |
| Payload nhìn đúng nhưng chữ ký giả | Header/payload vẫn đọc được | Thuật toán cho phép, chữ ký, public key tin cậy |
| Header có `kid` mới | `kid` hiển thị bình thường | JWKS cache, key rotation, khóa tương ứng từ issuer |
| `iss` nhìn đúng nhưng token bị từ chối | Text `iss` trùng kỳ vọng | So sánh issuer sau xác minh, metadata và cấu hình issuer |
| `aud` thiếu API hiện tại | Claim đọc được nhưng không phù hợp | Audience validator phải từ chối token |
| `exp` đã qua hoặc `nbf` tương lai | Các NumericDate vẫn đọc được | Claim validators, đồng bộ đồng hồ và clock skew |
| Token JWT hợp lệ nhưng scope thiếu | `scope` chỉ chứa `orders.read` | Authority mapping, `hasAuthority`, policy endpoint |
| Token không phải JWT JWS | Không thể tách/parse ba đoạn đúng | Phân biệt opaque token, JWE, dữ liệu không hợp lệ |
| Token hợp lệ nhưng truy cập nhầm tenant | Claim có `tenant_id` hợp lệ | Kiểm tra isolation và quyền trên từng tài nguyên |
| Khóa issuer chưa tải được | Decode bình thường | Trạng thái JWKS endpoint, TLS, DNS, timeout và cấu hình |

Cách phân biệt lỗi điển hình:

- **`401 Unauthorized`**: không có authentication hợp lệ, token sai, hết hạn, chữ ký/validator không đạt.
- **`403 Forbidden`**: authentication hợp lệ nhưng không đủ scope/authority hoặc chính sách quyền tài nguyên không cho phép.
- **Sự cố AS/JWKS**: có thể biểu hiện khác nhau tùy Spring Security version, cách cấu hình và exception handling; cần xem nguyên nhân gốc ở telemetry server.

Một lỗi hay gặp khi debug là thấy token có `scope=orders.write` nhưng request vẫn bị `403` rồi cho rằng Spring Security kiểm tra sai. Hãy kiểm tra token thực sự được xác thực chưa, claim scope được ánh xạ như thế nào và yêu cầu phân quyền có trùng đường dẫn/phương thức HTTP không. Đặc biệt, `ROLE_ADMIN` và `SCOPE_orders.write` không phải cùng một authority.

## 10. Quy trình debug JWT an toàn và hữu ích

Khi một API từ chối request dùng access token, một quy trình có thể là:

### Bước 1 — Xác định loại token trước

Hỏi Authorization Server phát hành token dạng gì:

- **JWS compact (signed JWT)** thường có ba đoạn cách nhau bởi dấu chấm.
- **JWE compact (encrypted JWT)** thường có năm đoạn.
- **Opaque access token** có thể là chuỗi không giải mã được thành claims JSON theo cách JWT.

Số đoạn và nội dung “trông như JWT” chỉ là tín hiệu định dạng, **không tự chứng minh token thật hoặc an toàn**.

### Bước 2 — Đọc header/payload để đặt giả thuyết

Nếu token là JWS compact và chính sách vận hành cho phép, hãy decode **cục bộ** để xem:

- `alg` và `kid` đang được token khai báo là gì.
- `iss` và `aud` có *trông giống* giá trị dự kiến không.
- `exp`, `nbf` có cho thấy khả năng lỗi thời gian không.
- `scope`/`scp` có những quyền nào.
- `typ` có gợi ý loại token không phù hợp không.

Những quan sát này phải được ghi chú là **unverified**. Một header/payload được đọc từ nguồn không tin cậy cũng có thể chứa dữ liệu không đúng kiểu, JSON rất lớn hoặc định dạng bất thường. Giới hạn kích thước và số trường khi viết công cụ inspect thực tế.

### Bước 3 — Kiểm tra cấu hình tin cậy từ phía API

Xem cấu hình của Resource Server:

- Issuer URI và expected audience.
- JWKS URI/metadata endpoint đến từ nguồn tin cậy.
- Thuật toán ký được chấp nhận.
- Kiểm tra thời gian và clock skew.
- Những `OAuth2TokenValidator` hoặc decoder tùy biến đã thêm.
- Chính sách phân quyền `SecurityFilterChain`, method security và mapping authorities.

Không dùng chính các claim chưa xác minh để quyết định issuer hoặc JWKS endpoint cho request hiện tại, trừ khi có một thiết kế multi-tenant an toàn đã giới hạn rõ danh sách issuer được phép.

### Bước 4 — Tìm kết quả của quá trình xác minh thật

Xem kết quả Resource Server nhận ở boundary authentication:

~~~text
Unverified token
      |
      +--> signature/algorithm/key valid?
      |        |
      |        +-- no  -> reject
      |
      +--> issuer/audience/time/type valid?
      |        |
      |        +-- no  -> reject
      |
      +--> authenticated principal + authorities
               |
               +--> endpoint/resource policy allows?
                        |
                        +-- no  -> forbidden
                        +-- yes -> controller/service
~~~

Việc đã đọc được JSON **không được dùng để bỏ qua** bất kỳ nút quyết định nào ở trên.

### Bước 5 — Ghi log với thông tin tối thiểu

Có thể log các thông tin vận hành không nhạy cảm theo chính sách:

~~~text
event=jwt_authentication_failed
path=/api/orders
reason=audience_invalid
expectedAudience=orders-api
traceId=a5c8...
token=[REDACTED]
~~~

Tùy nhu cầu, cũng có thể ghi mã lỗi hoặc định danh cấu hình công khai. **Không log nguyên JWT, payload chứa PII, secret, access token, refresh token hay token signature**. Không ghi message exception chứa token nguyên văn nếu thư viện đưa token vào thông báo.

Nếu phải làm việc với token thật để điều tra, dùng kênh và quy trình bảo mật được tổ chức cho phép; ưu tiên phát hành token kiểm thử có scope/audience tối thiểu.

## 11. Chẩn đoán lỗi chữ ký và JWKS: đọc `kid` chỉ là điểm khởi đầu

Một ví dụ thường gặp khi Authorization Server xoay khóa:

1. Token mới có header `kid=key-2026-02`.
2. Resource Server đang cache JWKS chỉ chứa `key-2026-01`.
3. Công cụ decode vẫn hiển thị header/payload hoàn toàn bình thường.
4. Resource Server chưa tìm được khóa phù hợp để verify, dẫn tới authentication thất bại cho tới khi bộ khóa được cập nhật đúng.

Kết luận đúng không phải “token chắc chắn sai” hay “chỉ cần bỏ qua chữ ký”. Cần xem quy trình **JWKS rotation/refresh**, tính sẵn sàng của endpoint, cache và thuật toán được chấp nhận.

Nếu AS công bố nhiều khóa, `kid` giúp tìm khóa nhưng **không phải bằng chứng chính**. Public key cần gắn với đúng issuer và đúng nguồn tin cậy. Khi gặp khóa không rõ, Resource Server phải từ chối token cho tới khi có khóa hợp lệ từ cơ chế tin cậy, không tự chấp nhận thông tin bên trong token.

## 12. JWE và opaque token: không phải token nào cũng có payload đọc trực tiếp

### JWE có thể chứa claims đã mã hóa

Một JWT được mã hóa theo JWE Compact Serialization thường có năm phần:

~~~text
protected-header
.
encrypted-key
.
initialization-vector
.
ciphertext
.
authentication-tag
~~~

Không thể chỉ Base64URL decode một phần bất kỳ rồi thấy claims JSON plaintext. Muốn đọc nội dung JWE cần **giải mã đúng cách bằng khóa phù hợp**, và tùy cấu trúc token còn phải xử lý nested JWT/JWS cùng các kiểm tra bảo mật khác.

Một JWE giải mã thành công **cũng không mặc nhiên đủ quyền truy cập**: Resource Server vẫn phải kiểm tra policy issuer, audience, thời gian, loại token và các điều kiện toàn vẹn/xác thực phù hợp. Không suy ra “giải mã được” đồng nghĩa “được phép dùng”.

### Opaque access token không có hợp đồng JWT

Opaque token được Resource Server coi như chuỗi tham chiếu. Không thể biết `scope`, `sub` hay `exp` chỉ bằng “decode”. Với Spring Security Resource Server, cơ chế tương ứng thường là **introspection**:

~~~text
Bearer opaque token
       |
       v
OpaqueTokenIntrospector
       |
       v
Authorization Server introspection endpoint
       |
       v
active + attributes
       |
       v
authentication + authorization policy
~~~

Không cố ép một opaque token qua JWT parser. Đồng thời, một access token có dạng JWT vẫn **có thể được introspect** nếu Authorization Server và chính sách Resource Server dùng cách đó để kiểm tra trạng thái.

Khác biệt quan trọng: **định dạng token** (JWS/JWE/opaque) và **cách xác minh** (cục bộ/introspection) là hai quyết định thiết kế cần được thống nhất với Authorization Server.

## 13. Thận trọng với token hợp lệ nhưng không thể dùng trong API

Ngay cả khi Spring Security đã tạo `Authentication` thành công, vẫn có những trường hợp token không đủ điều kiện cho hành động cụ thể.

Ví dụ API:

~~~text
GET    /api/orders/1001    cần SCOPE_orders.read
POST   /api/orders         cần SCOPE_orders.write
DELETE /api/orders/1001    cần SCOPE_orders.delete
~~~

Một token được ký chính xác, còn hạn, `aud=orders-api` và `scope=orders.read` có thể gọi `GET` nhưng không nên được dùng cho `POST` hoặc `DELETE`.

Một điều kiện khác là **quyền sở hữu dữ liệu**: principal `alice` có thể đọc order thuộc Alice nhưng không được đọc order thuộc Bob dù token có scope đọc đơn hàng.

Điều này cho thấy ba cổng kiểm soát riêng:

~~~text
Token payload đọc được?
    |
    v
Token đáng tin và còn hiệu lực?
    |
    v
Request có đủ quyền endpoint?
    |
    v
User/client có quyền trên bản ghi cụ thể?
    |
    v
Thực thi thao tác
~~~

Chỉ cổng thứ hai trở đi mới có ý nghĩa bảo mật; cổng “đọc được” chỉ hỗ trợ chẩn đoán.

## 14. Kiểm thử: một bài test mock JWT chưa kiểm tra chữ ký thật

Trong Spring Security Test, ứng dụng có thể dùng tiện ích như `SecurityMockMvcRequestPostProcessors.jwt()` để đưa một principal JWT giả lập vào kiểm thử MVC. Cách này rất hữu ích để kiểm tra **authorization rule**, mapping principal hoặc behavior của controller trong ngữ cảnh đã xác thực.

Tuy nhiên, cần hiểu giới hạn: kiểu test đó thường **không đưa một JWS thật qua quá trình xác minh chữ ký bằng JWKS**. Vì vậy một test thành công với mock JWT không chứng minh Resource Server đang cấu hình issuer, thuật toán, audience và chữ ký đúng.

Ví dụ lớp hành vi cần kiểm tra:

~~~text
Authorization test:
- Jwt principal đã xác thực có SCOPE_orders.read
- GET /api/orders trả kết quả dự kiến
=> Kiểm tra quyền truy cập

Verification/integration test:
- JWS ký bằng khóa thật của test issuer
- RS dùng đúng public key + issuer + audience
- Chấp nhận token hợp lệ, từ chối chữ ký sai/issuer sai/aud sai/hết hạn
=> Kiểm tra đường xác minh token
~~~

Hai nhóm kiểm thử phục vụ mục tiêu khác nhau. Không dùng mock claim như bằng chứng việc kiểm tra mật mã đã hoạt động.

## 15. Những hiểu nhầm quan trọng

**“Đã Base64 decode payload là đã xác thực JWT.”** Sai. Decode không dùng khóa và không xác minh tính toàn vẹn.

**“JWT có trường `alg=RS256` nghĩa là được ký RS256.”** Sai. Đây là khai báo trong header chưa đáng tin; chỉ quá trình verify với chính sách thuật toán và khóa đúng mới kiểm chứng.

**“`kid` cho biết nên tin khóa nào.”** Chưa đủ. `kid` là gợi ý chọn khóa trong tập khóa được cấu hình tin cậy, không tự tạo ra trust.

**“Chữ ký hợp lệ thì API phải nhận token.”** Sai. Phải kiểm tra `iss`, `aud`, thời gian, loại token và chính sách ứng dụng.

**“`sub=admin` nghĩa là request đến từ admin.”** Sai. Trước xác minh nó là dữ liệu không tin cậy; ngay cả sau xác minh nó mô tả principal/token theo issuer, không tự chứng minh người hiện tại trực tiếp nhập request.

**“Dán JWT vào công cụ web để decode không có rủi ro vì payload vốn công khai.”** Sai. Token là credential bearer; ai lấy được token còn hiệu lực có thể sử dụng trong phạm vi token cho phép. Việc gửi chuỗi token tới hệ thống ngoài có thể làm lộ toàn bộ credential.

**“Chỉ cần check `exp` trong JSON là đủ.”** Sai. Không được dựa vào thời gian do token chưa xác minh tự khai báo.

**“Spring Security `JwtDecoder` chỉ giống `Base64.getUrlDecoder()`.”** Sai. `JwtDecoder` được cấu hình đúng sẽ xử lý xác minh JWT và áp dụng validators.

**“JWT nào cũng có ba phần đọc được.”** Sai. JWS compact thường có ba phần; JWE compact thường có năm phần; opaque token không có cấu trúc JWT công khai.

## 16. Bài tập tư duy

### Câu 1: Hai token cùng có payload, một token bị sửa claim

Một access token thật có `scope=orders.read`. Người khác sửa payload thành `scope=orders.write` và giữ nguyên đoạn signature. Cả hai đều được công cụ decode hiển thị. Token thứ hai có đáng tin không?

**Đáp án:** Không. Thay đổi payload làm thay đổi dữ liệu được ký. Nếu không ký lại bằng khóa hợp lệ của issuer, bước verify phải thất bại. Việc decode vẫn chạy được không liên quan tới chữ ký.

### Câu 2: Chữ ký đúng nhưng `aud=inventory-api`

Token do cùng issuer ký, `exp` còn hạn, nhưng endpoint được gọi thuộc `orders-api`. Có thể chấp nhận token không?

**Đáp án:** Không, nếu audience của token không bao gồm `orders-api`. Resource Server phải kiểm tra token được cấp cho đúng tài nguyên.

### Câu 3: `JwtDecoder.decode()` trả về `Jwt`

Có thể tin các claim được lấy từ `Jwt` này không?

**Đáp án:** Có thể dùng theo chính sách **khi decoder và validators được cấu hình chính xác** với thuật toán, issuer, khóa và claim cần thiết. Nếu thay decoder bằng một implementation không xác minh hoặc bỏ sót audience, kết quả không đủ cơ sở tin cậy cho API.

### Câu 4: Spring MVC test có `jwt()` và trả `200`

Test đã chứng minh chữ ký JWT production được kiểm tra đúng chưa?

**Đáp án:** Chưa. Mock JWT trong test có thể mô phỏng principal/authorities và bỏ qua đường xác minh JWT thật. Cần integration test riêng qua decoder và khóa kiểm thử thích hợp.

### Câu 5: Debug tool cho thấy `iss` và `exp` đúng, server vẫn trả `401`

Nên sửa server để “đọc claim trực tiếp” thay decoder không?

**Đáp án:** Không. Cần kiểm tra nguyên nhân ở bước xác minh thực: thuật toán, chữ ký, JWKS, audience, issuer, thời gian, token type và cấu hình Spring Security. Tránh thay việc xác minh bằng parse thủ công.

## 17. Tài liệu tham khảo

- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): định dạng token, claim và NumericDate.
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515): compact serialization và chữ ký/MAC.
- [RFC 7516 — JSON Web Encryption (JWE)](https://www.rfc-editor.org/rfc/rfc7516): token có nội dung được mã hóa.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): định dạng khóa JWK/JWKS.
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518): thuật toán JOSE.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): algorithm verification, tránh nhầm loại token, issuer/audience validation.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): cấu trúc và xác minh JWT access token theo profile chuẩn.
- [Spring Security — OAuth 2.0 Resource Server JWT (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): cấu hình JWT, issuer, JWKS, validators và authorities.
- [Spring Security — `JwtDecoder` API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/JwtDecoder.html): contract decoder.
- [Spring Security — OAuth 2.0 Resource Server Opaque Token (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): xác minh qua introspection.

Khi triển khai thực tế, hãy ghi nhớ sự khác nhau giữa **“đọc một claim do token tự khai báo”** và **“nhận một claim sau khi Resource Server đã xác minh token bằng trust configuration của chính mình”**. Phân biệt đúng hai trạng thái này là điều kiện nền tảng để bảo vệ mọi API OAuth 2.0/OIDC.
