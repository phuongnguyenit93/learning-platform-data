# Giới hạn của lưu trữ trong bộ nhớ và lựa chọn kho dữ liệu bền vững

Một service broker phải nhớ service instance nào đã được cấp phát, binding nào đang tồn tại, operation nào còn chạy và tài nguyên provider nào tương ứng với từng yêu cầu. Những dữ liệu này quyết định broker sẽ trả lời thế nào khi nền tảng retry request, khi một node khởi động lại hoặc khi nhiều node cùng nhận yêu cầu cho một instance.

Lưu trữ trong bộ nhớ (in-memory storage) rất tiện khi làm prototype hoặc kiểm thử, nhưng dữ liệu chỉ tồn tại trong vòng đời của tiến trình và thường chỉ được nhìn thấy bởi một node. Với broker chạy trên cloud, điều đó gây rủi ro mất trạng thái, tạo tài nguyên trùng lặp và trả lời không nhất quán. Trong module **SPRING_CLOUD_SERVICE_BROKER**, cần lựa chọn kho dữ liệu bền vững phù hợp với vòng đời của service instance, binding và operation; đồng thời tách dữ liệu nhạy cảm như credentials sang cơ chế quản lý secret phù hợp.

Bài học này phân tích giới hạn của bộ nhớ tiến trình, các lựa chọn lưu trữ, cách thiết kế dữ liệu và transaction, cùng ví dụ tích hợp persistence theo hướng Spring reactive. Mục tiêu là giúp broker phục hồi được sau sự cố, hỗ trợ nhiều replica và duy trì trạng thái nhất quán với nền tảng lẫn nhà cung cấp.

## 1. Broker cần lưu những trạng thái nào?

Service broker không chỉ là một HTTP endpoint chuyển tiếp request. Nó điều phối vòng đời tài nguyên ở hệ thống bên ngoài. Để làm việc đó an toàn, broker cần lưu dữ liệu đủ để trả lời những câu hỏi sau:

- Service instance nào đã được tạo, thuộc service và plan nào?
- Instance đó được cấp phát cho organization, space hoặc tenant nào?
- Tài nguyên tương ứng ở provider có ID gì và đang ở trạng thái nào?
- Binding nào đã cấp cho consumer nào, provider principal nào được tạo?
- Operation provision, update hoặc deprovision nào đang chạy?
- Request hiện tại là lần đầu hay là retry của một request đã xử lý?
- Nếu broker dừng giữa một bước, cần tiếp tục từ checkpoint nào?
- Khi provider trả kết quả không rõ ràng, cần đối soát bằng định danh nào?

Các nhóm dữ liệu phổ biến:

| Nhóm dữ liệu | Ví dụ | Vì sao cần lưu bền vững |
|---|---|---|
| Service instance | instance ID, service ID, plan ID, tenant, state | Xử lý các thao tác vòng đời và truy vấn lại sau restart |
| Binding | binding ID, instance ID, consumer, provider binding ID | Retry bind, unbind đúng principal và thu hồi quyền |
| Operation | operation ID, loại thao tác, state, provider operation ID | Theo dõi tác vụ bất đồng bộ và phục hồi worker |
| Idempotency | request fingerprint, idempotency key, kết quả đã xử lý | Ngăn tạo tài nguyên hoặc credentials trùng lặp |
| Provider reference | resource ID, region, account, endpoint tham chiếu | Đối chiếu broker với tài nguyên thực tế |
| Audit metadata | correlation ID, thời điểm, actor, mã kết quả | Truy vết thay đổi và hỗ trợ vận hành |
| Policy snapshot | phiên bản plan, retention hoặc lifecycle policy | Giữ đúng chính sách đã áp dụng cho instance hiện hữu |

Không phải mọi dữ liệu đều cần nằm trong cùng một database. Metadata vòng đời có thể nằm trong cơ sở dữ liệu quan hệ; operation event có thể được chuyển qua message broker; credentials có thể nằm trong secret manager. Điều quan trọng là mỗi loại dữ liệu có chủ sở hữu, vòng đời, quyền truy cập và cơ chế phục hồi rõ ràng.

## 2. Vì sao in-memory storage không đủ cho production?

In-memory storage thường là các cấu trúc như HashMap, ConcurrentHashMap hoặc một object repository giữ dữ liệu trong heap của JVM. Chúng đọc và ghi nhanh, dễ dựng và thuận tiện cho unit test. Tuy nhiên, bộ nhớ tiến trình không tự cung cấp độ bền, chia sẻ trạng thái giữa node hoặc khả năng khôi phục sau sự cố.

### Mất dữ liệu khi tiến trình dừng

Khi JVM restart, container bị thay thế, pod bị reschedule hoặc node gặp sự cố, dữ liệu trong heap biến mất. Nếu broker chỉ lưu instance trong HashMap, sau restart broker có thể không biết instance ID nào đã được provision.

