# PATCH /v2/service_instances/{instance_id} và điều kiện plan_updateable

Open Service Broker API (OSB API) sử dụng endpoint **PATCH /v2/service_instances/{instance_id}** để yêu cầu service broker cập nhật một service instance đã được provision. Request có thể thay đổi các tham số cấu hình mà broker cho phép hoặc chuyển instance sang một service plan khác nếu offering công bố khả năng cập nhật plan.

Trong Spring Cloud Open Service Broker (SCOSB), nghiệp vụ này được triển khai qua abstraction **ServiceInstanceService** và phương thức xử lý update tương ứng. Broker phải xác thực request, kiểm tra instance và plan, xác định thay đổi có được phép hay không, rồi mới gọi provider. Đặc biệt, thuộc tính **plan_updateable** trong catalog là tín hiệu năng lực mà broker công bố cho platform; nó không có nghĩa mọi chuyển đổi plan đều hợp lệ.

Bài học thuộc module **SPRING_CLOUD_SERVICE_BROKER**, tập trung vào cấu trúc request PATCH, ý nghĩa của **plan_updateable**, quy tắc kiểm tra plan nguồn/đích, cập nhật tham số, phản hồi đồng bộ hoặc bất đồng bộ, idempotency và cách tổ chức implementation trong Spring Cloud.

## 1. PATCH dùng để làm gì?

Một service instance được tạo bằng request provision. Sau khi hoạt động, người dùng có thể cần thay đổi cấu hình, chẳng hạn tăng dung lượng database, thay đổi thời gian lưu backup hoặc nâng plan từ **small** lên **standard**. Platform gửi yêu cầu update đến broker, broker quyết định thay đổi có được hỗ trợ và phối hợp với provider để thực hiện.

Endpoint chuẩn:

~~~http
PATCH /v2/service_instances/{instance_id}
~~~

**instance_id** là định danh của service instance do platform cấp và sử dụng xuyên suốt vòng đời tài nguyên. Broker dùng ID này để tìm bản ghi nội bộ, xác định provider resource ID, plan hiện tại, trạng thái và cấu hình đã provision.

Luồng tổng quát:

~~~mermaid
sequenceDiagram
    actor User as Người dùng
    participant P as Platform
    participant B as Service broker
    participant DB as Broker store
    participant V as Validator / Policy
    participant S as Service provider

    User->>P: Yêu cầu thay đổi plan hoặc cấu hình
    P->>B: PATCH /v2/service_instances/{instance_id}
    B->>DB: Đọc instance và trạng thái hiện tại
    DB-->>B: Service, plan, provider resource, version
    B->>V: Kiểm tra quyền và điều kiện update
    V-->>B: Thay đổi hợp lệ
    B->>DB: Ghi nhận operation / trạng thái
    B->>S: Cập nhật tài nguyên
    S-->>B: Kết quả update
    B->>DB: Lưu plan và cấu hình mới
    B-->>P: 200 OK hoặc 202 Accepted
~~~

PATCH không tạo một service instance mới. Nó thay đổi trạng thái mong muốn của instance đã tồn tại. Broker phải bảo toàn định danh instance và lịch sử cần thiết để những request fetch, bind, unbind hoặc deprovision tiếp theo vẫn tham chiếu đúng tài nguyên.

## 2. Cấu trúc request update

Một request update có thể chứa các trường sau:

| Trường | Vai trò |
|---|---|
| **service_id** | ID của service offering mà instance thuộc về |
| **plan_id** | ID plan mà platform muốn instance sử dụng sau khi update |
| **parameters** | Các tham số cấu hình được phép cập nhật theo hợp đồng của broker |
| **previous_values** | Thông tin giá trị trước đó mà platform biết, hỗ trợ broker nhận diện thay đổi |
| **context** | Ngữ cảnh platform nếu được sử dụng trong môi trường triển khai |

Ví dụ request nâng cấp một database từ plan nhỏ lên plan tiêu chuẩn:

~~~http
PATCH /v2/service_instances/instance-7f31?accepts_incomplete=true
Content-Type: application/json
X-Broker-API-Version: 2.17
Authorization: Basic <broker-credentials>
~~~

