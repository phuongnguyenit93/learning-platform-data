# Cài đặt createServiceInstanceBinding() trong ServiceInstanceBindingService

Trong Open Service Broker API (OSB API), binding là thao tác cấp thông tin truy cập để một ứng dụng hoặc consumer sử dụng service instance đã được provision. Với Spring Cloud Open Service Broker, handler triển khai thao tác này thông qua phương thức createServiceInstanceBinding() trong ServiceInstanceBindingService.

Ví dụ, một ứng dụng đặt hàng đã có PostgreSQL instance. Khi nền tảng yêu cầu bind, broker có thể tạo một database role riêng cho ứng dụng, sinh password, giới hạn quyền trên database và trả về thông tin kết nối. Ứng dụng dùng credentials đó để kết nối đến database. Khi binding bị hủy, broker phải thu hồi quyền tương ứng ở nhà cung cấp.

Trong module **SPRING_CLOUD_SERVICE_BROKER**, binding là ranh giới bảo mật quan trọng giữa service instance và consumer. Handler cần xác thực instance, service, plan và yêu cầu bind; kiểm tra chính sách truy cập; xử lý request lặp; tạo credentials an toàn; lưu metadata binding; và trả response đúng hợp đồng OSB API. Bài học này trình bày luồng xử lý, thiết kế dữ liệu, ví dụ Java reactive, bảo mật credentials, idempotency, tích hợp provider và kiểm thử.

## 1. Binding nằm ở đâu trong vòng đời service?

Provision tạo service instance, chẳng hạn một database hoặc một queue. Binding cấp quyền sử dụng instance đó cho một consumer cụ thể. Hai thao tác có mục đích khác nhau:

| Thao tác | Đối tượng tạo/quản lý | Kết quả |
|---|---|---|
| Provision | Service instance | Tài nguyên dịch vụ được tạo |
| Bind | Service binding | Thông tin kết nối và quyền truy cập cho consumer |
| Unbind | Một binding cụ thể | Quyền truy cập của consumer bị thu hồi |
| Deprovision | Service instance và tài nguyên của nó | Tài nguyên dịch vụ được thu hồi |

Một instance có thể có nhiều binding. Ví dụ, PostgreSQL instance dùng chung cho ứng dụng nhưng có các database role khác nhau cho order-service, reporting-service và migration-job. Mỗi binding nên có định danh riêng và quyền tối thiểu phù hợp với consumer đó.

Không nên trả một tài khoản quản trị chung cho mọi ứng dụng. Khi một consumer bị gỡ bỏ, broker cần thu hồi đúng binding của consumer đó mà không làm gián đoạn các consumer còn lại.

## 2. Request create binding theo OSB API

OSB API v2 sử dụng endpoint có dạng:

~~~http
PUT /v2/service_instances/{instance_id}/service_bindings/{binding_id}
Content-Type: application/json
Accept: application/json
~~~

Ví dụ request:

~~~json
{
  "service_id": "postgres-service",
  "plan_id": "postgres-standard-v1",
  "app_guid": "app-orders-123",
  "bind_resource": {
    "app_guid": "app-orders-123"
  },
  "parameters": {
    "database_name": "orders",
    "role": "application"
  },
  "context": {
    "platform": "cloud-foundry",
    "organization_guid": "org-commerce",
    "space_guid": "space-production"
  }
}
~~~

Các dữ liệu chính:

| Trường | Ý nghĩa | Cách handler sử dụng |
|---|---|---|
| instance_id | ID service instance trong URL | Tìm tài nguyên đã provision |
| binding_id | ID binding do nền tảng cung cấp | Khóa idempotency và định danh quyền truy cập |
| service_id | ID service trong catalog | Đối chiếu với service của instance |
| plan_id | ID plan được gửi trong request | Đối chiếu với plan và chính sách bind |
| app_guid | Định danh ứng dụng nếu binding gắn với app | Xác định consumer |
| bind_resource | Metadata về tài nguyên consumer theo OSB API | Xác định loại binding và thông tin liên quan |
| parameters | Tham số riêng cho binding | Chọn database/schema/role hoặc quyền được cấp |
| context | Ngữ cảnh nền tảng | Áp dụng chính sách tích hợp theo nền tảng |

Một số loại binding không gắn trực tiếp với application, vì vậy không nên mặc định app_guid luôn có giá trị. Broker cần xác định kiểu binding mà service hỗ trợ và xác thực các trường bắt buộc theo hợp đồng của phiên bản OSB API.

