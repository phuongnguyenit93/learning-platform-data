# Persist request state cho tác vụ dài

Một RPC có thể khởi chạy công việc kéo dài hàng phút hoặc hàng giờ: xuất báo cáo, xử lý lô dữ liệu, đồng bộ kho hoặc tạo bản sao lưu. Nếu giữ một RPC mở cho toàn bộ thời gian đó, client có thể hết deadline, mất kết nối hoặc khởi động lại; server cũng có thể restart giữa chừng. Trong Spring gRPC, cách đáng tin cậy hơn là **lưu trạng thái operation bền vững**, trả mã operation sớm và cho phép client truy vấn tiến độ/kết quả bằng RPC riêng.

Trạng thái phải nằm trong kho bền vững như database, không chỉ trong `Map`, biến singleton hay bộ nhớ của worker. Khi process dừng, worker khác phải có thể tiếp tục hoặc phục hồi operation từ dữ liệu đã lưu.

## 1. Tách vòng đời RPC khỏi vòng đời operation

RPC `StartExport` chỉ tiếp nhận yêu cầu và tạo operation. Nó nên hoàn tất nhanh sau khi operation cùng thông tin dispatch đã được commit. Công việc thực tế chạy ở worker nền:

~~~mermaid
sequenceDiagram
    participant C as gRPC Client
    participant S as Spring gRPC Service
    participant DB as Operation DB
    participant O as Outbox Publisher
    participant W as Worker
    C->>S: StartExport(request, idempotency_key)
    S->>DB: INSERT operation + outbox trong một transaction
    DB-->>S: operation_id, state=QUEUED
    S-->>C: Operation(QUEUED)
    O->>DB: Đọc outbox chưa publish
    O->>W: Dispatch operation_id
    W->>DB: Claim operation, lease + fencing token
    W->>W: Thực thi và lưu progress
    W->>DB: Persist SUCCEEDED / FAILED
    C->>S: GetOperation(operation_id)
    S->>DB: Đọc trạng thái mới nhất
    DB-->>S: Operation snapshot
    S-->>C: Operation(state, progress, result)
~~~

RPC submission có deadline ngắn phù hợp với việc ghi nhận operation. Deadline của RPC đó không phải deadline của công việc nền. Khi client disconnect sau khi server đã commit operation, công việc vẫn tiếp tục theo policy đã công bố; client dùng operation ID hoặc idempotency key để tra cứu.

## 2. Thiết kế contract cho operation

Một API tối thiểu có thể cung cấp `StartExport`, `GetOperation`, `WatchOperation` và `CancelOperation`:

~~~proto
syntax = "proto3";

package acme.export.v1;

option java_multiple_files = true;
option java_package = "com.acme.export.v1";

import "google/protobuf/timestamp.proto";
import "google/rpc/status.proto";

service ExportService {
  rpc StartExport(StartExportRequest) returns (Operation);
  rpc GetOperation(GetOperationRequest) returns (Operation);
  rpc WatchOperation(WatchOperationRequest) returns (stream Operation);
  rpc CancelOperation(CancelOperationRequest) returns (Operation);
}

enum OperationState {
  OPERATION_STATE_UNSPECIFIED = 0;
  OPERATION_STATE_QUEUED = 1;
  OPERATION_STATE_RUNNING = 2;
  OPERATION_STATE_CANCEL_REQUESTED = 3;
  OPERATION_STATE_SUCCEEDED = 4;
  OPERATION_STATE_FAILED = 5;
  OPERATION_STATE_CANCELLED = 6;
}

message StartExportRequest {
  string idempotency_key = 1;
  string source_id = 2;
  string format = 3;
}

message Operation {
  string name = 1;
  OperationState state = 2;
  int32 progress_percent = 3;
  string result_uri = 4;
  google.rpc.Status error = 5;
  google.protobuf.Timestamp created_at = 6;
  google.protobuf.Timestamp updated_at = 7;
  int64 version = 8;
}

message GetOperationRequest {
  string name = 1;
}

message WatchOperationRequest {
  string name = 1;
  int64 after_version = 2;
}

message CancelOperationRequest {
  string name = 1;
}
~~~

