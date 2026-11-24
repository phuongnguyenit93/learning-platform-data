# Logout notification

## 1. Logout notification là gì?

**Logout notification** là thông điệp hoặc sự kiện cho biết một phiên đăng nhập cần được kết thúc tại một ứng dụng hoặc thành phần khác. Trong hệ thống Single Sign-On (SSO), người dùng có thể đăng nhập một lần tại Identity Provider (IdP) rồi truy cập nhiều Relying Party (RP). Khi người dùng đăng xuất tại IdP, các ứng dụng đã dựa vào phiên SSO đó cần được thông báo để kết thúc những session tương ứng.

Một logout notification có thể được chuyển qua browser (front-channel) hoặc gửi trực tiếp từ server tới server (back-channel). Nó giúp đồng bộ trạng thái đăng xuất giữa các thành phần, nhưng **bản thân thông báo không tự xóa session**. RP phải xác minh thông điệp, tìm đúng session, vô hiệu hóa session và xử lý token/credential liên quan theo policy.

Trong module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, logout notification kết nối authentication, session, token, federation và trust boundary. Đăng xuất an toàn cần hiểu session nào đang bị kết thúc, ai có quyền yêu cầu, thông điệp có xác thực không, cách chống replay và điều gì xảy ra khi thông báo bị trễ hoặc thất lạc.

Sau bài học, người học có thể:

- Phân biệt local logout, IdP logout, RP-initiated logout và global SSO logout.
- Giải thích front-channel và back-channel logout.
- Mô tả OIDC logout notification và xác minh Logout Token.
- Hiểu SAML Single Logout và các định danh session liên quan.
- Ánh xạ thông báo tới session của đúng issuer, subject và session ID.
- Thiết kế xử lý idempotent, replay protection, retry và audit.
- Phân biệt logout với token revocation và thông báo bảo mật cho người dùng.
- Kiểm thử session invalidation trên nhiều ứng dụng, thiết bị và browser.

## 2. Vì sao cần logout notification?

Một người dùng có thể đang có nhiều session:

- Session tại IdP sau khi đăng nhập.
- Session riêng tại ứng dụng A.
- Session riêng tại ứng dụng B.
- Session trên browser hoặc thiết bị khác.
- Access token và refresh token đã được cấp cho từng client.
- Session của API gateway hoặc backend service.

Nếu người dùng chỉ đăng xuất khỏi ứng dụng A, ứng dụng B và session tại IdP có thể vẫn hoạt động. Ngược lại, nếu người dùng đăng xuất khỏi IdP, các RP có thể vẫn giữ session nội bộ nếu không nhận và xử lý logout event.

Logout notification giúp một thành phần thông báo cho thành phần khác rằng một session hoặc tập session cần bị vô hiệu hóa. Ví dụ:

1. Người dùng đăng xuất khỏi IdP.
2. IdP kết thúc session SSO.
3. IdP gửi logout notification tới các RP liên quan.
4. Mỗi RP xác minh thông điệp và tìm session tương ứng.
5. RP vô hiệu hóa session, refresh credential và cache theo policy.
6. Những request tiếp theo từ session đã kết thúc bị từ chối.

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant OP as OpenID Provider
    participant A as RP / Ứng dụng A
    participant B as RP / Ứng dụng B
    U->>OP: Logout
    OP->>OP: Kết thúc session IdP
    OP-->>A: Logout notification
    OP-->>B: Logout notification
    A->>A: Xác minh và tìm session
    B->>B: Xác minh và tìm session
    A->>A: Vô hiệu hóa session liên quan
    B->>B: Vô hiệu hóa session liên quan
    A-->>OP: Kết quả nhận thông báo
    B-->>OP: Kết quả nhận thông báo
~~~

Đây là sơ đồ khái niệm. Giao thức cụ thể quy định cách gửi, phản hồi và xử lý thông điệp. Không phải mọi hệ thống SSO đều có global logout hoặc bảo đảm tất cả session kết thúc tức thời.

## 3. Phân biệt các kiểu logout

Các khái niệm logout thường bị dùng lẫn nhau:

| Kiểu | Ý nghĩa | Phạm vi |
| --- | --- | --- |
| **Local logout** | Người dùng đăng xuất khỏi một ứng dụng | Session của RP hiện tại |
| **RP-initiated logout** | RP yêu cầu IdP kết thúc hoặc thay đổi session SSO | Bắt đầu từ ứng dụng |
| **IdP-initiated logout** | IdP khởi tạo việc kết thúc các session RP liên quan | Bắt đầu từ IdP |
| **Front-channel logout** | IdP dùng browser để điều hướng/nhúng request tới RP | Qua user-agent |
| **Back-channel logout** | IdP gửi thông điệp trực tiếp tới endpoint backend của RP | Server-to-server |
| **Global/session-wide logout** | Kết thúc nhiều session liên quan tới một session IdP hoặc subject | Phụ thuộc khả năng giao thức và policy |
| **Token revocation** | Vô hiệu hóa token hoặc grant theo khả năng của AS | Token/grant, không nhất thiết xóa UI session |

