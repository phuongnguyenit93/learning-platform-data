# SSO session trong quản lý vòng đời danh tính IAM

> **Chương: SSO.** **SSO session** là trạng thái phiên được thiết lập trong quá trình người dùng đăng nhập liên thông (**Single Sign-On — SSO**), cho phép các ứng dụng tin cậy nhận biết người dùng đã được xác thực mà không bắt họ nhập lại thông tin đăng nhập ở mỗi ứng dụng. Trong thực tế không có một “phiên SSO toàn cục” duy nhất cho mọi hệ thống: phiên tại **Identity Provider (IdP)**, phiên cục bộ ở **Relying Party/Service Provider (RP/SP)** và **token cấp cho API** có vòng đời, nơi lưu trữ và khả năng thu hồi khác nhau. Hiểu sự khác biệt đó là điều kiện quan trọng để quản lý phiên đúng khi **Joiner–Mover–Leaver**, thay đổi quyền RBAC/ABAC và thực hiện Leaver an toàn.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **IdP session**, **application session**, **authentication assertion/token**, **access token** và **refresh token**.
2. Diễn giải cách phiên được thiết lập trong **OIDC/OAuth 2.0** và **SAML 2.0**, gồm mối liên hệ giữa cookie, redirect, token và phiên tại ứng dụng.
3. Thiết kế thời hạn **idle timeout**, **absolute timeout**, yêu cầu xác thực lại, MFA step-up, cơ chế logout và thu hồi phiên.
4. Nhận biết rủi ro **session fixation, hijacking, CSRF, token replay, cookie leakage, stale claims và session tồn dư**.
5. Phân tích tác động của **Joiner–Mover–Leaver**, IdP, SCIM, RBAC/ABAC và tài khoản đặc quyền đến các phiên đã tồn tại.
6. Xây dựng quy trình kiểm thử, giám sát và đối soát SSO session trên nhiều ứng dụng để tránh kết luận thu hồi sai.

## 1. SSO session là gì và vì sao dễ hiểu nhầm?

Một nhân viên mở CRM, được chuyển tới IdP, hoàn tất đăng nhập cùng MFA rồi quay lại CRM. Sau đó người này mở hệ thống wiki và không phải nhập mật khẩu lần nữa. Đây là trải nghiệm SSO điển hình.

Tuy nhiên có ít nhất **ba lớp trạng thái**:

- **Phiên tại IdP (IdP session):** IdP ghi nhớ rằng trình duyệt hoặc client đã xác thực, thường bằng cookie hoặc cơ chế quản lý phiên riêng. Phiên này có thể cho phép người dùng nhận kết quả xác thực cho một ứng dụng khác mà không lặp toàn bộ bước đăng nhập.
- **Phiên tại ứng dụng (RP/SP session):** CRM, wiki hoặc ứng dụng khác có thể tạo **cookie session riêng**, hoặc dùng cơ chế phiên ứng dụng sau khi kiểm chứng kết quả SSO. Mỗi ứng dụng có thời hạn, trạng thái và chính sách riêng.
- **Token và credential truy cập:** ứng dụng có thể giữ hoặc sử dụng ID token, access token, refresh token hoặc credential khác để gọi API. Chúng có điều kiện sử dụng và hạn riêng; không nên đồng nhất với cookie IdP hay session ứng dụng.

Vì vậy, **IdP session hết hạn không có nghĩa mọi app session lập tức hết hạn**. Tương tự, một lần đăng xuất ở CRM không nhất thiết xóa phiên IdP hoặc đăng xuất khỏi wiki. Mức đồng bộ phụ thuộc vào giao thức, cấu hình logout, kiến trúc và khả năng của từng hệ thống.

### Tình huống minh họa

**Lan** đăng nhập IdP lúc 08:00, sau đó vào CRM và wiki.

| Thành phần | Kết quả sau đăng nhập | Chủ thể quản lý | Tác động nếu IdP session hết hạn lúc 12:00 |
| --- | --- | --- | --- |
| IdP | Có phiên đăng nhập trung tâm. | IdP. | Lần yêu cầu xác thực mới có thể phải đăng nhập lại. |
| CRM | Có cookie session cục bộ. | CRM/RP. | CRM có thể vẫn chấp nhận phiên cho tới hạn riêng, nếu không kiểm tra lại. |
| Wiki | Có session riêng hoặc cơ chế dựa trên token. | Wiki/SP. | Không tự đồng bộ với CRM trừ khi có thiết kế cụ thể. |
| API báo cáo | Có access token dành cho API. | Authorization Server và Resource Server. | Token có thể còn hạn tùy cách kiểm tra và cơ chế thu hồi. |

Không nên suy ra kết quả thực tế của một sản phẩm chỉ từ bảng ví dụ. Khi triển khai phải đọc chính sách của hệ thống, thử nghiệm đăng nhập/đăng xuất và **xác minh trạng thái thực tế**.

## 2. Phân biệt identity, account, authentication và session

SSO session là kết quả của **xác thực**, nhưng được dùng trong hệ thống **IAM lifecycle** có các khái niệm rộng hơn:

| Khái niệm | Trả lời câu hỏi | Ví dụ |
| --- | --- | --- |
| **Identity** | Chủ thể được IAM quản lý là ai? | Identity ID-2041 liên kết hồ sơ HR. |
| **Account** | Chủ thể có tài khoản ở hệ thống nào? | IdP User, CRM User, wiki User. |
| **Identity proofing** | Danh tính được liên kết với con người đúng và đáng tin cậy chưa? | Hồ sơ Joiner được kiểm tra theo chính sách. |
| **Authentication** | Người yêu cầu truy cập chứng minh quyền kiểm soát authenticator ra sao? | Passkey hoặc mật khẩu kèm MFA. |
| **SSO session** | Kết quả xác thực được duy trì cho các tương tác tiếp theo thế nào? | IdP session và cookie ứng dụng. |
| **Authorization** | Người dùng được làm gì trên tài nguyên nào, trong điều kiện nào? | RBAC/ABAC quyết định quyền xem báo cáo. |
| **Provisioning** | Account và quyền tại ứng dụng đã được tạo/cập nhật/khóa chưa? | SCIM User active=false sau Leaver. |

**Một phiên xác thực hợp lệ không đồng nghĩa mọi quyền đều hợp lệ.** Ví dụ, sau Mover, Lan vẫn là cùng một người nên có thể tiếp tục xác thực thành công; nhưng quyền SupportAdmin không còn được dùng khi Lan chuyển sang Finance. Ứng dụng phải cập nhật và thực thi authorization độc lập với việc SSO session còn sống.

### Mô hình ba lớp phiên

~~~mermaid
flowchart TD
    U["User và thiết bị"] --> B["Browser / Native client"]
    B --> IDP["IdP: xác thực, MFA<br/>IdP SSO session"]
    IDP --> RP1["RP/SP: CRM<br/>App session A"]
    IDP --> RP2["RP/SP: Wiki<br/>App session B"]
    IDP --> RP3["RP/SP: Dashboard<br/>App session C"]
    RP1 --> API["API: access token<br/>authorization từng request"]
    HR["HR / nguồn JML"] --> IAM["IAM lifecycle<br/>Identity + trạng thái"]
    IAM --> IDP
    IAM --> SCIM["SCIM / provisioning"]
    SCIM --> RP1
    SCIM --> RP2
    SCIM --> RP3
    IAM --> AUD["Audit và đối soát"]
    IDP --> AUD
    RP1 --> AUD
    RP2 --> AUD
    RP3 --> AUD
