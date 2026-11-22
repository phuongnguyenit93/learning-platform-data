# Audit operator action trong Spring Batch

## 1. Audit operator action là gì?

Trong vận hành Spring Batch, **operator action** là một thao tác quản trị do người vận hành, công cụ nội bộ hoặc hệ thống điều phối chủ động yêu cầu. Ví dụ: chạy một job thủ công để bù dữ liệu, yêu cầu dừng job đang chạy, restart một lần chạy thất bại, hoặc từ bỏ một execution không được tiếp tục. Các thao tác này có thể ảnh hưởng trực tiếp đến dữ liệu, lịch xử lý, trạng thái `JobRepository` và tính đúng đắn khi restart.

**Audit operator action** là việc ghi lại có hệ thống những thao tác ấy để có thể trả lời:

- **Ai** đưa ra yêu cầu? Người dùng được xác thực, service account hay automation nào?
- **Yêu cầu gì**? `START`, `STOP`, `RESTART`, `ABANDON`, hoặc thao tác phục hồi khác?
- **Nhắm tới đâu**? Job name, `JobInstance`, `JobExecution`, kỳ nghiệp vụ hoặc input cụ thể nào?
- **Khi nào** yêu cầu được gửi, được chấp nhận hoặc bị từ chối?
- **Vì sao** operator thực hiện? Có incident/change ticket hoặc ghi chú được kiểm soát không?
- **Kết quả của yêu cầu** là gì? Từ chối do thiếu quyền, lỗi kiểm tra điều kiện, lệnh được tiếp nhận hay không?
- **Batch thực tế ra sao** sau đó? Job có kết thúc `COMPLETED`, `FAILED`, `STOPPED` hay vẫn đang chạy?

Một câu log kiểu `INFO Restarting job` chưa trả lời đủ những câu hỏi này. Audit phải tạo được dấu vết có danh tính, định danh request, trạng thái quyết định và khả năng đối chiếu với metadata Spring Batch.

```text
Operator / Scheduler / Automation
          |
          v
  Authentication + Authorization
          |
          +----> DENIED  ------> Audit: denied attempt
          |
          v
     Command API / Service
          |
          +----> Audit: REQUESTED (bền vững)
          |
          v
       JobOperator / JobLauncher
          |
          +----> Audit: ACCEPTED / FAILED
          |
          v
       JobRepository
          |
          v
      JobExecution / StepExecution
          |
          +----> Job/Step lifecycle events & metrics
```

**Phân biệt từ đầu:** audit của lệnh `RESTART` được chấp nhận không đồng nghĩa job đã hoàn thành. `JobOperator` có thể chấp nhận yêu cầu và tạo execution mới, nhưng quá trình chạy thực tế thất bại sau đó. Cần ghi nhận riêng **kết quả thao tác điều khiển** và **kết quả của batch execution**.

## 2. Mô hình đối tượng và phạm vi kiểm toán

### 2.1. Những API vận hành liên quan

Ví dụ trong **Spring Batch 5.2.x**, `JobOperator` cung cấp các thao tác điều khiển:

| Thao tác | API tiêu biểu 5.x | Ý nghĩa | Điều audit cần phân biệt |
|---|---|---|---|
| Chạy job | `JobOperator.start(jobName, parameters)` hoặc `JobLauncher.run(job, parameters)` | Yêu cầu tạo/lauch execution theo job name và `JobParameters` | Lệnh đã nhận, instance/execution nào được tạo, kết quả sau đó. |
| Chạy instance kế tiếp | `JobOperator.startNextInstance(jobName)` | Dùng `JobParametersIncrementer` để tạo lần chạy logic kế tiếp | Incrementer sinh tham số nào, có cố ý tạo instance mới không? |
| Yêu cầu dừng | `JobOperator.stop(executionId)` | Gửi yêu cầu dừng một execution đang chạy | **Request accepted** khác với đã `STOPPED`. |
| Restart | `JobOperator.restart(executionId)` | Yêu cầu tiếp tục instance qua execution mới khi trạng thái cho phép | ID execution cũ, ID execution mới, outcome. |
| Abandon | `JobOperator.abandon(executionId)` | Đánh dấu execution bị từ bỏ theo quy tắc API | Thao tác có tác động lớn, thường cần quyền cao và lý do cụ thể. |

Ở Spring Batch 6.x, một số method/operator API và package liên quan đã thay đổi; dòng 6.x có thêm khả năng `JobOperator.recover(...)` cho execution kẹt sau shutdown bất thường. Khi áp dụng, dùng **tài liệu API khớp phiên bản**; không sao chép code quản trị 5.x vào dự án 6.x mà không đối chiếu.

Một số thao tác khác cũng có ý nghĩa audit, dù không nằm trong `JobOperator`: sửa lịch chạy, thay số replica, bật/tắt cấu hình `@Scheduled`, thay tham số mặc định, điều chỉnh quyền operator, thực hiện data backfill, hoặc chạy một script sửa trạng thái batch bằng công cụ admin. Chúng cần dấu vết ở **hệ thống thực hiện thay đổi tương ứng**, không chỉ tại API điều khiển job.

### 2.2. JobInstance và JobExecution trong audit

Trong Spring Batch:

```text
JobInstance = job name + identifying JobParameters

JobInstance 420 (dailyOrdersJob / businessDate=2026-11-15)
  |
  +-- JobExecution 1001  -> FAILED
  |
  +-- JobExecution 1015  -> STARTED / COMPLETED (restart)
```

Nếu operator restart execution `1001`, audit nên giữ cả `targetExecutionId=1001` lẫn `createdExecutionId=1015` khi API trả về ID mới. Nếu chỉ ghi tên job, khó phân biệt nhiều lần chạy cho cùng ngày; nếu chỉ ghi execution ID mới, không biết operator đã yêu cầu restart từ lần thất bại nào.

`JobParameters` là dữ liệu định danh một lần chạy logic, nhưng **không được giả định toàn bộ tham số đều an toàn để đưa vào audit**. Các tham số có thể chứa input path, tenant, customer key, URL có token hoặc thậm chí secret nếu thiết kế ứng dụng sai. Audit nên lưu allowlist khóa nghiệp vụ được phép xuất hoặc một fingerprint được tính an toàn.

## 3. Audit, application log và JobRepository khác nhau thế nào?

| Nguồn | Trả lời câu hỏi | Điểm mạnh | Giới hạn |
|---|---|---|---|
| **Operator audit trail** | Ai yêu cầu, vì sao, quyền và quyết định thế nào? | Bằng chứng vận hành/tuân thủ, có thể truy cứu thao tác | Cần thiết kế riêng, không phải tính năng tự động đầy đủ của `JobOperator`. |
| Application log | Trong code đã xảy ra sự kiện/lỗi gì? | Tốt cho debug và correlation | Có thể bị rotate/drop, dễ trùng, không có cấu trúc hay retention theo yêu cầu audit. |
| JDBC `JobRepository` | Job/step đã thực thi với trạng thái và checkpoint nào? | Dữ liệu framework quản lý, hỗ trợ restart | Không lưu đầy đủ danh tính operator, lý do, quyền hoặc quyết định từ chối. |
| Security access log | Request HTTP nào được gửi, response status bao nhiêu? | Hữu ích cho truy vết API và denial | Không nhất thiết biết `JobExecution` nào thực sự được tạo. |
| Metrics / tracing | Độ trễ, tỉ lệ lỗi, đường đi giữa service? | Tốt cho giám sát và cảnh báo | Không thay thế nhật ký kiểm toán chi tiết theo từng hành động. |

