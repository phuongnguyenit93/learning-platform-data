# `issuer-uri` và kiểm tra claim `iss` theo giá trị đã cấu hình

## 1. Resource Server phải biết ai là bên phát hành access token

Một Orders API xây dựng bằng **Spring Boot và Spring Security OAuth 2.0 Resource Server** thường nhận JWT access token:

~~~http
GET /api/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer eyJhbGciOi...
~~~

API không thể coi mọi JWT có cấu trúc đúng đều đáng tin. Nó cần xác định **Authorization Server nào được phép phát hành token cho API**. Trong JWT, claim **`iss`** (issuer) mô tả bên phát hành token; trong cấu hình Spring Security, **`issuer-uri`** đặt ra giá trị issuer mà Resource Server tin cậy.

Giả sử Authorization Server có issuer:

~~~text
https://id.example.test/realms/shop
~~~

Access token hợp lệ theo hợp đồng có thể mang:

~~~json
{
  "iss": "https://id.example.test/realms/shop",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "iat": 1999999700,
  "exp": 2000000000
}
~~~

Đây là JSON minh họa phần payload, **không phải JWT có chữ ký thật**. Mục tiêu kiểm tra `iss` là đảm bảo **token sau khi được xác minh mật mã** tuyên bố chính xác issuer mà API đã cấu hình.

Trong Spring Boot, cấu hình tối thiểu thông thường là:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.test/realms/shop
~~~

**Điểm cần nhớ:** `issuer-uri` là một **giá trị tin cậy do ứng dụng đặt trước**, được sử dụng để khám phá metadata/khóa công khai (khi chọn discovery) và để **so sánh với claim `iss` trong JWT**. Nó không phải một URI bất kỳ được lấy từ token rồi tự động tin tưởng.

## 2. Issuer, client, audience và JWKS có vai trò khác nhau

Trong OAuth 2.0/OIDC, các địa chỉ và định danh thường cùng xuất hiện, nhưng chúng trả lời những câu hỏi khác nhau:

| Giá trị | Ví dụ | Trả lời câu hỏi |
|---|---|---|
| **Issuer / `iss`** | `https://id.example.test/realms/shop` | Ai phát hành token? |
| **Audience / `aud`** | `orders-api` | Token dành cho API/tài nguyên nào? |
| **Client ID** | `shop-web` | Ứng dụng client nào nhận/được cấp quyền? |
| **JWKS URI** | `https://id.example.test/realms/shop/protocol/openid-connect/certs` | Lấy public key đã công bố ở đâu? |
| **Authorization endpoint** | `.../protocol/openid-connect/auth` | Client đưa người dùng tới đâu để xin quyền? |
| **Token endpoint** | `.../protocol/openid-connect/token` | Client đổi code hoặc grant để lấy token ở đâu? |
| **Resource Server** | `https://api.example.test` | API nào lưu tài nguyên cần bảo vệ? |

Các endpoint với đường dẫn `/protocol/openid-connect/...` ở bảng chỉ là **một cách tổ chức minh họa của một số Identity Provider**, không phải endpoint chuẩn cố định cho mọi provider.

Một JWT có:

~~~json
{
  "iss": "https://id.example.test/realms/shop",
  "aud": "orders-api"
}
~~~

có thể đúng issuer và đúng audience; JWT khác có:

~~~json
{
  "iss": "https://id.example.test/realms/shop",
  "aud": "billing-api"
}
~~~

vẫn cùng issuer nhưng **không dành cho Orders API**.

Vì vậy, **kiểm tra issuer và kiểm tra audience bổ sung cho nhau**:

- `iss` xác định **nguồn phát hành** được tin.
- `aud` xác định **bên nhận dự kiến** của token.
- `exp` và `nbf` xác định **thời gian** token có hiệu lực.
- Chữ ký/JWS xác minh nội dung token không bị sửa và được ký bằng khóa phù hợp chính sách.
- `scope` hoặc authorities quyết định **quyền endpoint**; còn quyền sở hữu tài nguyên phải được kiểm tra thêm ở tầng nghiệp vụ.

Chỉ kiểm tra `iss` sẽ không ngăn một access token dành cho dịch vụ khác bị gửi nhầm sang Orders API nếu hai dịch vụ tin cùng issuer. Chỉ kiểm tra chữ ký cũng không thay thế issuer validator khi nhiều issuer có thể liên quan đến bộ khóa hoặc hạ tầng dùng chung.

## 3. Claim `iss` trong JWT được so sánh như thế nào?

### 3.1. Giá trị issuer là định danh, không chỉ là domain

Theo RFC 7519, `iss` là một giá trị StringOrURI định danh bên phát hành. Trong một hệ thống OAuth/OIDC, nó thường là HTTPS URI.

Giả sử API cấu hình:

~~~text
spring.security.oauth2.resourceserver.jwt.issuer-uri =
https://id.example.test/realms/shop
~~~

Các payload thử:

| JWT claim `iss` | So với cấu hình | Ý nghĩa |
|---|---|---|
| `https://id.example.test/realms/shop` | Khớp | Đúng issuer kỳ vọng |
| `https://id.example.test/realms/other` | Không khớp | Khác realm/tenant |
| `https://id.example.test/realms/shop/` | Không khớp | Khác dấu gạch chéo cuối |
| `http://id.example.test/realms/shop` | Không khớp | Khác scheme |
| `https://another.example.test/realms/shop` | Không khớp | Khác host |
| `https://id.example.test` | Không khớp | Thiếu đường dẫn issuer |
| Không có `iss` | Không đạt yêu cầu issuer | Thiếu claim cần xác minh |
| `"iss": 123` | Sai kiểu theo hợp đồng | Không phải String issuer |

**Không tự cắt slash cuối, bỏ path, đổi scheme hoặc so domain một cách lỏng lẻo** để chấp nhận token. Các giá trị URI trên có thể dẫn đến issuer khác nhau mặc dù nhìn gần giống nhau.

