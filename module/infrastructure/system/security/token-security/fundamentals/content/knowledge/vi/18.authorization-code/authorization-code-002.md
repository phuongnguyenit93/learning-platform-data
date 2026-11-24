# Client ID and redirect URI

Trong **OAuth 2.0 Authorization Code Flow**, Authorization Server (AS) cần biết **ứng dụng nào đang xin ủy quyền** và **nơi nào được phép nhận authorization response**. Hai thông tin then chốt của giao thức là `client_id` và `redirect_uri`:

- **`client_id`** là mã định danh AS cấp cho một OAuth client đã đăng ký; **không phải password hay bằng chứng xác thực client**.
- **`redirect_uri`** là URI mà AS được phép chuyển trình duyệt trở về khi trả authorization code (hoặc một lỗi ủy quyền thích hợp); URI phải thuộc các giá trị **đã đăng ký của đúng client**.

Giả sử client `invoice-web` đã đăng ký `https://app.example.test/oauth2/callback`. Nếu kẻ tấn công thay `redirect_uri` thành `https://attacker.invalid/receive-code` và AS vẫn redirect về đó, authorization code có thể bị chặn bắt. Đăng ký và kiểm chặt redirect URI hạn chế nguy cơ này, nhưng **không thay thế PKCE, state, client authentication và kiểm code một lần**.

Bài thuộc chương **Authorization Code** của module **Security Token Security Fundamentals**. Ta đặt hai tham số này trong mô hình tin cậy OAuth 2.0/OIDC và vòng đời token, đồng thời phân biệt callback của client với **audience của JWT/opaque access token**, scope và quyền thực tế trên Resource Server.

## 1. Xác định đúng các vai trò OAuth

| Vai trò | Trong ví dụ | Thông tin cần tin cậy |
|---|---|---|
| **Resource Owner** | Người dùng An | Phiên xác thực và grant/consent tại AS |
| **OAuth Client** | Ứng dụng hóa đơn `invoice-web` | `client_id`, redirect URIs, loại client, grant và client authentication policy |
| **Authorization Server** | `https://auth.example.test` | Client registry, issuer, authorization code và token endpoint |
| **Resource Server** | Invoice API | Access token có `aud=invoice-api`, scope và quyền tài nguyên |
| **User Agent** | Trình duyệt của An | Điều hướng từ client sang AS, rồi quay về callback với code/state |

Đừng coi `client_id` là người dùng. `client_id=invoice-web` **định danh ứng dụng**, còn `sub=user:an`, nếu xuất hiện trong token theo profile, **mô tả subject** được AS xác thực/ủy quyền. Một client có thể phục vụ rất nhiều người dùng.

Tương tự, callback URI thuộc client và **không phải địa chỉ Resource Server**. Access token do AS cấp có thể dành cho Invoice API, dù browser trở về `https://app.example.test/oauth2/callback`.

## 2. Client ID là mã định danh công khai

Một client registration minh họa:

~~~json
{
  "client_id": "invoice-web",
  "client_type": "public",
  "redirect_uris": [
    "https://app.example.test/oauth2/callback"
  ],
  "allowed_grants": ["authorization_code"]
}
~~~

JSON trên **không phải schema đăng ký bắt buộc của mọi AS**; các khóa chỉ để mô tả ý nghĩa. Thực tế AS có thể quản lý redirect URI, phương thức client authentication, grants, scope, consent, keys/JWKS và chính sách riêng theo client.

`client_id` thường đi qua front channel, xuất hiện trong URL authorization request và có thể quan sát trong trình duyệt, nên **không thể là secret**.

| Loại OAuth client | Có thể giữ secret dùng chung khỏi người sử dụng không? | Cách bảo vệ |
|---|---|---|
| **Confidential backend/BFF** | Có thể, nếu secret hoặc private key giữ server-side | Client authentication tại token endpoint + PKCE theo profile |
| **SPA thuần JavaScript** | Không | Authorization Code + PKCE; không nhúng client secret vào source |
| **Native mobile/desktop app** | Không thể giả định secret nhúng trong binary là bí mật | PKCE, redirect kiểu native và bảo vệ phiên/khóa phù hợp |
| **Workload service-to-service** | Có thể dùng workload credential | Client authentication, grant/resource/scope policy; thường không cần browser redirect với `client_credentials` |

Attacker biết `client_id` không có nghĩa họ được cấp token. AS cần kiểm **client registration, grant, authorization code được phát cho đúng client, redirect URI, PKCE và xác thực client nếu client là confidential**.

**Quy tắc:** `client_id` chỉ giúp AS tìm đúng cấu hình để thực thi chính sách. Không dùng một `client_id` tự khai làm bằng chứng danh tính người đang gửi HTTP request.

## 3. Redirect URI là địa chỉ callback, không phải token audience

Authorization endpoint có thể trả:

~~~http
HTTP/1.1 302 Found
Location: https://app.example.test/oauth2/callback?code=<redacted-code>&state=<state>
Cache-Control: no-store
~~~

Browser đi theo redirect đến client callback. Client kiểm transaction/`state` rồi đổi code tại **token endpoint của AS**. Trong Authorization Code Flow thông thường, access token và refresh token (nếu được cấp) đến từ **token response**, không được nhét vào callback URL.

### Ba địa chỉ không được đánh đồng

~~~text
Authorization endpoint:
  https://auth.example.test/authorize

Client redirect URI:
  https://app.example.test/oauth2/callback

Resource API:
  https://api.example.test/invoices
  token audience = invoice-api
~~~

Redirect URI xác định nơi nhận **authorization response**; token endpoint xác định nơi **đổi authorization code**; Resource Server là nơi **chấp nhận access token** trong audience và quyền đã cấp.

### Các thành phần redirect URI

~~~text
https://app.example.test:443/oauth2/callback?channel=web
 scheme | hostname       |port| path         |query
~~~