~~~

Đường nối trong sơ đồ chỉ biểu diễn quan hệ khái niệm; không có nghĩa IdP tự tạo trực tiếp app session hoặc SCIM luôn được tích hợp ở tất cả ứng dụng.

## 3. SSO session được hình thành qua OIDC như thế nào?

**OpenID Connect (OIDC)** là lớp giao thức định danh xây trên OAuth 2.0. Một ứng dụng **Relying Party (RP)** có thể dựa vào IdP/OpenID Provider để xác thực người dùng. Trong ứng dụng web hiện đại, **Authorization Code Flow với PKCE** thường là một lựa chọn quan trọng cho client phù hợp.

### Luồng tham khảo

~~~mermaid
sequenceDiagram
    actor User as Lan
    participant Browser as Browser
    participant RP as CRM / Relying Party
    participant OP as OIDC Provider / IdP
    User->>Browser: Truy cập CRM
    Browser->>RP: GET /dashboard
    RP-->>Browser: Redirect tới authorization endpoint
    Browser->>OP: Authorization request: client, state, PKCE
    OP->>OP: Kiểm tra IdP session
    alt IdP session chưa đủ điều kiện
        OP->>User: Yêu cầu login/MFA theo chính sách
        User-->>OP: Hoàn tất xác thực
    else IdP session đủ điều kiện
        OP->>OP: Sử dụng phiên IdP hợp lệ
    end
    OP-->>Browser: Redirect authorization code và state
    Browser->>RP: Callback tới redirect URI
    RP->>RP: Kiểm tra state và callback
    RP->>OP: Đổi code với PKCE verifier
    OP-->>RP: Token response
    RP->>RP: Kiểm chứng ID token và định danh
    RP-->>Browser: Tạo ứng dụng session an toàn
    Browser->>RP: Request tiếp theo kèm app cookie
    RP-->>Browser: Trả tài nguyên theo quyền hiện hành
~~~

Ở luồng này:

1. IdP quyết định có cần xác thực mới hay có thể dùng phiên IdP hiện tại.
2. RP kiểm tra callback và token theo yêu cầu OIDC, gồm issuer, audience, chữ ký, thời hạn và các claim/ràng buộc áp dụng cho flow.
3. RP liên kết **subject từ issuer cụ thể** với đúng account ứng dụng; tránh dùng email làm khóa duy nhất.
4. RP có thể tạo một **app session riêng** cho trình duyệt, thường dùng cookie an toàn.
5. Khi app session hết hạn, RP có thể bắt đầu luồng OIDC lần nữa. Nếu IdP session vẫn còn và đáp ứng chính sách, người dùng có thể lại được SSO mà không nhập mật khẩu.

### ID token, access token và refresh token không giống nhau

| Đối tượng | Mục đích điển hình | Điều không nên suy ra |
| --- | --- | --- |
| **ID token** | Chuyển thông tin kết quả xác thực/identity từ OpenID Provider tới RP theo OIDC. | Không dùng tùy tiện như access token cho API. |
| **Access token** | Cho phép client gọi một resource server theo audience, scope và chính sách. | Không mặc nhiên là bằng chứng xác thực người dùng dành cho RP. |
| **Refresh token** | Cho phép client xin token mới theo cơ chế đã được cấp và kiểm soát. | Không đồng nghĩa mọi access token cũ được thu hồi khi refresh token bị rút. |
| **IdP session cookie** | Duy trì phiên tại IdP theo cơ chế trình duyệt hoặc sản phẩm. | Không phải cookie của CRM hoặc Wiki. |
| **App session cookie** | Duy trì phiên CRM/Wiki riêng sau SSO. | Không buộc IdP còn session tại mọi request của ứng dụng. |

**OAuth 2.0 riêng lẻ là khung ủy quyền**, không nên tự xem access token bất kỳ là dấu hiệu người dùng đã đăng nhập tại RP. Cần sử dụng kết quả OIDC đúng mục đích hoặc giao thức xác thực tương ứng.

### Các kiểm tra OIDC quan trọng

- **state** bảo vệ tính liên kết request–callback và là một phần phòng vệ CSRF trong luồng phù hợp.
- **PKCE** ràng buộc authorization code với client bắt đầu yêu cầu, giảm nguy cơ code bị đánh cắp và đổi trái phép.
- **nonce** khi được sử dụng theo profile/flow phải được đối chiếu với ID token phù hợp.
- Kiểm tra **issuer** và **audience**, không tin một token chỉ vì chữ ký hợp lệ nếu token dành cho issuer/client khác.
- Kiểm tra chữ ký theo cấu hình thuật toán và key tin cậy; không chấp nhận thuật toán/key tùy ý từ dữ liệu chưa xác thực.
- **sub** là định danh chủ thể trong ngữ cảnh issuer, không tự thay bằng email, tên hiển thị hoặc ID HR.
- **auth_time, acr, amr** có thể là tín hiệu hỗ trợ kiểm soát độ mới và phương thức xác thực khi được IdP cung cấp đúng hợp đồng; không tự suy diễn mức bảo đảm chỉ từ sự tồn tại một claim.

**Điểm mấu chốt:** OIDC giúp RP biết kết quả xác thực từ IdP. RP vẫn chịu trách nhiệm về app session của mình và cách thực thi quyền tại API/tài nguyên.

## 4. SSO session qua SAML 2.0

Trong **SAML 2.0**, **Identity Provider** xác thực người dùng và phát hành SAML Response/Assertion cho **Service Provider (SP)**. SP kiểm tra thông điệp và có thể tạo phiên ứng dụng riêng.

### Các bước SP-initiated điển hình

1. Người dùng truy cập SP khi chưa có app session hợp lệ.
2. SP chuyển hướng hoặc gửi **AuthnRequest** tới IdP.
3. IdP xem phiên hiện tại có đủ điều kiện hay cần xác thực lại theo chính sách.
4. Sau khi xác thực, IdP trả về SAML Response/Assertion tới endpoint phù hợp.
5. SP kiểm tra chữ ký trên thành phần phù hợp, trust metadata, issuer, audience, recipient/destination, thời hạn, SubjectConfirmation và ràng buộc request khi áp dụng.
6. SP ánh xạ chủ thể vào đúng account/tenant và tạo **SP session**.

### Những thuộc tính liên quan tới phiên

| Thành phần SAML | Vai trò | Điều cần lưu ý |
| --- | --- | --- |
| **AuthnStatement** | Thông tin về việc xác thực người dùng. | Có thể có AuthnInstant và SessionIndex. |
| **SessionIndex** | Hỗ trợ nhận diện phiên của một AuthnStatement trong cơ chế liên quan. | Không phải mã cookie session của mọi SP và không bảo đảm SLO toàn hệ thống. |
| **SessionNotOnOrAfter** | Giới hạn thời điểm phiên gắn với authentication statement không nên tiếp tục được sử dụng theo ngữ nghĩa giao thức. | Không tự quy định toàn bộ lifetime của cookie cục bộ nếu SP không áp dụng đúng. |
| **Conditions/NotOnOrAfter** | Giới hạn thời hạn có thể dùng assertion. | Assertion hết hạn không đồng nghĩa mọi SP session trước đó hết hạn tức thì. |
| **NameID** | Định danh chủ thể theo định dạng đã cấu hình. | Phải xét IdP, namespace và mapping; email-format không tự bảo đảm duy nhất/bất biến. |
| **ForceAuthn** | SP yêu cầu IdP xác thực trực tiếp lại thay vì chỉ dựa phiên cũ khi được hỗ trợ đúng. | Việc xác thực lại và yếu tố bảo đảm vẫn phải theo chính sách thực tế. |

