# Credential access audit: kiểm toán truy cập credential

> **Chương:** Lưu trữ credential  
> **Phạm vi:** Module **SECURITY_AUTHENTICATION_FUNDAMENTALS** tìm hiểu nguyên lý xác thực danh tính từ credential, mật khẩu, MFA, passkey và chứng chỉ đến token, phiên, liên kết danh tính và khôi phục tài khoản. Bài này tập trung vào kiểm toán việc truy cập và sử dụng credential: ai hoặc workload nào đã đọc, tạo, thay đổi, sử dụng hay thu hồi secret; làm sao ghi nhận bằng chứng mà không đưa chính secret vào log; và cách phát hiện, điều tra hành vi truy cập bất thường.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích mục đích và phạm vi của credential access audit.
2. Phân biệt audit event với application log, authentication log và business transaction log.
3. Xác định các sự kiện cần ghi nhận khi truy cập secret manager, vault, KMS, HSM và credential registry.
4. Thiết kế event schema có actor, subject, workload, resource, action, outcome và correlation ID.
5. Ghi nhận secret access mà không log password, API key, token, private key hoặc OTP.
6. Áp dụng least privilege, separation of duties, dual control và break-glass audit.
7. Bảo vệ tính toàn vẹn, khả năng truy xuất và retention của audit trail.
8. Phát hiện truy cập bất thường, secret enumeration, bulk export và privilege misuse.
9. Triển khai audit event trong Java/Spring và xây dựng ma trận kiểm thử.

## 2. Credential access audit là gì?

**Credential access audit** là việc ghi nhận có cấu trúc các hành động liên quan tới credential và nơi lưu trữ credential, để có thể trả lời:

- Ai hoặc workload nào đã yêu cầu truy cập?
- Họ truy cập credential/resource nào?
- Hành động là read, create, update, rotate, disable hay revoke?
- Request được cho phép hay bị từ chối?
- Hành động xảy ra lúc nào, từ workload/client nào và theo request/change nào?
- Quyền truy cập được cấp bởi policy hoặc approval nào?
- Credential có được sử dụng, export hoặc thay thế sau đó không?

Audit không có nghĩa ghi lại giá trị secret. Mục tiêu là ghi lại **bằng chứng về hành động và ngữ cảnh**, đủ để phát hiện và điều tra nhưng không biến log thành một kho credential thứ hai.

Ví dụ, secret manager ghi nhận workload payment-api đọc phiên bản 7 của secret dùng cho payment provider, request được cho phép bởi policy workload-payment-prod, kết quả thành công, nhưng không ghi plaintext secret.

## 3. Vì sao credential access cần audit riêng?

Credential thường là tài sản có khả năng mở quyền truy cập trực tiếp. Nếu password, API key, client secret, private key hoặc refresh token bị lộ, attacker có thể hành động dưới danh tính của chủ thể hợp lệ.

Các rủi ro cần quan sát:

- Developer đọc secret production ngoài nhiệm vụ.
- Workload đọc hàng loạt secret không thuộc phạm vi.
- Credential bị export hoặc copy sang môi trường khác.
- Admin dùng quyền break-glass nhưng không có ticket hoặc approval.
- Secret cũ vẫn được đọc sau khi đã rotate.
- Một service account truy cập secret vào thời điểm không bình thường.
- Người dùng bị offboard nhưng credential access vẫn tiếp tục.
- Attacker thử liệt kê tên secret hoặc dò key ID.
- Kẻ tấn công thay policy hoặc tạo secret mới để duy trì persistence.

Authentication log có thể cho biết một principal đã đăng nhập. Credential access audit cho biết principal đó đã làm gì với tài sản xác thực sau khi đăng nhập. Hai loại log bổ sung cho nhau.

## 4. Phân biệt các loại log

| Loại log | Ghi nhận điều gì? | Ví dụ |
|---|---|---|
| Authentication log | Kết quả xác minh danh tính | User đăng nhập bằng passkey |
| Authorization decision log | Quyết định allow/deny | Workload được phép đọc secret X |
| Credential access audit | Hành động lên credential hoặc secret store | Secret version 7 được đọc |
| Application log | Trạng thái xử lý kỹ thuật | Client khởi tạo kết nối tới payment provider |
| Business audit | Hành động nghiệp vụ | Người dùng phê duyệt khoản thanh toán |
| Infrastructure audit | Thay đổi hạ tầng/control plane | Policy vault hoặc KMS key được sửa |

