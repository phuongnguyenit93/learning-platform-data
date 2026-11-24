# Ghi log đầy đủ trong Emergency Access: dấu vết kiểm toán xuyên suốt truy cập khẩn cấp

## 1. “Ghi log đầy đủ” nghĩa là gì?

Trong **Identity and Access Management (IAM)**, **Emergency Access** là cơ chế cho phép một chủ thể được ủy quyền sử dụng **quyền truy cập đặc biệt trong tình huống khẩn cấp** khi quy trình thông thường không đáp ứng kịp nhu cầu bảo vệ an toàn hoặc khôi phục hoạt động. Một dạng phổ biến là **break-glass access**: mở đường truy cập dự phòng được thiết kế, bảo vệ và giám sát trước để phục hồi hệ thống khi cơ chế thông thường không sẵn sàng.

**Ghi log đầy đủ** không có nghĩa ghi mọi byte, mọi mật khẩu, toàn bộ dữ liệu người dùng hay video không giới hạn. Trong ngữ cảnh emergency access, điều đó có nghĩa hệ thống có **dấu vết đáng tin cậy, đủ liên kết, đủ chi tiết và đủ thời gian lưu** để trả lời được:

1. **Ai** hoặc workload nào yêu cầu, kích hoạt và sử dụng đặc quyền?
2. **Vì sao** cần truy cập khẩn cấp, gắn với incident/ticket nào?
3. **Ai phê duyệt** hoặc chính sách khẩn cấp nào cho phép kích hoạt?
4. **Khi nào** bắt đầu, nâng quyền, thực hiện thao tác và kết thúc?
5. **Trên hệ thống, tenant, tài nguyên và hành động nào** quyền được sử dụng?
6. **Quyền nào** đã được cấp, thay đổi hoặc thu hồi; có vượt phạm vi không?
7. **Hành động nào thực sự thành công**, hành động nào bị từ chối hoặc lỗi?
8. **Có bằng chứng độc lập** rằng các log không bị người có đặc quyền sửa, xóa hoặc làm thất lạc không?
9. **Ai đã rà soát sau sự kiện** và đã xử lý bất thường nào?
10. **Quyền có thật sự mất hiệu lực sau khi kết thúc** hay vẫn còn đường truy cập tồn dư?

Trong module quản lý vòng đời danh tính **Joiner–Mover–Leaver (JML)**, ghi log emergency access phải liên kết được **HRIS/nguồn bảo trợ, IAM/IGA, IdP/SSO, SCIM, RBAC/ABAC/PBAC, service account, hệ thống đích và kiểm toán**. Một account bị khóa sau Leaver nhưng vẫn giữ được PAT hoặc secret break-glass là vấn đề mà log ở riêng IdP có thể không phát hiện.

### Mục tiêu học tập

Sau bài này, người học có thể thiết kế bộ sự kiện kiểm toán xuyên suốt phiên emergency access; xây dựng schema log và correlation ID; bảo vệ log khỏi sửa/xóa, thất thoát và tiết lộ bí mật; xử lý gián đoạn log pipeline; kết nối PAM/JIT, IdP, OAuth/OIDC, SCIM và resource server; phát hiện hành vi bất thường, rà soát sau sự kiện và kiểm thử bằng chứng thu hồi đặc quyền.

## 2. Vì sao log của Emergency Access đòi hỏi kiểm soát cao hơn?

Emergency access thường được dùng trong điều kiện:

- Dịch vụ authentication hoặc IAM thông thường đang lỗi.
- Tài nguyên production cần khôi phục nhanh.
- Quyền được cấp cao hơn quyền hằng ngày, ví dụ administrator hoặc operator đặc biệt.
- Một số bước phê duyệt/SoD có thể dùng **quy trình khẩn cấp đã được chuẩn bị và chấp thuận trước**.
- Nhiều đội phải thao tác đồng thời và luồng thay đổi khó lường.
- Thời gian xử lý ngắn, dễ phát sinh lỗi vận hành.

Vì vậy, log cần hỗ trợ **kiểm soát trong thời gian gần thực** và **điều tra hậu sự kiện**. Nếu đặc quyền khẩn cấp cho phép sửa IAM policy, truy cập secret hay thay cơ chế giám sát, nguy cơ người thao tác **làm mờ chính dấu vết của mình** tăng đáng kể.

Tuy nhiên **không phải mọi emergency access đều được phép vượt MFA, SoD hay audit**. Quy trình phải quy định rõ những kiểm soát nào giữ nguyên, những đường khẩn cấp nào được phép thay thế và yêu cầu kiểm soát bù trừ tương ứng. Một nút “Emergency” trên portal không tự tạo thẩm quyền cho mọi hành động.

## 3. Phân biệt access log, audit log, security log và session evidence

| Loại dữ liệu | Ghi nhận chính | Ví dụ | Giới hạn |
| --- | --- | --- | --- |
| **Authentication log** | Đăng nhập, xác minh yếu tố, phiên | Sign-in của emergency operator | Không tự chứng minh đã sửa tài nguyên nào |
| **Authorization decision log** | PDP/PEP Permit, Deny, policy/version | Cho phép UPDATE trên production service | Quyết định cho phép không chứng minh thao tác thật đã hoàn thành |
| **Provisioning/audit log** | Tạo account, cấp/gỡ role, thay ACL | Activate emergency role | Connector success chưa chắc API thực thi đúng |
| **Application/action log** | Hành động nghiệp vụ và kết quả | Restart service, export report | Có thể thiếu actor nếu app dùng service account chung |
| **Infrastructure/control-plane log** | Thay đổi cấu hình cloud, IAM, network | Sửa policy hoặc tạo API key | Không phải mọi truy cập dữ liệu nằm ở control plane |
| **Data-access log** | Đọc, sửa, xóa hay xuất dữ liệu | SELECT bảng nhạy cảm, DOWNLOAD backup | Khối lượng lớn; cần phân loại, bảo vệ dữ liệu log |
| **Session recording** | Bản ghi phiên terminal/UI khi có hỗ trợ | Phiên RDP/SSH qua PAM gateway | Video không nhất thiết ghi đủ API và background job |
| **Security detection log** | Cảnh báo hành vi bất thường | Bất ngờ xóa log hoặc dùng role ngoài scope | Alert cần được người/automation đủ thẩm quyền xử lý |
| **Incident/change record** | Lý do, phê duyệt, người chịu trách nhiệm, review | Incident INC-2026-041 | Ticket không thay dấu vết hành động tại target |

**Ghi log đầy đủ cần nhiều nguồn phù hợp**, thay vì nhầm một video phiên hoặc một event “admin login success” với toàn bộ bằng chứng. Ngược lại, thu gom toàn bộ payload nhạy cảm không làm audit đáng tin hơn nếu thiếu actor, resource và correlation.

## 4. Các mốc phải có dấu vết trong một vòng đời Emergency Access

Một phiên nên được nhìn dưới dạng **chuỗi sự kiện**, không phải một dòng log duy nhất:

| Giai đoạn | Sự kiện tối thiểu nên xem xét | Điều cần chứng minh |
| --- | --- | --- |
| **Chuẩn bị** | Kiểm tra emergency identity, owner, policy, credential health | Đường dự phòng sẵn sàng và được quản lý |
| **Yêu cầu** | ACCESS_REQUESTED, incident reference | Người yêu cầu và nhu cầu cụ thể |
| **Xác minh** | IDENTITY_VERIFIED, AUTHENTICATION_SUCCEEDED/FAILED | Chủ thể được xác thực theo playbook |
| **Phê duyệt/điều kiện** | APPROVAL_GRANTED/DENIED hoặc EMERGENCY_POLICY_TRIGGERED | Căn cứ kích hoạt đủ thẩm quyền |
| **Kích hoạt** | PRIVILEGE_ACTIVATION_REQUESTED/SUCCEEDED/FAILED | Role, scope, tenant, thời hạn được mở |
| **Sử dụng** | SESSION_STARTED, ACTION_ATTEMPTED/SUCCEEDED/DENIED | Hành động thật và kết quả |
| **Thay đổi đặc quyền** | ROLE_CHANGED, POLICY_CHANGED, TOKEN_ISSUED | Những quyền mới phát sinh giữa phiên |
| **Kết thúc** | SESSION_ENDED, EMERGENCY_ACCESS_DEACTIVATED | Phiên đã đóng, grant không còn cần |
| **Thu hồi** | REVOKE_REQUESTED, REVOKED_AT_TARGET, DENY_VERIFIED | Đã chặn quyền thực sự |
| **Rà soát** | REVIEW_ASSIGNED, REVIEW_COMPLETED, FINDING_CREATED/CLOSED | Có hậu kiểm độc lập và xử lý bất thường |

Không phải mỗi sản phẩm dùng đúng những tên sự kiện này. Nên xây dựng **event taxonomy nội bộ** hoặc ánh xạ nguồn sản phẩm vào một schema chuẩn, đồng thời giữ bản ghi gốc để điều tra.

## 5. Kiến trúc luồng log: thu thập độc lập với người dùng đặc quyền

~~~mermaid
flowchart LR
    U["Emergency operator / workload"] --> P["PAM / JIT / Emergency broker"]
    U --> T["Protected target / API / database"]
    P --> A["Activation & approval audit"]
    T --> B["Target action & security audit"]
    I["IdP / SSO / Token verifier"] --> C["AuthN / token event"]
    D["IAM / IGA / SCIM"] --> E["Entitlement & lifecycle audit"]
    A --> Q["Trusted collectors / queue"]
    B --> Q
    C --> Q
    E --> Q
    Q --> W["Append-only or retention-protected log storage"]
    Q --> S["SIEM / detection / alert routing"]
    S --> R["SOC / Independent reviewer"]
    W --> R
    R --> F["Incident review / reconciliation / remediation"]
