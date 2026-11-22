# state, PKCE và nonce bảo vệ những phần nào của luồng đăng nhập OAuth2/OIDC?

## 1. Phạm vi và câu trả lời trực tiếp

Trong **OAuth 2.0 Authorization Code Flow** và **OpenID Connect (OIDC) Authorization Code Flow**, browser đi từ ứng dụng (OAuth client / OIDC Relying Party) sang Authorization Server/OpenID Provider, sau đó quay lại ứng dụng qua callback. Ba giá trị `state`, PKCE và `nonce` cùng xuất hiện nhưng được kiểm tra ở ba mắt xích khác nhau.

| Cơ chế | Chứng minh điều gì? | Giá trị gửi khi bắt đầu | Được kiểm tra khi nào, bởi ai? | Nguy cơ chính được giảm |
| --- | --- | --- | --- | --- |
| **`state`** | Authorization response thuộc **giao dịch do đúng trình duyệt/phiên này khởi tạo** | `state` ngẫu nhiên trong URL tới authorization endpoint | **Client** nhận callback đối chiếu returned state với giao dịch đã lưu | Login CSRF, session swapping và callback không thuộc lượt đăng nhập đang chờ |
| **PKCE** | Người đổi authorization code biết **bí mật riêng của lượt khởi tạo** | `code_challenge` + `code_challenge_method=S256`; giữ kín `code_verifier` | **Authorization Server** nhận token request dùng verifier đối chiếu challenge của code | Authorization-code interception, injection/substitution và misuse |
| **OIDC `nonce`** | ID Token thật sự thuộc **lượt yêu cầu xác thực OIDC đang chờ** | `nonce` trong authentication request | **OIDC client** xác minh claim `nonce` của ID Token sau khi validate token | ID Token replay/substitution, ràng buộc token với lần đăng nhập cụ thể |

Ba cơ chế có **vùng giao nhau**: RFC 9700 xác nhận PKCE có thể chống CSRF khi server hỗ trợ và client gắn nó đúng với giao dịch/trình duyệt; OIDC nonce cũng có thể giúp chống CSRF và code injection trong các điều kiện cụ thể. Vì vậy đừng ghi nhớ thành ba hàng rào hoàn toàn tách biệt. Nhưng để debug: kiểm tra **callback** → nghĩ tới state; kiểm tra **đổi code lấy token** → nghĩ tới PKCE; kiểm tra **ID Token** → nghĩ tới nonce.

**OAuth 2.0** chủ yếu nói về *ủy quyền* (delegated access). **OIDC** bổ sung lớp *xác thực người dùng*, gồm scope `openid` và ID Token. Không kết luận ai đã đăng nhập chỉ bằng cách decode access token hoặc gọi nó là ID Token.

## 2. Luồng đầy đủ và vị trí lưu giá trị

Ví dụ chỉ dùng Authorization Code Flow, backend client bảo vệ session và giao dịch server-side; các URL tên miền `example.test` mang tính mô phỏng.

```text
Browser                  App (OAuth/OIDC Client)                 OpenID Provider / AS
   |                             |                                     |
   | GET /oauth2/authorization/demo                                   |
   |---------------------------->|                                     |
   |                             | sinh state=S                       |
   |                             | sinh verifier=V                    |
   |                             | challenge=C=S256(V)                |
   |                             | sinh nonce=N nếu OIDC              |
   |                             | lưu {S,V,N,issuer,expires}         |
   |                             | gắn với phiên browser này          |
   |<------ 302 /authorize?state=S&code_challenge=C&nonce=N ------------|
   |                             |                                     |
   | Browser theo redirect ------------------------------------------->|
   |                             |          xác thực người dùng       |
   |<---------------------- 302 callback?code=K&state=S ----------------|
   |                             |                                     |
   | GET /login/oauth2/code/demo?code=K&state=S                        |
   |---------------------------->|                                     |
   |                             | 1. compare S với state kỳ vọng     |
   |                             | 2. kiểm tra transaction còn hiệu lực|
   |                             |                                     |
   |                             | POST /token: code=K, verifier=V    |
   |                             |------------------------------------>|
   |                             |           S256(V) phải bằng C       |
   |                             |<----- access_token, id_token ------|
   |                             |                                     |
   |                             | 3. verify ID Token: signature,     |
   |                             |    iss, aud, exp, nonce tương ứng  |
   |                             | 4. tạo local session nếu hợp lệ   |
   |<---------------- 302 về trang ứng dụng ---------------------------|
```

