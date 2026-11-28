# Tiếp tục theo dõi tác vụ sau khi ứng dụng khởi động lại

## Bối cảnh

Trong Open Service Broker API (OSB API), một số thao tác vòng đời service instance có thể kéo dài hơn thời gian một request HTTP được phép giữ kết nối. Provision database cluster, thay đổi plan, di chuyển dữ liệu hoặc deprovision tài nguyên có thể cần nhiều bước và phải chờ provider hoàn tất. Khi Platform gửi accepts_incomplete=true, broker có thể chấp nhận công việc, trả HTTP 202 Accepted và tiếp tục xử lý bất đồng bộ.

Sau khi trả 202, broker vẫn phải cung cấp trạng thái qua endpoint last_operation. Platform có thể polling nhiều lần trong suốt quá trình thực hiện. Trong môi trường thực tế, process broker có thể bị restart do triển khai phiên bản mới, container bị thay thế, máy chủ khởi động lại, crash hoặc autoscaling. Nếu trạng thái operation chỉ nằm trong RAM, broker sẽ mất khả năng trả lời chính xác sau restart: operation có thể biến mất, worker có thể không chạy lại hoặc provider resource đã tạo nhưng database broker chưa ghi nhận.

Vì vậy, theo dõi operation sau restart phải được thiết kế như một quy trình bền vững. Broker lưu operation, trạng thái instance, checkpoint, thông tin provider operation và lịch sử lỗi trong kho lưu trữ dùng chung. Worker có thể tiếp tục công việc từ checkpoint an toàn hoặc đối chiếu trạng thái provider trước khi retry. API node sau khi khởi động lại chỉ cần đọc trạng thái đã lưu để trả lời Platform nhất quán.

Trong module SPRING_CLOUD_SERVICE_BROKER, nội dung này kết nối OSB asynchronous operation với Spring Boot lifecycle, database transaction, transactional outbox, queue, worker recovery, idempotency và tích hợp Cloud Foundry/Kubernetes.

## 1. Điều gì phải còn tồn tại sau restart?

Một asynchronous operation có hai vòng đời liên quan nhưng khác nhau:

- **Vòng đời giao thức:** Platform nhận 202, lưu operation reference và polling last_operation cho đến khi nhận trạng thái cuối.
- **Vòng đời thực thi:** broker điều phối worker, gọi provider, lưu checkpoint, xử lý retry và hoàn tất hoặc thất bại.

Restart process không làm hai vòng đời này kết thúc. Operation đã được chấp nhận vẫn phải có thể tra cứu và tiếp tục theo chính sách đã công bố.

Các dữ liệu cần lưu bền vững:

| Dữ liệu | Vì sao cần lưu |
|---|---|
| Operation ID | Để Platform tiếp tục polling đúng công việc |
| Platform ID và instance ID | Xác định đúng phạm vi và tài nguyên |
| Operation type | Phân biệt provision, update và deprovision |
| Trạng thái operation | Trả in progress, succeeded hoặc failed nhất quán |
| Trạng thái service instance | Không để instance bị coi là READY khi thao tác chưa hoàn tất |
| Request fingerprint | Nhận diện retry của cùng một ý định |
| Target configuration | Biết đích mà worker cần đạt tới |
| Current phase/checkpoint | Tiếp tục từ bước an toàn sau restart |
| Provider resource ID | Tìm lại tài nguyên đã tạo hoặc đang được thay đổi |
| Provider operation reference | Poll công việc dài hạn do provider thực hiện |
| Lease/worker ownership | Biết worker nào đang giữ quyền xử lý |
| Retry count và next attempt time | Điều khiển retry và backoff |
| Error code/description | Giải thích kết quả thất bại cho Platform và operator |
| Created/updated/completed time | Audit, timeout và retention |

Không cần lưu mọi object request thô nếu có thể lưu dữ liệu đã chuẩn hóa. Tránh lưu credential, password hoặc token vào operation record. Nếu worker cần secret để gọi provider, chỉ lưu secret reference tới secret manager và lấy secret khi thực thi.

## 2. Kiến trúc khuyến nghị

Một kiến trúc cơ bản có thể gồm API node, database, outbox publisher, queue, worker và provider adapter:

~~~mermaid
flowchart LR
    P[Platform] --> API[Broker API nodes]
    API --> DB[(Shared operation database)]
    DB --> OB[Transactional outbox]
    OB --> PUB[Outbox publisher]
    PUB --> Q[Durable queue]
    Q --> W1[Worker replica A]
    Q --> W2[Worker replica B]
    W1 --> PR[Provider adapter]
    W2 --> PR
    PR --> CLOUD[Cloud or Kubernetes provider]
    W1 --> DB
    W2 --> DB
    API --> DB
    API --> P
~~~

Database là nguồn trạng thái chuẩn của broker. Queue dùng để phân phối công việc, không phải nơi duy nhất giữ trạng thái operation. Nếu queue bị redeliver, worker phải đọc operation từ database và kiểm tra nó còn hợp lệ. Nếu queue message bị mất sau khi database commit, outbox publisher có thể phát lại.

