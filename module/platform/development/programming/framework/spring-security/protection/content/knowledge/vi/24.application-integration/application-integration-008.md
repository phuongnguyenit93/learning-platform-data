# Phân biệt CSRF token với state, nonce và PKCE trong OAuth/OIDC

## Mục tiêu học tập

Bài học thuộc chương **Tích hợp ứng dụng** của module **SPRING_SECURITY_HTTP_PROTECTION**. Sau khi hoàn thành, người học có thể:

- Mô tả chính xác **bốn giá trị dễ bị nhầm lẫn**: Spring Security CSRF token, OAuth 2.0 `state`, OIDC `nonce` và PKCE `code_verifier`/`code_challenge`.
- Xác định **chủ thể sinh**, **nơi lưu**, **nơi gửi**, **bên kiểm tra**, **thời điểm tiêu thụ** và **mối đe dọa bị chặn** bởi từng giá trị.
- Phân tích login CSRF, authorization response injection, authorization code interception, code substitution, ID token replay và request forgery trên phiên browser; chỉ ra vì sao những tấn công đó không giống nhau.
- Theo dõi một **Authorization Code + OIDC + PKCE** flow từ redirect đi IdP đến callback, token exchange, kiểm ID token và thiết lập session ứng dụng.
- Giải thích tương tác giữa **SameSite=Lax/Strict/None**, top-level GET callback, `form_post` cross-site POST, browser cookie và các repository lưu authorization request của Spring Security.
- Cấu hình và kiểm thử riêng phần **`oauth2Login` + authorization request repository** với phần **`csrf` + CsrfTokenRepository** ở cả **Servlet/Spring MVC** và **Reactive/WebFlux**.
- Chỉ ra lúc nào tiêu chuẩn OAuth Security Best Current Practice cho phép dùng **PKCE có ràng buộc đúng** làm cơ chế chống CSRF cho authorization flow, mà không kết luận sai rằng PKCE luôn thay thế `state` hoặc CSRF token của mọi form.
- Phân biệt các cơ chế trên với **authorization code, ID token, access token, refresh token, session ID** và quyền API.
- Viết ma trận kiểm thử **đúng/sai/hết hạn/từ phiên khác/replay**, tách test helper của Spring với test IdP và browser thực.
- Chẩn đoán `invalid_state_parameter`, `authorization_request_not_found`, `invalid_nonce`, `invalid_grant`, `403 CSRF`, lỗi SameSite, redirect URI và proxy mà không vô hiệu hóa lớp phòng vệ.

## 1. Vấn đề: bốn giá trị “token” ở ba ranh giới khác nhau

Giả sử ứng dụng Spring tại `https://app.example.com` dùng OpenID Connect để đăng nhập qua `https://login.identity.example`. Sau khi login thành công, người dùng sử dụng web app để sửa địa chỉ giao hàng. Một SPA hoặc worker cũng có thể gọi API riêng.

Trong một phiên có thể cùng tồn tại:

~~~text
state          = giá trị RP gửi qua authorization redirect,
                 nhận lại ở authorization response
nonce          = giá trị OIDC authentication request,
                 đối chiếu với claim trong ID token
code_verifier  = bí mật PKCE được client giữ,
                 gửi khi đổi authorization code lấy token
_csrf          = token chống giả mạo của request POST nghiệp vụ
JSESSIONID     = cookie định danh phiên browser tại RP
~~~

**Những giá trị này không tương đương, không gửi trên cùng request và không có vòng đời giống nhau.**

Một người dùng có thể:

1. Chạy login hoàn toàn hợp lệ với state/nonce/PKCE đúng.
2. Nhận một **session cookie** từ RP.
3. Truy cập website khác; website ấy khiến browser tự gửi POST thay đổi dữ liệu kèm session cookie.
4. Nếu RP tắt CSRF trên POST nghiệp vụ, thao tác có thể xảy ra dù bước OAuth/OIDC trước đó an toàn tuyệt đối.

Ngược lại, nếu `_csrf` trên mọi form của RP hoạt động tốt nhưng **OAuth callback bỏ kiểm state/nonce/PKCE**, attacker có thể tìm cách tiêm response login hoặc lợi dụng authorization code từ flow khác. **Một token đúng ở một ranh giới không tự bảo vệ ranh giới còn lại.**

### 1.1. Ba ranh giới cần ghi nhớ

~~~mermaid
flowchart LR
    subgraph L1["Ranh giới A: Browser ↔ RP, sau login"]
      B[Browser session cookie] --> R[Spring web POST]
      T[CSRF token đã cấp] --> R
    end
    subgraph L2["Ranh giới B: RP ↔ IdP qua redirect"]
      S[OAuth state] --> C[Authorization callback]
      N[OIDC nonce] --> I[ID token verification]
    end
    subgraph L3["Ranh giới C: Client ↔ Token Endpoint"]
      P[PKCE code verifier] --> X[Authorization code exchange]
    end
~~~

- **A:** “POST này có phải request được trang RP hợp lệ chủ động phát ra trong phiên browser không?”
- **B:** “Authorization response/ID token này thuộc **login flow** RP đã bắt đầu và thuộc đúng IdP/client/user context không?”
- **C:** “Bên đang đổi **authorization code** có giữ verifier của đúng authorization request đã tạo challenge không?”

Các câu hỏi liên quan nhau, nhưng **không thể trả lời bằng một biến chung `token`**.

### 1.2. Ví dụ những nhầm lẫn nguy hiểm

| Nhận định sai | Vì sao sai | Cách hiểu đúng |
|---|---|---|
| “Đăng nhập OIDC đã có state nên khỏi cần CSRF token.” | State chỉ liên kết authorization response với login request. | Cookie-authenticated POST sau login vẫn phải chống CSRF. |
| “Đã có Spring `_csrf` thì callback OAuth không cần state.” | CSRF token của form không tự kiểm code/state trên callback GET. | Callback cần correlation/protocol validation. |
| “Nonce là một CSRF token khác.” | Nonce nằm trong OIDC ID token theo flow và chống nhầm/replay ID token. | Không dùng nonce làm token của form POST. |
| “PKCE là CSRF token trong URL.” | PKCE tạo ràng buộc **code ↔ verifier** và gửi verifier tới token endpoint. | Không dùng verifier làm hidden field hay query callback. |
| “JWT ID token đã ký đúng nghĩa là response OAuth đúng phiên.” | Chữ ký không tự chứng minh response thuộc request hiện tại. | Kiểm issuer/audience/time/nonce và callback correlation. |
| “`SameSite=Strict` thay mọi token.” | Cookie policy chỉ quyết định browser tự gửi cookie theo ngữ cảnh. | Vẫn cần CSRF và OAuth/OIDC protocol checks. |
| “CORS khóa IdP redirect nên cần mở `*`.” | Redirect navigation không cần browser CORS. | Kiểm callback URI, cookie và protocol. |
| “PKCE luôn thay `state` ở mọi client.” | Theo BCP, điều đó có điều kiện nghiêm ngặt về PKCE support và request binding. | Chọn theo chuẩn/client/issuer và giữ các checks khác. |

## 2. Bảng phân biệt đầy đủ: ai tạo, ai giữ, ai kiểm?

| Cơ chế | Giá trị phát sinh ở đâu? | Vị trí lưu/di chuyển | Bên kiểm | Chặn loại tấn công chính | Tuổi thọ điển hình |
|---|---|---|---|---|---|
| **Spring CSRF token** | RP/Spring Security, qua `CsrfTokenRepository` | Expected token ở repository/session/cookie theo policy; submitted token trong field/header của unsafe request | `CsrfFilter`/`CsrfWebFilter` tại RP | Cross-site request forgery khi browser tự gửi session cookie | Theo repository/session/token lifecycle, có thể luân phiên |
| **OAuth `state`** | OAuth client/RP | Lưu expected authorization request có ràng buộc; đi qua authorize redirect rồi callback | OAuth client/RP tại callback | Login CSRF, response injection, trộn luồng authorize | Theo **một authorization transaction**, entropy cao, one-time |
| **OIDC `nonce`** | OIDC client/RP | Gửi trong OIDC auth request; ID token mang claim `nonce`; expected nonce được client nhớ | OIDC client/RP khi validate ID token | Ràng buộc ID token với authentication request, giảm replay/token substitution | Theo một authentication request/ID token validation |
| **PKCE `code_verifier`** | OAuth client | Giữ bí mật ở client; gửi **token endpoint**, không gửi tới authorize endpoint | Authorization Server tại token endpoint | Code interception/substitution; có thể hỗ trợ chống authorization CSRF theo điều kiện BCP | Theo một code flow; dùng một lần |
| **PKCE `code_challenge`** | Client dẫn xuất từ verifier | Gửi trong authorization request, AS gắn với code | Authorization Server lúc đổi code | Cùng cơ chế PKCE, không phải secret để nhận diện user | Cùng một authorization code transaction |

### 2.1. Không đánh đồng “giá trị ngẫu nhiên” với “bí mật”

- `state` thường cần **khó đoán** và **được ràng buộc đúng client/browser**, nhưng có thể xuất hiện trong URL authorize/callback; không thể xem state là client secret.
- `nonce` được gửi tới IdP và có thể thấy trong request; giá trị kỳ vọng phải được liên kết đúng login transaction.
- `code_verifier` cần được client giữ bí mật cho đến token exchange. `code_challenge` là dẫn xuất được gửi công khai, thường qua S256.
- CSRF token có thể được render trong HTML hoặc header JavaScript hợp lệ. Nó không phải password hay access token; khả năng chống giả mạo đến từ việc attacker cross-site **không có quyền đọc token đúng ngữ cảnh**.
- Session ID là credential; **không đưa session ID làm CSRF token** hoặc OAuth state theo cách trực tiếp.

### 2.2. Request nào thực sự mang giá trị nào?

| Giai đoạn | HTTP request | Dữ liệu liên quan |
|---|---|---|
| Bắt đầu login | Browser → RP: `GET /oauth2/authorization/corporate` | RP tạo authorization request và expected `state`; OIDC nonce/PKCE khi cấu hình |
| Sang IdP | Browser → IdP: top-level GET authorize | `client_id`, `redirect_uri`, `state`, `scope=openid`, `nonce`, `code_challenge` |
| Callback | Browser → RP: GET `/login/oauth2/code/corporate?code=...&state=...` | `code` + `state` + cookie RP nếu browser policy cho phép |
| Đổi code | RP backend → IdP token endpoint | `grant_type=authorization_code`, `code`, `redirect_uri`, `code_verifier`, client auth nếu cần |
| Token response | IdP → RP backend | ID token + access token (refresh token nếu được cấp) |
| ID token check | RP | `nonce` claim đối chiếu expected, chữ ký/issuer/audience/expiry và checks khác |
| RP gửi trang sau login | RP → Browser | Session cookie, HTML có thể chứa CSRF token/form |
| Ghi dữ liệu | Browser → RP: POST/PUT/PATCH/DELETE | Session cookie + submitted `_csrf`/`X-CSRF-TOKEN` |
| M2M API | Worker → Resource Server | `Authorization: Bearer` access token, không phải `state`/`nonce`/`_csrf` |

## 3. Tình huống A — CSRF trên POST nghiệp vụ sau login

### 3.1. Tấn công cần ambient credential

Alice đã đăng nhập RP. Browser lưu:

~~~http
Set-Cookie: JSESSIONID=opaque-session; Secure; HttpOnly; SameSite=Lax; Path=/
~~~

Một trang ngoài cố khiến browser gửi:

~~~http
POST /account/email HTTP/1.1
Host: app.example.com
Cookie: JSESSIONID=alice-session
Content-Type: application/x-www-form-urlencoded

email=attacker-controlled@example.invalid
~~~

Tùy chính sách SameSite/ngữ cảnh cross-site/cross-origin, browser có thể gửi cookie hoặc không; **SameSite=Lax giảm nhiều tình huống nhưng không chứng minh CSRF không còn** (ví dụ same-site khác origin và thay đổi policy/method/path).

Nếu server xác thực qua cookie và chấp nhận unsafe POST **không kiểm token**, attacker có thể tạo thay đổi dưới principal Alice khi browser tự gửi credential.

### 3.2. CSRF token được đối chiếu tại RP

Browser tải form hợp lệ từ RP:

~~~html
<form method="post" action="/account/email">
  <label>Email <input name="email" type="email"></label>
  <input type="hidden"
         th:name="${_csrf.parameterName}"
         th:value="${_csrf.token}">
  <button type="submit">Lưu</button>
</form>
~~~

Khi POST, `CsrfFilter` hoặc `CsrfWebFilter` so submitted token với expected token qua repository/handler. Request thiếu/sai token bị từ chối trước khi controller thực thi thay đổi, thường `403`.

**Điều cần nhớ:** Giá trị `_csrf` được cấp cho ứng dụng/session/browser request. Nó không đến từ authorization code, không cần IdP cấp, không phải claim của ID token.

### 3.3. OAuth state không giúp kiểm POST này

State của phiên OAuth login trước đó đã được tiêu thụ khi callback, không được gửi trong form đổi email. Kể cả bạn lưu một state cũ còn tồn tại, nó cũng không tự gắn với POST mới và không thay repository CSRF của Spring.

Ở endpoint Browser/BFF dùng cookie, **tiếp tục bật CSRF sau OIDC login**. Nếu Resource Server API thật sự chỉ nhận Bearer do client chủ động đặt, đánh giá CSRF theo credential contract khác; không kết luận từ việc API có JSON hay JWT.

## 4. Tình huống B — Login CSRF và authorization response injection

### 4.1. Khác “POST chỉnh dữ liệu” ở đâu?

Attacker muốn victim login vào RP **bằng account của attacker** hoặc đưa **authorization code/response của một login transaction khác** vào browser victim. Khi user tiếp tục làm việc, dữ liệu có thể bị ghi dưới tài khoản nhầm, hoặc attacker có thể lợi dụng session mix-up/identity confusion.

~~~mermaid
sequenceDiagram
    actor A as Attacker
    participant IA as IdP
    actor V as Victim Browser
    participant RP as Spring Relying Party

    A->>IA: Tạo authorization response cho flow A
    IA-->>A: code_A, state_A theo giao thức
    A->>V: Dụ mở callback chứa code_A/state_A
    V->>RP: GET callback + cookie của victim V
    RP->>RP: Tìm expected authorization request của V
    alt State/correlation không thuộc V
        RP-->>V: Từ chối, không tạo login session
    else RP bỏ correlation kiểm chứng
        RP->>IA: Có thể đổi code sai flow
        RP-->>V: Nguy cơ login/account confusion
    end
