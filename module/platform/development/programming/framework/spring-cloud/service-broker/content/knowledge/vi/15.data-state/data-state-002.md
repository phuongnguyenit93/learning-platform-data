# Khóa dữ liệu theo nền tảng, khách hàng và định danh OSB

Một service broker có thể phục vụ nhiều nền tảng, nhiều khách hàng và nhiều service instance cùng lúc. Các nền tảng có thể tạo ra những chuỗi định danh giống nhau trong các phạm vi khác nhau; một tenant cũng có thể có nhiều organization, space, project hoặc namespace. Nếu broker chỉ dùng một ID bên ngoài để tìm bản ghi, request có thể truy cập nhầm tài nguyên của khách hàng khác hoặc tạo dữ liệu trùng.

Trong module **SPRING_CLOUD_SERVICE_BROKER**, mô hình khóa dữ liệu cần phân biệt rõ danh tính platform, tenant nội bộ, phạm vi tài nguyên và các ID của Open Service Broker API (OSB API). Mỗi định danh phải có phạm vi duy nhất được xác định bằng hợp đồng tích hợp; khóa nội bộ phải đủ ổn định để liên kết instance, binding, operation và tài nguyên backend. Việc thiết kế đúng khóa và ràng buộc dữ liệu giúp broker cô lập tenant, xử lý request lặp, mở rộng nhiều nền tảng và khôi phục trạng thái sau lỗi.

## 1. Vì sao phải xác định phạm vi của khóa?

Giả sử broker tích hợp hai nền tảng Cloud Foundry khác nhau. Cả hai có thể gửi instance ID là chuỗi giống nhau, ví dụ **orders-db-prod**. Nếu bảng service instance chỉ có một cột instance_id và broker giả định giá trị này duy nhất toàn hệ thống, request từ nền tảng thứ hai có thể va chạm với bản ghi của nền tảng thứ nhất.

Tương tự, Kubernetes cluster A và cluster B đều có namespace **orders**; một cluster cũng có thể có nhiều tenant cùng dùng tên project hoặc workload giống nhau. Tên hiển thị hoặc ID do platform cấp chỉ có ý nghĩa trong phạm vi mà platform bảo đảm.

Ví dụ về các phạm vi khác nhau:

| Định danh | Phạm vi có thể áp dụng | Rủi ro nếu dùng đơn lẻ |
|---|---|---|
| platform ID | Một broker registration hoặc một platform đã xác thực | Trộn dữ liệu từ hai nền tảng |
| organization GUID | Một Cloud Foundry foundation | Trùng GUID ở foundation khác hoặc mất ngữ cảnh nguồn |
| space GUID | Một foundation, thường thuộc organization | Dùng sai scope khi chỉ tra theo space |
| cluster ID | Một hệ thống quản trị Kubernetes | Nhầm cluster hoặc registration |
| namespace | Bên trong một cluster | Tên giống nhau ở nhiều cluster |
| tenant ID | Phạm vi nội bộ do broker quản lý | Nhầm tenant nếu lấy trực tiếp từ request |
| service instance ID | Theo phạm vi ID mà platform và broker thống nhất | Va chạm hoặc truy cập nhầm instance |
| binding ID | Theo phạm vi binding mà broker quy định | Ghi đè binding của consumer khác |
| backend resource ID | Hệ thống backend/provider | Nhầm resource giữa provider, region hoặc account |

Một khóa tốt trả lời được hai câu hỏi: **đối tượng này là gì?** và **đối tượng này thuộc phạm vi nào?** Khi một ID không có ý nghĩa toàn cục, khóa tra cứu phải kết hợp nó với platform, tenant hoặc parent resource thích hợp.

## 2. Phân biệt định danh bên ngoài và khóa nội bộ

Broker nhận các ID từ OSB API và từ platform tích hợp, nhưng không nên dùng tất cả chúng làm primary key của mọi bảng. Nên có khóa nội bộ ổn định, thường là UUID hoặc kiểu khóa do database quản lý, rồi lưu các ID bên ngoài trong các cột có unique constraint theo phạm vi.

Có thể phân thành ba nhóm:

1. **Định danh catalog:** service ID và plan ID do broker công bố. Chúng là một phần của hợp đồng catalog và cần ổn định qua các lần triển khai.
2. **Định danh vòng đời OSB:** instance ID, binding ID và operation token được dùng trong các endpoint provision, bind, update, unbind, deprovision và last operation.
3. **Định danh hạ tầng:** backend resource ID, provider account, cluster UID, database identifier, cloud resource ARN hoặc Kubernetes object UID. Chúng định danh tài nguyên thật phía sau broker.

Ví dụ bảng ánh xạ:

| ID | Nguồn | Lưu ở đâu | Dùng để |
|---|---|---|---|
| service_id | Catalog broker | Service definition / instance | Chọn loại dịch vụ |
| plan_id | Catalog broker | Plan definition / instance | Chọn cấu hình dịch vụ |
| instance_id | Platform OSB | External identity của instance | Nhận diện instance qua endpoint OSB |
| binding_id | Platform OSB | External identity của binding | Nhận diện quan hệ consumer |
| operation_id | Broker | Operation record | Theo dõi công việc bất đồng bộ |
| internal_instance_id | Broker/database | Primary key instance | Liên kết dữ liệu nội bộ |
| internal_binding_id | Broker/database | Primary key binding | Liên kết binding và secret |
| backend_resource_id | Backend/provider | Instance/backend mapping | Gọi API quản lý tài nguyên thật |

Không dùng service ID hoặc plan ID làm khóa của instance. Nhiều instance có thể cùng sử dụng một service và plan. Không dùng backend resource ID thay cho instance ID, vì một instance có thể được triển khai qua nhiều tài nguyên backend và backend ID có thể thay đổi khi migration.

## 3. Xác định platform identity từ nguồn tin cậy

Platform ID dùng để phân biệt các nền tảng đã đăng ký với broker. Giá trị này nên được xác định từ principal đã xác thực, chẳng hạn credential riêng, mutual TLS identity hoặc gateway registration. Không lấy một field tự khai trong request body làm danh tính platform có thẩm quyền.

Ví dụ request có context:

~~~json
{
  "context": {
    "platform": "cloudfoundry",
    "organization_guid": "org-123",
    "space_guid": "space-456"
  }
}
~~~

Trường platform trong JSON chỉ là metadata. Broker phải xác thực caller trước, sau đó dùng registration tương ứng để diễn giải organization và space. Nếu principal thuộc Cloud Foundry foundation A nhưng context khai foundation B hoặc scope không thuộc registration đó, broker phải từ chối.

Mô hình platform registration có thể gồm:

| Field | Mục đích |
|---|---|
| platform_id | Khóa nội bộ ổn định cho platform registration |
| platform_type | Loại adapter, ví dụ cloud-foundry hoặc kubernetes |
| external_platform_key | ID foundation, cluster hoặc registration bên ngoài |
| auth_principal_ref | Tham chiếu danh tính/certificate/credential đã xác thực |
| status | Trạng thái active, suspended hoặc retired |
| created_at / updated_at | Audit thay đổi registration |

Nếu một tổ chức vận hành nhiều Cloud Foundry foundation hoặc nhiều Kubernetes cluster, nên tạo platform registration riêng hoặc một mô hình phân cấp có ID ổn định. Khi đó, cùng một organization GUID hoặc namespace ở hai nền tảng không bị nhập thành một scope.

## 4. Ánh xạ platform scope sang tenant nội bộ

Tenant ID là định danh nội bộ mà broker dùng để áp dụng quota, entitlement, ownership và phân quyền. Tenant ID không nhất thiết bằng organization GUID, space GUID, project ID hoặc namespace.

Một tenant có thể có nhiều scope bên ngoài:

- Một khách hàng có nhiều organization hoặc space trên Cloud Foundry.
- Một khách hàng triển khai workload trên nhiều Kubernetes cluster.
- Một tenant có thể dùng nhiều platform adapter.
- Một namespace có thể là môi trường kỹ thuật, không phải đơn vị khách hàng hoặc ranh giới thanh toán.

Vì vậy, broker nên có bảng mapping riêng:

~~~sql
CREATE TABLE platform_scope_mapping (
    mapping_id UUID PRIMARY KEY,
    platform_id UUID NOT NULL,
    scope_type VARCHAR(80) NOT NULL,
    external_scope_key VARCHAR(255) NOT NULL,
    tenant_id UUID NOT NULL,
    status VARCHAR(30) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    CONSTRAINT uq_platform_scope
        UNIQUE (platform_id, scope_type, external_scope_key)
);
~~~

Ví dụ:

| platform_id | scope_type | external_scope_key | tenant_id |
|---|---|---|---|
| cf-prod-a | organization | org-123 | tenant-commerce |
| cf-prod-a | space | org-123/space-456 | tenant-commerce |
| k8s-cluster-1 | namespace | orders | tenant-commerce |
| k8s-cluster-2 | namespace | orders | tenant-commerce |

Các giá trị trong bảng chỉ minh họa. Khóa external scope cần được tạo theo semantics của adapter. Với Kubernetes, namespace name nên kết hợp cluster identity hoặc namespace UID; với Cloud Foundry, space GUID nên được gắn với foundation/platform identity và có thể lưu organization GUID để kiểm tra quan hệ cha.

Không tự động tạo tenant mới chỉ vì request mang một organization hoặc namespace chưa biết. Việc đăng ký mapping cần qua quy trình quản trị hoặc provisioning đáng tin cậy, có xác thực và audit.

## 5. Khóa cho service và service plan

Service ID và plan ID được broker công bố trong catalog OSB API. Chúng không phải ID do từng tenant tự chọn. Broker nên giữ ID ổn định và không tái sử dụng một ID cho ý nghĩa khác.

Một mô hình catalog nội bộ:

~~~sql
CREATE TABLE service_definition (
    service_id VARCHAR(120) PRIMARY KEY,
    name VARCHAR(160) NOT NULL,
    bindable BOOLEAN NOT NULL,
    active BOOLEAN NOT NULL,
    created_at TIMESTAMP NOT NULL
);

CREATE TABLE service_plan (
    plan_id VARCHAR(120) PRIMARY KEY,
    service_id VARCHAR(120) NOT NULL,
    name VARCHAR(160) NOT NULL,
    active BOOLEAN NOT NULL,
    profile_version VARCHAR(80) NOT NULL,
    CONSTRAINT fk_plan_service
        FOREIGN KEY (service_id) REFERENCES service_definition(service_id),
    CONSTRAINT uq_service_plan_name
        UNIQUE (service_id, name)
);
~~~

Plan thuộc một service. Khi nhận provision, broker phải xác minh cặp service ID và plan ID là một quan hệ hợp lệ. Không chỉ kiểm tra plan ID tồn tại rồi bỏ qua service ID được gửi.

Nếu catalog có version hoặc plan profile thay đổi, instance đã provision cần giữ snapshot hoặc version đã dùng. Không xóa metadata lịch sử mà các instance cũ cần để update, retrieve hoặc deprovision.

## 6. Khóa cho service instance

Service instance là tài nguyên được platform yêu cầu tạo từ một service và một plan. Instance ID thường xuất hiện trong path của các endpoint vòng đời OSB. Broker cần quy định phạm vi unique của ID theo contract platform.

Có hai tình huống phổ biến:

- Nếu broker và platform bảo đảm instance ID duy nhất trên toàn broker, có thể đặt unique constraint toàn cục trên instance_id.
- Nếu broker hỗ trợ nhiều platform registration và ID chỉ duy nhất trong từng platform, đặt unique constraint theo platform_id cùng instance_id. Nếu hợp đồng cho phép ID lặp trong các tenant scope của cùng platform, cần thêm scope key phù hợp.

Không nên thêm tenant_id vào khóa chỉ vì muốn an toàn hơn nếu điều đó cho phép cùng một instance ID xuất hiện hai lần trong cùng platform khi contract không cho phép. Unique constraint phải phản ánh chính xác phạm vi ID đã thỏa thuận.

Schema minh họa:

~~~sql
CREATE TABLE service_instance (
    internal_instance_id UUID PRIMARY KEY,
    platform_id UUID NOT NULL,
    tenant_id UUID NOT NULL,
    platform_scope_id UUID NOT NULL,
    external_instance_id VARCHAR(255) NOT NULL,
    service_id VARCHAR(120) NOT NULL,
    plan_id VARCHAR(120) NOT NULL,
    lifecycle_state VARCHAR(40) NOT NULL,
    backend_provider VARCHAR(120),
    backend_resource_id VARCHAR(255),
    request_fingerprint VARCHAR(128) NOT NULL,
    profile_version VARCHAR(80) NOT NULL,
    version BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    CONSTRAINT uq_platform_instance
        UNIQUE (platform_id, external_instance_id),
    CONSTRAINT fk_instance_service
        FOREIGN KEY (service_id) REFERENCES service_definition(service_id),
    CONSTRAINT fk_instance_plan
        FOREIGN KEY (plan_id) REFERENCES service_plan(plan_id)
);
~~~

Đây là ví dụ cho hợp đồng mà instance ID duy nhất trong một platform registration. Nếu phạm vi thực tế khác, điều chỉnh unique key và cách lookup tương ứng. Có thể thêm composite foreign key hoặc domain validation để bảo đảm plan thuộc đúng service, không chỉ tồn tại độc lập.

Primary key nội bộ giúp các bảng binding, operation, resource mapping và audit tham chiếu instance mà không phụ thuộc ID bên ngoài. Khi platform thay đổi cách đặt tên hoặc adapter cần migrate ID, internal ID vẫn giữ ổn định.

## 7. Khóa cho service binding

Binding là quan hệ giữa instance và consumer. Một instance có thể có nhiều binding, vì vậy binding phải có khóa riêng và tham chiếu đến internal instance ID.

Một binding ID có thể được platform tạo theo một phạm vi cụ thể. Broker cần định nghĩa unique key theo contract đang hỗ trợ, thường ít nhất là gắn binding ID với instance và platform. Không giả định binding ID duy nhất toàn cục nếu platform không bảo đảm điều đó; cũng không được bỏ qua instance parent vì binding chỉ có ý nghĩa trong quan hệ với instance.

Schema tham khảo:

~~~sql
CREATE TABLE service_binding (
    internal_binding_id UUID PRIMARY KEY,
    internal_instance_id UUID NOT NULL,
    platform_id UUID NOT NULL,
    tenant_id UUID NOT NULL,
    external_binding_id VARCHAR(255) NOT NULL,
    consumer_id VARCHAR(255),
    binding_state VARCHAR(40) NOT NULL,
    request_fingerprint VARCHAR(128) NOT NULL,
    backend_principal_id VARCHAR(255),
    secret_reference VARCHAR(500),
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    CONSTRAINT fk_binding_instance
        FOREIGN KEY (internal_instance_id)
        REFERENCES service_instance(internal_instance_id),
    CONSTRAINT uq_instance_binding
        UNIQUE (internal_instance_id, external_binding_id)
);
~~~