Transaction tạm, **không phải** JSON gửi cho provider:

```json
{
  "state": "random-for-login-1",
  "codeVerifier": "private-random-verifier",
  "expectedNonce": "random-for-login-1",
  "issuer": "https://idp.example.test",
  "redirectUri": "https://app.example.test/login/oauth2/code/demo",
  "expiresAt": "short-lived-expiry",
  "consumed": false
}
```

Đối với server-side web client, giữ expected state, nonce và verifier trong server session/kho giao dịch đã được ràng buộc với browser. Với SPA/mobile, nơi lưu khác nhưng **không được làm lộ verifier** hoặc dùng cùng một transaction cho người dùng/browser khác. Thời gian tồn tại ngắn, tiêu thụ một lần và có cơ chế xử lý hai callback đồng thời.

## 3. state: chống login CSRF và gắn authorization response với phiên

### 3.1. Nếu không kiểm tra state

Attacker đã đăng nhập vào tài khoản của mình có thể lấy authorization response cho tài khoản attacker và dụ browser nạn nhân đi qua callback đó. Nếu ứng dụng chỉ thấy `code` là tự đăng nhập, trình duyệt nạn nhân có thể bị gắn vào **tài khoản do attacker kiểm soát**. Nạn nhân vô tình nhập thông tin vào tài khoản của attacker; đây là **login CSRF/session swapping**.

Giả sử browser nạn nhân đã bắt đầu flow với `state=S_victim`. Client lưu S_victim cho session đó. Một callback có `state=S_attacker` do attacker lấy từ browser khác sẽ bị bác bỏ **ngay ở client**, dù authorization code đi kèm vốn hợp lệ với provider.

### 3.2. Cách thực hiện đúng

1. Mỗi lần bắt đầu đăng nhập, sinh state ngẫu nhiên khó đoán (ví dụ 32 byte từ CSPRNG rồi Base64URL không padding), không dùng timestamp hay tên người dùng.
2. Lưu expected state **cùng phiên user agent** và dữ liệu authorization request (issuer, redirect URI, client registration, PKCE verifier, nonce nếu có).
3. Khi callback trở lại, tìm pending transaction của browser hiện tại; so giá trị returned state với expected. Sai, thiếu, hết hạn hoặc đã dùng → từ chối.
4. Đánh dấu/loại bỏ transaction sau khi xử lý theo nguyên tắc **single-use**. Nếu hai callback cùng tới, phải đảm bảo chỉ một callback thành công.
5. Nếu state còn mang một đường dẫn “quay lại /orders”, bảo vệ dữ liệu đó khỏi sửa đổi; chỉ cho phép redirect đích tin cậy. Đừng chuyển tùy ý tới URL trong state.
6. Bảo vệ cookie session (HTTPS, HttpOnly, Secure, SameSite phù hợp), cấu hình callback và reverse proxy chuẩn, tránh đưa state/code vào log nhạy cảm.

**Không đủ:** kiểm tra “tham số `state` có giá trị” hoặc so với một giá trị do **chính callback vừa cung cấp** mà không có bản đã lưu từ lúc bắt đầu. Quan trọng nhất là ràng buộc với giao dịch do **đúng browser** khởi tạo.

### 3.3. state có bảo vệ authorization code bị đánh cắp?

State bảo vệ mối liên hệ giữa request và callback ở **OAuth client**. Token endpoint thường không nhận state, nên state **không chứng minh quyền sở hữu authorization code** khi một bên thứ ba lấy được code. PKCE mới trực tiếp bảo vệ khâu này.

Theo **RFC 9700**, client có thể dựa vào PKCE để chống CSRF nếu chắc chắn server hỗ trợ/kiểm tra PKCE và giao dịch được ràng buộc đúng với user agent; lúc ấy state không phải điều kiện tuyệt đối của mọi flow. Trong ứng dụng Spring Security thông thường vẫn nên giữ state mặc định cùng PKCE để việc quản lý callback rõ ràng và an toàn.

## 4. PKCE: bảo vệ khi đổi authorization code lấy token

