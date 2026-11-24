# Front-channel và back-channel logout

Giả sử An đăng nhập bằng OpenID Connect (OIDC) vào **Invoice Web**, sau đó mở **Report Portal** trong cùng trình duyệt. Cả hai ứng dụng dùng phiên Single Sign-On (SSO) tại một **OpenID Provider (OP)**. Khi An bấm **Đăng xuất ở OP**, làm thế nào OP thông báo cho cả hai ứng dụng để chúng vô hiệu phiên đăng nhập nội bộ? Nếu trình duyệt chặn iframe hoặc một ứng dụng đang mất kết nối, liệu các phiên còn sống không?

**Front-channel logout** và **back-channel logout** là hai cơ chế của OpenID Connect nhằm **truyền tín hiệu kết thúc phiên từ OP đến Relying Party (RP)**:

- **Front-channel logout:** OP nhờ **trình duyệt người dùng** tải logout URI của các RP, thường qua iframe. Việc truyền tín hiệu phụ thuộc user agent, cookie và chính sách trình duyệt.
- **Back-channel logout:** OP gửi **HTTP POST trực tiếp từ backend OP đến backend RP** mang một **Logout Token** dạng JWT. RP xác minh sự kiện và vô hiệu những phiên tương ứng, không phụ thuộc browser đang mở iframe.

Hai cơ chế **không tự đồng nghĩa với OAuth 2.0 token revocation**. Việc RP xóa session cookie, OP chấm dứt SSO, Authorization Server (AS) thu hồi refresh/access token và Resource Server (RS) ngừng chấp nhận bearer access token là **các trạng thái có liên hệ nhưng khác nhau**.

Bài **“Front-channel và back-channel logout”** thuộc chương **Logout** của module **Security Token Security Fundamentals**. Ta sẽ tìm hiểu OIDC logout signaling trong mô hình tin cậy token, `iss`/`sid`/`sub`/`jti`, tính hợp lệ của Logout Token, giới hạn delivery, XSS/CSRF/replay, mối quan hệ với RFC 7009 và JWT/opaque access token, cùng thiết kế Java/Spring Security, ma trận kiểm thử và các tình huống vận hành.

## 1. Những phiên nào cần kết thúc khi đăng xuất?

Hãy phân biệt **phiên đăng nhập** và **credential/token**:

| Thực thể | Ví dụ | Chủ thể quản lý | Có tự kết thúc khi một RP xóa cookie? |
|---|---|---|---|
| **Phiên RP A** | Cookie `invoice_session=S1` tại Invoice Web | RP A và browser | **Có**, nếu server invalidate đúng |
| **Phiên RP B** | Cookie `report_session=S2` tại Report Portal | RP B và browser | **Không** |
| **Phiên SSO tại OP** | Cookie SSO ở `login.example.test` | OP và browser | **Không** |
| **Access token** | JWT A1 dành cho `invoice-api` | AS phát, RS kiểm | **Không tự động** |
| **Refresh token** | R1 mà RP/BFF giữ để xin access token | AS quản lý grant, client lưu | **Không tự động** |
| **Grant/authorization** | Consent/quyền được ủy quyền cho client | AS | **Không mặc nhiên** |

OP có thể dùng **front-channel** hoặc **back-channel** để ra tín hiệu “hãy kết thúc RP session gắn với phiên OP/subject này”. RP cần **phân biệt** việc đã xử lý sự kiện logout với việc access token đã hết hiệu lực ở tất cả API.

### Các vai trò

- **OP (OpenID Provider):** xác thực người dùng, quản lý SSO và là nguồn phát sự kiện logout.
- **RP (Relying Party):** ứng dụng OIDC đăng ký nhận logout notification và giữ session riêng.
- **AS (Authorization Server):** thường cùng hệ thống OP, nhưng OAuth token/grant lifecycle có hợp đồng riêng.
- **RS (Resource Server):** API dùng access token; phải kiểm token và quyền dữ liệu độc lập.
- **User agent/browser:** đường vận chuyển của **front-channel**, không tham gia đường **back-channel**.

## 2. So sánh front-channel và back-channel theo ranh giới tin cậy

| Tiêu chí | **Front-channel logout** | **Back-channel logout** |
|---|---|---|
| **Đường truyền** | OP → browser → RP | OP backend → RP backend |
| **Request điển hình** | Browser **GET** `frontchannel_logout_uri` (thường trong iframe) | OP **POST** `backchannel_logout_uri` bằng form với `logout_token` |
| **Bằng chứng sự kiện chuẩn** | URI được gọi, có thể kèm `iss`/`sid`; **không phải JWT ký bắt buộc** | **Logout Token** JWT do OP phát, RP phải xác minh |
| **Xác định session** | Browser cookie khi khả dụng, và `iss`/`sid` theo profile, có kiểm scope | `iss` + `sid` và/hoặc `sub`, gắn mapping với session RP |
| **Phụ thuộc third-party cookies/iframe?** | **Có thể phụ thuộc đáng kể** | **Không** |
| **Yêu cầu backend RP có public endpoint?** | Trình duyệt cần tải được logout URI | Backend OP cần kết nối được endpoint RP |
| **Chống giả mạo** | Phải cẩn trọng vì GET và query `iss/sid` có thể bị tự khai | Kiểm chữ ký JWT, issuer, audience, events, replay và session binding |
| **Retry/delivery** | Phụ thuộc browser, không có đảm bảo delivery chặt chỉ từ iframe | Có thể hỗ trợ retry/idempotency/monitoring server-to-server |
| **Kết thúc access token ở RS?** | **Không mặc nhiên** | **Không mặc nhiên** |

**Kết luận thực dụng:** Back-channel thường thuận lợi hơn khi cần tín hiệu logout đã xác thực và kiểm soát việc giao nhận trong hạ tầng server. Front-channel có thể bổ sung trải nghiệm logout qua browser, nhưng **không nên là kiểm soát duy nhất** khi phiên tồn tại lâu hoặc rủi ro cao.

## 3. Hai luồng hoàn chỉnh

### 3.1. Front-channel: browser thực hiện logout notification

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng An
    participant B as Browser của An
    participant OP as OpenID Provider
    participant A as Invoice Web (RP A)
    participant R as Report Portal (RP B)
    U->>B: Chọn đăng xuất tại OP
    B->>OP: Yêu cầu kết thúc SSO
    OP->>OP: Kết thúc OP session theo policy
    OP-->>B: Trang logout với front-channel notifications
    par Gửi tới RP A
        B->>A: GET frontchannel_logout_uri?iss=...&sid=...
        A->>A: Kiểm context và invalidate phiên tương ứng nếu xác định được
    and Gửi tới RP B
        B->>R: GET frontchannel_logout_uri?iss=...&sid=...
        R->>R: Kiểm context và invalidate phiên tương ứng nếu xác định được
    end
    Note over B,R: Một iframe/cookie/request có thể bị browser chặn
~~~

OP **không trực tiếp POST** logout event tới RP trong luồng này; OP chỉ tạo nội dung/điều hướng để **browser tải URI**. Do đó, việc trình duyệt của An **có thực sự tải** được URI, có gửi session cookie, có cho phép iframe và có nhận response không ảnh hưởng rất lớn đến độ tin cậy.

### 3.2. Back-channel: server phát JWT logout event

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng An
    participant OP as OpenID Provider
    participant A as Invoice Web (RP A)
    participant R as Report Portal (RP B)
    U->>OP: Logout tại OP
    OP->>OP: Xác định những RP sessions liên quan
    par OP gửi tới RP A
        OP->>A: POST /oidc/backchannel-logout (logout_token JWT)
        A->>A: Verify JWT và tìm session theo issuer/sub/sid
        A->>A: Invalidate đúng session + audit
        A-->>OP: HTTP acknowledgement
    and OP gửi tới RP B
        OP->>R: POST /oidc/backchannel-logout (logout_token JWT)
        R->>R: Verify JWT và tìm session theo issuer/sub/sid
        R->>R: Invalidate đúng session + audit
        R-->>OP: HTTP acknowledgement
    end
    Note over OP,R: Retry/idempotency/availability cần thiết kế vận hành
~~~

Trong back-channel, browser có thể đã đóng mà RP vẫn nhận được tín hiệu. Tuy nhiên, **OP và RP phải đều hỗ trợ profile**; nếu RP downtime, việc giao nhận vẫn có thể thất bại, và quy tắc retry không thể chỉ dựa vào browser.

