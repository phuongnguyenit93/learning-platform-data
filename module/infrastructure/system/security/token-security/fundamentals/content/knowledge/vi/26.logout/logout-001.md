# Logout local và logout tại authorization server

Người dùng đăng nhập vào ứng dụng `orders-web` bằng OpenID Connect (OIDC), sau đó nhấn **Đăng xuất**. Ứng dụng xóa session cookie và chuyển về trang đăng nhập. Nhưng khi bấm **Đăng nhập bằng tài khoản tổ chức** lần nữa, người dùng có thể được đăng nhập ngay, không cần nhập mật khẩu. Điều này chưa chắc là lỗi: **phiên tại ứng dụng đã kết thúc, trong khi phiên Single Sign-On (SSO) tại OpenID Provider vẫn còn**.

Trong hệ thống OAuth 2.0/OIDC, “logout” không phải một lệnh ma thuật làm mọi thông tin xác thực và mọi token biến mất. Phải xác định **đối tượng nào cần kết thúc**:

- **Local logout:** xóa hoặc vô hiệu phiên đăng nhập của chính ứng dụng (Relying Party – RP), xóa credential do ứng dụng quản lý và dừng hoạt động dùng phiên đó.
- **Logout tại authorization server/OpenID Provider:** yêu cầu hệ thống danh tính kết thúc phiên xác thực SSO của người dùng theo **OIDC RP-Initiated Logout** hoặc hợp đồng đăng xuất của nhà cung cấp.
- **Token/grant revocation:** yêu cầu AS thu hồi access/refresh token hoặc grant qua cơ chế phù hợp, chẳng hạn RFC 7009. Đây là mục tiêu riêng, **không tự được bảo đảm** chỉ nhờ hai loại logout trên.

Bài thuộc chương **Logout** của module `SECURITY_TOKEN_SECURITY_FUNDAMENTALS`. Nội dung kết nối mô hình tin cậy và vòng đời **JWT, opaque token, access token, refresh token, ID token** trong OAuth 2.0/OIDC; chỉ ra ranh giới issuer, audience, scope, session, lưu trữ, thu hồi và nguy cơ token bị đánh cắp/phát lại; cung cấp ví dụ Spring Security, sơ đồ, ma trận rủi ro và bài kiểm thử.

## 1. Bức tranh tổng thể: không chỉ có một phiên

Một lần OIDC login ở ứng dụng web có thể tạo nhiều trạng thái độc lập:

| Trạng thái | Nơi quản lý | Ví dụ | Có tự biến mất khi logout local? |
|---|---|---|---|
| **RP/application session** | Ứng dụng `orders-web` hoặc BFF | Server-side session, cookie `JSESSIONID` | **Có**, nếu logout local được triển khai đúng. |
| **OP/AS SSO session** | OpenID Provider | Cookie đăng nhập tại `id.example.test` | **Không**, vì ứng dụng không sở hữu cookie của OP. |
| **Access token** | AS phát, client giữ, RS chấp nhận | JWT/opaque token dành cho `orders-api` | **Không bảo đảm**; còn phụ thuộc expiry/revocation. |
| **Refresh token** | AS quản lý grant; client lưu bản token | Token đổi access token mới | **Không bảo đảm** nếu chưa revoke grant/token. |
| **ID token** | OP phát cho RP để xác minh đăng nhập | JWT `aud=orders-web` | Không phải session cookie; xóa bản lưu không làm token đã phát tự “mất hiệu lực”. |
| **Session của RP khác** | Ứng dụng khác, ví dụ `reports-web` | Cookie/session của Reports | **Không**, trừ khi có cơ chế logout liên ứng dụng. |
| **Phiên trên thiết bị khác** | RP/OP/AS và thiết bị đó | Ứng dụng mobile trên điện thoại | **Không**, nếu chỉ logout browser hiện tại. |

**Câu hỏi “đã logout chưa?” chỉ có nghĩa khi chỉ rõ đã kết thúc trạng thái nào.** Với nghiệp vụ nhạy cảm, cần nói rõ logout ở phiên hiện tại, toàn bộ SSO, toàn bộ thiết bị, hay thu hồi tất cả grants.

### Ví dụ thực tế

```text
Browser:
    orders-web.example.test
        Cookie: JSESSIONID=RP_SESSION_A

Identity Provider:
    id.example.test
        Cookie: OP_SSO_SESSION_B

Orders Web Backend:
    OAuth authorized client:
        ID token (RP use)
        Access token (aud=orders-api)
        Refresh token (nếu được cấp)

Orders API:
    Chỉ nhận access token đúng audience/scope
```

Xóa `RP_SESSION_A` không xóa được cookie `OP_SSO_SESSION_B` ở domain của OP. Nếu access token còn hạn bị kẻ khác sao chép trước logout, token đó có thể vẫn dùng được tới khi expiry hoặc bị RS từ chối bằng cơ chế thu hồi.

## 2. OAuth, OIDC và vai trò liên quan đến logout

| Vai trò | Điều nó sở hữu/quản lý |
|---|---|
| **Relying Party (RP)/OIDC client** | Session người dùng tại ứng dụng, trạng thái OAuth client, cache token và logic logout local. |
| **OpenID Provider (OP)** | SSO authentication session của người dùng; ID token; endpoints OIDC Logout nếu hỗ trợ. |
| **Authorization Server (AS)** | Grants, access/refresh tokens, token revocation/introspection và chính sách authorization. Có thể cùng hệ thống với OP. |
| **Resource Server (RS)** | Kiểm access token, audience, scope, expiry, tenant và quyền tài nguyên. |
| **Browser/user agent** | Lưu cookies theo origin, thực hiện redirects và request theo chính sách browser. |
| **End user** | Khởi tạo logout và lựa chọn phạm vi đăng xuất khi sản phẩm cung cấp. |

OIDC OP thường đồng thời là AS, nhưng các trách nhiệm **quản lý phiên SSO** và **quản lý tokens/grants** vẫn khác nhau. OAuth 2.0 Core **không định nghĩa một logout endpoint toàn cục cho mọi client**.

## 3. Ba thao tác cần phân biệt: local, OP/AS và revocation

| Thao tác | Mục tiêu | Cơ chế ví dụ | Điều không được bảo đảm |
|---|---|---|---|
| **Local logout** | Chấm dứt session của một RP. | Invalidate server session, clear SecurityContext, expire cookie, xóa token cache thuộc phiên. | OP SSO session, tokens đã phát và session RP khác tự kết thúc. |
| **OP/AS logout** | Kết thúc authentication session tại OP theo chính sách. | OIDC RP-Initiated Logout qua `end_session_endpoint`. | Access/refresh tokens và mọi RP sessions tự bị revoke nếu thiếu cơ chế phụ. |
| **Token revocation** | Thu hồi token/grant tại AS. | RFC 7009 revocation endpoint hoặc AS admin/grant policy. | Cookies của RP/OP và dữ liệu bên thứ ba tự bị xóa. |
| **Front-/Back-Channel Logout** | Thông báo cho các RPs khác rằng OP session kết thúc. | OIDC Front-Channel / Back-Channel Logout nếu các bên triển khai. | Mọi browser/device/session đều bị đóng nếu không có correlation và endpoint hoạt động. |

**“Logout tại authorization server”** có thể bị dùng mơ hồ. Trong OIDC, thuật ngữ chính xác thường là **logout tại OpenID Provider (OP)** đối với **authentication/SSO session**. Nếu muốn **thu hồi token hoặc grant ở AS**, phải áp dụng cơ chế revocation riêng.

## 4. Local logout hoạt động như thế nào?

Local logout tập trung vào **ứng dụng đang được sử dụng**. Với một web application có session server-side:

1. Người dùng gửi **request logout hợp lệ**, nên dùng POST được bảo vệ CSRF khi authentication dựa vào browser cookies.
2. Ứng dụng kiểm tra session hiện tại và quyền xử lý request.
3. **Invalidate server-side session**, xóa authenticated principal và SecurityContext.
4. Xóa hoặc gỡ liên kết **OAuth2AuthorizedClient** và token storage gắn với session khi kiến trúc yêu cầu.
5. Hết hạn cookie phiên tại browser với các thuộc tính **Domain/Path/Secure/SameSite** phù hợp.
6. Hủy/dừng các tác vụ background thuộc phiên nếu policy yêu cầu.
7. Ghi audit logout mà không tiết lộ raw tokens/cookies.
8. Redirect hoặc hiển thị trang “Đã đăng xuất” không tiết lộ thông tin riêng.

```mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant B as Browser
    participant RP as Orders Web / BFF
    participant OP as OpenID Provider
    U->>B: Nhấn Đăng xuất
    B->>RP: POST /logout + CSRF + RP session cookie
    RP->>RP: Invalidate local session và SecurityContext
    RP->>RP: Dọn OAuth authorized-client storage thuộc phiên
    RP-->>B: Redirect /logged-out, expire RP cookie
    Note over OP: SSO session tại OP vẫn có thể còn
    B->>RP: GET /login
    RP-->>B: Redirect đến OP
    B->>OP: Authentication Request
    OP-->>B: SSO còn hạn: có thể login lại không nhập mật khẩu
```

Trong biểu đồ này **không có request logout tới OP**. Local logout vẫn có thể là lựa chọn đúng nếu người dùng chỉ muốn thoát ứng dụng hiện tại, nhất là khi họ đang dùng nhiều ứng dụng SSO khác.

