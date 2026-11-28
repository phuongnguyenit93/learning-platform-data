# Hủy binding đồng bộ hoặc bất đồng bộ

## Mục tiêu và bối cảnh

Service binding tạo quan hệ giữa một service instance và một consumer, thường là ứng dụng hoặc workload cần sử dụng tài nguyên. Khi binding được tạo, broker có thể cấp database user, access key, token, quyền truy cập queue, cấu hình route hoặc thông tin mount. Khi consumer không còn cần dịch vụ, platform gọi unbind để broker thu hồi quyền đã cấp.

Hủy binding là thao tác bảo mật quan trọng. Nếu broker chỉ xóa bản ghi binding trong database mà không vô hiệu hóa credentials ở backend, ứng dụng vẫn có thể truy cập tài nguyên bằng thông tin đã nhận trước đó. Ngược lại, nếu broker xóa toàn bộ service instance khi chỉ cần hủy một binding, các consumer khác đang sử dụng instance có thể bị gián đoạn.

Bài học này thuộc chương Vòng đời liên kết của module Spring Cloud Service Broker. Nội dung tập trung vào vòng đời unbind, cách xử lý đồng bộ và cách phối hợp cleanup nền khi cần nhiều bước. Một điểm giao thức cần nắm rõ: OSB API chuẩn yêu cầu thao tác unbind được xử lý đồng bộ. Broker có thể dùng worker hoặc queue cho phần cleanup nội bộ sau khi quyền truy cập đã bị vô hiệu hóa, nhưng không được giả định endpoint unbind có cơ chế 202 Accepted và last_operation giống provision, update hoặc deprovision.

Sau bài học, bạn có thể:

- Hiểu request DELETE service binding và các định danh cần kiểm tra.
- Phân biệt unbind với deprovision.
- Thiết kế quy trình thu hồi credentials và quyền truy cập an toàn.
- Triển khai unbind đồng bộ trong Spring Cloud Service Broker.
- Dùng background worker cho phần cleanup còn lại mà không làm sai hợp đồng OSB API.
- Xử lý request lặp, timeout, lỗi một phần và binding không tồn tại.
- Kiểm thử việc thu hồi quyền và bảo đảm không ảnh hưởng consumer khác.

## 1. Unbind trong Open Service Broker API

Platform yêu cầu hủy một binding qua endpoint:

~~~http
DELETE /v2/service_instances/{instance_id}/service_bindings/{binding_id}?service_id={service_id}&plan_id={plan_id}
Authorization: Basic <broker-credentials>
X-Broker-API-Version: <supported-version>
~~~

Ví dụ:

~~~http
DELETE /v2/service_instances/instance-100/service_bindings/binding-app-200?service_id=service-postgresql&plan_id=plan-standard
Authorization: Basic <broker-credentials>
X-Broker-API-Version: <supported-version>
~~~

Request xác định binding bằng ba định danh chính:

| Thành phần | Nguồn | Vai trò |
|---|---|---|
| instance_id | Path | Service instance đang được consumer sử dụng |
| binding_id | Path | Binding cần thu hồi |
| service_id | Query | Xác nhận loại service của instance |
| plan_id | Query | Xác nhận plan đang được platform tham chiếu |
| Authorization | Header | Xác thực platform gọi broker |
| X-Broker-API-Version | Header | Phiên bản OSB API |

Broker cần xác thực platform, tìm binding trong phạm vi instance và tenant phù hợp, sau đó đối chiếu service_id và plan_id với dữ liệu đã lưu. Chỉ khi các kiểm tra này thành công mới bắt đầu thu hồi quyền.

### 1.1. Unbind khác deprovision

Hai thao tác có mục tiêu khác nhau:

| Thao tác | Đối tượng | Kết quả |
|---|---|---|
| Unbind | Quan hệ giữa một consumer và service instance | Thu hồi credentials hoặc quyền của consumer |
| Deprovision | Service instance và tài nguyên được quản lý | Thu hồi tài nguyên của instance theo chính sách |

Một instance có thể có nhiều binding. Ví dụ, database billing có thể được dùng bởi billing-api, billing-worker và reporting-job. Khi billing-api ngừng sử dụng, broker chỉ thu hồi binding của billing-api. Database và các binding còn lại phải tiếp tục hoạt động.

~~~mermaid
flowchart TD
    I[Service Instance: billing database]
    I --> B1[Binding: billing-api]
    I --> B2[Binding: billing-worker]
    I --> B3[Binding: reporting-job]
    B1 --> U[DELETE binding billing-api]
    U --> R[Thu hồi user và credentials riêng]
    B2 --> KEEP1[Giữ nguyên]
    B3 --> KEEP2[Giữ nguyên]
    I --> DB[Database vẫn hoạt động]
