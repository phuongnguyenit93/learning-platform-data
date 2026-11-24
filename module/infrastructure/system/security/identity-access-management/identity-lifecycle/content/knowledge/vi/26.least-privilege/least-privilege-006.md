# Temporary access trong IAM: cấp quyền tạm thời theo Least Privilege

> **Chương:** Least privilege
>
> **Bài:** Temporary access
>
> **Module:** SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE
>
> **Ngữ cảnh:** Quản lý vòng đời danh tính theo Joiner–Mover–Leaver (JML), từ xác minh, tạo tài khoản, cấp quyền đến thay đổi vai trò và thu hồi. Bài học kết nối IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, kiểm toán và việc giảm quyền truy cập tồn dư.

## 1. Temporary access là gì?

Một kỹ sư cần khởi động lại dịch vụ thanh toán production trong 30 phút. Nếu được cấp quyền quản trị toàn hệ thống vô thời hạn, tài khoản tiếp tục có khả năng thay đổi production sau khi sự cố kết thúc. Một phiên bị chiếm hoặc credential bị lộ vào ngày hôm sau có thể khiến quyền không còn cần thiết bị lạm dụng.

**Temporary access (truy cập tạm thời)** là việc cấp một tập quyền có **mục đích, phạm vi, điều kiện và thời gian sử dụng giới hạn**, theo một quy trình có thể kiểm chứng từ yêu cầu đến thu hồi. Nó là một cách triển khai nguyên tắc **Least Privilege**: chỉ trao quyền cần dùng, cho chủ thể phù hợp, trên tài nguyên phù hợp và trong thời gian thật sự có căn cứ.

Một grant tạm thời phải trả lời được:

- **Ai** nhận quyền: nhân viên, đối tác, quản trị viên hay workload?
- **Được làm gì:** đọc log, thay cấu hình, duyệt giao dịch hay truy xuất dữ liệu?
- **Trên tài nguyên nào:** service, project, database, tenant, file hay record cụ thể?
- **Vì sao:** nhiệm vụ, ticket, đợt kiểm toán hoặc sự cố được xác minh?
- **Từ khi nào đến khi nào:** thời điểm hiệu lực và hết hạn được xác định rõ?
- **Ai phê duyệt:** có đúng thẩm quyền và tách trách nhiệm hay không?
- **Hệ thống nào thực thi:** quyền có được cấp đúng ở target không?
- **Khi kết thúc:** role, session, token, API key, direct grant và các đường phụ có bị chặn?
- **Bằng chứng:** có readback hoặc kiểm tra hành vi xác nhận quyền đã mất hiệu lực?

### 1.1. Ví dụ mở đầu

Nhân viên An có quyền thường trực đọc log staging. Trong sự cố INC-2841, An cần quyền khởi động lại duy nhất dịch vụ payment-api ở tenant A.

**Thiết kế sai:** thêm An vào nhóm global-admin, dự định cuối ngày nhớ gỡ.

**Thiết kế tốt hơn:** yêu cầu quyền theo ticket, kiểm tra An đang active và được giao nhiệm vụ, áp dụng phê duyệt phù hợp, kích hoạt đúng hành động restart trên đúng service trong tối đa 30 phút, thu hồi sớm khi ticket đóng và xác minh target không còn cho phép restart.

Quyền tạm không nhất thiết là quyền admin. Nó cũng có thể là quyền xem một tập hồ sơ khách hàng để điều tra, quyền tải một báo cáo trong cuộc kiểm toán hoặc quyền của bot khi chạy một job trong vài phút.

## 2. Least Privilege không chỉ có một chiều thời gian

Một grant ngắn hạn nhưng phạm vi là toàn bộ cloud organization vẫn rất nguy hiểm. Ngược lại, quyền hẹp nhưng tồn tại vô thời hạn cũng tạo bề mặt tấn công không cần thiết.

| Chiều least privilege | Câu hỏi | Ví dụ |
|---|---|---|
| Subject | Đúng người hoặc principal nào cần? | Kỹ sư trực ca, không phải toàn team |
| Action | Những hành động tối thiểu? | Restart service thay vì IAM admin |
| Resource | Tài nguyên nào? | Một service của project A |
| Tenant/environment | Giới hạn phạm vi nào? | Production tenant A |
| Duration | Quyền cần kéo dài bao lâu? | 30 phút thay vì nhiều ngày |
| Context | Điều kiện bổ sung nào? | MFA phù hợp, thiết bị đạt policy |
| Delegation | Có được cấp lại quyền? | Không được tạo role khác |
| Session/credential | Có đường truy cập phụ nào? | Phiên PAM có hạn và theo dõi |

Mục tiêu của temporary access là giảm **thời gian đặc quyền có hiệu lực**, đồng thời giảm **phạm vi đặc quyền** và đảm bảo khả năng chứng minh nó đã chấm dứt.

### 2.1. Standing privilege và eligible privilege

- **Standing privilege:** quyền đã được cấp sẵn, khả dụng liên tục ngay cả khi không có công việc cần dùng.
- **Eligible privilege:** người dùng có tư cách yêu cầu kích hoạt một vai trò theo chính sách. Eligibility không phải quyền thực thi đã active.
- **Activated privilege:** quyền có hiệu lực sau khi yêu cầu và điều kiện kích hoạt được xác nhận.
- **Just-in-Time (JIT) access:** kích hoạt khi cần, tự hết hoặc bị thu hồi theo điều kiện, thay vì cấp trước vô thời hạn.

Một người có thể eligible cho role production operator nhưng vẫn phải bị từ chối action production nếu role chưa active.

## 3. Phân biệt các khái niệm thường gặp

| Thuật ngữ | Trọng tâm | Không nên nhầm |
|---|---|---|
| Temporary access | Quyền có thời hạn/mục đích/scope | Chỉ một password tạm |
| JIT access | Kích hoạt quyền đúng lúc cần | JIT provisioning khi login SSO |
| JEA | Just Enough Administration: giới hạn năng lực thực hiện | Full admin có TTL ngắn |
| PAM | Privileged Access Management: vault, session, credential, approval, audit | Một lần MFA đơn lẻ |
| PIM | Privileged Identity Management: eligibility/activation đặc quyền | Role nghiệp vụ của mọi SaaS |
| Time-bound grant | Entitlement chỉ hợp lệ trong khoảng thời gian | Token có ngày hết hạn |
| Temporary session | Phiên có thời hạn | Toàn bộ entitlement đã bị revoke |
| Temporary credential | Token/secret/certificate sống ngắn | Tài khoản đã hết quyền ở mọi API |
| Break-glass | Luồng khẩn cấp có kiểm soát | Quyền admin thường trực không giám sát |
| Access review | Rà soát sự cần thiết của quyền | Cơ chế tự động expire grant |

**JIT access khác JIT provisioning.** Việc SaaS tạo account lúc người dùng SSO lần đầu không tự làm role của account ấy trở thành quyền tạm có kiểm soát.

## 4. Mô hình một grant Temporary access

Một grant có thể được mô tả bằng các thông tin tối thiểu:

~~~text
grant = {
  subjectId,
  subjectType,
  actionSet,
  resourceScope,
  reasonOrTicket,
  approvalEvidence,
  validFrom,
  validUntil,
  constraints,
  policyVersion,
  grantStatus
}
~~~

