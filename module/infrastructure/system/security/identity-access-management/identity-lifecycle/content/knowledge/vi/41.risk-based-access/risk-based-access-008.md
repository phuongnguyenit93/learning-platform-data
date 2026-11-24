# Step-up decision trong IAM: quyết định tăng cường xác thực theo rủi ro và ngữ cảnh

**Step-up decision** là quyết định **có cần yêu cầu người dùng chứng minh mức bảo đảm xác thực cao hơn hoặc xác thực lại gần thời điểm thực hiện hành động** hay không. Đây là một thành phần của **risk-based access**, nơi hệ thống xét đồng thời **định danh, trạng thái tài khoản, thiết bị, phiên, tín hiệu nguy cơ, độ nhạy của tài nguyên, hành động, thời điểm và chính sách nghiệp vụ** trước khi cho phép truy cập. Step-up thường dẫn người dùng tới **MFA mạnh hơn, xác thực chống phishing, tái xác thực hoặc xác nhận có ràng buộc giao dịch**, tùy mức rủi ro và khả năng của IdP.

Bài **“Step-up decision”** thuộc chương **Risk-based access** của module **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**. Module nghiên cứu quản lý vòng đời danh tính theo **Joiner–Mover–Leaver (JML)**: từ xác minh, tạo tài khoản, cấp quyền, rà soát đến thu hồi khi thay đổi vai trò; phối hợp **IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, kiểm toán** để giảm **quyền truy cập tồn dư**. Step-up không thay thế quy trình này: **chỉ khi chủ thể còn quyền hợp lệ, step-up mới có thể nâng mức tin cậy của phiên cho hành động được phép**.

**Tình huống:** Một nhân viên đã đăng nhập SSO từ đầu ngày với mật khẩu và MFA thông thường. Đến chiều, nhân viên yêu cầu **xuất dữ liệu khách hàng nhạy cảm** từ một thiết bị chưa được quản lý, trong khi hệ thống thấy thay đổi vị trí truy cập bất thường. Quyết định phù hợp có thể là **STEP_UP_REQUIRED** để xác thực bằng WebAuthn/phương thức mạnh hơn, hoặc **DENY** nếu thiết bị vi phạm chính sách bắt buộc. Nếu nhân viên vừa chuyển vai trò và đã mất quyền xuất dữ liệu, **MFA thành công không được tái cấp quyền export**.

## 1. Phân biệt step-up, MFA, reauthentication và authorization

| Khái niệm | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Authentication** | Ai/đối tượng nào đang được xác thực? | IdP xác nhận user và phương thức đăng nhập. |
| **Authorization** | Chủ thể có được làm action trên resource này không? | User được đọc hóa đơn thuộc tenant VN. |
| **MFA** | Có nhiều yếu tố xác thực phù hợp không? | Password kết hợp security key hoặc authenticator theo chính sách. |
| **Step-up authentication** | Với hành động này, phiên hiện tại cần **mức bảo đảm hoặc độ mới cao hơn** không? | Yêu cầu WebAuthn trước khi đổi tài khoản nhận tiền. |
| **Reauthentication** | Cần yêu cầu người dùng xác thực lại vì phiên đã cũ hoặc sự kiện nhạy cảm? | Xác thực lại khi thay khóa bảo mật. |
| **Risk-based access** | Có nên ALLOW, STEP_UP, DENY hoặc yêu cầu điều kiện bổ sung theo rủi ro? | Truy cập bất thường từ thiết bị chưa quản lý. |
| **Continuous/session evaluation** | Điều kiện tin cậy có thay đổi trong phiên không? | Thiết bị bị đánh dấu compromised hoặc user Leaver. |
| **Just-in-time access (JIT)** | Quyền có thể được cấp có hạn sau approval phù hợp không? | Admin được kích hoạt vai trò 30 phút theo change ticket. |

**Step-up chỉ có thể tăng bảo đảm về việc đúng chủ thể đang tương tác, không tự tạo entitlement.** Nếu policy **cấm** user truy cập do Leaver, tenant mismatch, SoD hoặc resource classification, bước MFA thành công **không biến DENY thành ALLOW**.

### Các quyết định khác nhau

~~~text
ALLOW               : Identity, permissions, assurance và risk đều đáp ứng.
STEP_UP_REQUIRED    : Có quyền nghiệp vụ, nhưng assurance/freshness chưa đủ.
DENY                : Có hard deny, quyền không hợp lệ hoặc rủi ro không thể chấp nhận.
REQUIRE_APPROVAL    : Quyền cần business/SoD approval riêng, step-up không đủ.
INDETERMINATE       : Thiếu tín hiệu bắt buộc hoặc PDP/IdP không thể quyết định.
~~~

Trong API, **INDETERMINATE** nên dẫn đến cách xử lý **fail-safe** theo risk policy, không mặc định cho phép vì không lấy được risk score. Một hệ thống có thể dùng tên trạng thái khác; cần giữ **ngữ nghĩa tách biệt** trong toàn bộ luồng.

## 2. Vì sao step-up decision quan trọng với IAM lifecycle?

Quyền không bất biến theo thời gian. Người dùng có thể **Joiner**, **Mover**, **Suspended** hoặc **Leaver**; ứng dụng có thể thay đổi mức nhạy cảm; một phiên SSO có thể tồn tại lâu hơn quyết định quyền.

- **Joiner:** tài khoản có thể được provision trước ngày bắt đầu nhưng không được kích hoạt quyền trước effectiveAt. MFA không được bỏ qua điều kiện activation.
- **Mover:** nhân viên chuyển từ read-only sang Approver; quyền Approver mới cần phê duyệt, SoD và có thể đòi step-up, trong khi quyền cũ phải được thu hồi.
- **Leaver:** mọi phiên/token cũ cần bị chặn theo SLA; không hiển thị step-up như đường khôi phục quyền đã chấm dứt.
- **Suspension:** tài khoản bị security hold cần DENY hoặc quy trình khôi phục có thẩm quyền, không “step-up rồi tiếp tục” tự động.
- **Service account:** workload chạy không có người dùng tương tác; thay yêu cầu MFA bật lên bằng **workload attestation, short-lived credentials, role constraints, human approval** khi cần.
- **Access review:** kết quả REVIEW/KEEP hoặc grant expiry quyết định quyền được giữ hay không; step-up không thay việc xác nhận entitlement.
- **SoD:** người đã tạo payment không được tự duyệt chỉ bằng việc chứng minh lại danh tính.

**Mục tiêu:** không chỉ chặn người không đủ bảo đảm, mà còn **giữ cho người đủ quyền tiếp tục làm việc** bằng step-up hợp lý thay vì ép đăng nhập lại toàn bộ với mọi thao tác ít rủi ro.

## 3. Ba cổng kiểm soát cần tách trước khi quyết định

Một hệ thống nhất quán nên coi step-up như **một nhánh trong authorization pipeline**, không phải điều kiện duy nhất.

~~~mermaid
flowchart TD
    REQ["Request: subject/client, action, resource, context"] --> AUTHN["1. Verify authentication / token / session"]
    AUTHN --> A{"Định danh đáng tin?"}
    A -->|Không| LOGIN["Authenticate / reject invalid credential"]
    A -->|Có| ENT["2. Current entitlement + tenant + SoD + lifecycle"]
    ENT --> B{"Có quyền nghiệp vụ và không hard-deny?"}
    B -->|Không| DENY["DENY / do not offer MFA bypass"]
    B -->|Có| RISK["3. Risk + required assurance/freshness"]
    RISK --> C{"Outcome?"}
    C -->|Risk acceptable, assurance đủ| ALLOW["ALLOW + audit"]
    C -->|Need stronger proof| STEP["STEP_UP_REQUIRED"]
    C -->|Unacceptable risk| BLOCK["DENY / incident review"]
    C -->|Need independent approval| APPROVE["REQUIRE_APPROVAL"]
    STEP --> CHECK["IdP verifies strong authentication"]
    CHECK --> REEVAL["Re-evaluate policy, resource and risk"]
    REEVAL --> ENT
~~~

### Cổng 1: Xác thực

Token được phát bởi issuer được tin, còn hạn, đúng audience/type và bối cảnh client/sender phù hợp. Một access token không hợp lệ không được “chữa” bằng UI step-up mà bỏ qua verifier; client cần đi qua luồng xác thực/ủy quyền hợp lệ.

### Cổng 2: Quyền hiện hành

Dùng **RBAC/ABAC, tenant, resource owner, classification, grant validity, lifecycle status, SoD**. Dù token chứa role cũ, hành động ngoài **current state** cần DENY theo SLA.

### Cổng 3: Mức bảo đảm và rủi ro

Nếu user **đã có quyền** nhưng assurance/freshness chưa đáp ứng hành động nhạy cảm, có thể yêu cầu xác thực mạnh hơn. Nếu điều kiện cơ bản vi phạm, chọn **DENY**, **PENDING_APPROVAL** hoặc **INDETERMINATE** theo policy, không cho người dùng thử MFA vô hạn.

## 4. Những tín hiệu đầu vào của step-up decision

Không có một “risk score” chung đúng cho mọi tổ chức. Một risk engine nên kết hợp tín hiệu đáng tin, chính sách theo hành động và dữ liệu có độ mới xác định.

| Nhóm tín hiệu | Ví dụ | Nguồn tin cậy cần kiểm | Rủi ro diễn giải |
| --- | --- | --- | --- |
| **Subject** | Stable user ID, lifecycle state, role, contractor expiry. | HRIS/IGA/IdP mappings. | Email không ổn định, quyền cache stale. |
| **Authentication** | ACR/AAL, AMR, auth_time, MFA strength, phishing resistance. | IdP/AS token/session verified. | Một claim không có nghĩa mọi action đã đủ assurance. |
| **Session** | Session age, auth freshness, token issuance/refresh, client trust. | IdP/RP session metadata đáng tin. | Token được refresh chưa chắc user mới xác thực lại. |
| **Device** | Managed status, device compliance, attestation, security health. | MDM/EDR/device trust service. | Client có thể tự khai user-agent/compliant=true. |
| **Network** | IP reputation, ASN, corporate tunnel, anonymizer hints. | Edge/risk service. | NAT/VPN/địa lý không khẳng định tấn công. |
| **Behavior** | Impossible travel, unusual time, repeated failures, abnormal API volume. | Risk analytics với provenance. | False positives do du lịch, roaming, automation. |
| **Resource** | Data classification, payment amount, target environment, tenant. | Backend/resource catalog. | Không lấy classification từ request body. |
| **Action** | Read, export, payment approve, change MFA, grant admin. | API endpoint/business operation. | Tên role READ có thể che export gián tiếp. |
| **Transaction** | Beneficiary changed, account destination, new payee, business actor history. | Payment/ERP domain data. | Phải ràng buộc challenge với giao dịch thực. |
| **Threat/incident** | Compromised user/device, leaked credential, impossible behavior. | SOC/incident controls. | Risk “high” chưa nói rõ hành động bị cấm thế nào. |
| **Environment** | Production vs sandbox, corporate vs unmanaged. | Deployment/tenant authority. | Staging principal không được sử dụng quyền prod. |
| **Policy** | SoD rules, legal hold, JIT approval, privilege elevation conditions. | Policy owner và versioned PDP. | Strong authentication không override hard-deny. |

### Tín hiệu đáng tin và không đáng tin

**Client-supplied headers** như X-Device-Trusted, X-Risk-Level, X-User-Id hoặc X-Tenant không phải chứng cứ chỉ vì chúng hiện trong HTTP request. Gateway và backend phải **xác minh nguồn, chữ ký/attestation, session hoặc identity context**, rồi mới dùng làm policy input. Với dữ liệu thiếu, nên ghi **UNKNOWN** thay vì ngầm mặc định SAFE.

## 5. Mức rủi ro và ngưỡng quyết định chỉ là công cụ hỗ trợ

Một mô hình đơn giản có thể tính:

\[
R = w_1 \cdot \text{accountRisk} +
    w_2 \cdot \text{deviceRisk} +
    w_3 \cdot \text{networkRisk} +
    w_4 \cdot \text{transactionRisk}
\]

Các biến, trọng số, calibration, threshold và confidence phải được kiểm định bằng dữ liệu thật theo **risk appetite**. Đây chỉ là minh họa; **không coi công thức cộng điểm là chuẩn của NIST hoặc OAuth**, cũng không dùng điểm thấp để bỏ hard-deny.

### Ví dụ quyết định theo tier (giả định)

| Tier | Hoàn cảnh minh họa | Quyết định có thể phù hợp |
| --- | --- | --- |
| **Low** | Đọc thông tin công khai, phiên còn mới, thiết bị đáng tin. | ALLOW nếu permission và assurance đủ. |
| **Moderate** | Xem thông tin khách hàng nội bộ từ thiết bị mới. | STEP_UP bằng MFA có mức bảo đảm phù hợp, hoặc chính sách device trust. |
| **High** | Xuất PII hoặc đổi beneficiary có tín hiệu nguy cơ. | Phishing-resistant step-up + transaction binding/approval, hoặc DENY tùy policy. |
| **Critical** | Account Leaver, compromised device có hard deny, cross-tenant trái quyền. | DENY/containment, không cho MFA “vượt qua”. |
| **Unknown** | Không lấy được bắt buộc device compliance hay current permission state. | Fail-safe/INDETERMINATE; thông điệp và escalation có kiểm soát. |

**Ranh giới giữa các tiers là lựa chọn của tổ chức, không phải chuẩn phổ quát.** Một hành động như chuyển tiền có thể luôn đòi xác thực mạnh **dù risk score thấp**, trong khi một thay đổi mạng hợp lệ không nhất thiết cần chặn toàn bộ truy cập.

### Rule-based và ML-based

- **Rule-based:** dễ giải thích, kiểm thử, version; có thể bỏ sót tín hiệu mới hoặc nhiều false positives.
- **Statistical/ML:** phát hiện bất thường tổ hợp, nhưng cần data quality, drift monitoring, fairness review và tránh phụ thuộc hoàn toàn vào mô hình không giải thích được.
- **Hybrid:** hard-deny và policy bắt buộc được thực thi trước, risk model dùng để đề xuất challenge/tăng assurance ở các trường hợp còn đủ điều kiện.

Không dùng một model output không có provenance làm lý do **tự động cấp privileged access**.

## 6. Authentication assurance: AAL, ACR, AMR và auth_time

Các thuật ngữ dễ bị đánh đồng:

