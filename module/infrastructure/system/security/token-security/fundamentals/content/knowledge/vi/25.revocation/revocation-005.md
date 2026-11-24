# Logout và revocation khác nhau

Người dùng An đăng nhập một ứng dụng web bằng OpenID Connect (OIDC), rồi nhấn **Đăng xuất**. Ứng dụng xóa cookie phiên và chuyển về trang chủ. Tuy nhiên, một access token đã bị sao chép từ trước vẫn có thể gọi API cho tới khi token hết hạn; một refresh token trên thiết bị khác có thể tiếp tục xin access token; và phiên Single Sign-On (SSO) tại Identity Provider cũng có thể vẫn hoạt động.

Tình huống này cho thấy **logout (đăng xuất)** và **token revocation (thu hồi token)** là **hai cơ chế khác nhau**. Chúng có thể được phối hợp để thực hiện mục tiêu “đăng xuất an toàn”, nhưng không được đánh đồng:

- **Logout** chủ yếu kết thúc **phiên đăng nhập (session)** hoặc trạng thái xác thực của người dùng tại một hay nhiều bên như Relying Party (RP) và OpenID Provider (OP).
- **Revocation** là hành động khiến **token hoặc grant** không còn được Authorization Server (AS) chấp nhận theo chính sách, điển hình qua **OAuth 2.0 Token Revocation (RFC 7009)**.
- **Resource Server (RS)** chỉ từ chối access token bị thu hồi khi **cơ chế kiểm tra của RS biết và thực thi trạng thái đó**. Với JWT offline, thay đổi tại AS không tự lan tới mọi RS ngay lập tức.

Bài **“Logout và revocation khác nhau”** thuộc chương **Revocation** của module **Security Token Security Fundamentals**. Mục tiêu là phân biệt chính xác phiên trình duyệt, phiên SSO, access/refresh token, JWT/opaque token, OAuth 2.0/OIDC, phạm vi thu hồi và chống sử dụng lại token sau khi người dùng đã đăng xuất.

## 1. Bốn đối tượng thường bị gọi chung là “phiên đăng nhập”

| Đối tượng | Ví dụ | Được lưu ở đâu? | Hành động làm nó hết hiệu lực |
|---|---|---|---|
| **Phiên ứng dụng (RP session)** | Session ID trong cookie `app_session` | Browser giữ cookie; backend giữ session | Invalidate session server-side, xóa cookie đúng thuộc tính |
| **Phiên SSO tại OP/IdP** | Cookie đăng nhập ở `login.example.test` | Browser và OP | OP logout theo cơ chế/khả năng được hỗ trợ |
| **OAuth access token** | JWT hoặc opaque token để gọi Invoice API | Client, BFF hoặc runtime; được RS nhận | Hết `exp`, AS/RS revoke/denylist/introspection hoặc policy khác |
| **OAuth refresh token** | Credential xin access token mới | Client/BFF/thiết bị, lưu an toàn | Hết hạn, revoke, rotation/reuse detection hoặc grant invalidation |

Ngoài ra có thể có **remember-me cookie**, phiên ở nhiều thiết bị, phiên tại các RP khác nhau và các authorization grants khác nhau.

**Một thao tác UI tên “Đăng xuất” không mặc nhiên xóa được mọi đối tượng trong bảng.** Ứng dụng phải định nghĩa rõ phạm vi hành vi và thực hiện từng bước có thể kiểm chứng.

### Thuật ngữ cần phân biệt

- **RP (Relying Party):** ứng dụng dùng OIDC để xác thực người dùng.
- **OP (OpenID Provider):** hệ thống xác thực/SSO, thường cùng vai trò AS phát token.
- **AS (Authorization Server):** phát token OAuth và có thể hỗ trợ revocation/introspection.
- **RS (Resource Server):** API nhận access token; phải tự kiểm token và quyền.
- **Grant:** quyền ủy quyền được AS quản lý, từ đó có thể phát access/refresh token.
- **Local logout:** chỉ kết thúc phiên ở **một ứng dụng**.
- **Federated/single logout:** cố gắng kết thúc các phiên liên quan qua nhiều RP/OP.
- **Revocation:** thay đổi trạng thái token/grant do AS quản lý, và cần cơ chế để RS nhận biết.

## 2. So sánh nhanh: logout, revoke token, revoke grant

| Thuộc tính | Local logout | OIDC OP/federated logout | OAuth token revocation |
|---|---|---|---|
| **Mục tiêu trực tiếp** | Kết thúc RP session | Kết thúc/đồng bộ trạng thái phiên tại OP và/hoặc các RP | Vô hiệu một token hoặc token/grant liên quan theo policy AS |
| **Đối tượng quản lý** | Session store, cookie ứng dụng | OP session, RP session, logout notification | AS token/grant store, revocation state |
| **Chuẩn thường gặp** | Cơ chế session/framework ứng dụng | OIDC RP-Initiated Logout, Front-Channel Logout, Back-Channel Logout | **RFC 7009** |
| **Có cần browser?** | Thường có nhưng backend có thể invalidate | RP-initiated/front-channel cần điều hướng browser; back-channel là server-to-server | Không nhất thiết; thường POST server-to-server |
| **Có tự xóa access token đã cấp?** | **Không** | **Không được mặc định** | Chỉ theo loại token/phạm vi revoke, khả năng AS và cơ chế kiểm RS |
| **Có tự xóa mọi phiên trên thiết bị khác?** | **Không** | Phụ thuộc phạm vi session/OP, RP tham gia và delivery | Phụ thuộc grant/token family và policy |
| **Chống bearer token bị đánh cắp ngay lập tức?** | **Không** | **Không tự bảo đảm** | Chỉ khi RS kiểm được trạng thái revoke kịp thời |

### Ba câu hỏi phải hỏi khi thiết kế nút “Đăng xuất”

1. **Kết thúc phiên nào?** Chỉ tab/thiết bị này, toàn bộ phiên RP, phiên OP SSO hay mọi thiết bị?
2. **Thu hồi token nào?** Refresh token hiện tại, cả refresh-token family, access token đã cấp hay toàn bộ grant?
3. **Bao lâu các RS ngừng chấp nhận access token?** Ngay nhờ introspection/denylist/event, sau TTL cache, hay chờ JWT `exp`?

Nếu không có câu trả lời rõ, lời hứa “đăng xuất khỏi tất cả thiết bị ngay lập tức” rất dễ sai.

## 3. Mô hình tin cậy trước và sau logout

Giả sử Finance Web dùng **Backend For Frontend (BFF)**:

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant B as Browser
    participant RP as Finance Web / BFF
    participant OP as OpenID Provider / AS
    participant RS as Payment API
    U->>B: Mở ứng dụng đã đăng nhập
    B->>RP: Cookie RP session
    RP->>RS: Bearer access token A1
    RS-->>RP: Dữ liệu được phép
    U->>B: Nhấn Đăng xuất
    B->>RP: POST /logout + bảo vệ CSRF
    RP->>RP: Invalidate session, dọn token khỏi storage
    opt AS hỗ trợ và policy yêu cầu
        RP->>OP: POST /revoke refresh token R1 (RS client auth)
        OP->>OP: Thu hồi R1/grant theo policy
    end
    RP-->>B: Xóa cookie RP, redirect/trả response
    Note over B,OP: Phiên OP SSO có thể vẫn còn
    Note over RP,RS: A1 có thể vẫn được RS chấp nhận đến khi hết hạn hoặc RS biết revoke
~~~

Trong sơ đồ, request `/revoke` do BFF gửi tới AS **không phải bước bắt buộc của mọi local logout**. Khi ứng dụng cam kết thu hồi refresh token, nó phải thật sự thực hiện yêu cầu đó và xử lý kết quả. Client không nên báo **“đã thu hồi token ở mọi API”** khi chỉ mới xóa cookie.

### Phân biệt nguồn sự thật

~~~text
RP session store:
  session S1 = invalidated

OP session store:
  SSO session O1 = active (nếu chưa OP logout)

AS grant/token store:
  refresh token R1 = active/revoked theo từng bước

Payment API:
  access token A1 = accepted/rejected theo kiểm JWT/introspection/cache
