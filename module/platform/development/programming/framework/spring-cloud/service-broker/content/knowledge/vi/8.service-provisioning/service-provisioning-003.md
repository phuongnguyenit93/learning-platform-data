# Cài đặt createServiceInstance() trong ServiceInstanceService

Trong Open Service Broker API (OSB API), thao tác provision bắt đầu khi nền tảng yêu cầu broker tạo một service instance theo service và plan đã chọn. Với Spring Cloud Open Service Broker, phần xử lý yêu cầu này được triển khai qua phương thức createServiceInstance() trong ServiceInstanceService. Đây là điểm nối giữa hợp đồng HTTP của OSB API và nghiệp vụ cấp phát tài nguyên thực tế.

Trong module **SPRING_CLOUD_SERVICE_BROKER**, phương thức này cần phối hợp nhiều việc: xác thực service và plan, kiểm tra parameters, bảo đảm idempotency, ghi nhận trạng thái, gọi API nhà cung cấp, xử lý đồng bộ hoặc bất đồng bộ và tạo response đúng hợp đồng. Một handler chỉ gọi API tạo database rồi trả thành công sẽ chưa đủ an toàn cho môi trường cloud, vì request có thể được gửi lại, provider có thể timeout và tiến trình broker có thể dừng giữa chừng.

Bài học này đi từ hợp đồng của request đến cấu trúc triển khai, ví dụ Java với Reactor, quản lý trạng thái và operation, xử lý lỗi, kiểm thử và các tình huống vận hành thường gặp.

## 1. Vị trí của createServiceInstance() trong luồng provision

Một luồng provision cơ bản diễn ra như sau:

1. Người dùng chọn một service và plan trên nền tảng.
2. Nền tảng gửi request đến endpoint tạo service instance của broker.
3. Spring Cloud Open Service Broker nhận request HTTP, chuyển dữ liệu thành CreateServiceInstanceRequest và gọi ServiceInstanceService.
4. Handler kiểm tra yêu cầu, tạo bản ghi instance hoặc tìm bản ghi đã tồn tại.
5. Broker gọi provider adapter để tạo tài nguyên.
6. Broker lưu kết quả, trạng thái và thông tin operation nếu có.
7. Handler trả CreateServiceInstanceResponse để framework ánh xạ thành response OSB API.

Endpoint OSB API v2 có dạng:

~~~http
PUT /v2/service_instances/{instance_id}
Content-Type: application/json
Accept: application/json
~~~

Ví dụ request:

~~~json
{
  "service_id": "postgres-service",
  "plan_id": "postgres-small-v1",
  "organization_guid": "org-123",
  "space_guid": "space-456",
  "parameters": {
    "database_name": "orders",
    "storage_gb": 30
  },
  "context": {
    "platform": "cloud-foundry",
    "organization_name": "commerce",
    "space_name": "production"
  }
}
~~~

Các trường quan trọng:

| Trường | Ý nghĩa | Cách handler sử dụng |
|---|---|---|
| instance_id | Định danh service instance do nền tảng cung cấp trong URL | Khóa idempotency và khóa tra cứu instance |
| service_id | ID service trong catalog | Xác định loại tài nguyên cần cấp phát |
| plan_id | ID plan thuộc service | Chọn cấu hình và giới hạn tài nguyên |
| organization_guid | Định danh tổ chức trên nền tảng | Lưu quan hệ sở hữu và áp dụng chính sách |
| space_guid | Định danh space hoặc phạm vi triển khai | Phân vùng tài nguyên theo nền tảng |
| parameters | Tham số riêng của yêu cầu provision | Xác thực schema và chuyển cho provider adapter |
| context | Metadata do nền tảng gửi theo hợp đồng | Điều chỉnh tích hợp theo nền tảng khi cần |

Request còn có thể mang các header hoặc query parameter theo phiên bản OSB API, bao gồm thông tin cho biết client có chấp nhận thao tác bất đồng bộ hay không. Spring Cloud Open Service Broker chuyển ngữ cảnh đó vào request object. Hãy kiểm tra API của đúng phiên bản thư viện đang dùng để xác nhận tên accessor và cách framework ánh xạ dữ liệu.

