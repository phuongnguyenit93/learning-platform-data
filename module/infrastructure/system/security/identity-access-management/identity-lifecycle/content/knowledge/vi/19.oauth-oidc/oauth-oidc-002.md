# OpenID Connect (OIDC) – xác thực danh tính trên nền OAuth 2.0

## Mục tiêu học tập

Sau bài học, người học có thể:

- Giải thích **OpenID Connect (OIDC)** là gì, vì sao cần một giao thức xác thực trên nền OAuth 2.0 và OIDC khác **OAuth authorization**, **SSO**, **federation**, **identity proofing** và **account provisioning** như thế nào.
- Nhận diện các vai trò **End User, OpenID Provider (OP), Relying Party (RP), Authorization Server, OAuth Client và Resource Server**; hiểu ranh giới tin cậy giữa chúng.
- Trình bày **Authorization Code Flow + PKCE** cùng **state, nonce, code verifier, redirect URI, authorization code, ID token và access token**.
- Phân biệt **ID token, access token, refresh token, phiên OP và phiên RP**; biết cách xác minh những claim cốt lõi trước khi tạo phiên.
- Sử dụng đúng các khái niệm **scopes, claims, UserInfo Endpoint, Discovery và JSON Web Key Set (JWKS)**; hiểu nguồn và độ mới của thuộc tính.
- Mô tả tích hợp OIDC trong ứng dụng Java/Spring Security bằng thư viện phù hợp, không tự viết bộ xác minh giao thức.
- Kết nối OIDC với **Joiner–Mover–Leaver (JML)**, **IdP/SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, kiểm toán, reconciliation** và giảm **quyền truy cập tồn dư**.

## 1. OpenID Connect là gì và giải quyết vấn đề nào?

**OpenID Connect (OIDC)** là một **lớp xác thực danh tính** được xây dựng trên **OAuth 2.0**. OIDC cung cấp cách để ứng dụng xác minh rằng **người dùng đã được một bên cung cấp định danh tin cậy xác thực**, đồng thời nhận một số thông tin chuẩn hóa về người dùng.

Hãy xét một ứng dụng báo cáo nội bộ. Nếu ứng dụng tự quản lý mật khẩu, doanh nghiệp phải vận hành nhiều cơ sở dữ liệu tài khoản, quy trình reset, MFA và kiểm soát khóa khi nhân viên nghỉ việc. Với OIDC, ứng dụng có thể chuyển phần **xác thực người dùng** tới **Identity Provider (IdP)**, xác minh kết quả và tạo phiên ứng dụng theo chính sách của mình.

OIDC thường được sử dụng trong:

- Đăng nhập ứng dụng web, ứng dụng doanh nghiệp và SaaS.
- Đăng nhập trên ứng dụng di động với luồng OAuth/OIDC phù hợp.
- Tích hợp **Single Sign-On (SSO)** giữa nhiều ứng dụng với một IdP.
- Federation giữa tổ chức sở hữu ứng dụng và IdP của đối tác.
- Đánh giá mức/độ mới xác thực khi cần **step-up authentication**.

Trong module **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**, OIDC giúp nối **danh tính đã được xác minh và tạo ở Joiner** với hoạt động đăng nhập; tuy vậy **Mover** vẫn cần thay đổi/thu hồi quyền và **Leaver** phải chấm dứt đường truy cập, bao gồm phiên ứng dụng hoặc token còn hiệu lực. OIDC không tự làm tất cả những việc đó.

### 1.1. Vì sao chỉ OAuth 2.0 chưa đủ để xác thực danh tính?

OAuth 2.0 được thiết kế chủ yếu để **ủy quyền một client truy cập tài nguyên** thay mặt chủ thể hoặc theo quyền của chính client. Một kết quả OAuth có **access token** chưa tự cho ứng dụng biết một cách chuẩn hóa **ai đã đăng nhập** và bằng chứng xác thực người dùng là gì.

Nếu ứng dụng tùy tiện xem một access token bất kỳ là chứng cứ đăng nhập, nó có thể:

- Nhầm **audience**, chấp nhận token được phát cho API hoặc client khác.
- Suy luận sai người dùng từ một trường dữ liệu không được định nghĩa nhất quán.
- Bỏ qua cách kiểm tra thời điểm và bối cảnh xác thực.
- Nhầm quyền truy cập API với quyền thiết lập phiên đăng nhập.

OIDC bổ sung **ID token**, yêu cầu **scope openid**, các quy tắc xác minh và cơ chế lấy claims về chủ thể để RP thực hiện xác thực một cách có thể tương tác giữa các hệ thống.

**Ghi nhớ:** OAuth trả lời chủ yếu câu hỏi *client được phép truy cập gì*; OIDC bổ sung câu trả lời *người dùng được OP xác thực là ai*. Hai câu hỏi liên quan nhưng không đồng nhất.

## 2. Kiến trúc và các vai trò chính

| Vai trò | Trách nhiệm | Ví dụ trong doanh nghiệp |
| --- | --- | --- |
| **End User** | Người sử dụng ứng dụng và được xác thực | Nhân viên, nhà thầu |
| **OpenID Provider (OP)** | Xác thực người dùng, phát ID token và cung cấp thông tin OIDC | IdP doanh nghiệp |
| **Relying Party (RP)** | Ứng dụng dựa vào kết quả xác thực do OP cung cấp | Cổng báo cáo, ứng dụng SaaS |
| **OAuth Client** | Thành phần khởi tạo authorization request và trao đổi token | Web backend, mobile app |
| **Authorization Server** | Cung cấp authorization/token endpoints | Thường cùng nền tảng OP |
| **Resource Server** | API xác minh access token và thực thi authorization | API hóa đơn, API tài liệu |
| **HRIS / nguồn hợp đồng** | Xác nhận quan hệ việc làm, người quản lý, ngày hiệu lực | Hệ thống nhân sự |
| **IGA / Identity Registry** | Quản trị danh tính, gắn account, phê duyệt và vòng đời quyền | Bộ điều phối JML |

**OP** và **RP** là hai vai trò trung tâm trong OIDC. Một hệ thống có thể đồng thời mang nhiều vai trò, nhưng ở mỗi đường tin cậy phải xác định **ai phát token**, **ai nhận**, **ai kiểm** và **ai được quyết định quyền**.

### 2.1. Ranh giới tin cậy

- **Người dùng ↔ OP:** mật khẩu, passkey, MFA, recovery và chính sách xác thực thuộc trách nhiệm của OP.
- **RP ↔ OP:** cấu hình issuer, client ID, redirect URI, endpoint và khóa công khai để kiểm tra kết quả.
- **RP ↔ ứng dụng/API:** phiên người dùng, access token dành cho API và kiểm tra quyền theo tài nguyên.
- **HRIS/IGA ↔ OP/ứng dụng:** dữ liệu nguồn, trạng thái JML, tài khoản và role; đây **không phải** giao thức OIDC tự động xử lý.
- **Ứng dụng ↔ nguồn phê duyệt:** RBAC/ABAC, SoD và approval quyết định quyền thực tế, tách với việc xác thực.

### 2.2. Sơ đồ hệ thống

~~~mermaid
flowchart LR
    HR["HRIS / hợp đồng"] --> IGA["Identity Registry / IGA"]
    IGA -->|"Tạo, đổi, vô hiệu hóa"| OP["OpenID Provider / IdP"]
    IGA -->|"SCIM / API / quyền"| RP["Relying Party"]
    U["Người dùng"] -->|"Truy cập"| RP
    RP -->|"OIDC authorization request"| OP
    OP -->|"Đăng nhập / MFA"| U
    OP -->|"Authorization code, ID token theo luồng"| RP
    RP -->|"Access token đúng audience"| API["Resource Server"]
    RP --> AUD["Audit / session events"]
    API --> AUD
    IGA --> REC["Reconciliation"]
    AUD --> REC
