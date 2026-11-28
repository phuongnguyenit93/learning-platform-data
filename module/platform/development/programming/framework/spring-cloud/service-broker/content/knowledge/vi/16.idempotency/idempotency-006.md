# Kiểm soát hai yêu cầu cạnh tranh trên cùng instance hoặc binding

Service broker thường nhận nhiều request gần như cùng lúc. Nền tảng có thể gửi lại một request sau timeout trong khi request đầu vẫn đang chạy; hai người dùng có thể cùng cập nhật một service instance; một ứng dụng có thể bind trong lúc nền tảng đang deprovision instance; hoặc hai worker có thể tiếp tục cùng một operation sau khi lease cũ hết hạn. Nếu mỗi request chỉ đọc trạng thái rồi tự thực hiện, broker có thể tạo tài nguyên trùng, ghi đè cấu hình mới bằng dữ liệu cũ, cấp credentials cho instance đang bị xóa hoặc giải phóng quota nhiều lần.

Trong module SPRING_CLOUD_SERVICE_BROKER, cần phân biệt hai vấn đề thường bị gộp chung:

- **Request trùng:** cùng một ý định nghiệp vụ được gửi lại, thường do timeout hoặc retry. Broker cần idempotency để không thực hiện hiệu ứng lần thứ hai.
- **Request cạnh tranh:** hai ý định khác nhau cùng tác động lên một instance hoặc binding. Broker cần serialization, locking hoặc optimistic concurrency để quyết định thứ tự và ngăn trạng thái không hợp lệ.

Idempotency key không tự giải quyết mọi race condition. Hai request có key khác nhau vẫn có thể cùng sửa một instance. Ngược lại, khóa database không đủ để nhận diện một request retry sau khi response đầu đã bị mất. Một thiết kế đáng tin cậy cần kết hợp định danh request, ràng buộc dữ liệu, state transition nguyên tử và cơ chế phục hồi cho công việc bất đồng bộ.

## 1. Những bất biến cần bảo vệ

Trước khi chọn cơ chế khóa, hãy xác định các điều kiện luôn phải đúng trong vòng đời service instance và binding.

| Bất biến | Ý nghĩa |
|---|---|
| Mỗi instance chỉ có một operation thay đổi vòng đời đang hoạt động | Không chạy provision, update hoặc deprovision cạnh tranh trên cùng instance nếu các thao tác không tương thích |
| Instance đang deprovision không nhận binding mới | Không cấp credentials cho consumer trong lúc tài nguyên nền tảng đang bị thu hồi |
| Deprovision chỉ bắt đầu khi không còn binding blocking | Không xóa instance khi binding còn CREATING, BOUND hoặc UNBINDING |
| Một binding ID chỉ đại diện một binding trong phạm vi instance | Không tạo hai principal/secret khác nhau cho cùng một định danh binding |
| Một binding không được bind và unbind đồng thời | Không trả credentials khi quyền truy cập đang bị thu hồi |
| Plan hiện tại chỉ đổi sau khi backend xác nhận | Không công bố cấu hình đích khi tài nguyên thực tế chưa chuyển đổi thành công |
| Quota allocation chỉ được reserve/release có hiệu lực một lần | Request lặp không làm vượt quota hoặc giảm usage nhiều lần |
| Worker cũ không được ghi đè kết quả của worker mới | Lease hết hạn không cho phép worker cũ tiếp tục cập nhật state |

Các bất biến này cần được bảo vệ ở nơi có tính nhất quán dùng chung, thường là database hoặc một dịch vụ state coordinator. Kiểm tra trong bộ nhớ của một JVM không đủ khi broker chạy nhiều replica.

## 2. Phân loại các tình huống cạnh tranh

Không phải mọi cặp request đều cần cùng một chính sách:

| Request A | Request B | Rủi ro | Chính sách thường dùng |
|---|---|---|---|
| Provision instance X | Provision lại instance X với cùng request key | Tạo tài nguyên hai lần | Idempotency record và request fingerprint |
| Update instance X | Update instance X với payload khác | Ghi đè cấu hình hoặc plan | Serialize theo instance hoặc từ chối khi có operation active |
| Bind instance X / binding Y | Bind lại binding Y | Tạo principal và secret trùng | Unique constraint và idempotent replay |
| Bind instance X | Deprovision instance X | Credentials được cấp trong lúc xóa tài nguyên | Khóa instance và state transition nguyên tử |
| Unbind binding Y | Unbind lại binding Y | Revoke lặp hoặc lỗi giả | Idempotent unbind theo binding state |
| Bind binding Y | Unbind binding Y | Binding có thể vừa tạo vừa bị thu hồi | Khóa binding và transition state có điều kiện |
| Deprovision instance X | Deprovision lại instance X | Nhiều worker xóa cùng resource | Một active operation và tombstone |
| Worker A | Worker B xử lý lại cùng operation | Worker cũ ghi kết quả trễ | Lease, fencing token và version check |

Điều đầu tiên là xác định aggregate cần đồng bộ. Với bind/deprovision, aggregate thường là service instance vì cả hai thao tác đều tác động đến trạng thái instance. Với việc xoay credentials hoặc unbind, cần thêm khóa ở cấp binding. Không nên khóa toàn bộ broker hoặc toàn bộ tenant khi chỉ một instance cần được bảo vệ.

## 3. Idempotency key và request fingerprint

Idempotency key nhận diện một ý định request qua nhiều lần gửi. Nếu client hoặc nền tảng retry cùng request, broker có thể trả lại kết quả đã ghi nhận thay vì chạy lại tác dụng phụ.

Một bản ghi idempotency có thể gồm:

| Trường | Mục đích |
|---|---|
| scope | Phạm vi duy nhất, ví dụ tenant + broker + loại operation |
| idempotency_key | Khóa do caller gửi hoặc broker tạo theo hợp đồng tích hợp |
| request_fingerprint | Hash chuẩn hóa của payload có ý nghĩa nghiệp vụ |
| resource_id | Instance hoặc binding bị tác động |
| operation_id | Operation đã được tạo cho request |
| status | RECEIVED, IN_PROGRESS, COMPLETED hoặc FAILED |
| response_reference | Tham chiếu kết quả có thể replay |
| created_at, expires_at | Thời gian lưu dấu vết request |

Fingerprint giúp phát hiện trường hợp nguy hiểm: cùng một idempotency key nhưng payload khác. Ví dụ lần đầu key req-123 yêu cầu plan Basic, lần sau key đó lại yêu cầu High Availability. Không được coi đây là retry tương đương. Broker cần từ chối xung đột theo error mapping đã định nghĩa và ghi log có correlation ID.

Fingerprint nên được tính trên biểu diễn chuẩn hóa của các trường có ý nghĩa nghiệp vụ, không hash raw JSON bytes vì thứ tự key hoặc khoảng trắng có thể khác. Cần xác định rõ các trường đưa vào fingerprint, ví dụ operation type, instance ID, binding ID, service ID, plan ID và parameters sau chuẩn hóa. Không đưa secret thô vào log hoặc lưu fingerprint có thể làm lộ giá trị nhạy cảm; dùng HMAC hoặc hash có salt/secret phù hợp nếu fingerprint chứa dữ liệu nhạy cảm.

Không phải mọi nền tảng OSB đều gửi một header idempotency key tiêu chuẩn cho mọi thao tác. Nếu giao thức không cung cấp key, broker có thể dựa vào resource ID, operation type, trạng thái hiện tại và unique constraints để nhận diện request lặp. Không tự giả định một header riêng được mọi platform hỗ trợ; nếu bổ sung header, cần tài liệu hóa contract tích hợp riêng.

## 4. Khác biệt giữa request trùng và request xung đột