Spring Security sử dụng issuer validator theo giá trị kỳ vọng đã cấu hình. Khi claim `iss` không khớp, JWT không đạt bước validation và request cần bị từ chối. Trong Resource Server JWT thông thường, đó là **401 Unauthorized** với Bearer token không hợp lệ.

### 3.2. Chữ ký đúng chưa có nghĩa issuer đúng

Giả sử hai issuer trong cùng tổ chức:

~~~text
Issuer A: https://id.example.test/realms/retail
Issuer B: https://id.example.test/realms/partners
~~~

Nếu API chỉ tin **Issuer A**, token do Issuer B phát hành vẫn phải bị từ chối **kể cả khi** vì một cấu hình sai hoặc hạ tầng dùng chung mà chữ ký của nó được xác minh bởi một khóa nằm trong tập khóa API tin.

Quy tắc tin cậy không phải:

~~~text
Có thể xác minh chữ ký -> cho phép
~~~

Mà tối thiểu:

~~~text
Đúng nguồn khóa và thuật toán được phép
  + chữ ký hợp lệ
  + iss == issuer đã cấu hình
  + exp/nbf hợp lệ
  + aud đúng API
  + token profile phù hợp
  + quyền endpoint/tài nguyên
  -> mới được phép xử lý request
~~~

Tương tự, claim `iss` là một chuỗi nằm trong **dữ liệu đầu vào chưa tin cậy cho đến khi token được xác minh**. Không được tin riêng nội dung `iss` chỉ vì nó xuất hiện trong một JWT có ba phần Base64URL.

## 4. Discovery là gì và liên quan gì tới `issuer-uri`?

**Discovery** cho phép Resource Server tìm cấu hình Authorization Server/OpenID Provider từ một **issuer tin cậy**. Thay vì người phát triển ghi cứng toàn bộ endpoint, ứng dụng có thể lấy metadata do provider công bố.

Hai họ tài liệu thường gặp:

- **OpenID Connect Discovery**: OpenID Provider Configuration.
- **OAuth 2.0 Authorization Server Metadata** (RFC 8414): metadata cho Authorization Server.

Điểm chung: cung cấp thông tin định danh issuer và những endpoint liên quan, đặc biệt **`jwks_uri`** để kiểm tra chữ ký JWT.

### 4.1. Metadata mẫu

Với issuer:

~~~text
https://id.example.test/realms/shop
~~~

một provider có thể công bố metadata kiểu:

~~~text
https://id.example.test/realms/shop/.well-known/openid-configuration
~~~

Ví dụ nội dung rút gọn:

~~~json
{
  "issuer": "https://id.example.test/realms/shop",
  "authorization_endpoint":
    "https://id.example.test/realms/shop/protocol/openid-connect/auth",
  "token_endpoint":
    "https://id.example.test/realms/shop/protocol/openid-connect/token",
  "jwks_uri":
    "https://id.example.test/realms/shop/protocol/openid-connect/certs"
}
~~~

Đây là JSON **minh họa metadata**. Endpoint thực tế phải được xác nhận theo provider. Ngoài đường dẫn OIDC Discovery dạng issuer + `/.well-known/openid-configuration`, OAuth metadata có thể dùng cách ghép `/.well-known/oauth-authorization-server` với path issuer; Spring Security hỗ trợ những vị trí metadata tương ứng mà tài liệu hiện hành liệt kê.

**Đừng suy ra JWKS URI bằng cách tự thêm một hậu tố cố định vào issuer.** Địa chỉ JWKS không có cấu trúc đường dẫn bắt buộc giống nhau cho mọi nhà cung cấp; lấy từ metadata hoặc hợp đồng provider.

### 4.2. Discovery không đồng nghĩa đăng nhập OIDC

Resource Server chỉ cần xác minh **access token**. Việc nó dùng OIDC Provider Configuration để tìm public keys **không biến nó thành một OIDC Login Client**.

Các vai trò:

| Spring Security capability | Mục đích |
|---|---|
| `oauth2ResourceServer().jwt()` | Xác minh Bearer JWT access token để bảo vệ API |
| `oauth2Login()` | Thực hiện đăng nhập OAuth 2.0/OIDC cho ứng dụng web client |
| `oauth2Client()` | Quản lý OAuth2AuthorizedClient để gọi dịch vụ khác |

Resource Server có thể dùng metadata từ một OpenID Provider, nhưng **không có nghĩa nó sẽ nhận ID Token thay access token**. OIDC ID Token được cấp cho client; API cần JWT access token có audience/token type phù hợp.

### 4.3. Metadata phải nhất quán với issuer đã tin cậy

Với hệ thống ví dụ, cần đồng bộ ba giá trị:

~~~text
Configured issuer-uri:
https://id.example.test/realms/shop

Metadata "issuer":
https://id.example.test/realms/shop

JWT claim "iss":
https://id.example.test/realms/shop
~~~

Nếu metadata mô tả issuer khác, hoặc token phát hành `iss` khác với cấu hình, đó là **lỗi cấu hình/contract cần giải quyết**, không phải lý do bỏ issuer validation.

Ví dụ bên phát hành nằm sau reverse proxy: metadata trả `issuer = http://idp-internal:8080/realms/shop` nhưng token có `iss = https://login.example.com/realms/shop`. Resource Server nên thống nhất public issuer chính thức với provider và cấu hình metadata/forwarded headers đúng cách, thay vì chấp nhận tùy ý cả hai issuer.

## 5. Spring Boot cấu hình `issuer-uri` tối thiểu

### 5.1. Dependencies

Ví dụ Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

