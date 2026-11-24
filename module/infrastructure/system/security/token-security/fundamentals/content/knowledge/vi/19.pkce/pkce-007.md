# Public client protection

Một ứng dụng SPA chạy bằng JavaScript trong trình duyệt hoặc ứng dụng mobile được cài trên thiết bị của người dùng cần đăng nhập qua OAuth 2.0/OIDC. Ứng dụng có thể công bố `client_id`, nhưng **không thể giữ một client secret dùng chung như bí mật đáng tin**: mã nguồn JavaScript được tải về thiết bị, còn binary mobile có thể bị phân tích. Vậy Authorization Server (AS) làm cách nào để không cấp token cho người vừa chặn được **authorization code** trong đường chuyển hướng?

**PKCE (Proof Key for Code Exchange, đọc là “pixy”)** giải quyết phần quan trọng của bài toán này bằng cách gắn authorization code với một **bí mật ngắn hạn, ngẫu nhiên của riêng giao dịch**: `code_verifier`. Client gửi **`code_challenge`** đã dẫn xuất từ verifier ở authorization request, nhưng chỉ gửi **verifier thực** tại token endpoint. Khi đổi code, AS xác minh hai giá trị khớp nhau. Kẻ chỉ lấy được code từ callback **không đủ** điều kiện đổi code thành token.

**PKCE không biến public client thành confidential client và không làm access token trở thành sender-constrained.** Nếu attacker chiếm cả code và verifier, thực thi JavaScript trong chính origin của SPA, lấy access token sau khi cấp hoặc kiểm soát phiên người dùng, PKCE riêng lẻ không giải quyết được. Bài học cần đặt PKCE bên cạnh redirect URI validation, `state`, issuer binding, lưu trữ token, refresh token rotation và kiểm quyền tại Resource Server.

Đây là bài **“Public client protection”** thuộc chương **PKCE** của module **Security Token Security Fundamentals**. Mục tiêu: hiểu *public client được bảo vệ trước điều gì, giới hạn ở đâu và phải triển khai PKCE S256 ra sao* trong vòng đời OAuth 2.0/OIDC, dù AS cấp JWT hay opaque access token.

## 1. Public client là gì? Vì sao client ID không đủ?

OAuth 2.0 phân biệt client theo **khả năng giữ credential bí mật**, không phải theo việc ứng dụng có giao diện đẹp hay chạy trên điện thoại.

| Loại client | Ví dụ | Có thể bảo vệ client secret dùng chung khỏi người dùng cuối? | Chiến lược chính |
|---|---|---|---|
| **Public browser client** | SPA Vue/React chạy trên trình duyệt | **Không**: JS, bundle và nhiều dữ liệu runtime có thể bị người dùng quan sát | Authorization Code + PKCE; bảo vệ callback, JS, token và phiên |
| **Public native client** | Ứng dụng Android, iOS, desktop được cài trên thiết bị | **Không được mặc định**: secret nhúng trong binary có thể bị trích xuất | External browser + Authorization Code + PKCE; redirect native an toàn |
| **Confidential web client / BFF** | Backend giữ secret/private key phía server | **Có thể**, nếu hạ tầng và secret storage được bảo vệ | Client authentication **và** PKCE, session/CSRF protection |
| **Confidential workload** | Worker service-to-service | **Có thể**, qua workload identity/private key/secret manager | Client Credentials hoặc grant phù hợp; PKCE không liên quan nếu không dùng authorization code |

`client_id` là **định danh public do AS cấp cho client**. Nó giúp chọn client registration: redirect URIs, grant types, scopes, client authentication method và policy. Nó **không chứng minh** request đến từ bản cài app “chính hãng”.

Ví dụ, attacker sao chép `client_id=mobile-invoices` từ binary ứng dụng rồi tự gửi authorization request. Điều đó không tự cho attacker quyền lấy token của An. AS còn cần xác thực/consent người dùng, bảo đảm authorization code gắn đúng request, kiểm PKCE và redirect URI. Nhưng PKCE cũng **không chứng minh app binary là bản gốc**: một public client hợp lệ không có secret dùng chung để làm căn cứ bí mật duy nhất.

### Public client không đồng nghĩa “không cần bảo mật”

Không giữ được một **secret dùng chung** không có nghĩa bỏ mọi biện pháp bảo vệ. Client vẫn cần:

- Đăng ký `redirect_uri` chính xác và được AS xác minh.
- Tạo `state`/transaction riêng cho mỗi lần authorization; kiểm callback.
- Sử dụng PKCE `S256` và bảo vệ verifier cho đến lúc đổi code.
- Kiểm issuer/AS mong đợi khi có nhiều provider và xác minh ID token nếu dùng OIDC.
- Không để access/refresh token lộ qua URL, log, telemetry hoặc mã JavaScript không tin cậy.
- Giới hạn scope, audience, expiry và quyền dữ liệu; bảo vệ refresh token theo BCP.

## 2. PKCE bảo vệ bước nào trong OAuth 2.0?

Authorization Code Flow gồm hai bước cấp dữ liệu ủy quyền:

1. **Authorization endpoint**: browser được điều hướng tới AS, người dùng xác thực/consent; AS trả về **authorization code** qua redirect URI của client.
2. **Token endpoint**: client gửi code cho AS để đổi access token, và có thể ID token/refresh token theo grant.

**Không có PKCE:** một code bị chặn bắt có thể bị thử đổi tại token endpoint, đặc biệt khi public client không có phương thức client authentication đủ bí mật.

**Có PKCE S256:** AS đã gắn code với challenge; token endpoint còn yêu cầu **verifier tương ứng**. Một code riêng lẻ không đủ đổi token.

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng An
    participant C as SPA / Mobile Public Client
    participant B as Browser / External User Agent
    participant AS as Authorization Server
    participant X as Attacker chỉ có code
    C->>C: Sinh verifier bí mật V, challenge=S256(V)
    C->>B: Khởi tạo authorization request
    B->>AS: client_id, redirect_uri, state, challenge, method=S256
    AS->>AS: Kiểm client, redirect URI, policy/PKCE
    AS->>U: Đăng nhập và consent
    U-->>AS: Hoàn thành
    AS-->>B: Redirect với code C0 và state
    B-->>C: Callback với code C0
    Note over X: Attacker có thể nghe được C0
    X->>AS: POST /token: code C0, verifier sai/thiếu
    AS-->>X: invalid_grant; không cấp token
    C->>C: Kiểm state, issuer/transaction
    C->>AS: POST /token: code C0 + verifier V
    AS->>AS: Kiểm code single-use, client/redirect và S256(V)
    AS-->>C: Access token nếu mọi điều kiện hợp lệ
