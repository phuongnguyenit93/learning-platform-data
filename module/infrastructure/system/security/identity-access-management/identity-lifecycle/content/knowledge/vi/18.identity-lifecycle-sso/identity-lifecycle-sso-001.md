# Single Sign-On (SSO) trong quản lý vòng đời danh tính IAM

## 1. Single Sign-On là gì?

**Single Sign-On (SSO)** là cơ chế cho phép một người dùng **xác thực thông qua một điểm tin cậy** và sau đó truy cập nhiều ứng dụng có quan hệ tin cậy tương ứng mà **không phải nhập lại thông tin xác thực riêng cho từng ứng dụng trong mỗi lần chuyển ứng dụng**. SSO thường được triển khai với **Identity Provider (IdP)** và các ứng dụng nhận kết quả xác thực thông qua giao thức liên kết danh tính (*federation*).

Ví dụ, nhân viên Lan đăng nhập vào cổng danh tính doanh nghiệp bằng mật khẩu và khóa bảo mật FIDO2. Sau đó Lan mở hệ thống chấm công, ứng dụng quản lý công việc và cổng báo cáo. Nếu các ứng dụng được cấu hình SSO hợp lệ, chúng có thể nhận thông tin xác thực từ IdP thay vì yêu cầu Lan nhớ ba mật khẩu riêng.

**SSO không có nghĩa người dùng không bao giờ phải xác thực lại.** Phiên tại IdP có thể hết hạn, ứng dụng có thể yêu cầu xác thực mạnh hơn cho thao tác nhạy cảm, hoặc tổ chức có thể thu hồi phiên khi phát hiện rủi ro.

Bài học thuộc chương **SSO** trong mô-đun **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**. Phạm vi học là quản lý vòng đời danh tính **Joiner–Mover–Leaver (JML)**, từ xác minh và enrollment đến provisioning, rà soát, thay đổi vai trò và thu hồi quyền; đồng thời liên kết **IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, kiểm toán** và việc giảm quyền truy cập tồn dư.

### Phân biệt xác thực, đăng nhập một lần và quyền truy cập

| Khái niệm | Câu hỏi trả lời | Điều không tự bảo đảm |
|---|---|---|
| **Identity proofing** | Người đăng ký thực sự gắn với danh tính được khai đến mức nào? | Người đó có quyền trong ứng dụng |
| **Authentication** | Phiên hiện tại đã chứng minh quyền kiểm soát authenticator nào? | Danh tính đã được proofing ở mức cao |
| **SSO/Federation** | Ứng dụng tin được kết quả xác thực từ IdP như thế nào? | Ứng dụng đã được cấp đúng nhóm/role |
| **Provisioning** | Tài khoản và entitlement đã được tạo/cập nhật/thu hồi ở đích chưa? | Người dùng đã xác thực thành công |
| **Authorization** | Người dùng được thao tác gì với tài nguyên này? | Phiên IdP hoặc tài khoản còn hiệu lực mãi mãi |
| **Session management** | Phiên đăng nhập có còn hợp lệ và phải được thu hồi lúc nào? | Mọi session ở mọi ứng dụng sẽ tự đóng đồng thời |

**SSO là một lớp trong IAM, không thay thế identity proofing, MFA, RBAC/ABAC, SCIM hay Leaver deprovisioning.**

## 2. Những thành phần cốt lõi của kiến trúc SSO

### 2.1. Identity Provider (IdP)

**IdP** là hệ thống xác thực chủ thể và cung cấp bằng chứng/khẳng định xác thực cho những ứng dụng có quan hệ tin cậy. Nó có thể quản lý phương thức đăng nhập như password, passkey, FIDO2 security key và chính sách **Multi-Factor Authentication (MFA)**.

IdP thường giữ một **phiên đăng nhập trung tâm**: khi người dùng đã đăng nhập và phiên vẫn phù hợp chính sách, việc chuyển sang ứng dụng khác có thể không yêu cầu nhập lại mật khẩu.

### 2.2. Service Provider (SP) hoặc Relying Party (RP)

- Trong **SAML**, ứng dụng nhận và xác minh SAML assertion thường được gọi là **Service Provider (SP)**.
- Trong **OpenID Connect (OIDC)**, ứng dụng sử dụng kết quả đăng nhập thường được gọi là **Relying Party (RP)** hoặc **OIDC client**.
- Trong kiến trúc OAuth, có thêm vai trò **Authorization Server** và **Resource Server**; không được nhầm access token dùng gọi API với bằng chứng xác thực đăng nhập.

Ứng dụng phải **tự kiểm tra thông điệp tin cậy** và **tự áp quyền nghiệp vụ** theo hợp đồng tích hợp. Việc thấy người dùng đến từ một URL IdP không đủ để kết luận phiên đã được xác thực hợp lệ.

### 2.3. Identity store, HRIS và IGA

**HRIS** hoặc nguồn có thẩm quyền tạo sự kiện Joiner/Mover/Leaver và dữ liệu quan hệ nhân sự. **IAM/IGA** điều phối tài khoản, nhóm, phê duyệt, quyền, thời hạn và đối soát. **Directory** lưu bản ghi tài khoản và nhóm theo nhu cầu hệ thống. Những nguồn này có thể tích hợp với IdP nhưng không phải tất cả đều là IdP.

### 2.4. Browser, session và ứng dụng đích

Trình duyệt chuyển hướng giữa ứng dụng và IdP; phiên IdP và phiên ứng dụng thường là **hai phiên riêng**. Một ứng dụng có thể giữ cookie phiên của chính nó sau khi hoàn tất một lần federation. Vì vậy, khóa IdP không mặc nhiên xóa mọi cookie hay token cũ ở các ứng dụng.

### Kiến trúc tổng quan

~~~mermaid
flowchart TD
    HR[HRIS / nguồn danh tính] --> IAM[IAM / IGA: JML và chính sách]
    IAM --> IDP[IdP: authentication và MFA]
    IAM --> PROV[SCIM / API provisioning]
    U[Người dùng / Browser] <-->|Phiên đăng nhập và federation| IDP
    U --> CRM[CRM: SP / RP]
    U --> ERP[ERP: SP / RP]
    U --> PORTAL[Portal: SP / RP]
    IDP <-->|SAML / OIDC| CRM
    IDP <-->|SAML / OIDC| ERP
    IDP <-->|SAML / OIDC| PORTAL
    PROV --> CRM
    PROV --> ERP
    PROV --> PORTAL
    CRM --> AUTH[RBAC / ABAC tại ứng dụng]
    ERP --> AUTH
    PORTAL --> AUTH
    IAM --> AUDIT[Audit và reconciliation]
    IDP --> AUDIT
~~~

**Hai đường tích hợp khác nhau:** SAML/OIDC truyền **kết quả xác thực**; SCIM/API thường đồng bộ **tài khoản và quyền được quản lý**. Hai đường này có thể cùng tồn tại nhưng khác trách nhiệm.

