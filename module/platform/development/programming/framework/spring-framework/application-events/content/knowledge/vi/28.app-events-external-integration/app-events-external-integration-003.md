# Đảm bảo publish ra ngoài sau commit trong Spring Framework Application Events

## 1. Bài toán: dữ liệu đã commit nhưng hệ thống ngoài không nhận được event

Giả sử một dịch vụ xử lý đơn hàng cần thực hiện đồng thời hai việc:

1. Ghi trạng thái đơn hàng vào database.
2. Gửi sự kiện `OrderCommitted` cho Kafka, RabbitMQ, webhook hoặc một dịch vụ bên ngoài để tiếp tục xử lý.

Nếu gửi event **trước khi transaction commit**, bên nhận có thể thấy sự kiện rồi hành động, nhưng transaction nguồn sau đó rollback. Nếu chỉ gửi **sau commit**, database đã có kết quả đúng, nhưng process có thể crash, mạng có thể đứt hoặc broker có thể từ chối thông điệp trước khi gửi xong. Đây là bài toán **dual write**: database và broker là hai hệ thống có ranh giới commit khác nhau.

```text
BEGIN TRANSACTION
    UPDATE orders SET status = 'CONFIRMED'
    broker.send(OrderCommitted)   <-- broker nhận được
ROLLBACK                          <-- đơn hàng không được commit!

Hoặc:

BEGIN TRANSACTION
    UPDATE orders SET status = 'CONFIRMED'
COMMIT                            <-- đơn đã được lưu
process crash / broker timeout    <-- event chưa được gửi!
```

Hai rủi ro đối xứng:

- **Ghost event:** event xuất hiện bên ngoài dù thay đổi nghiệp vụ đã rollback.
- **Lost event:** thay đổi nghiệp vụ đã commit nhưng event cần thông báo không bao giờ được chuyển ra ngoài.

Spring Application Events cung cấp `@TransactionalEventListener(phase = AFTER_COMMIT)` để **không chạy callback trước một lần commit thành công**. Tuy nhiên, callback này vẫn ở **trong bộ nhớ của process**; nếu process chết sau commit mà trước khi gửi, callback có thể không bao giờ thực hiện được. Vì vậy cần phân biệt “chỉ phát sau commit” và “bảo đảm eventual publish sau commit”.

### Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt `AFTER_COMMIT`, `AFTER_ROLLBACK`, `BEFORE_COMMIT` và `AFTER_COMPLETION`.
- Hiểu vì sao `@EventListener` đồng bộ gọi broker bên trong transaction có thể tạo ghost event.
- Dùng `@TransactionalEventListener(AFTER_COMMIT)` cho công việc **best-effort**, và biết rõ cửa sổ crash của nó.
- Hiểu khi ghi database trong callback hậu commit phải có transaction mới, ví dụ `REQUIRES_NEW`.
- Thiết kế **transactional outbox**: bản ghi event được lưu **cùng transaction nghiệp vụ**, relay độc lập chỉ gửi các bản ghi đã commit.
- Xây retry, broker confirmation, đánh dấu gửi, idempotency và cơ chế claim nhiều worker.
- Kiểm thử rollback, broker lỗi tạm thời và tình huống “đã gửi nhưng chưa đánh dấu gửi”.
- Phân biệt **at-least-once publication** với exactly-once effect ở consumer và tính nhất quán cuối cùng.

Chủ đề thuộc nhóm **Tích hợp ngoài ứng dụng** trong Spring Framework Application Events. Trọng tâm không chỉ là annotation, mà là **thiết kế chính xác ranh giới transaction giữa Spring, database và dịch vụ bên ngoài**.

## 2. Cần định nghĩa “đảm bảo” trước khi chọn giải pháp

Câu “publish ra ngoài sau commit” có ít nhất bốn mức yêu cầu:

| Yêu cầu | Diễn giải | Cơ chế điển hình |
| --- | --- | --- |
| Không gửi khi rollback | Transaction thất bại thì không tạo tác dụng phụ ngoài từ event đó | Callback `AFTER_COMMIT` hoặc outbox ghi trong transaction |
| Chỉ gửi sau khi dữ liệu commit | Hệ thống ngoài có thể đọc trạng thái đã commit ở nguồn | Callback sau commit hoặc relay outbox |
| Event đã commit không bị mất khi process crash | Có bằng chứng bền vững để retry sau restart | **Transactional outbox** + relay/recovery |
| Không tạo tác dụng phụ trùng ở đích | Retry/redelivery vẫn không tạo hai hóa đơn, hai email | **Consumer idempotency**, unique business key, provider idempotency |

**`@TransactionalEventListener(AFTER_COMMIT)` đáp ứng mục tiêu về thời điểm callback trong điều kiện process sống**, nhưng **không một mình đáp ứng durability**. Với nghiệp vụ quan trọng, transactional outbox là giải pháp phổ biến để xử lý dual write mà không cần transaction phân tán giữa database và broker.

Định nghĩa chính xác hơn cho hệ thống đáng tin:

> Nếu và chỉ nếu transaction nghiệp vụ commit thành công, database phải có một bản ghi event/outbox tương ứng. Một relay có khả năng phục hồi sẽ tiếp tục thử publish cho đến khi có bằng chứng hệ thống ngoài chấp nhận theo hợp đồng, với giả định hạ tầng được phục hồi và relay tiếp tục chạy. Duplicate vẫn có thể xảy ra; consumer phải chịu được.

Đây là bảo đảm **có điều kiện**, không phải lời hứa “event luôn được giao đúng một lần trong mọi trường hợp” bất kể mất dữ liệu, ngừng vận hành vô thời hạn hay không có consumer.

## 3. Spring ApplicationEventPublisher thực sự làm gì?

Một service có thể phát POJO hoặc Java record:

```java
public record OrderCommitted(
        String eventId,
        String orderId
) {}

publisher.publishEvent(
        new OrderCommitted("evt-100", "ORD-42"));
```

Đây là snippet tích hợp; cần khai báo `ApplicationEventPublisher publisher`. Spring Framework hỗ trợ `publishEvent(Object)`; với object không extends `ApplicationEvent`, Spring có thể bọc thành `PayloadApplicationEvent<T>` rồi phân phối cho `@EventListener` nhận đúng payload type.

**Hợp đồng này là publication bên trong application context**, không phải việc:

- Ghi event vào message broker.
- Ghi event vào event store.
- Bảo đảm retry sau crash.
- Bảo đảm tất cả listener đã xử lý xong theo thời điểm cụ thể.
- Bảo đảm only-once/exactly-once.
- Tự đồng bộ transaction của database với Kafka/RabbitMQ/HTTP.

Một adapter có thể lắng nghe local event rồi gửi ra ngoài, nhưng **giữa local event và external broker vẫn có ranh giới failure** cần xử lý.

### Ba tầng nên tách trong suy nghĩ

```text
Business service
  |
  | publishEvent(OrderCommitted)
  v
Spring ApplicationEventMulticaster       <- local/in-process
  |
  v
@EventListener / @TransactionalEventListener
  |
  | KafkaTemplate.send / RabbitTemplate.convertAndSend /
  | HTTP client / email provider
  v
External system                          <- process/network boundary
```

