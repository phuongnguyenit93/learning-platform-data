# Xác định audit khi thiết kế chương trình IAM

Một chương trình **Identity and Access Management (IAM)** chỉ thực sự có thể kiểm soát quyền truy cập khi tổ chức trả lời được: **ai đã làm gì, trên danh tính hoặc tài khoản nào, vì lý do gì, theo chính sách nào, khi nào, kết quả ra sao và bằng chứng nào xác nhận trạng thái tại hệ thống đích?** Tập hợp yêu cầu về ghi nhận, bảo vệ, liên kết, lưu giữ, kiểm tra và sử dụng các thông tin đó được gọi là **thiết kế audit** (kiểm toán, dấu vết kiểm toán).

Ví dụ, hệ thống nhân sự báo một nhân viên nghỉ việc lúc 18:00. IAM gửi lệnh vô hiệu hóa IdP lúc 18:01 và lệnh SCIM đến ứng dụng lúc 18:02. Tuy nhiên ứng dụng báo lỗi, còn tài khoản local vẫn hoạt động tới 18:20. Nếu chỉ lưu một dòng “Leaver processed successfully” lúc 18:02, báo cáo sẽ che giấu **18 phút quyền truy cập còn tồn tại**. Audit đúng phải tách sự kiện nghiệp vụ, quyết định, lệnh, kết quả thực thi và bằng chứng đọc lại từ đích.

Bài học thuộc chương **Thiết kế chương trình IAM** của module `SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE`. Nội dung tập trung vào quản lý vòng đời danh tính **Joiner–Mover–Leaver (JML)**, IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, quyền đặc quyền và mục tiêu giảm quyền truy cập tồn dư.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **audit log**, **audit trail**, **evidence**, **monitoring**, **access review** và **reconciliation**.
2. Chọn sự kiện cần ghi cho vòng đời danh tính, tài khoản, role, policy, phê duyệt, phiên đăng nhập và thay đổi quyền.
3. Định nghĩa bản ghi audit có actor, subject, target, action, reason, policy version, thời gian, correlation ID và kết quả có thể xác minh.
4. Thiết kế đường liên kết **nguồn có thẩm quyền → quyết định IAM → yêu cầu thực thi → kết quả ở đích → đối soát/khắc phục**.
5. Xử lý audit cho tài khoản đặc quyền, break-glass, service account, workload identity và trường hợp cấp quyền qua nhiều hệ thống.
6. Bảo vệ tính toàn vẹn, bảo mật, phân quyền truy cập, tính sẵn sàng và vòng đời lưu giữ của dữ liệu audit.
7. Thiết kế ca kiểm thử và chỉ số phát hiện thiếu bản ghi, sai thứ tự, quyền còn tồn dư hoặc sự kiện chưa có bằng chứng hoàn tất.

## 2. Audit trong IAM có nghĩa là gì?

**Audit** là khả năng tái dựng và đánh giá những hoạt động có ý nghĩa bảo mật hoặc quản trị danh tính từ các bản ghi và bằng chứng được thu thập có hệ thống. Nó không chỉ là việc bật một tùy chọn “Enable logging”.

| Khái niệm | Mục đích | Ví dụ |
|---|---|---|
| **Event log** | Ghi nhận một sự kiện kỹ thuật hoặc nghiệp vụ đơn lẻ. | “Connector gửi yêu cầu disable account”. |
| **Audit trail** | Liên kết các sự kiện thành chuỗi có thể truy xuất. | HRIS Leaver → IAM policy → lệnh SCIM → SaaS confirmed. |
| **Audit evidence** | Dữ liệu làm căn cứ chứng minh một điều đã xảy ra hoặc trạng thái được quan sát. | Quyết định approver, phản hồi từ API, quyền đọc lại tại đích. |
| **Monitoring / alerting** | Quan sát và cảnh báo hành vi bất thường hoặc vi phạm ngưỡng. | Leaver đã có hiệu lực nhưng một SaaS account còn active. |
| **Access review** | Người có thẩm quyền xác nhận quyền hiện có còn cần thiết không. | Data owner chọn Revoke đối với quyền xuất báo cáo. |
| **Reconciliation** | So sánh trạng thái truy cập mong muốn với trạng thái thực tế. | IdP disabled nhưng local account vẫn active. |
| **Forensic investigation** | Tái dựng diễn biến, phạm vi và nguyên nhân một sự cố. | Ai cấp quyền admin và đã sử dụng từ phiên nào. |

**Audit không tự ra quyết định cấp quyền.** Policy model và role model quy định những quyền nào hợp lệ; approval cung cấp quyết định chấp thuận khi cần; provisioning thực hiện thay đổi; audit lưu dấu vết và bằng chứng để kiểm tra tất cả những bước đó.

**Có log không có nghĩa đã chứng minh thành công.** Ví dụ `HTTP 200` từ gateway chứng minh lời gọi được xử lý theo ngữ nghĩa API, nhưng chưa chắc người dùng đã mất mọi quyền hiệu lực ở SaaS. Để kết luận thu hồi, cần đọc lại quyền ở đích hoặc bằng chứng tương đương được quy định rõ trong hợp đồng kiểm soát.

## 3. Xác định câu hỏi kiểm toán trước khi chọn công nghệ

Mỗi nhóm liên quan sẽ đặt các câu hỏi khác nhau:

| Người sử dụng audit | Câu hỏi quan trọng |
|---|---|
| **IAM operations** | Event JML nào chưa được xử lý? Connector nào thất bại, retry bao nhiêu lần? |
| **Application/data owner** | Ai được cấp role hoặc quyền dữ liệu? Ai duyệt và còn đúng mục đích không? |
| **Security Operations** | Tài khoản nào bị khóa, ai gỡ khóa, phiên đặc quyền nào hoạt động sau đó? |
| **Internal audit / compliance** | Bằng chứng nào chứng minh quy trình đã thực thi và ngoại lệ được quản lý? |
| **Incident response** | Quyền nào từng tồn tại trong khoảng thời gian sự cố, ai sử dụng, đã thu hồi lúc nào? |
| **Privacy / data governance** | Audit lưu dữ liệu cá nhân nào, ai có thể xem, lưu trong bao lâu? |
| **Platform engineering** | Tích hợp nào làm mất event, thay đổi schema hay có clock skew? |

Từ các câu hỏi này, thiết kế phải xác định **sự kiện bắt buộc**, **nguồn dữ liệu**, **chủ thể chịu trách nhiệm**, **thời điểm**, **độ tin cậy**, **độ trễ chấp nhận**, **thời hạn lưu giữ** và **cách chứng minh kết quả**.

Không nên thiết kế audit bằng cách thu thập tất cả payload từ mọi hệ thống. Việc lưu toàn bộ dữ liệu có thể làm lộ bí mật, thông tin cá nhân hoặc tăng chi phí mà vẫn không có đủ ngữ nghĩa để kiểm toán.

## 4. Phạm vi audit: phải bao phủ các điểm quyết định và thực thi

Một sơ đồ ranh giới audit cần đi qua toàn bộ chu trình IAM:

~~~mermaid
flowchart LR
    SRC["HRIS / VMS / Service catalog<br/>Sự kiện có thẩm quyền"] --> INGEST["Identity event ingestion<br/>Validate + correlate"]
    INGEST --> DECIDE["IAM / IGA<br/>Policy + role + approval"]
    DECIDE --> ACT["Provisioning<br/>SCIM / API / PAM / IaC"]
    ACT --> TARGET["IdP / SaaS / Cloud / DB<br/>Account + entitlement"]
    TARGET --> VERIFY["Target readback<br/>Reconciliation"]
    SRC --> AUDIT["Central audit pipeline"]
    INGEST --> AUDIT
    DECIDE --> AUDIT
    ACT --> AUDIT
    VERIFY --> AUDIT
    AUDIT --> PROTECT["Bảo vệ + lưu giữ<br/>Truy vấn + phát hiện bất thường"]
    PROTECT --> REVIEW["IAM / Security / Owners<br/>Investigation + remediation"]
~~~

Các miền cần đưa vào scope:

- **Nguồn danh tính và quan hệ:** người mới, thay phòng ban, hết hợp đồng, tuyển lại, service owner thay đổi, workload retired.
- **Identity registry / correlation:** tạo identity, ghép/nối account, sửa liên kết, xử lý trùng danh tính hoặc orphan.
- **Account lifecycle:** tạo, kích hoạt, khóa, vô hiệu hóa, xóa, phục hồi account ở IdP, directory và ứng dụng đích.
- **Access governance:** yêu cầu quyền, phê duyệt, từ chối, ủy quyền, gán/thu hồi role, review, ngoại lệ và SoD.
- **Authentication:** đăng nhập, MFA, thay đổi cơ chế xác thực, gỡ/bật security hold, các hành vi phiên đáng chú ý.
- **Authorization và entitlement:** thay đổi permission, policy, role mapping, đặc quyền cloud, quyền trực tiếp và quyết định truy cập nhạy cảm khi phù hợp.
- **Non-human access:** tạo service account, key/certificate, role workload, thay owner, luân chuyển/thu hồi credential.
- **Administrative/configuration changes:** ai thay cấu hình IdP, connector, luồng approval, chính sách audit hoặc quyền truy cập chính hệ thống audit.
- **Remediation:** lỗi connector, retry, ticket thủ công, readback, drift, bằng chứng khắc phục và đóng ngoại lệ.

**Phạm vi audit không đồng nhất với danh sách ứng dụng SSO.** Các account local, tài khoản quản trị, khóa API hoặc token trực tiếp có thể nằm ngoài IdP nhưng vẫn có khả năng truy cập. Cần chọn nguồn log hoặc phương thức thu thập thay thế để bao phủ chúng.

## 5. Phân loại audit event: sự kiện, quyết định, lệnh và trạng thái đích

Nên có **taxonomy** (hệ thống phân loại) nhất quán để một người điều tra không phải suy đoán ý nghĩa của một chuỗi log tùy ý:

| Event class | Ví dụ event type | Ai phát | Ý nghĩa |
|---|---|---|---|
| **SOURCE_EVENT** | `IDENTITY_RELATIONSHIP_TERMINATED` | HRIS/VMS qua ingestion | Quan hệ nghiệp vụ hết hiệu lực. |
| **CORRELATION_EVENT** | `ACCOUNT_LINK_ESTABLISHED` | Identity registry | Account được liên kết với identity/workload. |
| **POLICY_DECISION** | `ROLE_ASSIGNMENT_EVALUATED` | IGA/policy engine | Quyền mong muốn được tính từ chính sách. |
| **APPROVAL_DECISION** | `ACCESS_REQUEST_APPROVED` | Approval service | Người có thẩm quyền đồng ý với request/version. |
| **COMMAND_ISSUED** | `ACCOUNT_DISABLE_REQUESTED` | Provisioning orchestrator | Lệnh đã được phát tới connector. |
| **COMMAND_RESULT** | `ACCOUNT_DISABLE_RESPONSE_RECEIVED` | Connector | Đích trả một kết quả kỹ thuật, có thể vẫn cần xác minh. |
| **TARGET_OBSERVATION** | `TARGET_ACCOUNT_OBSERVED_DISABLED` | Readback/reconciliation | Trạng thái đích được kiểm tra tại một thời điểm. |
| **DRIFT_FINDING** | `LEAVER_ACCESS_STILL_ACTIVE` | Reconciliation engine | Desired state và observed state khác nhau. |
| **REVIEW_DECISION** | `ACCESS_REVIEW_REVOKE_DECIDED` | Access review service | Reviewer kết luận một grant không còn hợp lệ. |
| **REMEDIATION_RESULT** | `REVOKE_CONFIRMED` | Fulfillment controller | Đã xác nhận kết quả khắc phục. |
| **SECURITY_EVENT** | `SECURITY_HOLD_PLACED` | SOC/IdP workflow | Quyết định hạn chế truy cập do nguồn an ninh có thẩm quyền. |
| **ADMIN_CHANGE** | `POLICY_VERSION_PUBLISHED` | Policy administration | Chính sách được cập nhật với version mới. |

Một `COMMAND_ISSUED` không được tự chuyển thành `REMEDIATION_RESULT: CONFIRMED`. Khi hệ thống đích chưa trả lời hoặc không thể đọc lại trạng thái, phải ghi rõ **chưa có bằng chứng xác nhận**, rồi xử lý theo rủi ro.

### Audit sự kiện thất bại và bị từ chối

Các trường hợp **không được phép** cũng cần audit, chẳng hạn:

- Yêu cầu cấp role đặc quyền bị từ chối vì không đạt điều kiện hoặc vi phạm SoD.
- Người dùng cố truy cập tài nguyên tenant khác và bị PEP từ chối.
- Approver cố duyệt request của chính mình.
- Connector không thể thu hồi một tài khoản đã hết quan hệ.
- Service account không được cấp thêm quyền vì chưa có owner hợp lệ.

Lưu kết quả `DENY` hoặc `FAILED` cùng mã lý do phù hợp; tránh ghi toàn bộ thông tin nhạy cảm trong thông báo lý do có thể bị trả cho client.

## 6. Thiết kế bản ghi audit có thể truy vết

Một bản ghi chuẩn cần trả lời **who – what – when – where – why – how – outcome**, trong đó **actor** (người hoặc thành phần thực hiện) khác **subject** (danh tính chịu tác động) và **target** (tài khoản/quyền/tài nguyên bị tác động).

| Trường | Ý nghĩa | Ví dụ |
|---|---|---|
| `auditEventId` | Khóa duy nhất của bản ghi audit | `aud-f1c7`. |
| `eventType` / `eventClass` | Ý nghĩa của sự kiện | `ACCOUNT_DISABLE_REQUESTED` / `COMMAND_ISSUED`. |
| `actor.type`, `actor.id` | Người hoặc workload đã thực hiện hành động | `SERVICE`, `iam-provisioner`. |
| `subject.identityId` | Danh tính nội bộ bị ảnh hưởng | `idn-1042`. |
| `subject.sourceRef` | Khóa có thẩm quyền của quan hệ | `HRIS/EMP-1042`. |
| `target.systemId`, `tenantId` | Hệ thống và ranh giới kỹ thuật | `crm-saas`, `corp-vn`. |
| `target.nativeAccountId` | ID account tại đích | `user-8820`. |
| `target.entitlementId` | Role, group hoặc quyền nếu có | `finance-admin`. |
| `action` | Thao tác nghiệp vụ hoặc kỹ thuật | `account:disable`, `role:revoke`. |
| `decision` / `outcome` | Kết quả đánh giá hoặc thực thi | `PERMIT`, `DENY`, `FAILED`, `CONFIRMED`. |
| `reasonCode` | Mã lý do không tiết lộ dữ liệu nhạy cảm | `LIFECYCLE_LEAVER`. |
| `policyId` / `policyVersion` | Chính sách quyết định hành động | `employee-leaver`, `8`. |
| `requestId` / `approvalRef` | Yêu cầu hoặc phê duyệt có liên quan | `ar-2048`. |
| `correlationId` / `causationId` | Liên kết cùng một luồng và quan hệ nguyên nhân | `corr-7b92`, `evt-leaver-23`. |
| `occurredAt` | Khi hành động xảy ra ở nguồn | Instant có múi giờ/offset. |
| `receivedAt` / `recordedAt` | Khi audit pipeline tiếp nhận và lưu | Dùng đo độ trễ và phát hiện event muộn. |
| `effectiveAt` | Khi thay đổi nghiệp vụ có hiệu lực | Không đồng nhất với giờ phát thông báo. |
| `sourceEventVersion` | Phiên bản của bản ghi nguồn nếu có | `23`. |
| `evidenceRefs` | Tham chiếu đến bằng chứng đích hoặc quyết định | ID readback, ticket, log đáng tin. |
| `schemaVersion` | Phiên bản hợp đồng audit | `1`. |

**Không dùng email hoặc username làm khóa duy nhất xuyên hệ thống.** Chúng có thể đổi, tái sử dụng và trùng giữa tenant. Nên lưu `identityId` ổn định, đồng thời có `sourceSystem + sourceRecordId` và `systemId + tenantId + nativeAccountId`.

### Ví dụ bản ghi audit cho lệnh Leaver