Ví dụ **dữ liệu giả lập**:

~~~json
{
  "grantId": "tmp-access-2026-006",
  "subjectId": "employee-1042",
  "subjectType": "USER",
  "actions": ["service.restart"],
  "resources": ["prod/tenant-a/payment-api"],
  "reason": "INC-2841",
  "approvedBy": "prod-duty-manager",
  "validFrom": "2026-11-23T09:00:00+07:00",
  "validUntil": "2026-11-23T09:30:00+07:00",
  "requiredAssurance": "corp-strong-auth",
  "policyVersion": "jit-service-v4",
  "status": "ACTIVE",
  "correlationId": "INC-2841"
}
~~~

Các trường chỉ minh họa, không phải schema chuẩn của nhà cung cấp IAM. Thông tin approvedBy phải đến từ một **quyết định phê duyệt được hệ thống xác minh**, không phải văn bản người xin quyền tự nhập vào biểu mẫu.

### 4.1. Grant ID khác account ID

Cùng một employee có thể có nhiều grant tạm theo các ticket khác nhau. Mỗi grant cần định danh và lịch sử riêng để có thể:

1. Thu hồi đúng grant.
2. Xác minh không nhầm quyền thường trực với quyền tạm.
3. Phân biệt các thời hạn và approval.
4. Xác định một grant bị retry trùng.
5. Phục dựng ai đã dùng quyền nào trong khoảng thời gian nào.

### 4.2. Trạng thái được quản lý

~~~mermaid
stateDiagram-v2
    [*] --> REQUESTED
    REQUESTED --> REJECTED: Không đủ điều kiện
    REQUESTED --> APPROVED: Phê duyệt hợp lệ
    APPROVED --> ACTIVE: Kích hoạt và readback
    APPROVED --> CANCELLED: Hủy trước khi dùng
    ACTIVE --> EXPIRING: Đến thời hạn
    ACTIVE --> REVOKING: Revoke sớm
    EXPIRING --> VERIFYING: Chặn quyền
    REVOKING --> VERIFYING: Chặn quyền
    VERIFYING --> VERIFIED_CLOSED: Đối soát PASS
    VERIFYING --> PARTIAL: Còn đường truy cập
    PARTIAL --> VERIFYING: Khắc phục
    REJECTED --> [*]
    CANCELLED --> [*]
    VERIFIED_CLOSED --> [*]
~~~

Tên trạng thái là mô hình giáo dục. Một entry mang trạng thái EXPIRED trong hệ quản lý yêu cầu **không đủ chứng minh** hệ thống đích đã hết quyền.

## 5. Luồng request–approve–activate–expire–verify

~~~mermaid
flowchart TD
    REQ[Subject yêu cầu truy cập tạm] --> CHK[Kiểm tra identity, ticket, scope]
    CHK --> ELIG{Eligible và SoD phù hợp?}
    ELIG -- Không --> NO[Từ chối]
    ELIG -- Có --> APP[Phê duyệt hoặc chính sách tự duyệt]
    APP --> ACT[Kích hoạt grant / session]
    ACT --> RB[Readback quyền được cấp]
    RB --> USE[Sử dụng theo action và scope]
    USE --> END{Hết hạn / kết thúc / revoke?}
    END -- Chưa --> USE
    END -- Có --> REV[Thu hồi grant + đường liên quan]
    REV --> VR[Kiểm tra effective access]
    VR --> OK{Bằng chứng đủ?}
    OK -- Có --> CL[VERIFIED_CLOSED]
    OK -- Chưa --> ES[PARTIAL / escalation]
    ES --> VR
~~~

Ở mỗi bước, phải có trách nhiệm rõ:

| Giai đoạn | Đầu vào | Bằng chứng đầu ra |
|---|---|---|
| Request | Subject, action, resource, justification, duration | Request ID, identity đã xác minh |
| Eligibility | HR/IAM status, role, tenant, risk | Quyết định đủ điều kiện |
| Approval | Chính sách, chủ tài nguyên/manager | Approver, scope và thời hạn được phê duyệt |
| Activation | Credential/session/grant target | Quyền thực tế đúng phạm vi |
| Use | Request trên tài nguyên | Nhật ký action/session phù hợp |
| Expiry/revoke | Deadline hoặc trigger chấm dứt | Grant không còn active theo policy |
| Verification | Readback và kiểm tra đường truy cập | VERIFIED hoặc PARTIAL có nguyên nhân |

Không đánh dấu hoàn thành nếu chỉ nhận HTTP 200 từ API revoke nhưng chưa xác minh target đã áp dụng.

## 6. Request phải gắn với mục đích cụ thể

Một yêu cầu hợp lệ không nên chỉ nói “cấp admin cho tôi”, mà phải cho thấy nhu cầu và phạm vi:

~~~text
Requester: employee-1042
Ticket: INC-2841
Task: Restart payment-api để xử lý kết nối lỗi
Action: service.restart
Resource: prod/tenant-a/payment-api
Requested duration: 30 minutes
Approver: Production duty manager
Risk: Service availability
Evidence: Incident record đã được duyệt
~~~

Backend phải kiểm tra ID của incident và quyền của người duyệt từ nguồn đáng tin. Không tin dữ liệu client tự khai như approved=true, scope=global hoặc tenant=all.

### 6.1. Hạn chế quyền theo hành động

Với nhiệm vụ đọc log, permission phù hợp có thể là logs.read; không cần logs.delete, role.assign hoặc iam.policy.update. Với restart service, xem nền tảng có hỗ trợ permission chỉ restart đúng service hay không.

Nếu nền tảng chỉ cung cấp role rất rộng, cần đánh giá bù trừ: PAM session proxy, command allowlist, phê duyệt nâng cao, giám sát chặt và giới hạn thời gian, đồng thời ghi nhận rủi ro chưa xử lý.

### 6.2. Phạm vi resource

Quyền xem bảng báo cáo của một team không tự cho phép export toàn bộ khách hàng. Quyền đọc một database view không đồng nghĩa có thể đọc mọi bảng chứa dữ liệu cá nhân.

Temporary access phải xét **resource-level authorization**, không chỉ xem action hoặc OAuth scope.

## 7. Approval, Separation of Duties và trách nhiệm

Không phải quyền tạm nào cũng cần duyệt thủ công. Có thể tự phê duyệt theo chính sách cho nhiệm vụ ít rủi ro, trong khi quyền admin cần sự chấp thuận của người có thẩm quyền.

| Loại yêu cầu | Cách xét approval có thể phù hợp |
|---|---|
| Đọc log đã lọc của hệ thống ít nhạy cảm | Tự duyệt qua policy, có audit |
| Xem dữ liệu khách hàng cho ticket | Chủ tài nguyên/manager phê duyệt |
| Export dữ liệu nhạy cảm | Mục đích và scope cụ thể, approval phù hợp |
| Quản trị production | Trực ca/owner duyệt, MFA mạnh, log hành động |
| Sửa IAM policy hoặc grant role | Approval đặc quyền, SoD chặt và giám sát |
| Break-glass khẩn cấp | Cơ chế riêng có cảnh báo, hậu kiểm |

