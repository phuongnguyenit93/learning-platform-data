# Xử lý provisioning failure trong IAM: chẩn đoán, phục hồi và đối soát quyền

## 1. Provisioning failure là gì?

**Provisioning** là quá trình biến một quyết định quản lý danh tính và quyền truy cập thành trạng thái thực tế trên hệ thống đích: tạo tài khoản, cập nhật thuộc tính, gán nhóm/vai trò, cấp quyền tài nguyên hoặc kích hoạt một danh tính. Theo nghĩa vận hành rộng hơn, **deprovisioning** là quá trình vô hiệu hóa hoặc thu hồi những quyền không còn hợp lệ. Cả hai đều thuộc quản lý **vòng đời danh tính (identity lifecycle)**.

**Provisioning failure** xảy ra khi một thay đổi hợp lệ từ hệ thống nguồn **không được thực thi đầy đủ, đúng hạn hoặc đúng trạng thái mong muốn** tại một hay nhiều hệ thống đích. Lỗi có thể hiện ra rõ ràng như HTTP 403/429 hoặc âm thầm như connector trả thành công nhưng role tại ứng dụng vẫn thiếu, cấp nhầm quyền, hoặc tài khoản đã nghỉ việc vẫn đăng nhập được.

Trong module **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**, chủ đề này gắn trực tiếp với **Joiner–Mover–Leaver (JML)**: xác minh và tạo tài khoản cho người mới, cập nhật/thu hồi quyền khi đổi vai trò, deprovision và kiểm toán khi chấm dứt quan hệ lao động. Tài liệu kết nối **Identity Provider (IdP), Single Sign-On (SSO), SCIM, RBAC/ABAC, service account và audit**, nhấn mạnh việc giảm **quyền truy cập tồn dư (residual access)**.

Sau bài học, người đọc có thể:

1. Phân biệt lỗi gửi yêu cầu, lỗi xử lý tại đích, lỗi dữ liệu nguồn và sai lệch quyền hiệu lực.
2. Điều tra theo correlation ID, dữ liệu JML, trạng thái connector, log và trạng thái thực tế của ứng dụng.
3. Chọn hướng retry, reconcile, sửa mapping, xử lý thủ công hoặc escalation mà không cấp quyền vượt chính sách.
4. Ưu tiên xử lý deprovisioning failure khi Leaver, revoke token/session và xác minh các đường truy cập độc lập.
5. Xây dựng runbook, bằng chứng kiểm toán và chỉ số theo dõi để đóng lỗi dựa trên **verified state**.

> **Phạm vi:** Đây là runbook tham chiếu, không phải lệnh quản trị của một vendor. Trạng thái HTTP, chiến lược retry, cấu trúc SCIM, giới hạn API và tiêu chí SLA phải được đối chiếu với khả năng thực tế của hệ thống triển khai và chính sách nội bộ.

## 2. Kiến trúc và nơi provisioning có thể thất bại

Một triển khai IAM thường có nhiều nguồn dữ liệu, bộ điều phối và ứng dụng đích. **Provisioning không đồng nhất với SSO**: người dùng có thể xác thực qua IdP thành công nhưng chưa có account hoặc chưa có quyền trong ứng dụng. Ở chiều ngược lại, một ứng dụng có tài khoản cục bộ, phiên hoặc API key độc lập có thể còn truy cập dù IdP đã disable.

~~~mermaid
flowchart LR
    HR[HRIS / Nguồn nhà thầu] --> EVT[Sự kiện JML]
    EVT --> ORCH[Điều phối IAM]
    POLICY[RBAC / ABAC / Approval] --> ORCH
    ORCH --> IDP[IdP / Directory]
    IDP -->|SSO: OIDC / SAML| APP1[Ứng dụng SaaS]
    ORCH -->|SCIM| APP1
    ORCH -->|API / Connector| APP2[Ứng dụng nội bộ]
    ORCH -->|Task có kiểm soát| APP3[Ứng dụng thủ công]
    ORCH -->|PAM / Workload| APP4[Cloud / Service account]
    ORCH --> AUDIT[Audit / SIEM]
    IDP --> AUDIT
    APP1 --> AUDIT
    APP2 --> AUDIT
    APP3 --> AUDIT
    APP4 --> AUDIT
    ORCH <--> RECON[Đối soát actual - desired]
~~~

Các điểm lỗi điển hình:

| Lớp | Ví dụ thất bại | Hậu quả |
|---|---|---|
| **Nguồn chủ quản** | HRIS thiếu mã người, ngày hiệu lực sai, sponsor nhà thầu hết hạn | Không xác định được ai cần có quyền nào |
| **Sự kiện JML** | Webhook bị mất, gửi trùng, đến sai thứ tự, chưa được xử lý | Desired state của điều phối bị cũ |
| **Policy / approval** | Mapping job code không tồn tại, xung đột SoD, thiếu phê duyệt | Workflow phải dừng cấp quyền |
| **IdP / Directory** | Không tạo được user/group, trùng định danh, lỗi quyền connector | SSO và đồng bộ nhóm bị ảnh hưởng |
| **SCIM / API** | Token hết hạn, lỗi schema, 429, 5xx, timeout, pagination lỗi | Đích chưa nhận được thay đổi hoặc không rõ kết quả |
| **Ứng dụng đích** | User tạo nhưng role thiếu; active sai; local grant không bị gỡ | Quyền hiệu lực khác quyền mong muốn |
| **Phiên và token** | Token, session, cache hoặc API key cũ chưa bị thu hồi | Leaver/Mover vẫn có thể dùng quyền cũ |
| **Quan sát / kiểm toán** | Thiếu correlation ID, không đọc lại trạng thái đích, ticket đóng sớm | Lỗi âm thầm và quyền tồn dư kéo dài |

**Điểm phân biệt then chốt:** *request accepted*, *operation applied* và *effective access verified* là ba mốc khác nhau. Một phản hồi 2xx hoặc job status = SUCCESS không thay thế được kiểm tra trạng thái thực tế khi quyền truy cập có rủi ro.

## 3. Mô hình trạng thái cho từng yêu cầu và từng hệ thống đích

Trong môi trường có nhiều ứng dụng, một sự kiện JML có thể thành công ở IdP và ứng dụng A nhưng thất bại ở ứng dụng B. Không nên gán duy nhất trạng thái “xong” cho toàn sự kiện trước khi các đích bắt buộc được xác minh.