~~~

Các trạng thái này **có thể khác nhau trong một khoảng thời gian**. Thiết kế cần nêu rõ “eventual consistency” và thời gian thu hồi tối đa chấp nhận được cho từng API.

## 4. Local logout: kết thúc session ứng dụng

Một local logout đúng nghĩa thường gồm:

1. Xác định **phiên của user hiện tại** qua session cookie/request đã được xác thực.
2. **Vô hiệu session server-side**; không chỉ xóa cookie trong browser.
3. Xóa cookie phiên bằng đúng **`Name`, `Path`, `Domain`** đã được sử dụng; kết hợp `Secure`, `HttpOnly`, `SameSite` theo kiến trúc.
4. Xóa/dừng trạng thái client-side nhạy cảm (in-memory token, pending OAuth transaction, SDK login state) **trong phạm vi kiểm soát được**.
5. Nếu có token/grant cần thu hồi theo chính sách, thực hiện **revocation** độc lập với bước session invalidation.
6. Thông báo phạm vi thực sự đã hoàn tất và điều kiện nào vẫn đang chờ.

### Chỉ xóa cookie không đủ

~~~http
HTTP/1.1 200 OK
Set-Cookie: app_session=; Max-Age=0; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Header trên chỉ **yêu cầu browser xóa cookie với thuộc tính phù hợp**; nếu backend vẫn chấp nhận session ID cũ từ một bản sao đã bị đánh cắp, logout không thực sự kết thúc phiên. Server session phải bị invalidate; nếu dùng session cookie stateless JWT tự xác minh, cần thiết kế thời hạn ngắn hoặc blacklist/session version để bảo đảm logout sớm hơn `exp`.

**Xóa cookie chỉ có tác dụng trong phạm vi browser/domain liên quan.** Ứng dụng A không thể tùy tiện xóa cookie `HttpOnly` của OP trên domain B bằng JavaScript.

### Bảo vệ CSRF và logout endpoint

Thao tác logout làm đổi trạng thái phiên. Nên dùng **POST có bảo vệ CSRF thích hợp** khi browser dùng cookie/session, thay vì GET chỉ cần ảnh/link là tự đăng xuất. XSS có thể điều khiển ứng dụng trong origin hiện tại, nên còn cần chống script injection, CSP phù hợp và quản lý session.

Nếu phiên đã bị invalidate, kết quả logout có thể idempotent về mặt UX (gọi lại vẫn ở trạng thái đã đăng xuất), nhưng **không được coi mọi HTTP 200 là đã revoke token tại AS**.

### Đăng nhập lại sau local logout

Nếu **OP SSO session** vẫn còn, mở lại OIDC authorization flow có thể đưa user về RP **không cần nhập lại mật khẩu**, vì OP vẫn công nhận SSO cookie. Đây không nhất thiết là lỗi: local logout và OP logout là hai phạm vi khác nhau. Nếu yêu cầu “logout cả IdP” hoặc “reauthentication bắt buộc”, ứng dụng phải dùng cơ chế OIDC/OP và policy thích hợp, không chỉ xóa RP cookie.

## 5. OAuth 2.0 Token Revocation theo RFC 7009

**RFC 7009** định nghĩa **token revocation endpoint** mà client được phép gọi để yêu cầu AS vô hiệu token.

Ví dụ BFF/confidential client gửi request:

~~~http
POST /oauth2/revoke HTTP/1.1
Host: auth.example.test
Authorization: Basic <redacted-client-credential>
Content-Type: application/x-www-form-urlencoded

token=<percent-encoded-refresh-token>&token_type_hint=refresh_token
~~~

| Tham số | Yêu cầu | Ý nghĩa |
|---|---|---|
| **`token`** | **Bắt buộc** | Token client muốn thu hồi, được URL-encode trong form body |
| `token_type_hint` | Tùy chọn | Gợi ý `access_token` hoặc `refresh_token` để AS tra cứu; **không phải proof** |
| Client authentication | Theo client registration/AS policy | Xác minh client được phép revoke token, không dùng `client_id` công khai thay secret |

Một AS hỗ trợ confidential clients phải áp dụng client authentication và kiểm token thuộc client/grant mà caller có quyền revoke. Không để **một public client biết chuỗi token của client khác** tùy tiện thu hồi grant của nạn nhân mà không theo security policy.

### Response thành công có thể là HTTP 200 với body rỗng

~~~http
HTTP/1.1 200 OK
Cache-Control: no-store
~~~

Theo RFC 7009, server trả **HTTP 200** cho yêu cầu thu hồi được chấp nhận ngay cả khi token đưa vào **không hợp lệ/không tồn tại**, tránh tạo token-validity oracle. Vì vậy:

- **HTTP 200 không chứng minh token trước đó từng tồn tại**.
- **HTTP 200 không chứng minh mọi access token ở các Resource Server đã lập tức không dùng được**.
- Thao tác revoke lặp lại một token thường có thể được client xử lý **idempotently** về mục tiêu.
- Lỗi authentication của client, token type không được hỗ trợ hoặc lỗi vận hành vẫn cần xử lý riêng.

Nếu token type cần revoke không được AS hỗ trợ, RFC 7009 có error `unsupported_token_type`. Không coi mọi lỗi 4xx/5xx là thành công.

### Revocation khác OAuth introspection

~~~text
POST /revoke:
  "Hãy vô hiệu token/grant này theo chính sách."

POST /introspect:
  "Token này hiện active không, có claims gì tôi được thấy?"

GET/POST protected API:
  "Đây là access token; tôi có quyền thực hiện hành động này không?"
~~~

Revocation là **write/change** tại AS; introspection là **read/check** để RS biết token còn active không theo AS. RS vẫn kiểm audience, scope, issuer và quyền dữ liệu.

## 6. Revoke refresh token và access token không đối xứng

Một refresh token thường có thể phát **nhiều access token** qua thời gian. Khi revoke một token, chính sách ảnh hưởng đến token khác phải được thiết kế rõ.

~~~text
Authorization grant G1
    |
    +-- Refresh token R1
    |      |
    |      +-- Access token A1
    |      +-- Access token A2
    |
    +-- Refresh token R2 sau rotation
           |
           +-- Access token A3
~~~

### Nếu revoke refresh token

Sau khi `R1` được AS đánh dấu revoked, token đó **không được dùng tiếp** để xin access token mới. **Các access token đã phát từ cùng grant có bị vô hiệu hóa hay không** phụ thuộc khả năng thu hồi access token của AS và chính sách được triển khai. RFC 7009 nêu rằng khi revoke **refresh token** và AS hỗ trợ revoke access token, AS **SHOULD** cũng vô hiệu access token dựa trên cùng authorization grant.

Không được suy ra “mọi A1/A2/A3 chắc chắn bị mọi RS từ chối ngay” chỉ từ một response HTTP 200. Cần biết cách **RS kiểm revoke**, cache introspection, denylist hay hạn JWT.

### Nếu revoke access token

Khi AS vô hiệu `A1`, việc `R1`/`R2` có bị revoke theo hay không **không phải hành vi bắt buộc đồng nhất ở mọi AS**. RFC 7009 cho phép AS **MAY** thu hồi refresh token tương ứng khi access token bị revoke.

Nếu mục tiêu là **khóa toàn bộ phiên hoặc ngăn cấp token mới**, chỉ revoke một access token **có thể không đủ** nếu refresh token/grant vẫn cho cấp access token khác.

### Refresh token rotation và family

Một AS áp dụng refresh token rotation có thể phát lần lượt `R1 → R2 → R3`, đồng thời phát hiện reuse của token đã tiêu thụ. Khi phát hiện reuse, AS có thể **thu hồi cả refresh-token family/authorization grant** theo policy để hạn chế kẻ đã lấy token dùng song song.

**Không mặc định** việc gọi RFC 7009 với `R2` chắc chắn thu hồi toàn bộ family nếu AS không nêu chính sách này. Tài liệu tích hợp phải chỉ rõ: token cụ thể, token descendants, grant nào, access token đã phát có bị từ chối và mức trễ tối đa.

## 7. Access token JWT và opaque sau revocation

