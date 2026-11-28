# Cài đặt deleteServiceInstance() và mô hình request/response

Trong Open Service Broker API (OSB API), thao tác **deprovision** yêu cầu broker thu hồi một service instance đã được cấp phát. Nền tảng gửi HTTP **DELETE** đến endpoint **/v2/service_instances/{instance_id}**; Spring Cloud Service Broker chuyển request này thành lời gọi **deleteServiceInstance()** của service xử lý vòng đời. Phương thức phải xác minh đúng instance, kiểm tra service và plan được tham chiếu, thực hiện hoặc khởi chạy quy trình thu hồi tài nguyên, lưu trạng thái và trả response phù hợp với việc xóa đồng bộ hay bất đồng bộ.

Trong module **SPRING_CLOUD_SERVICE_BROKER**, deprovision là thao tác có tác động trực tiếp đến dữ liệu và hạ tầng. Một triển khai đúng cần xử lý request lặp, timeout, instance đang có operation khác, binding còn tồn tại và lỗi backend. Response HTTP chỉ là kết quả giao tiếp với platform; trạng thái bền vững của instance và operation phải được lưu trong broker để có thể truy vấn và phục hồi sau khi process khởi động lại.

## 1. Deprovision và vai trò của deleteServiceInstance()

OSB API tách vòng đời tài nguyên thành các thao tác riêng:

- **Provision:** tạo service instance từ service và plan đã chọn.
- **Bind:** cấp quyền hoặc thông tin kết nối cho một consumer.
- **Unbind:** thu hồi quyền của một binding cụ thể.
- **Deprovision:** thu hồi service instance và tài nguyên mà instance đại diện.

**deleteServiceInstance()** là điểm tích hợp của broker để xử lý yêu cầu deprovision. Nó không đơn thuần xóa một dòng trong database. Phương thức phải điều phối việc thu hồi tài nguyên thật, cập nhật trạng thái, ghi nhận kết quả và tuân thủ hợp đồng request/response của OSB API.

Ví dụ, một instance PostgreSQL có thể đại diện cho một database cùng storage, backup policy, network rule và các đối tượng liên quan. Khi deprovision, broker cần xác định chính xác những tài nguyên thuộc instance đó và thực hiện quy trình thu hồi theo policy. Nếu instance được triển khai qua Kubernetes operator, broker có thể xóa custom resource do operator quản lý và chờ operator thu hồi các thành phần phụ thuộc. Nếu dùng managed database, broker gọi API của nhà cung cấp để xóa database hoặc cluster.

Không nên nhầm deprovision với unbind. Unbind thu hồi quyền của một consumer; deprovision thu hồi chính instance. Nền tảng thường điều phối unbind các binding trước khi deprovision instance. Broker cần có chính sách rõ ràng nếu vẫn còn binding, ví dụ từ chối thao tác theo quy tắc của hệ thống hoặc thực hiện cleanup có kiểm soát khi hợp đồng tích hợp cho phép.

## 2. HTTP request theo OSB API

Endpoint deprovision có dạng:

~~~http
DELETE /v2/service_instances/{instance_id}?service_id={service_id}&plan_id={plan_id}&accepts_incomplete={boolean}
~~~

Ví dụ:

~~~http
DELETE /v2/service_instances/orders-db-prod?service_id=svc-postgresql&plan_id=plan-postgresql-production&accepts_incomplete=true
X-Broker-API-Version: 2.17
Authorization: Bearer <broker-platform-token>
~~~

Request deprovision thường không cần JSON body. Các thông tin quan trọng được truyền qua path và query:

| Thành phần | Ý nghĩa | Cách dùng |
|---|---|---|
| instance_id | Định danh service instance do platform quản lý | Tìm đúng instance trong state store |
| service_id | ID service definition được chọn khi provision | Đối chiếu với service đã lưu |
| plan_id | ID plan đã chọn khi provision | Đối chiếu với plan đã lưu |
| accepts_incomplete | Cho biết platform có chấp nhận xử lý bất đồng bộ hay không | Quyết định có thể trả response accepted cùng operation hay không |
| X-Broker-API-Version | Phiên bản OSB API mà platform sử dụng | Adapter áp dụng contract tương ứng |