| Trạng thái | Ý nghĩa | Hành động vận hành |
|---|---|---|
| `RECEIVED` | Đã nhận sự kiện từ nguồn có thẩm quyền | Xác thực schema, nguồn, phiên bản và subject |
| `VALIDATED` | Danh tính, policy và approval đạt điều kiện | Tính desired state và kế hoạch thay đổi |
| `PENDING` | Chưa gửi hoặc đang chờ điều kiện thời gian/phê duyệt | Theo dõi owner và thời hạn |
| `IN_PROGRESS` | Connector đang thực thi | Theo dõi job ID, timeout và target |
| `APPLIED` | API/connector báo đã áp dụng | Đọc lại actual state tại đích |
| `VERIFIED` | Đích đã đạt desired state theo tiêu chí kiểm chứng | Ghi evidence và đóng target |
| `FAILED_RETRYABLE` | Lỗi tạm thời, có khả năng retry | Retry có giới hạn, có idempotency |
| `BLOCKED` | Dữ liệu/approval/mapping/identity không hợp lệ | Không cấp quyền; chuyển đúng owner |
| `UNKNOWN` | Timeout hoặc mất phản hồi, chưa rõ có thực thi hay chưa | Tra cứu actual state trước khi gửi lại |
| `EXCEPTION_OPEN` | Còn sai lệch cần xử lý khác luồng | Gán owner, hạn chót và biện pháp hạn chế rủi ro |

Một event chỉ được đánh dấu hoàn tất khi **tất cả target bắt buộc đã VERIFIED**, hoặc quy trình của tổ chức có định nghĩa rõ ràng về hoàn tất có ngoại lệ và người phê duyệt. Với Leaver, không được ghi “đã thu hồi toàn bộ” khi còn ứng dụng nhạy cảm đang `UNKNOWN` hoặc `EXCEPTION_OPEN`.

~~~mermaid
stateDiagram-v2
    [*] --> RECEIVED
    RECEIVED --> VALIDATED: Nguồn / danh tính / approval hợp lệ
    RECEIVED --> BLOCKED: Input không hợp lệ
    VALIDATED --> IN_PROGRESS: Tới thời điểm xử lý
    IN_PROGRESS --> APPLIED: Connector báo thành công
    IN_PROGRESS --> UNKNOWN: Timeout / mất phản hồi
    IN_PROGRESS --> FAILED_RETRYABLE: 429 / lỗi tạm thời
    IN_PROGRESS --> BLOCKED: Không hợp lệ / thiếu quyền
    FAILED_RETRYABLE --> IN_PROGRESS: Retry có kiểm soát
    UNKNOWN --> APPLIED: Đối soát đã áp dụng
    UNKNOWN --> IN_PROGRESS: Xác minh chưa áp dụng và retry an toàn
    APPLIED --> VERIFIED: Trạng thái đích đúng
    APPLIED --> EXCEPTION_OPEN: Sai actual vs desired
    BLOCKED --> VALIDATED: Sửa nguồn + approval
    EXCEPTION_OPEN --> VERIFIED: Khắc phục và xác minh
    VERIFIED --> [*]
~~~

**Bất biến vận hành:** mỗi bước phải truy vết được về `event_id`, `subject_id` bất biến, `target_id`, hành động mong muốn và version của sự kiện. Không dùng email đơn thuần làm khóa định danh vì email có thể đổi hoặc được tái sử dụng.

## 4. SOP-PF01 — Tiếp nhận và phân loại sự cố

**Trigger:** connector báo FAILED, job quá hạn, cảnh báo drift actual–desired, người dùng thiếu quyền sau Joiner/Mover, hoặc phát hiện Leaver còn tài khoản/quyền đang hoạt động.

**Owner ban đầu:** IAM Operations. Tùy trường hợp có thể chuyển HR/sponsor, chủ ứng dụng, đội nền tảng, PAM hoặc SOC.

1. Tạo hoặc mở ticket liên quan và gắn `event_id`, `correlation_id`, `subject_id`, `target_system`, thời điểm có múi giờ, event type và trạng thái thực thi.
2. **Xác nhận nguồn có thẩm quyền:** HRIS hoặc nguồn nhà thầu phát sự kiện đúng người, đúng loại và thời điểm hiệu lực chưa? Có thay đổi JML nào mới hơn không?
3. **Phân loại JML:** Joiner (chưa cấp đủ, chậm onboarding), Mover (thêm/thu hồi sai), Leaver (còn quyền nên cần ưu tiên khẩn cấp), hoặc service account/đặc quyền.
4. Xem request được gửi chưa, connector có log gì, đích phản hồi gì, trạng thái là failed, timeout, retrying, partially applied hay successful-but-drift.
5. Đánh giá **mức tác động và rủi ro**: ứng dụng trọng yếu, đặc quyền, PII, quyền admin, số tài khoản bị ảnh hưởng, khả năng tồn dư truy cập.
6. Xác định owner của từng đích và phân công hạn xử lý, cách chặn truy cập tạm thời nếu Leaver hoặc phát hiện quyền ngoài chính sách.
7. Không sửa trực tiếp trạng thái IAM từ log chưa xác minh, không tự mở account bị HR/Security đình chỉ và không tăng quyền connector tùy tiện.

### 4.1. Chẩn đoán qua bốn câu hỏi

| Câu hỏi | Kết quả cần có |
|---|---|
| **Thay đổi nào đáng lẽ xảy ra?** | Desired state từ JML, policy RBAC/ABAC, approval |
| **Thay đổi đã đi tới đâu?** | Queue/job/connector logs và API responses |
| **Thực tế ở đích đang là gì?** | Account, group/role, token/session, local grant và effective access |
| **Sao chưa đúng và có thể hành động an toàn nào?** | Root cause, retry/repair, owner, verification |

## 5. Thu thập dữ liệu và xây dựng evidence chain

Chỉ từ một dòng “SCIM sync failed” không thể biết lỗi có gây thiếu quyền hay quyền tồn dư. Bằng chứng phải nối đầy đủ từ **ý định cấp/thu hồi** tới **trạng thái thực tế**.

### 5.1. Trường cần lấy

| Nhóm dữ liệu | Trường gợi ý |
|---|---|
| Sự kiện | `event_id`, `event_type`, `source_system`, `source_version`, `effective_at` |
| Danh tính | `subject_id`, ID người ở IdP, `externalId` của SCIM, ID user của ứng dụng |
| Phê duyệt | Người yêu cầu, approver, ticket policy, grant/expiry, trường hợp ngoại lệ |
| Connector | `connector_id`, job ID, attempt count, request/correlation ID, endpoint/action, status |
| Thời gian | Request time, response time, next retry, last verified, múi giờ |
| Đích | Account enabled, group membership, direct roles, nested groups, application-local privileges |
| Bảo mật | Session/token revocation state, key ownership, PAM grants, security hold |
| Audit | Evidence references, actor, kết quả kiểm chứng, owner và thời hạn ngoại lệ |

**Quy tắc dữ liệu:** giữ bí mật token API, secret, password, mã MFA và nội dung nhân sự nhạy cảm ngoài ticket. Nếu cần log request/response, dùng dữ liệu đã che và chỉ giữ những trường hỗ trợ điều tra. Correlation ID nên được truyền từ nguồn qua connector tới hệ thống log khi có thể.

