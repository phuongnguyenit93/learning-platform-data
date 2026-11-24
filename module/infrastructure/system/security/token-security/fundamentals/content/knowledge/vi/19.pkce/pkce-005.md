# PKCE request and token exchange — Yêu cầu PKCE và đổi authorization code lấy token

## 1. PKCE bảo vệ điều gì trong OAuth 2.0?

Trong module `SECURITY_TOKEN_SECURITY_FUNDAMENTALS`, ứng dụng có thể sử dụng OAuth 2.0 để lấy **access token** dành cho API, và OpenID Connect (OIDC) để xác thực người dùng. **Proof Key for Code Exchange (PKCE)** theo RFC 7636 bổ sung một bằng chứng cho **Authorization Code grant**: bên đổi authorization code ở token endpoint phải biết một giá trị bí mật ngẫu nhiên đã được ràng buộc từ lúc bắt đầu authorization request.

Một authorization code được trả về qua trình duyệt, redirect URI hoặc cơ chế chuyển tiếp giữa ứng dụng và hệ điều hành. Nếu kẻ tấn công lấy được code trước khi client thật đổi code, và token endpoint chỉ yêu cầu **code**, kẻ tấn công có thể tìm cách đổi code thành access token/refresh token. Với PKCE đúng, code bị lấy cắp **một mình** không đủ: AS kiểm tra thêm `code_verifier` mà client hợp lệ đã tạo và giữ từ lúc khởi tạo giao dịch.

Ví dụ ứng dụng `sales-dashboard` dùng browser để yêu cầu scope `orders.read` cho `orders-api` từ AS `https://auth.example.test`:

~~~text
Client tạo code_verifier ngẫu nhiên (giữ bí mật).
Client tính code_challenge = BASE64URL(SHA256(code_verifier)).
Client gửi code_challenge trong /authorize.
AS ràng buộc code_challenge với authorization code.
Client nhận code qua redirect.
Client POST code + code_verifier tới /token.
AS tính lại challenge và so khớp, chỉ sau đó mới cấp token.
~~~

**PKCE không biến authorization code hoặc access token thành không thể bị đánh cắp.** Nó giảm khả năng **đổi authorization code bị chặn**; bearer access token đã cấp vẫn có thể bị phát lại nếu lộ. Nó cũng không tự thay thế xác minh redirect URI, client authentication, `state`, OIDC `nonce`, issuer, audience, scope, thời hạn hay authorization tại resource server.

> **Quy tắc trung tâm:** **`code_challenge` đi trong authorization request; `code_verifier` chỉ được gửi tới token endpoint qua kết nối bảo mật khi đổi code.** AS phải ràng buộc hai giá trị với **cùng một authorization code** và từ chối mọi lần đổi không thỏa ràng buộc.

### Mục tiêu sau bài học

1. Hiểu cấu trúc `code_verifier`, `code_challenge` và `code_challenge_method=S256`.
2. Viết đúng hai HTTP request: **authorization request** và **token request đổi code**.
3. Giải thích cách AS lưu challenge theo transaction, kiểm tra verifier và áp single-use code.
4. Phân biệt PKCE với `state`, OIDC `nonce`, client secret, redirect URI và RFC 8693 Token Exchange.
5. Triển khai bằng Java/Spring Security và kiểm thử các lỗi bắt code, mismatch, downgrade, concurrency.
6. Hiểu ranh giới tiếp tục bảo vệ JWT/opaque access token và refresh token sau khi PKCE thành công.

## 2. Các vai trò và thuật ngữ trong luồng PKCE

PKCE xuất hiện trong OAuth **Authorization Code** flow, với các vai trò:

| Vai trò/giá trị | Chức năng | Ví dụ |
| --- | --- | --- |
| **Resource Owner** | Chủ thể có quyền ủy quyền truy cập tài nguyên | Alice |
| **Client** | Ứng dụng xin quyền, khởi tạo PKCE | `sales-dashboard` |
| **Authorization Server (AS)** | Tiếp nhận authorization request, cấp code và token | `auth.example.test` |
| **Resource Server (RS)** | API kiểm tra access token và quyết định quyền | `orders-api` |
| **`code_verifier`** | Bí mật ngẫu nhiên theo mỗi authorization transaction, giữ phía client | Chuỗi 43–128 ký tự unreserved |
| **`code_challenge`** | Dấu cam kết công khai dẫn xuất từ verifier, gửi tới AS | Base64url của SHA-256(verifier) |
| **`code_challenge_method`** | Thuật toán AS dùng kiểm tra verifier | `S256` |
| **`authorization_code`** | Credential thời gian ngắn, dùng một lần để đổi token | `CODE-EXAMPLE` |
| **`state`** | Ràng buộc authorization response với transaction/CSRF defense | Random state của phiên |
| **`nonce` (OIDC)** | Ràng buộc ID token với authentication request trong những profile áp dụng | Random nonce |

**Public client** như SPA, mobile, desktop không thể bảo vệ client secret nhúng trong mã được phân phối cho người dùng. PKCE giúp public client sử dụng code flow mà không dựa vào bí mật chung. **Confidential client** như backend/BFF có thể giữ client credential và vẫn nên sử dụng PKCE; hai cơ chế giải quyết các rủi ro khác nhau.

### 2.1. PKCE gắn với một giao dịch, không gắn chung với ứng dụng

Alice mở hai tab đăng nhập vào cùng client:

~~~text
Tab A: state-A, verifier-A, challenge-A
Tab B: state-B, verifier-B, challenge-B
~~~

Mỗi callback phải lấy lại **đúng verifier** theo authorization transaction của chính nó. Một `code_verifier` cố định cho cả ứng dụng, tất cả user hoặc toàn bộ quá trình chạy sẽ phá mục tiêu bảo vệ code interception. Một client có hàng nghìn người dùng không được dùng một verifier chung cho mọi login.

### 2.2. PKCE khác mật khẩu và chữ ký JWT

`code_verifier` là bằng chứng cho **việc đổi một authorization code**, không phải mật khẩu của user, client secret, private key ký JWT hay refresh token. AS dùng code/verifier để quyết định cấp token; RS sau đó không yêu cầu `code_verifier` khi client gọi API. RS xác minh **access token** theo JWT/JWKS hoặc opaque introspection, rồi kiểm tra `iss`, `aud`, `exp`, `scope` và quyền nghiệp vụ.

## 3. Sinh code_verifier và code_challenge đúng RFC 7636

### 3.1. Quy tắc cú pháp và entropy

RFC 7636 quy định `code_verifier` là chuỗi có độ dài **43–128 ký tự** trong tập **unreserved** của URI:

~~~text
ALPHA / DIGIT / "-" / "." / "_" / "~"
~~~

Verifier cần có entropy cao và được tạo bằng **cryptographically secure random number generator (CSPRNG)**. Cách được RFC khuyến nghị là sinh **32 octet ngẫu nhiên** (256 bit) rồi mã hóa **Base64url không padding**, thu được **43 ký tự**. Đừng dùng timestamp, UUID đơn lẻ, tên user, một bộ đếm, `Math.random()` hoặc hash của một giá trị dễ đoán như session ID.

Ví dụ toán học:

\[
\text{code\_verifier}=\operatorname{BASE64URL\_NO\_PAD}(\operatorname{CSPRNG}(32\ \text{bytes}))
\]

**Độ dài 43 ký tự không tự chứng minh độ ngẫu nhiên**. Một chuỗi 43 chữ “A” thỏa số ký tự nhưng không phải verifier an toàn. Dùng CSPRNG thực sự; không giới hạn/verifier entropy bằng cách chỉ chọn trong vài ký tự.

### 3.2. Phương pháp `S256`

Với `code_challenge_method=S256`:

\[
\text{code\_challenge}=\operatorname{BASE64URL\_NO\_PAD}(
\operatorname{SHA256}(\operatorname{ASCII}(\text{code\_verifier})))
\]

Các bước:

1. Biểu diễn verifier thành **ASCII octets** của chuỗi unreserved.
2. Tính **SHA-256** trên đúng những bytes đó.
3. Mã hóa digest bằng Base64 **URL-safe**: `+` thành `-` và `/` thành `_`; **bỏ padding `=`**.
4. Gửi challenge và method `S256` đến authorization endpoint. **Không gửi verifier trong URL authorization.**

Code challenge S256 từ SHA-256 (32 bytes) thường có **43 ký tự** Base64url không padding.

### 3.3. Test vector của RFC 7636

RFC 7636 Appendix B có một cặp giá trị dùng để kiểm tra cách mã hóa:

~~~text
code_verifier:
dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk

code_challenge_method:
S256

code_challenge:
E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM
~~~

Đây là **test vector công khai** và **không được dùng làm verifier thật**. Nếu chương trình không tạo ra challenge tương ứng với verifier trên, phải kiểm tra ASCII encoding, SHA-256, Base64url và việc loại bỏ padding.

### 3.4. `plain` và downgrade

RFC 7636 định nghĩa cả `plain`, tức `code_challenge=code_verifier`, nhưng `plain` để lộ giá trị verifier qua authorization request. Đối với triển khai mới, dùng **`S256`** và không âm thầm fallback sang `plain` hay bỏ PKCE khi AS báo không hỗ trợ. Nếu một client có thể sử dụng `S256`, việc cho attacker hạ method làm giảm mục tiêu bảo vệ.

AS phải lưu **method đã được chấp nhận cùng challenge**. Không tin method do client tùy ý khai báo **khi đổi code** để làm thay đổi cách kiểm tra; token endpoint phải áp lại method gắn với authorization code ngay lúc phát hành.

### 3.5. Trường hợp input không hợp lệ

AS/client phải từ chối:

- Verifier dưới 43 hoặc trên 128 ký tự theo RFC 7636.
- Ký tự ngoài tập unreserved; ví dụ khoảng trắng, dấu `+`, `/`, `=` padding.
- Verifier bị URL decode/form decode sai, có Unicode hoặc line breaks.
- Challenge không đúng cú pháp/độ dài theo method, hoặc method không được phép.
- Token request thiếu verifier trong khi code gắn PKCE.
- Attempt dùng `plain` đối với client/AS policy yêu cầu `S256`.

Không dùng một string sanitizer “sửa” verifier sai định dạng thành giá trị khác; thay đổi verifier làm challenge không khớp. Hãy **sinh lại authorization transaction** khi dữ liệu verifier đã lỗi.

## 4. Toàn bộ chuỗi request: /authorize → redirect → /token

### 4.1. Sơ đồ thời gian

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Alice / Browser
    participant C as OAuth Client
    participant AS as Authorization Server
    participant RS as orders-api
    C->>C: Sinh state, code_verifier, code_challenge=S256
    C->>U: Điều hướng tới authorization endpoint
    U->>AS: GET /authorize: client_id, redirect_uri, state, challenge, S256
    AS->>AS: Kiểm tra client, redirect, scope/resource và policy
    AS->>U: Authentication, consent nếu cần
    U-->>AS: Hoàn tất login/consent
    AS->>AS: Sinh authorization code + gắn challenge/method/client/redirect
    AS-->>U: 302 về registered redirect_uri?code=...&state=...
    U->>C: Callback với code + state
    C->>C: So khớp state và lấy đúng verifier cho transaction
    C->>AS: POST /token: code + code_verifier + client auth khi cần
    AS->>AS: Verify code single-use, client, redirect, S256, grant
    AS-->>C: access_token (+ id_token/refresh_token nếu được cấp)
    C->>RS: Authorization: Bearer access_token
    RS->>RS: Validate AT, iss, aud, exp, scope, domain ACL
    RS-->>C: Tài nguyên cho phép
~~~

Điểm khác biệt quan trọng: **authorization request qua front-channel browser chứa challenge**, còn **token request** gửi verifier qua kênh HTTPS từ client đến AS. Authorization code bị rò từ redirect không đủ cho attacker khi PKCE ràng buộc đúng.

### 4.2. Bước A: sinh transaction

Client chuẩn bị:

~~~text
expected_issuer = https://auth.example.test
client_id       = sales-dashboard
redirect_uri    = https://client.example.test/login/oauth2/code/company
requested_scope = openid orders.read
requested_aud   = orders-api (nếu AS hỗ trợ resource indicator)
state           = random, bind với browser/session transaction
code_verifier   = random unreserved, 43–128 ký tự
code_challenge  = BASE64URL(SHA256(ASCII(code_verifier)))
code_challenge_method = S256
~~~

**Lưu transaction bí mật tại nơi phù hợp với client type**:

- Backend/BFF: session store server-side, chỉ browser nhận session cookie.
- SPA: transaction cache ngắn hạn phân vùng theo `state`, chống XSS và tránh trộn tabs; không phát tán verifier vào analytics/log.
- Native: trạng thái tạm bảo vệ trong app memory/secure storage nếu phải vượt app lifecycle, với OS redirect binding.

Không ghi `code_verifier` vào URL authorization, query string của callback, local analytics, proxy access logs hoặc error message.

### 4.3. Bước B: authorization request có challenge

Request minh họa, trong thực tế các tham số phải được URL-encode:

~~~http
GET /oauth2/authorize?response_type=code&client_id=sales-dashboard&redirect_uri=https%3A%2F%2Fclient.example.test%2Flogin%2Foauth2%2Fcode%2Fcompany&scope=openid%20orders.read&state=<opaque-state>&code_challenge=E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM&code_challenge_method=S256 HTTP/1.1
Host: auth.example.test
~~~

AS cần xác minh:

1. Client ID được đăng ký và **`response_type=code`** được phép.
2. `redirect_uri` khớp URI đã đăng ký theo policy, không phải open redirect.
3. Scope/resource request hợp lệ với client và quyền của RO/consent.
4. `code_challenge` có định dạng đúng, `code_challenge_method=S256` được hỗ trợ/yêu cầu.
5. Giao dịch được ràng buộc với AS issuer và trạng thái user authentication/authorization cần thiết.

AS **không phải tin rằng client sở hữu verifier chỉ vì thấy challenge**: sự chứng minh diễn ra **sau đó**, tại token endpoint, khi client trình verifier.

### 4.4. Bước C: redirect response với authorization code

Sau khi user hoàn tất authentication/consent nếu áp dụng, AS trả callback:

~~~http
HTTP/1.1 302 Found
Location: https://client.example.test/login/oauth2/code/company?code=<one-time-authorization-code>&state=<opaque-state>
Cache-Control: no-store
~~~

Client kiểm tra `state`, issuer/transaction binding và điều kiện callback. Authorization code cần được bảo vệ khỏi log, browser analytics và referrer leakage; redirect không nên đưa code qua open redirect hoặc script bên thứ ba. PKCE **giảm hậu quả code bị chặn** nhưng không hợp thức hóa việc để code bị rò có chủ đích.

### 4.5. Bước D: token request mang code + verifier

Một **public client** như SPA/native gửi request form:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.test
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&client_id=sales-dashboard&code=<one-time-authorization-code>&redirect_uri=https%3A%2F%2Fclient.example.test%2Flogin%2Foauth2%2Fcode%2Fcompany&code_verifier=dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk
~~~

Trong request thật, public client không được coi một static client secret nằm trong bundle là bí mật. Với **confidential client**, token request còn phải dùng **client authentication** đã đăng ký (ví dụ `client_secret_basic`, private-key JWT hoặc mTLS) mà không đặt secret vào URL. Khi authorization request có `redirect_uri`, token endpoint kiểm tra giá trị tương ứng theo quy tắc OAuth; đừng thay nó bằng một redirect URI tự chọn khi đổi code.

**Chỉ gửi verifier tại token endpoint của AS tin cậy qua TLS với certificate/hostname validation.** Đừng đưa verifier vào authorization request, HTTP Referer, header tùy ý gửi xuống RS hay một endpoint nhận token khác.

### 4.6. Bước E: AS kiểm tra PKCE trước khi phát hành

Về mặt logic, AS làm:

~~~text
stored = lookupAuthorizationCode(code)
require stored is present, not expired, not consumed
require token request client matches stored client binding
require redirect URI binding matches authorization request
require code_verifier present and valid syntax

if stored.method == "S256":
    expected = BASE64URL_NO_PADDING(SHA256(ASCII(code_verifier)))
else:
    reject unless a separately-approved method is supported

require constantTimeEquals(expected, stored.code_challenge)
atomically consume authorization code
issue access token with approved aud/scope/TTL
issue id_token and/or refresh_token only if grant + policy allow
~~~

Đây là **pseudo-code mô tả bảo đảm**, không thay thế OAuth library/transaction management. Việc kiểm tra code và **đánh dấu code đã dùng** phải chống race trên mọi node AS; hai request cùng code không được cùng mint token. Nếu verifier sai, AS phải từ chối request, không cấp AT/RT.

### 4.7. Bước F: kết quả token response

Ví dụ AS trả:

~~~json
{
  "access_token": "<access-token-for-orders-api>",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "orders.read"
}
~~~

Với OIDC, có thể thêm `id_token`; theo grant và chính sách AS, có thể có `refresh_token`. **`code_verifier` không được biến thành một claim trong access token để resource server tự kiểm tra.** PKCE là ràng buộc **authorization code redemption tại AS**, không phải cơ chế xác minh bearer token ở RS.

Sau khi nhận token, client phải lưu AT/RT theo client type và gửi AT tới **đúng resource**. RS kiểm tra issuer, chữ ký JWT hoặc introspection opaque, audience, thời hạn, scope, subject/tenant/ACL; PKCE đúng không làm tất cả các điều kiện ấy tự đúng.

## 5. “Token exchange” ở đây không đồng nghĩa RFC 8693

Trong cụm **PKCE request and token exchange**, chữ *exchange* chủ yếu chỉ bước **đổi authorization code lấy token** bằng `grant_type=authorization_code`. OAuth 2.0 còn có một grant riêng gọi là **Token Exchange** theo RFC 8693, dùng để xin token mới từ một subject/actor token trong các tình huống delegation giữa service.

| Tiêu chí | Đổi authorization code với PKCE | RFC 8693 Token Exchange |
| --- | --- | --- |
| Grant type | `authorization_code` | `urn:ietf:params:oauth:grant-type:token-exchange` |
| Credential gốc | Authorization code, kèm `code_verifier` | `subject_token`, có thể có `actor_token` theo profile |
| Vì sao dùng? | Hoàn tất user authorization flow để lấy AT | Chuyển/ngữ cảnh hóa quyền sang resource/actor mới có kiểm soát |
| Thông số đặc trưng | `code`, `redirect_uri`, `code_verifier` | `subject_token`, `subject_token_type`, `resource`/`audience`, requested token type |
| Quy tắc an toàn | PKCE S256, redirect/client binding, code one-time | AS xác minh subject/actor, client, quyền, audience và delegated scope |
| Dùng cho public SPA/native login? | Có, đây là trường hợp điển hình | Không thay thế bước login/code flow |
| Có thể tự nâng quyền? | Không | Cũng không; cần explicit AS policy |

Ví dụ *token exchange* RFC 8693 (khác yêu cầu PKCE):

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.test
Authorization: Basic <service-client-authentication>
Content-Type: application/x-www-form-urlencoded

grant_type=urn:ietf:params:oauth:grant-type:token-exchange&subject_token=<access-token-for-orders>&subject_token_type=urn:ietf:params:oauth:token-type:access_token&resource=https%3A%2F%2Fpayments.example.test%2F&scope=payments.read
~~~

Request này không có `code_verifier` vì **không đổi authorization code**. Token Exchange không bắt buộc là tính năng sẵn có ở mọi AS. Khi service A gọi service B thay user, hãy cấp token **audience B** và đánh giá subject/actor theo RFC 8693/nhà cung cấp, không tự chuyển token `aud=A` sang B và bỏ qua audience validation.