### 7.1. SoD ngăn tự cấp và tự che giấu

Một người không nên mặc định được tự yêu cầu, tự duyệt, tự kích hoạt rồi tự xác nhận/xóa dấu vết quyền admin của chính mình. Với đặc quyền cao, cần tách vai trò request, approval và audit.

Thời hạn ngắn không làm mất rủi ro **self-approval** hoặc **privilege escalation**.

### 7.2. Approval phải gắn với đúng request

Chữ ký/phê duyệt cho quyền logs.read không thể dùng lại để cấp iam.admin. Nếu scope, action, tenant hoặc duration thay đổi, approval cũ có thể không còn hợp lệ. Hệ thống phải so khớp request ID, approval ID, policy version và ngữ nghĩa entitlement.

### 7.3. Tránh approval giả

Một API không nên nhận JSON do người dùng gửi chứa approvedBy="director" rồi coi như đã duyệt. Việc phê duyệt phải nằm trong quy trình có danh tính người duyệt, thẩm quyền và audit riêng.

## 8. JIT activation, PIM và PAM

Khi user eligible yêu cầu role nhạy cảm, hệ thống có thể yêu cầu xác thực bổ sung, kiểm tra approver và kích hoạt trong khoảng ngắn.

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant P as Access Portal
    participant I as IdP / Policy / Approval
    participant T as Target / PAM
    participant A as Audit
    U->>P: Request action + resource + ticket
    P->>I: Verify eligibility, context, approval
    I-->>P: Approved with max duration
    P->>T: Activate targeted grant
    T-->>P: Operation response
    P->>T: Readback effective permissions
    T-->>P: Grant active in requested scope
    P->>A: Record ACTIVATED
    U->>T: Execute authorized action
    P->>T: Revoke at expiry or early close
    T-->>P: Revoke operation response
    P->>T: Readback
    T-->>P: Verified or remaining access
    P->>A: VERIFIED_CLOSED or PARTIAL
~~~

**PAM** có thể thêm credential vault, rotation, session recording và command controls. **PIM** có thể quản lý eligibility, activation và role assignments. Chi tiết phụ thuộc nhà cung cấp.

### 8.1. JEA giảm khả năng phá hoại

Temporary admin trong 15 phút vẫn nguy hiểm nếu quyền là toàn tổ chức. **Just Enough Administration** giới hạn những command/action thật sự được dùng, có thể theo phiên hoặc target. Nó bổ sung cho giới hạn thời gian chứ không thay thế.

### 8.2. Bảo đảm các đường truy cập được bao phủ

Nếu user kết thúc phiên PAM nhưng vẫn có SSH key cá nhân, local admin account hoặc database login trực tiếp, temporary access chưa thu hồi hết. Cần inventory và đối soát đường truy cập ngoài proxy/portal.

## 9. Thời điểm hiệu lực, TTL và ràng buộc thời gian

Một grant có thể chỉ hợp lệ trong khoảng:

~~~text
validFrom  = 2026-11-23T09:00:00+07:00
validUntil = 2026-11-23T09:30:00+07:00

Nếu now < validFrom: DENY
Nếu validFrom <= now < validUntil: xét thêm RBAC/ABAC/context
Nếu now >= validUntil: DENY
~~~

Cần dùng timestamp có timezone rõ ràng, đồng bộ đồng hồ, kiểm soát clock skew và xử lý các giới hạn bằng trusted time source.

### 9.1. Duration bắt đầu từ đâu?

Một approval có thể đến trước thời điểm kích hoạt. Phải quy định rõ TTL tính từ:

- Thời điểm yêu cầu;
- Thời điểm approval;
- Thời điểm activation thực tế;
- Hoặc một cửa sổ lịch cố định.

Nếu được duyệt 09:00 nhưng chỉ kích hoạt 11:00, không thể mặc định mọi hệ thống đều tính TTL từ 11:00. Cơ chế phải phù hợp policy đã duyệt.

### 9.2. Expiry trong portal khác expiry ở target

Ba mốc có thể khác nhau:

1. **Expected expiry:** policy yêu cầu kết thúc.
2. **Enforced expiry:** target thực sự chặn quyền.
3. **Verified expiry:** đã có readback/chứng cứ về việc chặn.

Nếu portal hiển thị EXPIRED lúc 09:30 nhưng SaaS còn chấp nhận quyền đến 09:35, đó là **5 phút quyền tồn dư**, cần đánh giá theo SLA và mức rủi ro.

### 9.3. Cache authorization decision

PDP có thể cache PERMIT. Nếu kết quả được cache một giờ nhưng grant chỉ có 30 phút, decision cũ có thể tiếp tục cho phép sau expiry. Cache phải được **giới hạn theo validUntil**, policy version, principal, resource, tenant và ngữ cảnh cần thiết, đồng thời invalidate khi revoke.

## 10. Scope đúng: subject, action, resource và tenant

Một permission không nên được định nghĩa chỉ bằng role. Cần xét action/resource cụ thể:

| Requested task | Grant hẹp | Grant không phù hợp |
|---|---|---|
| Chẩn đoán payment-api | service.logs.read trên payment-api | cloud.organization.admin |
| Restart payment-api | service.restart trên payment-api | restart mọi service trong cluster |
| Điều tra ticket | ticket.read với ticket ID được duyệt | crm.export.all |
| Đối soát hóa đơn | invoice.read trên tenant A | invoice.read mọi tenant |
| Xử lý một database migration | Chỉ schema và thao tác cần dùng | Database superuser vô thời hạn |
| Kiểm tra IAM policy | iam.policy.read trên scope được giao | iam.policy.write toàn organization |

### 10.1. Scope ở API chưa phải quyền trên mọi object

Access token có scope invoice.read không tự chứng minh user được đọc hóa đơn của mọi khách hàng. API phải kiểm tra tenant, owner, classification, RBAC/ABAC và các ràng buộc đặc thù.

### 10.2. Quyền tạo grant mới nguy hiểm hơn vẻ ngoài

Một grant tạm có action role.assign có thể tạo **quyền lâu dài** cho chính người dùng hoặc đồng nghiệp. Quyền document.share có thể tạo link tải dữ liệu không hạn. Do đó phải giới hạn delegation và quản lý **secondary grants/artefacts** phát sinh trong phiên.

### 10.3. SoD trong nghiệp vụ

Người vừa tạo hóa đơn có thể không được tự duyệt cùng hóa đơn dù đã được kích hoạt role approver tạm và qua MFA mạnh. Temporary privilege không bỏ qua quy tắc separation of duties cấp giao dịch.

## 11. Kết thúc sớm khi điều kiện không còn đúng

Quyền phải được đánh giá lại hoặc thu hồi khi xảy ra trigger như:

- Ticket đóng hoặc nhiệm vụ hoàn tất.
- Approval bị thu hồi bởi người có thẩm quyền.
- User chuyển vai trò (Mover) hoặc nghỉ việc (Leaver).
- Tài khoản bị suspended, thiết bị bị báo compromised.
- Project hoặc resource được chuyển owner/tenant.
- Phát hiện session bất thường hoặc credential bị lộ.
- Workload ngừng, thay môi trường hoặc thay chủ sở hữu.
- Grant hết hạn theo policy.