**service_id** và **plan_id** giúp broker kiểm tra request đang tham chiếu đúng lựa chọn ban đầu. Không dùng các giá trị này để ghi đè dữ liệu đã lưu. Nếu request gửi plan khác với plan của instance, broker cần phát hiện mismatch và trả lỗi theo contract, không xóa tài nguyên dựa trên thông tin mâu thuẫn.

Header xác thực được kiểm tra ở tầng bảo mật trước khi service xử lý. **instance_id** không phải bí mật và không phải bằng chứng caller có quyền xóa instance.

## 3. Mô hình request trong Spring Cloud Service Broker

Spring Cloud Service Broker cung cấp request model cho thao tác xóa service instance, thường là **DeleteServiceInstanceRequest**. Framework chuyển dữ liệu từ HTTP path/query thành object để lớp nghiệp vụ không cần tự parse URL.

Một request model về mặt nghiệp vụ có thể biểu diễn:

~~~java
public record DeprovisionCommand(
    String instanceId,
    String serviceDefinitionId,
    String planId,
    boolean acceptsIncomplete
) {}
~~~

Các giá trị tương ứng:

- **instanceId:** lấy từ path variable {instance_id}.
- **serviceDefinitionId:** lấy từ query parameter service_id.
- **planId:** lấy từ query parameter plan_id.
- **acceptsIncomplete:** lấy từ query parameter accepts_incomplete.

Tên getter và cách biểu diễn boolean trong **DeleteServiceInstanceRequest** có thể khác theo phiên bản thư viện. Khi triển khai, dùng đúng request type của dependency đang khai báo và chuyển nó sang command nội bộ. Không nên để domain service phụ thuộc vào chi tiết HTTP hoặc phiên bản framework.

Request này không nên được xem là nguồn ownership duy nhất. Broker phải tải instance đã lưu và đối chiếu platform/tenant scope từ principal đã xác thực. Context ban đầu của instance, tenant mapping và backend resource reference được lưu từ lúc provision mới là dữ liệu cần dùng để quyết định tài nguyên nào được phép thu hồi.

## 4. Mô hình response đồng bộ và bất đồng bộ

Kết quả deprovision có hai hình thức chính:

| Hình thức | HTTP response | Ý nghĩa |
|---|---|---|
| Đồng bộ | 200 OK, thường không có response body | Tài nguyên đã được thu hồi thành công |
| Bất đồng bộ | 202 Accepted kèm operation token | Broker đã chấp nhận công việc; platform tiếp tục truy vấn trạng thái |

### Xóa đồng bộ

Nếu backend hoàn tất trong thời gian xử lý request, broker cập nhật instance thành trạng thái đã thu hồi rồi trả response thành công. Không trả operation token nếu không có operation bất đồng bộ cần theo dõi.

Ví dụ response:

~~~http
HTTP/1.1 200 OK
Content-Length: 0
~~~

### Xóa bất đồng bộ

Nếu thao tác có thể kéo dài, broker chỉ được sử dụng luồng bất đồng bộ khi request cho phép bằng **accepts_incomplete=true** và đáp ứng điều kiện của OSB API version đang dùng. Broker ghi operation và trạng thái ban đầu trước khi trả response accepted.

Ví dụ:

~~~http
HTTP/1.1 202 Accepted
Content-Type: application/json
~~~

~~~json
{
  "operation": "deprovision-op-8a21"
}
~~~

Platform dùng operation token để gọi endpoint last operation:

~~~http
GET /v2/service_instances/orders-db-prod/last_operation?service_id=svc-postgresql&plan_id=plan-postgresql-production&operation=deprovision-op-8a21
~~~

Response khi đang chạy có thể có dạng:

~~~json
{
  "state": "in progress",
  "description": "Đang thu hồi tài nguyên database"
}
~~~

Khi hoàn tất:

~~~json
{
  "state": "succeeded",
  "description": "Service instance đã được thu hồi"
}
~~~

Các giá trị trạng thái và response phải theo contract của OSB API version mà broker hỗ trợ. Nếu backend cần xử lý bất đồng bộ nhưng platform không chấp nhận incomplete operation, broker phải trả lỗi phù hợp theo spec thay vì tự ý trả **202 Accepted**.

