# Audit scope trong IAM: xác định phạm vi kiểm toán vòng đời danh tính và quyền truy cập

## 1. Audit scope là gì?

**Audit scope** (phạm vi kiểm toán) trong **Identity and Access Management (IAM)** là tập hợp **đối tượng, hệ thống, hoạt động, kiểm soát, dữ liệu bằng chứng, khoảng thời gian và ranh giới tổ chức** được đưa vào một cuộc kiểm toán hoặc một chương trình giám sát có cấu trúc. Nó trả lời rõ: **kiểm tra cái gì, ở đâu, của ai, trong giai đoạn nào, theo tiêu chí nào và những gì nằm ngoài phạm vi**.

Ví dụ, yêu cầu “kiểm toán quyền truy cập quý IV” là chưa đủ rõ. Một audit scope có thể được viết cụ thể hơn:

> Rà soát toàn bộ quyền truy cập production vào ứng dụng thanh toán thuộc org-a trong kỳ đã xác định, gồm nhân viên, nhà thầu, guest, service account, OAuth client, local account và quyền đặc quyền; kiểm tra các sự kiện Joiner–Mover–Leaver, request/approval, provisioning/deprovisioning, SoD, recertification, token/credential liên quan, cùng bằng chứng quyền thực tế và trường hợp thu hồi quá hạn.

Phạm vi này vẫn cần nêu rõ **ngày bắt đầu/kết thúc, hệ thống đích, nguồn dữ liệu, chủ sở hữu kiểm soát, phương pháp kiểm tra, cách xử lý ngoại lệ và giới hạn bằng chứng**.

**Audit scope không đồng nghĩa lấy toàn bộ log**. Một chương trình thu gom hàng terabyte log nhưng không kiểm tra **những tài khoản cục bộ, quyền ngầm từ group lồng nhau, JWT còn hiệu lực hoặc service principal không có owner** vẫn có thể bỏ sót rủi ro IAM nghiêm trọng.

Trong module **Security — Identity Access Management — Identity Lifecycle**, audit scope phải được đặt trong mô hình **Joiner–Mover–Leaver (JML)**, liên kết **HRIS/nguồn bảo trợ, IAM/IGA, IdP/SSO/MFA, SCIM, RBAC/ABAC/PBAC, service/workload identity, quyền đặc quyền, token, kiểm toán và giảm quyền truy cập tồn dư**.

### Mục tiêu học tập

Sau bài học, người học có thể:

1. Phân biệt **audit scope**, audit objective, audit criteria, audit log, access review và reconciliation.
2. Xác định population của **human, non-human, device, privileged, guest và delegated identities**.
3. Chọn hệ thống, tenant, tài nguyên, thời gian và các điểm kiểm soát quan trọng dựa trên rủi ro.
4. Phân tích **expected, assigned, effective và used access** cùng chất lượng bằng chứng.
5. Liên kết sự kiện JML, request/approval, SoD, recertification, token/credential và deprovisioning.
6. Xây dựng source inventory, control matrix, evidence contract, sampling strategy và traceability.
7. Phát hiện **coverage gap**, dữ liệu không xác minh được và giới hạn kết luận.
8. Lập kế hoạch audit, viết phát hiện, theo dõi remediation và kiểm chứng quyền đã bị chặn tại hệ thống đích.

## 2. Mục đích kiểm toán quyết định phạm vi

Một cuộc kiểm toán không nên bắt đầu bằng câu “hãy xuất hết dữ liệu IdP”. Trước hết cần xác định **mục tiêu kiểm toán (audit objective)** và **điều kiện đạt (audit criteria)**.

| Mục tiêu | Câu hỏi chính | Ví dụ bằng chứng |
| --- | --- | --- |
| **Identity completeness** | Tất cả tài khoản có chủ thể và nguồn quyền hợp lệ không? | HRIS, directory, account inventory, correlation |
| **Joiner control** | Account và entitlement có được cấp sau xác minh/phê duyệt đúng không? | Joiner event, role approval, target state |
| **Mover control** | Quyền cũ có được rút khi đổi nhiệm vụ không? | Assignment delta, revoke records, negative tests |
| **Leaver control** | Quyền có được cắt đúng thời hạn không? | Termination events, token/session revoke, target Deny |
| **Least privilege** | Quyền hiện tại có vượt nhu cầu thực không? | Role/ACL, access model, resource owners |
| **SoD** | Có thể một người tự hoàn tất chuỗi giao dịch nhạy cảm không? | Static roles, transaction actor, approval logs |
| **Privileged access** | Ai có admin, trong bao lâu, sử dụng thế nào? | PAM/JIT sessions, permissions, target audit |
| **Non-human identity governance** | Bot/service principal có owner, quyền và credential hợp lệ không? | Service catalog, vault, CI/CD, cloud IAM |
| **Access recertification** | Reviewer có đủ thẩm quyền và remediation thật sự hoàn tất? | Review decisions, evidence, target readback |
| **Audit reliability** | Log và bằng chứng có đủ, đúng nguồn, không bị sửa không? | Pipeline health, integrity, retention, gap metrics |

Một audit có thể bao phủ nhiều mục tiêu, nhưng phải **ghi rõ từng control objective** để không kết luận quá rộng. Kiểm toán **Leaver compliance** không tự chứng minh **MFA effectiveness** hoặc **SoD ở giao dịch thanh toán** nếu các điều kiện này chưa được thử.

## 3. Audit scope khác logging, access review và monitoring

| Khái niệm | Vai trò | Mức độ kết luận |
| --- | --- | --- |
| **Audit scope** | Định nghĩa ranh giới đối tượng, thời gian, tiêu chí, evidence | Nêu điều gì có thể được kiểm tra và kết luận |
| **Audit logging** | Ghi sự kiện có thời điểm, actor và kết quả | Là nguồn bằng chứng, không tự là kết luận |
| **Access review/recertification** | Chủ quyền xác nhận giữ/thu hồi quyền | Một hoạt động/kiểm soát nằm trong scope kiểm toán |
| **Account reconciliation** | So expected với assigned/observed target rights | Phát hiện drift, hỗ trợ chứng minh remediation |
| **Security monitoring/SIEM** | Phát hiện tín hiệu bất thường gần thời gian thực | Cung cấp alert/case và điểm cần điều tra |
| **Internal audit/assurance** | Đánh giá thiết kế và hiệu lực kiểm soát theo tiêu chí | Nêu phát hiện, giới hạn và khuyến nghị |
| **Risk assessment** | Đánh giá khả năng/tác động của rủi ro | Giúp ưu tiên audit scope, không thay kiểm thử |

Ví dụ, **reviewer nhấn REVOKE** không chứng minh đã rút role. **SCIM trả HTTP 200** không chứng minh JWT/PAT đã bị vô hiệu. **SIEM không có alert** không chứng minh hệ thống không có quyền truy cập tồn dư.

Để đi từ audit scope đến kết luận đáng tin, cần **kiểm soát được nguồn bằng chứng, kiểm tra thực thi và giới hạn quan sát**.

## 4. Những chiều phải nêu khi xác định scope

| Chiều phạm vi | Câu hỏi cần khóa rõ | Ví dụ |
| --- | --- | --- |
| **Organization/tenant** | Những pháp nhân, tenant, environment nào? | org-a production, không gồm lab org-b |
| **Identity population** | Những loại principal nào? | Employee, contractor, guest, service principal |
| **Account systems** | IdP, cloud, SaaS, DB, local OS nào? | IdP-A, ERP-SaaS, billing DB |
| **Resource/action** | Quyền và tài nguyên nào? | READ/WRITE/ADMIN tại payment API |
| **Lifecycle events** | Joiner/Mover/Leaver, expiry, disable, transfer? | Termination and role removal |
| **Control activities** | Approval, MFA, SoD, review, logging? | Four-eyes approval, quarterly recertification |
| **Credential/token** | Những khóa, token, phiên nào liên quan? | OAuth grants, PAT, mTLS certificates |
| **Time window** | Kỳ kiểm toán và mốc hiệu lực? | 01/10–31/12 theo timezone được nêu |
| **Evidence sources** | Dữ liệu ở đâu, ai có authority? | HRIS events, target ACL, PAM audit |
| **Risk/materiality** | Tài sản/điều kiện nào cần ưu tiên? | Production, tài chính, dữ liệu nhạy cảm |
| **Execution method** | Kiểm toàn bộ hay lấy mẫu? | 100% Leaver cấp admin, mẫu các role phổ thông |
| **Exclusions/limitations** | Điều gì không đánh giá và vì sao? | Legacy SaaS không hỗ trợ session readback |

**Scope phải có phiên bản, owner và người phê duyệt**. Khi thêm một ứng dụng lớn giữa kỳ hoặc thay nguồn authority, phải ghi change control thay vì âm thầm đổi mẫu số kết quả.

## 5. Phạm vi theo đối tượng: identity, account, person và relation

Một người có thể có nhiều tài khoản ở nhiều hệ thống; một account không nhất thiết ánh xạ một-một với một người. Do đó, **identity population** không thể định nghĩa chỉ bằng số user trong IdP.

| Đối tượng | Ý nghĩa | Audit check điển hình |
| --- | --- | --- |
| **Person** | Chủ thể con người được nhận diện | Deduplication và verified identity |
| **Employment relation** | Mối quan hệ cụ thể với tổ chức/dự án | Start/endAt, sponsor, organization, role basis |
| **IAM identity** | Định danh logic trong IAM | Correlation, lifecycle state |
| **IdP account** | Principal ở identity provider | Authentication, MFA, group membership |
| **Target account** | User tại SaaS/DB/local OS | Local role, direct ACL, target active state |
| **Delegated account** | Quyền được người khác ủy quyền trong phạm vi | Delegation chain, expiry, approver |
| **Shared/technical account** | Account dùng chung hoặc cho automation | Accountable owner, session actor attribution |

Ví dụ nhân viên có account **lan@org-a** và tài khoản quản trị **lan-admin@org-a**. Scope chỉ tính “user có email trong HRIS” dễ bỏ qua tài khoản admin liên quan. Ngược lại, hai account cùng tên hiển thị chưa chắc cùng person nếu **issuer/tenant** khác nhau.

**Cần kiểm tra linkage bằng stable IDs, source authority và confidence**. Identity correlation không chắc chắn phải được ghi **UNKNOWN/UNVERIFIED**, không tự hợp nhất để làm báo cáo trông đầy đủ.

## 6. Phạm vi theo loại chủ thể: human và non-human

| Population | Ví dụ | Rủi ro dễ bỏ sót |
| --- | --- | --- |
| **Employee** | Nhân viên chính thức | Role accumulation sau Mover |
| **Contractor** | Nhà thầu theo hợp đồng | Hết hạn sponsor/contract nhưng còn quyền |
| **Guest/external partner** | Khách cộng tác từ tenant khác | Guest account/token không được review |
| **Intern/temporary staff** | Nhân sự ngắn hạn | Access endAt không được thực thi |
| **Privileged human account** | Admin/superuser | Quyền gián tiếp, session đặc quyền và SoD |
| **Service account** | svc-report-exporter | Owner cũ đã Leaver, static secret |
| **Service principal/OAuth client** | M2M integration | Client credentials, scope/trust quá rộng |
| **Managed/workload identity** | VM, Kubernetes pod, CI/CD job | Role ở cloud và workload federation |
| **Device identity** | Laptop, IoT gateway | Cert/device trust còn sau mất thiết bị |
| **Emergency/break-glass identity** | Recovery administrator | Ngoại lệ, không đủ audit, standing privilege |