~~~

Vì vậy, backend adapter của unbind cần nhận binding ID hoặc backend principal ID tương ứng. Không dùng lệnh xóa toàn bộ database chỉ vì một binding bị xóa.

## 2. Ranh giới đồng bộ và bất đồng bộ của OSB API

OSB API có hỗ trợ asynchronous operation cho một số thao tác vòng đời service instance, thường là provision, update và deprovision. Những thao tác này có thể dùng accepts_incomplete=true, trả HTTP 202 Accepted và cho platform truy vấn endpoint last_operation.

Với unbind, hợp đồng OSB API chuẩn yêu cầu xử lý đồng bộ. Request DELETE binding không dùng accepts_incomplete để khởi tạo một operation unbind bất đồng bộ và không có endpoint last_operation dành riêng cho binding.

Điều này không ngăn broker dùng queue hoặc worker bên trong. Cần phân biệt hai lớp:

- **Đồng bộ ở giao thức:** endpoint DELETE chỉ trả thành công khi điều kiện hoàn tất của unbind đã đạt, đặc biệt là credentials hoặc quyền truy cập đã không còn sử dụng được.
- **Bất đồng bộ nội bộ:** sau khi quyền đã bị vô hiệu hóa, broker có thể xếp các công việc dọn dẹp phụ trợ vào queue, chẳng hạn xóa metadata, giải phóng cache hoặc thu hồi tài nguyên phụ không còn ảnh hưởng đến khả năng truy cập.

Không được trả HTTP 202 cùng operation token cho unbind rồi kỳ vọng platform polling last_operation như khi deprovision. Đây không phải luồng asynchronous unbind của OSB API chuẩn.

### 2.1. Mẫu A: thu hồi hoàn toàn đồng bộ

Mẫu này phù hợp khi backend có thể vô hiệu hóa credentials và xóa các tài nguyên riêng của binding trong thời gian ngắn.

Quy trình:

1. Xác minh instance, binding, service, plan và quyền sở hữu.
2. Chuyển binding sang REVOKING.
3. Thu hồi user, token, key hoặc ACL ở backend.
4. Xác nhận credentials cũ không còn hợp lệ.
5. Xóa secret reference và dữ liệu binding cần thiết.
6. Đánh dấu binding UNBOUND hoặc xóa bản ghi theo chính sách lưu trữ.
7. Trả response thành công cho platform.

Endpoint chỉ hoàn tất khi quyền truy cập của binding đã bị thu hồi. Nếu backend không phản hồi hoặc việc thu hồi thất bại, broker cần giữ lại trạng thái để retry an toàn.

### 2.2. Mẫu B: vô hiệu hóa đồng bộ, cleanup phụ trợ bất đồng bộ

Một số backend có nhiều bước dọn dẹp. Ví dụ, broker có thể vô hiệu hóa database role ngay lập tức nhưng việc xóa audit artifact, cache entry hoặc tài nguyên phụ mất nhiều thời gian.

Có thể thực hiện:

1. Thu hồi hoặc vô hiệu hóa quyền truy cập ngay trong request unbind.
2. Xác nhận credentials cũ không còn hoạt động.
3. Ghi binding ở trạng thái REVOKED hoặc UNBOUND.
4. Ghi cleanup event vào transactional outbox trong cùng transaction.
5. Trả response thành công cho OSB API.
6. Worker xử lý các tác vụ housekeeping còn lại.

~~~mermaid
sequenceDiagram
    participant P as Platform
    participant API as Broker API
    participant DB as Broker Database
    participant BE as Access Backend
    participant Q as Outbox / Queue
    participant W as Cleanup Worker

    P->>API: DELETE service binding
    API->>DB: Xác minh binding và owner
    API->>BE: Disable credential / revoke grant
    BE-->>API: Access revoked
    API->>DB: Lưu UNBOUND + cleanup outbox
    API-->>P: 200 OK
    Q->>W: Cleanup event
    W->>BE: Xóa metadata hoặc tài nguyên phụ
    BE-->>W: Cleanup result
    W->>DB: Cập nhật cleanup state
~~~

Trong mẫu này, worker không được trì hoãn việc thu hồi quyền truy cập. Những công việc đưa vào queue phải là công việc có thể chạy sau khi consumer đã mất quyền sử dụng binding.

### 2.3. Mẫu C: không thể vô hiệu hóa quyền trong request