Một sự kiện có thể liên kết nhiều loại log bằng correlation ID, trace ID hoặc operation ID. Không sao chép raw token/cookie/private key giữa các hệ thống chỉ để tương quan.

## 5. Tài sản và bề mặt cần kiểm toán

Credential access audit cần bao phủ cả nơi lưu secret và các đường quản lý nó:

| Tài sản/bề mặt | Hành động cần quan sát |
|---|---|
| Password verifier store | Tạo/cập nhật verifier, reset, disable account |
| Secret manager/vault | Read, write, list, export, version, delete |
| KMS/HSM | Sign, decrypt, unwrap, key creation, disable, rotation |
| Certificate authority | Issue, renew, revoke, export certificate metadata |
| API key registry | Create, reveal-once, verify, rotate, revoke |
| TOTP store | Create pending seed, activate, replace, revoke |
| Passkey registry | Register, rename metadata, disable, remove credential |
| OAuth token store | Issue, exchange, refresh, revoke, introspect |
| Recovery service | Create grant, consume, cancel, expire |
| Backup/archive | Snapshot, restore, export và truy cập backup |
| Policy/control plane | Grant role, sửa ACL, thay policy, đổi trust configuration |

Không phải mọi hệ thống đều có thể audit từng lần private key được sử dụng ở bên trong secure hardware. Khi đó cần ghi nhận các thao tác mà provider hỗ trợ, ví dụ key handle, operation type, caller identity, result và policy decision.

## 6. Actor, subject và resource trong audit event

Một event cần phân biệt người gọi, danh tính được đại diện và credential bị tác động:

- **Actor:** user, service hoặc admin trực tiếp gửi request.
- **Subject:** account/client/workload mà hành động được thực hiện thay mặt.
- **Workload identity:** service/process đã xác thực ở tầng kết nối.
- **Resource:** secret, key, certificate, token family hoặc credential record.
- **Action:** read, list, create, update, rotate, revoke, sign, decrypt hoặc export.
- **Outcome:** allowed, denied, failed, pending hoặc partial.
- **Context:** environment, tenant, client, request ID, policy version và approval.

Ví dụ:

~~~text
event_type = credential.secret.read
actor = workload:payment-api
subject = service-account:payment-prod
resource_id = secret://prod/payment/provider-key
resource_version = 7
action = READ
outcome = ALLOWED
environment = production
policy_id = workload-payment-prod
request_id = req-7a12
timestamp = server-generated-time
~~~

Không dùng secret value làm resource ID. Resource identifier nên là tên logic hoặc ID nội bộ không chứa secret.

### Delegated access

Nếu admin thao tác thay user hoặc service gọi vault thay workload khác, audit cần ghi actor và subject riêng. Nếu chỉ ghi subject, điều tra viên có thể không biết ai thực sự thực hiện hành động.

## 7. Những event nào cần ghi?

### 7.1. Read và use

- Secret read/get.
- Secret version read.
- Key sign/decrypt/unwrap operation.
- Certificate/private-key operation nếu provider cung cấp event.
- Token refresh hoặc exchange.
- Recovery code verification.
- Credential verification thất bại hoặc bị từ chối.

### 7.2. Lifecycle

- Credential requested, created và activated.
- Secret version created/updated.
- Rotation started/completed/failed.
- Credential suspended, revoked, expired hoặc replaced.
- Recovery grant issued/consumed/cancelled.
- Certificate issued/renewed/revoked.
- API key revealed once hoặc activation completed.

### 7.3. Governance và administration

- Policy/ACL changed.
- Role/group membership changed.
- Secret permission granted/removed.
- KMS key policy changed.
- Break-glass started/ended.
- Dual approval requested/approved/denied.
- Audit sink, retention hoặc export configuration changed.

### 7.4. Failure và anomaly