## 2. ServiceInstanceService và trách nhiệm của handler

ServiceInstanceService là abstraction ở tầng service của Spring Cloud Open Service Broker. Ứng dụng cung cấp implementation để xử lý vòng đời service instance. Tùy phiên bản thư viện, interface có thể yêu cầu thêm các phương thức lấy instance, update, delete hoặc truy vấn last operation.

Về mặt trách nhiệm, createServiceInstance() nên điều phối nghiệp vụ cấp phát thay vì chứa toàn bộ chi tiết HTTP hoặc logic của nhà cung cấp.

Một cách chia lớp thường dùng:

| Thành phần | Trách nhiệm |
|---|---|
| ServiceInstanceService implementation | Điều phối quy trình provision và tạo response OSB |
| Catalog/Plan registry | Tra cứu service, plan, capability và schema đã công bố |
| Provisioning policy | Kiểm tra quyền, giới hạn và quy tắc cấp phát |
| ServiceInstanceRepository | Lưu và đọc trạng thái instance |
| OperationRepository | Lưu operation bất đồng bộ và trạng thái xử lý |
| Provider adapter | Gọi API quản trị của database, cache hoặc dịch vụ cloud |
| Idempotency component | Nhận diện request lặp và xử lý xung đột |
| Worker hoặc message consumer | Tiếp tục thao tác dài sau khi request được chấp nhận |

Một handler gọn giúp dễ kiểm thử và giúp thay đổi nhà cung cấp mà không phải viết lại hợp đồng OSB API.

## 3. Thiết kế dữ liệu trước khi viết phương thức

Trước khi gọi provider, broker cần có nơi lưu trạng thái của instance. Không nên chỉ dựa vào biến trong bộ nhớ của tiến trình, vì broker có thể khởi động lại hoặc chạy nhiều replica.

Một bản ghi service instance có thể chứa:

| Thuộc tính | Mục đích |
|---|---|
| instanceId | ID do nền tảng gửi |
| serviceId | Service đã chọn |
| planId | Plan được cấp phát |
| organizationGuid, spaceGuid | Phạm vi sở hữu |
| parameters | Tham số đã chuẩn hóa, đã loại dữ liệu nhạy cảm nếu không cần lưu |
| requestFingerprint | Dấu vân tay của request để phát hiện retry xung đột |
| state | Trạng thái vòng đời |
| providerResourceId | ID tài nguyên do provider trả về |
| operationId | Operation đang theo dõi nếu có |
| createdAt, updatedAt | Thời điểm tạo và cập nhật |
| lastErrorCode | Mã lỗi an toàn để đối soát |

Bảng operation có thể lưu operationId, instanceId, operationType, state, providerOperationId, startedAt, updatedAt và thông tin lỗi đã được làm sạch.

Một state machine rút gọn:

~~~mermaid
stateDiagram-v2
    [*] --> PROVISIONING: yêu cầu mới được ghi nhận
    PROVISIONING --> SUCCEEDED: provider xác nhận tạo xong
    PROVISIONING --> FAILED: lỗi cuối cùng
    PROVISIONING --> PROVISIONING: đang chờ hoặc retry an toàn
    SUCCEEDED --> DEPROVISIONING: yêu cầu thu hồi
    FAILED --> PROVISIONING: retry có kiểm soát
    DEPROVISIONING --> DEPROVISIONED: thu hồi hoàn tất
~~~

Không phải mọi trạng thái trong sơ đồ đều là trạng thái OSB API bắt buộc. Đây là mô hình nội bộ để broker điều phối và phục hồi công việc. Response gửi ra nền tảng phải ánh xạ trạng thái nội bộ theo hợp đồng giao thức.

## 4. Các bước xử lý createServiceInstance()

Một implementation đáng tin cậy có thể chia quy trình thành các bước sau.

### Bước 1: Xác thực service và plan

Tra cứu serviceId và planId trong catalog nội bộ. Kiểm tra plan thuộc đúng service, đang cho phép tạo instance mới và có provider profile hợp lệ.