Local logout không nhất thiết đăng xuất khỏi IdP. IdP logout cũng không bảo đảm mọi access token tự hết hiệu lực ngay. Cần thiết kế rõ phạm vi và hiển thị đúng cho người dùng.

### 3.1. RP-initiated logout

RP-initiated logout xảy ra khi người dùng chọn Sign out tại ứng dụng. RP có thể:

1. Vô hiệu hóa session local.
2. Xóa cookie/session state của ứng dụng.
3. Thu hồi refresh token hoặc grant nếu policy và endpoint hỗ trợ.
4. Chuyển browser tới end-session endpoint của IdP nếu cần kết thúc SSO session.
5. Nhận kết quả hoặc redirect trở lại URI đã đăng ký.

Trong OIDC, RP có thể sử dụng RP-Initiated Logout và end_session_endpoint được công bố trong metadata. Request có thể mang id_token_hint, post_logout_redirect_uri và state theo đặc tả. RP cần xác minh redirect đích đã đăng ký, đồng thời không coi redirect thành công là bằng chứng mọi session ở mọi ứng dụng đã bị hủy.

### 3.2. IdP-initiated logout

IdP có thể khởi tạo logout khi người dùng đăng xuất tập trung, quản trị viên vô hiệu hóa tài khoản, session bị thu hồi hoặc policy bảo mật yêu cầu. IdP gửi thông điệp tới các RP đã tham gia session tương ứng.

RP cần xác minh thông điệp đến từ issuer đáng tin cậy và chỉ vô hiệu hóa các session nằm trong phạm vi thông điệp. Không nhận một request logout ẩn danh rồi xóa session tùy ý dựa trên subject hoặc email do caller cung cấp.

### 3.3. Logout và đóng browser

Đóng tab hoặc browser không đồng nghĩa logout. Cookie có thể là persistent cookie, browser có thể khôi phục session, và server-side session vẫn còn hiệu lực. Nếu cần kết thúc phiên, người dùng nên thực hiện logout hoặc hệ thống cần có timeout/revocation policy.

## 4. Front-channel và back-channel notification

Hai cơ chế có cách phân phối và đặc tính khác nhau.

| Đặc điểm | Front-channel | Back-channel |
| --- | --- | --- |
| Kênh truyền | Browser/user-agent | Server-to-server |
| Cách phổ biến | Redirect, iframe hoặc browser navigation | HTTP POST tới logout endpoint |
| Phụ thuộc browser | Có | Ít phụ thuộc |
| Phụ thuộc third-party cookie | Có thể bị ảnh hưởng khi RP cần nhận diện session qua iframe | Không cần browser cookie để gửi notification |
| Khả năng quan sát | Có thể bị ảnh hưởng bởi tab đóng, script hoặc browser policy | Có thể retry và ghi nhận trạng thái ở server |
| Mức độ tin cậy | Cần kiểm tra request/context; browser là môi trường trung gian | Có thể xác minh token và kết nối server-to-server |
| Use case | Tương thích hệ thống cần browser propagation | Đồng bộ session backend đáng tin cậy |

### 4.1. Front-channel logout

Trong front-channel logout, IdP điều khiển browser truy cập logout URI của từng RP, thường qua iframe hoặc điều hướng theo profile. RP nhận request trong browser context và cố gắng kết thúc session tương ứng.

Ưu điểm là tận dụng browser để thông báo tới nhiều ứng dụng mà không cần IdP gọi trực tiếp backend của từng RP. Tuy nhiên, browser privacy controls, third-party cookie blocking, iframe restrictions, CSP, tab đóng hoặc mạng gián đoạn có thể làm notification không được xử lý như mong đợi.

Front-channel logout không nên là cơ chế duy nhất nếu hệ thống cần bảo đảm server-side session bị vô hiệu hóa. Khi cần độ tin cậy cao hơn, cân nhắc back-channel logout hoặc cơ chế session revocation bổ sung.

### 4.2. Back-channel logout

Trong back-channel logout, IdP gửi một thông điệp trực tiếp tới endpoint backend đã đăng ký của RP. Với OIDC Back-Channel Logout, thông điệp thường chứa Logout Token được ký dưới dạng JWT.

Ưu điểm:

- Không phụ thuộc browser đang mở.
- Không cần cookie third-party để server nhận thông báo.
- Có thể kiểm tra chữ ký, issuer, audience và session identifier.
- Có thể retry khi RP tạm thời không sẵn sàng.
- Dễ ghi nhận delivery result ở server.