Hệ quả nghiêm trọng hơn việc mất một bản ghi nội bộ: provider có thể vẫn đang chạy database hoặc queue đã tạo trước đó. Khi nền tảng retry provision, broker tưởng rằng instance chưa tồn tại và tạo thêm tài nguyên. Khi nền tảng gửi deprovision, broker lại không có provider resource ID để xóa đúng tài nguyên.

### Không chia sẻ dữ liệu giữa nhiều replica

Giả sử broker chạy ba pod sau một load balancer. Request provision đến pod A và lưu instance trong HashMap của A. Request bind tiếp theo có thể đến pod B. Pod B không nhìn thấy dữ liệu của A và kết luận instance không tồn tại.

Ngay cả khi sticky session giữ request ở cùng pod, cách đó không bảo đảm khi pod bị thay thế hoặc failover. Sticky session cũng không giải quyết việc worker chạy ở node khác cần đọc operation.

### Không giải quyết được request đồng thời

Hai request có thể cùng kiểm tra một instance hoặc binding chưa tồn tại, sau đó cùng tạo tài nguyên ở provider. ConcurrentHashMap bảo vệ một số thao tác trên map, nhưng không tự tạo ra transaction xuyên suốt giữa nhiều bước kiểm tra, ghi trạng thái và gọi provider.

Ví dụ, thao tác containsKey() rồi put() là hai bước riêng. Hai thread có thể cùng thấy key chưa tồn tại. Một cấu trúc thread-safe không đồng nghĩa toàn bộ nghiệp vụ đã atomic.

### Không có lịch sử và khả năng đối soát

Bộ nhớ tiến trình thường không lưu được lịch sử operation, provider request ID, lỗi cuối cùng hoặc checkpoint. Khi một thao tác timeout, đội vận hành khó xác định provider đã thực hiện hay chưa. Khi đó broker không thể phân biệt an toàn giữa retry và yêu cầu mới.

### TTL và eviction có thể xóa nhầm trạng thái quan trọng

Một cache có TTL hoặc eviction policy có thể loại bỏ dữ liệu khi bộ nhớ chịu áp lực. Điều đó chấp nhận được với dữ liệu có thể tính lại, nhưng rất nguy hiểm với instance, binding và operation đang cần phục hồi.

Không nên đặt service instance vào cache có TTL ngắn rồi coi cache là nguồn dữ liệu chính. Nếu cache bị mất, broker phải vẫn có thể tái tạo trạng thái từ kho dữ liệu bền vững.

### Sơ đồ rủi ro khi chỉ dùng bộ nhớ tiến trình

~~~mermaid
flowchart TD
    Platform["Cloud platform"] --> LB["Load balancer"]
    LB --> A["Broker pod A"]
    LB --> B["Broker pod B"]
    A --> MA["HashMap của A"]
    B --> MB["HashMap của B"]
    A --> Provider["Provider API"]
    B --> Provider
    Restart["A restart"] -. "heap bị xóa" .-> MA
    MA -. "không còn instance metadata" .-> Lost["Broker mất trạng thái"]
~~~

Mỗi pod có một vùng nhớ riêng. Provider vẫn giữ tài nguyên bên ngoài, trong khi broker có thể mất dữ liệu cần thiết để quản lý chúng. Đây là lý do trạng thái vòng đời phải được lưu ở một nơi bền vững và chia sẻ giữa các replica.

## 3. Khi nào in-memory storage vẫn phù hợp?

In-memory storage không phải lúc nào cũng sai. Nó phù hợp khi dữ liệu chỉ có giá trị trong phạm vi một tiến trình hoặc có thể tạo lại mà không gây side effect.

Các trường hợp thường phù hợp:

- Unit test cho service hoặc policy.
- Integration test dùng repository giả lập.
- Demo chạy một tiến trình, không quản lý tài nguyên thật.
- Cache metadata catalog có thể tải lại từ cấu hình hoặc database.
- Cache tạm cho dữ liệu provider có thể truy vấn lại.
- Buffer không phải nguồn dữ liệu duy nhất và có cơ chế phục hồi.

Ví dụ, một map ánh xạ ServiceId sang CatalogEntry có thể dùng làm cache vì catalog có thể được nạp lại từ cấu hình versioned. Ngược lại, map ánh xạ InstanceId sang ServiceInstance không nên là nguồn dữ liệu chính trong broker production.

Một quy tắc hữu ích: nếu mất dữ liệu đó có thể khiến broker tạo trùng tài nguyên, không thể thu hồi tài nguyên, cấp credentials sai hoặc không thể trả lời retry một cách nhất quán, dữ liệu đó cần được lưu bền vững.

## 4. Các lựa chọn kho dữ liệu bền vững

Không có một database duy nhất phù hợp với mọi broker. Lựa chọn phụ thuộc vào cấu trúc dữ liệu, transaction, quy mô, yêu cầu latency, vận hành và kỹ năng của đội ngũ.