Không tin rằng request hợp lệ chỉ vì nền tảng đã lấy catalog trước đó. Catalog có thể đã thay đổi hoặc client có thể gửi request trực tiếp.

Các điều kiện cần kiểm tra:

- Service tồn tại và đang được cung cấp.
- Plan tồn tại và thuộc service đó.
- Plan được bật cho provision mới.
- Capability provision được triển khai.
- Provider adapter và cấu hình cần thiết đã sẵn sàng.

### Bước 2: Xác thực parameters và context

Kiểm tra kiểu dữ liệu, trường bắt buộc, giới hạn, enum, độ dài và quan hệ giữa các tham số. Ví dụ storage_gb phải nằm trong khoảng của plan; database_name phải thỏa quy tắc đặt tên.

Context có thể giúp broker nhận biết nền tảng hoặc thông tin tổ chức, nhưng không nên xem context là bằng chứng xác thực danh tính. Xác thực và phân quyền phải được thực hiện ở lớp bảo mật của broker dựa trên cơ chế tin cậy.

Chỉ chuyển các trường được cho phép đến provider adapter. Không chuyển nguyên object request sang provider một cách thiếu kiểm soát.

### Bước 3: Tạo fingerprint và kiểm tra idempotency

OSB API dùng instance_id do nền tảng cấp để định danh yêu cầu provision. Nền tảng có thể retry cùng request nếu timeout hoặc mất kết nối. Broker phải tránh tạo hai database chỉ vì cùng một request được gửi lại.

Fingerprint nên được tạo từ dữ liệu có ý nghĩa đối với cấp phát, chẳng hạn serviceId, planId, organizationGuid, spaceGuid và parameters đã chuẩn hóa. Cần chuẩn hóa thứ tự key, kiểu dữ liệu và giá trị mặc định trước khi băm.

Quy tắc xử lý:

- Chưa có instanceId: bắt đầu quy trình tạo mới.
- Đã có instanceId với fingerprint giống nhau và đang PROVISIONING: trả lại cùng operation hoặc kết quả đang xử lý.
- Đã có instanceId với fingerprint giống nhau và đã SUCCEEDED: trả kết quả hiện hữu theo quy tắc idempotent.
- Đã có instanceId nhưng fingerprint khác: từ chối xung đột, không thay đổi tài nguyên hiện tại.
- Bản ghi ở trạng thái FAILED: áp dụng chính sách retry hoặc reconciliation có kiểm soát; không tự tạo tài nguyên mới nếu chưa xác định kết quả lần trước.

Cơ sở dữ liệu cần unique constraint trên instanceId. Việc chỉ kiểm tra tồn tại rồi mới insert trong hai câu lệnh riêng có thể tạo race condition khi hai request đồng thời cùng đi vào.

### Bước 4: Ghi nhận yêu cầu trước khi gọi provider

Sau khi xác thực, broker tạo bản ghi instance với trạng thái PROVISIONING và operation tương ứng nếu cần. Việc ghi nhận phải có tính nguyên tử trong database.

Không giữ transaction database mở trong khi chờ một API cloud chạy lâu. Một transaction ngắn để reserve instance và ghi outbox event thường an toàn hơn. Worker đọc outbox, gọi provider và cập nhật trạng thái sau đó.

Nếu provider hỗ trợ idempotency key, dùng một khóa ổn định gắn với instanceId hoặc operationId. Nhờ vậy, khi broker timeout sau khi provider đã tạo tài nguyên, lần retry có thể truy vấn hoặc tiếp tục cùng yêu cầu thay vì tạo thêm tài nguyên.

### Bước 5: Gọi provider adapter

Provider adapter nhận một command nội bộ đã xác thực, ví dụ:

~~~java
public record ProvisionCommand(
    String instanceId,
    String serviceId,
    String planId,
    String organizationGuid,
    String spaceGuid,
    Map<String, Object> parameters,
    String idempotencyKey
) {}
~~~

Adapter chịu trách nhiệm chuyển command thành request API cụ thể của nhà cung cấp. Nó không nên phụ thuộc vào CreateServiceInstanceRequest của OSB ở mọi lớp, vì như vậy logic provider sẽ bị gắn chặt với framework.

