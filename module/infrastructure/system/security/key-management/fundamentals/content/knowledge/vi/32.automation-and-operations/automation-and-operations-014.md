# Operator approval

Operator approval là bước phê duyệt có kiểm soát trước khi một operator hoặc automation thực hiện thao tác nhạy cảm trong hệ thống quản lý khóa. Approval xác nhận rằng một yêu cầu cụ thể đã được người có thẩm quyền xem xét trong đúng bối cảnh, đúng phạm vi tài nguyên và đúng thời hạn. Đây là một quyết định authorization có bằng chứng, không chỉ là một lời xác nhận trong chat hoặc một thao tác bấm nút.

Trong key management, nhiều thao tác có thể ảnh hưởng trực tiếp tới tính bí mật, tính toàn vẹn và khả năng khôi phục dữ liệu: import hoặc export key material, thay key policy, cấp grant, disable key, schedule deletion, restore key backup, thay KEK, rewrap hàng loạt DEK hoặc kích hoạt break-glass. Một lỗi phê duyệt có thể mở rộng quyền truy cập hoặc làm mất dữ liệu không thể phục hồi.

Bài học trình bày cách thiết kế operator approval cho vận hành tự động và thủ công: phân loại rủi ro, maker-checker, quorum, ràng buộc approval với request bất biến, xác minh danh tính, policy gate, thực thi bằng service identity giới hạn quyền, chống replay, xử lý emergency, audit và kiểm thử.

## 1. Mục tiêu và phạm vi

Sau bài học, người đọc cần có khả năng:

- Giải thích operator approval và phân biệt approval với authentication, authorization, audit và change ticket.
- Xác định thao tác key management nào cần phê duyệt và mức phê duyệt tương ứng.
- Thiết kế maker-checker, separation of duties và quorum theo blast radius.
- Ràng buộc approval với đúng request, key ID/version, operation, parameters và policy revision.
- Xác minh approver identity, role, MFA, quyền hạn và tính độc lập.
- Thiết kế approval expiry, nonce, anti-replay và revocation.
- Xử lý thay đổi context hoặc dependency giữa lúc phê duyệt và lúc execute.
- Tách người phê duyệt khỏi service identity thực hiện operation tại KMS/HSM.
- Tự động hóa low-risk operation bằng policy trong khi giữ human approval cho thao tác quan trọng.
- Xây dựng break-glass flow có giới hạn, giám sát và hậu kiểm.
- Ghi audit evidence không chứa key material hoặc secret.
- Kiểm thử allow/deny, quorum, stale approval, duplicate execution và provider failure.

Phạm vi là quy trình vận hành key management trong tổ chức. Tên API, quyền IAM, cơ chế HSM ceremony và tính năng approval phụ thuộc provider. Các mô hình và code trong bài là ví dụ kiến trúc, cần ánh xạ sang nền tảng đang triển khai.

## 2. Operator approval là gì?

Operator approval là quyết định được ghi nhận bởi một hoặc nhiều người có thẩm quyền, cho phép một operation cụ thể được thực hiện khi các điều kiện policy đã thỏa mãn.

Một approval hợp lệ phải trả lời:

- Ai đã phê duyệt?
- Họ có identity đã xác thực và quyền phê duyệt đúng loại operation không?
- Họ đã phê duyệt chính xác request nào?
- Resource/key ID/version nào bị tác động?
- Operation và parameters nào được phép?
- Approval được tạo lúc nào và hết hạn lúc nào?
- Policy version và dependency snapshot nào được xem xét?
- Có cần nhiều approver độc lập không?
- Approval còn hiệu lực ở thời điểm execute không?
- Kết quả thực thi được đối chiếu với request đã duyệt ra sao?

Approval có thể là một bước trong workflow tự động. Operator xem nội dung request, đánh giá rủi ro, xác thực lại, rồi ký hoặc xác nhận một quyết định có thể kiểm chứng. Orchestrator chỉ chuyển sang trạng thái execute sau khi kiểm tra đủ điều kiện.

## 3. Phân biệt authentication, authorization và approval

| Khái niệm | Câu hỏi | Ví dụ |
|---|---|---|
| Authentication | Bạn là ai? | Operator đăng nhập bằng identity doanh nghiệp và MFA |
| Authorization | Identity này được phép làm gì? | Role KeyCustodian có quyền approve rotation request |
| Approval | Request cụ thể này đã được người có thẩm quyền chấp thuận chưa? | Approver xác nhận rotate KEK version 4 |
| Policy evaluation | Context và điều kiện có cho phép operation không? | Không có legal hold, dependency snapshot còn mới |
| Audit | Điều gì đã xảy ra và ai chịu trách nhiệm? | Ghi request, approver, decision và execution result |
| Change ticket | Công việc được quản lý theo quy trình nào? | Change CHG-1042 liên kết tới approval request |

Đăng nhập thành công không có nghĩa operator được quyền approve. Có role approve cũng không có nghĩa mọi request đều được chấp thuận. Approval hợp lệ phải được kiểm tra cùng resource, action, context và policy.

Một ticket có trạng thái Approved cũng chưa đủ nếu không xác thực được ai phê duyệt, họ đã xem request nào và request có bị thay đổi sau đó không.

## 4. Vì sao cần operator approval trong key management?

Một số operation có tác động lớn hoặc khó đảo ngược:

- Export private key hoặc symmetric key material.
- Import key material từ bên ngoài.
- Thay key policy, IAM binding hoặc HSM partition permission.
- Cấp grant mới cho principal.
- Disable hoặc schedule deletion key production.
- Restore key backup hoặc recovery package.
- Thay KEK dùng chung nhiều tenant.
- Rewrap số lượng lớn DEK hoặc re-encrypt dữ liệu.
- Kích hoạt break-glass access.
- Thay cấu hình audit hoặc evidence retention.
- Thực hiện CA/signing key ceremony.

