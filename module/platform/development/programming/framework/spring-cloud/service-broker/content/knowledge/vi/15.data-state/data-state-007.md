# Khóa lạc quan, ràng buộc duy nhất và kiểm soát cập nhật cạnh tranh

## Mục tiêu và bối cảnh

Service broker tiếp nhận nhiều request từ platform, worker và các tiến trình vận hành. Các request có thể tác động đồng thời lên cùng một service instance hoặc binding. Ví dụ, platform gửi hai yêu cầu provision gần như cùng lúc với cùng instance ID; worker đang cập nhật plan trong khi người dùng yêu cầu deprovision; hai worker cùng xử lý một message do queue giao lại; hoặc hai request unbind cùng thu hồi một credential.

Nếu broker chỉ đọc trạng thái rồi cập nhật mà không có cơ chế đồng bộ, cả hai request có thể cùng tin rằng mình là bên duy nhất được phép thực hiện. Hậu quả có thể là tạo tài nguyên trùng, ghi đè cấu hình mới bằng dữ liệu cũ, chạy hai operation trên một instance hoặc xóa tài nguyên trong khi một workflow khác đang sử dụng.

Trong module Spring Cloud Service Broker, dữ liệu trạng thái là nền tảng để thực thi hợp đồng Open Service Broker API (OSB API) một cách an toàn. Bài học này tập trung vào ba cơ chế phối hợp:

- **Khóa lạc quan (optimistic locking):** phát hiện một bản ghi đã bị thay đổi kể từ lúc được đọc.
- **Ràng buộc duy nhất (unique constraints):** để database ngăn hai transaction tạo các định danh trùng nhau.
- **Kiểm soát cập nhật cạnh tranh:** bảo đảm state transition, operation và side effect được điều phối theo một quy tắc nhất quán.

Sau bài học, bạn có thể thiết kế version field, unique index, cập nhật có điều kiện, xử lý xung đột trong Spring Data/JPA hoặc SQL, phối hợp worker với request HTTP và retry an toàn khi xảy ra cạnh tranh.

## 1. Các tình huống cập nhật cạnh tranh trong service broker

Một broker có nhiều điểm cùng ghi dữ liệu:

- OSB API nhận provision, update, deprovision, bind hoặc unbind.
- Worker xử lý operation bất đồng bộ.
- Outbox publisher phát event.
- Reconciliation đối chiếu trạng thái broker và backend.
- Công cụ quản trị có thể yêu cầu retry hoặc can thiệp thủ công.

Các thành phần này có thể chạy trên nhiều instance ứng dụng. Một biến synchronized trong JVM chỉ bảo vệ thread trong cùng process; nó không điều phối được nhiều pod, nhiều worker hoặc nhiều broker instance.

### 1.1. Hai request provision cùng instance ID

Giả sử hai request PUT provision cùng đến với instance_id = instance-100:

1. Request A truy vấn và không tìm thấy instance.
2. Request B cũng truy vấn và không tìm thấy instance.
3. A tạo bản ghi và gọi backend tạo database.
4. B cũng tạo bản ghi hoặc gọi backend.
5. Broker có thể tạo hai tài nguyên backend cho cùng một instance ID.

Việc kiểm tra trước bằng SELECT không đủ để ngăn race condition. Cả hai transaction có thể cùng đọc kết quả "chưa tồn tại". Database cần một unique constraint để chỉ cho phép một transaction tạo bản ghi định danh đó.

### 1.2. Worker ghi đè trạng thái mới

Giả sử một worker đọc instance ở version 5, state READY. Trong lúc worker gọi backend, một request khác đã chuyển instance sang DEPROVISIONING và lưu version 6. Nếu worker cũ ghi state READY mà không kiểm tra version, nó có thể hồi sinh một instance đang bị xóa.

Đây là lost update: một cập nhật mới bị ghi đè bởi một tiến trình dùng dữ liệu cũ.

### 1.3. Hai operation không tương thích chạy đồng thời

Một request update và một request deprovision có thể cùng bắt đầu trên một instance. Nếu không có state transition có điều kiện, cả hai operation đều có thể được chấp nhận và gọi backend. Kết quả phụ thuộc thứ tự hoàn tất của các API bên ngoài, rất khó phục hồi.

Broker cần xác định các operation nào được phép chạy đồng thời. Với phần lớn thao tác thay đổi vòng đời của cùng một instance, quy tắc đơn giản và an toàn là chỉ có một lifecycle operation đang hoạt động tại một thời điểm.

