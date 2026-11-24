# SSO entry point: điểm bắt đầu đăng nhập một lần trong vòng đời danh tính IAM

Trong **Single Sign-On (SSO)**, **entry point** là điểm người dùng hoặc ứng dụng **bắt đầu một luồng truy cập có sử dụng SSO**: chẳng hạn mở URL của ứng dụng, chọn một ô ứng dụng trên cổng Identity Provider (IdP), truy cập deep link tới tài nguyên hoặc dùng trang đăng nhập tập trung của doanh nghiệp. Entry point ảnh hưởng tới **cách tìm đúng IdP, cách khởi tạo yêu cầu xác thực, cách lưu trạng thái điều hướng và cách đưa người dùng trở lại tài nguyên được phép**.

Ví dụ, nhân viên mở `https://reports.example.invalid/` và được chuyển tới IdP để xác thực; người khác mở cổng nhân viên, chọn ô “Reports”, rồi vào cùng ứng dụng; một người nữa nhấn đường dẫn tới báo cáo được chia sẻ trong email. Ba hành trình có thể đưa tới **cùng cơ chế xác thực**, nhưng khác nhau ở **ai khởi phát luồng**, **trạng thái phiên**, **URL cần quay về** và **rủi ro phải kiểm soát**.

Bài thuộc chương **SSO** của module quản lý vòng đời danh tính **Identity and Access Management (IAM)** theo mô hình **Joiner–Mover–Leaver (JML)**. Nội dung làm rõ entry point trong kiến trúc **IdP, SAML/OIDC, SCIM, RBAC/ABAC**, cách kết nối account/entitlement ở ứng dụng, xử lý đăng nhập và phiên, cùng trách nhiệm kiểm toán để **không để quyền truy cập tồn dư** khi nhân viên thay đổi vai trò hoặc rời tổ chức.

> **Trọng tâm:** Entry point là **nơi bắt đầu hành trình đăng nhập**, không phải bằng chứng danh tính, không tự cấp quyền, cũng không bảo đảm ứng dụng đã được provision account. Hệ thống phải kiểm tra xác thực và phân quyền ở những lớp có thẩm quyền.

## 1. SSO entry point là gì?

### 1.1. Phân biệt “điểm vào” với các endpoint giao thức

Một hệ thống SSO có thể có nhiều URL phục vụ các mục đích khác nhau. Không nên gọi tất cả là “trang đăng nhập”:

| Thành phần | Vai trò | Ví dụ minh họa |
| --- | --- | --- |
| **Application entry point** | URL người dùng mở để vào ứng dụng; có thể khởi phát đăng nhập SSO khi chưa có session. | `https://reports.example.invalid/` |
| **Deep-link entry point** | Đường dẫn tới tài nguyên cụ thể, đòi hỏi bảo toàn ý định truy cập qua luồng đăng nhập. | `https://reports.example.invalid/reports/quarterly` |
| **IdP portal / app launcher** | Cổng hiển thị ứng dụng đã được cấu hình hoặc được người dùng phép truy cập. | Cổng ứng dụng nội bộ có ô “Reports”. |
| **IdP SSO endpoint / OIDC authorization endpoint** | Endpoint giao thức nhận yêu cầu xác thực/ủy quyền từ ứng dụng hoặc bên khởi phát phù hợp. | `https://login.example.invalid/.../authorize` |
| **SAML Assertion Consumer Service (ACS)** | Endpoint tại Service Provider (SP) nhận SAML response theo cấu hình. | `https://reports.example.invalid/saml/acs` |
| **OIDC redirect URI/callback** | Endpoint tại Relying Party (RP) nhận authorization response trong luồng OIDC/OAuth. | `https://reports.example.invalid/oidc/callback` |
| **Account activation/invitation link** | Đường dẫn hỗ trợ onboarding hoặc mời thiết lập account; có thể dẫn tiếp tới SSO. | `https://reports.example.invalid/activate` |
| **Logout endpoint** | Điểm xử lý thoát phiên theo ứng dụng/IdP hoặc cơ chế federation. | `https://reports.example.invalid/logout` |

Tất cả URL trên **chỉ mang tính minh họa**, dùng miền `example.invalid`, không phải địa chỉ thật. Trong triển khai thực tế, phải kiểm tra **issuer, entity ID, client ID, redirect URI, ACS, tenant và cấu hình trust** của từng ứng dụng.

**Không nhầm:** OIDC **authorization endpoint** nằm ở Authorization Server/OpenID Provider, còn **redirect URI** là nơi client nhận response; với SAML, **SSO service endpoint** thường nằm ở IdP còn **ACS** nằm ở SP. Người dùng thông thường không cần tự điền URL của callback/ACS để bắt đầu đăng nhập.

### 1.2. SSO entry point không phải “một địa chỉ cố định duy nhất”

Một tổ chức có thể hỗ trợ đồng thời:

- Người dùng mở **URL ứng dụng** trước và được chuyển tới IdP.
- Người dùng mở **portal IdP**, chọn ứng dụng.
- Người dùng mở **deep link**, được chuyển tới IdP rồi quay lại đúng tài nguyên sau khi được phép.
- Người dùng được hướng dẫn vào **enterprise access portal** có khả năng chọn IdP/tenant thích hợp.
- Ứng dụng mobile/desktop bắt đầu một luồng đăng nhập qua trình duyệt hệ thống theo cơ chế hỗ trợ.
- Một số ứng dụng legacy chỉ hỗ trợ một loại entry point hoặc giao thức xác thực liên kết riêng.

Vì vậy, khi hỏi “entry point của SSO là gì?”, cần xác định **ứng dụng nào**, **giao thức nào**, **ai khởi phát**, **từ thiết bị nào** và **lý do truy cập**. Một URL cổng IdP có thể là trải nghiệm người dùng chính nhưng không thay thế logic xử lý callback/token của ứng dụng.

## 2. Các kiểu bắt đầu SSO thường gặp

| Kiểu | Người khởi phát | Hành trình tổng quát | Khi nào phù hợp |
| --- | --- | --- | --- |
| **SP-initiated SAML SSO** | Người dùng vào ứng dụng/SP trước. | SP tạo AuthnRequest → IdP xác thực → SP nhận/kiểm tra response. | Ứng dụng SAML có khả năng tạo yêu cầu theo phiên. |
| **IdP-initiated SAML SSO** | Người dùng vào portal IdP rồi chọn ứng dụng. | IdP gửi SAML response tới ACS đã cấu hình; có thể không có AuthnRequest trước đó. | Hệ thống hỗ trợ kiểu khởi phát từ IdP, với kiểm soát bổ sung thích hợp. |
| **RP-initiated OIDC login** | Ứng dụng/RP khởi tạo authorization request. | RP đưa browser tới authorization endpoint → IdP xác thực → redirect về RP → RP kiểm tra token. | Mô hình OIDC phổ biến cho web/app. |
| **Portal-launched OIDC** | Người dùng chọn ô ứng dụng ở portal. | Portal điều hướng tới entry URL của RP → **RP khởi tạo luồng OIDC bình thường**. | Giữ trải nghiệm “bấm từ IdP” mà vẫn có state/nonce/PKCE do RP quản lý. |
| **Deep link** | Một đường dẫn tới nội dung cụ thể. | Ứng dụng lưu trạng thái điều hướng → xác thực → kiểm tra quyền → mở tài nguyên. | Báo cáo, ticket, trang dự án có URL chia sẻ được. |
| **Home realm discovery / IdP discovery** | Người dùng hoặc chính sách chọn miền danh tính. | Xác định tổ chức/tenant/IdP tin cậy → bắt đầu giao thức tương ứng. | Ứng dụng đa doanh nghiệp hoặc nhiều IdP. |