Approval tạo một điểm kiểm soát độc lập để xem xét mục đích, phạm vi, blast radius và khả năng phục hồi. Nó cũng tạo bằng chứng trách nhiệm giải trình khi cần điều tra.

Không nên yêu cầu con người duyệt từng encrypt/decrypt request thông thường nếu operation đã nằm trong workload policy. Làm vậy sẽ phá availability, tạo fatigue và khiến approver bấm đồng ý theo thói quen. Human approval nên tập trung vào thay đổi đặc quyền, lifecycle operation và thao tác có rủi ro cao.

## 5. Phân loại operation theo rủi ro

Approval policy nên phân loại theo tác động, không chỉ theo tên API.

| Risk tier | Ví dụ | Kiểm soát gợi ý |
|---|---|---|
| Routine | Encrypt/decrypt theo workload policy | Machine authorization, audit và anomaly detection |
| Low | Tạo key cho môi trường dev với scope hẹp | Policy auto-approve, owner và audit |
| Medium | Rotate secret của một service | Owner approval hoặc change workflow |
| High | Thay key policy production, tạo grant rộng, rewrap tenant | Maker-checker, security approval, canary |
| Critical | Export root key, restore master key, schedule deletion KEK dùng chung | Quorum, dual control, ceremony, independent audit |
| Emergency | Contain key/credential compromise | Break-glass giới hạn, ghi nhận lý do và hậu kiểm |

Mức risk phụ thuộc key type, environment, tenant count, dữ liệu phụ thuộc, khả năng rollback và quyền của operation. Cùng một thao tác disable có thể low risk trên key test nhưng critical trên KEK production đang phục vụ nhiều tenant.

## 6. Operation nào cần approval?

Một ma trận policy tham khảo:

| Operation | Approval cần cân nhắc |
|---|---|
| Create key trong sandbox | Auto-approval theo quota và template |
| Create production KEK | Key owner và security approver |
| Import key material | Dual control và custody verification |
| Export key material | Mặc định cấm; ngoại lệ cần quorum và audit đặc biệt |
| Change key policy | Independent approver, before/after diff |
| Create/revoke grant | Approval theo scope và principal risk |
| Rotate key | Owner approval hoặc policy automation có kiểm soát |
| Rewrap hàng loạt DEK | Data owner/security approval, batch limits |
| Disable key | Approval theo impact; emergency path khi compromise |
| Schedule deletion | Quorum và dependency/retention clearance |
| Cancel deletion | Recovery/custodian approval và reason |
| Restore key backup | Quorum, integrity verification và recovery ticket |
| HSM partition change | Operator ceremony và dual control |
| Break-glass | Emergency authorization, TTL và retrospective review |

Không áp dụng ma trận như một danh sách cứng cho mọi provider. Cần kiểm tra semantics operation, khả năng đảo ngược và quyền thực tế mà API thực hiện.

## 7. Maker-checker và separation of duties

Maker-checker tách người tạo request khỏi người kiểm tra và phê duyệt request.

Một flow cơ bản:

1. Requester mô tả mục đích, resource, operation và thời gian thực hiện.
2. Workflow lấy metadata từ nguồn authoritative và tạo request snapshot.
3. Policy engine xác định approver role và quorum.
4. Approver xem nội dung đầy đủ, xác thực lại và approve/reject.
5. Orchestrator kiểm tra approval và policy lần cuối.
6. Executor service thực hiện đúng operation đã duyệt.
7. Kết quả provider được ghi lại và đối soát.

Các vai trò có thể gồm:

| Vai trò | Trách nhiệm |
|---|---|
| Requester | Khởi tạo yêu cầu và cung cấp rationale |
| Key owner | Xác nhận mục đích và phạm vi sử dụng |
| Data owner | Xác nhận tác động tới dữ liệu |
| Security approver | Đánh giá policy và rủi ro bảo mật |
| Key custodian | Kiểm soát custody hoặc ceremony |
| Executor | Thực hiện operation qua KMS/HSM |
| Auditor | Kiểm tra bằng chứng độc lập |

Requester không nên tự approve request của mình. Executor cũng không nên tự sửa request hoặc tự tạo approval để hợp thức hóa operation. Với operation critical, approver và executor nên là identity riêng.

## 8. Dual control và approval quorum

Dual control yêu cầu ít nhất hai cá nhân độc lập tham gia vào một thao tác nhạy cảm. Quorum là số lượng approval hợp lệ cần đạt trước khi operation được phép chạy.

Ví dụ:

- 1-of-2: một trong hai approver được chỉ định có thể chấp thuận; đây là quorum một người, chưa phải dual control.
- 2-of-3: cần hai approver độc lập trong ba custodian.
- 3-of-5: cần ba approver độc lập, có thể dùng cho key cấp nền tảng hoặc recovery ceremony.

Quorum phải dựa trên danh tính độc lập. Hai tài khoản do cùng một người kiểm soát không tạo ra dual control. Một nhóm chat có nhiều thành viên nhưng chỉ một tài khoản approve cũng không tạo quorum.

Cần xác định:

- Tập approver đủ điều kiện.
- Số lượng tối thiểu và role bắt buộc.
- Có yêu cầu approver từ các team khác nhau không.
- Approver có được đồng thời là requester hoặc executor không.
- Cách xử lý approver unavailable.
- Approval expiry và thay đổi membership.
- Cách thu hồi approval trước khi execute.