Ví dụ một operator bấm nút `Restart` và nhận HTTP `202 Accepted`. Audit ghi `RESTART_REQUEST_ACCEPTED` kèm ID mới; vài phút sau batch thất bại vì dữ liệu nguồn không còn tồn tại. Dòng `JobExecution` cuối cùng là `FAILED`. Cả hai thông tin đều đúng: **lệnh đã được tiếp nhận** nhưng **công việc chưa hoàn thành thành công**.

Đừng ghi `COMPLETED` vào sự kiện audit ngay khi `JobOperator.restart(...)` trả về. Với launcher đồng bộ, lời gọi có thể chờ job kết thúc; với launcher bất đồng bộ, lời gọi có thể trả về rất sớm. Thiết kế audit nên sử dụng tên phase tách bạch để không phụ thuộc cách launcher được cấu hình.

## 4. Mỗi event audit cần có những trường nào?

Một audit record tốt là **một event bất biến** với ID riêng. Với một thao tác có thể có nhiều event như `REQUESTED`, `ACCEPTED`, `DENIED`, `FAILED` hoặc `RECONCILED`; tất cả cùng `requestId` để tra cứu như một chuỗi.

| Trường | Ví dụ | Ý nghĩa |
|---|---|---|
| `auditEventId` | UUID | Định danh duy nhất cho từng event. |
| `requestId`/`operationId` | `req-c4f9...` | Nhóm mọi event của một yêu cầu thao tác. |
| `occurredAt` | `2026-11-16T03:00:00Z` | Thời điểm event theo UTC. |
| `actorId` | `operator-73` | Định danh ổn định lấy từ danh tính đã xác thực. |
| `actorType` | `HUMAN`/`SERVICE` | Phân biệt người dùng và service account. |
| `initiatedBy` | `scheduler-A` | Thông tin về tác nhân khởi tạo khi tác vụ đi qua nhiều tầng, nếu được xác minh. |
| `action` | `RESTART` | Loại thao tác cần audit. |
| `phase` | `REQUESTED`, `ACCEPTED`, `DENIED`, `FAILED` | Kết quả/pha của request điều khiển, không phải `BatchStatus`. |
| `jobName` | `dailyOrdersJob` | Job mục tiêu. |
| `targetExecutionId` | `1001` | Execution cũ cần stop/restart/abandon. |
| `createdExecutionId` | `1015` | Execution mới được tạo khi launch/restart thành công. |
| `jobInstanceId` | `420` | Gom các executions của cùng instance logic nếu đã biết. |
| `parameterFingerprint` | HMAC digest | Nhận diện bộ tham số mà không phải lưu raw secrets. |
| `reason`/`ticketRef` | `INC-4821` | Giải thích căn cứ thao tác. |
| `authorizationDecision` | `ALLOW`/`DENY` | Tách kết quả kiểm tra quyền khỏi kết quả thực thi lệnh. |
| `resultCode` | `ALREADY_COMPLETED` | Mã kết quả được chuẩn hóa; tránh phụ thuộc raw exception message. |
| `source` | `ADMIN_API`, `SCHEDULER`, `CLI` | Nơi phát sinh lệnh. |
| `traceId` | W3C trace ID | Liên kết log/tracing nếu có. |

Các trường `actorId`, `requestId`, `action`, `phase`, timestamp và target nên là phần tối thiểu. Trường `reason` có thể cần bắt buộc cho `ABANDON`, recovery hoặc restart sau sự cố. Không yêu cầu operator nhập token/password hoặc thông tin cá nhân chỉ để điền lý do.

### 4.1. Đừng đánh đồng `requestId` và `JobExecutionId`

Một request có thể bị từ chối **trước khi Spring Batch tạo execution**. Khi đó vẫn cần một `requestId`, nhưng không có `createdExecutionId`. Với stop, request nhắm tới một execution đã tồn tại mà không tạo ID mới. Với workflow phê duyệt, có thể có nhiều event trên một request trước khi gửi lệnh cho `JobOperator`.

`requestId` còn hữu ích để phòng thao tác lặp do UI timeout, double click hoặc API client retry. Tuy nhiên, **chỉ log requestId không tạo ra idempotency**; hệ thống phải lưu, kiểm tra và thực thi một chính sách xử lý request trùng riêng.

## 5. Thiết kế audit table append-only

Ví dụ PostgreSQL DDL dùng bảng sự kiện `batch_operator_audit_event`. Đây là bảng **do ứng dụng sở hữu**, tách khỏi các bảng metadata `BATCH_*` của Spring Batch:

```sql
CREATE TABLE batch_operator_audit_event (
    event_id UUID PRIMARY KEY,
    request_id VARCHAR(80) NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    actor_id VARCHAR(160) NOT NULL,
    actor_type VARCHAR(24) NOT NULL,
    action VARCHAR(32) NOT NULL,
    phase VARCHAR(32) NOT NULL,
    source VARCHAR(48) NOT NULL,
    job_name VARCHAR(160),
    target_execution_id BIGINT,
    created_execution_id BIGINT,
    job_instance_id BIGINT,
    parameter_fingerprint VARCHAR(128),
    reason VARCHAR(500),
    ticket_ref VARCHAR(100),
    result_code VARCHAR(100),
    trace_id VARCHAR(80),
    details_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT ck_operator_audit_action CHECK (
        action IN ('START', 'STOP', 'RESTART', 'ABANDON', 'RECOVER')
    ),
    CONSTRAINT ck_operator_audit_phase CHECK (
        phase IN ('REQUESTED', 'ACCEPTED', 'DENIED', 'FAILED', 'RECONCILED')
    )
);

CREATE INDEX idx_operator_audit_request
    ON batch_operator_audit_event (request_id, occurred_at);

CREATE INDEX idx_operator_audit_execution
    ON batch_operator_audit_event (target_execution_id, occurred_at);

CREATE INDEX idx_operator_audit_actor_time
    ON batch_operator_audit_event (actor_id, occurred_at);
```

Một request restart thành công có thể tạo hai bản ghi:

```text
event_id=A1 request_id=R1 action=RESTART phase=REQUESTED
  actor_id=operator-73 target_execution_id=1001

event_id=A2 request_id=R1 action=RESTART phase=ACCEPTED
  actor_id=operator-73 target_execution_id=1001 created_execution_id=1015
```

Không cập nhật bản ghi `A1` thành `ACCEPTED`: giữ lại từng bước theo thời gian để phát hiện request dở dang khi process crash. Nếu cần bảng `batch_operator_command` để quản lý trạng thái workflow hiện tại, bảng đó có thể được update, nhưng **event audit lịch sử** nên giữ cách ghi append-only.

**Thiết kế bất biến cần thực thi bằng quyền và cơ chế lưu trữ**, không chỉ bằng quy ước code. Chẳng hạn, tài khoản runtime chỉ có quyền `INSERT`/`SELECT` với bảng audit, không có quyền `UPDATE`/`DELETE`; quyền quản trị, retention, backup và cách xuất bản ghi sang hệ thống lưu trữ không thể sửa đổi phải được quản lý riêng.

