# accepts_incomplete và trường hợp phải báo AsyncRequired

## Bối cảnh

Một service broker theo Open Service Broker API (OSB API) có thể cần nhiều thời gian để cấp phát, cập nhật hoặc thu hồi tài nguyên. Ví dụ, tạo một database cluster có thể mất vài phút; nâng cấp plan có thể cần resize node; thu hồi một instance có thể phải xóa volume, network policy và nhiều tài nguyên phụ thuộc. Nếu broker giữ kết nối HTTP cho tới khi toàn bộ công việc kết thúc, request có thể vượt timeout của Platform, proxy hoặc load balancer.

OSB API định nghĩa cơ chế asynchronous operation để broker có thể nhận request, trả response sớm và tiếp tục xử lý ở background worker. Tuy nhiên, Platform phải chủ động cho biết nó có chấp nhận kiểu xử lý này hay không. Query parameter **accepts_incomplete=true** là tín hiệu đó.

Nếu một thao tác bắt buộc phải xử lý bất đồng bộ nhưng Platform không gửi accepts_incomplete=true, broker phải từ chối request bằng HTTP **422 Unprocessable Entity** với mã lỗi **AsyncRequired**. Quy tắc này bảo vệ hợp đồng giữa hai phía: Platform không bị bất ngờ khi một request tưởng như đã hoàn tất lại tiếp tục chạy nền.

Trong module SPRING_CLOUD_SERVICE_BROKER, đây là một phần quan trọng của quản lý vòng đời service instance, trạng thái operation, retry, idempotency và tích hợp các provider như Cloud Foundry hoặc Kubernetes.

## 1. Ý nghĩa của accepts_incomplete

accepts_incomplete là query parameter trên request OSB API cho biết Platform chấp nhận việc broker trả về trước khi thao tác vòng đời hoàn tất. Giá trị true cho phép broker dùng asynchronous operation nếu cần.

Ví dụ:

~~~http
PUT /v2/service_instances/db-instance-42?accepts_incomplete=true HTTP/1.1
Host: broker.example.internal
X-Broker-API-Version: 2.17
Authorization: Basic <broker-credentials>
Content-Type: application/json

{
  "service_id": "postgres-service",
  "plan_id": "ha-plan",
  "organization_guid": "org-123",
  "space_guid": "space-456"
}
~~~

Platform đang nói với broker rằng nó có thể nhận một response bất đồng bộ và theo dõi tiến trình sau đó. Broker vẫn có quyền hoàn tất đồng bộ nếu thao tác thực tế đủ nhanh.

### Đây là sự chấp thuận, không phải mệnh lệnh

Có ba quy tắc cần phân biệt:

1. **Không có accepts_incomplete=true:** Platform không chấp thuận asynchronous operation cho request đó.
2. **Có accepts_incomplete=true:** Platform cho phép broker trả asynchronous response nếu thao tác cần xử lý nền.
3. **Có accepts_incomplete=true không bắt buộc broker phải xử lý nền:** nếu broker có thể hoàn tất ngay, nó vẫn có thể trả response thành công đồng bộ.

Do đó, query parameter này không phải tùy chọn yêu cầu broker luôn tạo worker, không phải idempotency key và cũng không phải chỉ báo rằng request đã thành công. Nó chỉ biểu thị khả năng tiếp nhận một thao tác chưa hoàn tất tại thời điểm response ban đầu được trả về.

Giá trị bị bỏ qua hoặc false được xem là Platform chưa chấp thuận xử lý bất đồng bộ. Broker không được tự suy đoán rằng Platform luôn hỗ trợ asynchronous operation chỉ vì một request trước đó đã gửi true.

## 2. Những thao tác nào sử dụng accepts_incomplete?

Trong OSB API, cơ chế asynchronous operation chuẩn tập trung vào các thao tác vòng đời service instance:

| Thao tác | HTTP endpoint | Khả năng asynchronous |
|---|---|---|
| Provision | PUT /v2/service_instances/{instance_id} | Có |
| Update | PATCH /v2/service_instances/{instance_id} | Có |
| Deprovision | DELETE /v2/service_instances/{instance_id} | Có |
| Đọc trạng thái operation | GET /v2/service_instances/{instance_id}/last_operation | Dùng để polling, không phải thao tác khởi tạo async |
| Đọc catalog | GET /v2/catalog | Request đọc, không dùng accepts_incomplete |
| Create binding / delete binding | Endpoint service_bindings tương ứng | Không mặc nhiên áp dụng cơ chế async instance operation chuẩn |

Với binding hoặc extension riêng của Platform, cần kiểm tra đúng phiên bản hợp đồng đang tích hợp. Không thêm accepts_incomplete vào mọi endpoint một cách máy móc. Broker và Platform phải cùng hiểu endpoint nào hỗ trợ asynchronous operation.

Ví dụ provision:

~~~http
PUT /v2/service_instances/db-instance-42?accepts_incomplete=true
~~~

Ví dụ update:

~~~http
PATCH /v2/service_instances/db-instance-42?accepts_incomplete=true
~~~

Ví dụ deprovision:

~~~http
DELETE /v2/service_instances/db-instance-42?accepts_incomplete=true
~~~

Nếu request tới endpoint không hỗ trợ query parameter này, broker không nên tự mở rộng semantics. Hãy giữ đúng contract OSB API mà broker công bố.

## 3. Quyết định đồng bộ hay bất đồng bộ

Broker nên quyết định dựa trên khả năng thực tế của thao tác, không dựa riêng vào việc query parameter có xuất hiện hay không.

| Điều kiện | Hành vi phù hợp |
|---|---|
| Thao tác hoàn tất được trong request hiện tại | Xử lý đồng bộ và trả response thành công |
| Thao tác cần background processing, Platform gửi accepts_incomplete=true | Tạo operation, trả 202 Accepted và xử lý tiếp |
| Thao tác cần background processing, Platform không gửi true | Trả 422 Unprocessable Entity với error AsyncRequired |
| Request sai dữ liệu hoặc không được phép | Trả lỗi tương ứng như 400, 401, 403 hoặc lỗi OSB API phù hợp |

Điều quan trọng là broker không nên trả 202 khi Platform chưa chấp thuận. Cũng không nên trả 422 AsyncRequired nếu thao tác có thể hoàn tất đồng bộ và broker đã chọn hoàn tất ngay.

### Sơ đồ quyết định

~~~mermaid
flowchart TD
    A[Nhận request vòng đời instance] --> B[Validate request và API version]
    B --> C[Kiểm tra trạng thái, plan và provider capability]
    C --> D{Có thể hoàn tất đồng bộ?}
    D -->|Có| E[Thực hiện và xác minh thao tác]
    E --> F[Trả response thành công]
    D -->|Không| G{accepts_incomplete=true?}
    G -->|Không| H[Trả 422 AsyncRequired]
    G -->|Có| I[Ghi operation và outbox]
    I --> J[Trả 202 Accepted]
    J --> K[Worker tiếp tục xử lý]
    K --> L[Platform polling last_operation]
~~~

### Không bắt đầu side effect trước khi trả AsyncRequired

Nếu broker biết ngay thao tác cần xử lý nền nhưng Platform chưa chấp thuận, broker nên trả AsyncRequired trước khi tạo tài nguyên, ghi operation đang chạy hoặc gửi lệnh không thể thu hồi tới provider.

Ví dụ, không nên tạo database cluster rồi mới phát hiện request thiếu accepts_incomplete=true và trả 422. Khi đó Platform có thể gửi lại request theo cách khác trong khi cluster đầu tiên vẫn tồn tại, gây trùng tài nguyên và sai trạng thái.

Nếu chỉ có thể xác định thời gian xử lý sau khi gọi provider, broker cần thiết kế giai đoạn preflight hoặc thao tác có thể hủy. Không được để một request bị từ chối nhưng vẫn âm thầm tiếp tục chạy background. Các bước chuẩn bị có side effect phải có cơ chế cleanup/compensation rõ ràng.

