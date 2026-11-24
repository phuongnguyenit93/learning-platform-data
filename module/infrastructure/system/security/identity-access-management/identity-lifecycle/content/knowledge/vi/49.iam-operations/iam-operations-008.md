# Xử lý access khẩn cấp trong IAM: break-glass, JIT/PAM và thu hồi có kiểm chứng

## 1. Vì sao access khẩn cấp cần một runbook riêng?

**Access khẩn cấp (emergency access)** là cơ chế cho phép người hoặc workload được ủy quyền thực hiện **một hành động cần thiết, trong phạm vi và thời gian giới hạn**, khi luồng truy cập thông thường không đáp ứng một sự kiện khẩn như sự cố sản xuất, mất khả dụng Identity Provider (IdP), khóa nhầm tài khoản quản trị hoặc cần chặn truy cập của danh tính bị xâm nhập.

Trong chương **IAM operations** của module **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**, access khẩn cấp là một vấn đề của **vòng đời danh tính Joiner–Mover–Leaver (JML)** và **quản trị quyền truy cập**, không chỉ là cách mở một tài khoản admin. Nó cần phối hợp **IdP, SSO, SCIM, RBAC/ABAC, Privileged Access Management (PAM), danh tính dịch vụ, kiểm toán** và việc loại bỏ **quyền truy cập tồn dư** sau khi tình huống kết thúc.

Một quy trình vận hành đúng phải dung hòa hai yêu cầu có thể xung đột:

1. **Availability và incident response:** người có trách nhiệm vẫn có khả năng khôi phục dịch vụ, cô lập tài khoản bị chiếm, thu hồi credential hoặc thực thi yêu cầu Leaver ngay cả khi một thành phần IAM bị lỗi.
2. **Security và accountability:** đường khẩn cấp không trở thành cơ chế vượt MFA, phê duyệt, phân tách nhiệm vụ (SoD), giám sát hay giới hạn quyền thường ngày.

Access khẩn cấp có thể là **quyền tạm nâng cấp (just-in-time/JIT)** qua PAM, **tài khoản break-glass được quản lý sẵn**, hoặc **đường quản trị dự phòng** đã được thiết kế và kiểm thử. Không mặc định mọi hệ thống đều có sẵn các lựa chọn này; sử dụng phương án nào phải dựa trên kiến trúc và quy trình của tổ chức.

**Mục tiêu học tập:** sau bài này, người đọc có thể phân loại nhu cầu emergency access, đánh giá có thật sự cần thiết không, lựa chọn đường khẩn cấp phù hợp, xác minh requester, kiểm soát phê duyệt/phạm vi/thời hạn, theo dõi hoạt động, thu hồi quyền/credential/phiên và đóng hồ sơ bằng bằng chứng.

> **Phạm vi:** Đây là runbook tham chiếu, không phải chỉ dẫn để tạo hoặc sử dụng tài khoản đặc quyền trái phép. Các ngưỡng SLA, thời hạn, role, số người duyệt, hình thức MFA và quyền điều phối phải căn cứ chính sách, pháp lý và nền tảng cụ thể. Không được tự ý tắt bảo mật toàn hệ thống để giải quyết một yêu cầu khẩn.

## 2. Phân biệt các loại access khẩn cấp

| Cơ chế | Khi nào phù hợp | Đặc điểm kiểm soát |
|---|---|---|
| **JIT elevation** | Người đã có tài khoản hợp lệ cần quyền cao trong khoảng ngắn | Phê duyệt theo request, entitlement đúng phạm vi, TTL, audit và tự thu hồi theo khả năng nền tảng |
| **PAM privileged session** | Cần thao tác quản trị nhạy cảm trên host, database, cloud hoặc network | Vault/credential checkout, session brokering/recording nếu hỗ trợ, scope và hậu kiểm |
| **Break-glass account** | Không thể dùng đường quản trị thông thường do IdP/PAM/policy outage hoặc bị khóa | Được chuẩn bị sẵn, quản lý đặc biệt, cảnh báo mọi lần sử dụng, bảo vệ credential và kiểm thử định kỳ |
| **Emergency role/access package** | Incident đã được xác nhận, cần một role sẵn có nhưng không duy trì thường trực | Grant có phê duyệt, owner, thời hạn, điều kiện hoạt động và xác minh thu hồi |
| **Local emergency admin** | Ứng dụng/thiết bị có đường quản trị cục bộ độc lập theo thiết kế | Chỉ dùng nếu được phê duyệt; kiểm soát local credential, log và thời điểm thu hồi |
| **Quyền thao tác tại đích khi IdP lỗi** | Leaver/compromise cần thu hồi ngay mà connector trung tâm không hoạt động | Chủ ứng dụng/PAM hành động theo quyền đã ủy quyền; đồng bộ, đối soát sau khi phục hồi |
| **Workload recovery identity** | Automation trọng yếu cần khôi phục khi identity dependency bị hỏng | Service owner, trust, secret/credential ngắn hạn, dependency và quyền tối thiểu |

### 2.1. Những trường hợp không phải lý do hợp lệ

- Muốn tránh quy trình access request thường vì thấy chậm.
- Người dùng quên mật khẩu nhưng không có tác động khẩn cấp được xác nhận.
- Muốn giữ admin thường trực để “đề phòng” thay vì JIT hoặc quy trình đã kiểm thử.
- Dùng account của đồng nghiệp hoặc chia sẻ password qua chat vì requester chưa có quyền.
- Vượt qua security hold, Leaver hoặc lệnh đình chỉ do nguồn chủ quản có thẩm quyền phát ra.
- Tắt MFA, bỏ xác minh chữ ký SSO hoặc vô hiệu audit chỉ để mở đường vào một ứng dụng.

**Quy tắc:** yêu cầu gắn chữ “khẩn cấp” vẫn cần **mục đích, người chịu trách nhiệm, hệ thống mục tiêu và tiêu chí kết thúc**. Tính khẩn cấp điều chỉnh thứ tự ưu tiên xử lý, không tự động trao quyền không giới hạn.

## 3. Kiến trúc IAM và vị trí các đường access khẩn cấp

~~~mermaid
flowchart LR
    HR[HRIS / Contractor source] --> JML[Điều phối JML]
    JML --> POLICY[RBAC / ABAC / SoD / Approval]
    POLICY --> IDP[IdP / Directory]
    IDP -->|SSO: OIDC / SAML| APP[Ứng dụng / Cloud]
    JML -->|SCIM / API| APP
    REQUEST[Incident / Request] --> APPROVAL[Incident Commander / Owner / Security]
    APPROVAL --> PAM[PAM / JIT]
    PAM --> APP
    VAULT[Kho secret / Break-glass control] --> EMERG[Emergency access path]
    EMERG --> APP
    PAM --> AUDIT[Audit / SIEM]
    EMERG --> AUDIT
    IDP --> AUDIT
    APP --> AUDIT
    AUDIT --> REVIEW[Reconcile và hậu kiểm]
    REVIEW --> POLICY
~~~

**Điểm quan trọng:** IdP thường quản lý authentication và group, còn ứng dụng quản lý session, authorization và nhiều quyền cục bộ. **SSO login thành công không chứng minh role khẩn cấp đã được gán đúng**; API cấp role thành công cũng không chứng minh session cũ bị thu hồi khi quyền hết hạn. Phải đối soát **actual/effective access** ở ứng dụng.

### 3.1. Mặt phẳng authentication và provisioning có thể độc lập

Khi IdP gặp sự cố:

- **SSO** có thể không tạo được phiên đăng nhập mới, trong khi app vẫn chấp nhận session/token cũ.
- **SCIM/API provisioning** có thể vẫn hoạt động hoặc thất bại riêng; cần kiểm tra trạng thái từng connector.
- **Local access** hoặc break-glass có thể còn, nhưng chỉ được sử dụng nếu đã quản lý và kiểm thử.
- Một **Leaver** vẫn có thể sở hữu API key, SSH key, session ứng dụng hoặc delegated access dù account IdP disabled.

Do đó, emergency access phải đi cùng quy trình thu hồi và reconcile, tránh mở thêm đường truy cập mới mà hệ thống IAM không biết cách đóng.

## 4. Nguyên tắc thiết kế trước khi có sự cố

### 4.1. Least privilege và giới hạn theo ngữ cảnh

Mỗi emergency grant cần xác định:

1. **Who:** chủ thể được xác minh theo ID bất biến, trạng thái JML còn hợp lệ.
2. **Why:** incident/request cụ thể, tác động và hành động cần làm.
3. **What:** role, hành động, tài nguyên, dữ liệu và môi trường cần truy cập.
4. **Where:** tenant, project, application, host, region hoặc namespace.
5. **When:** thời điểm bắt đầu, thời hạn kết thúc, điều kiện gia hạn và thu hồi.
6. **How:** đường PAM/JIT, tài khoản quản trị dự phòng hoặc workflow đã duyệt, kèm authentication/MFA và logging.
7. **Who approves/reviews:** owner dữ liệu, Incident Commander, Security/PAM và người hậu kiểm phù hợp.

**RBAC** nên có emergency role hẹp cho từng tác vụ (ví dụ chỉ khởi động lại dịch vụ hoặc đọc log). **ABAC** có thể giới hạn tài nguyên, thiết bị tin cậy, phiên sự cố, môi trường và thời gian nếu hệ thống hỗ trợ; tránh dùng điều kiện quá rộng làm grant toàn tenant.

### 4.2. Segregation of Duties (SoD)

Người yêu cầu không nên tự phê duyệt quyền đặc quyền của chính mình khi policy yêu cầu phê duyệt độc lập. Với tình huống người duyệt thông thường không thể truy cập do outage, tổ chức cần **quy trình thay thế đã duyệt trước**: người trực on-call khác, Incident Commander, Security duty officer hoặc cơ chế emergency activation có cảnh báo và hậu kiểm bắt buộc.

**Không xây quy trình phụ thuộc duy nhất vào hệ thống đang lỗi.** Nếu quyền khẩn cấp được dùng để khôi phục IdP, việc kích hoạt nó không được đòi hỏi phải đăng nhập thành công vào chính IdP đó; tuy nhiên đường thay thế vẫn phải có xác minh, bảo vệ credential, kiểm soát và audit phù hợp.

### 4.3. Break-glass không phải tài khoản “không ai quản”

Một break-glass hợp lệ thường không gắn với người dùng HR cụ thể, nhưng phải có **Security/PAM owner**, inventory, phương thức lưu/khôi phục credential, quy trình kiểm tra định kỳ và giám sát độc lập. Không tự đánh dấu hoặc xóa tài khoản này là **orphan account** chỉ vì không có HR row; ngược lại, account tự nhận là break-glass nhưng thiếu owner, policy và cảnh báo là ngoại lệ cần xử lý.

### 4.4. Fail-safe và khả dụng có điều kiện

Khi hệ thống không xác minh được identity/policy, **không mặc nhiên cho phép quyền rộng**. Đường khẩn cấp phải được thiết kế trước như một ngoại lệ có giới hạn và có thể kiểm chứng; tùy rủi ro, tài nguyên nhạy cảm có thể phải từ chối truy cập cho đến khi nguồn tin cậy được khôi phục.

## 5. Danh mục kiểm soát emergency access cần chuẩn bị sẵn

| Thành phần | Cần có trước incident | Rủi ro khi bỏ sót |
|---|---|---|
| **Inventory break-glass/JIT roles** | Account/role, owner, mục đích, target, scope, expiry | Không biết tồn tại quyền nào hoặc ai được sử dụng |
| **Quy trình kích hoạt** | Trigger, mức độ, người quyết định, kênh liên lạc dự phòng | Yêu cầu khẩn bị chặn hoặc được mở sai thẩm quyền |
| **Identity proofing** | Cách xác minh requester khi SSO/mail không sẵn sàng | Kẻ mạo danh Help Desk lấy quyền admin |
| **Bảo vệ credential** | Vault/PAM, phương án lưu khẩn, nguyên tắc dual control khi áp dụng | Password/secret bị sao chép hoặc dùng chung |
| **Authentication/MFA phù hợp** | Phương án không phụ thuộc duy nhất vào thành phần có thể lỗi | Bị khóa hoàn toàn hoặc bị ép phải bypass bảo mật |
| **Tài khoản kiểm thử** | Kiểm thử đường khẩn cấp an toàn và cảnh báo | Lúc khẩn cấp mới phát hiện account không hoạt động |
| **Hạn quyền** | TTL, scope, role hẹp, giới hạn tài nguyên, cơ chế revoke | Access tồn dư nhiều ngày hoặc vĩnh viễn |
| **Audit độc lập** | Log, SIEM alert, session recording nếu hỗ trợ, người hậu kiểm | Không biết ai đã làm gì |
| **Kế hoạch dependency/failover** | DNS/IdP/PKI/PAM/vault/backup contact phù hợp | Tài khoản khẩn cấp cũng bị phụ thuộc outage |
| **Reconciliation và closing** | Checklist gỡ quyền, session/token, key rotation, evidence | Incident đã đóng nhưng admin còn hoạt động |

**Kiểm thử định kỳ:** thực hiện bằng kế hoạch được phê duyệt trong môi trường hoặc phạm vi an toàn, kiểm tra cả khả năng truy cập và khả năng thu hồi/cảnh báo. Không để một bài kiểm thử tạo credential admin mới tồn tại lâu dài.

## 6. Vai trò, trách nhiệm và quyền ra quyết định

| Vai trò | Trách nhiệm |
|---|---|
| **Requester / Responder** | Nêu incident, nhiệm vụ cụ thể, target, khoảng thời gian; chỉ dùng quyền trong scope |
| **Incident Commander (IC)** | Xác nhận mức khẩn cấp, ưu tiên, điều phối và quyết định kích hoạt đường sự cố theo quy định |
| **IAM Operations** | Kiểm tra identity/JML, role/SCIM/IdP, thực hiện provisioning/thu hồi, reconcile |
| **PAM / Privileged Access Owner** | Quản lý JIT, vault, break-glass, credential checkout, session và thu hồi |
| **Application/Data Owner** | Xác nhận quyền nào cần thiết, tác động và kiểm chứng nghiệp vụ |
| **SOC / Security** | Đánh giá rủi ro, compromise, duyệt/giám sát exception, bảo vệ bằng chứng |
| **HR / Sponsor** | Xác nhận người, trạng thái Active/Suspended/Terminated, contract expiry và thay đổi vai trò |
| **Platform / SRE** | Thực hiện khôi phục dịch vụ, tính sẵn sàng và đánh giá ảnh hưởng production |
| **Audit / Compliance** | Rà soát độc lập hành động khẩn, thời gian tồn quyền và exception |

**RACI phải gắn với hành động cụ thể** như kích hoạt, dùng credential, tăng quyền, gia hạn, thu hồi và xác nhận kết thúc. Không đủ chỉ liệt kê người “được thông báo”.

## 7. SOP-EA01 — Tiếp nhận và xác minh nhu cầu khẩn cấp