**SAML IdP-initiated không giống “OIDC IdP gửi ID token bất ngờ tới ứng dụng”.** Với OIDC, mô hình thông thường đòi hỏi RP chủ động tạo yêu cầu, trạng thái chống CSRF và kiểm tra callback. Một portal có thể đóng vai trò **launcher**, nhưng không nên suy ra ứng dụng được phép chấp nhận một ID token không gắn với yêu cầu do mình tạo.

## 3. SP-initiated SAML: vào ứng dụng trước

Trong **Service Provider (SP)-initiated SAML SSO**, người dùng bắt đầu tại ứng dụng. Nếu chưa có session hợp lệ, SP tạo **AuthnRequest** và điều hướng browser tới SAML SSO endpoint của IdP. IdP thực hiện xác thực theo chính sách, sau đó trả một **SAML Response** tới ACS của SP.

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant B as Trình duyệt
    participant SP as Ứng dụng / SP
    participant IDP as IdP
    U->>B: Mở URL ứng dụng hoặc deep link
    B->>SP: GET tài nguyên
    SP->>SP: Tạo yêu cầu SAML + lưu trạng thái
    SP-->>B: Redirect tới IdP kèm AuthnRequest
    B->>IDP: Gửi yêu cầu đăng nhập SAML
    IDP->>IDP: Kiểm tra account, MFA, session, policy
    IDP-->>B: SAML Response tới ACS
    B->>SP: POST SAML Response tới ACS
    SP->>SP: Kiểm tra chữ ký, issuer, audience, thời gian, InResponseTo khi có
    SP->>SP: Ánh xạ subject với account và tạo session
    SP-->>B: Mở tài nguyên theo quyền và return path hợp lệ
~~~

### 3.1. Ý nghĩa của “SP khởi phát”

SP biết người dùng **đang muốn vào ứng dụng/tài nguyên nào**, có thể giữ **request ID**, cấu hình IdP được phép sử dụng và thông tin phiên. Khi IdP trả response, SP có căn cứ đối chiếu **InResponseTo** với yêu cầu trước đó nếu profile/triển khai áp dụng.

Một luồng triển khai an toàn phải kiểm tra đúng các điều kiện SAML phù hợp: chữ ký theo cấu hình trust, issuer, audience, recipient/destination, thời gian hợp lệ, request correlation nếu có, subject và các kiểm soát chống replay cần thiết. Không suy ra chỉ vì browser đã qua IdP thì mọi assertion đều đáng tin.

### 3.2. Deep link qua SAML và RelayState

Khi một người muốn mở `/reports/quarterly`, ứng dụng có thể lưu đường dẫn cần quay về trong **state phía server** và dùng một giá trị `RelayState` phù hợp để liên kết luồng. Sau khi xác thực, SP khôi phục ý định điều hướng **nếu đường dẫn hợp lệ** và người dùng **có quyền** với báo cáo.

**RelayState không phải một quyền truy cập** và không nên được tin như URL đích tự do. Nếu ứng dụng chuyển người dùng tới giá trị RelayState không kiểm tra, có thể phát sinh **open redirect**, đánh cắp luồng đăng nhập hoặc điều hướng người dùng đến trang giả.

### 3.3. Những lỗi điển hình ở SP entry

- URL ứng dụng không được khai báo cho đúng SAML connection/tenant.
- SP tạo AuthnRequest sai issuer, ACS, NameID format hoặc binding so với cấu hình thực tế.
- IdP đã thay đổi chứng chỉ ký nhưng SP chưa cập nhật trust.
- SP không thể tìm account tương ứng với NameID/attribute đã xác minh.
- Cookie phiên mất hoặc SameSite/cross-site flow không tương thích cấu hình.
- Deep link không được bảo toàn, hoặc ứng dụng từ chối nó vì không đủ quyền.

Các lỗi này có thể đều hiện thành “SSO failed”, nhưng cần phân biệt **protocol failure**, **account linking failure** và **authorization denial** trước khi thay đổi chính sách.

## 4. IdP-initiated SAML: bắt đầu từ cổng ứng dụng

Với **IdP-initiated SAML**, người dùng truy cập portal IdP, xác thực nếu cần rồi bấm một ô ứng dụng. IdP tạo SAML response cho SP theo cấu hình, thường **không có AuthnRequest do SP tạo trước đó**.

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant P as Portal / IdP
    participant B as Trình duyệt
    participant SP as Ứng dụng / SP
    U->>P: Mở portal và xác thực
    U->>P: Chọn ô ứng dụng
    P->>P: Xác định SP, policy, assertion hợp lệ
    P-->>B: Form/response tới ACS đã cấu hình
    B->>SP: Gửi SAML Response
    SP->>SP: Kiểm chứng issuer, chữ ký, audience, thời gian, recipient, replay
    SP->>SP: Ánh xạ account và kiểm tra session/quyền
    SP-->>B: Mở trang đích hợp lệ
~~~

### 4.1. Điểm khác biệt về correlation

Vì SP có thể không tạo AuthnRequest, nó có thể **không có request ID để đối chiếu InResponseTo**. Đây là một khác biệt an ninh quan trọng so với SP-initiated flow. Không được tắt toàn bộ kiểm tra SAML để hỗ trợ khởi phát từ IdP; cần quyết định rõ **có cho phép unsolicited response không**, chỉ nhận từ **IdP đã được đăng ký**, kiểm tra đầy đủ các điều kiện khác và thực hiện kiểm soát replay, session và điều hướng phù hợp.

Một số ứng dụng không hỗ trợ hoặc chủ trương **vô hiệu hóa IdP-initiated SAML** vì đặc điểm rủi ro/khả năng correlation. Tổ chức nên chọn kiểu khởi phát theo đánh giá bảo mật và tính tương thích, không coi việc có ô ứng dụng trên portal là lý do bắt buộc phải chấp nhận unsolicited SAML response.

### 4.2. Portal có hiển thị ứng dụng không đồng nghĩa người dùng được phép sử dụng

Portal có thể **ẩn hoặc hiện ô ứng dụng** dựa trên nhóm/thuộc tính. Tuy nhiên, đây chủ yếu là **điều khiển trải nghiệm hoặc chính sách cấp ứng dụng**; người dùng vẫn có thể truy cập URL trực tiếp. SP/ứng dụng phải **kiểm tra xác thực và quyền ở phía server**, không chỉ dựa vào việc ô ứng dụng có xuất hiện.

Nếu một nhân viên bị gỡ khỏi nhóm cấp ứng dụng, cần xác minh cả **app assignment**, **account/role ở SP** và **session/token đã tồn tại**. Xóa ô khỏi portal không đủ để chứng minh quyền đã bị thu hồi.

## 5. OIDC: ứng dụng/RP khởi tạo phiên đăng nhập

**OpenID Connect (OIDC)** là lớp định danh xây dựng trên OAuth 2.0. Với một ứng dụng web thông dụng, **Relying Party (RP)** bắt đầu từ entry URL của mình và tạo yêu cầu tới authorization endpoint của **OpenID Provider (OP)/Authorization Server**. Trong luồng Authorization Code, OP trả về code tới **redirect URI đã đăng ký**; ứng dụng trao đổi code và kiểm tra kết quả trước khi tạo phiên.

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant RP as Ứng dụng / RP
    participant OP as IdP / OpenID Provider
    U->>RP: Mở URL ứng dụng/deep link
    RP->>RP: Tạo state, nonce khi dùng, PKCE và lưu return path an toàn
    RP-->>U: Redirect tới authorization endpoint
    U->>OP: Bắt đầu authorization request
    OP->>OP: AuthN, MFA, conditional access theo chính sách
    OP-->>U: Redirect tới redirect_uri với authorization code + state
    U->>RP: Gửi callback
    RP->>RP: Kiểm tra state, dùng code + PKCE để lấy tokens
    RP->>RP: Kiểm tra ID token: issuer, audience, signature, thời hạn, nonce nếu áp dụng
    RP->>RP: Ánh xạ subject, tạo session và kiểm tra quyền
    RP-->>U: Mở đường dẫn hợp lệ
