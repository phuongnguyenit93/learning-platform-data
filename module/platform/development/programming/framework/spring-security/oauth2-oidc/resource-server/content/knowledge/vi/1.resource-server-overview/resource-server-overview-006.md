# JWT, opaque token và lựa chọn cách xác minh trong Spring Security OAuth 2.0 Resource Server

Một **Resource Server** là API nhận access token do **Authorization Server** phát hành và quyết định một yêu cầu có được truy cập tài nguyên hay không. Hai cách xử lý bearer access token thường gặp là **tự xác minh JWT** và **gọi introspection endpoint để kiểm tra token**. Sự khác biệt này tác động trực tiếp đến độ trễ, khả năng thu hồi quyền truy cập, tính sẵn sàng và ranh giới tin cậy của hệ thống.

Điều cần phân biệt ngay từ đầu: **JWT và opaque token mô tả cách token được biểu diễn; xác minh cục bộ và introspection mô tả cách Resource Server kiểm tra token**. JWT thường được xác minh cục bộ bằng chữ ký số; opaque token thường cần introspection. Tuy nhiên một JWT hoàn toàn có thể được gửi tới introspection endpoint nếu hệ thống muốn xác nhận trạng thái còn hiệu lực từ Authorization Server.

## 1. Resource Server đứng ở đâu trong luồng OAuth 2.0?

Các thành phần chính:

- **Client**: ứng dụng web, mobile hoặc dịch vụ gọi API.
- **Authorization Server (AS)**: xác thực/cấp quyền theo luồng OAuth 2.0 phù hợp và phát hành access token.
- **Resource Server (RS)**: API bảo vệ tài nguyên; xác minh token và áp dụng quyền truy cập cho từng endpoint.

Luồng tổng quát:

~~~text
  Client                    Authorization Server                  Resource Server
    |                                |                                   |
    |--- xin/cấp access token ------>|                                   |
    |<--------- access token --------|                                   |
    |                                                                    |
    |------------- GET /api/orders ------------------------------------->|
    |             Authorization: Bearer <access_token>                   |
    |                                                                    |
    |                     RS xác minh token và xét quyền                 |
    |<------------------- 200 / 401 / 403 -------------------------------|
~~~

Resource Server **không nên tin token chỉ vì request gửi kèm header `Authorization: Bearer ...`**. Nó phải xác định token hợp lệ, được phát hành từ nguồn tin cậy, dành cho đúng API và có quyền phù hợp.

**Phân biệt access token với ID token của OpenID Connect (OIDC):**

- **Access token** dành cho Resource Server; dùng để gọi API theo phạm vi quyền được cấp.
- **ID token** dành cho OIDC Client (relying party), chứng minh thông tin về phiên xác thực của người dùng cho Client. Không thay ID token vào header Bearer để bảo vệ API.
- ID token thường là JWT, nhưng **định dạng JWT không biến một token thành access token**. Cần xem mục đích, issuer, audience, token type và hợp đồng với nhà cung cấp định danh.

### Xác thực token và phân quyền là hai quyết định khác nhau

Một token có thể được xác minh thành công nhưng không được phép thực hiện một thao tác cụ thể. Ví dụ:

- JWT có chữ ký hợp lệ, chưa hết hạn và dành cho `orders-api`: **xác thực token thành công**.
- Token chỉ có scope `orders.read` nhưng client gửi `POST /api/orders` đòi `orders.write`: **phân quyền thất bại**.

Trong HTTP API, kết quả thường được thể hiện là **401 Unauthorized** khi không có thông tin xác thực hợp lệ và **403 Forbidden** khi đã xác thực nhưng thiếu quyền. Cách ánh xạ lỗi thực tế phụ thuộc cấu hình và đường xử lý exception.

## 2. JWT access token: cấu trúc và ý nghĩa

**JWT (JSON Web Token)** là định dạng biểu diễn các claim dưới dạng JSON. JWT thường thấy dưới dạng JWS compact gồm ba phần, được nối bởi dấu chấm:

~~~text
BASE64URL(header).BASE64URL(payload).BASE64URL(signature)
~~~

Ví dụ nội dung khi giải mã hai phần đầu (chỉ minh họa, không phải token thực có thể xác minh):

~~~json
{
  "alg": "RS256",
  "kid": "signing-key-2026-01",
  "typ": "at+jwt"
}
~~~

~~~json
{
  "iss": "https://idp.example.com/realms/shop",
  "sub": "user-123",
  "aud": ["orders-api"],
  "iat": 1794700000,
  "nbf": 1794700000,
  "exp": 1794703600,
  "scope": "orders.read orders.write",
  "client_id": "shop-web"
}
~~~