## 5. Kiểm tra trước khi xóa

Trước khi gọi backend, **deleteServiceInstance()** cần xác minh:

1. Request đã qua xác thực platform.
2. Instance ID tồn tại trong phạm vi platform/tenant của caller.
3. Service ID và plan ID trong request khớp dữ liệu instance đã lưu.
4. Instance không ở trạng thái khiến deprovision không hợp lệ.
5. Không có operation update/provision đang chạy xung đột.
6. Binding còn tồn tại được xử lý theo policy đã định nghĩa.
7. Caller có quyền thu hồi instance.
8. Backend resource reference đã được lưu hoặc có cách đối soát an toàn nếu chưa có.

### Kiểm tra binding

Một instance có thể có nhiều binding đến các consumer. Việc xóa instance khi binding vẫn hoạt động có thể khiến ứng dụng mất kết nối đột ngột. Platform thường thực hiện unbind trước deprovision; broker vẫn nên kiểm tra trạng thái binding trong database để bảo vệ tính toàn vẹn.

Nếu còn binding, broker có thể từ chối deprovision với lỗi phù hợp và yêu cầu platform unbind trước. Một số hệ thống có thể hỗ trợ cascade cleanup, nhưng phải định nghĩa rõ: thu hồi từng credential, xác nhận kết quả unbind, rồi mới xóa instance. Không xóa record binding khỏi database mà bỏ lại user, token hoặc quyền truy cập còn hiệu lực ở backend.

### Kiểm tra operation đang chạy

Không nên chạy deprovision song song với provision hoặc update. Nếu instance đang **PROVISIONING**, backend có thể chưa có resource ID ổn định. Nếu đang **UPDATING**, việc xóa đồng thời có thể khiến worker update tạo lại hoặc thay đổi tài nguyên trong khi deprovision đang thu hồi.

Broker cần khóa instance hoặc dùng optimistic version/operation lease để chỉ có một thao tác vòng đời xung đột được thực thi tại một thời điểm. Khi deprovision đã bắt đầu, các request bind/update mới cần được từ chối hoặc xử lý theo trạng thái đã định nghĩa.

## 6. Luồng xử lý deleteServiceInstance()

Một trình tự tổng quát:

~~~mermaid
flowchart TD
    A["DELETE service_instances/{instance_id}"] --> B["Authenticate platform"]
    B --> C["Load instance by platform scope + instance_id"]
    C --> D["Validate service_id and plan_id"]
    D --> E["Check state, bindings and active operations"]
    E --> F{"Backend delete is immediate?"}
    F -->|Yes| G["Delete backend resource"]
    G --> H["Persist DEPROVISIONED"]
    H --> I["Return 200 OK"]
    F -->|No| J{"accepts_incomplete=true?"}
    J -->|No| K["Return contract-compliant error"]
    J -->|Yes| L["Persist operation + outbox"]
    L --> M["Return 202 + operation token"]
    M --> N["Worker deletes backend resource"]
    N --> O["Persist final state and operation result"]
    O --> P["Platform polls last_operation"]
~~~

Các bước chi tiết:

**Bước 1 — Chuẩn hóa request.** Lấy instance ID, service ID, plan ID và cờ chấp nhận async từ request model. Kiểm tra các trường bắt buộc theo contract.

**Bước 2 — Tải instance và xác minh ownership.** Truy vấn theo platform ID đã xác thực cùng instance ID. Không truy vấn instance toàn cục rồi chỉ so sánh ID ở phía client.

**Bước 3 — Đối chiếu service và plan.** So sánh ID trong request với service/plan đã lưu. Không dùng request để thay đổi quan hệ service/plan.

**Bước 4 — Kiểm tra trạng thái.** Xem instance có đang provision, update, deprovision hoặc đã deprovision hay không. Kiểm tra binding và operation còn hiệu lực.

**Bước 5 — Chọn luồng đồng bộ hoặc bất đồng bộ.** Nếu backend có thể xóa nhanh và chắc chắn, thực hiện đồng bộ. Nếu phải chờ operator, cloud provider hoặc tác vụ dọn dẹp dài, dùng async khi platform cho phép.

