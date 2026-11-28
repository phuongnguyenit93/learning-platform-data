# Hoàn thiện vòng đời cấp phát, truy xuất, cập nhật và thu hồi instance

## Mục tiêu capstone

Trong bài thực hành tổng hợp này, bạn xây dựng một Spring Cloud Service Broker cung cấp dịch vụ PostgreSQL managed cho ứng dụng Orders. Platform có thể xem catalog, yêu cầu cấp phát một service instance, theo dõi operation bất đồng bộ, truy xuất metadata của instance, thay đổi plan hoặc cấu hình, tạo binding cho ứng dụng và cuối cùng thu hồi instance.

Capstone kết hợp các năng lực cốt lõi của một broker theo Open Service Broker API (OSB API):

- Công bố service offering và service plan có ID ổn định.
- Provision một instance theo plan và parameters.
- Lưu trạng thái instance và operation bền vững.
- Xử lý request lặp an toàn bằng idempotency.
- Hỗ trợ asynchronous operation và endpoint last_operation.
- Tra cứu instance theo platform/tenant scope.
- Update plan hoặc cấu hình theo chính sách tương thích.
- Bind/unbind credentials cho consumer.
- Deprovision và xác minh tài nguyên provider đã được thu hồi.
- Bảo vệ credentials, phân quyền nhiều khách hàng và quan sát thời gian xử lý.

Kết quả mong đợi là một luồng lifecycle có thể kiểm thử từ đầu đến cuối, có khả năng phục hồi khi broker hoặc provider timeout, và không tạo database trùng khi platform retry request.

## 1. Bài toán và kịch bản thực tế

Một platform nội bộ cho phép team tạo database cho ứng dụng mà không cần tự gọi API của cloud provider. Platform chỉ biết broker và catalog của broker. Broker chịu trách nhiệm tạo database PostgreSQL, cấp quyền truy cập, quản lý thay đổi và thu hồi tài nguyên.

Kịch bản mẫu:

| Thành phần | Giá trị |
|---|---|
| Service offering | Managed PostgreSQL |
| Service ID | postgres-managed |
| Plan nhỏ | development |
| Plan tiêu chuẩn | standard |
| Plan lớn | production |
| Consumer | orders-api |
| Instance ID | orders-db-01 |
| Binding ID | orders-api-binding |
| Provider | PostgreSQL service hoặc PostgreSQL Operator |

Plan development có thể cấp database dung lượng nhỏ cho môi trường thử nghiệm. Plan standard có backup và giới hạn kết nối cao hơn. Plan production có dung lượng lớn, chính sách backup/HA và yêu cầu vận hành nghiêm ngặt hơn. Các giá trị tài nguyên trong ví dụ chỉ để minh họa; broker phải công bố chính xác giới hạn và khả năng mà provider thực sự hỗ trợ.

### Vai trò của từng thành phần

- **Platform:** gọi OSB API, quản lý service instance trong trải nghiệm marketplace và liên kết instance với ứng dụng.
- **Spring Cloud Service Broker:** xác thực request, kiểm tra plan/parameters, quản lý lifecycle, idempotency và operation.
- **Operation worker:** thực hiện công việc dài, retry và reconcile kết quả.
- **Provider adapter:** chuyển yêu cầu domain thành API call tới PostgreSQL provider hoặc Operator.
- **Persistence:** lưu instance, binding, operation, idempotency fingerprint và outbox.
- **Secret manager:** lưu credentials và hỗ trợ rotation/revocation.
- **Monitoring:** theo dõi provision duration, backlog, operation age, provider latency và lỗi.

~~~mermaid
flowchart TB
    P[Cloud platform / marketplace] -->|OSB API| B[Spring Cloud Service Broker]
    B --> A[Application and domain services]
    A --> R[(Instance, binding, operation DB)]
    A --> O[(Transactional outbox)]
    O --> Q[Queue]
    Q --> W[Lifecycle workers]
    W --> PA[Provider adapter]
    PA --> PG[(PostgreSQL provider)]
    W --> SM[Secret manager]
    B --> M[Metrics, logs and traces]
    W --> M
    P -->|Application binding| SM
~~~

## 2. Phạm vi OSB API và khái niệm truy xuất

OSB API cung cấp contract chuẩn cho catalog, provision, update, deprovision, binding và polling operation. Các endpoint thường dùng trong capstone:

| HTTP | Endpoint | Mục đích |
|---|---|---|
| GET | /v2/catalog | Đọc offering và plan |
| PUT | /v2/service_instances/{instance_id} | Provision service instance |
| PATCH | /v2/service_instances/{instance_id} | Update service instance |
| DELETE | /v2/service_instances/{instance_id} | Deprovision service instance |
| GET | /v2/service_instances/{instance_id}/last_operation | Poll trạng thái operation |
| PUT | /v2/service_instances/{instance_id}/service_bindings/{binding_id} | Tạo binding |
| DELETE | /v2/service_instances/{instance_id}/service_bindings/{binding_id} | Xóa binding |

### Phân biệt truy xuất instance và polling operation

OSB API không định nghĩa một GET endpoint tổng quát để platform đọc toàn bộ chi tiết của service instance theo instance ID. Endpoint last_operation chỉ trả trạng thái của một thao tác lifecycle, ví dụ provision hoặc update, chứ không phải API inventory đầy đủ của instance.

Vì vậy, trong capstone cần tách hai nhu cầu:

1. **Polling OSB operation:** platform gọi GET last_operation theo contract để biết thao tác còn in progress, succeeded hay failed.
2. **Tra cứu instance metadata:** broker đọc instance từ repository trong application service; nếu cần giao diện quản trị hoặc API inventory, xây dựng endpoint nội bộ riêng, có authentication/authorization, tenant scope và response đã redacted.

Không tự thêm GET service instance vào OSB public contract rồi gọi đó là endpoint chuẩn. Nếu platform có API riêng để hiển thị instance, platform có thể dùng dữ liệu do chính nó lưu hoặc tích hợp API quản trị được công bố riêng.

### Các loại ID không được đánh đồng

