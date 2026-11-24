# Lưu vết truy cập, vị trí dữ liệu và chính sách lưu giữ

Một hệ thống có thể phân quyền đúng và mã hóa dữ liệu tốt nhưng vẫn không trả lời được những câu hỏi quan trọng khi có sự cố: ai đã đọc hồ sơ này, request đến từ workload nào, dữ liệu được lưu ở khu vực nào, bản sao backup đang nằm ở đâu và khi nào dữ liệu được phép xóa? Nếu audit log thiếu, bị sửa hoặc đã hết hạn quá sớm, đội vận hành khó điều tra và tổ chức khó chứng minh các kiểm soát đã hoạt động.

Bảo vệ dữ liệu vì vậy cần quản lý cả **dấu vết truy cập**, **vị trí lưu trữ/xử lý** và **thời hạn lưu giữ**. Ba nội dung này liên quan nhưng khác nhau:

- **Audit trail** ghi nhận ai làm gì, với tài nguyên nào, vào lúc nào và kết quả ra sao.
- **Data residency** xác định dữ liệu được lưu trữ/xử lý tại địa lý hoặc vùng nào theo cam kết và cấu hình của dịch vụ.
- **Retention policy** quy định dữ liệu phải được giữ trong bao lâu, khi nào được xóa và trường hợp nào phải tạm dừng xóa.

Một chính sách chỉ có hiệu lực khi được triển khai tới database, object storage, log platform, backup, replica, search index và các dịch vụ cloud thực tế. Chọn một region cho database không tự bảo đảm mọi log, bản sao và telemetry đều nằm cùng nơi.

Bài thuộc chương **Bảo vệ dữ liệu** của mô-đun **SPRING_CLOUD_PROVIDER_INTEGRATION**. Mô-đun thực hành tích hợp Spring Boot với dịch vụ managed của AWS, Azure và Google Cloud qua các thư viện Spring Cloud tương ứng. Trọng tâm bài là thiết kế audit có thể điều tra, xác định đúng phạm vi residency và thực thi retention/xóa dữ liệu xuyên suốt vòng đời.

## 1. Mục tiêu học tập và tình huống xuyên suốt

Sau bài học, bạn có thể:

1. Phân biệt application audit, control-plane audit, data-plane audit, operational log và security event.
2. Thiết kế audit event có actor, action, resource, timestamp, outcome, tenant và correlation ID.
3. Ghi nhận truy cập đọc/tải dữ liệu, thay đổi quyền, export, xóa và thao tác quản trị.
4. Tích hợp Spring Boot audit với Spring Security, Spring Data JPA và transactional outbox.
5. Phân biệt region, geography, data residency, data sovereignty và cross-region replication.
6. Lập bản đồ vị trí cho dữ liệu nghiệp vụ, log, backup, metadata, key và telemetry.
7. Cấu hình AWS CloudTrail, Azure Monitor và Google Cloud Audit Logs theo đúng loại sự kiện.
8. Thiết kế retention, lifecycle, legal hold, immutable storage và quy trình xóa.
9. Kiểm thử log completeness, quyền đọc audit, vị trí dữ liệu, retention và khả năng restore.
10. Tránh lưu secret/PII quá mức trong audit log và tránh xóa bằng chứng trước khi hết nghĩa vụ lưu giữ.

Tình huống xuyên suốt: **document-service** lưu hợp đồng khách hàng trong object storage, metadata trong PostgreSQL và audit trong log platform. Service chạy tại một region, có backup/replica phục vụ disaster recovery và gửi log về hệ thống SIEM. Tổ chức cần biết ai đã xem/tải hợp đồng, log có được giữ đủ lâu không, dữ liệu có bản sao ở ngoài geography cho phép không và cách xóa dữ liệu khi hết retention.

~~~mermaid
flowchart TD
    A["User / service request"] --> B["Spring Boot authorization"]
    B --> C["Business operation"]
    B --> D["Application audit event"]
    C --> E["Database / object storage"]
    E --> F["Cloud data-plane audit"]
    D --> G["Durable audit outbox"]
    F --> H["Cloud audit trail"]
    G --> I["Central log archive / SIEM"]
    H --> I
    E --> J["Backup / replica / index"]
    I --> K["Retention + legal hold + access review"]
    J --> K
~~~

**Audit cho biết điều gì đã xảy ra; residency cho biết dữ liệu đi và nằm ở đâu; retention quyết định dữ liệu và bằng chứng tồn tại trong bao lâu.**

## 2. Các loại dấu vết cần thu thập

### 2.1. Application audit trail

Application audit được ghi ở cấp nghiệp vụ, nơi ứng dụng biết ý nghĩa của thao tác:

- Người dùng xem hoặc tải hồ sơ khách hàng.
- Nhân viên thay đổi trạng thái hợp đồng.
- Người quản trị cấp hoặc thu hồi quyền.
- Service tạo signed URL hoặc export báo cáo.
- Người dùng thay đổi thông tin thanh toán.
- Workflow xóa hoặc ẩn danh dữ liệu.

Cloud API log có thể cho biết một principal gọi GetObject, nhưng không nhất thiết biết request đó phục vụ nghiệp vụ nào, ticket nào hoặc người dùng cuối nào. Application audit bổ sung ngữ cảnh này.

### 2.2. Control-plane audit

Control-plane audit ghi nhận thay đổi cấu hình và quản trị tài nguyên:

- Tạo/xóa bucket, database, key hoặc service account.
- Thay đổi IAM/RBAC, bucket policy, network rule.
- Tắt audit logging hoặc thay đổi log destination.
- Tạo snapshot, replica, export hoặc diagnostic setting.
- Thay đổi retention period, legal hold và encryption configuration.

Các sự kiện này thường do cloud provider ghi nhận. Ứng dụng Spring Boot không thể tự thay thế nguồn audit quản trị của cloud.

### 2.3. Data-plane audit

Data-plane audit ghi nhận hoạt động trên dữ liệu:

- Đọc object, tải file, ghi hoặc xóa object.
- Query bảng hoặc đọc record.
- Truy cập secret hoặc gọi KMS decrypt.
- Đọc message hoặc export dataset.
- Thay đổi ACL/permission gắn với resource.

Đây là loại log thường cần bật/cấu hình riêng và có thể tạo volume lớn hoặc phát sinh chi phí. Không nên giả định việc bật management event đồng nghĩa đã ghi nhận mọi lần đọc object hoặc query dữ liệu.

### 2.4. Operational log và security event

| Loại | Mục đích | Ví dụ |
| --- | --- | --- |
| Application log | Debug và vận hành | Request timeout, lỗi kết nối DB |
| Access log | Theo dõi HTTP request | Method, route, status, latency |
| Application audit | Bằng chứng nghiệp vụ | Actor tải hợp đồng, outcome |
| Cloud audit | Bằng chứng hoạt động trên cloud | GetObject, IAM policy change |
| Security event | Phát hiện hành vi đáng ngờ | Nhiều lần access denied, token reuse |
| Metrics/traces | Hiệu năng và luồng xử lý | Latency, span, error rate |

