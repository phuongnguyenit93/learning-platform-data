# Federated logout (Đăng xuất liên kết)

> **Chương:** Đăng xuất  
> **Module:** SECURITY_AUTHENTICATION_FUNDAMENTALS — tìm hiểu nguyên lý xác thực danh tính từ credential, mật khẩu, MFA, passkey và chứng chỉ đến token, phiên, liên kết danh tính và khôi phục tài khoản. Người học biết mô hình hóa ranh giới tin cậy, phòng chống phishing, replay, lạm dụng đăng nhập và thiết kế luồng xác thực an toàn.
>
> **Trọng tâm:** Hiểu cách kết thúc phiên trên nhiều ứng dụng và Identity Provider trong một hệ thống liên kết; phân biệt local logout, IdP logout và Single Logout; triển khai OIDC/SAML logout an toàn, thu hồi phiên/token, xử lý browser restrictions và các tình huống một phần hoặc lỗi mạng.

## Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích federated logout và phân biệt local logout, IdP logout, RP/SP logout và Single Logout (SLO).
2. Mô tả vì sao một lần đăng nhập SSO thường tạo nhiều phiên độc lập và vì sao kết thúc một phiên không tự động kết thúc tất cả.
3. Phân tích các luồng OIDC RP-initiated logout, front-channel logout và back-channel logout.
4. Mô tả SAML Single Logout với LogoutRequest, LogoutResponse, SessionIndex và các binding liên quan.
5. Ràng buộc logout event với đúng issuer, subject, session và client; chống giả mạo, replay và logout nhầm người.
6. Phân biệt thu hồi browser session, refresh token, access token và credential xác thực.
7. Thiết kế logout idempotent, có timeout, retry, audit và xử lý partial failure trong hệ thống phân tán.
8. Kiểm thử logout từ nhiều RP, browser privacy restrictions, IdP outage, token còn hiệu lực và các cuộc tấn công logout CSRF/DoS.

## 1. Federated logout là gì?

**Federated logout (đăng xuất liên kết)** là quá trình phối hợp kết thúc hoặc vô hiệu hóa các phiên liên quan trong một hệ thống identity federation, thường gồm phiên tại ứng dụng hiện tại, phiên tại Identity Provider (IdP) và các phiên tại những ứng dụng khác đã tin cậy IdP.

Trong SSO, người dùng có thể đăng nhập một lần tại IdP rồi truy cập nhiều ứng dụng. Mỗi ứng dụng thường tạo một **local session** riêng sau khi xác minh kết quả đăng nhập. IdP cũng duy trì phiên của riêng mình. Vì vậy, hệ thống có nhiều trạng thái phiên cùng đại diện cho một người dùng nhưng nằm ở các thành phần khác nhau.

Ví dụ, một nhân viên đã đăng nhập vào Learning Portal (RP A), Staff Console (RP B), Support Desk (RP C) và IdP của tổ chức. Khi người dùng chọn logout ở Learning Portal, ứng dụng có thể kết thúc phiên local của chính nó. Nhưng Staff Console, Support Desk và phiên IdP có thể vẫn còn hiệu lực. Nếu người dùng muốn đăng xuất khỏi toàn bộ hệ sinh thái, cần một cơ chế phối hợp logout được các thành phần hỗ trợ.

### Các khái niệm cần phân biệt

| Khái niệm | Phạm vi | Kết quả |
| --- | --- | --- |
| **Local logout** | Một ứng dụng/RP/SP. | Kết thúc phiên cục bộ của ứng dụng đó. |
| **IdP logout** | Phiên tại Identity Provider. | Kết thúc phiên IdP; không mặc nhiên xóa mọi local session. |
| **RP/SP logout** | Một relying party hoặc service provider. | Kết thúc phiên ứng dụng và có thể gửi yêu cầu tới IdP. |
| **Federated logout** | Nhiều bên trong federation. | Phối hợp kết thúc các phiên liên quan theo giao thức và khả năng của từng bên. |
| **Single Logout (SLO)** | Cơ chế/giao thức logout liên kết. | Cố gắng thông báo và kết thúc các phiên liên quan; kết quả phụ thuộc triển khai. |
| **Token revocation** | Một token hoặc họ token. | Làm token không còn được chấp nhận theo cơ chế thu hồi của authorization server/resource server. |

**Logout không đồng nghĩa thu hồi mọi credential.** Kết thúc session không tự xóa mật khẩu, passkey hoặc chứng chỉ của người dùng. Thu hồi access token/refresh token cũng là một thao tác riêng, phụ thuộc authorization server và cách resource server kiểm tra trạng thái.

## 2. Vì sao SSO tạo ra bài toán logout?

SSO tập trung xác thực, nhưng không nhất thiết tập trung toàn bộ trạng thái phiên. Mỗi ứng dụng có thể có cookie, session store, timeout và chính sách riêng.

~~~mermaid
flowchart TD
    U["Người dùng đăng nhập"] --> I["Identity Provider"]
    I --> A["RP A: local session A"]
    I --> B["RP B: local session B"]
    I --> C["RP C: local session C"]
    I --> S["IdP session"]
    A --> X["Logout tại RP A"]
    X --> XA["Kết thúc session A"]
    X -. "Nếu SLO được cấu hình" .-> I
    I -. "Logout event" .-> B
    I -. "Logout event" .-> C
    I -. "Kết thúc phiên IdP" .-> S
