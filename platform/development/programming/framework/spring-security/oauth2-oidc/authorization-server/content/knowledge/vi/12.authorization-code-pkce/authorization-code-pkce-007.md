# Áp dụng PKCE cho ứng dụng public và confidential

## 1. Tình huống và mục tiêu học tập

Trong mô hình **OAuth 2.0/OpenID Connect (OIDC) Authorization Server** dùng **Spring Boot, Spring Security và Spring Authorization Server**, nhiều loại ứng dụng có thể cùng sử dụng **Authorization Code grant**: SPA chạy trong trình duyệt, ứng dụng di động, desktop, website có backend hoặc Backend for Frontend (BFF).

Một ngộ nhận phổ biến là: **“PKCE chỉ dành cho public client; confidential client đã có client secret thì không cần PKCE.”** Thực tế, hai cơ chế giải quyết **hai vấn đề khác nhau**. PKCE ràng buộc authorization code với **giao dịch đã khởi tạo**; client authentication chứng minh client được phép sử dụng credential tại Token Endpoint. Với OAuth Security Best Current Practice (RFC 9700), public client **MUST** dùng PKCE và confidential client **RECOMMENDED** dùng PKCE để chống code injection/misuse.

Trong chương **Authorization Code và PKCE**, bài này giúp bạn:

1. Phân biệt public/confidential client và vai trò độc lập của PKCE so với client authentication.
2. Tạo `code_verifier` và `code_challenge` đúng **S256**, gắn vào từng giao dịch Authorization Code.
3. Cấu hình `RegisteredClient` với `ClientSettings.requireProofKey(true)` cho **cả hai** nhóm client.
4. Hiểu trách nhiệm phía **Authorization Server** và phía **OAuth2 Client** (đặc biệt khi cả hai đều viết bằng Spring).
5. Kiểm thử cơ chế chống thiếu verifier, sai verifier, code replay, code injection và PKCE downgrade.

**Giới hạn phạm vi:** Bài tập trung vào Authorization Code + PKCE trong ứng dụng Servlet/Spring Boot. Các ví dụ API dùng hướng tiếp cận **Spring Authorization Server 1.5.x và Spring Security 6.x**; từ **Spring Security 7.x**, Authorization Server đã được tích hợp vào Spring Security và một số mặc định có thể thay đổi. Đừng sao chép cấu hình giữa các thế hệ mà không kiểm tra tài liệu đúng phiên bản.

## 2. Public, confidential và PKCE: ba câu hỏi độc lập

### 2.1. Phân loại client theo khả năng bảo vệ credential

| Tiêu chí | Public client | Confidential client |
| --- | --- | --- |
| Nơi chạy điển hình | SPA JavaScript, native mobile, desktop/CLI phát hành cho người dùng | Backend web, BFF, server-to-server có vùng lưu credential an toàn |
| Có thể giữ lâu dài một shared client secret khỏi người dùng cuối? | **Không đáng tin cậy** | **Có thể**, nếu cấu hình hạ tầng và secret management đúng |
| Client authentication tại Token Endpoint | Thường `none` với Authorization Code + PKCE | `client_secret_basic`, `private_key_jwt`, mTLS hoặc phương thức phù hợp |
| PKCE với Authorization Code | **Bắt buộc theo RFC 9700** | **Được khuyến nghị theo RFC 9700**; nên bật thành chính sách mặc định |
| Vị trí giữ `code_verifier` | Trạng thái ngắn hạn của giao dịch ở client, chống rò rỉ qua URL/log | Trạng thái server-side của BFF/backend, ràng buộc với phiên trình duyệt |

**Cảnh báo:** Việc thêm `client_secret` vào bundle JavaScript, mobile APK/IPA hay binary desktop không biến một client public thành confidential. Người dùng cuối vẫn có thể trích xuất secret đó. Ngược lại, một web app dùng server-side session/BFF có thể là confidential dù phần giao diện chạy trong browser, vì **OAuth client thực sự đổi code và giữ secret nằm ở backend**.

### 2.2. PKCE khác gì client authentication?

| Cơ chế | Chứng minh điều gì? | Giá trị/thông tin được gửi | Khi nào kiểm tra? |
| --- | --- | --- | --- |
| **Client authentication** | Request đến Token Endpoint có credential hợp lệ của client | Shared secret, signed JWT assertion, mTLS certificate… | Token Endpoint |
| **PKCE** | Bên đổi code biết `code_verifier` đã gắn với authorization request tạo ra code | `code_challenge` trước, `code_verifier` sau | Authorization Endpoint + Token Endpoint |
| **`state`** | Authorization response gắn với yêu cầu/phiên browser đang chờ | Chuỗi ngẫu nhiên hoặc dữ liệu transaction đã được ràng buộc an toàn | Client so khớp ở callback |
| **OIDC `nonce`** | ID token gắn với phiên xác thực/authorization request | Nonce trong authorization request và claim trên ID token | OIDC client kiểm tra ID token |

PKCE **không phải cơ chế xác thực client** và không thay secret, mTLS hoặc JWT client assertion khi confidential client buộc phải xác thực. Nó cũng không thay kiểm tra `redirect_uri`, `state`/CSRF, `nonce`, user authentication, consent, TLS và token validation.

### 2.3. Tại sao confidential client vẫn được lợi từ PKCE?

Giả sử BFF có client secret được giữ an toàn ở server. Một kẻ tấn công có thể:

- Chèn hoặc tráo authorization code vào callback/login transaction, gây **authorization code injection** hoặc đăng nhập nhầm tài khoản nếu thiếu cơ chế ràng buộc.
- Tìm cách đưa code hợp lệ của một giao dịch khác đến backend client.
- Lợi dụng ứng dụng chưa ràng buộc response với phiên browser đã khởi tạo.

Client secret chỉ chứng minh **BFF có credential hợp lệ** tại Token Endpoint. Nó không tự chứng minh code đang đổi được tạo trong **cùng giao dịch của người dùng hiện tại**. Khi BFF giữ verifier riêng cho mỗi giao dịch và Token Endpoint kiểm chứng S256, một code từ giao dịch khác sẽ không khớp verifier BFF gửi. Do đó, PKCE mang thêm lớp bảo vệ cho **cả confidential client**.

## 3. Quy tắc kỹ thuật PKCE theo RFC 7636

### 3.1. Hai giá trị: verifier và challenge

Client tạo **`code_verifier` ngẫu nhiên có entropy cao** cho **mỗi authorization transaction**:

```text
code_verifier:  chuỗi ngẫu nhiên dài 43–128 ký tự thuộc tập
                A-Z, a-z, 0-9, "-", ".", "_", "~"

code_challenge_method: S256

code_challenge = BASE64URL-ENCODE( SHA256( ASCII(code_verifier) ) )

Chú ý: base64url KHÔNG có padding "=".
```

RFC 7636 khuyến nghị sinh tối thiểu **256 bit entropy**, chẳng hạn 32 byte từ CSPRNG rồi base64url không padding. Với 32 byte, verifier thường dài **43 ký tự**, đồng thời challenge S256 SHA-256 cũng dài **43 ký tự**.

**Không dùng** mật khẩu người dùng, client secret, UUID phiên lặp lại, thời gian hiện tại, username, `state` hoặc giá trị cố định chung cho mọi request làm verifier. Không đưa verifier vào query Authorization Endpoint: **chỉ challenge** được gửi ở bước đầu.

### 3.2. Vì sao chọn S256 chứ không chọn plain?

RFC 7636 có hai cách biến đổi:

- `S256`: `code_challenge = BASE64URL(SHA-256(ASCII(verifier)))`.
- `plain`: `code_challenge = verifier`; chỉ dành cho những trường hợp tương thích đặc biệt khi client không thể dùng S256 và biết AS hỗ trợ plain.

**Mặc định thực hành: chỉ sử dụng S256**. Nếu thiếu `code_challenge_method`, RFC 7636 định nghĩa mặc định là `plain`, vì vậy một ứng dụng có khả năng hỗ trợ S256 phải **gửi rõ `code_challenge_method=S256`**. Đừng “fallback” từ S256 sang plain nếu request thất bại.

Lưu ý: `requireProofKey(true)` bắt buộc có proof key theo chính sách client, nhưng **không tự hàm ý mọi cấu hình đều chỉ chấp nhận duy nhất S256**. Nếu chính sách hệ thống yêu cầu chặn hoàn toàn `plain`, phải xác minh hành vi validator của phiên bản Spring Authorization Server và thêm validation có kiểm thử khi cần, thay vì mặc định cho rằng cờ PKCE đồng nghĩa “S256-only”.

### 3.3. Ví dụ tạo verifier/challenge bằng Java

Đây là code minh họa chạy ở **OAuth2 Client** (không phải đoạn xử lý trong Authorization Server):

```java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.util.Base64;

public final class PkceUtil {
    private static final SecureRandom RANDOM = new SecureRandom();
    private static final Base64.Encoder URL_ENCODER =
            Base64.getUrlEncoder().withoutPadding();

    private PkceUtil() {}

    public record Pair(String verifier, String challenge) {}

    public static Pair newPair() {
        byte[] randomBytes = new byte[32]; // 256-bit entropy
        RANDOM.nextBytes(randomBytes);
        String verifier = URL_ENCODER.encodeToString(randomBytes);
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                    .digest(verifier.getBytes(StandardCharsets.US_ASCII));
            String challenge = URL_ENCODER.encodeToString(digest);
            return new Pair(verifier, challenge);
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException("SHA-256 is unavailable", ex);
        }
    }
}
```

Ví dụ dùng:

```java
PkceUtil.Pair pkce = PkceUtil.newPair();
// pkce.challenge() gửi trong /oauth2/authorize với method=S256.
// pkce.verifier() lưu an toàn theo login transaction của client,
// rồi gửi sau tại /oauth2/token; KHÔNG log cả hai giá trị ở production.
```

Code Java 17+ dùng `record`, SHA-256, Base64 URL encoder không padding và entropy ngẫu nhiên. Nếu đã dùng `spring-security-oauth2-client` để thực hiện login, **ưu tiên cơ chế PKCE có sẵn**, không tự viết tiện ích tạo verifier nếu không thực sự cần điều khiển một OAuth client tùy biến.

## 4. Luồng Authorization Code + PKCE từ đầu đến cuối

```mermaid
sequenceDiagram
    autonumber
    participant U as Browser / Người dùng
    participant C as OAuth2 Client (SPA hoặc BFF)
    participant AS as Authorization Server
    participant DB as OAuth2AuthorizationService
    C->>C: Tạo verifier ngẫu nhiên, challenge=S256(verifier)
    C->>C: Lưu verifier với state và phiên login
    C-->>U: Redirect đến /oauth2/authorize
    U->>AS: client_id, redirect_uri, state, code_challenge, S256
    AS->>AS: Kiểm tra client, redirect URI, PKCE, user/consent
    AS->>DB: Lưu authorization code + challenge/method ràng buộc
    AS-->>U: Redirect callback?code=...&state=...
    U->>C: Chuyển authorization code + state về callback
    C->>C: So khớp state; lấy verifier của chính transaction
    C->>AS: POST /oauth2/token (code, code_verifier, client auth nếu cần)
    AS->>DB: Tra cứu authorization code và dữ liệu PKCE ban đầu
    AS->>AS: Kiểm tra code, verifier S256, client, redirect và thời hạn
    AS->>DB: Đánh dấu code đã dùng; lưu token state
    AS-->>C: Access token (+ ID/refresh token nếu áp dụng)
```