~~~

Một attacker không cần đọc cookie victim để thử tiêm authorization response. Vì vậy callback phải được liên kết với **request do cùng client/browser đã khởi tạo**.

### 4.2. State được tạo và lưu thế nào?

Khi bắt đầu login, RP tạo `state` entropy cao rồi giữ **expected authorization request** trong session hoặc repository có ràng buộc tương đương:

~~~text
Session của browser A:
  expected state: a9...random
  registrationId: corporate
  expected redirect URI: https://app.example.com/login/oauth2/code/corporate

Session của browser B:
  expected state: b7...random
  registrationId: corporate

Callback có state=a9... nhưng cookie session B
  -> không tìm đúng expected request
  -> fail closed, không login.
~~~

Kiểm state bằng cách **so với query parameter khác do cùng request cung cấp** là vô nghĩa. Không lấy state attacker gửi làm khóa duy nhất để lấy bất kỳ expected request trong kho chung rồi tin rằng nó thuộc browser hiện tại.

### 4.3. Vì sao state có thể xuất hiện trong URL mà vẫn hữu ích?

`state` **không phải bí mật tuyệt đối** giống client secret; nó là giá trị khó đoán, liên kết với request đã phát. Các lớp bảo vệ quan trọng gồm:

- Entropy tốt/không dự đoán được.
- Liên kết với correct browser session, `ClientRegistration`, issuer/redirect URI.
- TTL ngắn, xử lý một lần/replay.
- Không dùng lại state giữa nhiều login flows.
- Không để attacker kiểm soát repository hoặc override expected request.
- Không tùy ý log raw state/code cùng cookie; tránh thông tin correlation rò rỉ không cần thiết.

### 4.4. State không tự xác minh ID token

Callback state đúng chứng minh response khớp expected authorization request, **chưa chứng minh** ID token có chữ ký hợp lệ, đúng issuer, audience và nonce. Các bước xác minh giao thức khác vẫn phải diễn ra.

## 5. Tình huống C — OIDC ID token replay/substitution và nonce

### 5.1. ID token có mục tiêu khác authorization response

OIDC ID token là JWT chứa claims về authentication event và subject. RP phải kiểm hợp đồng ID token, bao gồm (tùy flow/claims):

~~~json
{
  "iss": "https://login.identity.example",
  "sub": "user-42",
  "aud": "spring-web-client",
  "exp": 1810000000,
  "iat": 1809999400,
  "nonce": "EXPECTED_NONCE_FROM_REQUEST"
}
~~~

Giá trị thời gian/issuer chỉ là fixture minh họa, **không phải ID token có chữ ký thật**. RP không được tin một JSON tự decode từ base64 mà chưa xác minh JWS/issuer/audience/time.

### 5.2. Nonce liên kết token với OIDC authentication request

Trong login, client tạo nonce rồi gửi ở authorization request, và lưu expected nonce trong correlation context. Nếu token response có `nonce` không đúng expected value, RP phải từ chối theo OIDC flow policy.

~~~text
Browser session S khởi tạo login:
  expected nonce = N1

IdP phát ID token:
  nonce = N2

N1 != N2
  -> không tạo authenticated session,
     dù token có chữ ký hợp lệ và issuer đúng.
~~~

Nonce giảm nguy cơ token replay/substitution giữa các authentication requests. **Nonce không chứng minh client được phép đổi authorization code**, đó là vai trò PKCE/client authentication; nó cũng không bảo vệ POST nghiệp vụ sau login.

### 5.3. Khi nào nonce bắt buộc?

OIDC Core yêu cầu nonce trong một số flow như implicit/hybrid; với Authorization Code flow nonce có điều kiện theo profile/khuyến nghị và **nếu client gửi nonce, phải kiểm claim token tương ứng**. Không khẳng định mọi OAuth2 Authorization Code request đều có `nonce`: nếu không có `openid`, đó có thể không phải OIDC.

Trong Spring Security, cần xem client registration/flow/phiên bản và xác minh thực tế OIDC nonce được tạo/gửi/đối chiếu như mong đợi. Đừng tự thay ID token validator bằng decoder chỉ kiểm JWT signature.

### 5.4. Issuer+subject và account linking

Hai IdP có thể phát `sub="42"` cho hai người khác nhau. Nonce không tự ngăn **account misbinding** nếu ứng dụng map user chỉ bằng `sub`.

Với multi-provider federation, identity key thường cần cặp **`iss + sub`** và một quy trình account linking được kiểm soát. Không map trực tiếp role admin từ email hoặc claim không được xác minh theo hợp đồng IdP.

## 6. Tình huống D — Authorization code interception và PKCE

### 6.1. PKCE chặn gì?

Trong Authorization Code flow, IdP gửi **authorization code** qua browser redirect. Đặc biệt ở public/native clients, code có thể bị lộ qua redirect handler, URI scheme interception, logs hoặc môi trường độc hại.

Nếu authorization code bị attacker lấy được, PKCE yêu cầu bên đổi code tại token endpoint phải chứng minh có **`code_verifier` gắn với authorization request**. Attacker chỉ có code nhưng không có verifier tương ứng sẽ không đổi được code lấy token, nếu Authorization Server triển khai/ép PKCE đúng.

~~~mermaid
sequenceDiagram
    participant C as OAuth Client/RP
    participant B as Browser
    participant AS as Authorization Server
    participant A as Attacker

    C->>C: Tạo code_verifier V, code_challenge C = S256(V)
    C->>B: Redirect authorize với state S và challenge C
    B->>AS: GET /authorize?...code_challenge=C
    AS->>AS: Lưu challenge C cho authorization code K
    AS-->>B: 302 callback?code=K&state=S
    B->>C: GET callback với K, S
    A-->>A: Có thể biết code K qua một kênh bị lộ
    A->>AS: POST token: code=K, verifier=V_attacker
    AS-->>A: invalid_grant hoặc lỗi PKCE
    C->>AS: POST token: code=K, verifier=V
    AS->>AS: S256(V) khớp C, kiểm code/client/redirect
    AS-->>C: Access token/ID token theo flow
~~~

Sơ đồ minh họa **tấn công chỉ có code**, không mặc định attacker kiểm soát client session hoặc chiếm được cả verifier. Nếu client làm lộ **cả authorization code và verifier**, PKCE không còn đủ chống đổi code; cần bảo vệ storage/transport/trust boundary khác.

### 6.2. Hai giá trị PKCE không thể hoán đổi

Công thức được dùng phổ biến:

\[
\operatorname{code\_challenge}
= \operatorname{BASE64URL\_NO\_PAD}(
  \operatorname{SHA256}(
    \operatorname{ASCII}(\operatorname{code\_verifier})
  )
)
\]

Trong authorization request:

~~~http
GET /authorize?response_type=code&client_id=web-rp&redirect_uri=https%3A%2F%2Fapp.example.com%2Flogin%2Foauth2%2Fcode%2Fcorporate&state=S&code_challenge=CHALLENGE&code_challenge_method=S256 HTTP/1.1
Host: login.identity.example
~~~

Trong token request:

~~~http
POST /token HTTP/1.1
Host: login.identity.example
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&code=K&redirect_uri=https%3A%2F%2Fapp.example.com%2Flogin%2Foauth2%2Fcode%2Fcorporate&code_verifier=ORIGINAL_VERIFIER
~~~

- `code_challenge` không phải secret và xuất hiện ở authorization endpoint.
- `code_verifier` **không gửi đến authorization endpoint**; client giữ đến token endpoint.
- Sử dụng `S256` thay `plain` khi được hỗ trợ; với các security profiles hiện đại nên yêu cầu S256.
- Authorization Server phải kiểm code/client/redirect URI và kiểm verifier thực sự; không chấp nhận thiếu verifier khi challenge đã được gửi.
- Một authorization code nên là **one-time use, short-lived**; PKCE không làm code trở thành token dùng đi dùng lại.

### 6.3. Tạo verifier bằng entropy mạnh

Ví dụ Java **minh họa thuật toán**, không cần tự dùng nếu Spring OAuth2 Client đã cung cấp PKCE:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Base64;

final class PkceUtility {

    private static final SecureRandom RANDOM = new SecureRandom();

    static String newVerifier() {
        byte[] random = new byte[32]; // 256-bit entropy
        RANDOM.nextBytes(random);
        return Base64.getUrlEncoder()
            .withoutPadding()
            .encodeToString(random);
    }

    static String s256Challenge(String verifier) throws Exception {
        byte[] bytes = verifier.getBytes(StandardCharsets.US_ASCII);
        byte[] digest =
            MessageDigest.getInstance("SHA-256").digest(bytes);
        return Base64.getUrlEncoder()
            .withoutPadding()
            .encodeToString(digest);
    }
}
~~~

`newVerifier()` tạo một chuỗi Base64URL 43 ký tự từ 32 bytes ngẫu nhiên, nằm trong độ dài verifier được RFC 7636 cho phép. Không dùng timestamp, username, session ID hoặc chuỗi đoán được làm verifier. Bản code trên **không quản lý storage/lifetime**; client còn phải lưu verifier tương ứng với đúng authorization transaction.

### 6.4. Vì sao mã client không nên tự dựng mọi tham số?

Một implementation tự viết thường mắc lỗi:

- Tạo verifier/challenge nhưng không lưu verifier đúng flow;
- Ghi verifier vào URL redirect hoặc log;
- Dùng cùng verifier cho mọi lần login;
- Không kiểm IdP thực sự áp PKCE mà vẫn tưởng đã được bảo vệ;
- Nhận authorization code nhưng không ràng buộc với client/redirect URI;
- Tạo callback handler riêng làm mất state validation hoặc OIDC checks;
- Race giữa các tab khiến verifier của flow A dùng cho code B.

Ưu tiên **Spring Security OAuth2 Client** hoặc SDK OIDC đã kiểm thử tương thích. Chỉ tùy biến khi có yêu cầu cụ thể và phải test các negative cases thật với Authorization Server.

## 7. Nuance quan trọng: PKCE có thể thay OAuth state trong một số điều kiện, không phải mọi CSRF

### 7.1. Tránh hai khẳng định cực đoan

Hai câu sau đều không đủ chính xác:

- “PKCE **không bao giờ** chống CSRF.” Sai vì PKCE gắn authorization response/code với verifier của flow hiện tại, và **OAuth 2.0 Security Best Current Practice (RFC 9700)** ghi nhận PKCE có thể đóng vai trò cơ chế CSRF cho authorization flow khi client **bảo đảm** Authorization Server hỗ trợ và áp PKCE đúng.
- “Đã bật PKCE thì **không bao giờ** cần `state` hay `_csrf`.” Sai vì khả năng thay thế có **điều kiện**, state còn có nhiệm vụ correlation/navigation và Spring CSRF token bảo vệ **business POST** sau login—một bề mặt hoàn toàn khác.

### 7.2. Khi nào PKCE góp phần chống authorization CSRF?

PKCE có thể ngăn client đổi một code mà attacker tạo từ flow **khác**, vì code đó gắn với challenge của attacker, còn RP/client hiện tại giữ verifier của flow mình. Bảo vệ chỉ có ý nghĩa nếu:

1. Client tạo **verifier mới ngẫu nhiên cho mỗi authorization transaction**.
2. Verifier lưu gắn với **đúng user agent/session và authorization request** hiện hành.
3. Authorization Server **cam kết hỗ trợ và thực thi PKCE**, không silently downgrade khi không có challenge/verifier.
4. Token exchange luôn gửi **verifier đúng flow**.
5. Client không cho callback tùy ý chèn một verifier attacker chọn hoặc đọc verifier của session khác.
6. Redirect URI, issuer/provider binding, token validation và replay checks vẫn được thực thi.

Khi client không thể bảo đảm các điều kiện ấy hoặc hỗ trợ nhiều Authorization Servers có profile khác nhau, **state ràng buộc browser/session vẫn là phòng vệ đơn giản và dễ audit**.

### 7.3. State có thể còn được dùng cho mục đích phi-CSRF

Một client có thể dùng state như khóa correlation tới original authorization request (provider, redirect URI, time, intended local navigation) mà không đặt data nghiệp vụ nhạy cảm trực tiếp vào state.

Nếu cần return path:

~~~text
state = random correlation value S
server-side store:
  S -> {
    original authorized client registration,
    expected callback,
    local post-login path "/dashboard"
  }
~~~

Không nhét `https://attacker.example` vào state rồi redirect mù quáng sau login. Return path phải là allowlisted **local path** hoặc một destination được quản trị.

### 7.4. PKCE không thay CSRF token của Spring

Ngay cả trong flow OAuth nơi PKCE cung cấp đầy đủ authorization CSRF protection, sau khi RP thiết lập `JSESSIONID`:

~~~http
POST /account/email
Cookie: JSESSIONID=SESSION_OF_ALICE
Content-Type: application/x-www-form-urlencoded

email=changed@example.invalid
~~~

không chứa authorization code, không gọi token endpoint, không có PKCE challenge/verifier để Authorization Server so. Vì vậy **PKCE không kiểm chứng POST này**. RP phải dùng `CsrfFilter`/`CsrfWebFilter` (hoặc mô hình phòng vệ tương đương được thiết kế đúng nếu thực sự cần).

### 7.5. Đừng dùng state/nonce/verifier như session authentication

`state`, `nonce`, `code_verifier` là **giá trị một giao dịch**. Chúng không tự cấp quyền API và không chứng minh người dùng đã đăng nhập trong mọi request. Cần có SecurityContext/session hoặc Bearer access token tương ứng. Không dùng những chuỗi này làm password, cookie phiên hay API key lâu dài.

## 8. Tổng hợp một authorization transaction hoàn chỉnh

Giả định client/RP `spring-web-client` dùng OIDC Authorization Code + PKCE với IdP `https://login.identity.example`.

### 8.1. Sequence cùng tất cả giá trị