## 4. Trường hợp phải trả 422 AsyncRequired

Broker trả lỗi này khi đồng thời thỏa mãn hai điều kiện:

- Thao tác không thể hoặc không nên hoàn tất trong request HTTP hiện tại theo giới hạn thời gian và khả năng provider.
- Platform không khai báo accepts_incomplete=true.

HTTP status là 422 Unprocessable Entity. Error code trong JSON body là AsyncRequired. Description nên giải thích rằng thao tác cần xử lý bất đồng bộ và Platform cần gửi lại request với accepts_incomplete=true nếu nó hỗ trợ.

Ví dụ:

~~~http
HTTP/1.1 422 Unprocessable Entity
Content-Type: application/json

{
  "error": "AsyncRequired",
  "description": "Provisioning this service requires asynchronous processing. Retry with accepts_incomplete=true if the Platform supports incomplete operations."
}
~~~

AsyncRequired là mã lỗi giao thức, không phải tên trạng thái operation. Nó cũng không có nghĩa provider đã bắt đầu provision. Request bị từ chối ở bước này chưa được chấp nhận để chạy nền.

### Phân biệt với các lỗi khác

| Tình huống | HTTP status thường dùng | Error code/ý nghĩa |
|---|---|---|
| Request thiếu trường bắt buộc hoặc sai định dạng | 400 Bad Request | Dữ liệu request không hợp lệ |
| Caller chưa xác thực | 401 Unauthorized | Thiếu hoặc sai credential |
| Caller không có quyền | 403 Forbidden | Không được phép thực hiện |
| Instance ID đã tồn tại với cấu hình xung đột | 409 Conflict | Trạng thái hiện tại xung đột |
| Thao tác cần async nhưng Platform chưa chấp thuận | 422 Unprocessable Entity | AsyncRequired |
| Provider gặp lỗi ngoài dự kiến | 5xx hoặc lỗi phù hợp | Lỗi thực thi, không phải AsyncRequired |

Không dùng 202 Accepted thay cho 422 khi Platform chưa chấp thuận asynchronous operation. Không dùng 500 để báo một điều kiện giao thức mà Platform có thể khắc phục bằng cách gửi lại request đúng query parameter.

## 5. Platform xử lý AsyncRequired như thế nào?

Khi nhận 422 với error AsyncRequired, Platform biết broker cần xử lý bất đồng bộ để hoàn tất thao tác. Nếu Platform hỗ trợ incomplete operations, nó có thể gửi lại request với accepts_incomplete=true.

Luồng retry:

~~~mermaid
sequenceDiagram
    participant P as Platform
    participant B as Service Broker
    participant W as Worker

    P->>B: PUT /service_instances/id (không accepts_incomplete)
    B->>B: Xác định provision cần xử lý nền
    B-->>P: 422 AsyncRequired
    Note over P: Platform kiểm tra khả năng hỗ trợ async
    P->>B: PUT /service_instances/id?accepts_incomplete=true
    B->>B: Validate và ghi operation
    B-->>P: 202 Accepted + operation
    B->>W: Gửi công việc provision
    W->>B: Cập nhật trạng thái
    P->>B: GET /last_operation
    B-->>P: in progress hoặc succeeded/failed
~~~

Platform không nên tự động thêm accepts_incomplete=true trong mọi tình huống mà không kiểm tra khả năng của chính nó. Query parameter thể hiện sự chấp thuận của Platform; broker không được tự thay đổi quyết định đó.

Nếu Platform không hỗ trợ async hoặc không thể theo dõi operation, nó không thể hoàn tất thao tác cần xử lý nền theo luồng này. Khi đó cần thay đổi lựa chọn plan, tham số hoặc chính sách vận hành để thao tác có thể hoàn tất đồng bộ, hoặc nâng cấp Platform để hỗ trợ incomplete operations.

## 6. Response 202 và operation