### 5.2. Sự kiện JML minh họa

~~~json
{
  "event_id": "iam-jml-example-0042",
  "event_type": "MOVER",
  "subject_id": "person-1042",
  "source_system": "HRIS",
  "source_version": 18,
  "effective_at": "2026-11-24T09:00:00+07:00",
  "attributes": {
    "department": "Finance",
    "job_code": "FIN_READER"
  },
  "approval_ref": "access-request-321",
  "correlation_id": "corr-example-042"
}
~~~

Đây là dữ liệu **giả lập**. Trong triển khai thật, bộ điều phối cần kiểm tra thứ tự phiên bản, source of truth, signature/trust của sự kiện và quyết định quyền trước khi gọi API.

## 6. SOP-PF02 — Phân loại phản hồi từ SCIM/API

SCIM là giao thức chuẩn hóa API cho việc quản lý user/group giữa các hệ thống hỗ trợ; không phải ứng dụng nào cũng triển khai đầy đủ các thao tác hoặc trường theo cùng cách. Với mỗi lỗi, đọc **response body có cấu trúc, mã trạng thái, request ID và khả năng thực tế của vendor**. Bảng sau dùng cách diễn giải HTTP thông dụng; sản phẩm có thể có mã lỗi riêng.

| Tín hiệu | Nguyên nhân cần kiểm tra | Cách xử lý |
|---|---|---|
| **400 Bad Request** | Payload sai schema, thiếu trường bắt buộc, sai kiểu dữ liệu, filter/patch path không hợp lệ | So schema/khả năng đích, sửa mapping và validation; không retry cùng payload vô hạn |
| **401 Unauthorized** | Token connector thiếu/hết hạn, cấu hình chứng thực lỗi | Kiểm tra credential bằng kênh quản trị, rotate qua secret manager, retry sau khi đã sửa |
| **403 Forbidden** | Thiếu scope/role API hoặc chính sách đích chặn | Kiểm tra quyền và approval của connector; chỉ cấp đúng scope cần thiết |
| **404 Not Found** | Không tìm được user/group hoặc resource/endpoint sai | Kiểm tra ID, mapping, endpoint; xác minh thực trạng trước khi create/retry |
| **409 Conflict** | Trùng username, externalId/unique field; ràng buộc duy nhất | Đối chiếu identity bất biến; không tự gộp account theo email |
| **412 Precondition Failed** | ETag/version thay đổi giữa read và write | Đọc lại resource và version, tính diff rồi thử lại có kiểm soát |
| **422 Unprocessable Content** | Dữ liệu hợp cú pháp nhưng không đáp ứng quy tắc ứng dụng, nếu API dùng mã này | Xem validation/rule cụ thể, sửa nguồn hoặc yêu cầu phê duyệt |
| **429 Too Many Requests** | Vượt rate limit của API/tenant | Tôn trọng `Retry-After`, backoff có jitter và kiểm soát hàng đợi |
| **5xx / 502 / 503 / 504** | Lỗi hoặc quá tải dịch vụ phía đích | Retry có giới hạn; đối chiếu kết quả thực trước khi gửi thao tác có nguy cơ trùng |
| **Timeout / connection reset** | Không nhận được phản hồi, không rõ request đã được xử lý chưa | Đặt trạng thái `UNKNOWN`, GET/readback tại đích trước khi retry |
| **2xx nhưng drift** | Vendor chấp nhận request, async processing, cache, mapping sai, grant ngoài luồng | Đọc lại actual state, xem job async và xử lý quyền hiệu lực |
| **Không có request** | Queue kẹt, webhook thất lạc, filter sai, scheduler ngừng | Điều tra đường sự kiện, checkpoint và replay có version/idempotency |

Không phải mọi API/SCIM endpoint đều dùng mã 422 hoặc hỗ trợ ETag/If-Match. **Không suy đoán khả năng từ HTTP status một mình**; kiểm tra tài liệu, phản hồi và các kiểm soát đã khai báo của ứng dụng.

### 6.1. Các trạng thái 2xx cần hiểu chính xác

- **201 Created:** resource có thể đã được tạo, nhưng role hoặc group bổ sung có thể chưa được cấp; đọc lại đầy đủ.
- **200 OK / 204 No Content:** request được ứng dụng xử lý theo ngữ nghĩa endpoint, nhưng chưa chứng minh effective access hoặc cache đã cập nhật.
- **202 Accepted:** nếu endpoint hỗ trợ xử lý bất đồng bộ, cần theo dõi job/trạng thái tới khi hoàn tất; không đóng ticket ở mốc accepted.
- **SCIM PATCH / PUT / POST:** cần kiểm tra đúng user/group và thuộc tính mong muốn. Đặc biệt việc disable account khác với xóa vĩnh viễn dữ liệu; hành vi target tùy nhà cung cấp.

### 6.2. Đọc lại và so khớp định danh

SCIM thường có các trường như `id` do đích cấp và `externalId` do client sử dụng để liên kết với danh tính nguồn. Một request create bị timeout có thể đã tạo user; nếu gửi POST tạo lại ngay có nguy cơ sinh trùng. Hãy tra cứu theo mapping/khóa định danh được quản lý, rồi mới quyết định create, patch hay sửa liên kết.

Không tự nhận hai tài khoản là một chỉ vì tên, địa chỉ email hoặc tên đăng nhập giống nhau. Với conflict, xác minh trước identity proofing và mapping, đặc biệt khi có email tái sử dụng, chuyển công ty, tái tuyển dụng hoặc nhiều tenant.

## 7. SOP-PF03 — Điều tra lỗi dữ liệu, policy và identity mapping

Lỗi 4xx và nhiều lỗi “thành công nhưng sai” bắt nguồn từ dữ liệu nguồn hoặc mapping. Bộ điều phối cần xác định **đúng chủ thể và đúng desired state** trước khi chỉnh quyền ở đích.

1. **Xác thực nguồn:** xem HRIS/nguồn sponsor có cập nhật đúng loại JML, thuộc tính bắt buộc, ngày hiệu lực và mã ID ổn định.
2. **Xác thực schema:** tên trường, kiểu, giá trị hợp lệ, unique constraints, timezone, chuẩn hóa Unicode và quy tắc null/empty.
3. **Xác thực mapping:** department/job code/location/employment type chuyển thành vai trò RBAC/điều kiện ABAC nào; có mapping thiếu, quá rộng hoặc hết hiệu lực không?
4. **Xác thực phê duyệt:** quyền nhạy cảm, quyền đặc quyền, ngoại lệ và SoD đã có approval phù hợp chưa; quyền tạm thời có ngày hết hạn chưa?
5. **Xác thực định danh đích:** IdP object ID, SCIM `externalId`, target user ID, tài khoản local và các đối tượng bị trùng đã được phân biệt đúng chưa?
6. **Chặn xử lý sai:** thiếu/không rõ định danh, không có approval, xung đột SoD hoặc source state không hợp lệ phải đưa về `BLOCKED`. Không “sửa tạm” bằng cách gán role admin hoặc vô hiệu hóa validation.
7. **Sửa tại nguồn sở hữu dữ liệu:** HR sửa thông tin nhân sự; IAM sửa policy/mapping theo change process; application owner sửa cấu hình đích. Sau đó phát lại phiên bản sự kiện hợp lệ.