**Một số bước nội bộ thay đổi theo grant/phiên bản**, nhưng ranh giới luôn giống nhau: verifier không được lộ trên front-channel ở thời điểm xin code; AS gắn challenge vào authorization; chỉ verifier khớp mới đổi code thành token.

### 4.1. Bước 1: bắt đầu authorization request

Ví dụ client `spa-ui`:

```http
GET /oauth2/authorize?response_type=code
  &client_id=spa-ui
  &redirect_uri=https%3A%2F%2Fspa.example.com%2Fcallback
  &scope=openid%20profile
  &state=STATE_BOUND_TO_THIS_LOGIN
  &code_challenge=S256_CHALLENGE_BASE64URL
  &code_challenge_method=S256
```

Các chuỗi `STATE_BOUND_TO_THIS_LOGIN`, `S256_CHALLENGE_BASE64URL` chỉ là **placeholder**, không phải giá trị hợp lệ để chạy. Trong request thật, chúng phải được sinh từ ngẫu nhiên an toàn và ràng buộc với một lần đăng nhập. OIDC client cũng cần dùng và xác thực `nonce` khi profile/flow yêu cầu.

Authorization Server:

1. Tra `RegisteredClientRepository.findByClientId("spa-ui")`.
2. Xác minh grant `authorization_code`, callback chính xác, scopes và trạng thái client theo chính sách.
3. Kiểm tra yêu cầu PKCE (có challenge và method được chấp nhận).
4. Thực hiện user authentication và consent khi cần.
5. Tạo authorization code ngắn hạn, **lưu challenge/method gắn với authorization** để kiểm tra khi đổi code.

**Quan trọng:** khi `client_id` hoặc `redirect_uri` không hợp lệ, Authorization Server không được gửi authorization error tới URI chưa xác nhận. PKCE **không** thay thế redirect URI validation.

### 4.2. Bước 2: Authorization Server redirect code

Khi yêu cầu được duyệt:

```http
HTTP/1.1 302 Found
Location: https://spa.example.com/callback?code=AUTHORIZATION_CODE&state=STATE_BOUND_TO_THIS_LOGIN
Cache-Control: no-store
```

Code là credential **ngắn hạn, dùng một lần**. Client nhận callback phải kiểm tra `state` trước khi hoàn tất trao đổi code; không tự tin code hợp lệ chỉ vì callback được gọi từ browser.

### 4.3. Bước 3: đổi code lấy token — public client

Public client **không** gửi shared client secret:

```http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code
&client_id=spa-ui
&code=AUTHORIZATION_CODE
&redirect_uri=https%3A%2F%2Fspa.example.com%2Fcallback
&code_verifier=THE_ORIGINAL_SECRET_VERIFIER
```

Các dòng body được xuống dòng để dễ đọc; HTTP form request thực tế cần URL-encode đúng và trình bày theo chuẩn request body. `client_id` được gửi vì client không xác thực bằng secret. `code_verifier` phải khớp challenge đã lưu từ chính giao dịch.

Tại Token Endpoint, AS kiểm tra code chưa dùng/chưa hết hạn, client/redirect phù hợp và:

```text
BASE64URL(SHA256(ASCII(received_code_verifier)))
    == stored_code_challenge
```

Nếu sai, Token Endpoint **không phát token**; thông thường trả OAuth error `invalid_grant`. Việc client biết `client_id` không giúp vượt qua PKCE.

### 4.4. Bước 3: đổi code lấy token — confidential client

Confidential client dùng **đồng thời** client authentication và PKCE:

```http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Authorization: Basic BASE64_CLIENT_ID_COLON_SECRET
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code
&code=AUTHORIZATION_CODE
&redirect_uri=https%3A%2F%2Fbff.example.com%2Flogin%2Foauth2%2Fcode%2Fbff
&code_verifier=THE_ORIGINAL_SECRET_VERIFIER
```

`Authorization` ở đây là **minh họa** cho `client_secret_basic`; không dùng chuỗi placeholder như credential thực. Với `private_key_jwt` hoặc mTLS, cách chứng minh danh tính client khác đi, nhưng **vẫn phải gửi verifier** nếu giao dịch dùng PKCE.

Token Endpoint sẽ kiểm tra **hai điều kiện độc lập**:

1. Credential của confidential client hợp lệ và được phép dùng grant.
2. Code + verifier thuộc đúng authorization transaction, cùng client, callback và trạng thái.

Client secret đúng **không cho phép bỏ qua verifier** khi registration yêu cầu PKCE.

## 5. Cấu hình RegisteredClient trong Spring Authorization Server

### 5.1. Hai RegisteredClient cùng bật PKCE

Ví dụ cấu hình Java cho demo/test (Spring Authorization Server 1.5.x):