Khi request có accepts_incomplete=true và broker quyết định xử lý nền, broker ghi nhận công việc bền vững rồi trả 202 Accepted. Response có thể chứa operation key để phân biệt lần thực thi và hỗ trợ polling.

Ví dụ:

~~~http
HTTP/1.1 202 Accepted
Content-Type: application/json

{
  "operation": "provision-7f31a9"
}
~~~

Operation key là định danh opaque do broker quản lý. Nó không nên chứa thông tin nhạy cảm hoặc để lộ cấu trúc nội bộ. Nếu broker cần phân biệt nhiều operation trên cùng instance, key cần duy nhất trong phạm vi tra cứu và được lưu bền vững.

### Polling last_operation

Sau response 202, Platform gọi endpoint last_operation để lấy trạng thái:

~~~http
GET /v2/service_instances/db-instance-42/last_operation?operation=provision-7f31a9 HTTP/1.1
X-Broker-API-Version: 2.17
Authorization: Basic <broker-credentials>
~~~

Ví dụ response khi đang xử lý:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "state": "in progress",
  "description": "Creating the database cluster"
}
~~~

Ví dụ response khi hoàn tất:

~~~json
{
  "state": "succeeded",
  "description": "Database cluster is ready"
}
~~~

Hoặc khi thất bại:

~~~json
{
  "state": "failed",
  "description": "The provider could not allocate the requested storage"
}
~~~

Broker cần trả trạng thái dựa trên operation đã lưu, không dựa vào biến trong bộ nhớ của một replica. Platform có thể gửi polling tới bất kỳ replica broker nào; do đó trạng thái phải được chia sẻ qua database hoặc kho lưu trữ bền vững.

Nếu broker trả operation key trong response ban đầu, broker cần hỗ trợ tra cứu operation tương ứng theo contract. Nếu không trả key, broker phải bảo đảm quy tắc tra cứu last_operation không mơ hồ cho instance đó. Khi có nhiều operation hoặc retry, operation key giúp tránh nhầm kết quả của lần chạy trước với lần hiện tại.

## 7. Thiết kế state và lưu trữ operation

Một operation bất đồng bộ cần có trạng thái rõ ràng, thời điểm tạo, loại thao tác và liên kết tới instance.

Ví dụ mô hình dữ liệu:

~~~text
ServiceOperation
  operationId
  platformId
  instanceId
  operationType
  requestFingerprint
  state
  phase
  description
  createdAt
  updatedAt
  completedAt
  retryCount
  providerRequestId
  errorCode

ServiceInstance
  platformId
  instanceId
  serviceId
  planId
  lifecycleState
  currentOperationId
  providerResourceId
~~~

Một state machine tối thiểu:

| Trạng thái | Ý nghĩa |
|---|---|
| ACCEPTED | Broker đã chấp nhận request và ghi operation |
| IN_PROGRESS | Worker đang thực hiện |
| SUCCEEDED | Thao tác đã hoàn tất và được xác minh |
| FAILED | Thao tác thất bại, không thể tiếp tục tự động |
| COMPENSATING | Broker đang chạy bước bù/cleanup sau lỗi |

Tên trạng thái nội bộ có thể khác các giá trị OSB API trả về. Broker cần ánh xạ trạng thái nội bộ thành state trong last_operation theo hợp đồng, ví dụ in progress, succeeded hoặc failed.

### Transactional outbox

Đối với xử lý nền, broker nên ghi bản ghi operation và outbox event trong cùng transaction database:

1. Kiểm tra instance và điều kiện chấp nhận request.
2. Tạo operation ở trạng thái ACCEPTED.
3. Cập nhật instance sang PROVISIONING, UPDATING hoặc DEPROVISIONING.
4. Ghi outbox event chứa operation ID.
5. Commit transaction.
6. Publisher chuyển event sang queue.
7. Worker nhận event và thực hiện thao tác provider.

Thiết kế này tránh trường hợp database đã ghi operation nhưng lệnh vào queue bị mất. Publisher có thể gửi lặp; worker phải idempotent để một event được xử lý nhiều lần vẫn không tạo side effect trùng.