**Không được mặc định SCIM User/Group là toàn bộ identity universe**. Nhiều cloud service principals, PAT, database accounts và appliance identities không đi qua SCIM.

Nếu audit chỉ tập trung vào employee identities, hãy ghi rõ **NHI/guest/device identities nằm ngoài phạm vi** thay vì tuyên bố tổ chức đã kiểm toán toàn bộ quyền truy cập.

## 7. Xác định hệ thống nguồn có thẩm quyền

Tính chính xác của audit phụ thuộc việc **ai là nguồn sự thật cho trường nào**:

| Thông tin | Authority thường gặp | Không nên suy từ |
| --- | --- | --- |
| **Nhân viên đang hoạt động** | HRIS hoặc nguồn nhân sự được ủy quyền | Activity gần nhất của IdP |
| **Contractor/guest sponsor** | Contract registry, sponsor workflow | Guest đã đăng nhập thành công |
| **Job/organization assignment** | HRIS/project authority | Nhóm IdP cũ còn tồn tại |
| **Service owner** | Service catalog/CMDB đã kiểm soát | Người tạo key gần nhất |
| **Principal/credential status** | Cloud IAM, vault, CA/PKI, issuer | Log từ một API không liên quan |
| **Role/ACL tại target** | SaaS, DB, cloud resource | Approval trong IGA |
| **Token validity** | Issuer + resource server theo contract | Chỉ JWT payload decode |
| **Device posture** | MDM/attestation verifier có thẩm quyền | Header client tự khai compliant=true |
| **Session/action result** | App/API/PAM/resource server | Chỉ portal approval |

**Một nguồn có thể authoritative cho một thuộc tính nhưng không phải toàn bộ identity state**. Ví dụ HRIS quyết định ngày Leaver, IdP quyết định account disabled, còn resource server quyết định liệu token cũ có thực sự bị từ chối hay không.

Nên thiết lập **source owner, collection method, extractedAt, sourceVersion, coverage và expected update latency** cho từng nguồn.

## 8. Phạm vi theo Joiner–Mover–Leaver

Mỗi giai đoạn JML có **control objective và dấu vết khác nhau**:

| Giai đoạn | Audit scope tối thiểu nên xét | Ví dụ phát hiện |
| --- | --- | --- |
| **Joiner** | Source verification, startAt, account creation, birthright roles, approvals, MFA enrollment | Quyền production được cấp trước ngày bắt đầu |
| **Mover** | Role/assignment delta, old-role revoke, new-role approval, target reconciliation | Người chuyển Atlas → Nova vẫn có AtlasAdmin |
| **Leaver** | Termination effectiveAt, user disable, group/role/ACL revoke, session/token/PAT handling | JWT/PAT vẫn ALLOW sau cutoff |
| **Rejoiner** | Account reactivation, identity match, old credentials/roles | Khôi phục role cũ không còn hợp lệ |
| **Concurrent relations** | Một người có nhiều quan hệ hợp lệ | Xóa nhầm quyền org-b khi Leaver org-a |

**Audit JML phải kiểm tra quyền có hiệu lực**, không chỉ ticket có chữ ký. Các sự kiện có thể đến muộn hoặc sai thứ tự; scope cần bao gồm **replay/regrant và status readback**.

### Câu hỏi quan trọng

Một employee Leaver đúng hạn ở HRIS và disabled ở IdP có thể vẫn có **local SaaS account, OAuth refresh grant hoặc access token được xác thực offline**. Audit scope chỉ gồm HRIS và IdP là không đủ để kết luận “toàn bộ quyền đã bị thu hồi”.

## 9. Joiner: phạm vi kiểm toán cấp danh tính và quyền ban đầu

Với Joiner, audit nên xem:

1. **Nguồn khởi tạo:** HRIS/contractor system hoặc sponsor workflow có đáng tin?
2. **Identity proofing:** đã kiểm tra person và tránh duplicate identity chưa?
3. **Account provisioning:** account ở IdP/target được tạo bởi actor nào, lúc nào?
4. **Birthright mapping:** quyền được tính theo đúng organization/job/role policy?
5. **Access request:** quyền nhạy cảm có approval từ người có thẩm quyền không?
6. **SoD và least privilege:** có toxic combination ngay lúc cấp không?
7. **MFA/SSO:** có yêu cầu onboarding assurance theo tài nguyên không?
8. **Effective date:** có tránh cấp role usable trước startAt không?
9. **Reconciliation:** target roles/ACL có trùng approved entitlement?
10. **Audit evidence:** có eventId, sourceVersion và target readback?

**Không mặc định “account đã tạo” đồng nghĩa “quyền đã được cấp đúng”**. Account có thể tồn tại trước ngày đi làm để chuẩn bị thiết bị nhưng vẫn cần chặn privileged/data access cho đến mốc chính sách.

## 10. Mover: phạm vi kiểm toán thay đổi quyền và trách nhiệm

Mover là nơi **quyền truy cập tồn dư** thường phát sinh do hệ thống chỉ thêm role mới mà không rút role cũ.

Ví dụ:

~~~text
Before Mover: Atlas ReportEditor, FinanceInvoiceCreator
After Mover expected: Nova ReportViewer

Audit targets:
    Old project role Atlas: REVOKED?
    FinanceInvoiceCreator: REVOKED?
    NovaViewer: APPROVED and correctly scoped?
    Local SaaS roles: UPDATED?
    OAuth/PAT scopes: STILL VALID?
    Resource API old action: DENY?
~~~

Scope cần bao gồm **trường hợp chuyển tạm, kiêm nhiệm và rollback**. Một overlap window có thể được chấp nhận nếu có approval/risk control và hạn kết thúc; không tự coi mọi overlap là vi phạm, cũng không để overlap kéo dài không giới hạn.

Các kiểm soát cần thử gồm **sự kiện nguồn, role delta, workflow approval, provisioning, session/cache propagation và quyền thực tế**.

## 11. Leaver: phạm vi kiểm toán thu hồi có thể chứng minh

Một audit Leaver đầy đủ hơn việc so:

~~~text
HRIS termination = TRUE
IdP disabled = TRUE
~~~

Thay vào đó cần kiểm:

| Lớp | Bằng chứng |
| --- | --- |
| **Nguồn Leaver** | employmentRelationId, effectiveAt, reason category |
| **IAM/IGA** | Deprovision plan và entitlement delta |
| **IdP/SSO** | Account/session/grant state |
| **SCIM/SaaS** | Target account, group, role và direct ACL |
| **OAuth/token** | Refresh grant, access token còn hạn và revocation policy |
| **PAM/JIT** | Privileged lease, elevated sessions, break-glass rights |
| **Device/credential** | PAT, SSH key, cert, local user, device trust theo scope |
| **NHI ownership** | Bot/service nào từng do người đó sở hữu |
| **Target enforcement** | Negative access test trong phạm vi kiểm toán |

**Mốc kết thúc ở nguồn khác mốc thực thi ở đích**. Cần tính **time-to-disable, time-to-revoke và time-to-verified-deny** riêng.

**SCIM active=false, HTTP 200 hoặc IGA ticket CLOSED không chứng minh mọi API đã từ chối token cũ**. Nếu target không hỗ trợ đọc token/session, audit phải ghi hạn chế và phương án kiểm soát thay thế theo risk.

## 12. Rejoiner, duplicate account và quan hệ đồng thời

Một person có thể rời rồi quay lại, có hai hợp đồng đồng thời hoặc đổi tên/email. Scope nên kiểm tra:

- **Stable personId** và relationId, không gộp chỉ theo email.
- **Nguồn** xác minh đây là rejoiner hay một người mới.
- **Đường account reactivation** có bỏ qua approval/SoD không?
- **Old groups, local SaaS roles, PAT, device binding** có được khôi phục ngoài ý muốn?
- **Old reviewer approvals** còn hợp lệ khi job/tenant đã thay đổi không?
- **Conflict** giữa role cũ và role mới có được phát hiện không?
- **Leaver ở org-a** có làm xóa nhầm quan hệ org-b còn ACTIVE không?

Audit scope theo **identity relation** giúp tránh cả **over-revocation** và **under-revocation**. “Tài khoản có email mới” không chứng minh mọi quyền cũ đã bị tách khỏi person.

## 13. Access request và approval workflow thuộc phạm vi nào?

Nếu objective là kiểm tra tính hợp lệ của cấp quyền, audit cần nối:

~~~text
Request -> Business justification -> Approver authority
    -> Decision -> SoD/Policy evaluation -> Provisioning
    -> Target readback -> Effective access
~~~

Các thuộc tính cần chứng minh:

| Kiểm soát | Câu hỏi |
| --- | --- |
| **Requester/beneficiary** | Ai đề nghị, ai thực sự nhận quyền? |
| **Resource owner** | Người duyệt có thẩm quyền với resource/tenant? |
| **Independence** | Có self-approval hoặc SoD conflict bị cấm không? |
| **Time window** | Approval có đúng hạn và còn phù hợp khi provision? |
| **Scope exactness** | Target grant có đúng role/action/resource được duyệt? |
| **Source status** | Người nhận có ACTIVE employment/sponsor khi cấp? |
| **Emergency/exception** | Có quy trình ngoại lệ đã phê duyệt và compensating controls? |
| **Closure evidence** | Quyền thực tế có đúng quyết định? |

**Một approval có thể hợp lệ ở thời điểm 09:00 nhưng không còn hợp lệ khi worker provisioning chạy 11:00**, nếu beneficiary đã Mover/Leaver hoặc role catalog mở rộng quyền materially. Scope nên bao gồm kiểm soát revalidation trước grant.

## 14. RBAC: role, hierarchy và quyền hiệu lực

Với **Role-Based Access Control (RBAC)**, audit phải xét hơn tên role:

- **Role definitions và versions**: các permissions nào được gắn?
- **Direct assignments** và approval/expiry.
- **Nested groups, inherited roles và dynamic groups**.
- **Resource scope/tenant/environment**.
- **Privileged role eligibility vs activation**.
- **Delegation và khả năng impersonate/assign role khác**.
- **Separation of Duties toxic combinations**.
- **Target-specific permissions** khác nhau giữa IdP và ứng dụng.

Ví dụ:

~~~text
IdP: role ReportViewer
Nested group: FinanceOperators -> BillingAdmin
SaaS direct ACL: ExportAllReports

Effective capability:
    READ, EXPORT, MANAGE_BILLING in relevant scope
~~~

**Role name “Viewer” không chứng minh quyền chỉ đọc**, và group đã gỡ trong IdP không tự chứng minh SaaS direct ACL biến mất. Audit phải xác định các **permission paths**, sau đó kiểm tra các **explicit deny/conditions** để tránh kết luận quá mức.