```java
import java.util.UUID;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.core.oidc.OidcScopes;
import org.springframework.security.oauth2.server.authorization.client.InMemoryRegisteredClientRepository;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClientRepository;
import org.springframework.security.oauth2.server.authorization.settings.ClientSettings;

@Configuration(proxyBeanMethods = false)
public class PkceClientRegistrationConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    RegisteredClientRepository registeredClients(
            PasswordEncoder passwordEncoder,
            @Value("${PKCE_BFF_SECRET}") String bffSecret) {

        RegisteredClient publicSpa = RegisteredClient
                .withId("spa-internal-id")
                .clientId("spa-ui")
                .clientAuthenticationMethod(ClientAuthenticationMethod.NONE)
                .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
                .redirectUri("https://spa.example.com/callback")
                .scope(OidcScopes.OPENID)
                .scope(OidcScopes.PROFILE)
                .clientSettings(ClientSettings.builder()
                        .requireProofKey(true)
                        .requireAuthorizationConsent(true)
                        .build())
                .build();

        RegisteredClient confidentialBff = RegisteredClient
                .withId("bff-internal-id")
                .clientId("bff")
                .clientSecret(passwordEncoder.encode(bffSecret))
                .clientAuthenticationMethod(
                        ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
                .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
                .authorizationGrantType(AuthorizationGrantType.REFRESH_TOKEN)
                .redirectUri("https://bff.example.com/login/oauth2/code/bff")
                .scope(OidcScopes.OPENID)
                .scope(OidcScopes.PROFILE)
                .clientSettings(ClientSettings.builder()
                        .requireProofKey(true)
                        .requireAuthorizationConsent(true)
                        .build())
                .build();

        return new InMemoryRegisteredClientRepository(publicSpa, confidentialBff);
    }
}
```

Ví dụ:

- **Public SPA**: `ClientAuthenticationMethod.NONE`, **không có** client secret, dùng Authorization Code + PKCE.
- **Confidential BFF**: `CLIENT_SECRET_BASIC` **và** `requireProofKey(true)`; dùng secret được inject từ environment/secret manager, không đưa plaintext vào source code.
- Hai client dùng **cùng một giao thức PKCE** nhưng **khác cách xác thực client**.
- `requireAuthorizationConsent(true)` minh họa consent policy, **không phải thành phần bắt buộc để PKCE hoạt động**.
- `InMemoryRegisteredClientRepository` chỉ thích hợp demo/test; production cần persistence, credential rotation và bảo vệ secret. Nếu dự án đã có `PasswordEncoder` bean, không đăng ký thêm bean cùng tên một cách vô ý.

**Mặc định phụ thuộc phiên bản:** Javadoc **Spring Authorization Server 1.5.x** nêu `ClientSettings.isRequireProofKey()` mặc định **`false`**; tài liệu **Spring Security 7.x** nêu mặc định **`true`** cho Authorization Code. Vì vậy, ở những hệ thống yêu cầu PKCE không được tắt, **ghi tường minh `requireProofKey(true)` cho từng client** và viết test thực tế thay vì dựa vào mặc định của thư viện.

### 5.2. Khai báo bằng application.yml (Spring Boot 3.x)

Khi dùng starter/auto-configuration phù hợp và **chưa thay thế RegisteredClientRepository bằng bean riêng**, có thể khai báo client bằng Boot properties:

```yaml
spring:
  security:
    oauth2:
      authorizationserver:
        client:
          spa:
            registration:
              client-id: spa-ui
              client-authentication-methods:
                - none
              authorization-grant-types:
                - authorization_code
              redirect-uris:
                - https://spa.example.com/callback
              scopes:
                - openid
                - profile
            require-proof-key: true
            require-authorization-consent: true

          bff:
            registration:
              client-id: bff
              client-secret: "${PKCE_BFF_SECRET_HASH}"
              client-authentication-methods:
                - client_secret_basic
              authorization-grant-types:
                - authorization_code
                - refresh_token
              redirect-uris:
                - https://bff.example.com/login/oauth2/code/bff
              scopes:
                - openid
                - profile
            require-proof-key: true
            require-authorization-consent: true
```

`PKCE_BFF_SECRET_HASH` phải chứa giá trị **được PasswordEncoder nhận diện** (ví dụ encoded hash với tiền tố thuật toán tương ứng) và được quản lý qua nguồn cấu hình bảo mật. Đây không phải plaintext secret client sử dụng. Với bean Java ở mục trước, secret được encoder xử lý lúc lưu, nên **không dùng đồng thời hai nguồn client registration rồi hy vọng Boot tự hợp nhất**.

**Lưu ý:** Khi khai báo tường minh `RegisteredClientRepository`, Boot có thể không tạo repository từ `spring.security.oauth2.authorizationserver.client.*`. Kiểm tra bean thực tế trong ApplicationContext; YAML chỉ có tác dụng ở phạm vi auto-configuration còn được áp dụng.

## 6. Spring Security OAuth2 Client cũng phải chủ động gửi PKCE

Một lỗi tích hợp thường gặp là:

> Authorization Server đã bật `requireProofKey(true)` nhưng OAuth2 Client không gửi `code_challenge`, khiến authorization request bị từ chối.

**Cấu hình ở Authorization Server chỉ buộc AS kiểm tra PKCE.** Phần mềm đóng vai trò **OAuth2 Client** phải tạo verifier/challenge cho từng transaction và lưu verifier để dùng ở Token Endpoint.

### 6.1. Public client dùng Spring Security OAuth2 Client

Với Spring Security OAuth2 Client trên Servlet stack, cấu hình client dùng `client-authentication-method: none`, không có client secret và grant `authorization_code`. Spring Security có hỗ trợ PKCE tự động cho cấu hình public client phù hợp. Ví dụ YAML **ở ứng dụng client** (không phải ở Authorization Server):

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          spa-proxy:
            provider: my-as
            client-id: spa-ui
            client-authentication-method: none
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
        provider:
          my-as:
            issuer-uri: https://auth.example.com