Một access log chỉ có method, URL và status có thể không đủ để biết actor được xác thực là ai hoặc resource nào đã được đọc. Ngược lại, application log debug không nên bị coi là audit record chính thức.

### 2.5. Câu hỏi audit cần trả lời

Mỗi audit record nên giúp trả lời:

- **Who:** user, service principal, workload hoặc administrator nào?
- **What:** action nào đã xảy ra?
- **Which resource:** object, record, tenant, dataset hoặc secret nào?
- **When:** thời gian xảy ra theo UTC và thời gian ghi nhận?
- **Where:** source IP, workload, region hoặc endpoint nào?
- **Why:** purpose, ticket, workflow hoặc policy nào cho phép?
- **Result:** allowed, denied, success, failure hay partial?
- **How:** request ID, trace ID, policy version và authentication context nào liên quan?

Không phải mọi field đều cần xuất hiện trong mọi event. Chỉ thu thập metadata cần cho điều tra, tuân thủ và vận hành.

## 3. Thiết kế schema audit event

### 3.1. Các trường khuyến nghị

| Field | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| eventId | ID duy nhất của audit event | UUID hoặc ID ngẫu nhiên |
| occurredAt | Thời điểm thao tác xảy ra | UTC/Instant |
| recordedAt | Thời điểm audit store nhận event | Phân biệt với occurredAt |
| actorType | USER, SERVICE, ADMIN, SYSTEM | Không chỉ dựa vào tên hiển thị |
| actorRef | Subject/service principal đã pseudonymize | Tránh email đầy đủ nếu không cần |
| tenantRef | Tenant liên quan | Phải được xác minh từ identity/context tin cậy |
| action | READ, DOWNLOAD, UPDATE, EXPORT, DELETE, GRANT | Dùng vocabulary ổn định |
| resourceType | CUSTOMER, DOCUMENT, SECRET, DATASET | Có thể là taxonomy nội bộ |
| resourceRef | ID tài nguyên | Không ghi payload hoặc nội dung tài liệu |
| outcome | ALLOWED, DENIED, SUCCESS, FAILURE | Phân biệt quyết định quyền với kết quả thao tác |
| reasonCode | Mã lý do hoặc policy decision | Tránh ghi exception chứa secret |
| purpose | Mục đích nghiệp vụ đã khai báo | Không lấy chuỗi tùy ý từ client |
| classification | Mức nhạy cảm của resource | Theo data inventory |
| source | Workload, application, API hoặc cloud service | Có thể có environment |
| sourceIp | IP nguồn khi có cơ sở thu thập | Cân nhắc masking/retention |
| requestId | Correlation ID của request | Validate hoặc tạo mới ở edge |
| traceId | Distributed trace ID | Không dùng làm identity |
| policyVersion | Phiên bản policy/authorization rule | Giúp giải thích quyết định cũ |
| region | Region/resource location liên quan | Không suy ra từ IP |

### 3.2. Không ghi dữ liệu nhạy cảm vào audit

Không ghi trực tiếp:

- Password, API key, OAuth token, refresh token, cookie, private key.
- Signed URL đầy đủ, SAS query string hoặc presigned URL.
- Toàn bộ request/response body.
- Số định danh, số thẻ, email/phone đầy đủ nếu không có mục đích.
- Nội dung hợp đồng hoặc support note.
- SQL bind parameter có dữ liệu nhạy cảm.
- Exception message chứa connection string hoặc credential.

Thay bằng event metadata, opaque resource reference, hash/pseudonymized identifier và reason code. Nếu cần lưu payload để điều tra, phải có mục đích, quyền riêng, mã hóa và retention riêng; không mặc định biến audit log thành kho dữ liệu nghiệp vụ thứ hai.

### 3.3. Phân biệt outcome và authorization decision

Ví dụ người dùng được phép tải hợp đồng nhưng object storage tạm thời lỗi:

- Authorization decision: ALLOWED.
- Operation result: FAILURE.

Nếu người dùng không có quyền:

- Authorization decision: DENIED.
- Operation result: NOT_EXECUTED.

Tách hai thông tin giúp phân biệt policy sai với lỗi hạ tầng.

### 3.4. Event vocabulary ổn định

Dùng action/resource type có danh mục rõ ràng. Tránh mỗi service tự tạo chuỗi tùy ý như VIEW_DOC, DOC_OPENED, READ_CONTRACT cho cùng một hành vi. Một vocabulary ổn định giúp query, alert và báo cáo xuyên nhiều service.

## 4. Lưu audit trong Spring Boot

### 4.1. Spring Data auditing và access audit khác nhau

Spring Data JPA hỗ trợ các metadata như created-by, last-modified-by, created-date và last-modified-date. Chúng hữu ích để biết ai tạo hoặc sửa một entity và vào lúc nào.

Tuy nhiên, Spring Data auditing **không tự ghi mọi lần đọc, download, export, access denied hoặc thay đổi quyền**. Với các thao tác này, cần application audit event riêng.

### 4.2. Bật JPA auditing

Ví dụ cấu hình auditor lấy principal từ Spring Security:

~~~java
import java.util.Optional;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.domain.AuditorAware;
import org.springframework.data.jpa.repository.config.EnableJpaAuditing;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

@Configuration
@EnableJpaAuditing(auditorAwareRef = "auditorProvider")
public class JpaAuditConfiguration {

    @Bean
    AuditorAware<String> auditorProvider() {
        return () -> Optional.ofNullable(
                    SecurityContextHolder.getContext().getAuthentication())
                .filter(Authentication::isAuthenticated)
                .filter(authentication ->
                        !(authentication instanceof AnonymousAuthenticationToken))
                .map(Authentication::getName);
    }
}
~~~

Entity có thể dùng metadata:

~~~java
import java.time.Instant;
import java.util.UUID;
import jakarta.persistence.Entity;
import jakarta.persistence.EntityListeners;
import jakarta.persistence.Id;
import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.jpa.domain.support.AuditingEntityListener;

@Entity
@EntityListeners(AuditingEntityListener.class)
public class DocumentEntity {

    @Id
    private UUID id;

    @CreatedBy
    private String createdBy;

    @CreatedDate
    private Instant createdAt;

    @LastModifiedBy
    private String lastModifiedBy;

    @LastModifiedDate
    private Instant lastModifiedAt;
}
~~~

Đây là lịch sử tạo/sửa entity. Không dùng các field này để thay thế access audit trail.

### 4.3. Mô hình audit record

Ví dụ Java record:

~~~java
import java.time.Instant;
import java.util.UUID;

public record AccessAuditEvent(
        UUID eventId,
        Instant occurredAt,
        String actorType,
        String actorRef,
        String tenantRef,
        String action,
        String resourceType,
        String resourceRef,
        String authorizationDecision,
        String operationOutcome,
        String reasonCode,
        String purpose,
        String classification,
        String requestId,
        String traceId,
        String region) {
}
~~~

Các field actorRef, tenantRef và resourceRef nên là identifier nội bộ hoặc pseudonymous reference. Không đưa object body vào record.

### 4.4. Ghi audit trong cùng transaction

Với thao tác quan trọng, audit record nên được commit cùng thay đổi nghiệp vụ hoặc ghi qua transactional outbox. Ví dụ schema:

~~~sql
CREATE TABLE access_audit_outbox (
    event_id UUID PRIMARY KEY,
    occurred_at TIMESTAMPTZ NOT NULL,
    actor_type VARCHAR(24) NOT NULL,
    actor_ref VARCHAR(160),
    tenant_ref VARCHAR(160),
    action VARCHAR(48) NOT NULL,
    resource_type VARCHAR(48) NOT NULL,
    resource_ref VARCHAR(200),
    authorization_decision VARCHAR(24) NOT NULL,
    operation_outcome VARCHAR(24) NOT NULL,
    reason_code VARCHAR(80),
    purpose VARCHAR(120),
    classification VARCHAR(32),
    request_id VARCHAR(100),
    trace_id VARCHAR(64),
    region VARCHAR(80),
    created_at TIMESTAMPTZ NOT NULL,
    published_at TIMESTAMPTZ
);
~~~

Các repository, actor/context, entity và exception dưới đây là kiểu domain của ứng dụng. Ví dụ tập trung vào việc ghi audit cùng transaction nghiệp vụ.

~~~java
import java.time.Clock;
import java.util.UUID;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DocumentCommandService {
    private final DocumentRepository documents;
    private final AccessAuditOutboxRepository auditOutbox;
    private final Clock clock;

    public DocumentCommandService(
            DocumentRepository documents,
            AccessAuditOutboxRepository auditOutbox,
            Clock clock) {
        this.documents = documents;
        this.auditOutbox = auditOutbox;
        this.clock = clock;
    }

    @PreAuthorize("hasAuthority('document:archive')")
    @Transactional
    public void archive(UUID documentId, AuditActor actor, AuditContext context) {
        DocumentEntity document = documents.findById(documentId)
                .orElseThrow(DocumentNotFoundException::new);

        DocumentAccessPolicy.requireArchivePermission(actor, document);
        document.archive();

        auditOutbox.save(AccessAuditOutbox.from(
                UUID.randomUUID(),
                clock.instant(),
                actor,
                "ARCHIVE",
                "DOCUMENT",
                document.getId().toString(),
                "ALLOWED",
                "SUCCESS",
                context));
    }
}
~~~

Ví dụ giả định actor/context đã được tạo từ security context tin cậy và kiểm tra quyền đã diễn ra trong service. Không lấy actor hoặc tenant từ body request rồi tin tưởng trực tiếp.

Đối với request bị từ chối, ghi security audit qua authorization failure handler hoặc một audit path riêng. Nếu chỉ ghi trong transaction nghiệp vụ rồi ném AccessDeniedException, transaction có thể rollback và làm mất chính event DENIED cần giữ.

Outbox publisher gửi event tới audit store/log platform rồi đánh dấu published. Publisher có thể gửi lặp nếu timeout; downstream cần event ID để deduplicate. Không xóa outbox record trước khi có xác nhận publish bền vững theo thiết kế.

### 4.5. Khi nào audit failure phải làm thao tác thất bại?

Phân loại mức độ:

- Với thay đổi quyền, tải dữ liệu restricted, export lớn hoặc hành động có nghĩa vụ audit, nếu không thể ghi audit bền vững thì có thể phải fail closed hoặc giữ thao tác ở trạng thái pending.
- Với telemetry phục vụ debug/performance, có thể cho phép mất một số event khi log backend lỗi, miễn là không gọi đó là audit evidence.
- Nếu dùng outbox cùng transaction, business change và ý định ghi audit cùng commit; publisher có thể gửi sau.

Quyết định phải theo risk và yêu cầu nghiệp vụ. Không âm thầm bỏ audit khi sink lỗi.

### 4.6. Request ID, trace ID và source IP

- Tạo request ID tại API gateway/edge nếu client không cung cấp.
- Nếu nhận X-Request-ID từ client, validate charset/length và không dùng nó làm danh tính.
- Dùng W3C trace context để nối trace qua service, nhưng trace ID không chứng minh actor.
- Chỉ tin X-Forwarded-For khi request đi qua proxy/load balancer đã cấu hình tin cậy.
- Không lấy IP đầu tiên trong header do client gửi trực tiếp làm bằng chứng nguồn.
- Tránh ghi full URL query string vì có thể chứa token.

### 4.7. Async processing và actor context

SecurityContext mặc định gắn với thread execution model. Khi chuyển công việc sang executor hoặc message listener, principal có thể không tự đi theo. Hãy truyền actor reference và request context rõ ràng trong command/event, hoặc dùng cơ chế context propagation phù hợp. Không giả định worker background đang chạy dưới danh tính user ban đầu nếu không có metadata được xác thực.

## 5. Audit log phải khó bị sửa hoặc xóa

### 5.1. Tách quyền ghi, đọc và quản trị

Một mô hình tốt:

- Application chỉ có quyền INSERT audit event/outbox.
- Audit publisher có quyền append vào archive.
- Auditor/security role có quyền đọc và query.
- Platform administrator không mặc định có quyền xóa bằng chứng.
- Thay đổi retention/immutability cần role riêng và approval.
- Credential của log archive không dùng chung với workload đang được audit.

Nếu principal bị audit có thể sửa hoặc xóa log của chính mình, audit trail mất giá trị.

### 5.2. Append-only và immutable storage

Có thể bảo vệ bằng:

- Database permission chỉ INSERT cho writer, SELECT cho auditor.
- Bảng partitioned theo thời gian và policy xóa partition riêng.
- Centralized log account/project/subscription.
- WORM/object lock hoặc retention lock.
- Hash/digest để phát hiện thay đổi.
- Replication sang security account hoặc SIEM độc lập.
- Alert khi logging bị tắt hoặc destination/retention thay đổi.

Immutable storage giúp ngăn sửa/xóa trong thời gian giữ. Nó cũng làm việc xóa sớm khó hoặc không thể thực hiện; phải xác định retention trước khi lock.

### 5.3. Tamper-evident không đồng nghĩa tamper-proof

Hash chain hoặc signed digest có thể giúp phát hiện record bị sửa/xóa nếu attacker không thể thay cả chuỗi và khóa kiểm chứng. Nhưng nếu cùng một administrator có quyền ghi, xóa và quản lý signing key, bằng chứng vẫn có thể bị phá hủy.

Cloud provider có thể cung cấp digest/integrity validation. Ví dụ CloudTrail log file integrity validation tạo digest được ký để xác minh log file; bật validation không tự động chạy kiểm tra cho bạn, cần thực hiện validation và bảo vệ nơi lưu digest.

### 5.4. Bảo vệ audit archive

- Dùng account/project riêng nếu khả thi.
- Bật MFA/strong auth cho quyền quản trị archive.
- Bảo vệ encryption key và key policy độc lập.
- Bật alert khi log sink/trail/diagnostic setting bị thay đổi.
- Lưu bản sao ở vùng/địa điểm đã được phê duyệt.
- Kiểm thử restore và integrity validation.
- Không cho application role quyền xóa archive hoặc rút ngắn retention.

## 6. Data residency, geography và sovereignty

### 6.1. Các khái niệm

