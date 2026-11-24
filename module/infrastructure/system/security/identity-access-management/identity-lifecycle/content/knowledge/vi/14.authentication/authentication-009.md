# Step-up authentication – xác thực tăng cường trong IAM lifecycle

## Mục tiêu học tập

Sau bài học, người học có thể:

- Giải thích **step-up authentication** là gì và phân biệt với đăng nhập ban đầu, xác thực lại, MFA, identity proofing và authorization.
- Xác định các hành động nhạy cảm cần nâng mức bảo đảm xác thực, dựa trên rủi ro, phương thức đã sử dụng, độ mới của lần xác thực và ngữ cảnh phiên.
- Thiết kế luồng step-up giữa ứng dụng, **Identity Provider (IdP)**, người dùng và điểm thực thi quyền ở backend.
- Hiểu cách sử dụng và xác minh các tín hiệu **OIDC, SAML và WebAuthn/passkey**, cùng giới hạn của mỗi loại tín hiệu.
- Liên kết step-up với **Joiner–Mover–Leaver (JML)**, SSO, SCIM, RBAC/ABAC, tài khoản đặc quyền và danh tính phi con người.
- Kiểm soát phiên, challenge, hành động có rủi ro cao, khôi phục authenticator, truy cập tồn dư và bằng chứng kiểm toán.

## 1. Step-up authentication là gì?

**Step-up authentication (xác thực tăng cường)** là quá trình yêu cầu người dùng **chứng minh lại hoặc bổ sung bằng chứng xác thực với mức bảo đảm phù hợp hơn** trước một tác vụ có rủi ro cao hơn so với hoạt động thông thường của phiên hiện tại.

Ví dụ, nhân viên đã đăng nhập SSO để đọc tài liệu. Khi họ yêu cầu cấp quyền quản trị, xuất dữ liệu nhạy cảm hoặc đổi phương thức MFA, ứng dụng có thể yêu cầu xác thực mạnh hơn hoặc xác thực lại đủ mới, dù phiên hiện tại chưa hết hạn.

Step-up dựa trên nguyên tắc **phiên đăng nhập hợp lệ không tự động đủ tin cậy cho mọi thao tác trong toàn bộ thời gian phiên tồn tại**.

Trong module **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**, step-up hỗ trợ bảo vệ thao tác dùng danh tính đã được provision và xác thực. Nó **không thay thế** việc xác minh danh tính ban đầu, phê duyệt quyền, quản lý RBAC/ABAC, đồng bộ SCIM hay thu hồi quyền khi Mover/Leaver.

### 1.1. Các khái niệm liên quan

| Khái niệm | Câu hỏi cần trả lời | Điểm khác biệt |
| --- | --- | --- |
| **Identity proofing** | Chủ thể được khai báo có đúng là người/thực thể trong hồ sơ? | Tạo cơ sở tin cậy về danh tính, không cấp quyền |
| **Authentication** | Người dùng có kiểm soát authenticator đã đăng ký không? | Là một lần chứng minh danh tính trong ngữ cảnh xác thực |
| **MFA** | Có kết hợp các yếu tố xác thực theo yêu cầu không? | Không mặc nhiên chống phishing hoặc đủ độ mới |
| **Reauthentication** | Người dùng có thực hiện xác thực lại không? | Có thể dùng phương thức cũ, chưa nâng assurance |
| **Step-up** | Với hành động này, mức bảo đảm và độ mới hiện tại đã đủ chưa? | Có thể đòi phương thức mạnh hơn hoặc một lần xác thực mới |
| **Authorization** | Người dùng có được phép làm thao tác đó không? | Cần role, thuộc tính, resource, approval và policy |
| **Transaction authorization** | Chủ thể có chấp thuận đúng nội dung giao dịch không? | Cần cơ chế ràng buộc kết quả với giao dịch cụ thể |

**Xác thực thành công không đồng nghĩa được cấp quyền.** Nhân viên không có entitlement quản trị thì vẫn phải bị từ chối ngay cả sau khi hoàn thành step-up.

**Xác thực lại không đồng nghĩa nâng mức bảo đảm.** Việc nhập lại mật khẩu có thể đáp ứng freshness trong một số trường hợp, nhưng không tự đạt yêu cầu MFA hay phishing-resistant authentication.

## 2. Vì sao đăng nhập SSO một lần chưa đủ?

Khi đăng nhập qua IdP, ứng dụng có thể nhận ID token hoặc assertion và thiết lập phiên cục bộ. Phiên đó có thể sống lâu hơn bối cảnh đã dùng để đánh giá rủi ro ban đầu:

- Người dùng chuyển từ xem tài liệu sang xóa dữ liệu hoặc đổi quyền production.
- Thiết bị, mạng hoặc hành vi truy cập có tín hiệu bất thường.
- Cookie/phiên bị đánh cắp và được dùng lại bởi kẻ tấn công.
- Người dùng được bổ sung role đặc quyền theo workflow Mover.
- Claim về department hoặc role trong phiên/ID token đã cũ.
- Chính sách yêu cầu xác thực **gần thời điểm phê duyệt giao dịch**.
- Người dùng vừa khôi phục MFA, nên quyền nhạy cảm cần thêm kiểm soát.

**SSO giúp ứng dụng tin vào việc xác thực từ IdP, nhưng không phải giấy phép thực hiện mọi tác vụ.** Step-up kiểm tra điều kiện bảo đảm trước hành động; backend vẫn phải đánh giá authorization hiện hành.

### 2.1. Ba chiều thiết yếu

1. **Assurance:** phương thức và quy trình xác thực đã dùng có đáp ứng yêu cầu của hành động không?
2. **Freshness:** lần xác thực đạt mức yêu cầu có đủ gần thời điểm quyết định không?
3. **Context/transaction binding:** chứng cứ có dành cho đúng chủ thể, phiên, ứng dụng, hành động, tài nguyên và tham số giao dịch không?

Một chứng cứ rất mạnh nhưng cũ nhiều giờ có thể không đạt freshness. Một lần MFA mới nhưng không liên kết tới hành động có thể bị lợi dụng để xác nhận một thao tác khác.

## 3. Khi nào nên yêu cầu step-up?

Tổ chức nên có **bảng chính sách rủi ro theo hành động**, thay vì yêu cầu step-up theo cảm tính hoặc chỉ ở giao diện.

