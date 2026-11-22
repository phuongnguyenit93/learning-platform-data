# state, nonce, PKCE và các ràng buộc bảo vệ luồng đăng nhập

## Mục tiêu học tập

Bài học thuộc phần **Đăng nhập OAuth2/OIDC** của **Spring Security reactive (Spring WebFlux)**. Sau bài này, bạn có thể:

- Vẽ đúng **Authorization Code Flow** có OpenID Connect (OIDC), phân biệt browser, OAuth2 client/Relying Party, Authorization Server/Identity Provider (IdP) và resource server.
- Hiểu **`state`** gắn authorization response với **login request gốc và browser session**, **`nonce`** gắn **ID Token** với phiên xác thực OIDC, còn **PKCE (Proof Key for Code Exchange)** gắn **authorization code** với client đang giữ `code_verifier`.
- Nêu chính xác vai trò và giới hạn của `code_verifier`, `code_challenge`, `S256`, `iss`, `aud`, `exp`, `redirect_uri` và `registrationId`.
- Giải thích vì sao phải chống **login CSRF, authorization-code injection, code interception, token substitution/replay, IdP mix-up, open redirect và redirect URI manipulation**.
- Sử dụng `ServerHttpSecurity.oauth2Login(...)`, `DefaultServerOAuth2AuthorizationRequestResolver` và `OAuth2AuthorizationRequestCustomizers.withPkce()` cho ứng dụng WebFlux Java 17.
- Biết Spring Security lưu authorization request ở `WebSessionOAuth2ServerAuthorizationRequestRepository` mặc định; không biến `state` hay PKCE verifier thành hằng số hoặc tự đọc từ query của người dùng để xác thực.
- Chạy một chương trình Java 17 minh họa **PKCE S256 có output xác định**, cấu hình WebFlux OAuth2/OIDC client và **test tạo authorization request offline** mà không cần IdP thật.
- Thiết kế kiểm thử âm tính: state sai/thiếu/replay, PKCE verifier không khớp, ID Token nonce sai, issuer/audience sai, callback không dùng đúng session.

> **Phạm vi:** Spring Security **reactive**, OAuth2 **Authorization Code + OIDC**. Không nhầm với `OAuth2 Resource Server` chỉ xác thực Bearer token của API, hay cấu hình `HttpSecurity`/`HttpSessionOAuth2AuthorizationRequestRepository` của Servlet. Bài học tập trung vào những ràng buộc chống giả mạo/chèn mã trong **đăng nhập**, không xây Authorization Server từ đầu.

## 1. Ba giá trị state, nonce, PKCE giải quyết ba câu hỏi khác nhau

Khi browser bắt đầu đăng nhập qua một IdP, ứng dụng bị đưa ra ngoài origin của mình rồi nhận callback. Chỉ thấy `code` trên callback **không chứng minh** đó là kết quả của chính login request hiện tại.

| Cơ chế | Câu hỏi bảo mật | Tạo ở đâu? | Xuất hiện ở đâu? | Kiểm tra thế nào? |
|---|---|---|---|---|
| **state** | “Callback này có thuộc request đăng nhập vừa khởi tạo trên browser/session này không?” | OAuth2 client | Authorization request và callback (`state`) | So với authorization request đã lưu/bind với browser; không chấp nhận thiếu/sai/đã dùng. |
| **OIDC nonce** | “ID Token này có được phát cho **lần yêu cầu xác thực này** không?” | OIDC client | Authorization request (`nonce`), rồi trong ID Token claim `nonce` | Sau khi xác thực chữ ký ID Token, đối chiếu nonce theo quy tắc của client/framework. |
| **PKCE** | “Bên đổi authorization code có sở hữu bí mật tạm thời gắn với code này không?” | OAuth2 client | `code_challenge` ở authorization request; **`code_verifier` ở token request** | Authorization Server kiểm tra phép biến đổi challenge/verifier gắn với code. |
| **redirect_uri** | “Code chỉ được trả về endpoint callback đã đăng ký?” | Client đăng ký với IdP | Authorization request và callback destination | IdP đối chiếu redirect URI chính xác; client bind code/token request với URI đó. |
| **issuer/audience** | “Token này đến từ đúng IdP và dành cho đúng client?” | Authorization Server | ID Token và metadata | Client xác minh chữ ký, `iss`, `aud`, thời hạn, `azp` khi liên quan. |

**Không coi ba giá trị là một:** `state` không làm code bị đánh cắp trở nên vô dụng tại token endpoint; nonce OIDC không phải access token; PKCE không tự thay thế mọi bước kiểm tra ID Token/issuer hoặc trạng thái người dùng.

Các tiêu chuẩn bảo mật mới (RFC 9700, tháng 01/2025) ghi nhận PKCE và nonce có thể cung cấp cả lợi ích chống CSRF trong điều kiện rất cụ thể, nhưng khi dùng Spring Security OAuth2 Login, **nên giữ nguyên state/session binding và dùng PKCE + OIDC nonce để phòng thủ nhiều lớp**. Không lược bớt một check chỉ vì đã có check khác.

## 2. Authorization Code + OIDC: sơ đồ đường đi

Tình huống một WebFlux application ở `https://app.example.test` muốn đăng nhập bằng `https://idp.example.test`:

~~~text
Browser                  WebFlux OAuth2 Client             OIDC IdP
  |                              |                             |
  | GET /oauth2/authorization/oidc                           |
  |----------------------------->|                             |
  |                              | Generate state S             |
  |                              | Generate OIDC nonce N        |
  |                              | Generate PKCE verifier V     |
  |                              | challenge C = BASE64URL(     |
  |                              |     SHA256(ASCII(V)))        |
  |                              | Save request + V + N in      |
  |                              | WebSession-bound repository  |
  |<----- 302 authorize? --------|                             |
  |       response_type=code     |                             |
  |       client_id=...          |                             |
  |       redirect_uri=...       |                             |
  |       scope=openid ...       |                             |
  |       state=S                |                             |
  |       nonce=N / hash(N)      |                             |
  |       code_challenge=C       |                             |
  |       code_challenge_method=S256                           |
  |----------------------------------------------------------->|
  |                              |                      Login/consent
  |<------------------------ 302 callback?code=K&state=S -----|
  | GET /login/oauth2/code/oidc?code=K&state=S                |
  |----------------------------->|                             |
  |                              | Load saved request for S     |
  |                              | Reject if state/session bad |
  |                              | POST /token: code=K, V ...  |
  |                              |---------------------------->|
  |                              |         Validate V against C|
  |                              |<----------------------------|
  |                              | access_token + id_token     |
  |                              | Validate ID Token: sig,     |
  |                              | iss, aud, exp, nonce etc.   |
  |                              | Establish local login       |
  |<------ Login success/redirect|                             |
~~~

Trong Spring Security 6.x, OIDC request resolver có thể giữ **giá trị nonce gốc trong authorization-request attributes** và đưa **giá trị dẫn xuất từ nonce** vào request gửi đến IdP; khi nhận ID Token, OIDC authentication manager xác nhận quy tắc ràng buộc tương ứng. Vì vậy **không tự so sánh một string `nonce` thô bằng mắt** nếu đang dùng cơ chế hash nonce của framework. Quan trọng là cả **request nonce** và **ID Token nonce** được kiểm chứng theo cùng quy tắc đã triển khai.

Trong luồng thực tế, redirect thường là HTTP 302; status và trang login cuối có thể khác theo IdP/client config. Code/access token/ID Token phải được coi là thông tin nhạy cảm; không dán URL callback thật vào ticket hoặc log công khai.