| Kiểu access token | RS kiểm token như thế nào? | Thu hồi “ngay” có được không? |
|---|---|---|
| **Opaque/reference token** | RS gọi AS introspection hoặc cơ chế kiểm trạng thái | Có thể gần thời gian thực, **nếu RS không dùng cache stale quá lâu** và AS state đã được cập nhật |
| **JWT self-contained, offline validation** | RS kiểm signature/JWKS, issuer, audience, `exp`, scope | **Không tự có** real-time revocation; JWT đã phát có thể tiếp tục hợp lệ đến `exp` |
| **JWT + introspection** | RS vừa kiểm token vừa hỏi trạng thái AS theo contract | Có thể từ chối sớm, phụ thuộc introspection cache và availability |
| **JWT + denylist/session version** | RS so `jti`/grant/session version qua state/event đáng tin | Có thể revoke trước expiry nếu mọi RS nhận cập nhật và fail policy đúng |

### Trục thời gian minh họa

~~~text
10:00:00  AS phát JWT access token A1, exp=10:15:00.
10:01:00  Attacker sao chép A1.
10:02:00  Người dùng logout tại Finance Web.
10:02:01  BFF xóa RP session, revoke refresh token R1.
10:02:02  AS ghi revoke thành công.
10:03:00  Attacker gửi A1 đến Payment API.

Nếu Payment API chỉ kiểm JWT offline:
  A1 có thể vẫn được nhận đến 10:15 theo policy.

Nếu Payment API kiểm revocation kịp thời:
  A1 có thể bị từ chối ngay sau khi RS nhận revoke state.
~~~

**Độ trễ thu hồi (revocation propagation lag)** là một yêu cầu kiến trúc đo được, không phải lời hứa do RFC 7009 tự đảm bảo. Hệ thống có thể dùng **access token TTL ngắn**, introspection TTL phù hợp, denylist và sự kiện thu hồi để đáp ứng SLO.

### Xóa access token ở client không xóa bản sao của attacker

~~~text
Browser/BFF delete A1 -> A1 không còn tại client lành tính.
Attacker đã copy A1   -> attacker vẫn giữ A1.
AS revoke A1          -> chỉ có tác dụng khi RS biết và thực thi.
~~~

Với **bearer access token**, ai giữ chuỗi token có thể thử gọi API trong thời hạn token còn được chấp nhận. Nếu cần chống dùng token bị sao chép, xem xét **DPoP (RFC 9449)** hoặc **mTLS certificate-bound token (RFC 8705)**; logout và revocation vẫn có vai trò riêng.

## 8. Thu hồi token sau logout nên diễn ra theo thứ tự nào?

Trong ứng dụng BFF có phiên cookie và lưu refresh token phía server, một quy trình có thể là:

1. **Ghi nhận yêu cầu logout** từ đúng phiên, qua endpoint chống CSRF.
2. **Ngừng cấp các yêu cầu mới** dùng phiên/token đó: invalidate session hoặc đánh dấu logout-in-progress ngay phía server.
3. **Snapshot thông tin revoke được phép dùng** (token handle/credential/issuer) trong khu vực server an toàn trước khi xóa session hoàn toàn.
4. Gửi **RFC 7009 revocation** tới AS nếu chính sách yêu cầu; bảo đảm request được xác thực và target đúng client/token.
5. **Xóa token khỏi storage client/BFF**, cookie và transaction đang chờ; không giữ raw token trong log/job queue.
6. Nếu cần **OP logout**, tiếp tục bước OIDC logout thích hợp và xử lý browser redirect.
7. Ghi kết quả từng bước và trạng thái chưa hoàn tất (nếu revocation chưa xác nhận), không tuyên bố phạm vi rộng hơn thực tế.

### Không có transaction phân tán tự động giữa RP, AS và RS

~~~text
RP session invalidated?     YES
Refresh token revoke?       TIMEOUT / UNKNOWN
OP SSO logout?              NOT REQUESTED
Access token denied by RS?  MAY STILL BE ACCEPTED
~~~

Nếu AS bị lỗi khi revoke, **không khôi phục session RP đã logout** chỉ để chờ retry. Thay vào đó, giữ trạng thái an toàn và sử dụng cơ chế retry/operational remediation bảo vệ credential, có giới hạn, audit và kết quả rõ. Khi dùng task queue để retry, tuyệt đối không đặt **raw refresh token vào queue chung hoặc log không được bảo vệ**.

### “Logout thành công” nên có nghĩa gì?

Hãy định nghĩa ở UX và API:

- **“Đã đăng xuất khỏi ứng dụng này”**: RP session đã invalidated.
- **“Đã yêu cầu thu hồi token”**: revocation request đã được gửi; không đồng nghĩa RS đã cập nhật.
- **“Đã thu hồi quyền truy cập trên mọi thiết bị”**: chỉ được hứa nếu hệ thống thực thi toàn bộ grant/session scope, có xác nhận đủ và SLO đo được.

**Không biến yêu cầu trải nghiệm người dùng thành tuyên bố kỹ thuật không thể bảo đảm.**

## 9. OIDC RP-Initiated Logout: yêu cầu OP kết thúc SSO

**OpenID Connect RP-Initiated Logout 1.0** mô tả cách **Relying Party (RP)** yêu cầu **OpenID Provider (OP)** đăng xuất người dùng tại OP, thường thông qua điều hướng browser đến `end_session_endpoint` được OP công bố.

Ví dụ RP chuyển browser tới:

~~~http
GET /connect/endsession?id_token_hint=<redacted-id-token>&post_logout_redirect_uri=https%3A%2F%2Fapp.example.test%2Flogged-out&state=<random-logout-state> HTTP/1.1
Host: login.example.test
~~~

Đây là **ví dụ minh họa**; endpoint và các tham số được hỗ trợ thực tế theo OP metadata/profile. Trong production, `id_token_hint` là dữ liệu nhạy cảm, có thể chứa thông tin người dùng; cần hạn chế log URL, history và referrer, đánh giá các cơ chế được OP hỗ trợ và rủi ro khi truyền ID token qua query.

| Tham số | Vai trò | Kiểm soát |
|---|---|---|
| `id_token_hint` | Gợi ý cho OP về phiên/client/end user cần logout | RP chỉ dùng ID token lấy từ phiên tin cậy; OP kiểm hợp đồng, không coi hint là lệnh vô điều kiện |
| `post_logout_redirect_uri` | Nơi OP có thể đưa browser về sau logout | Phải được kiểm theo registered URI/policy của OP, tránh open redirect |
| `state` | Cho RP liên kết post-logout response với yêu cầu đã khởi tạo | Dùng giá trị khó đoán gắn transaction; kiểm và consume một lần |
| `client_id` | Giúp OP xác định RP khi cần theo profile | Định danh công khai, không phải bằng chứng client authentication |
| `logout_hint` / `ui_locales` | Gợi ý phiên/UX nếu OP hỗ trợ | Không tự trao quyền xóa phiên của user bất kỳ |

**RP-Initiated Logout là giao thức kết thúc SSO/browser session, không phải yêu cầu RFC 7009 revoke token.** Một OP có thể đăng xuất thành công nhưng access token vẫn được RS offline chấp nhận; ứng dụng cần quyết định riêng việc revoke refresh/access token.

### Logout tại OP rồi có tự đăng xuất các RP khác không?

**Không mặc nhiên.** Để các RP khác cùng biết và kết thúc session, OP và các RP cần hỗ trợ các cơ chế **front-channel/back-channel logout** tương ứng hoặc chính sách phiên tập trung. Một RP không tích hợp sẽ không tự biết OP đã logout.

### Redirect sau logout phải có allowlist

~~~text
Registered post_logout_redirect_uri:
  https://app.example.test/logged-out

Unsafe:
  https://attacker.invalid/capture
  https://app.example.test.evil.invalid/logged-out
  https://app.example.test/redirect?next=https://attacker.invalid
~~~

Không dùng wildcard host hoặc tham số `next` mở ra domain bất kỳ. Cần tránh kẻ tấn công lợi dụng luồng logout làm open redirect hoặc điều hướng người dùng sang trang giả.

## 10. OIDC Front-Channel Logout: thông báo qua trình duyệt