Nếu platform có thể dùng cùng binding ID trên các instance khác nhau, khóa (internal_instance_id, external_binding_id) là phù hợp. Nếu hợp đồng có phạm vi rộng hơn, cần bổ sung platform hoặc scope tương ứng. Quan trọng là lookup theo cả parent instance và binding ID, sau đó xác minh platform/tenant ownership.

Không dùng consumer ID làm khóa thay cho binding ID. Một ứng dụng có thể tạo nhiều binding khác nhau đến cùng instance hoặc đến các instance khác nhau. Consumer ID là thuộc tính mô tả chủ thể sử dụng; binding ID định danh quan hệ được quản lý.

## 8. Khóa cho operation và tác vụ bất đồng bộ

Operation ID thường do broker tạo để platform truy vấn tiến độ provision, update, deprovision hoặc binding. Nó phải được lưu bền vững và liên kết với đúng resource cùng loại thao tác.

Một bảng operation có thể gồm:

~~~sql
CREATE TABLE broker_operation (
    operation_id VARCHAR(160) PRIMARY KEY,
    platform_id UUID NOT NULL,
    tenant_id UUID NOT NULL,
    internal_instance_id UUID,
    internal_binding_id UUID,
    operation_type VARCHAR(40) NOT NULL,
    request_fingerprint VARCHAR(128) NOT NULL,
    operation_state VARCHAR(40) NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    error_code VARCHAR(120),
    safe_error_description TEXT,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP
);
~~~

Một operation cần có một resource target rõ ràng: instance hoặc binding. Không lưu chỉ operation ID mà thiếu quan hệ resource, vì worker sẽ không biết phải tiếp tục tác động đến đối tượng nào sau khi process restart.

Operation ID không nên chứa tenant name, email hoặc thông tin nhạy cảm. Nếu token được dùng như một định danh có thể đoán được, cần bảo đảm endpoint last operation vẫn xác thực platform và kiểm tra ownership; operation ID không phải bearer authorization token trừ khi contract được thiết kế rõ như vậy.

## 9. Khóa idempotency và request fingerprint

OSB platform có thể retry request khi timeout. Broker cần phân biệt:

- Retry cùng yêu cầu logic.
- Request mới dùng cùng external ID nhưng nội dung khác.
- Request từ platform hoặc tenant khác có chuỗi ID trùng nhau.

Idempotency key nên dựa trên định danh đã xác thực và operation target:

~~~text
idempotency_key = hash(
    platform_id,
    tenant_id,
    resource_type,
    external_resource_id,
    operation_type,
    lifecycle_generation
)
~~~

Request fingerprint thể hiện nội dung có ảnh hưởng đến kết quả:

~~~text
request_fingerprint = hash(
    service_id,
    plan_id,
    canonical_parameters,
    resolved_platform_scope,
    selected_profile_version
)
~~~

Không đưa timestamp, trace ID hoặc thứ tự key JSON vào fingerprint. Hãy chuẩn hóa parameters trước khi hash để hai request có cùng ý nghĩa tạo fingerprint giống nhau. Không đưa password hoặc secret thô vào log; nếu cần so sánh bí mật, dùng HMAC hoặc cơ chế an toàn tương đương.

Quy tắc xử lý:

| Bản ghi hiện có | Request mới | Kết quả |
|---|---|---|
| Chưa có cùng khóa | ID hợp lệ | Tạo instance/binding và operation |
| Có cùng khóa, fingerprint giống | Retry tương đương | Trả kết quả hoặc operation đã lưu |
| Có cùng khóa, fingerprint khác | Request mâu thuẫn | Conflict; giữ nguyên dữ liệu cũ |
| ID giống nhưng platform khác | Scope khác | Tìm bản ghi theo platform scope riêng |
| ID giống nhưng tenant khác trong cùng platform | Ownership conflict | Từ chối; không chuyển tenant của resource |

Idempotency key cần được lưu cùng operation hoặc request ledger. Không chỉ tính trong bộ nhớ, vì retry có thể đến một instance broker khác hoặc sau khi process restart.

## 10. Tra cứu luôn theo khóa có phạm vi

Một lỗi nghiêm trọng là tìm instance bằng external ID trước rồi mới kiểm tra tenant ở tầng controller. Cách làm này có thể trả về dữ liệu của tenant khác hoặc tạo side channel cho việc dò ID.

Truy vấn nên giới hạn ngay trong điều kiện database:

~~~sql
SELECT *
FROM service_instance
WHERE platform_id = :authenticatedPlatformId
  AND external_instance_id = :instanceId;
~~~

Nếu contract yêu cầu tenant scope trong khóa, thêm tenant ID đã được resolver xác minh:

~~~sql
SELECT *
FROM service_instance
WHERE platform_id = :authenticatedPlatformId
  AND tenant_id = :resolvedTenantId
  AND external_instance_id = :instanceId;