~~~

Kiến trúc có thể có nhiều vùng mạng hoặc collector, nhưng phải tránh đường phụ thuộc vòng: **người có emergency administrator đồng thời có thể xóa nơi chứa log độc lập**, hoặc **để logging phụ thuộc duy nhất vào chính IdP đang gặp sự cố**.

**PAM gateway ghi session** rất hữu ích nhưng chưa đủ nếu operator có thể đăng nhập trực tiếp qua SSH, RDP, cloud console, API key hoặc console quản trị ngoài gateway. Cần kiểm kê và kiểm thử **mọi đường truy cập được phép**.

## 6. Các nguyên tắc bất biến của một hệ thống audit đáng tin

1. **Attribution:** sự kiện có actor/subject đáng tin, không chỉ địa chỉ IP.
2. **Completeness theo phạm vi:** mọi bước trọng yếu được bao phủ, biết rõ đường nào chưa có log.
3. **Traceability:** liên kết được request → approval → activation → action → revocation → review.
4. **Integrity:** nhận biết được khi log bị sửa, xóa hoặc ghi đè trái phép.
5. **Availability:** log có thể được đọc khi cần điều tra, kể cả thời điểm hệ thống chính lỗi.
6. **Timeliness:** các sự kiện rủi ro cao được chuyển tới người giám sát theo độ trễ mục tiêu.
7. **Minimum sensitive data:** không làm lộ mật khẩu, token, secret hay nội dung nhạy cảm không cần thiết.
8. **Separation of duties:** người dùng đặc quyền không có quyền toàn diện để xóa log về chính họ.
9. **Time correctness:** timestamp, timezone và độ lệch đồng hồ có thể giải thích.
10. **Reconciliation:** có cách kiểm tra quyền đã thu hồi thực sự, không chỉ thấy ticket đóng.

**Đầy đủ không đồng nghĩa tuyệt đối không có mất log trong mọi sự cố**. Hệ thống phải đo **coverage, lag, gaps và các giới hạn bằng chứng**, công bố trung thực khi không đủ dữ liệu.

## 7. Schema sự kiện tối thiểu

Một schema chuẩn hóa nên có các nhóm trường sau:

| Nhóm | Trường điển hình | Lý do |
| --- | --- | --- |
| **Event identity** | eventId, eventType, eventVersion, sourceSystem | Truy xuất và deduplicate |
| **Time** | eventTime, recordedAt, receivedAt | Phân biệt thời điểm xảy ra và thời điểm thu nhận |
| **Actor** | actorIdentityId, actorType, issuer, subjectRef | Liên kết đúng người hoặc workload |
| **Session** | emergencySessionId, authenticationSessionRef | Xâu chuỗi hành động trong một phiên |
| **Justification** | emergencyRequestId, incidentId, reasonCode | Liên kết nhu cầu và căn cứ |
| **Authority** | approvalId, approverRef, policyId/version | Bằng chứng quyền kích hoạt |
| **Scope** | targetSystem, tenantId, resourceId/type, action | Nơi hành động diễn ra |
| **Outcome** | decision, result, reasonCode, errorClass | Thành công/thất bại/bị từ chối |
| **Change context** | beforeRef, afterRef, changeId, targetVersion | Phân biệt những thay đổi được áp dụng |
| **Correlation** | correlationId, traceId, parentEventId | Gắn log qua nhiều service |
| **Collection** | collectorId, receivedAt, validationStatus | Chứng minh log đến từ nguồn kiểm soát |
| **Sensitivity** | dataClassification, redactionProfile | Điều chỉnh bảo vệ và hiển thị log |

Không phải mọi event bắt buộc có đủ mọi trường, ví dụ **AUTHENTICATION_FAILED** có thể chưa có verified actorIdentityId. Cần mô tả rõ **field required theo eventType** và trạng thái UNKNOWN, tránh gán actor giả để làm schema trông đầy đủ.

### Event ID không thay correlation ID

**eventId** phân biệt một bản ghi; **correlationId** nhóm các sự kiện trong một yêu cầu/chuỗi xử lý; **emergencySessionId** gắn hoạt động với một phiên đặc quyền. Chúng không nên đồng nhất cho mọi event. Nếu một incident có nhiều phiên, mỗi phiên cần ID riêng nhưng cùng incident reference.

## 8. Ví dụ JSON: kích hoạt đặc quyền khẩn cấp

~~~json
{
  "eventId": "evt-emerg-2026-1001",
  "eventType": "EMERGENCY_ACCESS_ACTIVATED",
  "eventSchemaVersion": "v2",
  "eventTime": "2026-11-23T09:18:20+07:00",
  "recordedAt": "2026-11-23T09:18:20.125+07:00",
  "sourceSystem": "pam-broker",
  "correlationId": "inc-2026-041-activation",
  "incidentId": "INC-2026-041",
  "emergencyRequestId": "ea-2026-091",
  "emergencySessionId": "ea-session-091-a",
  "actor": {
    "identityId": "iam-user-482",
    "identityType": "EMPLOYEE",
    "employmentRelationId": "emp-org-a-01"
  },
  "target": {
    "system": "production-platform",
    "tenantId": "org-a",
    "resourceScope": "service-payments-prod"
  },
  "grant": {
    "roleId": "scoped-emergency-operator",
    "policyVersion": "emergency-policy-v7",
    "expiresAt": "2026-11-23T10:18:20+07:00"
  },
  "authority": {
    "decisionType": "PREAPPROVED_EMERGENCY_POLICY",
    "policyId": "critical-restoration-v3"
  },
  "result": "SUCCESS",
  "collector": "audit-collector-east-2"
}
~~~

Đây là **schema minh họa**, không phải chuẩn bắt buộc của SCIM, OIDC hay một PAM cụ thể. **PREAPPROVED_EMERGENCY_POLICY** chỉ hợp lệ nếu chính sách và điều kiện kích hoạt đã được phê duyệt thực tế. Một đoạn text do requester tự điền không biến thành sự kiện được phê duyệt.

## 9. Ai là actor? Person, session, delegated identity và workload

Vấn đề khó khi emergency access được sử dụng qua **shared administrator** hoặc **service account** là log của target có thể chỉ ghi **root/admin/service-user**, không cho biết **người thật đã thao tác**.

Nên phân biệt:

| Thực thể | Ví dụ | Vai trò trong audit |
| --- | --- | --- |
| **Person/worker** | person-482 | Người chịu trách nhiệm cuối theo identity đã xác minh |
| **Employment relation** | emp-482-org-a | Nguồn quyền, đơn vị và thời hạn công việc |
| **IAM identity** | iam-user-482 | Liên kết bền giữa người với tài khoản |
| **IdP subject** | issuer + sub | Chứng minh actor đăng nhập theo issuer |
| **PAM operator identity** | pam-operator-482 | Ai mở phiên đặc quyền |
| **Target admin account** | emergency-admin-prod | Tài khoản thực hiện thao tác trên hệ thống đích |
| **Delegated/impersonated actor** | service-acting-for-482 | Phân biệt dịch vụ và user gốc |
| **Workload identity** | svc-recovery-operator | Máy thực hiện job, cần owner/purpose riêng |

Một session dùng **shared root account** phải có **binding từ phiên PAM tới verified operator** và trường target account riêng. Không gán mọi hoạt động root mặc định cho người trực gần nhất theo lịch; cần bằng chứng phiên/session correlation.

Với **OIDC**, nên phân biệt **issuer + sub**, không ghép tài khoản xuyên issuer chỉ theo sub. Với **SCIM**, **SP id** khác **client externalId**; lưu namespace đúng. Email/username không đủ để ghép identity trong hệ thống nhiều tenant hoặc khi account được tái sử dụng.

## 10. Thời gian: eventTime, receivedAt, clock skew và thứ tự sự kiện

Trong sự cố, log từ IdP, PAM, cloud, database và ứng dụng có thể có đồng hồ sai lệch. Một bản ghi có **eventTime** nhỏ hơn bản ghi khác không nhất thiết chứng minh nó xảy ra trước.

| Trường thời gian | Ý nghĩa |
| --- | --- |
| **eventTime** | Nguồn tin cho biết hành động xảy ra lúc nào |
| **recordedAt** | Khi nguồn ghi event vào log cục bộ |
| **receivedAt** | Khi collector/queue nhận event |
| **persistedAt** | Khi kho log lâu dài xác nhận ghi |
| **reviewedAt** | Khi người độc lập xem xét |
| **activatedAt/expiresAt** | Hiệu lực của emergency grant |
| **revokedAt** | Khi hệ thống quyền ghi nhận việc thu hồi |
| **effectiveDenyVerifiedAt** | Khi kiểm tra API chứng minh quyền đã bị từ chối |

Khuyến nghị dùng **timestamp ISO 8601 có offset/UTC**, đồng thời lưu **timezone/calendar** khi có nghĩa nghiệp vụ. Collector nên đánh dấu nguồn bị lệch giờ vượt ngưỡng, và dùng **sequence/version/correlation** hỗ trợ dựng thứ tự khi timestamp không tin cậy.

**Không sửa ngược eventTime để khiến event “đúng hạn”.** Phải phân biệt giờ nguồn, giờ collector và sai lệch được quan sát. Đồng hồ có thể không đồng bộ trong outage; đó là giới hạn điều tra cần được ghi.

## 11. Log yêu cầu và căn cứ sử dụng Emergency Access

Một yêu cầu khẩn cấp nên tạo sự kiện:

~~~text
EMERGENCY_REQUESTED
    requestId
    requesterIdentityRef
    beneficiaryIdentityRef
    incidentRef
    justificationCode
    targetSystem / tenant / resourceScope
    requestedActions / requestedDuration
    requestSource
    submittedAt
