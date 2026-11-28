# Mô phỏng lỗi giữa chừng, khởi động lại và đối soát tài nguyên

Service broker thường thực hiện một nghiệp vụ qua nhiều hệ thống: nhận request OSB, ghi operation vào database, đưa job vào queue, gọi provider, lưu resource ID, cấp credential và cập nhật trạng thái. Không có transaction database nào bao trùm đồng thời database của broker, message broker và API của cloud provider. Vì vậy, process có thể dừng sau khi provider đã tạo resource nhưng trước khi broker lưu kết quả. Khi worker khởi động lại, broker phải biết nên tiếp tục, truy vấn kết quả cũ, bù trừ hay yêu cầu đối soát.

Bài thực hành capstone này xây dựng một kịch bản có thể tái hiện trong **SPRING_CLOUD_SERVICE_BROKER**: provision một service instance, cố ý làm process chết ở các điểm giữa chừng, khởi động worker lại, xử lý retry và đối chiếu trạng thái trong broker với tài nguyên thực tế ở provider. Cùng một cách tiếp cận được áp dụng cho update, bind, unbind và deprovision. Mục tiêu là bảo đảm mỗi request có một kết quả có thể truy vết, không tạo resource trùng, không mất operation đã chấp nhận và không xóa nhầm tài nguyên.

## 1. Kết quả cần đạt của bài thực hành

Sau khi hoàn thành, hệ thống cần đáp ứng các điều kiện:

- Request OSB đã được chấp nhận phải có instance/operation record bền vững trước khi broker trả response asynchronous.
- Job được phát lại sau crash không tạo side effect trùng nếu provider hỗ trợ idempotency; nếu không, broker phải có cách tìm resource đã tạo hoặc chuyển sang reconciliation.
- Worker cũ không được ghi state sau khi lease đã hết hạn và worker khác đã tiếp quản.
- Provider resource ID, operation state và instance lifecycle được lưu nhất quán.
- last_operation phản ánh trạng thái thực tế và giữ operation token ổn định qua retry.
- Reconciliation phát hiện resource bị thiếu, resource mồ côi, duplicate và state drift.
- Mọi hành động repair hoặc cleanup đều kiểm tra platform, tenant, provider account và ownership.
- Fault injection chứng minh hệ thống phục hồi qua restart, duplicate message và response timeout.

Không đặt mục tiêu làm cho mọi lỗi tự động retry. Có những tình huống provider đã thực hiện side effect nhưng broker không biết kết quả. Trong trường hợp đó, retry mù quáng có thể tạo database thứ hai hoặc xóa nhầm tài nguyên. Phục hồi đúng đôi khi là dừng operation ở trạng thái RECONCILIATION_REQUIRED cho đến khi xác minh được provider state.

## 2. Kịch bản lab và các thành phần

Giả sử broker cung cấp service PostgreSQL. Platform gửi yêu cầu provision instance orders-db-lab theo plan standard. Broker chạy trên Spring Boot và Spring Cloud Open Service Broker, dùng database quan hệ làm state store, queue để phân phối job và provider adapter để gọi API tạo database.

Sơ đồ thành phần:

~~~mermaid
flowchart LR
    P["Platform / OSB client"] --> API["Broker HTTP API"]
    API --> DB[("Broker state DB")]
    API --> OB["Transactional outbox"]
    OB --> Q[("Job queue")]
    Q --> W["Provision worker"]
    W --> PA["Provider adapter"]
    PA --> CP["Cloud provider"]
    CP --> R["Database resource"]
    W --> DB
    REC["Reconciliation job"] --> DB
    REC --> PA
    P -->|last_operation| API
~~~

Các thành phần:

| Thành phần | Trách nhiệm |
|---|---|
| OSB controller/handler | Deserialize request, kiểm tra contract và trả response |
| Domain service | Xác thực quyền, idempotency, quota và lifecycle |
| Instance repository | Lưu service instance và provider mapping |
| Operation repository | Lưu operation state, token và tiến độ |
| Outbox | Ghi event cần publish trong cùng transaction với state |
| Queue/worker | Thực hiện operation bất đồng bộ |
| Provider adapter | Gọi API create/inspect/delete và chuẩn hóa lỗi |
| Reconciliation service | So sánh desired state với provider actual state |
| Fault injector | Cố ý tạo lỗi ở điểm xác định trong lab |
| Metrics/audit | Ghi nhận attempt, failure, repair và hành động cleanup |

Dùng provider fake hoặc sandbox có thể kiểm soát được. Không dùng tài khoản production để mô phỏng crash hoặc deprovision.

## 3. Mô hình dữ liệu tối thiểu

Tách service instance khỏi operation. Một instance có thể trải qua nhiều operation trong vòng đời; không dùng một cột status duy nhất để biểu diễn cả resource và công việc đang chạy.

### Service instance

~~~java
public record ServiceInstance(
    UUID id,
    String platformInstanceId,
    String externalInstanceId,
    UUID tenantId,
    String serviceId,
    String planId,
    String provider,
    String providerAccountRef,
    String providerResourceId,
    InstanceState state,
    long version,
    long ownershipEpoch
) {}
~~~

externalInstanceId là ID do platform gửi trong OSB path. providerResourceId là ID thật ở provider. Hai giá trị này có ý nghĩa khác nhau và không được thay thế cho nhau.

### Operation

~~~java
public record BrokerOperation(
    UUID id,
    UUID instanceId,
    String operationToken,
    OperationType type,
    OperationState state,
    String idempotencyKey,
    String providerRequestKey,
    int attempt,
    Instant createdAt,
    Instant updatedAt,
    Instant leaseUntil,
    long fencingToken,
    String failureCode
) {}
~~~