```

**Không nhầm:** YAML này mô tả **client tiêu thụ Authorization Server**. Prefix `spring.security.oauth2.client.registration.*` khác hoàn toàn `spring.security.oauth2.authorizationserver.client.*` trên server. Redirect URI của client phải **trùng URI đã đăng ký trên AS**; ở ví dụ, registration phía AS cần được điều chỉnh theo đường callback `/login/oauth2/code/spa-proxy` nếu thực sự chạy snippet.

Đối với SPA chạy JavaScript trực tiếp không dùng Spring Security Servlet client, bạn cần SDK OIDC/OAuth tương thích để sinh và ràng buộc verifier/challenge ở browser. Không thể dựa vào bean phía Authorization Server để tự sinh verifier thay client.

### 6.2. Confidential client dùng Spring Security oauth2Login

Nếu RP là Spring Boot backend/BFF, một cấu hình bảo mật có thể chủ động bật PKCE ở **OAuth2 Client** bằng `OAuth2AuthorizationRequestCustomizers.withPkce()`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizationRequestResolver;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizationRequestCustomizers;
import org.springframework.security.web.SecurityFilterChain;

@Bean
SecurityFilterChain relyingPartySecurityFilterChain(
        HttpSecurity http,
        ClientRegistrationRepository clientRegistrations) throws Exception {

    DefaultOAuth2AuthorizationRequestResolver resolver =
            new DefaultOAuth2AuthorizationRequestResolver(
                    clientRegistrations, "/oauth2/authorization");
    resolver.setAuthorizationRequestCustomizer(
            OAuth2AuthorizationRequestCustomizers.withPkce());

    http
        .authorizeHttpRequests(authorize ->
            authorize.anyRequest().authenticated())
        .oauth2Login(oauth2 -> oauth2
            .authorizationEndpoint(endpoint ->
                endpoint.authorizationRequestResolver(resolver)));

    return http.build();
}
```

Ở đây:

- Code thuộc **ứng dụng Relying Party**, không phải cấu hình chain của Authorization Server.
- Resolver tạo `code_challenge` cho redirect và lưu `code_verifier` trong attributes của authorization request để trao đổi code đúng giao dịch.
- Bộ client authentication (ví dụ `client_secret_basic`) vẫn hoạt động ở Token Endpoint; PKCE **không vô hiệu hóa** client secret.
- Ứng dụng vẫn cần `ClientRegistrationRepository`, `spring.security.oauth2.client.registration.*`, user session, redirect URI và cấu hình provider/issuer phù hợp.

Trong những phiên bản Spring Security mới hơn, `ClientRegistration.clientSettings.requireProofKey` có thể đã hỗ trợ bật PKCE trực tiếp cho confidential client. Cần kiểm tra model/version đang dùng; ví dụ resolver tường minh giúp thể hiện **ý định bật PKCE ở phía client** và phải được tích hợp nhất quán với resolver khác nếu đã custom login.

### 6.3. BFF thường hợp lý khi nào?

Với SPA chứa dữ liệu nhạy cảm, BFF có thể:

1. Đóng vai trò confidential client tại Token Endpoint.
2. Giữ client secret và access/refresh token **server-side**.
3. Tạo và lưu PKCE verifier trong **transaction state phía server**, ràng buộc với session cookie bảo mật.
4. Chỉ cung cấp cho browser cookie phiên `HttpOnly; Secure; SameSite` phù hợp luồng, và API nội bộ qua BFF.

Điều này giảm việc expose OAuth tokens/secret cho JavaScript. Tuy nhiên BFF vẫn phải chống **CSRF, XSS, session fixation**, bảo vệ cookie và kiểm soát proxy/forwarded headers. PKCE không tự giải quyết các lỗi đó.

## 7. PKCE giúp chống tấn công nào — và không giúp chống tấn công nào?

### 7.1. Interception: kẻ tấn công lấy được authorization code

Một code lộ qua môi trường ít tin cậy, extension độc hại hoặc callback sai không nên đủ để đổi token. Nếu attacker chỉ biết code nhưng **không biết verifier đúng transaction**, Token Endpoint từ chối. Đây là tình huống PKCE được thiết kế giải quyết.

### 7.2. Code injection và login CSRF

Attacker có thể tìm cách đưa code từ giao dịch khác vào callback của một người dùng. Nếu backend không ràng buộc giao dịch, code có thể bị đổi bằng credential hợp lệ của backend và gây nhầm phiên. PKCE tạo ràng buộc transaction-specific qua verifier; `state` (và OIDC `nonce` khi áp dụng) vẫn phải được kiểm tra và giữ liên kết với browser session.

**RFC 9700:** public client **MUST** dùng PKCE; confidential client **RECOMMENDED** dùng PKCE, giúp ngăn code injection/misuse và cung cấp bảo vệ CSRF mạnh khi binding được thực hiện đúng. Một số confidential OIDC client có phương án dựa trên nonce với các điều kiện bổ sung, nhưng **PKCE S256 là lựa chọn mặc định hợp lý cho kiến trúc mới**.

### 7.3. Các giới hạn của PKCE

