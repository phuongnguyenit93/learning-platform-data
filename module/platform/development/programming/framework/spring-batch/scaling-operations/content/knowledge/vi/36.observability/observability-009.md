# Audit restart và operator action trong Spring Batch

## Mục tiêu bài học

Một Spring Batch job xử lý 35 triệu giao dịch gặp lỗi ở partition thứ 19. Lúc 03:15, operator nhấn **Restart** trên dashboard. Giao diện báo “đã gửi lệnh”, nhưng vài phút sau xuất hiện hai `JobExecution` mới, worker cũ còn chạy và downstream có message trùng. Sau sự cố, đội kỹ thuật cần biết: **ai ra lệnh, với quyền nào, nhắm đúng execution nào, lệnh đã thật sự thực hiện hay chưa, và dữ liệu có bị ghi hai lần không?**

Một dòng log `Restart requested` hay trạng thái cuối `COMPLETED` không đủ trả lời. Có thể dashboard nhận HTTP 202, `JobOperator.restart` trả execution ID hoặc timeout sau khi JobRepository đã ghi nhận execution mới. Worker từ xa có thể tiếp tục xử lý sau khi manager mất kết nối. Vì vậy cần **audit trail bền vững, có cấu trúc, liên kết được ý định điều khiển với JobRepository, worker progress và business effects**.

**Audit restart và operator action** là việc lưu vết các thao tác quản trị batch theo vòng đời **yêu cầu → xác thực/cho phép → lưu durable intent → dispatch → framework response → observed outcome → business reconciliation**.

Bài thuộc chương **Observability**, module **SPRING_BATCH_SCALING_OPERATIONS**: mở rộng Spring Batch qua multi-threaded step, parallel steps, partitioning và xử lý phân tán; đo bottleneck, bảo đảm thread safety, retry/restart và vận hành job theo tài nguyên thực tế.

Sau bài, bạn sẽ:

- Phân biệt audit events, application logs, traces, metrics, JobRepository và business ledger.
- Định nghĩa audit cho `start`, `stop`, `restart`, `abandon`, replay, backfill, checkpoint repair và thay đổi chính sách.
- Ghi đúng `actor`, `approvalId`, `actionId`, `idempotencyKey`, `jobInstanceId`, `jobExecutionId` và business period.
- Không đánh đồng **command accepted**, **dispatch**, **JobExecution COMPLETED** và **business correctness**.
- Thiết kế bảng command state và append-only audit events trong PostgreSQL.
- Minh họa Java Spring Batch 5.x gọi `JobOperator` với durable policy/audit boundary.
- Xử lý race giữa controller, JobRepository, remote workers và message broker.
- Bảo vệ audit bằng IAM, retention, tamper evidence, schema và quy định dữ liệu nhạy cảm.
- Kiểm thử crash windows, triển khai metrics/trace correlation và runbook điều tra sự cố.

## 1. Audit operator action là gì?

**Operator action** là thao tác của con người hoặc automation nhằm thay đổi vòng đời batch: khởi chạy, stop, restart, abandon, replay hoặc thay đổi một policy điều phối.

Audit cần trả lời sáu câu hỏi:

| Câu hỏi | Thông tin tối thiểu |
| --- | --- |
| **Ai?** | Principal/service identity, actor type, on-behalf-of |
| **Làm gì?** | Command type, target job/instance/execution |
| **Khi nào?** | UTC timestamp, action sequence, source system |
| **Vì sao?** | Reason, incident/ticket và business justification |
| **Được phép?** | Authz decision, policy version, approval reference |
| **Kết quả?** | Dispatch result, JobRepository observation, business reconciliation |

Ví dụ một audit record chỉ có `operator=alice, action=restart, time=03:15` còn thiếu: restart **execution nào**, kỳ dữ liệu nào, có được approved không, và JobOperator có tạo execution mới hay không.

### Audit là lịch sử, không phải một status hiện tại

Một command có thể sinh nhiều sự kiện:

~~~text
ACTION_REQUESTED
AUTHORIZATION_APPROVED
POLICY_CHECK_PASSED
COMMAND_DURABLY_ACCEPTED
DISPATCH_STARTED
FRAMEWORK_RESPONSE_OBSERVED
JOB_EXECUTION_OBSERVED
BUSINESS_RECONCILIATION_PASSED
ACTION_FINALIZED
~~~

Nếu response timeout, cần thêm `DISPATCH_OUTCOME_UNKNOWN`. Không sửa sự kiện REQUESTED thành COMPLETED và xoá mất lịch sử.

## 2. Audit khác log, trace, metric và JobRepository

| Nguồn | Mục đích | Không đủ để chứng minh |
| --- | --- | --- |
| **Audit ledger** | Ai/được phép/đã yêu cầu và kết quả điều khiển | Toàn bộ DB locks/worker details |
| **Application logs** | Debug và execution diagnostics | Durable, đầy đủ mọi action, không bị sửa |
| **Distributed tracing** | Liên kết spans qua services | Cất giữ mọi action nếu sampling/retention |
| **Metrics** | Rate/latency/error ratio/SLO | Actor, reason, approval của action cụ thể |
| **Spring Batch JobRepository** | Job/Step status, checkpoint, metadata | Operator identity, quyền và lý do |
| **Business ledger/outbox** | Transaction commit, idempotent event effects | Chính sách bảo mật/approval |
| **Scheduler logs** | Trigger/misfire/dispatch | Restart checkpoint và business correctness |

Một câu query `BATCH_JOB_EXECUTION.STATUS='COMPLETED'` không cho biết operator nào đã bấm restart. Audit `COMMAND_ACCEPTED` không cho biết job đã hoàn thành. Cần **liên kết nguồn sự thật phù hợp**, không coi một bảng là toàn bộ bằng chứng.

## 3. Những operation cần audit

| Operation | Đích | Rủi ro |
| --- | --- | --- |
| `START_JOB` | Job + identifying params | Nhầm businessDate, tạo trùng instance |
| `RESTART_EXECUTION` | Failed/Stopped JobExecution | Replay chunks/side effects |
| `REQUEST_STOP` | Running JobExecution | Inflight chunks/remote worker vẫn commit |
| `ABANDON_EXECUTION` | Một execution theo runbook | Không còn đường restart bình thường |
| `BACKFILL_PERIOD` | Business period cũ | Trộn nguồn, sửa dữ liệu đã publish |
| `REPLAY_MESSAGE` | DLQ/request/event | Duplicate downstream side effects |
| `RELEASE_QUARANTINE` | Business run/data | Publish dữ liệu chưa chuẩn |
| `PUBLISH_OUTPUT` | Output manifest | Consumer thấy partial dataset |
| `CHANGE_CONCURRENCY` | Thread/pool/partition count | DB saturation, mapping thay đổi |
| `CHANGE_RETRY_POLICY` | Retry/skip/backoff | Retry storm, silently missing records |
| `CHANGE_SCHEDULE` | Cron/cutoff/recovery window | Mất hoặc nhân đôi kỳ xử lý |
| `REPAIR_CHECKPOINT` | JobRepository/ItemStream state | Tác động dữ liệu lớn, quyền đặc biệt |
| `OVERRIDE_POLICY` | Approval/cutoff business rule | Compliance và audit risk |

Các tên là **operation catalog của ứng dụng**, không phải toàn bộ API của Spring Batch.

Automation cũng là actor: auto-restart daemon, Cron controller, Kubernetes operator hoặc system recovery bot. Ghi service identity và policy version cụ thể, không chỉ `actor=SYSTEM`.

## 4. Vòng đời: request không đồng nghĩa job hoàn thành

~~~mermaid
flowchart TD
    U["Human / automation"] --> AU["Authenticate and authorize"]
    AU --> POL{"Policy gate"}
    POL -->|Deny| DEN["Audit DENIED"]
    POL -->|Allow| DB["Persist command intent + audit"]
    DB --> D["Dispatcher"]
    D --> OP["JobOperator"]
    OP --> RES{"Framework response"}
    RES -->|Execution ID| ACK["Audit RESPONSE_OBSERVED"]
    RES -->|Timeout| UNK["Audit DISPATCH_UNKNOWN"]
    ACK --> OBS["Observe JobRepository/workers"]
    UNK --> OBS
    OBS --> VALID["Business reconciliation"]
    VALID --> FIN["Append FINAL OUTCOME"]
~~~

Những mốc **khác nhau**:

1. **REQUESTED:** actor gửi ý định.
2. **APPROVED/DENIED:** policy, authorization và approval.
3. **ACCEPTED:** durable command intent đã được lưu.
4. **DISPATCHING:** chuẩn bị/gửi lệnh tới framework.
5. **FRAMEWORK_RESPONSE:** method trả execution ID, boolean hoặc exception.
6. **EXECUTION_OBSERVED:** JobRepository có execution/step state cụ thể.
7. **BUSINESS_VERIFIED:** output, event, side effects được đối soát.

HTTP `202 Accepted` thường chỉ xác nhận request đã được nhận/queued. Không dùng nó làm bằng chứng `JobExecution COMPLETED`.

## 5. State machine cho một command

~~~mermaid
stateDiagram-v2
    [*] --> REQUESTED
    REQUESTED --> DENIED: Authorization/policy deny
    REQUESTED --> APPROVED: Validation pass
    APPROVED --> DISPATCHING: Durable claim
    DISPATCHING --> DISPATCHED: Framework response observed
    DISPATCHING --> UNKNOWN: Timeout/uncertain
    DISPATCHING --> REJECTED: Confirmed framework rejection
    UNKNOWN --> DISPATCHED: Reconciled execution exists
    DISPATCHED --> RUNNING: JobExecution observed
    RUNNING --> COMPLETED: Job + business validation pass
    RUNNING --> FAILED: Execution/reconciliation failed
    DENIED --> [*]
    REJECTED --> [*]
    COMPLETED --> [*]
    FAILED --> [*]
~~~

Đây là state machine **ứng dụng**, không phải enum Spring Batch. Điều quan trọng:

- `UNKNOWN` nghĩa là **chưa biết lệnh đã có tác dụng hay chưa**, không phải “chắc chắn chưa”.
- `DISPATCHED` khác `RUNNING`; `RUNNING` khác `COMPLETED`.
- JobExecution có thể COMPLETED nhưng business validation/file publication vẫn FAIL.
- DENIED do quyền/policy khác REJECTED do framework từ chối.
- Dispatch retry khi UNKNOWN phải có **reconciliation** trước để không tạo duplicate action.

## 6. Identity và correlation: dùng đúng loại ID

| ID | Vai trò |
| --- | --- |
| `actionId` | Identity ổn định của một logical operator command |
| `idempotencyKey` | Chống gửi lại cùng command do HTTP/network retries |
| `requestId` | Identity một HTTP/API attempt, có thể đổi qua retry |
| `traceId` | Liên kết spans, có thể thiếu nếu sampling |
| `approvalId` | Approval có target, scope và expiry |
| `actorId` | Principal/service identity được xác thực |
| `jobName` | Định nghĩa Job |
| `jobInstanceId` | Logical instance theo job name + identifying params |
| `oldJobExecutionId` | Attempt đang được restart/stop |
| `newJobExecutionId` | Attempt mới được framework tạo nếu restart |
| `stepExecutionId` | Worker Step attempt cụ thể |
| `businessRunId` | Domain identity xuyên các executions |
| `partitionName` | Logical input scope, không phải hostname |
| `sourceVersion` | Snapshot đầu vào bất biến |
| `messageCorrelationId` | Ghép request/reply; không mặc định là business idempotency |

**Không dùng JobExecution ID làm idempotency key của business event** vì nó đổi khi restart. Không dùng trace ID làm action ID nếu trace có thể sampled hoặc bị thay đổi giữa retries.

## 7. Authentication, authorization và phê duyệt

Một lệnh restart production cần:

- SSO/OIDC/mTLS/service account identity đáng tin.
- RBAC/ABAC theo environment, job name, business period, operation.
- Reason và incident/ticket reference khi rủi ro cao.
- Approval có scope và thời hạn; two-person rule cho abandon, bypass cutoff, checkpoint repair hoặc replay tiền.
- Audit DENIED theo chính sách bảo mật, tránh làm lộ thông tin nhạy cảm.
- Recheck JobRepository và ownership **ngay trước dispatch**, không dùng trạng thái cũ tại thời điểm approve.

### Quyền minh họa

| Role | Start nonprod | Restart prod failed | Stop prod | Abandon/repair |
| --- | --- | --- | --- | --- |
| Developer | Theo scope | Không mặc định | Không mặc định | Không |
| Operator | Theo scope | Có điều kiện | Theo policy | Approval cao |
| Incident commander | Theo incident | Theo incident | Theo incident | Có thể cần two-person |
| Recovery bot | Job allow-list | Transient trong window | Giới hạn | Không mặc định |
| Auditor | Chỉ đọc | Không | Không | Không |

**Không tin `X-User` do client tự nhập**. Actor identity phải lấy từ security context/verified gateway. Approval `APR-123` cho restart execution #8100 không được dùng lại để abandon execution #9100.

## 8. Event schema có cấu trúc

~~~json
{
  "schemaVersion": 1,
  "actionId": "example-uuid",
  "eventSequence": 3,
  "eventType": "DISPATCH_STARTED",
  "occurredAt": "2026-11-26T03:15:02.345Z",
  "operation": "RESTART_EXECUTION",
  "actor": {
    "principal": "ops-alias-17",
    "type": "HUMAN",
    "authnMethod": "SSO"
  },
  "authorization": {
    "decision": "ALLOW",
    "policyVersion": "batch-ops@12",
    "approvalId": "APR-123"
  },
  "target": {
    "jobName": "settlementJob",
    "jobInstanceId": 7021,
    "oldExecutionId": 8100,
    "businessRunId": "settlement-2026-11-25-v1"
  },
  "reasonCode": "TRANSIENT_DB_FAILURE",
  "requestId": "request-example",
  "traceId": "trace-example"
}
~~~

IDs chỉ **minh họa**. Production nên dùng UUID đúng chuẩn và actor ID theo định danh tổ chức, không lưu raw token/PII.

Event `ACTION_REQUESTED` chứa **ý định ban đầu**. Khi JobRepository xác nhận execution mới, hãy append event `EXECUTION_OBSERVED`, **không ghi đè** REQUESTED.

## 9. Current command state và append-only event history

Một hệ thống audit có thể tách:

1. `operator_action` lưu **state hiện tại** để dispatcher/reconciler truy vấn nhanh.
2. `operator_audit_event` lưu toàn bộ **sự kiện bất biến** để kiểm toán.

~~~mermaid
flowchart LR
    R["Operator request"] --> C[("operator_action state")]
    C --> E[("operator_audit_event append-only")]
    C --> D["Dispatcher"]
    D --> J[("Spring Batch JobRepository")]
    J --> REC["Reconciler"]
    REC --> E
    REC --> C
    E --> SIEM["Archive / SIEM"]
~~~

Nếu chỉ UPDATE một hàng từ REQUESTED sang COMPLETED, bạn mất lịch sử DENIED/timeout/dispatch retries. Nếu chỉ lưu events mà không có projection/index, dispatcher có thể khó tìm các action UNKNOWN cần phục hồi. Hai cấu trúc bổ sung nhau.

## 10. PostgreSQL schema cho command và event

~~~sql
CREATE TABLE operator_action (
    action_id UUID PRIMARY KEY,
    environment TEXT NOT NULL,
    operation TEXT NOT NULL,
    idempotency_scope TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    actor_type TEXT NOT NULL,
    reason_code TEXT NOT NULL,
    incident_id TEXT,
    approval_id TEXT,
    job_name TEXT NOT NULL,
    job_instance_id BIGINT,
    target_execution_id BIGINT,
    business_run_id TEXT,
    source_version TEXT,
    identifying_params_digest CHAR(64),
    state TEXT NOT NULL,
    new_execution_id BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    version BIGINT NOT NULL DEFAULT 0,
    UNIQUE (
        environment, operation,
        idempotency_scope, idempotency_key
    )
);

CREATE TABLE operator_audit_event (
    audit_event_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,
    action_id UUID NOT NULL
        REFERENCES operator_action(action_id),
    event_seq INTEGER NOT NULL CHECK (event_seq > 0),
    event_type TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    actor_id TEXT NOT NULL,
    payload JSONB NOT NULL,
    prev_event_hash CHAR(64),
    event_hash CHAR(64),
    UNIQUE (action_id, event_seq)
);

CREATE INDEX idx_operator_action_target
    ON operator_action (
        environment, job_name, target_execution_id
    );

CREATE INDEX idx_operator_action_pending
    ON operator_action (state, updated_at);

CREATE INDEX idx_operator_audit_time
    ON operator_audit_event (occurred_at, audit_event_id);
~~~

### Quy tắc

- `operator_action` có thể UPDATE state/version qua optimistic locking.
- `operator_audit_event` chỉ INSERT theo quyền ứng dụng; audit/account này không được phép UPDATE/DELETE lịch sử.
- Cột hash chỉ là chỗ chứa dữ liệu; **chưa có hash chain** nếu chưa thực hiện canonical hashing, verification và external anchoring.
- `new_execution_id` NULL cho đến khi có evidence framework/reconciler.
- Một action có thể có nhiều dispatch attempts và observed events.

## 11. Durable request và audit event trong cùng transaction

Khi nhận request mới, ghi command intent và REQUESTED audit event trong cùng database transaction:

~~~sql
BEGIN;

INSERT INTO operator_action (
    action_id, environment, operation,
    idempotency_scope, idempotency_key,
    actor_id, actor_type, reason_code, incident_id,
    approval_id, job_name, job_instance_id,
    target_execution_id, business_run_id,
    source_version, identifying_params_digest, state
)
VALUES (
    :actionId, :environment, :operation,
    :scope, :idempotencyKey,
    :actorId, :actorType, :reasonCode, :incidentId,
    :approvalId, :jobName, :jobInstanceId,
    :targetExecutionId, :businessRunId,
    :sourceVersion, :paramsDigest, 'REQUESTED'
);

INSERT INTO operator_audit_event (
    action_id, event_seq, event_type, actor_id, payload
)
VALUES (
    :actionId, 1, 'ACTION_REQUESTED',
    :actorId, CAST(:sanitizedPayload AS jsonb)
);

COMMIT;
~~~

Đây là **SQL minh họa có bind parameters**; cần thực hiện bằng JDBC/Spring transaction manager thật.

Nếu `idempotencyKey` đã tồn tại trong cùng scope, tra action cũ và so **request fingerprint**. Nếu key trùng nhưng target/payload khác, trả conflict, không tự coi là cùng action.

Ghi durable intent **trước** khi gọi JobOperator giúp không mất toàn bộ bằng chứng khi JVM chết ngay sau dispatch. Nhưng vẫn có **dual-system gap** giữa audit DB và JobRepository nếu hai resource managers không commit atomically; cần reconciler.

## 12. Audit integrity, retention và timestamps

Append-only là chính sách lưu sự kiện, không phải claim rằng DBA không bao giờ sửa được dữ liệu. Các lớp bảo vệ:

- DB account chỉ có quyền INSERT/SELECT audit events, không UPDATE/DELETE.
- Backup, access log và tách quyền operator khỏi quyền sửa audit storage.
- Retention theo luật/hợp đồng; không cho operator xóa lịch sử hành động của chính mình.
- Với mức integrity cao, hash chain có **canonical encoding**, periodic verification và external signed/WORM anchor.
- Archive có manifest/checksum và có thể truy lại incident từ đầu đến cuối.
- Không lưu password, access token, full JobParameters hoặc PII không cần thiết.
- Timestamp từ DB để phản ánh thời điểm lưu bền; kèm client/request time khi hữu ích.
- `event_seq` phân biệt thứ tự causal trong **một action**; không dựa chỉ vào milliseconds giữa nhiều JVM.

Với hash chain giả định:

\[
h_i=\mathrm{SHA256}
  (\mathrm{domain}\parallel h_{i-1}\parallel
   \mathrm{canonicalEventBytes}_i)
\]