**Bước 6 — Lưu trạng thái trước khi thực thi dài.** Đánh dấu instance **DEPROVISIONING**, tạo operation và outbox event trong cùng transaction.

**Bước 7 — Thu hồi tài nguyên backend.** Gọi adapter theo backend resource ID đã lưu, dùng idempotency key ổn định.

**Bước 8 — Cập nhật kết quả.** Chỉ đánh dấu **DEPROVISIONED** khi broker có bằng chứng tài nguyên đã được xóa hoặc không còn tồn tại theo semantics backend.

**Bước 9 — Trả response hoặc cập nhật operation.** Luồng đồng bộ trả 200; luồng async cập nhật operation để platform poll đến khi thành công hoặc thất bại.

## 7. Cài đặt deleteServiceInstance() trong Spring

Trong Spring Cloud Service Broker, service xử lý vòng đời thường triển khai interface **ServiceInstanceService**. Ở các phiên bản reactive, method có dạng trả về **Mono<DeleteServiceInstanceResponse>**. Tên interface, request getter và response builder cần đối chiếu với version dependency của dự án; ví dụ sau tập trung vào cấu trúc xử lý.

~~~java
@Service
public class BrokerServiceInstanceService
        implements ServiceInstanceService {

    private final DeprovisioningService deprovisioningService;

    public BrokerServiceInstanceService(
            DeprovisioningService deprovisioningService) {
        this.deprovisioningService = deprovisioningService;
    }

    @Override
    public Mono<DeleteServiceInstanceResponse> deleteServiceInstance(
            DeleteServiceInstanceRequest request) {

        DeprovisionCommand command = new DeprovisionCommand(
            request.getServiceInstanceId(),
            request.getServiceDefinitionId(),
            request.getPlanId(),
            request.isAsyncAccepted()
        );

        return deprovisioningService.deprovision(command)
            .map(result -> {
                if (result.isAcceptedAsynchronously()) {
                    return DeleteServiceInstanceResponse.builder()
                        .async(true)
                        .operation(result.operationId())
                        .build();
                }

                return DeleteServiceInstanceResponse.builder().build();
            });
    }
}
~~~

Đây là ví dụ minh họa cho reactive API; chữ ký getter hoặc builder có thể khác theo phiên bản Spring Cloud Service Broker. Nếu phiên bản đang dùng có API imperative hoặc kiểu response khác, hãy giữ nguyên quy trình nghiệp vụ và điều chỉnh adapter tương ứng.

Không đặt toàn bộ logic xóa backend trong method callback. Method nên chuyển request thành command, gọi domain service và ánh xạ kết quả sang response model. Cách này giúp kiểm thử nghiệp vụ độc lập với HTTP và framework.

### Domain service

Domain service điều phối kiểm tra và chọn luồng:

~~~java
public Mono<DeprovisionResult> deprovision(
        DeprovisionCommand command) {

    return instanceRepository
        .findByPlatformAndInstanceId(
            currentPlatform.id(),
            command.instanceId()
        )
        .switchIfEmpty(Mono.error(new ServiceInstanceNotFoundException()))
        .flatMap(instance -> {
            validateServiceAndPlan(command, instance);
            validateOwnership(instance);
            validateCanDeprovision(instance);

            if (backendCanDeleteSynchronously(instance)) {
                return deleteSynchronously(instance);
            }

            if (!command.acceptsIncomplete()) {
                return Mono.error(
                    new AsyncOperationNotAcceptedException());
            }

            return acceptAsyncDeprovision(instance);
        });
}
~~~

Đoạn code là pseudocode kiến trúc. Các repository, exception và policy service là thành phần nội bộ do ứng dụng xây dựng. Với reactive stack, tránh gọi blocking JDBC hoặc SDK trực tiếp trên event-loop; dùng reactive client hoặc chuyển blocking I/O sang scheduler phù hợp. Với ứng dụng imperative, áp dụng transaction và executor theo mô hình tương ứng.

## 8. Request và response model ở tầng nghiệp vụ

