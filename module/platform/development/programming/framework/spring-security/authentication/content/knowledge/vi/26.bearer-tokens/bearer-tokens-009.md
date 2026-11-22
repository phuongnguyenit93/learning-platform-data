# Ranh giới giữa xác thực JWT, phát hành token và triển khai giao thức cấp quyền

## 1. Ba công việc khác nhau trong hệ thống dùng Bearer token

Một API Spring Security chấp nhận `Authorization: Bearer <access-token>` và kiểm tra JWT thành công **chưa phải** là hệ thống phát hành token, cũng chưa trở thành máy chủ OAuth 2.0/OpenID Connect (OIDC).

Có ba trách nhiệm cần phân biệt:

1. **Xác thực JWT ở Resource Server:** nhận access token, kiểm tra chữ ký và các ràng buộc như issuer, audience, thời hạn, loại token; tạo `Authentication` và thực thi quyền truy cập.
2. **Phát hành token:** chọn identity và claims, quyết định thời hạn/phạm vi, ký token bằng khóa của issuer hoặc phát token opaque; quản lý khóa, refresh, thu hồi và vòng đời.
3. **Triển khai giao thức cấp quyền:** Authorization Server xử lý các luồng OAuth 2.0 chuẩn, đăng ký client, authorize, token endpoint, grant, redirect URI, PKCE, consent, scopes, client authentication, refresh/revocation và metadata. Nếu hỗ trợ OIDC còn có ID Token, nonce, UserInfo và các yêu cầu xác thực danh tính.

Chúng có thể ở các tiến trình tách biệt hoặc cùng nền tảng nhưng **không được suy ra trách nhiệm thứ hai hoặc thứ ba chỉ từ việc API có JwtDecoder**.

Mục tiêu bài học: nhận diện đúng thành phần Spring Security, hiểu các bước xác minh access token, biết giới hạn của một hàm ký JWT, đánh giá khi nào cần Authorization Server/OIDC Provider, cấu hình Spring Boot Resource Server Java 17+ và kiểm thử các ranh giới issuer–audience–scope.

## 2. JWT, Bearer, OAuth 2.0 và OIDC khác nhau ra sao?

| Khái niệm | Ý nghĩa | Không tự bảo đảm |
| --- | --- | --- |
| **JWT** | Định dạng token chứa JSON claims, thường được bảo vệ bằng JWS (ký số) hoặc JWE (mã hóa) | Cấp quyền theo OAuth, quy trình đăng nhập, refresh/revoke |
| **Bearer token** | Credential mà người giữ token có thể trình để truy cập trong phạm vi được chấp nhận | Chứng minh chính HTTP caller đang giữ private key riêng |
| **Access token** | Chứng cứ quyền được cấp cho một API/Resource Server | Thông tin profile người dùng đầy đủ |
| **Refresh token** | Credential cho client xin access token mới tại Authorization Server | Quyền truy cập trực tiếp API tài nguyên |
| **OIDC ID Token** | Bằng chứng xác thực danh tính dành cho OIDC client (Relying Party) | Thay thế access token gọi API tùy ý |
| **OAuth 2.0** | Khung giao thức ủy quyền và cấp access token theo grant/policy | Yêu cầu access token phải là JWT |
| **OIDC** | Lớp xác thực danh tính trên OAuth 2.0, quy định ID Token và các luồng đăng nhập liên quan | Quyền tùy ý trên mọi API |
| **Resource Server** | API tiêu thụ/kiểm tra access token và quyết định quyền | Endpoint cấp token OAuth |
| **Authorization Server** | Phát hành và quản lý quyền/token theo giao thức | Tự cấu hình authorization cho mọi API |
| **OAuth2 Client** | Ứng dụng đi xin token, có thể đăng nhập qua IdP | Tự phát hành token cho bên khác |

**JWT không đồng nghĩa access token.** ID Token của OIDC cũng thường là JWT. Một access token OAuth có thể là **opaque token**, nghĩa là Resource Server không tự đọc claims từ chuỗi mà sử dụng introspection tới Authorization Server.

**Bearer không đồng nghĩa JWT.** Header `Authorization: Bearer ...` diễn tả cách trình token. Chuỗi token có thể là JWT ký số hoặc một mã tham chiếu opaque.

## 3. Sơ đồ kiến trúc và các ranh giới tin cậy

Giả sử một website cần gọi API báo cáo:

~~~text
                         Browser / User
                              |
                     (1) Mở web app
                              |
                              v
                          OAuth2 Client
                              |
                     (2) Authorization Code
                         + PKCE + state
                              |
                              v
                      Authorization Server
                     (AS / OIDC Provider)
                     - xác thực user/client
                     - kiểm grant, scope/consent
                     - cấp access token
                     - quản lý JWK/refresh/revoke
                              |
                 (3) access token JWT/opaque
                              |
                              v
                          OAuth2 Client
                              |
              (4) Authorization: Bearer <access-token>
                              |
                              v
                         Resource Server
                         Spring Security
                     - xác minh token hợp lệ
                     - kiểm iss/aud/exp/nbf
                     - map scope/authorities
                     - kiểm quyền tài nguyên
                              |
                              v
                            API data