PKCE (Proof Key for Code Exchange, **RFC 7636**) được thiết kế để authorization code bị nhìn thấy hoặc bị chèn vào luồng **không đủ** nhằm lấy token. Mỗi lần bắt đầu authorization request tạo một `code_verifier` ngẫu nhiên bí mật; authorization request chỉ gửi **biến đổi một chiều** của nó.

### 4.1. Thuật toán S256

Theo RFC 7636:

- `code_verifier` có 43–128 ký tự ASCII thuộc `A–Z a–z 0–9 - . _ ~`. Sinh **32 byte CSPRNG** và mã hóa Base64URL không padding tạo chuỗi **43 ký tự**, khoảng 256 bit entropy.
- Tính chính xác:

  `code_challenge = BASE64URL_NO_PADDING(SHA256(ASCII(code_verifier)))`

- Gửi `code_challenge` và `code_challenge_method=S256` trong **authorization request** ở browser.
- Giữ `code_verifier` trong transaction client; sau callback hợp lệ, gửi nó trong **POST /token qua TLS** cùng code, redirect URI và thông tin client cần thiết.
- Authorization Server lưu challenge gắn với **authorization code được phát**. Khi đổi code, server tính S256(verifier) và đối chiếu; nếu không khớp phải từ chối cấp token.

**S256** là lựa chọn hiện đại. Dùng `plain` có nghĩa challenge bằng chính verifier, làm giảm bảo vệ nếu attacker đọc được authorization request. Không chọn plain cho flow mới.

### 4.2. Tình huống code bị đánh cắp

Code K được phát cho challenge C=S256(V). Attacker lấy K nhưng không biết V. Gửi K kèm V2 → S256(V2)≠C → token endpoint từ chối. Client hợp lệ giữ V nên có thể đổi K sau khi các điều kiện khác (client, redirect URI, expiry, one-time code) hợp lệ.

PKCE không mã hóa authorization code và **không bảo vệ access token đã bị đánh cắp sau khi cấp**. Nếu attacker lấy cả K và V, PKCE không còn chặn được hành động dùng chúng; vì vậy vẫn cần HTTPS, tránh rò qua log, redirect URI hợp lệ và bảo vệ session/client runtime.

### 4.3. Public và confidential clients

- **Public clients** như native app, SPA không thể giữ một client secret lâu dài. RFC 9700 yêu cầu public clients sử dụng PKCE cho authorization code.
- **Confidential web clients** có client secret được bảo vệ phía server vẫn **được khuyến nghị** dùng PKCE để tránh code injection/misuse. Client authentication không thay thế hoàn toàn sự ràng buộc **một code với một lượt khởi tạo**.
- Authorization Server phải thực thi PKCE khi challenge được gửi và chống downgrade (ví dụ không bỏ qua challenge để nhận verifier sai). Chỉ thấy `code_challenge` trên Network là **chưa đủ** chứng minh server kiểm tra đúng.

PKCE cũng có thể cung cấp bảo vệ CSRF theo RFC 9700, với điều kiện provider thật sự hỗ trợ và client có transaction binding an toàn. Nhưng PKCE không tự xác minh ID Token và không đảm nhiệm quyền nghiệp vụ của người dùng.

## 5. nonce: gắn ID Token với lượt xác thực OIDC

### 5.1. ID Token hợp lệ về chữ ký chưa chắc thuộc lượt login này

OIDC client gửi nonce ngẫu nhiên trong authentication request; provider phản hồi qua **claim nonce trong ID Token**. Khi ID Token đến, client xác minh chữ ký/issuer/audience/time và đối chiếu claim nonce với expected nonce đã lưu lúc khởi tạo.

```json
{
  "iss": "https://idp.example.test",
  "sub": "user-123",
  "aud": "web-client",
  "iat": 1769999400,
  "exp": 1770000000,
  "nonce": "nonce-of-this-transaction"
}
```

JSON này chỉ là **payload minh họa**, không phải một JWT có thể tin cậy. Không được chấp nhận chỉ vì JSON có nonce đúng: signature, thuật toán, khóa, issuer, audience, hạn dùng và các claim bắt buộc đều phải hợp lệ.

Nếu attacker phát lại ID Token từ lần login trước (nonce N1) vào transaction đang chờ nonce N2, so sánh N1≠N2 giúp client **từ chối ID Token replay/substitution**. Nonce phải có entropy cao, gắn với session và transaction, dùng đúng một lần.