**OpenID Connect Front-Channel Logout 1.0** cho phép OP dùng browser user agent để thông báo logout tới các RP đã đăng ký, thường bằng cách tải những **front-channel logout URIs** trong iframe hoặc cơ chế điều hướng được profile quy định.

~~~mermaid
sequenceDiagram
    autonumber
    participant B as Browser
    participant OP as OpenID Provider
    participant A as RP A
    participant C as RP C
    B->>OP: User thực hiện OP logout
    OP->>OP: Kết thúc OP SSO session
    OP-->>B: Trang logout dùng front-channel notifications
    B->>A: GET frontchannel_logout_uri (nếu browser thực hiện được)
    B->>C: GET frontchannel_logout_uri (nếu browser thực hiện được)
    A->>A: Xác định đúng RP session và invalidate
    C->>C: Xác định đúng RP session và invalidate
~~~

### Hạn chế quan trọng

- Browser có thể **chặn third-party cookies/iframes**, tracking prevention hoặc mất mạng; thông báo front-channel **không bảo đảm tới mọi RP**.
- Cookie RP có thể không được gửi trong iframe, khiến RP không biết session nào cần kết thúc.
- Việc dùng `iss`/`sid` trong thông báo, nếu profile hỗ trợ, phải được kiểm với **OP và session binding được tin cậy**; URL query do browser mang theo không phải bằng chứng mật mã tự đủ.
- Mỗi RP phải thiết kế xử lý logout idempotent, không chấp nhận request GET mù quáng xóa mọi session chỉ vì có query tự khai.
- **Không dùng front-channel làm cơ chế revocation duy nhất** khi hệ thống đòi thu hồi access token nhanh và chắc.

Front-channel phù hợp với nhiều trường hợp UX federated logout, nhưng **mức bảo đảm delivery và tính toàn vẹn khác back-channel logout**.

## 11. OIDC Back-Channel Logout: server-to-server và logout token

**OpenID Connect Back-Channel Logout 1.0** cho phép OP gửi **logout token** tới endpoint backend RP đã đăng ký mà **không phụ thuộc vào browser iframe**. Logout token là **JWT dạng security event**, **không phải access token để gọi API** và không phải refresh token.

### Luồng minh họa

~~~mermaid
sequenceDiagram
    autonumber
    participant U as Người dùng
    participant OP as OpenID Provider
    participant RP as Finance RP
    U->>OP: Đăng xuất SSO
    OP->>OP: Xác định RP sessions liên quan
    OP->>RP: POST backchannel_logout_uri với logout_token JWT
    RP->>RP: Kiểm signature, iss, aud, iat, jti, events và sub/sid
    RP->>RP: Tìm đúng session(s), invalidate idempotent
    RP-->>OP: HTTP acknowledgement theo profile
~~~

### Payload logout token minh họa

~~~json
{
  "iss": "https://login.example.test",
  "aud": "finance-web",
  "iat": 1800000000,
  "jti": "logout-event-unique-id-01",
  "events": {
    "http://schemas.openid.net/event/backchannel-logout": {}
  },
  "sub": "user:an",
  "sid": "op-session-789"
}
~~~

Đây là **JWT payload minh họa, chưa có chữ ký**. Theo OIDC Back-Channel Logout, logout token phải có những claims cần thiết như `iss`, `aud`, `iat`, `jti`, `events` với đúng event identifier; **`sub` hoặc `sid` phải có ít nhất một** để RP xác định phiên phù hợp. Logout token **không được có `nonce`**; nó khác ID token và không dùng thay access token.

**Không suy rằng `sid` là session ID cookie của RP**: `sid` do OP phát biểu diễn session theo profile; RP cần lưu mapping giữa `iss`, `sub`/`sid` và **session nội bộ** khi đăng nhập.

### Kiểm logout token trước khi hành động

1. **Xác minh chữ ký/alg/JWKS** từ OP đã đăng ký; không nhận unsigned JWT hoặc khóa tự khai từ token.
2. Kiểm **`iss` chính xác** với trusted OP và `aud` chứa **client ID của RP**; kiểm `iat` theo cửa sổ cho phép.
3. Kiểm `jti` chưa được xử lý; **chống replay** bằng lưu event identifier trong TTL phù hợp, không invalidate rộng hơn scope khi trùng.
4. Kiểm cấu trúc `events` có **`http://schemas.openid.net/event/backchannel-logout`** với giá trị đúng profile, và **không có `nonce`**.
5. Kiểm **`sub` và/hoặc `sid`**, mapping tới session tương ứng; không xóa tất cả users chỉ vì thiếu mapping.
6. Thực hiện invalidate đúng RP session(s), dọn token phía RP theo policy; trả acknowledgement **không chứa token/PII**.
7. Nếu cần thu hồi refresh token, triển khai thêm RFC 7009 hoặc cơ chế token/grant tại AS theo contract; **back-channel logout token không tự là yêu cầu revoke access token tại mọi RS**.

### Back-channel không phải bảo đảm delivery tuyệt đối

OP có thể retry, RP có thể downtime hoặc kết nối server-to-server thất bại. Vì vậy endpoint RP cần **idempotent, retry-safe, logging/audit và khả năng phục hồi**. Một back-channel notification chưa tới không nên làm RP tin rằng user vẫn còn được đăng nhập an toàn vô thời hạn nếu session security policy yêu cầu freshness; cần session TTL, heartbeat hoặc cơ chế kiểm trạng thái phù hợp.

## 12. Logout một thiết bị, mọi thiết bị và mọi ứng dụng

Một người dùng có thể đang có:

~~~text
User An:
  Phone -> App A, session SA, refresh token RA
  Laptop -> App A, session SB, refresh token RB
  Tablet -> App B, session SC, refresh token RC
  Browser at OP -> OP SSO session O1
~~~

### Ba mức phạm vi thường gặp

| Hành động UX | Phạm vi mong muốn | Cần làm rõ |
|---|---|---|
| **Đăng xuất khỏi thiết bị này** | Session/token của một thiết bị hoặc client instance | Không xóa các grant/phiên khác nếu policy không yêu cầu |
| **Đăng xuất khỏi tất cả phiên của App A** | Tất cả session thuộc user tại RP A; các refresh tokens liên quan | Phải có session index/identity binding và grant mapping |
| **Đăng xuất khỏi mọi ứng dụng và thiết bị** | OP SSO + các RP tham gia + grant/tokens theo policy toàn cục | Cần OIDC logout notifications, revocation/session management, coverage và SLO rõ |

Một **refresh token** có thể đại diện một device/session/grant, nhưng mapping **không bắt buộc 1:1** trên mọi AS. Cần xác minh chính sách cấp token và granularity trước khi thiết kế “revoke all sessions”.

### Phạm vi quá rộng cũng có rủi ro

Nếu user chỉ bấm “Đăng xuất trên laptop” mà ứng dụng revoke **mọi grant của tài khoản**, các thiết bị khác có thể bị gián đoạn bất ngờ. Ngược lại, nếu user báo tài khoản bị chiếm và chọn **“Đăng xuất tất cả”**, chỉ xóa cookie hiện tại là không đủ.

**Thông điệp sản phẩm phải khớp biện pháp kỹ thuật**, tránh một nút duy nhất có ý nghĩa mơ hồ.

## 13. Session logout, consent revocation và account disable

Ngoài logout và token revocation còn có các hành động liên quan:

| Hành động | Mục đích | Không được đánh đồng |
|---|---|---|
| **Logout** | Kết thúc một hoặc nhiều phiên đăng nhập | Revoke mọi token đã cấp |
| **Revoke refresh token** | Chặn dùng credential đó để xin access token mới | Access token đang dùng chắc chắn chết ngay |
| **Revoke access token** | Khiến AS/RS từ chối access token cụ thể theo policy | Kết thúc toàn bộ phiên OP SSO |
| **Withdraw consent / revoke grant** | Người dùng/AS rút quyền ủy quyền cho client | Chỉ xóa cookie local |
| **Disable account** | Khóa danh tính/tài khoản vì security/admin policy | Tự lan đến mọi RS JWT offline nếu không có cơ chế |
| **Delete app / remove device** | Không còn client local hoặc loại device khỏi inventory | Token đã bị sao chép không còn ở ngoài thiết bị |