**Ví dụ:** một Mover đổi từ Support sang Finance nhưng hệ thống HR gửi `job_code = FIN-READ`, trong khi mapping chỉ nhận `FIN_READER`. Connector vẫn hoạt động, song bước tính quyền mới thất bại. Cách xử lý là chuẩn hóa mapping theo owner có thẩm quyền, tái tính quyền, cấp `finance-reader` đã duyệt và thu hồi các grant Support không còn hợp lệ. Không “cho tạm quyền rộng” rồi bỏ quên.

## 8. SOP-PF04 — Xử lý retry và lỗi tích hợp tạm thời

Lỗi mạng, 429 và 5xx là tình huống thường gặp. Retry có ích nếu **trạng thái và thứ tự sự kiện được bảo vệ**; ngược lại có thể gây trùng account, ghi đè quyền mới hoặc bật lại Leaver.

### 8.1. Nguyên tắc

| Quy tắc | Lý do |
|---|---|
| **Idempotency** | Chạy lại cùng event không tạo account hoặc grant trùng |
| **Check-before-retry** | Timeout không xác nhận request thất bại; cần GET actual state |
| **Backoff + jitter** | Giảm bão request khi đích quá tải; với 429 tôn trọng `Retry-After` |
| **Retry budget** | Dừng vòng lặp vô hạn, tạo escalation và DLQ/ticket |
| **Version guard** | Sự kiện Mover cũ không ghi đè sự kiện mới hoặc tái kích hoạt Leaver |
| **Target-level progress** | Không gửi lại toàn bộ workflow nếu một ứng dụng đã VERIFIED |
| **Audit từng attempt** | Phân biệt request, response, trạng thái thực và kết quả sau retry |
| **Least privilege** | Không cấp quyền connector rộng hơn chỉ để loại bỏ lỗi tạm |

### 8.2. Khi nào không retry tự động?

- **400/422 do payload không hợp lệ:** cần sửa schema/mapping hoặc source data.
- **403 do thiếu phê duyệt/scope:** cần xem quyền connector; không thử nhiều lần bằng cùng credential.
- **409 do xung đột định danh:** cần đối chiếu và quyết định merge/link thủ công theo chính sách.
- **Người dùng đã thành Leaver hoặc bị security hold:** retry Joiner/Mover cũ có thể mở lại truy cập; phải chặn bằng version/state.
- **Yêu cầu chưa xác định đích:** không tạo mới dựa chỉ trên email hoặc identifier không duy nhất.

### 8.3. Luồng retry mẫu

~~~text
process_target(event, target):
    validate_event_source_and_version(event)
    assert_authoritative_identity_mapping(event.subject_id, target)

    current = read_actual_state(target, event.subject_id)
    desired = compute_desired_state(event, policy, approvals)
    plan = diff(current, desired)

    if plan.is_empty:
        verify_effective_state(target, desired)
        mark_target_verified()
        return

    if not safe_to_apply(plan, event, latest_lifecycle_state):
        block_and_escalate()
        return

    result = apply_change_idempotently(target, plan)
    if result.is_timeout_or_unknown:
        mark_target_unknown()
        reconcile_before_retry()
    else if result.is_transient_error:
        schedule_bounded_retry_with_backoff()
    else if result.is_validation_or_policy_error:
        block_and_route_to_owner()
    else:
        verify_effective_state(target, desired)
        close_target_or_open_exception()
~~~

Pseudocode chỉ thể hiện luồng quyết định. Triển khai thực tế phải định nghĩa khóa đồng thời theo `subject_id + target`, deadline, timeouts, cơ chế lease, phiên bản event, bất biến lifecycle và hành động cần kiểm chứng.

## 9. SOP-PF05 — Đối soát desired state với actual state

**Reconciliation** là năng lực cốt lõi để phát hiện và xử lý lỗi provisioning âm thầm. Khác với chỉ xem log connector, đối soát hỏi: **ứng dụng hiện đang có đúng tài khoản, nhóm, role và quyền hiệu lực không?**

### 9.1. Tính desired state

Desired state được xây dựng từ các nguồn có thẩm quyền:

- Quan hệ lao động/nhà thầu, trạng thái JML và ngày hiệu lực.
- Vai trò cơ sở từ **RBAC**, điều kiện ngữ cảnh từ **ABAC**.
- Quyền đặc biệt đã được chủ dữ liệu/PAM duyệt, scope và thời hạn.
- Quy tắc phân tách nhiệm vụ (SoD), danh sách hạn chế, security hold.
- Các yêu cầu thu hồi khi Mover/Leaver hoặc quyền tạm hết hạn.

### 9.2. Đọc actual state

Actual state cần gồm ít nhất: account enabled/disabled, SCIM user ID, group membership, role trực tiếp, role kế thừa, local account, quyền tài nguyên ngoài IdP, tình trạng session/token có liên quan và các grant đặc quyền. Ở app không hỗ trợ API, application owner phải cung cấp bằng chứng xác minh theo quy trình.

### 9.3. Phân loại drift

| Drift | Ví dụ | Mức rủi ro và hành động |
|---|---|---|
| **Missing account** | Joiner Active ở IdP nhưng ứng dụng chưa có user | Tạo/link đúng định danh; kiểm tra approval và retry có kiểm soát |
| **Missing entitlement** | User có account nhưng thiếu nhóm được duyệt | Sửa group/role mapping và kiểm chứng truy cập |
| **Excess entitlement** | Mover vẫn là admin ở bộ phận cũ | Ưu tiên thu hồi, đối chiếu session và SoD |
| **Orphan account** | Account app không còn chủ thể/sponsor hợp lệ | Xác minh mapping rồi disable/thu hồi theo quy trình |
| **Stale deprovision** | Leaver disabled ở IdP nhưng SaaS active | Ưu tiên chặn đường truy cập trực tiếp và revoke token |
| **Unexpected reactivation** | Connector cũ đặt active=true sau sự kiện Leaver | Incident về thứ tự sự kiện; chặn và sửa version guard |
| **Data mismatch** | Sai department làm ABAC áp quyền khác | Sửa source mapping/thuộc tính, tái kiểm tra quyền hiệu lực |