## 4. Đăng ký client/metadata để nhận logout notifications

Đừng suy các endpoint logout chỉ từ tên miền ứng dụng. OIDC sử dụng metadata/registration riêng cho từng profile.

### Front-channel metadata

Theo **OpenID Connect Front-Channel Logout 1.0**, RP registration có thể cung cấp:

~~~json
{
  "client_id": "invoice-web",
  "frontchannel_logout_uri": "https://invoice.example.test/oidc/frontchannel-logout",
  "frontchannel_logout_session_required": true
}
~~~

- `frontchannel_logout_uri`: URI để browser tải khi OP gửi thông báo logout.
- `frontchannel_logout_session_required`: RP yêu cầu OP gửi **`iss` và `sid`** trong front-channel logout request để RP nhận diện session phù hợp, khi OP/profile hỗ trợ.
- OP có metadata liên quan khả năng hỗ trợ front-channel và session requirement; cần kiểm discovery/registration thực tế, không mặc định mọi OP hỗ trợ.

Ví dụ browser request:

~~~http
GET /oidc/frontchannel-logout?iss=https%3A%2F%2Flogin.example.test&sid=op-session-789 HTTP/1.1
Host: invoice.example.test
~~~

**`iss` và `sid` trong query không được ký mặc định.** Đó là dữ liệu do HTTP caller có thể tự tạo; RP không được xem hai giá trị này như một **lệnh đã xác thực** để xóa bất kỳ session nào trên server. Cần xây dựng giới hạn scope và tin cậy phù hợp, đặc biệt khi browser không gửi session cookie.

### Back-channel metadata

Theo **OpenID Connect Back-Channel Logout 1.0**, RP có thể đăng ký:

~~~json
{
  "client_id": "invoice-web",
  "backchannel_logout_uri": "https://invoice.example.test/oidc/backchannel-logout",
  "backchannel_logout_session_required": true
}
~~~

- `backchannel_logout_uri`: backend endpoint để OP gửi Logout Token.
- `backchannel_logout_session_required`: RP yêu cầu thông tin **`sid`** trong Logout Token để phân biệt từng phiên. OP và RP phải thống nhất năng lực; nếu OP không đáp ứng session identifier mà RP cần, không coi việc tích hợp đã thành công.
- OP công bố metadata về hỗ trợ back-channel logout theo profile. Các registration fields không thay thế kiểm **Logout Token thực tế**.

**`client_id` trong registration là định danh RP**, không phải password để xác thực HTTP POST. Bằng chứng back-channel chính là Logout Token được OP phát và được RP xác minh theo profile/khóa tin cậy.

### Phạm vi và an toàn của URI

Cả hai URI phải được RP kiểm soát, ưu tiên HTTPS, không chứa token/credential trong query và không trỏ tới open redirect. Không dùng URL nhận từ input người dùng để OP tự động gửi callback; nếu có onboarding động, OP cần chính sách đăng ký URI rõ và chống SSRF/redirect abuse.

## 5. `sid`, `sub`, `iss`: định danh phiên đúng ngữ nghĩa

Các tên giống nhau không có nghĩa có thể hoán đổi:

| Trường | Nguồn và ý nghĩa | Không nên làm |
|---|---|---|
| **`iss`** | Issuer của OP đã xác thực người dùng/phát event | Tin issuer tự khai trong query là đủ proof |
| **`sub`** | Subject người dùng theo **issuer**; không độc lập toàn cầu | Lấy `sub=user:an` từ OP A áp cho OP B |
| **`sid`** | Session ID do OP dùng để xác định phiên đăng nhập theo OIDC profile | Coi là cookie/session ID nội bộ của RP |
| **`jti`** | Định danh duy nhất của **Logout Token event**, dùng chống replay/audit | Coi như access-token `jti` hoặc RP session ID |
| **RP session ID** | Session handle do RP tạo và quản lý | Đưa trực tiếp vào URL public hoặc công khai trong `sid` |

### Lưu session mapping ngay khi login

RP nên liên kết dữ liệu xác thực tin cậy từ ID token đã kiểm vào **session nội bộ**:

~~~text
RpSessionRecord {
  rpSessionHandle = "internal-session-opaque-412"
  verifiedIssuer  = "https://login.example.test"
  verifiedSubject = "user:an"
  opSid           = "op-session-789"   // nếu OP phát sid
  clientId        = "invoice-web"
  active          = true
  createdAt       = trusted timestamp
  expiresAt       = RP session deadline
}
~~~

Khi RP nhận Logout Token có `sid=op-session-789`, nó tra **`issuer + sid`** (và subject/client nếu profile và mapping yêu cầu), sau đó invalidate **chính các RP sessions tương ứng**. Nếu OP gửi **chỉ `sub`**, RP có thể cần invalidate **nhiều phiên** của cùng subject tại RP theo profile/policy; không được áp dụng `sub` trần cho tất cả issuer.

### Một user có thể có nhiều OP sessions và RP sessions

~~~text
An ở laptop: OP sid=O1, RP session=S1
An ở mobile: OP sid=O2, RP session=S2
Bình ở laptop: OP sid=O3, RP session=S3

Logout Token:
  iss=OP-A, sub=An, sid=O1

Expected:
  Invalidate S1 (nếu đúng mapping và policy).
  KHÔNG tự xóa S2 hoặc S3.
~~~

Nếu Logout Token chỉ có `sub=An`, không `sid` và RP cho phép logout theo subject, phạm vi có thể rộng hơn — thường là các RP sessions khớp `issuer + subject`. Đây là lý do yêu cầu session-specific logout phải quyết định **ngay ở registration** bằng `backchannel_logout_session_required` và cách RP quản lý state.

## 6. Front-channel logout URI: GET, iframe và session cookie

Một OP có thể trả trang HTML chứa các iframe tải những RP logout URIs. Đây là **ý tưởng luồng**, không phải HTML template bắt buộc:

~~~html
<iframe
  src="https://invoice.example.test/oidc/frontchannel-logout?iss=https%3A%2F%2Flogin.example.test&amp;sid=op-session-789"
  title="Invoice logout"
  style="display:none"></iframe>
<iframe
  src="https://reports.example.test/oidc/frontchannel-logout?iss=https%3A%2F%2Flogin.example.test&amp;sid=op-session-789"
  title="Reports logout"
  style="display:none"></iframe>
~~~

Các iframe nằm trong tài liệu do OP phát và browser cố tải từ các origin RP khác. Không cần coi **CORS** là bằng chứng bảo mật: việc iframe điều hướng/tải tài nguyên khác cơ chế JavaScript `fetch` đọc response; **CORS không xác thực logout notification**.

### Browser có thể làm thất bại yêu cầu như thế nào?

1. **Third-party cookies bị chặn:** RP cookie không được gửi trong iframe cross-site, nên RP không biết session hiện tại.
2. **SameSite policy:** Cookie `SameSite=Lax` hoặc `Strict` thường không được gửi trong một iframe cross-site. `SameSite=None; Secure` là một điều kiện kỹ thuật ở một số browser, nhưng **không vượt được mọi biện pháp third-party cookie blocking**.
3. **Frame blocking:** `Content-Security-Policy: frame-ancestors` và `X-Frame-Options` của endpoint có thể ngăn OP nhúng iframe; không tắt CSP trên toàn ứng dụng để chữa lỗi một endpoint.
4. **Ad/tracking blockers, mạng hoặc navigation:** URI có thể không được gọi; tab có thể đóng giữa chừng.
5. **Thời gian:** RP có thể xử lý chậm hoặc bị deploy; browser không có cơ chế “đã tới mọi RP” đủ tin cậy chỉ từ việc hiển thị trang.

**Không suy rằng RP đã logout vì OP hiển thị màn hình “You are signed out.”** Có thể OP đã kết thúc SSO nhưng iframe tới RP chưa từng được tải.

### Nếu không có cookie, dùng `sid` query để xóa session?

**Không được làm một cách mù quáng.** Vì `sid` là query value tự gửi, một attacker biết/đoán session identifier có thể gọi endpoint và gây **logout CSRF hoặc DoS theo session**. Front-channel không mang JWT ký theo chuẩn; hãy thiết kế giới hạn theo session browser đáng tin, policy nguồn thông báo và biện pháp bổ sung nếu cần. Nếu không xác định được đúng session an toàn, **đừng xóa hàng loạt sessions bằng query tự khai**.

