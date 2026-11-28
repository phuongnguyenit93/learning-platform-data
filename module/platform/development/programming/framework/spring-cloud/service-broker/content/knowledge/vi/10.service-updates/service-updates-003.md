# Phân biệt đổi gói dịch vụ, đổi tham số và cập nhật context

Trong module **SPRING_CLOUD_SERVICE_BROKER**, service broker nhận yêu cầu cập nhật service instance theo Open Service Broker API (OSB API). Một request update có thể liên quan đến ba loại dữ liệu khác nhau: gói dịch vụ được chọn, các tham số cấu hình riêng của broker và context do platform cung cấp. Ba loại dữ liệu này có mục đích, quyền sở hữu và tác động vận hành khác nhau.

Đổi plan có thể làm thay đổi cấp dịch vụ, quota, chi phí hoặc loại tài nguyên. Đổi parameters có thể điều chỉnh cấu hình như dung lượng, backup hay giới hạn kết nối mà không nhất thiết đổi plan. Context mô tả môi trường hoặc phạm vi platform gắn với instance, chẳng hạn organization, space, cluster hoặc namespace. Nếu gộp cả ba vào một khối cấu hình duy nhất, broker dễ cập nhật nhầm dữ liệu sở hữu, áp dụng sai migration hoặc làm mất metadata cần thiết để xử lý các request sau.

Bài học này tập trung vào cách đọc request update, xác định chính xác phần nào thay đổi, kiểm tra khả năng của plan và platform, sau đó triển khai quy trình cập nhật có kiểm soát trong Spring Cloud Service Broker.

## 1. Ba loại thay đổi có ý nghĩa khác nhau

Trước khi xử lý endpoint update, cần phân loại dữ liệu:

| Loại thay đổi | Dữ liệu đại diện | Ai quyết định | Tác động thường gặp |
|---|---|---|---|
| Đổi service plan | **plan_id** | Người dùng hoặc platform chọn plan đích | Thay cấp dịch vụ, quota, tính năng, chi phí hoặc cấu hình tài nguyên |
| Đổi tham số | **parameters** | Người dùng hoặc client gửi cấu hình theo schema của broker | Thay đổi thuộc tính của instance như dung lượng, backup, retention hoặc giới hạn kết nối |
| Cập nhật context | **context** | Platform cung cấp theo môi trường tích hợp | Bổ sung hoặc làm mới metadata về tenant, organization, space, cluster, namespace hoặc môi trường |

Một request có thể chỉ thay đổi một loại dữ liệu hoặc kết hợp nhiều loại. Ví dụ, người dùng chuyển từ plan nhỏ sang plan tiêu chuẩn đồng thời tăng dung lượng và bật backup. Một platform cũng có thể gửi context hiện tại trong request update dù người dùng không thay đổi cấu hình dịch vụ.

Không nên suy luận rằng cứ có request update là plan đã thay đổi. Cũng không nên coi context là một tập parameters do người dùng tự do sửa. Broker cần phân loại thay đổi dựa trên dữ liệu hiện tại đã lưu, dữ liệu request và quy tắc OSB API.

## 2. Update service instance trong OSB API

Endpoint cập nhật service instance là:

~~~http
PATCH /v2/service_instances/{instance_id}
X-Broker-API-Version: 2.17
Content-Type: application/json
~~~

Nếu broker cần thực hiện thao tác bất đồng bộ, platform có thể gửi query parameter **accepts_incomplete=true** để cho biết nó chấp nhận workflow bất đồng bộ:

~~~http
PATCH /v2/service_instances/instance-7f3a?accepts_incomplete=true
~~~

Request update thường có các trường:

| Trường | Ý nghĩa | Cách sử dụng |
|---|---|---|
| **service_id** | ID của service offering | Xác định offering của instance; phải nhất quán với instance đã tồn tại |
| **plan_id** | ID của plan đích | Gửi khi yêu cầu chuyển plan; broker kiểm tra khả năng update |
| **parameters** | Tham số cấu hình | Validate theo schema update của plan và quy tắc nghiệp vụ |
| **context** | Context platform | Cung cấp ngữ cảnh tích hợp liên quan đến thao tác update |
| **previous_values** | Một số giá trị trước cập nhật | Giúp broker biết trạng thái cũ mà platform cung cấp, nhất là khi cần xử lý chuyển plan |

Các trường tùy chọn và điều kiện bắt buộc cụ thể cần được đối chiếu với phiên bản OSB API mà broker hỗ trợ. Trong xử lý nghiệp vụ, broker nên phân biệt rõ trường không xuất hiện, trường xuất hiện với object rỗng và trường xuất hiện với giá trị mới.

