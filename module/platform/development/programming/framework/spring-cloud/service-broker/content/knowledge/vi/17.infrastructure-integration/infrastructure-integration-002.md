# Ánh xạ gói và tham số sang yêu cầu API của nhà cung cấp

Một service broker công bố service và service plan theo Open Service Broker API (OSB API), nhưng tài nguyên thực tế thường được tạo bởi một hệ thống khác: cloud provider, managed database, Kubernetes operator hoặc nền tảng hạ tầng nội bộ. Broker phải chuyển lựa chọn sản phẩm mà platform gửi thành yêu cầu kỹ thuật mà backend hiểu được. Công việc này là ánh xạ plan và parameters sang API của nhà cung cấp.

Trong module **SPRING_CLOUD_SERVICE_BROKER**, cần giữ ổn định ý nghĩa của service plan trong catalog, đồng thời cho phép mỗi provider có cách biểu diễn tài nguyên riêng. Plan production có thể được triển khai thành managed database tier trên cloud, một custom resource do Kubernetes operator quản lý hoặc một cụm database trong private cloud. Parameters của consumer được kiểm tra theo schema, giới hạn plan, tenant policy và khả năng backend trước khi trở thành các field trong request provider.

## 1. Từ hợp đồng OSB đến API hạ tầng

Platform không nên phải biết broker dùng provider nào hoặc request backend có cấu trúc ra sao. Platform chọn service và plan, gửi parameters theo contract công khai. Broker chịu trách nhiệm diễn giải lựa chọn đó và thực hiện provisioning.

Luồng tổng quát:

~~~mermaid
flowchart TD
    A["OSB provision request"] --> B["Resolve service_id + plan_id"]
    B --> C["Validate parameters by schema"]
    C --> D["Resolve tenant policy and quota"]
    D --> E["Select provider target and capabilities"]
    E --> F["Build normalized resource specification"]
    F --> G["Map specification to provider request"]
    G --> H["Call provider API / Kubernetes API"]
    H --> I["Track long-running operation"]
    I --> J["Persist resource identity and plan snapshot"]
~~~

Mỗi bước có một trách nhiệm riêng:

1. Tra cứu service và plan mà broker đã công bố.
2. Xác thực parameters theo schema tương ứng.
3. Kiểm tra entitlement, quota và policy của tenant.
4. Chọn provider account, region, cluster hoặc deployment target.
5. Tạo resource specification trung gian, độc lập với nhà cung cấp.
6. Chuyển specification thành request hoặc manifest cụ thể.
7. Gọi backend, xử lý response và theo dõi công việc dài.
8. Lưu resource ID, cấu hình thực tế và phiên bản mapping đã dùng.

Nếu handler OSB tự ghép chuỗi JSON của provider từ request parameters, logic nghiệp vụ sẽ phụ thuộc chặt vào backend. Một thay đổi provider có thể làm ảnh hưởng catalog, validation và lifecycle handler. Tách lớp ánh xạ giúp broker thay backend mà không buộc platform thay đổi cách chọn plan.

## 2. Phân biệt service plan, parameters và provider SKU

Ba khái niệm cần được giữ riêng:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Service plan | Cấp dịch vụ broker công bố cho platform | PostgreSQL Production |
| Parameters | Tùy chọn consumer gửi để cấu hình instance | storage_gb = 500, database_name = orders |
| Provider SKU/profile | Cách provider biểu diễn năng lực hạ tầng | db.m6i.xlarge, Premium SSD, storage class premium |

Plan thể hiện cam kết sản phẩm của broker, chẳng hạn năng lực tính toán, dung lượng, backup, HA hoặc giới hạn kết nối. SKU là chi tiết triển khai có thể thay đổi theo provider, region và thời điểm. Parameters chỉ được phép tùy chỉnh các thuộc tính mà contract của service và plan cho phép.

Ví dụ, plan PostgreSQL Production có thể cam kết:

- Tối thiểu 4 vCPU và 16 GiB RAM.
- Dung lượng mặc định 500 GiB.
- Backup hằng ngày và retention 14 ngày.
- Có khả năng failover hoặc topology HA.
- Mã hóa storage và kết nối TLS.

Một provider có thể đáp ứng bằng SKU managed database cụ thể; provider khác có thể dùng node pool, persistent volume và operator. Broker không nên công bố SKU nội bộ làm plan ID nếu người dùng cần một lựa chọn sản phẩm ổn định qua nhiều backend.

Parameters như database name hoặc storage size không được tự do vượt qua giới hạn plan. Nếu plan chỉ cho phép 100–500 GiB, request 2 TiB phải bị từ chối trước khi gọi provider API, kể cả provider có hỗ trợ dung lượng lớn hơn.