Với **IdP-initiated SSO**, SP có thể không có AuthnRequest tương ứng để kiểm tra InResponseTo như SP-initiated flow. Nếu tổ chức cho phép cách này, cần xác định các biện pháp bảo vệ và giới hạn tin cậy riêng; không bỏ qua kiểm tra chữ ký, audience, thời hạn hoặc chủ thể chỉ để “đăng nhập được”.

### IdP session khác SP session

Khi IdP session kết thúc, SP có thể tiếp tục giữ session riêng tới khi app tự hết hạn hoặc nhận và thực thi một sự kiện logout đáng tin cậy. Vì vậy, **SAML Single Logout (SLO)** là một khả năng giao thức có thể được cấu hình, **không phải lời bảo đảm** mọi ứng dụng luôn đăng xuất đồng thời.

## 5. Vòng đời phiên: tạo, duy trì, nâng mức và kết thúc

Một thiết kế nội bộ có thể xem xét các trạng thái:

~~~mermaid
stateDiagram-v2
    [*] --> UNAUTHENTICATED
    UNAUTHENTICATED --> AUTHENTICATING: Bắt đầu SSO
    AUTHENTICATING --> AUTHENTICATED: IdP result hợp lệ
    AUTHENTICATING --> UNAUTHENTICATED: Thất bại/hủy
    AUTHENTICATED --> STEP_UP_REQUIRED: Tài nguyên nhạy cảm
    STEP_UP_REQUIRED --> AUTHENTICATED: Step-up đạt
    STEP_UP_REQUIRED --> REVOKED: Chính sách từ chối
    AUTHENTICATED --> EXPIRED: Idle/absolute timeout
    AUTHENTICATED --> LOGGED_OUT: Logout
    AUTHENTICATED --> REVOKED: Suspend/Leaver/rủi ro
    EXPIRED --> [*]
    LOGGED_OUT --> [*]
    REVOKED --> [*]
~~~

Đây là state machine minh họa, không phải một state machine bắt buộc của OIDC/SAML hoặc bất kỳ sản phẩm IdP nào. **Phiên IdP, phiên RP/SP và token** có thể ở những trạng thái khác nhau tại cùng thời điểm.

### Idle timeout và absolute timeout

Hai khái niệm phổ biến:

- **Idle timeout:** phiên hết hiệu lực sau một khoảng không hoạt động theo định nghĩa của hệ thống.
- **Absolute timeout:** phiên có thời hạn tối đa kể từ lúc được thiết lập, dù người dùng tiếp tục hoạt động.

Ví dụ nội bộ:

~~~text
createdAt = 08:00
lastActivityAt = 09:40
idleLimit = 30 phút
absoluteLimit = 8 giờ

expiresAt = min(
    lastActivityAt + idleLimit,
    createdAt + absoluteLimit
)
~~~

Đây là phép tính khái niệm; cần xác định event nào được xem là hoạt động, cơ chế gia hạn, timezone và clock source. Không dùng cùng một giá trị timeout cho mọi ứng dụng mà không xét mức nhạy cảm, yêu cầu làm việc và khả năng kỹ thuật.

### Reauthentication và step-up

**Reauthentication** yêu cầu chứng minh lại quyền kiểm soát phương thức xác thực sau một thời gian hoặc khi có rủi ro. **Step-up authentication** yêu cầu mức bảo đảm cao hơn trước khi cho phép thao tác nhạy cảm.

Ví dụ, người dùng đọc wiki có thể dùng phiên SSO hiện tại; khi mở console quản trị production, chính sách yêu cầu **phishing-resistant MFA** và có thể thêm PAM/JIT. Một session trước đó chỉ xác thực bằng phương thức yếu không tự trở thành phiên đủ mức bảo đảm chỉ vì role admin được gán sau Mover.

Trong OIDC, RP có thể dùng các cơ chế yêu cầu độ mới phù hợp như **max_age** hoặc **prompt=login** theo hợp đồng; nhưng việc IdP bắt xác thực lại **không mặc nhiên đồng nghĩa** đã áp dụng phương thức MFA mạnh theo yêu cầu tài nguyên. Cần kiểm tra authentication context/assurance và thực thi policy tại ứng dụng.

## 6. Cookie và phiên ứng dụng: bảo vệ ở browser

Trong mô hình web, RP/SP có thể dùng cookie để gắn các request với session đã xác thực. Phải bảo vệ cookie và trạng thái server-side, vì cookie bị đánh cắp có thể cho phép sử dụng phiên mà không phải thực hiện lại MFA.

### Các kiểm soát quan trọng

| Kiểm soát | Ý nghĩa bảo mật | Điểm kiểm thử |
| --- | --- | --- |
| **HTTPS/TLS** | Bảo vệ dữ liệu phiên khi truyền. | Không chấp nhận đường truyền kém an toàn cho credential/session. |
| **Secure cookie** | Cookie chỉ gửi qua kết nối bảo mật theo thuộc tính trình duyệt. | Đảm bảo thuộc tính được cấu hình ở môi trường thực. |
| **HttpOnly cookie** | Hạn chế JavaScript đọc cookie. | Kiểm tra nơi token/cookie được lưu và tác động XSS. |
| **SameSite phù hợp** | Hạn chế một số tình huống gửi cookie cross-site. | Không xem SameSite là giải pháp thay thế cho mọi cơ chế chống CSRF. |
| **Cookie scope** | Giới hạn domain/path nhận cookie. | Không chia sẻ session cho subdomain hoặc ứng dụng không cần thiết. |
| **Session ID rotation** | Giảm nguy cơ session fixation khi thay đổi trạng thái xác thực. | Sau đăng nhập/step-up, session mới không phụ thuộc vào ID có thể bị cố định trước đó. |
| **Server-side revocation** | Có cách hủy session hoặc kiểm tra trạng thái trước khi xử lý. | Cookie cũ sau logout/Leaver không dùng được theo chính sách. |
| **Session lifetime** | Idle, absolute và time-bound privileged session. | Phiên hết hạn theo quy tắc đã xác định. |
| **CSRF defense** | Bảo vệ thao tác thay đổi trạng thái. | Request bất hợp lệ không thực hiện thao tác dù trình duyệt còn cookie. |

**Session fixation** là trường hợp kẻ tấn công khiến nạn nhân dùng một session ID đã biết trước, sau đó lợi dụng khi nạn nhân đăng nhập. Một ứng dụng cần thiết lập/luân chuyển định danh phiên phù hợp ở ranh giới đăng nhập, thay đổi mức bảo đảm hoặc sự kiện bảo mật.

### Đăng nhập trên nhiều thiết bị

Một người có thể có đồng thời:

- Phiên IdP trên trình duyệt máy tính công ty.
- Phiên IdP trên điện thoại.
- Phiên CRM ở một trình duyệt khác.
- Token API được một client đã cấp quyền giữ.

Chức năng “logout this device” và “logout all devices” phải có **ngữ nghĩa được xác định**. Kiểm thử phải xác minh phạm vi từng lệnh; không giả định việc xóa một cookie trình duyệt khiến tất cả thiết bị, ứng dụng, refresh token và access token đều lập tức bị hủy.

## 7. Logout và thu hồi phiên xuyên ứng dụng

