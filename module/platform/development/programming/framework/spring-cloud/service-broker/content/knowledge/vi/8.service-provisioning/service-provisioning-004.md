# Ánh xạ instance_id sang tài nguyên của nhà cung cấp

Khi platform yêu cầu cấp phát một service instance qua Open Service Broker API (OSB API), platform gửi một định danh instance_id trong URL. Định danh này thuộc về vòng đời dịch vụ mà platform quản lý. Nhà cung cấp hạ tầng có thể tạo một tài nguyên với ID riêng, chẳng hạn database ID, cloud resource ID hoặc Kubernetes object name. Service broker cần lưu mối quan hệ giữa hai định danh đó để có thể tiếp tục quản lý đúng tài nguyên trong các yêu cầu update, binding, deprovision và retry.

Vì vậy, instance_id không nên được xem là ID của database hay tài nguyên cloud. Nó là khóa tham chiếu do platform cấp và được broker dùng để tìm bản ghi quản lý service instance. Broker phải ánh xạ khóa này tới thông tin service, plan, tenant, trạng thái vòng đời và định danh tài nguyên thực tế của nhà cung cấp.

Bài học này trình bày mô hình ánh xạ, cách lưu trạng thái bền vững, cách xử lý provision lặp, lỗi giữa chừng và thao tác bất đồng bộ, cùng cách dùng ánh xạ trong các thao tác vòng đời. Ví dụ tập trung vào Spring Cloud service broker quản lý PostgreSQL, nhưng cùng nguyên tắc có thể áp dụng cho Redis, RabbitMQ, object storage hoặc tài nguyên Kubernetes.

## 1. Hai định danh có vai trò khác nhau

Một yêu cầu provision thường có ít nhất hai định danh quan trọng:

- instance_id: định danh service instance do platform gửi cho broker.
- provider_resource_id: định danh tài nguyên do API nhà cung cấp trả về sau khi tạo tài nguyên.

Ví dụ, platform gửi yêu cầu tạo instance với ID osb-instance-7f2a. Broker gọi API của nhà cung cấp để tạo database. Nhà cung cấp trả về resource ID db-98135. Broker lưu quan hệ giữa hai giá trị này.

~~~text
Platform
  instance_id = osb-instance-7f2a
          |
          v
Service broker
  service_instance_id = osb-instance-7f2a
  provider_resource_id = db-98135
          |
          v
Provider
  database ID = db-98135
~~~

Khi platform gửi yêu cầu deprovision cho osb-instance-7f2a, broker tra cứu bản ghi tương ứng, lấy db-98135 rồi gọi API xóa tài nguyên. Broker không cần platform biết ID nội bộ của nhà cung cấp.

Việc tách định danh mang lại một số lợi ích:

- Platform và broker duy trì hợp đồng OSB ổn định dù nhà cung cấp thay đổi cách đặt ID.
- Broker có thể đổi nhà cung cấp hoặc chuyển tài nguyên sang hệ thống khác mà vẫn giữ định danh instance phía platform theo chính sách tương thích.
- Thông tin chi tiết của provider được giữ trong lớp tích hợp của broker.
- Broker có thể quản lý trạng thái và phục hồi sau khi tiến trình ứng dụng khởi động lại.
- Các thao tác vòng đời có thể tìm đúng tài nguyên mà không phải tìm kiếm bằng tên hiển thị hoặc tham số người dùng.

Không nên mặc định provider_resource_id bằng instance_id. Một số API cho phép client cung cấp tên tài nguyên, nhưng nhà cung cấp vẫn có thể trả về một ID riêng. Ngay cả khi hai giá trị tình cờ giống nhau trong một triển khai, mô hình dữ liệu vẫn nên thể hiện rõ hai vai trò.

## 2. Luồng ánh xạ khi provision

Một luồng provision điển hình gồm các bước:

1. Platform gửi request tới endpoint service_instances với instance_id.
2. Broker xác thực platform, kiểm tra service_id, plan_id và các tham số.
3. Broker xác định tenant hoặc scope từ context đáng tin cậy.
4. Broker tạo bản ghi service instance ở trạng thái đang cấp phát.
5. Broker gọi API provider để tạo tài nguyên.
6. Provider trả về resource ID và có thể trả thêm operation ID nếu xử lý bất đồng bộ.
7. Broker lưu resource ID, trạng thái provider và các thông tin quản lý cần thiết.
8. Khi tài nguyên sẵn sàng, broker chuyển instance sang trạng thái hoạt động.
9. Broker trả phản hồi OSB phù hợp với kết quả đồng bộ hoặc bất đồng bộ.