**Không chờ TTL khi căn cứ cấp quyền đã chấm dứt sớm hơn** và chính sách yêu cầu revoke.

### 11.1. Thu hồi nhiều lớp

| Đường truy cập | Cần kiểm tra khi revoke |
|---|---|
| JIT role/entitlement | Role đã deactivated hoặc bị hệ thống enforcement từ chối |
| IdP group/claim | Membership thay đổi; token mang claim cũ xử lý đúng |
| SaaS local permission | Role cấp trực tiếp có được thu hồi không |
| PAM session | Phiên/command còn thực hiện được không |
| Access/refresh token | Token còn hạn được xử lý theo chính sách ra sao |
| SSH key/certificate | Trust, TTL, certificate revocation hoặc host policy |
| API key/secret | Credential do user/workload tạo có bị giới hạn/thu hồi |
| Share link | Link còn mở sau khi grant hết không |
| Cloud resource policy | Grants trực tiếp và kế thừa còn hiệu lực không |
| Workload trust | Service principal và bindings còn hợp lệ không |

### 11.2. Trạng thái PARTIAL khi không thể xác minh

Một kết quả revoke trả 200, nhưng target vẫn báo role còn active, không được ghi VERIFIED_CLOSED. Giữ trạng thái PARTIAL hoặc PENDING_VERIFICATION, gắn owner, deadline và biện pháp containment.

### 11.3. Readback quyền hiệu lực

Readback có thể gồm đọc role từ API đích, kiểm tra group membership, đối soát session/credential, hoặc chạy một negative test được phép. Một HTTP 403 trên duy nhất một endpoint chưa chứng minh mọi đường truy cập đã bị chặn.

## 12. IdP, SSO, OIDC/OAuth và giới hạn của token expiration

Temporary access thường kết hợp hệ thống identity tập trung với ứng dụng đích:

~~~mermaid
flowchart LR
    HR[HRIS / Lifecycle] --> IAM[IAM: Temporary Grants]
    U[User] --> IDP[IdP / SSO / MFA]
    IDP --> APP[Application / Resource Server]
    IAM --> IDP
    IAM --> TARGET[SaaS / PAM / Cloud IAM]
    APP --> POLICY[RBAC / ABAC Enforcement]
    TARGET --> POLICY
    POLICY --> DATA[(Protected Resources)]
    IAM --> AUDIT[Audit / Reconciliation]
~~~

### 12.1. Token còn hạn sau khi grant hết

~~~text
Temporary grant: 09:00 đến 09:30
Access token: issued 09:20, expires 10:20
~~~

Nếu Resource Server chỉ kiểm tra chữ ký và exp, có thể nó vẫn tin role đã nhúng trong token đến 10:20. **Token validity khác entitlement validity.**

Một giải pháp có thể kết hợp:

- Access token TTL phù hợp và không vượt quyền đã hết khi hỗ trợ.
- Kiểm tra grant validUntil tại API/PDP.
- Introspection, trạng thái account/entitlement hoặc revocation theo hợp đồng AS/RS.
- Invalidate session, refresh token hoặc áp dụng denylist phù hợp.
- Tái cấp token không còn claim quyền sau expiry.
- Object-level authorization vẫn hoạt động dù token hợp lệ.

Không mặc định logout hay disable user ở IdP tự làm mọi session/token SaaS hết hiệu lực tức thời.

### 12.2. Độ mới MFA khác độ mới quyền

Trong OIDC, auth_time hoặc thông tin acr/amr có thể giúp đánh giá ngữ cảnh xác thực theo hợp đồng issuer. Nhưng MFA vừa thực hiện **không kéo dài validUntil**, không chứng minh role vẫn hợp lệ và không thay quyền trên resource.

### 12.3. Chặn đúng API audience

Một access token dành cho API báo cáo không nên được chấp nhận tại API thanh toán chỉ vì cùng IdP. Resource Server phải kiểm tra issuer, audience, thời hạn và token profile, rồi mới đến policy tạm thời và quyền trên object.

## 13. SCIM, provisioning và quyền tạm

SCIM hỗ trợ provisioning User/Group/membership theo khả năng của SaaS. Nó có thể được dùng để:

1. Thêm user vào một group khi activation.
2. Gỡ user khỏi group khi expiry/revocation.
3. Vô hiệu hóa account khi Leaver.
4. Đối soát trạng thái User/Group tại target.

Nhưng **SCIM không tự định nghĩa một workflow JIT permission đầy đủ**, không tự áp approval/TTL và không tự đảm bảo session, token, local role hoặc direct ACL bị thu hồi.

### 13.1. Độ trễ đồng bộ

Giả sử IAM gửi remove group lúc 09:30 nhưng SaaS chỉ cập nhật role 09:33. Quyền có thể tồn tại trong cửa sổ đó. Phải kiểm tra cách SaaS đánh giá membership, cache/session và khi nào quyền thật sự bị chặn.

### 13.2. SCIM và JIT provisioning

JIT provisioning có thể tạo account khi user đăng nhập lần đầu; nó không phải temporary access. Một account được tạo JIT có thể giữ role lâu dài nếu không có lifecycle/deprovisioning riêng.

## 14. RBAC và ABAC cho Time-bound Access

RBAC có thể quản lý role được kích hoạt tạm:

~~~text
subject = employee-1042
role = prod.operator
resourceScope = prod/tenant-a/payment-api
activeFrom = 09:00
activeUntil = 09:30
~~~

Không mặc định mọi hệ thống RBAC/SCIM group có thuộc tính expiresAt. Khi target không hỗ trợ expiry trực tiếp, cần automation remove và biện pháp bù trừ để hạn chế delayed revoke.

### 14.1. ABAC xét ngữ cảnh và thời hạn

~~~text
PERMIT nếu:
  subject.employmentStatus == ACTIVE
  AND subject.hasApprovedTemporaryGrant("service.restart")
  AND resource.id == "prod/tenant-a/payment-api"
  AND now >= grant.validFrom
  AND now < grant.validUntil
  AND session.assurance meets requiredPolicy
  AND ticket.status IN ["OPEN", "IN_PROGRESS"]
  AND resource.tenantId == subject.allowedTenantId
~~~

Dữ liệu employment status, approval, ticket, resource và thời gian phải lấy từ nguồn tin cậy. Không tin client tự khai ticket vẫn mở hoặc approval đã hợp lệ.

### 14.2. Attribute freshness

Nếu HRIS cập nhật Leaver hoặc ticket đóng mà PDP vẫn dùng trạng thái cũ quá thời hạn rủi ro, grant có thể bị dùng sau khi không còn căn cứ. Do đó độ mới của thuộc tính và temporary access phải thiết kế cùng nhau.

## 15. Pseudocode kiểm tra grant tại thời điểm request