| Lựa chọn | Điểm mạnh | Hạn chế/cần cân nhắc | Phù hợp với |
|---|---|---|---|
| Relational database (PostgreSQL, MySQL) | ACID transaction, unique constraint, quan hệ rõ, truy vấn và đối soát tốt | Cần quản lý schema, connection pool, migration và HA | Instance, binding, operation, quota và idempotency |
| Document database | Schema linh hoạt, lưu metadata lồng nhau thuận tiện | Transaction và consistency phụ thuộc sản phẩm/cấu hình; quan hệ cần thiết kế cẩn thận | Metadata thay đổi nhiều, document theo service |
| Key-value store | Tra cứu theo ID nhanh, thao tác đơn giản | Query và quan hệ phức tạp hạn chế; transaction tùy sản phẩm | Lookup, idempotency record hoặc trạng thái có key rõ |
| Distributed cache có persistence | Truy cập nhanh, chia sẻ giữa node, có thể hỗ trợ atomic operation | Persistence/replication có giới hạn và phải cấu hình; eviction vẫn là rủi ro | Cache, lock/lease có kiểm soát, dữ liệu phụ có thể phục hồi |
| Event log/message broker | Lưu chuỗi sự kiện, tách producer và worker, hỗ trợ replay tùy nền tảng | Không tự thay thế database truy vấn trạng thái; cần quản lý consumer offset và schema | Outbox event, tác vụ async, audit stream |
| File hoặc local disk | Đơn giản cho dữ liệu cục bộ | Không phù hợp nhiều replica, failover và volume ephemeral | Local development hoặc dữ liệu phụ không quan trọng |

### Relational database là lựa chọn mặc định hợp lý

Với phần lớn service broker, database quan hệ là điểm bắt đầu phù hợp cho metadata vòng đời. Các bảng instance, binding và operation có quan hệ rõ; unique constraint giúp bảo vệ định danh; transaction giúp reserve tài nguyên nội bộ trước khi gọi provider.

PostgreSQL hoặc MySQL có thể đáp ứng mô hình này. Chọn hệ thống mà đội ngũ có thể vận hành, backup, giám sát, nâng cấp và phục hồi đáng tin cậy.

### Document database khi metadata thực sự linh hoạt

Một số broker cung cấp nhiều loại service với parameters và metadata khác nhau. Document database có thể lưu cấu hình theo document linh hoạt. Tuy nhiên, các trường định danh như instance ID, binding ID, state và operation ID vẫn cần index và ràng buộc phù hợp.

Đừng chọn document database chỉ vì request OSB có JSON. Phần dữ liệu cần transaction và uniqueness vẫn phải được giải quyết rõ ràng.

### Distributed cache không mặc nhiên là database

Redis hoặc một hệ thống cache phân tán có thể chia sẻ dữ liệu giữa node, hỗ trợ TTL và atomic command. Nhưng nếu cấu hình eviction, persistence, replication hoặc failover không đáp ứng yêu cầu, dữ liệu vẫn có thể mất.

Dùng cache để tăng tốc truy vấn, không để cache là bản duy nhất của service instance hoặc binding. Nếu quyết định dùng một hệ thống key-value làm primary store, cần xác minh rõ độ bền, durability acknowledgement, backup, restore, replication và atomicity của đúng cấu hình triển khai.

## 5. Thiết kế schema cho instance, binding và operation

Một schema quan hệ đơn giản có thể bắt đầu từ ba bảng chính.

### Bảng service_instance

~~~sql
CREATE TABLE service_instance (
    instance_id          VARCHAR(255) PRIMARY KEY,
    service_id           VARCHAR(255) NOT NULL,
    plan_id              VARCHAR(255) NOT NULL,
    organization_guid    VARCHAR(255),
    space_guid           VARCHAR(255),
    provider_resource_id VARCHAR(512),
    provider_region      VARCHAR(128),
    state                VARCHAR(32) NOT NULL,
    version              BIGINT NOT NULL DEFAULT 0,
    request_fingerprint  VARCHAR(128),
    policy_version       VARCHAR(128),
    created_at           TIMESTAMP NOT NULL,
    updated_at           TIMESTAMP NOT NULL
);
~~~

Bảng này lưu định danh instance, service/plan, phạm vi sở hữu, tham chiếu provider và trạng thái. provider_resource_id có thể chưa có khi provision đang chạy. version hỗ trợ optimistic locking. request_fingerprint giúp phát hiện retry có nội dung khác.

### Bảng service_binding

~~~sql
CREATE TABLE service_binding (
    instance_id            VARCHAR(255) NOT NULL,
    binding_id             VARCHAR(255) NOT NULL,
    consumer_id            VARCHAR(255),
    provider_binding_id    VARCHAR(512),
    credential_secret_ref  VARCHAR(1024),
    state                  VARCHAR(32) NOT NULL,
    request_fingerprint    VARCHAR(128) NOT NULL,
    expires_at             TIMESTAMP,
    created_at             TIMESTAMP NOT NULL,
    updated_at             TIMESTAMP NOT NULL,
    PRIMARY KEY (instance_id, binding_id),
    FOREIGN KEY (instance_id)
        REFERENCES service_instance(instance_id)
);
~~~

