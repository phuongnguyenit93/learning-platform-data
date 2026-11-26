# Audit quyền operator trong Spring Batch

## 1. Mục tiêu và bối cảnh

Khi Spring Batch xử lý dữ liệu lớn bằng multi-threaded step, parallel steps, partitioning hoặc remote workers, việc điều khiển job không còn nằm ở một tiến trình duy nhất. Một người vận hành có thể khởi chạy, dừng, khởi động lại job hoặc thay đổi phân quyền từ giao diện quản trị; đồng thời một service account có thể thực hiện các thao tác tự động. Mỗi thao tác đều có khả năng tác động đến nhiều worker, dữ liệu của nhiều tenant và trạng thái restart của job.

**Audit quyền operator** cần trả lời được hai nhóm câu hỏi:

1. **Quyền đã được cấp như thế nào?** Ai được cấp, thay đổi, thu hồi quyền nào; trên job, tenant và môi trường nào; ai phê duyệt; quyền có còn hiệu lực không?
2. **Quyền đã được sử dụng như thế nào?** Ai đã yêu cầu thao tác gì, hệ thống cho phép hay từ chối theo chính sách nào, lệnh đã được tiếp nhận chưa, và trạng thái job sau đó ra sao?

Mục tiêu không chỉ là giữ lịch sử thao tác. Audit còn là bằng chứng để điều tra sự cố, phát hiện vượt quyền, đối soát với `JobRepository` và kiểm tra nguyên tắc đặc quyền tối thiểu. Một bản ghi trong `BATCH_JOB_EXECUTION` hoặc log của worker **không tự động thay thế được audit bảo mật**: chúng chủ yếu mô tả thực thi job, thường không chứa quyết định cấp quyền, định danh operator hay lịch sử cấp/thu hồi quyền.

Sau bài này, người học có thể thiết kế ma trận quyền theo phạm vi, triển khai điểm kiểm soát trước `JobOperator`, ghi nhận sự kiện audit đủ để truy vết, xử lý tính nhất quán khi chạy phân tán và lập quy trình rà soát quyền định kỳ.

## 2. Phân biệt authentication, authorization và audit

| Thành phần | Câu hỏi cần trả lời | Ví dụ trong batch operations |
|---|---|---|
| Authentication (xác thực) | Người hoặc tiến trình gọi là ai? | OIDC/OAuth2 principal `ops-042`; service account `batch-scheduler`; workload identity của worker |
| Authorization (ủy quyền) | Chủ thể đó có quyền thực hiện hành động này trên tài nguyên này không? | `ops-042` được `RESTART` job `invoiceJob` của tenant `vn-retail` trên production |
| Audit quyết định | Hệ thống đã quyết định gì, theo chính sách nào? | `DENY` vì tenant không thuộc phạm vi quyền |
| Audit thao tác | Việc gọi cơ chế điều khiển job diễn ra thế nào? | `JobOperator.restart(7812)` trả về execution mới `7820` |
| Audit kết quả cuối | Job thực sự kết thúc ra sao? | Execution `7820` chuyển sang `COMPLETED` sau khi các partition hoàn tất |
| Audit thay đổi quyền | Ai cấp hoặc thu hồi đặc quyền nào? | Quản trị viên thu hồi `BATCH_ABANDON` của một tài khoản sau ca trực |

Điểm quan trọng: **được phép thực hiện** khác với **đã thực hiện thành công**, và một lệnh `stop` đã được tiếp nhận khác với job **đã dừng hoàn toàn**. Với môi trường mở rộng theo nhiều worker, khoảng cách giữa các mốc này có thể kéo dài và phải được phản ánh trong audit.

Phạm vi audit tối thiểu gồm ba lớp:

- **Control plane:** API/UI/CLI quản trị, scheduler, cơ chế phân quyền và façade gọi `JobOperator`.
- **Execution plane:** `JobExecution`, `StepExecution`, partition, worker, retry và restart; ghi nhận tương quan với yêu cầu của operator.
- **Identity/permission plane:** hệ thống định danh, role/group, policy, phê duyệt nâng quyền và vòng đời tài khoản.

## 3. Thiết kế quyền theo hành động và phạm vi tài nguyên