~~~

**Justification** phải giúp reviewer phân biệt **phục hồi dịch vụ**, **xử lý dữ liệu sự cố**, **khôi phục identity infrastructure** hoặc lý do khác. Nếu có incidentId, phải xác minh nó thực sự tồn tại trong hệ thống sự cố có thẩm quyền khi điều kiện đó là bắt buộc.

Không ghi toàn bộ tài liệu nhạy cảm của incident vào audit event. Có thể dùng **reasonCode, incidentRef và tham chiếu bằng chứng được phân quyền**. Nếu người dùng tự nhập một dòng “critical”, nó là **claim của requester**, không phải kết quả xác minh sự cố.

## 12. Log phê duyệt, override và cơ sở thẩm quyền

Trong truy cập bình thường, role nhạy cảm có thể yêu cầu manager/resource owner/security approval. Trong emergency access, một số bước có thể dùng **policy được chấp thuận trước**, approver dự phòng hoặc break-glass theo playbook.

Các sự kiện cần cân nhắc:

- **APPROVAL_REQUIRED**: policy yêu cầu ai và vì sao.
- **APPROVAL_GRANTED/DENIED**: người duyệt, time, scope, role, duration, policy version.
- **APPROVAL_ESCALATED/DELEGATED**: người nhận quyền xử lý mới và cơ sở ủy quyền.
- **EMERGENCY_OVERRIDE_APPLIED**: nhánh nào của policy cho phép override, điều kiện nào được xác minh.
- **APPROVAL_TIMED_OUT**: ai chưa phản hồi và workflow chuyển trạng thái gì.
- **HARD_DENY_ENFORCED**: yêu cầu bị cấm dù có emergency justification.

**Approval timeout không tự bằng Permit**. **Self-approval** phải bị kiểm soát nếu không nằm trong một playbook khẩn cấp được phê duyệt rõ với kiểm soát bù trừ phù hợp.

Audit cần ghi cả **điều kiện được bỏ qua theo playbook** và **những điều kiện vẫn bắt buộc**, nhưng không phải ghi bí mật, chính sách phát hiện nội bộ chưa được phân quyền hoặc chi tiết nhạy cảm vào log phát tán rộng.

## 13. Log authentication và MFA mà không ghi bí mật

Đối với emergency session, nên biết:

| Dữ liệu | Có thể ghi | Không nên ghi |
| --- | --- | --- |
| **Authentication result** | SUCCESS/FAILURE, reason code | Mật khẩu người dùng |
| **Authenticator type** | Passkey, FIDO2/WebAuthn, certificate, hardware token | Private key, seed OTP, recovery code |
| **Assurance** | Mức bảo đảm được xác minh theo contract | Tuyên bố mơ hồ do client gửi |
| **Session** | Session reference, issuedAt/expiry và source | Session cookie hoặc bearer token thô |
| **Client device** | DeviceId/managed posture theo chính sách | Dump toàn bộ dữ liệu thiết bị |
| **Network context** | Nguồn IP đã chuẩn hóa, access path | Dữ liệu nhạy cảm không cần cho điều tra |
| **Failure** | Tài khoản không được phép, factor fail, replay suspected | Bí mật nhập sai, toàn bộ request body |

Khi **IdP/SSO không sẵn sàng**, emergency account có thể cần **đường xác thực độc lập đã được thử nghiệm**. Audit phải ghi **authentication path**, lý do fallback, người kích hoạt và control thay thế; không nên tuyên bố một phiên đã “MFA success” nếu thực tế dùng quy trình khôi phục khác.

Mức assurance phải được kiểm tra từ IdP/verifier hoặc PAM đáng tin cậy. **OIDC amr/acr/auth_time** chỉ có ý nghĩa khi issuer và ứng dụng thống nhất ngữ nghĩa, không chỉ vì claim tồn tại.

## 14. Log thời điểm cấp quyền: before/after và giới hạn grant

Trong JIT/PAM, thời điểm **activate emergency role** rất quan trọng. Audit nên lưu:

1. **Quyền hiện có trước activation**, ở dạng role/permission references.
2. **Entitlement delta** được cấp thêm, không chỉ tên role.
3. **Target và resource scope** được áp dụng.
4. **Risk tier, policy version và approval reference**.
5. **Mốc bắt đầu/kết thúc**, source clock và expiration mechanism.
6. **Kết quả từ connector**, bao gồm lỗi hoặc timeout.
7. **Readback assigned/effective permission** khi khả thi.
8. **Credential/token/session mới phát sinh** theo ID tham chiếu, không ghi giá trị bí mật.

Nếu một role **Operator** kéo theo quyền **MANAGE_ACCESS toàn tenant** vì mapping hoặc group nesting, log chỉ ghi “Operator activated” có thể che giấu quyền được mở quá rộng. Cần **role definition/version, permission expansion hoặc tham chiếu snapshot** để giải thích.

Một approval cho **READ** không được dùng để log/cấp **ADMIN** dưới cùng requestId khi role catalog đã đổi. Phải revalidate permission delta và ghi lại quyết định.

## 15. Log mọi thao tác đặc quyền hay chỉ những thao tác “quan trọng”?

Một kiến trúc thực tế phải định nghĩa **coverage theo threat model và rủi ro**, không thể hứa rằng sẽ thu thập mọi byte từ mọi thành phần. Nhưng ít nhất cần bảo đảm các hành động có nguy cơ thay đổi bảo mật và dữ liệu được quan sát.

Những nhóm thao tác cần ưu tiên:

- Tạo, xóa hoặc sửa **user, group, role, policy, trust relationship**.
- Cấp quyền cho chính mình, người khác hoặc service principal.
- Đọc, tạo, xoay hoặc xuất **secret/credential/key**; log metadata truy cập, không log giá trị bí mật.
- Thay **network rule, firewall, routing, DNS, certificate, security control**.
- Tắt/mở **audit, monitoring, EDR, SIEM forwarding hoặc backup**.
- Sửa/xóa **database, backup, snapshot, storage, IAM configuration**.
- Thay **resource owner, encryption configuration, retention hoặc policy**.
- Truy cập/EXPORT **dữ liệu nhạy cảm**, nếu loại log và nghĩa vụ cho phép.
- Chạy **command, automation, script, API call** thay đổi production.
- Tạo **long-lived token, PAT, API key** hoặc đổi session policy.

**Đọc dữ liệu nhạy cảm cũng có thể nguy hiểm như chỉnh sửa**. Một emergency admin không sửa quyền nào nhưng tải toàn bộ dữ liệu khách hàng cần để lại dấu vết phù hợp với mức độ nhạy cảm và quy định về quyền riêng tư.

## 16. Session recording: bằng chứng hữu ích nhưng không đủ một mình

Một số PAM/bastion cho phép ghi **terminal session, lệnh SSH, RDP hoặc video screen recording**. Nó giúp xác định operator đã làm gì khi sử dụng một shared admin account.

Nhưng cần biết các giới hạn:

- Video cho thấy màn hình, **không nhất thiết ghi backend action và kết quả thực tế**.
- Dữ liệu được xử lý bởi script, cron, API hoặc background job có thể không hiện trên màn hình.
- Một người có thể đi **đường truy cập không qua PAM gateway** nếu không bị chặn bằng network/control.
- Clipboard/terminal có thể hiển thị **secret** cần che trước khi lưu.
- Session bị mất kết nối có thể tạo recording thiếu đoạn, không nên đánh dấu đầy đủ.
- Việc lưu video quá mức có thể vi phạm chính sách bảo mật dữ liệu và làm tăng diện tấn công.

Nên kết hợp **session metadata + command/action logs + policy decisions + target audit**. Nếu có recording, lưu **recordingId, storageRef, start/end time, checksum/integrity metadata, người được phép xem và retention policy**. Không nhúng toàn bộ video vào một JSON event hay giả vờ rằng video thay thế audit API.

## 17. Terminal và command audit

Với SSH/terminal, có thể ghi:

| Thuộc tính | Mục tiêu |
| --- | --- |
| **SessionId và verified operator** | Quy kết trách nhiệm |
| **Target host / environment** | Xác định hệ thống bị tác động |
| **Command hoặc operation category** | Biết thao tác có ý nghĩa gì |
| **Start/end time và exit status** | Phân biệt attempt và completion |
| **Elevation method** | sudo, run-as hoặc PAM credential |
| **Parent process/job reference** | Gắn script, child process và deployment |
| **Change/ticket reference** | Giải thích lý do thao tác |
| **Output redaction status** | Không ghi secret hoặc dữ liệu nhạy cảm ngoài phạm vi |

**Chỉ ghi lịch sử shell không bảo đảm đầy đủ**: người dùng có thể chạy script tạo nhiều process, đổi môi trường, tương tác API trực tiếp hoặc disable history. Trên hệ thống phù hợp, nên dùng **OS audit, process execution telemetry, privileged command gateway và target-level state change logs**.

Không yêu cầu ghi **toàn bộ stdout/stderr chứa token, credential hoặc PII**; dữ liệu đầu ra cần phân loại và masking. Việc che lệnh hoàn toàn có thể làm mất bằng chứng; nên ghi **operation type, exit code và tham chiếu an toàn** khi cần tránh lộ tham số bí mật.

## 18. API và backend logging: chống chỉ ghi UI event

Emergency access có thể thao tác qua cloud API, internal API, CLI, automation hoặc một ứng dụng quản trị.

Ví dụ một request:

~~~http
POST /api/org-a/services/payments-prod/restart HTTP/1.1
Authorization: Bearer ACCESS_TOKEN_PLACEHOLDER
X-Correlation-Id: inc-2026-041-op-07
Content-Type: application/json

{"reasonRef":"INC-2026-041"}
~~~