Trong OAuth 2.0, redirect endpoint URI **không được chứa fragment**. Một URI có thể chứa query tĩnh đã đăng ký; AS cần bảo toàn những tham số thuộc URI đã kiểm khi thêm authorization response. Đối với web public callback, ưu tiên **HTTPS, host/path cụ thể, không dựa vào query động để quyết định nơi chuyển tiếp**.

## 4. Kiểm redirect URI theo từng client và exact match

Giả sử registry của AS:

~~~text
Client invoice-web:
  https://app.example.test/oauth2/callback
  https://app.example.test/oauth2/secondary-callback

Client payroll-web:
  https://payroll.example.test/oauth2/callback
~~~

Một request với `client_id=invoice-web` **chỉ** được dùng redirect URI đã đăng ký cho `invoice-web`. URI của `payroll-web` không được dùng thay, dù hai ứng dụng thuộc một công ty.

Theo **RFC 9700 (OAuth 2.0 Security BCP)**, AS phải so khớp **chuỗi redirect URI chính xác** với giá trị đã đăng ký, trừ ngoại lệ cho **port của loopback redirect URI ở native app** theo RFC 8252. Không dùng wildcard, prefix hoặc phép so khớp gần đúng để mở rộng đích nhận code.

| Đã đăng ký | Trong authorization request | Kết quả theo exact match |
|---|---|---|
| `https://app.example.test/oauth2/callback` | Giống hệt | **Hợp lệ** nếu các điều kiện khác đạt |
| URI trên | `https://app.example.test/oauth2/callback/` | **Từ chối**: khác dấu `/` cuối |
| URI trên | `http://app.example.test/oauth2/callback` | **Từ chối**: khác scheme |
| URI trên | `https://app.example.test.evil.invalid/oauth2/callback` | **Từ chối**: khác host |
| URI trên | `https://app.example.test:8443/oauth2/callback` | **Từ chối**: khác port |
| URI trên | `https://app.example.test/OAuth2/callback` | **Từ chối**: khác ký tự path |
| URI trên | `https://app.example.test/oauth2/callback?next=https://evil.invalid` | **Từ chối** nếu query đó không nằm trong registration |

Không tự kết luận hai URI “gần giống” là tương đương sau normalize, bỏ dấu `/`, giải mã % nhiều lần hoặc viết regex tùy ý. Client và AS phải thống nhất URI đăng ký, cách biểu diễn hợp lệ và ngoại lệ chính xác theo profile. Nhiều triển khai từng bị khai thác qua so khớp prefix/suffix hoặc path normalization khác nhau.

### Mẫu so khớp thiếu an toàn

~~~text
UNSAFE:
  redirect_uri.startsWith("https://app.example.test")
  redirect_uri.contains("app.example.test")
  redirect_uri.endsWith("example.test/callback")
  allow "https://*.example.test/*"
~~~

**Không chấp nhận những mẫu đó** thay cho exact URI allowlist. Một subdomain ít được kiểm soát, domain trông giống tên hợp lệ hoặc callback có open redirect có thể trở thành nơi rò authorization code.

## 5. Luồng Authorization Code + PKCE từ đầu đến cuối

Hai kênh cần phân biệt:

- **Front channel:** trình duyệt từ client sang AS rồi quay về callback mang `code` và `state`.
- **Token request:** client trình code cùng verifier và client authentication (nếu có) tới token endpoint của **đúng AS**.

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng An
    participant B as Browser
    participant C as Client invoice-web
    participant AS as Authorization Server
    participant API as Invoice API
    U->>B: Mở ứng dụng
    B->>C: Bắt đầu liên kết OAuth
    C->>C: Tạo state + PKCE verifier/challenge
    C-->>B: Redirect tới authorization endpoint
    B->>AS: client_id + redirect_uri + state + code_challenge
    AS->>AS: Kiểm client registry và exact redirect URI
    AS->>U: Xác thực/consent theo policy
    U-->>AS: Hoàn tất tương tác
    AS-->>B: Redirect URI đã kiểm + code + state
    B->>C: Callback chứa code và state
    C->>C: Kiểm state/transaction và issuer nếu áp dụng
    C->>AS: POST /token: code + redirect_uri + verifier + client proof
    AS->>AS: Kiểm code chưa dùng, client/redirect/PKCE
    AS-->>C: Access token, ID/refresh token nếu được cấp
    C->>API: Authorization: Bearer access token
    API->>API: Kiểm issuer, aud, exp, scope và quyền tài nguyên
    API-->>C: Phản hồi theo quyền
~~~

Ở **SPA public client**, callback và code exchange có thể do browser thực hiện khi AS hỗ trợ token endpoint CORS; ở **BFF/backend**, code exchange diễn ra phía server. Dù ở mô hình nào, việc browser nhận được code không tự chứng minh client đủ quyền đổi code thành token.

## 6. Authorization request: hiểu từng tham số

Authorization request minh họa trong browser:

~~~http
GET /authorize?response_type=code&client_id=invoice-web&redirect_uri=https%3A%2F%2Fapp.example.test%2Foauth2%2Fcallback&scope=openid%20invoice%3Aread&state=<random-state>&code_challenge=<challenge>&code_challenge_method=S256 HTTP/1.1
Host: auth.example.test
~~~

`scope=openid` được dùng để minh họa khi client cũng thực hiện **OIDC**; nếu chỉ OAuth không dùng OIDC, scope có thể là `invoice:read` theo chính sách AS.