Spring Batch cung cấp các thao tác quản trị job qua `JobOperator` và metadata qua `JobExplorer`/`JobRepository`. Ứng dụng phải đặt lớp authorization của mình trước mọi đường gọi có quyền điều khiển; không nên mặc định một endpoint hay service nội bộ là an toàn chỉ vì nó nằm trong mạng riêng.

### 3.1. Ma trận RBAC mẫu

| Hành động | `BATCH_VIEWER` | `BATCH_RUNNER` | `BATCH_OPERATOR` | `BATCH_ADMIN` |
|---|:---:|:---:|:---:|:---:|
| Xem danh sách, trạng thái, chỉ số job đã được cấp phạm vi | Có | Có | Có | Có |
| `START` job được cho phép | Không | Có | Có | Có |
| `STOP` job đang chạy | Không | Không | Có | Có |
| `RESTART` job thất bại/đã dừng, đủ điều kiện restart | Không | Không | Có | Có |
| `ABANDON` execution | Không | Không | Không | Có, cần lý do/phê duyệt |
| Thay đổi cấu hình vận hành nhạy cảm | Không | Không | Theo danh mục được duyệt | Có, theo phạm vi |
| `GRANT_PERMISSION` / `REVOKE_PERMISSION` | Không | Không | Không | Qua quy trình IAM riêng |

Ma trận minh họa, không phải quy tắc mặc định của Spring Batch. **`BATCH_ADMIN` cũng phải chịu ràng buộc tenant, môi trường và nhóm job**. Tách người cấp quyền và người phê duyệt quyền đối với thao tác nhạy cảm; quyền quản trị IAM không mặc nhiên cho phép sửa dữ liệu batch.

Một chính sách đủ chặt nên kiểm tra đồng thời:

~~~text
Decision = f(
  actor identity + trạng thái tài khoản,
  action,
  environment,
  tenant,
  job name / job group,
  resource state,
  permission scope + thời hạn hiệu lực,
  policy version,
  điều kiện phê duyệt
)
~~~

Ví dụ, operator có quyền `RESTART` trên `billingJob` tại staging vẫn phải bị từ chối khi yêu cầu restart execution thuộc production. Tương tự, hai tenant cùng dùng một tên job vẫn là hai phạm vi khác nhau.

### 3.2. Các thao tác cần kiểm soát chặt

- **`START`:** kiểm tra job nằm trong allowlist, tenant hợp lệ, JobParameters được xác thực; không chấp nhận tham số có thể chuyển job sang dữ liệu của tenant khác.
- **`STOP`:** chỉ định execution cụ thể, kiểm tra trạng thái hiện hành; lệnh dừng có thể cần thời gian để worker đạt điểm dừng an toàn.
- **`RESTART`:** xác định job và tenant từ metadata **đã lưu và đáng tin cậy** của execution cũ; kiểm tra điều kiện restart, tránh chạy lặp dữ liệu.
- **`ABANDON`:** thao tác tác động đến khả năng tiếp tục xử lý/restart; yêu cầu đặc quyền cao, lý do và quy trình phê duyệt riêng.
- **Đổi concurrency, worker pool, queue, retry policy:** có thể làm quá tải tài nguyên hoặc khiến nhiều bản xử lý cùng tác động dữ liệu; audit như một thay đổi vận hành nhạy cảm.
- **Đổi role/scope:** ghi cả giá trị trước và sau, thời hạn, đơn vị phê duyệt và kết quả áp dụng.

Không dùng `tenantId`, `jobName` hay `executionId` do client gửi làm bằng chứng duy nhất để quyết định quyền. Với thao tác trên execution đã tồn tại, tra `JobExplorer` để xác định job và phạm vi gắn với execution đó. Nguồn tenant trong metadata phải được hệ thống xác thực hoặc gán từ lúc tạo job; tham số ban đầu do người dùng tự khai mà không được kiểm tra cũng không đáng tin cậy.

## 4. Mô hình sự kiện audit có thể đối soát

Nên tạo **nhiều sự kiện bất biến** cho các mốc khác nhau, liên kết bằng `requestId`/`correlationId`, thay vì cập nhật một dòng log duy nhất đến khi job hoàn tất.