## 8. Idempotency khi Platform gửi lại request

Một request có thể được gửi lại do Platform nhận timeout hoặc không nhận được response 202. Broker phải xác định request mới là retry của operation đã tồn tại hay là một yêu cầu khác.

Fingerprint có thể dựa trên:

- Platform ID và instance ID.
- Loại thao tác: provision, update hoặc deprovision.
- Service ID, plan ID và parameters đã chuẩn hóa.
- Previous values hoặc version nguồn có ý nghĩa.
- Các thuộc tính request ảnh hưởng tới kết quả.

Quy tắc xử lý:

- Nếu cùng fingerprint và operation đang chạy, trả lại thông tin operation hiện có.
- Nếu cùng fingerprint và operation đã thành công, trả kết quả idempotent theo hợp đồng.
- Nếu cùng instance nhưng request có ý định khác khi operation đang chạy, trả lỗi conflict hoặc operation-in-progress phù hợp.
- Nếu request trước đã bị từ chối bằng AsyncRequired, không có operation đang chạy; request retry với accepts_incomplete=true có thể tạo operation mới.
- Nếu provider đã thực hiện side effect nhưng broker chưa lưu kết quả, reconcile provider state trước khi gọi lại.

Không dùng accepts_incomplete làm idempotency key. Query parameter chỉ biểu thị Platform chấp nhận xử lý nền; nó không nhận diện một request duy nhất.

## 9. Tích hợp trong Spring Cloud Open Service Broker

Spring Cloud Open Service Broker cung cấp request model và response model cho các thao tác service instance. Ứng dụng có thể đọc thông tin accepts-incomplete từ request object tương ứng, quyết định hoàn tất đồng bộ hay tạo asynchronous operation, sau đó trả response model cho framework ánh xạ sang HTTP.

Tên accessor và kiểu response có thể thay đổi theo phiên bản dependency. Hãy dùng API của phiên bản đang cài đặt; ví dụ dưới đây mô tả ý tưởng xử lý.

~~~java
CreateServiceInstanceResponse createServiceInstance(
        CreateServiceInstanceRequest request) {

    var command = provisionCommandFactory.from(request);
    var decision = provisioningPolicy.evaluate(command);

    if (decision.requiresAsync() && !request.isAcceptsIncomplete()) {
        throw new AsyncRequiredException(
                "Provisioning requires accepts_incomplete=true");
    }

    if (!decision.requiresAsync()) {
        var result = provisioningService.provisionSynchronously(command);
        return CreateServiceInstanceResponse.builder()
                .dashboardUrl(result.dashboardUrl())
                .build();
    }

    var operation = operationService.acceptProvision(command);
    return CreateServiceInstanceResponse.builder()
            .async(true)
            .operation(operation.id())
            .build();
}
~~~

Đây là mã mô hình hóa, không khẳng định AsyncRequiredException là tên class có sẵn trong mọi phiên bản. Nếu framework cung cấp exception chuyên biệt cho AsyncRequired, hãy dùng exception đó để framework ánh xạ đúng HTTP 422 và error code. Nếu không, cấu hình exception handler theo contract OSB API.

### Áp dụng cho update và deprovision

Nguyên tắc tương tự được áp dụng cho update và deprovision:

~~~java
if (updateRequiresAsync(command) && !request.isAcceptsIncomplete()) {
    throw asyncRequired();
}

if (updateRequiresAsync(command)) {
    var operation = updateService.accept(command);
    return UpdateServiceInstanceResponse.builder()
            .async(true)
            .operation(operation.id())
            .build();
}

return updateServiceInstanceSynchronously(command);
~~~

~~~java
if (deprovisionRequiresAsync(command) && !request.isAcceptsIncomplete()) {
    throw asyncRequired();
}

if (deprovisionRequiresAsync(command)) {
    var operation = deprovisionService.accept(command);
    return DeleteServiceInstanceResponse.builder()
            .async(true)
            .operation(operation.id())
            .build();
}

return deprovisionSynchronously(command);
~~~

