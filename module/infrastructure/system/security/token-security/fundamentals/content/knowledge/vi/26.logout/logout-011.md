# Không coi redirect là bằng chứng logout thành công

## 1. Bẫy thường gặp: trở về trang đăng xuất không có nghĩa mọi phiên đã kết thúc

Trong chương **Logout** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**, bài này tập trung vào một sai lầm thiết kế rất dễ gặp khi dùng OAuth 2.0 và OpenID Connect (OIDC): **coi một HTTP redirect, một callback hoặc việc người dùng nhìn thấy trang “Đăng xuất thành công” là bằng chứng rằng tất cả session và token liên quan đã bị vô hiệu**.

Giả sử Alice đăng nhập **Shop Web** qua OpenID Provider (OP) tại `https://login.example.com`. Khi cô nhấn “Đăng xuất”, Shop Web xóa một cookie local và chuyển trình duyệt đến endpoint logout của OP:

~~~text
Shop Web
  |
  | 302 Location: https://login.example.com/oidc/logout?...
  v
OpenID Provider
  |
  | 302 Location: https://shop.example.com/signed-out?state=...
  v
Shop Web hiển thị: "Bạn đã đăng xuất"
~~~

**Có thể kết luận những gì?**

- Trình duyệt đã được **điều hướng** qua những URL tương ứng.
- Shop Web **có thể** đã thực thi bước xóa session của mình nếu có bằng chứng phía server.
- OP **có thể** đã xử lý yêu cầu logout và điều hướng trở lại theo hợp đồng của nó.

**Không thể chỉ từ redirect kết luận:**

- Session SSO của OP chắc chắn đã chấm dứt trên mọi thiết bị.
- Session của mọi ứng dụng Relying Party (RP) khác đã bị đóng.
- Refresh token của Shop Web đã bị thu hồi tại Authorization Server (AS).
- JWT access token còn hạn đã bị mọi Resource Server (RS) từ chối.
- Mọi browser tab, thiết bị, session cookie, tác vụ nền và service downstream đã dừng hoạt động.
- Người dùng không thể được đăng nhập lại bằng một session còn hoạt động khác.

**Nguyên tắc xuyên suốt:** *Redirect là tín hiệu điều hướng trên kênh browser; logout success là kết quả của các thay đổi trạng thái và quyết định thực thi tại đúng trust boundary.*

### 1.1. Ví dụ sự cố không hiếm gặp

~~~text
10:00  Alice đăng nhập Shop Web; RP có session S1.
10:00  AS cấp access token T1 (exp 10:15), refresh token R1.
10:03  Alice nhấn Logout.
10:03  Browser nhận 302 sang OP, sau đó 302 về /signed-out.
10:04  Trang Shop Web báo "Đã đăng xuất".
10:05  R1 vẫn còn hiệu lực vì chưa có revoke ở AS.
10:06  Một bản sao JWT T1 vẫn được Orders API chấp nhận offline.
10:15  T1 tự hết hạn nếu không có cơ chế chặn sớm.
~~~

Trang `/signed-out` không phát hiện được R1 hay T1 chỉ bằng việc trình duyệt đến đó. Nếu UI khẳng định **“Đã đăng xuất khỏi mọi thiết bị và mọi API”**, đó là lời hứa không có căn cứ kỹ thuật.

### 1.2. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **local RP logout, OP/SSO logout, OIDC logout notifications, OAuth token revocation và RS enforcement**.
2. Giải thích ý nghĩa thực của các redirect trong **RP-Initiated Logout** theo OIDC.
3. Hiểu vì sao `post_logout_redirect_uri`, `state` và HTTP 302 **không phải proof of revocation**.
4. Thiết kế logout flow an toàn với cookie/session invalidation, CSRF, redirect URI validation, browser back/multi-tab và network failures.
5. Xử lý Front-Channel/Back-Channel Logout, logout token JWT, session binding (`sid`/`sub`) và replay protection theo profile.
6. Xác định ảnh hưởng tới access/refresh/ID token, JWT/opaque, audience, scope và refresh-token family.
7. Triển khai Java/Spring Security có quan sát phía server thay vì đánh dấu thành công chỉ dựa vào callback URL.
8. Xây dựng ma trận kiểm thử cho các tình huống logout một phần, thất bại phân tán, timeout và đăng nhập lại.

## 2. Định nghĩa các trạng thái logout phải tách biệt

Một hệ thống OIDC thường có **nhiều state stores khác nhau**. “Đăng xuất” không tự động là một transaction ACID trên tất cả chúng.

| Ranh giới | Trạng thái cần kết thúc | Ai kiểm soát? | Redirect có đủ làm bằng chứng không? |
|---|---|---|---|
| **RP local session** | HTTP session, server session ticket, browser cookie liên quan | Shop Web/RP | **Không**; cần kiểm state ở RP |
| **OP session/SSO** | Phiên đăng nhập tại OpenID Provider | OP | **Không**; OP phải xử lý thật |
| **RP khác** | Session của Helpdesk, Billing, CRM | Mỗi RP và cơ chế SSO logout | **Không** |
| **Authorization grant** | Quyền client được AS cấp cho user | AS | **Không** |
| **Refresh token/family** | Khả năng xin access token mới | AS token endpoint | **Không** |
| **Access token** | Credential API chưa hết hạn | AS/RS và thiết kế revoke | **Không** |
| **Resource authorization** | Quyền user trên order/tenant/action | RS hoặc policy engine | **Không** |
| **Ứng dụng mobile/thiết bị khác** | Token/session được lưu riêng | Client/AS/OP theo policy | **Không** |

### 2.1. Authentication session khác authorization grant

**RP session** giúp trình duyệt của Alice được Shop Web nhận diện là đã đăng nhập. **Authorization grant** cho phép một OAuth client nhận token trong giới hạn đã được ủy quyền. Hai state này có thể liên quan nhưng **không đồng nhất**.

~~~text
Alice nhấn Logout tại Shop Web.
    |
    +--> RP xóa session S1: có thể thành công.
    |
    +--> OP session: tùy RP-initiated logout, policy và browser.
    |
    +--> AS refresh token R1: tùy gọi revocation và policy.
    |
    +--> Access token T1 ở Orders API: tùy expiry/introspection/denylist.
~~~

Đóng session S1 **không tự gửi một thông điệp mật mã** tới mọi Orders API đang kiểm bearer token T1.

### 2.2. Logout, revoke và expiry có kết quả khác nhau

| Thao tác | Tác dụng có thể đạt được | Những điều không nên suy ra |
|---|---|---|
| Xóa cookie local | Browser không còn gửi cookie session đó (nếu xử lý đúng) | Session server đã bị vô hiệu hoặc token khác đã revoke |
| Invalidate server-side session | RP không còn chấp nhận session ID đó | OP session và refresh token đều đã hủy |
| RP-Initiated Logout | RP yêu cầu OP kết thúc phiên SSO theo profile | Mọi RPs/RS đã đóng session/token |
| Front-Channel Logout | OP dùng browser để gửi thông điệp logout tới RPs | Mọi iframe/request đã đến và được xử lý |
| Back-Channel Logout | OP gửi logout token trực tiếp tới RP backend | Các API khác đã revoke access token |
| RFC 7009 Token Revocation | AS xử lý yêu cầu vô hiệu token/grant theo contract | Mọi RS đã biết ngay về trạng thái mới |
| JWT tự hết hạn | `exp` không còn hợp lệ sau thời điểm giới hạn | Đã ngăn token trước expiry |
| Xóa token trong browser storage | Client không còn giữ credential trong kho đó | Kẻ đã sao chép token không còn dùng được |

### 2.3. Định nghĩa rõ “logout thành công” trong sản phẩm

Thay vì một biến global `logoutSuccess=true`, hãy xác định **mức độ cam kết**:

~~~text
LOCAL_SESSION_ENDED
    RP đã invalidate session hiện tại và kiểm tra state.

OP_LOGOUT_REQUESTED
    Browser đã được điều hướng hoặc request đã được khởi tạo.

OP_LOGOUT_CONFIRMED_BY_TRUSTED_MECHANISM
    Có tín hiệu/trạng thái đáng tin theo contract của OP,
    không chỉ một URL callback.

REFRESH_GRANT_REVOKED
    AS đã xử lý revoke theo policy; ảnh hưởng tới refresh.

ACCESS_TOKEN_ENFORCEMENT_CONFIRMED
    RS/propagation đã có bằng chứng từ chối token thuộc phạm vi.
~~~

Các tên trên là **mô hình nội bộ minh họa**, không phải enum hay response chuẩn của OIDC. Có thể chỉ cần hai trạng thái UX “đã kết thúc phiên trên thiết bị này” và “đăng xuất ở các dịch vụ khác chưa được xác minh”.

## 3. RP-Initiated Logout: các redirect trong giao thức nói gì?

**OpenID Connect RP-Initiated Logout 1.0** mô tả cách một Relying Party yêu cầu OpenID Provider kết thúc phiên của End-User. RP đưa user agent tới **`end_session_endpoint`** của OP, với các tham số phù hợp profile/đăng ký.

### 3.1. Một ví dụ request

~~~http
HTTP/1.1 302 Found
Location: https://login.example.com/connect/logout?id_token_hint=<ID_TOKEN_HINT>&post_logout_redirect_uri=https%3A%2F%2Fshop.example.com%2Fsigned-out&state=<UNPREDICTABLE_STATE>
Cache-Control: no-store
~~~

Ví dụ chỉ minh họa. Trong triển khai thật, client dùng OIDC discovery/metadata tin cậy, URI builder, validation và logout handler chuẩn. Không tự ghép raw ID token vào URL rồi ghi nguyên đường dẫn ra logs.

- **`end_session_endpoint`**: URL do OP công bố để tiếp nhận yêu cầu kết thúc OP session.
- **`id_token_hint`**: ID token được RP cấp trước đó, thường được dùng để OP nhận biết phiên/client/end-user liên quan; đây không phải access token để gọi API.
- **`post_logout_redirect_uri`**: URL mà RP yêu cầu OP điều hướng user agent tới **sau logout** theo điều kiện của OP.
- **`state`**: giá trị opaque của RP dùng để liên kết response điều hướng với logout request gốc; không phải chứng cứ OP đã revoke token.
- **`client_id`**, **`logout_hint`**, **`ui_locales`**: các tham số có thể hỗ trợ theo profile, mỗi tham số có nghĩa riêng và phải được OP kiểm đúng.

Không phải mọi OP hỗ trợ cùng bộ tham số và hành vi, nên phải đối chiếu **discovery, client registration và profile OP thực tế**. Không coi một endpoint tên `/logout` bất kỳ là `end_session_endpoint` chuẩn chỉ vì URL trông hợp lý.

### 3.2. `post_logout_redirect_uri` là đích điều hướng, không phải biên nhận bảo mật

Ví dụ browser về:

~~~http
GET /signed-out?state=<UNPREDICTABLE_STATE> HTTP/1.1
Host: shop.example.com
Cookie: ...
~~~

Điều kiện đúng:

1. RP phải kiểm `state` khớp request logout đang chờ nếu có dùng state.
2. RP không được nhận một `state` tự khai như bằng chứng OP đã vô hiệu refresh token.
3. RP chỉ nên hiển thị **các kết quả đã xác minh tại ranh giới mình kiểm soát**.

**Cảnh báo quan trọng:** một attacker có thể điều hướng trình duyệt thẳng tới `/signed-out?state=...` nếu đoán hoặc lấy được URL; thậm chí một state đúng **chỉ chứng minh tương quan với request**, không thể chứng minh toàn bộ state bên OP/AS/RS đã thay đổi.

### 3.3. Vì sao có thể có redirect dù logout chưa đạt mục tiêu của sản phẩm?

- RP đã xóa local session nhưng OP logout request thất bại hoặc user chưa hoàn tất bước tương tác của OP.
- OP xử lý logout ở mức một OP session, trong khi user còn session khác trên thiết bị khác.
- OP chuyển user về RP theo hợp đồng nhưng RPs khác không nhận hoặc không xử lý được logout notification.
- OP đã logout đúng, nhưng refresh/access tokens của một OAuth client vẫn còn sống vì token lifecycle độc lập.
- Browser chặn cookies/iframes hoặc navigation bị gián đoạn, khiến trạng thái OP/RP khó xác định.
- Một callback URL hoặc trang `/signed-out` bị gọi trực tiếp, không phải một chứng nhận từ OP.

Không nên khẳng định mọi OP đều redirect khi logout thất bại; hành vi cụ thể phụ thuộc chuẩn/profile/provider. Điều được khẳng định chắc chắn là **redirect không mang bằng chứng mật mã về toàn bộ token/session trong hệ thống**.

### 3.4. OIDC authorization callback khác post-logout callback

Hai tuyến dễ có tên giống nhau nhưng nghĩa hoàn toàn khác:

~~~text
/login/oauth2/code/shop
    -> Authorization Code callback
    -> có code, state, issuer binding; đổi code qua token endpoint.

/signed-out
    -> Post-logout destination
    -> không phải authorization code callback.
    -> state nếu có để correlation, không phải proof of token revoke.
~~~

Không để `/signed-out` cấp token mới, tự xác thực user bằng query hoặc coi một `code` bất kỳ từ URL như authorization code của request login trước.

