# RP-initiated logout

## 1. RP-initiated logout là gì và giải quyết vấn đề nào?

Trong chương **Logout** của module `SECURITY_TOKEN_SECURITY_FUNDAMENTALS`, **RP-initiated logout** là cơ chế của **OpenID Connect (OIDC)** cho phép một **Relying Party (RP)** — ứng dụng đã đăng nhập người dùng qua **OpenID Provider (OP)** — **khởi xướng yêu cầu kết thúc phiên đăng nhập tại OP**. Nó được chuẩn hóa trong **OpenID Connect RP-Initiated Logout 1.0**.

Ví dụ: Alice đăng nhập ứng dụng `sales-dashboard` qua OP `https://auth.example.test`. Sau đó Alice chọn **Đăng xuất**. Một hành vi đúng có thể bao gồm:

1. Ứng dụng kết thúc **local session** của Alice, xóa/bất hoạt cookie và dữ liệu xác thực phía RP.
2. RP chuyển trình duyệt Alice tới **`end_session_endpoint` của OP** kèm các tham số logout phù hợp.
3. OP nhận diện phiên trình duyệt hiện tại, áp chính sách/điều kiện logout, kết thúc **OP SSO session** tương ứng nếu yêu cầu được chấp nhận.
4. OP có thể đưa trình duyệt về **`post_logout_redirect_uri` đã đăng ký** của RP.
5. RP hiển thị trạng thái đã đăng xuất tại ứng dụng của mình; nếu còn phiên tại RP khác hoặc còn access/refresh token, chúng được xử lý bằng **các cơ chế bổ sung**.

**Đăng xuất ứng dụng không đồng nghĩa đăng xuất OP, và đăng xuất OP không đồng nghĩa mọi access token đã phát hành bị thu hồi.** Đây là điểm cần phân biệt ngay từ đầu.

> **Ý chính:** **RP-Initiated Logout** là **giao thức điều phối browser logout giữa RP và OP**. Nó **không** phải RFC 7009 token revocation endpoint, không phải API để RS kiểm tra `active`, và không bảo đảm xóa mọi local session ở các ứng dụng khác nếu thiếu front-/back-channel logout integration.

Trong bài, miền `example.test`, client IDs, token và URI chỉ là dữ liệu minh họa, không phải credential hoặc endpoint thật.

### Mục tiêu học tập

Sau khi học, bạn sẽ:

- Phân biệt **RP local logout**, **OP SSO logout**, **RP-initiated logout**, **Front-Channel/Back-Channel Logout**, **OAuth token revocation** và **consent withdrawal**.
- Xác định OP `end_session_endpoint` từ discovery metadata **đã được tin cậy**.
- Giải thích `id_token_hint`, `client_id`, `logout_hint`, `post_logout_redirect_uri`, `state` và `ui_locales`.
- Thiết kế browser flow và thứ tự cleanup an toàn, kiểm soát **CSRF, open redirect, callback state, session fixation và rò ID token**.
- Hiểu giới hạn của logout khi **JWT access token còn hạn**, refresh token còn hợp lệ, nhiều tabs, nhiều RPs, federation và OP outage.
- Sử dụng **Spring Security OAuth2 Login** và `OidcClientInitiatedLogoutSuccessHandler` đúng vai trò, có tests và kế hoạch fail-safe.

## 2. Những phiên, token và quyền có thể còn tồn tại khi Alice chọn Logout

Để đánh giá logout chính xác, phải tách các trạng thái:

| Trạng thái | Nằm ở đâu? | Khi Alice chọn Logout tại `sales-dashboard` |
| --- | --- | --- |
| **RP local session** | Browser cookie + session store của `sales-dashboard` | RP phải kết thúc phiên của chính nó |
| **OP/IdP SSO session** | Browser cookie và session store của `auth.example.test` | Chỉ kết thúc khi OP logout thành công theo policy |
| **Local session của RP khác** | `hr-dashboard`, `wiki-app`, `billing-app` | Không tự mất nếu chưa có logout notification/integration riêng |
| **Access token (AT)** | Browser, BFF/token store, API caller | Có thể còn sống đến `exp` hoặc cho đến khi RS biết revocation |
| **Refresh token (RT)** | Client token store | Cần RFC 7009/AS grant revocation hoặc cơ chế riêng nếu muốn chặn lấy AT mới |
| **Authorization grant/consent** | AS policy/consent store | Không tự mất vì OP kết thúc phiên SSO |
| **OIDC ID token** | RP giữ như chứng cứ authentication | Có thể dùng `id_token_hint` để trợ giúp OP nhận diện session; không phải AT |
| **Domain permissions** | RS/ứng dụng IAM/ACL | Không tự thay đổi chỉ vì một browser logout |

Một tổ chức thường muốn **đăng xuất RP và OP**, đồng thời **thu hồi RT/grant của client** theo chính sách. Nhưng ba hành động đó cần thiết kế rõ. Không dùng một nút Logout rồi nói “mọi token bị xóa trên toàn hệ thống” khi chưa có cách chứng minh.

### 2.1. Bốn vai trò trong bài

| Vai trò | Ví dụ | Trách nhiệm |
| --- | --- | --- |
| **End-user** | Alice | Chủ động yêu cầu kết thúc phiên ứng dụng |
| **Relying Party (RP)** | `sales-dashboard` | Sở hữu local session, định danh client, quyết định chuyển sang OP logout |
| **OpenID Provider (OP)** | `https://auth.example.test` | Sở hữu OP SSO session, công bố logout endpoint và thực hiện logout policy |
| **Resource Server (RS)** | `orders-api` | Xác minh OAuth AT đúng issuer/audience/expiry/scope và ACL; không suy token revoked từ browser logout |

RP chính là một OAuth client sử dụng OIDC để xác thực user; OP là authorization server có khả năng OIDC. RS có thể thuộc cùng tổ chức nhưng không trở thành thành phần trực tiếp của browser OP logout.

### 2.2. Đăng xuất không phải authorization decision

OIDC `openid` yêu cầu xác thực end-user. OAuth scopes như `orders.read` cấp quyền gọi API trong giới hạn policy. Alice logout:

- **Kết thúc phiên đăng nhập**, không tự cấp hay hủy role nhân viên.
- **Không** sửa scope hoặc audience bên trong JWT AT đã ký.
- **Không** biến ID token thành access token.
- **Không** thay mọi quyết định object/tenant authorization tại RS.

Nếu user bị khóa tài khoản hoặc admin rút quyền truy cập API, cần xem xét state check/denylist/introspection hoặc TTL để thực thi chính sách nhanh hơn AT còn hạn.

## 3. Phân biệt năm cơ chế logout và revoke

| Cơ chế | Bên khởi xướng/đích | Mục tiêu | Điều không bảo đảm |
| --- | --- | --- | --- |
| **RP local logout** | RP → local session store/browser cookie | Ngăn reuse session của RP | Kết thúc OP SSO session hoặc các RP khác |
| **OIDC RP-Initiated Logout** | RP đưa browser → OP `end_session_endpoint` | Yêu cầu OP kết thúc phiên SSO trong browser | Revoke tất cả RT/AT hoặc mọi RP session |
| **OIDC Front-Channel Logout** | OP → browser iframes/URLs ở các RPs | Thông báo logout qua browser front channel | Đảm bảo deliver khi third-party cookie/tracking protection chặn |
| **OIDC Back-Channel Logout** | OP → logout endpoint của RPs qua server-to-server | Thông báo OP logout để RP vô hiệu phiên phía server | Token revocation RS trực tiếp nếu không thiết kế thêm |
| **RFC 7009 Token Revocation** | Authorized client → AS revocation endpoint | Vô hiệu token, có thể liên quan grant/RT family theo AS | Kết thúc cookie SSO tại OP hoặc từng RP session |

Một OP/RP có thể chỉ hỗ trợ một phần các cơ chế. **RP-Initiated Logout 1.0** định nghĩa cách **khởi xướng** từ RP; **Front-/Back-Channel Logout** định nghĩa cách **truyền thông báo tới RPs**. Không gọi ba cơ chế này đồng nghĩa nhau.

### 3.1. Kịch bản tối thiểu

~~~text
Alice logout sales-dashboard.
  sales-dashboard invalidates its own HTTP session.
  Browser is redirected to OP end_session_endpoint.
  OP terminates the matching browser SSO session.
  Browser returns to registered post_logout_redirect_uri.

Meanwhile:
  hr-dashboard may still hold its own RP session.
  orders-api may still accept a previously issued JWT AT.
  a valid RT may still mint new AT unless AS policy/revocation blocks it.
~~~

Nếu yêu cầu là “đăng xuất khỏi mọi ứng dụng và vô hiệu tất cả tokens”, cần bổ sung phối hợp OP notification, RP session invalidation, RT/grant revocation và RS token-status policy. **Một redirect tới OP chưa đủ** để xác nhận mục tiêu này.

### 3.2. Khi nào cần một trong các lựa chọn?

- **Logout riêng ứng dụng này:** thường chỉ cần RP local logout, có thể không muốn ảnh hưởng OP SSO nếu product có nhiều ứng dụng.
- **Logout khỏi hệ thống SSO đang dùng trên browser:** RP-Initiated Logout là cách để yêu cầu OP kết thúc SSO session.
- **Thông báo cho các RPs khác:** OP cần Front-/Back-Channel Logout theo registration/policy, không chỉ RP-initiated request.
- **Chặn token bị lấy cắp hoặc logout một thiết bị:** AS revocation/RT token family và RS revocation freshness riêng.
- **Rút quyền/consent lâu dài:** quản lý OAuth grant/consent lifecycle, không chỉ xóa session cookie.

## 4. OP `end_session_endpoint`: nguồn tin cậy và discovery

Relying Party phải biết **đúng OP** đã phát hành ID token và nơi OP xử lý logout. OIDC Discovery metadata có thể công bố `end_session_endpoint`, ví dụ:

~~~http
GET /.well-known/openid-configuration HTTP/1.1
Host: auth.example.test
Accept: application/json
~~~

Response minh họa:

~~~json
{
  "issuer": "https://auth.example.test",
  "authorization_endpoint": "https://auth.example.test/oauth2/authorize",
  "token_endpoint": "https://auth.example.test/oauth2/token",
  "jwks_uri": "https://auth.example.test/oauth2/jwks",
  "end_session_endpoint": "https://auth.example.test/connect/logout"
}
~~~

**`end_session_endpoint` không phải một đường dẫn URL cố định của mọi OP.** Một provider có thể dùng `/connect/endsession`, `/protocol/openid-connect/logout` hoặc đường dẫn khác. Không đoán endpoint bằng cách nối `/logout` vào issuer rồi gửi ID token đến đó.

### 4.1. Quy tắc tin cậy metadata

1. RP bắt đầu từ **expected issuer** đã được phê duyệt và registration gắn với OIDC login.
2. Metadata được tải qua **HTTPS với certificate và hostname validation**.
3. RP so `issuer` trong metadata với issuer đã cấu hình, theo OIDC Discovery rules.
4. Chỉ sử dụng `end_session_endpoint` thuộc **trusted provider metadata/config**, không lấy từ request query, session cookie, claims chưa verify hoặc header của attacker.
5. Trong hệ thống multi-issuer, transaction logout gắn với **đúng registration/OP** đã xác thực user.
6. Nếu metadata không công bố logout endpoint và không có cấu hình tin cậy khác, RP không tự chuyển ID token đến URL bất kỳ; có thể thực hiện local logout và nêu giới hạn OP logout.

HTTPS chỉ chứng minh kết nối đến host được chọn; nó **không chứng minh** host đó được phép nhận ID token của Alice. Chọn đúng issuer/endpoint là trust boundary độc lập.

### 4.2. Phân biệt ba loại endpoint

