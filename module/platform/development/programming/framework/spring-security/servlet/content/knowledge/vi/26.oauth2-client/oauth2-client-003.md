# Authorization Code, `state`, PKCE và `nonce` trong OAuth2 Client — Spring Security Servlet

## 1. Mục tiêu và ngữ cảnh

Trong ứng dụng **Spring Security Servlet**, một OAuth2 Client cho phép người dùng bắt đầu đăng nhập hoặc ủy quyền qua Authorization Server (nhà cung cấp danh tính), nhận **authorization code** qua trình duyệt, rồi dùng back-channel để đổi code lấy token. Với OpenID Connect (OIDC), luồng này còn có thể nhận **ID Token** phục vụ xác thực danh tính người dùng.

Ba giá trị dễ nhầm lẫn trong luồng là:

- **`state`**: ràng buộc *authorization response* với yêu cầu mà client đã khởi tạo, hạn chế CSRF/nhầm lẫn callback.
- **PKCE** (`code_verifier`, `code_challenge`): ràng buộc *authorization code* với client instance đã khởi tạo yêu cầu, khiến code bị đánh cắp khó đổi thành token.
- **`nonce`**: trong **OIDC**, ràng buộc **ID Token** với authentication request tương ứng, giúp phát hiện ID Token bị phát lại hoặc tráo đổi; không mặc định áp dụng cho mọi luồng OAuth2 không có OIDC.

Bài tập trung vào **Authorization Code** trong ứng dụng server-side dùng **Spring Boot 3.x, Spring Security 6.x, Java 17+, Spring MVC/Servlet**. Các ví dụ URL/issuer của Identity Provider (IdP) là địa chỉ minh họa; muốn đăng nhập end-to-end phải thay bằng IdP thật và đăng ký đúng client/redirect URI.

Điều quan trọng trước tiên là phân biệt hai mục đích:

| Mục đích | Chuẩn/mô hình | Kết quả chính |
| --- | --- | --- |
| Cho ứng dụng truy cập tài nguyên thay người dùng | OAuth 2.0 Authorization Code | Access token (có thể kèm refresh token), phạm vi quyền được cấp |
| Đăng nhập và xác thực danh tính người dùng | OpenID Connect trên OAuth 2.0 | ID Token cùng các token khác; thông tin danh tính được xác minh |
| API backend tự kiểm tra Bearer token của client gọi tới | OAuth2 Resource Server | Xác thực token nhận được; là trách nhiệm khác với OAuth2 Client |

**Access token không phải ID Token**: access token có audience/ngữ cảnh sử dụng của resource server; không tự suy ra danh tính bằng cách giải mã access token. ID Token dùng cho client để xác nhận đăng nhập OIDC; không gửi ID Token như access token đến API.

## 2. Các tác nhân, endpoint và dữ liệu được truyền

Authorization Code flow có bốn vai trò:

1. **Resource Owner / người dùng** sử dụng trình duyệt.
2. **User-Agent / browser** đi qua các redirect.
3. **OAuth2 Client / ứng dụng Spring Security** khởi tạo authorization request, giữ correlation data trong phiên và gọi token endpoint ở phía server.
4. **Authorization Server / IdP** xác thực người dùng, nhận consent khi cần, phát code và token; Resource Server là bên nhận access token khi gọi API.

Ví dụ URL (cần thay theo IdP và deployment):

```text
Ứng dụng Spring:         https://app.example.test
Bắt đầu OAuth2 login:     GET /oauth2/authorization/learning-idp
Authorization endpoint:   https://idp.example.test/oauth2/authorize
Callback do Spring nhận:  GET /login/oauth2/code/learning-idp
Token endpoint:           https://idp.example.test/oauth2/token
```

`learning-idp` là **registrationId** trong Spring Security, không phải một tham số chuẩn mà IdP bắt buộc phải biết. URL bắt đầu và callback ở trên là **mặc định thường gặp** của Spring Security OAuth2 Login Servlet; có thể tùy biến, khi đó phải sửa khớp cấu hình ở cả client lẫn IdP.

### 2.1. Trình tự end-to-end