Kết quả adapter nên đủ để broker lưu providerResourceId, endpoint tham chiếu và trạng thái cấp phát. Secrets cần được lưu ở kho bí mật hoặc mã hóa theo chính sách, không đưa vào log hoặc response ngoài ý muốn.

### Bước 6: Trả response phù hợp với trạng thái

Nếu provider tạo tài nguyên xong trong thời gian xử lý request, broker lưu trạng thái SUCCEEDED và trả response thành công đồng bộ.

Nếu cần xử lý bất đồng bộ và client đã chấp nhận, broker trả response cho biết thao tác đang được xử lý, kèm operation ID ổn định để nền tảng gọi last operation.

Nếu client không chấp nhận bất đồng bộ mà broker không thể hoàn thành đồng bộ, broker phải trả lỗi theo hợp đồng OSB API cho trường hợp cần xử lý bất đồng bộ. Không được trả thành công trước khi tài nguyên thực sự được tạo.

## 5. Ví dụ implementation với Spring Cloud Open Service Broker

Đoạn mã sau minh họa cấu trúc triển khai theo API reactive thường dùng của Spring Cloud Open Service Broker. Tên accessor, constructor, builder và kiểu trả về cụ thể cần đối chiếu với phiên bản dependency của dự án; các interface repository và provider trong ví dụ là abstraction do ứng dụng định nghĩa.

~~~java
@Service
public class DatabaseServiceInstanceService
        implements ServiceInstanceService {

    private final CatalogRegistry catalogRegistry;
    private final ProvisioningPolicy provisioningPolicy;
    private final ServiceInstanceRepository instanceRepository;
    private final ProvisioningCoordinator provisioningCoordinator;

    public DatabaseServiceInstanceService(
            CatalogRegistry catalogRegistry,
            ProvisioningPolicy provisioningPolicy,
            ServiceInstanceRepository instanceRepository,
            ProvisioningCoordinator provisioningCoordinator) {
        this.catalogRegistry = catalogRegistry;
        this.provisioningPolicy = provisioningPolicy;
        this.instanceRepository = instanceRepository;
        this.provisioningCoordinator = provisioningCoordinator;
    }

    @Override
    public Mono<CreateServiceInstanceResponse> createServiceInstance(
            CreateServiceInstanceRequest request) {

        return Mono.defer(() -> {
            ProvisionCommand command = toCommand(request);

            return catalogRegistry.findPlan(
                        command.serviceId(), command.planId())
                    .switchIfEmpty(Mono.error(
                        new InvalidServicePlanException()))
                    .flatMap(plan ->
                        provisioningPolicy.validate(command, plan)
                            .then(provisioningCoordinator.create(
                                command, plan, request.isAsyncAccepted()))
                    )
                    .map(this::toResponse);
        });
    }

    private ProvisionCommand toCommand(
            CreateServiceInstanceRequest request) {
        return new ProvisionCommand(
                request.getServiceInstanceId(),
                request.getServiceDefinitionId(),
                request.getPlanId(),
                request.getOrganizationGuid(),
                request.getSpaceGuid(),
                request.getParameters(),
                request.getServiceInstanceId()
        );
    }

    private CreateServiceInstanceResponse toResponse(
            ProvisioningResult result) {
        CreateServiceInstanceResponse.Builder builder =
                CreateServiceInstanceResponse.builder();

        if (result.isAsync()) {
            builder.async(true)
                   .operation(result.operationId());
        }

        if (result.dashboardUrl() != null) {
            builder.dashboardUrl(result.dashboardUrl());
        }

        return builder.build();
    }
}
~~~

Đây là skeleton để minh họa ranh giới và luồng xử lý, không phải một lớp có thể biên dịch độc lập khi chưa định nghĩa các abstraction của ứng dụng. Đặc biệt, hãy xác minh chữ ký ServiceInstanceService, accessor asyncAccepted và các builder method theo đúng phiên bản Spring Cloud Open Service Broker đang sử dụng.