## 6. Phân tích tấn công: code interception và PKCE protection

### 6.1. Khi không có PKCE

Giả sử native app dùng redirect scheme `com.example.sales:/oauth2redirect`. Ứng dụng độc hại trên cùng thiết bị giành được callback:

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Alice
    participant C as Legitimate Native App
    participant AS as Authorization Server
    participant X as App độc hại
    C->>AS: Authorization request không có PKCE
    AS->>U: Authentication / consent
    AS-->>X: OS chuyển nhầm callback chứa CODE-1
    X->>AS: POST /token: code=CODE-1
    AS-->>X: Access token nếu grant/binding khác bị bypass
    Note over X,AS: Không có PKCE, code bị lấy cắp có thể là điều kiện đủ
~~~

Một số code flows có **client authentication** và những ràng buộc khác vẫn có thể ngăn tấn công trong hoàn cảnh cụ thể. Mục tiêu của sơ đồ là làm rõ rủi ro đặc biệt của **public client không có secret bảo vệ** và tại sao PKCE ràng buộc code với một verifier riêng, không khẳng định mọi authorization code không dùng PKCE đều đổi được vô điều kiện.

### 6.2. Với PKCE S256

~~~mermaid
sequenceDiagram
    autonumber
    participant C as Client thật
    participant AS as Authorization Server
    participant X as Attacker bắt được code
    C->>C: Sinh verifier V; challenge C256=SHA256(V)
    C->>AS: /authorize?code_challenge=C256&method=S256
    AS->>AS: Lưu binding challenge trên authorization code CODE-1
    AS-->>X: Attacker nhìn thấy CODE-1
    X->>AS: /token: code=CODE-1, verifier giả Vx
    AS->>AS: S256(Vx) không khớp C256
    AS-->>X: invalid_grant / request bị từ chối
    C->>AS: /token: CODE-1 + verifier V
    AS->>AS: Kiểm tra V, code chưa dùng, client/redirect
    AS-->>C: Token nếu grant còn hợp lệ
~~~

AS có thể đánh dấu code bị vô hiệu theo chính sách sau một lần thử sai để giảm online guessing/race; nếu attacker gửi verifier sai trước, client thật có thể phải đăng nhập lại. **Bảo vệ confidentiality và authorization an toàn quan trọng hơn việc đảm bảo callback luôn thành công**.

### 6.3. PKCE giảm rủi ro nào, và không giảm rủi ro nào?

| Tình huống | PKCE giúp gì? | Kiểm soát bổ sung |
| --- | --- | --- |
| Attacker chỉ chặn được authorization code | Thiếu verifier nên không đổi code | Redirect URI, code single-use, client binding, TLS |
| App khác chiếm private URI callback | Có thể ngăn đổi code nếu verifier vẫn bí mật | External browser, OS app links, `state` và issuer binding |
| Malicious JavaScript lấy **cả code và verifier** | **Không đủ bảo vệ** | XSS mitigation, CSP, BFF, transaction storage |
| Attacker đọc challenge công khai từ /authorize | Không thể suy ra verifier mạnh một cách thực tế từ S256 | CSPRNG 256-bit, không dùng plain |
| Attacker đổi authorization method thành `plain` | Có thể làm lộ verifier nếu AS/client cho downgrade | Client gửi S256, AS yêu cầu S256 và chống downgrade |
| Attacker chiếm access token sau issuance | PKCE **không** ngăn bearer replay | TLS, secure storage, AT TTL, DPoP/mTLS sender constraint |
| Attacker dùng ID token thay AT | PKCE không xác định token purpose ở RS | Token type, expected audience, OIDC/RS validation |
| Client gọi sai token endpoint do mix-up/SSRF | Có thể lộ verifier/code cho endpoint giả | Trusted issuer, metadata validation, TLS, mix-up protection |
| Client tự tăng scope/audience | PKCE không kiểm soát quyền cấp | AS scope/resource policy và RS authorization |

### 6.4. Thấy challenge không có nghĩa đã biết verifier

Với S256 và 256-bit verifier ngẫu nhiên, challenge có thể xuất hiện trong URL authorization và được quan sát mà vẫn không thực tế để tìm verifier bằng brute force. **Tính bí mật của verifier** là điều làm PKCE hữu ích. Nếu client dùng verifier đơn giản như `"123456789..."` hoặc gửi verifier trong browser query, attacker có thể lấy lại nó dù method khai báo S256.

### 6.5. PKCE không bù được open redirect

Nếu AS chấp nhận redirect URI tùy ý như `https://attacker.example.test/callback`, authorization code có thể bị gửi thẳng đến attacker. PKCE có thể vẫn ngăn đổi code nếu attacker không nắm verifier, nhưng open redirect còn gây những rủi ro authentication/response injection/phishing và khiến giao thức phụ thuộc vào một lớp bảo vệ duy nhất. **Redirect URI allowlist và exact matching policy vẫn bắt buộc.**

## 7. `state`, OIDC `nonce`, client authentication và PKCE khác nhau

Các cơ chế bảo vệ hoạt động trên các ranh giới riêng:

| Cơ chế | Tạo/kiểm tra ở đâu? | Mục tiêu chính | Sai lầm thường gặp |
| --- | --- | --- | --- |
| **PKCE** | Client tạo challenge/verifier; AS so tại token endpoint | Ràng buộc authorization code với verifier của transaction | Nghĩ PKCE thay thế CSRF, client authentication hoặc login |
| **`state`** | Client tạo và xác minh trên authorization callback | Ràng buộc response với request/CSRF; hỗ trợ transaction correlation | Dùng static state hoặc không kiểm tra state |
| **OIDC `nonce`** | Client gửi trong auth request; xác minh ID token khi áp dụng | Ràng buộc ID token với authentication request/replay defense | Xem nonce là scope hoặc thay `state` ở mọi flow |
| **Client authentication** | Confidential client chứng minh ở AS token endpoint | Xác minh OAuth client bí mật/khóa/chứng chỉ | Nhúng `client_secret` vào SPA rồi gọi là confidential |
| **Redirect URI binding** | AS kiểm tra ở auth và token steps | Chống code được trả/đổi cho URI không được đăng ký | Cho redirect wildcard/open redirect |
| **Issuer/mix-up protection** | Client ràng buộc transaction với expected AS issuer | Không gửi code/verifier cho sai AS | Tin một `iss` hoặc token endpoint do user điều khiển |
| **Token validation ở RS** | Resource server | Xác minh token được cấp cho **chính RS** và đủ quyền | Chỉ kiểm chữ ký, bỏ `aud`/scope/domain ACL |

### 7.1. State và PKCE có thể cùng cần thiết

Một client có thể triển khai PKCE đúng nhưng vẫn nhận callback từ **một authorization transaction khác** vì không so `state` hoặc không kiểm tra issuer. PKCE không nên được dùng làm cớ bỏ các cơ chế CSRF/mix-up của client. Ngược lại, có `state` đúng không giúp chống một attacker đã lấy code và có khả năng đổi code ở AS nếu không có PKCE/những binding phù hợp.

### 7.2. `nonce` thuộc ngữ nghĩa OIDC

Khi dùng `scope=openid` để xác thực user, client nhận ID token và cần kiểm tra claims theo OIDC profile: issuer, audience, signature, time và `nonce` nếu đã gửi/được yêu cầu. **Không dùng `nonce` của ID token để thay `code_verifier`**; token endpoint không tính challenge từ OIDC nonce.

### 7.3. PKCE ở confidential client không phải bản sao của client secret

Client secret hoặc private-key JWT xác thực **client được đăng ký**. PKCE xác nhận bên đổi code biết **verifier của authorization transaction cụ thể**. Nếu một code từ browser bị chặn, riêng client authentication không luôn giải quyết mọi đường injection, còn PKCE bảo vệ mối quan hệ code–transaction. Các cơ chế được áp dụng **cùng nhau**, không nhất thiết phải chọn một.

### 7.4. Các lớp bảo vệ với multi-AS

Nếu client hỗ trợ hai AS (`auth-a.example.test` và `auth-b.example.test`), mỗi transaction phải giữ:

~~~text
state → expected_issuer
      → client_registration
      → redirect_uri
      → code_verifier
      → requested_scope/resource
      → created_at / expiry
~~~

Khi callback tới, client so khớp state và issuer của transaction, không gửi code/verifier tới token endpoint khác. RFC 9207 định nghĩa issuer identification trong authorization response khi AS hỗ trợ; một ứng dụng cũng có thể dùng các biện pháp mix-up prevention khác phù hợp profile. **Không xây token endpoint URL trực tiếp từ claim/request chưa tin.**

## 8. Authorization server phải ràng buộc và tiêu thụ code thế nào?

Một AS an toàn không thể chỉ lưu bảng `code → user_id`. Nó còn cần kiểm tra:

| Thành phần binding | Lý do |
| --- | --- |
| Authorization code ID / hashed secret | Tìm đúng transaction, tránh lộ raw code trong storage/log |
| Issuer, client ID | Code thuộc client/AS nào; không cho client khác đổi |
| Redirect URI | Cố định nơi code được trả về, kiểm tra token request khi cần |
| PKCE challenge và method | Không để request thứ hai tự thay đổi challenge/method |
| User/subject và authorization grant | Xác định RO và consent/policy đã được phê duyệt |
| Granted scopes và resource/audience | Không cấp token vượt phạm vi đã authorize |
| Created/expiry/status | Code ngắn hạn, single-use, có thể revoke |
| Authentication/session context | Áp session/assurance policy khi AS yêu cầu |

### 8.1. Pseudo-state machine

~~~mermaid
stateDiagram-v2
    [*] --> ISSUED
    ISSUED --> EXPIRED: ttl exceeded
    ISSUED --> CONSUMED: Valid code + verifier + binding, atomic
    ISSUED --> REVOKED: Grant/session invalidated
    CONSUMED --> REUSE_DETECTED: Same code submitted again
    EXPIRED --> [*]
    REVOKED --> [*]
    REUSE_DETECTED --> [*]
