# Just-in-time access trong Least Privilege và IAM Identity Lifecycle

## 1. Just-in-time access là gì?

**Just-in-time access (JIT access)** là cách cấp hoặc kích hoạt **quyền truy cập đúng lúc có nhu cầu được chấp thuận**, với **phạm vi, mục đích và thời hạn giới hạn**, thay vì để người dùng hoặc workload giữ quyền rộng thường trực (*standing privilege*). Khi nhu cầu kết thúc hoặc quyền hết hiệu lực, hệ thống phải thu hồi khả năng sử dụng quyền theo chính sách và **xác minh trạng thái thực tế**.

Ví dụ, một kỹ sư vận hành bình thường chỉ được đọc log sản xuất. Khi có sự cố nghiêm trọng, người đó xin quyền **production.restart-service** cho đúng dịch vụ, trong 30 phút. Hệ thống kiểm tra người xin có thuộc danh sách đủ điều kiện, yêu cầu xác thực mạnh và phê duyệt khi cần, rồi kích hoạt quyền tạm. Khi hết hạn, việc gọi API restart phải bị từ chối; không được giữ vai trò quản trị vĩnh viễn chỉ để xử lý một vài sự cố mỗi tháng.

Bài học thuộc chương **Least privilege** của mô-đun **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**. Mục tiêu của mô-đun là quản lý danh tính **Joiner–Mover–Leaver (JML)** từ xác minh, tạo tài khoản, cấp quyền đến rà soát và thu hồi khi quan hệ hoặc vai trò thay đổi. JIT access liên kết trực tiếp với **IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, kiểm toán** và việc giảm **quyền truy cập tồn dư**.

### Những câu hỏi JIT phải trả lời

1. **Ai** đang yêu cầu và danh tính/quan hệ có còn hợp lệ?
2. **Quyền nào** thực sự cần cho tác vụ?
3. **Trên tài nguyên nào**, tenant và môi trường nào?
4. **Vì sao**, theo ticket, incident hay nhiệm vụ nào?
5. **Có đủ điều kiện và phê duyệt** không?
6. **Trong bao lâu**, có giới hạn về lượt dùng hoặc thời điểm không?
7. **Ai hoặc thành phần nào thực thi** việc cấp quyền?
8. **Hết hạn/Leaver/sự cố thì thu hồi thế nào**, kể cả phiên và token cũ?
9. **Bằng chứng nào** cho thấy quyền đã được cấp đúng và thu hồi đúng?

**JIT access không phải chỉ là một nhãn “temporary” trong giao diện.** Phải có enforcement thực tế, hạn sử dụng và khả năng đối soát.

## 2. Vì sao JIT là một kỹ thuật của Least Privilege?

**Principle of Least Privilege** yêu cầu mỗi chủ thể chỉ có quyền tối thiểu cần thiết để hoàn thành tác vụ được phép. Có ít nhất ba chiều cần giới hạn:

| Chiều | Câu hỏi | Ví dụ |
|---|---|---|
| **Quyền (what)** | Action nào thực sự cần? | restart-service, không phải toàn bộ cloud-admin |
| **Tài nguyên (where)** | Quyền áp dụng ở đâu? | service-payments của tenant A, không phải mọi service |
| **Thời gian (when)** | Khi nào được phép dùng? | Từ 09:00 đến 09:30 hoặc trước khi incident đóng |
| **Bối cảnh (under what conditions)** | Yêu cầu MFA, thiết bị, approval, SoD gì? | FIDO2 + change ticket hợp lệ |
| **Tác nhân (who)** | Chính người nào/workload nào được kích hoạt? | identityId cụ thể, không phải tài khoản chung |
| **Khả năng thực thi (how)** | Có cần quyền liên tục hay qua lệnh được trung gian hóa? | Command proxy chỉ cho restart đúng dịch vụ |

Một **standing admin role** khiến tài khoản luôn là mục tiêu có giá trị cao. JIT làm ngắn khoảng thời gian có thể lạm dụng quyền và thu hẹp ảnh hưởng khi credential hoặc phiên bị chiếm. Tuy nhiên, JIT không tự giải quyết phishing, chiếm phiên, lỗi cấp quyền ở API hoặc thao tác đã hoàn thành trong cửa sổ JIT.

### Ví dụ cùng một tác vụ

| Thiết kế | Quyền của người vận hành | Rủi ro |
|---|---|---|
| **Standing global admin** | Mọi lúc, mọi dịch vụ | Phạm vi và thời gian lạm dụng lớn |
| **Standing scoped admin** | Mọi lúc, một dịch vụ | Thu hẹp tài nguyên nhưng vẫn thường trực |
| **JIT scoped admin** | Một dịch vụ trong thời hạn duyệt | Giảm thời gian và phạm vi quyền |
| **JIT + Just-Enough-Administration** | Chỉ những lệnh cần thiết qua cơ chế trung gian | Thu hẹp thêm hành động; cần kiểm soát công cụ thực thi |

**Không tối ưu JIT bằng cách tạo một tài khoản admin chung rồi cho nhiều người mượn.** Danh tính riêng, traceability và SoD vẫn quan trọng.

## 3. Phân biệt Eligible và Active

Hai trạng thái quan trọng trong nhiều thiết kế JIT:

- **Eligible:** người dùng hoặc workload **đủ điều kiện được yêu cầu/kích hoạt** một quyền. Chưa có nghĩa action đặc quyền đã được phép thực hiện.
- **Active:** một grant đã được kích hoạt và hiện có thể được thực thi theo phạm vi, thời hạn và chính sách.
- **Expired/Revoked:** grant không còn là căn cứ cho quyền truy cập.
- **Suspended/Blocked:** không cho dùng quyền vì sự cố, thay đổi JML hoặc policy dù grant có thể còn metadata lịch sử.

Ví dụ, Lan là thành viên nhóm on-call và **eligible** để kích hoạt quyền **production.deploy**. Lan chỉ trở thành **active** cho quyền này sau khi hoàn thành kiểm tra thích hợp. Khi hết 45 phút, grant hết hạn; việc thuộc nhóm on-call không có nghĩa có thể tiếp tục deploy mà không kích hoạt lại.

### Hai loại entitlement

| Loại | Vai trò | Quản trị |
|---|---|---|
| **Eligibility assignment** | Quy định ai có thể yêu cầu quyền gì | Cần owner, review, scope và điều kiện |
| **Active grant** | Quyền thực thi được kích hoạt theo yêu cầu cụ thể | Có request ID, thời hạn, điều kiện, trạng thái và audit |

**Eligible không phải permission thực thi.** Một API chỉ kiểm “người dùng eligible” rồi cho gọi lệnh admin đã bỏ qua bước kích hoạt.

### Vòng đời grant

~~~mermaid
stateDiagram-v2
    [*] --> NotEligible
    NotEligible --> Eligible: Được đưa vào danh sách đủ điều kiện
    Eligible --> Requested: Xin kích hoạt theo nhiệm vụ
    Requested --> Denied: Không đủ điều kiện / bị từ chối
    Requested --> Approved: Policy và approval đạt
    Approved --> Active: Cấp grant và readback thành công
    Active --> Expired: Hết thời hạn
    Active --> Revoked: Thu hồi sớm / JML / sự cố
    Active --> Suspended: Tạm khóa theo risk
    Suspended --> Revoked: Chấm dứt
    Suspended --> Active: Được duyệt mở lại nếu còn hợp lệ
    Expired --> Eligible: Eligibility vẫn còn
    Revoked --> Eligible: Eligibility còn hợp lệ theo policy
    Denied --> Eligible: Có thể xin lại sau khi thay điều kiện
~~~

Sơ đồ là mô hình minh họa. Nếu người dùng **Leaver**, eligibility cũng phải được gỡ hoặc bị chính sách vô hiệu; không thể chuyển lại Eligible một cách tự động từ grant hết hạn.

## 4. Các thành phần kiến trúc của JIT access

Một triển khai JIT thường nối nhiều hệ thống:

| Thành phần | Vai trò |
|---|---|
| **HRIS / contract system** | Nguồn quan hệ làm việc và các sự kiện Joiner/Mover/Leaver |
| **IAM / IGA** | Identity mapping, eligibility, access request, review, desired state |
| **Identity Provider (IdP)** | Xác thực và MFA/step-up, quản lý phiên SSO |
| **PAM/PIM hoặc JIT broker** | Điều phối kích hoạt quyền, thời hạn, approval và thu hồi |
| **Policy engine (PDP)** | Quyết định subject–action–resource–context có phù hợp không |
| **Policy enforcement point (PEP)** | Chặn action nếu thiếu grant active/điều kiện |
| **SCIM/API connector** | Cập nhật group/role/account ở ứng dụng đích khi cần |
| **Resource server / cloud / database** | Nơi quyền thực sự được thực thi |
| **Token/session/secret manager** | Phát hành, giới hạn và thu hồi credential liên quan |
| **Audit/reconciliation** | Đối chiếu yêu cầu, cấp quyền, việc dùng và trạng thái thu hồi |

~~~mermaid
flowchart TD
    HR[HRIS / JML] --> IAM[IAM / IGA]
    U[Người dùng / workload] --> IDP[IdP / Strong Authentication]
    IDP --> BROKER[JIT / PAM / PIM Broker]
    IAM --> BROKER
    BROKER --> PDP[PDP: eligibility + scope + time + SoD]
    PDP --> BROKER
    BROKER --> APP[Target API / SCIM / Cloud IAM]
    APP --> PEP[PEP / Resource Server]
    U -->|Action được yêu cầu| PEP
    PEP --> POLICY[Grant active + RBAC/ABAC]
    APP --> AUDIT[Audit / Reconciliation]
    BROKER --> AUDIT
    PEP --> AUDIT
~~~

**Điểm quyết định và điểm thực thi có thể ở những hệ thống khác nhau.** Broker trả “approved” chưa chứng minh nhóm cloud hoặc DB role đã được cập nhật. Và connector cập nhật nhóm thành công chưa chứng minh API sẽ từ chối khi quyền hết hạn.

## 5. JIT access khác JIT provisioning và JEA thế nào?

Các thuật ngữ dễ bị nhầm:

| Thuật ngữ | Ý nghĩa | Ví dụ |
|---|---|---|
| **JIT access** | Cấp/kích hoạt quyền khi có nhu cầu và chỉ trong phạm vi/thời hạn thích hợp | Kỹ sư có quyền restart 30 phút |
| **JIT provisioning** | Tạo account ở ứng dụng khi đăng nhập/nhận sự kiện đầu tiên | SaaS tạo User khi SSO đầu tiên |
| **Just-Enough-Administration (JEA)** | Giới hạn tập thao tác quản trị tối thiểu có thể thực hiện | Chỉ restart một service qua command proxy |
| **Privileged Access Management (PAM)** | Quản lý và kiểm soát truy cập đặc quyền | Vault, session brokering, audit |
| **Privileged Identity Management (PIM)** | Quản trị trạng thái đủ điều kiện/kích hoạt role đặc quyền tùy nền tảng | Eligible admin role có thời hạn kích hoạt |
| **Break-glass** | Quy trình truy cập khẩn cấp có kiểm soát khi cơ chế thường lỗi | Khóa tài khoản khẩn cấp và giám sát |
| **Time-bound access** | Quyền có hạn thời gian | Grant hết hạn sau 1 giờ |

**Không phải cứ có ngày hết hạn là đã có JIT.** Một quyền cấp tự động từ đầu năm cho cả quý không chắc đáp ứng nguyên tắc “đúng lúc cần”. Ngược lại, JIT có thể kết hợp **time-bound role, per-command approval, session proxy hoặc token ngắn hạn**.

JIT access thường áp vào **quyền đặc quyền**, nhưng có thể dùng cho truy cập dữ liệu nhạy cảm, nhà thầu hoặc các thao tác nghiệp vụ cần phân tách trách nhiệm.

## 6. Xác định eligibility trước khi cho kích hoạt

Eligibility nên được quản lý như một quyền có điều kiện:

1. **Danh tính được xác minh:** identityId bền vững, account liên kết đúng.
2. **Quan hệ hợp lệ:** nhân viên/nhà thầu còn hiệu lực, chưa có Leaver hoặc suspension áp dụng.
3. **Vai trò nền tảng:** thuộc nhóm on-call, đội DBA hay chức năng được phép yêu cầu.
4. **Đã hoàn thành đào tạo/điều kiện:** chỉ khi policy nghiệp vụ thật sự yêu cầu.
5. **Không vi phạm SoD:** không tự cấp hoặc tự phê duyệt quyền xung đột.
6. **Đủ tư cách cho tenant/resource:** cùng dự án, đơn vị hay asset được bảo trợ.
7. **Thời hạn của eligibility:** nếu đến từ nhiệm vụ/điều động có hạn, không kéo dài vĩnh viễn.
8. **Có owner/phê duyệt:** manager, resource owner hoặc đội security phù hợp.

### Eligibility không nên lấy từ email

Tên hiển thị, username và email có thể thay đổi hoặc tái sử dụng. Quy tắc phải gắn với **identity ID và relationship ID** đã xác minh; khi nhân viên quay lại làm, không tự giữ lại eligibility của vai trò cũ chỉ vì email giống.

### Risk-based eligibility

Cùng một người có thể eligible để xem log nhưng không eligible để export database sản xuất. Eligibility cần gắn với **action và resource scope**, không chỉ cờ “có thể request admin”.

## 7. Quy trình yêu cầu và kích hoạt quyền JIT

Quy trình khuyến nghị:

1. **Tạo request:** xác định identity/workload, action, resource, scope, lý do, ticket và thời lượng cần dùng.
2. **Xác minh identity/relationship:** theo nguồn JML đáng tin; loại bỏ trạng thái Leaver hoặc bị đình chỉ.
3. **Kiểm tra eligibility:** đúng role nghiệp vụ, tenant, resource và các điều kiện tiên quyết.
4. **Đánh giá rủi ro:** quyền nhạy cảm, môi trường prod, dữ liệu, thời điểm, trạng thái thiết bị, dấu hiệu bất thường.
5. **Thực hiện step-up/MFA:** nếu action yêu cầu, dùng phương thức đủ assurance; không chỉ tin claim do client tự khai.
6. **Phê duyệt:** manager, resource owner hoặc người độc lập theo SoD khi chính sách đòi hỏi.
7. **Phát hành grant:** có ID, scope, from/until, policy version; không kéo dài vô hạn theo mặc định.
8. **Cấp quyền tại đích:** broker kích hoạt role, nhóm, session proxy hoặc credential ngắn hạn.
9. **Đối soát trước khi thông báo:** xác minh quyền hợp lệ đã hoạt động đúng phạm vi.
10. **Theo dõi trong thời gian active:** audit action, risk alert và thay đổi JML.
11. **Hết hạn/thu hồi sớm:** chặn action mới, thu hồi session/credential khi cần.
12. **Readback:** đối chiếu quyền ở đích và đóng request khi không còn quyền tồn dư trái policy.

### Sơ đồ trình tự

~~~mermaid
sequenceDiagram
    participant U as User
    participant IDP as IdP
    participant BROKER as JIT Broker
    participant PDP as Policy / Approver
    participant TARGET as Target System
    participant AUDIT as Audit
    U->>IDP: Đăng nhập / MFA theo yêu cầu
    U->>BROKER: Yêu cầu action + resource + thời hạn + ticket
    BROKER->>PDP: Kiểm tra eligibility, JML, SoD và risk
    PDP-->>BROKER: Approved / Denied + điều kiện
    BROKER->>TARGET: Kích hoạt grant có phạm vi
    TARGET-->>BROKER: Xác nhận / trạng thái quyền
    BROKER->>TARGET: Readback quyền đang active
    BROKER-->>U: Thông báo activated nếu được xác minh
    U->>TARGET: Thực hiện action được phép
    TARGET->>AUDIT: Ghi subject-action-resource-outcome
    BROKER->>TARGET: Thu hồi khi hết hạn hoặc JML
    TARGET-->>BROKER: Trạng thái sau thu hồi
    BROKER->>AUDIT: Reconciliation và closure
~~~

**Approval không đồng nghĩa active. Active không đồng nghĩa action đã hoàn thành. Revocation request không đồng nghĩa tài nguyên đã từ chối.** Mỗi mốc có trạng thái, bằng chứng và lỗi riêng.

## 8. Định nghĩa request/grant theo dữ liệu có cấu trúc

Một bản ghi **request JIT** có thể dùng dạng:

~~~json
{
  "requestId": "jit-20261123-018",
  "identityId": "person-2046",
  "relationshipId": "employment-2046-v1",
  "targetSystem": "production-operations",
  "tenantId": "org-vn",
  "resourceId": "service-payments",
  "action": "service.restart",
  "requestedDurationMinutes": 30,
  "purpose": "INC-2026-1427",
  "reason": "Khôi phục service sau lỗi xác định",
  "requestedAt": "2026-11-23T09:00:00+07:00",
  "requestState": "PENDING_APPROVAL"
}
~~~

Khi policy và phê duyệt hợp lệ, một **grant** có thể được ghi riêng:

~~~json
{
  "grantId": "grant-6f13",
  "requestId": "jit-20261123-018",
  "subjectId": "person-2046",
  "targetSystem": "production-operations",
  "resourceId": "service-payments",
  "allowedActions": ["service.restart"],
  "effectiveFrom": "2026-11-23T09:06:00+07:00",
  "effectiveUntil": "2026-11-23T09:36:00+07:00",
  "status": "ACTIVE",
  "approvedBy": "person-7812",
  "policyVersion": "jit-prod-v4",
  "activationMethod": "TARGET_ROLE_BINDING",
  "evidenceRef": "audit-20261123-992"
}
~~~

Đây là **schema minh họa nội bộ**, không phải cấu trúc chuẩn của SCIM, OIDC hay một sản phẩm PIM/PAM cụ thể.

### Phân tách những ID quan trọng

- **IdentityId/subjectId:** chủ thể xin quyền, phải bền vững và có namespace.
- **RelationshipId:** quan hệ làm việc làm căn cứ cấp quyền; có thể khác personId.
- **RequestId:** yêu cầu nghiệp vụ cần phê duyệt.
- **GrantId:** quyền đang có hiệu lực và cần thu hồi/đối soát.
- **Target resource ID:** tài nguyên thật, không chỉ tên dịch vụ dễ nhầm.
- **Policy version:** quy tắc đã được áp dụng khi quyết định.
- **EvidenceRef:** liên kết tới audit, không phải bí mật hoặc token.

**Không đưa mật khẩu, access token, private key hay approval secret vào bản ghi quản trị thông thường.**

## 9. Xác thực mạnh và phê duyệt không phải một việc

Trước khi kích hoạt quyền rủi ro cao, có thể cần:

- **MFA hoặc phishing-resistant authentication** như FIDO2/WebAuthn, theo mức assurance được chấp nhận.
- **Step-up authentication** gần thời điểm kích hoạt khi phiên hiện tại quá cũ hoặc chưa đủ mạnh.
- **Thiết bị đạt yêu cầu** theo tín hiệu MDM/EDR có thể xác minh.
- **Approval** từ người có thẩm quyền, đặc biệt với truy cập production, dữ liệu cá nhân nhạy cảm hoặc chuyển tiền.
- **Kiểm tra SoD** và policy về hạn mức/đối tượng.
- **Ticket/incident/change** hợp lệ làm căn cứ, khi quy trình yêu cầu.

**MFA không thay thế approval. Approval không thay thế MFA.** Một nhân viên xác thực bằng security key không tự có quyền sửa hệ thống sản xuất; một manager đồng ý cũng không khiến một phiên yếu được bỏ qua điều kiện xác thực.

### Rủi ro tự phê duyệt

Không nên cho người xin quyền tự phê duyệt request của chính mình khi có yêu cầu phân tách nhiệm vụ. Đánh giá SoD cần kiểm tra **người phê duyệt thực**, quyền được ủy quyền, quan hệ quản lý và khả năng tài khoản phê duyệt đã bị chiếm.

### Approval và hành động có thời hạn

Một phê duyệt có thể chỉ có giá trị cho **một request và cửa sổ cụ thể**. Không được tự hiểu “đã duyệt tháng trước” là giấy phép kích hoạt đặc quyền vô hạn trong tương lai.

## 10. Scope và Just-Enough-Administration (JEA)

JIT giảm **thời gian giữ quyền**; JEA giảm **tập hành động có thể thực hiện**. Kết hợp hai nguyên tắc giúp tránh kiểu “cần restart một service nhưng được global root”.

| Nhu cầu | Quyền quá rộng | Quyền nên cân nhắc |
|---|---|---|
| Xem log một ứng dụng | Global cluster administrator | logs.read trong namespace đã duyệt |
| Restart service | Full production admin | service.restart trên đúng service |
| Thay cấu hình DB có kiểm soát | Database superuser | Một tập lệnh hoặc role hẹp được trung gian hóa |
| Phê duyệt hóa đơn | Finance super-admin | invoice.approve theo đơn vị và hạn mức |
| Xuất dữ liệu để điều tra | Data admin mọi bảng | report.export đúng dataset, masking và thời hạn |
| Triển khai ứng dụng | Admin mọi project cloud | deploy trên service và environment được phép |

**Scope phải được thực thi tại hệ thống đích hoặc PEP**, không chỉ được ghi trong ticket. Ví dụ request ghi “namespace=payments” nhưng connector cấp **cluster-admin** thì đó không còn là quyền tối thiểu.

### Quyền admin không cần đồng nhất quyền nghiệp vụ

Nhân viên đội IAM có thể cần **user.disable** nhưng không cần **payment.approve**; kỹ sư hạ tầng có thể cần **deployment.rollback** nhưng không cần đọc payroll. JIT phải tôn trọng **separation of duties** và không hợp thức hóa việc chia sẻ global-admin.

## 11. Chính sách quyết định kích hoạt JIT

Một policy JIT có thể đánh giá:

\[
PermitActivation = Eligible \land ActiveIdentity \land ScopeAllowed
\land AssuranceSatisfied \land ApprovalSatisfied \land NoSoDConflict
\]

Đây là mô hình khái niệm; policy thực còn có các điều kiện rủi ro, thời gian, nguồn ticket và hệ thống đích.

### Giả mã minh họa

~~~text
function evaluateJitActivation(request, authenticatedSession):
    subject = loadTrustedIdentity(request.identityId)
    relationship = loadCurrentRelationship(request.relationshipId)
    eligibility = loadApprovedEligibility(subject, request.action)
    resource = loadTrustedTargetResource(request.targetSystem,
                                         request.resourceId)

    if not authenticatedSession.belongsTo(subject):
        return DENY

    if not relationship.isActiveAt(serverTime):
        return DENY

    if subject.lifecycleState in [LEAVER, SUSPENDED, DISABLED]:
        return DENY

    if not eligibility.allows(request.action, resource):
        return DENY

    if request.duration > policy.maximumDuration(request.action, resource):
        return DENY

    if not verifiedSessionAssuranceMeetsPolicy(authenticatedSession,
                                               request.action):
        return REQUIRE_STEP_UP

    if conflictsWithSeparationOfDuties(subject, request, resource):
        return DENY

    if policy.requiresApproval(request):
        if not verifiedIndependentApprovalExists(request):
            return PENDING_APPROVAL

    if not trustedRiskAndContextMeetPolicy(subject, resource):
        return DENY

    return PERMIT_ACTIVATION
~~~

**Giả mã không tự cấp quyền**; broker phải thực hiện activation tại đích, kiểm tra readback và lưu grant. Giá trị **request.action, duration, resourceId** phải bị kiểm soát bằng catalog và policy, không dùng trực tiếp để xây câu lệnh quản trị không được xác thực.

### Default deny

Khi eligibility không có, policy lỗi, không đọc được trạng thái Leaver hoặc không thể xác minh người phê duyệt, **không tự cho kích hoạt quyền nhạy cảm**. Có thể mở incident/đường hỗ trợ hoặc break-glass đã được quy định thay vì bỏ qua kiểm tra.

## 12. Thời hạn, lease, giới hạn lượt và quy tắc gia hạn

JIT thường dựa trên một **lease**: quyền chỉ hợp lệ trong khoảng từ **effectiveFrom** đến **effectiveUntil**.

### Ngữ nghĩa biên thời gian

Một cách xác định rõ ràng:

\[
Valid(t) \iff effectiveFrom \leq t < effectiveUntil
\]

Mốc **effectiveUntil** là **biên loại trừ**: tại hoặc sau thời điểm đó, grant không còn là căn cứ Permit. Dùng **clock đáng tin tại server**, thống nhất timezone và xử lý sai lệch đồng hồ.

### Những giới hạn hữu ích