~~~json
{
  "auditEventId": "aud-7182",
  "schemaVersion": 1,
  "eventClass": "COMMAND_ISSUED",
  "eventType": "ACCOUNT_DISABLE_REQUESTED",
  "actor": {
    "type": "SERVICE",
    "id": "iam-provisioner"
  },
  "subject": {
    "identityId": "idn-1042",
    "identityType": "EMPLOYEE",
    "sourceRef": "HRIS/EMP-1042"
  },
  "target": {
    "systemId": "crm-saas",
    "tenantId": "corp-vn",
    "nativeAccountId": "user-8820"
  },
  "action": "account:disable",
  "reasonCode": "LIFECYCLE_LEAVER",
  "policy": {
    "policyId": "employee-leaver",
    "policyVersion": 8
  },
  "sourceEventId": "evt-leaver-23",
  "sourceEventVersion": 23,
  "correlationId": "corr-7b92",
  "causationId": "evt-leaver-23",
  "actionId": "act-disable-crm-1042",
  "occurredAt": "2026-11-23T18:02:00+07:00",
  "recordedAt": "2026-11-23T18:02:01+07:00",
  "effectiveAt": "2026-11-23T18:00:00+07:00",
  "outcome": "REQUESTED",
  "evidenceRefs": []
}
~~~

Ví dụ có `outcome: REQUESTED` chứ **không phải `CONFIRMED`**: ở thời điểm này hệ thống chỉ biết đã gửi lệnh. Một bản ghi khác phải chứa kết quả connector và/hoặc bằng chứng đọc lại tài khoản SaaS đã disabled. Dữ liệu là hợp đồng minh họa, không phải schema bắt buộc của bất kỳ nhà cung cấp IAM nào.

## 7. Correlation ID, causation ID và khả năng tái dựng một hành động

Một sự kiện Leaver có thể tạo hàng chục thao tác tại IdP, SaaS, cloud, database và công cụ CI/CD. Nếu mỗi hệ thống ghi một request ID độc lập, việc nối các bước bằng tên người dùng và thời gian là **không đủ tin cậy**.

Nên dùng ít nhất:

- **`correlationId`:** giữ ổn định cho cả luồng nghiệp vụ hoặc transaction JML được điều phối.
- **`sourceEventId`:** tham chiếu event từ HRIS/VMS/service catalog.
- **`causationId`:** bản ghi/hành động trực tiếp dẫn đến bản ghi hiện tại.
- **`actionId`:** định danh lệnh cụ thể để retry/idempotency và kiểm tra trạng thái.
- **`targetRef`:** hệ thống/tenant/native account hoặc entitlement mà action thực sự tác động.
- **`attemptId`:** định danh lần thử lệnh, tránh gộp ba lần retry thành một lần thành công mơ hồ.
- **`evidenceId`:** định danh bằng chứng readback/response sau khi thực thi.

Ví dụ:

~~~text
sourceEventId: evt-leaver-23
correlationId: corr-7b92
|
+-- policyDecision: dec-12      -> desired access = DISABLED
|
+-- actionId: act-idp-1042
|   +-- attempt-1               -> connector SUCCESS
|   +-- evidence-idp-1042       -> account DISABLED (confirmed)
|
+-- actionId: act-crm-1042
|   +-- attempt-1               -> timeout
|   +-- attempt-2               -> accepted
|   +-- evidence-crm-1042       -> account still ACTIVE (drift)
|   +-- attempt-3               -> accepted
|   +-- evidence-crm-1042-b     -> account DISABLED (confirmed)
|
+-- actionId: act-cloud-1042
    +-- attempt-1               -> role revoked
    +-- evidence-cloud-1042     -> role absent (confirmed)
~~~

**Retry không được tạo một lịch sử giả.** Mỗi attempt có kết quả riêng, còn `actionId` biểu diễn ý định duy nhất. Khi đích hỗ trợ idempotency key, truyền khóa phù hợp; khi không hỗ trợ, đọc trạng thái trước/sau retry và áp thao tác an toàn.

### Ba loại thời gian không được trộn lẫn

1. **Thời gian nghiệp vụ:** `effectiveAt`, ví dụ khi quan hệ lao động chấm dứt.
2. **Thời gian hoạt động:** `occurredAt`, `sentAt`, `receivedAt` của event/lệnh/response.
3. **Thời gian xác minh:** `observedAt` hoặc `verifiedAt` khi hệ thống đích được đọc lại.

Các timestamp cần định dạng không mơ hồ, ưu tiên UTC hoặc ISO 8601 kèm offset; đồng bộ đồng hồ phù hợp và theo dõi **clock skew**. Khi giờ nguồn khác giờ ghi nhận, audit không tự suy rằng nguồn sai; ghi cả hai và dấu hiệu độ tin cậy để điều tra.

## 8. Bằng chứng audit theo Joiner–Mover–Leaver

### 8.1. Joiner — chứng minh quyền được cấp có căn cứ

Một chuỗi Joiner có thể cần:

1. **Nguồn:** HRIS/VMS ghi nhận quan hệ và ngày có hiệu lực; danh tính được liên kết bằng khóa ổn định.
2. **Xác minh:** điều kiện tạo/kích hoạt account đã đạt, không có security hold.
3. **Chính sách:** role birthright hoặc yêu cầu approval hợp lệ được tính từ RBAC/ABAC và policy version đã phê duyệt.
4. **Quyết định:** ai duyệt quyền nhạy cảm, cho đúng subject/tenant/scope và khoảng thời gian nào.
5. **Thực thi:** IdP, SCIM hoặc API nhận lệnh tạo account, cấp nhóm/quyền.
6. **Xác nhận:** account và entitlement thực tế đã có; quyền không được cấp ngoài phạm vi.

Không nên ghi “Joiner completed” nếu tài khoản cốt lõi còn lỗi hoặc quyền nhạy cảm được cấp trước ngày hiệu lực. Audit phải thể hiện bước nào đang chờ và owner đang chịu trách nhiệm xử lý.

### 8.2. Mover — phát hiện quyền cũ còn tồn tại

Khi nhân viên chuyển Finance sang Engineering, cần ghi:

- Event thay đổi vai trò và version nguồn;
- Policy/role catalog phiên bản nào tính quyền mong muốn;
- Trạng thái quyền **trước và sau** ở mức tham chiếu entitlement;
- Các grant phải gỡ, các grant mới được phép cấp và nguồn gốc từng grant;
- Kiểm tra SoD khi quyền cũ và mới xung đột;
- Kết quả từng connector và trạng thái readback.

**Không log thông tin nhạy cảm nguyên bản nếu có thể lưu các ID và snapshot reference.** Ví dụ không cần ghi toàn bộ dữ liệu phiếu tài chính để chứng minh role `FINANCE_ANALYST` đã được thu hồi.

Với các role có entitlement chồng lắp, audit phải chỉ rõ **assignment nào đã bị gỡ và quyền hiệu lực sau đó**. Gỡ một role không nhất thiết làm quyền native biến mất nếu role hợp lệ khác vẫn cấp quyền đó.

### 8.3. Leaver — chứng minh đã chấm dứt truy cập, không chỉ đã gửi lệnh

Một bảng kiểm toán Leaver có thể có cấu trúc:

| Mốc/bằng chứng | Ví dụ | Có đủ để xác nhận thu hồi? |
|---|---|---|
| `EMPLOYMENT_TERMINATED` từ HRIS | Quan hệ kết thúc lúc 18:00 | Chưa: chỉ xác nhận điều kiện nghiệp vụ. |
| IAM đánh giá chính sách | Desired state = no access | Chưa: mới là quyết định. |
| Lệnh IdP disable đã gửi | `REQUESTED` lúc 18:01 | Chưa: cần xác nhận. |
| IdP readback disabled | `CONFIRMED` lúc 18:03 | Có, cho account IdP cụ thể. |
| SCIM gửi lệnh vô hiệu hóa SaaS | `ACCEPTED` lúc 18:02 | Chưa: chưa xác minh tài khoản SaaS. |
| SaaS readback vẫn active | `DRIFT` lúc 18:05 | Không: cần remediation. |
| SaaS readback disabled | `CONFIRMED` lúc 18:20 | Có, cho account SaaS cụ thể. |
| Cloud role đọc lại đã absent | `CONFIRMED` lúc 18:04 | Có, cho role/tài nguyên được kiểm tra. |
| Token hoặc credential riêng | Không có dữ liệu | Chưa thể kết luận toàn bộ truy cập đã được thu hồi. |