Starter OAuth2 Resource Server cung cấp phần tích hợp Spring Security, bao gồm hỗ trợ JOSE/JWT tương ứng trong dependency setup của Spring Boot. Nếu quản lý dependency bằng module Spring Security thay vì starter, cần đảm bảo có cả thành phần resource server và JOSE để xác thực JWT.

### 5.2. Cấu hình `application.yml`

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.test/realms/shop
~~~

Chỉ cấu hình này là đủ cho kịch bản cơ bản khi:

1. Authorization Server hỗ trợ metadata discovery phù hợp.
2. JWKS công bố các khóa công khai để xác minh chữ ký của access token.
3. JWT sử dụng profile và thuật toán ký được decoder hỗ trợ/chấp nhận.
4. Resource Server có thể truy cập những endpoint cần thiết vào thời điểm giải quyết khóa.
5. Không có các chính sách bổ sung như audience hoặc custom claim cần cấu hình riêng.

Cần bảo đảm ứng dụng thực sự có **`SecurityFilterChain` bật JWT Resource Server**. Khi Spring Boot tự cấu hình một chain phù hợp và người phát triển chưa thay thế cấu hình, Boot có thể tạo chain mặc định; khi tự cung cấp chain, phải bật Resource Server trong chain đó.

### 5.3. Filter chain minh họa

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            );
        return http.build();
    }
}
~~~

Ví dụ chỉ đặt chain cho `/api/**`; một ứng dụng thực tế cần chính sách bảo vệ các đường dẫn còn lại. Hợp đồng issuer thực sự do property `issuer-uri` quyết định, còn `SecurityFilterChain` chọn các endpoint và bật xử lý JWT Bearer.

Khi nhận request:

~~~http
GET /api/orders HTTP/1.1
Authorization: Bearer <JWT_ACCESS_TOKEN>
~~~

thành phần `BearerTokenAuthenticationFilter` tìm token; `JwtAuthenticationProvider` dùng `JwtDecoder` để xác minh JWT và validators; nếu thành công, authentication được lưu trong `SecurityContext` để các rule authorization sử dụng.

### 5.4. Resource Server kiểm tra những gì?

Theo cấu hình thông dụng từ `issuer-uri`, Spring Security xác thực chữ ký JWT bằng public key phù hợp và kiểm tra các claim nền tảng như `exp`, `nbf`, `iss`. Sau đó converter có thể ánh xạ scopes thành authorities như `SCOPE_orders.read`.

**Không suy ra** rằng chỉ vì `issuer-uri` đã cấu hình thì tự động kiểm tra đủ mọi hợp đồng access token. `aud`, token type/profile, client, tenant hoặc claim nghiệp vụ có thể cần cấu hình thêm. Ứng dụng có yêu cầu chặt về audience nên khai báo rõ.

## 6. Đường đi: từ issuer đến metadata, JWKS và kiểm tra `iss`

~~~mermaid
sequenceDiagram
    participant Client as API Client
    participant API as Spring Resource Server
    participant Meta as Metadata Endpoint
    participant JWKS as JWKS Endpoint

    Client->>API: GET /api/orders + Bearer JWT
    Note over API: issuer-uri đã cấu hình trước, là nguồn tin cậy
    API->>Meta: Discovery metadata của issuer (khi cần)
    Meta-->>API: issuer + jwks_uri + metadata
    API->>JWKS: Lấy public signing keys (khi cần)
    JWKS-->>API: JWK Set
    API->>API: Xác minh JWS signature/thuật toán
    API->>API: Validate iss == issuer-uri
    API->>API: Validate exp/nbf và các validators khác
    API->>API: Chuyển scopes thành authorities
    API-->>Client: Cho request tiếp tục nếu hợp lệ/đủ quyền
~~~

Sơ đồ thể hiện **quan hệ giữa các bước**, không có nghĩa mọi request đều gọi metadata và JWKS qua mạng. Thư viện có thể cache cấu hình/khóa và chỉ truy cập lại khi cần, ví dụ khi chưa có khóa thích hợp hoặc có key rotation.

### 6.1. Discovery xảy ra khi nào?

Điểm này phụ thuộc phiên bản và cách khởi tạo decoder:

- Trong các tài liệu Spring Security Servlet hiện hành, cấu hình Resource Server mặc định có thể dùng **lazy discovery**, tức tra metadata khi bắt đầu xử lý request JWT đầu tiên; `SupplierJwtDecoder` giúp trì hoãn khởi tạo.
- Trong các phiên bản cũ hơn hoặc khi ứng dụng **tự xây `JwtDecoder`** bằng phương thức truy vấn issuer ngay lúc tạo bean, discovery có thể diễn ra sớm ở giai đoạn khởi tạo.
- Khi sử dụng `jwk-set-uri` trực tiếp cùng `issuer-uri`, ứng dụng không cần discovery chỉ để tìm địa chỉ JWKS; tuy vậy việc tải khóa thực tế vẫn cần provider/endpoint JWKS sẵn sàng tại thời điểm kiểm tra token.

Vì thế, không nên đưa ra quy tắc tuyệt đối “Resource Server luôn gọi IdP ở startup” hoặc “IdP down không bao giờ ảnh hưởng request”. Cần dựa vào **phiên bản Spring Security, cách khởi tạo decoder, trạng thái cache khóa và cấu hình HTTP client**.

### 6.2. Nếu discovery hoặc JWKS lỗi thì sao?

Ví dụ:

- Metadata endpoint không hoạt động hoặc không có đường dẫn discovery hỗ trợ.
- Metadata trả cấu trúc không phù hợp hoặc issuer không nhất quán.
- JWKS endpoint timeout/không truy cập được.
- JWT dùng `kid` chưa có trong cache và không tải được khóa mới.
- Bên phát hành đã quay vòng signing key nhưng Resource Server chưa lấy được public key cần thiết.