## 3. SSO diễn ra như thế nào?

Giả sử Lan mở ứng dụng báo cáo khi chưa có session trong ứng dụng nhưng đã đăng nhập IdP.

1. **Ứng dụng xác định chưa có phiên hợp lệ.** Nó tạo yêu cầu xác thực theo giao thức đã cấu hình.
2. **Trình duyệt được chuyển tới IdP.** IdP xác định Lan đã có phiên trung tâm phù hợp chính sách hay chưa.
3. **IdP xác thực khi cần.** Nếu chưa có phiên hoặc chính sách đòi hỏi, Lan đăng nhập, hoàn thành MFA hoặc step-up.
4. **IdP phát bằng chứng xác thực.** Với SAML là assertion/response; với OIDC thường có một luồng nhận **ID token**.
5. **Ứng dụng xác minh bằng chứng.** Nó kiểm tra chữ ký, nguồn phát, audience/client, thời hạn, phiên/yêu cầu tương ứng và các điều kiện giao thức.
6. **Ứng dụng liên kết đúng account.** Không được tạo nhầm user dựa duy nhất vào tên hiển thị hoặc email tự khai.
7. **Ứng dụng áp quyền.** RBAC/ABAC, trạng thái tài khoản, hợp đồng, chính sách tổ chức và quyền truy cập được đánh giá.
8. **Ứng dụng tạo session của riêng nó.** Lan sử dụng ứng dụng đến khi phiên hết hạn, bị thu hồi hoặc không còn đáp ứng chính sách.

### Luồng khái quát

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant A as Ứng dụng / SP-RP
    participant I as IdP
    participant P as IAM / quyền ứng dụng
    U->>A: Mở ứng dụng
    A-->>U: Chuyển sang yêu cầu xác thực tại IdP
    U->>I: Truy cập IdP
    I->>I: Kiểm tra session, MFA, policy
    I-->>U: Kết quả xác thực theo giao thức
    U->>A: Trả kết quả theo luồng phù hợp
    A->>A: Xác minh bằng chứng và liên kết account
    A->>P: Kiểm tra lifecycle và quyền hiện hành
    P-->>A: Kết quả chính sách
    A-->>U: Phiên ứng dụng nếu được phép
~~~

Một số bước được thực hiện **trực tiếp giữa server ứng dụng và IdP**, không phải mọi token đều đi qua trình duyệt. Sơ đồ trên chỉ minh họa vai trò giao tiếp; cách trao đổi chính xác phụ thuộc SAML hay OIDC.

## 4. SAML 2.0: SSO dựa trên XML assertion

**Security Assertion Markup Language 2.0 (SAML 2.0)** là chuẩn federation phổ biến trong ứng dụng doanh nghiệp, đặc biệt các phần mềm SaaS lâu đời.

### Thành phần chính

- **IdP:** xác thực người dùng và phát SAML assertion.
- **SP:** ứng dụng nhận, kiểm tra assertion và cho phép tạo session.
- **Metadata:** thông tin cấu hình như entity ID, endpoint, chứng chỉ và các tham số tin cậy.
- **AuthnRequest:** yêu cầu xác thực do SP tạo trong luồng SP-initiated.
- **SAML Response/Assertion:** thông điệp XML mang kết quả xác thực và thuộc tính được cho phép.
- **Audience, Recipient, Destination, InResponseTo:** các trường quan trọng trong việc giới hạn assertion cho đúng SP, endpoint và yêu cầu.
- **Conditions và SubjectConfirmationData:** ràng buộc về thời gian, đối tượng và cách dùng assertion.

### SP-initiated SSO

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant SP as SAML Service Provider
    participant IDP as SAML Identity Provider
    B->>SP: Mở ứng dụng
    SP-->>B: AuthnRequest / Redirect sang IdP
    B->>IDP: Chuyển AuthnRequest
    IDP->>IDP: Session hoặc login + MFA
    IDP-->>B: SAMLResponse theo binding đã cấu hình
    B->>SP: POST response tới Assertion Consumer Service
    SP->>SP: Xác minh chữ ký, audience, thời gian và correlation
    SP-->>B: Session ứng dụng nếu được phép
~~~

### Những kiểm tra không thể bỏ qua

SP phải kiểm tra **chữ ký hợp lệ và đúng phần nội dung được sử dụng**, issuer/metadata tin cậy, audience, recipient/destination, khoảng thời gian hiệu lực, SubjectConfirmation và sự phù hợp với AuthnRequest. Khi có **InResponseTo**, phải đối chiếu yêu cầu tương ứng. Cần ngăn replay và lỗi **XML signature wrapping** bằng thư viện SAML đáng tin cậy và cấu hình an toàn.

**Không chỉ giải mã XML rồi tin NameID/email.** NameID hoặc thuộc tính cũng cần được liên kết với đúng identity theo quy tắc account mapping đã được phê duyệt.

### IdP-initiated SSO

Trong **IdP-initiated SSO**, người dùng bắt đầu từ portal của IdP rồi mở ứng dụng, có thể không có AuthnRequest của SP để đối chiếu. Điều này làm giảm một số bảo đảm về ràng buộc phản hồi với yêu cầu ban đầu. Tổ chức cần đánh giá rủi ro, yêu cầu chống phát lại, trạng thái phiên và giới hạn tích hợp; **ưu tiên SP-initiated khi phù hợp** với ứng dụng và mức bảo đảm mong muốn.

## 5. OpenID Connect (OIDC): xác thực trên nền OAuth 2.0

**OpenID Connect** là lớp định danh xây trên OAuth 2.0, phổ biến ở ứng dụng web và mobile. OIDC cung cấp **ID token** và quy tắc xác minh để client biết **người dùng nào đã được xác thực tại OpenID Provider (OP)**.

Trong OIDC, OP thường là IdP; ứng dụng là RP/client.

### Authorization Code Flow với PKCE

Đây là một kiểu triển khai được ưu tiên trong nhiều ứng dụng hiện đại. Các bước tóm tắt:

1. RP tạo yêu cầu authorization với **client_id, redirect_uri, scope phù hợp (gồm openid), state**, cùng **nonce khi áp dụng** và tham số PKCE.
2. Trình duyệt tới authorization endpoint của OP. OP xác thực người dùng, thực thi MFA/step-up nếu cần.
3. OP chuyển hướng về redirect_uri đã đăng ký với một **authorization code** ngắn hạn.
4. RP đổi code tại token endpoint bằng các điều kiện cần thiết; **PKCE** chứng minh client nắm code_verifier tương ứng với code_challenge ban đầu.
5. RP nhận và xác minh **ID token** theo OIDC, kiểm tra issuer, audience, thời hạn, nonce nếu được sử dụng và các điều kiện áp dụng.
6. RP ánh xạ subject của OP tới tài khoản ứng dụng, kiểm tra quyền và tạo session riêng.

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant RP as OIDC Relying Party
    participant OP as OpenID Provider
    B->>RP: Mở ứng dụng
    RP-->>B: Redirect tới authorization endpoint
    B->>OP: Yêu cầu + state + PKCE challenge
    OP->>OP: Xác thực phiên và MFA khi cần
    OP-->>B: Redirect tới RP kèm authorization code + state
    B->>RP: Chuyển authorization code
    RP->>OP: Token request + code verifier
    OP-->>RP: ID token và token khác nếu áp dụng
    RP->>RP: Validate ID token, account mapping và quyền
    RP-->>B: Session ứng dụng