| Endpoint | Mục đích | Ai tương tác? |
| --- | --- | --- |
| `authorization_endpoint` | OIDC/OAuth authorization request, đăng nhập và cấp authorization code | Browser |
| `token_endpoint` | Code/refresh/token-exchange grants và cấp AT/ID token | Client qua back channel |
| `end_session_endpoint` | RP-initiated OP SSO logout | Browser, thường redirect GET |
| `revocation_endpoint` | RFC 7009 thu hồi AT/RT theo client/AS policy | Authorized client qua back channel |
| `introspection_endpoint` | RFC 7662 kiểm tra token `active`/metadata | Authorized RS qua back channel |

Nếu client gửi RT tới `end_session_endpoint` thay vì RFC 7009 revocation endpoint, đó là lỗi thiết kế. Nếu RS gọi `end_session_endpoint` để biết AT còn sống không, đó cũng là sai giao thức.

## 5. Các tham số chuẩn của RP-Initiated Logout Request

OIDC RP-Initiated Logout 1.0 định nghĩa các tham số chính:

| Tham số | Trạng thái trong spec | Nguồn/ý nghĩa | Cẩn trọng |
| --- | --- | --- | --- |
| **`id_token_hint`** | **RECOMMENDED** | ID token OP đã phát cho RP, giúp OP nhận diện user/client/session | Không gửi AT/RT vào đây; bảo vệ khỏi URL/log leakage |
| **`logout_hint`** | **OPTIONAL** | Gợi ý về user/session cần logout (ví dụ login hint theo contract OP) | Hint không phải proof; không tin dữ liệu tự khai như authentication |
| **`client_id`** | **OPTIONAL** | Xác định RP client; hữu ích nếu thiếu `id_token_hint` hoặc OP cần xác định registration | Không đủ xác minh browser session chỉ nhờ client_id public |
| **`post_logout_redirect_uri`** | **OPTIONAL** | URI RP muốn browser quay về sau OP logout | Phải được OP xác minh phù hợp **registered post-logout redirect URIs** |
| **`state`** | **OPTIONAL** | Giá trị RP tạo để liên kết OP logout redirect với giao dịch logout | Random, one-time, bound to RP browser/session; verify exact khi callback |
| **`ui_locales`** | **OPTIONAL** | Ngôn ngữ giao diện OP ưa thích | Không ảnh hưởng authentication/authorization |

Trong GET request, các tham số trên phải được **URL-encode** theo chuẩn; không gắn chuỗi ID token hoặc URI chưa encode bằng phép nối đơn giản. OP **MUST support HTTP GET** cho RP-Initiated Logout Request; OP **MAY support HTTP POST** tùy implementation và chính sách. Vì GET có thể mang `id_token_hint` trong URL, cần đặc biệt kiểm soát log, referrer, history và các bên nhận URL.

### 5.1. `id_token_hint` là hint, không phải bearer AT hay lệnh revoke

Một ID token có thể có claims:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "alice-742",
  "aud": "sales-dashboard",
  "sid": "op-session-example-932",
  "iat": 1893455700,
  "exp": 1893456000
}
~~~

Đây **chỉ là payload minh họa**, không phải JWT có chữ ký hợp lệ. RP chỉ nên dùng ID token **đã được xác minh trong phiên OIDC tương ứng** làm hint. `sid` là session identifier dùng trong một số OIDC logout profiles khi được OP phát hành; không phải claim bắt buộc của mọi ID token và không nên tự sinh rồi khẳng định OP sẽ hiểu.

OP tự đánh giá `id_token_hint` theo chính sách và phiên hiện có. Một ID token đã hết `exp` đôi khi vẫn hữu ích như **hint nhận diện** theo OP implementation/spec, nhưng không được coi expiry bypass là một authentication proof. Không dùng `id_token_hint` để xác minh OAuth scopes tại RS.

### 5.2. `client_id` không tự cho phép redirect bất kỳ

`client_id=sales-dashboard` thường là public identifier. Attacker cũng có thể biết nó. Vì thế, OP phải kiểm tra post-logout redirect URI thuộc registration phù hợp và đủ thông tin nhận diện RP/context; không tin client_id đơn lẻ để gửi browser đến URL tùy ý.

Nếu thiếu `id_token_hint`, việc bổ sung `client_id` có thể giúp OP xác định registration nhưng **không bảo đảm OP thực hiện silent logout/redirect**; OP có thể cần user confirmation hoặc context đáng tin khác theo spec/policy.

### 5.3. `post_logout_redirect_uri` khác OAuth `redirect_uri`

OAuth authorization callback:

~~~text
redirect_uri=https://portal.example.test/login/oauth2/code/company
~~~

OIDC logout callback:

~~~text
post_logout_redirect_uri=https://portal.example.test/signed-out
~~~

Đây là **hai loại URI phục vụ mục đích khác nhau** và có thể phải được đăng ký/tin cậy riêng ở OP. Không cho phép wildcard URL, scheme `javascript:`, chuyển tiếp qua open redirect hoặc redirect URI do browser cung cấp.

### 5.4. `state` là correlation, không thay CSRF protection cho local logout

RP nên tạo state ngẫu nhiên **riêng cho mỗi logout transaction**, lưu an toàn (ví dụ short-lived server-side record hoặc protected cookie/session) và so đúng giá trị OP trả về khi redirect.

Nhưng `state` **không** bảo vệ endpoint `POST /logout` của RP khỏi CSRF nếu endpoint đó bị thiết kế thiếu CSRF validation. Hai việc khác nhau:

- **CSRF defense ở RP local logout:** kiểm soát ai có thể khởi xướng hành động xóa session.
- **State ở OP callback:** ràng buộc redirect từ OP vào transaction logout đúng, tránh callback mix-up/replay.

Không dùng `state` như access token, login credential hoặc bằng chứng OP đã revoke tất cả RT.

## 6. Luồng chuẩn từ nút Logout tới OP và trở lại RP

Giả sử `sales-dashboard` là **Spring MVC/BFF** giữ session ở backend. User Alice có session hợp lệ tại RP và OP, rồi chủ động chọn Logout.

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Alice / Browser
    participant RP as sales-dashboard / RP
    participant OP as auth.example.test / OP
    participant S as Session store / Token store
    U->>RP: POST /logout + CSRF token
    RP->>RP: Xác minh local session & logout request
    RP->>S: Invalidate RP session / cookie; cleanup token state
    RP->>RP: Lấy ID token từ Authentication đã được xác minh
    RP->>RP: Tạo OP logout request, state nếu dùng
    RP-->>U: HTTP 302 Location: trusted end_session_endpoint
    U->>OP: GET /connect/logout? id_token_hint=...&...
    OP->>OP: Xác minh RP context và browser OP session
    opt Chính sách yêu cầu xác nhận
        OP->>U: Trang xác nhận đăng xuất
        U-->>OP: Xác nhận
    end
    OP->>OP: Kết thúc OP SSO session theo policy
    OP-->>U: Redirect tới registered post_logout_redirect_uri
    U->>RP: GET /signed-out?state=...
    RP->>RP: Verify callback state nếu sử dụng
    RP-->>U: Trang "Đã đăng xuất" (không tự login)
~~~

**Sơ đồ là một successful path minh họa**, không bảo đảm OP sẽ thực hiện mọi bước hoặc redirect trong tất cả trường hợp. Nếu `end_session_endpoint` không được hỗ trợ, OP session có thể còn. Nếu browser không theo redirect, local session đã kết thúc nhưng OP logout chưa xảy ra.

### 6.1. Bắt đầu bằng hành động có chủ ý

Ứng dụng nên cung cấp **POST Logout** với CSRF protection đối với browser cookie-based session. Một link GET có tác dụng thay đổi session có thể bị bên ngoài kích hoạt qua image/link/prefetch, gây **logout CSRF** hoặc làm gián đoạn phiên.

Nếu một sản phẩm cần GET logout vì lý do tương thích, nó phải đánh giá chống CSRF/confirmation và UX; không coi GET thay POST là mặc định an toàn chỉ vì OP `end_session_endpoint` hỗ trợ GET. **POST tại RP** và **GET redirect đến OP** là hai request khác nhau.

### 6.2. Tạo logout transaction trước khi mất session dữ liệu cần dùng

RP cần chuẩn bị:

- Xác định **client registration/OP issuer** từ authenticated session.
- Lấy **ID token đã được OP cấp và RP xác minh** từ security context, nếu có.
- Chọn `post_logout_redirect_uri` từ allowlist/config, không từ query `returnTo` tự do.
- Tạo `state` nếu cần correlation; lưu state ở cơ chế **còn tồn tại đủ ngắn sau local session invalidation**.
- Xác định chính sách xử lý AT/RT server-side và audit.

Một lỗi thực tế: RP tạo `state` rồi lưu nó **chỉ trong HTTP session**, ngay sau đó invalidate toàn bộ session. Khi OP redirect trở lại, RP không còn bản ghi state để kiểm tra. Giải pháp là **one-time, short-lived logout transaction store** hoặc protected same-site cookie phù hợp, với binding đủ mạnh; không vì vậy bỏ kiểm state.

### 6.3. Cleanup local session phải bền vững

RP nên:

1. Hủy session identifier cũ phía server hoặc chuyển nó thành invalid.
2. Xóa cookie session bằng thuộc tính **name/path/domain** phù hợp; không chỉ ghi một cookie khác path.
3. Xóa token/authorized-client state đã được chính sách xác định; xử lý RT revocation riêng nếu cần.
4. Xóa CSRF/session-bound state và ngăn session fixation.
5. Đặt `Cache-Control: no-store` hoặc policy cache phù hợp trên nội dung nhạy cảm, bảo vệ nút Back/forward cache và API responses.
6. Đảm bảo browser dùng session cũ không thể gọi API nội bộ đã được RP bảo vệ.

Không chỉ hiển thị thông báo “Logout thành công” trong frontend mà giữ backend session và RT có thể được reuse. Ngược lại, local session cleanup thành công **không** tự chứng minh OP đã kết thúc SSO.

### 6.4. HTTP logout redirect minh họa

RP có thể trả:

~~~http
HTTP/1.1 302 Found
Location: https://auth.example.test/connect/logout?id_token_hint=<url-encoded-id-token>&post_logout_redirect_uri=https%3A%2F%2Fportal.example.test%2Fsigned-out&state=<opaque-random-state>
Cache-Control: no-store
Referrer-Policy: no-referrer
~~~

Đây là URL **minh họa**; giá trị thực cần được encoder của thư viện xây dựng, không nối thủ công. Các OP có thể hỗ trợ POST logout request nếu muốn giảm lộ ID token trong URL, nhưng **GET là phương thức spec yêu cầu OP hỗ trợ**. Không tự assume RP gửi POST nếu OP chỉ hỗ trợ GET.

### 6.5. Callback sau logout

Nếu OP đã xác thực `post_logout_redirect_uri`, nó có thể redirect browser về:

~~~http
GET /signed-out?state=<opaque-random-state> HTTP/1.1
Host: portal.example.test
~~~

RP:

- So sánh chính xác state với giao dịch logout còn hợp lệ (nếu đã gửi state).
- Consume state **một lần** và áp timeout.
- Chỉ hiển thị trang logout public, không khởi tạo session đã xóa.
- Không dùng callback này làm bằng chứng mọi AT/RT đã bị thu hồi.
- Không redirect tiếp tới bất kỳ `next=...` nào từ query không được allowlist.

### 6.6. Tại sao browser redirect chỉ là best-effort?

User có thể đóng tab sau khi RP gửi 302, tắt mạng, chặn navigation hoặc OP trả lỗi. Do đó:

~~~text
RP local session invalidated:   YES (server-side, đã commit).
Browser reached OP logout:     UNKNOWN until browser follows redirect.
OP session ended:              UNKNOWN without OP protocol signal/state.
User returned to RP callback:  MAYBE.
AT/RT revoked at AS:          NOT INFERRED from redirect.
~~~