| Thuộc tính | Nghĩa đúng | Lưu ý khi triển khai |
| --- | --- | --- |
| **Authenticator Assurance Level (AAL)** | Mức bảo đảm xác thực theo khung NIST khi tổ chức dùng chuẩn này. | Không phải claim mặc định có trong mọi OAuth token. |
| **acr** | Authentication Context Class Reference của OIDC, biểu diễn lớp ngữ cảnh do IdP công bố. | Chuỗi acr có nghĩa theo hợp đồng/issuer; không so sánh tên tùy tiện. |
| **amr** | Authentication Methods References mô tả phương thức đã dùng theo issuer/profile. | amr=mfa không tự bảo đảm phishing resistance hay độ mới. |
| **auth_time** | Thời điểm người dùng thực sự xác thực theo OIDC semantics. | Access token iat hoặc refresh_at không thay thế auth_time. |
| **max_age** | Trong OIDC, giới hạn tuổi xác thực mà RP yêu cầu trong authorization request khi được hỗ trợ. | AS phải thực thi semantics; client phải kiểm response theo contract. |
| **prompt** | Hướng dẫn tương tác của OIDC; prompt=login có thể ép đăng nhập lại theo yêu cầu. | Không tự bảo đảm một ACR mạnh hơn nếu không có policy tương ứng. |
| **Session age** | Thời gian phiên tại IdP hoặc ứng dụng tồn tại. | Phiên mới tạo không chắc phản ánh authentication assurance cần thiết. |
| **Step-up proof** | Bằng chứng từ AS/IdP rằng yêu cầu xác thực mới đã đạt. | Phải gắn với đúng user/client/session/action theo design. |

### Ví dụ phân biệt thời điểm

~~~text
08:00  User đăng nhập bằng phương thức thông thường.
10:00  Client refresh access token từ refresh token.
10:05  User muốn đổi phương thức MFA hoặc xuất dữ liệu nhạy cảm.
10:06  IdP yêu cầu WebAuthn/step-up và xác minh thành công.
~~~

**Token cấp lúc 10:00 không chứng minh người dùng đã tái xác thực lúc 10:00.** Hệ thống phải đánh giá **auth_time và assurance evidence** đúng nguồn. Nếu risk policy yêu cầu xác thực mới trong 5 phút, phải xác nhận bước thành công lúc 10:06 được ràng buộc với user và action, không chỉ so thời điểm token mới được cấp.

### Không tự đặt thứ tự ACR chuỗi

Một issuer có thể dùng acr=urn:example:aal2, issuer khác dùng giá trị vendor riêng. Không dùng so sánh chuỗi lexical hoặc giả định acr chứa số cao hơn luôn mạnh hơn. **Ánh xạ assurance mức yêu cầu phải do identity owner định nghĩa** và kiểm tính tương thích giữa AS và RS.

## 7. Những phương thức step-up và độ mạnh khác nhau

| Phương thức | Có thể dùng khi | Hạn chế |
| --- | --- | --- |
| **WebAuthn/FIDO2 security key hoặc platform passkey phù hợp** | Phishing-resistant authentication được policy yêu cầu. | Cần kiểm RP ID/origin, user presence/verification, enrollment/recovery. |
| **TOTP authenticator** | Một số mức MFA trung bình khi được phép. | Có thể bị phishing/realtime relay; không phải phishing-resistant. |
| **Push confirmation có number matching và kiểm soát fatigue** | Môi trường hỗ trợ và policy chấp nhận. | Có nguy cơ social engineering, push bombing, mệt mỏi chấp thuận. |
| **SMS/voice OTP** | Phương án dự phòng theo chính sách và mức rủi ro cho phép. | SIM swap, interception, phishing; không xem như mạnh bằng WebAuthn. |
| **Hardware-backed client/device attestation** | Bổ sung chứng minh thiết bị/runtime đáp ứng yêu cầu. | Không tự thay user authentication hoặc business permission. |
| **Re-enter password** | Reauthentication khi policy cho phép. | Không tự nâng mức chống phishing hay MFA nếu chỉ nhập lại cùng password. |
| **Independent human approval** | Hành động nhạy cảm cần SoD/maker-checker. | Đây là approval, không phải authenticator của user đang gọi API. |
| **Privileged Access Management/JIT** | Activation quyền admin có TTL và approval. | JIT riêng với step-up; cần authorization và deactivation thực tế. |

**Không nói “đã MFA” là đủ** nếu policy yêu cầu **phishing-resistant** hoặc xác nhận giao dịch. Khả năng **đổi/khôi phục MFA factor** cũng là đường tấn công: khi authenticator bị thay bằng kênh yếu, assurance toàn bộ luồng có thể bị kéo xuống.


## 8. State machine của quyết định step-up

Một luồng step-up cần quản lý **yêu cầu ban đầu**, **challenge**, **bằng chứng xác thực mới** và **quyết định cuối**. Không nên giữ một cờ global “user vừa MFA xong” rồi tự động cho mọi request nhạy cảm.

~~~mermaid
stateDiagram-v2
    [*] --> REQUEST_RECEIVED
    REQUEST_RECEIVED --> HARD_DENIED: Lifecycle/tenant/SoD/entitlement deny
    REQUEST_RECEIVED --> ALLOWED: Policy + assurance đủ
    REQUEST_RECEIVED --> CHALLENGE_PENDING: Need stronger/fresher authentication
    REQUEST_RECEIVED --> APPROVAL_PENDING: Independent approval required
    REQUEST_RECEIVED --> INDETERMINATE: Missing mandatory signal
    CHALLENGE_PENDING --> CHALLENGE_FAILED: Fail, timeout, cancel, replay
    CHALLENGE_PENDING --> PROOF_RECEIVED: IdP step-up completes
    PROOF_RECEIVED --> REEVALUATING: Verify proof + bind request
    REEVALUATING --> ALLOWED: Current policy, risk and proof pass
    REEVALUATING --> HARD_DENIED: State changed or proof invalid
    REEVALUATING --> CHALLENGE_PENDING: Stronger assurance still required
    APPROVAL_PENDING --> REEVALUATING: Approval with authority verified
    INDETERMINATE --> HARD_DENIED: Fail safe for sensitive action
    ALLOWED --> [*]
    HARD_DENIED --> [*]
    CHALLENGE_FAILED --> [*]
~~~

### Các thuộc tính cần lưu trong challenge state

| Trường | Tác dụng |
| --- | --- |
| **challengeId** | Định danh opaque khó đoán, có TTL và quản lý chống replay. |
| **verifiedSubjectRef** | User ID ổn định cùng issuer/tenant; không lấy từ UI header. |
| **clientId / sessionRef** | Ràng buộc với ứng dụng và phiên khởi tạo. |
| **action / resourceRef / tenantRef** | Bảo vệ đúng giao dịch cần step-up. |
| **operationVersion / transactionDigest** | Phát hiện thay nội dung giao dịch sau challenge. |
| **requiredAssurance / requiredMethods** | Mục tiêu ACR/phishing-resistant và freshness do policy yêu cầu. |
| **policyVersion / riskSnapshotRef** | Biết challenge được mở theo điều kiện nào. |
| **createdAt / expiresAt / maxAttempts** | Chống challenge cũ, spam và brute force. |
| **status / consumedAt** | Ngăn dùng lại bằng chứng cho nhiều hành động nếu policy chỉ cho một lần. |
| **idempotencyKey** | Xử lý submit/retry mạng không thực thi nghiệp vụ hai lần. |

**Challenge state phải được tạo/kiểm bằng hệ thống tin cậy**. Không nhận một challengeId do client bịa rồi suy ngược user đã xác thực thành công.

### Re-evaluation sau step-up là bắt buộc

Trong thời gian người dùng nhập OTP hoặc chạm passkey, **role có thể bị thu hồi, risk tăng, payment thay đổi số tiền, hoặc tài khoản bị Suspended**. Vì vậy trước khi thực thi action cần **đọc lại quyền, trạng thái tài nguyên, độ mới risk và proof**, không dựa nguyên quyết định “đủ quyền” được chụp trước challenge.

## 9. Kiến trúc PDP–PEP–IdP cho step-up

~~~mermaid
sequenceDiagram
    participant U as User
    participant C as Client / Web Portal
    participant PEP as API / Policy Enforcement Point
    participant PDP as Policy Decision Point
    participant PIP as HRIS/IGA/Risk/Device context
    participant AS as IdP/Authorization Server
    U->>C: Bắt đầu hành động nhạy cảm
    C->>PEP: Request với access token/session
    PEP->>PEP: Xác thực token, issuer, audience
    PEP->>PDP: Subject, action, resource, current assurance
    PDP->>PIP: Entitlement, JML, risk, device, SoD
    PIP-->>PDP: Trusted attributes, version, freshness
    PDP-->>PEP: STEP_UP_REQUIRED + requirement reference
    PEP-->>C: Step-up challenge signal (no side effect)
    C->>AS: Redirect/challenge theo flow hợp lệ
    AS->>U: Strong authentication / WebAuthn
    U-->>AS: User completes challenge
    AS-->>C: Verified step-up result via defined protocol
    C->>PEP: Resume same authorized action with new context
    PEP->>PDP: Re-evaluate current permissions, risk, transaction
    PDP-->>PEP: ALLOW or DENY
    PEP-->>C: Business result; audit
~~~

### Ai chịu trách nhiệm từng phần?

- **IdP/AS** chịu trách nhiệm xác thực người dùng, assurance claims/step-up result theo protocol và quản lý authenticator.
- **PDP** quyết định policy: hành động nào cần assurance nào, có hard-deny không, risk/context đáng tin ra sao.
- **PIP** cung cấp identity lifecycle, approved entitlements, device posture, resource classification, risk analytics; cần provenance và freshness.
- **PEP** kiểm token, gọi PDP, chặn action trước side effect, ràng buộc response với resource/action và recheck sau step-up.
- **Ứng dụng client** chỉ điều phối flow hợp lệ, không tự gán acr hoặc khai “MFA passed” bằng biến JavaScript.
- **Audit** lưu reason/policy/proof metadata và kết quả thực thi mà không log secret/token.

**Một bước MFA thành công ở IdP chưa chắc đủ để Resource Server ALLOW**. Nếu token được trình cho API vẫn là token cũ không mang assurance mới theo contract, PEP phải lấy được **verified step-up evidence** hoặc token/authorization context mới từ hệ thống đáng tin.

## 10. Step-up trong OAuth/OIDC và chứng cứ assurance

Với client sử dụng OIDC, AS/IdP có thể trả thông tin xác thực như **acr, amr, auth_time** trong **ID token** theo profile. Các yêu cầu như **max_age, prompt, acr_values** có nghĩa cụ thể theo OIDC và IdP support. API bảo vệ tài nguyên cần **access token dành cho chính nó**; ID token của OIDC không được coi là bearer access token.

### Một sequence rút gọn

~~~mermaid
sequenceDiagram
    participant WEB as Web App/BFF
    participant API as Finance API
    participant AS as OIDC Authorization Server
    participant U as User
    WEB->>API: payment.approve with existing access context
    API-->>WEB: Additional authentication needed
    WEB->>AS: Authorization request with PKCE + assurance/freshness request
    AS->>U: Phishing-resistant authentication
    U-->>AS: WebAuthn proof
    AS-->>WEB: Authorization code
    WEB->>AS: Exchange code with PKCE verifier
    AS-->>WEB: Tokens + assurance evidence per issuer contract
    WEB->>API: Retry same action with valid API token/context
    API->>API: Verify token and current action/risk/SoD
    API-->>WEB: ALLOW / DENY
~~~

### Khi Resource Server cần step-up

Một API có thể diễn đạt yêu cầu bổ sung trong response theo protocol đã hỗ trợ. **RFC 9470** mô tả một cơ chế OAuth step-up authentication challenge ở Resource Server; triển khai cần kiểm **AS/RS/client hỗ trợ, error semantics, các giá trị assurance và thời hạn**. Không giả định mọi API trả một HTTP status đơn lẻ hay mọi IdP hiểu cùng acr.

Ví dụ **mang tính khái niệm**:

~~~http
POST /payments/431/approve HTTP/1.1
Host: finance.example.internal
Authorization: Bearer <redacted-access-token>
Content-Type: application/json

{"approved": true}
~~~

~~~text
Resource Server decision:
  action: payment.approve
  currentAccess: ELIGIBLE
  currentAssurance: insufficient
  requiredAssurance: phishing-resistant plus recent user authentication
  outcome: STEP_UP_REQUIRED
  sideEffectsCommitted: false
~~~

### Các điều kiện sau khi IdP trả về

1. Client xác minh **authorization response** đúng state/PKCE/redirect và issuer theo protocol.
2. ID token được RP xác minh đúng **issuer, audience, nonce khi flow yêu cầu, signature, expiry và auth_time** theo OIDC contract.
3. **acr/amr phải được ánh xạ** theo policy và đúng assurance class mà tổ chức chấp nhận.
4. Resource Server chỉ tin **API token/step-up assertion** theo hợp đồng, không tin header client khai rằng MFA đã xong.
5. **Tính mới**: reauthentication phải nằm trong window của action, không chỉ token vừa refresh.
6. **Đúng subject/client/session** và không đánh tráo người dùng qua tab/window/account switch.
7. **Current state**: phải kiểm lại JML, role, SoD và resource version.
8. Nếu không đạt, **DENY hoặc CHALLENGE** theo policy; không fallback xuống factor yếu ngoài risk acceptance.

### Lưu ý với SAML SSO

Một Service Provider dùng SAML có thể sử dụng **AuthnContextClassRef** và thông tin authentication statement theo profile. Không tự so ACR của OIDC với SAML AuthnContextClassRef như hai chuỗi tương đương. Cần **mapping assurance được IdP/SP thỏa thuận** và reauthentication behavior thực sự được hỗ trợ. Tương tự, logout SAML/SSO không tự thu hồi mọi API token đã phát.

## 11. Freshness: step-up “mạnh” nhưng đã cũ vẫn có thể không đủ

Một câu hỏi quan trọng là **độ mới của bằng chứng xác thực**, không chỉ phương thức đã dùng.

### Ví dụ

~~~text
08:00  User hoàn tất WebAuthn khi vào SSO.
16:20  User mở tài nguyên payment nhạy cảm.
16:21  API yêu cầu strong auth <= 5 phút cho thao tác approve.
16:22  Client dùng token mới do refresh nhưng auth_time vẫn 08:00.
16:23  IdP yêu cầu user WebAuthn lại và trả auth_time phù hợp.
16:24  API kiểm assurance mới + resource/state/risk, rồi quyết định.
~~~

