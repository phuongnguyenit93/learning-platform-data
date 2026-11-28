# Mô hình gói dịch vụ và ánh xạ gói sang tài nguyên hạ tầng

Trong Open Service Broker API (OSB API), **service plan** là một lựa chọn cung cấp thuộc về một service mà broker công bố trong catalog. Plan mô tả cấp cấu hình, tính năng hoặc giới hạn mà consumer có thể chọn. Khi nền tảng yêu cầu provision, broker dùng cặp `service_id` và `plan_id` để xác định chính xác lựa chọn dịch vụ, sau đó ánh xạ lựa chọn công khai này sang cấu hình và tài nguyên thực tế ở hạ tầng phía sau.

Trong module `SPRING_CLOUD_SERVICE_BROKER`, plan là ranh giới quan trọng giữa hợp đồng sản phẩm và cách triển khai kỹ thuật. Người dùng cần nhìn thấy những lựa chọn ổn định, dễ hiểu như `starter`, `standard` hoặc `production`; broker cần chuyển từng lựa chọn thành CPU, RAM, dung lượng, chính sách sao lưu, mức sẵn sàng và các giới hạn phù hợp với backend. Thiết kế tốt giữ được ý nghĩa của plan qua các lần triển khai, đồng thời cho phép thay đổi nhà cung cấp hoặc SKU hạ tầng mà không làm thay đổi hợp đồng với nền tảng.

## 1. Service plan trong catalog OSB API

Một service definition đại diện cho một loại dịch vụ mà broker cung cấp, ví dụ PostgreSQL hoặc Redis. Service definition chứa danh sách plan có thể lựa chọn. Mỗi plan có một ID ổn định và các metadata mô tả lựa chọn đó.

Ví dụ catalog rút gọn:

~~~json
{
  "services": [
    {
      "id": "svc-postgresql",
      "name": "postgresql",
      "description": "Dịch vụ cơ sở dữ liệu PostgreSQL được quản lý",
      "bindable": true,
      "plan_updateable": true,
      "plans": [
        {
          "id": "plan-postgresql-starter",
          "name": "starter",
          "description": "Dành cho môi trường phát triển",
          "free": true
        },
        {
          "id": "plan-postgresql-standard",
          "name": "standard",
          "description": "Dành cho ứng dụng thông thường",
          "free": false
        },
        {
          "id": "plan-postgresql-production",
          "name": "production",
          "description": "Dành cho hệ thống yêu cầu độ sẵn sàng cao",
          "free": false
        }
      ]
    }
  ]
}
~~~

Trong ví dụ:

- `service_id` xác định service definition PostgreSQL.
- `plan_id` xác định một lựa chọn cụ thể bên trong service đó.
- `name` và `description` giúp người dùng hiểu lựa chọn.
- `free` là metadata về việc plan có được công bố là miễn phí hay không; đây không phải cơ chế tính phí hoặc kiểm soát quota thay cho broker.
- `bindable` mô tả service có hỗ trợ binding hay không.
- `plan_updateable` công bố khả năng thay đổi plan của instance sau khi provision. Broker vẫn phải kiểm tra request và khả năng chuyển đổi thực tế.

Plan không phải một service độc lập. Một plan chỉ có ý nghĩa trong quan hệ với service chứa nó. Do đó, broker cần kiểm tra cả hai ID khi nhận request. Không chỉ tìm plan theo tên hiển thị hoặc giả định plan ID toàn cục nếu catalog và dữ liệu nội bộ cho phép các service có namespace riêng.

## 2. Plan mô tả lựa chọn sản phẩm, không phải tên máy chủ

Một plan có thể đại diện cho một hoặc nhiều thuộc tính của dịch vụ:

| Nhóm thuộc tính | Ví dụ | Tác động đến tài nguyên |
|---|---|---|
| Năng lực tính toán | vCPU, RAM, giới hạn CPU | Chọn node hoặc tier máy ảo phù hợp |
| Lưu trữ | Dung lượng, loại disk, IOPS | Chọn storage class hoặc volume profile |
| Khả năng sẵn sàng | Replica, multi-zone, failover | Tạo topology hoặc cấu hình HA |
| Sao lưu và phục hồi | Lịch backup, retention, PITR | Bật chính sách backup tương ứng |
| Hiệu năng | Số kết nối, throughput, IOPS | Áp dụng quota và giới hạn dịch vụ |
| Bảo mật | Encryption, network isolation, audit | Chọn policy hoặc profile bảo mật |
| Hỗ trợ vận hành | Monitoring, maintenance window | Cấu hình agent và lịch bảo trì |

Ví dụ, plan `production` có thể có 4 vCPU, 16 GB RAM, 500 GB storage, backup hằng ngày và HA. Nhưng không nên đặt tên plan là `db.m6i.xlarge` hoặc `disk-premium-500` nếu tên đó chỉ phản ánh SKU của một nhà cung cấp. Khi đổi cloud provider, SKU có thể không còn tồn tại dù cam kết sản phẩm `production` vẫn giữ nguyên.

Plan nên mô tả **mức dịch vụ mà broker cam kết**, còn lớp ánh xạ quyết định cách đáp ứng cam kết đó trên hạ tầng cụ thể. Một số thuộc tính có thể là giới hạn cứng, một số là mục tiêu hoặc tính năng được bật. Tài liệu plan cần diễn đạt rõ để người dùng không hiểu một giá trị minh họa thành cam kết SLA.

## 3. Phân biệt plan với parameters và quota

Ba khái niệm này có liên hệ nhưng phục vụ các mục đích khác nhau.

| Khái niệm | Vai trò | Ví dụ |
|---|---|---|
| Service plan | Lựa chọn cấp dịch vụ được công bố và quản lý bởi broker | PostgreSQL `standard` |
| Provision parameters | Tùy biến một instance trong giới hạn plan | Tên database, collation, cấu hình extension |
| Tenant quota/entitlement | Quyền hoặc hạn mức mà tenant được phép sử dụng | Tối đa 5 instance, tổng 2 TB storage |

Nếu plan `standard` cung cấp dung lượng mặc định 100 GB và cho phép tăng đến 250 GB, `storage_gb` có thể là parameter tùy chọn trong schema của service. Broker phải kiểm tra giá trị này không vượt giới hạn plan và quota tenant.

Không nên dùng parameters để thay thế plan. Nếu người dùng có thể gửi tùy ý `cpu=64`, `memory=256Gi` mà broker không đối chiếu với plan, thì catalog không còn là hợp đồng đáng tin cậy. Ngược lại, không nên tạo một plan mới cho mọi tên database hoặc mọi cấu hình nhỏ lẻ nếu chúng chỉ là tham số tùy biến.

Quy tắc thực thi có thể biểu diễn:

~~~text
effective_configuration =
    merge(
        service_defaults,
        selected_plan_profile,
        validated_provision_parameters,
        tenant_policy_overrides
    )
~~~

Thứ tự ưu tiên và field nào được phép ghi đè phải được định nghĩa rõ. Tenant policy không nên cho phép vượt qua các giới hạn bảo mật hoặc năng lực mà broker đã cam kết.

## 4. Mô hình dữ liệu plan và cấu hình nội bộ

Broker nên tách metadata công khai của plan khỏi cấu hình nội bộ dùng để tạo tài nguyên.

### Metadata công khai

Thông tin trong catalog có thể gồm:

- ID ổn định của plan.
- Tên và mô tả dành cho người dùng.
- Metadata hiển thị như nhóm, biểu tượng, tài liệu hoặc thông tin bổ sung.
- Trạng thái miễn phí nếu được công bố.
- Schema của parameters được hỗ trợ cho provision/update, tùy khả năng và phiên bản API.
- Các thuộc tính liên quan đến khả năng của service được công bố ở cấp service.

Metadata này là một phần của hợp đồng với platform. Không nên để lộ credential hạ tầng, tên node nội bộ, địa chỉ quản trị, account cloud hoặc chi tiết triển khai không dành cho consumer.

### Cấu hình nội bộ

Cấu hình nội bộ ánh xạ plan ID sang một profile kỹ thuật:

~~~yaml
service:
  id: svc-postgresql
  plans:
    plan-postgresql-starter:
      profile: postgres-dev
      limits:
        cpu: "1"
        memory: 2Gi
        storage: 20Gi
        connections: 30
      features:
        highAvailability: false
        backup: false

    plan-postgresql-standard:
      profile: postgres-general
      limits:
        cpu: "2"
        memory: 8Gi
        storage: 100Gi
        connections: 150
      features:
        highAvailability: false
        backup: true

    plan-postgresql-production:
      profile: postgres-ha
      limits:
        cpu: "4"
        memory: 16Gi
        storage: 500Gi
        connections: 500
      features:
        highAvailability: true
        backup: true
        pointInTimeRecovery: true
~~~

Đây là cấu hình minh họa. Trong ứng dụng thực tế, có thể lưu profile trong database, file cấu hình theo môi trường, configuration service hoặc module policy. Cần tránh nhân đôi các giá trị theo nhiều nơi mà không có quy tắc đồng bộ.

Tách metadata và profile mang lại ba lợi ích:

1. Catalog có thể giữ tên và ý nghĩa ổn định trong khi backend profile được điều chỉnh theo hạ tầng.
2. Broker có thể chọn profile khác nhau theo region, platform hoặc tenant mà vẫn kiểm tra cùng một plan ID.
3. Quyền đọc catalog không đồng nghĩa với quyền đọc cấu hình triển khai hoặc bí mật nội bộ.

## 5. Ánh xạ plan sang tài nguyên hạ tầng

Luồng ánh xạ cơ bản:

~~~mermaid
flowchart TD
    C["OSB provision request"] --> V["Validate service_id + plan_id"]
    V --> E["Check tenant entitlement and quota"]
    E --> P["Resolve plan profile"]
    P --> O["Apply region/platform overrides"]
    O --> A["Build effective resource specification"]
    A --> D["Backend adapter"]
    D --> R["Cloud / Kubernetes / Database infrastructure"]
    R --> S["Persist resource ID and plan snapshot"]
~~~

Các bước có trách nhiệm riêng:

1. **Validate lựa chọn:** xác nhận service tồn tại, plan thuộc service và plan được phép sử dụng.
2. **Kiểm tra entitlement:** xác định tenant hoặc platform có quyền provision plan này.
3. **Resolve profile:** tra cấu hình kỹ thuật gắn với plan ID.
4. **Áp dụng biến thể môi trường:** chọn region, zone, storage class hoặc SKU tương ứng.
5. **Validate parameters:** áp dụng giá trị người dùng yêu cầu trong giới hạn profile và quota.
6. **Tạo resource specification:** tạo mô hình trung gian không phụ thuộc nhà cung cấp.
7. **Gọi backend adapter:** chuyển specification thành API hoặc manifest cụ thể.
8. **Lưu kết quả:** lưu backend resource ID, plan ID, cấu hình đã áp dụng và trạng thái operation.

### Ví dụ: PostgreSQL trên các backend khác nhau

Cùng plan `plan-postgresql-production` có thể được triển khai theo các cách khác nhau:

| Môi trường | Ánh xạ kỹ thuật minh họa |
|---|---|
| Cloud provider A | Managed PostgreSQL tier có HA, disk 500 GB |
| Cloud provider B | Database cluster với primary/standby, storage encrypted |
| Kubernetes | Operator tạo StatefulSet/cluster, PVC 500 GiB, replica và backup policy |
| Private cloud | VM profile, volume profile và hệ thống backup nội bộ |

Các cấu hình này không nhất thiết giống nhau ở mức SKU, nhưng cần đáp ứng cùng tiêu chí sản phẩm mà plan đã công bố. Nếu một backend không thể đáp ứng yêu cầu HA hoặc backup của plan production, broker không nên âm thầm hạ cấp tính năng. Nó cần chọn backend khác, từ chối provision hoặc công bố catalog/capability phù hợp với môi trường đó.

### Một plan có thể ánh xạ tới nhiều profile

Trong môi trường nhiều region hoặc nhiều platform, ánh xạ có thể có thêm điều kiện:

~~~yaml
mappings:
  plan-postgresql-production:
    defaultProfile: postgres-ha-standard
    targets:
      aws-ap-southeast-1: postgres-rds-ha
      azure-southeastasia: postgres-flex-ha
      kubernetes-cluster-a: postgres-operator-ha
~~~

Không nên nhúng các tên target nội bộ vào ID plan công khai. Broker có thể dùng `platform_id`, region, backend capability và tenant policy để chọn mapping. Quy tắc chọn cần xác định được và có thể audit, để cùng một request không lúc chọn backend A, lúc chọn backend B ngoài dự kiến.

## 6. Resource specification làm ranh giới giữa plan và backend

Nếu logic plan gọi trực tiếp API của từng nhà cung cấp, ứng dụng sẽ nhanh chóng có nhiều nhánh điều kiện và khó kiểm thử. Một cách tổ chức tốt là tạo một mô hình resource specification trung gian.

Ví dụ Java:

~~~java
public record DatabaseResourceSpec(
    String engine,
    String version,
    int cpu,
    int memoryGiB,
    int storageGiB,
    int maxConnections,
    boolean highAvailability,
    BackupPolicy backupPolicy,
    String region,
    String networkProfile
) {}
~~~

Một service cấu hình chịu trách nhiệm biến service/plan/parameters đã xác thực thành specification:

~~~java
DatabaseResourceSpec resolveDatabaseSpec(
        PlanProfile profile,
        ProvisionParameters parameters,
        TenantPolicy policy,
        DeploymentTarget target) {

    int storage = parameters.storageGiB() != null
        ? parameters.storageGiB()
        : profile.defaultStorageGiB();

    if (storage < profile.minimumStorageGiB()
            || storage > profile.maximumStorageGiB()) {
        throw new InvalidProvisionParametersException(
            "storage_gb is outside the selected plan limits");
    }

    policy.assertStorageAllowed(storage);

    return new DatabaseResourceSpec(
        profile.engine(),
        profile.engineVersion(),
        profile.cpu(),
        profile.memoryGiB(),
        storage,
        profile.maxConnections(),
        profile.highAvailability(),
        profile.backupPolicy(),
        target.region(),
        target.networkProfile()
    );
}
~~~

Đây là ví dụ mô hình hóa, không phải API có sẵn của Spring Cloud Service Broker. Tên lớp và field cần được điều chỉnh theo domain của broker.

Backend adapter nhận specification và chuyển đổi thành lệnh cụ thể:

~~~java
public interface DatabaseProvisioner {
    ProvisionedDatabase provision(
        DatabaseResourceSpec specification,
        String idempotencyKey
    );

    void update(
        String backendResourceId,
        DatabaseResourceSpec targetSpecification
    );

    void deprovision(String backendResourceId);
}
~~~

Với cách này, lớp plan resolution không cần biết nhà cung cấp sử dụng REST API nào, Kubernetes CRD nào hoặc lệnh quản trị database nào. Adapter chịu trách nhiệm ánh xạ specification sang backend và chuyển lỗi về loại lỗi nghiệp vụ mà orchestrator hiểu được.

## 7. Xử lý plan khi provision

Khi nhận yêu cầu provision, broker không chỉ lưu `plan_id`. Nó cần xác định và lưu đủ dữ liệu để có thể quản lý tài nguyên về sau.

Một trình tự tham khảo:

1. Xác thực platform và tenant.
2. Tra cứu service definition.
3. Kiểm tra plan ID thuộc service đã chọn.
4. Kiểm tra tenant có entitlement và quota.
5. Resolve plan profile theo target và phiên bản cấu hình.
6. Validate parameters theo schema và giới hạn.
7. Tạo resource specification.
8. Tạo operation và ghi nhận idempotency key.
9. Gọi backend hoặc enqueue công việc bất đồng bộ.
10. Lưu backend resource ID, plan snapshot và kết quả.

Ví dụ request:

~~~json
{
  "service_id": "svc-postgresql",
  "plan_id": "plan-postgresql-standard",
  "parameters": {
    "database_name": "orders",
    "storage_gb": 150,
    "backup_retention_days": 14
  }
}
~~~