Một vấn đề phổ biến là người dùng bấm “Sign out” ở một ứng dụng, nhưng vẫn truy cập được ứng dụng khác vì IdP hoặc các SP còn phiên riêng.

### Các phạm vi logout khác nhau

| Hành động | Phạm vi có thể đạt | Giới hạn thường gặp |
| --- | --- | --- |
| **Local logout tại RP/SP** | Hủy session của chính ứng dụng. | Có thể giữ IdP session và session ứng dụng khác. |
| **IdP logout** | Kết thúc phiên trung tâm theo chức năng IdP. | App session hoặc API token riêng có thể tồn tại. |
| **OIDC RP-Initiated Logout** | RP gửi người dùng tới logout endpoint của OpenID Provider theo hỗ trợ/cấu hình. | Không bảo đảm toàn bộ RP đã hủy session cục bộ. |
| **OIDC Front-Channel Logout** | Thông báo logout qua luồng trình duyệt cho RP tích hợp. | Phụ thuộc trình duyệt, cross-site behavior và RP hỗ trợ. |
| **OIDC Back-Channel Logout** | OpenID Provider gửi logout token qua kênh server-to-server tới RP hỗ trợ. | Cần xác minh logout token, mapping session/sub và xử lý delivery/retry. |
| **SAML Single Logout** | Phối hợp logout giữa IdP và SP triển khai SLO. | Có thể có SP không tham gia, timeout hoặc phiên độc lập. |
| **Revoke refresh token/session** | Ngăn một số lần gia hạn hoặc tiếp tục phiên. | Không mặc định hủy access token tự chứa còn hạn. |
| **Application/API-specific revocation** | Hủy cookie, PAT, token hoặc phiên ngay tại đích. | Phải tích hợp API và kiểm chứng ngữ nghĩa từng nhà cung cấp. |

### Các nguyên tắc khi xử lý logout event

1. Kiểm tra thông điệp logout được phát từ **nguồn tin cậy**, đúng issuer, audience, chữ ký và yêu cầu giao thức.
2. Liên kết logout với đúng **subject và session**; tránh logout nhầm người chỉ vì email giống nhau.
3. Thao tác phải **idempotent**: cùng event được gửi lại không làm tạo phiên mới hoặc gây lỗi dây chuyền.
4. Hạn chế replay, áp thời hạn, kiểm tra trạng thái message và ghi audit theo correlation ID.
5. Khi delivery lỗi, retry có giới hạn và đưa về hàng chờ xử lý/đối soát; không giả định tất cả RP đã logout.
6. Lập danh mục RP/SP hỗ trợ loại logout nào và **test đường thu hồi thực tế**.

**Không nên dùng logout làm biện pháp Leaver duy nhất.** Leaver thường cần disable account, thu hồi nhóm/quyền, session/token/credential và kiểm chứng ở ứng dụng đích.

## 8. Token tự chứa, cache và quyền truy cập tồn dư

Ngay cả khi IdP session đã kết thúc, các token và session ứng dụng có thể vẫn sử dụng được theo chính sách của từng Resource Server.

### Access token và refresh token

- **Access token tự chứa**, chẳng hạn JWT dùng làm bearer token, có thể được Resource Server kiểm tra chữ ký và thời hạn mà không truy vấn lại IdP. Nếu không có cơ chế thu hồi hoặc kiểm tra trạng thái, token vẫn có thể được chấp nhận tới khi hết hạn.
- **Opaque token** có thể được xác minh qua introspection nếu kiến trúc sử dụng; điều đó cho phép Resource Server dựa vào trạng thái phía máy chủ, nhưng chỉ an toàn khi nó thực sự thực hiện kiểm tra với chính sách cache phù hợp.
- **Refresh token** cho phép lấy token mới nếu chưa hết hạn và chưa bị thu hồi. Thu hồi refresh token giúp chặn làm mới, nhưng không mặc nhiên vô hiệu hóa mọi access token đã cấp.
- **App session cookie** có thể tiếp tục tồn tại ngay cả khi ID token đã hết hạn; session cục bộ cần kiểm soát lifetime và revocation riêng.

### Stale claims sau Mover

Lan thuộc Support lúc 08:00 và đăng nhập qua SSO, ứng dụng tạo session chứa department=Support. HR phát Mover sang Finance lúc 09:00.

Nếu ứng dụng dùng department trong session cũ để xác định quyền xem ticket, Lan có thể tiếp tục hưởng quyền theo phòng ban cũ cho tới khi session hết hạn, trừ khi:

1. Ứng dụng kiểm tra authorization qua policy engine hoặc nguồn thuộc tính đủ mới ở thời điểm sử dụng.
2. Ứng dụng có cơ chế nhận thay đổi và invalidate/refresh session, claim hoặc cache.
3. Hệ thống áp thời hạn ngắn hoặc giới hạn tồn dư được chấp nhận theo rủi ro.

**Không coi một claim được ký hợp lệ là dữ liệu tổ chức luôn hiện hành.** Chữ ký chứng minh nguồn gốc và tính toàn vẹn của claim tại thời điểm phát hành, không bảo đảm department/manager vẫn đúng sau Mover.

### Kiểm soát thời gian tồn dư

Một thiết kế cần xác định:

| Đường truy cập | Giới hạn thực tế | Kiểm soát phù hợp |
| --- | --- | --- |
| App session server-side | Tới khi bị invalidate hoặc hết hạn. | Central/local revocation, kiểm tra trạng thái User khi thao tác nhạy cảm. |
| Access token JWT offline | Tới khi exp hoặc bị chặn qua cơ chế bổ sung. | TTL phù hợp, introspection/gateway/policy check khi cần, denylist theo khả năng. |
| Refresh token | Có thể xin token mới cho đến khi revoke/hết hạn. | Token rotation/revocation và quản lý phiên. |
| Cached RBAC/ABAC attributes | Tới khi cache invalidation/refresh. | Event update, TTL, policy lookup, kiểm tra quyền tại request. |
| PAT/API key riêng | Có thể độc lập với phiên SSO. | Inventory và revoke/rotate tại ứng dụng/secret manager. |

Nếu chính sách yêu cầu **thu hồi tức thời**, không nên chỉ dựa vào token tự chứa dài hạn được xác minh offline mà không có biện pháp bổ sung đáp ứng yêu cầu.

## 9. SSO session trong Joiner–Mover–Leaver

SSO session có liên hệ chặt chẽ với **nguồn định danh**, **ngày hiệu lực** và **tập quyền truy cập thực tế**.

### Joiner: chuẩn bị account không phải mở session

Trong Joiner:

1. Nguồn HR/hợp đồng xác định identity, ngày bắt đầu, người quản lý và điều kiện làm việc.
2. IAM kiểm tra identity proofing, đối sánh chống trùng và tạo/liên kết identityId.
3. IdP User và account SaaS có thể được **pre-provision** qua SCIM/connector trước ngày kích hoạt.
4. Account chuẩn bị cần được ngăn tạo **phiên nghiệp vụ hợp lệ** trước thời điểm chính sách cho phép, trừ các luồng enrollment onboarding giới hạn.
5. Khi đủ điều kiện, User đăng ký MFA/passkey và có thể bắt đầu SSO session với đúng authentication assurance.
6. IAM đối soát IdP, app account, session policy, nhóm và quyền theo RBAC/ABAC.