Ví dụ request kết hợp đổi plan và parameters:

~~~json
{
  "service_id": "service-postgresql",
  "plan_id": "plan-standard",
  "parameters": {
    "storage_gb": 100,
    "backup_enabled": true
  },
  "context": {
    "platform": "kubernetes",
    "cluster": "prod-cluster",
    "namespace": "payments"
  },
  "previous_values": {
    "service_id": "service-postgresql",
    "plan_id": "plan-small"
  }
}
~~~

Ví dụ chỉ đổi parameters, giữ nguyên plan:

~~~json
{
  "service_id": "service-postgresql",
  "parameters": {
    "backup_enabled": false,
    "connection_limit": 40
  }
}
~~~

Trong ví dụ thứ hai, không có plan ID đích mới. Broker cần giữ plan hiện tại và xác định schema update tương ứng với plan đó. Không được tự chọn một plan mặc định chỉ vì request không gửi plan ID.

## 3. Đổi service plan: thay đổi cấp dịch vụ

Service plan mô tả một cấp hoặc cấu hình dịch vụ được công bố trong catalog. Hai plan có thể khác nhau về CPU, RAM, dung lượng lưu trữ, số kết nối, backup, SLA, vùng triển khai hoặc mức giá.

Ví dụ:

| Thuộc tính | Plan small | Plan standard |
|---|---:|---:|
| vCPU | 1 | 2 |
| RAM | 2 GB | 8 GB |
| Storage ban đầu | 20 GB | 100 GB |
| Kết nối tối đa | 50 | 200 |
| Backup tự động | Tùy chọn | Có |
| Phạm vi hỗ trợ | Development | Production |

Khi người dùng chọn plan standard cho instance đang chạy plan small, platform gửi plan ID của plan đích. Broker phải kiểm tra service offering có công bố khả năng cập nhật plan hay không.

### 3.1. plan_updateable là capability về đổi plan

Trong catalog, service có thể công bố:

~~~json
{
  "id": "service-postgresql",
  "name": "postgresql",
  "bindable": true,
  "plan_updateable": true,
  "plans": [
    {
      "id": "plan-small",
      "name": "small"
    },
    {
      "id": "plan-standard",
      "name": "standard"
    }
  ]
}
~~~

**plan_updateable: true** thể hiện broker hỗ trợ thay đổi plan cho service offering theo quy tắc OSB API. Chỉ khai báo capability này khi broker thực sự có thể thực hiện và quản lý chuyển đổi plan.

Cần phân biệt hai việc:

- **Đổi parameters:** thay đổi cấu hình theo schema của instance; không nhất thiết chuyển plan.
- **Đổi plan:** chuyển instance từ plan hiện tại sang plan khác; cần hỗ trợ plan update theo capability đã công bố.

Một broker có thể hỗ trợ cập nhật parameters nhưng không hỗ trợ chuyển plan. Trong trường hợp đó, broker không nên công bố **plan_updateable: true** chỉ vì endpoint update đã tồn tại. Ngược lại, nếu công bố capability plan update, broker phải xử lý đúng yêu cầu chuyển plan và các lỗi tương ứng.

### 3.2. Kiểm tra khả năng chuyển đổi

Không phải mọi cặp plan đều có thể chuyển đổi. Broker nên duy trì ma trận tương thích hoặc policy theo offering:

| Plan hiện tại | Plan đích | Quyết định minh họa | Lý do |
|---|---|---|---|
| small | standard | Cho phép | Có thể tăng tài nguyên tại chỗ |
| standard | enterprise | Cho phép có điều kiện | Cần kiểm tra quota và migration |
| enterprise | small | Từ chối | Không thể giảm dung lượng đang sử dụng |
| plan vùng A | plan vùng B | Từ chối hoặc migration riêng | Thay đổi vị trí dữ liệu có rủi ro cao |

Đây là quy tắc sản phẩm của broker, không phải danh sách chuyển đổi được OSB API định nghĩa sẵn. Broker phải xác định các plan có thể chuyển đổi, điều kiện tiên quyết, thời gian downtime, chi phí và cách phục hồi.

### 3.3. previous_values hỗ trợ nhận diện trạng thái cũ

**previous_values** có thể chứa các giá trị trước cập nhật mà platform biết, chẳng hạn service ID, plan ID và một số định danh context của platform trong các tích hợp tương ứng. Nó giúp broker đối chiếu trạng thái trước và sau khi update.