Nếu admin quyền cao có thể sửa chain rồi tính lại hashes, chain **không chống giả mạo tuyệt đối** nếu không có anchor độc lập. Chọn khả năng bảo vệ theo threat model.

### Khi nào cần redaction?

Nếu event chứa business key/parameters nhạy cảm, dùng allow-list và sanitized payload trước lưu. Một fingerprint SHA-256 của input có entropy thấp cũng có thể bị đoán; cân nhắc HMAC theo threat model và tránh coi hash thông thường là ẩn danh hóa hoàn toàn.

## 13. Audit database và JobRepository không tự commit cùng nhau

Giả sử audit store ở DB A, JobRepository của Spring Batch ở DB B:

~~~text
T0  Audit DB A commit command ACCEPTED
T1  Dispatcher claim DISPATCHING
T2  JobOperator.restart(#8100)
T3  JobRepository B tạo JobExecution #8155
T4  Response network bị mất
T5  Dispatcher chưa ghi DISPATCHED vào DB A
~~~

Nếu chỉ nhìn audit DB A thấy DISPATCHING rồi gọi restart tiếp, bạn có thể gửi lệnh trùng. Không có transaction JDBC đơn giản nào tự bảo đảm atomicity giữa DB A, DB B, broker và external API.

### Giao thức xử lý

1. Ghi **durable command intent** trước dispatch.
2. Durable claim/conditional transition để chỉ một dispatcher sở hữu lệnh.
3. Ghi audit event DISPATCH_STARTED.
4. Gọi JobOperator **ngoài transaction audit DB**.
5. Ghi framework response nếu nhận; timeout thì chuyển `UNKNOWN`.
6. Reconciler truy vấn JobRepository và worker/side effects.
7. Chỉ thử lại dispatch nếu đã chứng minh an toàn; không dựa riêng vào thời gian chờ.
8. Gắn execution mới tìm được vào **action cũ**, không tạo action mới do response mất.

**`@Transactional` của audit store không tự bao phủ JobOperator lẫn business resources**. Nếu phân phối command qua queue/outbox, chính queue cũng có khả năng redelivery; idempotency và reconciliation vẫn cần.

## 14. Idempotency của operator action

HTTP client có thể gửi lại request do timeout, double-click hoặc retry ở gateway:

~~~text
POST /batch/operator-actions/restart
Idempotency-Key: ops-incident-123-attempt-1

{
  "oldJobExecutionId": 8100,
  "approvalId": "APR-123",
  "reasonCode": "DB_RECOVERED"
}
~~~

Một **idempotency key** đại diện cho **một logical command**, ổn định khi cùng request được gửi lại. Cặp environment + operation + scope + key có thể có unique constraint.

- Nếu key đã tồn tại với **cùng normalized request**, trả lại actionId/status cũ.
- Nếu key đã tồn tại với **target/payload khác**, trả conflict và ghi audit security event.
- Một yêu cầu restart mới hợp lệ sau FAILED cần actionId/ticket/approval riêng, không recycle key để làm mất lịch sử.
- Retention của key phải đủ để ngăn retry muộn tạo lại destructive command.

**Idempotency của command không phải idempotency của business writer**. API chống double-click không ngăn worker ghi tiền hai lần khi chunk replay. Business operation cần ledger/unique event identity riêng.

## 15. Conditional state transition để chỉ một dispatcher claim

Một controller chỉ được dispatch sau khi thắng compare-and-set ở database:

~~~sql
UPDATE operator_action
SET state = 'DISPATCHING',
    updated_at = now(),
    version = version + 1
WHERE action_id = :actionId
  AND state = 'APPROVED'
  AND version = :expectedVersion
RETURNING action_id, target_execution_id, version;
~~~

Nếu trả 0 rows, state đã đổi hoặc dispatcher khác claim. **Không gọi JobOperator** dựa vào kết quả `SELECT state` cũ.

Trong cùng DB transaction, append sự kiện `DISPATCH_CLAIMED` với eventSeq được cấp theo serializing rule. Đừng commit state rồi mới thử INSERT audit event ở transaction khác nếu invariant yêu cầu không bao giờ thiếu audit.

### Fencing cũ/mới

Khi controller A claim rồi GC pause, lease hết hạn và controller B reclaim, A không được UPDATE status của B. Dùng `claimToken` hoặc `recoveryGeneration` trong điều kiện cập nhật. Tuy nhiên fencing DB không thể thu hồi một lần gọi JobOperator đã đến framework, vì vậy **cần reconcile thực tế**.

## 16. Java: dispatcher dùng JobOperator và durable audit store

Ví dụ Java 17, Spring Batch 5.x. Các thành phần `OperatorActionStore` là interface ứng dụng, chưa có implementation; transaction và policy là trách nhiệm triển khai.

~~~java
import java.util.UUID;
import org.springframework.batch.core.launch.JobOperator;

record RestartAction(
        UUID actionId, long oldExecutionId) {}

interface OperatorActionStore {
    // Atomic claim of APPROVED -> DISPATCHING
    // together with append-only audit event.
    boolean claimApprovedAction(UUID actionId);

    // Persist response and event in one DB transaction.
    void recordFrameworkResponse(
            UUID actionId, long newExecutionId);

    // Do not claim the job definitely did not start.
    void recordOutcomeUnknown(
            UUID actionId, String errorCategory);
}

public final class AuditedRestartDispatcher {

    private final JobOperator operator;
    private final OperatorActionStore store;

    public AuditedRestartDispatcher(
            JobOperator operator,
            OperatorActionStore store) {
        this.operator = operator;
        this.store = store;
    }

    public String dispatch(RestartAction action) {
        if (!store.claimApprovedAction(action.actionId())) {
            return "ALREADY_CLAIMED_OR_INVALID_STATE";
        }

        try {
            long newId = operator.restart(
                    action.oldExecutionId());

            store.recordFrameworkResponse(
                    action.actionId(), newId);

            return "DISPATCHED newExecutionId=" + newId;
        } catch (Exception failure) {
            store.recordOutcomeUnknown(
                    action.actionId(),
                    failure.getClass().getSimpleName());

            return "UNKNOWN_RECONCILE_BEFORE_RETRY";
        }
    }
}
~~~

### Những giới hạn cần nhớ

- Code **không** tự triển khai authentication, approval, policy, SQL, JobRepository lookup hay reconciler.
- `claimApprovedAction` phải là durable CAS, không chỉ đọc state rồi ghi lại.
- Cách `catch (Exception)` đánh UNKNOWN bảo thủ: exception có thể do framework chắc chắn từ chối hoặc do response/audit DB lỗi; production nên phân loại theo exception và evidence.
- Nếu `recordOutcomeUnknown` cũng lỗi, action có thể còn DISPATCHING. Reconciler cần quét command stale.
- Nếu JobOperator trả ID nhưng audit update lỗi, câu `catch` vẫn đánh UNKNOWN; đây là trạng thái **không được nói chắc restart thất bại**.
- Return `DISPATCHED` không phải `JobExecution COMPLETED`.
- API của các phiên bản Spring Batch có thể thay đổi; kiểm tra dependencies/JobOperator configuration thực tế trước khi dùng.

**Không giữ audit row lock xuyên suốt quá trình JobExecution kéo dài.** DB transaction của command claim phải đóng trước call bên ngoài.

## 17. API dashboard nên hiển thị điều gì?

Một API bất đồng bộ trả action identity thay vì khẳng định job hoàn tất:

~~~json
{
  "actionId": "b49356d6-e2ae-4c83-aec4-d1a90e96f92b",
  "operation": "RESTART_EXECUTION",
  "oldExecutionId": 8100,
  "state": "ACCEPTED",
  "statusUrl": "/batch/operator-actions/b49356d6-e2ae-4c83-aec4-d1a90e96f92b"
}
~~~

UI cần tách:

- `ACCEPTED`: durable request có trong audit store.
- `APPROVED`: policy/authorization cho phép.
- `DISPATCHED`: framework response đã được quan sát.
- `RUNNING`: JobRepository có new JobExecution đang chạy.
- `EXECUTION_COMPLETED`: framework execution hoàn tất.
- `BUSINESS_VERIFIED`: output/side effects qua quality gate.

Với `UNKNOWN`, hiển thị **“Đang đối soát — không tự gửi lại”**. Một HTTP 202 không phải kết quả cuối và mất HTTP response không chứng minh lệnh chưa được lưu.

## 18. JobOperator.restart và JobInstance identity

`JobOperator.restart(oldExecutionId)` tạo JobExecution mới cho **cùng JobInstance** nếu restart hợp lệ:

~~~text
jobName=settlementJob
businessDate=2026-11-25        [IDENTIFYING]
sourceGeneration=V17           [IDENTIFYING]

JobInstance 7021
  JobExecution 8100 FAILED
  JobExecution 8155 STARTED -> COMPLETED
~~~

Audit lưu old execution ID, new execution ID, JobInstance ID và identifying parameter fingerprint. Nếu operator đổi `run.id=now` để ép launch, một **JobInstance mới** có thể được tạo; phải audit operation mới như `START_JOB`/`REPROCESS_REVISION` chứ không ngụy trang thành restart.

Business event identity không được dùng JobExecution ID vì nó thay đổi theo attempts. Khi cần replay-safe, dựa vào stable business event ID/source version và idempotent writer.

## 19. Stop request không có nghĩa worker đã dừng

Với Spring Batch, `stop` thường là yêu cầu dừng có kiểm soát:

~~~text
03:15 STOP_REQUESTED execution 8100
03:15 JobOperator xử lý stop request
03:16 StepExecution vẫn đang xử lý chunk dài
03:17 Chunk commit/rollback
03:17 JobExecution STOPPED (nếu stop hoàn tất)
~~~

Audit cần lưu các mốc:

- `STOP_REQUESTED`.
- `STOP_DISPATCHED`.
- `STOPPING_OBSERVED`.
- `STOPPED_OBSERVED`.
- `INFLIGHT_WORK_RECONCILED`.

Giá trị trả về của `JobOperator.stop` (theo API/version) **không chứng minh mọi worker JVM đã ngừng** hoặc mọi transaction đã rollback.

Kubernetes kill/SIGKILL khác graceful stop: audit phải lưu mechanism thật, không đánh `STOPPED_CLEANLY` chỉ vì pod biến mất. Khi worker còn STARTED stale, cần recovery/ownership runbook trước khi restart.

## 20. Abandon và checkpoint repair là thao tác rủi ro cao

`ABANDON_EXECUTION` thường thể hiện quyết định không tiếp tục execution qua restart bình thường. Nó không phải cách mặc định chữa transient failure.

Audit tối thiểu:

- Lý do không thể/không nên restart.
- Dữ liệu/StepExecution/checkpoint đã đối soát.
- Approval cấp cao/two-person nếu policy yêu cầu.
- Bản snapshot trước/sau và đường recovery thay thế.
- Phạm vi JobInstance/business period và downstream effect.

**Không sửa trực tiếp các bảng `BATCH_JOB_EXECUTION` hay `BATCH_STEP_EXECUTION` bằng SQL ad hoc để mở khóa**. Nếu phải repair, cần runbook, backup, scope lock, dry-run, audit before/after (sanitized), approval và independent verification.

## 21. Reconcile JobRepository khi dispatch UNKNOWN

Một reconciler có thể:

1. Lấy old JobExecution và JobInstance từ JobRepository/JobExplorer.
2. Tìm new JobExecutions của cùng JobInstance.
3. So framework timestamps, trạng thái, action ownership và command correlation.
4. Xác minh remote worker/StepExecution còn chạy không.
5. Đối soát checkpoint và business side effects khi kết quả commit chưa rõ.
6. Append `EXECUTION_OBSERVED` kèm evidence source.
7. Chuyển action sang DISPATCHED/REJECTED nếu đủ chứng cứ, hoặc giữ UNKNOWN.
8. Với lệnh rủi ro cao, escalates nếu chưa phân giải thay vì auto-dispatch lại.

### Cẩn trọng khi quy kết execution cho một action

Việc thấy một execution start gần thời điểm command **không tự chứng minh** command đó tạo execution, nếu có automation khác cùng nhắm JobInstance. Cần target-level ownership, durable action correlation và framework log/ledger liên quan.

Một execution đã COMPLETED vẫn có thể cần business reconciliation, vì file output/outbox hoặc external API có thể chưa hoàn tất đúng contract.

## 22. Action-level idempotency khác target-level exclusion

Hai operators có thể gửi **hai idempotency keys hợp lệ khác nhau** cùng restart execution #8100:

~~~text
Operator A: action A1, key incident-900-retry-1
Recovery bot: action B7, key auto-recover-900
Cả hai thấy JobExecution 8100 FAILED
~~~

Unique key theo action chỉ chống **retry cùng request**, không ngăn hai command cạnh tranh trên **cùng target**. Cần thêm admission/ownership theo logical key như `environment + jobName + jobInstanceId + operation risk`, tùy policy.

### Durable lock không phải Java synchronized

Các controller có thể chạy nhiều JVM/pods. `synchronized` trong một instance không bảo vệ instance khác. Dùng database conditional claim, advisory lock được quản lý đúng, distributed lease/fencing hoặc cơ chế coordination phù hợp.

Một mẫu schema phụ trợ:

~~~sql
CREATE TABLE operator_target_claim (
    environment TEXT NOT NULL,
    job_instance_id BIGINT NOT NULL,
    operation_group TEXT NOT NULL,
    action_id UUID NOT NULL,
    claim_generation BIGINT NOT NULL,
    lease_until TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (
        environment, job_instance_id, operation_group
    )
);
~~~

Bảng do ứng dụng tự tạo, **không phải schema Spring Batch**. Tính an toàn phụ thuộc protocol update/reclaim và state reconciliation, không chỉ câu `CREATE TABLE`.

### Lease hết hạn chưa chứng minh JobOperator call cũ không tồn tại

Controller cũ có thể bị pause sau khi đã gửi restart. Khi lease expire, controller mới phải tra JobRepository và worker ownership trước khi retry command; database fencing chỉ chặn ghi status cũ, **không hủy external action đã phát**.

## 23. Local/remote partitioning: audit logical work identity

Với partitioning, operator có thể stop/restart manager JobExecution trong khi nhiều worker StepExecutions đang xử lý các ranges khác nhau.

~~~mermaid
flowchart TB
    ACT["Action A1: stop JobExecution 8100"] --> M["Manager JobExecution 8100"]
    M --> P0["StepExecution P0 COMPLETED"]
    M --> P1["StepExecution P1 STARTED"]
    M --> P2["StepExecution P2 FAILED"]
    P1 --> W["Remote worker JVM"]
    W --> DB[("Business DB + JobRepository")]
    DB --> REC["Audit outcome reconciler"]
    REC --> ACT
~~~

Audit/evidence nên gắn:

- `jobInstanceId`, `jobExecutionId`, `stepExecutionId`.
- Stable `partitionName` và input range/shard identity.
- `workerInstanceId` ở từng observation, không dùng làm logical partition identity.
- `sourceVersion`/`inputManifestId`.
- Last confirmed checkpoint/committed business key nếu contract cho phép log.
- Worker status/progress, broker request/reply evidence.
- Kết quả stop/restart của từng StepExecution khi cần.

### Điều cần phân biệt

- Manager nhận stop request **không** chứng minh worker đang xử lý partition đã rollback.
- Worker báo COMPLETED **không** chứng minh reply đã tới manager.
- StepExecution status **không** thay kiểm tra business side effects.
- Khi worker đổi JVM sau restart, partition logic phải giữ nguyên để trace theo kỳ.
- Với file output, audit nên trỏ tới **validated attempt manifest** được finalizer chọn, không chỉ host path.

Một report về operator restart phải ghi lại **những partitions thực sự re-executed**, không suy từ “toàn job restart” rằng mọi partition đã chạy lại.

## 24. Remote chunking: correlation và ACK khác business idempotency

Remote chunking có nhiều loại identity:

~~~text
managerJobExecutionId = 8100
chunkRequestId         = chunk-0051
messageCorrelationId   = corr-e8e
workerDeliveryId       = broker-delivery-934
businessEventId        = payment-event-123
operatorActionId       = operator-a1
~~~

Các ID có mục đích riêng. Reply timeout có thể xảy ra **sau khi worker DB commit**:

~~~text
Manager sends chunk C51
Worker processes and commits business DB
Worker reply is lost
Manager sees timeout
Operator requests restart
Chunk/business event may be processed again
~~~

Audit event nên ghi `CHUNK_REPLY_OUTCOME_UNKNOWN` với references; sau đó reconciler tra JobRepository, business ledger và broker status. Không khẳng định `worker_failed` chỉ vì manager không nhận reply.

**Message correlation ID không phải business idempotency key mặc định**. Sau restart, cùng business event có thể nằm trong chunk khác, correlation mới và broker delivery mới.

## 25. Audit identifying JobParameters và source snapshot

Một JobInstance có identity theo Job name và **identifying JobParameters**. Ví dụ:

~~~text
jobName=settlementJob
businessDate=2026-11-25       [IDENTIFYING]
sourceGeneration=V17          [IDENTIFYING]
cutoffUtc=2026-11-25T17:00Z   [IDENTIFYING]
scheduledAtUtc=...            [NON-IDENTIFYING]
~~~

Operator restart **cùng JobInstance** không được âm thầm thay `businessDate`/sourceGeneration. Nếu tạo `run.id=now` identifying để “ép launch”, rất có thể đó là `START_JOB`/`REPROCESS_REVISION` mới, phải có audit operation và approval khác.

### Fingerprint có version

Không hash chuỗi `JobParameters.toString()` không ổn định. Hãy:

1. Allow-list identifying keys ảnh hưởng dữ liệu, không đưa secrets.
2. Chốt thứ tự keys và type representation.
3. Canonicalize dates/UTC, boolean, number và null.
4. Length-prefix hoặc serialize bằng canonical format không mơ hồ.
5. Gắn `parameterFingerprintVersion`.
6. Lưu fingerprint SHA-256 hoặc HMAC nếu threat model cần.
7. Khi JobOperator tạo execution mới, so identifying subset với original instance.

Hash giúp phát hiện drift; nó **không chứng minh source bytes còn nguyên**. Với file input, còn cần immutable URI/object generation và checksum; với DB source cần cutoff/watermark/query contract.

## 26. Trace context và structured logs xuyên dịch vụ

Một hành động từ dashboard có thể đi qua:

~~~mermaid
sequenceDiagram
    participant UI as Operator UI
    participant API as Control API
    participant A as Audit DB
    participant D as Dispatcher
    participant JR as JobRepository
    participant W as Remote Worker
    participant B as Business DB

    UI->>API: Restart request actionId=A1
    API->>A: REQUESTED/APPROVED
    API-->>UI: 202 actionId=A1
    D->>A: Claim A1
    D->>JR: JobOperator.restart oldExecution=8100
    JR-->>D: newExecution=8155
    D->>A: Dispatch result
    JR->>W: Resume/re-execute Steps
    W->>B: Business updates
    W-->>JR: Step progress/results
    D->>A: Observed execution/reconciliation
~~~

### Gợi ý context fields

- `actionId`: xuyên API, dispatcher, reconciler.
- `traceId`/`spanId`: từng request/interaction, sampling có thể khiến thiếu spans.
- `jobInstanceId`, `jobExecutionId`, `stepExecutionId`: context của framework.
- `businessRunId`, `sourceVersion`, `partitionName`: context nghiệp vụ.
- `operatorPrincipal`: lưu ở audit; khi propagate vào logs phải giảm thiểu dữ liệu nhạy cảm.
- `requestId`/`messageCorrelationId`: technical transport correlation.

**MDC/ThreadLocal không tự qua executor threads, broker messages hoặc remote JVM**. Muốn trace xuyên worker cần chủ động propagate context qua headers/ExecutionContext/request metadata phù hợp, tuân security and size limits. Không serialise security principal hay JWT raw để “tiện truy vết”.

## 27. Ví dụ structured log và phân biệt phase

Một log từ control API:

~~~text
event=operator_action_requested
actionId=A1
operation=RESTART_EXECUTION
actorType=HUMAN
actorRef=operator-17
jobName=settlementJob
oldJobExecutionId=8100
businessRunId=settlement-2026-11-25-v1
policyDecision=PENDING
~~~

Một log từ dispatcher:

~~~text
event=operator_action_dispatch_finished
actionId=A1
oldJobExecutionId=8100
newJobExecutionId=8155
dispatchOutcome=RESPONSE_OBSERVED
durationMs=147
~~~

Một log từ reconciler:

~~~text
event=operator_action_business_verified
actionId=A1
newJobExecutionId=8155
jobBatchStatus=COMPLETED
partitionCountExpected=24
partitionCountValidated=24
businessKeyMismatch=0
publishedOutputVersion=manifest-v3
~~~

Ba log trên giải thích các **phase khác nhau**. Audit events trong database vẫn là durable record; logs chỉ hỗ trợ vận hành/search.

### Giới hạn logging

Không log full JobParameters/payload, customer IDs, passwords, broker credentials. Không đưa raw SQL có bind values nhạy cảm vào audit. Dùng sanitized IDs/hashed references theo chính sách.

## 28. Metrics: đo command và outcome riêng

| Metric gợi ý | Ý nghĩa |
| --- | --- |
| `batch_operator_actions_requested_total` | Yêu cầu điều hành đã nhận |
| `batch_operator_actions_denied_total` | Từ chối authorization/policy |
| `batch_operator_actions_approved_total` | Qua policy gate |
| `batch_operator_dispatch_attempts_total` | Số lần dispatcher gọi framework |
| `batch_operator_dispatch_unknown_total` | Response không chắc chắn |
| `batch_operator_restarts_observed_total` | Restart execution mới có evidence |
| `batch_operator_stops_observed_total` | Stop state được JobRepository xác nhận |
| `batch_operator_actions_reconciled_total` | Actions có kết luận cuối |
| `batch_operator_actions_stale_total` | Command kẹt UNKNOWN/DISPATCHING |
| `batch_operator_command_latency_seconds` | Request→dispatch latency |
| `batch_operator_reconcile_latency_seconds` | UNKNOWN→evidence latency |
| `batch_operator_business_verify_seconds` | Dispatch→business PASS latency |
| `batch_audit_append_failures_total` | Không ghi audit durable được |
| `batch_audit_integrity_check_failures_total` | Hash/sequence/archive check fail |
| `batch_operator_policy_override_total` | High-risk override requests |

Các tên chỉ **minh họa**, không tự có từ Spring Batch/Actuator. Nhóm metric `outcome` cần phân biệt ACCEPTED, UNKNOWN, DENIED và business VERIFIED.

### Tránh high cardinality

Dùng labels ổn định như `operation`, `jobName`, `environment`, `outcome`, `errorCategory`. Không đặt `actorId`, `actionId`, `jobExecutionId`, `requestId` hoặc `businessRunId` thành Prometheus labels tăng vô hạn. Đặt exact identifiers trong structured logs/audit.

## 29. Dashboard: từ câu hỏi vận hành tới drill-down

Một dashboard tốt trả lời theo thứ tự:

1. Bao nhiêu operator actions đang `REQUESTED/APPROVED/DISPATCHING/UNKNOWN`?
2. Có action nào đã quá `maxUnknownAge` mà chưa reconcile không?
3. Ai đã override restart policy trong production?
4. JobInstance nào có nhiều restart attempts trong một khoảng thời gian?
5. Sau operator restart, bao nhiêu executions COMPLETED nhưng output validation FAIL?
6. Có JobExecution mới không có matching approved action/scheduler trigger?
7. Có command STOP được chấp nhận nhưng worker còn active quá grace period?
8. Các late restarts có gây trễ `publishSLA` hoặc backlog kỳ kế tiếp không?

Mỗi datapoint drill-down đến **audit action timeline**, JobRepository, StepExecutions, logs/traces, business reconciliation và downstream manifest/outbox evidence.

**Không thiết kế nút Restart nổi bật trong cùng màn hình trước khi hiển thị target identity, risk, approval và action status**; một click nhầm ở production có thể tạo side effects không đảo ngược được.

## 30. Alert security và anomaly detection

Các cảnh báo hữu ích:

- Operator attempt `ABANDON_EXECUTION` ngoài incident/approval.
- Tài khoản không đúng role gọi restart production.
- Nhiều denied actions liên tiếp từ cùng principal/source.
- Two-person approval bị tái dùng cho target không khớp.
- Nhiều actions trên cùng JobInstance trong thời gian ngắn.
- JobExecution restart xuất hiện **không có action/scheduler evidence**.
- Audit append failures hoặc audit DB read-only/outage.
- UNKNOWN commands quá hạn reconciliation.
- Stop accepted nhưng worker vẫn tạo business commits quá deadline.
- Audit integrity verification fail, archive missing hoặc có chỉnh sửa trái phép.

Bảo mật và vận hành phải phối hợp: một alert có thể là auto-recovery hợp lệ hoặc tài khoản automation bị compromise. Cần bằng chứng scope, actor identity, policy version và asset impact trước khi kết luận.

## 31. Audit volume và throughput scaling

Một job 30 triệu items không nhất thiết cần **30 triệu audit operator events**. Audit operator action khác per-item processing telemetry.

- Audit có một event cho REQUESTED/APPROVED/DISPATCHED/OBSERVED/FINAL của mỗi **operator command**.
- Step/chunk/item progress thường dùng metrics và sampled/structured logs.
- Business effects đáng kiểm toán có **business ledger/outbox** riêng.
- Khi có nhiều partitions, ghi summary + references thay vì mọi heartbeat là audit event.
- Cần lưu **mọi high-risk operator action** theo policy, không sampling audit bừa bãi.

### Capacity của audit DB

Audit writes tăng khi automation liên tục restart, khi JobRepository có nhiều job hoặc khi ghi detailed events. Cần:

- Index theo actor/job/actionId/time nhưng tránh quá nhiều indexes khiến INSERT chậm.
- Partition/archival theo thời gian cho audit table lớn.
- Backup và retention theo compliance.
- Theo dõi latency và transaction pool của audit DB.
- Có retention riêng cho command state và immutable event history.
- Thiết kế ingestion backpressure khi SIEM/archive down; **không xóa durable events** chỉ để giảm hàng đợi.

**Không đưa mọi business record vào operator audit**: tăng I/O, chi phí và rủi ro dữ liệu nhạy cảm mà không cải thiện accountability của action điều hành.

## 32. Khi audit storage bị lỗi: fail closed hay degraded?

Một câu hỏi policy quan trọng: operator có được restart production khi audit DB không ghi được sự kiện REQUESTED không?

Các lựa chọn:

| Chính sách | Phù hợp | Rủi ro |
| --- | --- | --- |
| **Fail closed** cho high-risk commands | Stop/restart/abandon/replay tài chính yêu cầu accountability | Recovery chậm khi audit DB outage |
| **Durable local/secondary queue** | Có hạ tầng bảo đảm intent không mất | Cần replay/backup/duplicate handling |
| **Break-glass** theo incident policy | Sự cố nghiêm trọng cần khôi phục ngay | Phải có approval độc lập và hậu kiểm bắt buộc |
| **Best-effort logging only** | Thao tác low-risk theo policy | Không đủ cho critical compliance |

**Không tuyên bố đã audit chỉ vì `logger.info` chạy thành công**: logs có thể không durable hoặc SIEM mất kết nối. Nếu policy đòi durable audit trước hành động, thiếu audit DB phải **chặn hành động** hoặc dùng break-glass protocol đã được chấp thuận.

### Break-glass không phải bỏ qua lịch sử

Nếu tổ chức cho phép cứu sự cố khi audit DB down, ghi sự kiện vào một **durable, independently controlled emergency ledger** kèm incident/actor/approval và sau đó reconcile/import vào audit chính, giữ provenance. Không để “khẩn cấp” thành nút tắt audit thường xuyên.

## 33. Quyền đọc audit và quyền thực hiện hành động

Đừng dùng cùng một role có quyền:

- Restart job production.
- Thay đổi policy phê duyệt.
- Sửa/xóa audit events.
- Xóa logs/traces.
- Chỉnh JobRepository metadata.

Tách quyền:

- **Operator:** gửi action trong scope được cấp, xem kết quả cần thiết.
- **Approver:** phê duyệt risk/target cụ thể, không tự động execute.
- **Auditor:** read-only toàn bộ lịch sử được phép, không dispatch.
- **Audit writer service:** append events/update current state theo contract, không DELETE history.
- **DB administrator:** quản trị storage qua break-glass và database audit.
- **Automated recovery:** quyền hẹp theo allow-list, retry budget và business window.

### Đọc audit cũng là hoạt động nhạy cảm

Audit có thể tiết lộ operator identity, tên khách hàng, business volume và system architecture. Áp dụng row-level/tenant isolation, encryption, access logging và data minimization theo policy. Với yêu cầu pháp lý, người xem records nhạy cảm cũng có thể cần được audit.

## 34. Schema evolution và các event types

Audit phải sống lâu hơn vòng đời một service release. Ví dụ một sự kiện năm trước dùng `restartRequested` và hệ thống mới dùng `ACTION_REQUESTED`.

Cần:

- `auditSchemaVersion` rõ ràng.
- Định nghĩa event type stable và schema registry/documentation tương ứng.
- Additive changes + defaults hoặc migration/replay strategy.
- Không đổi ý nghĩa `COMPLETED` từ “framework completed” sang “business verified” mà giữ cùng event name.
- Tránh custom payload tùy ý khiến auditor không parse được.
- Test old events vẫn hiển thị trong dashboard phiên bản mới.
- Khi đổi canonical hash method, pin `hashAlgorithmVersion`/`canonicalizerVersion`.
- Báo cáo truy vấn audit phải chỉ ra timeline với source schema, không tự bỏ unknown event types.

**Một audit event không parse được sau deploy cũng là sự cố observability**, vì không thể khôi phục lịch sử trách nhiệm khi cần điều tra.

## 35. Forensic timeline: restart thành công nhưng response thất lạc

Một tình huống cụ thể:

~~~text
03:15:00.100  Operator A gửi action A1, restart #8100
03:15:00.120  Audit DB commit ACTION_REQUESTED
03:15:00.170  Policy APPROVED, claim DISPATCHING
03:15:00.220  Dispatcher gọi JobOperator.restart(8100)
03:15:00.310  JobRepository tạo JobExecution #8155
03:15:00.330  Dispatcher mất kết nối trước khi nhận response
03:15:02.000  Dashboard thấy DISPATCH_OUTCOME_UNKNOWN
03:15:04.000  Reconciler tìm thấy #8155 của JobInstance #7021
03:15:04.100  Audit append EXECUTION_OBSERVED
03:50:00.000  JobExecution #8155 COMPLETED
03:55:00.000  Business reconciliation PASS
03:56:00.000  Output manifest COMMITTED
03:56:00.100  Action A1 FINALIZED (BUSINESS_VERIFIED)
~~~

**Cách xử lý sai:** UI báo “restart thất bại, thử lại”, operator gửi `JobOperator.restart(8100)` thêm lần nữa trước khi re-query. Có thể tạo competing actions hoặc hiểu nhầm exception khi instance đang chạy.

**Cách xử lý đúng:** giữ action A1 ở `UNKNOWN`, đọc JobRepository, tìm execution #8155 có bằng chứng liên kết; update audit timeline rồi theo dõi tới business outcome cuối. Không xóa dấu vết timeout; đó là một phần rất quan trọng của forensic history.

### Nếu không chứng minh được #8155 do action A1?

Giữ **uncertainty** hoặc escalates theo runbook, không tự gắn sai mối quan hệ. Có thể có automation B gửi restart cùng lúc; target-level ownership/trace cần đủ để phân biệt.

## 36. SQL truy vết action, events và JobRepository

Với schema ở phần 10, truy vấn timeline của một action:

~~~sql
SELECT
    a.action_id,
    a.operation,
    a.state AS current_state,
    a.job_name,
    a.job_instance_id,
    a.target_execution_id,
    a.new_execution_id,
    e.event_seq,
    e.event_type,
    e.occurred_at,
    e.actor_id,
    e.payload
FROM operator_action AS a
JOIN operator_audit_event AS e
  ON e.action_id = a.action_id
WHERE a.action_id = :actionId
ORDER BY e.event_seq;
~~~

Tìm các action UNKNOWN hoặc DISPATCHING bị kẹt:

~~~sql
SELECT
    action_id,
    job_name,
    job_instance_id,
    target_execution_id,
    state,
    updated_at,
    now() - updated_at AS state_age
FROM operator_action
WHERE state IN ('UNKNOWN', 'DISPATCHING')
  AND updated_at < now() - INTERVAL '5 minutes'
ORDER BY updated_at;
~~~

`5 minutes` là ngưỡng **minh họa**; production căn cứ p99 dispatch/reconcile latency và incident policy.

### Kết nối với JobRepository

Bảng Spring Batch thường có tên dạng `BATCH_JOB_INSTANCE`, `BATCH_JOB_EXECUTION`, `BATCH_STEP_EXECUTION` với schema theo version. Có thể đọc qua `JobExplorer`/repository APIs thay vì join thẳng các tables, nhất là khi JobRepository ở database khác.

Nếu thực hiện read-only SQL phục vụ điều tra:

- Dùng đúng schema/version của Spring Batch đang triển khai.
- Không UPDATE metadata để “sửa trạng thái”.
- Không suy output đúng chỉ vì `STATUS=COMPLETED`.
- Nếu JobRepository và audit ở DB khác, query liên kết nhiều nguồn là **logical join**, không phải một transaction snapshot cross-DB mặc định.

### Vì sao cần thời gian và event sequence?

`ORDER BY occurred_at` có thể không phản ánh đúng thứ tự các sự kiện đến từ nhiều JVM lệch clock. `event_seq` cấp trong cùng action bảo vệ thứ tự causal của audit timeline; timestamp dùng để đo lag và cross-system correlation.

## 37. Unit test: policy deny, allow và idempotency

Các unit tests nên kiểm tra:

1. Người không có quyền restart production → DENIED, không dispatch.
2. Approval cho execution #8100 không dùng cho #8101.
3. Approval hết hạn, revoked hoặc sai business period → DENIED.
4. Action đã publish output muốn restart destructive → yêu cầu revision/approval.
5. Idempotency key cùng payload → trả existing action.
6. Cùng key khác payload → CONFLICT.
7. `claimApprovedAction` trả false → không gọi JobOperator.
8. `JobOperator.restart` trả ID → state DISPATCHED, **không** business VERIFIED.
9. `JobOperator` timeout → state UNKNOWN, không auto retry.
10. Ghi audit response lỗi sau framework success → vẫn UNKNOWN và cần reconcile.

### Ví dụ JUnit 5 + Mockito

Test đơn vị tối giản cho skeleton phần 16:

~~~java
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.*;

import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.batch.core.launch.JobOperator;

class AuditedRestartDispatcherTest {

    @Test
    void doesNotDispatchWithoutDurableClaim()
            throws Exception {

        JobOperator operator = mock(JobOperator.class);
        OperatorActionStore store =
                mock(OperatorActionStore.class);

        UUID actionId = UUID.randomUUID();
        when(store.claimApprovedAction(actionId))
                .thenReturn(false);

        var dispatcher =
                new AuditedRestartDispatcher(operator, store);

        String result = dispatcher.dispatch(
                new RestartAction(actionId, 8100L));

        assertTrue(result.contains("NOT_CLAIMED"));
        verify(operator, never()).restart(anyLong());
    }

    @Test
    void recordsFrameworkResponseButNotCompletion()
            throws Exception {

        JobOperator operator = mock(JobOperator.class);
        OperatorActionStore store =
                mock(OperatorActionStore.class);

        UUID actionId = UUID.randomUUID();
        when(store.claimApprovedAction(actionId))
                .thenReturn(true);
        when(operator.restart(8100L))
                .thenReturn(8155L);

        var dispatcher =
                new AuditedRestartDispatcher(operator, store);

        String result = dispatcher.dispatch(
                new RestartAction(actionId, 8100L));

        assertTrue(result.contains("8155"));
        verify(store).recordFrameworkResponse(
                actionId, 8155L);
        verify(store, never()).recordOutcomeUnknown(
                any(), anyString());
    }
}
~~~

Code dùng Mockito/JUnit 5; không tự cấu hình Maven/Gradle dependencies hoặc Spring context. Test chỉ chứng minh invocation-level policy; **không chứng minh database transaction, JobRepository restart hay remote workers thực tế**.

## 38. Integration test với JobRepository thật

Một integration test có thể dùng Spring Batch test support cùng database thật (ví dụ PostgreSQL Testcontainers khi schema tương thích):

1. Tạo business run với immutable input V17, identifying JobParameters ổn định.
2. Chạy job và cố ý làm một Step/chunk FAILED sau khi vài giao dịch commit.
3. Assert JobExecution #1 FAILED và JobInstance ID được lưu.
4. Tạo operator action APPROVED, lưu audit REQUESTED trước dispatch.
5. Gọi `JobOperator.restart(oldExecutionId)`.
6. Assert JobExecution mới có **cùng JobInstance ID** và trạng thái phù hợp.
7. Assert action ledger có DISPATCH/OBSERVED events theo sequence.
8. Assert JobExecution COMPLETED **chưa tự** chuyển business verification nếu output chưa kiểm tra.
9. Chạy business reconciliation, assert không missing/duplicate, append BUSINESS_VERIFIED.
10. Thử đổi identifying params tạo instance mới → không gắn nhãn đó là restart cũ.

### Một lưu ý khi test

Mock `JobOperator` được gọi một lần không chứng minh framework restart đúng checkpoint. Cần test **JobRepository/StepExecutions thực** và side effects. Với JobRepository nằm ở DB khác business DB, inject crash ở khoảng commit để chứng minh idempotency.

## 39. Fault injection: ma trận cửa sổ lỗi

| Inject lỗi | Kết quả audit kỳ vọng | Kiểm tra bổ sung |
| --- | --- | --- |
| API chết trước durable intent | Không ACCEPTED, không dispatch | UI có thể gửi lại key |
| API chết sau durable intent trước response | Action tồn tại | GET action theo idempotency key |
| Dispatcher chết trước claim | APPROVED còn pending | Re-dispatch policy |
| Dispatcher chết sau claim trước call | DISPATCHING stale | Reconcile/có thể retry an toàn |
| JobRepository tạo execution, response mất | UNKNOWN → OBSERVED | Không restart thêm |
| Audit DB mất khi ghi response | UNKNOWN/stale | Reconciler tìm JobExecution |
| Hai controllers claim cùng action | Một CAS thắng | Không hai calls |
| Hai actions khác key cùng target | Target exclusion | Không simultaneous restart |
| Stop request accepted, worker còn chạy | STOPPING/UNKNOWN | Không gắn STOPPED sớm |
| Remote chunk reply mất sau DB commit | Outcome UNKNOWN | Ledger chống duplicate |
| Worker JVM chết sau business commit | Execution/recovery evidence | Checkpoint vs DB reconcile |
| JobRepository outage khi operator action | Không false success | Pause/reconcile |
| Outbox publish ACK mất | Có thể duplicate delivery | Consumer inbox |
| Approval bị revoke trước dispatch | DENIED hoặc cancel | Không dùng approval cũ |
| Audit event append failure | Alert/fail closed theo policy | Không drop event lặng lẽ |
| Archive hash chain bị sửa | Integrity alert | External anchor/backup |
| Policy/config deploy giữa approval và call | Revalidate với version | Scope/expiry |
| Operator force-restart sau SLA | Audit late approval | SLA breach vẫn được ghi |

**Fault injection phải assert audit history, framework state và business data**, không chỉ HTTP response. Trạng thái UNKNOWN không được coi là testcase FAIL nếu đó là **trạng thái đúng cho thông tin còn thiếu**; test phải xem có reconciler giải quyết về sau.

## 40. Load testing audit trong môi trường nhiều partitions

Mục tiêu module là scaling workload dữ liệu lớn; audit subsystem không nên trở thành bottleneck chung cho mọi chunk.

Một giả định:

~~~text
24 remote partitions
4 manager JobExecutions active
100 operator/recovery actions per hour
Audit events per action: 5–12
Worker metrics frequency: per 10 seconds
Business ledger events: millions, stored separately
~~~

Không đẩy heartbeat của từng item vào operator audit table. Các thao tác operator rủi ro cao vẫn cần durable records đầy đủ, nhưng per-item progress có thể dùng metrics/logs được kiểm soát.

### Đo các chi phí sau

- p95/p99 durable action INSERT latency.
- Audit database pool wait và write failure rate.
- Query latency theo actionId/jobInstanceId.
- Reconciler scan time cho UNKNOWN commands.
- Event archive lag và integrity verification lag.
- JobRepository read load do quá nhiều status polls.
- Số concurrent operator actions đang chờ ownership.
- Chi phí SIEM export/PII filtering.

**Đừng thêm một query JobRepository mỗi 10 ms cho từng partition chỉ để UI “real time”**. Sử dụng bounded polling, event notifications, caching với stale marker và rate limits theo SLA.

## 41. Case study: 35 triệu giao dịch và hai lần restart

Giả sử hệ thống thanh toán xử lý **35.000.000 giao dịch** qua 24 remote partitions và 8 worker JVM. Đầu vào bất biến `payments-V17`, output đích là ledger PostgreSQL và event outbox cho downstream.

### Lỗi ban đầu

~~~text
02:00 JobInstance 7021, JobExecution 8100 STARTED
03:01 DB deadlocks tăng ở partition 19
03:08 JobExecution 8100 FAILED, 26M events đã commit
03:15 Operator A gửi restart action A1 với approval APR-123
03:15 JobOperator tạo JobExecution 8155
03:15 Response mất, dashboard thấy UNKNOWN
03:16 Recovery bot phát hiện FAILED cũ, định restart tiếp
03:17 Reconciler tìm thấy 8155, ngăn bot dispatch
04:00 JobExecution 8155 COMPLETED
04:08 Reconciliation xác nhận 35M business records hợp lệ
04:10 Outbox/manifest publication đạt policy
~~~

### Nếu audit chỉ là một log dòng

Team không biết restart A1 đã tạo execution hay chưa. Một operator B có thể bấm Restart lần hai, làm StepExecutions chồng lấn hoặc phát side effects trùng; các logs ở nhiều workers có thể không đủ evidence do rotation hoặc sampling.

### Thiết kế có audit

- Actor A được xác thực, approval target bind execution 8100.
- API lưu ACTION_REQUESTED/APPROVED durable và cấp actionId A1.
- Dispatcher claim action, gọi JobOperator.
- Response mất → audit UNKNOWN thay vì FAILED.
- Reconciler tra JobRepository, tìm `8155` cùng JobInstance và worker evidence.
- Target-level claim chặn bot cố restart JobInstance 7021 khi 8155 STARTED.
- Action final chỉ là BUSINESS_VERIFIED sau khi ledger/outbox reconciliation PASS.
- Những side effects bị dedup vẫn được business ledger ghi lại với stable event IDs.

### Thước đo minh họa

| Chỉ số | Giá trị giả định | Ý nghĩa |
| --- | ---: | --- |
| Input unique events | 35.000.000 | Kỳ nghiệp vụ |
| Đã commit trước lỗi | 26.000.000 | Không được xử lý lại thành effect trùng |
| Chưa hoàn thành theo snapshot | 9.000.000 | Phải phục hồi |
| Operator actions requested | 2 | A1 và bot proposal |
| Actions dispatched thực sự | 1 | Target exclusion PASS |
| UNKNOWN outcomes được reconcile | 1 | Response mất được xử lý |
| Duplicate business effects | 0 | Ledger/idempotency PASS |
| Output key mismatches | 0 | Business reconciliation PASS |

Các số đều **giả định**, không phải benchmark thực hay default của Spring Batch. Nếu bot bị chặn trước durable command creation, số “requested” còn tùy semantics event catalog; dashboard phải định nghĩa rõ.

**Bài học:** audit tốt giúp ngăn quyết định lặp khi outcome chưa rõ, nhưng chỉ correctness gate mới chứng minh **không thiếu/trùng dữ liệu**.

## 42. Runbook điều tra operator restart bất thường

**Bước 1 — Khoanh vùng action.** Xác định actionId, actor, operation, environment, target execution/JobInstance và business period.

**Bước 2 — Kiểm tra quyền.** Xác minh principal, role, policy version, approval scope/expiry, incident ticket và dấu vết impersonation.

**Bước 3 — Dựng timeline.** Sắp events theo `eventSeq`; ghi REQUESTED, APPROVED, DISPATCHING, RESPONSE/UNKNOWN, JOB_OBSERVED, FINAL.

**Bước 4 — Xác minh JobRepository.** Old/new JobExecution IDs, JobInstance ID, StepExecutions, timestamps và checkpoint. Không chỉ xem một status cuối.

**Bước 5 — Xác định concurrency.** Có controller/automation nào khác nhắm cùng business run? Target claim và lease/fencing có đúng không?

**Bước 6 — Kiểm tra remote workers/broker.** Manager timeout, chunk replies, active worker instances, unfinished partitions và JobRepository progress.

**Bước 7 — Kiểm tra business effects.** Ledger/unique event IDs, outbox, files/manifest, DLQ và downstream API outcomes. Phân biệt committed vs unknown.

**Bước 8 — Chọn remediation.** Nếu UNKNOWN, reconcile trước khi dispatch. Nếu unauthorized, chặn quyền/rotating credentials/incident response. Nếu duplication, dùng business compensation/reprocess revision.

**Bước 9 — Bảo toàn chứng cứ.** Export audit timeline, signed archive references, logs/traces, DB snapshot ở mức policy cho phép; không xóa failed attempts quá sớm.

**Bước 10 — Đóng incident.** Chỉ khi action outcome, business data, publication và security scope có evidence, ghi root cause và follow-up tests.

### Hành động không nên làm

- Tạo JobInstance mới với `run.id=now` để “thử lại” khi response timeout.
- Đánh dấu action SUCCESS chỉ vì UI HTTP 200.
- Xóa UNKNOWN events để dashboard gọn.
- Sửa JobRepository trực tiếp không có runbook.
- Giảm audit retention để tiết kiệm disk giữa incident.
- Gửi lại payment/email/API khi chưa biết commit outcome.
- Public raw JobParameters hoặc principal tokens trong incident report.

## 43. Các ngộ nhận phổ biến

| Ngộ nhận | Thực tế |
| --- | --- |
| “Log Restart requested đủ làm audit.” | Log có thể mất và thiếu actor, approval, outcome. |
| “HTTP 202 nghĩa restart đã chạy xong.” | Chỉ có thể là command accepted. |
| “JobOperator trả execution ID nghĩa business đúng.” | Cần JobRepository completion và reconciliation. |
| “Timeout nghĩa lệnh chưa được thực hiện.” | Có thể JobExecution mới đã được tạo. |
| “JobExecution COMPLETED nghĩa operator action toàn bộ thành công.” | File/outbox/consumer vẫn có thể FAIL. |
| “Dùng traceId làm unique action ID luôn ổn.” | Trace có sampling/propagation khác command identity. |
| “JobExecutionId là business event idempotency key.” | ID đổi qua restart, không chống duplicate domain. |
| “Idempotency-Key chặn mọi operator race.” | Hai keys khác nhau vẫn nhắm cùng target. |
| “@Transactional bao trùm audit DB, JobRepository và broker.” | Không atomic cross-resource nếu không có protocol tương ứng. |
| “Stop() trả true nghĩa mọi worker đã dừng.” | Stop cần observation, remote workers còn inflight. |
| “Abandon là cách restart nhanh hơn.” | Thường cắt đường restart bình thường, cần policy cao. |
| “@StepScope đảm bảo audit per-thread.” | Scope theo StepExecution, context propagation là vấn đề khác. |
| “PartitionName bằng hostname.” | Partition logical identity phải ổn định qua worker chuyển JVM. |
| “Kafka correlationId là business eventId.” | Hai ID phục vụ mục tiêu khác nhau. |
| “Hash chain bất khả sửa với DB admin.” | Có thể tính lại nếu không có external anchor. |
| “Metrics chi tiết actorId tốt hơn.” | High-cardinality/PII risk; dùng audit/logs. |
| “Audit storage down vẫn có thể chỉ log best-effort.” | High-risk actions có thể yêu cầu fail-closed/break-glass. |
| “Operator có quyền restart thì nên có quyền sửa audit.” | Vi phạm separation of duties. |
| “Sửa JobRepository bằng SQL để bỏ stale STARTED luôn ổn.” | Cần ownership/reconciliation/repair runbook. |
| “Audit mọi item vào cùng table là observability tốt.” | Gây bottleneck, lẫn business ledger và operator audit. |

## 44. Checklist triển khai audit operator action production

### Identity, quyền và phê duyệt

- [ ] Có actor identity đáng tin từ SSO/OIDC/mTLS/gateway đã xác thực.
- [ ] Phân biệt HUMAN và AUTOMATION, ghi `onBehalfOf` khi cần.
- [ ] RBAC/ABAC giới hạn environment, job, business period và operation.
- [ ] High-risk actions yêu cầu reason, incident/ticket và approval đúng scope.
- [ ] Approval có người duyệt, target, thời hạn, policy version và trạng thái revoke.
- [ ] Two-person approval cho các thao tác đặc biệt nếu tổ chức yêu cầu.
- [ ] Operator không có quyền xóa/sửa chính audit events của mình.
- [ ] Các lệnh DENIED cũng được audit theo chính sách bảo mật.
- [ ] Break-glass có independent durable record và hậu kiểm bắt buộc.

### Command identity và lifecycle

- [ ] `actionId` độc lập với HTTP requestId, traceId và JobExecutionId.
- [ ] Idempotency key có scope rõ và payload fingerprint/check conflict.
- [ ] Command intent được ghi durable **trước** JobOperator dispatch.
- [ ] Audit REQUESTED và command state được commit atomically cùng DB resource.
- [ ] State transitions dùng conditional update/optimistic version.
- [ ] Có target-level exclusion cho hai commands khác keys cùng JobInstance.
- [ ] Dispatch timeout dẫn tới UNKNOWN, không tự nhận FAILED.
- [ ] UNKNOWN/DISPATCHING stale được reconciler theo dõi với deadline.
- [ ] Reconciler tra JobRepository và business side effects trước retry.
- [ ] Framework response và observed execution được audit thành events riêng.
- [ ] JobExecution COMPLETED khác BUSINESS_VERIFIED/PUBLISHED.
- [ ] Không đưa `run.id=now` vào identifying parameters chỉ để ép restart.
- [ ] Action `stop`/`abandon` có state/evidence và policy riêng, không dùng chung boolean success.

### Metadata và phân tán

- [ ] Lưu old/new JobExecution IDs, JobInstance ID, businessRunId và source version.
- [ ] Identifying JobParameters có canonical fingerprint/version, không lộ secrets.
- [ ] Source snapshot, cutoff và partition ranges giữ ổn định qua restart.
- [ ] Có `stepExecutionId`, partitionName và workerInstance trong evidence phù hợp.
- [ ] Worker reply lost được ghi UNKNOWN thay vì chắc chắn worker failed.
- [ ] Remote worker ownership/recovery/fencing được kiểm tra trước redispatch.
- [ ] Business event ID bền qua restart, không đồng nhất với correlation ID.
- [ ] Outbox/inbox/idempotency và file manifest có references trong audit.
- [ ] JobRepository và audit DB cross-resource gap có runbook/reconciler.

### Lưu trữ, observability và vận hành

- [ ] Audit events append-only theo DB permissions và policy backup/retention.
- [ ] Hash chain/anchor chỉ được tuyên bố khi đã triển khai và kiểm tra.
- [ ] Audit schema có version và old events vẫn đọc được sau deploy.
- [ ] Không lưu raw tokens, passwords, PII hay full JobParameters tùy tiện.
- [ ] Audit read access cũng được kiểm soát và log khi cần.
- [ ] Structured logs có actionId/phase/old-new execution IDs.
- [ ] Distributed trace propagation không phụ thuộc ThreadLocal qua broker.
- [ ] Metrics có accepted, denied, unknown, reconciliation latency riêng.
- [ ] High-cardinality IDs nằm trong logs/audit, không trong metric labels.
- [ ] Audit DB failure policy rõ: fail-closed hoặc break-glass.
- [ ] Có alert cho unauthorized actions, repeated restarts và audit integrity failures.
- [ ] Có backup/archive, kế hoạch legal hold và retention/test restore.
- [ ] Dispatcher/reconciler có resource budgets, bounded polling, no retry storm.
- [ ] Runbook giữ chứng cứ, xác minh business reconciliation trước đóng incident.

### Kiểm thử

- [ ] Unit test DENIED/APPROVED, expired/revoked approval, scope mismatch.
- [ ] Unit test idempotency key duplicate/conflicting payload.
- [ ] Unit test conditional claim chỉ một dispatcher thắng.
- [ ] Unit test JobOperator response và timeout UNKNOWN.
- [ ] Integration test JobRepository thật, restart cùng JobInstance.
- [ ] Integration test audit transaction và event sequence.
- [ ] Fault injection khi JobRepository tạo execution nhưng response mất.
- [ ] Fault injection audit DB outage và post-dispatch event append failure.
- [ ] Fault injection hai operators cùng restart một execution.
- [ ] Fault injection remote worker còn commit sau manager timeout.
- [ ] Kiểm tra side effects không trùng trên business DB/outbox/file.
- [ ] Kiểm tra SIEM/archive/retention và tamper-evidence theo risk policy.

## 45. Câu hỏi tự kiểm tra

**1. Audit restart cần chứng minh những thông tin nào ngoài JobExecutionId?**

Actor đã xác thực, operation, target JobInstance/business period, reason, approval, policy decision, thời điểm, dispatch attempts, framework outcome và business reconciliation. Một execution ID không cho biết ai yêu cầu và lệnh có được phép không.

**2. Vì sao log dòng “Restart requested” chưa đủ?**

Log có thể rotate/mất, thiếu durable authorization và không liên kết chắc với framework/external side effects. Audit phải có lifecycle bền vững và lịch sử không bị ghi đè.

**3. HTTP 202 Accepted chứng minh job đã restart thành công chưa?**

Chưa. Nó chỉ có thể biểu thị request đã được nhận/queued; cần JobRepository observation và sau đó business verification.

**4. JobOperator.restart trả newExecutionId có chứng minh business output đúng?**

Không. ID chỉ phản ánh framework response tạo/nhận execution. JobExecution có thể fail, file output partial hoặc side effects chưa đối soát.

**5. Dispatcher bị timeout sau khi JobRepository đã tạo execution. Có nên gửi lại restart ngay?**

Không. Ghi UNKNOWN và tra JobRepository/worker/side effects, tránh tạo competing attempts hoặc ghi trùng nghiệp vụ.

**6. Vì sao actionId, requestId và traceId không nên dùng thay nhau?**

Một action có thể có nhiều HTTP attempts/traces; actionId phải bền giữa retries. Trace có thể sampled và requestId có thể đổi.

**7. JobExecutionId có nên dùng làm khóa chống duplicate giao dịch?**

Không mặc định. ID thay qua restart; business event/operation ID phải ổn định xuyên attempts.

**8. Hai operators gửi hai idempotency keys khác nhau cho cùng JobInstance thì API idempotency có ngăn race không?**

Không. Cần **target-level durable exclusion/claim** ngoài dedup từng action.

**9. Tại sao append-only audit table và mutable operator_action table cùng cần thiết?**

Mutable state giúp dispatcher/reconciler tìm hành động cần xử lý; append-only history giữ toàn bộ sequence và bằng chứng phục vụ điều tra.

**10. Có thể gọi toàn bộ action FAILED nếu audit DB update status sau JobOperator.restart bị lỗi không?**

Không. JobOperator có thể đã tạo execution. Cần UNKNOWN và reconciliation.

**11. Stop request đã được JobOperator nhận có nghĩa remote partitions dừng hết không?**

Không. Inflight chunks có thể đang commit, worker cũ có thể không nhận signal; cần observed STOPPED/StepExecution và business state.

**12. Khi nào hành động abandon cần approval cao?**

Khi nó cắt đường restart thông thường hoặc ảnh hưởng checkpoint/recovery data. Mức approval theo risk policy tổ chức, thường không nên tự động hoá như transient retry.

**13. Vì sao audit cần lưu sourceVersion và businessDate?**

Để chứng minh restart đang xử lý đúng immutable input/business period. Nếu đổi source giữa attempts, checkpoint có thể sai dù JobInstance ID giống.

**14. Remote chunk correlationId có phải khóa idempotency ổn định của business event không?**

Không mặc định. Cùng event có thể nằm trong chunk khác sau restart. Cần stable domain event ID và ledger/inbox.

**15. Vì sao hash chain trên audit DB chưa đủ chống admin có quyền cao sửa lịch sử?**

Admin có thể chỉnh events rồi tính lại hashes. Cần external signed anchor/WORM/independent evidence nếu threat model đòi tamper evidence mạnh.

**16. Có nên gắn actorId/actionId/jobExecutionId làm Prometheus labels?**

Không mặc định, vì high cardinality và rủi ro PII. Dùng low-cardinality labels, exact IDs trong structured logs/audit.

**17. Nếu audit DB down, nên cho phép restart production không?**

Phụ thuộc policy. Với high-risk commands, fail-closed hoặc break-glass có durable independent record; không gọi best-effort logger là đầy đủ audit.

**18. Khi operator restart lệnh được approve nhưng JobExecution CREATED trong cùng incident bởi bot khác, có thể gắn execution đó cho action operator không?**

Chỉ khi có evidence liên kết đủ mạnh. Timestamp gần nhau không chứng minh causal attribution; cần ownership và correlation.

**19. Một job có BatchStatus COMPLETED nhưng đối soát file FAIL. Audit action cuối là gì?**

Không được kết luận BUSINESS_VERIFIED. Ghi framework completion và kết quả reconciliation FAIL riêng, có thể chuyển incident remediation theo policy.

**20. Test nào chứng minh tốt nhất hệ thống xử lý response lost?**

Tạo JobExecution trong JobRepository rồi làm mất response trước khi audit ghi DISPATCHED; xác nhận action UNKNOWN, reconciler tìm execution đã có và không dispatch thêm.

**21. Vì sao không audit mọi bản ghi item vào operator_audit_event?**

Đây là audit điều hành, không phải per-item business ledger. Hàng triệu item events có thể gây bottleneck, chi phí và rủi ro dữ liệu; lưu per-item correctness ở domain ledger và metrics phù hợp.

**22. Khi nào có thể đóng operator action/incident là hoàn tất?**

Khi có evidence về request/approval, framework execution, các worker liên quan, business side effects và publication/reconciliation đúng contract; đồng thời outcome UNKNOWN đã được phân giải hoặc lưu escalation rõ ràng.

---

**Ghi nhớ:** Audit restart và operator action là **chuỗi bằng chứng có cấu trúc**, không phải vài dòng log hoặc một cờ success. Hãy lưu **ai yêu cầu, quyền và lý do, target chính xác, durable command identity, từng bước dispatch và trạng thái JobRepository thực tế**. Trong môi trường Spring Batch phân tán, response timeout thường mang nghĩa **UNKNOWN**, không chứng minh lệnh chưa được thực thi. Durable idempotency, target-level ownership, append-only history và reconciler giúp tránh restart trùng; business ledger, outbox, file manifest và output validation mới chứng minh dữ liệu đúng. Chỉ gọi hành động hoàn tất khi **đã phân biệt kết quả điều khiển framework với tác động nghiệp vụ và giữ được bằng chứng có thể kiểm toán**.