Không nên dùng trực tiếp framework request/response model làm entity lưu trữ. Tách các model:

| Model | Vai trò |
|---|---|
| DeleteServiceInstanceRequest | Request adapter do Spring Cloud Service Broker tạo |
| DeprovisionCommand | Lệnh nghiệp vụ đã chuẩn hóa |
| ServiceInstance | Aggregate lưu ownership, plan, backend resource và state |
| DeprovisionOperation | Bản ghi theo dõi một lần thu hồi |
| DeprovisionResult | Kết quả domain: hoàn tất đồng bộ hoặc accepted async |
| DeleteServiceInstanceResponse | Response adapter ánh xạ sang contract OSB API |

Ví dụ result nội bộ:

~~~java
public record DeprovisionResult(
    boolean acceptedAsynchronously,
    String operationId
) {
    public static DeprovisionResult completed() {
        return new DeprovisionResult(false, null);
    }

    public static DeprovisionResult accepted(String operationId) {
        return new DeprovisionResult(true, operationId);
    }
}
~~~

Trong response đồng bộ, không cần operation ID. Trong response bất đồng bộ, operation ID phải được lưu bền vững trước khi gửi response cho platform. Nếu response bị mất, request retry có thể tìm operation hiện tại và trả lại cùng token.

## 9. Xử lý bất đồng bộ bằng operation và outbox

Xóa database hoặc cluster có thể mất nhiều thời gian. Không giữ HTTP connection mở cho đến khi mọi tài nguyên phụ thuộc đã được thu hồi. Thay vào đó, broker có thể lưu operation rồi để worker xử lý.

Một transaction ban đầu nên:

1. Khóa instance hoặc kiểm tra version.
2. Chuyển lifecycle state sang **DEPROVISIONING**.
3. Tạo operation ID duy nhất.
4. Ghi operation ở trạng thái **PENDING**.
5. Ghi outbox event chứa internal instance ID và operation ID.
6. Commit transaction.
7. Trả **202 Accepted** cùng operation token.

Worker nhận event và thực hiện:

1. Claim operation bằng lock/lease để tránh xử lý song song.
2. Tải instance và xác minh operation vẫn là operation hiện hành.
3. Gọi backend delete bằng idempotency key ổn định.
4. Đối soát kết quả nếu backend timeout.
5. Cập nhật backend resource state, instance state và operation state trong transaction.
6. Phát metric/audit event đã lọc.

Nếu broker chết sau commit nhưng trước khi gửi message, outbox publisher sẽ gửi lại event. Nếu worker chết sau khi backend xóa tài nguyên nhưng trước khi cập nhật database, lần chạy tiếp theo cần gọi delete idempotent hoặc kiểm tra backend resource đã biến mất trước khi kết luận.

## 10. Idempotency khi nhận DELETE lặp

Platform có thể gửi lại DELETE khi không nhận được response. Deprovision phải được thiết kế để xử lý request lặp an toàn.

| Trạng thái instance | Request DELETE tiếp theo | Hành vi cần có |
|---|---|---|
| **ACTIVE** | Lần đầu | Bắt đầu deprovision |
| **DEPROVISIONING** | Cùng instance/service/plan | Trả operation đang chạy hoặc trạng thái tương ứng; không tạo worker mới |
| **DEPROVISIONED** | Lặp lại cùng yêu cầu | Trả kết quả phù hợp với contract; không xóa tài nguyên khác |
| Không tìm thấy instance | ID không tồn tại trong phạm vi caller | Trả mã trạng thái OSB API quy định cho trường hợp không tồn tại |
| ID có nhưng service/plan mismatch | Request tham chiếu lựa chọn khác | Từ chối; không sửa metadata và không xóa resource |

Idempotency key cho backend nên ổn định theo platform, instance và generation của vòng đời:

~~~text
deprovision_key =
    hash(platform_id, instance_id, provision_generation, "DEPROVISION")
~~~

Không tạo UUID mới mỗi lần retry. Nếu backend hỗ trợ idempotency token, gửi cùng key cho cùng thao tác logic. Nếu không, dùng resource tag hoặc backend lookup để xác định tài nguyên đã bị xóa hay chưa.