~~~

Đây là mô hình trạng thái logic. Có thể AS quyết định vô hiệu code khi bị thử sai verifier nhiều lần; chính sách cụ thể còn phụ thuộc bảo mật và chống đoán mã. Dù trạng thái nội bộ đặt tên khác, **không được cho cùng authorization code đổi token hai lần thành công**.

### 8.2. Hai request đổi cùng code đồng thời

~~~mermaid
sequenceDiagram
    autonumber
    participant C1 as Request A
    participant C2 as Request B
    participant AS as Token endpoint nhiều node
    participant S as Shared grant storage
    par Concurrent redeem
        C1->>AS: CODE-1 + valid verifier
        C2->>AS: CODE-1 + valid verifier
    end
    AS->>S: Atomic compare-and-consume CODE-1
    S-->>AS: Only one request wins
    AS-->>C1: One request can receive tokens
    AS-->>C2: The other receives invalid_grant
~~~

Trong thực tế request A hoặc B có thể là winner; sơ đồ chỉ minh họa **single-winner**. Dùng database transaction/compare-and-swap/centralized state hoặc cơ chế phù hợp đa node. Khóa `synchronized` trên một JVM không đủ nếu AS scale ngang.

### 8.3. Token issuance cần cùng transaction với consume

Nếu AS đánh dấu code đã dùng rồi crash trước khi commit token, client có thể mất khả năng đăng nhập hợp lệ nhưng vẫn **không được phá single-use** để trả token lần thứ hai không an toàn. AS cần thiết kế nhất quán giữa code consumption, issuance record và recovery theo storage architecture, tránh trạng thái một code tạo nhiều kết quả.

RFC 6749 yêu cầu authorization code chỉ dùng một lần. Nếu AS phát hiện code bị dùng nhiều lần, nó phải từ chối; và nên thu hồi những token đã cấp từ code đó **nếu khả thi**, do có nguy cơ code bị can thiệp hoặc sử dụng lại.

### 8.4. Verify PKCE không được hạ cấp theo lỗi

Một AS có thể phát sinh lỗi:

~~~text
authorization record: method=S256, challenge=C
token request:        code=CODE-1, code_verifier missing
UNSAFE fallback:      "PKCE failed; check client secret only"
~~~

Nếu client registration yêu cầu PKCE hoặc authorization code đã được gắn challenge, thiếu verifier/sai verifier **không thể được coi là thành công**. Không bỏ PKCE vì client có secret hoặc do một node AS không đọc được record challenge. Sai/thiếu binding phải fail closed.

### 8.5. Lưu verifier ở AS hay client?

Thông thường AS **lưu challenge và method**, không cần lưu plaintext `code_verifier`, vì verifier được client giữ và chỉ xuất hiện khi đổi code. Client không gửi verifier trước lúc đó. Mô hình này giảm rủi ro chính AS lưu một bí mật khác không cần thiết. Mọi request body chứa verifier tại token endpoint vẫn phải được redact trong log/tracing.

## 9. Lỗi protocol thường gặp khi đổi code

| Tình huống | Lỗi/kết quả thường gặp | Hành vi đúng |
| --- | --- | --- |
| Không có hoặc sai `code_verifier` | Thường `invalid_grant` hoặc lỗi tương ứng theo AS | Từ chối; không cấp token |
| Verifier sai cú pháp | `invalid_request` hoặc `invalid_grant` tùy vị trí kiểm tra/profile | Từ chối; sửa client chứ không fallback |
| Authorization code đã dùng/hết hạn | `invalid_grant` | Không thử mãi cùng code; khởi tạo transaction mới |
| Code gắn client A nhưng B xin đổi | `invalid_grant`/`invalid_client` theo lỗi thật | Từ chối cross-client binding |
| Redirect URI không khớp | `invalid_grant` hoặc lỗi giao thức tương ứng | Từ chối |
| Confidential client auth sai | `invalid_client` | Không bỏ client authentication hoặc tiếp tục với public giả |
| Scope/resource request ban đầu không hợp lệ | Lỗi authorization theo policy/`invalid_scope` khi áp dụng | Không tự nâng scope |
| Token endpoint timeout | AS có thể đã commit, kết quả chưa biết | Không retry mù quáng credential single-use |
| Client dùng token sai `aud` tại API | `401 invalid_token` thường gặp | Không coi đây là lỗi PKCE; xin đúng audience bằng grant hợp lệ |
| API token hợp lệ nhưng thiếu scope | `403 insufficient_scope` thường gặp | Xin quyền hợp lệ, không đổi verifier để tự tăng quyền |

Các mã lỗi chính xác có thể khác theo đặc tả/bước lỗi và AS; không nên viết client logic giả định mọi lỗi PKCE đều trả một mã HTTP duy nhất. Điều quan trọng là **không phát hành token khi binding thất bại** và không tiết lộ raw code, verifier hoặc token trong thông báo lỗi.

### 9.1. Unknown outcome sau HTTP timeout

Client gửi:

~~~text
POST /token(CODE-1, V) → AS đã kiểm tra và phát token
AS → gửi HTTP 200 nhưng network reset trước khi client nhận
Client chỉ thấy timeout
~~~

Nếu client gửi lại cùng code, AS có thể trả `invalid_grant` vì code đã dùng. **Timeout không chứng minh request chưa được xử lý**. Client nên có một request redeem cho mỗi transaction, lưu kết quả/phiên ngay khi thành công và xử lý các callback lặp bằng trạng thái đã lưu. Nếu không thể khôi phục kết quả, có thể phải bắt đầu authorization flow mới; không yêu cầu AS bỏ single-use để trả lại token.

### 9.2. Không nhầm retry với code replay

Retry an toàn phải dựa vào grant semantics. `client_credentials` có thể xin token mới nhiều lần và dùng cache/single-flight; `authorization_code` là credential **dùng một lần**, retry sau unknown outcome cần xử lý đặc biệt. PKCE không khiến authorization code được phép sử dụng nhiều lần.

### 9.3. Quan sát lỗi an toàn

Log ở token endpoint có thể ghi:

~~~text
oauth_token_redemption_failed
grant_type=authorization_code
client_id=sales-dashboard
reason=PKCE_MISMATCH
correlation_id=<opaque-reference>
~~~

Không ghi:

~~~text
code=<raw-authorization-code>
code_verifier=<raw-secret-verifier>
Authorization: Basic <client-credentials>
access_token=<raw-access-token>
refresh_token=<raw-refresh-token>
~~~

`correlation_id` nên là tham chiếu không bí mật, không dùng được như credential. Nếu cần tương quan sự kiện, dùng metadata bảo vệ/credential fingerprint phù hợp; không đưa raw verifier vào log chỉ để debug.

## 10. PKCE theo từng loại client: SPA, native và BFF

PKCE thuộc Authorization Code flow nhưng **cách bảo vệ verifier và đổi code phụ thuộc client type**.

| Client | Ai sinh verifier? | Ai lưu verifier? | Ai POST `/token`? | Rủi ro trọng tâm |
| --- | --- | --- | --- | --- |
| **SPA thuần browser** | JavaScript app hoặc SDK đáng tin | Transaction storage tạm trên browser | Browser public client | XSS, extension độc hại, trộn multi-tab và verifier bị log |
| **Native mobile** | Ứng dụng với CSPRNG OS | App memory/secure storage khi cần | Native public client | Redirect URI hijack, embedded webview, secret trong binary |
| **Desktop/CLI** | App/CLI với CSPRNG | Runtime local, transaction-bound | App public client | Loopback listener hijack, shell logs/history, insecure file cache |
| **Server-rendered web app** | Backend | Server session/token transaction store | Backend confidential client | Session fixation/CSRF, stale transaction, secret lộ |
| **BFF** | Backend | Backend session store | Backend confidential client | Cookie/session CSRF/XSS, distributed session race |

### 10.1. SPA: public client, không dùng client secret nhúng

Trong SPA, `code_verifier` vẫn được tạo để bảo vệ code, nhưng **nó không phải bí mật an toàn trước JavaScript độc hại chạy cùng origin**. Một XSS có thể đọc transaction state, lấy verifier hoặc thao tác trực tiếp trên phiên. Vì vậy:

- Ưu tiên thư viện OAuth/OIDC client được bảo trì, hỗ trợ Authorization Code + PKCE và state/issuer/nonce đúng profile.
- Tạo verifier **cho mỗi authorization request**, không dùng singleton global chung nhiều tab.
- Giảm XSS qua encoding, CSP phù hợp, dependency hygiene và hạn chế mã bên thứ ba.
- Không đưa verifier/token vào URLs/analytics; bảo vệ refresh token theo AS policy (rotation hoặc sender constraint nếu phù hợp).
- Nếu yêu cầu giữ RT dài hạn mà không muốn token nằm trong JS, cân nhắc BFF.

### 10.2. Native: external browser và redirect URI

RFC 8252 khuyến nghị native apps dùng **external user-agent** thay vì embedded webview. Với redirect:

~~~text
App-claimed HTTPS URI: https://app.example.test/oauth/callback
Private-use URI scheme: com.example.sales:/oauth2redirect
Desktop loopback URI:   http://127.0.0.1:53621/callback
~~~

Native loopback HTTP trên chính thiết bị là ngoại lệ được profile cho phép cho **redirect URI local**, không cho phép HTTP plaintext tới AS token endpoint/API. PKCE bảo vệ code nếu app khác cố nhận callback, nhưng ứng dụng vẫn phải:

1. Dùng OS-bound redirect/app links khi có thể.
2. Bind loopback listener vào `127.0.0.1`/`[::1]`, không mở cổng ra mạng ngoài.
3. Kiểm tra `state` và expected issuer; dùng verifier đúng authorization transaction.
4. Gọi token endpoint qua HTTPS với certificate/hostname validation.
5. Lưu access/refresh token trong kho thích hợp; tránh hardcode secret trong binary.