Hai request chỉ nên được coi là cùng một request khi chúng có cùng định danh idempotency trong cùng scope và fingerprint tương đương.

| Trường hợp | Ví dụ | Hành vi |
|---|---|---|
| Cùng key, cùng fingerprint | Retry update plan Standard sang HA | Trả lại operation/kết quả đã tạo, không gọi backend lần nữa |
| Cùng key, fingerprint khác | Cùng key nhưng plan đích khác | Từ chối idempotency conflict |
| Khác key, cùng resource và cùng ý định | Hai lần deprovision độc lập cùng instance | Phát hiện operation deprovision đang active và dùng chung kết quả nghiệp vụ |
| Khác key, hai ý định không tương thích | Update plan và deprovision cùng instance | Serialize hoặc từ chối request thứ hai theo state |
| Khác resource | Bind hai binding ID khác nhau trên cùng instance | Có thể chạy song song nếu backend và policy cho phép, nhưng vẫn cần kiểm tra instance state |

Không dùng fingerprint để thay thế authorization. Một request giống hệt request trước vẫn phải được xác thực và kiểm tra caller có quyền xem kết quả replay hay không. Idempotency record cũng không phải bearer token.

## 5. Khóa theo instance và binding

Một cách trực tiếp để tuần tự hóa thao tác là dùng khóa theo aggregate:

- Khóa instance khi thay đổi lifecycle hoặc khi quyết định có cho phép bind/deprovision hay không.
- Khóa binding khi thay đổi trạng thái hoặc credential của binding đó.
- Dùng khóa operation khi worker cập nhật checkpoint hoặc terminal result.

Quy ước thứ tự khóa cần nhất quán. Một ví dụ:

1. Khóa instance.
2. Khóa binding theo binding ID nếu thao tác cần binding.
3. Khóa operation hoặc quota allocation theo thứ tự được quy định.

Nếu hai luồng khóa cùng các tài nguyên nhưng theo thứ tự ngược nhau, database có thể phát hiện deadlock. Một thứ tự toàn cục giúp giảm nguy cơ này.

Không giữ row lock trong khi gọi API database bên ngoài, Kubernetes API, secret manager hoặc cloud provider. Transaction nên ngắn: kiểm tra state, ghi reservation/operation, chuyển trạng thái và commit. Công việc remote chạy sau commit qua worker/outbox.

## 6. Pessimistic locking với database transaction

Pessimistic locking khóa bản ghi instance trong lúc transaction kiểm tra và thay đổi state. Ví dụ với JPA:

~~~java
public interface ServiceInstanceRepository
        extends JpaRepository<ServiceInstanceEntity, String> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select i from ServiceInstanceEntity i where i.id = :id")
    Optional<ServiceInstanceEntity> findByIdForUpdate(
            @Param("id") String id);
}
~~~

Một application service có thể reserve bind như sau:

~~~java
@Transactional
public BindingReservation reserveBinding(
        String instanceId,
        String bindingId,
        String tenantId) {

    ServiceInstanceEntity instance =
            instanceRepository.findByIdForUpdate(instanceId)
                    .orElseThrow(InstanceNotFoundException::new);

    accessPolicy.verifyTenant(tenantId, instance);

    if (instance.getStatus() != InstanceStatus.ACTIVE) {
        throw new InstanceNotBindableException();
    }

    return bindingRepository.insertCreating(
            instanceId, bindingId, tenantId);
}
~~~

Deprovision dùng cùng khóa instance:

~~~java
@Transactional
public DeprovisionReservation reserveDeprovision(String instanceId) {
    ServiceInstanceEntity instance =
            instanceRepository.findByIdForUpdate(instanceId)
                    .orElseThrow(InstanceNotFoundException::new);

    if (instance.getStatus() == InstanceStatus.DEPROVISIONING) {
        return operationRepository.findActiveDeprovision(instanceId)
                .map(DeprovisionReservation::existing)
                .orElseThrow(OperationStateException::new);
    }

    if (instance.getStatus() != InstanceStatus.ACTIVE) {
        throw new InvalidInstanceStateException();
    }

    if (bindingRepository.existsBlockingDeprovision(instanceId)) {
        throw new BindingsExistException();
    }

    instance.setStatus(InstanceStatus.DEPROVISIONING);
    DeprovisionOperation operation =
            operationRepository.create(instanceId);
    outboxRepository.append(operation.toEvent());

    return DeprovisionReservation.created(operation);
}
~~~

Các entity, enum và repository method trong ví dụ là mô hình ứng dụng. Hai transaction cùng khóa một instance sẽ được tuần tự hóa. Nếu bind commit trước, deprovision nhìn thấy binding CREATING/BOUND và từ chối. Nếu deprovision commit trước, bind nhìn thấy trạng thái DEPROVISIONING và bị từ chối.

Pessimistic lock phù hợp khi xung đột thường xuyên và transaction ngắn. Đổi lại, request có thể phải chờ khóa; cần timeout, theo dõi lock wait và tránh transaction kéo dài. Hành vi cụ thể của lock còn phụ thuộc database, isolation level và cách query.

## 7. Optimistic locking và compare-and-set

Optimistic locking phù hợp khi xung đột ít hơn và không muốn giữ khóa trong lúc đọc. Bản ghi có cột version:

~~~java
@Entity
public class ServiceInstanceEntity {

    @Id
    private String id;

    @Version
    private long version;

    @Enumerated(EnumType.STRING)
    private InstanceStatus status;

    private String currentPlanId;
}
~~~

Khi hai transaction cùng đọc version 7, chỉ một transaction có thể ghi version mới. Transaction còn lại gặp optimistic locking conflict và phải đọc lại state trước khi quyết định.

Với SQL compare-and-set, có thể cập nhật có điều kiện:

~~~sql
UPDATE service_instance
SET status = 'DEPROVISIONING',
    version = version + 1
WHERE id = :instance_id
  AND status = 'ACTIVE'
  AND version = :expected_version;
~~~

Nếu số hàng cập nhật bằng 1, transaction đã giành quyền chuyển state. Nếu bằng 0, state hoặc version đã đổi; không được tiếp tục cleanup như thể update thành công. Cần đọc lại instance và xử lý request theo trạng thái mới.

Optimistic locking không tự bảo vệ điều kiện phụ thuộc nằm ở bảng binding. Nếu deprovision kiểm tra không có binding rồi cập nhật instance mà không khóa chung aggregate hoặc dùng một cơ chế serialization tương đương, một transaction bind vẫn có thể thêm binding giữa hai bước. Có thể dùng parent-row lock, constraint/trigger phù hợp, transaction isolation đủ mạnh hoặc một command coordinator để bảo vệ cả invariant nhiều bảng.

## 8. Unique constraint là lớp bảo vệ cuối

Kiểm tra bằng code trước khi insert có thể bị vượt qua khi hai request chạy đồng thời. Database constraint giúp bảo đảm tính duy nhất ngay cả khi có nhiều replica.

Ví dụ các ràng buộc:

~~~sql
ALTER TABLE service_binding
ADD CONSTRAINT uq_binding_instance_id
UNIQUE (instance_id, binding_id);

CREATE UNIQUE INDEX uq_active_instance_lifecycle_operation
ON broker_operation (instance_id)
WHERE status IN ('PENDING', 'IN_PROGRESS')
  AND operation_type IN ('PROVISION', 'UPDATE', 'DEPROVISION');
~~~

Đây là ví dụ cú pháp có partial index; khả năng hỗ trợ phụ thuộc database. Với hệ quản trị khác, có thể dùng generated column, bảng active-operation riêng hoặc constraint tương đương. Cần định nghĩa chính xác thao tác nào không được chạy song song; không nhất thiết cấm mọi loại operation nếu có thao tác độc lập được phép chạy cùng lúc.