Operation cần giữ token ổn định để platform polling cùng một thao tác. attempt tăng theo lần worker xử lý; operationToken và providerRequestKey không thay đổi chỉ vì message được redeliver.

### Outbox event

~~~java
public record OutboxEvent(
    UUID id,
    String aggregateType,
    UUID aggregateId,
    String eventType,
    String payload,
    Instant createdAt,
    Instant publishedAt
) {}
~~~

Trong production, payload cần tối thiểu và không chứa secret. Event có thể được publish nhiều lần; consumer phải idempotent.

### Unique constraints quan trọng

- Unique theo (platform_instance_id, external_instance_id) cho service instance trong scope đã chọn.
- Unique theo (instance_id, operation_token) hoặc operation ID.
- Unique theo idempotency scope và request fingerprint.
- Unique theo provider resource mapping khi provider resource không được phép gắn với nhiều instance.
- Unique theo outbox event ID.

Các unique key phải phản ánh contract thực tế của broker. Đừng giả định external instance ID là duy nhất toàn cục nếu platform chỉ bảo đảm uniqueness trong một foundation hoặc broker registration.

## 4. State machine cho instance và operation

Instance state mô tả tài nguyên; operation state mô tả tiến trình một hành động.

~~~mermaid
stateDiagram-v2
    [*] --> PROVISIONING
    PROVISIONING --> ACTIVE
    PROVISIONING --> FAILED
    PROVISIONING --> RECONCILIATION_REQUIRED
    ACTIVE --> UPDATING
    UPDATING --> ACTIVE
    UPDATING --> RECONCILIATION_REQUIRED
    ACTIVE --> DEPROVISIONING
    DEPROVISIONING --> DEPROVISIONED
    DEPROVISIONING --> RECONCILIATION_REQUIRED
~~~

~~~mermaid
stateDiagram-v2
    [*] --> ACCEPTED
    ACCEPTED --> QUEUED
    QUEUED --> IN_PROGRESS
    IN_PROGRESS --> SUCCEEDED
    IN_PROGRESS --> RETRY_WAIT
    RETRY_WAIT --> QUEUED
    IN_PROGRESS --> FAILED
    IN_PROGRESS --> RECONCILIATION_REQUIRED
    RECONCILIATION_REQUIRED --> IN_PROGRESS
    RECONCILIATION_REQUIRED --> FAILED
~~~

Ví dụ:

| Instance state | Operation state | Ý nghĩa |
|---|---|---|
| PROVISIONING | QUEUED | Đã ghi nhận yêu cầu, đang chờ worker |
| PROVISIONING | IN_PROGRESS | Provider call đang diễn ra |
| ACTIVE | SUCCEEDED | Resource đã được tạo và mapping đã lưu |
| PROVISIONING | RECONCILIATION_REQUIRED | Chưa biết provider đã tạo resource hay chưa |
| DEPROVISIONING | IN_PROGRESS | Đang thu hồi resource |
| DEPROVISIONED | SUCCEEDED | Provider resource đã được xác nhận xóa |

Transition cần được kiểm soát bằng compare-and-set hoặc optimistic locking. Không cho phép một worker ghi ACTIVE nếu instance đã chuyển sang trạng thái khác bởi một operation mới hơn.

## 5. Luồng provision đúng thứ tự

Request bất đồng bộ nên được ghi nhận trong một database transaction trước khi trả response cho platform.

1. Xác thực platform principal và resolve tenant scope.
2. Kiểm tra service ID, plan ID, parameters, quota và entitlement; xác minh request cho phép xử lý asynchronous (accepts_incomplete) nếu thao tác cần chạy nền.
3. Tính request fingerprint từ các field nghiệp vụ đã chuẩn hóa.
4. Kiểm tra idempotency key hoặc instance identity đã tồn tại.
5. Tạo instance PROVISIONING.
6. Tạo operation ACCEPTED với token ổn định.
7. Tạo outbox event ProvisionRequested.
8. Commit transaction.
9. Trả response asynchronous theo OSB contract, kèm operation token khi cần; không chờ provider hoàn tất.
10. Outbox publisher chạy độc lập và đưa event đã commit vào queue.

Transaction ở bước 5-7 bảo đảm instance, operation và event được ghi cùng nhau. Nếu database commit thất bại, broker không được trả response thành công như thể job đã được lưu.

Nếu thao tác cần xử lý asynchronous nhưng platform không cho phép asynchronous completion, broker phải từ chối theo OSB API version/contract đang hỗ trợ. Không tạo operation nền rồi trả response thành công đồng bộ khi provider chưa hoàn tất.

Ví dụ pseudo-code:

~~~java
@Transactional
public ProvisionAccepted acceptProvision(
        AuthorizationContext context,
        ProvisionCommand command) {

    var fingerprint = fingerprint(command);

    var existing = idempotencyRepository
        .find(context.platformId(), command.instanceId());

    if (existing.isPresent()) {
        return verifySameRequest(existing.get(), fingerprint);
    }

    var instance = instanceRepository.insertProvisioning(
        context, command);

    var operation = operationRepository.insertAccepted(
        instance.id(), OperationType.PROVISION, fingerprint);

    outboxRepository.insert(
        OutboxEventFactory.provisionRequested(instance, operation));

    return new ProvisionAccepted(instance, operation);
}
~~~

Đây là ví dụ cấu trúc. Không thực hiện provider HTTP call bên trong transaction database; provider call có thể kéo dài, timeout hoặc tạo deadlock khi transaction giữ connection.

## 6. Idempotency ở ba lớp

Một hệ thống phục hồi sau crash cần phân biệt ba loại lặp:

| Lớp | Lặp xảy ra khi | Cách kiểm soát |
|---|---|---|
| HTTP/request idempotency | Platform retry PUT sau khi response bị mất | Cùng instance scope và request fingerprint trả cùng kết quả |
| Message/worker idempotency | Queue redeliver event hoặc worker restart | Operation ID, state check, lease và fencing |
| Provider side-effect idempotency | Provider create đã chạy nhưng broker không nhận response | Provider idempotency key hoặc lookup theo external reference/tag |

### Request fingerprint

Fingerprint chỉ bao gồm field ảnh hưởng tới kết quả nghiệp vụ: service ID, plan ID, parameters đã canonicalize, platform/tenant scope và các option liên quan. Không hash JSON thô nếu thứ tự key hoặc định dạng số có thể thay đổi mà semantics không đổi.

Nếu cùng instance ID được gửi lại với fingerprint giống nhau, trả operation/result đã có. Nếu fingerprint khác, xử lý theo OSB contract và policy conflict của broker. Không tạo operation mới cho request mâu thuẫn trên cùng instance.

### Provider request key

Tạo một provider request key ổn định từ internal instance ID và operation ID, lưu trước khi gọi provider. Nếu provider hỗ trợ idempotency header/key, dùng lại đúng key qua mọi retry.

Nếu provider không hỗ trợ idempotency, cần xác định cách lookup resource theo client token, tag hoặc deterministic external name. Không tự cho rằng tên resource duy nhất cũng bảo đảm create idempotent; phải có unique constraint hoặc provider-side conditional create.

## 7. Transactional outbox tránh mất job

Một lỗi phổ biến:

1. Broker ghi operation vào database.
2. Process chết trước khi publish message.
3. Platform đã nhận HTTP 202 nhưng không có worker nào biết job cần chạy.

Transactional outbox khắc phục khoảng trống này. Instance, operation và outbox event được commit cùng transaction. Publisher đọc các event chưa publish và gửi đến queue. Nếu process chết sau publish nhưng trước khi đánh dấu published, event có thể được gửi lại; worker phải xử lý idempotent.

Outbox publisher không cần đảm bảo exactly-once delivery. Hệ thống cần at-least-once delivery với idempotent consumer.

Ví dụ query claim event có thể dùng row lock/lease để nhiều publisher không lấy cùng event cùng lúc. Sau khi publish thành công, cập nhật published_at. Nếu publisher chết, lease hết hạn và process khác có thể lấy lại event.

## 8. Worker claim job với lease và fencing token

Worker cần claim operation bằng một cập nhật nguyên tử. Lease giúp worker khác tiếp quản khi process cũ chết; fencing token ngăn worker cũ tiếp tục ghi state sau khi lease hết hạn.

Ví dụ SQL khái niệm:

~~~sql
UPDATE broker_operation
SET state = 'IN_PROGRESS',
    lease_until = :lease_until,
    fencing_token = fencing_token + 1,
    attempt = attempt + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE id = :operation_id
  AND (
      state IN ('QUEUED', 'RETRY_WAIT')
      OR (state = 'IN_PROGRESS' AND lease_until < CURRENT_TIMESTAMP)
  )
  AND (lease_until IS NULL OR lease_until < CURRENT_TIMESTAMP);
~~~

Worker chỉ tiếp tục nếu update claim thành công và đọc được fencing token mới. Mỗi lần ghi kết quả phải kèm điều kiện fencing_token = :claimed_token và kiểm tra instance version/owner.

Nếu worker cũ quay lại sau pause dài, nó có token cũ nên update phải ảnh hưởng zero rows. Nó cần dừng và không được thực hiện thêm side effect. Fencing ở database không thể tự ngăn một HTTP call đã gửi tới provider; vì vậy provider idempotency và provider-side ownership checks vẫn quan trọng.

### Heartbeat

Worker đang xử lý operation dài phải gia hạn lease trước khi hết hạn. Heartbeat chỉ được gia hạn nếu token vẫn khớp. Nếu không gia hạn được, worker phải ngừng xử lý hoặc chuyển sang trạng thái an toàn; không tiếp tục với giả định nó vẫn sở hữu job.

## 9. Các điểm fault injection cần mô phỏng

Hãy thêm một FaultInjector chỉ bật trong profile test/lab. Nó có thể ném exception hoặc dừng process tại checkpoint. Không để endpoint public có thể yêu cầu production process tự kill.

~~~java
public enum FailurePoint {
    BEFORE_ACCEPT_COMMIT,
    AFTER_ACCEPT_COMMIT,
    AFTER_WORKER_CLAIM,
    BEFORE_PROVIDER_REQUEST,
    AFTER_PROVIDER_CREATED,
    BEFORE_LOCAL_RESOURCE_SAVE,
    AFTER_LOCAL_RESOURCE_SAVE,
    BEFORE_OPERATION_TERMINAL,
    AFTER_TERMINAL_COMMIT
}

public interface FaultInjector {
    void hit(FailurePoint point);
}
~~~

Một implementation lab có thể đọc danh sách failure point từ test configuration và chỉ kích hoạt một lần. Trong integration test, có thể dùng latch/barrier hoặc test hook để dừng process ở checkpoint, sau đó restart worker container/process.

| Điểm lỗi | Tình trạng khi process chết | Cách phục hồi cần chứng minh |
|---|---|---|
| Trước commit accept | Không có instance/operation/outbox | Platform retry request |
| Sau commit, trước publish | Có outbox chưa publish | Publisher gửi lại event |
| Sau worker claim | Operation IN_PROGRESS có lease | Lease hết hạn, worker khác claim |
| Trước provider request | Chưa có side effect | Retry an toàn |
| Sau provider tạo resource, trước response | Provider có resource, broker chưa biết kết quả | Lookup/idempotency trước khi retry |
| Sau response provider, trước local save | Provider có resource, mapping chưa lưu | Reconcile theo provider request key/tag |
| Sau local resource save, trước terminal commit | Mapping đã lưu, operation chưa terminal | Worker đọc mapping và hoàn tất state |
| Sau terminal commit, trước HTTP response/poll | Operation đã hoàn tất | Retry/poll trả cùng kết quả |
| Trong deprovision sau provider delete | Resource đã mất, local state còn DEPROVISIONING | Inspect provider, xác nhận absence rồi hoàn tất |