Một số claim đặc biệt quan trọng:

| Claim | Ý nghĩa | Quy tắc kiểm tra điển hình |
|---|---|---|
| `iss` | Bên phát hành token (issuer) | Phải trùng issuer mà API tin cậy |
| `sub` | Chủ thể gắn với token | Dùng làm định danh theo hợp đồng của AS; không tự suy ra quyền |
| `aud` | Tài nguyên/dịch vụ nhận token | Phải chứa định danh API hiện tại |
| `exp` | Thời điểm hết hạn (Unix timestamp) | Token hết hạn phải bị từ chối |
| `nbf` | Thời điểm bắt đầu hiệu lực | Không chấp nhận trước thời điểm này |
| `iat` | Thời điểm phát hành | Hữu ích cho chính sách thời gian và quan sát |
| `scope` / `scp` | Quyền được cấp | Cần chuyển đổi đúng quy ước của AS |
| `client_id` | Client được cấp token (nếu có) | Có thể áp dụng thêm chính sách theo client |

**Không phải mọi access token dạng JWT đều chứa đúng bộ claim trên.** Các claim cụ thể và cấu trúc `scope`/`scp` thay đổi theo Authorization Server và profile token. Một số hệ thống có thêm `roles`, `groups`, `tenant_id` hoặc claim riêng. Resource Server phải có hợp đồng rõ ràng thay vì tự đoán.

### JWT được ký, không mặc nhiên được mã hóa

Với JWS, header và payload chỉ được **Base64URL encode**. Người nắm được token có thể đọc những dữ liệu trong đó. Chữ ký giúp phát hiện sửa đổi, nhưng **không che giấu thông tin**. Không đưa mật khẩu, bí mật, thông tin cá nhân nhạy cảm hoặc dữ liệu không cần thiết vào claim của access token.

JWT có thể được mã hóa bằng JWE, nhưng đó là một cơ chế riêng; cấu hình JWT Resource Server thông thường tập trung vào JWT có chữ ký.

### Chữ ký bất đối xứng và JWK Set

Trong mô hình phổ biến, AS ký JWT bằng **private key** (ví dụ RSA hoặc EC), còn RS dùng **public key** tương ứng để kiểm tra chữ ký. Các public key thường được công bố tại **JWK Set URI (JWKS)**. Header `kid` giúp chọn khóa phù hợp từ tập khóa.

~~~text
Authorization Server                        Resource Server
       |                                          |
       | -- JWT được ký bằng private key -------> |
       |                                          | -- lấy/cache JWKS từ AS
       | <------------ (public keys) ------------ |
       |                                          | -- chọn public key theo kid
       |                                          | -- xác minh chữ ký + claim
~~~

Cách này không yêu cầu Resource Server sở hữu private key của Authorization Server. Khi AS xoay khóa ký, Resource Server có thể nạp các public key mới từ JWKS theo cơ chế cache/refresh của decoder.

**Không được xem `alg`, `kid` hoặc URL trong JWT header là cấu hình đáng tin cậy từ phía client.** Chính sách thuật toán, issuer và địa chỉ lấy khóa phải được cấu hình từ nguồn tin cậy. Không chấp nhận token unsigned (`alg: none`), không tùy tiện dùng khóa do token tự chỉ định.

## 3. Resource Server xác minh JWT cục bộ như thế nào?

Giả sử API nhận:

~~~http
GET /api/orders HTTP/1.1
Host: api.example.com
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
~~~

Một quy trình kiểm tra an toàn về mặt khái niệm gồm:

1. **Lấy bearer token** từ vị trí được chấp nhận, thông thường là header `Authorization`.
2. **Giải mã cấu trúc** JWT để xác định loại token và định dạng hợp lệ.
3. **Kiểm tra thuật toán và chữ ký** với public key thuộc issuer đã cấu hình; không dùng khóa/issuer do client tùy ý cung cấp.
4. **Kiểm tra claim thời gian** như `exp` và `nbf`, với mức sai lệch đồng hồ (clock skew) được kiểm soát.
5. **Kiểm tra issuer** (`iss`) và **audience** (`aud`) tương ứng với API.
6. **Áp dụng chính sách bổ sung** nếu cần: token type, tenant, client, yêu cầu MFA hoặc ràng buộc ứng dụng.
7. **Chuyển scope/claim thành authority** rồi kiểm tra endpoint hoặc method đang truy cập.