| Rủi ro | PKCE có giải quyết một mình không? | Kiểm soát bổ sung |
| --- | --- | --- |
| Client secret bị lộ từ frontend | **Không** | Phân loại public đúng; không nhúng secret vào frontend; cân nhắc BFF |
| Attacker chỉ biết authorization code | **Có ích mạnh** nếu verifier an toàn | Code ngắn hạn, một lần, TLS, redirect validation |
| Attacker biết cả code **và verifier** do XSS | **Không đủ** | Ngăn XSS, CSP, bảo vệ storage/transaction, BFF |
| Redirect URI có open redirect | **Không** | Exact redirect URI matching, không dùng redirector nguy hiểm |
| Access token bị đánh cắp sau khi cấp | **Không** | Token TTL, audience/scope, sender-constraining/rotation khi áp dụng |
| CSRF/login transaction không được ràng buộc | **Không bảo đảm** nếu PKCE bị dùng sai | Bind verifier với transaction/browser; kiểm tra state/nonce |
| Client confidential dùng secret yếu | **Không** | Secret manager, rotation, private_key_jwt/mTLS khi phù hợp |
| Refresh token bị replay | **Không** | Refresh rotation/replay detection hoặc sender constraints |
| Phát token cho client/grant không được phép | **Không** | Registration, client authentication, scopes, authorization policy |

### 7.4. Chống PKCE downgrade

Một lỗ hổng tích hợp là client/server chấp nhận **Authorization Code không gắn challenge**, nhưng ở Token Endpoint lại cố cho phép đổi code đó như một flow không-PKCE (hoặc “có verifier thì check, không có thì bỏ qua”).

Để tránh:

- Đặt `requireProofKey(true)` cho mọi `RegisteredClient` dùng Authorization Code theo chính sách dự án.
- Từ chối authorization request thiếu challenge/method hợp lệ theo policy.
- Khi code đã được gắn PKCE, **không cấp token nếu verifier thiếu hoặc sai**; không có “fallback” sang code-only.
- Nếu policy yêu cầu S256-only, kiểm tra và kiểm thử yêu cầu có method `plain` hoặc thiếu `code_challenge_method`.
- Không để nhiều code path (legacy/new endpoints) chấp nhận quy tắc khác nhau; áp dụng với public và confidential.
- Giữ code một lần, kiểm tra client/redirect URI trước khi phát token.

## 8. Lỗi thường gặp tại Authorization Endpoint và Token Endpoint

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Authorization request bị từ chối khi thiếu challenge | Client đăng ký `requireProofKey(true)` nhưng không gửi PKCE | Kiểm tra OAuth2 Client resolver/SDK; tạo S256 challenge cho từng login |
| `invalid_request` khi `code_challenge` malformed | Challenge không đúng định dạng, method không được hỗ trợ | Sinh bằng CSPRNG + SHA-256 + base64url không padding |
| `invalid_grant` khi đổi code | Verifier sai/thiếu, code hết hạn/đã dùng, client hoặc redirect không khớp | Kiểm tra correlation của từng transaction, không log verifier/token |
| `invalid_client` tại Token Endpoint của BFF | Client secret, method hoặc key xác thực sai | Kiểm tra client authentication **độc lập** với PKCE |
| Public client gửi `client_secret` và bị lỗi | Nhầm public thành confidential | Dùng `none` và không gửi secret từ browser |
| Có challenge nhưng token request không mang verifier | Client không giữ verifier qua callback hoặc session bị mất | Kiểm tra `OAuth2AuthorizationRequestRepository` / transaction storage |
| Wrong verifier sau khi mở nhiều tab | Dùng chung một verifier toàn phiên hoặc ghi đè state | Mỗi authorization transaction có verifier riêng, map theo state |
| Login thành công nhưng callback thất bại | Redirect URI client khác URI đã đăng ký trên AS | Khớp chính xác scheme/host/port/path của URI |
| Trong staging chạy, production không chạy | Cookie/SameSite, proxy, issuer, session store khác | Kiểm tra HTTPS, forwarded headers và session storage |
| Code đổi thành token dù thiếu PKCE | Server/registration chưa enforce, policy cũ | Bật `requireProofKey(true)`, cập nhật client, chạy test downgrade |
| Chỉ dùng secret nhưng vẫn bị code injection | Client authentication không gắn code với transaction | Bật PKCE ở confidential client và AS; kiểm tra state |

**Lỗi cụ thể có thể khác nhau giữa phiên bản/nhánh kiểm tra**. Với request sai `client_id` hoặc `redirect_uri`, Authorization Server phải tránh redirect lỗi về URI chưa tin cậy. Đừng dựa vào duy nhất HTTP status hoặc tên mã lỗi để kết luận PKCE đã thực thi đúng.

## 9. Kiểm thử tích hợp hai loại client

### 9.1. Ma trận test cần có

| Mã | Loại client | Tình huống | Kết quả mong đợi |
| --- | --- | --- | --- |
| P01 | Public | Authorization Code + S256/verifier hợp lệ | Đổi code thành token theo scopes đã được cấp |
| P02 | Public | Không có `code_challenge` | Authorization request bị từ chối; không phát code |
| P03 | Public | Verifier không trùng challenge | Token Endpoint từ chối, không phát token |
| P04 | Public | Đổi code thành công rồi dùng lại | Lần hai bị từ chối |
| P05 | Public | Dùng challenge cố định hoặc verifier tái sử dụng | Bị chặn bởi policy/test hoặc phát hiện vi phạm thiết kế |
| P06 | Public | Gửi secret không được đăng ký | Không trở thành confidential/không bỏ qua chính sách |
| C01 | Confidential | Secret hợp lệ **và** PKCE hợp lệ | Đổi code thành token thành công |
| C02 | Confidential | Secret hợp lệ, thiếu verifier | Không phát token |
| C03 | Confidential | Secret hợp lệ, verifier sai | Không phát token |
| C04 | Confidential | Secret sai, verifier đúng | Không phát token vì client authentication thất bại |
| C05 | Confidential | Code của transaction A + verifier của B | Không phát token |
| C06 | Confidential | Code đúng, redirect URI khác URI đã gắn với code | Từ chối theo protocol |
| S01 | Cả hai | `code_challenge_method=plain` khi policy chỉ cho S256 | Từ chối |
| S02 | Cả hai | Không gửi method (ngầm `plain` theo RFC 7636) | Từ chối nếu policy là S256-only |
| S03 | Cả hai | Redirect URI không đăng ký | Không redirect về URI chưa tin cậy |
| S04 | Cả hai | Nhiều tab, callback đến khác thứ tự | Verifier và state đúng từng transaction |
| S05 | Cả hai | Restart/scale 2 node giữa authorize và token | Authorization state và verifier của client còn truy xuất được theo kiến trúc |
| S06 | Cả hai | Lộ code nhưng không có verifier | Attacker không đổi được token |