Cần phân biệt request lặp của cùng generation với một vòng đời mới được phép dùng lại ID. Nếu policy cho phép reuse instance ID, chỉ tạo generation mới sau khi deprovision trước đã hoàn tất và backend đã được đối soát.

## 11. State machine cho deprovision

Một state machine đơn giản:

~~~mermaid
stateDiagram-v2
    [*] --> ACTIVE
    ACTIVE --> DEPROVISIONING: DELETE accepted
    DEPROVISIONING --> DEPROVISIONED: Backend confirms deletion
    DEPROVISIONING --> DEPROVISION_FAILED: Permanent failure
    DEPROVISIONING --> DEPROVISIONING: Retry transient failure
    DEPROVISION_FAILED --> DEPROVISIONING: Authorized retry
~~~

**DEPROVISIONING** cho biết yêu cầu thu hồi đã được chấp nhận nhưng tài nguyên có thể vẫn tồn tại. Broker không được coi instance đã bị xóa chỉ vì đã gửi lệnh DELETE đến backend.

Khi backend trả timeout, kết quả có thể chưa xác định: resource có thể đã bị xóa nhưng response thất lạc. Broker cần đối soát bằng resource ID, tag hoặc API retrieve. Chỉ sau khi có bằng chứng phù hợp mới cập nhật **DEPROVISIONED**.

Operation state riêng có thể là **PENDING**, **IN_PROGRESS**, **SUCCEEDED**, **FAILED**. Một instance có thể giữ lịch sử nhiều operation; không ghi đè lịch sử để chỉ còn một cờ boolean.

## 12. Xử lý lỗi và response phù hợp

Lỗi deprovision có thể đến từ request, quyền, trạng thái instance hoặc backend.

| Tình huống | Xử lý nghiệp vụ | Phản hồi |
|---|---|---|
| Thiếu hoặc sai query parameter | Không bắt đầu xóa | HTTP lỗi theo contract OSB |
| Instance không thuộc caller | Không tiết lộ dữ liệu instance khác | Lỗi xác thực/phân quyền phù hợp |
| Service/plan không khớp | Không xóa | Lỗi request theo spec |
| Còn binding bị policy cấm | Yêu cầu unbind trước | Lỗi conflict/validation phù hợp contract |
| Instance đang update | Không chạy hai thao tác xung đột | Lỗi trạng thái hoặc retry theo policy |
| Backend lỗi tạm thời | Retry có backoff nếu operation async | Operation tiếp tục in progress |
| Backend lỗi vĩnh viễn | Lưu lỗi đã lọc, giữ trạng thái cần xử lý | Operation failed |
| Backend timeout không rõ kết quả | Reconcile trước khi retry | Operation tiếp tục in progress nếu còn khả năng |
| Instance đã được thu hồi | Xử lý request lặp theo semantics API | Response phù hợp, không gọi backend tạo tác dụng phụ |

Không tự chọn HTTP status theo cảm tính. Các trường hợp instance không tồn tại, service/plan không hợp lệ, request chưa đủ điều kiện và thao tác async không được chấp nhận có quy tắc riêng trong OSB API version. Hãy ánh xạ exception nội bộ sang status/error response tại adapter của framework.

Thông báo lỗi không nên chứa SQL, stack trace, backend token, endpoint quản trị hoặc credential. Có thể trả error code và mô tả an toàn, đồng thời ghi trace ID để đội vận hành tra cứu.

## 13. Xóa tài nguyên phụ thuộc và dữ liệu

Một instance có thể tạo ra nhiều tài nguyên:

- Database hoặc cluster.
- Volume, snapshot và backup policy.
- Network rule, security group hoặc endpoint.
- Credential, user, role và binding.
- Secret, config và metadata do broker tạo.
- Custom resource trong Kubernetes.

Broker cần xác định ownership của từng tài nguyên và thứ tự thu hồi. Ví dụ, thu hồi credential/binding trước, dừng workload nếu cần, xóa database hoặc cluster, rồi dọn các resource phụ thuộc. Thứ tự cụ thể tùy backend; không xóa network hoặc secret dùng chung cho instance khác.

### Backup và retention

