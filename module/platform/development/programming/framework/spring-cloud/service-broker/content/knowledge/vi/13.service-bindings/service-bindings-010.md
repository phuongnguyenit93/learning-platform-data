# Tạo binding đồng bộ, bất đồng bộ và phản hồi yêu cầu tạo lặp

Trong Open Service Broker API (OSB API), thao tác binding cấp thông tin kết nối và quyền truy cập để một consumer sử dụng service instance đã được provision. Nền tảng gửi yêu cầu tạo binding đến broker, broker tạo hoặc xác định danh tính truy cập ở nhà cung cấp rồi trả credentials cho consumer.

Khi triển khai bằng Spring Cloud Open Service Broker, cần phân biệt hai khái niệm: **cách xử lý bên trong ứng dụng** và **hợp đồng phản hồi của OSB API**. Handler có thể dùng Reactor, gọi provider bằng I/O bất đồng bộ, phối hợp nhiều bước hoặc chờ một provider operation. Tuy nhiên, thao tác tạo binding theo hợp đồng OSB API thông thường phải trả kết quả binding hoàn chỉnh trong request hiện tại; không thể tùy tiện trả một response chấp nhận bất đồng bộ rồi yêu cầu nền tảng gọi last operation như đối với provision, update hoặc deprovision.

Bài học này trình bày cách tạo binding đồng bộ, tổ chức công việc bất đồng bộ ở bên trong broker, xử lý timeout và request lặp, đồng thời bảo đảm cùng một binding ID không tạo ra nhiều credentials hoặc quyền truy cập ngoài ý muốn.

## 1. Luồng tạo binding và hợp đồng phản hồi

Sau khi provision thành công, service instance có thể được nhiều consumer sử dụng. Mỗi consumer cần một binding riêng để broker cấp đúng quyền truy cập và có thể thu hồi độc lập.

Ví dụ, một PostgreSQL instance phục vụ ba ứng dụng. Broker tạo các role riêng cho order-service, reporting-service và migration-job. Mỗi role có quyền khác nhau; khi reporting-service bị gỡ, broker chỉ thu hồi binding của ứng dụng đó.

OSB API v2 dùng endpoint:

~~~http
PUT /v2/service_instances/{instance_id}/service_bindings/{binding_id}
Content-Type: application/json
Accept: application/json
~~~

Request minh họa:

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
    "role": "read-write"
  },
  "context": {
    "platform": "cloud-foundry",
    "organization_guid": "org-commerce",
    "space_guid": "space-production"
  }
}
~~~

Broker đọc instance theo instance_id, xác thực service và plan, kiểm tra consumer cùng parameters, sau đó tạo quyền truy cập ở provider. Response chứa credentials hoặc các trường binding phù hợp với loại dịch vụ.

Với lần tạo đầu tiên thành công, broker trả response tạo binding theo OSB API, thông thường là HTTP 201 Created. Khi cùng binding đã tồn tại và request lặp có cùng ý nghĩa, broker trả HTTP 200 OK cùng kết quả binding ban đầu. Nếu binding_id đã được dùng cho một yêu cầu có parameters hoặc consumer không tương thích, broker trả xung đột HTTP 409 Conflict theo hợp đồng OSB API.

Điểm quan trọng là response lặp phải đại diện cho chính binding đã tạo. Không tạo một user mới hoặc password mới chỉ vì nền tảng gửi lại request sau khi mất response đầu tiên.

## 2. Đồng bộ ở cấp giao thức và bất đồng bộ bên trong ứng dụng

Từ “bất đồng bộ” có thể chỉ hai hành vi khác nhau.

**Bất đồng bộ ở cấp giao thức** nghĩa là broker trả lời rằng thao tác đã được tiếp nhận nhưng chưa hoàn tất, kèm operation identifier để nền tảng truy vấn trạng thái sau đó. OSB API có cơ chế này cho một số thao tác vòng đời như provision, update và deprovision thông qua accepts_incomplete và last_operation.

**Bất đồng bộ ở cấp triển khai** nghĩa là ứng dụng sử dụng I/O non-blocking, Reactor, CompletableFuture, message queue hoặc worker để thực hiện các bước nội bộ. Request HTTP vẫn chỉ hoàn tất khi handler trả về response binding hợp lệ.