~~~mermaid
flowchart TD
    A[Request Update] --> R[(Service Instance)]
    B[Request Deprovision] --> R
    R --> C{State transition có điều kiện}
    C -->|Một request thắng| D[Operation được chấp nhận]
    C -->|Request còn lại| E[Conflict hoặc trả operation hiện tại]
    D --> W[Worker / Backend]
~~~

## 2. Khóa lạc quan hoạt động như thế nào?

Khóa lạc quan giả định xung đột không xảy ra thường xuyên. Thay vì khóa hàng trong suốt thời gian xử lý, broker lưu một version number hoặc timestamp version. Khi cập nhật, broker yêu cầu version trong database vẫn bằng version đã đọc.

Ví dụ bản ghi:

| instance_id | state | current_plan_id | version |
|---|---|---|---:|
| instance-100 | READY | plan-standard | 5 |

Worker đọc version 5. Một request khác cập nhật bản ghi và version tăng thành 6. Khi worker cũ ghi lại với điều kiện version = 5, database không cập nhật hàng nào. Worker biết dữ liệu đã thay đổi và phải đọc lại để quyết định bước tiếp theo.

### 2.1. Cập nhật bằng version trong SQL

Một câu UPDATE có điều kiện:

~~~sql
UPDATE service_instance
SET state = 'UPDATING',
    version = version + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE instance_id = :instanceId
  AND version = :expectedVersion
  AND state = 'READY';
~~~

Kết quả:

- Một hàng được cập nhật: request đã thắng cuộc đua và state transition thành công.
- Không hàng nào được cập nhật: instance không còn ở version hoặc state mong đợi; cần đọc lại và phân loại xung đột.

Không nên coi số hàng bằng 0 là lỗi hệ thống chung. Đó có thể là xung đột nghiệp vụ hợp lệ: một operation khác đã thay đổi instance, instance không còn READY hoặc bản ghi đã bị xóa.

### 2.2. @Version trong JPA

Với ứng dụng Spring dùng JPA, có thể khai báo version field bằng annotation @Version:

~~~java
@Entity
@Table(name = "service_instance")
public class ServiceInstanceEntity {

    @Id
    @Column(name = "instance_id", nullable = false)
    private String instanceId;

    @Column(name = "service_id", nullable = false)
    private String serviceId;

    @Column(name = "current_plan_id", nullable = false)
    private String currentPlanId;

    @Enumerated(EnumType.STRING)
    @Column(name = "state", nullable = false)
    private InstanceState state;

    @Version
    @Column(name = "version", nullable = false)
    private long version;

    // getters, setters và domain methods
}
~~~

Khi entity được cập nhật, JPA provider tạo câu UPDATE có điều kiện theo version cũ và tăng version. Nếu một transaction khác đã cập nhật entity, transaction hiện tại có thể nhận OptimisticLockException hoặc một exception được Spring chuyển đổi tương ứng, chẳng hạn ObjectOptimisticLockingFailureException.

Một số lưu ý:

- Version field phải được quản lý bởi persistence provider; không tự tăng version trong domain code khi dùng @Version.
- Không lấy entity cũ rồi merge sau một thời gian dài mà không xử lý xung đột.
- Không giữ transaction mở trong lúc gọi cloud API hoặc database backend.
- Version phải được đọc lại từ database sau khi một transaction khác thay đổi bản ghi.
- Với bulk UPDATE bằng JPQL hoặc native SQL, cần tự quản lý version vì bulk operation thường bỏ qua cơ chế dirty checking của entity.

### 2.3. Khóa lạc quan trong R2DBC hoặc SQL thuần

Nếu broker dùng reactive persistence hoặc R2DBC, có thể không dùng JPA @Version. Nguyên tắc vẫn giữ nguyên: UPDATE theo điều kiện version và state, sau đó kiểm tra số hàng bị tác động.

Ví dụ:

~~~sql
UPDATE service_instance
SET state = :newState,
    version = version + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE instance_id = :instanceId
  AND version = :expectedVersion
  AND state = :expectedState;
~~~

Điểm cốt lõi không nằm ở annotation mà ở tính nguyên tử của phép so sánh và cập nhật trong database. Không thực hiện SELECT version rồi UPDATE không điều kiện trong hai round trip riêng.

