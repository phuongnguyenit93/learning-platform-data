# MFA là gì? Xác thực đa yếu tố trong quản lý vòng đời danh tính

> **Chương:** MFA  
> **Bài:** MFA là gì  
> **Module:** `SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE`  
> **Phạm vi:** Giải thích Multi-Factor Authentication, các yếu tố và phương pháp xác thực, độ bảo đảm và cách quản lý MFA xuyên vòng đời **Joiner–Mover–Leaver**. Liên hệ IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, kiểm toán và giảm quyền truy cập tồn dư.

## 1. MFA giải quyết bài toán nào?

Một nhân viên có mật khẩu đăng nhập đúng chưa chắc là chủ sở hữu hợp pháp của tài khoản: mật khẩu có thể bị lộ trong một vụ rò rỉ dữ liệu, bị đoán, dùng lại từ website khác hoặc bị lấy qua trang đăng nhập giả. Nếu ứng dụng chỉ kiểm tra một mật khẩu, kẻ tấn công có được mật khẩu sẽ có cơ hội đăng nhập như người dùng.

**MFA (Multi-Factor Authentication, xác thực đa yếu tố)** là cơ chế yêu cầu người đăng nhập chứng minh danh tính bằng **ít nhất hai yếu tố xác thực thuộc các nhóm khác nhau**, được kiểm tra theo giao thức và chính sách phù hợp. Mục tiêu là giảm khả năng một kẻ tấn công vượt qua xác thực chỉ nhờ chiếm một loại bằng chứng.

Ví dụ, nhân viên Lan truy cập hệ thống báo cáo:

1. Lan nhập mật khẩu: bằng chứng về **điều Lan biết**.
2. Lan sử dụng security key hoặc ứng dụng xác thực trên thiết bị mình kiểm soát: bằng chứng về **điều Lan sở hữu/kiểm soát**.
3. Hệ thống kiểm tra kết quả và, nếu đạt chính sách, thiết lập phiên đăng nhập.

Nếu kẻ tấn công biết mật khẩu mà không kiểm soát yếu tố thứ hai, yêu cầu đăng nhập thường bị chặn. Tuy nhiên, MFA **không** tự ngăn tất cả các cuộc tấn công: mã OTP có thể bị lừa nhập vào website giả, phiên đã xác thực có thể bị chiếm và quy trình khôi phục tài khoản có thể bị lợi dụng.

### 1.1. MFA nằm ở đâu trong IAM?

IAM (Identity and Access Management) trả lời những câu hỏi khác nhau:

- **Identity proofing:** người được tạo danh tính có thực sự là người được khai báo không?
- **Authentication:** người đang yêu cầu truy cập có chứng minh được danh tính không? MFA hỗ trợ bước này.
- **Authorization:** người đã xác thực có được phép thực hiện hành động trên tài nguyên cụ thể không?
- **Lifecycle:** khi vào làm, đổi vai trò hay rời tổ chức, danh tính, authenticator, quyền và phiên được cập nhật/thu hồi như thế nào?
- **Audit:** có bằng chứng ai, vào lúc nào, theo phương thức nào, đã truy cập hoặc bị từ chối hay không?

Một người dùng hoàn tất MFA mạnh vẫn không được duyệt thanh toán nếu không có role `payment.approver`. Ngược lại, người có role này vẫn có thể bị yêu cầu xác thực bổ sung khi truy cập qua thiết bị không tin cậy hoặc thực hiện giao dịch rủi ro cao.

**MFA là kiểm soát xác thực; nó không thay thế phân quyền, giám sát hoặc thu hồi quyền.**

## 2. Ba nhóm yếu tố xác thực cơ bản

MFA không được xác định bằng số màn hình hay số lần nhấp, mà bằng **loại bằng chứng** được sử dụng.

| Nhóm yếu tố | Câu hỏi hệ thống kiểm tra | Ví dụ | Rủi ro cần hiểu |
|---|---|---|---|
| **Something you know — Kiến thức** | Bạn biết bí mật nào? | Mật khẩu, PIN bí mật phù hợp | Phishing, tái sử dụng mật khẩu, bị lộ hoặc đoán |
| **Something you have — Sở hữu/kiểm soát** | Bạn kiểm soát thiết bị/khóa nào? | Security key, smart card, authenticator giữ khóa, thiết bị TOTP | Thiết bị bị mất, seed/khóa bị sao chép, mã bị relay |
| **Something you are — Sinh trắc** | Một đặc điểm sinh trắc có được xác minh không? | Vân tay, khuôn mặt, mống mắt khi triển khai phù hợp | Giả mạo cảm biến, sai số, khó thay đổi đặc điểm khi bị lộ |

### 2.1. Vì sao hai mật khẩu chưa phải MFA?

Mật khẩu đăng nhập và một “mật khẩu cấp hai” tĩnh đều thuộc nhóm **something you know**. Dù người dùng nhập vào hai màn hình, ứng dụng vẫn đang kiểm tra **hai bí mật cùng loại**, không tự tạo thành xác thực đa yếu tố.

Tương tự:

- Mật khẩu + câu hỏi bảo mật: đều là knowledge, thường rất yếu.
- Mật khẩu + một PIN tĩnh khác nhập vào website: vẫn là knowledge.
- Mật khẩu + mã TOTP từ một ứng dụng xác thực riêng: có thể đáp ứng MFA nhờ thêm yếu tố kiểm soát thiết bị/secret.
- Khóa mật mã trên thiết bị + xác minh người dùng cục bộ bằng PIN hoặc sinh trắc: có thể đáp ứng yêu cầu đa yếu tố với một **authenticator đa yếu tố**, tùy thiết kế và policy.

Vì vậy, **hai yếu tố không nhất thiết đòi hai thiết bị**. Điều quan trọng là bằng chứng sở hữu khóa và việc xác minh người dùng có được kết hợp an toàn, được verifier kiểm tra đúng, và có đáp ứng chính sách bảo đảm hay không.

### 2.2. Vị trí và hành vi có phải yếu tố MFA?

Địa chỉ IP, địa điểm, giờ làm việc, loại thiết bị, tín hiệu EDR và hành vi bất thường có thể hữu ích cho **risk-based authentication**. Nhưng chúng thường được coi là **tín hiệu ngữ cảnh/rủi ro**, không mặc nhiên là một nhóm yếu tố MFA độc lập tương đương possession hay knowledge.