Giả sử plan standard cho phép storage từ 50 đến 250 GB và retention tối đa 30 ngày. Request có thể hợp lệ nếu tenant quota còn đủ. Nếu người dùng yêu cầu 1.000 GB hoặc retention 365 ngày, broker phải từ chối bằng lỗi validation phù hợp, dù backend có khả năng tạo tài nguyên lớn hơn.

### Lưu plan snapshot

Khi provision hoàn tất, instance nên giữ:

- Service ID và plan ID được chọn.
- Phiên bản metadata hoặc profile được dùng.
- Resource specification thực tế đã tạo.
- Backend provider, region và resource ID.
- Parameters đã chuẩn hóa, loại bỏ giá trị nhạy cảm nếu có.
- Tenant ownership và trạng thái operation.

Snapshot giúp broker biết instance cũ đã được tạo theo cấu hình nào ngay cả khi plan profile hiện tại thay đổi. Không nên chỉ tra lại cấu hình mới nhất mỗi lần update hoặc deprovision vì điều đó có thể khiến broker diễn giải sai tài nguyên đang chạy.

## 8. Thay đổi plan và tương thích cấu hình

Một service có thể công bố khả năng cập nhật plan thông qua metadata của service. Tuy nhiên, việc công bố khả năng đó không đảm bảo mọi cặp plan đều chuyển đổi được.

Ví dụ:

| Plan hiện tại | Plan đích | Có thể cần xử lý |
|---|---|---|
| starter | standard | Tăng CPU/RAM, mở rộng storage, bật backup |
| standard | production | Chuyển topology sang HA, tạo replica, cấu hình PITR |
| production | standard | Giảm tài nguyên, kiểm tra storage/connection và yêu cầu HA |
| production | starter | Có thể không hỗ trợ do mất tính năng hoặc giảm dung lượng |

Broker nên duy trì ma trận chuyển đổi hoặc một policy engine để quyết định:

- Cặp plan nào được phép chuyển.
- Chuyển đổi có thể thực hiện tại chỗ hay cần migration.
- Có downtime hay không.
- Có cần backup trước khi chuyển đổi không.
- Thứ tự thay đổi backend và cập nhật state.
- Cách rollback hoặc bù trừ khi một bước thất bại.

Không được chỉ thay `plan_id` trong database trước khi backend thực sự đáp ứng cấu hình đích. Trong thao tác bất đồng bộ, instance có thể mang trạng thái `UPDATING` và operation cần phản ánh tiến độ cho platform. Chỉ sau khi backend xác nhận, broker mới cập nhật active plan và snapshot mới.

### Versioning plan

Plan ID nên ổn định và không tái sử dụng cho ý nghĩa khác. Nếu thay đổi làm thay đổi đáng kể cấu hình, giới hạn hoặc cam kết sản phẩm, hãy cân nhắc tạo plan ID/version mới.

Ví dụ:

- `plan-postgresql-standard-v1`: 2 vCPU, 8 GB RAM, storage 100 GB.
- `plan-postgresql-standard-v2`: thay đổi chính sách backup hoặc giới hạn kết nối.

Có thể giữ tên hiển thị `standard` trong catalog nếu cách quản lý version nội bộ cho phép, nhưng broker phải có quy tắc migration rõ ràng cho instance cũ. Việc xóa plan khỏi catalog không có nghĩa là xóa cấu hình lịch sử cần thiết để quản lý tài nguyên đang tồn tại.

## 9. Plan, entitlement và quota theo tenant

Không phải mọi tenant đều được phép dùng mọi plan. Broker có thể áp dụng entitlement ở cấp tenant, organization, platform hoặc hợp đồng thương mại.

Ví dụ:

| Tenant | Plan được phép | Quota |
|---|---|---|
| Development | starter, standard | Tối đa 10 instance, 1 TB storage |
| Business | standard, production | Tối đa 30 instance, 10 TB storage |
| Enterprise | Tất cả plan | Hạn mức riêng theo hợp đồng |

Catalog có thể công bố danh sách plan chung hoặc lọc theo platform/tenant nếu mô hình tích hợp cho phép. Dù chọn cách nào, broker phải kiểm tra entitlement tại thời điểm provision và update. Không dựa vào việc plan có xuất hiện trong catalog để kết luận caller được quyền sử dụng.