## 4. Ba cái bẫy của HTTP redirect

### 4.1. HTTP 302 chỉ là lời hướng dẫn chuyển địa chỉ

Một `302 Found` và header `Location` xác định đích browser **nên điều hướng**, không xác minh:

- Đích có được truy cập thành công không.
- Network có thất bại giữa chừng không.
- Session server ở OP/RP đã bị invalidate không.
- Một bên thứ ba đã xử lý back-channel logout không.
- OAuth tokens đã bị revoke hoặc bị RS từ chối không.

### 4.2. HTTP 200 từ trang `/signed-out` cũng không đủ

Browser có thể nhận một trang HTML thành công từ `/signed-out`, nhưng đó chỉ là **response của RP endpoint**. Nếu endpoint luôn trả một trang đẹp mà không kiểm session state, người dùng có thể hiểu sai. Thiết kế UX phải dựa trên kết quả của các bước đã thực thi.

### 4.3. `state` chống lẫn response, không tạo quyền cho callback

Logout `state` có thể là giá trị random khó đoán, ngắn hạn và single-use, lưu ở pending logout transaction. Việc so khớp chống nhầm lẫn/CSRF ở callback, **không biến callback thành chữ ký của OP**.

~~~text
state matched: TRUE
local RP session invalidated: TRUE
AS refresh grant revoked: UNKNOWN
RS access token revoked: UNKNOWN

UI nên nói: "Đã kết thúc phiên trên trình duyệt này"
Không nói: "Tất cả token trên mọi thiết bị đã vô hiệu"
~~~

## 5. Cookie và session: điều RP thực sự kiểm soát

### 5.1. Xóa cookie không thay invalidate phiên trên server

Đăng xuất local an toàn thường gồm:

1. Xác định chính xác **session hiện tại** của user.
2. Invalidate server-side HTTP session hoặc session record theo cơ chế ứng dụng.
3. Xóa/cancel cookies tương ứng bằng `Set-Cookie` với đúng **name, path, domain** và thuộc tính policy.
4. Xóa/thu hồi credential/cache liên quan tại BFF hoặc token store nếu scope logout yêu cầu.
5. Không để trang nhạy cảm được phục vụ lại từ HTTP/browser cache sau logout.
6. Ngăn request khác tạo lại session cũ vì race trong refresh/login flow.

Ví dụ response xóa cookie minh họa:

~~~http
HTTP/1.1 302 Found
Set-Cookie: SESSION=; Path=/; Max-Age=0; Secure; HttpOnly; SameSite=Lax
Location: /signed-out
Cache-Control: no-store
~~~

**Không kết luận phiên đã bị chặn chỉ vì cookie có Max-Age=0.** Nếu session ID cũ vẫn active tại server, một bản sao cookie bị đánh cắp có thể còn dùng được. Server-side session invalidation là một kiểm soát độc lập.

### 5.2. Cookie attribute và browser quirks

- `Secure` giới hạn gửi cookie qua HTTPS.
- `HttpOnly` giảm khả năng JavaScript đọc cookie; nó không thay chống XSS/CSRF.
- `SameSite` ảnh hưởng gửi cookie trong cross-site navigation; chọn theo flow và threat model.
- Cookie deletion cần **domain/path đúng**; xóa cookie `Path=/logout` không tự xóa cookie cũ `Path=/`.
- Browser có thể có nhiều cookies cùng tên khác path/domain; test cụ thể.
- Front-channel logout dựa trên browser/iframe có thể thất bại vì cookie restrictions, third-party cookie blocking hoặc CSP.

Không dựa vào frontend `document.cookie=''` như giải pháp duy nhất cho server-side session cookies `HttpOnly`.

### 5.3. Nhiều browser tabs và session resurrection

~~~text
Tab A: người dùng nhấn Logout, RP invalidate session S1.
Tab B: vẫn hiển thị giao diện đã đăng nhập trong bộ nhớ.
Tab B: gửi request API với token được giữ tạm.
Tab B: nhận response và có thể dựng lại trạng thái UI sai.
~~~

Ứng dụng cần:

- Chặn session S1 ở backend.
- Đồng bộ trạng thái logout giữa tabs nếu sản phẩm yêu cầu, nhưng **backend là source of truth**.
- Xóa bộ nhớ/token client một cách phù hợp.
- Xử lý HTTP 401/403 từ API sau logout; không tự refresh lại token từ grant đã bị thu hồi.
- Chống race request trước/sau logout và không hiển thị lại dữ liệu bí mật từ cache.

`BroadcastChannel`, storage events hoặc framework state có thể hỗ trợ UX đồng bộ tab, nhưng **không phải bằng chứng bảo mật** và không thay server enforcement.

## 6. Logout theo từng phạm vi: một tab, một thiết bị, một OP hay mọi thiết bị?

Một nút ghi chung "Đăng xuất" có thể đại diện cho rất nhiều cam kết kỹ thuật. Trước khi triển khai, product/security cần định nghĩa **phạm vi logout và nơi thực thi**.

### 6.1. Ma trận các phạm vi

| Hành động trong UI | Mục tiêu | Hệ thống phải xử lý |
|---|---|---|
| **Đăng xuất ứng dụng này** | Kết thúc RP session hiện tại | RP server session/cookie/BFF token store |
| **Đăng xuất khỏi SSO** | Kết thúc OP session có liên quan | OP end-session flow, các RP logout mechanisms theo policy |
| **Đăng xuất thiết bị này** | Kết thúc sessions/grants gắn đúng thiết bị | RP, AS device/session binding và credential trên thiết bị |
| **Đăng xuất mọi thiết bị** | Vô hiệu mọi session/grant thuộc user trong phạm vi đã quy định | AS/OP/RPs, epoch/revocation propagation, thiết bị khác |
| **Ngắt kết nối ứng dụng bên thứ ba** | Thu hồi grant/token của client cụ thể | AS authorization grant, refresh tokens và access token enforcement nếu yêu cầu |
| **Đăng xuất do nghi bị chiếm tài khoản** | Chặn sử dụng credential và phiên còn tồn tại | Security epoch, revoke, session invalidation, reauthentication/step-up |

**Không thể dùng một post-logout redirect cho mọi phạm vi mà không có các cơ chế phía sau.** Ví dụ logout trên laptop không nhất thiết logout app mobile của Alice.

### 6.2. Phạm vi của OIDC session và client

Một user có thể đăng nhập nhiều ứng dụng:

~~~text
OpenID Provider:
    OP session P1: Alice trên Chrome.

Shop Web:
    RP session S1: Alice trên Chrome.

Helpdesk:
    RP session S2: Alice trên Chrome.

Shop Mobile:
    RP/OS session M1: Alice trên điện thoại khác.
~~~

RP-Initiated Logout từ Shop Web có thể yêu cầu kết thúc **P1**, và OP có thể thông báo các RPs theo những logout specs/profiles được hỗ trợ. Tuy nhiên **M1 trên thiết bị khác** không bị đảm bảo chấm dứt chỉ vì một redirect diễn ra trên Chrome.

Nếu hệ thống có yêu cầu “all devices”, cần một **user-wide session/grant revocation policy** có thể áp dụng và xác minh qua các thiết bị/regions.

### 6.3. Logout không đồng nghĩa xóa dữ liệu của người dùng

Kết thúc phiên và thu hồi token **không tự xóa** dữ liệu nghiệp vụ như đơn hàng, giao dịch hoặc hồ sơ. Nếu yêu cầu “xóa tài khoản/dữ liệu”, đây là workflow riêng với quyền, retention và bảo vệ chống thao tác nhầm.

Một API `/logout` không nên vì muốn “đăng xuất sạch” mà xóa hồ sơ nghiệp vụ hoặc xóa mọi logs/audit.

## 7. Local RP logout trước khi redirect: giảm phụ thuộc vào browser

Trong nhiều ứng dụng web có server session, một chính sách thực dụng là **làm mất hiệu lực local RP session ở server trước hoặc tại thời điểm phát redirect tới OP**, rồi điều hướng browser đến OP end-session endpoint.

~~~mermaid
sequenceDiagram
    actor U as Alice
    participant B as Browser
    participant RP as Shop Web
    participant OP as OpenID Provider
    U->>B: Nhấn Đăng xuất
    B->>RP: POST /logout + CSRF token
    RP->>RP: Invalidate local session S1, clear cookie
    RP->>RP: Record local logout result
    RP-->>B: 302 đến end_session_endpoint của OP
    B->>OP: Navigate logout request (id_token_hint, state...)
    OP->>OP: Xử lý OP session logout theo policy
    OP-->>B: Redirect về post_logout_redirect_uri nếu hợp lệ
    B->>RP: GET /signed-out?state=...
    RP->>RP: Correlate state với pending logout transaction
    RP-->>B: Hiển thị đúng phạm vi trạng thái đã biết
~~~

**Ý tưởng quan trọng:** nếu browser không đến được OP, **S1 vẫn có thể đã được RP invalidate**. Khi đó UI nên nói chính xác “Phiên của ứng dụng này đã kết thúc; chưa xác nhận được trạng thái đăng xuất SSO”, thay vì khôi phục S1 hoặc báo rằng mọi hệ thống đã logout.

### 7.1. Không lưu pending logout state trong session vừa bị xóa một cách mâu thuẫn

Một lỗi hay gặp:

~~~text
1. Lưu logout_state ở HTTP session S1.
2. Invalidate S1.
3. Redirect tới OP.
4. Callback /signed-out cần S1 để so state.
=> State không còn -> lỗi correlation.
~~~

Cách khắc phục có thể là:

- Lưu pending logout transaction trong **server-side short-lived store** tách khỏi session bị hủy, với random one-time state.
- Hoặc dùng một cơ chế correlation được framework hỗ trợ, với cookie short-lived được bảo vệ phù hợp chính sách.
- Chỉ lưu metadata tối thiểu như `state`, `issuer`, `client_registration_id`, `started_at`, `local_logout_done`, `expires_at`; **không** cần access/refresh token thô.
- Khi callback được nhận và kiểm hợp lệ, **consume** state để chống replay.
- Nếu callback không tới, hết TTL pending record mà **không hồi sinh RP session**.

**State không phải quyền đăng nhập:** một pending logout state đúng không được cho phép người dùng thiết lập lại session hoặc truy xuất thông tin tài khoản.

### 7.2. Dùng POST cho logout intent khi thích hợp

Đối với local logout tại RP, dùng **POST có bảo vệ CSRF** khi kiến trúc web/state-changing endpoint yêu cầu, thay vì cho mọi GET link tự xóa session.

Vì GET có thể bị kích hoạt bởi prefetch, link preview, image tags hoặc web page từ bên khác, một endpoint `GET /logout` thực hiện state change không kiểm soát có nguy cơ **logout CSRF**. Logout CSRF thường liên quan gây gián đoạn, login confusion và trong một số thiết kế có thể hỗ trợ chuỗi tấn công phức tạp hơn.

Lưu ý: OP `end_session_endpoint` theo RP-Initiated Logout có thể được truy cập bằng browser navigation/GET theo profile. **Không nhầm** yêu cầu POST bảo vệ CSRF của *local app logout action* với method bắt buộc của *OIDC RP-initiated request*.

### 7.3. Local logout phải an toàn ngay cả khi OP chậm

Phương án dễ gây sự cố:

~~~text
User nhấn Logout
  -> RP redirect sang OP
  -> Đợi OP trả callback
  -> Mới invalidate RP session
~~~

Nếu OP offline, DNS lỗi hoặc browser đóng tab, **RP session vẫn sống**. Thay vào đó, hãy quy định transaction boundary cho local logout không phụ thuộc hoàn toàn callback từ bên ngoài.

Trong một số sản phẩm có workflow đặc thù, thứ tự logout có thể khác; nhưng khi đó phải chỉ rõ rủi ro và cách tránh việc browser mất kết nối dẫn đến session chưa bị hủy.

## 8. Browser navigation có thể thất bại hoặc bị giả mạo

### 8.1. Các điểm đứt gãy có thể xảy ra

~~~text
RP invalidate S1 -- OK
RP gửi 302       -- OK
Browser -> OP    -- NETWORK ERROR
OP logout P1     -- UNKNOWN
Browser -> RP    -- KHÔNG TỚI
~~~

Kết quả an toàn của RP:

- Giữ S1 **đã bị invalidate**.
- Không tự đánh dấu OP/SSO logout thành công.
- Không tự tạo lại token/session trong vòng retry UI.
- Cho người dùng lựa chọn thử hoàn tất OP logout hoặc xem hướng dẫn theo profile.
- Ghi metadata không nhạy cảm về lỗi/timeout để chẩn đoán.

### 8.2. Callback có thể đến mà không có logout request

Một user hoặc attacker có thể gõ trực tiếp:

~~~http
GET /signed-out?state=arbitrary HTTP/1.1
Host: shop.example.com
~~~

Nếu controller chỉ kiểm path `/signed-out` rồi set `logoutSuccess=true`, nó đã nhầm **trang tĩnh** thành **security event**.

Nên phân biệt:

~~~text
No pending logout state
    -> Trang thông báo chung / request không hợp lệ.

Pending state hợp lệ, RP session đã invalidate
    -> Chứng minh được local RP logout theo state server.

OP logout completion
    -> Chỉ khẳng định theo mức tín hiệu OP/protocol thực sự cung cấp.