- Access denied.
- Unknown secret ID.
- Invalid key handle.
- Expired/revoked credential used.
- Rate limit exceeded.
- Bulk list/export attempted.
- Approval missing or expired.
- Audit delivery failure.

Không chỉ ghi successful read. Những lần bị từ chối có thể là tín hiệu quan trọng của enumeration, privilege probing hoặc credential misuse.

## 8. Metadata nào nên có trong event?

Một schema thực tế có thể gồm:

| Field | Mục đích |
|---|---|
| event_id | ID duy nhất của event |
| event_type | Loại hành động |
| occurred_at | Thời điểm do hệ thống đáng tin tạo |
| actor_id | Danh tính actor |
| subject_id | Danh tính được đại diện |
| workload_id | Workload/client đã xác thực |
| tenant_id | Tenant context đã xác minh |
| resource_id | ID logic của credential/secret |
| resource_version | Phiên bản secret/key/certificate |
| action | Read/write/rotate/revoke/sign/decrypt |
| outcome | Allowed/denied/failed/partial |
| reason_code | Lý do theo policy |
| policy_id/version | Policy quyết định |
| source_service | Service phát sinh event |
| request_id/trace_id | Tương quan request |
| approval_id | Liên kết phê duyệt nếu có |
| environment | Dev/staging/production |

Timestamp phải được tạo ở server hoặc nguồn thời gian được quản lý. Client không được tự khai thời gian để làm bằng chứng duy nhất. Đồng hồ hệ thống cần được đồng bộ và drift được giám sát.

## 9. Không bao giờ đưa secret vào audit log

Các dữ liệu không được ghi vào audit event:

- Plaintext password hoặc password reset secret.
- API key, client secret hoặc database password.
- Access token, refresh token, ID token hoặc authorization code.
- Session cookie, bearer token hoặc Authorization header.
- Private key, seed phrase hoặc recovery code.
- TOTP seed, provisioning URI hoặc QR code chứa seed.
- Nội dung request/response có thể chứa credential.
- Secret được giải mã hoặc giá trị trả về từ vault.

Thay thế bằng metadata:

- Secret ID/key ID.
- Version.
- Credential type.
- Operation type.
- Caller identity.
- Result và reason code.
- Approval/change ticket reference.

Không hash secret rồi ghi hash vào log một cách tùy tiện. Hash có thể trở thành dữ liệu nhạy cảm cho phép correlation hoặc kiểm tra đoán đối với secret entropy thấp. Dùng opaque resource ID hoặc keyed identifier do hệ thống quản lý nếu cần correlation.

## 10. Audit read và audit use khác nhau

Một số hệ thống tách hai sự kiện:

- **Read/access:** workload lấy secret từ secret manager.
- **Use:** workload dùng credential để xác thực với database, API hoặc provider.

Secret manager thường nhìn thấy read nhưng không biết ứng dụng đã dùng secret cho mục đích nào. Resource server/provider có thể ghi nhận use hoặc authentication result. Hai event có thể liên kết bằng workload identity, key ID hoặc operation ID an toàn.

Ví dụ:

1. payment-api đọc secret version 7.
2. payment-api mở kết nối tới provider.
3. Provider xác thực client thành công.
4. Audit ghi access event ở vault và authentication event ở provider.

Nếu vault read thành công nhưng provider login thất bại nhiều lần, đó có thể là dấu hiệu secret sai, bị rotate không đồng bộ hoặc bị lạm dụng.

Không khẳng định rằng secret đã được sử dụng chỉ vì có read event. Hãy ghi đúng loại bằng chứng mà hệ thống thực sự quan sát được.

## 11. Authorization trước khi truy cập secret

Audit giúp quan sát nhưng không thay authorization. Trước khi trả secret hoặc thực hiện crypto operation, store/provider cần kiểm tra:

- Actor/workload đã được xác thực.
- Subject và tenant được xác định từ nguồn tin cậy.
- Resource nằm trong namespace/owner mà caller được phép.
- Action cụ thể nằm trong policy.
- Environment và audience phù hợp.
- Secret version còn active và không bị revoke.
- Approval/dual control còn hiệu lực nếu cần.
- Context không vi phạm time window hoặc incident restriction.