| Giới hạn | Ý nghĩa |
|---|---|
| **Maximum duration** | Không cho người dùng tự chọn thời hạn vô hạn |
| **Earliest activation** | Không kích hoạt trước khi approval/quan hệ có hiệu lực |
| **Maximum concurrent grants** | Hạn chế nhiều phiên đặc quyền đồng thời |
| **One request per purpose** | Tránh tái dùng approval cho mục đích khác |
| **Idle timeout** | Đóng phiên proxy không hoạt động khi phù hợp |
| **Maximum action count** | Nếu kiến trúc hỗ trợ, giới hạn lượt thao tác |
| **No silent renewal** | Gia hạn cần kiểm policy, quan hệ và phê duyệt lại khi cần |
| **Early termination** | Incident đóng, risk tăng, Mover/Leaver làm mất hiệu lực trước hạn |

Không mặc định rằng **hết TTL của grant** sẽ cắt mọi token/phiên đã phát nếu target system không kiểm thời hạn ở runtime. TTL phải được **thực thi** tại PEP/RS/PAM hoặc qua thu hồi quyền/cấp phát credential có hạn phù hợp.

### Gia hạn

Một yêu cầu gia hạn không được tự nâng thành standing access. Cần kiểm tra **trạng thái JML hiện tại, lý do công việc còn hợp lệ, tổng thời lượng, phê duyệt và hành động đã thực hiện**. Tổ chức nên có chính sách giới hạn những chuỗi kích hoạt lặp vô hạn.

## 13. Cấp quyền thực tế: group, role, session proxy hay credential ngắn hạn?

Có nhiều mô hình activation; chúng không có cùng đặc tính thu hồi.

| Mô hình | Cách cấp quyền | Rủi ro đặc thù |
|---|---|---|
| **Temporary group membership** | Thêm user vào group được mapping tới permission | Group sync/cache trễ, token cũ còn claim |
| **Temporary role binding** | Gán role scoped ở cloud hoặc ứng dụng | Role binding có thể còn sau thời hạn nếu không có cleanup |
| **Session brokering** | PAM mở phiên được kiểm soát tới tài nguyên | Cần giám sát và đóng phiên thực sự |
| **Short-lived credential** | Phát token/certificate credential có hạn | Credential có thể tồn tại tới exp, không phải lúc nào revocable tức thì |
| **Per-command authorization** | Gateway kiểm action trước mỗi lệnh | Phải bao phủ mọi command path và tránh bypass |
| **Database temporary grants** | Kích hoạt DB role/quyền trong thời hạn | Pool connection/session cũ có thể giữ quyền |
| **SaaS entitlement API** | Cấp role qua SCIM hoặc API nhà cung cấp | Tính nhất quán bất đồng bộ, session chưa được thu hồi |

### Không đồng nhất “đã gửi cấp quyền” với “đã có quyền”

Nếu connector trả timeout sau lệnh thêm role, tác động có thể đã xảy ra. Phải **readback** hoặc truy vấn kết quả tương ứng trước khi retry gây duplicate hoặc cấp ngoài scope. Khi cấp quyền bất thành, workflow phải ghi trạng thái **FAILED/PARTIAL** thay vì báo Active giả.

## 14. Thu hồi JIT: phải chặn được action chứ không chỉ xóa bản ghi

Thu hồi là nơi hệ thống JIT thường bộc lộ lỗ hổng. Có ít nhất các việc khác nhau:

1. **Ngừng cấp grant mới:** eligibility hoặc policy không còn cho phép.
2. **Đánh dấu grant inactive:** broker không cho kích hoạt lại trên request cũ.
3. **Gỡ quyền ở hệ thống đích:** role binding, group membership, direct grant.
4. **Thu hồi session đặc quyền:** đóng PAM session hoặc session của ứng dụng.
5. **Xử lý OAuth access/refresh token:** ngăn sử dụng token theo khả năng và loại token.
6. **Vô hiệu credential máy:** secret, certificate hoặc API key gắn với grant.
7. **Chặn action ở PEP/RS:** cần thiết khi target có cache hoặc token còn hiệu lực.
8. **Readback và audit:** xác minh không còn đường thực thi quyền trái chính sách.

### JWT và session là ngoại lệ quan trọng

Một **JWT access token** được cấp khi grant Active có thể còn hợp lệ về chữ ký và exp sau khi role JIT hết hạn. Nếu API chỉ kiểm chữ ký/exp và tin role claim cũ, quyền thực tế vẫn có thể tiếp tục. Cần **TTL phù hợp, trạng thái quyền hiện hành, introspection, denylist hoặc cơ chế cập nhật** tùy kiến trúc.

**Thêm role vào SCIM group rồi gỡ group** chưa đủ chứng minh mọi ứng dụng đã thu hồi session/token. Ứng dụng có thể giữ local session và quyền cache. Với quyền nhạy cảm, mục tiêu là **request không còn được chấp nhận** từ mốc chính sách yêu cầu, chứ không chỉ “lệnh remove membership thành công”.

### Kiểm tra thu hồi

Một cách thực tế là đối soát:

- Grant ở broker có trạng thái **EXPIRED/REVOKED**.
- Target group/role không còn gán người đó.
- PEP từ chối action JIT khi không có grant Active.
- Các phiên đặc quyền được đóng hoặc chặn.
- Token/credential liên quan được xử lý trong giới hạn khả năng sản phẩm.
- Không còn direct grant hoặc local privilege tồn dư.
- Nếu tồn tại ngoại lệ, có owner, deadline và biện pháp giảm thiểu.

## 15. JIT trong RBAC, ABAC, PBAC và ReBAC

JIT không thay thế authorization model hiện tại.

### Với RBAC

**Role** mô tả nhóm permission. Người dùng có thể **eligible** cho role **DB_OPERATOR**, nhưng role chỉ **active** trong cửa sổ đã duyệt. Không nên cấp role **GLOBAL_ADMIN** nếu chỉ cần một permission trên một database.

### Với ABAC

**ABAC** kiểm tra điều kiện động: tenant, dự án, thời điểm, mức phân loại dữ liệu, trạng thái phiên và thiết bị. Grant Active là một thuộc tính/quan hệ policy, không phải căn cứ duy nhất.

### Với PBAC

Một **Policy-Based Access Control** engine có thể đánh giá điều kiện:

~~~text
permit request if
    identity.lifecycleState == ACTIVE
    and grant.status == ACTIVE
    and grant.subjectId == identity.id
    and grant.resourceId == request.resourceId
    and request.action in grant.allowedActions
    and grant.effectiveFrom <= trustedNow
    and trustedNow < grant.effectiveUntil
    and session.assuranceMeetsPolicy
    and resource.tenantId == identity.tenantId
    and noSeparationOfDutiesConflict
~~~

Đây là **giả mã**, không phải ngôn ngữ của một sản phẩm cụ thể. Kết quả Permit chỉ có nghĩa policy cho phép theo dữ liệu tin cậy tại thời điểm đánh giá.

### Với ReBAC

Grant có thể dựa trên quan hệ **onCallFor(service)** hoặc **incidentResponderFor(incident)**. Quan hệ phải có owner và thời hạn. Tránh để người dùng tự tạo quan hệ “tôi là on-call” nhằm vượt chính sách.

**RBAC quyết định tập chức năng, ABAC/ReBAC quyết định phạm vi và quan hệ, PBAC kết hợp các điều kiện; JIT giới hạn thời điểm và tiến trình kích hoạt.**

## 16. Tích hợp IdP, SSO, SCIM và OAuth

### IdP/SSO

IdP xác thực người dùng, có thể yêu cầu **phishing-resistant MFA** và cung cấp session/federation assertion. JIT broker dùng chứng cứ xác thực đáng tin cho việc kích hoạt nhưng **SSO login không tự cấp quyền admin**.

### SCIM và ứng dụng đích

SCIM thường đồng bộ user/group, có thể được dùng để **kích hoạt hoặc gỡ một group JIT** nếu service provider hỗ trợ. Tuy nhiên, tính năng xử lý group, độ trễ và ý nghĩa role tại SaaS phải được kiểm chứng.

**SCIM active=true/false** quản lý trạng thái user; không nên dùng để bật/tắt toàn bộ account nếu chỉ cần JIT một quyền hẹp. **SCIM User.groups thường read-only** trong core schema; cập nhật membership qua **Group.members** hoặc API vendor khi phù hợp.

### OAuth 2.0 / OIDC

