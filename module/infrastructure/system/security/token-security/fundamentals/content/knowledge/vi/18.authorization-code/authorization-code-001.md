# Authorization request parameters

Trong **OAuth 2.0 Authorization Code Flow**, client không bắt đầu bằng việc gửi mật khẩu người dùng hoặc yêu cầu access token trực tiếp từ trình duyệt. Nó chuyển người dùng đến **authorization endpoint** của authorization server (AS) cùng một tập tham số mô tả **client nào đang xin quyền, response nào cần nhận, nơi trả kết quả, phạm vi quyền được yêu cầu và cách ràng buộc kết quả với phiên khởi tạo**.

Ví dụ một ứng dụng quản lý đơn hàng muốn đăng nhập người dùng qua OpenID Connect (OIDC), rồi gọi Orders API. Một yêu cầu ban đầu có thể gồm `response_type=code`, `client_id`, `redirect_uri`, `scope=openid orders.read`, `state`, `code_challenge` và `code_challenge_method=S256`. Nếu client sai một tham số quan trọng, authorization code có thể bị đánh cắp, trả về sai nơi, gắn vào sai phiên hoặc đổi token thất bại.

Bài học thuộc chương **Authorization Code** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**. Trọng tâm là **authorization request parameters** và mối liên hệ của chúng với mô hình tin cậy, phát hành và xác minh access/refresh token, JWT/opaque token, audience, scope, OAuth 2.0/OIDC, lưu trữ, thu hồi và phòng chống token theft/replay.

> **Nguyên tắc:** Authorization request là **lời đề nghị cấp quyền**, không phải quyền đã được cấp. Authorization server phải tự kiểm tra client, redirect URI, PKCE, grant/consent và policy; resource server phải tự xác minh access token và phân quyền khi request thực tế đến.

## 1. Đặt authorization request vào đúng luồng

Các vai trò:

- **Resource owner:** chủ thể nắm quyền đối với dữ liệu, thường là người dùng.
- **Client:** ứng dụng muốn truy cập tài nguyên thay mặt người dùng hoặc theo grant được hỗ trợ.
- **Authorization server (AS)/OpenID Provider (OP):** bên xác thực người dùng khi cần, quyết định cấp quyền, phát authorization code và token.
- **Resource server (RS):** API chấp nhận access token đúng issuer, audience, scope và chính sách tài nguyên.

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant C as OAuth/OIDC client
    participant AS as Authorization server / OP
    participant RS as Orders API
    U->>C: Chọn Đăng nhập / Kết nối dữ liệu
    C->>C: Sinh state, PKCE verifier/challenge, nonce nếu OIDC
    C->>AS: Authorization request (response_type=code, ...)
    AS->>U: Xác thực và/hoặc consent theo policy
    U-->>AS: Hoàn thành tương tác
    AS-->>C: Redirect về redirect_uri cùng code + state
    C->>C: Kiểm tra state/issuer và giao dịch gốc
    C->>AS: POST token endpoint (code + code_verifier)
    AS-->>C: Access token, optional refresh token, ID token nếu OIDC
    C->>RS: Gửi access token cho đúng API
    RS->>RS: Xác minh token + quyền trên tài nguyên
    RS-->>C: Dữ liệu hoặc 401/403
~~~

**Phải phân biệt hai HTTP request:**

1. **Authorization request:** đi qua user-agent (browser) tới **authorization endpoint**, thường là `GET` với query parameters; kết quả chính là **authorization code** hoặc lỗi.
2. **Token request:** client gửi `POST` tới **token endpoint**, đổi code và PKCE verifier lấy token; confidential client còn phải thực hiện client authentication theo yêu cầu.

Đừng gửi `code_verifier`, client secret hoặc refresh token trong authorization request query. `code_verifier` chỉ được gửi tới **token endpoint** khi đổi code.

## 2. Một authorization request đầy đủ trông như thế nào?

Giả sử một SPA đã đăng ký với AS:

| Giá trị | Ví dụ |
| --- | --- |
| Authorization endpoint | `https://auth.example.com/oauth2/authorize` |
| Client ID | `orders-spa` |
| Redirect URI | `https://app.example.com/auth/callback` |
| Resource/API dự kiến | `https://api.example.com/orders` |
| Quyền yêu cầu | `openid profile orders.read` |
| Loại OAuth client | Public client, dùng Authorization Code + PKCE |

Yêu cầu minh họa đã xuống dòng để đọc:

~~~http
GET /oauth2/authorize?response_type=code
  &client_id=orders-spa
  &redirect_uri=https%3A%2F%2Fapp.example.com%2Fauth%2Fcallback
  &scope=openid%20profile%20orders.read
  &state=<cryptographically-random-value>
  &code_challenge=<base64url-sha256-of-verifier>
  &code_challenge_method=S256
  &nonce=<cryptographically-random-oidc-nonce>
  &resource=https%3A%2F%2Fapi.example.com%2Forders HTTP/1.1
Host: auth.example.com
~~~

Trong request thực, query string phải ở **một dòng**, từng giá trị phải được URL-encode và `resource` chỉ được dùng khi AS hỗ trợ **RFC 8707**. `nonce` thuộc OIDC và hữu ích khi client dùng `scope=openid`. Các placeholder không phải giá trị được phép dùng trong production; client phải sinh chúng bằng nguồn ngẫu nhiên mật mã.

### 2.1. Bảng tổng hợp tham số

| Tham số | Vai trò | Mức yêu cầu/ngữ cảnh |
| --- | --- | --- |
| **`response_type=code`** | Yêu cầu authorization code | Bắt buộc cho Authorization Code Flow |
| **`client_id`** | Xác định client registration tại AS | Bắt buộc |
| **`redirect_uri`** | Địa chỉ nhận authorization response | Bắt buộc trong OIDC Code Flow; OAuth 2.0 có quy tắc phụ thuộc đăng ký |
| **`scope`** | Phạm vi quyền xin cấp; `openid` nếu dùng OIDC | Tùy profile; `openid` là bắt buộc cho yêu cầu OIDC |
| **`state`** | Liên kết response với giao dịch client khởi tạo | Được OAuth khuyến nghị mạnh; dùng trong browser flow theo chính sách chống CSRF/mix-up |
| **`code_challenge`** | Cam kết PKCE từ bí mật `code_verifier` | Cần khi dùng PKCE; bắt buộc theo profile/chính sách hiện đại cho public clients |
| **`code_challenge_method=S256`** | Quy định cách tạo challenge | Nên dùng `S256`, không hạ xuống `plain` tùy tiện |
| **`nonce`** | Ràng buộc sự kiện OIDC với ID token | Có thể tùy chọn trong OIDC Code Flow, nên dùng khi cần chống replay/mix-up bổ sung |
| **`prompt`, `max_age`** | Điều khiển yêu cầu tương tác/tính mới của xác thực OIDC | Tùy chọn, chỉ khi dùng OIDC/provider hỗ trợ |
| **`login_hint`, `acr_values`** | Gợi ý tài khoản hoặc mức xác thực mong muốn | OIDC tùy chọn; cần kiểm tra kết quả thực tế |
| **`resource`** | Chỉ định resource indicator/audience mong muốn | Extension RFC 8707 khi AS hỗ trợ |
| **`authorization_details`** | Yêu cầu quyền theo cấu trúc phong phú | Extension RFC 9396 khi AS hỗ trợ |
| **`response_mode`** | Chọn cách AS mang authorization response | Tùy chọn theo OIDC/OAuth response-mode support |
| **`request`, `request_uri`** | Request Object (JAR) hoặc tham chiếu request đã đẩy (PAR) | Chỉ khi AS/client triển khai extension tương ứng |