| Hoạt động | Rủi ro chính | Yêu cầu minh họa |
| --- | --- | --- |
| Đọc thông báo nội bộ | Thấp | Phiên hợp lệ, quyền cơ bản |
| Xem bảng lương phòng ban | Cao | Quyền PayrollReader, xác thực đủ mức và còn mới |
| Xuất dữ liệu khách hàng số lượng lớn | Cao | Quyền export, step-up, giới hạn phạm vi và audit |
| Cấp role admin production | Rất cao | Phishing-resistant step-up, phê duyệt, SoD, quyền có thời hạn |
| Xóa workload production | Rất cao | Step-up người vận hành, change approval, kiểm tra dependency |
| Đổi passkey hoặc địa chỉ recovery | Cao | Reauthentication/step-up theo chính sách recovery |
| Đổi người thụ hưởng khoản thanh toán | Rất cao | Step-up và ràng buộc rõ số tiền/đối tượng giao dịch |
| Thao tác hỗ trợ thông thường | Thấp/trung bình | Yêu cầu tùy dữ liệu, vai trò và trạng thái phiên |

Đây là **ma trận ví dụ**, không quy định một thời hạn hay phương thức chung. Yêu cầu thực tế phải theo mức tác động, dữ liệu, nền tảng, quy định áp dụng và năng lực IdP.

### 3.1. Trigger dựa trên rủi ro

Một số tín hiệu hữu ích gồm phiên đã cũ, quyền đặc biệt mới được duyệt, thay đổi thiết bị, vị trí bất thường, tín hiệu chiếm tài khoản hoặc lượng dữ liệu xuất vượt ngưỡng.

Tuy nhiên IP, vị trí, device fingerprint và risk score có thể thiếu chính xác. Chúng nên được xem là **tín hiệu hỗ trợ chính sách**, không tự động chứng minh người dùng đáng tin hoặc đáng ngờ. Nếu tín hiệu thiếu, ứng dụng cần hành vi an toàn được định nghĩa trước và hỗ trợ người dùng hợp lệ.

## 4. Kiến trúc step-up và các ranh giới tin cậy

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant App as Ứng dụng / Backend
    participant PDP as Policy Engine
    participant IdP as IdP / Authentication Service
    participant Res as Tài nguyên nhạy cảm

    U->>App: Yêu cầu hành động nhạy cảm
    App->>PDP: Kiểm tra quyền và yêu cầu assurance
    PDP-->>App: Có quyền nhưng cần step-up
    App-->>U: Phát challenge và mở luồng IdP
    U->>IdP: Hoàn thành xác thực phù hợp
    IdP-->>App: Trả kết quả có thể kiểm chứng
    App->>App: Kiểm phiên, assurance, auth_time, challenge
    App->>PDP: Đánh giá lại RBAC/ABAC và JML status
    PDP-->>App: PERMIT hoặc DENY
    App->>Res: Thực thi đúng hành động được bảo vệ
    Res-->>App: Kết quả
    App-->>U: Thành công hoặc từ chối
~~~

Thành phần chính:

- **IdP:** xác thực người dùng, có thể hỗ trợ yêu cầu assurance/freshness và phát hành bằng chứng qua OIDC/SAML.
- **Ứng dụng/backend:** xác định hành động nhạy cảm, phát challenge, kiểm chứng kết quả và thực thi bảo vệ tại server.
- **Policy Decision Point (PDP):** tính quyền và điều kiện dựa trên RBAC/ABAC, danh tính, tài nguyên, trạng thái và rủi ro.
- **Policy Enforcement Point (PEP):** chặn hành động khi thiếu bằng chứng, ở backend hoặc thành phần đáng tin trước tài nguyên.
- **Identity registry/IGA:** duy trì danh tính, role, phê duyệt, quan hệ JML và lịch sử thay đổi.
- **SCIM/API:** provision/deprovision account hoặc nhóm; không tự kiểm soát mọi phiên.
- **Audit/SIEM:** truy vết ai yêu cầu, kết quả step-up, quyết định quyền và thực thi thực tế.

**Kiểm soát chỉ nằm ở frontend là không đủ.** Nếu nút trên trang web yêu cầu step-up nhưng endpoint API không kiểm tra, kẻ tấn công có thể gọi API trực tiếp để bỏ qua.

## 5. Mức bảo đảm và phương thức xác thực

**Authentication assurance** phản ánh mức độ tin cậy rằng người đang tương tác kiểm soát authenticator đã đăng ký. Các tổ chức có thể tham chiếu mức AAL từ các khung danh tính số, nhưng mức đạt được phụ thuộc **toàn bộ phương thức và quy trình triển khai**, không chỉ tên sản phẩm.

| Phương thức | Giá trị | Giới hạn cần hiểu |
| --- | --- | --- |
| **Passkey/WebAuthn** | Khóa công khai có ràng buộc với relying party và origin | Phải xác minh chữ ký, challenge, UV, origin; loại passkey và chính sách thiết bị có thể khác |
| **Khóa bảo mật FIDO2** | Có thể hỗ trợ phishing resistance và xác minh người dùng | Mức assurance còn phụ thuộc credential và cấu hình thực tế |
| **Push MFA** | Có yếu tố trên thiết bị được đăng ký | MFA fatigue/social engineering; number matching không tự làm nó phishing-resistant |
| **TOTP** | Mã thay đổi theo thời gian | Có thể bị phishing chuyển tiếp thời gian thực |
| **SMS/voice OTP** | Dễ tiếp cận trong một số bối cảnh | SIM swap, phishing và rủi ro mạng viễn thông |
| **Nhập lại mật khẩu** | Có thể chứng minh lại bí mật đã biết | Không tự đạt MFA hay mức bảo đảm cao hơn |
| **Chứng chỉ/smart card** | Phù hợp một số môi trường doanh nghiệp | Cần quản trị khóa, chủ thể, cấp phát và thu hồi |

Không nên kết luận **mọi MFA đều chống phishing** hoặc **mọi passkey đều đáp ứng mức assurance cao nhất**. Yêu cầu cho quyền nhạy cảm nên mô tả các thuộc tính kiểm chứng được.

### 5.1. Freshness

Thời hạn xác thực gần nhất phải được policy quyết định. Ví dụ tổ chức có thể yêu cầu xác thực đủ mức trong vài phút gần nhất trước khi cấp role đặc quyền, nhưng có thể chấp nhận thời gian dài hơn cho thao tác thông thường.