OAuth access token có thể mang scope hoặc claim về quyền đã cấp; **OIDC ID token dùng cho client đăng nhập**, không phải API credential. JIT cần tính đến **scope/audience, token TTL, revocation và stale claims**. Không coi “token được phát khi role đang Active” là bảo đảm role vẫn Active ở request sau.

### Kiểm soát đường truy cập độc lập

Một tài khoản có thể có **SSH key, PAT, API key, local admin, VPN session, DB connection** không đi qua IdP/SCIM. Chúng phải nằm trong phạm vi rà soát và thu hồi, đặc biệt khi quyền JIT hoặc quan hệ JML kết thúc.

## 17. JIT cho cloud, Kubernetes, database và SaaS

Các nền tảng có cách biểu diễn quyền và thời hạn khác nhau. Không giả định một giải pháp JIT có thể dùng API giống nhau cho mọi đích.

| Môi trường | Ví dụ nhu cầu JIT | Kiểm soát then chốt |
|---|---|---|
| **Cloud IAM** | Kích hoạt role vận hành cho một project/subscription | Scope resource, TTL, session/token handling |
| **Kubernetes** | Sửa resource trong namespace trong incident | RoleBinding/ClusterRoleBinding, audit, tránh cluster-admin |
| **Database** | Chạy truy vấn sửa dữ liệu đã duyệt | DB role, proxy, câu lệnh/đối tượng được phép, connection lifecycle |
| **SaaS** | Kích hoạt admin role xử lý tenant | API/group mapping, local sessions, readback |
| **CI/CD** | Deploy production theo change | Pipeline identity, artifact integrity, approval, expiry |
| **Privileged SSH/RDP** | Vào host để xử lý sự cố | PAM session brokering, recording theo chính sách, command limits |
| **Data platform** | Export dataset nhạy cảm có hạn | Classification, masking, row/object authorization |

### Kubernetes: nguy cơ scope

Một kỹ sư cần sửa deployment trong **namespace payments**. Nếu cấp **cluster-admin** thì JIT có giới hạn 15 phút vẫn là quyền rất rộng. Nên cân nhắc Role/RoleBinding ở namespace, command proxy hoặc policy action cụ thể. Phải đánh giá các quyền có khả năng **leo thang** như tạo pod privileged, sửa RBAC hoặc đọc secrets, không chỉ tên role.

### Database: quyền tại phiên đang mở

Gỡ DB role khi hết hạn chưa chắc một kết nối hiện có ngay lập tức mất quyền theo mọi DBMS. Cần hiểu đặc tính **session, transaction, pool và cached authorization** của hệ thống đích và thiết kế thu hồi/đóng phiên phù hợp.

### Cloud credentials có hạn

Một token/certificate ngắn hạn có thể không hỗ trợ thu hồi per-token tức thì trong mọi nền tảng. Nếu cần cắt quyền khẩn cấp, phải có **biện pháp ở điểm thực thi**, chính sách phiên hoặc cắt resource access phù hợp, không hứa hẹn SLA thu hồi mà nền tảng không đáp ứng.

## 18. JIT access trong Joiner lifecycle

Joiner không nhất thiết cần ngay quyền đặc biệt. Nên phân tách:

- **Baseline access:** quyền tối thiểu để hoàn thành công việc hằng ngày.
- **JIT eligibility:** khả năng yêu cầu quyền đặc quyền khi có nghiệp vụ và đã đạt điều kiện.
- **JIT activation:** quyền tạm chỉ được bật khi có request hợp lệ.

### Quy trình Joiner

1. HRIS xác minh identity, quan hệ, vị trí và **effectiveAt**.
2. IAM/IGA chuẩn bị IdP account và quyền baseline theo RBAC/ABAC.
3. Người mới hoàn thành enrollment MFA/passkey và các điều kiện cần thiết.
4. Owner nghiệp vụ xác định **những quyền JIT có thể yêu cầu**, không mặc định kích hoạt hết.
5. PAM/PIM/JIT broker đồng bộ eligibility theo nguồn có thẩm quyền.
6. Chỉ khi request có mục đích thực, mới kích hoạt quyền theo chính sách.
7. Readback chứng minh việc cấp baseline và JIT riêng biệt là đúng.

### Trước ngày bắt đầu

Có thể chuẩn bị account/eligibility trước ngày bắt đầu, nhưng **không để người chưa có quan hệ hiệu lực thực thi action đặc quyền** nếu chính sách không cho phép. Việc “account đã provision” không phải giấy phép kích hoạt JIT trước effectiveAt.

## 19. JIT access trong Mover lifecycle

Mover thay đổi vai trò, bộ phận, dự án, tenant, cấp độ dữ liệu hoặc điều kiện tin cậy. Đây là nguồn rủi ro **privilege accumulation** nếu chỉ thêm eligibility mới mà không gỡ eligibility cũ.

Ví dụ Lan chuyển từ **Sales Operations** sang **Finance Analysis**.

| Loại quyền | Trước Mover | Sau Mover mong muốn |
|---|---|---|
| Baseline role | Sales-Reader | Finance-Reader |
| JIT eligibility | CRM-Export-Operator | Finance-Data-Operator nếu được duyệt |
| Active JIT grant | CRM export đến 17:00 | **Thu hồi sớm** nếu chức năng cũ không còn hợp lệ |
| SoD | Không được sửa phân quyền IAM | Vẫn giữ nguyên ràng buộc |
| MFA | Theo rủi ro Sales | Có thể tăng assurance khi Finance nhạy cảm |

### Các bước cần thực hiện

- Nhận **sự kiện Mover mới nhất** từ nguồn có thẩm quyền.
- Tính lại **desired eligibility** và các grant hiện Active.
- Gỡ eligibility của role cũ và xử lý **active grant** không còn căn cứ, không chờ tới exp nếu policy yêu cầu.
- Cập nhật group, role và permission tại đích qua connector.
- Kiểm tra token/session có scope và role cũ.
- Xem xét SoD khi cấp eligibility mới; không để một người vừa eligible hai vai trò xung đột mà không có kiểm soát.
- Đối soát action cũ bị từ chối và action mới đúng phạm vi được cho phép.

**Mover không chỉ đổi tên role trong IAM.** Một PAM session đã mở hoặc cloud credential đã phát trước Mover có thể tiếp tục sử dụng quyền; phải đưa vào kế hoạch thu hồi.

## 20. JIT access trong Leaver lifecycle

**Leaver** phải chấm dứt cả **eligibility** lẫn **active JIT grants**, đồng thời xử lý những session/credential đặc quyền đã phát.

### Runbook theo lớp

| Lớp | Hành động | Bằng chứng cần xác minh |
|---|---|---|
| **HRIS/IGA** | Xác minh người, relationshipId, effectiveAt và loại Leaver | Sự kiện có thẩm quyền, version |
| **Eligibility** | Gỡ tư cách kích hoạt JIT trong từng hệ thống | Không thể request/kích hoạt grant mới |
| **Active grant** | Thu hồi mọi grant theo quan hệ hết hiệu lực | Grant state và target readback |
| **IdP/SSO** | Disable/chặn đăng nhập và xử lý session | Trạng thái IdP và các RP/SP quan trọng |
| **PAM/PIM** | Đóng privileged session, thu hồi temporary roles | Session state, role assignment |
| **SCIM/API** | Deprovision account/group/entitlement | Observed state tại ứng dụng |
| **Token/credential** | Xử lý access/refresh token, SSH key, PAT, certificate, secret | Resource server không còn chấp nhận |
| **Direct grants/local admin** | Gỡ quyền ngoài danh mục trung tâm | Inventory và readback |
| **Audit/reconciliation** | Kiểm tra không còn action đặc quyền | Finding/ticket, owner, deadline |

### Sai lầm thường gặp

Một nhân viên có quyền production-admin Active đến 18:00 nhưng nghỉ việc khẩn cấp lúc 16:30. Nếu JIT broker chỉ dựa vào exp=18:00 và không xử lý Leaver, người đó vẫn có thể thao tác trong 90 phút. **Sự kiện Leaver phải có khả năng làm mất hiệu lực grant trước hạn** theo policy.

### Một người có nhiều quan hệ

Nếu một người đồng thời là nhân viên và nhà thầu cho một dịch vụ được phép, kết thúc một quan hệ không nhất thiết buộc xóa mọi tài khoản của người đó. IAM phải xác định **quyền và grant gắn với relationshipId nào**; thu hồi đúng phạm vi nhưng không để một quan hệ khác vô tình kế thừa quyền của quan hệ đã kết thúc.