### Invalidate server session khác xóa cookie

Nếu ứng dụng chỉ trả:

```http
Set-Cookie: JSESSIONID=; Max-Age=0; Path=/; Secure; HttpOnly
```

mà **server-side session vẫn active**, bản sao cookie cũ bị lấy trước đó có thể tiếp tục được dùng theo chính sách server. Vì vậy cần **vô hiệu session ở server**, không chỉ xóa dấu vết phía browser.

Ngược lại, nếu session server đã bị invalidate nhưng cookie chưa được clear, browser có thể tiếp tục gửi cookie vô dụng; không nguy hiểm tương đương nhưng gây trải nghiệm khó hiểu và cần cleanup.

## 5. Local logout với stateless JWT không có session server-side

Một số ứng dụng nhận **Bearer JWT access token** trong header và không có server session. Khi người dùng nhấn logout, client có thể:

- Xóa access token khỏi memory/storage của chính ứng dụng.
- Xóa refresh token local khỏi kho an toàn nếu có.
- Ngừng các background refresh/sync jobs.
- Hủy UI authenticated state, cache và dữ liệu nhạy cảm thuộc tài khoản.
- Yêu cầu AS revoke refresh token/grant nếu cần chấm dứt quyền đăng nhập kéo dài.

**Không thể “xóa JWT đã phát khỏi mọi nơi” chỉ bằng việc xóa bản local.** Một JWT access token đã bị attacker sao chép vẫn có thể hợp lệ nếu chữ ký/`iss`/`aud`/`exp` đúng và RS không kiểm trạng thái revoke.

Với **opaque access token**, RS có thể hỏi introspection RFC 7662; khi AS revoke thành công và cache đã cập nhật, RS có thể nhận `active=false`. Nhưng độ trễ **cache introspection** vẫn cần được tính đến.

## 6. Authorization server/OpenID Provider logout là gì?

**OP logout** là kết thúc **authentication session** mà OP đang giữ cho người dùng. Một ứng dụng RP có thể đề nghị OP kết thúc session bằng **OpenID Connect RP-Initiated Logout 1.0** khi provider hỗ trợ.

Các điểm cần nhớ:

- RP cần xác định đúng **OP/issuer** mà user đang đăng nhập, không lấy logout URL từ request chưa tin.
- OP thường cung cấp **`end_session_endpoint`** trong discovery metadata theo profile hỗ trợ.
- RP có thể gửi **`id_token_hint`** để OP nhận diện phiên/user/client liên quan.
- RP có thể yêu cầu redirect về **`post_logout_redirect_uri`** đã đăng ký.
- RP có thể gửi **`state`** để ràng buộc logout response/redirect theo transaction.
- OP có thể yêu cầu **user confirmation**, tùy độ tin cậy của request, hints và chính sách.
- OP quyết định kết thúc session nào; không mặc định việc đăng xuất RP đồng nghĩa toàn bộ devices/users đều bị thoát.

**Logout OP không giống RFC 7009 token revocation.** Ngay cả khi OP trả về trang “Đã đăng xuất”, RP vẫn cần có chính sách về token/grant đang được lưu.

### Trường hợp chỉ cần logout local

Một ứng dụng dùng trong máy công ty chia sẻ SSO với nhiều hệ thống. Người dùng muốn đóng riêng Orders nhưng vẫn tiếp tục Reports. Local logout có thể phù hợp.

### Trường hợp cần logout OP

Máy kiosk công cộng hoặc yêu cầu “Đăng xuất khỏi tài khoản tổ chức tại trình duyệt này” có thể cần cả local logout lẫn OP logout. Tuy nhiên, **nếu muốn đăng xuất khỏi tất cả phiên và thiết bị**, RP-Initiated Logout một mình chưa đủ bảo đảm: cần OP session management và hệ thống revocation toàn cục theo chính sách.

## 7. OIDC RP-Initiated Logout: flow tổng thể

```mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant B as Browser
    participant RP as Orders RP / BFF
    participant OP as OIDC OpenID Provider
    participant RS as Orders API
    U->>B: Nhấn Đăng xuất khỏi ứng dụng và SSO
    B->>RP: POST /logout + CSRF token
    RP->>RP: Invalidate local session, xóa state/token cache
    RP-->>B: Redirect tới OP end_session_endpoint với hints an toàn
    B->>OP: RP-Initiated Logout Request
    OP->>OP: Kiểm hint/client/redirect, confirmation nếu cần
    OP->>OP: Kết thúc OP authentication session
    OP-->>B: Redirect về post_logout_redirect_uri đã đăng ký
    B->>RP: GET /logged-out?state=...
    RP->>RP: Xác minh state nếu dùng; không coi redirect là proof revoke
    RP-->>B: Hiển thị trang đã đăng xuất
    Note over RS: Bearer access token bị đánh cắp có thể còn hợp lệ
```

**Trình tự khuyến nghị:** local cleanup nên được thực hiện chắc chắn, kể cả khi OP logout request về sau thất bại. Không giữ local session active chỉ vì mạng tới OP đang gián đoạn, và không hiển thị trạng thái “toàn bộ token đã bị thu hồi” nếu chưa có xác nhận/contract thực tế.

Một ứng dụng có thể yêu cầu revoke refresh token **trước hoặc cùng quá trình logout**, nhưng phải xử lý race, timeout và chính sách revoke độc lập với flow redirect.

## 8. Discovery và `end_session_endpoint`

Một OP hỗ trợ RP-Initiated Logout có thể công bố metadata:

```json
{
  "issuer": "https://id.example.test",
  "authorization_endpoint": "https://id.example.test/oauth2/authorize",
  "token_endpoint": "https://id.example.test/oauth2/token",
  "jwks_uri": "https://id.example.test/oauth2/jwks",
  "end_session_endpoint": "https://id.example.test/connect/logout"
}
```

Đây là ví dụ về OIDC discovery metadata, không phải URL thực.

**Quy tắc an toàn:**

1. Cấu hình **issuer tin cậy** cho client registration.
2. Lấy endpoint/logout capabilities từ metadata của **đúng issuer** hoặc cấu hình đã được đánh giá.
3. Dùng HTTPS và kiểm certificate/hostname.
4. Không lấy `end_session_endpoint` từ một `returnUrl`, `iss` hoặc domain user cung cấp.
5. Nếu OP không hỗ trợ RP-Initiated Logout, **không tự dựng logout URL theo suy đoán**; chỉ làm local logout hoặc dùng provider-specific flow đã tài liệu hóa.
6. Khi hỗ trợ nhiều OP, giữ mapping **session → client registration → issuer → end-session endpoint**.

**Một provider có `end_session_endpoint` không tự cam kết nó revokes access tokens.** Khả năng đó phải được xác minh riêng.

## 9. Các tham số của RP-Initiated Logout

| Tham số | Vai trò | Yêu cầu thực hành |
|---|---|---|
| **`id_token_hint`** | ID token trước đó OP phát cho RP, giúp OP xác định user/session cần logout. | Dùng ID token thuộc **đúng OP/client**, bảo vệ khỏi lộ và không tự sửa JWT. |
| **`logout_hint`** | Gợi ý về end-user session được logout theo quy ước OP. | Không coi là bằng chứng caller có quyền đăng xuất người khác. |
| **`client_id`** | Xác định RP/client theo đăng ký, hữu ích trong các trường hợp không có ID token hint. | Không nhận client ID tùy ý làm lý do cho redirect không đăng ký. |
| **`post_logout_redirect_uri`** | URI mà OP có thể chuyển browser về sau xử lý logout. | Phải được đăng ký/chấp nhận theo chính sách OP; không là open redirect. |
| **`state`** | Ràng buộc phản hồi/redirect sau logout với giao dịch tại RP. | Sinh khó đoán, một lần, TTL ngắn; kiểm khi nhận callback nếu có dùng. |

Ví dụ logic request (giá trị đều là placeholders):

```http
GET /connect/logout?id_token_hint=ENCODED_ID_TOKEN_HINT&post_logout_redirect_uri=https%3A%2F%2Fapp.example.test%2Flogged-out&state=RANDOM_LOGOUT_STATE HTTP/1.1
Host: id.example.test
```

**Không phải tất cả các tham số đều bắt buộc trong mọi tình huống**, và OP có thể yêu cầu xác nhận người dùng khi không đủ thông tin tin cậy. Khi dùng `post_logout_redirect_uri`, OP phải áp dụng yêu cầu đăng ký/kiểm tra URI theo đặc tả và chính sách. **Không suy rằng caller được redirect về mọi URL chỉ vì có `client_id`.**

### Lưu ý với `id_token_hint` trong URL

`id_token_hint` là **ID token đã ký**, thường chứa thông tin authentication và có thể có PII. Khi truyền qua browser URL:

- Chỉ gửi tới **OP đúng issuer**.
- Không lưu raw logout URL trong access logs/analytics hoặc hỗ trợ khách hàng.
- Hạn chế Referer leakage, áp dụng Referrer-Policy thích hợp và HTTPS.
- Nếu OP hỗ trợ cách gửi logout request khác phù hợp profile, lựa chọn theo hợp đồng/khả năng thư viện.
- Không coi ID token là mật khẩu hay access token cho business API, nhưng vẫn **bảo vệ nó khỏi lộ**.