API phải tự xác minh **token/actor/tenant/resource**; X-Correlation-Id và reasonRef có thể do client tự đặt nên **không phải bằng chứng quyền hoặc approval**. Backend nên gắn correlation với **trusted emergencySessionId và verified request identity**.

Một log API tốt phân biệt:

~~~text
ACTION_REQUESTED:
    actor=iam-user-482
    target=payments-prod
    action=RESTART
    session=ea-session-091-a

AUTHORIZATION_DECISION:
    policy=critical-restoration-v3
    decision=PERMIT

ACTION_RESULT:
    operationId=restart-job-908
    result=SUCCEEDED
    targetState=HEALTHY
~~~

**HTTP 202 Accepted** chỉ có thể nói job đã được tiếp nhận, chưa chứng minh service restart hoàn tất. Với thao tác bất đồng bộ, cần **operationId/job state** để liên kết kết quả cuối, đặc biệt khi tác động tới quyền hoặc dữ liệu.

## 19. Log thất bại, Deny và các đường tấn công

Không chỉ thành công mới cần ghi log. Những trường hợp cần chú ý:

- Emergency account đăng nhập thất bại nhiều lần.
- Dùng role ngoài thời hạn, sai tenant, sai resource hoặc không đúng incident.
- Attempt tự gia hạn expiry hoặc sửa approval.
- Request có scope không đủ hoặc policy trả **Deny/NotApplicable/Indeterminate**.
- Bị chặn khi tạo PAT/secret hoặc chỉnh security group.
- PEP/PDP/PIP lỗi, dẫn đến quyết định **không cấp quyền** theo policy.
- Audit service bị disable, collector timeout hoặc thiếu log trong phiên.
- Phát hiện session không còn binding với người thực.

**Không log full request body khi request bị từ chối**: request có thể chứa mật khẩu hoặc dữ liệu độc hại. Ghi **reasonCode, resource/action, actor evidence, correlation, timestamp và security classification** là hướng an toàn hơn.

Phân biệt **Denied** (đánh giá hợp lệ và từ chối) với **Indeterminate** (không thể kết luận do lỗi). Một lỗi logging hay policy không được âm thầm biến thành **Permit không kiểm toán** nếu không có đường khẩn cấp đã được phê duyệt với kiểm soát thay thế.

## 20. Dữ liệu nhạy cảm: log đủ nhưng không tiết lộ bí mật

Những dữ liệu **không nên ghi trực tiếp** vào log dùng chung:

| Dữ liệu | Lý do | Dữ liệu thay thế |
| --- | --- | --- |
| Password, recovery code, OTP seed | Có thể chiếm quyền tài khoản | Factor type, result, verifierRef |
| OAuth access/refresh token, session cookie | Có thể tái sử dụng làm bearer credential | Token fingerprint/HMAC ref hoặc tokenId nếu an toàn |
| API key, private key, cloud secret | Mở đường truy cập rộng | Secret resource ID và action READ/ROTATE |
| Nội dung DB/query chứa PII | Tạo bản sao dữ liệu nhạy cảm | Query category, table/resource ID, row count nếu thích hợp |
| Toàn bộ HTTP body/header | Có thể chứa dữ liệu nghiệp vụ và credential | Endpoint/action, field allowlist, redacted metadata |
| Clipboard/video chưa lọc | Có thể quay lộ credential | Recording được kiểm soát, masking và hạn chế viewer |
| Hồ sơ HR đầy đủ | Vượt mục đích kiểm toán | employmentRelationId, status category, sourceVersion |

Ngay cả **hash trơn của một token có entropy thấp** cũng có thể tạo rủi ro; cân nhắc sử dụng **định danh do issuer cấp hoặc HMAC/fingerprint có kiểm soát**, tránh lưu bí mật hoặc thông tin có thể khôi phục. Không tuyên bố “hash là vô hại” mà chưa phân tích threat model.

Log phải áp dụng **data minimization, phân quyền đọc, retention theo chính sách, encryption phù hợp và kiểm soát xuất dữ liệu**. Người có quyền xem audit không mặc nhiên được xem toàn bộ dữ liệu cá nhân hoặc session recording.

## 21. Integrity: làm sao biết log không bị sửa hoặc xóa?

Các biện pháp phổ biến:

1. **Chuyển log ra hệ thống độc lập** càng sớm càng phù hợp.
2. **Append-only hoặc retention lock/WORM** nếu hệ thống và chính sách hỗ trợ.
3. **Immutable audit trail/retention control** với người quản trị log độc lập.
4. **Digital signature hoặc hash chaining** để phát hiện sửa đổi trong một chuỗi sự kiện.
5. **Sequence number/event gap detection** để nhận biết nguồn bỏ mất log.
6. **Clock synchronization và source identity** để tránh giả mạo thời điểm.
7. **Backup, replication và restore tests** cho bằng chứng.
8. **Access review định kỳ** đối với người có quyền xem/xóa/chỉnh retention.

### Hash chain minh họa

~~~text
entry[0].hash = HASH(canonical(entry[0].payload) + anchor)
entry[1].hash = HASH(canonical(entry[1].payload) + entry[0].hash)
entry[2].hash = HASH(canonical(entry[2].payload) + entry[1].hash)

verify:
    recompute hashes in a trusted environment
    compare with retained external anchor / signed checkpoint
~~~

**Hash chain không tự ngăn xóa cả chuỗi rồi tính lại hash**. Cần một **anchor/checkpoint được bảo vệ độc lập**, giới hạn quyền, lưu trữ chống sửa và đối soát lượng log. Chữ ký cũng không chứng minh dữ liệu đầu vào luôn đúng: nếu agent bị chiếm quyền rồi ký sự kiện giả, chữ ký chỉ chứng minh nguồn đã ký.

Một claim “log immutable” phải được kiểm chứng qua **cấu hình quyền, retention, deletion protection và thử nghiệm khôi phục**, không chỉ dựa tên sản phẩm.

## 22. Separation of Duties cho log: emergency admin không được tự xóa dấu vết

Trong thiết kế IAM, có thể cần phân tách:

| Chức năng | Chủ thể có thể đảm nhiệm | Hạn chế |
| --- | --- | --- |
| **Emergency operator** | Đội ứng cứu, platform on-call | Không được xóa audit độc lập về phiên mình |
| **PAM administrator** | Nhóm IAM/PAM quản trị thiết lập phiên | Không tự duyệt/che giấu mọi phiên của mình |
| **Log pipeline operator** | Logging/SRE theo phạm vi | Không được sửa evidence lịch sử tùy ý |
| **Security/SOC reviewer** | Người giám sát độc lập | Quyền đọc và phân tích, hạn chế sửa log gốc |
| **Retention policy owner** | Governance/security có thẩm quyền | Thay retention có approval và audit riêng |
| **Compliance/auditor** | Bộ phận kiểm tra | Chỉ đọc theo phân quyền; không nhất thiết có quyền cấp access |

**Một account emergency admin có thể cần khôi phục chính hệ thống logging**, nên một số quyền đặc biệt có thể khó tách hoàn toàn. Khi đó cần thiết kế **đường ghi log độc lập/out-of-band, evidence đã chuyển ra vùng khác, phê duyệt thay đổi và kiểm tra hậu sự kiện**.

Nếu một người vừa có **ModifyIAMPolicy** vừa có **DeleteAuditLogs**, đó là **SoD conflict** cần phân tích, không được bỏ qua chỉ vì role mang nhãn emergency. Ngoại lệ SoD (nếu được cho phép) phải có scope, risk owner, bù trừ và thời hạn.

## 23. Khi hệ thống log không sẵn sàng: không fail-open mù quáng

Thách thức của emergency access là **tình huống thật sự khẩn cấp có thể xảy ra đúng khi IdP, network, logging hoặc PAM bị sự cố**.

| Tình huống | Lựa chọn thiết kế | Điều cần chứng minh |
| --- | --- | --- |
| Collector tạm timeout, agent local còn hoạt động | Buffer có bảo vệ, retry và cảnh báo | Không mất event quá mức; đo backlog/gap |
| SIEM ngừng nhận event, kho local vẫn ghi | Có thể tiếp tục theo policy rủi ro | Log được forward và reconcile sau khi hồi phục |
| Audit trên target bị disable hoặc bị sửa | Chặn hành động nhạy cảm hoặc kích hoạt đường khẩn cấp dự phòng | Ai cho phép fallback, bằng chứng thay thế |
| Cả PAM và IdP đều lỗi | Dùng break-glass path độc lập đã kiểm thử | Identity, incident binding, local/out-of-band evidence |
| Không có khả năng ghi log ở bất kỳ tầng nào | Đánh giá cực kỳ thận trọng theo playbook | Không tuyên bố “đầy đủ”; ghi nhận gap và hậu kiểm |

**Fail-closed** thường là mặc định thích hợp với hành động đặc quyền: nếu không thể bảo đảm điều kiện kiểm toán bắt buộc, không cho thực hiện. Nhưng trong một số tình huống phục hồi an toàn, một **đường emergency continuity được phê duyệt trước** có thể sử dụng **offline signed evidence, dual control, bastion phụ, local protected journal hoặc giám sát trực tiếp độc lập**.

Không tự viết logic **logging failed → ALLOW_ALL**. Việc có cho tiếp tục khi giảm khả năng logging phải do **risk policy và playbook** quy định, giới hạn hành động, thời gian, owner và hoạt động hậu kiểm.

## 24. Buffer và retry log: không được mất thứ tự/ghi trùng một cách vô hình

Trong hệ thống phân tán, event có thể bị gửi lặp hoặc tới sai thứ tự do mạng và retry. Log pipeline cần phân biệt:

- **eventId:** một sự kiện logic duy nhất.
- **sourceSequence:** thứ tự do nguồn đáng tin cung cấp nếu có.
- **attemptId:** lần gửi lại cụ thể.
- **receivedAt:** thời điểm collector nhận.
- **ingestionStatus:** ACCEPTED, DUPLICATE, REJECTED, QUARANTINED.
- **schemaValidationStatus:** có thể đọc/đánh giá dữ liệu hay không.
- **gap/lag metrics:** sự kiện vắng mặt hay bị trễ.

Nếu nguồn dùng at-least-once delivery, có thể có duplicate; **deduplication phải không xóa nhầm các hành động lặp thực sự**. Ví dụ hai lần **DELETE_ATTEMPTED** với operationId khác nhau phải còn là hai event, không gộp chỉ vì cùng actor và action.

**Một sequence counter không bảo đảm log không bị bỏ sót** nếu chính nguồn có thể ngừng tạo event. Cần đối chiếu với target state change, operation counters, PAM session timeline và incident record.

## 25. Correlation qua request, session, token và resource

Ví dụ một incident có ba operator và năm session. **incidentId** giúp gom toàn bộ sự kiện, nhưng không thể thay **emergencySessionId**:

~~~text
INC-2026-041
  EA-2026-091 (request)
    ea-session-091-a (operator iam-482)
      op-001: restart service
      op-002: adjust timeout
    ea-session-091-b (operator iam-483)
      op-003: examine logs
  EA-2026-092 (different request)
    ea-session-092-a (workload svc-recovery)
      op-004: restore backup
~~~

Hệ thống cần gắn **verified actor/session** với cả các lệnh diễn ra ở target. Nếu một service chạy tác vụ bất đồng bộ, hãy giữ **actorInitiator, servicePrincipal và operationId**, tránh ghi tất cả thao tác chỉ do **system**.

Khi propagate trace/correlation qua API, không coi header do client gửi là nguồn đáng tin cho quyền. Gateway/service có thể tạo ID chuẩn và lưu liên kết với client-provided reference một cách an toàn.

## 26. Audit khi có nhiều tenant, organization và employment

Một người có thể có nhiều hợp đồng hoặc quyền tại các organization khác nhau. Một record emergency access phải gắn:

- **identityId/personId** đã xác minh;
- **employmentRelationId/sponsor** làm căn cứ;
- **tenantId/organizationId** được áp quyền;
- **resourceScope** thực tế;
- **approvedRole/permission delta**;
- **policy version** của tổ chức liên quan.

Ví dụ Lan còn quan hệ hợp lệ ở **org-b** nhưng đã Leaver **org-a**. Một phiên emergency để phục hồi dịch vụ của org-b có thể hợp lệ theo policy riêng; nó **không cho phép thao tác lên org-a** nếu không có căn cứ độc lập. Audit phải giúp phát hiện cross-tenant operation.

Tránh trộn log của nhiều tenant trong một dashboard mà người xem có thể nhìn thấy dữ liệu của tenant khác. **Phân quyền xem audit** cũng là authorization trên dữ liệu nhạy cảm.

## 27. Token, OAuth/OIDC và session: cần ghi gì để tìm quyền tồn dư?

Với OAuth 2.0/OIDC hoặc session của ứng dụng, nên lưu metadata:

| Loại | Metadata có ích | Không được suy diễn |
| --- | --- | --- |
| **OIDC sign-in** | issuer, sub reference, amr/acr khi có hợp đồng, auth_time | ID token không phải quyền trên API |
| **OAuth access token** | tokenId hoặc opaque ref, issuer, audience, scope, issuedAt, expiresAt | Scope không tự cho toàn bộ resource |
| **Refresh grant** | grantId, clientId, revocation status, event time | Revoke refresh không tự chặn access token JWT đã cấp |
| **PAM session** | sessionId, targetAccountRef, start/end, assurance | End session không chắc đã xóa local PAT |
| **Target local session** | appSessionRef, login/logout/revocation | Logout IdP không tự logout mọi SaaS |
| **Service credential** | credentialRef, owner, rotation/revoke event | Xóa key ở một nơi không chắc mọi bản sao đã mất |

**Không ghi bearer token thô**. Các trường như **jti** chỉ có nếu token/issuer cung cấp và đã được xác minh; không giả định mọi JWT có jti. Một **access token JWT được resource server xác thực offline** có thể còn được chấp nhận đến expiry nếu không có cơ chế chặn, do đó cần log **revoke requested vs effective deny verified**.

Với hành động đặc biệt nhạy cảm, resource server có thể thực hiện **policy recheck, token introspection hoặc security epoch check** theo kiến trúc. Audit cần phân biệt quyết định theo token cũ với trạng thái quyền hiện hành.

## 28. Log quản trị RBAC/ABAC/PBAC và dữ liệu quyết định

Emergency access thường thay đổi role/policy. Cần audit cả **quyền được cấp** và **quyết định thực thi**.

| Thành phần | Log nên có |
| --- | --- |
| **PAP** — Policy Administration Point | Ai tạo/sửa/duyệt/publish policy, version, diff summary |
| **PIP** — Policy Information Point | Thuộc tính và snapshot version dùng để đánh giá, freshness/error |
| **PDP** — Policy Decision Point | Decision Permit/Deny/NotApplicable/Indeterminate, policy ID/version, reasonCode |
| **PEP** — Policy Enforcement Point | Request action/resource và kết quả thực sự Blocked/Allowed |
| **RBAC mapping** | Role, hierarchy/group mapping và entitlement delta |
| **ABAC attributes** | employment/project/resource context từ nguồn có thẩm quyền, không dump toàn bộ HR |

**PDP Permit không chứng minh PEP đã thực thi**, và **PEP Allowed** không chứng minh một thao tác bất đồng bộ đã hoàn thành. Cần liên kết **decisionId, enforcementId và operationId**.

Policy mới được publish trong emergency có thể lan truyền không đồng thời giữa các node. Audit nên lưu **policy version adopted trên từng PDP/PEP** để điều tra tại sao hai request giống nhau có kết quả khác.

## 29. Log JML: Joiner, Mover, Leaver và nguy cơ emergency privilege tồn dư

### Joiner

Khi nhân viên mới bắt đầu, **không nên được cấp quyền emergency administrator theo birthright**. Nếu họ tham gia đội ứng cứu, cần onboarding riêng, xác minh training, sponsor, PAM enrollment và cấp **eligibility** phù hợp; mỗi lần activation vẫn có policy và audit.

Log cần liên kết **employment start, role eligibility, credential enrollment và assigned emergency access scope**. Không ghi mật khẩu/khóa dự phòng vào log onboarding.

### Mover

Khi operator chuyển khỏi đội on-call, cần kiểm tra các role emergency đang giữ, membership, backup admin account, PAT hoặc entitlement trực tiếp. Audit nên có **eligibility changed → revoke requested → target readback → effective deny**.

Không coi một lần **group removed** là bằng chứng tất cả đường truy cập đã đóng. Tài khoản cục bộ hoặc token cũ có thể vẫn hoạt động.

### Leaver

Khi HRIS/sponsor xác nhận kết thúc quan hệ, cần thu hồi access theo SLA, chặn pending emergency request và ngăn job cũ cấp lại quyền. Log phải liên kết cả **token/session/account/role revocation** và **negative effective-access tests**.

Một người có employment hợp lệ khác không tự mất mọi quyền nếu policy cho phép giữ tại tenant khác. Đánh giá theo **đúng employmentRelation, owner và scope**.

## 30. Emergency access của service account và workload

Một **workload** có thể tự thực hiện hành động khôi phục, ví dụ restore backup hoặc restart một cluster. Điều đó không có nghĩa không cần audit vì “không có con người đăng nhập”.

Các trường đáng có:

| Trường | Ví dụ | Mục tiêu |
| --- | --- | --- |
| **workloadId/serviceId** | svc-recovery-operator | Phân biệt máy thực hiện |
| **issuer/credentialRef** | workload-issuer-prod | Nguồn xác minh danh tính máy |
| **ownerTeam** | production-reliability | Ai chịu trách nhiệm |
| **job/pipeline/commitRef** | recovery-run-908 | Phiên bản logic được chạy |
| **trigger/incidentId** | INC-2026-041 | Lý do activation |
| **environment/tenant** | prod/org-a | Ngăn dùng nhầm môi trường |
| **resource/action** | RESTORE on backup-set-42 | Phạm vi quyền |
| **approval/policyVersion** | recovery-policy-v5 | Căn cứ tự động hóa |
| **temporaryCredential/sessionRef** | issued-token-ref-92 | Theo dõi quyền vòng đời |
| **result and rollbackRef** | RESTORE_COMPLETED | Kết quả và đường khôi phục |

Nếu cùng một người sửa pipeline và có quyền phê duyệt execution của chính pipeline, đó có thể là **SoD conflict**. Kiểm tra **code review, deployment approval, secret access và policy của workload**, không chỉ nhìn tên service principal.

**Owner Leaver không đồng nghĩa workload production phải xóa ngay** nếu nó còn nhiệm vụ hợp lệ; cần chuyển owner, rà soát secret họ biết và xóa các credential cá nhân còn đường truy cập.

## 31. SIEM/SOC: phát hiện sự kiện đáng quan tâm gần thời gian thực

Log có giá trị khi có **quy tắc phát hiện, người nhận cảnh báo, quy trình xử lý và kết quả kiểm chứng**.