Một kiến trúc cần logout chắc chắn khi browser chặn cookie nên ưu tiên **back-channel** có Logout Token đã ký hoặc phiên timeout/reauthentication được quản lý, thay vì vô hiệu hóa xác thực trên endpoint GET.

## 7. Front-channel và bài toán CSRF đặc biệt

Ở local logout thông thường, ứng dụng nên dùng **POST + CSRF token** với cookie session. Nhưng front-channel logout được thiết kế để browser **GET một logout URI từ context của OP** — đây là trường hợp giao thức có tính chất cross-site.

Nếu dùng chung endpoint `GET /logout` cho cả người dùng và OP front-channel, dễ xảy ra:

~~~text
Attacker đặt:
  <img src="https://invoice.example.test/logout">

Browser nạn nhân tải ảnh:
  GET /logout

Nếu app xóa mọi phiên dựa vào GET:
  Nạn nhân bị logout không mong muốn (logout CSRF).
~~~

**Phân tách hai endpoint:**

~~~text
POST /logout
  RP local logout do user khởi tạo, kiểm CSRF/session.

GET /oidc/frontchannel-logout
  Endpoint đặc thù cho tín hiệu OIDC, xử lý session mapping
  có giới hạn và không mặc định coi mọi GET là lệnh hợp lệ.
~~~

Tín hiệu `iss`/`sid` trong front-channel có thể hỗ trợ correlation, nhưng **không thay chữ ký**. Không coi `Referer`/`Origin` HTTP headers luôn tồn tại hoặc đủ để bảo vệ vì chúng có thể vắng, bị policy lọc hoặc không chứng thực end-user intent; nếu dùng, chỉ là tín hiệu bổ trợ trong threat model.

### Front-channel status: điều gì đủ để báo “đã logout”?

Một RP có thể trả HTTP 200/204 khi đã xử lý logout URI, nhưng response HTTP đó **không chứng minh** mọi browser tab/token/grant khác đã bị vô hiệu. Cần có cơ chế kiểm session store để xác nhận đúng RP session invalidated. Front-channel nên có **session TTL** và khả năng kiểm trạng thái OP khi cần, không phụ thuộc duy nhất vào một iframe một lần.

## 8. Back-channel Logout Token: cấu trúc JWT và giao thức POST

Theo **OpenID Connect Back-Channel Logout 1.0**, OP gọi endpoint RP đã đăng ký bằng **HTTP POST** với form parameter `logout_token`. Đây là **JWT thông báo sự kiện**, không phải cookie, access token, authorization code hoặc OIDC ID token thông thường.

