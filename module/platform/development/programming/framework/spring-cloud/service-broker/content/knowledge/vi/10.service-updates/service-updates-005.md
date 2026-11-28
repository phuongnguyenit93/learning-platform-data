# Kiểm tra đường chuyển gói, hạn mức và khả năng của nhà cung cấp

Khi nền tảng yêu cầu thay đổi plan của một service instance, broker cần xác định thay đổi đó có hợp lệ với instance hiện tại, có nằm trong các đường chuyển đổi được cho phép, có đáp ứng giới hạn tài nguyên và có được nhà cung cấp hỗ trợ trong môi trường đang chạy hay không. Việc plan đích xuất hiện trong catalog hoặc nhà cung cấp có một API update chưa đủ để kết luận rằng mọi instance đều có thể chuyển sang plan đó.

Trong module **SPRING_CLOUD_SERVICE_BROKER**, kiểm tra trước khi update giúp broker tránh nhận một yêu cầu chắc chắn thất bại, tránh vượt quota và tránh làm tài nguyên rơi vào trạng thái không nhất quán. Bài học này tập trung vào ba nhóm kiểm tra: **đường chuyển plan**, **hạn mức và capacity**, **khả năng thực tế của provider**; sau đó kết hợp chúng thành một quy trình kiểm tra trước khi thực hiện update theo Open Service Broker API (OSB API).

## 1. Vì sao cần kiểm tra trước khi chuyển plan?

Một plan thường đại diện cho tập hợp giới hạn và chính sách của dịch vụ: CPU, bộ nhớ, dung lượng lưu trữ, số kết nối, số replica, mức backup, tính sẵn sàng, vùng triển khai hoặc mức hỗ trợ vận hành. Thay đổi plan có thể làm thay đổi nhiều thuộc tính cùng lúc.

Ví dụ, một database đang ở plan small có dung lượng tối đa 50 GB. Người dùng muốn chuyển sang plan standard có dung lượng 200 GB. Đây có thể là một thao tác mở rộng hợp lệ nếu provider hỗ trợ tăng dung lượng trực tiếp và quota còn đủ.

Nhưng chiều ngược lại không nhất thiết hợp lệ. Nếu database đang dùng 80 GB thì chuyển về plan small có thể làm vượt giới hạn của plan đích. Ngay cả khi dung lượng hiện tại thấp hơn 50 GB, provider có thể không hỗ trợ giảm kích thước volume tại chỗ hoặc việc giảm có thể yêu cầu tạo tài nguyên mới và di chuyển dữ liệu.

Một yêu cầu update cần được đánh giá theo ít nhất bốn câu hỏi:

1. Service có cho phép update và plan đích có thuộc service đó không?
2. Instance hiện tại có được phép chuyển sang plan đích theo chính sách broker không?
3. Trạng thái và mức sử dụng hiện tại có nằm trong giới hạn của plan đích không?
4. Provider có hỗ trợ chính xác thao tác đó với loại tài nguyên, region, tài khoản và phiên bản hiện tại không?

Broker chỉ bắt đầu thay đổi tài nguyên sau khi các điều kiện cần thiết đã được xác nhận hoặc đã có quy trình xử lý bất đồng bộ phù hợp.

## 2. Đọc yêu cầu update theo hợp đồng OSB API

OSB API v2 định nghĩa thao tác update service instance bằng request PATCH tới endpoint có dạng:

~~~http
PATCH /v2/service_instances/{instance_id}?accepts_incomplete=true
Content-Type: application/json
~~~

Một request minh họa:

~~~json
{
  "service_id": "postgres-service",
  "plan_id": "postgres-standard-v2",
  "parameters": {
    "storage_gb": 120,
    "backup_retention_days": 14
  },
  "context": {
    "platform": "cloud-foundry"
  }
}
~~~

Tùy phiên bản đặc tả và thư viện, request có thể chứa thông tin previous_values để mô tả một số giá trị trước update. Hãy dùng request object mà Spring Cloud Open Service Broker cung cấp trong đúng phiên bản dự án và không tự giả định mọi trường đều hiện diện.

Các dữ liệu cần lấy để kiểm tra gồm:

| Dữ liệu | Ý nghĩa khi kiểm tra |
|---|---|
| instance_id | Tìm instance hiện tại và khóa đồng bộ update |
| service_id | Xác nhận service đích vẫn đúng với service của instance |
| plan_id | Xác định plan đích |
| parameters | Các thay đổi cấu hình được yêu cầu |
| context | Ngữ cảnh nền tảng hoặc tenant theo hợp đồng |
| previous_values (nếu có) | Thông tin trước update để đối chiếu hoặc phát hiện request cũ |

Thông tin authoritative về plan hiện tại phải lấy từ trạng thái broker đã lưu và/hoặc provider, không được chỉ tin previous_values do client gửi. Dữ liệu trong request là đầu vào cần kiểm tra; nó không thay thế trạng thái thực tế của instance.

### Catalog capability chỉ là điều kiện tổng quát

Trong catalog, trường plan_updateable cho biết service hỗ trợ khả năng update plan theo OSB API. Nếu trường này là false, broker không được xử lý yêu cầu chuyển plan như một khả năng đã công bố.

Nếu plan_updateable là true, điều đó vẫn không có nghĩa mọi cặp plan đều chuyển đổi được. Đây là capability tổng quát ở mức service; broker vẫn phải kiểm tra từng đường chuyển đổi và điều kiện của instance. Ví dụ, service có thể hỗ trợ nâng cấp từ small lên standard nhưng không hỗ trợ hạ cấp từ standard về small.

## 3. Mô hình hóa đường chuyển plan như đồ thị có hướng

Không nên giả định các plan có thể chuyển đổi tự do theo thứ tự kích thước. Mỗi chuyển đổi là một hành động riêng có thể có điều kiện và chi phí khác nhau.

Có thể mô hình hóa plan là các đỉnh trong đồ thị, còn đường chuyển được hỗ trợ là các cạnh có hướng:

~~~mermaid
flowchart LR
    Small["small"] --> Standard["standard"]
    Standard --> HA["high-availability"]
    Small --> HA
    Standard -. "không hỗ trợ hạ cấp trực tiếp" .-> Small
    HA -. "cần migration riêng" .-> Standard
~~~

Sơ đồ minh họa một chính sách trong đó có thể nâng cấp từ small lên standard hoặc high-availability, nhưng không hỗ trợ hạ cấp trực tiếp. Một hệ thống khác có thể có đồ thị khác dựa trên khả năng provider.

Mỗi cạnh nên mang metadata về điều kiện:

| Trường | Ví dụ | Mục đích |
|---|---|---|
| sourcePlanId | postgres-small-v1 | Plan hiện tại |
| targetPlanId | postgres-standard-v2 | Plan đích |
| direction | upgrade | Loại chuyển đổi |
| strategy | in-place | Cách provider thực hiện |
| minCurrentStorageGb | 0 | Điều kiện sử dụng hiện tại |
| maxCurrentStorageGb | 50 | Giới hạn dữ liệu hiện tại |
| requiresMaintenance | true | Có cần cửa sổ bảo trì không |
| supportsAsync | true | Có thể chạy bất đồng bộ không |
| estimatedDowntime | 5m | Ước lượng phục vụ điều phối |
| enabled | true | Có cho phép chuyển đổi không |

Metadata này là mô hình nội bộ của broker, không phải trường chuẩn bắt buộc trong catalog OSB API.

Một định nghĩa chuyển đổi nội bộ có thể biểu diễn bằng Java:

~~~java
public record PlanTransition(
    String sourcePlanId,
    String targetPlanId,
    UpdateStrategy strategy,
    Long maximumCurrentStorageGb,
    boolean maintenanceRequired,
    boolean asynchronous
) {}

public enum UpdateStrategy {
    IN_PLACE,
    EXPAND_ONLY,
    RECREATE_AND_MIGRATE,
    PROVIDER_MANAGED
}
~~~

Khi nhận yêu cầu, broker tra cứu đúng cạnh source-to-target. Không tìm thấy cạnh nghĩa là broker chưa cho phép chuyển đổi đó. Không nên suy ra chiều ngược lại từ một cạnh đã tồn tại: nếu small chuyển được lên standard, điều đó không chứng minh standard chuyển được xuống small.

### Phân biệt loại chuyển đổi