### Không dựa duy nhất vào broker

Dù broker ghi REVOKED, nếu hệ thống đích vẫn giữ role hoặc API vẫn chấp nhận token cũ, **Leaver chưa được xác minh là hoàn tất**. Phải mở exception có owner và biện pháp chặn bù trừ nếu không thể thu hồi ngay.

## 21. Rejoiner: không tự khôi phục quyền JIT lịch sử

Một người nghỉ việc rồi quay lại có thể được liên kết với **identity record gốc** vì lý do lịch sử, nhưng:

- Quan hệ mới cần được xác minh, có effectiveAt và role mới.
- Eligibility trước đây không tự mở lại.
- Những grant cũ phải giữ trạng thái expired/revoked, không được reuse approval.
- Authenticator, session và credential phải được đánh giá/enroll theo chính sách.
- Resource ownership và tenant phải được kiểm tra.
- SoD/JIT policy cần đánh giá theo nhiệm vụ mới, không sao chép toàn bộ quyền từ vai trò trước.
- Đối soát tài khoản đích để không hồi sinh local admin hoặc role đặc biệt.

**Same person không đồng nghĩa same authorization.** Đây là ranh giới quan trọng trong Joiner–Mover–Leaver.

## 22. JIT cho service account, bot và workload

Non-human identities có thể cần quyền ngắn hạn nhưng **không có HRIS person lifecycle trực tiếp**. JIT phải dựa trên **workload identity**, owner và nguồn có thẩm quyền khác.

### Ví dụ

Một pipeline CI/CD chạy deploy production sau khi change được duyệt. Pipeline dùng workload federation để nhận **credential/token ngắn hạn** chỉ cho service và môi trường cần deploy; không giữ global cloud-admin key trong CI secrets.

| Câu hỏi | Hướng giải quyết |
|---|---|
| **Workload nào?** | Dựa trên workload ID/attestation/registry đã xác minh |
| **Ai chịu trách nhiệm?** | Team owner, approver và escalation |
| **Action gì?** | deploy, artifact.read, secret.read theo phạm vi |
| **Khi nào?** | Chỉ trong workflow/change hợp lệ |
| **Credential thế nào?** | Ưu tiên managed identity/federation, token/cert ngắn hạn |
| **Tự thu hồi?** | Kết thúc job, hết lease hoặc khi policy chặn |
| **Sau owner Leaver?** | Chuyển owner, rà soát secret/grant và phê duyệt workload |
| **Đối soát?** | Theo client ID, role, scope, session và token |

**Không tạo một tài khoản nhân viên chung để bot đăng nhập SSO**, cũng không xóa mù quáng workload đang cần hoạt động khi nhân viên owner nghỉ. Chuyển owner và đánh giá lại quyền là hành động khác với Leaver của chính workload.

### JIT cho database maintenance job

Một job được phép đọc một số bảng hoặc chạy migration đã duyệt trong thời gian ngắn. Nếu credential của job lộ nhưng token chỉ dùng được cho đúng resource và cửa sổ hữu hạn, phạm vi rủi ro giảm. Tuy nhiên cần kiểm soát **credential issuance, log secrets, job execution context và quyền bên trong DB**.

## 23. JIT cho nhà thầu, đối tác và quyền được ủy quyền

Nhà thầu có thể chỉ cần quyền vào một hệ thống trong thời gian bảo trì, không nên có standing admin lâu dài.

### Điều kiện nên có

- **Sponsor/owner** của quan hệ nhà thầu và ngày hết hạn hợp đồng.
- **Identity proofing** và account/federation đáng tin theo rủi ro.
- **Eligibility** cho action/tài nguyên cần bảo trì, không cho mọi ứng dụng.
- **Approval và SoD** với người không phải chính nhà thầu.
- **MFA, device posture** theo chính sách doanh nghiệp.
- **Session monitoring/recording** khi phù hợp và tuân thủ quy định riêng tư.
- **Thời hạn ngắn**, tự đóng khi công việc hoàn tất hoặc hợp đồng hết hiệu lực.
- **Thu hồi đồng bộ** tại IdP, broker và hệ thống đích, xử lý credential và session còn tồn tại.

### Không chỉ dựa vào hợp đồng kết thúc

Hệ thống HRIS cho nhân viên có thể không chứa đầy đủ contractor/partner. IAM phải lấy sự kiện từ **hệ thống hợp đồng hoặc sponsor registry** phù hợp; nếu không, JIT eligibility của nhà thầu có thể tồn tại sau ngày chấm dứt mà không ai phát hiện.

## 24. Break-glass và quyền khẩn cấp

**Break-glass** là cơ chế truy cập khẩn cấp có kiểm soát khi quy trình bình thường không đáp ứng yêu cầu vận hành hoặc bị gián đoạn. Nó **không nên là cửa hậu Permit-all thường trực**.

### Khác JIT thông thường

| Tiêu chí | JIT thông thường | Break-glass |
|---|---|---|
| **Điều kiện** | Eligibility/approval/MFA theo quy trình chuẩn | Tình huống khẩn cấp được định nghĩa |
| **Phê duyệt** | Có thể trước activation | Có thể cơ chế thay thế được phê duyệt từ trước |
| **Scope** | Hẹp theo nhiệm vụ | Vẫn tối thiểu trong khả năng; đôi lúc rộng hơn |
| **Thời hạn** | Có hạn rõ | Có hạn, chấm dứt khi sự cố khép |
| **Monitoring** | Audit thông thường và cảnh báo rủi ro | Audit/alert và post-incident review tăng cường |
| **Credential** | Có thể được phát theo nhu cầu | Thường được bảo vệ sẵn, chỉ truy xuất theo thủ tục |
| **Review** | Rà soát định kỳ | Rà soát mỗi lần sử dụng và kiểm thử định kỳ |

Nếu IdP/PIM không hoạt động, một cơ chế break-glass phụ thuộc hoàn toàn vào cùng IdP/PIM có thể **không hữu ích**. Phải kiểm thử đường truy cập thực tế và bảo vệ bí mật trong vault hoặc biện pháp có độ tin cậy tương đương.

**Break-glass không làm vô hiệu SoD hay audit ở mọi hoàn cảnh.** Nếu bắt buộc nới kiểm soát, cần quy định rõ căn cứ, giám sát và yêu cầu giải trình sau sự kiện.

## 25. Các mối đe dọa và sai lầm thường gặp

| Sai lầm hoặc rủi ro | Hậu quả | Cách kiểm soát |
|---|---|---|
| **Eligible được xem như Active** | Có thể dùng quyền dù chưa xin phép | Enforce grant Active theo request cụ thể |
| **Standing global admin “để tiện”** | Khoảng thời gian/phạm vi rủi ro lớn | Scoped JIT và JEA |
| **Chọn duration tùy ý** | Quyền tồn tại vô hạn hoặc quá lâu | Max TTL theo action/risk |
| **Approval do người xin tự tạo** | Bypass SoD | Kiểm danh tính approver và tách nhiệm vụ |
| **Trust ticket ID do client khai** | Một ticket giả mở quyền prod | Kiểm tra ticket ở hệ thống có thẩm quyền |
| **Không kiểm MFA khi activate** | Attacker có session yếu tự nâng quyền | Step-up và session assurance |
| **Chỉ gỡ role, không đóng session** | Tiếp tục thao tác qua phiên cũ | Session revoke và target enforcement |
| **JWT role claim tồn dư** | Token vẫn cho phép sau expiry của grant | TTL/state checks/denylist theo khả năng |
| **PDP dùng thuộc tính HRIS cũ** | Mover/Leaver vẫn được Permit | Lifecycle event/version, cache invalidation |
| **Retry activation sau timeout** | Duplicate grants hoặc mở rộng quyền | Readback, idempotency, correlation |
| **Racing approval/revoke** | Job cũ mở lại quyền đã thu hồi | Version/fencing và kiểm tra trạng thái nguồn |
| **Connector có quyền quá rộng** | Bị lộ secret cho phép cấp admin hàng loạt | Least privilege, vault, rotation, audit |
| **Role binding sai tenant** | Truy cập tài nguyên khách hàng khác | Tenant/resource ID được xác minh |
| **JIT dựa UI, backend không chặn** | API trực tiếp bỏ qua expiry | PEP ở mọi điểm thực thi |
| **Không có owner khi grant thất bại** | Quyền dư kéo dài | Escalation, compensation và SLA |
| **Không quản lý local credential** | Đường truy cập ngoài SSO còn hoạt động | Inventory và revoke đa lớp |
| **Gia hạn tự động vô hạn** | JIT biến thành standing access | Renewal policy và cảnh báo |
| **Lạm dụng break-glass** | Bỏ qua approval bình thường | Phân biệt use case, alert và post-review |
| **Không phân biệt workload/user** | Bot có quyền của người thật | Workload identity và policy riêng |