**Không gửi access token hoặc refresh token thay `id_token_hint`.** OP cần đúng loại hint được đặc tả hỗ trợ.

## 10. Post-logout redirect không chứng minh đã thu hồi token

Một browser chuyển về:

```http
GET /logged-out?state=LOGOUT_STATE_PLACEHOLDER HTTP/1.1
Host: app.example.test
```

chỉ chứng minh browser đã đi qua luồng redirect tương ứng và callback được RP xử lý theo trạng thái. **Nó không phải chứng cứ**:

- mọi access token đã bị revoke;
- mọi refresh token family bị vô hiệu;
- các RP khác đã nhận logout signal;
- tất cả browser/device sessions đã kết thúc;
- dữ liệu đã tải về third-party client được xóa.

Trạng thái “Đăng xuất khỏi ứng dụng” nên dựa trên **local session invalidation**. Trạng thái “Đã đăng xuất khỏi SSO” có thể dựa trên kết quả/contract OP, nhưng vẫn cần diễn đạt phạm vi. Không dùng redirect `state` như một access token, và không để callback tạo lại session cũ.

## 11. Logout local có thể bị auto-login do SSO còn sống

Một tình huống thường gặp:

```text
T0: User login Orders → local session RP-A + OP SSO session S.
T1: User logout local → RP-A bị vô hiệu, S vẫn ACTIVE.
T2: User bấm Login → RP gửi OIDC Authentication Request.
T3: OP nhìn thấy SSO cookie S → không yêu cầu nhập lại mật khẩu.
T4: OP cấp code/ID token mới → RP tạo local session RP-B.
```

**Không phải local logout bị đảo ngược.** RP-A đã bị xóa; RP-B là **một phiên mới** được thiết lập nhờ OP SSO. Nếu sản phẩm yêu cầu người dùng phải xác thực lại sau logout local, có thể cần OP logout hoặc yêu cầu authentication freshness phù hợp OIDC (như `prompt=login`, `max_age`/`auth_time`) khi đăng nhập mới.

**Nonce OIDC không buộc người dùng nhập lại mật khẩu.** Nonce chỉ giúp gắn ID token với authentication transaction, không thay OP session policy.

## 12. Logout khỏi một ứng dụng không tự logout ứng dụng khác

Giả sử user đang dùng:

```text
orders-web.example.test → RP session ORD-1
reports-web.example.test → RP session REP-1
id.example.test        → OP session SSO-1
```

Nếu Orders xóa ORD-1:

- Reports có thể giữ REP-1.
- OP có thể vẫn giữ SSO-1.
- Người dùng quay lại Orders có thể login ngay nhờ SSO-1.

Nếu Orders khởi tạo OP logout:

- OP có thể kết thúc SSO-1.
- Reports **không nhất thiết** xóa REP-1 trừ khi Reports được thông báo và thực thi **OIDC Front-Channel Logout, Back-Channel Logout hoặc session integration**.
- Các access tokens của Reports có thể vẫn hợp lệ theo AS/RS policy.

**Single Logout (SLO)** là một yêu cầu tích hợp liên ứng dụng, không phải hệ quả tự động của local logout.

## 13. OIDC Front-Channel Logout khác RP-Initiated Logout

**RP-Initiated Logout** nói về **RP yêu cầu OP đăng xuất**.

**Front-Channel Logout** là cơ chế **OP thông báo cho các RP qua user agent/browser** rằng phiên OP liên quan đã kết thúc.

| Thuộc tính | RP-Initiated Logout | Front-Channel Logout |
|---|---|---|
| Hướng truyền | RP → OP, thường qua browser. | OP → RP qua browser. |
| Mục đích | Bắt đầu logout OP session. | Yêu cầu RP kết thúc local session liên quan. |
| Điểm khởi tạo | Người dùng logout trong ứng dụng hoặc sự kiện RP. | OP logout, phiên hết hạn hoặc chính sách OP. |
| Phụ thuộc browser | Có trong flow redirect. | Có; browser phải thực hiện request/iframe. |
| Nhược điểm | OP có thể không revoke tokens hoặc logout mọi RP. | Third-party cookies, iframe restrictions, network/browser behavior. |

Front-channel có thể dùng **logout URI** đã đăng ký cho RP và thông tin session như `iss`/`sid` khi hỗ trợ. RP phải kiểm nguồn và binding theo profile, không coi một GET logout URI tùy ý do Internet gọi là lệnh admin toàn cục.

### Vì sao front-channel có thể thiếu tin cậy?

Browser hiện đại giới hạn third-party cookies/iframes. Một OP có thể muốn gọi logout URI của RP trong iframe nhưng cookie phiên RP không được gửi; RP không tìm được session cần invalidate. **Do đó không tuyên bố front-channel luôn logout mọi ứng dụng.**

Nếu cần SLO có độ tin cậy cao hơn, cân nhắc **Back-Channel Logout** khi OP và RP cùng hỗ trợ và vận hành đúng.

## 14. OIDC Back-Channel Logout: thông báo từ OP tới RP

Back-channel cho phép OP **gửi một Logout Token đến RP qua server-to-server HTTP**, không dựa vào browser để gửi cookie RP.

```mermaid
sequenceDiagram
    autonumber
    participant U as User / Browser
    participant OP as OpenID Provider
    participant A as Orders RP
    participant B as Reports RP
    U->>OP: Logout SSO session
    OP->>OP: Xác định sessions/clients bị ảnh hưởng
    OP->>A: POST backchannel_logout_uri + signed logout_token
    OP->>B: POST backchannel_logout_uri + signed logout_token
    A->>A: Validate token + correlate sid/sub + revoke local sessions
    B->>B: Validate token + correlate sid/sub + revoke local sessions
    A-->>OP: HTTP outcome
    B-->>OP: HTTP outcome
```

**Logout Token không phải access token, refresh token hay ID token thông thường.** Nó là một JWT sự kiện dành cho **back-channel logout**, với claims/validation theo OpenID Connect Back-Channel Logout 1.0.

### Những thành phần cần kiểm tra

| Claim/thuộc tính | Công dụng |
|---|---|
| `iss` | OP/issuer tin cậy phát tín hiệu. |
| `aud` | RP/client nào được nhận Logout Token. |
| `iat`, `jti` | Thời điểm và định danh message; hỗ trợ chống replay. |
| `events` | Phải biểu thị sự kiện back-channel logout theo profile. |
| `sid` và/hoặc `sub` | Xác định session/subject liên quan để RP có thể logout. |
| JWT signature/algorithm | Chứng minh sự kiện từ OP tin cậy, không phải người ngoài POST giả. |

Theo Back-Channel Logout profile, Logout Token **không chứa `nonce`** vì không phải ID token phản hồi Authentication Request. RS/RP phải áp dụng validation riêng cho Logout Token, không chỉ dùng OIDC ID token validator thông thường.

**Nếu có `sid`**, RP nên map tới đúng OP session/RP sessions để tránh logout tất cả user sessions không chủ ý. **Nếu theo `sub`**, chính sách có thể ảnh hưởng nhiều session của cùng user; cần xác định yêu cầu rõ.

### Giới hạn back-channel

- Cần endpoint mà OP có thể gọi an toàn và kết nối ổn định.
- RP phải xác minh Logout Token, chống replay và xử lý idempotency.
- Nếu RP tạm offline, cần chính sách retry/queue và TTL của logout message.
- RP sessions có thể phân tán qua nhiều node, cần storage/tầng invalidate nhất quán.
- Back-channel local logout **không mặc định revoke mọi JWT access token đã phát**; revocation vẫn là bài toán riêng.

## 15. Session correlation: `sid` khác `sub`

Trong OIDC, một người dùng có thể đăng nhập từ nhiều thiết bị và nhiều phiên.

| Khóa correlation | Thể hiện | Nguy cơ nếu dùng sai |
|---|---|---|
| **`sid`** (session ID do OP định nghĩa) | Một OP session hoặc ngữ cảnh session theo profile. | Không map đúng → logout nhầm hoặc bỏ sót session. |
| **`sub`** | Subject/user tại OP. | Logout theo `sub` có thể ảnh hưởng **tất cả sessions** của user ngoài ý muốn. |
| **RP session ID** | Phiên local của ứng dụng. | Không nhất thiết trùng OP `sid`. |
| **Client ID + issuer** | Trust domain của RP/OP. | Chỉ dùng `sub` không có issuer có thể gây nhầm user. |

Ví dụ:

```text
OP issuer: https://id.example.test
subject: user-123

Device A:
    OP sid = SID-A
    Orders local session = ORD-A

Device B:
    OP sid = SID-B
    Orders local session = ORD-B
```

Nếu OP gửi Logout Token với `sid=SID-A`, RP nên kết thúc **ORD-A** theo mapping tin cậy, không mặc định xóa ORD-B. Nếu policy thực sự là “Logout khỏi mọi thiết bị”, cần một **session-wide/global invalidation** được hỗ trợ rõ.

**Không nhận `sid` từ unauthenticated HTTP query** rồi xóa session; chỉ tin session identifiers từ OP messages đã được xác minh.

## 16. Token revocation RFC 7009: một thao tác riêng với logout

Khi muốn không cho client tiếp tục đổi refresh token lấy access token mới, có thể cần gọi **OAuth 2.0 Token Revocation Endpoint** theo RFC 7009.