Không được dùng cùng một từ “publish” rồi vô tình đánh đồng **local publish đã gọi** với **broker đã xác nhận lưu thông điệp**.

## 4. Cách 1: @TransactionalEventListener(AFTER_COMMIT)

Với Spring transaction quản lý bằng `PlatformTransactionManager` trong ứng dụng thread-bound, listener có thể gắn với pha transaction:

```java
@Component
public class OrderCommittedPublisher {
    private final ExternalEventGateway gateway;

    public OrderCommittedPublisher(ExternalEventGateway gateway) {
        this.gateway = gateway;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderCommitted(OrderCommitted event) {
        gateway.publish(event);
    }
}
```

Đây là **mẫu tích hợp**, không phải chương trình chạy độc lập: cần `ExternalEventGateway` và các import phù hợp. Khi `OrderCommitted` được phát **trong một transaction đang hoạt động** và transaction commit thành công, Spring gọi callback sau commit. Nếu rollback, callback `AFTER_COMMIT` không được gọi. Nếu event phát ngoài transaction, callback **mặc định không chạy**, do `fallbackExecution = false`.

Đây là cách hợp lý cho các tác vụ **best-effort** không cần durability cao, ví dụ thông báo cache invalidation có thể tái dựng, metric phụ trợ hoặc tín hiệu đánh thức một worker khác đã có bản ghi công việc bền vững.

### Vòng đời cơ bản

```text
Transaction T1
    |
    +--> persist order
    +--> publishEvent(OrderCommitted)
    |
    +--> COMMIT thành công
            |
            +--> @TransactionalEventListener(AFTER_COMMIT)
                     |
                     +--> gateway.publish(...)
```

**Quan trọng:** “callback chạy sau commit” không có nghĩa “broker chắc chắn đã chấp nhận event”. Nếu gateway timeout, trả lỗi, process crash hoặc mạng không ổn định, việc gửi vẫn có thể thất bại.

### 4.1. Các phase

| `TransactionPhase` | Khi nào callback chạy? | Dùng cho mục đích gì? |
| --- | --- | --- |
| `BEFORE_COMMIT` | Trước khi commit, lúc commit còn có thể thất bại | Kiểm tra/đồng bộ công việc vẫn thuộc transaction; **không phù hợp gửi event ngoài đòi hỏi đã commit** |
| `AFTER_COMMIT` | Sau khi transaction commit thành công | Gửi tín hiệu best-effort; callback hậu commit |
| `AFTER_ROLLBACK` | Sau khi transaction rollback | Cleanup/telemetry phù hợp với rollback; tránh làm effect của thành công |
| `AFTER_COMPLETION` | Sau khi transaction kết thúc, dù commit hay rollback | Theo dõi/cleanup theo outcome |

`@TransactionalEventListener` mặc định dùng `AFTER_COMMIT`; ghi tường minh `phase` giúp người đọc hiểu mục đích. `AFTER_COMPLETION` không phải lựa chọn phù hợp nếu chỉ muốn gửi thông điệp “OrderCommitted” khi đơn đã commit, bởi nó có thể được gọi cả lúc rollback.

### 4.2. fallbackExecution

Mặc định:

```java
@TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT,
        fallbackExecution = false)
public void handle(OrderCommitted event) {
    // ...
}
```

Nếu không có transaction hoạt động, listener không được gọi. Bật `fallbackExecution=true` cho phép listener chạy dù không có transaction nguồn; nhưng **lúc đó không còn ý nghĩa xác nhận commit của transaction nguồn**. Với sự kiện phải bảo đảm chỉ xuất hiện sau commit, đừng bật fallback chỉ vì thấy callback không chạy — phải sửa nơi publish để có transaction đúng hoặc thiết kế đường xử lý riêng.

### 4.3. Reactive transaction cần xử lý khác

Từ Spring Framework 6.1, `@TransactionalEventListener` cũng có thể dùng với reactive transaction, nhưng transaction context của reactive pipeline nằm trong **Reactor Context**, không phải ThreadLocal thông thường. Trường hợp này cần cách publication và event source/context phù hợp, thường thông qua `TransactionalEventPublisher`. Không lấy snippet imperative với `TransactionTemplate` rồi coi như chạy tương đương trong toàn bộ WebFlux/R2DBC.

## 5. Những giới hạn của AFTER_COMMIT

### 5.1. Cửa sổ mất event

```text
T0  begin transaction
T1  update order
T2  publish local event (register after-commit callback)
T3  database COMMIT thành công
T4  process crash                <- CỬA SỔ MẤT EVENT
T5  callback không bao giờ chạy
T6  external broker không biết order đã commit
```

Ngay cả khi code hoàn toàn đúng về `@TransactionalEventListener`, vẫn có thể mất thông báo ở T4. Callback chỉ sống trong runtime; Spring không tự persist nó để chạy sau restart.

### 5.2. Network timeout và trạng thái không xác định

Sau commit, gateway gửi thông điệp; nếu request timeout:

- Có thể broker **chưa nhận** event.
- Có thể broker **đã nhận** event, nhưng response bị mất.
- Có thể broker mới nhận vào buffer chứ chưa thỏa yêu cầu durability ứng dụng đề ra.

Không tự động gán `SENT` hoặc `FAILED` dựa vào mỗi exception mà không hiểu **hợp đồng xác nhận** của broker/provider. Khi trạng thái không chắc chắn, retry thường là lựa chọn an toàn cho at-least-once nhưng dẫn tới khả năng duplicate.

### 5.3. Exception sau commit không rollback transaction đã commit

Nếu callback `AFTER_COMMIT` ném exception, dữ liệu nghiệp vụ đã commit sẽ không tự rollback theo exception đó. Caller có thể quan sát exception ở đường commit tùy hạ tầng, nhưng **kết quả DB và kết quả gửi ngoài đã tách rời**. Không thiết kế API theo giả định “bắt exception sau commit thì có thể coi đơn hàng chưa tạo”.

### 5.4. Ghi DB sau commit cần transaction mới

Spring cảnh báo trong callback hậu commit, một số transactional resources vẫn có thể còn bound với thread. Nếu thực hiện truy cập DB mới mà không có transaction mới, thao tác có thể “tham gia” resource cũ **nhưng không còn lượt commit tiếp theo**.

Nếu cần ghi marker/notification-outbox trong callback, dùng một service riêng:

```java
@Service
public class FollowUpRecorder {
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void recordFollowUp(OrderCommitted event) {
        repository.save(...);
    }
}

@Component
public class AfterCommitHandler {
    private final FollowUpRecorder recorder;

    public AfterCommitHandler(FollowUpRecorder recorder) {
        this.recorder = recorder;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void handle(OrderCommitted event) {
        recorder.recordFollowUp(event);
    }
}
```

Đây là **mẫu tích hợp**, cần repository và các import. `REQUIRES_NEW` phải được gọi qua Spring proxy, không phải self-invocation `this.recordFollowUp(...)`. Dù transaction mới commit thành công, mẫu này **vẫn có cửa sổ mất event giữa business commit và lời gọi recorder**; nó không phải transactional outbox toàn tuyến.