Dù cả hai lần token chứa cùng thông tin về user và factor, **bằng chứng lúc 08:00 không đáp ứng freshness năm phút ở 16:21**. Chỉ thay access token bằng token mới không giải quyết vấn đề nếu không có một authentication event mới được xác minh.

### Nguy cơ “MFA once, privileged forever”

Một cờ session toàn cục như **mfaPassed=true** có thể khiến chức năng payment, thay payout account, reset factor và grant admin đều được phép không giới hạn. Thiết kế cần xác định **scope, TTL, audience/client binding, transaction binding và step-up assurance evidence**. Đối với hành động rất nhạy cảm, sử dụng **single-operation proof/transaction confirmation** khi cần.

### Khi nào cần step-up lại?

- Auth_time quá xa hiện tại theo policy của action.
- Người dùng chuyển từ **read** sang **write/delete/export/privilege elevation**.
- Device hoặc risk state thay đổi đáng kể.
- Resource/tenant, payment amount hoặc beneficiary thay đổi.
- User đã đổi identity/account trong cùng trình duyệt.
- Một sự kiện session revocation, password reset hoặc authenticator rebinding xảy ra.
- Challenge trước bị consume, hết TTL hoặc không còn phù hợp policy version.

**Không ép step-up lại mỗi request nếu không cần**: điều này tăng mệt mỏi, có thể làm người dùng chấp nhận push bất cẩn và ảnh hưởng khả dụng. Xác định thời hạn theo risk và đánh giá thực tế.

## 12. Transaction binding và ngăn thay giao dịch sau step-up

Đối với hành động như **đổi tài khoản thụ hưởng, duyệt chuyển tiền, xuất hồ sơ khách hàng hoặc grant admin**, cần đánh giá **step-up có xác nhận đúng nội dung giao dịch hay chỉ xác thực lại user?**

### Mối nguy TOCTOU và transaction swapping

~~~text
1. User yêu cầu approve payment 431, số tiền 2 triệu.
2. App mở step-up và user xác thực thành công.
3. Trong khi challenge đang chạy, một request sửa payment lên 200 triệu.
4. App tiếp tục approve mà không kiểm version/content.
5. MFA đúng người, nhưng giao dịch đã khác bản mà user nghĩ mình duyệt.
~~~

### Ràng buộc được đề xuất

- Lưu **server-generated operationId** và approved transaction snapshot/version.
- Tạo **digest có domain separation** của những trường quan trọng như tenant, paymentId, amount, currency, beneficiary, operation version; không tính từ payload không tin cậy mà không chuẩn hóa.
- Khi challenge được giải, kiểm subject, client/session, action/resource, **current transaction version/digest**.
- Nếu **amount/payee/tenant thay đổi**, yêu cầu step-up/approval lại theo policy.
- Xử lý **nonce, expiry, consumedAt** và chống replay của proof.
- Trước commit, dùng **transactional authorization/optimistic locking** phù hợp, kiểm SoD trên resource history.
- Ghi bằng chứng **kết quả authorization** và **transaction commit outcome** riêng.

**WebAuthn chứng minh tương tác với RP theo protocol, không tự động hiển thị hoặc ký nội dung từng payment.** Nếu bài toán đòi **transaction confirmation** (người dùng nhìn thấy và xác nhận đúng số tiền/người nhận), phải bổ sung UX và bằng chứng gắn nội dung giao dịch theo thiết kế; không tuyên bố “WebAuthn = ký giao dịch” chỉ vì dùng security key.

## 13. Step-up versus deny: những hard-deny không thể vượt bằng MFA

| Điều kiện | Vì sao là DENY/không tự giải bằng step-up |
| --- | --- |
| **User đã Leaver/Suspended** | Account hoặc quyền không còn đủ điều kiện; cần lifecycle remediation/authority. |
| **Entitlement hết hiệu lực** | MFA không tạo role bị thu hồi. |
| **Tenant/resource mismatch** | Chứng minh user không mở quyền vào tenant khác. |
| **SoD self-approval** | Chính user đã tạo giao dịch, xác thực thêm không tạo người duyệt độc lập. |
| **Device compromised theo policy hard block** | MFA không khôi phục tính toàn vẹn của thiết bị. |
| **Legal hold/data residency restriction** | Yêu cầu pháp lý/chính sách không được bỏ qua bằng factor. |
| **Application token sai issuer/audience/type** | Phải xác thực đúng protocol và API trước. |
| **Unauthorised service principal** | Workload không thể “bấm MFA” để tự tạo authorization. |
| **Policy data bắt buộc không thể truy xuất** | Không biết quyền hiện hành thì không mặc định SAFE. |
| **Approval chưa có** | User authentication không thay approval của data/business owner. |

### Ví dụ Mover + SoD

Nhân viên An chuyển từ **Payment Creator** sang **Payment Approver**. An hoàn thành WebAuthn step-up nhưng cố duyệt một payment từng tự tạo. **Decision phải là DENY vì SoD**, không phải ALLOW. Một token/session mới có assurance cao không làm thay đổi lịch sử tác giả giao dịch.

## 14. UX và hướng dẫn người dùng khi cần step-up

Thiết kế step-up tốt cần **rõ ràng, ít gây nhiễu, hỗ trợ khôi phục có kiểm soát** và không làm lộ policy/risk signals nhạy cảm cho kẻ tấn công.

- Hiển thị **hành động cần bảo vệ**: “Xác nhận danh tính để thay tài khoản thanh toán”, không chỉ “MFA required” vô ngữ cảnh.
- Với giao dịch quan trọng, hiển thị **chi tiết chủ chốt đã xác minh ở server** để user kiểm trước khi xác nhận.
- Không tiết lộ nội bộ: cụ thể rule detection, secret risk score hoặc tiêu chí có thể bị game.
- Hỗ trợ **accessibility** và phương thức/phần cứng phù hợp theo policy, không tự fallback xuống kênh yếu chỉ để thành công.
- Tránh **push fatigue**: hạn chế số lần gửi, number matching khi phù hợp, cảnh báo bất thường và chức năng báo nghi gian lận.
- Challenge timeout, cancel, factor unavailable phải có thông báo, **không thực thi giao dịch** và cung cấp recovery channel được phê duyệt.
- Không buộc người dùng làm step-up liên tục trên các hành động low risk nếu phiên hiện hành đã đủ assurance.
- Nếu lỗi là **không có quyền**, hiển thị từ chối hoặc hướng dẫn access request, **không yêu cầu MFA trước rồi báo thiếu quyền** trừ khi chính sách chống lộ thông tin cần thiết.
- Nếu step-up fail do IdP outage, ghi **unavailable/indeterminate** thay vì “user thất bại MFA” hoặc “credential compromised” không chứng cứ.

### Recovery không thành đường yếu hơn

Nếu user mất passkey/security key, quy trình khôi phục phải có **identity proofing, factor replacement approval, risk limits và audit** tương xứng, đặc biệt với tài khoản privileged. Không dùng câu hỏi bảo mật đơn giản hoặc SMS yếu để âm thầm vượt yêu cầu phishing-resistant cho thay đổi admin.


## 15. Joiner: khởi tạo quyền và mức bảo đảm cần thiết

Một nhân viên mới thường có **tài khoản, MFA enrollment và quyền cơ bản** được chuẩn bị theo ngày bắt đầu. Quy trình step-up decision phải xem **identity proofing/enrollment status** chứ không coi “MFA đã đăng ký” là bằng chứng ngay lập tức cho mọi action.

### Dòng chảy Joiner

~~~mermaid
sequenceDiagram
    participant HR as HRIS
    participant IGA as IGA / Access governance
    participant IDP as IdP
    participant APP as App / PEP
    HR->>IGA: Joiner, verified subject, start effectiveAt
    IGA->>IDP: Pre-provision account, permitted enrollment
    IDP-->>IGA: Account/enrollment state
    IGA->>APP: Approved base entitlements, activation conditions
    APP->>APP: Before effectiveAt: DENY protected action
    HR->>IGA: Effective employment activation
    APP->>APP: Current lifecycle ACTIVE + permissions
    APP-->>IDP: Step-up if sensitive action needs higher assurance
    IDP-->>APP: Verified authentication evidence per contract
    APP->>APP: Re-evaluate policy and risk before ALLOW
~~~

**Các kiểm soát phải phân biệt:** tài khoản được tạo trước ngày làm việc để chuẩn bị **không có nghĩa quyền nghiệp vụ được kích hoạt sớm**. Nếu một user chưa hoàn tất enrollment ở phương thức mạnh theo policy, có thể cho enrollment có kiểm soát nhưng không dùng “đang enrollment” để mở chức năng nhạy cảm.

### Các tình huống

| Trạng thái Joiner | Decision phù hợp |
| --- | --- |
| Account provisioned nhưng effectiveAt trong tương lai. | DENY action nghiệp vụ, dù có passkey. |
| Active, quyền read-only, phiên assurance hợp lệ. | ALLOW đọc resource được duyệt. |
| Active, quyền payment.approve được duyệt nhưng chưa đạt authentication assurance. | STEP_UP_REQUIRED. |
| Không có entitlement payment.approve. | DENY hoặc access request theo workflow, không step-up để cấp quyền. |
| MFA enrollment chưa có phương thức đủ mạnh. | Enrollment/recovery workflow riêng; không downgrade tiêu chuẩn không được duyệt. |
| Cùng email với nhân viên cũ đã Leaver. | Verify stable subject/identity link, không dùng sessions/grants cũ. |

## 16. Mover: quyền mới, token cũ và SoD

Khi nhân viên Mover từ vai trò A sang B, ba sự kiện **gỡ quyền cũ, cấp quyền mới và bảo đảm xác thực** phải được điều phối.

### Ví dụ chuyển Creator → Approver

~~~text
08:55   Access token cũ chứa Creator scope, exp 09:25.
09:00   HRIS Mover effectiveAt.
09:01   IGA yêu cầu remove Creator entitlement.
09:02   IdP/SCIM trả ACK, nhưng token cũ vẫn có thể valid.
09:03   Current-state authorization chặn payment.create ở API.
09:04   Negative probe confirms Creator action DENY.
09:05   Approver grant activated after SoD gate.
09:06   User yêu cầu payment.approve: policy yêu cầu step-up.
09:07   User hoàn tất WebAuthn; current access/risk/SoD rechecked.
09:08   Approve payment của người khác có thể ALLOW.
09:09   Approve payment từng tự tạo vẫn DENY vì SoD.
~~~

### Điều cần ghi và kiểm

- Lifecycle event: **stable subject, revision, effectiveAt**.
- Desired rights: **toRevoke/toKeep/toGrant**, target, tenant, policy version.
- Actual rights: **IdP/SCIM/local ACL**, access token/session còn hạn, PEP effective access.
- Assurance: **acr/amr/auth_time từ nguồn tin cậy**, required ACR/freshness theo action.
- SoD: **vai trò tĩnh** lẫn **business actor history**.
- Sau step-up: **không cho quyền Creator cũ sống lại** do client refresh/cached JWT.
- Verification: **old action DENY, legitimate new action ALLOW, self-approval DENY** và no side effects.

**Step-up không giải quyết role overlap**. Trước khi cấp Approver, nếu rule cấm tồn tại đồng thời Creator, hệ thống cần **revoke-before-grant hoặc chặn bằng current-state PEP** tùy thiết kế và khả năng kiểm chứng, không dùng MFA như một ngoại lệ SoD.

## 17. Leaver, suspension và token/phiên tồn dư

Với Leaver/suspension, **trạng thái quyền hiện hành** phải được chặn dù user còn một phiên SSO đã xác thực mạnh.

~~~mermaid
flowchart LR
    HR["Leaver/Suspend effective"] --> IGA["IGA / policy current-state"]
    IGA --> IDP["Disable issuance / session or grant action"]
    IGA --> SCIM["SCIM account + group changes"]
    IGA --> PEP["PEP current access DENY"]
    IDP --> AUD["Audit + verification"]
    SCIM --> AUD
    PEP --> AUD
    AUD --> V{"All required targets verified?"}
    V -->|No| REM["UNVERIFIED / residual access remediation"]
    V -->|Yes| DONE["Verified deprovision"]
~~~

### Những điều step-up không thể sửa

- User đã **Leaver**, nhưng app-local PAT còn quyền.
- SCIM **active=false** được target nhận nhưng JWT cũ hoặc SP session còn dùng được.
- Resource Server chưa cập nhật trạng thái revoke do cache quá lâu.
- Account **suspended** vì incident nhưng session vẫn có ACR mạnh.
- Chủ sở hữu service account Leaver, nhưng automation cần được **chuyển owner**, không tự xóa một job hợp lệ.

### Khi xác thực lại vẫn có thể hợp lệ

Trong **khôi phục tài khoản** sau sự cố, organization có thể yêu cầu identity proofing/step-up theo quy trình quản trị. Nhưng đó là **quy trình phục hồi có thẩm quyền**, không phải đường tự mở lại những action nghiệp vụ đã bị hard-deny. Audit phải phân biệt **RECOVERY_APPROVED** với **USER_STEP_UP_SUCCEEDED**.

## 18. Service identity: vì sao không “bật MFA cho cron job”?

Service account, CI/CD runner và batch job không có người tương tác để nhận push MFA. Step-up decision của request **human** không thể áp nguyên xi lên principal phi con người.

| Context | Biện pháp tương ứng |
| --- | --- |
| CI/CD deploy production | Workload federation theo issuer/subject/ref/environment được duyệt, protected environment, independent approval khi policy yêu cầu. |
| Kubernetes CronJob gọi Finance API | Bound ServiceAccount token, STS/token exchange/managed identity, audience & scope hẹp. |
| Service principal đọc storage | Managed identity/mTLS/private_key_jwt và least privilege; không dùng user password. |
| Automation thay IAM policy | JIT role activation, change approval, secure workload attestation, SoD và audit. |
| Bot chạy thay user | Verified delegation/OBO + user entitlement/current state, không lấy owner làm originating user. |
| Emergency automation | Break-glass procedure có owner, TTL, approval/alert và hậu kiểm độc lập. |

### Không bịa human initiator

Một scheduled job chạy vào 02:00 có thể có **owner**, nhưng không có người dùng vừa xác thực. Log phải ghi **technical actor=workload**, **business owner** và **run trigger**, thay vì gắn giả owner làm user đã “MFA passed”. Nếu workflow cần sự phê duyệt của con người, đó là **separate approval process** có thể có step-up cho **người phê duyệt**, không phải cho robot.