Ví dụ confidential client:

```http
POST /oauth2/revoke HTTP/1.1
Host: id.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic CLIENT_AUTH_PLACEHOLDER

token=REFRESH_TOKEN_PLACEHOLDER&token_type_hint=refresh_token
```

- `token` là credential cần revoke.
- `token_type_hint` chỉ là **gợi ý** về loại token.
- Client authentication/authorization áp dụng theo AS.
- Không truyền refresh token bằng URL query.
- Không dùng endpoint revoke làm endpoint thay cho logout OP.
- Theo RFC 7009, response thành công thường **HTTP 200** cho token được xử lý, kể cả trường hợp token không tồn tại; không dùng response để enumerate tokens.
- Chính sách thu hồi thêm access tokens liên quan có thể khác nhau theo AS/grant lifecycle.

**Revoke refresh token** thường là bước quan trọng để ngăn client xin access token mới từ refresh token đó. Nhưng **access JWT đã cấp** có thể còn hiệu lực đến `exp` nếu RS không kiểm trạng thái/denylist.

### Thu hồi token theo phạm vi nào?

| Yêu cầu nghiệp vụ | Cần xem xét |
|---|---|
| Logout khỏi phiên web này | Local session invalidation và xóa token cache của phiên. |
| Không cho app tiếp tục refresh | Revoke refresh token/grant liên quan. |
| Ngăn access token còn hạn | AS revocation + RS enforcement (opaque introspection, denylist hoặc policy). |
| Logout khỏi SSO browser | RP-Initiated Logout tới OP. |
| Logout khỏi mọi RPs | OP Front-/Back-Channel Logout và session mapping phù hợp. |
| Logout khỏi mọi thiết bị | Session/grant/global revocation theo AS/OP policy, không chỉ local endpoint. |

Đây là **nhiều quyết định có quan hệ nhưng không đồng nhất**; ứng dụng cần thông báo cho người dùng chính xác phạm vi đã hoàn thành.

## 17. JWT và opaque token sau logout: kiểm tra tại resource server

### JWT tự chứa

Một access JWT có payload minh họa:

```json
{
  "iss": "https://id.example.test",
  "sub": "user-123",
  "aud": "orders-api",
  "scope": "orders.read",
  "exp": 1795410600,
  "jti": "TOKEN_REFERENCE_PLACEHOLDER"
}
```

Đây chỉ là payload, **không phải JWT được ký**. Nếu RS kiểm chữ ký, expiry, audience và scope nhưng không tra revoke, một JWT bị sao chép trước logout **vẫn có thể được chấp nhận đến lúc hết hạn**.

### Opaque token

RS có thể gọi introspection RFC 7662:

```json
{
  "active": false
}
```

Sau khi AS thu hồi token và RS không còn positive cache cũ, API có thể từ chối token. Nhưng `active=true` trong **introspection cache** còn hạn tạo ra khoảng trễ.

| Thuộc tính | JWT self-contained | Opaque + introspection |
|---|---|---|
| Xác minh local | Signature/claims/JWKS. | Thường dùng AS introspection qua TLS. |
| Revocation tức thời mặc định | Không. | Có thể nhanh hơn, nhưng phụ thuộc AS/RS cache. |
| Vai trò của logout local | Không làm JWT cũ tự invalid. | Không làm opaque token tự invalid nếu chưa revoke. |
| Audience/scope | RS phải kiểm. | RS phải kiểm metadata từ AS. |
| Token theft/replay | Bearer token vẫn có thể bị dùng nếu hợp lệ. | Tương tự cho đến khi bị từ chối/revoked. |

**Không dùng logout làm cớ bỏ resource authorization**. RS vẫn phải kiểm issuer, audience, scope, token type, thời hạn, tenant và quyền đối tượng.

## 18. Refresh token rotation, reuse detection và logout

Refresh token có thể cho phép client lấy access token mới mà không cần user tương tác. Vì vậy, nếu hệ thống có refresh token:

1. **Lưu an toàn** theo loại client (BFF phía server; mobile dùng OS protected storage; SPA có rủi ro XSS).
2. **Rotation hoặc sender constraint** theo OAuth Security BCP cho public clients khi được phát refresh token.
3. **Revoke token hoặc grant** khi user ngắt kết nối/logout theo yêu cầu security profile.
4. **Dừng background refresh** và hủy đồng bộ để không có request refresh tiếp tục ngay sau logout.
5. **Xử lý `invalid_grant`** như tín hiệu không thể refresh nữa, không tự âm thầm đăng nhập lại trái ý user.
6. **Reuse detection** nếu refresh token family được rotation: khi thấy token cũ bị dùng lại, AS có thể thu hồi family và yêu cầu reauthentication.
7. **Đánh giá race**: request refresh đang bay lúc logout có thể trả token mới, cần session generation/revocation guard.

### Một race thường gặp

```text
T0: Client bắt đầu POST /token grant_type=refresh_token.
T1: User bấm Logout.
T2: Client xóa token local.
T3: Token endpoint trả access token + refresh token mới cho request T0.
T4: Callback async lưu token mới và bật lại trạng thái authenticated.  // SAI
```

**Cách xử lý:** đánh dấu phiên/generation đã bị hủy trước khi xóa cache; cancel outstanding work nếu có thể; khi response đến, kiểm session còn active trước khi lưu token. Nếu policy yêu cầu, revoke token mới vừa được cấp trong race và ghi audit an toàn.

## 19. Browser, SPA, BFF và native mobile: ranh giới logout

| Kiến trúc | Local logout | OP/AS logout | Rủi ro riêng |
|---|---|---|---|
| **Server-rendered app / BFF** | Invalidate server session, clear cookie và token storage server-side. | Redirect browser tới OP logout endpoint nếu hỗ trợ. | Cookie/session fixation, CSRF, distributed sessions, server token store. |
| **SPA public client** | Xóa credentials/UI state khỏi browser storage; hủy refresh/network requests. | Mở OP logout flow theo browser/SDK/provider. | XSS, localStorage, multi-tab, silent re-login do OP cookie. |
| **Native mobile** | Xóa app session, tokens/keys khỏi Keychain/Keystore theo policy. | System browser/ASWebAuthenticationSession hoặc SDK/logout provider, nếu hỗ trợ. | App lifecycle, browser SSO shared, device backups, stale callbacks. |
| **CLI/desktop** | Xóa credential cache, cấu hình session và memory. | Theo flow mà OP cho phép; có thể cần browser. | Token file permissions, shell history/logs và long-running jobs. |

### BFF

Với BFF, browser chủ yếu cầm **HttpOnly Secure session cookie**, còn access/refresh tokens ở backend. Logout local cần:

- Invalidate **server session** và token entries liên quan.
- Clear cookie đúng domain/path.
- Cấm replay một session ID cũ.
- Chặn in-flight authorized-client update thuộc generation đã logout.
- Nếu cần, gọi token revocation từ backend nơi có credential.
- Gửi người dùng sang OP logout endpoint bằng thông tin issuer/ID token hint đã lưu đúng.

**HttpOnly cookie không loại trừ CSRF.** Endpoint logout và các action dùng cookie cần bảo vệ theo threat model.

### SPA

Với SPA, việc xóa localStorage/sessionStorage/memory không chứng minh token đã được AS revoke. Nếu app giữ refresh token, cần theo chính sách bảo vệ token của public client. Tránh phơi bày tokens hoặc `id_token_hint` trong logs, analytics và navigation ngoài OP tin cậy.

### Native mobile

Xóa token khỏi app không tự kết thúc SSO session trong **system browser** hoặc đăng xuất các app khác. Một ứng dụng không thể tùy tiện xóa cookie domain OP của trình duyệt hệ thống. Khi yêu cầu logout OP, dùng đúng provider/OS supported flow; nếu không, giải thích rằng chỉ **phiên của app này** được kết thúc.

## 20. Spring Security 6.x: local logout trên web app

Với Spring Security servlet, có thể dùng cơ chế logout chuẩn của framework.

Ví dụ Spring Boot web app:

```java
@Configuration
@EnableWebSecurity
public class WebSecurityConfig {

    @Bean
    SecurityFilterChain webSecurity(HttpSecurity http)
            throws Exception {

        http.authorizeHttpRequests(auth -> auth
            .requestMatchers("/", "/logged-out", "/health").permitAll()
            .anyRequest().authenticated());

        http.oauth2Login(Customizer.withDefaults());

        http.logout(logout -> logout
            .logoutUrl("/logout")
            .invalidateHttpSession(true)
            .clearAuthentication(true)
            .deleteCookies("JSESSIONID")
            .logoutSuccessUrl("/logged-out"));

        return http.build();
    }
}
```

Khi CSRF đang bật trong Spring Security, logout qua **POST /logout** với CSRF token thích hợp là hành vi nên sử dụng cho session/cookie authentication. Không thêm một custom `GET /logout` làm thay đổi trạng thái chỉ để dễ bấm link.

Ví dụ form HTML/Thymeleaf khái niệm:

```html
<form method="post" action="/logout">
  <input type="hidden"
         name="_csrf"
         value="CSRF_TOKEN_FROM_SERVER">
  <button type="submit">Đăng xuất</button>
</form>
```