## 3. Thiết kế Plan Profile nội bộ

Mỗi plan công khai nên được liên kết với một profile nội bộ. Profile chứa các thuộc tính kỹ thuật và policy để tạo resource specification.

Ví dụ YAML minh họa:

~~~yaml
service:
  id: svc-postgresql
  plans:
    plan-postgresql-production:
      profileVersion: "2026-01"
      capabilities:
        highAvailability: true
        backup: true
        pointInTimeRecovery: true
        encryptionAtRest: true
      compute:
        minimumVcpu: 4
        memoryGiB: 16
      storage:
        defaultGiB: 500
        minimumGiB: 100
        maximumGiB: 2000
      backup:
        defaultRetentionDays: 14
        maximumRetentionDays: 35
      connection:
        maximumConnections: 500
~~~

Đây là cấu hình nội bộ minh họa, không phải schema chuẩn của OSB API. Có thể lưu profile trong database, configuration repository hoặc service quản lý cấu hình. Cần version hóa profile vì instance đã provision phải tiếp tục được quản lý theo những lựa chọn đã dùng, ngay cả khi profile mới được triển khai.

Một profile nên mô tả năng lực và giới hạn ở mức sản phẩm, không nhất thiết chứa toàn bộ field đặc thù của một provider. Provider-specific mapping được quản lý ở lớp tiếp theo.

### Vì sao cần profile version?

Giả sử instance được tạo bằng profile version 2026-01 với backup retention 14 ngày. Sau đó broker phát hành profile 2026-02 với chính sách backup 30 ngày. Worker đang xử lý operation cũ không nên đọc cấu hình mới một cách vô tình.

Khi nhận provision, broker lưu profile version và resource specification đã resolve vào operation hoặc instance snapshot. Worker dùng snapshot đó để thực hiện đúng request đã được chấp nhận. Các thao tác update sau này có thể dùng profile version mới theo policy migration đã công bố.

## 4. Schema parameters theo service và plan

Catalog OSB có thể công bố schema cho parameters của thao tác create/update nếu broker hỗ trợ. Server vẫn phải thực hiện validation; không thể giả định platform luôn kiểm tra schema.

Ví dụ schema rút gọn:

~~~json
{
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "database_name": {
      "type": "string",
      "minLength": 1,
      "maxLength": 40,
      "pattern": "^[a-z][a-z0-9_]*$"
    },
    "storage_gb": {
      "type": "integer",
      "minimum": 100,
      "maximum": 2000
    },
    "backup_retention_days": {
      "type": "integer",
      "minimum": 1,
      "maximum": 35
    },
    "region": {
      "type": "string",
      "enum": ["ap-southeast-1", "ap-southeast-2"]
    }
  },
  "required": ["database_name"]
}
~~~

Schema trên là ví dụ minh họa. Trong thực tế, giới hạn cần được tạo từ plan profile hoặc policy tương ứng để catalog và server-side validator không lệch nhau.

Validation gồm nhiều lớp:

- Kiểu dữ liệu và cấu trúc JSON.
- Field bắt buộc, field không hỗ trợ và giá trị null.
- Min/max, enum, pattern và giới hạn kích thước.
- Quy tắc liên hệ giữa các field.
- Giới hạn của service plan.
- Entitlement và quota của tenant.
- Khả năng của provider target đã chọn.

Ví dụ, backup_retention_days chỉ hợp lệ khi plan bật backup; storage_gb không được nhỏ hơn dung lượng đã sử dụng trong thao tác update; region phải nằm trong danh sách target mà tenant được phép sử dụng.

Không ép kiểu âm thầm từ chuỗi "500" thành số 500 nếu schema yêu cầu integer. Không chuẩn hóa mọi string bằng cách lowercase hoặc trim chung vì có thể làm thay đổi dữ liệu có ý nghĩa phân biệt hoa thường.

## 5. Chuẩn hóa parameters thành command có kiểu

Sau validation, không nên chuyển tiếp trực tiếp JSON tree tới provider adapter. Hãy map thành một command có kiểu dữ liệu rõ ràng.

Ví dụ Java:

~~~java
public record ProvisionParameters(
    String databaseName,
    Integer storageGiB,
    Integer backupRetentionDays,
    String requestedRegion
) {}

public record ResolvedPlan(
    String serviceId,
    String planId,
    String profileVersion,
    String engine,
    String engineVersion,
    String encryptionProfile,
    int minimumVcpu,
    int memoryGiB,
    int defaultStorageGiB,
    int minimumStorageGiB,
    int maximumStorageGiB,
    boolean highAvailability,
    boolean backupEnabled,
    int defaultBackupRetentionDays,
    int maximumBackupRetentionDays
) {}
~~~