Quota có thể gồm số instance, tổng CPU, RAM, storage, số binding, số kết nối hoặc chi phí dự kiến. Cần tính cả tài nguyên đang tạo và đang update để tránh hai request đồng thời cùng nhìn thấy quota còn trống rồi vượt hạn mức. Có thể giữ reservation trong transaction cùng operation, sau đó xác nhận hoặc giải phóng khi thao tác hoàn tất/thất bại.

## 10. Ánh xạ plan sang Kubernetes và managed services

### Kubernetes

Một plan có thể được ánh xạ sang resource profile cho operator:

~~~yaml
apiVersion: database.example.io/v1
kind: PostgreSQLCluster
metadata:
  name: orders-db
spec:
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
~~~

Broker không nhất thiết tự tạo trực tiếp StatefulSet hoặc PVC. Nếu backend dùng operator, adapter có thể tạo custom resource và chờ trạng thái sẵn sàng. Plan `production` sẽ được ánh xạ sang replica count, resource requests, storage class và backup policy. Các field minh họa cần điều chỉnh theo CRD thực tế.

### Managed database

Với managed database, adapter có thể chuyển specification thành các tham số API như compute tier, storage, availability zone, backup retention và encryption. SKU cụ thể nên được chọn trong mapping theo region/provider. Broker lưu provider resource ID để có thể retrieve, update và deprovision về sau.

### Backend không đáp ứng plan

Nếu một target không hỗ trợ tính năng bắt buộc, broker có một số lựa chọn:

- Không công bố plan đó trong catalog của target.
- Từ chối provision với lỗi có thể hiểu được.
- Chọn backend khác đã được phê duyệt và đáp ứng cùng cam kết.
- Chỉ dùng fallback nếu policy sản phẩm cho phép và người dùng được thông báo rõ.

Không âm thầm ánh xạ plan production sang một cấu hình nhỏ hơn chỉ để request thành công.

## 11. Plan và xử lý bất đồng bộ, idempotency

Provision hoặc update tài nguyên có thể mất vài phút. Broker cần ghi nhận plan và profile đã chọn trước khi đưa công việc vào hàng đợi.

Một operation record có thể chứa:

~~~json
{
  "operation_id": "op-7831",
  "instance_id": "orders-db-prod",
  "service_id": "svc-postgresql",
  "plan_id": "plan-postgresql-production",
  "plan_profile_version": "2026-03",
  "target": "kubernetes-cluster-a",
  "status": "PENDING"
}
~~~

Worker xử lý operation cần dùng cùng plan snapshot và resource specification đã được xác định. Nếu chỉ lưu plan ID rồi đọc cấu hình mới nhất khi job chạy, một thay đổi cấu hình trong lúc chờ có thể khiến request được thực hiện với profile khác profile đã được xác nhận.

Idempotency key nên kết hợp tenant/platform scope, operation type, instance ID và fingerprint của lựa chọn service/plan/parameters. Khi request lặp đến, broker trả operation hoặc kết quả đã lưu. Nếu cùng ID nhưng plan hoặc parameters khác, broker phải phát hiện xung đột và áp dụng quy tắc API, không tạo tài nguyên thứ hai.

Khi backend tạo tài nguyên thành công nhưng broker mất kết nối trước khi lưu kết quả, adapter cần hỗ trợ đối soát bằng idempotency key, external resource tag hoặc một định danh ổn định khác. Điều này giúp retry không tạo thêm database hoặc cluster.

## 12. Bảo mật cấu hình plan

Plan profile thường chứa thông tin nhạy cảm về hạ tầng hoặc chính sách. Broker cần tách quyền đọc catalog khỏi quyền quản trị cấu hình nội bộ.

