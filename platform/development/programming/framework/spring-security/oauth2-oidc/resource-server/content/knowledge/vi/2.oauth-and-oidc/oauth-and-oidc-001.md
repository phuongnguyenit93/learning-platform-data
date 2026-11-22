# OAuth 2.0 ủy quyền truy cập và OIDC bổ sung lớp danh tính

## 1. Bài toán: được phép truy cập khác với biết người dùng là ai

Giả sử ứng dụng bán hàng có giao diện web và API Spring Boot:

- Người dùng đăng nhập trên trình duyệt.
- Giao diện gọi `GET /api/orders` để đọc đơn hàng.
- API chỉ cho phép truy cập khi lời gọi mang quyền `orders.read`.
- Giao diện cần biết người dùng đang đăng nhập để hiển thị tên, email hoặc hồ sơ cá nhân.

Hai nhu cầu trên liên quan nhưng khác nhau:

- **OAuth 2.0** cung cấp mô hình **ủy quyền truy cập**: một ứng dụng (client) nhận quyền truy cập tài nguyên được bảo vệ qua **access token**. Quyền truy cập được giới hạn bởi đối tượng nhận token, phạm vi quyền, thời hạn và chính sách của Authorization Server.
- **OpenID Connect (OIDC)** xây dựng **lớp xác thực danh tính** trên OAuth 2.0: client có thể nhận **ID Token** theo quy ước chuẩn để biết kết quả xác thực của người dùng, cùng các cách lấy thông tin hồ sơ như **UserInfo Endpoint**.

> Điểm cốt lõi: **OAuth 2.0 trả lời “client được phép làm gì với tài nguyên?”; OIDC giúp client trả lời “người dùng vừa được xác thực là ai?”** Trong một hệ thống thực, cả hai có thể xuất hiện trong cùng một lần đăng nhập.

Trong ngữ cảnh **Spring Security OAuth 2.0 / OIDC Resource Server**, API Spring Boot thường đóng vai trò **Resource Server**: nó tiếp nhận access token, kiểm tra tính hợp lệ và áp dụng quyền truy cập. Resource Server **không cần nhận hoặc sử dụng ID Token để bảo vệ API**.

## 2. OAuth 2.0 là cơ chế cấp quyền truy cập

### 2.1. Bốn vai trò cơ bản

| Vai trò | Trách nhiệm | Ví dụ |
|---|---|---|
| **Resource Owner** | Chủ thể có quyền đối với tài nguyên | Người sở hữu danh sách đơn hàng |
| **Client** | Ứng dụng muốn truy cập tài nguyên | Web frontend, mobile app, backend-for-frontend |
| **Authorization Server (AS)** | Xác thực theo chính sách, cấp authorization code/access token | Máy chủ định danh hoặc cấp quyền |
| **Resource Server (RS)** | Lưu trữ API/tài nguyên, nhận và kiểm tra access token | Spring Boot `/api/orders` |

**Authorization Server** và **Resource Server** có thể là hai ứng dụng khác nhau. Một nhà cung cấp danh tính (Identity Provider, IdP) có thể đồng thời đảm nhận vai trò Authorization Server của OAuth 2.0 và **OpenID Provider (OP)** của OIDC.

**Access token** là thông tin ủy quyền để gọi Resource Server. Nó có thể ở dạng JWT hoặc chuỗi opaque (không có cấu trúc để client tự giải mã). OAuth 2.0 không bắt buộc access token phải là JWT và không quy định rằng client được suy luận danh tính người dùng bằng cách đọc nội dung access token.

### 2.2. Scope, audience và thời hạn

Ví dụ Authorization Server cấp access token có các thuộc tính logic:

- `scope = orders.read`: được đọc đơn hàng; `orders.write`: được ghi đơn hàng.
- `aud = orders-api`: token dành cho API đơn hàng.
- `exp`: thời điểm hết hạn.
- `iss`: bên phát hành token.
- `sub`: chủ thể của token (có thể là người dùng hoặc client tùy loại grant).

**Scope** mô tả quyền được cấp ở mức phạm vi; **audience** ràng buộc tài nguyên dự kiến nhận token. API cần vừa xác thực token hợp lệ, vừa quyết định quyền truy cập theo endpoint và, nếu cần, theo dữ liệu nghiệp vụ. Có `orders.read` không tự động có nghĩa là người dùng được xem *mọi* đơn hàng của người khác.