### 5.2. Phân biệt nonce với state

`state` ở **authorization callback** chủ yếu nối authorization response với lượt khởi tạo. `nonce` ở **ID Token** nối bằng chứng xác thực người dùng với authentication request OIDC. Đừng dùng nonce để làm thay bước kiểm tra JWT signature hoặc dùng state như thể đó là nonce đã được provider ký trong ID Token.

Một số thư viện lưu giá trị random gốc, nhưng đưa **hash của giá trị đó** lên authorization request để làm nonce; validator phải dùng đúng quy ước của thư viện khi đối chiếu. Đừng tự sửa nonce bằng code tùy tiện làm đứt liên hệ giữa request và ID Token. Spring Security OAuth2 Login có cách tạo nonce nội bộ khi registration có scope `openid`.

### 5.3. Quy định OIDC Core và điểm dễ nhầm

Theo **OpenID Connect Core 1.0**, `nonce` là **OPTIONAL** trong **OIDC Authorization Code Flow**; nếu client gửi nonce thì provider phải đưa claim phù hợp vào ID Token và client phải kiểm tra. Trong **OIDC Implicit Flow**, nonce là **REQUIRED**; một số trường hợp Hybrid Flow cũng bắt buộc. Vì vậy khẳng định “nonce bắt buộc ở tất cả luồng OIDC” là sai.

RFC 9700 còn công nhận nonce, với các điều kiện bổ sung, có thể bảo vệ client OIDC confidential khỏi một số dạng code injection/CSRF. PKCE vẫn là cách trực tiếp, phổ biến để chứng minh quyền sở hữu **code** tại token endpoint, nên dùng **Authorization Code + PKCE + OIDC token validation**, và nonce khi có.

OAuth 2.0 thuần không sinh ra ID Token/nonce OIDC theo mặc định. Không thêm tùy tiện tham số tên `nonce` vào OAuth2 request rồi khẳng định sẽ có ID Token để kiểm tra.

## 6. HTTP trace: giá trị nào xuất hiện trong request nào?

Các chuỗi `<...>` là placeholder; đây là sơ đồ trao đổi, **không** phải HTTP exchange có token thực.

**Bước 1 — bắt đầu login ở ứng dụng:**

```http
GET /oauth2/authorization/demo HTTP/1.1
Host: app.example.test
Cookie: JSESSIONID=<browser-session-id>
```

Ứng dụng tạo S, V, C=S256(V), N, lưu dữ liệu pending transaction và trả redirect tới IdP:

```http
HTTP/1.1 302 Found
Location: https://idp.example.test/authorize?response_type=code&client_id=web-client&redirect_uri=https%3A%2F%2Fapp.example.test%2Flogin%2Foauth2%2Fcode%2Fdemo&scope=openid%20profile&state=<random-state>&code_challenge=<s256-challenge>&code_challenge_method=S256&nonce=<random-nonce>
```

Authorization URL có `state`, `code_challenge`, `nonce`; **không được có `code_verifier` hoặc client secret**.

**Bước 2 — người dùng đăng nhập tại IdP và browser quay về callback:**

```http
GET /login/oauth2/code/demo?code=<authorization-code>&state=<same-state> HTTP/1.1
Host: app.example.test
Cookie: JSESSIONID=<browser-session-id>
```

Ở đây **client** kiểm tra state với pending transaction trước khi tiếp tục. Nếu callback trả `error=access_denied` hoặc state sai/hết hạn/đã dùng, không được tạo phiên đăng nhập thành công.

**Bước 3 — backend client gọi token endpoint:**

```http
POST /token HTTP/1.1
Host: idp.example.test
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&code=<authorization-code>&redirect_uri=https%3A%2F%2Fapp.example.test%2Flogin%2Foauth2%2Fcode%2Fdemo&client_id=web-client&code_verifier=<original-code-verifier>
```

Nếu client confidential, thêm **client authentication** đã đăng ký ở back channel (ví dụ HTTP Basic trên TLS); không chuyển client secret qua browser URL. Authorization Server xác minh đúng verifier với challenge của code, và kiểm tra client/redirect URI/code expiry/one-time semantics.

**Bước 4 — OIDC client nhận ID Token:**