~~~

Khi RP A xóa cookie của nó, RP B không tự biết điều đó. Browser cũng không thể xóa cookie thuộc domain của RP B. Chỉ IdP hoặc cơ chế federation có thể gửi thông báo phù hợp tới các RP khác, và mỗi RP phải xác minh thông báo rồi tự vô hiệu hóa phiên của mình.

### Vì sao không thể coi SLO là một thao tác nguyên tử?

Các thành phần có thể đang offline hoặc timeout, không hỗ trợ cùng một logout profile, có session store hoặc cache khác nhau, không nhận được browser callback do cookie policy, hoặc còn access token hiệu lực độc lập với browser session. Một subject cũng có thể có nhiều session trên nhiều thiết bị.

Do đó, logout liên kết thường là một quy trình phân tán có thể thành công một phần. Hệ thống cần định nghĩa rõ điều gì đã được kết thúc, điều gì đang chờ và điều gì cần retry.

## 3. Mô hình trạng thái và phạm vi logout

Trước khi thiết kế giao thức, cần xác định đối tượng mà logout phải kết thúc.

| Đối tượng | Định danh thường dùng | Cách vô hiệu hóa |
| --- | --- | --- |
| Local application session | Session ID hoặc server-side session reference | Đánh dấu revoked/invalid trong session store, xóa cookie. |
| IdP session | IdP session reference; có thể được biểu diễn qua sid/session index | IdP kết thúc session theo chính sách. |
| RP session tại ứng dụng khác | Issuer + subject và/hoặc session identifier | RP nhận logout event, tìm session tương ứng và revoke. |
| Refresh token | Token reference hoặc token family | Authorization server revoke token/family. |
| Access token | Token reference/jti hoặc trạng thái introspection | Resource server từ chối theo revocation/introspection/denylist nếu hỗ trợ. |
| Device/workload credential | Credential ID hoặc key/certificate reference | Quy trình quản lý credential riêng; logout không tự revoke credential. |

### Logout một phiên hay mọi phiên?

Một subject có thể đăng nhập trên laptop, điện thoại và máy tính phòng lab. Logout một session không nên vô tình đăng xuất mọi thiết bị nếu người dùng chỉ yêu cầu kết thúc phiên hiện tại.

- **Current session:** chỉ kết thúc phiên ứng dụng hiện tại.
- **Current IdP session:** kết thúc phiên IdP tương ứng và thông báo tới các RP gắn với phiên đó.
- **All sessions for subject:** kết thúc mọi phiên của subject trên các ứng dụng/thiết bị, thường dùng trong sự cố hoặc thao tác bảo mật.
- **Credential compromise response:** thu hồi cả session, refresh token và credential bị lộ theo quy trình riêng.

Phải biết giao thức chỉ cung cấp session identifier hay subject-level logout. Nếu chỉ có subject, RP cần cẩn thận để không thu hồi mọi phiên của người dùng ngoài phạm vi yêu cầu.

## 4. OIDC RP-Initiated Logout

OpenID Connect RP-Initiated Logout cho phép một RP yêu cầu OP kết thúc phiên đăng nhập của người dùng tại OP. RP thường chuyển browser tới end_session_endpoint được công bố trong discovery metadata.

Các tham số thường gặp:

- **id_token_hint:** ID token đã được phát hành cho RP, giúp OP xác định phiên/người dùng liên quan.
- **post_logout_redirect_uri:** URI mà OP có thể chuyển browser về sau logout; phải được đăng ký/cho phép theo policy của OP.
- **state:** giá trị RP dùng để ràng buộc response sau logout với request do chính RP khởi tạo.

Ví dụ minh họa URL:

~~~text
GET https://id.example.org/logout
    ?id_token_hint=<id-token>
    &post_logout_redirect_uri=https%3A%2F%2Fapp.example.org%2Flogout%2Fcomplete
    &state=<random-state>
~~~

Đây là ví dụ khái niệm; tên endpoint và tham số cần tuân theo metadata/profile của OP. Không tự ghép URL logout từ input tùy ý.

### Luồng RP-Initiated Logout

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant B as Browser
    participant RP as Relying Party
    participant OP as OpenID Provider
    U->>B: Chọn Logout
    B->>RP: POST /logout
    RP->>RP: Revoke local session và xóa cookie
    RP->>RP: Tạo state logout
    RP-->>B: Redirect tới end_session_endpoint
    B->>OP: Logout request + id_token_hint + state
    OP->>OP: Xác định và kết thúc phiên IdP theo policy
    OP-->>B: Redirect về post_logout_redirect_uri
    B->>RP: GET /logout/complete?state=...
    RP->>RP: Kiểm tra state và hiển thị kết quả
    RP-->>B: Trang đã đăng xuất
~~~

### Thứ tự xử lý local và remote logout

Một ứng dụng nên vô hiệu hóa local session ngay khi nhận yêu cầu logout hợp lệ. Nếu chỉ chuyển browser tới IdP trước rồi chờ quay lại mới xóa session, người dùng có thể vẫn dùng phiên local nếu redirect thất bại hoặc bị bỏ dở.