~~~

### 8.3. Redirect đến website ngoài ý muốn

Nếu cho caller tự quyết định:

~~~http
POST /logout?returnTo=https://attacker.example/fake-login
~~~

rồi RP trả `Location` tới URL đó mà không kiểm soát, attacker có thể tạo **open redirect** sau logout để giả giao diện đăng nhập. Điều này rất nguy hiểm vì user vừa đăng xuất, dễ bị dụ nhập password lại.

Giải pháp:

1. Chỉ cho **post-logout redirect URIs đã đăng ký/allowlist** theo hợp đồng RP/OP.
2. Với local return path, chỉ cho **relative path nội bộ an toàn** hoặc allowlist cụ thể; tránh URL có scheme `javascript:`, protocol-relative `//`, hostname lạ và encoding mơ hồ.
3. Không dùng `Host`/`X-Forwarded-Host` từ nguồn không tin cậy để xây return URL.
4. Không đưa access token, refresh token, client secret hoặc session cookie vào query của logout URI.
5. Theo dõi redirect failures nhưng không ghi raw `id_token_hint` hoặc query bí mật vào log.

### 8.4. `state` phải ràng buộc đúng OP/client

Nếu Shop Web hỗ trợ nhiều OP:

~~~text
pending logout:
    state = random_unguessable
    expectedIssuer = https://login.company-a.example
    clientRegistration = shop-a
    postLogoutRedirectUri = https://shop.example.com/signed-out
    startedAt / expiresAt
    consumed = false
~~~

Không lấy một `issuer` tùy ý từ callback query để tin rằng request thuộc OP đó. Session/callback phải được ràng buộc với **issuer đã chọn từ nguồn tin cậy**, tránh mix-up.

### 8.5. `state` đúng cũng có giới hạn

Một browser redirect không ký có thể bị **replayed** nếu state không one-time, hoặc người khác có thể lấy URL từ history/log. Vì vậy state cần random, short-lived, single-use, không chứa secret dạng rõ. Nhưng ngay cả khi khớp và consumed đúng, nó **không phải giấy chứng nhận rằng mọi ứng dụng cùng OP đã logout**.

## 9. OIDC Front-Channel Logout: browser không phải kênh đáng tin tuyệt đối

**OpenID Connect Front-Channel Logout 1.0** dùng user agent/browser để thông báo logout tới RPs, thường qua các iframe hoặc request tới **`frontchannel_logout_uri`** đã đăng ký.

~~~text
OpenID Provider quyết định logout OP session
    |
    v
Browser tải logout page của OP
    |
    +--> iframe / request RP A frontchannel_logout_uri
    +--> iframe / request RP B frontchannel_logout_uri
    +--> iframe / request RP C frontchannel_logout_uri
~~~

Các RPs được thông báo có thể kết thúc sessions liên quan theo cơ chế của mình. Tuy nhiên đây là **front-channel**, phụ thuộc browser.

### 9.1. Những nguyên nhân làm front-channel không hoàn tất

- Browser đóng tab hoặc điều hướng trước khi iframe được tải.
- Third-party cookie restrictions làm RP không nhìn thấy cookie cần nhận diện session.
- CSP, sandbox, content blockers hoặc privacy features chặn iframe.
- Kết nối tới một RP bị timeout hoặc domain không sẵn sàng.
- Người dùng có nhiều sessions và RP không xác định đúng session cần đóng.
- Một RP trả `200 OK` nhưng handler không thực sự invalidate session.

**OP redirect về RP khác không thể chứng minh toàn bộ iframe logout đều đã chạy thành công.** Nếu security requirement đòi chặn session từ xa tin cậy, cần back-channel/session state hoặc cơ chế khác.

### 9.2. Không tin một HTTP GET không xác thực tùy ý

Một front-channel logout URI có thể được gọi bằng browser request. RP phải thực thi các ràng buộc **issuer/session/client parameters** được profile hỗ trợ, chống request giả hoặc thiếu session binding. Nếu chỉ cần `GET /frontchannel-logout?sid=...` để xóa bất kỳ session do attacker cung cấp, nó có thể thành endpoint logout/DoS injection.

Đừng đưa raw bearer access token vào frontchannel query; dù profile có `iss` và `sid`, chúng không phải access token và vẫn cần kiểm đúng trust boundary.

### 9.3. Khi nào front-channel hữu ích?

Front-channel có thể hỗ trợ UX đăng xuất từ nhiều browser-based RPs, nhưng cần:

- Những RPs đã đăng ký URL đúng.
- Handler idempotent.
- Session correlation an toàn.
- Test với third-party cookie blocking/multi-tab.
- Có timeout, fallback và trạng thái logout chưa chắc chắn.

**Không chọn front-channel làm bằng chứng duy nhất cho “mọi thiết bị đã logout ngay lập tức”**.

## 10. OIDC Back-Channel Logout: tín hiệu từ OP tới RP backend

**OpenID Connect Back-Channel Logout 1.0** cho phép OP gửi **logout token** tới endpoint được đăng ký của RP bằng request server-to-server, không phụ thuộc browser iframe.

~~~mermaid
sequenceDiagram
    participant OP as OpenID Provider
    participant RP1 as Shop Web backend
    participant RP2 as Helpdesk backend
    participant S as Session Store
    OP->>RP1: POST /backchannel-logout (logout_token)
    RP1->>RP1: Verify JWT claims/signature/issuer/audience/replay
    RP1->>S: Invalidate sessions matching sid/sub + issuer
    S-->>RP1: Durable session state updated
    RP1-->>OP: HTTP success theo contract
    OP->>RP2: POST logout_token (RP2 audience)
    RP2->>RP2: Verify + invalidate RP2 sessions
    Note over OP,RP2: Delivery tới RP1 không chứng minh RP2 đã hoàn tất
~~~

**Ưu điểm:** RP có thể kết thúc session ngay cả khi browser user không tải iframe. **Giới hạn:** mỗi RP phải đăng ký, nhận, xác minh và thực thi logout; delivery/retry/outage vẫn có thể xảy ra, và logout token không tự revoke OAuth access token tại RS.

### 10.1. Logout token có format và ngữ nghĩa riêng

Payload **minh họa**:

~~~json
{
  "iss": "https://login.example.com",
  "aud": "shop-web",
  "iat": 1893492000,
  "jti": "logout-event-A83c",
  "sid": "op-session-529",
  "events": {
    "http://schemas.openid.net/event/backchannel-logout": {}
  }
}
~~~

Đây là payload JWT ví dụ không có chữ ký. Back-Channel Logout spec quy định các claims/điều kiện riêng như `iss`, `aud`, `iat`, `jti`, `events` và ít nhất một trong `sub` hoặc `sid` theo profile. **Logout token không chứa `nonce`**; nếu có `nonce`, đó là điểm cần xử lý như token không hợp lệ theo spec.

Một RP phải:

1. Xác minh **chữ ký, issuer, audience, thời gian/ngữ cảnh** và thuật toán/khóa tin cậy của OP.
2. Xác minh `events` chứa đúng event logout yêu cầu theo spec; không coi JWT bất kỳ có trường `sid` là logout token.
3. Không chấp nhận `nonce` trong logout token theo profile.
4. Kiểm `jti` để phòng replay, với TTL/retention phù hợp.
5. Dùng `sid`/`sub` ràng buộc với **issuer và các sessions mà RP đã đăng ký/liên kết**, không lấy user email hoặc một raw session ID tự khai làm quyền.
6. Invalidate đúng các sessions tương ứng và ghi audit.
7. Trả response sau khi đạt commit/processing guarantee của implementation, thay vì ack trước rồi bỏ quên event.

### 10.2. `sid` không phải session cookie và không phải `sub`

- **`sub`**: subject identifier của End-User tại OP.
- **`sid`**: session identifier theo OIDC logout/session profile, giúp xác định những RP sessions liên quan đến OP session.
- **RP server session ID**: ID nội bộ của Shop Web, có thể khác `sid`.

Ví dụ mapping:

~~~text
issuer: https://login.example.com
sub: alice-123
sid: op-session-529
    |
    +--> Shop Web local session S1
    +--> Shop Web local session S2 (nếu profile/session model cho phép)
~~~

Không áp `sid=op-session-529` như một DB primary key của Alice. Khi nhận logout token theo `sid`, RP phải xác định đúng sessions được liên kết, không xóa ngẫu nhiên mọi session có cùng chuỗi `sid` ở issuer khác.

### 10.3. Back-channel message được xác minh ≠ access token đã revoke

Ngay cả khi Shop Web xử lý back-channel logout thành công và invalidate tất cả sessions tương ứng:

~~~text
Shop Web sessions: INVALIDATED
AS refresh tokens: có thể chưa bị revoke
Orders API JWT T1: có thể còn hạn
~~~

Vì vậy nếu yêu cầu “đăng xuất thì API chặn T1 ngay”, cần thêm **OAuth revocation/propagation** hoặc session/grant state checks tại RS.

### 10.4. Không khẳng định có sự bảo đảm delivery tuyệt đối

OP gửi logout token qua network; RP có thể offline hoặc xử lý lỗi. Hệ thống cần retry/monitoring theo contract và RP handler idempotent. **Không tự coi một OP logout success redirect là bằng chứng mọi back-channel logout recipients đã xử lý**, trừ khi có protocol/acknowledgement riêng đủ mạnh và kiểm tra được.

## 11. OAuth Token Revocation: chặn refresh không đồng nghĩa chặn access JWT

**RFC 7009** định nghĩa endpoint thu hồi token tại Authorization Server. Logout UX có thể kích hoạt bước revoke nếu ứng dụng có token/grant cần kết thúc theo policy.

### 11.1. Client gửi revocation request

~~~http
POST /oauth2/revoke HTTP/1.1
Host: login.example.com
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <CONFIDENTIAL_CLIENT_AUTH>

token=<URL_ENCODED_REFRESH_TOKEN>&token_type_hint=refresh_token
~~~

- Thông qua HTTPS; không đưa token vào URL query.
- Confidential client xác thực theo phương thức đã đăng ký; public client có ràng buộc khác và không có bí mật dài hạn an toàn.
- `token_type_hint` chỉ là gợi ý cho AS, không thay kiểm token ownership/client binding.
- Client không được tùy ý revoke token của client khác chỉ vì biết giá trị token.
- Access/refresh tokens và client credentials không được ghi nguyên vào log.

### 11.2. RFC 7009 HTTP 200 có ý nghĩa gì?

Ví dụ:

~~~http
HTTP/1.1 200 OK
Cache-Control: no-store
Pragma: no-cache
~~~

RFC 7009 trả **HTTP 200** cho revocation request hợp lệ kể cả khi token không hợp lệ, nhằm tránh tiết lộ sự tồn tại của credential.

**Do đó, không được diễn giải `200` thành “toàn bộ access tokens đã bị mọi RS từ chối”.** Nó mô tả kết quả xử lý ở endpoint AS theo contract, không phải distributed acknowledgement từ Orders API, Billing API và mọi gateway.

### 11.3. Refresh token rotation và token family

~~~text
R1 (ACTIVE) --refresh--> R2 (ACTIVE)
R1 (USED)
   |
   +-- reuse R1 sau rotation có thể là tín hiệu xâm phạm.
~~~

Nếu hệ thống sử dụng refresh-token rotation, logout/revoke có thể cần vô hiệu hóa **family/grant** phù hợp, không chỉ một token R1 đã USED. Đối với public clients được phát refresh token, OAuth 2.0 Security BCP yêu cầu rotation hoặc sender constraint theo profile để phòng/phát hiện reuse.

Phát hiện reuse đòi hỏi AS lưu state nhất quán và xử lý request đồng thời nguyên tử; không cho retry refresh khiến grant đã revoke được **hồi sinh**.

### 11.4. Opaque token và JWT access token sau logout

| Loại token/cách xác minh | Sau revoke ở AS | RS phải làm gì để chặn sớm? |
|---|---|---|
| **Opaque access token, introspection mỗi request** | Có thể nhận `active=false` khi state cập nhật | Introspection với consistency phù hợp và kiểm audience/scope |
| **Opaque với positive cache** | Cache `active=true` có thể còn stale | Giới hạn TTL/invalidate cache |
| **JWT access token offline** | Chữ ký và `exp` không tự đổi | Denylist `jti`, grant/session epoch, state lookup hoặc chờ `exp` theo policy |
| **JWT + revocation event** | AS phát event tới RS | Consumer, cache invalidation, replay, freshness và fail mode |
| **Sender-constrained access token** | Bản sao string khó dùng nếu không có khóa/proof | Vẫn cần revoke khi thiết bị/khóa/grant bị xâm phạm |

**Logout trên trình duyệt không thể thu hồi một bearer token đã bị sao chép** nếu RS vẫn nhận token đó. Xóa token local storage là biện pháp cần thiết ở client khi có token, nhưng không làm bản sao bên ngoài biến mất.

### 11.5. OIDC ID token là chứng từ đăng nhập, không phải access token

`id_token_hint` có thể hỗ trợ RP-Initiated Logout tại OP nhưng **ID token không phải refresh/access token**, và việc dùng ID token để gợi ý session logout không tự revoke OAuth grants.