Không nên dùng một cờ toàn cục cho biết “đã MFA trước đây” mà thiếu **timestamp và phạm vi**. Freshness phải dựa trên thông tin từ hệ thống đáng tin, không nhận thời gian do trình duyệt tự khai.

## 6. Luồng xử lý step-up từ đầu đến cuối

### Bước 1 – Kiểm tra quyền nền tảng

Backend tải danh tính và trạng thái hiện hành, xác định quyền cơ bản. Nếu người dùng không có quyền yêu cầu thao tác, cần từ chối thay vì cung cấp một luồng step-up có khả năng cấp quyền vượt chính sách.

### Bước 2 – Tính yêu cầu bảo đảm

Policy đánh giá role, tài nguyên, action, mức nhạy cảm, tình trạng phiên và rủi ro. Kết quả có thể là **PERMIT**, **DENY** hoặc **STEP_UP_REQUIRED**.

### Bước 3 – Tạo challenge an toàn

Nếu cần step-up, backend tạo challenge có entropy đủ, thời hạn ngắn và ràng buộc với identity, session, action/resource và tham số quan trọng. Với giao dịch giá trị cao, nên thiết kế **transaction-level challenge** thay vì nâng cả phiên thành “admin mãi mãi”.

### Bước 4 – Người dùng xác thực

IdP thực hiện phương thức đáp ứng chính sách; ứng dụng dùng giao thức tích hợp phù hợp. Một số IdP yêu cầu cấu hình step-up riêng, không mặc định hỗ trợ tất cả các mức assurance.

### Bước 5 – Backend kiểm chứng

Xác minh bằng chứng giao thức, mức bảo đảm đạt được, thời điểm xác thực, identity, session và challenge. Nếu IdP không trả đủ thông tin hoặc assurance không đạt, không được đánh dấu thành công.

### Bước 6 – Kiểm tra lại authorization

Giữa lúc tạo challenge và kết quả quay về, HRIS/IGA có thể cập nhật Mover hoặc Leaver; quyền, phiên hoặc policy có thể thay đổi. Backend phải kiểm tra **điều kiện hiện hành ngay trước thực thi**.

### Bước 7 – Thực hiện và ghi audit

Thao tác được thực thi theo đúng tham số, chống replay và idempotency. Ghi riêng **step-up result**, **authorization result** và **business execution result**.

### 6.1. Mô hình trạng thái minh họa

~~~mermaid
stateDiagram-v2
    [*] --> REQUESTED
    REQUESTED --> DENIED: Không có quyền yêu cầu
    REQUESTED --> EVALUATING: Có quyền cơ bản
    EVALUATING --> AUTHORIZED: Đủ assurance và freshness
    EVALUATING --> CHALLENGE: Thiếu điều kiện xác thực
    CHALLENGE --> EXPIRED: Quá hạn
    CHALLENGE --> FAILED: Không xác thực thành công
    CHALLENGE --> VERIFIED: IdP trả bằng chứng hợp lệ
    VERIFIED --> RECHECKING: Kiểm quyền, trạng thái và giao dịch
    RECHECKING --> DENIED: Điều kiện đã đổi
    RECHECKING --> AUTHORIZED: Vẫn đủ điều kiện
    AUTHORIZED --> EXECUTED: Thực thi chống lặp
    EXECUTED --> [*]
    EXPIRED --> [*]
    FAILED --> [*]
    DENIED --> [*]
~~~

## 7. Step-up trong OIDC

**OpenID Connect (OIDC)** cho phép relying party nhận kết quả xác thực từ OpenID Provider (IdP). Một số tín hiệu có thể dùng để yêu cầu hoặc xác minh mức bảo đảm và độ mới.

| Tín hiệu OIDC | Vai trò | Điều cần tránh |
| --- | --- | --- |
| **acr** | Authentication Context Class Reference do IdP khẳng định | Không suy ra mức từ tên chuỗi tùy ý; cần contract/mapping của IdP |
| **amr** | Authentication Methods References mô tả phương thức | Một nhãn MFA không tự chứng minh phishing resistance |
| **auth_time** | Thời điểm người dùng đã xác thực | Phải có, đáng tin và đủ mới theo policy |
| **acr_values** | Giá trị ACR ứng dụng yêu cầu | Tham số yêu cầu không phải bằng chứng kết quả thực tế |
| **max_age** | Giới hạn tuổi xác thực chấp nhận được | Không tự đảm bảo dùng phương thức mạnh hơn |
| **prompt=login** | Yêu cầu IdP xác thực lại | Reauthentication chưa chắc là step-up đủ assurance |
| **state, nonce, PKCE** | Bảo vệ liên kết yêu cầu–đáp ứng theo luồng | Không bỏ qua kiểm tra dù step-up thành công |

### 7.1. Ví dụ yêu cầu step-up

~~~text
GET /authorize?
  response_type=code
  &client_id=work-app
  &redirect_uri=https%3A%2F%2Fapp.example%2Foidc%2Fcallback
  &scope=openid
  &state=SERVER_GENERATED_RANDOM_STATE
  &nonce=SERVER_GENERATED_RANDOM_NONCE
  &code_challenge=SERVER_GENERATED_PKCE_CHALLENGE
  &code_challenge_method=S256
  &max_age=0
  &acr_values=urn%3Aexample%3Aassurance%3Aphishing-resistant
~~~

Đây là **URL minh họa**, không thể gửi trực tiếp. Giá trị ACR ví dụ không phải giá trị chuẩn áp dụng mọi IdP. OIDC **max_age=0** có thể được dùng để yêu cầu xác thực mới, nhưng nó không tự đảm bảo MFA/phishing resistance; ứng dụng vẫn phải kiểm tra kết quả trả về.

### 7.2. Xác minh kết quả từ IdP

Backend cần thực hiện các bước xác minh OIDC tương ứng với luồng được dùng: kiểm tra **issuer, audience, chữ ký hoặc cách kiểm chứng hợp lệ, hạn token, nonce/state và việc đổi authorization code**. Sau đó:

1. Liên kết đúng subject bằng **issuer + subject identifier**, không dùng email đơn độc làm khóa.
2. Xác minh **auth_time** và độ mới theo ngưỡng policy.
3. Xác minh **acr/amr** khi liên quan, dựa vào ý nghĩa đã thống nhất với IdP.
4. Nếu thông tin thiếu, không đạt hoặc không đáng tin, không cho qua step-up.
5. Gắn kết quả với challenge và phiên do backend quản lý.
6. Đánh giá lại quyền, trạng thái danh tính và nội dung giao dịch trước khi thực thi.

**ID token dùng cho xác thực ở relying party, không phải mặc nhiên là access token để gọi API.** Nếu API cần bằng chứng step-up, phải dùng ngữ cảnh phiên đáng tin ở server hoặc token/cơ chế có audience và claim phù hợp, thay vì tin cờ từ frontend.

### 7.3. Ví dụ kết quả minh họa

~~~json
{
  "iss": "https://idp.example",
  "sub": "idp-user-1042",
  "aud": "work-app",
  "auth_time": 1795405500,
  "acr": "urn:example:assurance:phishing-resistant",
  "amr": ["hwk", "user"]
}
~~~

Dữ liệu này chỉ minh họa cấu trúc claim; **không khẳng định một sản phẩm IdP cụ thể đáp ứng mức AAL**. Kết quả phải được kiểm tra với chính sách, định nghĩa ACR/AMR của nguồn phát và giao thức xác minh đầy đủ.

## 8. Step-up trong SAML

Với **SAML 2.0**, Service Provider có thể dùng **RequestedAuthnContext** để yêu cầu ngữ cảnh xác thực và **ForceAuthn** để yêu cầu IdP xác thực mới theo khả năng hỗ trợ.

Một ví dụ XML rút gọn nhằm minh họa ý tưởng:

~~~xml
<samlp:AuthnRequest
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    ID="_request-42"
    Version="2.0"
    IssueInstant="2026-11-23T09:00:00Z"
    ForceAuthn="true">
  <samlp:RequestedAuthnContext Comparison="exact">
    <saml:AuthnContextClassRef
      xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">
      urn:example:authn:strong
    </saml:AuthnContextClassRef>
  </samlp:RequestedAuthnContext>
</samlp:AuthnRequest>
~~~

XML trên **không phải AuthnRequest đầy đủ**. Khi tích hợp, ứng dụng phải xác minh chữ ký, issuer, audience, recipient, InResponseTo, Conditions, SubjectConfirmation và thời hạn theo profile áp dụng.

**ForceAuthn chỉ liên quan tới yêu cầu xác thực lại, không tự chứng minh phương thức mạnh hơn.** SP phải đọc AuthnContext trả về, kiểm tra mapping policy và ràng buộc với yêu cầu thực tế. Nếu IdP không hỗ trợ yêu cầu step-up phù hợp, không bỏ qua kiểm soát bảo mật chỉ vì luồng federation vẫn đăng nhập thành công.

## 9. WebAuthn/passkey trong step-up

**WebAuthn** sử dụng xác thực khóa công khai ràng buộc với **origin và relying party**, có khả năng chống nhiều dạng phishing khi triển khai đúng. Authenticator tạo assertion ký trên challenge từ RP, thay vì gửi secret có thể tái sử dụng.

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant B as Trình duyệt
    participant RP as RP Backend
    participant A as Authenticator

    U->>RP: Thực hiện hành động nhạy cảm
    RP->>RP: Sinh challenge riêng có TTL
    RP-->>B: WebAuthn request options
    B->>A: Yêu cầu xác thực cho đúng RP
    A->>U: User presence / user verification
    U-->>A: Xác nhận
    A-->>B: Assertion đã ký
    B->>RP: Trả assertion
    RP->>RP: Kiểm signature, challenge, origin, RP ID, flags
    RP->>RP: Kiểm lại action, entitlement và phiên
    RP-->>U: Thực thi hoặc từ chối
~~~

### 9.1. Kiểm tra bắt buộc ở backend

- Challenge đúng với challenge đã phát và chưa hết hạn/sử dụng lại.
- Origin và RP ID đúng; kiểm tra rpIdHash.
- Chữ ký hợp lệ với public key của credential đã đăng ký.
- Credential thuộc đúng identity/account và chưa bị thu hồi.
- Các flags **User Presence (UP)** và **User Verification (UV)** đáp ứng policy.
- Điều kiện về loại authenticator, backup/sync, thiết bị hoặc attestation theo mức rủi ro nếu có yêu cầu hợp lệ.
- Kết quả thuộc đúng phiên và tác vụ được bảo vệ.

**UV không tự chứng minh mọi yêu cầu assurance cao nhất đã đáp ứng.** Cần xét thêm vòng đời credential, phương pháp binding và chính sách hệ thống.

### 9.2. Phishing resistance không tự là phê duyệt giao dịch

WebAuthn ràng buộc xác thực với RP/origin. Nhưng một assertion xác thực thông thường **không tự chứng minh người dùng đã đọc và chấp thuận đúng số tiền, người thụ hưởng hoặc role cần cấp**.

Nếu cần transaction authorization, ứng dụng phải bảo vệ nội dung giao dịch, cho người dùng thấy thông tin quan trọng qua cơ chế đáng tin và ràng buộc kết quả step-up ở server với **hành động thực sự được thực thi**.

## 10. Kết hợp RBAC/ABAC và step-up

**RBAC** quy định role nào mang quyền gì; **ABAC** áp điều kiện theo chủ thể, tài nguyên, hành động và ngữ cảnh. Step-up là một điều kiện bổ sung, không biến quyền không hợp lệ thành hợp lệ.

Ví dụ mã giả:

~~~text
PERMIT sensitive_report.export IF
    subject.lifecycleStatus == ACTIVE
    AND subject.hasApprovedEntitlement("REPORT_EXPORT")
    AND subject.department == resource.ownerDepartment
    AND resource.classification <= subject.clearance
    AND session.assuranceSatisfies(policy.requiredAssurance)
    AND session.strongAuthAgeSeconds <= policy.maxStrongAuthAgeSeconds
    AND transaction.isBoundToValidStepUp
ELSE DENY
~~~

Mã giả không phải cú pháp của policy engine cụ thể. Mức assurance phải được **ánh xạ theo thứ bậc và tiêu chí rõ ràng**, không so sánh các chuỗi ACR tùy ý.

### 10.1. Sau step-up vẫn cần kiểm tra lại quyền