~~~

### 5.1. Những giá trị không nên nhầm lẫn

| Thành phần | Công dụng | Lưu ý bảo mật |
| --- | --- | --- |
| **Client ID** | Xác định client/RP đã được đăng ký tại OP. | Không tự nó là một bí mật. |
| **Redirect URI** | Nơi nhận authorization response. | Đăng ký và đối chiếu nghiêm ngặt theo chính sách/giao thức; tránh endpoint tùy ý. |
| **state** | Liên kết callback với request/phiên ban đầu và hỗ trợ chống CSRF. | Giá trị khó đoán, ràng buộc phiên và được kiểm tra khi trở về. |
| **nonce** | Liên kết ID token với yêu cầu, khi profile/flow dùng nonce. | Kiểm chứng trong ID token khi đã gửi nonce; không coi là thay thế state. |
| **PKCE** | Ràng buộc authorization code với bên đã khởi tạo code challenge. | Dùng theo profile hiện đại phù hợp loại client; không được tắt chỉ để sửa callback. |
| **ID token** | Chứa thông tin định danh/Authentication dành cho RP. | Kiểm chứng issuer, audience, chữ ký, thời gian và điều kiện liên quan. |
| **Access token** | Cấp quyền truy cập tài nguyên/API theo scope và policy. | Không dùng ID token thay access token. |
| **RP session cookie** | Duy trì phiên ứng dụng sau khi xác thực thành công. | Quản lý bảo vệ cookie, timeout, logout và chặn quyền khi cần. |

**Đặc biệt:** một ô ứng dụng trên portal IdP có thể dẫn tới **entry URL của RP**, để RP tự phát sinh yêu cầu OIDC và kiểm tra callback. Điều này khác việc OP tùy ý **đẩy ID token** tới RP khi RP chưa tạo luồng; không được tự thiết kế cơ chế đó như một phép thay thế cho login flow đã chuẩn hóa.

### 5.2. Ví dụ authorization request có chú thích

Đây là **minh họa các tham số logic**; giá trị được rút gọn để dễ đọc và không phải URL production có thể dùng nguyên trạng:

~~~text
GET https://login.example.invalid/oauth2/authorize
  ?response_type=code
  &client_id=reports-web
  &redirect_uri=https%3A%2F%2Freports.example.invalid%2Foidc%2Fcallback
  &scope=openid%20profile
  &state=<unpredictable-state>
  &nonce=<request-nonce>
  &code_challenge=<derived-from-code-verifier>
  &code_challenge_method=S256
~~~

Ứng dụng phải quản lý **state, PKCE code verifier, nonce khi sử dụng** trong ngữ cảnh phù hợp, kiểm chứng callback trước khi trao đổi code và không log secret/token. Trong thực tế cần xử lý URL encoding, quản lý session, cookie và ràng buộc đúng issuer/client; ví dụ trên chỉ mô tả khái niệm.

## 6. Deep link: đi vào tài nguyên sau khi hoàn tất SSO

Deep link làm SSO hữu ích hơn: người dùng nhấp một đường dẫn tới dashboard, ticket, báo cáo hoặc màn hình nghiệp vụ và sau khi đăng nhập được đưa về **đúng nơi họ định truy cập**. Tuy nhiên, tính thuận tiện không được thay thế AuthZ.

### 6.1. Mẫu khôi phục return path an toàn

1. Ứng dụng nhận yêu cầu GET `/reports/quarterly`.
2. Nếu chưa có session phù hợp, ứng dụng lưu **return path nội bộ** liên kết với một login transaction, thường ở server-side session hoặc cơ chế trạng thái đã bảo vệ.
3. Ứng dụng bắt đầu SAML/OIDC với các tham số giao thức được tạo chính xác.
4. Sau callback, ứng dụng kiểm chứng response, ánh xạ user, cập nhật phiên.
5. Ứng dụng kiểm tra return path thuộc **danh sách đường dẫn/host được phép**, không phải URL ngoài do client tùy ý đưa vào.
6. Ứng dụng kiểm tra **RBAC/ABAC ở chính tài nguyên đích**; nếu thiếu quyền, trả 403/Access denied phù hợp thay vì mở tài nguyên.

~~~text
Người dùng: GET /reports/quarterly
Ứng dụng: lưu returnPath=/reports/quarterly trong phiên đăng nhập
SSO: xác thực thành công, callback hợp lệ
Ứng dụng: kiểm chứng returnPath hợp lệ trong chính ứng dụng
Authorization: user được phép xem report này?
  Có     -> GET /reports/quarterly
  Không  -> 403, không lộ nội dung báo cáo
~~~

**Không dùng return URL để quyết định quyền.** Một đường dẫn có thể được chia sẻ hợp pháp giữa người có và không có quyền; IAM/ứng dụng vẫn phải áp dụng chính sách tại tài nguyên.

### 6.2. Open redirect và callback injection

Nếu app chấp nhận bất kỳ `returnUrl=https://...` từ client rồi redirect sau login, kẻ tấn công có thể tạo đường dẫn trông như thuộc website doanh nghiệp nhưng dẫn nạn nhân tới trang phishing hoặc nơi không mong muốn. Phòng tránh bằng cách:

- Ưu tiên **relative path** bên trong ứng dụng, chuẩn hóa và kiểm tra trước khi redirect.
- Nếu cần liên miền, dùng **allowlist cụ thể** và không dựa trên so khớp chuỗi thiếu chặt chẽ.
- Giữ return target trong **transaction state** được bảo vệ; không tin một tham số được chỉnh sửa tự do.
- Không nhúng token, secret hoặc code vào return URL không thuộc redirect endpoint được đăng ký.
- Áp dụng AuthZ sau đăng nhập; không cho deep link trở thành đường vòng bỏ kiểm soát.

### 6.3. Deep link vào ứng dụng mobile

Ứng dụng native/mobile thường khởi tạo OIDC qua **trình duyệt hệ thống hoặc user-agent phù hợp**, thay vì tự nhúng form mật khẩu của IdP trong ứng dụng. Cơ chế quay về app có thể dùng app/universal link hoặc redirect URI được đăng ký theo loại ứng dụng. Cần kiểm tra **redirect handling, PKCE, app/link ownership** và không coi custom scheme trùng lặp là bằng chứng duy nhất về danh tính ứng dụng.

Một universal link mở ứng dụng mobile cũng không tự bảo đảm user đã AuthN/AuthZ; app vẫn phải kiểm tra session và quyền đối với tài nguyên của deep link.

## 7. IdP discovery: chọn đúng miền danh tính

Trong tổ chức chỉ có một IdP, entry point có thể cố định. Nhưng với ứng dụng phục vụ nhiều công ty, nhiều tenant hoặc các nhóm nhân viên/đối tác khác nhau, cần cơ chế **Identity Provider discovery** hoặc **home realm discovery**.

Ví dụ, người dùng vào `portal.example.invalid` và chọn miền công ty hoặc nhập thông tin định tuyến như domain email. Hệ thống cần ánh xạ về **IdP đã được đăng ký cho tenant tương ứng**, không được tin mọi issuer do người dùng tự cung cấp.

### 7.1. Cách quyết định IdP cần dựa trên cấu hình có thẩm quyền

- **Tenant/organization ID:** tham chiếu tới cấu hình IdP tin cậy của đúng khách hàng/đơn vị.
- **Verified domain mapping:** domain có thể gợi ý tenant, nhưng phải được tổ chức xác minh và quản lý vòng đời.
- **Business relationship:** HRIS, contractor/sponsor hoặc dữ liệu doanh nghiệp có thể xác định nhóm người được phép dùng một IdP.
- **Policy về federation:** xác định giao thức, issuer, khóa tin cậy, assurance, application mapping và giới hạn truy cập.