API node và worker có thể chạy trong cùng một ứng dụng Spring Boot hoặc thành deployment riêng. Dù triển khai theo cách nào, cả hai phải dùng chung repository và quy tắc chuyển trạng thái. Không dựa vào local cache hoặc bộ nhớ của một replica làm nguồn sự thật.

### Nguyên tắc thiết kế

1. Ghi operation và ý định enqueue trong cùng một transaction.
2. Chỉ trả 202 sau khi operation được lưu bền vững.
3. Worker nhận message có thể xử lý lặp mà không nhân đôi side effect.
4. Trạng thái operation chỉ chuyển tiếp theo state machine hợp lệ.
5. Worker cũ không được ghi đè kết quả của worker mới sau khi mất lease.
6. Khi kết quả provider không chắc chắn, reconcile trước khi gọi lại lệnh có side effect.
7. API polling đọc từ kho trạng thái bền vững, không phụ thuộc worker còn sống hay không.

## 3. Ghi nhận operation trước khi trả 202

Khi nhận request provision/update/deprovision có accepts_incomplete=true và policy quyết định cần xử lý nền, broker phải ghi operation trước khi trả response. Nếu trả 202 trước khi lưu operation, Platform có thể polling một operation mà broker không biết.

Một transaction chấp nhận operation có thể thực hiện:

1. Xác thực caller và kiểm tra request.
2. Tải service instance và kiểm tra trạng thái hiện tại.
3. Tính request fingerprint và kiểm tra retry.
4. Tạo operation ở trạng thái ACCEPTED.
5. Chuyển instance sang PROVISIONING, UPDATING hoặc DEPROVISIONING.
6. Ghi outbox event chứa operation ID.
7. Commit transaction.
8. Trả 202 Accepted cùng operation ID.

Ví dụ response:

~~~http
HTTP/1.1 202 Accepted
Content-Type: application/json

{
  "operation": "provision-7f31a9"
}
~~~

Nếu database transaction thất bại, broker không được trả 202. Nếu commit thành công nhưng API node crash trước khi gửi response, Platform có thể retry request. Broker phải nhận diện fingerprint và trả lại operation đã được chấp nhận thay vì tạo operation thứ hai.

### Vì sao cần transactional outbox?

Giả sử broker thực hiện hai hành động độc lập:

- Commit operation vào database.
- Publish message lên queue.

Nếu database commit thành công nhưng process crash trước khi publish, operation tồn tại nhưng worker không bao giờ nhận được job. Nếu publish trước rồi transaction database rollback, worker có thể nhận message trỏ tới operation không tồn tại.

Transactional outbox ghi operation và outbox event trong cùng transaction. Publisher đọc các event chưa gửi, publish lên queue rồi đánh dấu đã gửi. Nếu publisher crash sau publish nhưng trước khi đánh dấu, event có thể được publish lần nữa; worker phải xử lý idempotent.

## 4. Mô hình dữ liệu cho recovery

Một mô hình tối thiểu có thể gồm operation, service instance và outbox:

~~~sql
CREATE TABLE service_operation (
    operation_id          VARCHAR(128) PRIMARY KEY,
    platform_id           VARCHAR(128) NOT NULL,
    instance_id           VARCHAR(128) NOT NULL,
    operation_type        VARCHAR(32) NOT NULL,
    state                 VARCHAR(24) NOT NULL,
    phase                 VARCHAR(64) NOT NULL,
    request_fingerprint   VARCHAR(128) NOT NULL,
    target_payload_ref    VARCHAR(256),
    provider_resource_id  VARCHAR(256),
    provider_operation_id VARCHAR(256),
    checkpoint             TEXT,
    retry_count            INTEGER NOT NULL DEFAULT 0,
    next_attempt_at        TIMESTAMP,
    lease_owner            VARCHAR(128),
    lease_until            TIMESTAMP,
    fencing_token          BIGINT NOT NULL DEFAULT 0,
    error_code             VARCHAR(128),
    error_description      VARCHAR(1024),
    created_at             TIMESTAMP NOT NULL,
    updated_at             TIMESTAMP NOT NULL,
    completed_at           TIMESTAMP
);

CREATE TABLE operation_outbox (
    event_id       VARCHAR(128) PRIMARY KEY,
    operation_id   VARCHAR(128) NOT NULL,
    event_type     VARCHAR(64) NOT NULL,
    payload        TEXT NOT NULL,
    published_at   TIMESTAMP,
    created_at     TIMESTAMP NOT NULL
);
~~~

Đây là schema minh họa, cần điều chỉnh kiểu dữ liệu, index, foreign key và chiến lược mã hóa theo database thực tế. Nếu payload có dữ liệu nhạy cảm, chỉ lưu tham chiếu hoặc mã hóa bằng cơ chế quản lý khóa phù hợp.