| Tín hiệu phát hiện | Lý do cảnh báo | Hành động kiểm tra |
| --- | --- | --- |
| Emergency access ngoài lịch trực/chính sách | Có thể sử dụng sai hoàn cảnh | Xác minh incident và actor |
| Activation không có incidentRef hợp lệ | Thiếu căn cứ | Kiểm tra playbook và nguồn incident |
| Role ngoài approved scope/tenant | Có thể vượt tổ chức | Kiểm tra entitlement delta và PEP |
| Nhiều lần authentication failure rồi success | Có thể credential attack | Điều tra source và session |
| Session vượt maxDuration | Quyền dùng lâu hơn dự kiến | Revoke và kiểm tra token/session |
| Tạo PAT/secret lâu hạn trong emergency | Tạo đường truy cập tồn dư | Rà soát credential mới |
| Sửa audit/retention/forwarding | Có thể che dấu vết | Kích hoạt giám sát độc lập |
| EXPORT dữ liệu nhạy cảm bất thường | Nguy cơ lộ dữ liệu | Xác minh resource owner, mục đích và volume |
| PEP Allowed sau emergency expiry | Revocation thất bại | Chặn và đối soát |
| Log gap hoặc collector ngừng nhận | Thiếu bằng chứng | Triage pipeline/target, không mặc định an toàn |
| Reviewer không hoàn thành hậu kiểm | Rủi ro không được đánh giá | Escalation và owner |

Không phải cảnh báo nào cũng là sự cố bảo mật. Hệ thống cần phân biệt **false positive, hành động hợp lệ trong incident, lỗi giám sát và lạm dụng có căn cứ**. Cảnh báo phải có correlation để SOC có thể xem **chuỗi sự kiện**, không chỉ một dòng log rời rạc.

## 32. Phản ứng với hành động ngoài phạm vi emergency

Khi phát hiện operator dùng emergency role để thực hiện hành động ngoài scope:

1. Xác minh log có **actor và target đúng** hay không.
2. Kiểm tra **request/approval/policy/incident** tương ứng.
3. Phân biệt **action attempted, PDP Permit/Deny, PEP Allowed/Blocked và action completed**.
4. Xác định có **data access/export, credential creation, policy change** hay không.
5. Thực hiện biện pháp chặn/thay đổi quyền theo **incident playbook** và thẩm quyền được duyệt.
6. Bảo toàn bản ghi gốc và evidence liên quan trước khi hệ thống xoay log.
7. Rà soát quyền mới phát sinh và các target ngoài scope.
8. Giao người độc lập thực hiện hậu kiểm, kết luận căn cứ và giới hạn quan sát.

Một event **Deny** không nhất thiết đã ngăn mọi đường truy cập nếu API khác hoặc local account vẫn có Permit. Cần kiểm tra các đường có thể bị bypass trước khi kết luận không có tác động.

## 33. Post-incident review: ai xem lại và xem những gì?

**Hậu kiểm độc lập** nên diễn ra sau khi phiên emergency kết thúc hoặc theo mốc policy. Reviewer cần có năng lực và thẩm quyền, không tự bấm **“Reviewed”** đối với chính phiên mình thực hiện khi SoD yêu cầu tách người.

### Trình tự đề xuất

1. Liệt kê tất cả **emergency sessions/activations** liên quan incident.
2. Xác nhận **incident thực và điều kiện kích hoạt**.
3. Kiểm tra **identity, authentication path và approval/policy**.
4. Dựng **timeline có time source/clock skew** từ nhiều log.
5. So request scope với **effective role/action/resource**.
6. Rà soát **lệnh, API, data access, policy change và credential creation**.
7. Kiểm tra **recording/log gap**, cả lúc SIEM hoặc IdP outage.
8. Xem bất thường **SoD, self-approval, cross-tenant, extended session**.
9. Đối chiếu **end/revoke events với actual target Deny**.
10. Ghi **findings, owner, corrective actions, deadlines và review decision**.

**Không xem lại log rồi chỉ ký một dấu xác nhận chung**. Một review hiệu quả phải phân loại từng chênh lệch, nêu bằng chứng và lưu kết quả các hành động khắc phục.

## 34. Khả năng bảo toàn chứng cứ và chain of custody

Khi một phiên trở thành đối tượng điều tra, cần quản lý evidence theo chính sách tổ chức. Những yếu tố có thể cần:

- **Nguồn gốc:** log/recording lấy từ target, collector và thời điểm nào.
- **Dữ liệu gốc:** bảo toàn file/stream gốc trong khu vực truy cập có kiểm soát.
- **Hash/checksum** để so sánh sau khi sao chép; nguồn đáng tin cho checksum.
- **Access log của chính evidence store**: ai đã xem/tải/xuất/chuyển bằng chứng.
- **Cơ chế duy trì tính toàn vẹn**: retention lock, signature, read-only snapshot khi hỗ trợ.
- **Tham chiếu sự kiện liên quan**: incidentId, sessionId, operationId, target.
- **Quy trình chuyển giao**: người nhận, mục đích và thời điểm.
- **Quy tắc riêng tư/pháp lý**: hạn chế nội dung/retention theo nghĩa vụ áp dụng.

**Chain of custody không chỉ là một mã hash**. Nó bao gồm việc chứng minh ai đã kiểm soát bản ghi trong từng bước và liệu evidence đã bị thay đổi hay chưa. Không khẳng định log có giá trị pháp lý cụ thể nếu chưa đối chiếu quy định và quy trình của tổ chức.

## 35. Retention: giữ bao lâu và ai được xem?

Không tồn tại một thời hạn lưu log phù hợp cho mọi quốc gia, ngành hoặc ứng dụng. Cần căn cứ **quy định áp dụng, mục đích kiểm toán, mức nhạy cảm và chính sách nội bộ**.

| Loại evidence | Yêu cầu cần thiết kế |
| --- | --- |
| **AuthN/access log** | Hạn lưu, truy xuất khi điều tra, giới hạn PII |
| **Approval/activation audit** | Duy trì căn cứ và policy/version đủ cho hậu kiểm |
| **PAM session recording** | Có thể chứa bí mật và thông tin cá nhân; hạn chế người xem |
| **Target action logs** | Bảo toàn những thay đổi có ảnh hưởng tới dữ liệu/sự cố |
| **Log integrity checkpoints** | Hỗ trợ xác minh bản ghi trong khoảng retention |
| **Incident evidence** | Có thể có legal hold nếu hợp lệ theo quy trình |
| **SIEM alerts/cases** | Giữ quan hệ với quyết định và remediation |

**Legal hold** hoặc nghĩa vụ bảo toàn chứng cứ có thể thay đổi lịch xóa thông thường, nhưng phải do người có thẩm quyền quyết định và lưu lý do. Mỗi đường truy cập log nhạy cảm nên có **RBAC/ABAC** và audit riêng.

Không đặt retention “vĩnh viễn” chỉ để tránh thiết kế chính sách. Lưu quá nhiều dữ liệu nhạy cảm làm tăng bề mặt rủi ro.

## 36. Reconciliation: log phải chứng minh emergency grant đã thực sự thu hồi

Hậu kiểm chưa hoàn tất nếu chỉ thấy:

~~~text
PAM Session Ended = SUCCESS
SCIM Group Removed = SUCCESS
IGA Ticket Status = CLOSED
~~~

Vẫn có thể tồn tại **local account, direct ACL, PAT, long-lived API key, active OAuth access token hoặc cached authorization decision**.

Một quy trình cần đối chiếu:

| Lớp | Mong muốn sau kết thúc | Bằng chứng |
| --- | --- | --- |
| **Emergency broker/PAM** | Session/lease đã đóng | Session end event và state readback |
| **IAM/IGA** | Không còn emergency entitlement đang hiệu lực | Expected rights và request/approval lifecycle |
| **IdP** | Không còn nhóm/quyền kích hoạt khẩn không hợp lệ | Group/account state và token-related events |
| **SCIM/SaaS** | Target role/ACL đúng trạng thái | User/Group/role readback |
| **OAuth/token** | Credential/grant liên quan đã thu hồi hoặc giới hạn đúng | Revocation/introspection/expiry metadata khi hỗ trợ |
| **PDP/PEP** | Request ngoài policy phải DENY | Authorization decision và enforcement audit |
| **Resource server** | Action nhạy cảm không còn ALLOW | Negative access test trên tài nguyên kiểm thử |
| **Workload** | Job/credential tạm thời không còn đường đặc quyền | Owner/credential lifecycle và action logs |

**Deny được kiểm chứng ở một endpoint không tự chứng minh mọi đường quyền đã bị đóng**. Cần nêu phạm vi các target/route đã kiểm tra, những đường chưa có khả năng quan sát và kết quả follow-up.

## 37. Mã giả: ghi audit độc lập trước, trong và sau phiên

Mã giả dưới đây mô tả hướng xử lý, **không phải SDK chạy trực tiếp** của IAM/PAM/SIEM:

~~~text
startEmergencySession(request, verifiedActor, now):
    requireTrustedActor(verifiedActor)
    requireValidCurrentEmergencyPolicy(request, now)
    requireVerifiedIncidentOrApprovedFallback(request.incidentRef)
    requireEligibleCurrentEmploymentOrWorkload(request.subject)
    requireNoHardDenyAndValidScope(request)

    activation = buildScopedTimeBoundGrant(request, now)
    auditIntent = buildMandatoryAuditEvent(
        type="EMERGENCY_ACTIVATION_REQUESTED",
        actorRef=verifiedActor.id,
        requestId=request.id,
        target=request.target,
        incidentRef=request.incidentRef,
        policyVersion=activation.policyVersion
    )

    if not durableAuditOrApprovedFallbackAvailable(auditIntent):
        return BLOCKED_AUDIT_UNAVAILABLE

    result = activateThroughTrustedBroker(activation)
    auditResultWithoutSecrets(result, activation)

    if result.isUnknown:
        return ACTIVATION_UNVERIFIED_RECONCILE

    return result.sessionReference