Khi không có cách xác minh đáng tin cậy, Resource Server **không được chấp nhận token chỉ dựa vào claim `iss`**. Lỗi có thể biểu hiện như authentication failure/401 hoặc sự cố hạ tầng tùy thời điểm/cấu hình; cần phân biệt trường hợp token sai với lỗi không thể xác minh do mạng.

Về vận hành, nên đặt timeout phù hợp, theo dõi tình trạng discovery/JWKS, có chính sách cache/key rotation rõ ràng và sử dụng HTTPS để truy cập endpoint tin cậy. Không fallback sang chấp nhận JWT chưa xác minh.

## 7. So sánh ba cấu hình `issuer-uri` và `jwk-set-uri`

| Cấu hình | Khám phá JWKS qua metadata? | Tự biết giá trị `iss` được kỳ vọng? | Khi nào phù hợp? |
|---|---|---|---|
| Chỉ `issuer-uri` | Có, trong pipeline discovery phù hợp | Có | Provider hỗ trợ discovery và dùng issuer đã thống nhất |
| `issuer-uri` + `jwk-set-uri` | Không cần discovery để tìm JWKS | Có | Muốn chỉ rõ JWKS, tránh phụ thuộc discovery khi khởi tạo |
| Chỉ `jwk-set-uri` | Không cần discovery | **Không mặc nhiên có issuer kỳ vọng** | Có khóa xác minh trực tiếp; phải cấu hình issuer validator riêng nếu API cần kiểm tra `iss` |

### 7.1. Chỉ `issuer-uri`

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.test/realms/shop
~~~

Spring Security dùng issuer tin cậy để xác định metadata, tìm public keys và validate claim `iss`. Ưu điểm là cấu hình ngắn và giảm hard-code endpoint JWKS.

### 7.2. `issuer-uri` kết hợp `jwk-set-uri`

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.test/realms/shop
          jwk-set-uri: https://id.example.test/realms/shop/protocol/openid-connect/certs
~~~

Hai giá trị có vai trò riêng:

- `issuer-uri` tiếp tục là **giá trị phải khớp với JWT claim `iss`**.
- `jwk-set-uri` là **địa chỉ lấy public keys để xác minh chữ ký JWS**.

Kết hợp này phù hợp nếu muốn định tuyến đến JWKS một cách tường minh mà **vẫn giữ issuer validation**.

**Không hiểu là Spring sẽ bỏ so `iss` khi có `jwk-set-uri`**: với cả hai property trong auto configuration phù hợp, kiểm tra issuer vẫn được duy trì.

### 7.3. Chỉ `jwk-set-uri`: một bẫy bảo mật

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          jwk-set-uri: https://id.example.test/realms/shop/protocol/openid-connect/certs
~~~

Nếu không cung cấp issuer bằng property khác hoặc validator tùy chỉnh, Resource Server **không có giá trị issuer được cấu hình để tự so sánh `iss`**. Việc xác minh JWS signature bằng khóa từ JWKS chưa chứng minh token có `iss` phù hợp với issuer mà API muốn tin.

Điều này đáng chú ý khi:

- Một bộ khóa được chia sẻ hoặc cấu hình sai giữa nhiều issuer.
- JWKS endpoint tập hợp khóa của nhiều tenant/realm.
- API không muốn chấp nhận mọi token được ký bởi hệ thống giữ khóa nhưng phát hành cho các ngữ cảnh khác nhau.

Nếu discovery không khả dụng mà vẫn cần kiểm tra issuer, hãy ưu tiên **khai báo đồng thời `issuer-uri` và `jwk-set-uri`**, hoặc tự gắn validator issuer đúng cách khi xây decoder.

### 7.4. JWKS URI không phải giá trị `iss`

Giả sử:

~~~text
issuer-uri:
https://id.example.test/realms/shop

jwk-set-uri:
https://id.example.test/realms/shop/protocol/openid-connect/certs
~~~

JWT phải có:

~~~json
{"iss": "https://id.example.test/realms/shop"}
~~~

JWT **không** được yêu cầu đặt `iss` thành URL `.../certs`. Đây là lỗi nhầm tên rất thường gặp: **issuer định danh bên phát hành**, còn **JWKS là endpoint phân phối public keys**.

## 8. Kiểm tra issuer và audience cùng lúc

Một access token có thể đúng issuer nhưng dành cho ứng dụng khác. Với Spring Boot hỗ trợ thuộc tính `audiences`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.test/realms/shop
          audiences:
            - orders-api
~~~

Với cấu hình phù hợp, API đòi:

~~~text
JWT iss == https://id.example.test/realms/shop
AND
JWT aud contains orders-api
~~~

Nếu một token:

~~~json
{
  "iss": "https://id.example.test/realms/shop",
  "aud": ["billing-api"],
  "exp": 2000000000
}
~~~

thì token đúng issuer nhưng sai audience đối với Orders API. Nếu audience validator đang được bật, request cần bị từ chối.

Ngược lại:

~~~json
{
  "iss": "https://id.example.test/realms/other",
  "aud": ["orders-api"],
  "exp": 2000000000
}
~~~

thì token đúng audience nhưng sai issuer. Cũng phải bị từ chối.

**Kiểm tra claim không thể thay thế xác minh chữ ký**: hai payload trên chỉ minh họa về trường dữ liệu. Trong thực tế, JWT phải được ký hợp lệ, kiểm tra thuật toán và các điều kiện thời gian trước khi được xem là một access token đáng tin.

## 9. Cấu hình Java khi cần tự tạo `JwtDecoder`

### 9.1. Dùng `JwtDecoders.fromIssuerLocation`

Khi sử dụng Spring Security ngoài auto configuration hoặc muốn tạo decoder tường minh, có thể gọi:

~~~java
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtDecoders;

String issuer = "https://id.example.test/realms/shop";
JwtDecoder decoder = JwtDecoders.fromIssuerLocation(issuer);
~~~