Người dùng có thể bắt đầu step-up lúc còn role FinanceReader, nhưng trong khi chờ, HRIS gửi Mover hoặc Leaver khiến role bị thu hồi. Backend phải kiểm tra **trạng thái và quyền hiện hành** ngay trước khi thực thi.

Không dùng token có role cũ làm bằng chứng quyền đã tồn tại vĩnh viễn. Có thể cần phiên mới, token mới hoặc kiểm tra chính sách trực tiếp theo kiến trúc và mức rủi ro.

## 11. Session-level và transaction-level step-up

**Session-level:** phiên được đánh dấu đã đáp ứng mức xác thực trong một khoảng ngắn, với phạm vi ứng dụng/chức năng đã định. Hữu ích khi người dùng thực hiện nhiều thao tác liên quan; cần TTL, giới hạn phạm vi và cơ chế hạ mức.

**Transaction-level:** một challenge chỉ hợp lệ cho một yêu cầu cụ thể, ví dụ cấp role Admin cho đúng tài khoản/đúng dự án. Phù hợp khi nguy cơ đánh tráo tham số cao.

### 11.1. Ví dụ challenge do server giữ

~~~json
{
  "challengeId": "stepup-req-5821",
  "identityId": "person-1042",
  "sessionRef": "session-94",
  "action": "GRANT_ROLE",
  "targetIdentityId": "person-2918",
  "resourceId": "prod-project-7",
  "role": "ProductionReader",
  "requestDigest": "sha256:illustrative-only",
  "requiredPolicy": "grant-role-v3",
  "createdAt": "2026-11-23T09:00:00+07:00",
  "expiresAt": "2026-11-23T09:05:00+07:00",
  "singleUse": true,
  "status": "PENDING"
}
~~~

Đây là **JSON minh họa**, không phải schema chuẩn. Digest phải được tính từ nội dung canonical do backend tin cậy, không chấp nhận một chuỗi tùy ý từ frontend làm bằng chứng toàn vẹn.

### 11.2. Chống replay và đánh tráo tham số

1. Sinh challenge ngẫu nhiên ở server.
2. Gắn với subject, session, action, target identity, role, resource và tham số quan trọng.
3. Đặt thời hạn ngắn và trạng thái dùng một lần.
4. Kiểm tra kết quả IdP/authenticator thuộc đúng challenge.
5. Khi client đổi tham số sau step-up, yêu cầu quyết định/challenge mới.
6. **Consume atomically** để không cho hai request đồng thời dùng cùng một challenge.
7. Kiểm tra authorization hiện hành ngay trước commit.
8. Ghi audit và không tái sử dụng chứng cứ cho hành động khác.

Đặc biệt khi cấp quyền, xác thực cho thao tác cấp role Reader **không được** áp cho lệnh cấp Admin chỉ vì cùng một người yêu cầu.

## 12. Mã giả cho backend Java

Ví dụ dưới đây chỉ trình bày các bước logic, **không phải code chạy trực tiếp** và không thay thế API thật của Java/Spring Security hay IdP.

~~~java
// PSEUDOCODE - không dùng nguyên xi làm triển khai sản xuất.
Decision authorizeSensitiveAction(
        Actor actor,
        SessionContext session,
        SensitiveAction action) {

    Identity current = identityService.loadCurrent(actor.identityId());

    if (!current.isActive()
            || !policy.mayRequest(actor, action, current)) {
        return Decision.deny("NOT_AUTHORIZED");
    }

    AssuranceRequirement required =
            policy.requiredAssurance(actor, action, current);

    boolean assuranceOk =
            assuranceService.satisfiesTrustedSession(session, required);
    boolean transactionProofOk = !required.mustBindTransaction() ||
            challengeStore.hasVerifiedProofFor(actor, session, action);

    if (!assuranceOk || !transactionProofOk) {
        Challenge challenge = challengeStore.create(
            actor.identityId(),
            session.reference(),
            action.type(),
            action.resourceId(),
            canonicalDigest(action.parameters()),
            required,
            shortExpiry(),
            true
        );
        return Decision.stepUpRequired(challenge.id());
    }

    if (required.mustBindTransaction() &&
            !challengeStore.matchesCurrentRequest(
                    actor.identityId(), session.reference(), action)) {
        return Decision.deny("STEP_UP_CONTEXT_MISMATCH");
    }

    // Mover/Leaver/policy có thể thay đổi khi xác thực đang diễn ra.
    Identity latest = identityService.loadCurrent(actor.identityId());
    if (!latest.isActive() ||
            !policy.mayExecute(actor, action, latest)) {
        return Decision.deny("ACCESS_CHANGED");
    }

    if (required.mustBindTransaction() &&
            !challengeStore.consumeAtomically(actor, session, action)) {
        return Decision.deny("EXPIRED_OR_REPLAYED_CHALLENGE");
    }

    return actionService.executeIdempotently(actor, action);
}
~~~

Ví dụ đơn giản hóa transaction boundary, session store và concurrency. Trong triển khai thật, cần bảo đảm việc tiêu thụ challenge và thực hiện giao dịch không tạo lỗ hổng race condition. Nếu action thất bại sau khi challenge đã được dùng, việc retry phải có **chính sách và idempotency** riêng.

Một ví dụ **không an toàn**:

~~~text
if (request.header("X-MFA-Completed") == "true") {
    grantAdminRole();
}
~~~

Header tự khai của client không phải bằng chứng xác thực. Backend phải kiểm tra tín hiệu từ nguồn đáng tin và policy đã cấu hình.

## 13. Step-up trong Joiner–Mover–Leaver

### 13.1. Joiner: xác lập đúng danh tính và authenticator

Joiner bắt đầu từ nguồn HRIS/hợp đồng và identity proofing. IdP đăng ký phương thức xác thực vào đúng danh tính; SCIM/API có thể tạo tài khoản ứng dụng, RBAC/ABAC cấp quyền theo nhiệm vụ. Step-up có thể cần khi nhân viên mới thực hiện **tác vụ nhạy cảm đầu tiên** hoặc quản lý yếu tố xác thực.

Xác minh danh tính ban đầu và liên kết authenticator phải đúng chủ thể. **Hoàn thành MFA không sửa được account link sai**, và không được dùng step-up để bỏ qua role approval.

### 13.2. Mover: quyền mới có thể đòi assurance cao hơn

Nhân viên chuyển từ Development sang Production Operations:

- IAM tính lại role, gỡ quyền cũ và đánh giá xung đột SoD.
- Chủ sở hữu tài nguyên phê duyệt quyền quản trị có thời hạn.
- Ứng dụng có thể yêu cầu step-up chống phishing khi kích hoạt quyền.
- Bộ điều phối xử lý claim/phiên/token chứa quyền cũ theo khả năng hệ thống.
- Reconciliation xác minh các quyền đã cấp và thu hồi đúng.

**Step-up không thay thế việc gỡ quyền cũ sau Mover.**

### 13.3. Leaver: phải thu hồi, không phải yêu cầu xác thực thêm

Khi người dùng đã nghỉ việc:

- HRIS/nguồn hợp đồng phát sự kiện Leaver có effectiveAt.
- IdP và ứng dụng vô hiệu hóa account, gỡ quyền, thu hồi session/token theo phạm vi hỗ trợ.
- Backend kiểm tra trạng thái danh tính ngay cả khi đang có kết quả step-up hợp lệ.
- Một phiên cũ hoặc một authenticator vẫn dùng được không biến người đó thành người còn quyền.

**Sai lầm:** Leaver còn phiên SaaS; ứng dụng yêu cầu MFA rồi cho thao tác dữ liệu vì MFA thành công. Việc người đó không còn quyền phải được ưu tiên trước mức assurance.

### 13.4. Reconciliation vẫn cần thiết

IdP cập nhật group không mặc nhiên gỡ mọi quyền ở SaaS, nhất là token, local account hoặc role ngoài SCIM. Reconciliation đọc lại desired/observed entitlements sau JML. Step-up chỉ là hàng rào bổ sung khi **quyền vốn đã hợp lệ**.

## 14. Service account và API không tương tác

Không phải mọi principal là con người. **Workload identity, service account, bot, CI/CD pipeline** không thể tự xác nhận push MFA hoặc nhập OTP của nhân viên một cách hợp lệ.

Các kiểm soát phù hợp hơn cho non-human identity:

- Managed identity hoặc workload federation, credential ngắn hạn theo môi trường đáng tin.
- mTLS, token ràng buộc người gửi hoặc proof-of-possession khi hệ thống hỗ trợ.
- Scope và audience hẹp, tenant và resource cụ thể.
- Just-In-Time privilege và approval có kiểm soát nếu workload cần quyền nhạy cảm.
- Quản lý secret, rotation, revoke và theo dõi sử dụng.
- Chủ sở hữu, ngày/điều kiện kết thúc và quy trình chuyển owner khi người vận hành Mover/Leaver.

Nếu một người phê duyệt việc deploy production, chính **người phê duyệt** có thể bị yêu cầu step-up; workload sau đó dùng credential riêng có scope/hạn ngắn. Không nhúng OTP cá nhân vào pipeline hay để service principal giả làm session admin của người vận hành.

## 15. Những rủi ro thường gặp

| Rủi ro | Cơ chế | Biện pháp |
| --- | --- | --- |
| **Frontend-only step-up** | API phụ không kiểm tra MFA | PEP tại backend/domain service và test bypass |
| **Chỉ tin cờ MFA từ client** | Header hoặc local state bị giả mạo | Kiểm chứng IdP/assertion/server session |
| **Coi mọi OTP là phishing-resistant** | Mã bị chuyển tiếp theo thời gian thực | Chọn authenticator đúng mức rủi ro |
| **MFA fatigue** | Người dùng duyệt push ngoài ý muốn | Phương thức mạnh hơn, rate limit, phát hiện bất thường |
| **Dùng lại kết quả vô hạn** | Một lần step-up cho mọi hành động | TTL, scope hẹp, single-use khi phù hợp |
| **Đánh tráo tham số** | Challenge cho Reader bị dùng cấp Admin | Transaction binding và recheck |
| **Không xét auth_time** | Assurance mạnh nhưng quá cũ | Freshness policy rõ |
| **Sai issuer/audience/subject** | Dùng chứng cứ của ứng dụng/người khác | Kiểm giao thức và liên kết identity |
| **Role đã bị thu hồi** | Mover/Leaver trong lúc challenge | Revalidate authorization trước commit |
| **Recovery yếu** | Kẻ tấn công thay MFA rồi step-up | Recovery proofing, thông báo, delay theo policy |
| **Token/phiên bị đánh cắp** | Lạm dụng session sau đăng nhập | Session hardening, step-up cho thao tác nhạy cảm |
| **IdP outage dẫn tới bypass** | Bỏ qua xác thực vì cần phục vụ công việc | Fail-safe, ngoại lệ break-glass có owner |

### 15.1. Không để đường API phụ bypass

Nếu giao diện yêu cầu step-up trước thao tác export, nhưng API tạo job nền hoặc URL download không kiểm tra tương tự, kẻ tấn công có thể bỏ qua luồng bảo vệ.

Nên gắn chính sách tại **lớp service thực thi nghiệp vụ** và kiểm thử tất cả đường dẫn có tác động tương đương, kể cả API batch, queue, webhook và thao tác bất đồng bộ.

## 16. Khôi phục authenticator và xử lý ngoại lệ

**Recovery** thường là điểm yếu nếu tổ chức cho đổi phương thức MFA bằng một yêu cầu hỗ trợ dễ giả mạo.

Quy trình hợp lý:

1. Xác định chủ thể bằng phương pháp phù hợp rủi ro, có thể gồm proofing lại.
2. Kiểm tra account chưa bị chặn bởi sự cố hoặc Leaver.
3. Thu hồi authenticator bị mất hoặc không còn đáng tin.
4. Đăng ký phương thức mới vào đúng identity/account qua quy trình được kiểm soát.
5. Thông báo thay đổi qua kênh độc lập khi cần.
6. Hạn chế tạm thời thao tác đặc quyền hoặc áp dụng waiting period theo chính sách nếu rủi ro cao.
7. Lưu đầy đủ phê duyệt và audit.

Nếu người dùng cần hỗ trợ tiếp cận, nên cung cấp phương thức thay thế **đáp ứng cùng yêu cầu bảo đảm**, thay vì mở một đường tắt dễ bị mạo danh.

### 16.1. Khi IdP không sẵn sàng