## 15. ABAC/PBAC: kiểm toán logic quyết định, không chỉ role

**Attribute-Based Access Control (ABAC)** sử dụng thuộc tính subject/resource/action/environment; **Policy-Based Access Control (PBAC)** tổ chức quyết định trong các policy được **PDP** đánh giá và **PEP** thực thi.

Audit scope nên gồm:

| Thành phần | Vấn đề cần kiểm |
| --- | --- |
| **Policy Administration Point (PAP)** | Ai thay policy, phê duyệt, publish và rollback? |
| **Policy Decision Point (PDP)** | Quyết định dùng policy/version nào? |
| **Policy Enforcement Point (PEP)** | API/DB/gateway có thực sự chặn request bị Deny? |
| **Policy Information Point (PIP)** | Thuộc tính có nguồn tin cậy, đủ mới và đúng tenant? |
| **Resource attributes** | Owner, classification, project và sensitivity có chính xác? |
| **Subject attributes** | Employment, sponsor, device posture, role, workload owner |
| **Environment/context** | Time, JIT lease, network, authentication assurance |
| **Decision cache** | Permit cũ có còn dùng sau Mover/Leaver? |

Một ví dụ kiểm soát:

~~~text
ALLOW APPROVE_INVOICE(invoice) IF
    subject.employmentStatus == ACTIVE
    AND subject.organizationId == invoice.organizationId
    AND subject.hasRole("InvoiceApprover", invoice.costCenter)
    AND invoice.createdByIdentityId != subject.identityId
    AND session.authenticationAssuranceMeetsPolicy
    AND noHigherPriorityDeny
~~~

**PDP trả Permit không chứng minh endpoint đã thực hiện kiểm tra đúng**, đặc biệt nếu có API batch, background job hoặc local admin path bỏ qua PEP. Audit cần kiểm thử **positive/negative outcomes ở resource server**.

## 16. Identity Provider, SSO và MFA trong audit scope

Đối với **IdP/SSO/MFA**, scope có thể gồm:

- Identity registration, account enable/disable và recovery.
- Chính sách authentication và nhóm dùng **phishing-resistant MFA** cho hành động nhạy cảm.
- Enrollment, removal và reset authenticator.
- Authentication successes/failures, risky sign-in, session issuance.
- Federation configuration: issuer, audience, trust, certificates.
- Session revocation, sign-out và step-up policy.
- Guest/federated identities và mapping từ external issuer.
- Privileged IdP administration/consent changes.

**SSO thành công không tự chứng minh app authorization hợp lệ**, và **MFA thành công không chứng minh SoD hoặc least privilege**. Audit scope phải phân biệt **authentication assurance** với **resource permission**.

Nếu IdP unavailable, **emergency access** có thể đi theo đường dự phòng; audit cần xem cả **fallback identity, session, log và hậu kiểm**, không chỉ log đăng nhập IdP chính.

## 17. SCIM provisioning và deprovisioning trong audit scope

**SCIM 2.0** thường được dùng để đồng bộ **Users/Groups** giữa hệ thống có thẩm quyền và Service Provider. Audit nên kiểm tra cả **ý định** và **kết quả thực thi**:

| Hạng mục | Evidence cần xem |
| --- | --- |
| **Create** | Request origin, externalId mapping, HTTP result, target id |
| **Update/PATCH** | Attribute delta, role/group membership trước/sau |
| **Deactivate** | active=false hoặc hành vi tương đương theo target contract |
| **Delete** | Chính sách retention và semantics xóa ở Service Provider |
| **Retry/idempotency** | Không tạo tài khoản trùng hoặc tái cấp quyền cũ |
| **Error/timeout** | 409 conflict, 429, 5xx, unknown outcome và reconcile |
| **Direct target changes** | Quyền local được cấp ngoài SCIM |
| **Post-provision readback** | Account/Group thực tế và effective access |

**SCIM success không đồng nghĩa OAuth refresh token, PAT, session hoặc SaaS local ACL đã bị thu hồi**, vì các cơ chế này thường nằm ngoài SCIM core. Scope kiểm toán Leaver nhạy cảm phải mở rộng sang **target token/session policy**.

SCIM User/Group cũng **không phải danh mục toàn bộ machine identities**; service principal hoặc certificate lifecycle có thể nằm ngoài chuẩn và cần nguồn dữ liệu khác.

## 18. OAuth/OIDC, token và credential audit scope

Với ứng dụng sử dụng token, audit phải phân biệt:

| Đối tượng | Rủi ro/câu hỏi |
| --- | --- |
| **OIDC ID token** | Client kiểm tra issuer/audience/signature/exp đúng chưa, có nhầm access token? |
| **OAuth access token** | Scope/audience/exp, sender constraint và resource authorization |
| **Refresh token/grant** | Rotation, inactivity/absolute TTL, revoke, token family reuse |
| **Client secret/certificate** | Owner, expiry, storage, rotation và compromised key |
| **PAT/API key** | Long-lived access ngoài IdP, lastUsed và revoke |
| **JIT/PAM token/lease** | Có vượt approved window không? |
| **Token introspection/cache** | Active state có đủ mới sau revoke không? |
| **JWT signing key/JWKS** | Issuer trust, key rotation, alg allowlist và overlap |
| **Machine/workload federation** | Issuer, subject, audience và role trust scope |

**JWT exp chỉ là giới hạn thời gian**, không phải chứng cứ đã thu hồi trước hạn. Scope audit cần xác định **revocation SLA, cơ chế chặn token cũ và thực tế Deny tại API**.

**Không lưu raw access/refresh token hoặc private key làm audit evidence**. Thay bằng token reference/jti khi đáng tin và có sẵn, metadata scope/exp, decision logs và bằng chứng thử quyền được ủy quyền.

## 19. Non-human account và workload identities

Một cuộc kiểm toán chỉ dựa trên HRIS có thể bỏ qua nhiều principal có quyền cao:

| Đối tượng | Bằng chứng thích hợp |
| --- | --- |
| **Service account** | Owner, purpose, role, vault secret, target account |
| **Cloud service principal** | IAM policy, trust/assume role, credential metadata |
| **Managed identity** | Workload binding, permissions, resource scope |
| **CI/CD bot** | Repository/branch/environment trust, deploy roles |
| **Kubernetes ServiceAccount** | Namespace, RoleBinding/ClusterRoleBinding, token projection |
| **RPA/integration user** | Bot account, shared credentials, SaaS ACL |
| **Device/machine certificate** | CA issuance, owner, revocation, active trust |
| **Recovery automation** | Emergency trigger, privileged scope, audit |

Audit cần xác định **owner còn hoạt động, service catalog purpose, access expectation và credential lifecycle**. Một owner Leaver không tự chứng minh workload phải bị xóa ngay, nhưng **shared secret hoặc quyền người cũ** phải được xử lý theo rủi ro.

**Managed/federated identity không đồng nghĩa least privilege** nếu trust cho phép mọi repository assume role admin. Review phải kiểm tra cả **permission policy và trust subject**.

## 20. Device identity và các quan hệ thiết bị–người–quyền

Thiết bị có thể là tín hiệu trong conditional access, nhưng nó có vòng đời riêng:

- **Device registration** và proof of possession/attestation nếu cần.
- **MDM/UEM enrollment** và posture freshness.
- **Device certificate/key** cùng expiry/rotation/revocation.
- **Custodian/owner** và bàn giao khi user Mover/Leaver.
- **Lost/stolen/suspended/retired** lifecycle events.
- **SSO session và local app token** trên thiết bị.
- **PEP validation** khi truy cập resource nhạy cảm.

Một thiết bị **REGISTERED** nhưng **NONCOMPLIANT** không tự đủ điều kiện truy cập; device certificate được revoke không chắc làm mọi session hiện hữu kết thúc ngay. Audit scope về **device-bound access** cần đọc cả registry, MDM, PKI và resource server.

**Không dùng serial number/MAC address đơn lẻ như bằng chứng danh tính mật mã**. Chúng có thể bị thay đổi hoặc giả mạo; PoP/attestation cũng chỉ chứng minh những claims trong phạm vi được kiểm tra.

## 21. Privileged access, PAM/JIT và break-glass

**Privileged access** thường có mức rủi ro cao hơn do khả năng đổi role, đọc secret hoặc tắt giám sát. Audit scope phải bao gồm:

1. **Privileged inventory:** tất cả role/admin account, standing grants và eligibility.
2. **Approval và activation:** ai duyệt, theo ticket/policy nào, phạm vi nào?
3. **Authentication assurance:** xác thực đủ mạnh, step-up khi yêu cầu.
4. **PAM/JIT lease:** start/end, maximum duration, session binding.
5. **Command/API/session evidence:** đã thực hiện những hành động nhạy cảm nào?
6. **SoD:** operator có thể tự cấp quyền và xóa log không?
7. **Emergency path:** break-glass được thiết kế, giới hạn và hậu kiểm?
8. **Credential creation:** có PAT/API key/long-lived session phát sinh trong phiên không?
9. **Revoke và verify:** hết lease phải mất quyền tại target.
10. **Independent review:** người khác kiểm tra kết quả theo policy.

**Một video PAM không tự bao phủ API, automation hoặc truy cập trực tiếp ngoài gateway**. Nếu audit claim “mọi privileged action đều được giám sát”, phải có test/coverage đối với **mọi đường truy cập có thể dùng**.

## 22. Segregation of Duties, ngoại lệ và compensating controls

Kiểm toán **SoD** phải xét cả:

- **Static SoD:** một identity có thể đồng thời nắm những role xung đột nào?
- **Dynamic SoD:** có thể thực hiện hai bước xung đột trên **cùng giao dịch** không?
- **Approval independence:** người yêu cầu có tự phê duyệt không?
- **Effective capability:** role gián tiếp, impersonation hoặc service account có tạo đường bypass?
- **Exception:** đã có risk owner, scope, TTL và phê duyệt độc lập?
- **Compensating control:** có thực thi thật, đúng frequency và có audit?
- **Expiry/remediation:** ngoại lệ đã hết hạn có còn quyền xung đột không?

Ví dụ, người giữ cả **InvoiceCreator** và **InvoiceApprover** có thể là static conflict; nếu workflow backend chặn **actor == invoice.createdBy**, rủi ro tự duyệt giao dịch được giảm bằng dynamic SoD. Audit phải kiểm tra **hành vi tại giao dịch**, không chỉ tên nhóm.

**Ngoại lệ được phê duyệt không xóa bản chất rủi ro SoD**. Một số policy có hard deny không được miễn trừ; audit phải phân biệt **approved controlled exception** và **unapproved violation**.

## 23. Access recertification nằm trong scope thế nào?

Đối với **Access Recertification**, audit không chỉ đếm số reviewer đã click:

| Bước | Điều phải chứng minh |
| --- | --- |
| **Campaign population** | Đã đưa đúng các identity/entitlement vào review? |
| **Snapshot quality** | Quyền và owner ở thời điểm chụp có đáng tin? |
| **Reviewer routing** | Ai có authority và độc lập theo risk/tenant? |
| **Decision** | KEEP, REVOKE, MODIFY, EXCEPTION có lý do rõ? |
| **Escalation** | Deadline/timeout có được xử lý đúng policy? |
| **Remediation** | REVOKE/MODIFY có được thực thi ở target? |
| **Verification** | Quyền thực tế sau thay đổi có đúng expected? |
| **Evidence** | Quyết định, source/version, actor/time, target readback |

Một campaign có completion 100% nhưng **mọi item KEEP trong vài giây** có thể là dấu hiệu review hình thức, không phải bằng chứng quyền đã phù hợp. Ngược lại, nhiều quyết định REVOKE chưa được thực thi cũng không được tính là quyền đã được loại bỏ.

## 24. Phân biệt expected, assigned, effective và used access

Đây là phân biệt then chốt khi xác định phạm vi:

| Lớp quyền | Câu hỏi | Bằng chứng |
| --- | --- | --- |
| **Expected** | Identity nên có quyền gì theo nhiệm vụ/phê duyệt? | HR/project/service catalog, access model |
| **Assigned** | Target đã cấu hình những role/group/ACL nào? | Cloud IAM, SaaS role, database GRANT |
| **Effective** | Trong điều kiện hiện hành, identity thực sự có thể làm gì? | Resource policy, PDP/PEP, token/session, negative tests |
| **Used** | Quyền nào đã được quan sát là sử dụng? | API/audit/session/job telemetry |

Ví dụ:

~~~text
Expected:  READ reports của Atlas
Assigned: READ reports Atlas + WRITE billing
Effective: READ Atlas; WRITE billing bị một explicit deny chặn
Used:     READ Atlas thường xuyên, không thấy WRITE billing

Audit finding:
    Assigned WRITE billing vượt expected access,
    dù hiện có deny và chưa quan sát thấy usage.
~~~

**Không thấy usage** không chứng minh quyền thừa; DR job có thể chỉ chạy mỗi quý hoặc log không đủ. **Không thấy effective Allow** ở một endpoint cũng không chứng minh mọi đường khác bị chặn.

Để kết luận quyền đã được thu hồi, scope phải nêu **những target và action nào đã được kiểm chứng**, không chỉ so role ở IdP.

## 25. Phạm vi theo tổ chức, tenant, environment và data classification

Một identity có thể được cấp quyền ở nhiều tổ chức, cloud account hoặc environment. Scope cần ràng buộc:

- **Legal entity, organizationId và tenantId**.
- **Production/staging/development**, tránh dùng dữ liệu dev để kết luận prod.
- **Cloud account/subscription/project/namespace**.
- **Data classification** như công khai, nội bộ, nhạy cảm, dữ liệu cá nhân.
- **Application/service boundaries** và chủ tài nguyên.
- **Regional/data residency constraints** nếu có nghĩa vụ áp dụng.
- **External delegation/cross-tenant trust**.

Ví dụ Leaver org-a không tự cho phép xóa mọi quyền org-b của cùng person nếu quan hệ org-b còn hợp lệ. Ngược lại, một service principal có role trên org-b dù chỉ phục vụ org-a cần được đưa vào scope **cross-tenant risk**.

Khi kiểm toán dữ liệu cá nhân hoặc thuộc quy định chuyên ngành, nên **xác định nghĩa vụ pháp lý/hợp đồng áp dụng với chuyên gia phụ trách**, không tự áp một quy tắc retention hoặc scope pháp lý chung cho mọi khu vực.

## 26. Phạm vi thời gian: period, cutoff, snapshot và event window

Kiểm toán IAM có nhiều loại thời gian khác nhau:

| Mốc | Ý nghĩa | Nguy cơ nếu bỏ qua |
| --- | --- | --- |
| **Audit period** | Giai đoạn được kiểm tra | Bỏ các event trước/sau kỳ mà có liên quan |
| **Event effectiveAt** | Sự kiện nghiệp vụ có hiệu lực từ lúc nào | Nhầm thời điểm HR nhập dữ liệu với ngày Leaver thật |
| **eventTime** | Nguồn báo hành động xảy ra lúc nào | Lệch giờ giữa systems |
| **receivedAt/ingestedAt** | Collector nhận/ghi event lúc nào | Nhầm event đến muộn là phát sinh mới |
| **Snapshot asOf** | Quyền tại một thời điểm | Quyền đã thay đổi sau snapshot |
| **Approval validFrom/validUntil** | Quyết định cấp quyền có hiệu lực | Provision quyền sau khi approval hết hạn |
| **Token exp/session end** | Thời hạn của credential/phiên | JWT cũ vẫn ALLOW sau Leaver |
| **VerifiedDenyAt** | Lúc kiểm thử chứng minh cắt quyền | Không thấy thời gian tồn dư thực tế |

### Ví dụ ranh giới kỳ

Audit period là **01/10/2026 00:00 đến trước 01/01/2027 00:00** theo múi giờ tổ chức. Một Leaver có **effectiveAt 31/12 23:55** nhưng target revoke lúc **01/01 00:20** phải được theo dõi qua ranh giới kỳ để đánh giá SLA, dù bước hoàn tất xảy ra ở kỳ sau.

**Không cắt chuỗi bằng chứng ngay ở cuối kỳ rồi kết luận “chưa thu hồi” hoặc “đã tuân thủ”** mà thiếu thời gian quan sát tiếp theo. Phạm vi có thể bao gồm một **follow-up window** cho các sự kiện phát sinh trong kỳ, được nêu minh bạch.

Nên chuẩn hóa timestamps thành **UTC/Instant có offset** và giữ timezone nghiệp vụ, cùng **source clock skew** nếu được đo. Một timestamp do client tự gửi chưa chắc đáng tin như mốc do hệ thống đích hoặc collector ghi.

## 27. Thiết kế scope dựa trên rủi ro và tính trọng yếu

**Risk-based scoping** ưu tiên phần có khả năng hoặc tác động kiểm soát thất bại lớn nhất, không đồng nghĩa bỏ những nhóm ít rủi ro ra khỏi inventory.

| Chiều rủi ro | Ví dụ mức cao |
| --- | --- |
| **Privilege** | Global admin, policy editor, secret reader, impersonation |
| **Data sensitivity** | Tài chính, dữ liệu cá nhân, production credentials |
| **Access exposure** | Cross-tenant trust, external guest, public API |
| **Lifecycle fragility** | Contractor hết hạn, owner Leaver, account orphaned |
| **Control weakness** | SCIM không bao phủ direct ACL, không có target readback |
| **Credential risk** | Long-lived PAT, password shared, static secret |
| **Change velocity** | Vai trò thay thường xuyên, nhiều Mover, pipeline động |
| **System criticality** | Billing, payments, IAM control plane, recovery tools |
| **Previous findings** | Regrant, SoD bypass, remediation trễ |
| **Visibility limitation** | Audit thiếu nguồn, không biết người dùng thật của shared account |

**Materiality/trọng yếu** là điều cần quy định theo mục tiêu và tổ chức: ví dụ một tài khoản read-only trong môi trường thử khác với **một service principal có thể tự cấp quyền production**. Không có điểm số chung có thể áp dụng cho mọi doanh nghiệp.

**Bỏ qua toàn bộ đối tượng khó kiểm tra vì thiếu log là sai hướng scoping.** Một gap lớn chính là finding hoặc giới hạn assurance cần trình bày, thường làm tăng mức ưu tiên chứ không phải loại khỏi phạm vi trong im lặng.

## 28. Kiểm toàn bộ hay lấy mẫu?

Phương pháp kiểm tra có thể gồm:

- **100% population (full-population test):** kiểm mọi item trong scope, phù hợp với truy vấn tự động và nhóm critical.
- **Risk-based/targeted sampling:** chọn trường hợp có đặc quyền, ngoại lệ, Leaver quá hạn hoặc bất thường.
- **Random/statistical sampling:** chọn ngẫu nhiên từ một population đủ tin cậy, với phương pháp và giả định được nêu rõ.
- **Stratified sampling:** chia theo tenant, role, loại identity, application hoặc risk tier rồi lấy mẫu trong từng nhóm.
- **Event-driven selection:** chọn những trường hợp phát hiện trong kỳ theo điều kiện mục tiêu.
- **Walkthrough/control design testing:** theo dõi một chuỗi thực thi từ request đến target để hiểu control có được thiết kế đầy đủ không.

Ví dụ minh họa, không phải chuẩn quy định:

~~~text
Population:
    4.000 user/access-change events
    120 privileged grants
    75 Leaver events

Test design:
    - 100% privileged grants và Leaver events qua automated control checks
    - Risk-based detail inspection các trường hợp failure/UNKNOWN
    - Stratified sample user changes theo app, role và organization
~~~

**Không thể kết luận toàn bộ population tuân thủ chỉ từ mẫu chọn theo convenience**. Nếu dùng mẫu thống kê, phải xác định population, phương thức chọn, kỳ dữ liệu, sai số và confidence theo thiết kế kiểm toán; không áp một mức phần trăm “10% là đủ” cho mọi trường hợp.

Khi có **exception/failure trong mẫu**, cần xử lý theo kế hoạch mở rộng kiểm tra hoặc đánh giá ảnh hưởng, thay vì bỏ qua vì “chỉ một trường hợp”.

## 29. Population completeness: mẫu số của kết luận đến từ đâu?

Một vấn đề nghiêm trọng trong audit IAM là **population không đầy đủ**. Nếu xuất user list từ IdP, ta có thể không biết local DB user hoặc cloud principal chưa được liên kết.

Một chương trình xác minh completeness cần:

1. **Lập danh mục target systems** từ CMDB/service catalog và phạm vi business process.
2. **Đối chiếu nguồn account** từ IdP, IGA, cloud IAM, SaaS, DB, OS, CI/CD, vault và PKI.
3. **Đối chiếu principal identifiers** theo issuer, tenant, accountId và identity type.
4. **So tổng số và biến động** theo từng nguồn/kỳ.
5. **Xác định duplicates, orphaned, unlinked và deleted-but-present**.
6. **Kiểm tra filter của export**, ví dụ chỉ ACTIVE accounts có bỏ Leaver/disabled cần audit không?
7. **Đối chiếu với telemetry và provisioning logs** để tìm identity xuất hiện ở target nhưng vắng trong inventory.
8. **Ghi gaps và mức tin cậy**, không sửa mẫu số theo cách làm kết quả đẹp hơn.

### Ví dụ

~~~text
IdP principals in scope:       1.250
SaaS local accounts:           1.312
Cloud service principals:         94
Inventory correlation:
    1.216 linked to human identities
       65 linked to service/workload owners
       81 need investigation

Không được kết luận "đã review 100% IAM accounts" chỉ vì
1.250/1.250 IdP principals có checkbox review.
~~~

Không thể cộng tổng thô các hệ thống thành số identity duy nhất vì **một identity có nhiều account**; phải trình bày cả **account-level denominator** và **identity-level denominator**.

## 30. Ma trận Scope × Control × Evidence

Một **audit coverage matrix** giúp phát hiện chỗ chưa có evidence:

| Control objective | Population | Authoritative source | Target evidence | Test |
| --- | --- | --- | --- | --- |
| Joiner đúng startAt | Employees mới | HRIS + IGA | IdP account + SaaS role | Không ALLOW trước startAt |
| Mover rút role cũ | Mover kỳ audit | Project/HR authority | Group/ACL/token state | Old action DENY |
| Leaver cắt quyền | Leaver + guest hết hạn | HRIS/sponsor | IdP, SCIM, PAT, SaaS API | Deadline đến effective Deny |
| SoD tự duyệt | Finance roles | SoD policy | Transaction actor/audit | Creator không approve chính mình |
| Privileged JIT | Admin identities | PAM policy/approval | Session + target role/action | Role hết hạn, audit đầy đủ |
| NHI owner | Service principals | Service catalog | Cloud/vault/CI/CD | Owner và role còn phù hợp |
| MFA assurance | Nhóm access nhạy cảm | Authentication policy | IdP/SSO sessions | Step-up đúng action |
| Recertification | High-risk entitlements | IGA campaign | Target role readback | REVOKE thực sự hoàn thành |
| Device access | Managed devices | MDM/registry | Device cert + PEP logs | Lost/suspended device DENY |

Ma trận cần thêm **coverage status, owner, extractedAt, policy version, limitation và reviewer**. Nếu một row chỉ có ticket approval mà thiếu target state, đánh dấu **PARTIAL**, không đánh dấu PASS.

## 31. Control assertions: tính hiện hữu, đầy đủ, hợp lệ và đúng thời điểm

Một kiểm toán có thể dùng các **assertions (khẳng định cần kiểm chứng)** khác nhau:

| Assertion | Câu hỏi | Ví dụ kiểm tra |
| --- | --- | --- |
| **Existence** | Quyền/account ghi trên hệ thống có thực sự tồn tại? | Target principal readback |
| **Completeness** | Có bỏ sót principal, grant hay sự kiện nào không? | Inventory reconciliation |
| **Validity/authorization** | Quyền có căn cứ và approval hợp lệ? | Owner/approver check |
| **Accuracy** | Role/scope/tenant có đúng decision? | Requested vs provisioned delta |
| **Timeliness** | Cấp/thu hồi có đúng mốc policy? | EffectiveAt vs verifiedAt |
| **Occurrence** | Hành động đã thực sự xảy ra hay chỉ được yêu cầu? | Action result/operationId |
| **Integrity** | Dữ liệu bị sửa/xóa ngoài quyền không? | Source provenance, retention/integrity checks |
| **Attribution** | Event thuộc actor/workload nào? | Verified identity, PAM session, token/client mapping |
| **Segregation** | Có sự kiểm tra độc lập cần thiết không? | Reviewer và transaction actor |
| **Effectiveness** | Control có ngăn đường sai tại target không? | Negative authorization tests |

**Một control có thể được thiết kế tốt nhưng không vận hành hiệu quả**. Ví dụ tài liệu quy định Leaver phải bị revoke trong một khoảng thời gian, nhưng connector liên tục timeout khiến role ở target còn hoạt động. Scope nên kiểm cả **design effectiveness** và **operating effectiveness**, theo mục tiêu audit đã chốt.

## 32. Những gì nằm ngoài phạm vi phải được nêu minh bạch

**Exclusion** là một quyết định có căn cứ về ranh giới, không phải một cách làm đẹp kết quả.

Ví dụ:

| Ngoài phạm vi | Lý do có thể hợp lệ | Hành động cần lưu |
| --- | --- | --- |
| Non-production test tenants | Chỉ kiểm toán production access | Ghi tenant list và loại trừ chính xác |
| Hệ thống mới sau cuối kỳ | Không hoạt động trong kỳ được kiểm | Bổ sung scope audit kỳ sau nếu cần |
| Một vendor SaaS không hỗ trợ session export | Evidence kỹ thuật chưa có | Đánh dấu assurance gap, đánh giá controls khác |
| Dữ liệu HR riêng tư không cần thiết | Giảm dữ liệu cá nhân | Chỉ lấy relation/status metadata cần thiết |
| Ứng dụng low-risk ngoài đợt chuyên đề | Risk-based plan | Đưa vào inventory và kế hoạch kiểm khác |

**Exclusion khác limitation**: loại ứng dụng dev khỏi scope là quyết định thiết kế; còn app production trong scope nhưng **không đọc được effective access** là limitation cần báo cáo. Không đổi tên limitation thành exclusion sau khi thấy dữ liệu xấu.

Mọi thay đổi scope đáng kể nên có **change record, risk owner/approver và ảnh hưởng tới kết luận**.

## 33. Quy trình xác định Audit scope

~~~mermaid
flowchart TD
    A["Định nghĩa audit objective và tiêu chí"] --> B["Lập inventory business services/tenants"]
    B --> C["Xác định identity population và permission paths"]
    C --> D["Phân loại risk/materiality"]
    D --> E["Chọn control objectives JML, access, SoD, PAM, NHI"]
    E --> F["Ánh xạ source authority và target evidence"]
    F --> G{"Coverage, permission và integrity đủ?"}
    G -->|"Chưa"| H["Ghi gap/limitation, tăng evidence hoặc thiết kế control thay thế"]
    H --> G
    G -->|"Đủ trong giới hạn"| I["Chốt period, population, sampling, exclusions"]
    I --> J["Owner phê duyệt scope/version"]
    J --> K["Thu thập snapshot và thử controls"]
    K --> L["Reconcile, findings và effective-access verification"]
    L --> M["Báo cáo assurance và giới hạn"]
    M --> N["Follow-up remediation theo mức rủi ro"]
~~~

**Scope xác định trước khi kiểm tra để giảm thiên lệch**, nhưng có thể được sửa khi phát hiện hệ thống chưa được liệt kê hoặc lỗ hổng population. Mọi thay đổi phải có lý do, thời điểm và tác động tới kết quả.

Một vòng kiểm toán không nhất thiết biến tất cả unknown thành known ngay; những **limitation chưa giải quyết** phải được giữ rõ trong báo cáo.

## 34. Evidence contract: thỏa thuận về dữ liệu cần lấy

Với mỗi nguồn, có thể ghi một **evidence contract**:

~~~yaml
sourceId: iam-prod-target-accounts
system: billing-saas
organization: org-a
environment: production
sourceOwner: finance-platform
collectorRole: audit-readonly
auditPeriod:
  startInclusive: "2026-10-01T00:00:00+07:00"
  endExclusive: "2027-01-01T00:00:00+07:00"
expectedFields:
  - targetAccountId
  - principalType
  - tenantId
  - accountState
  - assignedRoles
  - roleAssignmentVersion
  - observedAt
integrityControl:
  type: verified-export-checksum-and-provenance
collectionStatus: PENDING
coverage: UNKNOWN
privacyClass: CONFIDENTIAL
~~~

Đây là **YAML mẫu cho bài học**, không phải schema của sản phẩm hoặc cấu hình hệ thống thực. Nó nêu:

- Nguồn và người chịu trách nhiệm.
- Quyền truy vấn **read-only** phục vụ audit.
- Mốc thời gian và điều kiện lọc.
- Các trường bắt buộc, version/schema và cách phát hiện dữ liệu thiếu.
- Integrity/retention/access restrictions.
- Trạng thái collection và assurance.

Không yêu cầu xuất **password, private key, raw token, OTP seed hoặc toàn bộ hồ sơ HR**. Thiếu một trường quan trọng phải được biểu diễn **UNKNOWN**, không tự điền giá trị mong muốn.

## 35. Schema sự kiện audit phục vụ scoping

Một schema tổng quát có thể chứa:

| Nhóm | Trường | Công dụng |
| --- | --- | --- |
| **Event identity** | eventId, eventType, schemaVersion, sourceSystem | Phân biệt sự kiện và nguồn |
| **Actor** | actorIdentityRef, actorType, delegatedActorRef | Quy kết người/workload thao tác |
| **Beneficiary** | subjectIdentityRef, employmentRelationRef | Ai bị tác động bởi thay đổi quyền |
| **Target** | tenantId, resourceId, targetAccountId | Phạm vi quyền bị thay đổi |
| **Time** | eventTime, receivedAt, effectiveAt | Xác định thứ tự và độ trễ |
| **Authority** | requestId, approvalId, policyVersion | Vì sao hành động được phép |
| **Delta** | before/after role, scope, status ref | Quyền thay đổi thế nào |
| **Result** | requested, accepted, applied, denied, unknown | Phân biệt intent với outcome |
| **Correlation** | correlationId, traceId, sourceEventId | Nối chuỗi JML qua hệ thống |
| **Evidence** | sourceVersion, collectionHashRef, confidence | Chứng minh xuất xứ và hạn chế |

Ví dụ:

~~~json
{
  "eventId": "audit-iam-2026-0482",
  "eventType": "LEAVER_ACCESS_REVOKE_VERIFICATION",
  "sourceSystem": "identity-audit-service",
  "correlationId": "leaver-case-482",
  "actorIdentityRef": "iam-reconciliation-worker",
  "subjectIdentityRef": "iam-user-482",
  "employmentRelationRef": "emp-org-a-482",
  "tenantId": "org-a",
  "targetSystem": "billing-saas",
  "targetAccountRef": "saas-account-882",
  "requestedAction": "REVOKE_BILLING_APPROVER",
  "sourceEffectiveAt": "2026-11-23T10:00:00+07:00",
  "targetReadbackAt": "2026-11-23T10:04:00+07:00",
  "effectiveAccessResult": "DENY_VERIFIED_IN_TEST_SCOPE",
  "policyVersion": "leaver-revoke-v9",
  "sourceVersion": "hris-evt-2026-984",
  "testScope": "billing-api/org-a/approve",
  "limitations": ["OTHER_API_SESSIONS_NOT_OBSERVABLE"]
}
~~~

Ví dụ là **schema tự thiết kế**, không phải định dạng chuẩn SCIM/OIDC. Trường **DENY_VERIFIED_IN_TEST_SCOPE** giới hạn kết luận vào API được kiểm; không chứng minh tất cả ứng dụng đã Deny.

## 36. Correlation, lineage và nguồn gốc bằng chứng

Trong IAM phân tán, một sự kiện HRIS có thể đi qua IGA, IdP, SCIM connector và ứng dụng đích. Scope kiểm toán phải nối được chuỗi:

~~~mermaid
flowchart LR
    H["HRIS / sponsor event"] --> I["IAM/IGA expected access"]
    I --> A["Approval / policy / SoD"]
    A --> P["Provisioning / SCIM / target API"]
    P --> T["IdP, SaaS, cloud/DB assigned rights"]
    T --> R["PDP/PEP / token / effective rights"]
    H --> E["Audit evidence store"]
    I --> E
    A --> E
    P --> E
    T --> E
    R --> E
    E --> V["Independent auditor / control owner"]
    V --> F["Finding, remediation và follow-up"]
~~~

Các tham chiếu hữu ích:

- **sourceEventId**: event ban đầu, có version.
- **requestId/approvalId**: căn cứ quyết định.
- **grantId/targetAccountId**: quyền thực tế bị tác động.
- **correlationId/traceId**: nhóm workflow.
- **operationId**: job async, để phân biệt HTTP 202 Accepted với hoàn tất.
- **evidenceRef/hash/collectedAt**: xuất xứ của bản ghi kiểm toán.

**Header correlationId do client cung cấp không phải bằng chứng authorization**. Connector phải liên kết với actor/identity đã xác minh và state từ nguồn có thẩm quyền.

Không nối các event chỉ bằng username hoặc khoảng thời gian gần nhau nếu có nguy cơ nhầm người. **UNKNOWN_CORRELATION** là trạng thái hợp lệ khi không có khóa liên kết đủ tin cậy.

## 37. Evidence integrity, provenance và chain of custody

Phạm vi kiểm toán có thể đầy đủ về mặt danh sách, nhưng kết luận vẫn yếu nếu log có thể bị sửa/xóa bởi chính người có quyền bị kiểm tra.

Kiểm soát phù hợp gồm:

1. **Source identity và authenticated collection**, không tin dump do người bị kiểm toán tự sửa mà không xác minh.
2. **Collection timestamp và source version**, bảo toàn snapshot gốc.
3. **Append-only/retention-protected storage** khi được hỗ trợ.
4. **Hash/checksum, digital signatures hoặc signed checkpoints** theo mức cần thiết.
5. **Separation of duties** giữa privileged operator, log administrator và reviewer.
6. **Tamper evidence/gap detection**, giám sát ingestion và clock skew.
7. **Viewer access control và audit** đối với chính kho bằng chứng.
8. **Documented chain of custody** khi evidence phục vụ điều tra đặc biệt.

**Hash một file không tự chứng minh nội dung ở nguồn đã đầy đủ hoặc đúng**. Nếu người vận hành chỉ xuất 10 trong 100 account rồi ký hash, kiểm tra hash chỉ chứng minh 10 account đó không đổi sau xuất. Vì vậy cần **population completeness và source provenance**, không chỉ integrity checksum.

## 38. Quyền riêng tư, bảo mật dữ liệu và retention

Audit identity có thể chứa **employment history, sign-in metadata, device IDs, IP, resource names, access decisions và log hành động**. Thu thập phải có **mục đích, người được phép truy cập và giới hạn cần thiết**.

| Loại dữ liệu | Có thể cần | Cần tránh |
| --- | --- | --- |
| **HR status** | employmentRelationId, start/end, organization | Full hồ sơ cá nhân không liên quan |
| **Identity mapping** | Stable IDs, issuer/tenant, link provenance | Số giấy tờ cá nhân khi không cần |
| **Access rights** | Role, permission, scope, approval | Dữ liệu nghiệp vụ trong hồ sơ người dùng |
| **Token** | Token reference, issuedAt/exp, scope, outcome | Raw access/refresh tokens |
| **Credential** | Secret/certificate metadata, owner, rotation | Password, private key, OTP seed |
| **PAM sessions** | Session ID, action category, recordingRef | Phát tán recording chứa secret |
| **Audit logs** | Actor, action, resource, result, correlation | Toàn bộ request body có PII nếu không cần |

**Retention không có một con số chung cho mọi tổ chức**. Phải dựa trên quy định áp dụng, hợp đồng, mục tiêu kiểm toán, data classification và chính sách nội bộ; có thể có **legal hold** do người có thẩm quyền xác lập. Không mặc định “lưu vĩnh viễn là an toàn”.

**RBAC/ABAC cũng áp dụng cho người xem audit**. Auditor có quyền xem bằng chứng theo scope không mặc nhiên có quyền đọc mọi thông tin nhạy cảm của toàn bộ tenant.

## 39. Khi nguồn dữ liệu thiếu, lỗi hoặc đến muộn

Một nguồn không có log, connector timeout hoặc API chỉ trả một phần dữ liệu là **hạn chế bằng chứng**. Không thể dùng sự vắng mặt của dữ liệu để khẳng định không có quyền hoặc không có sự kiện.

| Tình huống | Phân loại hợp lý | Cách xử lý |
| --- | --- | --- |
| Collector không nhận log trong hai giờ | **EVIDENCE_GAP** | Xem buffer/target audit, đo lag và bảo toàn gap |
| SaaS export chỉ trả ACTIVE accounts | **POPULATION_INCOMPLETE** | Bổ sung disabled/deleted accounts liên quan kỳ audit |
| SCIM connector timeout | **TARGET_STATE_UNKNOWN** | Readback trước khi retry/kết luận |
| HRIS event tới muộn | **LATE_SOURCE_EVENT** | Giữ effectiveAt và receivedAt, tính SLA lại chính xác |
| User có hai account nhưng mapping mơ hồ | **IDENTITY_LINK_UNVERIFIED** | Điều tra, không gộp nhầm quyền |
| Token issuer revoke nhưng API vẫn ALLOW | **ENFORCEMENT_FAILURE** | Điều tra cached JWT/grant và PEP |
| PAM recording thiếu đoạn | **SESSION_EVIDENCE_PARTIAL** | Kiểm target actions/log độc lập |
| Audit row thiếu approver | **AUTHORITY_UNVERIFIED** | Kiểm workflow nguồn trước khi kết luận |

Các trạng thái như **PASS, FAIL, NOT_APPLICABLE, INDETERMINATE, UNKNOWN và NOT_TESTED** cần được định nghĩa rõ. **NOT_APPLICABLE** là kiểm soát thực sự không liên quan theo criteria; **NOT_TESTED/UNKNOWN** là thiếu kiểm tra hoặc bằng chứng, không tương đương PASS.

## 40. Quy trình thực hiện kiểm toán IAM trong phạm vi đã duyệt

Một kế hoạch thực thi có thể theo các bước:

1. **Scope approval:** chốt objective, criteria, population, tenant, thời gian, exclusions, risk và owner.
2. **Source mapping:** ghi nguồn có thẩm quyền cho relation, role, account, credential, session, action.
3. **Read-only evidence collection:** thu thập có phân quyền, lưu snapshot/source metadata.
4. **Population reconciliation:** đối chiếu IdP/IGA với target apps, cloud, local accounts và NHI.
5. **Risk stratification:** ưu tiên privileged, Leaver, SoD, orphaned, cross-tenant và token rủi ro.
6. **Control design test:** kiểm tra policy/workflow có định nghĩa đúng control không.
7. **Operating effectiveness test:** kiểm chứng các sự kiện và quyền được áp dụng đúng trong kỳ.
8. **Target effective-access validation:** thực hiện negative tests trên tài nguyên test được phép.
9. **Evidence challenge:** đối chiếu log, event/version/time, giải thích dữ liệu mâu thuẫn.
10. **Findings:** nêu tiêu chí, hiện trạng, tác động, nguyên nhân, bằng chứng và giới hạn.
11. **Remediation plan:** giao owner, mức ưu tiên, thay đổi dự kiến và verification.
12. **Report/sign-off:** công bố phạm vi thật đã kiểm, những phần không thể kết luận và kết quả.
13. **Follow-up:** kiểm tra remediation/rights sau khi thay đổi; không đóng chỉ vì ticket hoàn tất.

Mỗi bước có thể được automation hỗ trợ nhưng **người phụ trách kiểm toán và control owner** phải chịu trách nhiệm về tính phù hợp của phương pháp và kết luận.

## 41. Mã giả xác định population và ghi nhận coverage

Mã giả này minh họa cách thiết kế, không phải API thực thi trực tiếp:

~~~text
buildAuditPopulation(scope, authoritativeSources, targetSources):
    requireApprovedScopeVersion(scope)
    inventory = []

    for source in authoritativeSources + targetSources:
        result = collectReadOnlySnapshot(
            source,
            scope.timeWindow,
            scope.tenants,
            scope.identityTypes
        )
        recordCollectionProvenance(
            sourceId=source.id,
            extractedAt=result.extractedAt,
            sourceVersion=result.version,
            filters=result.filters,
            completeness=result.completeness
        )

        if result.failed or result.partial:
            createCoverageGap(
                source.id,
                scope,
                reason=result.failureOrPartialReason
            )

        inventory.addAll(result.validRows)

    correlated = correlateWithVerifiedNamespaces(
        inventory,
        keys=["issuer", "tenant", "accountId", "principalType"]
    )

    for item in correlated:
        if item.identityLinkAmbiguous:
            item.status = UNVERIFIED_IDENTITY_LINK

    expectedPopulation = deriveExpectedCoverageFromServiceInventory(scope)
    gaps = compareExpectedVsObservedSources(expectedPopulation, correlated)
    publishPopulationWithCoverageAndLimitations(correlated, gaps)
    return correlated
~~~

Điểm quan trọng: **không lọc những item đã phát hiện vấn đề ra khỏi mẫu số**. Ví dụ principal không có owner là một đối tượng review cần xử lý, không phải “invalid record” có thể bỏ qua.

## 42. Mã giả đánh giá một control assertion

~~~text
evaluateLeaverRevocation(case, scope):
    relation = loadAuthoritativeEmploymentRelation(case.relationId)
    if not relation.hasTerminationWithinScope(scope):
        return NOT_APPLICABLE_TO_THIS_CONTROL

    targetAccounts = resolveCorrelatedTargetAccounts(relation, scope.targets)
    if targetAccounts.mappingAmbiguous:
        return UNKNOWN_IDENTITY_CORRELATION

    findings = []

    for account in targetAccounts:
        expected = expectedAccessAfterTermination(relation, account)
        observed = readCurrentTargetState(account)

        if observed.unavailable:
            findings.add(UNVERIFIED_TARGET_STATE)
            continue

        if observed.permissionsConflictWith(expected):
            findings.add(RESIDUAL_ASSIGNED_ACCESS)

        test = performAuthorizedNegativeAccessCheck(
            account,
            scope.testResourcesFor(account),
            scope.verifiedCutoffTime
        )

        if test.cannotRun:
            findings.add(UNVERIFIED_EFFECTIVE_ACCESS)
        else if test.allowedUnexpectedly:
            findings.add(RESIDUAL_EFFECTIVE_ACCESS)
        else:
            recordScopeLimitedDenyEvidence(test)

    return summarizeByControlAndCoverage(findings)
~~~

**Phải tránh dùng tài khoản người đã Leaver để thực hiện thử nghiệm trái phép**. Negative tests cần được thiết kế với **test principal, test resource, cơ chế mô phỏng quyền hoặc cách kiểm tra được ủy quyền**. Không giả mạo token thật hoặc truy cập production không có phê duyệt.

**Kết luận “VERIFIED” chỉ phù hợp phạm vi quyền đã đọc và kiểm thử**. Nếu API không hỗ trợ readback session/JWT, cần ghi limitation thay vì tự suy chắc chắn mọi request sẽ Deny.

## 43. Từ audit finding tới remediation và xác minh

Một phát hiện tốt cần liên kết:

| Thành phần | Nội dung |
| --- | --- |
| **Criterion** | Quy tắc hoặc nghĩa vụ kiểm soát đã được xác định trước |
| **Condition** | Hiện trạng quan sát và nguồn dữ liệu |
| **Cause** | Nguyên nhân đã được xác minh hoặc giả thuyết cần điều tra |
| **Risk/impact** | Có thể dẫn đến gian lận, lộ dữ liệu, truy cập tồn dư thế nào |
| **Population/scope** | Bao nhiêu item, tenant, app, time window bị ảnh hưởng |
| **Evidence** | Event IDs, snapshot/source version, readback/operation refs |
| **Limitation** | Dữ liệu chưa có, quyền chưa kiểm, độ tin cậy |
| **Action** | Thu hẹp quyền, sửa mapping, rotate/revoke, bổ sung log |
| **Owner/due date** | Người chịu trách nhiệm và hạn xử lý |
| **Verification** | Expected target state và cách chứng minh |

Ví dụ:

~~~text
Finding: F-IAM-2026-021
Criterion: Leaver access must be revoked within approved SLA
Condition: SaaS direct ACL remained assigned after HR effectiveAt
Evidence: HR event H-92, SaaS role readback R-18, authorized test T-03
Scope: org-a/billing production, one affected relation
Risk: Residual ability to approve sensitive invoices
Action: Revoke ACL, review SCIM sync and access cache, reconcile other targets
Owner: Billing Platform + IAM
Status: REMEDIATION_PENDING
Close only when: target rights and relevant effective access verified
~~~

Nếu nguyên nhân mới chỉ là giả thuyết, phải ghi **CAUSE_UNCONFIRMED**, không khẳng định một connector lỗi trước khi kiểm chứng. **Risk owner** có thể chấp nhận một ngoại lệ được phép với điều kiện rõ, nhưng không làm biến mất lịch sử finding.

## 44. KPI và thước đo chất lượng audit scope

| KPI | Ý nghĩa | Cảnh báo diễn giải |
| --- | --- | --- |
| **Source inventory coverage** | Tỷ lệ target systems có dữ liệu trong scope | Thiếu CMDB khiến mẫu số sai |
| **Account correlation coverage** | Tỷ lệ target accounts ánh xạ được identity/owner | Không tự gộp mapping thiếu chắc chắn |
| **Population completeness gaps** | Số nhóm đối tượng chưa có đủ bằng chứng | Không tính UNKNOWN là PASS |
| **Control test coverage** | Control assertions được kiểm theo scope | 100% checklist không chứng minh effectiveness |
| **Privileged/Leaver coverage** | Các nhóm high risk đã kiểm bao nhiêu | Cần xét quyền gián tiếp/NHI |
| **Access review decision quality** | Decision có lý do và reviewer authority | Bulk KEEP có thể là rubber-stamping |
| **Time to verified revocation** | Từ cutoff tới effective Deny được chứng minh | Không chỉ đo lúc gửi SCIM PATCH |
| **Unverified-remediation ratio** | Thay đổi chưa đọc lại được target | UNKNOWN là finding/limitation |
| **Residual-access findings** | Trường hợp quyền trái expected vẫn còn | Phân loại assigned vs effective |
| **SoD exception coverage** | Ngoại lệ có approval/control/expiry và audit | Ngoại lệ không đồng nghĩa rủi ro bằng 0 |
| **Log integrity/gap rate** | Phần event thiếu hoặc bị trễ/chỉnh sửa nghi vấn | Không suy im lặng là an toàn |
| **Repeat-finding rate** | Kiểm soát tiếp tục lỗi sau remediation | Cần sửa nguyên nhân hệ thống |

### Ví dụ công thức

~~~text
Observed system coverage =
    số target systems trong scope có evidence hợp lệ
    / tổng target systems được xác định trong approved scope

Verified revocation rate =
    số remediation revoke có target readback và effective checks đạt
    / tổng remediation revoke cần kiểm chứng trong scope

Unverified account-link ratio =
    số target accounts còn UNKNOWN identity/owner correlation
    / tổng target accounts đã thu thập và thuộc scope
~~~

Phải công bố **định nghĩa mẫu số, kỳ dữ liệu, source coverage và điều kiện PASS**. Một dashboard có tỷ lệ cao không tự chứng minh không còn rủi ro, nhất là nếu ứng dụng khó quan sát đã bị loại khỏi denominator.

## 45. Các anti-pattern khi xác định Audit scope

| Anti-pattern | Rủi ro | Cách cải thiện |
| --- | --- | --- |
| “Audit toàn IAM” nhưng chỉ export IdP users | Bỏ sót local account/NHI/PAT | Inventory đa nguồn, scope matrix |
| Chỉ kiểm ACTIVE accounts | Bỏ disabled/Leaver cần kiểm | Include lifecycle states và effective window |
| Chỉ xem approvals | Không thấy quyền target khác decision | Readback + resource enforcement |
| Chỉ xem role trực tiếp | Bỏ hierarchy, trust, direct ACL | Permission path analysis |
| Coi no-usage là no-access | Bỏ quyền chưa dùng/telemetry gaps | Phân biệt assigned/effective/used |
| Mọi quyền được duyệt đều được xem là hợp lệ | Overprivilege hoặc SoD có thể tồn tại | Risk/least privilege independent tests |
| Kết luận đạt khi SCIM success | Token/session/local ACL vẫn hoạt động | Reconciliation và negative tests |
| Không xác định timezone/cutoff | Sai SLA Leaver/Mover | EffectiveAt và source/received timestamps |
| Chọn mẫu chỉ từ báo cáo sẵn | Population bias | Source reconciliation và sampling documented |
| Chỉ audit người, bỏ workload | M2M admin không owner | NHI/workload/device inventory |
| Cho người bị kiểm soát tự xuất, tự sửa log | Evidence không độc lập | Source-authenticated collection/SoD |
| Exclude nguồn thiếu dữ liệu không báo | Kết luận assurance quá rộng | Report limitation và risk owner |
| Thu hết raw tokens để “đủ bằng chứng” | Tạo credential leakage | Metadata, tokenRef, privacy controls |
| Đóng finding khi ticket CLOSED | Quyền còn hoạt động | Verified target state và action Deny |
| Dùng một policy version hiện tại cho sự kiện cũ | Kết luận sai theo thời điểm | Retain historical policy/version |
| Không kiểm tra quyền reviewer | Self-approval/rubber stamp | Authority và SoD checks |

**Audit scope là một cam kết về ranh giới của kết luận.** Giấu những giới hạn dữ liệu hoặc thay đổi phạm vi sau khi thấy kết quả sẽ làm giảm giá trị của báo cáo, kể cả khi công cụ báo không có lỗi.

## 46. Bộ kiểm thử Audit scope trong IAM

| Test | Tình huống | Kết quả mong đợi |
| --- | --- | --- |
| T01 | Scope nói toàn bộ IAM nhưng không có local DB accounts | Báo population gap, không PASS toàn bộ |
| T02 | Employee có hai tài khoản IdP và admin | Cả hai được map đúng person/relation |
| T03 | Service principal không có HR owner | Vẫn nằm trong NHI scope và có finding |
| T04 | Audit export chỉ ACTIVE accounts | Phát hiện thiếu disabled/Leaver |
| T05 | Leaver trước cuối kỳ, revoke xảy ra sau kỳ | Follow-up window kiểm tra SLA |
| T06 | HR eventTime và receivedAt lệch nhau | Tính cutoff theo source effectiveAt |
| T07 | User Mover Atlas → Nova còn direct ACL Atlas | Finding residual assigned access |
| T08 | JWT cũ vẫn gọi API sau Leaver | Finding residual effective access |
| T09 | SCIM deactivate success nhưng PAT còn ALLOW | Không kết luận deprovision hoàn tất |
| T10 | Reviewer tự duyệt role admin của mình | SoD violation/exception check |
| T11 | Một token sai audience nhưng exp còn hạn | API verifier Deny |
| T12 | IdP role thấp, nested group cấp admin | Scope nhận diện effective permission path |
| T13 | ABAC policy Deny ở UI nhưng batch API vẫn Permit | Integration test phát hiện PEP gap |
| T14 | NHI có cloud role hẹp nhưng trust wildcard | Finding về trust overbreadth |
| T15 | Break-glass qua local admin ngoài PAM | Scope ghi đường bypass và evidence bổ sung |
| T16 | PAM video đủ nhưng không có API action logs | Không tự khẳng định coverage tất cả action |
| T17 | Device LOST, chứng chỉ còn được VPN chấp nhận | Finding trust/revocation |
| T18 | Guest contract hết hạn nhưng account active | Review sponsor/endAt và access |
| T19 | Reviewer Leaver nhưng approval callback tới muộn | Invalid authority hoặc revalidation |
| T20 | Target connector timeout khi revoke | Status UNKNOWN, retry có readback |
| T21 | Một người có employment org-a và org-b | Không xóa nhầm quyền còn hợp lệ org-b |
| T22 | Event từ tenant khác có cùng username | Không gộp sai identity |
| T23 | Evidence snapshot không có extractedAt | Đánh dấu freshness/traceability gap |
| T24 | Chọn mẫu ngẫu nhiên từ inventory thiếu hệ thống | Không tuyên bố population-complete |
| T25 | Một control chỉ có design doc nhưng không có operating logs | Không đánh PASS effectiveness |
| T26 | Collector outage 2 giờ | Ghi evidence gap, đối soát source buffer |
| T27 | Auditor có quyền sửa log nguồn | Kiểm tra integrity/SoD và independence |
| T28 | Key rotation đã xong nhưng role OrgAdmin còn | Finding least privilege vẫn tồn tại |
| T29 | Campaign 100% KEEP nhưng nhiều quyền thừa | Review quality không đạt theo evidence |
| T30 | REVOKE ticket closed nhưng target vẫn gán role | Không VERIFIED_CLOSED |
| T31 | Leaver có old approval regrant sau revoke | Finding event ordering/state version |
| T32 | Account có tên khác giữa app và IdP | Correlation theo stable ID, source/tenant |
| T33 | Policy version đổi sau snapshot | Revalidate kết luận/giữ historical version |
| T34 | Device registered nhưng MDM NONCOMPLIANT | Conditional access scope đánh giá riêng |
| T35 | Nguồn thiếu session revocation visibility | Report limitation, không suy complete |
| T36 | Raw refresh token xuất hiện trong evidence | Redaction/security incident theo playbook |
| T37 | Audit chỉ kiểm demo/test tenant nhưng báo production | Phát hiện scope mismatch |
| T38 | Hệ thống mới bổ sung giữa kỳ | Scope change với lý do/time và owner |

**Kiểm thử nên dùng môi trường và tài nguyên được ủy quyền**; không sử dụng tài khoản thật đã Leaver hay token lộ lọt để thực hiện truy cập trái phép. Với hành động nguy hiểm, dùng **policy simulation, test principal và endpoint test có kiểm soát**.

## 47. Tình huống thực hành: kiểm toán quyền truy cập hệ thống thanh toán

**Bối cảnh:** Tổ chức **org-a** muốn kiểm toán IAM cho hệ thống thanh toán production trong một quý. Dịch vụ có IdP tập trung, provisioning bằng SCIM, OAuth API, cloud IAM và một integration bot cũ. Có tình trạng một số nhân viên chuyển dự án và một nhà thầu hết hợp đồng.