**Test P05 không thể chứng minh entropy thật chỉ bằng một request**. Nên unit test trình sinh verifier để kiểm tra độ dài, tập ký tự, xác suất trùng cực thấp qua nhiều mẫu, đồng thời review code rằng nó dùng CSPRNG. Đừng triển khai test ngẫu nhiên có ngưỡng quá nghiêm khiến CI thất bại không ổn định.

### 9.2. Kiểm tra giao thức bằng HTTP

Test request authorization hợp lệ phải dùng **verifier/challenge sinh thật**, không dùng placeholder:

```text
1. Client tạo verifier V bằng CSPRNG.
2. Client tính C = BASE64URL(SHA256(ASCII(V))).
3. GET /oauth2/authorize
     ?response_type=code
     &client_id=spa-ui
     &redirect_uri=https%3A%2F%2Fspa.example.com%2Fcallback
     &state=<STATE_BOUND_TO_BROWSER>
     &code_challenge=<C>
     &code_challenge_method=S256
4. User xác thực/consent; browser nhận redirect code + state.
5. Client so khớp state, POST /oauth2/token với code + V.
6. Kiểm tra có token; dùng lại code hoặc đổi V khác phải thất bại.
```

Với **confidential BFF**, bổ sung client authentication cho Token Endpoint, rồi test **hai lần lỗi độc lập**: đúng credential/sai verifier và sai credential/đúng verifier. Đây là bằng chứng thực tế rằng **PKCE và client authentication đều được thực thi**.

### 9.3. Các assertion cấp ứng dụng

Ngoài HTTP statuses, cần xác minh:

- Registered client public có `ClientAuthenticationMethod.NONE` và `ClientSettings.isRequireProofKey() == true`.
- Registered client confidential có method xác thực phù hợp và `isRequireProofKey() == true`.
- Callback client chỉ hoàn tất khi `state` khớp transaction và verifier tương ứng còn sẵn.
- Không có raw `code_verifier`, `client_secret`, authorization code, access/refresh token trong application logs, tracing hay URL do ứng dụng tự tạo.
- Authorization code chỉ được redeem một lần, trạng thái lưu trong `OAuth2AuthorizationService` và nhất quán giữa các node.
- Tất cả redirect URI được đối chiếu với registration chính xác; không có fallback sang callback khác.

## 10. Vận hành và rollout PKCE cho confidential client cũ

Một hệ thống có nhiều OAuth clients có thể còn confidential clients trước đây dùng Authorization Code **không có PKCE**. Thay đổi ngay `requireProofKey(true)` trên server mà client chưa hỗ trợ sẽ làm login thất bại. Cần rollout có kiểm soát:

1. **Kiểm kê** client theo `authorization_code`, auth method, SDK/phiên bản, callback và môi trường; phân loại public/confidential.
2. **Ưu tiên public clients**: không chấp nhận thiếu PKCE; xử lý client không tương thích bằng cập nhật SDK/kiến trúc, **không** hạ bảo mật để cho qua.
3. **Nâng cấp confidential clients**: cấu hình client tạo S256 verifier/challenge, lưu theo transaction; kiểm tra cả request `/oauth2/authorize` và `/oauth2/token`.
4. **Thử nghiệm canary/staging**: bắt lỗi wrong/absent verifier, nhiều tab, login redirect, reverse proxy, session store và restart.
5. **Bật server enforcement** `requireProofKey(true)` trên registration tương ứng, đồng thời giữ client authentication đang dùng.
6. **Quan sát và xử lý lỗi**: theo dõi tỷ lệ authorization failures/`invalid_grant`/`invalid_request` đã được phân loại, không log raw request credentials.
7. **Siết chính sách S256-only** nếu yêu cầu; đảm bảo không có legacy path bỏ qua PKCE hoặc fallback sang `plain`.

Với dữ liệu client lưu JDBC, cập nhật `RegisteredClient.clientSettings` qua cơ chế migration/management service của bạn; đừng mặc định sửa YAML sẽ đổi bản ghi JDBC đang được dùng. Giữ `RegisteredClient.id` ổn định để không phá liên kết authorization và consent.

### 10.1. Nhiều instance và session

Việc lưu challenge thường gắn với authorization trong `OAuth2AuthorizationService` ở Authorization Server, còn verifier được giữ **phía OAuth2 Client** trong transaction/login session. Hai bên phải có storage phù hợp khi đổi node hoặc restart:

```mermaid
flowchart LR
    BR["Browser"] --> RP1["RP/BFF node 1"]
    BR --> RP2["RP/BFF node 2"]
    RP1 --> RS[("RP transaction/session store<br/>state → verifier")]
    RP2 --> RS
    RP1 --> AS1["Authorization Server node 1"]
    RP2 --> AS2["Authorization Server node 2"]
    AS1 --> AUTH[("Authorization store<br/>code → challenge/method")]
    AS2 --> AUTH
```

Nếu verifier bị ghi đè trong phiên RP hoặc `OAuth2AuthorizationService` không chia sẻ giữa AS nodes, code hợp lệ có thể bị báo `invalid_grant`. Đây là lỗi **state/persistence**, không nên sửa bằng cách tắt PKCE.

### 10.2. Checklist an toàn khi đưa lên production

- [ ] Phân loại đúng client public/confidential theo khả năng **giữ credential**, không theo hình thức UI.
- [ ] Public Authorization Code clients đều bắt buộc PKCE, không dùng shared secret trong frontend.
- [ ] Confidential Authorization Code clients bật PKCE cùng client authentication.
- [ ] Mọi giao dịch dùng verifier CSPRNG, 43–128 ký tự, entropy cao; tạo **mới từng lần**.
- [ ] Challenge dùng **S256**, SHA-256 của ASCII verifier, base64url **không padding**.
- [ ] Verifier chỉ được gửi ở Token Endpoint; không đưa lên Authorization Endpoint hay URL callback.
- [ ] `requireProofKey(true)` được khai báo/kiểm chứng trong registration thực tế.
- [ ] Kiểm tra lỗi thiếu challenge, sai verifier, code replay và PKCE downgrade.
- [ ] Client ràng buộc `state`/verifier với browser session; OIDC `nonce` khi áp dụng.
- [ ] Redirect URI exact match, TLS, issuer và endpoint URLs nhất quán.
- [ ] BFF giữ secret và OAuth tokens server-side; cookie/session được bảo vệ trước CSRF/XSS.
- [ ] Đã kiểm tra phiên bản Spring, persistence và hoạt động nhiều node, không dựa vào mặc định không rõ.

## 11. Câu hỏi tự kiểm tra

1. **Confidential client đã có `client_secret_basic` thì PKCE còn tác dụng không?** Có: PKCE gắn code với transaction; secret chỉ chứng minh client khi đổi code.
2. **PKCE có làm SPA trở thành confidential không?** Không: SPA vẫn không thể giữ shared secret một cách đáng tin cậy.
3. **Nếu client gửi `code_challenge_method=S256` nhưng đổi code bằng verifier khác?** Token Endpoint phải từ chối.
4. **Nếu mã code đã đổi thành token rồi, verifier đúng có đổi lại được không?** Không; authorization code là một lần sử dụng.
5. **`requireProofKey(true)` có đồng nghĩa đã xác thực client chưa?** Không; confidential client vẫn cần credential theo method đã đăng ký.
6. **Vì sao một confidential client Spring Security cần thiết lập PKCE ở hai nơi?** Server phải **enforce**, còn RP/OAuth2 Client phải **generate và gửi** verifier/challenge.
7. **Làm sao phát hiện code injection do nhiều tab?** Kiểm tra `state`/verifier ràng buộc từng transaction, thử tráo code giữa hai flow.
8. **Thấy `invalid_grant` có nên tắt PKCE để chữa nhanh?** Không; kiểm tra verifier, code expiry, single-use, redirect, client và state storage.

## 12. Tài liệu tham khảo

- [RFC 7636 — Proof Key for Code Exchange](https://www.rfc-editor.org/rfc/rfc7636): định dạng verifier, phép biến đổi `S256`, flow và chống code interception.
- [RFC 9700 — OAuth 2.0 Security Best Current Practice, $2.1.1](https://www.rfc-editor.org/rfc/rfc9700): **public client MUST dùng PKCE**, **confidential client được khuyến nghị dùng PKCE**, chống code injection và CSRF.
- [RFC 8252 — OAuth 2.0 for Native Apps](https://www.rfc-editor.org/rfc/rfc8252): PKCE trong mobile/desktop/native và bảo vệ redirect.
- [Spring Authorization Server 1.5.x — SPA with PKCE](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-pkce.html): đăng ký client public bằng `none` và `requireProofKey(true)`, hạn chế refresh token của public clients trong implementation này.
- [Spring Authorization Server 1.5.x — ClientSettings API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/settings/ClientSettings.html): `isRequireProofKey()` và giá trị mặc định theo phiên bản.
- [Spring Authorization Server — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): `RegisteredClient`, `ClientSettings` và authorization state.
- [Spring Security — OAuth2 Client Authorization Grant Support](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorization-grants.html): PKCE ở ứng dụng client và `DefaultOAuth2AuthorizationRequestResolver`.
- [Spring Security — OAuth2 Client Authentication](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/client-authentication.html): public client `none` và các client authentication methods.
- [Spring Security — OAuth2AuthorizationRequestCustomizers API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/client/web/OAuth2AuthorizationRequestCustomizers.html): `withPkce()` và lưu verifier trong attributes.

**Kết luận:** Với **Authorization Code grant**, PKCE S256 là **ràng buộc mỗi authorization code vào một giao dịch đã khởi tạo**. Public client phải dùng PKCE; confidential client nên dùng **cả PKCE và client authentication**. Trong Spring Authorization Server, khai báo `ClientSettings.requireProofKey(true)` cho đúng registration; trong OAuth2 Client, phải tạo, giữ và gửi verifier/challenge đúng giao dịch. Đây là hai nửa bổ sung cho nhau, không phải hai lựa chọn thay thế.