~~~mermaid
sequenceDiagram
    participant P as Platform
    participant B as Service Broker
    participant DB as Broker Database
    participant V as Provider API
    P->>B: Provision(instance_id, service_id, plan_id)
    B->>DB: Tạo bản ghi PROVISIONING
    B->>V: Create resource
    V-->>B: provider_resource_id
    B->>DB: Lưu provider_resource_id
    B->>V: Kiểm tra trạng thái tài nguyên
    V-->>B: Ready
    B->>DB: Chuyển instance sang ACTIVE
    B-->>P: Provision thành công
~~~

Trong thực tế, provider có thể xử lý việc tạo tài nguyên trong thời gian dài. Khi đó broker lưu provider operation ID và trạng thái đang chạy, rồi cập nhật qua worker hoặc endpoint last_operation. Dù xử lý đồng bộ hay bất đồng bộ, quan hệ giữa instance_id và tài nguyên provider phải được lưu bền vững.

## 3. Mô hình dữ liệu ánh xạ

Một bảng service_instance có thể lưu thông tin cốt lõi của mỗi instance. Thiết kế cụ thể phụ thuộc database và provider, nhưng nên có các nhóm trường sau:

| Trường | Mục đích |
|---|---|
| service_instance_id | ID do platform gửi, dùng làm khóa tra cứu chính |
| service_id | Service definition được chọn từ catalog |
| plan_id | Plan được chọn khi provision |
| tenant_id | Tenant hoặc scope sở hữu instance |
| platform_context | Thông tin context cần thiết để phục vụ vòng đời |
| provider_name | Nhà cung cấp hoặc adapter được dùng |
| provider_account | Tài khoản, project hoặc subscription phía provider |
| provider_region | Region hoặc zone chứa tài nguyên |
| provider_resource_id | ID tài nguyên thực tế do provider trả về |
| provider_operation_id | ID thao tác bất đồng bộ phía provider, nếu có |
| state | Trạng thái vòng đời nội bộ |
| request_fingerprint | Dấu vân tay của yêu cầu provision ban đầu |
| created_at / updated_at | Thời điểm tạo và cập nhật |
| version | Số phiên bản để kiểm soát cập nhật đồng thời |

Ví dụ lược đồ SQL:

~~~sql
CREATE TABLE service_instance (
    service_instance_id VARCHAR(255) PRIMARY KEY,
    service_id VARCHAR(255) NOT NULL,
    plan_id VARCHAR(255) NOT NULL,
    tenant_id VARCHAR(255) NOT NULL,
    provider_name VARCHAR(100) NOT NULL,
    provider_account VARCHAR(255),
    provider_region VARCHAR(100),
    provider_resource_id VARCHAR(512),
    provider_operation_id VARCHAR(512),
    state VARCHAR(40) NOT NULL,
    request_fingerprint VARCHAR(128) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    version BIGINT NOT NULL DEFAULT 0
);
~~~

Khóa chính service_instance_id giúp broker tra cứu instance theo ID mà platform gửi. Nếu một broker phục vụ nhiều platform độc lập có thể tạo ID trùng nhau, cần xác định namespace hoặc phạm vi định danh phù hợp. Ví dụ, có thể dùng khóa ghép platform_id + service_instance_id nếu hợp đồng triển khai cho phép nhiều không gian định danh.

Thông tin provider cần đủ để tìm đúng tài nguyên. Chỉ lưu provider_resource_id có thể chưa đủ nếu cùng một provider có nhiều tài khoản hoặc region. Khi gọi API provider, broker có thể cần cả account, project, subscription, region hoặc cluster tương ứng.

Không nên dùng tên database, tên namespace hoặc tên hiển thị làm khóa duy nhất nếu provider cho phép đổi tên. Các tên đó có thể được lưu để hỗ trợ quan sát, nhưng thao tác quản lý nên dựa trên định danh ổn định do provider cấp hoặc khóa tra cứu đã được thiết kế rõ.

## 4. Lưu thông tin binding riêng với service instance

Service instance và service binding có vòng đời khác nhau. Một instance có thể có nhiều binding, mỗi binding thường đại diện cho quyền truy cập của một consumer.

