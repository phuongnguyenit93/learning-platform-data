# Nhật ký thao tác, hộp thư giao dịch và tránh thất lạc tác vụ

Một service broker thường phải phối hợp nhiều hệ thống trong cùng một thao tác vòng đời. Khi platform yêu cầu provision, broker có thể phải lưu service instance, ghi nhận operation, gửi công việc cho worker, gọi API của nhà cung cấp rồi cập nhật trạng thái để platform truy vấn qua last_operation. Những bước này không nằm trong cùng một giao dịch cơ sở dữ liệu. Nếu tiến trình dừng đúng lúc giữa hai bước, broker có thể đã ghi nhận yêu cầu nhưng chưa gửi job, hoặc đã gửi job nhưng chưa lưu được kết quả.

Nhật ký thao tác (operation journal) và transactional outbox/inbox giúp giải quyết vấn đề đó. Operation journal lưu trạng thái và lịch sử của thao tác. Outbox ghi sự kiện cần gửi trong cùng transaction với thay đổi dữ liệu nghiệp vụ. Một publisher chuyển sự kiện từ outbox tới queue hoặc message broker. Inbox ở phía consumer giúp nhận diện message đã xử lý để việc giao nhận lặp không tạo tác dụng phụ trùng lặp.

Trong Spring Cloud service broker, các mẫu này giúp broker tiếp nhận yêu cầu OSB một cách bền vững, trả phản hồi asynchronous khi phù hợp, phục hồi sau restart và xử lý retry an toàn. Bài học tập trung vào cách thiết kế dữ liệu, ranh giới transaction, relay, worker, idempotency, quan sát và phục hồi khi có lỗi.

## 1. Vì sao cần operation journal và outbox?

Giả sử platform gửi yêu cầu tạo một PostgreSQL service instance. Broker cần thực hiện các việc:

1. Lưu service instance ở trạng thái PROVISIONING.
2. Tạo operation để platform có thể theo dõi.
3. Gửi job cho worker.
4. Worker gọi provider để tạo database.
5. Lưu provider resource ID và trạng thái mới.
6. Trả kết quả qua endpoint last_operation.

Nếu broker chỉ lưu instance rồi gọi queue riêng rẽ, có thể xảy ra tình huống transaction database commit thành công nhưng việc gửi message thất bại. Instance bị kẹt ở PROVISIONING mà không có worker nào tiếp tục.

Tình huống ngược lại cũng có thể xảy ra: broker gửi message thành công, nhưng transaction lưu instance bị rollback. Worker nhận được một job không có bản ghi nghiệp vụ tương ứng.

Một lỗi khác xuất hiện khi broker lưu operation rồi trả HTTP 202 trước khi job được ghi nhận bền vững. Nếu process bị dừng sau response, platform tiếp tục polling nhưng không có worker xử lý thao tác.

Transactional outbox giải quyết khoảng trống giữa ghi database và gửi message bằng cách lưu sự kiện cần phát ngay trong cùng transaction với thay đổi nghiệp vụ. Operation journal giữ trạng thái để worker và endpoint last_operation cùng nhìn thấy một nguồn sự thật.

~~~mermaid
flowchart LR
    P[Platform] --> H[OSB Handler]
    H --> T[Database transaction]
    T --> I[(Service instance)]
    T --> O[(Operation journal)]
    T --> X[(Outbox)]
    X --> R[Outbox relay]
    R --> Q[Message queue]
    Q --> W[Background worker]
    W --> V[Provider API]
    W --> I
    W --> O
    P --> L[Last operation]
    L --> O
~~~

Các thành phần có vai trò riêng:

- Service instance lưu trạng thái và định danh tài nguyên được broker quản lý.
- Operation journal lưu từng thao tác provision, update hoặc deprovision.
- Outbox lưu sự kiện cần chuyển tới hệ thống xử lý nền.
- Relay chuyển sự kiện từ database tới queue.
- Worker thực hiện nghiệp vụ và cập nhật trạng thái.
- Inbox hoặc bảng idempotency ở consumer ghi nhận message đã được xử lý.

## 2. Phân biệt operation journal, outbox và inbox

Ba khái niệm này liên quan nhưng không thay thế nhau.

| Thành phần | Câu hỏi nó trả lời | Dữ liệu điển hình |
|---|---|---|
| Operation journal | Thao tác vòng đời đang ở trạng thái nào và đã đi qua những bước nào? | Operation ID, instance ID, loại thao tác, state, error, timestamps |
| Outbox | Sự kiện nào đã được commit và cần gửi tới consumer? | Event ID, aggregate ID, event type, payload, publish state |
| Inbox | Consumer đã nhận và xử lý message nào? | Consumer name, event ID, processed timestamp |
| Service instance | Tài nguyên dịch vụ hiện có trạng thái và mapping nào? | Instance ID, service/plan ID, tenant, provider resource ID |

