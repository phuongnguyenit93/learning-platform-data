# 8.6. Bổ sung nonce cho yêu cầu OIDC

Trong **OpenID Connect (OIDC) Authorization Code Flow**, ứng dụng Spring Security chuyển trình duyệt đến OpenID Provider (OP), nhận **authorization code** khi trình duyệt quay về, đổi code lấy token và xác minh **ID Token** trước khi đăng nhập người dùng. Một ID Token hợp lệ về chữ ký và thời hạn chưa tự chứng minh rằng token đó thuộc **đúng lần đăng nhập đang chờ**.

Tham số **`nonce`** giải quyết một phần quan trọng của bài toán này: OIDC Client sinh một giá trị riêng cho authorization request, gửi giá trị đó cho OP, rồi yêu cầu **ID Token** nhận được phải mang lại giá trị tương ứng. Khi client kiểm tra thành công ràng buộc này cùng các điều kiện OIDC khác, nguy cơ dùng lại hoặc tráo ID Token giữa các lần xác thực được giảm thiểu.

Bài học trình bày cách **bổ sung, bảo toàn và kiểm tra nonce** trong **Spring Boot 3.x / Spring Security 6.x với Servlet và `oauth2Login()`**, bao gồm cả trường hợp dùng resolver mặc định và trường hợp cần tùy biến authorization request. Đặc biệt, cần hiểu rằng **Spring Security đã hỗ trợ nonce cho OIDC login**: cấu hình chuẩn thường không yêu cầu tự viết mã sinh nonce.

## 1. Nonce nằm ở đâu trong luồng OIDC?

Một lần đăng nhập có thể được mô tả như sau:

```mermaid
sequenceDiagram
    autonumber
    actor B as Browser
    participant C as Spring Security OIDC Client
    participant OP as OpenID Provider
    B->>C: GET /oauth2/authorization/academy
    Note over C: Tạo authorization request<br/>sinh nonce và lưu ngữ cảnh
    C-->>B: 302 tới OP /authorize?...&nonce=N
    B->>OP: GET /authorize?...&nonce=N
    OP->>OP: Xác thực người dùng
    OP-->>B: Redirect về callback với code và state
    B->>C: GET /login/oauth2/code/academy?code=...&state=...
    Note over C: Tìm authorization request đã lưu<br/>kiểm tra liên kết response/request
    C->>OP: POST /token (authorization code)
    OP-->>C: access_token + id_token
    Note over C: Xác minh ID Token và nonce<br/>theo ngữ cảnh đã lưu
    C-->>B: Đăng nhập thành công; tạo/lưu Authentication
```

`nonce` xuất hiện ở **authorization request gửi đến OP** và **claim trong ID Token**. Nó thường **không xuất hiện dưới dạng tham số callback** trong Authorization Code Flow; callback chủ yếu mang `code` và `state`. Trong ứng dụng server-side, backend Spring xác minh nonce sau khi đổi code và nhận ID Token.

Ví dụ authorization request rút gọn:

```http
GET /authorize?response_type=code
    &client_id=academy-web
    &redirect_uri=https%3A%2F%2Fapp.example.com%2Flogin%2Foauth2%2Fcode%2Facademy
    &scope=openid%20profile
    &state=STATE_7b...
    &nonce=NONCE_b9... HTTP/1.1
Host: idp.example.com
```

Response ID Token, *sau khi payload đã được giải mã để minh họa*, có thể chứa:

```json
{
  "iss": "https://idp.example.com/realms/academy",
  "sub": "user-481",
  "aud": "academy-web",
  "iat": 1794800000,
  "exp": 1794800600,
  "nonce": "NONCE_b9..."
}
```

Các giá trị `NONCE_b9...` chỉ là ký hiệu: trong triển khai thật phải dùng chuỗi ngẫu nhiên đủ khó đoán và tuân theo cách Spring Security xử lý nonce. Payload JWT đọc được chưa nói lên tính xác thực; phải **kiểm tra chữ ký và các claims** trước khi tin vào nó.

## 2. Nonce bảo vệ điều gì và không bảo vệ điều gì?

### 2.1. Nguy cơ replay và ID Token substitution

Hãy xét hai lần đăng nhập:

- Lần A dùng nonce `N_A`, client mong nhận ID Token có nonce tương ứng với `N_A`.
- Lần B dùng nonce `N_B`, OP phát ID Token cho lần B.

Nếu có tình huống token của lần B bị đưa vào bước xác minh của lần A, chữ ký và `iss` có thể vẫn hoàn toàn hợp lệ vì cả hai token đều do cùng OP phát. **Nonce khác nhau là tín hiệu cho thấy token B không được tạo cho yêu cầu A.** Client phải từ chối token đó khi nonce không khớp.

Lưu ý: nonce bảo vệ một ràng buộc của luồng xác thực, **không phải cơ chế chống mọi dạng replay ở mọi lớp**. Nếu kẻ tấn công chiếm được toàn bộ session/ngữ cảnh và token hoặc làm sai lệch logic xác minh, nonce không đủ để ngăn toàn bộ hậu quả.

### 2.2. Phân biệt `state`, `nonce` và PKCE

Ba giá trị thường cùng tồn tại trong Authorization Code Flow:

| Đặc điểm | `state` | `nonce` | PKCE |
| --- | --- | --- | --- |
| Giá trị gửi từ client ở authorization request | `state` | `nonce` | `code_challenge` và `code_challenge_method` |
| Giá trị được trả/kiểm tra ở đâu? | Callback có `state`; client đối chiếu với request đã lưu | ID Token có claim `nonce`; client xác minh | Token request có `code_verifier`; OP xác minh |
| Mối đe dọa trọng tâm | Authorization response bị đưa vào sai luồng, login CSRF | ID Token không thuộc lần xác thực hiện tại, replay/substitution | Authorization code bị chặn rồi dùng để đổi token |
| Ai kiểm tra chính? | OAuth2/OIDC Client | OIDC Client | Authorization Server |
| Có dùng thay cho access token không? | Không | Không | Không |

Một request OIDC có thể chứa cả ba:

```text
GET /authorize
  ?response_type=code
  &client_id=academy-web
  &scope=openid%20profile
  &state=RANDOM_STATE
  &nonce=RANDOM_NONCE
  &code_challenge=CHALLENGE_S256
  &code_challenge_method=S256
```