### 10.3. BFF: browser không nhận verifier và OAuth token

Trong mô hình BFF, backend quản lý authorization transaction:

~~~text
Browser            BFF                       AS
   | GET /login      |                        |
   |---------------->| Sinh V,C,state         |
   |<----------------| 302 /authorize (C)     |
   |----------------------------------------->|
   |<-----------------------------------------| 302 code,state
   | GET /callback   |                        |
   |---------------->| Load V theo state      |
   |                 | POST /token(code,V)    |
   |                 |----------------------->|
   |                 |<-----------------------| AT/RT
   |<----------------| Session cookie         |
~~~

Browser có thể thấy code trong callback URL, nhưng **không được nhận `code_verifier` hoặc RT từ backend trong response**. Token store, session cookies và CSRF defense cần được thiết kế riêng. Một session cookie `HttpOnly` giảm khả năng JavaScript đọc trực tiếp cookie, nhưng không tự chặn XSS gửi request thay người dùng.

### 10.4. Không áp PKCE sai vào Client Credentials hoặc Refresh Token Grant

PKCE bảo vệ **authorization code redemption**. Một service dùng `grant_type=client_credentials` không có authorization code để ràng buộc challenge/verifier; nó cần **client authentication và AS policy**, audience/scope. Một client dùng `grant_type=refresh_token` phải bảo vệ refresh token, client binding, rotation/reuse detection và timeout/race, không gửi verifier từ code flow cũ để tự động làm refresh an toàn.

PKCE cũng **không thay thế** DPoP/mTLS-bound access tokens. Sau khi AS cấp AT, nếu cần chống bearer replay, dùng sender constraint đúng profile và RS verify proof; không yêu cầu RS giữ verifier.

## 11. Java 17+: tạo PKCE S256 bằng CSPRNG

Đây là ví dụ Java thuần dùng CSPRNG, SHA-256, Base64url không padding và ASCII. Trong production, ưu tiên dùng SDK/framework OAuth được bảo trì để tránh code trùng lặp, nhưng hiểu thuật toán giúp kiểm tra triển khai.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.util.Base64;

public final class Pkce {
    private static final SecureRandom RANDOM = new SecureRandom();
    private static final Base64.Encoder BASE64_URL =
            Base64.getUrlEncoder().withoutPadding();

    public record Pair(String verifier, String challenge) {}

    public static Pair generate() {
        byte[] randomBytes = new byte[32]; // 256 bit entropy
        RANDOM.nextBytes(randomBytes);
        String verifier = BASE64_URL.encodeToString(randomBytes);
        String challenge = s256Challenge(verifier);
        return new Pair(verifier, challenge);
    }

    public static String s256Challenge(String verifier) {
        if (verifier == null
                || !verifier.matches("[A-Za-z0-9._~-]{43,128}")) {
            throw new IllegalArgumentException(
                    "Invalid PKCE code_verifier format");
        }

        byte[] input = verifier.getBytes(StandardCharsets.US_ASCII);
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                    .digest(input);
            return BASE64_URL.encodeToString(digest);
        } catch (NoSuchAlgorithmException impossibleInNormalJava) {
            throw new IllegalStateException(
                    "SHA-256 is required by this environment",
                    impossibleInNormalJava);
        }
    }

    private Pkce() {}
}
~~~

**Điểm cần lưu ý:**

- 32 bytes từ `SecureRandom` được Base64url no padding thành verifier 43 ký tự; không cần tạo random string rồi băm một giá trị dễ đoán.
- Regex `[A-Za-z0-9._~-]{43,128}` kiểm tra cú pháp, **không đo entropy thật**. Kiểm tra độ ngẫu nhiên phải dựa vào nguồn CSPRNG khi tạo verifier.
- `StandardCharsets.US_ASCII` đúng vì tập unreserved chỉ chứa ASCII. Không dùng platform default charset.
- `Base64.getUrlEncoder().withoutPadding()` tránh dấu `+`, `/` và `=` không phù hợp S256 challenge.
- `MessageDigest.getInstance("SHA-256")` không phải một JWT signature, mà chỉ tạo cam kết một chiều.
- Không log đối tượng `Pair` (record mặc định có `toString` tiết lộ verifier). Trong production, nên dùng lớp transaction không cho serialization/logging bí mật, không in `pair` trong debugger/traces và xóa state khi kết thúc.

### 11.1. Kiểm thử với RFC 7636 Appendix B

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import org.junit.jupiter.api.Test;

class PkceTest {
    @Test
    void matchesPublishedTestVector() {
        String verifier =
                "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk";
        assertEquals(
                "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
                Pkce.s256Challenge(verifier));
    }

    @Test
    void producesFreshWellFormedPairs() {
        Pkce.Pair a = Pkce.generate();
        Pkce.Pair b = Pkce.generate();
        assertTrue(a.verifier().matches("[A-Za-z0-9._~-]{43,128}"));
        assertEquals(43, a.challenge().length());
        assertEquals(Pkce.s256Challenge(a.verifier()), a.challenge());
        // Kiểm tra tính khác nhau mang tính smoke test;
        // tính bảo mật dựa trên CSPRNG chứ không phải một phép thử duy nhất.
        assertTrue(!a.verifier().equals(b.verifier()));
    }
}
~~~

Test kiểm tra số ký tự, định dạng và vector hash. Việc hai verifier ngẫu nhiên trùng nhau có xác suất cực nhỏ nhưng không phải **bảo đảm logic tuyệt đối**; `assertTrue(!...equals(...))` là smoke test hợp lý cho môi trường test, không thay thế kiểm định nguồn entropy.

### 11.2. Lưu transaction đúng cách

Ở phía client, một transaction record có thể có:

~~~json
{
  "state_ref": "<opaque-state-reference>",
  "expected_issuer": "https://auth.example.test",
  "registration_id": "sales-dashboard",
  "redirect_uri": "https://client.example.test/callback",
  "code_verifier": "<protected-verifier>",
  "challenge_method": "S256",
  "created_at": "2026-11-23T02:00:00Z",
  "consumed": false
}
~~~

Record trên là ví dụ diễn giải, không phải cấu trúc chuẩn. `state_ref` phải có tính ngẫu nhiên/transaction binding thích hợp; verifier cần nằm trong storage phù hợp với loại client, có TTL ngắn và **bị xóa/consume khi callback hoàn tất hoặc thất bại**. Với backend nhiều instance, không chỉ lưu verifier trong biến memory của một instance nếu callback có thể về instance khác; cần session store/shared transaction store bảo vệ hoặc sticky routing được thiết kế đúng.

### 11.3. Đừng dùng `toString` để debug verifier

Các thư viện Java có thể tự serialize record/object trong log debug hoặc HTTP tracing. Nếu lưu `Pair(verifier,challenge)`, tránh truyền object thẳng vào log. Thậm chí khi dùng trace spans, không set `code_verifier` hoặc authorization code làm attribute. Nếu cần debug, log an toàn:

~~~text
auth_txn_id = <non-secret-correlation-id>
pkce_method = S256
pkce_challenge_present = true
result = PKCE_VERIFIED | PKCE_MISMATCH | CODE_EXPIRED
~~~

## 12. Spring Security OAuth2 Client: bật PKCE cho code flow

Spring Security có abstraction OAuth2 Login/OAuth2 Client để tạo authorization request, đổi authorization code, quản lý authorized client và tích hợp OIDC. **Tránh tự ghép URL, tự lưu code/verifier và tự post token nếu framework có thể làm đúng theo phiên bản bạn dùng.**

### 12.1. Client registration ở backend

Ví dụ cấu hình cho confidential client:

~~~yaml
spring:
  security:
    oauth2:
      client:
        provider:
          company-as:
            issuer-uri: https://auth.example.test
        registration:
          sales-dashboard:
            provider: company-as
            client-id: sales-dashboard
            client-secret: PLACEHOLDER_FROM_SECRET_MANAGER
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - orders.read
~~~

`PLACEHOLDER_FROM_SECRET_MANAGER` là **placeholder**, không phải client secret thật. Phải inject secret từ storage tin cậy, bảo vệ TLS endpoints và không trả secret xuống browser. `issuer-uri` dùng trusted discovery metadata theo framework; nếu có nhiều IdP, phải ràng buộc đúng issuer/registration ở callback.

### 12.2. AuthorizationRequestResolver sử dụng `withPkce()`

Trong Spring Security 6.x, có thể tùy biến authorization request resolver để thêm PKCE vào code flow:

~~~java
@Configuration
@EnableWebSecurity
class OAuthLoginSecurity {

    @Bean
    OAuth2AuthorizationRequestResolver pkceResolver(
            ClientRegistrationRepository registrations) {

        DefaultOAuth2AuthorizationRequestResolver resolver =
                new DefaultOAuth2AuthorizationRequestResolver(
                        registrations,
                        "/oauth2/authorization");

        resolver.setAuthorizationRequestCustomizer(
                OAuth2AuthorizationRequestCustomizers.withPkce());
        return resolver;
    }

    @Bean
    SecurityFilterChain webSecurity(
            HttpSecurity http,
            OAuth2AuthorizationRequestResolver pkceResolver)
            throws Exception {

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .anyRequest().authenticated());

        http.oauth2Login(login -> login
                .authorizationEndpoint(endpoint ->
                        endpoint.authorizationRequestResolver(pkceResolver)));

        return http.build();
    }
}
~~~

Ý nghĩa:

1. Resolver tạo OAuth authorization request của registration, bổ sung `code_challenge` và `code_challenge_method=S256` theo customizer.
2. Framework lưu `code_verifier` như một phần authorization transaction để dùng khi đổi code tại token endpoint theo integration đã cấu hình.
3. Phải **kiểm tra thật** authorization URL có challenge/method và POST `/token` có verifier sau callback, nhất là khi dùng session repository tùy chỉnh, Spring Security version khác hoặc nhiều node.
4. Với **public client**, có thể có hỗ trợ PKCE tích hợp theo client authentication method/version; hãy xác minh yêu cầu `S256` theo AS và client registration. Đừng phụ thuộc vào giả định rằng mọi bản framework đều bật cùng một mặc định.
5. Đây là snippet cần imports và các Spring OAuth2 client dependencies tương ứng; không phải cấu hình hoàn chỉnh cho session/CSRF/multi-AS/BFF logout.

### 12.3. Kiểm tra nơi lưu authorization transaction

Trong web session-based client, `OAuth2AuthorizationRequestRepository` giúp liên kết authorization request với callback. Nếu thay bằng custom repository (database/Redis/cookie), phải bảo vệ:

- `state` đủ ngẫu nhiên, thuộc đúng browser/session và one-time.
- `code_verifier` được lưu **cùng transaction** và lấy lại chính xác ở callback.
- Không encode verifier **plaintext vào URL hoặc client-visible cookie không bảo vệ**.
- TTL, concurrency giữa browser tabs và callback replay.
- Không tự gửi verifier tới AS khác khi issuer/registration không khớp.

Nếu framework lưu authorization request trong HTTP session, tắt session storage hoặc ghi đè repository thiếu PKCE attributes có thể gây lỗi `invalid_grant` lúc redeem. Đừng “sửa” bằng cách xóa PKCE khi callback bị mất session; cần sửa transaction persistence.

### 12.4. OIDC integration

Khi thêm `openid` scope, Spring Security OAuth2 Login có thể xử lý OIDC ID token theo cấu hình framework. Client vẫn cần xác minh `iss`, `aud`, signature, expiry và `nonce` theo profile/transaction khi áp dụng. Token nhận được để gọi API **phải là access token**, không phải ID token; AT phải đúng audience/scopes.

**PKCE xác minh ở AS khi đổi code; OIDC ID token validation xảy ra ở client.** Hai bước có thể cùng chạy trong một login flow nhưng không được trộn vai trò.

## 13. Spring Authorization Server: yêu cầu PKCE tại AS

Một AS cần từ chối authorization/token requests không thỏa PKCE policy. Spring Authorization Server có thiết lập `ClientSettings.requireProofKey(true)` trên client registration trong những phiên bản hỗ trợ.

Ví dụ **public client** có authorization code + PKCE:

~~~java
RegisteredClient publicClient = RegisteredClient
        .withId(UUID.randomUUID().toString())
        .clientId("public-mobile-client")
        .clientAuthenticationMethod(ClientAuthenticationMethod.NONE)
        .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
        .redirectUri("com.example.sales:/oauth2redirect")
        .scope("orders.read")
        .clientSettings(ClientSettings.builder()
                .requireProofKey(true)
                .requireAuthorizationConsent(true)
                .build())
        .build();
~~~

Snippet giả định imports, AS authorization providers và registration storage đã được cấu hình. `ClientAuthenticationMethod.NONE` phù hợp **public client không dùng client secret**; không áp cách này cho confidential client thay vì phương thức xác thực được đăng ký. `requireProofKey(true)` là chính sách trên AS yêu cầu PKCE, không phải lệnh tự sinh verifier giúp client.

Khi AS sử dụng nhiều node:

- Bản ghi authorization code phải chứa client, redirect, scope/resource và PKCE binding.
- Các node phải có storage chung hoặc coordination phù hợp để code **chỉ một lần** được redeem.
- Challenge/verifier mismatch không được tạo AT/RT.
- Không được chọn `plain` khi client/AS yêu cầu `S256`.
- Client/issuer/redirect binding không bị bỏ qua khi request đi qua proxy khác nhau.
- Mọi lỗi được phản hồi an toàn, không trả lại verifier/code/token trong response body/log.

### 13.1. Kiểm tra issuer/JWKS độc lập

PKCE bảo vệ token issuance. Nếu AS ký JWT access token, RS vẫn phải tin đúng issuer, JWKS/ký số, `aud`, `exp`, scope và token profile. Nếu AS cấp opaque token, RS dùng introspection endpoint được cấu hình và xác thực; `active=true` không tự cho token quyền truy cập mọi resource.

**Bật PKCE tại AS không có nghĩa resource server có thể bỏ xác minh token.**

### 13.2. PKCE không phải cơ chế refresh token rotation

Sau authorization code flow thành công, AS có thể cấp RT cho client theo grant/policy. RT rotation, sender constraint và replay detection là vấn đề **khác**, không được tự xem là đã giải quyết chỉ vì initial code flow có `S256`. Khi logout, revoke RT/grant theo chính sách; không mint RT mới để “thay” token đã logout.

### 13.3. Ranh giới với Resource Indicators

Nếu client yêu cầu `resource=https://orders.example.test/` theo RFC 8707, AS phải kiểm tra client/grant được phép xin token cho orders. PKCE không tăng quyền của client, và code đổi thành công **không tự** chứng minh scope/audience là đúng. Đến resource server, API phải check audience của chính mình và object-level authorization.

## 14. Quy trình kiểm tra một PKCE flow trong môi trường tích hợp

Khi tích hợp client mới với AS, cần quan sát **cả hai bước** mà không để lộ verifier/credential ra log. Một checklist kỹ thuật:

### 14.1. Trước khi mở browser

1. Client registration trỏ đến **issuer/authorization endpoint/token endpoint tin cậy** qua HTTPS; chứng chỉ server được kiểm tra đúng.
2. Client được AS cho phép `authorization_code` và redirect URI đã đăng ký.
3. Client tạo verifier **mới** cho mỗi transaction, challenge S256 và state ngẫu nhiên.
4. Challenge nằm trong request `/authorize`; verifier **không** nằm trong URL.
5. Transaction storage giữ đúng verifier cho session, issuer, client và state.

### 14.2. Sau callback

1. Client kiểm tra callback thuộc đúng session/state, issuer dự kiến và redirect.
2. Client lấy verifier từ transaction storage, **không chấp nhận verifier do query param hoặc một tab khác tùy ý đưa vào**.
3. Token request `POST /token` dùng form encoding với `grant_type=authorization_code`, code, verifier, redirect URI/client binding phù hợp.
4. Confidential client còn phải xác thực đúng phương thức; public client không dùng secret nhúng.
5. AS kiểm tra binding và tiêu thụ code nguyên tử; client lưu kết quả an toàn rồi hủy transaction.

### 14.3. Sau token issuance

1. Client chỉ dùng AT cho RS được AS cấp theo audience/resource policy.
2. RS xác minh JWT/JWKS hoặc introspection opaque, đúng issuer, audience, expiry, scope, subject/client/actor theo profile.
3. RS thực thi tenant/object-level authorization; không chỉ tin một scope.
4. RT (nếu có) được bảo vệ bằng rotation/sender constraint/revocation theo policy, tách biệt PKCE.
5. Không log raw code, verifier, AT, RT, client secret, private key trong gateway/SDK/APM.

### 14.4. Những lỗi có thể phân biệt qua quan sát

| Nơi lỗi | Dấu hiệu | Kiểm tra trước |
| --- | --- | --- |
| Authorization request | AS từ chối vì thiếu challenge/method | Client registration yêu cầu PKCE? URL có `code_challenge` và `S256`? |
| Callback | Không tìm thấy transaction của state | Session store mất, multiple tabs, CSRF/mix-up? |
| Token request | `invalid_grant` khi đổi code lần đầu | Đúng verifier, code, redirect, client binding? |
| Token request | `invalid_client` | Confidential client auth sai; không liên quan PKCE hash |
| Token request | `invalid_grant` chỉ khi retry | Code đã tiêu thụ thành công trong request trước? |
| JWT validation | `invalid_token` vì wrong audience | Token issuance/resource indicator, không phải tự sửa verifier |
| API authorization | `insufficient_scope` / 403 | AS chỉ cấp scope hẹp, RS domain permission |
| Refresh | RT reuse/`invalid_grant` | Refresh rotation race, không phải cần đổi PKCE verifier |

Một quy trình debug đúng phải phân biệt **authorization transaction**, **token issuance** và **resource-server authorization**. Cố sửa lỗi API bằng cách tắt PKCE thường là sai lớp.

## 15. Ma trận kiểm thử PKCE: đúng, sai và cạnh tranh

Trong test environment, tạo AS test với code storage có thể kiểm tra, các client registrations public/confidential, JWT/opaque test token và công cụ mô phỏng callback/interception. Giữ khóa test riêng; không đưa credential production vào test suite hoặc output.