Request body là dữ liệu đầu vào, không phải bằng chứng rằng consumer có quyền truy cập. Broker cần xác thực request đến từ nền tảng đáng tin cậy và áp dụng chính sách tenant, organization, space hoặc consumer tương ứng.

## 3. ServiceInstanceBindingService đảm nhiệm phần nào?

Spring Cloud Open Service Broker cung cấp abstraction ServiceInstanceBindingService để ứng dụng triển khai logic tạo binding. Handler nhận CreateServiceInstanceBindingRequest và trả về CreateServiceInstanceBindingResponse theo API reactive của phiên bản framework tương ứng.

Handler nên điều phối nghiệp vụ binding, còn việc giao tiếp với nhà cung cấp nên nằm trong adapter riêng.

Một cách phân chia trách nhiệm:

| Thành phần | Trách nhiệm |
|---|---|
| ServiceInstanceBindingService implementation | Điều phối yêu cầu bind và tạo response OSB |
| ServiceInstanceRepository | Đọc trạng thái instance và provider resource ID |
| Catalog/Plan registry | Xác định service, plan và capability đã công bố |
| BindingPolicy | Kiểm tra consumer, loại binding và quyền được cấp |
| BindingRepository | Lưu metadata và trạng thái binding |
| CredentialService | Sinh, mã hóa, lưu hoặc truy xuất credentials |
| Provider adapter | Tạo user, role, token, vhost hoặc quyền truy cập ở provider |
| Idempotency component | Nhận diện binding đã tồn tại và xử lý request lặp |
| Secret manager | Bảo vệ credentials và tham chiếu secret |

Một handler rõ ràng giúp thay đổi cách tạo user của PostgreSQL hoặc RabbitMQ mà không làm thay đổi hợp đồng OSB API.

## 4. Kiểm tra instance trước khi tạo binding

Binding chỉ được tạo khi service instance đã provision thành công và ở trạng thái cho phép sử dụng.

Các điều kiện cần kiểm tra:

1. Instance ID tồn tại trong kho dữ liệu broker.
2. Instance thuộc đúng service và plan được gửi trong request.
3. Instance đang ở trạng thái sẵn sàng, không provisioning, deprovisioning hoặc failed.
4. Service được công bố là bindable.
5. Plan và provider hỗ trợ loại binding được yêu cầu.
6. Consumer hoặc app context hợp lệ theo chính sách nền tảng.
7. Instance chưa vượt giới hạn số binding nếu service có quota này.
8. Không có operation khác đang thu hồi hoặc thay đổi quyền truy cập theo cách xung đột.

Catalog có trường bindable để công bố khả năng binding của service. Nếu bindable là false, broker không được nhận binding như một khả năng đã công bố. Nếu bindable là true, broker vẫn phải kiểm tra trạng thái instance, loại consumer và giới hạn cụ thể.

Không nên chỉ dựa vào việc service có endpoint kết nối. Một URL database không tạo ra quyền truy cập an toàn. Binding thường phải tạo credential hoặc cấp quyền riêng, có khả năng thu hồi và có thể đối soát.

## 5. Xác thực bind parameters và bind_resource

Tham số binding có thể dùng để chọn database, schema, role, quyền truy cập hoặc loại endpoint. Broker cần xác thực theo schema của plan và policy riêng của service.

Ví dụ các tham số được phép:

~~~json
{
  "database_name": "orders",
  "role": "read-write",
  "connection_limit": 20
}
~~~

Broker cần kiểm tra:

- database_name có hợp lệ và thuộc instance này không.
- role có nằm trong allowlist như read-only hoặc read-write không.
- connection_limit có nằm trong giới hạn của plan không.
- Consumer có được phép nhận loại quyền đó không.
- Parameters có chứa trường không được hỗ trợ hoặc trường có thể thay đổi quyền quản trị không.

Không nối trực tiếp parameters vào câu lệnh SQL hoặc shell command. Tên database và role cần được kiểm tra định dạng, escape đúng theo API provider hoặc bind qua cơ chế parameterized query phù hợp.

bind_resource chứa thông tin mô tả consumer. Tùy kiểu binding và nền tảng, broker có thể cần app_guid hoặc metadata khác. Chỉ dùng những trường đã được OSB API định nghĩa và nền tảng tin cậy cung cấp; không xem giá trị trong context là quyền hạn đã xác minh.

