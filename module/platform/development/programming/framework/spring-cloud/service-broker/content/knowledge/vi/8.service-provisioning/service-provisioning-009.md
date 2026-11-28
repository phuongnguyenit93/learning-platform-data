# Thu hồi tài nguyên đã tạo khi cấp phát chỉ thành công một phần

## Mục tiêu và bối cảnh

Một yêu cầu provision trong service broker thường phải tạo nhiều tài nguyên ở các hệ thống khác nhau. Ví dụ, cấp phát một dịch vụ PostgreSQL có thể gồm tạo network rule, tạo database, tạo user quản trị, cấu hình backup và đăng ký thông tin kết nối. Các bước này thường không nằm trong cùng một transaction cơ sở dữ liệu.

Nếu bước đầu và bước thứ hai đã thành công nhưng bước thứ ba thất bại, broker phải xử lý các tài nguyên đã tạo trước đó. Nếu chỉ trả lỗi cho platform rồi bỏ mặc backend, hệ thống có thể để lại database rỗng, user không còn được quản lý, security rule dư thừa hoặc volume không có service instance tương ứng. Những tài nguyên mồ côi này gây tốn chi phí, tạo bề mặt tấn công và làm sai lệch trạng thái giữa broker với backend.

Bài học này tập trung vào việc thu hồi tài nguyên đã tạo khi quá trình cấp phát chỉ thành công một phần trong module Spring Cloud Service Broker. Cách tiếp cận chính là mô hình saga với các hành động bù trừ (compensation), kết hợp resource ledger, trạng thái operation bền vững, retry và reconciliation.

Sau bài học, bạn có thể:

- Nhận diện các điểm có thể thất bại trong workflow provision nhiều bước.
- Thiết kế hành động bù trừ cho từng tài nguyên đã tạo.
- Thu hồi tài nguyên theo thứ tự ngược với thứ tự cấp phát.
- Xử lý timeout không rõ kết quả và retry an toàn.
- Lưu tiến độ cấp phát và cleanup để phục hồi sau khi broker restart.
- Biểu diễn kết quả provision thất bại qua operation của OSB API.
- Kiểm thử cả trường hợp cleanup thành công lẫn cleanup tiếp tục thất bại.

## 1. Vì sao provision có thể thành công một phần?

Một service instance thường được tạo từ nhiều bước độc lập. Ví dụ, một dịch vụ PostgreSQL có thể cần:

1. Kiểm tra quota và cấu hình của tenant.
2. Tạo network policy hoặc firewall rule.
3. Tạo database server hoặc database instance.
4. Tạo database/schema.
5. Tạo role và credentials cho quản trị.
6. Cấu hình backup và monitoring.
7. Lưu backend reference vào broker.
8. Đánh dấu service instance sẵn sàng.

Các bước này có thể gọi nhiều API, mỗi API có timeout, lỗi xác thực, giới hạn tốc độ hoặc trạng thái eventual consistency riêng. Không có transaction ACID bao trùm database của broker, cloud provider và database server.

Ví dụ:

~~~mermaid
flowchart TD
    A[Nhận yêu cầu provision] --> B[Kiểm tra quota]
    B --> C[Tạo network policy]
    C --> D[Tạo database instance]
    D --> E[Tạo database user]
    E --> F[Cấu hình backup]
    F --> G[Lưu backend reference]
    G --> H[Đánh dấu READY]
    E -->|Lỗi| X[Bắt đầu compensation]
    F -->|Lỗi| X
    X --> Y[Thu hồi database user]
    Y --> Z[Xóa database instance]
    Z --> W[Xóa network policy]
    W --> Q[Đánh dấu operation failed]
~~~

Giả sử network policy và database instance đã được tạo, nhưng backend từ chối tạo user vì vượt quota role. Broker không thể coi toàn bộ workflow là thành công. Nó cần thu hồi database instance và network policy đã tạo để đưa hệ thống về trạng thái phù hợp.

### 1.1. Các kiểu thất bại

| Tình huống | Ví dụ | Hướng xử lý |
|---|---|---|
| Lỗi trước khi tạo tài nguyên | Parameters không hợp lệ, tenant vượt quota | Từ chối request; không cần compensation backend |
| Lỗi trong một bước | Tạo database thành công, tạo user thất bại | Bù trừ những bước đã hoàn tất |
| Timeout không rõ kết quả | API tạo database timeout nhưng cloud có thể đã nhận lệnh | Tra cứu theo idempotency key hoặc resource tag trước khi quyết định |
| Lỗi khi cleanup | Xóa database bị giới hạn tốc độ | Ghi cleanup pending, retry và reconciliation |
| Broker restart | Tiến trình dừng giữa lúc xóa tài nguyên | Phục hồi từ operation và resource ledger |
| Tài nguyên dùng chung | Network policy được nhiều instance sử dụng | Chỉ thu hồi phần sở hữu riêng; không xóa tài nguyên dùng chung |