**Ngắn hạn không đồng nghĩa an toàn tuyệt đối.** Một người có quyền global admin trong 5 phút vẫn có thể gây thiệt hại lớn nếu action không được giới hạn và giám sát.

## 26. Audit, evidence và các chỉ số đánh giá hiệu quả JIT

### Nên log những gì?

Một request có thể có nhiều sự kiện:

- **EligibilityGranted/EligibilityRevoked**: ai đủ điều kiện, do ai duyệt, từ nguồn nào.
- **ActivationRequested**: subject, resource, action, purpose, requestedDuration.
- **StepUpCompleted**: bằng chứng assurance đã được IdP/PEP xác minh.
- **ActivationApproved/Denied**: approver, policy version và lý do.
- **GrantActivated**: target ID, scope, actual effectiveFrom/Until, readback.
- **PrivilegedActionExecuted**: action, resource, correlation ID và kết quả.
- **GrantExpired/Revoked**: trigger, timestamp, actor.
- **TargetRevocationObserved**: bằng chứng quyền đã bị gỡ/chặn.
- **ReconciliationFinding**: chênh lệch, mức rủi ro, owner, deadline.
- **Exception/BreakGlassUsed**: lý do, mức giám sát và review sau sử dụng.

Một bản ghi audit minh họa:

~~~json
{
  "eventId": "jit-audit-20261123-052",
  "grantId": "grant-6f13",
  "subjectId": "person-2046",
  "relationshipId": "employment-2046-v1",
  "targetId": "service-payments",
  "action": "service.restart",
  "policyVersion": "jit-prod-v4",
  "decision": "PERMIT",
  "grantState": "ACTIVE",
  "decisionAt": "2026-11-23T09:06:00+07:00",
  "expiresAt": "2026-11-23T09:36:00+07:00",
  "correlationId": "req-441d",
  "observedTargetState": "SCOPED_ROLE_ACTIVE",
  "purposeRef": "INC-2026-1427"
}
~~~

Đây là **schema nội bộ minh họa**, không phải chuẩn dùng chung của mọi công cụ. Không ghi **password, bearer token, refresh token, private key, recovery code hay nội dung phiên chứa dữ liệu nhạy cảm** vào log phổ thông. Recording phiên đặc quyền nếu dùng phải tuân thủ chính sách phân quyền, retention và riêng tư.

### Các chỉ số JIT hữu ích

| Chỉ số | Đo lường | Ý nghĩa |
|---|---|---|
| **Standing privileged accounts** | Số tài khoản giữ quyền admin thường trực | Rủi ro đặc quyền tồn tại liên tục |
| **Eligible vs Active grants** | Bao nhiêu eligible, bao nhiêu Active đúng hạn | Mức sử dụng và phạm vi tiềm năng |
| **Median activation duration** | Thời gian thực Active của grant | Phát hiện grant quá dài |
| **Unused activation rate** | Kích hoạt nhưng không dùng action | Eligibility/policy có thể quá rộng |
| **Approval bypass rate** | Ngoại lệ không qua approval bình thường | Cần phân loại break-glass và vi phạm |
| **Time to activate** | Từ request hợp lệ đến target ready | Trải nghiệm và hiệu quả vận hành |
| **Time to revoke** | Từ yêu cầu kết thúc đến target bị chặn | Đánh giá quyền tồn dư |
| **Expired-but-active findings** | Grant hết hạn nhưng quyền ở đích còn | Rủi ro nghiêm trọng |
| **Mover/Leaver revocation lag** | Độ trễ chặn quyền sau sự kiện JML | Cần cải thiện automation |
| **Scope violations** | Quyền đích vượt action/resource yêu cầu | Không đạt least privilege |
| **Orphan eligibility/grants** | Quyền thiếu owner, relationship hoặc purpose | Cần xử lý governance |
| **Emergency/break-glass usage** | Lượt dùng và lý do | Chẩn đoán lệ thuộc fallback |
| **Audit coverage** | % hệ thống có evidence đầy đủ | Hạn chế kết luận tuân thủ |
| **Failed revocation aging** | Thời gian các finding chưa khép | Đo khả năng khắc phục |

Không đo thành công bằng **số lượng grant được cấp**. Mục tiêu là đúng quyền, đúng lúc, giảm standing privilege và chứng minh **quyền đã hết hiệu lực đúng hạn**.

## 27. Kiểm thử JIT: trường hợp Permit và Deny

Các ca kiểm thử phải bao gồm **điều kiện bị từ chối** và tình huống phân tán bất đồng bộ, không chỉ happy path.

| Kịch bản | Điều kiện | Kết quả mong đợi |
|---|---|---|
| Eligible, đúng task | Active employee, approval/MFA hợp lệ, scope hẹp | Kích hoạt trong TTL đã duyệt |
| Not eligible | User không thuộc danh sách đủ điều kiện | DENY |
| Chưa đạt MFA | Phiên không đủ assurance | REQUIRE_STEP_UP hoặc từ chối |
| Self-approval | Người xin cũng là approver trong rule cấm | DENY |
| Sai tenant | Request action trên tài nguyên tenant khác | DENY |
| Quá max duration | Yêu cầu 24 giờ khi policy cho 1 giờ | DENY hoặc buộc điều chỉnh qua quy trình |
| Request đã hết hạn | Activation diễn ra sau mốc request validity | Không kích hoạt |
| Grant hết hạn | Request action tại effectiveUntil | DENY |
| Mover xảy ra giữa cửa sổ | Role cũ không còn hợp lệ | Thu hồi grant cũ/chặn action |
| Leaver khẩn cấp | Nhân viên nghỉ trước khi TTL kết thúc | Thu hồi ngay theo SLA và verify |
| Token cũ còn hạn | JWT chứa role JIT trước đó | RS không tiếp tục Permit trái policy |
| PAM session mở | Role bị thu hồi khi session chưa đóng | Session bị đóng hoặc action bị chặn |
| Activation timeout | API đích đã cấp nhưng response mất | Readback, không duplicate blind retry |
| Revocation timeout | Không biết đã gỡ role chưa | Readback và escalation |
| Event đến sai thứ tự | Job activation cũ chạy sau Leaver | Bị version/fencing chặn |
| Broker/PDP unavailable | Không thể xác minh điều kiện | Không tự cho grant nhạy cảm |
| Break-glass | Quy trình chuẩn không khả dụng, emergency hợp lệ | Chỉ đường đặc biệt đã kiểm soát, audit |
| Bot owner Leaver | Workload còn hợp lệ, owner cũ hết quan hệ | Chuyển owner và rà soát, không mở quyền vô chủ |
| Scope tài nguyên bị thay | Resource được chuyển tenant/project | Không dùng grant cũ để vượt scope mới |

### Tầng kiểm thử

1. **Policy unit tests** cho eligibility, approval, SoD, TTL.
2. **Integration tests** với IdP/MFA, HRIS/JML, broker, SCIM/API và target.
3. **Conformance/negative tests** cho expired/disabled user, cross-tenant và direct API call.
4. **Race tests** cho activation cạnh tranh với revoke/Leaver.
5. **Session/token tests** cho credential còn sống sau expiry grant.
6. **Failure injection** cho timeout, 429, 5xx, cache stale và connector unavailable.
7. **Audit tests** cho mối nối request–grant–action–revoke–readback.
8. **Disaster recovery tests** cho break-glass và việc ngừng quyền sau sự cố.

**Tạo grant và chờ đến khi hết TTL mà không thử gọi action sau đó không đủ để chứng minh thu hồi.**

## 28. Runbook xử lý sự cố khi JIT không kích hoạt hoặc không thu hồi

### Nhánh A — Không kích hoạt được