| ID | Vòng đời | Ý nghĩa |
|---|---|---|
| service_id | Ổn định theo offering | Chọn loại dịch vụ |
| plan_id | Ổn định theo plan | Chọn kích thước/tính năng |
| instance_id | Do platform cung cấp | Định danh service instance trong platform scope |
| binding_id | Do platform cung cấp | Định danh một consumer binding |
| operation ID | Do broker tạo/trả | Theo dõi một lifecycle operation |
| provider_resource_id | Do provider tạo | Định danh database thực tế |

Broker phải lưu mapping giữa các ID. Không dùng provider resource ID làm instance ID và không dùng resourceVersion/UID của Kubernetes thay operation ID.

## 3. Yêu cầu chức năng và tiêu chí chấp nhận

### Yêu cầu chức năng

1. Catalog trả về offering postgres-managed và ba plan có ID ổn định.
2. Provision validate service ID, plan ID, parameters và context.
3. Broker tạo instance record và operation record bền vững.
4. Request retry với cùng instance và cùng ý định không tạo database thứ hai.
5. Request cùng instance ID nhưng payload không tương thích phải bị từ chối theo policy.
6. Operation dài được trả về dưới dạng asynchronous response khi caller cho phép.
7. Platform poll last_operation cho đến terminal state.
8. Operator có thể truy xuất instance metadata theo tenant scope.
9. Update kiểm tra plan transition và parameters có được hỗ trợ hay không.
10. Deprovision thu hồi provider resource và credentials theo policy.
11. Binding tạo credential riêng cho consumer; unbind thu hồi credential.
12. Mọi endpoint và worker đều kiểm tra ownership.

### Tiêu chí hoàn thành

| Hạng mục | Tiêu chí kiểm chứng |
|---|---|
| Catalog | JSON đúng contract; service_id/plan_id ổn định |
| Provision | Tạo đúng một instance và trả response phù hợp sync/async |
| Operation | last_operation phản ánh state bền vững, không phụ thuộc process memory |
| Retrieval | Tra cứu đúng instance trong platform/tenant scope, không lộ secret |
| Update | Chỉ thay đổi thuộc tính được plan/provider hỗ trợ |
| Binding | Mỗi binding có credentials riêng và được lưu an toàn |
| Unbind | Provider credential bị revoke và secret được xử lý theo retention |
| Deprovision | Provider resource được thu hồi hoặc được reconcile rõ ràng |
| Idempotency | Retry không nhân đôi provider side effect |
| Recovery | Restart không làm mất operation hoặc tạo resource trùng |
| Security | Tenant A không đọc/sửa/xóa resource của tenant B |
| Monitoring | Có duration, backlog và oldest incomplete age |

## 4. Thiết kế catalog và plan

Catalog là hợp đồng mà platform dùng để khám phá dịch vụ. Service ID và plan ID cần ổn định qua các lần deploy. Không dùng display name làm khóa nghiệp vụ vì tên hiển thị có thể thay đổi hoặc được dịch.

Ví dụ response rút gọn:

~~~json
{
  "services": [
    {
      "id": "postgres-managed",
      "name": "managed-postgresql",
      "description": "Managed PostgreSQL for application workloads",
      "bindable": true,
      "plans": [
        {
          "id": "development",
          "name": "Development",
          "description": "Small database for development",
          "free": false
        },
        {
          "id": "standard",
          "name": "Standard",
          "description": "Production-ready database with backup",
          "free": false
        },
        {
          "id": "production",
          "name": "Production",
          "description": "Larger database with enhanced availability",
          "free": false
        }
      ]
    }
  ]
}
~~~

Response thực tế cần tuân theo schema và các capability của phiên bản OSB API mà broker công bố. Những trường metadata, plan_updateable, maintenance_info hoặc dashboard_url chỉ nên khai báo khi implementation thực sự hỗ trợ.

### Plan definition trong domain

~~~java
public record PlanDefinition(
        String id,
        String displayName,
        int storageGiB,
        int maxConnections,
        boolean backupEnabled,
        boolean highAvailability,
        Set<String> allowedRegions) {
}
~~~

Ví dụ plan mapping:

~~~java
Map<String, PlanDefinition> plans = Map.of(
    "development", new PlanDefinition(
        "development", "Development", 10, 20,
        false, false, Set.of("region-a")),
    "standard", new PlanDefinition(
        "standard", "Standard", 50, 100,
        true, false, Set.of("region-a", "region-b")),
    "production", new PlanDefinition(
        "production", "Production", 200, 300,
        true, true, Set.of("region-a", "region-b"))
);
~~~

Catalog service và application service phải dùng cùng một nguồn plan definition. Nếu catalog công bố plan nhưng provider adapter không thể thực thi, platform sẽ cho phép người dùng yêu cầu một cấu hình không tồn tại.

## 5. Mô hình dữ liệu lifecycle

Một thiết kế cơ bản có ba aggregate chính: ServiceInstance, ServiceBinding và ServiceOperation. Có thể bổ sung OutboxEvent và ProviderAttempt để quản lý event delivery và lịch sử provider call.

### Service instance

~~~sql
CREATE TABLE service_instance (
    platform_id          VARCHAR(128) NOT NULL,
    tenant_id            VARCHAR(128) NOT NULL,
    instance_id          VARCHAR(128) NOT NULL,
    service_id           VARCHAR(128) NOT NULL,
    plan_id              VARCHAR(128) NOT NULL,
    instance_state       VARCHAR(32) NOT NULL,
    provider_resource_id VARCHAR(256),
    parameters_json      JSON,
    created_at           TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at           TIMESTAMP WITH TIME ZONE NOT NULL,
    version              BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (platform_id, tenant_id, instance_id)
);
~~~

Schema là ví dụ và cần điều chỉnh theo database đang dùng. Parameters có thể chứa dữ liệu nhạy cảm hoặc thông tin cá nhân; không lưu plaintext tùy tiện. Chỉ lưu các thuộc tính cần thiết, mã hóa hoặc chuyển secret sang secret manager.

### Service operation