~~~json
{
  "service_id": "svc-postgresql",
  "plan_id": "plan-pg-standard",
  "parameters": {
    "storageGb": 200,
    "backupEnabled": true,
    "backupRetentionDays": 14
  },
  "previous_values": {
    "service_id": "svc-postgresql",
    "plan_id": "plan-pg-small",
    "organization_id": "org-123",
    "space_id": "space-456"
  }
}
~~~

Đây là dữ liệu minh họa. Broker cần xác định chính xác schema update mà offering công bố và những field mà phiên bản OSB API/platform đang sử dụng hỗ trợ.

### Ý nghĩa của từng phần

**service_id** xác định offering của instance. Trong một lần update thông thường, service offering không được thay đổi tùy ý. Broker phải kiểm tra service ID request gửi lên khớp với service ID đã lưu cho instance. Chuyển sang một loại dịch vụ khác thường là một quy trình migration riêng, không phải đổi service_id bằng PATCH.

**plan_id** xác định plan đích. Nếu platform gửi plan ID khác plan hiện tại, broker phải kiểm tra khả năng plan update và chính sách chuyển đổi. Nếu plan không đổi, request vẫn có thể cập nhật các tham số được hỗ trợ.

**parameters** chứa cấu hình mới theo schema update. Broker phải phân biệt tham số không được gửi, tham số được gửi với giá trị null và tham số được gửi với giá trị cụ thể theo hợp đồng của offering. Không mặc định rằng mọi field bị bỏ qua đều phải reset về default.

**previous_values** có thể cho broker biết platform đang nhìn thấy giá trị cũ nào, ví dụ plan trước đó hoặc ngữ cảnh organization/space. Đây là thông tin hỗ trợ so sánh thay đổi; broker vẫn phải đọc trạng thái authoritative từ kho lưu trữ của mình và provider khi cần. Không dùng previous_values do client gửi làm bằng chứng duy nhất về plan hoặc trạng thái hiện tại.

## 3. plan_updateable là gì?

Trong catalog OSB API, service definition có thuộc tính **plan_updateable** để broker công bố khả năng thay đổi plan cho service offering đó.

Ví dụ catalog rút gọn:

~~~json
{
  "services": [
    {
      "id": "svc-postgresql",
      "name": "postgresql",
      "description": "Managed PostgreSQL database",
      "bindable": true,
      "plan_updateable": true,
      "plans": [
        {
          "id": "plan-pg-small",
          "name": "small",
          "description": "Small database instance"
        },
        {
          "id": "plan-pg-standard",
          "name": "standard",
          "description": "Standard database instance"
        }
      ]
    }
  ]
}
~~~

Khi **plan_updateable** là true, platform biết broker hỗ trợ nghiệp vụ chuyển plan cho các instance thuộc offering đó và có thể hiển thị chức năng nâng cấp/hạ cấp plan. Nếu thuộc tính bị bỏ qua hoặc là false, platform không nên cung cấp thao tác chuyển plan cho service đó.

Cần phân biệt ba điều:

1. **Năng lực ở cấp service:** plan_updateable cho biết offering có hỗ trợ thay đổi plan hay không.
2. **Điều kiện ở cấp cặp plan:** dù offering hỗ trợ update plan, không phải mọi plan nguồn và plan đích đều có thể chuyển đổi. Ví dụ không hỗ trợ hạ cấp từ enterprise về small nếu dung lượng hiện tại vượt giới hạn small.
3. **Điều kiện ở cấp instance:** instance cụ thể phải ở trạng thái cho phép update, caller phải có quyền và provider phải hỗ trợ thay đổi tại thời điểm request.

Do đó, **plan_updateable=true** là công bố khả năng tổng quát, không phải giấy phép tự động cho mọi chuyển đổi. Broker luôn cần kiểm tra chính sách thực tế.

### Cài đặt thuộc tính trong Spring Cloud Open Service Broker

Khi dùng SCOSB, service definition được xây dựng trong catalog có thể khai báo khả năng này:

~~~java
import java.util.List;