**Ví dụ cần kiểm tra thêm tại tầng nghiệp vụ:** token có `orders.read` nhưng API chỉ được trả những đơn hàng của `sub` tương ứng, trừ khi có quyền quản trị cụ thể.

### 2.3. OAuth 2.0 không luôn có người dùng tương tác

Với **Authorization Code + PKCE**, người dùng thường tham gia bước đăng nhập và chấp thuận quyền. Nhưng với **Client Credentials**, một dịch vụ backend có thể nhận access token để gọi dịch vụ khác mà không có người dùng đang đăng nhập.

Vì vậy, việc “có access token hợp lệ” **không đủ để kết luận rằng một con người vừa đăng nhập**. Đây là lý do cần phân biệt ủy quyền và xác thực danh tính.

## 3. OIDC thêm danh tính vào luồng OAuth 2.0

### 3.1. Scope `openid` và ID Token

Khi client yêu cầu scope `openid`, một luồng phù hợp OIDC cho phép client nhận **ID Token** theo quy chuẩn OIDC. ID Token thường là JWT đã ký, với các claim quan trọng:

| Claim | Ý nghĩa khi client kiểm tra ID Token |
|---|---|
| `iss` | OpenID Provider nào đã phát hành |
| `sub` | Định danh chủ thể trong phạm vi issuer |
| `aud` | Client ID được phép nhận ID Token |
| `exp` | Hạn dùng |
| `iat` | Thời điểm phát hành |
| `nonce` | Giá trị client gửi ban đầu (khi sử dụng), giúp gắn token với yêu cầu xác thực |
| `auth_time` | Thời điểm người dùng được xác thực, khi được yêu cầu/cung cấp |
| `email`, `name` | Claim hồ sơ tùy chọn, không thay thế định danh `sub` |

Client phải kiểm tra ID Token theo OIDC, bao gồm **chữ ký**, **issuer**, **audience**, **thời hạn**, và **nonce nếu nonce đã được gửi**. Một số tình huống có thêm kiểm tra `azp` và những quy tắc đặc thù của từng flow. Nên để thư viện OIDC đáng tin cậy xử lý các phép kiểm tra này thay vì tự kiểm tra vài trường JSON.

> **Không gửi ID Token làm Bearer token để gọi API.** ID Token chứng minh kết quả xác thực **cho client được ghi trong `aud`**; nó không phải giấy phép truy cập tài nguyên của API. Một ID Token có `aud = web-client` không được API `orders-api` chấp nhận chỉ vì chữ ký hợp lệ.

### 3.2. UserInfo và các scope hồ sơ

OIDC định nghĩa **UserInfo Endpoint** để client có thể dùng access token phù hợp lấy các claim hồ sơ. Các scope thường gặp:

- `openid`: bật ngữ nghĩa OIDC.
- `profile`: đề nghị các claim hồ sơ như tên, ảnh đại diện.
- `email`: đề nghị `email` và `email_verified`.
- `address`, `phone`: các nhóm claim tùy chọn khác.

Những scope này **không đồng nghĩa** với quyền truy cập API nghiệp vụ như `orders.read`. Bên cung cấp còn quyết định claim nào thực sự được trả dựa trên cấu hình và sự chấp thuận.

`sub` kết hợp `iss` thường là khóa định danh đáng tin cậy hơn email. Email có thể đổi, chưa được xác minh, hoặc tái sử dụng; `sub` có thể là *pairwise* khác nhau theo client/sector trong chính sách của nhà cung cấp.

### 3.3. Discovery và chuẩn hóa

OIDC hỗ trợ metadata tại endpoint dạng:

~~~text
https://id.example.test/realms/shop/.well-known/openid-configuration
~~~

Đường dẫn thực tế tùy cấu trúc issuer của IdP. Metadata mô tả những endpoint như `authorization_endpoint`, `token_endpoint`, `userinfo_endpoint` và `jwks_uri`. JWKS cung cấp các khóa công khai để ứng dụng xác minh JWT được ký bằng thuật toán bất đối xứng.