Nếu một ứng dụng báo “thành công” nhưng actual khác desired, đích vẫn **chưa VERIFIED**. Việc sửa drift cũng phải có bằng chứng phê duyệt và người chịu trách nhiệm, đặc biệt với quyền đặc quyền.

## 10. SOP-J01 — Provisioning failure khi Joiner

**Mục tiêu:** người mới được xác minh, có danh tính duy nhất và nhận quyền tối thiểu đúng thời điểm.

### 10.1. Dấu hiệu và tác động

- HR đã phát sự kiện Joiner nhưng IdP chưa có user hoặc user chưa active sau thời điểm hiệu lực.
- IdP có user nhưng SCIM chưa tạo account ở SaaS, hoặc user đã tạo mà chưa gán đúng nhóm.
- SSO thành công nhưng ứng dụng trả “user not found” hoặc thiếu quyền.
- Tài khoản được tạo trùng do webhook/retry chạy lại.
- MFA enrollment chưa hoàn tất hoặc app nhận thuộc tính sai làm fail role mapping.

### 10.2. Quy trình xử lý

1. Xác nhận người mới đã được HR/sponsor xác minh, tới ngày bắt đầu và được phép tạo tài khoản. Không kích hoạt sớm do ticket khẩn.
2. Đối chiếu subject ID → IdP ID → target/SCIM `externalId`; kiểm tra đã có account trùng hoặc chờ xử lý.
3. Kiểm tra lỗi tại bước nguồn, IdP, SCIM, policy hay ứng dụng; xem status và error detail của từng target.
4. Với lỗi dữ liệu, sửa thông tin hoặc mapping tại source of truth; với retryable error, chạy lại từng target đúng version.
5. Gán **RBAC role tối thiểu** và các điều kiện **ABAC** hợp lệ; quyền nhạy cảm cần approval, không cấp admin “để user vào được”.
6. Kiểm tra SSO/MFA và actual entitlement tại ứng dụng. Không dùng một lần sign-in IdP thành công để kết luận toàn bộ Joiner hoàn tất.
7. Đóng ticket khi các ứng dụng bắt buộc đã VERIFIED; nếu còn app không trọng yếu thất bại, ghi ngoại lệ có owner và thời hạn theo chính sách.

**Ví dụ:** nhân viên Support được tạo ở IdP, nhưng SaaS ticketing trả 409 vì account có email trùng người cũ. Người vận hành không sửa một account bất kỳ theo email; phải đối chiếu `externalId`/ID bất biến, xác nhận người sở hữu account cũ, áp chính sách tái tuyển dụng hoặc tạo/link phù hợp, rồi kiểm chứng role của người mới.

## 11. SOP-M01 — Provisioning failure khi Mover

**Mục tiêu:** quyền mới được cấp theo phê duyệt và quyền cũ không còn hợp lệ được thu hồi đúng thời điểm.

### 11.1. Nguy cơ thường bị bỏ sót

Nếu workflow chỉ **thêm** role cho phòng ban mới mà thất bại ở bước **gỡ** role cũ, người dùng có thể có đồng thời hai tập quyền. Đây là **quyền tồn dư**, có thể tạo xung đột SoD hoặc truy cập dữ liệu ngoài nhiệm vụ. Vì thế, Mover là sự kiện vừa provisioning vừa deprovisioning.

### 11.2. Các bước xử lý

1. Lấy snapshot quyền hiện tại ở IdP và app, bao gồm quyền trực tiếp, nhóm lồng nhau, quyền đặc biệt và grant đã được phê duyệt.
2. Xác nhận sự kiện Mover **mới nhất**, ngày hiệu lực, role cũ/mới, desired state và phê duyệt quyền đặc biệt.
3. Tính **delta** giữa old/new: tập giữ, tập gỡ, tập thêm; kiểm tra SoD và quyền tạm thời.
4. Kiểm tra các target fail riêng: lỗi gỡ nhóm, lỗi role mapping, claim chưa cập nhật, token/phiên cũ hoặc API timeout.
5. Ưu tiên thu hồi grant cũ gây rủi ro theo chính sách; chỉ cho phép chuyển tiếp hai vai trò nếu có owner phê duyệt, giới hạn thời gian và giám sát.
6. Cấp quyền mới đã duyệt bằng workflow idempotent; cập nhật policy/attribute sai tại nguồn thay vì cấp grant thủ công không kiểm soát.
7. Xác minh role thực tế và phiên/token còn hiệu lực. Nếu app cache entitlement, cần chờ propagation hoặc revoke/refresh session phù hợp.
8. Ghi lại cả **delta cấp** và **delta thu hồi**. Không đóng ticket khi còn role cũ chưa VERIFIED revoked.

### 11.3. Ví dụ thực tế

| Phạm vi | Trước khi chuyển | Mong muốn sau chuyển | Lỗi phát hiện |
|---|---|---|---|
| Nhóm IdP | `support-base` | `finance-base` | Thêm nhóm mới thành công |
| Ticketing | `support-editor` | Không còn quyền Support | Connector gỡ role trả 503 |
| Finance app | Chưa có quyền | `finance-reader` đã duyệt | SCIM cấp thành công |
| Session/token | Phiên cũ có claim Support | Không sử dụng được quyền Support cũ | Session chưa được làm mới |

Trường hợp này **chưa hoàn tất Mover** dù Finance app đã hoạt động. IAM phải sửa lỗi gỡ quyền ở ticketing, xử lý phiên cũ nếu cần và đối chiếu quyền hiệu lực ở cả hai ứng dụng.

## 12. SOP-L01 — Deprovisioning failure khi Leaver

**Mục tiêu:** chặn kịp thời mọi lối truy cập không còn hợp lệ, thu hồi phiên/khóa/quyền và chứng minh trạng thái tại từng ứng dụng liên quan. Đây thường là tình huống có rủi ro cao hơn lỗi Joiner thiếu quyền.

### 12.1. Dấu hiệu nguy hiểm

- HR báo Terminated nhưng IdP, VPN, PAM hoặc ứng dụng vẫn enabled.
- SCIM disable user trả lỗi 401/403/429 hoặc target unreachable.
- IdP bị disable nhưng SaaS vẫn cho local login, phiên cũ hoặc API token.
- Role/grant ngoài SSO vẫn tồn tại: cloud IAM, nhóm ứng dụng, SSH key, repository access.
- Một job Joiner/Mover cũ retry sau Leaver và bất ngờ bật lại account.

### 12.2. Thứ tự ứng phó tham chiếu