Thiết kế UX phải phản ánh đúng trạng thái. Nếu OP logout chưa xác nhận, có thể nói “Bạn đã đăng xuất khỏi ứng dụng. Phiên đăng nhập ở nhà cung cấp danh tính có thể còn hoạt động” và đề xuất thao tác thích hợp thay vì khẳng định toàn hệ thống đã đăng xuất.

## 7. Session state machine và các nhánh lỗi

RP và OP không chia sẻ một transaction database, nên trạng thái logout có thể **không đồng bộ**:

~~~mermaid
stateDiagram-v2
    [*] --> AUTHENTICATED: OIDC login / RP session active
    AUTHENTICATED --> LOCAL_LOGOUT_REQUESTED: User submits POST /logout
    LOCAL_LOGOUT_REQUESTED --> RP_INVALIDATED: Server invalidates RP session
    RP_INVALIDATED --> OP_REDIRECT_PREPARED: Build trusted logout request
    OP_REDIRECT_PREPARED --> OP_PENDING: Browser visits end_session_endpoint
    OP_PENDING --> OP_ENDED: OP accepts & ends SSO session
    OP_PENDING --> OP_UNCONFIRMED: Browser interrupted / OP error
    OP_ENDED --> REDIRECT_COMPLETE: Registered callback + state
    OP_UNCONFIRMED --> [*]
    REDIRECT_COMPLETE --> [*]
~~~

Đây là state machine **application-level để thiết kế UX/observability**, không phải các trạng thái bắt buộc OIDC RP-Initiated Logout. Chỉ RP quyết định trạng thái của **local session**; chỉ OP quyết định trạng thái **OP SSO session**.

### 7.1. Không gọi kết quả chưa biết là “OP logout success”

Tình huống:

~~~text
T0   RP invalidates local session.
T1   RP sends 302 to OP logout endpoint.
T2   Browser loses network before visiting OP.
T3   Alice returns to RP; RP sees no local session.
T4   Alice clicks Login; OP SSO cookie still valid.
T5   OP can issue new OIDC authorization without prompting password.
~~~

Tại `T3`, local logout đã thành công; OP logout **chưa xảy ra**, vì thế login lại có thể diễn ra silently. Không “sửa lỗi” bằng cách bỏ OIDC state/nonce hoặc tin rằng `prompt=login` sẽ thu hồi mọi AT. Hãy đánh giá yêu cầu product là local logout hay full SSO logout, rồi dùng UX/retry theo cách không làm lộ credential.

### 7.2. OP có thể cần trang confirmation

OP có thể không xác định được phiên nào cần logout, nhận `id_token_hint` không phù hợp, hoặc có nhiều OP account sessions trên browser. Theo chính sách/đặc tả, OP có thể yêu cầu xác nhận người dùng thay vì silent logout. RP không được tự coi `client_id` public và `logout_hint` như chứng minh user đã ủy quyền logout.

### 7.3. Timeout ở OP không đồng nghĩa lỗi local logout

Nếu RP session đã bị hủy rồi:

- Trả trải nghiệm lỗi OP logout **không được tạo lại session cũ**.
- Không khôi phục RT hoặc AT đã xóa chỉ vì muốn “thử lại logout”.
- Có thể cho user thử truy cập OP logout endpoint tin cậy lần nữa bằng một flow được giới hạn.
- Đánh dấu trạng thái OP logout là **unknown**, không là success.
- Đừng đưa raw `id_token_hint` vào client-side log hoặc support ticket để debug.

### 7.4. Một logout request không nên có hiệu lực vô hạn

Giới hạn:

- Logout transaction state TTL ngắn, chống replay.
- Registered redirect URI exact match; không wildcard.
- Không reuse state của lần logout trước cho user khác.
- Nếu RP đã logout rồi, tiếp tục gửi same logout URL lặp lại có thể gây UX kỳ lạ tại OP; cần idempotent local cleanup.
- `id_token_hint`/OP logout request phải gắn với đúng issuer/client context, không trộn sessions.

## 8. Nhiều ứng dụng, nhiều tab và SSO: ai thực sự đã logout?

Giả sử Alice có ba ứng dụng:

~~~text
OP SSO session:      S-OP-123
RP-A sales-dashboard: session S-A
RP-B hr-dashboard:    session S-B
RP-C wiki-app:        session S-C
~~~

Alice logout tại RP-A. Sau khi OP kết thúc SSO session `S-OP-123`, **`S-B` và `S-C` không tự biến mất** chỉ vì OP cookie bị xóa. Chúng là local sessions do hai RPs khác nhau quản lý.

### 8.1. Nếu OP chỉ hỗ trợ RP-Initiated Logout

~~~text
RP-A local session invalidated.
OP SSO session invalidated.
RP-B still has local session cookie.
RP-C still has local session cookie.
~~~

RP-B và RP-C có thể tiếp tục phục vụ local-authenticated requests cho đến khi tự check session/OP state hoặc nhận logout notification. Trong hệ thống đòi single logout, đó là thiết kế chưa đầy đủ.

### 8.2. Front-Channel Logout và browser restrictions

Với **OIDC Front-Channel Logout**, OP có thể dẫn browser tải các logout URIs của RPs, thường thông qua iframes. RP có thể dùng OP `iss` và `sid` nếu profile cung cấp để biết phiên nào cần invalidation.

Những rủi ro:

- Third-party cookies bị chặn hoặc SameSite policy làm RP không nhận đúng session cookie.
- Iframe/network/JS policy ngăn logout URI hoàn tất.
- User đóng tab trước khi browser tải hết logout frames.
- Các RPs có khả năng xác minh `iss`/`sid` khác nhau.

Không dựa vào front-channel logout **một mình** nếu yêu cầu bắt buộc kết thúc mọi RP server session ngay cả khi browser không thực hiện yêu cầu.

### 8.3. Back-Channel Logout

Với **OIDC Back-Channel Logout**, OP gửi **Logout Token** đã ký đến registered back-channel logout URI của RP thông qua server-to-server request. RP xác minh token, tìm phiên liên quan và vô hiệu hóa server-side sessions.

Một Logout Token có thể có:

~~~json
{
  "iss": "https://auth.example.test",
  "aud": "hr-dashboard",
  "iat": 1893455700,
  "jti": "logout-event-example-22",
  "sid": "op-session-example-932",
  "events": {
    "http://schemas.openid.net/event/backchannel-logout": {}
  }
}
~~~

Payload này **chỉ minh họa**, không phải JWT Logout Token thực sự đã ký. Một Logout Token không phải ID token hay AT; `events` định nghĩa logout event. RP phải kiểm **chữ ký, expected issuer, audience, event semantics, thời gian, `jti` replay và `sid`/`sub` theo profile**; Back-Channel Logout Token **không chứa `nonce`** theo spec. Nếu OP dùng `sid`, RP phải lưu mapping OP session ↔ local sessions an toàn ngay từ lúc login.

Đừng coi một HTTP POST bất kỳ đến `/backchannel-logout` có tham số `sid=...` là đủ; nếu không verify Logout Token, attacker có thể logout hàng loạt phiên.

### 8.4. RP-Initiated và Back-Channel phối hợp

Một triển khai SSO logout đầy đủ có thể:

1. RP-A nhận yêu cầu của Alice và hủy local session.
2. Browser đi đến OP `end_session_endpoint` (RP-Initiated).
3. OP kết thúc OP SSO session.
4. OP phát Back-Channel Logout Tokens tới RP-B/RP-C đã đăng ký.
5. RP-B/RP-C xác minh Logout Tokens, invalidate local sessions theo `sid`/`sub` context.

Ngay cả mô hình này **không** tự revoke mọi OAuth AT/RT ở RS; các token/grant cần policy riêng. Hãy kiểm tra OP có hỗ trợ back-channel thông qua metadata/registration và test end-to-end.

### 8.5. Nhiều tabs của cùng một RP

Một browser có thể mở `sales-dashboard` ở tab A và B. Khi A logout:

- Server session bị invalidate, request mới từ B phải bị từ chối hoặc redirect login.
- UI ở tab B có thể vẫn hiển thị dữ liệu đã render/cached.
- Có thể dùng BroadcastChannel/client events **để cải thiện UX**, nhưng server-side session invalidation mới là điều quyết định.
- Frontend không thể chỉ xóa cookie `HttpOnly` bằng JavaScript; backend phải quản lý session/cookie.
- Không dựa vào UI “Đã đăng xuất” như bằng chứng mọi tab đã ngừng có token.

### 8.6. OP federation và upstream IdP

OP có thể liên kết với upstream corporate IdP/social provider. RP-Initiated Logout tại **OP đang trực tiếp phát ID token cho RP** không bảo đảm upstream IdP hoặc federation session bị kết thúc; điều đó phụ thuộc logout propagation và contract giữa OP/upstream IdP.

Nếu Alice login lại và upstream IdP vẫn còn session, cô ấy có thể được xác thực trở lại mà không nhập password. Cần xác định sản phẩm muốn **RP logout**, **OP logout** hay **full federated logout**; không khẳng định cơ chế thứ ba khi chưa được kiểm chứng.

## 9. AT, RT và consent sau RP-initiated logout

### 9.1. ID token là hint nhận diện, không mang quyền gọi API

ID token trong `id_token_hint` giúp OP hiểu ngữ cảnh RP/login; không gửi ID token vào `Authorization: Bearer ...` tới `orders-api`. Resource API phải chỉ chấp nhận OAuth AT đúng issuer, token purpose, audience, scope và domain ACL.

### 9.2. Refresh token chưa chắc bị revoke

Nếu RP có RT, việc browser sang `end_session_endpoint` **không phải RFC 7009 revocation request**. Tùy OP, logout có thể revoke grant/session tokens theo policy nội bộ, nhưng **không được mặc định**. Nếu yêu cầu bảo mật là chặn lấy AT mới, ứng dụng/AS cần:

- Thu hồi RT hoặc grant theo RFC 7009/AS-supported mechanism.
- Dọn local authorized-client/token store.
- Áp refresh-token rotation/reuse detection nếu RT vẫn được sử dụng theo grant.
- Xác minh revocation có hiệu lực theo phạm vi yêu cầu (per-device, per-client, all sessions) và client authentication.

Một lỗi thường gặp là xóa RT ở browser nhưng để bản sao RT bị lấy cắp còn hợp lệ tại AS. Cleanup local không thay AS revocation.

### 9.3. Revocation endpoint và HTTP request riêng

~~~http
POST /oauth2/revoke HTTP/1.1
Host: auth.example.test
Authorization: Basic <registered-confidential-client-auth>
Content-Type: application/x-www-form-urlencoded

token=<refresh-token>&token_type_hint=refresh_token
~~~

Đây là **RFC 7009 token revocation minh họa**, không phải RP-Initiated Logout. AS thường trả HTTP 200 ngay cả khi token đã không hợp lệ theo RFC 7009 để tránh token probing; client cần đánh giá outcome khi network timeout. Public client và confidential client có phương thức authentication khác nhau theo registration.

**Đừng** nhúng RT trong `end_session_endpoint` URL hoặc `post_logout_redirect_uri`.

### 9.4. JWT AT đã cấp có thể tiếp tục được chấp nhận

Ví dụ:

~~~text
10:00  AS cấp JWT access token, aud=orders-api, exp=10:15.
10:02  Alice logout sales-dashboard; RP session invalidated.
10:03  OP SSO session ended via RP-Initiated Logout.
10:04  Attacker còn giữ bearer AT đã bị lộ trước đó.
10:04  orders-api chỉ verify JWT signature + exp:
       Token có thể vẫn được chấp nhận.
~~~

Nếu SLA yêu cầu chặn ngay sau logout, cần **opaque introspection với cache freshness đủ chặt**, JWT denylist/session-state check, AT TTL ngắn có giới hạn rủi ro, hoặc authorization state trong RS. RT revoke ngăn issuance mới nhưng không tự thay đổi chữ ký/`exp` của JWT cũ.

### 9.5. Consent withdrawal khác logout