Không nên coi **previous_values** là kho lưu toàn bộ cấu hình trước đó. Các tham số tùy chỉnh của broker có thể không có mặt ở đây. Nếu cần so sánh parameters cũ với mới, broker phải đọc trạng thái instance đã lưu trong database của mình.

Broker cũng cần kiểm tra giá trị cũ có khớp với bản ghi hiện tại hay không. Nếu platform gửi **previous_values.plan_id** khác plan broker đang lưu, có thể đã xảy ra request đồng thời, trạng thái stale hoặc lỗi đồng bộ. Cần xử lý xung đột có chủ đích thay vì ghi đè im lặng.

## 4. Đổi parameters: thay đổi cấu hình của instance

Parameters là dữ liệu cấu hình riêng do broker định nghĩa. Chúng có thể ảnh hưởng đến tài nguyên thực tế nhưng không nhất thiết thay đổi service plan.

Ví dụ, trong cùng plan standard, người dùng có thể bật/tắt backup, thay đổi connection limit hoặc điều chỉnh thời gian lưu log. Các tham số này được mô tả trong catalog tại schema update của plan.

~~~json
{
  "schemas": {
    "service_instance": {
      "update": {
        "parameters": {
          "type": "object",
          "properties": {
            "storage_gb": {
              "type": "integer",
              "minimum": 100,
              "maximum": 500
            },
            "backup_enabled": {
              "type": "boolean"
            },
            "connection_limit": {
              "type": "integer",
              "minimum": 10,
              "maximum": 200
            },
            "log_retention_days": {
              "type": "integer",
              "minimum": 1,
              "maximum": 90
            }
          },
          "additionalProperties": false
        }
      }
    }
  }
}
~~~

Schema cho update có thể khác schema cho create. Ví dụ, region được chọn lúc tạo instance nhưng không cho đổi sau khi dữ liệu đã được đặt ở một vùng. Dung lượng có thể chỉ được tăng, không được giảm dưới mức đang sử dụng. Vì vậy, không nên dùng nguyên schema create cho update mà không xem xét vòng đời và khả năng của provider.

### 4.1. Không đồng nhất parameters với plan

Giả sử instance đang dùng plan standard có 100 GB storage. Người dùng yêu cầu tăng lên 150 GB bằng parameters. Nếu plan standard cho phép phạm vi 100 đến 500 GB, broker có thể giữ nguyên plan và cập nhật tham số.

Nếu người dùng yêu cầu chuyển sang plan enterprise, plan ID phải chỉ ra plan đích. Broker kiểm tra khả năng chuyển plan, giới hạn của plan mới và những thay đổi cấu hình đi kèm.

Một bảng phân loại đơn giản:

| Yêu cầu người dùng | Trường request chính | Plan có đổi không? |
|---|---|---|
| Bật backup | **parameters.backup_enabled** | Không |
| Tăng storage trong giới hạn plan | **parameters.storage_gb** | Không |
| Tăng giới hạn kết nối trong cùng plan | **parameters.connection_limit** | Không |
| Chuyển small sang standard | **plan_id** | Có |
| Chuyển plan và bật tính năng backup | **plan_id** và **parameters** | Có |
| Đổi namespace/tenant do platform quản lý | **context** | Không tự suy ra |

### 4.2. Quy tắc merge và giá trị bị bỏ qua

OSB API không tự định nghĩa chính sách merge mọi tham số tùy chỉnh của broker. Broker cần quy định rõ cách diễn giải object **parameters** trong update.

Một chính sách phổ biến là chỉ cập nhật các thuộc tính có mặt trong request và giữ nguyên những thuộc tính không được gửi. Tuy nhiên, nếu broker chọn cách merge này, cần kiểm soát rõ các trường hợp:

- Field bị bỏ qua nghĩa là giữ nguyên.
- Field được gửi với giá trị mới nghĩa là thay đổi.
- Field được gửi với **null** chỉ có ý nghĩa nếu schema và business rule cho phép.
- Object rỗng không được tự động hiểu là xóa toàn bộ cấu hình.
- Giá trị default của schema không tự động ghi đè cấu hình hiện tại khi update.

Ví dụ, request chỉ có **backup_enabled** không nên vô tình reset **storage_gb** về giá trị mặc định. Broker có thể lưu cấu hình đã chuẩn hóa trong instance configuration và áp dụng patch có kiểm soát lên bản ghi hiện tại.

## 5. Cập nhật context: metadata thuộc platform