~~~sql
CREATE TABLE service_operation (
    operation_id       VARCHAR(128) PRIMARY KEY,
    platform_id        VARCHAR(128) NOT NULL,
    tenant_id          VARCHAR(128) NOT NULL,
    instance_id        VARCHAR(128) NOT NULL,
    operation_type     VARCHAR(32) NOT NULL,
    operation_state    VARCHAR(32) NOT NULL,
    request_fingerprint VARCHAR(128) NOT NULL,
    accepted_at        TIMESTAMP WITH TIME ZONE NOT NULL,
    completed_at       TIMESTAMP WITH TIME ZONE,
    attempt_count      INTEGER NOT NULL DEFAULT 0,
    safe_error_code    VARCHAR(64),
    safe_description   VARCHAR(512),
    version            BIGINT NOT NULL DEFAULT 0
);
~~~

Operation record là nguồn sự thật để trả last_operation và phục hồi worker sau restart. Không chỉ lưu trạng thái operation trong biến Java, future hoặc queue message.

### Service binding

~~~sql
CREATE TABLE service_binding (
    platform_id       VARCHAR(128) NOT NULL,
    tenant_id         VARCHAR(128) NOT NULL,
    instance_id       VARCHAR(128) NOT NULL,
    binding_id        VARCHAR(128) NOT NULL,
    consumer_identity VARCHAR(256),
    binding_state     VARCHAR(32) NOT NULL,
    credential_ref    VARCHAR(512),
    created_at        TIMESTAMP WITH TIME ZONE NOT NULL,
    revoked_at        TIMESTAMP WITH TIME ZONE,
    PRIMARY KEY (platform_id, tenant_id, instance_id, binding_id)
);
~~~

Database chỉ nên lưu credential reference nếu secret manager chịu trách nhiệm lưu password/token. Không lưu password trong log, operation error hoặc metric label.

### Outbox và provider attempt

Outbox ghi ý định phát message trong cùng transaction với operation. Worker đọc outbox rồi publish message; sau khi publish thành công, đánh dấu event đã gửi. ProviderAttempt lưu attempt number, provider request reference, thời gian bắt đầu/kết thúc và error category đã làm sạch.

## 6. State machine cho instance và operation

Instance state và operation state mô tả hai thứ khác nhau. Instance cho biết tài nguyên đang ở trạng thái nào; operation cho biết một yêu cầu cụ thể đang tiến triển ra sao.

### Instance state

| State | Ý nghĩa |
|---|---|
| PROVISIONING | Đang tạo provider resource |
| AVAILABLE | Instance sẵn sàng sử dụng |
| UPDATING | Đang thay đổi cấu hình/plan |
| DEPROVISIONING | Đang thu hồi |
| FAILED | Lifecycle thất bại và cần xử lý theo policy |
| DELETED | Đã thu hồi hoặc tombstone để lưu lịch sử |

### Operation state

| State | Terminal? | Ý nghĩa |
|---|---|---|
| ACCEPTED | Không | Broker đã chấp nhận và lưu operation |
| QUEUED | Không | Đang chờ worker |
| IN_PROGRESS | Không | Worker đang xử lý |
| RETRY_WAIT | Không | Chờ lần retry tiếp theo |
| RECONCILING | Không | Đang xác minh outcome với provider |
| SUCCEEDED | Có | Thao tác hoàn tất |
| FAILED | Có | Thao tác kết thúc lỗi |
| CANCELLED | Có | Thao tác bị hủy theo policy |

~~~mermaid
stateDiagram-v2
    [*] --> ACCEPTED
    ACCEPTED --> QUEUED
    QUEUED --> IN_PROGRESS
    IN_PROGRESS --> RECONCILING
    IN_PROGRESS --> RETRY_WAIT
    RETRY_WAIT --> QUEUED
    RECONCILING --> SUCCEEDED
    RECONCILING --> FAILED
    IN_PROGRESS --> SUCCEEDED
    IN_PROGRESS --> FAILED
    ACCEPTED --> FAILED
~~~

Không phải mọi operation đều đi qua mọi state. Ví dụ thao tác sync có thể hoàn tất ngay; thao tác async có thể chuyển thẳng từ IN_PROGRESS sang terminal nếu provider response đã đủ xác nhận.

### Quy tắc transition

- Chỉ transition được định nghĩa mới được phép.
- Terminal state không quay lại IN_PROGRESS.
- Retry tạo attempt mới nhưng không tạo operation nghiệp vụ mới cho cùng request intent.
- Worker phải dùng version/lease/fencing để tránh worker cũ ghi đè trạng thái mới.
- Instance state và operation state được cập nhật trong transaction nhất quán ở broker database.
- Provider side effect không nằm trong transaction database; cần idempotency và reconciliation.

## 7. Kiến trúc ứng dụng Spring

Khi dùng Spring Cloud Open Service Broker, thư viện đảm nhận việc ánh xạ HTTP/OSB protocol tới service interface. Không cần tự viết lại toàn bộ endpoint controller nếu framework đã cung cấp protocol adapter. Business logic nên nằm trong application/domain service, tách khỏi model request/response của framework.

Package tham khảo:

~~~text
service-broker/
  catalog/
    CatalogService
    PlanRegistry
  osb/
    ProvisioningHandler
    UpdatingHandler
    DeprovisioningHandler
    BindingHandler
    LastOperationHandler
  application/
    ProvisionInstanceUseCase
    RetrieveInstanceUseCase
    UpdateInstanceUseCase
    DeprovisionInstanceUseCase
    CreateBindingUseCase
    DeleteBindingUseCase
  domain/
    ServiceInstance
    ServiceBinding
    ServiceOperation
    PlanDefinition
    OperationState
  persistence/
    InstanceRepository
    BindingRepository
    OperationRepository
    OutboxRepository
  provider/
    DatabaseProvider
    PostgresProviderAdapter
  worker/
    OperationDispatcher
    OperationWorker
    ReconciliationWorker
  security/
    TenantScopeResolver
    ResourceAuthorizationService
  observability/
    OperationMetrics
~~~

OSB handler nên mỏng: chuyển request thành command, gọi use case và ánh xạ kết quả về response của framework. Domain không nên phụ thuộc vào class request của thư viện.