Giá trị `code_verifier` phải được giữ tại client để sử dụng ở token endpoint; không gửi verifier trên front-channel. Việc `state` hợp lệ không cho phép bỏ qua nonce, và việc nonce hợp lệ không thay cho PKCE hoặc việc xác minh chữ ký ID Token.

### 2.3. OIDC có bắt buộc gửi nonce không?

Theo **OpenID Connect Core**, yêu cầu về nonce phụ thuộc response type/flow. Với **Authorization Code Flow** thuần (response type `code`), tham số nonce là **tùy chọn ở cấp giao thức**; với một số flow trả token trực tiếp qua front-channel, nonce là bắt buộc theo điều kiện đặc tả.

Tuy nhiên, **khi client đã gửi `nonce`**, OP phải phản ánh giá trị phù hợp trong ID Token và **client phải kiểm tra** claim đó theo quy tắc OIDC. Vì mục tiêu thực hành là xây ứng dụng OIDC Client vững chắc, việc sử dụng nonce cho code flow là một biện pháp phòng vệ hợp lý.

Không nên diễn giải “không bắt buộc với code flow” thành “có thể nhận mọi ID Token mà không cần liên kết phiên xác thực”.

## 3. Thuộc tính của một nonce được tạo đúng cách

Nonce là một chuỗi dùng để liên kết *một lần yêu cầu xác thực* với ID Token của lần đó. Nó có các đặc tính:

1. **Không dự đoán được:** dùng bộ sinh ngẫu nhiên an toàn mật mã (`SecureRandom` hoặc cơ chế an toàn của framework), không dùng timestamp/username/bộ đếm.
2. **Tươi mới cho mỗi yêu cầu:** mỗi lần bắt đầu OAuth2/OIDC login có nonce riêng, không dùng giá trị cố định toàn ứng dụng hoặc toàn người dùng.
3. **Gắn với ngữ cảnh request:** client lưu giá trị/biểu diễn cần thiết ở nơi tin cậy để lấy lại khi callback được xử lý.
4. **Không sống quá lâu:** dữ liệu đang chờ callback cần hết hạn và được dọn sau khi hoàn tất hoặc thất bại theo cơ chế repository.
5. **Không chứa dữ liệu nghiệp vụ nhạy cảm:** không nhúng email, client secret, mật khẩu hoặc access token vào nonce.
6. **Không dùng làm credential độc lập:** browser có thể quan sát nonce trong authorization redirect, nên không coi nonce là token cấp quyền.

Ví dụ sinh một chuỗi URL-safe để **hiểu nguyên tắc**:

```java
import java.security.SecureRandom;
import java.util.Base64;

public final class NonceGeneratorExample {
    private static final SecureRandom RANDOM = new SecureRandom();

    private NonceGeneratorExample() {}

    public static String newRandomNonce() {
        byte[] randomBytes = new byte[32];
        RANDOM.nextBytes(randomBytes);
        return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(randomBytes);
    }
}
```

Mỗi lần gọi tạo 32 byte ngẫu nhiên và biểu diễn Base64URL không padding, thường dài 43 ký tự. Đây là **minh họa nguồn ngẫu nhiên**, chưa phải lý do để ghi đè cơ chế nonce của Spring Security. Trong ứng dụng dùng `oauth2Login()`, nên để Spring tạo/lưu nonce và xác minh theo cùng quy ước.

### 3.1. Nonce có cần giữ bí mật như client secret?

Không. Trong Authorization Code Flow, nonce gửi qua URL authorization request tới OP và có thể thấy ở browser Network tab. Nó cần **khó đoán** để không dễ bị chuẩn bị trước cho lần xác thực khác, nhưng không phải một secret dài hạn tương đương client secret hay refresh token.

Bảo mật nằm ở **tổ hợp**: nonce được sinh an toàn, ràng buộc với yêu cầu đang chờ, ID Token do OP tin cậy ký và được client kiểm tra đầy đủ. Không nên log nonce một cách bừa bãi chỉ vì nó không phải credential dài hạn; URL login vẫn có thể mang những tham số nhạy cảm khác.

## 4. Luồng xử lý nonce trong Spring Security Servlet

Trong cấu hình OAuth2 Login tiêu chuẩn, các thành phần liên quan gồm:

| Thành phần Spring Security | Trách nhiệm đối với nonce |
| --- | --- |
| `ClientRegistration` | Xác định client, provider và scope. Scope `openid` kích hoạt bối cảnh đăng nhập OIDC. |
| `DefaultOAuth2AuthorizationRequestResolver` | Tạo authorization request; với OIDC, framework hỗ trợ thêm nonce và dữ liệu liên quan. |
| `OAuth2AuthorizationRequest` | Chứa các tham số gửi đến OP và attributes dùng nội bộ để khôi phục yêu cầu. |
| `OAuth2AuthorizationRequestRedirectFilter` | Sử dụng resolver, lưu authorization request và redirect browser đến OP. |
| `AuthorizationRequestRepository<OAuth2AuthorizationRequest>` | Lưu yêu cầu đang chờ callback, bao gồm dữ liệu tương quan cần để xác minh. |
| `HttpSessionOAuth2AuthorizationRequestRepository` | Repository mặc định thường dùng trong ứng dụng Servlet, lưu authorization request qua HTTP session. |
| `OAuth2LoginAuthenticationFilter` | Nhận callback, lấy lại authorization request, chuyển quá trình xác thực cho manager/provider. |
| `OidcAuthorizationCodeAuthenticationProvider` | Xử lý OIDC Authorization Code Flow và phối hợp xác minh ID Token, trong đó có nonce khi được sử dụng. |
| `OidcUserService` | Xây dựng OIDC principal sau khi thông tin xác thực thích hợp đã được kiểm tra. |

### 4.1. Khi nào Spring tự thêm nonce?

Với cấu hình Spring Security OAuth2 Login thông dụng, **client registration có scope `openid`** được xử lý như yêu cầu OIDC. Resolver mặc định có hỗ trợ sinh nonce cho authorization request OIDC; ứng dụng thường không phải khai báo một property như `nonce: true` trong `application.yml`.

Ví dụ registration:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          academy:
            provider: academy-oidc
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            scope:
              - openid
              - profile
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
        provider:
          academy-oidc:
            issuer-uri: ${OIDC_ISSUER_URI}