Các index quan trọng:

- operation_id để tra cứu từ last_operation.
- platform_id + instance_id để kiểm tra phạm vi và thao tác đang chạy.
- state + next_attempt_at để tìm operation cần recovery.
- lease_until để tìm worker lease đã hết hạn.
- published_at + created_at để publisher tìm outbox event chưa gửi.

Service instance nên có current_operation_id và version/generation để ngăn hai thao tác xung đột cùng thay đổi một instance.

## 5. State machine và ý nghĩa của trạng thái

Trạng thái nội bộ nên chi tiết hơn trạng thái OSB API trả về. Ví dụ:

| Trạng thái nội bộ | Ý nghĩa | OSB last_operation |
|---|---|---|
| ACCEPTED | Đã commit operation, chờ worker | in progress |
| QUEUED | Đã phát event hoặc chờ queue | in progress |
| RUNNING | Worker đang thực thi | in progress |
| WAITING_PROVIDER | Đang chờ provider operation | in progress |
| RETRY_WAIT | Chờ thời điểm retry | in progress |
| RECONCILING | Đối chiếu kết quả provider sau lỗi/timeout | in progress |
| SUCCEEDED | Đã xác minh kết quả mong muốn | succeeded |
| FAILED | Lỗi terminal, không thể tự tiếp tục | failed |
| CANCELLED | Được hủy theo policy trước khi hoàn tất | Ánh xạ theo hợp đồng và loại operation |

Không được chuyển operation thành SUCCEEDED chỉ vì worker đã gửi lệnh tới provider. Phải xác minh tài nguyên đạt target state và ghi nhận trạng thái instance tương ứng.

Ví dụ state machine:

~~~mermaid
stateDiagram-v2
    [*] --> ACCEPTED
    ACCEPTED --> QUEUED
    QUEUED --> RUNNING
    RUNNING --> WAITING_PROVIDER
    WAITING_PROVIDER --> RUNNING
    RUNNING --> RETRY_WAIT
    RETRY_WAIT --> QUEUED
    RUNNING --> RECONCILING
    WAITING_PROVIDER --> RECONCILING
    RECONCILING --> RUNNING
    RUNNING --> SUCCEEDED
    RUNNING --> FAILED
    RECONCILING --> FAILED
    SUCCEEDED --> [*]
    FAILED --> [*]
~~~

Chuyển trạng thái phải được kiểm soát bằng transaction và điều kiện trên state/version hiện tại. Ví dụ, chỉ operation RUNNING có đúng fencing token mới được ghi SUCCEEDED. Một worker cũ không được chuyển operation đã được worker mới tiếp quản thành FAILED hoặc SUCCEEDED.

## 6. Khôi phục khi ứng dụng khởi động lại

Sau khi Spring Boot process khởi động, broker không nên giả định mọi operation chưa terminal đều cần chạy lại từ đầu. Recovery cần phân loại:

- Operation đã ACCEPTED/QUEUED nhưng chưa có worker.
- Operation RUNNING nhưng lease đã hết hạn.
- Operation WAITING_PROVIDER và provider có operation ID riêng.
- Operation RETRY_WAIT đã tới next_attempt_at.
- Operation RECONCILING cần đọc lại provider state.
- Operation terminal đã hoàn tất và chỉ cần giữ để Platform polling.

Một startup recovery flow:

~~~mermaid
sequenceDiagram
    participant APP as Spring Boot app
    participant DB as Operation database
    participant Q as Durable queue
    participant W as Worker
    participant PR as Provider
    participant P as Platform

    APP->>DB: Load non-terminal operations
    DB-->>APP: ACCEPTED / expired lease / due retry
    APP->>DB: Reserve recoverable operations
    APP->>Q: Re-enqueue operation IDs
    Q-->>W: Deliver job
    W->>DB: Load operation and checkpoint
    W->>PR: Reconcile provider state
    PR-->>W: Current resource/operation status
    W->>DB: Resume phase and persist progress
    P->>APP: GET last_operation
    APP->>DB: Read durable operation state
    DB-->>APP: in progress / succeeded / failed
    APP-->>P: OSB last_operation response
~~~

### Thứ tự khởi động

1. Khởi tạo cấu hình và kết nối database.
2. Áp dụng database migration trước khi worker đọc schema mới.
3. Khởi tạo repository và provider adapter.
4. Bật API readiness theo chính sách của deployment.
5. Bật outbox publisher và worker recovery.
6. Quét operation cần tiếp tục theo batch có giới hạn.
7. Tiếp tục polling provider và cập nhật trạng thái.

API có thể sẵn sàng trước khi mọi operation được recovery nếu last_operation vẫn đọc được trạng thái bền vững. Tuy nhiên, readiness policy phải bảo đảm database và các thành phần cần cho response hoạt động. Nếu database chưa sẵn sàng, không trả trạng thái giả cho Platform.