`CSRF_TOKEN_FROM_SERVER` là placeholder; ứng dụng thực cần render token từ cơ chế CSRF hiện hành. Trong Thymeleaf tích hợp Spring Security, CSRF hidden input có thể được chèn tự động khi dùng đúng cơ chế template; phải kiểm request thật.

**Điều cần lưu ý:** `deleteCookies("JSESSIONID")` chỉ đúng khi domain/path cookie phù hợp. Xóa cookie ở browser **không thay** invalidate session server. Với session repository phân tán hoặc nhiều cookies, hãy kiểm config thật và xóa credentials/cache thuộc phiên.

### Authorized client storage

Spring Security có `OAuth2AuthorizedClientRepository`/`OAuth2AuthorizedClientService`. Nếu token được lưu trong database **không tự gắn vòng đời vào HttpSession**, chỉ invalidate HTTP session có thể **chưa xóa các authorized-client records**.

Cần xác định bản ghi thuộc user/session nào, có cần dùng sau logout không và cách revoke/cleanup một cách an toàn. Không xóa bừa OAuth tokens của **mọi thiết bị** nếu user chỉ yêu cầu logout local.

## 21. Spring Security: RP-Initiated Logout với OP

Spring Security cung cấp **`OidcClientInitiatedLogoutSuccessHandler`** cho kịch bản OIDC login và RP-Initiated Logout khi OP hỗ trợ.

Mẫu Spring Security 6.x:

```java
@Configuration
@EnableWebSecurity
public class OidcWebLogoutConfig {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            ClientRegistrationRepository registrations)
            throws Exception {

        OidcClientInitiatedLogoutSuccessHandler oidcLogout =
            new OidcClientInitiatedLogoutSuccessHandler(registrations);

        oidcLogout.setPostLogoutRedirectUri(
            "{baseUrl}/logged-out");

        http.authorizeHttpRequests(auth -> auth
            .requestMatchers("/", "/logged-out", "/health").permitAll()
            .anyRequest().authenticated());

        http.oauth2Login(Customizer.withDefaults());

        http.logout(logout -> logout
            .logoutUrl("/logout")
            .invalidateHttpSession(true)
            .clearAuthentication(true)
            .logoutSuccessHandler(oidcLogout));

        return http.build();
    }
}
```

Đây là mẫu minh họa dùng **OIDC RP-Initiated Logout**, chưa phải toàn bộ security config production:

- OP cần hỗ trợ và công bố **`end_session_endpoint`** cho issuer.
- **`post_logout_redirect_uri`** phải được OP cho phép/đăng ký theo hợp đồng.
- Framework có thể tạo `id_token_hint` từ OIDC authentication nếu có; hãy test request logout thực tế.
- CSRF vẫn cần cho POST logout trong app dùng session cookie.
- Local session cleanup và OAuth authorized-client cleanup/revocation cần được kiểm riêng.
- Đây là flow **đề nghị OP logout**, không phải bảo đảm revoke access/refresh tokens.
- Không tự bật Back-Channel Logout chỉ vì đã cấu hình `OidcClientInitiatedLogoutSuccessHandler`.

Nếu OP không hỗ trợ `end_session_endpoint` hoặc session không phải OIDC login, handler behavior phụ thuộc version/library. Ứng dụng nên có **fallback local logout** được xác minh; không redirect tới URL tự đoán.

## 22. Spring Security: tách revoke token khỏi logout handler

Trong hệ thống BFF, một dịch vụ chịu trách nhiệm cleanup có thể thực hiện **token revocation** riêng theo RFC 7009.

Pseudocode:

```java
// Pseudocode: interfaces dưới đây do ứng dụng định nghĩa.
void logoutCurrentSession(VerifiedSession session) {
    sessionRegistry.markLoggingOut(session.id());
    sessionRegistry.invalidate(session.id());

    oauthJobScheduler.cancelForSession(session.id());
    oauthAuthorizedClientStore.removeForSession(session.id());

    try {
        tokenRevocationService.revokeRefreshTokenIfPresent(
            session.issuer(),
            session.clientRegistrationId(),
            session.refreshToken());
    } catch (RevocationUnavailableException ex) {
        // Không hồi sinh session. Theo security policy, audit và
        // retry an toàn hoặc đánh dấu revoke pending.
        audit.recordRevocationPending(session.reference());
    }

    redirectToProviderLogoutIfConfigured(session);
}
```

**Các class, methods và thứ tự triển khai là pseudocode**, không phải Spring APIs có sẵn. Trong code thật, cần:

- Tránh vô tình đọc refresh token từ store **sau khi đã xóa**; capture nó vào ngữ cảnh an toàn trước khi xóa, đồng thời giảm thời gian tồn tại trong memory.
- Ràng buộc revocation request với đúng AS issuer/client authentication.
- Bảo vệ idempotency và race với refresh đang chạy.
- Không delay local logout vô hạn vì AS revoke timeout.
- Nếu ghi job retry, **không lưu raw refresh token trong queue không mã hóa** hoặc logs; dùng protected secret handle.
- Không coi logout success handler redirect là dấu hiệu revoke thành công.

**Revoke một refresh token của user/session không được tự xóa token mọi tài khoản** nếu sản phẩm chỉ yêu cầu thoát phiên hiện tại.

## 23. Browser cookies, CSRF và logout safety

Logout là hành động thay đổi trạng thái. Nếu app đăng nhập bằng cookie, attacker có thể cố **ép browser gửi request logout** mà user không chủ động thực hiện (logout CSRF).

### Kiểm soát cần có

- Dùng **POST** với CSRF protection cho logout endpoint khi dùng cookie authentication.
- Đặt cookies **Secure**, **HttpOnly** (với session cookie) và `SameSite` phù hợp mô hình redirect OIDC.
- Chống **session fixation** khi đăng nhập và đảm bảo session ID cũ bị invalidate khi logout.
- Dùng `Cache-Control: no-store` cho trang/dữ liệu riêng nhạy cảm khi cần.
- Đảm bảo không dùng GET state-changing logout action tùy tiện.
- Không nhận `returnUrl` tùy ý dẫn đến open redirect.
- Không để cross-origin scripts đọc tokens từ logout URLs hoặc responses.
- Kiểm CORS/cookie/domain đúng với ứng dụng; CORS **không thay CSRF protection**.

### Cookie OP và cookie RP

Browser chỉ cho ứng dụng thao tác cookie thuộc domain/path chính sách của nó. RP **không thể xóa SSO cookie HttpOnly của OP tại domain khác**. Cách hợp lệ là điều hướng người dùng đến OP logout flow hoặc dùng cơ chế SLO được OP hỗ trợ.

### SameSite và OIDC redirects

OIDC Authorization Code flow sử dụng cross-site redirects, nên cookie `SameSite` quá chặt có thể làm mất session/state khi callback; quá lỏng lại tăng bề mặt CSRF. Chọn thuộc tính theo flow (top-level GET, form_post, proxy, browser) và **kiểm thử thực tế**. Không khuyên đặt `SameSite=None` cho mọi cookie như một “cách sửa login/logout” chung.

## 24. XSS, token storage và logout không xóa credential bị sao chép

Nếu kẻ tấn công có thể chạy JavaScript độc hại trong SPA, họ có thể đọc token trong các storage mà script có quyền truy cập. Sau đó người dùng logout và xóa localStorage, nhưng attacker **đã có bản sao token**.

| Sự kiện | Logout local giúp gì? | Còn rủi ro gì? |
|---|---|---|
| Xóa access token trong memory | Client không dùng token nữa. | Bản sao bị lấy trước vẫn có thể hoạt động. |
| Xóa refresh token trong localStorage | Ngăn chính app tiếp tục refresh. | Attacker đã lấy token có thể refresh nếu chưa revoke/sender-constrained. |
| Invalidate BFF session | Cookie cũ không được server chấp nhận. | Access token đã lộ ở nơi khác vẫn có thể hợp lệ. |
| OP SSO logout | Browser không còn phiên SSO tương ứng theo OP policy. | JWT/opaque tokens đã cấp không tự bị revoke. |
| Grant/refresh family revocation | Giảm khả năng xin token mới. | Access token đã phát có thể còn hạn hoặc cache revoke chưa cập nhật. |

**Biện pháp lớp sâu:** chống XSS, CSP phù hợp, BFF khi hợp lý, token TTL ngắn, rotation/sender constraint, revocation/denylist/introspection và least privilege.

Logout là một thành phần trong bảo mật vòng đời token, **không phải phương án thay cho bảo vệ token ngay từ đầu**.

## 25. Sender-constrained token sau logout

Access token có thể được ràng buộc với người giữ khóa bằng:

- **DPoP** (RFC 9449): JWT proof cho HTTP request, ràng buộc key thumbprint.
- **mTLS-bound access token** (RFC 8705): token liên kết client certificate.

Điều này làm giảm khả năng kẻ chỉ lấy bản sao token sử dụng nó mà không có private key phù hợp. Nhưng:

- Nếu attacker chiếm **runtime và signing key**, vẫn có rủi ro.
- Logout local có thể xóa key material hoặc key reference theo policy, nhưng không có nghĩa AS đã revoke token.
- RS vẫn phải kiểm DPoP proof/mTLS binding cho từng request.
- Nếu key được dùng bởi nhiều sessions, không xóa một cách khiến phiên hợp pháp khác bị lỗi mà không có chính sách.
- Sender constraint không thay issuer, audience, scope và business authorization.