Bảng binding lưu metadata và tham chiếu secret. Không nên đặt password plaintext vào các cột thông thường. Nếu broker hỗ trợ nhiều loại binding, có thể bổ sung loại binding, provider scope hoặc metadata JSON đã được lọc.

### Bảng broker_operation

~~~sql
CREATE TABLE broker_operation (
    operation_id           VARCHAR(255) PRIMARY KEY,
    instance_id            VARCHAR(255) NOT NULL,
    operation_type         VARCHAR(32) NOT NULL,
    state                  VARCHAR(32) NOT NULL,
    provider_operation_id  VARCHAR(512),
    request_fingerprint    VARCHAR(128),
    failure_code           VARCHAR(128),
    started_at             TIMESTAMP NOT NULL,
    updated_at             TIMESTAMP NOT NULL,
    completed_at           TIMESTAMP
);
~~~

Operation lưu tiến độ các thao tác dài như provision, update và deprovision. Có thể thêm binding_id hoặc step_name nếu operation gắn với binding hoặc có nhiều checkpoint.

Schema trên là ví dụ khởi đầu, không phải schema bắt buộc của OSB API. Tên cột, kiểu dữ liệu và index cần điều chỉnh theo database, độ dài định danh và quy mô thực tế.

### Các index và ràng buộc cần có

- Primary key hoặc unique constraint trên instance_id.
- Primary key tổng hợp (instance_id, binding_id) hoặc quy tắc duy nhất tương đương.
- Index trên (state, updated_at) để tìm operation bị treo.
- Index trên provider_resource_id nếu cần reconciliation theo provider.
- Index trên operation_type, state và started_at cho worker.
- Foreign key nếu mô hình dữ liệu và yêu cầu xóa cho phép.
- Unique constraint cho idempotency key trong phạm vi phù hợp.

Không chỉ dựa vào kiểm tra ở Java. Ràng buộc ở database là lớp bảo vệ cuối cùng khi nhiều replica cùng xử lý request.

## 6. Transaction và ranh giới với provider API

Một lỗi thiết kế phổ biến là mở transaction database, sau đó gọi API provider trong lúc transaction vẫn giữ lock. Provider có thể chậm vài giây hoặc vài phút; transaction dài làm tăng lock contention, connection usage và nguy cơ timeout.

Một transaction database cũng không thể tự rollback side effect đã xảy ra ở hệ thống provider độc lập. Nếu provider tạo database xong nhưng transaction broker rollback, tài nguyên provider vẫn tồn tại.

Cách tiếp cận tốt hơn:

1. Trong transaction ngắn, reserve instance hoặc binding ID.
2. Ghi operation và outbox event nếu cần chạy async.
3. Commit.
4. Gọi provider bên ngoài transaction.
5. Trong transaction mới, lưu provider result và cập nhật state.
6. Nếu kết quả không rõ, đánh dấu UNKNOWN/RECONCILIATION_REQUIRED và tra cứu provider trước khi retry.

~~~mermaid
sequenceDiagram
    participant API as Broker API
    participant DB as Durable database
    participant Worker
    participant Provider

    API->>DB: Transaction: reserve instance + operation + outbox
    DB-->>API: Commit
    API-->>API: Return accepted response if async is supported
    Worker->>DB: Claim pending outbox item
    Worker->>Provider: Provision with stable idempotency key
    Provider-->>Worker: Resource ID / provider operation
    Worker->>DB: Transaction: save result + update state
    DB-->>Worker: Commit
~~~

Với thao tác đồng bộ, handler vẫn có thể chờ provider và trả response sau khi hoàn tất. Nhưng reservation và state transition nên được ghi trong các transaction ngắn trước/sau lời gọi provider. Không giữ transaction mở chỉ để chờ network.

## 7. Outbox để phối hợp database và worker

Nếu broker dùng queue hoặc worker cho operation dài, cần tránh tình huống database đã ghi operation nhưng message không được gửi, hoặc message đã gửi nhưng transaction database rollback.

Transactional outbox giải quyết khoảng trống này bằng cách ghi event cùng transaction với dữ liệu nghiệp vụ:

~~~sql
CREATE TABLE broker_outbox (
    event_id       VARCHAR(255) PRIMARY KEY,
    aggregate_id   VARCHAR(255) NOT NULL,
    event_type     VARCHAR(128) NOT NULL,
    payload        TEXT NOT NULL,
    created_at     TIMESTAMP NOT NULL,
    published_at   TIMESTAMP
);
~~~

Luồng:

1. Transaction tạo instance ở trạng thái PROVISIONING.
2. Cùng transaction ghi operation và outbox event.
3. Commit.
4. Publisher đọc event chưa publish và gửi đến queue.
5. Sau khi xác nhận gửi, cập nhật published_at.
6. Worker nhận event và xử lý idempotent.
7. Worker cập nhật operation và instance.