## 3. Ràng buộc duy nhất là lớp bảo vệ cuối cùng

Unique constraint bảo đảm một tập giá trị chỉ xuất hiện một lần trong phạm vi được định nghĩa. Nó được database thực thi, kể cả khi nhiều ứng dụng cùng ghi đồng thời.

Ví dụ:

~~~sql
CREATE TABLE service_instance (
    instance_id VARCHAR(128) NOT NULL,
    platform_id VARCHAR(128) NOT NULL,
    tenant_id VARCHAR(128) NOT NULL,
    service_id VARCHAR(128) NOT NULL,
    current_plan_id VARCHAR(128) NOT NULL,
    state VARCHAR(32) NOT NULL,
    version BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    CONSTRAINT pk_service_instance PRIMARY KEY (instance_id),
    CONSTRAINT uq_platform_instance UNIQUE (platform_id, instance_id)
);
~~~

Trong ví dụ, primary key instance_id đã bảo đảm ID duy nhất toàn cục. Unique constraint theo platform_id và instance_id là dư thừa nếu instance_id thực sự là primary key toàn cục; nó được thể hiện để minh họa hai lựa chọn mô hình. Khi thiết kế thật, hãy chọn một quy tắc rõ ràng:

- Nếu broker quản lý một namespace ID toàn cục, instance_id có thể là primary key.
- Nếu broker cần cô lập ID theo platform, dùng composite primary key hoặc unique(platform_id, instance_id).

Không tạo cả hai ràng buộc nếu chúng không bổ sung bảo vệ cần thiết.

### 3.1. Unique constraint cho binding

Binding ID thường được định danh trong ngữ cảnh service instance. Có thể dùng:

~~~sql
CREATE TABLE service_binding (
    instance_id VARCHAR(128) NOT NULL,
    binding_id VARCHAR(128) NOT NULL,
    platform_id VARCHAR(128) NOT NULL,
    tenant_id VARCHAR(128) NOT NULL,
    state VARCHAR(32) NOT NULL,
    version BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL,
    CONSTRAINT pk_service_binding
        PRIMARY KEY (instance_id, binding_id)
);
~~~

Nếu broker có nhiều platform hoặc cần định danh khác, hãy điều chỉnh key theo namespace thực tế. Quan trọng là hai request bind đồng thời với cùng binding identity không tạo hai backend principal.

### 3.2. Unique constraint cho idempotency key

Một operation có thể được nhận nhiều lần do platform retry. Broker có thể lưu idempotency key hoặc request fingerprint:

~~~sql
CREATE TABLE idempotency_record (
    platform_id VARCHAR(128) NOT NULL,
    idempotency_key VARCHAR(200) NOT NULL,
    request_fingerprint VARCHAR(128) NOT NULL,
    operation_id VARCHAR(128) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    CONSTRAINT uq_platform_idempotency
        UNIQUE (platform_id, idempotency_key)
);
~~~

Nếu cùng key được gửi với fingerprint khác, broker phải từ chối vì client đang tái sử dụng key cho một request khác. Nếu key và fingerprint khớp, broker có thể trả lại operation đã được ghi nhận.

Không phải mọi OSB request đều có header idempotency key chuẩn do platform cung cấp. Broker có thể sử dụng định danh tài nguyên của OSB, request fingerprint và unique constraint để đạt tính idempotent. Nếu bổ sung key riêng, phải tài liệu hóa cách client sử dụng.

### 3.3. Tại sao SELECT trước INSERT không đủ?

Mẫu sau không an toàn khi có concurrency:

~~~java
if (!repository.existsByInstanceId(instanceId)) {
    repository.save(newInstance);
}
~~~

Hai request có thể cùng nhận false. Unique constraint ở database mới là cơ chế cuối cùng ngăn duplicate. Code ứng dụng cần bắt lỗi vi phạm constraint và chuyển thành kết quả nghiệp vụ phù hợp.

Không nên xóa unique constraint chỉ vì một test concurrency bị lỗi. Hãy kiểm tra transaction boundary và cách xử lý DuplicateKeyException hoặc DataIntegrityViolationException.

## 4. Kiểm soát state transition bằng compare-and-set

Optimistic locking trên entity bảo vệ bản ghi khỏi lost update. Tuy nhiên, broker còn cần bảo vệ quy tắc nghiệp vụ: chỉ cho phép chuyển từ một trạng thái cụ thể sang trạng thái khác.