Nên dùng deny-by-default. Không có policy allow rõ thì từ chối. Việc bị từ chối vẫn tạo audit event với reason code phù hợp.

### Least privilege

- Workload chỉ đọc đúng secret cần dùng.
- Developer không mặc định có quyền đọc production secret.
- CI/CD chỉ được truy cập secret trong pipeline/environment đã phê duyệt.
- Operator có thể xem metadata nhưng không nhất thiết được reveal secret.
- KMS key usage tách khỏi key administration.
- Backup operator không tự động có quyền giải mã mọi backup.

## 12. Separation of duties và dual control

Một người không nên vừa tạo credential, tự phê duyệt, đọc secret production và xóa audit trail.

Separation of duties có thể phân chia:

- Requester yêu cầu quyền.
- Owner/resource custodian xác nhận mục đích.
- Security approver duyệt quyền nhạy cảm.
- Secret manager thực thi policy.
- Auditor chỉ đọc audit evidence.
- Platform operator quản lý hạ tầng nhưng không đọc plaintext secret mặc định.

Với thao tác đặc biệt như export key, decrypt backup hoặc thay policy KMS, có thể yêu cầu dual control: hai principal độc lập phê duyệt. Audit cần ghi từng approver, thời điểm, decision và operation được phê duyệt.

Không dùng một approval chung vô thời hạn. Approval cần gắn resource, action, subject, reason và expiry.

## 13. Break-glass access

Break-glass là quyền truy cập khẩn cấp khi quy trình thông thường không đáp ứng được sự cố nghiêm trọng. Vì có thể vượt một số ràng buộc thông thường, nó phải được kiểm soát và audit chặt.

Yêu cầu:

1. Có lý do và incident/ticket reference.
2. Principal được xác minh mạnh.
3. Phạm vi resource/action tối thiểu.
4. Thời hạn ngắn và tự động hết hiệu lực.
5. Dual approval nếu điều kiện vận hành cho phép.
6. Notification tới security owner.
7. Ghi nhận mọi read/use/export và thay đổi policy.
8. Review bắt buộc sau khi kết thúc.
9. Rotate credential nếu secret đã được reveal hoặc có nghi ngờ lộ.

Break-glass không được trở thành tài khoản dùng hằng ngày hoặc cơ chế bỏ qua audit. Nếu audit sink không khả dụng, policy phải xác định rõ có cho phép thao tác khẩn cấp trong điều kiện nào, bằng chứng tạm thời được ghi ở đâu và cách đồng bộ sau đó.

## 14. Bảo vệ tính toàn vẹn của audit trail

Audit log chỉ có giá trị nếu người bị kiểm toán không thể âm thầm sửa hoặc xóa bằng chứng.

Các lớp bảo vệ:

- Ghi event tới hệ thống log tách khỏi secret manager.
- Quyền append/write và quyền read/export được phân tách.
- Immutable/WORM storage hoặc retention lock cho event quan trọng.
- Hash chaining hoặc chữ ký batch để phát hiện sửa đổi khi phù hợp.
- Đồng bộ thời gian và ghi nhận source identity.
- Replication sang vùng/hệ thống độc lập.
- Theo dõi event gap, ingestion delay và sink failure.
- Audit cả thay đổi cấu hình log, retention và export.
- Hạn chế admin có thể xóa đồng thời cả nguồn và bản sao.

Hash chain không tự bảo vệ log nếu attacker có thể sửa cả dữ liệu lẫn anchor/key dùng xác minh. Cần bảo vệ signing key, checkpoint và bản sao độc lập.

~~~mermaid
flowchart LR
    V["Vault / KMS / credential store"] --> E["Structured audit event"]
    E --> C["Collector / validation"]
    C --> S["Central append-only log"]
    C --> W["Immutable archive"]
    S --> D["Detection and SIEM"]
    W --> I["Forensic investigation"]
    D --> A["Alert / incident workflow"]
    S --> M["Audit integrity monitor"]
~~~

## 15. Alert và detection use cases

Một số quy tắc phát hiện có giá trị:

| Use case | Tín hiệu | Phản ứng gợi ý |
|---|---|---|
| Secret enumeration | Nhiều unknown secret ID hoặc denied reads | Rate limit, alert, kiểm tra caller |
| Bulk secret access | Một workload đọc nhiều secret không thường dùng | Restrict, xác minh deployment/change |
| Human access to production | User đọc secret production ngoài change window | Alert, approval review |
| Offboarded identity access | Principal đã disable tiếp tục truy cập | Deny và incident |
| New workload reads old secret | Service identity mới đọc secret cũ | Kiểm tra rollout và ownership |
| Break-glass misuse | Emergency access không có incident reference | Alert mức cao, review |
| Policy tampering | ACL/KMS policy thay đổi bất thường | Dual control và incident |
| Secret read then suspicious login | Vault read theo sau bởi provider authentication anomaly | Correlate và rotate nếu cần |
| Repeated denied decrypt | Nhiều crypto operation thất bại | Kiểm tra key misuse |
| Audit silence | Không có event trong khi workload vẫn hoạt động | Kiểm tra pipeline/collector |

Alert không nên dựa vào một IP mới đơn lẻ. Kết hợp principal, workload, resource sensitivity, action, time, deployment context và lịch sử truy cập.

## 16. SIEM và correlation

SIEM có thể kết hợp:

- Vault/KMS access events.
- IdP authentication events.
- Authorization decisions.
- Cloud control-plane audit.
- Kubernetes/orchestrator workload events.
- Database/provider authentication.
- CI/CD deployment/change events.
- Endpoint detection và incident telemetry.

Ví dụ chuỗi:

1. Một developer đăng nhập từ thiết bị mới.
2. Developer được cấp role đọc secret production.
3. Secret được đọc ngoài change window.
4. Một workload mới dùng credential đó gọi provider.
5. Provider ghi nhận truy cập từ network/region bất thường.

Mỗi event riêng có thể hợp lệ; chuỗi và thời điểm mới cho thấy nguy cơ. Dùng event ID, principal ID, workload ID, resource ID và request correlation an toàn. Không cần đưa secret value vào SIEM.

## 17. Retention, privacy và dữ liệu audit

Audit có thể chứa dữ liệu nhạy cảm dù không có secret:

- Username/employee ID.
- Workload topology.
- Secret names phản ánh hệ thống nội bộ.
- IP, device metadata và thời điểm làm việc.
- Ticket/incident references.
- Relationship giữa service và tài nguyên.

Nguyên tắc:

- Chỉ thu thập metadata cần thiết để bảo mật và tuân thủ.
- Đặt retention theo mục đích, quy định và mức độ nhạy cảm.
- Hạn chế quyền truy cập audit theo vai trò.
- Mã hóa khi truyền và khi lưu.
- Có audit cho việc đọc/export audit log.
- Redact PII không cần thiết.
- Có quy trình legal hold/incident preservation.
- Xóa hoặc archive an toàn khi hết retention.

Không giữ mọi log vô thời hạn theo mặc định. Retention quá dài tăng rủi ro lộ dữ liệu và chi phí, còn quá ngắn làm mất khả năng điều tra. Cần thống nhất retention cho online search, immutable archive và forensic evidence.

## 18. Khi audit pipeline bị lỗi

Nếu secret manager cho phép read nhưng audit collector không nhận event, hệ thống có thể mất bằng chứng. Cần xác định failure semantics:

| Tình huống | Hành vi gợi ý |
|---|---|
| Audit sink tạm chậm | Buffer bền vững, retry và cảnh báo ingestion lag |
| Buffer đầy | Áp dụng policy theo mức nhạy cảm; không âm thầm bỏ event |
| Audit storage unavailable khi đọc secret production | Fail closed hoặc dùng durable local queue theo policy đã phê duyệt |
| Event duplicate do retry | Deduplicate theo event ID nhưng giữ được delivery evidence |
| Event mất thứ tự | Dùng timestamp/sequence/version và correlation |
| Collector bị compromise | Cách ly, chuyển sang sink độc lập và preserve evidence |
| Không xác minh được integrity | Đánh dấu evidence degraded và mở incident |