**Region** là vùng hạ tầng cloud được provider cung cấp. **Geography** có thể là nhóm region nằm trong một ranh giới địa lý hoặc data residency boundary của provider. **Data residency** nói về nơi customer data được lưu trữ/xử lý theo cấu hình và cam kết dịch vụ. **Data sovereignty** rộng hơn, liên quan đến luật áp dụng, quyền kiểm soát, quyền truy cập và vận hành dữ liệu.

Chọn region gần người dùng chủ yếu cải thiện latency. Chọn region để đáp ứng residency phải xét cả dịch vụ, replication, backup, logs và điều khoản dịch vụ.

### 6.2. Region không phải câu trả lời duy nhất

Một ứng dụng có thể lưu database ở Singapore nhưng vẫn đưa dữ liệu ra ngoài khu vực thông qua:

- Cross-region database replica hoặc object replication.
- Backup vault ở region khác.
- Log Analytics workspace hoặc SIEM ở geography khác.
- CDN/cache hoặc export destination.
- Data warehouse và BI pipeline.
- Support bundle, crash dump hoặc telemetry.
- Identity provider và metadata của tenant.
- Developer download hoặc admin truy cập từ quốc gia khác.

Phải lập data-flow map thay vì chỉ ghi một region trong deployment manifest.

### 6.3. Data location inventory

| Thành phần | Ví dụ | Điều cần xác minh |
| --- | --- | --- |
| Primary database | PostgreSQL managed service | Region, zone, replica và PITR |
| Object storage | S3, Blob, Cloud Storage | Bucket/container region, replication, version |
| Application audit | Audit DB/outbox | DB location, archive destination |
| Cloud audit | CloudTrail, Activity Log, Cloud Audit Logs | Log destination, region, retention |
| Search/cache | OpenSearch, Redis, managed cache | Replica, persistence và export |
| Backup/DR | Snapshot, vault, backup copy | Region, account/project và restore path |
| Key management | KMS, Key Vault, Cloud KMS | Key resource location, replica/availability semantics |
| Analytics | BigQuery, warehouse, SIEM | Dataset/workspace location và cross-region query |
| Telemetry | Traces, crash dump, metrics | Backend region, labels và payload capture |
| Support/export | Diagnostic bundle, ticket attachment | Người nhận, location, retention và deletion |

### 6.4. Data classification phải đi cùng location

Dữ liệu Restricted có thể yêu cầu giới hạn geography, replication và support access chặt hơn Public/Internal. Không nhất thiết mọi loại dữ liệu phải có cùng location constraint. Chọn mức kiểm soát theo classification và nghĩa vụ hợp đồng/pháp lý.

### 6.5. Region policy và ngoại lệ dịch vụ

Dùng organization policy, Azure Policy, SCP hoặc policy-as-code để hạn chế region được phép tạo resource. Nhưng policy không tự chứng minh mọi service dependency đều regional. Một số dịch vụ là global, một số metadata/control plane có phạm vi khác, và một số tính năng có thể lưu/replicate dữ liệu theo điều khoản riêng.

Trước khi cam kết residency, kiểm tra product-specific data residency documentation và service terms. Ghi lại ngoại lệ, người phê duyệt và biện pháp bù trừ.

## 7. Retention policy và data lifecycle

### 7.1. Retention là yêu cầu có chủ sở hữu

Mỗi loại dữ liệu cần có:

- Data owner và mục đích lưu.
- Classification.
- Căn cứ nghiệp vụ/hợp đồng/pháp lý.
- Retention start event.
- Thời hạn và đơn vị.
- Điều kiện gia hạn/legal hold.
- Cách xóa hoặc ẩn danh.
- Xử lý backup, replica, index và archive.
- Bằng chứng hoàn tất xóa.
- Owner phê duyệt ngoại lệ.

Không đặt retention chỉ theo mặc định của dịch vụ vì default retention có thể không phù hợp nghĩa vụ tổ chức.

### 7.2. Retention start time

Thời hạn có thể bắt đầu từ các mốc khác nhau:

- Ngày tạo record.
- Ngày kết thúc hợp đồng.
- Ngày đóng ticket.
- Ngày chấm dứt tài khoản.
- Ngày phát sinh audit event.
- Ngày kết thúc legal hold.

Ví dụ, hợp đồng có thể cần lưu từ ngày chấm dứt quan hệ khách hàng; log truy cập có thể cần lưu từ ngày event xảy ra. Không áp dụng cùng một mốc cho mọi dataset.

### 7.3. Ví dụ retention matrix

Các giá trị dưới đây chỉ minh họa cách lập policy, không phải thời hạn pháp lý mặc định:

| Data class | Ví dụ dữ liệu | Retention rule mẫu | Cách kết thúc |
| --- | --- | --- | --- |
| Operational logs | Debug/health/latency | 30–90 ngày tùy nhu cầu vận hành | Lifecycle delete |
| Security audit | Access denied, privilege change, export | Theo yêu cầu điều tra và compliance đã phê duyệt | Archive/immutable rồi delete |
| Business audit | Ai duyệt hợp đồng/thanh toán | Theo vòng đời record và nghĩa vụ hồ sơ | Retain/hold rồi delete |
| Customer content | Hồ sơ, tài liệu, file | Theo mục đích và hợp đồng | Delete/anonymize |
| Temporary upload | File quarantine | TTL ngắn sau khi scan/xử lý | Lifecycle delete |
| Backup | Snapshot/PITR | Theo RPO/RTO và policy backup | Backup expiry |
| Legal evidence | Hồ sơ có legal hold | Cho tới khi hold được giải phóng và hết retention liên quan | Authorized release rồi delete |

Mọi con số cần được data owner, security và legal/compliance xác nhận theo bối cảnh. Retention quá dài làm tăng rủi ro và chi phí; quá ngắn làm mất bằng chứng hoặc vi phạm nghĩa vụ.

### 7.4. Retention khác với immutability

- Retention policy quyết định giữ bao lâu.
- Lifecycle rule tự động chuyển storage class hoặc xóa khi điều kiện thỏa.
- Versioning giữ nhiều phiên bản, không tự đặt thời hạn giữ.
- Immutable/WORM ngăn sửa/xóa trong một khoảng thời gian hoặc khi legal hold.
- Backup policy giữ bản sao phục hồi theo RPO/RTO.

Có retention 365 ngày không có nghĩa object không thể bị xóa hôm nay. Muốn chống xóa sớm, cần immutability/permission controls phù hợp.

### 7.5. Legal hold và exception

Legal hold tạm dừng xóa dữ liệu liên quan đến điều tra/tranh chấp. Khi hold được áp dụng:

- Ghi lý do, người yêu cầu, phạm vi và ngày bắt đầu.
- Giới hạn quyền đặt/gỡ hold.
- Không để lifecycle job xóa object đang hold.
- Ghi audit khi hold được thêm/gỡ.
- Sau khi hold được gỡ, tính lại thời điểm đủ điều kiện xóa.
- Không kéo dài hold vô hạn nếu không còn căn cứ.

### 7.6. Xóa dữ liệu xuyên hệ thống

Khi xóa customer/document, cần xét:

1. Primary database.
2. Object storage và object versions.
3. Read replica và cross-region replica.
4. Search index và cache.
5. Event/message retention.
6. Export/report file.
7. Analytics warehouse.
8. Backup/snapshot/PITR.
9. Application logs và audit logs.
10. Support bundle hoặc third-party processor.

Không phải mọi audit record đều phải xóa cùng dữ liệu nghiệp vụ; có thể cần giữ metadata tối thiểu để chứng minh việc xóa đã xảy ra. Thiết kế sao cho audit record không chứa payload hoặc identifier trực tiếp vượt quá mục đích.

### 7.7. Backup và crypto-erasure

Backup có thể tồn tại sau khi record bị xóa khỏi primary database. Chính sách cần quy định:

- Backup hết hạn theo lịch riêng.
- Khi restore, áp dụng lại deletion/tombstone nếu record đã bị xóa sau thời điểm backup.
- Với envelope encryption, crypto-erasure chỉ phù hợp nếu key material thực sự không còn bản sao và không còn bản phục hồi.
- Không xóa KEK dùng chung nếu còn dữ liệu hợp lệ cần decrypt.
- Kiểm thử restore và deletion replay trong môi trường riêng.

## 8. AWS: CloudTrail, S3 data events và Object Lock

### 8.1. CloudTrail management events và data events

CloudTrail ghi nhận hoạt động API trên AWS:

- Management events theo dõi thay đổi control plane như tạo resource, policy và cấu hình.
- Data events theo dõi hoạt động trên resource như S3 GetObject, PutObject và DeleteObject.
- Một số dịch vụ hỗ trợ network activity events hoặc loại event khác.

**S3 object-level data events không được bật mặc định cho trail.** Cần cấu hình advanced event selectors để chọn bucket/object và read/write events. Data events có thể tạo volume lớn và phát sinh chi phí; chọn scope theo classification, bucket và mục đích audit.

Ví dụ, nếu chỉ cần audit truy cập hợp đồng, bật S3 data events cho bucket/prefix chứa hợp đồng thay vì mọi bucket trong account. Xem xét cả GetObject, PutObject, DeleteObject và các thao tác liên quan.

### 8.2. Lưu và kiểm tra tính toàn vẹn log

CloudTrail có thể ghi log vào S3 bucket do tổ chức chọn, thường nên đặt ở log archive account riêng. Có thể bật log file integrity validation để tạo digest hỗ trợ xác minh log file không bị thay đổi sau khi CloudTrail giao.

- Bảo vệ bucket archive bằng policy riêng.
- Giới hạn quyền delete và thay đổi lifecycle.
- Bật encryption và audit cho bucket archive.
- Kiểm tra digest định kỳ bằng công cụ/CLI phù hợp.
- Theo dõi trail bị stop, logging bị disable hoặc destination bị thay đổi.

Bật integrity validation chỉ tạo digest; cần thực hiện bước validation và bảo vệ cả log lẫn digest.

### 8.3. S3 Object Lock

S3 Object Lock cung cấp WORM cho object version:

- Bucket phải bật Versioning.
- Governance mode cho phép principal có quyền đặc biệt bypass retention.
- Compliance mode ngăn xóa/ghi đè object version trước thời hạn, kể cả root user trong account.
- Legal hold không có ngày hết hạn cố định, cần được gỡ rõ ràng.
- Object Lock không ngăn tạo object version mới cùng key; phải kiểm soát version và access policy.

Bật Object Lock là quyết định ảnh hưởng vòng đời bucket; sau khi enable, không thể disable Object Lock hoặc suspend versioning trên bucket đó. Không bật trên log archive chỉ vì muốn “an toàn hơn” nếu chưa thiết kế retention, legal hold và quy trình xóa.

### 8.4. AWS residency và replication

Chọn AWS Region cho S3/database và kiểm tra:

- S3 Cross-Region Replication hoặc replication rule.
- Backup copy sang region/account khác.
- CloudTrail destination bucket region.
- KMS key region và key policy.
- Export sang Athena/warehouse/SIEM.
- Global service và metadata ngoài phạm vi resource region.

CloudTrail multi-region trail giúp thu thập event từ nhiều region; nó không tự quyết định nơi lưu archive. Destination bucket và các bản sao cần được đưa vào data location inventory.

### 8.5. AWS retention và lifecycle

S3 Lifecycle có thể transition hoặc expire object/version. Kết hợp với Versioning, Object Lock và legal hold cần kiểm tra kỹ: object đang bị lock không thể bị lifecycle xóa trước khi đủ điều kiện. Cần test lifecycle rule trên bucket test và kiểm tra noncurrent versions, delete markers, replication và backup.

## 9. Azure: Activity Log, resource logs và immutable Blob Storage

### 9.1. Activity Log và resource logs

Azure Monitor có các nguồn log khác nhau:

- **Activity Log:** hoạt động quản trị/control plane ở subscription, ví dụ tạo resource, thay đổi role hoặc cấu hình.
- **Resource logs:** hoạt động bên trong từng resource, có thể chứa data-plane operations tùy dịch vụ.
- **Entra sign-in/audit logs:** xác thực và thay đổi identity.
- **Application logs:** event nghiệp vụ do Spring Boot phát.

Activity Log có sẵn trong nền tảng và được giữ 90 ngày; nếu cần lâu hơn, route sang Storage account, Log Analytics hoặc Event Hubs theo nhu cầu. Resource logs không tự động được thu thập mặc định cho mọi resource; cần tạo diagnostic setting cho từng resource.

### 9.2. Diagnostic settings

Diagnostic settings xác định:

- Category log/metric cần thu thập.
- Destination: Log Analytics workspace, Storage account, Event Hubs hoặc partner integration.
- Collection mode/schema.
- Chính sách retention ở destination.

Không giả định bật diagnostic setting cho một resource sẽ tự bật cho toàn bộ subscription. Dùng policy/deployment automation để kiểm tra resource mới có diagnostic setting cần thiết.

Một số destination có ràng buộc region; ví dụ destination Storage/Event Hubs cho regional resource phải đáp ứng giới hạn location tương ứng. Resource logs được thiết kế theo store-and-forward, không có transactional guarantee tuyệt đối; audit nghiệp vụ quan trọng nên có durable record riêng trong ứng dụng.

### 9.3. Azure immutable Blob Storage

Azure Blob immutable storage hỗ trợ:

- Time-based retention: object không thể sửa/xóa trong thời hạn.
- Legal hold: giữ WORM cho tới khi hold được gỡ.
- Container-level hoặc version-level WORM tùy cấu hình.
- Audit và quản lý policy theo scope được hỗ trợ.

Legal hold và time-based retention có thể kết hợp. Trước khi khóa policy, xác minh retention interval, versioning, delete semantics và quyền đặt/gỡ legal hold. Immutable storage có thể cản trở xóa dữ liệu dù business record đã hết mục đích.

### 9.4. Azure residency và location

Azure region thuộc geography; geography có thể là ranh giới residency cho nhiều dịch vụ. Tuy nhiên, cam kết và ngoại lệ phụ thuộc sản phẩm, tính năng, replication option và service terms.

Cần kiểm tra:

- Region của Storage account, database, Key Vault và Log Analytics workspace.
- Diagnostic setting route tới workspace/storage/event hub ở đâu.
- Geo-redundant storage có replicate trong geography hay qua geography khác theo SKU.
- Backup vault và recovery region.
- Microsoft Entra/identity metadata và service-specific location commitments.
- Dữ liệu được customer export hoặc support truy cập từ đâu.

Azure Policy có thể giới hạn location được phép tạo resource nhưng không thay thế việc kiểm tra các dịch vụ global hoặc ngoại lệ của từng product.

### 9.5. Azure retention

Activity Log 90 ngày không phải retention mặc định cho mọi resource log. Log Analytics, Storage account, Event Hubs consumer và archive có retention/TTL riêng. Thiết kế lifecycle và delete ở destination; kiểm tra export pipeline không giữ thêm bản sao ngoài policy.

## 10. Google Cloud: Cloud Audit Logs, log buckets và Bucket Lock

### 10.1. Các loại Cloud Audit Logs

Google Cloud Audit Logs gồm các nhóm chính:

- **Admin Activity:** thao tác quản trị làm thay đổi cấu hình/resource.
- **Data Access:** đọc metadata/data hoặc tạo, sửa, đọc dữ liệu do người dùng cung cấp.
- **System Event:** thao tác do hệ thống Google Cloud thực hiện.
- **Policy Denied:** request bị từ chối bởi policy, theo dịch vụ/cấu hình.

Admin Activity được bật mặc định. Data Access bị tắt mặc định cho hầu hết dịch vụ, ngoại trừ một số dịch vụ như BigQuery; phải kiểm tra và bật theo service, project/folder/organization scope. Data Access có thể có volume và chi phí đáng kể.

### 10.2. Cloud Storage audit có giới hạn cần biết

Với Cloud Storage:

- Admin Activity ghi thay đổi cấu hình bucket/IAM.
- Data Access ghi các thao tác đọc/ghi object khi đã bật.
- Public access qua allUsers hoặc allAuthenticatedUsers không được Cloud Audit Logs ghi nhận như truy cập authenticated thông thường.
- Object Lifecycle Management và Autoclass không được Cloud Audit Logs theo dõi đầy đủ như user-driven operation.
- Nếu cần log public access hoặc lifecycle behavior, xem xét Cloud Storage usage logs; delivery có thể chậm và không bảo đảm timeliness/completeness như audit logs.

Đừng chỉ bật Admin Activity rồi kết luận đã có bằng chứng cho mọi lần tải object.

### 10.3. Cloud Logging log buckets

Cloud Logging lưu log trong log bucket:

- Log bucket là regional resource; vị trí ảnh hưởng nơi log được lưu/index/query.
- Bucket có retention period và IAM access riêng.
- Có thể route log qua sink tới log bucket, BigQuery, Cloud Storage hoặc Pub/Sub.
- Bucket location được chọn khi tạo; không thể thay location của bucket hiện hữu.
- Bucket mặc định _Required và _Default có thể được tạo ở global nếu không cấu hình default resource location trước; organization/folder có thể cấu hình default location cho bucket mới.
- User-defined bucket có thể đặt region và retention riêng.

Không gửi log nhạy cảm sang BigQuery dataset hoặc SIEM ở region khác mà không đưa vào residency map.

### 10.4. Cloud Storage Bucket Lock

Cloud Storage retention policy quy định object phải được giữ tối thiểu bao lâu. Khi lock bucket retention policy:

- Không thể gỡ policy hoặc giảm retention period.
- Object chưa đủ tuổi không thể bị xóa/thay thế.
- Bucket không thể xóa cho tới khi mọi object đáp ứng retention.
- Lock là thao tác không thể đảo ngược.

Hãy test với bucket riêng, dữ liệu giả và thời hạn ngắn trước khi lock bucket production.

### 10.5. BigQuery location

BigQuery dataset location được chọn khi tạo dataset và không thể thay đổi trực tiếp sau đó. Muốn di chuyển cần copy/replicate hoặc tạo dataset mới ở location khác theo khả năng hỗ trợ.

Tất cả dataset được tham chiếu trong cùng query cần tương thích location. Kiểm tra location của dataset, job, connection, external data source và log sink trước khi triển khai analytics.

## 11. So sánh nhanh ba provider

| Nhu cầu | AWS | Azure | Google Cloud |
| --- | --- | --- | --- |
| Control-plane audit | CloudTrail management events | Azure Activity Log | Cloud Audit Logs Admin Activity |
| Data-plane audit | CloudTrail data events; cần cấu hình | Resource logs/diagnostic settings theo resource | Cloud Audit Logs Data Access; cần bật cho phần lớn dịch vụ |
| Object access | S3 GetObject/PutObject/DeleteObject data events | Storage resource logs | Cloud Storage Data Access; usage logs cho một số trường hợp |
| Central log destination | S3 archive, CloudTrail Lake, SIEM | Log Analytics, Storage, Event Hubs | Cloud Logging buckets, BigQuery, Cloud Storage, Pub/Sub |
| Integrity/immutability | CloudTrail digest validation, S3 Object Lock | Immutable Blob Storage | Cloud Logging bucket lock và Cloud Storage Bucket Lock |
| Residency control | AWS Region, bucket, replica và destination | Azure region/geography, workspace và storage destination | Resource location, log bucket region, dataset/bucket location |
| Retention | S3 Lifecycle/Object Lock, CloudTrail archive | Activity Log export, workspace/storage retention, Blob immutability | Log bucket retention, GCS retention/Bucket Lock, dataset policy |
| Cảnh báo thường gặp | S3 data events chưa bật | Diagnostic setting chưa tạo | Data Access logs chưa bật |

## 12. Xây dựng retention policy trong ứng dụng

### 12.1. Data retention catalog

Một bảng policy nội bộ có thể mô tả:

~~~yaml
retentionPolicies:
  - id: operational-log
    dataClass: INTERNAL
    purpose: application-operations
    retentionDays: 45
    destination: central-log-bucket
    immutable: false
    deleteMethod: lifecycle

  - id: security-access-audit
    dataClass: CONFIDENTIAL
    purpose: security-investigation
    retentionDays: 400
    destination: audit-archive
    immutable: true
    deleteMethod: controlled-expiration

  - id: temporary-upload
    dataClass: CONFIDENTIAL
    purpose: upload-processing
    retentionDays: 7
    destination: quarantine-storage
    immutable: false
    deleteMethod: lifecycle
~~~

Đây là cấu trúc minh họa, không phải thời hạn pháp lý mặc định. Trước khi áp dụng, cần owner và compliance phê duyệt từng policy, đồng thời xác minh destination thực sự có lifecycle/immutability tương ứng.

### 12.2. Không đặt retention chỉ trong code

Nếu code có constant 365 ngày nhưng bucket lifecycle giữ 7 năm, dữ liệu vẫn còn. Nếu app xóa record nhưng backup giữ nhiều tháng, bản sao vẫn tồn tại. Policy phải được thực thi ở đúng storage/service và kiểm tra định kỳ.

Có thể dùng policy-as-code hoặc IaC để triển khai:

- Region allowlist.
- Audit logging enabled.
- Diagnostic settings.
- Log destination.
- Retention period.
- Object lock/legal hold.
- Backup copy location.
- IAM permission cho audit archive.