~~~

### Ý nghĩa các trường quan trọng

| Trường/kiểm soát | Mục đích | Sai lầm thường gặp |
|---|---|---|
| **state** | Liên kết callback với giao dịch của client, hỗ trợ chống login CSRF | Không kiểm tra hoặc tái sử dụng tùy tiện |
| **nonce** | Ràng buộc ID token với yêu cầu và hỗ trợ chống replay trong các luồng áp dụng | Không xác minh khi đã phát nonce |
| **PKCE** | Bảo vệ authorization code khỏi bị sử dụng bởi bên không nắm code_verifier | Nghĩ PKCE thay thế hoàn toàn state, redirect URI hoặc xác thực client |
| **issuer (iss)** | Nhận biết OP đáng tin | Tin issuer từ dữ liệu do attacker chọn |
| **audience (aud)** | Bảo đảm ID token dành cho đúng RP | Chấp nhận token cấp cho client khác |
| **expiry (exp)** | Giới hạn thời hạn token | Chấp nhận token đã hết hạn |
| **subject (sub)** | Định danh người dùng theo issuer | Dùng email làm định danh bất biến |
| **redirect_uri** | Điểm quay lại đã đăng ký và kiểm soát | Cho phép redirect tùy ý gây rò rỉ code |

**Không tự xây trình xác minh JWT/OIDC bằng cách chỉ decode phần payload.** Cần kiểm tra thuật toán/chữ ký theo cấu hình tin cậy, key rotation, issuer, audience, nonce/state và các điều kiện chuẩn bằng thư viện đã được kiểm thử.

## 6. OIDC ID token, OAuth access token và SAML assertion khác nhau thế nào?

SSO thường gặp nhầm lẫn giữa **OIDC** và **OAuth 2.0**.

- **OAuth 2.0** là framework **ủy quyền** cho client truy cập tài nguyên theo phạm vi và điều kiện được cấp; bản thân OAuth không phải định nghĩa giao thức đăng nhập danh tính của người dùng.
- **OIDC** bổ sung lớp **authentication/identity** và ID token dành cho RP.
- **SAML** dùng assertion XML để chuyển thông tin xác thực qua quan hệ tin cậy giữa IdP và SP.

| Loại | Đối tượng dùng | Công dụng chính | Lưu ý bảo mật |
|---|---|---|---|
| **SAML assertion** | SAML SP | Nhận kết quả xác thực và thuộc tính | Xác minh chữ ký, audience, recipient, thời gian, request/replay |
| **OIDC ID token** | RP/client | Xác nhận sự kiện xác thực và subject tại OP | Kiểm tra issuer, audience, chữ ký, exp, nonce và claim liên quan |
| **OAuth access token** | Resource server/API | Cho phép truy cập tài nguyên theo phạm vi/quyền | Không dùng access token bất kỳ như ID token; định dạng có thể opaque hoặc JWT |
| **OAuth refresh token** | Client được cấp theo policy | Xin access token mới không cần người dùng đăng nhập lại mỗi lần | Bảo vệ, giới hạn, xoay vòng/thu hồi theo khả năng và chính sách |
| **Session cookie** | Trình duyệt – ứng dụng | Duy trì phiên ở ứng dụng | Bảo vệ cookie, CSRF, hết hạn và thu hồi |

Ví dụ **claim minh họa** trong một ID token đã được xác minh, không phải token thật và không phải mẫu đủ để tự xác thực:

~~~json
{
  "iss": "https://id.example.org",
  "sub": "user-4bc7",
  "aud": "reporting-web",
  "iat": 1795402800,
  "exp": 1795403100,
  "auth_time": 1795402750,
  "acr": "organization-defined-assurance",
  "amr": ["pwd", "hwk"]
}
~~~

Các claim như **acr/amr** cần được hiểu theo **hợp đồng tin cậy với IdP** và chính sách của tổ chức; một chuỗi do ứng dụng tự khai không chứng minh MFA đã được thực hiện. **Không nhúng bí mật, mật khẩu, PII không cần thiết hoặc chi tiết quyền nhạy cảm tùy tiện vào token.**

## 7. SSO thực sự có bao nhiêu phiên?

Trong hệ thống SSO thường có ít nhất hai lớp phiên:

1. **Phiên IdP:** giúp IdP biết người dùng đã xác thực và có thể thực hiện SSO sang ứng dụng khác mà không yêu cầu đăng nhập lại.
2. **Phiên ứng dụng (SP/RP):** cho người dùng tiếp tục sử dụng từng ứng dụng sau khi kết quả federation đã được xác minh.

Ngoài ra có thể có **access/refresh token**, API token hoặc session của proxy/gateway.

### Một tình huống dễ nhầm

Lan đăng nhập IdP lúc 09:00 và mở ứng dụng CRM. CRM tạo cookie phiên có hạn sử dụng theo chính sách riêng. Lúc 11:00, quản trị viên khóa account Lan tại IdP. **Điều này có thể chặn việc đăng nhập SSO mới nhưng không bảo đảm cookie CRM đã được thu hồi ngay.** Nếu ứng dụng không nhận sự kiện logout, không kiểm tra trạng thái người dùng hoặc không quản lý phiên phù hợp, cookie đó có thể còn dùng được cho đến khi hết hạn hoặc được hủy bằng cơ chế khác.

### Các lớp bảo vệ phiên

- Cookie nên có cấu hình bảo vệ phù hợp như **Secure, HttpOnly, SameSite** tùy kiến trúc và yêu cầu.
- Có giới hạn **idle timeout** và **absolute session lifetime** theo rủi ro.
- Chống session fixation, CSRF và chiếm session qua XSS hoặc lỗi cấu hình.
- Đánh giá **step-up authentication** khi thao tác nhạy cảm, không coi một lần đăng nhập sáng sớm là đủ cho mọi giao dịch.
- Áp cơ chế thu hồi/kiểm tra trạng thái ở ứng dụng khi có sự kiện Leaver, rủi ro cao hoặc thay đổi quyền.
- Với refresh token, đánh giá xoay vòng, phát hiện tái sử dụng và thu hồi theo nền tảng.