| ID | Tình huống | Kết quả mong đợi |
| --- | --- | --- |
| P01 | Sinh verifier bằng 32 bytes CSPRNG | Chuỗi Base64url no padding dài 43, entropy đến từ CSPRNG |
| P02 | Tính challenge từ RFC 7636 Appendix B | Khớp chính xác `E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM` |
| P03 | Hai authorization transaction liên tiếp | Verifier/state độc lập, không dùng một bộ dùng chung |
| P04 | Verifier có 42 ký tự | Client/AS từ chối cú pháp không hợp lệ |
| P05 | Verifier có 129 ký tự | Từ chối |
| P06 | Verifier chứa `+`, `/` hoặc `=` padding | Từ chối theo cú pháp RFC 7636 |
| P07 | Verifier chứa Unicode hoặc whitespace | Từ chối, không tự normalization |
| P08 | Challenge S256 tính bằng Base64 chuẩn thay URL-safe | Test phát hiện mismatch hoặc ký tự sai |
| P09 | Challenge tính bằng SHA-256 trên bytes sai charset | RFC vector không khớp; sửa thuật toán |
| P10 | Authorization request có challenge/method S256 hợp lệ | AS lưu binding với authorization code |
| P11 | Authorization request thiếu challenge trong client bắt buộc PKCE | AS từ chối, không âm thầm downgrade |
| P12 | Client yêu cầu `plain` khi AS bắt buộc S256 | AS từ chối |
| P13 | Attacker thay method trong authorization request thành plain | Chính sách S256 không cho downgrade thành công |
| P14 | Client gửi verifier trong /authorize thay challenge | Test phát hiện secret leakage và request sai |
| P15 | Callback có code/state đúng, verifier đúng | Code được đổi thành AT theo grant/policy |
| P16 | Callback `state` sai | Client từ chối, không gửi token request |
| P17 | Callback thuộc tab A nhưng client dùng verifier tab B | AS từ chối mismatch; không trao token |
| P18 | Token request thiếu `code_verifier` với code đã có challenge | AS từ chối, không cấp token |
| P19 | Token request dùng verifier sai | AS từ chối (thường `invalid_grant`) |
| P20 | Token request dùng một challenge khác để override stored challenge | AS bỏ qua/không chấp nhận override; verifier phải khớp stored binding |
| P21 | Authorization code đã hết hạn | AS từ chối |
| P22 | Authorization code được dùng lần hai sau thành công | AS từ chối single-use |
| P23 | Hai node AS đồng thời redeem cùng code/verifier | **Tối đa một request thành công** |
| P24 | Code của public client A được đổi bởi client B | AS từ chối cross-client binding |
| P25 | Token request sai redirect URI đã gắn với code | AS từ chối |
| P26 | Confidential client đúng PKCE nhưng client secret/private-key assertion sai | AS từ chối client authentication |
| P27 | Public client thiếu static client secret nhưng có PKCE đúng | Được phép theo đăng ký public, không coi thiếu secret là lỗi |
| P28 | Token request không có TLS certificate validation | Test chặn/nhận diện cấu hình không an toàn |
| P29 | Token endpoint trả redirect sang origin lạ | Client không gửi code/verifier/client secret sang đó |
| P30 | Browser callback mang code giả của issuer khác | Client chặn qua state/issuer/mix-up binding |
| P31 | Attacker chặn code nhưng không có verifier | Không thể đổi code thành token |
| P32 | Attacker nhìn thấy challenge công khai | Không có cách thực tế suy ra verifier CSPRNG S256 |
| P33 | Verifier vô tình xuất hiện trong log/traces | Redaction test thất bại, phải sửa |
| P34 | Code/verifier đúng nhưng client xin scope ngoài quyền | AS không cấp scope vượt policy |
| P35 | Code/verifier đúng nhưng RS nhận AT sai audience | RS từ chối AT |
| P36 | ID token OIDC được gửi làm AT ở API | RS từ chối token purpose/audience |
| P37 | AS đổi code thành công nhưng client mất HTTP response | Retry không phát token lần hai từ cùng code, recovery theo grant |
| P38 | Client nhận callback lặp sau khi đã lưu phiên hợp lệ | Không redeem code lần nữa; dùng session đã hoàn tất |
| P39 | OIDC ID token có nonce sai transaction | Client từ chối OIDC authentication, dù PKCE đã qua |
| P40 | SPA bị XSS đọc cả verifier lẫn code | Test minh họa PKCE không chặn khi cả hai bí mật lộ; cần XSS defense |
| P41 | Native redirect bị app khác nhận nhưng không biết verifier | Không đổi được code, nhờ PKCE/AS binding |
| P42 | BFF gửi verifier/refresh token về frontend | Vi phạm kiến trúc BFF, test response không có credential |
| P43 | RT rotation race sau khi initial PKCE thành công | Cần single-flight/reuse detection; PKCE không tự xử lý |
| P44 | Client credentials gửi `code_verifier` không có auth code | Không được hiểu PKCE là bằng chứng thay client authentication |
| P45 | RFC 8693 token exchange thiếu subject/actor authorization | AS từ chối; không nhầm với code redemption |
| P46 | PKCE thành công nhưng object thuộc tenant khác | RS từ chối theo domain ACL |

### 15.1. Test dương/âm phải cô lập nguyên nhân

Nếu thử P19 mà AS luôn trả `invalid_client` do secret sai, việc “PKCE mismatch bị từ chối” **không được chứng minh**. Hãy chuẩn bị:

~~~text
Test A:
  client, code, redirect, scope, PKCE verifier đều đúng
  → Nhận token

Test B:
  Giống Test A ở các điều kiện khác, thay verifier bằng giá trị sai
  → AS từ chối, không phát token

Test C:
  Làm lại code/verifier mới; lần đầu redeem hợp lệ
  → Nhận token
  Gửi cùng code lần hai
  → AS từ chối single-use
~~~

**Không** dùng chung authorization code giữa Test A và Test B nếu test runner chạy không xác định thứ tự và AS có policy tiêu thụ/revoke code sau thất bại; mỗi test nên có fixture authorization transaction riêng hoặc trình tự được kiểm soát.

### 15.2. Kiểm thử nhiều tab/nhiều instance

Với SPA:

~~~text
Tab A mở login  → state-A, verifier-A
Tab B mở login  → state-B, verifier-B
Callback B tới trước: tìm đúng verifier-B
Callback A tới sau:  tìm đúng verifier-A
Không đọc "lastVerifier" toàn cục rồi dùng cho cả hai.
~~~

Với BFF nhiều Pod:

~~~text
Authorization request tới Pod-1 → lưu verifier vào shared session store.
Callback tới Pod-2             → tìm state và verifier đúng phiên.
AS token request               → đúng verifier và client binding.
Duplicate callback             → transaction đã consumed; không đổi code lại.
~~~

Kiểm thử double-submit cần cố định barrier để **hai request thực sự cùng tới AS**; test client single-flight ngược lại phải xác nhận client không gửi trùng request khi một kết quả có thể chia sẻ. Đây là hai loại test bảo vệ ở hai phía khác nhau.

### 15.3. Kiểm thử ở resource server

PKCE được xác minh **tại AS**, nhưng không vì vậy bỏ bài test RS:

~~~json
{
  "valid_for_orders": {
    "iss": "https://auth.example.test",
    "aud": ["orders-api"],
    "scope": "orders.read"
  },
  "wrong_resource": {
    "iss": "https://auth.example.test",
    "aud": ["payments-api"],
    "scope": "orders.read"
  }
}
~~~

Hai JSON object là claims mô tả, **không phải JWT đã ký**. Với khóa/issuer test tin cậy, cả hai access token có thể được phát hành qua code+PKCE hợp lệ theo policy AS, nhưng **`orders-api` phải chỉ chấp nhận token đúng audience của nó** và domain ACL. Điều này minh họa PKCE và RS authorization là hai trách nhiệm độc lập.

## 16. Bốn tình huống triển khai và cách xử lý

### Tình huống A: Native app báo `invalid_grant` chỉ trên một số thiết bị

Ứng dụng `sales-mobile` dùng PKCE. Trên một số thiết bị, app khởi tạo login ở phiên A nhưng sau khi browser quay lại, một activity/process mới không đọc được `code_verifier` của A; app sinh verifier B rồi POST code A + verifier B. AS trả `invalid_grant`.

**Phân tích:** AS từ chối đúng vì proof không khớp. Lỗi nằm ở **transaction persistence/binding** phía native client, không phải vì AS “quá nghiêm”.

**Giải pháp:** Lưu verifier trong vùng transaction được bảo vệ đủ để vượt vòng đời activity, ràng buộc state/issuer/redirect, không sinh verifier mới cho callback cũ; hủy transaction lỗi và bắt đầu authorization mới nếu bản verifier cũ mất.

### Tình huống B: SPA nhiều tab dùng cùng `code_verifier`

Developer lưu một biến `currentVerifier` toàn cục ở localStorage. Alice mở login ở tab A và tab B. B ghi đè verifier của A; callback A nhận code A nhưng ứng dụng gửi verifier B.

**Phân tích:** PKCE không sai; cách lưu trữ transaction không phân biệt tab/state khiến client dùng nhầm proof. Nếu ứng dụng dùng verifier cố định để “khắc phục”, nó lại phá entropy và ràng buộc PKCE.

**Giải pháp:** Tạo và lưu verifier **per-authorization transaction**, tra theo state/session phù hợp; kiểm tra callback, consume transaction và bảo vệ storage khỏi XSS.

### Tình huống C: Confidential BFF bỏ PKCE vì đã có client secret

Backend `sales-dashboard` dùng Authorization Code nhưng không gửi code challenge vì “token endpoint đã có Basic Auth”. Một số attack paths liên quan code interception/injection vẫn có thể là mối lo trong kiến trúc, nhất là qua redirect/proxy/browser.

**Phân tích:** Client authentication xác thực **ứng dụng**, còn PKCE ràng buộc **code với transaction**. Đây là hai bảo vệ bổ sung; không nên xem chúng đồng nghĩa.

**Giải pháp:** Bật S256 trên authorization request resolver, yêu cầu PKCE ở AS cho registration thích hợp, kiểm tra state/issuer/callback/session, giữ verifier phía server và kiểm thử HTTP /authorize + /token.

### Tình huống D: PKCE đúng nhưng service chấp nhận ID token như access token

Alice đăng nhập OIDC qua Code + PKCE thành công. Client nhận ID token `aud=sales-dashboard` và access token `aud=orders-api`. Do bug, frontend dùng ID token làm bearer token gọi `orders-api`; API chỉ kiểm tra chữ ký và `sub` nên trả dữ liệu.

**Phân tích:** PKCE hoàn thành đúng **giai đoạn authorization code redemption** nhưng không bảo vệ lỗi **token purpose/audience confusion** ở RS.

**Giải pháp:** Client gửi đúng AT được cấp cho orders; RS yêu cầu access-token profile, `iss`, chữ ký hoặc introspection, expected `aud`, `exp`, scope và quyền object. PKCE không thay các validator này.

## 17. Checklist triển khai PKCE an toàn trong production

### 17.1. Client registration và yêu cầu authorization