### 12.3. Deletion workflow

Một deletion workflow có thể gồm:

1. Xác minh yêu cầu xóa và owner.
2. Kiểm tra legal hold, litigation hold và nghĩa vụ retention.
3. Xác định data lineage: primary, replica, index, export, event, backup.
4. Đặt deletion tombstone hoặc workflow state.
5. Xóa/ẩn danh primary data theo thứ tự an toàn.
6. Xóa cache/index và bản export theo policy.
7. Để backup hết hạn hoặc áp dụng deletion replay khi restore.
8. Ghi audit event xác nhận scope, outcome và thời điểm.
9. Kiểm tra bản sao và báo cáo kết quả.
10. Giữ evidence tối thiểu cần thiết mà không sao chép payload đã xóa.

Không ghi raw personal data vào deletion audit. Dùng reference đã pseudonymize, deletion request ID và số lượng record.

### 12.4. Retention exception và legal hold

Mỗi exception cần:

- Request ID và owner.
- Lý do.
- Dataset/object scope.
- Thời hạn hoặc điều kiện kết thúc.
- Người phê duyệt.
- Quyền đặt/gỡ hold.
- Audit log cho mọi thay đổi.

Không cho application workload tự đặt legal hold vô hạn chỉ để tránh lỗi xóa.

## 13. Kiểm soát quyền đọc audit và data location

### 13.1. Least privilege cho audit

Phân quyền riêng:

- Application writer: chỉ append event.
- Log pipeline: đọc outbox và ghi archive.
- Security analyst: query audit trong scope được giao.
- Auditor: read-only và export có audit.
- Platform admin: quản lý hạ tầng nhưng không mặc định có quyền sửa evidence.
- Retention operator: thực hiện lifecycle/hold theo approval.

Không dùng một role toàn quyền cho cả người phát sinh event, người điều tra và người quản lý retention.

### 13.2. Audit việc đọc audit

Log archive cũng chứa dữ liệu nhạy cảm về hành vi người dùng và hạ tầng. Cần ghi nhận:

- Ai query audit archive.
- Ai export/download log.
- Ai thay retention hoặc sink.
- Ai thay đổi IAM/log bucket policy.
- Ai gỡ legal hold hoặc unlock policy khi provider cho phép.
- Ai truy cập backup hoặc evidence archive.

### 13.3. Alert khi audit pipeline bị thay đổi

Tạo cảnh báo cho:

- CloudTrail/trail hoặc data event selector bị tắt.
- Azure diagnostic setting bị xóa hoặc destination thay đổi.
- Google Cloud audit configuration hoặc sink bị thay đổi.
- Log archive retention bị giảm.
- Object Lock/Bucket Lock/immutability policy thay đổi.
- Log ingestion giảm đột ngột hoặc ngừng.
- Service account/role có quyền delete archive mới được tạo.

Đặt cảnh báo ở control plane độc lập nếu có thể, để attacker không dễ tắt cả nguồn log và cảnh báo.

### 13.4. Residency verification định kỳ

Theo lịch hoặc khi thay đổi kiến trúc:

- So sánh IaC/resource inventory với region policy.
- Kiểm tra replication và backup destinations.
- Kiểm tra workspace/log bucket/dataset locations.
- Kiểm tra data export, SIEM và third-party integration.
- Kiểm tra support access và operational boundary theo product terms.
- Lưu bằng chứng cấu hình và owner xác nhận.

Không coi một lần review lúc go-live là đủ; region, service feature và data flow có thể thay đổi.

## 14. Kiểm thử audit, residency và retention

### 14.1. Application audit test

- Read/download thành công tạo event có actor/resource/outcome.
- Access denied tạo event phù hợp.
- Admin grant/revoke có actor và policy version.
- Export tạo event riêng và có scope.
- Event không chứa raw token, signed URL, password hoặc body.
- Request ID/trace ID liên kết được với log vận hành.
- Async worker giữ đúng actor context đã được truyền.

### 14.2. Audit pipeline test

- Outbox record được commit cùng business transaction.
- Publisher retry không tạo duplicate audit record.
- Sink tạm lỗi không làm mất event đã persist.
- Role của application không update/delete archive.
- Auditor đọc được nhưng không sửa.
- Integrity validation phát hiện file log bị thay đổi trong môi trường test.
- Alert phát hiện trail/diagnostic setting bị tắt.

### 14.3. Residency test

- Primary DB, object storage và KMS ở location đã duyệt.
- Replica/backup chỉ tới destination đã duyệt.
- Log workspace/bucket/SIEM nằm trong phạm vi được phép.
- BigQuery dataset và job location tương thích.
- Cross-region copy bị policy chặn nếu không được phê duyệt.
- Resource global/service-specific exception được ghi trong inventory.

### 14.4. Retention test

- Object đủ tuổi được lifecycle xử lý theo policy.
- Object chưa hết retention không thể bị xóa nếu WORM đã bật.
- Legal hold ngăn xóa cho tới khi được gỡ.
- Backup hết hạn đúng lịch.
- Restore backup áp dụng lại tombstone/deletion sau thời điểm backup.
- Log archive không bị xóa trước thời hạn.
- Retention lock không thể giảm hoặc gỡ theo semantics provider.

### 14.5. Restore và evidence test

- Restore một bản backup vào môi trường cô lập.
- Kiểm tra decrypt với key version đúng.
- Xác minh audit event cho thao tác restore.
- Kiểm tra data deletion state được replay.
- Kiểm tra hash/digest của log archive.
- Lập báo cáo có timestamp, scope, kết quả và người thực hiện.

## 15. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Có management event nhưng không có object read | Chưa bật data-plane audit | Bật S3 data events, Azure resource logs hoặc GCP Data Access |
| Azure Activity Log chỉ có 90 ngày | Chưa route sang destination lưu lâu hơn | Diagnostic setting tới Storage/Log Analytics/Event Hubs |
| GCS không có log cho object public | Cloud Audit Logs không ghi public allUsers/allAuthenticatedUsers access | Xem xét usage logs và thiết kế access restriction |
| Log không nằm đúng geography | Log sink/workspace/bucket ở region khác | Kiểm tra location của từng destination và replica |
| BigQuery query báo location mismatch | Dataset/job/connection ở location khác | Đặt location nhất quán hoặc copy/replicate dataset |
| Lifecycle không xóa object | Retention lock/legal hold/version còn hiệu lực | Kiểm tra object version và hold state |
| Audit log biến mất sau khi xóa resource | Destination phụ thuộc resource hoặc chưa archive | Tách log archive, kiểm tra diagnostic setting và retention |
| Audit event thiếu actor trong async worker | Security context không được propagate | Truyền actor metadata rõ ràng vào message/command |
| Audit event bị duplicate | Outbox publisher retry hoặc at-least-once delivery | Dùng event ID và deduplicate ở sink |
| Không xác minh được ai đọc object | Chỉ có app log hoặc chưa bật data event | Bật provider data-plane audit và nối request/resource reference |
| Không xóa hết dữ liệu customer | Còn backup, replica, cache, index hoặc export | Dùng data lineage và deletion workflow xuyên hệ thống |
| WORM ngăn xóa dữ liệu hợp lệ | Retention/lock cấu hình sai hoặc legal hold chưa gỡ | Review policy/approval trước khi lock; không bypass tùy tiện |