~~~mermaid
sequenceDiagram
    actor U as Alice
    participant B as Browser
    participant RP as Spring RP
    participant AS as OIDC Provider
    participant API as RP business controller

    U->>B: Chọn login Corporate
    B->>RP: GET /oauth2/authorization/corporate
    RP->>RP: state=S; nonce=N; verifier=V; challenge=SHA256(V)
    RP->>RP: Store expected authorization request for browser session
    RP-->>B: 302 /authorize?state=S&nonce=N&code_challenge=C
    B->>AS: Top-level GET /authorize
    AS->>AS: Login/MFA/consent và ghi challenge C
    AS-->>B: 302 RP callback?code=K&state=S
    B->>RP: GET callback với K,S và session cookie khi được phép
    RP->>RP: Tìm expected request, kiểm state S
    RP->>AS: POST /token code=K&code_verifier=V + client auth
    AS->>AS: Kiểm code/client/redirect/PKCE
    AS-->>RP: ID token chứa nonce N, access token
    RP->>RP: Validate signature, iss, aud, exp và nonce N
    RP->>RP: Authentication + session fixation protection
    RP-->>B: Redirect /account + session cookie
    B->>RP: GET /account cùng session
    RP-->>B: HTML form + Spring CSRF token T
    U->>B: Submit thay đổi
    B->>API: POST /account/email Cookie session + _csrf=T
    API->>API: CsrfFilter, authentication và authorization
    API-->>B: Success/redirect theo nghiệp vụ
~~~

**Bốn giá trị được tiêu thụ ở các điểm khác nhau**:

- `S (state)`: callback correlation.
- `N (nonce)`: ID token validation.
- `V (verifier)`: token endpoint kiểm PKCE.
- `T (CSRF token)`: POST nghiệp vụ tại RP sau login.

### 8.2. Chuỗi lỗi được chặn như thế nào?

| Attacker thao tác | Lớp chặn kỳ vọng | Khi nào lớp đó không đủ? |
|---|---|---|
| Gửi callback với `state` từ session khác | State/correlation repository | Nếu RP bỏ binding hoặc accept arbitrary state |
| Thay ID token có nonce của flow cũ | OIDC nonce và ID token validator | Nếu không gửi/kiểm nonce khi flow cần hoặc custom decoder bỏ validation |
| Đánh cắp code nhưng không có verifier | PKCE tại AS token endpoint | Nếu verifier cũng lộ/AS không kiểm PKCE |
| Dùng access token dành cho API X để login RP Y | Audience/token-type checks | Nếu RP nhầm access token với ID token |
| Ép browser đã login POST đổi email | Spring CSRF filter + authz | Nếu endpoint miễn CSRF hoặc session auth được coi tự an toàn |
| Lợi dụng JWT ký đúng nhưng issuer khác | Issuer binding và allowlisted registrations | Nếu RP chấp nhận key/issuer do attacker chọn |
| Gửi POST cross-site callback khi Lax cookie không gửi | Fail-closed correlation | Nếu RP bỏ state/PKCE để “sửa” lỗi |
| Gửi GET tới endpoint có side effect | HTTP method semantics + server design | Nếu GET xóa dữ liệu và CSRF filter mặc định không bảo vệ GET |

### 8.3. Kết luận của flow

Một lần login có thể được coi thành công **chỉ sau tất cả bước protocol authentication cần thiết**, chứ không phải chỉ vì callback có code và session cookie tồn tại. Và một business POST có thể được xử lý **chỉ sau khi auth/session, CSRF và quyền nghiệp vụ đều hợp lệ**.

## 9. Vòng đời, storage và tính một lần của bốn cơ chế

### 9.1. State/nonce/verifier cần gắn với authorization request

Một mô hình lưu dữ liệu tham chiếu:

~~~text
authorization_transaction_id: random identifier
client_registration_id: corporate
browser_session_reference: SESSION-A
issuer: https://login.identity.example
redirect_uri: https://app.example.com/login/oauth2/code/corporate
expected_state: S
expected_nonce: N
code_verifier: V     # secret; server-side only for BFF/RP
created_at: ...
expires_at: ...
consumed: false
post_login_path: /dashboard
~~~

Đây là sơ đồ khái niệm, **không phải cấu trúc bắt buộc của Spring Security**. Thực tế Spring `OAuth2AuthorizationRequest` và repository có các thuộc tính tương ứng theo version/configuration; code verifier có thể lưu dưới attributes.

**Yêu cầu:**

- Không có transaction thì callback không thể “tự đăng nhập”.
- Không dùng state hoặc verifier chung cho nhiều users/clients.
- Có TTL, eviction/cleanup.
- Consume/one-time semantics để tránh replay.
- Correlate đúng issuer/registration/redirect; không chỉ so một chuỗi state.
- Với nhiều tab, phải định nghĩa repository hỗ trợ một hay nhiều pending requests và xử lý race có chủ đích.
- Không ghi raw verifier/nonce/code vào telemetry.

### 9.2. CSRF token đi cùng session/request handler, không cùng OAuth transaction

Ở Spring Servlet, expected CSRF token có thể được quản lý qua `HttpSessionCsrfTokenRepository` hoặc `CookieCsrfTokenRepository` theo kiến trúc; request handler có thể dùng masked XOR token để chống BREACH trong HTML. Ở WebFlux, repository theo `WebSession` và `CsrfWebFilter` thực hiện tương ứng.

Một csrf token có thể có vòng đời theo session, có thể bị xóa/tái tạo khi login/logout. Không mặc định **một token cho mỗi request**, cũng không mặc định **không bao giờ rotate**; phải kiểm theo repository/handler phiên bản thực tế.

### 9.3. Session fixation và tab cũ

Khi login thành công, session fixation protection có thể đổi session ID và làm mới/xóa CSRF token. Nếu một tab có form từ trước login, submit sau login có thể bị `403` là hành vi đúng.

**Không** copy OAuth state vừa tiêu thụ thành `_csrf` mới để chữa form cũ. Hãy reload/token bootstrap lại theo session hiện hành.

### 9.4. Stateless authorization request repository không có nghĩa bỏ correlation

Một public client có thể lưu code verifier/state trong browser-managed storage theo OAuth SDK; một BFF có thể thiết kế cookie correlation có chữ ký/mã hóa. Nhưng dù không dùng `HttpSession`, client vẫn phải chứng minh authorization response liên quan **đúng request/session browser**, đúng issuer/redirect, không bị replay/đọc hoặc sửa bởi attacker.

“Stateless” là cách lưu state, **không phải lý do bỏ state/nonce/PKCE validation**.

## 10. Servlet Spring Security: hai repository, hai bộ lọc, hai mục tiêu

### 10.1. Phụ thuộc và giả định

Kịch bản sử dụng Spring Boot Servlet/Spring MVC làm **OIDC Relying Party** với browser session:

~~~text
spring-boot-starter-web
spring-boot-starter-security
spring-boot-starter-oauth2-client
spring-boot-starter-thymeleaf       # nếu render form HTML
spring-boot-starter-test           # test
spring-security-test               # test
~~~

Spring OAuth2 Client thực hiện authorize redirect, lưu request, callback, code exchange và OIDC login. Spring CSRF filter bảo vệ **unsafe requests của browser**. Không dùng OAuth2 Resource Server JWT validation như thể nó tự triển khai `oauth2Login()`; đó là vai trò khác.

### 10.2. OIDC ClientRegistration cơ bản

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate:
            provider: corporate-idp
            client-id: ${CORPORATE_CLIENT_ID}
            client-secret: ${CORPORATE_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            scope:
              - openid
              - profile
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
        provider:
          corporate-idp:
            issuer-uri: https://login.identity.example/realms/corporate
~~~

- `openid` khiến flow này là **OIDC**, không chỉ OAuth 2.0.
- `redirect-uri` là public HTTPS callback mà IdP đã đăng ký; `{baseUrl}` phải phản ánh trusted external host/scheme.
- `client-secret` dùng cho **confidential client**; không commit vào source, chỉ dùng secret manager/environment.
- Public/native/SPA clients có client authentication và PKCE profile khác; không đưa client secret của confidential RP vào JavaScript.
- `issuer-uri` là IdP được tin cậy; không tự nhận issuer discovery URL tùy ý từ request của user.
- Cấu hình Spring Security/Authorization Server có thể tự áp dụng PKCE theo client type/version. **Kiểm HTTP redirect để xác nhận `code_challenge`/`S256` thay vì giả định.**

### 10.3. HttpSecurity bật cả OAuth2 Login và CSRF

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class OidcAndCsrfServletSecurity {

    @Bean
    SecurityFilterChain browser(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    "/login", "/assets/**", "/error").permitAll()
                .requestMatchers("/account/**").authenticated()
                .anyRequest().authenticated()
            )
            .oauth2Login(Customizer.withDefaults())
            .csrf(Customizer.withDefaults())
            .build();
    }
}
~~~

Trong cấu hình này:

- `GET /oauth2/authorization/corporate` đi qua **OAuth2AuthorizationRequestRedirectFilter**: tạo authorization request, state và các thuộc tính OIDC/PKCE tương ứng flow/config.
- `GET /login/oauth2/code/corporate?code=...&state=...` đi qua **OAuth2LoginAuthenticationFilter**: lấy expected request và thực hiện validation/code exchange.
- `POST /account/email` đi qua **CsrfFilter**: cần token từ `CsrfTokenRepository` cùng authentication/authorization.
- `GET` là safe HTTP method theo mặc định CSRF matcher, **không có nghĩa OAuth GET callback bỏ state validation**.
- `oauth2Login()` **không đồng nghĩa** `csrf().disable()`.

### 10.4. Hai repository độc lập

| Công việc | Spring Servlet API | Chịu trách nhiệm |
|---|---|---|
| Lưu authorization request/expected `state` | `AuthorizationRequestRepository<OAuth2AuthorizationRequest>`, thường `HttpSessionOAuth2AuthorizationRequestRepository` | Đúng login flow và callback |
| Lưu expected `_csrf` | `CsrfTokenRepository`, thường `HttpSessionCsrfTokenRepository` | Unsafe browser POST sau/ngoài login |
| Lưu SecurityContext đã login | `SecurityContextRepository` theo session/security context configuration | Authentication của những HTTP request tiếp theo |
| Validation OIDC ID token | OIDC login providers/ID token validators | Chữ ký/issuer/audience/time/nonce theo flow |
| Kiểm PKCE tại token exchange | Authorization Server | Verifier khớp challenge của code |

**Hai repository cùng có thể dựa vào HttpSession nhưng vẫn khác dữ liệu, vòng đời và filter tiêu thụ.** Không coi `SessionCreationPolicy.STATELESS` trên browser login chain là cấu hình mặc định an toàn; nó có thể phá authorization request correlation và persistence.

### 10.5. Tùy biến PKCE trong AuthorizationRequestResolver khi cần

Một bản Spring Security hỗ trợ `OAuth2AuthorizationRequestCustomizers.withPkce()` có thể dùng mẫu sau để **chủ động bật PKCE** cho authorize request:

~~~java
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizationRequestResolver;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizationRequestCustomizers;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizationRequestRedirectFilter;

// Trích đoạn trong method cấu hình hoặc @Bean tương ứng:
DefaultOAuth2AuthorizationRequestResolver resolver =
    new DefaultOAuth2AuthorizationRequestResolver(
        registrations,
        OAuth2AuthorizationRequestRedirectFilter
            .DEFAULT_AUTHORIZATION_REQUEST_BASE_URI);

resolver.setAuthorizationRequestCustomizer(
    OAuth2AuthorizationRequestCustomizers.withPkce());
~~~

Đưa resolver vào OAuth2 Login:

~~~java
.oauth2Login(oauth -> oauth
    .authorizationEndpoint(endpoint -> endpoint
        .authorizationRequestResolver(resolver)))
~~~

**Điều kiện quan trọng:** `registrations` phải là `ClientRegistrationRepository` được inject, `resolver` phải được tạo đúng context và không làm mất customizers khác. Mã là **trích đoạn** để minh họa extension point; xác minh method/imports với Spring Security version của project. Provider phải hỗ trợ/áp PKCE đúng, và client phải giữ verifier của **đúng authorization request** cho token exchange.

Với public client hoặc cấu hình mặc định đã có PKCE, tránh bật trùng hoặc thay resolver chỉ để “trông có vẻ bảo mật”. Kiểm thử authorize redirect có challenge, token exchange có verifier và negative test verifier sai.

### 10.6. Tùy biến authorization request repository không thay CSRF repo

~~~java
import org.springframework.security.oauth2.client.web.HttpSessionOAuth2AuthorizationRequestRepository;

HttpSessionOAuth2AuthorizationRequestRepository authRequestRepository =
    new HttpSessionOAuth2AuthorizationRequestRepository();

// Trích đoạn DSL:
.oauth2Login(login -> login
    .authorizationEndpoint(endpoint -> endpoint
        .authorizationRequestRepository(authRequestRepository)))
~~~

Đây là repository **state/authorization transaction**, không phải một `CsrfTokenRepository`. Một custom repository phải xử lý concurrency, one-time use, expiry, browser binding và PKCE verifier; không đơn giản lưu state theo `Map<String,Object>` toàn cục và để bất kỳ session nào lấy.

**Điểm nhấn:** Spring cung cấp default integration; chỉ tùy biến repository khi thật sự có yêu cầu multi-tab, cross-node, storage hay IdP-specific response mode và có bộ test tương ứng.

## 11. Servlet: token của form/SPA sau OIDC login

### 11.1. Thymeleaf hidden CSRF input

Một controller đã yêu cầu authentication trên `/account/**` có thể render form:

~~~html
<form action="/account/email" method="post">
  <label for="email">Email</label>
  <input id="email" name="email" type="email" required>

  <input type="hidden"
         th:name="${_csrf.parameterName}"
         th:value="${_csrf.token}">

  <button type="submit">Lưu thay đổi</button>
</form>
~~~

`_csrf` là request attribute do Spring Security cung cấp theo stack/config. Một số Thymeleaf/Spring integrations có thể tự thêm hidden CSRF field khi dùng `th:action`; **kiểm HTML được render** để tránh trùng field.

Không cần đưa `state`, `nonce` hoặc PKCE verifier từ login transaction vào form. Những giá trị này có thể đã bị tiêu thụ và **không được tái sử dụng** cho các business POSTs.

### 11.2. SPA session-based gửi CSRF header

Với browser SPA gọi RP cùng origin:

~~~javascript
const response = await fetch("/account/email", {
  method: "POST",
  credentials: "same-origin",
  headers: {
    "Content-Type": "application/json",
    "X-CSRF-TOKEN": csrfFromApp
  },
  body: JSON.stringify({ email: "alice@example.invalid" })
});
~~~