**Không coi `cnf` trong JWT/introspection là đủ:** nếu RS không kiểm proof, token có thể bị dùng như một bearer credential dù được kỳ vọng sender-constrained.

## 26. Logout khi có nhiều thiết bị và nhiều tenant

Một tài khoản có thể tồn tại:

```text
Desktop browser, tenant A:
    RP session W-A
    OP session S-A
    Refresh family F-A

Mobile app, tenant A:
    App session M-A
    OP browser context S-M
    Refresh family F-M

Desktop browser, tenant B:
    RP session W-B
    OP session S-B (tùy OP)
    Refresh family F-B
```

**Logout khỏi W-A** không được tự mặc định thu hồi F-M hoặc logout tenant B nếu user chỉ muốn thoát phiên desktop.

Khi tính năng yêu cầu **“Đăng xuất khỏi tất cả thiết bị”**, cần thiết kế riêng:

1. Xác minh chủ thể có quyền yêu cầu global logout.
2. Xác định tập sessions/grants theo **issuer + subject + tenant + client policy**.
3. Thu hồi hoặc vô hiệu từng session phù hợp ở RP/OP.
4. Revoke refresh token families/grants theo policy.
5. Thông báo SLO đến các RPs nếu có hỗ trợ.
6. Thực thi access-token revocation latency và bảo vệ những routes nhạy cảm.
7. Đảm bảo thao tác không làm ảnh hưởng sai tenants/users khác.
8. Audit outcomes, lỗi từng hệ thống và cơ chế retry/reconciliation.

**Không dùng mỗi chuỗi `sub` để khóa mọi phiên trên toàn hệ sinh thái**: `sub` chỉ có ý nghĩa trong issuer và ngữ cảnh thích hợp, có thể trùng giữa issuers.

## 27. Logout với authorization server không đồng nghĩa OAuth consent revocation

Một bên thứ ba có thể đang giữ grant cho `orders.read` và refresh token để đồng bộ ngoài phiên browser. Khi user logout khỏi OP SSO:

- Người dùng có thể không còn authenticated tại OP browser.
- Third-party client vẫn có thể giữ **consent/grant ACTIVE**, tùy AS.
- Refresh token của third-party có thể tiếp tục hoạt động cho đến khi bị revoke/hết hạn.
- Dữ liệu client đã tải về vẫn còn theo chính sách retention.

**Nếu mục tiêu là “Ngắt kết nối ứng dụng bên thứ ba”**, cần **revoke consent/grant hoặc token riêng của ứng dụng**, không chỉ bấm Logout tại OP. Nếu cần cả logout SSO và ngắt kết nối app, UI cần thể hiện hai hành động hoặc một lựa chọn phạm vi rõ ràng.

Đây cũng là lý do cần phân biệt **consent, authentication, authorization grant và access-token validity** trong mọi sự cố an ninh.

## 28. Logout và access-token scope/audience

Giả sử một Bearer token trước logout có:

```json
{
  "iss": "https://id.example.test",
  "sub": "user-123",
  "aud": "orders-api",
  "scope": "orders.read",
  "exp": 1795410600
}
```

Payload trên chỉ để minh họa.

Kẻ lấy token có thể thử:

- Gọi **Payments API** → phải bị từ chối vì **sai audience**.
- Gọi **Orders approve endpoint** → phải bị từ chối nếu thiếu `orders.approve`.
- Gọi **Orders read endpoint** → vẫn có thể được xử lý nếu token còn active và đối tượng đúng quyền.

**Audience và scope thu hẹp phạm vi thiệt hại, không chứng minh caller có session RP còn active.** Nếu yêu cầu logout khiến token không còn dùng được ngay, RS cần tham gia enforcement bằng denylist/introspection/grant state.

Một API không được chấp nhận ID token `aud=orders-web` để thay access token `aud=orders-api` chỉ vì ID token được phát cho user đã đăng nhập.

## 29. Giao thức logout và các mã lỗi cần phân biệt

| Giai đoạn | Tình huống | Cách xử lý |
|---|---|---|
| Local RP logout | Session đã hết hạn hoặc đã logout. | Idempotent local cleanup; không tái tạo session. |
| POST /logout | Thiếu/sai CSRF với session cookie. | Chặn request, không âm thầm thực hiện. |
| RP-Initiated Logout | OP không có `end_session_endpoint`. | Local logout vẫn hoàn thành; không tự tạo URL không có cơ sở. |
| RP-Initiated Logout | `post_logout_redirect_uri` không đăng ký. | OP từ chối redirect hoặc xử lý theo profile; không open redirect. |
| RP-Initiated Logout | `id_token_hint` sai issuer/client. | OP từ chối hoặc yêu cầu xác nhận theo policy, không trust hint giả. |
| Back-Channel Logout | Logout Token sai chữ ký/audience/issuer. | RP từ chối, không invalidate sessions. |
| Back-Channel Logout | `jti` replay. | RP idempotent/replay reject theo profile. |
| Token revocation | Client auth thất bại. | Xử lý lỗi của revocation endpoint, không khẳng định đã revoke. |
| Token revocation | Token không tồn tại. | Theo RFC 7009 thường HTTP 200, không enumerate tokens. |
| Token use at RS | Access token expired/invalid. | Thường `401 invalid_token`. |
| Token use at RS | Token hợp lệ nhưng thiếu scope. | Thường `403 insufficient_scope`. |
| RS introspection | AS outage/timeout. | Không fail-open; dùng cache trong policy hoặc từ chối. |

**Không gom tất cả các lỗi thành “Logout success”**. Hệ thống cần có các trạng thái riêng: local logout completed, OP request initiated/completed khi biết, token revocation pending/failed, SLO notification results.

## 30. Audit logout mà không làm lộ credentials

| Event | Trường ghi phù hợp |
|---|---|
| `LOCAL_LOGOUT_REQUESTED` | RP session reference, trace ID, timestamp, logout scope. |
| `LOCAL_SESSION_INVALIDATED` | Session ref (đã hash/HMAC), user/tenant ref, outcome. |
| `OIDC_RP_LOGOUT_INITIATED` | Trusted issuer, client ID, redirect registration reference. |
| `OIDC_OP_LOGOUT_RETURNED` | State correlation result, không khẳng định token revoke. |
| `OIDC_BACKCHANNEL_LOGOUT_RECEIVED` | Verified OP issuer, client, sid/sub ref, jti digest, validation outcome. |
| `TOKEN_REVOCATION_REQUESTED` | Grant/token reference, issuer, reason class. |
| `TOKEN_REVOCATION_CONFIRMED` | Response outcome, revocation propagation policy. |
| `TOKEN_REVOCATION_PENDING` | Retry handle an toàn, không raw token. |
| `GLOBAL_LOGOUT_REQUESTED` | Authorized subject, tenant, scope, step-up result. |
| `RESOURCE_TOKEN_DENIED` | Issuer/audience/policy reason, không access token thô. |

**Không log** raw session cookies, access token, refresh token, full ID token hint, client secret, authorization code, PKCE verifier hoặc private key. Đặc biệt tránh ghi nguyên OP logout URL chứa `id_token_hint`, query strings của callback và HTTP Authorization header.

Có thể dùng **opaque session IDs**, salted HMAC references/correlation IDs với quản trị khóa và retention thích hợp để điều tra mà không lưu raw credentials.

## 31. Các lỗi triển khai phổ biến

| Sai lầm | Tác động | Cách khắc phục |
|---|---|---|
| Xóa cookie nhưng không invalidate session server. | Cookie bị sao chép có thể tiếp tục dùng. | Session invalidation và cookie cleanup. |
| Xóa UI state rồi coi access token đã revoke. | Bearer token bị lộ vẫn có thể hoạt động. | Revocation/RS enforcement theo yêu cầu. |
| Logout local nhưng báo “đã logout toàn bộ SSO”. | Người dùng có thể silent login lại. | Thể hiện phạm vi logout chính xác. |
| Gọi OP logout và tự kết luận refresh token đã bị revoke. | Offline access có thể còn hoạt động. | RFC 7009/grant policy riêng. |
| Revoke refresh nhưng không xét access JWT còn hạn. | API còn cửa sổ chấp nhận token. | TTL/denylist/introspection/revoke budget. |
| Không xóa OAuth authorized-client store persistent. | Backend vẫn giữ credential sau session logout. | Cleanup theo đúng session/grant ownership. |
| Gỡ token nhưng callback refresh trễ ghi token mới. | Đăng nhập “hồi sinh”. | Generation/cancel guard và revoke race. |
| Logout bằng GET không CSRF khi dùng session cookie. | Logout CSRF, gián đoạn phiên. | POST + CSRF protection. |
| RP cố xóa cookie domain OP. | Không có quyền cross-origin; thao tác vô hiệu. | OP end-session flow chính thức. |
| Tự đoán logout endpoint của provider. | Open redirect hoặc sai OP. | Trusted discovery/registration. |
| Nhận `post_logout_redirect_uri` từ user không kiểm. | Open redirect/phishing. | URI allowlist/registered exact match. |
| Log nguyên `id_token_hint` trong redirect URL. | Rò PII/token và correlation data. | Redaction/Referrer-Policy/HTTPS. |
| Back-channel nhận Logout Token chưa verify. | Attacker logout phiên bất kỳ. | Signature/iss/aud/events/jti/sid validation. |
| Map `sid` của một issuer sang session của issuer khác. | Cross-issuer session confusion. | Bind issuer + client + sid. |
| Nhận `sub` rồi logout mọi device ngoài policy. | Logout quá phạm vi. | Session-scoped vs subject-wide policy rõ. |
| Front-channel iframe bị chặn nhưng xem SLO đã hoàn tất. | Các RP khác còn session. | Theo dõi delivery/Back-Channel khi cần. |
| Không xử lý OP outage. | Local session vẫn active hoặc UI treo. | Local-first cleanup, status rõ, retry policy. |
| Chỉ kiểm JWT signature ở RS, bỏ aud/scope. | Token sai quyền/đích vẫn được dùng. | Token validation đầy đủ và resource authorization. |
| Opaque introspection cache quá dài sau revoke. | Stale active=true. | Cap TTL, invalidation, revoke budget. |
| Mobile logout app nhưng tuyên bố browser SSO cookie mất. | Re-login tự động, gây hiểu nhầm. | Dùng system browser/provider flow; mô tả giới hạn. |
| Xóa mọi token của tenant khi user logout một tab. | Tác động rộng và sai thẩm quyền. | Bind chính xác session/grant/subject. |
| Token revocation request bị fail nhưng log success. | Cửa sổ tấn công tiếp diễn. | Phân biệt pending/failed, audit/reconciliation. |