| Loại sự kiện | Mốc phát sinh | Thông tin cần có |
|---|---|---|
| `OPERATOR_AUTHZ_DECISION` | Sau khi đánh giá policy, trước thao tác đặc quyền | `ALLOW`/`DENY`, actor, action, resource, reasonCode, policyVersion |
| `OPERATOR_COMMAND_RESULT` | Sau lời gọi `JobOperator` | Accepted/failed, execution ID mới nếu có, mã lỗi chuẩn hóa |
| `BATCH_EXECUTION_OUTCOME` | Khi có trạng thái execution đáng tin cậy | Execution ID, trạng thái cuối, thời điểm, correlation ID |
| `OPERATOR_PERMISSION_CHANGED` | Khi cấp, thu hồi, giới hạn hoặc gia hạn quyền | Người thay đổi, chủ thể nhận quyền, before/after, scope, approval reference |
| `OPERATOR_PERMISSION_REVIEWED` | Khi kết thúc đợt rà soát quyền | Người xác nhận, tập quyền đã xem, phát hiện, quyết định giữ/thu hồi |

Mỗi event nên có `eventId` độc lập, `occurredAt` UTC, phiên bản schema và danh tính thành phần phát sinh; `requestId` có thể lặp giữa nhiều event thuộc cùng một lệnh. Không sử dụng một khóa duy nhất trên `requestId` cho bảng audit vì sẽ làm mất các pha của cùng giao dịch.

Ví dụ **bị từ chối khi restart khác tenant**:

~~~json
{
  "schemaVersion": 1,
  "eventType": "OPERATOR_AUTHZ_DECISION",
  "eventId": "4fb91441-68f8-43b9-a85b-04fb5a689421",
  "occurredAt": "2026-11-26T03:15:22Z",
  "requestId": "req-c3dd97",
  "correlationId": "trace-2af413",
  "actor": {"subject": "ops-042", "type": "HUMAN", "authn": "OIDC"},
  "action": "RESTART",
  "resource": {
    "environment": "production",
    "tenantId": "tenant-b",
    "jobName": "invoiceReconcileJob",
    "executionId": 7812
  },
  "decision": "DENY",
  "reasonCode": "TENANT_SCOPE_MISMATCH",
  "policyVersion": "batch-rbac-2026-11"
}
~~~

Audit cần đủ dữ kiện để tái dựng **đánh giá quyền tại thời điểm xảy ra sự kiện**, vì role và policy sau đó có thể thay đổi. Nếu quyền được kế thừa từ group trong IAM, nên ghi nguồn cấp quyền hoặc tham chiếu đến snapshot quyền hiệu lực có phiên bản.

Một bảng lưu sự kiện append-only có thể thiết kế như sau (minh họa PostgreSQL, lược bớt trường theo tổ chức):