### Thay đổi trust/cấp quyền sau Mover

Nếu pipeline chuyển từ repository A sang B, cần **thu hồi federation binding cũ** và kiểm principal B không có quyền rộng hơn. Step-up của con người sửa config không làm workload mới mặc nhiên đáng tin.

## 19. RBAC/ABAC: step-up là một điều kiện, không phải toàn bộ policy

Một quyết định có thể cần **RBAC role**, **ABAC conditions**, **authentication assurance**, **current lifecycle** và **transaction separation** cùng đạt.

Ví dụ rule khái niệm:

~~~text
PERMIT payment.approve ONLY IF:
    verifiedHumanSubject = TRUE
    lifecycleStatus = ACTIVE
    accountHold = FALSE
    roleContains(PAYMENT_APPROVER) = TRUE
    resourceTenant = subjectTenant
    payment.state = PENDING_APPROVAL
    payment.createdBy != subjectId
    payment.lastMaterialEditor != subjectId
    authenticationAssurance >= requiredForPaymentApprove
    authenticationFreshness <= policyWindow
    devicePolicy = COMPLIANT
    transactionVersion = stepUpBoundVersion
    noApplicableHardDeny = TRUE
~~~

Một số điều kiện ở trên có thể dẫn tới **STEP_UP_REQUIRED** (assurance/freshness chưa đủ), nhưng những điều kiện **không có quyền/hard-deny** phải dẫn tới **DENY**. Thứ tự thực thi cần tránh rò nội dung nhạy cảm: API không nên tiết lộ chi tiết resource cho caller không đủ quyền chỉ vì đã tính risk.

### ABAC động và cache

Nếu employee status, device risk hoặc resource classification thay đổi sau khi token phát, relying solely on token claims sẽ tạo **stale access window**. Đối với privileged actions, PDP/PEP cần **current-state** hoặc bounded cache tương thích SLA. “Token còn exp” không bằng “permission hiện hành cho phép”.

## 20. Risk signal freshness và trust provenance

Một risk score có thể đã tính ở phút trước, trong khi sự kiện **compromised device** vừa được SOC xác nhận. Nếu step-up chỉ dùng score cache chưa cập nhật, quyết định sẽ khác chính sách hiện hành.

### Metadata của tín hiệu nên gồm

~~~yaml
signal:
  name: device_compliance
  value: COMPLIANT
  source: managed-device-attestation
  authorityRef: corporate-device-trust
  observedAt: "2026-11-23T02:03:00Z"
  validUntil: "2026-11-23T02:08:00Z"
  confidenceCategory: VERIFIED
  signatureOrProvenanceRef: attestation-ref-114
  schemaVersion: device-risk-v2
~~~

Đây là ví dụ **envelope**, không phải chuẩn bắt buộc. Các fields phải được xác minh bởi bên thực thi; một risk signal có **signature** vẫn cần kiểm issuer, audience/purpose, freshness và policy trust. Không coi confidenceCategory: VERIFIED tự khai bởi client là đáng tin.

### Quy tắc dữ liệu thiếu

| Tín hiệu thiếu | Cách xử lý minh họa |
| --- | --- |
| Current lifecycle state của user. | Fail-safe với action nhạy cảm, không đoán ACTIVE. |
| Device attestation bắt buộc. | DENY/INDETERMINATE hoặc chuyển sang môi trường được quản lý theo policy. |
| Geolocation khả nghi nhưng không bắt buộc. | Risk challenge/review, không tự coi không có GPS là attacker. |
| Transaction snapshot/version. | Không commit action nhạy cảm; lấy lại dữ liệu server đáng tin. |
| IdP step-up result đang chờ. | PENDING/timeout; không ALLOW. |
| Risk analytics service lỗi trong low-risk request. | Policy có thể quy định hành vi bảo vệ bounded availability, cần audit và review. |
| Risk analytics service lỗi trong privileged change. | Không mặc định ALLOW khi thiếu điều kiện bắt buộc. |

**Không sử dụng tín hiệu bị thiếu như “risk = zero”**. Nhưng cũng tránh áp cùng mức xử lý cho dữ liệu không bắt buộc với mọi user, vì sẽ gây từ chối bất công, tăng support load và mở áp lực downgrade.

## 21. Risk model calibration, explainability và fairness

Risk-based step-up có thể gây friction cho nhân viên đi công tác, truy cập từ mạng di động, thiết bị hỗ trợ accessibility hoặc sử dụng VPN hợp lệ. Mô hình cần được **hiệu chỉnh**, không chỉ tối ưu giảm số vụ gian lận trên dữ liệu lịch sử thiên lệch.

### Các yêu cầu quản trị

- **Định nghĩa rõ risk outcome**: unauthorized payment, credential misuse, account takeover hoặc data exfiltration; không trộn tất cả vào một nhãn.
- **Lựa chọn tín hiệu phù hợp mục đích**: không sử dụng dữ liệu nhạy cảm cá nhân hoặc đặc điểm được bảo vệ như một proxy rủi ro thiếu cơ sở.
- **Đánh giá false positive và false negative** theo action, device cohort, user journey và tương thích accessibility.
- **Theo dõi drift** sau khi thay IdP, mạng VPN, thiết bị hoặc chính sách MFA.
- **Explainability cho auditor**: policyVersion, reasonCode, signal provenance/time và challenge outcome, không phải raw feature payload.
- **Hạn chế feedback loop**: nhóm user từng bị challenge có thể tạo nhiều logs hơn, khiến score về sau thiên lệch.
- **Canary/shadow mode** khi rollout model mới: thu thập prospective decisions không tự thay enforcement nếu chưa được duyệt.
- **Human override** chỉ qua thẩm quyền, hạn dùng và audit; không cho helpdesk tắt hard-deny tùy tiện.

### Fallback khi hệ thống rủi ro lỗi

Định nghĩa từ trước **fail-closed/fail-safe cho quyền critical** và cách xử lý sự cố với quyền ít nhạy cảm. Không để một thay đổi timeout ngầm làm policy ALLOW mọi request nhằm giữ latency. Nếu dùng cached risk, phải chứng minh **cache max age và điều kiện không cho stale data**.

## 22. Điều chỉnh risk policy và kiểm SoD trong access request

Một yêu cầu cấp quyền admin có thể đi qua:

1. **Human identity verified** bởi IdP/SSO.
2. **Current entitlement eligibility** và người hưởng quyền được xác minh.
3. **Risk assessment** theo action, tenant, device/session.
4. **Step-up cho requester/approver** nếu policy đòi.
5. **Independent approval** bởi người đủ thẩm quyền theo SoD.
6. **JIT grant** với TTL, phạm vi actions/resources cụ thể.
7. **Resource Server/Cloud IAM effective authorization** kiểm ở thời điểm thực thi.
8. **Expiry/revoke verification** sau khi task hoàn tất.

**MFA người yêu cầu và chữ ký người phê duyệt là hai kiểm soát khác nhau**. Người xin admin có thể chứng minh đúng danh tính nhưng vẫn thiếu thẩm quyền duyệt yêu cầu của mình. Cũng cần kiểm **người có thể impersonate/bind service principals**, không chỉ role danh nghĩa.

### Ví dụ SoD

Một manager vừa tạo access request cho chính mình vừa dùng group Admin để approve request đó. Step-up bằng security key không giải quyết xung đột **requester = beneficiary = approver** nếu policy cấm self-approval. PDP cần trả **DENY/REQUIRE_INDEPENDENT_APPROVAL** trước khi chạy connector grant.


## 23. Mẫu policy-as-data cho step-up decision

Một policy dễ kiểm toán cần định nghĩa **hành động, điều kiện quyền bắt buộc, assurance yêu cầu, freshness, risk, hard-deny và outcome** rõ ràng. Ví dụ dưới là **pseudo-YAML**, không phải cú pháp của IdP, OPA, Spring Security hoặc cloud vendor cụ thể:

~~~yaml
policyId: finance-transaction-step-up
version: "7"
status: ACTIVE
subjectType: HUMAN
resourceServer: finance-api
operation: payment.approve
applicableTenant: tenant-vn
preconditions:
  lifecycleState: ACTIVE
  requiredRole: PAYMENT_APPROVER
  disallowSelfApproval: true
  requireCurrentSubjectEntitlements: true
  requirePaymentState: PENDING_APPROVAL
  disallowCrossTenant: true
  denyIfSecurityHold: true
riskSignals:
  deviceTrust:
    required: true
    sourceRef: managed-device-service
    maxAgeSeconds: 300
  transactionRisk:
    sourceRef: finance-risk-engine
    maxAgeSeconds: 60
  accountRisk:
    sourceRef: identity-risk-service
    maxAgeSeconds: 60
assurance:
  requiredClassRef: corporate-phishing-resistant
  maxAuthenticationAgeSeconds: 300
  transactionBindingRequired: true
outcomes:
  onUnauthorisedEntitlement: DENY
  onSoDViolation: DENY
  onCompromisedDevice: DENY
  onMissingMandatorySignal: INDETERMINATE_FAIL_SAFE
  onAssuranceInsufficient: STEP_UP_REQUIRED
  onFreshVerifiedAssuranceAndPolicyPass: ALLOW
challenge:
  maxAttempts: 3
  ttlSeconds: 180
  singleUse: true
  bindToSubjectClientSessionActionResourceVersion: true
audit:
  requirePolicyVersion: true
  requireReasonCode: true
  logRawCredentials: false
~~~

### Đọc đúng ví dụ

- Các giá trị **60, 180, 300 giây chỉ là giả định phục vụ minh họa**, không phải mức mặc định bắt buộc của tiêu chuẩn.
- **requiredClassRef** phải ánh xạ tới khả năng IdP hỗ trợ thực tế và có kiểm thử assurance.
- **transactionBindingRequired** chỉ có ý nghĩa khi server thực sự **ràng buộc nội dung giao dịch** với challenge/proof.
- **OnMissingMandatorySignal** không cho action nhạy cảm đi tiếp; cần thống nhất error/fail-safe semantics với client.
- **Không tự tin giá trị YAML do client cung cấp** làm policy.
- Policy có **owner, phiên bản, môi trường, change approval, test evidence và rollback plan** ngoài fields minh họa.

## 24. Java pseudocode: hàm quyết định DENY, STEP_UP, ALLOW

Một giải pháp nên tách **token verification**, **current authorization**, **risk/assurance decision** và **business commit**. Ví dụ dưới giả định đối tượng VerifiedPrincipal đã được tạo **sau middleware xác minh token hợp lệ**; không nhận principal từ HTTP headers.

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.Set;

enum AccessDecision {
    ALLOW, STEP_UP_REQUIRED, DENY, REQUIRE_APPROVAL, INDETERMINATE
}

record VerifiedPrincipal(
    String subjectId,
    String issuer,
    String clientId,
    String tenantId,
    boolean tokenVerified,
    boolean humanUser
) {}

record CurrentRights(
    boolean active,
    boolean securityHold,
    Set<String> roles,
    long entitlementRevision
) {}

record PaymentView(
    String id,
    String tenantId,
    String state,
    String createdBySubjectId,
    String lastMaterialEditorSubjectId,
    long version
) {}

record TrustedAssurance(
    boolean verifiedByIssuer,
    String assuranceClassRef,
    Instant userAuthenticatedAt,
    String subjectId,
    String clientId,
    String sessionRef
) {}

record RiskSnapshot(
    boolean mandatorySignalsPresent,
    boolean mandatorySignalsFresh,
    boolean compromisedDevice,
    boolean riskAcceptable,
    boolean independentApprovalRequired
) {}

final class PaymentStepUpPolicy {
    AccessDecision decide(
        VerifiedPrincipal p,
        CurrentRights rights,
        PaymentView payment,
        TrustedAssurance assurance,
        RiskSnapshot risk,
        Instant now) {

        if (p == null || !p.tokenVerified() || !p.humanUser()
                || rights == null || payment == null) {
            return AccessDecision.DENY;
        }

        if (!rights.active() || rights.securityHold()
                || !p.tenantId().equals(payment.tenantId())
                || !"PENDING_APPROVAL".equals(payment.state())
                || !rights.roles().contains("PAYMENT_APPROVER")
                || p.subjectId().equals(payment.createdBySubjectId())
                || p.subjectId().equals(payment.lastMaterialEditorSubjectId())) {
            return AccessDecision.DENY; // Hard-deny không được MFA override.
        }

        if (risk == null || !risk.mandatorySignalsPresent()
                || !risk.mandatorySignalsFresh()) {
            return AccessDecision.INDETERMINATE;
        }

        if (risk.compromisedDevice()) {
            return AccessDecision.DENY;
        }

        if (risk.independentApprovalRequired()) {
            return AccessDecision.REQUIRE_APPROVAL;
        }

        if (!risk.riskAcceptable()) {
            return AccessDecision.DENY;
        }

        if (assurance == null
                || !assurance.verifiedByIssuer()
                || !p.subjectId().equals(assurance.subjectId())
                || !p.clientId().equals(assurance.clientId())
                || !"corporate-phishing-resistant".equals(
                        assurance.assuranceClassRef())
                || assurance.userAuthenticatedAt() == null
                || assurance.userAuthenticatedAt().isAfter(now)
                || Duration.between(
                        assurance.userAuthenticatedAt(), now).toMinutes() >= 5) {
            return AccessDecision.STEP_UP_REQUIRED;
        }

        return AccessDecision.ALLOW;
    }
}
~~~

### Những điều còn thiếu cố ý ở pseudocode

1. **VerifiedPrincipal** và **TrustedAssurance** chỉ là objects đã được tạo qua **thành phần kiểm cryptographic assertions hoặc policy adapter đáng tin**. Thuộc tính verifiedByIssuer không được lấy từ JSON client tự khai.
2. **issuer, audience, token type, client binding, expiry và token revocation** phải kiểm ở framework trước khi gọi policy.
3. **CurrentRights** cần lấy từ IGA/RS authoritative state hoặc PDP/PIP có freshness/consistency đáp ứng SLA.
4. **RiskSnapshot** phải có source provenance và expiry; ví dụ đã rút gọn thành booleans để dễ học.
5. **Không có logic transaction digest/version** trong hàm; PEP/business service phải kiểm challenge binding và optimistic locking trước commit.
6. Nếu tín hiệu bắt buộc thiếu, caller phải map INDETERMINATE thành **fail-safe** cho action này, không chuyển sang ALLOW.
7. **Step-up success không đồng nghĩa ALLOW**: phải gọi decide lại với resource/current rights mới và challenge result đã verify.
8. Các mức assurance, timeout và risk tiers cần được thiết kế theo thực tế doanh nghiệp, không copy hằng số ví dụ vào production.
9. Một expression đơn lẻ không giải quyết **cross-request concurrency, self-approval theo lịch sử sâu hoặc policy inheritance**; cần backend state và test.