- Không đưa credential, token, endpoint quản trị hoặc account ID bí mật vào catalog.
- Không cho parameters ghi đè các field bảo mật như network isolation, encryption hoặc tenant ownership.
- Kiểm tra entitlement và quota ở phía server, ngay cả khi catalog đã lọc plan.
- Chỉ cấp backend credential có quyền tối thiểu cần thiết.
- Lưu secret trong secret manager; resource specification và snapshot không lưu password/token.
- Audit thay đổi plan profile, mapping provider, quota và entitlement.
- Có thể rollback profile configuration, nhưng cần đánh giá tác động lên instance đã provision.
- Giới hạn quyền thay đổi cấu hình plan trong môi trường production.

Nếu profile có các thuộc tính như network, encryption key hoặc backup destination, hãy kiểm tra chúng thuộc đúng tenant và không cho phép client truyền ID tài nguyên của tenant khác để thay thế.

## 13. Tổ chức triển khai trong Spring Cloud Service Broker

Một ứng dụng Spring có thể tách trách nhiệm thành các thành phần:

~~~text
broker/
  catalog/
    CatalogConfiguration
    ServiceDefinitionProvider
  plans/
    PlanProfile
    PlanResolver
    PlanEntitlementService
    PlanCompatibilityService
  lifecycle/
    ServiceInstanceOrchestrator
    ProvisionOperationHandler
    UpdateOperationHandler
  resource/
    DatabaseResourceSpec
    ResourceSpecFactory
  backend/
    DatabaseProvisioner
    KubernetesDatabaseAdapter
    ManagedDatabaseAdapter
  persistence/
    ServiceInstanceEntity
    PlanSnapshotEntity
    OperationEntity
~~~

Vai trò chính:

- Catalog provider xây dựng service definition và danh sách plan để platform truy vấn.
- Plan resolver tìm profile tương ứng với service/plan và deployment target.
- Entitlement service kiểm tra tenant được phép sử dụng plan.
- Resource spec factory kết hợp plan profile với parameters hợp lệ.
- Orchestrator quản lý trạng thái và idempotency.
- Backend adapter tạo hoặc thay đổi tài nguyên cụ thể.
- Persistence lưu lựa chọn plan, snapshot và backend resource reference.

Spring Cloud Service Broker cung cấp abstractions để tích hợp catalog và các handler vòng đời OSB API. Tên lớp, cách cấu hình catalog và interface cụ thể phụ thuộc phiên bản thư viện. Vì vậy, nên đặt domain logic về plan trong service riêng và dùng adapter để nối với request model của phiên bản đang sử dụng, thay vì để logic mapping phụ thuộc trực tiếp vào chi tiết framework.

Một luồng provision ở mức khái niệm:

~~~mermaid
sequenceDiagram
    participant Platform
    participant Broker as Spring Cloud Broker
    participant Plan as Plan Resolver
    participant Store as State Store
    participant Adapter as Backend Adapter
    participant Infra as Infrastructure

    Platform->>Broker: PUT service_instances
    Broker->>Plan: Resolve service_id + plan_id
    Plan-->>Broker: Plan profile + version
    Broker->>Plan: Check entitlement, quota, parameters
    Plan-->>Broker: Effective resource specification
    Broker->>Store: Save operation + plan snapshot
    Broker-->>Platform: Accepted / operation token
    Broker->>Adapter: Provision specification
    Adapter->>Infra: Create resource
    Infra-->>Adapter: Backend resource ID
    Adapter-->>Broker: Provision result
    Broker->>Store: Save resource ID + active plan
    Platform->>Broker: GET last_operation
    Broker-->>Platform: Operation succeeded
~~~

## 14. Kiểm thử mô hình plan và mapping

Kiểm thử nên tập trung vào tính đúng đắn của hợp đồng plan và kết quả tài nguyên được tạo.