**Bài kiểm tra quan trọng:** Một User pre-provisioned có được tạo IdP session hoặc app session cho tài nguyên nghiệp vụ trước ngày kích hoạt không? Nếu có, cần sửa tại điểm kiểm soát thực sự, không chỉ ghi nhãn PENDING_ACTIVATION trong IAM.

### Mover: phiên còn sống nhưng quyền phải thay đổi

Mover có thể thay bộ phận, nhóm, vai trò, người quản lý hoặc phạm vi tenant mà không thay người sở hữu danh tính.

Ví dụ:

- Lan chuyển từ Support sang Finance lúc 09:00.
- IdP session vẫn còn hợp lệ về xác thực.
- Ứng dụng phải gỡ quyền SupportAdmin không còn phù hợp và chỉ cấp FinanceViewer theo phê duyệt.
- Session hoặc token cũ chứa role SupportAdmin có thể là rủi ro nếu Resource Server vẫn cho phép thao tác theo claim cũ.

Biện pháp cần đánh giá gồm **kiểm tra lại quyền theo nguồn mới, invalidation cache/session khi cần, step-up với quyền nhạy cảm, thu hồi access token phù hợp và kiểm thử hành động trước/sau Mover**.

Không bắt buộc logout mọi ứng dụng sau từng Mover nếu hệ thống có kiểm soát quyền hiện hành đủ tin cậy; nhưng không được để **quyền cũ tồn dư** ngoài giới hạn chính sách.

### Leaver: chặn đăng nhập mới và xử lý phiên đã tồn tại

Trong Leaver:

1. Nhận sự kiện có thẩm quyền và **effectiveAt** rõ ràng.
2. Tới hiệu lực, ngăn tạo phiên mới ở IdP và các ứng dụng có local auth.
3. Thu hồi hoặc giới hạn IdP session theo chức năng hỗ trợ.
4. Phát hành logout/revocation event tới các RP/SP tích hợp khi có; không xem việc gửi event là bằng chứng đã áp dụng.
5. Khóa app account qua SCIM/API và xử lý **app-local sessions, refresh tokens, access tokens, PAT, API keys và credential cục bộ** phù hợp.
6. Đối soát quyền, session, token theo từng hệ thống; ghi trạng thái đã xác minh và phần chưa thể thu hồi.
7. Ngăn các retry Joiner/Mover cũ kích hoạt lại User hoặc khôi phục phiên/quyền.

Một sự kiện Leaver đúng không nên bị trì hoãn chỉ vì HR chưa cập nhật manager mới hoặc chưa hoàn tất bàn giao dữ liệu.

### Ma trận hiệu ứng JML

| Sự kiện | IdP session | RP/SP session và token | Điều cần chứng minh |
| --- | --- | --- | --- |
| Joiner chờ kích hoạt | Không tạo phiên truy cập nghiệp vụ trái chính sách. | Không có đường vào dữ liệu nội bộ ngoài onboarding được duyệt. | Pre-provision không đồng nghĩa active access. |
| Joiner kích hoạt | Cho phép xác thực theo proofing/MFA policy. | App session chỉ được tạo cho đúng identity/account. | Đúng người, ngày hiệu lực và quyền. |
| Mover thường | Có thể tiếp tục xác thực. | Quyền, claims/cache và phiên được xem lại theo policy. | Không giữ quyền cũ, không tự tăng quyền. |
| Mover sang vai trò nhạy cảm | Có thể cần reauthentication/step-up. | Phiên mức thấp không tự đủ điều kiện admin. | Đủ assurance và SoD/PAM khi cần. |
| Suspend | Chặn đăng nhập mới theo phạm vi đình chỉ. | Đánh giá thu hồi/giới hạn phiên đang có. | Không bypass qua ứng dụng hoặc local auth. |
| Leaver | Vô hiệu hóa xác thực mới; xử lý phiên IdP. | Thu hồi hoặc kiểm soát phần tồn dư tại mọi đích. | Không còn truy cập trái chính sách trong giới hạn quy định. |
| Rehire | Không tự phục hồi session cũ. | Tính lại quyền và enrollment theo công việc hiện tại. | Không tự bật lại quyền đã thu hồi. |

## 10. IdP, SCIM, RBAC/ABAC và tài khoản đặc biệt

### SCIM quản lý User, không thay thế quản lý phiên

SCIM (**System for Cross-domain Identity Management**) giúp tạo, cập nhật, vô hiệu hóa User và Group tại ứng dụng. Ví dụ, một connector có thể cập nhật **active=false** khi Leaver có hiệu lực.

Điều này rất quan trọng, nhưng **không bảo đảm**:

- Cookie session tại RP/SP đã bị hủy.
- Access token JWT còn hạn đã bị Resource Server từ chối.
- Refresh token của tất cả client đã được thu hồi.
- Account cục bộ, PAT hoặc API key ngoài SCIM đã bị vô hiệu hóa.
- Nhóm/role được gán trực tiếp trong ứng dụng đều đã biến mất.

Vì thế, trong quy trình Leaver, **SCIM update là một bước provisioning**, còn **session/token revocation và access verification** là những bước kiểm soát cần bổ sung theo khả năng đích.

### RBAC và ABAC trong suốt session

**RBAC** quyết định quyền theo vai trò; **ABAC** xét thuộc tính của subject, tài nguyên, hành động và bối cảnh. Một session có thể hợp lệ về authentication trong khi không còn phù hợp về authorization.

Pseudocode minh họa:

~~~text
ALLOW report.read KHI
    identity.lifecycleState = ACTIVE
    AND appSession.isValid
    AND session.authenticationAssurance >= requiredAssurance
    AND roleAllows(identity, "report.read")
    AND identity.tenantId = report.tenantId
    AND currentPolicyAllows(identity, report)
ELSE DENY
~~~

Các điều kiện phải được thực thi ở **điểm kiểm tra quyền phù hợp**, không chỉ chạy lúc login rồi giữ mãi quyết định allow. Với thao tác nhạy cảm, dữ liệu vòng đời và thuộc tính phân quyền cần đủ mới theo yêu cầu rủi ro.

### Tài khoản đặc quyền và PAM

Người dùng có thể có một account thường và một account quản trị riêng. Đối với phiên đặc quyền:

- Đòi hỏi MFA phù hợp, ưu tiên phương thức có chống phishing khi chính sách yêu cầu.
- Có thể cần **step-up** hoặc chứng minh lại phiên trước hành động nguy hiểm.
- Cấp đặc quyền theo JIT/PAM, giới hạn thời gian và giám sát session.
- Không cho một session user thường tự thực hiện hành động admin chỉ vì role mới được gán.
- Với Leaver, rút cả phiên PAM, credential và account admin, không chỉ khóa User thường.

### Service account và workload identity

Danh tính máy có thể dùng OAuth client credentials, workload federation, mTLS hoặc certificate. Các kênh này **không phải SSO session tương tác của con người**.

Tuy nhiên, quản lý vòng đời vẫn quan trọng:

| Mối quan hệ | Kiểm tra cần thiết |
| --- | --- |
| Workload được đăng ký | Có service owner, purpose và nguồn cấp danh tính đáng tin. |
| Credential/token máy | Đúng audience, scope, môi trường và hạn; có cách rotate/revoke. |
| Owner nghỉ việc | Chuyển owner, thu hồi quyền/secret cá nhân, không xóa bừa workload hợp lệ. |
| Dịch vụ ngừng hoạt động | Thu hồi trust relationship, service principal và quyền liên quan. |
| Audit | Phân biệt workload identity với account con người, truy vết đến owner và hệ thống. |