Khi constraint vi phạm, application service phải nhận diện loại xung đột:

- Binding cùng instance/ID đã tồn tại: đọc record hiện có, kiểm tra consumer và fingerprint, sau đó replay hoặc báo conflict.
- Active operation đã tồn tại: tìm operation hiện hành và trả kết quả phù hợp.
- Xung đột dữ liệu khác: không biến mọi lỗi unique thành retry thành công.

Unique constraint không thay thế kiểm tra quyền hoặc validation nghiệp vụ. Nó bảo vệ invariant cấu trúc, còn application service quyết định ý nghĩa của xung đột.

## 9. Xử lý bind cạnh tranh với deprovision

Bind và deprovision cùng tác động đến instance nên phải đồng bộ trên khóa instance.

| Transaction thắng trước | Kết quả |
|---|---|
| Bind tạo binding reservation trước | Deprovision thấy binding chưa terminal và từ chối theo semantics OSB, thường là 422 |
| Deprovision chuyển instance sang DEPROVISIONING trước | Bind không được tạo reservation hoặc credentials mới |
| Cả hai cùng đọc ACTIVE nhưng không có khóa/constraint | Có thể tạo binding sau khi cleanup đã bắt đầu; đây là race không được chấp nhận |

Luồng bind:

1. Khóa instance.
2. Kiểm tra ACTIVE, tenant, service capability và quyền bind.
3. Insert binding ở trạng thái CREATING với unique key.
4. Ghi operation/outbox nếu cần xử lý background.
5. Commit transaction.
6. Tạo principal/secret ở backend.
7. Cập nhật binding thành BOUND và lưu credential reference.

Luồng deprovision:

1. Khóa cùng instance.
2. Kiểm tra không có binding blocking, bao gồm CREATING và UNBINDING.
3. Chuyển instance sang DEPROVISIONING.
4. Tạo operation và outbox trong transaction.
5. Commit rồi mới gọi backend cleanup.

Nếu bind đã tạo reservation CREATING nhưng worker chưa tạo xong user, deprovision vẫn phải xem reservation đó là binding đang tồn tại. Nếu bind thất bại, cleanup bù phải xác nhận không còn principal/secret rồi mới chuyển binding sang trạng thái terminal không blocking.

## 10. Xử lý hai request update trên cùng instance

Hai request update khác nhau có thể cùng đọc plan hiện tại là Basic. Request A chuyển Basic sang Standard; request B chuyển Basic sang High Availability. Nếu cả hai cùng gửi backend command, kết quả có thể phụ thuộc thứ tự hoàn tất và broker có thể ghi sai plan cuối.

Có hai chiến lược phổ biến:

- **Serialize:** chỉ một update được active trên instance; request thứ hai chờ hoặc bị từ chối xung đột.
- **Optimistic compare:** request mang expected version/plan hiện tại; chỉ chấp nhận nếu state chưa đổi. Request đến sau phải đọc lại và tính lại transition.

Với OSB, không giả định nền tảng luôn gửi version của instance. Broker có thể dùng version nội bộ trong state store để kiểm soát concurrency. Nếu update thứ hai đến khi update đầu đang IN_PROGRESS, thường nên từ chối theo lỗi state conflict hoặc yêu cầu caller thử lại sau, thay vì tự xếp hàng hai thay đổi plan không có quy tắc.

Khi update thành công, cập nhật currentPlanId và current parameters trong cùng transaction ghi terminal operation. Trong thời gian update, lưu targetPlanId riêng. Không để worker A ghi đè kết quả của worker B nếu lease hoặc operation ownership đã thay đổi.

## 11. Bind trùng và hai binding khác nhau

Hai request bind cùng binding_id phải được coi là cùng logical binding nếu instance, consumer và cấu hình tương thích. Broker có thể trả lại cùng binding response theo cách secret được lưu trữ cho phép. Nếu binding ID thuộc consumer hoặc instance khác, từ chối xung đột.