**Trigger:** incident/service outage, tài khoản admin bị khóa, cần khắc phục sự cố bảo mật đang diễn ra hoặc không thể thực hiện một lệnh chặn truy cập Leaver qua đường thông thường.

**Đầu vào bắt buộc:** `incident_id`, `request_id`, `requester_subject_id`, `target_system`, hành động dự kiến, lý do, severity, thời điểm bắt đầu, thời hạn dự kiến và người phê duyệt/owner.

### 7.1. Quy trình tiếp nhận

1. **Xác nhận sự kiện:** có incident đang hoạt động hoặc chứng cứ về tác động khẩn được ghi nhận không? Nếu chỉ là nhu cầu truy cập thông thường, dùng workflow access request chuẩn.
2. **Xác nhận requester:** sử dụng ID danh tính bền vững, nguồn nhân sự/sponsor và phương thức identity proofing theo chính sách. Không dựa riêng vào email từ requester hoặc danh tính hiển thị ở chat.
3. **Kiểm tra JML:** người yêu cầu có đang Active và được phép đảm nhiệm vai trò này không? Có security hold, Suspended, Leaver, contractor expiry hoặc chuyển vị trí Mover gần đây không?
4. **Xác nhận target và mục đích:** quyền tối thiểu có thể giải quyết vấn đề là gì? Chỉ cần xem log, restart service hay thực sự phải sửa policy?
5. **Xác định tuyến phê duyệt:** owner ứng dụng/dữ liệu, IC, Security/PAM; ghi rõ trường hợp on-call thay thế khi phê duyệt thông thường không khả dụng.
6. **Ước lượng TTL và điều kiện kết thúc:** ngắn nhất đủ để thao tác, không mặc định “cho tới khi báo xong”; có cơ chế expiry enforcement hoặc kiểm soát bù trừ nếu target không hỗ trợ.
7. **Xác định biện pháp bảo mật:** MFA/phương thức xác thực phù hợp, thiết bị, mạng, session monitoring, logging, cảnh báo.
8. **Ra quyết định:** `APPROVE_SCOPED`, `REQUEST_MORE_EVIDENCE`, `DENY` hoặc `ESCALATE_SECURITY`. Không tự cấp vì requester dùng từ “urgent”.

### 7.2. Cây quyết định

~~~mermaid
flowchart TD
    A[Nhận yêu cầu emergency access] --> B{Incident / tình huống khẩn hợp lệ?}
    B -->|Không| C[Access request thông thường]
    B -->|Có| D{Identity & lifecycle xác minh được?}
    D -->|Không| E[Block / escalate: không cấp đặc quyền]
    D -->|Có| F{Có role JIT/PAM phù hợp?}
    F -->|Có| G[Approval + scope + TTL + MFA]
    F -->|Không| H{Break-glass path đã duyệt sẵn?}
    H -->|Không| I[IC/Security chọn biện pháp thay thế hợp lệ]
    H -->|Có| J[Kích hoạt theo dual control / owner]
    G --> K[Audit + monitoring]
    J --> K
    K --> L[Thực thi trong scope]
    L --> M[Revoke / expire + verify]
    M --> N[Hậu kiểm & đóng incident access]
~~~

### 7.3. Ví dụ hồ sơ yêu cầu hợp lệ

| Trường | Giá trị giả lập |
|---|---|
| Incident | `INC-2026-081`: hệ thống thanh toán không xử lý queue |
| Requester | `person-1042`, thuộc nhóm on-call có thẩm quyền |
| Target | Một namespace của dịch vụ thanh toán |
| Action | Restart đúng deployment và đọc log lỗi |
| Scope | `payment-namespace-ops`, không có quyền sửa IAM |
| TTL | Ví dụ 30 phút, có thể đề nghị gia hạn theo policy |
| Approval | IC và application owner theo chính sách |
| Control | MFA phù hợp, PAM session log và cảnh báo |
| Exit | Queue hoạt động, quyền được thu hồi, kiểm chứng và audit |

Thời hạn 30 phút chỉ là **giá trị minh họa**. Nền tảng có thể quy định thời hạn khác; quan trọng là TTL có cơ chế cưỡng chế và chỉ gia hạn khi có căn cứ.

## 8. SOP-EA02 — Kích hoạt quyền JIT/PAM

**Dùng khi:** đường IAM thông thường hoạt động và có thể cấp quyền thời gian ngắn tới target cần thiết.

### 8.1. Các bước

1. **Tính desired emergency entitlement** từ yêu cầu được duyệt: hành động, resource, namespace/tenant, thuộc tính ABAC, thời gian.
2. Kiểm tra requester không nằm trong nhóm **Terminated, Suspended hoặc security hold**. Với Mover, chỉ cấp theo vai trò hiện tại; không dựa vào group cũ.
3. IAM/PAM thực hiện grant qua workflow có ID, approval reference, expiry; tránh gán standing global admin khi role hẹp đáp ứng được.
4. Yêu cầu phương thức xác thực phù hợp và dùng endpoint/thiết bị tin cậy theo chính sách.
5. Nếu nền tảng hỗ trợ, ràng buộc session và hành động với `incident_id`, khởi tạo log/session recording; thông báo SOC/owner.
6. Xác minh **quyền hiệu lực tại target** trước khi thao tác. Không dùng một phản hồi API 200 để chứng minh role đúng.
7. Theo dõi TTL và status trong suốt phiên; requester chỉ thực hiện hành động đã phê duyệt, không tạo credential/role mới ngoài scope.
8. Khi kết thúc hoặc hết hạn, bắt đầu quy trình revoke và verification ở SOP-EA06, kể cả khi ticket sự cố nghiệp vụ chưa đóng.

### 8.2. Ví dụ: grant tạm theo tài nguyên

~~~yaml
request_id: EMG-ACCESS-EXAMPLE-082
incident_ref: INC-2026-081
requester_subject_id: person-1042
target_system: k8s-payments
resource_scope: namespace/payments
desired_role: deployment-operator
allowed_actions:
  - read-application-logs
  - restart-deployment
prohibited_actions:
  - change-cluster-admin
  - view-secrets
  - modify-identity-policy
approval_refs:
  - ic-approval-082
  - application-owner-approval-082
authentication_policy: approved-strong-authentication
activated_at: "2026-11-23T10:00:00+07:00"
expires_at: "2026-11-23T10:30:00+07:00"
audit_ref: pam-session-082
status: ACTIVE
~~~

Ví dụ chỉ diễn tả **ý định và giới hạn quyền**, không phải cấu hình Kubernetes hoặc policy PAM có thể chạy trực tiếp. Cần kiểm tra role thực tế không cho phép hành động khác qua quyền kế thừa, group hoặc token cũ.

### 8.3. Khi role mục tiêu không đủ hẹp

Nếu nền tảng chỉ có role admin quá rộng cho một thao tác nhỏ, không tự cấp mà không đánh giá. Có thể cần:

- Đường workflow được phê duyệt cho một **hành động cụ thể** thay vì cấp tương tác admin.
- Privileged session có ghi nhận, thời gian ngắn và giám sát hai người.
- Emergency change được IC/Security/owner chấp nhận rủi ro rõ ràng.
- Cải tiến role catalog sau incident để tách quyền quản trị theo tác vụ.

Không biến exception một lần thành permission mặc định cho mọi on-call.

## 9. SOP-EA03 — Kích hoạt break-glass khi IdP/PAM không khả dụng

**Dùng khi:** đường quản trị thông thường không hoạt động và có bằng chứng về tình huống cần khôi phục khẩn cấp, trong khi break-glass đã được tổ chức chuẩn bị, quản lý và thử nghiệm.