## 6. TransactionSynchronization.afterCommit: lựa chọn cấp thấp

Nếu muốn điều khiển callback trực tiếp mà không dùng annotation, Spring có `TransactionSynchronizationManager.registerSynchronization(...)`:

```java
if (!TransactionSynchronizationManager.isSynchronizationActive()) {
    throw new IllegalStateException(
            "An active transaction synchronization is required");
}

TransactionSynchronizationManager.registerSynchronization(
        new TransactionSynchronization() {
            @Override
            public void afterCommit() {
                externalGateway.publish(event);
            }
        });
```

Đây là **snippet tích hợp**: cần có transaction đúng, `externalGateway`, `event` và import `TransactionSynchronizationManager`, `TransactionSynchronization`. Trong ứng dụng thực phải kiểm tra ngữ nghĩa transaction đang hoạt động phù hợp, không chỉ copy đoạn code vào method không có transaction.

Cơ chế này hữu ích khi cần hook ở mức transaction synchronization. Nhưng **nó có cùng bản chất callback trong RAM**, không khắc phục cửa sổ crash sau commit. `@TransactionalEventListener` thường dễ đọc và phù hợp hơn nếu một bean muốn nhận domain event Spring.

Đừng nhầm `TransactionSynchronization.afterCommit()` với `@Async` hoặc một message durable. Nếu có nhu cầu giao nhận bền vững ra broker, cả hai cần được bổ sung bằng transactional outbox.

## 7. Cách 2: Transactional outbox — lưu ý định gửi cùng transaction nghiệp vụ

**Transactional outbox** giải quyết dual write bằng việc không gửi broker trực tiếp trong transaction nghiệp vụ. Thay vào đó, service ghi **cả business state và outbox row trong cùng một database transaction**. Sau commit, một **relay** độc lập đọc outbox đã commit và gửi tới hệ thống ngoài, retry khi gặp lỗi.

```text
                  BUSINESS TRANSACTION (một DB)
BEGIN
   |
   +--> UPDATE orders SET status='CONFIRMED'
   |
   +--> INSERT event_outbox(
          event_id, aggregate_id, event_type, payload, status='PENDING')
   |
COMMIT  <--- order và outbox cùng commit hoặc cùng rollback
   |
   v
Durable outbox row
   |
   +--> Relay worker polling / CDC
           |
           +--> broker.publish(eventId, payload)
           |        |
           |        +--> timeout/failure -> giữ pending, retry
           |        |
           |        +--> confirmed -> đánh dấu SENT
           |
           v
      Kafka / RabbitMQ / webhook / external consumer
```

### Bảo đảm nguyên tử cốt lõi

Trong transaction nguồn:

- **Commit thành công** → cả dữ liệu đơn hàng và bản ghi outbox đều tồn tại bền vững.
- **Rollback** → không có trạng thái đơn hàng mới và cũng không có outbox row cho thay đổi đó.
- **Process crash sau commit** → outbox row vẫn còn; worker khác có thể tiếp tục gửi sau restart.

Điều kiện: business state và outbox phải thực sự nằm **trong cùng transaction của cùng nguồn lưu trữ ACID**. Nếu service ghi database A rồi ghi outbox vào database B ở một transaction khác, atomicity này không còn.

### 7.1. Transactional outbox không tự “gửi đúng một lần”

Một relay có thể:

1. Gửi event thành công tới broker.
2. Crash trước khi cập nhật `status = SENT`.
3. Khởi động lại và thấy row vẫn `PENDING`.
4. Gửi **cùng eventId** một lần nữa.

Đây là trạng thái **at-least-once relay delivery**; consumer nên dùng idempotency key/unique constraint để bỏ tác dụng phụ trùng. Không được thay eventId bằng UUID mới mỗi lần retry nếu muốn consumer nhận ra **cùng một occurrence**.

### 7.2. Polling publisher và CDC

Hai cách phổ biến để relay lấy outbox:

| Cơ chế | Nguyên tắc | Điểm cần cân nhắc |
| --- | --- | --- |
| Polling | Worker định kỳ query những row PENDING, claim và gửi | Độ trễ polling, tải DB, claim nhiều worker, retry |
| CDC / transaction-log tailing | Đọc thay đổi outbox từ log commit DB rồi chuyển ra broker | Vận hành connector, offset, ordering, schema, duplicate/repair |

Cả hai đều cần monitoring, idempotency và chính sách khôi phục. CDC không tự biến broker + database thành một transaction duy nhất theo kiểu exactly-once end-to-end cho mọi consumer.

## 8. Thiết kế schema outbox đủ dùng

Một schema mẫu trong một relational database:

```sql
CREATE TABLE orders (
    order_id       VARCHAR(80) PRIMARY KEY,
    status         VARCHAR(30) NOT NULL
);

CREATE TABLE event_outbox (
    event_id       VARCHAR(80) PRIMARY KEY,
    aggregate_id   VARCHAR(80) NOT NULL,
    aggregate_type VARCHAR(80) NOT NULL,
    event_type     VARCHAR(120) NOT NULL,
    payload_json   CLOB NOT NULL,
    status         VARCHAR(20) NOT NULL,
    attempt_count  INTEGER NOT NULL DEFAULT 0,
    created_at     TIMESTAMP NOT NULL
);
```

Đây là **schema thiết kế**, khác schema giản lược của chương trình mục 10. Trường quan trọng:

- `event_id`: định danh bất biến cho occurrence, được giữ nguyên khi retry.
- `aggregate_id` + `aggregate_type`: hỗ trợ routing, ordering và truy vết.
- `event_type` + `payload_json`: diễn tả thông điệp cần gửi ra ngoài.
- `status`: ví dụ `PENDING`, `IN_PROGRESS`, `SENT` hoặc `DEAD_LETTER` theo thiết kế.
- `attempt_count` và thời điểm retry: phục vụ backoff/observability.
- `created_at` và aggregate version: hữu ích nếu downstream cần xét thứ tự.

Trong ứng dụng multi-tenant, thêm `tenant_id` và khóa/constraint phù hợp với phạm vi định danh event. Không log payload chứa secrets/PII chỉ để debug.

### Status và claim

Với nhiều relay worker, không nên để mọi worker cùng query `WHERE status='PENDING'` rồi gửi ngay mà **không có claim coordination**. Có thể dùng lease có hạn:

```text
PENDING -> CLAIMED (owner, lease_until) -> SENT
                    |
                    +--> timeout / worker crash -> retryable PENDING
                    |
                    +--> quá số lần thử -> DEAD_LETTER
```

Một số database hỗ trợ `SELECT ... FOR UPDATE SKIP LOCKED`, hoặc claim bằng `UPDATE ... WHERE status='PENDING' ... RETURNING` theo tính năng DB. Cần transaction ngắn để claim, commit claim trước khi gọi broker, và xử lý lease hết hạn; **không giữ DB lock qua lời gọi HTTP/broker có thể chậm**.