Không chạy toàn bộ operation recovery đồng bộ trong constructor hoặc chặn ApplicationReady event cho đến khi mọi provider job hoàn tất. Một số thao tác có thể kéo dài nhiều giờ; recovery nên được phân trang, giới hạn concurrency và chạy qua worker.

## 7. Lease, heartbeat và fencing token

Khi nhiều worker replica cùng chạy, broker cần cơ chế xác định worker đang giữ quyền thực thi operation. Một lease có thời hạn giúp worker khác tiếp quản nếu process cũ bị crash.

Ví dụ:

1. Worker A lấy operation và ghi lease_owner=A, lease_until=now+30s.
2. Worker A gia hạn lease định kỳ khi vẫn xử lý.
3. Process A bị crash, không còn heartbeat.
4. Lease hết hạn.
5. Worker B lấy operation và tăng fencing_token.
6. Worker B reconcile provider state rồi tiếp tục.

Lease đơn thuần không đủ ngăn worker A cũ tiếp tục chạy nếu nó bị pause lâu rồi sống lại. Vì vậy, mỗi lần tiếp quản cần tăng fencing token. Mọi update database phải kèm token hiện tại; provider adapter cũng nên dùng generation/idempotency key nếu provider hỗ trợ.

Ví dụ SQL reserve operation:

~~~sql
UPDATE service_operation
SET lease_owner = :worker_id,
    lease_until = :lease_until,
    fencing_token = fencing_token + 1,
    state = 'RUNNING',
    updated_at = CURRENT_TIMESTAMP
WHERE operation_id = :operation_id
  AND state IN ('ACCEPTED', 'QUEUED', 'RUNNING', 'RETRY_WAIT', 'RECONCILING')
  AND (lease_until IS NULL OR lease_until < CURRENT_TIMESTAMP);
~~~

Worker phải kiểm tra số hàng được cập nhật. Nếu bằng 0, worker không sở hữu operation và không được thực hiện side effect. Khi ghi checkpoint hoặc kết quả, dùng operation ID cùng fencing token trong điều kiện update.

### Heartbeat và lease duration

Lease phải dài hơn khoảng thời gian giữa hai lần heartbeat và đủ dư địa cho độ trễ mạng/database. Không chọn lease quá ngắn khiến worker khỏe mạnh liên tục mất quyền; cũng không chọn quá dài khiến recovery chậm sau crash.

Nếu worker thực hiện một provider call kéo dài, cần gia hạn lease trong lúc chờ hoặc lưu provider operation ID rồi nhường worker để polling sau. Không giữ transaction database mở trong suốt một provider call dài.

## 8. Checkpoint và tiếp tục đúng phase

Một operation thường gồm nhiều bước. Checkpoint ghi nhận bước cuối cùng đã hoàn tất và dữ liệu cần để tiếp tục. Ví dụ provision database:

~~~text
operation: provision-7f31a9
phase: WAIT_DATABASE_READY
checkpoint:
  database_resource_id: db-provider-8821
  network_configured: true
  credentials_created: false
  last_provider_state: CREATING
~~~

Sau restart, worker không cần tạo lại network hoặc database nếu provider đã tạo chúng. Nó tải checkpoint, kiểm tra resource ID và đọc trạng thái hiện tại của provider. Nếu database đã READY, worker chuyển sang bước tiếp theo; nếu vẫn CREATING, tiếp tục polling; nếu provider báo FAILED, thực hiện retry hoặc compensation theo policy.

### Checkpoint phải được ghi sau bước có thể xác minh

Không ghi checkpoint trước khi side effect hoàn tất. Ví dụ, không đánh dấu DATABASE_CREATED ngay sau khi gửi create request nếu provider mới chỉ trả 202. Hãy lưu provider operation ID và phase WAIT_DATABASE_READY. Khi provider xác nhận resource sẵn sàng, cập nhật phase DATABASE_READY.

Checkpoint nên có version/schema version để code mới có thể đọc dữ liệu operation được tạo bởi phiên bản ứng dụng cũ. Khi deploy rolling update, worker mới có thể tiếp quản operation mà worker phiên bản trước đã tạo. Nếu thay đổi cấu trúc checkpoint, cần migration hoặc reader tương thích ngược.

## 9. Đối chiếu trạng thái với provider

Crash có thể xảy ra ở khoảng giữa provider side effect và database commit:

1. Worker gửi yêu cầu tạo resource.
2. Provider tạo resource thành công.
3. Response bị mất hoặc worker crash.
4. Database broker chưa lưu provider resource ID.

Nếu worker mới gọi create lần nữa mà không reconcile, broker có thể tạo hai database hoặc hai cluster cho cùng instance.

### Quy trình reconcile

Worker nên dùng một hoặc nhiều cách:

- Provider idempotency token gắn với operation ID.
- Resource tag chứa broker instance ID và operation ID.
- Provider operation ID đã lưu trước khi bắt đầu polling.
- Tìm kiếm resource theo deterministic name và owner metadata.
- Đọc trạng thái tài nguyên hiện tại từ provider API.