Không được giả định log đã ghi chỉ vì application logger không báo lỗi. Cần quan sát end-to-end: event created, collector accepted, durable storage confirmed và SIEM indexed.

### Fail-open hay fail-closed?

Với truy cập secret production hoặc private-key operation, mất audit có thể là lý do từ chối vì hành động không thể được giám sát. Một số môi trường có thể dùng durable local buffer được mã hóa và giới hạn dung lượng để duy trì dịch vụ ngắn hạn. Quyết định phải được policy owner phê duyệt và có cảnh báo.

Không dùng fail-open vô thời hạn hoặc bỏ qua audit mà không tạo event bù sau đó.

## 19. Java/Spring: event model cho credential audit

Ví dụ model chỉ chứa metadata:

~~~java
enum CredentialAction {
    READ,
    LIST,
    CREATE,
    ROTATE,
    REVOKE,
    SIGN,
    DECRYPT
}

enum AuditOutcome {
    ALLOWED,
    DENIED,
    FAILED,
    PARTIAL
}

record CredentialAuditEvent(
    UUID eventId,
    Instant occurredAt,
    String actorId,
    String subjectId,
    String workloadId,
    String tenantId,
    String resourceId,
    String resourceVersion,
    CredentialAction action,
    AuditOutcome outcome,
    String reasonCode,
    String policyVersion,
    String requestId,
    String approvalId
) {}
~~~

Không thêm field plaintext secret, token, password hoặc private key vào event. Schema cần được kiểm soát và validate để ngăn application tự ý đưa nội dung nhạy cảm vào field tự do.

### Phát event sau quyết định truy cập

~~~java
@Service
class AuditedSecretReader {
    private final SecretAuthorizationPolicy policy;
    private final SecretStore secretStore;
    private final CredentialAuditPublisher audit;

    AuditedSecretReader(
            SecretAuthorizationPolicy policy,
            SecretStore secretStore,
            CredentialAuditPublisher audit) {
        this.policy = policy;
        this.secretStore = secretStore;
        this.audit = audit;
    }

    SecretValue read(
            WorkloadPrincipal actor,
            String secretId,
            RequestContext context) {

        AccessDecision decision =
            policy.evaluate(actor, secretId, CredentialAction.READ, context);

        if (!decision.allowed()) {
            audit.publish(CredentialAuditEventFactory.denied(
                actor, secretId, decision, context
            ));
            throw new AccessDeniedException("Secret access denied");
        }

        SecretValue value = secretStore.read(secretId);

        audit.publish(CredentialAuditEventFactory.allowed(
            actor, secretId, value.version(), decision, context
        ));
        return value;
    }
}
~~~

Đây là ví dụ minh họa. Production cần bảo đảm event được ghi bền vững theo yêu cầu trước/sau khi trả secret, và xử lý trường hợp secret read thành công nhưng audit publish thất bại. Không log object SecretValue hoặc đưa nó vào exception.

### Outbox cho audit event

Nếu audit event phải commit cùng thay đổi credential trong cùng database, có thể dùng transactional outbox. Nếu secret store và audit sink là hai hệ thống độc lập, không có transaction ACID chung; cần durable event queue, retry, idempotent consumer và trạng thái delivery để không mất bằng chứng.

## 20. Java: redaction và kiểm tra schema

Không nên dùng cách ghi toàn bộ request object vào log. Tạo DTO audit allowlist chỉ chứa field được phép:

~~~java
record SecretAccessAuditView(
    String actorId,
    String resourceId,
    String action,
    String outcome,
    String requestId
) {}

SecretAccessAuditView toAuditView(
        WorkloadPrincipal actor,
        String resourceId,
        CredentialAction action,
        AuditOutcome outcome,
        String requestId) {
    return new SecretAccessAuditView(
        actor.id(),
        resourceId,
        action.name(),
        outcome.name(),
        requestId
    );
}
~~~

Allowlist an toàn hơn denylist vì field mới được thêm vào request không tự động đi vào audit. Bổ sung secret scanning cho log/test fixture và kiểm tra serialized event trước khi gửi.