| Tham số | Chức năng | Cần kiểm gì? |
|---|---|---|
| `response_type=code` | Yêu cầu Authorization Code Flow | AS chỉ hỗ trợ grant/response type được đăng ký |
| `client_id` | Chọn client registry | Không xem là mật khẩu |
| `redirect_uri` | Callback nhận authorization response | Exact match với URI của client |
| `scope` | Quyền client xin | AS giới hạn theo grant/consent/resource policy |
| `state` | Liên kết response với transaction phía client | Khó đoán, gắn session và kiểm một lần |
| `code_challenge` | Commitment mật mã cho verifier | Lưu binding với authorization code |
| `code_challenge_method=S256` | Dùng SHA-256 theo PKCE | Không tự hạ xuống `plain` ngoài policy |
| `nonce` (nếu profile OIDC dùng) | Liên kết ID token với authentication request | Kiểm theo OIDC; không thay `state`/PKCE |

### State bảo vệ liên kết giữa request và callback

Client sinh `state` ngẫu nhiên không đoán được và lưu nó cùng **transaction/phiên đang chờ**, các tham số như client, issuer, redirect URI, verifier. Khi browser quay về, client phải đối chiếu, kiểm TTL và **consume một lần**. Nếu thiếu/sai state hoặc không có transaction chờ, phải **từ chối**, không thử đổi code để xem có thành công không.

Không chứa access token, refresh token, mật khẩu hoặc dữ liệu nhạy cảm không cần thiết trong state. Nếu muốn trở lại trang ứng dụng sau login, lưu đường dẫn nội bộ tin cậy trong transaction thay vì nhét URL mở sang bất kỳ domain nào.

### PKCE S256: bổ sung bảo vệ cho authorization code

~~~text
Client tạo:
  verifier = chuỗi ngẫu nhiên entropy cao cho một giao dịch
  challenge = BASE64URL(SHA256(ASCII(verifier))), không padding

Front channel:
  code_challenge=<challenge>
  code_challenge_method=S256

Token request:
  code_verifier=<verifier>

AS:
  chỉ cấp token nếu verifier khớp challenge gắn với code
~~~

PKCE giúp chống code interception/code injection và không làm `client_id` trở thành secret. `code_verifier` phải được bảo vệ trong transaction và **không đặt trong front-channel authorization URL**. Authorization Server phải tuân thủ thuật toán/độ dài theo RFC 7636 và ràng buộc verifier với chính code đã phát.

## 7. Callback sai redirect URI: xử lý lỗi tại AS

Nếu request có:

~~~text
client_id    = invoice-web
redirect_uri = https://attacker.invalid/receive-code
~~~

và URI không nằm trong registry của `invoice-web`, AS phải **từ chối authorization request tại AS**; **không** redirect đến URI đó để báo lỗi. Nếu làm thế, AS có thể gửi code hoặc thông tin ủy quyền cho một origin chưa được tin cậy.

Nếu client/redirect URI hợp lệ nhưng user từ chối consent, AS có thể gửi lỗi OAuth về **callback đã xác minh**, ví dụ:

~~~http
HTTP/1.1 302 Found
Location: https://app.example.test/oauth2/callback?error=access_denied&state=<state>
~~~

Client vẫn phải kiểm state, không đưa code/token/query nhạy cảm vào log. Lỗi auth không nên tiết lộ credential hay danh sách user/session.

### Callback hợp lệ vẫn có thể là open redirector

Một URI đăng ký `https://app.example.test/oauth2/callback` có thể được AS cho phép, nhưng nếu ứng dụng sau callback đọc tham số do attacker kiểm soát để `302 Location: https://attacker.invalid/` và chuyển tiếp code/state, bí mật có thể rò.

**Bảo vệ callback:** endpoint chuyên dụng; không có tham số chuyển hướng ngoài origin tùy ý; xử lý và xóa query chứa code trước khi đi trang khác; giữ Referrer-Policy, cache và logging phù hợp; chỉ cho điều hướng nội bộ đã được allowlist. **Exact redirect matching không thay thế kiểm soát open redirect tại client.**

## 8. Token endpoint phải ràng buộc code với client và redirect URI

Request đổi code minh họa cho **public client**:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.test
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&
code=<redacted-code>&
client_id=invoice-web&
redirect_uri=https%3A%2F%2Fapp.example.test%2Foauth2%2Fcallback&
code_verifier=<redacted-verifier>
~~~

Với confidential client, AS còn cần **client authentication** theo registration, chẳng hạn `client_secret_basic`, `private_key_jwt` hoặc mTLS; chỉ gửi `client_id` không đủ.

| Kiểm tại AS | Dữ liệu tin cậy | Nếu thất bại |
|---|---|---|
| Code do AS phát, còn hạn | Token/grant store | Từ chối grant |
| Code chưa dùng lần nào | Atomic single-use state | Từ chối replay |
| Code phát cho đúng client | Client binding đã lưu khi authorize | Từ chối cross-client |
| Redirect URI khớp authorization transaction | URI AS đã kiểm và gắn cùng code | Từ chối |
| PKCE verifier khớp challenge | Challenge đã gắn vào code | Từ chối |
| Grant và client còn được phép | Registry, policy, user consent | Không cấp token ngoài quyền |
| Scope/resource được xin hợp lệ | Authorization grant đã được duyệt | Không tự nâng scope/audience |

Theo **RFC 6749**, nếu client đã gửi `redirect_uri` trong authorization request, nó phải gửi **giá trị giống hệt** trong token request, và AS phải kiểm sự tương ứng. Với thiết kế hiện đại, nên lưu binding của redirect URI với code, gửi URI tường minh theo profile và không suy từ hostname của backend.

**Một code chỉ đổi được một lần.** Nếu hai AS replica nhận cùng code, trạng thái tiêu thụ phải nguyên tử, không cấp hai nhánh token. Nếu response thất lạc sau khi code được tiêu thụ, client thường phải bắt đầu authorization transaction mới; không chấp nhận “grace period cho code” chỉ để retry dễ dàng.

## 9. Redirect URI cho web, SPA, BFF và native app

Không có một loại redirect URI phù hợp cho mọi môi trường chạy. Kiến trúc client quyết định khả năng giữ bí mật, xử lý callback và các ngoại lệ giao thức.