recordPrivilegedOperation(session, action, resource):
    verifyActiveSessionAndScope(session, action, resource)
    decision = authorizeAtResourceServer(session, action, resource)
    recordDecisionAndEnforcement(decision)
    if decision != PERMIT:
        return NO_ACCESS

    result = executeOperationWithAuditCorrelation(action, resource)
    recordSanitizedOutcomeAndTargetVersion(result)
    return result

closeEmergencySession(session, reason):
    closeLeaseAndScheduleTokenCredentialReview(session)
    recordRevocationIntentAndResults(session)
    verifyTargetEffectiveAccessAndAuditEvidence(session)
    assignIndependentPostIncidentReview(session)
~~~

Điểm cốt lõi: **không đánh đồng audit event đã tạo với audit đã được lưu bền vững**. Nếu hệ thống có **transactional outbox, local protected journal hoặc queue đáng tin**, cần kiểm tra khả năng ghi trước khi cho phép hành động thuộc lớp yêu cầu audit bắt buộc, theo threat model.

Việc ghi audit và thực hiện hành động ở **hai hệ thống độc lập** không tự động tạo atomic transaction. Cần xử lý trạng thái **INDETERMINATE, reconcile, retry idempotent và evidence gap**, không tuyên bố “exactly once” mà không có cơ chế thực tế.

## 38. Java minh họa: tách audit metadata khỏi dữ liệu bí mật

Một backend Java có thể dùng record dữ liệu bất biến để tạo event chuẩn hóa:

~~~java
import java.time.Instant;
import java.util.UUID;

public record EmergencyAuditEvent(
        UUID eventId,
        String eventType,
        Instant occurredAt,
        String actorIdentityId,
        String emergencySessionId,
        String incidentReference,
        String tenantId,
        String resourceId,
        String action,
        String decision,
        String result,
        String correlationId
) {}

public final class EmergencyAuditFactory {
    public static EmergencyAuditEvent actionResult(
            String actorId,
            String sessionId,
            String incidentRef,
            String tenantId,
            String resourceId,
            String action,
            String decision,
            String result,
            String correlationId) {
        return new EmergencyAuditEvent(
                UUID.randomUUID(),
                "EMERGENCY_ACTION_RESULT",
                Instant.now(),
                actorId,
                sessionId,
                incidentRef,
                tenantId,
                resourceId,
                action,
                decision,
                result,
                correlationId
        );
    }
}
~~~

Đây là ví dụ dữ liệu, **không phải hệ thống audit hoàn chỉnh**. Trong production cần thêm **schema validation, source authentication, transaction/outbox, durable delivery, redaction, retry, monitoring và authorization của audit reader**. Không đưa đối tượng chứa HTTP headers, OAuth token hoặc password vào hàm logger để serialize tự động.

Thời gian **Instant.now()** là timestamp của service ghi event, không nhất thiết là thời gian thực thi ở resource server. Nếu hành động được thực hiện từ xa hoặc theo job bất đồng bộ, lưu **eventTime tại nguồn** và **recordedAt tại backend** riêng khi cần.

## 39. Threat model của hệ thống audit Emergency Access

| Mối đe dọa | Ví dụ | Kiểm soát |
| --- | --- | --- |
| **Disable logging** | Emergency admin tắt audit agent | Đường log độc lập, alert khi mất heartbeat |
| **Delete/alter evidence** | Sửa retention hoặc xóa log | Append-only/retention lock, SoD, checkpoint |
| **Spoof actor** | Header gửi actorId giả | Verified identity từ PAM/IdP/token, không tin client |
| **Shared account ambiguity** | Mọi action đều hiện root | PAM session binding với human identity |
| **Log injection** | Chèn ký tự xuống dòng/giả JSON qua input | Structured logging, encoding và field validation |
| **Secret leakage** | Ghi token trong HTTP request log | Redaction allowlist, kiểm thử và secret scanning |
| **Cross-tenant disclosure** | Auditor tenant A thấy log tenant B | RBAC/ABAC và resource-level audit access |
| **Event replay** | Gửi lại event activation cũ | eventId/version/idempotency và current-state checks |
| **Silent log gap** | Collector mất mạng và không báo | Heartbeat/sequence/gap detection, buffered delivery |
| **Backdated event** | Client tự khai occurredAt trước approval | Trusted timestamps, receivedAt, version và provenance |
| **PDP/PEP bypass** | API phụ không gọi policy engine | Integration tests và target action logs |
| **Expired emergency grant reused** | Token/ACL còn hiệu lực | Revoke, token/credential lifecycle, negative tests |
| **Compromised log viewer** | Sao chép dữ liệu nhạy cảm trong recording | Least privilege, viewer audit, masking và retention |

**Bảo toàn log cần nhìn cả đường sinh và đường đọc log**. Một SIEM đã được bảo vệ tốt nhưng agent đầu nguồn có thể bị vô hiệu hóa vẫn tạo khoảng trống. Một agent hoạt động ổn nhưng kho log để operator xóa vô thời hạn vẫn không đủ tin cậy.

## 40. Bộ kiểm thử mức độ đầy đủ và an toàn của log

| Test | Tình huống | Kết quả mong đợi |
| --- | --- | --- |
| T01 | Emergency request hợp lệ | Có event request, actor, incident, scope và timestamp |
| T02 | Approval bằng chính sách khẩn cấp | Có policy/condition version, không ghi giả human approver |
| T03 | Login success qua IdP | Có verified identity/session metadata, không ghi password/token |
| T04 | Login fail với recovery credential | Ghi reason code phù hợp, không lưu bí mật |
| T05 | Activate role có hạn | Có permission delta, roleVersion, expiresAt và readback |
| T06 | Operator restart service | Có attempt, authz decision và kết quả cuối |
| T07 | Operation bị PEP Deny | Ghi decision/enforcement mà không trả dữ liệu |
| T08 | Operator dùng admin API ngoài PAM | Target audit vẫn có actor/đường truy cập, hoặc đường bypass bị chặn |
| T09 | Gọi lệnh async nhận HTTP 202 | Có operationId và completion event sau đó |
| T10 | Collector timeout ngắn | Buffer/retry, đo lag/gap và cảnh báo theo policy |
| T11 | SIEM outage | Có protected evidence/approved fallback theo thiết kế |
| T12 | Emergency admin sửa/xóa log | Bị chặn hoặc phát hiện theo threat model |
| T13 | Video PAM chứa credential | Masking/quyền xem hạn chế, không phát tán raw |
| T14 | Token JWT còn ALLOW sau session end | Không đánh dấu VERIFIED_CLOSED; xử lý residual |
| T15 | HRIS xác nhận operator Leaver | Chặn quyền/phiên và audit revocation |
| T16 | Operator Mover khỏi đội on-call | Eligibility và emergency grants được rà soát |
| T17 | Workload khôi phục production | Log serviceId, owner, job/incident và result |
| T18 | Callback/approval cũ tới sau revoke | Không re-activate quyền; log stale event |
| T19 | Nhiều tenant có cùng username | Audit không gộp identity sai |
| T20 | Event gửi trùng do retry | Deduplicate đúng eventId, không xóa action khác |
| T21 | Đồng hồ target lệch | Lưu source/received timestamp và flag skew |
| T22 | Người review là chính operator | SoD guard và reviewer độc lập nếu bắt buộc |
| T23 | Access log thiếu API export | Coverage test phát hiện và đánh dấu gap |
| T24 | Emergency role cho phép sửa IAM policy | Audit cả role/permission diff và target version |
| T25 | Thu hồi role ở IdP nhưng PAT còn active | Không tuyên bố revocation hoàn tất |
| T26 | Lệnh log shipper bị vô hiệu, session tiếp tục | Kích hoạt alert và đường response theo playbook |
| T27 | Khôi phục evidence từ backup | Integrity/retention và khả năng truy xuất được kiểm chứng |
| T28 | Access reviewer mở session recording | Viewer access được kiểm soát và audit |

Chạy kiểm thử với **tài khoản/tài nguyên kiểm thử được ủy quyền**, không làm gián đoạn dịch vụ sản xuất ngoài kế hoạch. Nên có **chaos/DR drill** có kiểm soát cho đường logging độc lập, nhưng không tắt logging production chỉ để thử một cách thiếu phê duyệt.

## 41. Tình huống thực hành: khôi phục dịch vụ thanh toán khi IdP gặp sự cố

**Bối cảnh:** Lúc 09:10, dịch vụ thanh toán production của **org-a** ngừng xử lý giao dịch, đồng thời **IdP chính không cho đăng nhập**. Đội SRE có một **break-glass path độc lập đã kiểm thử** để vào platform qua tài khoản dự phòng, lấy credential từ kho được kiểm soát và thực hiện thao tác hạn chế.

### 41.1. Trước activation

Incident commander mở **INC-2026-041**. Operator Minh được xác minh theo **quy trình khẩn cấp độc lập** đã phê duyệt, chứ không ghi giả rằng IdP chính đã xác thực thành công.

Audit ghi:

~~~text
09:11  EMERGENCY_REQUESTED
       actor=iam-minh, incident=INC-2026-041
       target=payments-prod, action=RESTART, scope=org-a

09:12  FALLBACK_AUTHENTICATION_SUCCEEDED
       path=approved-emergency-verifier
       assurance=evidence-ref-001

09:13  EMERGENCY_POLICY_TRIGGERED
       policy=restoration-v3, decision=ACTIVATION_ALLOWED

09:14  EMERGENCY_ACCESS_ACTIVATED
       role=scoped-emergency-operator, expiresAt=10:14
~~~

Điểm quan trọng: **evidence-ref-001** tham chiếu tới bằng chứng xác minh đã được phân quyền; không ghi trực tiếp thông tin dùng để mở credential hoặc recovery code.

### 41.2. Trong phiên