Không chuyển ID token như Bearer tới Orders API để “kiểm tra đã logout chưa”; Orders API phải yêu cầu access token đúng issuer/audience/token type.

### 11.6. Phạm vi revoke phải rõ

Giả sử Alice đang dùng cùng Shop Web trên laptop và điện thoại:

~~~text
grant laptop:  g-L, refresh token R-L
grant mobile:  g-M, refresh token R-M
~~~

Nếu người dùng yêu cầu “Đăng xuất thiết bị này”, chính sách có thể revoke **g-L** mà giữ g-M. Nếu yêu cầu “Đăng xuất khỏi mọi thiết bị”, cần revoke **cả g-L, g-M** cùng những grants khác nằm trong phạm vi.

Đừng sử dụng `sub=alice` như lý do revoke tất cả client sessions khi UX chỉ hứa logout một thiết bị; ngược lại đừng chỉ xóa cookie của một tab khi user đã xác nhận logout toàn bộ.

## 12. Revocation propagation: không hứa kết thúc token trước khi mọi RS được cập nhật

Khi một JWT access token đã phát, nó có thể được nhiều RS kiểm offline. Để chặn trước `exp`, có thể dùng:

- **Denylist** theo `iss + jti`, lưu tới khi token chắc chắn hết hạn.
- **Grant/session security version** được token mang và RS tra state mới.
- **Opaque introspection** với cache TTL/freshness phù hợp.
- **Event-driven invalidation** qua broker/outbox có kiểm ordering, idempotency và replay.
- **Short-lived access token** để giới hạn cửa sổ stale, kết hợp chặn refresh.
- **Hybrid**: kiểm state online cho hành động tài chính/admin, JWT offline TTL ngắn cho thao tác ít nhạy cảm.

~~~mermaid
sequenceDiagram
    actor A as Alice
    participant RP as Shop Web
    participant AS as Authorization Server
    participant E as Event Bus
    participant RS1 as Orders API
    participant RS2 as Billing API
    A->>RP: Yêu cầu logout và revoke grant
    RP->>AS: POST /revoke hoặc grant revocation theo policy
    AS->>AS: Commit grant REVOKED
    AS-->>RP: Revocation response (không bảo đảm toàn RS)
    AS->>E: GrantRevoked(grantId, version)
    E-->>RS1: Deliver + apply
    RS1->>RS1: Invalidate cache / update deny state
    E-->>RS2: Deliver + apply
    RS2->>RS2: Invalidate cache / update deny state
    Note over RS1,RS2: Chỉ khi enforcement hoàn tất mới có căn cứ về phạm vi chặn tương ứng
~~~

### 12.1. Những mốc không được đánh đồng

~~~text
t0: user nhấn Logout
t1: RP session invalidated
t2: AS commit grant revoked
t3: AS publish revocation event
t4: RS A áp state mới
t5: RS B áp state mới
t6: test request bị từ chối tại mọi RS trong phạm vi
~~~

Một màn hình `/signed-out` có thể xuất hiện tại **t1** trong khi **t5 chưa xảy ra**. Nếu UI chỉ chứng minh local logout, nên diễn đạt như vậy.

### 12.2. Freshness budget và hiệu lực trong sự cố mạng

Ví dụ service tài chính cần “mọi thao tác phê duyệt bằng token bị revoke bị chặn trong tối đa 10 giây sau AS commit” — đây là **SLO minh họa**, không phải quy định RFC.

Hệ thống phải đo:

- Độ trễ AS commit → event publish.
- Broker/consumer lag và apply state mỗi RS.
- Introspection positive cache TTL.
- Replica staleness và multi-region replication.
- Các RS chưa kết nối lại/có event gap.
- Hành vi khi không kiểm được trạng thái: fail closed, hard serve-stale window hay fail open có chấp thuận rủi ro.

Nếu một region bị partition 15 phút và vẫn chấp nhận `grant=ACTIVE` cache vô thời hạn, không thể hứa revocation dưới 10 giây. Hãy dùng freshness deadline/readiness/fallback **và đo trên enforcement points**.

### 12.3. Session của BFF khác token của API

Với kiến trúc **Backend for Frontend (BFF)**:

~~~text
Browser:
    chỉ có cookie session (HttpOnly, Secure...).

BFF:
    giữ OAuth tokens trong server-side token store.

Orders API:
    nhận access token từ BFF.
~~~

Logout có thể invalidate browser session và xóa token store tại BFF khá chắc chắn. Tuy nhiên bản sao access token bị lộ trước đó vẫn cần RS revoke/expiry. BFF cũng phải ngăn race khi background refresh tạo token/session mới trong lúc logout.

## 13. Kết quả logout: trạng thái có căn cứ thay vì một boolean

Một backend nên ghi nhận **các bước đã hoàn thành** riêng biệt. Có thể dùng state machine nội bộ:

~~~mermaid
stateDiagram-v2
    [*] --> REQUESTED: User xác nhận logout
    REQUESTED --> LOCAL_ENDED: RP invalidate session
    LOCAL_ENDED --> OP_REQUESTED: Tạo RP-Initiated Logout redirect
    OP_REQUESTED --> RETURNED: Browser tới post-logout URI hợp lệ
    OP_REQUESTED --> OP_UNKNOWN: Timeout/browser không tới OP
    RETURNED --> LOCAL_CONFIRMED: Kiểm pending state + local state
    LOCAL_CONFIRMED --> TOKEN_REVOKE_PENDING: Token/grant revoke chưa được xác minh
    TOKEN_REVOKE_PENDING --> TOKEN_REVOKE_COMMITTED: AS đã ghi revoke theo contract
    TOKEN_REVOKE_COMMITTED --> RS_PROPAGATED: RS enforcement được xác nhận nếu được đo
    OP_UNKNOWN --> LOCAL_CONFIRMED: RP session vẫn đã bị vô hiệu
~~~

Đây là **mô hình quan sát minh họa**, không phải state machine chuẩn OIDC. Thứ tự revoke có thể được thực hiện **trước/đồng thời** với OP redirect, không nhất thiết theo thứ tự tuyến tính như sơ đồ. Một số trạng thái có thể không có bằng chứng xác minh được.

### 13.1. Phân biệt `requested`, `observed`, `verified`

| Dữ liệu | Có thể khẳng định điều gì? | Không thể khẳng định |
|---|---|---|
| User nhấn nút Logout | User thể hiện ý định | Session đã bị xóa |
| Backend invalidate S1 và commit | S1 không còn được RP chấp nhận theo thiết kế | OP session đã đóng |
| Browser nhận 302 | RP yêu cầu điều hướng | Đích đã xử lý logout |
| Browser về với state khớp | Callback tương quan request trước | Mọi OP/RP/RS đã xử lý |
| RP nhận logout token hợp lệ và commit | RP đã thực thi session logout trong phạm vi token | AS đã revoke T1/R1 |
| AS `/revoke` phản hồi thành công | Revocation request xử lý theo contract AS | Token T1 chắc chắn bị Orders API chặn |
| RS probe từ chối T1 sau revoke | RS/probe path đó đã chặn T1 | Tất cả đường truy cập, region và credential khác đã chặn |

### 13.2. Thiết kế UX không hứa quá mức

**Thông điệp có căn cứ khi chỉ local logout hoàn tất:**

> Bạn đã đăng xuất khỏi Shop Web trên trình duyệt này. Trạng thái đăng xuất tại các ứng dụng và thiết bị khác chưa được xác nhận.

**Khi OP logout request chưa hoàn tất:**

> Phiên Shop Web đã kết thúc. Không thể xác nhận đăng xuất tại nhà cung cấp đăng nhập; bạn có thể hoàn tất đăng xuất SSO theo hướng dẫn.

**Khi người dùng chọn logout mọi thiết bị nhưng propagation còn tiếp diễn:**

> Yêu cầu đăng xuất các thiết bị đã được ghi nhận. Một số phiên hoặc token đang được vô hiệu theo chính sách hệ thống.

Các câu trên là **mẫu nội dung**, chỉ dùng khi hệ thống có các trạng thái tương ứng. Không dùng từ “đã thu hồi hoàn toàn” nếu chỉ có HTTP 302/200.

### 13.3. Trang `/signed-out` không nên được dùng như API “xác minh logout”

Sai:

~~~java
// SAI: caller truy cập URL bất kỳ cũng được đánh dấu tất cả đã logout.
@GetMapping("/signed-out")
public String signedOut() {
    currentUser.setGlobalLogoutSucceeded(true);
    return "All devices logged out";
}
~~~

Vì đây là GET chưa chứng minh nguồn và không kiểm trạng thái, attacker/automation có thể kích hoạt đường đi, thay đổi audit hoặc khiến người dùng hiểu nhầm. Endpoint chỉ nên **render** trạng thái đã được backend xác minh trong pending logout transaction hợp lệ.

### 13.4. Một kết quả không rõ có thể là kết quả trung thực nhất

Nếu OP không cung cấp một cơ chế xác nhận đáng tin cậy cho phạm vi logout mà ứng dụng mong muốn, UI có thể nói **“không xác minh được trạng thái SSO”**. Đó là cách biểu diễn uncertainty thực tế, không phải lỗi UX. Đừng phát minh một `logoutConfirmed=true` vì “browser đã đi tới OP”.

## 14. Java/Spring Security: RP-Initiated Logout không có nghĩa là global revocation

Spring Security hỗ trợ OIDC logout cho ứng dụng dạng **OAuth2 Login/Relying Party**. Có thể cấu hình `OidcClientInitiatedLogoutSuccessHandler` để chuyển user agent tới `end_session_endpoint` của OP khi OP công bố hỗ trợ.

### 14.1. Client registration dùng OIDC

~~~yaml
# application.yml - ví dụ client OIDC trên backend Shop Web
spring:
  security:
    oauth2:
      client:
        registration:
          shop:
            provider: company
            client-id: shop-web
            client-secret: ${OAUTH_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
        provider:
          company:
            issuer-uri: https://login.example.com
~~~

Ví dụ dành cho **confidential web backend**, không đặt client secret trong SPA/browser. Production cần kiểm issuer, redirect URIs, TLS, Authorization Code + PKCE S256 khi áp dụng, session/cookie/CSRF và token storage.

### 14.2. Cấu hình OIDC logout handler

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.oidc.web.logout.OidcClientInitiatedLogoutSuccessHandler;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ShopWebSecurityConfig {

    @Bean
    OidcClientInitiatedLogoutSuccessHandler oidcLogoutSuccessHandler(
            ClientRegistrationRepository registrations) {
        OidcClientInitiatedLogoutSuccessHandler handler =
            new OidcClientInitiatedLogoutSuccessHandler(registrations);

        // Đích quay về sau khi OP xử lý RP-Initiated Logout.
        // Phải có registration/allowlist phù hợp ở OP.
        handler.setPostLogoutRedirectUri("{baseUrl}/signed-out");
        return handler;
    }

    @Bean
    SecurityFilterChain webSecurity(
            HttpSecurity http,
            OidcClientInitiatedLogoutSuccessHandler logoutHandler)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public", "/signed-out").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .logout(logout -> logout
                .logoutUrl("/logout")
                .logoutSuccessHandler(logoutHandler)
                .invalidateHttpSession(true)
                .clearAuthentication(true)
                .deleteCookies("JSESSIONID"));

        return http.build();
    }
}
~~~

Đây là **mẫu cấu hình minh họa** cho Spring Security servlet với các API tương ứng phiên bản; cần kiểm theo dependency thực tế, client logout metadata và reverse-proxy/base URL. Nếu ứng dụng dùng `SESSION` qua Spring Session thay `JSESSIONID`, phải xử lý **đúng cookie name/path/domain** và session store.

**Lưu ý quan trọng:** handler này phục vụ **điều hướng OIDC RP-Initiated Logout**. Chỉ cấu hình nó **không có nghĩa**:

- Đã gọi OAuth revocation endpoint với refresh token.
- Đã thu hồi toàn bộ authorization grants.
- Đã phát Back-Channel Logout tới các RPs khác.
- Orders API đã biết các JWT access tokens phải bị chặn.
- User đã logout mọi thiết bị.

### 14.3. Cần quan sát local session state thật

Spring Security có các logout handlers như `SecurityContextLogoutHandler` để clear authentication/invalidate HTTP session. Nhưng trong ứng dụng có BFF, cache hoặc token store tùy chỉnh, cần dọn **các state riêng**.

Một thiết kế pseudocode:

~~~java
// Pseudocode: không phải API Spring Authentication/logout thật.
LocalLogoutResult endLocalSession(
        VerifiedBrowserSession browserSession,
        LogoutIntent intent) {

    return transaction.run(() -> {
        // Đánh dấu session không còn hợp lệ ở server, không chỉ xóa cookie.
        sessionStore.revoke(
            browserSession.sessionId(),
            browserSession.securityVersion() + 1);

        // Không hồi sinh session qua race refresh/login.
        pendingRefreshStore.disableForSession(
            browserSession.sessionId());

        // Tạo request revoke grant để worker riêng tiếp tục nếu policy cần.
        if (intent.shouldRevokeGrant()) {
            securityOutbox.enqueueGrantRevoke(
                browserSession.grantId());
        }

        return new LocalLogoutResult(
            browserSession.sessionId(),
            true,  // local session ended
            intent.shouldRevokeGrant()  // revoke requested, chưa chứng minh hoàn tất
        );
    });
}
~~~