## 3. state: chống callback giả mạo và login CSRF

### 3.1. State hoạt động như một correlation token

Ở request bắt đầu login, client sinh `state` **ngẫu nhiên, khó đoán và theo từng authorization attempt**. Client lưu `OAuth2AuthorizationRequest` liên quan trong session/repository của browser. IdP nhận `state` và phải trả lại nguyên giá trị trong authorization response.

Ví dụ dòng URL **minh họa, không phải token thật**:

~~~text
GET /oauth2/authorization/oidc
    -> 302 https://idp.example.test/authorize?
         response_type=code&
         client_id=client-web&
         state=S_X7m...&
         redirect_uri=https%3A%2F%2Fapp.example.test%2Flogin%2Foauth2%2Fcode%2Foidc

Callback hợp lệ:
GET /login/oauth2/code/oidc?code=K_abc&state=S_X7m...

Callback bị sửa:
GET /login/oauth2/code/oidc?code=K_abc&state=S_attacker
    -> từ chối, không được dùng code để tạo local session
~~~

Hãy hiểu `state` là **một giá trị opaque**, không phải object chứa user ID/role có thể tin cậy. Một phiên khác không được phép sử dụng state của phiên này để hợp thức hóa callback.

### 3.2. Login CSRF là gì?

Một kịch bản nguy hiểm: attacker đăng nhập ở IdP vào tài khoản của **attacker**, lấy một authorization response, rồi ép browser của nạn nhân truy cập callback để ứng dụng nạn nhân tạo session trỏ tới tài khoản attacker. Nạn nhân tưởng mình đang dùng tài khoản của mình nhưng thực chất ghi dữ liệu vào tài khoản attacker.

Không cần attacker biết mật khẩu của nạn nhân; đây là **login CSRF / session swapping**. State gắn với browser login attempt giúp ứng dụng không chấp nhận một callback xa lạ.

Quy tắc cần đạt:

1. Callback phải có `state` đúng với một **outstanding authorization request** đã lưu trong session/client context.
2. Request đã hoàn thành phải được **loại bỏ/đánh dấu đã dùng** để ngăn replay.
3. Request hết hạn hoặc không tìm được (session expired, mất cookie, đã khởi tạo luồng khác) phải fail closed.
4. Khi client hỗ trợ nhiều IdP, state còn phải gắn với **registration/issuer dự định**, không dùng code nhận từ IdP A gửi token endpoint IdP B.
5. Không để attacker kiểm soát state bằng cách gửi query `?state=...` rồi server chấp nhận như nguồn chân lý.

### 3.3. State không phải nơi lưu return URL tùy ý

Một số ứng dụng muốn sau login quay về `/orders/123`. Không tạo `state` bằng cách nối nguyên URL do client gửi vào và tin rằng callback có state hợp lệ thì mọi return target trong đó an toàn.

Cách thiết kế rõ ràng hơn:

~~~text
Trước redirect:
  server validate return path là đường dẫn nội bộ cho phép
  server save return path ở session/cache theo transaction ID
  server generate state ngẫu nhiên

Sau callback:
  validate state + session + issuer
  lấy lại return path đã được validate ở phía server
  redirect sang path nội bộ, không sang host tùy ý
~~~

Nếu state mang payload có ý nghĩa, cần **integrity protection** (ký/mã hóa nếu cần), session binding và hạn dùng. Tuyệt đối không phản chiếu `return_to=https://evil.example.test` thành Location sau login chỉ vì nó nằm trong state. Open redirect có thể làm lộ authorization code hoặc access token.

## 4. nonce: gắn ID Token vào lần xác thực OIDC

### 4.1. nonce khác state ở đâu?

`nonce` là tham số của **OpenID Connect Authentication Request**. IdP đưa một giá trị nonce tương ứng vào **ID Token** được cấp. Client xác minh sự trùng khớp theo thuật toán/cấu hình của thư viện, từ đó chống **ID Token replay/substitution** giữa các authentication transactions.

- `state` đi về ở **authorization response/callback**.
- `nonce` đi vào **ID Token được ký**, sau khi client đổi code và nhận token.
- `nonce` không phải `code_verifier` và không được gửi tới token endpoint như bí mật PKCE.
- `nonce` phải theo từng attempt, không dùng hằng số `nonce="demo"`.
- Không chỉ so `nonce`: ID Token vẫn cần xác minh **chữ ký JWS**, issuer, audience, expiration và các claims bắt buộc.

### 4.2. Những claim ID Token cần kiểm tra

Một ID Token payload **mang tính minh họa**, không phải chữ ký hay JWT hợp lệ:

~~~json
{
  "iss": "https://idp.example.test",
  "sub": "user-123",
  "aud": "web-client-id",
  "exp": 1893456000,
  "iat": 1893452400,
  "nonce": "expected-nonce-or-its-framework-derived-value"
}
~~~

Ý nghĩa:

| Claim | Điều cần kiểm tra |
|---|---|
| `iss` | Đúng issuer dự kiến, không nhận token của IdP ngẫu nhiên. |
| `sub` | Định danh user tại issuer; khóa user bền vững nên gắn **issuer + sub**, không chỉ email. |
| `aud` | Có client_id của ứng dụng; nếu nhiều audiences, xử lý `azp` theo OIDC. |
| `exp`/`iat` | Token không hết hạn, thời gian hợp lý và policy clock skew. |
| `nonce` | Match request nonce theo cơ chế triển khai, chống token replay/substitution. |
| Chữ ký `alg`/`kid`/JWKS | JWS phải được xác minh bằng thuật toán/khóa **được cấu hình tin cậy**; không tin alg tùy chọn từ token. |

Không dùng việc “JWT nhìn giống base64” hoặc payload JSON có `sub` làm chứng cứ đã xác thực. Việc giải mã payload không có chữ ký hợp lệ **không phải validation**.

### 4.3. Spring Security xử lý nonce mặc định

Với OIDC ClientRegistration có scope `openid`, `DefaultServerOAuth2AuthorizationRequestResolver` tạo ràng buộc nonce cho authorization request. Trong các phiên bản Spring Security 6.x, framework dùng cơ chế hash để đưa nonce qua request đồng thời giữ thông tin cần xác minh ở attributes của authorization request.

Khi OIDC login thành công, `OidcAuthorizationCodeReactiveAuthenticationManager` cùng các thành phần OIDC decoder/user service xác minh token và các điều kiện liên quan. **Không ghi đè/hủy nonce ở customizer**, không tự biến `scope=openid` thành `scope=profile` rồi nghĩ OIDC ID Token sẽ vẫn có.

Một OAuth2 provider **không hỗ trợ OIDC** có thể không cấp ID Token; khi đó không có OIDC nonce validation. Không tạo giả token ID để bắt `oauth2Login` coi nó là OIDC.

## 5. PKCE: bí mật theo lần đăng nhập bảo vệ authorization code

PKCE (RFC 7636) đọc là “pixy”. Nó được thiết kế để giảm rủi ro khi một **authorization code bị lấy cắp hoặc bị chèn** trên đường đi. Mấu chốt: người chỉ biết code không thể đổi nó thành access token nếu không biết bí mật `code_verifier` tương ứng.

### 5.1. Công thức S256

Client tạo:

1. `code_verifier`: một chuỗi **ngẫu nhiên mật mã** dài 43–128 ký tự trong bảng chữ cái URI unreserved theo RFC 7636.
2. `code_challenge`: `BASE64URL-ENCODE(SHA256(ASCII(code_verifier)))`, **không có padding**.
3. `code_challenge_method=S256`.