## 21. Các sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Log plaintext secret để điều tra | Log trở thành kho credential | Chỉ ghi resource ID/version/action |
| Chỉ ghi successful read | Không phát hiện probing và enumeration | Ghi cả denied/failed event |
| Chỉ ghi subject, không ghi actor | Không biết ai thao tác thay user | Ghi actor và subject riêng |
| Ghi raw token/cookie làm correlation | Rò bearer credential | Dùng request/event ID an toàn |
| Admin có thể sửa và xóa log | Mất bằng chứng | Immutable archive, tách quyền và integrity monitor |
| Audit chỉ nằm cùng secret store | Compromise store có thể xóa cả bằng chứng | Sink độc lập và bản sao immutable |
| Không audit policy change | Attacker mở rộng quyền mà không bị phát hiện | Ghi role/ACL/KMS policy changes |
| Không audit export/list | Bulk secret exfiltration khó phát hiện | Ghi list/export và volume metadata |
| Không theo dõi audit pipeline lag | Event bị mất âm thầm | End-to-end delivery monitoring |
| Break-glass không có expiry | Quyền khẩn cấp thành quyền thường trực | TTL, incident reference và post-review |
| Event schema có field tự do không kiểm soát | Developer vô tình log secret | Allowlist schema và validation |
| Dùng hash secret tùy tiện trong log | Có thể tạo oracle/correlation nhạy cảm | Opaque resource ID hoặc keyed reference |
| Retention vô hạn | Tăng privacy risk và chi phí | Retention theo mục đích |
| Retry audit tạo duplicate không kiểm soát | Khó điều tra và đếm sai | Event ID, idempotent ingestion |

## 22. Ma trận kiểm thử credential access audit

| Kiểm thử | Kết quả mong đợi |
|---|---|
| Workload đọc secret được phép | Audit ghi actor, resource ID/version, action và ALLOWED |
| Workload đọc secret ngoài scope | DENIED event được ghi |
| Secret ID không tồn tại | Failure event không tiết lộ secret value |
| User list nhiều secret | Ghi list operation và áp dụng quota/policy |
| Bulk export | Audit volume và alert theo policy |
| Admin đổi ACL | Ghi actor, before/after metadata, approval và policy version |
| KMS decrypt/sign | Ghi key ID, operation, caller và outcome |
| Secret rotation | Ghi version mới và trạng thái version cũ |
| Secret revoke | Verifier/store từ chối lần truy cập tiếp theo |
| Break-glass không có ticket/approval | Từ chối hoặc cảnh báo theo emergency policy |
| Break-glass hết hạn | Quyền tự hết hiệu lực |
| Dual approval thiếu approver thứ hai | Không thực hiện action |
| Event chứa password/API key/token | Schema/secret scanner từ chối hoặc phát hiện; không ingest |
| Application exception chứa secret | Redaction kiểm soát; không ghi raw exception data |
| Audit sink unavailable | Buffer bền vững hoặc fail-closed theo policy; có alert |
| Collector retry event | Ingestion idempotent theo event ID |
| Event tới sai thứ tự | Có thể correlate bằng timestamp/sequence/version |
| Log admin bị sửa | Integrity monitor phát hiện |
| User bị offboarded tiếp tục đọc secret | Access denied và incident signal |
| Workload mới đọc secret production | Alert hoặc approval check theo policy |
| Audit log được export | Ghi audit của chính hành động export |
| Backup restore secret store | Audit và credential status không bị rollback sai |
| Secret read thành công nhưng publish audit lỗi | Hành vi partial/fail-closed được thực hiện và quan sát |
| SIEM không nhận event | Delivery monitoring cảnh báo |

Kiểm thử cả event content lẫn end-to-end delivery. Xác minh không có secret trong event, application log, trace, metric label, exception hoặc test report.

## 23. Tình huống phân tích

### Tình huống A: developer đọc secret production ngoài giờ

Một developer đăng nhập hợp lệ rồi đọc nhiều secret production không thuộc service mình phụ trách.

**Phân tích:** Authentication hợp lệ không có nghĩa access được phép. Audit cần actor, resource, action, policy và outcome; detection tương quan số lượng secret, environment, owner và change window. Có thể revoke quyền và điều tra endpoint.

### Tình huống B: secret bị export nhưng log chỉ ghi read