~~~

Sơ đồ mô tả attacker chỉ nắm code và thứ tự request minh họa. Nếu attacker gửi code sai verifier trước client, AS có thể chặn/ghi nhận lạm dụng hoặc làm thất bại giao dịch tùy chính sách; điều đó **không tạo quyền cấp token cho attacker**. Nếu chính attacker đã có **cả verifier**, điều kiện bảo vệ của PKCE bị vượt qua.

**PKCE bảo vệ authorization code exchange**, không phải mọi lần API sử dụng access token. Một bearer access token đã được cấp, nếu bị sao chép, có thể được sử dụng tại đúng Resource Server trong thời hạn và scope được phép trừ khi có cơ chế sender-constraining/thu hồi khác.

## 3. `code_verifier`: bí mật ngắn hạn cho từng transaction

Theo **RFC 7636**, `code_verifier` là một chuỗi ngẫu nhiên có entropy cao, dùng **riêng cho một authorization request**, có độ dài **43–128 ký tự** trong bảng ký tự không dành riêng của URI (unreserved): chữ cái ASCII, chữ số, `-`, `.`, `_` và `~`.

Một cách an toàn, đơn giản là:

1. Dùng **CSPRNG** (cryptographically secure random number generator) tạo **32 byte ngẫu nhiên**.
2. Mã hóa Base64URL **không padding** thành chuỗi dài **43 ký tự**.
3. Lưu verifier cùng transaction chờ ở client; **không gửi verifier qua authorization URL**.
4. Xóa hoặc đánh dấu transaction đã dùng sau callback/code exchange; không tái dùng verifier giữa nhiều lần login.

~~~text
Authorization transaction T1:
  client_id        = invoice-spa
  expected_issuer  = https://auth.example.test
  redirect_uri     = https://app.example.test/oauth2/callback
  state            = random-state-S1
  code_verifier    = random-verifier-V1 (SECRET)
  code_challenge   = S256(V1) (PUBLIC COMMITMENT)
  expires_at       = short deadline
~~~

**Không sử dụng** `Math.random()`, timestamp, user ID, email, device ID, UUID suy đoán được hoặc chuỗi hardcode chung cho mọi phiên làm PKCE verifier. CSPRNG trong browser là `crypto.getRandomValues`; trong Java có `SecureRandom`; native platform dùng nguồn ngẫu nhiên mật mã được hỗ trợ.

### `state` và `code_verifier` không nên là một chuỗi duy nhất

Hai giá trị có mục đích khác:

- **`state`** được gửi và trả qua front channel để client so callback với authorization request, chống login CSRF/callback injection; nó được **công khai** trong URL.
- **`code_verifier`** phải được giữ khỏi front channel, rồi xuất trình **chỉ tại token endpoint** qua TLS để chứng minh transaction đã tạo challenge.

Có thể sinh hai giá trị từ CSPRNG độc lập, gắn chung vào một transaction. Không dùng thẳng `state` công khai làm verifier, vì như vậy attacker đã đọc được bí mật cần bảo vệ.

## 4. `code_challenge` và phương thức `S256` hoạt động thế nào?

Với phương thức `S256`:

\[
\operatorname{code\_challenge} =
  \operatorname{BASE64URL\_NO\_PADDING}
  \bigl(\operatorname{SHA256}(\operatorname{ASCII}(\operatorname{code\_verifier}))\bigr)
\]

Định nghĩa theo RFC 7636 là **SHA-256 trên chuỗi ASCII của verifier**, mã hóa kết quả **Base64URL, bỏ ký tự padding `=`**. Vì SHA-256 trả 32 byte, challenge được mã hóa thường dài **43 ký tự**.

~~~text
Verifier V (chỉ client giữ trong transaction)
    |
    | ASCII encoding
    v
SHA-256(V) -> 32 byte digest
    |
    | BASE64URL, không dấu "=" padding
    v
Challenge C (được gửi tới authorization endpoint)