## 8. Provision: từ request đến database sẵn sàng

### Request mẫu

~~~http
PUT /v2/service_instances/orders-db-01?accepts_incomplete=true HTTP/1.1
Authorization: Basic <broker-credential>
X-Broker-API-Version: 2.17
Content-Type: application/json

{
  "service_id": "postgres-managed",
  "plan_id": "standard",
  "organization_guid": "org-retail",
  "space_guid": "space-orders",
  "parameters": {
    "region": "region-a",
    "database_name": "orders"
  },
  "context": {
    "platform": "cloud-foundry"
  }
}
~~~

Payload là ví dụ minh họa. Trong triển khai thật, broker cần xác thực platform, xác minh context, validate các trường được phép và áp dụng giới hạn của plan. Không tin organization/space hoặc tenant do caller tự khai nếu chưa được xác minh theo platform registration.

### Luồng xử lý

1. Framework nhận và parse OSB request.
2. Security layer xác thực broker/platform caller.
3. TenantScopeResolver xác định platform/tenant scope.
4. Provision use case kiểm tra service ID và plan ID.
5. Parameter validator kiểm tra region, database name, quota và reserved fields.
6. Idempotency service tìm instance cùng scope.
7. Transaction tạo instance state PROVISIONING, operation ACCEPTED và outbox event.
8. Broker trả response theo sync/async contract.
9. Worker claim operation, gọi provider adapter và ghi provider resource ID.
10. Worker/reconciler xác minh database sẵn sàng, cập nhật instance AVAILABLE và operation SUCCEEDED.

~~~mermaid
sequenceDiagram
    participant Platform
    participant Broker
    participant DB as Broker database
    participant Queue
    participant Worker
    participant Provider

    Platform->>Broker: PUT provision instance
    Broker->>Broker: Authenticate, authorize, validate
    Broker->>DB: Save instance + operation + outbox
    DB-->>Broker: Commit
    Broker-->>Platform: 202 Accepted + operation reference
    Broker->>Queue: Publish outbox event
    Queue-->>Worker: Deliver operation ID
    Worker->>DB: Claim operation lease
    Worker->>Provider: Create database
    Provider-->>Worker: Provider resource reference
    Worker->>Provider: Verify database readiness
    Worker->>DB: Mark instance AVAILABLE / operation SUCCEEDED
    Platform->>Broker: GET last_operation
    Broker->>DB: Read operation
    Broker-->>Platform: succeeded
~~~

### Khi nào trả đồng bộ và khi nào trả 202?

Nếu provider có thể hoàn tất trong giới hạn request timeout và broker thực sự xác minh được kết quả, có thể trả kết quả đồng bộ theo contract. Nếu thao tác kéo dài, cần queue/worker và hỗ trợ asynchronous operation. Caller phải cho phép incomplete operation qua tham số OSB phù hợp, thường là accepts_incomplete=true. Nếu request không cho phép async nhưng broker không thể hoàn tất đồng bộ, trả lỗi protocol phù hợp thay vì giữ request vô hạn.

Không trả 202 trước khi operation và ý định xử lý được ghi bền vững. Nếu broker trả accepted nhưng process crash trước khi lưu operation, platform sẽ poll một operation không tồn tại.

### Provision application service

~~~java
public ProvisionResult provision(ProvisionCommand command) {
    var scope = authorization.requireProvisionPermission(command.scope());
    var plan = planRegistry.requirePlan(command.serviceId(), command.planId());
    var parameters = parameterValidator.validate(plan, command.parameters());
    var fingerprint = requestFingerprint.of(command, plan, parameters);

    return transactionTemplate.execute(status -> {
        var existing = instanceRepository.find(
                scope.platformId(), scope.tenantId(), command.instanceId());

        if (existing.isPresent()) {
            return idempotency.resolveProvisionRetry(
                    existing.get(), fingerprint);
        }

        var operation = operationFactory.newProvision(
                scope, command.instanceId(), fingerprint);
        var instance = ServiceInstance.provisioning(
                scope, command.instanceId(), plan, parameters);

        instanceRepository.insert(instance);
        operationRepository.insert(operation);
        outboxRepository.append(OperationRequested.provision(operation.id()));

        return ProvisionResult.accepted(operation.id());
    });
}
~~~

Đây là pseudocode mô tả ranh giới trách nhiệm, không phải chữ ký method bắt buộc của Spring Cloud Open Service Broker. Cần xử lý unique-key race: hai request đồng thời có thể cùng thấy chưa tồn tại. Unique constraint là lớp bảo vệ cuối; khi insert conflict, đọc lại instance và áp dụng idempotency policy.

## 9. Idempotency và xử lý request lặp

Platform có thể retry vì timeout hoặc mất response. Broker phải giả định request có thể được gửi nhiều lần.

### Quy tắc cho provision

| Trường hợp | Hành vi |
|---|---|
| Cùng scope, cùng instance ID, cùng fingerprint | Trả lại kết quả/operation hiện có theo contract |
| Cùng scope, cùng instance ID, payload khác | Conflict hoặc lỗi tương đương theo policy |
| Khác tenant, trùng instance ID | Tài nguyên độc lập nếu khóa scope cho phép |
| Cùng request đến đồng thời | Chỉ một logical instance và một provider side effect |
| Retry sau khi broker restart | Đọc operation/instance từ database, không tạo lại mù quáng |

Fingerprint được tạo từ payload đã canonicalize và các thuộc tính có ảnh hưởng tới tài nguyên. Không phụ thuộc thứ tự key trong JSON. Phải xác định rõ field nào có ý nghĩa, field nào volatile và field nào bị bỏ qua. Không bỏ tenant/platform scope khỏi khóa idempotency.

### Provider idempotency

Broker idempotency không đủ nếu worker đã gọi provider tạo database nhưng crash trước khi lưu provider resource ID. Provider adapter nên gửi stable idempotency token hoặc external request ID nếu provider hỗ trợ. Nếu provider không hỗ trợ, gắn ownership marker/tag và thực hiện lookup/reconciliation trước khi tạo lại.

Không tạo token mới cho mỗi retry. Token phải ổn định theo operation intent.