| Kiến trúc | Redirect URI điển hình | Lưu ý về bảo mật |
|---|---|---|
| **Web backend/confidential client** | `https://app.example.test/login/oauth2/code/provider` | HTTPS, client authentication, state/CSRF, PKCE, session cookie |
| **SPA public client** | `https://app.example.test/oauth2/callback` | Authorization Code + PKCE S256; không nhúng client secret; token endpoint CORS nếu JS cần gọi |
| **BFF** | `https://app.example.test/bff/oauth2/callback` | Code exchange và access/refresh token giữ phía server, browser dùng session cookie có bảo vệ |
| **Native app với app-claimed HTTPS** | URI HTTPS gắn domain mà OS xác minh cho app | Hệ điều hành phải kiểm association; vẫn dùng PKCE |
| **Native app với private-use scheme** | `com.example.app:/oauth2redirect` | App khác có thể claim scheme; PKCE và state rất quan trọng |
| **Native app với loopback redirect** | `http://127.0.0.1:54872/callback` | Chỉ dùng địa chỉ loopback; port động theo RFC 8252, không mở wildcard cho web |

### 9.1. Web redirect: HTTPS và exact URI

Không đăng ký callback quá rộng:

~~~text
UNSAFE FOR PUBLIC WEB:
  http://app.example.test/oauth2/callback
  https://*.example.test/*
  https://app.example.test/redirect?next=*

SAFER:
  https://app.example.test/oauth2/callback
~~~

AS kiểm URI đăng ký của từng client. SPA chạy ở một origin khác với Invoice API vẫn có thể dùng callback trên origin của **SPA**; không thay bằng hostname của API chỉ vì API là nơi nhận bearer access token. CORS của token endpoint là vấn đề riêng với redirect URI validation.

### 9.2. BFF và callback giữ token ở phía server

Trong mô hình Backend For Frontend, browser đi tới AS rồi trở về BFF callback. BFF kiểm state và đổi code bằng kết nối server-to-server, nhận access/refresh token và chỉ trả **session cookie** cho browser.

- Token cần được lưu bảo vệ phía server; refresh token có rotation/reuse detection nếu được cấp.
- Session cookie nên dùng các thuộc tính `Secure`, `HttpOnly`, `SameSite` phù hợp.
- Endpoints dùng cookie phải có cơ chế chống **CSRF** và chống XSS.
- BFF vẫn phải kiểm issuer, PKCE, redirect URI và client authentication thích hợp; không được coi “cùng server” là lý do bỏ kiểm.

Nếu BFF và browser cùng origin, browser không cần CORS để gọi BFF, nhưng **Same-Origin Policy không thay thế CSRF/XSS defense** và không quyết định quyền gọi Resource Server.

### 9.3. Native app loopback: ngoại lệ port động

Theo **RFC 8252**, native app có thể mở HTTP listener trên địa chỉ **loopback** và chọn một cổng chưa dùng tại thời điểm chạy:

~~~text
Registration theo chính sách native loopback:
  http://127.0.0.1/callback

Authorization request tại runtime:
  redirect_uri=http://127.0.0.1:54872/callback
~~~

Đây là minh họa ngoại lệ **port động**: AS cần cho phép thay đổi port khi áp dụng cho native loopback redirect, đồng thời kiểm **scheme, loopback host/IP và path** theo registration/profile. Không mở rộng ngoại lệ thành `http://*`, wildcard path, hostname tùy ý hay redirect HTTP public của web app.

RFC 8252 ưu tiên địa chỉ loopback IP literal như `127.0.0.1` hoặc `[::1]` thay vì tên `localhost` vì rủi ro resolution/implementation. Listener chỉ bind giao diện loopback. Không giả định không có app khác cạnh tranh nhận code qua loopback, vì vậy **PKCE** là lớp phòng vệ quan trọng.

### 9.4. App-claimed HTTPS và private-use schemes

Native app có thể dùng app-claimed HTTPS URI khi OS liên kết domain với ứng dụng qua cấu hình hợp lệ, hoặc private-use scheme như `com.example.app:/oauth2redirect`. Private scheme có thể bị app khác đăng ký để nhận callback; app-claimed HTTPS thường có cơ chế xác minh ownership tốt hơn nếu triển khai đúng. **Cả hai vẫn cần PKCE** và giao dịch được gắn với đúng client/issuer/state.

## 10. Proxy, forwarded headers và cách sinh callback URI

Trong một hệ thống sau reverse proxy, backend đôi khi tự xây redirect URI từ request:

~~~text
scheme = X-Forwarded-Proto
host   = X-Forwarded-Host
path   = /login/oauth2/code/provider
~~~

Các header `X-Forwarded-*` có thể giúp backend nhận biết public URL, nhưng **không đáng tin nếu client internet có thể tự đặt chúng**. Nếu app dùng giá trị không được kiểm để sinh redirect URI, attacker có thể tạo host-header/forwarded-header poisoning.

~~~http
GET /login HTTP/1.1
Host: app.example.test
X-Forwarded-Host: attacker.invalid
X-Forwarded-Proto: https
~~~

Một backend thiếu kiểm soát có thể tạo `https://attacker.invalid/login/oauth2/code/provider`. AS **phải từ chối** vì không được đăng ký, nhưng lỗi ở client vẫn phải được sửa để tránh open redirect, sai URL hoặc token/callback leak ở những thành phần khác.

**Hướng xử lý:**

1. Cấu hình **public base URL** hoặc redirect URI cố định và được review cho từng môi trường.
2. Nếu cần forwarded headers, chỉ chấp nhận từ **proxy được tin**; proxy xóa header caller tự gửi và tự đặt giá trị được chuẩn hóa.
3. Bảo đảm redirect URI **sau khi expand template** trùng registration ở AS.
4. Không để query `provider`, `host` hoặc `next` không đáng tin quyết định issuer/redirect.
5. Không dùng URL nội bộ của pod/container để thay thế redirect URI public chỉ vì backend nhìn thấy hostname đó.