Một bước resolve có thể kết hợp profile và parameters:

~~~java
public DatabaseResourceSpec resolve(
        ResolvedPlan plan,
        ProvisionParameters parameters,
        TenantPolicy tenantPolicy,
        DeploymentTarget target) {

    int storage = parameters.storageGiB() == null
        ? plan.defaultStorageGiB()
        : parameters.storageGiB();

    if (storage < plan.minimumStorageGiB()) {
        throw new InvalidProvisionParametersException(
            "Requested storage is below the allowed plan limit");
    }

    if (storage > plan.maximumStorageGiB()) {
        throw new InvalidProvisionParametersException(
            "Requested storage exceeds the selected plan limit");
    }

    if (parameters.requestedRegion() != null
            && !parameters.requestedRegion().equals(target.region())) {
        throw new InvalidProvisionParametersException(
            "Requested region does not match the selected deployment target");
    }

    int retentionDays = parameters.backupRetentionDays() == null
        ? plan.defaultBackupRetentionDays()
        : parameters.backupRetentionDays();

    if (!plan.backupEnabled() && parameters.backupRetentionDays() != null) {
        throw new InvalidProvisionParametersException(
            "The selected plan does not support backup");
    }

    if (plan.backupEnabled()
            && (retentionDays < 1
                || retentionDays > plan.maximumBackupRetentionDays())) {
        throw new InvalidProvisionParametersException(
            "Backup retention is outside the selected plan limits");
    }

    tenantPolicy.assertRegionAllowed(target.region());
    tenantPolicy.assertStorageAvailable(storage);

    return new DatabaseResourceSpec(
        parameters.databaseName(),
        plan.engine(),
        plan.engineVersion(),
        plan.minimumVcpu(),
        plan.memoryGiB(),
        storage,
        plan.highAvailability(),
        plan.backupEnabled(),
        plan.backupEnabled() ? retentionDays : 0,
        target.region(),
        target.networkProfile(),
        plan.encryptionProfile()
    );
}
~~~

Đây là pseudocode để minh họa phân lớp. Khi triển khai, kiểm tra thêm retention default/maximum, null semantics, quota reservation và cross-field constraints. Resource specification chỉ được tạo sau khi tất cả validation đã thành công.

Một command có kiểu giúp compiler và unit test phát hiện sai kiểu sớm. Provider adapter không phải đoán field nào là string, integer hay boolean, và không phải đọc lại raw request từ HTTP.

## 6. Resource specification trung gian

Resource specification là mô hình mô tả tài nguyên broker muốn tạo, độc lập với API cụ thể của provider.

Ví dụ:

~~~java
public record DatabaseResourceSpec(
    String databaseName,
    String engine,
    String engineVersion,
    int vcpu,
    int memoryGiB,
    int storageGiB,
    boolean highAvailability,
    boolean backupEnabled,
    int backupRetentionDays,
    String region,
    String networkProfile,
    String encryptionProfile
) {}
~~~

Specification có thể chứa các nhóm:

| Nhóm | Thuộc tính |
|---|---|
| Identity | Internal instance ID, tenant ID, external instance ID |
| Product | Service ID, plan ID, profile version |
| Compute | vCPU, memory, topology |
| Storage | Size, class, IOPS, encryption |
| Network | VPC, subnet, private endpoint, firewall profile |
| Availability | Replica count, zone, failover policy |
| Backup | Retention, schedule, point-in-time recovery |
| Security | Encryption, TLS, key reference, access policy |
| Placement | Provider account, region, cluster |
| Tags | Broker instance ID, tenant reference, managed-by |

Không phải mọi field đều được gửi trực tiếp đến provider. Một số field dùng để chọn account hoặc adapter, một số dùng làm tag, một số là policy nội bộ. Cần phân loại rõ field nào là cấu hình provider, field nào là metadata broker.

### Resource specification cần bất biến sau khi được chấp nhận

Khi operation đã được ghi nhận, worker nên dùng cùng specification đã resolve. Nếu profile hoặc tenant policy thay đổi trong lúc chờ, worker không tự thay đổi request đang thực thi. Nếu thay đổi cấu hình là bắt buộc vì sự cố bảo mật hoặc policy, hãy tạo một workflow thay đổi có kiểm soát và audit riêng.

## 7. Lớp Provider Mapping

Provider mapping chuyển resource specification thành request theo API của từng backend. Có thể dùng interface:

~~~java
public interface DatabaseProviderAdapter {
    ProviderProvisionResult provision(
        DatabaseResourceSpec specification,
        ProviderOperationContext context
    );

    ProviderOperationStatus getOperationStatus(
        String providerOperationId,
        ProviderOperationContext context
    );