**SSO giảm số lần người dùng đăng nhập, không làm mọi phiên ứng dụng trở thành một phiên duy nhất có thể xóa bằng một lệnh chung.**

## 8. Logout, Single Logout và thu hồi truy cập

### Logout khỏi ứng dụng khác logout khỏi IdP

Khi người dùng bấm “Đăng xuất CRM”, CRM có thể xóa session riêng nhưng **phiên IdP vẫn còn**. Mở CRM lại có thể dẫn tới đăng nhập SSO gần như ngay lập tức vì IdP vẫn nhận diện được Lan. Ngược lại, logout khỏi IdP chưa chắc khiến mọi ứng dụng đã tạo session bị logout.

### Single Logout (SLO)

Một số giải pháp federation hỗ trợ cơ chế **Single Logout** hoặc **logout notification**, nhưng phạm vi và độ tin cậy phụ thuộc giao thức, binding, ứng dụng và thiết kế triển khai. Ví dụ:

- **SAML Single Logout** có cơ chế giao thức riêng; hỗ trợ giữa các SP khác nhau có thể không đồng đều.
- **OIDC logout** có những cơ chế trong hệ sinh thái như RP-initiated, front-channel hoặc back-channel logout khi các bên hỗ trợ và cấu hình phù hợp.
- **Front-channel** dựa trình duyệt có thể bị giới hạn bởi cookie, trình duyệt hoặc phiên không còn hoạt động.
- **Back-channel** có thể phù hợp hơn một số bối cảnh server-to-server nhưng vẫn đòi ứng dụng xác minh thông điệp và chủ động hủy session.

Không nên khẳng định **“có SSO = có single logout hoàn hảo”**.

### Thu hồi khi Leaver

Với người nghỉ việc, cần phối hợp **vô hiệu hóa identity tại IdP, thu hồi phiên/token, deprovision tài khoản/nhóm tại đích, chặn local account hoặc credential riêng và đối soát kết quả**. Mục tiêu là kiểm tra **trạng thái truy cập thực tế**, không chỉ sự kiện logout đã gửi.

## 9. MFA và assurance trong SSO

SSO giúp tập trung quy trình xác thực tại IdP, vì vậy chính sách **MFA, passkey, FIDO2/WebAuthn, điều kiện thiết bị và rủi ro phiên** có thể được áp dụng nhất quán cho nhiều ứng dụng.

Tuy nhiên, cần phân biệt:

- **IAL – Identity Assurance Level:** mức bảo đảm từ quá trình identity proofing của người đăng ký.
- **AAL – Authenticator Assurance Level:** mức bảo đảm của quá trình xác thực/phiên.
- **FAL – Federation Assurance Level:** mức bảo vệ xác thực liên kết giữa các bên.

Ba lớp độc lập về mục đích; **SSO không tự chứng minh IAL cao**, một session có MFA không tự tạo quyền nghiệp vụ, và việc dùng SAML/OIDC không tự bảo đảm FAL cụ thể.

### Step-up authentication

Giả sử Lan đang đọc báo cáo thông thường qua SSO. Khi Lan muốn đổi tài khoản nhận lương hoặc duyệt giao dịch giá trị lớn, ứng dụng có thể yêu cầu **xác thực lại hoặc dùng phương thức mạnh hơn** trước khi cho phép thao tác.

Ứng dụng không nên chỉ hiển thị một nút “Xác thực thành công” mà không kiểm tra **thời điểm xác thực, phương thức đã thực hiện, issuer, claim tin cậy và các điều kiện chính sách**. Trong OIDC, các cơ chế và tham số yêu cầu xác thực phù hợp cần được cấu hình với IdP; trong SAML, cần dùng ngữ cảnh xác thực và hợp đồng tin cậy tương ứng.

### Phishing-resistant authentication

**Security key FIDO2/WebAuthn** hoặc passkey được triển khai đúng cách có thể hỗ trợ xác thực chống phishing tại IdP. Điều này hữu ích vì **IdP là điểm tập trung đăng nhập của nhiều ứng dụng**. Dù vậy, bảo vệ đăng nhập không thay thế chống **đánh cắp session, malware, cấp quyền sai và các thao tác trên ứng dụng đã đăng nhập**.

## 10. SSO và việc liên kết đúng danh tính với account ứng dụng

Sau khi SP/RP xác minh kết quả của IdP, nó cần xác định **tài khoản ứng dụng nào** tương ứng với subject của assertion/token.

### Không chỉ dựa vào email

Email, tên đăng nhập và tên hiển thị có thể đổi hoặc tái sử dụng. Nếu hai nhân viên dùng lại một địa chỉ email theo thời gian, việc nối tài khoản bằng email có thể khiến nhân viên mới truy cập nhầm dữ liệu của người cũ.

Nên sử dụng một **định danh ổn định trong ngữ cảnh của issuer** và **account mapping** đã được xác minh:

| Bản ghi | Ví dụ | Ý nghĩa |
|---|---|---|
| Authoritative person ID | person-2046 | Chủ thể nguồn |
| IAM identity ID | iam-4bc7 | Danh tính trong hệ thống điều phối |
| IdP issuer | https://id.example.org | Không gian định danh của OP/IdP |
| OIDC subject | user-4bc7 | Định danh được OP cung cấp cho RP |
| SAML persistent identifier | Giá trị do IdP và SP thỏa thuận | Liên kết chủ thể qua SAML khi được cấu hình |
| Target account ID | crm-user-739 | Account thực tế trong ứng dụng |
| Relationship ID | employment-2026-2046 | Quan hệ hiện đang cấp căn cứ quyền |

**OIDC sub có ý nghĩa trong ngữ cảnh issuer.** Có triển khai dùng **pairwise subject identifiers** riêng theo client/sector, vì vậy không nên giả định cùng một chuỗi sub ở mọi ứng dụng. Account mapping cần dựa trên **hợp đồng định danh** của từng tích hợp.

### Just-in-Time (JIT) provisioning

Một số ứng dụng tự tạo local user **khi đăng nhập SSO lần đầu** nếu assertion/token hợp lệ. Đây là **JIT provisioning**.

Ưu điểm: giảm nhu cầu tạo account trước cho một số ứng dụng. Nhưng:

- JIT chỉ xảy ra **khi có lần đăng nhập**, nên chưa chắc account và quyền sẵn sàng trước ngày bắt đầu.
- Cần kiểm soát **ai được tạo account**, tenant, group mặc định và trạng thái lifecycle.
- Nếu claim sai hoặc mapping lỗi, JIT có thể tạo **account trùng hoặc cấp quyền không mong muốn**.
- JIT không bảo đảm **xóa/thu hồi account khi Leaver**, vì người nghỉ không đăng nhập để kích hoạt một hành động nào.

Vì vậy, JIT nên được kết hợp với **IGA/SCIM/API reconciliation** hoặc một cơ chế quản lý vòng đời tương đương khi yêu cầu tổ chức đòi hỏi.