Các kiểm tra thực tế do Spring Security và validator được cấu hình thực hiện; danh sách trên là mô hình để phân biệt trách nhiệm. Nếu đã xác minh chữ ký nhưng bỏ qua `aud`, một JWT hợp lệ dành cho API A vẫn có nguy cơ được gửi sang API B trong cùng hệ sinh thái.

### JWT không cần gọi AS trên mỗi request

Khi đã có public key phù hợp trong cache, Resource Server có thể xác minh JWT mà không cần liên hệ Authorization Server cho từng request. Đây là lợi thế về độ trễ, lưu lượng và khả năng chịu lỗi kết nối.

Đổi lại, **chữ ký hợp lệ không tự chứng minh token chưa bị thu hồi**. Token có thể vẫn đạt kiểm tra chữ ký và `exp` dù người dùng vừa đăng xuất, bị khóa hoặc quyền truy cập vừa bị rút. Nếu hệ thống chỉ xác minh JWT cục bộ, các thay đổi đó thường có hiệu lực muộn nhất khi token hết hạn, trừ khi có cơ chế bổ sung như danh sách thu hồi, kiểm tra trạng thái hoặc cấp token sống ngắn.

## 4. Opaque token: xác minh bằng introspection

**Opaque token** là một chuỗi mà Resource Server **không cần biết cấu trúc bên trong**. Nó thường là giá trị ngẫu nhiên đóng vai trò tham chiếu tới dữ liệu ở Authorization Server.

~~~text
Authorization: Bearer 8f25e86a3b6d4e48b907f20e92a5f...
~~~

Không thể xác định hạn sử dụng, chủ thể hay quyền chỉ bằng cách cắt chuỗi và giải mã nó. Resource Server thường gọi **OAuth 2.0 Token Introspection** (RFC 7662) qua backchannel server-to-server:

~~~text
Client                          Resource Server               Authorization Server
  |                                   |                                |
  |-- Bearer opaque token ----------->|                                |
  |                                   |-- POST /introspect ------------>|
  |                                   |   token + xác thực của RS       |
  |                                   |<-- active, scope, sub, ... -----|
  |                                   |                                |
  |                                   |-- xét quyền và xử lý request    |
  |<------------ 200/401/403 ---------|                                |
~~~

Ví dụ HTTP request từ Resource Server tới AS:

~~~http
POST /oauth2/introspect HTTP/1.1
Host: idp.example.com
Authorization: Basic <credentials-of-resource-server>
Content-Type: application/x-www-form-urlencoded

token=<access_token>
~~~

Ví dụ response cho token còn hiệu lực:

~~~json
{
  "active": true,
  "sub": "user-123",
  "client_id": "shop-web",
  "scope": "orders.read orders.write",
  "aud": ["orders-api"],
  "iss": "https://idp.example.com/realms/shop",
  "exp": 1794703600
}
~~~

Response cho token không còn hiệu lực có thể đơn giản là:

~~~json
{
  "active": false
}
~~~

**`active: true` là kết luận của Authorization Server về trạng thái token tại thời điểm introspection.** Resource Server vẫn phải áp dụng chính sách của chính API, đặc biệt audience, scope và các điều kiện nghiệp vụ nếu có. Không nên cho rằng mọi AS đều trả cùng tập claim; chỉ sử dụng thông tin thực tế mà AS cam kết trả về.

### Tại sao introspection có thể đáp ứng yêu cầu thu hồi nhanh?

AS có thể kiểm tra token đã bị thu hồi, hết hạn, bị vô hiệu do thay đổi tài khoản hoặc chính sách. Nếu Resource Server gọi introspection ở mỗi request, lần gọi tiếp theo sẽ nhìn thấy quyết định mới của AS.

Khả năng này có chi phí: một cuộc gọi mạng bổ sung, tài nguyên của endpoint introspection, bảo mật client credentials, timeout và phụ thuộc vào tính sẵn sàng của AS. Nếu cache kết quả introspection để giảm tải, **thời gian hiệu lực của cache cũng là khoảng trễ tối đa có thể xuất hiện khi thu hồi token**, tùy chính sách cache và cách vô hiệu hóa cache.

### Opaque token không có nghĩa là yếu bảo mật

Một chuỗi token ngẫu nhiên đủ entropy, chỉ được truyền qua TLS, lưu giữ đúng cách và kiểm tra với AS có thể có tính bảo mật rất tốt. Ngược lại, JWT có chữ ký mạnh nhưng thiếu `aud`, cấu hình khóa sai hoặc sống quá lâu vẫn tạo rủi ro. Sự an toàn đến từ toàn bộ cơ chế xác thực, phân quyền, vòng đời token và vận hành, không chỉ từ vẻ ngoài của token.