- **In-place**: provider thay đổi tài nguyên hiện tại mà không thay thế identity của nó.
- **Expand-only**: chỉ cho phép tăng dung lượng hoặc giới hạn; không cho phép thu nhỏ.
- **Recreate and migrate**: tạo tài nguyên mới, di chuyển dữ liệu hoặc cấu hình rồi chuyển hướng kết nối.
- **Provider-managed**: provider có quy trình nâng cấp riêng, có thể cần kiểm tra operation hoặc maintenance window.

Mỗi chiến lược có yêu cầu khác nhau về backup, downtime, endpoint, credentials, rollback và thời điểm chuyển trạng thái broker.

## 4. Kiểm tra giới hạn của plan đích

Plan đích có thể giới hạn tài nguyên theo nhiều chiều. Không chỉ kiểm tra một con số CPU hoặc storage; cần xác định tất cả giới hạn ảnh hưởng đến instance.

Ví dụ plan database:

| Thuộc tính | Plan standard | Giá trị instance hiện tại |
|---|---:|---:|
| vCPU | 4 | 2 |
| Memory | 16 GB | 8 GB |
| Storage | Tối đa 150 GB | 120 GB |
| Connections | Tối đa 300 | 180 |
| Backup retention | Tối đa 30 ngày | 14 ngày |
| Replicas | Tối đa 2 | 1 |

Khi chuyển sang plan này, các giá trị hiện tại đều nằm trong giới hạn minh họa. Tuy nhiên, broker vẫn phải xác nhận provider có thể áp dụng các giới hạn mới và các tham số được yêu cầu không vi phạm policy.

Một số điều kiện thường gặp:

- Dung lượng đang sử dụng không vượt giới hạn storage của plan đích.
- Số kết nối hiện tại không vượt giới hạn mới.
- Số replica đang cấu hình phù hợp với plan đích.
- Phiên bản engine hoặc extension đang dùng tương thích.
- Chính sách backup, retention và encryption có thể được duy trì.
- Các tham số update không chứa trường không được hỗ trợ hoặc giá trị ngoài schema.
- Resource không ở trạng thái đang restore, failover, migration hoặc một operation khác không tương thích.

Cần phân biệt **giới hạn cấu hình** và **mức sử dụng thực tế**. Một volume được cấp 100 GB nhưng chỉ đang dùng 30 GB có thể vẫn không thu nhỏ được nếu provider chỉ hỗ trợ mở rộng. Ngược lại, mức sử dụng hiện tại thấp hơn giới hạn không tự chứng minh thao tác resize an toàn.

### Không dùng schema thay cho kiểm tra runtime

Schema trong catalog mô tả cấu trúc và một số giới hạn của parameters. Nó có thể giúp nền tảng kiểm tra trước khi gửi request, nhưng broker vẫn phải xác thực ở thời điểm update.

Ví dụ schema cho tham số storage:

~~~json
{
  "type": "object",
  "properties": {
    "storage_gb": {
      "type": "integer",
      "minimum": 10,
      "maximum": 150
    },
    "backup_retention_days": {
      "type": "integer",
      "minimum": 1,
      "maximum": 30
    }
  }
}
~~~

Schema không thể tự xác nhận dung lượng thực tế đang dùng trên provider, quota còn lại của tenant hoặc một operation khác có đang thay đổi cùng tài nguyên hay không. Những điều kiện đó cần kiểm tra từ trạng thái broker và provider.

## 5. Phân biệt quota, limit và capacity

Ba khái niệm thường bị gộp thành “còn tài nguyên hay không”, nhưng chúng có ý nghĩa khác nhau.

**Limit** là giới hạn được áp dụng cho một instance, plan hoặc tenant. Ví dụ plan chỉ cho phép tối đa 150 GB storage hoặc một tổ chức chỉ được tạo 10 database.

**Quota** là ngân sách hoặc mức sử dụng tối đa được cấp cho một phạm vi quản lý. Quota có thể được áp dụng ở tài khoản provider, subscription, project, region, tenant hoặc tổ chức.

**Capacity** là tài nguyên thực tế còn khả dụng tại provider hoặc vùng triển khai ở thời điểm yêu cầu. Một quota còn dư không bảo đảm vùng đó có đủ capacity để tạo hoặc mở rộng tài nguyên ngay.

Ví dụ:

- Tenant có quota storage 1.000 GB.
- Tenant đã sử dụng 900 GB.
- Một lần update cần tăng thêm 80 GB.
- Quota còn lại là 100 GB, nên về mặt quota yêu cầu có thể phù hợp.
- Tuy nhiên, region có thể đang thiếu capacity hoặc provider có thể áp dụng giới hạn riêng cho loại volume đó.

Một ma trận kiểm tra:

| Phạm vi | Cần kiểm tra | Nguồn dữ liệu |
|---|---|---|
| Instance | Giới hạn CPU, memory, storage, connections | Plan definition và provider state |
| Service/plan | Plan đích có cho phép cấu hình yêu cầu không | Catalog và policy nội bộ |
| Tenant/organization | Tổng quota và mức sử dụng hiện tại | Usage/quota service của broker |
| Provider account/project | Quota tài nguyên của tài khoản | API quota của provider |
| Region/zone | Capacity và loại tài nguyên khả dụng | API/provider scheduler |
| Thời điểm update | Reservation của các operation đang chạy | Database operation và quota reservation |

Không nên chỉ đọc quota rồi thực hiện update mà không giữ chỗ. Hai request đồng thời có thể cùng nhìn thấy 100 GB còn lại và mỗi request đều yêu cầu 80 GB. Nếu không có reservation hoặc cơ chế đồng bộ, tổng nhu cầu sẽ vượt quota.

## 6. Reservation và xử lý cạnh tranh quota

Để tránh hai update cùng tiêu thụ một phần quota, broker cần quản lý reservation. Reservation ghi nhận phần tài nguyên dự kiến được dùng trong khi operation đang chạy.

Một quy trình điển hình:

1. Đọc quota và mức sử dụng hiện tại.
2. Tính phần tăng hoặc giảm do update.
3. Trong transaction, khóa hoặc cập nhật nguyên tử bản ghi quota.
4. Tạo reservation gắn với instanceId và operationId.
5. Chỉ tiếp tục gọi provider sau khi reservation thành công.
6. Khi provider xác nhận thành công, cập nhật usage và giải phóng reservation.
7. Khi update thất bại chắc chắn, giải phóng reservation.
8. Nếu kết quả provider chưa rõ, giữ reservation ở trạng thái pending cho đến khi reconciliation xác định được kết quả.

Ví dụ, một tenant còn 100 GB quota. Hai instance đồng thời yêu cầu tăng 80 GB và 40 GB. Nếu mỗi request chỉ đọc quota, cả hai có thể cùng được chấp nhận. Nếu broker dùng phép cập nhật nguyên tử, request 80 GB có thể reserve trước; request 40 GB sau đó chỉ thấy còn 20 GB và bị từ chối hoặc chờ.

Không nên giải phóng reservation chỉ vì HTTP request đến provider timeout. Provider có thể đã áp dụng thay đổi nhưng response bị mất. Broker cần truy vấn operation hoặc trạng thái tài nguyên trước khi kết luận thất bại và hoàn quota.

Với thay đổi làm giảm usage, chỉ giảm số liệu quota sau khi provider xác nhận tài nguyên thực sự đã giảm. Việc broker nhận request giảm storage không có nghĩa provider đã giải phóng dung lượng.

## 7. Xác nhận khả năng thực tế của provider

Provider capability không chỉ là việc API có endpoint update. Khả năng thực tế phụ thuộc vào tổ hợp điều kiện:

- Loại resource và engine đang dùng.
- Plan nguồn và plan đích.
- Phiên bản API hoặc phiên bản dịch vụ của provider.
- Region, zone và loại storage/compute.
- Quyền của service account.
- Trạng thái hiện tại của resource.
- Maintenance window hoặc yêu cầu downtime.
- Các operation đang chạy và giới hạn tốc độ API.

Ví dụ, provider có thể hỗ trợ tăng storage cho PostgreSQL nhưng không hỗ trợ giảm storage. Có thể hỗ trợ đổi CPU/memory ở một số loại instance nhưng yêu cầu restart ở loại khác. Một region có thể hỗ trợ high-availability còn region khác không có topology phù hợp.

Do đó, adapter nên cung cấp một phép kiểm tra capability có ngữ cảnh thay vì chỉ một boolean toàn cục.

Một kết quả nội bộ có thể gồm:

~~~java
public record ProviderCapabilityResult(
    boolean supported,
    String reasonCode,
    UpdateStrategy strategy,
    boolean requiresMaintenance,
    boolean asynchronous,
    Duration estimatedDuration
) {}
~~~

Đây là model minh họa của ứng dụng. Provider adapter có thể lấy dữ liệu từ API mô tả tài nguyên, API capability, cấu hình đã xác minh hoặc policy theo phiên bản. Nếu provider không có endpoint kiểm tra riêng, broker có thể dùng capability matrix đã được kiểm thử và kết hợp với trạng thái resource hiện tại.

### Kiểm tra capability có thời hạn

Một capability đã kiểm tra trước đó có thể trở nên lỗi thời khi provider thay đổi API, region hết capacity hoặc quyền tài khoản bị thu hồi. Có thể cache kết quả kiểm tra trong một khoảng thời gian, nhưng phải:

- Gắn cache key với provider, account/project, region, resource type, source plan và target plan.
- Ghi thời điểm kiểm tra và phiên bản dữ liệu.
- Đặt TTL phù hợp.
- Làm mới khi có lỗi capability hoặc provider báo trạng thái không còn hợp lệ.
- Kiểm tra lại điều kiện quan trọng ngay trước khi thực hiện thay đổi nếu provider hỗ trợ.

Không gọi API capability quá dày cho mỗi request nếu có thể dùng cache hoặc cấu hình đã kiểm chứng. Tuy nhiên, không dùng cache cũ như một bảo đảm capacity hiện tại.

## 8. Quy trình preflight trước khi update

Có thể tổ chức kiểm tra trước khi update thành một pipeline:

~~~mermaid
flowchart TD
    Request["Update request"] --> Load["Đọc instance và trạng thái hiện tại"]
    Load --> Service["Kiểm tra service và plan đích"]
    Service --> Transition["Kiểm tra cạnh source -> target"]
    Transition --> Limits["Kiểm tra usage và giới hạn plan"]
    Limits --> Quota["Kiểm tra và reserve quota"]
    Quota --> Capability["Kiểm tra provider capability"]
    Capability --> Conflict["Kiểm tra operation/maintenance conflict"]
    Conflict --> Ready["Preflight passed"]
    Ready --> Execute["Thực hiện update"]
    Transition --> Reject["Từ chối có lý do"]
    Limits --> Reject
    Quota --> Reject
    Capability --> Reject
    Conflict --> Reject
~~~

Một số bước có thể chạy song song nếu độc lập, nhưng quota reservation, khóa instance và các thay đổi trạng thái cần có thứ tự rõ ràng. Không nên thực hiện side effect ở provider trước khi biết request có vượt limit hoặc không có đường chuyển đổi hợp lệ.

### Thứ tự kiểm tra đề xuất

1. **Tải instance**: xác định service, plan hiện tại, provider resource ID, region và trạng thái.
2. **Kiểm tra trạng thái**: instance phải ở trạng thái cho phép update; không có update, restore hoặc deprovision xung đột.
3. **Kiểm tra service và plan**: service ID khớp, plan đích tồn tại và đang cho phép chuyển đổi.
4. **Kiểm tra transition graph**: có cạnh từ plan hiện tại sang plan đích và policy cho phép.
5. **Kiểm tra parameters**: schema, giá trị mặc định, giới hạn và điều kiện nghiệp vụ.
6. **Kiểm tra usage/limits**: mức sử dụng hiện tại phù hợp với plan đích.
7. **Reserve quota**: giữ chỗ tài nguyên tăng thêm một cách nguyên tử.
8. **Kiểm tra provider capability**: xác nhận loại resource, region, account và strategy.
9. **Kiểm tra maintenance/conflict**: xác định cửa sổ bảo trì và operation đang chạy.
10. **Ghi operation**: tạo operation record và trạng thái update trước khi gọi provider.

Nếu capability check yêu cầu thông tin quota hiện tại từ provider, có thể cần điều chỉnh thứ tự giữa quota và capability. Điều quan trọng là mọi reservation phải có thể rollback hoặc reconciliation, và không thực hiện thay đổi tài nguyên trước khi preflight hoàn tất.

## 9. Ví dụ triển khai lớp PlanTransitionValidator