## 11. SSO và SCIM: hai chức năng bổ trợ, không thay thế

**SCIM (System for Cross-domain Identity Management)** thường quản lý đối tượng user/group giữa hệ thống điều phối và ứng dụng đích. **SSO/federation** chuyển kết quả xác thực lúc người dùng đăng nhập.

| Tình huống | SSO xử lý | SCIM/Provisioning xử lý |
|---|---|---|
| Joiner vào làm | Ứng dụng có thể xác thực qua IdP | Tạo account, group, thuộc tính trước khi dùng |
| Mover đổi bộ phận | Có thể đăng nhập bằng cùng danh tính | Cập nhật nhóm, role và thu hồi quyền cũ |
| Leaver nghỉ việc | Chặn SSO mới tại IdP khi disable | Deactivate account đích và gỡ entitlement |
| Account bị khóa tại IdP | Ngăn một số luồng đăng nhập mới | Cần xử lý local account/session/token của đích |
| Người dùng cần MFA | IdP thực thi và chuyển tín hiệu tin cậy | Không phải chức năng quản lý nhóm của SCIM |
| Phát hiện account thừa | Không nhìn thấy hết local account | Inventory và reconciliation phải quét đích |

### Ví dụ lỗi đồng bộ

IAM đã cấp group **FINANCE_READER** qua SCIM nhưng IdP chưa cho phép đăng nhập do nhân viên chưa hoàn tất MFA. Như vậy **provisioning có thể thành công trong khi authentication chưa đạt**.

Ngược lại, người dùng đăng nhập SSO thành công nhưng group FINANCE_READER chưa đồng bộ tới SaaS. Khi đó **authentication thành công nhưng authorization ở ứng dụng không đủ**. Cần nêu chính xác trạng thái từng lớp và không tự cấp quyền rộng hơn để “sửa lỗi SSO”.

## 12. RBAC/ABAC trong hệ sinh thái SSO

**SSO trả lời “phiên này được xác thực như thế nào và cho ai?”**; **authorization trả lời “người này có quyền gì?”**.

Ứng dụng cần thực thi **Role-Based Access Control (RBAC)** và/hoặc **Attribute-Based Access Control (ABAC)**, xem xét trạng thái chủ thể, vai trò, tài nguyên, hành động và ngữ cảnh:

~~~text
function authorize(request, identity, session, resource):
    if identity.lifecycleState != ACTIVE:
        return DENY

    if not session.valid or not session.federationVerified:
        return REQUIRE_AUTHENTICATION

    if request.requiresStepUp and not session.assuranceSatisfied:
        return REQUIRE_STRONGER_AUTHENTICATION

    if not policyAllows(identity.roles, identity.attributes,
                        request.action, resource, request.context):
        return DENY

    return ALLOW
~~~

Đây là **giả mã**, không thể sử dụng trực tiếp như một middleware bảo mật hoàn chỉnh. Kiểm tra authorization phải sử dụng **trạng thái đáng tin cậy** và cần xử lý quyền thay đổi trong khi phiên vẫn hoạt động.

### Claims có phải sự thật vĩnh viễn?

Một SAML assertion hoặc ID token có thể chứa thông tin nhóm/role tại một thời điểm. Nếu Lan chuyển bộ phận sau khi token được phát hành, dữ liệu cũ có thể còn trong session/token. Ứng dụng nhạy cảm nên có cơ chế **cập nhật hoặc kiểm tra lại entitlement**, thời hạn cache phù hợp và khả năng thu hồi để hạn chế quyền tồn dư.

**Không dùng một claim tự khai, không có nguồn tin cậy hoặc không kiểm tra signature/audience để quyết định quyền.** Ngay cả claim đã được xác minh cũng phải nằm trong **hợp đồng nguồn dữ liệu** và chính sách phân quyền đã định.

## 13. SSO trong Joiner–Mover–Leaver

### 13.1. Joiner: tạo đúng danh tính và điều kiện đăng nhập

Một quy trình Joiner thường gồm:

1. HRIS gửi sự kiện gia nhập với **person ID, relationship ID và effectiveAt**.
2. IAM/IGA kiểm tra trùng danh tính, trạng thái quan hệ và kết quả proofing đã được tổ chức chấp nhận.
3. IdP tạo/chuẩn bị account theo chính sách; có thể chưa mở truy cập trước ngày hiệu lực.
4. Người dùng hoàn tất **identity enrollment**: phương thức xác thực, MFA/passkey, security key hoặc bước xác minh còn thiếu.
5. IAM provisioning account và nhóm tới ứng dụng qua **SCIM/API**, hoặc JIT theo tích hợp đã được phê duyệt.
6. Người dùng thực hiện SSO; SP/RP xác minh assertion/token và liên kết đúng account.
7. IAM kiểm tra trạng thái quyền thực tế và thông báo đã sẵn sàng **chỉ khi các điều kiện cần thiết đạt**.

**Người mới đã login IdP không chứng minh account ứng dụng đã có đủ quyền; account ứng dụng đã được tạo không chứng minh người đó đã hoàn tất MFA.**

### 13.2. Mover: đồng bộ quyền mới và gỡ quyền cũ

Khi chuyển từ Sales sang Finance, Lan có thể tiếp tục dùng **cùng IdP account và security key** nhưng phải thay đổi nhóm và quyền:

- Gỡ quyền Sales không còn phù hợp, bao gồm **quyền cấp trực tiếp, group và token liên quan** nếu thuộc phạm vi.
- Cấp quyền Finance theo approval, RBAC/ABAC, thời hạn và SoD.
- Đánh giá yêu cầu **step-up** hoặc MFA mạnh hơn nếu vai trò mới nhạy cảm.
- Cập nhật mapping, SCIM/API và kiểm tra phiên/cache ở ứng dụng có thể giữ quyền cũ.
- Đối soát để phát hiện **privilege accumulation** hoặc entitlement tồn dư.

**SSO giúp trải nghiệm đăng nhập nhất quán nhưng không tự gỡ quyền của vai trò cũ.**

### 13.3. Leaver: chặn cả SSO và đường truy cập độc lập

Khi quan hệ kết thúc theo nguồn có thẩm quyền:

1. Xác định **effectiveAt** và loại chấm dứt (theo lịch hoặc khẩn cấp).
2. Vô hiệu hóa account IdP hoặc chặn chính sách đăng nhập theo phạm vi.
3. Thu hồi phiên/refresh token/access token khi nền tảng hỗ trợ; không mặc định mọi token biến mất ngay.
4. Deactivate user/group tại hệ thống đích qua SCIM/API và xử lý **local account, session, PAT, API key, SSH key, VPN, cloud role, chứng chỉ** liên quan.
5. Kiểm tra các SP/RP có **WebAuthn credential đăng ký trực tiếp**, không chỉ IdP.
6. Đối soát trạng thái thực tế và xử lý lỗi từng connector bằng ticket có owner, hạn và biện pháp bù trừ.
7. Lưu audit và dữ liệu nghiệp vụ hợp lệ nhưng không để việc giữ record tạo đường đăng nhập.