1. **Đúng flow:** Client đang sử dụng Authorization Code + PKCE, không mặc định implicit hay Resource Owner Password Credentials.
2. **Client type rõ:** SPA/native là public; backend/BFF có thể là confidential khi giữ credential đúng cách; không nhúng static secret vào public client.
3. **Trusted AS:** Issuer, authorization/token endpoints và metadata được cấu hình từ nguồn đáng tin; client không lấy URL từ code/JWT chưa xác minh.
4. **Redirect URI:** Đăng ký đúng, không wildcard/open redirect; native app áp redirect profile RFC 8252.
5. **PKCE S256:** Client sinh `code_verifier` mới cho từng transaction bằng CSPRNG 256-bit, dùng ASCII/SHA-256/Base64url không padding.
6. **Không downgrade:** AS yêu cầu S256 khi policy đã định; không fallback `plain` hoặc không PKCE nếu gặp lỗi.
7. **Transaction binding:** Challenge/method, `state`, issuer, client, redirect URI, scope và resource được ràng buộc với authorization transaction.
8. **Không lộ verifier:** Authorization request chỉ mang `code_challenge` và method, không mang raw verifier.

### 17.2. Token endpoint và AS

9. **Code single-use:** Authorization code ngắn hạn, chỉ một redemption thắng trên mọi AS nodes.
10. **PKCE binding:** AS so verifier với challenge/method đã lưu theo code; token request không được override binding.
11. **Client binding:** AS xác minh client ID/authentication, redirect URI và grant theo RFC/registration.
12. **Scope/audience:** Token chỉ mang granted scopes và resource đã được phép; S256 đúng không cho client tăng quyền.
13. **Error handling:** Mismatched/missing verifier, expired/reused code, sai client hoặc redirect đều bị từ chối không cấp token.
14. **Unknown outcome:** Timeout sau POST có thể xảy ra khi AS đã commit; client không retry mù quáng cùng code.
15. **Logging:** Token endpoint và reverse proxy không ghi raw code, verifier, access token, refresh token hoặc client secret.
16. **Transport:** Dùng HTTPS với certificate/hostname validation; không tự chuyển credential qua redirect sang host khác.

### 17.3. Sau khi nhận token

17. **Token purpose:** Client dùng OAuth access token gọi API, không dùng OIDC ID token hoặc refresh token.
18. **RS validation:** JWT/JWKS hoặc opaque introspection từ AS tin cậy, `iss`, `aud`, `exp`, scope và token profile.
19. **Domain authorization:** API xác minh tenant, owner, object-level ACL và actor/service policy.
20. **RT lifecycle:** Nếu có refresh token, AS/client phải thực hiện rotation hoặc sender constraint/reuse detection theo policy, single-flight và revocation.
21. **Token storage:** Browser/native/backend lưu token phù hợp threat model, hạn chế XSS/log leaks và credential persistence.
22. **Replay/threat model:** Nếu bearer AT bị lấy cắp, PKCE không cản replay; cân nhắc DPoP/mTLS-bound tokens khi rủi ro yêu cầu.
23. **QA:** Có test RFC vector, positive/negative PKCE, cross-client, code replay, multi-tab, multi-node, issuer mix-up và RS audience.

## 18. Câu hỏi tự kiểm tra

**Câu 1. `code_verifier` và `code_challenge` khác nhau thế nào?**

`code_verifier` là chuỗi ngẫu nhiên client giữ trong authorization transaction. `code_challenge` là giá trị công khai tính từ verifier bằng S256, gửi trong `/authorize`. Đến `/token`, client gửi verifier; AS tính lại và so với challenge đã gắn với code.

**Câu 2. Vì sao 32 bytes ngẫu nhiên tạo ra verifier 43 ký tự?**

Base64url mã hóa 256 bit thành 43 ký tự khi bỏ padding. Đây là một cách được khuyến nghị để đáp ứng độ dài 43–128 và entropy cao của RFC 7636.

**Câu 3. `code_challenge_method=plain` có an toàn tương đương S256 không?**

Không. `plain` đưa giá trị verifier ra front-channel authorization request. Triển khai hiện đại nên dùng S256 và policy chống downgrade.

**Câu 4. Client gửi `code_verifier` khi gọi `/authorize` để AS dễ kiểm tra hơn được không?**

Không. Làm vậy có thể làm lộ verifier ngay lúc bắt đầu flow. `/authorize` mang challenge/method; `/token` mới mang verifier qua HTTPS.

**Câu 5. Khi attacker chỉ có authorization code nhưng không có verifier, điều gì xảy ra?**

Nếu AS ràng buộc PKCE đúng, token request với verifier thiếu/sai bị từ chối. Đây là mục tiêu chính của PKCE chống code interception.

**Câu 6. PKCE có thay `state` và OIDC `nonce` không?**

Không. PKCE ràng buộc code redemption, `state` ràng buộc callback với authorization transaction/CSRF defense, còn OIDC `nonce` phục vụ ID token authentication binding khi áp dụng.

**Câu 7. Một confidential client đã dùng `client_secret_basic` có cần PKCE không?**

Vẫn nên áp PKCE trong Authorization Code flow theo thực hành hiện đại, vì client authentication xác minh client còn PKCE ràng buộc **authorization code cụ thể** với transaction. Không xem một cơ chế là bản sao của cơ chế kia.

**Câu 8. Vì sao callback có code hợp lệ nhưng token endpoint trả `invalid_grant`?**

Có thể verifier sai hoặc mất, code hết hạn/đã dùng, redirect URI/client binding không khớp, hoặc grant đã vô hiệu. Cần chẩn đoán theo thông tin an toàn, không bỏ PKCE để “chữa lỗi”.

**Câu 9. Nếu token request bị timeout, có thể gửi lại cùng code cho đến khi nhận 200 không?**

Không. AS có thể đã dùng code và cấp token nhưng response bị mất. Client phải xử lý unknown outcome/single-use và có thể bắt đầu authorization transaction mới.

**Câu 10. Sau PKCE thành công, API có thể bỏ kiểm tra `aud` vì code đã được bảo vệ không?**

Không. PKCE chỉ bảo vệ code redemption ở AS. Resource server vẫn phải yêu cầu access token đúng issuer/audience/expiry/scope và quyền nghiệp vụ.

**Câu 11. RFC 8693 Token Exchange có phải cùng request với `grant_type=authorization_code` + `code_verifier` không?**

Không. RFC 8693 dùng `subject_token` và optional actor context để xin token theo policy cho ngữ cảnh khác. PKCE áp dụng cho redemption authorization code, không mặc nhiên cho RFC 8693 Token Exchange.

**Câu 12. SPA có verifier mạnh thì đã chống XSS đánh cắp access token chưa?**

Chưa. XSS có thể lấy verifier nếu chạy trong app hoặc lấy AT sau issuance. Cần XSS defense, token storage phù hợp, TTL, rotation/revocation và sender constraint khi cần.

**Câu 13. Có thể dùng cùng verifier cho mọi user để tránh sai state giữa các tab không?**

Không. Verifier phải được tạo riêng, đủ entropy cho mỗi authorization transaction. Sửa transaction storage/multi-tab binding thay vì tái sử dụng bí mật.

**Câu 14. Client Credentials hoặc Refresh Token Grant có cần gửi `code_challenge` không?**

Không theo PKCE RFC 7636. Những grants đó không redeem authorization code; chúng có ràng buộc client/credential và replay protection riêng.

## 19. Tài liệu chuẩn tham khảo

- [RFC 7636 — Proof Key for Code Exchange by OAuth Public Clients](https://www.rfc-editor.org/rfc/rfc7636): định nghĩa `code_verifier`, `code_challenge`, `S256`, cú pháp và test vector Appendix B.
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): authorization code grant, client/redirect binding, token endpoint và code single-use.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): khuyến nghị PKCE, chống code injection/replay, giảm rủi ro OAuth hiện đại.
- [RFC 8252 — OAuth 2.0 for Native Apps](https://www.rfc-editor.org/rfc/rfc8252): external user-agent, redirect URI native, PKCE và loopback.
- [RFC 9207 — OAuth 2.0 Authorization Server Issuer Identification](https://www.rfc-editor.org/rfc/rfc9207): xác định issuer và giảm mix-up giữa AS.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): authorization/token endpoints và metadata.
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707): yêu cầu token cho đúng resource/audience.
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693): phân biệt token exchange grant với code redemption/PKCE.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): issuer, audience, scope, lifetime và access-token profile.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): bảo vệ bearer token khi gọi resource API và response lỗi.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662), [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): opaque access token, trạng thái và thu hồi.
- [RFC 8705 — OAuth 2.0 mTLS](https://www.rfc-editor.org/rfc/rfc8705), [RFC 9449 — OAuth 2.0 DPoP](https://www.rfc-editor.org/rfc/rfc9449): sender-constrained tokens sau khi cấp.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID token, OIDC nonce và các điều kiện xác minh client.
- [Spring Security — OAuth 2.0 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html), [OAuth 2.0 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html): authorization request resolver, PKCE và token handling.
- [Spring Authorization Server — Core Model Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): client settings và yêu cầu proof key.

**Điểm cần ghi nhớ:** **PKCE S256 gắn một authorization code với verifier ngẫu nhiên chỉ client của authorization transaction đó biết.** Client đưa `code_challenge` trong authorization request, giữ `code_verifier` và trình nó khi `POST /token` với `grant_type=authorization_code`; AS kiểm tra đúng challenge/method/client/redirect rồi **tiêu thụ code chỉ một lần**. PKCE bảo vệ **authorization code exchange**, không phải RFC 8693 Token Exchange hay giải pháp tự động cho token theft/replay sau khi AT/RT đã cấp. Muốn bảo vệ hệ thống trọn vẹn, phải kết hợp PKCE với `state`/OIDC `nonce`, client/issuer/redirect binding, TLS, audience/scope/TTL, token storage, refresh-token lifecycle và quyền nghiệp vụ tại resource server.