### Ordering

`ORDER BY created_at` đơn thuần không bảo đảm tuyệt đối trình tự event trên nhiều worker, nhất là khi timestamp trùng hoặc message đầu tiên bị retry. Nếu consumer cần trình tự theo aggregate, cần `aggregate_version`/sequence, partition key theo aggregate, điều kiện xử lý phiên bản và quy tắc retry. **Idempotency và ordering là hai hợp đồng khác nhau.**

## 9. Thiết kế relay gửi ra ngoài

Một relay thực tế nên có các pha:

1. **Tìm/claim** row outbox chưa hoàn tất bằng cách chống claim trùng giữa worker.
2. **Đọc một snapshot payload bền vững** gồm `eventId`, key, type, version và data.
3. **Gửi thông điệp** tới broker/provider bằng client cấu hình đúng producer acknowledgments/confirmations.
4. **Đợi tín hiệu thành công đủ mạnh theo yêu cầu** — không chỉ “đã gọi send()”.
5. **Đánh dấu SENT sau acknowledgment**, trong transaction cập nhật riêng.
6. Nếu lỗi tạm thời, **giữ/release row retryable** với exponential backoff và jitter.
7. Nếu lỗi schema/permission vĩnh viễn, **đưa vào trạng thái terminal/DLQ** và cảnh báo.
8. Ghi metric: số PENDING, oldest age, attempts, success, duplicate, latency và error rate.

### Kafka và RabbitMQ không có cùng API xác nhận

- Với Kafka, API gửi thường async; việc có một `Future` không có nghĩa message đã được broker xác nhận. Phải xử lý completion/exception và cấu hình producer phù hợp cho yêu cầu durability.
- Với RabbitMQ, publisher confirms và returned messages/routing policy là những khía cạnh riêng. “Send không ném lỗi ngay” không nhất thiết nghĩa đã được queue mong muốn chấp nhận.
- Với webhook/HTTP, HTTP 2xx có thể có ý nghĩa “đã nhận yêu cầu” chứ không chắc job đích đã hoàn tất. Cần hợp đồng API/idempotency key và reconcile nếu response không xác định.

**Không ghi `SENT` ngay sau khi gọi một API send bất đồng bộ nếu chưa có confirmation phù hợp**. Nếu đánh dấu quá sớm và process chết, message có thể chưa được chuyển đi mà outbox đã bị đóng.

### Không bọc toàn bộ network I/O trong transaction nguồn

Cố gửi broker ngay trong transaction database làm tăng thời gian giữ lock, giảm throughput và vẫn không bảo đảm atomicity giữa DB và broker. Broker có thể ACK rồi DB rollback; hoặc DB commit nhưng trạng thái gateway không chắc chắn. Outbox chủ động tách hai hệ thống để tránh tưởng rằng một transaction SQL bao trùm cả network.

## 10. Ví dụ hoàn chỉnh Java 17 + Spring Framework 6.2 + JDBC/H2

Ví dụ dưới đây chạy **trong một process** và dùng **broker giả lập** để kiểm chứng chính xác các failure window. Mục tiêu là minh họa **quan hệ giữa commit, outbox và relay retry**, không thực sự gửi Kafka/RabbitMQ.

Kịch bản:

1. Commit đơn `ORD-100`, tạo outbox `evt-100` cùng transaction.
2. Thử tạo `ORD-ROLLBACK` nhưng rollback — **không có order/outbox** và callback `AFTER_COMMIT` không chạy.
3. Relay gửi `evt-100`: broker giả lập lỗi lần đầu, row vẫn `PENDING`.
4. Relay retry: broker xác nhận thành công, row chuyển `SENT`.
5. Commit `ORD-300` với outbox `evt-300`.
6. Giả lập “broker đã nhận `evt-300` nhưng process chết trước khi đánh dấu SENT”. Row vẫn `PENDING`.
7. Relay lại gửi `evt-300`. Broker giả lập ghi nhận **duplicate delivery**, còn receiver dùng `eventId` để không tạo thêm effect.
8. Kết quả: hai order đã commit, hai outbox row, hai event ID được consumer chấp nhận duy nhất, dù có **bốn lần gọi gateway**.

### 10.1. Cấu trúc dự án

```text
after-commit-outbox-demo/
├── pom.xml
└── src/main/java/example/AfterCommitOutboxDemo.java
```

### 10.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>after-commit-outbox-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.0</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.0</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.3.232</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>example.AfterCommitOutboxDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 10.3. src/main/java/example/AfterCommitOutboxDemo.java