Một admin tải nhiều secret về máy cá nhân. Hệ thống chỉ ghi một event generic là read.

**Phân tích:** Event model không phân biệt read, list, export và bulk retrieval. Bổ sung action/volume metadata, export event, approval ID và cảnh báo theo ngưỡng.

### Tình huống C: attacker xóa log sau khi dùng break-glass

Attacker chiếm admin role, đọc secret và xóa log trong cùng hệ thống.

**Phân tích:** Audit sink nằm cùng trust boundary và có chung admin authority. Cần sink độc lập, immutable archive, separation of duties và audit thay đổi cấu hình log.

### Tình huống D: secret read thành công nhưng audit publish thất bại

Ứng dụng lấy được secret từ vault nhưng collector đang unavailable. Ứng dụng vẫn tiếp tục hoạt động và không có event nào được lưu.

**Phân tích:** Cần failure semantics đã phê duyệt: durable local/outbox queue hoặc fail closed cho secret nhạy cảm. Phải alert ingestion lag và reconcile event bị pending.

### Tình huống E: workload cũ vẫn đọc secret sau rotation

Secret đã được rotate nhưng một instance cũ tiếp tục đọc version trước và dùng credential cũ để gọi provider.

**Phân tích:** Audit cần resource version và workload identity. Correlate access với provider authentication; revoke version cũ theo overlap policy và kiểm tra instance chưa cập nhật.

## 24. Quy trình thiết kế và vận hành

Trước khi phát hành credential access audit, hãy xác định:

1. Secret store, KMS, HSM, CA, token store và backup nào nằm trong phạm vi?
2. Read, list, export, sign, decrypt, rotate, revoke và policy change có event riêng không?
3. Actor, subject, workload, tenant và resource được lấy từ nguồn nào?
4. Event schema có allowlist và không chứa secret không?
5. Có ghi cả denied/failed access và rate-limit event không?
6. Có correlation ID, policy version, resource version và approval reference không?
7. Audit sink có độc lập với secret store và admin authority không?
8. Event có immutable/archive/integrity protection không?
9. Retention và quyền đọc/export audit được quản lý ra sao?
10. Break-glass có TTL, approval, notification và post-review không?
11. Audit pipeline có durable buffer, retry, deduplication và delivery monitoring không?
12. Alert nào phát hiện enumeration, bulk export, offboarded identity và policy tampering?
13. SIEM có correlate vault, IdP, workload, provider và control-plane event không?
14. Có diễn tập audit sink outage, log tampering và secret exfiltration không?
15. Có secret scanning cho application log, trace, metric và audit fixture không?

## 25. Ghi nhớ trọng tâm

- **Audit ghi lại hành động, không ghi lại secret.** Resource ID, version, actor, action và outcome thường đủ để điều tra.
- **Authentication log không thay credential access audit.** Đăng nhập hợp lệ vẫn có thể truy cập secret trái quyền.
- **Ghi cả thành công và thất bại.** Denied read, list và export attempt có thể là dấu hiệu tấn công.
- **Phân biệt actor, subject và workload.** Điều tra cần biết ai thực hiện và danh tính nào được đại diện.
- **Authorization phải được thực thi trước khi đọc hoặc dùng credential.** Audit không thay deny-by-default và least privilege.
- **Break-glass cần TTL, approval, notification và post-review.**
- **Audit sink phải có trust boundary riêng.** Người đọc secret không được mặc nhiên có quyền xóa bằng chứng.
- **Bảo vệ integrity và delivery.** Event mất, trễ hoặc bị sửa phải được phát hiện.
- **Retention phải cân bằng điều tra và privacy.** Không giữ mọi metadata vô thời hạn.
- **Tương quan event không cần raw token.** Dùng event ID, request ID, workload ID và resource version.

Credential access audit tạo bằng chứng về cách tài sản xác thực được sử dụng và quản trị. Khi event có cấu trúc, không chứa secret, được lưu ở nơi độc lập và có thể liên kết với authentication, authorization cùng hoạt động downstream, tổ chức có thể phát hiện việc lạm dụng credential và điều tra mà không làm tăng nguy cơ lộ chính credential đó.