Context là object do platform cung cấp để mô tả môi trường hoặc phạm vi mà service instance được tạo và quản lý. Nó có thể chứa thông tin như platform, organization, space, cluster, namespace, project hoặc tenant theo mô hình tích hợp.

Context có vai trò khác parameters:

| Tiêu chí | Parameters | Context |
|---|---|---|
| Nguồn | Người dùng/client theo schema broker công bố | Platform theo hợp đồng tích hợp |
| Mục đích | Cấu hình dịch vụ | Mô tả môi trường và phạm vi platform |
| Ví dụ | storage, backup, connection limit | organization, space, cluster, namespace |
| Schema | Có thể công bố JSON Schema trong plan | Cấu trúc platform-specific |
| Quyền sở hữu | Broker định nghĩa và validate | Platform định nghĩa; broker sử dụng theo hợp đồng |
| Tác động | Cấu hình tài nguyên | Tenant scoping, policy, audit hoặc tích hợp |

OSB API xem context là dữ liệu platform-specific. Broker cần tránh giả định mọi platform có cùng cấu trúc context. Cloud Foundry có thể gửi organization/space; một integration trên Kubernetes có thể gửi cluster/namespace hoặc tenant metadata riêng.

### 5.1. Context trong request update không phải parameters

Nếu request update có trường **context**, broker cần biết platform đang cung cấp context cho thao tác này. Context có thể được dùng để định tuyến, kiểm tra phạm vi sở hữu, ghi audit hoặc cấu hình tích hợp phía provider.

Không nên cho phép người dùng sửa context như một cách chuyển quyền sở hữu instance. Ví dụ, thay namespace từ payments sang finance không tự động có nghĩa instance được chuyển tenant. Broker phải kiểm tra danh tính caller và quan hệ sở hữu đã lưu, đồng thời tuân theo semantics của platform adapter.

Nếu request không gửi context, broker cần giữ metadata context đã lưu theo chính sách của mình. Không nên thay context bằng object rỗng hoặc xóa context cũ chỉ vì field bị bỏ qua. Nếu request gửi context mới, broker cần xác định đây là context hiện tại của platform, metadata bổ sung hay thay đổi được phép theo tích hợp. Không tự suy diễn ý nghĩa từ việc một field xuất hiện.

### 5.2. Chuẩn hóa context qua platform adapter

Có thể chuyển context từ nhiều platform về một mô hình nội bộ:

~~~java
public record PlatformContext(
    String platform,
    String tenantId,
    String organizationId,
    String spaceId,
    String clusterId,
    String namespace
) {}
~~~

Đây là mô hình minh họa. Không phải mọi field đều có mặt trên mọi platform. Adapter có thể ánh xạ các field phù hợp và giữ metadata gốc cần thiết theo chính sách lưu trữ.

Ví dụ:

| Nguồn | Context có thể gặp | Mô hình nội bộ |
|---|---|---|
| Cloud Foundry | organization GUID, space GUID | organizationId, spaceId |
| Kubernetes integration | cluster, namespace | clusterId, namespace |
| Platform SaaS | tenant identifier, project | tenantId, project metadata |

Lifecycle coordinator nên dùng mô hình context đã chuẩn hóa cho policy và audit. Nó không nên chứa nhiều nhánh xử lý dựa trực tiếp trên tên field của từng platform.

## 6. Phân tích request update trước khi thay đổi dữ liệu

Một request update có thể chứa plan ID, parameters và context cùng lúc. Broker nên chuyển request thành một bản mô tả thay đổi rõ ràng trước khi gọi provider.

Có thể dùng quy trình:

1. Xác thực platform và kiểm tra header phiên bản OSB API.
2. Tải service instance theo instance ID và xác minh caller có quyền thao tác.
3. Kiểm tra service ID trong request khớp offering của instance.
4. Xác định plan hiện tại và plan đích; chỉ coi là đổi plan khi plan ID đích khác plan đang lưu.
5. Nếu đổi plan, kiểm tra **plan_updateable**, plan đích tồn tại và tương thích.
6. Chọn schema update phù hợp rồi validate parameters.
7. Chuẩn hóa và kiểm tra context theo platform adapter; xác minh tenant/ownership.
8. Tính toán thay đổi thực tế giữa trạng thái hiện tại và trạng thái yêu cầu.
9. Kiểm tra quota, khả năng provider, downtime, migration và chính sách bảo mật.
10. Ghi operation hoặc thực hiện đồng bộ tùy khả năng và thời gian xử lý.

Kết quả phân tích có thể là một command nội bộ:

~~~java
public record ServiceInstanceUpdateCommand(
    String instanceId,
    String currentPlanId,
    String targetPlanId,
    Map<String, Object> parameterChanges,
    PlatformContext platformContext,
    boolean planChanged,
    boolean parametersChanged,
    boolean contextChanged,
    long expectedVersion
) {}
~~~

Các cờ **planChanged**, **parametersChanged** và **contextChanged** là kết quả so sánh trạng thái, không nên lấy trực tiếp từ việc request có chứa field hay không. Ví dụ, platform gửi lại cùng context hiện tại không nhất thiết tạo ra một thay đổi thực tế.

## 7. Quy trình update an toàn cho provider

Sau khi phân tích request, broker cần xác định thứ tự thay đổi tại provider. Đổi plan có thể yêu cầu nâng cấp máy chủ, chuyển storage tier, migration dữ liệu hoặc thay endpoint. Đổi parameters có thể chỉ cần cập nhật cấu hình và reload dịch vụ. Cập nhật context có thể chỉ cần làm mới metadata nội bộ.

Một quy trình điển hình:

~~~mermaid
flowchart TD
    A["Nhận PATCH update"] --> B["Xác thực và tải instance"]
    B --> C["So sánh plan, parameters, context"]
    C --> D["Validate schema và policy"]
    D --> E{"Có thay đổi plan?"}
    E -->|Có| F["Kiểm tra plan_updateable và tương thích"]
    E -->|Không| G["Giữ plan hiện tại"]
    F --> H["Tạo Update Command"]
    G --> H
    H --> I{"Operation kéo dài?"}
    I -->|Không| J["Gọi provider và lưu kết quả"]
    I -->|Có| K["Lưu operation và enqueue worker"]
    K --> L["Worker cập nhật provider"]
    J --> M["Cập nhật trạng thái instance"]
    L --> M
    M --> N["Trả kết quả OSB"]
~~~

Không nên cập nhật **currentPlanId** trong database thành plan mới ngay khi mới nhận request nếu provider chưa hoàn tất migration. Có thể lưu riêng **desiredPlanId** hoặc plan đích trong operation, trong khi **currentPlanId** vẫn phản ánh trạng thái đang có hiệu lực. Khi provider xác nhận hoàn tất, broker mới chuyển trạng thái instance sang plan mới.

Nếu provider thực hiện được một phần rồi thất bại, broker phải ghi nhận bước đã hoàn thành và quyết định retry, compensation hoặc yêu cầu can thiệp. Không nên báo update thành công khi chỉ mới ghi nhận yêu cầu.

## 8. Đồng bộ và bất đồng bộ trong update

Một update nhỏ có thể hoàn tất nhanh, ví dụ đổi một tham số cấu hình có thể áp dụng tức thời. Update plan hoặc migration dữ liệu có thể kéo dài. OSB API cho phép workflow bất đồng bộ khi platform gửi **accepts_incomplete=true** và broker chọn xử lý theo cơ chế đó.

### 8.1. Update đồng bộ

Khi thao tác hoàn tất trong request, broker trả response thành công theo hợp đồng OSB API, thường là **200 OK** cùng nội dung response update phù hợp. Broker chỉ cập nhật trạng thái cuối sau khi provider và metadata nội bộ nhất quán theo cam kết của sản phẩm.

### 8.2. Update bất đồng bộ

Khi platform chấp nhận async, broker có thể trả **202 Accepted** cùng operation identifier. Platform dùng endpoint last operation để poll:

~~~http
GET /v2/service_instances/{instance_id}/last_operation?operation=update-001
~~~

Trạng thái operation có thể được broker quản lý nội bộ như sau:

~~~mermaid
stateDiagram-v2
    [*] --> ACCEPTED
    ACCEPTED --> VALIDATING
    VALIDATING --> IN_PROGRESS
    IN_PROGRESS --> SUCCEEDED
    IN_PROGRESS --> RETRYING
    RETRYING --> IN_PROGRESS
    IN_PROGRESS --> FAILED
    RETRYING --> FAILED
    SUCCEEDED --> [*]
    FAILED --> [*]
~~~

Các trạng thái nội bộ cần được ánh xạ sang các trạng thái OSB mà platform hiểu, chẳng hạn **in progress**, **succeeded** hoặc **failed**. Không để platform nhìn thấy các trạng thái tùy biến nếu chúng không thuộc response contract.

### 8.3. Idempotency và request lặp