Spring Security Resource Server có thể dựa trên **issuer URI** để tìm metadata/JWKS phù hợp. Điều này không biến API thành một OIDC client; API vẫn sử dụng access token để kiểm soát truy cập.

## 4. Một lần đăng nhập, hai mục đích khác nhau

Luồng phổ biến cho ứng dụng web là **Authorization Code Flow với PKCE**. Giả định Authorization Server có hỗ trợ OIDC và cấp access token cho `orders-api`.

~~~mermaid
sequenceDiagram
    actor User as Người dùng
    participant Client as Web / BFF (OIDC Client)
    participant OP as Authorization Server / OP
    participant API as Spring Resource Server
    User->>Client: Chọn đăng nhập
    Client->>OP: /authorize: response_type=code, scope=openid orders.read, state, code_challenge, nonce
    OP->>User: Xác thực và xin chấp thuận (nếu cần)
    User-->>OP: Hoàn thành
    OP-->>Client: Redirect với code và state
    Client->>Client: Kiểm tra state
    Client->>OP: /token: code, redirect_uri, code_verifier (+ client authentication nếu cần)
    OP-->>Client: access_token và id_token (có thể có refresh_token)
    Client->>Client: Kiểm tra ID Token để xác nhận người dùng
    Client->>API: GET /api/orders + Bearer access_token
    API->>API: Kiểm tra chữ ký/hạn/issuer/audience/scope
    API-->>Client: 200 nếu được phép; 401/403 nếu không
~~~

**Các bước cần hiểu:**

1. Client tạo `state` để chống giả mạo yêu cầu ủy quyền; tạo `code_verifier` và `code_challenge` cho PKCE; với OIDC, có thể tạo `nonce` và kiểm tra lại trong ID Token.
2. Trình duyệt đi qua trang đăng nhập của Authorization Server, tránh để ứng dụng tự nhận mật khẩu.
3. Authorization Server trả **authorization code** thông qua redirect. Code chỉ có hiệu lực ngắn, dùng một lần và được đổi tại token endpoint.
4. Client nhận **ID Token** để xác thực danh tính trong phạm vi client và **access token** để gọi API.
5. Spring Resource Server chỉ sử dụng access token khi ra quyết định cho `/api/orders`.

Nếu ứng dụng là **BFF/confidential client**, backend giữ token và có thể dùng client authentication khi đổi code. Nếu là **SPA/public client**, không đưa client secret vào JavaScript; dùng PKCE và biện pháp bảo vệ token phù hợp. Chọn kiến trúc và vòng đời token dựa trên mô hình đe dọa thực tế.

## 5. Phân biệt các loại token

| Giá trị | Ai dùng chính? | Mục đích | Gửi đến đâu? |
|---|---|---|---|
| **Authorization code** | OAuth/OIDC client | Đổi lấy token, thường kết hợp PKCE | Token endpoint của Authorization Server |
| **Access token** | Resource Server | Chứng minh quyền gọi tài nguyên cụ thể | `Authorization: Bearer ...` khi gọi API |
| **ID Token** | OIDC client / Relying Party | Xác thực thông tin người dùng đã đăng nhập | Client, **không dùng làm token cho API** |
| **Refresh token** | Client phù hợp chính sách cấp phát | Lấy access token mới khi được phép | Token endpoint; bảo vệ và xoay vòng theo chính sách |

Hai payload JWT *minh họa* dưới đây cố ý có **audience khác nhau**. Đây chỉ là phần claim được trình bày để học, không phải token đã ký thật:

**Access token cho Resource Server:**

~~~json
{
  "iss": "https://id.example.test/realms/shop",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read orders.write",
  "exp": 2000000000
}
~~~

**ID Token cho web client:**

~~~json
{
  "iss": "https://id.example.test/realms/shop",
  "sub": "user-123",
  "aud": "web-client",
  "email": "user@example.test",
  "email_verified": true,
  "nonce": "nonce-do-client-tao",
  "iat": 1999999700,
  "exp": 2000000000
}
~~~

JWT thường chỉ **được mã hóa Base64URL và ký**, chứ **không mặc nhiên được mã hóa bí mật**. Vì thế không đặt mật khẩu, khóa riêng, thông tin nhạy cảm không cần thiết vào claim. Không chấp nhận thuật toán ký yếu/không được phép; xác minh chữ ký qua khóa và thuật toán đúng chính sách tin cậy.