~~~

Hai đường đi độc lập về nhiệm vụ:

- **Cấp token:** Client hỏi Authorization Server để được cấp token theo grant và policy.
- **Tiêu thụ token:** Client trình access token cho Resource Server; Resource Server xác minh và cấp quyền.

Với JWT có chữ ký bất đối xứng, Resource Server có thể kiểm chữ ký bằng public key/JWK của issuer mà không yêu cầu Authorization Server xử lý từng request. Với opaque token hoặc JWT cần kiểm trạng thái tức thời, API có thể gọi **introspection**.

Trong grant `client_credentials` không có người dùng cuối: client backend tự xác thực với Authorization Server và xin token cho chính client. Không được mặc định claim `sub` của mọi access token đều là một người đang đăng nhập.

## 4. JWT chứa những gì?

JWT dạng compact JWS thường gồm:

~~~text
BASE64URL(header).BASE64URL(payload).BASE64URL(signature)
~~~

Header minh họa:

~~~json
{
  "alg": "RS256",
  "typ": "at+jwt",
  "kid": "key-2026-01"
}
~~~

Claims minh họa:

~~~json
{
  "iss": "https://login.example.test",
  "sub": "user-123",
  "aud": ["reports-api"],
  "iat": 1793900000,
  "nbf": 1793900000,
  "exp": 1793903600,
  "client_id": "web-portal",
  "scope": "reports.read reports.export"
}
~~~

Đây **không phải token được ký**. Các giá trị và timestamps chỉ phục vụ việc đọc cấu trúc.

| Claim/header | Ý nghĩa | Khi xác minh cần xem xét |
| --- | --- | --- |
| `alg` | Thuật toán chữ ký | Chỉ chấp nhận thuật toán đã cho phép, không tin alg tùy ý |
| `kid` | Key ID | Chỉ tra khóa trong JWK Set của issuer tin cậy |
| `typ` | Loại token theo profile | Tránh dùng ID Token làm access token |
| `iss` | Issuer | Phải đúng issuer mà API tin cậy |
| `aud` | Đối tượng nhận token | Phải bao gồm identifier của API đang được gọi |
| `exp` | Thời điểm hết hiệu lực | Từ chối token quá hạn |
| `nbf` | Không được dùng trước thời điểm này | Từ chối token chưa hợp lệ |
| `iat` | Thời điểm token được phát hành | Kiểm soát token age khi policy yêu cầu |
| `sub` | Subject | Không suy ra subject luôn là user; phân biệt issuer/tenant |
| `scope`/`scp` | Phạm vi được cấp | Chuyển sang authorities và kiểm chính xác |
| `client_id` | Client nhận token trong profile có dùng claim này | Kiểm client phù hợp khi tài nguyên yêu cầu |
| `jti` | ID token trong profile có định nghĩa | Không tự chống replay khi thiếu state |

**Chỉ parse JWT không phải xác thực.** Base64URL decoding cho phép đọc payload nhưng không xác nhận ai phát hành. Nếu ứng dụng tự decode rồi lấy `sub="admin"` thì client có thể sửa JSON để mạo danh.

**Xác minh chữ ký vẫn chưa đủ.** Token ký đúng bởi issuer tin cậy nhưng có `aud="billing-api"` không được dùng ở `reports-api`. Token có `scope="reports.read"` không có nghĩa được xuất báo cáo nếu endpoint đòi `reports.export`.

**JWS không mã hóa payload:** token ký số thường đọc được bởi người nắm chuỗi. Không đưa password, secrets, thông tin nhạy cảm không cần thiết vào JWT. Mã hóa nội dung đòi hỏi một cơ chế riêng như JWE, bên cạnh TLS.

**Loại token:** JWT access token theo RFC 9068 dùng `typ=at+jwt` hoặc `application/at+jwt`, cùng claims và quy tắc xác minh của profile. Không áp yêu cầu RFC 9068 một cách máy móc cho mọi JWT/issuer nếu hợp đồng token khác; nhưng phải có cách ngăn ID Token và access token bị nhầm lẫn.

## 5. Ranh giới thứ nhất: Resource Server kiểm tra Bearer JWT

Trong Spring Security Servlet, đường đi thông dụng:

1. `BearerTokenAuthenticationFilter` đọc access token từ request theo quy tắc Bearer.
2. `AuthenticationManager` chuyển tới `JwtAuthenticationProvider`.
3. `JwtDecoder` kiểm chữ ký/alg, token claims và validators theo cấu hình.
4. `JwtAuthenticationConverter` chuyển JWT hợp lệ thành `JwtAuthenticationToken` cùng `GrantedAuthority`.
5. Spring Security kiểm tra `authenticated()`, `hasAuthority(...)` hoặc policy ở phương thức/đối tượng.
6. API trả dữ liệu khi có quyền.