~~~text
function authorizeTemporaryAction(request):
    principal = verifyTrustedPrincipalAndSession(request)
    if principal is NONE:
        return UNAUTHENTICATED

    resource = loadTrustedResource(request.resourceId)
    if resource is NONE:
        return NOT_FOUND

    if principal.currentEmploymentStatus != ACTIVE:
        return DENY

    grant = trustedGrantStore.findMatching(
        principal.id, request.action, resource.id, resource.tenantId
    )

    if grant is NONE or grant.status != ACTIVE:
        return DENY

    now = trustedClock.now()
    if now < grant.validFrom or now >= grant.validUntil:
        return DENY

    if not grant.approvalStillValid:
        return DENY

    if not subjectMeetsAuthenticationAndDevicePolicy(principal):
        return REQUIRE_STEP_UP_OR_DENY

    if not evaluateRBAC_ABAC_SoD(principal, request.action, resource):
        return DENY

    return PERMIT_WITH_AUDIT_CONTEXT
~~~

Đây là mã giả, không thay implementation production. Hệ thống thực còn phải giải quyết consistency, token binding, cache, quyền phái sinh, TOCTOU và tách quyền cấp grant khỏi quyền sử dụng grant.

### 15.1. TOCTOU tại đúng thời hạn

Nếu API kiểm tra quyền lúc 09:29:59 rồi thực thi một lệnh nguy hiểm lúc 09:30:05, cần chính sách rõ về thời điểm quyền phải còn hợp lệ. Với thay đổi không thể đảo ngược, cân nhắc kiểm tra trong cùng transaction hoặc cơ chế version/fencing phù hợp.

### 15.2. Quyền cấp lại

Nếu user đang có quyền role.assign trong phiên tạm, cần kiểm tra grant mới không được vượt thời hạn, scope hoặc nguồn thẩm quyền cho phép. Cách đơn giản là **không cấp quyền delegation** khi nhiệm vụ không yêu cầu.

## 16. Break-glass: truy cập khẩn cấp có kiểm soát

**Break-glass** là cơ chế dùng khi hệ thống cấp quyền/xác thực thông thường bị gián đoạn hoặc tình huống khẩn cấp cần đường tiếp cận đã chuẩn bị từ trước.

Một cơ chế hợp lệ cần:

- Điều kiện kích hoạt và những tài nguyên được bảo vệ xác định.
- Account/credential được bảo vệ; tránh dùng chung bừa bãi.
- Cảnh báo ngay tới người độc lập và hậu kiểm chặt.
- Session/command evidence nếu hạ tầng cho phép.
- Giới hạn hành động và thời gian khi có thể.
- Rotation/revoke credential, session cleanup sau sử dụng.
- Kiểm thử khả năng hoạt động trong tình huống hệ thống chính outage.
- Chính sách phân biệt break-glass thật với ngoại lệ bảo trì thông thường.

### 16.1. Tránh phụ thuộc vòng tròn

Nếu IdP/PAM chính đang outage, bắt break-glass phải gọi chính IdP/PAM đó để approve có thể khiến không ai sử dụng được. Cần thiết kế khả năng độc lập phù hợp nhưng vẫn đủ bảo vệ và khả năng audit.

### 16.2. Không cho break-glass thành backdoor

Một tài khoản emergency admin được dùng hằng ngày, không owner, không logging và không rotate là một đường đặc quyền thường trực rủi ro cao, không phải JIT access.

## 17. Temporary access trong Joiner lifecycle

Trong Joiner, nhân viên mới có thể cần một số quyền ngắn hạn cho onboarding. Chẳng hạn:

- Quyền thường trực: project.viewer theo nhiệm vụ được giao.
- Quyền tạm: project.import trong một buổi để chuyển dữ liệu.
- Quyền tạm phải kết thúc sau import hoặc hết hạn.
- Quyền viewer thường trực chỉ tồn tại khi còn nhu cầu công việc.

Quy trình:

1. HRIS xác minh danh tính, trạng thái và ngày bắt đầu.
2. IdP tạo account và yêu cầu MFA theo rủi ro.
3. IAM phân biệt baseline entitlements với temporary grants.
4. Xác nhận task, scope, approval và thời hạn.
5. Kích hoạt không trước ngày có hiệu lực.
6. Readback quyền được cấp.
7. Thu hồi đúng hạn và kiểm chứng quyền còn lại theo baseline.

**Sai lầm Joiner:** cấp full admin “tạm cho nhân viên mới” rồi không ai sở hữu việc gỡ.

## 18. Temporary access trong Mover lifecycle

Mover có thể là chuyển phòng ban, thay dự án, nhận trách nhiệm mới hoặc bàn giao công việc.

Ví dụ An chuyển Finance sang Operations:

| Quyền | Trước Mover | Sau Mover hợp lệ |
|---|---|---|
| Finance viewer | Cần cho việc cũ | Thu hồi |
| Operations viewer | Chưa có | Cấp theo nhiệm vụ mới |
| Finance handover read | Chưa có | Có thể cấp tạm trên vài tài liệu |
| Invoice approver | Có | Thu hồi khi không còn căn cứ |
| Production restart | Chưa có | JIT khi có task được duyệt |

### 18.1. Bàn giao không phải giữ toàn quyền cũ

Thay vì giữ nguyên role Finance trong một tháng, hãy xác định tài liệu/việc cần bàn giao, cấp quyền đọc tạm trên phạm vi đó với approval, TTL và readback.

### 18.2. Event đến sai thứ tự

Job Mover cũ có thể chạy sau một sự kiện Leaver. Không được tái kích hoạt group hay temporary grant chỉ vì event được nhận cuối. Dùng lifecycle version, effectiveAt, desired-state checks và retry idempotent để chống hồi sinh quyền.

## 19. Temporary access trong Leaver lifecycle

Khi nhân viên nghỉ, grant tạm còn hiệu lực phải bị chặn theo thời điểm Leaver nếu thời điểm đó đến **trước** validUntil.

~~~text
Grant validUntil: 20:00
Leaver effectiveAt: 17:00
Access cutoff theo policy: 17:00
~~~

Chỉ chờ batch expire lúc 20:00 có thể để lại ba giờ đặc quyền.

### 19.1. Những lớp phải kiểm soát

- IdP/SSO chặn xác thực mới.
- Grant store thu hồi những grants còn active.
- PAM/PIM chấm dứt activation và session phù hợp.
- SCIM/API gỡ role/group và disable account tại SaaS.
- Cloud IAM/database thu hồi direct permissions.
- Token/session kiểm tra việc tiếp tục sử dụng quyền cũ.
- Credential/share link/API key phát sinh từ người dùng được rà soát.
- Reconciliation xác minh trạng thái ở từng target.

### 19.2. Ownership và tài nguyên còn hoạt động

Leaver của người quản trị **không có nghĩa phải xóa mọi dữ liệu hoặc job họ từng quản lý**. Hãy chuyển ownership của service, document và workload hợp lệ, đồng thời thu hồi quyền cá nhân.

### 19.3. Đo thời gian thu hồi thực tế

Phân biệt thời điểm chính sách yêu cầu hết quyền, thời điểm gửi lệnh, thời điểm target chặn và thời điểm được kiểm chứng. Không báo cáo SLA tốt bằng cách lấy thời điểm HTTP 200 thay cho actual revocation.

## 20. Temporary access cho service accounts và workloads

Một pipeline CI/CD có thể cần quyền cập nhật deployment hoặc secret trong vài phút. Thay vì giữ credential cloud admin dài hạn:

1. Tạo workload principal riêng với owner/môi trường/mục đích.
2. Dùng workload identity federation hoặc credential ngắn hạn nếu hỗ trợ.
3. Giới hạn issuer, audience, subject, target resource và permissions.
4. Kiểm tra quyền riêng cho từng job/action.
5. Thu hồi hoặc để credential/trust hết hạn theo chính sách.
6. Đối soát role/trust binding cũ khi job thay đổi hoặc ngừng.
7. Kiểm toán service principal, không giả định có người dùng đã hoàn thành MFA.

### 20.1. Token 5 phút vẫn có thể quá rộng

Một token sống ngắn với cloud.admin trên mọi project vẫn gây hậu quả lớn khi bị đánh cắp hoặc sử dụng sai. TTL không thay resource/action scope.

### 20.2. Workload không phải tài khoản cá nhân

Không tự động hóa việc đọc OTP của một nhân viên để job chạy mỗi đêm. Workload cần machine authentication, scope, owner và vòng đời riêng; người chỉnh production workload phải tuân thủ MFA/approval khi đăng nhập quản trị.

### 20.3. Thay owner khi nhân viên Leaver

Không vội xóa bot production chỉ vì owner cũ nghỉ. Xác định bot còn cần vận hành không; nếu có, bàn giao owner, thu hồi credential của người cũ và rà soát các grants/trust của workload.

## 21. Lỗi phổ biến và biện pháp kiểm soát

| Lỗi | Hệ quả | Kiểm soát |
|---|---|---|
| TTL chỉ nằm trong portal | Target vẫn cho phép sau expiry | Enforcement và readback |
| Full admin trong vài phút | Tác động lớn trong cửa sổ ngắn | JEA, resource scope, SoD |
| Self-approval | Người dùng tự cấp quyền nguy hiểm | Phân tách người duyệt |
| JWT sống dài hơn grant | Claim quyền cũ tiếp tục hợp lệ | Runtime entitlement check hoặc revocation |
| SCIM cập nhật chậm | Quyền tồn dư tại SaaS | Cảnh báo lag, đối soát và containment |
| Cache PDP giữ PERMIT | Quyền kéo dài quá validUntil | Decision cache bound/invalidation |
| Role local ngoài IAM | Gỡ group nhưng vẫn có admin | Inventory và đối soát |
| Retry sự kiện cũ | Tái cấp quyền sau Leaver | Sequence/version + idempotency |
| Gia hạn liên tục | Temporary biến thành standing privilege | Giới hạn renewal và approval mới |
| Quên secondary grants | Share link hoặc API key tồn tại lâu | Kiểm soát delegation và artefacts |
| Credential được chia sẻ | Mất khả năng truy vết người dùng | Principal/phiên riêng, không dùng chung secret |
| Break-glass không audit | Lạm dụng khó phát hiện | Alert, hậu kiểm, rotation |
| Quyền sai tenant | Rò dữ liệu chéo tổ chức | Namespace và object authorization |
| Quyền workload thiếu owner | Secret/trust mồ côi | Owner, expiry, review |
| Đóng revoke khi chưa readback | Quyền thực tế vẫn tồn tại | VERIFIED/PARTIAL rõ ràng |

### 21.1. Gia hạn phải đánh giá lại

Yêu cầu thêm 30 phút không nên tự động sửa validUntil theo ý client. Cần đánh giá lại task, ticket, trạng thái subject, approval và maximum total duration. Tránh chuỗi grant ngắn được nối liên tục để né chính sách.

### 21.2. Sự cố không thể thu hồi ngay

Nếu hệ thống đích không hỗ trợ revoke nhanh, có thể cần khóa network path, vô hiệu credential ở upstream, chặn tài khoản, thay policy resource hoặc biện pháp containment được phê duyệt. Ghi rõ hạn chế và thời gian effective access thật sự bị chặn.

## 22. Pseudocode kích hoạt và thu hồi

### 22.1. Kích hoạt một grant

~~~text
function activateTemporaryAccess(request):
    user = authoritativeIdentityStore.get(request.subjectId)
    task = trustedTicketStore.get(request.ticketId)
    policy = policyStore.findApplicablePolicy(
        request.action, request.resourceId
    )

    if user.status != ACTIVE:
        return DENY
    if task is NONE or not task.isAuthorizedAndOpen:
        return DENY
    if not policy.userEligible(user):
        return DENY
    if not policy.allowsScope(request.action, request.resourceId):
        return DENY

    approval = approvalService.verifyExactRequest(request)
    if not approval.valid:
        return DENY
    if policy.forbidsSelfApproval and approval.actorId == user.id:
        return DENY

    duration = min(request.duration, policy.maxDuration,
                   approval.maxDuration)
    grant = grantStore.createIdempotentGrant(
        requestId=request.id,
        subjectId=user.id,
        action=request.action,
        resourceId=request.resourceId,
        validUntil=trustedClock.now() + duration,
        lifecycleVersion=user.lifecycleVersion
    )

    target.applyGrant(grant)
    if not target.readbackExactEffectiveGrant(grant):
        grantStore.markPartialAndEscalate(grant.id)
        return PARTIAL

    grantStore.markActive(grant.id)
    return ACTIVE_WITH_AUDIT_ID
~~~

### 22.2. Reconcile sau expiry hoặc trigger

~~~text
function reconcileTemporaryGrants():
    for grant in grantStore.findPotentiallyInvalidGrants():
        user = authoritativeIdentityStore.get(grant.subjectId)
        shouldRevoke = (
            trustedClock.now() >= grant.validUntil
            or grant.explicitRevokeRequested
            or user.status != ACTIVE
            or user.lifecycleVersion != grant.eligibleVersion
        )

        if not shouldRevoke:
            continue

        grantStore.markRevoking(grant.id)
        target.revokeGrantIdempotently(grant)

        if target.verifyNoEffectiveAccessForThisGrant(grant):
            grantStore.markVerifiedClosed(grant.id)
        else:
            grantStore.markPartialAndEscalate(grant.id)
~~~

Cả hai đoạn là **pseudocode đào tạo**, không phải chương trình sản xuất. Cần xử lý transaction, concurrent requests, lỗi network, source freshness, TOCTOU, token/session và mọi đường grant. Việc một grant bị revoke không chứng minh user thiếu **mọi quyền** trên resource nếu có các grants hợp lệ khác; verification phải đánh giá **đúng entitlement cần thu hồi** và policy tổng thể.

## 23. Case study: truy cập production theo JIT

### 23.1. Bối cảnh

Doanh nghiệp có hệ thống payment-api. Nam là kỹ sư hỗ trợ có quyền support.viewer thường trực. Trong sự cố INC-2841, Nam cần restart service trong một cửa sổ bảo trì.

Yêu cầu bảo mật:

- Chỉ service.restart trên prod/tenant-a/payment-api.
- Production duty manager phê duyệt.
- MFA theo assurance phù hợp, không self-approval.
- Tối đa 30 phút, có thể revoke sớm.
- Có audit request, activation, action và verification.
- Không cấp global-admin hoặc credential chung.

### 23.2. Timeline minh họa