```text
Verify ID Token signature + trusted algorithm/key
Verify iss, aud, exp, iat và claims bắt buộc theo flow
Compare nonce claim với nonce kỳ vọng của transaction
Verify callback/token gắn với provider và client đã khởi tạo
Tạo phiên app; hủy/tiêu thụ pending transaction
```

Nếu `nonce` sai, client phải từ chối ID Token; không tự chuyển sang dùng token payload chưa xác minh hoặc tạo principal từ access token.

## 7. Tình huống tấn công và hàng rào đúng

| Tình huống | Cách attacker thực hiện | Hàng rào kiểm tra đầu tiên | Kết quả đúng |
| --- | --- | --- | --- |
| **Login CSRF** | Gửi callback `code` từ tài khoản attacker vào browser nạn nhân | state/session binding ở OAuth client; PKCE/nonce có thể hỗ trợ theo chuẩn | Không có pending transaction khớp thì từ chối |
| **Code interception** | Lấy authorization code K trên đường redirect nhưng không có verifier | PKCE tại Authorization Server token endpoint | Không đổi K thành token |
| **Code injection** | Tráo code của một giao dịch vào callback giao dịch khác | state binding + PKCE/nonce tùy kiểu tấn công | Code không khớp verifier hoặc token không khớp transaction |
| **ID Token replay** | Phát lại ID Token cũ có nonce N1 trong lần login mới N2 | Nonce của ID Token sau verify chuẩn | Từ chối ID Token |
| **JWT giả** | Tạo JWT giả với nonce mong đợi nhưng chữ ký/issuer sai | JWT/OIDC signature + issuer/audience validation | Từ chối; nonce đúng không biến token giả thành hợp lệ |
| **Authorization-server mix-up** | Đổi authorization response giữa provider A và B | Kiểm tra issuer/provider tương ứng với giao dịch | Từ chối response/token sai provider |
| **Callback replay** | Gửi cùng state/code nhiều lần | Single-use transaction và code one-time tại server | Lần lặp bị từ chối |
| **Token theft sau login** | Lấy access token/JSESSIONID sau khi đã cấp | Token/session security khác | Ba giá trị không thay thế được bảo vệ token/cookie |

Trong client hỗ trợ **nhiều provider**, cần chống mix-up bằng issuer identification (ví dụ authorization response `iss` theo RFC 9207, đối chiếu ID Token `iss` trong OIDC, hoặc redirect URI riêng khi phù hợp). Không giả định state, PKCE, nonce **tự** giải quyết mọi lỗi chọn nhầm provider.

## 8. Các ranh giới bảo mật không được hiểu nhầm

- `state` không phải CSRF token dùng tự động cho **mọi POST/DELETE sau đăng nhập**. Với ứng dụng web sử dụng cookie session, vẫn cần cơ chế CSRF cho nghiệp vụ theo chính sách của Spring Security.
- PKCE không thay HTTPS, client authentication (với confidential client), exact redirect URI, kiểm soát code expiry, issuer và one-time code.
- Nonce không thay xác minh chữ ký JWT, issuer, audience, thời gian, algorithm allowlist và xác định UserInfo/protocol claims theo OIDC Core.
- Cả ba không bảo vệ access token **đã bị trộm**, không xử lý XSS, session fixation, logout và phân quyền của ứng dụng.
- Không tin redirect URI đến domain tùy ý hay tham số `returnUrl` attacker nhập chỉ vì state hợp lệ. Phải allowlist đích, tránh open redirect.
- Không ghi code, verifier, token hay session cookie vào access log hoặc trace công khai. State và nonce có thể lộ trong authorization URL, nên thiết kế bảo vệ dựa trên **ràng buộc giao dịch và nonce randomness**, không coi URL là kho secret.
- Không dùng `code_challenge_method=plain` cho thiết kế mới. Không hardcode `state`/`nonce`/`code_verifier`, không dùng lại qua nhiều lượt login.
- Khi chạy nhiều tab, yêu cầu lưu transaction phải có chính sách rõ ràng: cấu hình repository có thể chỉ giữ một authorization request; callback khác thứ tự có thể bị từ chối đúng cách, không ghép sai verifier/nonce.

## 9. Spring Security 6.x và Spring Boot 3.x (Servlet OAuth2 Login)

### 9.1. Dependency và registration