```mermaid
sequenceDiagram
    participant B as Browser
    participant C as Spring OAuth2 Client
    participant A as Authorization Server / IdP

    B->>C: GET /oauth2/authorization/learning-idp
    C->>C: Tạo state, PKCE verifier/challenge; nonce nếu OIDC
    C->>C: Lưu authorization request trong session
    C-->>B: 302 tới authorization endpoint (state, challenge, nonce)
    B->>A: GET /authorize
    A->>B: Đăng nhập / consent (nếu cần)
    A-->>B: 302 tới redirect_uri?code=...&state=...
    B->>C: GET /login/oauth2/code/learning-idp?code=...&state=...
    C->>C: Tìm request đã lưu; đối chiếu state
    C->>A: POST /token (code, redirect_uri, code_verifier)
    A->>A: Kiểm tra code, client, redirect_uri, PKCE
    A-->>C: access_token; id_token nếu OIDC
    C->>C: Kiểm tra token; nonce trong ID Token nếu đã gửi
    C-->>B: Phiên đăng nhập và redirect sau thành công
```

Không có bước nào cần JavaScript frontend **giữ `client_secret` hoặc `code_verifier`** trong mô hình server-side này. Browser thấy authorization request và callback có code; token exchange diễn ra server-to-server. HTTPS và kiểm soát log/referrer vẫn quan trọng vì authorization code và token là dữ liệu nhạy cảm.

## 3. Bước 1: Tạo authorization request

Người dùng chọn nút đăng nhập tới `GET /oauth2/authorization/learning-idp`. Spring Security chọn ClientRegistration tương ứng và tạo một authorization request. Với code flow + PKCE + OIDC, URL đi tới IdP có các trường điển hình:

```http
GET /oauth2/authorize?
  response_type=code&
  client_id=learning-client&
  redirect_uri=https%3A%2F%2Fapp.example.test%2Flogin%2Foauth2%2Fcode%2Flearning-idp&
  scope=openid%20profile&
  state=<random-state>&
  code_challenge=<base64url-sha256-verifier>&
  code_challenge_method=S256&
  nonce=<random-oidc-nonce> HTTP/1.1
Host: idp.example.test
```

*Đoạn trên được xuống dòng để dễ đọc, không phải HTTP request nguyên văn để copy chạy.* Trong URL thực tế, query parameters được mã hóa URL đúng chuẩn. `state`, challenge và nonce là các chuỗi khác nhau; ví dụ không sử dụng literal `<random-state>` làm giá trị thật.

Ý nghĩa từng trường:

- `response_type=code`: client yêu cầu authorization code thay vì token trả trực tiếp ở front-channel.
- `client_id`: ID client đã đăng ký với IdP; **không phải secret**.
- `redirect_uri`: URI callback phải phù hợp đăng ký ở Authorization Server. Không lấy giá trị từ URL không đáng tin rồi chuyển tiếp tùy ý.
- `scope`: quyền/nhóm thông tin yêu cầu. Có `openid` thì đây là yêu cầu OIDC; ví dụ `profile` bổ sung thông tin hồ sơ tùy policy IdP.
- `state`: chuỗi khó đoán, do client khởi tạo và lưu để so khớp response.
- `code_challenge` + `code_challenge_method=S256`: bằng chứng PKCE được suy ra từ `code_verifier`. **Không gửi `code_verifier` trong URL authorization**.
- `nonce`: tham số **OIDC**, khi sử dụng phải được lưu và kiểm tra với claim `nonce` của ID Token. Luồng OAuth2 thuần không yêu cầu ID Token nên không áp dụng bước xác minh nonce như OIDC.

Spring Security Servlet thường lưu **authorization request và correlation data** trong `HttpSessionOAuth2AuthorizationRequestRepository`. Do đó browser cần duy trì đúng cookie phiên tới callback. Thiết kế stateless không dùng session phải tự xây một repository/cơ chế state an toàn khác; không xóa lưu trữ state rồi mong callback vẫn hoạt động.

## 4. Bước 2: IdP xác thực và redirect về client

Sau khi người dùng đăng nhập và cấp quyền khi cần, Authorization Server tạo **authorization code ngắn hạn, dùng một lần**, rồi redirect browser về URI đã đăng ký với code và state:

```http
HTTP/1.1 302 Found
Location: https://app.example.test/login/oauth2/code/learning-idp?code=<one-time-code>&state=<same-state>
```

Client phải kiểm tra callback khớp với authorization request nó đã khởi tạo: đúng session, đúng `state`, đúng IdP/client registration và các thông tin đã lưu. **Không** đổi một code không có correlation state hợp lệ lấy token theo cách “thử xem có thành công không”.