**Kết luận Leaver hoàn tất phải dựa trên account scope và control scope đã định nghĩa**, có bằng chứng cho từng hành động bắt buộc và phân loại ngoại lệ còn mở. Không thể chứng minh tuyệt đối rằng không còn bất kỳ đường truy cập nào nếu inventory thiếu hệ thống, tenant hoặc credential; vì vậy phải công bố độ bao phủ và duy trì discovery/reconciliation.

### 8.4. Security hold và khôi phục quyền

Khi SOC đặt `securityHold=true`, audit cần ghi:

- Ai hoặc hệ thống có thẩm quyền đã kích hoạt;
- Đối tượng, nguyên nhân theo mã phù hợp, thời điểm;
- Phiên/credential bị chặn hoặc bị thu hồi thực tế;
- Ai có thẩm quyền gỡ khóa, lý do và bằng chứng phê duyệt;
- Trạng thái thực tế sau khi mở lại, tránh tự phục hồi quyền đã hết hiệu lực do JML.

Một event HRIS `ACTIVE` đến sau **không được làm mờ dấu vết khóa** và không tự đóng sự cố bảo mật.

## 9. Audit với IdP, SSO, SCIM và hệ thống đích

Mỗi thành phần nhìn thấy một phần của chuỗi truy cập. Cần thiết kế cách hợp nhất dữ liệu mà không đánh đồng ý nghĩa:

| Thành phần | Log có giá trị | Giới hạn phải lưu ý |
|---|---|---|
| **IdP / directory** | Tạo/khóa user, thay group, credential, MFA, security hold | Không chứng minh mọi account local ở ứng dụng đã bị vô hiệu hóa. |
| **SSO (SAML/OIDC)** | Thành công/thất bại đăng nhập, ứng dụng/phiên, claim quan trọng | Phiên và token ở app có thể tiếp tục sau khi IdP thay đổi. |
| **SCIM / provisioning API** | Request/response, mã kết quả, target native ID | ACK thành công không tự chứng minh quyền hiệu lực đã thay đổi đúng. |
| **IGA / role engine** | Quyền mong muốn, nguồn cấp, policy/version, SoD | Desired state khác observed state khi connector lỗi hoặc cấp ngoài luồng. |
| **Application/API** | Quyết định cho phép/từ chối thao tác nhạy cảm, thay đổi dữ liệu | Phải ghi identity và tài nguyên sau khi đã kiểm chứng, không tin client-supplied role. |
| **Cloud/PAM** | Assume role, nâng quyền JIT, đổi policy, phiên đặc quyền | Cần liên kết session với danh tính cá nhân hoặc workload thật. |
| **Legacy/local system** | Tạo user local, thay mật khẩu, đổi quyền, xác nhận thao tác | Có thể chỉ có log riêng; cần nguồn thu thập và cách xác nhận phù hợp. |

### Audit cho RBAC/ABAC

- **RBAC:** ghi thay đổi role catalog, mapping role → entitlement, gán/gỡ role, nguồn assignment và role kế thừa.
- **ABAC:** ghi policy/version, subject/resource/action, lý do Permit/Deny cho thao tác quan trọng và các thuộc tính quyết định đã được lấy từ nguồn nào.
- **SoD:** ghi xung đột được phát hiện, quyền liên quan, quyết định chặn/ngoại lệ và người chịu trách nhiệm.
- **Runtime:** chỉ cần lưu **các dữ kiện đủ giải thích quyết định**; không nhất thiết chép toàn bộ claim, PII hoặc tài liệu bị truy cập.

Với hệ thống có lưu lượng rất cao, không phải mọi quyết định đọc dữ liệu ít rủi ro đều cần log đầy đủ từng request. Cần thiết kế mức chi tiết theo rủi ro, khả năng lưu giữ và nhu cầu kiểm toán; nhưng **hành động nhạy cảm**, thay đổi quyền, từ chối đáng chú ý và thay đổi cấu hình bảo mật phải được quản lý sao cho có thể điều tra.

## 10. Audit approval, review, ngoại lệ và SoD

### Approval

Một quyết định phê duyệt quyền phải liên kết:

- Request ID và **version của nội dung đã được duyệt**;
- Requester, beneficiary, entitlement, tenant, scope và effective window;
- Approver thực sự, authority/delegation và thời điểm;
- Kết quả approve/reject, reason code, policy version và kiểm tra SoD;
- Lệnh cấp quyền sau phê duyệt và readback ở đích.

Nếu request đổi từ `REPORT_READ` sang `REPORT_EXPORT` sau khi đã được duyệt, audit phải giữ được bản đã được chấp thuận và bản mới. Không được gán quyết định cũ cho scope mới mà không có reapproval theo policy.

### Access review

Mỗi review item cần có snapshot version, grant provenance, reviewer và authority, quyết định `KEEP` / `REVOKE` / `MODIFY` / `INVESTIGATE`, lý do và thời hạn. Nếu reviewer chọn `REVOKE`, audit phải theo dõi remediation đến trạng thái đích.

Ví dụ: `REVOKE_DECIDED` nhưng `REMEDIATION_FAILED` là một kết quả chưa hoàn tất, không thể gộp thành “review success”. Report cần phân biệt **review decision completion** và **remediation confirmation**.

### Ngoại lệ và break-glass

Một ngoại lệ phải có owner chấp nhận rủi ro, phạm vi, lý do, biện pháp bù trừ và ngày hết hạn. Đối với break-glass, cần đặc biệt ghi:

1. Ai hoặc cơ chế nào kích hoạt và với danh tính/credential nào.
2. Tại sao tình huống khẩn cấp được áp dụng và hệ thống nào bị ảnh hưởng.
3. Những phiên và thao tác đặc quyền đã diễn ra, kèm ID của người vận hành khi có thể.
4. Việc kết thúc phiên, gỡ quyền, luân chuyển credential và kết quả xác nhận.
5. Kết luận hậu kiểm, người rà soát độc lập và hành động khắc phục.

Không nên thiết kế “break-glass ⇒ không ghi audit”; ngay cả khi mạng hoặc IdP bị hỏng, cơ chế khẩn cấp cần có phương án ghi nhận an toàn và đồng bộ bằng chứng khi khôi phục.

## 11. Audit tài khoản dịch vụ, workload identity và credential

Danh tính phi con người có thể thực hiện nhiều hành động hơn tài khoản cá nhân và thường không trực tiếp đi theo HRIS. Audit cần nối **workload identity → service catalog → owner chịu trách nhiệm → tài nguyên và quyền hiệu lực**.

| Hoạt động | Dữ kiện nên ghi |
|---|---|
| Tạo service account/workload | `serviceId`, môi trường, mục đích, owner, role ban đầu, approver/policy. |
| Cấp role cho workload | Resource scope, loại hành động, thời hạn, policy và bằng chứng đích. |
| Thay owner | Owner trước/sau, nguồn có thẩm quyền, người phê duyệt, kế hoạch rà soát credential. |
| Tạo hoặc luân chuyển credential | Key/certificate **identifier**, thời điểm phát hành/thu hồi và hệ thống quản lý; **không log secret**. |
| Cấp token ngắn hạn | Chủ thể workload, target audience/scope, session ID và chính sách nếu được hệ thống hỗ trợ. |
| Workload retired | Event nguồn, account/entitlement/credential phải thu hồi và kết quả xác minh. |
| Bị nghi lộ credential | Tín hiệu bảo mật, lệnh cô lập/rotation, owner xử lý và trạng thái sau khắc phục. |

**Không ghi API key, private key, password, bearer token hoặc secret thô vào audit log.** Nếu cần truy vết một credential, dùng ID/fingerprint không thể dùng như credential, hoặc tham chiếu an toàn tới hệ thống quản lý bí mật.

Khi kỹ sư là technical owner nghỉ việc, audit cho Leaver cần chứng minh **quyền cá nhân đã bị thu hồi**, đồng thời ghi nhiệm vụ chuyển owner và rà soát credential của workload. Không được tự suy `WORKLOAD_RETIRED` từ việc nhân viên nghỉ; dịch vụ có vòng đời riêng.