Điểm quan trọng là timeout không đồng nghĩa với thao tác thất bại. Backend có thể đã thực hiện lệnh nhưng response bị mất. Nếu broker lập tức gửi lệnh tạo lại, có thể xuất hiện hai tài nguyên cùng phục vụ một instance.

## 2. Saga và hành động bù trừ

Saga chia một workflow dài thành các bước cục bộ. Mỗi bước thực hiện một thay đổi ở một hệ thống và có một hành động bù trừ tương ứng để đảo ngược tác động khi workflow không thể tiếp tục.

Ví dụ:

| Bước cấp phát | Tài nguyên tạo ra | Hành động bù trừ |
|---|---|---|
| Tạo network policy | Firewall rule riêng của instance | Xóa rule đó |
| Tạo database instance | Database server hoặc database instance | Xóa instance |
| Tạo database user | Role hoặc user backend | Thu hồi role/user |
| Cấu hình backup | Backup policy riêng | Xóa hoặc vô hiệu hóa policy |
| Đăng ký DNS | DNS record riêng | Xóa record nếu còn thuộc quyền sở hữu |

Nếu workflow chạy theo thứ tự A → B → C → D và D thất bại, các hành động bù trừ thường chạy theo thứ tự ngược: undo C → undo B → undo A. Thứ tự này giúp xử lý phụ thuộc: trước khi xóa database instance, broker cần thu hồi user và policy phụ thuộc vào nó.

~~~mermaid
sequenceDiagram
    participant Broker
    participant Ledger as Resource Ledger
    participant Network as Network API
    participant DB as Database API
    participant User as Identity API

    Broker->>Ledger: Ghi operation và step A
    Broker->>Network: Tạo network policy
    Network-->>Broker: Thành công
    Broker->>Ledger: A = CREATED
    Broker->>DB: Tạo database instance
    DB-->>Broker: Thành công
    Broker->>Ledger: B = CREATED
    Broker->>User: Tạo database user
    User-->>Broker: Lỗi
    Broker->>Ledger: Operation = COMPENSATING
    Broker->>DB: Xóa database instance
    DB-->>Broker: Đã xóa
    Broker->>Ledger: B = COMPENSATED
    Broker->>Network: Xóa network policy
    Network-->>Broker: Đã xóa
    Broker->>Ledger: A = COMPENSATED
    Broker->>Ledger: Operation = FAILED
~~~

Compensation không phải lúc nào cũng là phép đảo ngược hoàn hảo. Ví dụ, một thao tác gửi email, ghi audit hoặc phát event ra hệ thống bên ngoài không thể được xóa khỏi lịch sử. Với những bước như vậy, hành động bù trừ có thể là phát event sửa sai, thu hồi quyền hoặc đánh dấu trạng thái cần xử lý. Vì thế, hãy xác định tác động phụ của từng bước trước khi thiết kế workflow.

### 2.1. Compensation phải có tính idempotent

Một hành động cleanup có thể được thực hiện nhiều lần do worker retry, broker restart hoặc queue giao message trùng. Do đó, compensation phải an toàn khi lặp:

- Nếu tài nguyên đã được xóa, lần xóa tiếp theo được coi là đã hoàn tất.
- Nếu tài nguyên chưa từng được tạo, không được tạo ra lỗi cleanup giả.
- Nếu tài nguyên thuộc instance khác, từ chối xóa và ghi nhận xung đột.
- Nếu backend trả timeout, kiểm tra lại trạng thái trước khi gửi lệnh xóa tiếp.
- Mỗi hành động bù trừ có định danh ổn định gắn với operation và resource.

Không nên dựa vào thông báo "delete returned 404" để luôn kết luận cleanup thành công. Trước hết phải xác định 404 có nghĩa tài nguyên không còn tồn tại hay broker đang dùng sai ID hoặc sai tenant. Quy tắc coi "not found" là đã xóa cần được xác nhận theo API backend.

### 2.2. Không bù trừ tài nguyên dùng chung một cách mù quáng

Một số tài nguyên được chia sẻ giữa nhiều service instance, chẳng hạn network, subnet, cluster, database server hoặc storage pool. Nếu provision một instance thất bại, broker chỉ được thu hồi phần tài nguyên mà instance đó sở hữu.