Kết quả reconcile:

| Trạng thái provider | Hành động broker |
|---|---|
| Resource chưa được tạo | Gửi create request với cùng idempotency identity |
| Resource đang tạo | Lưu provider operation reference và tiếp tục polling |
| Resource đã đạt target | Ghi provider resource ID/checkpoint và chuyển phase |
| Resource tạo dở hoặc cấu hình sai | Tiếp tục sửa, cleanup hoặc compensation theo policy |
| Resource không tồn tại sau một lần delete | Xem bước cleanup đã đạt mục tiêu sau khi xác minh scope |
| Không thể xác định | Giữ RECONCILING, retry đọc trạng thái hoặc cảnh báo operator |

Không suy luận provider operation thất bại chỉ vì broker không nhận được response. Timeout là kết quả không xác định; reconcile phải xảy ra trước khi retry một lệnh có thể tạo side effect.

### Provider operation riêng

Một số provider có asynchronous operation ID riêng. Broker nên lưu cả operation ID của OSB và provider operation ID:

- OSB operation ID được Platform sử dụng khi polling broker.
- Provider operation ID được broker sử dụng khi polling cloud API hoặc Kubernetes controller.

Hai ID này có vòng đời và phạm vi khác nhau. Không trả provider operation ID trực tiếp cho Platform nếu hợp đồng OSB không yêu cầu. Broker đóng vai trò adapter, chuyển trạng thái provider thành trạng thái OSB.

## 10. Retry, backoff và giới hạn lỗi

Worker recovery cần phân loại lỗi:

| Loại lỗi | Cách xử lý |
|---|---|
| Lỗi mạng tạm thời | Retry với exponential backoff và jitter |
| Provider rate limit | Tôn trọng Retry-After hoặc quota policy |
| Provider 5xx | Retry có giới hạn, sau đó reconcile |
| Request provider sai cấu hình | Đánh dấu FAILED nếu không thể tự sửa |
| Thiếu quyền hoặc credential hết hạn | Dừng retry nhanh, báo operator |
| Operation provider đã hoàn tất | Ghi nhận kết quả, không gọi lại side effect |
| Kết quả không xác định | Chuyển RECONCILING trước khi quyết định retry |

Retry count, next_attempt_at và error category phải được lưu bền vững. Nếu broker restart, thời điểm retry không được reset về hiện tại khiến tất cả job cùng chạy dồn dập.

Exponential backoff có thể tính theo công thức:

\[
delay_n = \min(delay_{max}, delay_{base} \times 2^n) + jitter
\]

Jitter giúp nhiều worker không retry cùng thời điểm sau một sự cố provider diện rộng. Cần giới hạn tổng thời gian retry và có dead-letter/manual intervention cho operation không thể tự phục hồi.

## 11. Spring Boot và Spring Cloud Open Service Broker

Spring Cloud Open Service Broker cung cấp abstraction để triển khai service instance lifecycle và ánh xạ request/response OSB API. Ứng dụng nên tách API handler khỏi operation coordinator và worker.

Một cấu trúc package tham khảo:

~~~text
broker/
  osb/
    ServiceInstanceControllerAdapter
    LastOperationControllerAdapter
  application/
    ProvisioningService
    UpdatingService
    DeprovisioningService
    OperationCoordinator
    OperationRecoveryService
  domain/
    ServiceOperation
    OperationState
    OperationCheckpoint
    ServiceInstanceState
  persistence/
    OperationRepository
    InstanceRepository
    OutboxRepository
  messaging/
    OutboxPublisher
    OperationWorker
  provider/
    DatabaseProviderAdapter
    KubernetesProviderAdapter
~~~

Tên class là ví dụ tổ chức ứng dụng, không phải class bắt buộc do framework cung cấp. Interface và method signature cụ thể cần đối chiếu với phiên bản Spring Cloud Open Service Broker đang cài đặt.

### Application service tạo operation

~~~java
public AcceptedOperation accept(
        OperationCommand command) {

    return transactionTemplate.execute(status -> {
        var instance = instanceRepository.lock(command.instanceId());
        operationPolicy.validate(instance, command);

        var fingerprint = requestFingerprinter.create(command);
        var existing = operationRepository.findActive(
                command.platformId(),
                command.instanceId(),
                command.operationType(),
                fingerprint);

        if (existing != null) {
            return AcceptedOperation.from(existing);
        }

        var operation = ServiceOperation.accepted(
                command, fingerprint);
        operationRepository.save(operation);
        instanceRepository.markOperationPending(
                instance.id(), operation.id());
        outboxRepository.append(
                OperationRequested.from(operation));

        return AcceptedOperation.from(operation);
    });
}
~~~

Đoạn mã minh họa nguyên tắc transaction, không phải API có sẵn của Spring Cloud Open Service Broker. Không gọi provider bên trong transaction này. Transaction chỉ ghi trạng thái broker và ý định công việc.