Platform có thể gửi lại update khi timeout hoặc không nhận được response. Broker cần nhận diện cùng một thao tác bằng instance ID, loại operation, dữ liệu yêu cầu và operation đang tồn tại.

Một số nguyên tắc:

- Cùng một update request đang chạy không được tạo hai migration song song.
- Retry sau khi provider đã thực hiện xong nhưng broker chưa ghi kết quả phải có cách tra cứu trạng thái provider.
- Request mới có plan đích khác trong khi update trước đang chạy cần bị chặn hoặc xếp hàng theo policy.
- Request update lặp với cùng trạng thái mong muốn nên trả kết quả phù hợp thay vì tạo tác động lặp.
- Dùng optimistic locking hoặc version number để tránh hai request đồng thời ghi đè.

## 9. Lưu trạng thái trước, trong và sau update

Để xử lý crash và retry, broker cần lưu cả trạng thái hiện tại lẫn tiến trình thay đổi.

Một mô hình đơn giản:

| Trường | Mục đích |
|---|---|
| **instance_id** | Định danh instance theo platform |
| **current_plan_id** | Plan đang có hiệu lực |
| **desired_plan_id** | Plan đích của operation đang chạy, nếu có |
| **configuration** | Parameters đã chuẩn hóa và được áp dụng |
| **platform_context** | Context cần thiết cho policy và tích hợp |
| **version** | Phiên bản bản ghi để optimistic locking |
| **operation_id** | Operation update hiện tại hoặc gần nhất |
| **lifecycle_state** | Trạng thái vòng đời của instance |
| **updated_at** | Thời điểm cập nhật gần nhất |

Một bản ghi operation nên lưu loại thay đổi và kết quả:

- Plan cũ và plan đích.
- Những parameters thay đổi đã được làm sạch.
- Context cần thiết để xử lý hoặc audit.
- Trạng thái từng bước provider.
- Số lần retry, lỗi đã chuẩn hóa và correlation ID.
- Thời điểm bắt đầu, hoàn tất hoặc thất bại.

Không lưu secret trong operation payload hoặc log nếu không cần thiết. Nếu provider cần secret để thực hiện migration, hãy tham chiếu đến secret store bằng ID hoặc key an toàn.

## 10. Tình huống thực tế: nâng cấp PostgreSQL từ small lên standard

Một ứng dụng đang sử dụng PostgreSQL plan small với 20 GB storage. Đội vận hành muốn nâng lên plan standard, tăng dung lượng lên 100 GB và bật backup tự động. Platform gửi request update có plan đích, parameters và context hiện tại.

Broker xử lý theo các bước:

1. Tải instance theo instance ID và xác nhận tenant sở hữu.
2. Xác định plan hiện tại là small và plan đích là standard.
3. Kiểm tra service công bố **plan_updateable: true**.
4. Kiểm tra plan standard tồn tại và cho phép chuyển từ small.
5. Validate parameters theo schema update của plan đích hoặc theo quy tắc migration đã định nghĩa.
6. Xác minh quota tenant và khả năng provider tại vùng triển khai.
7. So sánh context với context đã lưu; nếu chỉ là context hiện tại được gửi lại thì không tạo thay đổi sở hữu.
8. Lưu operation với current plan là small và desired plan là standard.
9. Worker gọi provider để tăng tài nguyên và bật backup.
10. Khi provider xác nhận hoàn tất, broker cập nhật current plan, configuration và version.
11. Platform poll last operation đến khi nhận **succeeded**.

Nếu bước tăng storage thành công nhưng bật backup thất bại, broker không nên đánh dấu operation thành công. Nó cần retry bước backup, chạy hành động bù trừ nếu có thể hoặc đánh dấu lỗi kèm trạng thái thực tế để operator xử lý. Trạng thái broker phải phản ánh chính xác những gì provider đã làm.

## 11. Cập nhật context trong tích hợp Cloud Foundry và Kubernetes

### 11.1. Cloud Foundry

Cloud Foundry context có thể chứa organization và space identifiers cùng metadata do platform cung cấp. Khi xử lý update, broker cần giữ liên kết giữa instance và phạm vi platform ban đầu để xác thực caller và audit.

Nếu request mang context mới, broker cần hiểu semantics theo tích hợp Cloud Foundry đang dùng. Không tự coi thay đổi organization hoặc space là yêu cầu chuyển service instance sang tenant khác. Việc chuyển sở hữu nếu sản phẩm hỗ trợ phải là một quy trình riêng với kiểm tra quyền, chính sách dữ liệu và audit.

### 11.2. Kubernetes