## 6. Spring Security Resource Server xử lý access token như thế nào?

### 6.1. Chuẩn bị ứng dụng

Ví dụ Spring Boot sử dụng Spring Security và xác thực **JWT access token**. Thêm các starter tương ứng vào `build.gradle`:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

Nếu dùng Maven, dùng hai artifact tương đương với `spring-boot-starter-web` và `spring-boot-starter-oauth2-resource-server`; phiên bản được quản lý bởi Spring Boot BOM.

Cấu hình `application.yml` tối thiểu:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.test/realms/shop
~~~

`issuer-uri` phải trùng chính xác giá trị claim `iss` trên token. Tùy provider và cách ứng dụng khởi tạo, Spring sẽ dùng metadata của issuer để tìm JWKS và xác minh JWT. Đây là URI minh họa; khi triển khai thực tế phải thay bằng issuer của hệ thống định danh.

**Resource Server cần được cấu hình chấp nhận đúng access token của API.** Ngoài chữ ký, hạn và issuer, nên xác minh **audience = orders-api** và các ràng buộc token áp dụng cho hệ thống. Trường hợp access token là **opaque** thì dùng cơ chế introspection (`oauth2ResourceServer(...opaqueToken(...))`), không cấu hình JWT decoder cho opaque token.

### 6.2. SecurityFilterChain: bảo vệ endpoint theo scope

Tạo file `SecurityConfig.java`:

~~~java
package com.example.orders;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            // Chỉ áp dụng cho API stateless xác thực Bearer token,
            // không dựa vào cookie/session của trình duyệt.
            .csrf(csrf -> csrf.disable())
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

Khi JWT hợp lệ có claim `scope` chứa `orders.read`, Spring Security mặc định ánh xạ scope thành authority `SCOPE_orders.read` (tương tự với claim `scp` thuộc định dạng được hỗ trợ). Đó là lý do dùng `hasAuthority("SCOPE_orders.read")` chứ không so sánh tên người dùng hay đưa `openid` vào điều kiện phân quyền nghiệp vụ.

**Lưu ý về CSRF:** dòng vô hiệu hóa CSRF ở ví dụ chỉ phù hợp khi API thực sự xác thực bằng Bearer token ngoài cookie và không sử dụng cơ chế xác thực dựa trên session trình duyệt. Nếu hệ thống dùng cookie đăng nhập hoặc endpoint xử lý phiên trình duyệt, phải thiết kế bảo vệ CSRF tương ứng. CORS cũng cần cấu hình riêng theo nguồn frontend được phép; CORS không thay thế xác thực và phân quyền.

### 6.3. Đọc chủ thể đã xác thực trong controller

~~~java
package com.example.orders;

import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    @GetMapping
    public Map<String, String> myOrders(@AuthenticationPrincipal Jwt jwt) {
        // Ví dụ minh họa: phải áp dụng thêm kiểm tra quyền trên
        // từng đơn hàng và lọc dữ liệu theo người dùng thực tế.
        return Map.of("authenticatedSubject", jwt.getSubject());
    }
}
~~~

Với JWT, `jwt.getSubject()` lấy claim `sub` của access token. Nó **không phải ID Token**; controller đang đọc principal đã được xác thực bởi bộ lọc Resource Server. Việc trả dữ liệu theo `sub` chỉ là một bước của phân quyền theo đối tượng; trong hệ thống nhiều tenant cần thêm kiểm tra tenant và quyền sở hữu.

### 6.4. Xác minh audience bằng validator

Một access token có chữ ký hợp lệ do **cùng issuer** cấp nhưng dành cho API khác vẫn không nên được `orders-api` chấp nhận. Ví dụ cấu hình thêm `jwk-set-uri` và audience kỳ vọng:

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
    audience: orders-api
~~~

Đường dẫn JWKS phía trên là **ví dụ theo kiểu cấu trúc endpoint của một số IdP**, không phải quy tắc chung. Lấy `jwks_uri` thật từ metadata của provider. Có `jwk-set-uri` trực tiếp cũng giúp ứng dụng cấu hình vị trí khóa công khai tường minh.