Không phải mọi điểm lỗi đều cần kill process. Có thể dùng test hook ném exception để xác minh rollback/retry logic, sau đó bổ sung process termination test cho các ranh giới persistence và network.

## 10. Thực hiện lab với provider fake

Provider fake cần lưu resource riêng để state không biến mất khi broker worker restart. Có thể dùng database hoặc một HTTP stub có persistence.

Một resource fake:

~~~java
public record FakeProviderResource(
    String resourceId,
    String clientToken,
    String serviceId,
    String planId,
    String state
) {}
~~~

Endpoint fake có thể hỗ trợ:

- POST /resources: tạo resource, trả cùng resource nếu client token đã tồn tại.
- GET /resources/by-client-token/{token}: tìm kết quả create trước đó.
- GET /resources/{id}: đọc trạng thái.
- DELETE /resources/{id}: xóa resource; nếu đã xóa thì trả kết quả absence nhất quán.
- Fault mode: timeout trước side effect, timeout sau side effect, 429, 5xx hoặc response malformed.

Provider fake phải phân biệt rõ hai kịch bản:

1. Request timeout trước khi provider tạo resource.
2. Provider tạo resource thành công nhưng response bị mất.

Hai kịch bản đều nhìn như timeout ở broker, nhưng cách retry khác nhau. Kịch bản thứ hai là unknown outcome và phải lookup trước khi tạo lại.

## 11. Phục hồi khi provider tạo resource nhưng broker chưa lưu ID

Đây là failure window quan trọng nhất.

Giả sử worker gửi create với provider request key prov-req-abc. Provider tạo database db-7788, nhưng response bị mất hoặc process chết trước khi ghi provider_resource_id.

Khi worker mới tiếp quản:

1. Đọc operation và provider request key đã lưu.
2. Gọi provider lookup theo client token hoặc tag tương ứng.
3. Nếu tìm thấy đúng một resource thuộc scope, xác minh service/plan/region/owner.
4. Attach resource ID vào instance trong transaction.
5. Chuyển instance sang ACTIVE và operation sang SUCCEEDED trong cùng transaction.
6. Nếu không tìm thấy, kiểm tra provider consistency window và retry theo policy.
7. Nếu tìm thấy nhiều resource, không tự chọn/xóa tùy tiện; chuyển reconciliation và xử lý duplicate có audit.

Pseudo-code:

~~~java
public Mono<ProviderResource> ensureProvisioned(
        ProvisionOperation operation) {

    return provider.findByClientToken(operation.providerRequestKey())
        .switchIfEmpty(
            provider.create(
                operation.specification(),
                operation.providerRequestKey()
            )
        );
}
~~~

Ví dụ này chỉ an toàn nếu findByClientToken và create có semantics phù hợp. Nếu provider eventual consistency, lookup ngay sau create có thể chưa thấy resource. Dùng bounded retry/backoff cho lookup và idempotency key phía provider. Nếu provider không có lookup hay idempotency, không thể bảo đảm exactly-once chỉ bằng code broker; cần deterministic resource identity, external tag hoặc quy trình reconciliation/manual approval.

## 12. Hoàn tất mapping và operation trong một transaction

Sau khi provider resource được xác định, broker phải lưu mapping và trạng thái operation nhất quán.

~~~java
@Transactional
public void completeProvision(
        UUID instanceId,
        UUID operationId,
        long fencingToken,
        ProviderResource resource) {

    var instance = instanceRepository
        .lockById(instanceId)
        .orElseThrow();

    var operation = operationRepository
        .lockById(operationId)
        .orElseThrow();

    assertCurrentOwner(operation, fencingToken);
    assertProvisionOperation(operation, instance);

    instanceRepository.attachProviderResource(
        instanceId, resource.id(), InstanceState.ACTIVE);

    operationRepository.markSucceeded(operationId);
    outboxRepository.insert(
        OutboxEventFactory.provisionCompleted(instanceId, operationId));
}
~~~

Trong triển khai thực tế, transaction phải kiểm tra update count, version và ownership epoch. Nếu update instance thành công nhưng operation update thất bại, transaction cần rollback cả hai. Không phát event completion trước khi commit.

Nếu transaction commit response bị mất ở client, worker có thể đọc lại operation. Nếu operation đã SUCCEEDED và provider mapping tồn tại, không chạy provider create lần nữa.

## 13. Khởi động lại worker và xử lý operation bị bỏ dở

Khi worker restart, recovery scheduler cần tìm:

- Operation IN_PROGRESS có lease hết hạn.
- Operation QUEUED chưa được xử lý.
- RETRY_WAIT đã đến thời điểm chạy.
- Outbox event chưa publish.
- Operation có provider request key nhưng chưa có provider resource mapping.
- Operation ở RECONCILIATION_REQUIRED cần kiểm tra lại.
- Instance state không khớp operation terminal.

Quy trình recovery:

1. Đọc batch operation đủ nhỏ.
2. Claim bằng lease và fencing token mới.
3. Kiểm tra operation state và instance version.
4. Nếu mapping provider đã tồn tại, inspect resource trước khi gọi create.
5. Nếu chưa có mapping nhưng provider key đã tồn tại, lookup theo key.
6. Nếu provider chưa có resource và operation còn retryable, thực hiện lại bằng cùng provider key.
7. Nếu outcome không xác định, chuyển reconciliation.
8. Ghi transition có điều kiện và audit attempt.
9. Tiếp tục batch tiếp theo, có giới hạn concurrency.