Có thể lưu bảng service_binding riêng:

~~~sql
CREATE TABLE service_binding (
    binding_id VARCHAR(255) PRIMARY KEY,
    service_instance_id VARCHAR(255) NOT NULL,
    tenant_id VARCHAR(255) NOT NULL,
    provider_binding_id VARCHAR(512),
    state VARCHAR(40) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    CONSTRAINT fk_binding_instance
        FOREIGN KEY (service_instance_id)
        REFERENCES service_instance(service_instance_id)
);
~~~

Khi platform yêu cầu bind, broker tra cứu service instance theo instance_id rồi tạo thông tin binding tương ứng. Nếu provider có đối tượng riêng cho binding, broker lưu thêm provider_binding_id. Nếu binding chỉ tạo database user hoặc credential, broker có thể lưu tham chiếu tới secret trong secret store thay vì lưu credential dạng rõ trong bảng.

Khi unbind, broker dùng binding_id để tìm đúng binding và thu hồi quyền truy cập. Việc unbind thường không xóa service instance hay tài nguyên gốc. Deprovision mới là thao tác thu hồi instance, vì vậy không nên xóa bản ghi service instance khi một binding bị thu hồi.

## 5. Thiết kế entity trong Spring Boot

Với Spring Boot và Spring Data JPA, có thể biểu diễn service instance bằng một entity. Ví dụ dưới đây minh họa các trường định danh, trạng thái và optimistic locking:

~~~java
package com.example.broker.persistence;

import java.time.Instant;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

@Entity
@Table(name = "service_instance")
public class ServiceInstanceEntity {

    @Id
    @Column(name = "service_instance_id", nullable = false)
    private String serviceInstanceId;

    @Column(name = "service_id", nullable = false)
    private String serviceId;

    @Column(name = "plan_id", nullable = false)
    private String planId;

    @Column(name = "tenant_id", nullable = false)
    private String tenantId;

    @Column(name = "provider_name", nullable = false)
    private String providerName;

    @Column(name = "provider_account")
    private String providerAccount;

    @Column(name = "provider_region")
    private String providerRegion;

    @Column(name = "provider_resource_id")
    private String providerResourceId;

    @Column(name = "provider_operation_id")
    private String providerOperationId;

    @Enumerated(EnumType.STRING)
    @Column(name = "state", nullable = false)
    private InstanceState state;

    @Column(name = "request_fingerprint", nullable = false)
    private String requestFingerprint;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    @Version
    private long version;

    protected ServiceInstanceEntity() {
    }

    public String getServiceInstanceId() {
        return serviceInstanceId;
    }

    public String getProviderResourceId() {
        return providerResourceId;
    }

    public void setProviderResourceId(String providerResourceId) {
        this.providerResourceId = providerResourceId;
    }

    public InstanceState getState() {
        return state;
    }

    public void setState(InstanceState state) {
        this.state = state;
    }

    public String getProviderOperationId() {
        return providerOperationId;
    }

    public void setProviderOperationId(String providerOperationId) {
        this.providerOperationId = providerOperationId;
    }
}
~~~

Trạng thái nội bộ có thể được biểu diễn bằng enum:

~~~java
public enum InstanceState {
    PROVISIONING,
    ACTIVE,
    UPDATE_IN_PROGRESS,
    DEPROVISIONING,
    FAILED,
    UNKNOWN
}
~~~

Các trạng thái trên là mô hình nội bộ minh họa. Broker có thể bổ sung trạng thái như PROVISIONING_UNKNOWN hoặc DELETE_PENDING nếu cần phân biệt rõ hơn các tình huống phục hồi.

Repository cung cấp thao tác tìm theo ID:

~~~java
public interface ServiceInstanceRepository
        extends JpaRepository<ServiceInstanceEntity, String> {

    Optional<ServiceInstanceEntity> findByServiceInstanceId(
            String serviceInstanceId);

    List<ServiceInstanceEntity> findByTenantIdAndState(
            String tenantId, InstanceState state);
}
~~~

Khi triển khai thực tế, cần bổ sung constructor, factory method hoặc mapper để tạo entity nhất quán. Không nên cho nhiều lớp nghiệp vụ tự sửa trực tiếp các trường định danh và trạng thái mà không đi qua quy tắc chuyển trạng thái của broker.

## 6. Lấy instance_id từ request OSB và tra cứu bản ghi