Operation journal là dữ liệu nghiệp vụ. Outbox là cơ chế phát sự kiện đáng tin cậy. Inbox hỗ trợ xử lý message lặp ở consumer.

Một operation có thể tạo nhiều outbox event, ví dụ OperationAccepted, ProviderResourceCreated và OperationCompleted. Một outbox event có thể được gửi lại nhiều lần; consumer dùng inbox hoặc idempotency key để không áp dụng tác dụng phụ lặp.

Không nên dùng bảng outbox làm nơi duy nhất để hiển thị trạng thái operation cho platform. Outbox thường được dọn sau khi publish và không nhất thiết giữ đầy đủ lịch sử nghiệp vụ.

## 3. Operation journal cho service broker

Một thao tác OSB nên có định danh riêng và liên kết với service instance. Ví dụ operation provision có thể lưu:

| Trường | Mục đích |
|---|---|
| operation_id | ID thao tác mà broker dùng để theo dõi |
| service_instance_id | Instance được thao tác |
| operation_type | PROVISION, UPDATE hoặc DEPROVISION |
| state | Trạng thái hiện tại |
| description | Mô tả an toàn để trả qua last_operation |
| request_fingerprint | Dấu vân tay request để nhận diện retry |
| target_plan_id | Plan đích nếu là update |
| provider_operation_id | ID tác vụ của provider nếu có |
| attempt_count | Số lần xử lý |
| created_at | Thời điểm nhận yêu cầu |
| started_at | Thời điểm bắt đầu xử lý |
| completed_at | Thời điểm kết thúc |
| last_error_code | Mã lỗi đã chuẩn hóa |

Ví dụ schema SQL:

~~~sql
CREATE TABLE broker_operation (
    operation_id VARCHAR(255) PRIMARY KEY,
    service_instance_id VARCHAR(255) NOT NULL,
    operation_type VARCHAR(40) NOT NULL,
    state VARCHAR(40) NOT NULL,
    description VARCHAR(500),
    request_fingerprint VARCHAR(128),
    target_plan_id VARCHAR(255),
    provider_operation_id VARCHAR(512),
    attempt_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    last_error_code VARCHAR(100),
    version BIGINT NOT NULL DEFAULT 0
);

CREATE INDEX idx_operation_instance_created
    ON broker_operation(service_instance_id, created_at);
CREATE INDEX idx_operation_state_created
    ON broker_operation(state, created_at);
~~~

Một instance có thể có nhiều operation theo thời gian. Vì vậy, không nên đặt service_instance_id làm khóa chính của operation journal. Cần operation_id riêng để phân biệt nhiều lần update hoặc các thao tác tiếp nối trên cùng instance.

Nếu chính sách yêu cầu mỗi instance chỉ có một thao tác thay đổi tài nguyên đang chạy, có thể bổ sung ràng buộc hoặc cơ chế khóa để chỉ có một operation thuộc nhóm trạng thái active cho một instance tại một thời điểm.

## 4. Lịch sử chuyển trạng thái

Một cột state chỉ cho biết trạng thái hiện tại. Khi điều tra sự cố, người vận hành thường cần biết thao tác đã đi qua bước nào, lúc nào, worker nào xử lý và vì sao thất bại.

Có thể bổ sung operation_event để lưu lịch sử:

~~~sql
CREATE TABLE operation_event (
    event_id VARCHAR(255) PRIMARY KEY,
    operation_id VARCHAR(255) NOT NULL,
    previous_state VARCHAR(40),
    next_state VARCHAR(40) NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    details JSON,
    occurred_at TIMESTAMP NOT NULL,
    FOREIGN KEY (operation_id)
        REFERENCES broker_operation(operation_id)
);

CREATE INDEX idx_operation_event_time
    ON operation_event(operation_id, occurred_at);
~~~

Ví dụ lịch sử của một lần provision:

| Thời điểm | Sự kiện | Trạng thái |
|---|---|---|
| 10:00:00 | Request accepted | ACCEPTED |
| 10:00:01 | Job enqueued | QUEUED |
| 10:00:03 | Worker claimed | RUNNING |
| 10:00:08 | Provider create submitted | WAITING_PROVIDER |
| 10:01:12 | Provider resource ready | SUCCEEDED |

Lịch sử này giúp trả lời request đã được nhận chưa, job đã được gửi chưa, worker đã bắt đầu chưa và provider đã tạo tài nguyên chưa.