RP vẫn cần bảo vệ endpoint, xác minh token, chống replay và xử lý idempotent. Back-channel không có nghĩa request tự động đáng tin chỉ vì tới từ một IP hoặc URL quen thuộc.

## 5. OIDC Back-Channel Logout Token

OIDC Back-Channel Logout dùng một Logout Token để báo cho RP rằng session hoặc subject cần được logout. Logout Token là JWT được ký bởi OP và gửi tới backchannel_logout_uri đã đăng ký.

Các claim cốt lõi theo đặc tả gồm:

- **iss:** issuer đã phát hành Logout Token.
- **aud:** client/RP là audience của thông điệp.
- **iat:** thời điểm token được phát hành.
- **jti:** định danh duy nhất của token để hỗ trợ phát hiện replay.
- **events:** chứa URI event back-channel logout với object rỗng theo profile.
- **sub:** subject bị logout, nếu thông điệp định danh theo subject.
- **sid:** session ID tại OP, nếu thông điệp định danh theo session.

Logout Token phải có thời hạn exp theo đặc tả; RP cần kiểm tra thời hạn và các điều kiện token khác. Logout Token không được chứa nonce. RP phải xác minh chữ ký và các claim theo OIDC Back-Channel Logout specification trước khi thực hiện hành động.

Ví dụ JWT payload minh họa:

~~~json
{
  "iss": "https://id.example.test",
  "aud": "portal-web",
  "iat": 1795323000,
  "exp": 1795323300,
  "jti": "logout-event-8a21",
  "events": {
    "http://schemas.openid.net/event/backchannel-logout": {}
  },
  "sub": "user-4821",
  "sid": "op-session-91f2"
}
~~~

Đây là ví dụ cấu trúc, không phải token có thể sử dụng. Các giá trị phải được tạo bởi OP và xác minh theo metadata, key và client registration thực tế.

### 5.1. Xác minh Logout Token

RP cần kiểm tra tối thiểu:

1. Chữ ký JWT hợp lệ theo khóa tin cậy của issuer.
2. Thuật toán nằm trong allowlist; không tin thuật toán do token tự chọn.
3. iss khớp chính xác issuer đã cấu hình.
4. aud chứa client ID của RP.
5. iat và exp hợp lệ theo policy, có xử lý clock skew giới hạn.
6. jti chưa được xử lý trước đó trong phạm vi replay cache.
7. events có chứa back-channel logout event theo đặc tả.
8. Token không chứa nonce.
9. Có sub hoặc sid theo yêu cầu của đặc tả.
10. Token không bị nhầm với ID token hoặc access token thông thường.

Không giải mã payload rồi tin claim trước khi xác minh chữ ký. Không tải JWKS từ URL do JWT header tự chỉ định; dùng JWKS URI gắn với issuer đã được tin cậy.

### 5.2. sub và sid khác nhau thế nào?

- **sub** định danh người dùng trong phạm vi issuer.
- **sid** định danh một session tại OP.

Nếu Logout Token chứa sid, RP có thể kết thúc các session local đã liên kết với session OP đó. Nếu chỉ có sub, policy/protocol cho phép RP kết thúc các session liên quan tới subject đó theo cách được định nghĩa. Cần tránh xóa nhầm mọi tài khoản hoặc session của cùng email ở issuer khác.

Một subject có thể có nhiều session trên các browser hoặc thiết bị. sid giúp phân biệt một phiên IdP cụ thể; sub giúp xác định chủ thể. RP nên lưu mapping session rõ ràng để thực thi đúng phạm vi.

### 5.3. Replay protection với jti

Một Logout Token hợp lệ có thể bị gửi lại do retry hoặc bị attacker replay nếu bị lộ. RP nên lưu jti đã xử lý trong replay cache với TTL phù hợp thời hạn token và clock skew.

Thao tác kiểm tra và ghi jti cần nguyên tử. Nếu hai request giống nhau tới đồng thời, chỉ một lần xử lý được coi là mới. Lần lặp tiếp theo nên được xử lý idempotent hoặc trả response an toàn mà không gây side effect bổ sung.

Không lưu jti vô thời hạn; TTL cần đủ để phát hiện replay trong cửa sổ token còn hợp lệ. Cache phân tán cần bảo đảm nhất quán đủ cho các instance RP.

## 6. Ánh xạ logout notification tới session local

RP phải biết session nào được tạo dựa trên issuer và session IdP nào. Nếu không lưu mapping, RP có thể nhận thông điệp hợp lệ nhưng không biết phải vô hiệu hóa session nào.

Một mô hình khái niệm:

~~~text
LocalSession
  local_session_id
  principal_id
  issuer
  federated_subject
  idp_sid
  created_at
  status
  expires_at