    ProviderResourceState getResource(
        String providerResourceId,
        ProviderOperationContext context
    );
}
~~~

Mỗi adapter chịu trách nhiệm:

- Chọn endpoint và API version.
- Ánh xạ compute/storage/network/security thành field provider.
- Chọn account/project, region hoặc cluster.
- Tạo request và xác thực bằng credential phù hợp.
- Thêm idempotency token hoặc correlation tag.
- Gọi API và parse response.
- Chuyển lỗi provider thành lỗi nội bộ có phân loại.
- Trả provider resource ID và operation ID.

Plan resolver không nên biết tên field như DBInstanceClass hay storageClassName. Ngược lại, provider adapter không nên quyết định tenant có được dùng plan production hay không. Mỗi lớp giữ đúng ranh giới.

## 8. Ví dụ mapping sang managed database API

Giả sử resource specification yêu cầu:

- Engine PostgreSQL version 16.
- 4 vCPU, 16 GiB RAM.
- Storage 500 GiB.
- HA được bật.
- Backup retention 14 ngày.
- Region ap-southeast-1.

Một adapter managed database có thể chuyển thành request khái niệm:

~~~json
{
  "engine": "postgres",
  "engineVersion": "16",
  "instanceClass": "db.general.large",
  "allocatedStorage": 500,
  "multiZone": true,
  "backupRetentionPeriod": 14,
  "storageEncrypted": true,
  "region": "ap-southeast-1",
  "tags": {
    "managed-by": "spring-cloud-service-broker",
    "broker-instance": "internal-8f42",
    "tenant-ref": "tenant-commerce"
  }
}
~~~

Tên field và SKU trên chỉ minh họa. API thực tế của mỗi provider có schema, enum, giới hạn, default và version riêng. Adapter phải dùng SDK hoặc OpenAPI model của provider để tạo request đúng, không gửi payload giả định trực tiếp.

### Mapping compute

Plan có thể biểu diễn CPU và RAM ở mức sản phẩm. Provider chỉ có các instance class rời rạc. Adapter cần chọn SKU đáp ứng ít nhất các mức đã cam kết:

| Yêu cầu plan | Provider SKU minh họa | Điều kiện |
|---|---|---|
| 4 vCPU, 16 GiB | db.general.large | Đạt hoặc vượt năng lực yêu cầu |
| 8 vCPU, 32 GiB | db.general.xlarge | Đạt hoặc vượt năng lực yêu cầu |
| HA | Multi-zone hoặc primary/standby | Backend phải hỗ trợ failover |

Không chọn SKU nhỏ hơn rồi coi request thành công. Nếu target không có SKU tương thích, trả lỗi capacity/capability hoặc chọn một target khác đã được policy cho phép.

### Mapping storage

Storage 500 GiB có thể cần chuyển thành:

- Dung lượng allocated storage.
- Storage type hoặc class.
- IOPS hoặc throughput nếu plan quy định.
- Encryption at rest.
- Autoscaling limit.

Nếu provider có mức tăng dung lượng theo bậc hoặc giới hạn theo engine, adapter cần làm tròn theo quy tắc công khai và ghi lại giá trị thực tế. Không được âm thầm thay đổi dung lượng theo cách làm giảm cam kết plan.

## 9. Ví dụ mapping sang Kubernetes API

Nếu broker tích hợp Kubernetes qua operator, adapter có thể tạo custom resource thay vì trực tiếp tạo StatefulSet, Service và PersistentVolumeClaim. Operator chịu trách nhiệm quản lý các đối tượng phụ thuộc.

Ví dụ custom resource minh họa:

~~~yaml
apiVersion: database.example.io/v1
kind: PostgreSQLCluster
metadata:
  name: orders-db-prod
  namespace: data-services
  labels:
    app.kubernetes.io/managed-by: spring-cloud-service-broker
    broker.example.io/instance-ref: internal-8f42
    broker.example.io/tenant-ref: tenant-commerce
spec:
  postgresVersion: "16"
  instances: 3
  resources:
    requests:
      cpu: "4"
      memory: 16Gi
  storage:
    size: 500Gi
    storageClass: premium-encrypted
  backup:
    enabled: true
    retentionDays: 14
  security:
    tls: true
    encryptionAtRest: true
~~~

Đây là CRD giả định để minh họa cách mapping. Schema thật phụ thuộc operator được cài trên cluster. Adapter cần kiểm tra CRD/version và capability trước khi tạo object.

### Mapping các field Kubernetes