AS lưu C với authorization code.
Khi đổi code: AS tự tính S256(V') và so với C đã lưu.
~~~

### Ví dụ kiểm chứng từ RFC 7636

Đây là **test vector chuẩn** của RFC 7636, giúp kiểm tra implementation:

~~~text
code_verifier:
  dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk

code_challenge_method:
  S256

code_challenge:
  E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM
~~~

Chuỗi trên là **test vector công khai**, không phải verifier để sử dụng cho người dùng thật. Trong production, mỗi authorization transaction phải sinh verifier mới.

### `plain` có nên dùng không?

RFC 7636 có phương thức `plain`, nghĩa là challenge chính là verifier; khi verifier/challenge đều xuất hiện trong front channel, rủi ro bị chặn đồng thời tăng. Với public client hiện đại, **ưu tiên và áp đặt `S256`** theo chính sách bảo mật, không tự hạ từ `S256` sang `plain` chỉ vì AS phản hồi lỗi.

Nếu AS/client dự kiến `S256`, việc bỏ `code_challenge_method` có thể dẫn đến mặc định theo đặc tả ở một số triển khai; không dùng mặc định mơ hồ. Hãy **khai báo tường minh `code_challenge_method=S256`** và kiểm AS đã ghi nhận chính phương thức đó.

## 5. Hai điểm kiểm tra tại Authorization Server

Để PKCE có tác dụng, AS phải **bắt buộc PKCE ở authorization endpoint** và **kiểm challenge ở token endpoint**, với state được gắn vào cùng authorization code.

### 5.1. Khi nhận authorization request

~~~http
GET /authorize?response_type=code&client_id=invoice-spa&redirect_uri=https%3A%2F%2Fapp.example.test%2Foauth2%2Fcallback&scope=invoice%3Aread&state=<state-redacted>&code_challenge=<challenge>&code_challenge_method=S256 HTTP/1.1
Host: auth.example.test
~~~

AS phải kiểm:

| Kiểm soát | Vì sao quan trọng? |
|---|---|
| Client đã đăng ký và được dùng `response_type=code` | Chọn chính sách chính xác; `client_id` tự khai không đủ |
| `redirect_uri` khớp registration của chính client | Không gửi code đến URI lạ |
| Public client có PKCE `S256` theo policy | Không cấp code “không bảo vệ” rồi cho đổi dễ dàng |
| `code_challenge` đúng cú pháp/độ dài cho method | Tránh challenge không hợp lệ/bypass |
| Scope/resource và consent phù hợp | Không tăng quyền vì client xin thêm |
| AS lưu challenge và method với authorization code | Token endpoint biết expected PKCE proof từ nguồn đáng tin |
| Authorization code ngắn hạn và chỉ một lần | Hạn chế replay và chuyển giao code |

### 5.2. Khi nhận token request

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.test
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&
client_id=invoice-spa&
code=<authorization-code-redacted>&
redirect_uri=https%3A%2F%2Fapp.example.test%2Foauth2%2Fcallback&
code_verifier=<verifier-redacted>
~~~

AS cần tra code đã phát và kiểm **một cách đáng tin**:

1. Code tồn tại, còn hạn, **chưa được dùng**; áp dụng atomic single-use trong môi trường nhiều instance.
2. Code đã được phát cho **đúng client ID**; confidential client còn phải xác thực theo registration nếu là loại phù hợp.
3. `redirect_uri` trùng URI đã dùng ở authorization request theo hợp đồng OAuth.
4. PKCE challenge/method của code tồn tại và hợp lệ; **tính lại S256 từ verifier** được cung cấp và so sánh với challenge đã lưu.
5. Grant, scope, subject và resource/audience được cấp vẫn nằm trong policy; không tự nâng quyền từ tham số token request.
6. Sau khi mọi điều kiện hợp lệ, **tiêu thụ code đúng một lần** trong transaction nhất quán rồi cấp token.

**Quan trọng:** Không chấp nhận token request thiếu verifier khi code yêu cầu PKCE. Cũng không cho client gửi một verifier và tự bổ sung challenge tại token endpoint rồi xem như đã chứng minh gì đó; challenge **phải được gắn với authorization request ban đầu**.

## 6. Sơ đồ tin cậy: PKCE không thay thế điều gì?

| Cơ chế | Đối tượng nó bảo vệ | PKCE có thay thế không? |
|---|---|---|
| **Client authentication** | Confidential client chứng minh credential của mình tại AS | **Không** |
| **Redirect URI validation** | Không chuyển authorization code đến callback lạ | **Không** |
| **`state` / transaction correlation** | Không chấp nhận callback không thuộc request/phiên chờ | **Không hoàn toàn**; phải áp dụng CSRF defense theo profile |
| **Issuer binding / mix-up defense** | Không gửi code tới AS sai hoặc coi response AS A là của B | **Không** |
| **OIDC `nonce`/ID token validation** | Liên kết ID token với authentication request; kiểm ID token đúng issuer/audience | **Không** |
| **Access token validation** | RS xác minh chữ ký/introspection, `iss`, `aud`, `exp`, `scope` | **Không** |
| **Object-level authorization** | API kiểm người dùng/tenant có quyền trên dữ liệu | **Không** |
| **Refresh token rotation/sender-constraining** | Hạn chế refresh token bị đánh cắp và phát lại | **Không** |
| **DPoP/mTLS sender-constrained access token** | Yêu cầu bằng chứng khóa/chứng chỉ khi dùng access token | **Không** |
| **TLS/XSS/storage protection** | Giảm lộ code, verifier và token trong quá trình chạy | **Không** |

### PKCE không bảo vệ hoàn toàn khi attacker kiểm soát client runtime

Attacker có mã JavaScript thực thi trong **cùng origin của SPA** có thể:

- Đọc verifier trong memory/storage nếu mã độc chạy đúng lúc.
- Tạo authorization transaction khác từ bên trong SPA.
- Lấy access token sau code exchange hoặc tự gọi API bằng quyền ứng dụng.
- Gửi dữ liệu phản hồi, scope hoặc token sang máy khác.

PKCE không có cơ chế “phân biệt mã JavaScript tốt và xấu trong cùng origin”. Phải phòng **XSS**, hạn chế third-party script, cấu hình CSP phù hợp, cân nhắc BFF và bảo vệ chuỗi token ở các ranh giới tin cậy.

### PKCE cũng không làm token bearer thành proof of possession

Nếu access token là **Bearer**, ai có chuỗi token hợp lệ có thể thử dùng tại đúng RS theo audience/scope/expiry, dù họ không biết `code_verifier` đã dùng trước đó. PKCE bảo vệ **đường cấp token thông qua code**, không ràng buộc **mỗi API request sau khi cấp**. Nếu yêu cầu chống sử dụng access token bị sao chép đơn lẻ, cân nhắc **DPoP (RFC 9449)** hoặc **certificate-bound tokens (RFC 8705)** cùng kiểm tại RS.

## 7. SPA public client: PKCE trong môi trường JavaScript

Một SPA không nên nhúng `client_secret` vào JavaScript bundle, biến môi trường build được đẩy lên CDN hoặc source map. Dù tên biến là `SECRET`, người dùng có thể tải và đọc giá trị khi ứng dụng chạy.

### Quy trình thiết kế SPA

1. Khi người dùng nhấn **Đăng nhập**, sinh **`state` và `code_verifier` mới** bằng `crypto.getRandomValues`.
2. Tạo `code_challenge` bằng Web Crypto SHA-256 và Base64URL không padding.
3. Lưu pending transaction theo browser session/tab, gồm expected issuer, client ID, redirect URI, verifier, state, TTL; không để script origin khác truy cập.
4. Dùng **top-level navigation/redirect** tới authorization endpoint đáng tin; không dùng AJAX để “mở login form rồi copy HTML” trừ khi profile AS thực sự hỗ trợ.
5. Tại callback, lấy code và state; kiểm transaction **trước** code exchange.
6. Gửi code + verifier tới token endpoint qua HTTPS, theo client registration; nếu browser cross-origin, AS phải cấu hình CORS phù hợp.
7. Giữ access token và refresh token theo threat model; tránh lưu secret dài hạn không cần thiết trong JavaScript-readable storage.

~~~mermaid
flowchart TD
    S["SPA: user bắt đầu đăng nhập"] --> G["CSPRNG: state và verifier V"]
    G --> H["S256(V) thành challenge C"]
    H --> A["Browser redirect tới AS với C và state"]
    A --> B["AS kiểm client, redirect và PKCE policy"]
    B --> D["AS cấp authorization code một lần"]
    D --> E["Browser callback: code và state"]
    E --> F{"State/issuer/transaction hợp lệ?"}
    F -- "Không" --> Z["Từ chối callback; không đổi code"]
    F -- "Có" --> T["POST /token: code + verifier V"]
    T --> K{"AS kiểm S256(V)=C và code binding?"}
    K -- "Không" --> X["invalid_grant"]
    K -- "Có" --> R["Cấp access token theo grant"]
~~~

### Lưu verifier ở đâu?

`code_verifier` chỉ cần sống **trong một authorization transaction**, không phải credential dài hạn. Với SPA có full-page redirect, cần bảo toàn pending transaction qua trang rời đi/quay lại: có thể dùng **session storage theo tab**, hoặc cách quản lý transaction/session được OAuth client SDK tin cậy hỗ trợ; nếu dùng cookie/BFF, có thể giữ verifier **phía server**.

Không có nơi lưu nào tuyệt đối miễn nhiễm XSS nếu JavaScript cùng origin có thể đọc/điều khiển transaction. `sessionStorage` giới hạn vòng đời theo tab nhưng **không chống XSS**. `localStorage` thường tồn tại lâu hơn và dễ trở thành nơi tập trung bí mật. Nếu transaction bị mất khi browser quay lại, hãy **khởi tạo flow mới**, không bỏ PKCE để “tự động khôi phục đăng nhập”.

### CORS không phải OAuth authentication

Authorization endpoint thường được truy cập bằng **browser navigation**. Với public SPA, **token endpoint** có thể cần CORS khi SPA dùng `fetch` cross-origin để đổi code; chính sách CORS là quyết định của AS. CORS cho phép JavaScript của origin nhất định đọc response, **không** chứng minh public client có secret, không thay `redirect_uri` validation/PKCE và không bảo vệ API khỏi `curl` dùng token bị lộ.

Nếu AS không hỗ trợ token endpoint CORS cho browser client, không lách bằng một proxy mở không kiểm soát; cân nhắc **BFF hoặc kiến trúc client khác** được AS hỗ trợ.

## 8. Native app: PKCE chống code interception tại redirect

Mobile/desktop là public client vì attacker có thể trích credential khỏi binary hoặc chiếm một số đường callback. **RFC 8252** mô tả các kiểu redirect cho native apps và khuyến nghị sử dụng **external user-agent** thay vì nhúng login vào embedded WebView do ứng dụng kiểm soát.

| Redirect type | Ví dụ | Rủi ro | Cách phòng vệ |
|---|---|---|---|
| **Private-use URI scheme** | `com.example.invoice:/oauth2redirect` | App khác có thể đăng ký cùng scheme để nhận code | PKCE S256, state, association/OS policy nếu có |
| **App-claimed HTTPS redirect** | `https://login.example.test/mobile/callback` | Sai cấu hình association hoặc domain | OS-verified association, PKCE và callback validation |
| **Loopback interface** | `http://127.0.0.1:53217/callback` | App khác có thể cạnh tranh port/listener; nhầm bind ra public interface | Chỉ bind loopback, cổng động theo RFC 8252, PKCE và state |

### Loopback port là một ngoại lệ có giới hạn

Trong native app, AS cần hỗ trợ thay đổi **port** của loopback URI khi áp dụng RFC 8252. Đây là ngoại lệ cho **cổng**, không phải giấy phép mở wildcard host/path hoặc chấp nhận callback HTTP public.

~~~text
Registered native loopback:
  http://127.0.0.1/callback

Runtime authorization request:
  redirect_uri=http://127.0.0.1:53217/callback

Must remain constrained:
  scheme = http (chỉ cho local loopback trong profile này)
  host   = 127.0.0.1
  path   = /callback
  port   = dynamic được phép
~~~

Ưu tiên địa chỉ loopback IP literal như `127.0.0.1` hoặc `[::1]` thay vì phụ thuộc `localhost` và độ tin cậy của quá trình phân giải tên. Listener phải bind thật sự ở loopback, không mở ra mọi interface.

### Nếu một app khác chặn được code thì sao?

Giả sử app độc hại đăng ký cùng URI scheme và nhận callback `code=C0`. Nếu client thật dùng PKCE S256, app độc hại **không có verifier V0** và token endpoint sẽ không cấp token chỉ từ C0. Đây chính là một threat model quan trọng khiến PKCE thiết yếu cho native apps.

Tuy nhiên, nếu app độc hại cũng lấy được verifier từ bộ nhớ/IPC/log của ứng dụng thật, hoặc có quyền điều khiển app, PKCE không còn đủ. Native client cần dùng secure storage cho credential dài hạn, hạn chế debug log, tách IPC, cập nhật app và bảo vệ runtime.

## 9. `state`, issuer, nonce và các kiểu injection

PKCE giảm code interception, nhưng tích hợp OAuth an toàn còn phải đối phó **login CSRF, code injection và AS mix-up**.

### 9.1. State gắn callback với request

Một pending transaction nên chứa:

~~~text
PendingAuth(T1):
  state           = S1 ngẫu nhiên
  client_id       = invoice-spa
  issuer          = https://auth.example.test
  redirect_uri    = https://app.example.test/oauth2/callback
  code_verifier   = V1 ngẫu nhiên
  created_at      = trusted client time
  consumed        = false
~~~

Client phải từ chối callback nếu state thiếu, sai, hết hạn hoặc đã được tiêu thụ. Đánh dấu transaction dùng một lần để tránh hai callback chạy song song cùng cố đổi code. **Không nhận code đến từ tab/phiên khác chỉ vì hostname callback trùng**.

### 9.2. AS mix-up

Khi client hỗ trợ nhiều AS, attacker có thể cố khiến code từ AS A được gửi tới token endpoint của AS B. Client cần liên kết **issuer/AS mong đợi với transaction**. Nếu AS hỗ trợ **RFC 9207**, so tham số `iss` của authorization response với issuer đã lưu; nếu không, cần một mix-up defense phù hợp với profile (ví dụ redirect URI riêng cho provider và transaction binding).

Không lấy token endpoint từ query `provider` của callback chưa được xác minh. Với OIDC, kiểm `iss` và `aud` của ID token đúng profile sau token exchange.

### 9.3. OIDC `nonce`

`nonce` liên kết ID token với authentication request trong các OIDC flow áp dụng và hỗ trợ chống replay ID token. Nó **không thay PKCE**: có một ID token hợp lệ không chứng minh authorization code trước đó đã được đổi đúng transaction nếu AS/client bỏ PKCE. Ngược lại, PKCE không thay kiểm issuer, audience, chữ ký, expiry và nonce ID token.

### 9.4. Client injection và app impersonation

Một attacker có thể khởi tạo **authorization request riêng** với `client_id` public và `code_verifier` họ tự biết. PKCE sẽ bảo vệ transaction của **attacker**, không xác minh ứng dụng của họ là binary chính hãng. AS vẫn phải kiểm đúng redirect URI, tương tác người dùng, consent, policy và các tín hiệu chống lạm dụng; cơ chế app attestation nếu được dùng là **lớp bổ trợ**, không thay PKCE và authorization.

## 10. PKCE và bearer/refresh token security là các giai đoạn khác nhau

Một authorization code có thể được đổi thành access token dạng **JWT** hoặc **opaque**. PKCE không phụ thuộc access token format và không thay resource server token validation.

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "user:an",
  "aud": "invoice-api",
  "client_id": "invoice-spa",
  "scope": "invoice:read",
  "iat": 1800000000,
  "exp": 1800000900
}
~~~