import org.springframework.cloud.servicebroker.model.catalog.Catalog;
import org.springframework.cloud.servicebroker.model.catalog.Plan;
import org.springframework.cloud.servicebroker.model.catalog.ServiceDefinition;

Catalog catalog = Catalog.builder()
        .serviceDefinitions(List.of(
                ServiceDefinition.builder()
                        .id("svc-postgresql")
                        .name("postgresql")
                        .description("Managed PostgreSQL database")
                        .bindable(true)
                        .planUpdateable(true)
                        .plans(List.of(
                                Plan.builder()
                                        .id("plan-pg-small")
                                        .name("small")
                                        .description("Small database instance")
                                        .build(),
                                Plan.builder()
                                        .id("plan-pg-standard")
                                        .name("standard")
                                        .description("Standard database instance")
                                        .build()
                        ))
                        .build()
        ))
        .build();
~~~

**planUpdateable(true)** được đặt trên **ServiceDefinition**, vì đây là khả năng của service offering. Nó không phải thuộc tính của từng đối tượng Plan. Broker vẫn cần kiểm tra cặp plan cụ thể trong service update.

Nếu broker không hỗ trợ thay đổi plan, nên công bố **plan_updateable=false** hoặc để thuộc tính ở giá trị mặc định theo mô hình catalog của framework. Không khai báo true chỉ để platform hiển thị nút nâng cấp khi provider chưa có khả năng thực hiện.

## 4. Phân biệt cập nhật tham số và cập nhật plan

Một request PATCH có thể cập nhật tham số mà không đổi plan, hoặc thay đổi plan. Hai trường hợp cần kiểm tra khác nhau.

| Tình huống | plan_id trong request | Điều kiện chính |
|---|---|---|
| Chỉ đổi tham số | Trùng plan hiện tại | Schema update cho phép các field; instance và provider hỗ trợ |
| Nâng cấp plan | Khác plan hiện tại, plan đích cao hơn | plan_updateable=true, cặp plan được phép và provider có khả năng nâng cấp |
| Hạ cấp plan | Khác plan hiện tại, plan đích thấp hơn | plan_updateable=true, dữ liệu/tài nguyên đáp ứng giới hạn plan đích |
| Không hỗ trợ plan update | Khác plan hiện tại | Broker từ chối yêu cầu đổi plan |
| Chỉ gửi plan ID hiện tại | Trùng plan hiện tại | Có thể là update tham số hoặc request không tạo thay đổi; xử lý nhất quán |

Một số offering có thể chỉ cho phép nâng cấp chứ không cho phép hạ cấp. Một số provider yêu cầu dừng instance hoặc chạy migration trước khi chuyển plan. Chính sách này thuộc broker và provider, không thể suy ra chỉ từ thứ tự tên plan.

### Ví dụ quy tắc chuyển đổi

Giả sử có ba plan:

| Plan | Dung lượng tối đa | Có thể chuyển đến |
|---|---:|---|
| small | 100 GB | standard |
| standard | 500 GB | enterprise |
| enterprise | 2.000 GB | Không hỗ trợ hạ cấp trực tiếp |

Với instance đang ở plan **small**, yêu cầu chuyển sang **standard** có thể được chấp nhận nếu dung lượng hiện tại, quota và provider đều cho phép. Yêu cầu chuyển từ **enterprise** về **small** phải bị từ chối nếu dữ liệu hoặc cấu hình hiện tại vượt giới hạn của plan đích.

Nên biểu diễn các chuyển đổi được hỗ trợ thành policy rõ ràng thay vì so sánh chuỗi tên plan hoặc giả định plan nào có giá cao hơn là plan lớn hơn.

## 5. Kiểm tra schema update của parameters

Catalog có thể công bố schema riêng cho thao tác update. Schema này mô tả những tham số mà platform có thể gửi, nhưng broker vẫn phải xác thực lại.

Ví dụ schema update:

~~~json
{
  "schemas": {
    "service_instance": {
      "update": {
        "parameters": {
          "type": "object",
          "additionalProperties": false,
          "properties": {
            "storageGb": {
              "type": "integer",
              "minimum": 10,
              "maximum": 500
            },
            "backupEnabled": {
              "type": "boolean"
            },
            "backupRetentionDays": {
              "type": "integer",
              "minimum": 7,
              "maximum": 35
            }
          }
        }
      }
    }
  }
}
~~~

Schema update cần được thiết kế khác schema create khi có field chỉ đặt lúc provision. Ví dụ, **databaseName** hoặc **region** có thể bất biến sau khi tạo instance; broker không nên đưa chúng vào schema update nếu không hỗ trợ thay đổi.

Validation phía broker nên kiểm tra:

- Field có nằm trong allowlist của thao tác update hay không.
- Kiểu dữ liệu có đúng không; không tự ép chuỗi thành số hoặc boolean.
- Giá trị có nằm trong giới hạn plan đích hoặc chính sách update không.
- Các field có quan hệ với nhau hợp lệ không, ví dụ backup retention chỉ có ý nghĩa khi backup được bật.
- Tham số có thể thay đổi ở trạng thái instance hiện tại hay không.
- Plan mới có hỗ trợ cấu hình được gửi không.

Với PATCH, không nên mặc định rằng request body tuân theo JSON Merge Patch. Cách hiểu các field bị bỏ qua, null và giá trị mặc định phải được định nghĩa theo hợp đồng parameters của service broker. Một số broker xem parameters là cấu hình mong muốn đầy đủ; broker khác xem đây là tập thay đổi. Phải công bố và thực thi nhất quán.

## 6. Quy trình xử lý PATCH ở broker

Một luồng update có thể chia thành các bước:

1. Xác thực platform và quyền của caller.
2. Tìm service instance bằng instance_id.
3. Đọc service ID, plan hiện tại, cấu hình hiện tại, trạng thái và provider resource ID từ kho dữ liệu broker.
4. Xác nhận service_id trong request khớp với service ID đã lưu cho instance.
5. Xác định plan đích và so sánh với plan hiện tại.
6. Nếu plan thay đổi, kiểm tra plan_updateable, cặp plan nguồn/đích và policy migration.
7. Kiểm tra schema update, tham số, quota và giới hạn provider.
8. Kiểm tra instance đang ở trạng thái có thể update và không có operation xung đột.
9. Ghi nhận operation hoặc trạng thái update trước khi thực hiện side effect.
10. Gọi provider để thay đổi cấu hình hoặc chuyển plan.
11. Lưu plan/cấu hình mới sau khi provider xác nhận thành công.
12. Trả response đồng bộ hoặc bất đồng bộ theo khả năng và yêu cầu của platform.

~~~mermaid
flowchart TD
    A["PATCH request"] --> B["Load instance by instance_id"]
    B --> C{"Instance exists and authorized?"}
    C -->|"No"| X["Return OSB error"]
    C -->|"Yes"| D["Check service_id"]
    D --> E["Compare current plan and target plan"]
    E --> F{"Plan changed?"}
    F -->|"Yes"| G{"plan_updateable is true?"}
    G -->|"No"| X
    G -->|"Yes"| H["Validate transition policy"]
    F -->|"No"| I["Validate update parameters"]
    H --> I
    I --> J{"Parameters, quota and state valid?"}
    J -->|"No"| X
    J -->|"Yes"| K["Persist update operation"]
    K --> L["Apply provider change"]
    L --> M{"Provider succeeded?"}
    M -->|"No"| N["Record failure / reconcile"]
    M -->|"Yes"| O["Persist new plan and configuration"]
    O --> P["Return 200 or 202 workflow result"]
~~~

Việc lưu operation và trạng thái trước khi gọi provider giúp broker phục hồi sau restart. Tuy nhiên, broker cũng cần xử lý cửa sổ lỗi: provider có thể đã áp dụng thay đổi nhưng broker chưa kịp lưu kết quả. Cơ chế idempotency và reconciliation sẽ giúp phát hiện trạng thái thật và tránh chạy migration lặp không an toàn.

## 7. Triển khai update qua ServiceInstanceService