| Resource specification | Kubernetes/operator field |
|---|---|
| vCPU | resources.requests.cpu |
| memoryGiB | resources.requests.memory |
| storageGiB | spec.storage.size |
| highAvailability | spec.instances hoặc topology |
| backupEnabled | spec.backup.enabled |
| backupRetentionDays | spec.backup.retentionDays |
| networkProfile | NetworkPolicy, service hoặc endpoint config |
| encryptionProfile | StorageClass, CSI parameters hoặc operator policy |
| tenantId | Label/reference đã được allowlist |

Không đưa tenant ID hoặc dữ liệu nhạy cảm tùy ý vào label. Kubernetes label có giới hạn ký tự và giá trị; nếu cần lưu metadata lớn, dùng annotation hoặc record trong state store. Secret cần tạo qua API riêng và phân quyền namespace phù hợp, không nhúng password vào custom resource công khai.

## 10. Chọn provider target và kiểm tra capability

Cùng một plan có thể được triển khai ở nhiều region hoặc backend. Broker cần chọn target dựa trên policy và khả năng thực tế.

Các yếu tố có thể xét:

- Platform registration và region được phép.
- Tenant entitlement hoặc data residency.
- Provider account/project và quota.
- Engine/version hỗ trợ.
- Compute/storage capacity.
- HA, backup, encryption và network capability.
- Chi phí hoặc ưu tiên vận hành nếu policy có quy định.
- Trạng thái sức khỏe của cluster/provider.

Có thể mô hình hóa capability:

~~~java
public record ProviderCapabilities(
    Set<String> engines,
    Set<String> engineVersions,
    boolean highAvailability,
    boolean pointInTimeRecovery,
    boolean encryptionAtRest,
    int maximumStorageGiB,
    Set<String> supportedRegions
) {}
~~~

Resolver so sánh yêu cầu plan với capability của target:

~~~text
required_capabilities = capabilities(plan_profile)

eligible_targets = targets
    .filter(target is registered)
    .filter(target is allowed for tenant)
    .filter(target supports required_capabilities)
    .filter(target has sufficient quota/capacity)

selected_target = placement_policy.choose(eligible_targets)
~~~

Nếu không có target đáp ứng, broker cần từ chối có phân loại hoặc đưa operation vào trạng thái chờ capacity theo chính sách. Không tự hạ cấp HA, encryption hoặc backup để có thể tạo resource.

## 11. Xử lý defaults và giá trị thực tế từ provider

Provider có thể áp dụng default riêng nếu request không truyền field. Broker nên chủ động quyết định giá trị nào cần gửi và giá trị nào được để provider chọn.

Ví dụ:

- Nếu broker cam kết backup retention 14 ngày, gửi rõ giá trị 14.
- Nếu provider tự chọn maintenance window nhưng plan không cam kết giờ cụ thể, có thể để provider áp dụng default.
- Nếu encryption bắt buộc, không dựa vào default không được xác nhận.
- Nếu provider tự cấp endpoint, lấy endpoint từ response/retrieve sau khi resource sẵn sàng.

Sau khi tạo, broker nên lưu cả:

1. **Requested specification:** cấu hình broker đã yêu cầu.
2. **Effective specification:** cấu hình backend thực tế đã áp dụng hoặc provider xác nhận.
3. **Provider resource identity:** provider, account, region, resource ID.
4. **Mapping version:** phiên bản adapter/profile dùng để tạo resource.

Nếu provider làm tròn storage hoặc chọn SKU cụ thể, lưu giá trị thực tế để retrieve, update và deprovision. Không thay đổi plan ID chỉ vì provider trả về một SKU khác.

## 12. Quản lý API version và schema provider

API provider có thể thay đổi field, enum, endpoint hoặc quy tắc xác thực. Adapter nên cô lập chi tiết version:

- Chọn API version được hỗ trợ cho provider account.
- Dùng SDK/model tương ứng thay vì tự nối JSON.
- Validate request theo schema provider trước khi gửi nếu có thể.
- Không dùng field đã deprecated mà không có lý do tương thích.
- Theo dõi thay đổi enum/SKU và capability.
- Version hóa mapping profile để operation cũ tiếp tục chạy đúng.
- Có contract test với request/response mẫu theo API version.

Kubernetes cũng có API version cho từng resource/CRD. Adapter cần kiểm tra resource group/version/kind có tồn tại và schema tương thích. Không giả định mọi cluster cài cùng một operator version.

## 13. Bảo mật khi xây dựng provider request

Provider request thường chứa account, project, network, key reference hoặc secret. Cần kiểm soát nguồn của từng field:

- Tenant ID và platform scope đến từ resolver đã xác minh.
- Provider account và region đến từ deployment target được quản trị.
- Resource name được tạo hoặc validate theo naming policy.
- Network/subnet/security group phải thuộc target và tenant được phép.
- Encryption key và secret được tham chiếu từ secret manager hoặc key management service.
- Không nhận provider resource ID tùy ý từ consumer để thao tác trực tiếp.
- Backend credential dùng quyền tối thiểu và tách theo account/region nếu cần.
- Request/response log phải redaction credential, token, password và URI nhạy cảm.