**Cảnh báo:** email nhập ở entry point chỉ là một gợi ý định tuyến, **không chứng minh người nhập sở hữu email**. Không để tham số `issuer` hoặc `idpUrl` tùy ý từ browser quyết định nơi ứng dụng gửi thông tin định danh hoặc chấp nhận token.

### 7.2. Rủi ro khi chọn sai IdP/tenant

| Sai lệch | Hậu quả | Kiểm soát |
| --- | --- | --- |
| Người dùng được chuyển tới IdP của tenant khác. | Thông tin cá nhân có thể bị lộ, AuthN thất bại hoặc account bị liên kết sai. | Tenant-to-IdP mapping được quản trị; issuer/tenant kiểm chứng nghiêm ngặt. |
| RP chấp nhận token từ bất kỳ issuer. | Có nguy cơ nhầm token và trust boundary. | Allowlist issuer/cấu hình client, kiểm tra audience và khóa đúng issuer. |
| Email domain được xem là bằng chứng thuộc công ty. | Người dùng tự nhận tổ chức chỉ bằng chuỗi email nhập vào. | Proofing và domain ownership verification ở nguồn có thẩm quyền. |
| Discovery trả quá nhiều thông tin account. | Dễ dò người dùng hoặc tổ chức tồn tại. | Phản hồi trung tính, giới hạn lạm dụng và logging được bảo vệ. |
| Người dùng đổi domain khi Mover. | Entry point đưa nhầm IdP hoặc tạo account trùng. | Identity/account binding ổn định, alias và quy tắc chuyển đổi đã phê duyệt. |

**IdP discovery không giống account provisioning.** Việc biết người dùng nên được chuyển tới IdP nào không có nghĩa account đã được tạo hoặc entitlement ở ứng dụng đã sẵn sàng.

## 8. Entry point và chính sách xác thực của IdP

Ngay cả khi người dùng đến từ cùng một entry URL, quyết định xác thực có thể khác nhau dựa trên **trạng thái phiên, loại ứng dụng, độ nhạy thao tác, thiết bị, rủi ro và chính sách IAM**.

### 8.1. Có phiên IdP không đồng nghĩa được miễn mọi xác thực bổ sung

IdP có thể phát hiện browser đã có session và thực hiện SSO mà không yêu cầu người dùng nhập lại mật khẩu. Tuy nhiên:

- Ứng dụng nhạy cảm có thể yêu cầu **fresh authentication** hoặc **step-up MFA**.
- Một số hành động quản trị cần phương thức **phishing-resistant MFA** hoặc user verification phù hợp.
- Tổ chức có thể yêu cầu đánh giá rủi ro, thiết bị được quản lý, vị trí mạng hoặc assurance cụ thể.
- Ứng dụng phải kiểm tra **authentication context** do IdP cung cấp và ngữ nghĩa được hai bên thống nhất, không tự coi mọi login success là cùng mức bảo đảm.

Với OIDC, yêu cầu như `max_age`, `prompt`, `acr_values` có ý nghĩa theo giao thức và khả năng hỗ trợ của IdP. Với SAML, các tùy chọn như `ForceAuthn` hoặc `RequestedAuthnContext` có thể được dùng theo profile/cấu hình. **Không tự chèn tham số lạ hoặc tin rằng một tham số client yêu cầu là bằng chứng IdP đã thực thi chính sách**; cần kiểm tra kết quả AuthN/claim/context thực tế.

### 8.2. Entry point không được làm suy yếu MFA

Một ứng dụng có thể được mở từ URL trực tiếp, ô portal hoặc deep link, nhưng **chính sách bảo vệ tài nguyên cần nhất quán**. Nếu vào từ portal phải dùng MFA còn vào từ URL trực tiếp chỉ cần mật khẩu do cấu hình sai, người dùng hoặc kẻ tấn công có thể chọn đường yếu hơn.

Để giảm rủi ro, cần:
1. Rà soát chính sách tại IdP/ứng dụng theo **client, tài nguyên, hành động và risk context**, không chỉ giao diện launch.
2. Kiểm tra mọi entry point được hỗ trợ, kể cả direct URL và deep link.
3. Không để bypass authentication khi IdP timeout.
4. Có phương án break-glass riêng, giới hạn và kiểm toán cho trường hợp khẩn cấp, không dùng như lối vào mặc định.

## 9. SSO entry point không thay thế account provisioning và quyền truy cập

Một hệ thống IAM thường có **hai luồng liên quan nhưng độc lập**: **đường đăng nhập** và **đường cấp/quản lý account, entitlement**.

~~~mermaid
flowchart LR
    HR["HRIS / nguồn nhân sự có thẩm quyền"] --> IAM["IAM/IGA: Joiner–Mover–Leaver, policy"]
    IAM --> PROV["Provisioning: SCIM / API / manual"]
    PROV --> APP["Ứng dụng: account + entitlement"]
    IAM --> IDP["IdP: identity, account, policy, nhóm"]
    PORTAL["SSO entry point: app URL / portal / deep link"] --> IDP
    IDP --> AUTH["AuthN: MFA, SAML/OIDC"]
    AUTH --> APP
    APP --> DEC["AuthZ: RBAC/ABAC theo tài nguyên"]
    APP --> AUD["Readback/reconciliation + audit"]
    AUD --> IAM
~~~

Sơ đồ chỉ mô tả quan hệ khái niệm; trong thực tế application URL có thể đi qua browser/SP/RP trước IdP và phần provisioning có thể cập nhật IdP hoặc target theo nhiều thứ tự. Các điểm cần nhớ:

- **SSO** trả lời cách người dùng được xác thực và đưa thông tin xác thực tới ứng dụng.
- **SCIM/API/manual provisioning** quyết định account và nhóm/entitlement ở ứng dụng đích có được tạo/cập nhật đúng hay không, theo năng lực từng target.
- **RBAC/ABAC** áp dụng policy quyền dựa vào role, thuộc tính subject/resource/action/context.
- **IAM/IGA** gắn quyết định cấp/thu hồi quyền với nguồn nhân sự, approval, trạng thái vòng đời và kiểm toán.
- **SSO login success** không tự chứng minh người dùng đã được cấp entitlement hợp lệ.

### 9.1. Trường hợp người dùng đăng nhập thành công nhưng ứng dụng báo “user not found”

Một Joiner có thể đã có account IdP và MFA, trong khi **SCIM provisioning ở ứng dụng thất bại**. Người dùng vào đúng URL và AuthN thành công, nhưng ứng dụng không có target account tương ứng với subject/NameID.

Cách xử lý là kiểm tra:
1. IAM identity/account binding.
2. Cấu hình subject/NameID hoặc OIDC `sub` so với khóa account tại ứng dụng.
3. Trạng thái User provisioning từ SCIM/API/JIT user provisioning nếu được hỗ trợ.
4. Target account ID thực tế và kết quả readback.
5. Entitlement và role được duyệt sau khi account tồn tại.

**Không reset mật khẩu hoặc hạ MFA** để “sửa” lỗi do target thiếu user. Nếu ứng dụng hỗ trợ **Just-in-Time (JIT) user provisioning**, cần có policy và kiểm soát việc tạo user tự động lúc login; JIT user provisioning không tự đồng nghĩa quyền nhạy cảm đã được phê duyệt.

### 9.2. App launcher assignment khác entitlement nghiệp vụ

IdP có thể gán ứng dụng cho nhóm `finance-users`, làm xuất hiện ô Finance Portal. Nhưng bên trong Finance Portal, người dùng có thể chỉ đọc báo cáo thuộc department được phép. Một ô portal là **cửa vào**, không phải **chứng chỉ cho phép xem mọi dữ liệu**.

Khi Mover, một nhóm bị gỡ khiến ô ứng dụng biến mất, nhưng account local hoặc token cũ có thể vẫn tồn tại. IAM phải đối soát entitlement và các phiên liên quan, thay vì chỉ kiểm tra danh sách icon trên portal.