## 5. JWT, opaque token và introspection khác nhau ở đâu?

| Khía cạnh | JWT xác minh cục bộ | Token được xác minh qua introspection |
|---|---|---|
| Cách xác minh | Kiểm tra chữ ký và claim bằng khóa tin cậy | Hỏi AS về trạng thái và thuộc tính token |
| Token đầu vào | Thường là JWT có chữ ký | Opaque token **hoặc JWT** mà AS hỗ trợ introspect |
| Độ trễ thông thường | Thấp sau khi có khóa trong cache | Có thêm kết nối mạng tới introspection endpoint |
| Phụ thuộc AS khi xử lý request | Thường chỉ cần AS lúc khám phá metadata/lấy hoặc cập nhật khóa | Cần AS khi introspect, trừ khi cache kết quả |
| Thu hồi trước hạn | Không tức thời nếu chỉ xác minh cục bộ | Có thể nhanh khi AS phản ánh thu hồi và không cache lâu |
| Dữ liệu lộ trong token | Payload JWS có thể đọc được | Nội dung token có thể không tự bộc lộ claim |
| Khả năng mở rộng | Tốt cho lưu lượng lớn và nhiều RS | Cần năng lực xử lý introspection tương ứng |
| Thay đổi quyền giữa thời hạn token | Claim cũ còn trong JWT cho tới khi hết hạn hoặc có kiểm tra thêm | AS có thể trả trạng thái/quyền cập nhật theo thiết kế |
| Xử lý sự cố kết nối AS | Token với khóa đã cache có thể tiếp tục được xác minh | Request có thể không xác thực được nếu endpoint unreachable |
| Vận hành | Quản lý JWKS, key rotation, TTL, validator | Quản lý introspection, client credentials, timeout, cache |

Đây không phải phép so sánh “JWT an toàn hơn opaque” hay ngược lại. Nó là đánh đổi giữa **xác minh phân tán** và **quyết định trạng thái tập trung**.

## 6. Cấu hình Spring Boot Resource Server dùng JWT

Các ví dụ sau áp dụng cho **ứng dụng servlet Spring MVC** với Spring Security hiện đại và cấu hình bằng `SecurityFilterChain`. Khi dùng WebFlux, thay bằng các thành phần reactive tương ứng.

### 6.1. Khai báo dependencies

Trong dự án Spring Boot dùng Gradle, thêm các starter cần thiết:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

Starter Resource Server thông thường đưa vào các thành phần cần thiết để xử lý JWT. Nếu khai báo trực tiếp từng module Spring Security thay vì starter, hỗ trợ JWT cần cả `spring-security-oauth2-resource-server` và `spring-security-oauth2-jose`.

### 6.2. Chỉ định issuer và audience

Ví dụ `application.yml` cho một `orders-api` tin issuer cố định:

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

- `issuer-uri` xác định giá trị `iss` hợp lệ và cho phép Spring tìm thông tin cấu hình AS/JWKS qua endpoint metadata mà AS hỗ trợ.
- `audiences` yêu cầu token có audience phù hợp với Resource Server. Thuộc tính này có ở Spring Boot hiện đại; với phiên bản cũ chưa hỗ trợ, phải cấu hình `OAuth2TokenValidator<Jwt>` riêng.
- Các giá trị minh họa cần được thay bằng issuer và audience thực do AS cấp, không sao chép máy móc.

Nếu cần chỉ rõ JWKS (chẳng hạn AS không công bố metadata chuẩn), có thể cấu hình cả hai:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.com/realms/shop
          jwk-set-uri: https://idp.example.com/realms/shop/protocol/openid-connect/certs
          audiences:
            - orders-api
~~~

`jwk-set-uri` phải là địa chỉ đáng tin cậy do nhà cung cấp định danh công bố, không phải một URL được lấy tùy ý từ JWT. Giữ `issuer-uri` giúp tiếp tục kiểm tra `iss`. Cơ chế lấy metadata/khóa và thời điểm xảy ra có thể thay đổi theo phiên bản và cấu hình; kiểm tra theo stack đang vận hành.

### 6.3. Bảo vệ endpoint theo scope

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.config.Customizer;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/actuator/health").permitAll()
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

Ví dụ này mô tả endpoint chỉ dùng bearer token, không dùng session để xác thực. Với API không sử dụng cookie để tự động xác thực request, có thể xem xét cấu hình CSRF phù hợp; đừng tắt CSRF vô điều kiện nếu ứng dụng còn phục vụ web session hoặc luồng browser dựa trên cookie.