`JwtDecoders.fromIssuerLocation(issuer)` dùng issuer được chỉ định để tìm metadata/JWKS và tạo decoder theo các mặc định của Spring Security. Việc trực tiếp gọi phương thức này ở thời điểm khởi tạo bean có thể khiến metadata discovery diễn ra **khi tạo bean**, khác với đường đi lazy mà Spring Boot quản lý trong một số phiên bản.

Nếu dùng được `issuer-uri` qua Spring Boot và không cần custom decoder, thường nên để cấu hình tự động thực hiện công việc này vì ít điểm phải bảo trì hơn.

### 9.2. Dùng `NimbusJwtDecoder` và gắn validator issuer rõ ràng

Nếu cần dùng JWKS tường minh cùng issuer mà chưa dựa vào property tự cấu hình, có thể khai báo bean:

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
public class JwtDecoderConfig {

    @Bean
    JwtDecoder jwtDecoder(Environment environment) {
        String issuer = environment.getRequiredProperty(
            "spring.security.oauth2.resourceserver.jwt.issuer-uri");
        String jwks = environment.getRequiredProperty(
            "spring.security.oauth2.resourceserver.jwt.jwk-set-uri");

        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(jwks)
            .build();

        // Giữ các validator mặc định và bắt buộc claim iss khớp issuer.
        decoder.setJwtValidator(
            JwtValidators.createDefaultWithIssuer(issuer));

        return decoder;
    }
}
~~~

`application.yml` cho bean trên:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.test/realms/shop
          jwk-set-uri: https://id.example.test/realms/shop/protocol/openid-connect/certs
~~~

Giải thích:

- `withJwkSetUri(jwks)` tạo decoder dùng nguồn khóa công khai tường minh.
- `JwtValidators.createDefaultWithIssuer(issuer)` thêm **issuer validation**, cùng các validation mặc định thích hợp như thời gian token.
- `setJwtValidator(...)` đặt validator cho decoder.
- Không có thành phần nào ở đây tự cấu hình riêng audience/role/tenant của Orders API.

Khi tự cung cấp bean `JwtDecoder`, **Spring Boot có thể không tạo decoder tự động thay thế**. Các property tiện lợi của auto configuration, gồm cả `audiences`, không nên được mặc định cho là đã áp dụng lên bean tùy chỉnh: phải thêm các validator tương ứng vào chính decoder đó.

### 9.3. Thêm audience validator mà vẫn giữ issuer validator

Ví dụ phiên bản mở rộng khi API đòi `aud` chứa `orders-api`:

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
public class JwtContractConfig {

    @Bean
    JwtDecoder jwtDecoder(Environment env) {
        String issuer = env.getRequiredProperty(
            "spring.security.oauth2.resourceserver.jwt.issuer-uri");
        String jwks = env.getRequiredProperty(
            "spring.security.oauth2.resourceserver.jwt.jwk-set-uri");
        String audience = env.getRequiredProperty(
            "app.security.expected-audience");

        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(jwks)
            .build();

        OAuth2TokenValidator<Jwt> issuerAndTime =
            JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> audienceValidator = jwt -> {
            if (jwt.getAudience().contains(audience)) {
                return OAuth2TokenValidatorResult.success();
            }

            return OAuth2TokenValidatorResult.failure(
                new OAuth2Error(
                    "invalid_token",
                    "Token audience does not match this API",
                    null));
        };

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                issuerAndTime,
                audienceValidator));

        return decoder;
    }
}
~~~

YAML tương ứng:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.test/realms/shop
          jwk-set-uri: https://id.example.test/realms/shop/protocol/openid-connect/certs

app:
  security:
    expected-audience: orders-api
~~~

Đây là **cấu hình thay thế** cho bean `JwtDecoder` ở phần 9.2; không khai báo cả hai bean cùng tên/loại mà không có mục đích rõ ràng.

Những kiểm tra mà ví dụ minh họa:

1. JWS chữ ký hợp lệ với nguồn public key đã cấu hình.
2. Claim `iss` phải khớp issuer đã cấu hình.
3. `exp`/`nbf` đạt validator thời gian.
4. `aud` chứa audience ứng dụng yêu cầu.

Authorization cho từng endpoint (`scope`/authority/owner) vẫn thuộc `SecurityFilterChain` và nghiệp vụ. Với token theo RFC 9068 hoặc profile issuer có yêu cầu `typ`, `client_id`, `iat`, `jti`, cần thêm validator tương ứng.

### 9.4. Sai lầm khi tự thay validator

Ví dụ dễ mắc lỗi:

~~~java
decoder.setJwtValidator(jwt ->
    jwt.getAudience().contains("orders-api")
        ? OAuth2TokenValidatorResult.success()
        : OAuth2TokenValidatorResult.failure(
            new OAuth2Error("invalid_token", "Wrong audience", null)));
~~~

Nếu đoạn trên **thay toàn bộ validator**, nó có thể làm mất các kiểm tra issuer và thời gian mà decoder trước đó được cấu hình. Kết quả là ứng dụng chỉ nhìn audience và bỏ qua những điều kiện bảo mật nền tảng.

Cần kết hợp với `JwtValidators.createDefaultWithIssuer(issuer)` (hoặc các validator tương đương phù hợp), và chỉ bổ sung chứ không vô tình xóa các ràng buộc quan trọng.

## 10. Đọc `iss` trong controller khác với validation

Sau khi authentication thành công, controller có thể đọc issuer:

~~~java
package com.example.orders.api;

import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SessionInfoController {

    @GetMapping("/api/session-info")
    public Map<String, String> info(@AuthenticationPrincipal Jwt jwt) {
        return Map.of(
            "subject", jwt.getSubject(),
            "issuer", jwt.getIssuer().toString()
        );
    }
}
~~~