1. **Xác thực lệnh Leaver:** đúng subject ID, nguồn có thẩm quyền, thời điểm hiệu lực, tình huống khẩn hay theo lịch.
2. **Ưu tiên chặn lối vào:** disable hoặc block sign-in ở IdP, VPN, PAM và các điểm truy cập tập trung mà tổ chức quản lý. Với Leaver khẩn cấp, không chờ SaaS SCIM hồi phục mới chặn đường khác.
3. **Thu hồi đường truy cập độc lập:** revoke session/refresh token nơi hỗ trợ, API token, personal access token, SSH key, quyền admin và tài khoản local theo inventory. Việc khóa SSO không mặc nhiên kết thúc phiên ứng dụng.
4. **Xử lý target SCIM/API lỗi:** giữ trạng thái `PENDING_REVOKE` hoặc `EXCEPTION_OPEN`, retry có giới hạn. Nếu ứng dụng trọng yếu vẫn truy cập được, kích hoạt đường disable thủ công được phê duyệt với application owner/SOC.
5. **Bảo vệ thứ tự sự kiện:** mọi job cũ phải kiểm tra trạng thái lifecycle mới nhất và không được phép ghi `active=true` sau Terminated.
6. **Đối soát thực tế:** kiểm tra account inactive, role/grant không còn hợp lệ, token/session đã xử lý, tài khoản cục bộ và hệ thống không hỗ trợ SCIM.
7. **Bàn giao dữ liệu theo quy định:** chuyển ownership tài liệu, workflow hoặc dữ liệu qua quy trình ủy quyền; không giữ tài khoản Leaver hoạt động chỉ vì cần bàn giao.
8. **Ghi audit và ngoại lệ:** mỗi app còn fail phải có owner, hạn khắc phục và biện pháp giảm rủi ro; không ghi “Leaver fully offboarded” khi chưa đủ bằng chứng.

### 12.3. Ví dụ SCIM disable dạng PATCH

~~~http
PATCH /scim/v2/Users/target-user-84 HTTP/1.1
Authorization: Bearer [REDACTED]
Content-Type: application/scim+json

{
  "schemas": [
    "urn:ietf:params:scim:api:messages:2.0:PatchOp"
  ],
  "Operations": [
    {
      "op": "replace",
      "path": "active",
      "value": false
    }
  ]
}
~~~

Ví dụ là **minh họa cấu trúc SCIM 2.0**, không phải chỉ dẫn gửi tới một hệ thống thật. Trường `active` thể hiện trạng thái người dùng ở resource SCIM, nhưng khả năng ứng dụng chặn phiên hiện tại, xóa token hoặc xử lý quyền kế thừa **phụ thuộc vendor**. Phải kiểm chứng riêng ở đích.

### 12.4. Không đồng nhất disable, delete và retain

- **Disable/deactivate:** ngừng khả năng truy cập, thường giữ account để lưu lịch sử.
- **Revoke grants/tokens:** gỡ quyền và đường truy cập còn hiệu lực, có thể phải thực hiện riêng với disable.
- **Delete/erase:** xóa resource/dữ liệu theo chính sách giữ lại, pháp lý và quyền riêng tư; không mặc định áp dụng ngay trong Leaver.

Không dùng DELETE bừa bãi như biện pháp sửa 409 hoặc deprovision khi chưa hiểu hậu quả lưu trữ và phụ thuộc của ứng dụng.

## 13. SOP-X01 — Tài khoản dịch vụ và workload identity

Tài khoản phi con người cũng có provisioning lifecycle: tạo identity, cấp role/trust, thiết lập secret/certificate, rotate, đổi owner và thu hồi. Failure có thể khiến job production không chạy hoặc giữ bí mật/quyền quá lâu.

1. Xác định **owner kỹ thuật và owner nghiệp vụ**, mục đích, hệ thống phụ thuộc, môi trường, phạm vi quyền và deadline.
2. Phân biệt tài khoản workload với tài khoản cá nhân của nhân viên; không gắn quyền admin cá nhân để chạy script.
3. Với lỗi tạo hoặc cập nhật, kiểm tra trust relationship, service principal, quyền cloud IAM, vault secret version, tên resource và quota.
4. Nếu phải rotate secret/certificate, cập nhật mọi workload instance theo kế hoạch change, tránh vô tình vô hiệu hóa phiên bản đang chạy trước khi ứng dụng sẵn sàng.
5. Khi owner nghỉ việc, chuyển owner và rà lại các grant/credential; đồng thời thu hồi mọi đường truy cập cá nhân của Leaver. Không xóa service account production chỉ vì người tạo đã nghỉ.
6. Khi workload ngừng hoạt động, kiểm tra không còn dependency rồi disable identity, trust, role, secret, khóa và quyền trong dịch vụ đích; ghi bằng chứng.
7. Ưu tiên **managed identity** hoặc **workload federation/credential ngắn hạn** khi nền tảng hỗ trợ để giảm rủi ro khóa tĩnh.

**Ví dụ:** bộ triển khai CI/CD báo 403 sau khi rotate connector credential. Không nâng scope admin ngay; xác định action cần thực hiện, policy của service principal, secret version và quyền đã được phê duyệt. Sau sửa, kiểm thử hành động tối thiểu trong đúng môi trường và đối chiếu audit.

## 14. Phục hồi an toàn khi nhiều bước chỉ thành công một phần

IAM workflow thường không có giao dịch phân tán ACID giữa IdP, các SaaS và cloud IAM. Vì vậy cần mô hình **partial success** và **compensating action** có xét rủi ro.

### 14.1. Vì sao không luôn rollback?

- Với **Joiner**, tạo account A thành công nhưng B lỗi: có thể giữ account A ở mức quyền đã duyệt, chặn activation theo policy hoặc đưa vào trạng thái chờ; không nhất thiết xóa A ngay.
- Với **Mover**, đã gỡ quyền cũ nhưng chưa cấp quyền mới: có thể gây gián đoạn, song tự cấp lại quyền nhạy cảm cũ có thể vi phạm SoD.
- Với **Leaver**, đã khóa IdP nhưng SCIM app lỗi: **không rollback việc khóa IdP** để làm đồng bộ “đẹp trạng thái”. Tiếp tục chặn các lối vào khác và xử lý app lỗi.

Do đó, hướng xử lý nên là **roll forward tới desired state hợp lệ** hoặc compensating action **được owner phê duyệt**. Không đặt quy tắc hoàn tác tự động mọi thay đổi khi một target thất bại.

### 14.2. Sơ đồ xử lý nhiều target

~~~mermaid
flowchart TD
    A[Sự kiện JML hợp lệ] --> B[Tính desired state và delta]
    B --> C[Gửi lệnh tới từng target]
    C --> D{Target phản hồi}
    D -->|Success| E[Readback actual state]
    D -->|Timeout| F[Unknown: truy vấn trạng thái trước retry]
    D -->|Transient| G[Backoff và retry có giới hạn]
    D -->|Permanent / Policy| H[Blocked, sửa nguồn và approval]
    E --> I{Actual = desired?}
    I -->|Có| J[Target VERIFIED]
    I -->|Không| K[Drift ticket / reconcile]
    F --> E
    G --> C
    H --> K
    K --> B
    J --> L{Tất cả target bắt buộc verified?}
    L -->|Có| M[Đóng event + audit]
    L -->|Chưa| N[Giữ mở, owner + deadline + giám sát]