`name` là định danh operation ổn định, ví dụ `operations/01J...`; không nên để client tự chọn tenant hoặc chủ sở hữu qua field này. Server xác định tenant từ principal đã xác thực, sau đó kiểm tra operation thuộc tenant đó. `result_uri` nên trỏ tới artifact đã lưu bền vững; không nhét file lớn vào message trạng thái.

`WatchOperation` là kênh thông báo thay đổi thuận tiện, còn `GetOperation` là nguồn snapshot có thể truy vấn lại. Stream có thể bị ngắt và không tự bảo đảm replay; `after_version` cho phép client yêu cầu các cập nhật sau phiên bản đã nhận, hoặc server trả snapshot hiện tại nếu không còn lịch sử sự kiện.

## 3. Mô hình dữ liệu bền vững

Một bảng operation có thể lưu các trường sau:

~~~sql
CREATE TABLE operations (
    id               VARCHAR(64) PRIMARY KEY,
    tenant_id        VARCHAR(128) NOT NULL,
    idempotency_key  VARCHAR(128) NOT NULL,
    request_hash     VARCHAR(128) NOT NULL,
    state            VARCHAR(32) NOT NULL,
    progress_percent INTEGER NOT NULL DEFAULT 0,
    result_uri       TEXT,
    error_code       VARCHAR(64),
    error_message    TEXT,
    error_details    BYTEA,
    attempt          INTEGER NOT NULL DEFAULT 0,
    available_at     TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    lease_owner      VARCHAR(128),
    lease_until      TIMESTAMP WITH TIME ZONE,
    fencing_token    BIGINT NOT NULL DEFAULT 0,
    version          BIGINT NOT NULL DEFAULT 0,
    created_at       TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at       TIMESTAMP WITH TIME ZONE NOT NULL,
    UNIQUE (tenant_id, idempotency_key)
);
~~~

Outbox và event log có thể được lưu riêng:

~~~sql
CREATE TABLE outbox_events (
    event_id      VARCHAR(64) PRIMARY KEY,
    operation_id  VARCHAR(64) NOT NULL,
    event_type    VARCHAR(64) NOT NULL,
    payload       BYTEA NOT NULL,
    created_at    TIMESTAMP WITH TIME ZONE NOT NULL,
    published_at  TIMESTAMP WITH TIME ZONE
);

CREATE TABLE operation_events (
    operation_id      VARCHAR(64) NOT NULL,
    version           BIGINT NOT NULL,
    state             VARCHAR(32) NOT NULL,
    progress_percent  INTEGER NOT NULL,
    created_at        TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (operation_id, version)
);
~~~

`error_details` có thể lưu rich error đã được lọc nhạy cảm dưới dạng serialized Protobuf; nếu không cần rich detail thì chỉ lưu code và message chuẩn hóa. `available_at` xác định thời điểm operation được phép retry sau backoff. `operation_events` là nguồn replay cho `WatchOperation` nếu sản phẩm cần gửi lại từng version; nếu không lưu event log, endpoint chỉ có thể trả snapshot mới nhất.

Các cột quan trọng:

- `tenant_id` dùng để phân quyền và cô lập dữ liệu.
- `idempotency_key` ngăn client tạo operation trùng khi retry request submission.
- `request_hash` phát hiện trường hợp caller dùng lại key nhưng gửi payload khác.
- `state`, `progress_percent`, `result_uri`, `error_*` là snapshot trạng thái công khai.
- `attempt`, `lease_owner`, `lease_until` phục vụ worker claim và phục hồi.
- `fencing_token` ngăn worker cũ ghi đè kết quả của worker mới.
- `version` hỗ trợ optimistic concurrency và client resume watch.

Không nhất thiết lưu toàn bộ input hoặc output lớn trong bảng này. Có thể lưu request đã chuẩn hóa trong object storage hoặc bảng riêng và lưu tham chiếu bất biến trong operation. Bảo đảm dữ liệu đủ để worker khôi phục mà không phụ thuộc bộ nhớ process đã tạo request.

## 4. Tạo operation và outbox trong cùng transaction

Một lỗi thường gặp là ghi operation vào database rồi mới gửi message lên broker. Nếu process dừng giữa hai bước, operation nằm ở `QUEUED` nhưng không bao giờ được dispatch. Transactional outbox giải quyết khoảng trống đó: lưu operation và event cần dispatch trong cùng transaction; publisher đọc outbox và gửi lại cho tới khi thành công.