## 12. Bảo vệ tính toàn vẹn của audit trail

Audit là cơ sở điều tra, nên người có đặc quyền tại hệ thống được kiểm toán không được dễ dàng xóa hoặc viết lại bằng chứng về chính mình.

### Các lớp kiểm soát

| Kiểm soát | Mục đích |
|---|---|
| **Ghi tập trung qua đường thu thập đáng tin** | Giảm phụ thuộc vào log cục bộ có thể bị xóa. |
| **Tách quyền ghi/đọc/quản trị** | Admin ứng dụng không mặc nhiên được sửa/xóa audit history. |
| **Lưu trữ hạn chế sửa/xóa hoặc WORM khi phù hợp** | Hạn chế thay đổi bằng chứng đã ghi. |
| **Chữ ký, checksum, hash chain hoặc xác nhận integrity** | Hỗ trợ phát hiện thay đổi trái phép của tập log. |
| **Mã hóa truyền tải và lưu trữ** | Bảo vệ dữ liệu audit khỏi bị đọc trộm. |
| **Đồng bộ thời gian và version schema** | Hỗ trợ dựng lại thứ tự và ý nghĩa sự kiện. |
| **Quyền truy cập tối thiểu và ghi log truy vấn audit** | Ngăn lạm dụng dữ liệu audit và biết ai đã xem/xuất nó. |
| **Sao lưu, phục hồi và kiểm tra sẵn sàng** | Bảo đảm audit không biến mất khi xảy ra sự cố. |
| **Monitoring trạng thái pipeline** | Phát hiện agent/collector ngừng gửi, queue đầy, storage lỗi. |

**Hash không tự chứng minh sự kiện đã từng được phát sinh.** Nó có thể giúp phát hiện nội dung đã lưu bị sửa, nhưng nếu logger không ghi một sự kiện hoặc collector bị vô hiệu hóa từ trước thì chuỗi hash vẫn có thể “đúng”. Vì vậy cần vừa bảo vệ integrity, vừa có heartbeat, completeness checks và đối soát nguồn/đích.

### Nguy cơ đặc biệt

- Quản trị viên xóa lịch sử cấp quyền trước khi nghỉ việc.
- Ứng dụng cho phép thay `actorId` trong request log.
- Event log đến muộn và bị ghi đè vì cùng ID không có version.
- Collector bị tắt trong khi hệ thống vẫn chạy và phát sinh sự kiện.
- Kênh lưu trữ sự kiện đầy; hệ thống tiếp tục cho phép thay đổi đặc quyền mà không có bằng chứng.
- Dữ liệu audit bị xuất hàng loạt vì vai trò người đọc quá rộng.

Biện pháp phải được chọn theo threat model, năng lực nền tảng và mức rủi ro. Với thao tác quản trị đặc biệt, nếu không thể tạo bằng chứng bắt buộc, policy có thể **chặn thao tác hoặc chuyển sang chế độ khẩn cấp được quản trị riêng**; quyết định fail-open/fail-closed phải được thiết kế rõ, không để phát sinh ngẫu nhiên khi collector gặp lỗi.

## 13. Bảo vệ dữ liệu cá nhân và chính sách lưu giữ

Audit có thể chứa thông tin cá nhân: ID nhân viên, địa chỉ IP, thiết bị, thời điểm truy cập, resource ID, quyết định kỷ luật hoặc tín hiệu an ninh. Thu thập quá mức có thể tạo rủi ro riêng.

### Nguyên tắc thiết kế

1. **Data minimization:** chỉ ghi trường cần để giải thích quyết định, truy vết và đáp ứng yêu cầu đã xác định.
2. **Không ghi bí mật:** lọc password, token, cookie, SSH private key, client secret và nội dung bí mật trước khi log.
3. **Phân tầng quyền xem:** IAM operations có thể cần action status; security investigator có thể cần chi tiết điều tra; người khác không tự động được xem mọi log nhân sự.
4. **Ẩn hoặc mã hóa thuộc tính nhạy cảm:** ID ổn định có thể dùng để correlation; dữ liệu nhận diện bổ sung nên lấy từ hệ thống được phân quyền khi thật sự cần.
5. **Retention theo loại:** sự kiện thông thường, đặc quyền, điều tra sự cố và hồ sơ pháp lý có thể có yêu cầu lưu khác nhau.
6. **Lifecycle của audit data:** archive, retrieval, legal hold khi áp dụng và xóa an toàn khi hết thời hạn hợp lệ.
7. **Ghi nhận mọi truy cập đặc biệt vào kho log:** ai tìm kiếm/xuất dữ liệu, vì sao, phạm vi nào.

Không nên khẳng định một thời hạn lưu duy nhất cho mọi tổ chức. Chính sách retention phải dựa trên nghĩa vụ pháp lý/hợp đồng thực tế, mục tiêu điều tra, mức độ rủi ro, chi phí và quy định bảo vệ dữ liệu áp dụng. Sự kiện có legal hold hợp lệ có thể cần lưu khác với dữ liệu thông thường.

### Giảm nguy cơ rò rỉ qua log

Thay vì:

~~~text
Login failed: user=john@example.test token=eyJ... password=******
~~~

Ưu tiên bản ghi cấu trúc:

~~~json
{
  "eventType": "AUTHENTICATION_FAILED",
  "subjectRef": "idn-1042",
  "applicationId": "finance-portal",
  "reasonCode": "INVALID_CREDENTIAL",
  "occurredAt": "2026-11-23T09:15:20Z",
  "sessionId": "session-ref-20",
  "outcome": "DENY"
}
~~~

Ngay cả với `sessionId` cũng cần dùng giá trị tham chiếu **không đủ khả năng xác thực hoặc chiếm phiên**. Dữ liệu ví dụ minh họa cách hạn chế trường, không phải khuyến nghị lưu session token nguyên bản.

## 14. Bảo đảm đầy đủ và đáng tin: audit completeness

Một kho log có thể giữ nguyên mọi bản ghi đã nhận mà vẫn thiếu sự kiện vì mạng lỗi, collector dừng hoặc schema không tương thích. Cần thiết kế **khả năng nhận biết dữ liệu đang thiếu**.

| Rủi ro | Cơ chế phát hiện / xử lý |
|---|---|
| **Mất event trong luồng** | Sequence gap, so khớp số bản ghi nguồn, replay và reconciliation. |
| **Collector dừng** | Heartbeat, dữ liệu freshness, cảnh báo không có event khi kỳ vọng có. |
| **Event trùng** | Dedupe bằng `sourceSystem + eventId` hoặc khóa tương ứng. |
| **Event đến sai thứ tự** | Version/sequence theo nguồn và đối tượng; không dùng thời điểm nhận làm thẩm quyền. |
| **Schema thay đổi** | Schema version, kiểm tra trường bắt buộc, hàng lỗi có owner. |
| **Đồng hồ không khớp** | Ghi thời gian nguồn và thời gian collector; giám sát clock skew. |
| **Connector trả ACK nhưng quyền chưa đổi** | Đọc lại trạng thái ở đích và đối soát. |
| **Thao tác ngoài IAM** | Discovery quyền trực tiếp và audit nguồn native; phân loại drift. |
| **Lỗi lưu trữ audit** | Queue bền vững, retry, cảnh báo sớm, cơ chế ứng phó khi quá tải. |
| **Log bị sửa hoặc xóa** | Quyền hạn chế, immutable storage/tamper-evidence, điều tra integrity alert. |

Không nên hứa “exactly once” toàn tuyến chỉ vì message broker hỗ trợ một hình thức exactly-once trong phạm vi của nó. Thao tác tại SaaS hoặc cloud là side effect bên ngoài; phải chấp nhận mô hình **at-least-once + idempotent action + verification** khi phù hợp.

### Tách trạng thái đã biết và chưa biết

Một mô hình kết luận nên có ít nhất:

~~~text
BUSINESS_EVENT_RECEIVED
DECISION_RECORDED
COMMAND_DISPATCHED
TARGET_RESPONSE_RECEIVED
TARGET_STATE_VERIFIED
REMEDIATION_CLOSED
~~~