Với hành động nhạy cảm, không bật cờ **skip-step-up** toàn hệ thống. Lựa chọn có thể là tạm hoãn tác vụ, dùng phương thức dự phòng đã được chấp thuận, hoặc quy trình break-glass khẩn cấp có thẩm quyền, phạm vi/hạn sử dụng và review sau sự cố.

## 17. Audit, quyền riêng tư và bằng chứng

Một bản ghi step-up cần đủ thông tin để xác định **ai yêu cầu tác vụ gì, vì sao bị thách thức, bằng chứng có đáp ứng không, quyền hiện hành ra sao và hành động có thực sự chạy không**.

| Trường minh họa | Ý nghĩa |
| --- | --- |
| eventId / correlationId | Nối yêu cầu, challenge, xác thực và thực thi |
| identityId / actorId | Chủ thể yêu cầu |
| sessionRef / clientId | Ngữ cảnh phiên và ứng dụng, không lưu cookie thực |
| action / resourceId | Tác vụ và tài nguyên được bảo vệ |
| policyId / policyVersion | Yêu cầu bảo đảm được áp dụng |
| requiredAssurance / observedAssurance | Mức cần có và mức đã xác minh |
| authTime / verifiedAt | Thời gian xác thực và thời gian kiểm chứng |
| methodCategory | Loại authenticator phù hợp, không chứa bí mật |
| challengeRef / transactionRef | Bằng chứng ràng buộc hành động |
| stepUpResult | SUCCEEDED, FAILED, CANCELLED, EXPIRED |
| authorizationResult | PERMIT hoặc DENY sau kiểm tra quyền |
| businessExecutionResult | EXECUTED, NOT_EXECUTED, FAILED |

**Không ghi OTP, access token, refresh token, private key, full session cookie hoặc thông tin khôi phục bí mật** vào log.

Ba kết quả cần giữ riêng:

~~~text
Step-up authentication: SUCCEEDED
Authorization re-check: DENIED (role vừa bị thu hồi)
Business action: NOT_EXECUTED
~~~

Đây là **kết quả an toàn**, không phải lỗi step-up.

~~~text
Step-up authentication: SUCCEEDED
Authorization re-check: PERMITTED
Business action: FAILED (service timeout)
~~~

Trường hợp này cần chiến lược idempotency/retry của giao dịch; không mặc định tái dùng một challenge đã tiêu thụ hoặc chạy lại hành động hai lần.

## 18. Chỉ số vận hành và kiểm thử

| Chỉ số | Mục đích |
| --- | --- |
| Challenge rate theo hành động | Xem các tác vụ nào tạo nhiều step-up |
| Completion / failure / abandonment rate | Đánh giá trải nghiệm và lỗi xác thực |
| Time to step-up | Độ trễ từ challenge đến kiểm chứng |
| Assurance downgrade attempts | Theo dõi yêu cầu fallback không đạt policy |
| Replay/context mismatch count | Phát hiện challenge bị sử dụng sai |
| Stale authentication denials | Theo dõi yêu cầu vượt giới hạn freshness |
| Denied-after-step-up | Phát hiện quyền thay đổi hoặc sai policy |
| Recovery-sensitive actions | Rà soát hành động nhạy cảm gần thời điểm recovery |
| IdP outage impact | Chuẩn bị vận hành an toàn khi IdP không khả dụng |
| Privileged action without verified step-up | Kiểm tra việc bỏ qua PEP, nếu có |

Các kiểm thử cần bao gồm:

- Gọi trực tiếp API khi frontend đã bị bỏ qua.
- Sử dụng challenge đã hết hạn, đã dùng hoặc của session khác.
- Đổi role/resource/target identity sau khi step-up.
- Concurrent requests cùng dùng một challenge.
- IdP trả ACR không đạt, thiếu auth_time hoặc sai issuer/audience.
- Người dùng bị Mover/Leaver trong lúc xác thực.
- Thu hồi credential, recovery vừa hoàn tất và fallback yếu.
- IdP không sẵn sàng; application phải hành xử theo chính sách.
- Đường API batch, job nền và webhook có thể thực hiện cùng nghiệp vụ.

Không tối ưu completion rate bằng cách hạ yêu cầu cho toàn bộ hành động. Kết quả đo nên phân theo **mức rủi ro, tài nguyên, phương thức, loại người dùng và nguyên nhân thất bại**.

## 19. Tình huống tổng hợp

### 19.1. Cấp quyền production sau Mover

Nhân viên **Lan** chuyển từ Development sang Production Operations. HRIS cập nhật vai trò, IGA thu hồi quyền cũ và phê duyệt một quyền quản trị production có thời hạn.

Lan đăng nhập SSO buổi sáng. Chiều cùng ngày, Lan muốn kích hoạt ProductionAdmin. Backend kiểm tra role được duyệt nhưng phiên hiện tại không đủ **assurance và freshness**. IdP thực hiện step-up bằng phương thức theo chính sách; backend kiểm chứng kết quả, đánh giá lại SoD, trạng thái account và mục tiêu role, rồi cấp quyền đúng phạm vi/hạn sử dụng.

Nếu Lan đã Leaver trong lúc challenge mở, backend phải từ chối dù xác thực mạnh thành công. Sau khi quyền hết hạn, IAM thu hồi và reconciliation xác minh không còn entitlement.

### 19.2. Xuất dữ liệu và thay đổi tham số

Nhân viên có quyền xuất 100 bản ghi của phòng ban A. Backend phát challenge ràng buộc phạm vi **department=A, maxRows=100**. Trong khi xác thực, client thay yêu cầu thành xuất toàn bộ dữ liệu công ty.

Nếu backend chỉ lưu cờ MFA thành công, việc đánh tráo có thể được phép. Thiết kế đúng so lại tham số với nội dung đã bảo vệ; challenge cũ không còn phù hợp, nên phải từ chối hoặc yêu cầu quyết định mới.

### 19.3. Khôi phục MFA sau khi mất điện thoại

Nhân viên mất thiết bị push MFA. Một phiên web cũ không đủ để tự đăng ký MFA mới. Bộ phận hỗ trợ cần kiểm tra danh tính theo quy trình recovery, thu hồi yếu tố cũ, đăng ký yếu tố mới đúng account và ghi audit. Các hành động nhạy cảm ngay sau recovery phải tuân thủ chính sách bảo vệ bổ sung.

### 19.4. Leaver còn session SaaS