Với HSM ceremony, quorum có thể được enforcement bởi thiết bị hoặc security domain thông qua operator card/PIN. Approval workflow ở ứng dụng không thay thế enforcement dual control tại HSM.

## 9. Approval phải gắn với request bất biến

Một lỗi nguy hiểm là approver duyệt một request, sau đó requester thay resource hoặc parameters trước khi execute.

Approval cần gắn với canonical request snapshot gồm:

- Request ID duy nhất.
- Provider/account/project.
- Immutable key ID và key version.
- Tenant, environment và purpose.
- Operation cụ thể.
- Parameters có ảnh hưởng tới security.
- Requested state transition.
- Requester identity.
- Rationale và change/incident reference.
- Dependency snapshot/revision.
- Policy version.
- Created time và expiry.
- Idempotency key.

Có thể tạo digest từ biểu diễn canonical của request. Approval record phải tham chiếu digest này. Khi bất kỳ field quan trọng nào thay đổi, digest thay đổi và approval cũ không còn hợp lệ.

Không hash JSON tùy tiện nếu serialization không canonical: thứ tự field, Unicode normalization, number representation và omitted/null field có thể khiến hai nội dung tương đương có digest khác nhau hoặc nội dung khác nhau bị diễn giải sai. Dùng canonical serialization đã định nghĩa và version hóa.

## 10. Approval expiry, nonce và chống replay

Approval phải có thời hạn. Request đã được duyệt hôm qua không tự động được phép chạy hôm nay nếu context, key state hoặc policy đã đổi.

Các kiểm soát:

- expiresAt ngắn phù hợp với risk tier.
- Nonce hoặc approval ID duy nhất.
- Request digest ràng buộc resource/action/parameters.
- Approval chỉ dùng cho một execution hoặc một operation batch được chỉ định.
- Lưu trạng thái consumed/revoked.
- Dùng compare-and-set hoặc transaction để chỉ một executor claim approval.
- Kiểm tra policy và resource state ngay trước execute.
- Chặn approval trùng hoặc approval đã hết hạn.
- Ghi provider operation ID để reconcile khi timeout.

Không cho phép copy một approval token sang request khác. Nếu execution thất bại và cần thử lại, phải xác định retry cùng operation ID hay tạo request mới; không tái sử dụng approval mù quáng.

## 11. Approval state machine

Một workflow có thể mô hình hóa như sau:

~~~~mermaid
stateDiagram-v2
    [*] --> DRAFT
    DRAFT --> SUBMITTED
    SUBMITTED --> PENDING_APPROVAL
    PENDING_APPROVAL --> APPROVED
    PENDING_APPROVAL --> REJECTED
    PENDING_APPROVAL --> EXPIRED
    APPROVED --> READY_TO_EXECUTE
    READY_TO_EXECUTE --> EXECUTING
    READY_TO_EXECUTE --> INVALIDATED
    EXECUTING --> SUCCEEDED
    EXECUTING --> FAILED
    EXECUTING --> UNKNOWN
    UNKNOWN --> RECONCILING
    RECONCILING --> SUCCEEDED
    RECONCILING --> FAILED
    APPROVED --> REVOKED
    READY_TO_EXECUTE --> REVOKED
    REJECTED --> [*]
    EXPIRED --> [*]
    INVALIDATED --> [*]
    SUCCEEDED --> [*]
    FAILED --> [*]
    REVOKED --> [*]
~~~~

| State | Ý nghĩa |
|---|---|
| DRAFT | Request đang được soạn |
| SUBMITTED | Request snapshot đã được đóng băng |
| PENDING_APPROVAL | Chờ đủ approval |
| APPROVED | Đạt quorum |
| READY_TO_EXECUTE | Đã recheck policy và sẵn sàng |
| EXECUTING | Executor đã claim operation |
| SUCCEEDED | Provider xác nhận hoàn tất |
| FAILED | Provider xác nhận operation thất bại |
| UNKNOWN | Không rõ kết quả, thường do timeout |
| RECONCILING | Đang truy vấn provider để xác định trạng thái |
| REJECTED | Bị approver từ chối |
| EXPIRED | Hết hạn trước execute |
| INVALIDATED | Context hoặc request thay đổi |
| REVOKED | Approval bị thu hồi trước execute |

Không chuyển UNKNOWN trực tiếp về EXECUTING bằng cách gửi lại destructive command. Trước hết phải tra provider operation ID và state để tránh thực hiện hai lần.

## 12. Quy trình phê duyệt từ đầu đến cuối

### Bước 1: Tạo request

Requester chọn operation và resource. Hệ thống xác định key ID/version từ registry hoặc provider, không tin alias hoặc ID do caller tự khai báo.

### Bước 2: Enrich và đánh giá

Workflow lấy owner, purpose, environment, dependency, retention, legal hold, provider state, current policy và change ticket.

### Bước 3: Đóng băng request

Canonical request được tạo, digest được tính và request chuyển sang SUBMITTED. Sau thời điểm này, thay đổi field quan trọng phải tạo revision mới và invalidates approval cũ.

### Bước 4: Chọn approver

Policy engine xác định role, team, quorum, separation of duties và risk tier.

### Bước 5: Approver xem xét

Giao diện phải hiển thị resource, operation, impact, before/after, dependency, rollback, expiry và lý do. Không hiển thị raw key material.

### Bước 6: Xác thực và quyết định

Approver xác thực lại bằng MFA phù hợp, sau đó approve/reject. Hệ thống lưu identity, time, decision, rationale và request digest.

### Bước 7: Recheck trước execute