Nếu collector không nhận được phản hồi hoặc hệ thống đích không thể đọc lại, kết luận phải là **`UNKNOWN`, `PENDING` hoặc `EXCEPTION`** theo quy ước, không tự chuyển thành `SUCCESS`. Việc thiếu dữ liệu là một tín hiệu kiểm soát cần theo dõi, đặc biệt với Leaver và quyền đặc biệt.

## 15. Kiến trúc triển khai: audit ledger, evidence store và SIEM

Không nhất thiết lưu mọi sự kiện ở một cơ sở dữ liệu duy nhất. Nhưng các thành phần phải kết nối bằng ID và hợp đồng truy xuất:

| Thành phần | Trách nhiệm |
|---|---|
| **Producer** | Phát event với nguồn, ngữ nghĩa và khóa xác định. |
| **Collector / ingestion** | Xác thực nguồn, kiểm tra schema, lọc bí mật, đóng timestamp nhận và chuyển vào hàng bền vững. |
| **Audit ledger** | Lưu các sự kiện quan trọng có thứ tự/correlation, hạn chế sửa, hỗ trợ truy vấn lịch sử. |
| **Evidence store** | Lưu hoặc tham chiếu bằng chứng readback, approval, snapshot quyền, ticket và kết quả kiểm tra. |
| **SIEM / detection** | Phân tích cảnh báo, bất thường, tương quan an ninh và sự cố. |
| **Reconciliation engine** | So sánh desired/observed state, phát hiện drift và tạo remediation finding. |
| **Reporting / audit export** | Tạo báo cáo có scope, thời gian, bộ lọc, nguồn dữ liệu và dấu hiệu chưa đủ bằng chứng. |

**SIEM không phải mặc nhiên là nguồn sự thật cho trạng thái account.** Nó rất hữu ích để tìm chuỗi sự kiện và cảnh báo; trạng thái quyền thực tế vẫn phải đến từ API/đường đọc phù hợp của hệ thống đích hoặc nguồn được quy định là có thẩm quyền.

### Mẫu cấu hình audit control

~~~yaml
# Cấu hình minh họa, không phải schema của một sản phẩm IAM cụ thể.
auditProgram:
  id: iam-lifecycle-audit
  ownerTeam: IdentityGovernance
  scope:
    identities: [EMPLOYEE, CONTRACTOR, SERVICE, WORKLOAD]
    targets:
      - idp-corp
      - finance-saas
      - cloud-production
    mustRecord:
      - LIFECYCLE_EVENT
      - POLICY_DECISION
      - APPROVAL_DECISION
      - PROVISIONING_ACTION
      - TARGET_READBACK
      - PRIVILEGED_ACCESS
      - POLICY_CONFIGURATION_CHANGE
  identityKeys:
    - sourceSystem
    - sourceRecordId
    - identityId
    - targetSystemId
    - tenantId
    - nativeAccountId
  correlation:
    requireCorrelationId: true
    requireActionIdForSideEffects: true
    requireSchemaVersion: true
  evidence:
    requireTargetReadbackForLeaver: true
    requireTargetReadbackForPrivilegedRevoke: true
    classifyMissingEvidenceAs: INCOMPLETE
  security:
    redactSecrets: true
    separateApplicationAdminFromAuditAdmin: true
    auditAccessToEvidence: true
  exceptionHandling:
    missingRequiredEvent: ALERT_AND_RECONCILE
    targetReadbackFailure: RETRY_AND_ESCALATE
  review:
    owner: IdentityGovernance
    cadence: P90D
~~~

Ví dụ chỉ mô tả lựa chọn thiết kế. Thời hạn giữ log, độ trễ chấp nhận và danh sách sự kiện bắt buộc phải được xác định thêm dựa trên hệ thống và nghĩa vụ thực tế; không suy ra chúng chỉ từ tên các key trong YAML.

## 16. Audit cho hành vi quản trị và thay đổi chính sách

Một chương trình IAM có thể vận hành đúng cho nhân viên nhưng vẫn rủi ro nếu người có quyền quản trị lặng lẽ sửa policy để tự cấp đặc quyền. Audit cần bao phủ **thay đổi chính các thành phần quản trị IAM**:

- Thay đổi role catalog, business role → technical entitlement mapping;
- Thay đổi RBAC/ABAC policy, SoD matrix hoặc điều kiện eligibility;
- Sửa nguồn identity/owner, connector mapping, thuộc tính có thẩm quyền;
- Thay approval workflow, người duyệt, delegation, expiry và ngoại lệ;
- Cấp quyền quản trị IdP, IGA, PAM hoặc kho audit;
- Thay retention, pipeline, bộ lọc log, cơ chế cảnh báo hoặc cài đặt bảo vệ dữ liệu;
- Thao tác nhập dữ liệu hoặc sửa account/entitlement thủ công ngoài workflow.

Nên có **before/after reference**, policy version, người thay đổi, người duyệt nếu cần, thời điểm triển khai và kết quả kiểm thử/rollout. Nếu chính sách thay đổi khiến nhiều người được mở rộng quyền, audit phải hỗ trợ xác định **nhóm danh tính bị tác động** và việc cập nhật entitlement tại các đích.

### SoD cho quản trị audit

Người cấu hình IAM hoặc quản lý cloud production không nên mặc nhiên có quyền **xóa bằng chứng về thao tác của chính mình**. Áp dụng phân tách trách nhiệm quản trị log, lưu trữ, truy vấn và chính sách xóa theo nhu cầu tổ chức. Với tình huống khẩn cấp, bất kỳ đường nâng quyền nào đối với kho audit cũng phải có cơ chế phát hiện và hậu kiểm độc lập.

## 17. Dùng audit để điều tra một quyền còn tồn dư

### Tình huống: Leaver đã có hiệu lực nhưng SaaS vẫn truy cập được

Giả sử:

| Thời điểm | Bằng chứng |
|---|---|
| 17:50 | HRIS phát `EMPLOYMENT_TERMINATION_SCHEDULED` với `effectiveAt=18:00`. |
| 18:00 | Trạng thái quan hệ trở thành `TERMINATED` theo nguồn có thẩm quyền. |
| 18:01 | IAM tính desired state: không còn quyền trên IdP, SaaS, cloud. |
| 18:02 | IAM gửi lệnh disable tới SaaS, `actionId=act-88`. |
| 18:03 | Connector timeout, `attempt-1` chưa rõ kết quả. |
| 18:05 | Readback thấy tài khoản SaaS vẫn `ACTIVE`. |
| 18:07 | Retry được gửi, `attempt-2`. |
| 18:10 | SaaS báo chấp nhận; readback tiếp tục. |
| 18:12 | SaaS account `DISABLED` được xác nhận. |

Một nhà điều tra cần lần theo:

1. Quan hệ nhân sự nào thực sự kết thúc, nguồn và phiên bản?
2. IAM nhận event khi nào, quyết định gì, policy version nào?
3. Tài khoản SaaS nào được target, có liên kết đúng `nativeAccountId` không?
4. Vì sao lần đầu không xác nhận, retry nào đã diễn ra, có idempotency không?
5. Giữa 18:00 và 18:12 có bằng chứng truy cập thành công nào của tài khoản ở SaaS không?
6. Tại 18:12 trạng thái nào được đọc lại và có thêm token/credential độc lập cần thu hồi không?
7. Có vi phạm SLA không, remediation được đóng bởi ai và có vấn đề lặp lại không?

Kết luận phù hợp: **Leaver có quyền truy cập SaaS tồn dư ít nhất cho đến thời điểm readback 18:05 và được xác nhận đã vô hiệu hóa vào 18:12**. Từ hai điểm quan sát không thể biết chính xác mili-giây quyền mất hiệu lực nếu hệ thống đích không cung cấp event chính xác hơn. Báo cáo nên nêu rõ **độ phân giải của bằng chứng** thay vì khẳng định sai rằng quyền chắc chắn bị thu hồi lúc 18:10.

### Tái dựng lịch sử không đồng nghĩa phát lại side effect

Khi xuất log cho điều tra, cần đọc dữ liệu audit **mà không phát lại lệnh provisioning**. Replay event nghiệp vụ để khắc phục thiếu dữ liệu là một thao tác riêng có kiểm soát, phải xử lý idempotency, version và chính sách hiện hành để tránh cấp lại quyền đã bị thu hồi.