Với create binding chuẩn OSB API, hãy giữ hợp đồng phản hồi đồng bộ. Spring handler có thể trả Mono nhưng Mono không tự biến binding thành một thao tác OSB bất đồng bộ. Framework chờ Mono phát ra CreateServiceInstanceBindingResponse hoặc lỗi rồi mới hoàn tất response HTTP.

| Cách xử lý | Ví dụ | Hành vi đối với nền tảng |
|---|---|---|
| Đồng bộ hoàn toàn | Provider tạo user nhanh và trả credentials ngay | Handler trả response khi đã có binding |
| Reactive/non-blocking | Gọi API provider qua WebClient và ghép Mono | Vẫn trả response binding trong request hiện tại |
| Provider có operation riêng | Provider trả operation ID; broker poll hoặc nhận callback nội bộ | Handler chờ đến khi có kết quả binding hoặc lỗi trong giới hạn request |
| Worker nội bộ | Đưa các bước phụ vào queue nhưng handler vẫn chờ bước cần thiết để có credentials | Không trả một response thành công giả khi binding chưa sẵn sàng |
| Extension riêng | Nền tảng và broker thỏa thuận một giao thức khác | Chỉ dùng khi cả hai phía hỗ trợ rõ ràng; không xem là hành vi OSB portable |

Không được lấy mô hình async của provision áp thẳng sang binding. Nếu broker trả 202 Accepted hoặc một operation ID tùy ý cho binding rồi kỳ vọng nền tảng gọi last_operation, nền tảng OSB thông thường có thể không biết phải xử lý response đó như thế nào.

## 3. Các bước trong một binding request

Một quy trình create binding nên được chia thành các bước rõ ràng:

1. Đọc instance và xác nhận trạng thái đã provision thành công.
2. Đối chiếu service_id, plan_id và khả năng bindable.
3. Xác thực app_guid, bind_resource, context và parameters.
4. Chuẩn hóa request và tính fingerprint.
5. Reserve cặp instance_id và binding_id một cách nguyên tử.
6. Nếu binding đã tồn tại, kiểm tra fingerprint và trả lại kết quả hiện có.
7. Nếu là binding mới, gọi provider adapter để tạo principal hoặc quyền truy cập.
8. Lưu provider binding ID và credentials an toàn.
9. Chuyển binding sang trạng thái ACTIVE.
10. Tạo response chứa credentials cần thiết và trả về nền tảng.

Các bước reserve, lưu kết quả và gọi provider phải được thiết kế để chịu được request lặp, request đồng thời và lỗi giữa chừng. Không nên chỉ kiểm tra binding có tồn tại rồi mới tạo user, vì hai request đồng thời có thể cùng vượt qua bước kiểm tra.

## 4. Thiết kế trạng thái và dữ liệu binding

Broker cần lưu trạng thái bền vững để phục hồi sau khi tiến trình khởi động lại. Một model nội bộ có thể gồm:

| Thuộc tính | Mục đích |
|---|---|
| instanceId | Service instance được bind |
| bindingId | Định danh binding do nền tảng gửi |
| serviceId, planId | Service và plan đã được xác thực |
| consumerId | App hoặc consumer tương ứng |
| requestFingerprint | Phát hiện request lặp và xung đột |
| providerBindingId | ID user, role hoặc quyền ở provider |
| credentialSecretRef | Tham chiếu secret trong secret manager |
| state | Trạng thái xử lý nội bộ |
| createdAt, updatedAt | Thời điểm tạo và cập nhật |
| failureCode | Mã lỗi an toàn để đối soát |

Có thể dùng các trạng thái nội bộ sau:

~~~mermaid
stateDiagram-v2
    [*] --> RESERVED
    RESERVED --> CREATING
    CREATING --> ACTIVE
    CREATING --> FAILED
    CREATING --> UNKNOWN
    UNKNOWN --> ACTIVE: reconcile found created binding
    UNKNOWN --> FAILED: reconcile confirms no binding
    FAILED --> CREATING: controlled retry
    ACTIVE --> REVOKING
    REVOKING --> REVOKED
~~~