Ví dụ chỉ cho phép bắt đầu update khi instance READY:

~~~sql
UPDATE service_instance
SET state = 'UPDATING',
    version = version + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE instance_id = :instanceId
  AND state = 'READY'
  AND version = :expectedVersion;
~~~

Đây là mẫu compare-and-set (CAS): chỉ cập nhật nếu giá trị hiện tại vẫn đúng như điều kiện đã đọc.

Nếu số hàng bị cập nhật bằng 0, broker không được gọi backend update. Hãy đọc lại state:

- Nếu state đã UPDATING và có operation tương ứng, trả operation hiện tại hoặc conflict theo hợp đồng.
- Nếu state DEPROVISIONING, từ chối update.
- Nếu state FAILED, áp dụng policy phục hồi hoặc yêu cầu can thiệp.
- Nếu instance không còn tồn tại, trả lỗi not found/gone theo OSB API version.

### 4.1. State transition table

Một transition table giúp tránh logic rải rác:

| State hiện tại | Operation yêu cầu | State tiếp theo | Kết quả |
|---|---|---|---|
| READY | UPDATE | UPDATING | Chấp nhận nếu CAS thành công |
| READY | DEPROVISION | DEPROVISIONING | Chấp nhận nếu CAS thành công |
| READY | BIND | READY + binding mới | Chấp nhận nếu binding key chưa tồn tại |
| UPDATING | DEPROVISION | Theo policy | Chờ update hoặc hủy có kiểm soát |
| DEPROVISIONING | UPDATE | Không đổi | Từ chối/conflict |
| DELETED | DEPROVISION | DELETED | Idempotent theo policy |
| PROVISIONING | DEPROVISION | Theo policy | Phối hợp hủy hoặc chờ provision |

Không phải mọi transition đều thay đổi instance state. Bind và unbind có state riêng ở service_binding. Nếu binding được quản lý độc lập, đừng cập nhật instance version cho mọi thay đổi binding trừ khi domain model yêu cầu điều đó. Việc này có thể tạo xung đột không cần thiết giữa các consumer độc lập.

### 4.2. Ghi operation cùng state transition

Khi bắt đầu một lifecycle operation, việc đổi state và tạo operation nên nằm trong cùng transaction database. Có thể thêm unique constraint để chỉ có một operation đang hoạt động trên instance cho nhóm operation không tương thích.

Ví dụ ý tưởng:

~~~sql
CREATE TABLE broker_operation (
    operation_id VARCHAR(128) PRIMARY KEY,
    instance_id VARCHAR(128) NOT NULL,
    operation_type VARCHAR(32) NOT NULL,
    state VARCHAR(32) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP
);
~~~

Một partial unique index trên các operation active có thể được dùng nếu database hỗ trợ:

~~~sql
CREATE UNIQUE INDEX uq_active_instance_operation
ON broker_operation(instance_id)
WHERE state IN ('PENDING', 'RUNNING', 'RETRY_WAIT');
~~~

Cú pháp partial index phụ thuộc database. Với hệ quản trị không hỗ trợ partial index, có thể dùng bảng active_operation riêng hoặc một cột active_instance_id được quản lý bằng constraint. Không dựa vào kiểm tra SELECT active operation rồi INSERT mà không có ràng buộc đồng thời.

## 5. Transaction boundary và lời gọi backend

Optimistic locking và unique constraints bảo vệ dữ liệu broker, nhưng không tự tạo transaction phân tán giữa database broker và backend tài nguyên.

Không nên làm như sau:

1. Mở transaction database.
2. Đọc entity và khóa hàng.
3. Gọi cloud API trong vài phút.
4. Cập nhật entity.
5. Commit.

Cách này giữ connection và lock quá lâu, gây nghẽn khi backend chậm. Nếu process chết sau khi cloud tạo resource nhưng trước commit, transaction rollback nhưng tài nguyên backend vẫn tồn tại.

Mô hình phù hợp hơn:

1. Transaction ngắn: validate, CAS state transition, tạo operation và outbox event.
2. Commit transaction.
3. Worker nhận event và gọi backend.
4. Worker lưu external resource reference và tiến độ trong transaction riêng.
5. Worker cập nhật operation và instance bằng version/CAS.
6. Nếu có lỗi, retry hoặc compensation theo workflow.

