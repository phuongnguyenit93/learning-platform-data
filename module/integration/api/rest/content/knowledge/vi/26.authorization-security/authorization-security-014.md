# Audit log cho thay đổi quan trọng và bảo vệ dữ liệu nhạy cảm

## 1. Audit log trả lời câu hỏi gì?

Một REST API có thể trả **204 No Content** sau khi quản trị viên cấp quyền duyệt hoàn tiền. Về sau, bộ phận an ninh cần biết **ai** cấp quyền, **cho ai**, **khi nào**, **thuộc tenant nào**, **dưới thẩm quyền nào** và **thao tác có thực sự được ghi vào dữ liệu hay không**. Log ứng dụng như “POST finished in 36 ms” không trả lời đủ những câu hỏi đó.

**Audit trail** là chuỗi sự kiện có cấu trúc để quy trách nhiệm, điều tra, đối soát và phát hiện thay đổi quan trọng. Nó khác với application log dùng gỡ lỗi, access log ghi yêu cầu mạng và metric dùng đo sức khỏe hệ thống. Audit log phải **đáng tin cậy nhưng tối thiểu hóa dữ liệu**, vì bản thân kho audit cũng có thể trở thành nơi tập trung quyền truy cập, thông tin định danh và bí mật.

Bài thuộc chương **Phân quyền và an toàn**, module **INTEGRATION_API_REST**: xây REST API theo resource, URI, HTTP methods/status, hợp đồng rõ ràng, xác thực/phân quyền, idempotency và kiểm thử Java/Spring. Ví dụ dùng **Java 17+, Spring Boot 3.x, Spring Security 6.x, Spring MVC và Spring Data JPA**; các yêu cầu lưu trữ/pháp lý cụ thể cần theo chính sách tổ chức và khu vực áp dụng.

Mục tiêu:

- Chọn đúng **thao tác cần audit** và định nghĩa sự kiện phản ánh kết quả nghiệp vụ.
- Xây cấu trúc **actor, action, target, tenant, time, outcome, correlation ID**, không ghi bừa request body.
- Bảo vệ **token, mật khẩu, PII, dữ liệu thanh toán và khóa** khỏi audit log.
- Bảo đảm sự kiện quan trọng **không mất khi transaction commit hoặc broker tạm lỗi**.
- Hạn chế sửa/xóa, truy cập và trích xuất audit bằng phân quyền, kiểm soát toàn vẹn và retention.
- Triển khai luồng Spring REST và kiểm thử đúng HTTP/security/transaction.

## 2. Phân biệt audit với các loại log

| Loại ghi nhận | Ví dụ | Mục tiêu chính | Có thể thay thế audit không? |
| --- | --- | --- | --- |
| **Access log** | POST /users/{id}/roles trả 204 | Đường vào, latency, HTTP status | **Không**: không biết thay đổi nào được commit |
| **Application log** | “Role service called” | Debug lỗi code, luồng thực thi | **Không**: có thể bị sampling hoặc đổi level |
| **Security event** | Token sai, quyền bị từ chối, policy đổi | Phát hiện tấn công/bất thường | Có thể là một nguồn của audit, cần ngữ nghĩa riêng |
| **Audit event** | ROLE_GRANTED cho user u-42, kết quả COMMITTED | Truy cứu thay đổi nghiệp vụ | **Có**, nếu chính sách độ bền/toàn vẹn đạt |
| **Metrics/traces** | Request p95, trace span | Quan sát hiệu năng/phụ thuộc | **Không**: trace có thể được sampling và tự hết hạn |

Audit không phải “log mọi thứ, giữ mãi”. Ghi quá nhiều sự kiện không phân loại sẽ vừa tốn chi phí, vừa khiến người điều tra khó tìm sự kiện quan trọng, đồng thời tăng nguy cơ rò dữ liệu.

### Ví dụ HTTP

~~~http
POST /api/v1/users/u-42/role-assignments HTTP/1.1
Authorization: Bearer <access-token>
Content-Type: application/json
If-Match: "user-42-v7"

{
  "role": "REFUND_APPROVER",
  "reasonCode": "SUPPORT_ESCALATION"
}
~~~

~~~http
HTTP/1.1 204 No Content
Cache-Control: no-store
~~~

Khi việc cấp quyền **được commit**, hệ thống phải tạo một sự kiện audit tương ứng. Không ghi access token hay toàn bộ HTTP body. **If-Match** trong ví dụ là validator của chính collection role-assignments, do GET collection cung cấp; không dùng ETag của resource khác để kiểm tra nhầm precondition. Nếu muốn thêm **Idempotency-Key**, server phải có hợp đồng lưu/chống trùng riêng; hai cơ chế này **không tự tạo audit**.

## 3. Sự kiện nào cần ghi và khi nào?

Bắt đầu từ **risk assessment** và yêu cầu truy cứu của tổ chức, không dựa trên tên HTTP method đơn thuần.