Đây là state machine của ứng dụng broker, không phải các trạng thái chuẩn bắt buộc trong response OSB API. Nền tảng chỉ nhận kết quả binding cuối cùng hoặc lỗi của request hiện tại; các trạng thái trung gian được broker dùng để điều phối.

Đặt unique constraint trên cặp instanceId và bindingId. Nếu hệ thống quy định binding ID duy nhất trên toàn broker thì có thể dùng constraint rộng hơn, nhưng phải thống nhất với cách nền tảng định danh. Với mô hình phổ biến, khóa tổng hợp theo instance giúp thể hiện đúng phạm vi endpoint.

Không lưu password plaintext trong bảng binding. Lưu credentialSecretRef trỏ đến secret manager hoặc dữ liệu đã mã hóa bằng cơ chế quản lý khóa. Metadata và secret cần có quyền truy cập, audit và vòng đời riêng.

## 5. Idempotency: nhận diện request lặp

Nền tảng có thể retry khi response bị mất, gateway timeout hoặc kết nối bị ngắt. Broker phải nhận ra request lặp và trả lại cùng kết quả.

Tạo fingerprint từ dữ liệu có ảnh hưởng đến binding:

- instanceId và bindingId.
- serviceId và planId.
- consumer identity như appGuid nếu có.
- bind_resource đã chuẩn hóa.
- parameters đã chuẩn hóa.
- context chỉ gồm những thuộc tính thực sự ảnh hưởng đến quyền hoặc cấu hình.

Không đưa trace ID, request timestamp hoặc header thay đổi theo mỗi lần retry vào fingerprint. Nếu có giá trị mặc định, hãy chuẩn hóa trước khi băm để hai request có cùng ý nghĩa tạo ra cùng fingerprint.

Quy tắc xử lý:

| Tình huống | Hành vi |
|---|---|
| Binding chưa tồn tại | Reserve và bắt đầu tạo |
| Binding ACTIVE, fingerprint giống nhau | Trả lại response đã lưu, HTTP 200 |
| Binding ACTIVE, fingerprint khác | Trả HTTP 409 Conflict |
| Binding đang CREATING, fingerprint giống nhau | Tham gia chờ kết quả hiện tại trong giới hạn request; không gọi provider lần hai |
| Binding đang CREATING, fingerprint khác | Trả xung đột; không thay đổi binding đang chạy |
| Binding FAILED | Reconcile rồi mới quyết định retry an toàn |
| Binding REVOKED | Không tự tái kích hoạt quyền cũ; xử lý theo chính sách ID và vòng đời |

Nếu cùng binding ID được gửi với parameters khác, không được ghi đè binding hiện có. Nền tảng cần dùng binding ID mới nếu muốn tạo một binding khác với cấu hình mới.

### Tại sao phải giữ nguyên credentials khi retry?

Giả sử lần đầu provider tạo user db_orders_01 và password P1. Broker đã lưu secret nhưng response bị mất trên đường truyền. Nền tảng gửi lại cùng request.

Nếu broker tạo user mới với password P2, nền tảng có thể nhận P2 trong khi một consumer khác đã nhận P1 hoặc provider vẫn còn user cũ. Kết quả là hai quyền truy cập cùng tồn tại cho một binding ID.

Cách đúng là truy xuất secret đã lưu cho binding hiện tại và trả lại response tương đương với lần đầu. Nếu secret không thể truy xuất, broker cần xử lý lỗi nội bộ và reconciliation; không tự tạo credential mới dưới cùng binding ID.

## 6. Xử lý hai request đồng thời

Kiểm tra tồn tại bằng hai thao tác riêng không bảo đảm an toàn:

~~~text
Request A: SELECT binding -> không có
Request B: SELECT binding -> không có
Request A: CREATE provider user
Request B: CREATE provider user
Request A: INSERT binding
Request B: INSERT binding -> duplicate key
~~~

Dù database cuối cùng chỉ có một bản ghi, provider có thể đã tạo hai user. Do đó phải reserve ID trước khi gọi provider.

Một chiến lược:

1. Mở transaction ngắn.
2. Insert binding ở trạng thái RESERVED với fingerprint.
3. Unique constraint bảo đảm chỉ một request thắng.
4. Commit reservation.
5. Request thắng gọi provider.
6. Request thua đọc bản ghi hiện có và so sánh fingerprint.
7. Nếu cùng fingerprint và đang xử lý, request thua chờ kết quả hiện tại trong thời gian hữu hạn.
8. Nếu đã ACTIVE, request thua lấy secret và trả response lặp.
9. Nếu khác fingerprint, trả 409.

Không giữ database transaction hoặc row lock trong suốt lời gọi HTTP đến provider. Việc đó làm tăng thời gian giữ lock và có thể gây nghẽn khi provider chậm.

Sơ đồ trình tự:

~~~mermaid
sequenceDiagram
    participant P as Platform
    participant A as Broker node A
    participant B as Broker node B
    participant DB as Binding database
    participant S as Provider/Secret manager

    P->>A: PUT binding-123
    P->>B: Retry PUT binding-123
    A->>DB: Reserve ID + fingerprint
    B->>DB: Reserve same ID
    DB-->>A: Reservation created
    DB-->>B: Unique conflict
    B->>DB: Read existing reservation
    DB-->>B: Same fingerprint, CREATING
    A->>S: Create provider principal
    S-->>A: Principal + credentials
    A->>S: Store credentials securely
    S-->>A: Secret reference
    A->>DB: Mark ACTIVE
    DB-->>A: Saved
    A-->>P: 201 + binding response
    B->>DB: Read ACTIVE binding
    B->>S: Retrieve same credentials
    S-->>B: Original credentials
    B-->>P: 200 + equivalent response
~~~

Nếu request B không thể chờ request A hoàn tất trong timeout cho phép, broker có thể trả lỗi tạm thời để nền tảng retry cùng binding ID. Không trả response thành công khi credentials chưa sẵn sàng và không bắt đầu lần tạo provider thứ hai.

## 7. Triển khai đồng bộ bằng Spring Cloud Open Service Broker

Spring Cloud Open Service Broker cung cấp ServiceInstanceBindingService để xử lý yêu cầu tạo binding. Handler thường trả Mono<CreateServiceInstanceBindingResponse>. Mono là kiểu reactive; framework sẽ đợi publisher hoàn tất để tạo response HTTP.

Một skeleton minh họa:

~~~java
@Service
public class DatabaseBindingService
        implements ServiceInstanceBindingService {

    private final BindingCoordinator coordinator;

    public DatabaseBindingService(BindingCoordinator coordinator) {
        this.coordinator = coordinator;
    }

    @Override
    public Mono<CreateServiceInstanceBindingResponse>
            createServiceInstanceBinding(
                CreateServiceInstanceBindingRequest request) {

        return Mono.defer(() -> coordinator.create(request))
            .map(result ->
                CreateServiceInstanceBindingResponse.builder()
                    .credentials(result.credentials())
                    .build()
            );
    }
}
~~~

Đây là skeleton định hướng. Chữ ký interface, accessor của request và builder response cần đối chiếu đúng phiên bản Spring Cloud Open Service Broker trong dự án. BindingCoordinator, BindingResult và các repository là abstraction do ứng dụng định nghĩa.

Handler không nên chứa SQL, logic sinh password, lệnh tạo database role hoặc xử lý retry phức tạp. Những việc đó thuộc coordinator và provider adapter.

Không gọi subscribe() bên trong handler. Khi tự subscribe, handler có thể trả response trước khi công việc hoàn tất, lỗi bị tách khỏi request và framework mất quyền quản lý vòng đời reactive. Hãy trả Mono để framework thực thi chuỗi xử lý.

## 8. Tổ chức I/O bất đồng bộ bên trong binding

Provider adapter có thể dùng WebClient hoặc SDK reactive để thực hiện I/O không chặn. Ví dụ:

~~~java
public Mono<ProviderBinding> createPrincipal(
        CreateBindingCommand command) {

    return webClient.post()
        .uri("/resources/{resourceId}/bindings",
             command.providerResourceId())
        .header("Idempotency-Key", command.idempotencyKey())
        .bodyValue(command.toProviderRequest())
        .retrieve()
        .bodyToMono(ProviderBinding.class)
        .timeout(Duration.ofSeconds(8));
}
~~~