Mẫu này không tự tích hợp Spring LogoutFilter, transaction hoặc OP. Các type là **giả định**, nhưng minh họa ranh giới: local session revoke được **commit**, yêu cầu revoke grant được ghi bền vững, còn tiến độ AS/RS phải quan sát riêng.

Đừng hủy session trước khi lấy hết metadata cần thiết cho revocation, rồi gọi revoke với `refresh_token=null` và **vẫn báo global success**. Ngược lại, cũng không giữ session active chỉ vì RPC revoke tạm lỗi.

### 14.4. Một `LogoutSuccessHandler` có thể chỉ gửi redirect

Tên “success handler” của framework thường nghĩa là **thực hiện hành động sau local logout trong filter chain**, không chứng minh OP logout đã hoàn tất hay mọi token đã revoke. Trong nhiều trường hợp handler phát HTTP redirect rồi kết thúc response.

Không xây dashboard “OP logout confirmed” từ việc `OidcClientInitiatedLogoutSuccessHandler` đã chạy xong; nó không đợi mọi RPs/RS xác nhận.

### 14.5. Backend kiểm session cho endpoint nhạy cảm

Ví dụ controller chỉ cho phép authenticated session:

~~~java
@GetMapping("/api/my-orders")
public List<OrderDto> myOrders(Authentication authentication) {
    // Framework authentication phải được giải quyết từ session/credential
    // vẫn hợp lệ, không chỉ từ thông tin UI lưu trong tab.
    VerifiedActor actor =
        principalMapper.fromCurrentValidatedAuthentication(authentication);

    return ordersService.findAccessibleOrders(actor);
}
~~~

Nếu session S1 đã bị revoke, request sau bằng cookie S1 không được tạo authentication hợp lệ. Dù session hợp lệ, service vẫn phải kiểm **tenant/ownership/action**; logout không thay business authorization.

## 15. Java: Back-Channel Logout handler phải xác minh logout token

RP có thể được OP cấu hình nhận Back-Channel Logout qua endpoint HTTPS riêng. Request thường gửi **`logout_token`** trong form body, không giống authorization callback.

~~~http
POST /oidc/backchannel-logout HTTP/1.1
Host: shop.example.com
Content-Type: application/x-www-form-urlencoded

logout_token=<SIGNED_LOGOUT_JWT>
~~~

**Không tự chấp nhận mọi JWT có `sid`**, và không lấy `sub`/`sid` trực tiếp từ một JSON body không xác minh để xóa session của người khác.

### 15.1. Pipeline kiểm tra logout token

~~~java
// Pseudocode: các type bên dưới là thành phần ứng dụng,
// không phải Spring Security API có sẵn.
void processBackChannelLogout(
        String rawLogoutToken,
        TrustedOidcRegistration registration) {

    VerifiedLogoutToken logout = logoutTokenVerifier.verify(
        rawLogoutToken,
        registration.expectedIssuer(),
        registration.clientId(),
        registration.trustedSigningKeys(),
        registration.allowedAlgorithms());

    // verifier phải kiểm iss/aud/iat/jti/events và các ràng buộc của spec;
    // có sub hoặc sid phù hợp; KHÔNG có nonce.
    require(logout.events().contains(
        "http://schemas.openid.net/event/backchannel-logout"));
    require(logout.subject() != null || logout.sessionId() != null);
    require(!logout.hasNonce());

    transaction.run(() -> {
        if (!logoutReplayStore.markSeenOnce(
                registration.issuer(), logout.jwtId())) {
            return; // duplicate: idempotent
        }

        List<LocalSession> sessions = sessionStore.findMatching(
            registration.issuer(),
            registration.clientId(),
            logout.subject(),
            logout.sessionId());

        for (LocalSession session : sessions) {
            sessionStore.invalidate(session.id());
        }
    });
}
~~~

`verify` phải thực thi validation **toàn bộ** theo Back-Channel Logout spec và profile RP đã đăng ký: chữ ký, issuer, audience, algorithm/key source, event, `iat`/freshness policy, `jti` replay, `sub`/`sid` semantics; không để code ứng dụng chỉ kiểm field `events` rồi coi token đã tin cậy.

### 15.2. Thao tác idempotent và đồng nhất trên nhiều nodes

Nếu OP retry cùng logout token:

~~~text
POST #1: logout_token jti=evt-101  -> invalidate S1.
POST #2: logout_token jti=evt-101  -> replay/duplicate.
~~~

Handler nên có replay protection và không thực hiện lại side effects nguy hiểm. Nếu OP timeout sau khi RP đã commit, retry không làm session **hoạt động trở lại**. Session store/checkpoint phải dùng persistence/consistency thích hợp qua các RP nodes.

Không `ack` request trước khi cập nhật session state xong nếu hệ thống không có outbox/recovery khác; nếu tiến trình crash sau ack, OP có thể nghĩ logout đã xử lý trong khi S1 vẫn active.

### 15.3. `sid` có thể thiếu theo profile, cần xử lý đúng phạm vi

Logout token có thể mang `sid`, `sub` hoặc cả hai theo spec và registration:

- Nếu có `sid`, RP dùng mapping từ OP session tới local sessions tương ứng.
- Nếu chỉ có `sub`, RP xác định phạm vi các sessions của subject đó theo issuer/client và profile.
- Không dùng email làm user identity thay `iss + sub`.
- Không lấy `sid` raw từ public query làm quyền revoke một local session bất kỳ.
- Nếu RP không thể xác định phiên chịu tác động một cách an toàn, **không xóa ngẫu nhiên** hoặc mặc định coi message đã thực thi đầy đủ; cần error/audit và xử lý theo policy.

### 15.4. Back-channel có thể chặn RP session, nhưng RS vẫn cần revoke policy

Sau khi RP session S1 invalidated, JWT T1 đã gửi đến Orders API có thể vẫn được chấp nhận offline. Vì thế khi security requirement đòi **immediate access termination**, Back-Channel Logout phải được nối tới AS grant/session revoke hoặc RS state checks theo thiết kế; không coi một JWT logout token là lệnh tự động làm mọi OAuth access tokens hết hạn.

## 16. Tránh login tự động trở lại sau logout

Một hiện tượng UX gây hiểu nhầm:

~~~text
Alice nhấn Logout khỏi Shop Web.
Shop Web invalidate local S1.
Alice mở /account lần nữa.
Shop Web chuyển tới OP với OIDC authorization request.
OP SSO session P1 vẫn còn.
OP trả authorization code mới mà không hỏi password.
Shop Web tạo local session S2.
~~~

Đây **không nhất thiết là lỗi Spring**: local logout và OP SSO session là hai state khác nhau. Nếu chỉ local S1 bị chấm dứt, việc OP còn session có thể cho phép login lại nhanh.

### 16.1. Tách ba kỳ vọng của người dùng

1. **“Đăng xuất khỏi ứng dụng này”**: S1 kết thúc; mở lại app có thể có SSO login nếu OP còn session.
2. **“Đăng xuất khỏi nhà cung cấp đăng nhập”**: cần OP logout thực sự theo RP-Initiated Logout/profile.
3. **“Đăng xuất mọi thiết bị”**: cần global session/grant revocation theo phạm vi và confirmation policy.

Không sửa bằng cách xóa mọi OP session trên mọi thiết bị khi UI chỉ yêu cầu logout một app.

### 16.2. `prompt=login` không chứng minh session cũ đã logout

OIDC có tham số như `prompt=login` để yêu cầu OP tái xác thực theo profile. Nó hữu ích cho một số luồng, nhưng:

- Không chứng minh tất cả các session cũ đã bị revoke.
- Không thu hồi bearer access tokens đã cấp.
- Không tự chặn refresh tokens đã bị đánh cắp.
- Không thay RP/session invalidation và resource authorization.

Tương tự, một kết quả `prompt=none` có thể phụ thuộc cookies/browser policy, nên **không được dùng độc lập làm proof of global logout**.

### 16.3. Mobile/SPA và logout nhiều lớp

Với native/mobile app hoặc SPA:

- Xóa credential khỏi secure storage hoặc bộ nhớ client theo kiến trúc.
- Thu hồi refresh/grant khi policy yêu cầu và công nghệ cho phép.
- Điều hướng OP logout qua browser/system browser theo profile phù hợp.
- Chặn session/token ở backend/RS khi yêu cầu bảo mật cần.
- Không để app backup, crash logs hoặc deep links giữ bearer token.

Với native app, browser/system SSO session và application session có thể độc lập. **Một redirect/deep-link về app không chứng minh cookies của browser khác đã được xóa**.

## 17. HTTP status và lỗi: không biến timeout thành thành công giả

### 17.1. Sự kiện nào mang ý nghĩa nào?

| Tín hiệu | Kết luận hợp lý | Không thể kết luận |
|---|---|---|
| RP `302 Location` tới OP | Browser được yêu cầu đi tới OP | OP session đã kết thúc |
| OP `302` về RP | OP điều hướng user agent theo contract | Mọi RPs và RS đã revoke |
| RP `/signed-out` trả 200 | Trang đã render thành công | Token, session ở OP/RS đã vô hiệu |
| RP local session record = REVOKED | RP có thể từ chối S1 theo store của mình | R1/T1 bị thu hồi |
| AS `/revoke` trả 200 | Revocation request được xử lý theo RFC 7009 | JWT T1 không còn được RS nào nhận |
| RP back-channel endpoint trả 200 | Handler thông báo xử lý theo contract | Tất cả RP khác đã xử lý |
| RS introspection `active=false` | Token inactive theo AS trong ngữ cảnh kiểm | Mọi cache khác đều cập nhật |
| Orders API từ chối T1 sau revoke | Một enforcement path đã từ chối T1 | Mọi API/region/credential khác đều bị chặn |

### 17.2. Kịch bản network timeout

~~~text
RP gọi AS revoke R1.
AS commit REVOKED.
Response trên đường về bị timeout.
RP không biết AS đã commit hay chưa.
~~~

**Đừng** kết luận “revoke thất bại” hoặc “revoke thành công toàn bộ” chỉ từ timeout. Đây là **kết quả chưa biết**. Thao tác revoke được thiết kế để idempotent khi phù hợp; client/backend có thể retry có kiểm soát hoặc truy vấn trạng thái theo kênh tin cậy nếu contract cho phép.

Đặc biệt, một timeout phải không làm **local RP session sống lại** hoặc tự tạo lại refresh token.

### 17.3. Phản hồi không nên lộ thông tin phiên

Không trả:

~~~json
{
  "logout_error": "User alice@example.com still has refresh token R1=...",
  "active_session_cookie": "...",
  "access_token": "..."
}
~~~

Khi cần cho người dùng biết kết quả, dùng mô tả ngắn, không chứa raw token/refresh token/session ID, hoặc thông tin các thiết bị khác ngoài quyền quan sát của user. Cần audit chi tiết thì ghi metadata theo chính sách bảo mật.

### 17.4. Thực thi local logout dù remote logout không khả dụng

Một workflow nên giữ bất biến:

~~~text
Nếu RP đã commit invalidate S1
    -> Không cho S1 hoạt động lại do remote logout lỗi.

Nếu OP/AS revoke chưa xác minh
    -> Theo dõi, retry hoặc cảnh báo theo policy.

Nếu RS chưa hội tụ trạng thái revoke
    -> Không hứa "mọi access token đã bị chặn".
~~~

**Fail-open** khi AS/RS state không xác minh được có thể cho token bị revoke tiếp tục được dùng. Với hành động nhạy cảm, cần thiết kế fail-closed hoặc freshness hard bound, không chỉ một banner logout.

## 18. Thiết kế callback và trạng thái logout an toàn

Một trang sau logout thường là **public page** vì user vừa mất phiên đăng nhập. Điều này đúng về UX nhưng đặt ra câu hỏi: public page có thể **kiểm chứng trạng thái bảo mật nào** mà không dùng một session đã bị invalidate?

### 18.1. Một bảng pending logout tách khỏi session

Schema minh họa:

~~~sql
CREATE TABLE pending_logouts (
    id VARCHAR(64) PRIMARY KEY,
    correlation_key_hash VARCHAR(128) NOT NULL UNIQUE,
    issuer_id VARCHAR(256) NOT NULL,
    client_registration_id VARCHAR(128) NOT NULL,
    local_session_ref VARCHAR(128) NOT NULL,
    local_session_revoked BOOLEAN NOT NULL,
    op_request_initiated BOOLEAN NOT NULL,
    grant_revocation_status VARCHAR(32) NOT NULL,
    started_at TIMESTAMP NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    callback_consumed BOOLEAN NOT NULL DEFAULT FALSE
);
~~~

Đây **không phải schema OIDC bắt buộc** và không chứa đầy đủ dữ liệu nghiệp vụ, indexes, consent hoặc retention. `correlation_key_hash` có thể là HMAC dùng key được quản lý an toàn trên random state; nếu lưu state thô, phải có access control/TTL nghiêm ngặt.

**Không lưu raw refresh token, access token, cookie hay ID token ở bảng này.** Nếu cần gọi revocation endpoint, credential phải được giữ trong protected token store riêng và được xử lý theo lifecycle an toàn.

### 18.2. Bắt đầu logout