| Thời điểm | Sự kiện | Bằng chứng cần có |
|---|---|---|
| 08:55 | Nam gửi yêu cầu | Request đúng ticket và scope |
| 08:57 | Duty manager duyệt | Approval gắn request và duration |
| 09:00 | Kích hoạt grant | Target role/action readback |
| 09:04 | Nam restart service | Resource/action audit |
| 09:08 | Ticket đóng | Trigger revoke sớm |
| 09:09 | Target chặn action | Bằng chứng quyền đã hết |
| 09:10 | Workflow đóng | VERIFIED_CLOSED nếu đủ chứng cứ |

Thời điểm chỉ là ví dụ, không phải SLA được tiêu chuẩn hóa.

### 23.3. Biến cố 1: token còn quyền sau ticket đóng

JWT có thể phát lúc 09:01 và hết hạn 10:01. Nếu API chỉ kiểm tra chữ ký/exp và role claim, Nam vẫn restart sau 09:08. Cần kiểm tra grant hiện tại hoặc dùng cơ chế token/session revocation phù hợp, không chỉ nhìn thời gian token hết hạn.

### 23.4. Biến cố 2: group SCIM bị gỡ chậm

IAM remove membership lúc 09:08, nhưng SaaS áp dụng thay đổi 09:13. Revoke command có thể thành công về giao thức nhưng quyền thực tế còn năm phút. Hệ thống phải để PARTIAL và đo revocation lag, có biện pháp containment nếu rủi ro cao.

### 23.5. Biến cố 3: Nam không còn eligible trong lúc grant active

Nam được chuyển sang nhóm khác lúc 09:05 và không còn nhiệm vụ on-call. Quyền tạm cần được đánh giá lại theo policy và thu hồi sớm. Eligibility tại thời điểm request không thay trạng thái hiện hành.

## 24. Audit và các chỉ số vận hành

Một audit record nên trả lời: **Ai xin quyền gì, vì sao, ai duyệt, khi nào kích hoạt, đã dùng làm gì và khi nào thực sự bị chặn?**

~~~json
{
  "eventId": "temporary-access-2026-006",
  "grantId": "tmp-access-2026-006",
  "principalRef": "employee-1042",
  "subjectType": "USER",
  "action": "service.restart",
  "resourceRef": "prod/tenant-a/payment-api",
  "reasonRef": "INC-2841",
  "approvalRef": "APR-9051",
  "policyVersion": "jit-service-v4",
  "activatedAt": "2026-11-23T09:00:00+07:00",
  "validUntil": "2026-11-23T09:30:00+07:00",
  "revokeReason": "INCIDENT_CLOSED",
  "revokeRequestedAt": "2026-11-23T09:08:00+07:00",
  "verifiedRevokedAt": "2026-11-23T09:09:30+07:00",
  "finalState": "VERIFIED_CLOSED",
  "correlationId": "INC-2841"
}
~~~

Đây là JSON giả lập. Không ghi access token, private key, mật khẩu, OTP hoặc session cookie nguyên dạng. Session recording cần chính sách privacy, phân quyền xem và retention.

### 24.1. Các mốc không được trộn lẫn

- Approval time: khi người có thẩm quyền duyệt.
- Activation time: khi grant bắt đầu có hiệu lực.
- Intended expiry: hạn cần hết quyền.
- Revoke requested: lệnh thu hồi đã phát.
- Enforced revocation: quyền thực sự bị chặn.
- Verified revocation: hệ thống có bằng chứng xác nhận theo phạm vi.

Nếu lệnh revoke đã gửi nhưng chưa có bằng chứng target, không dùng verified timestamp giả.

### 24.2. KPIs/SLOs nên theo dõi

| Chỉ số | Ý nghĩa |
|---|---|
| Số standing admin grants | Bề mặt quyền mạnh thường trực |
| Tỷ lệ sử dụng JIT thay vì standing | Xu hướng giảm quyền tồn tại không cần |
| Activation latency | Hiệu quả vận hành |
| Tỷ lệ self-approval vi phạm | Lỗ hổng SoD |
| Số grants vượt maximum duration | Sai cấu hình hoặc renewal lạm dụng |
| Expiry-to-enforcement lag | Độ trễ chặn quyền |
| Tỷ lệ VERIFIED_CLOSED | Chất lượng bằng chứng thu hồi |
| Số PARTIAL/oldest pending | Rủi ro chưa xử lý |
| Số lần break-glass | Mức sử dụng và khả năng lạm dụng |
| Số grants workload thiếu owner | Quản trị định danh phi con người |
| Tỷ lệ request ngoài scope bị chặn | Chất lượng authorization |
| Số secondary grants tồn tại sau expiry | Quyền gián tiếp chưa được quản lý |

Các chỉ số cần định nghĩa mẫu số, phạm vi và độ trễ telemetry. JIT adoption cao không có nghĩa an toàn nếu mỗi request đều được full-admin.

## 25. Ma trận kiểm thử Temporary access

| Test | Kỳ vọng |
|---|---|
| User chưa xác thực yêu cầu role nhạy cảm | Từ chối |
| User đã Leaver/suspended | Từ chối activation |
| Request thiếu ticket bắt buộc | Từ chối hoặc yêu cầu hoàn thiện |
| User không eligible | Không kích hoạt |
| Người xin tự approve khi policy cấm | Từ chối |
| Approval cho logs.read dùng cấp iam.admin | Từ chối vì action không khớp |
| Grant tenant A đem dùng ở tenant B | Từ chối |
| Duration vượt policy maximum | Giới hạn hoặc từ chối |
| Request trước validFrom | Chưa có quyền |
| Request ngay trước validUntil | Chỉ cho phép nếu các điều kiện khác đạt |
| Request tại hoặc sau validUntil | Từ chối |
| Ticket đóng trước expiry | Kích hoạt revoke sớm |
| Mover làm mất eligibility | Thu hồi/đánh giá lại theo policy |
| Leaver sớm hơn TTL | Chặn theo thời điểm Leaver |
| JWT còn hạn khi grant đã hết | Không được thực hiện action bị thu hồi |
| Session PAM còn mở | Chặn action/terminate theo cơ chế |
| SCIM API trả 200 nhưng role còn | PARTIAL, retry/escalation |
| Group đã gỡ nhưng direct ACL còn | Phát hiện đường quyền tồn dư |
| Break-glass dùng ngoài sự cố | Audit/cảnh báo/deny theo policy |
| Workload credential còn hạn nhưng trust bị thu hồi | Chặn theo cơ chế được thiết kế |
| PDP cache PERMIT cũ | Không chấp nhận sau expiry |
| Đồng hồ service lệch | Không kéo dài quyền trái policy |
| Worker xử lý event expiry trùng | Idempotent, không tái cấp |
| Approval được sửa scope sau khi duyệt | Reject hoặc reapprove |
| User gia hạn nhiều lần liên tiếp | Không vượt giới hạn và approval policy |
| Token/API key được tạo trong phiên tạm | Kiểm soát vòng đời artefact mới |
| Grant đúng scope và còn hạn | Cho action hợp lệ, ghi audit |
| Backend bị gọi trực tiếp bỏ gateway | Vẫn kiểm tra authorization |

### 25.1. Kiểm thử ranh giới thời gian

Đánh giá tại validFrom trừ một khoảng nhỏ, đúng validFrom, ngay trước validUntil, đúng validUntil và sau validUntil. Thử cùng với token được phát trước expiry, cache cũ và sự kiện JML đến trễ.