Deprovision không nhất thiết có nghĩa xóa mọi bản backup ngay lập tức. Chính sách có thể yêu cầu giữ backup trong một khoảng thời gian, hỗ trợ khôi phục hoặc tuân thủ retention. Broker phải phân biệt:

- Tài nguyên đang chạy cần xóa.
- Backup được giữ theo retention policy.
- Snapshot phải xóa theo yêu cầu hoặc chính sách.
- Metadata audit cần giữ theo thời hạn.
- Secret/credential phải thu hồi ngay khi không còn cần.

Không dùng thao tác deprovision để xóa dữ liệu dùng chung hoặc vi phạm chính sách retention. Cần công bố rõ hành vi backup sau khi xóa service instance.

## 14. Bảo mật trong deleteServiceInstance()

Deprovision là thao tác phá hủy tài nguyên, do đó kiểm soát quyền cần chặt chẽ:

- Xác thực platform qua TLS và credential đã đăng ký.
- Phân giải tenant ownership từ instance record đã xác minh.
- Kiểm tra service ID/plan ID và caller scope trước khi xóa.
- Không dùng instance ID làm bí mật hoặc token quyền.
- Backend credential chỉ có quyền xóa tài nguyên thuộc phạm vi broker quản lý.
- Không nhận backend resource ID tùy ý từ request để xóa trực tiếp.
- Audit ai yêu cầu xóa, instance nào, operation ID và kết quả.
- Giới hạn quyền retry hoặc force cleanup cho thao tác quản trị.
- Không ghi secret vào log hoặc error response.

Nếu broker hỗ trợ force deprovision để dọn tài nguyên bị kẹt, đó phải là chức năng quản trị riêng với xác thực, phân quyền và audit, không phải hành vi mặc định của request DELETE từ platform.

## 15. Ví dụ adapter backend

Có thể định nghĩa interface để tách logic OSB khỏi nhà cung cấp:

~~~java
public interface ServiceInstanceDeprovisioner {
    Mono<BackendDeleteResult> delete(
        String backendResourceId,
        String idempotencyKey
    );

    Mono<BackendResourceState> find(
        String backendResourceId
    );
}
~~~

Một adapter Kubernetes có thể xóa custom resource do operator quản lý:

~~~java
public Mono<BackendDeleteResult> delete(
        String resourceName,
        String idempotencyKey) {

    return kubernetesClient
        .resources(PostgreSQLCluster.class)
        .withName(resourceName)
        .delete()
        .thenReturn(BackendDeleteResult.accepted());
}
~~~

Đây là pseudocode; API client và kiểu resource cụ thể phụ thuộc Kubernetes client/operator. Xóa custom resource có thể chỉ khởi động quá trình finalizer cleanup, chưa chứng minh mọi tài nguyên đã biến mất. Worker cần poll resource hoặc theo dõi trạng thái operator trước khi đánh dấu instance hoàn tất.

Với managed database, adapter gọi API provider và kiểm tra operation/resource state. Adapter không nên trả thành công chỉ vì HTTP DELETE được chấp nhận nếu provider còn đang xóa cluster.

## 16. Kiểm thử deleteServiceInstance()

Bộ kiểm thử nên bao gồm request model, response mapping, state transition, idempotency và backend behavior.

| Trường hợp | Input/trạng thái | Kết quả mong đợi |
|---|---|---|
| Xóa đồng bộ thành công | Instance active, backend xóa ngay | Response 200, instance deprovisioned |
| Xóa bất đồng bộ | Backend cần thời gian, accepts incomplete true | Response 202 với operation token |
| Async không được chấp nhận | Backend cần thời gian, accepts incomplete false | Lỗi theo OSB API, không trả accepted giả |
| Instance không tồn tại | ID không có trong phạm vi | Status theo contract, không gọi backend |
| Service ID sai | Query service ID khác bản ghi | Từ chối, instance không đổi |
| Plan ID sai | Query plan ID khác bản ghi | Từ chối, instance không đổi |
| Còn binding | Binding active và policy yêu cầu unbind trước | Không xóa instance |
| Update đang chạy | Instance state updating | Không chạy deprovision song song |
| DELETE lặp | Instance đang deprovisioning | Trả operation hiện tại, không enqueue trùng |
| DELETE sau thành công | Instance đã deprovisioned | Xử lý idempotent theo contract |
| Backend timeout | Kết quả xóa chưa rõ | Reconcile trước khi retry |
| Worker crash | Backend xóa xong, state chưa cập nhật | Retry/lookup xác nhận không xóa nhầm |
| Backend lỗi permanent | Permission denied hoặc policy block | Operation failed, lỗi đã lọc |
| Resource phụ thuộc | Có volume, backup, secret | Cleanup đúng ownership và retention |
| Caller sai tenant | Dùng ID của tenant khác | Không truy cập hoặc xóa tài nguyên |
| Request đồng thời | Hai DELETE cùng instance | Một operation có hiệu lực, request kia replay |