~~~

Khi xử lý logout token:
- Xác định issuer từ token đã xác minh.
- Nếu có sid, tìm session local gắn với issuer + sid.
- Nếu chỉ có sub, tìm session phù hợp với issuer + subject theo policy.
- Đánh dấu session revoked/terminated trong kho session.
- Thu hồi refresh token hoặc grant liên quan nếu policy hỗ trợ.
- Xóa hoặc vô hiệu hóa cache/session state trên các node.
- Ghi audit event với mã sự kiện và phạm vi đã xử lý.

Không tra cứu theo email hoặc display name. Email có thể thay đổi, trùng giữa issuer hoặc được tái cấp. Dùng định danh subject/session được giao thức xác định.

### 6.1. Nhiều session và nhiều thiết bị

Một người dùng có thể đăng nhập từ laptop, điện thoại và máy tính dùng chung. Logout notification chứa sid có thể chỉ áp dụng cho một session IdP; notification theo sub có thể có phạm vi rộng hơn theo protocol/policy.

Ứng dụng cần quyết định:
- Logout một browser hay mọi session của subject?
- Session nội bộ có liên kết một-một với sid hay một-nhiều?
- Session local có thể tiếp tục bằng credential riêng sau khi IdP logout không?
- Refresh token nào phải thu hồi?
- Có cần kết thúc session của mobile app hoặc API gateway không?

Không suy luận “logout toàn cầu” nếu thông điệp chỉ định một session cụ thể.

## 7. SAML Single Logout

Trong SAML 2.0, **Single Logout (SLO)** cho phép IdP và Service Provider (SP) trao đổi LogoutRequest/LogoutResponse để kết thúc session liên quan.

Một LogoutRequest có thể xác định subject bằng NameID và SessionIndex, cùng thông tin issuer, destination và thời gian theo profile. SP cần kiểm tra chữ ký, issuer, destination, thời hạn, request correlation và session mapping theo cấu hình.

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant SP as Service Provider
    participant IdP as Identity Provider
    U->>SP: Logout
    SP->>IdP: SAML LogoutRequest
    IdP->>IdP: Kết thúc session IdP
    IdP-->>SP: SAML LogoutRequest tới SP khác
    SP->>SP: Xác minh và kết thúc session local
    SP-->>IdP: LogoutResponse
    IdP-->>SP: Kết quả theo binding/profile
    SP-->>U: Hoàn tất logout theo trạng thái
~~~

SAML SLO có thể dùng HTTP-Redirect, HTTP-POST hoặc binding/profile được hỗ trợ. Thực tế interoperability phụ thuộc cấu hình IdP/SP; một số hệ thống chỉ hỗ trợ một phần SLO hoặc có hành vi khác nhau.

### 7.1. NameID và SessionIndex

NameID định danh subject trong ngữ cảnh SAML, còn SessionIndex giúp xác định session cụ thể tại IdP. Không dùng NameID đơn lẻ như một khóa toàn cục nếu thiếu issuer/partner context.

SP cần ánh xạ SessionIndex/NameID với session local theo metadata và policy. Nếu LogoutRequest không chỉ rõ session hoặc không thể xác định phạm vi an toàn, xử lý theo profile đã thống nhất và tránh kết thúc nhầm principal.

### 7.2. Kiểm tra SAML logout message

Một SP nên kiểm tra:
- Issuer đúng IdP đã cấu hình.
- Chữ ký XML hợp lệ theo trust metadata và canonicalization an toàn.
- Destination và recipient phù hợp endpoint.
- InResponseTo khớp request khi response cần correlation.
- NameID/SessionIndex ánh xạ đúng session.
- Thời hạn và replay policy.
- XML parser chống XXE, signature wrapping và các lỗi xử lý XML nguy hiểm.

Không tắt kiểm tra chữ ký chỉ để khắc phục lỗi SLO. Nếu metadata/certificate rollover gây lỗi, cần xử lý trust configuration và rotation đúng quy trình.

## 8. Logout notification và token revocation

Logout và revocation liên quan nhưng không đồng nghĩa.

| Cơ chế | Điều gì bị tác động | Giới hạn |
| --- | --- | --- |
| **Local session invalidation** | Session tại RP | Token độc lập có thể vẫn hợp lệ ở API khác |
| **Logout notification** | Thông báo RP kết thúc session liên quan | RP phải nhận, xác minh và xử lý |
| **Refresh token revocation** | Khả năng cấp access token mới từ refresh token | Access token đã phát hành có thể còn hiệu lực |
| **Access token revocation/introspection** | Trạng thái token theo AS/RS policy | JWT tự xác minh có thể vẫn được chấp nhận tới exp nếu RS không kiểm tra trạng thái |
| **Global account disable** | Trạng thái principal và quyền ở nhiều hệ thống | Cần propagation và enforcement tại từng hệ thống |