Ví dụ, “đúng mật khẩu + đang ở mạng văn phòng” không nên tự được quảng bá là MFA chuẩn, vì mạng có thể bị chia sẻ/giả mạo và không trực tiếp chứng minh người dùng kiểm soát một authenticator riêng.

## 3. MFA, 2FA, authenticator và credential

Cần phân biệt:

| Thuật ngữ | Ý nghĩa | Ví dụ |
|---|---|---|
| **SFA** | Xác thực dựa trên một nhóm yếu tố | Chỉ mật khẩu |
| **2FA** | Hai yếu tố thuộc nhóm khác nhau | Mật khẩu + authenticator TOTP |
| **MFA** | Ít nhất hai yếu tố thuộc những nhóm độc lập | Mật khẩu + security key, hoặc authenticator đa yếu tố phù hợp |
| **Authentication factor** | Loại bằng chứng | Knowledge, possession, inherence |
| **Authenticator** | Thiết bị/phần mềm dùng để chứng minh yếu tố | FIDO security key, ứng dụng OTP, platform authenticator |
| **Credential** | Vật liệu/bí mật liên kết với một danh tính | Mật khẩu, khóa riêng, seed TOTP |
| **Verifier** | Bên kiểm tra bằng chứng xác thực | IdP, authentication server hoặc relying party |
| **Authenticator enrollment/binding** | Quá trình gắn authenticator vào danh tính | Đăng ký passkey cho user `emp-108` |
| **Authentication assurance** | Mức tin cậy vào kết quả xác thực theo chính sách/giao thức | Yêu cầu bảo đảm cao hơn cho tài khoản quản trị |

Một phương thức “không dùng mật khẩu” vẫn có thể là MFA: passkey dùng khóa mật mã cùng PIN/sinh trắc cục bộ là ví dụ thường gặp khi các yêu cầu kiểm chứng được đáp ứng. Ngược lại, không phải mọi lần sử dụng một passkey hoặc khóa xác thực đều có **cùng mức bảo đảm**; cần xét user verification, phương án lưu/đồng bộ khóa, loại authenticator và chính sách của bên xác minh.

## 4. Các phương pháp MFA phổ biến

### 4.1. Mật khẩu + TOTP

**TOTP (Time-based One-Time Password)** tạo mã ngắn thay đổi theo thời gian từ một bí mật được chia sẻ giữa ứng dụng xác thực và server xác minh.

Luồng thường gặp:

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant App as Ứng dụng
    participant I as IdP / Verifier
    participant T as Ứng dụng TOTP
    U->>App: Yêu cầu đăng nhập
    App->>I: Chuyển đến bước xác thực
    U->>I: Cung cấp mật khẩu
    I->>I: Kiểm tra mật khẩu và chính sách
    I->>U: Yêu cầu mã TOTP
    U->>T: Mở ứng dụng xác thực
    T-->>U: Hiển thị mã hiện tại
    U->>I: Nhập mã TOTP
    I->>I: Kiểm tra seed, cửa sổ thời gian, rate limit
    I-->>App: Kết quả xác thực
~~~

**Ưu điểm:** hỗ trợ trên nhiều hệ thống, không phụ thuộc SMS, dễ triển khai cho nhiều tài khoản.  
**Giới hạn:** mã vẫn có thể bị thu thập và chuyển tiếp theo thời gian thực qua trang giả mạo; seed dùng tạo mã phải được bảo vệ và thu hồi/đăng ký lại nếu nghi bị sao chép.

Lưu ý: TOTP thường dùng kết hợp mật khẩu; chỉ nhập một mã TOTP mà không có bằng chứng độc lập khác **không mặc nhiên** là MFA.

### 4.2. Mật khẩu + SMS/thoại

Hệ thống gửi mã qua số điện thoại mà user kiểm soát. Cách này đơn giản về trải nghiệm nhưng có những điểm yếu: SIM swap, chuyển số, chuyển tiếp tin nhắn, lừa nhập mã hoặc mất vùng phủ sóng.

Trong thiết kế hiện đại, SMS/thoại thường được đánh giá là yếu tố có **rủi ro cao hơn phương thức chống phishing bằng mật mã** và có thể bị giới hạn hoặc không được chấp nhận đối với một số mức bảo đảm. Không nên dùng SMS làm bằng chứng duy nhất cho tài khoản quản trị khi có giải pháp phù hợp hơn.

Số điện thoại là **kênh có thể thay đổi người kiểm soát**, không phải định danh bất biến của nhân viên.

### 4.3. Push approval

Ứng dụng xác thực hiển thị yêu cầu đăng nhập, user chọn chấp nhận hoặc từ chối. Cách này có thể tiện dụng nhưng dễ gặp **push fatigue**: kẻ tấn công đã biết mật khẩu gửi nhiều yêu cầu cho tới khi user bấm chấp nhận vì nhầm lẫn hoặc mệt mỏi.

Cải thiện có thể gồm **number matching**, hiển thị ngữ cảnh yêu cầu, rate limiting, khóa tạm khi bất thường và hướng dẫn báo sự cố. Number matching giảm một số kiểu chấp nhận nhầm nhưng **không làm push approval tự trở thành phishing-resistant theo cùng cơ chế với WebAuthn**.

### 4.4. Security key, smart card và chứng chỉ

Các thiết bị này thường dùng khóa mật mã và đôi khi có PIN hoặc bước xác minh người dùng. Có thể phù hợp cho quyền nhạy cảm khi tổ chức quản lý tốt:

- Nguồn cấp phát, người sở hữu và binding vào identity.
- Bảo vệ khóa riêng và điều kiện sử dụng.
- Giao thức/chính sách xác minh bằng chứng.
- Mất/hỏng, khóa dự phòng và quy trình thu hồi.
- Thời hạn chứng chỉ và vòng đời khóa nếu dùng PKI.

**Không nên coi mọi dạng chứng chỉ là chống phishing như nhau**: phải đánh giá chứng chỉ dùng ở giao thức nào, có ràng buộc được đúng endpoint/phiên hay không và quy trình cấp phát có đáng tin cậy không.

### 4.5. Passkey và FIDO2/WebAuthn