Với hệ thống nhạy cảm, **disable account** có thể yêu cầu **kill active sessions + revoke grants/refresh tokens + cập nhật RS denylist hoặc introspection**. Đây là nghiệp vụ security orchestration lớn hơn một endpoint `/logout`.

### Logout không xóa audit trail

Khi xóa session và token khỏi client, vẫn cần **giữ audit metadata hợp lệ** về đăng nhập, logout, revocation request, kết quả và thời điểm theo chính sách compliance/retention. Không giữ raw access/refresh tokens trong audit; sử dụng opaque event IDs, session IDs đã giảm độ nhạy hoặc token fingerprint có bảo vệ khi cần.

## 14. Revocation latency và cache: tính toán có căn cứ

Giả sử Payment API cache introspection result trong **30 giây**. Một access token vừa được AS revoke vẫn có thể được RS chấp nhận trong cửa sổ cache nếu không có invalidation.

~~~mermaid
sequenceDiagram
    autonumber
    participant AS as Authorization Server
    participant RS as Payment API
    participant X as Bên giữ token A1
    RS->>AS: Introspect A1
    AS-->>RS: active=true, exp=10:15
    RS->>RS: Cache active trong 30 giây
    Note over AS: 10:02: AS revoke A1
    X->>RS: Gọi API bằng A1 trước cache expiry
    RS-->>X: Có thể vẫn chấp nhận nếu cached active còn hợp lệ
    Note over RS: Cache hết hạn hoặc nhận invalidation
    RS->>AS: Introspect A1 lại
    AS-->>RS: active=false
    RS-->>X: Từ chối token
~~~

### SLO minh họa

~~~text
Requirement:
  After emergency account lock, all sensitive APIs reject
  affected access tokens within <= 10 seconds.

Current architecture:
  RS introspection cache TTL = 60 seconds.
  No revoke event/denylist.

Conclusion:
  Architecture cannot claim to satisfy <= 10-second revoke SLO.
~~~

Muốn đáp ứng SLO phải giảm TTL, dùng revocation events/denylist hoặc revalidate theo request và kiểm latency/phân phối nhiều node. **Cache TTL cần được chọn theo yêu cầu thu hồi, không chỉ theo hiệu năng.**

### JWT `exp` và clock skew

Một JWT access token có `exp` 15 phút từ khi cấp sẽ được RS kiểm expiry (kèm skew có giới hạn). Nếu **không có cơ chế thu hồi trước hạn**, revocation SLO về bản chất có thể tới expiry còn lại. Tăng allowed clock skew quá lớn có thể kéo dài acceptance window. Các RS phải thống nhất trusted issuer, audience, token profile, signing keys và revocation policy.

### RS nên ứng xử ra sao khi introspection outage?

Nếu AS không khả dụng:

- RS **không được fail open** và nhận bất kỳ token nào chỉ vì không thể kiểm trạng thái.
- Có thể dùng kết quả introspection **đã cache và còn trong TTL/policy** nếu revoke-lag SLO cho phép.
- Nếu không có dữ liệu hợp lệ, từ chối request hoặc báo `503` theo phân loại lỗi phù hợp, **không tuyên bố user đã bị revoke** khi thực tế AS đang lỗi.
- Với API nhạy cảm hơn, có thể đặt TTL ngắn hoặc yêu cầu kiểm trạng thái trực tiếp.

**Không kéo dài TTL cache `active=true` khi AS outage** nếu điều đó vi phạm security policy hoặc `exp` của token.

## 15. Java/Spring Security: local logout và OIDC logout

Spring Security hỗ trợ **session logout** và có thành phần dành cho **OIDC RP-Initiated Logout**. Dù framework có handler điều hướng đến OP, điều đó **không đồng nghĩa tự động revoke refresh/access token**.

### 15.1. Cấu hình ví dụ Spring Security 6.x

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.oidc.web.logout.OidcClientInitiatedLogoutSuccessHandler;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
@EnableWebSecurity
class OidcLogoutConfiguration {
    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            ClientRegistrationRepository registrations) throws Exception {

        var successHandler =
            new OidcClientInitiatedLogoutSuccessHandler(registrations);
        successHandler.setPostLogoutRedirectUri(
            "{baseUrl}/logged-out");

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/logged-out").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(withDefaults())
            .logout(logout -> logout
                .logoutUrl("/logout")
                .invalidateHttpSession(true)
                .clearAuthentication(true)
                .deleteCookies("JSESSIONID")
                .logoutSuccessHandler(successHandler));

        // Không tắt CSRF cho browser logout dùng session cookie.
        return http.build();
    }
}
~~~

Ví dụ này chỉ minh họa ranh giới **RP session invalidation + OIDC logout redirect**:

- CSRF protection của Spring Security cần được giữ và tích hợp vào form/POST logout. Khi bật CSRF, logout URL thường yêu cầu **POST** theo config/framework; không biến thành GET vô bảo vệ chỉ để link dễ bấm.
- `OidcClientInitiatedLogoutSuccessHandler` cần OIDC client registration và OP cung cấp logout endpoint theo metadata. Không phải OP nào cũng hỗ trợ đầy đủ.
- `{baseUrl}/logged-out` sau expand phải là **post-logout redirect URI được OP cho phép**; không xây từ `Host`/`X-Forwarded-Host` chưa tin cậy.
- `deleteCookies("JSESSIONID")` chỉ là minh họa cookie name mặc định trong một số session stores. Với Spring Session, proxy path/domain hoặc cookie tùy biến, cần cấu hình xóa khớp **tên/path/domain**.
- **Mã trên chưa làm RFC 7009 revocation.** Nếu policy yêu cầu revoke refresh token, phải tích hợp token storage/revocation service an toàn trước khi dọn token.
- Framework filter chain không tự chứng minh Payment API đã dừng chấp nhận JWT A1. RS cần chiến lược revocation riêng.

### 15.2. Phân tách logic logout và revoke bằng interface

Mã Java 17 dưới đây là **mô hình ứng dụng minh họa**, không phải SDK OAuth hoàn chỉnh. Nó cố ý tách ba quyết định: **invalidate RP session**, **gửi revocation request** và **báo lại trạng thái kỹ thuật**.

~~~java
record LogoutSnapshot(
    String rpSessionId,
    String refreshTokenHandle,
    String trustedIssuer,
    String oauthClientRegistration
) {}

interface RpSessionStore {
    // Xác thực session caller và ngăn sử dụng tiếp một cách nguyên tử.
    LogoutSnapshot snapshotAndInvalidate(String rpSessionId);
}

interface RefreshTokenRevocationService {
    // Nhận handle tham chiếu token trong secure token store.
    // Chỉ adapter bên trong đọc token thật để POST /revoke qua HTTPS.
    void revoke(
        String trustedIssuer,
        String oauthClientRegistration,
        String refreshTokenHandle
    ) throws Exception;
}

enum RevocationOutcome {
    NOT_APPLICABLE,
    CONFIRMED_REQUEST,
    FAILED_OR_UNCERTAIN
}

record LogoutOutcome(
    boolean rpSessionInvalidated,
    RevocationOutcome revocation
) {}

final class LogoutCoordinator {
    private final RpSessionStore sessions;
    private final RefreshTokenRevocationService revoker;

    LogoutCoordinator(
            RpSessionStore sessions,
            RefreshTokenRevocationService revoker) {
        this.sessions = sessions;
        this.revoker = revoker;
    }

    LogoutOutcome logout(String rpSessionId) {
        LogoutSnapshot snapshot =
            sessions.snapshotAndInvalidate(rpSessionId);

        // Không dùng raw refresh token làm request ID/log field.
        if (snapshot.refreshTokenHandle() == null) {
            return new LogoutOutcome(
                true, RevocationOutcome.NOT_APPLICABLE);
        }

        try {
            revoker.revoke(
                snapshot.trustedIssuer(),
                snapshot.oauthClientRegistration(),
                snapshot.refreshTokenHandle());

            return new LogoutOutcome(
                true, RevocationOutcome.CONFIRMED_REQUEST);
        } catch (Exception ex) {
            // RP session vẫn bị invalidate, không restore user session.
            // Báo trạng thái uncertainty cho secure operations workflow.
            return new LogoutOutcome(
                true, RevocationOutcome.FAILED_OR_UNCERTAIN);
        }
    }
}
~~~

