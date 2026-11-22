# Phân quyền thao tác retry và resend trong Spring Framework Mail

Trong hệ thống gửi email production sử dụng Spring Framework Mail, sự cố gửi thư thường dẫn tới yêu cầu: “Cho tôi bấm gửi lại email này”. Một nút **Retry** tưởng đơn giản nhưng có thể làm phát sinh những hành động nhạy cảm: gửi trùng hóa đơn, gửi lại mã xác thực đã hết hạn, chuyển tài liệu sang recipient không được phép, bỏ qua consent của người nhận hoặc gửi quá giới hạn của nhà cung cấp SMTP.

**Phân quyền retry và resend không chỉ là ẩn hoặc hiện nút trên giao diện.** Đây là chính sách ở server-side command boundary, quyết định **ai được yêu cầu**, **hành động áp dụng cho notification nào**, **trạng thái/failure class có cho phép không**, **người nhận và nội dung có còn hợp lệ không**, **khi nào cần approval**, và **kết quả phải được audit/giới hạn/khôi phục ra sao**.

Bài học giới thiệu một mẫu thiết kế production cho Spring Framework Mail kết hợp Spring Security, RBAC/ABAC, transactional outbox, idempotency, optimistic concurrency, cooldown, approval hai người, audit trail và SMTP worker có service identity riêng. Các ví dụ Java/SQL/HTTP mang tính minh họa; domain classes và policies do ứng dụng tự triển khai, không phải API có sẵn của `JavaMailSender`.

## 1. Vì sao thao tác thủ công này cần bảo vệ?

Một email có thể chứa:

- Hóa đơn và thông tin giao dịch.
- OTP, reset-password link, magic login link.
- Thông báo pháp lý hoặc dữ liệu cá nhân.
- File PDF, CSV hoặc tài liệu có quyền truy cập.
- Nội dung marketing bị chi phối bởi consent/frequency caps.
- Thông tin vận hành chỉ cho một nhóm nhân viên được phép đọc.

Thao tác gửi lại sai có thể:

1. Làm lộ dữ liệu tenant A sang email của tenant B.
2. Gửi trùng khiến khách tưởng đã bị tính phí hai lần.
3. Gửi token đã hết hạn hoặc chứa security code không còn hợp lệ.
4. Bỏ qua suppression sau hard bounce hoặc complaint.
5. Tạo spam vì một operator bấm nhiều lần.
6. Gửi lại một notification đã SMTP accepted nhưng đang chờ delivery.
7. Ghi sai lịch sử vận hành vì không biết ai yêu cầu resend.
8. Bỏ qua giới hạn SMTP quota/cooldown.
9. Cho phép tài khoản support truy xuất raw body hay attachment không cần thiết.
10. Tạo retry storm sau một outage khi nhiều người cùng thao tác.

Vì vậy, **đường điều khiển vận hành** phải tách khỏi **đường gửi SMTP**.

## 2. Automatic retry, manual retry và resend khác nhau

| Hành động | Chủ thể khởi tạo | Cách thay đổi notification | Mục đích |
| --- | --- | --- | --- |
| Automatic retry | Worker/retry policy | Giữ `notificationId`, tạo `attemptId` mới | Khắc phục lỗi tạm thời |
| Manual retry | Operator có quyền | Giữ `notificationId`, lên lịch attempt mới | Thực thi lại ý định chưa hoàn tất |
| Resend | Người có quyền nghiệp vụ | **Tạo notification mới**, liên kết original | Cố ý gửi thêm một bản |
| Replay/redrive | Công cụ vận hành event/queue | Phụ thuộc business handler | Chạy lại một sự kiện/workflow |

Không gọi mọi thao tác là “retry”. Nếu original đã `DELIVERED`, việc gửi một bản nữa là **resend**, không phải retry một lần gửi thất bại.

### Sự khác biệt về định danh

```text
Manual retry:
  notificationId = N-1001
     attempt A1 -> transient error
     attempt A2 -> transient error
     attempt A3 -> manual retry -> SMTP accepted

Resend:
  original notificationId = N-1001
  new notificationId      = N-2002
  resendOf                = N-1001
  attempt B1              -> SMTP accepted
```

`notificationId` ổn định qua retry; `attemptId` mới cho từng SMTP submission. Resend tạo một ý định gửi mới, có audit liên kết tới original.

## 3. Trạng thái notification quyết định có thể làm gì

Một state machine minh họa:

```text
READY
  |
  v
PROCESSING
  |
  +--> SMTP accepted --------> SUBMITTED
  |                                 |
  |                                 +--> DELIVERED (provider event)
  |
  +--> Temporary failure ----> RETRY_WAIT
  |                                 |
  |                                 +--> PROCESSING
  |
  +--> Permanent failure ----> FAILED_PERMANENT
  |
  +--> Retry budget reached -> FAILED_EXHAUSTED
  |
  +--> Unknown outcome -----> AMBIGUOUS

Các trạng thái khác:
  CANCELLED / EXPIRED / SUPPRESSED / BOUNCED / COMPLAINED
```

Đây là mô hình ứng dụng, không phải enum mặc định của Spring Mail.

Cần phân biệt:

- **SUBMITTED**: SMTP transport/relay xác nhận submission. Không chứng minh Inbox delivery.
- **DELIVERED**: có downstream event phù hợp do provider báo.
- **BOUNCED**: email không giao được theo thông tin provider, có thể hard hoặc soft.
- **AMBIGUOUS**: không chắc server đã nhận hay chưa, ví dụ read timeout sau SMTP DATA.
- **SUPPRESSED**: recipient không được phép nhận theo policy.
- **EXPIRED**: nội dung hoặc business action đã quá hạn.
- **FAILED_EXHAUSTED**: retry budget đã hết; chỉ có policy hẹp mới cho can thiệp.

Không quyết định nút retry dựa duy nhất vào một cột `sent=false`.

## 4. Ba lớp kiểm soát để cấp quyền

Một lệnh cần vượt qua ít nhất ba lớp:

1. **Authentication**: actor là ai, đã xác thực như thế nào?
2. **Authorization**: actor có quyền trên **action và resource** này không?
3. **Business policy**: notification, recipient, state, content, consent, expiry và quota có cho phép action hiện tại không?

```text
Authenticated actor
      |
      v
RBAC authority + tenant/resource scope
      |
      v
State/failure class + consent/expiry
      |
      v
Cooldown/rate budget + approval
      |
      v
Atomic command + durable audit
      |
      v
Worker service account + SMTP
```

Có role `MAIL_OPERATOR` không tự động có quyền gửi mọi email trong hệ thống.

## 5. Thiết kế permissions theo hành động

Các authority có thể được định nghĩa:

| Permission | Ý nghĩa |
| --- | --- |
| `mail:read_metadata` | Xem metadata đã lọc |
| `mail:read_content` | Xem body/attachment theo phạm vi đặc biệt |
| `mail:retry_request` | Yêu cầu retry thủ công |
| `mail:resend_request` | Yêu cầu resend |
| `mail:resend_approve` | Phê duyệt resend nhạy cảm |
| `mail:retry_override` | Yêu cầu override retry budget hẹp |
| `mail:cancel` | Hủy job chưa gửi |
| `mail:audit_read` | Đọc audit history |
| `mail:policy_manage` | Thay đổi policy cấu hình |
| `mail:worker_dispatch` | Quyền nội bộ của sender worker |

Đây là tên do ứng dụng lựa chọn, không phải authority mà Spring Security tự tạo.

Nên tách quyền **đọc nội dung** và **gửi lại**. Một operator có thể cần retry bằng notification ID nhưng không cần đọc OTP, invoice PDF hoặc nội dung riêng tư.

## 6. Ma trận role gợi ý

| Vai trò | Metadata | Manual retry | Resend | Approve | Policy |
| --- | --- | --- | --- | --- | --- |
| Support viewer | Trong scope | Không | Không | Không | Không |
| Support agent | Ticket được giao | Theo policy hẹp | Transactional được phép | Không | Không |
| Mail operator | Tenant được giao | Có với failure phù hợp | Có điều kiện | Không tự approve | Không |
| Mail supervisor | Tenant được giao | Có | Có | Có thể duyệt người khác | Hạn chế |
| Platform admin | Theo delegated scope | Có điều kiện | Có điều kiện | Theo quy trình | Giới hạn |
| Retry worker | Jobs đã lease | Automatic only | Không tự tạo resend | Không | Không |

Đây là ví dụ về **least privilege**. Không nên dùng một role `ROLE_ADMIN` như chìa khóa bỏ qua consent, expiry, tenant isolation hoặc owner checks.

## 7. ABAC: quyền phụ thuộc vào notification cụ thể

Một operator có `mail:resend_request` nhưng đối tượng có:

```text
tenantId              tenant-42
category              ORDER_CONFIRMATION
status                DELIVERED
containsSensitiveDoc  true
recipientSuppressed   false
expiresAt             none
customerTicketId      TICKET-8123
```

Quyết định nên xem thêm:

- Actor có thuộc tenant 42 hoặc có delegated access không?
- Ticket đang được phân công cho actor hay không?
- Content chứa tài liệu nhạy cảm cần approval không?
- Recipient có opt-out, bounce, complaint hoặc suppression không?
- Email còn phù hợp với business state mới nhất không?
- Đã resend bao nhiêu lần trong cooldown window?
- SMTP provider có đang bị circuit breaker/cooldown không?

Với ABAC, **hành động được cấp** không đồng nghĩa **mọi resource đều hợp lệ**.

## 8. Multi-tenant và phòng chống BOLA/IDOR

Endpoint như:

```text
POST /api/v1/mail-notifications/{id}/retry
```

phải lookup resource trong tenant scope đã xác thực:

```sql
SELECT id, tenant_id, status, version, category
FROM mail_notification
WHERE id = :notification_id
  AND tenant_id = :authorized_tenant_id;
```

Không tin `tenantId` trong JSON request là căn cứ cấp quyền. Tenant phải đến từ authenticated principal, membership/delegated scope đã kiểm tra hoặc context server-side đáng tin.

UUID khó đoán **không phải authorization boundary**. Khi đối tượng ở tenant khác, API có thể trả 404 nếu policy yêu cầu không tiết lộ sự tồn tại thay vì để người gọi thử IDs.

Nếu operator quản trị nhiều tenants, danh sách scope phải được kiểm tra tại mỗi command.

## 9. Manual retry chỉ cho failure phù hợp

| Failure class | Ví dụ | Hướng xử lý |
| --- | --- | --- |
| `TRANSIENT_NETWORK` | Connect timeout/trục trặc mạng trước submit | Retry sau khi kiểm tra |
| `SMTP_TEMPORARY` | 421, 451, provider throttling | Retry theo backoff/cooldown |
| `CONFIGURATION` | Sai credential hoặc TLS config | Chỉ thử lại sau khi sửa nguyên nhân |
| `PERMANENT_RECIPIENT` | Địa chỉ không hợp lệ | Không retry nguyên email |
| `CONTENT_POLICY` | MIME quá lớn, attachment không cho phép | Sửa nội dung/workflow trước |
| `EXPIRED` | OTP/token/deadline hết hạn | Không retry payload cũ |
| `SUPPRESSED` | Unsubscribe hoặc complaint | Không bypass |
| `AMBIGUOUS` | Timeout sau SMTP DATA | Reconcile, tránh duplicate |
| `SUBMITTED/DELIVERED` | SMTP accepted hoặc provider delivered | Không retry; xem xét resend riêng |
| `UNKNOWN` | Chưa đủ bằng chứng | Điều tra |

Một nút **Retry All Failed** không phân biệt failure class có thể gây tái gửi vô ích hoặc spam.

## 10. Manual retry trên cùng notification

Quy trình:

1. Xác thực operator.
2. Kiểm tra authority và tenant/resource.
3. Xem status, last failure class, retry policy.
4. Kiểm tra expiry, suppression, consent, cooldown.
5. Kiểm tra attempt count và required approval.
6. Ghi command/audit bền vững.
7. Dùng state transition nguyên tử để lên lịch attempt mới.
8. Trả về `ACCEPTED`, **không gọi SMTP trong HTTP request**.
9. Worker xử lý theo lease và provider quota.
10. Audit attempt outcome.

Nếu notification đang `RETRY_WAIT` và automatic retry sắp chạy, manual retry có thể chỉ đổi `nextAttemptAt` theo policy; không được tạo hai attempts đồng thời cho cùng logical job.

## 11. Resend tạo notification mới

Resend là một quyết định gửi thêm:

```text
Original:
  notificationId = N-1001
  status = DELIVERED

Authorized resend:
  operationId = OP-9001
  reason = CUSTOMER_REQUEST
  requestedBy = operator-17

New:
  notificationId = N-2002
  resendOf = N-1001
  status = READY
```

Không cập nhật original từ `DELIVERED` về `READY`; làm vậy sẽ phá lịch sử submission và reporting. Resend mới có own status, attempts và provider event IDs.

Nên lưu `resendOfNotificationId`, `reasonCode`, `ticketId`, `requestedBy`, `approvalId` và content/version policy.

### Resend dùng nội dung nào?

- **Chứng từ/hóa đơn**: thường cần bản snapshot đã được phát hành hợp lệ.
- **Xác nhận đơn hàng**: tùy policy chọn snapshot gốc hoặc template mới.
- **OTP/reset-password**: không copy token cũ; phát hành workflow/token mới.
- **Marketing**: check consent/suppression **ở thời điểm resend**.
- **Thông báo trạng thái**: phải kiểm tra nội dung cũ còn đúng tình trạng hiện tại không.