~~~sql
CREATE TABLE batch_operator_audit (
    event_id          UUID PRIMARY KEY,
    event_type        VARCHAR(64) NOT NULL,
    occurred_at       TIMESTAMPTZ NOT NULL,
    request_id        VARCHAR(128) NOT NULL,
    correlation_id    VARCHAR(128),
    actor_subject     VARCHAR(200) NOT NULL,
    target_subject    VARCHAR(200),
    environment       VARCHAR(40) NOT NULL,
    tenant_id         VARCHAR(100),
    job_name          VARCHAR(200),
    execution_id      BIGINT,
    action            VARCHAR(64) NOT NULL,
    decision          VARCHAR(16),
    outcome           VARCHAR(32),
    reason_code       VARCHAR(100),
    policy_version    VARCHAR(80),
    approval_ref      VARCHAR(128),
    event_details     JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX ix_operator_audit_request
    ON batch_operator_audit (request_id, occurred_at);

CREATE INDEX ix_operator_audit_scope_time
    ON batch_operator_audit (tenant_id, job_name, occurred_at DESC);
~~~

Chỉ tài khoản dịch vụ audit được `INSERT`; tài khoản đọc báo cáo chỉ được `SELECT`; không cho đường quản trị batch thông thường `UPDATE`/`DELETE` lịch sử. Với yêu cầu tuân thủ cao, xuất bản sao sang kho immutable/WORM, áp dụng retention, phân vùng bảng theo thời gian và kiểm tra tính toàn vẹn. Quyền đọc audit cũng cần giới hạn, vì log có thể bộc lộ thông tin về job và người vận hành.

**Không ghi** access token, refresh token, mật khẩu, connection string, secret trong JobParameters, dữ liệu cá nhân của item, payload chưa lọc hoặc stack trace có bí mật. Chỉ lưu tham số đã được allowlist hoặc fingerprint/hash phù hợp; mã lỗi chuẩn hóa thay cho thông điệp exception thô. IP nguồn chỉ có giá trị khi lấy từ proxy/gateway đáng tin cậy, không dùng IP như căn cứ định danh duy nhất.

## 5. Luồng từ yêu cầu operator đến kết quả job

~~~mermaid
sequenceDiagram
    actor Operator
    participant API as API quản trị
    participant Policy as Authorization policy
    participant Audit as Audit store
    participant JO as JobOperator
    participant Repo as JobRepository
    Operator->>API: RESTART execution #7812 + identity
    API->>Repo: Tra metadata execution / scope
    API->>Policy: Kiểm tra actor, action, tenant, job, môi trường
    Policy-->>API: ALLOW hoặc DENY + reason
    API->>Audit: Ghi OPERATOR_AUTHZ_DECISION
    alt DENY
        API-->>Operator: 403 với lỗi an toàn
    else ALLOW
        API->>JO: restart(7812)
        JO->>Repo: Tạo/cập nhật execution
        JO-->>API: execution mới hoặc lỗi
        API->>Audit: Ghi OPERATOR_COMMAND_RESULT
        API-->>Operator: Kết quả lời gọi điều khiển
        Repo-->>Audit: Sự kiện trạng thái qua listener/reconciler
    end
~~~

Các điểm thiết kế cần được áp dụng nhất quán:

1. Đặt mọi thao tác điều khiển phía sau một **audited service/facade**. Endpoint, CLI, scheduler và dịch vụ nội bộ phải đi qua cùng một policy.
2. **Ghi quyết định quyền bền vững trước khi gọi lệnh đặc quyền.** Với lệnh nhạy cảm, nếu không thể ghi audit, từ chối thao tác và báo động vận hành (fail closed).
3. Ghi kết quả gọi `JobOperator` với execution ID mới hoặc mã lỗi. **Kết quả lời gọi không mặc nhiên có nghĩa job đã `COMPLETED`**.
4. Ghi trạng thái cuối qua `JobExecutionListener`/event hoặc đối soát từ `JobExplorer`/`JobRepository`. Chấp nhận các sự kiện có thể đến trễ khi worker phân tán.
5. Ghi sự kiện `DENY` cả khi request bị chặn sớm ở gateway, security filter, `@PreAuthorize` hay API authorization handler. Nếu chỉ audit bên trong service, một số request 401/403 sẽ không đến được service.

### 5.1. Ví dụ Java: bảo vệ lệnh restart

Đoạn sau minh họa cấu trúc cho ứng dụng dùng Spring Batch và Spring Security. `OperatorPermissionPolicy`, `TenantScopeResolver` và `OperatorAuditSink` là các interface do ứng dụng cài đặt; `OperatorAuditSink` phải ghi vào kho bền vững. Ví dụ tập trung vào luồng bảo vệ, nên chưa bao gồm HTTP controller và cách lưu database.

~~~java
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.explore.JobExplorer;
import org.springframework.batch.core.launch.JobOperator;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Service;

record BatchTarget(String tenantId, String jobName, long sourceExecutionId) {}

interface OperatorPermissionPolicy {
    boolean mayRestart(Authentication actor, BatchTarget target);
}

interface TenantScopeResolver {
    // Chỉ đọc scope đã được server kiểm chứng/gán khi tạo execution.
    String fromPersistedExecution(JobExecution execution);
}

interface OperatorAuditSink {
    // Các phương thức phải ghi bền vững, có eventId riêng và idempotent theo eventId.
    void decision(String requestId, String actor, String action,
                  BatchTarget target, boolean allowed, String reasonCode);
    void commandResult(String requestId, String actor, String action,
                       BatchTarget target, String result,
                       Long newExecutionId, String reasonCode);
}

@Service
public class AuditedRestartService {
    private final JobExplorer jobExplorer;
    private final JobOperator jobOperator;
    private final TenantScopeResolver scopeResolver;
    private final OperatorPermissionPolicy permissionPolicy;
    private final OperatorAuditSink audit;

    public AuditedRestartService(
            JobExplorer jobExplorer,
            JobOperator jobOperator,
            TenantScopeResolver scopeResolver,
            OperatorPermissionPolicy permissionPolicy,
            OperatorAuditSink audit) {
        this.jobExplorer = jobExplorer;
        this.jobOperator = jobOperator;
        this.scopeResolver = scopeResolver;
        this.permissionPolicy = permissionPolicy;
        this.audit = audit;
    }

    public long restart(long executionId, Authentication actor, String requestId)
            throws Exception {
        // Authenticated actor và requestId chuẩn hóa ở gateway/controller.
        JobExecution previous = jobExplorer.getJobExecution(executionId);
        if (previous == null) {
            audit.decision(requestId, actor.getName(), "RESTART",
                    null, false, "TARGET_NOT_FOUND");
            throw new AccessDeniedException("Không tìm thấy hoặc không có quyền");
        }

        BatchTarget target = new BatchTarget(
                scopeResolver.fromPersistedExecution(previous),
                previous.getJobInstance().getJobName(),
                executionId);

        boolean allowed = permissionPolicy.mayRestart(actor, target);
        audit.decision(requestId, actor.getName(), "RESTART", target,
                allowed, allowed ? "POLICY_ALLOW" : "POLICY_DENY");

        if (!allowed) {
            throw new AccessDeniedException("Không tìm thấy hoặc không có quyền");
        }

        try {
            long newExecutionId = jobOperator.restart(executionId);
            audit.commandResult(requestId, actor.getName(), "RESTART", target,
                    "ACCEPTED", newExecutionId, null);
            return newExecutionId;
        } catch (Exception ex) {
            // Lưu mã lỗi được chuẩn hóa, không lưu ex.getMessage() tùy ý.
            audit.commandResult(requestId, actor.getName(), "RESTART", target,
                    "FAILED", null, "BATCH_RESTART_FAILED");
            throw ex;
        }
    }
}
~~~

Với production, cần bổ sung kiểm soát ở lớp API cho xác thực, validation và rate limiting; tra cứu metadata với phạm vi an toàn; kiểm tra trạng thái restart; xử lý ngoại lệ theo mã lỗi ổn định. Bảo vệ các lối gọi khác (`start`, `stop`, `abandon`, launcher của scheduler) theo cùng nguyên tắc. Chỉ đặt annotation `@PreAuthorize("hasAuthority('BATCH_RESTART')")` ở controller là chưa đủ: annotation đó kiểm tra quyền tổng quát, còn phạm vi job/tenant cần chính sách trên tài nguyên cụ thể; các sự kiện bị chặn bởi annotation cũng phải được audit ở tầng tương ứng.

Đặc biệt, nếu `audit.commandResult(...)` lỗi **sau khi `jobOperator.restart(...)` đã tạo execution**, việc ném exception ra HTTP không hoàn tác job. Phải đánh dấu command ở trạng thái cần đối soát, cảnh báo và truy vấn `JobRepository` bằng thông tin tương quan; **không tự động gửi lại `RESTART` chỉ vì client nhận lỗi**.

### 5.2. Liên kết với kết quả thực thi

Khi job kết thúc, `JobExecutionListener.afterJob` có thể phát sinh một event chứa `jobExecutionId`, `BatchStatus`, `ExitStatus` và correlation ID đã được thiết lập từ nguồn đáng tin cậy. Event này cần có khóa chống trùng lặp và cơ chế retry riêng. Tránh đặt toàn bộ khả năng ghi audit vào luồng listener mà lỗi ghi log có thể phá vỡ kết quả nghiệp vụ hoặc làm mất sự kiện; có thể dùng outbox bền vững và một consumer đẩy sang audit sink.

Các câu hỏi truy vấn quan trọng:

- `requestId = req-c3dd97`: ai yêu cầu gì, policy chấp nhận hay từ chối?
- `sourceExecutionId = 7812`: thao tác nào đã tạo execution mới và ai khởi tạo?
- `newExecutionId = 7820`: execution cuối cùng `FAILED`, `STOPPED` hay `COMPLETED`?
- Job chưa có outcome quá thời hạn: đang chạy hợp lệ, mất event hay worker gặp sự cố?

## 6. Audit việc cấp, đổi và thu hồi quyền operator

Chỉ ghi hành động `START`/`STOP`/`RESTART` vẫn chưa chứng minh được tại sao một operator có quyền ở thời điểm đó. Phải có luồng audit riêng cho **vòng đời đặc quyền**.

Một event `OPERATOR_PERMISSION_CHANGED` cần nêu:

- **Actor thực hiện thay đổi** và **subject nhận/mất quyền** (hai trường tách biệt).
- Permission, scope (environment, tenant, job group), giá trị **before/after** và thời điểm hiệu lực.
- Nguồn thay đổi: IAM group, role binding, policy-as-code hay quyền tạm thời theo ca trực.
- Lý do, ticket/phê duyệt, người duyệt, thời hạn hết hiệu lực; event áp dụng thành công hay thất bại.
- Phiên bản chính sách và correlation ID để truy vết thay đổi tới hệ thống IAM.

Ví dụ: một nhân viên được cấp quyền `BATCH_ABANDON` cho `invoiceReconcileJob` trong production từ 09:00 đến 10:00 để xử lý một execution mắc kẹt. Bản ghi phải thể hiện rõ người yêu cầu, người phê duyệt, phạm vi hẹp, ngày hết hạn và việc quyền đã thực sự bị thu hồi; tránh ghi chung chung “admin granted access”.

Cơ chế cần có để quyền không âm thầm mở rộng:

1. **Inventory quyền hiệu lực:** định kỳ xuất danh sách subject, group kế thừa, role, scope, expiration và trạng thái tài khoản. Snapshot cần phiên bản vì group membership/policy có thể đổi mà không tạo event ở ứng dụng batch.
2. **Rà soát định kỳ:** chủ job hoặc chủ dữ liệu xác nhận danh sách người được start/restart/stop/abandon trên tenant của mình; ghi `OPERATOR_PERMISSION_REVIEWED` và các ngoại lệ.
3. **Joiner/mover/leaver:** thu hồi khi đổi nhiệm vụ, rời tổ chức hoặc service account không còn sử dụng; kiểm tra quyền tồn dư và credential còn hoạt động.
4. **Tách nhiệm vụ:** người đề nghị nâng quyền không tự duyệt cho mình; quyền `GRANT_PERMISSION` tách khỏi quyền vận hành job nhạy cảm khi quy trình yêu cầu.
5. **Quyền tạm thời:** đặt TTL, giới hạn job/tenant, tự động hết hạn theo IAM, cảnh báo khi quyền tiếp tục tồn tại sau thời điểm dự kiến.

Nếu thay đổi quyền thực hiện trong chính cơ sở dữ liệu ứng dụng, có thể ghi bản ghi thay đổi và outbox audit trong cùng transaction. Nếu IAM nằm ngoài hệ thống, không thể giả định hai hệ thống có transaction chung: cần correlation ID, nhận audit event từ IAM và tiến trình đối soát trạng thái quyền thực tế.

## 7. Bài toán consistency khi mở rộng và chạy phân tán

### 7.1. Multi-instance API và request trùng lặp

Hai API replica có thể đồng thời nhận cùng `requestId` do client retry hoặc timeout. Không dùng audit event để ngăn lệnh chạy lặp; tạo **command ledger/idempotency store** có khóa duy nhất phù hợp (ví dụ subject + action + resource + idempotency key) và lưu tiến độ yêu cầu. Trùng key với cùng payload trả về kết quả trước đó hoặc trạng thái đang xử lý; trùng key nhưng payload khác phải bị từ chối.

Luồng command ledger và lời gọi `JobOperator` có cửa sổ lỗi giữa hai hệ thống. Khi không thể transaction hóa cùng nhau, xử lý trạng thái chưa xác định bằng truy vấn `JobRepository` và reconcile, không phát lại lệnh nguy hiểm một cách mù quáng.

### 7.2. Partitioning, remote chunking và worker identity

Một yêu cầu operator có thể sinh ra nhiều `StepExecution` trên nhiều thread/process/worker. Phân biệt:

- **Initiating actor:** người/service đã yêu cầu `START` hoặc `RESTART` qua control plane.
- **Executing principal:** service account/workload identity của manager và từng worker.
- **Execution correlation:** job execution ID, partition ID, request ID, trace ID, retry attempt, worker instance ID.

Worker có thể retry trên máy khác; identity của worker mới không thay thế initiating actor. Không tin header `X-Operator-Id` do client tự nhập. Khi cần chuyển thông tin qua broker, sử dụng metadata đã được server xác nhận, mTLS/workload identity cho worker, chữ ký hoặc bảo vệ integrity phù hợp; chỉ cho phép dữ liệu truy vết không nhạy cảm đi qua queue.

`SecurityContextHolder` thường gắn với thread; multi-threaded step và xử lý từ xa **không tự bảo đảm principal của request được truyền đúng**. Đưa identity khởi tạo vào execution metadata theo thiết kế, để worker xử lý với **quyền của chính worker**, đồng thời audit vẫn truy ngược được operator đã yêu cầu job.

### 7.3. Giao dịch, outbox và eventual consistency

Audit là hệ thống chứng cứ nên ưu tiên dữ liệu bền vững. Một số lựa chọn:

| Thiết kế | Điểm mạnh | Giới hạn cần xử lý |
|---|---|---|
| Ghi audit đồng bộ trước lệnh | Có bằng chứng `ALLOW`/`DENY` trước khi tác động | Sink lỗi có thể chặn thao tác; phải giám sát độ sẵn sàng |
| Outbox cùng DB với thay đổi ứng dụng | Giảm rủi ro “DB commit nhưng mất event” | Chỉ bao phủ dữ liệu trong transaction đó; không tự bảo đảm atomically với job/broker bên ngoài |
| Event bus với retry và consumer idempotent | Phù hợp nhiều replica/worker | Có thể giao nhận ít nhất một lần, trùng/lệch thứ tự |
| Reconcile audit với `JobRepository` và IAM | Phát hiện event thất lạc/trạng thái chưa rõ | Cần lưu khóa tương quan và quy tắc đối soát rõ ràng |

Dùng `eventId` làm khóa chống xử lý trùng tại consumer. Không tuyên bố “exactly once” xuyên DB, message broker và worker khi chưa có cơ chế giao dịch thực sự bao phủ toàn bộ. Định nghĩa trạng thái chưa kết luận rõ ràng như `PENDING_RECONCILIATION`, không ghi `FAILED` hoặc `COMPLETED` theo phỏng đoán.

## 8. Khả năng quan sát và bảo vệ kho audit

Audit bảo mật nên có đường lưu trữ, quyền truy cập và retention được xác định riêng với log ứng dụng. Bộ chỉ số hữu ích gồm:

- Số quyết định `DENY` theo action, environment, reasonCode; phát hiện tăng đột biến theo thời gian.
- Số lần `ABANDON`, thay đổi concurrency hoặc cấp quyền cao; cảnh báo khi không có approval reference.
- Tỷ lệ lệnh có decision nhưng thiếu command result; lệnh có execution mới nhưng thiếu outcome quá ngưỡng.
- Độ trễ ghi audit, số event trong outbox chưa gửi, số sự kiện lỗi schema, số lần audit sink unavailable.
- Chênh lệch giữa snapshot quyền IAM và quyền đã được phê duyệt; tài khoản hết hạn nhưng vẫn còn quyền.

Không đưa `userId`, `requestId`, `jobExecutionId` vào label Prometheus có cardinality cao. Các giá trị đó nên nằm trong log/tracing hoặc bản ghi audit có thể tra cứu, còn metric dùng nhãn ít biến thiên như `action`, `environment`, `decision` và `reasonCode`.

Định kỳ kiểm tra ai đã truy vấn hoặc xuất dữ liệu audit; đảm bảo đồng bộ thời gian giữa các node, phân tách quyền quản trị log với quyền vận hành batch, mã hóa dữ liệu phù hợp, có chính sách retention và xóa theo quy định nội bộ. Với sự kiện bắt buộc phải giữ lâu dài, kiểm tra cả khả năng khôi phục và tính toàn vẹn của bản lưu trữ.

## 9. Kịch bản thực tế và tiêu chí kiểm thử

**Tình huống:** tại production, `invoiceReconcileJob` xử lý dữ liệu theo tenant bằng partitioning trên tám worker. Execution `7812` của tenant B bị `FAILED`. Operator thuộc tenant A có role `BATCH_OPERATOR` cố yêu cầu restart execution này.

1. API xác thực operator, truy metadata của execution `7812` và tìm tenant B từ nguồn đã kiểm chứng.
2. Policy xác nhận role cho phép hành động `RESTART` nói chung nhưng scope chỉ bao phủ tenant A; quyết định `DENY`.
3. Audit lưu `OPERATOR_AUTHZ_DECISION` với `TENANT_SCOPE_MISMATCH`, không gọi `JobOperator.restart`, trả lỗi không tiết lộ dữ liệu tenant B.
4. Operator được cấp đúng scope tenant B theo quy trình phê duyệt. Sự kiện `OPERATOR_PERMISSION_CHANGED` ghi thời hạn hiệu lực và người duyệt.
5. Khi operator retry với quyền hợp lệ, audit ghi `ALLOW`, sự kiện lời gọi tạo execution mới, và cuối cùng ghi outcome thực từ `JobRepository`. Mỗi partition liên kết execution mới để điều tra khi cần.

Bộ ca kiểm thử tối thiểu:

| Ca kiểm thử | Kỳ vọng |
|---|---|
| Operator không xác thực | Gateway trả `401`, có audit security phù hợp; không có lời gọi điều khiển job |
| Role đúng nhưng tenant/job sai scope | `DENY` có reasonCode, không rò rỉ chi tiết execution |
| `RESTART` hợp lệ nhưng batch đã hoàn tất/không restart được | `ALLOW` và command `FAILED` có mã lỗi nghiệp vụ; không ghi nhầm `COMPLETED` |
| `STOP` được tiếp nhận nhưng worker chưa dừng | Ghi lệnh đã tiếp nhận; outcome theo trạng thái execution thực |
| Hai API replica nhận lại cùng idempotency key | Không tạo hai thao tác điều khiển độc lập; audit và command ledger đối soát được |
| Audit store lỗi trước thao tác đặc quyền | Fail closed; không gọi `JobOperator` |
| Audit store lỗi sau khi lệnh đã tác động | Cảnh báo và reconcile bằng `JobRepository`; không blind retry |
| Worker retry/chuyển máy | Ghi được worker identity mới, vẫn truy về initiating actor |
| Quyền tạm thời hết hạn hoặc bị thu hồi | Request tiếp theo bị từ chối; có event thay đổi quyền |
| Thay đổi policy hoặc group trong IAM | Snapshot quyền và lịch sử policy giải thích được quyết định cũ |

Một bài kiểm tra hoàn chỉnh phải xác minh cả **security outcome** (cho phép/từ chối chính xác) lẫn **evidence outcome** (có đủ event, liên kết được request → command → execution → kết quả). Test môi trường phân tán cần cố ý gây timeout, mất kết nối, message trùng và worker restart để đo khả năng đối soát.

## 10. Checklist triển khai

- [ ] Có danh mục action, role, tenant, job group, environment và các điều kiện cấp quyền cụ thể.
- [ ] Tất cả API, scheduler và đường gọi trực tiếp `JobOperator` đi qua cùng điểm kiểm soát authorization/audit.
- [ ] Ghi bền vững cả `ALLOW` và `DENY`; các trường hợp bị chặn ở lớp security cũng được ghi nhận.
- [ ] Sự kiện decision, command result, final outcome và permission change có identity, timestamp UTC, correlation ID và policy version.
- [ ] Audit không chứa secret, dữ liệu item hoặc payload nhạy cảm; người vận hành không có quyền sửa lịch sử.
- [ ] Retry, multi-instance, partitioning và remote worker có idempotency, identity tương quan và đối soát.
- [ ] Có chính sách fail closed cho thao tác đặc quyền, cảnh báo mất audit và runbook xử lý lệnh ở trạng thái chưa xác định.
- [ ] Có inventory quyền hiệu lực, rà soát định kỳ, thu hồi quyền hết hạn và bằng chứng phê duyệt cho thao tác nhạy cảm.

**Nguyên tắc cốt lõi:** Quyền operator phải gắn với hành động *và* phạm vi tài nguyên cụ thể; audit phải chứng minh được ai có quyền, quyền được dùng thế nào, lệnh có thực sự tác động và job đã kết thúc ra sao. Trong Spring Batch mở rộng, kết luận đáng tin cậy đến từ việc liên kết chính sách IAM, quyết định ở control plane, sự kiện tác động của `JobOperator` và trạng thái thực từ `JobRepository`.