Không áp quy tắc timeout của browser cookie trực tiếp lên token machine-to-machine; cần chính sách riêng cho loại danh tính và phương thức sử dụng.

## 11. Quản lý phiên an toàn trước những lỗi phân tán

Trong hệ thống SSO có nhiều dịch vụ, các thay đổi thường bất đồng bộ. Điều này dẫn đến **race condition, stale event và trạng thái chưa đồng bộ**.

### Lỗi 1 — Leaver xảy ra trong lúc đang login

Người dùng bắt đầu OIDC login ở 16:59, HR phát Leaver có hiệu lực 17:00, callback quay về RP lúc 17:01. Nếu RP chỉ xét token được phát trước thời điểm khóa mà không kiểm tra chính sách access hiện hành, có thể tạo một app session trái quy định.

**Kiểm soát:** tại điểm cấp phiên hoặc điểm truy cập quan trọng, xác minh account/lifecycle state theo yêu cầu hệ thống, xử lý logout/revocation đã nhận, không coi một token được cấp trước Leaver là giấy phép vô thời hạn.

### Lỗi 2 — Retry Joiner bật lại tài khoản

1. Job Joiner gửi lệnh tạo/bật User và timeout.
2. Leaver có hiệu lực; IAM khóa User và thu hồi phiên.
3. Job Joiner được retry, bật lại User hoặc nhóm cũ.

**Kiểm soát:** mọi tác vụ cấp quyền phải dùng **sourceVersion, effectiveAt, identityId** và đọc trạng thái hiện hành; cập nhật có điều kiện/idempotency để sự kiện cũ không ghi đè quyết định Leaver.

### Lỗi 3 — Logout event đến sai thứ tự

Một app tạo session mới sau một lần xác thực hợp lệ, nhưng đồng thời nhận logout event của phiên cũ. Nếu không có định danh session hoặc mốc liên kết rõ ràng, ứng dụng có thể hủy nhầm session mới hoặc giữ phiên đã bị rút.

**Kiểm soát:** xử lý session identifier và subject theo hợp đồng giao thức, kiểm tra thời điểm, event ID, chống replay, idempotency và ánh xạ chính xác phạm vi logout.

### Lỗi 4 — Connector cập nhật xong nhưng RP còn quyền cũ

SCIM đã đổi group, nhưng RP tạo session với role cũ và cache quyền trong nhiều giờ.

**Kiểm soát:** quan sát trạng thái thực tế và effective permission; khi policy yêu cầu, invalidate session/cache hoặc thực hiện authorization lookup với dữ liệu hiện hành. Không công bố hoàn tất Mover chỉ dựa vào SCIM 200 OK.

### Lỗi 5 — IdP không liên lạc được

Phiên đang tồn tại có thể vẫn được RP chấp nhận khi IdP tạm lỗi; quy tắc này phải là **quyết định chính sách có chủ đích**, không phải fallback vô điều kiện.

Với tài nguyên nhạy cảm, cần xác định hành vi khi không thể xác nhận trạng thái người dùng, session hoặc quyền: fail closed, giới hạn chức năng, hoặc biện pháp kiểm soát bù tùy thiết kế. Không bỏ kiểm tra token hoặc issuer chỉ vì IdP tạm thời không phản hồi.

## 12. Thuật toán đánh giá và thu hồi phiên theo vòng đời

Một logic minh họa cho ứng dụng sau khi xác thực qua SSO:

~~~text
authorizeRequest(request):
    session = resolveApplicationSession(request)
    if session is absent or session.expired or session.revoked:
        return DENY

    identity = resolveIdentityByTrustedIssuerAndSubject(
        session.issuer,
        session.subject,
        session.tenant
    )
    if identity is unresolved:
        return DENY_AND_REVIEW

    lifecycle = getCurrentLifecycleState(identity.sourceKey)
    if lifecycle is unavailable:
        return applyDocumentedRiskPolicy(request.resource)
    if lifecycle.status in [TERMINATED, SUSPENDED]:
        revokeOrFlagSession(session)
        return DENY

    if request.requiresFreshAuthentication:
        if session.authTime too old or assurance insufficient:
            return REQUIRE_REAUTH_OR_STEP_UP

    if not currentAuthorizationAllows(
        identity,
        request.action,
        request.resource,
        request.context
    ):
        return DENY

    return ALLOW
~~~

Đoạn mã chỉ là **pseudocode giáo dục**. Một hệ thống thực cần xử lý cache có thời hạn, availability, transaction boundaries, concurrency, quyền truy vấn nguồn, logging và các ngoại lệ hợp lệ. Không yêu cầu mọi API gọi HR trực tiếp trên từng request; có thể dùng nguồn trạng thái IAM/policy engine đáng tin cậy và đủ mới theo yêu cầu.

### Quy trình hủy phiên sau Leaver

~~~mermaid
flowchart TD
    E["HR hoặc nguồn có thẩm quyền<br/>Leaver effectiveAt"] --> V["Validate identity, time, sourceVersion"]
    V --> B["Chặn sign-in mới tại IdP<br/>và local auth"]
    B --> I["Thu hồi IdP session<br/>refresh token theo hỗ trợ"]
    I --> N["Notify RP/SP qua logout/event<br/>khi được cấu hình"]
    N --> A["Thu hồi app-local sessions<br/>PAT, token, credential"]
    A --> P["SCIM/connector cập nhật User,<br/>Group và quyền"]
    P --> R["Readback account, quyền,<br/>session/token theo phạm vi có thể"]
    R --> D{"Các điều kiện bắt buộc<br/>đã được xác minh?"}
    D -->|Có| C["REVOKED_VERIFIED<br/>lưu audit"]
    D -->|Chưa| F["PARTIAL_FAILURE<br/>retry, owner, kiểm soát bù"]
~~~

Trong thực tế, việc chặn đăng nhập, thu hồi phiên và cập nhật provisioning có thể thực hiện **song song** để giảm độ trễ. Sơ đồ chỉ nhấn mạnh các lớp phải bao phủ và việc không được tự tuyên bố thành công trước readback.

## 13. Kiểm thử SSO session

Kiểm thử phải bao gồm **positive path**, **negative path**, lỗi phân tán và các trường hợp JML. Nên dùng danh tính thử, client và ứng dụng thử được phép, tránh làm thay đổi phiên hoặc quyền của người dùng sản xuất.

### Ma trận kiểm thử