**Leaver chưa hoàn tất nếu còn ứng dụng cho phép truy cập bằng phiên hoặc credential nằm ngoài SSO.**

### 13.4. Rejoiner: không tự mở lại quyền cũ

Một người tái gia nhập có thể dùng identity ID gốc để bảo toàn lịch sử, nhưng phải có quan hệ mới và được đánh giá lại về proofing, authenticator, account mapping và quyền. Không tự cho phép token/cookie, role và nhóm cũ quay lại chỉ vì IdP nhận thấy cùng email.

## 14. Bảo mật SSO: những rủi ro cần kiểm soát

SSO giảm số mật khẩu phải quản lý nhưng đồng thời **tập trung một phần rủi ro tại IdP**. Khi IdP hoặc quan hệ federation bị chiếm, nhiều ứng dụng có thể bị ảnh hưởng.

| Rủi ro | Ví dụ | Biện pháp |
|---|---|---|
| **Phishing/chiếm account IdP** | Attacker đăng nhập IdP để vào nhiều ứng dụng | MFA chống phishing, bảo vệ endpoint, giám sát phiên |
| **Token/assertion replay** | Thông điệp bị dùng lại ngoài ngữ cảnh hợp lệ | Challenge/correlation, nonce, hạn thời gian, chống replay |
| **Sai issuer/audience** | Ứng dụng chấp nhận token từ tenant hoặc client khác | Kiểm tra issuer, audience và metadata tin cậy |
| **Sai redirect URI** | Authorization code bị chuyển sang miền không hợp lệ | Redirect URI đăng ký chặt chẽ, PKCE, state |
| **Login CSRF / account mix-up** | Session được liên kết với tài khoản không mong muốn | State, kiểm tra issuer/nonce phù hợp, session binding |
| **SAML signature wrapping** | Ứng dụng đọc phần assertion khác phần đã ký | Thư viện chuẩn, xác minh chữ ký đúng node |
| **Federation misconfiguration** | Trust nhầm IdP, sai chứng chỉ hoặc cấu hình test ở production | Quản lý metadata, environment isolation và change control |
| **Session theft** | Cookie ứng dụng bị lấy sau khi xác thực | Cookie security, XSS/CSRF controls, session revoke |
| **Overprivileged claims** | Role cũ, group rộng hoặc claim chưa tin cậy | Authorization độc lập, least privilege, reconciliation |
| **JIT account sprawl** | Tài khoản tự tạo không có lifecycle đầy đủ | Điều kiện JIT, identity mapping, inventory và deprovision |
| **Logout không toàn diện** | IdP disabled nhưng RP session vẫn dùng được | Phối hợp logout/revoke và đối soát tại ứng dụng |
| **IdP outage** | Người dùng không thể đăng nhập ứng dụng mới | Resilience, DR, break-glass được kiểm soát |

### Phân tách môi trường và tenant

Mỗi ứng dụng cần cấu hình IdP, client/entity ID, endpoint, chứng chỉ/key và audience chính xác cho **môi trường và tenant được phép**. Không nên để môi trường thử nghiệm có thể tạo assertion/token được chấp nhận bởi môi trường production.

### Không dùng SSO làm lý do bỏ qua kiểm tra ứng dụng

Dù IdP đã xác thực mạnh, ứng dụng vẫn phải kiểm tra **dữ liệu và quyền tài nguyên ở mỗi thao tác quan trọng**. Một URL tài liệu không được phép không trở nên hợp lệ chỉ vì người dùng có SSO session.

## 15. Quản lý quan hệ tin cậy, chứng chỉ và khóa ký

SSO dựa vào **cấu hình tin cậy**: bên nhận phải biết IdP/OP nào được phép phát thông điệp, key/chứng chỉ nào hợp lệ và quy tắc nào cần được kiểm tra.

### Vòng đời trust material

- **Đăng ký:** quản trị viên thiết lập issuer/entity ID, endpoint, metadata và key được phê duyệt.
- **Xác minh:** ứng dụng sử dụng nguồn metadata/JWKS tin cậy, kiểm tra signature/audience/issuer.
- **Xoay vòng:** cập nhật key/chứng chỉ theo cửa sổ chuyển tiếp, thử nghiệm và kế hoạch rollback.
- **Thu hồi:** gỡ quan hệ IdP không còn được tin cậy, vô hiệu cấu hình cũ, đảm bảo cache và ứng dụng đã cập nhật.
- **Kiểm toán:** ghi thay đổi metadata, owner tích hợp, người duyệt, thời điểm và phạm vi ảnh hưởng.

### SAML metadata và OIDC discovery

**SAML** thường dùng metadata trao đổi entity ID, endpoint và chứng chỉ. **OIDC** có cơ chế discovery và **JWKS** để client tìm cấu hình và khóa công khai. Tuy nhiên, client không được tin một URL JWKS ngẫu nhiên do attacker đặt trong token; nguồn phải được ràng buộc với issuer đã cấu hình tin cậy.

**Không tắt kiểm tra chữ ký hoặc chấp nhận mọi chứng chỉ để khắc phục lỗi SSO.** Khi rotation lỗi, cần khắc phục metadata, lịch sử key và cấu hình trong phạm vi đã phê duyệt, không giảm tính an toàn của giao thức.

## 16. SSO cho nhân viên và xác thực máy–máy khác nhau

**SSO qua trình duyệt** thường dành cho con người. **Service account, bot, device và workload identity** có thể dùng các mô hình xác thực khác, không phù hợp khi bắt một bot “đăng nhập như nhân viên”.

| Chủ thể | Cách tiếp cận thường phù hợp | Kiểm soát vòng đời |
|---|---|---|
| Nhân viên | IdP/SSO với MFA hoặc passkey | JML, enrollment, access review, session revoke |
| Nhà thầu/đối tác | Federation tới IdP được chấp thuận hoặc guest identity | Quan hệ bảo trợ và ngày hết hạn |
| API service | OAuth client credentials hoặc danh tính máy khác khi phù hợp | Client owner, scope, secret/cert lifecycle |
| Cloud workload | Workload identity federation/managed identity | Ràng buộc workload, policy, token ngắn hạn |
| Thiết bị được quản lý | Device identity, PKI hoặc attestation khi hỗ trợ | Enroll, compliant state, certificate revoke |
| Break-glass human account | Quy trình xác thực khẩn cấp có kiểm soát | Owner, bảo vệ credential, giám sát và thử nghiệm |

Không chia sẻ mật khẩu SSO của một nhân viên để bot gọi API. Khi nhân viên owner nghỉ việc, cần **chuyển owner và rà soát quyền/secret của service account**, thay vì xóa mù quáng workload còn được phép vận hành.