~~~

Các mũi tên biểu diễn **quan hệ logic**: authorization code được chuyển qua trình duyệt trong luồng phù hợp; bước đổi code lấy token thường dùng kênh token endpoint được bảo vệ. Không nên truyền bí mật hoặc token qua kênh tùy tiện chỉ vì sơ đồ có mũi tên giữa hai thành phần.

## 3. OIDC khác OAuth, SSO, federation và provisioning ra sao?

| Khái niệm | Câu hỏi chính | Vai trò trong kiến trúc |
| --- | --- | --- |
| **OAuth 2.0** | Client được ủy quyền truy cập tài nguyên như thế nào? | Authorization và access token |
| **OIDC** | RP xác thực người dùng qua OP như thế nào? | ID token, claims, authentication protocol |
| **SSO** | Người dùng có thể dùng trạng thái đăng nhập ở IdP cho nhiều RP không? | Trải nghiệm đăng nhập liên ứng dụng, thường dùng OIDC/SAML |
| **Federation** | Tổ chức/ứng dụng có thể tin nguồn định danh khác bằng cơ chế nào? | Hợp đồng trust, issuer/claims, bảo đảm và trách nhiệm |
| **Identity proofing** | Danh tính trong hồ sơ được xác lập tin cậy tới đâu? | Quy trình trước hoặc ngoài một phiên OIDC |
| **Provisioning** | User/group/role được tạo và thu hồi tại đâu? | SCIM, API, JIT hoặc thủ công có kiểm soát |
| **Authorization** | Người dùng được làm gì ở tài nguyên cụ thể? | RBAC, ABAC, approval, SoD và chính sách API |
| **Reconciliation** | Quyền/tài khoản thực tế có khớp chính sách không? | Đối soát desired/observed, phát hiện quyền tồn dư |

Ví dụ: nhân viên có thể **đăng nhập OIDC thành công** vào ứng dụng tài chính nhưng không có quyền xem một hóa đơn do RBAC/ABAC từ chối. Ngược lại, nhân viên đã nghỉ có thể còn **phiên ứng dụng cũ** dù IdP không còn cho đăng nhập mới; do đó Leaver không thể chỉ dựa vào cờ user bị disabled ở OP.

## 4. Các khái niệm giao thức cần biết

| Thuật ngữ | Ý nghĩa |
| --- | --- |
| **Issuer (iss)** | Định danh của OP; token và metadata phải khớp miền tin cậy đã cấu hình |
| **Client ID** | Định danh OAuth/OIDC client tại OP |
| **Redirect URI** | Địa chỉ OP chuyển người dùng về RP với kết quả authorization |
| **Authorization Endpoint** | Điểm khởi phát yêu cầu đăng nhập/authorization |
| **Token Endpoint** | Điểm client đổi authorization code lấy token |
| **Authorization Code** | Mã ngắn hạn, dùng để đổi token theo luồng |
| **PKCE** | Cơ chế buộc bên đổi code chứng minh có code_verifier tương ứng |
| **State** | Giá trị gắn phản hồi với yêu cầu ban đầu, giúp chống login CSRF/mix-up |
| **Nonce** | Giá trị được gắn với ID token để chống sử dụng sai kết quả xác thực |
| **Scope** | Phạm vi được yêu cầu; **openid** là scope kích hoạt OIDC |
| **Claim** | Thuộc tính được OP khẳng định về token/chủ thể |
| **ID Token** | Kết quả xác thực có cấu trúc và có thể kiểm chứng dành cho RP |
| **Access Token** | Chứng cứ ủy quyền gọi Resource Server theo đúng mục đích |
| **Refresh Token** | Credential để yêu cầu token mới khi được phép |
| **JWKS** | Tập khóa công khai phục vụ xác minh chữ ký theo cấu hình OP |
| **UserInfo Endpoint** | API để lấy claims người dùng theo access token và phạm vi được cấp |

Không phải hệ thống nào cũng cung cấp tất cả tính năng tùy chọn; cần kiểm tra metadata và thỏa thuận với OP. Tên của endpoint, thuật toán hoặc phương thức xác thực client không nên đoán từ một URL không đáng tin.

## 5. Authorization Code Flow + PKCE

Đây là luồng OIDC quan trọng cho nhiều ứng dụng hiện đại. **RP không nhận trực tiếp một danh tính đã được xác minh chỉ từ redirect**: nó phải xử lý yêu cầu, đổi code và kiểm tra ID token theo giao thức.

~~~mermaid
sequenceDiagram
    autonumber
    actor User as Người dùng
    participant Browser as Trình duyệt
    participant RP as RP / OIDC Client
    participant OP as OpenID Provider

    User->>RP: Mở ứng dụng
    RP->>RP: Tạo state, nonce, code_verifier
    RP-->>Browser: Redirect đến OP với code_challenge
    Browser->>OP: Authorization request có scope=openid
    OP->>User: Xác thực và MFA nếu cần
    User-->>OP: Hoàn tất đăng nhập
    OP-->>Browser: Redirect về RP cùng code + state
    Browser->>RP: Trả code và state
    RP->>RP: Kiểm state và transaction
    RP->>OP: Token request: code + code_verifier
    OP-->>RP: ID token và các token theo scope
    RP->>RP: Kiểm ID token, issuer, audience, nonce
    RP-->>User: Thiết lập phiên RP an toàn
~~~

### 5.1. Bước 1 – Chuẩn bị yêu cầu

RP tạo các giá trị **ngẫu nhiên, không đoán được**, ràng buộc với giao dịch đăng nhập:

- **state:** RP ghi tại phía đáng tin cậy và so khớp khi callback về, giúp ngăn response bị ghép vào một yêu cầu khác.
- **nonce:** nếu được gửi trong yêu cầu, RP kiểm tra claim nonce trong ID token. Trong Authorization Code Flow, nonce có thể tùy chọn theo OIDC Core nhưng là một biện pháp hữu ích khi thiết kế phù hợp.
- **code_verifier:** bí mật của transaction PKCE, không gửi ở authorization request.
- **code_challenge:** giá trị dẫn xuất từ verifier, thường dùng phương thức **S256**, gửi tới OP.
- **redirect_uri:** phải thuộc danh sách đã đăng ký; không nhận redirect tùy ý từ người dùng.
- **scope:** cần có **openid**, có thể bổ sung profile/email theo nhu cầu.

### 5.2. Bước 2 – Người dùng được OP xác thực

OP quyết định có dùng phiên SSO hiện tại hay yêu cầu đăng nhập/MFA. RP có thể đặt yêu cầu về **độ mới hoặc mức bảo đảm** thông qua cơ chế được OP hỗ trợ.

**RP không nên suy ra đã MFA chỉ vì một authorization request hoàn thành.** Khi chính sách yêu cầu điều kiện cụ thể, ứng dụng phải kiểm tra kết quả có thể chứng minh được.

### 5.3. Bước 3 – Nhận authorization code

OP chuyển trình duyệt về redirect URI cùng **code** và **state**. RP kiểm tra state trước khi dùng code; code có thời hạn ngắn và thường chỉ được sử dụng một lần.

**Không được dùng một code vừa nhận để lập phiên ngay mà bỏ qua token exchange và ID token validation.**

### 5.4. Bước 4 – Đổi code lấy token