| ID | Kịch bản | Kết quả mong đợi |
| --- | --- | --- |
| SSO-SESSION-01 | Đăng nhập CRM lần đầu, chưa có IdP session. | IdP xác thực/MFA; CRM tạo session cho đúng User. |
| SSO-SESSION-02 | Mở Wiki khi IdP session còn và đủ assurance. | Có thể SSO không nhập lại mật khẩu; Wiki kiểm tra đúng subject/issuer. |
| SSO-SESSION-03 | IdP session hết hạn, CRM session còn. | Hành vi theo policy CRM; không kết luận tự động CRM hết phiên. |
| SSO-SESSION-04 | App cookie đã hết hạn nhưng IdP session còn. | RP có thể bắt đầu SSO lại; không bypass security checks. |
| SSO-SESSION-05 | Logout tại CRM. | CRM session bị hủy; phạm vi logout IdP/ứng dụng khác đúng cam kết. |
| SSO-SESSION-06 | Logout từ IdP; RP hỗ trợ back-channel logout. | RP xác thực logout event và thu hồi đúng session/subject. |
| SSO-SESSION-07 | Logout token/event bị sửa hoặc từ issuer khác. | Bị từ chối; không hủy nhầm session của User khác. |
| SSO-SESSION-08 | Cookie session cố định trước khi login. | Sau login không tái sử dụng session ID dễ bị chiếm đoạt. |
| SSO-SESSION-09 | Access token hết hạn, sai audience. | API từ chối theo validation policy. |
| SSO-SESSION-10 | Mover đổi phòng ban, app còn claim cũ. | Quyền cũ bị ngăn theo giới hạn chính sách; app không chỉ tin stale claim. |
| SSO-SESSION-11 | Step-up cần cho admin console. | Phiên assurance thấp không tự đủ quyền. |
| SSO-SESSION-12 | Leaver có hiệu lực trong khi User đang có 3 app sessions. | Chặn sign-in mới, xử lý session/token theo từng app và đo residual access. |
| SSO-SESSION-13 | Leaver xong, retry của Joiner chạy lại. | Không bật lại User/phiên hoặc entitlement cũ. |
| SSO-SESSION-14 | Token cũ của API dùng sau khi IdP logout. | Hành vi đúng token lifetime/revocation policy; nếu vượt giới hạn thì fail. |
| SSO-SESSION-15 | SAML assertion phát lại hoặc sai audience. | SP không tạo phiên trái phép. |
| SSO-SESSION-16 | Hai phiên đăng nhập song song, logout một phiên. | Không lẫn subject, session ID hoặc phạm vi logout. |
| SSO-SESSION-17 | SCIM User disabled, app còn local password. | Leaver test phát hiện và xử lý đường local auth riêng. |
| SSO-SESSION-18 | IdP hoặc SCIM API timeout trong quá trình thu hồi. | Trạng thái per-target PENDING/FAILED, retry có giới hạn và readback. |

### Test case theo Given–When–Then

~~~gherkin
Feature: SSO sessions follow IAM lifecycle

  Scenario: Joiner account is prepared but not yet active
    Given an identity is pending activation
    And the IdP and CRM accounts are pre-provisioned
    When the user attempts to start a business SSO session
    Then business access is denied by the effective-date policy
    And no authorized CRM session is established

  Scenario: Mover cannot keep access from an old role
    Given the user has a valid SSO session with role SupportAdmin
    And an authoritative Mover event removes SupportAdmin
    When the user requests a SupportAdmin-only resource
    Then the request is denied after required policy convergence
    And the stale permission is reported and reconciled

  Scenario: Leaver cannot start a new session
    Given an authoritative Leaver event has become effective
    When the user attempts SSO into CRM
    Then the IdP denies authentication according to policy
    And existing application sessions are evaluated for revocation
    And all residual access is measured against the required boundary
~~~

Ví dụ là **đặc tả hành vi**, không phải mã test cho một nhà cung cấp cụ thể. Khi triển khai, cần mô hình hóa policy rõ ràng để tránh các assertion mơ hồ như “phiên phải hết ngay” trong hệ thống không có cơ chế revoke tức thời nhưng lại tuyên bố đạt.

### Cách kiểm thử thực tế thay vì chỉ xem log

1. Tạo phiên IdP và phiên app ở các trình duyệt/thiết bị giả lập riêng biệt.
2. Ghi thời điểm phát session, token, ID issuer/subject, chính sách và quyền ban đầu.
3. Phát sự kiện JML hoặc thay đổi policy thông qua nguồn test đáng tin cậy.
4. Thực hiện các request được phép tới tài nguyên thử trước và sau mốc hiệu lực.
5. Kiểm tra đăng nhập mới, cookie session cũ, refresh token, access token và các credential ngoài SSO theo phạm vi.
6. Đọc lại trạng thái IdP và từng ứng dụng, liên kết với correlation ID.
7. Đo **thời gian tồn dư thực tế** và so với giới hạn chính sách.
8. Đưa kết quả không thể xác minh vào **UNVERIFIED/INCOMPLETE**, không dùng PASS tổng để che lỗi.

## 14. Giám sát và kiểm toán session

Một hệ thống SSO thường trải qua nhiều đường log. Để điều tra, cần liên kết được sự kiện giữa **IdP, RP/SP, provisioning engine và ứng dụng/API** mà không tiết lộ secret.

### Dữ liệu audit hữu ích

| Dữ liệu | Mục đích |
| --- | --- |
| Identity ID và nguồn | Nối phiên với đúng chủ thể HR/IAM. |
| Issuer, subject, clientId/SP entityID | Xác định phạm vi và trust relationship. |
| Session reference / correlation ID | Liên kết sự kiện trên các hệ thống mà không log cookie hoặc token. |
| Authentication method/context | Giải thích mức bảo đảm và step-up đã thực hiện. |
| CreatedAt, lastActivityAt, expiresAt | Phân tích lifetime và timeout. |
| Logout/revoke time, verifiedAt | Đo thời gian chấm dứt truy cập thực tế. |
| JML event, sourceVersion, effectiveAt | Phân biệt session hợp lệ với phiên sau Mover/Leaver. |
| Target và account local ID | Truy vết ứng dụng chưa hủy phiên. |
| Result và failure reason | Xác định partial failure, retry, unknown state. |

Ví dụ event nội bộ khái niệm:

~~~json
{
  "eventType": "SSO_SESSION_REVOKE_CHECK",
  "identityId": "ID-LAN-2041",
  "sourceKey": "HRIS:EMP-2041",
  "lifecycleEvent": "LEAVER",
  "sourceVersion": 53,
  "effectiveAt": "2026-12-01T17:00:00+07:00",
  "issuer": "https://id.example.org",
  "subjectRef": "idp-user-551",
  "application": "CRM",
  "sessionRef": "crm-session-redacted-ref",
  "action": "REVOKE_APP_SESSION",
  "observedResult": "REVOKED_VERIFIED",
  "verifiedAt": "2026-12-01T17:00:15+07:00",
  "correlationId": "leaver-2041-v53"
}
~~~

Đây là **schema minh họa**, không phải định dạng chuẩn của OIDC, SAML hoặc SCIM. Không lưu **cookie session, mật khẩu, khóa riêng, OTP, recovery code, ID/access/refresh token nguyên vẹn** trong log hoặc ticket. Cần hạn chế quyền xem, bảo vệ tính toàn vẹn và có chính sách lưu giữ.

### Các chỉ số vận hành

| Chỉ số | Ý nghĩa |
| --- | --- |
| **Active sessions by user/app** | Phát hiện phiên không hợp lệ hoặc vượt chính sách concurrency. |
| **Session lifetime distribution** | Đánh giá idle/absolute timeout có được thực thi như thiết kế. |
| **SSO reauthentication rate** | Kiểm tra trải nghiệm và hành vi xác thực lại. |
| **Step-up compliance** | Những hành động nhạy cảm đã yêu cầu assurance phù hợp hay chưa. |
| **Leaver session revocation delay** | Từ effectiveAt tới khi các phiên trong phạm vi không còn truy cập được. |
| **Residual active session count** | Phiên tồn tại sau Leaver hoặc suspension ngoài giới hạn. |
| **Logout propagation failures** | Tỷ lệ RP/SP không áp dụng logout event trong hạn. |
| **Stale claims/permission incidents** | Quyền cũ được dùng sau Mover vì cache/session/token. |
| **Unknown/unverifiable sessions** | Những đích chưa có API hoặc bằng chứng để khẳng định thu hồi. |
| **Stale reactivation attempts** | Retry Joiner/Mover cũ có nguy cơ bật lại access sau Leaver. |