Sau khi kết thúc local session, RP có thể điều hướng browser tới OP. Nếu OP không khả dụng, local logout vẫn phải hoàn tất và ứng dụng nên giải thích rằng phiên ở các ứng dụng khác có thể chưa được kết thúc.

### Kiểm tra post-logout redirect

- Chỉ cho phép URI đã đăng ký hoặc được policy OP chấp nhận.
- Không dùng URL do request tự do cung cấp.
- Kiểm tra state để tránh ghép nhầm callback.
- Không đưa secret hoặc token vào redirect URI.
- Trang logout completion không nên tự đăng nhập lại hoặc khởi tạo flow ngoài ý muốn.

id_token_hint là dữ liệu nhạy cảm. Không ghi nó vào access log, analytics, referrer hoặc URL log. Dùng TLS và cấu hình logging redaction.

## 5. OIDC Front-Channel Logout

Front-channel logout sử dụng browser làm kênh chuyển thông báo từ OP tới các RP. OP có thể tải các logout URI của RP trong browser, thường thông qua iframe hoặc navigation theo profile.

Mỗi RP nhận thông báo và tìm session liên quan để kết thúc.

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant B as Browser
    participant OP as OpenID Provider
    participant A as RP A
    participant C as RP C
    U->>B: Logout tại OP
    B->>OP: Kết thúc phiên IdP
    OP->>B: Trang logout với các RP logout URI
    B->>A: Front-channel logout request
    B->>C: Front-channel logout request
    A->>A: Xác minh logout context và revoke session liên quan
    C->>C: Xác minh logout context và revoke session liên quan
    A-->>B: Kết quả xử lý
    C-->>B: Kết quả xử lý
~~~

### Ưu điểm và giới hạn

Front-channel có thể tương thích với hệ sinh thái web đã hỗ trợ profile, nhưng phụ thuộc browser còn mở, mạng, iframe/navigation và chính sách cookie. Third-party cookie restrictions có thể làm việc dựa vào iframe hoặc cookie không hoạt động như kỳ vọng. Một RP không mở được trang hoặc không xử lý kịp có thể bỏ lỡ thông báo.

Front-channel logout không nên được coi là bảo đảm mọi RP nhận được event. Không nên nhận request chỉ vì nó đến từ URL logout; cần xác minh theo đặc tả/profile và thiết kế chống logout CSRF/DoS.

### Ràng buộc phiên

OIDC Front-Channel Logout có thể dùng issuer và sid trong logout request theo profile. RP cần kiểm tra issuer đúng OP đã tin cậy và chỉ kết thúc phiên tương ứng. Nếu không có sid, cách ánh xạ có thể rộng hơn và cần policy rõ ràng.

## 6. OIDC Back-Channel Logout

Back-channel logout cho phép OP gửi logout notification trực tiếp tới RP qua kênh server-to-server. Browser không cần tham gia vào việc truyền thông báo này.

OP gửi một **Logout Token** tới back-channel logout URI đã đăng ký của RP. Logout Token là JWT có các claim và sự kiện theo OIDC Back-Channel Logout specification.

Các kiểm tra quan trọng gồm:

- Chữ ký hợp lệ theo khóa của issuer đã tin cậy.
- iss đúng OP.
- aud chứa client ID của RP nhận thông báo.
- iat hợp lệ theo policy thời gian.
- jti có thể dùng để phát hiện replay.
- Claim events có URI sự kiện back-channel logout theo đặc tả.
- Có sid và/hoặc sub theo quy tắc của profile.
- Không có nonce trong Logout Token theo đặc tả.
- Token được gửi tới đúng back-channel endpoint đã đăng ký.

Ví dụ payload rút gọn:

~~~json
{
  "iss": "https://id.example.org",
  "aud": "learning-portal-client",
  "iat": 1795334400,
  "jti": "logout-event-unique-id",
  "events": {
    "http://schemas.openid.net/event/backchannel-logout": {}
  },
  "sid": "op-session-reference",
  "sub": "learner-42"
}
~~~

### Luồng Back-Channel Logout

~~~mermaid
sequenceDiagram
    autonumber
    participant OP as OpenID Provider
    participant RP as Relying Party
    participant DB as Session Store
    OP->>OP: Người dùng kết thúc phiên IdP
    OP->>RP: POST Logout Token tới back-channel URI
    RP->>RP: Xác minh chữ ký, iss, aud, iat, events
    RP->>RP: Kiểm tra jti và session binding
    RP->>DB: Revoke session theo sid/sub trong phạm vi policy
    DB-->>RP: Kết quả cập nhật
    RP-->>OP: HTTP success sau khi xử lý
~~~

### Vì sao back-channel hữu ích?

- Không phụ thuộc browser còn mở hay không.
- Không phụ thuộc third-party cookie để chuyển thông báo.
- OP có thể thông báo trực tiếp tới backend của RP.
- RP có thể revoke server-side session ngay cả khi browser không hoạt động.

### Các rủi ro cần kiểm soát