**Không phải cứ đưa tham số vào URL là AS sẽ cấp quyền tương ứng.** AS phải kiểm tra client registration, quyền được yêu cầu, user consent, policy và giới hạn token. Một số tham số không được hỗ trợ có thể bị từ chối, bỏ qua theo chuẩn hoặc có hành vi phụ thuộc profile; client cần hiểu contract của **issuer cụ thể**.

## 3. `response_type=code`: phân biệt code với access token

~~~text
response_type=code
~~~

Giá trị này yêu cầu AS trả về **authorization code**, không phải access token trực tiếp từ authorization endpoint. Authorization code:

- Có thời hạn **ngắn**, chỉ dùng được một lần theo yêu cầu giao thức;
- Được ràng buộc với `client_id`, redirect URI và PKCE challenge khi có;
- Không phải credential để gọi Orders API;
- Phải được client đổi tại token endpoint bằng request hợp lệ.

**Không nhầm `response_type` với `grant_type`:**

~~~text
Authorization endpoint:
  response_type=code

Token endpoint:
  grant_type=authorization_code
~~~

Các giá trị `response_type=token` hay kết hợp nhiều response types thuộc luồng khác. Với client hiện đại, Authorization Code + PKCE thường được ưu tiên thay vì phát access token trực tiếp trong front-channel (implicit flow), giúp giảm rủi ro token xuất hiện trong browser redirect.

## 4. `client_id`: định danh client, không phải client secret

~~~text
client_id=orders-spa
~~~

`client_id` là identifier do AS cấp khi đăng ký OAuth client. Nó **không phải bí mật** và có thể xuất hiện trong URL, log và browser history. AS dùng nó để:

- Tìm client registration và loại client: **public** hoặc **confidential**;
- Kiểm tra redirect URIs đã đăng ký;
- Kiểm tra grant/response types, scopes, token policy và yêu cầu PKCE;
- Áp client-specific settings như response modes, OIDC claims và authentication method.

**Public client** (SPA/native) không thể giữ client secret an toàn trong mã được phân phối cho người dùng. Không đưa `client_secret` vào JavaScript hoặc authorization request.

**Confidential client** (BFF/server Java) có thể giữ credential ở backend và **xác thực tại token endpoint** bằng client secret/private_key_jwt/mTLS hoặc phương pháp đã đăng ký. Sự tồn tại của `client_id` trong URL **không chứng minh** caller sở hữu confidential client.

## 5. `redirect_uri`: ranh giới chống đánh cắp authorization code

~~~text
redirect_uri=https://app.example.com/auth/callback
~~~

Sau khi user hoàn tất authorization, AS redirect user-agent về URI này cùng `code`/`state` hoặc error. Vì code có thể được đổi lấy token nếu thiếu các ràng buộc đúng, **redirect URI là một ranh giới bảo mật quan trọng**.

### 5.1. Chỉ chấp nhận địa chỉ đã đăng ký

AS phải so redirect URI theo quy tắc đăng ký/profile. Với các HTTP redirect URI thông thường, **exact string matching** là phương án chuẩn an toàn; không dùng host wildcard, pattern chứa attacker-controlled subdomain hoặc substring comparison.

| Cấu hình | Đánh giá | Giải thích |
| --- | --- | --- |
| `https://app.example.com/auth/callback` | Phù hợp khi đăng ký chính xác | HTTPS và đường nhận response cố định |
| `https://*.example.com/callback` | Không nên dùng | Subdomain không đáng tin có thể nhận code |
| `https://app.example.com/redirect?to=...` | Nguy cơ cao nếu open redirect | Code có thể bị chuyển sang nơi khác |
| `https://attacker.example/callback` | Không được chấp nhận | Không thuộc client registration |
| `http://127.0.0.1:<dynamic-port>/callback` | Ngoại lệ có điều kiện cho native app | Loopback redirect theo RFC 8252 với quy tắc đăng ký/port riêng |

Theo RFC 9700, URI matching phải tuân nguyên tắc chính xác, với **ngoại lệ giới hạn cho port của loopback redirect ở native apps**. Không lấy ngoại lệ đó áp rộng cho web SPA hoặc wildcard hostname.

### 5.2. Trả `redirect_uri` đúng với lúc đổi code

Trong OAuth 2.0, khi authorization request có `redirect_uri`, token request phải dùng cùng giá trị nếu được yêu cầu và AS phải ràng buộc code với redirect URI đúng contract.

~~~text
Authorization request:
  redirect_uri=https://app.example.com/auth/callback

Token request:
  redirect_uri=https://app.example.com/auth/callback
~~~

Không thay thành URL nội bộ như `http://localhost:8080` khi token exchange trừ khi đó đúng là registered URI tương ứng cho flow. Sau reverse proxy, cần thiết lập **public origin đáng tin**; không sinh redirect URI từ spoofed `X-Forwarded-Host` hoặc `Host` của caller.

### 5.3. Không dùng redirect endpoint làm open redirect

Nếu callback chấp nhận `?next=https://attacker.example` rồi redirect tự do, code, `state` hoặc token response có thể bị rò qua URL/referrer hoặc sai ngữ cảnh. Callback nên xử lý code, dọn query khỏi browser URL và chỉ điều hướng đến **local allowlisted paths**. Không dùng bearer access token trong redirect query.

## 6. `scope`: yêu cầu phạm vi, không phải quyền được bảo đảm

~~~text
scope=openid profile orders.read
~~~

`scope` là danh sách các giá trị scope được phân tách bằng **dấu cách**, được URL-encode trong query. AS kiểm tra scope thuộc phạm vi client được đăng ký, user/consent và policy. Token response có thể cấp **tập quyền hẹp hơn** yêu cầu.