**Bất biến:** Sau khi `snapshotAndInvalidate` hoàn tất, caller không được tiếp tục dùng RP session dù token endpoint lỗi. Nếu revocation thất bại, hệ thống cần **cơ chế remediation đáng tin** (ví dụ secure operations queue tham chiếu token handle có quyền chặt hoặc cảnh báo vận hành), không thể chỉ trả `FAILED_OR_UNCERTAIN` rồi âm thầm quên token.

**Các giới hạn của ví dụ:**

- `RpSessionStore.snapshotAndInvalidate` phải xác minh phiên thuộc người gọi, atomic invalidation và tạo snapshot thông tin cần revoke theo chính sách. Code chỉ nêu interface, **không triển khai** session store.
- `RefreshTokenRevocationService` phải dùng HTTP form encoding, HTTPS, client authentication và token ownership theo RFC 7009; code không xử lý chi tiết HTTP/OAuth error.
- `CONFIRMED_REQUEST` nghĩa là **AS đã chấp nhận revocation request theo contract**, không chứng minh token từng tồn tại hoặc RS toàn hệ thống đã nhận trạng thái revoke.
- Không log raw refresh/access token, `id_token_hint` hoặc client secret.
- Nếu muốn retry an toàn sau timeout, secure token store phải giữ **token/handle được bảo vệ** đủ để thực hiện retry; không cho session đã logout truy cập lại credential trong thời gian remediation.
- Việc OP logout vẫn phải được điều phối qua OIDC logout flow, không nằm trong interface này.

### 15.3. Revoke token qua HTTP (định dạng minh họa)

~~~http
POST /oauth2/revoke HTTP/1.1
Host: auth.example.test
Authorization: Basic <base64-of-authorized-client-credential-redacted>
Content-Type: application/x-www-form-urlencoded

token=<form-encoded-refresh-token>&token_type_hint=refresh_token
~~~

Không triển khai revoke bằng `GET /revoke?token=...`. Query URL dễ rơi vào browser history, proxy logs, referrer hoặc APM. Một AS cũng có thể áp dụng client authentication `private_key_jwt` hoặc mTLS thay Basic; tuân thủ client registration của hệ thống.

## 16. Những lỗi triển khai có thể khiến “logout” không an toàn

| Sai lầm | Nguy cơ | Cách khắc phục |
|---|---|---|
| Chỉ xóa cookie local | Session server-side hoặc token bị sao chép còn dùng được | Invalidate RP session và xử lý token theo policy |
| Chỉ xóa SPA `localStorage` | Token trong tab khác/attacker đã copy vẫn sống | Storage policy, revoke nếu cần, kiểm RS |
| Chỉ revoke access token A1 | Refresh token còn active có thể xin A2 | Revoke refresh/grant theo mục tiêu |
| Chỉ revoke refresh token R1 | Access token đã cấp có thể còn hợp lệ | Revoke access token/denylist/introspection hoặc TTL ngắn |
| Coi HTTP 200 RFC 7009 là đã “logout mọi nơi” | Quá mức bảo đảm về phạm vi/propagation | Phân biệt request accepted và RS enforcement |
| Không tắt RP session khi revocation timeout | User còn dùng session dù đã bấm logout | Fail-safe local invalidation trước/độc lập revoke |
| Khôi phục session sau lỗi revoke | Logout có thể bị đảo ngược do AS outage | Giữ session invalidated, xử lý remediation riêng |
| Coi OP logout là revoke mọi token | RS vẫn chấp nhận bearer/JWT | Token lifecycle và RS revocation policy riêng |
| Chỉ dùng Front-Channel Logout | Iframe/cookie bị browser chặn | Back-channel/session TTL, kế hoạch fallback |
| Không kiểm logout JWT của back-channel | Attacker gửi sự kiện giả xóa phiên | Verify signature/iss/aud/events/sub/sid/jti/iat |
| Reuse `jti` không được kiểm | Replay logout event, audit không tin cậy | Idempotency và replay protection |
| `post_logout_redirect_uri` mở | Open redirect, phishing sau logout | Allowlist exact URI theo OP registration |
| Dùng GET logout không CSRF | Trang ngoài có thể gây trạng thái logout không mong muốn | POST + CSRF defense phù hợp |
| Đăng xuất 1 thiết bị nhưng revoke mọi grant | Mất phiên ngoài ý muốn | Session/grant binding và UI scope rõ |
| “Logout all devices” chỉ invalidate 1 cookie | Các thiết bị khác tiếp tục hoạt động | Central session index, grant revocation, multi-RP signals |
| JWT `exp` dài, RS chỉ kiểm offline | Token bị đánh cắp dùng tới expiry | TTL ngắn, denylist/introspection hoặc sender-constraining |
| Cache introspection quá lâu | Revoked token tiếp tục được nhận | TTL/invalidation theo revoke SLA |
| Xóa token khỏi log sau incident và coi như đủ | Attacker vẫn giữ bản copy | AS/RS revoke + audit + containment |
| Gộp ID token và access token | Sai audience và token purpose | RP kiểm ID token, RS kiểm access token |
| Dùng cùng logout handler cho mọi issuer không kiểm mapping | Session/token của issuer khác bị ảnh hưởng | Bind issuer, client, sub/sid và session policy |

## 17. Mô hình sự cố: token bị đánh cắp trước logout

Giả sử:

~~~text
10:00  Browser của An đăng nhập Finance Web.
10:01  BFF có access token A1 (Bearer, exp=10:16) và refresh R1.
10:02  Attacker lấy được A1 qua log thiếu redaction.
10:03  An bấm logout tại Finance Web.
10:03  RP session invalidated; refresh token R1 revoked.
10:04  Attacker gọi Payment API bằng A1.
~~~

### Ba kiểu RS enforcement

| Hệ thống Payment API | Kết quả A1 lúc 10:04 |
|---|---|
| JWT offline, chỉ kiểm signature/`exp`, không có revoke state | **Có thể còn được nhận**, nếu các điều kiện quyền khác đạt |
| Opaque/introspection và AS đã revoke A1, RS không cache stale | **Từ chối** khi `active=false` |
| JWT + denylist/event revoke, RS nhận sự kiện kịp thời | **Từ chối** nếu `jti`/grant nằm trong denylist đúng policy |

**Kết luận:** Local logout + revoke refresh token có thể ngăn cấp token mới, nhưng không bảo đảm A1 đã bị chặn ở mọi RS. Đó là lý do các hệ thống nhạy cảm cần **revoke-lag SLO và kiểm thử thực tế**.

### Ứng phó sự cố cần làm gì?

1. Ngăn nguồn rò: redaction access token/Authorization headers, giới hạn APM, bảo vệ logs.
2. Xác định **issuer, token class, client, subject, audience, scope, `exp`** từ nguồn tin cậy và phạm vi ảnh hưởng.
3. Thu hồi token/grant/refresh family tại AS theo khả năng; cập nhật RS revoke state/denylist nếu chính sách yêu cầu.
4. Invalidate session liên quan, có thể OP/back-channel logout nếu account compromise.
5. Kiểm audit API usage và token issuance/reuse, không để lộ thêm raw token trong ticket.
6. Giảm TTL và thu hẹp scope/audience; cân nhắc DPoP/mTLS để giảm tác hại của bearer theft.

**Không dùng `id_token_hint` hoặc JWT payload chưa xác minh để xác định chính xác token nào bị lộ**, và không làm thao tác “revoke all” rộng ngoài policy chỉ vì tên user xuất hiện trong log.

## 18. Ma trận kiểm thử logout và token revocation

Giả định test fixture:

~~~text
OP/AS: https://login.example.test
RP A: Finance Web, client_id=finance-web
RP B: Report Portal, client_id=report-portal
Resource Server: Payment API, aud=payments-api

Browser A:
  RP session S1, OP SSO O1
  refresh token R1
  access token A1 (JWT, expires in 15 minutes)

Phone:
  RP/native app session S2, refresh token R2, access token A2