Nên kiểm thử repository/transaction bằng database thật hoặc Testcontainers để xác minh lock và optimistic version. Với backend adapter, dùng fake server có thể mô phỏng DELETE thành công nhưng response mất, trả 404 khi retry hoặc giữ resource ở trạng thái terminating để kiểm tra reconciliation.

## 17. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Xóa database record trước backend | Mất thông tin để retry hoặc đối soát | Giữ instance ở DEPROVISIONING cho đến khi xác nhận |
| Chỉ gửi HTTP DELETE rồi trả thành công | Backend có thể vẫn đang xóa | Theo dõi trạng thái backend |
| Không kiểm tra service/plan ID | Request sai có thể xóa instance | Đối chiếu với metadata đã lưu |
| Xóa instance khi binding còn hiệu lực | Consumer mất quyền đột ngột, credential có thể còn sót | Kiểm tra và thu hồi binding |
| Cho update và deprovision chạy đồng thời | Worker có thể tạo lại hoặc sửa tài nguyên đang xóa | Khóa lifecycle và kiểm tra operation |
| Tạo operation mới cho mỗi retry | Nhiều worker cùng xóa hoặc cleanup lặp | Replay operation theo instance/generation |
| Coi timeout là thất bại chắc chắn | Retry có thể đụng trạng thái không xác định | Reconcile trước khi thực thi lại |
| Xóa backup bất kể retention | Mất khả năng phục hồi hoặc vi phạm policy | Áp dụng retention riêng |
| Dùng backend ID do caller gửi | Có thể xóa tài nguyên ngoài phạm vi | Chỉ dùng resource reference đã lưu |
| Đánh dấu deleted ngay khi accepted | Platform tưởng tài nguyên đã biến mất | Tách DEPROVISIONING và DEPROVISIONED |

## 18. Nguyên tắc cần ghi nhớ

**deleteServiceInstance()** là adapter của thao tác deprovision trong OSB API. Nó tiếp nhận request đã được framework ánh xạ, chuyển sang domain command, xác minh instance và ownership, kiểm tra trạng thái cùng binding, điều phối backend và trả response đúng với kết quả đồng bộ hoặc bất đồng bộ.

Khi triển khai trong Spring Cloud Service Broker, hãy giữ các nguyên tắc sau:

- Lấy instance ID từ path và service/plan ID từ query; đối chiếu với dữ liệu đã lưu.
- Xác thực platform và tenant ownership trước khi thu hồi.
- Phân biệt unbind với deprovision; xử lý binding còn tồn tại theo policy.
- Không chạy deprovision song song với provision/update đang hoạt động.
- Lưu trạng thái DEPROVISIONING, operation và outbox trước công việc dài.
- Trả 200 khi xóa đã hoàn tất; trả 202 cùng operation token khi async được chấp nhận.
- Dùng idempotency key và reconciliation để xử lý DELETE lặp hoặc timeout.
- Chỉ đánh dấu DEPROVISIONED khi backend đã được xác nhận.
- Giữ backup/audit theo retention và thu hồi credential đúng thứ tự.
- Ánh xạ lỗi nội bộ sang HTTP response theo đúng OSB API version.

Với cách tổ chức này, broker có thể thu hồi tài nguyên an toàn, phản hồi đúng cho platform, tiếp tục xử lý sau timeout và giữ state store nhất quán với hạ tầng thực tế.