Handler không tự gọi subscribe() để chạy nền. Nó trả về Mono cho framework quản lý subscription. Công việc bất đồng bộ cần được ghi bền vững và chuyển cho worker hoặc message consumer. Nếu gọi subscribe() tùy tiện bên trong handler, lỗi có thể bị tách khỏi response, request có thể mất theo tiến trình và khó kiểm soát backpressure.

### Coordinator điều phối tạo instance

Coordinator có thể trả về một kết quả nội bộ:

~~~java
public record ProvisioningResult(
    boolean async,
    String operationId,
    String dashboardUrl
) {}
~~~

Một triển khai khái niệm:

~~~java
public Mono<ProvisioningResult> create(
        ProvisionCommand command,
        ServicePlan plan,
        boolean asyncAccepted) {

    return reservationService.reserve(command)
        .flatMap(reservation -> {
            if (reservation.isExisting()) {
                return Mono.just(reservation.toResult());
            }

            if (plan.requiresAsyncProvisioning()) {
                if (!asyncAccepted) {
                    return reservationService.cancelUnstarted(
                            reservation)
                        .then(Mono.error(
                            new AsyncProvisioningRequiredException()));
                }

                return outboxService.enqueueProvision(
                            reservation.operationId(),
                            command)
                    .thenReturn(new ProvisioningResult(
                            true,
                            reservation.operationId(),
                            null));
            }

            return providerAdapter.provision(command, plan)
                .flatMap(providerResource ->
                    reservationService.markSucceeded(
                            reservation,
                            providerResource)
                        .thenReturn(new ProvisioningResult(
                            false, null,
                            providerResource.dashboardUrl()))
                )
                .onErrorResume(error ->
                    reservationService.markFailure(
                            reservation, error)
                        .then(Mono.error(error)));
        });
}
~~~

Đoạn code này cũng là pseudocode: kiểu repository, reservation và exception thuộc ứng dụng. Trong hệ thống thật, cần bảo đảm reservation được commit trước khi worker xử lý; outbox event và bản ghi operation nên được ghi trong cùng transaction. Đường đồng bộ cần có timeout và cơ chế reconciliation nếu provider đã tạo tài nguyên nhưng phản hồi bị mất.

## 6. Đồng bộ và bất đồng bộ: chọn theo thời gian cấp phát

Không phải mọi thao tác provision đều cần bất đồng bộ. Nếu provider có thể tạo tài nguyên nhanh và broker có thể hoàn thành trong thời gian request hợp lý, xử lý đồng bộ giúp luồng đơn giản hơn.

Nên dùng bất đồng bộ khi:

- Provider cần nhiều bước hoặc thời gian tạo tài nguyên dài.
- Quá trình phải chờ scheduler, network hoặc hệ thống phê duyệt.
- API nhà cung cấp trả operation ID và yêu cầu polling.
- Thời gian xử lý có thể vượt timeout của gateway hoặc nền tảng.

Với thao tác bất đồng bộ, quy trình nên là:

1. Ghi service instance ở trạng thái PROVISIONING.
2. Tạo operation ID và lưu trạng thái operation.
3. Ghi outbox event trong cùng transaction.
4. Trả response async cho nền tảng nếu request cho phép.
5. Worker lấy event và gọi provider.
6. Worker cập nhật providerResourceId và trạng thái cuối.
7. Nền tảng gọi last operation để nhận trạng thái theo hợp đồng.

Một response async thường cần thể hiện cờ async và operation identifier. Framework sẽ ánh xạ response object sang HTTP response theo OSB API. Không tự đặt HTTP status hoặc cấu trúc JSON riêng nếu framework đã quản lý phần giao thức.

Nếu nền tảng không chấp nhận bất đồng bộ, broker cần hoàn thành đồng bộ hoặc trả lỗi thích hợp theo OSB API. Không được đưa công việc vào hàng đợi rồi trả response đồng bộ thành công khi chưa có tài nguyên.

## 7. Idempotency và xử lý request đồng thời

Idempotency là yêu cầu cốt lõi của createServiceInstance(). Nền tảng có thể gửi lại request do timeout, retry tự động hoặc mất response. Broker phải bảo đảm một instance ID không tạo ra nhiều tài nguyên ngoài ý muốn.