Đây chỉ là **payload JWT minh họa**. Invoice API phải kiểm chữ ký/issuer, `aud`, thời gian, loại token, `scope` và quyền trên từng hóa đơn. Với opaque token, RS có thể dùng introspection đáng tin theo RFC 7662. Việc AS đã xác minh PKCE **không cho phép RS bỏ kiểm quyền**.

| Sự cố | PKCE có giải quyết không? | Bổ sung cần thiết |
|---|---|---|
| App độc hại chỉ lấy được **authorization code** | **Có thể ngăn code exchange** nếu verifier vẫn bí mật | Code single-use, redirect matching, TLS |
| Kẻ tấn công lấy được **code + verifier** | **Không đủ** | Bảo vệ runtime, XSS/IPC/log, issuer/client binding |
| Bearer access token bị lấy sau khi cấp | **Không** | TTL ngắn, audience/scope hẹp, sender-constraining, revoke/giám sát |
| Refresh token bị lấy | **Không** | Rotation/reuse detection hoặc sender-constraining theo BCP; storage an toàn |
| Thay access token `aud=api-B` dùng ở api-A | **Không** | RS kiểm audience và issuer |
| Token có scope nhưng truy cập object của tenant khác | **Không** | Object-level authorization tại RS |
| AS cấp code cho redirect URI không đăng ký | **Không** | Exact redirect URI matching |
| XSS trong origin của SPA | **Không** | Output encoding, CSP lớp bổ trợ, giảm quyền script, BFF khi phù hợp |
| Code được đổi hai lần bởi AS replica | **Không trực tiếp** | Atomic single-use authorization code |