Resource Server **không cần private signing key** của issuer nếu token được ký bất đối xứng. Nó thường cần public key/JWK Set tin cậy. Không lấy `jku` hoặc JWK URL trong token do caller gửi rồi tự kết nối đến URL tùy ý: nguồn khóa phải được quản trị.

### 5.1. Những kiểm tra mặc định và bổ sung

Với `issuer-uri` trong Spring Boot 3.5.x và Spring Security 6.5.x, decoder chuẩn kiểm chữ ký, `iss`, `exp`, `nbf`; scope thường được ánh xạ tiền tố `SCOPE_`. Tùy issuer/provider, cần quy định thêm loại access token, client ID, tenants, allowed algorithms, claims riêng và chính sách tuổi token.

**Hãy kiểm `aud` rõ ràng.** Chỉ kiểm `iss` không ngăn token của một API khác lọt sang API của bạn. Spring Boot cung cấp thuộc tính `spring.security.oauth2.resourceserver.jwt.audiences` để kiểm audience dự kiến.

### 5.2. Phân biệt HTTP 401 và 403

- Không có Bearer token khi cần, token sai chữ ký, hết hạn, issuer hoặc audience không hợp lệ: authentication bị từ chối, **thường 401**.
- Token hợp lệ nhưng scope/authority không đủ: request đã xác thực nhưng không có quyền, **thường 403**.
- Token hợp lệ và scope đúng: vẫn phải kiểm quyền trên object, tenant, owner, trạng thái tài nguyên, **không được cấp tất cả quyền chỉ vì đã authenticated**.

Ví dụ issuer cấp `scope="reports.read"`, Spring Security mặc định map thành `SCOPE_reports.read`. Rule `hasAuthority("SCOPE_reports.read")` kiểm authority đó. Nó khác `hasRole("reports.read")` thường tìm tiền tố `ROLE_`.

## 6. Ví dụ hoàn chỉnh: Spring Boot Resource Server Java 17+

Ví dụ này chỉ **nhận và kiểm tra JWT**, không có endpoint phát hành token. Dùng Spring Boot 3.5.x / Spring Security 6.5.x / Java 17+, Maven, Servlet/Spring MVC.

### 6.1. Phụ thuộc

Tạo project Spring Initializr với:

- Spring Web: `spring-boot-starter-web`.
- OAuth2 Resource Server: `spring-boot-starter-oauth2-resource-server`.

Starter cung cấp các module cần thiết cho JWT/JOSE. Nếu khai báo dependency thủ công phải có cả `spring-security-oauth2-resource-server` và `spring-security-oauth2-jose` với phiên bản tương thích; để Spring Boot BOM quản lý versions.

### 6.2. Cấu hình issuer và audience

Tệp `src/main/resources/application.properties`:

~~~properties
server.port=8080

spring.security.oauth2.resourceserver.jwt.issuer-uri=https://login.example.test
spring.security.oauth2.resourceserver.jwt.audiences=reports-api
~~~

Đây là issuer **minh họa**; để login thật phải thay bằng issuer hợp lệ có metadata và JWK Set, phát hành JWT với `iss` chính xác và `aud` chứa `reports-api`.

Nếu issuer không cung cấp discovery chuẩn nhưng đã có endpoint JWK Set được kiểm chứng, có thể chỉ định thêm (đường dẫn tùy issuer):

~~~properties
spring.security.oauth2.resourceserver.jwt.jwk-set-uri=https://login.example.test/oauth2/jwks
~~~

Giữ `issuer-uri` giúp kiểm `iss`. Chỉ định duy nhất `jwk-set-uri` mà không cấu hình validator issuer có thể bỏ mất kiểm tra issuer, tùy custom decoder.

### 6.3. Java nguồn đầy đủ

Tạo `src/main/java/demo/jwt/JwtResourceServerApplication.java`:

~~~java
package demo.jwt;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class JwtResourceServerApplication {

    public static void main(String[] args) {
        SpringApplication.run(JwtResourceServerApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/health").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/reports/me")
                    .hasAuthority("SCOPE_reports.read")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()));

        return http.build();
    }

    @RestController
    static class ReportApi {

        @GetMapping("/health")
        String health() {
            return "Resource Server ready";
        }

        @GetMapping("/api/reports/me")
        Map<String, Object> myToken(@AuthenticationPrincipal Jwt jwt) {
            return Map.of(
                "subject", jwt.getSubject(),
                "issuer", jwt.getIssuer().toString(),
                "audience", jwt.getAudience()
            );
        }
    }
}
~~~

Giải thích:

- `oauth2ResourceServer(...jwt(...))` đăng ký xác thực Bearer JWT; nó **không** dựng `/oauth2/token` hoặc ký token.
- `issuer-uri` và `audiences` ràng buộc trust để API không nhận nhầm token issuer/service khác.
- `hasAuthority("SCOPE_reports.read")` yêu cầu token có scope phù hợp.
- `@AuthenticationPrincipal Jwt` là JWT **đã được Spring Security xác minh**; controller không lấy token thô từ request để tự decode.
- `/health` cho phép gọi không cần token; `denyAll()` chặn URL khác nếu chưa có rule.