## 10. SSO entry point trong Joiner–Mover–Leaver

### 10.1. Joiner: quyền mở cổng và quyền dùng ứng dụng có thể đến ở các thời điểm khác nhau

Ví dụ một nhân viên mới bắt đầu ngày 01/12:

1. HRIS tạo bản ghi có nguồn, identity reference và ngày hiệu lực.
2. IAM xác minh danh tính, chuẩn bị account IdP/ứng dụng theo policy.
3. Người dùng được hướng dẫn đến **entry URL chính thức**, enroll MFA theo quy trình bảo đảm danh tính.
4. IdP chỉ cho đăng nhập tại thời điểm/trạng thái được phép; app launcher assignment được cấp khi đủ điều kiện.
5. SCIM/API/manual provisioning tạo hoặc liên kết account ở target với entitlement đúng role.
6. Kiểm tra **đường login**, account ở ứng dụng, role và scope độc lập.

Nếu nhân viên mở URL sớm và bị từ chối vì account chưa active, đó có thể là **hành vi đúng chính sách**, không phải “lỗi SSO” cần tắt kiểm soát. Nếu đã đến ngày bắt đầu nhưng app còn thiếu user, cần sửa provisioning/correlation.

### 10.2. Mover: SSO vẫn hoạt động nhưng danh sách ứng dụng và quyền phải thay đổi

Khi nhân viên chuyển từ Operations sang Finance:
- **Identity/account IdP** có thể giữ nguyên.
- Portal có thể thôi hiển thị ứng dụng vận hành và hiện ứng dụng tài chính.
- Nhóm/role/entitlement vận hành phải được thu hồi theo effective time, kể cả direct grants ở ứng dụng nếu không còn căn cứ.
- Quyền tài chính chỉ được cấp theo chính sách, phê duyệt và SoD.
- SSO sessions, ID token hoặc access token đang tồn tại có thể cần đánh giá lại khi thay đổi quyền nhạy cảm.

**Lỗi thường gặp:** chỉ ẩn ô ứng dụng vận hành khỏi portal. Khi người dùng giữ bookmark URL cũ, ứng dụng vẫn cho truy cập vì account/role local chưa được gỡ. Đây là **residual access**, không phải hành vi SSO hợp lệ chỉ vì cửa vào đã bị ẩn.

### 10.3. Leaver: chặn đăng nhập mới và đóng những đường truy cập còn hiệu lực

Khi HRIS xác nhận kết thúc quan hệ lao động:
- IdP account nên được disable/chặn đúng thời điểm theo policy.
- App assignments/group memberships và target accounts/entitlements cần được deprovision.
- Các local login, phiên ứng dụng, access/refresh token hoặc API key có thể còn hiệu lực độc lập và phải được đánh giá/thu hồi theo khả năng đích.
- Kiểm chứng ở cả IdP và target; lưu status, timestamp, error owner.
- Không coi việc xóa icon hoặc portal tile là hoàn tất offboarding.

**Một IdP từ chối AuthN tại entry point là cần thiết nhưng chưa đủ để chứng minh mọi access path đã bị chặn.** Cần reconciliation với ứng dụng, đặc biệt nơi hỗ trợ đăng nhập local hoặc có phiên/credential độc lập.

### 10.4. Rehire, nhà thầu và nhiều quan hệ cùng lúc

Người được tái tuyển có thể có employee identifier mới/cũ theo HRIS. IAM phải xác minh person/account linking trước khi cấp lại SSO, tính entitlement mới theo vai trò hiện tại, không khôi phục quyền cũ tự động. Nhà thầu có sponsor và ngày hết hạn riêng; cổng đăng nhập có thể dẫn tới IdP khác nhưng vẫn cần policy về identity proofing, account expiry và access review.

Một người giữ nhiều assignment hợp lệ không nên mất quyền chỉ vì **một** role bị thay đổi. Desired access cần xét tất cả quan hệ hiệu lực và ngoại lệ có owner/thời hạn; entry point chỉ phản ánh trải nghiệm truy cập sau khi policy được áp dụng.

## 11. Phiên, đăng xuất và quyền còn tồn dư

SSO có thể khiến người dùng truy cập nhiều ứng dụng mà không nhập lại credential, nhưng **phiên tại IdP** và **phiên tại ứng dụng** là hai đối tượng khác nhau. Token OIDC/OAuth cũng có vòng đời riêng.

| Đối tượng | Được quản lý ở đâu? | Điều thường bị hiểu sai |
| --- | --- | --- |
| **IdP session** | IdP hoặc authentication service. | Logout khỏi một ứng dụng chưa chắc xóa toàn bộ session ở IdP. |
| **RP/SP application session** | Ứng dụng. | Disable IdP không chắc tự kết thúc ngay session đã tạo tại ứng dụng. |
| **OIDC ID token** | OP phát hành cho RP. | Không được dùng như access token cho API; có thể chứa thông tin tại lúc phát hành. |
| **Access token** | Authorization server/API ecosystem. | Quyền có thể còn hiệu lực cho tới khi hết hạn/thu hồi tùy enforcement. |
| **Refresh token** | Client/authorization server theo cơ chế đã chọn. | Có thể cho phép tạo access token mới nếu chưa bị thu hồi và policy cho phép. |
| **Local credential/session** | Ứng dụng đích. | Có thể độc lập SSO, đặc biệt trong ứng dụng legacy. |

### 11.1. Logout không phải deprovisioning

**Logout** xử lý phiên theo cơ chế sản phẩm. **Deprovisioning** cập nhật account, role, group, credential và các đường truy cập theo quyết định JML. Với Leaver, chỉ cho người dùng “đăng xuất khỏi portal” không bảo đảm:
- Account tại ứng dụng đã disable;
- Group/role nhạy cảm đã bị thu hồi;
- Refresh token, API key, personal access token đã vô hiệu hóa;
- Người đó không thể dùng local login.

Tùy SAML/OIDC và sản phẩm, có thể có SAML Single Logout, OIDC Front-Channel/Back-Channel Logout hoặc cơ chế session management khác. Mỗi loại có **khả năng và giới hạn thực thi**; không nên khẳng định logout liên kết luôn thành công trên mọi ứng dụng. Với quyền nhạy cảm, cần kiểm chứng chính sách session/token và phối hợp deprovisioning tại target.

### 11.2. Session fixation, replay và cookie

Một entry point an toàn không chỉ kiểm tra token, mà còn cần:
- Bảo vệ cookie phiên (ví dụ `Secure`, `HttpOnly`, chính sách `SameSite` phù hợp với federation flow).
- Làm mới hoặc ràng buộc phiên đúng khi Authentication thay đổi trạng thái.
- Kiểm soát `state`, SAML request correlation và replay.
- Hạn chế session lifetime theo rủi ro; tránh giữ phiên không giới hạn.
- Không chấp nhận callback/token từ issuer/tenant sai.
- Không cho phép open redirect hoặc chuyển token tới một host ngoài.

Những kiểm soát này phải được cấu hình phù hợp browser và giao thức đang dùng; thiết lập `SameSite` tùy tiện có thể phá vỡ SAML POST/SSO callback, nhưng không nên vì thế bỏ toàn bộ bảo vệ cookie hoặc CSRF.

## 12. Entry point cho tài khoản dịch vụ và workload

**Service account** và **workload identity** thường không tương tác theo cách một người mở portal SSO và bấm ô ứng dụng. Job có thể dùng **client credentials, mTLS, certificate hoặc workload identity federation** để lấy token trong một luồng máy–máy phù hợp. Đây là **đường xác thực của workload**, không mặc định là một entry point SSO dành cho con người.