### Transactional outbox

Lưu operation và outbox trong cùng transaction:

~~~text
BEGIN
  INSERT service_instance (state = PROVISIONING)
  INSERT service_operation (state = ACCEPTED)
  INSERT outbox_event (operation_id, event_type = PROVISION)
COMMIT
~~~

Outbox publisher có thể gửi event nhiều lần. Worker phải idempotent theo operation ID và claim/lease. Queue delivery thường là at-least-once; không giả định exactly-once.

## 10. Tra cứu instance và trạng thái operation

### Tra cứu qua repository

Use case nội bộ cần truy vấn theo toàn bộ scope:

~~~java
public InstanceView retrieve(
        TenantScope scope,
        String instanceId) {

    var instance = instanceRepository
            .find(scope.platformId(), scope.tenantId(), instanceId)
            .orElseThrow(ResourceNotFoundException::new);

    authorization.requireRead(scope, instance);
    return InstanceView.from(instance);
}
~~~

InstanceView chỉ chứa metadata an toàn: service ID, plan ID, instance state, timestamps, region, dung lượng và provider health summary nếu được phép. Không trả password, private endpoint credential, secret manager path hoặc provider access token.

### API quản trị nội bộ (nếu cần)

Nếu operator cần endpoint inventory, có thể thiết kế API riêng như:

~~~http
GET /internal/v1/service-instances/orders-db-01
Authorization: Bearer <admin-token>
X-Tenant-Scope: retail
~~~

Đây là API nội bộ minh họa, không thuộc OSB API. Nó cần authentication riêng, role/scope rõ ràng, audit access và response redaction. Không mở endpoint này cho platform caller chỉ vì họ có quyền gọi OSB provision.

### Polling last_operation

~~~http
GET /v2/service_instances/orders-db-01/last_operation?service_id=postgres-managed&plan_id=standard&operation=op-123
Authorization: Basic <broker-credential>
X-Broker-API-Version: 2.17
~~~

Response rút gọn:

~~~json
{
  "state": "in progress",
  "description": "Database is being provisioned"
}
~~~

Khi hoàn tất, state chuyển thành succeeded hoặc failed theo OSB contract. Description cần an toàn, không chứa SQL password, provider token hoặc stack trace.

### Last operation handler

~~~java
public LastOperationResult lastOperation(LastOperationQuery query) {
    var scope = authorization.resolvePlatformScope(query.authentication());
    var operation = operationRepository
            .findByScopeAndInstanceAndOperation(
                    scope, query.instanceId(), query.operationId())
            .orElseThrow(ResourceNotFoundException::new);

    authorization.requireRead(scope, operation);
    return lastOperationMapper.toOsbResult(operation);
}
~~~

Nếu query không có operation ID trong trường hợp contract cho phép, broker phải xác định operation phù hợp theo instance và operation type. Không trả một operation của tenant khác chỉ vì instance ID trùng.

## 11. Update plan và parameters

Update service instance cho phép thay đổi plan hoặc cấu hình theo capability đã công bố. Không phải mọi plan transition đều hợp lệ.

### Chính sách update

Ví dụ:

| Current plan | Target plan | Chính sách |
|---|---|---|
| development | standard | Cho phép nâng cấp |
| standard | production | Cho phép nếu quota và region hỗ trợ |
| production | standard | Chỉ cho phép nếu provider hỗ trợ downgrade an toàn |
| standard | development | Từ chối nếu mất dữ liệu/cấu hình không tương thích |

Các quy tắc thực tế phải dựa trên provider. Update có thể là resize storage, tăng connection limit, bật backup, thay đổi maintenance window hoặc nâng cấp plan.

### Validate update

1. Xác minh instance thuộc caller.
2. Xác minh instance đang AVAILABLE và không có operation xung đột.
3. Đọc current plan và target plan.
4. Kiểm tra plan transition.
5. Validate parameters và maintenance information.
6. Tạo update operation và outbox trong transaction.
7. Worker thực hiện thay đổi theo thứ tự an toàn.
8. Reconcile provider state.
9. Cập nhật plan/parameters và operation terminal trong transaction.

### Update application service

~~~java
public UpdateResult update(UpdateCommand command) {
    var instance = instanceRepository.requireOwned(
            command.scope(), command.instanceId());
    authorization.requireUpdate(command.scope(), instance);
    lifecycleGuard.requireNoConflictingOperation(instance);

    var targetPlan = planRegistry.requirePlan(
            instance.serviceId(), command.targetPlanId());
    planTransitionPolicy.validate(instance.planId(), targetPlan.id());
    var targetParameters = parameterValidator.validateUpdate(
            targetPlan, command.parameters());

    return operationCoordinator.acceptUpdate(
            instance, targetPlan, targetParameters, command);
}
~~~

Update API cần hỗ trợ các trường request theo schema OSB version đang dùng. Chỉ cập nhật field đã được validate; không ghi đè metadata ownership, platform scope hoặc provider resource identity từ request.

### Update có thể cần maintenance

Một số provider chỉ thực hiện resize hoặc engine upgrade trong maintenance window. Khi đó broker cần biểu diễn operation đang chờ lịch, giữ trạng thái non-terminal và trả last_operation là in progress. Không đánh dấu succeeded khi chỉ mới lên lịch.

## 12. Binding và unbinding

Provision tạo database; binding cấp quyền để một consumer kết nối tới database đó. Tách credentials theo binding giúp thu hồi một consumer mà không phải thay password của tất cả consumer khác.

### Create binding

1. Xác minh instance tồn tại, thuộc scope và AVAILABLE.
2. Kiểm tra offering/plan bindable.
3. Xác minh consumer context theo platform.
4. Kiểm tra binding ID và idempotency.
5. Provider tạo database principal hoặc credential riêng.
6. Secret manager lưu secret và trả credential reference.
7. Broker lưu binding record.
8. Response OSB trả credentials theo contract và policy.

Response ví dụ:

~~~json
{
  "credentials": {
    "hostname": "postgres.internal.example",
    "port": 5432,
    "database": "orders",
    "username": "orders_api_user",
    "password": "<generated-secret>",
    "sslmode": "verify-full"
  }
}
~~~