Client gửi code, redirect URI và code_verifier tới token endpoint; confidential client còn có thể phải xác thực client bằng cơ chế phù hợp. OP kiểm tra mã và PKCE rồi trả token.

**PKCE giúp giảm nguy cơ kẻ khác đổi authorization code bị chặn**, nhưng không thay thế TLS, state, redirect URI allowlist, client authentication, issuer validation hoặc quản lý phiên.

### 5.5. Bước 5 – Xác minh ID token và lập phiên

RP kiểm tra token, xác định subject, liên kết với account đúng và tạo phiên ứng dụng có cookie/session được bảo vệ. Ứng dụng **vẫn cần kiểm tra authorization** cho từng nghiệp vụ khi gọi API.

## 6. Ví dụ authorization request và token

### 6.1. Yêu cầu mở phiên minh họa

~~~text
GET https://idp.example.com/authorize
  ?response_type=code
  &client_id=hr-portal
  &redirect_uri=https%3A%2F%2Fportal.example.com%2Flogin%2Fcallback
  &scope=openid%20profile%20email
  &state=OPAQUE_RANDOM_SERVER_STATE
  &nonce=OPAQUE_RANDOM_SERVER_NONCE
  &code_challenge=BASE64URL_SHA256_OF_VERIFIER
  &code_challenge_method=S256
~~~

Đây là **minh họa cấu trúc**, không phải URL đã cấu hình để chạy. Các giá trị state, nonce, verifier/challenge phải được sinh và kiểm tra an toàn theo phiên/transaction; endpoint và client ID phải xuất phát từ OP tin cậy.

### 6.2. Payload ID token minh họa

~~~json
{
  "iss": "https://idp.example.com",
  "sub": "subject-1042",
  "aud": "hr-portal",
  "exp": 1795500000,
  "iat": 1795496400,
  "nonce": "OPAQUE_RANDOM_SERVER_NONCE",
  "auth_time": 1795496380,
  "acr": "urn:example:assurance:workforce",
  "email": "user@example.com",
  "email_verified": true
}
~~~

Dữ liệu trên chỉ là **phần payload minh họa**. Một ID token thật cần **được xác minh chữ ký và các điều kiện giao thức**; nội dung đọc được từ JWT chưa phải bằng chứng hợp lệ. Các giá trị thời gian và ACR chỉ để minh họa, không xác nhận một mức AAL hoặc một OP cụ thể.

### 6.3. Khóa subject của người dùng

Cặp **iss + sub** là cơ sở quan trọng để RP nhận diện chủ thể trong phạm vi OP. Không dùng email làm định danh ổn định mặc định: email có thể đổi, được cấp lại hoặc có chính sách xác minh khác nhau giữa OP.

Nếu cùng một người đăng nhập hai RP khác nhau và OP dùng **pairwise subject**, các RP có thể nhìn thấy các giá trị sub khác nhau. Vì vậy không tự suy luận có thể hợp nhất account chỉ bằng sub giữa nhiều RP hoặc chỉ bằng tên/email.

## 7. ID token, access token, refresh token và session

### 7.1. So sánh vai trò

| Đối tượng | Mục đích | Nơi sử dụng | Lưu ý |
| --- | --- | --- | --- |
| **ID token** | RP biết kết quả xác thực người dùng | RP/client | Kiểm iss, aud, chữ ký, exp, nonce và các điều kiện liên quan |
| **Access token** | Gọi API trong phạm vi được cấp | Resource Server | Kiểm audience, scope/quyền, hạn token, issuer/format phù hợp |
| **Refresh token** | Xin token mới theo policy OP | Client/token endpoint | Credential nhạy cảm, cần lưu trữ/revocation/rotation phù hợp |
| **Phiên RP** | Duy trì đăng nhập tại ứng dụng | RP và cookie/session store | Có TTL và logout riêng, không đồng nhất với ID token |
| **Phiên OP** | Duy trì trạng thái đăng nhập ở IdP | OP | Có thể hỗ trợ SSO sang nhiều RP |
| **SCIM user/account** | Bản ghi user trong ứng dụng | Ứng dụng đích | Trạng thái tài khoản không đồng nhất với mọi phiên/token |

### 7.2. ID token không phải access token

Một ứng dụng API **không nên chấp nhận ID token dành cho RP như access token**. Audience của ID token thường dành cho OIDC client, còn access token phải dành cho Resource Server có thẩm quyền.

Access token có thể là **JWT hoặc opaque token**, phụ thuộc OP và contract với API. Không giả định có thể decode JWT để lấy tất cả quyền, hoặc cứ có trường sub thì token dùng được ở bất kỳ endpoint nào.

### 7.3. Hết hạn ID token và hết hạn phiên khác nhau

ID token có thể hết hạn sau một khoảng ngắn, trong khi RP vẫn duy trì phiên cục bộ theo policy. Ngược lại, RP có thể chủ động chấm dứt phiên dù token chưa hết hạn. Không xem **exp của ID token** là đồng hồ duy nhất của toàn bộ trải nghiệm SSO.

### 7.4. Refresh token và rủi ro tồn dư

Refresh token có thể cho phép client lấy access token mới. Nếu bị lộ hoặc không được thu hồi khi Leaver, nó có thể duy trì đường truy cập. Cần kiểm soát **lưu trữ, audience/scope, expiration, rotation, revoke và cách ràng buộc với phiên/client** theo khả năng OP.

Không ghi refresh token, access token hoặc ID token thô vào log, email, ticket hay URL không được bảo vệ.

## 8. Kiểm chứng ID token: những bước bắt buộc

**RP phải kiểm chứng ID token bằng thư viện OIDC đáng tin cậy**, theo profile giao thức và cấu hình OP, trước khi lập phiên hoặc tin bất kỳ claim nào.

### 8.1. Bảng kiểm tra

| Kiểm tra | Mục đích | Sai lầm nếu bỏ qua |
| --- | --- | --- |
| **Issuer (iss)** | Token phải do đúng OP tin cậy phát hành | Tin nhầm IdP/tenant khác |
| **Audience (aud)** | RP có phải đối tượng token hướng đến không? | Token của client khác bị dùng lại |
| **Authorized Party (azp), khi áp dụng** | Xác minh client được ủy quyền trong một số trường hợp nhiều audience | Không phân biệt client thực nhận |
| **Chữ ký/thuật toán** | Kiểm tra token không bị sửa và được OP hợp lệ ký | JWT giả mạo được chấp nhận |
| **Khóa và kid** | Chọn khóa hợp lệ trong JWKS của đúng OP | Dùng khóa từ nguồn kẻ tấn công chỉ định |
| **Expiration (exp)** | Token còn thời hạn | Chấp nhận chứng cứ đã hết hạn |
| **Issued At (iat)** | Mốc phát hành có hợp lý | Chấp nhận token với thời gian bất thường |
| **Nonce, nếu yêu cầu đã gửi** | Ràng buộc ID token với authorization transaction | Token bị ghép vào yêu cầu khác |
| **auth_time, nếu policy cần** | Kiểm tra độ mới của xác thực | Dùng chứng cứ quá cũ cho hành động nhạy cảm |
| **acr/amr, nếu policy cần** | Đánh giá assurance/method theo OP contract | Tin nhầm một nhãn không rõ nghĩa |
| **Subject (sub)** | Xác định chủ thể OP khẳng định | Liên kết sai account |
| **Luồng và session binding** | Response thuộc đúng yêu cầu/state/redirect | Login CSRF hoặc session swapping |

Một số điều kiện kiểm tra như **at_hash, c_hash** thuộc những trường hợp/luồng cụ thể; không áp dụng hoặc bỏ qua máy móc. Thư viện phù hợp phải biết profile đang dùng và yêu cầu liên quan.