| Giá trị scope | Ý nghĩa phụ thuộc profile |
| --- | --- |
| `openid` | Đánh dấu request là **OIDC authentication request** |
| `profile` | OIDC scope yêu cầu tập claims profile theo quy định/consent |
| `email` | OIDC scope liên quan email claims |
| `orders.read` | Scope API minh họa; semantics do AS/RS thiết lập |
| `orders.write` | Scope API minh họa cho quyền thao tác ghi |
| `offline_access` | OIDC scope liên quan yêu cầu offline access theo policy của OP |

**`offline_access` không bảo đảm refresh token sẽ được cấp**. OP quyết định theo grant, client type, consent, session và chính sách; trong OIDC có yêu cầu riêng khi xin offline access, chẳng hạn các điều kiện liên quan `prompt=consent`.

Client không được giả định “đã gửi `scope=orders.write` thì token nhất định có quyền ghi”. Khi dùng access token, resource server phải kiểm tra **scope thực tế đã cấp** hoặc introspection metadata, đồng thời kiểm tra tenant/ownership.

### 6.1. Scope không đồng nhất với role

Một `scope=orders.read` cho phép xét chức năng đọc Orders API, nhưng không tự cấp quyền đọc **mọi** đơn hàng của mọi tenant. `ROLE_ADMIN` có thể là quyền nội bộ có ngữ cảnh, không được suy ra đơn giản từ scope client xin.

~~~text
Authorization request: scope=orders.read
Access token:          scope=orders.read, tenant_id=acme
API request:           GET /tenants/globex/orders/42

Kết luận: TỪ CHỐI nếu token/user không có quyền trên Globex.
~~~

## 7. `state`: liên kết callback với giao dịch gốc

~~~text
state=<unguessable-random-value>
~~~

`state` là giá trị opaque do **client** tạo trước khi redirect, dùng để liên kết authorization response với **authorization request/session** đã bắt đầu. Khi callback đến, client phải kiểm tra `state` nhận được khớp giao dịch đang chờ và **chưa được sử dụng**.

### 7.1. Tại sao `state` quan trọng?

Nếu client chấp nhận bất kỳ `code` nào trong callback mà không ràng buộc nó với phiên khởi tạo, attacker có thể cố gắng đưa browser nạn nhân đến callback chứa code của attacker hoặc trộn response giữa các issuer. Hậu quả có thể là **login CSRF**, session confusion hoặc nhầm grant.

`state` không được coi là user ID, API authorization credential, access token hay chỗ lưu bí mật trong URL. Nó chỉ là **correlation/CSRF value**, nhưng vẫn cần ngẫu nhiên đủ khó đoán và thời hạn ngắn.

### 7.2. Thực hành an toàn

1. Sinh state bằng **CSPRNG** (ví dụ 128–256 bit ngẫu nhiên), không dùng timestamp hay `Math.random()`.
2. Lưu bản ghi transaction ở nơi gắn với phiên/tab, có `state`, issuer, client, redirect URI, PKCE verifier, nonce và thời gian tạo.
3. Khi callback, so state với transaction; nếu thiếu, sai, hết hạn, đã dùng hoặc có nhiều giá trị mơ hồ thì **từ chối**.
4. Đánh dấu transaction đã tiêu thụ và xóa dữ liệu PKCE sau khi xử lý; không cho replay callback.
5. Nếu hỗ trợ nhiều issuer, state cần gắn với **issuer dự kiến**; bổ sung các biện pháp mix-up defense theo RFC 9207/profile.

Theo OAuth 2.0, `state` được **khuyến nghị** chứ không bắt buộc tuyệt đối cho mọi mô hình. Một số profile dùng PKCE và các cơ chế ràng buộc khác để đáp ứng chống CSRF. Tuy nhiên, **đối với ứng dụng browser, dùng state đúng cách là thực hành thiết kế rõ ràng và dễ kiểm tra**.

### 7.3. Đừng gắn business return URL chưa kiểm soát vào state

Sai:

~~~text
state=https://attacker.example/receive
~~~

Nếu client sau callback redirect đến URL trong `state` mà không kiểm tra, nó tạo **open redirect**. Giữ state là giá trị ngẫu nhiên, ánh xạ tới **đường dẫn local được phép** trong transaction server/client, không chuyển hướng sang origin tùy ý.

## 8. PKCE: `code_challenge` và `code_challenge_method`

**Proof Key for Code Exchange (PKCE, RFC 7636)** ràng buộc code với một bí mật do client sinh trước khi bắt đầu authorization request. Điều này giúp ngăn bên chỉ lấy được authorization code đổi code lấy token mà không biết `code_verifier`.

~~~mermaid
flowchart LR
    A["Client sinh code_verifier\nngẫu nhiên"] --> B["code_challenge =\nBASE64URL(SHA256(verifier))"]
    B --> C["Authorization request:\nchallenge + S256"]
    C --> D["AS liên kết challenge\nvới authorization code"]
    D --> E["Token request:\ncode + code_verifier"]
    E --> F{"AS kiểm tra\nchallenge khớp?"}
    F -->|Không| G["Từ chối token request"]
    F -->|Có| H["Tiếp tục xác minh\ngrant/client/redirect"]
~~~

### 8.1. Tham số gửi tới authorization endpoint

~~~text
code_challenge=<base64url-encoded-sha256-verifier>
code_challenge_method=S256
~~~

Giá trị `code_verifier` **không được gửi trong authorization request**. Nó chỉ xuất hiện tại **token request**, nơi AS so lại với challenge đã lưu cùng code.

Theo RFC 7636, code verifier gồm 43–128 ký tự không dành riêng trong tập `[A-Z]`, `[a-z]`, `[0-9]`, `-`, `.`, `_`, `~`. Một cách phổ biến là sinh 32 byte ngẫu nhiên và Base64url không padding để được 43 ký tự.

### 8.2. S256 được tính như thế nào?

\[
\texttt{code\_challenge}
= \operatorname{BASE64URL\_NO\_PAD}
\bigl(\operatorname{SHA256}(\operatorname{ASCII}(\texttt{code\_verifier}))\bigr)
\]

**Không nhầm `code_challenge` với `state` hoặc `nonce`.** Các giá trị có nhiệm vụ khác nhau và nên được sinh độc lập.

### 8.3. Vì sao tránh `plain`?

`code_challenge_method=plain` là một tùy chọn lịch sử theo PKCE, nhưng không bảo vệ tốt nếu attacker thấy cả authorization request và đánh cắp code trong mô hình đe dọa tương ứng. Các profile/best practices hiện đại ưu tiên **`S256`**. Client không được tự hạ từ S256 xuống plain khi AS báo lỗi mà không có policy được phê duyệt.