Với JWT có claim:

~~~json
{
  "scope": "orders.read orders.write"
}
~~~

Spring Security mặc định thường chuyển scope thành authority có tiền tố `SCOPE_`, tức `SCOPE_orders.read` và `SCOPE_orders.write`. Vì vậy cấu hình trên không viết trực tiếp `hasAuthority("orders.read")`.

**Lưu ý:** `roles`, `groups` hoặc các claim quyền tùy biến từ IdP không tự động trở thành `ROLE_ADMIN`. Nếu cần mapping đặc biệt, cấu hình `JwtAuthenticationConverter` tương ứng và đặt chính sách rõ ràng.

### 6.4. Lấy thông tin chủ thể đã xác thực

Trong nhánh JWT, có thể lấy principal với `@AuthenticationPrincipal Jwt`:

~~~java
package com.example.orders.api;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
@RequestMapping("/api/me")
public class MeController {

    @GetMapping
    public Map<String, Object> me(@AuthenticationPrincipal Jwt jwt) {
        return Map.of(
            "subject", jwt.getSubject(),
            "issuer", jwt.getIssuer().toString()
        );
    }
}
~~~

Đoạn này giả định token đã được xác thực và `iss` tồn tại theo contract. Chỉ trả các thông tin cần thiết cho client; tránh trả toàn bộ claim hoặc nguyên token trong API response. Với opaque token, principal có kiểu khác (xem phần tiếp theo), nên không dùng nguyên ví dụ controller JWT cho cả hai chế độ.

## 7. Cấu hình Resource Server dùng opaque token

### 7.1. Chỉ định introspection endpoint và thông tin xác thực

Cùng starter Resource Server, cấu hình introspection như sau:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://idp.example.com/oauth2/introspect
          client-id: ${INTROSPECTION_CLIENT_ID}
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
~~~

Đây là **cấu hình thay thế** cấu hình JWT của ví dụ trước, có thể đặt trong profile riêng; không trộn hai cơ chế chỉ bằng cách khai báo đồng thời hai nhóm thuộc tính mà không định nghĩa rõ SecurityFilterChain.

- `introspection-uri`: endpoint thật của AS theo tài liệu IdP.
- `client-id` và `client-secret`: định danh/thông tin bí mật để RS xác thực khi gọi introspection; **khác với bearer token của người gọi API**.
- Cấp secret qua secret manager hoặc biến môi trường; không commit credential vào repository.
- Giao tiếp RS ↔ AS phải sử dụng HTTPS có kiểm tra chứng chỉ.

### 7.2. SecurityFilterChain cho introspection

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
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.opaqueToken(Customizer.withDefaults()));

        return http.build();
    }
}
~~~

Ở chế độ này, Spring Security dùng `OpaqueTokenIntrospector` để kiểm tra token. Khi AS trả `active: true` và danh sách scope hợp lệ, mặc định Spring ánh xạ scope thành authority có tiền tố `SCOPE_`. Do đó các rule `hasAuthority` nói trên có thể giữ giống nhánh JWT.

Một response introspection có `active: true` nhưng không có scope `orders.write` vẫn không đủ quyền cho `POST /api/orders`.

### 7.3. Đọc principal từ introspection

~~~java
package com.example.orders.api;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
@RequestMapping("/api/me")
public class MeController {

    @GetMapping
    public Map<String, Object> me(
            @AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal) {
        return Map.of("subject", principal.getName());
    }
}
~~~

Với opaque token, `Authentication#getPrincipal()` mặc định là `OAuth2AuthenticatedPrincipal`; tên chủ thể thường được lấy từ `sub` nếu AS trả về. Nếu contract AS không có `sub`, cần thống nhất cách xác định danh tính, không mặc định rằng tên này là email hoặc username.

### 7.4. JWT cũng có thể được introspect

Giả sử AS phát hành access token có dạng JWT nhưng doanh nghiệp yêu cầu khóa token ngay khi phát hiện thiết bị bị đánh cắp. Nếu AS hỗ trợ introspection cho JWT, Resource Server vẫn có thể cấu hình nhánh `opaqueToken` để **gửi nguyên chuỗi JWT cho introspection endpoint**.

Khi đó **JWT là định dạng token; introspection là phương thức xác minh**. Spring Security sẽ sử dụng kết quả introspection làm nguồn thông tin xác thực, thay vì mặc định giải mã JWT để lấy principal kiểu `Jwt`. Cần kiểm tra AS có hỗ trợ và trả đủ attribute cho chính sách quyền của API hay không.