```

Điều cần quan sát là authorization redirect có `scope=openid...` và tham số `nonce`. Khi sử dụng resolver mặc định, Spring Security lo liệu cả việc giữ dữ liệu nonce cần thiết để kiểm tra sau callback.

**Không suy ra nonce đã được bật chỉ vì bạn thêm chuỗi `openid` vào một URL thủ công**. Nếu ứng dụng sử dụng custom `OAuth2AuthorizationRequestResolver` hoặc tự xây dựng authorization request, code tùy biến có thể vô tình bỏ qua xử lý mặc định.

### 4.2. Nonce trên đường truyền và nonce trong attributes

Một `OAuth2AuthorizationRequest` có hai khu vực đáng chú ý:

- **`additionalParameters`**: các tham số bổ sung sẽ được đưa vào authorization request gửi tới OP, ví dụ tham số `nonce`.
- **`attributes`**: dữ liệu phụ trợ nội bộ gắn với request, không nhất thiết được gửi nguyên dạng qua browser; có thể dùng để giữ thông tin phục vụ xác thực callback.

Trong một số phiên bản triển khai của Spring Security, **biểu diễn nonce lưu nội bộ khác với giá trị nonce gửi trên wire**: ví dụ tạo chuỗi ngẫu nhiên gốc và dùng biểu diễn băm cho tham số gửi ra; bước kiểm tra ID Token phải áp dụng **đúng quy ước tương ứng**. Điều đó lý giải vì sao việc tự ghi thêm `nonce` vào `additionalParameters` mà không cập nhật ngữ cảnh nội bộ có thể gây lỗi, dù nhìn trong browser thấy nonce xuất hiện.

**Nguyên tắc an toàn:** đừng giả định `attributes.get("nonce")` luôn bằng từng byte với tham số `nonce` ngoài URL ở mọi phiên bản. Để framework tạo và kiểm tra chúng theo cùng cơ chế; khi phải thay đổi, cần dựa vào API và phiên bản chính xác đang chạy.

### 4.3. Nonce đi qua `AuthorizationRequestRepository`

Trước khi gửi redirect, Spring lưu authorization request vào repository. Với mô hình Servlet, HTTP session là lựa chọn thông dụng:

```text
Browser                                  Spring application
   |                                             |
   | GET /oauth2/authorization/academy           |
   |-------------------------------------------->|
   |                                             | Tạo:
   |                                             |  - state
   |                                             |  - nonce data
   |                                             |  - PKCE data (nếu bật)
   |                                             | Lưu OAuth2AuthorizationRequest
   |<--------------------------------------------|
   | 302 tới OP + session cookie                  |
   |                                             |
   | ... Browser xác thực ở OP ...                |
   |                                             |
   | GET /login/oauth2/code/academy?code=&state= |
   | Cookie: JSESSIONID                           |
   |-------------------------------------------->|
   |                                             | Khôi phục request
   |                                             | Chuyển dữ liệu đến OIDC provider
   |                                             | Kiểm tra ID Token/nonce
```

Nếu browser không gửi lại đúng session cookie hoặc session không còn dữ liệu đã lưu, ứng dụng có thể thất bại **trước khi đến bước kiểm tra nonce**. Không thể khôi phục nonce bằng cách tự lấy bất kỳ giá trị nào từ URL callback vì callback code flow thông thường không mang nonce do client đã gửi.

Đối với ứng dụng chạy nhiều instance, chiến lược chia sẻ session hoặc routing phải bảo đảm callback có thể tìm được request ban đầu. Với callback qua cross-site redirect, cần xem xét `SameSite`, `Secure`, domain/path cookie, HTTPS và cấu hình reverse proxy.

## 5. Cấu hình OIDC Client tối thiểu để có nonce

### 5.1. Dependency

Ví dụ Maven có Spring Boot dependency management:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-client</artifactId>
</dependency>
```

Với Gradle:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
```

### 5.2. `application.properties` tương đương

Nếu dự án dùng properties thay cho YAML:

```properties
spring.security.oauth2.client.registration.academy.provider=academy-oidc
spring.security.oauth2.client.registration.academy.client-id=${OIDC_CLIENT_ID}
spring.security.oauth2.client.registration.academy.client-secret=${OIDC_CLIENT_SECRET}
spring.security.oauth2.client.registration.academy.authorization-grant-type=authorization_code
spring.security.oauth2.client.registration.academy.scope=openid,profile
spring.security.oauth2.client.registration.academy.redirect-uri={baseUrl}/login/oauth2/code/{registrationId}
spring.security.oauth2.client.provider.academy-oidc.issuer-uri=${OIDC_ISSUER_URI}
```

Bạn chỉ cần dùng **một trong hai** file cấu hình tương đương, không sao chép cả hai với các giá trị chồng lấn. `OIDC_CLIENT_SECRET` nên lấy từ environment/secret manager. Issuer phải là issuer thực do OP công bố; domain `idp.example.com` dưới đây chỉ minh họa:

```text
OIDC_CLIENT_ID=academy-web
OIDC_CLIENT_SECRET=<gia-tri-bi-mat-cua-client>
OIDC_ISSUER_URI=https://idp.example.com/realms/academy
```

Tại OP, callback tương ứng cần được cho phép, ví dụ:

```text
http://localhost:8080/login/oauth2/code/academy
```

Local có thể dùng loopback HTTP theo chính sách OP; production cần HTTPS public URL đúng cấu hình.

### 5.3. `SecurityFilterChain`

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
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
                .requestMatchers("/", "/error", "/assets/**").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(Customizer.withDefaults());

        return http.build();
    }
}
```

Với cấu hình này, browser có thể bắt đầu login:

```text
http://localhost:8080/oauth2/authorization/academy
```

Khi request đi qua resolver chuẩn, Spring tự xây authorization request OIDC với các tham số cần thiết. **Không cần tự viết controller** cho `/login/oauth2/code/academy` hay tự thêm nonce vào response callback.

## 6. Kiểm tra nonce đã xuất hiện trong authorization request

### 6.1. Quan sát front-channel bằng browser

Trong môi trường phát triển:

1. Mở Developer Tools → **Network**, bật **Preserve log** để giữ redirect.
2. Truy cập `http://localhost:8080/oauth2/authorization/academy`.
3. Tìm response `302` từ ứng dụng, xem header `Location` trỏ tới authorization endpoint của OP.
4. Mở URL hoặc request tương ứng, đọc query parameters.
5. Xác định `scope` chứa `openid` và có tham số `nonce` trong authorization request.

Ví dụ các tham số cần tìm (giá trị tượng trưng):

```text
response_type=code
client_id=academy-web
redirect_uri=http://localhost:8080/login/oauth2/code/academy
scope=openid profile
state=5c92...
nonce=ad21...
```

Nếu dùng PKCE, có thêm:

```text
code_challenge_method=S256
code_challenge=<challenge>
```

Lưu ý **`state` và `nonce` phải khác nhau về vai trò**; đừng tự ép chúng bằng nhau chỉ để dễ ghi log. Cũng không giả định mọi client luôn dùng cùng định dạng nonce khi framework có thể biến đổi giá trị trước khi gửi.

### 6.2. Token request sẽ không xuất hiện trong browser

Sau khi OP redirect callback về ứng dụng:

```text
GET /login/oauth2/code/academy?code=...&state=...
```

Spring backend mới gọi Token Endpoint. ID Token thường được trả về trên **back-channel**. Vì vậy Network tab của browser có thể cho bạn thấy nonce gửi đi, nhưng **không trực tiếp thấy payload ID Token mà backend nhận**, trừ khi ứng dụng cố ý lộ token qua response và điều đó không được khuyến khích.

Khi xác minh trong môi trường phát triển, nên quan sát kết quả login và log lỗi đã **loại bỏ credential**. Tránh sao chép nguyên callback URL (có code), session cookie, access/refresh token hoặc ID Token vào ticket công khai.

## 7. Nếu muốn thêm tham số tùy biến, hãy giữ nguyên nonce mặc định

Nhiều yêu cầu phát sinh từ OIDC provider thực tế không phải là thay nonce, mà là thêm `prompt`, `login_hint`, `max_age` hoặc tham số provider-specific vào **authorization request**. Khi đó, nên bắt đầu từ `DefaultOAuth2AuthorizationRequestResolver` và giữ nguyên quy tắc nonce của Spring.