Ngưỡng cảnh báo và thời hạn cần được xác định theo **mức nhạy cảm**, khả năng kỹ thuật và chính sách tổ chức; không áp một con số chung cho mọi hệ thống.

## 15. Tình huống thực hành

### Tình huống A — Đã logout CRM nhưng Wiki vẫn đăng nhập

**Bối cảnh:** Lan đăng nhập CRM và Wiki qua cùng IdP. Lan bấm logout ở CRM, sau đó mở Wiki vẫn vào được mà không đăng nhập lại.

**Câu hỏi:** Đây có nhất thiết là lỗi bảo mật không?

**Gợi ý:** Chưa chắc. Nếu CRM chỉ thực hiện **local logout**, IdP và Wiki có thể còn phiên độc lập. Cần kiểm tra sản phẩm có tuyên bố “logout tất cả ứng dụng” hay không; nếu có thì phải kiểm thử RP-initiated/front-channel/back-channel logout hoặc SAML SLO theo cấu hình và ghi kết quả từng đích.

### Tình huống B — IdP session hết hạn, CRM vẫn hoạt động

**Bối cảnh:** IdP yêu cầu xác thực lại sau tám giờ nhưng cookie CRM có absolute lifetime mười hai giờ. Lan vẫn dùng CRM dù phiên IdP đã hết.

**Câu hỏi:** Cần đánh giá điều gì?

**Gợi ý:** Kiểm tra RP session policy, độ nhạy tài nguyên, cơ chế reauthentication/step-up và cách CRM kiểm soát lifetime. IdP session timeout không tự hủy CRM session; chính sách phải xác định hành vi này có được chấp nhận không.

### Tình huống C — Mover nhưng role cũ còn trong session

**Bối cảnh:** Lan chuyển từ Support sang Finance. IdP và SCIM đã bỏ SupportAdmin nhưng một JWT tại API còn role SupportAdmin và còn hạn.

**Câu hỏi:** Vấn đề ở authentication hay authorization?

**Gợi ý:** JWT có thể vẫn hợp lệ về mật mã, nhưng authorization từ claim cũ không còn phù hợp. Cần đánh giá token lifetime, policy lookup, cache invalidation, denylist/revocation khả dụng, và test effective permission sau Mover.

### Tình huống D — Leaver bị khóa IdP nhưng còn refresh token

**Bối cảnh:** HR phát Leaver lúc 17:00. IdP chặn login mới, nhưng một native client vẫn có refresh token.

**Câu hỏi:** Có thể tuyên bố offboarding hoàn tất không?

**Gợi ý:** Cần thử theo phạm vi được phép xem refresh token có còn đổi được không, xử lý session/token revocation theo hỗ trợ và đánh giá access token còn hạn. Cũng cần kiểm tra app session và quyền cục bộ; chưa đủ bằng chứng thì không được kết luận thu hồi toàn bộ.

### Tình huống E — Hai tài khoản cùng email tại hai tenant

**Bối cảnh:** Một ứng dụng liên kết SSO account bằng email, trong khi hai tenant có cùng email danh nghĩa.

**Câu hỏi:** Rủi ro nào có thể xảy ra?

**Gợi ý:** Account misbinding hoặc truy cập nhầm tenant. RP phải liên kết theo issuer/subject, tenant và mapping có thẩm quyền; không chỉ dựa vào email hoặc displayName.

### Tình huống F — Leaver đến khi OIDC callback đang xử lý

**Bối cảnh:** User bắt đầu login trước Leaver. Trong lúc RP xử lý authorization code callback, nguồn IAM cập nhật TERMINATED.

**Câu hỏi:** Cần làm gì để không tạo đường truy cập mới?

**Gợi ý:** RP/IdP phải áp trạng thái và chính sách hiện hành ở điểm thích hợp, không chỉ tin kết quả đăng nhập được bắt đầu trước mốc. Sử dụng version/event guard, session invalidation và readback để bảo đảm không có session trái chính sách.

## 16. Câu hỏi tự kiểm tra

**1. IdP session và RP session có phải cùng một phiên không?**

Không. IdP quản lý phiên xác thực trung tâm; RP/SP có thể tạo phiên riêng với cookie, timeout và cơ chế thu hồi độc lập.

**2. Khi IdP session hết hạn, mọi ứng dụng SSO có tự đăng xuất tức thì không?**

Không mặc định. Ứng dụng có thể tiếp tục dùng app session của mình tới khi hết hạn hoặc bị thu hồi qua cơ chế tích hợp.

**3. Access token và ID token trong OIDC có thể dùng thay nhau không?**

Không nên. ID token dành cho kết quả định danh/xác thực tại RP; access token dành cho Resource Server với audience/scope tương ứng.

**4. Logout ở CRM có chắc chắn chấm dứt cả Wiki session không?**

Không nếu không có cơ chế logout liên thông được hỗ trợ, cấu hình và kiểm chứng tại Wiki.

**5. Vì sao một JWT hợp lệ về chữ ký vẫn có thể gây rủi ro sau Mover?**

Vì role/department trong token là snapshot lúc phát hành; quyền hiện tại có thể đã thay đổi và cần kiểm tra authorization theo chính sách mới.

**6. SCIM active=false có chứng minh mọi session/token đã hết hiệu lực không?**

Không. SCIM quản lý account/Group theo khả năng đích; app-local session, refresh/access token hoặc PAT có thể cần thu hồi riêng.

**7. Khi người dùng nghỉ việc nhưng job Joiner cũ được retry, điều gì phải ngăn account mở lại?**

Trạng thái vòng đời mới nhất, sourceVersion/effectiveAt, idempotency và kiểm soát ghi có điều kiện, kèm reconciliation.

**8. Một service principal dùng client credentials có nên dùng chính sách cookie session dành cho browser không?**

Không mặc định. Danh tính máy cần chính sách riêng về issuer, token/credential, scope, rotation, trust relationship và vòng đời workload.

**9. Vì sao phải kiểm tra RP session sau logout ở IdP?**

Vì RP có thể tiếp tục chấp nhận cookie riêng; chỉ việc IdP trả thành công không chứng minh app session hoặc token tại Resource Server đã bị thu hồi.

## Ghi nhớ

- **SSO session không phải một phiên duy nhất.** IdP session, RP/SP session, ID token, access token và refresh token có vai trò, phạm vi và thời hạn khác nhau.
- **OIDC/SAML** liên kết kết quả xác thực từ IdP sang ứng dụng; RP/SP vẫn phải xác minh đúng subject/issuer, bảo vệ session và thực thi authorization.
- **Cookie an toàn, timeout, reauthentication, MFA step-up, CSRF defense, session rotation và logout có kiểm chứng** là những thành phần quan trọng của quản lý phiên.
- **Logout và khóa IdP** không mặc nhiên kết thúc mọi phiên, token hoặc credential của ứng dụng; **SCIM active=false** cũng không chứng minh toàn bộ quyền đã mất.
- **Joiner** không được mở phiên nghiệp vụ trước ngày kích hoạt; **Mover** không được duy trì quyền cũ qua token/cache; **Leaver** phải chặn login mới và thu hồi/kiểm soát phần tồn dư.
- **RBAC/ABAC, PAM, sourceVersion, idempotency, readback và audit** giúp giữ đúng quyền theo vòng đời, phát hiện lỗi đồng bộ và giảm truy cập tồn dư xuyên hệ thống SSO.