Trong một integration Kubernetes, context có thể mang cluster, namespace hoặc tenant identifier. Broker có thể dùng các giá trị đó để định tuyến provider adapter, xác định quota hoặc áp dụng policy.

Nếu namespace thay đổi, broker phải kiểm tra controller hoặc principal gọi request có quyền với cả instance và phạm vi đích theo quy trình được thiết kế. Một trường namespace trong JSON không đủ để chứng minh quyền. Context cũng không nên được sử dụng làm nơi chứa password, token hoặc thông tin xác thực.

### 11.3. Giữ context có thể truy vết

Dù platform khác nhau, broker nên lưu các định danh cần thiết để trả lời:

- Instance được tạo trong tenant hoặc namespace nào?
- Request update do platform nào gửi?
- Caller có quyền trên instance đó không?
- Context nào được dùng khi provision?
- Context trong update có khác context đang lưu không?
- Sự thay đổi có được cho phép và đã được audit chưa?

Việc chuẩn hóa context giúp lifecycle coordinator không phụ thuộc trực tiếp vào cấu trúc của từng platform.

## 12. Ánh xạ update vào Spring Cloud Service Broker

Spring Cloud Open Service Broker cung cấp abstraction để triển khai xử lý update service instance. Tùy phiên bản thư viện, service layer có thể nhận một **UpdateServiceInstanceRequest** và trả về response tương ứng. Request model cung cấp các giá trị như service ID, plan ID, parameters, context và previous values theo hợp đồng của phiên bản đang dùng.

Một kiến trúc rõ ràng nên chia thành:

| Thành phần | Trách nhiệm |
|---|---|
| OSB API adapter | Nhận PATCH request, kiểm tra giao thức và map request |
| Catalog service | Tra cứu service, plan, capability và schema |
| Update application service | Phân loại plan/parameters/context change |
| Context adapter | Chuẩn hóa context theo platform |
| Policy service | Kiểm tra quyền, quota và plan compatibility |
| Operation repository | Lưu operation và trạng thái |
| Provider adapter | Thực hiện thay đổi tại nhà cung cấp |
| Instance repository | Lưu current state và version |

Pseudocode minh họa:

~~~java
public UpdateResult update(UpdateServiceInstanceRequest request) {
    ServiceInstance instance =
        instanceRepository.requireById(request.getServiceInstanceId());

    authorization.requireCanUpdate(request.getContext(), instance);

    if (!instance.getServiceId().equals(request.getServiceDefinitionId())) {
        throw new InvalidServiceForInstanceException();
    }

    UpdateAnalysis analysis = updateAnalyzer.analyze(instance, request);

    if (analysis.planChanged()) {
        catalogPolicy.requirePlanUpdateable(analysis.serviceDefinition());
        planPolicy.requireCompatible(
            instance.getPlanId(),
            analysis.targetPlanId()
        );
    }

    parameterValidator.validateUpdate(
        analysis.targetPlan(),
        analysis.parameterChanges()
    );

    return updateCoordinator.execute(instance, analysis);
}
~~~

Đây là pseudocode về trách nhiệm, không phải chữ ký API cố định của mọi phiên bản thư viện. Tên getter, kiểu response và cơ chế đồng bộ/bất đồng bộ cần đối chiếu dependency thực tế.

Điểm quan trọng là update analyzer phân biệt ba nhóm thay đổi. Update coordinator nhận một kế hoạch đã được xác thực, sau đó chọn xử lý đồng bộ hoặc tạo operation nền. Provider adapter không nên tự quyết định caller có được đổi plan hay context hay không; các quyết định đó thuộc policy và application layer.

## 13. Kiểm thử ma trận thay đổi

Update service instance có nhiều tổ hợp request. Cần kiểm thử riêng từng loại thay đổi và các trường hợp kết hợp.

| Trường hợp | Kết quả mong đợi |
|---|---|
| Không đổi plan, không đổi parameters, context giống nhau | Không tạo thay đổi provider không cần thiết |
| Chỉ đổi parameters hợp lệ | Giữ nguyên plan và áp dụng đúng cấu hình |
| Parameters vượt schema | Từ chối trước khi tạo operation hoặc gọi provider |
| Chỉ đổi plan, capability không hỗ trợ | Từ chối theo hợp đồng OSB |
| Đổi plan tương thích | Thực hiện migration và cập nhật plan sau khi thành công |
| Đổi plan không tương thích | Trả lỗi có mô tả rõ |
| Plan và parameters cùng đổi | Validate theo quy tắc của plan đích và migration |
| Context không được gửi | Giữ context đã lưu theo policy |
| Context được gửi lại không đổi | Không coi là thay đổi quyền sở hữu |
| Context thay đổi tenant/namespace | Kiểm tra authorization và policy riêng |
| Request lặp trong khi operation đang chạy | Không chạy hai update song song |
| Hai update đồng thời | Một request được xử lý hoặc request xung đột bị từ chối có kiểm soát |
| Provider thất bại giữa chừng | Lưu trạng thái thực tế, retry hoặc compensation |
| Provider thành công nhưng broker crash trước khi ghi state | Reconciliation khôi phục trạng thái mà không lặp side effect |