Đây là ví dụ **đọc principal đã được Resource Server xác thực**. Trong hệ thống dùng issuer URI, phương thức `jwt.getIssuer()` cho biết issuer claim sau decode. Khi claim này bắt buộc và đã qua validation, nó có thể được sử dụng để tạo context nghiệp vụ.

**Không dùng** cách sau để “xác thực” token:

~~~java
// KHÔNG ĐÚNG: đọc payload chưa xác minh rồi so chuỗi trong controller.
String issuer = decodeBase64UrlPayload(rawBearerToken).get("iss");
if (issuer.equals("https://id.example.test/realms/shop")) {
    // tự cho phép truy cập
}
~~~

Một attacker có thể tự tạo JSON payload với bất kỳ `iss` nào. Chỉ khi token đã được xác minh chữ ký với khóa tin cậy và qua các validator, issuer claim mới có ý nghĩa bảo mật.

Ví dụ controller trên giả định token hợp lệ luôn có `sub` và `iss`. Ở ứng dụng production, tránh log hoặc trả về claim không cần thiết; chỉ expose metadata trong endpoint debug/training được kiểm soát.

## 11. Cấu hình issuer khi có reverse proxy, realm hoặc nhiều môi trường

### 11.1. Không lấy host nội bộ thay cho issuer công khai

Giả sử Identity Provider chạy nội bộ:

~~~text
http://idp:8080/realms/shop
~~~

Nhưng public issuer chính thức là:

~~~text
https://login.example.test/realms/shop
~~~

JWT và metadata chuẩn công bố:

~~~json
{
  "iss": "https://login.example.test/realms/shop"
}
~~~

Resource Server phải cấu hình issuer theo **định danh bên phát hành thực tế trong token**:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.test/realms/shop
~~~

Nếu metadata discovery từ public issuer không truy cập được trong mạng nội bộ, có thể chỉ rõ `jwk-set-uri` theo hợp đồng định tuyến an toàn, **vẫn giữ issuer-uri theo public iss**. Không tự chuyển `issuer-uri` thành `http://idp:8080/...` chỉ để kết nối thuận tiện.

Nên ưu tiên sửa cấu hình external issuer/base URL hoặc proxy headers của IdP để metadata, JWT `iss` và public host cùng một giá trị nhất quán.

### 11.2. Phân biệt realm/tenant

Một số IdP cấp mỗi tenant/realm một issuer:

~~~text
https://id.example.test/realms/company-a
https://id.example.test/realms/company-b
~~~

Resource Server chỉ tin company-a sẽ không chấp nhận token có `iss` là company-b trừ khi được cấu hình **multi-issuer** có chủ đích. Không kiểm tra bằng quy tắc `startsWith("https://id.example.test/realms/")` để tin mọi realm trên một domain.

Ngay cả khi hai tenant chia sẻ domain, các đường dẫn issuer thường biểu thị ranh giới tin cậy khác nhau. Cần có allowlist và validation theo từng issuer.

### 11.3. Các môi trường dev, staging, production

Ví dụ:

~~~text
Dev issuer:     https://id-dev.example.test/realms/shop
Staging issuer: https://id-stg.example.test/realms/shop
Prod issuer:    https://id.example.test/realms/shop
~~~

Token của dev không nên được API production chấp nhận chỉ vì có cùng tên scope hoặc subject. Mỗi môi trường cần issuer, key source và audience phù hợp. Đừng dùng một cấu hình nới lỏng cho phép issuer bất kỳ để “dễ chuyển môi trường”.

### 11.4. Hệ thống thật sự có nhiều issuer

Nếu Orders API phải chấp nhận token từ nhiều Authorization Server, không thể chỉ thêm một giá trị `issuer-uri` rồi hy vọng nó tự chấp nhận nhiều `iss`.

Spring Security Servlet có cơ chế **`JwtIssuerAuthenticationManagerResolver`** với danh sách issuer tin cậy, ví dụ:

~~~java
import org.springframework.security.oauth2.server.resource.authentication.JwtIssuerAuthenticationManagerResolver;

JwtIssuerAuthenticationManagerResolver resolver =
    JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(
        "https://id.example.test/realms/company-a",
        "https://id.example.test/realms/company-b");

http.oauth2ResourceServer(oauth2 -> oauth2
    .authenticationManagerResolver(resolver)
);
~~~

Đoạn trên minh họa **chiến lược đa issuer** trong các phiên bản Spring Security hỗ trợ API này; nó là một cấu hình thay thế cho luồng single-issuer `jwt()` trực tiếp, không dùng để cộng thêm tùy tiện vào một chain không tương thích.

**Bảo mật:** resolver có thể cần nhìn `iss` trong token trước khi biết phải chọn issuer/manager nào. Ở thời điểm đó, `iss` chỉ là *routing hint chưa được xác minh*. Chỉ cho phép issuer thuộc **allowlist đáng tin**, rồi phải xác minh JWT bằng key/validator tương ứng với chính issuer đã chọn. Không tải metadata hoặc JWKS từ một `iss` bất kỳ do client gửi.

## 12. Thực hành: dự đoán kết quả với `issuer-uri`

Giả sử:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.test/realms/shop
          audiences:
            - orders-api
~~~

Endpoint yêu cầu xác thực:

~~~java
http.authorizeHttpRequests(auth ->
    auth.anyRequest().authenticated());
~~~

Các case:

| Trường hợp | JWT `iss` | JWT `aud` | Dự kiến |
|---|---|---|---|
| Đúng issuer, audience và validators | `https://id.example.test/realms/shop` | `orders-api` | Cho qua authentication |
| Sai realm | `https://id.example.test/realms/other` | `orders-api` | **401** |
| Thiếu issuer | Không có `iss` | `orders-api` | **401** |
| Issuer có slash cuối khác | `https://id.example.test/realms/shop/` | `orders-api` | **401** |
| Issuer đúng, audience sai | `https://id.example.test/realms/shop` | `billing-api` | **401** nếu audience validator hoạt động |
| Đúng issuer nhưng token hết hạn | Đúng | `orders-api` | **401** |
| Đúng issuer nhưng chữ ký sai | Đúng | `orders-api` | **401** |
| Đúng issuer, đúng audience, thiếu scope cho endpoint | Đúng | `orders-api` | Authentication thành công, có thể **403** khi authorization yêu cầu scope |
| Không có token tới endpoint bảo vệ | Không áp dụng | Không áp dụng | Thường **401** |

Không có một payload JSON nào trong bảng đủ để được chấp nhận mà thiếu signature hợp lệ. Kết quả “cho qua authentication” cũng không đảm bảo endpoint trả 200: còn có chính sách scope, role, tenant và business ownership.

### 12.1. Gửi request bằng curl

~~~bash
curl -i \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  https://api.example.test/api/orders
~~~

Dùng token test do issuer môi trường thử nghiệm phát hành. Nếu muốn kiểm thử `iss` sai mà vẫn có chữ ký hợp lệ, phải sử dụng một **issuer test riêng với khóa test và cấu hình tin cậy được kiểm soát** hoặc một decoder test có thiết kế cụ thể. Tự sửa JSON payload của JWT đang có sẽ làm chữ ký bị sai, không còn phân biệt được lỗi issuer với lỗi signature.

### 12.2. Một số phản hồi thường gặp

Token sai issuer thường bị Resource Server từ chối ở bước JWT validation. Phản hồi có thể là:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

Tùy handler, thông điệp có thể thêm hoặc bớt các thuộc tính. Không đưa chuỗi token, public/private key không cần thiết hoặc toàn bộ claims vào thông báo công khai.

Nếu token đã hợp lệ nhưng thiếu quyền endpoint:

~~~http
HTTP/1.1 403 Forbidden
~~~

Vì issuer validation là một phần **authentication**, lỗi issuer thuộc nhóm JWT không hợp lệ (thường 401), khác với trường hợp principal được xác thực nhưng không đủ scope/role (thường 403).

## 13. Chẩn đoán cấu hình khi token thật không được chấp nhận

### 13.1. “Token có chữ ký đúng nhưng vẫn 401”

Kiểm tra tuần tự:

1. Spring Security có chọn đúng `SecurityFilterChain` bật Resource Server hay không?
2. Header có `Authorization: Bearer <token>` đúng hợp đồng không?
3. `issuer-uri` có **khớp chính xác** `iss` trong access token được phát hành không?
4. Metadata discovery có trả đúng issuer và `jwks_uri` không?
5. Decoder có lấy đúng signing public key và thuật toán được phép không?
6. `exp`/`nbf` và clock skew có phù hợp không?
7. `aud` có dành cho API không?
8. Token có thật sự là **OAuth 2.0 access token** thay vì OIDC ID Token không?

Chỉ xem chữ ký hoặc decode payload bằng công cụ Base64URL không đủ để kết luận token hợp lệ.

### 13.2. “Issuer URI giống nhau nhưng khác slash”

Ví dụ:

~~~text
Configured: https://id.example.test/realms/shop
JWT iss:    https://id.example.test/realms/shop/
~~~

Đây là hai giá trị khác nhau theo so sánh issuer. Cần sửa cấu hình hoặc phía Authorization Server để chúng thống nhất. Không tạo validator chấp nhận cả hai chỉ để bỏ qua việc lệch cấu hình, trừ khi thực sự có **hai issuer được cho phép** và thiết kế multi-issuer rõ ràng.

### 13.3. “JWKS truy cập được nhưng JWT vẫn lỗi issuer”

JWKS đáp ứng là điều kiện để tìm public key, **không chứng minh claim `iss` khớp**. Một token được ký hợp lệ vẫn bị từ chối nếu issuer claim không đúng. Kiểm tra `issuer-uri` và provider metadata, sau đó kiểm tra scope và audience riêng.

### 13.4. “Chỉ khai báo `jwk-set-uri` mà token từ issuer khác vẫn vào”

Nếu không có issuer validator thì decoder có thể chỉ kiểm tra chữ ký và các điều kiện thời gian. Cần thêm `issuer-uri` cùng JWKS hoặc `JwtValidators.createDefaultWithIssuer(...)` khi tự tạo decoder.

Không sửa bằng cách lấy issuer từ token rồi tạo validator **theo chính giá trị token gửi**; như vậy mọi `iss` tự tuyên bố đều có thể vượt kiểm tra issuer.

### 13.5. “Ứng dụng không gọi metadata ở startup”

Điều này có thể hoàn toàn đúng với **lazy discovery** trong phiên bản Spring Security hiện hành. Khởi động được không tự chứng minh endpoint discovery/JWKS đã sẵn sàng cho request đầu tiên. Cần quan sát cả **thời điểm request xác thực đầu tiên** và tình trạng cache/khóa.

Ngược lại, khi ứng dụng tự gọi `JwtDecoders.fromIssuerLocation` lúc tạo bean, metadata có thể được truy vấn sớm. Không áp một kỳ vọng startup duy nhất cho tất cả phiên bản/cách cấu hình.

### 13.6. “Sau khi key rotation, token mới không xác minh được”

Public key mới có thể chưa sẵn sàng trong JWKS/cache. Cần xem `kid` trong JWS header, khóa do issuer công bố, cấu hình allowed JWS algorithms và khả năng refresh JWKS. Không vô hiệu hóa issuer/signature validation để cho token mới qua.

### 13.7. “Token từ staging vô tình gọi production API”

Nếu production Resource Server tin issuer staging (hoặc không kiểm tra issuer) và audience cũng chưa ràng buộc chặt, có nguy cơ lẫn môi trường. Cần xác định issuer và audience theo môi trường và kiểm tra cả hai; không chỉ so tên client hay scope.