## 32. Ma trận kiểm thử local và authorization server logout

Giả sử ứng dụng `orders-web` là OIDC RP/BFF của `https://id.example.test`, Orders API là RS cho `aud=orders-api`; local web session được quản lý phía server và OP có thể hỗ trợ RP-Initiated Logout. Hệ thống có access JWT hoặc opaque token tùy profile.

| ID | Kịch bản | Kết quả mong đợi |
|---|---|---|
| L01 | User POST logout hợp lệ tại Orders. | Local session bị invalidate và auth context được xóa. |
| L02 | Browser xóa cookie nhưng server session còn active. | Test phát hiện lỗi, cookie cũ không được dùng lại sau logout đúng. |
| L03 | GET /logout trong app cookie-based. | Không làm state change nếu không có CSRF protection phù hợp. |
| L04 | POST /logout thiếu CSRF token. | Từ chối theo CSRF policy. |
| L05 | POST logout hai lần. | Idempotent, không tạo session mới. |
| L06 | Cookie `JSESSIONID` có Domain/Path khác. | Test bảo đảm cookie cleanup đúng, server session vẫn invalidate. |
| L07 | Server dùng distributed session store. | Phiên bị invalidate trên mọi node liên quan. |
| L08 | OAuth authorized client token store nằm ngoài HttpSession. | Cleanup đúng record thuộc phiên khi logout policy yêu cầu. |
| L09 | Local logout nhưng OP SSO còn active. | Re-login có thể không cần password; test phân biệt session mới/cũ. |
| L10 | Local logout không gọi OP. | OP session và RP khác không được tự coi đã logout. |
| L11 | User chọn “Logout khỏi SSO”, OP hỗ trợ end_session_endpoint. | RP chuyển browser tới OP logout request. |
| L12 | OP không hỗ trợ end_session_endpoint. | Local logout thành công; fallback minh bạch. |
| L13 | Logout URL từ issuer do user tự cung cấp. | Chặn redirect/token exfiltration. |
| L14 | `id_token_hint` do issuer khác phát. | OP/handler không tin hint sai. |
| L15 | `post_logout_redirect_uri` chưa đăng ký. | OP không chuyển về URI tùy ý. |
| L16 | Client truyền user-supplied returnUrl. | Không open redirect. |
| L17 | Logout `state` trong redirect về không khớp. | RP không coi callback là transaction đã hoàn tất. |
| L18 | OP yêu cầu confirmation vì thiếu hint tin cậy. | UI/flow xử lý theo OP policy, không bỏ qua xác minh. |
| L19 | OP logout thành công nhưng app Reports còn session. | Không tuyên bố SLO nếu chưa có propagation. |
| L20 | Front-channel logout bị chặn cookie/iframe. | Test phát hiện RP khác còn active, không false success. |
| L21 | Back-channel Logout Token chữ ký sai. | RP từ chối thông báo. |
| L22 | Back-channel Logout Token sai `aud`/issuer. | RP từ chối. |
| L23 | Back-channel Logout Token thiếu sự kiện `events` hợp lệ. | RP từ chối theo profile. |
| L24 | Back-channel Logout Token `jti` replay. | Không invalidate phiên mới/khác; xử lý idempotent. |
| L25 | Back-channel Logout Token có `sid=SID-A`. | RP chỉ logout session map SID-A. |
| L26 | Back-channel `sub` được dùng trong policy subject-wide. | Chỉ ảnh hưởng sessions thuộc đúng issuer/client/subject. |
| L27 | Logout request bị user cancel giữa chừng. | Local session không được hồi sinh, trạng thái rõ. |
| L28 | Token revocation endpoint nhận refresh token hợp lệ. | AS xử lý revocation theo RFC 7009/policy. |
| L29 | Revoke token không tồn tại. | Theo RFC 7009 response thành công không làm lộ token existence. |
| L30 | Revoke client authentication sai. | Không báo revocation thành công. |
| L31 | Access JWT còn hạn sau local/OP logout. | Test phản ánh RS có thể vẫn nhận nếu chưa revoke/denylist. |
| L32 | JWT có `jti` trong denylist sau revoke. | RS từ chối theo enforcement policy. |
| L33 | Opaque token sau revoke trả introspection `active=false`. | RS từ chối. |
| L34 | Cache opaque `active=true` còn hạn sau revoke. | Test đo revocation latency/TTL. |
| L35 | Access token sai `aud` sau logout. | RS từ chối dù token chưa hết hạn. |
| L36 | Access token thiếu scope. | RS từ chối operation. |
| L37 | ID token được dùng làm access token API. | RS từ chối. |
| L38 | Refresh token bị dùng trực tiếp tại API. | RS từ chối token type. |
| L39 | Refresh request bắt đầu trước logout, trả token sau logout. | Callback không lưu/hồi sinh phiên. |
| L40 | Refresh token rotation reuse sau logout. | AS phát hiện/xử lý theo family policy. |
| L41 | Local logout ở thiết bị A. | Thiết bị B vẫn active nếu không có global policy. |
| L42 | Global logout được thực hiện bởi user không có authority. | Từ chối yêu cầu vượt quyền. |
| L43 | Global logout cho tenant A. | Không xóa nhầm phiên tenant B. |
| L44 | SPA xóa token localStorage. | Không tuyên bố token đã bị AS revoke. |
| L45 | BFF invalidate session cookie nhưng thiếu cleanup token DB. | Test phát hiện residual credential storage. |
| L46 | Mobile logout app rồi dùng system browser có OP SSO. | Re-login có thể silent; UI/flow phản ánh đúng. |
| L47 | OP outage ở thời điểm redirect logout. | Local logout vẫn được duy trì; không fail open. |
| L48 | AS revocation timeout. | Ghi pending/failed theo policy, không nói đã revoke. |
| L49 | Hai callback logout thành công đến đồng thời. | Idempotent, không có race tạo session mới. |
| L50 | Session ID cũ bị replay sau logout. | Không truy cập được dữ liệu bảo vệ. |
| L51 | Logout URL chứa raw ID token trong access log. | Redaction/security test phát hiện lỗi. |
| L52 | API nhận bearer bị attacker sao chép trước logout. | Threat test mô tả rủi ro replay còn lại tới revoke/exp. |
| L53 | Multi-tab: tab 1 logout, tab 2 gọi API với cookie cũ. | Server từ chối session cũ; UI đồng bộ trạng thái. |
| L54 | Browser back-button hiện trang cũ chứa dữ liệu nhạy cảm. | Cache-control/UX policy hạn chế rò dữ liệu. |
| L55 | App logout nhưng service worker/background job vẫn refresh. | Jobs bị hủy hoặc stale responses bị bỏ qua. |
| L56 | Back-channel network outage, một RP không nhận message. | Theo dõi delivery/retry và không khẳng định SLO hoàn tất. |
| L57 | User chọn revoke connected third-party app. | AS thu hồi grant/refresh theo policy, không chỉ OP SSO session. |
| L58 | Consent revoke nhưng third-party đã download dữ liệu. | Test xác nhận không hứa dữ liệu tự xóa. |
| L59 | Security config Spring dùng logout success handler nhưng OP không có logout metadata. | Fallback local logout được test; không redirect tùy ý. |
| L60 | Audit log có access token, refresh token hoặc cookies. | Security/redaction test thất bại. |

### Test theo các tầng

- **Unit tests:** session generation, cleanup idempotency, token cache ownership, logout state/issuer URI allowlist, race guards.
- **Browser end-to-end:** logout form POST+CSRF, cookie expiry, SameSite, multi-tab, back-button, SSO re-login và OP redirect.
- **OIDC integration:** discovery `end_session_endpoint`, `id_token_hint`, `post_logout_redirect_uri` allowlist, state binding, OP confirmation.
- **Front-/Back-Channel tests:** delivery, `sid` mapping, JWT signature/issuer/audience/events/jti, replay và failover.
- **AS revocation tests:** refresh/access revoke, 200 on unknown token, credential auth failure, grant/family propagation.
- **RS tests:** JWT signature/issuer/aud/scope, opaque introspection, denylist, revocation latency, tenant policy.
- **Resilience tests:** OP/AS outage, timeout, distributed sessions, stale callbacks, background jobs và retries.
- **Operational/security tests:** token storage, cookie flags, log redaction, malicious return URL, logout CSRF và incident investigation.