Ví dụ trên minh họa WebClient; endpoint, header và response là API giả định của provider. Timeout cần dựa trên SLA và ngân sách thời gian của request, không nên sao chép con số minh họa vào production.

Nếu SDK provider chỉ có API blocking, cô lập lời gọi đó trong adapter và chạy trên scheduler dành cho blocking I/O. Không gọi block() trên event-loop thread. Nếu có nhiều bước I/O, ghép chúng bằng Mono/Flux và giữ luồng lỗi rõ ràng.

Ví dụ coordinator:

~~~java
public Mono<BindingResult> create(
        CreateServiceInstanceBindingRequest request) {

    return commandFactory.from(request)
        .flatMap(bindingRepository::reserve)
        .flatMap(reservation -> {
            if (reservation.isExisting()) {
                return replayService.loadExistingResult(reservation);
            }

            return provider.createPrincipal(reservation.command())
                .flatMap(providerBinding ->
                    secretStore.store(
                            reservation.bindingId(),
                            providerBinding.credentials())
                        .flatMap(secretRef ->
                            bindingRepository.markActive(
                                reservation,
                                providerBinding.providerBindingId(),
                                secretRef)
                        )
                        .thenReturn(
                            resultFactory.from(providerBinding))
                )
                .onErrorResume(error ->
                    failureCoordinator.handle(
                        reservation, error));
        });
}
~~~

Đây là pseudocode thể hiện thứ tự nghiệp vụ. Trong triển khai thật, cần xử lý transaction reserve, trạng thái CREATING, lưu provider result và secret sao cho có thể phục hồi nếu một bước thất bại.

### Khi provider trả operation ID

Một số provider không tạo principal ngay mà trả operation ID cho tác vụ nội bộ của họ. Broker có thể poll provider hoặc nhận callback để chờ credentials.

Có thể triển khai:

1. Gọi provider tạo binding.
2. Nhận providerOperationId và lưu vào bản ghi binding.
3. Poll trạng thái bằng backoff có giới hạn hoặc chờ callback đã xác thực.
4. Khi provider báo hoàn tất, lấy credentials.
5. Lưu secret và đánh dấu binding ACTIVE.
6. Trả response OSB cho request đang chờ nếu vẫn trong thời hạn.
7. Nếu vượt timeout, chuyển binding sang trạng thái cần reconciliation và trả lỗi tạm thời phù hợp; không trả thành công giả.

Đây là bất đồng bộ nội bộ. Nền tảng OSB vẫn nhận kết quả cuối cùng của binding qua request hiện tại hoặc nhận lỗi để retry.

## 9. Timeout và kết quả không xác định

Timeout không chứng minh provider chưa tạo binding. Có thể provider đã tạo user nhưng response bị mất. Nếu broker gửi lại lệnh tạo mà không tra cứu, một binding có thể tạo ra nhiều principal.

Khi gặp timeout:

- Giữ binding ở trạng thái CREATING hoặc UNKNOWN.
- Tra cứu provider theo external reference ổn định gắn với instanceId và bindingId.
- Nếu provider resource đã tồn tại, lấy kết quả và tiếp tục lưu secret.
- Nếu provider xác nhận chưa tạo, retry bằng idempotency key cũ.
- Nếu không thể xác định, giữ trạng thái để reconciliation và không tạo một binding mới bằng ID khác một cách âm thầm.

Nếu provider tạo principal thành công nhưng secret manager lỗi, broker phải có quy trình bù trừ. Có thể thử lưu lại credentials nếu vẫn còn trong bộ nhớ an toàn hoặc provider cho phép đọc lại. Nếu không thể khôi phục, revoke principal vừa tạo và đánh dấu lỗi sau khi xác nhận đã thu hồi. Không ghi secret vào log để phục hồi thủ công.

## 10. Lưu và phát lại response an toàn

OSB yêu cầu request tạo binding lặp phải nhận kết quả tương ứng với binding đã tạo. Vì response có thể chứa password hoặc token, broker cần chuẩn bị cách phát lại.

Một thiết kế thường dùng:

- Metadata binding lưu trong database.
- Credentials lưu trong secret manager hoặc dạng mã hóa bằng envelope encryption.
- Database chỉ lưu credentialSecretRef và metadata cần thiết.
- Secret manager phân quyền đọc theo service identity và binding ownership.
- Mỗi lần phát lại response đều kiểm tra instance, binding và tenant.
- Secret có audit event khi được đọc để trả response.

Không thể dùng password hash để dựng lại response có password gốc. Nếu provider chỉ hiển thị secret một lần, broker cần lưu secret an toàn trước khi trả response lần đầu. Nếu không lưu được secret và provider không cho truy xuất lại, cần có cơ chế khôi phục hoặc revoke; không được trả một password mới dưới cùng binding ID như thể đó là kết quả cũ.

Response minh họa:

~~~json
{
  "credentials": {
    "uri": "postgres://orders_app:secret-value@db.example.internal:5432/orders",
    "username": "orders_app",
    "password": "secret-value",
    "database": "orders"
  }
}
~~~

Credentials là object do broker định nghĩa cho service. Không ghi response nguyên vẹn vào log, tracing span, metric label hoặc exception. Khi cần log, chỉ ghi bindingId, instanceId, provider request ID và mã lỗi đã làm sạch.

## 11. Phản hồi cho các trường hợp request lặp

Các trường hợp phổ biến:

| Trường hợp | Response/hành vi |
|---|---|
| Binding mới và tạo thành công | HTTP 201 với binding response |
| Binding đã ACTIVE, cùng request | HTTP 200 và response tương đương kết quả ban đầu |
| Binding ID đã tồn tại, request khác parameters/consumer | HTTP 409 Conflict |
| Instance không tồn tại | Lỗi theo hợp đồng OSB, không gọi provider |
| Instance chưa sẵn sàng | Lỗi phù hợp với trạng thái instance |
| Hai request giống nhau đồng thời | Chỉ một lần tạo provider; request còn lại chờ hoặc replay |
| Request lặp đến khi binding đang tạo | Tham gia cùng tiến trình hoặc trả lỗi tạm thời để retry |
| Provider timeout, kết quả chưa rõ | Reconcile; không tạo thêm principal |
| Binding đã bị revoke | Không phát lại credentials cũ; áp dụng policy vòng đời và ID |

Mã HTTP cụ thể phải được ánh xạ theo OSB API version và framework đang dùng. Bảng này nêu hành vi mong đợi ở mức hợp đồng, không thay thế kiểm tra response mapping của phiên bản thư viện.

## 12. Bảo mật và quyền truy cập trong binding

Binding cấp quyền cho consumer, vì vậy credentials phải tuân theo least privilege:

- Tạo principal riêng cho mỗi binding nếu provider hỗ trợ.
- Giới hạn quyền theo database, schema, bucket, queue, vhost hoặc resource scope.
- Dùng password/token sinh từ nguồn ngẫu nhiên mật mã an toàn.
- Truyền secret qua TLS và lưu trong secret manager.
- Không dùng tài khoản quản trị provider làm credentials cho ứng dụng.
- Xác thực consumer và tenant theo danh tính tin cậy của nền tảng.
- Không xem app_guid hoặc context trong request là bằng chứng phân quyền độc lập.
- Thu hồi principal ở provider khi unbind.
- Xóa hoặc vô hiệu hóa secret sau khi quyền đã được thu hồi theo policy.
- Ghi audit cho tạo, đọc lại và thu hồi credentials.

Nếu service hỗ trợ nhiều kiểu binding như application binding, route service hoặc volume binding, cần kiểm tra capability và response fields tương ứng. Chỉ trả credentials hoặc metadata mà consumer và nền tảng cần.

## 13. Kiểm thử đồng bộ, bất đồng bộ và idempotency

Một bộ kiểm thử nên xác nhận cả HTTP contract, database state, secret store và side effect ở provider.