Nếu người dùng từ chối consent hoặc có lỗi, callback có thể dùng `error` và `state` thay vì `code`; đây là nhánh thất bại cần xử lý và ghi nhận an toàn. Redirect của IdP không chứng minh code hợp lệ cho đến khi client hoàn tất xác minh và token exchange.

**Tại sao phải lưu state ở server?** Nếu client chỉ nhận `state` từ query rồi so sánh với một giá trị do chính callback gửi lại, phép kiểm tra không có ý nghĩa. Giá trị phải được tạo trước, ràng buộc với giao dịch và giữ trong nơi mà attacker không tự điều khiển.

## 5. Bước 3: Back-channel token exchange và PKCE

Sau khi callback hợp lệ, client gửi authorization code lên **token endpoint** qua kênh server-to-server, kèm `code_verifier` đã giữ từ bước khởi tạo:

```http
POST /oauth2/token HTTP/1.1
Host: idp.example.test
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&code=<one-time-code>&redirect_uri=https%3A%2F%2Fapp.example.test%2Flogin%2Foauth2%2Fcode%2Flearning-idp&code_verifier=<original-verifier>
```

Đoạn HTTP là minh họa các tham số quan trọng; **confidential client** còn phải xác thực với token endpoint theo `client-authentication-method` được cấu hình, ví dụ HTTP Basic hoặc `private_key_jwt`. Client công khai (`public client`) không có secret phải dựa vào cơ chế phù hợp gồm PKCE. Không đặt `client_secret` vào URL, browser hoặc các tài liệu chia sẻ.

Authorization Server phải đối chiếu code với client/redirect URI và, khi authorization request có PKCE, kiểm tra:

```text
BASE64URL-ENCODE(SHA256(ASCII(code_verifier))) == code_challenge đã lưu
```

Với PKCE `S256`, `code_verifier` là chuỗi ngẫu nhiên thuộc tập ký tự URL-safe (RFC 7636 yêu cầu 43–128 ký tự hợp lệ). `code_challenge` trong request đầu tiên là kết quả băm và mã hóa base64url **không padding**. Không tự đặt `code_verifier` ngắn, đoán được, hoặc tái sử dụng một verifier cho nhiều giao dịch.

Một request khác chỉ đánh cắp được authorization code nhưng **không có verifier đúng** sẽ không đổi code lấy token nếu Authorization Server triển khai PKCE đúng. PKCE không thay thế việc kiểm tra state ở callback, không thay thế client authentication cho confidential client, và cũng không loại bỏ việc xác minh redirect URI, token, TLS hay quyền người dùng.

### 5.1. Demo PKCE chuẩn Java 17+ chạy độc lập

Tập tin **`PkceExample.java`** sau chỉ dùng Java standard library. Nó kiểm tra test vector công khai của RFC 7636 và tạo một verifier mới với 32 bytes từ `SecureRandom` (256 bit entropy):

```java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Base64;

public class PkceExample {
    static String challengeS256(String verifier) throws Exception {
        byte[] digest = MessageDigest.getInstance("SHA-256")
            .digest(verifier.getBytes(StandardCharsets.US_ASCII));
        return Base64.getUrlEncoder()
            .withoutPadding()
            .encodeToString(digest);
    }

    static String newVerifier() {
        byte[] random = new byte[32];
        new SecureRandom().nextBytes(random);
        return Base64.getUrlEncoder()
            .withoutPadding()
            .encodeToString(random);
    }

    public static void main(String[] args) throws Exception {
        String rfcVerifier =
            "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk";
        String rfcChallenge =
            "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM";
        System.out.println("RFC 7636 matches: "
            + challengeS256(rfcVerifier).equals(rfcChallenge));

        String verifier = newVerifier();
        System.out.println("Verifier length: " + verifier.length());
        System.out.println("Challenge length: "
            + challengeS256(verifier).length());
    }
}
```

Biên dịch và chạy:

```bash
javac PkceExample.java
java PkceExample
```

Stdout chính xác (chuỗi ngẫu nhiên không được in):

```text
RFC 7636 matches: true
Verifier length: 43
Challenge length: 43
```

32 bytes mã hóa base64url không padding luôn thành 43 ký tự, nên chiều dài output ổn định; **giá trị verifier/challenge thực tế thay đổi mỗi lần chạy**. Đây là demo thuật toán PKCE, không phải OAuth2 Client hoàn chỉnh. Khi dùng Spring Security, để framework sinh và lưu verifier, không tự hard-code test vector làm verifier của người dùng.