### Worker xử lý operation

~~~java
public void handle(OperationRequested event) {
    var claim = operationRepository.tryAcquireLease(
            event.operationId(), workerId);

    if (claim.isEmpty()) {
        return;
    }

    var operation = claim.get().operation();
    var fencingToken = claim.get().fencingToken();

    try {
        var providerState = providerAdapter.reconcile(operation);
        var result = operationExecutor.resume(
                operation, providerState);

        operationRepository.saveProgress(
                operation.id(), fencingToken, result.checkpoint());

        if (result.isComplete()) {
            operationRepository.markSucceeded(
                    operation.id(), fencingToken, result.description());
            instanceRepository.markReady(
                    operation.instanceId(), operation.id());
        } else {
            operationRepository.scheduleNextAttempt(
                    operation.id(), fencingToken, result.nextAttemptAt());
        }
    } catch (RetryableProviderException ex) {
        operationRepository.scheduleRetry(
                operation.id(), fencingToken, ex.retryAt());
    } catch (PermanentProviderException ex) {
        operationRepository.markFailed(
                operation.id(), fencingToken, safeDescription(ex));
        instanceRepository.markOperationFailed(
                operation.instanceId(), operation.id());
    }
}
~~~

Worker phải kiểm tra fencing token trong mọi lần ghi trạng thái. Provider adapter reconcile trước khi thực hiện bước tiếp theo. Nếu process crash, lease hết hạn và event được gửi lại, worker mới tải checkpoint để tiếp tục.

### Last operation service

Last operation handler chỉ đọc dữ liệu đã lưu:

~~~java
LastOperationResponse getLastOperation(
        String platformId,
        String instanceId,
        String operationId) {

    var operation = operationRepository.find(
            platformId, instanceId, operationId)
        .orElseThrow(OperationNotFoundException::new);

    return switch (operation.state()) {
        case SUCCEEDED -> response("succeeded", operation.description());
        case FAILED -> response("failed", operation.description());
        default -> response("in progress", operation.description());
    };
}
~~~

Đây là pseudocode để diễn giải mapping. Thực tế cần dùng response model của framework và đúng semantics endpoint theo operation type. Last operation không nên gọi provider trực tiếp hoặc tự khởi động công việc; việc polling phải nhẹ, ổn định và chỉ đọc trạng thái đã được worker cập nhật.

## 12. Spring lifecycle, shutdown và rolling deployment

Restart có thể là chủ động hoặc đột ngột. Với shutdown chủ động, ứng dụng nên ngừng nhận job mới, cho worker hiện tại một khoảng thời gian hoàn tất phase an toàn và giải phóng lease. Nếu không thể hoàn tất trong grace period, worker dừng tại checkpoint đã lưu và để operation được recovery.

Không đánh dấu FAILED chỉ vì JVM nhận SIGTERM hoặc container bị thay thế. Việc process dừng không chứng minh nghiệp vụ provider thất bại.

Một quy trình shutdown:

1. Chuyển worker sang trạng thái không nhận message mới.
2. Ngừng claim operation mới.
3. Hoàn tất hoặc checkpoint phase đang chạy.
4. Lưu provider operation reference nếu đã nhận được.
5. Giải phóng lease có kiểm soát hoặc để lease hết hạn.
6. Đóng consumer, connection và application context.

Với rolling deployment, phiên bản mới và cũ có thể cùng chạy trong một khoảng thời gian. Do đó:

- Schema database cần tương thích trong giai đoạn chuyển đổi.
- Checkpoint cũ phải đọc được bởi worker mới.
- Event schema cần versioning.
- Không thay đổi ý nghĩa state đang được worker khác sử dụng.
- Chỉ một worker được sở hữu operation tại một thời điểm qua lease/fencing.
- Không xóa operation đang được Platform polling trong quá trình deploy.

### Spring Boot startup hooks

Có thể dùng ApplicationReadyEvent, ApplicationRunner hoặc scheduler để bật recovery sau khi dependency cần thiết đã sẵn sàng. Chọn hook phù hợp với kiến trúc ứng dụng; tránh đặt toàn bộ logic phục hồi trong constructor hoặc static initializer.

Ví dụ minh họa:

~~~java
@Component
class OperationRecoveryListener {

    private final OperationRecoveryService recoveryService;

    OperationRecoveryListener(OperationRecoveryService recoveryService) {
        this.recoveryService = recoveryService;
    }

    @EventListener(ApplicationReadyEvent.class)
    public void onReady() {
        recoveryService.scheduleRecoveryScan();
    }
}
~~~

scheduleRecoveryScan nên lên lịch công việc có giới hạn, không thực hiện một vòng quét không giới hạn ngay trên thread phát event. Với nhiều replica, mọi replica có thể cùng khởi chạy scan nếu repository claim operation bằng lease và fencing token an toàn.

## 13. Cloud Foundry và Kubernetes