- Không chấp nhận Logout Token chỉ vì nó decode được.
- Không bỏ qua audience hoặc issuer.
- Không cho phép một token từ tenant khác kết thúc session.
- Dùng replay cache cho jti trong cửa sổ phù hợp.
- Ánh xạ sid/sub đúng với session đã lưu; không thu hồi rộng hơn policy.
- Bảo vệ endpoint khỏi request flood và giới hạn payload.
- Thiết kế xử lý lặp an toàn vì OP có thể retry khi không nhận được response.

Back-channel logout là thông báo cần xác minh, không phải một lệnh tin cậy tuyệt đối chỉ vì endpoint được gọi server-to-server.

## 7. So sánh front-channel và back-channel logout

| Tiêu chí | Front-channel | Back-channel |
| --- | --- | --- |
| Kênh truyền | Browser điều phối request tới RP. | OP gọi trực tiếp RP qua server-to-server. |
| Phụ thuộc browser | Có. | Không phụ thuộc browser để truyền event. |
| Third-party cookie | Có thể bị ảnh hưởng nếu triển khai dựa vào iframe/cookie. | Không cần third-party cookie cho notification. |
| Độ tin cậy giao nhận | Có thể bị gián đoạn bởi browser, tab, mạng hoặc privacy controls. | Có thể dùng retry, timeout và server-side monitoring. |
| Xác minh | RP phải xác minh request theo front-channel profile. | RP xác minh Logout Token và ràng buộc issuer/audience/session. |
| Phù hợp | Hệ thống web có hỗ trợ front-channel và cần tương thích. | Backend có endpoint ổn định và cần logout notification đáng tin cậy hơn. |
| Giới hạn | Không bảo đảm mọi RP nhận được thông báo. | Cần quản lý endpoint, retry, key validation và khả năng sẵn sàng. |

Hai cơ chế có thể được hỗ trợ song song tùy kiến trúc. Cần bảo đảm xử lý idempotent để cùng một session nhận cả hai loại notification vẫn chỉ được revoke an toàn một lần.

## 8. SAML Single Logout

SAML 2.0 định nghĩa Single Logout Protocol để các thành phần trong federation trao đổi thông điệp logout.

Các thành phần chính:

- **LogoutRequest:** yêu cầu một bên kết thúc phiên liên quan.
- **LogoutResponse:** phản hồi kết quả xử lý LogoutRequest.
- **NameID:** định danh subject theo federation contract.
- **SessionIndex:** tham chiếu tới phiên cụ thể của subject tại một bên.
- **Issuer:** bên phát hành thông điệp.
- **Destination:** endpoint nhận thông điệp.
- **RelayState:** dữ liệu trạng thái đi kèm binding; cần được kiểm soát, không tin như redirect URL tùy ý.

### Luồng SAML SLO khái quát

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant B as Browser
    participant SP as Service Provider
    participant IdP as Identity Provider
    participant Other as SP khác
    U->>B: Chọn logout tại SP
    B->>SP: Logout request
    SP->>SP: Kết thúc local session hoặc bắt đầu SLO
    SP-->>B: Redirect/POST LogoutRequest tới IdP
    B->>IdP: LogoutRequest với NameID/SessionIndex
    IdP->>IdP: Xác minh request và kết thúc phiên IdP
    IdP-->>Other: LogoutRequest tới SP khác theo cấu hình
    Other->>Other: Kết thúc session phù hợp
    Other-->>IdP: LogoutResponse
    IdP-->>B: LogoutResponse cho SP khởi tạo
    B->>SP: Chuyển kết quả về SP
    SP->>SP: Xác minh response và correlation
~~~

SAML SLO có thể sử dụng các binding như HTTP-Redirect, HTTP-POST hoặc SOAP tùy triển khai. Mỗi bên phải cấu hình metadata và endpoint tương ứng.

### Kiểm tra SAML LogoutRequest/LogoutResponse

- Xác minh chữ ký theo policy và metadata tin cậy.
- Kiểm tra issuer, destination và endpoint phù hợp.
- Kiểm tra request ID và InResponseTo để ràng buộc response với request.
- Kiểm tra NameID và SessionIndex để xác định đúng phiên.
- Chống replay thông điệp theo ID và cửa sổ thời gian.
- Xác minh RelayState theo cấu hình và không chuyển hướng tới URL tùy ý.
- Xử lý status trong LogoutResponse và ghi nhận kết quả từng bên.

Không tin một XML message chỉ vì parser đọc được. Dùng thư viện SAML đã được kiểm chứng và bảo vệ khỏi XML Signature Wrapping, XML External Entity (XXE) cùng các lỗi xử lý XML.

## 9. Logout session, access token và refresh token

Một hệ thống thường có nhiều loại credential truy cập. Logout browser session không tự động làm mọi token đã phát hành mất hiệu lực.

| Thành phần | Điều xảy ra khi local logout | Việc cần làm thêm |
| --- | --- | --- |
| Session cookie | Xóa/hết hạn cookie trên browser. | Revoke session server-side để cookie đã sao chép không còn dùng được. |
| IdP session | Có thể còn hoạt động. | Gọi RP-initiated logout hoặc cơ chế IdP logout nếu muốn kết thúc. |
| Local session ở RP khác | Thường vẫn hoạt động. | SLO notification và xử lý ở từng RP. |
| Refresh token | Có thể vẫn còn hiệu lực. | Revoke token/family theo authorization server nếu policy yêu cầu. |
| Access token JWT | Có thể vẫn được xác minh cục bộ đến khi exp. | Introspection, denylist, token version hoặc TTL ngắn nếu cần thu hồi sớm. |
| API key / passkey / certificate | Không bị xóa bởi logout. | Dùng quy trình quản lý/revoke credential riêng nếu bị lộ hoặc không còn được phép. |