Một validator nội bộ có thể tách việc kiểm tra đường chuyển đổi khỏi handler OSB:

~~~java
@Service
public class PlanTransitionValidator {

    private final PlanTransitionRepository transitions;
    private final PlanRepository plans;

    public PlanTransitionValidator(
            PlanTransitionRepository transitions,
            PlanRepository plans) {
        this.transitions = transitions;
        this.plans = plans;
    }

    public Mono<ValidatedTransition> validate(
            ServiceInstance instance,
            String targetPlanId,
            Map<String, Object> parameters) {

        return plans.findById(targetPlanId)
            .switchIfEmpty(Mono.error(
                new UnknownTargetPlanException(targetPlanId)))
            .flatMap(targetPlan ->
                transitions.find(
                        instance.getPlanId(),
                        targetPlanId)
                    .switchIfEmpty(Mono.error(
                        new UnsupportedPlanTransitionException(
                            instance.getPlanId(),
                            targetPlanId)))
                    .flatMap(transition ->
                        validateCurrentUsage(
                            instance, targetPlan, transition)
                            .thenReturn(new ValidatedTransition(
                                targetPlan,
                                transition,
                                parameters))
                    )
            );
    }

    private Mono<Void> validateCurrentUsage(
            ServiceInstance instance,
            ServicePlan targetPlan,
            PlanTransition transition) {

        return usageService.getUsage(instance.getProviderResourceId())
            .flatMap(usage -> {
                if (usage.storageGb()
                        > targetPlan.maxStorageGb()) {
                    return Mono.error(
                        new TargetPlanLimitExceededException());
                }

                if (transition.maximumCurrentStorageGb() != null
                        && usage.storageGb()
                        > transition.maximumCurrentStorageGb()) {
                    return Mono.error(
                        new UnsupportedDowngradeException());
                }

                return Mono.empty();
            });
    }
}
~~~

Ví dụ trên là skeleton minh họa; repository, model, usageService và exception là thành phần nội bộ. Cần bổ sung validation cho các chiều tài nguyên khác, nullability, trạng thái instance, parameters và chính sách riêng của provider. Nếu usage API không trả dữ liệu đáng tin cậy, validator cần xử lý theo policy rõ ràng thay vì mặc định mức sử dụng bằng 0.

Sau validator, một coordinator có thể tiếp tục kiểm tra quota, provider capability, reserve quota và tạo operation. Giữ các bước kiểm tra thuần túy tách khỏi bước tạo side effect giúp dễ viết unit test và dễ giải thích lý do từ chối.

## 10. Xử lý update bất đồng bộ và thay đổi trạng thái

Một số provider có thể hoàn tất update ngay; một số khác trả về provider operation ID và yêu cầu polling. Nếu client OSB chấp nhận bất đồng bộ, broker có thể trả response async theo hợp đồng và cho nền tảng truy vấn last operation.

Một operation nội bộ có thể lưu:

| Thuộc tính | Mục đích |
|---|---|
| operationId | Định danh thao tác update trong broker |
| instanceId | Instance đang được cập nhật |
| sourcePlanId | Plan trước update |
| targetPlanId | Plan đích |
| providerOperationId | ID thao tác phía provider |
| state | PRECHECKED, RUNNING, SUCCEEDED, FAILED hoặc trạng thái nội bộ tương đương |
| quotaReservationId | Reservation đang giữ |
| transitionStrategy | Chiến lược update đã chọn |
| startedAt, updatedAt | Thời điểm thực hiện |
| failureCode | Mã lỗi đã làm sạch |

Luồng xử lý:

1. Khóa hoặc reserve instance để ngăn update khác chạy đồng thời.
2. Lưu operation và quota reservation.
3. Gọi provider adapter.
4. Nếu provider hoàn tất ngay, xác minh trạng thái mới và commit plan đích.
5. Nếu provider trả operation ID, lưu ID và trả response async nếu client chấp nhận.
6. Worker poll hoặc nhận callback theo cơ chế provider hỗ trợ.
7. Khi thành công, cập nhật plan, usage và trạng thái instance; giải phóng reservation.
8. Khi thất bại chắc chắn, áp dụng rollback hoặc giữ trạng thái cần reconciliation; giải phóng reservation khi biết chắc tài nguyên chưa đổi hoặc đã được phục hồi.
9. Nếu trạng thái chưa xác định, giữ operation và reservation ở trạng thái pending, không tự ghi plan đích hoặc plan cũ như thể đã chắc chắn.