Operation journal và event history nên được cập nhật trong transaction nhất quán. Nếu chỉ cập nhật state mà không lưu event, hoặc ghi event mà state không đổi, dữ liệu có thể khó diễn giải. Có thể dùng một service transition duy nhất để kiểm tra trạng thái hiện tại, ghi state mới và thêm event trong cùng transaction.

Không đưa password, token, private key, connection string có credential hoặc payload nhạy cảm vào event details. Operation history thường được nhiều công cụ vận hành truy cập hơn secret store.

## 5. Outbox giải quyết khoảng trống transaction như thế nào?

Database transaction thường không thể bao trùm đồng thời database của broker và một message broker bên ngoài. Nếu broker thực hiện:

~~~text
BEGIN DATABASE TRANSACTION
  INSERT service_instance
  INSERT broker_operation
COMMIT

SEND MESSAGE TO QUEUE
~~~

thì process có thể dừng sau COMMIT nhưng trước SEND MESSAGE. Dữ liệu đã lưu, message chưa được gửi.

Nếu đảo thứ tự:

~~~text
SEND MESSAGE TO QUEUE

BEGIN DATABASE TRANSACTION
  INSERT service_instance
  INSERT broker_operation
COMMIT
~~~

thì message có thể được consumer xử lý trong khi transaction database thất bại.

Transactional outbox đặt message cần gửi vào một bảng cùng database. Bản ghi nghiệp vụ và outbox event được commit hoặc rollback cùng nhau:

~~~text
BEGIN DATABASE TRANSACTION
  INSERT service_instance
  INSERT broker_operation
  INSERT outbox_event
COMMIT
~~~

Sau commit, relay đọc outbox và gửi message. Nếu transaction rollback, cả dữ liệu nghiệp vụ lẫn event đều không tồn tại. Nếu commit thành công, event đã được lưu bền vững để relay có thể gửi lại sau restart.

Đây là bảo đảm quan trọng: broker không bị mất dấu việc cần xử lý giữa thao tác ghi database và gửi message.

## 6. Thiết kế bảng outbox

Một bảng outbox cơ bản có thể gồm:

~~~sql
CREATE TABLE outbox_event (
    event_id VARCHAR(255) PRIMARY KEY,
    aggregate_type VARCHAR(100) NOT NULL,
    aggregate_id VARCHAR(255) NOT NULL,
    event_type VARCHAR(150) NOT NULL,
    payload JSON NOT NULL,
    created_at TIMESTAMP NOT NULL,
    published_at TIMESTAMP,
    publish_attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMP,
    last_error_code VARCHAR(100)
);

CREATE INDEX idx_outbox_pending
    ON outbox_event(published_at, next_attempt_at, created_at);
~~~

Ý nghĩa các trường:

- event_id là ID duy nhất, giữ nguyên qua mọi lần gửi lại.
- aggregate_type cho biết event thuộc loại dữ liệu nào, ví dụ ServiceInstance hoặc BrokerOperation.
- aggregate_id thường là instance ID hoặc operation ID.
- event_type xác định loại công việc, ví dụ ProvisionRequested.
- payload chứa dữ liệu tối thiểu để consumer thực hiện công việc.
- published_at cho biết relay đã ghi nhận việc gửi thành công hay chưa.
- publish_attempts và next_attempt_at hỗ trợ retry có backoff.
- last_error_code lưu mã lỗi đã chuẩn hóa, không lưu thông tin bí mật.

Payload nên chứa định danh tham chiếu và dữ liệu cần thiết cho worker, chẳng hạn operation ID, instance ID và loại thao tác. Worker có thể tải dữ liệu nghiệp vụ mới nhất từ database theo ID. Cách này tránh đưa một bản sao lớn hoặc nhạy cảm của toàn bộ request vào message.

Nếu payload cần lưu snapshot của request, phải canonicalize, giới hạn kích thước và loại bỏ secret. Broker có thể lưu secret reference thay vì secret value.

## 7. Ghi operation và outbox trong cùng transaction

Khi platform gửi provision, handler cần xác thực request và chuẩn bị operation. Trong một transaction database, broker tạo instance, operation và outbox event.

Ví dụ Java dùng Spring:

~~~java
@Service
public class ProvisionAcceptanceService {

    private final ServiceInstanceRepository instances;
    private final OperationRepository operations;
    private final OutboxRepository outbox;

    public ProvisionAcceptanceService(
            ServiceInstanceRepository instances,
            OperationRepository operations,
            OutboxRepository outbox) {
        this.instances = instances;
        this.operations = operations;
        this.outbox = outbox;
    }