Trong các thao tác vòng đời, platform đưa instance_id vào URL. Spring Cloud Open Service Broker nhận request và chuyển thông tin tới service handler theo abstraction của framework. Handler cần dùng ID đó để tìm bản ghi nội bộ.

Một service quản lý có thể cung cấp method tra cứu:

~~~java
@Service
public class ServiceInstanceRegistry {

    private final ServiceInstanceRepository repository;

    public ServiceInstanceRegistry(ServiceInstanceRepository repository) {
        this.repository = repository;
    }

    public ServiceInstanceEntity require(String instanceId) {
        return repository.findByServiceInstanceId(instanceId)
                .orElseThrow(() -> new InstanceNotFoundException(instanceId));
    }
}
~~~

InstanceNotFoundException là exception nghiệp vụ của ứng dụng. Lớp chuyển đổi lỗi OSB cần ánh xạ nó sang response phù hợp với hợp đồng của endpoint và phiên bản framework.

Khi tra cứu, broker phải kiểm tra tenant hoặc context của request có khớp với tenant sở hữu bản ghi hay không. Chỉ biết instance_id không đủ để cho phép người gọi thao tác trên instance. Nếu một request đã được xác thực nhưng thuộc tenant khác, broker cần từ chối theo chính sách phân quyền.

Không nên tìm instance bằng cách nhận tenant_id từ một parameter tùy ý rồi bỏ qua danh tính đã xác thực. Context của platform cần được kiểm tra theo cấu hình tích hợp và danh tính của platform client.

## 7. Tạo bản ghi ánh xạ trước khi gọi provider

Một thiết kế hữu ích là tạo bản ghi nội bộ ở trạng thái PROVISIONING trước khi gọi API provider. Điều này giúp broker có dấu vết bền vững về request ngay cả khi tiến trình bị dừng giữa chừng.

Luồng xử lý:

1. Kiểm tra instance_id đã tồn tại hay chưa.
2. Nếu chưa có, tạo bản ghi PROVISIONING với service ID, plan ID, tenant và request fingerprint.
3. Commit bản ghi trước khi gọi provider.
4. Gọi provider để tạo tài nguyên.
5. Lưu provider_resource_id và operation ID nếu có.
6. Theo dõi cho tới khi tài nguyên sẵn sàng.
7. Chuyển trạng thái sang ACTIVE.

Không nên giữ một transaction database mở trong suốt thời gian gọi API cloud có thể mất vài phút. Transaction dài dễ giữ khóa, làm cạn connection pool và gây tranh chấp. Thay vào đó, dùng các transaction ngắn để ghi trạng thái trước và sau từng bước bên ngoài.

Có thể minh họa bằng service orchestration:

~~~java
public ProvisionResult provision(ProvisionCommand command) {
    ServiceInstanceEntity instance =
            instanceWriter.createProvisioningRecord(command);

    ProviderCreateResult result =
            providerClient.createResource(
                    command.providerRequest(),
                    command.idempotencyKey());

    instanceWriter.attachProviderResource(
            instance.getServiceInstanceId(),
            result.resourceId(),
            result.operationId());

    if (result.completed()) {
        instanceWriter.markActive(instance.getServiceInstanceId());
        return ProvisionResult.completed();
    }

    return ProvisionResult.inProgress(result.operationId());
}
~~~

Các method instanceWriter nên thực hiện transaction ngắn và kiểm tra trạng thái hiện tại. Ví dụ chỉ cho phép attach provider resource khi instance còn ở trạng thái PROVISIONING hoặc một trạng thái phục hồi được xác định trước.

Đoạn code là cấu trúc minh họa cho orchestration, không phải một implementation hoàn chỉnh của ProvisionService trong mọi phiên bản Spring Cloud Open Service Broker. Cần ánh xạ kết quả sang kiểu response mà phiên bản framework đang dùng yêu cầu.

## 8. Idempotency khi platform gửi lại provision

Platform có thể retry khi timeout hoặc mất kết nối. Ví dụ broker đã nhận request, provider đã tạo database nhưng response bị mất trên đường truyền. Platform không biết tài nguyên đã được tạo hay chưa và gửi lại request với cùng instance_id.

Broker phải nhận diện request lặp để không tạo thêm tài nguyên. Có thể dùng instance_id làm khóa tra cứu chính và kết hợp với request fingerprint:

- Nếu chưa có bản ghi, bắt đầu provision.
- Nếu đã có bản ghi với cùng service ID, plan ID và nội dung yêu cầu tương đương, tiếp tục hoặc trả kết quả dựa trên trạng thái hiện tại.
- Nếu đã có bản ghi nhưng request mới có service hoặc plan khác, từ chối xung đột theo hợp đồng OSB.
- Nếu instance đang provision, không khởi tạo một thao tác provider thứ hai.
- Nếu instance đã ACTIVE, trả kết quả phù hợp với ngữ nghĩa idempotency và trạng thái hiện tại.

Request fingerprint có thể được tạo từ các trường có ý nghĩa của request như service ID, plan ID, tenant context đã chuẩn hóa và parameters đã canonicalize. Không đưa secret thô vào fingerprint. Nếu request chứa credential hoặc dữ liệu nhạy cảm, cần xử lý riêng bằng cách loại bỏ hoặc dùng cơ chế hash có khóa phù hợp.

Provider cũng nên nhận idempotency key ổn định nếu API của họ hỗ trợ. Có thể dùng instance_id kết hợp với operation type và số lần thay đổi logic. Với lần provision đầu, một khóa ổn định giúp provider trả lại cùng kết quả khi broker retry lệnh tạo tài nguyên.

Nếu provider không hỗ trợ idempotency key, broker có thể dùng deterministic resource name hoặc tag chứa correlation ID để tìm tài nguyên đã được tạo trước khi gửi lệnh tạo mới. Cách này phụ thuộc khả năng truy vấn và tính duy nhất của provider.

## 9. Xử lý cửa sổ lỗi giữa provider và database broker

Một tình huống khó xảy ra khi provider đã tạo tài nguyên thành công nhưng broker chưa kịp lưu provider_resource_id.

Ví dụ:

1. Broker tạo bản ghi PROVISIONING.
2. Broker gửi lệnh tạo database.
3. Provider tạo database db-98135.
4. Provider trả response.
5. Tiến trình broker bị dừng trước khi cập nhật database nội bộ.

Sau khi khởi động lại, bản ghi vẫn ở trạng thái PROVISIONING và chưa có provider_resource_id. Nếu broker tạo lại tài nguyên mà không kiểm tra, có thể phát sinh database thứ hai.

Để giảm rủi ro, có thể kết hợp các cơ chế:

- Provider idempotency key: gửi cùng một key cho các lần retry của cùng thao tác.
- Deterministic name: đặt tên tài nguyên dựa trên một định danh ổn định đã được kiểm tra giới hạn và quy tắc của provider.
- Provider tags/labels: gắn service_instance_id hoặc correlation ID vào metadata tài nguyên.
- Lookup before create: trước khi tạo lại, tìm tài nguyên có tag hoặc tên tương ứng.
- Reconciliation: quét bản ghi đang provision và đối chiếu với tài nguyên thực tế.
- Operation journal: lưu từng bước và mã thao tác provider để có thể tiếp tục.

Không nên dùng instance_id trực tiếp làm tên tài nguyên nếu nó có thể chứa ký tự không hợp lệ, vượt độ dài hoặc làm lộ định danh nội bộ. Có thể tạo tên rút gọn hoặc mã hóa phù hợp, nhưng phải lưu quan hệ giữa tên đó và instance_id.

## 10. Lưu trạng thái thao tác bất đồng bộ

Một số provider trả operation ID thay vì tạo xong tài nguyên ngay. Ví dụ API tạo database trả task-456 với trạng thái ACCEPTED. Broker cần lưu provider_operation_id cùng service_instance_id.

Bản ghi thao tác riêng có thể có cấu trúc:

~~~sql
CREATE TABLE provider_operation (
    operation_id VARCHAR(255) PRIMARY KEY,
    service_instance_id VARCHAR(255) NOT NULL,
    operation_type VARCHAR(40) NOT NULL,
    provider_operation_id VARCHAR(512),
    state VARCHAR(40) NOT NULL,
    started_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,
    last_error_code VARCHAR(100),
    FOREIGN KEY (service_instance_id)
        REFERENCES service_instance(service_instance_id)
);
~~~

Khi platform gọi last_operation, broker tra cứu trạng thái thao tác nội bộ dựa trên service_instance_id và operation identifier mà broker đã trả về theo hợp đồng OSB. Nếu provider còn xử lý, broker báo đang thực hiện; khi provider hoàn tất, broker cập nhật bản ghi instance và operation.