### 8.2. Không tự decode JWT rồi cho đăng nhập

Đoạn mã giả **không an toàn**:

~~~text
claims = base64UrlDecode(idToken.payload)
username = claims.email
session.login(username)
~~~

Nó bỏ qua chữ ký, issuer, audience, thời hạn và account linking. Payload JWT dễ đọc được **không có nghĩa đã được xác thực**; chữ ký phải được xác minh bằng khóa đáng tin, không lấy key theo nguồn tùy ý.

### 8.3. Mã giả xử lý callback

~~~text
onOidcCallback(request, session):
    transaction = loadPendingTransaction(session)

    require request.state == transaction.expectedState
    require request.code exists

    tokenResponse = oauthClient.exchangeCode(
        trustedTokenEndpoint(transaction.issuer),
        request.code,
        transaction.codeVerifier,
        registeredRedirectUri(transaction.clientId)
    )

    identity = oidcLibrary.validateIdToken(
        tokenResponse.idToken,
        expectedIssuer = transaction.issuer,
        expectedAudience = transaction.clientId,
        expectedNonce = transaction.nonce
    )

    require identity.assuranceAndFreshnessSatisfyPolicy()
    link = loadVerifiedIdentityLink(identity.issuer, identity.subject)
    require link is valid or approvedFirstLoginFlow(link)

    require currentLifecycleAndApplicationPolicyAllowsLogin(link)

    establishProtectedApplicationSession(link)
    auditLoginWithoutWritingTokens()
~~~

Đây là **mã giả**, không phải API thư viện có thật. Cần xử lý cạnh tranh phiên, lỗi kênh truyền, dấu thời gian, token replay và nhiều issuer theo kiến trúc. Không khuyến khích tự viết trình xác minh OIDC/JWT thay cho thư viện được duy trì.

## 9. Scopes và claims trong OpenID Connect

**Scope** thể hiện những nhóm thông tin/quyền client xin phép. **Claim** là thuộc tính được OP đưa ra trong ID token hoặc UserInfo.

| Scope chuẩn thường gặp | Ý nghĩa khái quát |
| --- | --- |
| **openid** | Yêu cầu xác thực OIDC, cần cho luồng OIDC |
| **profile** | Yêu cầu một tập thông tin hồ sơ như name, preferred_username (khi có/được phép) |
| **email** | Yêu cầu email và email_verified khi được hỗ trợ/cấp |
| **address** | Yêu cầu thông tin địa chỉ theo schema tương ứng |
| **phone** | Yêu cầu số điện thoại và trạng thái xác minh khi có |
| **offline_access** | Liên quan yêu cầu khả năng lấy refresh token trong điều kiện OP cho phép |

**Xin scope không bảo đảm OP luôn trả mọi claim**, vì còn phụ thuộc cấu hình, consent, dữ liệu thực có và policy.

### 9.1. Claims cốt lõi và claims tùy chọn

- **iss, sub, aud, exp, iat:** quan trọng trong ID token.
- **auth_time:** cần khi đánh giá độ mới hoặc theo các yêu cầu OIDC liên quan.
- **nonce:** dùng khi đã gửi nonce hoặc luồng yêu cầu.
- **acr, amr:** có thể phục vụ đánh giá ngữ cảnh/mức bảo đảm nếu OP và RP đã thống nhất.
- **name, preferred_username, email, email_verified:** có thể phục vụ hiển thị, liên hệ, tài khoản.
- **groups, roles, department:** thường là claims doanh nghiệp tùy chỉnh; không phải schema role bắt buộc của mọi OP.

**Email_verified không phải bằng chứng người dùng còn làm việc.** Nó thường phản ánh OP đã kiểm tra quyền kiểm soát địa chỉ email theo cơ chế của mình, không tự chứng minh employment status, hợp đồng hoặc quyền đọc dữ liệu nội bộ.

### 9.2. Claim mapping và authorization

Một claim department có thể đến từ HRIS đồng bộ tới OP. Nhưng nếu nhân viên đã **Mover**, token cũ có thể còn department trước đó. Với quyền nhạy cảm, RP nên kiểm tra dữ liệu/policy hiện hành phù hợp, không phụ thuộc vô thời hạn vào claim cũ.

Ví dụ mã giả:

~~~text
ALLOW invoice.read IF
    identity.lifecycleStatus == ACTIVE
    AND identity.accountLinkVerified
    AND subject.hasApprovedRole("FinanceReader")
    AND subject.department == resource.ownerDepartment
    AND session.assuranceSatisfies(requiredAssurance)
ELSE DENY
~~~

Đây không phải cú pháp OIDC. **RBAC/ABAC quyết định quyền**, còn OIDC cung cấp bằng chứng xác thực và có thể cung cấp một số thuộc tính đầu vào.

## 10. UserInfo Endpoint

**UserInfo Endpoint** là endpoint của OP trả về các claims của end user khi client gọi bằng **access token phù hợp** và được cấp phạm vi cần thiết.

### 10.1. Quy trình minh họa

~~~text
Client đã thực hiện OIDC login
        |
        v
Có access token được cấp cho UserInfo
        |
        v
GET UserInfo Endpoint với Bearer access token
        |
        v
Nhận claims, có "sub"
        |
        v
Kiểm UserInfo.sub == ID token.sub
        |
        v
Dùng các claims theo policy và mục đích đã duyệt
~~~

**RP phải xác minh sub trả về từ UserInfo khớp sub trong ID token** để tránh gắn thuộc tính người dùng khác vào phiên đã xác thực. Nếu response UserInfo là JWT có ký hoặc mã hóa theo cấu hình, cần xác minh theo cơ chế tương ứng.

### 10.2. UserInfo không thay thế nguồn HRIS

OP có thể trả email, name hoặc department. Điều đó không mặc nhiên biến UserInfo thành **nguồn có thẩm quyền của quan hệ lao động**. Trạng thái Joiner/Leaver, sponsor, ngày hết hợp đồng, quyền dữ liệu và ngoại lệ vẫn cần nguồn phù hợp hoặc chính sách IGA.

Không thiết kế mọi API nội bộ nhận thông tin UserInfo từ trình duyệt rồi tin là thuộc tính đã xác thực mà không kiểm tra nguồn và transaction.

## 11. Discovery, metadata và JWKS

OIDC Discovery giúp RP biết metadata của OP mà không phải nhập thủ công mọi endpoint. Thông thường RP đọc một tài liệu cấu hình theo **well-known OpenID Provider configuration** từ issuer tin cậy.

### 11.1. Ví dụ metadata rút gọn

~~~json
{
  "issuer": "https://idp.example.com",
  "authorization_endpoint": "https://idp.example.com/authorize",
  "token_endpoint": "https://idp.example.com/token",
  "userinfo_endpoint": "https://idp.example.com/userinfo",
  "jwks_uri": "https://idp.example.com/keys",
  "response_types_supported": ["code"],
  "subject_types_supported": ["public", "pairwise"],
  "id_token_signing_alg_values_supported": ["RS256"]
}
~~~

Đây là **JSON minh họa**, không phải metadata bắt buộc của một nhà cung cấp cụ thể. Ứng dụng phải kiểm **issuer từ metadata khớp issuer được cấu hình** và chỉ tin endpoint/khóa từ nguồn trust đã xác lập.

### 11.2. JWKS và luân chuyển khóa

OP có thể công bố các khóa công khai trong **JSON Web Key Set (JWKS)**. RP chọn khóa phù hợp theo ID/thuật toán trong ngữ cảnh của OP, rồi dùng để xác minh chữ ký ID token.