Ví dụ GET `/api/reports/me` xuất vài claim để học; trong ứng dụng thật cần cân nhắc không công khai thông tin issuer/audience/subject cho những bên không cần.

### 6.4. Chạy và xác minh

Trong project Maven:

~~~bash
./mvnw spring-boot:run
~~~

Windows: `mvnw.cmd spring-boot:run`. Không có wrapper thì dùng `mvn spring-boot:run`.

Kiểm tra route công khai:

~~~bash
curl -i http://127.0.0.1:8080/health
~~~

Body kỳ vọng:

~~~text
Resource Server ready
~~~

Kiểm tra route được bảo vệ:

~~~bash
curl -i http://127.0.0.1:8080/api/reports/me
~~~

Thường nhận HTTP 401 khi chưa có Bearer token. Khi đã **lấy access token thật** từ issuer tương thích:

~~~bash
curl -i \
  -H "Authorization: Bearer ACCESS_TOKEN_HOP_LE" \
  http://127.0.0.1:8080/api/reports/me
~~~

`ACCESS_TOKEN_HOP_LE` là placeholder, không phải token thật. Trên Windows PowerShell có thể dùng `curl.exe` và viết cùng một dòng. Không lưu token thật vào lịch sử shell dùng chung hoặc log.

Nếu JWT hợp lệ với scope `reports.read`, ví dụ response:

~~~json
{
  "subject": "user-123",
  "issuer": "https://login.example.test",
  "audience": ["reports-api"]
}
~~~

Nếu token có issuer đúng nhưng `aud=billing-api`, xác thực phải thất bại. Nếu audience đúng nhưng thiếu `reports.read`, request thường là 403. Những kết quả cụ thể còn phụ thuộc IdP, token claim thực tế và cấu hình entry point.

**Giới hạn:** ứng dụng này không có trang đăng nhập, không nhận username/password, không có grant flow, refresh token, client registration hoặc phát hành token. Việc truy cập hostname giả định không thành công không phải lỗi logic của Resource Server.

## 7. Ranh giới thứ hai: một hàm ký JWT chỉ là primitive phát hành token

Một chương trình có thể dùng `JwtEncoder` để tạo và ký JWT:

~~~java
// Đoạn minh họa; chưa phải class/chương trình độc lập.
JwtClaimsSet claims = JwtClaimsSet.builder()
    .issuer("https://issuer.example.test")
    .subject("user-123")
    .audience(java.util.List.of("reports-api"))
    .expiresAt(java.time.Instant.now().plusSeconds(900))
    .claim("scope", "reports.read")
    .build();

Jwt jwt = jwtEncoder.encode(
    org.springframework.security.oauth2.jwt.JwtEncoderParameters.from(claims)
);
~~~

Cần có bean `JwtEncoder` đã cấu hình khóa, lựa chọn algorithm, logic xác thực caller và chính sách claims. Đoạn code trên **không** là một AS có thể vận hành; chỉ mô tả thao tác ký payload đã dựng.

### 7.1. Tại sao endpoint POST /login trả JWT chưa phải OAuth 2.0?

Ví dụ tự định nghĩa:

~~~http
POST /login HTTP/1.1
Content-Type: application/json

{"username":"alice","password":"..."}
~~~

Response minh họa:

~~~json
{
  "token": "eyJ..."
}
~~~

Đó có thể là **giao thức token riêng của ứng dụng**, nếu đã được thiết kế và bảo vệ đúng. Nhưng chỉ như vậy chưa có:

- OAuth client registration, client authentication, kiểu client public/confidential.
- Authorization Code + PKCE, Client Credentials, Refresh Token cùng contract chuẩn.
- Authorization endpoint, token endpoint, redirect URI validation, state/correlation, chống CSRF.
- Quản lý scope, resource/audience và consent; không trao scope vượt policy.
- Client-credentials security, key rotation, JWKS và metadata/discovery.
- Refresh token lifecycle, revocation/introspection, lưu trạng thái authorization.
- OIDC ID Token, nonce, UserInfo và logout khi cần đăng nhập federated.

Không gọi tự chế `/login` trả JWT là “OAuth Server” nếu client OAuth tiêu chuẩn không thể hoàn thành giao thức. Việc dùng JWT làm access token **không bắt buộc** phải triển khai OAuth, nhưng phải gọi đúng bản chất giao thức.

### 7.2. Issuer chịu những trách nhiệm nào?

1. Quyết định **ai** yêu cầu token: client nào, người dùng nào, credential/grant nào.
2. Kiểm client registration, allowed grant types, redirect URIs và scopes.
3. Quy định `iss`, `aud`, `sub`, claims, token type và thời hạn hợp lệ.
4. Bảo vệ signing private keys, phân phối JWK public, `kid`, rotation và xử lý lộ khóa.
5. Lưu authorization, refresh, consent/revocation cần thiết.
6. Audit, rate limit, chống login abuse, bảo vệ token endpoints.
7. Có chính sách client secrets, PKCE, MFA/SSO (nếu liên quan).