1. Kiểm tra **identityId/relationshipId** và trạng thái nguồn JML.
2. Xác minh user **eligible** cho action/resource thực sự cần.
3. Kiểm tra **IdP/MFA, session assurance, approval, SoD và ticket**.
4. Xem broker đã trả decision gì, theo **policy version** nào.
5. Nếu decision Permit nhưng chưa Active, kiểm tra connector, tenant, role mapping và error.
6. Nếu timeout, đọc target trước khi retry.
7. Nếu quyền đã Active tại đích nhưng vẫn 403, kiểm tra action/resource scope, stale session/token và local authorization.
8. Không sửa lỗi bằng cách gán standing global-admin.

### Nhánh B — Quyền không được thu hồi đúng hạn

1. Ưu tiên **chặn action rủi ro** tại điểm thực thi nếu có thể.
2. Xác định grant, target resource, session/token liên quan và **effectiveUntil/revoke trigger**.
3. Kiểm tra broker đã chuyển trạng thái hay chưa và connector có thực hiện lệnh gỡ đúng tenant không.
4. Readback role/group/direct grants tại target.
5. Kiểm tra phiên PAM/ứng dụng và token có claim/quyền cũ.
6. Áp biện pháp thu hồi bổ sung phù hợp; với token tự chứa phải hiểu giới hạn revocation thực tế.
7. Tạo finding có **owner, risk, SLA, workaround, correlation ID và evidence**.
8. Chỉ đóng khi không còn action trái policy trong phạm vi xác minh.

### Nhánh C — Leaver vẫn có thể dùng quyền JIT

Đây là sự cố cần ưu tiên theo rủi ro. Kiểm tra ngay **identity disable, eligibility, Active grants, PAM sessions, app sessions, access tokens, local credentials và SoD**. Không đợi tới lịch dọn grant hàng đêm nếu chính sách cần thu hồi tức thời.

## 29. Tình huống xuyên suốt: JIT qua Joiner–Mover–Leaver

Giả sử **Lan** được tuyển vào đội vận hành hệ thống, sau đó chuyển sang Finance rồi nghỉ việc. Công ty có IdP dùng MFA, IGA, JIT broker và một ứng dụng SaaS được provision bằng SCIM.

### Giai đoạn 1 — Joiner

HRIS phát sự kiện Joiner với **personId=person-2046**, relationshipId và ngày bắt đầu. IAM tạo account IdP, hoàn thành enrollment/security key và cấp quyền đọc log thông thường. Lan được gán **eligibility** để xin **service.restart** cho các dịch vụ thuộc đội vận hành, nhưng **không có standing production-admin**.

### Giai đoạn 2 — Kích hoạt theo incident

Khi service-payments lỗi, Lan tạo incident và yêu cầu quyền restart trong 30 phút. Broker xác minh account active, eligibility, ticket, MFA và approval. Grant được kích hoạt trên đúng service. Lan restart dịch vụ, API ghi audit gồm **subject, action, resource, grant và outcome**.

Khi incident đóng sau 12 phút, broker thu hồi grant sớm. Nếu target session còn đang mở hoặc role vẫn tồn tại, hệ thống tiếp tục xử lý và chưa đánh dấu fully revoked.

### Giai đoạn 3 — Mover

Lan chuyển sang Finance. IAM gỡ eligibility restart của đội vận hành và hủy các grant còn Active thuộc vai trò cũ. Lan nhận quyền baseline Finance và có thể eligible cho một quyền export báo cáo có hạn theo policy mới. Một token chứa claim Ops cũ không được dùng để tiếp tục restart nếu resource server thực thi trạng thái mới đúng cách.

### Giai đoạn 4 — Leaver khẩn cấp

HRIS phát Leaver hiệu lực ngay. IdP chặn login, JIT broker vô hiệu toàn bộ eligibility và grant thuộc quan hệ kết thúc. SCIM/API deprovision account và nhóm. Đội IAM còn kiểm tra phiên PAM, token, key hoặc local admin được cấp trực tiếp. Một target SaaS chưa gỡ quyền do connector lỗi 429 phải được đưa vào **PARTIAL**, retry có backoff và áp biện pháp chặn trong thời gian chờ.

### Giai đoạn 5 — Rejoiner

Nếu Lan quay lại ở một đơn vị khác, IAM có thể dùng identityId cũ để nối lịch sử nhưng phải xác minh **quan hệ mới và chính sách hiện hành**. Eligibility Ops, approval incident và grant cũ không tự trở lại. Quyền JIT mới phải được cấp từ nhiệm vụ hiện tại.

### Bài học rút ra

**JIT không chỉ là “bật admin vài phút”.** Đó là một vòng đời **request → evaluate → approve → activate → enforce → expire/revoke → verify**, phụ thuộc tình trạng danh tính, scope quyền, phiên/token và quyền thực tế tại hệ thống đích.

## 30. Checklist triển khai JIT access an toàn

1. **Định nghĩa đúng:** đã phân biệt JIT access, JIT provisioning, JEA, PAM/PIM và break-glass?
2. **Identity:** subjectId/relationshipId có nguồn tin cậy, không dựa email dễ tái sử dụng?
3. **Baseline vs eligible:** đã tách quyền thường trực tối thiểu với tư cách được yêu cầu JIT?
4. **Eligible vs Active:** API không cho dùng quyền chỉ vì user eligible?
5. **Action catalog:** quyền được mô tả bằng action nghiệp vụ và resource cụ thể?
6. **Scope:** có giới hạn tenant, project, namespace, environment, dataset hoặc lệnh?
7. **Time:** có effectiveFrom/effectiveUntil, maximum TTL, expiry và quy tắc gia hạn?
8. **MFA:** quyền nhạy cảm có step-up hoặc phishing-resistant authentication khi policy yêu cầu?
9. **Approval:** có xác minh approver, SoD, ticket, purpose và risk?
10. **Grant ID:** request/grant có ID riêng, correlation và version để tránh retry trùng?
11. **Provisioning:** connector/PAM/SCIM/API có cấp đúng quyền ở đích, có readback?
12. **Enforcement:** PEP/backend có kiểm grant ACTIVE, scope và time tại action thật?
13. **Session:** có xử lý privileged session sau khi grant hết hạn/thu hồi?
14. **Token:** JWT/opaque token, refresh token, cache permission có chiến lược chặn quyền tồn dư?
15. **Joiner:** không kích hoạt trước ngày và điều kiện có hiệu lực?
16. **Mover:** có gỡ eligibility cũ và Active grants không còn căn cứ?
17. **Leaver:** đã ngừng cấp mới, thu hồi grant, phiên, token và credential độc lập?
18. **Rejoiner:** không tự khôi phục eligibility/approval/grant lịch sử?
19. **Non-human:** workload có owner, credential ngắn hạn, scope và lifecycle riêng?
20. **Contractor:** thời hạn hợp đồng và sponsor được đưa vào policy?
21. **Break-glass:** quy trình khẩn cấp có kiểm soát, alert và post-review?
22. **SoD:** người xin không tự phê duyệt hoặc sở hữu quyền xung đột ngoài policy?
23. **Failure cases:** có xử lý timeout, rate limit, retry, event sai thứ tự và partial revoke?
24. **Testing:** đã thử expired grant, stale token, Leaver, cross-tenant và API bypass?
25. **Audit:** có thể nối request, approval, grant, action, revoke và readback?
26. **Metrics:** có đo standing privilege, time-to-activate, time-to-revoke và expired-but-active?
27. **Reconciliation:** đã xác minh **quyền thực tế** bị chặn, không chỉ cập nhật trạng thái broker?

### Ghi nhớ

**Just-in-time access là cấp hoặc kích hoạt đúng quyền, đúng tài nguyên, đúng thời điểm và trong thời hạn ngắn đủ cho nhiệm vụ, thay vì duy trì đặc quyền thường trực.** Thiết kế JIT phải phân biệt **eligible** và **active grant**, áp **MFA/step-up, approval, SoD, scope, TTL**, theo dõi **session/token** và đối soát trạng thái tại điểm thực thi. Trong quản lý **Joiner–Mover–Leaver**, JIT chỉ thực sự đạt **Least Privilege** khi quyền cũ bị thu hồi sau Mover hoặc Leaver, grant hết hạn không còn cho phép hành động, và các đường truy cập ngoài **IdP/SSO/SCIM** cũng được kiểm tra để ngăn **quyền truy cập tồn dư**.