Ví dụ service layer:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ExportSubmissionService {

    private final OperationRepository operations;
    private final OutboxRepository outbox;
    private final RequestHasher requestHasher;
    private final OperationIdGenerator idGenerator;

    public ExportSubmissionService(
            OperationRepository operations,
            OutboxRepository outbox,
            RequestHasher requestHasher,
            OperationIdGenerator idGenerator) {
        this.operations = operations;
        this.outbox = outbox;
        this.requestHasher = requestHasher;
        this.idGenerator = idGenerator;
    }

    @Transactional
    public OperationRecord submit(String tenantId, StartExportRequest request) {
        String hash = requestHasher.hashCanonicalRequest(request);

        var inserted = operations.insertIfAbsent(
            idGenerator.newId(),
            tenantId,
            request.getIdempotencyKey(),
            hash,
            "QUEUED");

        if (inserted.isPresent()) {
            OperationRecord created = inserted.get();
            outbox.append("EXPORT_REQUESTED", created.getId());
            return created;
        }

        OperationRecord existing = operations
            .findByTenantAndIdempotencyKey(
                tenantId, request.getIdempotencyKey())
            .orElseThrow();

        if (!existing.getRequestHash().equals(hash)) {
            throw new IdempotencyKeyConflictException();
        }

        return existing;
    }
}
~~~

`insertIfAbsent` cần được triển khai bằng unique constraint trên `(tenant_id, idempotency_key)` và thao tác atomic, ví dụ `INSERT ... ON CONFLICT DO NOTHING` trong PostgreSQL. Chỉ append outbox khi operation mới được tạo. Nếu cùng key và cùng request hash, trả lại operation cũ; nếu cùng key nhưng payload khác, trả lỗi conflict rõ ràng, không âm thầm đổi request đã nhận.

Publisher có thể gửi event nhiều lần nếu crash sau khi publish nhưng trước khi đánh dấu outbox đã xử lý. Worker vì vậy phải idempotent theo operation ID; không giả định message broker chỉ giao đúng một lần.

gRPC adapter chỉ cần lấy tenant từ principal đã xác thực, gọi application service và trả snapshot. Ví dụ rút gọn:

~~~java
import io.grpc.Status;
import io.grpc.stub.StreamObserver;

public final class ExportGrpcService
        extends ExportServiceGrpc.ExportServiceImplBase {

    private final ExportSubmissionService submissions;
    private final AuthenticatedTenantResolver tenantResolver;
    private final OperationMapper operationMapper;

    public ExportGrpcService(
            ExportSubmissionService submissions,
            AuthenticatedTenantResolver tenantResolver,
            OperationMapper operationMapper) {
        this.submissions = submissions;
        this.tenantResolver = tenantResolver;
        this.operationMapper = operationMapper;
    }

    @Override
    public void startExport(
            StartExportRequest request,
            StreamObserver<Operation> observer) {
        try {
            String tenantId = tenantResolver.currentTenantId();
            OperationRecord record = submissions.submit(tenantId, request);
            observer.onNext(operationMapper.toProto(record));
            observer.onCompleted();
        } catch (IdempotencyKeyConflictException conflict) {
            observer.onError(Status.ALREADY_EXISTS
                .withDescription("idempotency key was used with another request")
                .asRuntimeException());
        }
    }
}
~~~

Adapter không tự gửi event tới broker; application service đã ghi outbox cùng operation trong transaction. `tenantResolver` phải đọc identity từ authentication context/interceptor, không lấy tenant ID từ request body.

## 5. State machine và điều kiện chuyển trạng thái

State machine làm rõ thao tác nào hợp lệ:

~~~mermaid
stateDiagram-v2
    [*] --> QUEUED
    QUEUED --> RUNNING: worker claim
    QUEUED --> CANCELLED: cancel trước khi chạy
    RUNNING --> SUCCEEDED: kết quả đã commit
    RUNNING --> FAILED: lỗi không thể retry
    RUNNING --> CANCEL_REQUESTED: caller yêu cầu hủy
    CANCEL_REQUESTED --> CANCELLED: worker dừng an toàn
    CANCEL_REQUESTED --> SUCCEEDED: hoàn tất trước khi hủy có hiệu lực
    RUNNING --> QUEUED: lỗi tạm thời, còn attempt