Một access token JWT đã phát hành có thể vẫn được RS chấp nhận tới khi hết hạn nếu RS chỉ kiểm tra chữ ký, issuer, audience và exp. Nếu cần thu hồi tức thời hơn, có thể dùng opaque token với introspection, denylist/token status, token lifetime ngắn hoặc cơ chế revocation event được đồng bộ.

Không hứa với người dùng rằng logout đã xóa mọi token ở mọi dịch vụ nếu kiến trúc không hỗ trợ điều đó. Thông báo trạng thái cần phản ánh đúng phạm vi: session local đã kết thúc, SSO logout đã được yêu cầu hay token grant đã bị thu hồi.

## 9. Delivery, retry và xử lý lỗi

Logout notification có thể thất bại do RP down, timeout, mạng lỗi, certificate/JWKS rollover hoặc endpoint cấu hình sai. Một thiết kế phân tán cần quy tắc delivery rõ ràng.

### 9.1. Idempotency

Xử lý cùng một logout event nhiều lần không được gây lỗi hoặc side effect nguy hiểm. RP nên:
- Nhận diện event bằng jti hoặc request ID theo protocol.
- Vô hiệu hóa session theo thao tác idempotent.
- Không tạo session mới hoặc thay đổi principal khi xử lý logout.
- Lưu trạng thái event đã xử lý với TTL.
- Ghi audit cho lần đầu và các lần lặp theo mức cần thiết.

Nếu session đã bị logout trước đó, notification hợp lệ có thể được xem là đã hoàn tất. Không nên trả lỗi khiến IdP retry vô hạn chỉ vì session không còn tồn tại.

### 9.2. Retry và timeout

Back-channel endpoint nên có timeout hợp lý và phản hồi nhanh sau khi đã xác minh/ghi nhận event theo thiết kế. Nếu cần xử lý nặng, có thể đưa event vào queue bền vững rồi trả acknowledgement khi đã lưu an toàn; worker xử lý tiếp và có retry.

Cần:
- Retry có giới hạn và backoff.
- Dead-letter queue hoặc cảnh báo khi delivery thất bại kéo dài.
- Giám sát tỷ lệ notification lỗi.
- Idempotency khi queue giao event ít nhất một lần.
- Chính sách xử lý khi RP không hoạt động trong thời gian dài.
- Không bỏ qua event âm thầm khi endpoint gặp lỗi.

Đối với front-channel, RP không kiểm soát được browser sẽ hoàn tất mọi iframe/navigation. Cần coi đây là kênh best-effort và có cơ chế timeout/session expiry bổ sung.

### 9.3. Fail-open hay fail-closed?

Nếu RP không thể xác minh logout notification, không được xóa session dựa trên dữ liệu chưa xác thực; điều đó có thể tạo denial of service. Tuy nhiên, nếu notification hợp lệ nhưng hệ thống session store đang lỗi, cần có chính sách bảo vệ dữ liệu: có thể tạm từ chối request nhạy cảm hoặc yêu cầu reauthentication cho tới khi trạng thái được đồng bộ.

Quyết định fail-open/fail-closed phụ thuộc rủi ro và khả năng vận hành. Không coi lỗi mạng là bằng chứng logout đã thành công.

## 10. Bảo vệ logout endpoint

Logout endpoint là bề mặt có thể bị lạm dụng để đăng xuất người dùng hoặc gây tải lớn.

Các kiểm soát cần có:
- Chỉ chấp nhận giao thức, method và content type được quy định.
- Xác minh chữ ký, issuer, audience và thời hạn trước khi xử lý.
- Giới hạn kích thước request/token.
- Rate limit và bảo vệ trước request flood.
- Dùng TLS; bảo vệ endpoint bằng client authentication hoặc network controls nếu profile cho phép, nhưng không thay xác minh token.
- Không dùng subject/email do caller gửi làm căn cứ xóa session.
- Chống replay bằng jti/request ID và atomic consume.
- Không tiết lộ thông tin session có tồn tại hay không qua response.
- Log reason code, issuer, event ID và số session bị ảnh hưởng; không log token thô.

Một attacker có thể gửi logout token giả để ép RP xóa session. Chữ ký và issuer validation là điều kiện bắt buộc trước khi thực hiện.

## 11. Front-channel, browser privacy và cookie

Front-channel logout có thể chạy trong iframe hoặc navigation cross-site. Browser hiện đại có thể hạn chế third-party cookies, partition storage hoặc chặn nội dung nhúng. Vì vậy RP không nên giả định cookie session luôn được gửi khi logout URI được mở trong iframe.