    @Transactional
    public AcceptedOperation accept(ProvisionCommand command) {
        var instance = ServiceInstanceEntity.provisioning(command);
        instances.save(instance);

        var operation = BrokerOperation.accepted(
                command.serviceInstanceId(),
                "PROVISION");
        operations.save(operation);

        var event = OutboxEvent.provisionRequested(
                operation.getOperationId(),
                command.serviceInstanceId());
        outbox.save(event);

        return new AcceptedOperation(
                operation.getOperationId());
    }
}
~~~

Các factory method trong ví dụ đại diện cho constructor hoặc mapper của ứng dụng. Điểm quan trọng là ba thao tác ghi nằm trong cùng một transaction do Spring quản lý.

Sau khi method commit thành công, handler có thể chuyển operation ID thành response OSB 202 nếu request cho phép asynchronous operation. Nếu commit thất bại, không được trả 202 vì broker chưa lưu được một yêu cầu có thể phục hồi.

Không nên gọi provider API hoặc publish queue trực tiếp bên trong transaction này. Gọi hệ thống bên ngoài trong khi giữ transaction có thể kéo dài khóa database và vẫn không tạo được transaction phân tán nguyên tử.

## 8. Outbox relay chuyển event tới queue

Relay là tiến trình đọc các event chưa publish và gửi chúng tới message broker. Relay có thể chạy định kỳ hoặc liên tục.

Một chu trình cơ bản:

1. Lấy một batch event chưa publish và đã đến thời điểm retry.
2. Claim event để tránh nhiều relay xử lý cùng lúc.
3. Gửi message tới queue.
4. Khi broker message xác nhận nhận, đánh dấu event đã publish.
5. Nếu gửi lỗi, tăng số lần thử và lên lịch retry.
6. Tiếp tục với batch tiếp theo.

~~~mermaid
sequenceDiagram
    participant DB as Outbox Database
    participant R as Relay
    participant Q as Message Queue
    R->>DB: Claim pending events
    DB-->>R: Event batch
    R->>Q: Publish event
    Q-->>R: Broker acknowledgment
    R->>DB: Mark published
~~~

Cần chú ý cửa sổ lỗi giữa publish và đánh dấu published. Nếu queue đã nhận message nhưng relay bị dừng trước khi cập nhật database, event vẫn được coi là pending. Relay sẽ gửi lại sau khi khởi động. Vì vậy, outbox relay thường cung cấp giao nhận ít nhất một lần (at-least-once), không phải exactly-once.

Consumer phải xử lý message lặp an toàn. Không nên cố gắng loại bỏ mọi duplicate chỉ bằng trạng thái published của outbox, vì không thể atomically commit trạng thái database và acknowledgment của queue nếu hai hệ thống không cùng transaction.

## 9. Claim event an toàn khi có nhiều relay

Trong môi trường nhiều replica, nhiều relay có thể cùng đọc outbox. Nếu tất cả cùng chọn một hàng pending trước khi hàng được cập nhật, một event có thể được publish nhiều lần gần như đồng thời.

Có thể dùng row locking và SKIP LOCKED trên PostgreSQL để mỗi relay claim một batch riêng:

~~~sql
BEGIN;

WITH picked AS (
    SELECT event_id
    FROM outbox_event
    WHERE published_at IS NULL
      AND (next_attempt_at IS NULL
           OR next_attempt_at <= CURRENT_TIMESTAMP)
    ORDER BY created_at
    FOR UPDATE SKIP LOCKED
    LIMIT 100
)
UPDATE outbox_event o
SET publish_attempts = publish_attempts + 1
FROM picked
WHERE o.event_id = picked.event_id
RETURNING o.*;

COMMIT;
~~~

Đây là ví dụ claim đơn giản. Trong production, nên có lease hoặc trạng thái CLAIMED với owner và thời hạn. Nếu relay chết sau khi claim nhưng trước khi publish, event cần tự trở lại trạng thái có thể claim khi lease hết hạn.

Không giữ transaction và row lock trong lúc gọi network tới queue. Hãy claim ngắn, commit, publish bên ngoài transaction rồi cập nhật kết quả bằng một transaction khác. Khi cập nhật, kiểm tra lease owner hoặc fencing token để một relay cũ không ghi đè kết quả của relay mới đã tiếp quản.

Một thiết kế khác dùng cột claimed_until, claimed_by và claim_token. Claim token tăng hoặc thay đổi theo mỗi lần nhận quyền; update cuối cùng chỉ thành công nếu token vẫn khớp.

## 10. Inbox giúp consumer xử lý message lặp

Queue có thể giao cùng message nhiều lần khi consumer xử lý xong nhưng chưa ack, hoặc ack bị mất. Inbox lưu event ID đã xử lý để consumer nhận diện duplicate.

Ví dụ schema:

~~~sql
CREATE TABLE inbox_message (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(255) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Consumer thực hiện insert inbox và cập nhật dữ liệu nghiệp vụ trong cùng transaction:

~~~java
@Transactional
public void handle(ProvisionRequested event) {
    boolean firstDelivery = inboxRepository
            .insertIfAbsent("provision-worker", event.eventId());

    if (!firstDelivery) {
        return;
    }

    operationService.markQueuedForExecution(event.operationId());
    jobRepository.createWorkItem(event.operationId());
}
~~~

Method insertIfAbsent phải được triển khai bằng câu lệnh có xử lý conflict nguyên tử, chẳng hạn INSERT ... ON CONFLICT DO NOTHING trên PostgreSQL. Không nên thực hiện SELECT trước rồi INSERT sau vì hai consumer đồng thời có thể cùng thấy chưa tồn tại.

Nếu xử lý nghiệp vụ và ghi inbox cùng transaction, khi transaction rollback thì cả hai cùng rollback. Khi queue giao lại, consumer có thể thử lại. Khi transaction commit, event ID đã được ghi nhận và lần giao tiếp theo được bỏ qua.

Nếu consumer phải gọi provider API trực tiếp, inbox không tự bảo đảm provider call chỉ chạy một lần. Tác dụng phụ bên ngoài cần idempotency key, provider operation ID hoặc một state machine riêng. Inbox chỉ ngăn lặp phần xử lý đã nằm trong transaction consumer.

## 11. Outbox và inbox không tạo exactly-once cho toàn hệ thống

Một hệ thống có thể kết hợp outbox, queue acknowledgment và inbox, nhưng vẫn không thể giả định toàn bộ chuỗi database → queue → provider là một transaction exactly-once.

Ví dụ worker gọi provider tạo database thành công rồi bị dừng trước khi commit kết quả vào database broker. Queue giao lại message. Nếu worker gọi create lần nữa mà không có idempotency, provider có thể tạo database thứ hai.

Cần kết hợp nhiều cơ chế:

- Outbox để không mất event sau khi commit dữ liệu nghiệp vụ.
- At-least-once delivery để event cuối cùng được thử gửi lại.
- Inbox để bỏ qua message đã xử lý trong transaction consumer.
- Idempotency key để provider nhận diện yêu cầu lặp.
- Provider lookup hoặc tag để đối soát khi không biết call trước đã thành công chưa.
- Operation state machine để chỉ cho phép transition hợp lệ.
- Reconciliation để phát hiện trạng thái lệch giữa broker và provider.

Mục tiêu thực tế thường là **effectively-once**: message có thể được giao nhiều lần nhưng các tác dụng phụ được kiểm soát để kết quả nghiệp vụ chỉ được ghi nhận một lần theo định danh operation.

## 12. Worker claim và thực thi operation

Sau khi consumer nhận event, worker cần claim operation để chỉ một worker xử lý tại một thời điểm. Có thể lưu trạng thái RUNNING, worker ID, lease expiration và số lần thử.

Ví dụ:

~~~sql
UPDATE broker_operation
SET state = 'RUNNING',
    started_at = COALESCE(started_at, CURRENT_TIMESTAMP),
    attempt_count = attempt_count + 1,
    version = version + 1
WHERE operation_id = :operation_id
  AND state IN ('ACCEPTED', 'QUEUED', 'RETRY_WAIT');
~~~

Nếu số hàng cập nhật bằng 1, worker đã claim thành công. Nếu bằng 0, operation có thể đã được worker khác claim hoặc đã kết thúc. Worker phải đọc lại trạng thái và quyết định bỏ qua, chờ hoặc xử lý theo chính sách.

Lease giúp phục hồi khi worker chết. Ví dụ worker A claim operation nhưng process bị dừng. Sau thời hạn lease, worker B có thể tiếp quản. Cần fencing token hoặc version để worker A nếu quay lại muộn không thể ghi đè kết quả do worker B đã hoàn thành.

Worker nên cập nhật operation và instance trong transaction ngắn sau mỗi bước quan trọng. Không giữ transaction mở trong lúc gọi provider.

## 13. Transaction boundary khi gọi provider

Provider API và database broker là hai hệ thống riêng. Không thể mặc định một transaction Spring @Transactional bao trùm cả hai.

Một quy trình provision có thể được chia:

| Bước | Transaction database | Tác động bên ngoài |
|---|---|---|
| Nhận yêu cầu | Lưu instance, operation, outbox | Chưa gọi provider |
| Worker bắt đầu | Claim operation | Chưa gọi provider |
| Tạo tài nguyên | Lưu trạng thái trước call nếu cần | Gọi provider create |
| Ghi kết quả | Lưu provider resource ID và trạng thái | Provider đã tạo tài nguyên |
| Hoàn tất | Commit operation SUCCEEDED, instance ACTIVE | Có thể kiểm tra provider |

Nếu provider create thành công nhưng transaction ghi resource ID thất bại, broker cần có cách truy tìm tài nguyên đã tạo. Idempotency key, deterministic resource tag hoặc provider operation ID có thể hỗ trợ.

Nếu provider API trả operation ID, worker lưu ID đó rồi tiếp tục polling hoặc nhận callback. Không đánh dấu operation thành công chỉ vì provider đã chấp nhận request; cần chờ tiêu chí hoàn tất của nghiệp vụ.

Đây là một quy trình kiểu saga: nhiều bước commit độc lập, có trạng thái trung gian và có hành động bù trừ khi cần. Một số bước không thể rollback hoàn toàn, nên reconciliation và can thiệp vận hành vẫn cần thiết.

## 14. Spring @Transactional và các điểm dễ sai

Spring quản lý transaction thông qua proxy hoặc cơ chế tương ứng của cấu hình. Một số lỗi triển khai thường gặp:

- Gọi method @Transactional từ method khác trong cùng object (self-invocation) có thể không đi qua proxy transaction theo cấu hình proxy mặc định.
- Bắt exception rồi không ném lại hoặc không đánh dấu rollback có thể khiến transaction commit dù nghiệp vụ thất bại.
- Gọi network trong transaction dài làm giữ connection và lock không cần thiết.
- Dùng event in-memory sau commit không tương đương transactional outbox; process có thể dừng sau commit trước khi listener xử lý.
- Reactive transaction có cách quản lý context khác imperative transaction; cần dùng transaction operator hoặc cấu hình reactive transaction manager phù hợp với R2DBC.

Nếu ứng dụng dùng JPA/JDBC blocking, transaction thường được quản lý theo thread. Nếu dùng R2DBC reactive, transaction context gắn với reactive pipeline. Không trộn hai mô hình một cách tùy tiện.

Ví dụ với R2DBC có thể dùng TransactionalOperator:

~~~java
return transactionalOperator.transactional(
        instanceRepository.save(instance)
                .then(operationRepository.save(operation))
                .then(outboxRepository.save(event))
);
~~~

Đoạn code thể hiện ba thao tác repository nằm trong một reactive transaction nếu chúng dùng cùng reactive connection factory và transaction manager. Nếu repository dùng JPA/JDBC, không dùng ví dụ này như thể nó tự tạo reactive transaction.

## 15. Vì sao không chỉ dùng @TransactionalEventListener?

Spring có thể phát application event sau khi transaction commit thông qua @TransactionalEventListener. Điều này hữu ích để tách logic nội bộ trong cùng process, nhưng listener không tự bảo đảm message bền vững.

Một tình huống:

1. Transaction commit thành công.
2. Process dừng ngay sau commit.
3. Listener chưa chạy hoặc chưa gửi message.
4. Khi process khởi động lại, application event trong memory không còn.

Nếu yêu cầu là không được thất lạc công việc sau commit, outbox là lựa chọn phù hợp hơn. Có thể dùng listener để đánh thức relay sớm, nhưng outbox database vẫn là nguồn sự thật; relay định kỳ phải tìm lại mọi event chưa publish.

Không nên dùng event listener làm cơ chế duy nhất để đưa operation sang worker nếu platform đã nhận 202 và đang trông đợi thao tác hoàn tất.

## 16. Retry, backoff và dead-letter handling

Không phải lỗi nào cũng nên retry giống nhau.

| Nhóm lỗi | Ví dụ | Hành vi |
|---|---|---|
| Lỗi tạm thời | Timeout mạng, HTTP 503, rate limit | Retry với exponential backoff và jitter |
| Lỗi xác thực/cấu hình | Credential provider sai, plan không hợp lệ | Dừng retry tự động, cảnh báo vận hành |
| Lỗi nghiệp vụ | Quota hết, instance không cho phép update | Đánh dấu failed theo contract |
| Kết quả không xác định | Provider timeout sau khi có thể đã tạo resource | Tra cứu operation/resource trước khi retry |
| Message lỗi không thể xử lý | Payload thiếu field bắt buộc hoặc version không hỗ trợ | Đưa vào dead-letter queue hoặc quarantine |

Exponential backoff có thể tính:

~~~text
delay = min(max_delay, base_delay * 2^attempt) + jitter
~~~

Jitter giúp nhiều worker không cùng retry tại một thời điểm. Cần giới hạn số lần thử, tổng thời gian retry và deadline nghiệp vụ.

Khi vượt ngưỡng, message có thể được đưa vào dead-letter queue để điều tra. Operation cần chuyển sang trạng thái FAILED hoặc NEEDS_ATTENTION theo chính sách, kèm error code an toàn. Không được để operation ở RUNNING vô thời hạn chỉ vì worker liên tục retry.

## 17. Đảm bảo thứ tự event theo instance

Một instance có thể có nhiều operation: provision, update rồi deprovision. Nếu event được xử lý sai thứ tự, worker có thể chạy deprovision trước khi provision hoàn tất hoặc update trên tài nguyên chưa tồn tại.

Có một số chiến lược:

- Partition queue theo service_instance_id để event cùng instance vào cùng partition.
- Dùng sequence number hoặc aggregate version trong event.
- Chỉ cho phép một operation thay đổi tài nguyên active trên một instance.
- Kiểm tra expected state và version trước mỗi transition.
- Lưu event đến sau ở trạng thái chờ nếu operation trước chưa hoàn tất.

Không nên dựa hoàn toàn vào thứ tự gửi message. Nhiều queue bảo đảm thứ tự trong phạm vi partition hoặc queue cụ thể, nhưng retry, nhiều consumer và dead-letter có thể ảnh hưởng thứ tự thực tế.

Một event có thể mang aggregate_version. Consumer chỉ áp dụng event nếu version tiếp theo đúng với trạng thái hiện tại. Nếu event đến trễ hoặc thiếu một phiên bản, consumer có thể trì hoãn và yêu cầu reconciliation.

## 18. Quan sát và vận hành outbox

Outbox cần được theo dõi như một thành phần vận hành, không chỉ là bảng phụ trong database.

Các metric hữu ích:

- Số lượng outbox event đang pending.
- Tuổi của event pending lâu nhất.
- Số lần publish retry.
- Tỷ lệ publish thành công/thất bại.
- Số message duplicate mà inbox bỏ qua.
- Số operation đang RUNNING quá thời hạn.
- Thời gian từ operation accepted tới worker started.
- Thời gian từ worker started tới operation completed.
- Số operation cần operator can thiệp.

Nên tạo cảnh báo khi:

- Outbox backlog tăng liên tục.
- Event pending lâu hơn SLA.
- Relay không publish được trong một khoảng thời gian.
- Queue có nhiều dead-letter message.
- Worker lease hết hạn quá thường xuyên.
- Operation không có tiến triển hoặc provider operation bị treo.

Log cần có correlation ID, operation ID, service instance ID và event ID để nối các bước. Các định danh này không thay thế phân quyền và cần tránh đưa dữ liệu nhạy cảm vào log.

## 19. Dọn dẹp dữ liệu và lưu giữ lịch sử

Outbox, inbox và operation journal có tốc độ tăng khác nhau. Cần có chính sách retention:

- Outbox đã publish có thể được archive hoặc xóa sau thời hạn audit phù hợp.
- Inbox cần giữ đủ lâu để message cũ không bị xử lý lại khi queue replay.
- Operation journal có thể cần giữ lâu hơn để hỗ trợ last_operation retry, audit và điều tra.
- Operation event history có thể được partition theo thời gian.
- Dead-letter message cần được lưu cho tới khi điều tra và xử lý xong.

Không xóa outbox pending hoặc operation active chỉ vì chúng cũ. Trước khi cleanup, cần kiểm tra trạng thái, lease, provider operation và quy trình phục hồi. Với inbox, retention phải dài hơn khoảng thời gian tối đa mà hệ thống có thể replay message; nếu xóa inbox quá sớm, message cũ có thể tạo tác dụng phụ lại.

Dữ liệu lịch sử nên được giới hạn quyền truy cập. Nếu operation details chứa request parameters, hãy loại bỏ secret hoặc mã hóa trường nhạy cảm trước khi lưu.

## 20. Ví dụ tình huống lỗi và cách phục hồi

### 20.1. Database commit thành công, relay chưa gửi message

- Operation và outbox đã commit.
- Relay chưa chạy hoặc process dừng.
- Khi relay hoạt động lại, nó tìm event pending và gửi.
- Platform vẫn truy vấn last_operation và thấy trạng thái đang chờ.

Không mất job vì event đã được lưu trong cùng transaction.

### 20.2. Queue nhận message, relay chưa đánh dấu published

- Queue đã nhận event.
- Relay bị dừng trước khi cập nhật published_at.
- Relay gửi lại event khi restart.
- Consumer nhận duplicate và inbox bỏ qua lần xử lý đã commit.

Có thể có hai delivery nhưng chỉ một lần xử lý nghiệp vụ trong transaction consumer.

### 20.3. Worker gọi provider thành công, chưa lưu resource ID

- Provider đã tạo database.
- Worker bị dừng trước khi ghi mapping.
- Queue giao lại event.
- Worker kiểm tra operation và provider idempotency key hoặc tìm resource theo tag.
- Broker gắn lại provider resource ID thay vì tạo resource thứ hai.

Nếu provider không hỗ trợ lookup hay idempotency, cần có quy trình reconciliation hoặc can thiệp vận hành; không thể bảo đảm không trùng chỉ bằng outbox.

### 20.4. Worker hoàn tất nhưng chưa ack queue

- Worker đã commit operation SUCCEEDED.
- Process dừng trước khi ack.
- Queue giao message lại.
- Inbox hoặc operation state cho biết công việc đã hoàn tất.
- Worker bỏ qua tác dụng phụ và ack message.

## 21. Ví dụ luồng provision hoàn chỉnh

Giả sử platform gửi provision cho instance-123 và broker cần tạo PostgreSQL trên provider.

1. Handler xác thực request, service ID, plan ID và tenant.
2. Một transaction lưu service instance PROVISIONING, operation ACCEPTED và outbox event ProvisionRequested.
3. Transaction commit.
4. Handler trả 202 cùng operation ID nếu platform đã gửi accepts_incomplete=true.
5. Relay claim event và publish vào queue.
6. Worker nhận message, ghi inbox và claim operation.
7. Worker gọi provider bằng idempotency key gắn với operation.
8. Provider trả operation ID hoặc resource ID.
9. Worker lưu mapping và tiếp tục polling provider nếu cần.
10. Khi database sẵn sàng, worker cập nhật instance ACTIVE và operation SUCCEEDED.
11. Platform gọi last_operation và nhận succeeded.
12. Nếu message được giao lại, inbox và operation state ngăn tạo database trùng.

~~~mermaid
sequenceDiagram
    participant P as Platform
    participant H as Broker Handler
    participant DB as Broker Database
    participant R as Outbox Relay
    participant Q as Queue
    participant W as Worker
    participant V as Provider
    P->>H: Provision request
    H->>DB: Instance + operation + outbox
    DB-->>H: Commit
    H-->>P: 202 Accepted + operation ID
    R->>DB: Read/claim outbox
    R->>Q: Publish event
    Q-->>W: ProvisionRequested
    W->>DB: Inbox + claim operation
    W->>V: Create database (idempotency key)
    V-->>W: Provider operation/resource ID
    W->>V: Check readiness
    V-->>W: Ready
    W->>DB: Instance ACTIVE, operation SUCCEEDED
    P->>H: GET last_operation
    H->>DB: Read operation
    DB-->>H: SUCCEEDED
    H-->>P: Operation completed
~~~

Luồng này tách request HTTP khỏi công việc dài nhưng vẫn bảo đảm mỗi giai đoạn có dữ liệu bền vững để phục hồi.

## 22. Checklist triển khai

- [ ] Operation journal có operation ID riêng và liên kết service instance.
- [ ] Trạng thái hiện tại và lịch sử transition được lưu nhất quán.
- [ ] Service instance, operation và outbox event được ghi trong cùng transaction.
- [ ] Chỉ trả 202 sau khi transaction nhận yêu cầu đã commit.
- [ ] Outbox relay có cơ chế claim/lease khi chạy nhiều replica.
- [ ] Relay retry publish an toàn và giữ event ID ổn định.
- [ ] Consumer dùng inbox hoặc cơ chế idempotency nguyên tử.
- [ ] Provider call có idempotency key hoặc cơ chế lookup/reconciliation.
- [ ] Worker claim operation có lease hoặc optimistic locking.
- [ ] Provider call không nằm trong transaction database kéo dài.
- [ ] Message ordering và xung đột operation trên cùng instance được kiểm soát.
- [ ] Có exponential backoff, jitter, retry limit và dead-letter handling.
- [ ] last_operation đọc trạng thái từ kho dữ liệu bền vững.
- [ ] Có metric cho outbox backlog, worker lag và operation treo.
- [ ] Retention của outbox, inbox và operation history được xác định.
- [ ] Không lưu secret hoặc dữ liệu nhạy cảm trong event payload và log.
- [ ] Đã thử các cửa sổ lỗi: commit trước publish, publish trước mark, provider success trước DB update và worker success trước ack.

Operation journal, transactional outbox và inbox tạo thành nền tảng tin cậy cho các tác vụ dài trong service broker. Journal cho biết thao tác đang ở đâu; outbox bảo đảm sự kiện cần xử lý không bị mất giữa commit và publish; inbox giúp consumer chịu được message giao lặp. Kết hợp chúng với worker idempotent, provider reconciliation và state transition có kiểm soát, broker có thể tiếp tục provision, update hoặc deprovision sau timeout, restart và lỗi mạng mà vẫn giữ được trạng thái nhất quán để platform theo dõi.