Ví dụ thêm `prompt=login` (buộc OP cân nhắc xác thực lại theo hỗ trợ của OP):

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizationRequestResolver;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class AuthorizationRequestConfig {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            ClientRegistrationRepository clientRegistrations)
            throws Exception {

        var resolver = new DefaultOAuth2AuthorizationRequestResolver(
                clientRegistrations,
                "/oauth2/authorization");

        resolver.setAuthorizationRequestCustomizer(builder ->
                builder.additionalParameters(parameters ->
                        parameters.put("prompt", "login")));

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error", "/assets/**").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(oauth2 -> oauth2
                .authorizationEndpoint(endpoint -> endpoint
                    .authorizationRequestResolver(resolver)));

        return http.build();
    }
}
```

Đây là **phương án thay thế** bean `SecurityFilterChain` ở mục trước; không thêm cả hai bean có cùng matcher mặc định vào một ứng dụng.

Tại sao ví dụ này liên quan nonce? Vì resolver chuẩn vẫn xử lý authorization request OIDC và dữ liệu nonce tương ứng; customizer chỉ thêm tham số khác. **Bạn không cần tái tạo hoặc ghi đè nonce bằng tay** để thêm `prompt`. Nếu thêm một customizer khác cho PKCE, cần bảo toàn các tùy biến trước đó và sử dụng API được hỗ trợ thay vì dựng request mới từ đầu một cách thiếu thông tin.

### 7.1. Khi phải bọc `OAuth2AuthorizationRequestResolver`

Nếu bài toán yêu cầu thay đổi tham số dựa trên request (ví dụ điều kiện chọn OP hoặc username hint), có thể viết decorator quanh resolver chuẩn. Nguyên tắc là:

```text
delegate.resolve(request)
         |
         v
OAuth2AuthorizationRequest đã có
  - state và thông tin correlation
  - OIDC nonce và attributes liên quan
  - PKCE nếu được bật
         |
         v
OAuth2AuthorizationRequest.from(original)
  - chỉ thêm/sửa tham số nghiệp vụ cần thiết
  - giữ nguyên dữ liệu nonce, state, PKCE
         |
         v
Lưu vào AuthorizationRequestRepository như cũ
```

Ví dụ khung decorator (bỏ qua điều kiện nghiệp vụ để tập trung vào cơ chế):

```java
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.security.oauth2.core.endpoint.OAuth2AuthorizationRequest;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizationRequestResolver;

public final class PromptRequestResolver
        implements OAuth2AuthorizationRequestResolver {

    private final OAuth2AuthorizationRequestResolver delegate;

    public PromptRequestResolver(OAuth2AuthorizationRequestResolver delegate) {
        this.delegate = delegate;
    }

    @Override
    public OAuth2AuthorizationRequest resolve(HttpServletRequest request) {
        return withPrompt(delegate.resolve(request));
    }

    @Override
    public OAuth2AuthorizationRequest resolve(
            HttpServletRequest request,
            String clientRegistrationId) {
        return withPrompt(delegate.resolve(request, clientRegistrationId));
    }

    private OAuth2AuthorizationRequest withPrompt(
            OAuth2AuthorizationRequest original) {

        if (original == null) {
            return null;
        }

        return OAuth2AuthorizationRequest.from(original)
                .additionalParameters(params ->
                        params.put("prompt", "login"))
                .build();
    }
}
```

Để dùng decorator, cấu hình `authorizationRequestResolver(new PromptRequestResolver(defaultResolver))` trong `oauth2Login().authorizationEndpoint(...)`. Code này dùng `OAuth2AuthorizationRequest.from(original)` để giữ phần request đã có; nếu tự tạo một authorization request hoàn toàn mới, bạn phải bảo toàn đầy đủ redirect URI, state, nonce, PKCE và thông tin registration.

Đây là **một ví dụ cách giữ nonce khi bổ sung tham số**, không phải lời khuyên buộc mọi dự án phải custom resolver. Với nhu cầu đơn giản, customizer trực tiếp như mục 7 là đủ.

## 8. Trường hợp thực sự cần tự tạo nonce

Có những tình huống tích hợp rất đặc biệt: một client không dùng resolver tiêu chuẩn, cần tạo authorization request ngoài đường đi `oauth2Login()`, hoặc đang viết một extension cho Spring Security. Khi đó, khái niệm bổ sung nonce thủ công có bốn bước bắt buộc:

1. Sinh nonce mới bằng nguồn ngẫu nhiên an toàn cho **mỗi** authorization request.
2. Đưa giá trị nonce cần gửi vào **tham số authorization request** tới OP.
3. Lưu dữ liệu tương quan trong ngữ cảnh được bảo vệ của client, đảm bảo có thể lấy lại khi callback.
4. Sau token exchange, xác minh **claim `nonce` trong ID Token** theo đúng giá trị/biểu diễn mà client đã gửi, và từ chối token nếu sai hoặc thiếu trong trường hợp đã gửi nonce.

```text
Client bắt đầu login
    |
    +--> tạo nonce ngẫu nhiên
    +--> chuẩn bị giá trị đưa vào authorization URL
    +--> lưu ngữ cảnh nonce theo flow
    |
    v
OP nhận nonce ở /authorize
    |
    +--> phát ID Token có claim nonce tương ứng
    |
    v
Client nhận ID Token sau /token
    |
    +--> xác minh chữ ký, iss, aud, exp ...
    +--> lấy dữ liệu nonce đã lưu từ flow hiện tại
    +--> kiểm tra claim nonce
    |
    +--> sai/thiếu => từ chối login
    +--> hợp lệ + các điều kiện khác hợp lệ => tiếp tục Authentication
```

**Không nên chỉ thêm `parameters.put("nonce", random)`** vào một resolver hoàn toàn tự viết rồi mặc định rằng Spring sẽ nhớ giá trị đó để kiểm tra. Tùy cách bộ xác minh OIDC đọc dữ liệu, việc không lưu nonce nội bộ đúng cấu trúc có thể khiến xác minh thất bại hoặc, nguy hiểm hơn, mất kiểm tra ràng buộc.

### 8.1. Mối quan hệ giữa raw nonce, nonce hash và claim trong ID Token

OIDC định nghĩa mối quan hệ logic: **nonce claim của ID Token phải tương ứng với tham số nonce trong authorization request**. Bản thân OIDC không bắt buộc client tạo tham số bằng raw random bytes hay bằng SHA-256 của một chuỗi random riêng; đó là một lựa chọn của client implementation miễn sao giá trị gửi đi được đối chiếu đúng.

Một số implementation của Spring Security sử dụng quy ước tương tự:

```text
rawNonce = secureRandom()
wireNonce = BASE64URL(SHA256(ASCII(rawNonce)))

Authorization request thêm:
  nonce = wireNonce

Ngữ cảnh tạm của client lưu:
  rawNonce

Khi nhận ID Token:
  claim nonce phải tương ứng với wireNonce
  và phải được xác minh bằng cùng quy ước
```

Đây là **mô tả quy ước triển khai có thể xuất hiện**, không phải API bắt buộc trong mọi bản Spring Security. Không lấy ví dụ này để tự thay bộ xác minh mặc định khi chưa xác định chính xác source/API của phiên bản đang dùng.

Nếu cần can thiệp vì yêu cầu provider, hãy thiết kế sao cho **giá trị gửi ra, giá trị lưu và hàm đối chiếu ở OIDC AuthenticationProvider nhất quán**; tránh “sửa nhanh” bằng cách bỏ nonce validation khi gặp lỗi.

### 8.2. Không chuyển nonce thành dữ liệu có thể sửa bởi browser

Lỗi thiết kế thường gặp:

```text
Browser redirect chứa nonce=N_A
Callback chứa code=...
Server lấy nonce từ một query parameter tùy ý mà browser gửi
Server so ID Token nonce với giá trị browser mới đưa
```

Nếu server tin vào một giá trị do browser mới cung cấp tại callback mà không liên kết với authorization request đã lưu, đối thủ có thể thay đổi cả thông tin tham chiếu. **Giá trị kỳ vọng phải đến từ trạng thái tin cậy đã tạo khi khởi đầu flow**, không phải được client chấp nhận tùy ý ở cuối flow.

## 9. Nonce, ID Token và các bước xác minh bắt buộc khác

Ngay cả khi nonce khớp, client vẫn phải xác minh đầy đủ ID Token.

| Điều kiện | Tại sao cần |
| --- | --- |
| Chữ ký và thuật toán | Bảo đảm nội dung token được phát hành bởi bên có khóa ký tin cậy, theo thuật toán cho phép. |
| `iss` | Token phải từ đúng OP đã cấu hình cho authorization request. |
| `aud` | Token phải dành cho đúng OAuth2 Client (`client_id`); xử lý `azp` nếu áp dụng. |
| `exp` và các kiểm tra thời gian thích hợp | Token phải còn hiệu lực. |
| `nonce` | Nếu request đã gửi nonce, ID Token phải mang giá trị tương ứng với lần xác thực đó. |
| `auth_time`, `acr` và các claims theo yêu cầu | Được kiểm tra khi nghiệp vụ/protocol yêu cầu độ mới hoặc mức xác thực nhất định. |

### 9.1. Vì sao không tự parse JWT rồi kiểm tra một claim?

Một ví dụ dễ sai:

```java
// MINH HỌA CÁCH LÀM SAI - KHÔNG SỬ DỤNG
String claimNonce = decodeJwtWithoutVerifyingSignature(idToken)
        .getClaim("nonce");
if (expectedNonce.equals(claimNonce)) {
    // Không được kết luận rằng người dùng đã xác thực.
}
```

Nếu chỉ giải mã Base64URL payload và đọc `nonce`, client chưa kiểm tra chữ ký hoặc nguồn phát hành. Kẻ tấn công có thể tự tạo một chuỗi JWT có claim nonce bất kỳ mà không có chữ ký hợp lệ của OP. Vì vậy **nonce validation phải nằm trong quá trình xác minh ID Token đáng tin cậy**, không thể thay thế nó.

### 9.2. ID Token khác access token

- **ID Token** dùng để OIDC Client xác minh sự kiện xác thực và danh tính người dùng; nonce thuộc về lớp này.
- **Access token** dùng để truy cập resource server/API theo chính sách của API. Nó có thể là JWT hoặc opaque token.
- **Authorization code** là credential tạm trong callback để đổi token.
- **Session cookie** là cơ chế giữ phiên đăng nhập với ứng dụng Spring.

Không đọc claim nonce từ access token để quyết định người dùng đã đăng nhập OIDC. Không gửi ID Token làm Bearer access token cho API chỉ vì ID Token có chữ ký hợp lệ.

## 10. Khi nào nonce bị mất hoặc bị sai?

### 10.1. Sai do authorization request không được khôi phục

Trường hợp phổ biến là browser có callback đúng `code`/`state` nhưng Spring không tìm được authorization request tạm. Khi đó **không còn dữ liệu nonce đáng tin cậy** để đối chiếu, và flow phải bị dừng.

Nguyên nhân có thể là:

- Session cookie `JSESSIONID` không được gửi lại sau redirect;
- Browser áp dụng `SameSite` không phù hợp với response mode;
- Session hết hạn khi người dùng mất nhiều thời gian đăng nhập;
- App chạy nhiều instance nhưng session không chia sẻ;
- Reverse proxy tạo callback với hostname/scheme khác;
- Custom `AuthorizationRequestRepository` không lưu hoặc không khôi phục các attributes cần thiết;
- Một authorization request mới thay thế request trước đó khi có nhiều tab/flow đồng thời.

Không xử lý bằng cách **tạo nonce mới tại callback**: nonce mới không phải nonce của request đã gửi OP.

### 10.2. Sai do custom resolver ghi đè nonce

Giả sử resolver chuẩn đã tạo nonce, nhưng customizer viết:

```java
// Chỉ để minh họa lỗi có thể xảy ra; không áp dụng:
builder.additionalParameters(parameters ->
        parameters.put("nonce", "fixed-value-for-testing"));
```

Khi đó OP có thể phản ánh `fixed-value-for-testing` trong ID Token, nhưng ngữ cảnh nonce mà Spring lưu vẫn theo giá trị khác. Kết quả có thể là **nonce mismatch** hoặc rủi ro bảo mật nếu đồng thời có code tùy biến bỏ qua kiểm tra.

Một vấn đề khác là clone request mà **chỉ copy URL**:

```text
Old request:
  authorizationUri + state + nonce + attributes + PKCE context

Custom request sai:
  authorizationUri + state + nonce URL
  (mất attributes nội bộ và PKCE context)
```

Điều cần làm là dùng builder/cơ chế copy đầy đủ được hỗ trợ hoặc customizer trên resolver chuẩn. Không dùng một chuỗi URL làm “bản sao” của `OAuth2AuthorizationRequest`.

### 10.3. Sai do OP không đưa nonce vào ID Token

Nếu authorization request có tham số nonce, nhưng ID Token trả về không có claim tương ứng, việc xác thực phải thất bại theo yêu cầu OIDC. Cần kiểm tra:

- URL authorization request thực sự gửi tham số `nonce` nào;
- OP/realm/client thực sự được dùng là gì;
- Provider có hỗ trợ đúng OIDC flow và response type hay không;
- Token được nhận có thực sự là ID Token của flow hiện tại hay không;
- Có middleware/proxy hoặc customizer thay đổi authorization request không.

Không thêm tùy chọn “ignore nonce” vào logic ID Token validation để né lỗi từ một OP cấu hình sai.

### 10.4. Sai do nhiều browser tab hoặc nhiều lần bấm login

Một người dùng có thể mở hai lần đăng nhập:

```text
Tab A: state=S_A, nonce=N_A
Tab B: state=S_B, nonce=N_B
```

Nếu repository chỉ giữ **một** authorization request đang chờ mỗi session, request B có thể ghi đè A. Khi callback của A đến, Spring không tìm được `S_A` và ngữ cảnh `N_A` tương ứng. Thiết kế cần quyết định có hỗ trợ đồng thời hay không; nếu có, repository phải lưu phân biệt, giới hạn vòng đời và tiêu thụ từng request an toàn.

Không dùng chung nonce giữa A và B để tránh lỗi nhiều tab. Điều đó làm mất ý nghĩa ràng buộc nonce với từng lần xác thực.

## 11. Bảng chẩn đoán theo triệu chứng

| Triệu chứng | Lớp cần điều tra trước | Hướng xử lý |
| --- | --- | --- |
| Authorization redirect không có `nonce` | Registration/resolver | Scope có `openid` không? Có custom resolver thay mặc định không? |
| Callback báo không tìm thấy authorization request | Session/repository | Browser có gửi cookie? Session timeout, nhiều instance, `SameSite` và callback host có đúng không? |
| Callback thất bại vì `state` | Authorization response correlation | So flow khởi đầu với callback; tránh login song song hoặc mất request đã lưu. |
| Token endpoint từ chối `invalid_grant` | Code exchange/PKCE | Kiểm tra code một lần, redirect URI, client ID, PKCE verifier; chưa phải lỗi nonce của ID Token. |
| ID Token bị từ chối vì nonce không tương ứng | OIDC ID Token validation | So authorization request thực tế, ngữ cảnh nonce nội bộ, OP và customizer. |
| ID Token bị từ chối vì `iss`/`aud` | Issuer/client registration | Xác nhận metadata issuer, client ID và OP/tenant đúng. |
| Chữ ký ID Token thất bại | JWKS/signature | Kiểm tra khóa ký, `kid`, CA/TLS và thuật toán được phép. |
| Login trên local được, production lỗi | Proxy/cookie/session | HTTPS, forwarded headers tin cậy, external redirect URI, cookie `Secure`/`SameSite`. |
| Đăng nhập thành công nhưng request tiếp theo yêu cầu login | `SecurityContext`/session | Kiểm tra cơ chế lưu bối cảnh, cookie và session store. |
| Sau login, API trả `401` | Access token / Resource Server | Kiểm tra token dành cho API, scope, audience và API validation; nonce không giải quyết vấn đề này. |

Mã lỗi/exception chi tiết phụ thuộc phiên bản Spring Security, OAuth2 provider và failure handler đang dùng. Một lỗi ID Token validation có thể được bọc trong exception tổng quát; đừng dựa vào một chuỗi lỗi cố định để định nghĩa logic nghiệp vụ.

## 12. Thực hành quan sát một luồng an toàn

Mục tiêu thực hành là nhìn thấy nonce ở đúng chặng và chứng minh Spring tạo được phiên đăng nhập OIDC sau khi OP xác minh người dùng.

### Chuẩn bị

- Ứng dụng Spring Boot với `spring-boot-starter-oauth2-client`, security chain có `oauth2Login()`.
- OP hỗ trợ OIDC Discovery và đã đăng ký redirect URI phù hợp.
- Scope `openid` được cấp cho registration.
- Các biến `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET` và `OIDC_ISSUER_URI` có giá trị thực từ môi trường test.

### Thực hiện

1. Mở browser profile/private window mới và Developer Tools → Network.
2. Truy cập `/oauth2/authorization/academy`.
3. Quan sát redirect tới OP, ghi nhận **sự có mặt** của `state`, `nonce` và các tham số OIDC khác. Không cần lưu nguyên nonce/token vào báo cáo.
4. Đăng nhập test tại OP. Browser quay lại callback mang code/state.
5. Nếu xác thực thành công, ứng dụng đưa browser về trang yêu cầu trước đó hoặc success URL; truy cập endpoint đã bảo vệ để xác nhận session.
6. Đăng xuất khỏi ứng dụng, khởi động một flow mới và quan sát **nonce mới**. Nếu OP vẫn có SSO session, browser có thể quay lại nhanh hơn, nhưng client vẫn nên tạo ngữ cảnh đăng nhập mới.
7. Nếu ứng dụng tùy biến resolver, lặp lại luồng để quan sát rằng tham số nonce vẫn được giữ trên authorization redirect và callback hoàn tất.

### Controller minh họa đọc principal OIDC

```java
import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProfileController {

    @GetMapping("/profile")
    public Map<String, String> profile(
            @AuthenticationPrincipal OidcUser user) {

        return Map.of(
            "subject", user.getSubject(),
            "displayName",
            user.getFullName() == null ? "(không cung cấp)" : user.getFullName()
        );
    }
}
```

Controller không tự kiểm tra nonce, vì **xác minh OIDC phải hoàn tất trước khi principal được chấp nhận**. Ví dụ giả định endpoint chỉ cho người dùng đăng nhập qua OIDC; nếu ứng dụng hỗ trợ cơ chế đăng nhập khác, cần xử lý kiểu principal phù hợp.

## 13. Những tình huống tùy biến dễ làm sai

### 13.1. Dùng `nonce` cố định để tiện kiểm thử

```text
nonce = "123456"
```

Một giá trị cố định phá hỏng khả năng phân biệt giữa các lần xác thực. Hãy dùng nonce mới khó đoán cho mỗi authorization request. Kiểm thử có thể thay nguồn ngẫu nhiên bằng thành phần có kiểm soát trong test scope, nhưng production không được dùng giá trị cố định.

### 13.2. Dùng username hoặc timestamp làm nonce

```text
nonce = "alice-2026-11-16-09-00"
```

Thông tin này có thể dự đoán, có thể tiết lộ dữ liệu người dùng, và không đạt mục tiêu của nonce. Dùng CSPRNG thay vì ghép dữ liệu con người dễ đoán.

### 13.3. Đọc `nonce` từ URL callback rồi xác nhận

Trong Authorization Code Flow, callback thường chỉ mang `code` và `state`. Nếu custom code tự nhận query param `nonce` tại callback rồi dùng làm expected nonce, giá trị này có thể bị browser hoặc bên thứ ba sửa. **Expected nonce phải đến từ yêu cầu đã lưu**, không phải một tham số mới gửi ở cuối flow.

### 13.4. Bỏ nonce validation vì ID Token “đã có chữ ký”

Chữ ký giúp biết token không bị thay đổi bởi bên ngoài và do khóa được tin cậy ký; nonce giúp biết token thuộc đúng yêu cầu xác thực hiện tại. Hai kiểm tra phục vụ mục tiêu khác nhau. Khi request có nonce, phải xác minh claim tương ứng.

### 13.5. Thêm nonce mà không lưu authorization request

Đưa `nonce` lên authorization redirect chỉ là **một nửa** chức năng. Nếu request repository không lưu ngữ cảnh tương quan, client không có expected nonce đáng tin cậy sau callback. Với Spring Security, hãy giữ cơ chế repository và dữ liệu attributes được resolver tạo.

### 13.6. Gộp `state` và `nonce` thành một biến duy nhất

Về mặt kỹ thuật, cả hai đều là giá trị có thể ngẫu nhiên, nhưng **ý nghĩa và điểm xác minh khác nhau**. Không dùng một customizer áp đặt chúng trùng nhau hoặc giả định rằng kiểm tra state tự động hoàn thành kiểm tra nonce. Nên giữ cách quản lý riêng của framework.

### 13.7. Tắt CSRF toàn ứng dụng vì OIDC callback gặp lỗi

`state`, `nonce` và PKCE là biện pháp của luồng OAuth2/OIDC; CSRF token của ứng dụng Servlet bảo vệ request thay đổi trạng thái dựa trên session cookie. Không tắt `csrf()` một cách rộng rãi chỉ để callback chạy; cần phân tích method, cookie policy, callback matcher và cơ chế lưu authorization request.

## 14. Những điểm mở rộng cần cân nhắc

### 14.1. Nhiều OpenID Provider

Nếu ứng dụng cho đăng nhập qua `academy` và `corporate`, mỗi authorization request phải được gắn với **đúng `ClientRegistration`/issuer**. Nonce giúp liên kết ID Token với yêu cầu đăng nhập, nhưng không thay việc kiểm tra `iss`, `aud` và các biện pháp chống mix-up khi nhiều OP.

Ví dụ cùng một chuỗi `sub` từ hai issuer khác nhau không nhất thiết là cùng người. Khi ánh xạ tài khoản, thường dùng cặp `(issuer, subject)` thay vì tin mỗi `sub` hay `email`.

### 14.2. OIDC logout và đăng nhập lại

Ứng dụng logout khỏi session Spring nhưng OP có thể vẫn giữ SSO cookie. Lần login sau có thể không yêu cầu nhập mật khẩu, nhưng vẫn là **một authorization request mới** và phải có dữ liệu tương quan mới. Nonce không tự thực hiện đăng xuất khỏi OP hoặc thu hồi access/refresh token.

OIDC RP-Initiated Logout, khi được hỗ trợ, là cơ chế riêng và có thể cần cấu hình bổ sung.

### 14.3. Request mang `prompt=none`

Ứng dụng có thể yêu cầu OP xác thực âm thầm bằng `prompt=none` nếu SSO session đã có. Dù không có màn hình đăng nhập, đó vẫn là một lần authorization request mới; nonce vẫn cần được quản lý độc lập và so với ID Token phù hợp. Nếu OP không thể đáp ứng, nó có thể trả OAuth2/OIDC error thay vì một code.

### 14.4. `max_age` và `auth_time`

Khi nghiệp vụ yêu cầu biết người dùng vừa xác thực gần đây hay chưa, có thể bổ sung `max_age` vào authorization request và kiểm tra `auth_time` trong ID Token theo yêu cầu OIDC. Đây là các tham số/claims có vai trò **khác nonce**: nonce gắn token với request, còn `max_age` liên quan độ mới xác thực.

### 14.5. Nhiều instance và session phân tán

Nếu authorization request và nonce lưu trong HTTP session của một JVM, callback chuyển sang instance khác có thể không khôi phục được request. Tùy kiến trúc, có thể dùng sticky sessions hoặc Spring Session với store phân tán. Cần bảo vệ và giới hạn thời gian sống của dữ liệu session vì nó chứa bối cảnh giao thức nhạy cảm.

## 15. Câu hỏi tự kiểm tra

**Câu 1 — Nonce ở callback.** Sau khi người dùng đăng nhập tại OP, callback chỉ có `code` và `state`. Có phải OP quên trả nonce?

> Không. Với Authorization Code Flow, nonce được gửi trong authorization request và phản ánh trong **ID Token** nhận ở token response, không bắt buộc là query param của callback.

**Câu 2 — Đã dùng state, có cần nonce?** Client kiểm tra state thành công rồi nhận ID Token có nonce khác yêu cầu đã gửi.

> Phải từ chối ID Token. State bảo vệ liên kết authorization response, nonce bảo vệ liên kết ID Token với lần xác thực.

**Câu 3 — ID Token có chữ ký hợp lệ nhưng nonce sai.** Ứng dụng có thể chỉ cảnh báo rồi cho login vì token còn hạn không?

> Không. Nếu client gửi nonce, kết quả không khớp vi phạm ràng buộc OIDC; không được tạo phiên đăng nhập thành công từ token đó.

**Câu 4 — Có cần tự viết nonce generator để dùng `oauth2Login()`?**

> Thường không. Với registration OIDC chuẩn và resolver mặc định, Spring Security hỗ trợ nonce. Điều cần làm là cấu hình scope `openid` đúng và giữ nguyên resolver/repository/token validation, rồi quan sát request để xác nhận hoạt động.

**Câu 5 — Custom resolver làm mất nonce.** Bạn thay resolver chuẩn bằng code tự tạo URL login với `client_id`, `scope` và `redirect_uri`. Sau đó login lỗi kiểm tra ID Token.

> Custom resolver có thể đã bỏ qua dữ liệu nonce/state/PKCE cần thiết. Nên mở rộng resolver chuẩn, bảo toàn `OAuth2AuthorizationRequest` và các attributes thay vì tự dựng URL thiếu bối cảnh.

**Câu 6 — Nonce mới tạo ở thời điểm callback.** Lý do gì không nên sinh nonce lúc nhận code?

> OP đã nhận một nonce **trước đó** ở authorization request; nonce mới không còn liên kết với token được cấp cho request ban đầu. Nó không phải giá trị tham chiếu có tính xác thực.

**Câu 7 — Nonce và access token.** Có nên gửi nonce thay cho `Authorization: Bearer <access_token>` khi gọi API?

> Không. Nonce là ràng buộc của OIDC login; API thường yêu cầu access token phù hợp với issuer, audience, scope và chính sách của resource server.

## 16. Ghi nhớ quy trình bổ sung nonce

```text
ClientRegistration có scope openid
          |
          v
DefaultOAuth2AuthorizationRequestResolver
  - tạo authorization request OIDC
  - sinh và bổ sung nonce theo quy ước framework
  - giữ thông tin cần thiết trong request attributes
          |
          v
AuthorizationRequestRepository lưu yêu cầu
          |
          v
Browser được redirect đến OP
  - authorization request chứa nonce
          |
          v
OP phát ID Token với nonce tương ứng
          |
          v
OAuth2LoginAuthenticationFilter nhận callback
  - khôi phục authorization request
          |
          v
OIDC AuthenticationProvider xác minh ID Token
  - signature / issuer / audience / time
  - nonce theo yêu cầu đã lưu
          |
          v
Tạo OidcUser, OAuth2AuthenticationToken
và lưu SecurityContext theo cấu hình
```

Trong ứng dụng Servlet dùng Spring Security, điểm bắt đầu đáng tin cậy nhất là **cấu hình OIDC Client có scope `openid` và dùng resolver mặc định**. Nếu cần thêm tham số vào authorization request, hãy mở rộng từ resolver chuẩn để giữ nguyên cơ chế nonce. Nếu thực sự cần tự tạo nonce, phải đồng bộ **giá trị gửi tới OP, dữ liệu lưu ở client và kiểm tra ID Token**; không chỉ thêm một query parameter rồi bỏ qua phần xác minh.

### Tài liệu tham khảo

- [OpenID Connect Core 1.0 — Authentication Request và ID Token](https://openid.net/specs/openid-connect-core-1_0.html).
- [OpenID Connect Core 1.0 — ID Token Validation](https://openid.net/specs/openid-connect-core-1_0.html#IDTokenValidation).
- [Spring Security Reference — OAuth 2.0 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html).
- [Spring Security Reference — Advanced OAuth 2.0 Login Configuration](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html).
- [Spring Security API — DefaultOAuth2AuthorizationRequestResolver](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/client/web/DefaultOAuth2AuthorizationRequestResolver.html).
- [Spring Security API — OAuth2AuthorizationRequest](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/core/endpoint/OAuth2AuthorizationRequest.html).
- [Spring Security API — OidcAuthorizationCodeAuthenticationProvider](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/client/oidc/authentication/OidcAuthorizationCodeAuthenticationProvider.html).
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749).
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700).