**PKCE không chứng minh user là ai**, không thay user authentication, MFA, redirect URI validation, state/CSRF defense hay client authentication của confidential client. Nó bảo vệ **bước đổi code** khỏi một lớp tấn công đánh cắp code.

## 9. `nonce` trong OIDC Authorization Code Flow

Khi `scope` chứa `openid`, OP có thể cấp **ID token** tại token endpoint. `nonce` là giá trị do OIDC client tạo để ràng buộc ID token với một phiên/request xác thực, giảm replay và nhầm giao dịch.

~~~text
scope=openid profile
nonce=<unguessable-random-nonce>
~~~

Trong **OIDC Code Flow**, `nonce` có thể tùy chọn theo OIDC Core, nhưng nếu client đã gửi `nonce` thì phải **kiểm tra giá trị `nonce` trong ID token** sau khi xác minh ID token (issuer, signature, audience, expiry và các claim bắt buộc khác).

| Giá trị | Tạo bởi | Kiểm tra ở đâu? | Bảo vệ mục tiêu gì? |
| --- | --- | --- | --- |
| `state` | Client | Callback authorization response | Response/session correlation và CSRF/mix-up defenses |
| `code_verifier` + PKCE challenge | Client | Token endpoint kiểm tra verifier | Authorization code interception |
| `nonce` | OIDC client | ID token validation tại client | Liên kết ID token với authentication request |

ID token dành cho **OIDC client**, thường có `aud=client_id`; access token dành cho **resource server/API**, thường có audience riêng. Không dùng ID token như Bearer token gọi API chỉ vì nonce đúng.

## 10. `prompt`, `max_age`, `login_hint` và `acr_values`

Những tham số dưới đây thuộc **OIDC Authentication Request**, không phải các trường bắt buộc của OAuth Authorization Code Flow thuần:

| Tham số | Ví dụ | Ý nghĩa | Lưu ý |
| --- | --- | --- | --- |
| `prompt` | `login` | Yêu cầu OP hướng tới việc xác thực lại | Không chứng minh MFA đã hoàn thành |
| `prompt` | `consent` | Yêu cầu biểu diễn consent theo policy OP | Không cho client tự cấp scope vượt quyền |
| `prompt` | `none` | Yêu cầu không hiển thị giao diện tương tác | Có thể nhận `login_required` hoặc `interaction_required` |
| `prompt` | `select_account` | Yêu cầu OP cho chọn account | Hành vi phụ thuộc OP |
| `max_age` | `300` | Yêu cầu authentication đủ mới, tối đa 300 giây | Client phải kiểm tra `auth_time` trong ID token |
| `login_hint` | `user@example.com` | Gợi ý tài khoản cho OP | Không phải bằng chứng identity |
| `acr_values` | `urn:example:loa:2` | Yêu cầu mức/ngữ cảnh xác thực | Client cần kiểm tra `acr` được trả hoặc policy phù hợp |
| `ui_locales` | `vi en` | Gợi ý ngôn ngữ giao diện | Không phải kiểm soát bảo mật |

### 10.1. `max_age` không phải TTL của access token

Ví dụ user đăng nhập lúc 09:00. Đến 10:00, client yêu cầu `max_age=300` vì một tác vụ nhạy cảm. Client cần dựa vào **`auth_time` được OP xác nhận** và policy để kiểm tra tính mới của authentication; **không dùng `iat` của access token hoặc ID token thay thế**.

`prompt=login` yêu cầu xác thực lại, nhưng **không mặc nhiên bảo đảm MFA**. Nếu nghiệp vụ yêu cầu step-up, phải có hợp đồng về `acr`/`amr`, quy tắc OP và kiểm tra kết quả phù hợp.

### 10.2. `prompt=none` không phải cơ chế đăng nhập chắc chắn thành công

Nếu OP không có SSO session phù hợp hoặc phải lấy consent/step-up, nó có thể trả error thay vì code. Browser có thể chặn third-party cookies/iframes; do đó không nên dựa vào silent iframe flow như cách chắc chắn khôi phục phiên mà không tương tác.

## 11. `resource`: yêu cầu access token cho API nào?

OAuth scopes không luôn đủ để chỉ ra **resource server/audience**. **RFC 8707 — Resource Indicators for OAuth 2.0** định nghĩa tham số `resource` để client yêu cầu token dành cho một tài nguyên cụ thể khi AS hỗ trợ.

~~~text
resource=https://api.example.com/orders
~~~

AS có thể dùng `resource` để xác định audience và giới hạn token. Nhưng **client không có quyền tự đặt bất kỳ URL nào rồi nhận token truy cập nơi đó**: resource indicator phải được AS chấp nhận theo đăng ký, consent/grant và policy.

| Khái niệm | Ví dụ | Ai quyết định cuối cùng? |
| --- | --- | --- |
| Scope yêu cầu | `orders.read` | AS cấp phù hợp grant; RS thực thi quyền |
| Resource yêu cầu | `https://api.example.com/orders` | AS xác định target được phép |
| Token audience (`aud`) | `https://api.example.com/orders` | AS phát hành, RS phải validate |

Nếu client gửi access token cho Payments API mà token có `aud` chỉ Orders API, Payments API phải từ chối **dù signature đúng**.

**RFC 8707 cho phép nhiều tham số `resource` trong một số trường hợp**, nhưng token có được cấp cho nhiều resource hay không phụ thuộc policy. Client và API không được tự suy diễn audience chỉ từ request ban đầu; cần kiểm tra token/introspection thực tế.

### 11.1. Resource indicator khác `redirect_uri`

`redirect_uri` là nơi **client nhận code**. `resource` là nơi **access token được dự định sử dụng**. Chúng có thể là hai domain khác nhau:

~~~text
redirect_uri = https://app.example.com/auth/callback
resource     = https://api.example.com/orders
~~~

Không đưa API URL vào `redirect_uri` hoặc đưa callback URL thành resource audience trừ khi đó thực sự là contract của AS.

## 12. `authorization_details`: yêu cầu quyền có cấu trúc

Khi scope đơn giản như `payments.write` không thể mô tả đủ ngữ cảnh (số tiền, đối tượng, loại giao dịch), **Rich Authorization Requests (RAR, RFC 9396)** cung cấp tham số `authorization_details`.

Ví dụ JSON **minh họa** trước khi URL-encode:

~~~json
[
  {
    "type": "payment_initiation",
    "actions": ["initiate"],
    "locations": ["https://api.example.com/payments"],
    "instructedAmount": {
      "currency": "VND",
      "amount": "500000"
    }
  }
]
~~~