~~~java
// Pseudocode: các type là thành phần ứng dụng minh họa.
LogoutRedirect beginLogout(
        VerifiedBrowserSession browser,
        LogoutScope requestedScope) {

    LogoutState state = secureRandomState.create();

    transaction.run(() -> {
        sessionStore.invalidate(browser.sessionId());
        pendingLogoutStore.create(
            state.hmacLookupKey(),
            browser.oidcIssuer(),
            browser.clientRegistration(),
            browser.sessionId(),
            true, // LOCAL_SESSION_ENDED
            requestedScope,
            clock.instant().plusSeconds(180));

        if (requestedScope.includesGrantRevoke()) {
            securityOutbox.requestGrantRevocation(
                browser.grantReference());
        }
    });

    browserCookiePolicy.expireSessionCookie();
    // URL của OP lấy từ trusted discovery/registration, không từ caller.
    return oidcLogoutUriBuilder.forTrustedIssuer(
        browser.oidcIssuer(),
        browser.clientRegistration(),
        state.value(),
        browser.idTokenHintReference());
}
~~~

**Không biên dịch trực tiếp** pseudocode này như API Spring. Hành vi `browserCookiePolicy.expireSessionCookie` trên HTTP response phải được gắn vào filter/controller pipeline; `idTokenHintReference` là một reference tới dữ liệu được bảo vệ, không phải URL tự tạo từ input browser. Tầng application logout cần đảm bảo các thay đổi local state đã được commit phù hợp trước khi trả redirect.

### 18.3. Nhận callback từ post-logout URI

~~~java
// Pseudocode: GET này không đăng xuất thêm phiên nào.
LogoutView postLogoutLanding(String receivedState) {
    if (receivedState == null || receivedState.isBlank()) {
        return LogoutView.genericSignedOutPage();
    }

    PendingLogout tx =
        pendingLogoutStore.findByHmacState(receivedState);

    if (tx == null || tx.isExpired() || tx.callbackConsumed()) {
        return LogoutView.genericSignedOutPage();
    }

    pendingLogoutStore.consumeCallbackOnce(tx.id());

    // Có thể hiển thị local success vì store có bằng chứng local revocation.
    // Callback không phải bằng chứng OP đã revoke mọi grants/tokens.
    return LogoutView.forVerifiedLocalResult(
        tx.localSessionRevoked(),
        tx.grantRevocationStatus());
}
~~~

Lưu ý an toàn:

- **GET không được đánh dấu lại `session=REVOKED` chỉ vì nhận state.** Bước logout local đã xảy ra trước đó.
- **Không đổi `grantRevocationStatus` thành CONFIRMED** chỉ dựa vào callback.
- Kiểm state random, one-time, TTL; chống direct calls và replay.
- Có ràng buộc issuer, client registration và request context ở pending record; không dựa vào callback tự khai để chọn issuer.
- Tránh lộ những session của user khác trên public page; nếu cần hiển thị chi tiết, phải có cơ chế xác thực/ủy quyền mới đúng.

### 18.4. Không biến trạng thái logout thành oracle

Một endpoint:

~~~text
GET /logout-status?sessionId=someone-elses-id
~~~

trả JSON chứa user email, danh sách devices, refresh-token state hoặc token IDs sẽ gây lộ dữ liệu. Dù đã logout, dữ liệu session/grant vẫn nhạy cảm. Status endpoint có thể:

- Chỉ nhận random one-time correlation token rất ngắn hạn.
- Trả metadata **tối thiểu** cho UX, không chứa PII/credentials.
- Bảo vệ chống enumeration/rate limit và sử dụng TLS.
- Không dùng correlation token như credential để revoke tùy ý sessions.
- Nếu user muốn xem lịch sử thiết bị/grants chi tiết, yêu cầu **authenticated account settings** thay vì public callback.

### 18.5. Không dùng callback để “xác nhận logout toàn bộ”

Một cách tổ chức rõ ràng:

~~~text
Local session:
    authoritative RP session store.

OP SSO:
    OP protocol + nguồn trạng thái OP cung cấp theo contract.

Refresh grant:
    AS grant/token store và revocation receipt.

Access token:
    RS introspection/denylist/epoch và enforcement observation.

Browser callback:
    chỉ là correlation/navigation signal.
~~~

Mỗi ranh giới cần **bằng chứng riêng** nếu sản phẩm thực sự muốn xác nhận trạng thái đó.

## 19. Threat model: khi redirect bị dùng làm tín hiệu bảo mật giả

| Lỗi hoặc tấn công | Điều xảy ra | Kiểm soát chính |
|---|---|---|
| **Fake callback** | Attacker vào thẳng `/signed-out` để tạo success giả | Pending one-time state + server evidence |
| **State replay** | Dùng lại URL callback cũ | CSPRNG, TTL, consume-once, request binding |
| **Open redirect** | `/logout?returnTo=evil.example` đưa user đến fake login | Registered post-logout URI và allowlist local path |
| **Logout CSRF** | Website lạ kích hoạt `GET /logout` tự xóa session | State-changing logout intent qua POST/CSRF theo kiến trúc |
| **Browser navigation failure** | RP 302 nhưng OP không nhận | Local session invalidate không phụ thuộc OP callback |
| **OP session còn sống** | User login lại im lặng sau local logout | RP-Initiated Logout đúng profile, UX mô tả phạm vi |
| **Front-channel iframe blocked** | RP khác không nhận logout signal | Back-channel/session state/fallback, không hứa global |
| **Back-channel forgery** | Attacker gửi JWT/JSON có `sid` giả | Verify signed logout token và issuer/audience/events |
| **Back-channel replay** | Một logout token được gửi lại | `jti` replay protection, idempotency |
| **Cross-issuer sid collision** | Logout nhầm session thuộc OP khác | Bind `iss + sid/sub + RP client` |
| **Cookie path mismatch** | Browser vẫn gửi session cookie | Xóa đúng name/domain/path; server invalidate |
| **Session token cache** | Xóa cookie nhưng BFF lưu refresh token | Đồng bộ BFF token store/revocation |
| **JWT còn hiệu lực** | RS vẫn nhận stolen access token | Denylist/epoch/introspection hoặc expiry policy |
| **Opaque introspection stale** | `active=true` cache sau revoke | TTL/invalidation/state freshness |
| **Refresh family còn sống** | Client/attacker tiếp tục xin token mới | AS revoke đúng grant/family và reuse detection |
| **Race refresh/logout** | Refresh request tạo token mới sau logout | Atomic grant/session version và issue-time checks |
| **Logout toàn user khi chỉ một device** | Phạm vi xóa quá rộng, gây DoS | Scope/grant/device binding |
| **Logout một device khi user chọn all** | Vẫn còn sessions khác | Global policy và convergence checks |
| **Key compromise bỏ sót JWKS cache** | RS tin khóa bị lộ | Emergency key invalidation + propagation |
| **Cross-tenant logout** | User A yêu cầu xóa session tenant B | Caller authority + tenant/session binding |
| **Lộ id_token_hint trong log** | Metadata/claims trong ID token bị thu thập | URL logging redaction, TLS, short token lifetime |
| **Ủy quyền sai sau logout** | Access token còn dùng để đọc dữ liệu Bob | Token validation và resource-level authorization |

### 19.1. `id_token_hint` và dữ liệu trong logout URL

Trong RP-Initiated Logout, `id_token_hint` thường được truyền trên redirect tới OP. **ID token không phải access token**, nhưng vẫn chứa claims cá nhân, có thể bị ghi vào browser history, logs của proxy hoặc telemetry nếu URL bị thu thập.

Giảm rủi ro:

- Chỉ gửi cho **OP end_session_endpoint tin cậy** được lấy từ metadata đã xác minh.
- Không log nguyên `Location`, query string hoặc raw ID token hint.
- Cấu hình Referrer-Policy hợp lý và tránh bên thứ ba trên các trang có dữ liệu nhạy cảm.
- Không gửi access/refresh token, client secret hoặc session cookie trong logout URL.
- Không để `post_logout_redirect_uri` là open redirect.
- Bảo vệ token trong server-side store thay vì đặt vào support tickets để debug.

Không tự xóa `id_token_hint` khỏi flow một cách tùy tiện nếu OP yêu cầu tham số để xác định đúng session/client. Phải tuân thủ **profile OP và threat model**.

### 19.2. Logout và credential đã bị đánh cắp

Nếu attacker đã sao chép access token trước logout:

~~~text
RP cookie invalidated: YES
OP session ended: YES
Attacker still has bearer access token T1: YES
RS validates T1 offline until exp: YES
~~~

Kết quả là attacker vẫn có thể gọi API nếu RS không có early revocation control. Đây là lý do **logout UI và security incident response không thể thay token lifecycle policy**.

### 19.3. Cấm session resurrection khi restore/replication lag

Một local session có thể bị revoke ở primary store nhưng một node đọc replica cũ lại thấy ACTIVE. Nếu logout yêu cầu chặn ngay, phải bảo đảm **consistency/epoch** của session store và load balancer:

~~~text
Node A: S1 REVOKED version=5.
Node B: replica cache S1 ACTIVE version=4.
Node B nhận request cookie S1.
~~~

Node B không nên cho S1 hoạt động nếu freshness policy yêu cầu version 5. Các chiến lược: read authoritative state, cache invalidation, monotonically increasing security epoch, fail closed khi state quá cũ.

### 19.4. Không để lỗi logout dẫn đến quyền cao hơn

Nếu một service có service token mạnh hơn user Alice, nó không được xử lý logout cleanup bằng cách “cấp tạm service token cho browser” để retry. Dùng service credential chỉ ở server-side boundary, giới hạn action và ghi audit. **Logout thất bại không cho phép bỏ qua authentication/authorization.**

## 20. Ma trận kiểm thử: browser quay về chưa thể là tiêu chí duy nhất

Một bộ test tốt phải kiểm **trạng thái thật** ở RP, OP, AS và RS trong giới hạn có thể quan sát, thay vì chỉ assert `302 Location` hoặc HTML “Đã đăng xuất”.

### 20.1. Local RP session và cookies

| Trường hợp | Hành vi mong đợi |
|---|---|
| User nhấn POST `/logout` hợp lệ với CSRF token | RP invalidate server-side session hiện tại và clear cookie đúng cách |
| Browser không đi tới OP vì mất mạng sau 302 | Session local vẫn **đã bị invalidate** |
| Cookie đã xóa ở browser nhưng server session record còn ACTIVE | **Test fail**: cookie bị đánh cắp vẫn dùng được |
| RP invalidate session nhưng cookie name/path/domain xóa sai | Kiểm server từ chối session cũ; sửa cookie cleanup |
| Browser gửi lại cookie S1 cũ sau logout | Request protected phải bị từ chối |
| Hai tabs cùng dùng S1; tab A logout | Tab B không truy cập protected API bằng S1 |
| Request đang xử lý ở tab B khi logout xảy ra | Không cho session/token tái hoạt hóa trái policy |
| Browser back về trang private được cache | Không hiển thị dữ liệu nhạy cảm trái chính sách cache |
| Local logout được gọi hai lần | Idempotent hoặc xử lý an toàn, không hồi sinh state |
| GET `/logout` từ website ngoài | Không thực hiện state-changing logout trái CSRF policy |
| RP session có `HttpOnly` cookie | Frontend không cần đọc cookie để thực hiện invalidation |
| User logout thiết bị A | Session B không bị vô hiệu nếu UX/policy chỉ logout A |

### 20.2. RP-Initiated Logout và post-logout redirect

| Trường hợp | Hành vi mong đợi |
|---|---|
| OP có `end_session_endpoint` đáng tin | Handler điều hướng tới endpoint đã discover/đăng ký |
| `post_logout_redirect_uri` không đăng ký với OP | OP từ chối hoặc xử lý theo contract, RP không giả định logout thành công |
| Callback `/signed-out` được gọi trực tiếp | Không đánh dấu OP/token global success |
| Callback có `state` không khớp | Không gắn callback với pending request |
| Callback dùng lại state đã consumed | Từ chối correlation/replay |
| State quá hạn | Không dùng để thay đổi session/grant state |
| State đúng nhưng refresh token chưa revoke | UI chỉ báo trạng thái đã có bằng chứng; không báo token đã revoke |
| Browser nhận 302 rồi đóng tab | Không yêu cầu callback để invalidate local RP session |
| OP logout thành công nhưng redirect callback timeout | Local session vẫn ended; OP status có thể chưa xác minh ở RP |
| OP session còn hoạt động sau local logout | UI không báo global logout; login lại theo OP policy có thể xảy ra |
| OP không hỗ trợ end-session metadata | Sử dụng fallback rõ phạm vi, không tự đoán `/logout` |
| Caller gửi `returnTo=https://attacker.example` | Không open redirect |
| Đổi `X-Forwarded-Host` không tin cậy | Không đổi trusted post-logout domain |
| ID token hint bị log trong full Location header | Security/privacy test fail |

### 20.3. Front-channel và back-channel