~~~

Các trạng thái terminal thường là `SUCCEEDED`, `FAILED` và `CANCELLED`. Một operation terminal không được tự quay về `RUNNING`; nếu cần chạy lại sau lỗi, tạo operation mới hoặc định nghĩa attempt/retry lifecycle rõ ràng.

Mỗi transition phải có điều kiện ở database, không chỉ kiểm tra trong Java rồi update vô điều kiện. Ví dụ chỉ chuyển `RUNNING` sang `SUCCEEDED` nếu operation vẫn ở `RUNNING` và fencing token của worker khớp. `version` có thể tăng mỗi lần cập nhật để phát hiện ghi đè cạnh tranh.

## 6. Worker claim bằng lease và fencing token

Worker không nên giữ một database transaction mở suốt thời gian xử lý dài. Thay vào đó, claim operation trong transaction ngắn, ghi lease có thời hạn rồi xử lý bên ngoài transaction. Ví dụ PostgreSQL dùng `FOR UPDATE SKIP LOCKED`:

~~~sql
WITH candidate AS (
    SELECT id
    FROM operations
    WHERE (state = 'QUEUED' AND available_at <= CURRENT_TIMESTAMP)
       OR (state IN ('RUNNING', 'CANCEL_REQUESTED')
           AND lease_until < CURRENT_TIMESTAMP)
    ORDER BY created_at
    FOR UPDATE SKIP LOCKED
    LIMIT 1
)
UPDATE operations AS op
SET state = CASE
        WHEN op.state = 'CANCEL_REQUESTED' THEN 'CANCEL_REQUESTED'
        ELSE 'RUNNING'
    END,
    lease_owner = :worker_id,
    lease_until = CURRENT_TIMESTAMP + INTERVAL '30 seconds',
    fencing_token = fencing_token + 1,
    attempt = attempt + 1,
    version = version + 1,
    updated_at = CURRENT_TIMESTAMP
FROM candidate
WHERE op.id = candidate.id
RETURNING op.*;
~~~

Lease cho phép worker khác tiếp quản nếu worker hiện tại chết và lease hết hạn. `fencing_token` tăng mỗi lần claim; worker cũ có token thấp hơn không được phép ghi progress hoặc terminal state sau khi worker mới đã tiếp quản. Nếu row được claim vẫn ở `CANCEL_REQUESTED`, worker mới chỉ thực hiện cleanup/cancellation và kết thúc operation, không khởi động lại tác vụ.

Khi heartbeat, worker gia hạn lease có điều kiện:

~~~sql
UPDATE operations
SET lease_until = CURRENT_TIMESTAMP + INTERVAL '30 seconds',
    updated_at = CURRENT_TIMESTAMP
WHERE id = :operation_id
  AND state = 'RUNNING'
  AND lease_owner = :worker_id
  AND fencing_token = :fencing_token;
~~~

Nếu số hàng được cập nhật là zero, worker đã mất quyền sở hữu operation và phải dừng ghi kết quả. Thời hạn lease cần lớn hơn khoảng heartbeat dự kiến và có biên an toàn cho pause/GC; heartbeat không được làm transaction xử lý chính kéo dài vô hạn.

Fencing token trong database chỉ bảo vệ các update có điều kiện ở database. Nếu worker ghi sang hệ thống ngoài, sink đó cũng cần idempotency key, version/fencing token hoặc thao tác conditional write; nếu không, worker cũ vẫn có thể tạo side effect bên ngoài sau khi mất lease.

## 7. Cập nhật progress và kết quả có kiểm soát

Progress nên phản ánh mốc công việc có ý nghĩa, không cần ghi database sau từng record. Cập nhật có điều kiện theo fencing token:

~~~sql
UPDATE operations
SET progress_percent = GREATEST(progress_percent, :progress),
    version = version + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE id = :operation_id
  AND state = 'RUNNING'
  AND lease_owner = :worker_id
  AND fencing_token = :fencing_token;
~~~

Progress nên đơn điệu tăng, nằm trong khoảng 0–100 và không báo 100 trước khi artifact được lưu bền vững. Khi hoàn tất:

1. Ghi artifact vào storage bằng key ổn định theo operation/attempt hoặc một quy trình publish nguyên tử.
2. Xác minh artifact đã tồn tại và có metadata/checksum cần thiết.
3. Chuyển operation sang `SUCCEEDED`, lưu `result_uri`, tăng version và xóa lease trong cùng transaction.
4. Chỉ sau đó mới thông báo trạng thái thành công.

Nếu worker crash sau khi ghi artifact nhưng trước khi cập nhật operation, lần chạy lại cần nhận diện artifact đã hoàn tất hoặc ghi đè an toàn theo idempotency key. Không trả `SUCCEEDED` khi kết quả chỉ nằm trong bộ nhớ hoặc file tạm chưa được publish.

## 8. Phục hồi khi process hoặc worker restart

Sau restart, service không khôi phục operation từ bộ nhớ cũ. Nó đọc database để trả trạng thái hiện tại. Worker scheduler tìm operation `QUEUED` và các operation `RUNNING` có lease hết hạn để tiếp quản.

Một quy trình phục hồi cần:

- Quét operation quá lease và claim bằng fencing token mới.
- Retry lỗi tạm thời với số attempt tối đa và `available_at`/backoff.
- Đánh dấu `FAILED` khi lỗi vĩnh viễn hoặc hết retry budget.
- Dùng checkpoint để tiếp tục từ phần đã commit, thay vì lặp toàn bộ công việc nếu chi phí lớn.
- Làm cho side effect của worker idempotent hoặc deduplicate theo operation ID.
- Có job đối soát operation bị kẹt lâu ở `QUEUED`, `RUNNING` hoặc `CANCEL_REQUESTED`.

Nếu dùng broker, outbox publisher tiếp tục gửi các event chưa được xác nhận. Worker phải chịu được event trùng, event đến trễ và event đến sai thứ tự; database operation state là nguồn quyết định quyền claim và transition.

## 9. Cancellation không phụ thuộc disconnect của client

Client disconnect chỉ kết thúc RPC đang mở. Nó không tự động có nghĩa caller muốn hủy một operation đã được chấp nhận và lưu bền vững. Nếu tự động gắn cancellation của gRPC Context vào worker nền, một mạng chập chờn có thể hủy công việc mà caller vẫn mong muốn tiếp tục.

Thiết kế rõ hai hành động:

- **Disconnect:** ngừng gửi response cho RPC hiện tại; operation tiếp tục theo policy.
- **CancelOperation:** caller gọi RPC riêng để yêu cầu hủy operation.

Nếu operation còn `QUEUED`, server có thể chuyển trực tiếp sang `CANCELLED`. Nếu đang `RUNNING`, chuyển sang `CANCEL_REQUESTED`; worker kiểm tra cờ hủy ở các checkpoint và dừng an toàn. Nếu công việc đã commit kết quả trước khi yêu cầu hủy được áp dụng, operation có thể vẫn `SUCCEEDED`; transition phải dùng compare-and-set để giải quyết race.

Cancellation không thể luôn đảo ngược side effect đã commit. Contract cần nói rõ cancel là best-effort hay bảo đảm dừng trước một mốc cụ thể.

## 10. GetOperation và WatchOperation

`GetOperation` trả snapshot mới nhất sau khi xác thực tenant sở hữu operation. Nếu không thuộc tenant, trả status theo policy bảo mật; tránh để caller dò ID của tenant khác.

`WatchOperation` có thể phát snapshot ban đầu và các thay đổi tiếp theo. Vì stream gRPC có thể bị ngắt:

- Mỗi update nên có `version` tăng đơn điệu.
- Client ghi lại version cuối đã xử lý.
- Khi reconnect, gửi `after_version` để nhận thay đổi tiếp theo hoặc snapshot mới nhất.
- Nếu event history đã hết retention, server trả snapshot hiện tại để client đồng bộ lại.
- Client vẫn có thể gọi `GetOperation` để phục hồi trạng thái nếu stream mất.

Đừng xem Watch stream là kho lưu lịch sử bền vững. Nếu cần audit đầy đủ, lưu operation events riêng và áp dụng retention/access policy.

## 11. Bảo mật, tenant isolation và retention

Operation ID không phải credential. Mọi RPC `GetOperation`, `WatchOperation` và `CancelOperation` đều phải xác thực caller và kiểm tra quyền trên tenant/resource. Không chỉ dựa vào tính khó đoán của UUID.