**Access token sender-constrained** dùng DPoP hoặc mTLS yêu cầu bằng chứng khóa/chứng chỉ ở **thời điểm gọi API**. Nó có mục tiêu khác PKCE, vốn kiểm transaction **trước khi cấp token**. Trong mô hình bảo mật cao, hai lớp có thể được kết hợp.

## 11. Java 17: sinh PKCE verifier và challenge đúng chuẩn

Đoạn code dưới đây dùng `SecureRandom`, `MessageDigest` và Base64URL **không padding** để tạo một cặp PKCE S256. Không cần đưa secret hay token thật vào ví dụ.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.util.Base64;

public final class Pkce {
    private static final SecureRandom RNG = new SecureRandom();

    public record Pair(String verifier, String challenge) {}

    public static Pair create() {
        byte[] random = new byte[32]; // 256 bit entropy
        RNG.nextBytes(random);

        String verifier = Base64.getUrlEncoder()
            .withoutPadding()
            .encodeToString(random); // 43 ký tự hợp lệ
        String challenge = challengeS256(verifier);
        return new Pair(verifier, challenge);
    }

    public static String challengeS256(String verifier) {
        if (verifier == null || !verifier.matches(
                "[A-Za-z0-9._~-]{43,128}")) {
            throw new IllegalArgumentException("Invalid PKCE verifier");
        }
        try {
            byte[] ascii = verifier.getBytes(StandardCharsets.US_ASCII);
            byte[] digest = MessageDigest.getInstance("SHA-256")
                .digest(ascii);
            return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(digest);
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException("SHA-256 unavailable", ex);
        }
    }

    private Pkce() {}
}
~~~

Sử dụng:

~~~java
Pkce.Pair pair = Pkce.create();
// Authorization request:
//   code_challenge = pair.challenge()
//   code_challenge_method = S256
// Token request (sau khi callback state hợp lệ):
//   code_verifier = pair.verifier()
~~~

**Bảo mật ví dụ:** `verifier` là credential của transaction, không log ra console, không gửi vào telemetry và không lưu bền vững sau khi flow kết thúc. Java `String` có thể còn trong RAM cho tới khi GC; nếu threat model yêu cầu giảm khả năng đọc memory, dùng SDK/runtime bảo vệ secret tốt hơn và hạn chế dump/diagnostics.

### Kiểm bằng RFC test vector

~~~java
String verifier =
    "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk";
String expected =
    "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM";

if (!expected.equals(Pkce.challengeS256(verifier))) {
    throw new AssertionError("PKCE S256 implementation mismatch");
}
~~~