```java
package example;

import java.util.LinkedHashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;
import java.util.concurrent.atomic.AtomicInteger;
import javax.sql.DataSource;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.support.TransactionTemplate;

public class AfterCommitOutboxDemo {

    public record OrderCommitted(String eventId, String orderId) {
        public OrderCommitted {
            Objects.requireNonNull(eventId, "eventId");
            Objects.requireNonNull(orderId, "orderId");
            if (eventId.isBlank() || orderId.isBlank()) {
                throw new IllegalArgumentException("ID must not be blank");
            }
        }
    }

    private record Pending(String eventId, String orderId) {}

    private static class SimulatedTransportFailure
            extends RuntimeException {
        SimulatedTransportFailure() {
            super("Simulated broker is unavailable");
        }
    }

    // Broker/receiver giả; chỉ mô phỏng ACK và idempotency.
    public static class FakeGateway {
        private final Set<String> receivedIds = new LinkedHashSet<>();
        private int attempts;
        private int failures;
        private int duplicateDeliveries;

        public void send(String eventId, String orderId) {
            attempts++;

            // Chỉ lần gửi đầu của evt-100 bị lỗi giả lập.
            if ("evt-100".equals(eventId) && failures == 0) {
                failures++;
                throw new SimulatedTransportFailure();
            }

            // Bên nhận chống trùng bằng eventId.
            if (!receivedIds.add(eventId)) {
                duplicateDeliveries++;
            }
        }

        public int attempts() {
            return attempts;
        }

        public int failures() {
            return failures;
        }

        public int duplicateDeliveries() {
            return duplicateDeliveries;
        }

        public int uniqueEvents() {
            return receivedIds.size();
        }
    }

    // Chỉ là gợi ý đánh thức relay sau commit, không trực tiếp
    // gửi broker và không đóng vai trò nguồn durability.
    public static class AfterCommitHint {
        private final AtomicInteger hints = new AtomicInteger();

        @TransactionalEventListener(
                phase = TransactionPhase.AFTER_COMMIT)
        public void onCommitted(OrderCommitted event) {
            hints.incrementAndGet();
        }

        public int count() {
            return hints.get();
        }
    }

    public static class OrderService {
        private final JdbcTemplate jdbc;
        private final TransactionTemplate businessTx;
        private final ApplicationEventPublisher publisher;

        public OrderService(
                JdbcTemplate jdbc,
                TransactionTemplate businessTx,
                ApplicationEventPublisher publisher) {
            this.jdbc = jdbc;
            this.businessTx = businessTx;
            this.publisher = publisher;
        }

        public void commitOrder(
                String orderId, String eventId, boolean rollback) {
            businessTx.executeWithoutResult(status -> {
                jdbc.update(
                        "INSERT INTO orders(order_id, status) "
                        + "VALUES (?, 'CONFIRMED')",
                        orderId);

                // Outbox được ghi CÙNG transaction với order.
                jdbc.update(
                        "INSERT INTO event_outbox "
                        + "(event_id, order_id, event_type, status) "
                        + "VALUES (?, ?, 'OrderCommitted', 'PENDING')",
                        eventId, orderId);

                // Local event: callback sau commit chỉ tạo hint.
                publisher.publishEvent(
                        new OrderCommitted(eventId, orderId));

                if (rollback) {
                    status.setRollbackOnly();
                }
            });
        }
    }

    // Relay một worker duy nhất: code minh họa ngữ nghĩa,
    // production cần claim/lease nếu có nhiều worker.
    public static class OutboxRelay {
        private final JdbcTemplate jdbc;
        private final FakeGateway gateway;

        public OutboxRelay(JdbcTemplate jdbc, FakeGateway gateway) {
            this.jdbc = jdbc;
            this.gateway = gateway;
        }

        private List<Pending> pendingRows() {
            return jdbc.query(
                    "SELECT event_id, order_id "
                    + "FROM event_outbox "
                    + "WHERE status = 'PENDING' ORDER BY event_id",
                    (rs, row) -> new Pending(
                            rs.getString("event_id"),
                            rs.getString("order_id")));
        }

        public void drainOnce() {
            for (Pending item : pendingRows()) {
                try {
                    // Gửi ngoài DB transaction. Chỉ coi thành công
                    // khi gateway trả về như ACK của demo.
                    gateway.send(item.eventId(), item.orderId());
                } catch (SimulatedTransportFailure expected) {
                    // Lỗi tạm thời: row vẫn PENDING để retry.
                    continue;
                }

                // Chỉ ghi SENT SAU khi gateway báo thành công.
                jdbc.update(
                        "UPDATE event_outbox SET status = 'SENT' "
                        + "WHERE event_id = ? AND status = 'PENDING'",
                        item.eventId());
            }
        }

        public void simulateAckBeforeMark(String eventId) {
            Pending item = pendingRows().stream()
                    .filter(p -> p.eventId().equals(eventId))
                    .findFirst()
                    .orElseThrow();

            // Gửi thành công rồi giả lập crash ngay tại đây:
            // cố ý KHÔNG cập nhật status.
            gateway.send(item.eventId(), item.orderId());
        }

        public int pendingCount() {
            return jdbc.queryForObject(
                    "SELECT COUNT(*) FROM event_outbox "
                    + "WHERE status = 'PENDING'",
                    Integer.class);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        public DataSource dataSource() {
            DriverManagerDataSource ds =
                    new DriverManagerDataSource();
            ds.setDriverClassName("org.h2.Driver");
            ds.setUrl("jdbc:h2:mem:outbox_demo;DB_CLOSE_DELAY=-1");
            ds.setUsername("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        public JdbcTemplate jdbcTemplate(DataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }

        @Bean
        public PlatformTransactionManager transactionManager(
                DataSource dataSource) {
            return new DataSourceTransactionManager(dataSource);
        }

        @Bean
        public TransactionTemplate businessTx(
                PlatformTransactionManager transactionManager) {
            return new TransactionTemplate(transactionManager);
        }

        @Bean
        public FakeGateway fakeGateway() {
            return new FakeGateway();
        }

        @Bean
        public AfterCommitHint afterCommitHint() {
            return new AfterCommitHint();
        }

        @Bean
        public OrderService orderService(
                JdbcTemplate jdbc,
                TransactionTemplate businessTx,
                ApplicationEventPublisher publisher) {
            return new OrderService(jdbc, businessTx, publisher);
        }

        @Bean
        public OutboxRelay outboxRelay(
                JdbcTemplate jdbc,
                FakeGateway gateway) {
            return new OutboxRelay(jdbc, gateway);
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {
            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            OrderService service = context.getBean(OrderService.class);
            OutboxRelay relay = context.getBean(OutboxRelay.class);
            FakeGateway gateway = context.getBean(FakeGateway.class);
            AfterCommitHint hint = context.getBean(AfterCommitHint.class);

            jdbc.execute(
                    "CREATE TABLE orders ("
                    + "order_id VARCHAR(80) PRIMARY KEY,"
                    + "status VARCHAR(30) NOT NULL)");

            jdbc.execute(
                    "CREATE TABLE event_outbox ("
                    + "event_id VARCHAR(80) PRIMARY KEY,"
                    + "order_id VARCHAR(80) NOT NULL,"
                    + "event_type VARCHAR(100) NOT NULL,"
                    + "status VARCHAR(20) NOT NULL)");

            // T1 commit, T2 rollback.
            service.commitOrder("ORD-100", "evt-100", false);
            service.commitOrder(
                    "ORD-ROLLBACK", "evt-rollback", true);

            // Lần đầu broker giả lỗi; retry sau đó thành công.
            relay.drainOnce();
            int pendingAfterFailure = relay.pendingCount();
            relay.drainOnce();
            int pendingAfterRetry = relay.pendingCount();

            // Event thứ hai commit và có row outbox bền vững.
            service.commitOrder("ORD-300", "evt-300", false);

            // Giả lập: gateway nhận nhưng chưa mark SENT.
            relay.simulateAckBeforeMark("evt-300");
            int pendingAfterAckBeforeMark = relay.pendingCount();

            // Worker retry có thể gửi trùng; receiver dedupe.
            relay.drainOnce();

            System.out.println("After first drain pending="
                    + pendingAfterFailure);
            System.out.println("After retry pending="
                    + pendingAfterRetry);
            System.out.println("After ack-before-mark pending="
                    + pendingAfterAckBeforeMark);
            System.out.println("Committed orders="
                    + jdbc.queryForObject(
                            "SELECT COUNT(*) FROM orders",
                            Integer.class));
            System.out.println("Outbox rows="
                    + jdbc.queryForObject(
                            "SELECT COUNT(*) FROM event_outbox",
                            Integer.class));
            System.out.println("After-commit hints=" + hint.count());
            System.out.println("Gateway attempts=" + gateway.attempts());
            System.out.println("Transient failures=" + gateway.failures());
            System.out.println("Duplicate deliveries="
                    + gateway.duplicateDeliveries());
            System.out.println("Receiver unique events="
                    + gateway.uniqueEvents());
            System.out.println("Final pending=" + relay.pendingCount());
            System.out.println("Rolled-back rows="
                    + jdbc.queryForObject(
                            "SELECT COUNT(*) FROM orders "
                            + "WHERE order_id = 'ORD-ROLLBACK'",
                            Integer.class));
        }
    }
}
```

### 10.4. Lệnh chạy

Dùng JDK 17+ và Maven, từ thư mục chứa `pom.xml`:

```bash
mvn -q compile exec:java
```

**Mười hai dòng kết quả do chương trình in** trong thiết kế demo này, không tính log Maven/Spring nếu có:

```text
After first drain pending=1
After retry pending=0
After ack-before-mark pending=1
Committed orders=2
Outbox rows=2
After-commit hints=2
Gateway attempts=4
Transient failures=1
Duplicate deliveries=1
Receiver unique events=2
Final pending=0
Rolled-back rows=0
```

### 10.5. Vì sao từng con số đúng?

- `ORD-100` được ghi và commit cùng outbox `evt-100`, nên có một row PENDING.
- Transaction của `ORD-ROLLBACK` gọi `status.setRollbackOnly()`, làm cả order/outbox rollback. Listener `AFTER_COMMIT` cho event này không chạy.
- `relay.drainOnce()` đầu tiên gọi gateway cho `evt-100`. FakeGateway cố ý ném `SimulatedTransportFailure` trong lần gửi đầu tiên; relay bắt đúng loại lỗi tạm thời và giữ PENDING.
- Lần `drainOnce()` kế tiếp gửi `evt-100` thành công; gateway thêm ID vào tập đã nhận, rồi relay cập nhật outbox thành SENT.
- `ORD-300` được commit với outbox `evt-300` và thêm một callback hint.
- `simulateAckBeforeMark("evt-300")` gọi gateway thành công nhưng **không cập nhật DB**, mô phỏng process chết ngay giữa ACK và mark SENT. Outbox vẫn PENDING.
- Worker thử lại `evt-300`. Gateway nhận thêm một lần gọi nhưng receiver giả lập có set `eventId` nên phát hiện duplicate, không thêm effect mới.
- Tổng `gateway.attempts() = 4`: một lần lỗi của evt-100, một lần thành công evt-100, một lần thành công evt-300 trước mark, một lần retry evt-300.
- `failures = 1`, `duplicateDeliveries = 1` và `receivedIds.size() = 2`.
- Có hai business commit, nên `AfterCommitHint` nhận hai callback. Không có callback cho transaction rollback.
- Cuối cùng cả hai outbox row đều SENT; không còn PENDING. Trong bảng orders chỉ có ORD-100 và ORD-300.

### 10.6. Những giới hạn chủ đích của ví dụ

- `FakeGateway` là mô phỏng broker/receiver, **không có kết nối mạng hoặc delivery guarantee thật**. Nó coi method `send(...)` trả về thành công là ACK của bản demo.
- `LinkedHashSet` chỉ lưu các ID đã nhận trong một JVM. **Production cần dedupe bền vững ở consumer** nếu side effect không được lặp.
- H2 dùng database in-memory; khi JVM kết thúc, dữ liệu không được giữ bền vững qua restart. Với hệ thống thật, dùng database persistent và cơ chế backup/replication phù hợp.
- `OutboxRelay` chỉ có **một worker tuần tự**, chưa thực hiện claim/lease, backoff, DLQ hoặc producer confirmation của broker thật.
- Ví dụ chỉ mô phỏng crash window, **không kill process thật**.
- Mã dùng `TransactionTemplate` để kiểm soát commit/rollback mà không cần cấu hình `@Transactional` proxy. Với ứng dụng dùng `@Transactional`, vẫn cần transaction manager đúng và tránh self-invocation.
- Callback `AfterCommitHint` chỉ tăng counter, **không gửi broker**, do đó không tạo ra cửa sổ dual write mới. Production có thể dùng hint để đánh thức relay nhưng phải có polling/recovery độc lập khi hint bị mất.
- Các ID cố định dùng để kết quả dễ kiểm chứng; production phải cấp phát eventId duy nhất cho event occurrence mới, giữ nguyên khi retry.
- Hệ thống thật phải xác định acknowledgment của external gateway và chính sách retry/idempotency theo hợp đồng cụ thể.

**Điểm quan trọng nhất:** sự kiện bên ngoài được gửi bởi **relay đọc outbox đã commit**, không phải bởi callback `AFTER_COMMIT`. Callback chỉ tối ưu độ trễ, còn **outbox row mới là nguồn công việc bền vững**.

## 11. Khi nào dùng callback trực tiếp, khi nào dùng outbox?

| Tiêu chí | `@TransactionalEventListener(AFTER_COMMIT)` gọi gateway trực tiếp | Transactional outbox + relay |
| --- | --- | --- |
| Không gửi trên rollback | Có, nếu transaction/callback được cấu hình đúng | Có, vì outbox cũng rollback |
| Đơn giản triển khai | Đơn giản hơn | Nhiều thành phần hơn |
| Crash sau commit trước gửi | Có thể mất event | Outbox đã commit vẫn còn |
| Broker down lâu | Callback có thể thất bại và không có retry bền vững | Relay retry từ outbox |
| Gửi message có thể trùng | Có thể nếu tự retry/nguồn phát lặp | Có; relay có thể lặp sau ACK-before-mark |
| Bảo đảm delivery dài hạn | Không, nếu không thêm persistence/recovery | Có điều kiện khi relay vận hành và hạ tầng phục hồi |
| Phù hợp với notification quan trọng | Chỉ nếu chấp nhận best-effort | Thường phù hợp hơn |
| Cần idempotent consumer | Có, khi retry/duplicate có thể xảy ra | Có, bắt buộc cho effect không được trùng |
| Độ trễ | Có thể ngắn nếu callback chạy ngay | Polling/CDC/hint ảnh hưởng độ trễ |
| Vận hành | Theo dõi callback và gateway | Cần monitor backlog, claim, retry, DLQ |

**Lựa chọn thực tế:** nếu chỉ cần cập nhật metric phụ trợ và chấp nhận event đôi lúc bị mất, callback hậu commit có thể đủ. Nếu phải thông báo cho billing, fulfillment, audit quan trọng hoặc hệ thống ngoài sau mỗi business commit, **ưu tiên transactional outbox** và xác minh độ tin cậy từng chặng.

## 12. Nếu vẫn cần phát event local để đánh thức worker

Một mô hình kết hợp tốt:

```text
OrderService transaction
    +--> save order
    +--> insert event_outbox
    +--> publishEvent(OutboxReadyHint)
             |
             v
        AFTER_COMMIT
             |
             +--> signal relay (best effort)
             |
             +--> poller/CDC vẫn là đường phục hồi
```

Tín hiệu hậu commit chỉ giúp worker không phải đợi kỳ polling tiếp theo. Nếu signal bị mất do crash, poller vẫn tìm được row bền vững. Với một ứng dụng có nhiều instance, relay phải có **cơ chế phối hợp claim/lease**; signal từ một instance không đảm bảo instance đó là worker được chọn.

Không được dùng hint là **đường duy nhất** xử lý outbox. Nếu hint không có listener hoặc listener chết, PENDING sẽ tồn đọng mãi. Cần một vòng quét định kỳ hoặc CDC có checkpoint/recovery.

### Không tạo event gốc mới chỉ để retry

Khi phát lại cùng outbox row, dùng **eventId đã ghi**. Nếu mỗi lần relay retry lại sinh UUID mới, consumer mất khả năng dedupe cùng event occurrence. Nếu nghiệp vụ tạo một command mới hợp lệ, có thể cần ID mới; phải phân biệt command mới với replay.