AS phải hiểu **kiểu `type` đã đăng ký/thỏa thuận**, kiểm tra chính sách, consent và cấp token/authorization details phù hợp. Các trường nghiệp vụ trong ví dụ **không phải schema bắt buộc phổ quát cho mọi RAR profile**.

**Không coi JSON client gửi như quyền đã được cấp.** RS phải xác minh quyền/constraints thực sự được AS xác nhận, đồng thời kiểm tra resource data, transaction binding và nguy cơ replay.

Với request nhiều dữ liệu nhạy cảm, **đừng gửi JSON khổng lồ hoặc PII trong URL**. Cân nhắc PAR/JAR và giảm dữ liệu hiển thị trong front-channel nếu hạ tầng hỗ trợ.

## 13. `response_mode`: AS mang code trở về bằng cách nào?

Mặc định trong Authorization Code Flow, AS thường trả kết quả qua **query parameters** tại `redirect_uri`:

~~~http
HTTP/1.1 302 Found
Location: https://app.example.com/auth/callback?code=<one-time-code>&state=<matching-state>
Cache-Control: no-store
~~~

Một số OP hỗ trợ `response_mode=form_post` để gửi response bằng HTML form POST về callback, hoặc **JWT Secured Authorization Response Mode (JARM)** với response được ký theo profile.

| Response mode | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `query` | Code/state trong query của redirect URI | Dọn URL, tránh logs/referrer và open redirect |
| `form_post` | Browser POST response qua HTML form | Cần callback nhận POST và bảo vệ CSRF theo flow |
| `jwt`/JARM modes | Authorization response được đóng gói/ký dưới dạng JWT | Cần validate issuer, audience, signature, expiration và state |

Không tùy tiện đặt `response_mode` không được AS hỗ trợ. **Không dùng fragment chứa access token** như một đường tắt quay về implicit flow.

### 13.1. Callback nhận được lỗi, không phải code

Ví dụ user từ chối consent:

~~~http
HTTP/1.1 302 Found
Location: https://app.example.com/auth/callback?error=access_denied&state=<matching-state>
~~~

Client phải đối chiếu `state` kể cả khi nhận lỗi, hủy/đóng giao dịch phù hợp và hiển thị thông báo an toàn. Không giả định mọi callback đều có `code`; cũng không đưa `error_description` chưa được kiểm soát trực tiếp vào HTML bằng `innerHTML`.

## 14. PAR và JAR: bảo vệ request phức tạp

Khi authorization request có nhiều tham số hoặc dữ liệu nhạy cảm, một URL dài có thể bị log, sửa, copy hoặc vượt giới hạn browser/proxy. Hai extension hữu ích:

### 14.1. Pushed Authorization Requests (PAR, RFC 9126)

Client gửi authorization request **trực tiếp qua back-channel** tới PAR endpoint của AS, nhận `request_uri` tạm thời và đưa user-agent đến authorization endpoint với tham chiếu đó.

~~~mermaid
sequenceDiagram
    autonumber
    participant C as OAuth Client/BFF
    participant AS as Authorization server
    participant B as Browser
    C->>AS: POST PAR endpoint: registered params + PKCE
    AS->>AS: Validate client/request theo policy
    AS-->>C: request_uri + expires_in
    C->>B: Chuyển browser tới authorize URL
    B->>AS: GET /authorize?client_id=...&request_uri=...
    AS->>AS: Lấy request đã được đẩy và kiểm tra
    AS-->>B: Login/consent rồi callback với code/state
~~~

Một request authorization cuối của browser có thể là:

~~~text
https://auth.example.com/oauth2/authorize
  ?client_id=orders-bff
  &request_uri=urn%3Aietf%3Aparams%3Aoauth%3Arequest_uri%3A...
~~~

`request_uri` trong PAR là **tham chiếu do AS cấp và giới hạn thời gian**, không phải một URL bất kỳ do caller yêu cầu AS tải. Cách client xác thực tại PAR endpoint phụ thuộc loại client/profile; AS vẫn phải ràng buộc các tham số với client.

### 14.2. JWT-Secured Authorization Request (JAR, RFC 9101)

JAR dùng **JWT Request Object** để đóng gói và có thể bảo vệ tính toàn vẹn/xác thực của authorization request theo profile. AS phải kiểm tra issuer/audience, chữ ký/algorithms, thời hạn và các quy tắc xử lý claim phù hợp.

**PAR và JAR có thể được kết hợp**, nhưng chúng giải quyết các vấn đề khác nhau:

- **PAR:** giảm tham số nhạy cảm/URL dài trong front-channel và giúp AS xử lý request trước khi browser được chuyển hướng.
- **JAR:** ràng buộc nội dung authorization request theo đối tượng được ký/đã xác minh.

Không tự coi bất kỳ JWT nào ở `request` là đáng tin; không lấy `request_uri` từ caller như một endpoint mạng tùy ý để SSRF.

## 15. Tạo authorization request bằng JavaScript an toàn

Đoạn dưới đây minh họa **SPA public client** sinh `state`, PKCE verifier/challenge và `nonce` bằng Web Crypto, rồi lưu **giao dịch authorization ngắn hạn** để kiểm tra callback sau redirect. Client registration/issuer/URL đều là hằng số đáng tin. Đây là code minh họa, cần kết hợp thư viện OAuth/OIDC đã được kiểm thử trong sản phẩm thật.

~~~javascript
const AS_AUTHORIZE = "https://auth.example.com/oauth2/authorize";
const ISSUER = "https://auth.example.com";
const CLIENT_ID = "orders-spa";
const REDIRECT_URI = "https://app.example.com/auth/callback";
const ORDERS_RESOURCE = "https://api.example.com/orders";

function randomBase64Url(byteLength = 32) {
  const bytes = new Uint8Array(byteLength);
  crypto.getRandomValues(bytes);
  let binary = "";
  for (const b of bytes) binary += String.fromCharCode(b);
  return btoa(binary)
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/g, "");
}

async function pkceS256(verifier) {
  const input = new TextEncoder().encode(verifier);
  const digest = await crypto.subtle.digest("SHA-256", input);
  let binary = "";
  for (const b of new Uint8Array(digest)) {
    binary += String.fromCharCode(b);
  }
  return btoa(binary)
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/g, "");
}