Không reset tất cả IN_PROGRESS thành QUEUED khi khởi động. Worker khác có thể vẫn đang xử lý; chỉ reclaim operation có lease hết hạn và token cũ không còn quyền ghi.

## 14. Reconciliation: so sánh desired state với actual state

Reconciliation là quá trình so sánh trạng thái broker mong muốn với tài nguyên thực tế ở provider và sửa sai có kiểm soát. Nó không đơn giản là xóa mọi resource không tìm thấy trong database.

Desired state lấy từ instance/operation store. Actual state lấy từ provider API, tags/labels, account inventory và resource metadata.

Mỗi resource provider nên mang metadata đủ để tìm lại:

- Broker identity.
- Platform registration/scope reference ở dạng opaque.
- Internal instance ID hoặc hash.
- Operation ID/client token.
- Service ID/plan ID nếu provider tag policy cho phép.
- Environment/region.
- Ownership epoch hoặc generation.
- Created/managed-by marker.

Không đưa credential, raw tenant data hoặc thông tin cá nhân vào provider tags.

### Phân loại kết quả đối chiếu

| Broker state | Provider actual | Cách xử lý |
|---|---|---|
| Có instance + resource ID, provider resource tồn tại đúng | Match | Không thay đổi; cập nhật observed timestamp |
| Instance PROVISIONING, chưa có mapping, provider resource tìm thấy theo request key | Resource created, mapping missing | Attach mapping và hoàn tất operation sau khi xác minh |
| Instance ACTIVE, provider resource không tồn tại | Missing resource | Đánh dấu drift; xác minh deletion/manual action trước khi đổi state |
| Không có instance, provider resource có broker tag | Orphan candidate | Quarantine, tìm audit/owner; không auto-delete ngay |
| Instance trỏ resource thuộc account/tenant khác | Ownership mismatch | Dừng, cảnh báo security; không attach |
| Một instance map tới nhiều provider resources | Duplicate | Chọn canonical bằng idempotency/audit; quarantine phần dư |
| Operation terminal nhưng resource vẫn ở state cũ | State inconsistency | Recompute từ provider và transition có điều kiện |
| Provider API không truy cập được | Actual state unknown | Giữ trạng thái hiện tại, retry reconciliation; không coi absence |

### Không xóa resource mồ côi tự động

Resource không có record local có thể thuộc một lần migration chưa hoàn tất, một broker khác, hoặc resource được tạo thủ công. Trước cleanup cần kiểm tra broker marker, provider account, creation timestamp, owner, legal hold, dependency và retention. Dùng quarantine/tag để chặn cấp phát mới nếu phù hợp; cleanup destructive cần approval hoặc policy rõ ràng.

## 15. Reconciliation algorithm theo từng bước

Một reconciliation run có thể triển khai như sau:

1. Chọn platform/provider account/region scope đã được xác thực.
2. Tạo reconciliation run ID và lưu checkpoint.
3. Lấy batch instance/operation trong scope từ state store.
4. Lấy provider inventory theo pagination và filter phù hợp.
5. Chuẩn hóa provider resource thành map theo client token/resource ID.
6. Đối chiếu mapping và ownership.
7. Phân loại match, missing, orphan, duplicate, mismatch và unknown.
8. Tạo repair action cho trường hợp an toàn.
9. Đưa trường hợp mơ hồ vào manual review.
10. Ghi kết quả, metric, audit và checkpoint.
11. Lặp lại cho đến hết scope; chạy lại phải idempotent.

Pseudo-code:

~~~java
public Mono<ReconciliationResult> reconcile(
        ReconciliationScope scope) {

    return instanceRepository.findBatch(scope)
        .collectList()
        .flatMap(instances ->
            providerInventory.list(scope.providerAccount(), scope.region())
                .collectList()
                .flatMap(resources ->
                    reconciliationPlanner.plan(instances, resources)
                )
        )
        .flatMap(reconciliationExecutor::applySafeRepairs);
}
~~~

Đây là ví dụ khái niệm. Với inventory lớn, không load toàn bộ resource vào memory; dùng pagination, streaming hoặc batch theo tag/time window. Planner nên tạo decision trước, executor chỉ áp dụng action được phân loại safe. Mỗi action cần idempotency key và audit record.

## 16. Repair an toàn cho từng loại drift

### Mapping bị thiếu nhưng resource đã tồn tại

Nếu provider resource có client token đúng, service/plan và account/region khớp, có thể attach provider ID. Transaction phải kiểm tra instance vẫn đang PROVISIONING và operation vẫn là operation hiện hành. Nếu instance đã bị deprovision hoặc ownership epoch thay đổi, không attach.

### Instance ACTIVE nhưng provider resource biến mất

Không lập tức chuyển instance sang FAILED nếu provider có eventual consistency hoặc API inventory đang stale. Thực hiện inspect theo resource ID, retry bounded và kiểm tra audit/provider deletion event. Nếu resource thực sự bị xóa ngoài broker, ghi drift và xử lý theo policy: báo platform, đánh dấu failed/lost hoặc khởi tạo recovery workflow. Không âm thầm provision resource thay thế với cùng instance ID nếu dữ liệu đã mất.

### Orphan provider resource

Xác minh marker và account trước. Có thể gắn tag quarantine hoặc tạo ticket cleanup. Nếu policy cho phép tự cleanup, yêu cầu tuổi resource vượt retention, không có dependency, không có legal hold và có bằng chứng resource do broker quản lý.

### Duplicate provider resource

Xác định resource canonical bằng client token, created time, operation audit và metadata. Nếu có hai resource do retry lỗi, cần xác minh consumer có đang kết nối resource nào. Không xóa resource chỉ dựa trên tên gần giống. Chuyển duplicate sang quarantine, kiểm tra data và dependencies rồi mới cleanup.