| Nhóm thao tác | Event đề xuất | Cần phân biệt |
| --- | --- | --- |
| Cấp/thu hồi role, scope, quyền quản trị | ROLE_GRANTED / ROLE_REVOKED | Ai cấp, quyền nào, target nào, tenant |
| Reset MFA, đổi email khôi phục | MFA_RESET / RECOVERY_CONTACT_CHANGED | Ghi loại thay đổi, **không ghi secret/email đầy đủ** |
| Tạo/thu hồi API key hoặc credential | API_KEY_CREATED / API_KEY_REVOKED | Chỉ key ID/fingerprint, **không lưu giá trị key** |
| Duyệt hoàn tiền, điều chỉnh số dư | REFUND_APPROVED / BALANCE_ADJUSTED | Số tiền, currency, reference theo policy |
| Đổi cấu hình security, chính sách hoặc audit | SECURITY_POLICY_CHANGED | Cả người yêu cầu và người phê duyệt |
| Export dữ liệu nhạy cảm hoặc chia sẻ ngoài | SENSITIVE_EXPORT_REQUESTED / COMPLETED | Mục đích, phạm vi, số bản ghi/định danh job |
| Truy cập trái quyền, token thất bại | ACCESS_DENIED / TOKEN_REJECTED | Ngữ cảnh an toàn, giới hạn để tránh log flood |
| Đọc resource thông thường | Không mặc định mọi GET | Chỉ audit nếu loại dữ liệu/policy yêu cầu |

**Tách event attempted, denied, accepted và committed.** Một request GET/POST đến được controller chưa chắc đã ghi dữ liệu thành công. Với async job, **202 Accepted** chỉ là nhận việc; cần event riêng cho **JOB_COMPLETED / JOB_FAILED** khi công việc thực sự kết thúc.

Một số sự kiện bị từ chối diễn ra **trước transaction** (401/403), có thể ghi qua security filter/handler theo kênh riêng. Sự kiện commit của nghiệp vụ nên gắn với **transaction đã thành công**. Nếu ghi “ROLE_GRANTED” trước khi transaction rollback, trail sẽ sai thực tế.

### Phân biệt command và state change

- **ROLE_GRANT_REQUESTED**: hệ thống đã nhận yêu cầu, không bảo đảm đã thay đổi.
- **ROLE_GRANT_DENIED**: xác thực/phân quyền hoặc policy không cho phép.
- **ROLE_GRANTED**: trạng thái quyền đã commit.
- **ROLE_GRANT_NOOP**: quyền đã tồn tại, không có state change; quyết định có ghi riêng theo policy.
- **ROLE_GRANT_FAILED**: lỗi trước commit, nên ghi dạng thất bại chứ không giả thành granted.

Không trộn **HTTP status 204** với “audit đã được chuyển tới kho SIEM”. Thành công của API và độ trễ chuyển sự kiện đến hệ thống phân tích là hai khái niệm khác nhau; cần công bố mức bảo đảm thực.

## 4. Schema audit: vừa đủ để điều tra, không biến thành bản sao dữ liệu

Một envelope minh họa:

~~~json
{
  "eventId": "evt-01JZ7Q...",
  "schemaVersion": 1,
  "eventType": "ROLE_GRANTED",
  "occurredAt": "2026-11-18T09:30:00Z",
  "recordedAt": "2026-11-18T09:30:01Z",
  "actor": {
    "kind": "USER",
    "subject": "sub-123",
    "clientId": "admin-portal"
  },
  "tenantId": "tenant-a",
  "target": {
    "type": "USER",
    "id": "u-42"
  },
  "outcome": "COMMITTED",
  "change": {
    "fields": ["roleAssignments"],
    "grantedRole": "REFUND_APPROVER"
  },
  "reasonCode": "SUPPORT_ESCALATION",
  "requestId": "req-e91",
  "traceId": "trace-8c7",
  "operationId": "op-841"
}
~~~

| Trường | Bất biến thiết kế |
| --- | --- |
| **eventId** | ID duy nhất, bất biến; hỗ trợ de-duplicate trên đường chuyển |
| **schemaVersion** | Cho phép reader xử lý event cũ khi schema tiến hóa |
| **eventType** | Machine-readable, ổn định, không dùng bản dịch làm mã |
| **occurredAt / recordedAt** | UTC, ghi rõ ý nghĩa; phân biệt lúc nghiệp vụ xảy ra và lúc nhận vào sink |
| **actor** | Principal/service đã xác minh; phân biệt user trực tiếp và service được ủy quyền |
| **tenantId, target** | Phạm vi để kiểm soát truy vấn/correlation; không lấy tenant tùy tiện từ body |
| **outcome** | REQUESTED/DENIED/COMMITTED/FAILED theo từ vựng đã công bố |
| **change** | Danh sách trường và giá trị **được cho phép**; không dump entity |
| **requestId, traceId, operationId** | Liên kết request, trace, async job, retry và các service |
| **reasonCode** | Lý do chuẩn hóa; không nhận tự do thông tin bí mật nếu không cần |

Không yêu cầu mọi event phải có đủ toàn bộ trường. Security event bị từ chối có thể **không được biết target thực sự tồn tại**; tránh làm lộ owner/tenant bằng cách đặt thông tin chưa xác minh vào “trusted target”.

**Không dùng tên class Java, stack trace, log message tự do hay JSON request nguyên bản** làm schema audit. Bảo đảm event có version, đơn vị thời gian UTC, sự phân biệt giữa hành động thử và thay đổi đã commit.

## 5. Actor, tenant và correlation phải đến từ nguồn đáng tin

Với JWT resource server, caller có thể có **sub, iss, aud, scope, client_id** và claim tenant theo hợp đồng IdP. Chỉ tin claims **sau khi** Spring Security xác thực token và kiểm tra issuer, audience, thời hạn và chữ ký. Nếu quyền tenant thuộc domain model, truy vấn tenant membership dựa trên principal thay vì tin một tenantId client tự gửi.

Cần phân biệt:

- **actor**: principal thực hiện thao tác, có thể là USER, SERVICE hoặc SCHEDULED_JOB.
- **delegated actor**: khi service gọi thay user, ghi cả service identity và user delegation **nếu đã xác minh**, không suy từ header X-User-Id bất kỳ.
- **tenant**: phạm vi bảo vệ resource; audit event và truy vấn audit đều phải được tenant-scoped.
- **requestId**: lấy từ gateway/tracing đã kiểm soát hoặc do server sinh; giá trị client gửi phải được giới hạn ký tự/độ dài.
- **operationId**: định danh thao tác nghiệp vụ, liên kết retry, idempotency và async processing.

Không gộp tất cả retries thành “một request duy nhất” nếu mục tiêu điều tra cần biết số lần thử. Có thể có **request-attempt security log** và **một state-change event duy nhất** cho nghiệp vụ commit. Đây là hai lớp có chức năng khác nhau.

## 6. Bảo vệ dữ liệu nhạy cảm ngay từ lúc tạo sự kiện

Mặc định **không ghi mọi dữ liệu có thể đọc được**. Tạo schema theo **allowlist**: field nào thật sự cần cho mục đích audit mới được đưa vào event. Redaction ở tầng log collector là tuyến phòng vệ bổ sung, không thay nguyên tắc giảm thiểu dữ liệu tại nguồn.

| Loại dữ liệu | Quy tắc khuyến nghị |
| --- | --- |
| Password, OTP, refresh/access token, API key, private key | **Không ghi giá trị**; chỉ ghi loại thao tác, ID/fingerprint không thể dùng để đăng nhập |
| Cookie, Authorization header, signed URL | Không lưu nguyên trạng; lọc cả request, response, exception và tracing |
| Email, điện thoại, địa chỉ, số tài khoản | Tránh giá trị thô; ghi “field changed”, ID nội bộ hoặc bản mã hóa/masked theo nhu cầu đã phê duyệt |
| Số thẻ thanh toán, CVV, thông tin tài chính đặc biệt | Không ghi dữ liệu xác thực nhạy cảm; tuân chính sách ngành và cơ chế tokenization |
| Role/permission | Có thể ghi mã role trước/sau nếu mục đích audit cần; quyền đọc log phải giới hạn |
| Số tiền, currency, business reference | Ghi khi cần đối soát và được phân loại; không kèm toàn bộ payload thanh toán |
| Địa chỉ IP / User-Agent | Chỉ nếu phục vụ security analysis; quản lý retention và tránh giá trị có thể giả mạo |
| Request body, entity, DTO.toString() | **Không dump nguyên bản**; dễ chứa dữ liệu chưa biết trong những field mới |

### Ví dụ không nên làm

~~~java
// Không dùng ở đường xử lý production:
log.info("role change request={} auth={}", request, authentication);
auditService.append(objectMapper.writeValueAsString(entity));
~~~

Khi DTO/entity phát triển, các lệnh trên có thể vô tình ghi passwordHash, phone, token, metadata của khách hàng hoặc thông tin tenant. Exception stack trace cũng có thể chứa URL ký, SQL parameter hay rejectedValue.

### Ghi thay đổi theo allowlist

Ví dụ sự kiện đổi email khôi phục chỉ cần:

~~~json
{
  "eventType": "RECOVERY_CONTACT_CHANGED",
  "target": {"type": "USER", "id": "u-42"},
  "change": {
    "fields": ["recoveryEmail"],
    "oldValueRecorded": false,
    "newValueRecorded": false
  },
  "outcome": "COMMITTED"
}
~~~

Nếu điều tra bắt buộc cần đối chiếu một giá trị định danh mà không thấy giá trị gốc, cân nhắc **HMAC-SHA-256 có secret do KMS quản lý**, kèm key ID/version để xoay khóa. **SHA-256 không khóa** của email/số điện thoại có entropy thấp thường có thể bị đoán bằng từ điển. HMAC vẫn tạo **pseudonymous personal data** có thể liên kết người dùng giữa các event, không biến dữ liệu thành “vô danh tuyệt đối”; kiểm soát mục đích và quyền truy cập tương ứng.

**Mã hóa có thể giải mã** chỉ phù hợp nếu thật sự phải phục hồi giá trị để đáp ứng yêu cầu hợp pháp, với quyền tách biệt, envelope encryption và logging truy cập khóa. Không dùng “đã mã hóa” làm lý do lưu mọi secret. Khi xoay hoặc hủy khóa, phải hiểu ảnh hưởng đến khả năng tra cứu/giải mã sự kiện cũ.

### Chống log injection

Bất kỳ **reason, User-Agent, path, externalRef** nào cũng có thể chứa newline, control characters, ký tự bất thường hoặc JSON giả. Ghi **structured JSON bằng serializer** với độ dài giới hạn, escape đúng; không nối chuỗi raw thành nhiều dòng log dễ giả mạo. Với export CSV, áp chính sách chống formula injection riêng. Nếu dùng log pipeline đẩy sang SIEM, cấu hình trường nào được index để tránh lộ dữ liệu trong hệ thống tìm kiếm.

## 7. Bài toán nhất quán: database commit và audit phải đi cùng nhau

Một sai lầm thường gặp:

~~~java
roleRepository.save(role);
log.info("ROLE_GRANTED ...");          // Không bảo đảm audit bền vững
auditPublisher.send(event);            // Có thể lỗi sau khi DB commit
~~~

Tình huống xấu:

1. Database commit thành công nhưng process crash trước khi gửi event → **thiếu audit**.
2. Event được gửi trước khi transaction commit; DB rollback → **audit nói thành công giả**.
3. Broker nhận event nhưng ACK về publisher mất; publisher gửi lại → **duplicate event**.
4. Request retry sau timeout tạo nhiều event nếu không phân biệt **attempt** với **state change**.