“Resend raw MIME” không phải giải pháp phổ quát.

## 12. SUBMITTED khác DELIVERED, và cả hai khác retryable

Nếu `JavaMailSender.send(...)` kết thúc bình thường, SMTP hop hiện tại thường đã chấp nhận submission. Recipient vẫn có thể chưa thấy vì downstream deferral, filtering, quarantine hoặc bounce.

Khi người dùng báo chưa nhận:

1. Tìm provider message ID/SMTP queue ID nếu có.
2. Xem delivery/deferred/bounced events.
3. Kiểm tra message chưa bị suppression.
4. Xem provider logs/delays.
5. Chỉ cân nhắc resend theo authorized policy và cooldown.

Không tạo duplicate vì một email đã submit đang chờ provider delivery event.

## 13. SMTP outcome AMBIGUOUS cần guard đặc biệt

Một tình huống:

```text
Application                      SMTP relay
    |                                  |
    |---- MIME + DATA terminator ----->|
    |                                  | Queued already?
    |<---- final reply lost -----------X
    |
    +--> read timeout
         Outcome unknown
```

Không thể suy từ client timeout rằng server chắc chắn chưa nhận. Retry có thể tạo email thứ hai.

Policy có thể quy định:

- `AMBIGUOUS` bị chặn với quyền manual retry thông thường.
- Operator phải tra provider logs/queue ID nếu có.
- Có reconciliation window hoặc approval.
- Nếu business buộc retry, ghi rõ nguy cơ duplicate và rationale.
- Không đổi `AMBIGUOUS` thành `NOT_SENT` chỉ để hiển thị nút Retry.

SMTP MIME `Message-ID` không bảo đảm server sẽ tự deduplicate.

## 14. Consent và suppression là guard không được bypass tùy tiện

Một operator được quyền resend **không** được mặc nhiên:

- Gửi marketing sau unsubscribe.
- Gửi tiếp khi provider báo hard bounce/complaint.
- Gửi OTP/token đã hết hạn.
- Gửi thông báo sai với business state hiện tại.
- Bỏ qua quiet hours/frequency caps có hiệu lực.
- Gửi tài liệu đã bị thu hồi quyền chia sẻ.
- Dùng recipient cũ dù khách đã thay đổi địa chỉ có xác thực.

Nếu tổ chức có quy trình riêng giải quyết suppression, phải cấp quyền chuyên biệt; không biến `mail:resend_request` thành quyền gỡ suppression.

## 15. Tách con người và service identity

**Human operator**:

- Được xác thực (MFA nếu hành động nhạy cảm).
- Có authority theo role/tenant/ticket.
- Gửi durable command và cung cấp reason.
- Có audit actor/session/approval.
- Không cần giữ SMTP credential.

**Mail worker**:

- Có service principal riêng.
- Claim jobs từ durable store bằng lease.
- Chỉ đọc artifacts cần thiết.
- Gọi `JavaMailSender` qua SMTP credential do secret manager cấp.
- Không tự tạo resend command theo ý mình.
- Ghi attempt outcome theo ownership/version.
- Recheck các eligibility conditions có thể đổi.

Không chuyển HTTP `SecurityContext`/JWT nguyên vẹn vào `@Async` worker hoặc outbox để “giữ quyền operator”.

## 16. Spring Security method authorization

Ví dụ Spring Security hiện đại:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
```

Service boundary:

```java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class MailOperationsService {

    private final MailCommandHandler handler;

    public MailOperationsService(
            MailCommandHandler handler) {
        this.handler = handler;
    }

    @PreAuthorize("hasAuthority('mail:retry_request')")
    public MailOperationReceipt requestRetry(
            UUID notificationId,
            String reason,
            String idempotencyKey) {

        return handler.requestRetry(
            notificationId, reason, idempotencyKey
        );
    }

    @PreAuthorize("hasAuthority('mail:resend_request')")
    public MailOperationReceipt requestResend(
            UUID notificationId,
            String reason,
            String idempotencyKey) {

        return handler.requestResend(
            notificationId, reason, idempotencyKey
        );
    }
}
```

Các classes `MailCommandHandler`, `MailOperationReceipt` là abstraction ứng dụng.

`@PreAuthorize` ở đây kiểm tra **quyền thô** (coarse-grained). Command handler còn phải kiểm tra tenant, resource state, consent, content category, cooldown, approval và idempotency. Một authority đơn lẻ không đủ.

## 17. Actor identity phải được xác thực ở server

Một domain actor:

```java
public record MailActor(
    String subjectId,
    UUID tenantId,
    Set<String> authorities,
    boolean mfaSatisfied
) {}
```

Một provider:

```java
public interface MailActorProvider {
    MailActor currentActor();
}
```

Implementation có thể lấy từ `Authentication` do Spring Security đã xác thực, mapping custom principal/JWT claims sang `MailActor`.

Không nhận `actorId`, `tenantId`, `roles` hoặc `mfaSatisfied` từ request body rồi tin là đã được cấp quyền. Với token-based authentication, cần verify issuer/audience, tenant scope và grant semantics theo security configuration thực tế.

## 18. Authorization policy ở application layer

```java
public interface MailOperationPolicy {

    void requireRetryAllowed(
        MailActor actor,
        MailNotification notification,
        RetryRequest request
    );

    void requireResendAllowed(
        MailActor actor,
        MailNotification original,
        ResendRequest request
    );
}
```

Một policy concept:

```java
public void requireRetryAllowed(
        MailActor actor,
        MailNotification target,
        RetryRequest request) {

    requireAuthority(actor, "mail:retry_request");
    requireTenantMembership(actor, target.tenantId());
    requireAllowedCategory(actor, target.category());
    requireRetryableStatus(target.status());
    requireRetryableFailureClass(target.lastFailureClass());
    requireNotExpired(target.expiresAt());
    requireNoSuppression(target);
    requireAttemptBudget(target);
    requireCooldownElapsed(target.lastManualActionAt());
    requireValidReason(request.reasonCode());
}
```

Các helper `require...` là business implementation minh họa. Nếu điều kiện thất bại, không tạo attempt, không cập nhật outbox, không gọi SMTP.

Phần này phải chạy trên server và cần phối hợp với transaction/conditional update để không bị race.

## 19. Phòng TOCTOU khi trạng thái đổi giữa lúc kiểm tra và update

Rủi ro:

```text
Operator sees FAILED_TRANSIENT
         |
         v
Authorization check passes
         |
         +--> another worker submits message
         |    status becomes SUBMITTED
         |
         v
Manual retry updates status to READY
         |
         v