~~~text
V = random code_verifier (giữ bí mật trong transaction store)
C = BASE64URL_NOPAD(SHA256(ASCII(V)))

Authorization request:
  response_type=code
  code_challenge=C
  code_challenge_method=S256

Token request:
  grant_type=authorization_code
  code=K
  code_verifier=V

Authorization Server:
  C_stored_for_code == BASE64URL_NOPAD(SHA256(ASCII(V))) ?
      yes -> tiếp tục kiểm tra code/client/redirect_uri và cấp token
      no  -> từ chối token request
~~~

`code_verifier` **không được gửi trong authorize URL**. `code_challenge` có thể xuất hiện trong authorize URL vì nó là dẫn xuất một chiều; bí mật quan trọng là verifier. Authorization Server phải gắn code với challenge được gửi lúc cấp code và **thực thi** kiểm tra ở token endpoint.

### 5.2. Vì sao khuyến nghị S256 thay plain?

PKCE có method `plain`, theo đó challenge bằng đúng verifier. Nếu kẻ tấn công quan sát được authorization request, họ có luôn verifier và cơ chế bảo vệ bị suy yếu đáng kể. RFC 9700 khuyến nghị dùng method không lộ verifier trong authorization request; **S256** là method phổ biến và được hỗ trợ.

Không fallback âm thầm sang `plain` khi IdP từ chối S256. Với ứng dụng cần bảo mật, IdP phải có hỗ trợ PKCE đúng; nếu không, cần đánh giá nâng cấp/provider khác thay vì giảm mức bảo vệ.

### 5.3. Public client và confidential client

| Kiểu client | Có giữ được client secret an toàn? | PKCE nên dùng? |
|---|---|---|
| SPA thuần JavaScript, mobile/native (public) | Không, nếu secret nằm trong client bundle. | **Bắt buộc về mặt best practice**; authorization code + PKCE. |
| Backend WebFlux/BFF (confidential) | Có thể giữ secret ở server. | **Vẫn khuyến nghị** PKCE để chống code interception/injection; secret không thay PKCE. |
| Service-to-service client credentials | Không dùng browser authorization code. | PKCE không áp dụng cho client_credentials grant. |

Spring Security 6.5 hỗ trợ tự thêm PKCE cho public client nếu `client-authentication-method=none` (không có client secret), hoặc khi `ClientRegistration.clientSettings.requireProofKey=true`. Với **confidential OAuth2 Login**, có thể yêu cầu PKCE rõ ràng bằng `OAuth2AuthorizationRequestCustomizers.withPkce()`, như ví dụ dưới.

### 5.4. Pure Java 17: tự tính một PKCE S256 challenge

Ví dụ sau **chạy độc lập chỉ với JDK 17**, dùng test vector công khai từ RFC 7636; đây **không phải** cách bạn nên tự thay thế Spring Security PKCE implementation.

Tệp `PkceS256.java`:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Base64;

public final class PkceS256 {
    private PkceS256() {
    }

    public static String challenge(String verifier) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                .digest(verifier.getBytes(StandardCharsets.US_ASCII));

            return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(digest);
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException("SHA-256 unavailable", ex);
        }
    }

    public static void main(String[] args) {
        // RFC 7636 Appendix B: PUBLIC test vector, not a real secret.
        String verifier =
            "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk";

        System.out.println(challenge(verifier));
    }
}
~~~

Chạy:

~~~bash
javac PkceS256.java
java PkceS256
~~~

**Stdout chính xác**:

~~~text
E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM
~~~

Đây là một **test vector cố định để kiểm chứng công thức**, không được dùng verifier cố định này trong login thực. Khi triển khai thật, để Spring Security tạo verifier bằng nguồn ngẫu nhiên mật mã cho **mỗi lần đăng nhập** và lưu nó cùng authorization request.

### 5.5. Chuyện gì xảy ra khi kẻ tấn công lấy được code?

Nếu authorization code `K` bị rò rỉ từ callback URL hoặc nhật ký reverse proxy:

- **Không có PKCE:** attacker có thể thử đổi code, tùy public/confidential client authentication và các ràng buộc khác.
- **Có PKCE S256 đúng:** attacker biết K nhưng không có V; IdP từ chối token request do code_verifier không khớp.
- **Nếu XSS/server compromise làm lộ cả V:** PKCE không còn bảo đảm vì attacker có đủ dữ liệu.
- **Nếu IdP không thực thi PKCE hoặc cho downgrade:** client gửi challenge thôi chưa đủ; phải test IdP thực sự từ chối verifier thiếu/sai.

PKCE cũng không thay thế **token recipient validation** (`iss`/`aud`), TLS, session/cookie protection hay authorization theo nghiệp vụ.

## 6. Spring Security reactive tự quản lý request correlation ra sao?

Các thành phần tiêu biểu trong WebFlux OAuth2 Login:

| Thành phần | Vai trò |
|---|---|
| `OAuth2AuthorizationRequestRedirectWebFilter` | Nhận request bắt đầu login, tạo redirect đến IdP Authorization Endpoint. |
| `ServerOAuth2AuthorizationRequestResolver` | Tạo `OAuth2AuthorizationRequest` cho một client registration. |
| `DefaultServerOAuth2AuthorizationRequestResolver` | Resolver mặc định, nhận `/oauth2/authorization/{registrationId}` và tạo state/nonce, PKCE tùy client settings/customizer. |
| `ServerAuthorizationRequestRepository<OAuth2AuthorizationRequest>` | Lưu/tra request gốc từ lúc redirect đến khi callback. |
| `WebSessionOAuth2ServerAuthorizationRequestRepository` | Repository mặc định lưu request trong `WebSession`, giúp callback ràng buộc với browser session. |
| `OAuth2LoginAuthenticationWebFilter` | Xử lý callback authorization response, lấy request gốc và bắt đầu authentication. |
| `WebClientReactiveAuthorizationCodeTokenResponseClient` | Đổi code lấy token tại token endpoint, có code_verifier khi PKCE áp dụng. |
| `OidcAuthorizationCodeReactiveAuthenticationManager` | Xử lý OIDC authorization code login, xác minh các điều kiện ID Token có liên quan. |
| `ReactiveOidcIdTokenDecoderFactory` | Tạo decoder xác minh chữ ký ID Token theo cấu hình đăng ký client. |
| `ServerSecurityContextRepository` | Lưu Authentication đã xác minh cho login session, khác với repository lưu authorization request đang chờ. |

### 6.1. Vì sao lưu OAuth2AuthorizationRequest vào WebSession?

Trong lúc browser rời ứng dụng sang IdP, client cần nhớ **state gốc, PKCE verifier, nonce, redirect URI, registration ID và các attributes khác**. Khi callback trở về, repository truy lại transaction tương ứng từ browser's `WebSession`, xác minh state rồi tiếp tục trao đổi token.

**Không** tạo một singleton `Map<String, OAuth2AuthorizationRequest>` không giới hạn/không kiểm soát TTL để thay repo, vì dễ gây rò dữ liệu, replay, concurrency race, memory leak và lỗi khi chạy nhiều instance. Nếu custom repository phân tán qua Redis/database, cần bảo đảm:

- State đủ entropy, dữ liệu được bảo vệ khỏi đọc/sửa bởi tenant/browser khác.
- Mỗi transaction có TTL ngắn và được tiêu thụ **một lần** ở callback.
- Binding với browser/session và client/issuer được duy trì.
- Xử lý đồng thời nhiều tab (nhiều login attempts) rõ ràng; không âm thầm ghi đè transaction của tab khác.
- Session store có tính nhất quán và sticky/non-sticky load balancer được xử lý đúng.
- Không log `code_verifier`, nonce gốc, session cookie hay authorization code.