Với thay đổi nhạy cảm, chọn mô hình **transactional outbox**: ghi thay đổi nghiệp vụ **và** một record audit/outbox trong **cùng transaction database**.

~~~mermaid
flowchart TD
  A[HTTP POST /role-assignments] --> B[Authentication + authorization]
  B --> C[DB transaction]
  C --> D[Kiểm tra tenant và precondition]
  D --> E[Ghi role assignment]
  E --> F[Ghi audit outbox cùng transaction]
  F --> G{Commit thành công?}
  G -->|Không| H[Rollback cả nghiệp vụ và outbox]
  G -->|Có| I[HTTP success]
  I --> J[Outbox relay đọc record đã commit]
  J --> K[Broker / Audit sink]
  K --> L[Consumer idempotent theo eventId]
~~~

**Bảo đảm chính xác:** nếu thay đổi và outbox cùng nằm trong một DB transaction có ACID phù hợp, **cả hai cùng commit hoặc cùng rollback**. Relay có thể chuyển **at-least-once**, vì vậy sink phải de-duplicate theo eventId. **Không hứa exactly-once end-to-end** chỉ vì đã có outbox.

Một audit sink tách biệt có thể cập nhật trễ. Do đó phải có monitoring **oldest unpublished event, queue lag, retry count, dead-letter, reconciliation**. Tùy chính sách, DB outbox có thể là bản ghi bền vững đầu tiên của audit; cần kế hoạch archival/retention sau khi consumer xác nhận chứ không xóa sớm chỉ vì đã cố gửi.

### Vì sao afterCommit callback chưa đủ?

Sử dụng TransactionSynchronization.afterCommit để gửi audit sang broker **không tự biến việc gửi thành durable**. Process có thể chết ngay sau DB commit nhưng trước callback, làm mất event. Callback chỉ hợp lý nếu có một cơ chế ghi nhận bền vững khác hoặc hoạt động được phép best-effort.

### Nếu storage audit lỗi thì sao?

Định nghĩa **failure policy theo loại thao tác**:

- Với **ROLE_GRANTED, API_KEY_REVOKED, REFUND_APPROVED** cần audit bắt buộc, nếu không thể ghi audit outbox **trong transaction** thì rollback và không trả thành công.
- Với **debug telemetry** hoặc một số request-denied signal không ảnh hưởng trạng thái, có thể dùng queue bền vững/giới hạn hoặc best-effort theo threat model; phải đo mất sự kiện và không che lỗi.
- Nếu sink SIEM tạm ngừng nhưng outbox đã commit, API có thể tiếp tục theo chính sách khi **backlog còn an toàn**, rồi cảnh báo/sửa relay. Nếu outbox đầy hoặc khả năng lưu trữ không đảm bảo, policy có thể chuyển **fail closed** cho thao tác nhạy cảm.

Không khóa thread HTTP để chờ kho log từ xa không có giới hạn; tăng độ trễ, vòng phụ thuộc và nguy cơ gián đoạn toàn hệ thống.

## 8. Java/Spring: ghi role và outbox trong cùng transaction

Ví dụ service cấp role cho user trong tenant, với controller trả 204 khi transaction thành công. Chỉ record **vai trò đã cấp**, không ghi token, email hoặc bản dump user entity.

~~~java
public record GrantRoleRequest(
    @NotBlank String role,
    @NotBlank String reasonCode
) {}

@RestController
@RequestMapping("/api/v1/users")
class RoleAssignmentController {
    private final RoleGrantService roles;

    RoleAssignmentController(RoleGrantService roles) {
        this.roles = roles;
    }

    @PostMapping(
        path = "/{userId}/role-assignments",
        consumes = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<Void> grant(
            @PathVariable String userId,
            @Valid @RequestBody GrantRoleRequest command,
            @RequestHeader("If-Match") String ifMatch,
            Authentication authentication) {

        roles.grant(userId, command, ifMatch, authentication);
        return ResponseEntity.noContent()
            .cacheControl(CacheControl.noStore())
            .build();
    }
}
~~~

Service minh họa (repository, policy và event factory là abstraction của ứng dụng):

~~~java
@Service
class RoleGrantService {
    private final AccountRepository accounts;
    private final RoleAssignmentRepository assignments;
    private final AuditOutboxRepository outbox;
    private final TenantPolicy tenantPolicy;
    private final RevisionPreconditions preconditions;
    private final AuditEventFactory eventFactory;

    RoleGrantService(
            AccountRepository accounts,
            RoleAssignmentRepository assignments,
            AuditOutboxRepository outbox,
            TenantPolicy tenantPolicy,
            RevisionPreconditions preconditions,
            AuditEventFactory eventFactory) {
        this.accounts = accounts;
        this.assignments = assignments;
        this.outbox = outbox;
        this.tenantPolicy = tenantPolicy;
        this.preconditions = preconditions;
        this.eventFactory = eventFactory;
    }