Logout kết thúc session theo policy. **Withdraw consent** có thể có nghĩa user/admin rút quyền client được phát token trong tương lai. Một lần OP logout không mặc nhiên xóa mọi consent record; một lần rút consent cũng không nhất thiết kết thúc tất cả RP sessions đang mở.

Phân biệt ba việc trong audit/UX:

~~~text
session_logout:
  RP or OP authenticated session ended.

grant_revocation:
  AS no longer accepts RT/associated grant under policy.

consent_withdrawal:
  User/admin permission decision removed or updated.
~~~

Đừng báo “đã xóa tài khoản” hoặc “đã thu hồi mọi quyền” nếu chỉ thực hiện browser RP-Initiated Logout.

## 10. Threat model của RP-initiated logout

### 10.1. Logout CSRF tại RP

Một website do attacker kiểm soát nhúng:

~~~html
<img src="https://portal.example.test/logout">
~~~

Nếu RP chấp nhận **GET /logout** và hủy session mà không có bảo vệ thích hợp, attacker có thể làm Alice bị đăng xuất ngoài ý muốn. Đây là **logout CSRF**: thường gây gián đoạn/UX, và trong một số flow có thể hỗ trợ session swapping hoặc user confusion.

**Phòng vệ:** RP dùng **POST /logout với CSRF protection**, kiểm tra method/session và thiết kế UX xác nhận khi cần. OP `end_session_endpoint` vẫn có thể dùng GET theo OIDC spec; điều này **không có nghĩa RP local logout phải dùng GET**.

### 10.2. Open redirect tại `post_logout_redirect_uri`

Ứng dụng nhận:

~~~http
POST /logout?returnTo=https://attacker.example.test/phish HTTP/1.1
Host: portal.example.test
~~~

Rồi RP lấy `returnTo` từ request, đưa thẳng vào `post_logout_redirect_uri`. Nếu OP hoặc RP cho phép URI lỏng lẻo, browser có thể bị chuyển sang website attacker sau khi logout, làm người dùng tưởng trang đăng nhập giả là thật.

**Phòng vệ:** RP chọn URI từ cấu hình/allowlist chặt; OP so với **registered post-logout redirect URIs**. Nếu hỗ trợ return path, chỉ nhận **relative path an toàn** có chính sách rõ, không nhận full URLs/open redirects, tránh double-encoding bypass.

### 10.3. OP logout endpoint injection

Một RP đọc `end_session_endpoint` từ query:

~~~text
/logout?logoutEndpoint=https://attacker.example.test/collect
~~~

RP nối `id_token_hint` rồi redirect browser sang URL đó. Attacker có thể thu ID token qua request/analytics/logs.

**Phòng vệ:** Endpoint phải lấy từ **trusted issuer metadata/registration**; không nhận host logout do browser tự khai. Trong multi-OP login, chọn đúng issuer/registration từ **authenticated context đã được RP verify**, không phải email domain hay raw `iss` chưa xác minh.

### 10.4. ID token leakage qua GET URL

RP-Initiated Logout có thể dùng `id_token_hint` trong GET query. ID token không phải AT cho API, nhưng vẫn là **credential-like authentication assertion chứa claims nhạy cảm**. Nó có thể xuất hiện trong:

- Reverse proxy/access logs, CDN, WAF hoặc APM tracing.
- Browser history, copied URLs, diagnostics screenshots.
- Referer khi OP logout page tải tài nguyên bên thứ ba nếu không có chính sách phù hợp.
- Crash/support dumps và telemetry.

Phòng vệ:

- Bắt buộc HTTPS; không gửi tới redirect host lạ.
- Redact `id_token_hint` và query params nhạy cảm ở proxies/gateways/logs.
- Áp `Referrer-Policy: no-referrer` hoặc chính sách tương đương tại trang phù hợp.
- Chỉ dùng `post_logout_redirect_uri` đã đăng ký và giới hạn third-party resources trên logout pages.
- Nếu OP hỗ trợ và threat model yêu cầu, cân nhắc POST RP-Initiated Logout Request để giảm rủi ro query URL; **không mặc định mọi OP hỗ trợ POST**.
- Giữ ID token trong protected RP server context/BFF thay vì in ra debug console.

### 10.5. Session confusion khi nhiều OP

Alice login `sales-dashboard` qua OP-A, Bob login qua OP-B trên một browser/tab khác. Nếu logout code dùng một URL OP global cố định rồi gắn ID token của OP-B, ứng dụng có thể gửi assertion đến sai provider và logout sai/không logout.

**Phòng vệ:** Mỗi authenticated RP session phải gắn **issuer, client registration, verified ID token và OP logout endpoint**, không suy từ một biến global `lastProvider`. Với nhiều tabs/users, không dùng `lastIdToken` chung cho mọi session.

### 10.6. State callback replay/mix-up

Attacker đoán hoặc lấy state logout cũ rồi gọi `/signed-out?state=...`, khiến RP nhầm rằng OP logout request gần đây đã hoàn tất. Nếu RP tự tạo login session dựa trên callback, còn nguy hiểm hơn.

**Phòng vệ:** State ngẫu nhiên, ngắn hạn, một lần, ràng buộc browser/transaction/issuer; kiểm tra exact; callback logout **không tạo authentication**. Nếu chưa lưu state hoặc đã expired, trang có thể thông báo chưa thể xác minh redirect, nhưng không tái kích hoạt RP session.

### 10.7. Browser logout chưa đồng nghĩa token invalidation

Attacker lấy bearer AT trước khi user logout. RP và OP xóa cookies, nhưng attacker replay AT tới RS. Nếu API chỉ verify JWT offline, AT có thể vẫn hợp lệ tới `exp`.

**Phòng vệ:** Thu hồi RT/grant, đo AT revocation SLA, dùng introspection/denylist/state checks hoặc TTL phù hợp; RS kiểm issuer/audience/scope/ACL, cân nhắc sender-constrained tokens khi cần.

### 10.8. Back-channel logout giả mạo

RP nhận HTTP POST chứa `sid` rồi invalidates session mà không xác minh Logout Token. Attacker có thể gửi forged notifications để logout hàng loạt người dùng.

**Phòng vệ:** Xác minh OIDC Back-Channel Logout Token **signature, issuer, audience, event, `jti` replay, `sid`/`sub`** và điều kiện thời gian; không coi raw `sid`/`sub` header là sự thật.

### 10.9. Đa tài khoản tại OP

OP có thể hỗ trợ nhiều user accounts trong browser. RP không nên cố logout “tất cả accounts” chỉ vì RP biết một `sub`. `id_token_hint` và OP policy giúp xác định phiên thích hợp; OP có thể yêu cầu user confirmation. Việc người dùng chọn Logout từ một RP **không** là authorization để xóa các tài khoản hay khóa các thiết bị khác.

### 10.10. Logout request và race với refresh token

Nếu RP xóa session trong khi background worker đang dùng RT để refresh:

~~~text
T0: User clicks Logout.
T1: Background refresh begins with RT-1.
T2: RP removes authorized-client record and revokes RT-1.
T3: AS accepts refresh and issues RT-2 (race).
T4: Worker saves RT-2 into store after cleanup.
~~~

Một phiên mới/RT mới có thể bị **hồi sinh** sau logout nếu không có coordination. Phòng vệ:

1. Đánh dấu phiên/grant **LOGGING_OUT/REVOKED** ở server store.
2. Ngừng phát sinh refresh jobs mới và fence workers bằng session/grant generation.
3. Revoke token family/grant theo AS policy (nếu hỗ trợ).
4. Không cho worker ghi RT-2 khi session generation đã bị logout.
5. Có cleanup/reconciliation khi token endpoint/network outcome không rõ.

Đây là vấn đề **OAuth token lifecycle/concurrency**, không phải lỗi riêng của `end_session_endpoint`. RP logout và OP logout chỉ là hai bước trong thiết kế đầy đủ.

## 11. Spring Security: OIDC login và `OidcClientInitiatedLogoutSuccessHandler`

Spring Security cung cấp **`OidcClientInitiatedLogoutSuccessHandler`** để hỗ trợ RP-Initiated Logout cho ứng dụng servlet đã dùng `oauth2Login()` với OIDC. Handler dựa trên **ClientRegistration/ProviderDetails** và authenticated `OidcUser` để xây request tới OP logout endpoint theo khả năng provider.

### 11.1. Cấu hình OAuth2/OIDC client

~~~yaml
spring:
  security:
    oauth2:
      client:
        provider:
          company-op:
            issuer-uri: https://auth.example.test
        registration:
          sales-dashboard:
            provider: company-op
            client-id: sales-dashboard
            client-secret: INJECT_FROM_SECRET_MANAGER
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
~~~

`INJECT_FROM_SECRET_MANAGER` là placeholder; secret thật phải được inject từ kho bảo mật. Ví dụ là **confidential backend**; với SPA/native public client, không hardcode static client secret và phải sử dụng Authorization Code + PKCE theo loại client.

RP-Initiated Logout chỉ có ngữ cảnh OIDC khi login đã nhận **ID token** và provider hỗ trợ `end_session_endpoint`. Nếu client chỉ có OAuth AT nhưng không có `openid`/ID token, đừng giả định OIDC handler sẽ tự biết session cần logout tại OP.

### 11.2. Bean logout success handler

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.oidc.web.logout.OidcClientInitiatedLogoutSuccessHandler;
import org.springframework.security.web.authentication.logout.LogoutSuccessHandler;

@Bean
LogoutSuccessHandler oidcLogoutSuccessHandler(
        ClientRegistrationRepository registrations) {

    OidcClientInitiatedLogoutSuccessHandler handler =
            new OidcClientInitiatedLogoutSuccessHandler(registrations);

    handler.setPostLogoutRedirectUri("{baseUrl}/signed-out");
    return handler;
}
~~~

Handler trong các phiên bản Spring Security được hỗ trợ biết cách lấy OIDC authentication context và tạo OP logout request. **Kiểm tra version cụ thể** vì endpoint discovery, ID token hint, state handling và fallback behavior có thể khác giữa các phiên bản; đừng tự khẳng định một version tự tạo/kiểm tra mọi logout transaction state nếu chưa test.

### 11.3. SecurityFilterChain bảo vệ local logout

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.logout.LogoutSuccessHandler;

@Configuration
class OidcWebSecurityConfiguration {