### 5.1. Có cần khóa ngoại tới `BATCH_JOB_EXECUTION`?

Không bắt buộc. Một event `DENIED` có thể nhắm vào ID chưa tồn tại; một audit record có thể cần được giữ lâu hơn metadata batch đã được cleanup theo retention. Nếu đặt foreign key trực tiếp, thao tác xóa metadata có thể bị chặn hoặc kéo theo việc xóa audit không mong muốn. Thường chỉ lưu ID để correlation và thiết kế retention độc lập, tùy chính sách của hệ thống.

### 5.2. Schema và database dùng trong audit

Với hệ thống nhỏ, audit table và `BATCH_*` có thể cùng nằm trong một database nhưng dùng transaction boundary rõ ràng. Với hệ thống cần chống sửa đổi cao, có thể lưu vào database riêng, append-only event store hoặc audit service có quyền riêng. Tách database có thể giảm rủi ro xóa nhầm khi dọn dữ liệu batch, nhưng tăng yêu cầu vận hành, tính sẵn sàng và bài toán ghi nhất quán giữa các hệ thống.

## 6. Vị trí ghi audit trong luồng xử lý operator action

Một luồng REST/CLI an toàn cần nhận diện mọi điểm có thể từ chối yêu cầu:

```text
1. API nhận request, gán requestId
2. Xác thực actor (hoặc service identity)
3. Kiểm tra quyền thao tác + phạm vi job/tenant
   - DENIED: ghi security denial audit
4. Validate reason, target ID, input parameters
5. Ghi event REQUESTED bền vững
6. Gọi JobOperator hoặc JobLauncher
7a. Lệnh được nhận -> event ACCEPTED + execution ID nếu có
7b. Lệnh thất bại -> event FAILED + error code
8. Theo dõi job lifecycle riêng đến trạng thái cuối
```

**Ghi audit sau authorization trong service chưa đủ để thấy các request bị từ chối ở tầng security.** Nếu dùng `@PreAuthorize` hoặc Spring Security filter, lệnh có thể bị chặn trước khi method được gọi. Muốn audit denial, phải quan sát sự kiện authorization ở tầng bảo mật tương ứng (ví dụ access-denied handler, authorization event listener hoặc interceptor) và chỉ ghi những metadata an toàn có thể lấy được.

Các lỗi validation không đủ dữ liệu để gọi `JobOperator` vẫn nên có event `FAILED`/`REJECTED` theo mô hình của hệ thống. Trong bảng DDL minh họa, có thể chuẩn hóa lỗi input thành `phase=FAILED`, `result_code=INVALID_REQUEST`; còn từ chối quyền là `phase=DENIED`. Tránh nhồi mọi trường hợp vào `FAILED` mà không có `resultCode` để phân loại.

### 6.1. Một ví dụ REST API

```http
POST /ops/batch/executions/1001/restart
Authorization: Bearer <token>
Idempotency-Key: req-9e35...
Content-Type: application/json

{
  "reason": "Restart after verified upstream outage",
  "ticketRef": "INC-4821"
}
```

Response minh họa khi hệ thống tiếp nhận lệnh:

```http
HTTP/1.1 202 Accepted
Content-Type: application/json

{
  "operationId": "req-9e35...",
  "action": "RESTART",
  "targetExecutionId": 1001,
  "createdExecutionId": 1015,
  "commandStatus": "ACCEPTED"
}
```

`ACCEPTED` ở đây **không có nghĩa batch execution 1015 đã `COMPLETED`**. UI nên hiển thị trạng thái request và trạng thái job riêng biệt, có màn hình theo dõi tiến độ/metadata. `Idempotency-Key` là một quy ước API do ứng dụng thực thi, không phải header tự được Spring Batch xử lý. Không đưa access token thực tế vào audit log.

## 7. Nhận diện operator và kiểm soát quyền

### 7.1. Lấy actor từ danh tính xác thực

Khi dùng Spring Security, có thể lấy `Authentication` từ `SecurityContextHolder`, hoặc inject `Principal`/`@AuthenticationPrincipal` vào controller. Giá trị `actorId` phải đến từ principal **đã được xác thực**. Không tin một trường do client gửi như:

```json
{"operatorId":"admin", "action":"ABANDON", "executionId":1001}
```

Nếu client tự đặt `operatorId`, bất kỳ người gọi nào cũng có thể giả mạo tác giả của thao tác. Thay vào đó, dùng subject/user ID ổn định của identity provider; tên hiển thị có thể thay đổi và không nên là khóa kiểm toán duy nhất.

Với machine-to-machine, ghi **service identity** từ token/mTLS/workload identity và, nếu có yêu cầu được ủy quyền từ người dùng, thêm một trường `initiatedBy` đã được xác minh. Đừng biến một header tùy ý `X-User` thành danh tính đáng tin cậy nếu gateway không bảo đảm chữ ký/nguồn gốc và chính sách truyền danh tính.

### 7.2. Phân quyền theo từng hành động

Không nên trao toàn bộ quyền điều hành job chỉ bằng một role quá rộng nếu các thao tác có rủi ro khác nhau:

| Hành động | Quyền gợi ý | Nhận xét |
|---|---|---|
| Xem trạng thái/list executions | `BATCH_READ` | Đọc metadata, có thể cần giới hạn theo job/tenant. |
| Chạy job theo tham số hợp lệ | `BATCH_START` | Validate job allowlist và input parameters. |
| Dừng job đang chạy | `BATCH_STOP` | Hiểu dừng là yêu cầu hợp tác; không phải kill OS. |
| Restart thất bại | `BATCH_RESTART` | Xác minh trạng thái, checkpoint và side effects. |
| Abandon execution | `BATCH_ABANDON` | Quyền nhạy cảm, nên yêu cầu lý do/ticket và có thể thêm approval. |
| Recover execution kẹt (6.x) | `BATCH_RECOVER` | Chỉ sau khi xác minh process cũ không còn chạy. |

Tên authority trên là **quy ước của ứng dụng**, không phải authority Spring Batch định nghĩa sẵn. Còn cần kiểm tra **phạm vi tài nguyên**: operator được phép restart `dailyOrdersJob` chưa chắc được quyền restart job lương, job thanh toán hoặc dữ liệu tenant khác. RBAC có thể kết hợp ABAC/policy theo job name, tenant, environment và mức độ nhạy cảm của thao tác.