## 6. Thiết kế dữ liệu ServiceBinding

Broker cần lưu metadata binding để xử lý retry, unbind và đối soát. Không nên chỉ trả credentials rồi quên binding đã tạo.

Một bản ghi binding có thể chứa:

| Thuộc tính | Mục đích |
|---|---|
| bindingId | ID do nền tảng gửi |
| instanceId | Service instance được bind |
| serviceId, planId | Service và plan của instance |
| appGuid | Consumer nếu binding gắn với ứng dụng |
| bindResource | Metadata consumer đã chuẩn hóa |
| parametersFingerprint | Dấu vân tay parameters để phát hiện retry xung đột |
| providerBindingId | ID user/role/resource ở provider |
| credentialSecretRef | Tham chiếu đến secret được quản lý riêng |
| state | CREATING, SUCCEEDED, REVOKING hoặc REVOKED |
| createdAt, updatedAt | Thời điểm tạo và cập nhật |
| lastErrorCode | Mã lỗi an toàn để đối soát |

Định danh binding thường cần duy nhất trong phạm vi instance. Có thể dùng unique constraint trên cặp instanceId và bindingId.

Không nên lưu password plaintext trong bảng binding. Nếu broker cần trả lại cùng credentials khi nhận request lặp, có thể lưu secret được mã hóa bằng cơ chế quản lý khóa hoặc lưu tham chiếu đến secret manager có quyền truy xuất phù hợp. Chỉ lưu hash password là không đủ nếu broker cần trả lại password ban đầu trong response retry.

Metadata binding và secret nên có vòng đời riêng. Khi unbind thành công, xóa hoặc vô hiệu hóa secret theo chính sách và giữ metadata tối thiểu cần thiết để nhận diện retry hoặc audit.

## 7. Idempotency khi cùng binding được gửi lại

Nền tảng có thể retry request bind khi timeout hoặc mất response. Nếu mỗi lần retry broker tạo một database user mới, một binding ID có thể sinh ra nhiều credential và quyền truy cập ngoài ý muốn.

Broker nên tạo fingerprint từ dữ liệu có ảnh hưởng đến binding:

- instanceId và bindingId.
- serviceId và planId.
- appGuid hoặc consumer identity.
- bind_resource đã chuẩn hóa.
- parameters đã chuẩn hóa.

Quy tắc xử lý:

| Trạng thái binding | Request lặp cùng fingerprint | Request cùng ID nhưng fingerprint khác |
|---|---|---|
| Chưa tồn tại | Reserve và bắt đầu tạo | Không áp dụng |
| CREATING | Trả trạng thái đang xử lý theo chính sách handler | Từ chối xung đột |
| SUCCEEDED | Trả lại kết quả binding đã lưu và credentials có thể truy xuất an toàn | Từ chối xung đột |
| FAILED | Reconcile trước khi thử lại hoặc retry có kiểm soát | Từ chối xung đột |
| REVOKING/REVOKED | Không tự tạo lại quyền; xử lý theo quy tắc vòng đời | Từ chối hoặc yêu cầu binding ID mới |

Dùng unique constraint để giải quyết race condition. Hai request đồng thời có thể cùng thấy binding chưa tồn tại; chỉ một request được phép reserve ID. Request còn lại đọc bản ghi đã tồn tại và so sánh fingerprint.

Nếu provider hỗ trợ idempotency key, dùng khóa ổn định dựa trên instanceId và bindingId. Nếu provider không hỗ trợ, adapter cần tra cứu user hoặc resource theo external reference trước khi tạo lại.

Không thể bảo đảm exactly-once giữa broker và provider chỉ bằng transaction database. Thiết kế phải chịu được retry, lưu kết quả từng bước và có reconciliation khi response provider bị mất.

## 8. Tạo credentials và quyền tối thiểu

Đối với database, binding có thể tạo một user riêng cho ứng dụng. Đối với RabbitMQ, binding có thể tạo user và giới hạn quyền trên vhost hoặc exchange/queue. Đối với object storage, binding có thể cấp access key hoặc token giới hạn bucket và hành động.

Credentials nên tuân theo nguyên tắc least privilege:

- Tạo một danh tính riêng cho từng binding khi provider hỗ trợ.
- Chỉ cấp quyền đọc, ghi hoặc quản trị cần thiết cho use case.
- Giới hạn database, schema, table, bucket, vhost hoặc resource scope.
- Đặt thời hạn hoặc chính sách xoay vòng nếu phù hợp.
- Không dùng tài khoản quản trị provider làm credentials của ứng dụng.
- Thu hồi đúng danh tính khi unbind.
- Không tái sử dụng credential của binding này cho binding khác.

Password hoặc token cần được sinh bằng bộ sinh số ngẫu nhiên mật mã an toàn. Không dùng thời gian hiện tại, instance ID, binding ID hoặc UUID thông thường làm password.

Nếu provider tự sinh credentials, broker nên lấy secret qua kênh được bảo vệ và lưu vào secret manager. Nếu broker tự sinh, cần bảo đảm provider nhận được secret một cách an toàn và broker có thể trả response theo hợp đồng.

Ví dụ response binding cho PostgreSQL:

~~~json
{
  "credentials": {
    "uri": "postgres://orders_app:secret-value@db.example.internal:5432/orders",
    "username": "orders_app",
    "password": "secret-value",
    "host": "db.example.internal",
    "port": 5432,
    "database": "orders"
  }
}
~~~

Đây là response minh họa. Trường credentials là dữ liệu do broker định nghĩa theo hợp đồng của service. Không đưa password mẫu hoặc giá trị thật vào log, tài liệu public hay metric label.

## 9. Tạo binding bằng provider adapter

Provider adapter nhận một command nội bộ đã xác thực, thay vì phụ thuộc trực tiếp vào CreateServiceInstanceBindingRequest trong mọi lớp.

Ví dụ model:

~~~java
public record CreateBindingCommand(
    String instanceId,
    String bindingId,
    String providerResourceId,
    String consumerId,
    String databaseName,
    String role,
    String idempotencyKey
) {}
~~~

Adapter có thể cung cấp phương thức reactive:

~~~java
public interface DatabaseBindingProvider {

    Mono<ProviderBinding> createBinding(
        CreateBindingCommand command);

    Mono<Void> revokeBinding(
        String providerBindingId,
        String idempotencyKey);
}
~~~

Kết quả provider có thể gồm providerBindingId, username, endpoint và tham chiếu secret. Nếu provider chỉ trả secret một lần, adapter cần chuyển secret vào kho bảo mật trước khi hoàn tất và trả kết quả cho tầng điều phối.

Không để adapter log request hoặc response nguyên vẹn nếu chúng chứa password, token hoặc access key.

## 10. Ví dụ triển khai createServiceInstanceBinding()

Đoạn mã dưới đây minh họa cấu trúc reactive của handler trong Spring Cloud Open Service Broker. Chữ ký interface, accessor của request và builder của response cần được xác minh theo phiên bản dependency thực tế. Các repository, policy và coordinator là abstraction do ứng dụng định nghĩa.

~~~java
@Service
public class DatabaseServiceInstanceBindingService
        implements ServiceInstanceBindingService {

    private final ServiceInstanceRepository instances;
    private final BindingPolicy bindingPolicy;
    private final BindingCoordinator coordinator;

    public DatabaseServiceInstanceBindingService(
            ServiceInstanceRepository instances,
            BindingPolicy bindingPolicy,
            BindingCoordinator coordinator) {
        this.instances = instances;
        this.bindingPolicy = bindingPolicy;
        this.coordinator = coordinator;
    }

    @Override
    public Mono<CreateServiceInstanceBindingResponse>
            createServiceInstanceBinding(
                CreateServiceInstanceBindingRequest request) {

        return Mono.defer(() ->
            instances.findById(request.getServiceInstanceId())
                .switchIfEmpty(Mono.error(
                    new ServiceInstanceNotFoundException()))
                .flatMap(instance ->
                    bindingPolicy.validate(instance, request)
                        .then(coordinator.create(instance, request))
                )
                .map(result ->
                    CreateServiceInstanceBindingResponse.builder()
                        .credentials(result.credentials())
                        .build()
                )
        );
    }
}
~~~

Đây là skeleton định hướng. Tên getter và builder method có thể khác theo phiên bản framework; cần đối chiếu Javadoc hoặc source của dependency đang dùng trước khi chép vào dự án. Ví dụ cũng lược bỏ ánh xạ các response field tùy chọn như syslog drain, route service hoặc volume mount vì chỉ áp dụng cho loại service tương ứng.