**OAuth client credentials không phải SSO cho người dùng.** Nó phục vụ quyền của client/workload theo phạm vi được cấp, không mặc nhiên đại diện cho một nhân viên đã xác thực.

## 17. Khả năng sẵn sàng, fallback và vận hành sự cố IdP

SSO tập trung xác thực giúp quản trị thuận tiện nhưng cũng khiến nhiều ứng dụng phụ thuộc vào **khả năng sẵn sàng của IdP**, cấu hình DNS/TLS và metadata federation.

### Thiết kế vận hành

- Đánh giá SLA/SLO xác thực, HA, khôi phục thảm họa và kênh hỗ trợ khi IdP không khả dụng.
- Quản lý phiên ứng dụng có thời hạn và chính sách rõ để cân bằng khả dụng với rủi ro.
- Dự phòng key/chứng chỉ và kiểm thử rotation có kiểm soát.
- Giám sát lỗi callback, issuer/audience mismatch, endpoint timeout, certificate expiry và tỷ lệ login failure.
- Kiểm soát các **local fallback accounts** hoặc break-glass: có owner, quyền tối thiểu, vault, giám sát và review; không biến fallback thành đường bỏ qua MFA thường trực.
- Với ứng dụng tối quan trọng, quyết định chế độ **fail closed/fail safe** dựa trên rủi ro; không tự mở rộng quyền khi IdP gặp sự cố.

### Khi người dùng báo “SSO không hoạt động”

Không nên ngay lập tức đặt lại mật khẩu hoặc tắt MFA. Trước hết cần xác định sự cố xảy ra **trước xác thực, tại giao thức federation, lúc liên kết account hay lúc kiểm tra quyền**. Mỗi lớp có bằng chứng và người xử lý khác nhau.

## 18. Chẩn đoán lỗi SSO có phương pháp

Một runbook nên ghi nhận **correlation ID, client/entity ID, issuer, thời điểm, môi trường, loại giao thức và kết quả từng bước**, tránh thu thập token hoặc assertion thô vào ticket phổ thông.

| Dấu hiệu | Nguyên nhân khả dĩ | Kiểm tra phù hợp |
|---|---|---|
| Không mở được trang IdP | DNS, TLS, mạng, IdP outage | Sức khỏe endpoint và mạng |
| IdP từ chối xác thực | Account disabled, MFA/policy không đạt | Trạng thái lifecycle và authentication event |
| OIDC callback báo invalid state | Session bị mất, callback không khớp, lỗi tích hợp | State binding, cookie và redirect URI |
| OIDC invalid issuer/audience | Sai client, tenant hoặc trust config | Issuer/client ID/JWKS cấu hình |
| OIDC code exchange thất bại | Code hết hạn/dùng lại, PKCE sai, token endpoint lỗi | Logs an toàn và cấu hình flow |
| SAML invalid signature | Key/chứng chỉ rotation hoặc XML sai | Metadata, signature validation và key đang hoạt động |
| SAML response expired | Lệch đồng hồ hoặc assertion quá hạn | Đồng bộ thời gian và điều kiện thời hạn |
| SAML invalid recipient/audience | SP endpoint/entity ID sai | ACS/Destination/Audience và metadata |
| SSO thành công nhưng thiếu quyền | SCIM/group chưa đồng bộ hoặc policy từ chối | Desired vs observed entitlements |
| Đăng xuất nhưng mở lại vẫn vào | Phiên IdP còn, local session còn hoặc SLO không hiệu quả | Session tại từng bên và logout policy |
| Leaver vẫn truy cập được ứng dụng | Local account, token hoặc cookie chưa thu hồi | Deprovision, session revoke và đối soát tại đích |

### Các bước xử lý

1. Xác định tài khoản và ứng dụng đúng bằng ID tin cậy, không chỉ tên/email.
2. Kiểm tra trạng thái HRIS/JML, IdP và chính sách truy cập.
3. Đối chiếu luồng giao thức (SAML/OIDC), cấu hình trust và sự kiện xác thực.
4. Kiểm tra mapping từ subject của issuer tới target account.
5. Phân biệt lỗi **authentication** và **authorization** bằng readback quyền ứng dụng.
6. Sửa theo thay đổi được phê duyệt, không vô hiệu kiểm tra chữ ký, không tự cấp quyền rộng.
7. Thử lại có kiểm soát và ghi bằng chứng kết quả, session/logout, quyền thực tế.
8. Với Leaver, ưu tiên **chặn đường truy cập** và mở incident/ticket nếu chưa thể thu hồi.

## 19. Kiểm toán SSO và những chỉ số cần theo dõi

### Sự kiện nên ghi

- Đăng nhập IdP: kết quả, thời điểm, identity ID, phương thức và mức assurance đã được xác minh.
- Yêu cầu federation: client/entity ID, issuer, giao thức, correlation ID, thời gian, kết quả kiểm tra.
- Đăng ký/thu hồi trust: metadata, cert/key rotation, người phê duyệt.
- Cấp và kết thúc phiên ứng dụng, yêu cầu step-up, logout/revoke.
- Lỗi provisioning, kết quả SCIM/API và chênh lệch quyền.
- JML: effectiveAt, account disable, local session/token revoke, trạng thái deprovision tại ứng dụng.
- Trường hợp bất thường: login nhiều lần thất bại, account mix-up, claim sai hoặc issuer không được tin.

**Không ghi plaintext password, refresh token, access token, SAML assertion chứa PII hoặc session cookie vào log/ticket thông thường.** Chỉ lưu phần metadata và tham chiếu cần thiết, bảo vệ theo chính sách. Khi cần thu thập mẫu để điều tra, phải xử lý trong môi trường và quyền truy cập phù hợp.

### Chỉ số vận hành

| Chỉ số | Diễn giải |
|---|---|
| **SSO adoption/coverage** | Tỷ lệ ứng dụng/người dùng được quản lý qua cơ chế SSO phù hợp |
| **Successful authentication rate** | Tỷ lệ phiên xác thực thành công, theo client/flow |
| **Federation validation errors** | Lỗi issuer, audience, signature, callback và thời gian |
| **MFA/phishing-resistant coverage** | Mức áp chính sách MFA/chống phishing cho nhóm rủi ro |
| **Session revocation latency** | Độ trễ từ yêu cầu thu hồi đến khi ứng dụng xác nhận đóng đường truy cập |
| **Deprovisioning residual access** | Account/credential/session còn hoạt động sau effectiveAt của Leaver |
| **Access mismatch count** | Người đã SSO thành công nhưng quyền đích chưa đúng |
| **Trust/certificate expiry risk** | Cấu hình hoặc chứng chỉ sắp hết hạn chưa có kế hoạch xử lý |
| **Fallback exception aging** | Local login/break-glass ngoại lệ tồn tại quá hạn |
| **App reconciliation coverage** | Tỷ lệ ứng dụng/quyền/phiên có thể kiểm tra thực tế |