### 9.1. Điều kiện kích hoạt

1. Sự cố đã được xác nhận và quyền khẩn cấp thực sự cần thiết để khôi phục hoặc containment.
2. Account/phương án được **đăng ký và phê duyệt trước**; owner rõ ràng, scope đúng mục đích.
3. Người sử dụng được identity-proofing bằng **kênh dự phòng** phù hợp; không dựa duy nhất email/SSO đang lỗi.
4. IC/Security/PAM áp phê duyệt theo quy trình. Nếu cơ chế phê duyệt điện tử cũng lỗi, dùng phương án ghi nhận/đối chứng đã được định nghĩa trước và hậu kiểm.
5. Credential được lấy từ kho/phương thức lưu khẩn cấp an toàn, tránh đưa vào ticket/chat hoặc chia sẻ công khai.
6. Có cơ chế giám sát hoặc bằng chứng tối thiểu, kể cả khi SIEM/central logging gián đoạn; audit đồng bộ lại sau phục hồi.

### 9.2. Quy trình vận hành

| Bước | Hành động | Tiêu chí |
|---|---|---|
| 1 | IC xác nhận phạm vi outage và mục tiêu | Có incident ID, target, người thực hiện |
| 2 | PAM/Security xác minh người sử dụng và owner | Không phải Leaver/unauthorized |
| 3 | Phê duyệt/đối chứng theo phương án dự phòng | Có record và trách nhiệm rõ |
| 4 | Truy xuất credential qua kênh an toàn | Không phát tán secret/OTP trong log/ticket |
| 5 | Đăng nhập qua đúng đường khẩn cấp đã kiểm thử | Không tắt signature/MFA ở hệ thống khác |
| 6 | Chỉ thực hiện nhiệm vụ khôi phục được duyệt | Theo dõi hành động và hạn sử dụng |
| 7 | Thu hồi session/credential hoặc rotate theo policy | Không để access tồn dư |
| 8 | Reconcile account/role/SCIM và review audit | Owner và Security xác nhận đóng |

### 9.3. Lưu ý đặc biệt về MFA và tính độc lập

Tùy kiến trúc, một tài khoản khẩn cấp có thể cần **phương thức xác thực không phụ thuộc cùng IdP/MFA provider** đang lỗi. Điều này **không có nghĩa bỏ MFA một cách tùy tiện**. Tổ chức phải đánh giá phương thức thay thế phù hợp, tính chống phishing, quyền truy cập vật lý/thiết bị, quy trình bảo vệ recovery credential và giám sát để đạt mục tiêu khôi phục mà không tạo bypass thường trực.

### 9.4. Không phục hồi cả tenant bằng cách mở toàn bộ chính sách

Không tắt Conditional Access của mọi người, không bỏ bắt buộc kiểm tra chữ ký OIDC/SAML và không mở “allow all” ở firewall/chính sách IAM để sửa một luồng đăng nhập. Cần xử lý nguyên nhân ở đúng lớp: network, directory, signing keys, SSO, MFA, chính sách hoặc ứng dụng.

## 10. SOP-EA04 — Vận hành phiên access khẩn cấp

**Giai đoạn thực thi** cần bảo vệ cả **người thao tác**, **tài nguyên**, **dữ liệu** và **evidence**. Việc cấp được quyền chỉ là mốc bắt đầu, không phải thành công cuối cùng.

### 10.1. Kiểm soát trong phiên

- **Giới hạn tài nguyên và hành động:** chỉ thực hiện thao tác liên quan incident, không mở rộng role hoặc target mà chưa được duyệt.
- **Gắn định danh vào phiên:** actor, request/incident ID, target, role, session ID, thời điểm, nguồn thiết bị nếu được phép lưu.
- **Tách quyền đọc và sửa:** xem log thường khác với thay đổi production, rotate secret hoặc sửa IAM policy.
- **Theo dõi thời hạn:** cảnh báo trước expiry, không tự kéo dài session vượt approval.
- **Giám sát bất thường:** cấp admin cho người khác, tạo key/token mới, xuất dữ liệu lớn, tắt audit, sửa MFA/policy, tạo local account.
- **Khi phát hiện compromise:** dừng phiên/thu hồi đặc quyền và chuyển SOC theo quy trình; không tự xóa log để “làm sạch”.
- **Không trao quyền cho người khác:** người đã được duyệt không sử dụng account khẩn cấp như tài khoản chia sẻ cho nhiều responder.
- **Duy trì evidence:** session recording/PAM logs nếu khả dụng, change IDs, resource audit; chỉ lưu metadata cần thiết, không lưu mật khẩu hoặc key thô.

### 10.2. Nếu PAM/session recording bị lỗi

Khi công cụ log trung tâm không hoạt động, việc có được tiếp tục hay không phải phụ thuộc **policy và mức rủi ro**. Nếu được phép xử lý bằng đường dự phòng, cần cơ chế ghi nhận/đối chứng, chỉ thao tác tối thiểu và đồng bộ audit sau khi khôi phục. Không tuyên bố “đã ghi audit đầy đủ” khi chỉ có ghi chép thủ công không xác minh.

### 10.3. Thao tác tạo credential mới trong emergency

Nếu phục hồi dịch vụ buộc phải tạo credential mới cho workload, phải ghi owner, issuer, secret store, scope, expiry và kế hoạch rotate/thu hồi. Không lưu private key hoặc client secret trong source, terminal history, ticket hoặc shared chat. Sau incident, kiểm tra các credential khẩn này đã được thu hồi/chuyển về quy trình chuẩn.

## 11. SOP-EA05 — Gia hạn, hạ quyền hoặc kết thúc trước hạn

### 11.1. Gia hạn phải là quyết định mới

Nếu nhiệm vụ kéo dài hơn TTL:

1. Requester cập nhật incident, thao tác chưa hoàn tất và lý do cụ thể.
2. Owner/IC/Security kiểm tra có còn cần quyền cũ không, scope có thay đổi không, có dữ liệu nhạy cảm hoặc risk mới không.
3. Gia hạn theo approval, ghi thời điểm, owner và expiry mới; không tự động lặp không giới hạn.
4. Xác minh token/session, policy và monitoring tương ứng với thời hạn được cấp.
5. Có thể chuyển sang quyền thấp hơn nếu chỉ còn cần giám sát sau sửa lỗi.

### 11.2. Thu hồi sớm trong những trường hợp sau

- Incident đã được containment hoặc thao tác đã hoàn tất.
- Requester rời ca trực, chuyển nhiệm vụ hoặc không còn là người chịu trách nhiệm.
- HR/sponsor phát thay đổi JML khiến người đó không còn phù hợp.
- Security phát hiện compromise, unauthorized actions, sai scope hoặc account bị đình chỉ.
- Hạn phê duyệt/contract expiry đến trước thời hạn dự kiến.

**Không chờ ticket nghiệp vụ đóng để thu hồi** khi quyền không còn cần thiết.

## 12. SOP-EA06 — Thu hồi, xác minh và đối soát sau emergency access

Đây là bước dễ bị bỏ sót nhất. **Kết thúc phiên hoặc hết TTL trên portal không đủ chứng minh mọi quyền hiệu lực đã mất** nếu ứng dụng còn session/token, direct grant, inherited role hoặc credential độc lập.

### 12.1. Quy trình thu hồi