### Cloud Foundry

Khi broker chạy trên Cloud Foundry, ứng dụng có thể được restage hoặc restart trong quá trình vận hành. Process mới phải đọc operation từ database dùng chung và tiếp tục xử lý. Không lưu operation trong local filesystem của container vì filesystem có thể bị thay thế.

Nếu broker dùng managed database hoặc queue service, cần bảo đảm binding credentials của chính broker vẫn còn hiệu lực trong lúc restart. Khi provider API có asynchronous task, lưu provider task ID để process mới có thể polling tiếp.

### Kubernetes

Khi broker chạy trong Kubernetes, Deployment có thể tạo pod mới trong rolling update hoặc pod bị restart do node failure. Worker nên xử lý termination signal, dừng claim job mới và checkpoint trước khi kết thúc. Lease/fencing giúp pod mới tiếp quản operation khi pod cũ biến mất.

Không dựa vào Kubernetes Pod name như định danh operation bền vững. Pod name chỉ nhận diện process tạm thời; operation ID phải do broker sinh và lưu trong database.

Kubernetes Job hoặc controller có thể được dùng để thực thi từng loại công việc, nhưng trạng thái OSB operation vẫn phải được lưu ở broker. Không coi việc Kubernetes Job object chuyển Complete là thay thế hoàn toàn cho việc broker xác minh tài nguyên và cập nhật instance state.

## 14. Bảo mật dữ liệu operation

Operation record và checkpoint có thể chứa provider resource ID, tenant ID, region, cấu hình hoặc tham chiếu secret. Đây là dữ liệu vận hành cần kiểm soát truy cập.

- Chỉ API node được phép đọc operation trong đúng Platform/instance scope.
- Worker chỉ có quyền truy cập operation và secret cần cho loại công việc của nó.
- Không đưa password/token vào checkpoint, outbox payload hoặc error description.
- Dùng secret reference và lấy secret từ vault khi cần.
- Mã hóa dữ liệu nhạy cảm trong database và queue.
- Operation ID nên đủ khó đoán và luôn đi kèm authorization; không xem ID là credential.
- Audit việc đọc secret, thay đổi operation state và thao tác recovery thủ công.
- Giới hạn thông tin provider trong description mà Platform nhìn thấy.

Khi cần operator retry hoặc resume operation thủ công, thao tác đó phải được xác thực, phân quyền và audit. Không cung cấp endpoint quản trị nội bộ có thể thay đổi operation state mà không kiểm tra tenant, instance và fencing token.

## 15. Quan sát operation sau restart

Các metric cần phản ánh cả sức khỏe worker và tuổi của operation:

| Metric | Ý nghĩa |
|---|---|
| active_operations | Số operation chưa terminal |
| oldest_pending_operation_age | Tuổi của operation chờ lâu nhất |
| expired_leases | Số lease hết hạn cần recovery |
| recovery_scan_count | Số operation được scan/claim sau startup |
| operation_recovered_total | Số operation đã được tiếp quản thành công |
| provider_reconcile_total | Số lần đối chiếu trạng thái provider |
| operation_retry_total | Số lần retry |
| operation_failed_total | Số operation terminal failed |
| outbox_backlog | Số event chưa publish |
| last_operation_latency | Thời gian phản hồi endpoint polling |

Log nên có operation ID, instance ID, operation type, phase, worker ID, fencing token, provider operation reference và trace/request ID. Không dùng operation ID hoặc tenant ID có cardinality rất cao làm metric label nếu hệ thống monitoring không phù hợp.

Các cảnh báo hữu ích:

- Operation ở RUNNING nhưng lease đã hết hạn quá lâu.
- Operation ở RECONCILING vượt thời gian cho phép.
- Outbox backlog tăng liên tục.
- Worker không có heartbeat hoặc queue consumer lag tăng.
- Operation ở in progress quá thời gian SLA.
- Provider resource tồn tại nhưng không có operation/instance record tương ứng.

## 16. Kiểm thử crash và recovery

Kiểm thử restart cần mô phỏng crash tại các ranh giới side effect, không chỉ restart ứng dụng khi không có operation.

| Điểm crash | Kết quả mong đợi sau restart |
|---|---|
| Sau khi ghi operation, trước publish outbox | Publisher phát lại event |
| Sau khi publish, trước đánh dấu outbox | Event có thể lặp; worker không tạo side effect trùng |
| Sau khi claim lease | Lease hết hạn, worker khác tiếp quản |
| Trước provider call | Worker thực hiện phase chưa chạy |
| Sau provider call, trước lưu provider ID | Worker reconcile resource theo operation tag/idempotency key |
| Khi provider operation đang chạy | Worker mới polling provider operation ID đã lưu |
| Sau khi ghi checkpoint | Worker tiếp tục từ phase kế tiếp |
| Sau khi provider hoàn tất, trước mark succeeded | Worker reconcile và xác minh target state |
| Sau mark succeeded, trước Platform polling | last_operation trả succeeded từ database |
| Trong rolling deployment | Worker mới đọc được checkpoint và event của phiên bản cũ |