### Token revocation

OAuth Token Revocation (RFC 7009) cho phép client gửi token tới revocation endpoint của authorization server để yêu cầu thu hồi. Việc thu hồi refresh token và access token phụ thuộc hỗ trợ của authorization server và cách resource server kiểm tra token.

Với JWT access token được resource server xác minh cục bộ, việc gọi revocation endpoint không nhất thiết làm token lập tức bị từ chối nếu resource server không kiểm tra trạng thái. Cần hiểu rõ cơ chế của hệ thống trước khi hứa rằng logout đã thu hồi mọi access token.

### Khi nào cần revoke refresh token?

- Người dùng chủ động chọn logout khỏi thiết bị hoặc ứng dụng.
- Tài khoản bị khóa hoặc offboard.
- Credential hoặc thiết bị bị nghi ngờ compromise.
- Người dùng đổi mật khẩu hoặc thay authenticator theo policy.
- Quản trị viên thu hồi phiên do incident.

Phạm vi revoke có thể là token hiện tại, token family, client grant hoặc mọi refresh token của subject. Chọn phạm vi đúng để tránh giữ lại quyền attacker nhưng cũng không vô tình đăng xuất mọi thiết bị khi người dùng chỉ kết thúc một phiên.

## 10. Quy trình logout an toàn ở một RP

Một RP nên có quy trình local logout rõ ràng trước khi phối hợp liên kết.

### Các bước đề xuất

1. Nhận logout request bằng phương thức và cơ chế chống CSRF phù hợp.
2. Xác định local session từ cookie đã được server xác minh.
3. Đánh dấu session revoked/invalid trong session store.
4. Thu hồi refresh token hoặc token reference liên quan nếu policy yêu cầu.
5. Hết hạn cookie bằng đúng tên, Path và Domain/host scope đã dùng.
6. Xóa dữ liệu session nhạy cảm khỏi cache phía server.
7. Ghi audit event với session reference đã che/hash, không ghi cookie hoặc token nguyên vẹn.
8. Nếu người dùng chọn federated logout, bắt đầu RP-initiated logout hoặc xử lý SLO theo protocol.
9. Trả kết quả phù hợp, nêu rõ phạm vi logout nếu các bên khác chưa xác nhận.

### Logout phải idempotent

Người dùng có thể bấm logout hai lần, browser gửi lại request hoặc IdP retry notification. Gọi logout nhiều lần phải an toàn:

- Revoke một session đã revoked vẫn trả kết quả hợp lệ.
- Logout Token đã xử lý được nhận diện qua jti/replay store.
- Không tạo session mới khi đang xử lý callback logout.
- Không thu hồi nhầm các session khác do tìm kiếm subject quá rộng.
- Retry không làm lặp side effect như gửi thông báo quá nhiều lần.

### Không dựa vào browser để revoke session

Xóa cookie ở browser chỉ xóa bản cookie của browser đó. Attacker có thể đã sao chép cookie. Server phải vô hiệu hóa session reference trong session store và mọi node phải nhìn thấy trạng thái revoke theo yêu cầu nhất quán.

## 11. Logout CSRF, giả mạo và replay

Logout thường ít được chú ý hơn login, nhưng vẫn có thể bị lạm dụng.

### 11.1 Logout CSRF

Attacker có thể khiến browser của nạn nhân gửi request logout tới ứng dụng. Hậu quả thường là người dùng bị đăng xuất ngoài ý muốn, gây gián đoạn hoặc hỗ trợ một chuỗi tấn công khác.

Biện pháp:

- Dùng POST cho thao tác thay đổi trạng thái.
- Áp CSRF token hoặc cơ chế xác minh origin phù hợp.
- Cấu hình SameSite cookie hợp lý.
- Không thực hiện logout chỉ bằng một GET có thể bị kích hoạt từ website khác, nếu thiết kế có thể tránh.
- Với callback logout theo giao thức, xác minh đúng thông điệp và ràng buộc session theo protocol thay vì áp dụng máy móc CSRF token của form local.

### 11.2 Forged logout notification

Attacker có thể gửi request tới back-channel hoặc front-channel endpoint để cố đăng xuất người dùng.

Biện pháp:

- Xác minh chữ ký và issuer của Logout Token.
- Kiểm tra audience là đúng RP.
- Kiểm tra event claim theo OIDC Back-Channel Logout.
- Kiểm tra sid/sub và ánh xạ session.
- Kiểm tra jti, thời gian và replay.
- Với SAML, xác minh chữ ký, issuer, destination, request correlation và session index.
- Giới hạn rate, payload và log an toàn.

### 11.3 Replay logout message

Nếu một logout message cũ được gửi lại, RP không nên xử lý như một event mới không giới hạn. Lưu ID đã xử lý trong replay cache với TTL phù hợp; xử lý lặp theo nguyên tắc idempotent.