~~~

Không lấy resolvedTenantId trực tiếp từ body. Giá trị này phải đến từ mapping đáng tin cậy gắn với platform principal và scope request.

Trong Spring Data, có thể thể hiện rõ scope trong repository method:

~~~java
public interface ServiceInstanceRepository
        extends JpaRepository<ServiceInstanceEntity, UUID> {

    Optional<ServiceInstanceEntity>
    findByPlatformIdAndExternalInstanceId(
        UUID platformId,
        String externalInstanceId
    );

    Optional<ServiceInstanceEntity>
    findByPlatformIdAndTenantIdAndExternalInstanceId(
        UUID platformId,
        UUID tenantId,
        String externalInstanceId
    );
}
~~~

Chọn một phương thức theo quy tắc unique key của hệ thống. Không tạo một method findByInstanceId không có scope rồi để mọi caller tự nhớ kiểm tra tenant. Repository API nên làm cho việc truy vấn có phạm vi trở thành mặc định.

## 11. Ràng buộc khóa và index trong database

Các ràng buộc cần được bảo vệ ở database, không chỉ trong Java:

- Primary key cho mọi entity nội bộ.
- Unique constraint cho external ID theo phạm vi đã xác định.
- Foreign key từ plan đến service.
- Foreign key từ instance đến service và plan.
- Foreign key từ binding đến instance.
- Unique key cho operation/idempotency identity.
- Check constraint hoặc enum mapping cho lifecycle state.
- Index hỗ trợ lookup theo platform, tenant, instance và binding.

Ví dụ index:

~~~sql
CREATE INDEX ix_instance_tenant_state
    ON service_instance (tenant_id, lifecycle_state);

CREATE INDEX ix_instance_platform_tenant
    ON service_instance (platform_id, tenant_id);

CREATE INDEX ix_binding_instance_state
    ON service_binding (internal_instance_id, binding_state);

CREATE INDEX ix_operation_resource_state
    ON broker_operation (internal_instance_id, operation_state);
~~~

Không tạo index cho mọi cột theo cảm tính. Hãy dựa vào query thực tế: lookup theo external ID, liệt kê instance theo tenant, tìm operation đang chạy và tìm binding của một instance. Index cũng cần tính đến thứ tự cột trong composite index và selectivity của từng field.

Unique constraint là lớp bảo vệ cuối cùng khi hai request đồng thời cùng cố tạo một instance hoặc binding. Kiểm tra SELECT trước INSERT không đủ để chống race condition.

## 12. Tenant isolation ở tầng ứng dụng và database

Tenant isolation cần được áp dụng xuyên suốt request, repository, cache, queue và backend adapter.

### Ở tầng ứng dụng

- Xác thực platform trước khi đọc context.
- Chuẩn hóa scope thành platform ID, tenant ID và platform scope ID.
- Đưa scope vào service/domain command.
- Repository lookup phải có scope.
- Kiểm tra ownership trước update, bind, unbind và deprovision.
- Không cho phép caller truyền internal tenant ID hoặc backend resource ID để ghi đè ownership.

### Ở tầng database

Có thể dùng row-level security (RLS) nếu database hỗ trợ. Ví dụ PostgreSQL:

~~~sql
ALTER TABLE service_instance ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_instance_isolation
ON service_instance
USING (
    tenant_id = current_setting('app.tenant_id')::uuid
);
~~~

Đây là ví dụ khái niệm. Ứng dụng cần đặt tenant context an toàn trong transaction, reset sau khi trả connection về pool và kiểm tra mọi đường truy cập nền/administrative. RLS không thay thế authorization ở application layer; nó là một lớp phòng vệ bổ sung.

### Cache và message queue

Cache key cũng phải chứa scope:

~~~text
service-instance:{platform_id}:{tenant_id}:{instance_id}
~~~

Không dùng cache key chỉ là instance ID. Với message queue, payload nên chứa internal resource ID, platform/tenant ID đã xác minh, operation ID và schema version. Worker cần kiểm tra bản ghi trong state store trước khi thực thi; không tin payload cũ hoặc dữ liệu tenant do message producer không được xác thực cung cấp.

## 13. Context và scope của Cloud Foundry, Kubernetes

### Cloud Foundry

Một Cloud Foundry integration có thể gửi organization GUID và space GUID. Broker nên ánh xạ chúng trong phạm vi foundation đã xác thực:

~~~text
platform_id = cf-foundation-prod
external_scope = organization_guid + space_guid
tenant_id = tenant-commerce
~~~

Organization và space name là metadata hiển thị; GUID là định danh ổn định hơn. Tuy nhiên, GUID cần gắn với foundation/platform registration vì broker có thể kết nối nhiều foundation.

### Kubernetes

Với Kubernetes, tên namespace không đủ để định danh một scope trên nhiều cluster. Nên dùng cluster registration cộng namespace UID hoặc namespace name đã được phân giải:

~~~text
platform_id = k8s-controller-prod
cluster_id = cluster-asia-1
namespace_uid = 7a0f...
tenant_id = tenant-commerce
~~~