**WebAuthn** cho phép authenticator tạo và dùng khóa bất đối xứng để xác thực cho một dịch vụ (*Relying Party, RP*). RP giữ khóa công khai, còn khóa riêng được authenticator quản lý. Khi đăng nhập, RP gửi thử thách mới, authenticator ký bằng chứng phù hợp với **RP ID/origin** và chính sách user presence/user verification.

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant B as Trình duyệt / client
    participant F as Authenticator FIDO
    participant R as RP / IdP
    U->>B: Chọn đăng nhập bằng passkey
    B->>R: Yêu cầu challenge
    R-->>B: Challenge và thông tin RP
    B->>F: WebAuthn get() theo RP ID
    F->>U: Yêu cầu xác minh cục bộ nếu cần
    U-->>F: PIN hoặc sinh trắc phù hợp
    F-->>B: Assertion và chữ ký
    B->>R: Gửi assertion
    R->>R: Kiểm tra challenge, RP ID, origin, chữ ký và UP/UV
    R-->>B: Thành công hoặc từ chối
~~~

**Điểm mạnh về chống phishing:** trang giả mạo ở một origin khác không thể chỉ thu thập mã rồi dùng lại assertion hợp lệ cho RP thực, nếu WebAuthn được triển khai và xác minh đúng. Đây là khác biệt quan trọng so với OTP mà user tự nhập.

Cần tránh hai suy diễn:

- **“Dùng passkey thì hết mọi rủi ro.”** Sai: session bị chiếm, recovery yếu, thiết bị mất hoặc cấu hình RP sai vẫn tạo rủi ro.
- **“Mọi passkey đều có mức assurance giống nhau.”** Sai: passkey gắn thiết bị và passkey có thể đồng bộ khác nhau về mô hình bảo vệ khóa và quản trị; mức bảo đảm phụ thuộc giải pháp, policy và yêu cầu của hệ thống.

## 5. So sánh các phương thức theo mục tiêu bảo mật

| Phương thức | Trải nghiệm | Chống phishing | Quản trị vòng đời |
|---|---|---|---|
| Mật khẩu + SMS | Tương đối phổ biến, phụ thuộc sóng di động | Không có bảo vệ origin; có thể bị relay | Quản lý số, SIM swap, thiết bị và mất máy |
| Mật khẩu + TOTP | Phổ biến, dùng được offline | Mã có thể bị phishing/relay | Bảo vệ seed, đăng ký lại khi mất thiết bị |
| Mật khẩu + push | Thao tác nhanh | Cần biện pháp giảm push fatigue; không mặc nhiên chống phishing | Quản lý thiết bị và phiên ứng dụng xác thực |
| Passkey/WebAuthn có kiểm tra phù hợp | Ít nhập liệu, hỗ trợ nhiều thiết bị/nền tảng | Có ràng buộc với RP/origin; chống kiểu phishing mã thông thường | Gắn credential, bảo vệ user verification, backup/recovery |
| Security key phần cứng với xác minh user | Cần thiết bị vật lý, phù hợp quyền nhạy cảm | Có thể chống phishing khi dùng FIDO2/WebAuthn đúng | Cấp phát, thay khóa, khóa dự phòng, thu hồi |
| Smart card/PKI | Phù hợp một số môi trường quản trị | Phụ thuộc giao thức/cách triển khai | Chứng chỉ, CA, hạn, revocation, card lifecycle |

Không có một phương thức duy nhất tốt nhất cho mọi người và mọi tài nguyên. Một tổ chức cần cân nhắc **rủi ro, khả năng truy cập cho người dùng, thiết bị hỗ trợ, chi phí vận hành, khôi phục và mức bảo đảm mong muốn**.

## 6. MFA khác risk-based authentication và step-up ở điểm nào?

**MFA** trả lời cần sử dụng những yếu tố nào để xác thực. **Risk-based authentication** quyết định mức kiểm tra dựa trên ngữ cảnh và tín hiệu đáng tin cậy, còn **step-up authentication** yêu cầu xác thực thêm hoặc mạnh hơn khi hành động nhạy cảm xảy ra.

Ví dụ, nhân viên Bình đã đăng nhập SSO để đọc bản tin nội bộ. Bình chuyển sang chức năng duyệt thanh toán:

1. Ứng dụng biết thao tác sắp diễn ra là `payment.approve`.
2. Policy kiểm tra user role, mức nhạy cảm khoản tiền và mức xác thực đã đạt.
3. Nếu lần xác thực chưa đủ mạnh hoặc đã quá cũ, IdP yêu cầu step-up.
4. Sau khi step-up, API vẫn kiểm tra Bình có được duyệt khoản đó không.

Cần phân biệt: **step-up đủ mạnh nhưng thiếu role** vẫn phải từ chối; **role hợp lệ nhưng mức xác thực không đủ** cũng phải từ chối hoặc yêu cầu bổ sung.

### 6.1. Authentication assurance

Mức bảo đảm xác thực không thể chỉ suy ra từ câu “đã bật MFA”. Một policy có thể xét:

- Chất lượng và số nhóm yếu tố thực sự được chứng minh.
- Khả năng chống phishing, chống phát lại và bảo vệ khóa.
- Quy trình đăng ký authenticator và kiểm tra user verification.
- Bảo vệ session, thời gian từ lần xác thực cuối và khả năng khôi phục.
- Khả năng phát hiện/ứng phó khi authenticator bị mất hoặc bị đánh cắp.

Những hệ thống tham chiếu chuẩn về Authentication Assurance Level (AAL) cần ánh xạ theo **điều kiện cụ thể của từng chuẩn và phiên bản**, không nên tự gán cấp bằng cách nhìn tên phương thức.

## 7. MFA hoạt động trong kiến trúc IdP và SSO

Trong mô hình **Identity Provider (IdP)**, user đăng nhập tại một bên cung cấp danh tính. Nhiều ứng dụng có thể dùng **Single Sign-On (SSO)** với OIDC hoặc SAML để nhận kết quả xác thực, không cần mỗi ứng dụng tự giữ mật khẩu.