### 6.2. Không disable CSRF hoặc tự đăng nhập bằng callback controller

OAuth2 authorization callback được Spring Security OAuth2 login filter xử lý. Không nên viết controller:

~~~java
// PHẢN VÍ DỤ: không làm điều này.
@GetMapping("/login/oauth2/code/oidc")
public Mono<String> dangerous(@RequestParam String code) {
    // Chưa validate state/PKCE/nonce/issuer; không được tạo login.
    return Mono.just("logged in");
}
~~~

Đây chỉ là mẫu lỗi, không phải code có thể chạy thành login. Một controller tự đọc `code` rồi tạo Authentication từ query string là lỗ hổng; ủy quyền luồng callback cho framework/identity library đã kiểm thử.

### 6.3. PKCE tự động và PKCE cưỡng chế qua customizer

Spring Security 6.5 hỗ trợ public clients, và có API cưỡng chế PKCE trên authorization request của **confidential** client khi IdP hỗ trợ:

~~~java
DefaultServerOAuth2AuthorizationRequestResolver resolver =
    new DefaultServerOAuth2AuthorizationRequestResolver(
        clientRegistrationRepository);

resolver.setAuthorizationRequestCustomizer(
    OAuth2AuthorizationRequestCustomizers.withPkce());
~~~

Đây là **mảnh cấu hình**; bạn phải gắn resolver vào `http.oauth2Login(...)`. Spring Security thêm `code_challenge`/`code_challenge_method` và lưu `code_verifier` trong `OAuth2AuthorizationRequest.attributes` để dùng lại ở token request.

**Đừng viết customizer thay thế toàn bộ `additionalParameters`/`attributes` mà vô tình xóa `nonce`, PKCE metadata hoặc `registrationId`.** Nếu chỉ cần thêm `prompt=login`, hãy giữ nguyên các giá trị bảo mật đã có bằng mutation có kiểm soát.

## 7. Ví dụ ứng dụng Spring Boot WebFlux Java 17: OAuth2 Login + PKCE S256

Đây là ứng dụng **Java 17 / Spring Boot 3.5.16**, dùng dependency Spring Security do Boot quản lý. Phần khởi tạo và các test cho authorization request có thể chạy local; **đăng nhập end-to-end cần một IdP OIDC thật được cấu hình**. Không thể tuyên bố callback/token validation thành công chỉ vì Spring Boot đã startup trong khi chưa có provider.

### 7.1. Cấu trúc project

~~~text
reactive-oidc-login-security/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/example/ReactiveOidcLoginApp.java
    │   └── resources/application.yml
    └── test/
        └── java/example/AuthorizationRequestSecurityTest.java
~~~

Tệp `settings.gradle`:

~~~groovy
rootProject.name = 'reactive-oidc-login-security'
~~~

Tệp `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Dùng JDK 17+ và Gradle/Wrapper tương thích Spring Boot 3.5. `spring-boot-starter-oauth2-client` quan trọng: chỉ có starter security không đủ để khởi tạo OAuth2/OIDC Login. Không trộn thêm `spring-boot-starter-web` Servlet vào bài WebFlux này.

### 7.2. application.yml và các giá trị đăng ký IdP

Tệp `src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080

spring:
  security:
    oauth2:
      client:
        registration:
          oidc:
            provider: corporate-oidc
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: openid,profile,email
        provider:
          corporate-oidc:
            issuer-uri: ${OIDC_ISSUER_URI}
~~~

**Cần thay bằng environment variables thật**, ví dụ issuer là một URL **HTTPS** của OIDC provider do tổ chức sở hữu. Cú pháp placeholder của YAML sau khi bạn tạo file là `${OIDC_ISSUER_URI}` (bản trình bày dùng dấu gạch chéo escape ở nguồn văn bản để giữ nguyên template; khi chép vào YAML thực, **bỏ gạch chéo trước dấu $**). Các biến:

- `OIDC_CLIENT_ID`: Client ID được IdP cấp.
- `OIDC_CLIENT_SECRET`: Client secret của backend confidential client; lưu bằng secret manager/env, **không commit vào repository**.
- `OIDC_ISSUER_URI`: URI OIDC issuer, IdP cần cung cấp discovery metadata hợp lệ và HTTPS.
- `scope: openid,profile,email`: có `openid` để dùng OIDC ID Token và nonce; những scope khác theo nhu cầu.
- `redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"`: URI callback khớp endpoint mặc định của WebFlux OAuth2 Login và **phải đăng ký chính xác ở IdP**.

**Lưu ý về discovery:** Khi dùng `issuer-uri`, Spring Boot/Spring Security có thể truy vấn OIDC discovery metadata của IdP; ứng dụng chỉ chạy nếu issuer reachable và cấu hình nhất quán. Đây không phải ứng dụng giả lập IdP. Phép test offline mục 8 tự tạo registration trong memory nên **không kết nối** issuer URL.

### 7.3. Ứng dụng đầy đủ

Tệp `src/main/java/example/ReactiveOidcLoginApp.java`:

~~~java
package example;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.MediaType;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizationRequestCustomizers;
import org.springframework.security.oauth2.client.web.server.DefaultServerOAuth2AuthorizationRequestResolver;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
public class ReactiveOidcLoginApp {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveOidcLoginApp.class, args);
    }

    @Bean
    SecurityWebFilterChain security(
        ServerHttpSecurity http,
        ReactiveClientRegistrationRepository registrations) {

        var resolver =
            new DefaultServerOAuth2AuthorizationRequestResolver(
                registrations);

        // Thêm PKCE S256 cả cho backend confidential client.
        // Không tự sinh/ghi đè state hoặc nonce.
        resolver.setAuthorizationRequestCustomizer(
            OAuth2AuthorizationRequestCustomizers.withPkce());

        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/", "/error", "/login",
                    "/oauth2/authorization/**",
                    "/login/oauth2/code/**")
                .permitAll()
                .anyExchange().authenticated())
            .oauth2Login(oauth -> oauth
                .authorizationRequestResolver(resolver))
            .build();
    }

    @RestController
    static class Api {

        @GetMapping(value = "/", produces = MediaType.TEXT_HTML_VALUE)
        Mono<String> home() {
            return Mono.just(
                "<!doctype html><html lang=\"vi\"><body>" +
                "<h1>OIDC Login demo</h1>" +
                "<a href=\"/oauth2/authorization/oidc\">" +
                "Đăng nhập OIDC</a></body></html>");
        }

        @GetMapping("/me")
        Mono<Map<String, String>> me(ServerWebExchange exchange) {
            return exchange.getPrincipal()
                .map(principal -> Map.of(
                    "subject", principal.getName()));
        }
    }
}
~~~

**Những quyết định quan trọng:**