Một số giới hạn:
- Cookie SameSite=Lax/Strict có thể không được gửi trong iframe cross-site.
- SameSite=None; Secure vẫn có thể bị browser chặn theo third-party cookie policy.
- CSP frame-ancestors hoặc X-Frame-Options có thể ngăn IdP nhúng logout page.
- Browser có thể đóng tab hoặc ngắt request.
- Ứng dụng có thể chạy trong nhiều browser profile hoặc thiết bị khác nhau.

Nếu front-channel cần cookie để tìm session, thiết kế cần hiểu SameSite, browser policy và các phương án thay thế. Không hạ toàn bộ session cookie xuống SameSite=None chỉ để làm iframe logout hoạt động.

Back-channel logout thường đáng tin cậy hơn cho việc vô hiệu hóa session server-side vì không phụ thuộc browser cookie. Có thể kết hợp front-channel để cập nhật UI với back-channel để đảm bảo backend nhận sự kiện.

## 12. User-facing logout notification và security alert

Cần phân biệt logout notification giữa hệ thống với thông báo gửi cho người dùng.

**Protocol notification** là thông điệp IdP gửi tới RP để kết thúc session. **Security alert** là thông báo cho người dùng rằng có một sự kiện đáng chú ý, chẳng hạn đăng xuất từ thiết bị mới, session bị thu hồi hoặc tài khoản bị quản trị viên vô hiệu hóa.

Security alert có thể hữu ích khi:
- Session bị kết thúc do phát hiện rủi ro.
- Tài khoản bị vô hiệu hóa hoặc có thay đổi credential.
- Người dùng yêu cầu logout tất cả thiết bị.
- Một session từ thiết bị/vị trí lạ bị thu hồi.
- Quản trị viên buộc logout do sự cố bảo mật.

Thông báo cho người dùng cần:
- Không chứa session ID, token hoặc thông tin xác thực.
- Không đưa link đăng nhập tới domain không đáng tin.
- Dùng kênh liên hệ đã xác minh và policy notification.
- Tránh tiết lộ chi tiết có thể giúp attacker biết trạng thái bảo mật của người khác.
- Cung cấp hướng dẫn hành động an toàn nếu người dùng không nhận ra sự kiện.
- Có cơ chế chống spam và chống giả mạo thông báo.

Không gửi email cho mọi local logout thông thường nếu điều đó gây nhiễu; chọn sự kiện thực sự có giá trị bảo mật hoặc người dùng đã yêu cầu.

## 13. Audit và khả năng quan sát

Logout là sự kiện bảo mật quan trọng. Audit giúp điều tra khi session bị chiếm, logout không đồng bộ hoặc người dùng báo vẫn truy cập được sau khi đăng xuất.

Một event có thể ghi:
- Event type: local_logout, rp_initiated_logout, idp_logout_received, backchannel_logout_processed.
- Issuer/IdP và client/RP.
- Subject reference đã được bảo vệ.
- sid hoặc SessionIndex khi có và khi policy cho phép.
- Event ID/jti đã được che hoặc tham chiếu.
- Thời điểm nhận, thời điểm xử lý và kết quả.
- Số session bị vô hiệu hóa.
- Lý do thất bại theo reason code.
- Correlation ID và service instance.

Không log raw Logout Token, ID token, access token, cookie, NameID nhạy cảm hoặc dữ liệu cá nhân dư thừa. Dùng subject reference nội bộ, masking và retention phù hợp.

Các chỉ số hữu ích:
- Tỷ lệ notification được xác minh thành công.
- Tỷ lệ delivery failure và retry.
- Thời gian từ IdP logout tới RP invalidation.
- Số session được kết thúc theo event.
- Tỷ lệ duplicate/replay bị phát hiện.
- Số request tới session đã logout nhưng vẫn được chấp nhận.
- Số session không tìm thấy mapping.

## 14. Threat model và biện pháp kiểm soát

| Mối đe dọa | Cách xảy ra | Kiểm soát |
| --- | --- | --- |
| **Forged logout** | Attacker gửi request logout giả | Xác minh chữ ký, issuer, audience và token profile |
| **Logout replay** | Dùng lại notification hợp lệ | jti/request ID, replay cache và atomic consume |
| **Wrong-session invalidation** | Dùng subject/email để xóa nhầm nhiều session | Mapping issuer + sid/sub và policy scope |
| **Denial of service** | Gửi hàng loạt request logout để ép người dùng đăng xuất | Xác thực trước khi xóa, rate limit và monitoring |
| **Notification loss** | RP down hoặc browser không xử lý iframe | Back-channel, retry, queue, timeout và session expiry |
| **Token remains valid** | Session local bị xóa nhưng access token còn hiệu lực | Token revocation/introspection, short lifetime hoặc denylist |
| **Issuer confusion** | Token từ IdP khác được chấp nhận | Issuer allowlist và audience/client binding |
| **Key confusion** | JWKS/algorithm không đáng tin | Issuer-bound JWKS, allowlist, key rotation |
| **Session mapping gap** | RP không lưu sid/sub với local session | Ghi mapping khi tạo session và kiểm thử |
| **Front-channel cookie blocked** | Browser không gửi cookie trong iframe | Không phụ thuộc front-channel đơn độc; back-channel |
| **XML signature attack** | SAML XML signature wrapping hoặc parser lỗi | XML signature validation đúng node, parser hardening |
| **Sensitive audit leakage** | Log token hoặc subject thô | Redaction, access control và retention |
| **Stale browser cache** | Dữ liệu vẫn hiện sau logout | Cache policy, clear client state và server enforcement |