Không từ chối mọi retry hợp lệ một cách mù quáng nếu OP đang thử giao lại do timeout. Có thể trả success cho event đã xử lý mà không lặp side effect.

## 12. Partial failure và khả năng phục hồi

Federated logout là quy trình phân tán. Một RP có thể kết thúc local session trong khi RP khác chưa nhận được thông báo. IdP có thể timeout sau khi một số RP đã xử lý xong.

### Những trạng thái nên phân biệt

- **Local logout complete:** phiên của ứng dụng hiện tại đã bị revoke.
- **IdP logout requested:** RP đã gửi yêu cầu kết thúc phiên IdP.
- **IdP logout confirmed:** OP đã trả kết quả theo protocol.
- **RP notification pending:** còn RP chưa xác nhận hoặc chưa nhận event.
- **Federation logout partial:** một số phiên đã kết thúc, một số chưa xác định.
- **Federation logout complete:** các bên bắt buộc theo policy đã xác nhận hoặc đã được xử lý theo cơ chế timeout/revocation đã định nghĩa.

Không nên hiển thị “đã đăng xuất khỏi tất cả ứng dụng” nếu chỉ local session đã bị xóa.

### Retry và timeout

- Dùng timeout cho outbound request và callback.
- Retry có backoff, jitter và giới hạn số lần.
- Dùng event ID/idempotency key để không xử lý side effect lặp.
- Có dead-letter hoặc reconciliation job cho notification thất bại.
- Theo dõi RP endpoint nào đang lỗi và thời điểm event được gửi.
- Có thời hạn tối đa cho trạng thái pending.
- Không giữ browser request vô thời hạn để chờ mọi RP.

### Chính sách khi IdP không khả dụng

Nếu người dùng bấm logout nhưng IdP đang lỗi:

1. Kết thúc local session ngay.
2. Xóa cookie local.
3. Thu hồi refresh token local theo khả năng.
4. Thông báo rằng logout khỏi IdP/ứng dụng khác chưa xác nhận nếu điều đó quan trọng.
5. Lưu công việc retry ở server nếu có cơ chế an toàn.
6. Không giữ người dùng trong trạng thái còn đăng nhập local chỉ vì OP không phản hồi.

Đối với tài khoản bị compromise, quản trị viên có thể cần revoke local sessions khẩn cấp tại từng ứng dụng hoặc qua một cơ chế tập trung độc lập với browser.

## 13. Bảo vệ session và callback trong logout

Logout endpoint và callback cần được thiết kế như các endpoint bảo mật.

### Bảo vệ callback

- Chỉ nhận callback tại URI đã đăng ký.
- Kiểm tra state hoặc correlation theo giao thức.
- Kiểm tra issuer và audience của logout message/token.
- Không nhận redirect destination tùy ý từ query string.
- Không tạo session authenticated từ callback logout.
- Không để logout callback vô hiệu hóa mọi session chỉ dựa trên subject nếu request yêu cầu session cụ thể.
- Không ghi raw token, cookie, Logout Token hoặc SAML Response vào log.

### Cookie sau logout

Ví dụ hết hạn cookie:

~~~http
Set-Cookie: __Host-session=; Path=/; Max-Age=0; Secure; HttpOnly; SameSite=Lax
~~~

Tên cookie và thuộc tính phải khớp với cookie đã được phát hành. Với __Host- cookie, phải giữ điều kiện Secure, Path=/ và không có Domain. Việc xóa cookie không thay thế revoke server-side.

### Chống session fixation khi đăng nhập lại

Sau logout, browser có thể giữ một cookie hết hạn hoặc bắt đầu một session anonymous mới. Khi người dùng đăng nhập lại, RP vẫn phải xoay session ID tại ranh giới xác thực. Không tái sử dụng session ID cũ hoặc session reference đã revoke.

## 14. Audit, giám sát và quyền riêng tư

Logout event là dữ liệu quan trọng cho điều tra và vận hành.

### Audit fields hữu ích

- Event ID và loại logout (local, RP-initiated, front-channel, back-channel, SAML SLO).
- Issuer/tenant và client/RP nhận event.
- Subject reference đã bảo vệ hoặc pseudonymized.
- Session reference hoặc sid đã che/hash theo policy.
- Thời điểm nhận, xác minh và hoàn tất.
- Kết quả validation và status xử lý.
- Số lần retry, timeout và bên còn pending.
- Policy version và correlation ID.

### Không ghi các dữ liệu sau ở dạng rõ

- Session cookie.
- ID token hoặc access token.
- Refresh token.
- Logout Token.
- SAML assertion/response chứa thuộc tính cá nhân.
- Private key, client secret hoặc dữ liệu xác thực.

### Chỉ số vận hành

- Tỷ lệ local logout thành công.
- Tỷ lệ OP logout request thành công.
- Tỷ lệ front-channel/back-channel notification được xử lý.
- Thời gian từ IdP logout tới khi RP revoke session.
- Số event replay/invalid signature/issuer mismatch.
- Số session còn active sau logout theo SLA.
- Tỷ lệ partial logout và retry exhaustion.

Giám sát giúp phát hiện RP không xử lý logout, endpoint lỗi hoặc key rotation sai. Nhưng log và metric phải tránh làm lộ subject/session identifier.