Resource Server thường **không điều khiển token issuance**. Nó kiểm tra token theo hợp đồng với issuer và quyết định quyền truy cập tài nguyên tại API.

## 8. Ranh giới thứ ba: Authorization Server thực thi OAuth 2.0/OIDC

### 8.1. Vai trò giao thức

| Vai trò | Trách nhiệm |
| --- | --- |
| Resource Owner | Chủ thể sở hữu tài nguyên, thường là người dùng |
| Client | Ứng dụng muốn truy cập tài nguyên |
| Authorization Server | Xác thực phù hợp, thực hiện grant, phát hành token |
| Resource Server | API chấp nhận access token và bảo vệ tài nguyên |

AS có thể dùng cùng cơ sở dữ liệu người dùng với API, nhưng các contract và quyền khác nhau.

### 8.2. Authorization Code + PKCE

Luồng trình duyệt/OIDC tiêu biểu:

~~~text
Browser → Client → AS /oauth2/authorize
                (client_id, scope, redirect_uri,
                 state, code_challenge, method=S256)
                       |
                  login / consent
                       |
                 redirect code + state
                       |
Client → AS /oauth2/token
             (code, redirect_uri, code_verifier,
              client auth nếu phù hợp)
                       |
            access token (+ refresh token khi được phép;
                           ID Token khi là OIDC login)
                       |
Client → API: Authorization: Bearer <access-token>
~~~

**PKCE** ràng buộc authorization code với `code_verifier` của client, làm giảm rủi ro code interception. `state` hỗ trợ correlation/CSRF protection của authorization response. OIDC bổ sung các yêu cầu như ID Token validation và `nonce` khi áp dụng. Public clients như SPA/mobile không được giấu client secret cứng trong frontend mà gọi đó là secret.

**Access token khác ID Token:** ID Token hướng đến OIDC client; Resource Server thường yêu cầu access token có audience/API-specific claims và scope. Cùng được ký bởi một issuer không có nghĩa dùng thay thế nhau.

### 8.3. Client Credentials

Backend gọi AS với `grant_type=client_credentials` và client authentication phù hợp, nhận access token rồi gọi Resource Server. Không có người dùng cuối trong flow này; quyền thường gắn với service/client. Không tự dùng `sub` như user ID khi token có ngữ nghĩa client.

### 8.4. Refresh và revoke

Client có refresh token hợp lệ có thể gửi tới **AS token endpoint** để xin access token mới. Resource Server không phải nơi nhận refresh token. Với JWT xác minh offline, revoke ở AS không nhất thiết khiến mọi API lập tức biết token đã bị thu hồi; cần chọn short TTL, introspection, denylist, sự kiện thu hồi hoặc cơ chế bổ sung dựa trên yêu cầu độ trễ revoke.

## 9. Spring Resource Server, OAuth2 Client và Authorization Server dùng module nào?

| Nhu cầu | Cơ chế Spring |
| --- | --- |
| API xác minh JWT Access Token do IdP phát hành | `spring-boot-starter-oauth2-resource-server` với JWT decoder |
| API xác minh opaque Bearer Token | Resource Server + introspection |
| Web app đăng nhập qua OIDC IdP | `spring-boot-starter-oauth2-client` + `oauth2Login()` |
| Backend lấy token client_credentials để gọi API | OAuth2 Client token acquisition phù hợp |
| Tự xây OAuth2 Authorization Server chuẩn | `spring-boot-starter-oauth2-authorization-server` hoặc nền tảng IdP chuyên dụng |
| Chỉ ký/đọc JWT trong Java | `JwtEncoder`/`JwtDecoder` là primitive, không tạo protocol |

**Mốc phiên bản ví dụ:** Spring Boot 3.5.x / Spring Security 6.5.x / Authorization Server tương thích theo Spring Boot BOM. Từ Boot 4/Spring Security 7, kiểm lại tên module, API, DSL và migration guide thay vì copy nguyên cấu hình dự án cũ.

### 9.1. Hình dạng cấu hình Authorization Server

Một project khác muốn làm AS có thể bắt đầu với starter:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-authorization-server</artifactId>
</dependency>
~~~

Ví dụ YAML mô tả **một client** cho authorization code và refresh token (cấu hình rút gọn để hiểu cấu trúc; không phải toàn bộ triển khai production):

~~~yaml
server:
  port: 9000

spring:
  security:
    oauth2:
      authorizationserver:
        client:
          web-client:
            registration:
              client-id: web-client
              client-secret: "${CLIENT_SECRET_ENCODED}"
              client-authentication-methods:
                - client_secret_basic
              authorization-grant-types:
                - authorization_code
                - refresh_token
              redirect-uris:
                - https://app.example.test/login/oauth2/code/web-client
              scopes:
                - openid
                - profile
                - reports.read
            require-authorization-consent: true
~~~