Không dùng credentials minh họa này trong môi trường thật. Không log response binding. Nếu platform yêu cầu binding response có credentials, broker phải trả đúng consumer credentials và không lấy secret từ một binding khác.

### Delete binding

1. Xác minh instance và binding thuộc scope.
2. Provider revoke/drop database principal hoặc token.
3. Secret manager revoke/expire secret.
4. Đánh dấu binding REVOKED/DELETED và lưu revoked_at.
5. Trả response theo OSB contract.

Nếu xóa Secret nhưng quên revoke principal tại database, credentials cũ vẫn có thể dùng được. Unbind phải hoàn tất side effect provider và xác minh revoke theo policy.

## 13. Deprovision và thu hồi tài nguyên

Deprovision là thao tác phá hủy tài nguyên; cần kiểm tra ownership, trạng thái, binding và policy bảo vệ dữ liệu.

### Luồng deprovision

1. Platform gửi DELETE với instance ID và service/plan identifiers.
2. Broker xác thực caller và tra instance trong tenant scope.
3. Kiểm tra idempotency và operation đang chạy.
4. Kiểm tra binding còn hoạt động; xử lý theo policy (từ chối, revoke hoặc cascade có kiểm soát).
5. Tạo deprovision operation và outbox.
6. Worker thu hồi database, principal, backup/replica theo retention policy.
7. Provider adapter xác minh tài nguyên đã xóa hoặc đã ở trạng thái absent.
8. Broker đánh dấu instance DELETED/tombstone và operation SUCCEEDED.

### Không coi 404 là luôn thành công

Provider trả 404 có thể nghĩa resource đã được xóa trước đó, nhưng cũng có thể do sai account/project/region. Chỉ coi là idempotent success khi broker xác minh đúng provider scope và owner marker. Nếu không xác định được resource, chuyển operation sang RECONCILING hoặc FAILED với safe description và tạo cảnh báo.

### Retention và backup

Deprovision cần xác định backup có bị xóa ngay, giữ theo retention hay chuyển sang archival. Chính sách này phải được mô tả trong plan/contract và được áp dụng nhất quán. Không xóa backup bắt buộc theo compliance chỉ vì nhận DELETE nếu policy quy định retention.

## 14. Worker, lease và reconciliation

Worker có thể crash ở bất kỳ thời điểm nào. Cần có cơ chế claim bền vững:

- Worker claim operation bằng atomic update hoặc row lock.
- Lease có thời hạn và heartbeat.
- Mỗi lần claim có fencing token/version.
- Worker chỉ cập nhật state nếu lease/token còn hợp lệ.
- Hết lease thì worker khác có thể tiếp quản.
- Retry dùng backoff và giới hạn attempt.
- Operation không rõ provider outcome chuyển sang RECONCILING.

### Recovery sau timeout

Ví dụ worker gọi provider tạo database, provider đã tạo thành công nhưng response bị mất. Broker không biết resource ID. Nếu gọi create lần nữa có thể tạo database thứ hai.

Recovery:

1. Tìm resource theo stable idempotency token hoặc owner marker.
2. Nếu tìm thấy đúng resource, cập nhật mapping provider_resource_id.
3. Nếu chưa thấy, kiểm tra provider consistency window và retry lookup.
4. Chỉ create lại khi đã xác minh chưa có resource tương ứng.
5. Nếu có nhiều resource cùng marker, đưa vào manual reconciliation và cảnh báo.

### Worker pseudocode

~~~java
public void process(String operationId) {
    var claim = operationRepository.claim(operationId, workerId, leaseDuration);
    if (claim.isEmpty()) {
        return;
    }

    var operation = claim.get().operation();
    try {
        var instance = instanceRepository.requireForOperation(operation);
        var result = providerAdapter.execute(
                operation, instance, claim.get().fencingToken());
        reconciliationService.verify(operation, result);
        operationCoordinator.markSucceeded(
                operation.id(), claim.get().fencingToken(), result);
    } catch (RetryableProviderException ex) {
        operationCoordinator.scheduleRetry(
                operation.id(), claim.get().fencingToken(), safeCategory(ex));
    } catch (UnknownProviderOutcomeException ex) {
        operationCoordinator.markReconciling(
                operation.id(), claim.get().fencingToken());
    } catch (PermanentProviderException ex) {
        operationCoordinator.markFailed(
                operation.id(), claim.get().fencingToken(), safeCategory(ex));
    }
}
~~~

Đây là pseudocode. Không truyền raw exception message vào API response. Worker phải kiểm tra lease/fencing token trước khi ghi kết quả; lỗi database khi commit terminal phải được phục hồi qua operation ledger.

## 15. Xác thực, phân quyền và bảo vệ dữ liệu

Broker cần xác thực platform caller theo cơ chế đã đăng ký. Sau authentication, resolve TenantScope từ danh tính tin cậy và kiểm tra quyền trên từng resource.

Các yêu cầu:

- Không tin tenant ID, organization ID, space ID hoặc namespace từ request nếu chưa xác minh.
- Mọi repository query phải có platform/tenant scope.
- Unique key phải phản ánh phạm vi định danh thật.
- Binding ID phải được kiểm tra cùng instance ID và tenant.
- Operation polling phải xác minh owner của operation.
- Provider credentials không lưu plaintext trong log/database.
- Secret manager access dùng least privilege.
- Endpoint inventory nội bộ có role riêng và audit.
- Error response không tiết lộ resource thuộc tenant khác.
- Metrics label không chứa tenant/instance/binding ID có cardinality lớn.

### Response redaction

Instance retrieval view có thể trả:

~~~json
{
  "instance_id": "orders-db-01",
  "service_id": "postgres-managed",
  "plan_id": "standard",
  "state": "AVAILABLE",
  "region": "region-a",
  "created_at": "2026-11-27T10:00:00Z",
  "updated_at": "2026-11-27T10:03:00Z"
}
~~~

Không trả password, token, secret value, private key hoặc raw provider configuration. Dữ liệu này chỉ được cung cấp trong binding response cho caller được phép và theo đúng contract.