## 15. Ví dụ thực tế: nền tảng học tập dùng OIDC

Một tổ chức có Learning Portal, Staff Console và Support Desk cùng tin cậy một IdP.

### Người học logout khỏi Learning Portal

1. Người học bấm Logout.
2. Portal xác minh request và revoke local session.
3. Portal hết hạn cookie session.
4. Portal gửi browser tới OP end_session_endpoint với id_token_hint, post_logout_redirect_uri và state theo cấu hình.
5. OP kết thúc phiên IdP nếu policy chấp nhận.
6. OP phát back-channel logout notification tới Staff Console và Support Desk nếu chúng đăng ký endpoint.
7. Mỗi RP xác minh Logout Token, kiểm tra issuer/audience/event/jti và tìm session theo sid/sub.
8. Mỗi RP revoke local session tương ứng và phản hồi thành công.
9. Portal xác minh state ở post-logout callback và hiển thị kết quả phù hợp.

### Staff Console không nhận được notification

Nếu Staff Console timeout, OP hoặc hệ thống điều phối có thể retry theo policy. Portal vẫn đã kết thúc local session của người học. UI không nên khẳng định toàn bộ federation đã logout nếu trạng thái của Staff Console chưa xác định.

Nếu tổ chức yêu cầu thu hồi ngay do incident, quản trị viên có thể dùng session revocation API hoặc cơ chế nội bộ để kết thúc các session còn lại; không phụ thuộc vào browser front-channel.

### Access token còn hiệu lực

Một access token JWT đã phát hành có thể còn được API chấp nhận tới khi hết hạn nếu API chỉ xác minh chữ ký cục bộ. Nếu yêu cầu thu hồi nhanh, kiến trúc cần introspection, denylist, token version hoặc TTL ngắn phù hợp. Logout browser session không tự làm JWT biến mất khỏi thiết bị đã sao chép.

## 16. Kiểm thử federated logout

| Kịch bản | Cách kiểm tra | Kết quả mong đợi |
| --- | --- | --- |
| Local logout | Logout tại RP A rồi dùng cookie cũ gọi API A. | Session A bị từ chối ở server. |
| RP-initiated logout | Kiểm tra redirect tới endpoint OP và state callback. | OP nhận đúng request; RP xác minh state. |
| Redirect URI không đăng ký | Thay post-logout redirect URI thành host attacker. | OP từ chối hoặc không redirect tới đích không được phép. |
| Front-channel notification | OP gửi logout event tới RP. | RP xác minh và revoke đúng session theo profile. |
| Third-party cookie bị chặn | Chạy trong browser privacy mode. | Hệ thống không giả định front-channel luôn giao nhận thành công; trạng thái được xử lý theo fallback. |
| Back-channel token hợp lệ | Gửi Logout Token đúng chữ ký, issuer, audience và event. | RP revoke session phù hợp và trả success. |
| Back-channel token sai issuer | Dùng token từ issuer khác. | RP từ chối, không revoke session. |
| Back-channel token sai audience | Dùng token dành cho client khác. | RP từ chối. |
| Logout Token thiếu event claim | Bỏ claim back-channel logout event. | RP từ chối theo đặc tả. |
| Logout Token có nonce | Thêm nonce không hợp lệ theo đặc tả. | RP từ chối. |
| Logout Token replay | Gửi lại cùng jti. | Event thứ hai được nhận diện; không lặp side effect. |
| sid cụ thể | Gửi event có sid gắn một phiên. | Chỉ session tương ứng bị revoke. |
| sub không có sid | Gửi event subject-level theo policy. | RP xử lý phạm vi subject đã được quy định, không thu hồi nhầm tenant. |
| SAML LogoutRequest hợp lệ | Gửi request đã ký với NameID/SessionIndex phù hợp. | SP/IdP kết thúc session liên quan. |
| SAML InResponseTo sai | Trả LogoutResponse không khớp request. | Bên khởi tạo từ chối response. |
| SAML signature sai | Sửa XML sau khi ký. | Thông điệp bị từ chối. |
| Logout CSRF | Site ngoài kích hoạt request logout local. | CSRF/origin controls ngăn request không hợp lệ theo thiết kế. |
| IdP outage | OP timeout trong lúc logout. | Local session vẫn bị revoke; UI phản ánh remote status chưa xác nhận. |
| RP outage | Một RP không phản hồi back-channel event. | Timeout/retry được áp dụng; trạng thái partial được theo dõi. |
| Token còn hiệu lực | Dùng access token đã cấp sau local logout. | Kết quả đúng theo revocation design; không giả định token tự mất hiệu lực. |
| Logout lặp | Gửi logout nhiều lần. | Xử lý idempotent, không tạo lỗi hoặc revoke nhầm session khác. |
| Concurrent sessions | Một subject có hai thiết bị/session. | Logout current-session chỉ kết thúc đúng phiên nếu policy yêu cầu. |

## 17. Checklist thiết kế và vận hành