Một chiến lược có thể gồm:

- Unique constraint trên instanceId.
- Fingerprint của nội dung request đã chuẩn hóa.
- Transaction reserve trước khi gọi provider.
- Idempotency key ổn định gửi đến provider nếu API hỗ trợ.
- Operation record có unique constraint cho operation logic tương ứng.
- Cơ chế kiểm tra trạng thái provider khi kết quả lần trước không rõ ràng.

Tình huống hai request đồng thời:

~~~mermaid
sequenceDiagram
    participant P as Platform
    participant B1 as Broker node A
    participant B2 as Broker node B
    participant DB as Database
    participant API as Provider API

    P->>B1: Provision instance-123
    P->>B2: Retry instance-123
    B1->>DB: Insert reservation
    B2->>DB: Insert same instance ID
    DB-->>B1: Insert succeeds
    DB-->>B2: Unique constraint conflict
    B2->>DB: Read existing instance
    DB-->>B2: PROVISIONING + same fingerprint
    B1->>API: Create with stable idempotency key
    API-->>B1: Provider resource ID
    B1->>DB: Mark SUCCEEDED
    B1-->>P: Provision result
    B2-->>P: Existing operation/result
~~~

Node B không được coi unique constraint conflict là lỗi cấp phát ngay lập tức. Nó cần đọc lại bản ghi đã tồn tại và so sánh fingerprint. Nếu cùng request, trả trạng thái hiện có. Nếu request khác nội dung, trả lỗi xung đột theo quy tắc broker.

Nếu provider không hỗ trợ idempotency key, broker cần chiến lược reconciliation: tra cứu tài nguyên theo external reference hoặc tag ổn định trước khi gửi lệnh tạo lại. Không có cách nào bảo đảm exactly-once tuyệt đối giữa hai hệ thống độc lập chỉ bằng một transaction database; thiết kế cần chịu được retry và phát hiện trạng thái không chắc chắn.

## 8. Quản lý lỗi và ánh xạ sang OSB API

Lỗi trong createServiceInstance() cần được phân loại để nền tảng nhận được phản hồi phù hợp và vận hành có thể khắc phục.

| Loại lỗi | Ví dụ | Cách xử lý |
|---|---|---|
| Request không hợp lệ | Parameters sai schema | Từ chối với lỗi client có ý nghĩa |
| Service/plan không hợp lệ | ID không tồn tại hoặc plan không thuộc service | Từ chối, không gọi provider |
| Không đủ quyền | Tenant không được dùng plan | Từ chối và ghi nhận mã lỗi an toàn |
| Xung đột idempotency | Cùng instance ID nhưng request khác | Trả lỗi xung đột, giữ nguyên instance cũ |
| Provider từ chối | Quota hoặc cấu hình không hợp lệ | Ánh xạ thành lỗi nghiệp vụ phù hợp |
| Provider tạm thời không khả dụng | Timeout, 429 hoặc 5xx | Retry có giới hạn hoặc giữ operation ở trạng thái chờ |
| Kết quả không xác định | Timeout sau khi provider có thể đã tạo tài nguyên | Reconcile trước khi tạo lại |
| Lỗi nội bộ | Database hoặc serializer lỗi | Trả lỗi server, log correlation ID |

Không trả stack trace, access token, password hoặc nội dung bí mật từ provider cho nền tảng. Log nên chứa instanceId, operationId, provider request ID và mã lỗi đã làm sạch, không chứa credential.

Cần phân biệt lỗi có thể retry và lỗi cuối cùng. Retry phải có backoff, jitter, giới hạn số lần và cơ chế dead-letter hoặc cảnh báo. Khi provider trả rate limit, tôn trọng thời gian chờ nếu API có cung cấp.

## 9. Giao dịch, outbox và phục hồi sau sự cố

Một transaction database không thể bao trùm an toàn cả thao tác ghi dữ liệu nội bộ và một lời gọi HTTP đến provider. Nếu broker giữ transaction trong lúc gọi provider, lock có thể kéo dài và gây nghẽn. Nếu gọi provider trước rồi mới ghi database, tiến trình có thể dừng sau khi provider tạo tài nguyên nhưng trước khi broker lưu kết quả.