~~~mermaid
sequenceDiagram
    participant API as OSB API
    participant DB as Broker DB
    participant Q as Outbox / Queue
    participant W as Worker
    participant BE as Backend

    API->>DB: CAS READY -> UPDATING
    API->>DB: Insert operation + outbox
    DB-->>API: Commit
    API-->>API: Return accepted response
    Q->>W: Operation event
    W->>DB: Claim operation with lease
    W->>BE: Apply resource change
    BE-->>W: Result
    W->>DB: Persist result with version check
~~~

Nếu worker không còn quyền cập nhật vì version đã thay đổi, nó phải dừng và đọc lại state. Không ghi đè một transition mới hơn.

## 6. Xử lý xung đột trong Spring

### 6.1. OptimisticLockException

Với JPA, một transaction có thể nhận OptimisticLockException khi version trong database khác version entity đang giữ. Spring có thể chuyển đổi exception này thành dạng DataAccessException phù hợp.

Cách xử lý:

- Rollback transaction hiện tại.
- Đọc lại entity trong transaction mới.
- Xác định state mới và operation hiện tại.
- Nếu request đã được xử lý bởi một tiến trình khác, trả kết quả hiện tại.
- Nếu request vẫn hợp lệ, tính toán lại command và thử transition mới.
- Nếu không còn hợp lệ, trả conflict hoặc lỗi nghiệp vụ.

Không retry mù quáng cùng một câu UPDATE với version cũ. Nó sẽ tiếp tục thất bại.

### 6.2. Unique constraint violation

Khi hai request cùng INSERT một instance hoặc binding, một transaction có thể thành công, transaction còn lại nhận lỗi unique constraint.

Ví dụ xử lý ở application service:

~~~java
public ProvisionDecision acceptProvision(ProvisionCommand command) {
    try {
        return transactionTemplate.execute(status ->
                createInstanceAndOperation(command)
        );
    } catch (DuplicateKeyException conflict) {
        return resolveExistingProvision(command);
    }
}
~~~

Đây là pseudocode. Cần bắt exception bên ngoài transaction đã rollback; không tiếp tục truy vấn trong transaction đang bị đánh dấu rollback-only.

Hàm resolveExistingProvision phải đọc bản ghi đã thắng cuộc đua:

- Nếu service ID, plan ID và request fingerprint khớp, trả kết quả hoặc operation hiện tại.
- Nếu cùng instance ID nhưng nội dung request khác, trả conflict.
- Nếu bản ghi thuộc platform/tenant khác, xử lý theo policy bảo mật và không tiết lộ dữ liệu.

### 6.3. Không biến mọi conflict thành retry

Có hai loại xung đột:

- **Transient conflict:** worker khác vừa cập nhật version; có thể đọc lại và thử lại nếu nghiệp vụ vẫn cho phép.
- **Business conflict:** instance đang DEPROVISIONING hoặc request yêu cầu plan không hợp lệ; retry không làm tình hình tốt hơn.

Chỉ retry khi có một điều kiện rõ ràng cho phép thử lại. Nếu không, trả lỗi sớm để platform hoặc người dùng điều chỉnh.

## 7. Kiểm soát cạnh tranh giữa request và worker

Một broker có thể nhận DELETE từ platform trong khi worker đang provision. Nếu request handler và worker không chia sẻ cùng một cơ chế state transition, chúng có thể cùng gọi backend.

Một cách tiếp cận:

- Mọi thay đổi lifecycle đều phải claim operation bằng transaction và CAS.
- Mỗi instance chỉ có một lifecycle operation active thuộc nhóm loại trừ nhau.
- Worker phải xác minh operation_id và version trước khi áp dụng từng bước quan trọng.
- Backend adapter phải nhận idempotency key ổn định.
- Khi deprovision được chấp nhận, worker provision cũ phải nhận biết state đã đổi và dừng hoặc chuyển sang compensation theo policy.

Ví dụ worker trước khi thực hiện bước tiếp theo:

~~~java
if (!operationRepository.isCurrentOwner(
        operation.id(),
        operation.leaseToken(),
        operation.expectedInstanceVersion())) {
    throw new StaleOperationException(operation.id());
}
~~~

Đây là kiểm tra minh họa. Có thể triển khai bằng lease, fencing token, version hoặc một tổ hợp. Việc kiểm tra phải có tính nguyên tử với thao tác claim hoặc state update; một SELECT độc lập rồi mới gọi backend vẫn có cửa sổ race.