~~~mermaid
flowchart TD
    U[Người dùng] --> APP[Ứng dụng doanh nghiệp]
    APP --> IDP[IdP / SSO]
    IDP --> POL[Chính sách xác thực]
    POL --> AUTH[Authenticator đã đăng ký]
    AUTH --> IDP
    IDP --> RESULT[Kết quả xác thực theo giao thức]
    RESULT --> APP
    APP --> API[API / điểm thực thi phân quyền]
    API --> DATA[(Tài nguyên được bảo vệ)]
    GROUP[Group, role, thuộc tính IAM] --> API
    POLICY[RBAC / ABAC / resource policy] --> API
~~~

Đây là sơ đồ khái niệm. Trên thực tế, phần authentication và authorization có thể nằm tại nhiều thành phần và cần tuân thủ giao thức riêng.

### 7.1. ID token và access token không giống nhau

Trong OIDC:

- **ID token** dùng để truyền thông tin về kết quả xác thực người dùng tới client phù hợp.
- **Access token** phục vụ gọi API có scope/role/audience được xác minh.
- **Session cookie** duy trì đăng nhập ở IdP hoặc ứng dụng theo cách mỗi bên quản lý.

Một ID token cho biết lần đăng nhập đã được chấp nhận không tự cấp quyền sử dụng mọi API. Tương tự, việc IdP xác thực MFA không tự chứng minh user còn quyền duyệt thanh toán tại hệ thống đích.

### 7.2. Thông tin về phương thức xác thực trong OIDC

Một số hệ thống dùng những trường như:

- `amr`: phương thức xác thực đã tham gia theo quy ước của issuer.
- `acr`: lớp/ngữ cảnh xác thực theo hợp đồng giữa issuer và relying party.
- `auth_time`: thời điểm user được xác thực theo giao thức.

**Tên và giá trị claim không có ngữ nghĩa giống nhau ở mọi IdP.** Ứng dụng phải kiểm tra chữ ký/nguồn token, audience, thời hạn và quy ước policy chính thức của issuer; không đơn thuần thấy chuỗi `mfa` là tuyên bố đáp ứng mọi yêu cầu.

### 7.3. SSO có xóa được mọi phiên sau Leaver không?

Không nhất thiết. IdP có thể chặn đăng nhập mới, nhưng ứng dụng SaaS có thể giữ session cookie riêng hoặc API vẫn chấp nhận token đã phát hành đến lúc hết hạn. Do đó, **thu hồi quyền và phiên tại ứng dụng đích** là một phần của IAM lifecycle, không thể chỉ dựa vào MFA/SSO.

## 8. SCIM, RBAC và ABAC liên quan gì tới MFA?

| Thành phần | Trách nhiệm chính | Không nên nhầm với |
|---|---|---|
| **MFA/IdP** | Xác thực chủ thể bằng bằng chứng phù hợp | Cấp quyền truy cập dữ liệu nghiệp vụ |
| **SSO** | Cho phép nhiều ứng dụng dùng kết quả xác thực tập trung | Thu hồi mọi local account/session khi user rời tổ chức |
| **SCIM** | Provisioning/đồng bộ User, Group theo hệ thống hỗ trợ | Giao thức mặc định để đăng ký passkey, TOTP seed hoặc revoke mọi token |
| **RBAC** | Vai trò xác định tập quyền | Chứng minh người cầm credential thực sự là chủ thể |
| **ABAC** | Quyết định quyền dựa trên thuộc tính subject/resource/action/context | Thay thế kiểm tra authentication |
| **PAM/JIT** | Kiểm soát đặc quyền và thời hạn sử dụng | Miễn trừ MFA/step-up cho người quản trị |

Ví dụ: Lan thuộc role `finance-viewer` và truy cập từ thiết bị được quản lý bằng MFA chống phishing. API vẫn phải từ chối `invoice.delete` vì role không cho phép. Nếu Lan được bổ nhiệm làm người phê duyệt, IAM có thể cập nhật quyền qua RBAC/ABAC, đồng thời yêu cầu MFA thích hợp khi quyền mới có hiệu lực.

### 8.1. Ví dụ policy kết hợp MFA với quyền

~~~text
function approveInvoice(request):
    principal = authenticateAndValidateSession(request)
    invoice = loadInvoiceFromTrustedStorage(request.invoiceId)

    if principal.status != "ACTIVE":
        return DENY

    if not principal.hasRole("invoice-approver"):
        return DENY

    if invoice.businessUnit != principal.businessUnit:
        return DENY

    if not principal.authenticationContext.meetsPolicy("approval-high"):
        return REQUIRE_STEP_UP

    if invoice.createdBy == principal.id:
        return DENY  # Ngăn tự tạo và tự duyệt khi chính sách SoD cấm

    return ALLOW
~~~

Đây là **pseudocode**, không phải cấu hình của một vendor cụ thể. Thông tin role, phiên và yếu tố đã sử dụng phải lấy từ nguồn đã được xác minh; không tin các HTTP header tự khai báo như `X-MFA-Completed: true`.

## 9. MFA trong Joiner: đăng ký và xác minh authenticator

Joiner bao gồm tạo danh tính, xác minh người mới, cấp tài khoản và **đăng ký phương thức xác thực**. Chỉ gửi email “hãy tự bật MFA” có thể chưa đủ nếu đường dẫn đăng ký hoặc bước xác minh ban đầu dễ bị người khác chiếm.

### 9.1. Luồng enrollment tham khảo

1. **Nguồn danh tính:** HRIS/hợp đồng hoặc hệ thống phù hợp xác nhận identity ID, trạng thái và ngày bắt đầu.
2. **Identity proofing:** bảo đảm người đến đăng ký thực sự được gán với danh tính cần cấp.
3. **Bootstrap có kiểm soát:** dùng kênh khởi tạo hợp lệ, thời hạn ngắn và các bước kiểm tra tương xứng rủi ro.
4. **Chọn authenticator:** dựa trên chính sách, độ nhạy cảm, thiết bị và nhu cầu hỗ trợ tiếp cận.
5. **Bind authenticator:** liên kết credential với identity ổn định, không chỉ tên/email có thể đổi.
6. **Xác minh hoạt động:** người đăng ký thực hiện thử thách để chứng minh kiểm soát authenticator.
7. **Thiết lập dự phòng:** chuẩn bị cách đăng nhập dự phòng/khôi phục hợp lệ tránh khóa người dùng khi mất thiết bị.
8. **Kiểm tra tại đích:** ứng dụng nhận kết quả đủ mạnh, và các thao tác không có quyền vẫn bị từ chối.
9. **Audit:** ghi nhận sự kiện, loại authenticator, người phê duyệt và thời điểm; không lưu bí mật thô.