Mẫu outbox giúp thu hẹp khoảng trống này:

1. Trong một transaction ngắn, insert service instance, operation và outbox event.
2. Commit transaction.
3. Worker đọc outbox event chưa xử lý.
4. Worker gọi provider với idempotency key ổn định.
5. Worker lưu kết quả và đánh dấu event đã xử lý.
6. Nếu worker dừng, event chưa hoàn tất có thể được xử lý lại.

Outbox thường cho bảo đảm giao nhận ít nhất một lần. Do đó worker và provider adapter vẫn phải idempotent. Một worker có thể xử lý lại event sau khi provider đã thành công nhưng broker chưa kịp ghi kết quả.

Định kỳ cần có tác vụ reconciliation để tìm:

- Instance ở PROVISIONING quá lâu.
- Operation không được cập nhật trong thời gian quy định.
- Tài nguyên provider tồn tại nhưng thiếu bản ghi broker.
- Bản ghi broker báo thành công nhưng tài nguyên provider không còn.
- Event outbox bị lỗi hoặc retry vượt ngưỡng.

Quy trình phục hồi phải có audit trail để người vận hành biết ai yêu cầu, request nào, provider nào và hành động khắc phục đã diễn ra.

## 10. Bảo mật trong quá trình provision

Provision có thể tạo tài nguyên tính phí và quyền truy cập mới, vì vậy handler cần bảo vệ cả request lẫn thông tin gửi đến provider.

- Xác thực nền tảng gọi broker bằng cơ chế bảo mật được triển khai, chẳng hạn TLS và xác thực phù hợp.
- Phân quyền theo tenant, organization, space và chính sách sử dụng service.
- Kiểm tra parameters theo allowlist; không chuyển các trường tùy ý đến provider.
- Dùng service account có quyền tối thiểu cần thiết.
- Mã hóa dữ liệu nhạy cảm khi lưu; dùng secret manager cho credentials.
- Không ghi password, token hoặc secret vào log, trace hay error message.
- Giới hạn kích thước request và kiểm tra dữ liệu đầu vào để giảm rủi ro lạm dụng.
- Gắn correlation ID và audit event để truy vết mà không làm lộ dữ liệu bí mật.

Không nên tin organizationGuid hoặc spaceGuid trong payload như một bằng chứng quyền hạn độc lập. Broker cần đối chiếu với danh tính đã xác thực hoặc ngữ cảnh tin cậy mà nền tảng cung cấp theo mô hình tích hợp.

## 11. Kiểm thử createServiceInstance()

Kiểm thử cần xác nhận hành vi nghiệp vụ và hợp đồng OSB API. Một số nhóm trường hợp quan trọng:

| Trường hợp | Kết quả mong đợi |
|---|---|
| Service và plan hợp lệ | Tạo instance đúng plan |
| Service không tồn tại | Từ chối, không gọi provider |
| Plan không thuộc service | Từ chối, không tạo bản ghi cấp phát |
| Parameters ngoài schema | Từ chối với lỗi có ý nghĩa |
| Request mới | Tạo một reservation và một lần cấp phát |
| Retry cùng request | Trả cùng instance hoặc operation, không tạo tài nguyên thứ hai |
| Cùng ID nhưng parameters khác | Trả xung đột |
| Hai request đồng thời | Chỉ một reservation thắng; request còn lại đọc kết quả hiện có |
| Provider timeout trước khi tạo | Retry theo chính sách |
| Provider timeout sau khi có thể đã tạo | Reconcile trước khi gửi lệnh tạo lại |
| Client chấp nhận async | Trả operation và worker tiếp tục xử lý |
| Client không chấp nhận async | Hoàn tất đồng bộ hoặc trả lỗi async-required phù hợp |
| Broker restart giữa tiến trình | Khôi phục từ bản ghi và outbox |