Spring Cloud Open Service Broker cung cấp interface **ServiceInstanceService** để broker xử lý vòng đời service instance. Phần update cần sử dụng request model do framework cung cấp và chuyển dữ liệu sang lớp nghiệp vụ riêng.

Một cấu trúc tổ chức có thể như sau:

~~~text
ServiceInstanceService
        |
        v
ServiceInstanceUpdateHandler
        |
        +--> InstanceRepository
        +--> CatalogService / PlanPolicyRepository
        +--> UpdateParameterValidator
        +--> PlanTransitionPolicy
        +--> OperationRepository
        +--> ProviderClient
~~~

Ví dụ dưới đây là mã khung minh họa trách nhiệm nghiệp vụ. Tên accessor và constructor cụ thể cần đối chiếu phiên bản SCOSB trong dự án:

~~~java
public Mono<UpdateServiceInstanceResponse> updateServiceInstance(
        UpdateServiceInstanceRequest request) {

    String instanceId = request.getServiceInstanceId();

    return instanceRepository.findById(instanceId)
            .switchIfEmpty(Mono.error(
                    new ServiceInstanceNotFoundException(instanceId)))
            .flatMap(instance -> authorizationService
                    .checkCanUpdate(request, instance)
                    .thenReturn(instance))
            .flatMap(instance -> planPolicyRepository
                    .load(instance.getServiceId(),
                            request.getPlanId())
                    .switchIfEmpty(Mono.error(
                            new PlanNotAvailableException()))
                    .map(targetPlan -> new UpdateContext(
                            instance, targetPlan, request)))
            .flatMap(updateValidator::validate)
            .flatMap(updateHandler::execute)
            .map(result -> UpdateServiceInstanceResponse.builder()
                    .build());
}
~~~

Đây là skeleton để minh họa cách phân lớp, không phải implementation hoàn chỉnh cho mọi phiên bản SCOSB. Trong ứng dụng thật:

- **InstanceRepository** đọc trạng thái hiện tại và kiểm soát cập nhật đồng thời.
- **AuthorizationService** xác minh caller có quyền trên instance và tenant.
- **PlanPolicyRepository** đọc service definition, plan đích và giới hạn.
- **UpdateValidator** kiểm tra tham số và trạng thái.
- **PlanTransitionPolicy** quyết định cặp plan có thể chuyển đổi.
- **OperationRepository** lưu trạng thái và mã operation.
- **ProviderClient** gọi API quản trị của provider.
- Response builder được cấu hình theo kết quả đồng bộ hoặc bất đồng bộ mà handler trả về.

Không nên đặt logic gọi provider trong controller hoặc trong bước mapping đơn giản. Một lớp handler riêng giúp kiểm thử quy tắc chuyển plan và xử lý lỗi độc lập với giao thức HTTP.

### Ví dụ kiểm tra plan_updateable

Pseudocode:

~~~java
void validatePlanChange(
        ServiceDefinition service,
        String currentPlanId,
        String targetPlanId) {

    if (currentPlanId.equals(targetPlanId)) {
        return; // Không có chuyển plan; vẫn kiểm tra parameters update.
    }

    if (!service.isPlanUpdateable()) {
        throw new PlanUpdateNotSupportedException();
    }

    if (!transitionPolicy.canTransition(
            currentPlanId, targetPlanId)) {
        throw new InvalidPlanTransitionException(
                currentPlanId, targetPlanId);
    }
}
~~~

Tên getter có thể khác tùy phiên bản model. Điều quan trọng là lấy plan_updateable từ service definition của catalog và dùng policy phía broker để kiểm tra chuyển đổi thực tế. Không lấy một boolean do client gửi trong parameters để quyết định quyền đổi plan.

## 8. Phản hồi đồng bộ và bất đồng bộ

Một update có thể hoàn thành nhanh hoặc cần thời gian dài, chẳng hạn mở rộng storage, chuyển vùng dữ liệu hoặc migrate database.

### Cập nhật đồng bộ

Nếu provider hoàn tất trong thời gian xử lý request, broker lưu trạng thái mới và trả **200 OK**. Platform có thể coi update đã hoàn tất và tiếp tục thao tác phụ thuộc.

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
~~~