## 8. Chọn phương án xác minh theo yêu cầu hệ thống

Không có lựa chọn tốt nhất cho mọi Resource Server. Có thể ra quyết định bằng các câu hỏi sau.

### Câu hỏi 1: Cần thu hồi token nhanh đến mức nào?

Nếu yêu cầu là **thu hồi quyền gần như ngay lập tức** (người dùng bị khóa, phiên có nguy cơ lộ, quyền truy cập tài chính bị rút), introspection là hướng phù hợp nếu AS hỗ trợ và hiệu năng cho phép. Cache introspection, nếu bật, cần TTL tương ứng với thời hạn thu hồi chấp nhận được.

Nếu API chấp nhận việc token hết hiệu lực sau một khoảng ngắn, JWT có **TTL ngắn** và không cấp quyền quá rộng có thể là lựa chọn đơn giản hơn. Logout phía client chỉ xóa token ở client; nó không mặc nhiên làm JWT đang lưu hành mất hiệu lực ở Resource Server.

### Câu hỏi 2: Độ trễ và lưu lượng request có nghiêm ngặt không?

Với API có lưu lượng lớn, nhiều instance, cần độ trễ thấp, xác minh JWT bằng khóa đã cache thường tiết kiệm một round-trip mạng trên mỗi request. Phải tính cả vòng đời key rotation và tình huống cần tải JWKS mới.

Introspection đặt thêm tải lên AS hoặc tầng introspection chuyên dụng. Nếu chọn phương án này, cần thiết kế timeout, pool kết nối, quota, cache phù hợp, giám sát lỗi và năng lực phục vụ của AS. Không nên tự động **fail open** (cho phép request khi không liên hệ được AS), vì nó biến sự cố kết nối thành lỗ hổng xác thực.

### Câu hỏi 3: Claim và quyền thay đổi thường xuyên hay không?

JWT tự chứa claim giúp RS tự quyết định nhanh, nhưng quyền được ghi trong JWT có thể trở nên cũ. Với quyền động, có thể:

- Dùng introspection để AS trả trạng thái/quyền theo chính sách cập nhật.
- Dùng JWT sống ngắn, để client lấy access token mới khi cần.
- Giữ JWT để xác thực, rồi hỏi dịch vụ quyền riêng cho các quyết định nhạy cảm.
- Thiết kế token chỉ mang định danh/scope thô, còn resource ownership được kiểm tra trong API.

Không nhầm scope `orders.read` với quyền đọc **mọi** đơn hàng. Resource Server thường còn phải kiểm tra đơn hàng có thuộc user/tenant phù hợp hay không.

### Câu hỏi 4: API có chấp nhận phụ thuộc vào Authorization Server theo từng request không?

Nếu yêu cầu là tiếp tục phục vụ request khi đường mạng tới AS bị gián đoạn, JWT có thể giúp RS xác minh các token đã phát hành bằng khóa có sẵn. Tuy nhiên việc này không xóa yêu cầu thiết kế key refresh, hạn token, token compromise và chính sách ứng xử khi không lấy được khóa.

Nếu yêu cầu an toàn ưu tiên trạng thái trung tâm mới nhất, có thể chấp nhận việc từ chối xử lý yêu cầu khi không introspect được token. Phải biểu diễn trường hợp AS lỗi rõ ràng trong giám sát, không gộp mọi sự cố vào “token sai”.

### Bảng chọn nhanh theo tình huống

| Tình huống | Cách khởi đầu nên cân nhắc | Vì sao |
|---|---|---|
| API đọc công khai có xác thực, lưu lượng lớn, token sống ngắn | JWT xác minh cục bộ | Giảm phụ thuộc mạng khi xử lý |
| API liên quan quyền nhạy cảm, cần thu hồi gần tức thời | Introspection | Trạng thái do AS quyết định tại thời điểm gọi |
| Microservices nội bộ tin cùng issuer, mỗi dịch vụ có audience riêng | JWT + xác minh `iss`, `aud`, scope | Phù hợp xác minh phân tán, ngăn token gửi nhầm API |
| API đối tác dùng token tham chiếu do IdP phát hành | Opaque + introspection | RS không cần hiểu cấu trúc token |
| JWT bắt buộc phải được kiểm tra revocation theo từng request | Introspection cho JWT | Định dạng JWT không cản trở kiểm tra trạng thái tập trung |
| Lưu lượng lớn **và** cần thu hồi nhanh | Thiết kế kết hợp có kiểm soát | Cân bằng TTL ngắn, cache/denylist hoặc kiểm tra nhạy cảm theo nhu cầu |