## 13. Cách xử lý transaction ở mỗi chặng

Bài toán này có **ba transaction** khác nhau, không nên đánh đồng:

1. **Business transaction:** cập nhật order và ghi event outbox cùng commit.
2. **Relay claim/mark transaction:** nhận quyền xử lý row và đánh dấu sau broker acknowledgment.
3. **Consumer transaction:** ghi marker idempotency và effect nội bộ tại hệ thống nhận.

```text
T1: UPDATE order + INSERT event_outbox  -> COMMIT
T2: CLAIM outbox row                    -> COMMIT
NETWORK: publish event + broker ACK
T3: MARK outbox SENT                    -> COMMIT
CONSUMER: INSERT processed + business effect -> COMMIT
```

Không thể lấy một `@Transactional` trên toàn phương thức network send rồi mặc nhiên làm cho broker join vào transaction SQL. Khi các hệ thống không tham gia cùng giao thức transaction phân tán, không có atomic commit giữa chúng.

### Khi mark SENT thất bại

Broker đã ACK nhưng T3 lỗi hoặc process crash → outbox có thể còn PENDING/CLAIMED. Khi lease hết hạn, worker thử lại và **có thể gửi trùng**. Đây là lý do consumer phải idempotent.

### Khi broker timeout

Không biết broker đã xử lý hay chưa. Không nên đánh dấu SENT. Cho row quay lại trạng thái retryable, với cùng eventId/idempotency key; không xóa row vì timeout.

### Khi consumer lỗi

Broker có thể đã lưu message và xác nhận producer thành công, nhưng consumer chưa xử lý. Outbox của producer có thể đã SENT theo hợp đồng broker; cần **consumer retry/DLQ và idempotency** tại hệ thống nhận. “Producer sent” không đồng nghĩa “business effect của consumer đã commit”.

## 14. Idempotency ở consumer

Một bảng marker mẫu:

```sql
CREATE TABLE processed_messages (
    consumer_name VARCHAR(80) NOT NULL,
    event_id      VARCHAR(80) NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
```

Consumer xử lý trong một transaction:

```text
BEGIN CONSUMER TRANSACTION
    INSERT processed_messages(consumer, eventId)
        -- unique conflict: duplicate -> rollback/skip
    UPDATE read_model / INSERT invoice
COMMIT
```

Khi marker và hiệu ứng database cùng transaction, lỗi effect rollback marker; lần retry sau được phép làm lại. Unique constraint bảo vệ khi **hai worker cạnh tranh**; không dùng `SELECT exists` rồi `INSERT` tách rời mà không có unique key.

### Khóa idempotency phải theo đúng nghiệp vụ

- `(consumer, eventId)` chống xử lý trùng cùng occurrence cho một consumer.
- Một business key như `(tenantId, paymentId, invoiceType)` có thể cần thêm unique constraint nếu **hai eventId khác nhau** vẫn không được tạo hai invoice.
- `correlationId` chỉ gom workflow, thường không phải dedupe key.
- `aggregateId` có thể có nhiều event hợp lệ (Created, Paid, Shipped); không dùng đơn độc làm khóa chặn mọi event.

Nếu tác dụng phụ là HTTP/email, DB marker chưa đủ cho exactly-once: gửi ngoài có thể thành công rồi timeout trước khi marker commit. Cần API đích có idempotency key, outbox ở consumer, hoặc reconciliation và chấp nhận hợp đồng at-least-once phù hợp.

## 15. Testing: kiểm tra commit, rollback và các cửa sổ lỗi

### 15.1. Ma trận tối thiểu

| Kịch bản | Điều cần khẳng định |
| --- | --- |
| Commit order thành công | Có order và outbox row cùng eventId |
| Transaction rollback | Không có order mới, không có outbox row, không có callback AFTER_COMMIT |
| Publish local event ngoài transaction | Listener transaction-bound không chạy khi `fallbackExecution=false` |
| Crash sau business commit | Outbox vẫn bền vững sau restart trên DB persistent |
| Broker down | Row giữ pending/retryable, không mark SENT giả |
| Broker ACK thành công | Mark SENT chỉ sau xác nhận đủ theo hợp đồng |
| Crash sau ACK trước mark | Retry có thể gửi lại cùng eventId |
| Hai relay worker cùng claim | Không mất nhiệm vụ; có coordination, có thể duplicate được consumer xử lý |
| Consumer nhận cùng eventId hai lần | Business effect chỉ được ghi một lần |
| Poison message | Có trạng thái terminal/DLQ và cảnh báo |
| Event đi lệch thứ tự | Consumer có kiểm tra version/sequence nếu cần |
| Queue backlog tăng | Monitoring nhận ra, không âm thầm mất sự kiện |

Chương trình mục 10 mô phỏng một phần ma trận: commit, rollback, gateway lỗi một lần, retry, ACK-before-mark và receiver dedupe. Nó **không thay thế integration test với broker và persistent DB thật**.

### 15.2. Test AFTER_COMMIT với Spring transaction

Nếu test dùng `@Transactional` ở cấp phương thức kiểm thử, Spring TestContext thường rollback transaction test sau mỗi test. Một listener `AFTER_COMMIT` khi đó **không được gọi**, dù code đã publish local event.

Để test callback sau commit, dùng transaction được commit thật qua `TransactionTemplate` hoặc điều khiển test-managed transaction bằng `TestTransaction.flagForCommit()` và `TestTransaction.end()`. Test rollback phải xác minh không có effect.

### 15.3. Không dùng sleep để test retry

Với relay async, dùng latch/future có timeout, fake gateway đếm attempts và query trạng thái outbox. Tránh `Thread.sleep(50)` rồi assert; máy CI chậm hoặc queue đầy có thể khiến test flaky.

### 15.4. Khi cần bảo đảm qua restart

Test thực tế:

1. Khởi động ứng dụng với **database persistent**.
2. Trong transaction, ghi order + outbox và commit.
3. Dừng process **trước khi relay gửi**.
4. Khởi động phiên mới và xác minh relay tìm lại row PENDING.
5. Làm broker timeout rồi phục hồi; bảo đảm eventual send.
6. Dừng process sau ACK trước mark; xác nhận không mất event và consumer chống trùng.
7. Xác minh số lượng effect nghiệp vụ cuối cùng đúng yêu cầu.

Đó mới là bằng chứng về resilience qua crash; không nên suy ra từ một demo H2 in-memory.

## 16. Monitoring và runbook vận hành

Các metric nên có:

- `outbox_pending_count` theo event type và tenant/partition khi phù hợp.
- `outbox_oldest_pending_age_seconds`: tuổi của row chưa gửi lâu nhất.
- `outbox_publish_attempts_total`, `outbox_publish_success_total`, `outbox_publish_failure_total`.
- `outbox_claim_expired_total`: số lease hết hạn cần reclaim.
- `broker_publish_ack_latency` và tỷ lệ timeout.
- `consumer_duplicates_skipped_total`.
- `dead_letter_count`, `schema_validation_failure_total`.
- `relay_instance_heartbeat` hoặc tình trạng connector CDC.
- Thời gian `business_commit -> broker_ack` (end-to-end publication lag).