### 9.2. Ví dụ trạng thái đăng ký

~~~json
{
  "identityId": "emp-108",
  "eventType": "AUTHENTICATOR_ENROLLED",
  "authenticatorId": "auth-key-092",
  "method": "WEBAUTHN",
  "status": "ACTIVE",
  "ownerTeam": "identity-security",
  "registrationVerified": true,
  "registeredAt": "2026-11-23T09:00:00+07:00",
  "correlationId": "IAM-JOIN-118"
}
~~~

Đây là dữ liệu minh họa, không phải schema chuẩn. Tuyệt đối không ghi seed TOTP, mật khẩu, mã dự phòng, private key hoặc token truy cập nguyên dạng vào audit log.

### 9.3. Người không thể dùng một phương thức bắt buộc

Có người không có smartphone cá nhân, không thể dùng một dạng sinh trắc, làm việc ở khu vực không có sóng hoặc phải dùng thiết bị chia sẻ. Chính sách MFA cần có **phương án thay thế có bảo đảm tương xứng** và quy trình hỗ trợ rõ ràng, thay vì vô hiệu hóa MFA cho mọi trường hợp ngoại lệ.

## 10. MFA trong Mover: đổi thiết bị, đổi vai trò và tăng đặc quyền

Mover không nhất thiết là chuyển phòng ban. Nhân viên có thể đổi số điện thoại, thay máy tính, tiếp nhận dự án mới hoặc được cấp quyền nhạy cảm tạm thời. Những thay đổi này có thể làm **phương thức xác thực cũ không còn phù hợp**.

| Sự kiện Mover | Điều cần xét | Rủi ro nếu bỏ sót |
|---|---|---|
| Nhân viên trở thành quản trị viên production | Bảo đảm xác thực cao hơn, step-up, PAM/JIT | Dùng phương thức yếu để nhận quyền mạnh |
| Đổi điện thoại chạy authenticator | Bind thiết bị mới, revoke thiết bị cũ | Thiết bị cũ vẫn có mã/khả năng đăng nhập |
| Chuyển từ dùng máy công ty sang BYOD | Device policy, session, loại authenticator | Không thỏa yêu cầu thiết bị khi truy cập dữ liệu nhạy cảm |
| Đổi số điện thoại | Xác minh người yêu cầu, kênh recovery, SIM swap | Kẻ tấn công chiếm quyền khôi phục |
| Kết thúc ca quản trị khẩn cấp | Thu hồi bypass/JIT permission, kiểm tra session | Đặc quyền còn tồn dư sau thời hạn |
| Chuyển đội hoặc thay người quản lý | Rà soát owner và các đường cấp quyền | Người cũ giữ quyền quản trị authenticator hoặc nhóm |

### 10.1. Thay authenticator an toàn

Giả sử Mai làm mất điện thoại dùng TOTP:

1. Ghi nhận sự kiện và đánh giá rủi ro credential/session.
2. Xác minh Mai qua quy trình recovery được phê duyệt, không chỉ dựa trên cuộc gọi.
3. Thu hồi authenticator bị mất nếu không còn đáng tin.
4. Đăng ký authenticator mới, xác minh dùng được.
5. Cân nhắc giới hạn phiên hoặc chấm dứt token nếu tình huống cho thấy có nguy cơ bị chiếm quyền.
6. Thông báo thay đổi qua kênh đã được xác nhận, theo dõi truy cập bất thường.
7. Ghi audit đủ dữ liệu chứng minh user/owner và các bước xử lý.

**Mất một yếu tố xác thực không đồng nghĩa Leaver của cả người dùng.** User có thể tiếp tục làm việc khi hoàn thành quy trình thay thế được kiểm soát.

### 10.2. Không để bypass trở thành quyền thường trực

Trong sự cố, nhân viên có thể được cho dùng cơ chế dự phòng khẩn cấp theo chính sách. Khi sự cố kết thúc, mọi bypass, exception, quyền quản trị và credential tạm phải **hết hạn và được đối soát**. Một cơ chế MFA exception tồn tại vô thời hạn có thể là đường tấn công làm vô hiệu các kiểm soát mạnh hơn.

## 11. MFA trong Leaver: kết thúc khả năng xác thực và quyền còn tồn tại

Khi nhân viên chấm dứt hợp đồng, chỉ **xóa một security key** không đủ nếu user còn mật khẩu, TOTP, passkey đồng bộ hoặc phiên ứng dụng. Ngược lại, **khóa user tại IdP** chưa chắc đã làm token và phiên cũ ở mọi SaaS hết hiệu lực.

Quy trình Leaver nên bao gồm:

1. **Sự kiện có thẩm quyền:** identity ID ổn định và thời điểm kết thúc từ nguồn nghiệp vụ.
2. **Chặn phiên mới:** vô hiệu hóa hoặc hạn chế đăng nhập tại IdP theo chính sách.
3. **Authenticator:** thu hồi/unbind các credential còn liên kết khi cần theo chính sách và công nghệ.
4. **Tài khoản ứng dụng:** dùng connector/SCIM/API để khóa account, gỡ group, role và quyền tại đích.
5. **Phiên và token:** thu hồi refresh token/session khi hỗ trợ, đánh giá access token đã phát hành và hạn còn lại.
6. **Đường truy cập khác:** kiểm tra local login, VPN, SSH, API key và quyền đặc quyền.
7. **Bàn giao:** chuyển dữ liệu và ownership công việc mà không giữ tài khoản người nghỉ việc hoạt động.
8. **Readback:** xác minh account/role/credential ở những hệ thống liên quan đã về trạng thái kỳ vọng.
9. **Bằng chứng:** lưu các kết quả, lỗi connector, ngoại lệ và người chịu trách nhiệm.

Để tránh nhầm lẫn, cần tách:

- **Disable account:** chặn khả năng đăng nhập theo đường đã quản lý.
- **Revoke authenticator:** bỏ liên kết giữa yếu tố và danh tính.
- **Revoke access:** gỡ quyền trên ứng dụng/tài nguyên.
- **Invalidate session/token:** làm mất hiệu lực phiên hoặc token theo cơ chế hỗ trợ.