Minh restart service rồi thay timeout cấu hình thuộc phạm vi được duyệt. Resource server ghi **operationId, before/after config ref, decision và result**, trong khi PAM ghi session reference.

~~~text
09:16  ACTION_ATTEMPTED
       action=RESTART, resource=payments-prod, op=restart-908

09:16  AUTHORIZATION_PERMITTED
       policy=restoration-v3, session=ea-session-091-a

09:17  ACTION_COMPLETED
       op=restart-908, result=SUCCESS

09:19  CONFIG_CHANGE_COMPLETED
       change=payments-timeout, result=SUCCESS

09:22  ACTION_DENIED
       action=CREATE_ADMIN_USER, policy=emergency-scope-limit
~~~

Một event **CREATE_ADMIN_USER bị Deny** có thể là lỗi thao tác hoặc ý định vượt scope; reviewer cần xem ngữ cảnh, không tự kết luận gian lận chỉ từ một dòng log.

### 41.3. Log collector mất kết nối

Lúc 09:20, đường về SIEM lỗi trong ba phút. Agent cục bộ vẫn ghi vào **protected buffer** theo policy đã phê duyệt và phát cảnh báo local/out-of-band. Khi kết nối hồi phục, collector nhận lại event với **eventTime và receivedAt khác nhau**, đánh dấu ingestion lag.

Nếu protected buffer cũng không còn khả dụng, không được âm thầm tiếp tục mọi thao tác nhạy cảm. Phải đi theo **emergency continuity playbook**, giới hạn hành động, người chứng kiến và evidence thay thế nếu tổ chức đã cho phép.

### 41.4. Thu hồi và hậu kiểm

Lúc 09:33, dịch vụ ổn định, Minh kết thúc phiên. IAM/PAM đóng lease, xử lý credential liên quan và kiểm tra quyền tại target:

| Bằng chứng | Kết quả |
| --- | --- |
| Session ended | PASS |
| Emergency role removed | PASS |
| New long-lived PAT created | Không thấy trong nguồn đã kiểm chứng; ghi rõ coverage |
| API RESTART với emergency account sau revoke | DENY |
| API CREATE_ADMIN_USER | DENY trong cả phiên |
| Log gap reconciliation | Event tồn đọng đã nhận, sequence kiểm tra |
| Independent review | Được giao reviewer không phải Minh |

Đến khi có **readback và negative access tests** đạt, ticket mới được ghi nhận **verified revocation** trong phạm vi đã kiểm chứng. Nếu còn session/token không kiểm tra được, giữ **UNVERIFIED** với owner và deadline.

### 41.5. Bài học rút ra

Sự kiện trên có thể phục hồi dịch vụ ngay cả khi IdP chính lỗi **nếu** đường dự phòng được chuẩn bị kỹ. Nhưng ghi log phải bảo đảm **source, actor, scope, result, time, approval và hậu kiểm** đáng tin. Sự cố SIEM không được trở thành lý do xóa hoặc bịa đầy đủ audit; phải ghi rõ đoạn mất kết nối và cách bảo toàn bằng chứng.

## 42. Câu hỏi tự kiểm tra

**Câu 1. Một dòng EMERGENCY_LOGIN_SUCCESS có đủ gọi là ghi log đầy đủ không?**

**Trả lời:** Không. Nó chưa chứng minh quyền nào được cấp, operator đã làm gì, trên resource nào, hiệu lực ra sao và có thu hồi/hậu kiểm chưa.

**Câu 2. Có nên ghi access token để lần sau so sánh dễ hơn không?**

**Trả lời:** Không. Token thô là credential có thể bị lạm dụng; dùng định danh/fingerprint được thiết kế an toàn và metadata cần thiết.

**Câu 3. Một phiên PAM có video recording rồi có cần API audit nữa không?**

**Trả lời:** Có thể cần. Video không bảo đảm ghi đủ backend outcome, background job, API và những đường không qua PAM.

**Câu 4. Nếu SIEM lỗi, có thể cho mọi lệnh emergency chạy không log không?**

**Trả lời:** Không mặc định. Cần tuân theo policy về protected buffer, fail-closed và đường continuity được phê duyệt trước, có kiểm soát/evidence thay thế khi được phép.

**Câu 5. SCIM đã gỡ group emergency nhưng token cũ còn gọi API được thì đã thu hồi hoàn tất chưa?**

**Trả lời:** Chưa. Phải xử lý token/session/ACL liên quan và kiểm chứng quyền hiệu lực ở resource server.

**Câu 6. Một người có thể tự review log của chính phiên khẩn cấp không?**

**Trả lời:** Khi SoD yêu cầu độc lập thì không. Reviewer phải có thẩm quyền và độc lập với operator hoặc được kiểm soát theo policy ngoại lệ có căn cứ.

**Câu 7. Nếu thiếu log của ba phút, có được khẳng định không có hành động nào xảy ra trong khoảng đó không?**

**Trả lời:** Không. Phải đánh dấu gap, tìm evidence bổ sung từ target/PAM/state change và ghi giới hạn kết luận.

**Câu 8. Một workload thực hiện restore không có human login, có cần ghi actor không?**

**Trả lời:** Có. Ghi workloadId/serviceId, owner, trigger, incident, job/version, target, action, result và policy liên quan.

## 43. Checklist thiết kế “Ghi log đầy đủ” cho Emergency Access

| Câu hỏi | Bằng chứng/kiểm soát cần có |
| --- | --- |
| Đã định nghĩa các đường emergency access được phép? | PAM, break-glass, local admin, API, workload |
| Có event taxonomy xuyên suốt vòng đời? | Request → Verify → Approve → Activate → Use → Revoke → Review |
| Có actor và account mapping đúng? | Stable identity, issuer/sub, PAM operator, target account |
| Có incident/approval/policy reference? | Căn cứ kích hoạt và policyVersion |
| Có role/action/resource/tenant scope rõ? | Entitlement delta, resource IDs, ownership |
| Có log Deny/Indeterminate, không chỉ Success? | PDP/PEP/target decision và error reason |
| Có log hành động thực tế? | Command/API/DB/control-plane/data-access theo risk |
| Có correlation giữa các nguồn? | RequestId, incidentId, sessionId, operationId |
| Có timestamps nhất quán? | Event/recorded/received/verifiedAt và skew alerts |
| Có cách giám sát đường bypass PAM? | Target-level logs, network policy và integration tests |
| Có chặn secret/token trong audit? | Field allowlist, masking, secret leak tests |
| Có bảo vệ log khỏi operator sửa/xóa? | SoD, independent storage, retention control |
| Có integrity/coverage verification? | Checkpoint, event gap, source heartbeat, restore tests |
| Có cơ chế buffering khi collector lỗi? | Protected queue/journal, retry, lag và alert |
| Có playbook khi logging không sẵn sàng? | Fail-closed hoặc approved continuity với evidence |
| Có monitoring gần thời gian thực? | SIEM detection, SOC owner, response playbook |
| Có reviewer độc lập sau phiên? | Review task, findings, result, dueAt |
| Có giới hạn xem video/nhật ký nhạy cảm? | RBAC/ABAC và audit viewer access |
| Có retention và legal hold phù hợp? | Policy, phân loại log, retention/approval |
| Có link với IdP/SSO/MFA? | Authentication path và assurance được xác minh |
| Có link với SCIM/RBAC/ABAC/PBAC? | Role/grant changes, policy decisions, target rights |
| Có kiểm tra Joiner/Mover/Leaver? | Eligibility, revoke, stale account và pending jobs |
| Có quản lý workload emergency identity? | ServiceId, ownerTeam, job/incident, credential lifecycle |
| Có log phiên, token và credential sau kết thúc? | Session end, token/grant/key revoke evidence |
| Có readback và negative access tests? | Effective Deny tại target trong scope |
| Có trạng thái UNKNOWN/UNVERIFIED đúng nghĩa? | Không đóng case khi thiếu bằng chứng |
| Có test chống giả actor, log injection và duplicate? | Structured logging, validation, idempotency |
| Có KPI về coverage, lag và review? | Monitoring dashboard và điều tra gap |

## 44. Tổng kết

**Ghi log đầy đủ trong Emergency Access** là khả năng tạo và bảo vệ **chuỗi bằng chứng đáng tin cậy** từ lúc yêu cầu, xác minh và kích hoạt đặc quyền đến từng hành động quan trọng, thay đổi quyền, kết thúc phiên, thu hồi và hậu kiểm. Nó không phải một file ghi “admin logged in”, cũng không phải việc lưu mọi bí mật trong log. Một hệ thống tốt phải **định danh chính xác actor, gắn incident/request/session/operation, ghi Permit/Deny và kết quả thực tế, bảo vệ integrity, giảm dữ liệu nhạy cảm, phát hiện log gap và bảo đảm reviewer độc lập**.

Trong vòng đời **Joiner–Mover–Leaver**, **HRIS/nguồn bảo trợ** cung cấp căn cứ về người và quan hệ; **IAM/IGA** quản trị điều kiện truy cập khẩn và entitlement; **IdP/SSO/MFA** chứng minh authentication khi sẵn sàng; **PAM/JIT** giới hạn và ghi nhận việc kích hoạt đặc quyền; **SCIM/API** đồng bộ role/account; **RBAC/ABAC/PBAC cùng PDP/PEP** quyết định và thực thi quyền tại tài nguyên. **Workload/service accounts** cần identity, owner và log riêng. Chỉ khi có **bằng chứng log đủ để giải thích hành động, người độc lập rà soát, và quyền đã thực sự bị chặn sau phiên tại hệ thống đích**, tổ chức mới có thể vận hành emergency access vừa sẵn sàng phục hồi vừa hạn chế lạm dụng và **quyền truy cập tồn dư**.