Namespace có thể bị xóa rồi tạo lại cùng tên. Namespace UID mới biểu thị một đối tượng khác. Nếu broker chỉ lưu tên namespace, một namespace mới có thể vô tình nhận quyền truy cập vào tài nguyên cũ của namespace đã xóa. Cần quy định việc mapping lại scope và chuyển giao ownership một cách tường minh.

Một adapter Kubernetes có thể chuyển các định danh cluster/namespace/workload thành mô hình nội bộ chuẩn. Broker không nên ép mọi platform gửi cùng một JSON schema; nó cần giữ định danh gốc cùng platform registration và chuẩn hóa scope ở lớp adapter.

## 14. Quan hệ khóa và vòng đời dữ liệu

Mô hình tổng quát:

~~~mermaid
erDiagram
    PLATFORM ||--o{ PLATFORM_SCOPE : owns
    TENANT ||--o{ PLATFORM_SCOPE : maps_to
    SERVICE ||--o{ PLAN : contains
    PLATFORM ||--o{ INSTANCE : namespaces
    TENANT ||--o{ INSTANCE : owns
    PLAN ||--o{ INSTANCE : selected_for
    INSTANCE ||--o{ BINDING : has
    INSTANCE ||--o{ OPERATION : tracks
    BINDING ||--o{ OPERATION : tracks
    INSTANCE ||--o{ BACKEND_RESOURCE : maps_to

    PLATFORM {
      uuid platform_id PK
      string platform_type
    }
    TENANT {
      uuid tenant_id PK
    }
    PLATFORM_SCOPE {
      uuid mapping_id PK
      uuid platform_id FK
      uuid tenant_id FK
      string external_scope_key
    }
    SERVICE {
      string service_id PK
    }
    PLAN {
      string plan_id PK
      string service_id FK
    }
    INSTANCE {
      uuid internal_instance_id PK
      uuid platform_id FK
      uuid tenant_id FK
      string external_instance_id
      string service_id FK
      string plan_id FK
    }
    BINDING {
      uuid internal_binding_id PK
      uuid internal_instance_id FK
      string external_binding_id
      string consumer_id
    }
    OPERATION {
      string operation_id PK
      uuid internal_instance_id FK
      uuid internal_binding_id FK
      string operation_type
    }
    BACKEND_RESOURCE {
      uuid backend_mapping_id PK
      uuid internal_instance_id FK
      string provider
      string backend_resource_id
    }
~~~

Sơ đồ mô tả quan hệ khái niệm. Một instance có thể ánh xạ đến nhiều backend resource nếu broker quản lý nhiều thành phần như database, volume và backup policy. Vì vậy, nếu thực tế là quan hệ một-nhiều, nên dùng bảng backend resource riêng thay vì chỉ một cột backend_resource_id trên instance.

Binding luôn thuộc một instance. Operation có thể thuộc instance hoặc binding tùy loại thao tác. Nếu schema cho phép cả hai foreign key, cần ràng buộc để bảo đảm operation target đúng một loại resource hoặc có một aggregate reference rõ ràng.

## 15. Lưu backend resource ID có scope

Backend resource ID có thể không duy nhất trên mọi provider hoặc account. Ví dụ, một database ID có thể chỉ duy nhất trong một project, region hoặc provider account.

Nên lưu backend identity cùng phạm vi:

| Trường | Ví dụ |
|---|---|
| provider | aws-rds |
| account/project | cloud-account-42 |
| region/cluster | ap-southeast-1 |
| resource type | postgres-instance |
| backend resource ID | db-abc123 |
| internal instance ID | UUID do broker tạo |

Nếu một instance tạo nhiều resource, bảng mapping có thể có unique key theo provider/account/region/resource ID. Khi gọi backend API, adapter phải dùng account và region đã lưu, không lấy chúng từ request DELETE hoặc UPDATE không được xác thực.

Không xóa mapping backend ngay khi gửi yêu cầu delete. Giữ lại trạng thái deprovisioning và resource reference cho đến khi backend xác nhận hoặc reconciliation xác định rõ kết quả. Nếu xóa mapping quá sớm, broker mất khả năng retry và đối soát tài nguyên.

## 16. Lifecycle state, tombstone và reuse ID

Xóa instance khỏi bảng ngay khi deprovision bắt đầu có thể làm mất thông tin cần thiết để xử lý request lặp hoặc worker còn chạy. Nên giữ trạng thái và lịch sử:

| Trạng thái | Ý nghĩa |
|---|---|
| PROVISIONING | Đã nhận yêu cầu, đang tạo tài nguyên |
| ACTIVE | Tài nguyên sẵn sàng |
| UPDATING | Đang thay đổi cấu hình/plan |
| DEPROVISIONING | Đang thu hồi tài nguyên |
| DEPROVISIONED | Backend đã được xác nhận thu hồi |
| FAILED | Thao tác thất bại, cần policy retry hoặc can thiệp |

Sau khi deprovision, broker có thể giữ tombstone chứa external ID, platform scope, generation, fingerprint và thời điểm xóa trong một khoảng thời gian theo policy. Tombstone giúp nhận diện retry cũ và ngăn request cũ bị hiểu thành provision mới.

Nếu contract cho phép reuse ID, broker cần tạo generation mới sau khi vòng đời trước đã hoàn tất và tài nguyên cũ được đối soát. Idempotency key của generation mới phải khác key của generation cũ. Không tái sử dụng ID hoặc xóa tombstone khi còn operation cũ có khả năng chạy tiếp.

## 17. Migration khi thay đổi khóa

Khi broker thay đổi cách xác định scope, chẳng hạn từ unique instance ID toàn cục sang composite key theo platform, cần migration có kế hoạch.

Một trình tự tham khảo:

1. Xác định phạm vi unique thực tế từ dữ liệu và contract platform.
2. Tìm các ID trùng hoặc bản ghi thiếu platform/tenant mapping.
3. Thêm cột mới dưới dạng nullable và index hỗ trợ.
4. Backfill platform ID, tenant ID và scope từ nguồn mapping đáng tin cậy.
5. Kiểm tra các trường hợp không thể phân giải; đưa vào hàng đợi xử lý thay vì tự gán tenant.
6. Tạo unique constraint mới sau khi dữ liệu đã sạch.
7. Chuyển repository lookup sang khóa mới.
8. Theo dõi lỗi và đối chiếu request trong giai đoạn chuyển đổi.
9. Chỉ bỏ cột/index cũ sau khi không còn consumer phụ thuộc.

Không suy ra tenant từ tên namespace hoặc organization nếu có thể có trùng lặp. Không gán tất cả bản ghi thiếu mapping vào một tenant mặc định. Một migration sai có thể làm rò rỉ dữ liệu giữa khách hàng.

Schema version cũng có ích cho operation bất đồng bộ. Worker cũ có thể xử lý message được tạo trước migration; message cần có schema version hoặc worker phải có khả năng đọc phiên bản cũ cho đến khi backlog được xử lý hết.

## 18. Tổ chức trong Spring Cloud Service Broker

Có thể đặt các lớp chịu trách nhiệm phân giải khóa và scope riêng:

~~~text
broker/
  identity/
    AuthenticatedPlatform
    PlatformRegistration
  tenant/
    TenantResolver
    PlatformScopeMapping
    TenantRepository
  catalog/
    ServiceDefinitionRepository
    ServicePlanRepository
  instance/
    ServiceInstanceEntity
    ServiceInstanceRepository
    InstanceIdentity
  binding/
    ServiceBindingEntity
    ServiceBindingRepository
  operation/
    BrokerOperationEntity
    OperationRepository
  backend/
    BackendResourceMapping
    BackendResourceRepository
  persistence/
    TenantAwareRepositorySupport
~~~

Một value object có thể biểu diễn định danh instance đã được phân giải:

~~~java
public record InstanceIdentity(
    UUID platformId,
    UUID tenantId,
    String externalInstanceId
) {}
~~~

Service nghiệp vụ nhận identity đã xác minh thay vì tự đọc field từ request:

~~~java
public Mono<ServiceInstanceEntity> loadOwnedInstance(
        InstanceIdentity identity) {

    return instanceRepository
        .findByPlatformIdAndTenantIdAndExternalInstanceId(
            identity.platformId(),
            identity.tenantId(),
            identity.externalInstanceId()
        )
        .switchIfEmpty(Mono.error(
            new ServiceInstanceNotFoundException()
        ));
}
~~~

Đây là ví dụ thiết kế. Nếu unique key của broker chỉ gồm platform ID và instance ID, repository method cần phản ánh đúng khóa đó. Tenant ID vẫn được xác minh với bản ghi đã lưu trước khi thực hiện hành động. Không nên tạo một phương thức repository tổng quát chỉ nhận external ID.

### Tách trách nhiệm

- Platform authentication xác định caller.
- Platform context resolver phân giải external scope.
- Tenant resolver ánh xạ scope sang tenant nội bộ.
- Identity value object đóng gói khóa tra cứu.
- Repository thực hiện lookup có scope và dựa trên unique constraint.
- Domain service kiểm tra ownership và lifecycle.
- Backend adapter dùng backend mapping đã lưu.
- Operation worker đọc state store và xác minh scope trước khi tiếp tục.

Cách tách này tránh việc mỗi handler provision, update, bind, unbind và deprovision tự diễn giải platform ID theo cách khác nhau.

## 19. Kiểm thử khóa và cô lập tenant

Bộ kiểm thử nên chứng minh rằng cùng một chuỗi ID không dẫn đến truy cập chéo tenant hoặc platform.

| Ca kiểm thử | Dữ liệu | Kết quả mong đợi |
|---|---|---|
| Cùng instance ID ở hai platform | platform A và B cùng gửi orders-db | Hai record độc lập nếu contract cho phép |
| Cùng namespace ở hai cluster | namespace orders trên cluster A/B | Scope được phân biệt bằng cluster identity |
| Scope chưa mapping | Platform gửi namespace/space chưa đăng ký | Từ chối, không tự tạo tenant |
| Caller giả platform | Context ghi platform B nhưng principal thuộc A | Dùng principal A; scope không hợp lệ bị từ chối |
| Tenant mismatch | Instance thuộc tenant A, request resolve tenant B | Không trả dữ liệu hoặc thay ownership |
| Plan không thuộc service | Cặp service_id/plan_id sai | Từ chối provision |
| Binding ID trùng instance khác | Cùng binding ID trên hai instance | Xử lý theo unique scope đã định nghĩa |
| Request retry | Cùng platform, tenant, resource và fingerprint | Replay operation/kết quả |
| Request mâu thuẫn | Cùng ID nhưng plan/parameters khác | Conflict, giữ nguyên record |
| Request đồng thời | Hai request cùng external key | Unique constraint chỉ cho một bản ghi |
| Cache isolation | Hai tenant cùng instance ID | Cache key khác nhau theo scope |
| Queue redelivery | Worker nhận lại operation | Đọc lại ownership và state, không tác động resource khác |
| Namespace bị tạo lại | Tên giống nhưng UID khác | Không tự kế thừa ownership cũ |
| Deprovision tombstone | Retry DELETE sau khi đã xóa | Không tạo lại hoặc xóa nhầm tài nguyên |
| Migration thiếu mapping | Bản ghi cũ không xác định tenant | Đưa vào xử lý thủ công, không gán mặc định |

Nên dùng database thật hoặc Testcontainers cho test unique constraint và transaction cạnh tranh. Mock repository không chứng minh được composite key hoạt động đúng dưới hai request đồng thời.

## 20. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Chỉ dùng instance_id làm primary key trong mọi trường hợp | ID trùng giữa platform có thể va chạm | Dùng internal PK và unique key theo scope |
| Lấy platform từ context body | Caller có thể giả mạo nền tảng | Lấy platform từ principal đã xác thực |
| Dùng namespace name làm tenant ID | Trùng tên giữa cluster và tenant | Kết hợp cluster identity, namespace UID và mapping |
| Dùng organization name làm khóa | Tên có thể đổi hoặc trùng | Dùng external ID ổn định trong platform scope |
| Dùng binding ID làm khóa toàn cục không có căn cứ | Request hợp lệ từ instance khác có thể va chạm | Định nghĩa unique scope theo contract |
| Truy vấn instance trước rồi mới kiểm tra tenant | Có nguy cơ IDOR và lộ dữ liệu | Scope query ngay từ database |
| Chỉ kiểm tra uniqueness trong Java | Race condition có thể tạo bản ghi trùng | Unique constraint trong database |
| Dùng backend resource ID thay instance ID | Mất liên kết OSB khi provider thay đổi | Lưu mapping riêng |
| Cache key không có tenant/platform | Cache leak giữa khách hàng | Đưa scope vào cache key |
| Worker tin payload queue | Message cũ hoặc sai scope có thể tác động nhầm | Đọc state store và xác minh ownership |
| Xóa record ngay khi deprovision bắt đầu | Mất dữ liệu đối soát và retry | Giữ tombstone/lifecycle history |
| Migration gán tenant mặc định | Trộn dữ liệu nhiều khách hàng | Phân giải từ nguồn tin cậy hoặc xử lý thủ công |

## 21. Nguyên tắc cần ghi nhớ

Khóa dữ liệu của service broker phải phản ánh phạm vi thật của từng định danh. Platform identity đến từ xác thực; tenant ID được phân giải từ mapping đáng tin cậy; service và plan ID thuộc catalog; instance và binding ID thuộc vòng đời OSB; operation ID do broker quản lý; backend resource ID thuộc hạ tầng.

Khi xây dựng bằng Spring Cloud Service Broker, hãy áp dụng các nguyên tắc:

- Tách external ID khỏi internal primary key.
- Xác định và ghi rõ phạm vi unique của từng ID theo contract platform.
- Dùng platform registration và tenant mapping để chuẩn hóa context.
- Ràng buộc plan với service, binding với instance và operation với đúng resource.
- Đưa platform/tenant scope vào repository lookup, unique constraint, cache key và message.
- Xác minh ownership ở mỗi thao tác vòng đời, không chỉ khi provision.
- Dùng database constraint để chống trùng dưới tải đồng thời.
- Giữ backend resource mapping, lifecycle history và tombstone đủ lâu cho retry/reconciliation.
- Migration khóa phải dựa trên dữ liệu nguồn tin cậy và có bước xử lý bản ghi không xác định.
- Không coi external ID hoặc context do caller gửi là bằng chứng quyền truy cập.

Khi mỗi ID có phạm vi rõ ràng và mọi truy vấn đều được giới hạn theo platform cùng tenant đã xác minh, broker có thể phục vụ nhiều nền tảng trong cùng hệ thống mà vẫn giữ dữ liệu, quyền truy cập và vòng đời tài nguyên tách biệt.