Ví dụ là **Spring MVC** với Java 17+, Spring Boot 3.x, không dùng WebFlux API. Trong dự án đã có Boot plugin/dependency management, thêm các dependency:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Mẫu `src/main/resources/application.yml`:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          demo:
            provider: corporate
            client-id: REPLACE_WITH_REGISTERED_CLIENT_ID
            client-secret: REPLACE_FROM_SECRET_STORE
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
        provider:
          corporate:
            issuer-uri: https://idp.example.test
```

Đây là **cấu hình minh họa**, không chạy login được cho đến khi điền issuer/client ID/secret thật, đăng ký redirect URI tại IdP và cấu hình HTTPS/proxy đúng. Đưa client secret vào secret manager/biến môi trường khi triển khai thực tế, không lưu vào Git. `scope=openid` là điều kiện OIDC: OpenID Provider phát ID Token; ứng dụng phải xác minh ID Token.

### 9.2. Bật PKCE cho cả confidential client

Tạo `src/main/java/com/example/demo/OAuthLoginConfig.java`:

```java
package com.example.demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizationRequestResolver;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizationRequestCustomizers;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OAuthLoginConfig {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            ClientRegistrationRepository clientRegistrations) throws Exception {

        var resolver = new DefaultOAuth2AuthorizationRequestResolver(
                clientRegistrations, "/oauth2/authorization");

        // Cần PKCE S256 cả khi backend giữ client secret.
        // Spring vẫn sinh state; scope openid còn kích hoạt OIDC nonce.
        resolver.setAuthorizationRequestCustomizer(
                OAuth2AuthorizationRequestCustomizers.withPkce());

        return http
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers("/", "/error").permitAll()
                        .anyRequest().authenticated())
                .oauth2Login(oauth2 -> oauth2
                        .authorizationEndpoint(endpoint -> endpoint
                                .authorizationRequestResolver(resolver)))
                .build();
    }
}
```

Ở Spring Security, `DefaultOAuth2AuthorizationRequestResolver` tạo state, và khi scope chứa `openid` cũng áp dụng nonce của OIDC. `OAuth2AuthorizationRequestCustomizers.withPkce()` thêm challenge vào authorization request; verifier được giữ trong **attributes của authorization request** cho token exchange. Thư viện tự quản lý việc so state với authorization request đã lưu và xác minh ID Token OIDC. Nếu tự viết custom resolver hoặc authorization request repository, không làm mất dữ liệu giao dịch đó.

Spring Security tự kích hoạt PKCE cho public client (client authentication method `none`) hoặc khi `ClientSettings.requireProofKey=true`. Đoạn customizer trên cho thấy chủ đích **áp dụng PKCE cả confidential client**, phù hợp khuyến nghị RFC 9700. Với provider không hỗ trợ PKCE trong cấu hình cũ, phải kiểm tra/đánh giá hỗ trợ của provider trước khi triển khai.

### 9.3. Đọc danh tính đã xác thực

Trong dự án đã có `@SpringBootApplication`, thêm controller (OIDC only) tại `src/main/java/com/example/demo/MeController.java`:

```java
package com.example.demo;

import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class MeController {

    @GetMapping("/me")
    public Map<String, String> me(@AuthenticationPrincipal OidcUser user) {
        return Map.of("subject", user.getSubject());
    }
}
```

Chỉ tạo authenticated session sau khi Spring OAuth2 Login hoàn tất callback, token exchange và OIDC validation. Nếu registration là OAuth 2.0 thuần (không openid), principal có thể là `OAuth2User` chứ không phải `OidcUser`. Mã này **không** tự xác thực JWT; thư viện xử lý khi hoàn thành OIDC flow.

Mở `/oauth2/authorization/demo` để bắt đầu. Trong Developer Tools → Network, response 302 Location phải có `state` và (khi PKCE bật) `code_challenge_method=S256`, `code_challenge`; nếu có scope `openid` thì còn có `nonce`. **Không** được có `code_verifier` hay client secret trong Location.

## 10. Java 17 độc lập: chứng minh công thức PKCE và so state/nonce

Lưu đoạn code dưới đây vào file `LoginProofDemo.java`; dùng Java 17+ có thể biên dịch/chạy không cần Spring. Chương trình mô phỏng sinh giá trị và chứng minh công thức **S256**, không tự thực hiện OAuth, không thay được client–server flow và **không** xác minh JWT.

```java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.util.Base64;

public class LoginProofDemo {

    private static final SecureRandom RANDOM = new SecureRandom();