`CLIENT_SECRET_ENCODED` phải được cấp từ kho secrets và biểu diễn theo PasswordEncoder tương ứng; không commit plaintext password/client secret vào Git. Khi vận hành AS cần cấu hình issuer URI, HTTPS, keys, persistence cho clients/authorizations/consents, user login, rotation/revoke, HA và giám sát.

Các thành phần thường gặp:

- `RegisteredClientRepository` quản lý clients, grants, redirect URIs, scopes.
- `OAuth2AuthorizationService` quản lý authorization state và token lifecycle.
- `OAuth2AuthorizationConsentService` quản lý consent khi được sử dụng.
- `JWKSource<SecurityContext>` đưa key material cho JWT signing/JWK publication.
- `AuthorizationServerSettings` định nghĩa issuer và các endpoints.
- Các `SecurityFilterChain` cho AS protocol endpoints và đăng nhập user.
- OIDC setup riêng khi AS phát ID Token và cung cấp OIDC metadata/UserInfo.

Một cấu hình in-memory có thể phù hợp học tập nhưng không đáp ứng HA, key persistence, audit và token lifecycle cho sản xuất.

## 10. JWT so với opaque token và kiểm tra trạng thái

| Tiêu chí | JWT tự xác minh | Opaque token qua introspection |
| --- | --- | --- |
| Cách xác minh | JWS + claims/issuer/audience/time/policy | AS introspection trả active và claims theo hợp đồng |
| Network call mỗi API request | Thường không cần khi JWKS đã cache | Thường cần, trừ cơ chế cache được thiết kế |
| Token có đọc được claims không | Payload JWS thường đọc được | Giá trị opaque không bộc lộ claim trực tiếp |
| Phụ thuộc AS runtime | Ít hơn, nhưng vẫn cần JWKS/rotation | Cao hơn, cần endpoint introspection |
| Thu hồi quyền sớm | Cần cơ chế bổ sung nếu chỉ check offline | AS có thể ngừng đánh dấu active |
| Key/credential | Public key/JWKS tin cậy | Client secret hoặc xác thực introspection |
| Authorization | API vẫn tự thực thi policy | API vẫn tự thực thi policy |

Spring Security hỗ trợ `opaqueToken(...)` khi đã có introspection endpoint đáng tin:

~~~properties
spring.security.oauth2.resourceserver.opaquetoken.introspection-uri=https://login.example.test/oauth2/introspect
spring.security.oauth2.resourceserver.opaquetoken.client-id=reports-api
spring.security.oauth2.resourceserver.opaquetoken.client-secret=${INTROSPECTION_CLIENT_SECRET}
~~~

~~~java
// Đoạn cấu hình bên trong SecurityFilterChain:
.oauth2ResourceServer(oauth2 ->
    oauth2.opaqueToken(Customizer.withDefaults()))
~~~

Đây chỉ là **mảnh cấu hình** thay cho `jwt(...)`, không phải ứng dụng độc lập. Spring có thể introspect một token có hình dạng JWT nếu cần hỏi trạng thái AS; định dạng token và cách xác minh là hai lựa chọn riêng. Cần bảo vệ secret, TLS, timeout và fail closed.

## 11. Tách token authentication và resource authorization

Một token có thể trả lời ai/cái gì đang gọi và quyền cơ bản nào được cấp; API vẫn phải kiểm tài nguyên cụ thể.

Ví dụ:

- AS cấp JWT: `sub=user-123`, `aud=reports-api`, `scope=reports.read`, `tenant_id=tenant-A`.
- API xác minh JWT thành công, kiểm scope đúng.
- User gọi `GET /api/tenants/tenant-B/reports/99`.

Nếu API chỉ kiểm scope, user tenant A có thể đọc dữ liệu tenant B. API phải kiểm tenant và ownership/object-level permissions. **JWT hợp lệ không đồng nghĩa truy cập hợp lệ**.

Các khái niệm khác biệt:

- User authentication ở IdP/AS xác nhận user credential hoặc session.
- Client authentication ở AS xác nhận client.
- Token authentication ở API xác minh Bearer token.
- Authorization grant ở AS quyết định scopes/resources được cấp.
- Resource authorization ở API quyết định từng hành động, đối tượng, tenant và chính sách nghiệp vụ.

Client **xin** scope trong authorization request không có nghĩa issuer buộc phải cấp. API thấy scope cũng không có nghĩa role nội bộ tự có. Role-based authorization và scope-based authorization có thể bổ sung nhau nhưng không phải một.

## 12. Java 17 độc lập: minh họa kiểm issuer/audience/time/scope

Để tự kiểm tra quy tắc claims mà không cần server, chương trình sau mô phỏng bước policy **sau khi claims đã được xác minh bằng một JWT decoder đáng tin**. Nó không parse token, không kiểm chữ ký và **không được dùng độc lập để xác thực Bearer token**.

Tạo `TokenPolicyDemo.java`:

~~~java
import java.time.Instant;
import java.util.Set;

public class TokenPolicyDemo {

    record VerifiedClaims(
            String issuer,
            Set<String> audiences,
            Instant expiresAt,
            Set<String> scopes) {}