| Tình huống | Kết quả cần xác nhận |
|---|---|
| Binding hợp lệ | Trả 201 và credentials hợp lệ |
| Retry cùng binding ID và fingerprint | Trả 200, cùng provider principal và credentials |
| Retry với parameters khác | Trả 409, không thay đổi binding cũ |
| Hai request đồng thời giống nhau | Chỉ một provider create được thực hiện |
| Hai request đồng thời khác fingerprint | Một request reserve; request kia bị xung đột |
| Provider I/O reactive hoàn tất nhanh | Mono phát response cuối cùng |
| Provider trả operation ID | Handler chờ kết quả theo timeout nội bộ |
| Provider timeout trước khi tạo | Retry có kiểm soát |
| Provider timeout sau khi có thể đã tạo | Reconcile trước khi retry |
| Secret manager lỗi | Phục hồi kết quả hoặc revoke principal bù trừ |
| Broker restart khi CREATING | Reconciliation tiếp tục hoặc xác định kết quả |
| Binding đã ACTIVE nhưng response bị mất | Retry trả lại response tương đương |
| Binding đã REVOKED | Không phát lại secret cũ |
| Log và trace | Không chứa password/token |

Dùng test double cho provider để mô phỏng response thành công, rate limit, timeout trước và sau side effect. Với kiểm thử concurrency, chạy nhiều request đồng thời với cùng binding ID và xác nhận số principal thực tế ở provider chỉ là một.

Ngoài unit test, nên có contract test kiểm tra status code, response body, header và lỗi theo OSB API version mà broker tuyên bố hỗ trợ. Kiểm tra replay cần xác nhận credentials trả về khớp secret ban đầu, không chỉ so sánh HTTP status.

## 14. Những lỗi thường gặp

**Nhầm Mono với OSB asynchronous operation.** Mono là cơ chế lập trình reactive. Framework vẫn chờ Mono hoàn tất để trả response HTTP của binding.

**Trả 202 rồi chờ nền tảng gọi last_operation.** Binding chuẩn không dùng chung luồng async provision/update/deprovision. Chỉ triển khai kiểu phản hồi riêng khi có extension và thỏa thuận tương thích rõ ràng.

**Tạo credentials mới cho request retry.** Điều này làm một binding ID gắn với nhiều quyền truy cập. Hãy lưu và phát lại cùng kết quả.

**Chỉ kiểm tra tồn tại mà không reserve.** Hai request đồng thời có thể cùng tạo principal. Dùng unique constraint và reservation trước side effect.

**Trả thành công khi provider mới tiếp nhận operation.** Credentials có thể chưa tồn tại. Handler chỉ trả response binding khi dữ liệu cần thiết đã sẵn sàng.

**Coi timeout là thất bại chắc chắn.** Provider có thể đã tạo user. Tra cứu theo external reference và reconcile trước khi gửi lệnh mới.

**Không lưu secret trước response đầu tiên.** Nếu response bị mất và provider chỉ trả secret một lần, broker không thể phát lại kết quả ban đầu. Lưu secret an toàn trước khi đánh dấu binding ACTIVE.

**Gọi subscribe() trong handler.** Việc này tách side effect khỏi lifecycle của request và khiến lỗi khó kiểm soát. Trả Mono cho framework quản lý.

## 15. Nguyên tắc triển khai trong Spring Cloud Service Broker

Hãy giữ createServiceInstanceBinding() làm điểm tiếp nhận request OSB và chuyển nghiệp vụ sang BindingCoordinator. Coordinator xác thực instance và consumer, chuẩn hóa fingerprint, reserve binding ID, xử lý request đã tồn tại, gọi provider adapter và lưu credentials an toàn. Repository cần unique constraint để bảo vệ trước concurrency; secret manager cần hỗ trợ truy xuất an toàn khi phát lại response.

Dùng Reactor hoặc SDK bất đồng bộ để tránh chặn thread khi gọi provider, nhưng vẫn hoàn thành hợp đồng binding trong request hiện tại. Nếu provider có operation dài, broker có thể poll hoặc nhận callback nội bộ trong giới hạn thời gian; nếu không thể hoàn tất, giữ trạng thái cần reconciliation và trả lỗi retryable phù hợp. Không trả thành công khi chưa có credentials.

Với request lặp, cùng binding ID và cùng fingerprint phải nhận lại kết quả đã tạo; cùng ID nhưng nội dung khác phải bị từ chối xung đột. Với request đồng thời, chỉ một tiến trình được tạo side effect tại provider. Những nguyên tắc này giúp binding có thể retry an toàn, bảo vệ credentials và giữ cho trạng thái giữa nền tảng, broker và nhà cung cấp nhất quán.