### Bảo vệ bất đồng bộ

Nếu request approve tạo một **message queue job**, policy không nên chỉ chạy ở HTTP gateway rồi worker ghi thanh toán không kiểm nữa. Với hành động critical, worker phải nhận **authorized transaction context** có hạn, đã được ký/ràng buộc hoặc recheck policy, không tin message từ queue tự khai là step-up đã xong.

## 25. Java pseudocode: challenge verification và commit an toàn

Step-up decision thường làm request **dừng trước khi commit**, sau đó tiếp tục khi có proof đã xác minh. Cần thiết kế chống replay, account swapping và transaction swapping.

~~~java
record StepUpChallenge(
    String challengeId,
    String subjectId,
    String clientId,
    String sessionRef,
    String operationId,
    String resourceId,
    String action,
    long resourceVersion,
    String approvedTransactionDigest,
    Instant expiresAt,
    boolean consumed
) {}

record VerifiedStepUpProof(
    String subjectId,
    String clientId,
    String sessionRef,
    String assuranceClassRef,
    Instant authenticatedAt,
    String issuerProofRef
) {}

final class PaymentStepUpCommit {
    void approvePayment(
        StepUpChallenge challenge,
        VerifiedStepUpProof proof,
        VerifiedPrincipal caller) {

        // Pseudocode: phải thực hiện trong transaction/locking phù hợp.
        challengeStore.lockSingleUseChallenge(challenge.challengeId());

        if (challenge.consumed()
                || !clock.now().isBefore(challenge.expiresAt())
                || !challenge.subjectId().equals(caller.subjectId())
                || !challenge.clientId().equals(caller.clientId())
                || !challenge.subjectId().equals(proof.subjectId())
                || !challenge.clientId().equals(proof.clientId())
                || !challenge.sessionRef().equals(proof.sessionRef())
                || !proofVerifier.validateIssuerAndFreshness(proof)) {
            throw new SecurityException("Step-up proof invalid");
        }

        Payment current = repository.getForUpdate(challenge.resourceId());

        if (current.version() != challenge.resourceVersion()
                || !digestService.computeBoundDigest(current).equals(
                    challenge.approvedTransactionDigest())) {
            throw new SecurityException("Transaction changed");
        }

        // Recheck quyền hiện hành, SoD, risk, status và assurance
        // ngay trước business commit.
        if (policyEngine.evaluateCurrent(caller, proof, current)
                != AccessDecision.ALLOW) {
            throw new SecurityException("Current policy denied");
        }

        repository.approveOnceWithIdempotency(
            current, challenge.operationId());

        challengeStore.markConsumedAtomically(challenge.challengeId());
        audit.emitSafeResult(challenge.operationId(), "APPROVED");
    }
}
~~~

### Chú ý tính nguyên tử

Ví dụ mô tả ý tưởng, **không đảm bảo atomicity giữa DB thanh toán, challenge store và audit store**. Hệ thống thật cần:
- Transaction/locking hoặc optimistic concurrency theo DB.
- Một **idempotency key** cho business operation, không tạo payment approve hai lần do retry.
- Outbox hoặc cơ chế sự kiện tin cậy để audit không bị mất sau commit.
- Chính sách xử lý trường hợp **commit thành công nhưng response timeout**.
- Chống reuse challenge và proof khi người dùng đổi tab/đổi tài khoản/đổi target resource.
- Tính toán digest trên **canonical server-side transaction snapshot**, không hash chuỗi JSON không được chuẩn hóa.
- Giảm khả năng time-of-check/time-of-use nếu data, role hoặc transaction thay đổi.
- Không log raw proof/token, assertion/cookie hoặc security key data nhạy cảm.

## 26. Kiểm thử policy ở mức unit và integration

Một bảng test đơn giản nên kiểm **hard deny trước, then step-up when eligible, then allow after proof**:

| Case | Quyền hiện hành | Assurance/risk | Kết quả |
| --- | --- | --- | --- |
| Đúng role, compliant device, WebAuthn mới xác thực. | Đủ. | Fresh và đủ class. | ALLOW. |
| Đúng role, phiên đã 8 giờ. | Đủ. | Freshness thiếu. | STEP_UP_REQUIRED. |
| Không có role Approver. | Thiếu. | WebAuthn rất mới. | DENY. |
| User đã Leaver. | Disabled. | WebAuthn rất mới. | DENY. |
| User là người tạo payment. | SoD conflict. | WebAuthn mới. | DENY. |
| Device compromised theo hard policy. | Đủ. | Risk critical. | DENY. |
| Missing required device state. | Đủ. | Unknown mandatory signal. | INDETERMINATE/fail-safe. |
| Payment thay đổi phiên bản trong lúc user step-up. | Có thể đủ. | Proof cũ không match transaction. | DENY/NEW_CHALLENGE. |
| Cần approval độc lập nhưng chưa có. | Eligibility có. | Strong auth đủ. | REQUIRE_APPROVAL. |
| Phiên active, role đúng, only read action. | Đủ. | Baseline assurance đủ. | ALLOW theo policy read. |

### Test oracle độc lập

Kỳ vọng phải dựa trên **approved policy**, current-state của IAM và resource dữ liệu thử, không dùng lại cùng thuật toán production làm “đáp án”. Cần test **idempotency, no side effects** và audit reason code, không chỉ kiểm HTTP 200/401/403.


## 27. Case study 1: xuất dữ liệu PII từ thiết bị lạ

### Bối cảnh

Nhân viên **Linh** làm việc tại bộ phận chăm sóc khách hàng, có entitlement xuất **thống kê tổng hợp** tenant VN nhưng không được xuất **dữ liệu gốc có định danh cá nhân**. Linh đăng nhập SSO bằng phương thức được chấp nhận vào 08:00. Lúc 15:00, ứng dụng nhận một yêu cầu download báo cáo tổng hợp từ thiết bị chưa quản lý.

### Phân tích

~~~text
Subject: person-linh (verified through corporate IdP)
Lifecycle: ACTIVE
Approved role: CUSTOMER_REPORT_READER
Action: report.summary.export
Resource: tenant-vn, classification INTERNAL
Session: authenticated at 08:00
Device: unmanaged, compliance policy UNKNOWN
Network: unfamiliar ASN, risk signals moderate
Required assurance: strong recent authentication
Result: STEP_UP_REQUIRED only if device policy permits remediation
~~~

Nếu tổ chức **bắt buộc dùng managed device** cho mọi export, đầu ra phải là **DENY/REQUIRE_MANAGED_DEVICE**, không phải step-up. Nếu policy cho phép thiết bị không quản lý sau WebAuthn và thêm giới hạn export, hệ thống có thể đưa ra STEP_UP_REQUIRED kèm điều kiện.

### Nhánh quyết định

| Nhánh | Tình huống | Outcome |
| --- | --- | --- |
| **A** | Linh xuất summary đã được duyệt từ thiết bị hợp lệ, assurance còn mới. | ALLOW. |
| **B** | Linh xuất summary từ thiết bị mới, chính sách cho phép sau step-up. | STEP_UP, sau đó re-evaluate. |
| **C** | Linh chọn raw-PII export không có entitlement. | DENY dù WebAuthn hoàn tất. |
| **D** | Device bị compromise và policy hard-block. | DENY, mở incident nếu cần. |
| **E** | Thiếu device attestation bắt buộc. | INDETERMINATE/fail-safe theo policy. |
| **F** | Trong lúc step-up, tenant/report classification bị đổi. | Re-evaluate, hủy proof cũ nếu không còn match. |

### Bằng chứng cần ghi

- Verified subject/client/session, action/report/resource classification.
- Policy version, trusted device/risk signal refs và timestamps.
- Step-up challenge status, required assurance class và proof metadata (không raw token).
- Final decision, download object ID, data egress event và business outcome.
- Phiên bản quyền hiện hành và reason nếu DENY.

**Một bước MFA thành công không chứng minh báo cáo đã được xuất**, và một download thành công không chứng minh toàn bộ dữ liệu trong file đúng classification. Kiểm cả **authorization của object kết quả** và audit downstream storage.

## 28. Case study 2: đổi tài khoản ngân hàng thụ hưởng

### Bối cảnh

Một user có quyền chỉnh thông tin người thụ hưởng (beneficiary), nhưng đây là hành động nhạy cảm: nếu attacker chiếm phiên đã đăng nhập, họ có thể chuyển khoản thanh toán sang tài khoản do họ kiểm soát.

### Desired workflow

1. User yêu cầu thay beneficiary cho invoice payment plan.
2. PEP xác minh session/token, current entitlement và resource owner.
3. Backend lấy **bank account masked display**, owner và resource version; xác minh dữ liệu từ nguồn đáng tin.
4. Risk engine xem xét **new payee, device, velocity, transaction amount, recent account changes**.
5. PDP trả **STEP_UP_REQUIRED** với yêu cầu **phishing-resistant recent authentication** và, khi policy đòi, **independent approval**.
6. User nhìn thấy chi tiết thay đổi quan trọng và hoàn tất challenge theo IdP.
7. Backend xác minh **proof gắn subject/client/session + request version/digest**, chưa hết TTL và chưa consume.
8. Backend **re-evaluate current rights/risk/SoD**.
9. Chỉ sau các kiểm tra, thực hiện thay beneficiary với optimistic locking/idempotency.
10. Audit ghi quyết định và business commit riêng; nếu payee thay trong thời gian challenge, hủy proof và yêu cầu xác nhận lại.

### Negative tests phải có

| Thử nghiệm | Kết quả mong đợi |
| --- | --- |
| Challenge được mở cho beneficiary A nhưng submit beneficiary B. | DENY; không lưu B. |
| User đổi tenant giữa tab/challenge. | Proof không được sử dụng chéo tenant. |
| User đã Mover mất quyền edit trước khi xác thực xong. | DENY. |
| Challenge được dùng lại để đổi beneficiary thứ hai. | DENY/replay detected. |
| Device risk chuyển critical sau step-up. | Re-evaluation DENY. |
| Người phê duyệt chính là người đã tạo request, policy cấm. | REQUIRE_INDEPENDENT_APPROVAL hoặc DENY. |
| Payment record version đã thay. | Hủy/refresh transaction challenge; không commit với version cũ. |
| API timeout sau commit làm client retry. | Idempotency tránh thay/ghi hai lần ngoài mong muốn. |

**Thành công bảo mật không chỉ là “user đã chạm passkey”** mà là giao dịch đúng nội dung đã được duyệt, đúng chủ thể/quyền, đúng phiên và không có tác dụng phụ ngoài phạm vi.

## 29. Case study 3: Mover tới role Finance Approver

### Timeline và correlation

| Mốc minh họa | Diễn biến | Điều cần kiểm |
| --- | --- | --- |
| 09:00 | HRIS Mover effectiveAt: Creator → Approver. | Canonical subject + revision. |
| 09:01 | IGA revoke Creator ở IdP/SCIM và policy PEP. | Target ACK khác verified DENY. |
| 09:02 | Creator access token cũ vẫn còn exp. | Current-state/API phải chặn Creator theo SLA. |
| 09:03 | Negative probe payment.create bị DENY. | No side effects, API healthy. |
| 09:04 | Role Approver được grant sau SoD gate. | No forbidden overlap. |
| 09:05 | User yêu cầu duyệt payment. | Eligibility + current state. |
| 09:06 | Session assurance cũ; step-up được yêu cầu. | Challenge bound to payment/version. |
| 09:07 | WebAuthn step-up hoàn thành. | Verified auth_time, ACR, identity binding. |
| 09:08 | Payment của người khác ALLOW nếu approved. | Final policy check. |
| 09:09 | Payment do chính user từng tạo vẫn DENY. | Transaction SoD vẫn hiệu lực. |

### Hai lỗi thiết kế

**Lỗi 1 — MFA đè quyền:** API thấy WebAuthn success rồi ALLOW payment.create bằng token cũ dù IGA đã revoke. Đây là lỗi **current authorization**, không phải thiếu MFA.

**Lỗi 2 — SoD đè bằng role mới:** user hoàn thành step-up và có Approver role, nhưng lại tự duyệt payment do chính họ tạo. Đây là lỗi **transaction history policy**, không phải authentication assurance.

### Bằng chứng cần có

Tối thiểu: HRIS event, IGA desired delta, target revoke readback, API old-action deny, Approver grant approval, step-up proof metadata, API approval ALLOW/DENY và transaction actor history. Nếu một required target vẫn cho Creator action ALLOW, trạng thái Mover phải **PARTIAL/REMEDIATION**, dù bước step-up của Approver đã hoạt động.

## 30. Case study 4: privileged access qua PAM/JIT và approval

### Bối cảnh

Một kỹ sư cần thay policy production firewall trong 20 phút. Tài khoản kỹ sư hiện chỉ có role Observer. Tổ chức yêu cầu quyền privileged qua **PAM/JIT**, WebAuthn step-up, approval độc lập và ghi audit.

### Các cổng cần tách

~~~mermaid
flowchart TD
    R["Engineer requests time-bound prod change"] --> E{"Eligible for JIT role?"}
    E -->|Không| DENY["DENY / require entitlement request"]
    E -->|Có| A{"Independent approval present?"}
    A -->|Chưa| PENDING["REQUIRE_APPROVAL"]
    A -->|Có| X{"Current assurance/risk sufficient?"}
    X -->|Không| STEP["STEP_UP_REQUIRED"]
    X -->|Có| J["Activate narrow JIT role, TTL & scope"]
    STEP --> C["Verified WebAuthn / re-evaluate"]
    C --> X
    J --> ACTION["PEP checks actual config action"]
    ACTION --> END["Revoke JIT + verify effective DENY"]
~~~

### Kiểm soát cần quan tâm

- WebAuthn step-up của engineer **không thay approval của change owner**.
- JIT role phải có **action/resource/env scope** cụ thể, TTL và owner rõ.
- Nếu quyền privileged không được approved, token chứa acr mạnh không được **suy ra quyền admin**.
- Principal workload thực thi automation được xác thực riêng; người approve có thể là human, không bịa MFA cho service account.
- Sau TTL/deactivation, phải **readback và negative probe** trên target; không coi một notification “role expired” là bằng chứng toàn bộ session đã chấm dứt.