~~~http
POST /oidc/backchannel-logout HTTP/1.1
Host: invoice.example.test
Content-Type: application/x-www-form-urlencoded
Accept: */*

logout_token=<url-encoded-signed-jwt>
~~~

RP cần lấy đúng **một** tham số `logout_token`, parse theo HTTP form encoding, áp giới hạn kích thước request và validate token. Không nhận token từ query string/URL hoặc header tự đặt trừ khi một giao thức mở rộng đã được các bên đăng ký và kiểm đầy đủ.

### Payload Logout Token minh họa

~~~json
{
  "iss": "https://login.example.test",
  "aud": "invoice-web",
  "iat": 1800000000,
  "jti": "logout-event-random-001",
  "events": {
    "http://schemas.openid.net/event/backchannel-logout": {}
  },
  "sub": "user:an",
  "sid": "op-session-789"
}
~~~

Đây **chỉ là payload JSON minh họa**, chưa có chữ ký JWS. Một Logout Token thực tế phải được xử lý dưới dạng JWT phù hợp với cấu hình OP/RP, có xác minh mật mã và kiểm claims; **không** đọc payload rồi tin là sự kiện đăng xuất.

| Claim | Bắt buộc/điều kiện | Cần kiểm |
|---|---|---|
| **`iss`** | Bắt buộc | Chuỗi issuer **khớp chính xác** OP đã đăng ký |
| **`aud`** | Bắt buộc | Có `client_id` của chính RP trong audience |
| **`iat`** | Bắt buộc | NumericDate thời điểm sự kiện được phát, trong giới hạn thời gian/replay window phù hợp |
| **`jti`** | Bắt buộc | Định danh event duy nhất; chống xử lý trùng/replay trong lưu trữ có kiểm soát |
| **`events`** | Bắt buộc | Chứa member `http://schemas.openid.net/event/backchannel-logout` với JSON object rỗng theo profile |
| **`sub`** | Có thể có; **`sub` hoặc `sid` phải có ít nhất một** | Subject theo issuer; binding tới đúng user/session |
| **`sid`** | Có thể có, nhưng phải có nếu RP yêu cầu session-specific theo registration | OP session identifier; mapping tới đúng session RP |
| **`nonce`** | **Không được có** | Logout Token có `nonce` là sai OIDC Back-Channel Logout profile |
| `exp` | Có thể có tùy profile | Nếu có, kiểm expiration theo JWT/policy, không chấp nhận sự kiện hết hạn |

### Vì sao một Logout Token không phải ID token?

ID token có mục tiêu chứng minh **authentication event** cho một RP, theo giao thức login và validation riêng. Logout Token phát tín hiệu **kết thúc phiên**, có claim `events` đặc thù, `jti` chống replay và **không có `nonce`**. Nó không trao quyền truy cập API; không lưu làm access token hoặc dùng `Authorization: Bearer <logout-token>` để gọi Resource Server.

Ngược lại, **ID token cũ** không phải một Logout Token chỉ vì nó có `iss`/`sub`/`sid`. RP phải kiểm **event type và token purpose** nhằm ngăn token substitution.

## 9. Quy trình xác minh Logout Token bắt buộc

Một RP an toàn xử lý sự kiện theo các bước riêng biệt, fail closed trước khi đụng session store:

1. **Chọn OP theo registration/trust context đáng tin**, không chấp nhận `iss` được token tự khai để tải JWKS từ hostname bất kỳ.
2. **Parse JWT có giới hạn kích thước/độ phức tạp**, không chấp nhận token hỏng, alg `none`, key/alg không nằm trong allowlist hoặc header dẫn tới SSRF/key substitution.
3. **Xác minh chữ ký (hoặc quy trình JWT bảo mật được hai bên cấu hình)** với khóa OP trusted từ metadata/JWKS đã kiểm; hỗ trợ rotation có kiểm soát.
4. Kiểm **`iss` exact match** và **`aud` chứa client ID của RP**; không dùng audience của một RP khác.
5. Kiểm **`iat` hợp lý và cửa sổ chấp nhận sự kiện**, `exp` nếu có; hạn chế dùng lại notification quá cũ.
6. Kiểm **`jti` nonempty/unique** và chống duplicate/replay trong scope `issuer + audience + event ID`.
7. Kiểm **`events`** có `http://schemas.openid.net/event/backchannel-logout` với value đúng schema; **từ chối nếu có `nonce`**.
8. Yêu cầu **ít nhất một `sub` hoặc `sid`**; nếu cả hai có mặt, phải xác minh chúng **khớp cùng session mapping**.
9. Xác định chính xác RP session(s) thuộc **`issuer + subject/sid + client`**; invalidate **atomic** theo scope và policy.
10. Ghi nhận kết quả xử lý, idempotency và audit; trả HTTP response theo profile, **không** đưa token/PII vào body.

### Token sai không được biến thành lệnh xóa session

~~~text
UNSAFE:
  parseUnsignedJwtPayload(logout_token)
  sessionStore.deleteAllSessionsFor(payload.sub)

SAFE:
  verify Logout Token JWS and all OIDC logout claims
  bind verified issuer/client/sub/sid to RP session(s)
  invalidate only matched sessions, idempotently
~~~

Nếu không có RP session nào khớp, RP có thể xử lý như một notification hợp lệ nhưng **không có session cần xóa** (theo contract/idempotency); không được chọn “session gần nhất” hay “toàn bộ session” để cố làm cho event có tác dụng.

### Kiểm audience đặc biệt quan trọng ở multi-RP

Một OP có thể gửi Logout Token `aud=invoice-web` tới RP A. Nếu attacker forward nguyên JWT đó đến RP B, RP B **phải từ chối** khi client ID của mình là `reports-web`. Chữ ký OP hợp lệ **không thay kiểm audience**.

### Event `jti` dùng ở đâu?

`jti` giúp nhận biết **một sự kiện logout**, không phải ID của access token bị revoke. RP có thể dùng kho deduplication với TTL phù hợp để nhớ `issuer/client/jti` đã xử lý. Việc một event được gửi lại sau timeout thường nên **idempotent**, nhưng cần chống replay gây sai lệch audit, quota hoặc trạng thái nhiều phiên.

## 10. Back-channel session targeting: `sub`, `sid` và tính nhất quán

**`sid`** rất hữu ích khi user có nhiều phiên của cùng RP hoặc nhiều thiết bị:

~~~text
RP session store:
  S1: issuer=OP-A, subject=An, opSid=O1, device=laptop
  S2: issuer=OP-A, subject=An, opSid=O2, device=phone
  S3: issuer=OP-A, subject=Bình, opSid=O3, device=laptop
  S4: issuer=OP-B, subject=An, opSid=O4, device=tablet
~~~

**Logout Token `iss=OP-A`, `sub=An`, `sid=O1`** → chỉ session S1 tương ứng (hoặc đúng tập session cùng OP sid theo policy) được invalidate.

**Logout Token `iss=OP-A`, `sub=An` không có `sid`** → theo profile, RP có thể kết thúc các sessions của An tại RP do OP-A xác thực; nếu ứng dụng yêu cầu phiên cụ thể thì việc **không có sid** phải bị từ chối theo session-required contract.

**Logout Token chỉ có `sid=O2`** → RP có thể xác định đúng session qua issuer và sid nếu mapping đáng tin, nhưng không được tự suy một subject khác. Nếu có cả `sub` và `sid` mà chúng mâu thuẫn với session store, **từ chối** thay vì dùng một trường và bỏ trường kia.

### Tại sao không dùng `sub` một mình trong hệ thống nhiều OP?

`sub` chỉ duy nhất trong **ngữ cảnh issuer**, không nhất thiết duy nhất giữa các Identity Providers. `sub="12345"` tại OP-A có thể là người khác hoàn toàn với `sub="12345"` tại OP-B.

~~~text
WRONG CACHE INDEX:
  subject -> all sessions

SAFER INDEX:
  issuer + client_id + subject -> eligible RP sessions
  issuer + client_id + sid -> eligible RP sessions
~~~

Khi nhận event back-channel sau đổi tài khoản, merged identities hoặc chuyển tenant, phải áp đúng **subject mapping** và policy. Một logout của An trong tổ chức A không được khiến Bình hoặc user tenant B bị logout chỉ vì trùng email/username.

## 11. Delivery: back-channel tốt hơn nhưng không “đảm bảo 100%”

Vì back-channel là server-to-server, OP có thể biết HTTP status/timeout và thiết kế retry/audit. Nhưng vẫn có failure modes:

| Sự cố | Nguy cơ | Thiết kế cần có |
|---|---|---|
| RP logout endpoint downtime | OP không gửi notification thành công | Retry có giới hạn, durable delivery policy, alert |
| OP timeout sau khi RP đã invalidate | OP nghĩ chưa thành công và gửi lại | Idempotency bằng `jti`/session state |
| RP nhận hai notification đồng thời | Race hoặc double processing | Atomic state transition/dedupe |
| Event tới muộn sau khi user đăng nhập lại | Có thể xóa nhầm session mới | Mapping `sid`, issuer, session generation và thời gian event |
| Event có `sub` nhưng không `sid` | Tác động tất cả phiên subject nếu policy cho phép | Scope rõ trong registration/policy, tránh fallback tùy tiện |
| OP signer key rotation | Verify thất bại nếu JWKS stale | Trusted JWKS refresh theo policy, không fail-open |
| OP gửi JWT sai audience | RP khác có thể xử lý nhầm | Kiểm `aud` chặt |
| OP retry quá nhiều | RP bị flood | Rate limit, duplicate fast-path, bounded queue |
| RP đã xóa session | No-op event được coi là lỗi nặng | Idempotent handling/ack phù hợp |

### Một response thành công xác nhận điều gì?

RP trả HTTP **200** sau khi đã kiểm event và thực hiện invalidate phù hợp theo contract. Đó là **acknowledgement xử lý notification**, không phải bằng chứng:

- Mọi session RP khác đã bị logout.
- OP đã revoke toàn bộ access/refresh token.
- JWT self-contained không còn được RS offline chấp nhận.
- User không thể bắt đầu login mới bằng một session/credential khác.

Với lỗi tạm thời, OP/RP cần quy trình retry và giám sát rõ. Đặc tả logout không tự tạo distributed transaction giữa OP, mọi RP và mọi Resource Server.

### Thời hạn xử lý và sự kiện đến muộn

Một event có `iat` cũ hơn cửa sổ cho phép có thể bị từ chối theo policy để hạn chế replay. Nhưng nếu hạ tầng có retry lâu, cần **quyết định thiết kế cụ thể**: hỗ trợ hàng đợi bảo đảm delivery có kiểm chứng, hoặc session TTL/phương án reconcile; không mở cửa sổ JWT vô hạn chỉ để tiếp nhận mọi event muộn.

## 12. Front-channel có thể bị spoof: threat model và biện pháp phòng vệ

Front-channel URI phải đủ an toàn khi được gọi từ **một browser bất kỳ**. Không nên mã hóa logic:

~~~text
GET /oidc/frontchannel-logout?iss=OP-A&sid=O1

deleteEverySessionWhoseOpSidIs(O1)
return 200
~~~

Vấn đề: bất kỳ attacker nào có thể gửi GET với `iss` và `sid` tự khai. Dù session identifiers khó đoán, chúng có thể bị lộ qua URL log, analytics hoặc debugging. **Không có chữ ký** như back-channel để RP xác định chính OP gửi yêu cầu.

### Phòng vệ theo từng nhu cầu

- Nếu dùng browser cookie: chỉ invalidate **đúng session browser đã xác định hợp lệ**, có so correlation/`iss`/`sid` với mapping; lưu ý third-party cookies có thể vắng.
- Nếu bắt buộc session-specific logout mà cookie không ổn định: dùng **back-channel signed Logout Token** thay vì tin query `sid`.
- Nếu front-channel chỉ dùng làm **tín hiệu gợi ý**: đánh dấu client-side state cần kiểm lại hoặc điều hướng đến một flow được bảo vệ, không xóa các sessions server khác từ query không xác thực.
- Giới hạn request rate, tránh phản hồi tiết lộ session nào tồn tại, không trả PII hoặc token.
- Tách request handler từ browser CSRF-protected local logout; cấu hình CSP, iframe policy cho endpoint cụ thể, không tắt header bảo vệ trên toàn domain.

**Điểm cần nhớ:** Kể cả `iss` là một URL HTTPS có vẻ hợp lệ, nó vẫn chỉ là **chuỗi được truyền trong request**, không tự biến HTTP GET thành thông báo được OP ký.

### Không có giải pháp “dùng CORS” để chứng thực sender

CORS áp dụng chủ yếu cho quyền JavaScript từ một origin đọc response từ origin khác. Nó không cung cấp chữ ký hay bảo đảm một request GET/iframe thật sự do OP phát. Khi cần xác thực mạnh và phân vùng session chính xác, **back-channel signed Logout Token** là lựa chọn thích hợp hơn.

## 13. So với RP-Initiated Logout và Session Management

**RP-Initiated Logout** trả lời câu hỏi: *“Một RP yêu cầu OP kết thúc phiên SSO thế nào?”* Nó thường bắt đầu từ browser redirect tới `end_session_endpoint`.

**Front-Channel Logout** trả lời: *“OP dùng browser để thông báo các RP về sự kiện logout thế nào?”*

**Back-Channel Logout** trả lời: *“OP gửi một sự kiện JWT đã xác thực trực tiếp tới backend RP thế nào?”*

**OIDC Session Management** là một cơ chế khác để theo dõi thay đổi trạng thái đăng nhập thông qua các tín hiệu phiên/user agent theo profile; không được nhầm với việc OP gửi Logout Token qua back-channel.

~~~mermaid
flowchart TD
    U["Người dùng bấm logout tại RP A"] --> RP["RP A invalidate local session"]
    RP --> RI["Có yêu cầu logout OP SSO?"]
    RI -- "Có" --> OP["RP-Initiated Logout → OP end_session_endpoint"]
    RI -- "Không" --> END["Chỉ logout RP A"]
    OP --> F{"OP và RP chọn cơ chế notification"}
    F -- "Front-channel" --> B["Browser tải RP logout URIs"]
    F -- "Back-channel" --> C["OP POST signed Logout Tokens tới RP backends"]
    F -- "Cả hai/khác" --> M["Theo profile thực tế đã đăng ký"]
    B --> S["RP tự invalidate session tương ứng"]
    C --> S
    M --> S
    S --> G["Nếu cần: AS token revocation và RS revocation enforcement riêng"]
~~~

Sơ đồ này mô tả một **khả năng điều phối**, không phải bảo đảm OP luôn gửi cả hai loại notification. Hệ thống nào được hỗ trợ phụ thuộc OP discovery, RP registration và flow kích hoạt logout.

### `post_logout_redirect_uri` khác logout notification URI

`post_logout_redirect_uri` là nơi OP có thể trả browser về **sau RP-Initiated Logout**; nó không phải `frontchannel_logout_uri` hoặc `backchannel_logout_uri`. Cả ba cần cấu hình theo profile đúng và không chấp nhận redirect URI từ input tự khai mà không có kiểm registration.

## 14. Token revocation: một bước khác với logout notification

Khi RP nhận front/back-channel logout và invalidate RP session, các bearer access token **đã bị sao chép** có thể còn dùng được. OAuth **RFC 7009** cung cấp revocation endpoint để client được phép yêu cầu AS vô hiệu token.

~~~http
POST /oauth2/revoke HTTP/1.1
Host: login.example.test
Authorization: Basic <redacted-authorized-client-credential>
Content-Type: application/x-www-form-urlencoded

token=<url-encoded-refresh-token>&token_type_hint=refresh_token
~~~

| Hành động | Đích thực thi | Kết quả |
|---|---|---|
| OP kết thúc SSO cookie | OP | Không còn OP SSO session đó |
| OP phát front-channel GET | Browser tới RP | RP **có thể** invalidate session nếu xác định đúng |
| OP phát back-channel Logout Token | OP tới RP backend | RP xác minh và invalidate session phù hợp |
| RP xóa session cookie/server state | RP | Client không dùng RP session cũ |
| RP revoke refresh token | AS | Refresh token/grant bị vô hiệu theo policy AS |
| RS kiểm `active=false` hoặc denylist | RS | Access token bị chặn khi RS biết revoke state |

**RFC 7009 HTTP 200** có thể được trả ngay cả khi token không tồn tại, để tránh token-validity oracle. Nó không cam kết **mọi RS đã ngừng nhận JWT ngay lập tức**.

### JWT offline và opaque token

| Access token | Cách RS kiểm | Sau logout/AS revoke |
|---|---|---|
| **Opaque/reference** | Introspection tới AS (có thể cache) | Có thể từ chối sớm theo `active=false`; độ trễ bằng cache/propagation |
| **JWT offline validation** | Chữ ký/JWKS, issuer, audience, `exp`, scope | Token đã cấp có thể được chấp nhận tới `exp` nếu không có revoke state |
| **JWT + denylist/introspection** | Kết hợp chữ ký và trạng thái revoke | Có thể chặn sớm nếu RS nhận tín hiệu kịp thời |
| **Sender-constrained (DPoP/mTLS)** | Token validation và proof/chứng chỉ người gửi | Khó sử dụng bản sao token đơn lẻ, nhưng vẫn cần logout/revoke policy |

**Không gọi Logout Token của OIDC là access token**, và không coi việc AS revoke refresh token tự làm mất mọi RP session cookie đang sống. Hai hướng điều phối có thể cùng cần thực hiện tùy chính sách.

## 15. Java 17: xử lý back-channel logout bằng event đã xác minh

Đoạn code minh họa dưới đây **chỉ xử lý business state sau khi JWT đã được một thư viện OIDC/JWT tin cậy xác minh mật mã**. Không tự xây JWT signature verification, không lấy khóa công khai từ `jku`/`jwk` do attacker tự chỉ định.

Giả định RP có **một OP tin cậy và một client ID**, có session store và cơ chế idempotency/replay guard chung giữa các replica.

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Set;

// Được tạo CHỈ sau khi JOSE/OIDC library xác minh JWT.
record VerifiedLogoutEvent(
    String issuer,
    Set<String> audiences,
    Instant issuedAt,
    Instant expiresAt,
    String eventId,
    boolean correctBackchannelEvent,
    boolean hasNonce,
    String subject,
    String opSessionId
) {}

record BackchannelPolicy(
    String trustedIssuer,
    String rpClientId,
    Duration maximumEventAge,
    Duration allowedClockSkew,
    boolean requireSid
) {}

interface TrustedLogoutTokenVerifier {
    // Verify signature, allowed alg/key, issuer, audience,
    // required OIDC logout claims/types/events, and JWT format.
    VerifiedLogoutEvent verify(String signedLogoutToken);
}

interface LogoutSessionStore {
    // Trong MỘT transaction/atomic operation:
    // - deduplicate issuer+RP+jti in a bounded replay window;
    // - map issuer+RP+sub/sid tới đúng RP session(s);
    // - nếu sub và sid cùng có, yêu cầu chúng nhất quán;
    // - invalidate session(s) hợp lệ;
    // - đánh dấu event đã xử lý trong cùng transaction.
    //
    // DUPLICATE: đã xử lý; idempotent no-op.
    // NO_MATCH: không có session hợp lệ; không xóa rộng.
    ApplyResult applyAtomically(VerifiedLogoutEvent event);
}

enum ApplyResult { INVALIDATED, NO_MATCH, DUPLICATE }

final class BackchannelLogoutHandler {
    private final TrustedLogoutTokenVerifier verifier;
    private final LogoutSessionStore sessions;
    private final BackchannelPolicy policy;
    private final Clock clock;

    BackchannelLogoutHandler(
        TrustedLogoutTokenVerifier verifier,
        LogoutSessionStore sessions,
        BackchannelPolicy policy,
        Clock clock
    ) {
        this.verifier = verifier;
        this.sessions = sessions;
        this.policy = policy;
        this.clock = clock;
    }

    ApplyResult handle(String signedLogoutToken) {
        VerifiedLogoutEvent event = verifier.verify(signedLogoutToken);
        if (!policy.trustedIssuer().equals(event.issuer())) {
            throw new SecurityException("Unexpected logout issuer");
        }
        if (event.audiences() == null ||
            !event.audiences().contains(policy.rpClientId())) {
            throw new SecurityException("Wrong logout audience");
        }
        if (!event.correctBackchannelEvent() || event.hasNonce()) {
            throw new SecurityException("Invalid logout event claims");
        }
        if (event.eventId() == null || event.eventId().isBlank()) {
            throw new SecurityException("Missing jti");
        }
        if (event.subject() == null &&
            event.opSessionId() == null) {
            throw new SecurityException("Missing sub and sid");
        }
        if (policy.requireSid() && event.opSessionId() == null) {
            throw new SecurityException("Session ID required");
        }
        if (event.issuedAt() == null) {
            throw new SecurityException("Missing iat");
        }

        Instant now = clock.instant();
        Duration age = Duration.between(event.issuedAt(), now);
        if (age.compareTo(policy.allowedClockSkew().negated()) < 0 ||
            age.compareTo(policy.maximumEventAge()) > 0) {
            throw new SecurityException("Stale or future logout event");
        }
        if (event.expiresAt() != null &&
            !now.isBefore(event.expiresAt())) {
            throw new SecurityException("Expired logout token");
        }

        // Chỉ thao tác session sau tất cả kiểm tra ở trên.
        return sessions.applyAtomically(event);
    }
}
~~~

### Những phần production chưa có trong snippet

- `TrustedLogoutTokenVerifier` phải được triển khai bằng **JOSE/OIDC library**, xác minh JWS/JWE theo trust contract, chữ ký, issuer/audience, JSON types, event object, `nonce` vắng, key rotation và algorithm policy. Method `verify()` **không được** chỉ Base64 decode.
- `BackchannelPolicy` được khởi tạo từ cấu hình **trusted issuer và RP registration**, không lấy từ JWT hoặc HTTP query.
- `LogoutSessionStore.applyAtomically()` phải kiểm **`issuer+client+sub/sid`** với session thật; chỉ nhận `sid` của đúng issuer, xử lý trường hợp cả `sub`/`sid` không khớp bằng từ chối hoặc không xóa; nên có transaction atomic giữa dedupe và invalidation.
- `maximumEventAge`, `allowedClockSkew` và TTL dedupe phải được review theo retry/delivery policy. Các giá trị không âm, giới hạn hợp lý.
- Mã thiếu HTTP handler, TLS/proxy configuration, rate limiting, storage cleanup, distributed tracing, privacy/audit, secure retry and cancellation. Không dùng làm API production nguyên xi.

**Tại sao dedupe + session invalidation phải nguyên tử?**

~~~text
SAI:
  mark jti=J1 processed
  crash before invalidating RP session S1
  OP retries J1
  handler sees processed -> ignores
  S1 remains active

ĐÚNG:
  transaction:
    verify jti not yet processed
    invalidate matching RP sessions
    record jti processed
  commit atomically
~~~

Với Redis + SQL khác nhau, một transaction đơn lẻ có thể không khả dụng; khi đó thiết kế **idempotent state transition, outbox/inbox, reconciliation** và retry có kiểm soát thay vì giả vờ có atomicity giữa hai hệ thống.

## 16. Spring Security: cấu hình phiên và tích hợp logout endpoint

Với một Spring Boot 3 / Spring Security 6 RP, thông thường ứng dụng đã có **`SecurityFilterChain`, OAuth2 Login/OIDC client registration và session handling**. Hãy giữ ranh giới:

1. **Local logout:** dùng Spring Security logout handler để invalidate `HttpSession`/SecurityContext và xóa cookie phù hợp; bảo vệ CSRF cho browser POST.
2. **RP-Initiated Logout:** nếu cần OP SSO logout, có thể dùng `OidcClientInitiatedLogoutSuccessHandler` theo metadata `end_session_endpoint` và `post_logout_redirect_uri` đã đăng ký.
3. **Front-channel:** endpoint GET riêng, không tái sử dụng `/logout` mở cho mọi GET; chỉ xử lý những RP session mà request có thể xác định **an toàn**.
4. **Back-channel:** endpoint POST riêng, nhận form `logout_token`, xác minh Logout Token đầy đủ và invalidate session store theo `issuer/sub/sid`.
5. **AS token revocation:** adapter riêng gửi RFC 7009 request qua HTTPS/client authentication khi chính sách yêu cầu.

### Mã giả wiring cho back-channel endpoint

Đây là **minh họa interface Spring MVC**, không phải cấu hình Spring Security back-channel hoàn chỉnh:

~~~java
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
final class OidcBackchannelController {
    private final BackchannelLogoutHandler handler;

    OidcBackchannelController(BackchannelLogoutHandler handler) {
        this.handler = handler;
    }

    @PostMapping(
        path = "/oidc/backchannel-logout",
        consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    ResponseEntity<Void> logout(
            @RequestParam("logout_token") String logoutToken) {

        handler.handle(logoutToken);
        // Không ghi log JWT hoặc session identifiers nhạy cảm.
        return ResponseEntity.ok().build();
    }
}
~~~

**Cảnh báo cấu hình bảo mật:**

- Endpoint này là **server-to-server**, thường **không có CSRF token của browser**; có thể cần **CSRF exception có phạm vi chính xác tới path/method này**, không tắt CSRF toàn bộ ứng dụng. Cách ngoại lệ và xác thực được áp dụng tùy phiên bản Spring/profile.
- Nếu filter chain mặc định bắt browser session login mới tới được endpoint, OP sẽ bị chặn. Endpoint cần được phép nhận HTTP request **nhưng phải kiểm JWT trước khi làm thay đổi session**. “`permitAll()` ở network layer” không đồng nghĩa tin mọi POST.
- Nếu Spring Security phiên bản đang dùng có **tích hợp OIDC back-channel logout được hỗ trợ**, ưu tiên framework/SDK đã được cập nhật thay vì tự viết kiểm JWT. Cần xác nhận chính xác contract và cấu hình phiên bản tại môi trường triển khai.
- Giới hạn request size, content type, rate/connection limits và không phản hồi thông tin về subject/session cho caller.
- Khi ứng dụng có nhiều replica, session store **phải chia sẻ được** hoặc cơ chế invalidation phát tới node sở hữu session; invalidate chỉ trên memory của node nhận POST có thể bỏ sót phiên ở node khác.
- Nếu có cả logout local và back-channel, logic session termination cần idempotent, nhưng **không** cho front-channel GET mạo danh back-channel POST có JWT.

### Front-channel handler không nên nhận `sid` như quyền admin

~~~text
Bad:
  @GetMapping("/oidc/frontchannel-logout")
  deleteEverySessionFor(request.query.sid)

Better:
  establish trusted browser session context if available
  compare issuer/sid to that current session
  invalidate only when policy allows
  otherwise no broad delete; rely on signed back-channel
~~~

Việc endpoint GET có `permitAll()` theo Spring Security không phải bằng chứng OP đứng sau request. **Front-channel protocol không bảo đảm cryptographic authentication cho URL query theo mặc định.**

## 17. Đồng bộ nhiều tab, nhiều thiết bị và nhiều issuer

### Một browser, hai tab cùng RP

Nếu RP session cookie dùng chung giữa các tab, khi session server-side bị invalidate, **request kế tiếp** từ mỗi tab sẽ bị từ chối theo session store. Nhưng giao diện của tab không hoạt động có thể vẫn hiển thị trang cũ trong memory cho tới khi có request.

Ứng dụng có thể dùng browser **BroadcastChannel** hoặc cơ chế client-side notification khác để cập nhật UI giữa các tab thuộc cùng origin. Đây chỉ là **UX synchronization**; quyền truy cập API phải được backend/RS thực thi, không dựa vào tab đã nhận thông báo hay chưa.

### Hai thiết bị có OP `sid` khác nhau

~~~text
Laptop browser: OP sid=O1, RP session=S1
Phone browser:  OP sid=O2, RP session=S2

Logout Token with sid=O1:
  Invalidate S1.
  Keep S2 nếu chính sách là logout phiên O1.

Logout Token with only sub=An:
  Có thể invalidate cả S1 và S2 theo RP/OP profile,
  nếu RP chấp nhận subject-wide logout.
~~~

Không được tuyên bố “logout all devices” nếu OP chỉ phát một event cho `sid=O1` và RP chưa có cơ chế xử lý những sessions còn lại.

### Nhiều issuer

~~~text
OP-A: issuer=https://login-a.example.test, sub=42, sid=A1
OP-B: issuer=https://login-b.example.test, sub=42, sid=B1

Logout Token signed by OP-A:
  RP chỉ invalidates sessions linked to OP-A.
  OP-B session không bị ảnh hưởng nếu không có policy hợp pháp riêng.
~~~

**`sub` không phải global user ID.** Multi-tenant/multi-issuer RP phải quản lý chính sách trust, issuer mapping, key set và session index cẩn thận. Kẻ chiếm một OP registration hoặc endpoint không được điều khiển phiên của OP khác.

## 18. Metrics, audit và khắc phục sự cố delivery

| Signal | Mục đích | Lưu ý bảo mật |
|---|---|---|
| `oidc_frontchannel_request_total` | Browser có tải notification URI không | Không log raw `sid`/query nhạy cảm |
| `oidc_frontchannel_session_match_total` | Có session context đủ tin cậy để invalidate không | Không coi request count là số phiên đã logout |
| `oidc_backchannel_received_total` | OP đã gửi Logout Token tới RP | Phân loại issuer/client registration đã xác minh |
| `oidc_logout_jwt_invalid_total` | Chữ ký/iss/aud/events/nonce sai | Không log raw JWT |
| `oidc_logout_event_duplicate_total` | OP retry hoặc event replay | Dedupe theo `jti` trong audit store có ACL |
| `oidc_backchannel_delivery_lag_seconds` | Độ trễ từ `iat` tới xử lý | Có clock-skew policy |
| `rp_sessions_invalidated_total` | Session thực sự đã bị vô hiệu | Không lộ user/session ID trong metrics label |
| `oidc_logout_no_matching_session_total` | Không có session để hủy | Có thể bình thường khi session đã hết hạn |
| `oauth_revoke_requested_total` | Yêu cầu RFC7009 gửi AS | Không suy RS đã từ chối token |
| `rs_revocation_propagation_seconds` | Thời gian API ngừng chấp nhận token revoked | Đo riêng theo API/AS/token profile |

### Hai loại sự cố phải chẩn đoán riêng

**Sự cố A — OP logout nhưng tab RP vẫn dùng được session:**

- Kiểm RP đã đăng ký logout URI đúng chưa.
- Với front-channel, xem browser có tải iframe không, cookie SameSite/third-party restrictions, CSP frame policy và network.
- Với back-channel, kiểm HTTP POST đến RP, JWT validation, mapping issuer/sub/sid, session store và xử lý event trùng.
- Kiểm RP invalidate **session server-side**, không chỉ gửi Set-Cookie xóa cookie một tab.

**Sự cố B — RP logout thành công nhưng access token vẫn gọi API được:**

- Kiểm AS đã revoke access/refresh token hoặc grant đúng policy chưa.
- Kiểm RS dùng JWT offline, introspection cache hay denylist; measured revocation lag có đáp ứng SLO không.
- Xác định token là Bearer hay sender-constrained, audience/scope còn hiệu lực và token đã được attacker copy trước logout hay không.

Không dùng sự thành công của **front/back-channel logout** để kết luận vấn đề **token revocation** đã được giải quyết.

### Nhật ký an toàn

~~~text
GOOD:
  event=oidc_backchannel_logout_processed
  issuer_alias=corporate-op
  rp_client=invoice-web
  result=invalidated
  affected_session_count=1
  correlation_id=<random-id>

BAD:
  logout_token=<raw-jwt>
  sid=<raw-op-session-id> trong metrics công khai
  sub/email/tenant PII trong tracing không có ACL
  refresh_token=<raw-token>
  Authorization: Bearer <raw-access-token>
~~~

## 19. Ma trận kiểm thử front-channel và back-channel

Giả định hệ thống:

~~~text
Issuer OP: https://login.example.test
RP A: invoice-web, https://invoice.example.test
RP B: reports-web, https://reports.example.test
RP session A: S1 (sub=An, OP sid=O1)
RP session B: S2 (sub=An, OP sid=O1)
RP khác user: S3 (sub=Bình, OP sid=O3)
JWT Logout Token: expected aud=invoice-web ở RP A
Invoice API audience: invoice-api
~~~

| Ca kiểm thử | Thiết lập | Kết quả kỳ vọng |
|---|---|---|
| **Front-channel hợp lệ có cookie** | Browser tải URI, RP xác định đúng S1 | Invalidate S1, không xóa S3 |
| **Front-channel thiếu cookie** | Browser chặn third-party cookie | Không xóa hàng loạt từ `sid` tự khai |
| **Front-channel SameSite=Lax** | Cross-site iframe không gửi cookie | Phát hiện giới hạn UX; không báo guaranteed logout |
| **Frame bị CSP chặn** | Browser không tải RP iframe | Phát hiện delivery failure và fallback theo thiết kế |
| **Front-channel query giả** | Attacker gửi `iss`/`sid` | Không dùng query làm proof để xóa session khác |
| **Front-channel GET lặp** | Browser tải URI hai lần | Idempotent, không ảnh hưởng session khác |
| **Front-channel logout CSRF** | Website ngoài nhúng URI như ảnh | Không thể xóa toàn bộ phiên theo query không ký |
| **Front-channel `iss` sai** | Issuer không match session | Không invalidate session tin cậy |
| **Front-channel `sid` sai** | Session ID không thuộc cookie session | Không invalidate session khác |
| **Front-channel network outage** | RP A không phản hồi iframe | RP A có thể còn session; phải có fallback/SLO phù hợp |
| **Back-channel valid JWS** | Signed Logout Token, claims đúng | Invalidate RP session tương ứng |
| **Không có `logout_token`** | POST form thiếu param | Từ chối request, không thay state |
| **Form token lặp** | POST hai `logout_token` | Không dùng một token tùy ý; reject ambiguous request |
| **JWT malformed** | Không đủ cấu trúc JWT/JWE | Từ chối |
| **JWT alg=none** | Unsigned logout token | Từ chối |
| **JWT ký bằng attacker key** | `kid` trông đúng nhưng key lạ | Từ chối, không fetch JWKS từ token-supplied URL |
| **JWT OP key rotation** | Chữ ký key mới trong trusted JWKS | Thực hiện trusted refresh/verify theo policy |
| **`iss` không khớp** | Logout Token từ issuer khác | Từ chối |
| **`aud` hướng tới RP B** | RP A nhận token `aud=reports-web` | Từ chối dù chữ ký hợp lệ |
| **Thiếu `iat`** | Logout Token không có thời điểm | Từ chối |
| **`iat` quá cũ** | Replay sau policy window | Từ chối/reconcile theo thiết kế |
| **`iat` tương lai bất thường** | Vượt clock skew | Từ chối |
| **Thiếu `jti`** | Không định danh event | Từ chối |
| **Duplicate `jti`** | OP retry cùng token | Idempotent, không double-invalidate |
| **Thiếu `events`** | Không có backchannel-logout marker | Từ chối |
| **Sai event URI** | `events` chứa event loại khác | Từ chối |
| **`events` value sai** | Value không đúng JSON object theo profile | Từ chối |
| **Có `nonce`** | Logout Token chứa nonce | Từ chối theo profile |
| **Thiếu cả `sub` và `sid`** | Không xác định user/session | Từ chối |
| **Chỉ có `sid`** | Session-specific event hợp lệ | Invalidate đúng session O1 của issuer |
| **Chỉ có `sub`** | OP gửi subject-wide logout | Invalidate các sessions đúng issuer+subject theo policy |
| **Session-required thiếu sid** | RP registration yêu cầu sid | Từ chối event không đủ thông tin |
| **Cả `sub`/`sid` mâu thuẫn** | sid O1 thuộc An, sub=Bình | Không invalidate session nào; alert |
| **Issuer trùng sub khác user** | OP-A và OP-B đều dùng sub=42 | Không cross-issuer invalidate |
| **No matching session** | RP session đã hết hạn | Safe no-op và audit theo policy |
| **RP chết sau khi nhận event** | Invalidate chưa commit | Retry không bị mất do mark jti trước session |
| **Hai node RP xử lý cùng event** | Concurrent delivery | Atomic idempotency, không xóa session ngoài scope |
| **JWT access token vẫn hợp lệ** | RP logout, RS offline kiểm chữ ký | Đo tồn tại acceptance tới expiry nếu không revoke state |
| **Opaque access token revoked** | RS introspection active=false | RS từ chối |
| **Replay bearer token** | Attacker copy access token trước logout | Logout token không ngăn bearer reuse nếu RS không revoke |
| **Logout vs new login race** | OP gửi event muộn sau user có session mới | Mapping sid/generation không xóa nhầm session mới |
| **401 từ introspection AS** | RS credential lỗi | Fail closed; không coi RP logout làm token active |
| **Log/telemetry** | Kiểm HTTP logs, APM, errors | Không có raw logout_token/access/refresh token |

### Test concurrency mà unit test tuần tự dễ bỏ sót

~~~text
T0: OP gửi event J1 cho session S1.
T1: RP-1 bắt đầu validate J1.
T2: RP-2 cũng nhận J1 do OP retry.
T3: RP-1 invalidate S1, mark J1 consumed.
T4: RP-2 kiểm jti đã xử lý, kết thúc idempotent.

Assert:
  S1 inactive.
  S2/S3 unaffected unless same target scope.
  jti processed exactly once as a state transition.
  No path can mark J1 done but leave S1 active due crash.
~~~

## 20. Bài tập tình huống: browser chặn iframe, OP gửi lại Logout Token

An dùng cùng OP để đăng nhập Invoice Web và Report Portal. OP kết thúc SSO và cố dùng front-channel để thông báo, nhưng Safari/trình duyệt bảo vệ quyền riêng tư chặn third-party cookies trong iframe. Sau đó OP gửi back-channel notification cho Invoice Web, nhưng request đầu timeout.

**Câu 1. OP đã logout SSO thì có chắc Invoice Web và Report Portal cùng logout không?**

**Không.** OP kết thúc phiên OP; các RP chỉ logout khi nhận và xử lý notification, hoặc có chính sách session expiry/revalidation riêng. Front-channel có thể không xác định được session do cookie bị chặn.

**Câu 2. RP có thể lấy `sid` từ query front-channel, tìm tất cả session có sid đó rồi xóa không?**

**Không được tin query tùy ý làm bằng chứng xác thực.** Nếu không có browser session context phù hợp, cần back-channel đã ký hoặc cơ chế bảo vệ khác; không biến endpoint GET thành công cụ logout DoS.

**Câu 3. Back-channel request đầu đã vô hiệu S1 nhưng OP timeout, rồi retry cùng `jti` thì sao?**

RP nên trả kết quả idempotent cho event đã xử lý, **không** xóa thêm sessions ngoài scope và không làm thất bại chỉ vì notification trùng.

**Câu 4. Nếu RP lưu “J1 processed” trước khi cập nhật session và crash giữa hai thao tác?**

Đó là lỗi: OP retry sẽ bị bỏ qua dù S1 vẫn active. Dedupe và invalidation cần atomic hoặc một mô hình có retry/recovery đáng tin.

**Câu 5. RP A nhận JWT có chữ ký OP đúng nhưng `aud=reports-web`. Có được xử lý không?**

Không, vì Logout Token được phát cho **RP B**, không cho RP A. Phải kiểm audience đúng client registration của endpoint.

**Câu 6. Event có `sub=An` và `sid=O2`, nhưng session O2 thuộc Bình. Có được chọn sub hoặc sid để xóa?**

Không. Hai định danh mâu thuẫn; RP phải từ chối/không áp event để tránh xóa sai tài khoản và điều tra mapping.

**Câu 7. Sau khi RP A invalidate S1, token bearer A1 bị attacker sao chép có thể còn dùng tại Invoice API không?**

Có thể, đặc biệt khi RS kiểm JWT offline và `exp` còn thời hạn. Logout notification không thay token revocation ở AS và kiểm trạng thái revoke tại RS.

**Câu 8. Nếu Report Portal dùng `sub` từ issuer khác trùng `sub` của An thì sao?**

Không được gộp. Subject phải được phân biệt theo **`issuer + sub`**; event của OP-A không xóa session thuộc OP-B.

**Câu 9. Front-channel có cần mở CORS “*” để browser tải iframe không?**

Không. CORS không phải công cụ chứng thực logout URI và không giải quyết third-party cookie blocking. Cần hiểu browser navigation/embedding, cookie attributes và frame policy đúng context.

**Câu 10. Nếu sản phẩm hứa “Đăng xuất mọi thiết bị ngay lập tức”, chỉ dùng hai logout protocols có đủ không?**

Không. Cần xác định phạm vi OP/RP sessions, multi-device coverage, revocation refresh/access grants, khả năng RS chặn token đã cấp, sự kiện chưa delivery và **SLO đo được**.

## 21. Checklist triển khai OIDC logout trong production

1. **Phân biệt phạm vi:** Hệ thống có định nghĩa rõ local RP logout, OP SSO logout, federated RP notifications và OAuth token revocation?
2. **Registration đúng profile:** `frontchannel_logout_uri`/`backchannel_logout_uri`/`*_session_required` đã được OP/RP đồng ý; discovery metadata khớp?
3. **Endpoint HTTPS và trust:** Logout URI là endpoint RP kiểm soát, không mở redirect/SSRF, không cho caller tự thay issuer/JWKS?
4. **Front-channel hạn chế được ghi rõ:** Browser iframe, third-party cookies, SameSite và CSP có thể làm notification không tới hoặc thiếu session cookie?
5. **Front-channel không tin query như chữ ký:** `iss`/`sid` qua GET được kiểm context, không thể xóa session khác chỉ bằng giá trị tự khai?
6. **Tách local/logout notification endpoints:** `POST /logout` cho user với CSRF protection; `GET frontchannel` riêng; `POST backchannel` có JWT validation?
7. **Back-channel đúng HTTP format:** OP gửi form `logout_token` tới registered backend endpoint, có giới hạn request size/content type?
8. **JWT verify thực sự:** Chữ ký/alg/key từ OP trusted, không nhận `alg=none` hay `jku`/JWKS do token tự chọn?
9. **Các claims bắt buộc:** Kiểm `iss`, `aud`, `iat`, `jti`, `events` đúng schema?
10. **Định danh session:** Ít nhất `sub` hoặc `sid`; nếu registration yêu cầu `sid` thì không chấp nhận thiếu?
11. **Không có `nonce`:** Logout Token bị từ chối nếu có nonce; không nhầm với ID token hoặc access token?
12. **Tính nhất quán `sub`/`sid`:** Khi cả hai có mặt, RP bảo đảm chúng chỉ cùng session/subject đã được xác minh?
13. **Issuer/tenant isolation:** Subject và OP sid được index cùng issuer, RP client/tenant context; không xóa chéo nhiều OP/users?
14. **Dedupe và atomicity:** `jti` chống xử lý trùng/replay, session invalidation và event marking không mất do crash/race giữa replicas?
15. **Sự kiện tới trễ:** `iat` window, `exp` nếu có, session generation và mapping sid không khiến user vừa login lại bị logout nhầm?
16. **Delivery/availability:** OP/RP có retry, audit, monitoring, TTL/fallback và reconciliation phù hợp khi notification thất bại?
17. **Phiên thực sự bị vô hiệu:** Backend RP session store từ chối session handle cũ, không chỉ xóa cookie UI/browser?
18. **Token lifecycle xử lý riêng:** Refresh token/grant có bị revoke theo policy? Access token bị RS từ chối đúng revocation SLO?
19. **JWT/opaque được phân biệt:** JWT RS offline có thể còn hợp lệ tới `exp`; opaque/introspection phụ thuộc cache và AS availability?
20. **Không lộ tokens trong log:** Raw `logout_token`, ID/access/refresh token và `sid` nhạy cảm không đưa vào URL logs, APM, metrics labels hoặc ticket?
21. **Thử nghiệm trình duyệt thực tế:** Kiểm third-party cookie blocking, Safari/Firefox/Chrome privacy modes, CSP frame-ancestors và SameSite theo target environment?
22. **Kiểm thử đường lỗi:** Wrong issuer/audience, missing events, invalid signature, nonce, missing sid, replay, multi-device, concurrent logout và AS outage?

**Ghi nhớ:** **Front-channel logout truyền thông báo qua browser, thường bằng GET/iframe, nên phụ thuộc cookie và chính sách user agent; `iss`/`sid` trên URL không phải chữ ký. Back-channel logout dùng một Logout Token JWT do OP phát, gửi POST server-to-server, RP phải xác minh `iss`/`aud`/`iat`/`jti`/`events`, ít nhất một `sub` hoặc `sid`, và không có `nonce` trước khi invalidate chính xác session.** Cả hai cơ chế có mục tiêu chính là **kết thúc RP session**; **revocation access/refresh token, việc RS ngừng nhận JWT/opaque token và phạm vi “logout mọi thiết bị” vẫn cần kiến trúc, kiểm tra và SLO riêng**.

### Chuẩn và tài liệu tham khảo

- **OpenID Connect Front-Channel Logout 1.0:** `frontchannel_logout_uri`, `frontchannel_logout_session_required`, browser/iframe notifications và issuer/session correlation.
- **OpenID Connect Back-Channel Logout 1.0:** `backchannel_logout_uri`, `backchannel_logout_session_required`, Logout Token JWT, `events`, `iss`, `aud`, `iat`, `jti`, `sub`/`sid` và điều kiện vắng `nonce`.
- **OpenID Connect RP-Initiated Logout 1.0:** `end_session_endpoint`, `id_token_hint`, `post_logout_redirect_uri` và `state` khi RP yêu cầu OP đăng xuất.
- **OpenID Connect Session Management 1.0:** một cơ chế riêng liên quan việc theo dõi session ở OP/RP.
- **OpenID Connect Core 1.0:** ID token/issuer/subject/audience validation và cách RP gắn session với OP authentication.
- **RFC 7009 — OAuth 2.0 Token Revocation:** token/grant revocation endpoint; khác tín hiệu OIDC logout và HTTP 200 không phải RS revocation acknowledgement.
- **RFC 7662 — OAuth 2.0 Token Introspection:** `active` và giới hạn độ trễ revoke khi Resource Server cache introspection.
- **RFC 6749 — The OAuth 2.0 Authorization Framework:** access token, refresh token, OAuth clients, AS và grants.
- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** rủi ro token bị sao chép và sử dụng lại.
- **RFC 7519 — JSON Web Token (JWT):** JWT time/issuer/audience/id claims và yêu cầu validation liên quan.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** token theft/replay mitigation, refresh token protection và security boundaries.
- **RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP):** sender-constrained access tokens khác với OIDC logout signaling.
- **RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens:** certificate-bound access token enforcement.
- **Spring Security Reference — OAuth2 Login, Logout, OIDC Logout:** session invalidation, CSRF và các tích hợp logout được framework/phiên bản hỗ trợ.
- **OWASP Session Management Cheat Sheet và OAuth 2.0 Cheat Sheet:** browser session/logout, cookie isolation, token storage, incident response và least privilege.