Orchestrator kiểm tra approval còn hạn, chưa bị consume/revoke, quorum vẫn hợp lệ, policy revision và resource state không thay đổi, dependency snapshot còn mới.

### Bước 8: Thực thi

Executor service dùng short-lived workload identity và quyền provider giới hạn cho đúng operation/resource. Operator không cần nhận key material.

### Bước 9: Verify và audit

Đọc trạng thái provider, kiểm tra postcondition, ghi operation ID và kết quả. Nếu provider timeout, chuyển UNKNOWN và reconcile.

## 13. Giao diện approval cần hiển thị gì?

Một màn hình phê duyệt tốt phải giúp operator hiểu tác động trước khi quyết định.

Nội dung tối thiểu:

- Request ID và requester.
- Provider/account/project.
- Key ID/version, tenant và environment.
- Key purpose, algorithm và classification.
- Operation và parameters.
- Current state và requested state.
- Tác động tới decrypt/unwrap/sign/verify.
- Số lượng consumer và dữ liệu phụ thuộc.
- Dependency/retention/legal hold result.
- Rollback plan và recovery dependency.
- Risk tier và policy rule áp dụng.
- Change/incident reference.
- Approval quorum hiện tại/còn thiếu.
- Thời gian request hết hạn.
- Request digest hoặc immutable revision.

Không chỉ hiển thị nút Approve màu xanh mà giấu thông tin chi tiết trong một màn hình khác. Operator phải có khả năng kiểm tra chính xác điều mình đang duyệt.

## 14. Phê duyệt thay đổi key policy và IAM

Key policy hoặc IAM change có thể mở quyền cho principal mới hoặc mở rộng scope của operation hiện tại.

Approval nên hiển thị:

- Principal được thêm/bớt.
- Action được thêm/bớt.
- Resource scope và wildcard.
- Condition, tenant, network và workload restriction.
- Role inheritance và grant.
- Before/after policy diff.
- Effective permission sau khi tính deny/allow precedence.
- Thời hạn của grant hoặc role.
- Owner và change ticket.

Một policy change chỉ thay đổi một dòng nhưng có thể cấp quyền decrypt cho toàn bộ key trong account. Cần đánh giá effective permission, không chỉ review text diff.

## 15. Phê duyệt rotation và rewrap

Rotation và rewrap có thể là routine automation nếu policy đã xác định rõ, nhưng các thay đổi lớn hoặc key có blast radius cao cần approval.

Đối với key rotation:

- Key mới và purpose có đúng không?
- Consumer đã hỗ trợ version mới chưa?
- Overlap window bao lâu?
- Key cũ còn cần decrypt/verify không?
- Có thể rollback không?
- Có incident compromise khiến không được giữ overlap không?

Đối với KEK rewrap:

- Có bao nhiêu wrapped DEK cần chuyển?
- Backup, archive và DR có nằm trong inventory không?
- Rewrap có giữ nguyên DEK/data ciphertext không?
- Có transaction/CAS để cập nhật blob và version metadata không?
- Có thể retry idempotent không?
- Khi batch lỗi giữa chừng, trạng thái nào được ghi nhận?

Approval cần ràng buộc với batch scope, không chỉ key ID. Nếu số lượng DEK hoặc tenant vượt giới hạn đã duyệt, cần request mới.

## 16. Phê duyệt backup, restore và recovery

Restore key backup có thể đưa key material trở lại hệ thống hoặc thay đổi trạng thái trust. Approval cần kiểm tra:

- Backup package có nguồn gốc và integrity hợp lệ không?
- Package thuộc đúng key ID/version/provider/partition không?
- Có anti-rollback protection không?
- Recovery quorum có đủ không?
- Backup có thể chứa key đã compromise hoặc bị revoke không?
- Restore có ghi đè key hiện hành không?
- Có kế hoạch kiểm thử trong môi trường quarantine không?
- Ai chịu trách nhiệm xác nhận restore hoàn tất?

Không cho một operator vừa tạo backup package, tự xác nhận integrity, tự restore và tự đóng audit. Tách custody, approval và execution theo risk.

## 17. HSM ceremony và dual control

Một số thao tác HSM yêu cầu operator card, smart card, PIN, quorum hoặc ceremony tại thiết bị.

Các nguyên tắc:

- Mỗi custodian dùng credential cá nhân.
- Không chia sẻ PIN hoặc operator card.
- Ceremony có mục đích, key ID/partition, participants và witness.
- Ghi nhận thời điểm, thiết bị, firmware, HSM state và operation.
- Không quay/chụp nội dung bí mật hoặc key material.
- Ghi nhận card custody và bàn giao.
- Tách người chuẩn bị command khỏi người xác nhận.
- Có independent audit và reconciliation với HSM event log.

Application approval có thể là lớp điều phối, nhưng HSM phải tiếp tục enforce policy nội bộ. Không bypass HSM quorum chỉ vì workflow đã có hai người bấm approve.

## 18. Operator approval và automation

Automation không loại bỏ approval; nó thực hiện các bước có thể lặp lại và đảm bảo policy được kiểm tra nhất quán.

Một automation controller có thể:

- Tạo request từ lịch rotation hoặc event.
- Enrich key metadata và dependency.
- Đánh giá risk tier.
- Auto-approve các operation low-risk đã được policy cho phép.
- Chờ human approval với operation high-risk.
- Claim request sau khi quorum đạt.
- Gọi KMS/HSM qua workload identity.
- Reconcile provider state.
- Ghi audit và cập nhật inventory.

### Auto-approval chỉ phù hợp khi

