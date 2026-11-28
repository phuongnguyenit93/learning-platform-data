# Bổ sung tính lặp an toàn và kiểm thử yêu cầu cạnh tranh

Trong service broker, platform có thể gửi nhiều yêu cầu provision cho cùng một service instance gần như đồng thời. Một request có thể bị retry sau timeout trong khi request đầu vẫn đang chạy; queue có thể giao lại cùng message; hai worker có thể cùng nhận một operation khi lease hết hạn. Nếu broker chỉ kiểm tra bằng câu lệnh SELECT rồi mới INSERT, nhiều request có thể cùng vượt qua bước kiểm tra và tạo nhiều tài nguyên bên nhà cung cấp.

Capstone này yêu cầu bạn gia cố một luồng provision của **SPRING_CLOUD_SERVICE_BROKER** để xử lý an toàn request lặp và request cạnh tranh. Broker sử dụng Open Service Broker API (OSB API), Spring Cloud Open Service Broker (SCOSB), database bền vững và provider adapter. Bạn sẽ thiết kế idempotency key, request fingerprint, transaction, unique constraint, operation/outbox, worker claim và provider reconciliation; sau đó chứng minh bằng kiểm thử đồng thời và fault injection rằng một service instance không bị provision nhiều lần.

Bài thực hành tập trung vào một tình huống cụ thể: Cloud Foundry hoặc platform OSB gửi nhiều PUT provision cho cùng instance_id. Có request giống nhau cần được gộp thành cùng một kết quả; có request khác plan hoặc parameters cần bị từ chối; provider có thể đã tạo resource nhưng broker chưa nhận được response. Kết quả cần đạt là broker duy trì một instance record, một operation provision có thẩm quyền và một provider resource được xác minh.

## 1. Kịch bản capstone

Bạn được giao một broker cung cấp PostgreSQL managed service. Catalog có service svc-postgresql với hai plan:

| Plan ID | Tài nguyên minh họa | Quyền truy cập |
|---|---|---|
| plan-small | 2 vCPU, 4 GB RAM, 50 GB storage | Theo cấu hình binding |
| plan-standard | 4 vCPU, 16 GB RAM, 200 GB storage | Theo cấu hình binding |

Platform gửi request:

~~~http
PUT /v2/service_instances/instance-orders-100?accepts_incomplete=true
Content-Type: application/json
X-Broker-API-Version: 2.17
~~~

~~~json
{
  "service_id": "svc-postgresql",
  "plan_id": "plan-standard",
  "parameters": {
    "storage_gb": 200,
    "region": "ap-southeast-1",
    "high_availability": true
  },
  "context": {
    "platform": "cloud-foundry"
  }
}
~~~

Trong một tình huống thực tế, các request sau có thể xảy ra:

1. Platform gửi request A; broker tạo operation và trả 202.
2. Platform không nhận được response do network timeout nên gửi lại request B với cùng instance_id và cùng nội dung.
3. Một retry khác đến khi worker đang gọi provider.
4. Provider tạo database thành công nhưng response bị mất.
5. Queue giao lại message cho worker khác.
6. Một request C đến cùng instance_id nhưng yêu cầu plan-small.
7. Hai worker có thể chạy chồng lên nhau nếu worker đầu bị pause và lease hết hạn.

Thiết kế phải phân biệt request lặp hợp lệ, request xung đột, retry operation và kết quả provider chưa xác định. Không thể giải quyết tất cả bằng cách bắt exception AlreadyExists.

## 2. Mục tiêu và phạm vi triển khai

Sau capstone, broker cần đáp ứng các mục tiêu sau:

- Một khóa instance chỉ tạo tối đa một service instance record trong phạm vi platform đã xác định.
- Cùng một yêu cầu provision gửi nhiều lần không tạo operation hoặc provider resource mới.
- Request có cùng instance_id nhưng khác service, plan, tenant hoặc parameters quan trọng được phát hiện là xung đột.
- Request đến khi operation đang chạy nhận lại cùng operation hiện hành.
- Request đến sau khi instance đã READY nhận kết quả hiện tại theo contract OSB API.
- Database bảo vệ uniqueness bằng constraint, không phụ thuộc vào kiểm tra trong bộ nhớ.
- Instance, operation và outbox event được ghi nguyên tử.
- Worker claim operation có lease và cơ chế ngăn worker cũ ghi đè kết quả mới.
- Provider call dùng idempotency token ổn định nếu provider hỗ trợ.
- Nếu provider đã tạo resource nhưng broker chưa lưu response, worker reconciliation tìm và xác minh resource trước khi create lại.
- Mọi hành vi có kiểm thử unit, integration và concurrency test.
- Log, metric và response không làm lộ secret.

Phạm vi capstone tập trung vào provision. Bạn có thể dùng cùng nguyên tắc cho update, bind, unbind và deprovision, nhưng không cần triển khai lại toàn bộ lifecycle nếu bài toán hiện tại chỉ yêu cầu chứng minh tính lặp an toàn của provision.

## 3. Kiến trúc đích

Tách request path khỏi provider side effect. HTTP handler xác thực, validate và ghi nhận operation; worker xử lý provider call ở ngoài database transaction.

~~~mermaid
flowchart LR
    P["OSB Platform"] --> H["SCOSB HTTP adapter"]
    H --> V["Validate + fingerprint"]
    V --> A["Provision application service"]
    A --> DB[("Broker database")]
    DB --> O["Transactional outbox"]
    O --> Q["Queue / worker trigger"]
    Q --> W["Provision worker"]
    W --> I["Provider idempotency + lookup"]
    I --> C["Cloud / database provider"]
    C --> W
    W --> DB
    H --> R["OSB response"]
~~~

Các thành phần:

| Thành phần | Trách nhiệm |
|---|---|
| SCOSB HTTP adapter | Nhận OSB request, map response và kiểm tra API contract |
| Request validator | Kiểm tra service, plan, parameters và context |
| Fingerprint service | Chuẩn hóa dữ liệu nghiệp vụ và tạo digest ổn định |
| Provision application service | Xử lý insert, duplicate, conflict và tạo operation |
| Instance repository | Lưu trạng thái service instance và enforce unique key |
| Operation repository | Lưu trạng thái, attempt, lease và provider reference |
| Outbox publisher | Phát event sau khi transaction commit |
| Worker | Claim operation, gọi provider và checkpoint kết quả |
| Provider adapter | Gọi API provider với idempotency key và lookup |
| Reconciliation service | Đối chiếu trạng thái broker với provider sau kết quả không chắc chắn |

Không để controller tự thực hiện SELECT, INSERT, gọi provider và retry trong cùng một method. Tách lớp giúp kiểm thử từng ranh giới và kiểm soát transaction.

## 4. Quy định idempotency cho request provision

OSB API sử dụng PUT với service instance ID làm định danh của instance. Broker phải coi cùng instance ID là cùng đối tượng trong phạm vi platform đã xác định.

Trong capstone, áp dụng quy tắc nghiệp vụ:

| Trạng thái hiện có | Request mới | Hành vi mong đợi |
|---|---|---|
| Chưa có instance | Request hợp lệ | Tạo instance, operation và outbox |
| Đang provision | Cùng tenant, service, plan và fingerprint | Trả lại operation hiện hành; không tạo operation mới |
| Đã READY | Cùng nội dung nghiệp vụ | Trả kết quả hiện có theo contract OSB API |
| Đang provision | Khác plan hoặc parameters ảnh hưởng tài nguyên | Từ chối conflict |
| Đã READY | Khác service hoặc plan | Từ chối conflict theo contract |
| Kết quả provider chưa rõ | Cùng request | Reconcile operation cũ trước khi thử side effect mới |
| Operation thất bại chắc chắn chưa tạo resource | Cùng request | Cho phép retry theo policy và giữ định danh operation/idempotency phù hợp |

Với API version được triển khai, kiểm tra status code và response body theo OSB specification. Thông thường, lần provision mới đồng bộ trả 201 Created; thao tác bất đồng bộ được chấp nhận trả 202 Accepted kèm operation identifier; request trùng với instance đã tồn tại cần trả kết quả idempotent theo contract; request xung đột thường trả 409 Conflict. Không hardcode status chỉ dựa trên bảng minh họa nếu version/behavior của broker có quy định cụ thể khác.

Một nguyên tắc quan trọng: request lặp không được tạo side effect thứ hai chỉ vì HTTP connection của request đầu đã đóng.

## 5. Phân biệt instance key, request fingerprint và provider key

Ba định danh này phục vụ ba mục đích khác nhau.

| Định danh | Dùng để | Có thay đổi giữa các retry không? |
|---|---|---|
| Instance key | Nhận diện service instance trong broker | Không |
| Request fingerprint | So sánh nội dung nghiệp vụ của request | Không nếu nội dung nghiệp vụ không đổi |
| Provider idempotency key | Nhận diện một side effect provision tại provider | Không trong mọi retry của cùng operation |

### Instance key

Với broker đa platform, có thể dùng:

~~~text
instance_key = platform_id + ":" + instance_id
~~~

Nếu platform có namespace hoặc tenant scope riêng, lưu tenant đã xác thực cùng instance record và kiểm tra ownership khi đọc lại. Không dùng tên resource provider làm instance key vì tên có thể trùng giữa account hoặc tenant.

### Request fingerprint

Fingerprint được tính từ dữ liệu đã validate và canonicalize:

~~~json
{
  "service_id": "svc-postgresql",
  "plan_id": "plan-standard",
  "parameters": {
    "high_availability": true,
    "region": "ap-southeast-1",
    "storage_gb": 200
  },
  "provider_target": "postgres-prod/ap-southeast-1"
}
~~~

Không đưa trace ID, timestamp, HTTP header không liên quan hoặc thứ tự field JSON vào fingerprint. Nếu parameters chứa secret, không ghi plaintext vào digest/log; dùng HMAC với key quản lý riêng nếu cần bảo vệ khả năng đoán giá trị. Fingerprint cần có version để có thể thay đổi quy tắc canonicalization có kiểm soát.

### Provider idempotency key

Ví dụ:

~~~text
broker-prod:cf-prod:instance-orders-100:PROVISION
~~~

Key phải ổn định cho cùng operation. Không thêm attempt number hoặc random UUID mới ở mỗi lần retry. Nếu provider giới hạn độ dài, dùng hash/digest của các định danh ổn định.

## 6. Thiết kế database có constraint

Database là nơi thực thi uniqueness khi nhiều request cùng đến. Kiểm tra trong Java không đủ vì hai request có thể chạy đồng thời trên nhiều replica.

Ví dụ PostgreSQL schema rút gọn:

~~~sql
CREATE TABLE broker_service_instance (
    platform_id VARCHAR(64) NOT NULL,
    instance_id VARCHAR(128) NOT NULL,
    tenant_id VARCHAR(128) NOT NULL,
    service_id VARCHAR(128) NOT NULL,
    plan_id VARCHAR(128) NOT NULL,
    request_fingerprint VARCHAR(128) NOT NULL,
    fingerprint_version INTEGER NOT NULL DEFAULT 1,
    state VARCHAR(32) NOT NULL,
    provider_resource_id VARCHAR(256),
    version BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (platform_id, instance_id)
);

CREATE TABLE broker_operation (
    operation_id VARCHAR(128) PRIMARY KEY,
    platform_id VARCHAR(64) NOT NULL,
    instance_id VARCHAR(128) NOT NULL,
    operation_type VARCHAR(32) NOT NULL,
    request_fingerprint VARCHAR(128) NOT NULL,
    provider_idempotency_key VARCHAR(256) NOT NULL,
    state VARCHAR(32) NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    worker_id VARCHAR(128),
    lease_until TIMESTAMPTZ,
    fencing_token BIGINT NOT NULL DEFAULT 0,
    provider_operation_id VARCHAR(256),
    provider_resource_id VARCHAR(256),
    last_error_code VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    FOREIGN KEY (platform_id, instance_id)
        REFERENCES broker_service_instance(platform_id, instance_id),
    UNIQUE (platform_id, instance_id, operation_type)
);