Duplicate submit
```

Đây là *time-of-check to time-of-use*.

Giải pháp:

- Validate trong transaction ngắn.
- Query resource theo authorized tenant.
- Dùng optimistic `version` hoặc conditional SQL.
- Chặn trạng thái `PROCESSING/SUBMITTED`.
- Unique idempotency key cho command.
- Re-evaluate mutable eligibility trước SMTP send.
- Check worker ownership/attempt token khi update outcome.

Không dựa vào dữ liệu đã load trên UI vài phút trước.

## 20. Conditional SQL cho manual retry

Ví dụ PostgreSQL:

```sql
UPDATE mail_notification
SET status = 'RETRY_WAIT',
    next_attempt_at = NOW(),
    version = version + 1,
    last_manual_requested_by = :actor_id,
    updated_at = NOW()
WHERE id = :notification_id
  AND tenant_id = :authorized_tenant_id
  AND version = :expected_version
  AND status IN (
      'FAILED_TRANSIENT',
      'FAILED_EXHAUSTED',
      'RETRY_WAIT'
  )
  AND attempt_count < :authorized_attempt_limit
  AND (
      last_manual_action_at IS NULL
      OR last_manual_action_at <= :cooldown_cutoff
  )
RETURNING id, version;
```

Cho `FAILED_EXHAUSTED` chỉ nên hợp lệ nếu policy đã cấp một retry budget đặc biệt; `authorized_attempt_limit` phải tính server-side, **không** nhận tùy ý từ HTTP request.

Query trên chỉ là phần kiểm tra atomic state. Service vẫn phải xác thực failure class, consent, category, approval và idempotency trước mutation. Nếu update trả 0 rows, trả conflict/re-evaluate thay vì fallback sang update không điều kiện.

## 21. Resend bằng insert mới, không reset original

Schema minh họa:

```sql
CREATE TABLE mail_notification (
    id                      UUID PRIMARY KEY,
    tenant_id               UUID NOT NULL,
    category                VARCHAR(50) NOT NULL,
    status                  VARCHAR(40) NOT NULL,
    recipient_ref           VARCHAR(200) NOT NULL,
    content_version         VARCHAR(80),
    resend_of_notification  UUID,
    requested_by            VARCHAR(200),
    version                 BIGINT NOT NULL DEFAULT 0,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

Khi resend:

```text
Original N-1001:
  status = DELIVERED
  resend_of_notification = null

New N-2002:
  status = READY
  resend_of_notification = N-1001
  requested_by = operator-17
  content_version = approved snapshot
```

Tạo notification/outbox intent và audit operation trong một transaction. Không sửa lịch sử accepted/delivered của original.

Trong thực tế còn cần durable recipient/content references, policy version, idempotency key, approval, business event và retention metadata.

## 22. Manual command cần idempotency key

Khi operator double-click, HTTP gateway retry hoặc response bị timeout, backend không được tạo hai resends.

Ví dụ request:

```http
POST /api/v1/mail-notifications/3f4.../resend
Idempotency-Key: 9fb541b4-0f92-4dd6-a67d-7b5a8fb6cf1b
Content-Type: application/json

{
  "reasonCode": "CUSTOMER_REQUEST",
  "ticketId": "T-8123"
}
```

Đường dẫn ID rút gọn chỉ để minh họa.

Một dedup scope:

```text
tenantId
+ authenticated actorId or service principal
+ actionType
+ originalNotificationId
+ idempotencyKey
```

Nếu cùng key và cùng semantic payload, trả lại operation receipt đã tạo. Nếu key trùng nhưng payload khác, trả conflict.

Idempotency phải bền vững qua restart và multi-instance (unique constraint/transaction), không chỉ là một `Map` trong memory.

## 23. Resend có key mới vẫn phải có cooldown

Idempotency key giải quyết request lặp của **cùng một ý định**, không tự chặn một operator cố tình gửi 20 requests với 20 keys mới.

Do đó cần:

- Per-notification resend cooldown.
- Per-recipient frequency cap.
- Per-actor action budget.
- Per-tenant quota.
- Provider rate budget.
- Approval thresholds.
- Dedup trong khoảng thời gian hợp lý nếu business policy yêu cầu.

Không dùng `originalNotificationId` làm unique key tuyệt đối cấm mọi resend mãi mãi: hai customer requests ở hai ngày khác nhau có thể là các ý định hợp lệ. Phải có policy rõ về thời gian và lý do.

## 24. API command không nên gửi SMTP trực tiếp

Endpoint:

```http
POST /api/v1/mail-notifications/{id}/retry
Idempotency-Key: ...

{
  "reasonCode": "INCIDENT_RESOLVED",
  "ticketId": "INC-42"
}
```

Hoặc:

```http
POST /api/v1/mail-notifications/{id}/resend
Idempotency-Key: ...

{
  "reasonCode": "CUSTOMER_REQUEST",
  "ticketId": "T-8123"
}
```

Khi command đã được lưu bền vững:

```http
HTTP/1.1 202 Accepted
Content-Type: application/json

{
  "operationId": "OP-9001",
  "status": "ACCEPTED",
  "notificationId": "N-2002",
  "requestedAction": "RESEND"
}
```

`202 Accepted` xác nhận command được nhận để xử lý, **không** chứng minh SMTP accepted, delivered hoặc opened. Một endpoint truy vấn operation/notification status sẽ cho biết kết quả cuối.

Nếu cần approval, command có thể ở `PENDING_APPROVAL` và chưa có send job READY.

## 25. Mã HTTP và policy response

| Tình huống | Mã thường dùng | Giải thích |
| --- | --- | --- |
| Chưa xác thực | 401 | Authentication bắt buộc |
| Không có action/scope | 403 | Forbidden |
| Không được biết resource tồn tại | 404 | Giảm lộ thông tin cross-tenant |
| State/version đã đổi | 409 | Conflict |
| Input/reason không hợp lệ | 400/422 | Validation failure |
| Rate limit/cooldown | 429 | Có thể có Retry-After |
| Approval required | 202 với PENDING_APPROVAL | Chưa gửi |
| Command durable accepted | 202 | Đã xếp lệnh |
| Key trùng, payload giống | Trả receipt cũ | Không tạo thao tác khác |
| Key trùng, payload khác | 409 | Idempotency conflict |

API cần error codes nhất quán, không tiết lộ SMTP secrets, raw MIME hoặc email addresses tenant khác trong error message.

## 26. Controller mỏng trong Spring Boot

```java
@RestController
@RequestMapping("/api/v1/mail-notifications")
public class MailOperationsController {

    private final MailOperationsService operations;

    public MailOperationsController(
            MailOperationsService operations) {
        this.operations = operations;
    }

    @PostMapping("/{id}/retry")
    public ResponseEntity<MailOperationReceipt> retry(
            @PathVariable UUID id,
            @RequestHeader("Idempotency-Key") String key,
            @RequestBody RetryRequest request) {

        MailOperationReceipt result =
            operations.requestRetry(
                id, request.reasonCode(), key
            );

        return ResponseEntity.accepted().body(result);
    }

    @PostMapping("/{id}/resend")
    public ResponseEntity<MailOperationReceipt> resend(
            @PathVariable UUID id,
            @RequestHeader("Idempotency-Key") String key,
            @RequestBody ResendRequest request) {

        MailOperationReceipt result =
            operations.requestResend(
                id, request.reasonCode(), key
            );

        return ResponseEntity.accepted().body(result);
    }
}
```

DTO:

```java
public record RetryRequest(String reasonCode) {}
public record ResendRequest(String reasonCode) {}

public record MailOperationReceipt(
    UUID operationId,
    UUID notificationId,
    String status
) {}
```

Đây là cấu trúc minh họa, chưa có validation annotations, ticket/approval, error handling, tenant scope hoặc transaction logic.

**Quyền quyết định phải ở service/policy layer**, không chỉ controller, vì cùng command có thể được gọi từ internal endpoint hoặc một workflow khác.

## 27. Lưu ý proxy và self-invocation với @PreAuthorize

Spring method security thường được thực thi qua proxy/AOP. Nếu một bean gọi chính method được annotate của nó bằng `this.requestRetry(...)`, có thể bỏ qua interceptor theo cấu hình thông thường.

Anti-pattern:

```java
@Service
public class MailOperationService {

    public void internalOperation(UUID id) {
        this.requestRetry(id); // May bypass proxy.
    }

    @PreAuthorize("hasAuthority('mail:retry_request')")
    public void requestRetry(UUID id) {
        // Mutation.
    }
}
```

Thiết kế nên:

- Đặt authorized boundary trong bean được gọi qua Spring proxy.
- Không lộ unaudited mutation path.
- Bảo vệ domain command bằng policy service ở sâu hơn.
- Dùng transaction/conditional state checks trong handler.
- Test cả API call và những đường gọi nội bộ.

Dù annotation có được bypass vì lý do kỹ thuật, **business policy checks** vẫn phải bảo vệ trạng thái quan trọng.

## 28. Không kéo HTTP Authentication sang worker

Worker có thể chạy sau nhiều phút hoặc trên JVM khác. Không serialize toàn bộ `Authentication`, session cookie hay JWT vào outbox.

```text
HTTP authenticated actor
          |
          v
Authorize + create durable operation
          |
          +--> actorId / tenantId
          +--> action / reason / ticket
          +--> approvalId
          |
          v
DB COMMIT
          |
          v
Mail worker with service identity
          |
          +--> Claim job
          +--> Recheck eligibility/lease
          +--> Send by JavaMailSender
          +--> Persist outcome
```

Worker không cần impersonate HTTP user. Nó có quyền hạ tầng để xử lý **những jobs đã được chấp nhận hợp lệ**. `TaskDecorator` giúp trace/MDC propagation, không phải cơ chế ủy quyền bền vững.

## 29. Approval / maker-checker cho hành động nhạy cảm

Một số actions nên cần hai người:

- Resend tài liệu chứa dữ liệu cá nhân nhạy cảm.
- Gửi lại một batch lớn/campaign.
- Override cooldown/retry budget trong incident.
- Gửi lại notification có outcome `AMBIGUOUS`.
- Thay đổi recipient khi tài liệu liên quan người khác.
- Hành động thuộc tenant/regulatory scope quan trọng.

Luồng:

```text
Requester
   |
   v
Create operation
   |
   v
PENDING_APPROVAL
   |
   +--> REJECTED / EXPIRED -> no send
   |
   +--> Approved by another authorized actor
                           |
                           v
                  Revalidate current policy
                           |
                           v
                  Create durable send intent
                           |
                           v
                      SMTP worker
```

**Người yêu cầu không nên tự phê duyệt** khi quy trình maker-checker yêu cầu separation of duties.

Approval có thời hạn, gắn tenant/notification/action/reason/recipient/content fingerprint rõ; không phải quyền chung gửi tùy ý trong tương lai.

## 30. Revalidate ở lúc approve và thực thi

Trong thời gian chờ approval:

- Người nhận có thể unsubscribe.
- Notification gốc có thể được báo DELIVERED.
- Actor/approver có thể mất quyền.
- Ticket có thể đóng.
- Document permission có thể bị thu hồi.
- OTP hoặc business deadline có thể hết hạn.

Do đó policy kiểm tra lại ở thời điểm quyết định phê duyệt và trước khi tạo send intent. Khi worker thực sự submit, còn cần recheck những điều kiện mutable như suppression, expiry và recipient eligibility.

Approval record có thể lưu:

```text
approvalId
operationId
requestedBy
approvedBy
approvedAt
expiresAt
tenantId
targetNotificationId
action
payloadFingerprint
reason/ticket
policyVersion
```

Không cho requester sửa recipient/content sau approval mà giữ nguyên approval cũ.

## 31. Rate limit, cooldown và budgets

| Guard | Chức năng |
| --- | --- |
| Per-actor command limit | Chặn một người gửi quá nhiều requests |
| Per-notification cooldown | Chặn nhiều resend liên tiếp |
| Per-recipient frequency cap | Bảo vệ người nhận |
| Per-tenant quota | Tenant isolation |
| SMTP provider rate limit | Tuân thủ account/domain quota |
| Manual resend daily cap | Giảm rủi ro thao tác thủ công |
| Max attempts | Chặn retry vô hạn |
| Backoff + jitter | Giảm retry storm |
| Business expiry | Không gửi nội dung đã hết giá trị |

Manual retry không được mặc nhiên bỏ qua provider quota. Nếu có `mail:retry_override`, quyền này nên chỉ cho phép override **những guard cụ thể** có scope/time limit, không bypass consent hoặc tenant isolation.

Đừng giữ worker bằng `Thread.sleep` để cooldown. Persist `nextAttemptAt` rồi để scheduler xử lý khi đến hạn.

## 32. Control plane và data plane

Kiến trúc:

```text
Admin UI / API
      |
      v
Spring Security
      |
      v
MailOperationsService
  - RBAC + ABAC
  - Tenant/resource scope
  - State/failure policy
  - Idempotency/cooldown
  - Approval/audit
      |
      v
Durable command/outbox transaction
      |
      v
Sender worker with service identity
  - Claim/lease
  - Eligibility recheck
  - Rate limit
  - Build MimeMessage
  - JavaMailSender.send(...)
  - Persist status
```

Ưu điểm:

- HTTP request không bị SMTP timeout kéo dài.
- SMTP credential không tới admin UI.
- Có trạng thái operation bền vững.
- Worker restart có thể recover bằng lease.
- Audit command trước khi có side effect.
- Không vì một quyền UI mà biến operator thành SMTP relay.

## 33. Audit phải ghi cả allowed và denied

Các sự kiện gợi ý:

```text
mail.retry.requested
mail.retry.denied
mail.resend.requested
mail.resend.pending_approval
mail.resend.approved
mail.resend.rejected
mail.operation.accepted
mail.operation.executed
mail.smtp.attempted
mail.smtp.submitted
mail.smtp.failed
mail.smtp.ambiguous
```

Một audit record:

```json
{
  "eventType": "mail.resend.requested",
  "operationId": "OP-9001",
  "actorId": "operator-17",
  "tenantId": "tenant-42",
  "action": "RESEND",
  "targetNotificationId": "N-1001",
  "reasonCode": "CUSTOMER_REQUEST",
  "ticketId": "T-8123",
  "decision": "PENDING_APPROVAL",
  "policyVersion": "v5",
  "timestamp": "2026-11-12T11:00:00Z"
}
```

Không ghi raw OTP, body, attachments, SMTP password hoặc access tokens vào audit. Có thể dùng recipient reference/masked address theo access policy.

**Audit durability:** nếu command DB commit thành công mà log collector hỏng, vẫn cần tra được actor và quyết định. Có thể lưu audit events trong DB cùng transaction hoặc transactional outbox để xuất về audit system sau.

## 34. Operation record và unique key

Schema minh họa:

```sql
CREATE TABLE mail_operation (
    id                      UUID PRIMARY KEY,
    tenant_id               UUID NOT NULL,
    action_type             VARCHAR(30) NOT NULL,
    target_notification_id  UUID NOT NULL,
    new_notification_id     UUID,
    actor_id                VARCHAR(200) NOT NULL,
    reason_code             VARCHAR(100) NOT NULL,
    ticket_id               VARCHAR(200),
    idempotency_key         VARCHAR(200) NOT NULL,
    payload_fingerprint     VARCHAR(100) NOT NULL,
    status                  VARCHAR(40) NOT NULL,
    approval_id             UUID,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (
        tenant_id,
        actor_id,
        action_type,
        target_notification_id,
        idempotency_key
    )
);
```

Đây không phải schema Spring Mail có sẵn. Cần giới hạn độ dài idempotency key, scope theo service principal, retention policy, audit event history và cách replay operation receipt.

Tạo operation/resend intent/audit trong transaction thích hợp và không tạo send job khi approval chưa hợp lệ.

## 35. Recipient, From và Bcc phải có policy

Một API resend không nên nhận và tin các giá trị tùy ý:

```json
{
  "to": "attacker@example.net",
  "bcc": ["hidden@example.net"],
  "from": "ceo@example.com"
}
```

Các trường nhạy cảm này phải do application kiểm soát:

- `To` dựa trên verified recipient của business resource.
- `Cc/Bcc` chỉ do policy được phép xác định.
- `From` dựa trên provider account/verified sender alias.
- Attachment references được kiểm tra tenant và quyền truy cập.
- `Reply-To` có routing policy riêng.
- Nếu cần đổi recipient, phải qua workflow xác minh mới.

**Một quyền resend không đồng nghĩa quyền đổi recipient**. Việc chuyển hóa đơn sang địa chỉ mới có thể cần xác minh account/email ownership và approval.

## 36. Resend email bảo mật không nên copy token cũ

Với OTP/password reset/email verification:

- Token có TTL.
- Token có thể single-use hoặc đã bị thu hồi.
- Email cũ có thể chứa URL hết hạn.
- Gửi lại raw MIME có thể tạo thông điệp vô dụng hoặc rủi ro.
- Người dùng có thể đang bị tấn công request flooding.

Workflow thích hợp:

```text
Authorized user/security recovery request
         |
         v
Identity service validates state, rate, risk
         |
         v
Issue/rotate token according to policy
         |
         v
Create NEW notification intent
         |
         v
Mail worker sends through normal quota
```

Một support operator không nên được quyền đọc raw OTP/token chỉ để xử lý “resend”. Việc cấp security token mới thuộc authentication/identity flow, không phải quyền chung của mail operator.

## 37. Đổi recipient nên là workflow riêng

Khi khách yêu cầu “Gửi hóa đơn tới địa chỉ mới”, cần:

1. Xác minh yêu cầu từ đúng account/đúng người được quyền.
2. Xác minh email ownership hoặc căn cứ hợp lệ.
3. Kiểm tra consent/suppression.
4. Đảm bảo tài liệu đúng người và đúng phiên bản.
5. Áp approval nếu chính sách yêu cầu.
6. Tạo notification mới tới recipient đã xác minh.
7. Audit việc thay đổi recipient/reason.

Không đơn giản cho operator truyền `toOverride` tùy ý qua resend API.

## 38. UI capability chỉ phục vụ hiển thị

UI có thể nhận:

```json
{
  "canRequestRetry": true,
  "canRequestResend": false,
  "retryRequiresReason": true,
  "resendRequiresApproval": true,
  "explanations": ["RESEND_NOT_ALLOWED_FOR_FAILED_ORIGINAL"]
}
```

Giao diện có thể hiển thị:

```text
Notification N-1001
Status: FAILED_TRANSIENT
Failure: SMTP_TEMPORARY
Manual retry: Allowed
Resend: Not allowed
Next automatic retry: 10:45 UTC
Cooldown until: 10:43 UTC
```

Capability kết quả tại thời điểm xem không phải một giấy phép vĩnh viễn. Backend phải **check lại khi bấm** vì notification status, roles và consent có thể đổi.

Ẩn nút không bảo vệ API nếu client gọi trực tiếp.

## 39. UI confirmation tránh nhầm hành động

Với resend đã SUBMITTED hoặc DELIVERED, UI nên giải thích:

- **Retry failed send:** hoàn tất cùng notification chưa thành công.
- **Send another copy:** tạo notification mới, người nhận có thể thấy hai bản.
- **Reissue secure link:** tạo một security workflow/token mới.

Ví dụ:

```text
Action: Send another copy
Original status: DELIVERED
Recipient: masked
Category: ORDER_CONFIRMATION
Reason: CUSTOMER_REQUEST
Effect: A new notification will be created
Warning: Recipient may receive a duplicate
```

Một confirmation dialog giúp giảm thao tác nhầm nhưng không thay server-side authorization, cooldown và idempotency.

## 40. Chính sách theo category

| Category | Retry | Resend |
| --- | --- | --- |
| TRANSACTIONAL | Theo transient failure | Theo authorized customer request |
| SECURITY | Qua recovery policy | Không copy token cũ; reissue |
| MARKETING | Theo consent/suppression | Rất hạn chế, áp frequency caps |
| OPERATIONAL | Theo incident policy | Theo incident runbook |
| LEGAL/COMPLIANCE | Quy trình chuyên biệt | Có thể cần approval |

Policy còn phụ thuộc tenant, jurisdiction, loại tài liệu và business context. Không nên cho phép một actor bypass các yêu cầu bắt buộc chỉ vì có role cấp cao.

## 41. Break-glass cần hẹp, có thời hạn và audit

Trong incident lớn, đôi khi cần override một số giới hạn như retry budget sau khi đã sửa SMTP credential.

Một break-glass policy nên có:

- Ticket/lý do bắt buộc.
- MFA hoặc xác thực mạnh.
- Scope cụ thể: tenant/category/notification/provider.
- Nêu guard được override.
- Hết hạn tự động.
- Approval/hậu kiểm.
- Alert tới security/operations.
- Immutable audit.
- Không được mở rộng quyền xem nội dung không liên quan.

Không dùng một “super-admin bypass all” thường trực. Không bypass tenant isolation, consent hoặc workflow xác thực token.

## 42. Monitoring manual operations

Metrics gợi ý:

| Metric | Ý nghĩa |
| --- | --- |
| `mail_manual_retry_requests_total` | Lệnh manual retry |
| `mail_resend_requests_total` | Lệnh resend |
| `mail_operation_denied_total` | Denied theo reason |
| `mail_operations_pending_approval` | Approval backlog |
| `mail_resend_approved_total` | Approved resends |
| `mail_retry_attempts_total` | Attempts thực tế |
| `mail_resend_submitted_total` | Resend SMTP accepted |
| `mail_ambiguous_operations_total` | Outcome cần điều tra |
| `mail_idempotent_replay_total` | Requests được dedup |
| `mail_policy_override_total` | Override actions |

Các tên metric là ví dụ ứng dụng tự tạo, không mặc định có trong Spring Mail.

Chỉ dùng tags cardinality thấp như action, category, outcome. Không dùng recipient email, notification ID hoặc ticket ID làm metric labels.

Alert cần theo dõi spike manual resends, nhiều denied operations, approval backlog bất thường và tỷ lệ SMTP errors sau một đợt retry.

## 43. Test quyền ở service và API

Một nhóm unit/integration tests:

1. Viewer không có retry/resend permission.
2. Support agent chỉ thao tác với ticket được giao.
3. Cùng role nhưng khác tenant vẫn bị từ chối.
4. Notification SUBMITTED không retry.
5. FAILED_TRANSIENT được retry nếu hợp lệ.
6. FAILED_PERMANENT/SUPPRESSED/EXPIRED bị chặn.
7. AMBIGUOUS cần approval hoặc policy riêng.
8. Resend token hết hạn không copy raw token.
9. Unsubscribe sau original khiến resend bị chặn.
10. Reason/ticket thiếu thì không ghi durable command.
11. Requester không tự approve.
12. Approval hết hạn/bị revoke không cho execute.
13. Idempotency replay không tạo thêm job.
14. Same idempotency key + payload khác trả conflict.
15. Người có mail action permission nhưng không có read-content permission không xem raw body.
16. Service actor không thể tạo resend tùy ý qua internal API.

Spring Security tests có thể dùng `@WithMockUser` cho authorities đơn giản hoặc mock JWT/custom principal khi cần tenant claims. Test phải bao phủ code path thực đi qua method-security proxy.

## 44. Test race conditions và DB atomicity

Các tình huống:

- Hai operator đồng thời retry một notification.
- Manual retry đua với automatic retry.
- Double-click resend tạo một new notification cho cùng idempotency key.
- Hai approvers cùng bấm approve; chỉ một execution.
- Notification chuyển SUBMITTED trước khi retry command commit.
- Recipient unsubscribe khi approval pending.
- Actor bị revoke permission trước khi execute.
- Worker crash sau SMTP accepted nhưng trước DB update.
- Stale worker hết lease cố ghi đè status.
- Audit operation và outbox mutation phải nhất quán trong transaction.

Những tests này cần database có concurrency semantics phù hợp; chỉ mock repository trả success cho mọi call sẽ không kiểm tra được duplicate/race.

## 45. SMTP integration tests nên dùng test server

Một test end-to-end:

```text
Authorized API command
      |
      v
Durable operation/outbox
      |
      v
Worker claim
      |
      v
JavaMailSender
      |
      v
GreenMail SMTP capture server
      |
      v
Captured MimeMessage
```

Assertions quan trọng:

- Unauthorized command: không có job mới, không gửi.
- Retry: giữ original notification ID, tạo attempt mới.
- Resend: tạo notification ID mới với `resendOf`.
- Duplicate idempotency key: không có email thứ hai.
- Suppressed/expired/approval pending: chưa gửi.
- Authorized recipient đúng, không có Bcc/From override trái phép.
- Audit có actor/reason/ticket/approval.
- SMTP temporary failure có retry backoff.
- SMTP accepted làm `SUBMITTED`, không tự đánh dấu `DELIVERED`.

Không dùng SMTP account/recipient production trong CI.

## 46. Runbook manual retry

1. Xác định notification ID, actor và tenant/ticket scope.
2. Đọc status, last failure class, attempt history và nextAttemptAt.
3. Nếu đang PROCESSING, kiểm tra owner/lease thay vì claim thêm.
4. Nếu RETRY_WAIT, xem automatic retry sắp chạy hay không.
5. Nếu FAILED_TRANSIENT/FAILED_EXHAUSTED, xác minh nguyên nhân đã khắc phục.
6. Nếu FAILED_PERMANENT, sửa dữ liệu/cấu hình trước.
7. Nếu AMBIGUOUS, kiểm tra provider queue ID/logs và duplicate risk.
8. Nếu SUBMITTED/DELIVERED, không retry; cân nhắc resend riêng.
9. Xác minh recipient, consent, suppression và deadline.
10. Ghi reason/ticket và approval khi cần.
11. Gửi idempotent command.
12. Theo dõi operation rồi SMTP outcome và downstream event.

Không dùng SQL trực tiếp `UPDATE mail_notification SET status='READY'` như thao tác vận hành thường xuyên vì dễ bỏ qua authorization, audit và state transition.

## 47. Runbook khi khách yêu cầu resend

1. Xác minh người yêu cầu có quyền nhận bản sao.
2. Tìm original notification và category/content version.
3. Xác minh original đã SUBMITTED/DELIVERED hay AMBIGUOUS.
4. Kiểm tra xem có chỉ là provider delay không.
5. Kiểm tra snapshot, attachment và token expiry.
6. Kiểm tra consent/suppression/recipient eligibility hiện thời.
7. Nếu địa chỉ đổi, chuyển sang workflow đổi recipient có xác minh.
8. Xem lịch sử resend và cooldown.
9. Xác minh authority, tenant scope và approval requirement.
10. Ghi reason/ticket, tạo operation với idempotency key.
11. Tạo notification mới liên kết `resendOf`.
12. Theo dõi worker SMTP submission và provider events.

Mục tiêu là tạo một bản sao có chủ đích, không che mất lịch sử, không gửi sai người và không bỏ qua business policy.

## 48. Anti-pattern thường gặp

| Anti-pattern | Hậu quả | Thay thế |
| --- | --- | --- |
| Chỉ ẩn nút Retry | API có thể gọi trực tiếp | Server-side authorization |
| Kiểm tra ROLE_ADMIN duy nhất | Vượt tenant, state, consent | RBAC + ABAC |
| Operator gọi JavaMailSender ngay | Khó audit, lộ transport quyền | Durable command/worker |
| Retry mọi FAILED | Vòng lặp lỗi permanent | Failure-class policy |
| Retry SUBMITTED/DELIVERED | Gửi trùng | Resend notification mới |
| Resend update original thành READY | Sai lịch sử | Insert new record với resendOf |
| Resend OTP/token cũ | Token hết hạn/rủi ro | Identity workflow reissue |
| Cho operator tự điền To/Bcc/From | Data leak/open relay | Verified sender/recipient |
| Không check tenant trong query | Cross-tenant access | Tenant-scoped lookup |
| Idempotency in-memory | Restart làm mất dedup | Durable unique key |
| Không cooldown/attempt budget | Spam/retry storm | Quotas/backoff |
| Bỏ qua unsubscribe | Vi phạm consent | Recheck eligibility |
| Requester tự approve | Maker-checker vô hiệu | Approver độc lập |
| Approval không gắn payload | Sửa recipient sau duyệt | Immutable fingerprint |
| Không CAS/version khi update | Race và duplicate | Atomic transition |
| Coi HTTP 202 là gửi thành công | Báo sai | Operation/attempt status |
| Coi SMTP accepted là delivered | Báo sai | Provider events |
| Retry timeout sau DATA như chưa gửi | Duplicate | AMBIGUOUS/reconcile |
| Log OTP, raw HTML, attachment | Lộ dữ liệu | Minimized audit/telemetry |
| Dùng log collector làm nguồn audit duy nhất | Có thể mất khi collector lỗi | Durable audit record |

## 49. Lộ trình triển khai production

1. Tách rõ automatic retry, manual retry và resend.
2. Xây state machine có transient, permanent, ambiguous, submitted và suppressed states.
3. Định nghĩa authorities theo hành động thay vì một role chung.
4. Dùng ABAC theo tenant/resource/category/ticket/consent/deadline.
5. Đặt Spring Security method authorization ở command service.
6. Thêm policy check authoritative trong transaction.
7. Dùng optimistic version/conditional SQL cho retry.
8. Resend tạo notification mới, giữ original bất biến.
9. Dùng durable idempotency key và operation receipt.
10. Giới hạn cooldown, quota, retry budget.
11. Thêm approval maker-checker cho trường hợp nhạy cảm.
12. Dùng service identity riêng cho worker, không giữ HTTP token.
13. Ghi audit actor/reason/approval/state transitions bền vững.
14. Revalidate eligibility trước SMTP khi dữ liệu có thể đổi.
15. UI cung cấp capability/confirmation nhưng không thay backend enforcement.
16. Kiểm thử denied/allowed, cross-tenant, concurrency, ambiguity và audit.
17. Thêm metrics/alerts và runbook incident.

## 50. Checklist trước khi cho phép

- [ ] Actor đã được xác thực bằng cơ chế phù hợp?
- [ ] Có authority đúng cho **retry** hoặc **resend**?
- [ ] Actor có quyền trên tenant/resource/ticket cụ thể?
- [ ] Trạng thái và failure class cho phép action?
- [ ] Original có outcome AMBIGUOUS hoặc delivery còn chờ?
- [ ] Recipient/From/Bcc được quyết định từ nguồn tin cậy?
- [ ] Consent, suppression, complaint và business expiry còn hợp lệ?
- [ ] Email bảo mật có cần phát hành token mới?
- [ ] Cooldown/quota/retry budget còn cho phép?
- [ ] Reason/ticket/approval có đủ không?
- [ ] Idempotency key và expected version được kiểm tra?
- [ ] Audit record commit cùng command mutation?
- [ ] Worker có lease/ownership và recheck eligibility?
- [ ] API trả ACCEPTED/PENDING chứ không tự nhận DELIVERED?
- [ ] Log/metric không rò credentials, OTP, raw MIME?

## 51. Ghi nhớ

- **Automatic retry** là trách nhiệm của worker/policy; **manual retry** tiếp tục notification; **resend** tạo notification mới.
- Quyền thao tác là authentication + RBAC/ABAC + business policy, không chỉ role.
- Tenant scope phải kiểm tra trong resource query; UUID không thay authorization.
- Retry theo trạng thái và failure class, không retry mù mọi lỗi.
- SUBMITTED/DELIVERED không thuộc luồng retry; muốn thêm bản sao phải qua resend.
- AMBIGUOUS sau SMTP DATA cần đối soát vì có rủi ro duplicate.
- OTP/reset link hết hạn không được resend bằng cách copy raw email.
- Resend không tự cho phép bỏ qua unsubscribe/suppression/consent.
- `@PreAuthorize` là lớp chặn coarse-grained; policy và atomic DB update bảo vệ quyết định thật.
- Không nhận actor/roles/tenant từ request body làm nguồn xác thực.
- Idempotency bền vững giúp chống double-click và gateway retries.
- Resend tạo new notification và giữ `resendOf`; original không bị reset status.
- Approval có thời hạn, tách requester/approver và gắn immutable payload.
- Worker chạy với service identity, không mang JWT của operator qua async queue.
- Audit actor/reason/ticket/approval cần bền vững và được bảo vệ dữ liệu.
- Manual actions vẫn chịu rate limits, cooldown và provider quota.
- HTTP 202 chỉ báo operation accepted, không phải SMTP delivered.
- Cần revalidate quyền và eligibility khi trạng thái có thể thay đổi.

**Nguyên tắc cốt lõi:** Trong Spring Framework Mail production, retry và resend là **các business commands có phân quyền, chính sách, audit và idempotency**, không phải hai nút gọi thẳng `JavaMailSender.send(...)`. Giữ retry trên notification gốc, tạo notification mới cho resend, bảo vệ tenant/recipient/consent và giao SMTP cho worker có quyền hạ tầng riêng. Thiết kế đó giúp vận hành có thể kiểm toán, hạn chế gửi nhầm hoặc gửi trùng, và không biến công cụ hỗ trợ thành lỗ hổng bảo mật.
