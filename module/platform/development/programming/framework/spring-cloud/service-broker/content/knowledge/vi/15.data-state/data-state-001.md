# Mô hình lưu trữ cho instance, binding, operation và tài nguyên bên ngoài

Một service broker cần lưu được mối quan hệ giữa service instance mà platform quản lý, các binding cấp cho consumer, những operation đang hoặc đã chạy và tài nguyên thực tế do provider tạo ra. Nếu chỉ lưu một trạng thái trên service instance hoặc chỉ giữ provider resource ID trong bộ nhớ, broker sẽ khó phục hồi sau restart, xử lý request lặp, theo dõi nhiều binding và đối chiếu trạng thái khi provider trả kết quả không đồng bộ.

Trong module **SPRING_CLOUD_SERVICE_BROKER**, mô hình dữ liệu là nền tảng cho các thao tác Open Service Broker API (OSB API): catalog, provision, update, bind, unbind, deprovision và polling last_operation. Spring Cloud Open Service Broker (SCOSB) cung cấp request/response model và service abstraction; ứng dụng broker vẫn cần thiết kế kho lưu trữ để duy trì trạng thái vòng đời và ánh xạ ID của platform sang tài nguyên provider.

Bài học này xây dựng mô hình lưu trữ gồm bốn nhóm dữ liệu chính: **service instance**, **service binding**, **operation** và **external resource**. Ngoài ra, bài học trình bày outbox cho xử lý bất đồng bộ, quan hệ khóa, transaction, idempotency, bảo vệ secret, tenant isolation, index và chiến lược phục hồi.

## 1. Vì sao cần tách các nhóm dữ liệu?

Bốn khái niệm có vòng đời và phạm vi khác nhau:

| Đối tượng | Đại diện cho | Ví dụ |
|---|---|---|
| Service instance | Dịch vụ mà platform yêu cầu broker cấp phát | Một database PostgreSQL có ID instance-100 |
| Service binding | Quyền truy cập của một consumer vào instance | Credential riêng cho ứng dụng orders-api |
| Operation | Một lần thực hiện nghiệp vụ vòng đời | Provision, update hoặc deprovision đang chạy |
| External resource | Tài nguyên thật ở hệ thống provider | Database ID, cluster, queue, user hoặc volume |

Một service instance có thể có nhiều binding. Ví dụ, database orders được bind cho ứng dụng API, worker và một công cụ báo cáo. Mỗi binding có thể có user, credential và quyền khác nhau.

Một service instance cũng có thể trải qua nhiều operation theo thời gian: provision, một vài lần update và cuối cùng là deprovision. Vì vậy, operation không nên chỉ là một cột trạng thái duy nhất trên instance. Broker cần lưu lịch sử hoặc ít nhất lưu từng operation với ID riêng để platform polling đúng thao tác.

Một instance còn có thể được ánh xạ tới nhiều tài nguyên provider. Ví dụ, một offering database có thể tạo database, network policy, backup schedule và một secret. Do đó, không phải lúc nào một instance cũng có đúng một provider resource ID.

## 2. Bức tranh quan hệ giữa các bảng

Mô hình quan hệ tổng quát:

~~~mermaid
erDiagram
    SERVICE_INSTANCE ||--o{ SERVICE_BINDING : owns
    SERVICE_INSTANCE ||--o{ OPERATION : tracks
    SERVICE_INSTANCE ||--o{ EXTERNAL_RESOURCE : maps
    OPERATION ||--o{ OUTBOX_EVENT : publishes

    SERVICE_INSTANCE {
        string instance_id PK
        string tenant_id
        string service_id
        string plan_id
        string state
        int version
    }
    SERVICE_BINDING {
        string binding_id PK
        string instance_id FK
        string consumer_id
        string state
        string credentials_secret_ref
    }
    OPERATION {
        string operation_id PK
        string instance_id FK
        string operation_type
        string state
        string provider_operation_id
    }
    EXTERNAL_RESOURCE {
        string resource_id PK
        string instance_id FK
        string provider_id
        string external_resource_id
        string state
    }
    OUTBOX_EVENT {
        string event_id PK
        string operation_id FK
        string event_type
        string publish_state
    }
~~~

Các cardinality quan trọng:

- Một service instance có thể có zero hoặc nhiều service binding.
- Một service instance có thể có nhiều operation trong suốt vòng đời.
- Một service instance có thể liên kết với một hoặc nhiều external resource.
- Một operation có thể phát sinh một hoặc nhiều outbox event.
- Một binding thường tham chiếu đến một secret hoặc một phiên bản secret chứa credentials của binding đó.

Sơ đồ chỉ thể hiện các quan hệ logic. Trong triển khai thật, secret manager thường là hệ thống bên ngoài database; bảng binding chỉ lưu đường dẫn và phiên bản secret, không lưu nội dung bí mật.

## 3. Bảng service_instance

Bảng **service_instance** lưu trạng thái authoritative của một service instance trong broker. Đây là nơi broker tra cứu khi nhận request update, bind, unbind hoặc deprovision.

Các trường gợi ý:

| Trường | Ý nghĩa |
|---|---|
| instance_id | ID do platform cấp, khóa chính trong phạm vi broker |
| tenant_id | Organization, project hoặc tenant sở hữu instance |
| service_id | ID service offering trong catalog |
| plan_id | Plan hiện tại của instance |
| plan_version | Phiên bản định nghĩa plan đã được dùng khi provision hoặc update |
| state | Trạng thái vòng đời nội bộ của instance |
| parameters | Cấu hình đã được xác thực, không chứa secret plaintext |
| context | Ngữ cảnh platform đã được lọc và chuẩn hóa |
| provider_id | Nhà cung cấp hoặc adapter được sử dụng |
| version | Version để optimistic locking |
| created_at, updated_at | Thời điểm tạo và cập nhật |
| deleted_at | Thời điểm kết thúc nếu cần lưu tombstone |

Ví dụ PostgreSQL:

~~~sql
CREATE TABLE service_instance (
    instance_id VARCHAR(128) PRIMARY KEY,
    tenant_id VARCHAR(128) NOT NULL,
    service_id VARCHAR(128) NOT NULL,
    plan_id VARCHAR(128) NOT NULL,
    plan_version VARCHAR(64),
    state VARCHAR(32) NOT NULL,
    parameters JSONB NOT NULL DEFAULT '{}'::jsonb,
    context JSONB NOT NULL DEFAULT '{}'::jsonb,
    provider_id VARCHAR(128) NOT NULL,
    version BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ,
    CONSTRAINT chk_instance_state CHECK (
        state IN (
            'PROVISIONING',
            'READY',
            'UPDATING',
            'DEPROVISIONING',
            'DEPROVISIONED',
            'FAILED'
        )
    )
);

CREATE INDEX idx_instance_tenant_state
    ON service_instance(tenant_id, state);

CREATE INDEX idx_instance_service_plan
    ON service_instance(service_id, plan_id);
~~~

JSONB là kiểu dữ liệu riêng của PostgreSQL. Với database khác, có thể dùng JSON, CLOB hoặc các bảng con tùy khả năng truy vấn và yêu cầu migration.

### Vì sao cần lưu plan_version?

Catalog có thể thay đổi theo thời gian. Plan small hôm nay có thể có quota 100 GB, nhưng sau một lần phát hành catalog, cấu hình plan có thể thay đổi. Nếu instance cũ chỉ lưu plan_id, broker có thể không biết chính xác chính sách hoặc cấu hình đã được áp dụng khi tạo instance.

Có thể lưu snapshot tối thiểu của plan hoặc một plan_version bất biến. Khi update, broker ghi lại plan version mới sau khi provider xác nhận thay đổi. Snapshot giúp giải thích lịch sử, xử lý fetch và deprovision đúng theo tài nguyên đã cấp.

### Lưu parameters như thế nào?

Chỉ lưu các tham số đã được xác thực và chuẩn hóa. Tránh lưu nguyên request HTTP vì request có thể chứa field không được phép, dữ liệu thừa hoặc secret. Nếu một tham số nhạy cảm bắt buộc phải dùng lại khi worker xử lý, hãy lưu nó trong secret manager và chỉ lưu reference trong JSON.

Không dùng JSON làm nơi chứa mọi dữ liệu một cách tùy tiện. Những field thường xuyên cần lọc, join hoặc áp dụng unique constraint như tenant, service ID, plan ID và state nên có cột riêng.

## 4. Bảng service_binding

Bảng **service_binding** biểu diễn một consumer được cấp quyền sử dụng service instance. Binding có ID riêng do platform gửi và phải gắn với đúng instance.

Các trường gợi ý:

| Trường | Ý nghĩa |
|---|---|
| binding_id | ID binding do platform cấp |
| instance_id | Service instance sở hữu binding |
| tenant_id | Tenant sở hữu consumer và binding |
| consumer_id | Ứng dụng hoặc consumer được cấp quyền |
| state | Trạng thái binding |
| credentials_secret_ref | Tham chiếu secret chứa credentials |
| credential_version | Phiên bản credentials hiện tại |
| provider_principal_id | User/role được tạo ở provider nếu có |
| metadata | Metadata binding không nhạy cảm |
| created_at, updated_at, revoked_at | Mốc thời gian vòng đời |

Ví dụ schema:

~~~sql
CREATE TABLE service_binding (
    binding_id VARCHAR(128) PRIMARY KEY,
    instance_id VARCHAR(128) NOT NULL
        REFERENCES service_instance(instance_id),
    tenant_id VARCHAR(128) NOT NULL,
    consumer_id VARCHAR(256) NOT NULL,
    state VARCHAR(32) NOT NULL,
    credentials_secret_ref VARCHAR(512),
    credential_version BIGINT NOT NULL DEFAULT 1,
    provider_principal_id VARCHAR(256),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at TIMESTAMPTZ,
    CONSTRAINT chk_binding_state CHECK (
        state IN ('CREATING', 'ACTIVE', 'REVOKING', 'REVOKED', 'FAILED')
    )
);

CREATE INDEX idx_binding_instance_state
    ON service_binding(instance_id, state);

CREATE INDEX idx_binding_tenant_consumer
    ON service_binding(tenant_id, consumer_id);
~~~

Trong hệ thống có nhiều tenant, mọi truy vấn binding cần ràng buộc tenant theo caller đã xác thực. Không chỉ tìm theo binding ID rồi trả kết quả. Truy vấn an toàn thường kết hợp **instance_id**, **binding_id** và tenant scope.

Nếu database sử dụng composite key, có thể chọn khóa chính (instance_id, binding_id) thay cho binding ID toàn cục. Dù chọn cách nào, broker phải bảo đảm binding không thể bị gắn nhầm sang instance khác.

### Vì sao mỗi binding cần credential riêng?

Nếu nhiều ứng dụng dùng chung credential quản trị của provider, broker không thể thu hồi quyền của một ứng dụng độc lập. Khi một consumer ngừng sử dụng service, broker cần unbind đúng user hoặc role của binding đó mà không ảnh hưởng đến consumer còn lại.

Vì vậy, một binding thường có credential hoặc principal riêng, với quyền tối thiểu. Bản ghi binding lưu quan hệ đến credential, còn nội dung credential nằm trong secret manager.

## 5. Bảng operation

Bảng **operation** ghi nhận từng yêu cầu vòng đời mà broker cần theo dõi. Đây là nguồn dữ liệu để triển khai endpoint **last_operation** cho provision, update và deprovision.

Các trường gợi ý:

| Trường | Ý nghĩa |
|---|---|
| operation_id | ID riêng của operation |
| instance_id | Instance liên quan |
| operation_type | PROVISION, UPDATE hoặc DEPROVISION |
| state | Trạng thái nội bộ của operation |
| source_plan_id | Plan trước update nếu có |
| target_plan_id | Plan đích nếu có |
| request_fingerprint | Fingerprint request đã chuẩn hóa để nhận diện retry |
| idempotency_key | Khóa idempotency nếu broker sử dụng |
| provider_operation_id | Mã operation do provider trả về |
| attempt_count | Số lần worker thực hiện |
| last_error_code | Mã lỗi đã chuẩn hóa |
| description | Mô tả không chứa secret |
| started_at, completed_at | Thời điểm bắt đầu và kết thúc |
| version | Version để kiểm soát cập nhật đồng thời |

Ví dụ schema:

~~~sql
CREATE TABLE service_instance_operation (
    operation_id VARCHAR(128) PRIMARY KEY,
    instance_id VARCHAR(128) NOT NULL
        REFERENCES service_instance(instance_id),
    operation_type VARCHAR(32) NOT NULL,
    state VARCHAR(40) NOT NULL,
    source_plan_id VARCHAR(128),
    target_plan_id VARCHAR(128),
    request_fingerprint VARCHAR(128),
    idempotency_key VARCHAR(256),
    provider_operation_id VARCHAR(256),
    attempt_count INTEGER NOT NULL DEFAULT 0,
    last_error_code VARCHAR(128),
    description VARCHAR(500),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    version BIGINT NOT NULL DEFAULT 0,
    CONSTRAINT chk_operation_type CHECK (
        operation_type IN ('PROVISION', 'UPDATE', 'DEPROVISION')
    ),
    CONSTRAINT chk_operation_state CHECK (
        state IN (
            'QUEUED',
            'IN_PROGRESS',
            'SUCCEEDED',
            'FAILED',
            'RECONCILIATION_REQUIRED'
        )
    )
);

CREATE INDEX idx_operation_instance_created
    ON service_instance_operation(instance_id, created_at DESC);

CREATE INDEX idx_operation_state_updated
    ON service_instance_operation(state, updated_at);
~~~

### Vì sao operation không nên chỉ là cột trên instance?

Một instance có thể đã provision thành công, update thành công nhiều lần rồi deprovision. Nếu chỉ lưu last_operation_state trên service_instance, thông tin của thao tác trước sẽ bị ghi đè. Khi platform gửi query parameter operation để hỏi kết quả của một request cũ, broker không thể trả lời chính xác.

Bảng operation riêng cho phép:

- Tra cứu đúng operation theo instance_id và operation_id.
- Trả lại kết quả khi platform retry request hoặc polling muộn.
- Phục hồi công việc sau khi broker restart.
- Đối chiếu với provider operation ID.
- Lưu lịch sử và phục vụ điều tra sự cố.
- Phân biệt lỗi của một operation với trạng thái tổng thể của instance.

Có thể lưu thêm current_operation_id trên service_instance để xác định thao tác đang chiếm quyền cập nhật instance. Khi operation kết thúc, cập nhật con trỏ và version trong cùng transaction.

## 6. Bảng external_resource

Service instance trong broker là định danh logic mà platform biết. Provider có thể tạo một hoặc nhiều tài nguyên với ID hoàn toàn khác. Broker cần lưu ánh xạ giữa hai thế giới.

Ví dụ:

- Platform gửi instance_id=instance-100.
- Broker gọi API của cloud database provider.
- Provider trả database_id=db-9a8f.
- Broker lưu ánh xạ instance-100 sang db-9a8f.

Không dùng provider resource ID thay cho instance ID. Platform chỉ biết ID do nó cấp; broker phải duy trì mapping để xử lý request sau này.

Một bảng external_resource có thể gồm:

| Trường | Ý nghĩa |
|---|---|
| resource_id | ID nội bộ của mapping |
| instance_id | Service instance sở hữu tài nguyên |
| provider_id | Provider adapter hoặc nhà cung cấp |
| provider_account_id | Account/project ở provider |
| external_resource_id | ID thật do provider trả về |
| resource_type | DATABASE, USER, QUEUE, BUCKET, VOLUME... |
| state | Trạng thái quan sát được của tài nguyên |
| attributes | Metadata không nhạy cảm |
| last_observed_at | Thời điểm gần nhất đối chiếu provider |

Schema ví dụ:

~~~sql
CREATE TABLE external_resource (
    resource_id VARCHAR(128) PRIMARY KEY,
    instance_id VARCHAR(128) NOT NULL
        REFERENCES service_instance(instance_id),
    provider_id VARCHAR(128) NOT NULL,
    provider_account_id VARCHAR(256) NOT NULL,
    external_resource_id VARCHAR(512) NOT NULL,
    resource_type VARCHAR(64) NOT NULL,
    state VARCHAR(32) NOT NULL,
    attributes JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_observed_at TIMESTAMPTZ,
    CONSTRAINT uq_provider_resource UNIQUE (
        provider_id,
        provider_account_id,
        external_resource_id
    )
);

CREATE INDEX idx_external_resource_instance
    ON external_resource(instance_id, resource_type);
~~~

Unique constraint ngăn cùng một tài nguyên provider bị ánh xạ nhầm cho hai instance trong cùng provider account. Nếu provider cho phép cùng external ID ở các account khác nhau, provider_account_id là một phần quan trọng của khóa duy nhất.

Không lưu access token hay secret quản trị provider trong bảng này. Nếu provider client cần credential, hãy tham chiếu secret riêng được quản lý bởi secret store.

## 7. Outbox để đồng bộ transaction và background worker

Khi một request cần xử lý bất đồng bộ, broker thường phải vừa ghi operation vào database vừa gửi công việc đến queue. Nếu ghi database thành công nhưng publish message thất bại, operation có thể bị treo. Nếu message được gửi trước nhưng transaction database rollback, worker có thể chạy một công việc không có operation record hợp lệ.

Mẫu **transactional outbox** giải quyết khoảng trống này bằng cách ghi operation và event vào cùng transaction:

~~~sql
CREATE TABLE broker_outbox (
    event_id VARCHAR(128) PRIMARY KEY,
    operation_id VARCHAR(128) NOT NULL
        REFERENCES service_instance_operation(operation_id),
    event_type VARCHAR(128) NOT NULL,
    payload JSONB NOT NULL,
    publish_state VARCHAR(24) NOT NULL DEFAULT 'PENDING',
    attempt_count INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at TIMESTAMPTZ
);

CREATE INDEX idx_outbox_pending
    ON broker_outbox(publish_state, next_attempt_at);
~~~

Luồng xử lý:

1. Mở transaction database.
2. Tạo hoặc cập nhật operation.
3. Cập nhật instance sang trạng thái tương ứng, ví dụ PROVISIONING.
4. Ghi outbox event chứa operation ID và loại công việc.
5. Commit transaction.
6. Publisher đọc event PENDING và gửi message tới queue.
7. Sau khi broker message xác nhận, publisher đánh dấu event đã publish.
8. Worker nhận message, claim operation và thực hiện provider call.

Outbox publisher có thể gửi lại event nếu không nhận được xác nhận. Vì vậy, worker vẫn phải idempotent; outbox giúp tránh mất event nhưng không bảo đảm message chỉ xuất hiện đúng một lần.

Không đưa credentials hoặc raw parameters chứa secret vào payload outbox. Message nên mang ID và thông tin tham chiếu đủ để worker tải dữ liệu cần thiết từ kho lưu trữ an toàn.

## 8. Mô hình trạng thái phải tách theo từng đối tượng

Không nên dùng một field status chung cho instance, binding, operation và provider resource. Mỗi đối tượng có vòng đời riêng.

### Trạng thái service instance

| Trạng thái nội bộ | Ý nghĩa |
|---|---|
| PROVISIONING | Đang tạo tài nguyên |
| READY | Instance sẵn sàng phục vụ |
| UPDATING | Đang thay đổi cấu hình hoặc plan |
| DEPROVISIONING | Đang giải phóng tài nguyên |
| DEPROVISIONED | Đã hoàn tất giải phóng |
| FAILED | Thao tác vòng đời kết thúc với lỗi cần xử lý |

### Trạng thái binding

| Trạng thái nội bộ | Ý nghĩa |
|---|---|
| CREATING | Đang tạo quyền truy cập |
| ACTIVE | Binding hoạt động |
| REVOKING | Đang thu hồi quyền |
| REVOKED | Đã thu hồi |
| FAILED | Tạo hoặc thu hồi binding gặp lỗi |

### Trạng thái operation

| Trạng thái nội bộ | Ý nghĩa |
|---|---|
| QUEUED | Đã ghi nhận, chờ worker |
| IN_PROGRESS | Worker hoặc provider đang xử lý |
| SUCCEEDED | Operation hoàn tất |
| FAILED | Operation thất bại |
| RECONCILIATION_REQUIRED | Kết quả chưa chắc chắn, cần đối chiếu |

### Trạng thái external resource

| Trạng thái nội bộ | Ý nghĩa |
|---|---|
| PENDING | Đã yêu cầu tạo nhưng provider chưa xác nhận |
| ACTIVE | Provider xác nhận tài nguyên hoạt động |
| UPDATING | Đang thay đổi tài nguyên |
| DELETING | Đang xóa |
| DELETED | Đã xóa |
| UNKNOWN | Broker chưa xác định được trạng thái thật |

Khi trả last_operation cho platform, broker ánh xạ các trạng thái operation nội bộ sang các giá trị OSB API được phép như **in progress**, **succeeded** và **failed**. Không trả nguyên các trạng thái nội bộ như QUEUED hoặc RECONCILIATION_REQUIRED vào field state của response.

## 9. Quan hệ giữa trạng thái instance và operation

Operation phản ánh tiến độ của một yêu cầu; instance phản ánh trạng thái vòng đời tổng thể. Hai trạng thái liên quan nhưng không đồng nhất.

Ví dụ khi provision:

~~~mermaid
stateDiagram-v2
    [*] --> PROVISIONING
    PROVISIONING --> READY: Provision operation succeeded
    PROVISIONING --> FAILED: Terminal provision failure
    READY --> UPDATING: Update operation accepted
    UPDATING --> READY: Update operation succeeded
    UPDATING --> FAILED: Update cannot be recovered
    READY --> DEPROVISIONING: Delete accepted
    DEPROVISIONING --> DEPROVISIONED: Deprovision succeeded
    DEPROVISIONING --> FAILED: Deprovision failed
~~~

Khi một operation chuyển sang SUCCEEDED, worker thường cập nhật trạng thái instance và operation trong cùng transaction sau khi provider đã xác nhận kết quả. Ví dụ:

- Provision thành công: operation = SUCCEEDED, instance = READY, external resource = ACTIVE.
- Update thành công: operation = SUCCEEDED, instance = READY, plan/configuration = giá trị mới.
- Deprovision thành công: operation = SUCCEEDED, instance = DEPROVISIONED, external resource = DELETED.

Nếu provider đã hoàn thành nhưng transaction lưu trạng thái broker thất bại, không được trả kết quả thành công giả. Operation cần được phục hồi hoặc đưa sang RECONCILIATION_REQUIRED để đối chiếu provider.

## 10. Khóa, quan hệ và quy tắc toàn vẹn dữ liệu

Các constraint trong database giúp broker ngăn trạng thái sai ngay cả khi có nhiều replica xử lý đồng thời.

Một số quy tắc quan trọng:

- service_binding.instance_id phải tham chiếu tới một service instance hợp lệ.
- operation.instance_id phải tham chiếu tới instance sở hữu operation.
- external_resource.instance_id phải tham chiếu tới instance logic đã lưu.
- binding_id không được tái sử dụng cho một binding khác trong phạm vi khóa đã chọn.
- External resource phải duy nhất theo provider, provider account và external resource ID.
- Operation ID phải duy nhất và không thay đổi trong suốt vòng đời operation.
- Các trường state phải nằm trong tập giá trị được định nghĩa.
- Không xóa instance khi vẫn còn binding hoặc operation chưa kết thúc nếu chính sách vòng đời không cho phép.

### Xóa logic và tombstone

Khi deprovision thành công, có thể giữ bản ghi instance ở trạng thái DEPROVISIONED thay vì xóa vật lý ngay. Bản ghi tombstone giúp:

- Nhận diện request retry đến muộn.
- Trả lỗi phù hợp khi platform gọi lại instance đã xóa.
- Ngăn vô tình tái sử dụng instance ID.
- Giữ quan hệ với operation và audit history.
- Phục vụ đối chiếu khi provider còn tài nguyên chưa được giải phóng.

Thời hạn lưu tombstone và lịch sử operation cần theo chính sách retention. Không nên xóa binding đang ACTIVE hoặc operation đang chạy chỉ để dọn dữ liệu.

## 11. Kiểm soát cập nhật đồng thời bằng version

Hai request có thể cùng đọc một instance ở version 5 rồi cùng cập nhật. Nếu không có concurrency control, request thứ hai có thể ghi đè kết quả của request thứ nhất.

Có thể dùng optimistic locking:

~~~sql
UPDATE service_instance
SET state = 'UPDATING',
    version = version + 1,
    updated_at = now()
WHERE instance_id = :instance_id
  AND version = :expected_version
  AND state = 'READY';
~~~

Nếu số dòng được cập nhật bằng 0, có thể instance đã thay đổi hoặc không còn ở trạng thái READY. Broker cần đọc lại trạng thái và trả lỗi xung đột phù hợp thay vì tiếp tục provider call.

Trong JPA có thể dùng @Version:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Version;

@Entity
public class ServiceInstanceEntity {

    @Id
    private String instanceId;

    private String tenantId;
    private String serviceId;
    private String planId;
    private String state;

    @Version
    private long version;
}
~~~

Đây là ví dụ entity tối giản. Nếu dùng Spring Data R2DBC, cơ chế versioning và câu lệnh update cần được triển khai theo repository tương ứng; không giả định annotation JPA tự hoạt động với R2DBC.

Đối với operation, worker cần cơ chế claim hoặc lease để hai worker không cùng thực hiện một side effect. Có thể dùng conditional update từ QUEUED sang IN_PROGRESS, lease owner, lease expiry và fencing token. Khi lease hết hạn, worker mới phải xác minh provider state trước khi tiếp tục.

## 12. Idempotency và fingerprint request

Platform có thể gửi lại provision hoặc update sau timeout. Broker cần xác định request đó là retry của operation cũ hay một yêu cầu mới.

Có thể lưu:

- Idempotency key nếu client/platform cung cấp hoặc broker tạo theo hợp đồng.
- Request fingerprint từ service ID, plan ID, operation type và parameters đã chuẩn hóa.
- Instance ID và operation ID.
- Provider operation ID.
- Trạng thái operation và kết quả đã ghi nhận.

Một constraint gợi ý:

~~~sql
CREATE UNIQUE INDEX uq_operation_instance_idempotency
    ON service_instance_operation(instance_id, idempotency_key)
    WHERE idempotency_key IS NOT NULL;
~~~

Đây là partial index theo cú pháp PostgreSQL. Database khác có thể cần cách biểu diễn tương đương.

Khi nhận request trùng:

1. Tra cứu operation theo instance và idempotency key.
2. So sánh fingerprint với request đã lưu.
3. Nếu fingerprint giống nhau và operation đang chạy, trả lại operation hiện có.
4. Nếu fingerprint giống nhau và operation đã kết thúc, trả kết quả phù hợp theo OSB API.
5. Nếu key giống nhưng fingerprint khác, từ chối xung đột thay vì âm thầm dùng lại operation.

Không lưu fingerprint của raw JSON theo thứ tự byte nếu cùng một object có thể được serialize với thứ tự key khác nhau. Nên chuẩn hóa dữ liệu trước khi tính fingerprint. Không đưa secret plaintext vào fingerprint dễ quan sát hoặc log; nếu cần xác định request có cùng secret, sử dụng cách so sánh an toàn phù hợp với threat model.

## 13. Bảo vệ secret và dữ liệu nhạy cảm

Broker xử lý nhiều loại dữ liệu khác nhau. Không nên áp dụng cùng một chính sách lưu trữ cho metadata công khai, cấu hình và secret.

| Loại dữ liệu | Ví dụ | Cách lưu |
|---|---|---|
| Metadata | service ID, plan ID, mô tả, state | Database thông thường |
| Cấu hình không nhạy cảm | storage size, region, backup flag | Cột hoặc JSON đã xác thực |
| Thông tin định danh provider | provider resource ID, account ID | Database với quyền truy cập giới hạn |
| Credentials binding | username, password, token | Secret manager/KMS hoặc kho mã hóa chuyên biệt |
| Provider credential | API key, client secret, private key | Secret manager, không lưu trong entity/log |
| Audit | actor, operation ID, kết quả, timestamp | Audit store với retention và access control |

Các nguyên tắc cần áp dụng:

- Không lưu password hoặc access token plaintext trong JSON parameters, metadata hay outbox payload.
- Chỉ lưu secret reference và version trong binding record.
- Mã hóa dữ liệu nhạy cảm khi truyền và khi lưu.
- Giới hạn service identity nào được đọc từng secret.
- Audit việc đọc và rotate secret nhưng không ghi nội dung secret vào audit log.
- Mask các field nhạy cảm trong exception và tracing.
- Xóa hoặc revoke secret khi binding bị unbind theo chính sách.
- Không trả provider credential trong GET binding hoặc response khác của OSB API.

Nếu broker cần hỗ trợ bindings_retrievable, phải thiết kế cách đọc lại credential hiện hành một cách an toàn. Chỉ lưu hash một chiều không thể khôi phục password để trả lại platform.

## 14. Tenant isolation và quyền truy cập dữ liệu

Một broker có thể phục vụ nhiều organization hoặc tenant. Do đó, việc tra cứu bằng ID đơn lẻ không đủ bảo đảm quyền truy cập.

Ví dụ, request tìm binding cần ràng buộc:

~~~sql
SELECT b.*
FROM service_binding b
JOIN service_instance i
  ON i.instance_id = b.instance_id
WHERE b.instance_id = :instance_id
  AND b.binding_id = :binding_id
  AND b.tenant_id = :authenticated_tenant_id
  AND i.tenant_id = :authenticated_tenant_id;
~~~

authenticated_tenant_id phải đến từ danh tính đã xác thực hoặc ngữ cảnh tin cậy do platform/gateway cung cấp và broker đã xác minh. Không dùng một tenant ID tùy ý trong request body làm căn cứ phân quyền.

Với truy vấn operation và external resource cũng áp dụng nguyên tắc tương tự. Mọi API quản trị cần xác minh caller có quyền trên instance, binding và tenant tương ứng. UUID khó đoán không thay thế authorization.

## 15. Mapping dữ liệu trong Java/Spring

Có thể biểu diễn các bản ghi domain bằng Java record hoặc entity tùy công nghệ persistence. Ví dụ mô hình domain rút gọn:

~~~java
import java.time.Instant;
import java.util.Map;

public record ServiceInstanceRecord(
        String instanceId,
        String tenantId,
        String serviceId,
        String planId,
        String planVersion,
        InstanceState state,
        Map<String, Object> parameters,
        String providerId,
        long version,
        Instant createdAt,
        Instant updatedAt
) {
}

public record OperationRecord(
        String operationId,
        String instanceId,
        OperationType operationType,
        OperationState state,
        String providerOperationId,
        String requestFingerprint,
        int attemptCount,
        Instant createdAt,
        Instant updatedAt,
        Instant completedAt
) {
}

public record ExternalResourceRecord(
        String resourceId,
        String instanceId,
        String providerId,
        String providerAccountId,
        String externalResourceId,
        String resourceType,
        ResourceState state
) {
}
~~~

Các enum nội bộ:

~~~java
public enum InstanceState {
    PROVISIONING,
    READY,
    UPDATING,
    DEPROVISIONING,
    DEPROVISIONED,
    FAILED
}

public enum OperationType {
    PROVISION,
    UPDATE,
    DEPROVISION
}

public enum OperationState {
    QUEUED,
    IN_PROGRESS,
    SUCCEEDED,
    FAILED,
    RECONCILIATION_REQUIRED
}

public enum ResourceState {
    PENDING,
    ACTIVE,
    UPDATING,
    DELETING,
    DELETED,
    UNKNOWN
}
~~~

Các record là mô hình minh họa, không phải model OSB API. Tách domain model khỏi request/response model của SCOSB giúp broker không phụ thuộc trực tiếp vào cấu trúc HTTP khi lưu dữ liệu. Mapper sẽ chuyển request đã xác thực thành command/domain object và chuyển kết quả nghiệp vụ thành response framework.

Với dữ liệu binding, nên dùng một record riêng chứa credentialsSecretRef thay vì đưa map credentials vào object được serialize hoặc ghi log.

## 16. Giao dịch khi provision một instance

Provision là ví dụ rõ nhất cho việc nhiều bảng phải được cập nhật phối hợp.

Một luồng xử lý gợi ý:

1. Xác thực caller và validate service ID, plan ID, parameters.
2. Tạo service_instance ở trạng thái PROVISIONING.
3. Tạo operation PROVISION ở trạng thái QUEUED hoặc IN_PROGRESS.
4. Ghi outbox event trong cùng transaction.
5. Commit transaction và trả 202 nếu xử lý bất đồng bộ.
6. Worker gọi provider để tạo tài nguyên.
7. Lưu external_resource mapping khi provider trả resource ID.
8. Khi provider và broker state đã được commit, cập nhật operation thành SUCCEEDED và instance thành READY.
9. Nếu lỗi cuối cùng, lưu operation FAILED và instance FAILED hoặc trạng thái phục hồi phù hợp.

Không nên giữ một transaction database mở trong suốt thời gian gọi provider qua mạng. Provider call có thể mất nhiều giây hoặc phút và không thể tham gia transaction ACID của database broker. Dùng transaction ngắn để ghi ý định, sau đó xử lý bên ngoài transaction và cập nhật kết quả bằng transaction mới.

Nếu provider tạo tài nguyên thành công nhưng bước lưu external_resource thất bại, operation chưa thể báo thành công. Broker cần retry bước lưu hoặc reconciliation bằng provider operation ID/resource ID đã biết.

## 17. Giao dịch khi bind và unbind

Bind thường tạo principal hoặc credential ở provider, sau đó lưu binding và secret reference. Một thứ tự an toàn có thể là:

1. Validate consumer và quyền bind.
2. Tạo binding record ở CREATING.
3. Gọi provider để tạo user/role riêng cho binding.
4. Lưu credential vào secret manager.
5. Ghi secret reference, provider principal ID và metadata vào binding record.
6. Chuyển binding sang ACTIVE.
7. Trả binding response cho platform.

Nếu bước lưu secret thành công nhưng database commit thất bại, secret có thể bị mồ côi. Cần có cleanup hoặc reconciliation dựa trên binding ID. Nếu provider tạo principal thành công nhưng broker không lưu mapping, cũng cần khả năng tìm và thu hồi tài nguyên đó.

Unbind thực hiện theo hướng ngược lại:

1. Đánh dấu binding REVOKING và ghi operation nếu bất đồng bộ.
2. Thu hồi principal/credential ở provider.
3. Xác nhận quyền truy cập đã bị thu hồi.
4. Xóa hoặc đánh dấu secret hết hiệu lực.
5. Đánh dấu binding REVOKED và operation SUCCEEDED.

Không xóa binding record trước khi biết quá trình revoke đã hoàn tất, nếu không broker có thể mất thông tin cần thiết để retry hoặc đối chiếu.

## 18. Reconciliation giữa broker và provider

Database broker và provider không chia sẻ transaction. Vì vậy, có thể xảy ra trạng thái không nhất quán:

- Broker ghi PROVISIONING nhưng provider đã tạo resource.
- Provider đã xóa resource nhưng broker vẫn ghi ACTIVE.
- Binding record tồn tại nhưng principal đã bị xóa thủ công ở provider.
- Broker có external resource mapping nhưng resource không còn tồn tại.

Một tiến trình reconciliation định kỳ có thể:

1. Tìm các operation quá hạn hoặc ở trạng thái cần đối chiếu.
2. Dùng provider operation ID hoặc external resource ID truy vấn trạng thái provider.
3. So sánh với instance, binding và external_resource trong broker.
4. Cập nhật trạng thái khi có bằng chứng rõ ràng.
5. Retry thao tác có thể retry an toàn.
6. Đưa trường hợp không thể tự khôi phục vào hàng chờ vận hành thủ công.

Reconciliation không được tự ý tạo lại hoặc xóa tài nguyên chỉ vì hai hệ thống khác trạng thái. Trước side effect cần xác định nguồn dữ liệu có thẩm quyền và quy tắc sửa sai. Mọi thay đổi nên có audit record và correlation ID.

## 19. Index và tối ưu truy vấn

Các endpoint OSB thường tra cứu theo ID:

- GET instance, update, deprovision: instance ID.
- Bind/unbind/get binding: instance ID và binding ID.
- Last operation: instance ID và operation ID.
- Worker: operation state, next attempt và updated timestamp.
- Reconciliation: trạng thái tài nguyên và thời điểm quan sát gần nhất.

Do đó, cần index theo các đường truy vấn thực tế:

| Bảng | Index gợi ý | Truy vấn phục vụ |
|---|---|---|
| service_instance | PRIMARY KEY(instance_id) | Tìm instance |
| service_instance | (tenant_id, state) | Liệt kê instance theo tenant/trạng thái |
| service_binding | (instance_id, binding_id) hoặc binding ID PK | Tìm binding thuộc instance |
| service_binding | (tenant_id, consumer_id) | Tra cứu binding theo consumer |
| service_instance_operation | (instance_id, created_at DESC) | Lấy operation gần nhất |
| service_instance_operation | (state, updated_at) | Worker/reconciliation tìm operation cần xử lý |
| external_resource | UNIQUE(provider_id, provider_account_id, external_resource_id) | Bảo đảm mapping provider không trùng |
| broker_outbox | (publish_state, next_attempt_at) | Publisher lấy event cần gửi |

Không tạo index cho mọi cột. Index làm tăng chi phí ghi và dung lượng lưu trữ. Dùng query plan và metric thực tế để xác định index cần thiết.

## 20. Retention, audit và migration schema

Dữ liệu vòng đời cần chính sách retention rõ ràng:

- Instance đã deprovision có thể giữ tombstone để nhận diện retry và ngăn tái sử dụng ID.
- Operation terminal có thể được lưu theo thời hạn phục vụ polling và điều tra.
- Outbox event đã publish có thể được dọn sau khi hết thời gian đối soát.
- Binding đã revoke cần giữ metadata tối thiểu nhưng secret phải được xóa hoặc vô hiệu hóa theo chính sách.
- External resource mapping đã deleted có thể được giữ như audit history.

Không xóa operation đang chạy hoặc binding đang REVOKING chỉ để dọn dữ liệu. Cần có job cleanup riêng, có batch size, audit và khả năng resume.

Khi thay đổi schema database, sử dụng migration có phiên bản như Flyway hoặc Liquibase. Với hệ thống đang chạy nhiều replica, ưu tiên chiến lược expand-and-contract:

1. Thêm cột/bảng mới tương thích với code cũ.
2. Deploy code có thể đọc cả schema cũ và mới.
3. Backfill dữ liệu theo batch.
4. Chuyển luồng đọc/ghi sang schema mới.
5. Kiểm tra dữ liệu và metric.
6. Chỉ sau đó mới xóa cột cũ nếu không còn consumer.

Không sửa trực tiếp cấu trúc database production mà không có migration được kiểm soát.

## 21. Kiểm thử mô hình dữ liệu

Nên kiểm thử constraint, repository query và các luồng transaction, không chỉ kiểm tra mapper.

| Nhóm kiểm thử | Tình huống | Kết quả mong đợi |
|---|---|---|
| Instance | Tạo hai instance cùng ID | Bản ghi thứ hai bị từ chối |
| Binding | Binding tham chiếu instance không tồn tại | Foreign key từ chối |
| Binding | Cùng binding ID nhưng khác instance theo khóa đã chọn | Không gây ánh xạ nhầm |
| Operation | Tra cứu operation với instance sai | Không trả operation của instance khác |
| Operation | Request retry cùng idempotency key | Không tạo operation trùng |
| External resource | Hai instance cùng map một provider resource | Unique constraint từ chối |
| State | Ghi state ngoài tập cho phép | Check constraint từ chối |
| Concurrency | Hai request cập nhật cùng version | Chỉ một cập nhật thành công |
| Outbox | DB transaction rollback | Không có operation/event nửa vời |
| Worker | Message được gửi lặp | Provider side effect được bảo vệ bằng idempotency |
| Secret | Serialize binding record | Không xuất hiện secret plaintext |
| Tenant | Caller tenant A truy vấn instance tenant B | Bị từ chối |
| Reconciliation | Provider đã tạo resource nhưng broker chưa lưu | Có thể phục hồi mapping mà không tạo trùng |

Integration test nên chạy với database cùng loại với production hoặc Testcontainers để xác minh JSON type, partial index, foreign key, transaction và locking. Mock repository không thể chứng minh các constraint database thực sự hoạt động.

## 22. Quy trình thiết kế mô hình dữ liệu cho một offering mới

Khi bổ sung offering mới vào broker, hãy xác định trước các tài nguyên mà provider sẽ tạo và cách chúng liên kết với vòng đời OSB:

1. Xác định service instance đại diện cho tài nguyên logic nào.
2. Liệt kê consumer có thể bind và loại principal/credential cần tạo.
3. Xác định các operation có thể chạy bất đồng bộ.
4. Liệt kê provider resource được tạo, cập nhật và xóa.
5. Chọn ID ổn định cho instance, binding, operation và resource mapping.
6. Định nghĩa trạng thái và chuyển trạng thái hợp lệ cho từng đối tượng.
7. Xác định dữ liệu nào lưu trong database, JSON, secret manager hoặc provider.
8. Thiết kế khóa ngoại, unique constraint, index và tenant scope.
9. Xác định transaction boundary, outbox, idempotency và reconciliation.
10. Đặt retention, audit và migration policy.
11. Viết repository test, integration test và kiểm thử khôi phục sau lỗi.

Bắt đầu từ vòng đời và truy vấn thực tế giúp mô hình tránh hai cực đoan: một bảng khổng lồ chứa mọi loại dữ liệu, hoặc quá nhiều bảng nhỏ khiến mỗi thao tác phải join phức tạp.

## Kết luận

Mô hình lưu trữ của service broker cần phản ánh đúng ranh giới giữa **instance logic**, **binding của consumer**, **operation vòng đời** và **tài nguyên thực tế ở provider**. Service instance giữ trạng thái và cấu hình đã xác thực; binding giữ quan hệ consumer cùng secret reference; operation lưu tiến độ và kết quả từng yêu cầu; external resource duy trì ánh xạ tới ID do provider cấp. Transaction ngắn, khóa ngoại, unique constraint, optimistic locking, outbox, idempotency và reconciliation giúp các nhóm dữ liệu này nhất quán dù broker chạy nhiều replica hoặc provider xử lý bất đồng bộ. Trong Spring Cloud Service Broker, việc tách domain model khỏi request/response của SCOSB và bảo vệ secret ngay từ thiết kế giúp các thao tác provision, update, bind, unbind và deprovision có thể phục hồi, kiểm thử và vận hành đáng tin cậy.

## Tài liệu tham khảo

- [Open Service Broker API Specification](https://github.com/openservicebrokerapi/servicebroker/blob/master/spec.md) — service instance, service binding, operation và vòng đời broker.
- [Spring Cloud Open Service Broker Reference Documentation](https://docs.spring.io/spring-cloud-open-service-broker/docs/current/reference/) — service abstraction, request/response và tích hợp Spring.
- [Spring Data Relational Documentation](https://docs.spring.io/spring-data/relational/reference/) — repository và persistence cho mô hình quan hệ.
- [PostgreSQL Documentation — Constraints](https://www.postgresql.org/docs/current/ddl-constraints.html) — primary key, foreign key, unique và check constraint.
- [PostgreSQL Documentation — Indexes](https://www.postgresql.org/docs/current/indexes.html) — thiết kế index theo truy vấn.
- [Transactional Outbox pattern](https://microservices.io/patterns/data/transactional-outbox.html) — đồng bộ transaction dữ liệu và phát event.
- [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html) — lưu trữ, truy cập và rotation secret.