1. **Chụp before snapshot:** emergency grants, target roles, session IDs, key refs và approval; đối chiếu phạm vi đã cấp.
2. **Thu hồi JIT/PAM grant:** gỡ membership/role/binding tạm theo target, đóng session hoặc release privileged checkout theo khả năng nền tảng.
3. **Thu hồi session/token/credential liên quan:** sign-out, revoke refresh token, API key, SSH/mTLS key, local admin session khi chính sách và rủi ro yêu cầu; đừng giả định token đã phát tự biến mất khi role bị gỡ.
4. **Khôi phục chính sách thường:** loại bỏ policy exception tạm, firewall rule/bypass, service credential hoặc local access được tạo cho incident.
5. **Readback actual state:** kiểm tra IdP/Directory, SCIM, app-local role, cloud IAM/PAM, nested grants và thời điểm thay đổi.
6. **Kiểm tra quyền hiệu lực:** responder không còn thao tác đặc quyền đã cấp trong incident; các quyền thường ngày vẫn được phép theo RBAC/ABAC hiện hành.
7. **Đối soát JML:** cập nhật Mover/Leaver, không cho job cũ tái cấp emergency role hoặc account.
8. **Bảo vệ dữ liệu và audit:** đối chiếu thao tác đã làm với mục đích, ghi lại resource changes, credential mới và kết quả kiểm tra.
9. **Giữ ngoại lệ nếu còn tồn dư:** target fail hoặc chưa xác minh phải có owner, deadline, biện pháp giảm thiểu và escalation.
10. **Hậu kiểm độc lập:** Security/PAM/owner rà access timeline và quyền tồn dư trước khi xác nhận đóng emergency access.

### 12.2. Trạng thái và tiêu chí hoàn tất

| Trạng thái | Ý nghĩa | Được đóng? |
|---|---|---|
| `REQUESTED` | Đã yêu cầu nhưng chưa duyệt | Không |
| `APPROVED` | Đã xác nhận scope, actor, TTL và owner | Không |
| `ACTIVE` | Emergency access đang có hiệu lực | Không |
| `EXPIRED_PENDING_VERIFICATION` | TTL hết nhưng chưa chứng minh quyền đã mất | Không |
| `REVOKED_APPLIED` | API/connector/PAM báo đã gỡ | Cần readback |
| `REVOKED_VERIFIED` | Target không còn grant/credential và effective access đã đúng | Có thể đóng target |
| `EXCEPTION_OPEN` | Quyền hoặc session còn tồn tại/chưa xác minh | Không được báo fully closed |
| `REVIEW_COMPLETED` | Hậu kiểm hành động, policy, credentials và evidence hoàn tất | Có thể kết thúc quy trình |

**Nguyên tắc:** trạng thái request ≠ trạng thái thay đổi ≠ **quyền hiệu lực tại ứng dụng**. Không dùng `200 OK` của SCIM/API hoặc dashboard PAM làm bằng chứng duy nhất nếu phiên/role target có thể tồn tại độc lập.

## 13. Access khẩn cấp trong vòng đời Joiner–Mover–Leaver

### 13.1. Joiner — không dùng emergency để bỏ qua onboarding

Nhân viên mới chưa được xác minh, chưa tới ngày bắt đầu hoặc chưa hoàn thành MFA **không mặc nhiên có quyền khẩn cấp**. Nếu người mới được phân công on-call theo quy trình:

1. HR/sponsor xác nhận danh tính và ngày hiệu lực.
2. IdP/SCIM tạo account và role nền hợp lệ, MFA/đường xác thực cần thiết hoàn tất.
3. Phân công on-call/eligible-JIT được owner phê duyệt; quyền thực tế chỉ nâng khi có request hợp lệ.
4. Kiểm tra account không được gán admin thường trực bởi template hoặc manual workaround.
5. Audit cả quyền eligibility và từng lần activation.

### 13.2. Mover — không mang theo đặc quyền từ vị trí cũ

Khi chuyển vai trò, nhân viên có thể không còn thẩm quyền xử lý production hoặc dữ liệu đơn vị cũ:

- Thu hồi **eligibility** JIT/PAM của nhiệm vụ cũ ngay theo Mover.
- Đối chiếu các emergency grants còn ACTIVE và quyết định thu hồi sớm nếu không hợp lệ.
- Nếu có nhiệm vụ mới cần quyền khẩn, phải cấp eligibility/role mới theo approval, không sao chép toàn bộ quyền cũ.
- Kiểm tra session/token/grants ở app/cloud, SoD và ABAC theo department/project mới.
- Chặn event cũ tái gán quyền admin của vị trí trước.

### 13.3. Leaver — thu hồi cả quyền thường và khẩn

Leaver khẩn cấp có thể cần chặn trước khi IdP/SCIM khôi phục. Phải kiểm tra:

1. Account IdP/SSO, VPN và directory.
2. PAM/JIT eligibility, standing admin grants, break-glass checkout hoặc privileged session.
3. App-local account, service console, SSH key, PAT/API key, OAuth grants và refresh token.
4. Delegation, shared credential, resource ownership và quyền qua nhóm lồng nhau.
5. Job retry/event cũ có thể re-enable account hoặc tái cấp role.

Nếu một responder đang dùng emergency access nhưng trở thành Leaver/Suspended hoặc chịu security hold, quyền đó phải được **đánh giá và chặn theo lifecycle mới nhất**, không được duy trì vì incident cũ còn mở. Bàn giao nhiệm vụ cho người hợp lệ qua quy trình mới.

### 13.4. Guest và nhà thầu

External responder cần sponsor hợp lệ, hợp đồng/engagement còn hiệu lực, danh sách resource, expiry và approval riêng. Không gán vai trò admin toàn hệ thống chỉ vì họ là vendor hỗ trợ. Sau sự cố phải thu hồi B2B account access, API key, session và quyền local, kể cả nếu account guest còn cần cho dự án khác.

## 14. Trường hợp đặc biệt: Leaver, credential compromise hoặc IdP outage

### 14.1. Emergency access để thu hồi tài khoản đang bị chiếm

Khi phát hiện admin credential bị lộ, SOC/PAM có thể cần quyền cao để revoke, rotate signing key hoặc khóa account:

1. Xác nhận sự cố và **actor phục hồi độc lập**, tránh dùng chính account nghi compromise.
2. Xác định target, thao tác cô lập và rủi ro của credential còn active.
3. Kích hoạt đường quản trị **được phê duyệt trước** và có bằng chứng.
4. Revoke/disable account, token, key, session hoặc role bị ảnh hưởng đúng issuer và resource server.
5. Rà quyền phát sinh trái phép, app consent, service principal, local account và persistence.
6. Khôi phục trust và kiểm chứng actor khẩn đã mất quyền bổ sung sau khi nhiệm vụ xong.

Không dùng emergency access để bỏ qua điều tra lạm dụng hoặc xóa log.

### 14.2. Emergency access khi IdP lỗi diện rộng

Xác nhận lỗi IdP/network/MFA/SSO trước khi dùng break-glass. Cần phân biệt:

- **IdP không cấp phiên mới:** app sessions hiện tại có thể vẫn được chấp nhận.
- **PAM cần IdP để xác thực:** có thể cùng mất khả dụng, nên đường dự phòng phải được kiểm thử trước.
- **SCIM đồng bộ lỗi:** quản lý quyền tại đích có thể vẫn hoạt động qua app owner.
- **Signing key/JWKS lỗi:** không tắt signature validation để sửa đăng nhập.

Sau khi IdP hoạt động lại, kiểm thử OIDC/SAML, MFA, Conditional Access, chính sách quyền và hàng đợi provisioning. Đồng thời kiểm tra **mọi emergency bypass, local session, token và role** được dùng trong outage.

### 14.3. Emergency access cho Leaver khẩn