Ví dụ cấu hình method security trong Spring Boot 3.x:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
class OperatorSecurityConfiguration {
}
```

Trong service:

```java
@PreAuthorize("hasAuthority('BATCH_RESTART')")
public long restart(long executionId, String reason, String requestId)
        throws Exception {
    // Validate authorization scope, ghi audit, gọi JobOperator.
}
```

`@EnableMethodSecurity` cần được bật và method phải được gọi **qua Spring proxy** thì `@PreAuthorize` mới có hiệu lực. Nếu test khởi tạo class bằng `new` rồi gọi method trực tiếp, annotation không tự thực thi kiểm tra quyền. Với HTTP API có session/cookie authentication, tiếp tục áp dụng chính sách CSRF phù hợp; audit không thay thế kiểm soát truy cập.

### 7.3. Từ chối quyền cũng cần audit

Ví dụ một user không có `BATCH_ABANDON` gọi endpoint abandon. Cần giữ ít nhất `requestId`, actor hợp lệ nếu xác định được, action, target ID, thời điểm, `DENIED` và reason code `MISSING_AUTHORITY`. Với request chưa xác thực, sử dụng định danh như `ANONYMOUS` hoặc thuộc tính connection đã được chuẩn hóa, và không ghi raw access token/credential.

Tránh dùng raw exception message, URL đầy đủ có query params hoặc request body làm record audit mặc định. URL có thể chứa khóa bí mật, file path nhạy cảm hoặc dữ liệu khách hàng. Các trường cần được chọn và chuẩn hóa trước khi lưu.

## 8. Ví dụ triển khai service audit cho `RESTART`

Đoạn minh họa dưới đây chọn **Spring Boot 3.x, Spring Batch 5.x, Spring Security 6.x**, với các API ID-based của `JobOperator`. Đây là phần code nghiệp vụ tập trung vào audit, giả định Spring context đã cấu hình `JobOperator`, security và một triển khai `OperatorAuditWriter` ghi sự kiện bền vững.

Định nghĩa giao diện ghi audit:

```java
public interface OperatorAuditWriter {

    void append(
            String requestId,
            String actorId,
            String action,
            String phase,
            Long targetExecutionId,
            Long createdExecutionId,
            String reason,
            String resultCode);
}
```

Service thực thi:

```java
import org.springframework.batch.core.launch.support.SimpleJobOperator;
import org.springframework.batch.core.launch.JobOperator;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;

@Service
public class BatchOperatorService {

    private final JobOperator jobOperator;
    private final OperatorAuditWriter audit;

    public BatchOperatorService(JobOperator jobOperator,
                                OperatorAuditWriter audit) {
        this.jobOperator = jobOperator;
        this.audit = audit;
    }