~~~json
{}
~~~

### Cập nhật bất đồng bộ

Nếu thao tác cần chạy nền, platform phải cho broker biết rằng nó chấp nhận xử lý bất đồng bộ bằng query parameter:

~~~http
PATCH /v2/service_instances/instance-7f31?accepts_incomplete=true
~~~

Broker có thể ghi nhận operation, trả **202 Accepted** cùng mã operation, rồi xử lý provider ở background:

~~~http
HTTP/1.1 202 Accepted
Content-Type: application/json
~~~

~~~json
{
  "operation": "resize-storage-op-981"
}
~~~

Platform dùng endpoint last_operation để theo dõi:

~~~http
GET /v2/service_instances/instance-7f31/last_operation?operation=resize-storage-op-981
~~~

Response trạng thái có thể biểu diễn:

~~~json
{
  "state": "in progress",
  "description": "Increasing database storage"
}
~~~

Khi xong, broker trả trạng thái **succeeded** hoặc **failed** theo hợp đồng OSB API. Platform không nên gửi update mới phụ thuộc vào kết quả cũ trước khi operation hiện tại đạt trạng thái kết thúc.

Nếu broker cần xử lý bất đồng bộ nhưng platform không gửi **accepts_incomplete=true**, broker không được âm thầm nhận một operation nền mà platform không thể theo dõi. Hãy trả lỗi theo quy định OSB API cho trường hợp async không được chấp nhận (thường là **422 Unprocessable Entity** với lỗi **AsyncRequired**).

Trong SCOSB, response update có thể được tạo với cờ async và operation identifier theo API của phiên bản thư viện. Hãy đối chiếu **UpdateServiceInstanceResponse** và tài liệu version đang dùng trước khi chọn builder method cụ thể.

## 9. Idempotency và xử lý request lặp

Platform có thể gửi lại PATCH nếu kết nối bị timeout và không nhận được response, trong khi broker hoặc provider đã bắt đầu thay đổi tài nguyên. Nếu broker coi mỗi request là một update mới, có thể chạy migration hai lần, tăng dung lượng lặp hoặc tạo operation trùng.

Broker nên xác định request lặp bằng tổ hợp:

- instance_id và loại thao tác.
- Service ID và plan ID đích.
- Tham số đã chuẩn hóa.
- Operation hiện tại và fingerprint của yêu cầu.
- Mã operation/provider operation nếu provider cung cấp.

Nếu cùng một yêu cầu đã được xử lý hoặc đang chạy, broker nên trả lại kết quả/operation hiện có theo hợp đồng thay vì tạo side effect mới. Nếu request mới xung đột với một operation đang chạy, broker cần từ chối hoặc yêu cầu platform chờ hoàn tất, theo chính sách đã định nghĩa.

Không được chỉ dựa vào previous_values để quyết định request có phải retry hay không. Đây là dữ liệu do platform gửi; broker phải đối chiếu với trạng thái và operation đã lưu.

## 10. Cập nhật đồng thời và trạng thái instance

Hai người dùng hoặc hai automation có thể gửi PATCH gần như đồng thời cho cùng một instance. Ví dụ một request nâng cấp plan lên standard, request khác thay storage và gửi lại plan small. Nếu không có kiểm soát đồng thời, trạng thái cuối cùng có thể không khớp với provider.

Có thể áp dụng:

- **Optimistic locking:** lưu version của instance; chỉ cập nhật nếu version vẫn như lúc đọc.
- **Pessimistic lock hoặc per-instance queue:** chỉ cho phép một update tác động lên instance tại một thời điểm.
- **State machine:** chỉ nhận update khi instance ở trạng thái READY hoặc trạng thái cho phép đã định nghĩa.
- **Operation ownership:** mỗi operation lưu instance ID, target plan, target parameters và trạng thái.
- **Reconciliation:** đối chiếu trạng thái broker với provider sau timeout, crash hoặc lỗi một phần.

Ví dụ chuyển trạng thái:

~~~mermaid
stateDiagram-v2
    [*] --> READY
    READY --> UPDATING: PATCH accepted
    UPDATING --> READY: Provider success + persist
    UPDATING --> UPDATE_FAILED: Provider failure
    UPDATE_FAILED --> READY: Reconcile / rollback completed
    UPDATING --> UPDATING: Poll status
    READY --> DEPROVISIONING: DELETE
~~~

Không nên chuyển instance về READY ngay khi gửi request provider. Chỉ đánh dấu update thành công khi provider đã xác nhận thay đổi và broker đã lưu trạng thái mới nhất. Nếu provider thực hiện một phần, broker phải ghi nhận trạng thái lỗi và có quy trình khôi phục hoặc reconcile rõ ràng.

## 11. Xử lý lỗi trong quá trình update

Broker nên phân biệt lỗi validation, lỗi chính sách, lỗi trạng thái và lỗi provider.

| Tình huống | Hướng xử lý |
|---|---|
| instance_id không tồn tại | Trả lỗi not found theo OSB API |
| service_id không khớp instance | Từ chối request |
| Offering không bật plan_updateable nhưng plan ID thay đổi | Từ chối yêu cầu đổi plan |
| Plan đích không tồn tại hoặc đã ngừng nhận update | Từ chối theo policy |
| Cặp plan không hỗ trợ chuyển đổi | Trả lỗi nghiệp vụ có mô tả |
| Parameters sai kiểu hoặc vượt giới hạn | Trả lỗi invalid parameters |
| Instance đang provision/update/deprovision | Từ chối hoặc yêu cầu chờ theo state machine |
| Caller không có quyền | Trả lỗi authorization, không tiết lộ dữ liệu tenant khác |
| Provider timeout | Theo dõi operation, retry an toàn hoặc reconcile |
| Lưu trạng thái broker thất bại sau khi provider đổi thành công | Ghi nhận tình huống không nhất quán và reconcile |

Không trả stack trace, SQL, thông tin xác thực provider hoặc dữ liệu nội bộ trong response. Mỗi lỗi nên có correlation ID để đội vận hành liên kết request, operation và provider call trong log.

Nếu provider timeout, không được mặc định rằng provider chưa thực hiện thay đổi. Request có thể đã đến provider và được áp dụng trước khi kết nối đứt. Broker cần truy vấn trạng thái provider hoặc sử dụng operation ID/idempotency key của provider để xác định kết quả trước khi retry.

## 12. Kiểm thử PATCH và plan_updateable

Cần kiểm thử cả metadata catalog lẫn hành vi endpoint update.

| Ca kiểm thử | Kết quả mong đợi |
|---|---|
| plan_updateable=false, plan ID không đổi | Có thể update parameters nếu schema và policy cho phép |
| plan_updateable=false, plan ID thay đổi | Request đổi plan bị từ chối |
| plan_updateable=true, chuyển cặp plan được phép | Provider nhận đúng yêu cầu update |
| plan_updateable=true, cặp plan bị cấm | Request bị từ chối trước side effect |
| Parameters update hợp lệ | Broker cập nhật và lưu cấu hình mới |
| Parameters có field lạ | Validation thất bại, provider không được gọi |
| Thiếu hoặc sai service ID | Request bị từ chối |
| Instance không tồn tại | Trả lỗi not found |
| Instance đang có operation | Không chạy update xung đột |
| Provider hoàn tất đồng bộ | Trả 200 và lưu trạng thái mới |
| Provider cần xử lý nền, platform chấp nhận async | Trả 202 và operation ID |
| Provider cần xử lý nền, platform không chấp nhận async | Trả lỗi AsyncRequired phù hợp |
| Retry cùng request | Không tạo side effect trùng |
| Hai PATCH đồng thời | Version/lock ngăn ghi đè không nhất quán |
| Provider thành công nhưng broker restart trước khi lưu | Reconciliation phục hồi trạng thái đúng |

Ví dụ unit test cho policy chuyển plan:

~~~java
import static org.assertj.core.api.Assertions.assertThatCode;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;

class PlanTransitionPolicyTest {

    private final PlanTransitionPolicy policy =
            new PlanTransitionPolicy();