Nếu HR báo chấm dứt ngay nhưng IdP/SCIM API lỗi, owner ứng dụng được ủy quyền có thể cần truy cập quản trị để disable local account, revoke PAT và dừng session. Runbook phải giữ:

- **Nguồn Leaver có thẩm quyền**, subject ID bất biến và thời điểm hiệu lực.
- **Tập target phải chặn**, ưu tiên tài nguyên nhạy cảm có lối login độc lập.
- **Người thực thi khác Leaver**, approval/emergency path và audit.
- **Trạng thái chưa xử lý** có owner/đường chặn thay thế, không báo fully offboarded.
- **Reconciliation sau khi IdP/SCIM phục hồi** để không còn lối truy cập.

### 14.4. Break-glass bị nghi lộ credential

Đây là sự cố an ninh độc lập có thể ảnh hưởng khả năng khôi phục toàn hệ thống:

1. Kích hoạt SOC/PAM và đánh giá issuer, scope, lịch sử sử dụng, log vault và các phiên/token.
2. Theo mức rủi ro, revoke/rotate credential, khóa hoặc thay thế account theo kế hoạch khả dụng; tránh để lại account dự phòng không còn tin cậy.
3. Kiểm tra grant, token, role và secret được tạo từ account nghi lộ.
4. Đảm bảo **đường khẩn cấp còn lại** vẫn hoạt động và được bảo vệ; không tự mở account mới không audit.
5. Thực hiện hậu kiểm mọi lần sử dụng và cập nhật bài kiểm thử khẩn cấp.

## 15. Emergency access cho service account và workload identity

Không phải mọi “khẩn cấp” đều có người tương tác. Một workload có thể không lấy được token mới, CI/CD dừng triển khai hoặc service principal mất quyền cần thiết. Tuy nhiên việc cấp quyền khẩn cho workload phải có **owner và change control**.

| Tình huống | Cách tiếp cận |
|---|---|
| Service account credential hết hạn | Xác định owner, vault version, dependency, rotate bằng kênh an toàn |
| Workload federation/token service lỗi | Kiểm tra issuer, trust, metadata và phương án dự phòng đã thiết kế |
| CI/CD cần sửa production | Dùng service role/JIT phù hợp, giới hạn environment, không cấp global admin |
| Service principal bị compromise | Cô lập/tru hồi secret/role và điều tra grants phát sinh |
| Owner kỹ thuật đã nghỉ | Chuyển owner và rà quyền; không tự xóa workload production nếu còn dependency |
| Workload bị decommission | Revoke grant, trust, tokens/keys và disable identity sau xác minh dependency |

### 15.1. SOP cấp quyền khẩn cho workload

1. Xác nhận **ứng dụng và owner** chứ không chỉ người thực hiện lệnh.
2. Xác nhận incident, dependency và desired entitlement theo environment/resource.
3. Dùng managed identity/workload federation hoặc credential ngắn hạn nếu nền tảng hỗ trợ.
4. Nếu buộc tạo secret tạm, lưu trong vault, ghi owner, expiry, scope, distribution và rotation plan; **không đưa secret vào source, CI log hoặc chat**.
5. Áp role hẹp, theo dõi job/traffic và giới hạn retries; không dùng admin token cá nhân làm secret production.
6. Khi dịch vụ phục hồi, gỡ grant tạm, revoke credential cũ, xác minh workload chỉ có quyền thường ngày và audit đầy đủ.

**Không đồng nhất credential rotation với thu hồi quyền.** Key mới có thể vẫn mang policy admin quá rộng; cần đối soát RBAC/ABAC và trust.

## 16. Các lỗi vận hành thường gặp và cách phòng ngừa

| Anti-pattern | Hậu quả | Kiểm soát cải thiện |
|---|---|---|
| Admin luôn thường trực để “phòng khi cần” | Tăng rủi ro compromise và quyền thừa | JIT/PAM, role hẹp, approval và TTL |
| Break-glass chung password qua chat | Không truy vết được actor, secret lan rộng | Vault/dual control khi áp dụng, credential discipline |
| Requester tự duyệt quyền của mình | Thiếu SoD, tăng nguy cơ lạm quyền | Approver độc lập, policy khẩn đã duyệt trước |
| Dùng account Leaver/Suspended cho emergency | Trái lifecycle, khó audit | Kiểm tra authoritative JML trước activation |
| Tắt MFA/audit/SSO signature check | Mở đường tấn công ngoài phạm vi incident | Chẩn đoán đúng dependency, dùng emergency path chính thức |
| TTL hết nhưng session/token còn sống | Privilege vẫn hiệu lực sau incident | Revoke phiên/token, resource-side verify |
| Gỡ role thủ công, SCIM lại cấp lại | Quyền tạm trở thành standing privilege | Sửa desired state/source, reconciliation, version guard |
| Không kiểm thử break-glass trước incident | Không truy cập được lúc khẩn hoặc không có log | Controlled periodic exercise, failback test |
| Incident đóng, credential khẩn vẫn tồn tại | Quyền tồn dư ngoài kiểm soát | Expiry enforcement, hậu kiểm, rotation và metrics |
| Dùng admin toàn tenant khi chỉ cần đọc log | Mở quyền dữ liệu và hành động quá rộng | Chia nhỏ role, ABAC theo resource |
| Xóa break-glass vì không có HR row | Mất khả năng khôi phục khi IdP down | Registry ngoại lệ PAM/Security có owner |
| Khôi phục quyền cũ khi Mover/Leaver | Regrant trái policy, SoD conflict | Latest lifecycle, approval, source version guard |

## 17. Mô hình trạng thái và xử lý retry/revoke thất bại

~~~mermaid
stateDiagram-v2
    [*] --> REQUESTED
    REQUESTED --> DENIED: Không hợp lệ
    REQUESTED --> APPROVED: Xác minh & phê duyệt
    APPROVED --> ACTIVE: Grant & verify
    ACTIVE --> EXPIRING: Gần hết hạn / kết thúc task
    ACTIVE --> REVOKE_REQUIRED: Bị compromise / JML thay đổi
    EXPIRING --> EXTENSION_REVIEW: Có yêu cầu gia hạn
    EXTENSION_REVIEW --> ACTIVE: Gia hạn được duyệt
    EXTENSION_REVIEW --> REVOKE_REQUIRED: Từ chối gia hạn
    EXPIRING --> REVOKE_REQUIRED: TTL kết thúc
    REVOKE_REQUIRED --> REVOKED_APPLIED: Revoke API thành công
    REVOKE_REQUIRED --> EXCEPTION_OPEN: Timeout / target lỗi
    REVOKED_APPLIED --> REVOKED_VERIFIED: Actual & effective access đúng
    REVOKED_APPLIED --> EXCEPTION_OPEN: Session / grant còn tồn dư
    EXCEPTION_OPEN --> REVOKE_REQUIRED: Khắc phục & retry an toàn
    REVOKED_VERIFIED --> REVIEW_COMPLETED: Audit / hậu kiểm
    REVIEW_COMPLETED --> [*]
    DENIED --> [*]
~~~

### 17.1. Ma trận lỗi revoke