1. Đăng nhập bắt đầu ở `/oauth2/authorization/oidc` — đây là **`registrationId`** từ YAML, không phải tên issuer tùy ý.
2. `DefaultServerOAuth2AuthorizationRequestResolver` của Spring Security tạo authorization request và state. Có `scope=openid`, Spring Security OIDC hỗ trợ nonce theo authorization request.
3. `withPkce()` bảo đảm code challenge/verifier cho flow. Public clients có thể tự bật PKCE theo cấu hình framework, nhưng ví dụ backend dùng confidential client nên yêu cầu rõ ràng.
4. `oauth2Login(oauth -> oauth.authorizationRequestResolver(resolver))` **gắn resolver vào đúng OAuth2 Login DSL**. Chỉ tạo bean resolver rồi quên gắn có thể khiến app không dùng customizer.
5. Không tự thiết lập login session từ query `code/state`; OAuth2 Login filter và authentication manager mặc định thực hiện callback/token validation.
6. `/me` chỉ được gọi sau login; đọc principal từ Spring Security. Không in access token/refresh token/ID Token ra JSON.
7. Giữ CSRF protection mặc định của WebFlux. OAuth2 callback dạng GET được xử lý theo luồng OAuth2; với POST form của ứng dụng, CSRF vẫn có vai trò riêng.
8. Không cho phép return URL tùy ý sau login; nếu mở rộng redirect, phải validate target và chống open redirect.
9. Dòng `permitAll()` đối với callback/authorization URL chỉ nói về authorization matcher; **không bypass state, nonce hoặc PKCE** trong OAuth2 Login filters.
10. Đây là ví dụ server-side confidential client: browser không có quyền đọc secret hoặc code_verifier từ JavaScript.

### 7.4. Chạy với IdP OIDC thật

1. Đăng ký client **confidential**, authorization code flow, với callback chính xác `http://localhost:8080/login/oauth2/code/oidc` **chỉ cho môi trường dev local**. Trong production phải là HTTPS.
2. Bật PKCE S256 ở IdP; xác minh IdP **thực thi** challenge/verifier khi đổi code.
3. Cung cấp ba biến môi trường theo hướng dẫn của shell/IDE; không ghi secret vào git.
4. Chạy:

~~~bash
gradle bootRun
~~~

Hoặc `./gradlew bootRun` / `gradlew.bat bootRun` với Gradle Wrapper. Mở `http://localhost:8080/`, click **Đăng nhập OIDC**, sau khi IdP xác thực và redirect về callback, mở `http://localhost:8080/me`.

**Không có một stdout cố định cho login thật**: mỗi lần có state/nonce/verifier mới; user ID, redirect location và IdP metadata tùy environment. Trong network diagnostics cần thấy:

- Redirect đầu từ `/oauth2/authorization/oidc` chứa `response_type=code`, `client_id`, `state`, `nonce`, `code_challenge` và `code_challenge_method=S256`.
- Callback thành công về `/login/oauth2/code/oidc?code=...&state=...` trên **cùng browser session** đã bắt đầu login.
- Token request từ backend có `code_verifier` (kiểm tra bằng IdP test harness/telemetry an toàn; **không log raw verifier/token**).
- ID Token pass chữ ký/claim/nonce validation. Nếu thất bại, **không** tạo local authenticated session và phải có error handling an toàn.
- `/me` thành công chỉ khi login thực sự được xác minh.

Một provider có yêu cầu riêng về PKCE, claims, clock skew hay client authentication có thể khiến demo cần điều chỉnh theo tài liệu của IdP đó. Không tắt nonce/audience validation để “sửa cho login thành công”.

## 8. Kiểm thử offline authorization request bằng Reactor StepVerifier

Ta có thể kiểm tra việc **sinh state, PKCE challenge/verifier và nonce** mà không cần IdP, bằng cách tạo `ClientRegistration` trong memory rồi gọi `DefaultServerOAuth2AuthorizationRequestResolver` với `MockServerWebExchange`.

**Giới hạn được nêu rõ:** Test này chỉ xác minh **client tạo authorization request đúng**. Nó **không** chứng minh IdP thực thi PKCE, client từ chối callback state sai hoặc ID Token nonce sai. Những việc đó cần integration/security tests với IdP test harness hoặc test doubles tại đúng token/authentication layer.

Tệp `src/test/java/example/AuthorizationRequestSecurityTest.java`:

~~~java
package example;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Base64;

import org.junit.jupiter.api.Test;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.InMemoryReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizationRequestCustomizers;
import org.springframework.security.oauth2.client.web.server.DefaultServerOAuth2AuthorizationRequestResolver;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.core.endpoint.OAuth2AuthorizationRequest;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.*;

class AuthorizationRequestSecurityTest {