- Operation đã được định nghĩa rõ và có scope hẹp.
- Policy owner đã phê duyệt template.
- Resource nằm trong inventory hợp lệ.
- Dependency/retention gate tự động có độ tin cậy phù hợp.
- Có rate limit, batch limit và circuit breaker.
- Có audit và alert độc lập.
- Có thể dừng tự động khi context bất thường.

Không dùng auto-approval cho thao tác export root key, thay CA trust anchor hoặc destroy key dùng chung nếu governance yêu cầu dual control.

## 19. Tách approval khỏi execution identity

Approver không nên cần quyền gọi API destroy hoặc export key trực tiếp. Approval service xác minh quyết định; executor service thực hiện operation bằng workload identity.

~~~~mermaid
sequenceDiagram
    participant R as Requester
    participant W as Workflow
    participant A as Approver
    participant P as Policy engine
    participant E as Executor identity
    participant K as KMS/HSM
    R->>W: Submit immutable request
    W->>P: Evaluate risk and required quorum
    P-->>W: Approval policy
    W->>A: Present exact request
    A->>W: Approve with authenticated identity
    W->>P: Verify quorum and current context
    P-->>W: Permit execution
    W->>E: Dispatch approved operation
    E->>K: Call scoped provider API
    K-->>E: Operation result
    E-->>W: Provider state and operation ID
~~~~

Executor identity cần:

- Chỉ được gọi action đã duyệt.
- Chỉ truy cập key ID/version nằm trong scope.
- Dùng credential ngắn hạn và workload attestation.
- Không có quyền sửa approval record.
- Không có quyền tự tạo request/approval.
- Có rate limit và execution concurrency control.
- Ghi provider operation ID và outcome.

IAM/provider policy phải chặn direct API path từ operator thông thường. Nếu operator vẫn có quyền gọi API destructive trực tiếp, approval workflow có thể bị bypass.

## 20. Java 17: mô hình request và approval

Ví dụ sau biểu diễn request snapshot và approval metadata. Digest phải được tạo từ canonical serialization bên ngoài record; ví dụ không tự triển khai canonical JSON.

~~~~java
import java.time.Instant;
import java.util.Objects;

public record OperationRequest(
        String requestId,
        String provider,
        String keyId,
        String keyVersion,
        String tenantId,
        String operation,
        String parametersDigest,
        String policyVersion,
        String dependencyRevision,
        String requesterId,
        String requestDigest,
        Instant createdAt,
        Instant expiresAt
) {
    public OperationRequest {
        Objects.requireNonNull(requestId);
        Objects.requireNonNull(provider);
        Objects.requireNonNull(keyId);
        Objects.requireNonNull(keyVersion);
        Objects.requireNonNull(tenantId);
        Objects.requireNonNull(operation);
        Objects.requireNonNull(parametersDigest);
        Objects.requireNonNull(policyVersion);
        Objects.requireNonNull(dependencyRevision);
        Objects.requireNonNull(requesterId);
        Objects.requireNonNull(requestDigest);
        Objects.requireNonNull(createdAt);
        Objects.requireNonNull(expiresAt);

        if (!expiresAt.isAfter(createdAt)) {
            throw new IllegalArgumentException("Invalid request expiry");
        }
    }
}
~~~~

Approval metadata có thể biểu diễn như sau:

~~~~java
import java.time.Instant;
import java.util.Objects;

public record OperatorApproval(
        String approvalId,
        String requestId,
        String requestDigest,
        String approverId,
        String approverRole,
        String decision,
        String rationale,
        String authenticationContext,
        Instant approvedAt,
        Instant expiresAt,
        String signatureReference
) {
    public OperatorApproval {
        Objects.requireNonNull(approvalId);
        Objects.requireNonNull(requestId);
        Objects.requireNonNull(requestDigest);
        Objects.requireNonNull(approverId);
        Objects.requireNonNull(approverRole);
        Objects.requireNonNull(decision);
        Objects.requireNonNull(rationale);
        Objects.requireNonNull(authenticationContext);
        Objects.requireNonNull(approvedAt);
        Objects.requireNonNull(expiresAt);
        Objects.requireNonNull(signatureReference);
    }
}
~~~~

signatureReference đại diện cho reference tới chữ ký hoặc bằng chứng approval được xác minh bởi hệ thống identity/workflow. Không tin một chuỗi do client gửi; cần kiểm tra chữ ký, issuer, audience, role, expiry và revocation theo cơ chế thực tế.

## 21. Java 17: kiểm tra quorum trước execute

Ví dụ dưới đây minh họa policy gate cho approval. ApprovalVerifier phải kiểm tra chữ ký và identity bằng nguồn tin cậy; ApprovalStore phải hỗ trợ claim nguyên tử để chống replay.

~~~~java
import java.time.Clock;
import java.time.Instant;
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;

public final class ApprovalGate {
    public interface ApprovalVerifier {
        boolean isAuthenticAndAuthorized(OperatorApproval approval);
    }

    public interface ApprovalStore {
        boolean claimOnce(String requestId, String approvalId);
    }

    private final Clock clock;
    private final ApprovalVerifier verifier;
    private final ApprovalStore store;

    public ApprovalGate(
            Clock clock,
            ApprovalVerifier verifier,
            ApprovalStore store
    ) {
        this.clock = Objects.requireNonNull(clock);
        this.verifier = Objects.requireNonNull(verifier);
        this.store = Objects.requireNonNull(store);
    }