## 31. Audit, log correlation và giải thích quyết định step-up

Step-up có hai chuỗi sự kiện cần nối: **quyết định ban đầu** và **bằng chứng challenge/final action**. Audit phải ghi ai chịu trách nhiệm cho chính sách, ứng dụng và resource nào bị tác động, đồng thời không biến logs thành kho credential.

### Taxonomy sự kiện đề xuất

| Event | Metadata quan trọng | Không được nhầm |
| --- | --- | --- |
| ACCESS_EVALUATED | Subject/client/resource/action, policy version, current decision, signals ref. | Quyết định ALLOW không phải business commit. |
| STEP_UP_REQUIRED | ChallengeRef, required assurance/freshness, reason category. | Chưa phải xác thực thành công. |
| STEP_UP_STARTED | Session/client/subject, challengeRef, timestamp. | Chỉ có challenge UI, chưa có proof. |
| STEP_UP_COMPLETED | Verified IdP proof reference, method class, auth_time. | Không tự có permission. |
| STEP_UP_FAILED/CANCELLED/EXPIRED | Outcome, attempts, reason class, rate limiting. | Không chắc user là attacker. |
| STEP_UP_REJECTED | Subject/session mismatch, replay, transaction changed, policy deny. | Không được đánh đồng với MFA factor lỗi. |
| APPROVAL_REQUIRED/GRANTED | Approver, beneficiary, requestRef, policy/SoD result. | Step-up của requester không thay approval. |
| FINAL_AUTHZ_DECISION | ALLOW/DENY/INDETERMINATE, policyVersion, entitlement revision. | Không chứng minh downstream commit. |
| TRANSACTION_COMMITTED | Business operationId, resourceRef, idempotency/commit status. | Không phải authentication event. |
| JML_RIGHTS_CHANGED | HRIS eventId, effectiveAt, target grants, state revision. | SCIM ACK không tự là PEP DENY. |
| REVOKE_VERIFIED | Target/PEP, denied action, verifiedAt, evidenceRef. | 503/timeout không phải policy DENY. |

### Structured event JSON minh họa

~~~json
{
  "eventType": "STEP_UP_DECISION",
  "schemaVersion": "risk-access-v1",
  "eventId": "evt-risk-882",
  "correlationId": "corr-payment-431",
  "operationRef": "payment-431-approval",
  "subjectRef": "person-4821",
  "issuerRef": "corporate-idp",
  "clientRef": "finance-portal",
  "sessionRef": "session-protected-ref",
  "tenantRef": "tenant-vn",
  "action": "payment.approve",
  "resourceRef": "payment-431",
  "policyId": "finance-transaction-step-up",
  "policyVersion": "7",
  "entitlementRevision": 29,
  "riskCategory": "ELEVATED",
  "riskSignalRefs": ["device-risk-114", "transaction-risk-76"],
  "currentAssuranceRef": "corporate-password-mfa",
  "requiredAssuranceRef": "corporate-phishing-resistant",
  "decision": "STEP_UP_REQUIRED",
  "reasonCode": "RECENT_STRONG_AUTH_REQUIRED",
  "occurredAt": "2026-11-23T02:06:00Z",
  "rawTokenLogged": false
}
~~~

Không ghi **raw access/refresh tokens, session cookie, passkey secret/key material, OTP, MFA seed hoặc bản đầy đủ dữ liệu payment**. Correlation IDs có thể cho phép liên kết cá nhân và phải có retention, access control, data minimization và audit khi analyst tra cứu.


## 32. Threat model: cách attacker tìm đường vượt step-up

Một hệ thống step-up có nhiều bề mặt tấn công: **sai identity mapping, downgrade phương thức, bỏ qua PEP, replay challenge, phishing MFA, giả mạo trust signal, xử lý lỗi fail-open và race conditions**.

| Mối đe dọa | Khai thác thường gặp | Biện pháp phòng vệ |
| --- | --- | --- |
| **Step-up bypass** | Gọi trực tiếp API không đi qua giao diện yêu cầu MFA. | PEP tại Resource Server và mọi async/legacy path. |
| **Client-side boolean spoofing** | Sửa cờ mfaPassed ở UI/local state. | Chỉ nhận proof được IdP/AS xác minh ở server. |
| **ACR confusion** | AS A và AS B dùng acr giống chữ nhưng khác assurance. | Mapping issuer-bound do IdP owner duyệt, token validation. |
| **Stale auth_time** | Refresh access token để giả “đã đăng nhập mới”. | Dùng verified authentication time, không dùng iat/refresh timestamp. |
| **MFA fatigue/social engineering** | Gửi hàng trăm push chờ user chấp thuận. | Rate limits, phishing-resistant options, anti-fatigue UX và alerts. |
| **Phishing OTP** | Lừa lấy TOTP/SMS để hoàn tất step-up. | Phương thức chống phishing khi risk/policy đòi. |
| **Factor reset abuse** | Attacker chiếm recovery flow và đăng ký factor yếu. | Identity proofing/approval, delay, alerts, recovery assurances. |
| **Challenge replay** | Dùng proof đã hoàn thành cho một operation khác. | One-time challenge, TTL, nonce, subject/session/action binding. |
| **Transaction swapping** | Đổi số tiền/payee trong khi user đang xác thực. | Transaction digest, resource version, final recheck/locking. |
| **Cross-session swap** | Dùng step-up của user/tab A cho user/tab B. | Verified subject, issuer, client and session binding. |
| **Risk header spoofing** | Gửi X-Device-Compliant=true hoặc X-Risk=LOW. | Trusted PIP/MDM/EDR, verified provenance. |
| **Risk cache stale** | Thiết bị đã compromise nhưng cache chưa cập nhật. | Freshness policy, event-driven invalidation và fail-safe. |
| **Entitlement stale** | Token cũ chứa role đã bị revoke. | Current-state/PEP authorization và revocation SLA. |
| **SoD bypass** | User tự tạo và duyệt sau step-up. | Transaction-level SoD, actor history, independent approval. |
| **Async bypass** | Gateway challenge xong, worker xử lý message ngoài policy. | Validated authorized context và policy check ở worker. |
| **JIT standing rights** | Step-up xong admin role tồn tại mãi. | TTL, JIT scope và verified revoke/PEP DENY. |
| **Fail-open outage** | IdP/risk service down nên app ALLOW. | Define INDETERMINATE/fail-safe cho critical actions. |
| **Challenge enumeration** | Dùng mã lỗi/step-up response để dò user/role/resource. | Thông điệp và challenge flow tối thiểu, rate limiting. |
| **Audit/log tampering** | Đổi cấu hình audit sau privilege step-up. | SoD, protected logging, independent evidence. |

### Phân biệt lỗi bị tấn công và lỗi cấu hình

Một challenge thất bại không đủ kết luận tài khoản đã bị chiếm. Có thể do **passkey hỏng, browser không tương thích, user cancel hoặc IdP timeout**. Threat model cần **reason codes, provenance, nguồn tín hiệu và khả năng phục hồi** để SOC không tạo false positives nghiêm trọng.

## 33. KPI và giám sát hiệu quả của step-up decision

Tổ chức cần đo đồng thời **bảo mật, khả dụng và chi phí tương tác**. Tăng tỷ lệ challenge lên 100% có thể làm giảm trải nghiệm mà không cải thiện thực chất SoD/hard-deny.

| Chỉ số | Ý nghĩa | Cạm bẫy |
| --- | --- | --- |
| **Step-up challenge rate** | Tỷ lệ eligible sensitive requests cần step-up. | Không lấy toàn bộ traffic hoặc unauthorized requests làm mẫu số tùy tiện. |
| **Challenge completion rate** | Số challenge hoàn tất so với challenge thực sự phát hành. | Hoàn tất challenge chưa chắc authorization ALLOW. |
| **Final unauthorized action rate** | Hành động ngoài quyền có actual side effects. | Cần business commit evidence, không chỉ HTTP status. |
| **False step-up rate** | Người/phiên đủ assurance vẫn bị challenge không cần. | Cần test oracle và policy owner review. |
| **Risk false-negative detections** | Những hành động thực sự nguy hiểm bị policy bỏ qua. | Không suy bằng cách đếm incidents chưa phát hiện. |
| **Time-to-complete challenge** | Độ trễ user chờ từ STEP_UP_REQUIRED tới proof verified. | Phân biệt user think-time với network/IdP latency. |
| **Authentication assurance compliance** | Tỷ lệ action critical đạt required assurance/freshness. | ACR claims phải map đúng issuer. |
| **Phishing-resistant adoption** | Tỷ lệ tài khoản/flows đủ mạnh theo policy. | Enrollment không đồng nghĩa lần action dùng đúng factor. |
| **Challenge replay blocked** | Số attempts dùng proof hết hạn/đã consume. | Có thể do retry lỗi, cần triage. |
| **Device risk signal freshness** | Tỷ lệ request có trusted signals trong TTL. | Không nhận boolean tự khai. |
| **Unknown-signal fail-safe rate** | Số action được chặn/treo vì thiếu mandatory risk data. | Có thể phản ánh PIP outage hơn là tăng đe dọa. |
| **JML residual access** | Action còn ALLOW sau Mover/Leaver effectiveAt. | Step-up success không bù được quyền cũ chưa thu hồi. |
| **Revocation verified latency** | Từ effectiveAt đến DENY ở required PEP. | Không lấy SCIM ACK hoặc IdP logout làm verifiedAt. |
| **Policy version drift** | API nodes chạy policy/ACR mapping khác nhau. | Một node stale có thể vẫn ALLOW. |
| **Privileged grant linger** | JIT grants còn hiệu lực sau TTL/deactivation. | “Role expired” trên UI không chứng minh resource chặn. |
| **Helpdesk recovery escalations** | Những challenge hợp lệ không hoàn tất được vì mất factor. | Không tự downgrade bảo mật để giảm ticket. |

### Công thức minh họa

\[
\text{ChallengeRate} =
\frac{\text{Số eligible requests nhận STEP\_UP\_REQUIRED}}
{\text{Tổng eligible requests cần đánh giá}}
\times 100\%
\]

\[
\text{VerifiedRevocationLatency} =
t_{\text{last required PEP verified DENY}} -
t_{\text{lifecycle effectiveAt}}
\]

Nếu một PEP critical chưa được kiểm, **không có latency hoàn tất toàn scope**, chỉ có coverage đã đạt và outstanding target. Tương tự, “0 unauthorized successes” khi logs của batch export bị mất **không chứng minh an toàn**.

### Dashboard tối thiểu

Một dashboard tốt cho policy owner cần thấy:
- Policy/action/resource tier và assurance requirement.
- Tỷ lệ ALLOW, STEP_UP, DENY, APPROVAL_REQUIRED, INDETERMINATE.
- IdP challenge success/fail, timeout và factor method (không raw proof).
- Chênh lệch giữa **step-up proof success** và **final authorization outcome**.
- Risk signal provenance/freshness, missing-data rate, false-positive review.
- JML effectiveAt, rights revision, actual PEP decisions và residual grants.
- Target coverage, exception TTL, owner/escalation và SLA.
- Sự cố **challenge replay, transaction mismatch, self-approval, token confusion**.


## 34. Ma trận kiểm thử Step-up decision trong IAM

Mỗi bài test nên dùng **test subject, token/IdP thử, thiết bị giả lập và tài nguyên synthetic** trong môi trường được phép; không sao chép session, FIDO private key hoặc dữ liệu thanh toán production vào test fixture.