Tạo `JwtValidationConfig.java`:

~~~java
package com.example.orders;

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
public class JwtValidationConfig {

    @Bean
    JwtDecoder jwtDecoder(Environment env) {
        String issuer = env.getRequiredProperty(
            "spring.security.oauth2.resourceserver.jwt.issuer-uri");
        String jwkSetUri = env.getRequiredProperty(
            "spring.security.oauth2.resourceserver.jwt.jwk-set-uri");
        String expectedAudience = env.getRequiredProperty(
            "app.security.audience");

        NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withJwkSetUri(jwkSetUri).build();

        OAuth2TokenValidator<Jwt> issuerAndLifetime =
            JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> audience = jwt -> {
            if (jwt.getAudience().contains(expectedAudience)) {
                return OAuth2TokenValidatorResult.success();
            }
            return OAuth2TokenValidatorResult.failure(
                new OAuth2Error("invalid_token", "Invalid audience", null));
        };

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(issuerAndLifetime, audience));
        return decoder;
    }
}
~~~

Validator này bổ sung kiểm tra `aud`, đồng thời giữ kiểm tra mặc định về issuer và thời gian của `JwtValidators.createDefaultWithIssuer`. Trên hệ thống thực tế còn cần kiểm soát thuật toán ký được cho phép, xử lý key rotation, cách issuer phát hành token, và chính sách khác theo IdP. **Nếu thêm bean `JwtDecoder` tùy chỉnh, phải giữ đầy đủ những validation mà cấu hình tự động trước đó cung cấp.**

Nếu provider dùng claim quyền khác `scope`/`scp` (ví dụ mảng role riêng), cần cấu hình `JwtAuthenticationConverter` theo định dạng của provider; không mặc định hiểu mọi role là scope. Đồng thời không được coi `email` hoặc `preferred_username` là quyền truy cập.

## 7. OIDC Login và Resource Server trong Spring Security là hai vai trò

Spring Security có các cơ chế dễ bị nhầm vì cùng bắt đầu bằng “OAuth2”:

| Cơ chế Spring Security | Ứng dụng đóng vai trò | Chức năng chính |
|---|---|---|
| `oauth2Login()` | OAuth 2.0/OIDC **Client** | Đưa người dùng đến provider, nhận code, đổi token, tạo phiên đăng nhập |
| `oauth2Client()` | OAuth **Client** | Quản lý authorized client/access token để gọi dịch vụ khác |
| `oauth2ResourceServer().jwt()` | **Resource Server** | Nhận Bearer access token và xác thực JWT để bảo vệ API |
| `oauth2ResourceServer().opaqueToken()` | **Resource Server** | Xác minh opaque access token qua introspection |

Một ứng dụng có thể đồng thời là client và resource server, nhưng phải cấu hình **từng luồng** có chủ đích. Ví dụ:

- **Frontend/BFF:** thực hiện OIDC login để biết người dùng, giữ phiên hoặc token theo thiết kế.
- **Orders API:** chỉ cần Resource Server để kiểm tra Bearer access token và áp dụng quyền `orders.read`.
- **Authorization Server/IdP:** xác thực người dùng, phát hành ID Token cho client và access token cho Orders API.

Bật `oauth2ResourceServer().jwt()` **không tự làm xuất hiện trang đăng nhập OIDC** và không tự cấp token. Ngược lại, có phiên đăng nhập từ `oauth2Login()` không có nghĩa API đã cấu hình nhận Bearer JWT từ các client bên ngoài.

## 8. Thử các trường hợp truy cập

Sau khi Authorization Server cấp **access token thật** có audience và scope phù hợp, có thể gọi API:

~~~bash
curl -i \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  https://api.example.test/api/orders
~~~

Đừng dùng ID Token thay cho `<ACCESS_TOKEN>`. Không commit token thật vào mã nguồn, tài liệu công khai hay log; khi thử lệnh, lưu và xử lý token như bí mật đăng nhập tạm thời.

Kết quả kỳ vọng theo cấu hình ví dụ:

| Tình huống | Kết quả thường gặp | Lý do |
|---|---|---|
| Không có Bearer token | **401 Unauthorized** | Chưa có thông tin xác thực hợp lệ |
| Token hết hạn, sai chữ ký/issuer hoặc sai audience | **401 Unauthorized** | Access token không được chấp nhận |
| Access token hợp lệ, thiếu `orders.read` khi gọi GET | **403 Forbidden** | Đã xác thực nhưng không đủ quyền |
| Access token hợp lệ, có `orders.read` khi gọi GET | **200 OK** | Vượt qua lớp bảo vệ endpoint; vẫn phải qua kiểm tra nghiệp vụ |
| ID Token gửi làm Bearer thay access token | **Phải bị từ chối** | Sai mục đích, thông thường sai audience/loại token |
| JWT do một issuer khác cấp | **401 Unauthorized** | Không thuộc bên phát hành được tin cậy |

Các HTTP status là hành vi dự kiến của cấu hình mẫu; ứng dụng còn có thể trả lỗi từ các bộ lọc, gateway hoặc kiểm tra nghiệp vụ khác.

### Lỗi kiến trúc thường gặp

1. **Dùng OAuth 2.0 “đăng nhập” nhưng không có OIDC:** client đọc user ID/email từ access token và xem đó là danh tính chuẩn. Các claim trong access token không được OAuth 2.0 chuẩn hóa như ID Token; muốn xác thực đăng nhập theo chuẩn liên thông, sử dụng OIDC.
2. **Gửi ID Token cho API:** ID Token dành cho client và có `aud` là client ID. API cần access token dành cho API.
3. **Chỉ kiểm tra chữ ký:** token có thể đúng chữ ký nhưng sai `iss`, `aud`, hết hạn hoặc thiếu scope; xác thực và phân quyền là hai lớp khác nhau.
4. **Nhầm scope với quyền sở hữu bản ghi:** `orders.read` không cho phép bỏ qua kiểm tra chủ sở hữu đơn hàng, tenant hoặc chính sách dữ liệu.
5. **Đưa client secret vào SPA/mobile:** đây là public client, không thể giữ bí mật đã nhúng vào ứng dụng; dùng PKCE và cấu hình client thích hợp.
6. **Coi JWT là dữ liệu đã mã hóa:** payload có thể đọc được nếu ai đó sở hữu chuỗi token.
7. **Xử lý refresh token như access token:** refresh token phục vụ token endpoint, cần bảo vệ và tuân thủ rotation/revocation của provider.
8. **Dùng cùng một token cho mọi API mà không giới hạn audience:** làm tăng rủi ro một API tiếp nhận token phát cho nơi khác.

## 9. Ghi nhớ khi thiết kế hệ thống

Hãy bắt đầu từ câu hỏi ứng dụng đang giải quyết:

- **“API có cho phép lời gọi này không?”** → Resource Server kiểm tra **OAuth 2.0 access token**, hạn, issuer, audience, scope/authority và quyền đối tượng.
- **“Người dùng vừa đăng nhập là ai?”** → **OIDC client** kiểm tra **ID Token** và dùng `iss` + `sub` làm định danh; tùy nhu cầu lấy thêm claim qua UserInfo.
- **“Ứng dụng backend cần gọi API khác không có người dùng?”** → OAuth 2.0 **Client Credentials** có thể phù hợp; không tự suy ra phiên đăng nhập OIDC.

**Một câu kết nối với Spring Security:** `oauth2Login` giải quyết trải nghiệm đăng nhập OIDC ở phía **client**, còn `oauth2ResourceServer` giải quyết việc **API** xác minh access token và thực thi chính sách ủy quyền. Hai cơ chế bổ sung cho nhau, nhưng không thể dùng ID Token thay access token.

### Tài liệu chuẩn để tra cứu

- [OAuth 2.0 Authorization Framework — RFC 6749](https://www.rfc-editor.org/rfc/rfc6749)
- [OAuth 2.0 Bearer Token Usage — RFC 6750](https://www.rfc-editor.org/rfc/rfc6750)
- [Proof Key for Code Exchange (PKCE) — RFC 7636](https://www.rfc-editor.org/rfc/rfc7636)
- [JWT Profile for OAuth 2.0 Access Tokens — RFC 9068](https://www.rfc-editor.org/rfc/rfc9068)
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html)
- [Spring Security Reference — OAuth 2.0 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html)