| Trường hợp | Dữ liệu kiểm thử | Kết quả mong đợi |
|---|---|---|
| Plan hợp lệ | Service và plan tồn tại, plan thuộc service | Resolve được profile |
| Plan không thuộc service | Gửi plan ID của service khác | Từ chối request |
| Plan không tồn tại | ID không có trong catalog | Lỗi lựa chọn hợp lệ |
| Tenant không có entitlement | Tenant chọn plan production bị giới hạn | Từ chối trước khi gọi backend |
| Parameter trong giới hạn | Storage 150 GB với plan cho phép 50–250 GB | Tạo specification hợp lệ |
| Parameter vượt giới hạn | Storage 1 TB khi plan tối đa 250 GB | Từ chối, không gọi backend |
| Mapping theo region | Cùng plan ở hai region | Chọn profile tương ứng, vẫn giữ ý nghĩa plan |
| Backend thiếu capability | Target không hỗ trợ HA bắt buộc | Không hạ cấp âm thầm |
| Profile thay đổi khi job đang chờ | Operation đã ghi profile version cũ | Worker dùng snapshot đã lưu |
| Retry provision | Cùng ID và fingerprint | Không tạo tài nguyên trùng |
| Plan update hợp lệ | Cặp plan có migration được hỗ trợ | Update theo workflow đã định nghĩa |
| Plan update không hỗ trợ | Cặp plan không có đường chuyển đổi | Từ chối trước khi thay đổi state/backend |
| Backend lỗi giữa chừng | Resource tạo một phần rồi timeout | Retry/compensation an toàn và có thể đối soát |

Nên kiểm thử cả unit test cho PlanResolver/ResourceSpecFactory và integration test với backend adapter giả lập. Với mỗi plan công bố, cần có dữ liệu kiểm thử xác nhận profile được resolve, parameter được giới hạn và specification tạo ra đáp ứng những tính năng đã mô tả.

## 15. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Dùng SKU nhà cung cấp làm plan ID công khai | Khó chuyển provider hoặc region | Dùng plan ID theo ý nghĩa sản phẩm, mapping SKU ở nội bộ |
| Gộp plan với parameters | Catalog không còn mô tả được giới hạn lựa chọn | Tách cấp dịch vụ khỏi tùy biến instance |
| Chỉ lưu plan ID hiện tại | Không tái dựng được cấu hình instance cũ sau khi profile đổi | Lưu profile version và snapshot |
| Chỉ kiểm tra quyền trong catalog | Request trực tiếp có thể vượt entitlement | Kiểm tra quyền ở provision và update |
| Ánh xạ plan production sang cấu hình thấp hơn | Vi phạm cam kết về tính năng và hiệu năng | Kiểm tra capability, từ chối hoặc chọn target phù hợp |
| Đổi plan bằng cách sửa metadata | State và backend không đồng nhất | Dùng workflow update và operation |
| Cho parameters vượt giới hạn plan | Tenant có thể tiêu thụ quá quota | Validate server-side và reservation quota |
| Dùng cấu hình mới cho job cũ | Kết quả không khớp lựa chọn ban đầu | Ghi snapshot khi tạo operation |
| Xóa plan đang được instance sử dụng | Mất khả năng quản lý tài nguyên cũ | Ngừng công bố nhưng giữ metadata lịch sử cần thiết |

## 16. Nguyên tắc cần ghi nhớ

Service plan là lựa chọn sản phẩm mà broker công bố cho platform. Nó cần có ID ổn định, mô tả rõ ràng và giới hạn có thể kiểm chứng. Khi provision, broker ánh xạ cặp service/plan sang profile kỹ thuật, kết hợp parameters đã xác thực, entitlement, quota và target để tạo resource specification cho backend.

Hãy giữ rõ các ranh giới sau:

- Catalog công bố ý nghĩa và khả năng của plan.
- Plan profile mô tả cấu hình kỹ thuật nội bộ.
- Parameters tùy biến instance trong giới hạn plan.
- Entitlement và quota quyết định tenant có được dùng plan hay không.
- Resource specification làm hợp đồng giữa lớp nghiệp vụ và backend adapter.
- Plan snapshot giúp quản lý tài nguyên cũ khi cấu hình hoặc provider thay đổi.
- Workflow update quản lý chuyển đổi plan và trạng thái bất đồng bộ.

Với cách phân tách này, Spring Cloud Service Broker có thể giữ hợp đồng OSB API ổn định trong khi ánh xạ các plan sang managed database, Kubernetes operator hoặc hạ tầng riêng. Người dùng chọn một mức dịch vụ dễ hiểu; broker chịu trách nhiệm biến lựa chọn đó thành tài nguyên đúng giới hạn, có thể theo dõi, cập nhật và thu hồi an toàn.