Lưu ý:

- Tạo tenant ID từ principal đã xác thực, không tin field do client tự khai.
- Giới hạn kích thước request và validate format/options trước khi tạo operation.
- Mã hóa hoặc kiểm soát quyền truy cập input/output nhạy cảm.
- `result_uri` cần được cấp quyền truy cập có thời hạn hoặc qua endpoint có authorization.
- Error detail lưu trong operation không được chứa token, secret hoặc stack trace.
- Áp dụng retention cho operation terminal, outbox và artifact; không xóa operation đang chạy.
- Ghi audit cho submit, cancel, read result và thay đổi trạng thái quan trọng.

## 12. Kiểm thử contract và độ bền của operation

Test cần kiểm tra hành vi qua restart và lỗi giữa các bước, không chỉ xác minh service trả một response:

| Kịch bản | Assertion |
| --- | --- |
| Submit thành công | Operation và outbox được commit cùng transaction |
| Retry cùng idempotency key/request | Trả lại cùng operation ID, không tạo job thứ hai |
| Dùng lại key với payload khác | Trả conflict, không sửa operation cũ |
| Process dừng sau commit trước publish | Outbox publisher vẫn dispatch sau restart |
| Worker chết khi RUNNING | Lease hết hạn, worker khác claim với fencing token mới |
| Worker cũ ghi sau khi mất lease | Update bị từ chối do token không khớp |
| Client disconnect sau submit | Operation vẫn tiếp tục và truy vấn được |
| Cancel operation đang chạy | Chuyển CANCEL_REQUESTED rồi dừng ở checkpoint |
| Artifact lưu xong, worker crash trước SUCCEEDED | Retry nhận diện/publish artifact an toàn |
| Tenant khác đọc operation | Bị từ chối theo authorization policy |
| Watch stream reconnect | Client tiếp tục từ version hoặc nhận snapshot |

Nên có integration test với database thật và broker/outbox relay thật hoặc test double có kiểm soát lỗi. Kiểm thử transaction cần chứng minh không tồn tại trường hợp operation commit nhưng event dispatch bị mất vĩnh viễn.

## 13. Quan sát và vận hành

Theo dõi:

- Số operation theo từng state và tuổi của operation lâu nhất.
- Thời gian từ `QUEUED` đến `RUNNING`, thời gian xử lý và tổng thời gian hoàn tất.
- Số lease hết hạn, worker takeover và fencing rejection.
- Retry count, failure reason và tỷ lệ operation terminal.
- Outbox backlog, độ trễ publish và số event gửi lại.
- Tỷ lệ cancellation và thời gian từ yêu cầu hủy đến `CANCELLED`.
- Watch stream disconnect/reconnect và số lần client đồng bộ snapshot.

Log/trace nên gắn operation ID, tenant ID dạng an toàn, worker ID, attempt và fencing token. Không dùng operation ID hoặc tenant ID làm metric label không giới hạn nếu cardinality quá cao; dùng histogram/counter theo nhóm operation type và state.

## 14. Ghi nhớ và tự kiểm tra

**Persist request state cho tác vụ dài** nghĩa là biến công việc nền thành một operation có ID, state machine và dữ liệu được lưu bền vững. RPC submit tạo operation cùng outbox trong một transaction rồi trả kết quả sớm; worker claim bằng lease/fencing token, cập nhật progress và lưu kết quả trước khi đánh dấu terminal. Client dùng Get/Watch/Cancel riêng, còn disconnect của RPC không tự hủy operation.

Tự kiểm tra:

1. Vì sao không nên giữ một RPC mở trong suốt tác vụ kéo dài?
2. Transactional outbox ngăn mất dispatch trong tình huống nào?
3. Idempotency key giải quyết retry submission ra sao?
4. Lease và fencing token ngăn worker cũ ghi đè như thế nào?
5. Vì sao client disconnect khác CancelOperation?
6. Watch stream cần version/cursor để phục hồi sau reconnect ra sao?
7. Khi nào operation được phép chuyển sang SUCCEEDED?

Persist trạng thái đúng cách giúp Spring gRPC chịu được process restart, client timeout/disconnect và worker crash, đồng thời cho caller một contract ổn định để theo dõi hoặc hủy tác vụ dài.