Cần tách:
- **Human IAM identity**: có HR lifecycle, account IdP, MFA, SSO portal và các quyền cá nhân.
- **Workload identity**: có owner, mục đích, credential/trust binding, tài nguyên và quyền truy cập riêng.
- **Ownership relation**: nhân viên hoặc nhóm chịu trách nhiệm cho workload; có thể thay đổi khi Mover/Leaver.

Nếu owner của một service account chuyển vai trò hoặc nghỉ việc, không nên “xóa ô ứng dụng trên portal” rồi coi service đã an toàn. Cần bàn giao owner, thu hồi khả năng quản trị của người cũ, xem secret/token/certificate và đánh giá quyền của workload theo chính sách. Không vô hiệu hóa account dịch vụ đang chạy chỉ vì một owner nhân sự đã rời tổ chức nếu quy trình chưa xác định đúng vòng đời dịch vụ.

## 13. Các nguy cơ bảo mật gắn với điểm bắt đầu SSO

| Nguy cơ | Entry point liên quan | Kiểm soát nên áp dụng |
| --- | --- | --- |
| **Trang portal/IdP giả mạo** | URL đăng nhập hoặc link trong email/chat. | Công bố URL chính thức, xác minh domain/TLS, bảo vệ người dùng bằng MFA chống phishing khi có thể. |
| **Open redirect** | `returnUrl`, deep link, RelayState. | Kiểm tra return target, ràng buộc session, allowlist và không đặt token vào URL không tin cậy. |
| **Login CSRF hoặc response injection** | OIDC callback; SAML unsolicited flow. | State/nonce/PKCE khi áp dụng, kiểm tra origin/trust, request correlation và replay policy. |
| **Issuer/tenant mix-up** | IdP discovery hoặc multi-tenant entry. | Allowlist issuer, validate audience, client và tenant-to-IdP mapping. |
| **Replay assertion/token** | SAML ACS, OIDC callback, token usage. | Thời gian hiệu lực, one-time usage, request correlation và các kiểm soát token phù hợp. |
| **Sai account linking** | Portal launch, SSO subject/NameID mapping. | Dùng identifier có phạm vi rõ; không gán quyền chỉ vì tên/email giống nhau. |
| **Bypass MFA theo một entry khác** | Direct app URL so với portal tile. | Chính sách AuthN theo ứng dụng/tài nguyên, kiểm thử mọi entry path. |
| **Portal tile bị ẩn nhưng quyền còn** | Mover/Leaver. | Deprovision entitlement, đối soát account/role/session tại target. |
| **Token/credential bị ghi log** | Authorization redirect, callback, debug. | Không log secret/token; bảo vệ correlation ID và dữ liệu cá nhân. |
| **Metadata/certificate drift** | SAML federation, IdP rotation. | Owner, lịch cập nhật trust, giám sát và kiểm thử thay đổi theo quy trình. |

### 13.1. “Có đường dẫn chính thức” chưa đủ chống phishing

Một link hiển thị tên công ty trong phần văn bản có thể trỏ tới domain khác. Portal app tile cũng có thể được cấu hình sai. Tổ chức nên **quản trị danh mục application entry point**, xác nhận owner, domain, callback và tenant; thông báo người dùng cách tìm đường chính thức. Với truy cập nhạy cảm, ưu tiên cơ chế xác thực chống phishing phù hợp và bảo vệ session.

### 13.2. Không “sửa lỗi đăng nhập” bằng cách bỏ kiểm chứng giao thức

Khi OIDC callback lỗi `state` hoặc SAML assertion sai audience/chữ ký, giải pháp không phải là tắt những kiểm tra đó. Cần xác định **root cause**: session/cookie, callback URI, issuer, metadata, certificate rotation, clock skew hoặc cấu hình ứng dụng. Một bản vá làm việc đăng nhập “thành công” bằng cách nhận token/assertion không hợp lệ có thể dẫn đến chiếm phiên hoặc nhầm danh tính.

## 14. Thiết kế và vận hành danh mục SSO entry point

Trong doanh nghiệp nhiều ứng dụng, mỗi entry point nên có chủ sở hữu và thông tin cấu hình tối thiểu đủ để vận hành:

| Thuộc tính danh mục | Ví dụ logic | Mục đích |
| --- | --- | --- |
| **Application ID / owner** | `finance-reports` / `team-finance-platform` | Biết ai chịu trách nhiệm cho entry và callback. |
| **Official entry URL** | `https://reports.example.invalid/` | Hướng người dùng tới đúng domain đã được quản trị. |
| **Deep-link support** | `/reports/*` theo rule an toàn | Biết đường nào được phép bảo toàn sau SSO. |
| **SSO protocol** | SAML SP-initiated; OIDC Authorization Code | Xác định cách khởi phát, trust và kiểm chứng. |
| **IdP issuer / tenant** | Issuer đã được xác minh cho tổ chức | Tránh nhầm IdP hoặc tenant. |
| **SAML ACS/entity ID** hoặc **OIDC redirect URI/client ID** | Giá trị đã đăng ký theo sản phẩm | Khớp federation configuration. |
| **Allowed launch methods** | App URL, IdP portal, deep link | Không mở các luồng chưa được đánh giá. |
| **Authentication policy** | MFA/step-up/assurance theo rủi ro | Đảm bảo entry không làm suy yếu bảo vệ. |
| **Account provisioning** | SCIM, API, JIT hoặc manual | Biết account đích được tạo và cập nhật ra sao. |
| **Authorization owner** | Business/data owner | Xác nhận role, group, ABAC và quyền. |
| **Lifecycle hooks** | JML event, expiry, deprovision, review | Xử lý thay đổi hoặc kết thúc quyền đúng thời điểm. |
| **Logging/correlation** | Request ID, auth event, target account ID | Điều tra lỗi và chứng minh trạng thái. |

### 14.1. Runbook khi tích hợp ứng dụng mới

1. Xác định **application owner**, người phê duyệt quyền và nhóm vận hành.
2. Kiểm tra hỗ trợ SAML/OIDC, kiểu launch và khả năng JIT/provisioning.
3. Đăng ký issuer/tenant, client/entity ID, callback/ACS và cấu hình trust đúng phạm vi.
4. Thiết kế **account linking** với IAM identity và application account ID; tránh phụ thuộc duy nhất vào display name.
5. Thiết kế app assignment và entitlement theo **RBAC/ABAC**, đặt mốc JML và owner xử lý lỗi.
6. Kiểm thử **SP/RP-initiated**, portal launch, deep link, URL đã hết quyền, sai tenant và callback không hợp lệ.
7. Kiểm thử MFA/step-up, session expiration, logout và Leaver deprovisioning theo risk.
8. Kiểm tra audit/correlation, retry khi provisioning lỗi và readback trạng thái tại target.
9. Công bố URL chính thức, hướng dẫn hỗ trợ và đường báo cáo phishing.
10. Theo dõi chứng chỉ/secret/trust metadata, lịch rotation và đánh giá access review định kỳ.

**Với SAML IdP-initiated**, kiểm tra xem SP có cho phép unsolicited response không; nếu có, đánh giá rủi ro và cơ chế chống replay/correlation khác phù hợp. **Với OIDC**, portal nên launch RP entry để RP tự tạo transaction và kiểm chứng callback.

## 15. Chẩn đoán lỗi theo điểm bắt đầu