Hai request bind với hai binding ID khác nhau trên cùng instance có thể được phép song song nếu:

- Instance vẫn ACTIVE.
- Plan cho phép bind.
- Tenant còn quota hoặc giới hạn số binding.
- Backend hỗ trợ tạo nhiều principal đồng thời.
- Không có operation update/deprovision làm thay đổi điều kiện truy cập.

Ngay cả khi cho phép song song, cần kiểm soát quota và số binding bằng atomic reservation hoặc constraint. Không dựa vào một lần đếm binding trước khi insert nếu hai transaction có thể cùng vượt qua ngưỡng.

Ví dụ giới hạn tối đa 20 binding:

~~~sql
UPDATE service_instance
SET binding_count = binding_count + 1,
    version = version + 1
WHERE id = :instance_id
  AND status = 'ACTIVE'
  AND binding_count < 20;
~~~

Nếu update không tác động hàng nào, instance không còn ACTIVE hoặc đã chạm giới hạn. Việc insert binding phải nằm trong cùng transaction; nếu insert thất bại, rollback counter. Nếu dùng counter denormalized, cần reconcile định kỳ với binding records để phát hiện sai lệch.

## 12. Unbind cạnh tranh với bind hoặc deprovision

Unbind và bind cùng binding ID cần khóa binding record. Nếu unbind chuyển trạng thái sang UNBINDING trước, request bind lặp không được cấp lại credentials khi quyền cũ đang bị thu hồi. Nếu bind reservation đang CREATING, unbind cần xử lý theo policy cho binding chưa hoàn tất và bảo đảm principal tạo dở được cleanup.

Deprovision phải xem UNBINDING là binding blocking. Chỉ khi backend xác nhận principal/token đã bị revoke, binding mới chuyển sang UNBOUND và không còn chặn deprovision.

Một quy tắc transition:

| Trạng thái hiện tại | Request | Trạng thái/đáp ứng |
|---|---|---|
| Không có binding | Bind | Tạo CREATING reservation |
| CREATING | Bind cùng fingerprint | Trả operation đang tạo hoặc tiếp tục cùng workflow |
| BOUND | Bind cùng fingerprint | Replay binding response theo chính sách |
| BOUND | Unbind | Chuyển UNBINDING và revoke |
| UNBINDING | Unbind lặp | Theo dõi cùng operation; không revoke song song |
| UNBOUND | Unbind lặp | Trả kết quả đã thu hồi theo semantics đã định nghĩa |
| UNBINDING | Bind | Từ chối cho đến khi unbind hoàn tất |

## 13. Transactional outbox và worker coordination

Database transaction không thể bao trùm một API cloud bên ngoài. Nếu broker commit state nhưng không gửi được message, worker không biết cần xử lý; nếu gửi message trước commit rồi transaction rollback, worker có thể xử lý một operation chưa tồn tại.

Transactional outbox giải quyết khoảng hở này:

1. Trong cùng transaction, ghi state transition, operation record và outbox event.
2. Commit.
3. Publisher đọc outbox và gửi event ít nhất một lần.
4. Consumer ghi inbox/dedup record theo event ID hoặc operation ID.
5. Worker thực hiện bước idempotent và lưu checkpoint.

Outbox event cần mang operation ID, aggregate ID, event type và version. Consumer phải bỏ qua event đã xử lý hoặc phát hiện version cũ. Vì message broker thường có delivery at-least-once, worker cần idempotency ở cấp operation và adapter.

## 14. Lease, fencing token và worker cũ

Lease giúp worker khác tiếp quản operation khi worker hiện tại chết hoặc ngừng gia hạn. Nhưng lease expiry không dừng được tiến trình cũ ngay lập tức. Worker A có thể bị pause, lease hết hạn, worker B nhận operation và bắt đầu xử lý; sau đó A hoạt động lại. Nếu A vẫn ghi state, hai worker cùng điều khiển một operation.