    static boolean mayRead(VerifiedClaims token, Instant now) {
        return "https://login.example.test".equals(token.issuer())
                && token.audiences().contains("reports-api")
                && now.isBefore(token.expiresAt())
                && token.scopes().contains("reports.read");
    }

    public static void main(String[] args) {
        Instant now = Instant.parse("2026-11-06T00:00:00Z");
        Instant later = Instant.parse("2026-12-01T00:00:00Z");

        var valid = new VerifiedClaims(
                "https://login.example.test",
                Set.of("reports-api"),
                later,
                Set.of("reports.read"));

        var wrongAudience = new VerifiedClaims(
                "https://login.example.test",
                Set.of("billing-api"),
                later,
                Set.of("reports.read"));

        var wrongScope = new VerifiedClaims(
                "https://login.example.test",
                Set.of("reports-api"),
                later,
                Set.of("reports.export"));

        var expired = new VerifiedClaims(
                "https://login.example.test",
                Set.of("reports-api"),
                Instant.parse("2026-11-05T00:00:00Z"),
                Set.of("reports.read"));

        System.out.println(mayRead(valid, now));
        System.out.println(mayRead(wrongAudience, now));
        System.out.println(mayRead(wrongScope, now));
        System.out.println(mayRead(expired, now));
    }
}
~~~

Chạy:

~~~bash
javac --release 17 TokenPolicyDemo.java
java TokenPolicyDemo
~~~

Stdout **chính xác**:

~~~text
true
false
false
false
~~~

Dòng 1 đáp ứng cả bốn điều kiện; các dòng sau lần lượt sai audience, thiếu scope hoặc hết hạn. Trong hệ thống thật còn phải có chữ ký, algorithm whitelist, issuer trust, `nbf`, token type và các quy tắc nghiệp vụ khác.

## 13. Sai lầm thường gặp và cách khắc phục

| Sai lầm | Tác hại | Cách khắc phục |
| --- | --- | --- |
| Chỉ Base64URL-decode để lấy `sub` | Có thể tin claims do attacker tự viết | Dùng `JwtDecoder` xác minh và validators |
| Chỉ kiểm chữ ký, bỏ `aud` | Dùng token của API khác | Kiểm audience tài nguyên |
| Chỉ kiểm `iss` nhưng bỏ `exp` | Dùng token hết hạn | Kiểm thời gian và clock skew hợp lý |
| Tự tin header `alg`/`jku` | Algorithm/key confusion, nguồn khóa độc hại | Whitelist thuật toán và JWK URL |
| Dùng ID Token thay access token | Token hướng tới OAuth client bị API chấp nhận nhầm | Kiểm audience và token profile |
| Dùng một symmetric secret cho mọi service | Bất kỳ service có secret đều có thể giả issuer | Tách quyền ký/xác minh, ưu tiên khóa bất đối xứng |
| Tự làm `/login` trả JWT và nói hỗ trợ OAuth | Thiếu protocol grants/PKCE/refresh/metadata | Dùng AS/IdP chuẩn khi cần interoperability |
| Client secret nhúng vào SPA/mobile | Secret có thể bị trích xuất | Dùng public-client model với PKCE |
| Chỉ check `authenticated()` | Bỏ qua scope/tenant/object permission | Rule theo scope và dữ liệu |
| JWT TTL quá dài | Token bị đánh cắp dùng lâu | TTL ngắn, refresh/revoke theo policy |
| Tin `jti` tự chống replay | Bearer token vẫn có thể được gửi lại | Token binding, state/replay detection khi yêu cầu |
| Quên JWKS rotation | Token hợp lệ bị từ chối hoặc key lộ còn được tin | Key lifecycle, multiple active keys, refresh cache |
| Ghi Bearer token trong URL/log | Rò token qua lịch sử, log, monitoring | Header, masking, HTTPS, bảo mật client |
| Gọi mọi lỗi là 403 | Nhầm lỗi token với lỗi thiếu quyền | Phân biệt 401/403 và kiểm tests |
| Dùng `sub` toàn cục qua mọi tenant | Trùng subject giữa issuer/tenant | Namespace hóa identity qua issuer + tenant + sub |

### Bearer token có phải proof-of-possession?

Không. Với Bearer, bên giữ chuỗi token còn hiệu lực có thể dùng nó trong phạm vi cho phép. JWT do issuer ký bằng RSA chỉ chứng minh token do issuer có private key ký, **không chứng minh request HTTP do client sở hữu private key riêng gửi**. Nếu cần proof-of-possession phải thiết kế sender-constrained token như mTLS-bound tokens hoặc DPoP phù hợp.

### Browser và lưu token

Client cần chống XSS, exfiltration và log leakage. Token lưu ở JS-readable storage có rủi ro XSS; token truyền tự động bằng cookie lại cần xem xét CSRF, SameSite và policy session. CORS không phải biện pháp xác thực và không thay thế authorization. Dùng HTTPS trên mọi kênh chứa token và tránh chuyển token qua query parameter.

### Thu hồi quyền không tự động