Không nên phụ thuộc vào một request HTTP đang mở để giữ trạng thái. Broker có thể chạy nhiều replica, restart hoặc nhận request last_operation từ một replica khác. Trạng thái phải được lưu trong kho dùng chung và có khả năng đọc nhất quán phù hợp.

Cũng cần phân biệt operation ID của broker với operation ID của provider. Platform theo dõi thao tác theo contract OSB; broker dùng provider operation ID để gọi API nhà cung cấp. Hai ID có thể khác nhau và cần được ánh xạ nếu framework hoặc logic nghiệp vụ yêu cầu.

## 11. Dùng ánh xạ trong update

Khi platform yêu cầu update service instance, broker tra cứu instance_id để lấy:

- provider_resource_id hiện tại.
- service ID và plan ID hiện tại.
- tenant sở hữu instance.
- provider account và region.
- trạng thái instance và operation đang chạy.

Sau đó broker xác minh service ID và plan đích trong request, kiểm tra khả năng update và gọi provider bằng provider_resource_id.

Ví dụ, platform yêu cầu nâng cấp PostgreSQL từ plan small sang production. Broker không tạo database mới theo instance_id khác. Nó tìm database đang gắn với instance_id đó và yêu cầu provider thay đổi compute hoặc storage theo chính sách. Nếu provider yêu cầu tạo tài nguyên mới để migration, broker phải lưu thêm mapping hoặc quan hệ thay thế và chỉ chuyển mapping chính sau khi migration thành công.

Không nên cập nhật plan_id trong bản ghi nội bộ trước khi provider hoàn thành thay đổi nếu thao tác có thể thất bại. Có thể lưu target_plan_id riêng trong operation để thể hiện mục tiêu đang thực hiện. Khi hoàn tất, broker commit plan mới cùng trạng thái provider thực tế.

## 12. Dùng ánh xạ trong binding và deprovision

### 12.1. Binding

Khi platform gửi yêu cầu bind với instance_id và binding_id, broker tra cứu service instance, xác minh tenant, trạng thái ACTIVE và khả năng binding. Sau đó broker dùng provider_resource_id để tạo quyền truy cập hoặc đối tượng binding ở provider.

Ví dụ với PostgreSQL:

- instance_id ánh xạ tới database ID db-98135.
- binding_id xác định một consumer cụ thể.
- Broker tạo database user riêng cho binding đó.
- Broker lưu provider binding ID hoặc tham chiếu secret.
- Broker trả credentials qua response binding theo hợp đồng OSB.

Không nên tạo một credential dùng chung cho tất cả binding nếu cần thu hồi quyền riêng cho từng ứng dụng. Secret cần được bảo vệ và không được ghi vào log.

### 12.2. Deprovision

Khi platform yêu cầu deprovision, broker tra cứu instance_id và lấy provider_resource_id. Broker xác minh service/plan/context cần thiết rồi gọi provider để xóa tài nguyên.

Nếu provider trả trạng thái đang xóa, broker giữ bản ghi ở DEPROVISIONING và theo dõi operation. Chỉ khi xác nhận tài nguyên đã được thu hồi, broker mới đánh dấu instance đã deprovision hoặc chuyển bản ghi sang trạng thái lưu trữ theo chính sách.

Việc giữ lại tombstone hoặc bản ghi lịch sử có thể hữu ích để xử lý retry và điều tra. Nếu xóa hẳn bản ghi ngay sau khi provider xóa, broker có thể mất dấu vết để nhận diện request DELETE lặp hoặc phát hiện tài nguyên mồ côi. Chính sách lưu trữ cần cân bằng giữa khả năng idempotency, audit và yêu cầu bảo vệ dữ liệu.

## 13. Tenant context và phân tách quyền sở hữu

Một broker có thể phục vụ nhiều organization, space, project hoặc tenant. Khi đó, mapping không chỉ là instance_id sang provider_resource_id; nó còn phải ghi nhận ai sở hữu instance.

Thông tin tenant có thể đến từ context mà platform gửi cùng request, nhưng broker phải kiểm tra nó trong phạm vi danh tính platform đã xác thực. Không được coi mọi trường trong request body là bằng chứng quyền sở hữu.

Khi truy xuất một instance, cần kiểm tra đồng thời:

- instance_id tồn tại.
- tenant hoặc context của caller được phép truy cập instance.
- service ID và plan ID khớp với thao tác.
- trạng thái hiện tại cho phép thực hiện thao tác.
- provider account/region được lấy từ bản ghi đáng tin cậy, không lấy từ input tùy ý.

Nếu broker dùng một tài khoản cloud chung để tạo tài nguyên cho nhiều tenant, provider_resource_id cần được lưu cùng provider account và tenant mapping. Nếu mỗi tenant có tài khoản provider riêng, cần lưu thông tin tham chiếu tới credential hoặc secret manager phù hợp. Không lưu access key dạng rõ trong bản ghi service instance.

## 14. Phục hồi và đối soát mapping

Theo thời gian, trạng thái broker và provider có thể lệch nhau. Ví dụ, người vận hành xóa thủ công database trên cloud, hoặc broker mất kết nối sau khi provider hoàn tất thao tác.

Reconciliation là quy trình đối chiếu bản ghi nội bộ với tài nguyên thực tế để phát hiện và xử lý sai lệch.

Một số trường hợp cần phát hiện:

| Trạng thái broker | Trạng thái provider | Cách xử lý gợi ý |
|---|---|---|
| PROVISIONING, chưa có resource ID | Có tài nguyên mang tag tương ứng | Gắn lại resource ID và tiếp tục kiểm tra |
| ACTIVE, có resource ID | Provider không tìm thấy tài nguyên | Đánh dấu UNKNOWN hoặc cần xử lý, kiểm tra xóa ngoài hệ thống |
| ACTIVE | Tài nguyên tồn tại nhưng cấu hình khác plan | Cảnh báo drift và quyết định reconcile hoặc yêu cầu operator |
| DEPROVISIONING | Provider đã xóa tài nguyên | Hoàn tất deprovision và giải phóng trạng thái |
| Không có bản ghi broker | Provider có tài nguyên gắn tag broker | Xác định orphan resource và xử lý theo chính sách |
| PROVISIONING quá thời hạn | Provider operation vẫn chạy | Tiếp tục polling hoặc đưa vào hàng đợi phục hồi |

Không nên tự động xóa mọi tài nguyên không có bản ghi broker ngay khi phát hiện. Tài nguyên có thể thuộc hệ thống khác hoặc đang trong một quy trình di chuyển. Cần dựa vào tag, provider account, thời gian, audit và quy tắc ownership để xác định tài nguyên mồ côi.

Reconciliation nên có khả năng chạy lặp an toàn, ghi lại hành động và tạo cảnh báo khi không thể tự động sửa. Với số lượng instance lớn, có thể phân trang theo provider, region hoặc tenant và đặt giới hạn tốc độ để không gây tải quá mức lên API nhà cung cấp.

## 15. Bảo mật thông tin ánh xạ

Mapping chứa các định danh nội bộ và thông tin có thể giúp truy cập tài nguyên. Cần bảo vệ dữ liệu này:

- Giới hạn quyền đọc/ghi bảng service_instance và service_binding.
- Không trả provider_resource_id nếu platform không cần biết.
- Không lưu credential dạng rõ trong bảng mapping.
- Lưu tham chiếu secret hoặc mã định danh secret trong secret manager.
- Mã hóa dữ liệu nhạy cảm khi lưu và khi truyền.
- Ghi audit cho các thao tác tạo, đổi mapping, xóa và reconciliation.
- Không ghi request chứa secret hoặc provider response nhạy cảm vào log.
- Kiểm tra tenant ownership trước mọi thao tác dựa trên instance_id.

ID khó đoán không phải cơ chế phân quyền. Kể cả khi instance_id là UUID ngẫu nhiên, broker vẫn phải xác thực caller và kiểm tra tenant trước khi cho phép thao tác.