| ID | Tình huống | Kết quả mong đợi |
| --- | --- | --- |
| SU01 | User ACTIVE, có role phù hợp, assurance mới, risk thấp. | ALLOW action được duyệt. |
| SU02 | User ACTIVE, có role, session assurance chưa đủ. | STEP_UP_REQUIRED. |
| SU03 | User ACTIVE nhưng không có role cho action. | DENY, không bật MFA để tạo quyền. |
| SU04 | User đã Leaver, có ACR mạnh và access token còn hạn. | DENY theo lifecycle/current access. |
| SU05 | User Suspended do incident. | DENY hoặc recovery path có thẩm quyền, không tự step-up unlock. |
| SU06 | Joiner pre-provision trước effectiveAt. | DENY protected action trước activation. |
| SU07 | Joiner ACTIVE, role read-only, baseline assurance đủ cho read. | ALLOW low-risk read. |
| SU08 | Mover mất quyền Creator nhưng token cũ còn claim Creator. | PEP chặn Creator sau effectiveAt theo SLA. |
| SU09 | Mover được cấp Approver nhưng Creator chưa thu hồi, SoD cấm overlap. | Chặn activation/action cho đến khi policy gates đạt. |
| SU10 | User Approver định duyệt payment mình từng tạo. | DENY transaction-level SoD dù MFA thành công. |
| SU11 | Client gửi JWT chưa xác minh nhưng khai acr mạnh. | Token/authentication reject. |
| SU12 | API nhận ID token của OIDC làm access token. | DENY sai token purpose/audience. |
| SU13 | Token dành cho API B dùng tại API A. | DENY audience mismatch. |
| SU14 | Client gửi header X-User-Id khác verified subject. | Không đổi identity/authorization. |
| SU15 | Client gửi X-Device-Trusted=true nhưng MDM không xác minh. | Không coi device trusted. |
| SU16 | Trusted device attestation đã quá max age. | Không dùng dữ liệu stale cho decision nhạy cảm. |
| SU17 | Device compromised theo policy hard block. | DENY, không cho WebAuthn vượt hard block. |
| SU18 | Risk analytics service down và action high-risk. | INDETERMINATE/fail-safe, không ALLOW mặc định. |
| SU19 | Risk signal optional vắng mặt trong low-risk action. | Kết quả theo approved fallback, được audit. |
| SU20 | User có risk score thấp nhưng action luôn cần recent strong MFA. | STEP_UP nếu không đủ assurance. |
| SU21 | User risk cao vượt acceptable threshold dù MFA mạnh. | DENY hoặc quy trình incident, không chỉ step-up. |
| SU22 | WebAuthn authentication thành công cho user A, retry request user B. | DENY subject mismatch. |
| SU23 | Challenge được tạo tại client A, dùng với client B. | DENY client binding mismatch. |
| SU24 | Challenge session đã logout nhưng proof cũ được dùng. | DENY session invalidation. |
| SU25 | Challenge đã consume, gửi lại lần hai. | DENY replay/duplicate execution. |
| SU26 | Challenge hết TTL, proof đến muộn. | DENY/NEW_CHALLENGE. |
| SU27 | Proof có auth_time cũ hơn freshness window. | STEP_UP_REQUIRED hoặc DENY theo policy. |
| SU28 | Access token vừa refresh nhưng user chưa reauthenticate. | Không coi token iat là auth_time mới. |
| SU29 | IdP trả acr khác required assurance class. | Không ALLOW privileged action. |
| SU30 | amr=mfa nhưng factor không đáp ứng phishing-resistant policy. | STEP_UP bằng method phù hợp hoặc DENY. |
| SU31 | OIDC response sai state/issuer/nonce theo flow. | Client từ chối, không tạo trusted step-up proof. |
| SU32 | Authorization code exchange dùng PKCE verifier sai. | AS từ chối. |
| SU33 | WebAuthn proof có origin/RP ID sai hoặc chữ ký không hợp lệ. | IdP từ chối. |
| SU34 | User bấm push approval sau 20 lần spam. | Anti-fatigue/rate limit/incident controls theo policy. |
| SU35 | User mất passkey và helpdesk đề xuất SMS bypass cho admin. | Không downgrade nếu không có approved secure recovery. |
| SU36 | Transaction change: payment amount 2 triệu thành 200 triệu sau challenge. | DENY digest/version mismatch. |
| SU37 | Beneficiary thay từ A sang B sau khi user hoàn tất step-up. | Hủy proof cũ, yêu cầu xác nhận đúng nội dung. |
| SU38 | User đổi tenant/tab trong khi challenge đang mở. | Proof không tái sử dụng chéo tenant/session. |
| SU39 | Challenge ID/nonce do client tự bịa. | Server không chấp nhận. |
| SU40 | Challenge được gửi lại qua retry khi commit đã hoàn tất. | Idempotency, không tạo side effects lặp. |
| SU41 | Policy ban đầu STEP_UP nhưng entitlement bị revoke trong lúc xác thực. | Re-evaluation DENY. |
| SU42 | Payment state từ PENDING thành CANCELLED trong lúc challenge. | DENY/NEW_ACTION theo current resource state. |
| SU43 | Risk profile đổi từ moderate sang compromised trong lúc step-up. | Final decision DENY. |
| SU44 | API chỉ chặn ở web UI, direct POST bypass. | Integration test phát hiện bypass tại API. |
| SU45 | Gateway trả STEP_UP nhưng async worker vẫn tạo export. | FAIL no-side-effect; worker PEP cần sửa. |
| SU46 | Client truyền proof “mfaPassed=true” trong JSON. | Backend không tin, yêu cầu IdP proof hợp lệ. |
| SU47 | App-only service principal được đưa vào human step-up redirect. | Không dùng tương tác MFA cho robot; áp workload/JIT policy. |
| SU48 | CI/CD staging identity xin assume production role. | DENY trust/environment mismatch. |
| SU49 | Human owner Leaver nhưng batch service vẫn cần hoạt động. | Chuyển owner và revoke human controls, không xóa nhầm job hợp lệ. |
| SU50 | Người yêu cầu tự approve admin grant, đã WebAuthn mạnh. | REQUIRE_INDEPENDENT_APPROVAL/DENY SoD. |
| SU51 | JIT admin role hết TTL nhưng một resource còn ALLOW. | Residual access finding, chưa VERIFIED revoke. |
| SU52 | SCIM PATCH active=false trả 204 nhưng session cũ còn API ALLOW. | Không đánh dấu Leaver verified. |
| SU53 | API trả 503 cho negative step-up/authorization probe. | UNVERIFIED, không coi DENY. |
| SU54 | Risk device score từ nguồn không có provenance. | Đánh dấu untrusted, không dùng làm input bắt buộc. |
| SU55 | IdP/AS authentication assurance mapping khác giữa hai tenants. | Issuer/tenant-aware mapping, không so acr string trực tiếp. |
| SU56 | User đổi account giữa hai tab, local cached challenge chưa đổi. | DENY subject/client/session mismatch. |
| SU57 | IdP sign-out nhưng RP session still active trên API. | Policy check session/token hiện hành; audit gap nếu có. |
| SU58 | Low-risk action bị challenge trên mọi request do bug. | Detect false step-up/usability regression. |
| SU59 | User hoàn tất step-up, payment commit thất bại và rollback. | Audit phân biệt proof success với business failure. |
| SU60 | Policy cho DENY nhưng API vẫn commit payment. | Critical security failure, no-side-effect test FAIL. |
| SU61 | Device risk thấp nhưng có trusted security-hold signal. | Hard-deny ưu tiên risk score. |
| SU62 | Risk engine trả score không có timestamp hoặc schema version. | Missing mandatory signal/INDETERMINATE theo policy. |
| SU63 | Một policy thay đổi giữa challenge và final submit. | Đánh giá lại bằng policy version hiện hành. |
| SU64 | IdP token issued nhưng API có token assurance cũ. | API không tự cho phép; proof/token contract phải được cập nhật và xác minh. |
| SU65 | OAuth OBO token xin action rộng hơn quyền user/client. | AS/RS chặn privilege amplification. |
| SU66 | Unmanaged browser profile dùng strong passkey nhưng data export bắt buộc managed device. | DENY device restriction, không MFA override. |
| SU67 | Correlation events đầy đủ nhưng raw bearer token nằm trong SIEM logs. | Security regression FAIL và xử lý exposure. |
| SU68 | Cùng session nhận challenge cho payment A và B song song. | Proof bound per operation, không cross-use. |
| SU69 | Verified challenge state được tái sử dụng cho resource mới có cùng tên. | DENY vì stable resource ID/version khác. |
| SU70 | Approval step-up thành công, sau đó người phê duyệt bị Leaver trước grant commit. | Re-evaluate approver authority, không cấp quyền. |

### Kiểm thử theo thứ tự ưu tiên

1. **Positive path**: user đủ quyền, assurance đủ, legitimate action ALLOW.
2. **Hard-deny**: Leaver/SoD/tenant/device compromised phải DENY dù step-up success.
3. **Step-up eligibility**: thiếu assurance hoặc freshness nhưng role đúng mới CHALLENGE.
4. **Protocol security**: OAuth/OIDC issuer, state/PKCE, audience, WebAuthn origin/RP ID, proof trust.
5. **Context binding**: user/client/session/resource/transaction digest/version phải match.
6. **Re-evaluation**: role, risk và resource state đổi giữa challenge/commit.
7. **No-side-effect**: API/worker không ghi, gửi payment hoặc xuất dữ liệu khi DENY.
8. **Failure/fault**: IdP/risk PIP timeout, stale cache, token refresh race, retry.
9. **JML/revocation**: Mover quyền cũ, Leaver sessions, JIT expiry, service identity offboard.
10. **Audit/privacy**: challenge events, policy version, no secrets, target verification.

**Test oracle phải độc lập với chính PDP đang kiểm.** Bộ test không nên chỉ so response status: kiểm backend business state, logs, audit và required PEP coverage. Với một negative probe trả HTTP 503, phải dùng positive control để xác nhận endpoint hoạt động rồi mới kết luận authentication/authorization đã từ chối.


## 35. Những sai lầm phổ biến khi ra quyết định step-up

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Gắn MFA vào mọi request rồi coi hệ thống an toàn. | Gây phiền nhiễu nhưng vẫn có thể thiếu RBAC/SoD. | Chỉ challenge khi policy cần, hard-deny trước. |
| User không có quyền nhưng cho “MFA để lấy quyền”. | Authentication bị dùng sai như provisioning. | Tách entitlement approval và assurance. |
| Leaver có token còn hạn và MFA cũ nên tiếp tục ALLOW. | Quyền tồn dư sau offboarding. | Current-state PEP/revocation và target verification. |
| Thiết bị compromised được “giải cứu” bằng OTP. | Rủi ro endpoint vẫn tồn tại. | Hard-deny theo device policy, incident/recovery. |
| Chỉ kiểm assurance ở UI/browser. | Attacker gọi API trực tiếp. | Resource Server PEP bắt buộc. |
| Client tự gửi cờ mfa=true, trustedDevice=true. | Client có thể tự tuyên bố assurance. | Trusted IdP/provenance, authenticated attributes. |
| Xem ID token như access token dành cho API. | Token purpose/audience confusion. | API dùng access token đúng issuer/audience/type. |
| Nhìn token iat mới và suy người dùng vừa xác thực. | Refresh token làm giả “freshness”. | Kiểm verified auth_time của authentication event. |
| So sánh chuỗi acr tùy tiện. | Ánh xạ assurance sai giữa tenants/providers. | Issuer-bound ACR mapping và test. |
| Mặc định amr=mfa là phishing-resistant. | OTP/push có thể bị phishing. | Đánh giá factor/assurance thực tế theo policy. |
| Dùng OTP SMS làm fallback mặc định cho admin. | Recovery/downgrade là con đường tấn công. | Strong recovery, approval và risk controls. |
| WebAuthn success được coi là user đã ký payment. | Không ràng buộc beneficiary/amount. | Transaction confirmation/binding riêng. |
| Không bind challenge với subject/client/session. | Proof từ tab/user khác dùng được. | Verified binding + one-time/TTL. |
| Không bind challenge với resource version. | TOCTOU/transaction swapping. | Version/digest + final consistency check. |
| Reuse challenge nhiều lần. | Replay mở nhiều thao tác nhạy cảm. | ConsumedAt, idempotency và one-time proof. |
| Không re-evaluate sau khi challenge hoàn tất. | Quyền/nguồn risk thay đổi trong lúc user xác thực. | Current entitlement, risk, resource and SoD check trước commit. |
| Quyền chính xác ở gateway nhưng worker bypass. | Async export/payment vẫn commit khi DENY. | PEP trên mọi path, no-side-effect tests. |
| Risk service lỗi thì gán risk=0. | Fail-open cho action nhạy cảm. | Missing-signal semantics và fail-safe. |
| Chỉ dựa geolocation hoặc IP. | False positives với VPN/roaming và spoofing. | Tín hiệu đa chiều, trusted provenance, calibration. |
| Một risk score thấp override rule SoD. | User tự duyệt hoặc cross-tenant. | Hard-deny policy ưu tiên trước risk tier. |
| Bắt tất cả users step-up liên tục. | Push fatigue và friction không cần thiết. | Risk-tiered assurance, freshness window và UX phù hợp. |
| App-only bot được redirect sang form MFA. | Automation fail hoặc người dùng chia sẻ credentials. | Workload identity, JIT và human approval riêng. |
| Gắn owner service account làm initiator. | Sai attribution/SoD. | Phân biệt technical actor, business sponsor, human requester. |
| PAM JIT hết hạn nhưng role ở resource vẫn ALLOW. | Standing privileged access tồn dư. | Verified revoke/PEP negative probe. |
| IdP báo step-up success và ticket đóng ngay. | Chưa biết business action thực thi/được chặn. | Final authorization và transaction outcome audit. |
| HTTP 503 được tính DENY. | Outage bị xem là enforcement. | Positive control, reason-coded evidence và retry. |
| Không bảo vệ factor enrollment/recovery. | Attacker reset factor yếu rồi nâng quyền. | Risk-based recovery identity proofing/approval. |
| Log raw tokens/OTP để điều tra. | Log trở thành credential store. | Protected references và redaction. |
| Dùng một policy không version. | Không giải thích được vì sao decision khác giữa nodes. | Version/owner/change review và canary. |
| “Challenge completion” được dùng làm KPI đủ cho security. | Người dùng đã MFA vẫn có thể export sai tenant. | Đo final action, side effects và residual access. |

## 36. Checklist triển khai Step-up decision từ thiết kế tới nghiệm thu

1. **Mục đích xác định:** những actions nào cần step-up, những actions nào DENY hẳn và lý do nghiệp vụ.
2. **Owner policy:** IAM, Security, Data/Resource owner và Application owner chịu trách nhiệm rõ.
3. **Stable identity:** dùng issuer/tenant + immutable subject, không ghép email hoặc client header.
4. **Authentication verifier:** token type, signature/introspection, audience, issuer, expiry và sender constraints khi áp dụng.
5. **JML lifecycle:** Joiner effectiveAt, Mover revoke-before-grant/SoD, Leaver/session revocation và contractor expiry.
6. **Current authorization:** RBAC/ABAC entitlement, object/tenant/classification, status và policy version được kiểm tại PEP.
7. **Hard-deny first:** Leaver, security hold, cross-tenant, SoD và unlawful action không được vượt bằng MFA.
8. **Risk model definition:** tên signals, source, quality, version, thresholds, owners và cách xử lý unknown.
9. **Risk provenance:** device/EDR/MDM, network, account risk có trusted issuer và freshness.
10. **Action tiering:** low/medium/high/critical theo business impact, không chỉ theo IP/device.
11. **Assurance classes:** ánh xạ AAL/ACR/AMR theo IdP contract, không tự so chuỗi.
12. **Authentication freshness:** auth_time và window cho từng action; token iat không thay thế.
13. **Phishing-resistant MFA:** yêu cầu khi risk/policy phù hợp, support enrollment/recovery an toàn.
14. **OIDC/OAuth integration:** code+PKCE, secure redirect/state, issuer validation, API token đúng audience.
15. **SAML integration:** AuthnContext và SP session binding nếu ứng dụng dùng SAML.
16. **Challenge state:** challengeId TTL, nonce, max attempts, consumedAt, required method/assurance.
17. **Challenge binding:** subject, client, session, action, resource, tenant, transaction version/digest.
18. **Transaction confirmation:** hiển thị và kiểm amount/payee/classification khi policy cần, không nhầm WebAuthn với ký payload.
19. **Re-evaluation:** current risk/role/SoD/resource sau proof và ngay trước commit.
20. **No unauthorized effects:** deny/challenge không tạo payment, export file hoặc queue job có tác động.
21. **Concurrency/idempotency:** xử lý hai tab, double submit, timeout after commit và replay.
22. **JIT/approval:** human independent approval tách khỏi MFA, role activation có TTL và scope.
23. **Workload identity:** app-only/batch/CI/CD có trust/attestation riêng, không ép human step-up cho robot.
24. **Session management:** logout, token refresh, session binding và short-lived proof được thiết kế rõ.
25. **PDP/PIP outages:** xử lý INDETERMINATE và fail-safe cho critical, bounded caches có risk acceptance.
26. **Monitoring:** risk signal lag, challenge failures, factor downgrade, abuse patterns và policy drift.
27. **Privacy:** không log OTP, session cookies, raw tokens, passkey secret, PII không cần.
28. **Structured audit:** request/correlation, subject, action, resource, policy/version, reasonCode, assurance proofRef, final outcome.
29. **Security testing:** positive + negative probes trên API, async, export, JIT và SSO/IdP paths.
30. **Threat model:** phishing, push fatigue, challenge replay, transaction swap, factor recovery, header spoofing, SSRF/token leaks khi áp dụng.
31. **False positive review:** đánh giá impact với VPN/remote users, accessibility và helpdesk pathways.
32. **Canary/shadow rollout:** xem risk outcomes, detect unexpected hard-deny, bảo đảm không fail-open.
33. **Recovery governance:** identity proofing/approval/audit cho reset factors, không self-service downgrade privileged.
34. **Revocation verification:** quyền sau Mover/Leaver hoặc JIT expiry phải DENY tại required PEP.
35. **Incident readiness:** compromised authenticator/device, leaked tokens, IdP outage và account takeover có playbook.
36. **Evidence coverage:** chưa có chứng cứ ở target critical thì báo PARTIAL/UNVERIFIED, không CLAIM VERIFIED.
37. **Change governance:** thresholds, signal version, required ACR, policy evaluation order thay đổi đều có review/test.
38. **Thước đo cuối:** user hợp lệ thực hiện được action theo policy, và user/transaction ngoài quyền thực sự bị chặn.