### 7.1. Lease và fencing token

Lease cho worker quyền xử lý operation trong một khoảng thời gian. Fencing token là số tăng dần gắn với mỗi lần claim. Backend hoặc persistence layer có thể từ chối thao tác từ worker giữ token cũ.

Ví dụ:

| Claim | Worker | Fencing token |
|---|---|---:|
| Lần 1 | worker-A | 41 |
| Lần 2 sau khi lease hết hạn | worker-B | 42 |

Nếu worker-A tiếp tục sau khi worker-B đã claim, các cập nhật với token 41 phải bị từ chối. Lease đơn thuần không đủ vì worker cũ có thể vẫn chạy sau khi bị pause hoặc mất kết nối.

## 8. Concurrency và idempotency của binding

Binding cũng cần unique constraint và state transition riêng. Hai request bind có cùng binding ID không được tạo hai principal backend.

Một ràng buộc có thể là:

~~~sql
ALTER TABLE service_binding
ADD CONSTRAINT uq_instance_binding
UNIQUE (instance_id, binding_id);
~~~

Nếu binding ID là unique toàn cục trong broker, có thể dùng unique(binding_id). Chọn scope theo định danh mà platform và broker cam kết.

Khi bind:

1. Xác minh instance READY và thuộc tenant.
2. Insert binding ở trạng thái BINDING với unique key.
3. Ghi operation hoặc event nếu binding cần workflow nền nội bộ.
4. Tạo principal backend với idempotency key gắn binding ID.
5. Lưu secret reference và backend principal ID.
6. Chuyển binding sang BOUND bằng version/CAS.

Khi unbind:

1. Chuyển BOUND sang REVOKING bằng CAS.
2. Revoke principal backend.
3. Đánh dấu UNBOUND.
4. Request lặp nhận trạng thái hiện tại và không revoke nhầm principal khác.

Nếu hai request cùng bind và một request thắng unique constraint, request còn lại phải kiểm tra binding đã tồn tại và xác định có thể trả lại binding hiện tại hay cần conflict. Không tạo credentials mới trước khi claim được binding identity.

## 9. Unique constraint cho resource ledger và outbox

Các bảng phụ trợ cũng cần constraint để ngăn event hoặc resource reference trùng:

~~~sql
ALTER TABLE managed_resource
ADD CONSTRAINT uq_operation_step_resource
UNIQUE (operation_id, step_key);
~~~

~~~sql
ALTER TABLE outbox_event
ADD CONSTRAINT uq_outbox_event_id
UNIQUE (event_id);
~~~

Nếu mỗi operation step chỉ được ghi nhận một resource cho một loại resource, unique(operation_id, step_key) giúp ngăn hai worker lưu hai kết quả khác nhau. Nếu một step có thể tạo nhiều resource, dùng sequence hoặc resource key riêng thay vì ràng buộc quá chặt.

Outbox event có event_id ổn định. Publisher có thể gửi lại event nếu process chết sau khi publish nhưng trước khi đánh dấu published. Consumer dùng event_id hoặc operation_id để nhận diện message lặp.

Ràng buộc duy nhất bảo vệ dữ liệu broker; backend adapter vẫn cần idempotency key hoặc lookup để tránh tạo tài nguyên trùng ở hệ thống ngoài.

## 10. Chọn optimistic hay pessimistic locking?

Optimistic locking phù hợp khi xung đột hiếm và transaction ngắn. Pessimistic locking phù hợp khi xung đột thường xuyên hoặc cần tuần tự hóa một vùng dữ liệu trong transaction ngắn.

| Tiêu chí | Optimistic locking | Pessimistic locking |
|---|---|---|
| Cách hoạt động | So sánh version khi cập nhật | Khóa hàng hoặc tài nguyên trong transaction |
| Khi phù hợp | Đọc nhiều, ghi ít, xung đột thấp | Ghi cạnh tranh cao, cần tuần tự hóa |
| Chi phí | Có thể phải retry khi conflict | Có thể chờ lock và giữ connection |
| Rủi ro | Retry sai có thể ghi đè logic | Deadlock, lock timeout, contention |
| Phạm vi | Version trên bản ghi | Lock được database quản lý |
| Lời gọi backend dài | Không giữ transaction mở | Không giữ lock trong lúc gọi API ngoài |