    public void requireQuorum(
            OperationRequest request,
            List<OperatorApproval> approvals,
            Set<String> requiredRoles,
            int quorum
    ) {
        Objects.requireNonNull(request);
        Objects.requireNonNull(approvals);
        Objects.requireNonNull(requiredRoles);

        if (quorum < 1) {
            throw new IllegalArgumentException("Quorum must be positive");
        }

        Instant now = clock.instant();
        if (!now.isBefore(request.expiresAt())) {
            throw new SecurityException("Request has expired");
        }

        Set<String> approvers = new HashSet<>();
        int valid = 0;

        for (OperatorApproval approval : approvals) {
            if (!approval.requestId().equals(request.requestId())
                    || !approval.requestDigest().equals(request.requestDigest())
                    || !"APPROVE".equals(approval.decision())
                    || !requiredRoles.contains(approval.approverRole())
                    || !now.isBefore(approval.expiresAt())
                    || approval.approvedAt().isAfter(now)
                    || approval.approverId().equals(request.requesterId())
                    || !verifier.isAuthenticAndAuthorized(approval)) {
                continue;
            }

            if (approvers.add(approval.approverId())) {
                valid++;
            }
        }

        if (valid < quorum) {
            throw new SecurityException("Approval quorum is not satisfied");
        }
    }

    public boolean claimApproval(String requestId, String approvalId) {
        return store.claimOnce(requestId, approvalId);
    }
}
~~~~

Đây là ví dụ policy gate, chưa phải implementation production. Quorum thực tế phải tính role diversity, organizational independence, approver revocation và approval consumption trong một transaction. claimOnce cần được tích hợp nguyên tử với trạng thái workflow để tránh hai executor cùng dùng một approval. Sau khi quorum đạt, hệ thống vẫn phải recheck provider state, policy version, dependency revision và request expiry ngay trước execute.

## 22. Thay đổi context làm approval mất hiệu lực

Approval phải bị invalidated khi điều kiện quan trọng thay đổi.

Ví dụ:

- Key alias trỏ sang key ID khác.
- Key version hoặc provider account thay đổi.
- Policy revision thay đổi.
- Dependency inventory có thêm consumer.
- Legal hold được kích hoạt.
- Key chuyển sang state khác.
- Request parameters hoặc batch size thay đổi.
- Approver bị thu hồi role.
- Incident severity hoặc risk tier thay đổi.
- Request hết hạn hoặc change window đóng.

Workflow cần xác định rõ field nào là immutable và field nào phải re-evaluate. Không phải mọi metadata thay đổi đều cần xin approval lại, nhưng thay đổi ảnh hưởng đến security decision phải invalidate hoặc chạy policy evaluation mới.

## 23. Emergency approval và break-glass

Break-glass dùng khi quy trình bình thường không đáp ứng được thời gian phản ứng của incident. Đây là ngoại lệ có kiểm soát, không phải một role quản trị vĩnh viễn.

Điều kiện:

- Có incident hoặc emergency reference.
- Lý do và scope được ghi rõ.
- Identity mạnh, MFA và thiết bị phù hợp.
- Quyền ngắn hạn, chỉ đúng provider/key/action.
- Quorum hoặc second-person confirmation khi khả thi.
- Alert độc lập tới security/key custodian.
- Audit được ghi ở nguồn độc lập.
- Hậu kiểm trong thời hạn policy quy định.
- Thu hồi quyền break-glass sau khi xử lý.

Có thể có tình huống cần containment ngay như revoke session hoặc disable credential bị compromise. Policy phải định nghĩa trước action nào được phép tự động/khẩn cấp và action nào vẫn cần dual control. Không để emergency path trở thành cách schedule deletion hoặc export key mà không có review.

## 24. Approval cho thao tác destructive

Các thao tác như schedule deletion, destroy, purge hoặc xóa backup key cần gate chặt chẽ.

Trước khi approve, kiểm tra:

- Key ID/version bất biến.
- Key đã retired hoặc state phù hợp.
- Không còn consumer tạo dữ liệu mới.
- Ciphertext, wrapped DEK, backup, archive và DR dependency đã được rà soát.
- Retention/legal hold đã được kiểm tra.
- Data owner xác nhận.
- Provider deletion window và cancel semantics được hiểu.
- Approval quorum và executor độc lập.
- Dependency snapshot còn mới tại thời điểm execute.

Approval không chứng minh key đã bị destroy. Sau khi execute, phải đọc lại provider state và lưu operation ID/kết quả. Nếu provider trả PENDING_DELETION, không ghi nhận DESTROYED.

## 25. Tích hợp approval với KMS/HSM và IAM

Approval workflow cần phối hợp với enforcement thực tế:

- IAM identity policy giới hạn principal nào có thể gọi provider action.
- Key policy giới hạn resource/action.
- Organization guardrail ngăn bypass.
- Workflow service xác minh approval/quorum.
- Executor identity có short-lived credential và scope hẹp.
- HSM enforce operator role, partition policy và ceremony.
- Audit pipeline nhận cả approval và provider event.

Không nên cấp quyền destructive trực tiếp cho requester hoặc approver. Chỉ executor service được phép gọi API tương ứng sau khi workflow authorize. Tuy nhiên, executor cũng phải kiểm tra request digest, resource và provider state; không nhận một lệnh tùy ý từ queue.

## 26. Audit và evidence của approval

Approval record là evidence quan trọng. Cần ghi:

- Request ID và request digest.
- Operation, resource ID/version và provider.
- Requester identity và rationale.
- Approver identity, role, decision và rationale.
- Authentication context/MFA evidence reference.
- Approval time, expiry và revocation time.
- Policy version và quorum requirement.
- Dependency snapshot/revision.
- Executor identity và provider operation ID.
- Result, error category và postcondition.
- Break-glass reason và retrospective review nếu có.