### 25.2. Kiểm thử thực tế tại target

Không chỉ kiểm tra portal hiển thị EXPIRED; phải xác minh hiệu lực tại hệ thống đích bằng API/readback hoặc test hành vi được phê duyệt, không gây thay đổi nguy hiểm trên production ngoài phạm vi cho phép.

## 26. Những sai lầm cần tránh

**“Thêm expiresAt trong database là đủ.”** Không nếu API hoặc PAM target không enforce thời hạn.

**“Mật khẩu tạm đồng nghĩa quyền tạm.”** Credential có hạn và entitlement có hạn là hai khái niệm riêng.

**“MFA mạnh cho phép giữ admin vô thời hạn.”** MFA không thay nguyên tắc least privilege.

**“Full admin 15 phút luôn an toàn.”** Quyền quá rộng vẫn có thể bị lạm dụng trong 15 phút.

**“Đóng ticket rồi gửi remove group là xong.”** Có thể còn session, role local, share link và token cũ.

**“SCIM 200 nghĩa là toàn bộ quyền đã mất.”** Cần readback và kiểm tra effective access.

**“JIT provisioning là JIT access.”** Account tạo khi login có thể vẫn giữ role dài hạn.

**“Leaver có thể chờ grant tự hết hạn sau vài ngày.”** Nếu hợp đồng chấm dứt sớm, quyền phải chặn theo policy Leaver.

**“Break-glass có thể là admin chung không audit.”** Đây là backdoor rủi ro, phải có bảo vệ/hậu kiểm.

**“Token workload có TTL ngắn nên scope nào cũng được.”** Short-lived credentials không thay action/resource scoping.

**“Hết role tạm thì API key tạo trong phiên cũng tự chết.”** Artefact phụ có thể tồn tại độc lập.

**“Chỉ cần kiểm tra điều kiện khi activation.”** Trong thời gian grant hoạt động có thể xảy ra Mover, Leaver, incident closure hoặc thay đổi resource.

## 27. Tình huống tự luyện tập

### Tình huống A: quyền admin sau bảo trì

Kỹ sư được cấp database-admin để bảo trì một bảng và nhóm dự định gỡ thủ công cuối tuần. Công việc đã hoàn tất sau một giờ.

**Phân tích:** Cấp quyền vượt thời gian và phạm vi. Nên xác định action, schema, TTL, approval, auto-expiry/containment và readback.

### Tình huống B: token sống lâu hơn quyền

Grant export báo cáo hết hạn lúc 10:00 nhưng token đã phát lúc 09:50 còn hạn đến 10:50.

**Phân tích:** API không được coi token còn hạn là grant còn hiệu lực. Cần kiểm tra entitlement expiry hoặc cơ chế session/token thu hồi phù hợp.

### Tình huống C: Mover bàn giao ba tài liệu

Nhân viên chuyển sang team mới, cần xem ba tài liệu cũ hai ngày để bàn giao.

**Phân tích:** Thu hồi role team cũ rộng; cấp chỉ quyền đọc ba tài liệu với owner, approval, validUntil và revoke verification.

### Tình huống D: Contractor rời sớm

Contractor có grant đến ngày 30 nhưng hợp đồng kết thúc ngày 25.

**Phân tích:** Leaver effectiveAt phải chặn grant theo chính sách từ ngày 25, không chờ ngày 30.

### Tình huống E: IdP outage và break-glass

IdP ngừng hoạt động, hệ thống thanh toán gặp sự cố cần khôi phục.

**Phân tích:** Kế hoạch break-glass phải khả dụng ngoài phụ thuộc IdP đang outage, nhưng vẫn giới hạn access, cảnh báo độc lập và hậu kiểm, rotation.

### Tình huống F: quyền tạm sinh API key lâu dài

Trong phiên admin 15 phút, một user tạo API key có quyền export rồi lưu vào script. Role admin hết hạn nhưng API key vẫn dùng được.

**Phân tích:** Cần quản lý secondary credentials/permissions, không chỉ grant ban đầu. Giới hạn quyền tạo key và có cách revoke/bàn giao.

## 28. Checklist thiết kế Temporary access

1. **Purpose:** nhiệm vụ có ticket/mục đích rõ và owner?
2. **Subject:** người hoặc workload được định danh ổn định và đang đủ điều kiện?
3. **Action:** permission hẹp đúng thao tác?
4. **Resource:** target có tenant, project, environment và instance cụ thể?
5. **Eligibility:** đã tách eligible với active privilege?
6. **Approval:** người duyệt đúng thẩm quyền và SoD?
7. **Authentication:** MFA/step-up đủ assurance cho quyền nhạy cảm?
8. **Time:** validFrom/validUntil/maxDuration và timezone rõ?
9. **Activation:** có readback xác minh target cấp đúng quyền?
10. **Enforcement:** API/PDP kiểm tra grant tại thời điểm action?
11. **RBAC/ABAC:** policy kết hợp role, resource, context và trạng thái?
12. **JEA:** có giới hạn command/action thay vì full-admin?
13. **PAM/PIM:** session và đường đặc quyền có được bao phủ?
14. **Token/session:** JWT, refresh token, SaaS session có thể sống lâu hơn grant không?
15. **SCIM:** provisioning group có độ trễ/role local không?
16. **Revoke early:** incident close, Mover, Leaver hoặc mất eligibility có trigger?
17. **Expiry:** quyền hết bằng enforcement, không chỉ đổi màu UI?
18. **Verification:** có readback về effective access ở target?
19. **Partial failure:** có owner, deadline, escalation và containment?
20. **Secondary grants:** share link, API key, delegated role có được quản lý?
21. **Renewal:** không gia hạn vượt policy hoặc approval?
22. **Break-glass:** kiểm soát khả dụng, cảnh báo và hậu kiểm?
23. **Workload:** owner, scope, credential, trust và TTL riêng?
24. **Joiner:** tách baseline rights khỏi onboarding temporary rights?
25. **Mover:** gỡ role cũ và chỉ cấp quyền bàn giao hẹp?
26. **Leaver:** chặn grant theo employment cutoff dù TTL còn?
27. **Audit:** request/approval/activation/use/revoke/verify có correlation?
28. **KPIs:** theo dõi standing rights, lag, PARTIAL và exception?
29. **Testing:** có boundary, stale token, sai tenant, cache, direct grant và race tests?
30. **Accountability:** ai chịu trách nhiệm nếu target vẫn còn quyền sau hạn?

---

**Ghi nhớ:** **Temporary access** là quyền **đúng chủ thể, đúng hành động, đúng tài nguyên và chỉ trong khoảng thời gian có căn cứ**, chứ không đơn thuần là password hoặc token ngắn hạn. Để thực hiện Least Privilege, cần phối hợp **JIT/JEA, PAM/PIM, approval, MFA, RBAC/ABAC** với quy trình request–activate–expire/revoke–verify. Trong **Joiner–Mover–Leaver**, chỉ khi kiểm chứng quyền thực tế đã hết ở IdP, SSO, SCIM, API, SaaS và workload liên quan mới có thể kết luận đã giảm **quyền truy cập tồn dư**.