Với service broker, optimistic locking thường là lựa chọn mặc định tốt cho instance và operation vì các thao tác backend dài nên nằm ngoài transaction database. Pessimistic lock có thể hữu ích trong transaction ngắn khi claim operation hoặc cập nhật một nhóm hàng có phụ thuộc chặt.

Không dùng SELECT FOR UPDATE rồi gọi cloud API trước khi commit. Điều đó giữ lock trong thời gian không kiểm soát được.

## 11. Thiết kế retry an toàn sau conflict

Retry phải bắt đầu bằng việc đọc lại trạng thái mới nhất và tính toán lại quyết định. Không lặp lại side effect bên ngoài chỉ vì database update bị conflict.

Một quy trình retry:

1. Rollback transaction có conflict.
2. Đọc instance, operation và resource ledger mới nhất.
3. Kiểm tra request còn hợp lệ không.
4. Xác định backend step trước đó đã chạy chưa.
5. Nếu backend side effect có thể đã xảy ra, tra cứu bằng idempotency key hoặc external reference.
6. Tạo transaction mới với expected version mới.
7. Thử state transition bằng CAS.
8. Chỉ gửi công việc mới sau khi transaction commit.

Ví dụ, worker gọi backend tạo database thành công nhưng cập nhật version thất bại vì một request khác đã deprovision instance. Worker không được tạo database lần nữa. Nó phải đọc state hiện tại, phát hiện instance đang bị xóa và chuyển resource vừa tạo vào compensation hoặc cleanup theo policy.

### 11.1. Giới hạn số lần retry

Retry optimistic conflict liên tục có thể gây livelock khi nhiều request cùng tranh chấp. Nên:

- Giới hạn số lần retry.
- Dùng backoff ngắn có jitter nếu xung đột có thể tự hết.
- Ghi metric conflict.
- Trả conflict khi trạng thái mới không cho phép request.
- Không retry lỗi validation, authorization hoặc unique conflict do request khác nội dung.

## 12. Kiểm thử cạnh tranh

Concurrency test cần chạy nhiều transaction hoặc request thật đồng thời, không chỉ gọi method tuần tự trong một unit test.

| Kịch bản | Kết quả mong đợi |
|---|---|
| Hai provision cùng instance ID và request giống nhau | Chỉ một instance/operation được tạo; request còn lại nhận kết quả tương ứng |
| Hai provision cùng ID nhưng plan khác nhau | Một request thắng; request còn lại nhận conflict |
| Hai bind cùng binding ID | Chỉ một binding/principal được tạo |
| Hai update cùng version | Một cập nhật thành công; cập nhật còn lại phát hiện optimistic conflict |
| Update và deprovision đồng thời | Chỉ một lifecycle transition thắng; không có hai backend workflow xung đột |
| Worker cũ cập nhật sau worker mới | Fencing/version từ chối worker cũ |
| Outbox event được gửi lặp | Consumer xử lý idempotent |
| Unbind được gửi hai lần | Principal chỉ bị revoke một cách an toàn |
| Unique constraint bị vi phạm | Application chuyển lỗi database thành kết quả nghiệp vụ phù hợp |
| Transaction rollback sau insert | Không có operation hoặc outbox event mồ côi |

### 12.1. Test optimistic locking

Một integration test có thể dùng hai transaction độc lập:

1. Transaction A đọc instance version 3.
2. Transaction B đọc cùng instance version 3.
3. B cập nhật state và commit, version thành 4.
4. A cố cập nhật với version 3.
5. A phải nhận optimistic lock conflict.
6. Database vẫn giữ thay đổi của B.

Không dùng cùng một persistence context cho cả hai transaction vì cache entity có thể làm test không phản ánh concurrency thực.

### 12.2. Test unique constraint

Chạy hai request provision đồng thời với cùng instance ID. Sau khi cả hai kết thúc, kiểm tra:

- Chỉ có một service_instance record.
- Chỉ có operation hợp lệ theo idempotency policy.
- Backend không có hai tài nguyên trùng.
- Request thua cuộc được ánh xạ thành kết quả idempotent hoặc conflict.
- Không có outbox event mồ côi.

Dùng database thực hoặc Testcontainers để kiểm tra constraint và isolation level. Mock repository không thể chứng minh database thực sự ngăn duplicate.

## 13. Quan sát và vận hành

Các metric cần theo dõi:

- Số optimistic lock conflict theo entity và operation type.
- Số unique constraint violation theo constraint.
- Số request bị từ chối do state transition không hợp lệ.
- Số operation active trên mỗi instance.
- Số lần worker lease hết hạn hoặc fencing token bị từ chối.
- Thời gian chờ lock và lock timeout nếu dùng pessimistic locking.
- Tỷ lệ retry thành công và số retry vượt giới hạn.
- Số backend resource được tạo trùng hoặc phát hiện orphan.

Log nên có instance_id, binding_id, operation_id, expected_version, actual_version, state transition và correlation ID. Không ghi credentials hoặc toàn bộ parameters nhạy cảm.

Khi điều tra một conflict, cần trả lời:

- Hai actor nào đã cập nhật cùng bản ghi?
- Transaction nào commit trước?
- State transition nào đã thắng?
- Worker có thực hiện side effect backend trước khi conflict không?
- Resource ledger có đủ thông tin để reconcile hoặc compensation không?

Không đưa instance ID hoặc tenant ID làm metric label nếu cardinality cao. Dùng label giới hạn như operation_type, entity_type, provider và result.

## 14. Những lỗi thiết kế thường gặp

- **Chỉ kiểm tra tồn tại trước INSERT:** race condition vẫn tạo duplicate nếu không có unique constraint.
- **Không có version field:** một worker có thể ghi đè state mới hơn.
- **Tự tăng @Version:** xung đột với cơ chế quản lý version của JPA.
- **Bắt conflict rồi tiếp tục trong transaction đã rollback-only:** thao tác tiếp theo có thể thất bại hoặc tạo trạng thái không nhất quán.
- **Retry cùng dữ liệu cũ:** optimistic conflict tiếp tục xảy ra.
- **Retry backend side effect không idempotent:** tạo database, user hoặc volume trùng.
- **Dùng synchronized trong JVM:** không bảo vệ nhiều pod hoặc nhiều process.
- **Giữ row lock khi gọi cloud API:** làm nghẽn database và tăng nguy cơ deadlock.
- **Không có unique key cho binding hoặc operation:** request lặp tạo principal hoặc workflow trùng.
- **Không kiểm soát operation active:** update và deprovision có thể chạy cùng lúc.
- **Dùng bulk update bỏ qua version:** mất bảo vệ optimistic locking.
- **Coi mọi conflict là lỗi 500:** làm platform retry sai cách và khó phân biệt lỗi nghiệp vụ.

## 15. Quy trình triển khai kiểm soát cập nhật cạnh tranh

Khi thiết kế một entity hoặc workflow mới cho broker, hãy thực hiện:

1. Xác định định danh và phạm vi uniqueness của instance, binding, operation và event.
2. Thêm primary key và unique constraints phù hợp trong database.
3. Thêm version field cho entity có nhiều actor cùng cập nhật.
4. Xác định state transition hợp lệ và điều kiện CAS.
5. Ghi state transition, operation và outbox trong transaction ngắn.
6. Không gọi backend trong transaction đang giữ row lock.
7. Dùng idempotency key cho backend step và message consumer.
8. Bắt optimistic conflict hoặc unique violation ở application boundary.
9. Đọc lại state mới nhất trước khi quyết định retry.
10. Giới hạn retry và phân biệt transient conflict với business conflict.
11. Dùng lease/fencing token nếu có worker phân tán.
12. Viết concurrency test với database thật.
13. Theo dõi conflict, retry, duplicate và operation bị kẹt.

## Kết luận

Khóa lạc quan, ràng buộc duy nhất và state transition có điều kiện bổ sung cho nhau trong việc bảo vệ dữ liệu service broker. Unique constraint ngăn tạo trùng khi nhiều request cùng kiểm tra một định danh; optimistic locking phát hiện cập nhật dựa trên dữ liệu cũ; compare-and-set bảo đảm chỉ transition hợp lệ mới được chấp nhận.

Trong Spring Cloud Service Broker, hãy kết hợp các cơ chế này với transaction ngắn, operation record, outbox, idempotent backend adapter và retry có kiểm soát. Mọi request HTTP, worker và reconciliation phải tuân theo cùng quy tắc cập nhật. Khi xung đột xảy ra, broker cần đọc lại trạng thái, xác minh side effect backend và quyết định tiếp tục, trả conflict hoặc compensation thay vì ghi đè dữ liệu mới hơn.