| Lỗi | Điều tra | Hành động |
|---|---|---|
| `401/403` | Credential/scopes của PAM hoặc connector lỗi | Owner sửa đúng quyền tối thiểu; không mở rộng admin tùy tiện |
| `404` | Target/grant ID không tồn tại hoặc đã bị gỡ | Đọc lại actual state, tránh xóa nhầm object |
| `409/412` | Conflict/phiên bản thay đổi | Đọc version/ETag nếu hỗ trợ, tính diff mới |
| `429` | Rate limit | Tôn trọng `Retry-After`, bounded retry/backoff có jitter |
| `5xx/timeout` | Không rõ thao tác đã áp dụng chưa | `UNKNOWN`, readback trước retry |
| `2xx nhưng grant còn | Cache, async job, role kế thừa hoặc local grant | Đối soát target, đừng đóng sớm |
| TTL không cưỡng chế tại target | Token/session/role không tự mất | Revoke riêng và giám sát cho tới verified |

**Retry chỉ an toàn nếu có idempotency và kiểm tra version**. Sự kiện grant cũ không thể được phép chạy sau một lệnh revoke mới khi requester đã Leaver/Suspended hoặc incident đã kết thúc. Với quyền khẩn cấp rủi ro cao còn hoạt động nhưng revoke tạm lỗi, mở **security exception**, biện pháp containment và escalation chứ không retry vô hạn.

## 18. Pseudocode runbook: cấp, theo dõi và thu hồi access khẩn

Ví dụ tư duy dưới đây là **mô hình kiểm soát**, không phải mã thực thi quản trị. Hệ thống thật phải triển khai IAM policy, authorization, concurrency, audit và giới hạn API riêng.

~~~text
request_emergency_access(request):
    assert request.incident_id and request.target_id
    actor = resolve_immutable_subject_id(request.requester)
    lifecycle = read_authoritative_lifecycle(actor)

    if not identity_proofing_passed(actor) or lifecycle.is_ineligible:
        reject_and_escalate(request)
        return

    if not emergency_trigger_verified(request.incident_id):
        route_to_standard_access_workflow(request)
        return

    desired = calculate_minimum_emergency_entitlement(
        request.action, request.resource, policy, approvals
    )
    if violates_sod_or_security_hold(actor, desired):
        reject_and_escalate(request)
        return

    if not independent_approval_valid(request, desired):
        use_only_documented_emergency_approval_fallback_or_deny()
        return

    grant = grant_idempotently(
        actor, desired, expires_at=approved_expiry(request)
    )
    verify_effective_access_is_within_scope(grant)
    start_audit_and_monitoring(grant, request.incident_id)
    schedule_revocation_or_expiry_check(grant)

close_emergency_access(grant):
    latest = read_authoritative_lifecycle(grant.actor)
    stop_privileged_sessions_when_supported(grant)
    revoke_grants_and_credentials(grant)
    actual = read_target_state(grant.target, grant.actor)

    if actual.still_allows_emergency_actions:
        open_security_exception_with_owner_and_deadline(grant)
        apply_authorized_containment()
        return

    verify_normal_access_matches_current_policy(latest)
    review_session_and_change_audit(grant)
    record_verified_revocation_and_close(grant)
~~~

**Bất biến triển khai:** mỗi lần activation có `incident_id`, `request_id`, `subject_id`, `target_id`, `grant_id`, `policy_version`, thời gian và approval. Trong xử lý song song phải tránh race giữa **expire**, **gia hạn**, **Leaver** và **retry grant**. Phải kiểm tra latest lifecycle và expiry trước mọi hành động cấp lại.

### 18.1. Vì sao expiration phải cưỡng chế hai tầng?

Một policy JIT có thể hết hạn ở PAM nhưng **session ứng dụng** vẫn còn hoặc access token có quyền cũ còn được resource server chấp nhận. Lý tưởng, hệ thống giới hạn đồng thời thời hạn grant và thời hạn phiên, có khả năng revoke/deny ở đích. Khi không thể thu hồi tức thì, chính sách phải ghi nhận **cửa sổ rủi ro**, giám sát và phương án containment thay thế.

## 19. Audit, telemetry và các chỉ số theo dõi

### 19.1. Audit record tối thiểu

~~~yaml
emergency_access_record_id: EMG-EXAMPLE-084
incident_ref: INC-2026-081
request_id: EMG-REQ-084
actor_subject_id: person-1042
actor_lifecycle_state: ACTIVE
owner_ref: payments-application-owner
target_system: production-payments
resource_scope: namespace/payments
emergency_type: JIT_PAM
requested_action: restart-payment-worker
approved_role: namespace-deployment-operator
policy_version: iam-policy-v18
approval_refs:
  - ic-approval-084
  - owner-approval-084
authentication_evidence_ref: auth-event-084
activated_at: "2026-11-23T10:00:00+07:00"
approved_expiry_at: "2026-11-23T10:30:00+07:00"
session_audit_ref: pam-session-084
operation_evidence_ref: deploy-event-084
revocation:
  requested_at: "2026-11-23T10:18:00+07:00"
  grant_revoked: VERIFIED
  privileged_session_closed: VERIFIED
  credentials_reviewed: VERIFIED
  effective_access: NORMAL_POLICY_ONLY
after_review_ref: security-review-084
exceptions: []
status: REVIEW_COMPLETED
~~~

**Đây là dữ liệu giả lập**, không chứa credential thực. Trong hồ sơ production, chỉ lưu ID/tham chiếu, kết quả kiểm chứng, thời điểm và owner; không ghi password, mã MFA, secret, access token, private key hoặc session cookie thô.

### 19.2. Các chỉ số vận hành có ý nghĩa

| Metric | Ý nghĩa |
|---|---|
| **Emergency activation count** | Số lần kích hoạt theo hệ thống, role, team và nguyên nhân |
| **Time to authorized activation** | Độ trễ từ request hợp lệ đến lúc quyền được cấp đúng |
| **Scope overrun / unauthorized action** | Hành động vượt scope, policy violation hoặc security alert |
| **Time to verified revocation** | Từ kết thúc nhiệm vụ/TTL đến khi quyền hiệu lực đúng |
| **Overdue emergency grants** | Quyền quá hạn còn active hoặc chưa verified |
| **Break-glass usage rate** | Tần suất sử dụng break-glass, lý do và hậu kiểm |
| **Emergency credential rotation completion** | Việc xoay/thu hồi credential sau checkout/incident |
| **JML stale privilege count** | Quyền khẩn của Mover/Leaver còn tồn dư |
| **Unreviewed emergency sessions** | Số session chưa được owner/Security hậu kiểm |
| **Failover exercise success** | Tỉ lệ kiểm thử định kỳ đạt yêu cầu activation + revocation |
| **Regrant recurrence** | Quyền khẩn được cấp lại bởi connector/event cũ |
| **Exception age** | Thời gian tồn tại exception chưa xử lý, phân mức rủi ro |

Các metric phải tách **đã yêu cầu**, **đã phê duyệt**, **đã cấp**, **đã thu hồi qua API**, **đã verified**. Một dashboard có “0 grant active” ở PAM nhưng chưa đọc session tại ứng dụng có thể bỏ sót residual access.

### 19.3. Bằng chứng để đóng hồ sơ

1. Incident và lý do khẩn đã được xác nhận; requester, target, thao tác và thời hạn rõ ràng.
2. Có approval hợp lệ hoặc phương án khẩn dự phòng được policy cho phép, kèm bằng chứng.
3. Authentication/identity proofing và JML state được kiểm tra tại thời điểm kích hoạt.
4. Quyền đã cấp đúng scope, có log các thao tác và exception phát sinh.
5. Grant, session, token/credential liên quan đã được thu hồi hoặc quản lý như exception có hạn.
6. **Actual state** và **effective access** của mọi target liên quan phù hợp policy hiện hành.
7. Break-glass credential/đường local đã được khóa, rotate hoặc trả về trạng thái bảo vệ theo quy định.
8. Hậu kiểm của Security/PAM/owner hoàn tất; cập nhật root cause và đề xuất cải tiến.

## 20. Các tình huống thực hành

### Tình huống A — IdP down, cần khôi phục quyền quản trị

IdP không cấp đăng nhập mới; PAM phụ thuộc cùng IdP nên on-call không thể vào hệ thống quản lý. Một dịch vụ trọng yếu ngừng xử lý giao dịch.

**Hướng xử lý:** mở incident, xác nhận outage và vai trò on-call, kiểm tra đường break-glass độc lập đã được kiểm thử, phê duyệt/đối chứng qua quy trình dự phòng, thực hiện đúng thao tác phục hồi và giữ log. Sau đó thu hồi/đánh giá lại session, credential, kiểm tra IdP/SSO/SCIM đã phục hồi và không còn quyền khẩn tồn dư. Không tắt MFA hoặc ký xác thực toàn tenant.

### Tình huống B — Cần xem log nhưng requester đòi Global Admin

Responder cần xem log lỗi trên một namespace nhưng yêu cầu admin toàn cluster vì đó là role có sẵn.

**Hướng xử lý:** đánh giá tác vụ cụ thể, chọn quyền read-logs tại namespace hoặc role hẹp; nếu hệ thống không hỗ trợ, owner/Security đánh giá phương án PAM giám sát và thời hạn ngắn. Không cấp standing Global Admin chỉ vì thiếu role catalog tốt.

### Tình huống C — JIT hết hạn nhưng API token còn scope admin

Quyền PAM hết TTL, dashboard hiển thị hết hạn nhưng một service API vẫn chấp nhận token admin được phát trước đó.

**Hướng xử lý:** chưa ghi `REVOKED_VERIFIED`. Tìm issuer/resource server, revoke token/session hoặc dùng deny policy theo khả năng, kiểm chứng hành động admin bị từ chối, phân tích nguyên nhân session TTL không đồng bộ grant TTL và sửa thiết kế.

### Tình huống D — Nhân viên chuyển vai trò nhưng vẫn được JIT admin

Người từng là SRE đã sang nhóm Finance. Eligibility PAM của SRE chưa bị thu hồi và họ yêu cầu JIT để sửa production.

**Hướng xử lý:** từ chối cấp theo role cũ; đọc Mover mới nhất, thu hồi eligibility và kiểm tra grants/session còn sống. Nếu thực sự cần tham gia incident, tạo approval mới phù hợp nhiệm vụ và SoD, quyền hẹp/thời hạn rõ ràng; không dùng quyền đứng từ vị trí cũ.

### Tình huống E — Leaver khẩn nhưng SCIM lỗi

HR đã xác nhận Terminated; SaaS quan trọng vẫn active, API SCIM trả 503 và người nghỉ còn PAT.

**Hướng xử lý:** responder có quyền được ủy quyền dùng đường quản trị tại SaaS để disable account, revoke PAT/session và chặn quyền cục bộ; ghi evidence. Giữ exception connector và reconcile khi khôi phục, không báo fully offboarded khi còn đường truy cập chưa kiểm chứng.

### Tình huống F — Break-glass được dùng mà không có incident

SIEM báo một lần sử dụng break-glass vào cuối tuần nhưng không có incident record, người dùng nói “chỉ thử”.

**Hướng xử lý:** SOC/PAM xác minh account, actor, session, thao tác và mục đích; coi là sử dụng ngoài quy trình cho tới khi làm rõ, hạn chế/revoke credential theo rủi ro và hậu kiểm. Nếu là bài test hợp lệ nhưng thiếu record, sửa quy trình drill; không bỏ qua alert vì account vốn dùng cho khẩn cấp.

### Tình huống G — Service principal được cấp quyền tạm quá rộng

Pipeline CI/CD cần triển khai một ứng dụng nhưng vì lỗi permission đã được cho admin trên toàn cloud project và giữ quyền sau lần deploy.

**Hướng xử lý:** tìm owner và dependency, thiết kế service role giới hạn resource/environment, chuyển workload sang role phù hợp, revoke grant admin và secret tạm, kiểm tra job chạy bình thường và cloud audit. Không thay bằng token admin cá nhân.

### Tình huống H — Người phê duyệt không thể truy cập hệ thống

Một incident cần thay policy ứng dụng nhưng người duyệt thông thường không thể dùng SSO. Requester tự đề nghị duyệt trên tài khoản của mình.

**Hướng xử lý:** dùng kênh quyết định dự phòng đã được định nghĩa (IC/Security/on-call approver, ghi lại bằng chứng và hậu kiểm). Nếu không có phương án có thẩm quyền, escalated decision hoặc fail closed theo chính sách; không tự phê duyệt và tạo admin không audit.

### Tình huống I — Emergency role bị cấp lại sau thu hồi

IAM gỡ role emergency tại ứng dụng nhưng một job đồng bộ vẫn giữ user trong group nguồn, vài phút sau quyền xuất hiện lại.

**Hướng xử lý:** điều tra desired state, event ID/version, group mapping và connector retry. Sửa nguồn, chặn regrant, chạy reconciliation idempotent rồi xác minh target/phiên không còn quyền. Không chỉ lặp lại thao tác Remove trong app.

## 21. Checklist runbook cho ca trực

| Giai đoạn | Tiêu chí kiểm tra |
|---|---|
| **Trigger** | Incident/request thực sự khẩn, có ID và severity/impact? |
| **Identity** | Requester đã được xác minh, vẫn Active, không bị security hold? |
| **Scope** | Hành động/tài nguyên/môi trường/thời hạn đã giới hạn nhỏ nhất? |
| **Approval** | Có owner, IC, Security/PAM theo policy, không tự phê duyệt? |
| **Authentication** | MFA/phương thức dự phòng phù hợp, không tắt kiểm soát rộng? |
| **Activation** | Grant được cấp đúng target, actual/effective access đúng phạm vi? |
| **Session** | Log/monitoring, expiry, hành động và thay đổi trong phiên được ghi? |
| **JML** | Event Mover/Leaver mới không bị job cấp quyền cũ ghi đè? |
| **Revoke** | Role/grant, session/token/credential và đường local đã xử lý? |
| **Verify** | Thao tác đặc quyền không còn được phép; quyền thường đúng policy? |
| **Evidence** | Request, approval, actor, before/after, timestamp, review đủ? |
| **Exception** | Quyền chưa thu hồi có owner, biện pháp giảm thiểu và deadline? |
| **Review** | Break-glass/JIT được hậu kiểm, cập nhật policy và lesson learned? |

## 22. Tổng kết

**Access khẩn cấp không phải là quyền admin vô điều kiện.** Đó là một **ngoại lệ được thiết kế trước, có người chịu trách nhiệm, thời hạn rõ ràng, phạm vi tối thiểu, kiểm soát hoạt động và xác minh thu hồi**. Trong vận hành IAM, chuẩn bị tốt break-glass/JIT/PAM giúp ứng phó IdP outage, sự cố production và yêu cầu chặn truy cập khẩn mà không phá vỡ nguyên tắc Zero Trust và least privilege.

Quan trọng nhất, quá trình phục hồi phải đóng vòng đời quyền: **Joiner** không được bypass xác minh, **Mover** không mang theo đặc quyền cũ, **Leaver** không giữ được session/token hoặc quyền local, **service account** có owner và credential an toàn, còn **IdP/SSO/SCIM/RBAC/ABAC** được đối soát về desired state sau incident. Một emergency access chỉ thực sự kết thúc khi **quyền hiệu lực ở các hệ thống đích đã trở về đúng chính sách và có bằng chứng kiểm toán**.