Bốn thao tác này có liên quan nhưng không đồng nghĩa; tùy nền tảng có thể cần các bước riêng.

## 12. Recovery là một phần của an ninh MFA

Nếu tổ chức dùng WebAuthn để chống phishing nhưng helpdesk cho phép tắt MFA ngay sau một cuộc điện thoại không xác minh danh tính, kẻ tấn công sẽ nhắm vào **quy trình recovery** thay vì tìm cách phá khóa mật mã.

Những kịch bản điển hình:

- Giả làm người dùng đang đi công tác và “mất điện thoại, cần mở gấp”.
- Chiếm số điện thoại qua SIM swap rồi đặt lại authenticator.
- Lấy quyền email recovery trước khi đăng ký yếu tố mới.
- Chiếm một session có đặc quyền quản lý thiết bị xác thực.
- Đánh cắp mã dự phòng hoặc tài liệu chứa QR đăng ký TOTP.
- Lợi dụng quyền helpdesk để thay authenticator không có phê duyệt.

### 12.1. Nguyên tắc recovery có kiểm soát

- Xác minh lại danh tính với mức độ tương xứng quyền truy cập.
- Chỉ dùng kênh/nguồn xác minh đáng tin, không tin caller ID hoặc thông tin dễ tra cứu.
- Tài khoản đặc quyền có thể cần kiểm tra độc lập, xác nhận bởi người quản lý hoặc cấp duyệt thích hợp.
- Thu hồi thiết bị/credential bị mất; xem xét phiên/token đã phát hành.
- Ghi rõ ai xử lý, phương thức xác minh, thời điểm và lý do.
- Thông báo qua kênh tin cậy khi authenticator bị thêm/xóa.
- Nếu cần, hạn chế một số quyền nhạy cảm ngay sau recovery và theo dõi đăng nhập bất thường.

**Một cơ chế recovery yếu có thể kéo mức an toàn thực tế của MFA xuống ngang mắt xích yếu nhất.**

## 13. MFA không giải quyết được những nguy cơ nào?

Bảng sau giúp chọn biện pháp bổ sung thay vì chỉ tăng số lần yêu cầu MFA.

| Nguy cơ | MFA giúp gì? | Kiểm soát bổ sung |
|---|---|---|
| Mật khẩu bị lộ | Thường chặn login nếu kẻ tấn công thiếu yếu tố khác | MFA chống phishing, kiểm tra mật khẩu lộ, phát hiện đăng nhập |
| Trang login giả lấy TOTP | MFA kiểu OTP vẫn có thể bị relay | FIDO2/WebAuthn, đào tạo và bảo vệ phiên |
| Chiếm session cookie sau login | Không chặn được mọi trường hợp | Bảo vệ session, timeout, token binding khi có hỗ trợ, giám sát |
| Ứng dụng có lỗi IDOR/BOLA | MFA không sửa lỗi phân quyền tài nguyên | RBAC/ABAC, kiểm tra quyền trong API với từng object |
| Quyền admin được cấp quá rộng | MFA chỉ xác thực người dùng quyền cao | Least privilege, SoD, PAM/JIT, access review |
| Helpdesk bị lừa reset MFA | MFA có thể bị vô hiệu qua recovery | Identity re-proofing, approval và audit |
| Thiết bị có malware | MFA không bảo đảm endpoint không bị chiếm | Endpoint security, device compliance, cách ly rủi ro |
| Token dịch vụ/API key bị lộ | MFA của user không chặn token của workload | Workload identity, secret rotation, giới hạn scope |
| Nhân viên đã nghỉ nhưng SaaS còn phiên | Khóa MFA ở IdP có thể chưa hủy session SaaS | Deprovision account, session/token revoke, readback |

MFA là một lớp trong chiến lược bảo vệ danh tính; cần phối hợp với **identity lifecycle, phân quyền, bảo vệ thiết bị, kiểm toán và xử lý sự cố**.

## 14. Tài khoản dịch vụ có MFA không?

Một workload như `billing-sync`, pipeline CI/CD hoặc service account thường chạy tự động, không có người để nhập OTP hoặc xác minh sinh trắc. Yêu cầu một kỹ sư bấm OTP mỗi lần job chạy có thể dẫn đến dùng chung tài khoản cá nhân hoặc tắt kiểm soát.

**Machine authentication** có các phương án riêng, chẳng hạn:

- Workload identity federation dựa trên issuer/subject/audience và trust policy chặt chẽ.
- OAuth 2.0 Client Credentials với phương thức xác thực client được phê duyệt.
- Chứng chỉ và mTLS khi kiến trúc/giao thức phù hợp.
- Credential ngắn hạn được cấp theo workload/role và giới hạn phạm vi.
- Secret manager, rotation và thu hồi API key nếu nền tảng còn yêu cầu secret tĩnh.

Không nên gọi các cơ chế machine-to-machine này là “MFA của user” chỉ vì có nhiều bước mật mã. **Người vận hành các workload**, khi đăng nhập để quản trị credential hoặc production, vẫn phải chịu chính sách MFA/step-up phù hợp.

Trong JML của service account, cần có owner, môi trường, mục đích, role, trust binding và cơ chế thu hồi riêng. Khi chủ kỹ thuật nghỉ việc, chuyển ownership của workload còn hoạt động và thu hồi quyền cá nhân; không để một script vận hành mãi nhờ tài khoản cá nhân đã nghỉ.

## 15. Tình huống thực hành: tích hợp MFA vào một hệ thống doanh nghiệp

Doanh nghiệp có ba ứng dụng:

- **NewsPortal:** bản tin nội bộ.
- **CRM:** dữ liệu khách hàng theo chi nhánh.
- **PaymentAdmin:** phê duyệt giao dịch tài chính.

Chính sách minh họa:

| Ứng dụng hoặc hành động | Quyền nghiệp vụ | Yêu cầu xác thực |
|---|---|---|
| Đọc NewsPortal | Nhân viên còn trạng thái active | SSO và yêu cầu cơ sở theo chính sách |
| Xem khách hàng trong CRM | Role `crm.viewer`, đúng chi nhánh | MFA phù hợp và chính sách thiết bị |
| Xuất toàn bộ khách hàng | Quyền `crm.export` có phê duyệt | Step-up hoặc phương thức mạnh hơn tùy rủi ro |
| Duyệt thanh toán | Role `payment.approver`, đúng hạn mức, SoD | MFA có mức bảo đảm cao, xác thực đủ mới |
| Quản trị IdP | Role quản trị được phê duyệt | Phương thức chống phishing, PAM/JIT, audit |

### 15.1. Một yêu cầu duyệt thanh toán

Nhân viên An có role `payment.approver` và đăng nhập bằng mật khẩu + TOTP. Khi An duyệt khoản tiền lớn, policy yêu cầu phương thức mạnh hơn và xác thực đủ mới.

~~~mermaid
sequenceDiagram
    participant A as An
    participant UI as PaymentAdmin
    participant I as IdP
    participant API as Payment API
    A->>UI: Bấm duyệt giao dịch
    UI->>API: Yêu cầu duyệt
    API->>API: Kiểm tra role, hạn mức, SoD, auth context
    API-->>UI: Step-up required
    UI->>I: Yêu cầu nâng mức xác thực
    I->>A: Thử thách theo phương thức đạt policy
    A-->>I: Hoàn thành xác thực
    I-->>UI: Kết quả mới theo giao thức
    UI->>API: Gửi lại yêu cầu có bằng chứng hợp lệ
    API->>API: Xác minh token, freshness, role, dữ liệu giao dịch
    API-->>UI: Cho phép hoặc từ chối
~~~

Sơ đồ minh họa nguyên tắc, không phải mô tả cách mọi sản phẩm truyền auth context. Việc API yêu cầu xác thực mạnh hơn phải được ràng buộc với chính sách và bằng chứng tin cậy; không dựa vào `mfaCompleted=true` do trình duyệt tự gửi.

### 15.2. Sau Mover và Leaver

Khi An chuyển vai trò sang kiểm toán, IAM thu hồi `payment.approver`, bổ sung quyền xem báo cáo theo phê duyệt và rà soát MFA/step-up phù hợp. Nếu auth context đã đạt mức cao, API **vẫn phải từ chối duyệt thanh toán** vì role đã bị thu hồi.

Khi An nghỉ việc, IdP chặn xác thực mới và deprovision account tại PaymentAdmin/CRM. Cần xử lý phiên/token, authenticator và quyền tồn dư; chỉ coi hoàn tất khi trạng thái được kiểm chứng ở các đích theo khả năng hệ thống.

## 16. Kiểm toán MFA: nên ghi nhận điều gì?

Một audit log MFA hữu ích cần giúp giải thích **vì sao hệ thống chấp nhận hoặc từ chối một lần xác thực** mà không làm lộ bí mật.

| Nhóm thông tin | Giá trị cần có |
|---|---|
| Chủ thể | Identity ID ổn định, loại danh tính, trạng thái tại thời điểm yêu cầu |
| Sự kiện | Đăng ký, đăng nhập, step-up, thất bại, gỡ authenticator, recovery, bypass |
| Authenticator | Loại phương thức và ID metadata, không lưu secret |
| Chính sách | Phiên bản policy, ứng dụng/action được yêu cầu, mức bảo đảm cần có |
| Ngữ cảnh | Thời gian, device/risk indicators phù hợp và nguồn dữ liệu |
| Quyết định | Thành công, từ chối, yêu cầu step-up, lý do |
| Vòng đời | Event JML, chủ sở hữu, approval và thời điểm hiệu lực |
| Đối soát | Trạng thái authenticator, phiên/token hoặc quyền đích đã được xác minh chưa |

Ví dụ một sự kiện giả lập:

~~~json
{
  "eventId": "mfa-event-2026-041",
  "identityId": "emp-108",
  "eventType": "STEP_UP_AUTHENTICATION",
  "relyingParty": "payment-admin",
  "requestedAction": "payment.approve",
  "authenticatorType": "WEBAUTHN",
  "policyId": "approval-high-assurance",
  "result": "SUCCESS",
  "verifiedAt": "2026-11-23T09:15:00+07:00",
  "correlationId": "TX-8405"
}
~~~

Các trường chỉ minh họa. Không ghi mật khẩu, mã OTP, seed TOTP, private key, recovery codes hay token thô. Thông tin sinh trắc cũng không nên bị đưa vào log chỉ vì hệ thống dùng cảm biến vân tay.

### 16.1. Các chỉ số vận hành hữu ích

1. **Tỷ lệ tài khoản yêu cầu MFA đã đăng ký authenticator phù hợp**, phân theo nhóm rủi ro.
2. **Tỷ lệ đăng nhập bằng phương thức chống phishing** ở các ứng dụng nhạy cảm.
3. **Số bypass/exception MFA quá hạn** và owner cần xử lý.
4. **Thời gian xử lý mất authenticator hoặc recovery**, kết hợp chất lượng xác minh, không chỉ tốc độ.
5. **Số lần phát sinh push bất thường và số lần từ chối**, để hỗ trợ phát hiện hành vi.
6. **Tỷ lệ step-up thành công** và số yêu cầu bị chặn đúng chính sách.
7. **Thời gian thu hồi authenticator/phiên sau Leaver**, phân biệt lệnh gửi và trạng thái đích.
8. **Số danh tính hoặc credential mồ côi**, không có owner hoặc không còn công việc hợp lệ.

Cần xác định rõ mẫu số, nguồn dữ liệu và giới hạn telemetry. Ví dụ, một user có hai authenticator không đồng nghĩa với việc mọi đăng nhập của user đều dùng MFA chống phishing.

## 17. Các sai lầm phổ biến

**“Hai bước đăng nhập chắc chắn là MFA.”** Không; hai bí mật đều thuộc knowledge có thể vẫn là một nhóm yếu tố.

**“Mật khẩu + TOTP chống được mọi phishing.”** Không; TOTP có thể bị thu thập và relay. Phương thức có ràng buộc RP/origin thường chống kiểu tấn công này tốt hơn.

**“SMS là một định danh lâu dài của user.”** Không; số điện thoại có thể thay đổi quyền kiểm soát và là mục tiêu của SIM swap.