~~~

Sơ đồ là logic khái niệm. Với Leaver, **không** chờ bước cuối của mọi target mới bắt đầu chặn đường truy cập trọng yếu.

## 15. Cơ chế kỹ thuật giúp ngăn lỗi lặp

### 15.1. Event version và thứ tự

Sự kiện có thể trùng hoặc đến sai thứ tự. Khi xử lý, cần ghi `source_version` hoặc sequence có ngữ nghĩa rõ ràng, kiểm tra latest state và giữ **fence** để một Mover cũ không ghi đè Leaver mới. Không chỉ dựa trên timestamp do client tự khai nếu không có cơ chế xác nhận thứ tự.

### 15.2. Idempotency và unique mapping

Sử dụng `event_id` để chống xử lý trùng và `subject_id`/`externalId` để đối chiếu danh tính. Trước POST create lại khi timeout, GET/search theo khóa được chuẩn hóa; trước PATCH phải đọc resource/version nếu yêu cầu. Tránh retry “tạo user” vô hạn khiến nhiều account trùng hoặc grant chồng.

### 15.3. Queue, dead-letter và backpressure

Khi ứng dụng đích giới hạn API, giới hạn số worker đồng thời cho từng tenant, ưu tiên Leaver nhạy cảm theo chính sách, tôn trọng `Retry-After` và backoff có jitter. Sự kiện vượt retry budget vào **dead-letter queue (DLQ)** có cảnh báo owner và deadline; không để DLQ trở thành nơi lãng quên.

### 15.4. Reconciliation định kỳ và theo sự kiện

Kết hợp event-driven provisioning với scheduled reconciliation, đặc biệt ở hệ thống cho phép admin sửa quyền cục bộ. Chạy đối soát sau những đợt thay đổi role, connector recovery, SCIM outage và thời điểm Leaver. Với app không hỗ trợ API đọc quyền, cần checklist xác nhận thủ công và người chịu trách nhiệm.

### 15.5. Bảo vệ connector credential

Credential của SCIM/API connector có thể là quyền quản trị trên nhiều người dùng. Lưu trong vault, áp quyền tối thiểu, rotation có kiểm soát, giám sát đăng nhập và tránh log secret. Các lỗi 401/403 phải xử lý qua owner và change management; không dùng token cá nhân của một người vận hành làm giải pháp lâu dài.

### 15.6. Rate limit, timeout và circuit breaker

Giới hạn request theo target/tenant, đặt timeout rõ ràng, ngắt tạm các luồng không khẩn cấp khi đích mất ổn định và duy trì hàng đợi phục hồi có thứ tự. Với Leaver, cần đường chặn truy cập thay thế qua owner hoặc IAM/SOC theo chính sách khi target không đáp ứng.

## 16. Mẫu runbook xử lý từng mức ưu tiên

Các mức dưới đây chỉ để minh họa; tổ chức phải tự định nghĩa SLA/SLO theo loại dữ liệu, nền tảng và rủi ro.

| Mức tham khảo | Tình huống | Hướng xử lý |
|---|---|---|
| **P0** | Leaver khẩn cấp còn truy cập tài nguyên trọng yếu; job cũ tái kích hoạt user đã nghỉ | Chặn lối vào, chuyển IAM/SOC, xác minh độc lập và theo dõi mọi target |
| **P1** | Leaver thất bại deprovision ở ứng dụng quan trọng; Mover giữ admin cũ trái SoD | Thu hồi quyền theo đường thay thế có kiểm soát, owner xử lý ngay theo SLA |
| **P2** | Joiner thiếu quyền mặc định ở app làm gián đoạn công việc | Sửa dữ liệu/connector, retry có kiểm chứng, cập nhật ticket |
| **P3** | Drift ít nhạy cảm được phát hiện trong review nhưng chưa gây ảnh hưởng | Lập kế hoạch đối soát, thu hồi và xác nhận theo deadline |

### Checklist thao tác tại thời điểm incident

1. **Phát hiện:** xác định event và target fail, loại JML, số user/ứng dụng ảnh hưởng.
2. **Triage:** đánh giá quyền tồn dư, SoD, đặc quyền và khả năng truy cập thực tế.
3. **Contain:** với Leaver hoặc thừa quyền, chặn các đường vào có thể kiểm soát ngay.
4. **Diagnose:** đối chiếu source/approval, connector log, request ID, API response và actual state.
5. **Repair:** sửa source/mapping/policy/credential, retry idempotent hoặc dùng đường thủ công phê duyệt.
6. **Verify:** đối chiếu account/role/grant và session/token liên quan ở từng target.
7. **Close:** audit đầy đủ; mọi ngoại lệ còn tồn tại có owner, mức rủi ro, deadline và biện pháp kiểm soát.

## 17. Audit, metrics và tiêu chí đóng sự cố

### 17.1. Các chỉ số vận hành

| Metric | Ý nghĩa và cách dùng |
|---|---|
| **Provisioning success rate** | Tỷ lệ target đạt VERIFIED, tách Joiner/Mover/Leaver |
| **Time to verified provisioning** | Độ trễ từ thời điểm có hiệu lực tới lúc tất cả target bắt buộc xác minh |
| **Deprovisioning latency** | Độ trễ từ Leaver có hiệu lực đến khi chặn và xác nhận đường truy cập |
| **Unknown/partial-success count** | Số job mất phản hồi hoặc chỉ thành công một phần cần đối soát |
| **Retry backlog / DLQ age** | Sự kiện đang đợi phục hồi và thời gian chờ |
| **Drift count/age** | Số quyền actual khác desired và tuổi tồn dư, phân nhóm mức nhạy cảm |
| **Orphan account count** | Account không còn liên kết chủ thể/sponsor có thẩm quyền |
| **Unauthorized privilege regrant** | Quyền bị cấp lại không đúng policy do retry/thứ tự event |
| **Manual exception closure** | Số tác vụ thủ công được xác minh tại đích, không chỉ marked done |

Nếu đo SLA, cần phân biệt thời điểm phát sự kiện, `effective_at` và thời điểm target verified; không tính một lần 200 OK là hoàn thành. Đối với sự kiện Leaver có nhiều hệ thống, có thể đo riêng thời gian **chặn lối vào trọng yếu** và thời gian **thu hồi toàn bộ quyền** để thấy rủi ro trong khoảng trống.

### 17.2. Audit record tối thiểu

~~~yaml
ticket_id: IAM-PROVISION-EXAMPLE-402
event_id: iam-jml-example-0042
event_type: MOVER
subject_id: person-1042
source_system: HRIS
source_version: 18
effective_at: "2026-11-24T09:00:00+07:00"
correlation_id: corr-example-042
approval_refs:
  - access-request-321