Tên response builder và method cần được đối chiếu với đúng phiên bản Spring Cloud Open Service Broker. Điểm kiến trúc không thay đổi: kiểm tra chấp thuận trước khi tạo operation, lưu trạng thái bền vững, rồi mới trả async response.

### Tách policy khỏi provider adapter

ProvisioningPolicy hoặc UpdatePolicy quyết định một yêu cầu có thể hoàn tất đồng bộ hay cần background processing. Provider adapter cung cấp thông tin capability và thực thi lệnh, nhưng không nên tự ý bỏ qua chấp thuận của Platform.

Ví dụ:

| Lớp | Trách nhiệm |
|---|---|
| OSB service implementation | Đọc request và accepts_incomplete |
| Operation policy | Xác định thao tác có cần async không |
| Application service | Tạo operation và điều phối lifecycle |
| Repository/outbox | Lưu operation và công việc bền vững |
| Worker | Thực hiện thao tác nền |
| Provider adapter | Gọi Cloud API hoặc Kubernetes API |
| Last operation service | Trả trạng thái cho Platform polling |

## 10. Xử lý lỗi và giới hạn vận hành

Broker cần phân biệt lỗi trước khi chấp nhận operation với lỗi xảy ra trong khi operation đang chạy.

| Thời điểm | Ví dụ | Cách phản hồi |
|---|---|---|
| Trước khi nhận request | Thiếu header, sai JSON, không có quyền | HTTP 4xx tương ứng |
| Trước khi thực hiện async | Cần async nhưng Platform chưa chấp thuận | 422 AsyncRequired |
| Sau khi trả 202 | Provider timeout hoặc quota thay đổi | Cập nhật operation thành failed hoặc retry theo policy |
| Trong cleanup/compensation | Xóa tài nguyên phụ thất bại | Giữ trạng thái cần reconcile và cảnh báo operator |

Sau khi đã trả 202, không thể thay response ban đầu bằng lỗi HTTP mới. Broker phải ghi lỗi vào operation và để Platform nhận kết quả qua last_operation. Description nên hữu ích nhưng không chứa stack trace, credential, SQL hoặc chi tiết hạ tầng nhạy cảm.

Worker cần timeout, retry có giới hạn, backoff, circuit breaker và dead-letter handling phù hợp. Không retry vô hạn một lỗi cấu hình hoặc lỗi quyền. Khi retry, phải kiểm tra operation còn hiệu lực và instance chưa bị thao tác khác thay thế.

## 11. Kiểm thử accepts_incomplete và AsyncRequired

Các test quan trọng phải xác nhận cả HTTP response lẫn việc broker có tạo side effect hay không.

| Trường hợp | Kết quả mong đợi |
|---|---|
| Không gửi accepts_incomplete, thao tác hoàn tất đồng bộ được | Trả response thành công đồng bộ |
| Không gửi accepts_incomplete, thao tác bắt buộc async | 422 với error AsyncRequired |
| Gửi accepts_incomplete=true, thao tác hoàn tất đồng bộ được | Có thể trả response thành công đồng bộ |
| Gửi accepts_incomplete=true, thao tác cần async | 202 và operation reference |
| Gửi accepts_incomplete=false, thao tác cần async | 422 AsyncRequired |
| Query parameter sai định dạng | Request bị từ chối như request không hợp lệ |
| Retry sau AsyncRequired với true | Tạo một operation hợp lệ, không có side effect từ lần bị từ chối |
| Retry cùng request sau 202 | Không tạo operation hoặc tài nguyên trùng |
| Polling operation | Trả đúng in progress/succeeded/failed |
| Worker lỗi sau 202 | Lưu trạng thái failed và description đã chuẩn hóa |
| Broker restart | Worker có thể tiếp tục từ operation/checkpoint đã lưu |
| Hai request đồng thời | Không tạo hai operation xung đột cho cùng instance |

### Kiểm tra không có side effect khi trả AsyncRequired

Đây là test đặc biệt quan trọng:

1. Gửi request provision không có accepts_incomplete=true.
2. Mock policy/provider cho biết thao tác cần async.
3. Xác nhận response là 422 và error là AsyncRequired.
4. Xác nhận operation repository không có operation được chấp nhận.
5. Xác nhận outbox không có event provision.
6. Xác nhận provider adapter chưa tạo tài nguyên.

Test này ngăn lỗi phổ biến: broker trả AsyncRequired nhưng worker vẫn chạy do event đã được gửi trước đó.

## 12. Các lỗi triển khai thường gặp

### Coi accepts_incomplete=true là bắt buộc phải async

Query parameter cho phép asynchronous operation, không yêu cầu broker luôn dùng worker. Nếu thao tác hoàn tất nhanh, response đồng bộ vẫn hợp lệ.

### Bắt đầu provision rồi mới trả AsyncRequired

Điều này tạo side effect dù request đã bị từ chối. Hãy đánh giá khả năng xử lý trước khi tạo operation hoặc gọi provider.

### Trả 202 khi query parameter không có

Platform có thể không polling và không biết công việc vẫn chạy. Khi async bắt buộc nhưng chưa được chấp thuận, trả 422 AsyncRequired.

### Chỉ lưu operation trong memory

Broker có nhiều replica hoặc có thể restart. Operation phải được lưu bền vững để last_operation hoạt động nhất quán.

### Dùng AsyncRequired cho mọi lỗi xử lý chậm

Chỉ dùng error này khi thao tác thực sự cần asynchronous operation và Platform chưa chấp thuận. Provider lỗi, quota hết hoặc request sai phải được phân loại theo nguyên nhân thực tế.

### Nhầm reactive với asynchronous operation của OSB

Mono hoặc CompletableFuture có thể giúp HTTP request không chặn thread, nhưng nếu response chỉ được trả sau khi tác vụ hoàn tất thì đó vẫn là xử lý đồng bộ theo hợp đồng OSB. Async operation yêu cầu response ban đầu kết thúc trong khi công việc vẫn tiếp tục và có thể được truy vấn.

## 13. Checklist triển khai

- [ ] Xác định các endpoint vòng đời instance hỗ trợ asynchronous operation.
- [ ] Đọc accepts_incomplete từ request model của đúng phiên bản framework.
- [ ] Xem thiếu hoặc false là Platform chưa chấp thuận async.
- [ ] Hoàn tất đồng bộ nếu có thể và trả response thành công bình thường.
- [ ] Nếu cần async mà chưa được chấp thuận, trả 422 với error AsyncRequired.
- [ ] Không tạo tài nguyên, operation hoặc queue event trước khi trả AsyncRequired.
- [ ] Nếu Platform chấp thuận async, lưu operation và outbox trước khi trả 202.
- [ ] Cung cấp operation reference và endpoint last_operation nhất quán.
- [ ] Lưu trạng thái operation bền vững, hỗ trợ polling qua nhiều replica.
- [ ] Retry và worker delivery phải idempotent.
- [ ] Chuẩn hóa lỗi sau 202 thành trạng thái operation failed.
- [ ] Có test xác nhận AsyncRequired không gây side effect.
- [ ] Không nhầm reactive execution với OSB asynchronous operation.

## Kết luận

accepts_incomplete=true là cách Platform cho broker biết rằng nó chấp nhận thao tác vòng đời service instance tiếp tục chạy sau response HTTP ban đầu. Broker nên xử lý đồng bộ khi có thể; khi thao tác bắt buộc chạy nền mà Platform chưa chấp thuận, broker phải trả 422 Unprocessable Entity với error AsyncRequired và không để lại side effect. Khi Platform gửi lại request với accepts_incomplete=true, broker có thể tạo operation bền vững, trả 202 Accepted và cung cấp trạng thái qua last_operation. Tôn trọng ranh giới chấp thuận này giúp service broker tránh công việc chạy ngầm ngoài dự kiến, đồng thời giữ retry, idempotency và trạng thái giữa Platform, Spring Cloud và provider nhất quán.