Fencing token giải quyết vấn đề này. Mỗi lần claim operation, coordinator cấp một token tăng đơn điệu. Mọi cập nhật state phải kèm token hiện tại; token cũ bị từ chối.

~~~text
Worker A claim operation -> fencing token 41
Worker A bị pause, lease hết hạn
Worker B claim operation -> fencing token 42
Worker B cập nhật checkpoint với token 42 -> chấp nhận
Worker A hoạt động lại, ghi với token 41 -> từ chối
~~~

Token cần được kiểm tra ở nơi ghi state có thẩm quyền. Chỉ lưu token trong worker memory không có tác dụng. Nếu backend hỗ trợ version/etag hoặc idempotency key, truyền operation ID/fencing token đến backend để ngăn lệnh cũ ghi đè tài nguyên mới. Nếu backend không hỗ trợ fencing, worker mới phải reconcile trạng thái thực tế trước khi tiếp tục.

## 15. Retry, conflict và backoff

Không phải mọi lỗi cạnh tranh đều nên retry ngay:

| Lỗi | Hành vi |
|---|---|
| Duplicate request cùng key/fingerprint | Replay operation hoặc kết quả hiện có |
| Cùng key, fingerprint khác | Từ chối conflict; không retry tự động |
| Optimistic locking conflict | Đọc lại state; đánh giá lại điều kiện nghiệp vụ |
| Unique constraint active operation | Tìm operation đang tồn tại và áp dụng policy |
| Lock timeout | Có thể retry có giới hạn với backoff và jitter |
| Instance đang UPDATING/DEPROVISIONING | Từ chối hoặc yêu cầu thử lại sau; không spin retry |
| Backend timeout sau tác dụng phụ | Reconcile trước khi gửi lệnh lại |
| Authorization/validation failure | Không retry tự động nếu input hoặc quyền chưa thay đổi |

Backoff nên có giới hạn và jitter để nhiều retry không dồn vào cùng thời điểm. Cần phân loại lỗi tạm thời và lỗi vĩnh viễn. Không giữ lock database trong suốt thời gian backoff; transaction kết thúc trước khi chờ retry.

## 16. Tích hợp với Spring và mô hình reactive

Với Spring, có thể dùng @Transactional và JPA pessimistic/optimistic locking nếu state store là relational database. Với R2DBC, cần dùng reactive transaction manager và kiểm tra khả năng lock/version của database driver; không gọi blocking repository trong reactive event loop.

Một số nguyên tắc triển khai:

- Application service là nơi điều phối state transition và transaction boundary.
- Repository cung cấp atomic update, lock hoặc version check.
- OSB handler chuyển request model thành command và ánh xạ lỗi nghiệp vụ.
- Outbox publisher và worker chạy ngoài HTTP request.
- Infrastructure adapter dùng operation ID và resource ownership metadata để thực hiện idempotent calls.
- Response mapper không tự quyết định concurrency; nó chỉ phản ánh kết quả application service.

Không dùng synchronized hoặc ReentrantLock làm cơ chế duy nhất cho broker nhiều replica. Những khóa này chỉ có hiệu lực trong một process và mất khi restart. Có thể dùng chúng để giảm contention cục bộ, nhưng database constraint/transaction hoặc coordinator dùng chung vẫn phải bảo vệ invariant.

## 17. Kiểm thử hai yêu cầu cạnh tranh

Kiểm thử tuần tự không chứng minh được tính an toàn khi concurrency. Cần tạo các request thực sự chạy đồng thời bằng barrier/latch hoặc test harness có thể điều khiển điểm đồng bộ.