Nếu backend chỉ có thể thu hồi credentials bằng một workflow kéo dài và trong thời gian chờ credentials vẫn còn hiệu lực, broker không được trả thành công sớm. Vì OSB API chuẩn không cung cấp asynchronous unbind, broker nên:

- Trả lỗi tạm thời phù hợp nếu chưa thể hoàn tất.
- Giữ binding ở trạng thái REVOKE_PENDING hoặc REVOKE_RETRY_WAIT.
- Ghi operation nội bộ để worker thử lại nếu phù hợp.
- Cho phép platform retry cùng DELETE request.
- Đảm bảo request lặp không tạo thêm quyền hoặc xóa nhầm binding khác.

Nếu broker có thể vô hiệu hóa credential bằng một thao tác nhanh, ví dụ disable user hoặc revoke token, hãy thực hiện bước đó đồng bộ trước; phần cleanup dài hơn có thể chạy nền sau khi access đã bị khóa.

## 3. Mô hình dữ liệu và trạng thái binding

Broker cần lưu thông tin đủ để biết quyền nào phải thu hồi. Không nên chỉ lưu binding_id và instance_id nếu backend cần principal ID hoặc secret reference để revoke.

Một binding record có thể chứa:

| Trường | Mục đích |
|---|---|
| binding_id | ID do platform cung cấp |
| instance_id | Service instance sở hữu binding |
| service_id | Service definition đã chọn |
| plan_id | Plan được tham chiếu khi tạo binding |
| platform_id | Platform đã đăng ký broker |
| tenant_id | Tenant sở hữu instance |
| consumer_id | Ứng dụng hoặc workload sử dụng binding |
| backend_principal_id | User, role, key hoặc principal ở backend |
| secret_ref | Tham chiếu tới secret đã cấp |
| state | Trạng thái vòng đời binding |
| version | Phiên bản để kiểm soát cập nhật đồng thời |
| created_at / revoked_at | Thời điểm tạo và thu hồi |

Không lưu password hoặc access token ở dạng bản rõ trong bảng binding. Lưu secret trong secret manager và giữ secret_ref để broker có thể truy xuất đúng thông tin cần thu hồi.

### 3.1. State machine

Một state machine đơn giản:

~~~mermaid
stateDiagram-v2
    [*] --> BINDING
    BINDING --> BOUND
    BINDING --> FAILED
    BOUND --> REVOKING
    REVOKING --> UNBOUND
    REVOKING --> REVOKE_RETRY_WAIT
    REVOKE_RETRY_WAIT --> REVOKING
    UNBOUND --> [*]
~~~

Ý nghĩa:

- BINDING: broker đang tạo quyền và credentials.
- BOUND: consumer đã được cấp quyền sử dụng instance.
- REVOKING: broker đang vô hiệu hóa quyền.
- REVOKE_RETRY_WAIT: lần thu hồi gần nhất thất bại tạm thời, chờ retry.
- UNBOUND: quyền của binding đã bị thu hồi.

Có thể lưu trạng thái cleanup phụ trợ riêng. Ví dụ, binding đã UNBOUND nhưng cleanup event vẫn ở PENDING. Trạng thái này hợp lệ nếu quyền truy cập đã bị vô hiệu hóa và công việc còn lại không ảnh hưởng đến bảo mật hoặc tính đúng đắn của unbind.

### 3.2. Không xóa record quá sớm

Nếu xóa bản ghi binding trước khi backend revoke thành công, broker có thể mất thông tin cần thiết để thử lại. Một trình tự an toàn:

- Đọc và khóa binding.
- Chuyển state sang REVOKING.
- Gọi backend để revoke.
- Xác nhận revoke.
- Xóa secret hoặc đánh dấu secret đã thu hồi.
- Ghi state UNBOUND và audit.
- Giữ tombstone hoặc audit record theo chính sách.

Tombstone giúp nhận biết request DELETE lặp và ngăn một binding ID cũ bị hiểu nhầm là binding mới.

## 4. Xác minh request trước khi revoke

Unbind cũng cần xác minh định danh và quyền sở hữu. Một request hợp lệ về mặt HTTP vẫn có thể tham chiếu sai binding hoặc tenant.

Các bước xác minh:

1. Xác thực platform và kiểm tra API version.
2. Tìm service instance trong phạm vi platform/tenant.
3. Tìm binding theo binding_id và instance_id.
4. So sánh service_id và plan_id với bản ghi đã lưu.
5. Kiểm tra consumer và tenant có đúng phạm vi sở hữu.
6. Kiểm tra trạng thái binding.
7. Chỉ sau đó mới gọi backend revoke.

Ví dụ truy vấn có scope:

~~~sql
SELECT binding_id,
       instance_id,
       service_id,
       plan_id,
       tenant_id,
       consumer_id,
       backend_principal_id,
       secret_ref,
       state,
       version
FROM service_binding
WHERE binding_id = :bindingId
  AND instance_id = :instanceId
  AND platform_id = :authenticatedPlatformId;
~~~

Không tìm binding chỉ bằng binding_id rồi xóa. Việc ràng buộc binding với instance và platform giúp ngăn IDOR và tránh một platform tác động lên binding thuộc platform khác.

### 4.1. Kiểm tra service_id và plan_id

Service ID và plan ID trong query phải khớp với dữ liệu broker đã lưu theo hợp đồng OSB API. Không dùng giá trị từ request để ghi đè bản ghi binding.

Nếu plan của instance đã được cập nhật, broker phải duy trì mapping nhất quán giữa binding và instance. Một số binding được tạo theo plan tại thời điểm bind; một số policy có thể dùng plan hiện tại của instance. Cần xác định rõ mô hình dữ liệu của broker và đối chiếu theo hợp đồng mà platform gửi. Không chấp nhận một plan ID bất kỳ chỉ vì nó thuộc cùng service.

## 5. Thu hồi credentials và quyền backend

Credentials là phần nhạy cảm nhất của binding. Consumer có thể đã sao chép credentials vào environment, secret store hoặc cấu hình runtime. Xóa secret trong broker không làm credentials đã phát hành tự động mất hiệu lực.

Do đó, revoke phải diễn ra ở backend hoặc tại lớp kiểm soát truy cập mà backend tin cậy.

Ví dụ theo loại backend:

| Backend | Hành động revoke |
|---|---|
| PostgreSQL | Disable hoặc drop role riêng của binding; thu hồi session nếu chính sách yêu cầu |
| Redis | Disable ACL user hoặc thu hồi key tương ứng |
| Kafka/RabbitMQ | Xóa principal, credential hoặc ACL riêng |
| Object storage | Disable access key hoặc xóa policy gắn với binding |
| Kubernetes | Xóa hoặc vô hiệu hóa credential/Secret và RBAC riêng |
| API service | Revoke token, client credential hoặc grant |

Nếu backend dùng một tài khoản chung cho nhiều binding, broker không thể xóa tài khoản đó khi unbind một consumer. Nên tạo principal riêng cho từng binding hoặc có cơ chế grant/revoke theo từng consumer.

### 5.1. Thứ tự thu hồi

Một thứ tự thường dùng:

1. Chuyển binding sang REVOKING để ngăn cấp lại hoặc thao tác xung đột.
2. Vô hiệu hóa credentials hoặc quyền ở backend.
3. Thu hồi session hoặc connection nếu backend hỗ trợ và policy yêu cầu.
4. Xóa secret hoặc đánh dấu secret đã thu hồi.
5. Xóa ACL, network rule hoặc metadata riêng của binding.
6. Lưu audit và chuyển binding sang UNBOUND.

Không xóa secret trước khi đã bảo đảm backend không còn chấp nhận credential cũ, trừ khi có cơ chế khác để tìm và revoke principal. Nếu mất thông tin nhận diện backend principal, cleanup có thể không thể hoàn tất.

## 6. Xử lý đồng bộ trong Spring Cloud Service Broker

Spring Cloud Open Service Broker cung cấp abstraction ServiceInstanceBindingService để ứng dụng xử lý vòng đời binding. Implementation nhận request unbind và trả về response khi phần xử lý đồng bộ đã hoàn tất.

Ví dụ minh họa:

~~~java
@Service
public class BrokerBindingService
        implements ServiceInstanceBindingService {

    private final UnbindApplicationService unbindApplicationService;

    public BrokerBindingService(
            UnbindApplicationService unbindApplicationService) {
        this.unbindApplicationService = unbindApplicationService;
    }

    @Override
    public Mono<DeleteServiceInstanceBindingResponse>
    deleteServiceInstanceBinding(
            DeleteServiceInstanceBindingRequest request,
            String serviceInstanceId,
            String bindingId) {

        UnbindCommand command = new UnbindCommand(
                serviceInstanceId,
                bindingId,
                request.getServiceDefinitionId(),
                request.getPlanId()
        );

        return unbindApplicationService.unbind(command)
                .thenReturn(
                        DeleteServiceInstanceBindingResponse.builder().build()
                );
    }
}
~~~

Đây là ví dụ theo phong cách API reactive của Spring Cloud Open Service Broker. Chữ ký method, package và builder cần khớp phiên bản dependency mà ứng dụng đang sử dụng. Application service phải hoàn tất bước revoke bắt buộc trước khi Mono phát ra response thành công.