## 15. Ví dụ triển khai xử lý OIDC back-channel logout

Pseudocode minh họa:

~~~text
function handleBackchannelLogout(httpRequest):
    requireMethod(httpRequest, "POST")
    requireContentType(httpRequest, "application/x-www-form-urlencoded")
    requireBodySizeWithinLimit(httpRequest)

    logoutToken = parseLogoutToken(httpRequest.body)

    claims = verifyJwt(
        token = logoutToken,
        trustedIssuer = configuredIssuer,
        trustedJwks = issuerBoundJwks,
        allowedAlgorithms = configuredAllowlist
    )

    require(claims.iss == configuredIssuer)
    require(audienceContains(claims.aud, registeredClientId))
    requireValidIssuedAtAndExpiry(claims.iat, claims.exp)
    require(claims.events contains backchannelLogoutEvent)
    require(claims.nonce is absent)
    require(claims.sub exists OR claims.sid exists)

    if replayStore.consumeOnce(claims.iss, claims.jti) == false:
        return safeDuplicateAcknowledgement()

    sessions = sessionStore.findByIssuerAndSessionOrSubject(
        issuer = claims.iss,
        sid = claims.sid,
        sub = claims.sub
    )

    for each session in sessions:
        sessionStore.invalidate(session.id)
        revokeAssociatedRefreshGrantIfSupported(session)

    audit("backchannel_logout_processed", claims.jti, sessions.count)
    return success()
~~~

Pseudocode chỉ mô tả trình tự trách nhiệm. Production implementation phải dùng thư viện OIDC/JWT/XML đáng tin cậy, validate đầy đủ profile, xử lý concurrency, database transaction, queue, retry và mapping session.

Không thực hiện session deletion trước khi xác minh token. Nếu việc thu hồi refresh token hoặc ghi audit lỗi, cần có policy retry/compensation và không báo thành công vượt quá trạng thái đã đạt.

## 16. Kiểm thử logout notification

| Test case | Kết quả mong đợi |
| --- | --- |
| Logout local tại RP | Session local bị vô hiệu hóa |
| RP-initiated logout | RP kết thúc local session và gọi end-session theo cấu hình |
| Logout Token có chữ ký hợp lệ | RP tìm đúng session và xử lý |
| Issuer sai | Từ chối, không xóa session |
| Audience sai | Từ chối |
| Token hết hạn hoặc iat bất thường | Từ chối theo clock policy |
| Thiếu logout event claim | Từ chối |
| Có nonce trong Logout Token | Từ chối theo đặc tả |
| Không có cả sub lẫn sid | Từ chối theo đặc tả |
| jti đã được xử lý | Không lặp side effect |
| Hai notification đồng thời | Atomic replay handling, không xử lý trùng |
| sid khớp một session | Chỉ session tương ứng bị kết thúc |
| sub-only notification | Phạm vi xử lý theo policy và protocol |
| Issuer khác nhưng sub giống nhau | Không xóa session của issuer khác |
| RP tạm thời offline | Delivery retry hoặc queue theo policy |
| Front-channel iframe không có cookie | Không giả định đã kết thúc session server-side |
| Refresh token bị thu hồi | Không thể refresh theo trạng thái AS |
| JWT access token còn hạn sau logout | RS xử lý theo revocation/expiry policy |
| SAML LogoutRequest chữ ký sai | SP từ chối |
| SAML SessionIndex không khớp | Không xóa session khác |
| Browser back button sau logout | Không hiển thị dữ liệu nhạy cảm từ cache theo policy |
| User-facing alert | Không chứa token, cookie hoặc session ID |

### 16.1. Kiểm tra nhiều ứng dụng và thiết bị

Tạo test matrix có ít nhất hai RP và hai session/thiết bị cho cùng một subject. Xác minh:
- Logout tại RP A có chỉ kết thúc session A hay còn gọi IdP logout theo policy.
- Logout tại IdP có tới cả RP A và B không.
- Logout theo sid có giữ session khác của cùng subject nếu protocol/policy yêu cầu.
- Logout theo sub có xử lý đúng phạm vi subject.
- Một session bị revoke có bị tạo lại từ refresh token cũ không.
- Browser cũ có còn hiển thị dữ liệu từ cache hoặc back-forward navigation không.