| Ca kiểm thử | Invariant cần xác nhận |
|---|---|
| Hai request provision cùng idempotency key | Chỉ một logical resource và một operation được tạo |
| Cùng key nhưng payload khác | Một request thành công; request khác bị conflict rõ ràng |
| Hai update khác nhau cùng instance | Không có hai operation lifecycle không tương thích cùng active |
| Bind và deprovision cùng instance | Không có binding BOUND/CREATING khi instance đã DEPROVISIONING |
| Hai bind cùng binding ID | Chỉ một binding record và một principal |
| Hai bind ID khác nhau cùng instance | Không vượt quota hoặc max binding |
| Bind và unbind cùng binding | Không trả credentials sau khi revoke đã thắng |
| Hai unbind cùng binding | Principal được revoke idempotently, state chỉ terminal một lần |
| Worker A lease hết hạn, worker B tiếp quản | Worker A không thể ghi state bằng fencing token cũ |
| Outbox event gửi lặp | Worker không lặp tác dụng phụ không an toàn |
| Lock timeout | Transaction rollback đúng, không để state trung gian sai |
| Backend timeout sau khi đã tạo resource | Retry reconcile được resource hiện hữu thay vì tạo bản sao |

Test nên kiểm tra cả response và database/backend state. Ví dụ, hai request bind có thể cùng nhận response 200 nhưng vẫn tạo hai database user; chỉ kiểm tra HTTP status sẽ bỏ sót lỗi. Dùng integration test với database có transaction/locking thực tế để kiểm chứng unique constraints và isolation level.

## 18. Quan sát và vận hành concurrency

Các metric hữu ích:

- Số request bị deduplicate và số idempotency conflict.
- Số optimistic lock conflict, unique constraint conflict và lock timeout.
- Thời gian chờ khóa theo instance/binding.
- Số operation lifecycle đang active trên mỗi instance.
- Số binding ở CREATING, UNBINDING hoặc trạng thái retryable quá lâu.
- Số worker lease hết hạn và số lần fencing token cũ bị từ chối.
- Số outbox event pending, tuổi event lâu nhất và số lần delivery.
- Số lần backend retry/reconcile sau timeout.

Log nên có correlation ID, operation ID, instance ID, binding ID và version/fencing token khi cần điều tra. Không ghi credentials hoặc raw parameters. Cảnh báo khi một instance có nhiều operation active bất thường, binding bị kẹt ở trạng thái trung gian hoặc outbox tồn đọng lâu.

## 19. Những sai lầm thường gặp

- Chỉ dùng idempotency key mà không khóa hoặc kiểm soát state của resource.
- Chỉ dùng row lock mà không nhận diện request retry sau timeout.
- Dùng khóa trong JVM cho hệ thống có nhiều replica.
- Kiểm tra không có binding rồi chuyển instance sang DEPROVISIONING trong hai transaction tách rời.
- Giữ database transaction mở khi gọi cloud API.
- Xử lý mọi unique constraint violation như request trùng hợp lệ.
- Retry ngay mọi optimistic lock conflict mà không đọc lại state.
- Dùng lease mà không có fencing/version để chặn worker cũ.
- Cho rằng message queue chỉ gửi một lần và không cần deduplicate.
- Chỉ kiểm tra HTTP response mà không kiểm tra tài nguyên và state store.

## Kết luận

Kiểm soát hai yêu cầu cạnh tranh cần bảo vệ trạng thái của service instance và binding ở một nguồn nhất quán dùng chung. Idempotency key cùng request fingerprint xử lý request retry; row lock hoặc optimistic version tuần tự hóa các thay đổi xung đột; unique constraint bảo vệ định danh và operation active; state transition cùng outbox giúp worker tiếp tục an toàn sau lỗi. Với thao tác bất đồng bộ, lease cần đi cùng fencing token hoặc version check để worker cũ không ghi đè worker mới. Khi các invariant được kiểm thử bằng request song song và trạng thái backend thực tế, service broker Spring Cloud có thể xử lý retry, nhiều replica và thao tác bind/update/deprovision cạnh tranh mà không tạo tài nguyên trùng hoặc làm sai vòng đời dịch vụ.