    @Test
    void allowsSamePlanWhenPlanUpdatesAreDisabled() {
        assertThatCode(() -> policy.validate(
                false,
                "plan-pg-small",
                "plan-pg-small"))
                .doesNotThrowAnyException();
    }

    @Test
    void rejectsPlanChangeWhenServiceDoesNotSupportIt() {
        assertThatThrownBy(() -> policy.validate(
                false,
                "plan-pg-small",
                "plan-pg-standard"))
                .isInstanceOf(PlanUpdateNotSupportedException.class);
    }

    @Test
    void rejectsUnsupportedTransitionEvenWhenCapabilityIsEnabled() {
        assertThatThrownBy(() -> policy.validate(
                true,
                "plan-pg-enterprise",
                "plan-pg-small"))
                .isInstanceOf(InvalidPlanTransitionException.class);
    }
}
~~~

Đây là ví dụ test cho lớp policy độc lập; implementation thực tế cần inject transition matrix và exception của dự án. Ngoài unit test, nên có HTTP integration test gửi PATCH trực tiếp đến broker, xác minh status code, body, operation polling và việc provider chỉ được gọi khi request hợp lệ.

## 13. Checklist triển khai update an toàn

Trước khi công bố khả năng update cho một service offering, kiểm tra các điểm sau:

- Service definition khai báo plan_updateable đúng với khả năng thật của broker.
- Schema catalog có schema update phù hợp với parameters được hỗ trợ.
- Broker xác minh service_id, instance ID, plan hiện tại và plan đích.
- Policy chuyển plan được định nghĩa rõ theo từng cặp plan.
- Validation parameters, quota, authorization và trạng thái chạy trước side effect.
- Provider API hỗ trợ update hoặc có quy trình migration tương ứng.
- Operation được lưu bền vững và có thể polling sau restart.
- Retry không lặp side effect; request đồng thời được kiểm soát.
- Broker lưu plan/cấu hình mới sau khi provider xác nhận.
- Có reconciliation cho tình huống provider thành công nhưng broker chưa ghi được kết quả.
- Response và log không làm lộ secret.
- Unit test, HTTP integration test và contract test với platform đã được chuẩn bị.

## Kết luận

**PATCH /v2/service_instances/{instance_id}** cho phép platform yêu cầu broker cập nhật cấu hình hoặc plan của một service instance đã tồn tại. Thuộc tính **plan_updateable** trong service definition công bố rằng offering có hỗ trợ thay đổi plan; broker vẫn phải kiểm tra plan nguồn, plan đích, trạng thái instance, quota, quyền và khả năng của provider. Trong Spring Cloud Open Service Broker, hãy đặt nghiệp vụ update trong **ServiceInstanceService**, tách validation và transition policy, lưu operation bền vững, xử lý đồng bộ/bất đồng bộ đúng OSB API và bảo đảm retry an toàn. Khi các điều kiện này được thực hiện nhất quán, platform có thể cung cấp trải nghiệm nâng cấp dịch vụ mà broker vẫn kiểm soát được vòng đời và trạng thái tài nguyên.

## Tài liệu tham khảo

- [Open Service Broker API Specification — Updating a Service Instance](https://github.com/cloudfoundry/servicebroker/blob/master/spec.md) — request PATCH, previous_values, accepts_incomplete, last_operation và catalog capability.
- [Spring Cloud Open Service Broker Reference Documentation](https://docs.spring.io/spring-cloud-open-service-broker/docs/current/reference/) — ServiceInstanceService, request/response model và xử lý operation.
- [Spring Cloud Open Service Broker — ServiceDefinition API](https://docs.spring.io/spring-cloud-open-service-broker/docs/current/apidocs/org/springframework/cloud/servicebroker/model/catalog/ServiceDefinition.html) — mô hình catalog và thuộc tính planUpdateable.
- [Spring Cloud Open Service Broker — UpdateServiceInstanceResponse API](https://docs.spring.io/spring-cloud-open-service-broker/docs/current/apidocs/org/springframework/cloud/servicebroker/model/instance/UpdateServiceInstanceResponse.html) — response cho thao tác update.