Không ghi raw key material, secret, password, PIN hoặc token vào approval record. Lưu reference tới identity assertion/signature theo access policy. Bảo vệ audit store khỏi chính role có quyền approve hoặc execute.

## 27. Failure handling và idempotency

Approval workflow có thể lỗi ở nhiều giai đoạn:

| Lỗi | Xử lý |
|---|---|
| Approver unavailable | Chờ, thay approver qua policy hoặc để request expire |
| Quorum thiếu | Không execute |
| Approval service unavailable | Giữ request ở trạng thái an toàn |
| Policy engine timeout | Không suy diễn allow |
| Provider timeout | Chuyển UNKNOWN và reconcile operation ID |
| Duplicate message | Deduplicate bằng request/operation ID |
| Approval bị revoke | Invalidate trước execute |
| Dependency revision đổi | Re-evaluate và yêu cầu approval mới nếu cần |
| Executor credential hết hạn | Lấy credential mới và recheck approval |
| Audit sink lỗi | Dùng durable buffer hoặc dừng operation theo policy |
| Provider partial success | Đối soát từng resource/version, không đánh dấu cả batch thành công |

Mọi operation cần idempotency key hoặc provider operation ID khi nền tảng hỗ trợ. Retry phải phân biệt “request chưa được provider nhận” với “provider đã thực hiện nhưng response bị mất”.

## 28. Giám sát approval abuse và fatigue

Approval system cũng có thể trở thành mục tiêu tấn công.

Tín hiệu cần phát hiện:

- Một approver phê duyệt số lượng request tăng đột biến.
- Approval được thực hiện ngoài giờ hoặc từ thiết bị/vị trí bất thường.
- Requester và approver có quan hệ identity đáng ngờ.
- Một role vừa được cấp rồi dùng ngay để approve.
- Nhiều request gần giống nhau nhằm né batch limit.
- Request digest thay đổi sau khi approver mở màn hình.
- Approval bị tái sử dụng hoặc claim nhiều lần.
- Break-glass kích hoạt thường xuyên.
- Approver liên tục approve trong thời gian rất ngắn.
- Một executor gọi provider action không có workflow reference.

Để giảm fatigue:

- Gom request tương tự thành batch có scope và limit rõ.
- Hiển thị risk và tác động rõ ràng.
- Không yêu cầu human approval cho operation routine đã có policy.
- Đặt giới hạn request theo principal và time window.
- Định kỳ review approver role và access.
- Dùng escalation khi quorum không đạt, không tự hạ quorum.

## 29. Kiểm thử Operator approval

| Test | Điều kiện | Kết quả mong đợi |
|---|---|---|
| Valid single approval | Operation yêu cầu 1 approver | Cho phép khi role/context đúng |
| Missing quorum | Chưa đủ approver | Từ chối execute |
| Self approval | Requester approve request của mình | Từ chối |
| Wrong role | Approver không có role phù hợp | Từ chối |
| Wrong request digest | Approval gắn request khác | Từ chối |
| Wrong key version | Key version thay đổi | Invalidate approval |
| Expired approval | Approval hết hạn | Từ chối |
| Revoked approver | Role bị thu hồi trước execute | Re-evaluate và từ chối |
| Duplicate approver | Một người dùng nhiều account | Không tính quorum độc lập |
| Replay approval | Cùng approval dùng hai lần | Lần claim sau bị từ chối |
| Policy drift | Policy version thay đổi | Re-evaluate hoặc yêu cầu approval mới |
| Dependency drift | Inventory revision thay đổi | Invalidate approval |
| Alias substitution | Alias đổi resource | Từ chối |
| Provider timeout | Không rõ kết quả operation | Reconcile, không retry mù |
| Direct API bypass | Operator gọi provider ngoài workflow | IAM/guardrail từ chối |
| Audit unavailable | Không ghi được evidence bắt buộc | Dừng hoặc dùng durable buffer theo policy |
| Emergency path | Có incident và quyền TTL hợp lệ | Chỉ cho phép action trong scope |
| Break-glass expiry | Quyền hết hạn | Từ chối operation tiếp theo |
| Batch overflow | Số resource vượt limit đã duyệt | Dừng batch và yêu cầu approval mới |
| Approval UI tampering | Nội dung hiển thị khác request digest | Không cho approve/execute |

Nên kiểm thử end-to-end từ request creation, UI review, identity verification, quorum, policy evaluation, executor, provider result tới audit. Unit test riêng cho hàm isApproved không đủ chứng minh workflow an toàn.

## 30. Tình huống thực tế

### Tình huống A: Thay key policy production

Một operator cần cấp quyền decrypt cho workload mới. Workflow tạo request chứa key ID/version, principal, action, tenant scope và policy diff. Security approver xác minh workload identity và scope. Sau approval, executor service áp dụng policy revision. Audit ghi before/after và provider event. Nếu policy diff mở wildcard, policy engine từ chối dù approver đã bấm approve.

### Tình huống B: Rewrap KEK theo batch

Một KEK cũ cần được thay thế. Controller tạo batch gồm danh sách wrapped DEK, tenant và version. Data owner xác nhận phạm vi; security approver duyệt batch digest và giới hạn số lượng. Executor rewrap theo từng item với idempotency key. Nếu dependency revision hoặc batch membership đổi, request bị invalidated. Không được thêm tenant mới vào batch đã duyệt.

### Tình huống C: HSM recovery

HSM cần restore key backup sau sự cố thiết bị. Custodians tham gia ceremony, xác thực bằng credential riêng và kiểm tra backup manifest. Approval gắn với partition, backup ID, key ID/version và recovery plan. HSM enforce quorum; executor ghi operation result. Nếu integrity check không đạt, dừng restore và mở incident.