Handler trả về Mono cho framework quản lý subscription. Không gọi subscribe() bên trong phương thức để tự chạy công việc nền; việc đó có thể tách lỗi khỏi request và làm mất khả năng quản lý vòng đời reactive.

### Coordinator điều phối tạo binding

Coordinator có thể thực hiện theo thứ tự:

1. Chuẩn hóa request và tạo fingerprint.
2. Reserve binding ID bằng unique constraint.
3. Nếu binding đã tồn tại, kiểm tra fingerprint và trả kết quả hiện có.
4. Tạo provider binding với idempotency key ổn định.
5. Lưu providerBindingId và tham chiếu secret.
6. Chuyển trạng thái binding thành SUCCEEDED.
7. Tạo response chứa credentials cần thiết.

Một skeleton khái niệm:

~~~java
public Mono<BindingResult> create(
        ServiceInstance instance,
        CreateServiceInstanceBindingRequest request) {

    BindingCommand command = commandFactory.from(instance, request);

    return bindingRepository.reserve(command)
        .flatMap(reservation -> {
            if (reservation.isExisting()) {
                return bindingRepository.loadResult(
                    reservation.bindingId());
            }

            return provider.createBinding(command)
                .flatMap(providerBinding ->
                    secretStore.store(
                            command.bindingId(),
                            providerBinding.credentials())
                        .flatMap(secretRef ->
                            bindingRepository.markSucceeded(
                                reservation,
                                providerBinding.providerBindingId(),
                                secretRef)
                        )
                        .thenReturn(
                            resultFactory.from(providerBinding))
                )
                .onErrorResume(error ->
                    bindingRepository.markFailure(
                            reservation, safeErrorCode(error))
                        .then(Mono.error(error)));
        });
}
~~~

Đây là pseudocode: kiểu reservation, repository và provider thuộc ứng dụng. Trong triển khai thật, cần xác định rõ hành vi nếu provider tạo user thành công nhưng việc lưu secret hoặc cập nhật database thất bại. Khi đó phải tra cứu providerBindingId bằng external reference, tiếp tục lưu kết quả hoặc thu hồi tài nguyên vừa tạo theo quy trình bù trừ.

Không giữ transaction database mở trong suốt lời gọi provider. Có thể dùng transaction ngắn để reserve binding và ghi outbox khi cần điều phối nhiều bước; binding OSB thường được xử lý đồng bộ theo hợp đồng. Nếu không thể hoàn tất binding trong thời gian request và phiên bản giao thức không hỗ trợ binding bất đồng bộ cho trường hợp đó, broker cần trả lỗi phù hợp thay vì tự ý trả response async không đúng hợp đồng.

## 11. Response binding và các kiểu thông tin truy cập

Response chuẩn của thao tác bind có thể chứa credentials và một số trường dành cho loại dịch vụ cụ thể theo phiên bản OSB API:

| Trường response | Mục đích | Ví dụ sử dụng |
|---|---|---|
| credentials | Thông tin xác thực và kết nối do service định nghĩa | URI, username, password, token |
| syslog_drain_url | Endpoint nhận log nếu service hỗ trợ syslog drain | URL collector |
| route_service_url | Endpoint route service nếu service cung cấp khả năng đó | URL proxy |
| volume_mounts | Mô tả volume mount nếu service hỗ trợ | Driver, container directory, mode |

Không phải service nào cũng cần các trường này. Database thông thường có thể chỉ trả credentials. Một service cung cấp volume có thể cần volume_mounts. Broker chỉ nên trả trường mà service và nền tảng thực sự hỗ trợ.

Credentials là object do broker định nghĩa. Có thể bao gồm URI, host, port, username, password, database, token hoặc thông tin TLS. Cần giữ schema ổn định để ứng dụng consumer không bị lỗi khi broker thay đổi tên trường.

Không nên trả secret tham chiếu nội bộ, provider admin token hoặc thông tin tài khoản quản trị. Response chỉ nên chứa dữ liệu consumer cần để sử dụng service.

## 12. Bảo mật credentials trong toàn bộ vòng đời binding

Credentials là dữ liệu nhạy cảm. Bảo vệ chỉ ở thời điểm trả response là chưa đủ; broker phải kiểm soát từ lúc sinh, lưu, truyền đến lúc thu hồi.

### Khi tạo

- Dùng bộ sinh ngẫu nhiên mật mã an toàn.
- Giới hạn quyền của user hoặc token mới.
- Dùng TLS khi gọi provider và khi nền tảng gọi broker.
- Lưu secret trong secret manager hoặc dạng mã hóa có kiểm soát.
- Không ghi request/response có secret vào log.
- Không đưa secret vào exception message, trace attribute hoặc metric.