    @Bean
    SecurityFilterChain webChain(
            HttpSecurity http,
            LogoutSuccessHandler oidcLogoutSuccessHandler)
            throws Exception {

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/signed-out", "/public/**").permitAll()
                .anyRequest().authenticated());

        http.oauth2Login(Customizer.withDefaults());

        // Keep CSRF enabled for browser cookie-based sessions;
        // Spring defaults to POST /logout when CSRF is enabled.
        http.csrf(Customizer.withDefaults());

        http.logout(logout -> logout
                .logoutUrl("/logout")
                .invalidateHttpSession(true)
                .clearAuthentication(true)
                .deleteCookies("JSESSIONID")
                .logoutSuccessHandler(oidcLogoutSuccessHandler));

        return http.build();
    }
}
~~~

**Lưu ý:** Đoạn này là ví dụ Spring Security servlet 6.x, cần wiring/imports theo version. `logoutSuccessHandler` nhận `Authentication` của request logout để lấy OIDC context. Không tự ghi một `LogoutHandler` dọn Authentication **trước khi** handler có thể lấy ID token hint mà không hiểu lifecycle của Spring filters.

`deleteCookies("JSESSIONID")` là một phần cleanup; nếu cookie tên/path/domain khác hoặc session store distributed, còn cần kiểm tra cookie và server-side session invalidation đúng. Đừng dựa chỉ vào xóa cookie phía client.

### 11.4. Logout button sử dụng POST và CSRF

Với Thymeleaf/Spring MVC, ví dụ:

~~~html
<form method="post" th:action="@{/logout}">
    <input type="hidden"
           th:name="${_csrf.parameterName}"
           th:value="${_csrf.token}">
    <button type="submit">Đăng xuất</button>
</form>
~~~

**Đây là Thymeleaf markup minh họa**, cần Spring/Thymeleaf integration làm `_csrf` có mặt trong model/request và render token thật phía server. Một số cấu hình tự chèn hidden field khi dùng `th:action`; nếu vậy không thêm duplicate input. Kiểm tra HTML đã render và CSRF behavior thực tế, tránh hardcode token hoặc cho browser tự tạo giá trị ngẫu nhiên không khớp session.

Nếu dùng frontend fetch/SPA, gửi POST và CSRF token theo chính sách cookie/session của RP; không tắt CSRF toàn cục chỉ để nút Logout bớt cấu hình.

### 11.5. Đăng ký `post_logout_redirect_uri` ở OP

Ngoài redirect URI phục vụ login:

~~~text
https://portal.example.test/login/oauth2/code/sales-dashboard
~~~

cần bảo đảm OP cho phép post-logout URI:

~~~text
https://portal.example.test/signed-out
~~~

Các OP quản lý danh sách này trong client registration với tên thuộc tính tùy provider. `handler.setPostLogoutRedirectUri(...)` **không tự đăng ký URI với OP**. Nếu OP chưa cho phép, nó có thể bỏ redirect hoặc báo lỗi/logout confirmation; không tắt kiểm URI để “fix”.

### 11.6. Trang `/signed-out` là public, không tự đăng nhập lại

~~~java
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
class SignedOutController {
    @GetMapping("/signed-out")
    String signedOutPage() {
        return "signed-out";
    }
}
~~~

Trang này chỉ hiển thị trạng thái local logout. Nếu application yêu cầu manual `state` verification, cần một filter/controller logic bổ sung **trước khi tin callback**; ví dụ trên **không** tự triển khai state verification. Không tạo local authenticated session từ query callback, không dùng HTML page làm bằng chứng RT đã revoked.

### 11.7. Kiểm tra redirect thực tế thay vì chỉ tin cấu hình

Trong integration test cần:

- Đăng nhập thực sự bằng OIDC test OP, nhận verified ID token.
- Gửi **POST /logout** hợp lệ cùng CSRF.
- Kiểm tra local session đã invalidated.
- Kiểm tra HTTP redirect đi tới **registered `end_session_endpoint`**, có đúng ID token hint theo behavior của framework/provider.
- Kiểm tra `post_logout_redirect_uri` đúng allowlist.
- Dùng fake OP để kiểm tra callback/failure/missing endpoint, không chỉ test handler bean tạo thành công.

Một unit test xác nhận `OidcClientInitiatedLogoutSuccessHandler` đã được tạo **không chứng minh** OP session đã chấm dứt. Cần browser/integration test và kiểm tra OP session độc lập.

## 12. Khi cần token revocation: tích hợp nhưng không trộn giao thức

Một BFF có thể yêu cầu cả **RP/OP logout** và **RFC 7009 RT revocation**. Chúng nên là hai **tác vụ phân biệt với kết quả/audit riêng**.

### 12.1. Mô hình logout coordinator

~~~text
POST /logout (CSRF validated)
  ├─ Capture trusted OIDC issuer/client/id_token context.
  ├─ Freeze client token refresh, fence concurrent workers.
  ├─ Invalidate local RP session + cookies immediately.
  ├─ Revoke RT / authorized grant via trusted AS back channel
  │   └─ Record success / unknown-outcome / failure for retry policy.
  ├─ Clear local authorized-client/token store.
  └─ Redirect browser to trusted OP end_session_endpoint
      └─ Optional registered post_logout_redirect_uri return.
~~~

Thứ tự thực thi có thể thay đổi theo kiến trúc để tránh giữ request quá lâu khi AS outage, nhưng các **bất biến** cần bảo đảm:

1. Local session không còn hợp lệ sau user logout.
2. Không còn background refresh job có thể **ghi RT mới** trở lại session đã logout.
3. Revocation/reconciliation không bị bỏ qua vì browser đóng tab.
4. OP redirect không nhận RT/client secret và không phải nơi chờ revoke.
5. Kết quả OP logout được trình bày trung thực; không khẳng định thành công khi không có bằng chứng.

### 12.2. RFC 7009 back-channel request Java

~~~java
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

public final class RefreshTokenRevoker {
    private final URI endpoint = URI.create(
            "https://auth.example.test/oauth2/revoke");
    private final HttpClient http = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(3))
            .followRedirects(HttpClient.Redirect.NEVER)
            .build();

    public int revoke(
            String refreshToken,
            String registeredClientAuthHeader) throws Exception {
        String form = "token=" + URLEncoder.encode(
                refreshToken, StandardCharsets.UTF_8)
                + "&token_type_hint=refresh_token";

        HttpRequest request = HttpRequest.newBuilder(endpoint)
                .header("Content-Type",
                        "application/x-www-form-urlencoded")
                .header("Authorization",
                        registeredClientAuthHeader)
                .timeout(Duration.ofSeconds(7))
                .POST(HttpRequest.BodyPublishers.ofString(form))
                .build();

        HttpResponse<Void> response = http.send(
                request, HttpResponse.BodyHandlers.discarding());
        return response.statusCode();
    }
}
~~~

**Giới hạn của snippet:** `registeredClientAuthHeader` phải đến từ một **credential provider an toàn** đã gắn với client registration, không lấy từ browser input. Không log header/token, không tự follow HTTP redirect, và phải kiểm TLS/hostname. Phải xử lý HTTP 200 (kể cả invalid token theo RFC), HTTP 401/429/5xx, network timeout **unknown outcome**, retry/backoff/reconciliation và per-grant policy. Đoạn này là **một revocation client minh họa**, không phải production coordinator.

### 12.3. Timeout khi revoke

Tình huống:

~~~text
RP sends POST /revoke RT-1.
AS commits revocation.
Network drops response.
RP sees timeout: status UNKNOWN.
~~~

Không khôi phục local session vì AS response mất; không tuyên bố “RT đã revoke thành công” nếu không biết. Retry có giới hạn theo RFC/AS contract có thể an toàn, nhưng cần idempotent semantics và tránh lộ token/race. Nếu token family có rotation, phải ngăn worker cấp RT mới trong lúc cleanup.

### 12.4. Single-device logout vs logout-all

Nếu Alice có laptop, TV và điện thoại:

- **Logout laptop RP** có thể chỉ revoke session/RT grant của laptop nếu AS cho phép phân biệt.
- **Logout mọi thiết bị** có thể cần AS revoke toàn bộ user grants/sessions và yêu cầu các RPs invalidation; đây là quyền quản trị/rủi ro khác.
- RP-Initiated Logout ở browser laptop **không tự** biết session trên TV/phone.

Không dùng chung `sub` để revoke ngẫu nhiên mọi người dùng có cùng email hoặc mọi session của một tenant. Scope của logout phải được xác định bằng authenticated user/client/device/grant identifiers đáng tin.

## 13. Tự quản lý logout transaction khi cần callback `state`

Framework có thể xây OP logout request giúp RP. Tuy nhiên, nếu sản phẩm yêu cầu **chứng minh callback thuộc đúng lượt logout**, cần thiết kế một **transaction store ngắn hạn** độc lập với session RP vừa bị hủy.

### 13.1. Dữ liệu tối thiểu

~~~json
{
  "transaction_id": "ltx-example-582",
  "state_digest": "<protected-digest-of-random-state>",
  "issuer": "https://auth.example.test",
  "client_registration_id": "sales-dashboard",
  "expected_post_logout_redirect_uri": "https://portal.example.test/signed-out",
  "browser_binding_digest": "<protected-browser-binding>",
  "created_at": "2026-11-23T02:30:00Z",
  "expires_at": "2026-11-23T02:35:00Z",
  "consumed_at": null
}
~~~

Đây là **application-specific data model**, không phải JSON của chuẩn OIDC. Nó cho phép RP kiểm tra state sau khi local session đã invalidated, không cần giữ session đăng nhập còn sống. Trong production:

- Dùng random state đủ entropy; tránh email, `sub`, timestamp hoặc ID tăng dần.
- Hạn dùng **ngắn và một lần**; có cleanup và bounded storage.
- Gắn state với browser/request context bằng cookie/secure flow phù hợp. Không tạo **session login** mới từ state.
- Nếu lưu hash/HMAC state, thực hiện compare an toàn và tránh token leak trong logs.
- Không lưu raw ID token/refresh token chỉ để state verification; các credential này có vòng đời riêng.

### 13.2. Tạo state ngẫu nhiên bằng Java 17

~~~java
import java.security.SecureRandom;
import java.util.Base64;

public final class LogoutStateFactory {
    private static final SecureRandom RNG = new SecureRandom();

    public static String generate() {
        byte[] bytes = new byte[32]; // 256-bit random state
        RNG.nextBytes(bytes);
        return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(bytes);
    }
}
~~~

`state` này chỉ là **correlation secret**, không dùng như JWT signing key, CSRF token chung cho mọi session, access token hoặc refresh token. Cần bảo vệ session/transaction binding riêng. 32 bytes từ CSPRNG là ví dụ đủ mạnh, **không phải độ dài bắt buộc duy nhất của OIDC spec**.

### 13.3. Bất biến khi xử lý callback

~~~text
on GET /signed-out?state=received:
    require received state is nonblank and within accepted length
    locate short-lived logout transaction by protected state lookup
    require transaction not expired and not previously consumed
    require expected issuer/client/redirect/browser binding if applicable
    atomically mark state consumed
    serve public signed-out page
    NEVER establish a new authenticated RP session
~~~

Nếu callback thiếu state dù RP đã gửi state, không được đánh dấu `OP_LOGOUT_CONFIRMED` theo transaction. Nếu sản phẩm cho phép trang public `/signed-out` truy cập trực tiếp, có thể hiển thị thông báo chung “Bạn chưa đăng nhập tại ứng dụng” nhưng không dùng nó làm xác nhận OP logout.

### 13.4. State matching không chứng minh token revocation

Kể cả callback từ trusted OP mang đúng state, RP mới biết **browser quay về theo flow**. Muốn chứng minh RT revoke, cần kết quả revocation; muốn chứng minh AT inactive, phải kiểm tra token-status policy; muốn chứng minh mọi RP sessions đã hủy, cần notification/acknowledgement hoặc kiểm tra độc lập tại các RPs.

### 13.5. Cần cẩn thận với cross-site cookies

Nếu RP dùng cookie để bind logout transaction:

- Cookie `Secure`, `HttpOnly` khi thích hợp và `SameSite` phải phù hợp top-level redirect từ OP về RP.
- `SameSite=Strict` có thể làm cookie không được gửi ở cross-site callback, tùy browser behavior; `SameSite=Lax` thường phù hợp GET top-level navigation, nhưng threat model/CSRF phải đánh giá riêng.
- Cookie path/domain phải đủ hẹp; khi xóa cần dùng thuộc tính tương ứng.
- Không gửi logout state cookie tới OP nếu không cần; browser chỉ gửi tới đúng domain RP.

Browser privacy controls và cross-site handling thay đổi theo nền tảng. Không tự dựa vào cookie cross-site như phương tiện thông báo logout cho mọi RPs.

## 14. Tương thích OP và các trường hợp không có `id_token_hint`

### 14.1. `end_session_endpoint` không được công bố

Không phải mọi OAuth Authorization Server đều là một OP hỗ trợ RP-Initiated Logout. Ngay cả khi OP hỗ trợ OIDC login, nó có thể **không công bố/triển khai logout endpoint** tương ứng trong metadata.

RP cần:

1. Kiểm tra **provider metadata đã xác minh** và client registration.
2. Nếu không có endpoint, thực hiện **local logout**; nếu product cần OP SSO logout, nêu rõ hạn chế.
3. Chỉ dùng provider-specific logout URL nếu URL và contract đã được **quản trị phê duyệt**, không tự suy.
4. Không gửi ID token sang `authorization_endpoint` hay URL login chỉ để “buộc OP logout”.

### 14.2. ID token hint không còn có sẵn

Một số RP chỉ lưu session principal/claims mà không giữ ID token sau login. Khi logout, handler có thể không tạo được `id_token_hint` theo behavior framework.

Các lựa chọn tùy OP:

- Giữ **ID token đã được xác minh** đủ cho RP logout trong server-side authenticated context, không đặt trong client-side logs.
- Cung cấp `client_id` và/hoặc `logout_hint` theo contract OP.
- Chấp nhận OP yêu cầu user confirmation nếu không có đủ session context.
- Chỉ làm local logout nếu OP logout không thể thực hiện an toàn.

**Không chế ra một JWT `id_token_hint`** bằng khóa của RP; OP cần ID token do chính OP phát theo OIDC. Một email/`sub` tự khai cũng không thay ID token hint.

### 14.3. ID token hết hạn

Một ID token đã hết hạn **không dùng được làm bằng chứng authentication mới** ở RP. Tuy nhiên OP có thể vẫn sử dụng nó như **logout hint** để nhận diện phiên đã được phát hành trước đó theo OP policy. Hành vi chấp nhận từ chối tùy OP/contract; không sửa verifier để chấp nhận expired ID token như login credential.

Trong test, kiểm tra rõ hai nhánh: OP nhận expired hint và OP từ chối/đòi xác nhận; RP đều phải giữ **local logout đã thực hiện**, không restore session.

### 14.4. Thiếu hoặc sai `post_logout_redirect_uri`

Nếu RP không gửi `post_logout_redirect_uri`, OP có thể hiển thị trang đã logout của chính OP, không redirect về RP. Nếu URI không thuộc registration, OP phải từ chối sử dụng URI đó theo spec/policy; hành vi báo lỗi/confirmation có thể khác.

Đừng biến lỗi “OP không redirect” thành lý do mở wildcard/loose URI matching. Sửa client registration hoặc URI cấu hình chính xác.

### 14.5. Nhiều OP providers trong cùng một RP

Với Spring multi-client:

~~~text
client registration company-op:
  issuer = https://auth.company.example.test
  end_session_endpoint = https://auth.company.example.test/logout

client registration partner-op:
  issuer = https://login.partner.example.test
  end_session_endpoint = https://login.partner.example.test/logout
~~~

RP phải dùng registration gắn với authenticated user/session khi logout. Không dùng provider đầu tiên của repository hoặc hostname suy từ user email. Phải kiểm tra **ID token issuer và client audience** trước khi định tuyến hint.

### 14.6. OP không chủ động thu hồi mọi AT/RT

Một số nhà cung cấp kết hợp OP session logout với refresh-token revocation hoặc server-side token invalidation; một số không. Đây là **provider behavior** phải được kiểm chứng bằng integration tests. Đừng mặc định rằng callback `/signed-out` hàm ý AS đã revoke RT, hay rằng OP logout failure làm API AT không dùng được.

## 15. Xử lý vận hành và bảo đảm an toàn khi lỗi mạng

### 15.1. Một mô hình trạng thái có thể kiểm toán

Ghi nhận riêng:

~~~text
rp_session_status          = INVALIDATED
op_logout_request_status   = REDIRECT_SENT / CALLBACK_OBSERVED / UNKNOWN
refresh_revocation_status  = SUCCESS / FAILURE / UNKNOWN
active_token_status        = POLICY_DEPENDENT
other_rp_session_status    = NOT_VERIFIED / NOTIFIED / VERIFIED_CLOSED
~~~

Các trạng thái này là **application audit model**, không phải giao thức bắt buộc. Không đánh đồng `CALLBACK_OBSERVED` với “mọi session/token bị thu hồi”.

### 15.2. OP outage

Nếu OP trả 502 khi browser đi đến `end_session_endpoint`:

- RP local session vẫn phải invalidated.
- Trang lỗi rõ ràng, không in `id_token_hint`.
- Có thể hướng dẫn user đóng browser hoặc thử lại OP logout với flow thích hợp.
- Nếu OP vẫn có SSO cookie, lần login sau có thể tự xác thực; cần thông báo trung thực.
- Nếu bảo mật yêu cầu disable/remote logout, cần back-channel/revocation/AS controls **không phụ thuộc** vào browser hoàn tất redirect.

### 15.3. Race logout và request API

Một request `POST /orders` có thể đang xử lý khi Alice bấm Logout. Việc hủy RP session không tự hủy request đã được RS xác thực trước đó. Nếu nghiệp vụ yêu cầu bảo đảm “không thao tác sau thời điểm logout”, cần thiết kế:

- Transaction/authorization boundary khi commit action.
- User/session state checks theo SLA và ordering rõ.
- Idempotency/audit các hành động đã commit trước hoặc đồng thời logout.
- Không khẳng định logout rollback các giao dịch nghiệp vụ đang thực hiện.

### 15.4. Cluster RP và distributed session store

Nếu RP có nhiều Pods, logout tại Pod-A phải khiến Pod-B từ chối cùng session identifier. Chỉ xóa cookie trên browser không đủ nếu Pod-B còn session state. Có thể dùng shared session store, distributed invalidation, token generation fencing hoặc session-version checks. Test điều này trên **hai instance thật**.

### 15.5. Metrics có ý nghĩa

| Metric minh họa | Ý nghĩa |
| --- | --- |
| `rp_logout_started_total` | Số lần user gửi POST /logout hợp lệ |
| `rp_session_invalidated_total` | Tần suất local session thực sự bị hủy |
| `op_logout_redirect_sent_total` | RP đã tạo redirect tới OP logout |
| `op_logout_callback_observed_total` | Browser quay lại RP theo callback |
| `op_logout_callback_state_invalid_total` | Sai/expired/replayed state |
| `op_logout_endpoint_unavailable_total` | Metadata thiếu hoặc lỗi OP logout |
| `refresh_token_revocation_total` theo outcome | RT/grant revoke success/fail/unknown |
| `backchannel_logout_token_rejected_total` | Notification không hợp lệ hoặc replay |
| `session_reuse_after_logout_total` | Session ID cũ bị thử dùng lại |
| `at_accepted_after_logout_seconds` | Đo cửa sổ AT có thể tiếp tục được RS chấp nhận |

Tên metric là **ví dụ**, không phải thuộc tính chuẩn của Spring/OIDC. Không đưa raw ID token, RT, bearer AT, client secret, email hoặc `sub` cá nhân vào metric labels có cardinality quá cao.

### 15.6. Sự cố OP SSO logout không có callback

Không tự động retry hàng trăm browser redirects hoặc chuyển sang site khác được hardcode ngoài trust config. Retry nếu có cần được user khởi xướng/điều phối an toàn; state/logout transaction phải mới hoặc còn hợp lệ theo policy. Backend không nên tự “mô phỏng browser cookie” của OP, vì cookie SSO thuộc browser/OP boundary và không thể được thu hồi một cách hợp lệ bằng request server-to-server tùy tiện.

## 16. Ma trận kiểm thử RP-initiated logout (60 ca)

Thiết lập một **OP test hỗ trợ RP-Initiated Logout**, hai RPs đăng ký riêng, một RS `orders-api` và test token/RT store. Tạo hai browser sessions độc lập, giả lập nhiều tabs/Pod, mạng timeout, redirect refusal, client registration mismatch và một OP test hỗ trợ Back-Channel Logout khi kiểm thử single logout. Tất cả ID token/AT/RT đều là **credential test**; không dùng token production.

| ID | Trường hợp | Kết quả mong đợi |
| --- | --- | --- |
| L01 | Alice authenticated, gửi POST `/logout` cùng CSRF hợp lệ | RP invalidates local session, bắt đầu OP logout request đúng provider |
| L02 | Browser truy cập `GET /logout` khi RP cấu hình POST+CSRF | Không tự hủy session bằng GET không được phép |
| L03 | Cross-site POST thiếu/sai CSRF token | Request bị từ chối, không thay đổi state trái phép |
| L04 | Xóa browser cookie rồi dùng lại session ID cũ qua client khác | Server-side session đã invalid, từ chối |
| L05 | Xóa cookie sai path/domain, cookie thật còn | Test phát hiện lỗi cleanup, sửa cookie attributes |
| L06 | Logout handler không có OIDC authentication/ID token | Local logout vẫn an toàn; xử lý OP logout theo contract, không giả ID token |
| L07 | Issuer/discovery đúng, metadata có `end_session_endpoint` | RP dùng endpoint đúng đã được trust |
| L08 | Request chứa `logoutEndpoint=https://attacker.example.test` | Không override OP URL từ untrusted input |
| L09 | Discovery metadata `issuer` khác configured issuer | RP không tin metadata hoặc endpoint của issuer khác |
| L10 | OP không công bố `end_session_endpoint` | RP chỉ local logout hoặc dùng approved fallback; không tự đoán URL |
| L11 | `id_token_hint` là verified ID token của đúng RP/issuer | OP có ngữ cảnh để áp logout policy |
| L12 | `id_token_hint` là ID token của RP/issuer khác | Không logout/redirect dựa trên hint sai binding |
| L13 | `id_token_hint` đã hết hạn | OP xử lý theo policy, có thể confirmation; RP không coi là login token mới |
| L14 | Client gửi bearer AT/RT thay `id_token_hint` | Không chấp nhận như ID token theo OIDC contract |
| L15 | Không có hint nhưng có registered `client_id` | OP chỉ xử lý khi đủ trusted context/policy, có thể yêu cầu confirmation |
| L16 | Chỉ có client_id public và attacker-controlled redirect | OP không redirect tới URI chưa đăng ký |
| L17 | `post_logout_redirect_uri` đúng registration | OP có thể redirect về URI này theo policy |
| L18 | `post_logout_redirect_uri` không nằm trong registration | OP không chuyển browser tới URI đó |
| L19 | Wildcard path/subdomain hoặc open redirect URI | Bị từ chối theo strict policy |
| L20 | URI double-encoded hoặc có `%2f%2f` để lách allowlist | OP/RP không bị bypass matching |
| L21 | RP nhận `returnTo` full URL của attacker | Không đưa nguyên xi vào logout redirect |
| L22 | OP callback trả đúng `state` của transaction còn hạn | RP xác nhận correlation, consume state một lần |
| L23 | OP callback trả `state` khác | Không đánh dấu đúng logout transaction |
| L24 | OP callback trả state đã hết TTL | Từ chối dùng như callback hợp lệ |
| L25 | Callback state được dùng lại lần hai | Không replay được |
| L26 | RP xóa session chứa state trước khi OP redirect | State vẫn kiểm được qua protected logout transaction store/cookie thiết kế đúng |
| L27 | Public `/signed-out` được mở trực tiếp | Không tạo lại authenticated RP session |
| L28 | OP logout nhưng không redirect callback | RP local session vẫn invalid; OP completion status không đoán |
| L29 | OP yêu cầu user xác nhận logout | RP không tự tin silent logout luôn thành công |
| L30 | OP trả 5xx/timeout | Local logout giữ nguyên, xử lý trạng thái OP UNKNOWN |
| L31 | Browser đóng tab trước khi theo 302 | RP session đã hủy; OP session có thể còn |
| L32 | OP từ chối logout request do hint/URI sai | RP không restore local session hoặc RT |
| L33 | Hai tabs cùng RP session, tab A logout | Tab B không thể dùng session cũ gọi backend API |
| L34 | Laptop logout trong khi điện thoại còn phiên khác | Không tự xóa session điện thoại nếu không có global-logout policy |
| L35 | RP-A logout OP, RP-B local session còn | Test thể hiện giới hạn nếu không có logout notification |
| L36 | OP gửi Back-Channel Logout Token ký đúng issuer/audience/event | RP-B xác minh và invalidate session đã map |
| L37 | Attacker gửi `sid`/`sub` raw không có Logout Token hợp lệ | RP không logout theo forged request |
| L38 | Back-Channel Logout Token `jti` bị replay | RP nhận diện replay và không tái xử lý nguy hiểm |
| L39 | Back-Channel Logout Token `iss`/`aud` sai | RP từ chối |
| L40 | Logout Token `sid` không khớp local session mapping | Không xóa ngẫu nhiên session user khác |
| L41 | Browser chặn third-party cookie ở Front-Channel Logout | Test bộc lộ giới hạn delivery, không báo single logout bảo đảm |
| L42 | OP logout thành công nhưng upstream federated IdP còn SSO | RP không khẳng định upstream logout; login lại có thể silent |
| L43 | OP logout xong nhưng RT tại AS vẫn còn theo provider contract | Không suy OP logout = RT revoked |
| L44 | RP gọi RFC 7009 revoke RT đúng client/grant | AS chặn refresh mới theo policy |
| L45 | RFC 7009 request timeout sau AS commit | Outcome UNKNOWN; local logout vẫn hoàn tất, recovery có giới hạn |
| L46 | Background worker refresh RT đồng thời logout | Không được lưu RT mới vào session/grant đã logout |
| L47 | JWT AT đã cấp còn `exp`, RS chỉ validate offline | Test ghi nhận AT có thể còn được chấp nhận tới TTL |
| L48 | RS có denylist/session-state check và grant revoked | RS từ chối trong revocation SLA |
| L49 | Opaque AT introspection trả `active=false` sau revoke | RS từ chối khi cache freshness cho phép quan sát |
| L50 | `id_token_hint` xuất hiện trong proxy/access logs | Redaction test phát hiện và sửa |
| L51 | OP logout page tải third-party resource kèm Referer nhạy cảm | Privacy/referrer test phát hiện leakage và ngăn |
| L52 | Logout URL quá dài do ID token hoặc query abuse | RP/OP xử lý an toàn theo size limits; không log token raw |
| L53 | `client_id` không khớp `id_token_hint` audience | OP không coi request là RP context hợp lệ |
| L54 | Một RP hỗ trợ OP-A và OP-B; Alice login OP-B | Logout phải đến đúng OP-B theo verified registration |
| L55 | Cookie `SameSite=Strict` làm logout callback binding cookie không gửi | Integration test phát hiện; chọn cookie/transaction strategy phù hợp |
| L56 | User gửi logout hai lần song song | Local cleanup idempotent; không phát OP redirect/token leak trái policy |
| L57 | API request đã bắt đầu trước khi logout commit | Transaction/domain policy xác định ordering, không giả logout rollback tự động |
| L58 | User rút consent nhưng không logout OP | Test phân biệt consent withdrawal với OP SSO session |
| L59 | RP logout nhưng OP cookie còn; login lại | Có thể silent SSO; ứng dụng thông báo đúng OP logout chưa đạt |
| L60 | Admin yêu cầu logout mọi sessions trên các RPs/devices | Chỉ công bố thành công khi AS/RP notification và revocation policy thực sự đáp ứng |

### 16.1. Test phải chứng minh đúng nguyên nhân

Để kiểm tra post-logout redirect validation:

~~~text
Test dương:
  OP session hợp lệ, id_token_hint của đúng RP.
  post_logout_redirect_uri thuộc registration.
  → OP cho phép logout redirect theo policy.

Test âm:
  Cùng OP session, RP, hint và state.
  Chỉ thay redirect_uri bằng attacker-owned URL.
  → OP không redirect tới attacker.
~~~

Nếu cả hai đều thất bại vì OP không reachable hoặc ID token sai issuer, test **chưa chứng minh** redirect allowlist bảo vệ đúng.

### 16.2. Test local session khác test OP SSO session

~~~text
Step A: Login tại OP và tạo session RP.
Step B: POST /logout, assert RP session ID cũ không dùng lại được.
Step C: Browser theo OP end_session_endpoint.
Step D: Kiểm tra OP session độc lập với RP session.
Step E: Mở RP mới cùng OP để quan sát SSO behavior.
~~~

Không dùng chỉ `GET /signed-out` trả HTTP 200 làm bằng chứng OP SSO đã logout. Một callback public có thể 200 cả khi OP chưa hề được browser truy cập.

### 16.3. Test state với fake clock và replay

~~~text
T0:
    state-X random, stored in short-lived transaction store.
    RP local session invalidated.
T0+10s:
    OP callback state-X accepted; mark consumed.
T0+11s:
    Replay state-X -> rejected as stale/consumed.
T0+6min:
    Another state-Y was never used -> expired and rejected.
~~~

Nếu application yêu cầu state binding với browser cookie, test trình duyệt thật với cross-site OP redirect và `SameSite` attributes; unit test thuần state comparison không phát hiện cookie missing sau redirect.

### 16.4. Kiểm thử browser crash / network partition

~~~text
Case 1:
  RP commits local logout.
  Browser never reaches OP.
  → RP invalidated, OP status UNKNOWN, possible SSO reuse.

Case 2:
  OP ends SSO session.
  Browser never reaches RP callback.
  → RP invalidated; callback not observed, do not restore session.

Case 3:
  OP returns after delay/confirmation.
  Callback state still valid within TTL.
  → RP accepts once and shows signed-out page.
~~~

Thiết kế không phụ thuộc vào việc một web browser sẽ **luôn** đi hết chuỗi redirects. Nếu cần compliance logout toàn hệ thống, phải có state/notification và kiểm tra độc lập.

### 16.5. Test refresh race bằng barrier

Điều khiển hai workers:

~~~text
Worker Refresh:
    read RT-1 + generation=5
    wait at barrier

Worker Logout:
    mark session generation=6 / LOGGED_OUT
    revoke grant/RT family as policy permits
    clear token store

Release Refresh:
    even if AS returns RT-2,
    CAS "session generation must still be 5" must fail
    RT-2 must not revive local session
~~~

Đây là test **token lifecycle** liên quan logout, không phải test của OP `end_session_endpoint`. Kiểm tra trên shared token store/distributed sessions nếu production chạy nhiều Pods, không chỉ trên một thread-local test.

## 17. Năm tình huống thực tế và cách xử lý

### Tình huống A: Alice logout portal nhưng login lại không cần mật khẩu

**Bối cảnh:** Alice đăng nhập `employee-portal` bằng OIDC. Developer tạo nút Logout chỉ xóa `JSESSIONID` và redirect về trang chủ. Khi Alice bấm Login lần nữa, OP vẫn có SSO cookie nên trả authorization code mà không hiển thị form mật khẩu.

**Nguyên nhân:** Chỉ có **RP local logout**, chưa yêu cầu OP kết thúc SSO session. Không phải OP “bỏ qua bảo mật”; một SSO session còn hợp lệ được phép hỗ trợ đăng nhập tiếp theo theo policy.

**Giải pháp:** Nếu yêu cầu là logout khỏi OP, dùng **RP-Initiated Logout** đến trusted `end_session_endpoint`, đưa `id_token_hint` khi phù hợp và registered `post_logout_redirect_uri`. Kiểm tra OP logout bằng browser/integration test; vẫn đảm bảo local session invalid ngay. Nếu product chỉ cần logout ứng dụng, nói rõ điều đó trên UX.

### Tình huống B: Sau logout, trình duyệt chuyển tới trang phishing

**Bối cảnh:** Ứng dụng nhận `returnTo` và dùng luôn làm `post_logout_redirect_uri`. Attacker gửi link với `returnTo=https://attacker.example.test/login`. Sau logout, Alice nhìn thấy trang login giả.

**Nguyên nhân:** **Open redirect/trust boundary error** ở RP/OP. URL dùng để tiếp tục flow không được giới hạn theo registered logout redirect URIs.

**Giải pháp:** RP chọn post-logout URI từ cấu hình, OP đăng ký và kiểm tra exact URI, không chấp nhận arbitrary URL hay wildcard. Nếu ứng dụng cần điều hướng nội bộ sau logout, chỉ chấp nhận relative paths theo allowlist. Áp integration test cho URL encoding/double encoding và subdomain takeover.

### Tình huống C: Mọi app đã “logout” nhưng nhân viên vẫn truy cập API

**Bối cảnh:** RP-A gửi RP-Initiated Logout, OP kết thúc SSO và Back-Channel Logout thông báo cho các RPs. Nhưng một JWT AT của Alice đã bị attacker sao chép trước đó còn hạn 12 phút. `orders-api` chỉ verify chữ ký/JWKS.

**Nguyên nhân:** OP/RP session logout **không tự revoke** một JWT AT đã phát hành. Logout Token gửi cho RP khác cũng không phải JWT AT denylist của RS.

**Giải pháp:** Xác định SLA: cần revoke RT/grant và đánh giá AT denylist/state check/introspection hoặc TTL ngắn. RS kiểm token purpose, issuer, audience, expiry, scope và domain ACL. Không tuyên bố “đã đăng xuất an toàn khỏi mọi API” nếu attacker vẫn có thể replay AT.

### Tình huống D: Spring handler không redirect tới OP sau khi logout

**Bối cảnh:** Backend cấu hình `OidcClientInitiatedLogoutSuccessHandler` nhưng user đăng nhập bằng OAuth2 authorization flow **không có `openid`**, hoặc provider metadata không có `end_session_endpoint`. Kết quả chỉ là local logout/fallback URL.

**Nguyên nhân:** Handler cần ngữ cảnh **OIDC authentication** và thông tin OP logout; không thể suy OP session chỉ từ OAuth AT hoặc `client_id`.

**Giải pháp:** Kiểm tra client registration có OIDC scope `openid`, RP thực sự nhận/verify ID token, metadata issuer đúng và OP hỗ trợ RP-Initiated Logout. Kiểm tra HTTP redirect thật bằng browser test, không chỉ bean tồn tại. Không hardcode URL của OP không tin cậy.

### Tình huống E: Logout thành công nhưng RT mới xuất hiện trở lại

**Bối cảnh:** User bấm Logout ở BFF. Đồng thời scheduled task refresh RT cho session đó. Backend xóa RT cũ nhưng task nhận RT mới và ghi lại vào token store sau khi cleanup. Lần sau session có thể phát sinh AT dù user đã logout.

**Nguyên nhân:** **Refresh/logout race condition**, không phải OP không xóa SSO cookie.

**Giải pháp:** Đánh dấu session/grant `LOGGING_OUT` trước khi cleanup, khóa/fence writers theo generation, ngăn refresh mới, revoke family/grant theo AS policy, CAS khi ghi token. Audit và reconciliation khi AS request timeout; bảo vệ cả trên multi-instance store.

## 18. Checklist triển khai RP-initiated logout trong production

### 18.1. Điều kiện nền tảng

1. **Đúng bài toán:** Product cần logout **chỉ RP**, logout **OP SSO**, logout **mọi RP sessions** hay revoke **mọi AT/RT**? Đã định nghĩa riêng từng yêu cầu?
2. **OIDC registration:** RP đang dùng OIDC `openid`, có verified ID token trong authenticated context khi cần?
3. **Trusted issuer:** OP issuer, discovery, JWKS và `end_session_endpoint` đến từ cấu hình/metadata được phê duyệt?
4. **TLS:** Certificate/hostname validation đúng; không trust-all hoặc chuyển credential sang host lạ?
5. **Metadata missing:** Nếu OP không hỗ trợ logout, có local fallback/UX phù hợp, không đoán URL?
6. **Multi-provider:** Logout dùng đúng client registration/issuer đã xác thực user, không dùng `lastProvider` global?

### 18.2. Browser request và redirect

7. **RP local endpoint:** Browser gửi POST `/logout` có CSRF defense và session check phù hợp?
8. **OP request:** RP xây request tới đúng `end_session_endpoint` theo OIDC RP-Initiated Logout; GET được OP hỗ trợ, POST chỉ khi provider hỗ trợ?
9. **`id_token_hint`:** Chỉ dùng verified ID token đúng OP/RP, không dùng AT/RT; hạn chế rò trong URL/logs?
10. **`client_id`/`logout_hint`:** Được dùng đúng vai trò hint/registration, không coi là authentication proof?
11. **Post-logout URI:** URI thuộc registration, không wildcard/open redirect, không chấp nhận absolute `returnTo` từ attacker?
12. **State:** Nếu dùng, random và một lần; RP còn lưu state sau khi invalidate session, validate exact trên callback?
13. **Callback:** `/signed-out` không tạo authenticated session hoặc giả lập token revocation success?
14. **Browser cancel:** Nếu user đóng tab, RP session vẫn invalid; không thông báo OP logout đã được xác nhận?
15. **Cookie:** Session cookie name/domain/path, `Secure`/`HttpOnly`/`SameSite` và transaction cookie nếu có được test thật?

### 18.3. Local session, OP session và các RPs khác

16. **Server session:** Session identifier cũ không thể dùng lại tại Pod khác/tab khác sau logout?
17. **Frontend caches:** Các trang có dữ liệu nhạy cảm được bảo vệ khỏi Back-button/caching không phù hợp?
18. **OP session:** Đã test SSO cookie/session thực sự bị OP invalid khi browser theo logout flow?
19. **OP confirmation:** UI và redirect xử lý được trường hợp OP cần user xác nhận hoặc hint không đủ?
20. **Front-channel:** Nếu dùng, đã xem xét third-party cookies/iframe blockers và best-effort delivery?
21. **Back-channel:** Nếu dùng, RP xác minh Logout Token signature/issuer/audience/event/`jti`/`sid` hoặc `sub` theo profile?
22. **Federation:** Có phân biệt OP session và upstream IdP SSO session, không hứa global logout không có hợp đồng?
23. **Scope logout:** Có phân biệt logout thiết bị này/ứng dụng này với logout mọi thiết bị theo chính sách?

### 18.4. Token lifecycle và resource authorization

24. **RT:** Khi yêu cầu chặn refresh, đã revoke RT/grant ở AS bằng cơ chế riêng?
25. **Refresh race:** Background refresh bị fence/CAS và không làm sống lại token store sau logout?
26. **AT:** Đã xác định JWT offline/opaque introspection behavior và khoảng chấp nhận AT cũ theo SLA?
27. **RS:** Vẫn kiểm `iss`, `aud`, `exp`, scope, token purpose và object/tenant ACL?
28. **Consent:** Logout không bị hiểu nhầm thành consent withdrawal hoặc xóa account?
29. **Revoke outcome:** Timeout revocation được ghi UNKNOWN/reconcile, không claim success bừa?

### 18.5. Quan sát và bảo mật vận hành

30. **Logs:** Đã redact `id_token_hint`, AT/RT, authorization code, `Authorization`/client secret trong proxies/APM/browser logs?
31. **Referrer:** OP/RP logout pages không vô tình lộ ID token hint đến third-party resources?
32. **Audit:** Local session, OP redirect/callback, RT revocation và các RP notification có sự kiện riêng?
33. **Failures:** OP outage, missing endpoint, unregistered redirect, expired hint, multiple tabs và stale sessions có tests?
34. **Replay:** Logout state và Back-Channel Logout Token `jti` chỉ dùng một lần theo contract?
35. **Change control:** OP/provider metadata, registered logout URIs, signing keys và client registrations được quản trị/review?
36. **Claims:** UX và compliance không nói “mọi token bị thu hồi” trừ khi hệ thống đã chứng minh được?

## 19. Câu hỏi tự kiểm tra

**Câu 1. RP-Initiated Logout là gì?**

Đó là cơ chế OIDC để RP chủ động đưa browser tới OP `end_session_endpoint`, yêu cầu OP kết thúc phiên SSO. Nó khác local RP logout, RFC 7009 revocation và OIDC Back-Channel Logout.

**Câu 2. Một RP đã xóa `JSESSIONID` có chắc OP SSO session đã logout không?**

Không. Cookie/session của RP và OP thuộc hai miền/trust boundary khác nhau; OP session chỉ được OP quản lý. Login lại có thể silent SSO nếu OP cookie còn.

**Câu 3. `end_session_endpoint` lấy ở đâu?**

Từ **trusted OP discovery metadata** hoặc cấu hình provider được phê duyệt, sau khi xác minh expected issuer/TLS. Không tự đoán `/logout` hoặc lấy từ query parameter của browser.

**Câu 4. `id_token_hint` có bắt buộc không?**

Theo spec nó được **RECOMMENDED**, không phải bắt buộc trong mọi request. OP có thể dùng `client_id`/`logout_hint` và những ngữ cảnh khác theo policy, có thể yêu cầu user confirmation. Không giả ID token nếu không có.

**Câu 5. Có được gửi refresh token trong `id_token_hint` không?**

Không. `id_token_hint` dành cho ID token do OP đã cấp cho RP. RT là credential cho token/revocation endpoint, không dành cho browser logout URL.

**Câu 6. `client_id` trong logout request có xác thực browser/user không?**

Không. Client ID thường là định danh công khai. OP phải ràng buộc request với trusted RP/session context và kiểm tra registered redirect URI.

**Câu 7. `post_logout_redirect_uri` và login `redirect_uri` khác nhau thế nào?**

Login `redirect_uri` nhận authorization code; post-logout URI nhận browser sau OP logout. OP quản lý registration/validation cho mục đích riêng, không cho tùy ý redirect attacker.

**Câu 8. `state` ở logout để làm gì?**

Để RP liên kết callback sau OP logout với **logout transaction** đã bắt đầu; cần random, short-lived, one-time và callback validation. Nó không thay CSRF defense ở POST local logout.

**Câu 9. Tại sao RP nên dùng POST /logout dù OP hỗ trợ GET logout?**

Vì local logout là hành động thay đổi session dựa trên browser cookie; POST + CSRF defense giảm logout CSRF. GET ở `end_session_endpoint` thuộc giao thức OP khác.

**Câu 10. Callback `/signed-out` có chứng minh refresh token đã revoked không?**

Không. Nó chỉ là browser redirect theo logout flow. RT revocation cần AS revocation/grant logic và outcome kiểm chứng riêng.

**Câu 11. Có thể dùng `id_token_hint` đã hết hạn không?**

OP có thể xử lý expired ID token như **hint** theo chính sách/đặc tả, nhưng không được coi nó là authentication credential còn hiệu lực. Tùy provider có thể yêu cầu confirmation hoặc từ chối.

**Câu 12. Logout ở RP-A có tự hủy session RP-B không?**

Không. Cần Front-/Back-Channel Logout hoặc cơ chế SSO session coordination khác. RP-A không có quyền trực tiếp xóa server session của RP-B.

**Câu 13. Back-Channel Logout Token có phải ID token hoặc access token không?**

Không. Đây là JWT sự kiện logout theo OIDC Back-Channel Logout, có `events`/`jti` và `sid` hoặc `sub` theo profile, phải được RP xác minh signature/issuer/audience và chống replay. Nó không dùng để gọi API.

**Câu 14. Tại sao logout OP không bảo đảm logout upstream federated IdP?**

OP đang phát ID token cho RP có thể là một broker liên kết upstream identity provider. Logout propagation đến upstream phụ thuộc contract/hỗ trợ riêng; xóa OP session không tự xóa upstream SSO cookie.

**Câu 15. Một JWT AT còn `exp` sau 10 phút có bị vô hiệu ngay khi OP logout không?**

Không tự động. RS verify JWT offline có thể chấp nhận đến hết hạn; cần AS/RS revocation state, introspection/denylist hoặc TTL phù hợp nếu muốn chặn sớm.

**Câu 16. Khi browser đóng tab trước khi tới OP logout, ứng dụng nên làm gì?**

Giữ local session đã invalidated, không khôi phục token hoặc session; trạng thái OP logout là unknown/best effort. Nếu cần, cho user một cách an toàn để thử logout OP lại.

**Câu 17. Một request refresh đồng thời logout có rủi ro gì?**

Worker có thể nhận RT mới và ghi lại sau khi session bị xóa. Cần session/grant generation fencing, CAS, ngăn refresh mới, revoke family/grant và kiểm thử race.

**Câu 18. Có nên tin `returnTo` do user gửi để làm `post_logout_redirect_uri` không?**

Không. Full URL tự do có thể tạo open redirect/phishing. Dùng registered URI và allowlist/relative paths được kiểm tra chặt.

## 20. Tiêu chuẩn và tài liệu tham khảo

- [OpenID Connect RP-Initiated Logout 1.0](https://openid.net/specs/openid-connect-rpinitiated-1_0.html): OP `end_session_endpoint`, `id_token_hint`, `logout_hint`, `client_id`, `post_logout_redirect_uri`, `state`, `ui_locales` và browser logout request/redirect.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID token, `iss`, `sub`, `aud`, `sid` theo liên quan, RP/OP authentication responsibilities và OIDC session concepts.
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html): issuer/OP configuration và metadata nguồn tin cậy.
- [OpenID Connect Front-Channel Logout 1.0](https://openid.net/specs/openid-connect-frontchannel-1_0.html): OP thông báo logout đến RPs qua browser; giới hạn phụ thuộc cookies/iframes.
- [OpenID Connect Back-Channel Logout 1.0](https://openid.net/specs/openid-connect-backchannel-1_0.html): Logout Token, `events`, `jti`, `sid`, `sub`, issuer/audience validation và server-to-server notification.
- [OpenID Connect Session Management 1.0](https://openid.net/specs/openid-connect-session-1_0.html): session-state monitoring giữa OP và RP, các giới hạn browser-based.
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): authorization, access/refresh token, client/AS/RS roles, scopes và grants.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): revocation endpoint và trạng thái RT/AT, khác OP browser logout.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): `active` metadata của access token tại AS và revocation freshness.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): bảo vệ token, refresh rotation/replay detection và các thực hành an toàn OAuth.
- [RFC 7636 — Proof Key for Code Exchange](https://www.rfc-editor.org/rfc/rfc7636): PKCE Authorization Code exchange; không thay OP logout hoặc token revocation.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): HTTP Bearer token, `invalid_token` và replay/leakage risks.
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519), [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): JWT validation, issuer/audience/time và token-type confusion.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): OAuth JWT AT dành cho RS, khác OIDC ID token.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): nguồn metadata cho các endpoints và issuer trong triển khai OAuth.
- [Spring Security — OIDC Logout](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/logout.html): `OidcClientInitiatedLogoutSuccessHandler`, post-logout redirect URI và đăng xuất RP/OP.
- [Spring Security — OAuth2 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html): OIDC authentication, client registration và verified user.
- [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): bảo vệ các browser POST actions như logout.
- [Spring Security — Logout](https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html): server-side session invalidation, cookie cleanup và logout handlers.
- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): token revocation và OAuth endpoint cấu hình riêng với RP-Initiated Logout.

**Điểm cần ghi nhớ:** **RP-Initiated Logout** là cách một **Relying Party** chủ động yêu cầu **OpenID Provider** kết thúc SSO session qua **`end_session_endpoint`**. RP nên kết thúc **local session** an toàn, lấy OP endpoint từ trusted metadata, gửi **`id_token_hint`** khi có verified ID token, chỉ dùng **registered `post_logout_redirect_uri`** và kiểm tra **`state`** nếu triển khai callback correlation. **POST local logout có CSRF protection** khác **GET browser logout request đến OP**. Việc browser quay về `/signed-out` không chứng minh **mọi RPs, upstream IdP sessions, access tokens hoặc refresh tokens đã mất hiệu lực**. Muốn single logout và token invalidation đầy đủ, phải phối hợp OIDC Front-/Back-Channel Logout, RFC 7009/AS grant revocation, refresh-token race protection và RS audience/scope/expiry/ACL/active-state checks theo SLA đã định nghĩa.