## 17. Xử lý deprovision khi process chết giữa chừng

Deprovision cũng có failure window tương tự:

- Broker ghi DEPROVISIONING.
- Worker gửi delete đến provider.
- Provider xóa resource.
- Worker chết trước khi ghi DEPROVISIONED.

Khi restart, broker thấy local state vẫn DEPROVISIONING. Worker mới inspect provider resource:

- Nếu resource còn tồn tại và thuộc đúng instance, tiếp tục delete với idempotency key ổn định.
- Nếu provider trả not-found và scope/identity được xác minh, coi desired state deprovision đã đạt và hoàn tất operation.
- Nếu provider API không truy cập được, giữ operation chờ retry/reconciliation.
- Nếu resource ID thuộc owner khác, dừng và cảnh báo.

Not-found chỉ được xem là thành công khi đã gọi đúng provider account/region và đã xác minh resource identity. Sai account có thể trả not-found dù resource vẫn tồn tại ở account khác.

## 18. Áp dụng cho bind và unbind

Binding tạo credential hoặc quyền truy cập cho consumer. Broker cần lưu binding intent và operation trước khi tạo credential, tương tự provision.

Nếu worker chết sau khi provider tạo user/database role nhưng trước khi lưu binding record, recovery phải tìm credential/resource phụ theo binding ID hoặc client token. Không tạo user mới mỗi lần retry.

Khi unbind:

1. Đánh dấu binding UNBINDING.
2. Ghi operation và outbox.
3. Revoke credential/role tại provider.
4. Xác minh credential không còn hiệu lực.
5. Đánh dấu binding UNBOUND và operation terminal.

Nếu provider đã revoke nhưng broker chưa lưu state, retry revoke cần idempotent; provider trả not-found/credential-disabled có thể là trạng thái mong muốn sau khi xác minh đúng binding. Không xóa binding metadata trước khi lưu audit và kết quả thu hồi.

## 19. Backoff, retry budget và dead-letter queue

Retry phải có giới hạn để broker không khuếch đại outage.

Một policy mẫu:

~~~java
Duration retryDelay(int attempt) {
    long baseSeconds = 2L;
    long maxSeconds = 300L;
    long exponential = Math.min(
        maxSeconds,
        baseSeconds * (1L << Math.min(attempt, 8))
    );
    return Duration.ofSeconds(withJitter(exponential));
}
~~~

Đây là pseudocode. Trong triển khai thật, tránh overflow, chọn jitter phù hợp và cấu hình max attempts/total retry window. Retry 429 nên tôn trọng Retry-After nếu provider trả. Không retry lỗi validation hoặc authorization permanent một cách vô hạn.

| Lỗi | Hành động |
|---|---|
| Timeout trước khi biết provider outcome | Lookup/idempotency trước retry |
| 429/rate limit | Backoff, tôn trọng Retry-After |
| 5xx/transient network | Retry giới hạn |
| 400/validation | FAILED, không retry |
| 401/403 | Dừng hoặc pause provider scope, sửa credential/permission |
| Quota exhausted | Chờ capacity hoặc route theo policy |
| Unknown outcome | RECONCILIATION_REQUIRED |
| Max attempts reached | DLQ/manual review theo policy |

DLQ không phải nơi kết thúc trách nhiệm. Cần dashboard, owner, retry/replay procedure và retention. Khi replay, giữ operation ID và provider request key; không tạo request key mới.

## 20. Last operation và platform polling

Nếu provision được chấp nhận asynchronous, platform sẽ poll endpoint last operation. Response cần phản ánh operation hiện tại:

| Internal operation | OSB-facing state |
|---|---|
| ACCEPTED/QUEUED | In progress |
| IN_PROGRESS | In progress |
| RETRY_WAIT | In progress |
| RECONCILIATION_REQUIRED | In progress hoặc trạng thái xử lý được contract/version hỗ trợ; không báo succeeded |
| SUCCEEDED | Succeeded |
| FAILED | Failed |

Ánh xạ chính xác phải tuân theo OSB API version và framework response model. Không trả state nội bộ tùy ý nếu contract chỉ chấp nhận một tập giá trị. Error description cần đủ để platform/operator chẩn đoán nhưng không chứa secret hoặc stack trace.

Operation token cần ổn định qua retry và restart. Nếu platform gửi lại request provision do mất response ban đầu, broker phải tìm instance/operation đã tạo và trả cùng operation reference thay vì tạo operation mới.

## 21. Fault injection trong Spring test

Có thể inject lỗi tại các checkpoint bằng interface:

~~~java
@Component
@Profile("fault-lab")
public class ConfigurableFaultInjector implements FaultInjector {

    private final FaultPlan faultPlan;

    @Override
    public void hit(FailurePoint point) {
        if (faultPlan.consumeOnce(point)) {
            throw new SimulatedProcessFailure(point.name());
        }
    }
}
~~~

Test ví dụ khái niệm:

~~~java
@Test
void shouldRecoverWhenProviderCreatedResourceButLocalSaveFailed() {
    faultPlan.failOnce(FailurePoint.AFTER_PROVIDER_CREATED);

    assertThatThrownBy(() -> runProvisionWorker(operationId))
        .isInstanceOf(SimulatedProcessFailure.class);

    restartWorker();

    runRecoveryWorker();

    assertThat(instanceRepository.find(instanceId).state())
        .isEqualTo(InstanceState.ACTIVE);

    assertThat(providerFake.resourcesFor(clientToken))
        .hasSize(1);
}
~~~

Trong thực tế, test worker có thể reactive/asynchronous và cần chờ condition với timeout thay vì gọi method đồng bộ như ví dụ. Để mô phỏng process chết thật, chạy worker trong process/container riêng, bật fault hook ghi marker rồi terminate process. Khởi động lại cùng database/queue/provider fake và chạy recovery.