## 16. Bài tập thực hành tổng hợp

document-service lưu hợp đồng trong object storage, metadata trong PostgreSQL, audit trong log platform và backup ở một region phục hồi. Ứng dụng tích hợp với AWS, Azure hoặc Google Cloud theo môi trường.

**Nhiệm vụ:**

1. Lập data inventory cho primary data, audit, logs, telemetry, backups, keys, exports và replicas.
2. Thiết kế audit schema có actor, action, resource, tenant, purpose, outcome, request ID và policy version.
3. Tạo access audit event cho READ, DOWNLOAD, EXPORT, UPDATE, DELETE và GRANT.
4. Dùng Spring Data auditing cho created/modified metadata và phân biệt với access audit.
5. Ghi audit qua transaction/outbox để không mất event khi service restart.
6. Bật data-plane audit cho object storage và ghi rõ chi phí/scope.
7. Chọn log destination và xác minh region/geography cho từng provider.
8. Xây retention matrix cho operational logs, security audit, business records, temporary files và backups.
9. Cấu hình WORM/legal hold cho audit archive trong môi trường test.
10. Viết deletion workflow bao gồm primary, replica, index, export và backup.
11. Kiểm thử quyền đọc audit, integrity validation, retention và restore.
12. Viết báo cáo chứng minh dữ liệu và log nằm trong location đã được phê duyệt.

**Câu hỏi tự đánh giá:**

- Application audit khác Cloud control-plane audit như thế nào?
- Vì sao S3 data events cần được cấu hình riêng?
- Vì sao Azure resource logs không tự động được thu thập?
- Vì sao GCP Data Access logs phải bật cho nhiều dịch vụ?
- Vì sao Cloud Storage public access có thể không xuất hiện trong Cloud Audit Logs?
- Region và geography khác nhau như thế nào?
- Vì sao log destination và backup phải có trong residency map?
- Retention policy khác WORM/immutability ra sao?
- Vì sao BigQuery dataset location phải được chọn trước khi tạo?
- Vì sao Cloud Logging log bucket location cần được kiểm tra?
- Vì sao S3 Object Lock cần Versioning?
- Vì sao Bucket Lock của GCS cần cân nhắc trước khi bật?
- Vì sao Spring Data auditing không ghi mọi lần đọc/download?
- Vì sao transactional outbox phù hợp với audit event?
- Khi xóa customer, vì sao cần xử lý replica, cache, index và backup?
- Vì sao audit archive cũng cần audit quyền đọc?

**Đáp án định hướng:** application audit ghi ngữ cảnh nghiệp vụ còn cloud audit ghi hoạt động provider; S3 data events không bật mặc định; Azure resource logs cần diagnostic setting; GCP Data Access disabled cho phần lớn dịch vụ; public access có giới hạn ghi audit; region là vùng hạ tầng, geography có thể là boundary; log/backup là bản sao dữ liệu; retention quy định thời hạn còn WORM ngăn sửa/xóa; BigQuery location không đổi trực tiếp sau tạo; Cloud Logging log bucket có location cố định; S3 Object Lock yêu cầu versioning; GCS Bucket Lock không thể giảm/gỡ retention; Spring Data auditing theo dõi tạo/sửa entity; outbox gắn ý định audit với transaction; deletion phải theo data lineage; người đọc audit cũng cần được kiểm soát.

## 17. Tài liệu tham khảo chính thức

### Spring

- [Spring Data JPA – Auditing](https://docs.spring.io/spring-data/jpa/reference/auditing.html): created/modified metadata và AuditorAware tích hợp Spring Security.

### AWS

- [AWS CloudTrail – Logging data events](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/logging-data-events-with-cloudtrail.html): data-plane events, S3 object activity và advanced event selectors.
- [AWS CloudTrail – S3 data events for governance](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/logging-s3-data-events-governance.html): audit access, deletion, replication và chi phí.
- [AWS CloudTrail – Log file integrity validation](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-log-file-validation-intro.html): digest và xác minh tính toàn vẹn log.
- [Amazon S3 – Object Lock](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html): WORM, governance/compliance mode, retention và legal hold.
- [Amazon S3 – Configuring Object Lock](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock-configure.html): Versioning requirement và cấu hình bucket/object.
- [AWS – Data privacy FAQ](https://aws.amazon.com/compliance/data-privacy-faq/): lựa chọn Region và customer content location.

### Azure

- [Azure Monitor – Activity Log](https://learn.microsoft.com/en-us/azure/azure-monitor/fundamentals/activity-log): Activity Log và lưu trữ dài hơn 90 ngày.
- [Azure Monitor – Resource logs](https://learn.microsoft.com/en-us/azure/azure-monitor/logs/resource-logs): thu thập resource logs và destination.
- [Azure Monitor – Diagnostic settings](https://learn.microsoft.com/en-us/azure/azure-monitor/platform/diagnostic-settings): route log/metric tới workspace, Storage và Event Hubs.
- [Azure Storage – Immutable storage overview](https://learn.microsoft.com/en-us/azure/storage/blobs/immutable-storage-overview): WORM, time-based retention và legal hold.
- [Azure – Data residency](https://azure.microsoft.com/en-us/explore/global-infrastructure/data-residency/): geography, regional services và các ngoại lệ location.
- [Azure – Regions overview](https://learn.microsoft.com/en-us/azure/reliability/regions-overview): region, geography và resiliency.

### Google Cloud

- [Cloud Audit Logs with Cloud Storage](https://docs.cloud.google.com/storage/docs/audit-logging): Admin Activity, Data Access, public access và giới hạn log.
- [Enable Data Access audit logs](https://docs.cloud.google.com/logging/docs/audit/configure-data-access): bật Data Access và cân nhắc log volume/cost.
- [Cloud Logging – Log buckets and retention](https://docs.cloud.google.com/logging/docs/store-log-entries): location, retention, IAM và routing.
- [Cloud Logging – Locations](https://docs.cloud.google.com/logging/docs/region-support): regional log buckets và default location.
- [Cloud Storage – Bucket Lock](https://docs.cloud.google.com/storage/docs/bucket-lock): retention policy và lock không thể đảo ngược.
- [BigQuery – Dataset locations](https://docs.cloud.google.com/bigquery/docs/datasets): location cố định khi tạo dataset.
- [Cloud Storage – Usage and storage logs](https://docs.cloud.google.com/storage/docs/access-logs): trường hợp cần usage logs bổ sung cho audit.

### OWASP

- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): dữ liệu cần tránh log, log integrity, access control và retention.

**Ghi nhớ:** muốn chứng minh dữ liệu được truy cập đúng cách, hãy kết hợp application audit với cloud data-plane audit. Muốn đáp ứng residency, hãy theo dõi cả primary, replica, backup, logs, analytics và telemetry. Muốn retention có hiệu lực, phải triển khai lifecycle/immutability ở storage thực tế, xử lý legal hold và kiểm tra restore/xóa xuyên toàn bộ data flow.