| Người dùng báo lỗi | Lớp cần kiểm tra đầu tiên | Không nên kết luận vội |
| --- | --- | --- |
| Mở URL app nhưng không chuyển tới IdP. | App route/login handler, cấu hình client/SP và session. | Không chắc người dùng nhập sai mật khẩu. |
| Bấm ô portal nhưng ứng dụng không mở. | App launcher target URL, tenant, SAML/OIDC launch method, browser flow. | Chưa chứng minh ứng dụng bị mất quyền. |
| IdP xác thực xong ứng dụng báo lỗi callback. | OIDC state/nonce/PKCE/redirect URI hoặc SAML ACS/audience/issuer/signature. | Không bỏ validation để cho qua. |
| Mở deep link xong bị đưa về trang chủ. | Return path/session transaction và cơ chế redirect. | Không tự cấp quyền để sửa điều hướng. |
| App không tìm thấy user sau login. | Account mapping, SCIM/API/JIT provisioning, subject/NameID. | Không mặc định là AuthN failure. |
| Vào app được nhưng nhận 403 ở báo cáo. | Entitlement và RBAC/ABAC tại tài nguyên. | Không reset password/MFA. |
| Mover không thấy ô app cũ nhưng bookmark vẫn vào được. | Account local, role, group, session/token tại ứng dụng. | Không coi ẩn tile là đã deprovision. |
| Leaver bị IdP từ chối nhưng API token còn gọi được. | Access paths ngoài IdP, token/local credential. | Không coi IdP deny là offboarding hoàn tất. |
| Chỉ một tenant gặp lỗi. | IdP discovery, issuer/tenant mapping và client configuration. | Không thay đổi cấu hình cho tất cả tenant khi chưa xác định phạm vi. |
| Sau rotation certificate, nhiều SP từ chối SAML. | Federation trust, metadata, signature verification và thời gian. | Không tắt kiểm tra chữ ký để xử lý gấp. |

### 15.1. Quy trình điều tra ngắn

~~~mermaid
flowchart TD
    A["Người dùng mở SSO entry point"] --> B{"Ứng dụng có tạo/nhận luồng AuthN hợp lệ?"}
    B -->|Không| C["Kiểm tra launch URL, SP/RP cấu hình, IdP discovery"]
    B -->|Có| D{"IdP AuthN/MFA thành công?"}
    D -->|Không| E["Kiểm tra account JML, credential, MFA, policy, availability"]
    D -->|Có| F{"SP/RP nhận và xác minh response/token thành công?"}
    F -->|Không| G["Kiểm tra issuer, audience, state, chữ ký, ACS/callback, clock"]
    F -->|Có| H{"Application account được liên kết?"}
    H -->|Không| I["Kiểm tra SCIM/API/JIT, subject mapping và target account ID"]
    H -->|Có| J{"Tài nguyên có cho phép truy cập?"}
    J -->|Không| K["Kiểm tra RBAC/ABAC, entitlement, direct grant, policy"]
    J -->|Có| L["Kiểm tra return path an toàn, session và audit"]
~~~

**Bằng chứng cần kết nối:** event HRIS/IGA, identity ID, IdP auth event, issuer/client/entity ID, SP/RP request ID, callback validation result, target account ID, role/permission decision và correlation ID. Không ghi password, mã OTP, full token hoặc private key vào ticket/log.

## 16. Tình huống xuyên suốt: ứng dụng báo cáo doanh nghiệp

**Bối cảnh:** Công ty dùng cổng IdP, ứng dụng **Finance Reports** hỗ trợ OIDC, ứng dụng **Legacy ERP** hỗ trợ SAML, còn provisioning User/Group tại một số target thông qua SCIM. Nhân viên **An** có IAM identity `person-2048` và một account IdP đã liên kết.

### 16.1. Joiner: mở app từ portal

Ngày đầu tiên, An đăng nhập IdP bằng MFA và chọn ô **Finance Reports**. Portal điều hướng tới entry URL của ứng dụng; RP tạo OIDC authorization request, nhận callback, kiểm tra token và tìm application account.

Nhưng ứng dụng trả **“user not provisioned”** vì SCIM tạo user bị lỗi. Lỗi này **không được giải quyết bằng cách tắt MFA hay thay redirect URI tùy tiện**. IAM kiểm tra SCIM job, sửa account mapping, tạo đúng user và quyền theo phê duyệt, rồi readback ứng dụng.

### 16.2. Mover: chuyển từ Finance sang Operations

Sau khi An chuyển vai trò:
- Portal ẩn ô Finance Reports nếu chính sách assignment yêu cầu.
- IAM phải **thu hồi entitlement tài chính** và cấp quyền vận hành được duyệt.
- An vẫn có thể dùng URL bookmark cũ của Finance Reports. Nếu ứng dụng còn role tài chính hoặc session cũ, truy cập có thể vẫn xảy ra.
- Reconciliation phải xác nhận **actual access** ở Finance Reports đã bị chặn đúng policy, không chỉ dựa vào portal.

Đồng thời, nếu An được cấp vai trò quản trị production, IdP/ứng dụng có thể yêu cầu **step-up MFA mạnh hơn**, không được dựa duy nhất vào việc An đến từ cổng IdP.

### 16.3. Leaver: SSO bị chặn nhưng session cũ tồn tại

HRIS xác nhận An rời tổ chức. IAM disable account IdP theo mốc chính sách; An mở lại portal bị từ chối. Tuy nhiên, **Legacy ERP** vẫn có một session cũ hoặc local account. Hệ thống cần:
1. Xác định các account/đường truy cập của An tại ERP.
2. Disable/deprovision và xử lý phiên/token/credential liên quan theo khả năng.
3. Xác minh trạng thái tại ứng dụng và lưu kết quả.
4. Chỉ đóng workflow khi các access path bắt buộc đã bị chặn hoặc ngoại lệ được quản lý theo quy trình.

**Kết luận tình huống:** việc vào bằng app URL, portal hay deep link là điểm bắt đầu luồng SSO; **quyền truy cập thực sự** phụ thuộc trạng thái danh tính, AuthN, account liên kết, entitlement và session tại đích.

### 16.4. Ví dụ sự kiện audit liên kết entry point và quyết định truy cập

Dưới đây là một **schema JSON nội bộ minh họa**, không phải payload chuẩn OIDC, SAML hay SCIM:

~~~json
{
  "eventId": "sso-login-event-8001",
  "correlationId": "login-flow-2048-20261201",
  "entryPoint": {
    "type": "IDP_PORTAL_LAUNCH",
    "applicationId": "finance-reports",
    "requestedPath": "/reports/quarterly",
    "launchProtocol": "OIDC_AUTHORIZATION_CODE"
  },
  "federation": {
    "issuerRef": "corporate-idp",
    "clientId": "finance-reports-web",
    "authenticationResult": "SUCCEEDED",
    "callbackValidation": "PASSED"
  },
  "identity": {
    "identityId": "person-2048",
    "idpAccountId": "idp-user-581",
    "targetAccountRef": "finance-user-882"
  },
  "authorization": {
    "resourceRef": "report-quarterly",
    "result": "DENY",
    "reasonCode": "INSUFFICIENT_ENTITLEMENT",
    "policyRef": "finance-access-policy-v4"
  },
  "lifecycle": {
    "workItemRef": "iam-workflow-991",
    "verificationStatus": "PENDING_RECONCILIATION"
  }
}
~~~

Trong ví dụ, **AuthN thành công nhưng AuthZ từ chối**. Đây không phải dữ liệu “tự mâu thuẫn”: hệ thống nhận diện đúng An nhưng không cho mở báo cáo chưa được phép. Log cần bảo vệ định danh, không chứa token hoặc secret, và giữ lịch sử policy để phục vụ kiểm toán.

## 17. Chỉ số vận hành và sai lầm thường gặp

### 17.1. Chỉ số tham khảo