**Proxy rewrite không tự đổi `client_id`, `redirect_uri` hay `aud`.** Đó là các giá trị thuộc hợp đồng riêng của client registry, OAuth transaction và access token.

## 11. OAuth mix-up, code injection và callback CSRF

### 11.1. OAuth mix-up: response của AS A bị coi là của AS B

Một client hỗ trợ nhiều Identity Provider/AS có thể bị nhầm **issuer/token endpoint** nếu không ràng buộc authorization request và callback với đúng nhà phát hành.

**Phòng vệ:**

- Mỗi pending transaction lưu `expectedIssuer`, client registration, redirect URI, PKCE verifier và state.
- Dùng **RFC 9207 Authorization Server Issuer Identification** khi AS hỗ trợ: kiểm `iss` trong authorization response với issuer đã lưu.
- Trong OIDC, kiểm issuer và audience của ID token theo profile; không tự coi một bước kiểm ID token là giải pháp hoàn chỉnh cho mọi kiểu mix-up.
- Không gửi code đến token endpoint chỉ dựa vào query `provider`/`iss` do caller tự khai.
- Có thể dùng redirect URI riêng cho từng provider nếu kiến trúc cần, nhưng vẫn phải kiểm transaction binding.

### 11.2. Code injection: code của giao dịch khác

Attacker có thể cố gắn một authorization code khác vào callback của nạn nhân. Nếu client không kiểm state/transaction hoặc AS không kiểm PKCE, client có thể gắn phiên đăng nhập/ủy quyền trái ý muốn.

~~~text
Pending transaction T1:
  client_id       = invoice-web
  expected_issuer = https://auth.example.test
  redirect_uri    = https://app.example.test/oauth2/callback
  state           = random-S1
  code_verifier   = secret-V1
  expires_at      = short deadline

Callback:
  state phải bằng S1, thuộc đúng phiên
  issuer/AS phải khớp transaction
  T1 phải còn hạn và chưa được consume

Token endpoint:
  code phải thuộc client và redirect URI đã lưu
  code_verifier phải khớp challenge của code
  code chưa từng được đổi trước đó
~~~

**Không cố đổi code khi callback thiếu state hoặc không có transaction pending.** Callback an toàn kiểm các điều kiện trước khi gửi token request và không trả thông tin nhạy cảm cho caller ngoài.

### 11.3. State khác nonce

`state` thường được dùng để gắn callback với yêu cầu OAuth do client khởi tạo và phòng login CSRF. Với OpenID Connect, `nonce` có thể liên kết ID token với authentication request và chống replay theo profile. Không dùng nonce thay PKCE, không dùng state thay chữ ký/issuer/audience ID token và không coi một `state` ngắn dễ đoán là bảo vệ đủ.

### 11.4. Đăng nhập và consent UI

AS cần bảo vệ login/consent khỏi clickjacking và những thao tác đánh lừa người dùng theo browser security policy. Client không nên nhúng trang đăng nhập của AS vào iframe trái thiết kế; authorization flow thông thường dựa vào user agent điều hướng đến AS đáng tin. Những kiểm soát UI bổ sung cho kiểm client/redirect, không thay thế chúng.

## 12. Liên hệ JWT, opaque token, scope, audience và OIDC ID token

Sau khi code được đổi hợp lệ, AS cấp token tùy theo grant và profile. Format access token **không thay đổi vai trò của `client_id`/`redirect_uri` ở Authorization Code Flow**.

| Trường/đối tượng | Có ý nghĩa gì? | Không tự bảo đảm điều gì? |
|---|---|---|
| `client_id` | Client được đăng ký | Người gửi HTTP hiện tại là client thật |
| `redirect_uri` | Điểm client được nhận authorization response | Resource Server nào chấp nhận access token |
| Authorization `code` | Giá trị ngắn hạn để đổi token khi đủ binding | Quyền gọi API trực tiếp |
| `code_verifier` | Bằng chứng PKCE của transaction | Quyền nâng scope/audience |
| `state` | Liên kết callback với pending transaction | Xác minh chữ ký token |
| `scope` | Quyền được request/grant theo chính sách | Quyền trên mọi bản ghi |
| Access token `aud` | Resource Server được token hướng tới | Caller hiện giữ token là chủ thể thật |
| `iss` | Issuer tin cậy của token | Token còn hạn hoặc đủ quyền |
| Access token `sub` | Subject theo token profile | Thiết bị gửi token chính là của subject |

Ví dụ payload của **JWT access token** (chưa có chữ ký):

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "user:an",
  "aud": "invoice-api",
  "client_id": "invoice-web",
  "scope": "invoice:read",
  "iat": 1800000000,
  "exp": 1800000900
}
~~~

**Invoice API** phải xác minh chữ ký/issuer, audience, thời gian, loại/profile, scope và **quyền trên từng hóa đơn**. Một access token bearer bị đánh cắp có thể được dùng tại đúng API trong thời hạn còn lại; việc redirect URI được AS kiểm chính xác không ngăn mọi hành vi token theft về sau.

Với **opaque access token**, Resource Server có thể dùng introspection của AS để xác minh `active` và ngữ cảnh theo hợp đồng. Việc token không decode được tại client không thay kiểm scope/audience/owner.

**OIDC ID token** dành cho client/relying party, thường có `aud` là client ID; **không phải access token để gửi Invoice API**. Nếu AS cấp refresh token, nó đến từ token endpoint và được bảo vệ theo client và grant, **không được đưa vào callback URL**. Refresh rotation, reuse detection và revocation tiếp tục là những vấn đề của vòng đời token sau code exchange.

## 13. Java/Spring: cấu hình client và transaction binding

### 13.1. Spring Security OAuth2 Client