Có thể phân biệt:

- **Tài nguyên riêng:** được tạo riêng cho một instance và có thể xóa khi instance đó thất bại.
- **Tài nguyên dùng chung:** được quản lý ở cấp platform hoặc tenant; chỉ xóa khi không còn consumer và chính sách cho phép.
- **Tài nguyên được mượn:** broker chỉ giữ reference và không có quyền sở hữu vòng đời.

Resource ledger cần ghi loại sở hữu hoặc owner reference để compensation không xóa nhầm tài nguyên chung.

## 3. Lưu resource ledger và tiến độ workflow

Broker cần lưu dấu vết bền vững về những tài nguyên đã tạo và trạng thái của từng bước. Không nên chỉ lưu một cờ provisioned=true/false vì cờ đó không thể diễn tả workflow đã tạo được những gì.

Một mô hình dữ liệu tham khảo:

| Bảng | Trường quan trọng | Mục đích |
|---|---|---|
| service_instance | instance_id, service_id, plan_id, tenant_id, state | Trạng thái nghiệp vụ của instance |
| broker_operation | operation_id, instance_id, type, state, current_step, error_code | Theo dõi workflow |
| provision_step | operation_id, step_key, sequence, state, attempts, resource_ref | Theo dõi từng bước |
| managed_resource | resource_id, instance_id, provider, external_id, ownership, state | Ghi nhận tài nguyên backend |
| outbox_event | event_id, aggregate_id, event_type, payload, published_at | Phát công việc bền vững |

Không nhất thiết phải triển khai đúng các bảng này. Có thể dùng một bảng operation với payload có cấu trúc hoặc một kho dữ liệu khác, nhưng phải lưu được tiến độ từng bước và các reference cần để cleanup.

### 3.1. Trạng thái step

Một state machine cho từng bước có thể gồm:

~~~mermaid
stateDiagram-v2
    [*] --> PENDING
    PENDING --> RUNNING
    RUNNING --> CREATED
    RUNNING --> FAILED
    FAILED --> UNKNOWN
    CREATED --> COMPENSATING
    COMPENSATING --> COMPENSATED
    COMPENSATING --> CLEANUP_FAILED
    CLEANUP_FAILED --> COMPENSATING
~~~

Ý nghĩa:

- PENDING: bước chưa được thực hiện.
- RUNNING: broker đã bắt đầu gọi backend.
- CREATED: backend xác nhận tài nguyên đã được tạo.
- FAILED: thao tác trả lỗi rõ ràng.
- UNKNOWN: kết quả không xác định, thường do timeout hoặc mất kết nối.
- COMPENSATING: đang thu hồi tài nguyên.
- COMPENSATED: hành động bù trừ đã hoàn tất.
- CLEANUP_FAILED: cleanup thất bại và cần retry hoặc can thiệp.

Trạng thái UNKNOWN đặc biệt quan trọng. Nếu API tạo tài nguyên timeout, broker chưa thể biết tài nguyên có tồn tại hay không. Worker phải tra cứu theo resource name, idempotency key hoặc metadata trước khi quyết định tiếp tục provision hay bù trừ.

### 3.2. Lưu external resource reference sớm

Ngay khi backend trả về resource ID, broker cần lưu reference đó cùng operation và step. Nếu broker đợi đến cuối workflow mới lưu tất cả reference, một lỗi ở bước sau có thể khiến broker không biết phải xóa tài nguyên nào.

Một resource record nên có:

- Instance ID và operation ID.
- Tên provider/backend.
- External resource ID.
- Resource type.
- Ownership: exclusive, shared hoặc borrowed.
- Trạng thái provision và cleanup.
- Metadata cần thiết để truy vấn hoặc thu hồi.
- Thời điểm tạo, cập nhật và xóa.

Không lưu credentials thô trong resource ledger. Nếu cần thông tin xác thực để cleanup, dùng secret manager và lưu reference đến secret.

### 3.3. Transactional outbox

Nếu broker ghi operation trong database rồi gửi message vào queue bằng hai thao tác độc lập, có thể xảy ra trường hợp database commit nhưng message không được gửi, hoặc message đã gửi nhưng transaction rollback.

Transactional outbox giải quyết khoảng trống này bằng cách ghi operation và event vào cùng một transaction database. Một publisher riêng đọc outbox và phát message. Worker xử lý message theo cơ chế at-least-once và phải idempotent.