IdP đã khóa account của nhân viên nghỉ việc nhưng ứng dụng SaaS chưa hủy local session. Người dùng gọi endpoint xóa dữ liệu, ứng dụng yêu cầu step-up.

Hệ thống **không được** cho qua chỉ vì một yếu tố xác thực hoàn thành; trạng thái Leaver đã làm quyền không còn hợp lệ. Backend phải chặn, đồng thời hệ thống deprovision và reconciliation cần xử lý session/token, account và quyền tồn dư.

## 20. Checklist triển khai step-up

| Câu hỏi | Bằng chứng mong đợi |
| --- | --- |
| Hành động có rủi ro cao được định danh đầy đủ? | Policy theo action/resource |
| Quyền nghiệp vụ tách khỏi assurance? | RBAC/ABAC + điều kiện step-up |
| Yêu cầu về phương thức và freshness rõ ràng? | Contract IdP và policy version |
| Có kiểm chứng OIDC/SAML đầy đủ? | Issuer, audience, signature, nonce/state, conditions tùy giao thức |
| Kết quả assurance có được kiểm tra, không chỉ yêu cầu? | Mapping ACR/AMR, auth_time và giới hạn |
| Backend có thể chặn mọi đường thực thi? | PEP và negative tests |
| Challenge ràng buộc đúng identity/session/action? | Server-side context, TTL và single-use |
| Có ngăn replay/đánh tráo tham số không? | Atomic consume, digest/context và idempotency |
| Quyền và JML status được đọc lại sau step-up? | Current-state guard |
| Có xử lý session/token tồn dư? | Session control và deprovision workflow |
| Có khôi phục authenticator an toàn? | Recovery proofing, rebind, audit |
| Có hỗ trợ non-human identity riêng? | Workload credential và owner management |
| IdP outage không dẫn tới bypass? | Fail-safe hoặc break-glass được duyệt |
| Có phương thức thay thế hỗ trợ tiếp cận? | Cùng mức bảo đảm, được kiểm soát |
| Audit tách xác thực, quyền, thao tác? | Ba kết quả và correlation ID |
| Có đo lường rủi ro/UX và test concurrency? | KPI, replay test và bypass test |

## 21. Những nhầm lẫn thường gặp

1. **“Đã bật MFA nên không bao giờ cần step-up.”** Mức bảo đảm và độ mới có thể chưa đủ cho tác vụ.
2. **“Nhập lại mật khẩu luôn nâng assurance.”** Có thể chỉ là reauthentication cùng mức.
3. **“OIDC acr_values ghi mức cao nghĩa là IdP đã thực hiện.”** Phải kiểm tra kết quả thực và hợp đồng ACR.
4. **“prompt=login nghĩa là phishing-resistant MFA.”** Nó yêu cầu xác thực lại, không định nghĩa phương thức.
5. **“Push kèm number matching luôn chống phishing.”** Không tương đương xác thực ràng buộc origin của WebAuthn.
6. **“WebAuthn đã ký thì người dùng đã xác nhận số tiền.”** Assertion xác thực không tự ký mọi nội dung giao dịch nghiệp vụ.
7. **“Frontend biết step-up thành công là đủ.”** Backend phải kiểm chứng bằng chứng đáng tin.
8. **“Sau step-up khỏi cần kiểm tra quyền.”** Mover/Leaver hoặc policy có thể thay đổi trong lúc chờ.
9. **“Step-up sửa được quyền cấp nhầm.”** Cần quản trị entitlement và reconciliation.
10. **“Leaver chỉ cần MFA mạnh hơn.”** Người không còn quyền phải bị chặn, không phải xác thực thêm rồi truy cập.
11. **“Service account dùng OTP của nhân viên.”** Workload cần authentication và governance không tương tác.
12. **“IdP lỗi thì bỏ qua step-up.”** Cần fail-safe và ngoại lệ có kiểm soát.

## 22. Câu hỏi tự đánh giá

1. Step-up khác authentication ban đầu, MFA và reauthentication như thế nào?
2. Vì sao phiên SSO hợp lệ vẫn có thể không đủ khi cấp role production?
3. Ba yếu tố assurance, freshness và transaction binding giải quyết những rủi ro khác nhau nào?
4. Trong OIDC, acr, amr, auth_time, acr_values, max_age và prompt=login có vai trò gì?
5. Vì sao backend phải kiểm tra issuer, audience, nonce/state và đúng subject?
6. WebAuthn có đặc tính chống phishing như thế nào và giới hạn của nó đối với transaction authorization là gì?
7. Vì sao sau step-up vẫn phải kiểm tra lại RBAC/ABAC và JML status?
8. Điều gì xảy ra nếu challenge cho Reader bị dùng để cấp Admin?
9. Vì sao service principal không nên dùng OTP tương tác của nhân viên?
10. Quy trình recovery cần gì để không trở thành lỗ hổng yếu hơn step-up?
11. IdP/SCIM có tự thu hồi mọi session của Leaver không?
12. Audit nên phản ánh thế nào khi xác thực mạnh thành công nhưng quyền bị từ chối?
13. Những test nào phát hiện endpoint phụ bypass step-up?
14. Khi IdP gián đoạn, hành vi fail-safe và break-glass nên khác nhau ở điểm nào?

## 23. Ghi nhớ

**Step-up authentication** tăng mức yêu cầu xác thực theo **rủi ro hành động, assurance đang có, độ mới và ngữ cảnh phiên/giao dịch**. Để hiệu quả, nó cần được **kiểm chứng tại backend**, ràng buộc đúng chủ thể và hành động, giới hạn TTL, chống replay và đi cùng kiểm tra authorization hiện hành.

Trong **Joiner–Mover–Leaver**, step-up bảo vệ việc đăng ký/thay đổi authenticator và thao tác nhạy cảm sau khi quyền mới được cấp; nó **không thay thế** identity proofing, phê duyệt, thu hồi quyền khi Mover hoặc chặn truy cập của Leaver. **IdP/SSO** cung cấp xác thực, **SCIM/API** quản lý tài khoản, **RBAC/ABAC** quyết định quyền, còn **reconciliation và audit** phát hiện quyền, phiên và token tồn dư. Hành động nhạy cảm chỉ nên được thực thi khi đồng thời thỏa **danh tính hợp lệ, quyền hiện hành, mức bảo đảm phù hợp, xác thực đủ mới và ràng buộc giao dịch chính xác**.