Publisher có thể gửi lại event nếu mất xác nhận. Vì vậy worker phải nhận diện event đã xử lý hoặc dùng operation ID ổn định. Outbox cung cấp khả năng giao event ít nhất một lần trong mô hình thông dụng; không nên giả định message chỉ được xử lý đúng một lần.

Không nhất thiết mọi broker đều cần message queue ngay từ đầu. Với tác vụ ít và ngắn, một worker có thể poll bảng operation. Nhưng trạng thái operation vẫn cần lưu bền vững để broker phục hồi sau restart.

## 8. Chọn mô hình đồng bộ hay reactive cho persistence

Spring Cloud Open Service Broker thường tích hợp với ứng dụng Spring WebFlux và các service handler trả về Reactor Mono hoặc Flux. Persistence cần phù hợp với cách xử lý này.

Có hai hướng thường gặp:

| Hướng | Công nghệ ví dụ | Lưu ý |
|---|---|---|
| Reactive persistence | Spring Data R2DBC, reactive driver của database | Có thể giữ luồng non-blocking từ HTTP đến database |
| Blocking persistence | Spring Data JPA/JDBC | Cần quản lý blocking I/O đúng cách khi ứng dụng chạy WebFlux |

R2DBC phù hợp khi muốn duy trì reactive pipeline xuyên suốt. JPA/JDBC vẫn có thể dùng nếu tổ chức đã có nền tảng đó, nhưng không nên gọi blocking repository trực tiếp trên event-loop thread. Có thể cô lập tác vụ blocking trên scheduler phù hợp, song cần kiểm soát connection pool và backpressure.

Không chọn R2DBC chỉ vì handler trả Mono. Cần xem xét transaction support, driver maturity, query cần dùng, migration tool, observability và năng lực vận hành. Một hệ thống dùng JDBC được tổ chức tốt vẫn có thể phù hợp hơn một reactive stack chưa được đội ngũ vận hành thành thạo.

### Ví dụ repository reactive

~~~java
public interface ServiceInstanceRepository
        extends ReactiveCrudRepository<ServiceInstanceEntity, String> {

    Mono<ServiceInstanceEntity> findByProviderResourceId(
        String providerResourceId);

    Flux<ServiceInstanceEntity> findByStateAndUpdatedAtBefore(
        String state,
        Instant cutoff);
}
~~~

Đây là interface minh họa với Spring Data R2DBC. Cần có entity mapping, schema migration và cấu hình connection phù hợp. Tên query method phải khớp property của entity.

### Transaction reactive

Khi dùng R2DBC, transaction reactive cần được quản lý qua TransactionalOperator hoặc cơ chế transaction tương ứng của Spring. Không dùng transaction imperative rồi giả định nó tự truyền qua mọi thread trong Reactor.

Ví dụ khái niệm:

~~~java
public Mono<Reservation> reserve(
        ProvisionCommand command) {

    return transactionalOperator.transactional(
        repository.insertReservation(command)
            .flatMap(reservation ->
                operationRepository.insertProvisionOperation(
                    reservation)
                    .thenReturn(reservation)
            )
    );
}
~~~

Transaction ở đây chỉ bao gồm các thao tác database ngắn. Lời gọi provider phải nằm sau khi transaction đã hoàn tất.

## 9. Optimistic locking và kiểm soát cập nhật đồng thời

Nhiều request có thể cùng tác động đến một instance: update, bind, unbind hoặc deprovision. Broker cần bảo vệ state transition để không cho hai operation xung đột.

Một cách là optimistic locking. Bản ghi instance có cột version. Khi cập nhật, câu lệnh chỉ thành công nếu version vẫn là giá trị mà worker đã đọc:

~~~sql
UPDATE service_instance
SET state = 'UPDATING',
    version = version + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE instance_id = :instanceId
  AND version = :expectedVersion
  AND state = 'SUCCEEDED';
~~~

Nếu số dòng được cập nhật bằng 0, trạng thái đã thay đổi hoặc một operation khác đã thắng. Broker cần đọc lại và quyết định retry, trả conflict hoặc chờ theo policy.

Với thao tác cần khóa lâu, không nên giữ row lock trong suốt network call. Có thể reserve operation bằng state và lease có thời hạn; worker heartbeat để gia hạn lease. Khi worker chết, worker khác tiếp quản sau khi xác nhận lease hết hạn và trạng thái provider.

### State machine là nguồn quy tắc

Một state machine nội bộ giúp xác định chuyển trạng thái hợp lệ:

~~~mermaid
stateDiagram-v2
    [*] --> PROVISIONING
    PROVISIONING --> SUCCEEDED
    PROVISIONING --> FAILED
    SUCCEEDED --> UPDATING
    UPDATING --> SUCCEEDED
    UPDATING --> UPDATE_FAILED
    SUCCEEDED --> DEPROVISIONING
    DEPROVISIONING --> DEPROVISIONED
    DEPROVISIONING --> DEPROVISION_FAILED
~~~

Các tên trạng thái trên là ví dụ nội bộ. OSB API quy định hành vi và response mà broker phải cung cấp; ứng dụng có thể dùng state machine chi tiết hơn để điều phối. Mỗi transition cần có điều kiện, actor và audit event.