## 16. Lỗi thường gặp khi ánh xạ instance

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Deprovision không tìm thấy tài nguyên | Chỉ lưu instance_id, không lưu provider_resource_id hoặc provider account | Lưu đầy đủ thông tin định tuyến tới provider |
| Retry provision tạo hai database | Không có idempotency key hoặc lookup trước khi create | Dùng provider token, deterministic tag và reconciliation |
| Update tác động nhầm tài nguyên | Tra cứu bằng tên hiển thị hoặc tham số không đáng tin cậy | Tra cứu bằng instance_id và mapping đã lưu |
| Request của tenant khác truy cập instance | Không kiểm tra tenant ownership | Kiểm tra context với danh tính đã xác thực |
| Broker restart làm mất trạng thái | Chỉ lưu mapping trong memory | Dùng database bền vững |
| Nhiều replica ghi đè trạng thái | Không kiểm soát concurrency | Dùng optimistic locking hoặc transaction |
| Provider đã tạo resource nhưng DB broker chưa lưu ID | Crash giữa hai hệ thống | Dùng idempotency, tag và reconciliation |
| Unbind xóa nhầm service instance | Gộp dữ liệu binding và instance | Quản lý hai vòng đời bằng hai bản ghi riêng |
| Xóa record ngay sau deprovision khiến retry khó xử lý | Không giữ tombstone hoặc lịch sử | Lưu trạng thái deprovisioned theo thời hạn chính sách |
| Provider ID không đủ để định tuyến request | Thiếu account, project hoặc region | Lưu provider scope cùng resource ID |

## 17. Quy trình triển khai mapping trong Spring Cloud broker

Khi xây dựng chức năng ánh xạ instance_id, có thể thực hiện theo trình tự:

1. Xác định platform nào gọi broker và phạm vi duy nhất của instance_id.
2. Thiết kế entity service instance, binding và provider operation.
3. Chọn database bền vững và tạo khóa, index, ràng buộc cần thiết.
4. Lưu service ID, plan ID, tenant context và provider scope.
5. Xây dựng repository tra cứu theo instance_id.
6. Xây dựng provider adapter trả resource ID và operation ID.
7. Tạo bản ghi PROVISIONING trước khi gọi provider.
8. Thực hiện idempotency và xử lý request lặp.
9. Cập nhật mapping sau khi provider trả kết quả.
10. Dùng mapping trong update, binding, unbind và deprovision.
11. Bổ sung reconciliation để phục hồi cửa sổ lỗi giữa broker và provider.
12. Kiểm thử nhiều replica, timeout, retry, tenant mismatch và thao tác provider thất bại.

Nên tách các lớp theo trách nhiệm:

- OSB handler nhận request và chuyển dữ liệu giao thức sang command nghiệp vụ.
- Instance service quản lý trạng thái và mapping.
- Repository lưu dữ liệu bền vững.
- Provider adapter gọi API nhà cung cấp.
- Operation coordinator theo dõi thao tác dài.
- Reconciliation worker đối chiếu trạng thái broker và provider.

Cách phân tách này giúp thay đổi provider mà không làm thay đổi logic định danh instance của platform.

## 18. Checklist kiểm tra mapping

- [ ] instance_id do platform gửi được lưu bền vững.
- [ ] provider_resource_id được lưu riêng và không bị nhầm với instance_id.
- [ ] Mapping bao gồm provider account, project hoặc region khi cần.
- [ ] Service ID và plan ID được lưu để xử lý vòng đời.
- [ ] Tenant ownership được xác định và kiểm tra ở mọi thao tác.
- [ ] Bản ghi PROVISIONING được lưu trước khi gọi provider.
- [ ] Request lặp không tạo tài nguyên trùng lặp.
- [ ] Có cách phục hồi khi provider tạo tài nguyên nhưng broker chưa lưu ID.
- [ ] Provider operation ID được lưu cho thao tác bất đồng bộ.
- [ ] Update, binding và deprovision đều tra cứu mapping đúng.
- [ ] Binding được lưu tách khỏi service instance.
- [ ] Deprovision retry không xóa hoặc giải phóng trạng thái nhiều lần.
- [ ] Trạng thái được bảo vệ khi nhiều replica cùng cập nhật.
- [ ] Có reconciliation và phát hiện orphan resource.
- [ ] Secret không được lưu dạng rõ trong bảng mapping hoặc log.
- [ ] Có audit cho các thay đổi định danh và trạng thái.

Ánh xạ instance_id sang tài nguyên của nhà cung cấp là nền tảng để broker quản lý vòng đời service instance một cách đáng tin cậy. Platform giữ định danh của mình; broker lưu quan hệ tới provider resource ID, scope và trạng thái; provider adapter thực hiện thao tác trên tài nguyên thật. Khi mapping được lưu bền vững, có kiểm tra tenant, idempotency và reconciliation, broker có thể xử lý retry, restart và thay đổi nhà cung cấp mà vẫn quản lý đúng instance đã được platform tạo.