| Trường hợp | Hành vi mong đợi |
|---|---|
| Browser chặn third-party iframe | Front-channel chưa chắc tới RP; không có global success giả |
| Front-channel logout URI nhận request không phù hợp session/issuer | Không logout nhầm session của user khác |
| Back-channel nhận logout token chữ ký sai | Từ chối |
| JWT có `iss` không tin cậy | Từ chối |
| JWT `aud` dành cho client khác | Từ chối |
| Logout token thiếu `events` đúng spec | Từ chối |
| Logout token có `nonce` | Từ chối theo Back-Channel Logout spec |
| Logout token không có cả `sub` và `sid` | Từ chối |
| Logout token thiếu/không hợp lệ `iat` hoặc `jti` | Từ chối theo spec |
| Logout token có `sid` của OP khác | Không invalidate sessions sai issuer |
| Logout token hợp lệ theo `sid` | Invalidate đúng RP sessions liên kết với OP session |
| Logout token hợp lệ theo `sub` khi profile cho phép | Xử lý phạm vi sessions của subject đúng policy |
| Hai lần gửi cùng `jti` | Idempotent/replay-safe |
| RP commit logout nhưng response timeout; OP retry | Không hồi sinh session, retry an toàn |
| RP node crash sau nhận token trước commit | Không báo completion nếu state chưa được lưu |
| Một RP không nhận logout vì offline | Có retry/giám sát/fallback, không nói tất cả đã logout |

### 20.4. OAuth grants, refresh và access tokens

| Trường hợp | Hành vi mong đợi |
|---|---|
| RP logout nhưng không gọi revoke R1 | Test khẳng định R1 có thể còn hiệu lực theo policy, không giả định mất hiệu lực |
| AS xử lý revoke R1 | Refresh bằng R1 không cấp token mới nếu đã revoke |
| RFC 7009 trả 200 cho token không tồn tại | Không suy token từng tồn tại hay RS đã cập nhật |
| Client A cố revoke token client B | AS không cho revoke trái client binding |
| R1 đã rotation thành R2 trước logout | Family/grant xử lý theo policy, không bỏ sót R2 |
| Hai refresh requests đồng thời với logout | Không tạo token mới từ grant đã revoke trái policy |
| JWT access token còn hạn sau local/OP logout | Có thể tiếp tục hợp lệ nếu không có early revocation control; test phản ánh đúng contract |
| JWT có `jti` bị denylist | RS từ chối trong freshness budget |
| Opaque access token `active=false` sau revoke | RS từ chối |
| Introspection cache `active=true` trước revoke | Cache hết hạn/invalidate trong SLA |
| RS region B không nhận revocation event | Fail behavior đúng policy, không silent allow quá freshness budget |
| Client credentials workload token không gắn user session | Không bị revoke tùy tiện chỉ vì Alice logout |
| Token audience Billing API được gửi đến Orders API | Từ chối dù không nằm trên denylist |
| Token hợp lệ nhưng user không có quyền trên order | Từ chối theo resource authorization |

### 20.5. Kiểm thử phân tán và sự cố

1. Tạo test user, ít nhất hai RP sessions và hai test access tokens còn hạn.
2. Gọi local logout ở một RP, kiểm tra server session không còn truy cập được.
3. Cố tình ngắt trình duyệt ngay sau HTTP 302 tới OP, xác nhận local logout **vẫn có hiệu lực**.
4. Mô phỏng OP vẫn có SSO session, xác định UX và login lại đúng profile.
5. Gửi callback `/signed-out` giả hoặc state replay, xác minh không thay trạng thái grant.
6. Với Back-Channel Logout, gửi logout token fixture hợp lệ và các biến thể chữ ký/audience/events/sid sai.
7. Với grant revoke, kiểm refresh token bị chặn và đo thời gian RS từ chối access token theo SLO.
8. Mô phỏng positive introspection cache stale, broker pause, consumer restart, multi-region.
9. Kiểm không có đường API nội bộ bypass gateway chấp nhận bearer token chịu revoke.
10. Kiểm log/error/redirect không chứa raw access/refresh/ID tokens hoặc session cookie.

Các bài test phải dùng **fixtures riêng**, không dùng credential production để thử replay hoặc rò logging.

## 21. Tình huống tự suy luận

### Tình huống A — quay lại trang “Đã đăng xuất”

Alice nhấn logout. Browser về `/signed-out?state=s1` và trang hiển thị thành công. Backend chưa có bước revoke refresh token.

**Câu hỏi:** Có thể tuyên bố refresh token đã mất hiệu lực không?

**Trả lời:** Không. Redirect và state không thay thế kết quả AS token revocation. Chỉ tuyên bố những trạng thái đã được kiểm như local session invalidation.

### Tình huống B — không tới được OP

Shop Web invalidate S1, trả 302 sang OP nhưng browser mất mạng.

**Câu hỏi:** Có nên phục hồi S1 để user thử logout lại không?

**Trả lời:** Không. Local session đã bị chấm dứt cần tiếp tục bị chặn. Có thể hướng dẫn thử hoàn tất SSO logout, nhưng không hồi sinh session cũ vì remote logout thất bại.

### Tình huống C — fake callback

Attacker gọi `https://shop.example.com/signed-out?state=random` rồi API log đánh dấu `globalLogout=true`.

**Câu hỏi:** Sai ở đâu?

**Trả lời:** Endpoint tin một HTTP GET và query tự khai để tạo security state. Cần pending one-time state, server-side evidence và không coi callback là proof revoke.

### Tình huống D — state khớp hoàn toàn

Browser về với state đúng, chưa dùng và còn hạn.

**Câu hỏi:** Điều này chứng minh OP đã gửi logout token cho mọi RP?

**Trả lời:** Không. Nó chỉ cung cấp correlation cho browser return; không xác nhận front/back-channel delivery hay RS token enforcement.

### Tình huống E — hai ứng dụng cùng SSO

Alice logout từ Shop Web, nhưng Helpdesk vẫn giữ RP session S2 vì front-channel iframe bị browser chặn.

**Câu hỏi:** Có thể xảy ra không?

**Trả lời:** Có. Browser-based logout delivery có các giới hạn như third-party cookie/iframe. Cần Back-Channel Logout hoặc cơ chế session state đáng tin phù hợp nếu yêu cầu SSO logout rộng hơn.

### Tình huống F — ID token hint trong URL

Security logging ghi đầy đủ `Location: https://login.example.com/logout?id_token_hint=...`.

**Câu hỏi:** Có nên để log nguyên URL?

**Trả lời:** Không. ID token hint không phải access token nhưng có claims nhạy cảm; redaction URL query và giới hạn logging là cần thiết. Không để refresh/access token hoặc client secret vào logout URL.

### Tình huống G — cookie đã bị xóa

Browser không còn cookie SESSION, nhưng attacker có bản sao session cookie cũ và server store vẫn ACTIVE.

**Câu hỏi:** Attacker có thể tiếp tục dùng không?

**Trả lời:** Có thể. Xóa cookie phía browser không đủ. RP phải invalidate session ở server, dùng version/epoch khi cần và kiểm ở mỗi request.

### Tình huống H — tab khác vẫn hiện tên Alice

Tab A logout, tab B vẫn hiển thị dashboard trong bộ nhớ nhưng API trả 401.

**Câu hỏi:** Logout có thất bại không?

**Trả lời:** Backend có thể đã chặn session đúng; tab B có UI state/cache stale. Cần đồng bộ UX và ngăn render dữ liệu nhạy cảm sau logout, nhưng không suy server session còn sống chỉ từ UI cũ.

### Tình huống I — đăng nhập lại ngay

Alice logout local khỏi Shop Web rồi mở lại trang; OP còn SSO session và cấp login mới.

**Câu hỏi:** Vì sao không hiện màn nhập mật khẩu?

**Trả lời:** Local RP logout và OP SSO session khác nhau. Nếu UX yêu cầu OP logout, phải thực hiện RP-Initiated Logout đúng profile và không chỉ xóa local session.

### Tình huống J — ID token gửi như Bearer

Lập trình viên gửi `id_token_hint` tới Orders API với header `Authorization: Bearer`.

**Câu hỏi:** API nên xử lý thế nào?

**Trả lời:** Từ chối sai token type/audience. ID token dùng để xác minh OIDC login và có thể hỗ trợ OP logout, không thay OAuth access token cho API.

### Tình huống K — refresh R1 vẫn hoạt động

Alice chọn “Đăng xuất mọi thiết bị” nhưng backend chỉ xóa session S1.

**Câu hỏi:** Hành vi đúng yêu cầu chưa?

**Trả lời:** Chưa. Cần chính sách global session/grant revoke, kể cả refresh tokens của các thiết bị trong phạm vi, và propagation/access token handling; UI phải báo trạng thái đúng mức quan sát.

### Tình huống L — JWT T1 vẫn sống

OP session đã chấm dứt, refresh token đã revoke, nhưng JWT T1 còn 8 phút và Orders API kiểm offline.

**Câu hỏi:** Đây có phải lỗi JWT signature validation?

**Trả lời:** Không. T1 có thể vẫn ký hợp lệ. Đây là giới hạn early revocation của thiết kế offline; cần denylist/epoch/introspection hoặc chấp nhận cửa sổ tới `exp` theo policy.

### Tình huống M — HTTP 200 từ `/revoke`

RP nhận HTTP 200 khi revoke R1.

**Câu hỏi:** Có chắc R1 từng tồn tại và mọi access tokens đã chặn?

**Trả lời:** Không. RFC 7009 cố ý không tiết lộ token có tồn tại khi request xử lý hợp lệ; response không phải chứng nhận RS convergence.

### Tình huống N — back-channel token có `sid`

Một caller gửi JSON `{"sid":"op-session-529"}` tới RP endpoint và yêu cầu xóa tất cả sessions.

**Câu hỏi:** RP có nên nghe theo không?

**Trả lời:** Không. Back-Channel Logout dùng logout token JWT được **xác minh** với issuer, audience, signature, events, jti/replay và sid/sub binding; JSON tự khai không đủ.

### Tình huống O — logout token có `nonce`

RP nhận JWT có các claims logout, nhưng có thêm `nonce`.

**Câu hỏi:** Có nên coi đây là logout token hợp lệ vì chữ ký đúng?

**Trả lời:** Không theo Back-Channel Logout spec: logout token không được chứa `nonce`. Signature đúng vẫn phải kiểm semantic claims và token profile.

### Tình huống P — OP không gọi được một RP

OP gửi back-channel logout đến Shop Web thành công, còn Helpdesk trả 503.

**Câu hỏi:** Có thể đánh dấu cả hai RP sessions đã logout không?

**Trả lời:** Không. Phải có retry/monitoring/fallback phù hợp và không báo thành công cho Helpdesk khi chưa có confirmation có ý nghĩa.

### Tình huống Q — client tự chỉ định returnTo

Sau logout, RP redirect tới địa chỉ bất kỳ từ `returnTo` trong query. Attacker gửi một link logout trỏ về website giả login.

**Câu hỏi:** Đây là lỗi gì?

**Trả lời:** Open redirect/phishing. Chỉ cho registered post-logout redirect URIs hoặc local relative paths đã kiểm an toàn, không tin host header/query của client.

### Tình huống R — mobile app quay về deep link

Sau khi mở system browser để logout OP, mobile app nhận deep link trở về và báo “đã đăng xuất khỏi mọi thiết bị”.

**Câu hỏi:** Deep link chứng minh gì?

**Trả lời:** Chỉ điều hướng quay về app theo flow. Không tự chứng minh cookies trên trình duyệt khác, grants hoặc access tokens ở các thiết bị khác đã bị vô hiệu.

### Tình huống S — refresh/logout đồng thời

Một background refresh đọc grant ACTIVE, user nhấn logout và AS commit revoke, nhưng request refresh cũ vẫn tạo access token mới.

**Câu hỏi:** Cần xử lý tại đâu?

**Trả lời:** AS phải atomic/recheck grant version tại token issuance, BFF ngừng refresh khi local logout, RS có revocation strategy. Redirect không chặn race.

### Tình huống T — user A có `sid` giống user B ở issuer khác

Hai OP phát `sid=123`, RP nhận logout cho OP A và dùng `sid=123` để xóa session của OP B.

**Câu hỏi:** Vì sao sai?

**Trả lời:** Session lookup thiếu issuer/client binding. Phải dùng namespace theo trusted issuer và các ràng buộc phiên/profile, không dùng raw sid toàn cục.

### Tình huống U — token đúng nhưng tài nguyên thuộc tenant khác

Token còn hợp lệ sau logout local, nhưng có `scope=orders:read`. Attacker thử đọc order của Bob ở tenant B.

**Câu hỏi:** Revocation có thay kiểm object permission không?

**Trả lời:** Không. RS phải từ chối do audience/scope/tenant/ownership policy khi phù hợp; kể cả token ACTIVE cũng không cho phép đọc mọi order.

### Tình huống V — OP logout thành công nhưng client bị chiếm

User đã logout trên browser, nhưng attacker lấy được refresh token R1 trước đó từ crash report.

**Câu hỏi:** Browser redirect có chặn attacker dùng R1 không?

**Trả lời:** Không. Cần thu hồi refresh/grant và rotation/replay protection tại AS; đồng thời đánh giá access token đã cấp và credential leakage.

### Tình huống W — nhầm HTTP 503 thành invalid_token

RP gọi AS revoke/introspection bị timeout và UI báo “token chắc chắn đã vô hiệu”.

**Câu hỏi:** Kết luận nào chính xác hơn?

**Trả lời:** Trạng thái remote chưa xác minh; cần retry/record pending, fail mode theo policy và hiển thị thông tin trung thực. Không thể suy từ lỗi mạng rằng AS đã hoặc chưa commit.