Chỉ số **“người dùng đăng nhập SSO thành công”** không phản ánh đầy đủ trạng thái bảo mật nếu quyền cũ vẫn còn hoặc token ứng dụng không được thu hồi sau Leaver.

## 20. Ví dụ xuyên suốt: từ nhân viên mới tới nghỉ việc

Giả sử **Minh** gia nhập tổ chức ngày **01/12/2026**, làm tại Finance, sau chuyển sang Analytics rồi nghỉ việc. Tổ chức có IdP dùng OIDC/SAML, ứng dụng Finance qua SAML, portal Analytics qua OIDC và một SaaS được provision qua SCIM.

### Giai đoạn A — Joiner

HRIS tạo hồ sơ Minh với định danh bền vững, ngày có hiệu lực và kết quả xác minh danh tính theo chính sách. IAM/IGA tạo account IdP, hướng dẫn Minh đăng ký phương thức xác thực mạnh, đặt policy theo role Finance. Connector SCIM tạo account SaaS và group baseline. Trước ngày bắt đầu, account có thể ở trạng thái chưa cho truy cập đúng theo quy định.

### Giai đoạn B — Đăng nhập bằng SSO

Minh đăng nhập IdP bằng passkey/security key theo yêu cầu; sau đó mở Finance (SAML SP) và Analytics (OIDC RP). Mỗi ứng dụng kiểm tra thông điệp federation, ánh xạ subject tới đúng target account và áp RBAC/ABAC. Mặc dù không cần nhập lại password mỗi lần, **mỗi ứng dụng vẫn giữ session và quyền riêng**.

### Giai đoạn C — Mover

Minh chuyển sang Analytics. HRIS phát sự kiện Mover mới; IAM thu hồi quyền Finance không còn hợp lệ, cấp quyền Analytics theo phê duyệt và tăng yêu cầu MFA cho truy cập nhạy cảm khi cần. Minh vẫn dùng cùng IdP account. Nếu cookie Finance cũ còn tồn tại, ứng dụng cần kiểm tra quyền cập nhật/thu hồi phiên theo chính sách để không giữ quyền Finance chỉ vì SSO phiên trước đó còn hiệu lực.

### Giai đoạn D — Leaver

Khi HRIS phát Leaver có hiệu lực, IAM khóa đăng nhập IdP, thu hồi phiên/token và điều phối SCIM/API vô hiệu account ứng dụng. Một ứng dụng Finance legacy có local credential ngoài SSO. Vì vậy IAM phải thu hồi riêng local account, session và token, rồi đối soát. Nếu một connector thất bại, workflow vẫn **PARTIAL/OPEN**, có owner và thời hạn; không công bố hoàn tất khi còn đường truy cập.

### Giai đoạn E — Rejoiner

Minh tái gia nhập vào vị trí khác. IAM đánh giá quan hệ mới, proofing/enrollment phù hợp, tính lại quyền và ràng buộc subject/target account chính xác. **Không tự phục hồi group Finance, credential cũ hoặc session đã thu hồi.**

Ví dụ nhấn mạnh: **SSO tập trung trải nghiệm xác thực**, trong khi **quản trị vòng đời danh tính và quyền yêu cầu provisioning, authorization, session management và reconciliation độc lập nhưng phối hợp**.

## 21. Checklist triển khai Single Sign-On trong IAM Lifecycle

1. **Kiến trúc:** đã xác định IdP/OP, SAML SP, OIDC RP, issuer/entity ID, tenant và owner từng tích hợp chưa?
2. **Giao thức:** đã phân biệt SAML assertion, OIDC ID token và OAuth access/refresh token chưa?
3. **Trust:** ứng dụng xác minh chữ ký, issuer, audience, thời hạn, endpoint và request correlation đúng giao thức chưa?
4. **OIDC:** có authorization code flow, PKCE khi cần, state, nonce theo luồng và redirect URI được kiểm soát chưa?
5. **SAML:** có kiểm tra AuthnRequest/InResponseTo, Destination/Recipient, Conditions, audience và chống replay/wrapping chưa?
6. **Identity mapping:** đã dùng subject ổn định theo issuer và mapping đáng tin thay vì email/name duy nhất chưa?
7. **MFA:** IdP áp authentication policy đúng rủi ro; ứng dụng có yêu cầu step-up đáng tin cho thao tác nhạy cảm không?
8. **Provisioning:** SSO đã được phân biệt với SCIM/JIT/API; account/group/role ở đích có được đối soát không?
9. **Authorization:** mỗi ứng dụng vẫn thực thi RBAC/ABAC, tenant isolation, SoD và least privilege chưa?
10. **Joiner:** account, enrollment, MFA, ngày hiệu lực và quyền baseline có được kiểm tra riêng chưa?
11. **Mover:** role cũ được thu hồi, claim/cache/phiên được xử lý và quyền mới có phê duyệt chưa?
12. **Leaver:** IdP disable có đi cùng thu hồi phiên/token, local accounts, credential riêng và kiểm tra hệ thống đích chưa?
13. **Logout:** đã phân biệt IdP logout, app logout, SAML/OIDC SLO và giới hạn thu hồi session chưa?
14. **Non-human:** bot/workload không dùng chung mật khẩu SSO của người; có owner, danh tính máy và credential lifecycle riêng chưa?
15. **Resilience:** đã chuẩn bị IdP outage, key rotation, DR và break-glass/fallback theo chính sách chưa?
16. **Monitoring:** có correlation ID, metrics, reconciliation coverage và alert cho lỗi trust, token hoặc residual access không?
17. **Bảo vệ dữ liệu:** token, assertion, password, session cookie và PII không bị lộ qua log, analytics hoặc ticket chưa?
18. **Đóng vòng đời:** chỉ đánh dấu hoàn tất khi trạng thái truy cập đúng tại mọi hệ thống thuộc phạm vi đã được xác minh chưa?

### Ghi nhớ

**Single Sign-On giúp người dùng truy cập nhiều ứng dụng thông qua một quan hệ xác thực tập trung, nhưng không đồng nghĩa mọi ứng dụng chia sẻ một phiên duy nhất hoặc tự động đồng bộ quyền.** SAML và OIDC cần kiểm tra đầy đủ nguồn phát, chữ ký, đối tượng nhận, thời hạn và điều kiện bảo mật; OAuth access token không được nhầm với ID token. Trong vòng đời **Joiner–Mover–Leaver**, SSO phải phối hợp với **identity proofing, MFA, SCIM provisioning, RBAC/ABAC, quản lý phiên và đối soát hệ thống đích**. Khi người dùng thay đổi vai trò hoặc nghỉ việc, chỉ khóa đăng nhập IdP là chưa đủ nếu **session, token, local account và entitlement tồn dư** vẫn cho phép truy cập.