## 18. Các chỉ số audit cần theo dõi

Chỉ số audit nên đo **độ bao phủ, độ tin cậy và khả năng giải quyết vấn đề**:

| Chỉ số | Ý nghĩa và cách sử dụng |
|---|---|
| **Audit source coverage** | Tỷ lệ hệ thống/tenant trong account scope đã có đường thu thập và chủ sở hữu log. |
| **Required event completeness** | Tỷ lệ nghiệp vụ bắt buộc có đủ event class và correlation theo định nghĩa; cần nêu cách ước lượng mẫu số. |
| **Evidence confirmation rate** | Tỷ lệ hành động cần xác minh đã có target readback/evidence phù hợp. |
| **Missing/late event rate** | Event thiếu, đến trễ hoặc quá ngưỡng freshness theo nguồn. |
| **Schema rejection rate** | Bản ghi bị từ chối vì thiếu trường, sai version hoặc không đúng authority. |
| **Audit pipeline availability** | Khả năng nhận, ghi, truy vấn dữ liệu theo yêu cầu đã xác định. |
| **Audit delivery latency** | Độ trễ giữa producer và lưu vào kho audit trung tâm. |
| **Clock skew / ordering anomaly** | Sai lệch đồng hồ, version gap hoặc sự kiện trái thứ tự. |
| **Leaver confirmed revocation latency** | Độ trễ từ `effectiveAt` đến khi quyền bắt buộc được xác minh thu hồi ở từng đích. |
| **Unresolved IAM drift** | Quyền thực tế khác desired state, phân loại theo mức rủi ro và tuổi finding. |
| **Privileged/exception audit coverage** | Phiên đặc quyền và ngoại lệ có đủ actor, scope, lý do, thời hạn và kết quả. |
| **Unauthorized audit access alerts** | Truy cập, xuất hoặc sửa cấu hình kho log trái quyền. |

### Ví dụ phân biệt hai loại thời gian

Một Leaver có `effectiveAt=18:00`; IAM nhận lúc `18:01`; gửi lệnh lúc `18:02`; SaaS xác nhận readback disabled lúc `18:12`.

- Độ trễ **tiếp nhận nghiệp vụ**: 1 phút.
- Độ trễ **gửi lệnh** so với mốc hiệu lực: 2 phút.
- Độ trễ **xác nhận thu hồi**: 12 phút.

Nếu dashboard chỉ báo “2 phút”, nó có thể đánh lạc hướng về rủi ro tồn dư truy cập. Cần báo **mốc và ý nghĩa riêng**; không dùng thời điểm gửi lệnh thay cho thời điểm xác nhận thu hồi.

## 19. Kiểm thử audit trước khi đưa vào vận hành

Kiểm thử phải chứng minh cả **đúng event**, **liên kết được chuỗi** và **bằng chứng không bị đánh dấu sai**.

| Ca kiểm thử | Dữ kiện | Kết quả mong đợi |
|---|---|---|
| **1. Joiner hợp lệ** | HRIS xác nhận bắt đầu và IAM cấp role baseline. | Có event nguồn, policy/version, lệnh và readback đúng account. |
| **2. Approval đặc quyền** | Hai approver độc lập duyệt quyền production. | Audit lưu đúng request version, approver, scope, expiry và action thực tế. |
| **3. Approval bị từ chối** | User thiếu eligibility hoặc vi phạm SoD. | Có bản ghi Deny với reason code; không có lệnh cấp quyền ngoài luồng. |
| **4. Mover giữ quyền cũ** | Chuyển Finance → Engineering, SaaS chưa gỡ nhóm. | Audit lưu desired state và drift finding, không tuyên bố đã thu hồi. |
| **5. Leaver connector lỗi** | SCIM timeout và readback còn active. | Hành động ở `FAILED/RETRYING`, có correlation, alert và chủ thể xử lý. |
| **6. Leaver được khắc phục** | Retry thành công và đọc lại account disabled. | `CONFIRMED` chỉ sau bằng chứng, giữ lịch sử các attempt trước. |
| **7. Token/phiên cũ** | IdP khóa user nhưng token tại SaaS còn khả dụng. | Có finding về khoảng trống session/token nếu trong control scope; không kết luận toàn bộ truy cập đã chặn. |
| **8. Quyền local ngoài IdP** | ERP có account độc lập. | Có đường log/đối soát riêng, identity correlation và bằng chứng thu hồi. |
| **9. Hai tenant cùng username** | `alice` tồn tại tại tenant VN và SG. | Bản ghi phân biệt target bằng tenant/native ID, không ghép nhầm. |
| **10. Event trùng** | Producer gửi lại cùng source event ID. | Dedupe logic không làm mất dấu vết retry; không nhân bản hành động ngoài ý muốn. |
| **11. Event sai thứ tự** | Source version 18 đến trước 17. | Audit giữ cả sự kiện và trạng thái xử lý stale, không hồi quy quyền. |
| **12. Dữ liệu nguồn bị thiếu** | `sourceRecordId` không có. | Event bị cách ly/cảnh báo, không tự đoán identity rồi ghi sai audit. |
| **13. Collector ngừng gửi** | Một ứng dụng không phát log như kỳ vọng. | Heartbeat/freshness alert, thống kê coverage không che giấu khoảng trống. |
| **14. Chỉnh sửa bằng chứng** | Người không được phép sửa/xóa một bản ghi cũ. | Thao tác bị chặn hoặc phát hiện integrity violation theo cơ chế đã thiết kế. |
| **15. Log chứa secret** | API gửi lỗi kèm bearer token. | Bộ lọc không lưu secret, có cảnh báo nếu đường thu thập vi phạm. |
| **16. Truy vấn log trái quyền** | Người vận hành không có quyền xuất toàn bộ audit. | Bị từ chối; thao tác truy cập kho audit được ghi nhận. |
| **17. Break-glass** | Account khẩn cấp được sử dụng khi IdP lỗi. | Có cơ chế thu bằng chứng, đồng bộ sau khôi phục và hậu kiểm độc lập. |
| **18. Service owner nghỉ việc** | Robot vẫn chạy; owner cá nhân đã Leaver. | Ghi quyền cá nhân bị thu hồi, ticket chuyển owner workload và credential review. |
| **19. Review Revoke chưa thực thi** | Reviewer chọn Revoke, API vẫn còn entitlement. | `REVIEW_DECIDED` tách với `REMEDIATION_PENDING/FAILED`. |
| **20. Policy thay đổi** | Role mapping bổ sung quyền xuất dữ liệu. | Có version, actor, approval và thông tin đối tượng bị ảnh hưởng. |

**Kiểm thử audit không chỉ là đếm số dòng log.** Cần truy ngược một scenario từ event nguồn đến dữ liệu đích, thử truy vấn bằng correlation ID, kiểm tra dấu thời gian, độ đầy đủ, quyền đọc log và kịch bản lỗi. Không cần chạy các kiểm thử này ở bước soạn nội dung; đây là tiêu chí thiết kế cho giai đoạn triển khai.

## 20. Lộ trình xác định audit trong chương trình IAM

### Bước 1 — Chọn câu hỏi và mức độ đảm bảo

Làm rõ các luồng cần chứng minh: Joiner đúng điều kiện, Mover không giữ role cũ, Leaver thu hồi hoàn toàn trong account scope, đặc quyền có owner/expiry, review/approval có bằng chứng.

**Đầu ra:** danh sách câu hỏi kiểm toán và mức rủi ro, kết luận nào phải có target readback.

### Bước 2 — Lập audit scope matrix

Với từng hệ thống/tenant và loại account, xác định source logs, owner, event class bắt buộc, correlation, độ trễ, retention và phương pháp xác minh.

**Đầu ra:** bản đồ hệ thống có và chưa có log, kế hoạch xử lý vùng thiếu dữ liệu.

### Bước 3 — Thống nhất schema và từ điển sự kiện

Chuẩn hóa `eventType`, `actor`, `subject`, `target`, `correlationId`, `causationId`, `outcome` và time fields; định nghĩa enum/semantics để không nhầm `REQUESTED` với `CONFIRMED`.