- Không lấy JWKS từ URL được đưa tùy ý trong token hay request chưa tin cậy.
- Không chấp nhận thuật toán ngoài chính sách hoặc thuật toán không chữ ký khi token cần được xác thực.
- Có cơ chế làm mới/cache JWKS khi OP rotate khóa, không bỏ xác minh khi chưa tìm được khóa.
- Không dùng khóa/secret của OP-A để xác minh token OP-B.
- Theo dõi lỗi issuer, signature, kid và key rotation để phát hiện cấu hình sai.

**JWKS đúng chỉ chứng minh cách kiểm chữ ký từ OP được tin cậy**, không có nghĩa mọi claim về group, employment status hoặc role luôn đáng tin để cấp quyền.

## 12. SSO, session và logout

OIDC thường là một thành phần của **SSO**: người dùng đã đăng nhập tại OP có thể vào một RP khác mà không nhập lại mật khẩu nếu chính sách OP cho phép dùng phiên sẵn có.

Tuy nhiên tồn tại nhiều trạng thái độc lập:

1. **Phiên OP:** trạng thái xác thực ở IdP.
2. **Phiên RP:** trạng thái đăng nhập cục bộ ở ứng dụng.
3. **Access/refresh token:** credential phục vụ API hoặc lấy token mới.
4. **Account và entitlement ở hệ thống đích:** do provisioning/governance quản lý.

### 12.1. Local logout không đồng nghĩa global logout

| Cơ chế | Có thể làm gì? | Giới hạn |
| --- | --- | --- |
| **Local logout tại RP** | Kết thúc phiên một ứng dụng | Không nhất thiết kết thúc phiên IdP |
| **RP-Initiated Logout** | RP yêu cầu OP xử lý logout theo capability | Phụ thuộc OP/RP và cấu hình |
| **Front-Channel Logout** | Truyền thông báo logout qua trình duyệt | Có thể bị giới hạn bởi trình duyệt/cookie |
| **Back-Channel Logout** | OP gửi thông báo tới RP qua server channel | RP phải kiểm chứng và áp dụng thông báo |
| **Token Revocation** | Thu hồi loại token được OP hỗ trợ | API có thể vẫn chấp nhận token tự chứa tới khi hết hạn nếu không kiểm lại |
| **SCIM deactivation** | Vô hiệu hóa account theo phạm vi provider | Không bảo đảm mọi phiên, token và role cục bộ bị hủy |

**Một lần logout RP không xóa account**, và **khóa user tại IdP không tự chấm dứt mọi phiên RP hoặc access token đã phát hành**.

### 12.2. Thiết kế session an toàn

- Cookie session ở ứng dụng web nên dùng **Secure, HttpOnly và SameSite** phù hợp kiến trúc.
- Giới hạn session TTL theo mức rủi ro; có thể yêu cầu xác thực lại hoặc step-up.
- Bảo vệ CSRF, session fixation, logout CSRF và session management ở backend.
- Không đưa access/refresh token vào browser storage không an toàn hoặc log.
- Khi Mover/Leaver, xem xét vô hiệu hóa phiên, thay đổi role cache và chặn giao dịch nhạy cảm theo chính sách.
- Nếu hệ thống không thể thu hồi tức thời, ghi rõ **cửa sổ rủi ro còn tồn tại** và biện pháp giảm thiểu.

## 13. Account linking và đăng nhập lần đầu

Một RP phải quyết định **người dùng từ OP tương ứng với identity/account nào trong ứng dụng**. Đây là vấn đề khác với việc token có chữ ký hợp lệ.

### 13.1. Nối theo issuer + subject

~~~text
External identity:
  issuer  = https://idp.example.com
  subject = subject-1042

Internal mapping:
  identityId      = person-1042
  rpAccountId     = erp-user-718
  linkStatus      = VERIFIED
  linkedByPolicy  = account-linking-v3
~~~

**Không nối account chỉ bằng email, display name hoặc sub không kèm issuer.** Email có thể đổi/tái sử dụng; các OP khác nhau có thể cấp cùng sub; pairwise sub có thể khác giữa các RP.

### 13.2. Nếu chưa có account trong ứng dụng?

Các lựa chọn tùy policy:

- **Pre-provision:** IGA/SCIM đã tạo account, RP tìm mapping và cho đăng nhập.
- **JIT provisioning:** RP tạo account khi đăng nhập đầu nếu issuer/sub/điều kiện nghiệp vụ đáp ứng.
- **Manual review:** cần xử lý liên kết mơ hồ, nhà thầu chưa có sponsor hoặc chứng cứ không đủ.
- **Deny:** không tạo account và không cấp quyền khi chưa có cơ sở.

**JIT provisioning là tính năng triển khai của RP**, không phải nghĩa vụ tự động của OIDC Core. Khi tạo JIT, nên có owner, quyền tối thiểu, phạm vi tenant, ngày hết hạn và khả năng Leaver.

### 13.3. Rủi ro takeover khi dùng email

Nhân viên A nghỉ, email được cấp lại cho B. Nếu ứng dụng tìm account theo email, B có thể chiếm quyền truy cập dữ liệu hoặc role của A. Cần duy trì identityId ổn định và bản đồ **issuer + sub → account**; rehire chỉ được tái sử dụng account theo quy trình xác minh chủ thể.

## 14. Mối liên hệ với Joiner–Mover–Leaver

### 14.1. Joiner: từ hồ sơ nhân sự tới phiên OIDC đầu tiên

Một Joiner đúng quy trình thường gồm:

1. HRIS/hợp đồng xác nhận sự kiện bắt đầu và **effectiveAt**.
2. Identity proofing đủ mức tạo tin cậy vào chủ thể.
3. IAM/IGA tạo identityId và liên kết với nguồn hồ sơ.
4. IdP tạo/kích hoạt account, đăng ký MFA/passkey an toàn.
5. RP được cấu hình tin cậy với OP; account được tạo trước qua SCIM/API hoặc JIT có kiểm soát.
6. RBAC/ABAC tính quyền dựa trên role, quan hệ việc làm, approval và SoD.
7. Reconciliation kiểm tra account, group/entitlement thực tế.
8. Khi người dùng đăng nhập, RP xác minh ID token, linking và chính sách truy cập hiện hành.

Một người **đăng nhập OIDC thành công** có thể vẫn bị từ chối ERP do role chưa được provision. Đây là dấu hiệu cần xử lý **provisioning**, không phải lý do tự cấp role admin.

### 14.2. Mover: token và role có thể bị cũ

Khi nhân viên chuyển từ Support sang Finance:

- HRIS cập nhật department/manager/job và ngày hiệu lực.
- IGA tính lại desired access, gỡ quyền Support và cấp Finance theo approval.
- IdP/SCIM cập nhật nhóm/thuộc tính/account ở các hệ thống có tích hợp.
- **ID token/access token cũ có thể vẫn chứa claims trước Mover** cho tới khi hết hạn hoặc bị thay.
- RP có thể giữ role đã cache trong session cục bộ.
- Ứng dụng nhạy cảm cần kiểm tra quyền hiện hành, xử lý phiên/token khi cần.
- Reconciliation phát hiện **EXTRA_ACCESS** nếu role cũ chưa được gỡ.

**Step-up chỉ làm xác thực mạnh hơn, không biến role cũ thành quyền hợp lệ.**

### 14.3. Leaver: chặn cả đường truy cập còn sống

Khi quan hệ việc làm chấm dứt:

1. Nguồn có thẩm quyền phát sự kiện Leaver.
2. IdP chặn xác thực mới và điều chỉnh credential/account theo chính sách.
3. SCIM/API vô hiệu hóa account hoặc gỡ entitlement tại các ứng dụng.
4. RP và API xử lý phiên, refresh token, access token, role cache và các kênh độc lập theo khả năng.
5. IAM đối soát và lưu bằng chứng đã thu hồi; lỗi phải có owner và deadline.

**IdP disabled không đồng nghĩa mọi RP session hoặc token bị vô hiệu ngay.** Những đường truy cập này phải được đánh giá và xử lý trong offboarding.

### 14.4. Rehire và nhiều quan hệ việc làm

Một người nghỉ ở pháp nhân A nhưng vẫn có hợp đồng hợp lệ ở B. Không được mặc định dùng một cờ TERMINATED của A để hủy toàn bộ quyền liên quan B. Mô hình identity và authorization cần xét **employment relationship** và phạm vi tài nguyên.

Rehire có thể dùng lại identity nội bộ theo chính sách, nhưng phải xét lại authenticator, account linking và **tập quyền mới**, tránh khôi phục role/refresh token cũ.

## 15. RBAC/ABAC và mức bảo đảm từ OIDC

OIDC cung cấp **bằng chứng xác thực** và có thể cung cấp claims làm đầu vào. **RBAC/ABAC** là lớp ra quyết định quyền.

### 15.1. Phân tách rõ trách nhiệm

| Thành phần | Trách nhiệm |
| --- | --- |
| **OIDC/IdP** | Ai vừa xác thực, bằng phương thức/bối cảnh nào nếu có claim |
| **HRIS/IGA** | Identity nào còn quan hệ làm việc, role và phê duyệt nào hợp lệ |
| **RBAC** | Role nào được gán và chứa permission gì |
| **ABAC** | Điều kiện theo thuộc tính, tài nguyên, hành động và ngữ cảnh |
| **Ứng dụng/API** | Kiểm quyền cuối cùng trước mỗi hành động nhạy cảm |
| **Reconciliation** | So sánh quyền mong muốn với quyền thực tế ở các hệ thống |

Nếu RP dựa trên group/role claims từ IdP, phải kiểm chứng issuer, nguồn claim, phiên bản/mapping policy và độ mới. **OIDC không bắt buộc mọi IdP phát cùng định dạng group/role.**

### 15.2. Step-up qua OIDC

Một số thông tin có thể hỗ trợ ứng dụng yêu cầu **xác thực mới hoặc mức bảo đảm cao hơn**:

- **auth_time:** thời điểm xác thực để kiểm freshness.
- **acr:** ngữ cảnh/mức bảo đảm OP khẳng định; giá trị do OP/RP thống nhất.
- **amr:** phương thức đã sử dụng theo contract.
- **max_age:** yêu cầu giới hạn tuổi xác thực.
- **prompt=login:** yêu cầu OP xác thực lại.
- **acr_values:** các giá trị assurance client yêu cầu, không phải kết quả được đảm bảo.

**Reauthentication không luôn đồng nghĩa assurance cao hơn**, và **acr_values chỉ là yêu cầu**. Ứng dụng phải kiểm tra ID token/result thực tế trước hành động. Sau step-up vẫn cần **đánh giá lại role và JML status**, vì quyền có thể đã đổi trong lúc xác thực.

## 16. Tích hợp với ứng dụng Java/Spring Security

Trong ứng dụng Java, nên dùng **thư viện OIDC/OAuth được duy trì** để thực hiện Discovery, Authorization Code Flow, PKCE theo cấu hình, xác minh token và quản lý đăng nhập. Không nên tự viết bộ xử lý JWT, redirect và key rotation từ đầu.

### 16.1. Cấu hình Spring Boot minh họa

Ví dụ cấu hình **minh họa dành cho web server-side OIDC client**:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          enterprise:
            provider: enterprise
            client-id: illustrative-client-id
            client-secret: managed-outside-source-code
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          enterprise:
            issuer-uri: https://idp.example.com
~~~

**Không sử dụng client-secret minh họa này trong sản xuất.** Bí mật thật phải đến từ cấu hình bí mật được bảo vệ và không commit vào Git. Khi dùng **public client**, cần cấu hình mô hình client và PKCE đúng với nền tảng; không giả vờ public client có secret bí mật.

Spring Security có thể sử dụng issuer-uri để Discovery và xác minh ID token theo cơ chế framework hỗ trợ. Vẫn cần cấu hình chính sách, authorization ở endpoint, session security, logout và mapping role phù hợp. **Không suy diễn toàn bộ cấu hình bảo mật đã đủ chỉ từ đoạn YAML này.**