export async function beginAuthorization() {
  const state = randomBase64Url();
  const nonce = randomBase64Url();
  const verifier = randomBase64Url();
  const challenge = await pkceS256(verifier);

  const pending = {
    issuer: ISSUER,
    redirectUri: REDIRECT_URI,
    verifier,
    nonce,
    createdAt: Date.now()
  };

  // Chỉ giữ transaction ngắn hạn qua redirect.
  // KHÔNG lưu access/refresh token trong sessionStorage.
  sessionStorage.setItem(
    "oauth.tx." + state,
    JSON.stringify(pending)
  );

  const url = new URL(AS_AUTHORIZE);
  url.searchParams.set("response_type", "code");
  url.searchParams.set("client_id", CLIENT_ID);
  url.searchParams.set("redirect_uri", REDIRECT_URI);
  url.searchParams.set("scope", "openid profile orders.read");
  url.searchParams.set("state", state);
  url.searchParams.set("code_challenge", challenge);
  url.searchParams.set("code_challenge_method", "S256");
  url.searchParams.set("nonce", nonce);

  // Chỉ bật nếu AS được cấu hình hỗ trợ RFC 8707.
  url.searchParams.set("resource", ORDERS_RESOURCE);
  location.assign(url.toString());
}
~~~

### 15.1. Vì sao lưu transaction trong `sessionStorage`?

Sau full-page redirect đến AS, JavaScript document cũ thường bị hủy. **`code_verifier` cần tồn tại tới khi callback nhận code**; `state` và `nonce` cũng cần được so lại. Một số thư viện SPA dùng storage theo tab cho **transaction ngắn hạn**; đây **khác** việc lưu access/refresh token bền vững trong Web Storage.

Tuy nhiên, `sessionStorage` vẫn truy cập được bởi script cùng origin; **XSS có thể đánh cắp PKCE verifier**. BFF có thể giữ transaction trong server-side session để hạn chế secret ở browser. Luôn xóa transaction sau xử lý, giới hạn TTL, không serialize dữ liệu này vào log.

### 15.2. Khi callback quay lại

Pseudocode ở client:

~~~text
1. Parse callback query hoặc response mode đã đăng ký.
2. Đọc state; nếu không có/không khớp transaction -> reject.
3. Kiểm tra transaction còn hạn, issuer và redirectUri dự kiến.
4. Nếu AS hỗ trợ iss trong authorization response (RFC 9207):
   phải so với issuer dự kiến; chống mix-up theo profile.
5. Nếu có error: xử lý lỗi và kết thúc transaction.
6. Nếu có code: đánh dấu transaction đã dùng, lấy verifier.
7. POST token endpoint theo đúng client/grant/redirect với verifier.
8. Nếu OIDC: verify ID token (iss, aud, exp, nonce,...).
9. Giữ access token an toàn và chỉ gửi tới resource đúng audience.
10. Xóa code/state/error khỏi URL hiển thị; không log credential.
~~~

Thực tế nên dùng thư viện OAuth2/OIDC có hỗ trợ PKCE, state, issuer binding và token validation phù hợp; không nên tự viết parser/protocol security bằng vài dòng code và coi ví dụ là thư viện production.

## 16. Token request: đối chiếu các tham số, không trộn hai endpoint

Sau authorization response:

~~~http
HTTP/1.1 302 Found
Location: https://app.example.com/auth/callback?code=<one-time-code>&state=<matching-state>
~~~

SPA public client gửi request trao đổi code (khi AS cho phép public client gọi token endpoint trực tiếp và cấu hình CORS phù hợp):

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Content-Type: application/x-www-form-urlencoded
Accept: application/json

grant_type=authorization_code
&client_id=orders-spa
&code=<authorization-code>
&redirect_uri=https%3A%2F%2Fapp.example.com%2Fauth%2Fcallback
&code_verifier=<original-pkce-verifier>
~~~

Body trên được xuống dòng **chỉ để minh họa**; request form thật phải encode đúng thành một chuỗi. **Confidential client** thực hiện client authentication theo đăng ký tại token endpoint và vẫn nên dùng PKCE.

Phản hồi token minh họa:

~~~json
{
  "access_token": "<opaque-or-jwt-access-token>",
  "token_type": "Bearer",
  "expires_in": 900,
  "scope": "orders.read",
  "id_token": "<oidc-id-token-if-openid-request>"
}
~~~

Refresh token có thể được cấp **theo policy**, không phải kết quả bắt buộc của mọi authorization code exchange. `id_token` chỉ hiện diện theo OIDC profile/flow; access token có thể là JWT hoặc opaque.

**Lưu ý:** `expires_in` là thời lượng token còn hiệu lực theo response, không phải authorization request parameter. `exp`, `iat`, `nbf`, `aud` thường là claims/metadata của token, **không phải quyền cho client tự đặt** ở authorization request.

## 17. Authorization response `iss` và chống mix-up khi nhiều issuer

Nếu một client đăng nhập với nhiều AS/OP, attacker có thể cố gắng **đánh tráo authorization response** giữa các issuer. Chỉ nhận code và state mà không ràng buộc chính xác endpoint/issuer có thể khiến client gửi code hoặc verifier tới nơi sai.

**RFC 9207 — OAuth 2.0 Authorization Server Issuer Identification** định nghĩa authorization response parameter `iss`, cho phép client đối chiếu issuer trả response với issuer của transaction đã khởi tạo.

~~~http
HTTP/1.1 302 Found
Location: https://app.example.com/auth/callback
  ?code=<code>
  &state=<matching-state>
  &iss=https%3A%2F%2Fauth.example.com
~~~

Ví dụ bị xuống dòng để đọc. Khi AS/profile hỗ trợ `iss`:

- Client lưu **issuer dự kiến** trong transaction khi bắt đầu.
- Callback so `iss` trả về với issuer đã đăng ký, không tin issuer tùy ý từ response để tự khám phá token endpoint.
- Nếu `iss` sai hoặc bị thiếu trái contract, **từ chối** thay vì tiếp tục.
- Token endpoint URL cũng phải đến từ metadata đã được tin cậy cho **issuer tương ứng**.

Với AS cũ không hỗ trợ `iss`, client đa issuer phải áp **biện pháp mix-up defense tương đương** theo profile/threat model, ví dụ redirect URI tách biệt và binding request/issuer chặt. Đừng tự gửi code đến một token endpoint được lấy từ dữ liệu chưa được xác minh.

## 18. Lưu trữ và bảo vệ authorization code, state và token

Mỗi giá trị có vòng đời và rủi ro khác nhau:

| Giá trị | Đi qua browser URL? | Nơi nên giữ | Khi nào loại bỏ? |
| --- | --- | --- | --- |
| `client_id` | Có | Config công khai | Không phải bí mật |
| `state` | Có | Transaction ngắn hạn gắn phiên | Sau callback/timeout |
| `code_challenge` | Có | Có thể công khai trong request | Sau khi AS hoàn thành grant |
| `code_verifier` | **Không** ở authorization URL | Transaction client/BFF bảo vệ | Sau token exchange/timeout |
| Authorization code | Có trong callback URL query ở query mode | Xử lý một lần, không lưu lâu | Ngay sau code exchange |
| OIDC `nonce` | Có | Transaction client/BFF | Sau khi validate ID token |
| Access token | **Không** trong authorization request URL | Memory/vault/BFF token store phù hợp | Khi hết hạn/logout/thu hồi |
| Refresh token | **Không** trong authorization URL/API call | Kho bảo vệ theo client type | Rotation/revocation/hết hạn |
| Client secret | **Không** ở frontend/authorization URL | Backend secret manager | Rotation theo policy |

**Không ghi authorization code, code verifier, access token hay refresh token vào access logs, analytics, query history, tracing hoặc bug reports.** Callback query có code cần được xử lý sớm và dọn khỏi URL bằng cơ chế thích hợp sau khi xác minh response; vẫn phải bảo vệ server/proxy logs.

### 18.1. XSS và cross-origin handling

XSS trên SPA có thể đọc transaction storage hoặc điều khiển ứng dụng khi authorization đang diễn ra. Phòng ngừa XSS, CSP/Trusted Types khi phù hợp, giới hạn third-party scripts và kiểm soát redirect là lớp bảo vệ quan trọng.

CORS chỉ quản lý browser cross-origin access; **không tự xác thực client** và không thay PKCE, state, token validation. Token endpoint cho SPA chỉ hỗ trợ CORS theo AS policy; BFF có thể thực hiện token exchange server-to-server.

## 19. Các lỗi phổ biến và cách xử lý

| Lỗi | Khi nào xuất hiện? | Cách xử lý |
| --- | --- | --- |
| `invalid_request` | Thiếu/sai parameter, malformed request | Kiểm tra response_type, client_id, redirect, PKCE, encoding |
| `unauthorized_client` | Client chưa được phép dùng response/grant type | Sửa registration/policy, không tự nới quyền |
| `invalid_scope` | Scope không được hỗ trợ/được phép | Xin scope hợp lệ theo AS và consent |
| `access_denied` | Người dùng/AS từ chối grant | Xử lý UX, không retry ép cấp quyền |
| `login_required` | OIDC `prompt=none` không thể đăng nhập im lặng | Dùng tương tác đăng nhập khi được phép |
| `consent_required` | OIDC cần consent nhưng request không cho tương tác | Cho phép consent theo quy trình hợp lệ |
| `invalid_grant` tại token endpoint | Code hết hạn, đã dùng, sai redirect/client/PKCE | Bắt đầu flow mới, không replay code |
| `invalid_client` tại token endpoint | Client authentication thất bại | Kiểm tra secret/key/mTLS tại backend |
| `state` không khớp | Callback không gắn transaction | Từ chối, cảnh báo và xóa transaction |
| `iss` khác issuer dự kiến | Mix-up hoặc cấu hình nhiều AS sai | Từ chối, không gửi code/verifier tới token endpoint lạ |
| Callback thiếu code, có error | AS trả lỗi | Đối chiếu state và xử lý an toàn |

### 19.1. AS không được redirect tự do khi redirect URI sai

Nếu request có `redirect_uri` không hợp lệ, AS **không được** gửi authorization code hoặc lỗi chứa dữ liệu nhạy cảm về URI của attacker. AS nên hiển thị lỗi an toàn trực tiếp hoặc xử lý theo profile mà **không redirect tới URI chưa được xác minh**.

### 19.2. HTTP lỗi không đồng nhất với authorization response error

Authorization endpoint có thể redirect về callback với `error=access_denied`, trong khi token endpoint thường trả JSON error với HTTP 400/401 thích hợp. Đừng nhầm lỗi front-channel `state` với Bearer `401 invalid_token` từ resource server khi gọi API.

## 20. Các tình huống thực tế

**Tình huống A — Code bị lộ qua browser history nhưng PKCE hoạt động.**

Một attacker biết authorization code nhưng **không có code verifier**. AS từ chối token request của attacker vì challenge không khớp. Client vẫn cần bảo vệ code URL, vì PKCE không phải lý do cho phép log hoặc phát tán code.

**Tình huống B — Redirect URI là open redirect.**

Client đăng ký `https://app.example.com/redirect` nhưng endpoint cho phép `?to=https://attacker.example`. Đây là thiết kế nguy hiểm; cần callback cố định, không forward code tới origin khác và exact matching ở AS.

**Tình huống C — App gửi `scope=orders.write` nhưng nhận `orders.read`.**

AS chỉ cấp scope được phép. Client không được bỏ qua scope đã cấp; API từ chối thao tác ghi khi token không đủ quyền.

**Tình huống D — SPA có nhiều tab và callback khác state.**

Hai tab khởi tạo các authorization transactions khác nhau. Nếu client chỉ giữ **một** biến state global, callback có thể bị nhầm. Lưu transaction theo state, có TTL và kiểm tra đúng tab/session.

**Tình huống E — Mobile app dùng loopback redirect.**

Native app dùng `http://127.0.0.1:<port>/callback` theo RFC 8252 và PKCE. Đây là ngoại lệ được quản lý cho native loopback, không phải giấy phép dùng wildcard redirect cho web.

**Tình huống F — OIDC `max_age=300` nhưng MFA không xảy ra.**

`max_age` yêu cầu authentication đủ mới, không tự bảo đảm một loại MFA cụ thể. Client phải kiểm tra `auth_time` và mức `acr/amr` khi policy step-up yêu cầu.

**Tình huống G — Client cố đăng nhập qua OP khác bằng một response cũ.**

Nếu client hỗ trợ nhiều issuer, cần gắn state với issuer và kiểm tra `iss` của response khi có theo RFC 9207; không đổi token endpoint dựa vào tham số chưa tin cậy.

**Tình huống H — Token đúng scope nhưng gọi sai audience.**

AS phát access token cho Orders API. Client đưa token cho Payments API. Payments API phải từ chối dù token có scope cùng tên, vì audience khác.

## 21. Kiểm thử bắt buộc