## 6. `state`, PKCE và `nonce`: ba đối tượng kiểm tra khác nhau

| Thành phần | Sinh/lưu ở đâu? | Có mặt ở request nào? | Kiểm tra ở đâu? | Bảo vệ chính |
| --- | --- | --- | --- | --- |
| `state` | Client tạo ngẫu nhiên, giữ với authorization request trong session/correlation store | Authorization request và callback | Client so state callback với giao dịch đã lưu | Chống unsolicited callback/login CSRF và nhầm giao dịch |
| PKCE verifier/challenge | Client tạo `code_verifier`, giữ bí mật; gửi `code_challenge=S256(verifier)` | Challenge ở authorization request; verifier chỉ ở token request | Authorization Server kiểm tra verifier tương ứng code | Hạn chế đổi token bằng code bị lấy cắp |
| OIDC `nonce` | OIDC client tạo, lưu trong giao dịch | Nonce trong authentication request; giá trị được ràng buộc trong ID Token | Client kiểm tra ID Token nonce khi request có nonce | Chống phát lại/tráo ID Token trong giao dịch đăng nhập |

### 6.1. Hai câu hỏi bảo mật khác nhau

- **`state`** trả lời: “Callback này có thuộc authorization request mà chính client/session vừa khởi tạo không?”
- **PKCE** trả lời: “Bên đổi code có sở hữu code verifier đã cam kết khi xin code hay không?”
- **OIDC `nonce`** trả lời: “ID Token được trả về có khớp authentication request đã gắn nonce không?”

Ví dụ, kiểm tra PKCE thành công không tự chứng minh response tới đúng browser session. Ngược lại, `state` hợp lệ không chứng minh một authorization code bị lộ không thể bị đổi token nếu Authorization Server không có PKCE. Dùng **cả state lẫn PKCE** khi thích hợp, mỗi cơ chế giải quyết một rủi ro khác nhau.

### 6.2. Khi nào cần nonce?

**OAuth2 thuần** (scope không có `openid`, mục tiêu là truy cập API) không nhận ID Token theo chuẩn OIDC, nên không có claim nonce trong ID Token để xác minh. Đừng nhầm nonce với CSRF token dành cho form hoặc với state của OAuth2.

**OIDC Authorization Code** (scope chứa `openid` và IdP tuân thủ OIDC) có ID Token. Theo OIDC Core, tham số nonce **không bắt buộc tuyệt đối trong mọi Authorization Code request**, nhưng khi client gửi nonce thì ID Token trả về phải có nonce phù hợp và client phải kiểm tra. Một số flow khác của OIDC có quy định nonce chặt hơn. Trong ứng dụng Spring Security OIDC login, hãy để framework quản lý nonce mặc định nếu có, và giữ validation nếu tùy biến request hoặc token processing.

Nonce phải được sinh ngẫu nhiên, liên kết với **đúng giao dịch đăng nhập**, không tái sử dụng một giá trị cố định trên toàn ứng dụng. Không thay nonce bằng state và không so với access token. Ngoài nonce, ID Token vẫn cần kiểm tra **chữ ký (hoặc cơ chế bảo vệ tương ứng), issuer, audience, expiration** và các ràng buộc liên quan như `azp` khi áp dụng. Spring Security OIDC login có các validator chuẩn; khi viết custom flow không được lược bỏ.

## 7. Cấu hình Spring Security Servlet cho Authorization Code + PKCE

Ví dụ sau minh họa **OIDC login** theo Authorization Code trên server-side Spring Boot. Nó dùng `state`/authorization-request repository của framework và **bật PKCE S256 một cách tường minh** qua `OAuth2AuthorizationRequestCustomizers.withPkce()`.

### 7.1. Dependencies và đăng ký client