Không dùng Thread.sleep cố định để chờ job. Dùng latch, Awaitility hoặc polling có deadline; test phải fail rõ ràng khi điều kiện không đạt.

## 22. Bộ bài tập capstone theo cấp độ

### Bài A — Crash trước khi ghi nhận request

1. Bật fault BEFORE_ACCEPT_COMMIT.
2. Gửi PUT provision.
3. Xác minh không có instance, operation hoặc outbox event.
4. Gửi lại cùng request.
5. Xác minh chỉ có một instance/operation được tạo.

Kết quả: request chưa commit thì retry có thể bắt đầu một lần xử lý mới.

### Bài B — Crash sau commit, trước publish

1. Bật fault AFTER_ACCEPT_COMMIT.
2. Gửi PUT và xác nhận response chỉ được trả khi commit thành công.
3. Dừng publisher trước khi gửi event.
4. Restart publisher.
5. Xác minh outbox event được publish và worker nhận job.

Kết quả: không mất operation đã accepted.

### Bài C — Crash sau provider side effect

1. Bật fault AFTER_PROVIDER_CREATED.
2. Gửi provision.
3. Xác minh provider fake có một resource nhưng broker chưa lưu provider ID.
4. Dừng worker và khởi động lại.
5. Chạy recovery lookup theo provider request key.
6. Xác minh broker attach đúng resource và không tạo resource thứ hai.

Kết quả: unknown outcome được giải quyết bằng lookup/idempotency.

### Bài D — Worker lease hết hạn và worker cũ quay lại

1. Worker A claim operation và lấy fencing token N.
2. Tạm dừng A lâu hơn lease.
3. Worker B claim operation và nhận token N+1.
4. Cho A tiếp tục và thử ghi state.
5. Xác minh update của A bị từ chối.
6. Xác minh B hoàn tất operation.

Kết quả: không có stale worker ghi đè state mới.

### Bài E — Deprovision thành công nhưng local state chưa cập nhật

1. Bật fault sau provider delete.
2. Xác minh provider resource đã biến mất nhưng instance vẫn DEPROVISIONING.
3. Restart worker.
4. Inspect đúng provider account/resource ID.
5. Xác minh not-found được xử lý như desired state đã đạt.
6. Xác minh operation thành công và không gọi delete nhầm resource khác.

Kết quả: retry deprovision an toàn.

### Bài F — Orphan và duplicate resource

1. Tạo provider resource có broker marker nhưng không có local instance.
2. Tạo thêm một resource trùng client token trong fake provider nếu test provider cho phép.
3. Chạy reconciliation.
4. Xác minh cả hai được phân loại và có decision/audit.
5. Xác minh hệ thống không auto-delete resource khi chưa đủ bằng chứng.
6. Chỉ thực hiện cleanup qua action có owner/approval trong lab.

Kết quả: reconciliation phân biệt repair tự động và trường hợp cần review.

## 23. Ma trận fault và kết quả mong đợi

| Fault point | Broker DB | Provider | Expected recovery |
|---|---|---|---|
| Before accept commit | Không có record | Không có resource | Platform retry |
| After accept commit | Instance/operation/outbox có | Chưa có resource | Outbox publish lại |
| After worker claim | Operation IN_PROGRESS, lease | Chưa có resource | Reclaim sau lease expiry |
| Before provider request | Operation đang chạy | Chưa có resource | Retry cùng operation |
| Provider created, response lost | Mapping có thể chưa có | Có resource | Lookup theo provider key, attach |
| After local resource save | Mapping đã có | Có resource | Đọc mapping, hoàn tất operation |
| Before terminal commit | Instance có thể đã ACTIVE trong transaction chưa commit | Có resource | Transaction rollback hoặc read committed state rồi hoàn tất |
| After terminal commit | Operation SUCCEEDED | Có resource | Poll/retry trả cùng kết quả |
| After provider delete | Instance DEPROVISIONING | Không có resource | Inspect, mark deprovisioned |
| Worker A stale | State do B sở hữu | Có/không tùy stage | Fencing từ chối write của A |

Trong test, kiểm tra record count, provider resource count, ownership epoch, operation token, provider request key và audit event. Không chỉ kiểm tra cuối cùng HTTP status.

## 24. Quan sát và audit quá trình recovery

Mỗi lần worker claim/retry/reconcile cần ghi:

- Operation ID và instance ID nội bộ.
- Platform/tenant scope dưới dạng ID nội bộ được bảo vệ.
- Operation type và attempt number.
- Worker identity và fencing token.
- Provider request key dạng opaque hoặc hash phù hợp.
- Fault point/test run ID nếu đang chạy lab.
- Provider response category và latency.
- State trước/sau.
- Repair action và reason code.
- Correlation ID và timestamp.

Không log token, password, connection URI có secret, raw request body hoặc provider credential. Với metrics, dùng label có cardinality thấp như operation type, provider, result, reason class. Instance/operation ID để trong log hoặc trace.

Các metric hữu ích:

| Metric | Mục đích |
|---|---|
| broker_operation_attempts_total | Đếm worker attempt |
| broker_operation_recovery_total | Đếm operation được reclaim |
| broker_operation_reconciliation_total | Đếm reconciliation result |
| broker_provider_duplicate_resource_detected_total | Phát hiện duplicate |
| broker_orphan_resource_detected_total | Phát hiện orphan candidate |
| broker_stale_worker_write_rejected_total | Fencing từ chối stale write |
| broker_outbox_oldest_unpublished_age_seconds | Theo dõi outbox backlog |
| broker_operation_oldest_in_progress_age_seconds | Phát hiện operation bị kẹt |