Một số kiểm thử quan trọng cần có:

- **Unit test:** phân loại planChanged, parametersChanged và contextChanged.
- **Schema test:** validate parameters theo đúng plan và operation.
- **Policy test:** plan compatibility, quota, tenant ownership và capability.
- **Contract test:** PATCH request và response theo OSB API.
- **Async test:** 202, operation key, last operation và retry.
- **Concurrency test:** optimistic locking và chống update song song.
- **Recovery test:** crash window giữa provider side effect và database commit.

## 14. Những lỗi thiết kế cần tránh

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Coi mọi update là đổi plan | Từ chối nhầm parameter update hoặc migration sai | So sánh plan ID cũ và plan ID đích |
| Dùng **plan_updateable** để quyết định mọi loại update | Hạn chế nhầm việc đổi parameters | Chỉ áp dụng capability cho đổi plan |
| Dùng schema create cho update | Cho phép field không thể thay đổi hoặc từ chối field hợp lệ | Công bố và validate schema update riêng |
| Coi context là parameters | Người dùng có thể gửi dữ liệu platform sai phạm vi | Xử lý context qua platform adapter và policy |
| Ghi đè context bằng object rỗng khi field bị bỏ qua | Mất metadata sở hữu hoặc audit | Phân biệt absent, empty và populated |
| Tin **previous_values** là trạng thái chuẩn duy nhất | Request stale có thể ghi đè dữ liệu mới | Đối chiếu với state store và version |
| Cập nhật current plan trước khi provider hoàn tất | Database broker báo trạng thái không đúng thực tế | Lưu desired state trong operation, commit current state khi thành công |
| Chạy hai migration song song | Hỏng tài nguyên hoặc mất dữ liệu | Khóa theo instance và optimistic locking |
| Retry không idempotent | Tạo side effect trùng | Dùng operation key và provider reconciliation |
| Không lưu trạng thái từng bước | Khó phục hồi khi provider thất bại giữa chừng | Lưu operation progress và compensation state |

## 15. Checklist trước khi phát hành chức năng update

Trước khi công bố khả năng update của broker, hãy xác nhận:

- [ ] Catalog khai báo **plan_updateable** đúng với khả năng đổi plan thực tế.
- [ ] Broker phân biệt đổi plan, đổi parameters và cập nhật context.
- [ ] service_id của request khớp service offering của instance.
- [ ] Plan đích tồn tại và có quy tắc tương thích với plan hiện tại.
- [ ] Parameters được validate theo schema update của đúng plan.
- [ ] Chính sách absent, empty, null và default được định nghĩa.
- [ ] previous_values được dùng như thông tin đối chiếu, không thay thế state store.
- [ ] Context được chuẩn hóa và kiểm tra theo platform; không cho phép đổi tenant chỉ bằng cách sửa JSON.
- [ ] Quota, provider capacity, downtime và migration được kiểm tra trước side effect.
- [ ] Request update được bảo vệ bằng idempotency và concurrency control.
- [ ] Operation async có trạng thái bền vững và endpoint last operation.
- [ ] Current plan chỉ chuyển sang plan mới khi provider update đạt trạng thái thành công theo cam kết.
- [ ] Lỗi giữa chừng có chiến lược retry, compensation hoặc reconciliation.
- [ ] Log và audit có correlation ID nhưng không chứa secret.
- [ ] Có unit, contract, async, concurrency và recovery tests.

Đổi plan, đổi parameters và cập nhật context đều có thể xuất hiện trong cùng một request update, nhưng mỗi loại phải được xử lý theo đúng ý nghĩa của nó. Khi broker so sánh request với trạng thái đã lưu, kiểm tra capability và schema, xác thực context theo platform, rồi điều phối provider qua operation có thể phục hồi, chức năng update sẽ giữ được tính nhất quán giữa platform, service broker và tài nguyên thực tế.