## 10. Lưu idempotency để retry an toàn

Nền tảng có thể retry provision, bind hoặc deprovision khi timeout. Broker cần lưu dấu vết request đã xử lý để xác định retry.

Một bảng idempotency có thể gồm:

~~~sql
CREATE TABLE broker_idempotency (
    scope_key           VARCHAR(512) PRIMARY KEY,
    request_fingerprint VARCHAR(128) NOT NULL,
    operation_id        VARCHAR(255),
    response_reference  VARCHAR(512),
    state               VARCHAR(32) NOT NULL,
    created_at          TIMESTAMP NOT NULL,
    expires_at          TIMESTAMP
);
~~~

scope_key có thể là tổ hợp operation type, instance ID và binding ID tùy thao tác. request_fingerprint được tạo từ payload đã chuẩn hóa. Không dùng request timestamp hoặc correlation ID làm thành phần quyết định nội dung.

Khi nhận request:

1. Tạo fingerprint.
2. Thử insert idempotency record.
3. Nếu insert thành công, request được quyền bắt đầu.
4. Nếu key đã tồn tại, đọc record hiện tại.
5. Fingerprint giống nhau: trả kết quả/operation hiện có hoặc chờ trạng thái hiện tại.
6. Fingerprint khác nhau: trả lỗi xung đột theo hợp đồng.
7. Khi hoàn tất, cập nhật response reference và state.

Không nhất thiết lưu toàn bộ response có credentials vào bảng idempotency. Lưu tham chiếu đến binding/secret record và dựng response từ nguồn được bảo vệ.

Thời hạn giữ idempotency record phải đủ dài để bao phủ retry của nền tảng, thời gian operation và cửa sổ đối soát. Không xóa record chỉ vì operation vừa thành công nếu request cũ vẫn có thể được gửi lại.

## 11. Tách credentials khỏi database nghiệp vụ

Service broker có thể xử lý username, password, access token, private key hoặc certificate. Những dữ liệu này cần mức bảo vệ cao hơn metadata thông thường.

Không nên lưu secret plaintext trong bảng service_binding, operation payload, outbox hoặc log. Một số lựa chọn:

- Secret manager như Vault hoặc dịch vụ quản lý secrets của cloud.
- KMS và envelope encryption nếu cần lưu ciphertext trong database.
- Mã hóa theo tenant hoặc theo instance để giới hạn phạm vi ảnh hưởng.
- Lưu credential_secret_ref trong binding record thay vì giá trị secret.
- Audit thao tác đọc, cập nhật, rotate và revoke secret.

Outbox event cũng cần được lọc. Chỉ gửi ID, operation type, resource reference và dữ liệu không nhạy cảm. Không đưa credentials vào message payload chỉ vì worker cần sử dụng chúng; hãy dùng secret reference và cấp quyền truy xuất theo identity của worker.

### Secret rotation và backup

Nếu database chứa ciphertext, backup database vẫn là dữ liệu nhạy cảm. Cần bảo vệ backup, khóa KMS và quyền restore. Khi xóa instance hoặc binding, broker phải xử lý cả secret reference và secret thực tế theo retention policy.

Nếu secret manager chỉ trả secret một lần, broker phải lưu an toàn trước khi trả response đầu tiên cho nền tảng. Nếu cần phát lại response khi retry, secret phải có thể được truy xuất theo binding ownership. Hash một chiều không đủ để dựng lại password ban đầu.

## 12. Catalog và cache khác với dữ liệu vòng đời

Catalog có thể được tạo từ cấu hình tĩnh, database quản trị hoặc một registry nội bộ. Cache catalog trong bộ nhớ có thể phù hợp vì dữ liệu có thể tải lại. Nhưng cache phải có cơ chế invalidation khi plan hoặc capability thay đổi.

Service instance, binding và operation có vòng đời khác. Chúng là trạng thái giao dịch mà broker phải khôi phục được sau restart.

| Dữ liệu | Có thể cache? | Nguồn dữ liệu chính nên là |
|---|---|---|
| Catalog definitions | Có, nếu có version/invalidation | Cấu hình versioned hoặc registry bền vững |
| Service instance | Có thể cache đọc | Database bền vững |
| Binding metadata | Có thể cache đọc | Database bền vững |
| Operation state | Cache chỉ hỗ trợ truy vấn | Database bền vững hoặc event store có projection đáng tin cậy |
| Provider resource status | Cache có TTL | Provider API kết hợp trạng thái broker |
| Credentials | Không cache tùy tiện | Secret manager hoặc encrypted secret store |
| Quota usage | Có thể cache ngắn hạn | Quota source có thẩm quyền và reservation store |

Nếu dùng cache, phải xác định cache miss, stale data và invalidation hoạt động thế nào. Một cache stale không được phép làm broker cấp lại credentials đã bị revoke hoặc cho phép update trên instance đang deprovision.

## 13. Backup, restore và disaster recovery