### 16.2. SecurityFilterChain minh họa

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class WebSecurityConfig {

    @Bean
    SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .requestMatchers("/admin/**").hasAuthority("APP_ADMIN")
                .anyRequest().authenticated()
            )
            .oauth2Login(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Đây là **mẫu giải thích**, không phải ứng dụng hoàn chỉnh. Quyền **APP_ADMIN** phải do cơ chế mapping/authorization đáng tin xác định từ IAM/IGA hoặc chính sách ứng dụng; đoạn code không tự ánh xạ group claim thành authority đó.

Ứng dụng thực tế còn phải định nghĩa session, CSRF, exception handling, logout, account lifecycle, step-up và Resource Server protection nếu cung cấp API. **Không nên vô hiệu hóa CSRF đại trà chỉ để đăng nhập được**.

### 16.3. Kiểm tra quyền nghiệp vụ

Ngay cả sau khi framework xác thực thành công, service thực thi thao tác nhạy cảm nên kiểm tra **đúng identity, account status, role/entitlement, resource và policy hiện hành**.

Ví dụ một API xem hóa đơn cần kiểm tra invoice thuộc phạm vi department mà người dùng được duyệt; kiểm tra người dùng đã đăng nhập OIDC chưa đủ để đọc mọi hóa đơn.

### 16.4. SPA, mobile và backend-for-frontend

- **Server-rendered web/BFF:** backend xử lý OIDC và giữ token ở server, browser sử dụng session cookie được bảo vệ.
- **Single-page application:** thường là public client dùng Authorization Code + PKCE; lưu token và bảo vệ trình duyệt cần đánh giá kỹ.
- **Mobile/native:** dùng external browser hoặc system authorization agent và redirect được đăng ký, tránh nhúng webview thu thập mật khẩu.
- **Backend API:** dùng Resource Server để xác minh access token theo issuer/audience/scope, không dùng login cookie của RP thay thế không kiểm soát.

Không áp cùng một chiến lược secret/session cho mọi loại client. **PKCE và client authentication phục vụ các mục tiêu khác nhau**; cách cấu hình cần đúng với public/confidential client.

## 17. Những lỗi bảo mật phổ biến

| Rủi ro | Nguyên nhân | Kiểm soát |
| --- | --- | --- |
| **Chấp nhận token từ issuer lạ** | RP thiếu issuer allowlist | Kiểm iss và Discovery từ OP tin cậy |
| **Sai audience** | Dùng token dành cho client/API khác | Kiểm aud, azp khi áp dụng |
| **Bỏ qua chữ ký JWT** | Chỉ decode payload | Thư viện xác minh với JWKS đúng OP |
| **Tin thuật toán do attacker chỉ định** | Chấp nhận alg bất kỳ | Allowlist thuật toán, cấm các cấu hình không chữ ký ngoài profile |
| **Login CSRF/session swapping** | Thiếu state và transaction binding | State, cookie và phiên ràng buộc |
| **Authorization code interception** | Code bị đánh cắp và đổi token | PKCE S256, TLS, redirect bảo vệ |
| **Open redirect** | Callback nhận URL tùy ý | Exact redirect allowlist |
| **Nonce/replay sai** | Token ghép vào lần đăng nhập khác | Nonce nếu dùng, kiểm state/session/TTL |
| **Mix-up nhiều OP** | RP không biết response thuộc issuer nào | Gắn issuer với transaction, so khớp OP |
| **Account takeover qua email** | Account linking chỉ dựa email | Cặp issuer+sub và quy trình xác minh |
| **Claim role stale** | Dùng token cũ sau Mover | Kiểm chính sách hiện hành, refresh/thu hồi phiên |
| **Quyền tồn dư sau Leaver** | Chỉ disable IdP, quên SaaS/local account | SCIM/API, session/token revoke, reconciliation |
| **Refresh token lộ** | Lưu trong log/browser storage không an toàn | Secret storage, rotation/revoke và TTL |
| **Thiếu giới hạn UserInfo** | RP lấy/ghi nhiều dữ liệu cá nhân | Scope tối thiểu, privacy và retention |
| **Khôi phục MFA quá yếu** | Attacker chiếm account IdP qua recovery | Recovery proofing, MFA/phishing resistance, audit |
| **Shadow OIDC clients** | Client/trust không owner, cấu hình lỗi thời | Inventory, review, thu hồi client không dùng |

### 17.1. Không tự tin cậy claim từ frontend

Một client có thể gửi JSON nói email hoặc role của mình là admin; backend không được dùng dữ liệu này làm chứng cứ. Phải kiểm tra **token hoặc session đã được xác thực** và authorization từ nguồn tin cậy.

### 17.2. Không ghi token vào log

JWT ký (JWS) **không đồng nghĩa đã mã hóa nội dung bí mật**; payload có thể được đọc bởi người có token. Không đưa ID/access/refresh token, authorization code, code_verifier, client secret, private key hoặc cookie session vào log, exception, URL hoặc ticket.

## 18. Kiểm toán, giám sát và reconciliation

Một hệ thống IAM/OIDC cần truy vết được **ai đăng nhập, qua OP nào, vào RP nào, dựa trên account link nào, có quyền gì và đã bị thu hồi ở đâu**.

### 18.1. Các nhóm bằng chứng cần lưu

| Nhóm | Ví dụ trường | Ý nghĩa |
| --- | --- | --- |
| **Trust/client config** | Issuer, clientId, config version, owner | RP đã tin OP nào |
| **Authorization transaction** | Correlation ID, start time, callback outcome | Chẩn đoán login/CSRF/mix-up |
| **Authentication** | Subject reference, method context, auth_time, result | Kết quả đăng nhập không cần lưu token thô |
| **Account linking** | identityId, RP accountId, issuer+sub reference | Giải thích cách nối chủ thể |
| **Authorization** | Role/entitlement, policy version, resource, decision | Vì sao được truy cập |
| **JML event** | Source HRIS, relationshipId, effectiveAt, version | Trạng thái nghiệp vụ liên quan |
| **Provisioning** | SCIM/API task, target account, execution result | Đã cấp/gỡ quyền gì |
| **Session/token** | Session ID ref, revoke/logout result | Đường truy cập còn hay không |
| **Reconciliation** | Desired vs observed, verifiedAt, exception owner | Phát hiện và xử lý quyền tồn dư |

Chỉ ghi dữ liệu cần thiết, dùng tham chiếu bảo vệ, áp quyền đọc log theo vai trò và có retention phù hợp. Không biến log thành kho lưu mật khẩu hoặc toàn bộ hồ sơ nhân sự.

### 18.2. Chỉ số vận hành

| Chỉ số | Ý nghĩa |
| --- | --- |
| OIDC login success/failure theo issuer và RP | Khả năng sẵn sàng của federation |
| ID token validation failure | Sai chữ ký, issuer, audience, nonce, thời hạn |
| State/PKCE error count | Sai transaction, client config hoặc rủi ro can thiệp |
| Account-linking exception | Login hợp lệ nhưng không nối được identity |
| JIT vs SCIM account mismatch | Tài khoản/tập quyền được tạo ngoài luồng |
| Claim/role drift sau Mover | Token hoặc role cục bộ khác quyền mới |
| Leaver residual session/entitlement | Đường truy cập còn sau effectiveAt |
| Logout propagation coverage | RP nào hỗ trợ và xác minh được logout |
| Trust/client owner coverage | OP/RP registration có trách nhiệm rõ ràng |
| Token/recovery incident rate | Rủi ro credential và khôi phục |

Không đánh giá hệ thống chỉ qua tỷ lệ login thành công. Một RP có thể **đăng nhập đúng nhưng cấp sai quyền** hoặc chưa thu hồi role sau Leaver.

## 19. Tình huống thực tế theo JML

### 19.1. Joiner: đăng nhập được nhưng chưa có quyền

Nhân viên **Minh** bắt đầu làm việc ngày 01/12/2026. HRIS ghi quan hệ việc làm và effectiveAt; identity proofing hoàn tất; IdP đã tạo account MFA. RP xử lý Authorization Code + PKCE và xác minh ID token thành công.

Tuy nhiên ứng dụng báo cáo chưa nhận được role Reader qua SCIM. RP cho biết tài khoản chưa có quyền cần thiết và mở ticket xử lý; **không tự cấp Admin** chỉ vì OIDC đã đăng nhập thành công. IGA sửa provisioning, reconciliation đọc lại quyền và sau đó Minh mới truy cập đúng phạm vi.

### 19.2. Mover: token vẫn mang department cũ

Nhân viên **Lan** chuyển từ Support sang Finance. HRIS/IGA cập nhật desired access, nhưng Lan còn phiên RP có group/claim Support từ lần đăng nhập buổi sáng. Ứng dụng CRM vẫn có role SupportReader cục bộ.

Hệ thống cần cập nhật/gỡ role ứng dụng, xử lý phiên hoặc buộc đánh giá lại khi rủi ro yêu cầu. Một token mới mang department Finance **không tự chứng minh** CRM đã gỡ SupportReader. Reconciliation phải kiểm observed role, không chỉ xem ID token.

### 19.3. Leaver: IdP bị khóa, RP còn phiên

Nhà thầu **An** hết hợp đồng lúc 18:00. IdP của đối tác vẫn giữ account hợp lệ cho mục đích khác, nhưng tổ chức sở hữu RP phải thu hồi quyền truy cập theo hợp đồng. Nếu RP còn local session và chưa kiểm trạng thái hợp đồng, An vẫn có thể gọi API.

Quy trình Leaver cần vô hiệu hóa/thu hồi tài khoản, entitlement và phiên theo scope của RP; API phải kiểm quyền hiện hành; reconciliation xác minh kết quả. **Chỉ trông đợi IdP đối tác khóa tài khoản là không đủ.**

### 19.4. Rehire và email tái sử dụng

Nhân viên cũ quay lại, sử dụng cùng email nhưng account trước đó đã thu hồi. IAM phải xác minh chủ thể, đánh giá linking issuer+sub, quyết định account mới/cũ theo policy và tính lại quyền. Không dùng email trùng để tự phục hồi refresh token hay role cũ.

### 19.5. Service account và workload

Một pipeline CI/CD có thể dùng workload federation dựa trên token do issuer của nền tảng phát hành để xin credential cloud ngắn hạn. Đây **khác với OIDC login tương tác của người dùng**: cần kiểm issuer, audience, subject/claims của workload, owner, môi trường và quyền hẹp. Khi owner Mover/Leaver, phải chuyển quyền quản lý và đánh giá secret/trust, không mặc định xóa workload đang phục vụ sản xuất.

## 20. Bảng kiểm tra triển khai OpenID Connect

| Câu hỏi | Bằng chứng mong đợi |
| --- | --- |
| Có hiểu rõ RP, OP, client, resource server không? | Sơ đồ tin cậy và owner |
| Có phân biệt OIDC với OAuth authorization không? | ID token vs access token dùng đúng mục đích |
| OP/issuer được phép có danh mục không? | Allowlist issuer và client registration |
| Redirect URI được đăng ký chặt không? | Exact URI, không mở redirect |
| Luồng được chọn phù hợp loại client không? | Authorization Code + PKCE, client auth khi cần |
| Có bảo vệ state và nonce khi sử dụng không? | Transaction binding và kiểm callback |
| Có xác minh ID token bằng thư viện phù hợp không? | Issuer, aud/azp, signature, exp, nonce và chính sách |
| Discovery/JWKS có ràng buộc với issuer không? | Metadata đáng tin, key rotation |
| Có phân biệt RP session và OP session không? | TTL, logout, session store và policy |
| Có tránh ID token được dùng như access token không? | API xác minh token đúng audience |
| Scope và claim có tối thiểu không? | Data minimization, purpose và consent |
| UserInfo.sub có đối chiếu ID token.sub không? | Kiểm tra identity consistency |
| Account linking có theo issuer+sub không? | Link record, anti-duplicate/rehire policy |
| JIT provisioning có giới hạn không? | Approval, sponsor, role tối thiểu, Leaver |
| Có map role/group claim theo contract không? | RBAC/ABAC mapping và freshness |
| Khi Mover, quyền cũ có được gỡ không? | SCIM/API tasks và reconciliation |
| Khi Leaver, RP session/token có được xử lý không? | Deprovision, revoke, audit/observed state |
| Có step-up khi thực hiện quyền nhạy cảm không? | Assurance/freshness policy, recheck quyền |
| Có bảo vệ secret, token và thông tin cá nhân không? | Vault, phân quyền log, rotation |
| Có kiểm thử đa OP và account linking mơ hồ không? | Negative tests: issuer mix-up, email reuse |
| Tài khoản dịch vụ có owner và vòng đời riêng không? | Trust/credential inventory, JML owner transfer |
| Có KPI và runbook xử lý sự cố OIDC không? | Monitoring, audit, reconciliation, escalation |

## 21. Những hiểu lầm thường gặp

1. **“OAuth 2.0 tự xác thực người dùng.”** OAuth chủ yếu là authorization; OIDC thêm quy tắc identity authentication.
2. **“Đăng nhập OIDC thành công nghĩa là có quyền ở mọi API.”** Authorization phải kiểm tra riêng.
3. **“ID token là access token.”** Chúng có mục đích và audience khác nhau.
4. **“JWT decode được tức là token thật.”** Phải kiểm chữ ký, issuer, audience và điều kiện token.
5. **“Client yêu cầu scope thì luôn nhận đủ claims.”** OP còn có policy và dữ liệu thực tế.
6. **“Email_verified nghĩa là nhân viên ACTIVE.”** Không thể suy ra trạng thái quan hệ làm việc.
7. **“sub là duy nhất giữa tất cả IdP.”** Cần issuer+sub; pairwise subject có thể khác theo RP.
8. **“Có PKCE rồi thì khỏi cần state/nonce/redirect validation.”** Các biện pháp giải quyết những rủi ro khác nhau.
9. **“ID token hết hạn nghĩa là ứng dụng logout.”** RP session có vòng đời riêng.
10. **“Khóa IdP là SaaS mất ngay mọi session.”** Cần logout/deprovision và kiểm chứng từng đích.
11. **“Group claim ở IdP là quyền cuối cùng của ứng dụng.”** Mapping, permission cục bộ và ABAC có thể khác.
12. **“OIDC tự tạo hoặc thu hồi tài khoản ở SaaS.”** Cần SCIM/API/JIT có kiểm soát.
13. **“JIT có thể auto-link bằng email.”** Dễ gây account takeover khi email thay đổi/tái sử dụng.
14. **“MFA mạnh có thể bù cho role không được duyệt.”** Step-up không cấp quyền nghiệp vụ.
15. **“Workload identity dùng OTP của nhân viên.”** Workload có cơ chế non-interactive và governance riêng.

## 22. Câu hỏi tự đánh giá

1. OpenID Connect giải quyết vấn đề nào mà chỉ OAuth 2.0 không chuẩn hóa đầy đủ?
2. OP và RP làm gì, và Resource Server khác RP như thế nào?
3. Scope **openid** có vai trò gì trong yêu cầu đăng nhập?
4. Trình bày từng bước Authorization Code Flow + PKCE và lý do cần code_verifier.
5. State và nonce ngăn những nhóm rủi ro khác nhau nào?
6. Cần xác minh các claim/điều kiện nào của ID token trước khi lập phiên?
7. Vì sao không thể chỉ decode JWT rồi dùng email để đăng nhập?
8. ID token, access token, refresh token, RP session và OP session khác nhau ra sao?
9. Khi dùng UserInfo, vì sao phải kiểm sub khớp ID token?
10. JWKS và Discovery giúp RP biết gì; vì sao không dùng JWKS do request của attacker chỉ định?
11. Vì sao issuer+sub là khóa linking phù hợp hơn email?
12. JIT provisioning khác SCIM provisioning như thế nào và cần kiểm soát gì?
13. Một nhân viên Mover nhưng token cũ còn claim Support. Những kiểm soát IAM nào cần thực hiện?
14. Khi Leaver, vì sao IdP disabled chưa chắc chặn toàn bộ ứng dụng?
15. Một ứng dụng Java dùng Spring Security OIDC login thành công. Cần bổ sung những kiểm soát authorization và JML nào?
16. ACR/AMR/auth_time hỗ trợ step-up ra sao và vì sao không thể tin chỉ một tham số yêu cầu?
17. Khi tích hợp nhiều OP, những biện pháp nào tránh issuer mix-up và account takeover?
18. Tài khoản dịch vụ dùng workload federation khác đăng nhập OIDC của con người ở những điểm nào?

## 23. Ghi nhớ

**OpenID Connect (OIDC)** là **lớp xác thực trên nền OAuth 2.0** giúp **Relying Party** tin vào kết quả xác thực của **OpenID Provider** qua các điều kiện giao thức và **ID token**. Một triển khai an toàn cần xác định **issuer/client/redirect trust**, sử dụng luồng phù hợp như **Authorization Code + PKCE**, kiểm tra **state, nonce khi dùng, chữ ký, issuer, audience, thời hạn và subject**, bảo vệ token/phiên và nối account bằng **issuer + sub**.

Trong vòng đời **Joiner–Mover–Leaver**, OIDC/SSO phục vụ đăng nhập, còn **HRIS và identity proofing** xác định chủ thể và quan hệ nghiệp vụ, **SCIM/API/JIT được kiểm soát** quản lý account, **RBAC/ABAC** quyết định entitlement, và **audit/reconciliation** xác minh việc cấp–đổi–thu hồi. **Đăng nhập thành công không có nghĩa quyền hợp lệ; khóa IdP không tự xóa mọi RP session/token; step-up không thay thế việc gỡ quyền cũ.** Quản lý cả danh tính con người lẫn workload theo nguồn, owner, thời gian hiệu lực và bằng chứng thực tế là cơ sở giảm **tài khoản mồ côi và quyền truy cập tồn dư**.