    record Pending(
            String state,
            String verifier,
            String challenge,
            String nonce) {}

    static String randomToken() {
        byte[] bytes = new byte[32]; // 256-bit entropy
        RANDOM.nextBytes(bytes);
        return Base64.getUrlEncoder().withoutPadding()
                .encodeToString(bytes);
    }

    static String s256(String verifier) {
        try {
            byte[] hash = MessageDigest.getInstance("SHA-256")
                    .digest(verifier.getBytes(StandardCharsets.US_ASCII));
            return Base64.getUrlEncoder().withoutPadding()
                    .encodeToString(hash);
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("No SHA-256", e);
        }
    }

    static boolean same(String expected, String actual) {
        return MessageDigest.isEqual(
                expected.getBytes(StandardCharsets.US_ASCII),
                actual.getBytes(StandardCharsets.US_ASCII));
    }

    static Pending startLogin() {
        String verifier = randomToken();
        return new Pending(
                randomToken(), verifier, s256(verifier), randomToken());
    }

    public static void main(String[] args) {
        Pending p = startLogin();

        System.out.println("verifierLength=" + p.verifier().length());
        System.out.println("challengeLength=" + p.challenge().length());

        System.out.println("pkceCorrect=" +
                same(s256(p.verifier()), p.challenge()));
        System.out.println("pkceWrong=" +
                same(s256("x" + p.verifier()), p.challenge()));

        System.out.println("stateMatches=" + same(p.state(), p.state()));
        System.out.println("oldNonceMatches=" +
                same("old-nonce", p.nonce()));
    }
}
```

Chạy:

```bash
javac LoginProofDemo.java
java LoginProofDemo
```

Output chính xác:

```text
verifierLength=43
challengeLength=43
pkceCorrect=true
pkceWrong=false
stateMatches=true
oldNonceMatches=false
```

Base64URL không padding của 32 byte cho ra đúng 43 ký tự; S256 SHA-256 cho 32 byte hash nên challenge cũng 43 ký tự. `pkceWrong=false` chứng minh verifier khác không giải được challenge. Phép so state/nonce ở đây chỉ minh họa: trong ứng dụng thực phải lấy expected từ **transaction đúng browser** và chỉ so nonce sau khi **xác minh ID Token đầy đủ**. Không in ra secret/verifier thực tế lên log.

## 11. Kế hoạch kiểm thử integration với provider thật hoặc mock OP

Chạy các ca dưới đây trên môi trường test đã cấu hình OIDC Client + OP. Muốn test nonce riêng biệt, mock OP phải cấp ID Token có **chữ ký hợp lệ, issuer/audience đúng**, rồi cố ý đổi **riêng claim nonce**; nếu JWT đã hỏng chữ ký, test chỉ cho thấy signature validation.

| Test | Thao tác | Kỳ vọng |
| --- | --- | --- |
| Happy path | Login, callback state đúng, verifier đúng, ID Token nonce đúng | Tạo phiên app; `GET /me` thành công |
| Callback sai state | Sửa `state` ở callback | Client từ chối; không nhận code để đăng nhập |
| Callback chưa khởi tạo | Dán URL callback vào browser mới không có pending transaction | Client từ chối |
| Replay state/code | Gọi callback 2 lần sau khi transaction đã tiêu thụ | Lần sau thất bại; authorization code cũng one-time |
| Sai PKCE verifier | Mock request/token endpoint dùng verifier V2 khác challenge C | Provider từ chối (thường `invalid_grant`), không phát token |
| Thiếu challenge/downgrade | Test xóa challenge hoặc chọn method không chấp nhận | Không được lặng lẽ hoàn tất flow vốn yêu cầu PKCE |
| ID Token sai nonce | Mock OP phát token hợp lệ chữ ký nhưng nonce N2 thay vì expected N1 | OIDC client từ chối |
| ID Token thiếu nonce sau khi gửi nonce | Mock OP bỏ claim nonce | Client từ chối |
| ID Token có nonce đúng nhưng signature/iss/aud sai | Giữ nonce, làm sai các claim/chữ ký khác | Client từ chối |
| Hai browser/tabs | Khởi tạo các transaction khác nhau, đổi thứ tự callback | Không ghép sai state/nonce/verifier, reject transaction đã hết hạn |
| Provider mix-up | Bắt đầu ở A, trả response/token từ B | Client không tạo session |
| Không có cookie sau login | Browser khác gọi `/me` | Ứng dụng yêu cầu login lại |

Khi test một lỗi, xác định **tầng gây lỗi**: state ở OAuth client, verifier ở authorization server token endpoint, nonce ở OIDC client ID Token validator. Xem Network và log an toàn chỉ với mã lỗi và correlation ID; không đưa code, verifier hay token vào log.

## 12. Lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân thường gặp | Kiểm tra đúng |
| --- | --- | --- |
| `authorization_request_not_found`, state mismatch | Cookie session không đi qua callback, giao dịch bị ghi đè, stale callback, lỗi reverse proxy | Kiểm tra session cookie, callback URL, transaction repository, TTL |
| PKCE `invalid_grant` | Verifier sai, code hết hạn/đã dùng, redirect URI/client mismatch | Kiểm tra error từ token endpoint, không log giá trị thật |
| Có challenge nhưng verifier sai vẫn đổi được | Authorization Server không kiểm PKCE hoặc bị downgrade | Negative test với verifier sai; xác minh cấu hình/provider |
| Nonce mismatch | Token của transaction khác, nonce bị custom resolver sửa, mất pending session | Đối chiếu ID Token sau verify và authorization request đã lưu |
| Nonce không xuất hiện | `scope` thiếu `openid` hoặc OAuth2 thuần | Kiểm tra OIDC registration; không bịa nonce trong client |
| Login được nhưng ID Token invalid | App decode JWT mà không verify signature, issuer/audience/time | Dùng OIDC client chuẩn; loại bỏ bypass |
| Hai tab login làm tab trước lỗi | Store chỉ giữ một pending request hoặc có transaction override | Thiết kế repository theo nhu cầu multi-tab; không dùng lại verifier |
| Open redirect sau login | Tin tùy tiện URL trong state/returnUrl | Allowlist đích trở về, dùng đường dẫn tương đối |
| Tắt CSRF toàn app vì đã có state | Nhầm login CSRF với CSRF của nghiệp vụ | Giữ CSRF protection cho request dùng cookie khi cần |
| Dùng nonce cố định mỗi user | Nonce không có transaction freshness | Tạo ngẫu nhiên theo từng lần login |

## 13. Checklist và câu hỏi tự kiểm tra

- **state:** random đủ mạnh, lưu theo phiên/trình duyệt, đối chiếu callback với transaction tồn tại, hết hạn và single-use.
- **PKCE:** sinh verifier đủ entropy (43–128 ký tự); dùng S256; giữ verifier kín tới token request; server xác minh chính xác challenge gắn với code.
- **nonce:** khi dùng OIDC và gửi nonce, client so nonce claim từ ID Token **đã validate** với transaction đang chờ; không dùng token cũ.
- **Độc lập:** kiểm tra issuer, audience, signature, expiry, exact redirect URI, client authentication, transport TLS, session security và authorization.
- **Thực nghiệm:** sửa sai từng state, verifier và nonce để xác minh mỗi lỗi bị từ chối **ở đúng tầng**.

Nếu phải nhớ một chuỗi duy nhất: **callback về client kiểm tra state → Authorization Server đổi code kiểm tra PKCE verifier → OIDC client nhận ID Token kiểm tra nonce và các claim/token validation**. Đây là cách trả lời chính xác “ba cơ chế bảo vệ phần nào” và cũng là hướng debug có thể kiểm chứng trên trace thật.

### Tài liệu gốc

- [RFC 6749 — OAuth 2.0](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 7636 — Proof Key for Code Exchange](https://www.rfc-editor.org/rfc/rfc7636)
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700)
- [RFC 9207 — Authorization Server Issuer Identification](https://www.rfc-editor.org/rfc/rfc9207)
- [OpenID Connect Core 1.0 — Authentication Request, nonce, ID Token Validation](https://openid.net/specs/openid-connect-core-1_0.html)
- [Spring Security — OAuth2 Client Authorization Grants](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorization-grants.html)
- [Spring Security API — DefaultOAuth2AuthorizationRequestResolver](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/web/DefaultOAuth2AuthorizationRequestResolver.html)
- [Spring Security API — OAuth2AuthorizationRequestCustomizers.withPkce()](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/web/OAuth2AuthorizationRequestCustomizers.html)