~~~mermaid
flowchart LR
    API[Provision API] --> TX[Database Transaction]
    TX --> I[(Instance + Operation)]
    TX --> O[(Outbox Event)]
    O --> P[Outbox Publisher]
    P --> Q[Queue]
    Q --> W[Provision Worker]
    W --> B[Backend APIs]
    W --> L[(Resource Ledger)]
~~~

## 4. Quy trình provision và compensation

Một workflow provision có thể chia thành các giai đoạn rõ ràng.

### 4.1. Giai đoạn kiểm tra trước khi tạo

Trước khi gọi backend:

1. Xác thực platform và request.
2. Kiểm tra service ID, plan ID và instance ID.
3. Kiểm tra parameters, quota và quyền tenant.
4. Kiểm tra instance ID đã được dùng chưa.
5. Tạo instance ở trạng thái PROVISIONING.
6. Tạo operation và các step PENDING.
7. Phát event cho worker qua outbox.

Nếu validation thất bại ở giai đoạn này, không có tài nguyên backend cần bù trừ. Broker trả lỗi request phù hợp theo OSB API.

### 4.2. Giai đoạn tạo tài nguyên

Worker thực hiện từng bước:

- Đánh dấu step RUNNING và lưu attempt.
- Gọi backend adapter với idempotency key hoặc resource name ổn định.
- Khi backend xác nhận thành công, lưu external resource ID.
- Chuyển step sang CREATED.
- Chỉ bắt đầu bước tiếp theo sau khi đã lưu được kết quả cần thiết của bước hiện tại.

Pseudocode minh họa:

~~~java
public void executeProvision(ProvisionOperation operation) {
    for (ProvisionStep step : operation.pendingStepsInOrder()) {
        stepRepository.markRunning(step.id());

        try {
            ResourceReference resource =
                    provisioner.create(step.command());

            resourceRepository.save(
                    ManagedResource.created(
                            operation.instanceId(),
                            step.key(),
                            resource
                    )
            );

            stepRepository.markCreated(step.id(), resource.id());
        } catch (Exception failure) {
            operationRepository.recordFailure(
                    operation.id(),
                    classify(failure),
                    safeDescription(failure)
            );
            compensationScheduler.schedule(operation.id());
            return;
        }
    }

    instanceRepository.markReady(operation.instanceId());
    operationRepository.markSucceeded(operation.id());
}
~~~

Đây là pseudocode thể hiện trách nhiệm của application service và worker, không phải chữ ký bắt buộc của Spring Cloud Service Broker. Trong implementation thực tế, cần xử lý transaction, retry, timeout và concurrency cho từng step.

### 4.3. Giai đoạn bù trừ

Khi một bước thất bại, broker chuyển operation sang COMPENSATING. Worker lấy danh sách các tài nguyên đã được xác nhận tạo thành công, sắp xếp theo thứ tự ngược và chạy cleanup.

Pseudocode:

~~~java
public void compensateProvision(String operationId) {
    BrokerOperation operation = operationRepository.get(operationId);

    operationRepository.markCompensating(operationId);

    List<ManagedResource> resources =
            resourceRepository.findCreatedResources(operationId)
                    .stream()
                    .sorted(Comparator.comparingInt(
                            ManagedResource::sequence).reversed())
                    .toList();

    for (ManagedResource resource : resources) {
        if (resource.isSharedOrBorrowed()) {
            resourceRepository.markRetained(resource.id());
            continue;
        }

        try {
            provisioner.delete(resource.reference());
            resourceRepository.markCompensated(resource.id());
        } catch (Exception cleanupFailure) {
            resourceRepository.markCleanupFailed(
                    resource.id(),
                    safeDescription(cleanupFailure)
            );
            operationRepository.markCleanupPending(operationId);
            return;
        }
    }

    instanceRepository.markProvisionFailed(operation.instanceId());
    operationRepository.markFailed(operationId);
}
~~~

Pseudocode này minh họa ý tưởng. Một hệ thống production nên tiếp tục cleanup các tài nguyên độc lập khác ngay cả khi một cleanup step thất bại, đồng thời ghi lại tất cả lỗi. Nếu tài nguyên B phụ thuộc vào A, không xóa A khi B chưa được thu hồi. Vì vậy, thứ tự và dependency giữa các resource step phải được mô hình hóa rõ ràng thay vì chỉ dựa vào số thứ tự.

Nếu cleanup thất bại, broker không được đánh dấu toàn bộ tài nguyên đã được thu hồi. Hãy giữ operation ở trạng thái nội bộ cleanup pending, lưu step thất bại và lên lịch retry. Chỉ khi đã xử lý xong các tài nguyên cần thu hồi mới kết thúc operation với kết quả provision failed.