RS introspection cache TTL (nếu dùng): 30 giây
~~~

| Ca kiểm thử | Tình huống | Kết quả mong đợi |
|---|---|---|
| **Local logout chuẩn** | Browser A gửi POST logout hợp lệ | Session S1 server-side invalidated; cookie hết hiệu lực |
| **Chỉ xóa cookie** | Server session S1 vẫn active | Test phát hiện lỗi: session ID cũ không được chấp nhận |
| **Cookie Path/Domain sai** | Cookie không bị xóa đúng scope | Test fail; sửa matching attributes |
| **Logout CSRF** | Website ngoài gửi GET/POST không có CSRF proof | Không thực hiện logout tùy tiện theo policy browser |
| **Logout lặp lại** | Browser POST logout hai lần | Không phục hồi session; ứng xử idempotent và an toàn |
| **Session theft** | Attacker còn giữ session ID trước logout | Server từ chối session ID cũ sau invalidation |
| **OP SSO vẫn sống** | Chỉ local logout, O1 không bị kết thúc | Re-login có thể dùng OP SSO; UI không hứa global logout |
| **RP-initiated logout** | RP gọi OP logout đúng metadata | OP xử lý SSO theo profile; không tự suy access token đã revoke |
| **Post-logout redirect hợp lệ** | URI đã đăng ký | OP chỉ redirect tới URI hợp lệ |
| **Post-logout redirect lạ** | `https://attacker.invalid` | OP từ chối/không redirect vào host lạ |
| **State logout sai** | Browser quay về với `state` không thuộc transaction | RP không coi response là hoàn tất transaction tin cậy |
| **Front-channel bị block** | Browser chặn iframe/cookie | RP khác có thể chưa logout; session TTL/fallback theo chính sách |
| **Front-channel URL giả** | Attacker gọi endpoint logout với `sid` tự khai | Không invalidate rộng nếu không có session/OP binding hợp lệ |
| **Back-channel JWT hợp lệ** | OP gửi signed logout token đúng issuer/audience/events/sub/sid | RP invalidate các session được chỉ định |
| **Back-channel chữ ký sai** | JWT giả | RP từ chối, không xóa session |
| **Back-channel issuer lạ** | `iss` khác OP đáng tin | RP từ chối |
| **Back-channel audience sai** | `aud` là RP khác | RP từ chối |
| **Back-channel thiếu sub/sid** | Không thể xác định session | RP từ chối theo profile |
| **Back-channel có nonce** | Logout token chứa `nonce` | RP từ chối theo OIDC Back-Channel Logout |
| **Back-channel thiếu events** | Thiếu đúng event identifier | RP từ chối |
| **Back-channel replay** | Cùng `jti` gửi lại | Không mở rộng phạm vi invalidation; xử lý idempotently |
| **Back-channel delivery trễ** | RP downtime rồi nhận notification | Chính sách session state/retry xử lý an toàn, audit đủ |
| **RFC 7009 revoke refresh** | Client hợp lệ gửi R1 | AS chấp nhận yêu cầu, R1 không dùng để refresh tiếp |
| **RFC 7009 revoke unknown token** | Token không tồn tại | HTTP 200 theo RFC, không tiết lộ token tồn tại |
| **RFC 7009 credential sai** | Client không xác thực đúng | AS từ chối client; không coi là revoke thành công |
| **Revoke token client khác** | Client A cố revoke grant của client B | AS áp kiểm quyền/ownership, không cho cross-client abuse |
| **`token_type_hint` sai** | Hint không đúng token thực | AS áp dụng protocol/policy, không dùng hint làm bằng chứng |
| **Refresh token vẫn sống** | Chỉ revoke A1, R1 không bị revoke theo AS policy | R1 có thể còn xin A2; phát hiện thiếu phạm vi revoke |
| **JWT offline sau revoke** | AS revoke A1, RS chỉ kiểm signature/exp | A1 có thể còn được nhận; đánh giá revoke-lag SLO |
| **Opaque + introspection** | AS trả `active=false` | RS từ chối token |
| **Introspection cache stale** | RS đang cache active 30 s | Đo revoke lag; không hứa immediate revocation |
| **Introspection outage** | AS 503, không có cache còn hợp lệ | RS fail closed, không cho qua |
| **Clock skew quá lớn** | RS cho phép JWT quá `exp` | Từ chối; skew policy phải giới hạn |
| **Sender-constrained access token** | Attacker chỉ lấy token string, không có DPoP key/mTLS cert | RS từ chối thiếu proof phù hợp |
| **Logout một thiết bị** | An logout Laptop S1 | S2 chỉ bị ảnh hưởng nếu policy rõ; không revoke chéo nhầm |
| **Logout all devices** | User dùng tính năng toàn cục | Session/grant của mọi thiết bị trong phạm vi được xử lý; đo coverage |
| **Tài khoản bị khóa** | Admin disable user | Phiên, grant, RS state được phối hợp theo incident policy |
| **Revoke timeout** | RP invalidate session, AS timeout | Session vẫn invalidated; revocation báo uncertain và remediate |
| **Token lộ ở log** | Raw Bearer/refresh token xuất hiện trong APM | Security test fail; redaction và retention policy |
| **Sai audience** | Token A1 dành cho API khác | RS từ chối dù SSO còn hoạt động |
| **Thiếu scope** | A1 active nhưng không có quyền approve | `403`/insufficient_scope, không liên quan logout |
| **Cross-tenant access** | A1 hợp lệ nhưng object thuộc tenant khác | RS từ chối theo object-level authorization |

### Các bài test concurrency đặc biệt

~~~text
Test A — Logout vs API request:
  T0: API request dùng session S1 bắt đầu.
  T1: Logout invalidates S1.
  T2: API request cũ tiếp tục.
  Expected: policy định nghĩa rõ in-flight request handling;
            không cho request MỚI dùng S1.

Test B — Revoke vs refresh:
  T0: refresh R1 đang được xử lý.
  T1: revoke R1/grant chạy ở node AS khác.
  Expected: AS có trạng thái nhất quán;
            không âm thầm cấp refresh descendant sau terminal revoke.

Test C — Revocation event vs introspection cache:
  T0: RS có active=true cache entry A1.
  T1: event revoke A1 tới RS, xóa/đánh dấu entry.
  T2: introspection response cũ active=true tới muộn.
  Expected: response cũ không ghi đè revoke state mới hơn.

Test D — Back-channel logout duplicate:
  T0: OP POST logout JWT jti=J1, RP invalidate S1.
  T1: OP retry cùng J1 vì mất acknowledgement.
  Expected: RP xử lý idempotent, không xóa session user khác.
~~~

## 19. Tình huống thực hành: ba thiết bị và một token bị sao chép

An đăng nhập vào Finance Web trên laptop bằng OIDC; đồng thời có Finance Mobile trên điện thoại và Report Portal trên tablet. Finance Web dùng BFF, Payment API nhận JWT access token. Một kẻ tấn công đã sao chép A1 từ log, trước khi An bấm **“Đăng xuất”**.

~~~text
Laptop:
  Finance Web RP session S1
  OP SSO browser session O1
  access token A1, exp=10:15
  refresh token R1

Phone:
  Finance Mobile session S2
  refresh token R2

Tablet:
  Report Portal session S3

Event at 10:03:
  An chọn "Đăng xuất khỏi Finance Web trên laptop".
~~~

**Câu 1. Sau local logout, S1 còn dùng được không?**

**Không**, nếu RP đã invalidate session server-side đúng cách. Xóa cookie và hủy session cần cùng được thực hiện; bản sao S1 không được backend chấp nhận.

**Câu 2. Browser có thể tự đăng nhập lại không cần mật khẩu?**

**Có thể**, nếu OP SSO session O1 vẫn active và OP cho SSO. Local logout không mặc nhiên kết thúc O1.

**Câu 3. Revoke R1 có làm R2 trên điện thoại mất hiệu lực không?**

**Không thể kết luận khi chưa biết grant/family policy**. Nếu R1/R2 thuộc các grants/device sessions riêng, AS có thể chỉ revoke R1. Nếu security policy là global account lock, có thể cần revoke toàn bộ grants. Không dùng UI “logout thiết bị này” để giả định phạm vi toàn tài khoản.