### Tình huống X — logout sau khi mất thiết bị

Alice mất điện thoại và chọn “Đăng xuất tất cả”. OP browser session hiện tại đã đóng nhưng Shop Mobile vẫn có token.

**Câu hỏi:** Phải kiểm lớp nào?

**Trả lời:** Grants/refresh tokens theo device/user, access-token revocation tại RS, session state trên mobile và thời gian propagation. Đóng OP session trên laptop không bảo đảm credential trên điện thoại mất hiệu lực.

## 22. Playbook: xử lý khi logout đã hiển thị thành công nhưng credential còn hoạt động

Khi support/security phát hiện user đã logout nhưng vẫn có phiên/token hoạt động ngoài kỳ vọng, cần phân biệt **cam kết sản phẩm** với **bằng chứng kỹ thuật**.

### 22.1. Khoanh vùng vấn đề

Ghi nhận theo metadata được bảo vệ:

~~~text
logoutRequestId
trustedIssuerId
clientRegistrationId
localSessionReference
OPSessionReference (nếu profile cung cấp)
authorizationGrantReference
accessTokenId / HMAC fingerprint (không raw token)
refreshFamilyReference
affectedResourceServerIds
localLogoutCommittedAt
OPLogoutRequestedAt
grantRevokedAt
lastRSRevokeAppliedAt
observedDenyAt
~~~

Không lưu raw refresh/access/ID token, cookie hoặc client secret vào ticket hoặc log. Khi cần xác định một token, có thể dùng HMAC fingerprint với khóa bảo vệ thay token thô.

### 22.2. Điều tra theo các câu hỏi độc lập

1. **Local session:** RP có invalidate S1 và chặn requests mang cookie S1 không?
2. **Browser:** browser đã nhận redirect nào? Có network error, third-party cookie blocking hay direct callback không?
3. **OP:** RP-Initiated Logout có được OP hỗ trợ, request đã hợp lệ, OP session trong phạm vi có chấm dứt theo dữ liệu OP không?
4. **Các RPs khác:** front/back-channel logout messages đã đến và được xử lý bền vững chưa?
5. **Authorization grant:** AS có revoke đúng grant/refresh family/device không?
6. **Access tokens:** JWT/opaque còn hạn có thể được RS nào chấp nhận? Có cache stale không?
7. **Business actions:** token còn sống đã dùng để làm gì, trên resource/tenant nào?
8. **Độ trễ:** có vi phạm freshness SLO hoặc có một region/bypass path không được bảo vệ không?

### 22.3. Hành động giảm thiểu

- Nếu RP session chưa bị invalidate: sửa cơ chế session store/cookie và chặn SID cũ.
- Nếu OP session chưa logout: kiểm endpoint/registration/request, hướng dẫn user hoàn tất SSO theo policy.
- Nếu một RP bỏ lỡ Back-Channel Logout: replay/retry có kiểm soát, xác minh logout token và invalidate sessions liên quan.
- Nếu refresh family còn ACTIVE ngoài mong đợi: revoke qua AS và chặn issuance mới.
- Nếu access token bị lộ hoặc tiếp tục được RS nhận: dùng denylist/grant epoch/introspection/emergency policy theo khả năng.
- Nếu signing key hoặc client credential bị compromise: theo playbook rotate/revoke riêng, đánh giá blast radius.
- Nếu token đã dùng để xuất dữ liệu: điều tra truy cập và tác động, vì revoke không hoàn tác dữ liệu đã đọc.

### 22.4. Không tạo ra thành công giả trong monitoring

Một dashboard:

~~~text
logout_redirection_success = 99.99%
~~~

không nói lên security logout success. Thay bằng các chỉ số quan sát khác nhau, ví dụ:

~~~text
local_session_revocation_committed_rate
rp_initiated_logout_redirect_started_rate
op_logout_signal_processing_rate (nếu có dữ liệu)
backchannel_logout_token_validation_failure_rate
backchannel_logout_consumer_lag
refresh_grant_revocation_committed_rate
access_token_revocation_enforcement_lag_p99
rp_sessions_active_after_logout_request
api_allows_after_revoked_at_in_test_probes
~~~

Nên tách **navigation metrics** khỏi **server state/RS enforcement metrics**. Đừng suy SSO logout “thành công 100%” từ số lượng HTTP 302.

### 22.5. Khi kết quả không thể xác minh

Không phải OP/RS nào cũng cung cấp endpoint hoặc event đáng tin để hỏi “mọi phiên toàn hệ thống đã kết thúc chưa?”. Nếu không có cách đo, báo:

~~~text
local_session = ENDED (đã xác minh)
op_session = UNKNOWN (không có confirmation)
refresh_grant = REVOKE_REQUESTED (chưa xác minh commit)
access_token_enforcement = UNKNOWN
~~~

Sau đó đề xuất thiết kế bổ sung **audit/state/revocation propagation** nếu mục tiêu sản phẩm đòi bảo đảm mạnh hơn. “UNKNOWN” là kết quả trung thực hơn một nhãn SUCCESS không có dữ liệu.

## 23. Checklist triển khai đúng phạm vi logout

1. **Định nghĩa UX:** “logout app”, “logout SSO”, “logout device” hay “logout all devices” có ý nghĩa kỹ thuật và phạm vi nào?
2. **Local state:** server-side session bị invalidate, cookie được clear đúng, protected endpoints từ chối cookie cũ.
3. **Không phụ thuộc callback:** local logout không được thất bại chỉ vì browser mất mạng trên đường đến OP.
4. **Giao thức OP:** dùng `end_session_endpoint` từ trusted metadata và client registration; không tự đoán URL logout.
5. **Redirect an toàn:** post-logout URI được đăng ký/allowlist; không open redirect/host-header injection.
6. **State:** dùng random single-use short-lived state để correlate, ràng buộc issuer/client/request; không coi state là proof of revoke.
7. **ID token hint:** dùng theo profile, gửi đúng OP; không log nguyên query chứa hint.
8. **CSRF:** bảo vệ local state-changing logout action, tránh GET tùy ý kết thúc session.
9. **Front-channel:** hiểu giới hạn browser iframe, third-party cookies và timeout.
10. **Back-channel:** verify logout JWT (signature, issuer, audience, events, iat, jti, sid/sub, no nonce), replay protection và durable session invalidation.
11. **Phạm vi session:** sid/sub/issuer/client binding đúng; logout một thiết bị không vô hiệu sai thiết bị khác, trừ khi policy yêu cầu.
12. **OAuth revoke:** nếu sản phẩm cần, gọi RFC 7009 hoặc grant revoke đúng phạm vi; 200 không chứng minh RS enforcement.
13. **Refresh family:** xử lý rotation, reuse detection và revoke atomically với token issuance.
14. **JWT/opaque:** thiết kế access-token expiry, introspection, denylist/epoch hoặc hybrid theo freshness SLO.
15. **Distributed systems:** event propagation, cache invalidation, stale windows, fail-closed/fail-open risk và recovery.
16. **BFF/client storage:** token store xóa đúng; background refresh không khôi phục session sau logout.
17. **Multi-tab/device:** UI đồng bộ, không hiển thị dữ liệu private đã cache, không hiểu login lại qua OP là local logout thất bại mặc nhiên.
18. **Resource authorization:** RS vẫn kiểm issuer, audience, time, scope và principal/action/resource/tenant; logout không thay quyền nghiệp vụ.
19. **Error handling:** timeout/unknown không tự SUCCESS; phân biệt local ended, OP requested, revoke committed và RS enforced.
20. **Observability:** log metadata tối thiểu, không credential; theo dõi logout enforcement theo từng ứng dụng/region.
21. **Kiểm thử:** direct callback, state replay, OP timeout, frontchannel blocked, backchannel failure, refresh race, JWT stale và logout all devices.
22. **Incident response:** có kế hoạch revoke/disable và audit dữ liệu đã truy cập khi một credential vẫn còn dùng được sau logout.

### 23.1. Sơ đồ quyết định thực dụng

~~~mermaid
flowchart TD
    A[Người dùng yêu cầu logout] --> B[RP invalidate local session]
    B --> C{Có cần OP SSO logout?}
    C -- Có --> D[RP-Initiated Logout tới OP trusted endpoint]
    C -- Không --> E[Local logout state = ENDED]
    D --> F{Browser quay về qua callback?}
    F -- Có --> G[Kiểm state và hiển thị local status]
    F -- Không --> H[OP status UNKNOWN; local vẫn ENDED]
    G --> E
    H --> E
    E --> I{Policy yêu cầu revoke OAuth grants?}
    I -- Có --> J[AS revoke đúng grant/token family]
    I -- Không --> K[Không hứa access tokens đã revoke]
    J --> L{Có early access token revocation?}
    L -- Có --> M[RS introspection/denylist/epoch propagation]
    L -- Không --> N[Token còn hạn tới exp theo thiết kế]
    M --> O[Đo enforcement tại mọi RS trong phạm vi]
    O --> P[Chỉ báo mức đã có bằng chứng]
    N --> P
    K --> P
~~~

Sơ đồ này mô tả **nhiều nhánh độc lập**; thứ tự grant revoke có thể song song với OP logout tùy sản phẩm. Điều cốt yếu không đổi: **browser callback chỉ chứng minh một phần đường điều hướng và correlation, không đại diện cho những hệ thống khác**.

### 23.2. Nhớ nhanh trong một phút

~~~text
HTTP 302 / Location
    = Điều hướng user agent.

post_logout_redirect_uri + state
    = Callback/correlation theo RP-initiated flow.
    != Bằng chứng global logout hoặc token revocation.

RP session invalidation
    = Kết thúc phiên local nếu backend thực thi đúng.

OIDC Front-/Back-Channel Logout
    = Cơ chế thông báo kết thúc RP sessions theo profile.
    != Tự động thu hồi mọi bearer access token.

RFC 7009 revoke
    = AS xử lý yêu cầu thu hồi theo contract.
    != Mọi Resource Server đã hội tụ trạng thái.

JWT access token offline
    = Có thể còn hợp lệ tới exp khi không có early revoke.

Resource Server
    = Luôn kiểm token + action + resource + tenant.
~~~

**Kết luận:** Một trang “Đã đăng xuất” sau redirect chỉ có ý nghĩa đáng tin khi được gắn với **trạng thái thực sự đã được backend xác minh**. OIDC RP-Initiated Logout giúp điều hướng browser để yêu cầu OP kết thúc phiên; Front-Channel/Back-Channel Logout giúp truyền logout tới RPs; RFC 7009 xử lý thu hồi token tại AS; RS phải tự cưỡng chế trạng thái access token theo kiến trúc. **Không có một `302`, `200`, `state` hay callback URL đơn lẻ nào chứng minh tất cả các bước đó đã hoàn tất.** Muốn hứa logout mạnh như “mọi thiết bị” hoặc “vô hiệu token ngay”, phải thiết kế cơ chế state, xác nhận và độ trễ hội tụ tương ứng.

## Tài liệu tham khảo

- [OpenID Connect RP-Initiated Logout 1.0](https://openid.net/specs/openid-connect-rpinitiated-1_0.html): `end_session_endpoint`, `id_token_hint`, `post_logout_redirect_uri`, `state` và quy trình RP yêu cầu OP logout.
- [OpenID Connect Front-Channel Logout 1.0](https://openid.net/specs/openid-connect-frontchannel-1_0.html): trình duyệt thông báo logout tới các RPs và giới hạn front-channel.
- [OpenID Connect Back-Channel Logout 1.0](https://openid.net/specs/openid-connect-backchannel-1_0.html): Logout Token JWT, `iss`, `aud`, `iat`, `jti`, `events`, `sid`/`sub`, replay và server-to-server logout.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID token, OP/RP, subject và phiên xác thực.
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html): metadata của OP, endpoint discovery và issuer.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): revocation endpoint, HTTP 200 semantics và token type hint.
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): authorization grant, access/refresh token và client authentication.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): chống token theft/replay, refresh token rotation và client security.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): `active` state, introspection protections và cache considerations.
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519): JWT signature, `exp`, `iat`, `jti` và claim semantics.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): issuer, audience, scope và JWT access token type.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): bearer access tokens và resource-server error semantics.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession](https://www.rfc-editor.org/rfc/rfc9449): sender-constrained access tokens theo DPoP khi phù hợp.
- [RFC 8705 — OAuth 2.0 Mutual-TLS](https://www.rfc-editor.org/rfc/rfc8705): client authentication và certificate-bound access tokens.
- [Spring Security Reference — Logout](https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html): logout filter, session invalidation, cookie cleanup và logout handlers.
- [Spring Security Reference — OIDC Logout](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/logout.html): `OidcClientInitiatedLogoutSuccessHandler` và RP-Initiated Logout trong servlet app.
- [Spring Security Reference — OAuth 2.0 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html): access token verification và JWT/opaque token usage.
- [Spring Authorization Server Reference](https://docs.spring.io/spring-authorization-server/reference/): token issuance, grant lifecycle, revocation và ứng dụng AS.
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): session invalidation, cookie protections và timeout.
- [OWASP Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): chống CSRF cho state-changing actions.
- [OWASP OAuth2 Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html): OAuth client/token flow, redirect security và token protection.