    private DefaultServerOAuth2AuthorizationRequestResolver resolver() {
        ClientRegistration reg = ClientRegistration
            .withRegistrationId("oidc")
            .clientId("offline-client")
            .clientSecret("offline-test-secret")
            .clientAuthenticationMethod(
                ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
            .authorizationGrantType(
                AuthorizationGrantType.AUTHORIZATION_CODE)
            .redirectUri("{baseUrl}/login/oauth2/code/{registrationId}")
            .scope("openid", "profile")
            .authorizationUri("https://idp.example.test/authorize")
            .tokenUri("https://idp.example.test/token")
            .jwkSetUri("https://idp.example.test/jwks")
            .clientName("Offline OIDC Test")
            .build();

        var repo = new InMemoryReactiveClientRegistrationRepository(reg);
        var resolver =
            new DefaultServerOAuth2AuthorizationRequestResolver(repo);

        resolver.setAuthorizationRequestCustomizer(
            OAuth2AuthorizationRequestCustomizers.withPkce());

        return resolver;
    }

    private MockServerWebExchange exchange() {
        return MockServerWebExchange.from(
            MockServerHttpRequest
                .get("/oauth2/authorization/oidc")
                .build());
    }

    private String sha256Url(String input) {
        try {
            byte[] sha256 = MessageDigest.getInstance("SHA-256")
                .digest(input.getBytes(StandardCharsets.US_ASCII));

            return Base64.getUrlEncoder().withoutPadding()
                .encodeToString(sha256);
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException(ex);
        }
    }

    @Test
    void createsStateNonceAndS256Challenge() {
        StepVerifier.create(resolver().resolve(exchange()))
            .assertNext(request -> {
                assertNotNull(request.getState());
                assertFalse(request.getState().isBlank());

                String verifier = request.getAttribute("code_verifier");
                assertNotNull(verifier);
                assertTrue(verifier.length() >= 43);
                assertTrue(verifier.length() <= 128);

                assertEquals("S256",
                    request.getAdditionalParameters().get(
                        "code_challenge_method"));

                assertEquals(sha256Url(verifier),
                    request.getAdditionalParameters().get(
                        "code_challenge"));

                assertTrue(request.getAdditionalParameters()
                    .containsKey("nonce"));
                assertNotNull(request.getAttribute("nonce"));

                String authorizationUrl =
                    request.getAuthorizationRequestUri();

                assertTrue(authorizationUrl.contains("state="));
                assertTrue(authorizationUrl.contains(
                    "code_challenge="));
                assertTrue(authorizationUrl.contains("nonce="));

                // Bí mật PKCE không được gửi trong authorize URL.
                assertFalse(authorizationUrl.contains(
                    "code_verifier="));
                assertFalse(authorizationUrl.contains(verifier));
            })
            .verifyComplete();
    }

    @Test
    void eachAuthorizationAttemptUsesDifferentState() {
        var resolver = resolver();

        Mono<OAuth2AuthorizationRequest> first =
            resolver.resolve(exchange());
        Mono<OAuth2AuthorizationRequest> second =
            resolver.resolve(exchange());

        StepVerifier.create(Mono.zip(first, second))
            .assertNext(pair -> {
                assertNotEquals(
                    pair.getT1().getState(),
                    pair.getT2().getState());

                assertNotEquals(
                    pair.getT1().getAttribute("code_verifier"),
                    pair.getT2().getAttribute("code_verifier"));

                assertNotEquals(
                    pair.getT1().getAttribute("nonce"),
                    pair.getT2().getAttribute("nonce"));
            })
            .verifyComplete();
    }

    @Test
    void doesNotResolveUnknownLoginPath() {
        var resolver = resolver();
        var unrelated = MockServerWebExchange.from(
            MockServerHttpRequest.get("/not-an-oauth-login").build());

        StepVerifier.create(resolver.resolve(unrelated))
            .verifyComplete();
    }
}
~~~

Chạy test offline từ thư mục project sau khi tải dependencies:

~~~bash
gradle test
~~~

Với Gradle Wrapper dùng `./gradlew test` hoặc `gradlew.bat test`. Kỳ vọng 3 test pass với Spring Security 6.5.x/Boot 3.5.x tương thích. Test không dùng `@SpringBootTest` và không cần môi trường `OIDC_ISSUER_URI`: tự tạo `ClientRegistration`. Cần thực sự chạy build để khẳng định dependency/toolchain của máy phù hợp.

### 8.1. Vì sao test nonce không so trực tiếp ID Token?

Trong offline test chưa có ID Token được ký hợp lệ từ IdP. Ta chỉ xác nhận **nonce được tạo và gắn vào authorization request**. Việc xác minh ID Token nonce cần chạy integration test với một fake IdP có chữ ký và JWKS hợp lệ, hoặc test authentication manager/ID token decoder riêng với mock response có kiểm soát.

Không tạo một JSON chứa `nonce` rồi tuyên bố “OIDC nonce validation passed” — vì còn phải kiểm tra chữ ký, issuer, audience, expiration và quy tắc nonce hashed của Spring.

### 8.2. Kiểm tra callback state sai như thế nào?

Một integration test có thể:

1. Khởi tạo `GET /oauth2/authorization/oidc` và giữ session cookie.
2. Lưu `state=S1` trong redirect đã nhận; không in giá trị thật vào log/ticket.
3. Gọi callback với `state=modified` và một `code` giả; mong **authentication thất bại** và **không** gọi token endpoint.
4. Gọi callback với đúng S1 nhưng **cookie session khác**; cũng phải từ chối.
5. Dùng lại S1 sau callback hợp lệ; phải từ chối replay theo thiết kế repository.
6. Kiểm tra status/redirect theo failure handler thật; không cứng hóa mọi lỗi là HTTP 401 hoặc 403 vì `oauth2Login` có thể redirect về login error page.

**Không thực hiện test sai state bằng cách tự viết callback controller** làm mất những check mặc định. Test nên đi qua filter chain và provider/test double phù hợp.

## 9. Những ràng buộc bảo vệ luồng login ngoài ba tham số

### 9.1. Redirect URI phải đăng ký và khớp chính xác

Authorization Server cần đăng ký các redirect URIs và đối chiếu **exact string matching** theo RFC 9700 (có ngoại lệ riêng cho native app localhost dynamic ports). Với WebFlux:

~~~text
Authorization start:
  /oauth2/authorization/oidc

Registered callback:
  https://app.example.test/login/oauth2/code/oidc
~~~

Không đăng ký pattern tùy tiện `https://app.example.test/*`, không chấp nhận callback từ host không sở hữu, không đưa `redirect_uri` lấy từ query của attacker vào token request. Tại IdP, tách URI localhost dev và HTTPS production thành entry chính xác.

Nếu có reverse proxy, cấu hình `Forwarded`/`X-Forwarded-*` phải tin cậy và được validate, vì Spring có thể expand `{baseUrl}` từ request/proxy data. Một proxy cho phép client tự điều khiển forwarded host/scheme có thể khiến redirect URI bị tạo sai hoặc mở lỗ hổng.

### 9.2. Bind với đúng issuer để chống IdP mix-up

Khi một ứng dụng hỗ trợ nhiều OAuth2/OIDC providers, attacker có thể tạo tình huống client **gửi authorization code từ IdP A đến token endpoint của IdP B**. Đây là **mix-up attack**.

Theo RFC 9700, client hỗ trợ nhiều Authorization Servers cần có đối sách mix-up, ví dụ:

- Bind authorization request với issuer/registration dự định trong transaction store.
- Xác minh `iss` trong authorization response theo RFC 9207 nếu provider hỗ trợ.
- Hoặc xác minh ID Token issuer ở đúng thời điểm theo OIDC/protocol; dùng callback URI khác nhau theo issuer khi cần.
- Không chọn token endpoint dựa vào một tham số `issuer=...` chưa được xác minh của callback.
- Test trường hợp callback từ registration A không được accept cho B, dù state trông hợp lệ.

Đừng mặc định **“đã có state”** thì tự miễn mọi mix-up risks. Ràng buộc request đến đúng issuer/token endpoint là điều kiện độc lập.

### 9.3. Không bỏ xác minh ID Token

Với OIDC login, phải xác minh:

1. JWS signature/JWKS từ IdP được đăng ký.
2. `iss` khớp issuer tin cậy.
3. `aud` chứa đúng client ID, `azp` theo OIDC nếu cần.
4. `exp`, `iat` và clock skew hợp lý.
5. `nonce` khớp authorization request, nếu nonce đã được gửi.
6. `sub` dùng làm identity ổn định theo issuer, không lấy email làm ID toàn cục mặc định.

Không để response `userinfo` hoặc claims từ access token tùy ý **ghi đè** identity đã được xác minh bằng ID Token. Với nhiều tenants/issuers, dùng khóa identity có issuer prefix.

### 9.4. Authorization code một lần và TTL ngắn

Authorization code phải có hạn dùng ngắn, gắn với client ID/redirect URI và chỉ dùng **một lần** tại token endpoint. Nếu code bị đổi hai lần, IdP phải từ chối lần sau và có thể revoke tokens liên quan theo policy. PKCE không làm code trở thành một bearer token dài hạn.

State/nonce/PKCE verifier cũng chỉ thuộc một login attempt. Nếu người dùng mở hai tab login đồng thời, có thể có hai transaction; phải test cách repository/session lưu chúng, không ghi đè state của tab khác một cách âm thầm.

### 9.5. Cookie session và login callback

Một OAuth2 Login WebFlux server-side thường lưu pending authorization request trong `WebSession`. Browser cần giữ đúng **session cookie** từ lúc bắt đầu authorization cho đến callback.

- Cookie session nên `Secure` và `HttpOnly` ở HTTPS.
- `SameSite=Lax` thường phù hợp với cross-site **top-level GET redirect** của authorization code flow, nhưng đừng coi đó là chính sách hợp với mọi response mode.
- OIDC `response_mode=form_post` sử dụng cross-site POST có thể bị SameSite chặn và cũng cần xét CSRF-specific handling; phải thiết kế lại flow/cookie policy, không đơn giản disable mọi CSRF.
- Nhiều instance cần shared session store hoặc affinity phù hợp; nếu callback rơi vào instance không có pending request, state validation sẽ thất bại.
- Login success nên có session-fixation protection và bảo vệ local session, không dùng ID phiên do attacker cố định.
- Redirect login session không đồng nghĩa mọi refresh token hoặc IdP session đã được bảo vệ/thu hồi.

### 9.6. HTTPS, Referrer-Policy và tránh lộ code

Callback URL có `code` và `state`; bảo vệ nó khỏi rò rỉ qua:

- Bắt buộc HTTPS/TLS ở production.
- Không log full query string trên reverse proxy, tracing hoặc analytics.
- Không nhúng third-party script/asset không đáng tin vào callback/success page khi URL còn chứa code.
- Dùng `Referrer-Policy` hạn chế referrer; chuyển người dùng sang URL sạch sau xử lý.
- Không redirect code/token sang URL động từ query.
- Không gửi access token, ID Token hoặc client secret qua fragment/query đến nơi không tin cậy.
- Giữ secret/JWKS keys đúng cấu hình và rotate theo chính sách; không bỏ validation vì clock skew hoặc lỗi JWKS nhất thời.

### 9.7. Consent, prompt, login_hint không phải bảo đảm an ninh

OIDC hỗ trợ những tham số UX như `prompt=login`, `prompt=consent`, `login_hint=...`, `max_age`. Chúng điều chỉnh hành vi IdP; không thay thế state, nonce, PKCE và issuer validation. Nếu yêu cầu reauthentication nhạy cảm, policy cần kiểm tra `auth_time`/`acr` hoặc session age sau login, không chỉ thêm query `prompt=login` rồi tin mọi token mới đều đạt mức assurance mong muốn.

## 10. Threat model: mỗi biện pháp chặn gì và không chặn gì?

| Đe dọa | State | OIDC nonce | PKCE S256 | Những ràng buộc khác bắt buộc |
|---|---|---|---|---|
| Callback giả mạo từ website khác (login CSRF) | **Chính yếu** nếu bind session đúng | Cung cấp bảo vệ theo OIDC khi validate đúng | Có ích khi IdP thực thi PKCE và session binding đúng | Cookie/session, one-time state |
| Authorization code bị đánh cắp | Không bảo vệ việc đổi code ở token endpoint | Không trực tiếp cho pure OAuth | **Chính yếu** | Client auth, TLS, code TTL |
| Code injection từ flow khác | Phát hiện callback không thuộc request | Có thể phát hiện ID Token swap ở OIDC | **Ràng buộc code với verifier** | IdP đúng, redirect URI đúng |
| ID Token replay/substitution | Không kiểm tra nội dung ID Token | **Chính yếu** | Không thay signature/claims validation | JWS, iss, aud, exp |
| Mix-up giữa hai IdP | Binding cần thiết nhưng **chưa đủ** | Có thể giúp theo OIDC | Không tự chọn đúng token endpoint | `iss`/registration binding, issuer response, callback strategy |
| Open redirect sau login | Không mặc nhiên | Không | Không | Validate post-login redirect target |
| XSS trên origin ứng dụng | Có thể bị đọc/lợi dụng tùy thiết kế | Có thể bị lộ nếu script kiểm soát flow | Verifier có thể bị lộ khi client storage bị compromise | CSP, output encoding, BFF/cookie policy |
| CSRF trên endpoint nghiệp vụ POST | Không thay thế CSRF filter app | Không | Không | CSRF token/Origin checking, SameSite |
| Stolen active session cookie | Không đủ | Không | Không | Secure/HttpOnly cookie, session revoke, MFA/step-up |

**Nhớ:** OAuth2 callback anti-CSRF (`state`/PKCE/nonce theo điều kiện) khác với CSRF protection cho các API thay đổi dữ liệu **sau khi user đã đăng nhập**. Không nên tắt `ServerHttpSecurity.csrf` toàn cục chỉ vì OAuth2 Login đã dùng state.

## 11. Sai lầm phổ biến

**Lỗi 1 — Gán `state="abc"` cho mọi lần login.** Attacker có thể dự đoán/replay, mất transaction binding. Dùng random state theo attempt, lưu ở repository đáng tin và consume một lần.

**Lỗi 2 — Dùng state do client query tự khai.** State phải được sinh và lưu ở client trusted server/BFF rồi đối chiếu callback, không coi query state là dữ liệu quyền hạn.

**Lỗi 3 — Coi `nonce` là bản sao của state.** State kiểm tra callback; nonce gắn ID Token với OIDC authentication request. Mỗi giá trị có nơi kiểm tra khác nhau.

**Lỗi 4 — Không validate ID Token vì “đã có PKCE”.** PKCE chỉ ràng buộc code/verifier; vẫn cần signature, iss, aud, exp và nonce validation.

**Lỗi 5 — Đưa `code_verifier` vào authorize URL.** Verifier là bí mật tạm thời; chỉ gửi đến token endpoint. Authorization endpoint nhận challenge.

**Lỗi 6 — Dùng PKCE `plain` hoặc verifier cố định.** S256 ngăn lộ verifier qua authorization request; mỗi attempt phải có random verifier mới.

**Lỗi 7 — Chỉ client gửi PKCE nhưng IdP không check.** PKCE an toàn khi authorization server **bind** challenge với code và từ chối verifier sai; cần kiểm thử provider.

**Lỗi 8 — Nghĩ confidential client secret đã thay PKCE.** Client secret xác thực ứng dụng, PKCE ràng buộc code với login attempt; dùng PKCE cả với backend khi hỗ trợ.

**Lỗi 9 — Tự tạo callback controller đọc code và phát local session.** Bypass state/nonce/PKCE và token validation. Dùng Spring OAuth2 Login filter.

**Lỗi 10 — Customizer xóa nonce hoặc PKCE attributes.** Phá security bindings; khi thêm prompt/custom parameter cần giữ metadata framework.

**Lỗi 11 — State hết hạn thì “cho qua nếu code đúng”.** Không có correlation state thì fail closed; không có fallback “skip state check”.

**Lỗi 12 — Lưu OAuth2AuthorizationRequest trong global Map không TTL.** Memory leak, cross-user mix-ups, replay và không hoạt động ổn định trên multi-instance. Dùng repository/session store có kiểm soát.

**Lỗi 13 — Cho redirect URI wildcard hoặc mở URL tùy ý.** Code có thể bị gửi sang origin không tin cậy. Đăng ký exact redirect URIs, tránh open redirects.

**Lỗi 14 — Chỉ kiểm tra state mà bỏ issuer binding.** Multi-IdP client có thể gặp mix-up; cần bind đúng issuer/registration và tuân RFC 9700/9207.

**Lỗi 15 — Nhầm access token với ID Token.** Access token để gọi resource server; ID Token chứng minh authentication cho client OIDC sau khi được xác minh. Không dùng access token làm login ID Token tùy ý.

**Lỗi 16 — Dùng email làm global user ID không xét issuer.** Email có thể đổi/chưa được verify/trùng giữa IdP. Dùng issuer + sub cho identity key.

**Lỗi 17 — Log raw authorize URL/callback query/PKCE verifier.** Có thể làm rò code, state, nonce và dữ liệu correlation; mask URL/query và secrets.

**Lỗi 18 — Tắt CSRF mọi POST vì đã bật oauth2Login.** Callback anti-CSRF không thay CSRF cho endpoint nghiệp vụ sau login.

**Lỗi 19 — Session cookie mất do SameSite/proxy.** Callback sẽ không load pending state. Debug cookie Domain/Path/Secure/SameSite, forwarded headers và session store trước khi bỏ validation.

**Lỗi 20 — Tin rằng test redirect 302 là test đăng nhập toàn diện.** Chỉ chứng minh client bắt đầu flow. Cần negative tests cho state, verifier, nonce, token claims và replay.

**Lỗi 21 — Hardcode client secret trong YAML commit.** Secret của confidential client phải ở secret manager/env; public client không có client secret đáng tin nếu bundle gửi cho người dùng.

**Lỗi 22 — Ép mọi lỗi callback thành 200/“logged in”.** OAuth2 authentication failure phải giữ trạng thái chưa xác thực; chuyển đến trang lỗi theo UX nhưng không tạo Authentication.

## 12. Checklist bảo mật trước khi triển khai

1. **Grant:** Dùng Authorization Code Flow; không dùng Implicit Grant hoặc Password Grant mới cho login.
2. **state:** Có random state theo từng attempt và bind với browser/session/authorization request?
3. **Callback:** Thiếu/sai/expired/replayed state bị từ chối; request đã dùng được remove?
4. **nonce:** OIDC scope `openid`, nonce theo attempt và được validate trong ID Token theo framework?
5. **PKCE:** Có `code_challenge_method=S256`, verifier ngẫu nhiên 43–128 ký tự; IdP từ chối thiếu/sai verifier?
6. **Verifier secrecy:** Không có code_verifier ở authorization URI, logs, client URL hoặc third-party analytics?
7. **Client type:** Public client không chứa static client secret; confidential backend dùng secret manager và PKCE khi hỗ trợ?
8. **Redirect URI:** URI đăng ký exact, dùng HTTPS production, không arbitrary port/host/path wildcards?
9. **Issuer:** `iss`/provider registration/binding được kiểm tra; multi-IdP có mix-up defense theo RFC 9700?
10. **ID Token:** JWS, JWKS, allowed algorithms, iss, aud, exp, iat, nonce và azp theo OIDC?
11. **Subject:** User identity gắn issuer + sub, không tin một email chưa được verify?
12. **One-time:** Code, state và pending request hết hạn/tiêu thụ một lần; replay không tạo session?
13. **Session:** WebSession store bền qua callback và nhiều instance, cookie Secure/HttpOnly/SameSite phù hợp?
14. **Cross-site mode:** response_mode=form_post có chính sách cookie/CSRF riêng, không vô tình mất session?
15. **Proxy:** {baseUrl} và forwarded headers chỉ lấy từ reverse proxy tin cậy?
16. **Open redirect:** Post-login success target được giới hạn vào allowlist/path nội bộ, không từ query tùy ý?
17. **CSRF:** Business POST sau login vẫn có CSRF/Origin/SameSite controls?
18. **Tokens:** Access/refresh/ID Tokens không được đưa vào body/log cho client không có quyền; lưu/revoke phù hợp?
19. **Observability:** Có audit sanitized cho error reason (state mismatch, PKCE invalid, invalid_nonce, issuer mismatch) mà không lộ secrets?
20. **Testing:** Có offline resolver tests và end-to-end IdP tests (success + negative) thực sự chạy trong CI/staging?
21. **Version:** Đối chiếu API Spring Security thực tế, đổi version cần regression tests cho OAuth2 Login filters?
22. **Browser:** Test ở Chrome/Firefox/Safari và trên mobile app khi có app-link/redirect đặc biệt?
23. **Time:** Đồng hồ app/IdP được đồng bộ NTP; clock skew policy không mở quá rộng?
24. **Failure mode:** IdP lỗi/discovery mất kết nối dẫn đến fail closed, không fallback sang việc nhận token chưa verify?

## 13. Câu hỏi tự kiểm tra

**1.** `state` và `nonce` đều là random, có thể chỉ giữ một không?

**Đáp án:** Không nên tùy tiện bỏ. State là correlation của OAuth2 authorization response với login request/browser; nonce là ràng buộc với OIDC ID Token. RFC 9700 công nhận các tương tác bảo mật giữa chúng trong điều kiện cụ thể, nhưng framework mặc định đã thiết kế cả hai cho defense in depth.

**2.** Attacker chụp được authorization code nhưng không có PKCE verifier. Họ có thể tự đổi code không?

**Đáp án:** Authorization Server có PKCE S256 đúng phải từ chối token request thiếu/sai verifier. Điều này không thay thế bảo mật token sau khi cấp.

**3.** `code_challenge` được gửi tới đâu, và `code_verifier` tới đâu?

**Đáp án:** Challenge gửi qua **authorization request**; verifier chỉ gửi qua **token request** tới IdP, không đưa vào browser redirect URL.

**4.** Vì sao cần kiểm tra `iss` và `aud` của ID Token dù nonce đúng?

**Đáp án:** Nonce chỉ ràng buộc giao dịch; issuer/audience mới giúp chứng minh token do IdP được phép cấp cho đúng client. Chữ ký và thời hạn cũng bắt buộc.

**5.** `redirect_uri` có thể đăng ký `https://app.example.test/*` để tiện triển khai không?

**Đáp án:** Không theo OAuth2 Security BCP. IdP phải exact match redirect URIs (trừ ngoại lệ native localhost ports); URL wildcard/open redirect có thể làm rò code/token.

**6.** `WebSessionOAuth2ServerAuthorizationRequestRepository` khác với `ServerSecurityContextRepository` thế nào?

**Đáp án:** Repository thứ nhất giữ authorization request đang chờ callback (state/PKCE/nonce), repository thứ hai lưu Authentication đã được xác minh cho login session. Hai loại state và vòng đời khác nhau.

**7.** WebFlux `oauth2Login` sử dụng `HttpSessionOAuth2AuthorizationRequestRepository` của Servlet không?

**Đáp án:** Không. WebFlux dùng repository reactive như `WebSessionOAuth2ServerAuthorizationRequestRepository`.

**8.** Nếu app có hai IdP và callback code từ A bị gửi đến token endpoint B, đã có state thì chắc chắn an toàn?

**Đáp án:** Không. Cần chống IdP mix-up bằng issuer/registration binding, response issuer theo RFC 9207 hoặc chiến lược distinct redirect URIs phù hợp.

**9.** Test StepVerifier mục 8 chứng minh điều gì và chưa chứng minh điều gì?

**Đáp án:** Nó chứng minh resolver sinh state/nonce/challenge/verifier theo từng attempt và không lộ verifier ở authorize URL. Nó chưa chứng minh callback/session handling, token endpoint PKCE enforcement hoặc ID Token validation; các phần đó cần integration tests.

**10.** OIDC ID Token có `nonce` đúng nhưng chữ ký sai, nên chấp nhận login không?

**Đáp án:** Không. Phải xác minh chữ ký, issuer, audience, expiration và các claims khác trước khi tạo Authentication.

**11.** Callback mất session cookie nên state không tìm được, có nên cho qua nếu code còn dùng được?

**Đáp án:** Không. Đây là tình huống cần fail closed và điều tra cookie SameSite/Secure/Path, proxy/session persistence; không bypass anti-CSRF.

**12.** Vì sao public SPA không được chứa client secret trong bundle?

**Đáp án:** Bất kỳ người dùng nào cũng có thể xem mã/bundle. SPA không có kênh bảo mật đáng tin cho client secret; dùng Authorization Code + PKCE hoặc BFF để giữ secrets/tokens ở server.

## Tài liệu chính thức

- Spring Security 6.5 — Reactive OAuth2 Authorization Grant Support (PKCE, authorization request resolver, WebSession repository): https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/client/authorization-grants.html
- Spring Security 6.5 — OAuth2 WebFlux & OIDC login: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/index.html
- Spring Security 6.5 — OAuth2 Login advanced settings: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/login/advanced.html
- Spring Security — `OAuth2AuthorizationRequestCustomizers.withPkce()`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/web/OAuth2AuthorizationRequestCustomizers.html
- RFC 7636 — PKCE, S256, public test vector: https://www.rfc-editor.org/rfc/rfc7636.html
- RFC 9700 (January 2025) — OAuth 2.0 Security Best Current Practice: https://www.rfc-editor.org/rfc/rfc9700.html
- RFC 9207 — Authorization Server Issuer Identification in Authorization Response: https://www.rfc-editor.org/rfc/rfc9207.html
- OpenID Connect Core 1.0 — nonce / ID Token / code flow: https://openid.net/specs/openid-connect-core-1_0.html
- OWASP — OAuth2 Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html