Không nối parameters trực tiếp vào shell command, SQL hoặc manifest mà không có typed mapping và escaping theo đúng ngữ cảnh. Đặc biệt, không cho consumer ghi đè field như tenant label, broker ownership tag, IAM role, network isolation hoặc encryption policy.

## 14. Idempotency khi gọi provider API

Một worker có thể timeout sau khi provider đã tạo resource nhưng trước khi broker nhận response. Nếu retry với request mới hoặc tên mới, broker có thể tạo tài nguyên trùng.

Mỗi lần provision logic nên có idempotency key ổn định, ví dụ:

~~~text
provider_idempotency_key = hash(
    platform_id,
    internal_instance_id,
    provision_generation,
    provider_target_id
)
~~~

Dùng key này trong provider API nếu backend hỗ trợ. Nếu không, gắn correlation tag/label ổn định vào resource và tìm theo tag trước khi tạo lại.

Worker cần lưu operation và mapping version trước khi gọi provider. Khi timeout:

1. Tra cứu operation state.
2. Gọi provider retrieve/list theo resource ID hoặc correlation tag.
3. Nếu resource đã tồn tại và thuộc đúng instance, tiếp tục cập nhật state.
4. Nếu resource chưa tồn tại, retry với cùng idempotency key.
5. Nếu kết quả không xác định, giữ operation ở trạng thái reconciliation thay vì tạo resource mới ngay.

Idempotency tại broker không tự bảo đảm idempotency ở provider. Adapter phải dùng tính năng của provider hoặc một quy trình lookup/compensation tương đương.

## 15. Theo dõi tác vụ dài của provider

Nhiều provider trả operation ID hoặc trạng thái provisioning thay vì resource sẵn sàng ngay. Broker cần phân biệt HTTP request đã được chấp nhận với tài nguyên đã sẵn sàng.

Một luồng tham khảo:

~~~mermaid
sequenceDiagram
    participant O as OSB Handler
    participant S as State Store
    participant A as Provider Adapter
    participant P as Provider API
    participant W as Worker

    O->>S: Save instance, operation and resource spec
    O-->>O: Return accepted operation to platform
    W->>S: Claim pending operation
    W->>A: Provision(spec, idempotency key)
    A->>P: Create resource
    P-->>A: Provider operation ID
    A-->>W: Accepted by provider
    W->>S: Save provider operation ID
    W->>P: Poll/retrieve operation
    P-->>W: Resource ready
    W->>S: Save resource ID and ACTIVE state
    O->>S: Platform polls last_operation
    S-->>O: Operation succeeded
~~~

Worker phải có thể tiếp tục sau restart. Lưu provider operation ID, target, resource specification snapshot và trạng thái lần thử. Dùng backoff và jitter khi poll; tôn trọng rate limit của provider.

Nếu provider operation thất bại, chuyển lỗi thành loại nội bộ như invalid configuration, quota/capacity, permission, transient network hoặc unknown outcome. Operation OSB chỉ được đánh dấu thành công khi broker có bằng chứng backend đã đạt trạng thái sẵn sàng theo tiêu chí của plan.

## 16. Chuyển lỗi provider thành lỗi broker

Không chuyển nguyên văn lỗi provider cho platform vì có thể chứa account ID, endpoint nội bộ, request token hoặc chi tiết hạ tầng.

| Lỗi provider | Phân loại nội bộ | Hướng xử lý |
|---|---|---|
| Field/enum không hợp lệ | Mapping/configuration error | Không retry; sửa adapter/profile |
| SKU không có ở region | Capability/capacity error | Chọn target khác theo policy hoặc từ chối |
| Quota provider vượt | Quota error | Từ chối hoặc chờ capacity nếu được hỗ trợ |
| Credential provider hết hạn | Authentication/configuration error | Refresh credential theo quy trình; không retry vô hạn |
| Permission denied | Authorization/configuration error | Dừng, cảnh báo vận hành |
| Rate limit | Transient throttling | Backoff theo hướng dẫn provider |
| Timeout trước khi biết kết quả | Unknown outcome | Reconcile trước khi tạo lại |
| Provider 5xx | Transient provider failure | Retry giới hạn với backoff |
| Resource name đã tồn tại | Conflict | Tìm resource theo correlation tag và xác minh ownership |