**Hướng tiếp cận thực tế:** bắt đầu từ hợp đồng access token của AS, yêu cầu thu hồi và SLA của API; sau đó mới chọn `jwt()` hay `opaqueToken()`.

## 9. Những điều phải kiểm tra ngoài chữ ký hoặc `active`

### 9.1. Audience phải dành cho đúng Resource Server

Giả sử cùng một issuer phát hành token cho `inventory-api` và `orders-api`. Token có `aud: ["inventory-api"]` không được tự động dùng trên `orders-api`, dù cùng `iss` và chữ ký đều hợp lệ.

Với JWT, thêm audience validator. Trong Spring Boot hỗ trợ `audiences`, có thể cấu hình trực tiếp như phần 6.2.

Với introspection, nếu response có `aud`, API nên áp dụng điều kiện audience theo hợp đồng với AS. Không được cho rằng kiểm tra `active` của introspector mặc định tự động áp dụng mọi policy audience/tenant riêng của dự án. Khi cần, bọc `OpaqueTokenIntrospector` bằng logic kiểm tra bổ sung hoặc cấu hình một bộ chuyển đổi xác thực/chính sách phân quyền tương ứng.

### 9.2. Đừng nhầm scope với vai trò, hoặc vai trò với quyền sở hữu dữ liệu

- `scope` như `orders.read` thường là quyền API được cấp cho client/token.
- `role` như `ADMIN` có thể là mô hình quyền của tổ chức hoặc ứng dụng.
- **Quyền sở hữu dữ liệu** là điều kiện trên một tài nguyên cụ thể, ví dụ khách A có thể đọc order A nhưng không đọc order B.

Các lớp này có thể đồng tồn tại. Một token có `SCOPE_orders.read` chưa đủ để truy vấn đơn hàng của người khác.

### 9.3. Tránh rò rỉ bearer token

Bearer token hoạt động theo nguyên tắc ai nắm token hợp lệ có thể dùng token, trừ khi có thêm cơ chế ràng buộc người sử dụng token. Vì vậy:

- Bắt buộc TLS từ client tới API và từ API tới introspection/JWKS endpoint.
- Không ghi nguyên bearer token vào log, exception, trace, analytics hoặc URL query parameter.
- Giữ access token sống phù hợp với mức rủi ro; hạn chế scope và audience.
- Bảo vệ refresh token và introspection client secret theo đúng vai trò của chúng.
- Nếu có cơ chế sender-constrained token như mTLS/DPoP, cần triển khai xác minh tương ứng; header Bearer đơn thuần không tự thực thi ràng buộc đó.

### 9.4. Khóa ký, cache và lệch đồng hồ

Với JWT, kế hoạch vận hành cần tính đến:

- **Key rotation**: AS có thể công bố khóa mới trước khi dùng để ký; RS cần cập nhật JWKS và vẫn xử lý được token cũ chưa hết hạn trong thời gian chuyển đổi.
- **Cache JWKS**: cache giúp giảm tải nhưng cần chiến lược refresh và xử lý `kid` mới.
- **Clock skew**: máy chủ lệch thời gian có thể từ chối token gần `nbf`/`exp`; đồng bộ thời gian và chỉ cho phép sai lệch nhỏ có chủ đích.
- **Thuật toán cho phép**: sử dụng những thuật toán đáng tin và đúng với AS; không để header token tự hạ chuẩn bảo mật.

Với introspection, cache response cần xác định rõ **trạng thái active được tin trong bao lâu**. Không cache quá `exp`; cũng phải xét giới hạn thu hồi và quyền động.

## 10. Đọc kết quả HTTP để khoanh vùng lỗi

Giả sử API quy định `GET /api/orders` cần `SCOPE_orders.read`.

| Yêu cầu | Dự kiến | Nơi cần xem |
|---|---|---|
| Không gửi `Authorization` | Thường 401 | Client có gửi bearer token không |
| JWT hỏng, sai chữ ký, hết hạn, sai issuer/audience | Thường 401 | Decoder, validator, JWKS, đồng hồ |
| Opaque token introspection trả `active: false` | Thường 401 | Trạng thái token tại AS |
| Token hợp lệ nhưng thiếu `orders.read` | Thường 403 | Mapping scope và rule phân quyền |
| Token hợp lệ, đúng scope nhưng không sở hữu resource | 403 hoặc 404 tùy chính sách API | Kiểm tra quyền trên dữ liệu |
| Introspection timeout hoặc AS lỗi | Phụ thuộc cách cấu hình/ánh xạ exception | Kết nối, TLS, credentials, timeout và trạng thái AS |