Không cập nhật planId nội bộ sang plan đích ngay khi gửi request provider. Chỉ cập nhật sau khi provider xác nhận tài nguyên thực sự đã chuyển. Trong lúc đang chạy, có thể lưu targetPlanId riêng trong operation để theo dõi.

Nếu thao tác là recreate-and-migrate, rollback có thể không đơn giản. Cần lưu checkpoint, backup, endpoint cũ và mới, trạng thái chuyển traffic, cũng như điều kiện xác nhận có thể quay lại tài nguyên cũ.

## 11. Idempotency và khóa đồng thời cho update

Nền tảng có thể retry update khi mất response. Broker cần nhận diện cùng một yêu cầu để không khởi chạy nhiều lần chuyển plan.

Một fingerprint có thể dựa trên instanceId, source plan, target plan, parameters đã chuẩn hóa và các giá trị context có ảnh hưởng đến thay đổi. Cùng instance và cùng fingerprint đang chạy thì trả lại operation hiện có. Cùng instance nhưng yêu cầu khác khi operation trước chưa kết thúc cần bị từ chối hoặc xếp hàng theo policy.

Có thể dùng:

- Unique constraint cho operation update đang hoạt động theo instance.
- Optimistic locking bằng version của bản ghi instance.
- Distributed lock hoặc database row lock trong khoảng ngắn để reserve.
- Idempotency key ổn định khi gọi provider.
- Reconciliation khi timeout khiến kết quả provider không rõ ràng.

Không giữ distributed lock trong suốt một operation kéo dài nhiều giờ. Hãy dùng trạng thái operation và lease/heartbeat có thời hạn để worker khác có thể tiếp quản khi node xử lý bị lỗi, đồng thời vẫn bảo vệ tài nguyên khỏi hai update cạnh tranh.

## 12. Ánh xạ lỗi preflight thành phản hồi có thể xử lý

Lỗi kiểm tra cần có mã và thông điệp đủ rõ để người gọi hiểu nguyên nhân mà không làm lộ dữ liệu nội bộ.

| Lý do | Ví dụ | Hướng xử lý |
|---|---|---|
| Plan đích không tồn tại | plan_id không được catalog nhận diện | Chọn plan hợp lệ |
| Không có đường chuyển | source plan không có cạnh tới target | Chọn đường chuyển được hỗ trợ |
| Vượt giới hạn plan | Usage hiện tại vượt storage tối đa | Giảm usage hoặc chọn plan lớn hơn |
| Vượt quota | Tenant không còn đủ quota | Giải phóng quota hoặc yêu cầu tăng hạn mức |
| Thiếu capacity | Region không đủ tài nguyên tại thời điểm update | Thử lại sau hoặc chọn region/strategy khác nếu được phép |
| Provider không hỗ trợ | Loại instance không hỗ trợ resize | Chọn strategy hoặc plan khác |
| Cần bảo trì | Update cần maintenance window | Lên lịch theo policy |
| Có operation xung đột | Instance đang restore hoặc update | Chờ operation hiện tại hoàn tất |
| Trạng thái không xác định | Provider timeout sau khi nhận update | Reconcile trước khi retry |

Lỗi validation không nên trả về stack trace hoặc thông tin nhạy cảm. Có thể log correlation ID, instanceId, operationId và provider request ID cùng mã lỗi đã làm sạch.

Đối với lỗi tạm thời như rate limit hoặc capacity tạm thời, broker cần phân biệt với lỗi cấu hình không thể retry. Không tự retry vô hạn một yêu cầu chắc chắn không hợp lệ.

## 13. Kiểm thử đường chuyển plan, quota và provider capability

Một bộ kiểm thử cần bao phủ cả điều kiện hợp lệ và các trường hợp cạnh tranh:

| Trường hợp | Kết quả mong đợi |
|---|---|
| Có transition small → standard | Preflight cho phép tiếp tục |
| Không có transition standard → small | Từ chối trước khi gọi provider |
| Instance đang dùng vượt limit plan đích | Từ chối và nêu lý do phù hợp |
| Parameters vượt schema | Từ chối, không tạo operation thực thi |
| Quota đủ | Reservation được tạo |
| Quota không đủ | Không gọi provider |
| Hai update cùng tiêu thụ quota | Reservation nguyên tử ngăn vượt quota |
| Provider không hỗ trợ loại resource | Từ chối trước side effect |
| Capability cache đã hết hạn | Làm mới theo policy |
| Provider timeout sau khi nhận lệnh | Giữ trạng thái chưa xác định và reconciliation |
| Update cần maintenance | Operation được lên lịch hoặc từ chối theo policy |
| Retry cùng request | Trả operation/result hiện có |
| Request khác khi update đang chạy | Từ chối hoặc xếp hàng theo policy |

Nên kiểm thử validator độc lập với provider bằng các test double. Kiểm thử quota cần mô phỏng hai request đồng thời. Kiểm thử provider adapter cần bao gồm response thành công, lỗi quyền, rate limit, timeout trước và sau khi provider có thể đã thực hiện thay đổi.

Kiểm thử tích hợp nên xác nhận cả response OSB API, trạng thái operation, plan lưu trong database, usage/quota reservation và trạng thái thực tế phía provider. Chỉ kiểm tra HTTP status là chưa đủ để chứng minh update an toàn.

## 14. Những sai lầm thường gặp

**Cho rằng plan lớn hơn luôn là đường nâng cấp hợp lệ.** Hai plan có thể khác engine, topology hoặc region. Cần kiểm tra transition graph và khả năng provider.

**Cho rằng plan_updateable bật nghĩa là mọi chuyển đổi đều được phép.** Capability này chỉ cho biết service hỗ trợ update plan ở mức tổng quát. Policy nội bộ vẫn phải kiểm tra cặp source-target.

**Chỉ so sánh cấu hình plan mà không đọc usage thực tế.** Instance có thể đang dùng nhiều storage hoặc connection hơn giới hạn của plan đích. Phải kiểm tra trạng thái tài nguyên hiện tại.

**Coi quota còn dư là capacity chắc chắn.** Quota và capacity là hai khái niệm khác nhau. Provider vẫn có thể từ chối do region thiếu tài nguyên.

**Kiểm tra quota nhưng không reserve.** Hai request đồng thời có thể cùng tiêu thụ một phần quota. Dùng reservation và cập nhật nguyên tử.

**Tin kết quả capability đã cache quá lâu.** Quyền, region và provider API có thể thay đổi. Cache cần scope rõ và TTL phù hợp; điều kiện quan trọng phải được xác minh lại khi thực thi.

**Cập nhật plan nội bộ trước khi provider hoàn tất.** Nếu provider thất bại, broker sẽ mô tả sai trạng thái instance. Chỉ commit plan đích sau khi xác nhận kết quả.

**Giải phóng quota ngay khi timeout.** Timeout không chứng minh provider chưa thay đổi tài nguyên. Hãy reconcile trước khi hoàn quota.

## 15. Nguyên tắc triển khai trong Spring Cloud Service Broker

Trong ứng dụng Spring Cloud Open Service Broker, nên để handler update nhận request OSB và chuyển sang một coordinator có trách nhiệm kiểm tra, lập operation và điều phối provider adapter. Transition graph, plan limits, quota policy và provider capability cần được mô hình hóa thành các thành phần có thể kiểm thử độc lập.

Catalog công bố khả năng update tổng quát; broker kiểm tra đường chuyển cụ thể ở runtime. Plan đích phải tương thích với usage hiện tại và parameters. Quota cần được reserve an toàn trước side effect. Provider capability phải được đánh giá theo resource type, account, region, phiên bản API và trạng thái instance. Với update dài, lưu operation bền vững, hỗ trợ retry idempotent và reconciliation khi kết quả không rõ ràng.

Chỉ đánh dấu update thành công và thay đổi plan hiện tại sau khi provider xác nhận trạng thái đích. Nếu thao tác thất bại hoặc chưa xác định, giữ đủ dữ liệu để phục hồi và phản hồi đúng trạng thái cho nền tảng. Cách làm này giúp service broker bảo đảm mọi đường chuyển plan được công bố đều có điều kiện thực thi rõ ràng, phù hợp với hạn mức và năng lực thật của nhà cung cấp.