- [ ] Đã xác định phạm vi logout: local, IdP, current session, all sessions hay credential compromise.
- [ ] Đã phân biệt session cookie, IdP session, local RP session, access token và refresh token.
- [ ] Local session được revoke server-side ngay khi logout hợp lệ.
- [ ] Cookie được hết hạn với đúng tên và thuộc tính đã phát hành.
- [ ] RP-initiated logout dùng endpoint/metadata OP đã tin cậy.
- [ ] post-logout redirect URI được allowlist; state được kiểm tra.
- [ ] Front-channel logout có kiểm tra issuer/session và xử lý browser privacy restrictions.
- [ ] Back-channel Logout Token được xác minh chữ ký, iss, aud, iat, jti, events và sid/sub.
- [ ] Logout notification được xử lý idempotent và có replay protection.
- [ ] SAML SLO xác minh signature, issuer, destination, request correlation, NameID và SessionIndex.
- [ ] Logout không thu hồi rộng hơn phạm vi session được yêu cầu.
- [ ] Refresh token được revoke theo policy; hiểu giới hạn thu hồi access token JWT.
- [ ] Có timeout, retry, backoff, monitoring và reconciliation cho partial failure.
- [ ] IdP outage không ngăn local logout.
- [ ] UI không tuyên bố global logout hoàn tất khi còn RP chưa xác nhận.
- [ ] Audit không ghi raw cookie, token, Logout Token hoặc SAML assertion.
- [ ] Có test logout CSRF, forged notification, replay, wrong audience, wrong issuer và concurrent sessions.
- [ ] Có quy trình incident để revoke sessions/credentials khi tài khoản hoặc IdP bị compromise.

## 18. Tự kiểm tra

**Câu 1.** Vì sao local logout ở một RP không tự kết thúc phiên tại các RP khác?

**Đáp án:** Mỗi RP thường duy trì local session và cookie riêng. Xóa cookie của RP A không tác động tới session store hoặc cookie của RP B. Cần SLO notification và từng RP phải xử lý.

**Câu 2.** Federated logout có đồng nghĩa thu hồi mọi access token không?

**Đáp án:** Không. Logout session, IdP session, refresh token và access token là các phạm vi riêng. Access token JWT có thể còn hiệu lực đến exp nếu resource server không kiểm tra trạng thái.

**Câu 3.** RP-Initiated Logout dùng id_token_hint để làm gì?

**Đáp án:** Giúp OP nhận diện phiên/người dùng liên quan tới RP logout request theo profile. Nó không thay thế state, redirect URI validation hoặc việc kết thúc local session.

**Câu 4.** Front-channel logout có hạn chế nào đáng chú ý?

**Đáp án:** Phụ thuộc browser và có thể bị ảnh hưởng bởi iframe, third-party cookie restrictions, tab đóng hoặc mạng gián đoạn. Không nên coi việc gửi notification qua browser là bảo đảm mọi RP đã logout.

**Câu 5.** Back-channel logout khác front-channel ở đâu?

**Đáp án:** OP gọi trực tiếp endpoint backend của RP bằng server-to-server request mang Logout Token. RP xác minh token và revoke session mà không cần browser chuyển tiếp.

**Câu 6.** Vì sao phải kiểm tra aud trong Logout Token?

**Đáp án:** Để bảo đảm token được phát cho đúng RP nhận notification. Token của client khác không được phép kết thúc session ở RP hiện tại.

**Câu 7.** sid và sub khác nhau thế nào trong logout?

**Đáp án:** sub xác định subject trong phạm vi issuer; sid xác định phiên IdP theo profile. sid có thể giúp revoke một session cụ thể, trong khi subject-level logout có phạm vi rộng hơn.

**Câu 8.** Nếu IdP không khả dụng khi người dùng logout, RP nên làm gì?

**Đáp án:** Revoke local session và xóa cookie ngay. Remote logout có thể được đánh dấu pending/retry; UI cần nói rõ phạm vi chưa xác nhận.

**Câu 9.** SAML SLO cần SessionIndex để làm gì?

**Đáp án:** SessionIndex giúp liên kết LogoutRequest với phiên cụ thể của subject tại bên federation, tránh kết thúc nhầm các phiên khác.

**Câu 10.** Vì sao logout notification phải idempotent?

**Đáp án:** Browser, OP hoặc mạng có thể gửi lại cùng event. Xử lý idempotent cho phép retry an toàn, tránh lặp side effect và không làm hỏng trạng thái phiên đã revoke.

## Ghi nhớ

**Federated logout** phối hợp kết thúc phiên tại RP/SP, IdP và các ứng dụng liên quan trong một hệ thống SSO. Mỗi ứng dụng thường có local session riêng, vì vậy local logout không tự đăng xuất các ứng dụng khác. OIDC hỗ trợ RP-initiated, front-channel và back-channel logout; SAML có Single Logout Protocol với LogoutRequest/LogoutResponse và session correlation.

Hãy revoke local session ở server ngay khi logout hợp lệ, xóa cookie đúng cách và xác minh mọi logout notification theo issuer, audience, chữ ký, thời hạn, event, session identifier và replay policy. Phân biệt session logout với refresh/access token revocation; thiết kế timeout, retry, idempotency và trạng thái partial khi một bên không phản hồi. **Chỉ tuyên bố đã đăng xuất toàn hệ sinh thái khi các phạm vi bắt buộc đã được xác nhận hoặc được xử lý theo chính sách đã công bố.**