### 47.1. Xác định objective và scope

Mục tiêu: xác định liệu danh tính có được cấp quyền phù hợp, Mover/Leaver được thu hồi kịp thời, mọi principal đặc quyền có owner/phê duyệt và các quyền tồn dư được phát hiện.

| Chiều | Quyết định scope |
| --- | --- |
| **Tenant** | org-a |
| **Environment** | production payments |
| **Population** | Employees, contractors, guests, admin, service accounts, OAuth clients |
| **Systems** | HRIS, IGA, IdP, SCIM billing SaaS, payments API, cloud IAM, vault |
| **Controls** | JML, request/approval, least privilege, SoD, PAM, token revoke |
| **Period** | Quý được chọn với follow-up cho event cuối kỳ |
| **Risk priority** | Global admin, payment approver, NHI/PAT và Leaver |
| **Exclusion** | Non-production sandbox; ghi rõ không dùng kết quả cho sandbox |

### 47.2. Xây population từ nhiều nguồn

Giả sử:

~~~text
HRIS relations in scope:             600
IdP accounts linked to people:      615
SaaS target accounts:               640
Cloud service principals:            24
Local emergency accounts:             2
Accounts with unverified linkage:    17
~~~

**Các số lượng này có thể chồng lấn**. Không cộng ra “1.881 identities” vì một person có thể có nhiều accounts, và cloud principals là một loại khác.

Auditor phải giải thích **17 mapping chưa xác minh**, không loại bỏ để báo cáo 100% matched.

### 47.3. Phát hiện từ Joiner và Mover

- Một nhân viên Joiner được cấp role PaymentApprover trước effective startAt: cần kiểm role có thể sử dụng trước ngày hợp lệ hay bị deny bởi policy.
- Một nhân viên Mover từ team Finance sang Support vẫn giữ **direct SaaS ACL ApprovePayment** dù IdP group đã gỡ: đây là **assigned-access drift**; kiểm tra API để xác định effective exposure.
- Hai reviewers tự duyệt quyền đặc quyền của chính họ: cần SoD/approval evidence.

### 47.4. Phát hiện từ Leaver và OAuth

Một contractor có contractEndAt 10:00. IGA gửi SCIM deactivate lúc 10:02, IdP disabled lúc 10:03, nhưng API vẫn chấp nhận **PAT cũ** ở một endpoint lúc 10:06.

~~~text
Expected at cutoff: contractor cannot approve payments
Observed:
    HRIS/sponsor expired             = TRUE
    IdP disabled                     = TRUE
    SCIM deactivation accepted       = TRUE
    SaaS PAT status                  = ACTIVE
    Payment API action test          = unexpected ALLOW

Finding: RESIDUAL_EFFECTIVE_ACCESS
Close condition: PAT revoked and relevant API paths Deny verified
~~~

Nếu policy có SLA khác cutoff tức thời, phải **đối chiếu đúng deadline đã được phê duyệt** khi xác định vi phạm. Dù vậy, quyền còn ALLOW là tín hiệu cần xem xét; không được che vì SCIM trả success.

### 47.5. Non-human account và quyền gián tiếp

Integration bot **svc-ledger-sync** có owner cũ đã Leaver, được cấp **BillingReader** nhưng cũng có quyền đọc secret administrator ở vault. Audit yêu cầu:

1. Xác minh service còn chạy và cần những action nào.
2. Chuyển owner sang team hiện hành nếu workload hợp lệ.
3. Thu hẹp vault/role/trust và rotate credential theo risk.
4. Kiểm tra mọi SaaS/API keys liên quan và negative tests.
5. Ghi finding về **indirect privilege escalation** dù tên role là Reader.

### 47.6. Báo cáo và giới hạn

Kết luận có thể ghi:

> Trong phạm vi org-a payments production và kỳ đã kiểm, chương trình phát hiện một số sai lệch về quyền Mover, thu hồi token Leaver và non-human identity ownership. Việc xác minh effective access đã thực hiện trên các API được liệt kê. Những phiên hoặc tài khoản đích chưa hỗ trợ readback được ghi là limitation, không được coi là đã kiểm chứng thu hồi.

Đây là **kết luận ví dụ**, không phải kết quả kiểm toán thật của một tổ chức.

## 48. Câu hỏi tự kiểm tra

**Câu 1: Nếu audit chỉ kiểm các tài khoản nhân viên trong IdP, có được gọi là audit toàn bộ IAM không?**

**Trả lời:** Không. Cần xét những hệ thống/tài khoản khác như local SaaS, DB, cloud, NHI, PAT, device và guest hoặc công khai rõ chúng nằm ngoài scope.

**Câu 2: Scope chỉ định Leaver kỳ tháng 12; revoke xảy ra ngày 1/1 thì có được bỏ qua không?**

**Trả lời:** Không nếu nó là kết quả của sự kiện Leaver trong kỳ và liên quan SLA. Nên có follow-up window và ghi rõ ranh giới.

**Câu 3: 100% access review items đã bấm KEEP có chứng minh quyền hợp lệ?**

**Trả lời:** Không. Cần kiểm reviewer authority, justification, risk/SoD và effective-access evidence.

**Câu 4: Vì sao phải phân biệt expected, assigned, effective và used access?**

**Trả lời:** Vì quyền đã duyệt có thể khác quyền được gán; quyền được gán có thể bị policy Deny; log sử dụng không bao phủ toàn bộ khả năng có thể thực hiện.

**Câu 5: Nếu không có log dùng một API key 90 ngày, có thể kết luận key vô hại?**

**Trả lời:** Không. Có thể là job DR ít chạy, telemetry thiếu hoặc credential bị đánh cắp chưa sử dụng; cần owner và scope review.

**Câu 6: SCIM đã deactivate account, nhưng token JWT cũ vẫn ALLOW ở API. Audit có được PASS không?**

**Trả lời:** Không. Đó là rủi ro effective access tồn dư nếu vượt tiêu chí cutoff; cần kiểm token revocation/PEP và chứng minh Deny.

**Câu 7: “Không đọc được local account list” là exclusion hay limitation?**

**Trả lời:** Nếu hệ thống nằm trong approved scope thì đó là **limitation/gap**. Không đổi thành exclusion chỉ để tránh báo cáo điểm yếu.

**Câu 8: Một kiểm thử Deny trên API A có chứng minh quyền đã mất ở API B không?**

**Trả lời:** Không. Kết luận chỉ thuộc endpoint/action/resource đã thử; phải ghi coverage và hạn chế.

## 49. Checklist chốt Audit scope

| Câu hỏi | Bằng chứng/đầu ra cần có |
| --- | --- |
| Đã nêu audit objective và criteria? | Control objectives và policy references |
| Đã có owner/approver cho phạm vi? | Approved scope version |
| Đã chọn organization, tenant, environment? | Target inventory và scope filters |
| Đã nêu resource/action nhạy cảm? | Permission catalog và data classification |
| Đã định nghĩa time period và cutoff? | UTC/offset, effectiveAt, follow-up window |
| Đã phân biệt human/NHI/device/guest? | Population taxonomy và counts |
| Đã đối chiếu IdP với local/cloud/SaaS accounts? | Account correlation và unknown mappings |
| Đã xác định source authority từng thuộc tính? | HRIS/CMDB/vault/IdP/target source map |
| Đã kiểm Joiner start và birthright? | Source verification, account/role grant events |
| Đã kiểm Mover old-role revoke? | Role delta và target rights |
| Đã kiểm Leaver session/token/PAT? | Source cutoff, revoke và effective Deny |
| Đã gồm access request/approval workflow? | Requester, approver, approval reason/scope |
| Đã kiểm least privilege và role inheritance? | Expected vs assigned/effective permissions |
| Đã gồm ABAC/PBAC/PDP/PEP? | Policy versions, trusted attributes và enforcement |
| Đã kiểm SoD/static/dynamic và ngoại lệ? | Transaction actor, risk approval, controls |
| Đã kiểm privileged/PAM/emergency paths? | Session log, JIT lease, direct API route |
| Đã kiểm OAuth/OIDC token và credential? | Issuer, audience, expiry, grants và revocation |
| Đã đánh giá SCIM target mapping? | User/Group/direct ACL readback |
| Đã gồm service principals/workload ownership? | NHI inventory, role/trust/secret lifecycle |
| Đã xem device registration/posture khi liên quan? | MDM/PKI/device security evidence |
| Đã xác minh recertification effectiveness? | Reviewer authority, decision, remediation status |
| Đã nêu sampling method và population denominator? | Full test/sample strategy và selection logic |
| Đã có coverage matrix? | Control × population × source × test |
| Đã ghi nguồn, extractedAt, version và confidence? | Evidence contracts và lineage |
| Có chống sửa/xóa evidence trái quyền? | Integrity controls, retention và SoD |
| Có giới hạn thu thập dữ liệu nhạy cảm? | Data minimization và access control |
| Có mô tả missing/partial evidence? | Gaps, UNKNOWN/NOT_TESTED và limitations |
| Có bảo đảm target readback sau revoke? | Assigned rights và effective Deny trong test scope |
| Có cách báo findings và remediation owner? | Criterion/condition/risk/action/dueAt |
| Có KPI và follow-up? | Coverage, revoke latency, repeat findings |
| Có change control cho scope? | Version, approval, impact of changes |

## 50. Tổng kết

**Audit scope** trong IAM là **ranh giới được xác định trước, có căn cứ và có thể kiểm chứng** về danh tính nào, hệ thống nào, quyền nào, sự kiện nào, khoảng thời gian nào và những kiểm soát nào được đánh giá. Nó không chỉ là danh sách log cần xuất, mà là **bản thiết kế cho kết luận kiểm toán có ý nghĩa**: xác định population, source authority, control criteria, phương pháp lấy mẫu, coverage, integrity và giới hạn bằng chứng.

Trong vòng đời **Joiner–Mover–Leaver**, **HRIS/nguồn bảo trợ** cung cấp quan hệ và mốc hiệu lực; **IAM/IGA** quản lý expected rights, request/approval và review; **IdP/SSO/MFA** xác thực; **SCIM** đồng bộ User/Group; **OAuth/OIDC, token và credential** có vòng đời khác; **RBAC/ABAC/PBAC với PDP/PEP** xác định và thực thi quyền tại resource; **non-human/service identities, device, privileged/PAM** có những đường truy cập riêng cần được đưa vào scope phù hợp.

Một audit đáng tin cậy phải **phân biệt expected, assigned, effective và used access; đối chiếu mọi nguồn thuộc phạm vi; ghi nhận UNKNOWN thay vì tự đoán; bảo vệ evidence và quyền riêng tư; kiểm tra quyền thực sự bị chặn tại hệ thống đích; công bố rõ những phần chưa thể xác minh**. Khi phạm vi được định nghĩa đúng và kiểm chứng minh bạch, tổ chức mới có cơ sở giảm **quyền thừa, SoD conflict, account mồ côi và quyền truy cập tồn dư** mà không nhầm việc “đã chạy báo cáo” với việc “đã kiểm toán có hiệu lực”.