Lưu bền vững không chỉ là ghi database. Broker phải có kế hoạch phục hồi khi database bị lỗi, vùng cloud mất khả năng hoạt động hoặc dữ liệu bị xóa nhầm.

Các khía cạnh cần xác định:

- **RPO (Recovery Point Objective)**: mức dữ liệu tối đa có thể mất theo thời gian.
- **RTO (Recovery Time Objective)**: thời gian mục tiêu để khôi phục dịch vụ.
- Tần suất backup và thời gian giữ backup.
- Cơ chế point-in-time recovery nếu database hỗ trợ.
- Replication và failover.
- Mã hóa backup và quản lý khóa.
- Quy trình restore vào môi trường sạch.
- Đối soát provider resources sau restore.

### Vì sao restore database cần reconciliation?

Giả sử database broker được khôi phục từ backup cũ hơn trạng thái provider. Provider đã tạo thêm một database hoặc đã xóa một tài nguyên sau thời điểm backup. Broker có thể không có record tương ứng hoặc vẫn nghĩ tài nguyên còn tồn tại.

Sau restore, không nên lập tức xử lý mọi request như trạng thái đã chính xác. Cần:

1. Khởi động broker ở chế độ hạn chế nếu cần.
2. Đọc các instance và operation đang dở dang.
3. Tra cứu provider theo external reference hoặc tag ổn định.
4. Đối chiếu tài nguyên thực tế với record broker.
5. Phục hồi operation bị thiếu hoặc đánh dấu orphan resource.
6. Kiểm tra binding và credentials còn hiệu lực.
7. Chỉ mở lại luồng provisioning đầy đủ sau khi reconciliation đạt điều kiện.

Provider resource nên có tag hoặc external reference chứa broker instance ID, nhưng không đưa secret hoặc dữ liệu cá nhân vào tag. Định danh này giúp tìm tài nguyên khi broker mất một phần metadata.

## 14. Migration schema và tương thích dữ liệu

Schema broker sẽ thay đổi khi thêm capability, binding rotation, retention policy hoặc provider metadata. Cần quản lý migration có kiểm soát.

Nguyên tắc thường dùng:

- Dùng migration versioned như Flyway hoặc Liquibase.
- Thay đổi theo hướng tương thích ngược khi có thể.
- Thêm cột nullable hoặc có default trước khi code mới yêu cầu.
- Backfill dữ liệu theo batch có thể retry.
- Chỉ xóa cột cũ sau khi code và dữ liệu không còn phụ thuộc.
- Không đổi ý nghĩa của state cũ mà không có migration.
- Kiểm thử upgrade từ schema hiện tại và restore từ backup.

Với broker chạy nhiều replica trong rolling deployment, có thể tồn tại hai phiên bản ứng dụng cùng truy cập database. Migration cần tương thích trong giai đoạn chuyển tiếp; không triển khai thay đổi schema phá vỡ node cũ trước khi chúng được thay thế.

Dữ liệu instance cũ cũng có thể cần policy snapshot. Nếu plan thay đổi hoặc bị ngừng cung cấp, broker vẫn phải biết plan và policy nào áp dụng khi instance được tạo để xử lý update, bind và deprovision.

## 15. Ví dụ PersistenceService trong Spring

Một service có thể đóng vai trò điều phối việc reserve instance và tạo operation trước khi gọi provider.

Ví dụ abstraction:

~~~java
public interface InstanceStateStore {
    Mono<ServiceInstance> find(String instanceId);

    Mono<Reservation> reserveProvision(
        ProvisionCommand command);

    Mono<ServiceInstance> markProvisioned(
        Reservation reservation,
        ProviderResource resource);

    Mono<ServiceInstance> markFailed(
        Reservation reservation,
        String safeFailureCode);
}
~~~

Một implementation khái niệm:

~~~java
@Service
public class ProvisioningStateService {

    private final InstanceStateStore stateStore;
    private final ProviderAdapter provider;

    public ProvisioningStateService(
            InstanceStateStore stateStore,
            ProviderAdapter provider) {
        this.stateStore = stateStore;
        this.provider = provider;
    }

    public Mono<ServiceInstance> provision(
            ProvisionCommand command) {

        return stateStore.reserveProvision(command)
            .flatMap(reservation -> {
                if (reservation.isExisting()) {
                    return Mono.just(reservation.instance());
                }

                return provider.provision(
                        command,
                        command.idempotencyKey())
                    .flatMap(resource ->
                        stateStore.markProvisioned(
                            reservation, resource))
                    .onErrorResume(error ->
                        stateStore.markFailed(
                                reservation,
                                safeFailureCode(error))
                            .then(Mono.error(error)));
            });
    }
}
~~~

Đây là skeleton minh họa, không phải class có sẵn trong Spring Cloud Open Service Broker. Repository, Reservation, ProviderAdapter và các model thuộc ứng dụng. Trong production, cần phân biệt lỗi provider chắc chắn thất bại với timeout có kết quả chưa rõ; không đánh dấu FAILED và tạo lại tài nguyên nếu provider có thể đã provision thành công.