`csrfFromApp` đến từ HTML/bootstrap endpoint/cookie repository theo chính sách. Spring Security Servlet hiện đại có thể **defer token loading** và sử dụng **XOR-masked token khi render**; nếu SPA đọc raw token từ cookie, request handler phải được cấu hình đúng cho raw token so với expected token. Đừng chữa mismatch bằng việc **tắt CSRF** hoặc lấy OAuth state làm header.

### 11.3. Token khác nhau xuất hiện trên Network tab

Sau login, DevTools có thể thấy:

~~~text
GET  /oauth2/authorization/corporate
302  Location: IdP authorize?state=S&nonce=N&code_challenge=C

GET  /login/oauth2/code/corporate?code=K&state=S
302  Location: /account

GET  /account
200  HTML có hidden _csrf=T (hoặc SPA bootstrap)

POST /account/email
Cookie: JSESSIONID=AUTHENTICATED_SESSION
X-CSRF-TOKEN: T
~~~

Nếu một trace có `code_verifier` đi cùng `POST /account/email`, đó là dấu hiệu **trộn sai giao thức**. Verifier chỉ cần cho code exchange tại token endpoint, và không nên xuất hiện trong browser business requests của server-side RP.

## 12. SameSite và redirect: state mất không có nghĩa nên bỏ state

### 12.1. Một GET callback phụ thuộc browser cookie

Với RP dùng `HttpSessionOAuth2AuthorizationRequestRepository`, expected state thường tìm lại qua session cookie.

~~~mermaid
flowchart TD
    A[Browser gọi RP và nhận session cookie] --> B[RP tạo state S và redirect IdP]
    B --> C[IdP top-level redirect GET callback]
    C --> D{Cookie RP có được gửi?}
    D -->|Có| E[RP tải expected authorization request]
    D -->|Không| F[Authorization request not found]
    E --> G{State S đúng?}
    G -->|Có| H[Đổi code + validate OIDC]
    G -->|Không| I[Từ chối state mismatch]
    F --> J[Không login; sửa cookie hoặc repository]
~~~

Ở callback:

- Cookie `SameSite=Lax` thường **được phép gửi** trên cross-site top-level GET nếu Domain/Path/Secure hợp lệ.
- `SameSite=Strict` thường **không được gửi** trong cross-site navigation về RP.
- `SameSite=None; Secure` mở thêm những ngữ cảnh cookie gửi, nhưng vẫn chịu browser privacy/third-party cookie rules.
- Nếu hostname/Path/expiry sai, Lax không giúp; cookie không tới được RP.
- Login code/state đúng **không có nghĩa RP có thể bỏ correlation khi cookie bị mất**.

### 12.2. Form POST callback khác GET

IdP có thể hỗ trợ `response_mode=form_post`:

~~~http
POST /login/oauth2/code/corporate HTTP/1.1
Host: app.example.com
Origin: https://login.identity.example
Content-Type: application/x-www-form-urlencoded

code=K&state=S
~~~

Với cross-site POST, cookie RP `SameSite=Lax` **thường không gửi**, khiến repository session-backed không tìm được expected state/verifier/nonce.

Để hỗ trợ form_post thực sự, cần **đồng thời**:

1. Callback handler OAuth2 Login có hỗ trợ method/response_mode và parse POST đúng;
2. Cookie/correlation mechanism hợp lệ trong cross-site POST (có thể cần `SameSite=None; Secure` hoặc thiết kế correlation khác);
3. CSRF filter không chặn **riêng POST callback giao thức hợp lệ** một cách vô ý, nhưng các business POST còn được bảo vệ;
4. State/nonce/PKCE/issuer/audience/code validation vẫn được thực thi;
5. Browser tests nhiều vendor/third-party cookie policy.

Không tự assume `csrf.ignoringRequestMatchers("/login/oauth2/code/**")` đủ để Spring mặc định hỗ trợ form_post. **Nới CSRF chỉ sau khi xác minh handler và protocol validator tương ứng**, và nên giới hạn matcher method/path/provider.

### 12.3. Browser default và các ngoại lệ Lax

Một số browser có ngoại lệ tương thích ngắn hạn cho **cookie không khai SameSite** trong POST sau khi được tạo, nhưng không thể dùng đó làm security contract cho **explicit `SameSite=Lax`**. Luôn kiểm `Set-Cookie` và request Cookie thực tế, không chỉ nhìn cookie list.

### 12.4. CORS không sửa được lỗi callback

OAuth authorize redirect và callback là **browser navigations**, không phải JavaScript fetch đọc response từ cross-origin IdP. CORS không quyết định session cookie RP có được gửi ở top-level GET/POST callback. Một `Access-Control-Allow-Origin: *` rộng không sửa mất state; chỉ làm tăng rủi ro với các API khác nếu triển khai sai.

## 13. Redirect URI, proxy và session store: các yếu tố ngoài token

### 13.1. Public callback URL phải nhất quán

~~~text
Browser → RP:        https://app.example.com
Reverse proxy → app: http://spring-app:8080
Registered callback: https://app.example.com/login/oauth2/code/corporate
~~~

Nếu app tính `redirect_uri` thành `http://spring-app:8080/...`, IdP có thể báo mismatch hoặc callback về host không có cookie. Hãy đăng ký chính xác public URI; với proxy đáng tin cậy, cấu hình forwarded scheme/host phù hợp và **strip forwarded headers do client Internet giả**.

Ví dụ một property trong Spring Boot:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

Property này **không tự làm forwarded headers đáng tin**. Hạ tầng phải quyết định proxy nào được ghi đè headers, chặn direct backend access và validate public hosts.

### 13.2. Session node A và callback node B

Nếu authorization request chỉ nằm trong HttpSession node A mà callback đến node B không có store chung, **state không tìm được**.

Dùng Spring Session/shared backing store, sticky session có đánh giá failover hoặc custom transaction repository đáng tin. Giữ TTL đủ cho MFA/consent, nhưng không bỏ state validation để tránh lỗi cluster.

### 13.3. Nhiều tab / nhiều pending login transactions

Một user mở login qua provider A rồi provider B trong hai tab; hai callback có thể về theo thứ tự đảo.

Một số repository mặc định có thể chỉ giữ một expected authorization request hoặc có hành vi overwrite; **đo/kiểm trên version đang dùng**, không assume concurrent flows luôn được hỗ trợ. Một custom multi-request repository phải index đúng state cùng binding browser, chống replay và bảo vệ verifier/nonce riêng của từng transaction.

### 13.4. Không dùng open redirect làm return path

Sau login, RP có thể redirect user về page đã chọn; nhưng không tin `next=https://attacker.example` hoặc URL có scheme/protocol-relative arbitrary. Dùng local path allowlist/canonicalization; tránh đưa authorization code/state/ID token vào return URL.

## 14. Reactive/WebFlux: cùng ranh giới, API khác Servlet

### 14.1. Bảng đối chiếu

| Chức năng | Servlet/Spring MVC | Reactive/WebFlux |
|---|---|---|
| Security builder | `HttpSecurity` | `ServerHttpSecurity` |
| Security chain | `SecurityFilterChain` | `SecurityWebFilterChain` |
| CSRF filter | `CsrfFilter` | `CsrfWebFilter` |
| CSRF repository | `CsrfTokenRepository` | `ServerCsrfTokenRepository` |
| Repository token theo session | `HttpSessionCsrfTokenRepository` | `WebSessionServerCsrfTokenRepository` |
| Browser session | `HttpSession` | `WebSession` |
| OAuth authorization request repository | `AuthorizationRequestRepository<OAuth2AuthorizationRequest>` | `ServerAuthorizationRequestRepository<OAuth2AuthorizationRequest>` |
| Repository tương ứng phiên | `HttpSessionOAuth2AuthorizationRequestRepository` | `WebSessionOAuth2ServerAuthorizationRequestRepository` |
| Client registration | `ClientRegistrationRepository` | `ReactiveClientRegistrationRepository` |
| OAuth2 login | `oauth2Login()` | `oauth2Login()` trên reactive builder |
| Cookie resolver | Servlet container / Spring Session | `CookieWebSessionIdResolver` hoặc Spring Session |
| Test | `MockMvc` | `WebTestClient` |

Browser không quan tâm backend dùng blocking thread hay Reactor: SameSite, redirect, CSRF và OIDC state/nonce/PKCE vẫn tuân cùng threat model. Đừng đồng nhất `ServerCsrfTokenRepository` với repository lưu `state`.

### 14.2. Cấu hình Reactive OAuth2 login với CSRF

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
class OidcReactiveBoundarySecurity {

    @Bean
    SecurityWebFilterChain browser(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers("/login", "/assets/**", "/error")
                    .permitAll()
                .pathMatchers("/account/**").authenticated()
                .anyExchange().authenticated()
            )
            .oauth2Login(Customizer.withDefaults())
            .csrf(Customizer.withDefaults())
            .build();
    }
}
~~~

OAuth2 Login dùng authorization request repository liên kết với browser/WebSession theo thiết kế. Sau callback, browser có thể giữ session cookie `SESSION` và `CsrfWebFilter` kiểm unsafe business requests. `NoOpServerSecurityContextRepository` thường chỉ nên dùng khi chủ đích triển khai bearer-only stateless chain, **không tùy tiện gắn cho browser login chain**.

### 14.3. Cookie WebSession cho top-level GET callback

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.server.session.CookieWebSessionIdResolver;
import org.springframework.web.server.session.WebSessionIdResolver;

@Configuration
class ReactiveSessionCookieConfig {

    @Bean
    WebSessionIdResolver webSessionIdResolver() {
        CookieWebSessionIdResolver resolver =
            new CookieWebSessionIdResolver();

        resolver.setCookieName("SESSION");
        resolver.addCookieInitializer(cookie -> cookie
            .path("/")
            .httpOnly(true)
            .secure(true)
            .sameSite("Lax"));

        return resolver;
    }
}
~~~

Ví dụ áp dụng khi Spring Framework version hỗ trợ `addCookieInitializer` và resolver đó thực sự phát cookie. Nếu Spring Session/custom serializer quản lý cookie, hãy cấu hình đúng nơi. Kiểm response `Set-Cookie` ở public HTTPS host.

Lax phù hợp nhiều OIDC top-level GET callbacks nhưng thường chặn cookie trong cross-site `form_post`. **CSRF disabled toàn ứng dụng không giải quyết việc state/authorization request không được tìm thấy.**

### 14.4. OIDC authorization request và CSRF token cùng WebSession nhưng khác nhiệm vụ

~~~text
WebSession liên quan browser A:
  OAuth2 authorization request:
    expected state S
    expected OIDC nonce N (nếu flow gửi)
    PKCE verifier V (nếu flow dùng PKCE)

  CSRF token repository:
    expected submitted token T

  SecurityContext sau login:
    authenticated principal
~~~

Các mục trên là mô hình **khái niệm**, không phải property names chính xác trong WebSession. Khi viết custom reactive repository, phải giữ state/issuer/registration/redirect/browser correlation, nonce/verifier, TTL, one-time/replay protection và không block event loop.

### 14.5. Controller Reactively render CSRF token cho form

~~~java
import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.reactive.result.view.Rendering;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@Controller
class ReactiveAccountFormController {

    @GetMapping("/account/email")
    Mono<Rendering> form(ServerWebExchange exchange) {
        Mono<CsrfToken> csrf =
            exchange.getAttribute(CsrfToken.class.getName());

        return csrf.map(token ->
            Rendering.view("account/email")
                .modelAttribute("_csrf", token)
                .build());
    }
}
~~~

Mẫu phụ thuộc `CsrfWebFilter` đã cung cấp attribute trên route và tương thích với version; thực tế cần kiểm controller/view integration. Không gọi `block()`, không thay `_csrf` bằng OAuth state/nonce/PKCE verifier. Khi session login/logout rotate, token/form cũ có thể bị từ chối hợp lệ.

### 14.6. PKCE/nonce trong Reactive cần được kiểm chứng bằng protocol test

- Authorize redirect thực tế có `code_challenge` và `code_challenge_method=S256` khi yêu cầu PKCE.
- Token endpoint kiểm verifier và từ chối verifier sai.
- OIDC nonce được gửi/kiểm theo flow/profile.
- Callback từ session khác hoặc state sai bị từ chối trước khi tạo authenticated WebSession.
- Custom reactive resolver/repository không làm mất correlation hoặc thực hiện blocking I/O trên event loop.

Không chuyển Servlet `DefaultOAuth2AuthorizationRequestResolver` nguyên xi vào WebFlux; dùng API reactive phù hợp với Spring Security version triển khai.

## 15. Đừng nhầm chúng với code, tokens và cookie

### 15.1. Authorization code là artifact ngắn hạn

Code do Authorization Server phát, được đổi một lần tại token endpoint. Nó không phải access token/session ID. PKCE hạn chế tấn công chỉ biết code mà không biết verifier; state kiểm response thuộc expected transaction; nonce dùng khi kiểm ID token.

### 15.2. ID token chỉ dùng đúng audience và OIDC role

ID token là assertion authentication cho OIDC client, cần validate signature, issuer, audience, timestamps và nonce khi được yêu cầu. Nó không được dùng thay access token để gọi arbitrary Resource Server. Nonce đúng không bù được issuer hoặc audience sai.

### 15.3. Access token là credential API có phạm vi

Access token thường được dùng trong `Authorization: Bearer` cho Resource Server. Kiểm issuer/audience/scope/expiry, client/user authority và resource ACL. API thật sự bearer-only và không nhận ambient browser credential có thể được đánh giá miễn CSRF kiểu cookie; token theft/XSS/replay vẫn là những rủi ro riêng.

### 15.4. Refresh token và session ID không phải CSRF token

Refresh token dùng xin token mới; nếu refresh API nhận **cookie tự gửi**, phải xét CSRF theo mô hình đó. Session ID `JSESSIONID`/`SESSION` là ambient credential của RP; `HttpOnly` không ngăn browser gửi nó. Đừng đưa refresh token, session ID hoặc access token vào `_csrf` field để “tái sử dụng” một chuỗi bí mật.

### 15.5. Khi login xong, OAuth state có thể không còn

State/nonce/verifier của authorization transaction thường bị tiêu thụ hoặc xóa. Business POST sau login **không** mang code/state/nonce/verifier; nó mang session cookie và submitted CSRF token. Đó là lý do cả OAuth2 Login và Spring CSRF protection cần được cấu hình/kiểm thử độc lập.

## 16. Hệ thống hỗn hợp browser OIDC + M2M Bearer