OSB error response cần tuân thủ contract và status code phù hợp. Nếu request parameters không hợp lệ, trả lỗi validation trước khi gọi provider. Nếu backend lỗi sau khi operation đã được chấp nhận, cập nhật operation failed hoặc retry theo policy; không biến lỗi tạm thời thành lỗi đầu vào.

## 17. Mapping cho update và deprovision

Provider mapping không chỉ phục vụ provision. Cùng resource specification cần hỗ trợ các thao tác vòng đời khác.

### Update

Khi platform yêu cầu update, broker cần:

1. Tải instance và requested/effective specification hiện tại.
2. Resolve plan đích và validate parameters update.
3. Tạo target specification.
4. So sánh current và target để xác định thay đổi.
5. Kiểm tra provider có hỗ trợ thay đổi tại chỗ hay cần migration.
6. Gọi API update hoặc tạo workflow chuyển đổi.
7. Lưu operation và cập nhật effective specification sau khi provider xác nhận.

Không gửi toàn bộ provider create request vào endpoint update nếu API có semantics riêng. Một số field immutable sau khi tạo; một số cần restart hoặc migration.

### Deprovision

Khi deprovision, broker dùng backend resource mapping đã lưu. Không tính lại resource ID từ plan hoặc parameters hiện tại. Nếu một instance tạo nhiều resource phụ thuộc, adapter cần xóa đúng tập resource thuộc internal instance ID, giữ backup theo retention policy và đối soát kết quả.

Nếu profile mapping đã thay đổi, deprovision vẫn phải dùng provider, account, region và resource IDs đã lưu từ lúc provision. Đây là lý do phải giữ resource mapping snapshot đủ lâu.

## 18. Ví dụ Provider Adapter trong Spring

Một lớp adapter có thể tách việc tạo provider request:

~~~java
@Component
public class ManagedPostgresAdapter
        implements DatabaseProviderAdapter {

    private final ProviderDatabaseClient client;
    private final ProviderRequestMapper mapper;

    public ManagedPostgresAdapter(
            ProviderDatabaseClient client,
            ProviderRequestMapper mapper) {
        this.client = client;
        this.mapper = mapper;
    }

    @Override
    public ProviderProvisionResult provision(
            DatabaseResourceSpec spec,
            ProviderOperationContext context) {

        ProviderCreateDatabaseRequest request =
            mapper.toCreateRequest(spec, context);

        ProviderCreateDatabaseResponse response =
            client.createDatabase(
                request,
                context.idempotencyKey()
            );

        return new ProviderProvisionResult(
            response.resourceId(),
            response.operationId(),
            response.status()
        );
    }
}
~~~

Mapper chỉ chuyển đổi field; nó không tự quyết định quyền tenant hoặc plan entitlement:

~~~java
public ProviderCreateDatabaseRequest toCreateRequest(
        DatabaseResourceSpec spec,
        ProviderOperationContext context) {

    return ProviderCreateDatabaseRequest.builder()
        .engine(spec.engine())
        .engineVersion(spec.engineVersion())
        .instanceClass(context.selectedSku())
        .storageGiB(spec.storageGiB())
        .region(spec.region())
        .highAvailability(spec.highAvailability())
        .backupRetentionDays(spec.backupRetentionDays())
        .encryptionKeyRef(context.encryptionKeyRef())
        .tags(context.ownershipTags())
        .build();
}
~~~

Các class ProviderCreateDatabaseRequest, client và response là model minh họa do adapter hoặc SDK cung cấp; không phải API Spring Cloud Service Broker. Trong dự án thực tế, dùng SDK chính thức hoặc client có schema được version hóa.

Với Kubernetes, adapter có thể dùng client để tạo CRD qua API server. Mapper chuyển specification thành object của CRD đã cài trên cluster. Worker tiếp tục theo dõi status condition của operator cho đến khi cluster/database ready.

## 19. Kiểm thử ánh xạ plan và parameters

Cần kiểm thử cả kết quả mapping và hành vi khi mapping không thể đáp ứng cam kết plan.

| Trường hợp | Đầu vào | Kết quả mong đợi |
|---|---|---|
| Plan hợp lệ | Service/plan tồn tại | Resolve đúng profile version |
| Plan không thuộc service | Cặp ID không hợp lệ | Từ chối trước provider |
| Parameter hợp lệ | Storage trong giới hạn | Tạo specification đúng |
| Parameter sai kiểu | storage_gb là string | Validation error |
| Parameter vượt plan | Storage lớn hơn maximum | Từ chối, không gọi provider |
| Tenant vượt quota | Cấu hình đúng nhưng quota không đủ | Từ chối hoặc reservation thất bại |
| Target không hỗ trợ HA | Plan yêu cầu HA | Không hạ cấp âm thầm |
| SKU mapping thiếu | Không có SKU đạt compute | Capability/capacity error |
| Region không được phép | Request yêu cầu region ngoài allowlist | Từ chối trước provider |
| Mapping provider | Cùng spec qua hai adapter | Mỗi adapter tạo request đúng schema riêng |
| Profile thay đổi | Operation đã lưu version cũ | Worker dùng snapshot đã chấp nhận |
| Provider timeout | Resource có thể đã tạo | Reconcile trước retry |
| Provider rate limit | Trả throttling | Backoff có giới hạn |
| Secret handling | Request/response chứa token | Log đã redaction |
| Deprovision sau mapping đổi | Adapter profile mới khác profile cũ | Xóa bằng resource mapping đã lưu |