    @Transactional
    @PreAuthorize("hasAuthority('SCOPE_users:roles:write')")
    public void grant(
            String userId, GrantRoleRequest input,
            String ifMatch, Authentication caller) {

        String tenantId =
            tenantPolicy.requireAuthorizedTenant(caller);
        Account target = accounts
            .findByTenantIdAndPublicIdForUpdate(tenantId, userId)
            .orElseThrow(() -> new ResponseStatusException(
                HttpStatus.NOT_FOUND));

        preconditions.requireMatches(
            ifMatch, target.securityRevision());

        String role = tenantPolicy.requireGrantableRole(
            caller, target, input.role());
        String reason =
            tenantPolicy.requireAllowedReason(input.reasonCode());

        if (assignments.existsFor(target, role)) {
            return; // Không có state change; idempotency/attempt audit theo policy.
        }

        assignments.save(
            RoleAssignment.newGrant(tenantId, target, role));
        target.advanceSecurityRevision();

        AuditEvent event = eventFactory.roleGranted(
            caller, tenantId, userId, role, reason);

        outbox.save(AuditOutboxEntity.from(event));
        // Cùng transaction: hoặc cả role và outbox commit,
        // hoặc cả hai bị rollback.
    }
}
~~~

**Các lớp Account, RoleAssignment, AuditEvent và repositories là skeleton** cần cài đặt. Repository **findByTenantIdAndPublicIdForUpdate** phải có lock/consistency phù hợp, unique constraint trên **(tenant_id, user_id, role)** và kiểm soát concurrency thật. **RevisionPreconditions** chuyển If-Match không khớp thành **412**, không tự gán 409 nếu có HTTP precondition.

Spring phải bật **@EnableMethodSecurity**, security filter chain phải xác thực JWT/Bearer đúng scope, và transaction proxy phải áp dụng khi gọi service qua Spring bean. Controller không bao giờ đọc **tenantId từ body**, cũng không nhận reason tùy ý không qua validation. Nếu dùng **@Version** của JPA, việc tăng revision và format ETag phải nhất quán với version thực tế; đừng tự sửa field do JPA quản lý mà không kiểm thử.

Một **eventId** phải được tạo trong cùng command, outbox có unique constraint; publisher và consumer dùng eventId để de-duplicate. Khi role đã tồn tại, service không ghi ROLE_GRANTED giả: có thể ghi **ROLE_GRANT_NOOP** ở kênh audit attempt hoặc định nghĩa phản hồi 409 theo hợp đồng. Retry cùng **Idempotency-Key** và payload nên dẫn tới cùng kết quả đã ghi nếu server công bố idempotency.

## 9. Relay outbox, de-duplicate và đối soát

Một outbox relay định kỳ đọc các record **đã commit**, gửi sang broker/audit sink, rồi đánh dấu đã chuyển. Có thể dùng poller hoặc CDC (change data capture); cách nào cũng phải xử lý restart, lỗi broker và event bị gửi lại.

~~~text
1. Chọn một batch record PENDING với lock/lease.
2. Publish eventId + payload đã kiểm tra schema.
3. Broker xác nhận nhận thành công.
4. Mark PUBLISHED hoặc ghi checkpoint bền vững.
5. Nếu crash giữa bước 3–4, publish lại cùng eventId.
6. Sink INSERT theo unique(eventId), bỏ event trùng an toàn.
~~~

Nếu dùng PostgreSQL với nhiều relay worker, có thể dùng **FOR UPDATE SKIP LOCKED** và cơ chế claim/lease được thiết kế cẩn thận để tránh tranh cùng record. Không giữ DB transaction mở khi chờ network dài; chọn mô hình claim + timeout phù hợp và xử lý lease hết hạn. Đừng xóa outbox ngay khi call publish được gửi nhưng chưa nhận ACK; điều đó có thể làm mất audit.

**Ordering:** event theo hai resource khác nhau không nhất thiết cần thứ tự toàn cục. Với cùng target, cần sequence/version nếu việc điều tra yêu cầu biết thứ tự ROLE_GRANTED rồi ROLE_REVOKED. Một event đến muộn không được làm consumer viết lại timeline theo **recordedAt** rồi nhầm là thời gian nghiệp vụ. Lưu cả event time, ingestion time và per-aggregate revision/sequence khi cần.

**Idempotency:** eventId giúp sink de-duplicate; một command retry có thể tạo **operationId** giống nhau nhưng requestId khác. Unique business constraint và Idempotency-Key xử lý trùng thao tác nghiệp vụ, **khác với** de-duplicate sự kiện audit ở broker.

Đo các chỉ số: **oldest pending age**, outbox backlog, publish error rate, sink lag, duplicate count, checksum failures. Thiết lập cảnh báo và quy trình replay/DLQ có quyền riêng; replay không được âm thầm thay nội dung sự kiện gốc.

## 10. HTTP status và audit outcome phải đúng thực tế

| HTTP tình huống | Audit đúng nên phản ánh |
| --- | --- |
| **200/201/204** sau commit | State change COMMITTED và outbox bền vững; response không cần mang audit body |
| **202 Accepted** | JOB_ACCEPTED; chỉ ghi JOB_COMPLETED khi worker hoàn tất thật |
| **400/422** validation | INPUT_REJECTED theo policy, không lưu body sai chứa PII |
| **401** thiếu/sai token | AUTHENTICATION_FAILED nếu policy yêu cầu, có sampling/rate control chống flood |
| **403** thiếu quyền | ACCESS_DENIED với actor đã xác minh, không giả là thay đổi thành công |
| **404** ngoài tenant/phạm vi | Có thể ghi access denial nội bộ; không tiết lộ target thực sự tồn tại |
| **409** business conflict | CONFLICT hoặc NOOP; không ghi ROLE_GRANTED nếu không thay đổi |
| **412** If-Match không khớp | PRECONDITION_FAILED, không ghi state change |
| **429/503** quota hoặc outage | REJECTED/FAILED theo nguyên nhân, kiểm tra xem transaction có từng commit không |
| **Network reset sau commit** | HTTP client không nhận được response nhưng audit COMMITTED vẫn đúng; retry cần idempotency |

**Mã status không đủ để kết luận transaction đã commit** nếu hệ thống có nhiều bước và side effects. Trạng thái audit phải dựa trên nguồn chân lý nghiệp vụ. Đối với POST có Idempotency-Key, định nghĩa cùng key/payload được replay thế nào, event state change chỉ tạo một lần; một request lặp có thể vẫn có access log riêng.

### Lỗi từ Spring Security nằm trước MVC

**AuthenticationEntryPoint** và **AccessDeniedHandler** của Spring Security xử lý nhiều trường hợp 401/403 trước controller. Chỉ thêm **@RestControllerAdvice** không đủ để ghi toàn bộ security denials. Dùng event handler/filter có kiểm soát và tránh blocking đồng bộ trên mỗi token sai; **không ghi raw Authorization** hay JWT vào sự kiện. Nếu ghi request path, chuẩn hóa endpoint template hoặc giới hạn độ dài để chống spoofing/PII.

## 11. Chống sửa, xóa và giả mạo audit

Audit dùng để điều tra hành vi có đặc quyền; vì vậy **người có quyền sửa nghiệp vụ không nên đồng thời có quyền xóa audit**. Dùng defense in depth:

1. **Append-only** đối với event đã commit. User/app role chỉ được INSERT; quyền UPDATE/DELETE/DDL trong sink dành cho quy trình quản trị độc lập và được giám sát.
2. **Separation of duties:** vận hành kho audit, truy vấn dữ liệu, thay đổi chính sách retention và xoay khóa thuộc các quyền tách biệt; thao tác quản trị audit **cũng phải được audit**.
3. **Object lock/WORM hoặc immutable storage** theo tính năng nhà cung cấp và chính sách retention; không chỉ đặt tên bucket là “immutable”.
4. **TLS khi truyền**, mã hóa at rest bằng KMS, giới hạn quyền decrypt; kiểm tra backup, restore và replication.
5. **Integrity verification** để phát hiện sự kiện bị sửa/xóa/đổi thứ tự; giám sát việc xác minh định kỳ và đóng dấu thời gian.
6. **Đường thu thập dự phòng** để sự cố logging không âm thầm làm biến mất tất cả sự kiện security.

### Hash chain, HMAC và giới hạn bằng chứng

Một chuỗi integrity theo thứ tự xác định có thể tính:

~~~text
payload_i = canonicalSerialize(event_i)
mac_i = HMAC_SHA256(K, mac_(i-1) || sequence_i || payload_i)
record = {sequence_i, keyVersion, payload_i, mac_i}
~~~

**K** là secret key từ KMS, còn **keyVersion** chỉ là định danh để tìm đúng khóa khi xác minh, không thay thế khóa. Ghi sequence, key ID và anchor/checkpoint tới một miền quản trị độc lập. Xác minh lại theo thứ tự để phát hiện sửa, mất hoặc đảo event; canonical serialization bảo đảm cùng event có cùng bytes.

**Hash chain không làm log “không thể giả mạo”** nếu attacker có quyền thay toàn bộ chain lẫn khóa hoặc anchor. Chữ ký/HMAC, WORM, phân quyền và anchor ngoài miền quản trị phải được thiết kế cùng nhau. Khóa HMAC dùng cho integrity **khác** khóa dùng HMAC pseudonymization của email, và **khác** khóa mã hóa payload. Có quy trình key rotation, phục hồi khóa, xác minh audit cũ và ứng phó khi khóa bị lộ.

Không dùng một hash chain toàn cục như khóa đồng bộ cổ chai nếu throughput lớn; có thể phân vùng theo tenant/stream, nhưng phải định nghĩa ranh giới sequence và checkpoint. Nếu audit sink hỗ trợ immutable ledger, vẫn cần kiểm chứng các lời hứa về integrity/retention bằng test và quyền vận hành.

## 12. Quyền đọc audit, tìm kiếm và export

Kho audit có thể nhạy cảm hơn chính resource gốc: một operator có thể thấy **ai làm gì**, target IDs, mô hình sử dụng và sự kiện bảo mật. Không đặt endpoint audit chỉ vì người dùng đã có SCOPE_orders:read.

Ví dụ API nội bộ:

~~~http
GET /api/v1/security/audit-events?targetType=USER&targetId=u-42&limit=50 HTTP/1.1
Authorization: Bearer <audit-reader-token>
Accept: application/json
~~~

Thiết kế:

- Scope/role riêng như **SCOPE_audit:read** và **quyền tenant**; admin của tenant A không đọc event tenant B.
- Policy **purpose-based access** cho investigation, compliance hoặc support; với audit rất nhạy cảm có thể yêu cầu phê duyệt hai người.
- Filter theo tenant **trong truy vấn**, trước paging/count. Limit, cursor và thời gian tìm kiếm có giới hạn; không cho scan toàn bộ bảng tùy tiện.
- Response chỉ có field thuộc **read projection** được phép; audit raw payload nội bộ và thông tin pseudonymized chưa chắc phù hợp mọi reader.
- Mọi thao tác **xem, export, download, thay đổi quyền đọc audit** cần có audit event riêng. Tránh vòng lặp vô hạn khi việc ghi audit cho truy vấn audit lại bị audit đệ quy.
- Export cần watermark/expiry, encryption và kiểm soát truy cập, không gửi link ký dài hạn qua log/query. Nếu tạo 202 job, kiểm tra quyền khi tải kết quả.
- Tránh đưa audit vào public CDN/cache chung; **Cache-Control: no-store** phù hợp cho response nhạy cảm.

Không xây UI “truy vấn mọi request raw JSON” mặc định. Cấu trúc audit ổn định giúp lọc theo **eventType, tenant, actor, target, time range, outcome, operationId** với index và quyền có giới hạn.

### Hợp đồng OpenAPI cho thao tác được audit

~~~yaml
openapi: 3.1.0
info: { title: User Roles API, version: 1.0.0 }
paths:
  /api/v1/users/{userId}/role-assignments:
    post:
      summary: Cấp role; lưu audit trong transaction
      description: Cần quyền users:roles:write và quyền trên tenant/target.
      security:
        - bearerAuth: []
      parameters:
        - in: path
          name: userId
          required: true
          schema: { type: string }
        - in: header
          name: If-Match
          required: true
          schema: { type: string }
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              additionalProperties: false
              required: [role, reasonCode]
              properties:
                role: { type: string }
                reasonCode: { type: string }
      responses:
        '204': { description: Đã commit; không có body }
        '400': { description: Dữ liệu hoặc header không hợp lệ }
        '401':
          description: Chưa xác thực
          headers:
            WWW-Authenticate:
              schema: { type: string }
        '403': { description: Không có quyền }
        '404': { description: Target ngoài phạm vi có thể xem }
        '412': { description: If-Match không còn khớp }
components:
  securitySchemes:
    bearerAuth: { type: http, scheme: bearer }
~~~

OpenAPI mô tả **hợp đồng HTTP**, không tự ghi audit, không thay kiểm tra scope/tenant, và không thể chứng minh sự kiện đã được commit. Thực thi cùng kiểm thử mới bảo đảm ba trách nhiệm đó.

## 13. Retention, xóa dữ liệu và đối soát quyền riêng tư

**Giữ dữ liệu càng lâu càng không mặc nhiên tốt.** Xác định retention theo loại event, risk, mục đích điều tra, hợp đồng, nghĩa vụ pháp lý và chính sách bảo vệ dữ liệu đang áp dụng. Không tự chọn một thời hạn duy nhất rồi khẳng định mọi ngành/khu vực đều tuân thủ.

| Vấn đề | Cách quyết định |
| --- | --- |
| **Lưu bao lâu?** | Policy per category/tenant/system, có người phê duyệt và ghi version |
| **Bắt đầu đếm từ đâu?** | occurredAt hay thời điểm đóng hồ sơ, được định nghĩa rõ |
| **Legal hold** | Tạm dừng xóa theo yêu cầu hợp lệ, kiểm soát quyền bật/tắt và audit thao tác |
| **Yêu cầu xóa dữ liệu cá nhân** | Đánh giá nghĩa vụ lưu giữ hợp pháp, minimization và pseudonymization; không hứa xóa dữ liệu bắt buộc lưu |
| **Backup và replica** | Retention/deletion bao phủ bản sao, index, export và recovery policies |
| **Hết hạn khóa mã hóa** | Có thể hỗ trợ crypto-shredding, nhưng xem xét ảnh hưởng đến audit integrity/khả năng xác minh |
| **Xóa dữ liệu trong WORM** | Kiểm tra đặc tính retention cố định của lưu trữ trước khi ghi; tránh rơi vào xung đột không thể xử lý |

Đánh giá **privacy impact** khi mở thêm trường audit. Không cho phép “dữ liệu đã vào audit nên không bao giờ phải kiểm tra yêu cầu xóa/giới hạn truy cập”. Với dữ liệu pseudonymized vẫn có thể liên kết cá nhân, tiếp tục áp biện pháp kiểm soát tương ứng.

## 14. Kiểm thử audit: kiểm cả dữ liệu, HTTP và quyền

**Mock service trả 204 không chứng minh audit đã được commit.** Test nên có ba lớp: **MockMvc/Spring Security** cho request–response và authority, **integration database** cho transaction/outbox, **relay/sink test** cho at-least-once, integrity và retention. Với Spring Boot 3.x, có thể dùng PostgreSQL trong Testcontainers để thấy đúng hành vi unique constraint/commit.

Ví dụ skeleton kiểm thử thành công:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class RoleAuditIntegrationTest {
    @Autowired MockMvc mvc;
    @Autowired AuditOutboxRepository outbox;

    @Test
    void grantedRoleHasOneCommittedAuditEvent() throws Exception {
        mvc.perform(post("/api/v1/users/u-42/role-assignments")
                .with(jwt()
                    .jwt(j -> j.subject("sub-admin")
                        .claim("tenant_id", "tenant-a"))
                    .authorities(
                        new SimpleGrantedAuthority(
                            "SCOPE_users:roles:write")))
                .header("If-Match", "\"user-42-v7\"")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"role":"REFUND_APPROVER",
                     "reasonCode":"SUPPORT_ESCALATION"}
                    """))
            .andExpect(status().isNoContent());

        assertThat(outbox.countByEventTypeAndTargetId(
            "ROLE_GRANTED", "u-42")).isEqualTo(1);
    }
}
~~~

Ví dụ cần test fixtures: user u-42 thuộc tenant-a ở revision v7, admin có quyền grant theo domain policy, repository method kiểm đếm và PostgreSQL test thật. **jwt() từ spring-security-test giả lập authentication**, không xác minh chữ ký/issuer/audience; test resource server thật phải bổ sung token đã ký và mock JWKS/introspection theo security setup.

### Ma trận kiểm thử bắt buộc

| Trường hợp | Điều phải xác minh |
| --- | --- |
| POST hợp lệ, commit thành công | 204, role được cấp và **một** outbox event ROLE_GRANTED |
| Caller thiếu token/scope | 401/403; **không** có role change hay ROLE_GRANTED |
| User thuộc tenant khác | 404/403 theo policy, không lộ target hoặc ghi thay đổi |
| If-Match cũ | 412, không có event COMMITTED |
| Invalid reason/role | 400/422 theo contract, không phát event sai |
| Ghi audit outbox lỗi | **Cả transaction rollback**, không có role change |
| Transaction nghiệp vụ rollback | Không còn outbox event COMMITTED mồ côi |
| Sink bị ngắt lúc publish | Outbox vẫn bền vững; relay retry, không mất event |
| ACK mất sau khi broker đã nhận | Cùng eventId có thể gửi lại, sink de-duplicate |
| Hai POST đồng thời cấp một role | Unique constraint, một state change và audit tương ứng |
| Authorization và token trong log | Không có Authorization, token, password hoặc DTO dump |
| Audit query từ tenant B | Không truy vấn được event tenant A |
| Thay đổi schema/retention | Event cũ vẫn parse được; quyền export/xóa được audit |
| HMAC integrity / object tampering | Sửa/xóa/reorder một event bị phát hiện trong phạm vi kiểm soát |

Không đặt **@Transactional trên toàn test method** rồi lầm tưởng đã kiểm tra commit thực: test transaction có thể rollback sau test, làm che lỗi phát sinh lúc commit. Với business-critical audit, tạo transaction thật ở API/service boundary và kiểm tra trạng thái sau request. Test publisher retry, poison message và DLQ bằng cách kiểm soát lỗi broker/sink, không chỉ mock phương thức send() trả success.

## 15. Bài tập: duyệt hoàn tiền và thu hồi API key

Thiết kế hai endpoint bảo mật của hệ thống thương mại:

~~~http
POST /api/v1/refunds/ref-501/approvals HTTP/1.1
Authorization: Bearer <admin-token>
Content-Type: application/json
Idempotency-Key: approve-ref-501-v1
If-Match: "refund-501-v3"

{"reasonCode":"DOCUMENTS_VERIFIED"}
~~~

~~~http
DELETE /api/v1/api-keys/key-312 HTTP/1.1
Authorization: Bearer <owner-token>
If-Match: "key-312-v2"
~~~

Yêu cầu: duyệt hoàn tiền phải có quyền theo tenant và giới hạn số tiền; thu hồi API key không được ghi secret. Cả hai thao tác cần audit bền vững theo kết quả COMMITTED, không được log request token, số thẻ hay thông tin định danh không cần thiết.

Nhiệm vụ:

1. Lập **threat model**: ai có thể sửa nghiệp vụ, ai có thể truy cập audit, đâu là bí mật/PII và đường tấn công log injection.
2. Viết **event schema** có eventId, actor, tenant, target, eventType, outcome, timestamp, requestId/operationId và schemaVersion; định nghĩa allowlist field cho từng event.
3. Thiết kế transaction ghi thay đổi + **audit outbox**, unique business constraint và eventId de-duplication; phân biệt 204/201, 202, 403, 409, 412 và network timeout.
4. Viết Java/Spring controller/service sử dụng @Transactional và @PreAuthorize, lấy actor/tenant từ principal đã xác minh, không từ JSON body.
5. Thiết kế poller/CDC relay sang kho audit, retry có giới hạn, cảnh báo backlog, replay an toàn và cơ chế kiểm tra integrity.
6. Chọn chính sách retention, legal hold, key management và quyền đọc/export theo role, tenant, mục đích.
7. Viết tối thiểu **10 test** gồm HTTP, authorization hai tenant, transaction rollback, duplicate retry, broker outage, redaction, tamper evidence và export authorization.
8. Mô tả một sự cố giả định: database commit thành công nhưng broker ACK mất; trình bày cách xác minh không mất event hoặc nhân đôi sự kiện nghiệp vụ.

**Đầu ra:** hợp đồng HTTP, Java/Spring skeleton, audit schema, outbox DB, threat model, ma trận kiểm thử và quyết định bảo mật/retention.

## 16. Checklist và kết luận

Trước khi vận hành một audit trail cho REST API:

- **Đúng nghiệp vụ:** phân biệt REQUESTED, DENIED, COMMITTED, FAILED và async completion.
- **Đúng danh tính:** actor/tenant/scope lấy từ nguồn tin cậy, service delegation rõ.
- **Ít dữ liệu:** event theo allowlist, không raw token, mật khẩu, PII, request/response dump.
- **Đúng transaction:** state change và outbox cùng commit, replay at-least-once với eventId de-dup.
- **Đúng quyền:** người sửa nghiệp vụ không tự do sửa/xóa audit; read/export phải được bảo vệ và ghi lại.
- **Đúng toàn vẹn:** append-only/WORM khi cần, integrity anchors, key rotation, monitor tampering.
- **Đúng vòng đời:** retention, legal hold, backup, deletion và privacy policy được phê duyệt.
- **Đúng vận hành:** quan sát lag/backlog/failure, có replay và fail-closed policy cho thao tác nhạy cảm.
- **Đúng kiểm thử:** HTTP status, Spring Security, transaction rollback, tenant isolation và broker failure.

**Kết luận:** Audit log không chỉ là một câu log sau khi controller gọi service. Nó là **hợp đồng sự kiện đáng tin, có tính tối thiểu và gắn với trạng thái nghiệp vụ đã commit**. Thiết kế tốt giúp trả lời ai đã thay đổi điều gì, khi nào và có thực sự thành công không, trong khi vẫn bảo vệ credential, dữ liệu cá nhân và quyền truy cập của từng tenant.