## 25. Tiêu chí nghiệm thu

Capstone chỉ đạt khi các bằng chứng sau có thể được tái hiện và lưu trong test report:

- [ ] Request provision chỉ tạo một instance record trong scope.
- [ ] Instance, operation và outbox được commit cùng transaction.
- [ ] Crash sau commit không làm mất job.
- [ ] Duplicate message không tạo duplicate provider resource.
- [ ] Crash sau provider create được recovery bằng lookup/idempotency.
- [ ] Provider resource mapping và operation terminal state được commit nhất quán.
- [ ] Worker cũ không ghi được sau khi fencing token thay đổi.
- [ ] last_operation trả trạng thái chính xác và token ổn định.
- [ ] Deprovision crash sau provider delete có thể hoàn tất sau restart.
- [ ] Reconciliation phát hiện missing, orphan, duplicate và ownership mismatch.
- [ ] Resource mơ hồ không bị auto-delete.
- [ ] Bind/unbind retry không cấp hoặc revoke nhầm credential.
- [ ] DLQ có owner và quy trình replay.
- [ ] Log/audit không chứa secret.
- [ ] Fault injection chỉ bật trong môi trường test/lab.
- [ ] Có runbook restart, reconciliation và cleanup.

## 26. Runbook khi operation bị kẹt sau restart

Khi platform báo operation không hoàn tất:

1. Tìm instance theo platform registration và external instance ID.
2. Lấy operation token hiện tại và state từ database.
3. Kiểm tra updated_at, attempt, lease expiry và worker heartbeat.
4. Kiểm tra outbox/queue/DLQ để biết job đang ở đâu.
5. Tra log bằng correlation ID và operation ID.
6. Kiểm tra provider resource bằng resource ID, client token hoặc broker tag.
7. Phân loại: chưa gửi provider request, provider chưa tạo, đã tạo nhưng chưa lưu, đã hoàn tất hoặc outcome unknown.
8. Reclaim operation chỉ khi lease hết hạn và fencing token mới được cấp.
9. Chạy retry với cùng provider request key hoặc reconciliation phù hợp.
10. Xác minh instance state, provider resource, operation state và platform polling.
11. Ghi audit và đóng incident sau khi không còn drift.

Không reset state bằng SQL thủ công khi chưa hiểu worker lease, operation token và provider side effect. Nếu cần sửa dữ liệu, dùng repair command có dry-run, ownership check, audit và idempotency.

## 27. Những lỗi thường gặp và cách khắc phục

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Gọi provider trước khi lưu operation | Crash làm mất dấu request | Commit instance/operation/outbox trước |
| Commit DB rồi publish queue trực tiếp | Crash giữa hai bước làm mất job | Transactional outbox |
| Tạo provider key mới mỗi retry | Duplicate resource | Persist và reuse provider request key |
| Coi timeout là provider thất bại | Retry create dù resource đã tồn tại | Lookup/reconcile unknown outcome |
| Reset mọi IN_PROGRESS khi restart | Hai worker cùng thao tác | Lease expiry và fencing |
| Chỉ có lease, không có fencing | Worker cũ có thể ghi sau khi lease hết | Token tăng đơn điệu và conditional write |
| Ghi mapping và operation ở hai transaction | State không nhất quán | Commit trong cùng transaction |
| Xóa orphan ngay khi không thấy DB record | Xóa nhầm resource đang được migrate | Quarantine, verify owner, approval |
| Dùng external instance ID làm provider ID | Không tìm được resource thực tế | Lưu riêng platform ID và provider ID |
| Reconciliation load toàn inventory vào memory | OOM khi hệ thống lớn | Pagination và batch |
| Retry lỗi permanent | Tăng tải và kéo dài incident | Phân loại retryable/permanent |
| Replay DLQ bằng operation mới | Mất idempotency | Giữ operation ID và provider key |
| Test chỉ qua HTTP 202 | Không chứng minh provider hoàn tất | Assert state, mapping và provider inventory |
| Fault hook bật trong production | Có thể chủ động làm chết worker | Profile test/lab và access control |

## 28. Tổng kết bài thực hành

Sự cố giữa chừng là tình huống bình thường trong một hệ thống phân tán. Process có thể chết sau commit, queue có thể redeliver, provider có thể thực hiện side effect nhưng response bị mất, và worker cũ có thể quay lại sau khi lease hết hạn. Broker cần thiết kế để nhận biết từng trường hợp và phục hồi dựa trên dữ liệu bền vững.

Khi hoàn thành **SPRING_CLOUD_SERVICE_BROKER**, hãy nhớ:

- Ghi instance, operation và outbox trong một transaction trước khi xác nhận request async.
- Giữ operation token, request fingerprint và provider idempotency key ổn định qua retry.
- Dùng lease kết hợp fencing token để kiểm soát worker sau restart.
- Sau timeout không rõ kết quả, inspect/lookup provider trước khi lặp side effect.
- Lưu provider resource mapping và terminal operation state nhất quán.
- Reconciliation phải phân loại match, missing, orphan, duplicate và unknown.
- Chỉ tự động repair trường hợp có bằng chứng ownership; resource mơ hồ cần review.
- Deprovision, bind và unbind cũng phải idempotent và có recovery path.
- Dùng fault injection có kiểm soát để chứng minh từng failure window.
- Kiểm thử bằng database/queue/provider fake có persistence qua lần restart.
- Giữ audit, metrics và runbook để vận hành được khi sự cố xảy ra thật.

Một broker đáng tin cậy không phụ thuộc vào giả định worker sẽ chạy đến cuối. Nó lưu đủ state để tiếp tục sau restart, phân biệt được side effect đã xảy ra hay chưa và chỉ sửa tài nguyên khi có bằng chứng đúng ownership.