**“Sinh trắc tự động được gửi về server để xác thực passkey.”** Không đúng với luồng WebAuthn điển hình; xác minh người dùng thường diễn ra cục bộ trên authenticator, còn RP xác minh bằng chứng mật mã.

**“Dùng MFA mạnh thì không cần RBAC/ABAC.”** Sai; authentication và authorization là hai quyết định khác nhau.

**“IdP disable user nghĩa là mọi phiên SaaS biến mất.”** Không mặc định; cần cơ chế xử lý account/session ở đích.

**“SCIM quản lý được tất cả authenticator.”** SCIM chủ yếu là provisioning User/Group; không tự động đăng ký/thu hồi mọi passkey và token.

**“Mất điện thoại thì tắt MFA cho nhanh.”** Recovery yếu có thể trở thành cửa ngõ takeover; cần kiểm tra danh tính và phương án bảo đảm phù hợp.

**“Máy với máy phải dùng tài khoản của nhân viên để nhập OTP.”** Nên tách workload identity và cơ chế machine authentication theo thiết kế phù hợp.

## 18. Tình huống tự kiểm tra

### Tình huống A: hai bí mật

Một website yêu cầu người dùng nhập mật khẩu và một câu trả lời bí mật thứ hai. Quản trị viên gọi đó là “2FA”.

**Phân tích:** Cả hai đều thuộc knowledge; không tự đạt MFA hai nhóm. Cần xem xét phương thức sở hữu/kiểm soát hoặc authenticator đa yếu tố phù hợp.

### Tình huống B: TOTP bị phishing

Bình nhập mật khẩu và TOTP vào trang giả. Kẻ tấn công lập tức dùng thông tin đó đăng nhập website thật.

**Phân tích:** MFA kiểu OTP không ràng buộc origin, nên có thể bị relay. Cần xem xét WebAuthn/FIDO2 và các biện pháp bảo vệ session.

### Tình huống C: user vượt qua MFA nhưng không có quyền

Mai dùng passkey hợp lệ, rồi cố mở báo cáo lương của phòng ban khác.

**Phân tích:** API vẫn phải kiểm tra role/attribute và quyền trên dữ liệu; MFA không cấp quyền kinh doanh.

### Tình huống D: chuyển vai trò

Lan chuyển từ nhân viên kế toán sang kiểm toán, nhưng vẫn còn role `payment.approver`. Lan hoàn thành MFA mạnh rồi duyệt một khoản tiền.

**Phân tích:** Đây là lỗi Mover/deprovision quyền cũ, không phải lỗi thiếu MFA. IAM phải gỡ role và xác minh effective access tại đích.

### Tình huống E: helpdesk bị lừa

Một người gọi tự nhận giám đốc đã mất điện thoại, yêu cầu gỡ passkey và thêm thiết bị mới ngay.

**Phân tích:** Yêu cầu khẩn không thay quy trình identity re-proofing. Cần xác minh độc lập, approval/hậu kiểm theo rủi ro, thu hồi credential mất và giám sát phiên.

### Tình huống F: account rời tổ chức

IdP khóa account của Nam lúc 18:00. 18:05 Nam vẫn truy cập SaaS qua cookie cũ.

**Phân tích:** Leaver chưa hoàn tất trên SaaS. Cần kiểm tra session và quyền tại ứng dụng, áp dụng revoke/containment theo khả năng và lưu bằng chứng.

## 19. Checklist khi triển khai MFA trong IAM

Trước khi đưa một chính sách MFA vào vận hành:

1. **Xác định đối tượng:** tài khoản nhân viên, đối tác, quản trị viên hay workload? Tránh áp cơ chế tương tác của người dùng cho job máy.
2. **Nhận diện yếu tố:** có ít nhất hai nhóm yếu tố phù hợp hoặc authenticator đa yếu tố đáp ứng yêu cầu thực tế?
3. **Mục tiêu bảo đảm:** ứng dụng/action nào cần phishing-resistant, step-up, thiết bị được quản lý?
4. **Đăng ký ban đầu:** đã identity proofing và binding authenticator đúng identity ID chưa?
5. **Bí mật/khóa:** private key, TOTP seed, recovery codes có được bảo vệ không?
6. **Chống phishing:** phương thức có ràng buộc RP/origin hay vẫn dựa vào mã có thể relay?
7. **Dự phòng và tiếp cận:** người dùng không có smartphone hoặc không dùng sinh trắc có phương án phù hợp?
8. **Recovery:** mất thiết bị, đổi số điện thoại và reset MFA có quy trình xác minh độc lập?
9. **IdP/SSO:** ứng dụng có kiểm tra auth context từ nguồn tin cậy và độ mới xác thực đúng yêu cầu?
10. **SCIM:** có phân biệt user provisioning với authenticator management không?
11. **RBAC/ABAC:** API vẫn xét role, resource, scope và SoD sau khi MFA hoàn tất?
12. **Mover:** thay thiết bị/vai trò có rà soát yếu tố, session, bypass và JIT/privilege?
13. **Leaver:** đã disable account, revoke authenticator, deprovision quyền và kiểm tra token/session?
14. **Giám sát:** có phát hiện push fatigue, thay đổi yếu tố trái phép và hành vi đăng nhập bất thường?
15. **Audit:** có event ID, owner, policy, kết quả, thời gian và bằng chứng readback?
16. **Ngoại lệ:** bypass khẩn cấp có owner, lý do và thời điểm hết hạn rõ ràng?

---

**Ghi nhớ:** MFA là yêu cầu chứng minh danh tính bằng **nhiều yếu tố thuộc những nhóm bằng chứng độc lập**, không phải chỉ tăng số lần nhập dữ liệu. Những phương thức chống phishing như WebAuthn/FIDO2 có thể bảo vệ tốt hơn trước việc đánh cắp mã OTP, nhưng vẫn cần bảo vệ phiên và recovery. Trong quản lý vòng đời **Joiner–Mover–Leaver**, MFA phải được quản trị từ **đăng ký, sử dụng, nâng mức, thay thế, khôi phục đến thu hồi**; chỉ khi kết hợp IdP/SSO, quyền RBAC/ABAC, provisioning/deprovisioning và kiểm toán, tổ chức mới giảm được nguy cơ chiếm tài khoản và **quyền truy cập tồn dư**.