## 16. Error mapping và hành vi retry

Broker cần phân biệt lỗi request, lỗi authorization, lỗi provider có thể retry và lỗi terminal.

| Nhóm lỗi | Ví dụ | Hành vi |
|---|---|---|
| Invalid request | service ID/plan ID sai, parameter không hợp lệ | Từ chối request, không tạo provider resource |
| Unauthorized | Credential broker sai | Từ chối tại security layer |
| Forbidden/out of scope | Caller không sở hữu instance | Từ chối, không tiết lộ metadata |
| Conflict | Instance đã tồn tại với fingerprint khác | Trả lỗi phù hợp, không ghi đè |
| Provider transient | Rate limit, network unavailable | Retry có backoff nếu operation được accept |
| Provider permanent | Quota vượt giới hạn, region không hỗ trợ | Terminal failed với safe description |
| Unknown outcome | Timeout sau side effect | Reconcile trước khi retry create |
| Internal failure | Database/outbox lỗi | Không trả accepted nếu transaction chưa commit |

Error description của OSB nên ngắn, có thể hành động và không chứa secret hoặc stack trace. Log nội bộ dùng error category, operation ID và correlation ID để điều tra.

## 17. Observability cho lifecycle

Capstone cần ít nhất các metric:

| Metric | Mục đích |
|---|---|
| provision duration histogram | Thời gian từ accepted_at tới terminal |
| operation count by state | Số operation QUEUED/RUNNING/RETRY_WAIT/RECONCILING |
| oldest incomplete operation age | Phát hiện operation bị kẹt |
| queue wait histogram | Phát hiện worker capacity thiếu |
| provider call duration | Theo dõi dependency |
| retry attempts counter | Phát hiện provider lỗi lặp |
| terminal failure counter | Theo dõi lỗi lifecycle |

Dùng Micrometer Timer/Counter/Gauge và Prometheus registry. Chỉ dùng tags hữu hạn như operation_type, provider, outcome, plan_tier nếu tập plan được kiểm soát. Không gắn instance ID, tenant ID, binding ID hoặc operation ID làm metric tag.

Structured log có thể chứa operation ID, instance ID, tenant reference đã được policy cho phép, attempt và error category. Không ghi credentials hoặc raw request/response binding.

Alert nên dựa trên SLO theo plan. Ví dụ oldest operation age vượt ngưỡng liên tục, queue backlog tăng trong khi throughput thấp, hoặc tỷ lệ provider timeout tăng. Ngưỡng phải được xác định từ dữ liệu vận hành thực tế.

## 18. Kiểm thử capstone

Chia test theo lớp và luôn xác minh side effect, không chỉ HTTP status.

### Catalog tests

- Catalog trả đúng service ID và plan ID.
- Plan bindable phản ánh khả năng thực tế.
- Thay đổi display name không làm thay ID.
- Không công bố plan mà provider adapter chưa hỗ trợ.

### Provision tests

- Request hợp lệ tạo instance PROVISIONING và operation.
- Request thiếu service ID/plan ID bị từ chối.
- Parameter ngoài giới hạn bị từ chối trước provider call.
- accepts_incomplete=true cho phép async operation nếu broker hỗ trợ.
- Không chấp nhận async nếu caller không cho phép và broker không thể hoàn tất sync.
- Retry cùng fingerprint không tạo instance/provider resource thứ hai.
- Cùng instance ID nhưng fingerprint khác bị conflict.
- Hai request đồng thời chỉ tạo một logical instance.
- Timeout sau provider side effect được reconcile.

### Retrieval và polling tests

- Tenant A đọc instance A thành công.
- Tenant A không đọc instance B.
- Response inventory không chứa secret.
- last_operation trả đúng operation của instance và scope.
- Polling nhiều lần không ghi thêm duration hoặc tạo operation mới.
- Unknown operation ID không tiết lộ operation của tenant khác.

### Update tests

- Update parameters hợp lệ cập nhật provider và repository.
- Plan transition không được hỗ trợ bị từ chối.
- Update khi instance đang deprovision bị conflict.
- Update async giữ operation IN_PROGRESS cho đến khi provider sẵn sàng.
- Worker cũ không ghi đè update mới hơn.

### Binding tests

- Binding tạo principal riêng.
- Retry cùng binding ID không tạo credential trùng.
- Binding của tenant khác không thể đọc.
- Response chỉ chứa credentials của binding được phép.
- Unbind revoke principal và secret.
- Credential cũ không còn truy cập được sau revoke.

### Deprovision tests

- Deprovision xóa provider resource đúng scope.
- Retry DELETE không tạo side effect nguy hiểm.
- Provider 404 chỉ được coi là success khi owner/scope đã được xác minh.
- Binding active được xử lý theo policy.
- Backup retention tuân thủ plan/policy.
- Sau khi hoàn tất, instance không còn xuất hiện trong active inventory.

### Failure và recovery tests

- Broker restart sau khi operation được accept.
- Worker crash sau khi provider tạo resource.
- Outbox publish lặp.
- Queue redelivery.
- Lease hết hạn và worker khác claim.
- Provider timeout với outcome chưa rõ.
- Database lỗi khi commit terminal state.
- Reconciliation tìm thấy resource mồ côi.

### Security và observability tests

- Broker authentication bắt buộc.
- Tenant spoofing không thay scope đã xác thực.
- Repository query luôn có tenant scope.
- Secret canary không xuất hiện trong log/trace/error.
- Metric không có ID động.
- Oldest age và backlog thay đổi theo state.
- Global gauge không bị nhân lên theo số replica.

## 19. Ví dụ kiểm thử HTTP theo luồng

Ví dụ dưới đây mô tả request sequence. Broker credentials và endpoint nội bộ cần thay bằng cấu hình của môi trường test.

### Đọc catalog

~~~bash
curl -u broker-user:broker-password \
  -H "X-Broker-API-Version: 2.17" \
  http://localhost:8080/v2/catalog
~~~

Xác nhận service postgres-managed và ba plan được trả về.

### Provision instance