### Bộ kiểm thử tích hợp

1. Gửi provision request có accepts_incomplete=true và nhận 202.
2. Xác nhận operation và outbox event đã commit.
3. Cho worker chạy tới một checkpoint có thể quan sát.
4. Dừng process hoặc mô phỏng worker mất lease.
5. Khởi động worker mới.
6. Xác nhận worker mới tiếp quản cùng operation ID.
7. Xác nhận provider chỉ có một tài nguyên tương ứng với operation.
8. Gọi last_operation từ API node khác.
9. Xác nhận trạng thái in progress trong lúc xử lý và succeeded sau khi hoàn tất.
10. Gửi lại request gốc và xác nhận broker trả kết quả idempotent, không tạo operation mới.

Nên có fault injection cho timeout, duplicate queue delivery, database failover, provider 429/5xx, mất response sau side effect và shutdown trong lúc chờ provider. Kiểm tra invariant quan trọng: một OSB instance không có hai operation không tương thích cùng sở hữu quyền thay đổi trạng thái.

## 17. Lỗi thiết kế thường gặp

### Lưu operation trong RAM

Sau restart, broker không thể tìm thấy operation dù Platform vẫn polling. Hãy lưu operation và trạng thái instance trong database bền vững.

### Chỉ dựa vào queue để biết công việc còn tồn tại

Message có thể bị ack, redeliver hoặc hết retention. Database operation mới là nguồn trạng thái chuẩn; outbox giúp phát lại công việc chưa được publish.

### Khởi động lại là chạy lại từ đầu

Lặp lại provider create/update có thể tạo tài nguyên trùng hoặc làm hỏng migration. Worker phải đọc checkpoint và reconcile provider trước khi lặp side effect.

### Giữ transaction mở khi gọi provider

Provider call có thể kéo dài, gây lock lâu và cạn connection pool. Dùng transaction ngắn để claim/ghi trạng thái; thực hiện I/O bên ngoài transaction; sau đó lưu kết quả với fencing token.

### Dùng lease nhưng không có fencing

Worker cũ có thể sống lại sau khi lease hết hạn và ghi đè trạng thái của worker mới. Dùng fencing token hoặc generation trong điều kiện cập nhật.

### Đánh dấu FAILED khi process dừng

Restart không đồng nghĩa thao tác nghiệp vụ thất bại. Giữ operation ở trạng thái recoverable, để lease hết hạn và worker khác reconcile.

### Xóa operation ngay khi hoàn tất

Platform có thể vẫn đang polling hoặc retry request cũ. Giữ kết quả terminal trong thời hạn retention đủ dài, sau đó cleanup theo policy.

## 18. Checklist triển khai

- [ ] Operation được ghi bền vững trước khi broker trả 202.
- [ ] Operation ID được lưu và tra cứu trong đúng Platform/instance scope.
- [ ] Operation state, instance state và outbox event được commit nhất quán.
- [ ] Queue chỉ phân phối công việc; database là nguồn trạng thái chuẩn.
- [ ] Worker xử lý duplicate message idempotent.
- [ ] Có lease, heartbeat và fencing token để tiếp quản an toàn.
- [ ] Checkpoint được ghi sau khi phase có thể xác minh đã hoàn tất.
- [ ] Provider operation ID/resource ID được lưu để polling và reconcile.
- [ ] Recovery scan tìm ACCEPTED, lease hết hạn và retry đã đến hạn.
- [ ] Recovery chạy theo batch/concurrency limit, không chặn startup vô hạn.
- [ ] Last_operation chỉ đọc trạng thái bền vững và ánh xạ đúng OSB state.
- [ ] Shutdown ngừng nhận job mới và checkpoint operation đang chạy.
- [ ] Rolling deployment giữ tương thích schema, event và checkpoint.
- [ ] Operation terminal được giữ đủ lâu cho Platform polling.
- [ ] Có crash-injection test tại các ranh giới database/provider/queue.
- [ ] Secret không xuất hiện trong operation payload, checkpoint, log hoặc metric.

## Kết luận

Để Platform tiếp tục theo dõi một tác vụ sau khi broker restart, operation phải được lưu bền vững và có thể được worker khác tiếp quản. Transactional outbox bảo đảm công việc không bị mất giữa database và queue; lease cùng fencing token ngăn worker cũ ghi đè; checkpoint và provider reconciliation giúp tiếp tục từ trạng thái thực tế thay vì chạy lại mù quáng. API last_operation đọc cùng kho trạng thái nên vẫn trả lời nhất quán trong lúc worker được phục hồi. Khi kết hợp các cơ chế này với idempotency, retry có giới hạn và kiểm thử crash, service broker Spring Cloud có thể duy trì vòng đời provision, update và deprovision qua restart, rolling deployment và sự cố hạ tầng.