policy_version: iam-policy-v12
desired_snapshot_ref: desired-state-402
actual_before_ref: actual-before-402
targets:
  - system: finance-app
    operation: grant-finance-reader
    api_result: APPLIED
    verification: VERIFIED
    evidence_ref: app-event-1901
  - system: support-app
    operation: revoke-support-role
    api_result: RETRIED
    verification: VERIFIED
    evidence_ref: app-event-1902
actual_after_ref: actual-after-402
exceptions: []
completed_at: "2026-11-24T09:07:00+07:00"
~~~

Mẫu trên là **giả lập**, không chứa bí mật. Trong vận hành, evidence phải truy được từ sự kiện và phê duyệt đến hành động từng target, phản hồi, readback, quyền hiệu lực và ngoại lệ. Phân quyền xem log, bảo vệ dữ liệu cá nhân và lưu giữ theo quy định của tổ chức.

### 17.3. Tiêu chí nghiệm thu

| Câu hỏi | Joiner | Mover | Leaver |
|---|:---:|:---:|:---:|
| Đã xác định đúng chủ thể, nguồn, phiên bản và thời điểm? | ✓ | ✓ | ✓ |
| Đã áp policy RBAC/ABAC và approval cần thiết? | ✓ | ✓ | Theo phạm vi |
| Account IdP/SCIM ở trạng thái mong muốn? | ✓ | ✓ | ✓ |
| Quyền cấp mới được kiểm chứng tại target? | ✓ | ✓ | Không áp dụng |
| Quyền cũ không hợp lệ đã bị gỡ? | Theo trường hợp | ✓ | ✓ |
| Quyền trực tiếp, role kế thừa và local grant được đối chiếu? | ✓ | ✓ | ✓ |
| Token/session/secret/PAM được xử lý khi cần? | Theo chính sách | Theo rủi ro | ✓ |
| Mọi target bắt buộc có bằng chứng VERIFIED? | ✓ | ✓ | ✓ |
| Ngoại lệ còn mở có owner, hạn chót và biện pháp kiểm soát? | ✓ | ✓ | ✓ |

## 18. Tình huống luyện tập

### Tình huống A — Joiner SCIM POST timeout

HR xác nhận Joiner và IdP tạo tài khoản thành công. Connector gọi POST user tới ứng dụng SaaS rồi timeout. Không rõ SaaS đã tạo user hay chưa.

**Hướng xử lý:** đánh dấu target `UNKNOWN`; truy vấn app bằng mapping/ID bền vững. Nếu đã có user đúng, kiểm tra nhóm/role và chuyển sang VERIFY. Nếu chưa có, retry theo cơ chế idempotent. Nếu trùng email với người khác, dừng để xác minh identity mapping. Không liên tục POST mới gây user trùng.

### Tình huống B — Mover cấp Finance thành công nhưng không gỡ Support

Ứng dụng Finance trả 200, ứng dụng Support trả 503 khi revoke role. Người dùng đã chuyển sang Finance nhưng vẫn xem được dữ liệu Support.

**Hướng xử lý:** coi Mover chưa VERIFIED, ưu tiên giảm quyền tồn dư, retry revoke có giới hạn và dùng đường thu hồi do owner phê duyệt khi cần; kiểm tra phiên/token cũ và actual access. Không rollback quyền Finance đã phê duyệt chỉ để làm sự kiện “đồng nhất”.

### Tình huống C — Leaver SCIM 429 và có local token

Một nhà thầu hết hạn hợp đồng. SCIM trả 429 khi disable SaaS, trong khi app vẫn chấp nhận API token do nhà thầu tạo.

**Hướng xử lý:** block IdP/VPN/PAM và thu hồi token trực tiếp ở SaaS theo đường quản trị được ủy quyền; đánh dấu target chờ thu hồi, retry theo `Retry-After`, kiểm chứng account inactive và token bị từ chối. Báo đầy đủ ngoại lệ tới IAM/SOC; không đánh dấu offboarding xong khi token còn dùng được.

### Tình huống D — Event Mover cũ bật lại Leaver

Nguồn HR phát Mover version 17 rồi Leaver version 18. Connector bị lỗi và retry event 17 sau khi đã xử lý version 18, vô tình đặt user active.

**Hướng xử lý:** chặn truy cập ngay, điều tra log và sửa version guard/ordering để không áp event cũ lên trạng thái Terminated. Đối soát toàn bộ grant đã tái kích hoạt và kiểm tra các tài khoản tương tự trước khi đóng incident.

### Tình huống E — Service account mất quyền sau rotation

Credential connector vừa rotate, job provisioning cloud IAM trả 403. Chủ ứng dụng đề nghị dùng tài khoản admin cá nhân để chạy lại.

**Hướng xử lý:** từ chối cách chạy làm mất truy vết và tăng quyền tùy tiện; kiểm tra service identity, secret version, scope và permission theo chính sách; sửa credential hoặc role tối thiểu được phê duyệt. Sau đó retry và xác minh trạng thái đích bằng service identity có owner.

## 19. Những nguyên tắc vận hành cần ghi nhớ

1. **Provisioning failure là chênh lệch giữa desired state và actual state**, bao gồm cả thiếu quyền lẫn thừa quyền.
2. **Một phản hồi API thành công chưa chứng minh quyền hiệu lực đúng**; phải đọc lại và kiểm chứng ở ứng dụng đích.
3. **JML quyết định thứ tự ưu tiên:** Joiner thường bị thiếu quyền, Mover phải vừa cấp mới vừa thu hồi cũ, Leaver phải chặn truy cập và xử lý quyền tồn dư.
4. **Retry phải idempotent và bảo vệ phiên bản sự kiện:** timeout là trạng thái chưa rõ, sự kiện cũ không được kích hoạt lại người đã nghỉ việc.
5. **Sửa đúng nguồn có thẩm quyền:** HR sửa trạng thái nhân sự, IAM sửa policy/mapping, application owner xử lý tài khoản/quyền đích theo phê duyệt.
6. **Quyền đặc quyền và service account cần owner riêng:** bảo vệ connector secret, PAM, API token và quyền cục bộ ngoài SSO.
7. **Đóng sự cố bằng bằng chứng:** có thể truy vết sự kiện, quyết định, thao tác, kết quả kiểm chứng và mọi ngoại lệ đang mở.

Một quy trình xử lý provisioning failure hiệu quả giúp IAM không chỉ “đẩy” lệnh cấp/thu hồi quyền mà còn **chứng minh hệ thống đã đạt trạng thái truy cập đúng với vòng đời danh tính hiện tại**. Điều đó bảo vệ người dùng hợp lệ khi Joiner/Mover và giảm thời gian quyền tồn dư ở Leaver.