**Điều kiện hoàn tất:** một quyết định Step-up tốt phải dẫn tới **trải nghiệm xác thực phù hợp** và **quyết định ủy quyền cuối dựa trên đúng danh tính, quyền và dữ liệu hiện hành**, không chỉ hiện một màn hình MFA.


## 37. Câu hỏi tự kiểm tra

**Câu 1. Step-up decision là gì, và khác authorization như thế nào?**

**Trả lời:** Step-up quyết định **có cần tăng cường hoặc làm mới bằng chứng xác thực** cho một action theo risk/context không. Authorization quyết định user/client **có quyền** làm action trên resource hay không. MFA thành công không tự cấp role.

**Câu 2. Khi nào policy nên trả DENY thay vì STEP_UP_REQUIRED?**

**Trả lời:** Khi có hard-deny như Leaver, Suspended, không có entitlement, cross-tenant, SoD self-approval hoặc device compromised bị cấm. Step-up phù hợp khi user **đã có quyền** nhưng assurance/freshness chưa đủ và challenge có thể làm đáp ứng yêu cầu.

**Câu 3. Tại sao một access token mới phát không nhất thiết chứng minh user mới MFA?**

**Trả lời:** Token có thể được **refresh** từ refresh token mà không có authentication event mới. Phải dùng **auth_time/assurance evidence** đáng tin theo IdP/AS contract, không dùng access token iat thay thế.

**Câu 4. acr, amr và auth_time biểu thị điều gì?**

**Trả lời:** acr biểu thị authentication context class do issuer công bố; amr mô tả methods; auth_time là thời điểm người dùng xác thực theo protocol. Giá trị cần được **xác minh cryptographically và ánh xạ theo issuer**, không mặc nhiên amr=mfa là chống phishing.

**Câu 5. Vì sao không dùng tên acr từ IdP A so chuỗi với acr của IdP B?**

**Trả lời:** Hai IdP có thể dùng vocabulary và assurance semantics khác nhau. Identity owner cần **mapping được duyệt và kiểm thử**, không so chữ hay mức số do phỏng đoán.

**Câu 6. WebAuthn có tự động bảo đảm người dùng đã xác nhận đúng số tiền của payment không?**

**Trả lời:** Không. WebAuthn cung cấp authentication/proof đối với RP theo protocol. Muốn xác nhận **số tiền, người thụ hưởng và transaction version**, cần UX và challenge/confirmation binding được thiết kế riêng.

**Câu 7. Vì sao hard-deny phải được xét trước challenge?**

**Trả lời:** Nếu user không có quyền nhưng API lại hiển thị MFA, hệ thống vừa tạo friction không cần thiết vừa có nguy cơ logic sau MFA vô tình cấp quyền. Hard-deny không được dùng step-up làm bypass.

**Câu 8. Một user đã ACTIVE, có quyền payment.approve và dùng passkey, tại sao vẫn có thể bị DENY?**

**Trả lời:** Payment có thể thuộc tenant khác, đang bị cancel, vượt limit, user từng tạo payment hoặc device bị hard-block. Assurance cao **không thay business rules, RBAC/ABAC hoặc SoD**.

**Câu 9. Nếu risk service outage, có thể ALLOW theo mặc định để không gián đoạn không?**

**Trả lời:** Không đối với action nhạy cảm cần mandatory risk checks. Dùng **INDETERMINATE/fail-safe**, hoặc bounded fallback đã được risk owner duyệt cho các trường hợp cụ thể; phải log và monitor.

**Câu 10. Vì sao nhiều lần step-up trong ngày có thể làm giảm mức an toàn?**

**Trả lời:** Challenge liên tục gây mệt mỏi, thúc đẩy chấp thuận push theo thói quen hoặc yêu cầu fallback yếu. Chính sách cần xác định **khi nào assurance hiện tại còn đủ**, tránh friction không mang lại lợi ích.

**Câu 11. ChallengeId nên ràng buộc những gì?**

**Trả lời:** Verified subject, client, session, action, resource/tenant, transaction version hoặc digest, required assurance, TTL, consumedAt và policy/risk context. Các bindings ngăn replay, account switching và transaction swapping.

**Câu 12. Vì sao phải đánh giá lại policy sau khi hoàn thành MFA?**

**Trả lời:** Trong lúc challenge, user có thể Mover/Leaver, risk/device thay đổi hoặc transaction bị sửa. Final authorization phải kiểm **current rights, SoD, resource state, risk và proof** ngay trước commit.

**Câu 13. Một nhân viên đã chuyển sang Approver và step-up thành công. Có thể tự duyệt payment đã tạo khi còn Creator không?**

**Trả lời:** Không nếu policy cấm self-approval. SoD transaction-level dựa vào **lịch sử createdBy/lastMaterialEditor** của payment, không bị xóa bởi role mới hoặc MFA mới.

**Câu 14. SCIM active=false có đủ để nói phiên ứng dụng cũ không còn dùng được không?**

**Trả lời:** Không. JWT/SSO session/PAT/local ACL có vòng đời riêng. Cần **effective access verification** tại Resource Server và các target bắt buộc, không chỉ SCIM ACK.

**Câu 15. Với client credentials của batch job, có nên redirect sang WebAuthn để step-up không?**

**Trả lời:** Không như một người dùng tương tác. Workload dùng **managed/federated identity, mTLS, credential ngắn hạn, trust chặt và least privilege**. Nếu cần approval của người, người phê duyệt step-up qua workflow riêng.

**Câu 16. Một risk score rất thấp có thể bỏ qua policy luôn yêu cầu phishing-resistant MFA cho admin grant không?**

**Trả lời:** Không. **Action sensitivity và mandatory assurance** là các điều kiện policy độc lập với risk score. Score hỗ trợ quyết định chứ không được override yêu cầu bắt buộc.

**Câu 17. Khi user thay beneficiary sau step-up nhưng trước commit, hệ thống nên làm gì?**

**Trả lời:** Kiểm **transaction snapshot/version/digest**; khi thay nội dung trọng yếu, từ chối dùng proof cũ và yêu cầu xác nhận lại theo policy. Dùng locking/idempotency trước khi ghi.

**Câu 18. API trả 503 cho một negative step-up test. Được tính là DENY thành công chưa?**

**Trả lời:** Chưa. 503 biểu thị lỗi khả dụng; cần positive control và bằng chứng policy/PEP DENY có no side effects khi API hoạt động. Kết quả nên là **UNVERIFIED**.

**Câu 19. Vì sao bước MFA thành công không chứng minh thao tác payment đã hoàn thành?**

**Trả lời:** Authentication event tách biệt với **authorization decision và business commit**. Payment có thể bị DENY bởi SoD, mất quyền, sai tenant hoặc rollback. Audit phải ghi riêng proof/result/transaction.

**Câu 20. Điều gì cần kiểm khi nhân viên mất security key/passkey?**

**Trả lời:** Quy trình **identity proofing/recovery, factor enrollment, device/session revocation, helpdesk approval và audit** phải đủ mạnh, đặc biệt với privileged account; tránh SMS/password yếu làm đường downgrade.

**Câu 21. JIT role được cấp 20 phút, user đã hoàn tất step-up. Khi hết hạn đã an toàn chưa?**

**Trả lời:** Phải kiểm **role/credential/session/token còn hiệu lực ở target** và negative probe tại required PEP. Cờ hết TTL trong UI không tự chứng minh quyền thực tế đã bị từ chối.

**Câu 22. Vì sao không nên tin X-Device-Compliant=true từ client?**

**Trả lời:** Header có thể bị giả mạo. Device posture phải đến từ **attestation/MDM/EDR nguồn tin cậy** với metadata về issuer, freshness và policy mapping.

**Câu 23. Khi nào cần independent approval bên cạnh step-up?**

**Trả lời:** Khi business/SoD/risk policy yêu cầu quyết định của **một người có thẩm quyền khác**, ví dụ cấp admin, thanh toán giá trị lớn hoặc sửa rule production. Xác thực mạnh hơn không thay việc phê duyệt.

**Câu 24. Một step-up challenge hợp lệ của tenant VN có thể dùng cho tenant SG không?**

**Trả lời:** Không nếu challenge đã được ràng buộc tenant/resource và user không có quyền tenant SG. Final PEP phải kiểm **tenant/resource authorization** độc lập với assurance.

**Câu 25. KPI nào giúp phân biệt hệ thống step-up hoạt động thực chất và hệ thống chỉ hiển thị nhiều MFA?**

**Trả lời:** Ngoài challenge rate/completion, cần đo **final unauthorized actions, no-side-effect, false step-up, assurance compliance, risk signal freshness, JML residual access, verified revoke latency và required-target coverage**.

## 38. Tham khảo tiêu chuẩn và kiểm chứng với hệ thống thực

Các tài liệu sau là **điểm bắt đầu để đối chiếu với platform đang dùng**, không phải tuyên bố mọi sản phẩm đều hỗ trợ đầy đủ mọi chức năng:

| Chủ đề | Tài liệu/hệ sinh thái để tra cứu | Điều cần xác minh |
| --- | --- | --- |
| **Digital identity assurance** | NIST SP 800-63 series (đặc biệt hướng dẫn Authentication và AAL hiện hành). | Assurance, reauthentication, authenticator lifecycle và recovery. |
| **OIDC authentication context** | OpenID Connect Core. | acr, amr, auth_time, max_age, prompt, issuer/client response verification. |
| **OAuth step-up challenge** | RFC 9470 (OAuth 2.0 Step Up Authentication Challenge). | Resource Server challenge semantics, required auth context/age, AS/client support. |
| **OAuth access tokens** | RFC 6749, RFC 6750 và cập nhật an ninh OAuth Security BCP. | AS/RS token type, issuer, audience, grants, expired/revoked access. |
| **PKCE** | RFC 7636. | Authorization code flow, state/redirect protections, public client. |
| **JWT security** | RFC 7519, RFC 8725 và JWT access token profile RFC 9068 khi áp dụng. | Signature, allowed algorithms, issuer/audience/time, token type. |
| **WebAuthn/FIDO** | W3C Web Authentication specification và FIDO Alliance guidance. | RP ID/origin binding, UV/UP, attestation policies, phishing resistance, registration/recovery. |
| **SCIM** | RFC 7643, RFC 7644. | User/group provisioning, target readback; không coi SCIM là global token revoke. |
| **ABAC policy** | NIST SP 800-162 và policy engine documentation. | Trust attributes, PIP/PDP/PEP, action/resource attributes và current state. |
| **Access control, audit và response** | NIST SP 800-53 relevant controls và tổ chức governance policies. | Risk ownership, SoD, audit evidence, change approval, exceptions. |
| **Privileged access** | Tài liệu IAM/PAM/JIT của nhà cung cấp và quy trình nội bộ. | Privileged session assurance, activation TTL, approval và verified revoke. |

### Những điều nhất thiết phải kiểm với nhà cung cấp

- IdP có hỗ trợ **phishing-resistant step-up**, auth_time, ACR mapping và chính sách reauthentication cho đúng client hay không.
- Resource Server có thể kiểm **assurance evidence trong access token hoặc bước token exchange/step-up proof** nào, theo hợp đồng không?
- Browser/native/legacy client có tuân **Authorization Code + PKCE**, redirect/state/nonce và token storage phù hợp không?
- Step-up challenge có thể ràng buộc **specific operation/resource/transaction version** không hay chỉ reauthenticate cả session?
- Device/risk signal có nguồn đáng tin và TTL bao nhiêu; policy xử lý unknown ra sao?
- JML events từ HRIS/IGA/IdP/SCIM đến API có SLA và **effective DENY evidence** không?
- Các async workers, batch exports, local PATs và legacy app có bỏ qua PEP hoặc challenge không?
- Cơ chế **factor recovery/locked-out user** có tương xứng risk và không tạo downgrade không?

Không mặc định bất cứ giá trị **risk tier, AAL, TTL, max_age, transaction digest, status code** nào là chung cho mọi ứng dụng. Các ví dụ trong bài chỉ mang tính học tập; khi triển khai cần thống nhất **policy owner, resource owner, IdP/AS/RS contract và kết quả kiểm thử thực tế**.

---

**Ghi nhớ:** **Step-up decision là cổng tăng cường bảo đảm xác thực cho một hành động đủ điều kiện, không phải công cụ tạo quyền hoặc vượt hard-deny.** Một thiết kế đúng xét **authentication validity → current authorization/JML/SoD → risk signals và assurance/freshness**, rồi trả **ALLOW, STEP_UP_REQUIRED, DENY, REQUIRE_APPROVAL hoặc INDETERMINATE** theo chính sách. Sau khi user hoàn tất WebAuthn/MFA phù hợp, API vẫn phải **xác minh proof, ràng buộc đúng user/client/session/giao dịch, đánh giá lại entitlement/resource/risk và chặn side effects ngoài quyền**. Kết hợp **IdP/SSO/OIDC, SCIM, RBAC/ABAC, PAM/JIT, service identity, audit và verified deprovisioning** để người có quyền hợp lệ truy cập thuận tiện, còn **quyền tồn dư khi Mover/Leaver và những hành động bị cấm thực sự bị từ chối tại PEP**.