### Tình huống D: Emergency revoke credential

Một workload credential bị phát hiện lộ. Incident playbook cho phép revoke session/credential theo quyền khẩn cấp có scope hẹp, đồng thời gửi alert cho security approver. Sau containment, team review evidence, phát hành credential mới và thực hiện retrospective approval. Quyền break-glass hết hạn tự động.

## 31. Checklist triển khai

### Governance và policy

- [ ] Có ma trận risk tier và operation cần approval.
- [ ] Routine operation không bị human approval gây nghẽn.
- [ ] Requester, approver và executor được phân tách.
- [ ] Quorum dựa trên identity độc lập.
- [ ] Approver role có owner và được review định kỳ.
- [ ] Break-glass có scope, TTL và hậu kiểm.

### Request và approval

- [ ] Request có immutable ID và canonical digest.
- [ ] Digest ràng buộc provider, key ID/version, action và parameters.
- [ ] Approval có identity, role, decision, rationale và expiry.
- [ ] Approval không thể replay hoặc dùng cho request khác.
- [ ] Thay đổi policy/dependency/context làm re-evaluate.
- [ ] UI hiển thị đầy đủ impact và rollback.

### Execution và audit

- [ ] Executor dùng workload identity ngắn hạn.
- [ ] IAM/provider guardrail chặn direct API bypass.
- [ ] Operation có idempotency và reconciliation.
- [ ] Provider state được xác minh sau execute.
- [ ] Audit ghi request digest, approver, executor và provider operation ID.
- [ ] Không log key material, secret hoặc token.
- [ ] Có negative test cho self-approval, stale approval và quorum thiếu.
- [ ] Có alert cho approval abuse và break-glass bất thường.

## 32. Câu hỏi tự kiểm tra

**1. Operator approval là gì?**

Quyết định có bằng chứng của người có thẩm quyền cho phép một operation cụ thể được thực hiện khi policy và context hợp lệ.

**2. Approval khác authentication thế nào?**

Authentication xác định danh tính; approval là quyết định chấp thuận một request cụ thể.

**3. Có role approver có nghĩa mọi request đều được phép không?**

Không. Vẫn phải kiểm tra resource, action, context, policy và request digest.

**4. Vì sao cần maker-checker?**

Để người tạo request không tự phê duyệt hành động của mình.

**5. Quorum là gì?**

Số lượng approval hợp lệ tối thiểu từ tập approver được phép.

**6. Hai account của cùng một người có tạo dual control không?**

Không. Identity và quyền kiểm soát phải độc lập thực sự.

**7. Approval cần gắn với những dữ liệu nào?**

Request ID/digest, provider, key ID/version, operation, parameters, policy và dependency revision.

**8. Vì sao approval cần expiry?**

Để ngăn quyết định cũ được sử dụng khi context hoặc trạng thái đã thay đổi.

**9. Nonce và claim-once giúp gì?**

Ngăn approval bị replay hoặc nhiều executor cùng sử dụng.

**10. Nếu key alias đổi sau approval thì sao?**

Resolve lại immutable key ID/version; nếu khác target đã duyệt thì invalidate approval.

**11. Ai nên gọi API destructive tại KMS?**

Executor service có workload identity và quyền provider giới hạn, sau khi workflow xác minh approval.

**12. Operator có nên giữ quyền destroy trực tiếp không?**

Thông thường không; direct permission có thể bypass approval workflow.

**13. Auto-approval phù hợp với loại operation nào?**

Operation low-risk, scope hẹp, có policy rõ, rate limit, audit và điều kiện tự động đáng tin cậy.

**14. HSM dual control có thể được thay bằng hai nút approve trên web không?**

Không. HSM phải enforce operator role/quorum theo semantics của thiết bị.

**15. Approval có thay thế dependency check không?**

Không. Dependency và retention phải được kiểm tra trước và ngay trước execute.

**16. Nếu provider timeout thì có retry ngay không?**

Không. Cần reconcile provider operation ID và state trước khi retry.

**17. Break-glass có phải quyền vĩnh viễn không?**

Không. Quyền phải ngắn hạn, giới hạn scope và được hậu kiểm.

**18. Có nên để SIEM tự approve destroy khi alert critical không?**

Không nếu chưa có policy và authorization được thiết kế trước; alert không tự thay thế approval.

**19. Approval record có nên lưu secret value không?**

Không. Chỉ lưu metadata và reference tới evidence/identity assertion.

**20. Operator approval workflow được coi là an toàn khi nào?**

Khi approval gắn đúng request bất biến, identity/quorum hợp lệ, context được recheck, executor bị giới hạn, provider result được xác minh và audit đầy đủ.

## 33. Tài liệu tham khảo

- NIST SP 800-53 Rev. 5 — Security and Privacy Controls: separation of duties, least privilege, access enforcement, dual authorization và audit.
- NIST SP 800-57 Part 1 Rev. 5 — Recommendation for Key Management: key lifecycle, protection và operational controls.
- NIST SP 800-61 Rev. 3 — Incident Response Recommendations and Considerations for Cybersecurity Risk Management.
- NIST SP 800-63B-4 — Digital Identity Guidelines: Authentication and Authenticator Management.
- NIST SP 800-92 — Guide to Computer Security Log Management.
- RFC 8785 — JSON Canonicalization Scheme (JCS), khi hệ thống dùng JSON canonicalization và đáp ứng đúng profile.
- Tài liệu IAM, approval workflow, key policy và audit logging của KMS/HSM đang triển khai.
- Quy trình nội bộ về change management, separation of duties, emergency access và HSM ceremony.