Trong project Spring Boot 3.x, Java 17+ được tạo từ Spring Initializr, thêm các dependency Gradle Groovy sau; phần plugin, version và dependency management thuộc project gốc:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Mẫu **`src/main/resources/application.yml`**:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          learning-idp:
            provider: learning-idp
            client-id: ${OAUTH_CLIENT_ID}
            client-secret: ${OAUTH_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
        provider:
          learning-idp:
            issuer-uri: https://idp.example.test/realms/learning
```

**Phải thay `issuer-uri` bằng issuer OIDC có discovery endpoint hoạt động**, thiết lập `OAUTH_CLIENT_ID`, `OAUTH_CLIENT_SECRET` bằng secret manager/env của môi trường thực, và đăng ký callback trùng URI thực tế tại IdP (ví dụ `http://localhost:8080/login/oauth2/code/learning-idp` khi thử localhost được IdP cho phép). Đây là cấu hình **confidential server-side client** sử dụng client secret; public client không copy nguyên phương án này. `issuer-uri` giúp Spring lấy endpoints và khóa xác minh từ metadata OIDC của IdP.

`scope: openid, profile` khiến phần login sử dụng OIDC và có ID Token. Nếu đổi sang OAuth2 thuần (không `openid`), không thể giả định controller có `OidcUser`, hoặc sẽ có nonce/ID Token.

### 7.2. Main class

Tập tin **`src/main/java/com/example/oauthflow/OAuthFlowApplication.java`**:

```java
package com.example.oauthflow;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OAuthFlowApplication {
    public static void main(String[] args) {
        SpringApplication.run(OAuthFlowApplication.class, args);
    }
}
```

### 7.3. SecurityFilterChain và PKCE

Tập tin **`src/main/java/com/example/oauthflow/SecurityConfig.java`**:

```java
package com.example.oauthflow;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizationRequestResolver;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizationRequestCustomizers;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            ClientRegistrationRepository registrations) throws Exception {

        DefaultOAuth2AuthorizationRequestResolver resolver =
            new DefaultOAuth2AuthorizationRequestResolver(
                registrations, "/oauth2/authorization");

        // Thêm PKCE cho cả confidential client trong ví dụ.
        resolver.setAuthorizationRequestCustomizer(
            OAuth2AuthorizationRequestCustomizers.withPkce());

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(login -> login
                .authorizationEndpoint(endpoint ->
                    endpoint.authorizationRequestResolver(resolver)
                )
            );

        return http.build();
    }
}
```

`DefaultOAuth2AuthorizationRequestResolver` tạo URL authorization, gồm state và các thuộc tính cần thiết; customizer PKCE tạo **code challenge** và giữ **verifier** trong authorization request để sử dụng tại token exchange. Trong nhiều bản Spring Security, PKCE có thể được bật mặc định cho public client có `ClientAuthenticationMethod.NONE`; đoạn config trên chọn bật rõ ràng **cả với confidential client**.

`oauth2Login()` gắn login authorization-code flow vào filter chain Servlet. Khi cần dùng access token để gọi API khác thay người dùng, tìm hiểu thêm OAuth2 Authorized Client (`OAuth2AuthorizedClientManager`, `oauth2Client`) và cơ chế lưu token phù hợp; đó là nhiệm vụ tiếp theo, không phải lý do tự lấy token từ query của callback.

**Không tự viết controller xử lý `/login/oauth2/code/learning-idp`** trong cấu hình này: `OAuth2LoginAuthenticationFilter` của Spring Security xử lý callback, kiểm tra authorization request/state và thực hiện phần exchange/authentication tương ứng. Đừng mở GET callback công khai bằng một handler tự chế rồi bỏ qua các validation mặc định.

### 7.4. Trang thử đăng nhập

Tập tin **`src/main/java/com/example/oauthflow/MeController.java`**:

```java
package com.example.oauthflow;

import java.util.Map;

import org.springframework.http.MediaType;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class MeController {
    @GetMapping(value = "/", produces = MediaType.TEXT_HTML_VALUE)
    String home() {
        return """
            <!doctype html>
            <html lang="vi">
            <head><meta charset="utf-8"><title>OIDC Login Demo</title></head>
            <body>
                <h1>OIDC Login Demo</h1>
                <a href="/oauth2/authorization/learning-idp">
                    Đăng nhập qua Identity Provider
                </a>
            </body>
            </html>
            """;
    }

    @GetMapping("/me")
    Map<String, String> me(@AuthenticationPrincipal OidcUser user) {
        return Map.of("subject", user.getSubject());
    }
}
```

`/` mở được khi chưa đăng nhập; link gửi browser đến filter khởi tạo login. `/me` đòi đã xác thực và trong **cấu hình OIDC** trả `sub` (subject identifier) của người dùng, không phơi token ra response. Với OAuth2 provider không hỗ trợ OIDC, dùng loại principal thích hợp thay vì ép `OidcUser`.

Chạy từ Gradle Wrapper của project:

```bash
./gradlew bootRun
```

Trên Windows PowerShell dùng `.\gradlew.bat bootRun`. Chỉ chạy end-to-end sau khi cấu hình **IdP thực, redirect URI và biến môi trường** hợp lệ. Với issuer giả `idp.example.test`, không có session đăng nhập thật và không có stdout đăng nhập nào được đảm bảo.

### 7.5. Quan sát các điểm trong luồng

Trong DevTools → Network (Preserve log), bắt đầu ở `/oauth2/authorization/learning-idp`:

1. Xem response 302 của ứng dụng. URL IdP phải có `response_type=code`, `client_id`, `redirect_uri`, `state`; sau khi bật PKCE phải thấy `code_challenge_method=S256`, `code_challenge`. Với OIDC và request handler tương ứng có thể thấy `nonce`.
2. Xác thực ở IdP; browser nhận callback với `code` và `state` (hoặc `error` khi thất bại). Kiểm tra state callback khớp request khởi tạo, không copy giá trị này sang một session khác.
3. Token exchange thông thường diễn ra ở **server**, nên DevTools của browser không hiển thị `code_verifier` gửi tới token endpoint. Không vì “không thấy” mà chuyển verifier ra client JavaScript.
4. Khi thành công, browser có session của ứng dụng và `/me` trả subject OIDC tương ứng. Khi thất bại, đọc Spring Security log đã lọc thông tin nhạy cảm và IdP logs thay vì in code, token hay secret vào log.

Phần lớn OAuth2 redirect được thực hiện qua **top-level GET**. Nếu dùng phương thức callback khác như OIDC `response_mode=form_post`, phải xem kỹ cookie `SameSite` và CSRF của endpoint callback: một cross-site POST có thể không mang cookie phiên khi `SameSite=Lax`. Không đổi cookie policy bừa bãi; phân tích cách IdP trả callback và đường đi HTTPS.

## 8. Token exchange, session và bảo mật phía sau proxy

### 8.1. Trách nhiệm của Spring Security mặc định

Với OAuth2 Login Servlet, các thành phần chính:

| Thành phần | Vai trò |
| --- | --- |
| `OAuth2AuthorizationRequestRedirectFilter` | Xử lý request khởi tạo và redirect browser đến Authorization Server |
| `DefaultOAuth2AuthorizationRequestResolver` | Xây dựng authorization request từ `ClientRegistration`, state và các tham số tùy biến |
| `HttpSessionOAuth2AuthorizationRequestRepository` | Mặc định giữ authorization request giữa redirect và callback để xác minh correlation |
| `OAuth2LoginAuthenticationFilter` | Nhận callback, sử dụng authorization request đã lưu và bắt đầu xác thực |
| `OAuth2AccessTokenResponseClient` và provider tương ứng | Đổi code lấy token theo cấu hình client/provider |
| OIDC provider/validator của Spring Security | Kiểm tra ID Token, gồm nonce khi đã tham gia authentication request |

Luồng có thể khác khi người dùng tự thay authentication filter, custom authorization request repository hoặc custom token response client. Khi tùy biến, phải giữ nguyên tính chất **state được lưu trước và kiểm tra một lần**, verifier tương ứng code challenge, ID Token được xác minh.

### 8.2. HTTP session và cookie

Một lỗi thực tế là browser quay về callback nhưng Spring không tìm thấy authorization request đã lưu. Thường gặp khi:

- Cookie phiên (`JSESSIONID`) không được gửi về cùng application origin do `SameSite`, `Secure`, Domain, Path hoặc HTTP/HTTPS khác nhau.
- Redirect sang hostname khác so với hostname tạo session.
- Ứng dụng chạy nhiều instance không chia sẻ session, hoặc load balancer đổi node và session chỉ tồn tại cục bộ.
- Session bị hết hạn/đã hủy khi người dùng đang đăng nhập tại IdP.
- Tự đặt `SessionCreationPolicy.STATELESS` hoặc custom repository rồi bỏ đi lưu trữ correlation data.
- Authorization request được khởi tạo hai lần, tab/flow cũ bị ghi đè trong một thiết kế chỉ lưu một pending request.

Trong Spring Security, lỗi callback thiếu giao dịch có thể biểu hiện dạng `authorization_request_not_found`. **Đừng “sửa” bằng cách bỏ so khớp state**. Hãy kiểm tra session cookie, storage và luồng redirect. Trường hợp hai tab đăng nhập đồng thời có thể cần thiết kế repository lưu nhiều pending authorization requests theo state, tùy yêu cầu sản phẩm.

### 8.3. Reverse proxy và callback URI

Với app sau Nginx/Ingress, `{baseUrl}` trong `redirect-uri` phải trở thành URL công khai thật, **không phải `http://internal-service:8080/...`**. Khi ứng dụng dựa vào forwarded headers (`Forwarded`, `X-Forwarded-Proto`, `X-Forwarded-Host`), cấu hình proxy và Spring để **chỉ tin các forwarded headers từ proxy tin cậy**. Một lựa chọn trong Spring Boot là `server.forward-headers-strategy=framework` khi hạ tầng có trust boundary phù hợp; kiểm tra lại URI được tạo trước khi đăng ký ở IdP.

Lỗi redirect URI mismatch thường xuất hiện do HTTP↔HTTPS, host, port, context path hoặc proxy path rewrite khác nhau. So sánh `redirect_uri` của request authorization với giá trị đăng ký tại IdP và giá trị gửi lại ở token request. Không cố vượt qua bằng một open redirect hoặc wildcard callback thiếu kiểm soát.

## 9. Bảng lỗi phổ biến và cách chẩn đoán

| Dấu hiệu | Nguyên nhân cần xác minh | Hướng xử lý đúng |
| --- | --- | --- |
| Bị lỗi ngay khi mở `/oauth2/authorization/{registrationId}` | `registrationId` sai, thiếu `ClientRegistration`, issuer metadata không truy cập được | So khớp YAML registration/provider ID và endpoint discovery |
| IdP báo `invalid_redirect_uri` hoặc redirect mismatch | Host/scheme/port/path callback không đúng đăng ký | Đồng bộ redirect_uri giữa Spring, proxy và IdP |
| Callback có `code` nhưng báo `authorization_request_not_found` | Mất session/authorization request, state khác phiên, cookie bị chặn | Kiểm tra session cookie, SameSite, shared session, host và repository |
| Callback có `state` khác state khi khởi tạo | Flow bị tráo/nhầm, session bị thay hoặc pending request khác | Từ chối callback, tìm nguyên nhân; không chấp nhận state do caller tự bịa |
| Token endpoint trả `invalid_grant` | Code hết hạn/dùng lại, redirect URI khác, code client khác, hoặc PKCE verifier sai | Đọc log phía IdP ở mức an toàn, kiểm tra code/verifier/callback cùng một giao dịch |
| Authorization URL thiếu `code_challenge` | PKCE chưa được bật cho loại client/chain hiện tại | Kiểm tra resolver đúng chain, `withPkce()`, provider hỗ trợ S256 |
| Có challenge nhưng token exchange thiếu verifier | Request repository hoặc custom token client đánh mất thuộc tính PKCE | Giữ verifier từ auth request tới token request, kiểm tra custom code |
| Authorization Server trả về ID Token nhưng nonce không khớp | ID Token thuộc giao dịch khác, provider lỗi hoặc custom code làm mất nonce | Từ chối ID Token, kiểm tra correlation; không tắt validator |
| Không thấy `nonce`/ID Token | Đang dùng OAuth2 thuần, chưa yêu cầu scope `openid` hoặc IdP không hỗ trợ OIDC | Xác định đang cần login OIDC hay OAuth2 authorization thuần |
| `invalid_client` từ token endpoint | Client secret sai, authentication method không khớp, ID client/IdP sai | Sửa credential và phương thức xác thực ở server; không đưa secret vào frontend |
| `/me` không phải OIDC principal | Registration không yêu cầu `openid`, login không qua OIDC hoặc mapping không đúng | Kiểm tra scope và loại principal; không cast tùy tiện |
| Flow dùng cookie bị lỗi qua proxy | Wrong scheme, forwarded headers không chính xác, SameSite hoặc TLS | So sánh public URL, `Set-Cookie`, `Cookie`, proxy headers và callback thực |
| Người dùng vừa đăng nhập xong bị 403 khi POST dữ liệu | CSRF protection của ứng dụng vẫn áp dụng | Gửi CSRF token của phiên; OAuth2 `state` không phải form-CSRF token |
| Hai tab login đồng thời gây lỗi callback | Session repository giữ một request đang chờ hoặc request bị ghi đè | Kiểm tra behavior thật và thiết kế lưu theo state nếu cần nhiều giao dịch |
| Token/secret xuất hiện trong log | Logging query/header/body quá mức ở app/proxy | Giảm log, redaction và rotation credential theo quy trình |

Một số lỗi từ IdP không có cùng mã HTTP giữa các nhà cung cấp. Nên phân biệt **authorization endpoint error (qua browser)** với **token endpoint error (server-to-server)** trước khi kết luận.

## 10. Kiểm thử bảo mật theo từng lớp

### 10.1. Test thuật toán PKCE

Chạy `PkceExample.java` ở phần 5.1. Test vector RFC 7636 phải khớp, verifier mới phải có chiều dài hợp lệ; không sử dụng giá trị cố định đó làm credential production. Trong hệ thống thật, khi authorization request có `code_challenge`, token endpoint phải từ chối code nếu `code_verifier` không chứng minh được challenge tương ứng.

### 10.2. Test authorization redirect

Với IdP thử nghiệm và một client registration thật:

- Mở authorization endpoint qua Spring; xác nhận có **state ngẫu nhiên** và **PKCE S256 challenge**.
- Với login OIDC có nonce, kiểm tra request mang nonce theo cấu hình framework; không suy luận nonce trong plain OAuth2 API authorization.
- Callback thành công phải dùng đúng browser session, đúng `state` và đúng code.
- Callback thiếu/sai state, code tái sử dụng hoặc callback hết hạn phải thất bại.
- Token exchange sai verifier phải bị Authorization Server từ chối.
- Nếu request OIDC gửi nonce, ID Token trả về có nonce sai hoặc thiếu phải bị client từ chối.
- Đảm bảo kiểm tra chữ ký/issuer/audience/thời hạn ID Token, và kiểm soát quyền/role sau đăng nhập riêng biệt.

**Không cần cố tạo callback giả trên production.** Các ca bất thường được kiểm tra với local IdP/test environment, giao dịch kiểm thử có quản lý và log đã che dữ liệu nhạy cảm. Cần kiểm thử cả security filters và behavior thật của IdP; test chỉ kiểm tra URL redirect chưa chứng minh token validation đã đúng.

### 10.3. Kỳ vọng trong browser và server

Browser Network thấy redirect tới IdP, callback mang code/state, session cookie của ứng dụng và redirect về trang thành công. Nó **không nên thấy** token request chứa `code_verifier` hoặc `client_secret` trong mô hình server-side chuẩn. Server/IdP logs có thể theo dõi các mốc HTTP và mã lỗi đã redacted mà không ghi nguyên code/token/verifier/secret.

Khi triển khai, đảm bảo:

1. **HTTPS** cho các endpoint thực; redirect URIs có whitelist chính xác.
2. `state` sinh ngẫu nhiên, lưu và xác minh gắn với phiên/giao dịch; không bỏ qua khi callback sai.
3. **PKCE S256** với verifier đủ entropy và chỉ gửi verifier khi đổi code.
4. **OIDC nonce** khi request có nonce: xác minh ID Token nonce, chữ ký, `iss`, `aud`, `exp` và ràng buộc liên quan.
5. Client credentials nằm trong secret store/server; token storage/rotation/revocation và quyền truy cập được thiết kế phù hợp.
6. Cookie session, SameSite, proxy forwarded headers, load balancing và session timeout không làm mất correlation state.
7. Phân tách login OAuth2/OIDC với CSRF của biểu mẫu ứng dụng và xác thực resource-server cho API.

## 11. Cách nhớ đúng cho một giao dịch

```text
Authorization request:
    state = S
    code_verifier = V                 (lưu an toàn tại client)
    code_challenge = BASE64URL(SHA256(V))
    nonce = N                         (chỉ khi giao dịch OIDC dùng nonce)

Browser tới IdP:
    response_type=code, state=S, code_challenge=..., method=S256, nonce=N

Browser callback:
    code=CODE, state=S                -> Client phải so state và session

Client tới token endpoint:
    grant_type=authorization_code, code=CODE, code_verifier=V
    (+ client authentication khi là confidential client)

Client nhận token:
    Verify token response; nếu OIDC đã gửi nonce N, ID Token phải chứa
    nonce khớp N, đồng thời phải vượt mọi kiểm tra ID Token khác.
```

**Kết luận áp dụng:** Trong Spring Security Servlet, để filter/framework quản lý Authorization Code correlation, dùng **state** để xác nhận callback thuộc đúng giao dịch, dùng **PKCE S256** để ràng buộc code với verifier, và dùng **nonce khi có ID Token theo OIDC** để xác nhận token thuộc yêu cầu đăng nhập. Cả ba bổ sung cho nhau và không thay thế bảo vệ session, redirect URI, token validation, authorization hay CSRF của ứng dụng.