Test vector là dữ liệu **công khai** chỉ dành cho kiểm thuật toán. Không sử dụng nó như verifier runtime. Trong production, client cần dùng bộ thư viện OAuth/OIDC đáng tin cậy để quản lý cả transaction, redirect, state, token exchange và lưu trữ; hàm này chỉ minh họa **cách dẫn xuất challenge**.

## 12. Mã giả phía AS: ràng buộc challenge với code, chống downgrade

~~~text
onAuthorize(request):
    client = registry.find(request.client_id)
    if not client or grant not allowed:
        reject safely (do not redirect to untrusted URI)

    redirect = validateExactRegisteredRedirect(client, request.redirect_uri)
    if redirect invalid:
        reject safely

    if client is public and PKCE S256 is required:
        if missing challenge or method != "S256":
            reject safely

    validate challenge syntax, scope, resource and other parameters
    authenticate user; apply consent and policy

    code = issueShortLivedSingleUseCode(
        clientId=client.id,
        redirectUri=redirect,
        pkceChallenge=request.code_challenge,
        pkceMethod=request.code_challenge_method,
        grantedScopes=approvedScopes,
        subject=authenticatedUser
    )
    redirect browser with code and state

onToken(request):
    authenticate confidential client or apply public client binding
    record = lookupAuthorizationCode(request.code)
    if record absent, expired, used, or bound to other client:
        return invalid_grant
    if request.redirect_uri does not match record.redirectUri:
        return invalid_grant
    if record.pkceMethod == S256:
        if missing verifier or S256(verifier) != record.pkceChallenge:
            return invalid_grant
    else if policy requires PKCE S256:
        return invalid_grant

    atomically consume code once within a safe transaction
    issue tokens restricted to approved grant and current policy
~~~

Mã giả này trình bày **bất biến**, không phải mã AS production. Cần bảo đảm không có đường “code thiếu PKCE nhưng token request có verifier thì cho qua” và không kiểm challenge từ giá trị do caller tự gửi lại ở token endpoint. Nếu thuật toán hỗ trợ nhiều method, AS áp dụng theo **method đã lưu với code**, không theo method mới do token request đề xuất.

### So sánh challenge cần làm an toàn

AS có thể tính S256(verifier) và so sánh với challenge đã lưu bằng phép so sánh phù hợp trong thư viện đáng tin; tránh tự viết xử lý encoding dễ sai, rò qua lỗi/cơ chế thời gian hoặc cho phép so khớp một phần. Quan trọng hơn, challenge không được điều khiển bởi token request hiện tại và authorization code phải **single-use atomic**.

## 13. Lỗi giao thức, retry và cách phản ứng ở client

Nếu client gửi verifier sai hoặc code không hợp lệ/hết hạn/đã dùng, token endpoint thường trả OAuth error **`invalid_grant`** theo RFC 6749:

~~~http
HTTP/1.1 400 Bad Request
Cache-Control: no-store
Pragma: no-cache
Content-Type: application/json

{"error":"invalid_grant"}
~~~

Các lỗi cần phân biệt:

| Tình huống | Client nên làm gì? | Không nên làm |
|---|---|---|
| `invalid_grant` do code/verifier sai | Kết thúc transaction, khởi tạo authorization flow mới khi phù hợp | Retry cùng code liên tục, bỏ PKCE |
| State/callback không khớp | Từ chối ngay, ghi sự kiện tối thiểu | Đổi code trước rồi mới kiểm state |
| Redirect URI bị AS từ chối | Kiểm registration và URI chính xác | Mở wildcard hoặc đưa code sang URI khác |
| AS không hỗ trợ `S256` theo cấu hình hiện tại | Xem lại AS/SDK/profile; dùng hệ thống đáp ứng BCP | Hạ xuống `plain` để “chạy cho được” không đánh giá rủi ro |
| Token endpoint trả `429` | Tôn trọng `Retry-After`/backoff theo chính sách, để ý code TTL | Flood request hoặc giả định code dùng lại vô hạn |
| Response token bị thất lạc | Xử lý transaction bất định; có thể khởi tạo flow mới | Giả định code chưa dùng và cấp token nhiều lần |
| Client secret/credential confidential sai | Sửa cấu hình xác thực client an toàn | Dùng `client_id` công khai thay credential |

PKCE không làm authorization code có thể được đổi nhiều lần. Trong hệ thống phân tán, **AS phải tiêu thụ code nguyên tử**, và client phải hiểu rằng timeout không chứng minh token endpoint chưa xử lý request.

### Không log verifier hoặc token khi debug

Có thể log các metadata:

~~~text
GOOD:
  event=oauth_pkce_exchange_failed
  client_registration=invoice-spa
  grant_type=authorization_code
  error=invalid_grant
  request_id=correlation-id
  step=token_exchange

NEVER:
  code=<raw-code>
  code_verifier=<raw-verifier>
  Authorization: Bearer <raw-access-token>
  refresh_token=<raw-refresh-token>
~~~

`code_challenge` là giá trị được thiết kế để công khai, nhưng cũng không cần dùng làm metric label có cardinality cao. Các correlation ID phải được tạo an toàn và không chứa bí mật/PII dư thừa.

## 14. Những lỗi phổ biến khi bảo vệ public client