**Câu 4. Attacker có A1 còn hạn, liệu họ gọi Payment API được không?**

**Có thể**, nếu A1 là Bearer, đúng audience/scope, RS chỉ kiểm JWT offline và chưa có revocation state. Logout BFF và xóa cookie không xóa bản sao A1 của attacker.

**Câu 5. Nếu ứng dụng gọi RFC 7009 và nhận HTTP 200, có chắc attacker bị chặn?**

**Không.** HTTP 200 cho biết revocation request được AS chấp nhận theo protocol (kể cả token không tồn tại), không chứng minh RS đã cập nhật. Cần kiểm actual enforcement và độ trễ.

**Câu 6. Nếu An chọn “Đăng xuất khỏi mọi ứng dụng và thiết bị” thì nên làm gì khác?**

Thiết kế cần điều phối **OP session logout, RP sessions ở từng ứng dụng, các refresh tokens/grants, access-token revocation state ở RS**, có cơ chế back-channel/notification và SLO đo được. Thực tế có thể có RP không tham gia hay endpoint lỗi; phải báo trạng thái còn thiếu.

**Câu 7. Một RP nhận back-channel logout JWT không có `sid` nhưng có `sub=user:an`, có dùng được không?**

Tùy profile và mapping: Back-Channel Logout yêu cầu **`sub` hoặc `sid`**; nếu có `sub`, RP có thể xác định các session phù hợp của subject/issuer theo chính sách. Phải kiểm JWT signature, `iss`, `aud`, `iat`, `jti`, `events` và chống replay trước khi invalidate, không xóa session user khác hoặc issuer khác.

**Câu 8. OP gửi logout JWT có `nonce` để “tăng an toàn” thì sao?**

Không đúng profile: **Logout Token không được chứa `nonce`** theo OIDC Back-Channel Logout. RP nên từ chối token sai chuẩn thay vì âm thầm bỏ qua.

**Câu 9. Nếu Payment API trả `403 insufficient_scope` sau logout, có nghĩa token đã bị revoke không?**

**Không.** `403` do thiếu scope/quyền có thể xảy ra ngay cả khi token active. `401 invalid_token` thường liên quan token không chấp nhận được; cần phân biệt authentication, authorization và revoke status.

**Câu 10. Có nên gửi client secret hoặc R1 vào email/ticket để “đối chiếu revoke” không?**

**Không.** Chỉ dùng audit metadata/correlation ID hoặc secure token handle theo policy. Nếu cần điều tra, truy cập token store và logs phải được kiểm soát; không phát tán raw credential.

## 20. Checklist triển khai logout và revocation

1. **Định nghĩa phạm vi logout:** local RP, OP SSO, một thiết bị, tất cả phiên của client hay toàn tài khoản?
2. **Session invalidation server-side:** Session ID/cookie cũ bị từ chối, không chỉ xóa browser storage?
3. **Cookie đúng thuộc tính:** `Name`/`Path`/`Domain` khớp, `Secure`/`HttpOnly`/`SameSite` phù hợp?
4. **CSRF/XSS:** Logout qua endpoint được bảo vệ, không dùng GET logout không kiểm soát; chống script injection?
5. **Phân biệt OP và RP:** Local logout không được quảng bá là đã kết thúc OP SSO nếu chưa thực hiện?
6. **OIDC RP-Initiated Logout:** OP endpoint/metadata có hỗ trợ, `id_token_hint` và post-logout redirect được quản lý an toàn?
7. **Front-channel hạn chế:** Hiểu browser cookie/iframe restrictions, không giả định mọi RP luôn nhận sự kiện?
8. **Back-channel JWT validation:** Kiểm `iss`, `aud`, `iat`, `jti`, `events`, `sub/sid`, signature; không có `nonce`?
9. **Back-channel replay/idempotency:** Duplicate notifications không xóa nhầm phiên hoặc bị replay tùy ý?
10. **RFC 7009 đúng hợp đồng:** POST form token, `token_type_hint` optional, client authentication, TLS; xử lý HTTP 200/`unsupported_token_type`/AS outage?
11. **Hiểu token scope:** Revoke access token, refresh token, family và grant có tác động rõ theo AS profile?
12. **Có kế hoạch với access token đã phát:** JWT offline, opaque introspection và RS denylist được phân biệt?
13. **Revoke-lag SLO:** Thời gian tối đa RS còn nhận token đã revoke được định nghĩa, đo bằng kiểm thử thật?
14. **Cache không fail-open:** Introspection cache TTL/expiry/invalidation đáp ứng SLO; AS outage không kéo dài token vô hạn?
15. **Chống token theft:** Giữ access token ngắn hạn, scope/audience nhỏ, sender-constrained khi cần, không log raw token?
16. **Multi-device/grant binding:** “Logout một thiết bị” không chạm nhầm thiết bị khác; “Logout all” có coverage phù hợp?
17. **Sự kiện revoke và session race:** Không còn refresh descendant được cấp sai sau grant revoke; in-flight request có policy?
18. **Không nhầm authn và authz:** RS vẫn kiểm issuer, audience, expiry, scope, tenant/owner/object sau khi logout hay không?
19. **Partial failure minh bạch:** RP session đã invalidated nhưng AS revoke timeout được ghi là uncertain và có remediation?
20. **Audit và riêng tư:** Không raw token, client secret, id_token_hint trong logs/tickets; lưu event ID/metadata theo retention?
21. **Test âm tính:** Cross-client revoke, invalid token 200, POST logout CSRF, OIDC logout token giả, JWT stale, RS cache và multi-issuer?

**Ghi nhớ:** **Logout kết thúc session; revocation làm thay đổi hiệu lực token/grant; Resource Server phải thực sự biết trạng thái đó để chặn access token.** Local logout ở RP không mặc nhiên kết thúc OP SSO, và OIDC logout notification không mặc nhiên thu hồi mọi access/refresh token. Với **JWT kiểm offline**, token bị đánh cắp có thể dùng tới `exp` nếu không có denylist/introspection/event policy; với **opaque token**, tốc độ thu hồi còn phụ thuộc cache và availability. Một hệ thống muốn “đăng xuất mọi nơi” phải **định nghĩa phạm vi, phối hợp nhiều bên và đo được độ trễ thu hồi**.

### Chuẩn và tài liệu tham khảo

- **RFC 7009 — OAuth 2.0 Token Revocation:** `/revoke`, request/response, `token_type_hint`, client authentication, tác động lên các token cùng grant và security considerations.
- **RFC 7662 — OAuth 2.0 Token Introspection:** `active`, protected introspection endpoint, caching và giới hạn dữ liệu tiết lộ.
- **RFC 6749 — The OAuth 2.0 Authorization Framework:** access token, refresh token, client authentication và authorization grants.
- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** bearer token và `invalid_token`/`insufficient_scope`.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** bảo vệ refresh tokens, token theft, replay và access token security.
- **OpenID Connect RP-Initiated Logout 1.0:** `end_session_endpoint`, `id_token_hint`, `post_logout_redirect_uri` và `state`.
- **OpenID Connect Front-Channel Logout 1.0:** browser-based logout notifications, `iss`/`sid` và giới hạn trình duyệt.
- **OpenID Connect Back-Channel Logout 1.0:** signed logout token, `events`, `sub`/`sid`, `jti` và replay protection.
- **OpenID Connect Session Management 1.0:** cơ chế theo dõi trạng thái phiên OP/RP khi profile hỗ trợ.
- **RFC 7519 — JSON Web Token (JWT):** signature context và các `iss`, `aud`, `exp`, `jti` claims.
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** access token purpose, JWT claims và validation tại RS.
- **RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP):** sender-constrained access tokens và proof theo request.
- **RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens:** ràng buộc token với client certificate.
- **Spring Security Reference — Logout và OAuth2 Login/OIDC Logout:** session invalidation, CSRF logout và OIDC RP-Initiated Logout handler.
- **OWASP Session Management Cheat Sheet, Authentication Cheat Sheet và OAuth 2.0 Cheat Sheet:** cookie/session security, logout, token storage và incident handling.