Cấu hình minh họa cho **confidential web app/BFF** dùng Spring Security 6.x:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          invoice-provider:
            client-id: invoice-web
            client-secret: "<load-from-secret-manager>"
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "https://app.example.test/login/oauth2/code/invoice-provider"
            scope:
              - openid
              - invoice:read
        provider:
          invoice-provider:
            issuer-uri: "https://auth.example.test"
~~~

Đây chỉ là **ví dụ cấu trúc**, không phải một cấu hình production hoàn chỉnh:

- Placeholder `client-secret` phải được resolve an toàn lúc chạy; **không commit secret plaintext vào Git**.
- AS phải đăng ký chính xác `client_id=invoice-web` và `https://app.example.test/login/oauth2/code/invoice-provider`.
- `issuer-uri` là issuer đã kiểm tin cậy, không do frontend quyết định.
- Phải cấu hình client authentication/PKCE/cookie/session/CSRF theo framework và profile được dùng.
- Đằng sau proxy, hãy kiểm trusted forwarded headers và public base URL.

Spring OAuth2 Client cũng thường hỗ trợ template `{baseUrl}/login/oauth2/code/{registrationId}`. **URI sau khi expand** phải đúng bản đăng ký ở AS. Không dùng `registrationId` như bằng chứng issuer hay access token audience.

### 13.2. Java 17: kiểm callback trước code exchange

Mã minh họa về trách nhiệm phía client, **không phải API nguyên mẫu của Spring**:

~~~java
final class AuthorizationCallbackHandler {
    private final PendingTransactionStore transactions;
    private final OAuthTokenClient tokens;

    AuthorizationCallbackHandler(
            PendingTransactionStore transactions,
            OAuthTokenClient tokens) {
        this.transactions = transactions;
        this.tokens = tokens;
    }

    TokenResponse handle(
            String browserSessionId,
            String returnedState,
            String authorizationCode,
            String returnedIssuer) {

        PendingOAuthTransaction tx =
            transactions.consumeOnce(browserSessionId, returnedState);
        if (tx == null || tx.isExpired()) {
            throw new InvalidOAuthCallbackException();
        }

        // Giả định AS dùng RFC 9207 để phát iss response.
        // AS khác cần mix-up defense tương ứng theo profile.
        if (!tx.expectedIssuer().equals(returnedIssuer)) {
            throw new InvalidOAuthCallbackException();
        }

        // Lấy token endpoint và client config từ registration
        // đáng tin, không suy từ query/Host trong callback.
        return tokens.exchangeAuthorizationCode(
            tx.clientRegistrationId(),
            authorizationCode,
            tx.registeredRedirectUri(),
            tx.codeVerifier());
    }
}
~~~

Các kiểu `PendingOAuthTransaction`, `OAuthTokenClient`, `TokenResponse` và exception là **kiểu ứng dụng minh họa**. Trong hệ thống thật, còn phải kiểm authorization error response, client authentication, nonce/ID token theo OIDC, quyền session, bảo vệ cookie, đường truyền HTTPS và lưu token. `consumeOnce` phải thực sự nguyên tử và kiểm transaction tương ứng **đúng phiên**, không nhận tùy ý transaction của người dùng khác.

Không coi `returnedIssuer` trong query là bằng chứng đủ khi chưa ràng buộc với expected AS, kiểm token endpoint metadata và những kiểm chứng giao thức liên quan. Đừng tự triển khai toàn bộ OAuth nếu có framework được bảo trì phù hợp.

### 13.3. Bất biến ở Authorization Server

~~~text
onAuthorize(request):
    client = registry.find(request.client_id)
    if not client:
        reject locally; never redirect to untrusted URI

    expectedRedirect = validateRegisteredRedirectUri(
        client, request.redirect_uri)
    if not expectedRedirect:
        reject locally; never redirect to supplied URI

    validate response_type/grant, PKCE challenge and parameters
    authenticate user and apply consent

    code = issueShortLivedSingleUseCode(
        clientId=client.id,
        redirectUri=expectedRedirect,
        pkceChallenge=request.code_challenge,
        subject=authenticatedSubject,
        grantedScopes=approvedScopes
    )
    redirect browser to expectedRedirect with code and state

onToken(request):
    authenticate/bind client as required by registration
    validate and atomically consume code (unexpired and unused)
    verify stored clientId and exact redirectUri binding
    verify PKCE verifier against challenge
    only grant scopes/resources authorized at authorize step
    issue access token and optional ID/refresh token
~~~

Đây là mã giả về **kiểm soát và thứ tự trách nhiệm**, không phải transaction production. Việc **atomic code consumption** phải được thiết kế cho nhiều instance AS để tránh phát token hai lần hoặc cấp token vượt quyền khi có race/exception.

## 14. Các lỗi triển khai thường gặp

| Sai lầm | Rủi ro | Sửa như thế nào? |
|---|---|---|
| Coi `client_id` là password | Attacker sao chép ID từ URL/source | Phân biệt ID công khai với client authentication/PKCE |
| Redirect allowlist dùng `https://*.example.test/*` | Subdomain/path ít tin cậy nhận code | Exact redirect URI theo từng client |
| So host bằng `contains`/`startsWith` | Host giả/tên giống hợp lệ được nhận | Kiểm exact URI, không dùng substring |
| Chỉ kiểm domain chung cho nhiều client | Client A dùng callback của client B | Registry/binding theo đúng `client_id` |
| Callback có `next=` mở tới host bất kỳ | Open redirect và code/state leakage | Callback chuyên dụng, chỉ điều hướng nội bộ tin cậy |
| Cho HTTP web callback production | Code có nguy cơ bị nghe lén trên mạng | HTTPS, chỉ ngoại lệ native loopback được profile hỗ trợ |
| Redirect lỗi tới URI chưa xác minh | Rò dữ liệu ủy quyền cho attacker | AS từ chối tại chính AS |
| Bỏ PKCE vì có client ID | Code interception/injection | PKCE S256, ràng buộc verifier đúng code |
| Bỏ state/transaction correlation | Login CSRF/mix-up/callback injection | State khó đoán, gắn phiên, dùng một lần |
| Code không gắn với client | Cross-client code substitution | Bind code với client registration |
| Token endpoint không so redirect URI | Token issuance trên code sai ngữ cảnh | So với authorization transaction theo chuẩn |
| Code được đổi hai lần do race | Attacker và client cùng lấy token | Atomic single-use authorization code |
| SPA/mobile nhúng client secret | Dễ trích secret từ mã/binary | Public client + PKCE, không coi secret là confidential |
| Chọn issuer theo `provider` query | OAuth mix-up, gửi code sai AS | Transaction issuer binding, kiểm RFC 9207 khi có |
| Nhầm redirect URI với `aud` | Sử dụng token sai Resource Server | RS kiểm audience riêng; callback không quyết định `aud` |
| Log raw callback query | Code lọt APM, browser history, ticket | Redaction, referrer/cache policy, dọn URL sớm |
| Dùng CORS thay redirect validation | Browser CORS không bảo vệ mọi redirect | AS kiểm URI, CORS chỉ điều khiển browser reads |