| Sai lầm | Vì sao không an toàn? | Biện pháp |
|---|---|---|
| Nhúng `client_secret` trong SPA/mobile | Có thể bị trích xuất; không còn là bí mật server-side | Public client + PKCE, hoặc BFF giữ credential |
| Chỉ dựa vào `client_id` | ID công khai, ai cũng có thể sao chép | Registration, state/PKCE, code/client binding |
| Verifier cố định cho mọi lần đăng nhập | Lộ một lần ảnh hưởng nhiều giao dịch | CSPRNG verifier mới mỗi transaction |
| Dùng random yếu hoặc quá ngắn | Dễ đoán verifier | 32 byte CSPRNG, 43 ký tự Base64URL |
| Gửi verifier trong authorization URL | Attacker quan sát front channel lấy cả code/verifier | Chỉ gửi challenge, verifier chỉ dùng ở token endpoint |
| Dùng `plain` để tương thích dễ dàng | Challenge có thể lộ verifier | Áp dụng S256 theo policy hiện đại |
| AS cho public client bỏ PKCE | Code bị chặn có thể đổi thành token | Require PKCE khi cấp code, validate tại token endpoint |
| AS không lưu challenge với code | Token endpoint không có nguồn kiểm đáng tin | Bind method/challenge trong authorization grant |
| Token endpoint tin challenge caller tự gửi | Attacker có code có thể tạo verifier/challenge mới | Chỉ dùng challenge đã gắn với code |
| AS không ràng buộc code với `client_id` | Code của client A có thể được B dùng | Kiểm code client binding và client auth khi cần |
| Redirect URI dùng wildcard/substring | Code có thể về host/path attacker | Exact registered redirect URI, ngoại lệ native loopback có kiểm |
| Bỏ `state`/issuer binding | Login CSRF/code injection/mix-up | State/transaction/issuer check trước code exchange |
| Dùng embedded WebView native để login | App có thể nhìn credential/login content, phá trust boundary | External user agent theo RFC 8252 |
| Lưu verifier/token vào log/analytics | Token hoặc PKCE proof bị trích xuất | Redact, hạn chế storage/runtime exposure |
| Nghĩ PKCE ngăn bearer access token bị lấy | PKCE chỉ bảo vệ code exchange | TTL, scope/aud, DPoP/mTLS, XSS defense |
| Không xử lý race của authorization code | Hai replica AS có thể cấp hai token | Atomic single-use, test concurrency |

## 15. Ma trận kiểm thử: public client protection với PKCE

Giả định hệ thống:

~~~text
Issuer:        https://auth.example.test
Client:        invoice-spa (public)
Redirect URI:  https://app.example.test/oauth2/callback
Flow:          Authorization Code + PKCE S256
Resource:      invoice-api
Allowed scope: invoice:read
~~~

| Ca kiểm thử | Input/hành vi | Kết quả kỳ vọng |
|---|---|---|
| **Luồng hợp lệ** | State, code, verifier, redirect đều đúng | Cấp access token đúng scope/audience; code single-use |
| **Không gửi `code_challenge`** | Public client xin code không có PKCE | AS từ chối theo policy, không cấp code yếu |
| **Không gửi `code_challenge_method`** | Policy yêu cầu tường minh S256 | Từ chối hoặc xử lý đúng theo profile; không downgrade |
| **Dùng `plain`** | Client xin method `plain` khi policy chỉ S256 | AS từ chối |
| **Verifier ngắn 10 ký tự** | Token request có verifier sai RFC | Từ chối |
| **Verifier 43 ký tự đúng định dạng nhưng sai giá trị** | Không khớp challenge | `invalid_grant`, không cấp token |
| **Verifier đúng** | Cùng transaction S256 | Đổi code tối đa một lần thành công |
| **Chỉ có code bị chặn** | Attacker dùng code không có verifier | Không cấp token cho attacker |
| **Có cả code/verifier** | Mô phỏng client runtime bị lộ | PKCE không bảo vệ đủ; cần lớp khác |
| **Tái sử dụng verifier cũ** | V1 của transaction cũ với code C2 | Không khớp challenge của C2 |
| **Dùng code hai lần** | Hai AS replica xử lý đồng thời | Tối đa một request được cấp token |
| **Code hết hạn** | Request sau expiry | `invalid_grant` |
| **Code của client khác** | Code của app A đổi bằng client B | AS từ chối |
| **Redirect URI khác** | Token request dùng URI không trùng authorization step | AS từ chối |
| **Redirect attacker** | Authorization request trỏ đến attacker.invalid | AS không chuyển code sang URI lạ |
| **State bị thay** | Callback có state không thuộc browser session | Client từ chối trước code exchange |
| **State replay** | Callback giao dịch đã hoàn tất | Client từ chối |
| **Mix-up giữa AS A/B** | Callback chứa issuer không đúng expected AS | Client từ chối hoặc kiểm mix-up defense phù hợp |
| **Native custom-scheme collision** | App khác nhận authorization code | Không đổi được code nếu không có verifier |
| **Native loopback port động** | Port thay đổi, host/path hợp lệ | AS dùng ngoại lệ RFC 8252 đúng phạm vi |
| **XSS trong SPA** | Script độc hại truy cập verifier/token | Test phát hiện rủi ro; PKCE không được tuyên bố chống XSS |
| **Sai JWT audience** | `aud=profile-api` đến Invoice API | Resource Server từ chối |
| **Thiếu scope** | Token chỉ có scope `invoice:read` nhưng API cần `invoice:delete` | Resource Server từ chối |
| **Chéo tenant** | Có access token hợp lệ nhưng đọc hóa đơn tenant khác | Resource Server từ chối theo object-level authorization |
| **Refresh token bị lộ** | Attacker dùng refresh token tại AS | Rotation/reuse detection hoặc sender-constraining theo policy |
| **Token endpoint CORS** | SPA fetch token endpoint cross-origin | CORS allowlist khi AS hỗ trợ; PKCE vẫn được kiểm |
| **Log/telemetry** | Kiểm log sau code exchange | Không có code, verifier, access/refresh token plaintext |

## 16. Bài tập tình huống: mã bị chặn khi app mobile trở về

Một ứng dụng Android `invoice-mobile` đăng ký public client với AS. Ứng dụng dùng redirect scheme `com.example.invoice:/oauth2redirect` và PKCE S256.

~~~text
Client mở authorization flow:
  client_id = invoice-mobile
  redirect_uri = com.example.invoice:/oauth2redirect
  state = S1
  verifier = V1 (giữ trong app)
  challenge = S256(V1) (gửi AS)

AS phát code C1 cho transaction này.

App độc hại cùng thiết bị claim scheme và nhận C1.
~~~

**Câu 1. Attacker nhận C1 có đổi được thành access token không?**

Thông thường **không**, nếu AS đã bắt buộc PKCE S256, lưu challenge cùng C1 và attacker không có V1. Gửi code với verifier khác sẽ không qua kiểm ở token endpoint.

**Câu 2. Vì sao không dùng client secret nhúng trong APK làm giải pháp thay PKCE?**