CREATE TABLE broker_outbox (
    event_id VARCHAR(128) PRIMARY KEY,
    aggregate_id VARCHAR(128) NOT NULL,
    event_type VARCHAR(64) NOT NULL,
    event_version INTEGER NOT NULL,
    payload JSONB NOT NULL,
    published_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

Đây là schema minh họa cho một operation provision duy nhất trên mỗi instance. Nếu broker hỗ trợ nhiều lần operation cùng loại sau khi deprovision/reprovision, cần bổ sung generation hoặc lifecycle sequence vào unique key. Không xóa lịch sử operation chỉ để tránh unique conflict.

Những điều cần kiểm tra:

- Primary key/unique constraint phản ánh đúng phạm vi platform và instance.
- Operation liên kết với instance bằng foreign key.
- Outbox event có ID duy nhất.
- Provider idempotency key được lưu bền vững.
- State và version hỗ trợ conditional update.
- Không lưu provider password/token trong các cột fingerprint hoặc log.
- Index được thêm cho worker polling và reconciliation query.

## 7. Ghi instance, operation và outbox trong một transaction

Không thực hiện mô hình SELECT trước, INSERT sau mà thiếu unique constraint. Hai request có thể cùng thấy chưa có instance.

Luồng insert an toàn:

~~~sql
INSERT INTO broker_service_instance (
    platform_id, instance_id, tenant_id, service_id, plan_id,
    request_fingerprint, fingerprint_version, state
)
VALUES (
    :platform_id, :instance_id, :tenant_id, :service_id, :plan_id,
    :fingerprint, :fingerprint_version, 'PROVISIONING'
)
ON CONFLICT (platform_id, instance_id) DO NOTHING
RETURNING platform_id, instance_id;
~~~

Nếu insert trả về một row, request này thắng quyền tạo instance. Trong cùng transaction:

1. Tạo operation ID.
2. Tạo provider idempotency key ổn định.
3. Insert operation ở trạng thái QUEUED.
4. Insert outbox event ProvisionRequested.
5. Commit.

Nếu insert không trả row, request phải đọc instance hiện có, so sánh tenant/service/plan/fingerprint và quyết định replay hoặc conflict. Với PostgreSQL READ COMMITTED, thao tác đọc tiếp theo sau khi câu INSERT chờ unique conflict sẽ thấy transaction thắng đã commit; vẫn cần xử lý trường hợp winner rollback và insert có thể thành công ở attempt tiếp theo.

Không gọi provider trước khi transaction này commit. Nếu provider call xảy ra trước commit, broker có thể tạo resource nhưng không có record hoặc outbox bền vững để phục hồi.

### Pseudocode transaction

~~~text
BEGIN

  inserted = INSERT instance ON CONFLICT DO NOTHING

  IF inserted:
      INSERT operation(state = QUEUED)
      INSERT outbox(event = ProvisionRequested)
      COMMIT
      return NEW_OPERATION

  existing = SELECT instance FOR UPDATE

  IF ownership does not match:
      ROLLBACK
      return NOT_FOUND_OR_FORBIDDEN

  IF fingerprint differs:
      ROLLBACK
      return CONFLICT

  operation = SELECT current provision operation

  COMMIT
  return REPLAY(existing, operation)
~~~

SELECT ... FOR UPDATE ở nhánh duplicate giúp serialize quyết định dựa trên record hiện có. Cần thiết kế isolation và retry transaction theo lỗi serialization/deadlock của database.

## 8. Xử lý request trùng theo trạng thái

Sau khi tìm thấy instance, không phải mọi request lặp đều nhận cùng một response body. Quyết định dựa trên state và operation hiện tại.

| Instance state | Operation state | Hành vi |
|---|---|---|
| PROVISIONING | QUEUED | Trả trạng thái operation đã nhận |
| PROVISIONING | CLAIMED/RUNNING | Trả cùng operation ID; không enqueue operation mới |
| PROVISIONING | RECONCILIATION_REQUIRED | Trả operation hiện hành; để worker reconcile |
| READY | SUCCEEDED | Trả kết quả instance đã tồn tại theo OSB contract |
| FAILED | FAILED, provider chưa tạo resource | Có thể retry theo policy đã định |
| FAILED/UNKNOWN | Outcome chưa rõ | Giữ trạng thái và reconcile trước khi retry |
| DEPROVISIONING | Deprovision đang chạy | Không khởi tạo provision mới mâu thuẫn |
| DELETED | Instance tombstone còn hiệu lực | Áp dụng chính sách reprovision/generation rõ ràng |

Không tạo một operation provision mới chỉ vì request mới có request ID khác. Request ID và correlation ID giúp trace; chúng không định nghĩa một provisioning action mới.

## 9. Worker claim và lease

Queue có thể giao cùng message nhiều lần. Worker cũng có thể chết sau khi claim operation. Vì vậy, worker phải claim bằng một thao tác atomic và lease có thời hạn.

Ví dụ claim:

~~~sql
UPDATE broker_operation
SET state = 'CLAIMED',
    worker_id = :worker_id,
    lease_until = now() + interval '60 seconds',
    fencing_token = fencing_token + 1,
    attempt_count = attempt_count + 1,
    updated_at = now()
WHERE operation_id = :operation_id
  AND state IN ('QUEUED', 'RETRYABLE')
  AND (lease_until IS NULL OR lease_until < now())
RETURNING operation_id, fencing_token, provider_idempotency_key;
~~~

Trong hệ thống thực tế, cần xử lý cả operation đang CLAIMED nhưng lease hết hạn, có thể dùng câu UPDATE/claim riêng hoặc FOR UPDATE SKIP LOCKED. Worker chỉ tiếp tục khi claim thành công.

Worker cần:

- Heartbeat/renew lease khi operation kéo dài.
- Lưu fencing token khi claim.
- Kiểm tra fencing token ở các lần ghi kết quả.
- Không giữ database transaction mở khi gọi provider.
- Dừng ghi nếu lease đã bị worker khác thay thế.
- Kiểm tra provider state trước khi retry side effect sau lease expiry.

Lease giúp điều phối worker, nhưng không tự bảo đảm provider side effect chỉ chạy một lần. Provider idempotency và reconciliation vẫn cần thiết.

## 10. Gọi provider bằng idempotency key ổn định

Provider adapter nhận operation và key đã lưu trong database:

~~~java
public interface PostgreSqlProvider {
    Mono<ProviderResource> createDatabase(
            ProvisionSpec spec,
            String idempotencyKey);

    Mono<Optional<ProviderResource>> findByIdempotencyKey(
            String idempotencyKey);

    Mono<ProviderResource> getByResourceId(String resourceId);
}
~~~

Interface minh họa. Provider cụ thể có thể không hỗ trợ lookup bằng idempotency key; khi đó cần dùng ownership tags/labels hoặc external reference do broker tạo.

Worker không tự sinh key mới cho từng attempt:

~~~java
public Mono<ProviderResource> provision(
        ProvisionOperation operation) {

    return provider.findByIdempotencyKey(
                    operation.providerIdempotencyKey())
            .flatMap(Mono::justOrEmpty)
            .switchIfEmpty(Mono.defer(() ->
                    provider.createDatabase(
                            operation.provisionSpec(),
                            operation.providerIdempotencyKey())));
}
~~~

Đoạn code là pseudocode về luồng. Trong triển khai thật, kiểu Optional và Mono cần được thống nhất; cần phân loại lỗi lookup, timeout và not-found rõ ràng. Không coi mọi lỗi lookup là resource không tồn tại.

Nếu provider trả AlreadyExists, worker phải tra cứu và xác minh resource. Chỉ khi marker, tenant, instance ID, provider account và cấu hình khớp mới attach resource vào broker instance.

## 11. Reconciliation khi response provider bị mất

Đây là failure mode bắt buộc phải kiểm thử:

1. Worker gửi create request với provider idempotency key K.
2. Provider tạo database.
3. Response bị mất hoặc worker timeout.
4. Broker không biết resource ID.
5. Message được giao lại.
6. Worker mới phải tìm resource theo K hoặc ownership marker trước khi create.

Sơ đồ:

~~~mermaid
sequenceDiagram
    participant W1 as Worker A
    participant P as Provider
    participant DB as Broker DB
    participant W2 as Worker B

    W1->>P: Create with stable key K
    P->>P: Create database
    P--xW1: Response lost
    W1->>DB: Mark RECONCILIATION_REQUIRED
    W2->>DB: Claim expired operation
    W2->>P: Lookup by K / ownership marker
    P-->>W2: Existing resource
    W2->>W2: Verify owner and configuration
    W2->>DB: Attach resource ID and mark READY
~~~

Các nhánh xử lý:

| Kết quả lookup | Hành động |
|---|---|
| Tìm thấy resource, owner và cấu hình khớp | Attach mapping, hoàn tất operation |
| Resource đang tạo | Poll provider operation hoặc retry lookup |
| Không tìm thấy, provider xác nhận chắc chắn chưa tạo | Gọi create lại bằng cùng key |
| Lookup timeout hoặc eventual consistency | Giữ outcome uncertain, retry lookup có giới hạn |
| Resource có owner khác | Conflict/manual review, không adopt |
| Resource cùng owner nhưng cấu hình khác | Reconcile theo policy hoặc conflict; không đánh dấu READY giả |

Không tự động xóa resource khi gặp AlreadyExists. Resource có thể đang chứa dữ liệu hoặc thuộc instance khác.

## 12. Fencing để worker cũ không ghi đè kết quả

Giả sử worker A claim operation với fencing token 7 rồi bị pause. Lease hết hạn; worker B claim cùng operation với token 8 và hoàn tất. Sau đó worker A thức dậy và cố ghi provider resource ID cũ.

Mọi update kết quả phải có điều kiện token:

~~~sql
UPDATE broker_operation
SET state = 'SUCCEEDED',
    provider_resource_id = :provider_resource_id,
    updated_at = now()
WHERE operation_id = :operation_id
  AND worker_id = :worker_id
  AND fencing_token = :fencing_token
  AND state IN ('CLAIMED', 'RUNNING');
~~~

Nếu update ảnh hưởng 0 row, worker không còn quyền sở hữu operation. Không được ghi đè state mới hơn.

Cần bảo vệ cả instance mapping. Một fencing check ở operation nhưng một UPDATE instance không có điều kiện vẫn có thể cho worker cũ ghi đè provider_resource_id. Có thể cập nhật instance và operation trong cùng transaction với điều kiện fencing/version tương ứng.

## 13. Spring application service cho request provision

Tạo một command độc lập với SCOSB request model:

~~~java
public record ProvisionCommand(
        String platformId,
        String tenantId,
        String instanceId,
        String serviceId,
        String planId,
        Map<String, Object> parameters,
        Map<String, Object> context
) {
}

public sealed interface ProvisionDecision {
    record Created(String operationId) implements ProvisionDecision {}
    record ReplayInProgress(String operationId) implements ProvisionDecision {}
    record AlreadyReady(String instanceId) implements ProvisionDecision {}
    record Conflict(String reasonCode) implements ProvisionDecision {}
}
~~~

Application service điều phối repository trong reactive transaction:

~~~java
public class ProvisionApplicationService {

    private final TransactionalOperator transaction;
    private final InstanceRepository instances;
    private final OperationRepository operations;
    private final OutboxRepository outbox;
    private final FingerprintService fingerprints;

    public Mono<ProvisionDecision> accept(ProvisionCommand command) {
        String fingerprint = fingerprints.create(command);

        return transaction.transactional(
                instances.insertIfAbsent(command, fingerprint)
                        .flatMap(inserted -> {
                            if (inserted) {
                                return operations.createQueued(
                                                command, fingerprint)
                                        .flatMap(operation ->
                                                outbox.addProvisionRequested(operation)
                                                        .thenReturn(
                                                                new ProvisionDecision.Created(
                                                                        operation.operationId())));
                            }

                            return instances.findForUpdate(
                                            command.platformId(),
                                            command.instanceId())
                                    .flatMap(existing -> {
                                        if (!existing.matchesOwner(command)
                                                || !existing.matchesRequest(fingerprint)) {
                                            return Mono.just(
                                                    new ProvisionDecision.Conflict(
                                                            "INSTANCE_REQUEST_MISMATCH"));
                                        }

                                        return operations.findProvisionForInstance(
                                                        command.platformId(),
                                                        command.instanceId())
                                                .map(this::decisionForExisting);
                                    });
                        })
        );
    }

    private ProvisionDecision decisionForExisting(
            ProvisionOperation operation) {
        return switch (operation.state()) {
            case QUEUED, CLAIMED, RUNNING, RECONCILIATION_REQUIRED ->
                    new ProvisionDecision.ReplayInProgress(
                            operation.operationId());
            case SUCCEEDED ->
                    new ProvisionDecision.AlreadyReady(
                            operation.instanceId());
            default ->
                    new ProvisionDecision.Conflict(
                            "OPERATION_REQUIRES_RECOVERY");
        };
    }
}
~~~

Đây là skeleton kiến trúc, không phải code drop-in. Cần bổ sung imports, enum state, error handling, database-specific insertIfAbsent, transaction manager và mapping response SCOSB. Trong reactive application, dùng reactive transaction manager/TransactionalOperator phù hợp; không trộn blocking repository vào event loop.

Không bắt duplicate-key exception rồi tiếp tục dùng transaction đã bị database đánh dấu rollback-only. Dùng ON CONFLICT DO NOTHING hoặc transaction mới để đọc lại record hiện có.

## 14. Ánh xạ kết quả về OSB response

Adapter SCOSB chuyển ProvisionDecision thành response theo contract đang hỗ trợ.

| ProvisionDecision | Adapter xử lý |
|---|---|
| Created | Trả success đồng bộ hoặc 202 cùng operation ID tùy provider workflow |
| ReplayInProgress | Trả cùng operation đang xử lý; không phát operation mới |
| AlreadyReady | Trả kết quả instance hiện hữu theo OSB API version |
| Conflict | Trả lỗi conflict có error code ổn định, không lộ nội bộ |

Các điểm cần kiểm tra:

- operation identifier trong response phải là operation đã lưu.
- dashboard_url chỉ trả nếu offering có giá trị hợp lệ.
- Không trả provider resource ID nếu contract không yêu cầu.
- Error description không chứa SQL, provider token hoặc secret.
- Request thiếu accepts_incomplete=true phải được xử lý theo khả năng async và OSB API contract.
- Header X-Broker-API-Version được validate theo version đã hỗ trợ.

Không để adapter tự quyết định idempotency bằng cách gọi repository riêng. Quyết định phải nằm trong application service và được bảo vệ bởi database constraint.

## 15. Kiểm thử unit cho fingerprint và decision

Unit test không cần provider hoặc database thật.

Các ca cho FingerprintService:

- JSON object có thứ tự key khác nhau nhưng cùng giá trị phải có fingerprint giống nhau.
- Service ID khác phải có fingerprint khác.
- Plan ID khác phải có fingerprint khác.
- Parameters ảnh hưởng tài nguyên thay đổi phải có fingerprint khác.
- Trace ID/timestamp thay đổi không làm fingerprint khác.
- Secret không xuất hiện trong log hoặc output debug.
- Fingerprint version được ghi cùng instance.

Các ca cho decision service:

| Trạng thái | Request | Kết quả |
|---|---|---|
| Không có instance | Hợp lệ | Created |
| PROVISIONING | Cùng fingerprint | ReplayInProgress |
| READY | Cùng fingerprint | AlreadyReady |
| PROVISIONING | Khác fingerprint | Conflict |
| Tenant khác | Cùng instance ID | Không tiết lộ record; từ chối |
| RECONCILIATION_REQUIRED | Cùng fingerprint | ReplayInProgress/reconciliation hiện hành |

Ví dụ:

~~~java
@Test
void sameBusinessPayloadProducesSameFingerprint() {
    var first = commandWithParameters(
            Map.of("storage_gb", 200, "region", "ap-southeast-1"));
    var second = commandWithParameters(
            Map.of("region", "ap-southeast-1", "storage_gb", 200));

    assertThat(fingerprint.create(first))
            .isEqualTo(fingerprint.create(second));
}
~~~

## 16. Integration test với PostgreSQL thật

Dùng Testcontainers để xác minh constraint, transaction và isolation trên database tương tự môi trường chạy.

Các điều kiện:

- Mỗi test bắt đầu với database sạch hoặc transaction fixture được cô lập.
- Chạy migration thực tế trước khi test.
- Kiểm tra primary key/unique constraint.
- Kiểm tra instance, operation và outbox được commit cùng nhau.
- Giả lập lỗi insert outbox để xác nhận transaction rollback.
- Kiểm tra request thứ hai đọc đúng record do request đầu tạo.
- Kiểm tra không có transaction bị giữ mở trong provider call.
- Xác minh row count và state sau khi test hoàn tất.

Ví dụ Testcontainers:

~~~java
@Testcontainers
@SpringBootTest
class ProvisionPersistenceIntegrationTest {

    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @Test
    void duplicateInstanceInsertCreatesOnlyOneRow() {
        // Arrange: configure application datasource with container.
        // Act: submit two insertIfAbsent calls for the same platform/instance.
        // Assert: exactly one call inserts; one instance row exists.
    }
}
~~~

Đây là skeleton. Trong dự án, dùng DynamicPropertySource hoặc service connection phù hợp với phiên bản Spring Boot để cấu hình datasource từ container. Test cần chạy thật với hai connection/transaction riêng để mô phỏng cạnh tranh; không chỉ gọi repository tuần tự trong cùng transaction.

## 17. Concurrency test cho cùng request

Bài kiểm thử cốt lõi gửi nhiều request đồng thời với cùng instance ID và fingerprint.

Kịch bản:

- Tạo 30 hoặc 50 request worker.
- Dùng CountDownLatch để đồng bộ thời điểm bắt đầu.
- Mỗi request dùng cùng platform_id, instance_id, tenant, service, plan và parameters.
- Chạy qua application service hoặc HTTP endpoint.
- Chờ tất cả kết quả.
- Truy vấn database và provider fake để đếm side effect.

Kết quả bắt buộc:

| Đối tượng | Số lượng mong đợi |
|---|---:|
| Instance record | 1 |
| Provision operation đang đại diện request | 1 |
| Outbox event ProvisionRequested | 1 |
| Provider create effect | 1 |
| Provider resource | 1 |
| Request được chấp nhận/replay | Tất cả cùng quy về operation đó |

Không yêu cầu mọi HTTP response phải giống byte-for-byte nếu request đầu và request retry đi qua hai state khác nhau. Yêu cầu là response đều đúng contract và không sinh operation/resource thứ hai.

Ví dụ test skeleton:

~~~java
@Test
void concurrentIdenticalRequestsCreateOneOperation() throws Exception {
    int callers = 30;
    var ready = new CountDownLatch(callers);
    var start = new CountDownLatch(1);
    var executor = Executors.newFixedThreadPool(callers);

    try {
        var futures = IntStream.range(0, callers)
                .mapToObj(index -> executor.submit(() -> {
                    ready.countDown();
                    start.await();
                    return provisionService.accept(command())
                            .block(Duration.ofSeconds(10));
                }))
                .toList();

        ready.await();
        start.countDown();

        var decisions = new ArrayList<ProvisionDecision>();
        for (var future : futures) {
            decisions.add(future.get(10, TimeUnit.SECONDS));
        }

        assertThat(decisions).hasSize(callers);
        assertThat(instanceRepository.count()).isEqualTo(1);
        assertThat(operationRepository.provisionCount()).isEqualTo(1);
        assertThat(outboxRepository.provisionEventCount()).isEqualTo(1);
    } finally {
        executor.shutdownNow();
    }
}
~~~

Với API reactive, import java.time.Duration và block với timeout ở test thread để Future nhận kết quả ProvisionDecision thực tế. Chỉ dùng block trong test harness; tuyệt đối không dùng block trong production reactive request path. Dùng database container và provider fake thread-safe để phép thử phản ánh concurrency thật.

## 18. Concurrency test cho request xung đột

Tiếp theo, gửi hai nhóm request cùng instance ID nhưng khác plan hoặc parameters:

- Nhóm A yêu cầu plan-standard.
- Nhóm B yêu cầu plan-small.
- Cả hai bắt đầu đồng thời.
- Một request thắng quyền tạo instance; request còn lại phải phát hiện fingerprint khác.

Kết quả:

- Chỉ một instance record tồn tại.
- Chỉ một request được phép tạo operation.
- Request còn lại nhận conflict theo contract.
- Provider chỉ nhận một create call với plan của request thắng.
- Không có lần ghi đè plan âm thầm.
- Kết quả cuối cùng không phụ thuộc request nào thắng trước.

Không hardcode rằng plan-standard luôn thắng. Test phải chấp nhận một trong hai request thắng, nhưng yêu cầu state trong database, operation và provider spec phải nhất quán với request thắng đó.

## 19. Kiểm thử worker giao message lặp

Giả lập queue giao cùng event hai hoặc nhiều lần:

1. Worker A claim operation.
2. Worker A gọi provider fake.
3. Queue giao lại event.
4. Worker B thử claim khi lease A còn hiệu lực.
5. Worker B phải không claim được.
6. Khi lease hết hạn, worker mới claim với fencing token mới.
7. Worker mới lookup provider trước khi create lại.
8. Provider fake chỉ có một resource cho key ổn định.

Kiểm tra:

- Provider create count là một khi provider idempotency được hỗ trợ.
- Provider lookup count tăng khi reconciliation.
- Operation không có hai owner hợp lệ cùng lúc.
- Worker cũ không ghi được sau khi fencing token thay đổi.
- State cuối cùng là READY/SUCCEEDED nếu resource xác minh thành công.

## 20. Fault injection: provider tạo xong nhưng response bị mất

Đây là test quan trọng nhất để phân biệt idempotency ở database với idempotency của side effect bên ngoài.

Provider fake cần hỗ trợ kịch bản:

~~~text
create(key=K):
  if K chưa có:
      tạo resource R
      lưu K -> R
      ném TimeoutException sau khi lưu
  nếu K đã có:
      trả resource R hiện có
~~~

Bài test:

1. Worker gửi create với key K.
2. Fake provider tạo resource R nhưng ném timeout.
3. Broker đánh dấu operation RECONCILIATION_REQUIRED hoặc trạng thái outcome uncertain.
4. Worker retry/recovery.
5. Worker lookup bằng K.
6. Fake provider trả R.
7. Broker xác minh ownership và configuration.
8. Broker lưu provider_resource_id=R và đánh dấu operation SUCCEEDED.
9. Không có resource R2.

Nếu provider không hỗ trợ idempotency token, fake provider cần mô phỏng lookup theo ownership marker. Nếu không có token, marker hoặc API tra cứu đáng tin cậy, ghi nhận giới hạn và yêu cầu manual reconciliation; không giả định broker có thể bảo đảm exactly-once.

## 21. Kiểm thử lease hết hạn và fencing

Dùng hai worker giả lập:

| Thời điểm | Worker A | Worker B |
|---|---|---|
| T1 | Claim token 10 | Chưa claim |
| T2 | Bắt đầu provider call, bị pause | Chưa claim |
| T3 | Lease A hết hạn | Claim token 11 |
| T4 | Tiếp tục chạy | Lookup/reconcile provider |
| T5 | Thử ghi bằng token 10 | Ghi kết quả bằng token 11 |
| Kết quả | Update 0 row | Update thành công |

Test cần chứng minh worker A không thể ghi đè kết quả của B. Fencing token phải tăng đơn điệu trong phạm vi operation và được kiểm tra trong câu UPDATE.

## 22. Kiểm thử HTTP contract qua SCOSB

Ngoài test application service, chạy test qua endpoint OSB để xác minh adapter mapping.

Các trường hợp:

| ID | Request | Kết quả mong đợi |
|---|---|---|
| HTTP-001 | PUT lần đầu, provider async, accepts_incomplete=true | 202 và operation ID |
| HTTP-002 | PUT lặp khi operation đang chạy | Cùng operation ID |
| HTTP-003 | PUT lặp sau READY | Kết quả idempotent theo OSB contract |
| HTTP-004 | PUT cùng instance ID nhưng plan khác | 409 hoặc conflict response đúng version |
| HTTP-005 | Thiếu/không hỗ trợ API version | Error response theo contract |
| HTTP-006 | Tenant không sở hữu instance | Từ chối và không lộ dữ liệu |
| HTTP-007 | Provider timeout chưa rõ kết quả | Operation được giữ để reconciliation |
| HTTP-008 | Request parameters không hợp lệ | Validation error, không gọi provider |

Dùng WebTestClient hoặc công cụ HTTP integration tương ứng. Xác minh cả status, body, operation ID, database row và provider call count.

## 23. Kiểm tra observability

Tính lặp an toàn phải có thể quan sát khi chạy production.

Metric gợi ý:

| Metric | Ý nghĩa |
|---|---|
| broker_provision_requests_total | Tổng request provision |
| broker_provision_replays_total | Số request được nhận diện là retry |
| broker_provision_conflicts_total | Request cùng instance ID nhưng fingerprint khác |
| broker_provider_create_total | Số lần gọi create provider |
| broker_provider_already_exists_total | Provider báo resource tồn tại |
| broker_reconciliation_total | Số lần reconciliation |
| broker_operation_lease_expired_total | Lease operation hết hạn |
| broker_operation_duration_seconds | Thời gian operation |
| broker_outbox_backlog | Event chưa publish |
| broker_orphan_resource_total | Resource cần đối chiếu |

Metric label nên có giá trị giới hạn như service ID, operation type và provider type. Không dùng instance ID, tenant ID, request fingerprint hoặc secret làm label vì cardinality và rò rỉ dữ liệu.

Log có thể ghi:

~~~text
event=provision_replayed
platform_id=cf-prod
instance_id=instance-orders-100
operation_id=provision-op-100
fingerprint_version=1
decision=IN_PROGRESS
correlation_id=trace-abc
~~~

Không log raw parameters, password, provider token hoặc toàn bộ request body. Với request conflict, ghi error code và correlation ID đủ để điều tra.

## 24. Kịch bản chạy thử end-to-end

Sau khi hoàn thiện code, chạy theo trình tự:

1. Đăng ký broker test trên platform hoặc gọi trực tiếp OSB endpoint trong môi trường tích hợp.
2. Lấy catalog và xác nhận service/plan.
3. Gửi một provision request hợp lệ với instance-orders-100.
4. Gửi lại cùng request đồng thời nhiều lần.
5. Xác minh mọi request quy về cùng operation/instance.
6. Poll last_operation tới khi operation kết thúc.
7. Gửi lại request sau khi instance READY.
8. Gửi request cùng instance ID nhưng plan khác.
9. Xác minh conflict và không có provider side effect.
10. Chạy fault injection provider create-success-response-lost.
11. Restart worker trong khi operation đang chạy.
12. Xác minh reconciliation hoàn tất mà không tạo resource thứ hai.
13. Chạy deprovision nếu môi trường cho phép.
14. Kiểm tra provider resource đã được xử lý đúng và database state nhất quán.

Ví dụ gọi endpoint bằng curl:

~~~bash
curl -i -X PUT \
  "https://broker.example.test/v2/service_instances/instance-orders-100?accepts_incomplete=true" \
  -H "Content-Type: application/json" \
  -H "X-Broker-API-Version: 2.17" \
  -H "Authorization: Bearer $BROKER_TOKEN" \
  --data @provision-request.json
~~~

Trong môi trường thực tế, token phải được lấy từ secret store và không được đưa vào shell history hoặc log chia sẻ. Gửi request lặp bằng cùng payload; với test cạnh tranh, dùng script test hoặc test harness đồng bộ thay vì chạy thủ công tuần tự.

## 25. Definition of Done

Capstone chỉ được xem là hoàn thành khi có bằng chứng cho các điều kiện sau.

### Tính đúng đắn dữ liệu

- [ ] Unique constraint bảo vệ instance key.
- [ ] Cùng request fingerprint được nhận diện là replay.
- [ ] Request cùng instance ID nhưng khác fingerprint bị conflict.
- [ ] Instance, operation và outbox commit nguyên tử.
- [ ] Operation có provider idempotency key ổn định.
- [ ] Worker claim dùng lease và fencing/version.
- [ ] Resource provider có ownership marker hoặc cơ chế lookup tương đương.
- [ ] Outcome uncertain đi qua reconciliation trước retry.

### Kiểm thử cạnh tranh

- [ ] 30 hoặc 50 request giống nhau đồng thời chỉ tạo một instance.
- [ ] Chỉ có một provision operation và một outbox event.
- [ ] Provider create chỉ tạo một resource.
- [ ] Request khác plan/parameters không ghi đè request thắng.
- [ ] Queue duplicate không tạo side effect lần hai.
- [ ] Worker cũ không ghi đè kết quả của worker mới.
- [ ] Provider tạo resource nhưng response mất được recovery an toàn.

### OSB contract và vận hành

- [ ] HTTP response đúng OSB API version.
- [ ] Request retry đang chạy nhận operation hiện hành.
- [ ] Request conflict không làm lộ tenant hoặc provider metadata.
- [ ] last_operation phản ánh đúng operation state.
- [ ] Metric phân biệt replay, conflict, provider duplicate và reconciliation.
- [ ] Log không chứa secret hoặc raw sensitive parameters.
- [ ] Có runbook xử lý AlreadyExists và manual reconciliation.

## 26. Các lỗi cần tránh

**Chỉ dùng synchronized hoặc lock trong JVM.** Broker có nhiều replica; lock trong một process không bảo vệ request tới replica khác. Dùng unique constraint/transaction ở database và coordination phù hợp.

**SELECT trước rồi INSERT.** Hai request đồng thời có thể cùng thấy chưa có row. Database phải enforce uniqueness.

**Tạo operation mới cho mỗi HTTP retry.** Request ID khác không có nghĩa nghiệp vụ khác. Replay cần trả lại operation hiện hành.

**Fingerprint toàn bộ JSON thô.** Thứ tự key, timestamp hoặc trace ID có thể làm cùng request bị coi là khác. Canonicalize field nghiệp vụ.

**Tạo provider key mới ở mỗi attempt.** Provider sẽ coi retry là create mới. Key phải ổn định trong operation.

**Giữ transaction mở khi gọi provider.** Điều này giữ lock và connection quá lâu, đồng thời không tạo được transaction ACID xuyên database/provider.

**Coi AlreadyExists là thành công ngay.** Resource có thể thuộc tenant khác. Phải xác minh ownership và cấu hình.

**Coi timeout là thất bại chắc chắn.** Provider có thể đã tạo resource. Chuyển sang reconciliation khi kết quả chưa rõ.

**Chỉ test tuần tự.** Race condition chỉ lộ ra khi request thực sự cạnh tranh qua nhiều transaction/connection.

**Chỉ mock repository.** Mock không kiểm tra unique constraint, isolation, deadlock hoặc transaction rollback. Cần integration test với database thật.

**Bỏ qua worker lease và fencing.** Queue delivery at-least-once có thể khiến nhiều worker cùng xử lý một operation.

## 27. Lộ trình thực hiện đề xuất

Chia capstone thành các mốc nhỏ để mỗi phần có thể review:

| Mốc | Công việc | Bằng chứng |
|---|---|---|
| 1. Baseline | Tái hiện race bằng hai request đồng thời | Test thất bại trước khi sửa |
| 2. Data model | Thêm unique constraint và fingerprint | Migration và repository test |
| 3. Atomic acceptance | Ghi instance, operation, outbox trong transaction | Integration test |
| 4. Replay decision | Phân biệt replay và conflict | Unit/HTTP contract test |
| 5. Worker safety | Claim, lease, heartbeat, fencing | Worker concurrency test |
| 6. Provider safety | Stable key, ownership marker, lookup | Provider adapter test |
| 7. Recovery | Timeout sau side effect và reconciliation | Fault injection test |
| 8. Verification | Chạy load/concurrency test và review metric | Test report, Definition of Done |

Ở mốc 1, hãy giữ lại test tái hiện lỗi làm regression test. Không xóa test đỏ cũ sau khi code mới chạy xanh; test đó là bằng chứng nguyên nhân đã được xử lý.

## 28. Hồ sơ bàn giao

Khi hoàn thành capstone, chuẩn bị các artifact để reviewer có thể đánh giá:

- Sơ đồ request path và worker path.
- Mô tả instance key, fingerprint và provider idempotency key.
- Database migration và constraint.
- Quy tắc replay/conflict theo operation state.
- Provider adapter contract và ownership marker.
- Test report cho request giống nhau và request xung đột.
- Test report provider timeout/lost response.
- Test report worker lease/fencing.
- Metric và log mẫu đã redacted.
- Runbook reconciliation và Definition of Done.

Không đưa access token, password, secret response hoặc dữ liệu tenant thật vào hồ sơ. Dùng fixture và identifier giả lập.

## Kết luận

Capstone yêu cầu xây dựng một luồng provision có thể chịu được request lặp, request cạnh tranh, queue delivery trùng và provider timeout. Giải pháp cần phối hợp instance key, request fingerprint, unique constraint, transaction/outbox, operation state, worker lease/fencing và provider idempotency/reconciliation. Kiểm thử phải chạy trên nhiều transaction/connection thật để chứng minh các request giống nhau cùng quy về một operation, request xung đột bị từ chối và provider chỉ có một resource được xác minh. Với Spring Cloud Service Broker, đây là nền tảng để duy trì hợp đồng OSB API và trạng thái service instance chính xác ngay cả khi platform retry hoặc hạ tầng bên ngoài không trả lời đúng lúc.

## Tài liệu tham khảo

- [Open Service Broker API Specification](https://github.com/openservicebrokerapi/servicebroker/blob/master/spec.md) — provision, asynchronous operation và service instance lifecycle.
- [Spring Cloud Open Service Broker Reference Documentation](https://docs.spring.io/spring-cloud-open-service-broker/docs/current/reference/) — service abstraction và request/response model.
- [PostgreSQL — INSERT](https://www.postgresql.org/docs/current/sql-insert.html) — ON CONFLICT và xử lý uniqueness.
- [PostgreSQL — Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html) — row-level locks và concurrency control.
- [PostgreSQL — Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html) — isolation và hành vi transaction đồng thời.
- [Transactional Outbox pattern](https://microservices.io/patterns/data/transactional-outbox.html) — ghi database state và event trong cùng transaction.
- [AWS — Making requests idempotent](https://docs.aws.amazon.com/ec2/latest/devguide/ec2-api-idempotency.html) — idempotency token trong API provider.
- [Kubernetes — Leases](https://kubernetes.io/docs/concepts/architecture/leases/) — lease coordination.
- [Testcontainers for Java](https://java.testcontainers.org/) — integration test với PostgreSQL và dependency thật.
- [Project Reactor Reference Guide](https://projectreactor.io/docs/core/release/reference/) — composition, retry và xử lý lỗi reactive.