## 5. Xử lý timeout và kết quả không xác định

Đây là một trong những tình huống khó nhất của provisioning.

Ví dụ broker gửi lệnh tạo database đến cloud provider. Provider tạo database thành công nhưng response bị mất. Broker nhận timeout. Nếu coi timeout là thất bại và chạy compensation ngay, broker có thể chưa biết database nào cần xóa. Nếu gửi lại lệnh create mà backend không idempotent, một database thứ hai có thể được tạo.

Quy trình an toàn hơn:

1. Đánh dấu step UNKNOWN thay vì FAILED ngay.
2. Tra cứu backend bằng resource name ổn định, operation ID hoặc idempotency key.
3. Nếu tài nguyên tồn tại và thuộc instance hiện tại, ghi reference vào ledger.
4. Nếu tài nguyên chưa tồn tại, retry lệnh create theo chính sách.
5. Nếu không xác định được quyền sở hữu, chuyển sang trạng thái cần reconciliation hoặc can thiệp.
6. Khi đã xác định tài nguyên được tạo nhưng workflow không thể tiếp tục, đưa tài nguyên vào compensation.

Mỗi lệnh tạo tài nguyên nên có định danh ổn định, ví dụ tên resource chứa instance ID đã được chuẩn hóa. Có thể gắn tag metadata như broker-instance-id, broker-operation-id và broker-owner. Metadata giúp tìm lại tài nguyên sau timeout hoặc restart.

Không dùng tên người dùng tự nhập trực tiếp làm external resource ID. Hãy chuẩn hóa, giới hạn ký tự và bảo đảm uniqueness theo backend.

## 6. Idempotency cho provision và cleanup

Nền tảng có thể retry PUT provision vì response bị mất. Worker cũng có thể nhận cùng một message nhiều lần. Do đó, cả thao tác tạo lẫn thao tác xóa đều phải idempotent.

### 6.1. Idempotency của provision

Với cùng instance ID và cùng ý nghĩa request:

- Không tạo service instance thứ hai.
- Không tạo operation provision mới nếu operation cũ vẫn đang xử lý.
- Trả lại trạng thái hoặc operation tương ứng theo hợp đồng OSB API.
- Nếu request cùng ID nhưng service, plan hoặc parameters xung đột, trả conflict phù hợp.

Backend adapter nên nhận idempotency key ổn định cho từng step. Ví dụ, khóa có thể được tạo từ instance ID và step key. Không tạo key mới mỗi lần worker retry vì backend sẽ xem đó là yêu cầu mới.

### 6.2. Idempotency của compensation

Cleanup phải có thể chạy lại sau khi worker restart:

- Trước khi xóa, kiểm tra trạng thái resource trong ledger.
- Nếu đã COMPENSATED, bỏ qua.
- Nếu UNKNOWN, truy vấn backend trước.
- Nếu backend xác nhận không còn resource, cập nhật COMPENSATED.
- Nếu backend vẫn có resource, gửi lệnh delete bằng định danh ổn định.
- Nếu nhận lỗi tạm thời, tăng attempt và retry với backoff.

Không chỉ dựa vào trạng thái trong database broker vì ledger có thể chưa kịp cập nhật trước khi process crash. Trạng thái backend và ledger cần được đối chiếu khi kết quả không rõ.

## 7. Kết nối compensation với Open Service Broker API

OSB API cung cấp hợp đồng để platform gọi provision và theo dõi operation. Khi broker xử lý bất đồng bộ, request provision có thể trả HTTP 202 Accepted cùng operation token nếu platform gửi accepts_incomplete=true và broker hỗ trợ thao tác async.

Ví dụ request:

~~~http
PUT /v2/service_instances/instance-123?accepts_incomplete=true
X-Broker-API-Version: <supported-version>
Authorization: Basic <broker-credentials>
Content-Type: application/json
~~~

~~~json
{
  "service_id": "service-postgresql",
  "plan_id": "plan-standard",
  "organization_guid": "org-100",
  "space_guid": "space-200",
  "parameters": {
    "storage_gb": 100
  }
}
~~~

Broker có thể trả:

~~~http
HTTP/1.1 202 Accepted
Content-Type: application/json
~~~

~~~json
{
  "operation": "provision-op-123"
}
~~~

Khi workflow đang provision hoặc đang compensation, endpoint last operation có thể báo state in progress. Broker chỉ báo state succeeded khi instance đã sẵn sàng. Nếu provision thất bại và compensation hoàn tất, operation kết thúc với state failed.

Ví dụ response khi cleanup đang chạy:

~~~json
{
  "state": "in progress",
  "description": "Dang thu hoi cac tai nguyen da tao"
}
~~~

Sau khi cleanup hoàn tất:

~~~json
{
  "state": "failed",
  "description": "Provision that bai; cac tai nguyen da tao da duoc thu hoi"
}
~~~

Nếu cleanup không thể hoàn tất dù đã retry, broker cần báo operation failed theo kết quả provision và giữ trạng thái cleanup pending trong hệ thống nội bộ, đồng thời phát cảnh báo vận hành. Không được mô tả rằng tài nguyên đã được thu hồi nếu vẫn còn resource tồn tại. Description gửi platform nên trung thực, ngắn gọn và không chứa secret hoặc chi tiết nội bộ nhạy cảm.

Nếu request không cho phép thao tác bất đồng bộ, broker không được trả 202 cho một workflow dài. Broker phải hoàn tất trong giới hạn đồng bộ hoặc trả lỗi theo hợp đồng OSB API khi không thể thực hiện trong chế độ đó. Cần kiểm tra phiên bản API và hành vi platform tích hợp.

### 7.1. Phân biệt trạng thái OSB và trạng thái nội bộ

| Trạng thái nội bộ | Ý nghĩa | Trạng thái operation OSB thường trả |
|---|---|---|
| PROVISIONING | Đang tạo tài nguyên | in progress |
| COMPENSATING | Đang thu hồi phần đã tạo | in progress |
| CLEANUP_PENDING | Cleanup còn lỗi tạm thời và sẽ retry | in progress khi broker còn tiếp tục workflow |
| PROVISION_SUCCEEDED | Instance sẵn sàng | succeeded |
| PROVISION_FAILED_CLEAN | Provision thất bại, cleanup hoàn tất | failed |
| PROVISION_FAILED_ORPHANED | Provision thất bại, còn tài nguyên cần xử lý | failed, kèm mô tả trung thực và cảnh báo nội bộ |

Các tên trên là trạng thái nội bộ minh họa. OSB API không yêu cầu broker công bố nguyên trạng mọi trạng thái nội bộ. Broker ánh xạ chúng sang trạng thái operation mà API định nghĩa.

## 8. Xử lý lỗi trong quá trình cleanup

Cleanup cũng có thể thất bại. Ví dụ backend đang bảo trì, API trả 429, tài nguyên đang được sử dụng hoặc quyền xóa đã bị thay đổi.

Một chiến lược đáng tin cậy cần:

- Phân loại lỗi tạm thời và lỗi không thể tự phục hồi.
- Retry với exponential backoff và jitter.
- Giới hạn số lần thử trong một khoảng thời gian.
- Lưu mã lỗi đã chuẩn hóa và resource reference.
- Tiếp tục thu hồi các tài nguyên độc lập nếu an toàn.
- Không xóa tài nguyên cha khi tài nguyên phụ thuộc chưa được thu hồi.
- Đưa lỗi kéo dài vào dead-letter queue hoặc hàng đợi can thiệp.
- Phát metric và cảnh báo khi cleanup pending vượt ngưỡng.
- Cung cấp công cụ vận hành để retry hoặc xử lý thủ công theo quyền.

Ví dụ phân loại:

| Lỗi cleanup | Hướng xử lý |
|---|---|
| Timeout mạng | Tra cứu resource, sau đó retry delete |
| HTTP 429 | Tôn trọng Retry-After nếu có, backoff và retry |
| HTTP 5xx | Retry có giới hạn |
| HTTP 401/403 | Không retry vô hạn; cảnh báo lỗi credentials hoặc quyền |
| Resource đang được sử dụng | Thu hồi dependency trước hoặc chờ theo chính sách |
| Resource không tồn tại | Xác minh identity/tenant; nếu đúng resource đã bị xóa thì đánh dấu hoàn tất |
| Resource thuộc owner khác | Dừng cleanup và báo xung đột, không cố xóa |

Không nên retry vô hạn trong một worker đồng bộ vì có thể giữ tài nguyên thread và làm tắc queue. Retry phải được lập lịch bền vững, có thời gian chờ và có giới hạn.

## 9. Reconciliation và phát hiện tài nguyên mồ côi

Dù có saga và retry, broker vẫn có thể bị gián đoạn giữa hai hệ thống. Reconciliation giúp so sánh resource ledger với trạng thái backend và phát hiện tài nguyên mồ côi.

Một reconciler có thể tìm:

- Operation COMPENSATING nhưng không có worker đang xử lý.
- Step CLEANUP_FAILED đã quá thời gian retry.
- Resource ledger ở trạng thái CREATED nhưng instance đã PROVISION_FAILED.
- Backend có resource tag thuộc broker nhưng không có instance tương ứng.
- Instance FAILED nhưng backend vẫn còn database, user, policy hoặc volume.
- Resource UNKNOWN quá lâu chưa được xác minh.

Quy trình reconciliation:

1. Lấy danh sách operation hoặc resource đến hạn kiểm tra.
2. Truy vấn backend bằng external ID hoặc tag.
3. Xác minh owner và instance ID.
4. So sánh trạng thái thực tế với ledger.
5. Nếu tài nguyên còn tồn tại và cần thu hồi, lập cleanup operation.
6. Nếu tài nguyên đã biến mất, cập nhật ledger.
7. Nếu không xác minh được quyền sở hữu, tạo cảnh báo và yêu cầu can thiệp.

Không nên tự động xóa mọi resource có tag gần giống tên broker. Reconciler phải xác minh đúng account, tenant, owner và resource ID để tránh xóa nhầm tài nguyên ngoài phạm vi quản lý.

## 10. Quan sát workflow và audit

Provision một phần và compensation cần được theo dõi như một workflow duy nhất. Mỗi log hoặc trace nên có các định danh:

- instance_id.
- operation_id.
- step_key.
- resource_id hoặc external resource ID đã được che phù hợp.
- attempt number.
- provider/backend.
- trạng thái trước và sau.
- correlation ID hoặc trace ID.

Không ghi password, access token, connection string hoặc toàn bộ parameters có thể chứa secret vào log. Description trả về platform cũng không nên chứa chi tiết nội bộ của nhà cung cấp.

Các metric hữu ích:

| Metric | Ý nghĩa |
|---|---|
| provision_started_total | Tổng số yêu cầu provision |
| provision_failed_total | Số yêu cầu provision thất bại |
| compensation_started_total | Số workflow bắt đầu bù trừ |
| compensation_completed_total | Số workflow bù trừ hoàn tất |
| cleanup_pending_resources | Số tài nguyên đang chờ thu hồi |
| cleanup_retry_total | Tổng số lần retry cleanup |
| orphan_resource_detected_total | Số tài nguyên mồ côi được phát hiện |
| provision_duration_seconds | Thời gian provision |
| compensation_duration_seconds | Thời gian cleanup |

Không đưa instance ID hoặc resource ID làm metric label có cardinality cao. Hãy dùng label có tập giá trị giới hạn như provider, step type và result.

Audit nên ghi nhận ai hoặc platform nào khởi tạo provision, bước nào thất bại, tài nguyên nào đã được tạo và thu hồi, thời điểm retry và người vận hành can thiệp nếu có.

## 11. Kiểm thử compensation

Không chỉ kiểm thử trường hợp provision thành công. Cần chủ động làm từng bước thất bại để xác nhận broker không để lại tài nguyên ngoài ý muốn.

Giả sử workflow có ba bước:

- A: tạo network policy.
- B: tạo database instance.
- C: tạo database user.

Các tình huống kiểm thử:

| Kịch bản | Kết quả mong đợi |
|---|---|
| A thất bại | Không có tài nguyên nào cần bù trừ |
| B thất bại sau A thành công | Xóa A |
| C thất bại sau A và B thành công | Xóa B rồi xóa A |
| B timeout nhưng backend đã tạo resource | Tra cứu và ghi reference trước khi compensation |
| Xóa B timeout nhưng backend đã xóa | Reconcile và đánh dấu B đã thu hồi |
| Xóa B trả 429 | Ghi cleanup pending và retry sau backoff |
| Xóa B bị 403 | Giữ trạng thái cleanup lỗi, cảnh báo và không giả định đã xóa |
| Broker restart khi đang compensation | Worker tiếp tục từ resource ledger |
| Message compensation được giao hai lần | Không xóa nhầm hoặc tạo tác động phụ lặp |
| Resource là shared | Không xóa resource dùng chung |
| Một resource độc lập cleanup thất bại | Vẫn xử lý các resource độc lập khác nếu an toàn |

### 11.1. Unit test cho thứ tự bù trừ

Có thể kiểm tra rằng các hành động bù trừ được gọi theo thứ tự ngược:

~~~java
@Test
void compensatesCreatedResourcesInReverseOrder() {
    operationFixture.markCreated("network-policy", 1);
    operationFixture.markCreated("database", 2);
    operationFixture.markCreated("database-user", 3);

    compensationService.compensate("operation-123");

    InOrder order = inOrder(provisioner);
    order.verify(provisioner).delete("database-user");
    order.verify(provisioner).delete("database");
    order.verify(provisioner).delete("network-policy");
}
~~~