Vì APK có thể được phân tích để lấy secret dùng chung. Khi bị trích xuất, bí mật đó không còn chứng minh bản app cụ thể. PKCE tạo một **bí mật ngắn hạn cho mỗi giao dịch**, không phụ thuộc một client secret bị chia sẻ.

**Câu 3. Nếu app độc hại đọc được cả C1 và V1 thì sao?**

PKCE không đủ, vì attacker có cả hai điều kiện của code exchange. Cần bảo vệ IPC/runtime, kiểm app integrity ở mức phù hợp, giảm lộ verifier, bảo vệ redirect và các lớp phòng vệ khác; nếu token đã cấp thì xử lý thu hồi/binding.

**Câu 4. Nếu AS gửi authorization code tới một redirect URI khác mà không kiểm registration?**

PKCE vẫn có thể ngăn một số trường hợp code interception, nhưng **AS đã vi phạm ranh giới redirect URI**. AS phải kiểm URI đã đăng ký và từ chối URI lạ. Không dùng PKCE để biện minh cho open redirect.

**Câu 5. Nếu attacker chiếm access token bearer sau code exchange, V1 có giúp RS từ chối không?**

Không. RS không dùng verifier V1 để xác minh từng bearer API request. RS phải kiểm token issuer/audience/expiry/scope/owner, có thể bổ sung sender-constrained token và revocation theo chính sách.

**Câu 6. Nếu có hai request dùng C1 đúng V1, AS có thể cấp hai bộ token không?**

Không. Authorization code phải ngắn hạn và **single-use**, thao tác tiêu thụ phải nguyên tử giữa các AS instance. PKCE không thay code replay protection.

**Câu 7. Nếu ứng dụng chuyển sang loopback redirect với cổng thay đổi mỗi lần mở?**

AS có thể chấp nhận cổng động theo ngoại lệ RFC 8252 cho native loopback nhưng vẫn kiểm scheme, host loopback literal và path theo registration, đồng thời yêu cầu PKCE. Ngoại lệ này không mở rộng sang web callback không kiểm soát.

## 17. Checklist triển khai PKCE cho public clients

1. **Xác định đúng public client:** SPA/native không được coi client secret nhúng trong mã là credential bảo mật?
2. **Chọn Authorization Code Flow:** Không dùng implicit flow để tránh bước code exchange hoặc né PKCE?
3. **Bắt buộc PKCE S256 tại AS:** Challenge/method có được yêu cầu khi phát code và được gắn vào record?
4. **CSPRNG cho verifier:** Mỗi transaction có verifier 43–128 ký tự hợp lệ, entropy cao, không dùng lại?
5. **Challenge tính đúng:** `BASE64URL(SHA256(ASCII(verifier)))` không padding, không dùng hex digest hoặc Base64 thường?
6. **Verifier không xuất hiện trong front channel:** Không đưa vào `/authorize`, URL callback, `state`, log, telemetry?
7. **Redirect URI exact-match:** Theo client registration; ngoại lệ native loopback chỉ cho port được profile cho phép?
8. **State/issuer/transaction binding:** Callback được gắn đúng session, client, expected AS và có chống replay?
9. **Token endpoint kiểm đủ:** Code đúng client/redirect, chưa dùng/chưa hết hạn; verifier đúng challenge/method đã lưu?
10. **Confidential authentication không bị bỏ:** Với client có secret/key, AS vẫn xác thực đúng, PKCE là lớp bổ sung?
11. **Native dùng external browser:** Private-use scheme/app-claimed HTTPS/loopback được cấu hình an toàn, không embedded WebView tùy tiện?
12. **SPA xử lý XSS/CORS/storage:** Token endpoint browser CORS nếu cần, JS không lưu bí mật quá mức và có kế hoạch BFF khi rủi ro cao?
13. **Access token an toàn sau cấp:** JWT/opaque được RS kiểm issuer, audience, scope, expiry, quyền tenant/owner, revocation theo policy?
14. **Refresh token an toàn:** Rotation/reuse detection hoặc sender-constraining khi áp dụng; không giả định PKCE bảo vệ refresh token?
15. **Không bỏ chống race/abuse:** Code single-use atomic, rate limit issuance, log metadata thay vì code/verifier/token?
16. **Test negative paths:** Thiếu PKCE, `plain` downgrade, verifier sai, code replay, redirect sai, state sai, mix-up, native interception, XSS và token theft?

**Ghi nhớ:** **Public client không thể dựa vào một client secret dùng chung để chứng minh tính chính hãng**, nên PKCE S256 tạo một bằng chứng **riêng cho từng Authorization Code transaction**: client công bố `code_challenge`, giữ `code_verifier`, còn AS chỉ cấp token nếu verifier khớp challenge đã lưu với code. Đây là lớp chống **authorization code interception**, không phải giấy phép bỏ `state`, redirect URI matching, client/grant validation hoặc code single-use. Khi token đã được cấp, **Bearer/JWT/opaque token security, refresh token protection và quyền tại Resource Server** vẫn phải được thiết kế độc lập.

### Chuẩn và tài liệu tham khảo

- **RFC 7636 — Proof Key for Code Exchange by OAuth Public Clients:** định dạng `code_verifier`, `S256`, test vector và kiểm ở token endpoint.
- **RFC 6749 — The OAuth 2.0 Authorization Framework:** public/confidential client, Authorization Code Flow, client identifier và token endpoint.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** PKCE trong các luồng hiện đại, redirect validation, code injection, token theft và bảo vệ refresh token.
- **RFC 8252 — OAuth 2.0 for Native Apps:** external user agent, app-claimed HTTPS, private-use schemes và loopback redirects.
- **RFC 9207 — OAuth 2.0 Authorization Server Issuer Identification:** tham số `iss` giúp chống AS mix-up.
- **RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP):** sender-constraining khác với PKCE.
- **RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens:** client authentication/token binding theo chứng chỉ.
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** issuer, audience, client và scope của JWT access token.
- **RFC 7662 — OAuth 2.0 Token Introspection:** trạng thái và ngữ cảnh opaque access token tại RS.
- **OpenID Connect Core 1.0:** ID token, issuer, audience và nonce trong OIDC.
- **OWASP OAuth 2.0 Cheat Sheet:** hướng dẫn thiết kế, PKCE, state, redirect URI và token handling.