    @PreAuthorize("hasAuthority('BATCH_RESTART')")
    public long restart(long executionId, String reason, String requestId)
            throws Exception {

        Authentication authentication = SecurityContextHolder
                .getContext().getAuthentication();
        String actorId = authentication.getName();

        if (reason == null || reason.isBlank()) {
            throw new IllegalArgumentException("reason is required");
        }

        // Nếu ghi sự kiện đầu tiên thất bại, không gửi lệnh privileged.
        audit.append(requestId, actorId, "RESTART", "REQUESTED",
                executionId, null, reason, null);

        try {
            long newExecutionId = jobOperator.restart(executionId);
            audit.append(requestId, actorId, "RESTART", "ACCEPTED",
                    executionId, newExecutionId, reason, null);
            return newExecutionId;
        } catch (Exception ex) {
            audit.append(requestId, actorId, "RESTART", "FAILED",
                    executionId, null, reason,
                    ex.getClass().getSimpleName());
            throw ex;
        }
    }
}
```

`SimpleJobOperator` không cần được import nếu code chỉ phụ thuộc interface `JobOperator`; import tên implementation ở trên có thể bỏ đi khi triển khai thực tế. Các phương thức/exception chính xác cần đối chiếu dependency Spring Batch đang dùng. Demo giả định request đã được xác thực và đã qua policy theo phạm vi job/tenant; trong production, không chỉ kiểm tra authority chung rồi cho phép restart mọi execution.

**Điểm cần hiểu trong mẫu này:**

1. `REQUESTED` được ghi **trước** khi gọi API có tác động. Nếu storage audit không sẵn sàng, việc restart bị chặn theo chính sách fail-closed của ví dụ.
2. `ACCEPTED` có ID execution mới, giúp correlation với `JobRepository`.
3. Nếu `JobOperator.restart(...)` ném exception, lưu `FAILED` cùng loại lỗi đã chuẩn hóa. Không tự đưa stack trace, toàn bộ exception message hoặc credentials vào bảng audit.
4. `@PreAuthorize` chạy **trước khi thân method**, nên lời gọi bị deny phải được audit ở security boundary, không phải nhánh `catch` ở đây.
5. Audit không tự bảo đảm atomic với `JobOperator`: process có thể crash sau khi restart được nhận nhưng trước khi ghi `ACCEPTED`. Cần cơ chế reconciliation ở mục sau.
6. Dùng `authentication.getName()` chỉ phù hợp khi tên này là định danh ổn định theo cấu hình identity provider; nếu là display name, cần ánh xạ về immutable subject ID.

### 8.1. Viết sự kiện bền vững bằng transaction riêng

Một `OperatorAuditWriter` có thể dùng `JdbcTemplate` hoặc JPA để insert vào bảng append-only. Trong hệ thống sử dụng transaction của Spring, có thể đặt thao tác ghi ở **một Spring bean riêng** với `Propagation.REQUIRES_NEW`, để commit audit độc lập với transaction của business step.

```java
import java.time.Clock;
import java.time.Instant;
import java.util.UUID;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class JdbcOperatorAuditWriter implements OperatorAuditWriter {

    private final JdbcTemplate jdbc;
    private final Clock clock;

    public JdbcOperatorAuditWriter(JdbcTemplate jdbc, Clock clock) {
        this.jdbc = jdbc;
        this.clock = clock;
    }

    @Override
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void append(String requestId, String actorId,
                       String action, String phase,
                       Long targetExecutionId, Long createdExecutionId,
                       String reason, String resultCode) {

        jdbc.update("""
                INSERT INTO batch_operator_audit_event (
                    event_id, request_id, occurred_at,
                    actor_id, actor_type, action, phase, source,
                    target_execution_id, created_execution_id,
                    reason, result_code
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                UUID.randomUUID(), requestId,
                java.sql.Timestamp.from(Instant.now(clock)),
                actorId, "HUMAN", action, phase, "ADMIN_API",
                targetExecutionId, createdExecutionId,
                reason, resultCode);
    }
}
```

Trong một ứng dụng có nhiều transaction manager, cần chỉ định `@Transactional(transactionManager = "auditTransactionManager", propagation = Propagation.REQUIRES_NEW)` cùng datasource đúng. Khi dùng PostgreSQL, chọn mapping JDBC thích hợp cho kiểu `TIMESTAMPTZ` và `UUID`; cần xác minh với driver thực tế. Bean `Clock` cũng phải được đăng ký, chẳng hạn `Clock.systemUTC()`.

Ví dụ dùng actor type `HUMAN` và source `ADMIN_API` để đơn giản hóa, còn hệ thống thật cần nhận diện service account/scheduler/CLI và lưu đúng nguồn. Mẫu này chưa đưa `jobName`, `jobInstanceId`, fingerprint, trace ID và ticket vào insert; khi triển khai đầy đủ, ghi những trường đã định nghĩa ở schema và lấy từ dữ liệu đáng tin cậy.

`REQUIRES_NEW` tạo transaction mới khi được gọi qua Spring proxy. Nếu gọi method `append` nội bộ trong cùng class bằng `this.append(...)`, Spring proxy có thể bị bỏ qua. Transaction riêng giúp audit không bị rollback theo transaction nghiệp vụ khác, nhưng **không biến hai database hoặc lệnh `JobOperator` và audit thành một giao dịch atomic**.

### 8.2. Vì sao không nên ghi audit bên trong chunk transaction?

Giả sử operator restart một job rồi một chunk gặp lỗi và rollback. Nếu audit ghi trong transaction xử lý chunk, bản ghi audit có thể bị rollback theo, làm mất dấu vết yêu cầu restart đã xảy ra. Audit nên được ghi ở **boundary điều khiển job** và có transaction/lifecycle riêng, không phụ thuộc việc item writer commit thành công hay thất bại.

Với lệnh có mức rủi ro rất cao, việc mất kết nối audit store có thể cần **từ chối thao tác** thay vì tiếp tục và hy vọng log console còn giữ. Đó là chính sách thiết kế; phải được thống nhất với yêu cầu vận hành và tính sẵn sàng.

## 9. Ghi audit khi thao tác thất bại giữa chừng

Không có lời hứa rằng mọi thao tác controller, audit database và `JobRepository` luôn commit cùng lúc. Ví dụ:

```text
T1: Ghi REQUESTED thành công
T2: Gọi JobOperator.restart(1001)
T3: JobRepository tạo JobExecution 1015
T4: Process API crash trước khi ghi ACCEPTED

Audit còn REQUESTED, không có ACCEPTED.
Batch metadata có thể đã có JobExecution 1015.
```

Nếu thấy request chỉ có `REQUESTED` mà không có kết quả, **đừng tự động gọi lại restart**: có thể hành động đã được thực hiện. Cần truy vấn `JobRepository`, đối chiếu thời gian, job instance, tham số và lệnh trước đó, rồi ghi một event `RECONCILED` cho kết quả điều tra. Audit event cuối có thể chỉ ra `resultCode=EXECUTION_FOUND` cùng execution ID đã xác định.

### 9.1. Mẫu command intake bền vững cho yêu cầu nghiêm ngặt

Với hệ thống đòi hỏi audit và điều phối mạnh hơn, có thể tách **ghi nhận command** khỏi **thực thi command**:

```text
API:
  - Xác thực và phân quyền
  - Ghi command (requestId unique, actor, action, target, reason)
  - Ghi audit REQUESTED cùng transaction
  - Trả operationId

Worker điều phối:
  - Claim command đã commit
  - Kiểm tra request đã được thực hiện chưa
  - Gọi JobOperator theo policy, kèm lock/guard phù hợp
  - Ghi ACCEPTED / FAILED
  - Reconcile command dở dang sau crash
```

`requestId UNIQUE` trên bảng command giúp nhận diện request lặp, còn bảng audit event cho phép nhiều event cùng `requestId`. Việc thực thi command vẫn cần **idempotency theo hành động và khóa nghiệp vụ**, vì worker có thể crash ngay sau lời gọi `JobOperator`. Không hứa exactly-once chỉ nhờ có queue hoặc một bảng outbox.

### 9.2. Không ghi nhầm kết quả cuối của job

Một tiến trình theo dõi có thể ghi thêm sự kiện `JOB_EXECUTION_COMPLETED` hoặc liên kết tới `JobExecution` khi job đạt trạng thái cuối. Tuy nhiên nên lưu nhóm sự kiện lifecycle riêng với audit thao tác, hoặc đặt `eventType`/`category` phân biệt rõ; không thay đổi event `ACCEPTED` thành `COMPLETED` như thể command ban đầu chỉ hoàn thành vào thời điểm job kết thúc.

Nếu API launch bất đồng bộ, `JobExecution` có thể đang `STARTING`/`STARTED` khi response trả về. `JobOperator.stop(...)` chỉ gửi tín hiệu dừng; nó có thể trả về trước khi `BatchStatus` thành `STOPPED`. Hệ thống theo dõi phải quan sát trạng thái thực tế, có timeout và cảnh báo khi execution không kết thúc theo mong đợi.

## 10. Audit riêng cho từng hành động có rủi ro

### 10.1. START thủ công

Với chạy thủ công, cần ghi job name, actor, lý do, khóa nghiệp vụ và **tham số đã lọc** hoặc fingerprint. Trường hợp operator chọn sai `businessDate` có thể dẫn tới xử lý dữ liệu của ngày khác, nên validation thuộc audit operation boundary và phải có decision log.

```text
REQUESTED action=START job=dailyOrdersJob businessDate=2026-11-15
ACCEPTED  action=START createdExecutionId=1015
```

Nếu hệ thống thường chạy qua scheduler, hãy phân biệt `source=SCHEDULER` với `source=ADMIN_API`. Không giả mạo một user id khi chính scheduler phát lệnh. Nếu có lệnh chạy bù thủ công thông qua scheduler service, lưu cả service identity và người khởi tạo đã xác minh.

### 10.2. STOP

`stop` thường là **cooperative stop request**, không tương đương kill process. Audit cần ghi `STOP_REQUEST_ACCEPTED` rồi theo dõi đến `BatchStatus.STOPPED`, `FAILED` hoặc trạng thái khác. Nếu operator yêu cầu stop nhưng một tasklet đang block, yêu cầu có thể chưa được hoàn tất. Ghi cả thời điểm yêu cầu và thời điểm execution kết thúc giúp phân tích độ trễ dừng.

### 10.3. RESTART

Restart cần ghi target execution cũ, new execution ID khi có, trạng thái trước đó, lý do, identifying business key và trạng thái checkpoint/reconciliation nếu hệ thống có. Không tự ý thêm `run.id` identifying chỉ để né `JobInstanceAlreadyCompleteException`: hành động đó thường tạo instance mới và có thể xử lý trùng dữ liệu.

### 10.4. ABANDON

`ABANDON` tác động tới khả năng tiếp tục execution. Nó không phải một cách restart nhanh. Với hành động này nên có quyền chuyên biệt, lý do bắt buộc, ticket/approval theo chính sách và audit event không thể xóa tùy ý. Trước khi thực hiện, operator phải xác minh không còn work thực tế đang chạy và đã chọn rõ phương án xử lý dữ liệu còn dở.

### 10.5. RECOVER sau process crash

Trong Spring Batch 6.x, `JobOperator.recover(...)` hỗ trợ phục hồi execution bị kẹt sau shutdown bất thường. Audit cần ghi bằng chứng xác minh process cũ không còn chạy, target execution, lý do, ai phê duyệt và new execution nếu có restart sau recovery.

Với Spring Batch 5.x, phục hồi execution kẹt `STARTED` cần quy trình quản trị metadata được kiểm soát; đây cũng là thao tác phải audit. Không tự cập nhật một cột `STATUS` bằng SQL rồi coi quá trình recovery đã đầy đủ; trạng thái job/step, `ExitStatus`, version optimistic locking và `ExecutionContext` phải nhất quán để restart đúng.

## 11. Không ghi secrets và dữ liệu nhạy cảm vào audit

Một audit trail thường có thời gian lưu dài và nhiều người có nhu cầu đọc hơn log debug. Vì vậy phải coi nó là **vùng dữ liệu nhạy cảm** ngay cả khi operator action chỉ là metadata.

Ví dụ tham số có thể đi cùng job:

```text
businessDate=2026-11-15
tenantId=acme
inputPath=s3://private-bucket/customer-data/...
apiToken=...
dbPassword=...
```

Không gọi `jobParameters.toString()` và lưu nguyên chuỗi vào bảng audit. Với những key được phép lưu, dùng **allowlist** và hạn chế độ dài giá trị; với giá trị nhạy cảm, có thể lưu một fingerprint bằng HMAC thay vì raw value. HMAC-SHA-256 với khóa quản lý riêng phù hợp hơn hash SHA-256 thuần khi giá trị đầu vào dễ đoán, vì hash thường có thể bị thử từ điển.

Một mẫu chiến lược:

| Loại thông tin | Chính sách audit gợi ý |
|---|---|
| `jobName`, `jobExecutionId`, action, phase | Ghi rõ, vì cần truy vết. |
| `businessDate` công khai trong tổ chức | Có thể ghi nếu chính sách cho phép. |
| `tenantId` | Kiểm tra phân quyền và chính sách dữ liệu; có thể pseudonymize. |
| `inputPath` chứa tên khách hàng | Không ghi raw; dùng object revision/ID an toàn. |
| Password, token, secret | Không ghi dưới bất kỳ hình thức plaintext nào. |
| Toàn bộ HTTP body/headers | Không ghi mặc định; chỉ trích xuất trường được cho phép. |
| Stack trace/exception message | Lưu error code được chuẩn hóa; stack trace đưa vào log kỹ thuật đã kiểm soát. |
| IP address | Chỉ lưu khi có mục đích phù hợp và xác định đúng địa chỉ trusted proxy. |

Nếu API nằm sau reverse proxy, không dùng bừa `X-Forwarded-For` do client tự gửi làm bằng chứng địa chỉ nguồn. Chỉ sử dụng forwarded headers khi hạ tầng có trust boundary được cấu hình và lọc/ghi đè headers tại ingress đáng tin cậy.

Audit cũng cần chính sách **retention, quyền xem, mã hóa, backup, export và xóa dữ liệu theo yêu cầu pháp lý** được xác định trong tổ chức. Append-only không có nghĩa bỏ qua chính sách bảo vệ dữ liệu; nếu cần purge theo retention, hãy dùng quy trình quản trị có ghi nhận, không cho runtime tự sửa xóa tùy ý.

## 12. Tính toàn vẹn và khả năng phát hiện sửa audit

Không nên đánh giá audit chỉ qua việc “đã insert vào database”. Một actor có quyền `UPDATE` hoặc DBA quyền cao có thể sửa lịch sử nếu không có biện pháp bảo vệ. Tùy mức nghiêm ngặt của yêu cầu, có thể áp dụng nhiều lớp:

1. **Quyền tối thiểu:** runtime chỉ `INSERT` và quyền đọc cần thiết; người vận hành batch không có quyền xóa hoặc sửa audit event.
2. **Append-only ở tầng ứng dụng và database:** chỉ tạo event mới để giải thích/correct; không âm thầm overwrite event cũ.
3. **Lưu bản sao bất biến:** chuyển sự kiện sang kho lưu WORM hoặc nền tảng audit tập trung có retention lock phù hợp.
4. **Tamper evidence:** hash chain/digital signature hoặc batch digest khi yêu cầu chứng minh không có event bị chỉnh sửa; quản lý khóa ký riêng.
5. **Clock và correlation:** thời gian UTC đồng bộ, event ID và request ID để so sánh nhiều nguồn.
6. **Monitoring audit pipeline:** cảnh báo khi insert audit thất bại, queue backlog, exporter ngừng hoặc event `REQUESTED` không có kết quả tương ứng.

Một hash chain đơn giản có thể giúp phát hiện việc sửa event nếu chain head được neo ở nơi độc lập; **chỉ lưu cả event và hash trong cùng database mà một người có thể sửa tất cả thì chưa chống được việc viết lại toàn bộ lịch sử**. Mức bảo đảm phải phù hợp mô hình đe dọa và quy định vận hành của hệ thống.

## 13. Cách đối chiếu operator action với metadata Spring Batch

Ví dụ audit ghi:

```text
requestId=req-77 action=RESTART actorId=operator-73
targetExecutionId=1001 createdExecutionId=1015 phase=ACCEPTED
```

Truy vấn metadata `BATCH_JOB_EXECUTION` (Spring Batch 5.x, schema mặc định):

```sql
SELECT
    ji.JOB_NAME,
    ji.JOB_INSTANCE_ID,
    je.JOB_EXECUTION_ID,
    je.STATUS,
    je.EXIT_CODE,
    je.START_TIME,
    je.END_TIME
FROM BATCH_JOB_EXECUTION je
JOIN BATCH_JOB_INSTANCE ji
  ON je.JOB_INSTANCE_ID = ji.JOB_INSTANCE_ID
WHERE je.JOB_EXECUTION_ID IN (1001, 1015);
```

Truy vấn audit:

```sql
SELECT
    occurred_at,
    actor_id,
    action,
    phase,
    target_execution_id,
    created_execution_id,
    result_code
FROM batch_operator_audit_event
WHERE request_id = 'req-77'
ORDER BY occurred_at, event_id;
```

Sau đó đối chiếu: cùng `JobInstance` không, execution mới có tồn tại và đã kết thúc chưa, số step executions có phù hợp không, dữ liệu đầu ra có được commit theo nghiệp vụ không. Các bảng metadata mặc định của Spring Batch **không lưu đầy đủ ai đã bấm nút restart và lý do**, vì vậy cần bảng audit riêng.

Trong production, dùng prepared statement/bind parameters cho dữ liệu nhận từ API; các giá trị ID literal ở SQL trên chỉ dùng để minh họa. Không cập nhật trực tiếp `BATCH_JOB_EXECUTION` hoặc `BATCH_STEP_EXECUTION` khi đang truy vấn phục vụ audit.

### 13.1. Không nhầm trình tự event với trạng thái hệ thống

Một event được ghi ở `10:05:00Z` chưa chắc có nghĩa mọi thay đổi đã commit vào database khác tại thời điểm đó. Nhiều service, transaction và logging backend có độ trễ hoặc clock skew. Dựa trên **quan hệ ID, trạng thái repository và quy tắc transaction** để xác định nguyên nhân; timestamp là một trong nhiều tín hiệu, không phải bằng chứng tuyệt đối về thứ tự toàn hệ thống.

## 14. Phân biệt hành động của người vận hành và automation

Spring Batch có thể được chạy từ `@Scheduled`, Quartz, Kubernetes CronJob, CI/CD, hệ thống quản trị nội bộ hoặc API. Cần thống nhất cách nhận diện người chịu trách nhiệm:

| Nguồn | `actorType` | Danh tính nên lưu | Ví dụ lý do |
|---|---|---|---|
| Nút Run trong Admin UI | `HUMAN` | Subject ID từ identity provider | Backfill theo ticket. |
| Scheduler hàng ngày | `SERVICE` | Service/workload identity | Scheduled execution theo lịch. |
| Script vận hành trong CI | `SERVICE` | CI service principal và pipeline/run ID | Triển khai hoặc chạy dữ liệu kiểm tra. |
| Bot được người dùng yêu cầu | `SERVICE` + `initiatedBy` xác minh | Service identity và human subject có căn cứ | Automation theo yêu cầu có phê duyệt. |
| Hệ thống khôi phục tự động | `SERVICE` | Recovery controller ID và policy version | Stale execution recovery theo điều kiện. |

Nếu một service chạy thay người dùng, phải phân biệt **identity thực sự của service gọi API** và **người đã phê duyệt hoặc khởi tạo workflow**. Đừng gán event dưới tên người dùng chỉ vì một trường `initiatedBy` được truyền trong request mà không có xác minh/ủy quyền.

## 15. Kiểm thử audit operator action

Kiểm thử nên chứng minh dấu vết được tạo khi hệ thống chấp nhận **và** từ chối thao tác. Cần tách logic audit khỏi việc chạy batch thật để các unit test có tốc độ ổn định; chỉ những trường hợp cần kiểm tra wiring/transaction/repository mới phải dùng integration test.

### 15.1. Unit test ghi sự kiện đúng thứ tự

Với JUnit 5 và Mockito, có thể kiểm tra service ghi `REQUESTED` trước khi gọi `JobOperator` và ghi `ACCEPTED` sau khi nhận ID mới. Ví dụ dưới đây giả định kiểm thử method body trực tiếp; **nó không kiểm tra `@PreAuthorize`** vì không chạy qua Spring Security proxy:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.inOrder;
import static org.mockito.Mockito.when;

import java.util.List;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.mockito.InOrder;
import org.mockito.Mockito;
import org.springframework.batch.core.launch.JobOperator;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;

class BatchOperatorServiceTest {

    private final JobOperator jobOperator = Mockito.mock(JobOperator.class);
    private final OperatorAuditWriter audit = Mockito.mock(OperatorAuditWriter.class);

    @AfterEach
    void clearSecurityContext() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void restartWritesRequestAndAcceptanceEvents() throws Exception {
        SecurityContextHolder.getContext().setAuthentication(
                new UsernamePasswordAuthenticationToken(
                        "operator-73", "n/a",
                        List.of(new SimpleGrantedAuthority("BATCH_RESTART"))));

        when(jobOperator.restart(1001L)).thenReturn(1015L);

        BatchOperatorService service =
                new BatchOperatorService(jobOperator, audit);

        long newId = service.restart(1001L, "Investigated incident", "req-77");
        assertEquals(1015L, newId);

        InOrder calls = inOrder(audit, jobOperator);
        calls.verify(audit).append("req-77", "operator-73",
                "RESTART", "REQUESTED", 1001L, null,
                "Investigated incident", null);
        calls.verify(jobOperator).restart(1001L);
        calls.verify(audit).append("req-77", "operator-73",
                "RESTART", "ACCEPTED", 1001L, 1015L,
                "Investigated incident", null);
    }
}
```

Kiểm thử này xác minh thứ tự lời gọi và các trường cần thiết, nhưng không chứng minh audit record đã commit vào database. Nếu `AuditWriter` dùng `REQUIRES_NEW`, nên có một integration test riêng xác nhận dữ liệu audit vẫn tồn tại khi một transaction nghiệp vụ khác rollback.

### 15.2. Integration test phân quyền

Với Spring Security Test (`spring-security-test`) và `MockMvc`/`WebTestClient`, có thể mô phỏng những tình huống:

| Test case | Kỳ vọng |
|---|---|
| User có `BATCH_RESTART` và được phép trên job mục tiêu | API tiếp nhận lệnh và ghi `REQUESTED`, `ACCEPTED` hoặc `FAILED` theo kết quả. |
| User không có `BATCH_RESTART` | HTTP 403; `JobOperator.restart` không được gọi; audit `DENIED` ở security boundary. |
| Chưa xác thực | HTTP 401 hoặc flow xác thực tương ứng; audit denial/unauthenticated theo chính sách, không giả mạo actor. |
| Có authority nhưng sai tenant/job scope | Từ chối và ghi reason code xác định. |
| Reason bắt buộc bị bỏ trống | Không gọi `JobOperator`; có event về request không hợp lệ nếu policy yêu cầu. |
| Audit store không ghi được `REQUESTED` | Hành động privileged bị chặn theo chính sách fail-closed. |
| Operator gửi lại cùng idempotency key | Không tạo tác vụ mới trái phép; response được đối chiếu với request/command đã có. |

Để chứng minh denied requests được audit, cần cấu hình security handler/event listener thật trong Spring Test. Nếu chỉ mock service và xác minh `@PreAuthorize` trên method chưa đi qua proxy, bài test không thể chứng minh policy hoạt động.

### 15.3. Integration test với JobRepository

Trong môi trường test có JDBC repository riêng:

1. Chạy một job có chủ đích thất bại và lưu `JobExecution` cũ.
2. Gọi API restart bằng operator được phân quyền.
3. Xác minh có audit event `REQUESTED` rồi `ACCEPTED` kèm new execution ID.
4. Xác minh `JobInstance` đúng và `JobExecution` mới được tạo.
5. Chờ job kết thúc, đối chiếu `BatchStatus` thực tế với màn hình/audit lifecycle.
6. Kiểm tra các bản ghi audit vẫn còn khi dọn `BATCH_*` test theo chính sách phù hợp.

Đừng dùng database production để thử `ABANDON`, `RECOVER` hoặc thao tác sửa metadata. Test riêng cho failure recovery cần có bước chứng minh process cũ thật sự đã chết trước khi chuyển trạng thái `STARTED` tồn đọng.

### 15.4. Crash window test

Để kiểm tra trường hợp crash giữa lệnh và audit kết quả, có thể chạy API/worker trong process test riêng, tạo điểm chặn sau khi `JobOperator` thực hiện nhưng trước khi event `ACCEPTED` được ghi, rồi kill process đó. Sau khi khởi động lại, cơ chế reconciliation phải:

- Tìm request có `REQUESTED` nhưng không có kết quả cuối.
- Kiểm tra metadata/lệnh đã thực hiện trước đó.
- Ghi event `RECONCILED` với bằng chứng/ID phù hợp.
- Tránh thực hiện lại thao tác nếu chưa xác định an toàn.

Không kill JVM chạy toàn bộ JUnit suite; một crash test thật cần chạy job/command service trong process hoặc container test độc lập.

## 16. Runbook điều tra một thao tác operator gây sự cố

Ví dụ sau mô tả quy trình khi một job bất ngờ được restart và dữ liệu đầu ra bị xử lý hai lần:

1. **Xác định job/execution:** lấy job name, `JobInstanceId`, `JobExecutionId`, khoảng thời gian và business key.
2. **Tra audit theo execution:** tìm event `RESTART` có `targetExecutionId`/`createdExecutionId` tương ứng.
3. **Xác định actor và kênh:** người vận hành nào hoặc automation nào, quyền nào được sử dụng, requestId và nguồn gọi.
4. **Đọc chuỗi event:** có `REQUESTED`, `DENIED`, `ACCEPTED`, `FAILED` hay `RECONCILED`? Có retry request cùng idempotency key không?
5. **Đối chiếu metadata:** các execution thuộc cùng instance hay đã tạo instance mới do thay identifying parameters?
6. **Đối chiếu kết quả dữ liệu:** số record/file/message thực tế, idempotency key, outbox hoặc các effect ngoài DB.
7. **Kiểm tra lịch/automation:** có CronJob, Quartz, scheduler replica hoặc script khác phát lệnh song song không?
8. **Lập kết luận có căn cứ:** ghi mốc thời gian, actor, policy và kết quả điều tra vào incident report; không sửa/xóa bản ghi audit gốc.

Nếu audit cho thấy lệnh `ACCEPTED` nhưng execution không tồn tại, đó có thể là lỗi correlation, metadata bị cleanup hoặc sự cố transaction/cấu hình nhiều repository. Nếu repository có execution nhưng audit chỉ có `REQUESTED`, đó có thể là cửa sổ crash và cần reconciliation. Các trường hợp khác nhau không nên được xử lý bằng cùng một câu lệnh SQL sửa trạng thái.

## 17. Những lỗi phổ biến khi thiết kế audit

| Hiện tượng | Nguyên nhân | Cách cải thiện |
|---|---|---|
| Không biết ai restart job | Chỉ dựa vào `BATCH_JOB_EXECUTION` | Ghi operator audit event ở control plane với actor đã xác thực. |
| Audit ghi "job completed" ngay khi API trả về | Nhầm command acceptance với batch lifecycle | Tách `ACCEPTED` khỏi `BatchStatus.COMPLETED`. |
| Không thấy thao tác bị 403 | Chỉ audit bên trong method có `@PreAuthorize` | Ghi denial ở security boundary. |
| Thấy tên `admin` dù người gọi không có quyền | Tin trường `operatorId` do client gửi | Dùng authenticated subject, xác minh delegation. |
| Ghi raw JobParameters | Không có allowlist/redaction | Chỉ lưu khóa được phép và fingerprint an toàn. |
| Một request tạo nhiều restart | UI retry/double click, thiếu idempotency | Dùng operation ID/unique command key và guard trước khi thực thi. |
| Audit mất khi batch rollback | Audit ghi trong transaction nghiệp vụ | Dùng transaction riêng, kiểm tra kiến trúc đồng bộ dữ liệu. |
| Có REQUESTED nhưng không có ACCEPTED | Crash hoặc lỗi audit sau khi JobOperator chạy | Reconcile với JobRepository trước khi retry. |
| STOP audit thành công nhưng job còn STARTED | Stop là yêu cầu hợp tác; job chưa thực sự kết thúc | Theo dõi status thực tế và cảnh báo quá hạn. |
| Không thể restart sau ABANDON | Dùng sai thao tác quản trị | Giới hạn quyền và bắt buộc lý do/approval. |
| Audit table bị xóa khi cleanup Batch | Dùng chung schema/retention hoặc khóa ngoại cascade | Tách sở hữu/retention và quyền xóa; không cascade nhầm. |
| Log kho dữ liệu chứa password | Log URL/body/header/exception không được lọc | Dùng data minimization, masking và security review. |
| Audit không chống sửa đổi | Runtime có quyền UPDATE/DELETE | Append-only + quyền tối thiểu + lưu bản sao bất biến khi cần. |
| Dashboard báo hai trạng thái trái nhau | Một bên hiển thị request phase, bên kia hiển thị `BatchStatus` | Hiển thị rõ `commandStatus` và `jobExecutionStatus` khác nhau. |
| Job đang chạy ở tenant khác bị operator tác động | Chỉ kiểm tra authority chung | Kiểm tra scope theo job, tenant và environment. |

## 18. Quy trình triển khai audit cho một hệ thống Spring Batch

Khi xây dựng hoặc cải tiến giao diện vận hành, có thể theo trình tự:

1. **Lập danh sách action** hiện có: start, stop, restart, abandon, recover, sửa lịch hoặc tạo backfill.
2. **Định nghĩa identity và quyền** cho người dùng/service, quyền theo action và phạm vi job/tenant/environment.
3. **Thiết kế event schema** gồm actor, requestId, action, phase, target/created execution IDs, timestamp UTC và reason/ticket.
4. **Xác định dữ liệu được phép lưu**: allowlist fields, fingerprint tham số, chính sách bỏ secrets/PII.
5. **Tạo append-only store** với quyền ghi phù hợp, retention và cơ chế backup/tamper-evidence theo yêu cầu.
6. **Gắn audit vào request lifecycle**, kể cả denial ở security boundary và validation failures.
7. **Ghi event trước hành động có tác động**, chọn chính sách fail-closed khi audit store không khả dụng.
8. **Ghi kết quả của command** và liên kết với `JobRepository`; không đánh đồng acceptance và completion.
9. **Xử lý crash window** bằng operationId/idempotency/reconciliation thay vì retry mù.
10. **Kiểm thử cả bảo mật và dữ liệu audit**, gồm unauthorized, timeout, restart, dừng mềm, thay đổi job parameters, rollback và storage failure.
11. **Theo dõi audit pipeline** để phát hiện event thiếu, ghi lỗi, backlog hoặc truy cập bất thường.
12. **Diễn tập điều tra sự cố** bằng cách lần theo một request từ principal đến execution và dữ liệu đầu ra.

### Bài tập thực hành

**Bài 1 — Audit START và RESTART**

- Tạo API nhận request launch/restart với `requestId`, `reason` và `ticketRef`.
- Lấy operator ID từ Spring Security principal, không chấp nhận `operatorId` tự khai báo trong body.
- Ghi hai event `REQUESTED` và `ACCEPTED` với ID execution được tạo.
- Kiểm tra một job restart thành công và một request bị `JobInstanceAlreadyCompleteException`.

**Bài 2 — Audit DENIED**

- Tạo hai tài khoản thử: một có `BATCH_READ`, một có `BATCH_RESTART`.
- Dùng MockMvc gọi endpoint restart với tài khoản thiếu quyền.
- Xác minh API trả 403, `JobOperator` không được gọi, audit event `DENIED` có actor và requestId.
- Kiểm tra không có password/access token trong bản ghi audit.

**Bài 3 — Tách status của operator command và batch job**

- Gửi `STOP` tới job chạy lâu và ghi `ACCEPTED` ngay khi hệ thống nhận yêu cầu.
- Theo dõi đến khi `BatchStatus` chuyển sang `STOPPED` hoặc trạng thái khác.
- Tạo dashboard biểu diễn hai trường riêng `commandStatus` và `jobExecutionStatus`.

**Bài 4 — Crash sau khi gửi lệnh**

- Cho test worker gọi `JobOperator.restart(...)`, rồi mô phỏng crash trước khi ghi event `ACCEPTED` trong process test riêng.
- Viết reconciliation đọc `JobRepository` và audit records để tìm execution mới tương ứng.
- Ghi `RECONCILED` thay vì tự khởi tạo thêm một restart không có bằng chứng.

**Bài 5 — Kiểm tra tính toàn vẹn**

- Tạo database role ứng dụng chỉ được `INSERT`/`SELECT` audit event.
- Xác minh runtime role không được update/delete bản ghi lịch sử.
- Xuất snapshot audit và xác định cơ chế lưu giữ có integrity/retention phù hợp với yêu cầu tổ chức.

## 19. Tài liệu tham khảo

- [Spring Batch Reference — JobOperator and Advanced Metadata Usage](https://docs.spring.io/spring-batch/reference/job/advanced-meta-data.html): các thao tác điều khiển job, restart, stop và metadata vận hành.
- [Spring Batch 5.2 — Running a Job](https://docs.spring.io/spring-batch/reference/5.2/job/running.html): `JobParameters`, `JobLauncher` và quy tắc job instance.
- [Spring Batch Reference — Meta-Data Schema](https://docs.spring.io/spring-batch/reference/schema-appendix.html): các bảng `BATCH_*` và những dữ liệu thực thi được lưu.
- [Spring Security Reference — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize` và policy cho service.
- [Spring Security Reference — Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html): cơ chế quyết định authorization và tích hợp sự kiện truy cập.
- [Spring Framework Reference — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): `REQUIRES_NEW` và ranh giới transaction.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): nguyên tắc ghi sự kiện bảo mật, dữ liệu nhạy cảm, tính toàn vẹn và bảo vệ log.