## 15. Ma trận kiểm thử client ID và redirect URI

Giả định:

~~~text
Issuer:       https://auth.example.test
Client ID:    invoice-web
Registered:   https://app.example.test/oauth2/callback
Flow:         Authorization Code + PKCE S256
Resource:     invoice-api, scope invoice:read
~~~

| Tình huống | Input/điều kiện | Kết quả kỳ vọng |
|---|---|---|
| **Đường thành công** | ID đúng, redirect exact, state/PKCE đúng | AS cấp code; đổi một lần thành token trong grant |
| **Client ID lạ** | `client_id=unknown` | AS từ chối, không redirect tới URI caller tự khai |
| **Biết client ID** | Attacker sao chép ID sang browser khác | Không có quyền cấp token chỉ vì biết ID |
| **Redirect của client khác** | invoice-web + URI của payroll-web | AS từ chối |
| **Hostname giả** | `https://app.example.test.evil.invalid/oauth2/callback` | AS từ chối |
| **Scheme khác** | `http://app.example.test/oauth2/callback` | AS từ chối web callback |
| **Path lệch một ký tự** | `/oauth2/callback/` thay `/oauth2/callback` | AS từ chối theo exact matching |
| **Query bổ sung** | `?next=https://evil.invalid` | Từ chối nếu chưa đăng ký URI đó |
| **Fragment** | `https://app.example.test/cb#token` | AS từ chối redirect URI không hợp lệ |
| **Wildcard host/path** | `https://*.example.test/*` | Registry/policy không chấp nhận wildcard thiếu an toàn |
| **Open redirect** | Callback chuyển tiếp tới website lạ | Không lộ code/token qua redirect |
| **State sai** | Callback có state không thuộc session | Client từ chối |
| **State dùng lại** | Replay callback đã xử lý | Client từ chối |
| **Code verifier sai** | Verifier không khớp challenge | AS không cấp token |
| **PKCE downgrade** | `code_challenge_method=plain` khi policy yêu cầu S256 | AS từ chối |
| **Code hết hạn** | Đổi sau TTL | AS từ chối |
| **Code replay** | Hai replica đổi cùng code | Tối đa một lần thành công |
| **Code client A tại B** | Code của invoice-web đổi bởi client B | AS từ chối |
| **Redirect ở token request sai** | Code gắn callback cũ, token request dùng URI khác | AS từ chối |
| **Client secret sai** | Confidential client không chứng minh đúng credential | AS trả lỗi xác thực, không cấp token |
| **Native loopback port** | Loopback URI đúng host/path, cổng động theo RFC 8252 | AS chấp nhận theo ngoại lệ port, không mở wildcard khác |
| **OIDC ID token sai** | Dùng ID token như access token | RS từ chối sai mục đích |
| **JWT audience sai** | `aud=profile-api` gọi Invoice API | RS từ chối dù callback trước đó hợp lệ |
| **Scope/tenant sai** | Có `invoice:read` nhưng hóa đơn không thuộc user | RS từ chối quyền dữ liệu |
| **Issuer mix-up** | Response từ AS A được xử lý như AS B | Client phát hiện và từ chối |
| **Forwarded header giả** | `X-Forwarded-Host: attacker.invalid` | Client không tạo redirect không tin cậy |
| **Code xuất hiện trong log** | Callback query được ghi APM/proxy | Redact, bảo vệ token/secret |

## 16. Bài tập tình huống: một công ty, hai client

AS quản lý:

~~~text
Invoice Web:
  client_id = invoice-web
  redirect_uri = https://app.example.test/oauth2/callback

Payroll Portal:
  client_id = payroll-web
  redirect_uri = https://payroll.example.test/oauth2/callback

Authorization Server:
  issuer = https://auth.example.test
  PKCE S256 bắt buộc cho cả hai client theo policy
~~~

Người dùng An bắt đầu authorization flow từ Invoice Web. Attacker sửa request thành:

~~~text
response_type=code
client_id=invoice-web
redirect_uri=https://payroll.example.test/oauth2/callback
scope=invoice:read
state=<attacker-chosen-state>
code_challenge=<attacker-challenge>
code_challenge_method=S256
~~~

**Câu 1: AS có được redirect code sang Payroll Portal vì cùng công ty không?**

**Không.** URI của `payroll-web` không thuộc registry `invoice-web`. AS phải từ chối authorization request mà không redirect code/error tới URI không hợp lệ.

**Câu 2: Nếu attacker đổi cả `client_id` thành `payroll-web` thì sao?**

AS đánh giá grant/URI của `payroll-web`, **không biến request thành một flow hợp lệ của Invoice Web**. Client nhận callback phải kiểm pending transaction, state, issuer và PKCE; biết client ID không tự cho attacker quyền đổi code.