### 16.1. Hai SecurityFilterChain Servlet

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Bean
@Order(1)
SecurityFilterChain integrations(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/integrations/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.POST, "/integrations/jobs")
                .hasAuthority("SCOPE_jobs:write")
            .anyRequest().authenticated()
        )
        .sessionManagement(s -> s
            .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
        .formLogin(AbstractHttpConfigurer::disable)
        .httpBasic(AbstractHttpConfigurer::disable)
        .oauth2ResourceServer(oauth -> oauth
            .jwt(Customizer.withDefaults()))
        .csrf(AbstractHttpConfigurer::disable)
        .build();
}

@Bean
@Order(2)
SecurityFilterChain browser(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/login", "/assets/**").permitAll()
            .anyRequest().authenticated()
        )
        .oauth2Login(Customizer.withDefaults())
        .csrf(Customizer.withDefaults())
        .build();
}
~~~

Đây là **một phương án thay thế** cho ứng dụng có hai kiểu client; không đặt cạnh một bộ security chain khác có matcher/order xung đột. Spring chỉ chọn **chain phù hợp đầu tiên**:

- `/login/oauth2/code/**` phải vào browser OAuth2 Login chain; callback dùng state/nonce/PKCE.
- `/account/**` dùng browser session/CSRF.
- `/integrations/**` chỉ được miễn CSRF nếu bearer-only thực sự, không chấp nhận session cookie/Basic/SSO gateway fallback.
- JWT access token M2M vẫn cần signature/issuer/audience/expiry/scopes và object-level authorization.

### 16.2. Kiểm thử ranh giới hai chiều

~~~text
Browser đã đăng nhập:
  POST /integrations/jobs chỉ có Cookie: JSESSIONID=...
  -> không được xác thực thành machine principal

M2M worker có access token:
  POST /account/email chỉ có Authorization: Bearer ...
  -> không được coi như browser OIDC authenticated user
~~~

Nếu có cả Cookie lẫn Bearer header trong cùng request, phải làm rõ credential precedence, custom filter/gateway behavior và kiểm không có quyền tăng nhờ fallback.

### 16.3. Reactive tương ứng

Reactive có thể dùng `SecurityWebFilterChain`, `@Order(1)` cùng `ServerWebExchangeMatchers.pathMatchers("/integrations/**")` cho bearer-only Resource Server và browser fallback với `oauth2Login` + `csrf`. Không để custom WebFilters biến browser cookie thành M2M authentication trong vùng đã miễn CSRF.

## 17. CORS, CSP, HSTS, HTTP firewall và proxy: bảo vệ ở đúng lớp

### 17.1. CORS không quyết định OAuth redirect

| Request | Browser CORS áp không? | Cơ chế cần kiểm |
|---|---|---|
| Browser top-level redirect RP → IdP authorize | Không cần CORS | Trusted issuer, redirect URI, state/PKCE |
| Browser top-level GET callback IdP → RP | Không cần CORS | Cookie SameSite, state, nonce, code |
| Browser form POST callback `form_post` | CORS không chặn form navigation thông thường | Cookie, callback handler, protocol validation |
| RP backend POST token endpoint | Không chịu browser CORS | TLS, client auth, code+PKCE |
| SPA JavaScript `fetch` API origin khác | Có | CORS, credential model, CSRF nếu session-cookie |
| M2M HTTP client → Resource API | Không | Bearer token + TLS + authorization |

Nếu callback thất bại do `authorization_request_not_found`, đừng thêm `Access-Control-Allow-Origin: *`; kiểm cookie, repository, matcher và proxy.

### 17.2. CSP giúp giảm XSS, không thay protocol validation

~~~http
Content-Security-Policy: default-src 'self'; script-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'
~~~

Header cần được đặt trên **HTML login/app shell thực**, không chỉ JSON API. Điều chỉnh `form-action`/`connect-src` theo UI và IdP integration. XSS trong origin RP có thể lạm dụng phiên/CSRF token hoặc OAuth data nếu bị render ra DOM; CSP, output escaping và DOM hardening giảm rủi ro đó, nhưng **không thay state/nonce/PKCE**.

### 17.3. HTTPS/HSTS, cookie và forwarded headers

RP, IdP authorize/token endpoints và callback cần HTTPS/TLS đáng tin. Session cookies nên có `Secure; HttpOnly; SameSite`, Domain/Path phù hợp. HSTS giúp browser nâng cấp scheme theo host policy; `includeSubDomains`/preload chỉ khi toàn bộ host đã sẵn sàng.

Proxy không được tin `Forwarded`/`X-Forwarded-Host` do attacker gửi; nếu Spring tạo `{baseUrl}` từ forwarded headers giả, callback URL có thể sai hoặc bị điều hướng đến host không tin cậy.

### 17.4. HTTP firewall và callback matcher

Một callback thông thường:

~~~text
/login/oauth2/code/corporate?code=...&state=...
~~~

Proxy path rewrite, encoded slashes, semicolons, duplicate slash hoặc context path khác nhau có thể làm callback không khớp OAuth2 Login filter. Kiểm **public URL → upstream URL → Spring security matcher**; không nới lỏng `StrictHttpFirewall` hoặc cho `/**` permitAll để “sửa state mismatch”.

### 17.5. Browser third-party cookie khác top-level redirect

Silent SSO/front-channel logout trong iframe có thể bị third-party cookie blocking, dù top-level login của chính IdP hoạt động. `SameSite=None; Secure` không bảo đảm mọi browser cho cookie trong iframe. Không tắt state/nonce/PKCE/CSRF để chữa lỗi cookie của silent iframe.

### 17.6. Referrer, cache và logging

Callback URL có thể chứa `code` và `state`, token exchange có `code_verifier`, client credentials và tokens. Cần `Referrer-Policy` phù hợp, `Cache-Control: no-store` cho các phản hồi auth nhạy cảm và logging redaction. Không ghi raw authorization code, state, nonce, verifier, session cookie, ID/access/refresh token, client secret hoặc full signed URLs vào logs/traces.

## 18. Năm tình huống tấn công: chọn đúng cơ chế

### 18.1. Login CSRF

~~~text
Attacker có callback code K_A + state S_A từ flow riêng.
Victim có session V với expected state S_V.
Attacker ép victim GET callback?code=K_A&state=S_A.

RP tìm expected request trong session V:
  S_V != S_A -> từ chối, không login.
~~~

**Bảo vệ:** state + browser/session correlation, có thể có PKCE đúng flow làm lớp bổ sung. Spring `_csrf` của form sau login không tự bảo vệ callback GET.

### 18.2. Authorization code bị lấy cắp

~~~text
Attacker biết code K.
Authorization Server gắn K với challenge C = S256(verifier V).
Attacker không có V, gửi verifier A.
S256(A) != C -> token endpoint từ chối.
~~~

**Bảo vệ:** PKCE tại AS. Chỉ biết state không đủ ngăn một attacker đã có code đổi code của public client nếu AS không bảo vệ token exchange đúng.

### 18.3. ID token cũ được thay vào lần login mới

~~~text
Expected nonce của flow hiện tại = N2.
ID token cũ được ký đúng nhưng chứa nonce N1.
N1 != N2 -> OIDC client từ chối theo flow.
~~~

**Bảo vệ:** nonce khi được yêu cầu, cùng signature/issuer/audience/timestamp validation. Không dùng nonce làm form CSRF token.

### 18.4. Browser POST bị giả mạo sau OIDC login

~~~text
Alice đã login RP, browser có session cookie.
Attacker khiến browser POST /account/email.
Không có submitted _csrf hợp lệ.
CsrfFilter/CsrfWebFilter từ chối, dữ liệu không đổi.
~~~

**Bảo vệ:** Spring CSRF. State/nonce/verifier của authorization transaction đã hết vai trò.

### 18.5. Account mix-up giữa hai issuers

~~~text
IdP A phát sub=123 cho Alice.
IdP B phát sub=123 cho Bob.
RP map user chỉ bằng sub=123 -> nhầm tài khoản.
~~~

**Bảo vệ:** issuer+subject identity mapping, trusted provider correlation và account-linking policy. Không thể sửa chỉ bằng một token ngẫu nhiên.

### 18.6. Refresh endpoint được bảo vệ sai mô hình

~~~text
POST /auth/refresh
Cookie: REFRESH_TOKEN=browser-cookie

Endpoint chấp nhận cookie tự gửi và có tác động đến token lifecycle.
~~~

Cần đánh giá CSRF, SameSite, Origin/Fetch Metadata, refresh rotation/replay detection riêng. Không miễn mọi POST liên quan OAuth chỉ vì bearer-only API ở đường dẫn khác có thể được miễn CSRF.

## 19. Ma trận kiểm thử: chứng minh mỗi ranh giới riêng biệt

| ID | Dữ liệu/tình huống | Kiểm tra chính | Kết quả cần đạt |
|---|---|---|---|
| **T-01** | GET authorize hai lần | State uniqueness | Mỗi flow có state entropy cao, không hardcode |
| **T-02** | Authorization request có PKCE S256 | PKCE initiation | Có code challenge/method khi profile yêu cầu |
| **T-03** | OIDC request gửi nonce | Nonce initiation | Expected nonce gắn với đúng flow |
| **T-04** | Callback đúng state/cookie/session | State correlation | Được xét tiếp code exchange |
| **T-05** | Callback thiếu state | State validation | Từ chối, không login |
| **T-06** | Callback sai state | State validation | Từ chối, không login |
| **T-07** | Callback state flow A + session B | Browser binding | Không session swapping |
| **T-08** | Callback replay code/state | One-time semantics | Không login lần nữa |
| **T-09** | Callback sau session timeout | Repository expiry | Fail closed, không tự khôi phục state |
| **T-10** | Callback thuộc IdP A nhưng xử lý như B | Issuer/registration binding | Không login sai provider |
| **T-11** | Authorization code đã dùng/hết hạn | Code validation | Token endpoint từ chối |
| **T-12** | Code + verifier đúng | PKCE | Đổi code nếu các checks khác hợp lệ |
| **T-13** | Code + verifier sai | PKCE | Token endpoint từ chối |
| **T-14** | Code đã có challenge nhưng thiếu verifier | PKCE downgrade resistance | Từ chối |
| **T-15** | Verifier từ flow khác | PKCE transaction binding | Từ chối |
| **T-16** | ID token có nonce đúng | OIDC nonce | Có thể qua nonce check |
| **T-17** | ID token nonce sai | OIDC nonce | Từ chối login |
| **T-18** | ID token replay từ flow cũ | Nonce/replay | Từ chối |
| **T-19** | ID token sai signature | JWT validation | Từ chối |
| **T-20** | ID token sai issuer | Issuer validation | Từ chối |
| **T-21** | ID token sai audience/client ID | Audience validation | Từ chối |
| **T-22** | ID token expired/`nbf` sai khi áp dụng | Time validation | Từ chối |
| **T-23** | Login thành công rồi truy cập protected page | RP session | Authenticated principal đúng |
| **T-24** | Business POST với CSRF hợp lệ | Spring CSRF + authz | Chỉ xử lý nếu user có quyền |
| **T-25** | Business POST thiếu CSRF | Spring CSRF | `403`, không side effect |
| **T-26** | Business POST CSRF sai | Spring CSRF | `403`, không side effect |
| **T-27** | CSRF token của session B gửi với session A | Token/repository binding | Từ chối |
| **T-28** | Form trước login submit sau session rotation | CSRF lifecycle | Không bypass, UX reload an toàn |
| **T-29** | Browser GET callback với Lax | SameSite browser behavior | Cookie đến RP nếu scope hợp lệ |
| **T-30** | Browser POST form_post với Lax | SameSite browser behavior | Cookie thường bị loại, fail closed |
| **T-31** | Browser GET callback với Strict | SameSite browser behavior | Không phụ thuộc vào Strict cookie được gửi cross-site |
| **T-32** | Callback host/Path khác scope cookie | Cookie scope | Không bỏ state check |
| **T-33** | Redirect URI sai external host/scheme | IdP/Proxy | Reject/mismatch, không mở callback tùy ý |
| **T-34** | Callback từ node khác | Session store | Same correlation nếu architecture hỗ trợ |
| **T-35** | Hai tabs khởi tạo đồng thời | Repository concurrency | Không trộn state/verifier/nonce |
| **T-36** | M2M Bearer API chỉ có cookie browser | Credential isolation | Không được authenticated |
| **T-37** | Browser account API chỉ có machine Bearer | Credential isolation | Không trở thành RP web user |
| **T-38** | Local logout thiếu CSRF | Spring CSRF | Không bị forced logout |
| **T-39** | Code/state/verifier trong proxy logs | Sensitive-data hygiene | Redacted |
| **T-40** | Hai issuers cùng `sub` | Identity/account linking | Không map nhầm người |

**Trọng tâm kiểm thử:** Sau một callback fail không tồn tại authenticated session mới; sau một POST bị CSRF chặn không có DB mutation; khi PKCE verifier sai không có token; khi nonce sai không có OIDC principal.

### 19.1. Phân loại 401, 403, redirect và OAuth errors

- **`403` trên `POST /account/email`:** thường do CSRF/authorization; kiểm filter và exception.
- **`authorization_request_not_found` hoặc state mismatch trên OAuth callback:** thường là cookie/session/repository/state correlation, không phải `_csrf` của business POST.
- **`invalid_grant` từ token endpoint:** code expired/reused, redirect URI/client/PKCE mismatch hoặc server policy; kiểm đúng token request.
- **OIDC nonce/issuer/audience failure:** token validation sau code exchange; không chữa bằng cách cho callback permitAll.
- **`302 /login?error`:** authentication entry/failure handler có thể che lỗi gốc; kiểm logs **đã redact** và loại failure.
- **`401` trên M2M API:** lỗi Resource Server access token; đừng nhầm với OIDC ID token validation của login RP.

### 19.2. Negative assertions trước và sau

~~~text
Trước: authenticated session user = none
Gửi callback với state của phiên khác
Kỳ vọng: không có authenticated session, không map account.

Trước: email user Alice = alice@old.example
Gửi POST /account/email với session Alice và thiếu _csrf
Kỳ vọng: HTTP 403, email giữ nguyên, không event EmailChanged.

Gửi token exchange với code K và verifier sai
Kỳ vọng: token endpoint không trả access/ID token, code không được
xử lý thành successful login.
~~~

Không chỉ assert HTTP status rồi bỏ qua side effects và session identity. Với test provider token grants, có thể phải kiểm code one-time/replay và auth server state riêng.

## 20. MockMvc: test Spring CSRF và khởi tạo OAuth2 Login trên Servlet

### 20.1. Test form POST sau login bằng `oidcLogin()`

`spring-security-test` có helper `oidcLogin()` mô phỏng OIDC principal cho một request. Ví dụ giả định app có `GET /account` trả 200 và `POST /account/email` trả redirect sau khi update:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.oidcLogin;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OidcVsCsrfServletTests {

    @Autowired MockMvc mvc;

    @Test
    void oidcPrincipalCanReadOwnAccount() throws Exception {
        mvc.perform(get("/account").with(oidcLogin()))
            .andExpect(status().isOk());
    }

    @Test
    void oidcLoginDoesNotExemptBusinessPostFromCsrf()
            throws Exception {

        mvc.perform(post("/account/email")
                .with(oidcLogin())
                .param("email", "must-not-save@example.invalid"))
            .andExpect(status().isForbidden());
    }

    @Test
    void correctCsrfCanReachBusinessController()
            throws Exception {

        mvc.perform(post("/account/email")
                .with(oidcLogin())
                .with(csrf())
                .param("email", "alice@example.invalid"))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    void wrongCsrfIsRejectedEvenWithOidcPrincipal()
            throws Exception {

        mvc.perform(post("/account/email")
                .with(oidcLogin())
                .with(csrf().useInvalidToken())
                .param("email", "must-not-save@example.invalid"))
            .andExpect(status().isForbidden());
    }
}
~~~

**Phạm vi bằng chứng:** `oidcLogin()` tạo mock authentication. Nó **không thực hiện** authorization redirect, state comparison, nonce check, PKCE, JWT cryptographic validation, browser cookie SameSite hoặc session rotation. Test này minh họa **OAuth/OIDC principal và Spring CSRF token phải cùng được tôn trọng**.

Positive test còn cần fake controller/service và quyền đúng; phải kiểm DB/event nếu request bị từ chối.

### 20.2. Test authorize redirect có state nhưng không tự chứng minh callback

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OAuthAuthorizationRequestServletTests {

    @Autowired MockMvc mvc;

    @Test
    void authorizationRequestContainsState() throws Exception {
        MvcResult result = mvc.perform(
                get("/oauth2/authorization/corporate"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        String location =
            result.getResponse().getHeader("Location");

        assertNotNull(location);
        assertTrue(location.startsWith(
            "https://login.identity.example/"));
        assertTrue(location.contains("state="));
        assertTrue(location.contains("redirect_uri="));

        // Khi profile/AS hỗ trợ PKCE S256 và client đã bật:
        assertTrue(location.contains("code_challenge="));
        assertTrue(location.contains("code_challenge_method=S256"));
    }
}
~~~

**Điều kiện:** Test profile phải cấu hình provider authorize URI như ví dụ, PKCE được bật và không cần gọi production IdP. Nếu provider metadata cần network discovery khi boot, dùng test stub/fixture thay thế. Không log full `Location` chứa state/raw parameters.

**Mục tiêu test:** `state` và `code_challenge` được **gửi** đúng. Nó không chứng minh callback được nhận, verifier tương ứng được **đổi** thành token hay JWT OIDC nonce được xác minh.

### 20.3. Test state của session khác phải ở integration level

`MockMvc` có thể giữ một `MockHttpSession` từ GET initiation và thử callback với state sai; tuy nhiên nếu token endpoint chưa được stub, test không đi tới code exchange. Trường hợp mạnh nhất:

~~~text
Session A:
  GET /oauth2/authorization/corporate -> state A

Session B:
  GET /oauth2/authorization/corporate -> state B

Callback vào session B với state A và code của A:
  -> không tạo authenticated session.

Callback vào session A với state A nhưng code/verifier sai:
  -> token endpoint từ chối, không login.
~~~

Cần test IdP/backend stubs/authorization request store. **Đừng** tự set SecurityContext bằng `oidcLogin()` để gọi callback rồi kết luận state validation đã chạy.

## 21. WebTestClient: tách kiểm thử CSRF khỏi OIDC protocol trong WebFlux

### 21.1. MockOidcLogin không tự xác minh token thật

`WebTestClient` với `spring-security-test` có thể gắn một OIDC principal giả vào request, tương tự `MockMvc` trên Servlet.

Giả định ứng dụng có `GET /account/me` trả 200, `POST /account/email` trả 204 khi user được phép ghi:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockOidcLogin;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class OidcVsCsrfReactiveTests {

    @Autowired ApplicationContext context;

    WebTestClient client() {
        return WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .build();
    }

    @Test
    void authenticatedOidcUserCanRead() {
        client().mutateWith(mockOidcLogin())
            .get().uri("/account/me")
            .exchange()
            .expectStatus().isOk();
    }

    @Test
    void postWithoutCsrfFailsEvenAfterOidcLogin() {
        client().mutateWith(mockOidcLogin())
            .post().uri("/account/email")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"email\":\"must-not-save@example.invalid\"}")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void postWithCsrfCanProceedIfAuthorized() {
        client().mutateWith(mockOidcLogin())
            .mutateWith(csrf())
            .post().uri("/account/email")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"email\":\"alice@example.invalid\"}")
            .exchange()
            .expectStatus().isNoContent();
    }
}
~~~

Đây là **integration test minh họa security chain**, có giả định rõ về controller và fake/domain service. Nếu app trả redirect/JSON status khác, điều chỉnh assertion theo hợp đồng.

**Giới hạn:** `mockOidcLogin()` bỏ qua OIDC redirect, state/nonce/PKCE và cryptographic validation. Test browser cookie, WebSession persistence và issuer behavior cần lớp khác. Positive case vẫn phải qua business authorization; token CSRF hợp lệ không tự cấp quyền trên resource.

### 21.2. Correlation state trong WebSession

Một integration test thực có thể khởi tạo hai WebSession/cookie jars:

~~~text
WebSession A:
  GET /oauth2/authorization/corporate
    -> expected state SA, nonce NA, verifier VA
    -> 302 IdP

WebSession B:
  GET /oauth2/authorization/corporate
    -> expected state SB, nonce NB, verifier VB
    -> 302 IdP

Callback tới B với code thuộc A và state SA
    -> không khôi phục expected transaction trong B
    -> không tạo authenticated WebSession.

Callback A với state SA, code hợp lệ, nhưng ID token nonce NB
    -> từ chối token validation.
~~~

`WebTestClient` có thể gửi cookie thủ công, nhưng nó **không phải browser engine** và không thực thi SameSite như Chrome/Firefox/Safari. Mục tiêu ở đây là xác minh **repository/server-side correlation**.

### 21.3. Reactive integration còn phải kiểm concurrency

- Hai flows song song trong một WebSession không được ghép sai verifier/state/nonce; nếu repository chỉ hỗ trợ một pending request, fail closed và UX rõ.
- Callback đến node khác phải tìm đúng WebSession khi shared store/affinity được cấu hình.
- Pre-login session hết hạn không được chuyển thành login success.
- Custom reactive token exchange/authorization request repository không block Reactor event-loop.
- Logout thay/clear WebSession đúng; business POST thiếu CSRF vẫn bị từ chối.
- Các routes Browser và Bearer API được chọn đúng `SecurityWebFilterChain` theo `@Order`.

## 22. Integration test với Authorization Server thử nghiệm: nơi chứng minh PKCE/nonce thật

### 22.1. Tại sao không đủ nếu chỉ dùng mocks?

`oidcLogin()`, `mockOidcLogin()` và một mock JWT principal có thể bỏ qua chính những bước cần kiểm: **IdP phát code thật hay giả, AS có kiểm PKCE, client có lưu verifier, nonce có khớp, chữ ký/issuer/audience có được xác minh**.

Để test sâu, tạo **test issuer/Authorization Server** được kiểm soát (ví dụ container IdP hoặc test server có metadata, authorize, token, JWKS endpoints). Không dùng tài khoản hoặc client secret production.

### 22.2. Các thành phần test IdP

~~~text
Test authorization endpoint:
  /authorize
  - nhận client_id/redirect_uri/state/nonce/challenge
  - phát code một lần, TTL ngắn
  - lưu code -> registered client, redirect URI, challenge S256

Test token endpoint:
  /token
  - kiểm client authentication theo profile
  - kiểm code one-time, TTL, redirect_uri
  - kiểm code_verifier khớp challenge
  - phát ID token ký bằng test private key

Test JWKS/metadata:
  /.well-known/openid-configuration
  /jwks
  - test public JWKs, issuer identifier chính xác
~~~

Không bắt buộc tự viết Authorization Server nếu dùng một IdP test có khả năng tạo lỗi token/PKCE. Mục tiêu là **quan sát validation thật**, không chỉ stub response “200 OK” của token endpoint không kiểm verifier.

### 22.3. Trình tự kiểm thử tích hợp tối thiểu

1. GET `/oauth2/authorization/corporate` qua RP; lưu **session cookie**, trích URL authorize và `state`/`nonce`/`code_challenge` trong bộ test.
2. Test AS nhận authorization request, kiểm client/redirect/scopes/challenge và tạo code `K` ràng buộc challenge.
3. Callback `GET /login/oauth2/code/corporate?code=K&state=S` với **cùng session cookie**.
4. RP tải expected authorization request, kiểm state, gửi token request có verifier.
5. Test AS kiểm `S256(verifier) == challenge` và code/client/redirect, phát signed ID token có nonce kỳ vọng.
6. RP validate ID token signature/issuer/audience/time/nonce, tạo session login và redirect nội bộ.
7. GET protected route bằng session mới, xác minh user identity mapping đúng.
8. POST business route thiếu/sai CSRF, xác minh 403 và **không ghi dữ liệu**.
9. Lặp negative cases: state sai/session khác, verifier sai/missing, code reuse/expiry, nonce sai, issuer/audience/signature sai, account linking sai.
10. Kiểm sensitive-data redaction trong server/proxy logs.

### 22.4. Các phản hồi cần giả lập chính xác

| Chỉnh sửa trong test IdP | Lỗi kỳ vọng | Cơ chế được kiểm |
|---|---|---|
| State khác expected | Callback rejected | State/correlation |
| Code gắn với challenge A, verifier B | `invalid_grant` hoặc PKCE failure | PKCE server |
| Không có verifier khi code yêu cầu PKCE | Token endpoint reject | PKCE downgrade prevention |
| ID token nonce khác expected | OIDC authentication failure | Nonce |
| ID token ký bằng key không tin cậy | Authentication failure | Signature/JWK trust |
| ID token `iss` sai | Authentication failure | Issuer |
| ID token `aud` không có client ID | Authentication failure | Audience |
| ID token `exp` đã qua | Authentication failure | Time |
| Cùng code được đổi hai lần | Token endpoint reject lần sau | Code one-time |
| Đúng nonce nhưng wrong issuer | Authentication failure | Nonce không thay issuer |
| Đúng state nhưng wrong nonce | Authentication failure | State không thay nonce |

**Chú ý:** Một số OAuth security profiles cho phép PKCE làm CSRF protection khi được thực thi đầy đủ; test dựa vào BCP phải phản ánh đúng client/AS binding. Không xóa state khỏi Spring chỉ để test PKCE nếu chưa chứng minh client thiết kế theo profile đó.

### 22.5. Tại sao mock decoder chưa đủ?

Nếu token endpoint stub trả ID token giả và Spring OIDC decoder được mock luôn cho pass, bạn chỉ test request routing. Để chứng minh signature/JWKS/issuer, để RP dùng **validator thật** với test keys/JWKs và chủ động tạo tokens sai bằng test signer.

Không đưa private signing key test vào production config; không dùng production issuer để phát token “sai” khi test.

## 23. Browser E2E: kiểm cookie thật trên GET/POST callback

### 23.1. Chuẩn bị hai site HTTPS

Môi trường test minh họa:

~~~text
RP:          https://app.example.test
Test IdP:    https://login.other.test
API:         https://app.example.test/account
Cookie RP:   JSESSIONID=...; Secure; HttpOnly; SameSite=Lax; Path=/
~~~

Phải cấu hình hostname/certificate và hai **schemeful sites** khác nhau. Dùng test identity/secret, không chụp HAR chứa production code/state/tokens.

### 23.2. GET callback với Lax

1. Browser GET `/oauth2/authorization/corporate`, RP tạo expected state và session cookie.
2. Network hiển thị `302 Location` tới đúng test IdP, có state và PKCE challenge khi cấu hình.
3. Test IdP thực hiện login rồi trả **top-level GET callback** về RP.
4. Kiểm **request callback thực tế** có RP cookie hay không; `HttpOnly` không xuất hiện trong `document.cookie` là chuyện bình thường.
5. RP đối chiếu state/verifier/nonce và tạo session sau validation; session fixation protection có thể rotate session ID.
6. POST business với CSRF token mới hoạt động; POST thiếu/sai token bị 403, không có side effect.

### 23.3. Cross-site form_post với Lax

1. Đổi IdP sang `response_mode=form_post`.
2. Browser submit POST form tới RP callback từ site IdP.
3. RP cookie `SameSite=Lax` thường **không đi cùng POST**; xem DevTools excluded-cookie reason.
4. RP có thể báo `authorization_request_not_found` hoặc 403 nếu CSRF filter chặn.
5. **Fail closed**: không tự tạo expected state hoặc login user dựa vào code khi session mất.
6. Nếu bắt buộc hỗ trợ form_post, đánh giá `SameSite=None; Secure`/alternative correlation, handler POST và CSRF exception **chỉ cho endpoint protocol** với state/nonce/PKCE đầy đủ.
7. Chạy lại negative tests để chắc chắn response từ attacker không được chấp nhận.

### 23.4. Strict GET, cookie Path/Domain và sai redirect URI

Thử lần lượt:

- RP cookie `SameSite=Strict` và IdP cross-site top-level GET callback;
- Cookie `Path=/web` trong khi callback là `/login/oauth2/code/corporate`;
- RP khởi tạo ở `app.example.test` nhưng callback về `www.app.example.test` và cookie host-only;
- Redirect URI từ Spring bị tính thành `http://spring:8080` sau reverse proxy HTTPS;
- IdP callback với trailing slash hoặc path không khớp registration;
- Session hết hạn khi user làm MFA lâu;
- Callback tới node không truy cập được expected state repository.

**Mục tiêu:** RP phải fail closed khi correlation thất bại; thay đổi SameSite/proxy/path là để đưa cookie/trạng thái đúng **vào handler đã kiểm chứng**, không để bỏ handler.

### 23.5. Same-origin vs same-site

Một frontend `https://app.example.test` và API `https://api.example.test` là **cross-origin nhưng có thể same-site**. Cookie host-only cho `app.example.test` không tự gửi sang API host, kể cả SameSite cho phép; SPA `fetch` còn phải tuân theo CORS.

Đừng suy từ “cookie không gửi trong cross-origin fetch” thành “OAuth redirect state bị hỏng”; mỗi trường hợp cần nhìn **request method, top-level navigation, origin/site, Domain/Path/credentials**.

### 23.6. Browser privacy policy và iframe

Silent login qua iframe có thể bị 3rd-party cookie restrictions dù top-level OAuth code flow thành công. Browser state partitioning khác nhau theo vendor/version, nên test matrix phải ghi browser/profile/same-site cross-site conditions. Đừng nhầm silent SSO cookie failure với nonce mismatch hoặc PKCE failure.

## 24. Chẩn đoán lỗi: nhận biết đúng state, nonce, PKCE hay CSRF

| Hiện tượng | Tầng có khả năng xảy ra | Cách kiểm tra mà không lộ secrets |
|---|---|---|
| `authorization_request_not_found` trên callback | Authorization request repository/cookie | Browser có gửi session cookie đúng Domain/Path/SameSite/Secure/TTL không? |
| State parameter missing | OAuth callback | IdP redirect có state? Callback matcher có parse đúng? |
| State mismatch | OAuth callback correlation | Flow hiện hành, session, hai tab, replay/provider mapping |
| Callback từ session khác vẫn login | **Lỗ hổng response injection** | Audit custom repository, expected request binding, state validation |
| Callback không có state nhưng vẫn login | **Lỗi thiết kế nghiêm trọng** | Không cho fallback accept code không correlation |
| `invalid_grant` tại token endpoint | AS code exchange | Code hết hạn/reuse, client/redirect URI/verifier mismatch |
| Code challenge có nhưng không có verifier | PKCE client token request | Kiểm lưu/khôi phục verifier của đúng flow |
| Verifier không khớp challenge | PKCE AS check | Kiểm request correlation và công thức S256 |
| Có code challenge nhưng AS vẫn nhận verifier sai | **PKCE không được thực thi** | Kiểm AS configuration, fail closed; không tuyên bố PKCE là CSRF defense |
| ID token invalid nonce | OIDC token validation | Expected nonce, token claim, session/replay |
| JWT ký đúng nhưng ID token vẫn fail | OIDC issuer/audience/time/nonce | Kiểm `iss`, `aud`, `exp`, `nonce` và flow |
| ID token được chấp nhận dù issuer lạ | **Lỗi trust configuration** | Trusted issuer/ClientRegistration/JWKs và token validators |
| Browser login xong POST `/account` trả `403` | Spring CSRF hoặc business authorization | Submitted `_csrf` có khớp session token? Controller có chạy không? |
| Form cũ trước login trả `403` | CSRF/session lifecycle | Token/session có rotate sau authentication không? |
| Cookie RP không gửi ở form_post | Browser SameSite | Lax + cross-site POST, callback handler/exception/correlation |
| Cookie RP không gửi ở GET callback | Cookie Domain/Path/Secure/Strict/expiry | Xem request callback, không dùng `document.cookie` cho HttpOnly |
| State fail ngẫu nhiên sau MFA | Session timeout hoặc store eviction | Pre-login session TTL, storage/repository cleanup |
| State fail khi scale node | Session không chia sẻ | Shared store/affinity, session serializer, key rotation |
| Lỗi chỉ khi hai tab login đồng thời | Repository overwrite/concurrency | Multiple pending requests và replay behavior |
| `redirect_uri_mismatch` | RP/IdP/proxy | Trusted public scheme/host/path, registration |
| App trả `http://spring:8080` trong Location | Proxy forwarded headers | Forwarded strategy, trusted proxy, ingress rewrite |
| Callback trả 404/SPA HTML | HTTP firewall/matcher/proxy path | Public vs upstream URL và OAuth filter matching |
| Login của IdP A map thành IdP B | Account/issuer mix-up | Issuer+sub mapping, registration binding |
| OAuth callback nhận 403 CSRF | POST form callback | Có `form_post` được hỗ trợ và CSRF exception hẹp không? |
| Login GET callback bị chặn bởi CORS config | Chẩn đoán sai | Top-level navigation không cần browser CORS |
| Silent SSO iframe lỗi cookie | Browser third-party cookie policy | So top-level vs iframe, đừng sửa state/PKCE |
| Local logout xong login lại ngay | Phiên IdP còn hiệu lực | RP local logout khác RP-initiated/back-channel logout |
| `401` trên M2M API | Resource Server bearer token | Không phải `_csrf` của browser hoặc ID token nonce |
| Code/state xuất hiện trên proxy log | Data leakage | Query/header redaction, retention, access controls |
| Business POST thành công thiếu CSRF | **Lỗ hổng session endpoint** | Chain/order/`csrf.disable()`/ignore matcher và no-side-effects tests |
| Machine token xác thực web session | **Credential fallback** | Tách browser/M2M chain, test Cookie+Bearer precedence |

### 24.1. Quy trình 10 bước khi liên kết đăng nhập thất bại

~~~text
1. Đặt câu hỏi: lỗi ở GET authorize, GET/POST callback,
   token exchange, ID token validation hay POST nghiệp vụ?

2. Kiểm public URI/method và security chain được chọn
   (Servlet/Reactive, context path, proxy rewrite).

3. Kiểm redirect tới đúng IdP/ClientRegistration:
   client_id, redirect_uri, response_type, scope,
   code_challenge S256 khi yêu cầu.

4. Kiểm callback browser có session cookie RP không:
   SameSite, Domain, Path, Secure, cookie expiry, top-level vs POST.

5. Kiểm authorization request repository:
   expected state còn không, thuộc phiên/registration nào,
   có bị tab khác overwrite hoặc session store mất?

6. Kiểm state/callback correlation:
   missing/mismatch/replay phải fail closed.

7. Nếu đến token endpoint:
   code TTL/one-time, client auth, redirect_uri,
   PKCE verifier/challenge và chống downgrade.

8. Nếu token response về RP:
   ID token signature, trusted issuer, audience/client_id,
   nonce theo flow, timestamps, account linking.

9. Nếu login thành công nhưng POST business thất bại:
   session rotation, csrf repo/handler, submitted _csrf,
   route authorization và object-level permissions.

10. Chạy negative tests và redact logs:
    không log code/state/verifier/cookie/token/secret thô.
~~~

### 24.2. Sơ đồ quyết định nhanh

~~~mermaid
flowchart TD
    A[Đăng nhập hoặc POST gặp lỗi] --> B{Đang ở bước nào?}
    B -->|Authorize redirect| C[ClientRegistration, issuer, PKCE challenge, redirect URI]
    B -->|RP callback| D{Expected authorization request còn?}
    D -->|Không| E[Cookie SameSite/Path/Domain/TTL, repository, proxy, node]
    D -->|Có| F{State có đúng không?}
    F -->|Không| G[Từ chối, audit correlation/replay]
    F -->|Có| H[Token endpoint: code, PKCE verifier, client auth]
    H --> I{Token exchange pass?}
    I -->|Không| J[invalid_grant, code reuse, redirect URI, PKCE]
    I -->|Có| K[OIDC ID token: signature, iss, aud, nonce, time]
    B -->|POST nghiệp vụ| L[Session auth + CSRF token + authorization]
    K --> M{OIDC claims pass?}
    M -->|Không| N[Fail login, không tạo session]
    M -->|Có| O[Tạo browser session và áp CSRF cho POST]
~~~

**Không sửa ô H/J bằng việc bỏ ô F**, cũng không sửa ô L bằng việc thêm OAuth state vào POST. Bài toán nhiều lớp phải được phân tích theo request cụ thể.

## 25. Checklist kỹ thuật khi đưa OAuth/OIDC và CSRF lên production

| Hạng mục | Điều kiện chấp nhận |
|---|---|
| **Trusted IdPs** | RegistrationId/issuer allowlist, không nhận dynamic issuer tùy ý |
| **Redirect URI** | Public HTTPS URI chính xác, không wildcard/open redirect |
| **Authorization request** | State entropy cao, lưu có browser/session binding |
| **State validator** | Callback so expected state, one-time/replay protection |
| **Nonce** | Tạo/kiểm đúng theo OIDC flow/profile, không bỏ ID token validation |
| **PKCE** | Verifier ngẫu nhiên mỗi transaction, challenge S256 đúng |
| **PKCE AS enforcement** | Token endpoint từ chối missing/wrong verifier, không downgrade |
| **Code** | Short TTL, one-time, đúng client/redirect URI |
| **ID token trust** | Signature/JWKs, `iss`, `aud`, time, `nonce` checks |
| **Identity** | Map theo issuer+sub, account linking và role/tenant policy |
| **Cookie RP** | Secure, HttpOnly, SameSite, Domain/Path/expiry đúng callback |
| **GET callback** | Top-level GET thực có cookie session Lax khi cần |
| **form_post** | Nếu sử dụng, handler POST/cookie/CSRF exception hẹp được kiểm thử |
| **Session rotation** | Chống fixation, browser authenticated session được persist |
| **CSRF sau login** | Unsafe session-cookie endpoints phải kiểm `_csrf`/header |
| **CSRF token handler** | Thymeleaf/XOR/deferred/raw SPA token theo version |
| **Logout** | Local POST có CSRF; OIDC federated logout là flow riêng |
| **CORS** | Chỉ dùng cho browser cross-origin fetch, không sửa OAuth redirect |
| **CSP** | Header trên HTML browser thực, không dùng thay CSRF/token validation |
| **HSTS/TLS** | HTTPS từ browser tới RP/IdP, proxy headers đáng tin |
| **HTTP firewall** | Callback paths/methods không bị rewrite/normalization bypass |
| **Multiple nodes** | Shared session/repository hoặc affinity với fail-closed policy |
| **Multiple tabs** | Concurrent authorization requests xử lý rõ, không trộn verifier |
| **Multiple providers** | Không issuer mix-up, account mapping đúng |
| **M2M coexistence** | Bearer-only chain không chấp nhận browser cookie, ngược lại |
| **Logs** | Không ghi raw code/state/nonce/verifier/cookie/tokens/client secret |
| **Tests** | Matrix state/nonce/PKCE/CSRF positive+negative, no side effects |
| **Browser E2E** | SameSite top-level GET vs cross-site form POST qua HTTPS thật |
| **Change review** | Đổi IdP, redirect URI, SameSite, repo, session TTL hoặc Spring version phải regression |

### 25.1. Phiếu phân tích một request bảo mật

~~~text
Request type: authorize redirect / callback / token exchange / business POST
HTTP method:
Public RP URL:
Security chain:
ClientRegistration / issuer:
Browser origin/site:
Cookie RP Domain/Path/SameSite/Secure:
Expected authorization request exists? yes/no
State validation outcome: pass/fail/not-applicable
Nonce validation outcome: pass/fail/not-applicable
PKCE verifier outcome: pass/fail/not-applicable
Spring CSRF token outcome: pass/fail/not-applicable
Authenticated principal:
Business authorization outcome:
No-side-effects assertion:
Log redaction verified:
~~~

Không ghi **giá trị thật** của state/nonce/verifier/code/session/token vào phiếu hoặc ticket. Chỉ ghi loại lỗi, correlation ID được phép, timestamps và metadata đã ẩn bí mật.

### 25.2. Review khi thay authorization request repository

Trước khi thay `HttpSessionOAuth2AuthorizationRequestRepository` bằng cookie hoặc distributed store:

- Chứng minh cùng browser/request mới có thể lấy đúng expected state.
- Định nghĩa một hay nhiều pending auth requests, race/overwrite.
- TTL và cleanup khi user dừng ở IdP hoặc browser đóng.
- Xử lý nonce/verifier đúng transaction, không để JS/third parties đọc secret.
- Ký/mã hóa cookie correlation nếu cần chống sửa/đọc; Secure/HttpOnly/SameSite/Path đúng.
- Không tin state từ query như key duy nhất để cấp phép lấy dữ liệu flow của user khác.
- One-time consumption và replay protection ngay cả khi nhiều node cùng nhận callback.
- Tách hẳn CSRF token repository khỏi logic xác minh OAuth callback.

## 26. Bài tập thực hành có lời giải định hướng

### Bài tập 1 — Cùng một chữ “token” nhưng bốn vai trò

Một developer đề xuất:

~~~text
- Lưu OAuth state vào session.
- Dùng state làm CSRF hidden field của toàn bộ form.
- Gửi chính state làm PKCE code_verifier.
- Dùng state đó làm OIDC nonce.
~~~

**Câu hỏi:** Điều gì sai?

**Gợi ý đáp án:** Đây là tái sử dụng một giá trị cho các giao thức và vòng đời khác nhau. State ràng buộc callback, nonce ràng buộc ID token, PKCE verifier là secret của code exchange, CSRF token bảo vệ unsafe browser requests. Tái sử dụng có thể tạo coupling, leak, replay và phá token lifecycle. Hãy để mỗi cơ chế sinh/lưu/validate theo repository và flow của nó.

### Bài tập 2 — Callback của kẻ tấn công vào phiên Alice

Alice đã mở login tại RP và expected state `SA`. Attacker có code `KB` và state `SB` của flow khác, dụ Alice mở callback với `KB/SB`.

**Câu hỏi:** Check nào ngăn tình huống này trước khi tạo session?

**Gợi ý:** RP phải tìm expected authorization request theo session Alice, so state `SB` với `SA`, từ chối nếu không khớp. PKCE có thể là lớp bổ sung nếu code `KB` được ràng buộc với verifier khác, nhưng không được bỏ correlation validation khi client chưa thiết kế theo profile đảm bảo chống authorization CSRF.

### Bài tập 3 — Code bị lộ nhưng state vẫn đúng

Một authorization code bị lộ từ callback URL. Attacker không biết verifier, nhưng lấy được `code` và `state`.

**Câu hỏi:** Cơ chế nào giúp ngăn attacker lấy token từ code?

**Gợi ý:** PKCE nếu AS buộc code với challenge S256 và token endpoint yêu cầu verifier đúng. State không phải token endpoint credential; client authentication, exact redirect URI, code TTL/one-time và TLS cũng quan trọng.

### Bài tập 4 — ID token chữ ký hợp lệ nhưng nonce khác

Authorization request của RP dùng nonce `N_CURRENT`. ID token trả về có signature đúng, issuer đúng, audience đúng, nhưng nonce `N_PREVIOUS`.

**Gợi ý:** Khi nonce được dùng/đòi hỏi trong OIDC flow, client phải từ chối token vì không ràng buộc với request hiện tại. Đừng sửa bằng cách bỏ nonce validator hay lấy nonce từ chính token làm expected value.

### Bài tập 5 — OIDC login pass nhưng POST email thiếu CSRF

Alice đăng nhập OIDC với code/state/nonce/verifier hợp lệ. Sau đó một website khác khiến browser POST `/account/email` bằng session cookie nhưng không có `_csrf`.

**Gợi ý:** RP phải kiểm CSRF token riêng và từ chối request, không ghi dữ liệu. Những cơ chế login protocol đã hoàn tất không chứng minh nguồn gốc POST này.

### Bài tập 6 — Lax cookie và form_post

RP có HttpSession-backed authorization request repo, cookie `SameSite=Lax`. IdP dùng `response_mode=form_post` gửi cross-site POST callback. RP báo `authorization_request_not_found`.

**Gợi ý:** Browser có thể không gửi RP cookie trên cross-site POST, làm state/verifier/nonce không được tìm lại. Kiểm handler có hỗ trợ form_post, cookie policy, exact callback route và CSRF filter. Nếu cần, thiết kế `None; Secure` hoặc correlation khác với safeguards; **không** bỏ state/PKCE/nonce hoặc tắt CSRF toàn app.

### Bài tập 7 — BCP cho phép PKCE làm CSRF protection?

Một nhóm nói: “RFC 9700 cho PKCE thay state nên hãy xóa state khỏi tất cả OAuth clients.”

**Gợi ý:** Nhận định thiếu điều kiện. PKCE chỉ góp phần phòng authorization CSRF khi client bảo đảm AS hỗ trợ/ép PKCE, verifier theo transaction đúng binding, không downgrade và các checks khác vẫn áp. Không bỏ state ở Spring nếu không có thiết kế/bằng chứng tương đương; kể cả khi PKCE đáp ứng authorization CSRF, **không bỏ `_csrf` cho business POST**.

### Bài tập 8 — Multi-tab login trộn verifier

User mở login A (state SA, verifier VA), rồi login B (state SB, verifier VB). Callback A tới sau khi repository chỉ còn B; developer lấy VB đổi code A.

**Gợi ý:** Token endpoint phải từ chối PKCE mismatch. Sửa đúng bằng repository hỗ trợ pending transactions hoặc UX fail closed; không dùng một verifier toàn cục, không bỏ PKCE khi có hai tab.

### Bài tập 9 — Issuer trùng subject

IdP A và IdP B đều phát `sub="123"` nhưng đại diện hai user khác nhau. RP login qua IdP B rồi liên kết vào account của IdP A.

**Gợi ý:** Lỗi account mapping/issuer confusion, không phải `state` hay `_csrf`. Sử dụng issuer+sub và account linking policy, kiểm registration/issuer binding.

### Bài tập 10 — Form POST đã có CSRF token nhưng controller vẫn không được phép

Alice có CSRF token hợp lệ và session login đúng, gửi `POST /projects/99/delete`. Project 99 thuộc Bob.

**Gợi ý:** CSRF chứng minh request phù hợp cơ chế chống giả mạo, **không cấp object-level permission**. Controller/service phải kiểm principal/tenant/resource ACL. Kỳ vọng 403/404 theo policy và không side effect.

### Bài tập 11 — CORS wildcard để sửa callback

Một OIDC callback GET lỗi do cookie `Path=/app` trong khi callback ở `/login/oauth2/code/corporate`. Nhóm triển khai mở CORS wildcard ở mọi route.

**Gợi ý:** CORS không điều khiển top-level navigation hoặc cookie Path. Sửa cookie Path/public callback và repository; wildcard credentialed CORS có thể gây sai chính sách API.

### Bài tập 12 — Viết negative tests có ý nghĩa

Thiết kế ba test:

1. Callback đúng code nhưng **sai state**.
2. Callback đúng state nhưng **ID token nonce sai**.
3. Business POST có OIDC session nhưng **CSRF token sai**.

**Tiêu chí đạt:** Test 1 không tạo authenticated session; test 2 không tạo authenticated session dù code exchange đã xảy ra; test 3 trả 403/no side effects. Cần chọn đúng lớp test: callback/IdP integration cho (1)–(2), MockMvc/WebTestClient + business service fixture cho (3).

## 27. Câu hỏi tự đánh giá

**Câu 1.** OAuth state có bảo vệ POST cập nhật hồ sơ sau login OIDC không?

**Đáp án:** Không tự động. State liên kết authorization response với request của OAuth flow; POST dựa vào browser session cookie cần Spring CSRF token và business authorization.

**Câu 2.** CSRF token của Spring có được IdP phát trong ID token không?

**Đáp án:** Không. Nó thuộc RP `CsrfTokenRepository`, được gửi bởi form/header tới Spring `CsrfFilter`/`CsrfWebFilter`; không cần IdP phát.

**Câu 3.** OIDC nonce được kiểm khi nào?

**Đáp án:** Khi RP xác minh ID token theo OIDC flow/profile đã gửi/yêu cầu nonce, bên cạnh signature, issuer, audience và time claims. Nó không được so với `_csrf` form field.

**Câu 4.** PKCE verifier được gửi đến authorize endpoint hay token endpoint?

**Đáp án:** Verifier giữ ở client rồi gửi **token endpoint** khi đổi code. Authorize endpoint nhận `code_challenge` (thường dẫn xuất S256) và method.

**Câu 5.** Nếu attacker biết authorization code nhưng không biết verifier, cơ chế gì giúp chặn đổi code?

**Đáp án:** PKCE khi Authorization Server gắn challenge vào code và buộc verifier đúng tại token endpoint. Code TTL/one-time, client/redirect matching và TLS vẫn quan trọng.

**Câu 6.** `state`, `nonce`, `code_verifier` có nhất thiết là một chuỗi giống nhau vì đều ngẫu nhiên không?

**Đáp án:** Không. Chúng có mục tiêu, vị trí gửi, nơi kiểm và vòng đời khác nhau, phải được quản lý độc lập theo flow.

**Câu 7.** PKCE có thể cung cấp protection chống authorization CSRF theo RFC 9700 không?

**Đáp án:** Có, **trong điều kiện** client bảo đảm AS hỗ trợ/ép PKCE, verifier được ràng buộc đúng authorization transaction và không downgrade. Không biến phát biểu đó thành lý do bỏ CSRF token của các browser business POSTs.

**Câu 8.** Một callback có state đúng nhưng ID token sai audience có hợp lệ không?

**Đáp án:** Không. State đúng không thay ID token signature/issuer/audience validation. RP phải từ chối token không dành cho client.

**Câu 9.** Một ID token được ký đúng và nonce đúng nhưng issuer không được tin cậy thì sao?

**Đáp án:** Phải từ chối. Nonce chỉ là ràng buộc theo authentication transaction, không biến một issuer lạ thành đáng tin cậy.

**Câu 10.** Có nên dùng session ID làm OAuth state hoặc CSRF token không?

**Đáp án:** Không. Session ID là credential và không nên bị phơi qua URL/form; state/CSRF token phải được sinh và ràng buộc đúng mục đích của chúng.

**Câu 11.** Vì sao `SameSite=Lax` thường hợp với top-level GET OAuth callback nhưng không hợp form_post cross-site?

**Đáp án:** Browser thường gửi Lax cookie cho top-level cross-site safe GET, nhưng không gửi trên cross-site POST. Nếu state/verifier/nonce nằm trong session, cookie vắng khiến correlation thất bại.

**Câu 12.** Có thể sửa `authorization_request_not_found` bằng cách bỏ state validation không?

**Đáp án:** Không. Đó có thể tạo login CSRF/response injection. Phải kiểm cookie, session store, expiry, client registration, callback matcher và proxy.

**Câu 13.** `oidcLogin()` trong MockMvc chứng minh PKCE và nonce validation của IdP thật chưa?

**Đáp án:** Chưa. Nó mock authenticated principal; cần test IdP/AS/token endpoint/decoder thật để chứng minh PKCE, signature/nonce/issuer/audience.

**Câu 14.** WebTestClient có tự áp cookie SameSite như browser thật không?

**Đáp án:** Không. Có thể gửi cookie tùy ý và kiểm server-side; cần browser engine thực để chứng minh GET/POST cross-site có gửi cookie hay không.

**Câu 15.** CORS có quyết định IdP được top-level redirect tới RP callback không?

**Đáp án:** Không. Redirect navigation không phải XHR/fetch. CORS dùng cho JavaScript cross-origin requests; callback phải được bảo vệ bằng state/protocol checks và cookie correlation.

**Câu 16.** CSRF token hợp lệ có nghĩa user được xóa tài nguyên của tenant khác không?

**Đáp án:** Không. CSRF token bảo vệ request origin/intent trong bối cảnh cookie; object-level authorization phải kiểm riêng.

**Câu 17.** Nếu code K có challenge PKCE nhưng token endpoint vẫn chấp nhận verifier sai, có thể kết luận client được PKCE bảo vệ không?

**Đáp án:** Không. Authorization Server phải **thực thi** PKCE và chống downgrade; chỉ có challenge trên URL không đủ.

**Câu 18.** Trong multi-provider OIDC login, sao không map user theo `sub` một mình?

**Đáp án:** `sub` được định danh trong phạm vi issuer; hai issuers có thể dùng cùng subject string. Cần issuer+subject và account linking policy.

**Câu 19.** `SessionCreationPolicy.STATELESS` có luôn phù hợp với browser OAuth2 Login không?

**Đáp án:** Không. Session-backed authorization request repository và browser SecurityContext cần storage phù hợp; stateless tùy tiện có thể làm mất state/nonce/verifier và phiên sau login. Chỉ dùng stateless theo kiến trúc rõ.

**Câu 20.** Làm sao phân biệt `invalid_grant` của token endpoint và `403` CSRF trên business POST?

**Đáp án:** `invalid_grant` thuộc authorization code exchange/PKCE/client/redirect ở AS. `403` CSRF thuộc RP filter xử lý POST dùng cookie. Xác định request/stage trước khi sửa.

## Kết luận

Trong hệ thống Spring Security tích hợp OAuth2/OIDC, **CSRF token, `state`, `nonce` và PKCE không phải bốn tên gọi của cùng một secret**:

- **Spring CSRF token** bảo vệ các unsafe requests của ứng dụng khi browser tự gửi session cookie.
- **OAuth `state`** liên kết authorization callback với request/client/browser context đã khởi tạo và góp phần chống login CSRF/response injection.
- **OIDC `nonce`** ràng buộc ID token với authentication request theo OIDC flow và giảm replay/substitution; nó không thay signature/issuer/audience validation.
- **PKCE `code_verifier/code_challenge`** gắn authorization code với verifier của client, hạn chế code interception/substitution; **có thể** góp phần chống authorization CSRF theo các điều kiện nghiêm ngặt của OAuth Security BCP, nhưng **không thay** CSRF token cho POST nghiệp vụ.

Trên **Servlet/Spring MVC**, OAuth2 authorization request repository, `HttpSecurity.oauth2Login`, `HttpSession` và `CsrfTokenRepository/CsrfFilter` phục vụ những mục tiêu khác nhau. Trên **Reactive/WebFlux**, cơ chế tương ứng sử dụng `ServerHttpSecurity.oauth2Login`, `WebSession`, reactive authorization request repository và `CsrfWebFilter`. Cùng tồn tại trong một session không đồng nghĩa dữ liệu có thể dùng thay nhau.

Browser **SameSite**, redirect URI, TLS/HSTS, CSP, CORS, HTTP firewall, proxy, state repository và security chains quyết định token có được gửi/đối chiếu đúng vị trí không. Callback GET với cookie Lax, `form_post` cross-site, multi-tab, multi-node, logout và M2M bearer-only APIs phải được kiểm theo threat model riêng.

**Cách chứng minh bài học đúng là kiểm thử những thất bại bắt buộc:** state sai không login; nonce sai không login; PKCE verifier sai không đổi code; POST browser thiếu `_csrf` không ghi dữ liệu; issuer/audience sai không được nhận; cookie/session mất không cho phép bỏ correlation. Đó là nguyên tắc tích hợp **SPRING_SECURITY_HTTP_PROTECTION**: mỗi lớp bảo vệ làm đúng việc của mình và **không che lỗ hổng của lớp khác bằng cách vô hiệu hóa kiểm chứng**.

## Tài liệu tham khảo

- [Spring Security — OAuth 2.0 Login Core (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html): `oauth2Login` và OIDC client.
- [Spring Security — Advanced OAuth 2.0 Login (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html): authorization request resolver, request repository và endpoints.
- [Spring Security — OAuth 2.0 Login (Reactive)](https://docs.spring.io/spring-security/reference/reactive/oauth2/login/core.html): Reactive OAuth2 Login/WebSession.
- [Spring Security — Servlet CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): repositories, masked token, SPA, login/logout.
- [Spring Security — Reactive CSRF](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html): `CsrfWebFilter` và WebSession.
- [Spring Security — OAuth2 Client PKCE (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorization-grants.html): PKCE với Authorization Code clients, cấu hình client.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): authorization code, `state`, redirect URI.
- [RFC 7636 — Proof Key for Code Exchange by OAuth Public Clients](https://www.rfc-editor.org/rfc/rfc7636): verifier/challenge, entropy, `S256`.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): CSRF protection và điều kiện PKCE, redirect URI và mix-up defenses.
- [RFC 9207 — Authorization Server Issuer Identification](https://www.rfc-editor.org/rfc/rfc9207): bảo vệ chống issuer mix-up.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID token, nonce, authorization code flow và token validation.
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html): issuer metadata/JWKs discovery.
- [OWASP — OAuth2 Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html): state, PKCE, redirect và OAuth client security.
- [OWASP — Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): token patterns, SameSite và defense in depth.
- [MDN — Set-Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie): `SameSite`, `Secure`, `HttpOnly`, `Domain` và `Path`.
- [MDN — CORS](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS): browser cross-origin fetch và preflight, khác top-level redirect.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): safe methods và response status semantics.