Ví dụ gọi API bằng `curl`:

~~~bash
curl -i \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  https://api.example.com/api/orders
~~~

Khi debug, nên phân biệt:

1. **Không xác thực được token:** token hết hạn, issuer/audience sai, khóa JWKS cũ, AS introspection báo inactive.
2. **Đã xác thực nhưng không đủ quyền:** thiếu scope, mapping authority khác quy ước, rule áp dụng sai endpoint.
3. **Sự cố phụ thuộc bên ngoài:** JWKS/introspection không truy cập được, DNS/TLS lỗi, secret sai hoặc AS quá tải.

Header phản hồi `WWW-Authenticate` có thể cung cấp thông tin về bearer error theo chuẩn, nhưng không nên tiết lộ dữ liệu nội bộ hoặc nguyên token trong thông báo lỗi.

## 11. Ví dụ quyết định kiến trúc cho hệ thống đặt hàng

Giả sử công ty có:

- `orders-api` cho ứng dụng mua hàng;
- `billing-api` xử lý thanh toán;
- IdP duy nhất phát hành access token cho cả hai;
- nhu cầu vô hiệu hóa tài khoản bị xâm nhập ngay lập tức đối với thao tác thanh toán.

Một thiết kế có thể là:

1. **Định nghĩa audience riêng** `orders-api` và `billing-api` để hai API không chấp nhận nhầm token của nhau.
2. `orders-api` dùng **JWT ngắn hạn** và xác minh cục bộ với issuer, audience, thời gian và scope phù hợp.
3. `billing-api` dùng **introspection** cho các thao tác nhạy cảm, với chính sách timeout và giám sát phụ thuộc AS rõ ràng. AS phải thực sự phản ánh thu hồi nhanh như yêu cầu.
4. Cả hai API đều kiểm tra **quyền trên từng tài nguyên**: khách hàng chỉ thao tác trên order/invoice được cấp quyền.
5. Nếu AS trả JWT cho cả hai, `billing-api` vẫn có thể introspect JWT nếu IdP hỗ trợ. Không cần ép AS phát hành chuỗi opaque chỉ để được introspection.

Điểm quyết định nằm ở **mục tiêu an toàn và vận hành của từng API**, không nằm ở việc toàn bộ hệ thống bắt buộc chỉ dùng duy nhất một dạng token.

## 12. Những hiểu nhầm cần tránh

**“JWT đã verify signature thì gọi API nào cũng được.”** Sai. Phải xác minh issuer, audience và các claim liên quan, sau đó kiểm tra quyền trên endpoint và dữ liệu.

**“Opaque token không có chữ ký nên kém an toàn.”** Không đúng. Opaque token thường dựa vào giá trị khó đoán và việc AS xác nhận trạng thái qua kênh tin cậy; cần đánh giá cơ chế end-to-end.

**“JWT không thể bị thu hồi.”** Không chính xác. JWT có thể bị từ chối qua introspection, denylist hoặc chính sách khác. Chỉ riêng **xác minh chữ ký cục bộ** không biết mọi sự kiện thu hồi diễn ra sau khi phát hành.

**“JWT chỉ dùng được với OAuth, opaque token chỉ dùng được với OIDC.”** Không đúng. OAuth 2.0 không bắt buộc access token là JWT; OIDC thêm các khái niệm danh tính như ID token. Định dạng access token tùy Authorization Server và hợp đồng hệ thống.

**“Introspection luôn kiểm tra tất cả quyền truy cập.”** Không đúng. `active: true` mới xác định trạng thái token theo AS; Resource Server vẫn chịu trách nhiệm áp dụng audience, scope và điều kiện của tài nguyên.

**“Nếu lỗi AS thì cứ chấp nhận request để tăng availability.”** Không an toàn. Mọi phương án degrade cần được thiết kế trước theo ranh giới tin cậy, không tự ý bỏ qua xác thực khi introspection thất bại.

## 13. Tài liệu chuẩn và tham khảo

- [Spring Security — OAuth 2.0 Resource Server JWT (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — OAuth 2.0 Resource Server Opaque Token (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html)
- [Spring Boot — OAuth2 Resource Server configuration](https://docs.spring.io/spring-boot/reference/security/oauth2.html)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)

Khi triển khai vào hệ thống thực tế, hãy đối chiếu cả phiên bản Spring Security/Spring Boot đang dùng và tài liệu của Authorization Server: endpoint metadata, JWKS, định dạng `scope`, audience, cách thu hồi và hợp đồng introspection có thể khác nhau giữa các nhà cung cấp.