Không gọi block() trong reactive handler để chờ backend. Hãy dùng API reactive tương ứng hoặc chuyển blocking I/O sang scheduler phù hợp với giới hạn concurrency. Dù implementation dùng reactive, hợp đồng HTTP của unbind vẫn là đồng bộ: response thành công chỉ được phát khi quyền truy cập đã được vô hiệu hóa.

### 6.1. Application service

Application service có thể chia thành các bước:

~~~java
public Mono<Void> unbind(UnbindCommand command) {
    return bindingRepository
            .findForUpdate(
                    command.instanceId(),
                    command.bindingId()
            )
            .switchIfEmpty(Mono.error(
                    new BindingNotFoundException()
            ))
            .flatMap(binding ->
                    identityValidator.validate(command, binding)
                            .then(bindingStateService.markRevoking(binding))
                            .then(backendAccessService.revoke(binding))
                            .then(secretService.markRevoked(binding.secretRef()))
                            .then(auditService.recordUnbound(binding))
                            .then(bindingRepository.markUnbound(binding.id()))
            );
}
~~~

Đây là pseudocode minh họa thứ tự xử lý. Trong implementation thật, cần xem xét transaction boundaries và reactive transaction manager. Không giữ database lock trong khi gọi một backend chậm nếu có thể thay bằng state transition có điều kiện và lease ngắn.

### 6.2. Transaction và backend không cùng một hệ thống

Không thể dùng một transaction database để rollback thao tác revoke đã thực hiện ở backend. Vì vậy, broker cần lưu trạng thái trung gian:

- Ghi REVOKING trước khi gọi backend.
- Gọi revoke bằng định danh ổn định.
- Nếu revoke thành công, ghi UNBOUND.
- Nếu backend timeout, tra cứu principal hoặc trạng thái quyền trước khi retry.
- Nếu backend trả lỗi tạm thời, lưu REVOKE_RETRY_WAIT và cho phép request lặp hoặc worker tiếp tục.

Không đánh dấu UNBOUND chỉ vì broker đã gửi lệnh revoke. Cần có bằng chứng backend đã vô hiệu hóa quyền hoặc một cơ chế chặn truy cập khác đã được kích hoạt.

## 7. Cleanup nền sau khi access đã bị revoke

Khi unbind có nhiều công việc phụ trợ, broker có thể ghi cleanup event vào outbox sau khi đã vô hiệu hóa credentials. Các công việc nền có thể gồm:

- Xóa cache entry liên quan binding.
- Xóa metadata hoặc artifact tạm.
- Thu hồi resource phụ không còn được dùng.
- Cập nhật inventory hoặc billing record.
- Xóa Secret trong Kubernetes sau khi workload đã được cập nhật.
- Gửi audit event đến hệ thống giám sát.

Những tác vụ này chỉ được đưa sang background worker nếu việc trì hoãn không khiến credentials cũ còn hiệu lực hoặc tạo ra quyền truy cập ngoài ý muốn.

Ví dụ transaction sau revoke:

~~~java
@Transactional
public void completeUnbind(
        String bindingId,
        String operationId) {

    bindingRepository.markUnbound(bindingId);

    outboxRepository.save(
            OutboxEvent.bindingCleanupRequested(
                    bindingId,
                    operationId
            )
    );

    auditRepository.save(
            AuditEvent.bindingRevoked(bindingId)
    );
}
~~~

Sau khi transaction commit, publisher gửi cleanup event đến queue. Worker có thể retry mà không ảnh hưởng đến kết quả unbind đã trả cho platform.

### 7.1. Theo dõi cleanup nội bộ

Broker có thể có bảng cleanup_task riêng:

| Trường | Ý nghĩa |
|---|---|
| cleanup_id | ID công việc cleanup |
| binding_id | Binding liên quan |
| state | PENDING, RUNNING, RETRY_WAIT, SUCCEEDED, FAILED |
| attempt | Số lần thử |
| next_attempt_at | Thời điểm thử tiếp |
| error_code | Lỗi đã chuẩn hóa |
| completed_at | Thời điểm hoàn tất |

Đây là trạng thái nội bộ, không phải operation token cho platform polling theo OSB API. Endpoint last_operation của service instance không nên bị dùng để mô phỏng trạng thái unbind.

## 8. Idempotency và request DELETE lặp

Platform có thể gửi lại DELETE nếu response bị mất hoặc kết nối bị ngắt. Broker phải xử lý request lặp mà không tạo lỗi nguy hiểm.

Các trường hợp:

| Trạng thái binding | Request lặp | Hành vi |
|---|---|---|
| BOUND | DELETE hợp lệ | Bắt đầu revoke |
| REVOKING | DELETE cùng binding | Tiếp tục hoặc trả kết quả retryable theo trạng thái hiện tại |
| REVOKE_RETRY_WAIT | DELETE cùng binding | Thử lại revoke hoặc giữ lịch retry |
| UNBOUND | DELETE lặp | Không tạo side effect; phản hồi theo mã 200/410 của hợp đồng |
| Không tồn tại | DELETE | Trả kết quả not found/gone theo OSB API version |
| ID hoặc owner không khớp | DELETE | Từ chối, không gọi backend |

Idempotency cần được áp dụng ở nhiều lớp:

- Unique key cho binding_id trong phạm vi instance.
- Backend principal ID ổn định.
- Revoke API có khả năng gọi lặp hoặc tra cứu trạng thái.
- Conditional state transition để chỉ một request bắt đầu revoke.
- Tombstone hoặc audit record để nhận biết binding đã kết thúc.
- Request lặp không tạo cleanup task trùng không cần thiết.

Nếu backend trả "principal not found", broker chỉ coi đó là revoke hoàn tất sau khi xác minh đúng tenant, đúng principal và đúng binding. Không được biến mọi lỗi 404 thành thành công nếu có nguy cơ ID sai.

## 9. Xử lý lỗi và timeout

Unbind có thể gặp lỗi trước, trong hoặc sau khi backend revoke.

| Tình huống | Cách xử lý |
|---|---|
| Binding không tồn tại | Trả response theo hợp đồng OSB API |
| service_id hoặc plan_id không khớp | Từ chối trước khi gọi backend |
| Caller không có quyền | Từ chối và ghi audit |
| Backend timeout | Tra cứu trạng thái principal trước khi retry |
| Backend trả 429 | Tôn trọng Retry-After và retry có giới hạn |
| Backend trả 5xx | Giữ REVOKING/RETRY_WAIT và cho phép retry |
| Backend trả 401/403 | Dừng retry mù quáng, cảnh báo lỗi credentials/quyền |
| Revoke thành công nhưng xóa secret thất bại | Giữ trạng thái revoke đã hoàn tất, retry cleanup secret |
| Cleanup phụ trợ thất bại | Giữ cleanup task pending; không khôi phục quyền đã thu hồi |

Nếu backend revoke thất bại và credentials vẫn còn hiệu lực, broker không nên trả success. Có thể trả lỗi tạm thời để platform retry DELETE. Nếu broker tiếp tục retry nội bộ, cần bảo đảm request lặp và worker không tranh chấp trên cùng binding.

Nếu revoke đã thành công nhưng việc dọn secret hoặc metadata phụ trợ thất bại, broker có thể trả thành công khi điều kiện unbind đã đạt, đồng thời giữ cleanup task để xử lý tiếp.

## 10. Bảo mật và cô lập consumer

Binding thường chứa credentials hoặc quyền truy cập cụ thể. Vì vậy, unbind cần bảo đảm không tác động đến consumer khác và không làm lộ thông tin bí mật.

Các nguyên tắc:

- Gắn binding với instance, tenant và consumer đã xác thực.
- Tạo principal hoặc credential riêng cho từng binding nếu backend hỗ trợ.
- Không dùng binding_id do client gửi để xóa một principal chưa được đối chiếu ownership.
- Vô hiệu hóa quyền backend trước khi xóa secret reference.
- Không ghi credentials, access token hoặc connection string vào log.
- Ghi audit cho actor, tenant, binding ID, operation và kết quả.
- Giới hạn quyền của broker service account chỉ ở phạm vi cần thiết.
- Kiểm tra backend ownership tag trước khi xóa resource nếu provider hỗ trợ.

Với Kubernetes, nếu credentials được lưu trong Secret, xóa Secret chỉ ngăn workload mới đọc secret từ API; pod hoặc tiến trình đã đọc giá trị trước đó có thể vẫn giữ credential trong bộ nhớ. Backend credential phải được revoke hoặc rotate để giá trị cũ mất hiệu lực. Sau đó controller mới dọn Secret và cập nhật workload theo chính sách.

## 11. Tương tác với Cloud Foundry và Kubernetes

### 11.1. Cloud Foundry

Cloud Foundry gọi broker để tạo binding và khi ứng dụng bỏ dịch vụ, platform gọi unbind. Broker cần thu hồi thông tin xác thực hoặc quyền đã cấp cho application binding.

Một luồng điển hình:

1. Ứng dụng được bind với service instance.
2. Broker tạo credentials hoặc quyền backend riêng cho ứng dụng.
3. Platform cung cấp thông tin binding cho ứng dụng.
4. Khi người dùng unbind, Cloud Controller gọi DELETE service binding.
5. Broker vô hiệu hóa credentials hoặc grant tương ứng.
6. Broker trả kết quả unbind theo hợp đồng.
7. Platform cập nhật trạng thái binding của ứng dụng.

Không deprovision database chỉ vì một ứng dụng Cloud Foundry bị unbind. Service instance có thể còn được các ứng dụng khác sử dụng.

### 11.2. Kubernetes

Kubernetes có thể tích hợp service broker qua controller hoặc adapter. Controller theo dõi resource đại diện cho binding và gọi endpoint unbind khi resource bị xóa hoặc spec thay đổi.

Một quy trình dùng finalizer:

1. Controller nhận biết binding resource đang bị xóa.
2. Finalizer giữ resource trong API server.
3. Controller gọi DELETE binding trên broker.
4. Broker revoke quyền và trả kết quả đồng bộ.
5. Controller xóa Secret hoặc tài nguyên liên quan theo chính sách.
6. Controller gỡ finalizer sau khi đã hoàn tất.

Nếu broker trả lỗi tạm thời, controller giữ finalizer và retry. Không gỡ finalizer trước khi binding đã được thu hồi, nếu không Kubernetes có thể xóa object trong khi backend credentials vẫn còn hiệu lực.

~~~mermaid
flowchart LR
    U[Binding CR bị xóa] --> C[Controller]
    C --> F[Finalizer giữ resource]
    F --> API[DELETE OSB Binding]
    API --> R[Broker revoke credentials]
    R --> OK[Unbind complete]
    OK --> S[Cleanup Secret / metadata]
    S --> D[Gỡ finalizer]
    D --> END[Resource được xóa]
~~~

## 12. Kiểm thử unbind đồng bộ và cleanup nền

Một bộ test cần xác nhận cả kết quả giao thức lẫn trạng thái quyền backend.

| Kịch bản | Kết quả mong đợi |
|---|---|
| Binding tồn tại, credentials hợp lệ | Backend revoke thành công và endpoint trả success |
| Binding không tồn tại | Response theo OSB API; không tạo side effect |
| service_id sai | Từ chối trước khi gọi backend |
| plan_id sai | Từ chối trước khi gọi backend |
| Binding thuộc tenant khác | Không cho phép revoke |
| Backend revoke timeout nhưng đã vô hiệu hóa credential | Tra cứu backend rồi cập nhật state đúng |
| Backend revoke timeout và credential còn hiệu lực | Không trả success; giữ trạng thái để retry |
| Backend trả 429 | Retry có backoff hoặc platform retry |
| Secret cleanup lỗi sau revoke | Unbind đã hoàn tất; cleanup task tiếp tục |
| DELETE được gửi hai lần | Không tạo side effect nguy hiểm hoặc principal trùng |
| Một binding bị hủy | Binding khác và service instance vẫn hoạt động |
| Worker cleanup bị restart | Cleanup task được phục hồi từ database/outbox |
| Kubernetes controller restart | Finalizer giữ resource cho đến khi unbind hoàn tất |

### 12.1. Unit test cho việc revoke trước khi hoàn tất

Ví dụ kiểm tra service gọi backend revoke trước khi đánh dấu binding UNBOUND:

~~~java
@Test
void revokesBackendAccessBeforeMarkingBindingUnbound() {
    bindingFixture.givenBound("instance-1", "binding-1");

    unbindService.unbind(command("instance-1", "binding-1"))
            .block();

    InOrder order = inOrder(backendAccessService, bindingRepository);
    order.verify(backendAccessService).revoke(any());
    order.verify(bindingRepository).markUnbound("binding-1");
}
~~~

Đây là ví dụ minh họa. Test thực tế cần dùng API reactive hoặc mock phù hợp với implementation và kiểm tra response OSB chỉ được phát sau khi bước revoke bắt buộc hoàn tất.

### 12.2. Test không ảnh hưởng binding khác

Tạo hai binding cùng trỏ tới một instance, sau đó unbind một binding. Xác nhận:

- Principal của binding bị hủy đã bị vô hiệu hóa.
- Principal của binding còn lại vẫn hoạt động.
- Service instance vẫn ở trạng thái READY.
- Backend database hoặc tài nguyên dùng chung không bị xóa.
- Audit ghi đúng consumer và binding đã bị hủy.

## 13. Quan sát và audit

Các trường nên có trong log hoặc trace:

- instance_id và binding_id.
- service_id và plan_id.
- platform_id và tenant_id.
- consumer_id đã được che hoặc mã hóa phù hợp.
- backend_principal_id theo chính sách bảo vệ.
- trạng thái binding trước và sau.
- thời gian revoke và cleanup.
- cleanup task ID nếu có.
- correlation ID và kết quả request.

Không ghi Authorization header, password, token hoặc connection string. Description gửi platform nên ngắn gọn và không lộ thông tin backend.

Metric hữu ích:

- Số request unbind theo kết quả.
- Thời gian revoke credentials.
- Số binding ở REVOKING hoặc REVOKE_RETRY_WAIT.
- Số cleanup task pending.
- Số lần retry backend revoke.
- Số request bị từ chối do ownership hoặc service/plan mismatch.
- Số binding bị phát hiện còn principal backend sau khi đã đánh dấu UNBOUND.

Cảnh báo khi binding ở REVOKING quá lâu, cleanup task vượt ngưỡng hoặc backend revoke liên tục thất bại. Những chỉ số này giúp phát hiện credential có thể còn hiệu lực sau khi platform đã yêu cầu hủy binding.

## 14. Những lỗi thiết kế thường gặp

- **Chỉ xóa binding record:** credentials backend vẫn còn hiệu lực.
- **Xóa cả service instance:** làm gián đoạn các consumer khác.
- **Trả thành công trước khi revoke:** platform tin rằng quyền đã mất nhưng consumer vẫn truy cập được.
- **Giả lập async unbind bằng 202:** không tuân theo hợp đồng asynchronous operation chuẩn của OSB API.
- **Xóa secret trước khi revoke:** broker có thể mất dữ liệu cần để vô hiệu hóa principal.
- **Không lưu trạng thái REVOKING:** request lặp có thể tạo nhiều workflow xung đột.
- **Không có idempotency:** retry có thể gây lỗi hoặc xóa nhầm principal.
- **Không phân biệt cleanup bắt buộc và phụ trợ:** tác vụ phụ trợ chậm làm kéo dài unbind không cần thiết hoặc cleanup quan trọng bị bỏ sót.
- **Coi 404 backend luôn là thành công:** có thể che giấu sai tenant hoặc sai resource ID.
- **Gỡ Kubernetes finalizer quá sớm:** object biến mất nhưng backend binding vẫn hoạt động.
- **Không kiểm thử consumer khác:** một binding bị hủy có thể ảnh hưởng toàn bộ instance.

## 15. Quy trình triển khai unbind an toàn

Khi xây dựng một binding service, hãy triển khai theo thứ tự:

1. Xác định dữ liệu binding và backend principal cần quản lý.
2. Lưu instance, service, plan, tenant và consumer khi bind.
3. Thiết kế state machine cho BOUND, REVOKING, UNBOUND và retry.
4. Xác minh caller, instance, binding, service_id, plan_id và ownership.
5. Dùng conditional update hoặc lock để chỉ một request thực hiện revoke.
6. Vô hiệu hóa credentials hoặc quyền backend.
7. Xác nhận credential cũ không còn sử dụng được.
8. Xóa secret reference và hoàn tất trạng thái binding.
9. Ghi audit và outbox event cho cleanup phụ trợ.
10. Trả response đồng bộ theo OSB API.
11. Dùng worker retry các cleanup task không ảnh hưởng đến access đã bị revoke.
12. Kiểm thử request lặp, backend timeout, tenant mismatch và binding dùng chung instance.

Nếu không thể vô hiệu hóa quyền trong request, hãy giữ trạng thái để retry và trả lỗi phù hợp. Không tuyên bố unbind thành công khi consumer vẫn còn quyền truy cập.

## Kết luận

Hủy binding thu hồi quyền của một consumer đối với service instance; nó không xóa service instance hoặc tài nguyên dùng chung. Broker phải xác minh binding, service, plan và ownership, sau đó vô hiệu hóa credentials hoặc grant ở backend trước khi đánh dấu unbind hoàn tất.

OSB API chuẩn yêu cầu unbind đồng bộ. Broker vẫn có thể dùng queue và worker cho cleanup phụ trợ sau khi quyền truy cập đã bị vô hiệu hóa, với điều kiện response thành công chỉ được trả khi ranh giới bảo mật đã đạt. Trong Spring Cloud Service Broker, hãy kết hợp ServiceInstanceBindingService, application service, backend adapter idempotent, trạng thái REVOKING/UNBOUND, outbox và audit để xử lý request lặp, timeout và lỗi một phần mà không ảnh hưởng đến consumer khác.