Đây là ví dụ minh họa với mock và fixture giả định. Test thực tế cần kiểm tra cả cập nhật resource ledger, trạng thái operation và hành vi khi một lệnh delete ném lỗi.

### 11.2. Integration test với backend giả lập

Dùng fake backend hoặc container/service test double để mô phỏng:

- API tạo resource thành công nhưng response bị timeout.
- API xóa trả 429 trong vài lần đầu.
- API xóa đã hoàn tất nhưng response bị mất.
- Backend không cho xóa do resource đang được tham chiếu.
- Worker restart sau khi step đã tạo resource nhưng trước khi ledger cập nhật.

Sau test, truy vấn backend để xác nhận không còn resource riêng của instance thất bại, hoặc resource còn lại đã được ghi nhận cleanup pending với lý do cụ thể.

## 12. Những lỗi thiết kế thường gặp

- **Chỉ trả lỗi và bỏ qua cleanup:** tài nguyên backend trở thành orphan.
- **Không lưu resource reference sau từng bước:** broker không biết cần thu hồi tài nguyên nào.
- **Cleanup theo thứ tự tạo:** có thể xóa tài nguyên cha trước khi thu hồi dependency.
- **Coi timeout là thất bại chắc chắn:** dễ tạo resource trùng hoặc bỏ sót tài nguyên đã được tạo.
- **Compensation không idempotent:** retry có thể gây lỗi hoặc tác động phụ lặp.
- **Xóa tài nguyên dùng chung:** ảnh hưởng đến service instance khác.
- **Đánh dấu FAILED ngay khi bước provision lỗi:** operation kết thúc trong khi cleanup vẫn còn chạy.
- **Đánh dấu cleanup thành công khi chưa xác minh:** broker và backend tiếp tục lệch trạng thái.
- **Retry vô hạn trong thread:** làm cạn worker và che giấu lỗi cấu hình.
- **Không có reconciliation:** tài nguyên mồ côi tồn tại lâu sau crash hoặc timeout.
- **Ghi secret vào resource ledger hoặc log:** làm lộ credentials trong quá trình xử lý sự cố.

## 13. Quy trình thiết kế compensation cho một broker

Khi xây dựng workflow provision mới, hãy thiết kế hành động bù trừ cùng lúc với hành động tạo:

1. Liệt kê tất cả tài nguyên backend cần tạo.
2. Xác định thứ tự tạo và quan hệ phụ thuộc giữa tài nguyên.
3. Với mỗi bước, xác định external ID, owner và cách tìm lại resource sau timeout.
4. Định nghĩa hành động compensation và điều kiện coi là hoàn tất.
5. Xác định tài nguyên nào riêng, dùng chung hoặc được mượn.
6. Lưu tiến độ từng bước vào resource ledger.
7. Thiết kế idempotency key cho create và delete.
8. Quy định retry, backoff, timeout và dead-letter.
9. Ánh xạ workflow sang operation OSB API.
10. Viết test cho lỗi ở từng bước, lỗi cleanup và broker restart.
11. Xây dựng reconciliation để phát hiện orphan resource.
12. Tạo metric, log và audit để vận hành.

Một workflow chỉ nên được xem là hoàn tất khi trạng thái backend và trạng thái broker nhất quán theo chính sách. Nếu provision thất bại nhưng một resource chưa thu hồi được, broker phải giữ dấu vết và tiếp tục cleanup; không được che giấu tình trạng đó.

## Kết luận

Khi provision chỉ thành công một phần, service broker phải thu hồi những tài nguyên đã tạo để tránh chi phí, quyền truy cập và dữ liệu mồ côi. Saga với các hành động bù trừ cho phép chia workflow thành các bước độc lập, lưu tiến độ từng bước và chạy cleanup theo thứ tự ngược với các phụ thuộc.

Trong Spring Cloud Service Broker, hãy kết hợp resource ledger, operation bền vững, backend adapter idempotent, retry có giới hạn và reconciliation. Với OSB API, operation chỉ báo thành công khi instance sẵn sàng; nếu provision thất bại, broker cần phản ánh trạng thái failed và giữ trạng thái cleanup nội bộ cho đến khi các tài nguyên đã được thu hồi hoặc được ghi nhận rõ ràng để can thiệp. Thiết kế này giúp broker phục hồi sau timeout, restart và lỗi backend mà vẫn duy trì được tính nhất quán của vòng đời service instance.