| Chỉ số | Gợi ý đo | Điều không nên suy ra |
| --- | --- | --- |
| **Entry-point login success rate** | Số luồng bắt đầu từ từng entry point có AuthN + callback hợp lệ ÷ tổng luồng tương ứng. | Không đồng nghĩa ứng dụng đã cấp quyền đúng. |
| **Federation validation error rate** | Tỷ lệ callback/assertion bị từ chối vì trust/state/audience/config. | Không phải mọi lỗi đều do credential người dùng. |
| **Deep-link return success** | Tỷ lệ phiên login hợp lệ quay về đúng internal path đã cho phép. | Không được bỏ qua AuthZ để tăng tỷ lệ. |
| **Portal/app entitlement drift** | Trường hợp tile/assignment khác với account/entitlement thực tế ở target. | Ẩn tile không phải là deprovision. |
| **JML access-block verification** | Sự kiện đến hạn được đối soát tất cả đường truy cập bắt buộc. | Chỉ nhìn IdP authentication denial chưa đủ. |
| **IdP discovery routing accuracy** | Tỷ lệ luồng đi tới issuer/tenant tin cậy đúng cấu hình. | Email domain người dùng nhập không tự xác minh danh tính. |
| **Session closure latency** | Thời gian từ mốc phải chặn đến lúc các session/đường truy cập yêu cầu đã bị vô hiệu hóa. | Đóng ticket không chứng minh session đã hết hiệu lực. |
| **SSO support rework** | Số ticket chẩn đoán nhầm AuthN/SSO/SCIM/AuthZ và phải mở lại. | Không nên tối ưu số lượng bằng cách đóng ticket sớm. |

### 17.2. Những lỗi thiết kế điển hình

| Sai lầm | Hậu quả | Hướng xử lý |
| --- | --- | --- |
| Chỉ công bố portal tile, không quản trị app URL và deep link. | Người dùng dùng bookmark cũ, bỏ qua kiểm soát giao diện hoặc đến nhầm domain. | Inventory entry point và kiểm tra quyền ở server. |
| Coi OIDC có thể nhận ID token tùy ý từ portal mà không tạo transaction. | Thiếu state/nonce/request binding, tăng rủi ro nhầm phiên/CSRF. | Portal launch RP entry; RP khởi phát giao thức và kiểm chứng callback. |
| Cho phép SAML unsolicited response mà không đánh giá rủi ro. | Giảm khả năng request correlation. | Chọn loại flow theo policy, kiểm tra trust/replay/session. |
| Nhầm SAML ACS/OIDC callback với URL người dùng phải mở. | Người dùng gặp lỗi hoặc cấu hình sai. | Tách application entry URL và protocol response endpoint. |
| Chuyển tiếp `returnUrl` tùy ý sau login. | Open redirect hoặc lộ thông tin nhạy cảm. | Relative path/allowlist và trạng thái phiên được bảo vệ. |
| Chỉ ẩn ứng dụng trên IdP portal khi Mover/Leaver. | Entitlement, account hoặc session cũ vẫn dùng được. | Deprovision/reconcile tại target và kiểm tra token/session. |
| Mọi entry đều chuyển tới bất kỳ IdP do người dùng nhập. | Issuer/tenant mix-up, trust sai. | Discovery dựa trên cấu hình được xác minh. |
| Bỏ validation callback để “sửa lỗi SSO”. | Có thể chấp nhận assertion/token không hợp lệ. | Khắc phục metadata, issuer, signature, state và redirect config. |
| Coi SSO AuthN success là business authorization. | Người dùng được xem dữ liệu ngoài phạm vi hoặc thiếu quyền không được xử lý. | App áp dụng RBAC/ABAC và entitlement tại tài nguyên. |
| Dùng SSO entry point của người cho service account. | Workload dùng thông tin đăng nhập con người, khó quản lý secret. | Workload identity và luồng máy–máy phù hợp. |

## 18. Checklist triển khai và bài tập tự kiểm tra

### 18.1. Checklist cho một SSO entry point

- [ ] Xác định **application URL, portal launch URL, deep-link behavior và protocol callback** như các khái niệm khác nhau.
- [ ] Có application owner, issuer/tenant mapping, SP/RP identifier và metadata/trust được quản trị.
- [ ] Phân biệt SP-initiated SAML, IdP-initiated SAML và RP-initiated OIDC; chỉ bật các luồng được policy cho phép.
- [ ] OIDC dùng state/PKCE/nonce khi thích hợp; callback kiểm tra issuer, audience, chữ ký, thời gian và ràng buộc phiên.
- [ ] SAML response kiểm tra issuer, chữ ký, audience, recipient, thời gian, request correlation khi có và chống replay.
- [ ] Deep link/RelayState/return path được bảo vệ, không mở redirect tùy ý hoặc bỏ kiểm tra AuthZ.
- [ ] IdP discovery chỉ dùng issuer/tenant được đăng ký, không nhận tham số IdP từ client làm nguồn tin cậy.
- [ ] Chính sách MFA/conditional access không suy yếu khi người dùng chọn một entry khác.
- [ ] Account provisioning qua SCIM/API/JIT/manual được quản lý độc lập với SSO AuthN.
- [ ] Application account mapping dựa trên identifier tin cậy; RBAC/ABAC kiểm tra quyền tại tài nguyên.
- [ ] Joiner có account/MFA đúng thời điểm; Mover gỡ quyền cũ; Leaver chặn mọi đường truy cập bắt buộc.
- [ ] Đã đánh giá IdP session, app session, local account, access/refresh token và logout/deprovisioning.
- [ ] Có log correlation, actor/owner, policy/version và trạng thái readback/reconciliation phù hợp.
- [ ] Có runbook xử lý lỗi federation, rotation certificate/secret và kiểm thử mỗi loại entry được hỗ trợ.

### 18.2. Bài tập tình huống

**Tình huống A — OIDC tile ở IdP:** Người dùng chọn “Reports” tại portal. Một thiết kế muốn IdP tự gửi ID token tới ứng dụng mà ứng dụng chưa tạo login transaction. Hãy giải thích vì sao nên dùng **portal launch vào RP entry** để RP tự khởi tạo Authorization Code, state và PKCE.

**Tình huống B — Deep link độc hại:** Một link đăng nhập chứa `returnUrl=https://external.example.invalid/`. Hãy xác định nguy cơ open redirect và cách dùng **relative return path hoặc allowlist có ràng buộc phiên** mà vẫn hỗ trợ link tới báo cáo nội bộ.

**Tình huống C — SAML IdP-initiated:** SP nhận một SAML Response không có `InResponseTo`. Đây có luôn là lỗi không? Hãy giải thích khác biệt với SP-initiated và các kiểm tra issuer, audience, thời hạn, chữ ký, replay và policy cần xét trước khi chấp nhận.

**Tình huống D — Mover vẫn vào ứng dụng cũ:** Sau khi chuyển vai trò, ô ứng dụng đã biến mất khỏi portal nhưng bookmark cũ vẫn mở được. Hãy phân biệt **portal visibility**, **app assignment**, **local entitlement**, **session/token** và trình bày cách đối soát.

**Tình huống E — Leaver và phiên còn sống:** IdP từ chối mọi lần đăng nhập mới của nhân viên nghỉ việc, nhưng một session ERP đã có vẫn truy cập được. Hãy xác định lớp nào đã được chặn, lớp nào còn tồn dư và bằng chứng cần có trước khi hoàn tất deprovisioning.

**Tình huống F — Hai IdP:** Ứng dụng phục vụ nhân viên và đối tác. Một người nhập email thuộc domain chưa được xác minh để chuyển hướng tới một IdP tùy ý. Hãy giải thích vì sao **domain hint** không đủ làm trust decision, và mô tả tenant-to-IdP mapping an toàn.

**Điểm cần ghi nhớ:** **SSO entry point** xác định **hành trình bắt đầu đăng nhập**, không phải quyền truy cập. SP-initiated SAML, IdP-initiated SAML, RP-initiated OIDC, portal launch và deep link có các điều kiện giao thức và rủi ro khác nhau. Hãy bảo vệ **trust, callback, state, return path và session**; đồng thời tách biệt **xác thực tại IdP**, **tạo account qua SCIM/API**, **phân quyền RBAC/ABAC** và **thu hồi quyền theo Joiner–Mover–Leaver**. Chỉ khi có readback/reconciliation tại các ứng dụng đích mới có thể kết luận đường truy cập không còn căn cứ đã bị chặn.