Với operation dài, thay lời gọi provider trực tiếp bằng outbox/worker. Handler OSB gọi service này và ánh xạ kết quả sang response theo hợp đồng. Persistence layer không nên phụ thuộc trực tiếp vào HTTP request object của framework; dùng command và entity nội bộ để dễ kiểm thử và thay đổi provider.

## 16. Kiểm thử persistence và khả năng phục hồi

Kiểm thử cần xác nhận dữ liệu còn tồn tại sau restart, nhiều node nhìn thấy cùng trạng thái và request đồng thời không tạo side effect trùng.

| Tình huống | Kết quả cần xác nhận |
|---|---|
| Broker restart sau provision | Instance vẫn được tìm thấy |
| Request tiếp theo đến node khác | Node đó đọc được cùng instance state |
| Hai request provision cùng instance ID | Unique constraint chỉ cho một reservation |
| Hai bind cùng binding ID | Chỉ một provider binding được tạo |
| Broker dừng sau provider success, trước DB update | Reconciliation tìm lại provider resource |
| Worker restart giữa operation | Operation được tiếp tục từ checkpoint |
| Outbox event gửi lặp | Worker xử lý idempotent |
| Cache bị xóa | Broker tải lại từ nguồn bền vững |
| Database failover | Broker kết nối lại và không làm mất trạng thái đã commit theo durability contract |
| Restore từ backup | Reconciliation phát hiện khác biệt với provider |
| Migration schema | Dữ liệu cũ được giữ và node tương thích trong rolling deploy |
| Secret manager unavailable | Không trả credentials giả hoặc tạo binding không thể phục hồi |
| Operation stale | Monitoring phát hiện và reconciliation xử lý |

Dùng Testcontainers hoặc database test phù hợp để kiểm tra repository và constraint trên loại database thật. Unit test với mock repository không thể chứng minh unique constraint, isolation level hoặc hành vi transaction của database.

## 17. Những lỗi thường gặp

**Dùng HashMap làm nguồn dữ liệu production.** Restart hoặc request đến node khác sẽ làm mất trạng thái. Chuyển instance, binding và operation sang kho bền vững.

**Cho rằng ConcurrentHashMap bảo đảm idempotency.** Nó không bảo vệ transaction nghiệp vụ giữa nhiều node hoặc giữa database và provider. Dùng unique constraint, reservation và provider idempotency key.

**Dùng cache làm nguồn dữ liệu chính.** TTL hoặc eviction có thể xóa trạng thái quan trọng. Cache chỉ nên tăng tốc dữ liệu có thể tải lại.

**Mở transaction database trong lúc gọi provider.** Network call dài làm giữ lock và connection. Dùng transaction ngắn trước/sau side effect.

**Lưu credentials plaintext cùng metadata.** Điều này mở rộng phạm vi rò rỉ. Tách secret sang secret manager hoặc encrypted store.

**Chỉ backup database mà không kiểm tra restore.** Backup có thể thiếu khóa giải mã hoặc không khớp trạng thái provider. Phải diễn tập restore và reconciliation.

**Không dùng unique constraint.** Kiểm tra tồn tại ở Java không ngăn được race condition. Để database bảo vệ định danh ở lớp cuối.

**Xóa operation ngay khi hoàn tất.** Mất lịch sử cần cho retry, audit và đối soát. Dùng retention cho operation metadata thay vì xóa tùy tiện.

**Cho rằng reactive nghĩa là không cần transaction.** Reactive thay đổi cách thực thi I/O, không loại bỏ yêu cầu atomicity và consistency. Cần dùng transaction manager phù hợp với driver.

## 18. Nguyên tắc lựa chọn cho Spring Cloud Service Broker

Với broker chạy một hoặc nhiều replica, hãy dùng một kho dữ liệu bền vững làm nguồn sự thật cho service instance, binding, operation và idempotency. Database quan hệ thường là lựa chọn phù hợp vì có transaction, unique constraint và truy vấn đối soát rõ ràng. Có thể bổ sung message queue cho công việc dài, cache để tăng tốc và secret manager để bảo vệ credentials.

Giữ ranh giới rõ giữa metadata vòng đời và secret. Ghi trạng thái trước khi gọi provider, không giữ transaction mở qua network call, dùng outbox khi cần phối hợp database với worker và dùng idempotency key ổn định để xử lý retry. Khi provider trả kết quả không rõ hoặc broker phục hồi từ backup, reconciliation phải đối chiếu record nội bộ với tài nguyên thực tế.

In-memory storage vẫn hữu ích cho test, demo và cache có thể tái tạo. Nhưng dữ liệu quyết định việc tạo, cấp quyền, cập nhật và thu hồi tài nguyên phải tồn tại ngoài vòng đời của một JVM. Lựa chọn kho dữ liệu đúng giúp broker phục hồi sau restart, hoạt động nhất quán trên nhiều node và duy trì được hợp đồng với nền tảng cũng như nhà cung cấp.