**Mock principal hoặc Spring Security Test `jwt()` có thể kiểm endpoint authorization nhưng không chứng minh OP SSO đã logout, back-channel Logout Token đã được xác minh hoặc AS đã revoke refresh token.** Muốn kết luận end-to-end phải kiểm từng hệ thống thật hoặc test double triển khai đúng contract.

## 33. Tình huống học tập

### A. Đã logout nhưng bấm login không cần mật khẩu

User logout Orders local, nhưng OP vẫn giữ SSO cookie.

**Câu hỏi:** Local logout có thất bại không?

> Không nhất thiết. RP session cũ đã bị invalidate; OP SSO còn hoạt động nên có thể tạo **session RP mới** sau Authorization Code flow. Nếu yêu cầu thoát SSO, dùng RP-Initiated Logout khi OP hỗ trợ.

### B. OP logout rồi token vẫn gọi được API

RP gọi `end_session_endpoint` thành công, nhưng access JWT còn 5 phút và RS chỉ kiểm chữ ký/`exp`.

**Câu hỏi:** Đây là lỗi OIDC logout hay thiếu yêu cầu revoke token?

> OP logout quản lý SSO session; access token đã phát có **vòng đời riêng**. Nếu chính sách yêu cầu API token bị từ chối ngay, cần revocation/denylist/introspection hoặc token policy phù hợp.

### C. Refresh token vẫn hoạt động sau logout

Ứng dụng đóng local session nhưng refresh token trong database vẫn được một background worker dùng.

**Câu hỏi:** Cần làm gì?

> Ràng buộc authorized-client storage với session/grant, dừng jobs, xử lý race và revoke refresh token/grant nếu logout yêu cầu cắt offline access.

### D. Back-channel token có issuer giả

Một request POST vào RP logout callback chứa JWT có `sid` của nạn nhân nhưng chữ ký sai.

**Câu hỏi:** Có được xóa session tương ứng không?

> Không. RP phải xác minh Logout Token theo Back-Channel Logout profile: issuer, audience, signature, events, replay và session binding. Không dùng `sid` chưa được xác minh.

### E. User muốn logout riêng Orders, không logout Reports

Hai RP dùng chung OP SSO. User chỉ chọn “Thoát Orders”.

**Câu hỏi:** Có nên luôn gọi OP end-session để “an toàn hơn” không?

> Không mặc định. Làm vậy có thể ảnh hưởng SSO của Reports. Phải có sản phẩm/UX policy phân biệt **logout ứng dụng** và **logout tài khoản/SSO**.

### F. Mobile app đã xóa token nhưng browser vẫn còn SSO

App mobile xóa tokens trong Keychain, rồi người dùng bấm Login lại và system browser dùng phiên SSO hiện có.

**Câu hỏi:** Vì sao?

> App local storage và OP browser authentication session thuộc **hai ranh giới khác nhau**. Cần dùng logout flow của OP khi muốn kết thúc SSO, hoặc thể hiện đúng rằng chỉ app logout.

### G. Một JWT đã bị đánh cắp trước logout

Attacker có bearer access token `aud=orders-api, scope=orders.read`. Người dùng local logout.

**Câu hỏi:** Attacker có bị khóa ngay không?

> Không bảo đảm. Nếu token còn hạn và RS không kiểm revocation, attacker có thể dùng token **trong audience/scope được cấp**. TTL, revocation và sender constraint giúp giảm nguy cơ.

### H. User revoke app bên thứ ba nhưng dữ liệu vẫn còn

Người dùng chọn “Ngắt kết nối đối tác” rồi bên thứ ba vẫn giữ tệp đã xuất.

**Câu hỏi:** OAuth revoke có tự xóa tệp không?

> Không. Token/grant revoke ngăn truy cập tiếp theo, không tự xóa dữ liệu đã sao chép. Cần quy trình data retention/deletion riêng.

### Tự đánh giá

1. Local RP session và OP SSO session khác nhau thế nào?
2. Vì sao logout local không tự xóa cookie OP ở domain khác?
3. RP-Initiated Logout dùng endpoint/metadata nào và nhằm mục đích gì?
4. `id_token_hint` dùng để gợi ý điều gì? Có được thay bằng access token không?
5. Vì sao `post_logout_redirect_uri` phải được đăng ký/kiểm tra?
6. `state` ở logout có thay JWT signature/issuer validation không?
7. Front-Channel Logout khác Back-Channel Logout về kênh và độ tin cậy thế nào?
8. Một Logout Token cần ràng buộc với issuer, client và session như thế nào?
9. `sid` khác `sub` ra sao khi logout một thiết bị so với tất cả thiết bị?
10. RFC 7009 token revocation khác OP logout ở phạm vi nào?
11. Vì sao JWT còn `exp` có thể được RS chấp nhận sau logout?
12. Với opaque token, introspection cache ảnh hưởng revocation latency thế nào?
13. Vì sao refresh token rotation cần race guard khi logout?
14. Tại sao không nên implement GET /logout thay POST+CSRF cho browser session?
15. Logout trên mobile có tự xóa SSO browser session của OP không?
16. Vì sao audience và scope vẫn cần được RS kiểm ngay cả sau logout?
17. Phải kiểm thử những hệ thống nào để khẳng định global logout đã hoàn tất?

## 34. Ghi nhớ

- **Logout local kết thúc phiên tại RP**: invalidate server session, clear authentication, cookie và credential/cache thuộc phiên theo policy.
- **Logout tại OP/AS SSO là thao tác khác**, dùng OIDC RP-Initiated Logout khi OP hỗ trợ. RP **không thể tự xóa cookie OP khác domain**.
- **Revoke access/refresh token là cơ chế riêng** (ví dụ RFC 7009); OP logout không tự bảo đảm mọi JWT/opaque tokens bị vô hiệu.
- **OIDC RP-Initiated Logout** có thể dùng `end_session_endpoint`, `id_token_hint`, `post_logout_redirect_uri` và `state` theo profile/đăng ký.
- **Front-Channel Logout** thông báo qua browser, bị ảnh hưởng bởi cookie/iframe restrictions; **Back-Channel Logout** gửi Logout Token qua server-to-server, yêu cầu JWT validation và session correlation.
- **`sid` giúp logout theo phiên; `sub` theo subject** có thể ảnh hưởng nhiều phiên; luôn ràng buộc issuer/client/tenant và policy.
- **Local logout không làm JWT tự chứa bị thu hồi**. Với opaque token, introspection có thể phát hiện revoke nhưng cache vẫn tạo độ trễ.
- **Refresh token có thể duy trì offline access**; cần cleanup/revocation và chống race với refresh đang chạy.
- **POST logout + CSRF, cookie/session security, chống open redirect và log redaction** là các lớp bảo vệ thiết yếu cho browser app.
- **SPA/BFF/mobile có ranh giới storage và SSO khác nhau**; không hứa logout toàn hệ sinh thái khi chỉ xóa local state.
- **Audience, scope, token type và object authorization luôn cần được RS kiểm tra**; token bị lộ có thể bị replay trong quyền đã cấp nếu chưa bị chặn.
- **Một thao tác “đăng xuất mọi thiết bị/ứng dụng” phải có thiết kế session và grant revocation toàn cục**, theo dõi kết quả từng hệ thống và trình bày phạm vi minh bạch.

### Tài liệu chuẩn tham khảo

- [OpenID Connect RP-Initiated Logout 1.0](https://openid.net/specs/openid-connect-rpinitiated-1_0.html): RP yêu cầu OP logout, `end_session_endpoint`, `id_token_hint` và post-logout redirect.
- [OpenID Connect Front-Channel Logout 1.0](https://openid.net/specs/openid-connect-frontchannel-1_0.html): OP thông báo logout tới RPs qua user-agent.
- [OpenID Connect Back-Channel Logout 1.0](https://openid.net/specs/openid-connect-backchannel-1_0.html): Logout Token, server-to-server notification, `sid` và JWT validation.
- [OpenID Connect Session Management 1.0](https://openid.net/specs/openid-connect-session-1_0.html): quản lý session giữa OP và RP qua browser.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): Authentication Request, ID token, `nonce` và ID token validation.
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html): issuer, metadata, end-session endpoint.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): revoke access/refresh token và giới hạn giao thức.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): trạng thái token và `active`, revocation visibility.
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): access/refresh token, AS/RS/client roles và grants.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): Bearer token replay và `invalid_token`/`insufficient_scope`.
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700): refresh security, token theft, redirect hardening và sender constraints.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): JWT access token type, issuer, audience và scope.
- [RFC 9449 — OAuth 2.0 DPoP](https://www.rfc-editor.org/rfc/rfc9449) và [RFC 8705 — OAuth 2.0 mTLS](https://www.rfc-editor.org/rfc/rfc8705): sender-constrained tokens và replay protection.
- [Spring Security — Logout](https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html): HttpSecurity logout, session invalidation, CSRF và logout handlers.
- [Spring Security — OIDC Logout](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/logout.html): OIDC RP-Initiated Logout và Spring Security integration.