Không chỉ kiểm tra redirect cuối cùng. Cần xác minh server-side session store, refresh token state và API access sau logout.

## 17. Checklist review

| Câu hỏi | Dấu hiệu thiết kế tốt |
| --- | --- |
| Phạm vi logout được định nghĩa? | Local, RP, IdP, session hay subject rõ ràng |
| Có phân biệt front-channel và back-channel? | Kênh được chọn theo độ tin cậy và khả năng |
| Logout Token được xác minh? | Signature, iss, aud, exp, iat, events và jti |
| sub/sid được ánh xạ đúng? | Issuer-bound session mapping |
| Có replay protection? | Atomic consume và TTL phù hợp |
| Xử lý idempotent? | Notification lặp không tạo side effect |
| Có retry/delivery monitoring? | Timeout, backoff, queue và cảnh báo |
| Session local bị vô hiệu hóa thực sự? | Store/cache/API enforcement được cập nhật |
| Refresh token/grant được xử lý? | Revoke theo policy, không giả định tự mất |
| JWT access token còn hiệu lực được xử lý? | Short lifetime, introspection hoặc revocation strategy |
| SAML SLO được xác minh? | Signature, issuer, destination, NameID/SessionIndex |
| Browser privacy được tính đến? | Front-channel không phải cơ chế duy nhất |
| Endpoint chống DoS? | Xác thực trước khi xóa, size/rate limit |
| User alert có an toàn? | Kênh đã xác minh, nội dung tối thiểu |
| Audit có đủ và không lộ bí mật? | Event ID/reason code, không log token thô |
| Có test nhiều RP/device? | Đã kiểm tra session scope và propagation |

### Tình huống tự kiểm tra

**Tình huống 1:** Người dùng logout tại IdP. Có thể giả định session local ở mọi RP đã kết thúc ngay không?

**Trả lời:** Không. RP phải nhận và xử lý notification hoặc có cơ chế đồng bộ khác. Delivery có thể chậm hoặc thất bại.

**Tình huống 2:** Một RP nhận Logout Token có chữ ký hợp lệ nhưng audience là client khác. Có nên xóa session không?

**Trả lời:** Không. Audience phải chứa client/RP nhận thông điệp. Token dành cho client khác không được dùng để kết thúc session của RP hiện tại.

**Tình huống 3:** Logout Token có sid. RP có nên xóa mọi session của cùng email không?

**Trả lời:** Không. sid định danh session IdP; cần ánh xạ issuer + sid tới đúng session local. Email không phải khóa session đáng tin cậy.

**Tình huống 4:** Back-channel logout đã xóa session nhưng access token JWT vẫn còn hạn và API chỉ xác minh chữ ký/exp. API có thể tiếp tục chấp nhận token không?

**Trả lời:** Có thể. Cần thiết kế revocation/introspection, denylist hoặc access token lifetime ngắn nếu cần thu hồi sớm.

**Tình huống 5:** Browser chặn third-party cookies nên front-channel iframe không tìm được session cookie. Có thể coi logout đã hoàn tất không?

**Trả lời:** Không. Cần cơ chế server-side như back-channel hoặc session expiry/revocation phù hợp.

**Tình huống 6:** IdP gửi cùng logout event ba lần do retry. RP có nên xóa session ba lần và báo lỗi hai lần sau không?

**Trả lời:** Xử lý nên idempotent. Event đã được xác minh và xử lý rồi có thể được acknowledgement an toàn mà không lặp side effect.

## 18. Ghi nhớ

**Logout notification là cơ chế truyền yêu cầu kết thúc session giữa IdP và các ứng dụng đã tin cậy nhau.** Front-channel dùng browser và có thể bị ảnh hưởng bởi cookie/privacy policy; back-channel gửi trực tiếp tới backend và thường phù hợp hơn để vô hiệu hóa session server-side. OIDC dùng Logout Token có chữ ký, issuer, audience, thời gian, event và định danh subject/session; SAML dùng LogoutRequest/LogoutResponse theo profile SLO.

RP phải xác minh thông điệp trước khi hành động, ánh xạ đúng issuer + sid/sub, chống replay, xử lý idempotent và cập nhật session store. Logout notification không tự thu hồi mọi access token, không thay thế authorization và không bảo đảm mọi thiết bị đã đăng xuất tức thời. Thiết kế hoàn chỉnh cần kết hợp session invalidation, token revocation strategy, retry, audit, browser behavior và kiểm thử nhiều RP/thiết bị.