Log nên có `eventId`, `aggregateId`, `eventType`, `correlationId`, `attempt`, `relayWorkerId`, `status` và tên broker/topic được phép log. Không log toàn bộ payload chứa secrets hoặc PII.

### Runbook ngắn khi hệ thống ngoài không thấy event

1. Kiểm tra business transaction có thực sự commit không.
2. Tìm outbox row theo eventId; nếu không có, điều tra code transaction hoặc workflow nguồn.
3. Nếu có row PENDING, xem lease, next_retry_at và relay heartbeat.
4. Nếu row SENT, kiểm tra producer confirmation và message ID ở broker.
5. Nếu broker có message, kiểm tra consumer offset/ACK/DLQ/idempotency.
6. Nếu có duplicate, xem khoảng ACK-before-mark và chính sách retry.
7. Không “replay toàn bộ event” mù quáng khi consumer có tác dụng phụ không idempotent.
8. Khi backfill, giữ nguyên eventId/tenant/schema version và ghi dấu thao tác vận hành.

## 17. Sai lầm thường gặp

1. **Gửi broker trong `@Transactional` rồi nghĩ broker cùng rollback với DB.** Hai hệ thống không tự có một commit.
2. **Gọi `@EventListener` thường và gửi trước khi transaction commit.** Có thể tạo ghost event.
3. **Dùng `@TransactionalEventListener(AFTER_COMMIT)` và tuyên bố “không mất event”.** Callback trong RAM vẫn có cửa sổ crash.
4. **Bật `fallbackExecution=true` vì listener không chạy.** Có thể chạy không gắn với commit nguồn.
5. **Ghi DB trong callback hậu commit mà không mở transaction mới.** Resource cũ có thể không có commit tiếp.
6. **Cho rằng exception ở listener hậu commit rollback business state.** Business transaction đã commit.
7. **Ghi outbox sau commit trong transaction khác rồi coi như atomic với business.** Có cửa sổ mất việc giữa hai transaction.
8. **Gọi trực tiếp broker từ relay nhưng đánh dấu SENT ngay khi gọi method async.** Chưa có ACK phù hợp.
9. **Cho rằng producer ACK nghĩa consumer đã xử lý thành công.** Hai bước độc lập.
10. **Retry tạo eventId mới.** Consumer không nhận ra cùng occurrence.
11. **Đánh dấu SENT trước khi broker xác nhận.** Có thể mất event.
12. **Giữ DB row lock trong suốt network send.** Dễ tăng contention và thời gian giữ transaction.
13. **Không có claim/lease khi nhiều relay worker.** Hai worker có thể cùng gửi một row; yêu cầu idempotency càng quan trọng.
14. **Bắt mọi lỗi SQL và xem là duplicate.** Có thể che connection outage/constraint khác.
15. **Chỉ dùng bảng `processed_messages` mà không có business unique key.** Hai eventId khác nhau vẫn có thể tạo effect trùng theo nghiệp vụ.
16. **Không kiểm soát ordering.** Hai event khác version cho một aggregate có thể đến đảo thứ tự.
17. **Gửi raw JPA entity trong payload.** Có thể gặp lazy loading, mutable state và schema coupling.
18. **Chỉ ghi thông tin trạng thái trong log.** Không đủ để recovery sau crash.
19. **Dùng H2 in-memory test rồi tuyên bố đã chứng minh durability qua restart.** In-memory DB mất dữ liệu khi process kết thúc.
20. **Không có DLQ/alert.** Poison message có thể chặn hàng đợi hoặc retry vô hạn.
21. **Bỏ qua partition/tenant key.** Một message có thể gửi nhầm tenant hoặc phá thứ tự aggregate.
22. **Dựa vào một wake-up hint mà không có polling/recovery.** Signal có thể bị mất.
23. **Quên rằng broker cũng có retention/replication failure modes riêng.** Outbox bảo vệ nguồn, không xóa mọi giới hạn ở đích.
24. **Xem idempotency là chống mất event.** Nó chống effect trùng, không tạo lại event chưa từng được lưu.

## 18. Checklist triển khai production

- [ ] Đã định nghĩa yêu cầu: không ghost event, không lost event, mức retry/latency và durability.
- [ ] Mỗi event có `eventId` ổn định, `eventType`, aggregate key và version/correlation metadata phù hợp.
- [ ] Business state và **event outbox cùng một transaction ACID**.
- [ ] Rollback business transaction đồng thời rollback outbox.
- [ ] Relay lấy row từ **committed outbox**, không dựa vào callback RAM duy nhất.
- [ ] Có claim/lease khi nhiều worker, retry với backoff/jitter và DLQ.
- [ ] Có producer confirmation đúng theo broker/provider thực tế.
- [ ] Chỉ mark SENT sau khi được xác nhận phù hợp; timeout giữ trạng thái retryable.
- [ ] Retry/replay giữ nguyên eventId và scope tenant.
- [ ] Consumer dùng idempotency marker cùng business unique constraint khi cần.
- [ ] Có kiểm soát ordering/version khi domain yêu cầu.
- [ ] Local `@TransactionalEventListener(AFTER_COMMIT)` nếu dùng chỉ là hint hoặc best-effort.
- [ ] Truy cập DB mới từ callback hậu commit có transaction mới khi cần.
- [ ] Không nhầm local Spring event với broker publication.
- [ ] Test commit/rollback, gateway lỗi, ACK-before-mark, worker crash và restart.
- [ ] Test cạnh tranh nhiều worker, dedupe consumer và lỗi network không xác định.
- [ ] Có metric backlog, oldest pending, retry, failed, DLQ và publication lag.
- [ ] Có runbook reprocess/backfill an toàn, không phát trùng effect nhạy cảm.
- [ ] Payload được version hóa, giảm thiểu dữ liệu nhạy cảm và kiểm soát quyền broker.

**Ghi nhớ:** `@TransactionalEventListener(AFTER_COMMIT)` giúp bảo đảm **thời điểm** chạy callback trong một process khi transaction đã commit, nhưng không tự bảo đảm delivery bền vững. Để **đảm bảo publish ra ngoài sau commit** ngay cả khi process hoặc broker tạm thời gặp lỗi, hãy **lưu outbox trong transaction nghiệp vụ**, dùng **relay có recovery và retry** để gửi chỉ những event đã commit, và chuẩn bị cho duplicate bằng **consumer idempotency**.

## Tài liệu tham khảo

- [Spring Framework 6.2 — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
- [Spring Framework 6.2 — TransactionSynchronization API](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html)
- [Spring Framework 6.2 — ApplicationEventPublisher API](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/context/ApplicationEventPublisher.html)
- [Spring Framework 6.2 — TransactionTemplate API](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/transaction/support/TransactionTemplate.html)
- [Transactional Outbox Pattern — microservices.io](https://microservices.io/patterns/data/transactional-outbox.html)
- [AWS Prescriptive Guidance — Transactional outbox pattern](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html)