**Đầu ra:** event catalog, schema version, hợp đồng giữa producer và collector.

### Bước 4 — Thiết kế nguồn chứng cứ và bảo vệ

Xác định bằng chứng nào từ HRIS/VMS, IdP, SCIM, SaaS, cloud, PAM, SIEM và người thực hiện thao tác thủ công. Quy định tamper-resistance, phân quyền, redaction, encryption, retention và cách phát hiện collector bị mất.

**Đầu ra:** kiến trúc audit ledger/evidence store và tiêu chí dữ liệu được tin cậy.

### Bước 5 — Gắn audit vào luồng JML và access governance

Mọi workflow phải tạo hoặc tham chiếu được chain **event → decision → command → result → observed state → remediation**. Với mỗi hoạt động, chỉ rõ điều kiện kết luận đã hoàn tất và tình huống chưa có chứng cứ.

**Đầu ra:** correlation map, action state model và quy trình escalation.

### Bước 6 — Kiểm tra bằng kịch bản thật

Diễn tập Joiner tương lai, Mover có SoD, Leaver connector lỗi, nhà thầu hết hạn, quyền admin trực tiếp, service account mất owner và break-glass. Kiểm tra cả khả năng dựng lại timeline lẫn quyền truy cập kho log.

**Đầu ra:** báo cáo test, lỗ hổng coverage và kế hoạch khắc phục.

### Bước 7 — Vận hành và rà soát định kỳ

Theo dõi pipeline freshness, quyền tồn dư, cảnh báo an ninh, kết quả readback, schema drift và exceptions. Chủ chương trình định kỳ xác nhận event catalog, retention và các thay đổi hệ thống.

**Đầu ra:** dashboard, runbook điều tra, báo cáo phạm vi và kế hoạch cải tiến.

## 21. Các lỗi thiết kế audit thường gặp

1. **Chỉ bật log IdP rồi tuyên bố IAM đã được kiểm toán đầy đủ.** Bỏ sót quyền SaaS, cloud, account local và credential riêng.
2. **Gọi lệnh được gửi là quyền đã thu hồi.** Không có target readback, đặc biệt nguy hiểm với Leaver.
3. **Không phân biệt actor, subject và approver.** Không biết ai thực hiện, ai được cấp quyền và ai chịu trách nhiệm quyết định.
4. **Không có correlation ID, native account ID và tenant.** Không dựng lại được chuỗi nhiều hệ thống hoặc ghép nhầm account trùng tên.
5. **Log không có policy/role version.** Không thể giải thích vì sao một role được cấp tại thời điểm lịch sử.
6. **Dùng event nhận sau cùng làm trạng thái có thẩm quyền.** Event đến sai thứ tự khiến audit và workflow hồi quy.
7. **Ghi log đầy đủ bí mật, token hoặc PII không cần thiết.** Tăng nguy cơ dữ liệu audit bị lạm dụng.
8. **Admin hệ thống có thể tự xóa audit.** Mất khả năng điều tra thay đổi quyền đặc biệt.
9. **Bỏ qua collector downtime hoặc schema error.** Có kho log nguyên vẹn nhưng thực tế thiếu nhiều event.
10. **Không audit thay đổi chính sách hoặc chính hệ thống audit.** Người có đặc quyền có thể thay đổi cấu hình mà không bị phát hiện.
11. **Xóa/gộp các lần retry thất bại.** Không còn bằng chứng để đo thời gian quyền tồn dư hoặc nguyên nhân tích hợp lỗi.
12. **Đưa toàn bộ truy vấn audit cho mọi nhân viên IT.** Thiếu phân quyền và ghi nhận truy cập dữ liệu nhạy cảm.
13. **Gộp mọi trạng thái thành `SUCCESS`.** Không biết thành công ở bước lệnh, response hay trạng thái đã xác minh.
14. **Không công bố phạm vi và giới hạn chứng cứ.** Báo cáo “mọi truy cập đã bị chặn” trong khi một tenant chưa được onboard vào audit.

## 22. Bài tập thực hành: thiết kế audit trail cho tổ chức đa hệ thống

Một doanh nghiệp sử dụng HRIS, VMS, IdP/SSO, SaaS hỗ trợ SCIM, ERP có tài khoản local, cloud production, PAM và một robot CI/CD. Tháng này xảy ra các sự kiện:

1. Nhân viên A gia nhập, được cấp role cơ sở; đồng thời xin quyền xuất báo cáo tài chính cần data owner phê duyệt.
2. Nhân viên B chuyển Finance sang Engineering nhưng quyền `finance-read` ở SaaS vẫn tồn tại sau một lần đồng bộ.
3. Nhà thầu C hết hợp đồng lúc 18:00, IdP bị vô hiệu hóa lúc 18:01 nhưng ERP local chỉ được xác nhận disabled lúc 18:25.
4. Quản trị viên D dùng quyền PAM/JIT trong một sự cố production; sau đó quyền bị gỡ.
5. Kỹ sư E nghỉ việc, trong khi robot CI/CD do E từng sở hữu vẫn đang chạy.
6. Một thành viên IT cố sửa chính sách audit hoặc xuất dữ liệu log vượt phạm vi cho phép.

**Yêu cầu:**

1. Lập **audit scope matrix** cho từng hệ thống: event cần thu, nguồn có thẩm quyền, owner, phương thức bảo vệ log và evidence readback.
2. Vẽ chuỗi **source event → IAM policy/approval → provisioning → target response → target observation → remediation** cho nhà thầu C.
3. Thiết kế JSON audit record cho yêu cầu `ACCESS_REQUEST_APPROVED` của A; phân biệt requester, beneficiary, approver, system/tenant, policy và request version.
4. Với B, nêu cách liên kết role mapping, grant provenance, sự kiện Mover và log drift để xác định nguyên nhân tồn dư.
5. Với C, chỉ ra độ trễ gửi lệnh và độ trễ xác nhận thu hồi; giải thích vì sao không được kết luận ERP đã bị chặn ngay lúc 18:01.
6. Với D, liệt kê audit evidence của phiên đặc quyền và kiểm soát để ngăn người vận hành xóa dấu vết.
7. Với E, mô tả các sự kiện audit cho Leaver cá nhân, chuyển service owner, luân chuyển credential và quyết định giữ hoặc ngừng workload.
8. Thiết kế kiểm soát khi collector dừng, event trùng, event sai version, thiếu source ID, thay schema hoặc có dấu hiệu log bị sửa.
9. Đề xuất **ít nhất tám ca kiểm thử** và **năm KPI** đánh giá completeness, evidence confirmation, latency và quyền tồn dư.

### Tiêu chí nghiệm thu

Một thiết kế audit IAM đủ rõ để triển khai cần chứng minh:

- **Mọi luồng quan trọng** có event catalog, nguồn, owner và hệ thống/tenant trong scope.
- Actor, subject, target, action, policy version và kết quả có ngữ nghĩa nhất quán.
- Có khóa liên kết event, request/approval, action, retry, readback và remediation.
- **Leaver/Mover** không được tuyên bố hoàn tất khi quyền ở đích còn sai lệch hoặc chưa có bằng chứng.
- Audit cho **đặc quyền, service account, workload, break-glass và quyền cấp trực tiếp** không bị bỏ sót.
- Kho log có kiểm soát **integrity, confidentiality, least privilege, retention và giám sát mất dữ liệu**.
- Có quy trình truy vấn, dựng lại timeline và xuất bằng chứng phục vụ điều tra/đánh giá.
- Chỉ số tách **thời gian nhận event, gửi lệnh và xác nhận trạng thái thực tế**, đồng thời nêu các khoảng trống bao phủ.

**Audit là lớp bằng chứng và trách nhiệm giải trình xuyên suốt chương trình IAM.** Khi thiết kế đúng, nó không chỉ trả lời “ai đã đăng nhập” mà còn chứng minh ai đã quyết định cấp hoặc thu hồi quyền, điều gì được thực thi, kết quả nào đã được xác minh và phần quyền truy cập nào vẫn cần xử lý. Đó là nền tảng để kiểm soát Joiner–Mover–Leaver, điều tra sự cố và giảm quyền truy cập tồn dư một cách có thể kiểm chứng.