Nên dùng provider giả lập để kiểm soát response, timeout và lỗi. Kiểm thử tích hợp có thể dùng môi trường provider sandbox hoặc test container phù hợp. Ngoài kết quả response, cần kiểm tra số lần provider được gọi, số bản ghi instance, trạng thái operation và việc không rò rỉ secrets trong log.

Với Reactor, tránh dùng block() trong đường xử lý reactive. Nếu SDK provider chỉ có API blocking, cô lập nó bằng adapter và chạy trên scheduler phù hợp cho tác vụ blocking. Không để một lời gọi blocking chiếm event-loop thread.

## 12. Những lỗi triển khai thường gặp

**Gọi provider trước khi lưu instance.** Broker có thể mất kết quả nếu tiến trình dừng sau khi provider tạo tài nguyên. Hãy reserve instance và operation trước, sau đó gọi provider bằng cơ chế có thể retry.

**Chỉ dùng câu lệnh kiểm tra tồn tại để chống trùng.** Hai request đồng thời có thể cùng thấy chưa tồn tại. Dùng unique constraint và xử lý xung đột bằng cách đọc lại bản ghi.

**Trả thành công khi mới đưa việc vào queue.** Chấp nhận bất đồng bộ phải được thể hiện bằng response async và operation ID theo hợp đồng. Không báo provision hoàn tất trước khi provider xác nhận.

**Tạo operation ID mới cho mỗi lần retry.** Retry cùng một yêu cầu đang chạy cần nhận diện operation hiện có. Tạo nhiều operation cho một instance sẽ khiến nền tảng khó theo dõi và có thể kích hoạt nhiều lần tạo tài nguyên.

**Nuốt lỗi trong reactive chain.** Không dùng onErrorResume để biến mọi lỗi thành response thành công hoặc Mono.empty(). Hãy ánh xạ lỗi có chủ đích và giữ correlation ID.

**Dùng parameters làm dữ liệu tin cậy.** Request có thể chứa giá trị vượt giới hạn hoặc trường không được hỗ trợ. Luôn validate ở broker và chỉ gửi allowlist đến provider.

**Không xử lý kết quả provider không xác định.** Timeout không chứng minh thao tác tạo đã thất bại. Cần tra cứu theo external reference hoặc idempotency key trước khi retry.

## 13. Kết nối với các thao tác vòng đời khác

createServiceInstance() tạo nền tảng trạng thái mà các thao tác sau sẽ sử dụng. Bind cần kiểm tra instance đã provision thành công. Update cần đọc plan hiện tại, operation và khả năng chuyển đổi. Deprovision cần biết providerResourceId và binding còn tồn tại hay không. Last operation cần truy vấn operation record được tạo trong quá trình provision.

Vì vậy, nên dùng chung mô hình ServiceInstance, Operation và ProviderResource cho các handler trong ServiceInstanceService. Mỗi handler cập nhật state machine theo quy tắc rõ ràng và không tự tạo một nguồn trạng thái riêng.

Khi tài nguyên được cấp phát thành công, broker cần lưu các dữ liệu đủ để thao tác khác tiếp tục: provider resource ID, service/plan đã chọn, thông tin sở hữu, trạng thái, metadata không nhạy cảm và tham chiếu đến secret được quản lý riêng.

## 14. Tổng kết triển khai

Một createServiceInstance() tốt thực hiện đúng hợp đồng OSB API và tạo ra một quy trình cấp phát có thể phục hồi. Handler xác thực service, plan, parameters và context; dùng instanceId để bảo đảm idempotency; ghi trạng thái và operation trước khi gọi provider; gọi adapter với khóa ổn định; rồi trả response đồng bộ hoặc bất đồng bộ phù hợp với khả năng của client.

Trong Spring Cloud Open Service Broker, hãy giữ handler tập trung vào điều phối, đưa logic provider vào adapter, lưu trạng thái bền vững và dùng outbox/worker cho thao tác dài. Kiểm thử cả request lặp, request đồng thời, provider timeout, broker restart và lỗi bảo mật. Cách triển khai này giúp nền tảng có thể yêu cầu cấp phát service instance một cách nhất quán, kể cả khi mạng hoặc hệ thống nhà cung cấp gặp sự cố.