**Câu 3: Attacker lấy được authorization code trong browser history. Họ đổi code được không?**

**Không nhất thiết.** Nếu AS kiểm PKCE đúng, attacker còn cần verifier; confidential client còn cần authentication. Code ngắn hạn, gắn client/redirect và single-use. Tuy nhiên rò code vẫn là sự cố phải ngăn, không coi PKCE là lý do được log code.

**Câu 4: Callback đã đăng ký nhưng có open redirect `next=` đến trang attacker. Vấn đề là gì?**

Ứng dụng có thể làm rò code/state qua redirect sau callback, nhất là nếu URI checking lỏng lẻo. Phải dùng callback chuyên dụng, xử lý code trước khi chuyển trang và chỉ chấp nhận đường điều hướng nội bộ được kiểm.

**Câu 5: Code được đổi thành access token `aud=invoice-api`. Có thể gọi Payroll API bằng token đó không?**

**Không**, nếu Payroll API kiểm audience đúng. Redirect URI chỉ quyết định nơi client nhận code; `aud` của access token xác định resource server dự kiến.

**Câu 6: Nếu `redirect_uri` ở token request khác với URI mà AS lưu khi phát code?**

AS phải từ chối theo ràng buộc redirect URI của authorization transaction. Code không được chuyển sang callback khác sau khi cấp.

**Câu 7: Native app có loopback callback `http://127.0.0.1:54872/cb`, AS có phải bắt buộc port cố định không?**

Không. RFC 8252 quy định ngoại lệ port động cho redirect URI loopback native app, trong khi host loopback, path và các phần khác vẫn cần được kiểm theo policy. Ngoại lệ này không áp dụng cho HTTP callback public web.

## 17. Checklist triển khai Authorization Code với client ID và redirect URI

1. **Client registration rõ ràng:** AS có `client_id`, loại client, grant, redirect URIs, authentication method và issuer đáng tin?
2. **Không coi client ID là secret:** Public client dùng PKCE; confidential client xác thực phía server, không chỉ gửi ID?
3. **Redirect URI theo client:** Không dùng một wildcard/allowlist chung cho mọi client?
4. **Exact matching:** AS so chính xác URI đăng ký; ngoại lệ native loopback chỉ cho port đúng profile?
5. **Xử lý redirect sai:** AS từ chối tại chỗ, không gửi code hoặc lỗi tới URI chưa xác minh?
6. **Callback không open redirect:** Không nhận `next` tùy ý, không chuyển code/token sang origin lạ, có referrer/cache/logging policy?
7. **PKCE S256:** Challenge đúng, verifier đủ entropy, lưu liên kết theo transaction và chống downgrade?
8. **State và issuer binding:** Callback thuộc đúng browser session/client/AS, state khó đoán, dùng một lần, mix-up defense theo profile?
9. **Code single-use:** Thời hạn ngắn, gắn client/redirect/PKCE, tiêu thụ nguyên tử trên nhiều AS instance?
10. **Token request đúng:** Kiểm client authentication, `redirect_uri`, code, verifier, scope và resource policy?
11. **SPA/native không cất secret giả:** Chọn flow/redirect URI đúng môi trường, không sao chép client secret vào mã frontend?
12. **Proxy đáng tin:** Public URL/forwarded headers cấu hình an toàn, không phụ thuộc `Host` do client khai?
13. **Không nhầm callback với `aud`:** Resource Server vẫn kiểm `iss`, `aud`, `exp`, `scope`, token profile, tenant/owner?
14. **Bảo vệ token sau code exchange:** Access token ngắn hạn, refresh token bảo vệ/rotation/revoke nếu cấp, không token trong URL/log?
15. **Kiểm thử âm tính:** Client sai, redirect sai ký tự, code replay, state/PKCE sai, mix-up, open redirect, native loopback và JWT sai audience?

**Ghi nhớ:** **`client_id` trả lời “OAuth client nào đã đăng ký đang yêu cầu ủy quyền?”, còn `redirect_uri` trả lời “AS được phép trả authorization response tới đâu cho chính client đó?”**. `client_id` là **định danh công khai**, không phải mật khẩu; `redirect_uri` cần **đăng ký và so khớp chính xác**, không wildcard hoặc substring tùy ý. Authorization code chỉ được đổi thành token sau khi **đúng client, đúng redirect transaction, PKCE verifier hợp lệ và code chưa dùng**. Cuối cùng Resource Server vẫn cần kiểm issuer, audience, scope, thời hạn và quyền từng tài nguyên.

### Chuẩn và tài liệu tham khảo

- **RFC 6749 — The OAuth 2.0 Authorization Framework:** client identifier, redirect endpoint và authorization code grant.
- **RFC 7636 — Proof Key for Code Exchange by OAuth Public Clients:** `code_verifier`, `code_challenge` và `S256`.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** redirect URI exact matching, PKCE và các bảo vệ OAuth hiện đại.
- **RFC 8252 — OAuth 2.0 for Native Apps:** app-claimed HTTPS, private-use URI scheme và loopback redirect/port động.
- **RFC 9207 — OAuth 2.0 Authorization Server Issuer Identification:** `iss` trong authorization response để phòng mix-up.
- **RFC 8414 — OAuth 2.0 Authorization Server Metadata:** issuer và endpoint metadata.
- **RFC 8707 — Resource Indicators for OAuth 2.0:** resource/audience khi xin token.
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** JWT access token, claims và token purpose.
- **RFC 7519 — JSON Web Token (JWT):** các claims `iss`, `sub`, `aud`, `exp`.
- **RFC 7662 — OAuth 2.0 Token Introspection:** ngữ cảnh và trạng thái opaque/reference access token.
- **OpenID Connect Core 1.0:** ID token, issuer, audience, nonce và redirect URI trong OIDC.
- **OWASP OAuth 2.0 Cheat Sheet:** PKCE, redirect URI, state, code interception và bảo vệ tích hợp client.