| Test case | Kỳ vọng |
| --- | --- |
| `response_type=code`, client/redirect hợp lệ | AS xử lý theo flow được cấp quyền |
| Thiếu `client_id` | AS từ chối request |
| `client_id` không tồn tại hoặc unauthorized | Không phát code |
| Redirect URI khác giá trị đã đăng ký | Không redirect code/error nhạy cảm đến URI giả |
| Redirect chứa wildcard/open redirect | Không được AS cho phép theo policy |
| Request không có PKCE khi client bắt buộc PKCE | Từ chối hoặc không cấp code theo profile |
| PKCE `S256` đúng | Token endpoint đối chiếu verifier thành công |
| PKCE verifier sai hoặc thiếu | Không đổi code được |
| PKCE chuyển `S256` sang `plain` trái policy | Từ chối downgrade |
| Authorization code được dùng hai lần | Lần sau bị từ chối |
| State thiếu/sai/hết hạn/đã dùng | Callback bị từ chối |
| Callback error có `state` không khớp | Không chấp nhận response |
| Client hỗ trợ nhiều AS, `iss` khác dự kiến | Chặn mix-up; không đổi code tại AS khác |
| `nonce` được gửi, ID token nonce sai | Client từ chối ID token |
| `scope=openid` và ID token hợp lệ | Client kiểm tra iss/aud/signature/nonce đúng policy |
| `scope` không được phép | AS không cấp vượt client/grant |
| `resource` không được đăng ký | AS từ chối hoặc áp policy, không phát audience tùy ý |
| API nhận token sai `aud` | Từ chối |
| Scope đúng nhưng object khác tenant | Từ chối object-level authorization |
| `prompt=none` khi cần consent/login | OP trả lỗi OIDC phù hợp, không bypass |
| `max_age` yêu cầu xác thực mới | Kiểm tra `auth_time`/step-up policy |
| Request URI PAR hết hạn hoặc không thuộc client | Từ chối |
| JAR signature/claims sai | Từ chối Request Object |
| Callback query có code | Xử lý một lần và xóa khỏi URL/logs |
| Reverse proxy phát sai external host | Không tạo redirect_uri từ spoofed header |
| Public client chứa client secret trong JS | Kiểm tra bảo mật thất bại |
| Cùng code/transaction được replay sau logout | Từ chối |
| Token response thiếu access token hoặc token type sai | Client xử lý lỗi, không coi là đăng nhập hợp lệ |
| Access token gửi sai API hoặc bị thu hồi | Resource server từ chối theo policy |

Khi làm integration tests, dùng **AS/OP test fixture và credentials thử nghiệm**, không dán code/token thật vào logs hoặc báo cáo lỗi. Unit test chỉ mock `Authentication` không đủ chứng minh state, PKCE và redirect validation hoạt động.

## 22. Checklist triển khai authorization request

1. **Đăng ký client đúng loại:** public/confidential; `client_id`, grant, response types, redirect URIs và client authentication.
2. **Dùng Authorization Code + PKCE:** `response_type=code`, code verifier ngẫu nhiên, challenge S256 và kiểm tra tại token endpoint.
3. **Cố định `redirect_uri`:** exact registration, HTTPS cho web, ngoại lệ native loopback đúng chuẩn; không open redirect.
4. **Ràng buộc callback:** `state` ngẫu nhiên, TTL, transaction theo session/tab, one-time consumption và issuer binding.
5. **Nếu dùng OIDC:** `scope=openid`, nonce theo policy, xác minh ID token, phân biệt `auth_time` với `iat`.
6. **Giới hạn scopes:** chỉ xin quyền cần thiết; không tự mặc định AS cấp mọi scope yêu cầu.
7. **Giới hạn resource/audience:** dùng RFC 8707 khi hỗ trợ; resource server kiểm tra token `aud` thực tế.
8. **Chỉ dùng tham số mở rộng có contract:** `prompt`, `max_age`, `acr_values`, `authorization_details`, `response_mode`, PAR/JAR.
9. **Không lộ credential:** client secret/code_verifier/token không nằm trong URL, logs, analytics hoặc browser state bền vững không có thiết kế.
10. **Trao đổi code đúng endpoint:** `grant_type=authorization_code`, code, cùng redirect URI và PKCE verifier; confidential client phải authn.
11. **Tách ID token và access token:** OIDC client kiểm tra ID token; API xác minh access token JWT/opaque, issuer, audience, time và scope.
12. **Phân quyền tại API:** kiểm tra tenant, role, ownership, resource state và khả năng thu hồi; code flow không thay authorization.
13. **Kiểm soát nhiều issuer:** RFC 9207 `iss` hoặc biện pháp mix-up tương đương, không chọn token endpoint theo response tùy ý.
14. **Kiểm thử âm:** redirect injection, state mismatch, PKCE failure, code reuse, wrong audience, malicious issuer và lỗi frontend/proxy.

## 23. Tài liệu tham khảo

- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): authorization endpoint, `response_type`, `client_id`, `redirect_uri`, `scope`, `state` và code exchange.
- [RFC 7636 — Proof Key for Code Exchange (PKCE)](https://www.rfc-editor.org/rfc/rfc7636): `code_challenge`, `code_challenge_method`, `code_verifier` và S256.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): PKCE, redirect validation, mix-up, token theft/replay và OAuth security profile.
- [RFC 8252 — OAuth 2.0 for Native Apps](https://www.rfc-editor.org/rfc/rfc8252): native redirect, loopback và external user-agent.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): OIDC Authentication Request, `openid`, `nonce`, `prompt`, `max_age`, `auth_time`.
- [RFC 9207 — Authorization Server Issuer Identification](https://www.rfc-editor.org/rfc/rfc9207): tham số `iss` trong authorization response để chống mix-up.
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707): tham số `resource` và audience/resource binding.
- [RFC 9396 — Rich Authorization Requests (RAR)](https://www.rfc-editor.org/rfc/rfc9396): tham số `authorization_details` cho quyền theo cấu trúc.
- [RFC 9126 — Pushed Authorization Requests (PAR)](https://www.rfc-editor.org/rfc/rfc9126): gửi authorization request qua back-channel trước browser redirect.
- [RFC 9101 — JWT-Secured Authorization Request (JAR)](https://www.rfc-editor.org/rfc/rfc9101): bảo vệ nội dung authorization request bằng JWT Request Object.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): trusted discovery cho authorization/token/PAR endpoints và metadata.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): xác minh JWT access token tại resource server.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): vận chuyển access token và kiểm tra Bearer.
- [Spring Security — OAuth2 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html): client registration và authorization code login với Java/Spring.

**Ghi nhớ:** **Authorization request parameters quyết định cách client xin authorization code**, không trực tiếp cấp quyền API. `response_type=code`, `client_id`, `redirect_uri`, `scope`, `state` và PKCE phải được tạo, đăng ký và kiểm tra đúng; OIDC bổ sung `openid`, `nonce` và các yêu cầu authentication; extensions như `resource`, PAR/JAR/RAR chỉ dùng theo hợp đồng AS. Sau callback, client phải **ràng buộc state/issuer, đổi code một lần với PKCE, bảo vệ token**, còn resource server vẫn xác minh issuer, audience, thời gian, scope và quyền trên tài nguyên.