### Khi lưu và truy xuất

- Mã hóa secret khi lưu và kiểm soát quyền giải mã.
- Tách secret khỏi metadata binding.
- Giới hạn service account có thể đọc secret.
- Kiểm tra tenant và binding ownership trước khi truy xuất.
- Có audit event cho thao tác đọc hoặc export secret.
- Xác định cách trả lại credentials khi request bind được retry.

### Khi thu hồi

- Gọi provider để revoke user, token hoặc permission.
- Xác nhận provider đã vô hiệu hóa quyền nếu API hỗ trợ.
- Xóa hoặc disable secret trong secret manager.
- Đánh dấu binding REVOKED và lưu metadata tối thiểu.
- Không để một credential cũ tiếp tục truy cập do chỉ xóa bản ghi broker.

Nếu provider hỗ trợ rotation, có thể xây dựng quy trình xoay vòng credentials riêng. Việc rotation cần phối hợp cập nhật secret ở consumer hoặc nền tảng để tránh gián đoạn kết nối.

## 13. Xử lý lỗi và kết quả provider không xác định

Binding thường là thao tác đồng bộ, nhưng vẫn có thể gặp timeout, rate limit hoặc lỗi khi tạo user ở provider.

| Loại lỗi | Ví dụ | Cách xử lý |
|---|---|---|
| Instance không tồn tại | instance_id không có trong broker | Từ chối, không gọi provider |
| Instance chưa sẵn sàng | Provisioning hoặc deprovisioning | Từ chối theo trạng thái |
| Service không bindable | Capability không được công bố | Không tạo binding |
| Parameters sai | Role không nằm trong allowlist | Từ chối request |
| Binding ID xung đột | Cùng ID nhưng consumer/parameters khác | Trả lỗi xung đột |
| Provider từ chối | Không đủ quyền tạo user | Ánh xạ lỗi an toàn |
| Provider rate limit | Quá nhiều yêu cầu tạo binding | Retry có giới hạn theo policy |
| Provider timeout | Không rõ user đã được tạo chưa | Reconcile trước khi tạo lại |
| Secret store lỗi | Provider đã tạo credential nhưng chưa lưu secret | Khôi phục kết quả hoặc revoke binding bù trừ |
| Database lỗi sau provider | Provider tạo binding nhưng broker chưa ghi thành công | Tra cứu external reference và reconcile |

Không trả stack trace hoặc thông tin provider nhạy cảm cho nền tảng. Log nên có instanceId, bindingId, correlation ID và mã lỗi đã làm sạch.

Nếu provider timeout sau khi nhận lệnh tạo user, không được mặc định user chưa tồn tại. Tra cứu bằng tên hoặc external reference ổn định trước khi retry. Nếu không thể xác định, giữ binding ở trạng thái cần reconciliation và cảnh báo vận hành.

## 14. Unbind phải thu hồi đúng quyền của binding

Tạo binding và thu hồi binding phải dùng chung định danh. Khi nền tảng gửi unbind, broker tra cứu binding theo instanceId và bindingId, sau đó thu hồi đúng providerBindingId.

Một luồng unbind có thể gồm:

1. Đọc binding và kiểm tra quan hệ với service instance.
2. Chuyển binding sang trạng thái REVOKING.
3. Gọi provider adapter để disable hoặc xóa user/token/role.
4. Xác nhận quyền truy cập đã bị thu hồi.
5. Xóa hoặc disable secret trong secret manager.
6. Đánh dấu binding REVOKED và giữ tombstone cần thiết.

Nếu unbind được gửi lại, broker cần trả kết quả idempotent theo hợp đồng. Không được xóa quyền của binding khác chỉ vì username hoặc tên role trùng nhau. Provider resource ID cần được gắn với binding cụ thể.

Khi deprovision instance, broker cũng cần đối soát các binding còn tồn tại. Thông thường nền tảng yêu cầu unbind trước, nhưng broker vẫn phải bảo vệ khỏi trạng thái không nhất quán hoặc request đến sai thứ tự.

## 15. Kiểm thử createServiceInstanceBinding()

Kiểm thử cần xác nhận cả response OSB và side effect tại provider:

| Trường hợp | Kết quả mong đợi |
|---|---|
| Instance đã provision và bindable | Tạo binding thành công |
| Instance không tồn tại | Từ chối, provider không được gọi |
| Instance đang provisioning | Từ chối theo policy |
| Service không bindable | Không tạo credential |
| Parameters hợp lệ | Provider tạo đúng quyền |
| Parameters chứa role không hợp lệ | Từ chối trước side effect |
| Request bind lặp cùng fingerprint | Trả cùng binding và credentials có thể truy xuất an toàn |
| Cùng binding ID nhưng fingerprint khác | Từ chối xung đột |
| Hai request đồng thời | Chỉ một binding được reserve |
| Provider timeout | Reconcile trước khi tạo lại |
| Secret store lỗi sau khi provider thành công | Có thể khôi phục hoặc revoke bù trừ |
| Unbind | Credential và quyền provider bị thu hồi |
| Binding của consumer A bị unbind | Binding của consumer B vẫn hoạt động |
| Log và trace | Không chứa password hoặc token |

Nên dùng provider test double để kiểm soát response, timeout và lỗi. Kiểm tra số lần tạo user, số binding record, secret reference, quyền provider và nội dung response. Với database thật, có thể kiểm tra role chỉ có quyền đúng scope thay vì chỉ kiểm tra user đã tồn tại.

Với Reactor, tránh gọi block() trong đường xử lý reactive. Nếu SDK provider chỉ có API blocking, cô lập nó trong adapter và chạy trên scheduler dành cho blocking I/O. Không để lời gọi blocking chiếm event-loop thread.

## 16. Những lỗi triển khai thường gặp

**Dùng chung một tài khoản quản trị cho mọi ứng dụng.** Khi một ứng dụng bị xâm nhập hoặc unbind, broker không thể thu hồi riêng quyền của consumer đó. Hãy tạo principal riêng cho từng binding nếu provider hỗ trợ.

**Tạo credentials trước khi reserve binding ID.** Hai request đồng thời có thể tạo hai user cho cùng một binding. Reserve ID bằng unique constraint trước khi thực hiện side effect.

**Chỉ lưu hash password rồi kỳ vọng trả lại credentials khi retry.** Hash không thể khôi phục password. Nếu cần trả lại cùng secret, hãy lưu secret mã hóa hoặc trong secret manager có quyền truy xuất phù hợp.

**Coi timeout là provider chưa tạo user.** Provider có thể đã hoàn tất nhưng response bị mất. Tra cứu external reference và reconcile trước khi tạo lại.

**Lưu password plaintext trong bảng binding.** Điều này làm tăng phạm vi dữ liệu nhạy cảm. Dùng secret manager hoặc mã hóa có quản lý khóa và lưu tham chiếu trong metadata.

**Xóa secret mà không revoke quyền ở provider.** Consumer vẫn có thể dùng credential đã biết. Phải vô hiệu hóa quyền tại nguồn và xác nhận kết quả.

**Trả credentials của binding khác khi ID bị xung đột.** Luôn so sánh fingerprint và ownership trước khi trả kết quả hiện có.

**Gọi subscribe() trong handler reactive.** Framework không còn kiểm soát đầy đủ vòng đời và lỗi. Trả Mono để framework quản lý.

## 17. Nguyên tắc triển khai trong Spring Cloud Service Broker

Trong ứng dụng Spring Cloud Open Service Broker, createServiceInstanceBinding() nên là điểm điều phối giữa hợp đồng OSB và nghiệp vụ cấp quyền của provider. Handler đọc instance, xác thực service/plan và consumer, kiểm tra capability, sau đó gọi BindingCoordinator. Coordinator reserve binding ID, xử lý idempotency, gọi provider adapter, lưu secret an toàn và tạo response.

Mỗi binding cần có định danh riêng, trạng thái bền vững và liên kết đến provider resource. Credentials chỉ được trả cho consumer tương ứng và phải có khả năng thu hồi khi unbind. Khi retry, broker cần trả lại đúng kết quả đã tạo mà không sinh thêm user hoặc token. Khi provider timeout, cần reconciliation trước khi thử lại.

Hãy kiểm thử cả đường tạo, retry, xung đột, provider timeout, secret store failure và unbind. Việc triển khai đúng createServiceInstanceBinding() giúp mỗi ứng dụng nhận quyền truy cập tối thiểu cần thiết, có thể truy vết và thu hồi độc lập trong toàn bộ vòng đời service instance.