JWT đã ký và còn `exp` có thể tiếp tục được API offline chấp nhận sau khi user logout/đổi role nếu Resource Server không có cơ chế nhận biết thay đổi. Cần quyết định TTL, introspection, revocation list, key rotation, policy lookup hoặc sự kiện thu hồi. Không vô hiệu hóa signature validation chỉ để khắc phục sự cố khóa/JWK.

## 14. Checklist triển khai

**Resource Server:**

- [ ] Chỉ chấp nhận issuer đã khai báo; JWK Set từ nguồn tin cậy.
- [ ] Kiểm chữ ký, allowed algorithms, `iss`, `aud`, `exp`, `nbf`.
- [ ] Kiểm token type/profile khi ứng dụng có nhiều loại JWT.
- [ ] Xác nhận audience cho API; không coi token của service khác là hợp lệ.
- [ ] Map scope/roles và kiểm object/tenant ownership.
- [ ] Phân biệt 401 token invalid với 403 insufficient permission.
- [ ] Bảo vệ Bearer credentials, tránh log/URL, sử dụng HTTPS.
- [ ] Có kế hoạch JWKS cache/rotation, timeout và xử lý lỗi issuer.
- [ ] Thiết kế chính sách revoke và hiệu lực token phù hợp.

**Authorization Server:**

- [ ] Đăng ký client, xác thực client và giới hạn grants/scopes/redirect URIs.
- [ ] Dùng Authorization Code + PKCE cho ứng dụng public phù hợp.
- [ ] Thiết lập issuer, aud, claims, token lifetime, token type chính xác.
- [ ] Bảo vệ private signing keys, JWKS, secret storage, rotation.
- [ ] Quản lý authorization consent/refresh/revoke/introspection theo nhu cầu.
- [ ] OIDC ID Token/UserInfo/metadata nếu triển khai login danh tính.
- [ ] Thiết lập HTTPS, rate limit, MFA/login policy, audit, monitoring.
- [ ] Có kế hoạch phục hồi sau key compromise/token leakage.

## 15. Ma trận kiểm thử

| Trường hợp | Kỳ vọng |
| --- | --- |
| Không gửi token tới endpoint bảo vệ | 401 |
| Bearer token là chuỗi ngẫu nhiên | 401 |
| JWT có cấu trúc hợp lệ nhưng sai chữ ký | 401 |
| Token từ issuer không tin cậy | 401 |
| Chữ ký đúng nhưng sai audience | 401 |
| Token hết hạn hoặc trước `nbf` | 401 |
| Token đúng nhưng thiếu `reports.read` | 403 |
| Token hợp lệ, đủ scope nhưng khác tenant/object | Deny theo policy, thường 403 |
| Token đúng issuer, aud, scope và quyền dữ liệu | 200 hoặc response nghiệp vụ hợp lệ |
| ID Token trình thay access token | Bị từ chối theo audience/token type policy |
| Refresh token trình vào API | Bị từ chối; refresh chỉ dành cho AS |
| Key rotation của issuer | Resource Server cập nhật JWK theo policy, không tắt xác minh |
| AS tạm mất kết nối, JWKS đã cache | Hành vi theo cache/timeout đã kiểm thử, không nhận token chưa kiểm chứng |
| Introspection endpoint bị lỗi | Fail closed, không tự coi token `active` |

Các status là kỳ vọng cho API Bearer thông dụng; custom entry point/gateway có thể thay HTTP status cuối, nhưng **tuyệt đối không cấp quyền sai**.

## 16. Câu hỏi tự kiểm tra

1. Vì sao `oauth2ResourceServer().jwt()` không tạo ra `/oauth2/token`?
2. Một hàm ký JWT còn thiếu gì để đạt giao thức OAuth2 chuẩn?
3. ID Token và access token khác audience và mục đích ra sao?
4. Vì sao chữ ký JWT hợp lệ không đủ để API cấp quyền?
5. Khi nào Resource Server không cần private signing key?
6. Scope `reports.read` thường thành authority nào của Spring Security?
7. Token `client_credentials` có nhất thiết đại diện cho user không?
8. Logout tại AS có tự làm mọi JWT đã ký hết hiệu lực ngay không?
9. Khi nào trả 401, khi nào thường 403?
10. Vì sao `sub` không đủ làm identity toàn cục trong hệ thống multi-tenant?
11. Vì sao `jti` không tự ngăn Bearer replay?
12. Trường hợp nào chọn Resource Server, OAuth2 Client, Authorization Server hoặc OIDC Provider?

## 17. Tài liệu tham khảo

- [Spring Security 6.5 — Resource Server JWT](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html)
- [Spring Security 6.5 — Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/opaque-token.html)
- [Spring Security 6.5 — OAuth2 Client](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/client/index.html)
- [Spring Authorization Server 1.5 — Getting Started](https://docs.spring.io/spring-authorization-server/reference/1.5/getting-started.html)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 9068 — JWT Profile for OAuth Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 7636 — Proof Key for Code Exchange](https://www.rfc-editor.org/rfc/rfc7636)
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html)