~~~bash
curl -i -u broker-user:broker-password \
  -X PUT \
  -H "X-Broker-API-Version: 2.17" \
  -H "Content-Type: application/json" \
  "http://localhost:8080/v2/service_instances/orders-db-01?accepts_incomplete=true" \
  -d '{
    "service_id": "postgres-managed",
    "plan_id": "standard",
    "organization_guid": "org-retail",
    "space_guid": "space-orders",
    "parameters": {
      "region": "region-a",
      "database_name": "orders"
    }
  }'
~~~

Kỳ vọng: response async theo OSB contract, có operation reference phù hợp. Kiểm tra instance và operation đã được ghi bền vững trước khi worker thực hiện provider call.

### Poll operation

~~~bash
curl -u broker-user:broker-password \
  -H "X-Broker-API-Version: 2.17" \
  "http://localhost:8080/v2/service_instances/orders-db-01/last_operation?service_id=postgres-managed&plan_id=standard&operation=op-123"
~~~

Poll theo khoảng thời gian hợp lý, dùng backoff và dừng khi terminal. Không poll liên tục để tránh tạo tải không cần thiết lên broker.

### Update instance

~~~bash
curl -i -u broker-user:broker-password \
  -X PATCH \
  -H "X-Broker-API-Version: 2.17" \
  -H "Content-Type: application/json" \
  "http://localhost:8080/v2/service_instances/orders-db-01?accepts_incomplete=true" \
  -d '{
    "service_id": "postgres-managed",
    "plan_id": "production",
    "parameters": {
      "region": "region-a"
    }
  }'
~~~

Kỳ vọng: broker kiểm tra transition standard → production, ghi operation update và chỉ báo succeeded sau khi provider xác nhận cấu hình mới.

### Deprovision instance

~~~bash
curl -i -u broker-user:broker-password \
  -X DELETE \
  -H "X-Broker-API-Version: 2.17" \
  "http://localhost:8080/v2/service_instances/orders-db-01?service_id=postgres-managed&plan_id=production&accepts_incomplete=true"
~~~

Kỳ vọng: broker tạo deprovision operation, thu hồi binding/credentials theo policy, xóa provider resource và cập nhật instance tombstone khi hoàn tất.

Các lệnh dùng dữ liệu và credential giả. Không chạy trực tiếp trên production. Trong bài kiểm thử thật, lưu response operation ID rồi dùng đúng giá trị đó khi poll.

## 20. Trình tự triển khai theo milestone

| Milestone | Công việc | Kết quả cần có |
|---|---|---|
| M1 — Contract | Catalog, service ID, plan ID, capability | Catalog contract tests pass |
| M2 — Persistence | Instance, binding, operation, unique key | Repository tests pass |
| M3 — Provision | Validation, idempotency, outbox, provider adapter | Provision/retry tests pass |
| M4 — Async | Worker, lease, last_operation, recovery | Restart/replay tests pass |
| M5 — Retrieval | Inventory use case, scope, redaction | Cross-tenant tests pass |
| M6 — Update | Plan transition, provider update, reconcile | Update tests pass |
| M7 — Binding | Principal, Secret, bind/unbind | Credential lifecycle tests pass |
| M8 — Deprovision | Cleanup, retention, tombstone | Delete/retry tests pass |
| M9 — Operations | Metrics, dashboard, alerts, runbook | Monitoring tests pass |
| M10 — Integration | End-to-end flow và failure injection | Capstone acceptance pass |

Không nên bắt đầu bằng cách viết tất cả endpoint cùng lúc. Hoàn thành contract và state model trước, sau đó triển khai từng lifecycle use case. Mỗi milestone cần có test chứng minh side effect và recovery.

## 21. Definition of Done

Capstone được xem là hoàn thành về mặt kỹ thuật khi:

- [ ] Catalog hợp lệ và plan IDs ổn định.
- [ ] Provision tạo đúng một logical instance.
- [ ] Operation được lưu bền vững trước khi trả accepted.
- [ ] Async polling trả đúng last_operation state.
- [ ] Inventory retrieval có tenant authorization và redaction.
- [ ] Update áp dụng đúng plan transition và parameters.
- [ ] Binding tạo credentials riêng theo consumer.
- [ ] Unbind revoke credentials tại provider.
- [ ] Deprovision thu hồi provider resource và xử lý retention.
- [ ] Retry/replay không nhân đôi provider side effect.
- [ ] Restart worker/broker có thể phục hồi operation.
- [ ] Unknown provider outcome được reconcile.
- [ ] Tenant A không thể truy cập instance/binding/operation của tenant B.
- [ ] Secret không xuất hiện trong log, trace hoặc error response.
- [ ] Metrics phản ánh provision duration, backlog và oldest age.
- [ ] Integration tests bao phủ success, failure, timeout và concurrency.
- [ ] Runbook mô tả cách điều tra operation stuck và provider cleanup.

## Kết luận

Một service broker hoàn chỉnh cần quản lý lifecycle như một chuỗi nghiệp vụ bền vững, bắt đầu từ catalog và provision, tiếp tục qua operation polling, inventory retrieval, update và kết thúc bằng deprovision. Spring Cloud Open Service Broker cung cấp protocol adapter; application/domain layer quản lý instance, binding, operation và idempotency; provider adapter thực hiện side effect; worker và reconciliation bảo đảm hệ thống phục hồi sau timeout hoặc restart. Khi tách rõ OSB last_operation với API truy xuất inventory nội bộ, giữ tenant scope ở mọi truy vấn, quản lý credentials theo binding và kiểm thử cả retry lẫn failure path, broker có thể cung cấp trải nghiệm marketplace đáng tin cậy cho nhiều platform và khách hàng.

## Tài liệu tham khảo

- [Open Service Broker API Specification](https://github.com/cloudfoundry/servicebroker/blob/master/spec.md)
- [Spring Cloud Open Service Broker Reference](https://docs.spring.io/spring-cloud-open-service-broker/reference/)
- [Spring Boot Reference Documentation](https://docs.spring.io/spring-boot/reference/)
- [Micrometer Documentation](https://docs.micrometer.io/micrometer/reference/)
- [Prometheus Documentation](https://prometheus.io/docs/introduction/overview/)