## 14. Vận hành và giới hạn tin cậy

### 14.1. URI của issuer là cấu hình bảo mật

Không nhận `issuer-uri` từ request header, query parameter hoặc từ claim `iss` chưa được kiểm tra. Với single-issuer API, giá trị issuer nên nằm trong cấu hình có kiểm soát.

Với multi-issuer, dùng **allowlist** và quy tắc phân tenant đã thiết kế; không tự dựng URL metadata theo token do client đưa.

### 14.2. Chỉ tin metadata và JWKS từ nguồn được cho phép

Discovery dùng endpoint của issuer đã cấu hình hoặc nhà cung cấp theo hợp đồng. Kết nối nên có HTTPS và cơ chế xác thực chứng chỉ đúng; tránh redirect/URL tự do đến các host không đáng tin làm phát sinh nguy cơ SSRF hoặc key substitution.

Trường `kid` trong JWT giúp chọn key từ nguồn đã tin cậy; nó không cấp quyền tải public key từ URL bất kỳ do token quảng bá.

### 14.3. Không vô tình làm mất issuer validator

Nếu thay thế auto-configured decoder bằng bean tùy chỉnh, hãy giữ validator issuer và timestamp, rồi mới thêm validator khác. Khi dùng `setJwtValidator(...)`, phải nhớ đây là **thay thế validator đã đặt** trên decoder chứ không tự động cộng dồn mọi logic trước đó.

### 14.4. Không dùng issuer để thay thế quyền dữ liệu

Issuer xác định bên phát hành, không nói rằng một người dùng được xem tất cả dữ liệu do issuer đó cấp. API vẫn cần kiểm tra `aud`, scope/authorities, tenant, owner và chính sách domain.

### 14.5. Khác biệt access token và ID Token

Một ID Token OIDC có thể mang `iss` đúng với cùng IdP. Nhưng `aud` của ID Token thường là **OIDC client ID**, không phải Resource Server. Chỉ kiểm tra `iss` là chưa đủ để ngăn việc chấp nhận nhầm ID Token.

Dùng access token dành cho API; áp dụng audience và token profile theo hợp đồng phát hành.

## 15. Bảng câu hỏi khi triển khai issuer mới

| Câu hỏi | Cần xác nhận ở đâu? |
|---|---|
| Giá trị issuer chính xác là gì? | Metadata của Authorization Server/IdP và claim `iss` trên access token được cấp |
| Issuer có slash cuối không? | So khớp nguyên chuỗi ở token, metadata, cấu hình |
| Discovery endpoint nào được hỗ trợ? | OIDC Provider Configuration hoặc RFC 8414 metadata |
| `jwks_uri` thật là gì? | Metadata của issuer hoặc tài liệu IdP |
| API có cần khởi động mà không truy cập metadata không? | Cân nhắc `issuer-uri` + `jwk-set-uri` và phiên bản Spring Security |
| JWT dùng thuật toán ký nào? | Hợp đồng token, JWS header và cấu hình allowed algorithms |
| Audience hợp lệ của API là gì? | Hợp đồng Resource Server, thường ràng buộc qua `audiences` hoặc validator |
| API nhận một hay nhiều issuer? | Kiến trúc single-issuer hay allowlist multi-issuer |
| Claim `iss` không khớp thì sao? | Authentication thất bại; thường HTTP 401 |
| Chính sách key rotation thế nào? | IdP/JWKS, caching và vận hành Resource Server |
| Endpoint nào đòi scope gì? | `SecurityFilterChain`, method security, business policy |

Tài liệu tích hợp nên ghi rõ **giá trị issuer nguyên văn**. Một dòng như “issuer: máy chủ IdP của công ty” không đủ để cấu hình `issuer-uri` chính xác.

## 16. Ghi nhớ

- **`issuer-uri`** cấu hình **Authorization Server/issuer mà Resource Server tin cậy**.
- Spring Security dùng issuer đó để **discovery metadata/JWKS** khi phù hợp, đồng thời kiểm tra **JWT claim `iss`** với issuer đã cấu hình.
- **`iss` phải khớp giá trị dự kiến**; realm khác, scheme khác hoặc dấu `/` cuối khác có thể làm JWT bị từ chối.
- **JWKS URI** cung cấp public keys; nó **không phải issuer**. Chỉ cấu hình `jwk-set-uri` mà thiếu issuer validator có thể bỏ qua kiểm tra `iss`.
- Khai báo **cả `issuer-uri` và `jwk-set-uri`** là cách giữ issuer validation trong khi chỉ rõ vị trí public keys.
- Khi tự cung cấp `JwtDecoder`, phải **gắn/giữ validator issuer và thời gian**; thêm audience và claim validators theo hợp đồng API.
- **Kiểm tra issuer không thay thế kiểm tra audience, chữ ký, thời hạn, token type hoặc quyền nghiệp vụ**.
- Với hệ thống đa issuer, dùng **allowlist và resolver chuyên dụng**; không tin issuer tùy ý do token chưa xác minh cung cấp.
- Lỗi `iss` thường là **authentication failure → 401**, còn token hợp lệ thiếu quyền thường là **authorization failure → 403**.

### Tài liệu tham khảo

- [Spring Security Reference — OAuth 2.0 Resource Server JWT (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security Reference — OAuth 2.0 Resource Server Multi-tenancy](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/multitenancy.html)
- [Spring Boot Reference — OAuth2 Resource Server](https://docs.spring.io/spring-boot/reference/security/oauth2.html)
- [Spring Security API — JwtDecoders](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/JwtDecoders.html)
- [Spring Security API — JwtValidators](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/JwtValidators.html)
- [Spring Security API — JwtIssuerValidator](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/JwtIssuerValidator.html)
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414)
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)