Nên có:

- Unit test cho parameter validator và plan resolver.
- Unit test cho resource specification factory.
- Contract test cho provider request mapper.
- Integration test với fake provider server hoặc sandbox.
- Test serialization của Kubernetes CRD.
- Test retry, timeout, duplicate event và reconciliation.
- Test xác nhận request không hợp lệ không tạo operation hoặc gọi provider.

Không chỉ kiểm tra rằng mapper tạo ra một object khác null. Hãy xác minh field cụ thể, enum, units, region, ownership tags, idempotency key và những capability bắt buộc của plan.

## 20. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Dùng plan ID làm provider SKU | Catalog phụ thuộc nhà cung cấp | Giữ plan theo ý nghĩa sản phẩm, mapping SKU riêng |
| Chuyển raw parameters trực tiếp tới provider | Field không được kiểm soát có thể thay đổi hạ tầng | Validate và tạo command có kiểu |
| Để handler OSB gọi SDK provider trực tiếp | Logic lifecycle phụ thuộc backend | Dùng provider adapter |
| Bỏ qua tenant quota | Tạo resource vượt quyền hoặc ngân sách | Kiểm tra/reserve quota trước khi gọi provider |
| Hạ cấp capability khi target thiếu tính năng | Vi phạm cam kết plan | Chọn target phù hợp hoặc từ chối |
| Không lưu profile/resource snapshot | Không thể update/deprovision đúng instance cũ | Lưu version và effective spec |
| Dùng default provider không rõ ràng | Cấu hình thực tế khác cam kết | Gửi rõ field bắt buộc và lưu giá trị provider xác nhận |
| Retry create với idempotency key mới | Tạo tài nguyên trùng | Dùng key ổn định và reconciliation |
| Đánh dấu ACTIVE ngay khi API trả accepted | Instance chưa sẵn sàng | Theo dõi provider operation/condition |
| Trả nguyên lỗi provider | Lộ chi tiết hạ tầng và credential | Phân loại, lọc và ánh xạ lỗi |
| Dùng profile mới để xóa instance cũ | Xóa sai account/region/resource | Dùng backend mapping đã lưu |
| Không kiểm tra API/CRD version | Request không tương thích backend | Version hóa adapter và contract test |

## 21. Nguyên tắc cần ghi nhớ

Ánh xạ plan và parameters sang API nhà cung cấp là quá trình chuyển hợp đồng sản phẩm của broker thành cấu hình hạ tầng cụ thể. Plan mô tả mức dịch vụ; parameters tùy chỉnh trong giới hạn; resource specification biểu diễn yêu cầu đã chuẩn hóa; provider adapter chuyển nó thành request theo API thực tế.

Khi triển khai bằng Spring Cloud Service Broker, hãy giữ các nguyên tắc:

- Dùng plan profile có version để mô tả năng lực và giới hạn sản phẩm.
- Validate parameters theo service, plan, operation, tenant policy và backend capability.
- Chuyển raw JSON thành command có kiểu trước khi tạo resource specification.
- Giữ resource specification độc lập với provider.
- Dùng adapter riêng cho managed service, Kubernetes operator hoặc private infrastructure.
- Version hóa provider mapping và lưu requested/effective specification.
- Chọn target có đủ capability; không tự hạ cấp bảo mật, HA hoặc backup.
- Dùng provider idempotency key/correlation tag và reconciliation khi timeout.
- Theo dõi long-running operation đến khi resource thật sự ready.
- Lưu provider account, region, resource ID và mapping version để update/deprovision đúng tài nguyên.
- Phân loại lỗi provider và không tiết lộ thông tin nội bộ trong response/log.

Với cách phân lớp này, broker có thể giữ catalog OSB ổn định trong khi thay đổi provider hoặc triển khai cùng plan trên nhiều loại hạ tầng. Platform chỉ cần chọn service, plan và parameters theo contract; broker chịu trách nhiệm biến lựa chọn đó thành request kỹ thuật an toàn, có thể theo dõi và quản lý xuyên suốt vòng đời tài nguyên.

