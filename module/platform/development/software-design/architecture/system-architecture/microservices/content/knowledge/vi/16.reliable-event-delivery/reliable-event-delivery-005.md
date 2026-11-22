# Inbox hoặc sổ ghi nhận thông điệp ở phía tiếp nhận

## 1. Vì sao phía nhận cần Inbox?

Trong hệ thống microservices trao đổi sự kiện bất đồng bộ, producer có thể gửi một event qua Kafka, RabbitMQ, một hàng đợi cloud hoặc một hệ thống message broker khác. Consumer nhận event, cập nhật database của mình, rồi xác nhận với broker rằng đã xử lý.

Vấn đề là **xử lý database và ACK message thường không nằm trong cùng một local transaction**.

Ví dụ:

~~~text
Order Service
    |
    | OrderPaid(eventId=evt-001, orderId=ord-123)
    v
Message Broker
    |
    v
Fulfillment Consumer
    |
    +--> INSERT shipment vào Fulfillment DB
    |
    +--> ACK message / commit offset
~~~

Giả sử INSERT shipment thành công nhưng consumer crash ngay trước ACK. Broker có thể giao lại **chính event đó**. Nếu handler không biết mình đã xử lý trước đây, nó tạo thêm một shipment và làm hỏng quy tắc “mỗi đơn chỉ có một lệnh giao hàng tương ứng”.

**Inbox pattern** hoặc **sổ ghi nhận thông điệp đã tiếp nhận** là cách lưu vết bền vững để phía nhận biết message/operation nào đã được xử lý và ngăn tạo lại cùng một hiệu ứng nghiệp vụ khi bị giao trùng, retry hoặc replay.

Trong bài này, từ **Inbox** được dùng cho hai biến thể liên quan nhưng khác nhau:

1. **Transactional deduplication ledger:** bảng ghi nhận event đã được áp dụng; ghi marker và dữ liệu nghiệp vụ trong **cùng transaction**.
2. **Durable receiver inbox:** lưu raw/envelope của event vào bảng bền vững, ACK broker sau khi lưu; một worker sau đó xử lý message qua trạng thái và retry riêng.

Cả hai đều hữu ích. Nhưng chúng giải quyết các ranh giới transaction khác nhau; phải chọn theo nhu cầu phục hồi, throughput và hiệu ứng phụ.

### Mục tiêu học tập

- Giải thích tại sao at-least-once delivery có thể tạo xử lý trùng.
- Phân biệt Inbox với Outbox, consumer offset, ACK, DLQ và business idempotency.
- Thiết kế bảng Inbox/ledger với khóa chống trùng, transaction và trạng thái.
- Hiểu thứ tự **database COMMIT → broker ACK** và các cửa sổ lỗi.
- Kiểm soát cạnh tranh khi nhiều worker cùng thấy một event.
- Xử lý lỗi tạm thời, poison message, replay và retention của dedup ledger.
- Biết giới hạn của Inbox khi handler gửi email, gọi payment hoặc phát event.
- Viết ví dụ PostgreSQL và Java/Spring, cùng kịch bản kiểm thử crash/retry.

**Thông điệp chính:** một message được giao đúng một lần không phải điều kiện cần để một hiệu ứng nghiệp vụ diễn ra đúng một lần. Ta thiết kế **xử lý lặp an toàn** vì thông điệp có thể được nhận lại.

## 2. Các thuật ngữ phải phân biệt

| Thuật ngữ | Vai trò | Có tự chống xử lý trùng không? |
|---|---|---|
| **Message/event ID** | Định danh một sự kiện cụ thể do producer công bố | Không, chỉ là khóa đầu vào để dedup |
| **Business operation ID** | Định danh một thao tác nghiệp vụ logic, ví dụ một lần charge | Không, phải được lưu/kiểm tra ở nơi có hiệu ứng |
| **Inbox/processed-message ledger** | Lưu bằng chứng phía consumer đã tiếp nhận/áp dụng event | Có thể, nếu atomic với hiệu ứng và scope đúng |
| **Broker ACK / offset commit** | Thông báo tiến độ tiêu thụ cho broker | Không, ACK có thể bị mất sau DB commit |
| **Outbox** | Lưu ý định phát sự kiện/command cùng transaction của producer | Không tự chống trùng ở consumer |
| **Idempotent handler** | Chạy lại với cùng thao tác logic vẫn tạo kết quả nghiệp vụ đúng | Có, nếu thật sự bảo vệ mọi hiệu ứng |
| **Dead-letter queue (DLQ)** | Cách ly thông điệp không xử lý được theo policy | Không phải ledger đầy đủ các event đã xử lý |
| **Replay** | Đọc lại dữ liệu lịch sử còn được giữ | Có thể gây trùng nếu ledger/logic không phù hợp |
| **Checkpoint/offset** | Vị trí đọc/tiến độ theo partition hoặc queue | Không chứng minh business transaction đã commit |

Không nên mô tả Inbox là “bảo đảm exactly-once delivery”. Inbox xử lý **duplicate business effect** trong phạm vi đã thiết kế, trong khi broker vẫn có thể giao nhiều bản sao.

## 3. At-least-once delivery tạo duplicate thế nào?

### 3.1. Failure window kinh điển

~~~text
T0  Broker giao message M cho consumer
T1  Consumer bắt đầu DB transaction
T2  Consumer cập nhật domain state
T3  Consumer COMMIT DB thành công
T4  Consumer crash / mất mạng trước ACK
T5  Broker không thấy ACK hợp lệ
T6  Broker giao lại message M
T7  Consumer chạy lại handler nếu không có dedup
~~~

Broker làm đúng nhiệm vụ **không làm mất message** khi không nhận được xác nhận. Nhưng từ góc nhìn nghiệp vụ, lần giao lại không nên tạo lệnh giao hàng, khoản thu hoặc email không mong muốn.

Một cửa sổ lỗi khác:

~~~text
Consumer cập nhật DB
    |
ACK broker quá sớm
    |
DB transaction lỗi/rollback
    |
Message không còn được giao lại
~~~

Nếu ACK **trước** khi DB commit mà không có bản Inbox bền vững, message có thể bị mất hiệu ứng.

Hai sự cố này giải thích vì sao việc xác định **điểm bền vững** và **thứ tự ACK** quan trọng hơn việc chỉ cấu hình số lần retry.

### 3.2. Inbox không thay thế thiết kế business invariant

Nếu event **PaymentCaptured** được công bố hai lần với **hai eventId khác nhau** cho cùng một payment operation, ledger khóa theo eventId không phát hiện đây là cùng một giao dịch. Cần thêm **operationId, paymentId, unique business constraint** hoặc trạng thái nghiệp vụ phù hợp.

Mức bảo vệ có thể gồm hai tầng:

~~~text
Dedup theo event identity:
   "Event evt-001 đã xử lý chưa?"

Bất biến theo business identity:
   "Shipment cho order ord-123 đã tồn tại chưa?"
~~~

Không dùng một event ID do broker ngẫu nhiên cấp lại ở mỗi lần publish làm khóa duy nhất khi cần nhận diện cùng event gốc. Hợp đồng producer phải xác định identity có ổn định qua retry/replay hay không.

## 4. Biến thể A: processed-message ledger trong cùng transaction

Đây là phương án đơn giản khi **toàn bộ hiệu ứng cần bảo vệ nằm trong một database local**.

~~~text
Broker giao event M
       |
       v
BEGIN DB transaction
       |
       +-- INSERT consumer_inbox(consumer, eventId)
       |      nếu đã tồn tại -> bỏ qua
       |
       +-- áp dụng thay đổi nghiệp vụ
       |
       +-- ghi outbox event nếu cần
       |
COMMIT DB transaction
       |
       v
ACK broker / commit offset
~~~

Điểm quyết định:

- Ledger marker và business change **commit hoặc rollback cùng nhau**.
- Nếu crash **trước COMMIT**, cả marker và domain write rollback; broker redeliver và message được xử lý lại.
- Nếu crash **sau COMMIT nhưng trước ACK**, broker redeliver; unique constraint cho biết event đã được áp dụng và không tạo thêm business change.
- Nếu ACK thất bại, consumer có thể nhận lại nhưng **không mất tính đúng đắn** khi dedup đúng.
- Nếu message đã được commit business nhưng downstream external API chưa thực hiện, cần Outbox/worker riêng; không hứa một local transaction bảo vệ cả external side effect.

### 4.1. Vì sao marker phải nằm trong cùng transaction?

**Sai:**

~~~text
TX1: INSERT inbox("evt-1") -> COMMIT
Crash
TX2: UPDATE business_state  -> chưa xảy ra
Redelivery thấy evt-1 đã có -> bỏ qua
=> MẤT HIỆU ỨNG NGHIỆP VỤ
~~~

**Đúng khi hiệu ứng cùng database:**

~~~text
BEGIN
  INSERT inbox("evt-1")
  UPDATE business_state
COMMIT

Nếu crash trước COMMIT:
  cả hai rollback

Nếu COMMIT:
  cả hai cùng bền vững
~~~

Với worker chạy trên nhiều thread/instance, dùng **unique constraint của database** để phân xử cạnh tranh thay vì mẫu SELECT rồi INSERT không có khóa.

## 5. Thiết kế schema cho Inbox ledger

Ví dụ PostgreSQL:

~~~sql
CREATE TABLE consumer_inbox (
    consumer_name      TEXT NOT NULL,
    event_id           TEXT NOT NULL,
    event_type         TEXT NOT NULL,
    payload_fingerprint TEXT NOT NULL,
    source_producer    TEXT,
    aggregate_id       TEXT,
    aggregate_version  BIGINT,
    processed_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (consumer_name, event_id)
);

CREATE INDEX idx_consumer_inbox_processed_at
    ON consumer_inbox (processed_at);
~~~

### 5.1. Ý nghĩa các trường

| Trường | Mục đích |
|---|---|
| **consumer_name** | Phạm vi dedup thuộc một consumer logic |
| **event_id** | Identity ổn định của event nguồn |
| **event_type** | Giúp kiểm tra routing/version sự kiện |
| **payload_fingerprint** | Phát hiện cùng ID nhưng payload khác trong phạm vi hợp đồng |
| **source_producer** | Biết producer chịu trách nhiệm dữ liệu |
| **aggregate_id** | Hỗ trợ truy vấn/phân tích theo entity |
| **aggregate_version** | Hỗ trợ kiểm tra ordering, stale message hoặc gap |
| **processed_at** | Thời điểm local transaction ghi nhận xử lý thành công |

**consumer_name** không nhất thiết bằng tên Pod hoặc tên consumer group runtime. Nó là **identity logic của hiệu ứng**.

Ví dụ event **OrderPaid** có thể được dùng bởi:

- **order-search-v1** để cập nhật search index.
- **revenue-analytics-v1** để cộng doanh thu.
- **notification-intent-v1** để ghi ý định gửi thông báo.

Mỗi consumer cần quyết định phạm vi ledger riêng. Nếu ba handler dùng chung khóa chỉ theo eventId mà không có consumer_name, handler đầu có thể khiến hai handler còn lại tưởng event đã xử lý.

### 5.2. Khi đổi phiên bản handler

Nếu cần xây dựng lại một projection bằng logic hoàn toàn mới, có thể dùng **projection table mới + consumer_name mới** để cho phép đọc toàn bộ event lịch sử một cách hợp lệ.

Nhưng đổi consumer_name cho handler có **tác dụng phụ bên ngoài** sẽ khiến dedup cũ không còn hiệu lực. Không được đổi namespace tùy tiện rồi gửi lại email, refund hoặc charge cũ.

### 5.3. Có cần lưu toàn bộ payload?

Với ledger kiểu processed-message, thường chỉ cần event identity, dấu kiểm tra và metadata đủ vận hành. Lưu full payload:

- Tăng dung lượng và chi phí.
- Có thể sao chép PII nhạy cảm.
- Yêu cầu retention/deletion/backup phức tạp hơn.
- Có thể bị xem nhầm là source of truth.

Biến thể **durable receiver inbox** có thể cần envelope/payload để worker xử lý về sau; nhưng nên lưu tối thiểu, có mã hóa/quyền truy cập phù hợp và chính sách xóa rõ ràng.

## 6. PostgreSQL: chống trùng bằng INSERT ... ON CONFLICT

Một transaction cơ bản:

~~~sql
BEGIN;

INSERT INTO consumer_inbox (
    consumer_name,
    event_id,
    event_type,
    payload_fingerprint,
    aggregate_id,
    aggregate_version
)
VALUES (
    'fulfillment-order-paid-v1',
    'evt-001',
    'order.paid.v1',
    'sha256-of-canonical-payload',
    'ord-123',
    4
)
ON CONFLICT (consumer_name, event_id) DO NOTHING;

-- Chỉ thực hiện thay đổi nghiệp vụ khi INSERT thật sự thêm 1 dòng.
-- Kiểm tra số affected rows trong application.

INSERT INTO shipments (
    shipment_id,
    order_id,
    status
)
VALUES ('ship-001', 'ord-123', 'PENDING');

COMMIT;
~~~

**Quan trọng:** code phía ứng dụng **phải** kiểm tra số row INSERT Inbox thực sự thành công; không được chạy INSERT shipment vô điều kiện như một script thô ở trên. Đoạn SQL chỉ minh họa các lệnh sẽ nằm trong cùng transaction khi event là mới.

Nên thêm unique constraint nghiệp vụ:

~~~sql
ALTER TABLE shipments
ADD CONSTRAINT uq_shipments_order_id UNIQUE (order_id);
~~~

Ràng buộc nghiệp vụ giúp chặn lỗi khi eventId khác nhưng cùng orderId, hoặc khi logic producer phát hai sự kiện có ý nghĩa trùng. Nếu một order được phép nhiều chuyến giao, khóa phải được thiết kế theo **shipment intent ID/fulfillment request ID** thay vì đơn giản là orderId.

### 6.1. Concurrency: hai worker cùng thấy một event

~~~text
Worker A                          Worker B
   |                                 |
BEGIN                              BEGIN
   |                                 |
INSERT inbox(evt-1)                INSERT inbox(evt-1)
   |                                 |
unique constraint xử lý xung đột, không dựa vào
SELECT trước rồi INSERT theo kiểu check-then-act
   |                                 |
A commit/rollback                B nhận kết quả tương ứng
~~~

Với PostgreSQL, unique constraint/transaction isolation quyết định tiến trình nào chờ và tiến trình nào thêm marker. Nếu A commit, B sẽ không tạo marker trùng. Nếu A rollback, B có thể thêm marker rồi xử lý. Cần test bằng concurrency thực, không chỉ unit test tuần tự.

### 6.2. Cùng ID nhưng payload khác

Nếu eventId bị tái sử dụng cho payload khác, bỏ qua một cách im lặng có thể che lỗi nguồn. Khi **ON CONFLICT** xảy ra, hệ thống có thể đọc fingerprint đã lưu và so với payload nhận được, rồi cảnh báo hoặc cách ly sự kiện có identity bất thường.

Fingerprint cần có định nghĩa ổn định (canonical JSON, định dạng bytes hoặc các trường nghiệp vụ xác định). Hash trực tiếp chuỗi JSON với thứ tự field/whitespace khác nhau có thể tạo false mismatch. Không dùng fingerprint như phương án thay thế cho chữ ký/xác thực producer.

## 7. Ví dụ Java/Spring: transaction xử lý Inbox

Giả sử consumer nhận một **OrderPaid** event. Nó cần tạo một **fulfillment intent** trong PostgreSQL của Fulfillment và ghi Inbox marker trong cùng transaction.

### 7.1. Domain contract đơn giản

~~~java
public record OrderPaid(
    String eventId,
    String orderId,
    String paymentId,
    long aggregateVersion
) {}
~~~

Trong thực tế cần validation, producer authentication, schema version, correlation ID và payload hash; ví dụ tập trung vào transaction và dedup.

### 7.2. Handler dùng JdbcTemplate

~~~java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderPaidHandler {

    private final JdbcTemplate jdbc;

    public OrderPaidHandler(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public ProcessingResult apply(OrderPaid event) {
        int inserted = jdbc.update("""
            INSERT INTO consumer_inbox (
                consumer_name, event_id, event_type,
                payload_fingerprint, aggregate_id, aggregate_version
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT (consumer_name, event_id) DO NOTHING
            """,
            "fulfillment-order-paid-v1",
            event.eventId(),
            "order.paid.v1",
            fingerprint(event),
            event.orderId(),
            event.aggregateVersion()
        );

        if (inserted == 0) {
            // Đơn giản hóa: production nên đối chiếu fingerprint
            // và cảnh báo nếu cùng eventId mang payload khác.
            return ProcessingResult.DUPLICATE;
        }

        jdbc.update("""
            INSERT INTO fulfillment_intents (
                intent_id, order_id, payment_id, status
            )
            VALUES (?, ?, ?, 'PENDING')
            ON CONFLICT (intent_id) DO NOTHING
            """,
            "fulfill-" + event.paymentId(),
            event.orderId(),
            event.paymentId()
        );

        return ProcessingResult.APPLIED;
    }

    private String fingerprint(OrderPaid event) {
        // Ví dụ placeholder: triển khai canonicalize + SHA-256 ổn định.
        return "payload-hash-from-validated-envelope";
    }

    public enum ProcessingResult {
        APPLIED, DUPLICATE
    }
}
~~~

**Giả định vận hành của mẫu:**

1. **fulfillment_intents** có unique constraint cho **intent_id** và các ràng buộc nghiệp vụ cần thiết.
2. **consumer_inbox** và **fulfillment_intents** thuộc cùng một transaction manager/database.
3. Nếu một lỗi database xảy ra sau INSERT Inbox mà trước commit, transaction phải rollback; không được bắt lỗi rồi vẫn commit.
4. **fingerprint()** ở đây chỉ là placeholder minh họa vị trí tính hash, không phải triển khai thật; production phải dùng canonicalization và hashing đúng.
5. Return **DUPLICATE** mới chỉ chứng minh đã có marker với cùng eventId; nên kiểm tra payload fingerprint, consumer version và trạng thái business khi cần.
6. Fulfillment intent là **ý định thực hiện**, chưa phải khẳng định đã giao hàng hoặc đã gọi hãng vận chuyển thành công.
7. Nếu handler phải gọi REST bên ngoài, không đặt lời gọi đó giữa transaction chỉ vì đã có **@Transactional**; cần Outbox/worker và idempotency riêng.

**Tại sao code chỉ tạo intent?** Vì tạo một bản ghi trong cùng DB có thể atomic với Inbox marker. Còn gọi nhà vận chuyển qua HTTP không thể rollback bằng local transaction Fulfillment.

### 7.3. Kafka listener và ACK sau khi DB commit

Một ví dụ bố trí lớp:

~~~java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.support.Acknowledgment;
import org.springframework.stereotype.Component;

@Component
public class OrderPaidConsumer {

    private final OrderPaidHandler handler;

    public OrderPaidConsumer(OrderPaidHandler handler) {
        this.handler = handler;
    }

    @KafkaListener(
        topics = "order-events",
        groupId = "fulfillment-order-paid"
    )
    public void onMessage(OrderPaid event, Acknowledgment ack) {
        // Handler là bean khác; @Transactional áp dụng qua proxy.
        // Thành công hoặc trùng đã được xử lý bền vững.
        handler.apply(event);

        // Chỉ ACK sau khi DB transaction trả về thành công.
        ack.acknowledge();
    }
}
~~~

**Mẫu này cần containerFactory được cấu hình manual acknowledgment thích hợp**, consumer deserializer/schema, error handler và offset commit policy. Không copy vào production mà bỏ qua cấu hình Kafka listener. Không swallow exception ở **handler.apply** rồi ACK; lỗi phải khiến broker/retry flow xử lý theo chính sách.

**Cần phân biệt ACK và commit offset trong Kafka:** cơ chế, thời điểm commit và xử lý lỗi phụ thuộc ack mode, concurrency, error handler và transactional integration của Spring Kafka. ACK tại đây biểu thị ý định xác nhận sau local commit; bảo đảm thật phải được xác minh bằng integration test với broker và database.

### 7.4. Vấn đề commit offset khi có nhiều record

Trong Kafka, offset là **tiến độ theo partition**. Không nên commit một offset sau khi message sau đã hoàn thành nếu message trước cùng partition vẫn đang xử lý thất bại mà chưa có cơ chế bảo vệ tương ứng. Nếu xử lý song song, phải thiết kế partition ordering, xử lý gap và checkpoint đúng.

Một ledger theo eventId có thể chịu redelivery của message cũ, nhưng không tự đảm bảo trạng thái được xây dựng đúng nếu event cùng aggregate áp dụng **sai thứ tự**. Ordering vẫn cần giải quyết riêng.

## 8. Biến thể B: durable receiver inbox trước khi xử lý

Không phải mọi handler có thể hoàn tất trong một transaction ngắn ngay khi broker giao event. Một service có thể muốn **nhận bền vững**, ACK broker sớm và xử lý bởi worker độc lập.

~~~text
Broker
   |
   | message M
   v
Receiver
   |
BEGIN
  INSERT inbox_records(M, status='RECEIVED')
COMMIT
   |
   v
ACK broker
   |
   v
Inbox Worker
   |
   +--> claim/lease record
   +--> run business processing
   +--> mark COMPLETED or schedule retry
~~~

Điều khác biến thể A:

- ACK có thể xảy ra khi message mới được **lưu bền vững**, chưa được xử lý nghiệp vụ.
- Inbox table **trở thành hàng đợi nội bộ** và phải có worker, retry, monitoring, retention, capacity/backpressure.
- Khi worker crash, record vẫn còn để xử lý tiếp.
- Nếu worker thực hiện side effect rồi crash trước khi mark COMPLETED, side effect có thể bị lặp; phải có idempotency/Outbox hoặc cách đối soát riêng.

Đây là pattern hữu ích để **tách nhịp tiêu thụ broker khỏi nhịp xử lý nghiệp vụ**, nhưng làm tăng độ trễ và trách nhiệm vận hành.

### 8.1. Schema cho durable receiver inbox

~~~sql
CREATE TABLE inbox_records (
    id                  BIGSERIAL PRIMARY KEY,
    consumer_name       TEXT NOT NULL,
    event_id            TEXT NOT NULL,
    event_type          TEXT NOT NULL,
    payload             JSONB NOT NULL,
    status              TEXT NOT NULL DEFAULT 'RECEIVED',
    attempts            INTEGER NOT NULL DEFAULT 0,
    next_attempt_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    leased_by           TEXT,
    lease_until         TIMESTAMPTZ,
    last_error_code     TEXT,
    received_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at        TIMESTAMPTZ,
    UNIQUE (consumer_name, event_id),
    CHECK (status IN (
        'RECEIVED', 'PROCESSING', 'RETRY', 'COMPLETED', 'QUARANTINED'
    ))
);

CREATE INDEX idx_inbox_ready
    ON inbox_records (status, next_attempt_at, id);
~~~

Các trường là mẫu thiết kế, cần xem xét index/cardinality, lock contention, kích thước payload, retention, policy dữ liệu nhạy cảm và scalability.

### 8.2. Trạng thái

~~~text
                    +-------------------+
                    | RECEIVED          |
                    +---------+---------+
                              |
                           claim
                              v
                    +-------------------+
                    | PROCESSING        |
                    +------+------------+
                           |
                +----------+----------+
                |                     |
             success               transient error
                |                     |
                v                     v
           COMPLETED               RETRY
                                      |
                                next_attempt
                                      |
                                      v
                                  PROCESSING

           permanent failure / exhausted policy
                                      |
                                      v
                                  QUARANTINED
~~~

**PROCESSING** phải có lease/claim timeout hoặc cơ chế tương đương: nếu worker chết, một worker khác có thể lấy lại công việc sau khi lease hết hạn. Nếu chỉ đặt PROCESSING và không có đường recovery, message bị mắc kẹt vĩnh viễn.

### 8.3. Claim record bằng row lock

Ví dụ PostgreSQL, chọn một số message sẵn sàng xử lý:

~~~sql
WITH candidates AS (
    SELECT id
    FROM inbox_records
    WHERE (
        status IN ('RECEIVED', 'RETRY')
        OR (status = 'PROCESSING' AND lease_until < NOW())
    )
      AND next_attempt_at <= NOW()
    ORDER BY next_attempt_at, id
    FOR UPDATE SKIP LOCKED
    LIMIT 20
)
UPDATE inbox_records i
SET
    status = 'PROCESSING',
    leased_by = :worker_id,
    lease_until = NOW() + INTERVAL '30 seconds',
    attempts = attempts + 1
FROM candidates
WHERE i.id = candidates.id
RETURNING i.*;
~~~

Các worker có thể chia nhau record bằng **FOR UPDATE SKIP LOCKED**, khi transaction claim được commit đúng. Nhưng một lease 30 giây chỉ là ví dụ, không phải giá trị mặc định.

**Cảnh báo:** lease hết không chứng minh worker cũ đã ngừng. Có thể có hai worker cùng đang xử lý một event khi worker cũ bị chậm, pause hoặc mất kết nối rồi hoạt động trở lại. Để tránh side effect kép cần:

- Idempotency của thao tác nghiệp vụ.
- **Fencing token / claim version** nếu resource có thể kiểm tra generation.
- Gia hạn lease có kiểm soát cho tác vụ dài.
- So sánh **leased_by, claim_version** khi mark COMPLETED.
- Không dùng lease như bảo đảm exactly-once.

Một thiết kế production thường thêm **claim_version** tăng đơn điệu. Các update state và thao tác với resource có hỗ trợ fencing phải xác nhận phiên claim mới nhất. Nếu external API không hỗ trợ fencing, business idempotency key vẫn là cơ chế quan trọng.

### 8.4. Đánh dấu COMPLETED an toàn

Một worker có thể xử lý business change ở cùng DB với inbox_records. Khi đó nên để **business update + state COMPLETED** trong cùng local transaction, sau khi xác thực claim hợp lệ.

Nếu xử lý gồm HTTP bên ngoài, không thể atomically mark COMPLETED cùng request HTTP; cần mô hình outbox/dispatch và xác định “COMPLETED” nghĩa là:

- Đã tạo durable intent để gửi?
- Đã gửi tới provider?
- Provider xác nhận chấp nhận?
- Hay nghiệp vụ cuối đã được xác minh?

Không thể dùng một status COMPLETED mơ hồ cho mọi bước có mức độ bảo đảm khác nhau.

## 9. Hai biến thể Inbox khác nhau thế nào?

| Khía cạnh | Transactional ledger | Durable receiver inbox |
|---|---|---|
| Điểm ACK broker | Sau khi local business transaction commit | Sau khi message được ghi bền vào inbox |
| Tác vụ ban đầu | Dedup + thay đổi nghiệp vụ ngắn | Persist envelope, xử lý sau |
| Cần worker nội bộ | Không bắt buộc | Có |
| Trạng thái | Có thể chỉ có marker đã xử lý | RECEIVED/PROCESSING/RETRY/COMPLETED |
| Latency nghiệp vụ | Phụ thuộc thời gian handler | Có thể có queue lag |
| Recovery | Broker redelivery + DB dedup | Inbox worker retry/claim + DB dedup |
| Backpressure | Theo broker consumer | Cả broker và inbox backlog |
| Rủi ro bên ngoài DB | Cần Outbox/idempotency riêng | Cũng cần Outbox/idempotency riêng |
| Độ phức tạp | Thấp hơn nếu handler chỉ dùng một DB | Cao hơn nhưng tách nhịp xử lý |

Khi chọn, hãy hỏi **điểm nào cần được xem là “đã nhận thành công”** trong hợp đồng giữa các hệ thống. Không nên ACK broker sớm nếu local inbox chưa thực sự durable.

## 10. Inbox và Transactional Outbox là hai nửa của dòng sự kiện đáng tin cậy

Một cặp pattern thông dụng:

~~~text
Order Service                                Fulfillment Service

BEGIN transaction                           Receive event
  UPDATE order                              |
  INSERT outbox(order.paid)                 v
COMMIT                                      BEGIN transaction
  |                                           INSERT inbox(eventId)
  v                                           INSERT fulfillment_intent
Outbox publisher                           COMMIT
  |                                           |
  +----> Message broker ---------------------+
                                             |
                                           ACK broker
~~~

### Outbox bảo vệ phía gửi

Nếu Order commit mà tiến trình crash trước khi publish, outbox record còn lại để relay gửi sau. Nhưng publisher có thể phát trùng nếu crash sau khi broker nhận event mà trước khi đánh dấu outbox đã gửi.

### Inbox bảo vệ phía nhận

Fulfillment biết eventId nào đã được áp dụng thành công. Nếu broker redeliver, nó không tạo thêm fulfillment intent.

### Cả hai không tự bảo vệ external side effect

Ví dụ Fulfillment cần gọi hãng vận chuyển. Lệnh gọi đó nên mang **shipment operation ID ổn định**, và provider cần hỗ trợ idempotency/status query hoặc một quy trình đối soát.

**Outbox + Inbox thường giúp hướng tới một business effect ổn định**, không bảo đảm mọi giao thức mạng đều “giao chính xác một lần” theo nghĩa tuyệt đối.

## 11. Vì sao consumer offset không thay thế Inbox?

Một số đội hỏi: “Kafka đã có consumer group offset, sao còn cần bảng Inbox?”

Vì offset và business state được ghi ở **hai nơi khác nhau**:

~~~text
Kafka committed offset       Database commit state
          |                          |
          +---------- không tự atomic nhau ----------+
~~~

Các cửa sổ:

1. DB commit trước, Kafka offset commit sau: crash → message redelivery.
2. Kafka offset commit trước, DB commit sau: crash → có thể mất business effect.
3. DB commit thành công, phản hồi Kafka ACK bị mất: message có thể được gửi lại.
4. Consumer rebalance hoặc retry làm một record được xử lý bởi instance khác.

Inbox gắn identity xử lý với business transaction tại DB. Nhưng Kafka offset vẫn cần để quản lý tiến độ, partition ordering và tài nguyên broker. **Hai cơ chế bổ sung nhau**.

Một số stream processing framework hoặc broker transaction hỗ trợ atomicity trong phạm vi xác định, chẳng hạn Kafka-to-Kafka. Phải xem chính xác những resource nào thuộc cùng transaction. Không mặc định nó cũng bảo vệ một PostgreSQL write hoặc HTTP charge bên ngoài.

## 12. Chọn khóa dedup: eventId, messageId hay operationId?

### 12.1. Event identity

Nếu producer phát cùng một event lại với **cùng eventId**, consumer có thể dedup theo **(consumerName, eventId)**.

Ưu điểm: rõ ràng, giữ được qua broker redelivery và replay nếu envelope ổn định.

Giới hạn: nếu producer tạo **hai event khác ID cho cùng thao tác**, ledger không coi chúng trùng.

### 12.2. Business operation identity

Một số hành vi cần ràng buộc theo operation:

- Một lần capture payment: **captureOperationId**.
- Một lệnh tạo shipment: **fulfillmentIntentId**.
- Một lần reserve inventory: **reservationOperationId**.
- Một webhook notification logic: **notificationIntentId**.

Ví dụ, consumer nhận hai event **PaymentSucceeded** có eventId khác nhau nhưng cùng **paymentId**. Nếu handler phải tạo một invoice cho payment đó, **UNIQUE(paymentId)** hoặc unique business key tương đương là tuyến phòng thủ quan trọng.

### 12.3. Aggregate version

Nếu event cùng aggregate cần được xử lý theo thứ tự, một số consumer cần khóa/version:

~~~text
Order ord-123:
   version 1: CREATED
   version 2: PAID
   version 3: SHIPPED
~~~

Consumer chỉ ghi **version 2** khi đã có version 1 nếu thuật toán phụ thuộc các thay đổi liên tiếp. Nếu event version 3 tới trước version 2, một upsert “chỉ nhận version lớn hơn” có thể đúng cho **snapshot event chứa toàn trạng thái** nhưng sai cho **delta event cần áp đủ từng bước**.

Ledger chống trùng không tự giải quyết gap hoặc out-of-order. Cần:

- Partitioning/ordering theo aggregate khi broker hỗ trợ.
- Trường aggregateVersion hay sequence.
- Version guard và chính sách phát hiện thiếu event.
- Buffer/quarantine/retry khi chưa có predecessor.
- Snapshot/rebuild để khôi phục nếu mất sự kiện.

## 13. Nhiều consumer và nhiều handler: phạm vi sổ ghi nhận

Giả sử event **OrderPaid** được ba hệ thống dùng:

~~~text
order.paid.v1
      |
      +--> SearchProjectionHandler
      |
      +--> RevenueAnalyticsHandler
      |
      +--> FulfillmentIntentHandler
~~~

Nếu mọi handler dùng một bảng chung với PRIMARY KEY(eventId), handler Search xử lý trước sẽ “chiếm” event và hai handler sau bỏ qua nhầm.

Một phương án là PRIMARY KEY(consumerName, eventId), trong đó consumerName có nghĩa **đơn vị logic sở hữu hiệu ứng**.

Với một consumer phức hợp thực hiện nhiều loại hiệu ứng, có thể tách ledger theo từng effect intent hoặc dùng một transaction thống nhất nếu tất cả hiệu ứng nằm trong cùng local DB. Nếu một phần thành công, một phần thất bại ngoài DB, đánh dấu toàn event “đã xử lý” dễ che mất việc chưa hoàn tất.

**Nên viết hợp đồng rõ:** marker trong ledger chứng minh **đã áp dụng phần nào**? Domain state update, outbox intent, notification delivery, hay cả workflow terminal?

## 14. Inbox retention: giữ marker trong bao lâu?

Một rủi ro bị bỏ quên:

~~~text
Broker giữ event lịch sử 30 ngày.
Inbox ledger chỉ giữ marker 3 ngày.

Ngày 10: replay lại event ngày 1.
Marker đã bị xóa.
Handler tưởng message mới.
=> Có thể tạo tác dụng phụ trùng.
~~~

Cửa sổ dedup nên được chọn theo khả năng message được giao lại **và** yêu cầu bảo vệ nghiệp vụ.

Những yếu tố cần xem:

1. Broker retention và vùng lịch sử có thể replay.
2. Kho archive/event store có thể cho replay lâu hơn broker không?
3. Thời hạn retry/reconciliation/DLQ redrive.
4. Có event duplicate do hệ thống đối tác phát lại sau nhiều tháng không?
5. Những tác dụng phụ nào không được lặp dù sau nhiều năm?
6. Có thể dùng business unique key/trạng thái cuối để bảo vệ lâu dài mà không giữ mọi event marker không?
7. Yêu cầu xóa dữ liệu, pháp lý, dữ liệu nhạy cảm và chi phí storage.

**Không có một TTL Inbox đúng cho mọi hệ thống.** Với payment/refund, có thể cần bảo vệ bởi identity nghiệp vụ tồn tại lâu dài; với cache projection có thể tái dựng, marker có thể quản lý theo lifecycle projection và replay plan.

### 14.1. Đừng xóa marker chỉ vì status COMPLETED

Một ledger có vài triệu record mỗi ngày sẽ lớn nhanh. Có thể partition theo thời gian, archive hoặc dọn theo policy. Nhưng trước khi xóa phải xác định:

- Nguồn message cũ còn có thể xuất hiện trong bao lâu.
- Business unique constraint còn bảo vệ được gì.
- Snapshot/checkpoint nào đã trở thành nguồn phục hồi mới.
- Replay operator có được phép bỏ qua dedup cũ hay không.
- Dữ liệu nào phải xóa theo privacy policy.

Giảm dung lượng ledger bằng cách hạ TTL xuống vài giờ **không an toàn** nếu DLQ hoặc replay có thể đưa message cũ trở lại sau nhiều ngày.

## 15. ACK, retry và Dead-letter queue: thứ tự nào an toàn?

### 15.1. Thành công

~~~text
Receive -> BEGIN -> Inbox + Domain COMMIT -> ACK
~~~

### 15.2. Duplicate đã commit trước

~~~text
Receive -> kiểm tra Inbox cho biết đã xử lý
        -> không chạy lại business effect
        -> ACK
~~~

### 15.3. Lỗi tạm thời trước commit

~~~text
Receive -> BEGIN -> lỗi DB -> ROLLBACK
        -> không ACK thành công
        -> retry/backoff theo policy
~~~

### 15.4. Poison message

Ví dụ schema không tương thích hoặc dữ liệu vi phạm invariant. Không nên retry vô hạn cùng event khiến partition/queue tắc nghẽn.

Cần policy:

- Số lần retry và backoff.
- Cách phân loại lỗi **transient** với **permanent**.
- Nơi cách ly message, reason code, stack trace đã được lọc bí mật.
- Ai chịu trách nhiệm sửa dữ liệu/handler.
- Khi nào được redrive từ DLQ.
- Trước khi ACK message gốc, DLQ/quarantine đã được ghi **bền vững** chưa?
- Nếu broker/DB không có atomic handoff tới DLQ, xử lý khả năng publish DLQ trùng hoặc thất bại như thế nào?

**Đừng đánh dấu COMPLETED chỉ vì đã bỏ vào DLQ.** Cần trạng thái nói rõ message chưa áp dụng business effect hoặc bị quarantine theo policy.

### 15.5. Retry vô hạn với lỗi nghiệp vụ có thể sai

Một event yêu cầu phát hành shipment nhưng order chưa tồn tại có thể là **event đến sai thứ tự** và cần retry có giới hạn hoặc chờ predecessor. Nhưng nếu orderId bị giả mạo và không bao giờ hợp lệ, retry mãi sẽ lãng phí tài nguyên. Phân biệt bằng evidence, timeout nghiệp vụ và đường điều tra.

## 16. Khi Inbox và business state nằm ở hai database

Giả sử ledger nằm trong PostgreSQL A còn business state nằm trong PostgreSQL B. Code gọi:

~~~text
INSERT inbox trong DB-A -> COMMIT
UPDATE domain trong DB-B -> COMMIT
~~~

Đây là **hai local transactions**, không atomic với nhau. Crash giữa hai bước có thể làm consumer ghi đã xử lý nhưng chưa cập nhật domain.

Một số lựa chọn:

- Đặt Inbox ledger và business state cùng một database/transaction manager nếu khả thi.
- Thiết kế **durable inbox + worker** với trạng thái tiến độ và business idempotency, để không cần giả định cùng transaction.
- Dùng transactional outbox/command intent khi một bước cần chuyển tới resource khác.
- Nếu yêu cầu global atomic commit thực sự và các resource phù hợp, đánh giá 2PC/XA cùng toàn bộ trade-off blocking/recovery; không giả định Spring @Transactional tự tạo 2PC.
- Thay đổi service boundary để những bất biến cần atomic nằm trong cùng owner.

**Điểm kiểm tra:** mọi dấu “đã xử lý” chỉ được coi là cuối cùng khi các hiệu ứng mà dấu đó đại diện đã được xác nhận theo hợp đồng.

## 17. External side effects: gọi Payment, Email hoặc Webhook

Ledger có thể bảo vệ database state, nhưng không tự bảo vệ lời gọi ngoài transaction.

### 17.1. Lỗi điển hình: đã gửi email nhưng chưa lưu marker

~~~text
Consumer nhận OrderPaid
   |
Email Provider gửi thành công
   |
Consumer crash trước Inbox COMMIT
   |
Broker redelivery
   |
Email được gửi lại
~~~

Nếu đổi thứ tự, ghi marker trước rồi email sau, crash có thể khiến email không được gửi bao giờ.

### 17.2. Thiết kế durable intent

Một phương án an toàn hơn về khả năng khôi phục:

~~~text
BEGIN DB transaction
    insert inbox(eventId)
    insert notification_outbox(notificationIntentId)
COMMIT
ACK broker

Outbox dispatcher
    |
    +-- send email with stable request/intent ID
    |
    +-- record provider outcome
~~~

Nếu provider có idempotency key, dùng **notificationIntentId** ổn định. Nếu provider không hỗ trợ, vẫn có thể xảy ra trường hợp “đã gửi nhưng mất response”. Cần:

- Chính sách retry hạn chế.
- Trạng thái UNKNOWN/PENDING khi kết quả chưa rõ.
- Cơ chế tìm trạng thái provider hoặc đối soát khi có.
- Ghi nhật ký gửi/nhận đủ để hỗ trợ.
- Tránh tuyên bố “exactly one email” nếu hệ thống thực tế chỉ có at-least-once attempt.

### 17.3. Payment và refund còn nhạy cảm hơn

Một event **OrderCreated** không được khiến consumer tự gọi charge mà không có business operation ID. Nếu charge timeout, không tạo charge mới bằng ID mới. Cần dùng cùng idempotency key theo hợp đồng provider và đối soát kết quả cũ trước khi quyết định retry hay compensation.

Inbox chỉ là một lớp trong chiến lược **idempotency end-to-end**, không thay thế state machine tài chính.

## 18. Inbox và replay: xây lại projection thế nào?

Consumer Search cần dựng lại index sau bug. Nếu đọc lại tất cả event với **consumer_name cũ**, Inbox nói event đã xử lý và bỏ qua toàn bộ; index mới vẫn trống.

Cách tiếp cận hợp lý:

1. Xác định đây là **rebuild projection**, không phải workflow phát lệnh nghiệp vụ.
2. Tạo bảng/index mới và namespace ledger mới, ví dụ search-projection-v2.
3. Dùng consumer group/replay job riêng, không reset live consumer group nếu không có kế hoạch.
4. Chọn snapshot/cutoff rõ và đọc lịch sử đủ.
5. Áp event theo ordering/version yêu cầu, không gọi external side effect.
6. Đối soát số bản ghi, trạng thái, tombstone, schema và độ trễ.
7. Bắt kịp live stream và chuyển read alias/route khi đạt guardrail.
8. Giữ khả năng rollback rồi dọn namespace cũ theo policy.

**Không áp dụng quy trình đổi namespace như vậy cho Payment/Notification**, vì nó mở khóa xử lý lại các hiệu ứng bên ngoài có thể đã xảy ra. Với những consumer đó, cần đối soát business operation status, dedup key và giới hạn redrive.

### 18.1. Khi lịch sử không còn đủ

Nếu broker chỉ giữ event 7 ngày, nhưng muốn dựng lại state 30 ngày trước, consumer group mới không tự tạo lại phần đã bị xóa. Phải có archive/snapshot/source of truth đủ hoặc công bố khoảng thiếu dữ liệu. Inbox không phải event store đầy đủ nếu chỉ lưu ID event.

### 18.2. Event schema đã đổi

Replay event v1 qua handler chỉ hiểu v3 có thể sai dù eventId hợp lệ. Cần schema version, upcaster/adapter, compatible defaults và kiểm thử trên dữ liệu cũ. Ledger bảo vệ **duplicate** chứ không kiểm chứng ý nghĩa event.

## 19. Xử lý ordering, gap và upsert

### 19.1. Idempotent không có nghĩa commutative

Giả sử hai event cùng order:

~~~text
v2: OrderPaid
v3: OrderCancelled
~~~

Nếu consumer nhận v3 trước v2, chỉ dedup theo eventId không bảo đảm kết quả hợp lệ. Một handler cần đảm bảo thứ tự hoặc có mô hình update không phụ thuộc thứ tự.

**Ba kiểu xử lý:**

- **Full-state event:** mỗi event chứa trạng thái mới đầy đủ; có thể dùng version guard, chỉ ghi nếu version lớn hơn.
- **Delta event:** áp chênh lệch, ví dụ +5 điểm; phải áp mỗi delta đúng một lần và xử lý version gap.
- **Command/event có điều kiện:** phải kiểm tra trạng thái hiện tại và phép chuyển trạng thái hợp lệ.

### 19.2. Ví dụ version guard

~~~sql
INSERT INTO order_read_model (
    order_id, status, aggregate_version
)
VALUES (:order_id, :status, :version)
ON CONFLICT (order_id)
DO UPDATE SET
    status = EXCLUDED.status,
    aggregate_version = EXCLUDED.aggregate_version
WHERE order_read_model.aggregate_version
      < EXCLUDED.aggregate_version;
~~~

Đoạn này phù hợp khi event mang **snapshot trạng thái tự đủ** và “giữ version mới nhất” là semantics mong muốn. Nó **không** thay thế việc xử lý event delta từng bước, phát hiện missing version hoặc các side effect phải xảy ra khi một transition cụ thể được áp dụng.

### 19.3. Không đánh dấu event đã xử lý nếu còn thiếu predecessor

Nếu handler đòi v2 có mặt trước v3, nhưng nhận v3 khi state mới ở v1:

- Từ chối/hoãn v3 trong transaction và rollback ledger marker, hoặc
- Lưu v3 vào durable inbox chờ thứ tự theo thiết kế.

Không mark v3 COMPLETED rồi bỏ qua chỉ vì hiện tại chưa áp dụng được; làm vậy khiến retry sau không còn cơ hội bổ sung event hợp lệ.

## 20. Schema cho sổ ghi nhận trạng thái chi tiết

Trong workflow dài, một bảng chỉ gồm eventId/processedAt có thể chưa đủ. Có thể xây **message processing ledger** chứa trạng thái từng bước:

~~~sql
CREATE TABLE message_processing_ledger (
    consumer_name       TEXT NOT NULL,
    message_id          TEXT NOT NULL,
    business_key        TEXT,
    status              TEXT NOT NULL,
    attempt_count       INTEGER NOT NULL DEFAULT 0,
    claim_version       BIGINT NOT NULL DEFAULT 0,
    last_error_code     TEXT,
    first_seen_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at        TIMESTAMPTZ,
    PRIMARY KEY (consumer_name, message_id),
    CHECK (status IN (
        'RECEIVED', 'IN_PROGRESS', 'WAITING', 'DONE', 'FAILED'
    ))
);
~~~

Cần quy định:

- Trạng thái **RECEIVED** có nghĩa payload đã được lưu bền ở đâu?
- **IN_PROGRESS** có lease/claim và recovery ra sao?
- **WAITING** đợi điều kiện nào hoặc callback nào?
- **DONE** chứng minh business effect nào đã hoàn thành?
- **FAILED** là terminal hay có thể được redrive?
- EventId và businessKey khác nhau thế nào?
- Ai thay đổi status, trong transaction nào?
- Khi nào purge marker mà vẫn an toàn với replay?

Bảng ledger chi tiết tăng khả năng quan sát nhưng cũng tăng chi phí và độ phức tạp. Chọn mức trạng thái theo workflow cần thiết, tránh tạo một transaction coordinator “thủ công” không có protocol rõ.

## 21. Một sự kiện – nhiều hiệu ứng: tách trạng thái hợp lý

Ví dụ consumer OrderPaid phải:

1. Cập nhật read model.
2. Tạo invoice intent.
3. Tạo notification intent.
4. Phát sự kiện FulfillmentRequested.

Nếu tất cả bốn bước được ghi vào **cùng một database** dưới dạng state/outbox intent, chúng có thể dùng chung transaction và một Inbox marker.

~~~text
BEGIN:
  INSERT Inbox(OrderPaid)
  UPDATE OrderReadModel
  INSERT InvoiceIntent
  INSERT NotificationOutbox
  INSERT FulfillmentOutbox
COMMIT
ACK broker
~~~

Tuy nhiên, nếu bước 2 gọi hệ thống kế toán bên ngoài ngay, còn bước 3 gọi Email API ngay, một Inbox marker đơn không đủ biểu diễn trạng thái của các hiệu ứng ngoài DB.

**Nguyên tắc:** chuyển external side effects thành **durable intents có identity riêng** rồi cho worker xử lý với idempotency và trạng thái theo từng operation. Nhờ vậy Inbox marker có nghĩa rõ ràng: **đã ghi nhận thành công các ý định phải thực hiện**, chưa phải mọi tác vụ bên ngoài đều hoàn tất.

## 22. Dữ liệu nhạy cảm và vòng đời của Inbox

Durable Inbox có thể lưu bản sao của event gốc chứa:

- Customer ID, email, địa chỉ.
- Payment reference và thông tin order.
- Token/metadata không nên được giữ lâu.
- Dữ liệu nhạy cảm dưới nhiều schema version.

Thiết kế cần:

1. Chỉ lưu trường thực sự cần cho retry/recovery.
2. Mã hóa phù hợp khi lưu và truyền dữ liệu.
3. Hạn chế quyền đọc dữ liệu Inbox theo service/đội vận hành.
4. Tránh ghi raw payload vào log lỗi hoặc traces.
5. Có retention và chính sách xóa phù hợp nghĩa vụ dữ liệu.
6. Xử lý bản sao trong backup, archive, DLQ và snapshot.
7. Ngăn replay khôi phục dữ liệu đã phải xóa.
8. Không dùng email/phone/raw userId làm metric label high-cardinality.
9. Định nghĩa ai được redrive message có tác dụng phụ.
10. Audit các thao tác xóa marker hoặc force retry.

**Dedupe retention và privacy retention có thể xung đột.** Có thể giữ business operation identity tối thiểu hoặc hash/cơ chế tối thiểu hóa dữ liệu phù hợp để bảo vệ idempotency lâu dài mà không giữ nguyên payload nhạy cảm.

## 23. Hiệu năng: Inbox có làm chậm consumer?

Inbox thêm ít nhất một DB operation và unique-index lookup cho mỗi event. Với tải lớn, nó có thể thành bottleneck:

- Unique index tăng kích thước theo số event.
- Insert conflict trên hot key gây contention.
- Bảng quá lớn làm vacuum/backup/index maintenance nặng.
- Durable Inbox lưu JSONB đầy đủ có thể tốn dung lượng.
- Worker retry liên tục tạo nhiều update trên một record.
- Nhiều message thuộc một aggregate tranh chấp business row.
- Purge/partition theo thời gian ảnh hưởng các truy vấn dedup nếu thiết kế chưa đúng.

Các hướng tối ưu có điều kiện:

1. Chọn khóa và index đúng workload; tránh thêm index không cần thiết.
2. Dùng INSERT ... ON CONFLICT thay check-then-insert.
3. Giữ local transaction ngắn, không gọi HTTP chậm khi giữ lock.
4. Partition/archive theo retention policy có bằng chứng về replay horizon.
5. Dùng batch processing **khi vẫn bảo vệ atomicity và checkpoint đúng**.
6. Giới hạn worker concurrency theo capacity database và per-aggregate ordering.
7. Dùng backpressure/rate limit để tránh overload.
8. Tách dữ liệu envelope khỏi processing metadata nếu payload lớn.
9. Theo dõi p95/p99 xử lý, lock waits và DB saturation.
10. Đừng tối ưu bằng cách xóa marker sớm đến mức làm hỏng dedup.

Không có throughput tối đa phổ quát. Một ledger nhỏ với 1.000 event/giây và một ledger lớn với hàng trăm nghìn event/giây cần cấu hình, lưu trữ và mô hình partition khác nhau; phải benchmark theo workload thực tế.

## 24. Observability và cảnh báo

| Metric | Ý nghĩa |
|---|---|
| Received message count | Số lần broker giao message |
| Unique events applied | Số event thật sự tạo business effect local |
| Duplicate suppressed count | Số lần redelivery/replay được chặn |
| Inbox insert conflict rate | Tín hiệu duplicate hoặc lỗi identity |
| Inbox backlog size | Durable Inbox còn bao nhiêu record chưa DONE |
| Oldest pending age | Message lâu nhất chưa hoàn thành |
| Worker claim/lease expiry | Phát hiện worker crash, task bị lấy lại |
| Retry attempts / backoff | Phân biệt transient failure và poison |
| Quarantined/DLQ count | Số event cần can thiệp |
| Handler latency p50/p95/p99 | Thời gian xử lý local business transaction |
| Database lock wait / deadlocks | Tắc nghẽn unique index và domain rows |
| Broker lag / offset commit failures | Khoảng cách consumer với producer |
| Inbox-vs-business mismatch | Marker có nhưng business effect không đủ hoặc ngược lại |
| External side-effect duplicate incidents | Lỗi nghiêm trọng Inbox không ngăn được |
| Dedup retention horizon | Thời gian marker còn bảo vệ được |
| Schema mismatch count | Event cũ/mới không tương thích |
| Recovery/redrive duration | Năng lực xử lý sự cố |

Trace/log có thể ghi **eventId, businessOperationId, consumerName, aggregateId, traceId**, nhưng cần bảo vệ giá trị nhạy cảm; tránh biến chúng thành metric labels gây cardinality rất cao. Một cảnh báo tốt không chỉ nói “Inbox queue lớn” mà chỉ ra business capability, thời gian backlog và số message đang bị kẹt theo trạng thái.

## 25. Test cần chạy: không chỉ happy path

| Tình huống | Cách mô phỏng | Kết quả mong đợi |
|---|---|---|
| Event mới | Broker giao một event hợp lệ | Một business effect, marker lưu |
| Duplicate đơn giản | Giao cùng eventId hai lần | Chỉ một business effect |
| Hai worker đồng thời | Hai consumer xử lý cùng ID | Unique constraint chỉ cho một transaction áp dụng |
| Crash trước COMMIT | Kill sau insert marker trước commit | Marker và business change rollback, redelivery xử lý lại |
| Crash sau COMMIT, trước ACK | Kill sau DB commit | Broker redeliver; ledger chặn duplicate |
| ACK thất bại | Giả lập broker không nhận ACK | Redelivery không gây effect kép |
| Business update exception | Throw sau inbox INSERT | Cả marker và domain change rollback |
| Cùng ID, payload khác | Producer gửi eventId trùng với nội dung khác | Phát hiện fingerprint mismatch, không bỏ qua âm thầm |
| Cùng operation, khác event ID | Gửi hai event cho cùng payment/shipment | Business unique key/idempotency ngăn effect kép |
| Out-of-order | Gửi aggregate v3 trước v2 | Không áp sai hoặc bỏ quên predecessor |
| Missing predecessor | Không có v2 nhưng nhận v3 | Message được retry/quarantine thay vì mark DONE sai |
| External API timeout | Provider xử lý nhưng mất response | Operation status/idempotency ngăn tác dụng phụ lặp |
| Worker lease expiry | Tạm dừng worker lâu hơn lease | Claim/fencing + idempotency giữ an toàn |
| Poison message | Event schema sai vĩnh viễn | Retry giới hạn, quarantine/DLQ và giám sát |
| Replay dài ngày | Replay event ngoài TTL marker | Có business safeguard hoặc kiểm soát phạm vi replay |
| Rebuild projection | Dựng index mới với namespace riêng | Không kích hoạt lại notification/payment |
| Retention cleanup | Purge marker theo policy | Không làm mất bảo đảm đã công bố |
| Consumer rebalance | Đổi partition owner khi đang xử lý | Không ack quá sớm, duplicate được chặn |

### 25.1. Kịch bản crash đáng thử nhất

~~~text
1. Consumer nhận OrderPaid(evt-888).
2. BEGIN transaction.
3. INSERT Inbox(evt-888).
4. INSERT fulfillment_intent(intent-888).
5. COMMIT thành công.
6. Kill consumer trước ACK broker.
7. Khởi động consumer lại.
8. Broker gửi lại evt-888.
9. Consumer nhận thấy Inbox conflict và ACK.
10. Kiểm tra chỉ có một intent-888.
~~~

Nếu chỉ assert listener chạy thành công hai lần, test chưa chứng minh được idempotency. Cần đọc business state thật và kiểm tra số bản ghi/hiệu ứng.

### 25.2. Test ACK trước commit

Cố tình thiết kế một phiên bản lỗi trong môi trường lab: ACK message rồi throw exception trước DB COMMIT. Quan sát message không còn được broker retry theo cơ chế thông thường dù domain state không thay đổi. Bài thử cho thấy tại sao hệ thống phải chọn điểm ACK đúng.

Không chạy failure injection trên production nếu chưa có kế hoạch bảo vệ dữ liệu và người dùng.

## 26. Ví dụ kiến trúc hoàn chỉnh: OrderPaid → Fulfillment

### 26.1. Bên gửi

Order Service nhận kết quả Payment, cập nhật order state:

~~~text
BEGIN
  UPDATE orders SET status='PAID'
  INSERT order_outbox(
      eventId='evt-123',
      eventType='order.paid.v1',
      payload=...
  )
COMMIT
~~~

Outbox relay phát **evt-123** lên broker. Relay có thể publish trùng nhưng vẫn dùng cùng eventId theo contract producer.

### 26.2. Bên nhận

Fulfillment Consumer xử lý:

~~~text
Receive evt-123
   |
BEGIN
  INSERT inbox('fulfillment-order-paid-v1', 'evt-123')
  Nếu trùng: skip
  Nếu mới:
      INSERT fulfillment_intent(
          id='fulfillment:payment-456',
          orderId='ord-123',
          status='PENDING'
      )
      INSERT fulfillment_outbox(
          eventType='fulfillment.requested.v1',
          intentId='fulfillment:payment-456'
      )
COMMIT
   |
ACK
~~~

Fulfillment Dispatcher sau đó gửi command cho hệ thống giao hàng với intent ID ổn định. Nếu provider không có idempotency, cần đối soát và chính sách retry an toàn.

### 26.3. Chuỗi lỗi và kết quả

| Lỗi xảy ra | Điều còn lại | Khi khôi phục |
|---|---|---|
| Order crash trước COMMIT | Không có order paid/outbox | Retry transaction nghiệp vụ theo idempotency |
| Order crash sau COMMIT, trước publish | Outbox còn event | Relay publish sau |
| Relay publish rồi crash trước mark sent | Broker có thể nhận duplicate | Fulfillment Inbox dedup |
| Fulfillment crash trước DB COMMIT | Không có marker/intent | Broker redelivery để xử lý lại |
| Fulfillment crash sau COMMIT, trước ACK | Có marker + intent | Broker redelivery; Inbox skip |
| Fulfillment Dispatcher timeout sau provider accepted | Intent vẫn có trạng thái cần đối soát | Không tự gửi operation mới với key mới |
| Event mới đến trước event phụ thuộc | Thiếu predecessor | Hoãn/đợi hoặc xử lý theo contract |

Kết quả mong muốn không phải “mạng không bao giờ gửi trùng”; mà là **mọi lần gửi trùng được hấp thụ để business state vẫn đúng**.

## 27. Các phản ví dụ cần tránh

**“Đã dùng Kafka consumer group thì khỏi cần Inbox.”** Offset không atomic với business DB transaction theo mặc định; crash sau commit vẫn tạo redelivery.

**“Check SELECT trước, không thấy thì INSERT.”** Hai worker có thể cùng thấy chưa có và chạy song song. Dùng unique constraint/transaction và invariant nghiệp vụ.

**“Chỉ cần giữ eventId 24 giờ.”** Replay/DLQ redrive sau 10 ngày có thể khiến event bị áp dụng lại. TTL phải gắn với nguy cơ duplicate và business safeguard.

**“Đã insert Inbox thì ACK ngay.”** Nếu chỉ có processed-message ledger mà domain change chưa commit, ACK sớm có thể làm mất hiệu ứng. Với durable receiver inbox, chỉ ACK sau khi **bản Inbox đã commit bền** và worker recovery đáng tin.

**“Cứ thêm @Transactional là hai database và HTTP API cùng atomic.”** Local transaction chỉ bảo vệ resource được enlist phù hợp. External API không tự rollback.

**“Inbox bảo đảm gửi đúng một email.”** DB marker không biết Email Provider đã chấp nhận request khi response bị mất. Cần provider idempotency, trạng thái và đối soát.

**“EventId luôn duy nhất cho business operation.”** Hai event ID khác nhau có thể phản ánh cùng thao tác. Cần khóa nghiệp vụ độc lập.

**“Dedupe giúp giải quyết event out-of-order.”** Duplicate và ordering là hai bài toán riêng.

**“Bất kỳ event cũ cũng có thể replay.”** Handler mang side effect có thể kích hoạt hành vi không còn hợp lệ. Cần quy trình phân biệt projection rebuild và workflow re-execution.

**“Xóa Inbox càng nhanh càng tốt để tiết kiệm storage.”** Có thể phá khả năng chống trùng trong cửa sổ replay còn tồn tại.

**“Nếu worker giữ lease thì không thể có worker khác chạy cùng lúc.”** Pause/partition khiến lease hết, worker cũ vẫn sống; cần fencing/idempotency.

## 28. Quy trình đưa Inbox vào hệ thống cũ

Không nhất thiết sửa mọi consumer trong một đợt.

### Bước 1: chọn luồng có hậu quả rõ ràng

Ví dụ OrderPaid → FulfillmentIntent hoặc CustomerRegistered → WelcomeNotification. Ưu tiên luồng có duplicate thực tế, có thể xác định business key và có owner vận hành.

### Bước 2: ghi nhận delivery contract

- Broker/queue nào?
- Message được ACK/commit offset khi nào?
- Retry và DLQ được cấu hình ra sao?
- Event ID có ổn định qua redelivery/replay không?
- Có consumer chạy song song, rebalances hoặc out-of-order không?

### Bước 3: xác định hiệu ứng cần bảo vệ

Ghi rõ business operation ID, invariant và dữ liệu cần cập nhật. Nếu gọi hệ thống ngoài DB, thiết kế outbox/intent và idempotency của provider.

### Bước 4: chọn biến thể Inbox

- Handler ngắn, chỉ cập nhật DB local: **transactional ledger**.
- Cần tách thời gian nhận và xử lý, payload có thể lưu bền, workflow nhiều bước: **durable receiver inbox**.

### Bước 5: thiết kế schema và transaction

Thêm unique key đúng phạm vi, migration, index, retention, quyền và metric. Đảm bảo marker và business state chung transaction khi chọn biến thể ledger.

### Bước 6: thay ACK policy

Chỉ ACK khi đã đạt điểm durable được mô tả. Với manual ACK, kiểm tra hành vi listener container, concurrency và offset commit thực tế.

### Bước 7: thử nghiệm lỗi

Mô phỏng crash ngay trước/sau COMMIT và trước ACK; hai worker đồng thời; event trùng khác payload; retry/DLQ; timeout sau external provider accepted.

### Bước 8: rollout có quan sát

Theo dõi duplicate suppression, backlog, handler latency, DB load, DLQ và business mismatch. Bật từng nhóm consumer với rollback plan về code/traffic, nhưng **không xóa ledger bừa** khi rollback.

### Bước 9: viết runbook

Runbook gồm cách truy vết eventId, tái xử lý, sửa ledger, cách ly poison event, đối soát business effect và người có quyền redrive.

### Bước 10: xem lại retention theo số liệu

So sánh độ dài broker retention, DLQ, archive, replay và sự cố thực tế. Điều chỉnh partition/retention theo bảo đảm đã cam kết thay vì chỉ dung lượng đĩa.

## 29. Mẫu tài liệu hợp đồng Inbox

~~~markdown
# Inbox Processing Contract: <consumer-name>

## Mục đích
- Event type / producer:
- Business effect được bảo vệ:
- Consumer owner / on-call:

## Message identity
- eventId / messageId:
- businessOperationId:
- aggregateId / aggregateVersion:
- Producer có giữ ID ổn định khi retry không:
- Schema version / compatibility:

## Ranh giới transaction
- Local DB và bảng Inbox:
- Unique key:
- Domain tables / outbox được ghi cùng transaction:
- ACK/offset được thực hiện sau bước nào:
- Các external side effects và idempotency:

## Delivery / ordering
- Broker / consumer group / partition key:
- Delivery semantics:
- Concurrency:
- Ordering/gap policy:
- Retry / backoff / DLQ:
- Manual redrive permissions:

## Retention / replay
- Broker retention:
- Inbox/dedup retention:
- Archive / snapshot:
- Projection rebuild namespace:
- Cách tránh duplicate external effect:
- Privacy/deletion policy:

## Observability / recovery
- Metric và dashboard:
- Tracing fields:
- Poison messages và incident runbook:
- Crash/rebalance tests:
- Reconciliation và cutoff:
- Review date / owner:
~~~

Mẫu trên nên nằm gần contract event và code consumer. Khi đổi cách ACK, đổi khóa dedup hay giảm retention, phải cập nhật cùng deployment và kiểm thử hồi quy.

## 30. Bài tập thực hành

### Bài 1: xử lý duplicate cơ bản

Một consumer nhận **InventoryReserved(eventId=evt-10, orderId=ord-7)**. Handler tạo một shipment request rồi ACK. Sau khi tạo shipment request, consumer crash trước ACK. Broker redeliver evt-10.

Hãy:

1. Vẽ lại failure window.
2. Viết bảng Inbox cần có và unique key.
3. Xác định transaction boundary.
4. Giải thích ACK đặt ở đâu và vì sao.
5. Nêu business constraint bổ sung nếu producer gửi event mới **evt-11** nhưng vẫn đại diện cho cùng reservation.

**Gợi ý:** không chỉ chặn evt-10, còn cần nhận diện cùng **fulfillment intent** theo nghiệp vụ.

### Bài 2: phân biệt processed-message ledger và durable receiver inbox

Consumer nhận 50.000 event/phút, handler gọi một API chậm khoảng vài giây. Đội kỹ thuật muốn ACK broker nhanh để tránh lag rồi đưa event vào PostgreSQL xử lý sau.

Hãy thiết kế:

- Schema Inbox gồm trạng thái và lease.
- Thời điểm ACK.
- Cách worker claim và phục hồi khi crash.
- Cách tránh hai worker xử lý trùng khi lease hết.
- Cơ chế không tạo side effect đôi khi external API đã xử lý nhưng mất response.
- Ba metric để phát hiện backlog/rủi ro.

**Gợi ý:** ACK sau khi lưu Inbox bền là hợp lệ trong mô hình durable receiver; nhưng còn phải thiết kế worker retry và idempotency sau ACK.

### Bài 3: tìm lỗi trong Java pseudocode

~~~java
public void onMessage(OrderPaid event) {
    if (!inbox.exists(event.eventId())) {
        emailClient.sendConfirmation(event.orderId());
        inbox.insert(event.eventId());
    }
    ack();
}
~~~

Hãy chỉ ra ít nhất sáu lỗi/rủi ro, bao gồm:

- Check-then-act race.
- External API không cùng transaction.
- Email đã gửi nhưng chưa insert Inbox.
- ACK khi xử lý chưa durable.
- Thiếu business operation ID.
- Không có retry/DLQ/reconciliation policy.

Viết lại thành sơ đồ durable notification intent + outbox + provider idempotency nếu có.

### Bài 4: sự kiện out-of-order

Event cùng order:

~~~text
v1: CREATED
v2: PAID
v3: CANCELLED
~~~

Consumer nhận **v3 trước v2**. Hãy giải thích khi nào có thể dùng “ghi version lớn nhất”, khi nào phải chờ v2, và vì sao Inbox theo eventId không trả lời được câu hỏi này.

### Bài 5: retention và replay

Broker giữ event 30 ngày; Inbox giữ 7 ngày; DLQ có thể redrive sau 20 ngày. Consumer Notification đã gửi email ở ngày 1. Ngày 20, operator redrive một event cũ.

Hãy đề xuất:

1. Lỗi có thể xảy ra nếu chỉ dựa vào Inbox.
2. Cách chọn dedup horizon hoặc business notification intent key.
3. Cách bảo vệ privacy khi giữ ledger dài.
4. Runbook trước khi redrive.
5. Cách kiểm thử trước khi thay TTL.

## 31. Checklist trước khi production

- [ ] Event có ID ổn định và business key khi cần.
- [ ] Consumer identity/namespace được định nghĩa đúng phạm vi hiệu ứng.
- [ ] Có unique constraint của DB để phân xử concurrency, không chỉ check-then-insert.
- [ ] Marker ledger và domain change nằm trong cùng local transaction nếu dùng biến thể A.
- [ ] Nếu ACK sau lưu vào durable Inbox, worker recovery/retry đã được thiết kế đầy đủ.
- [ ] ACK/offset không được tiến trước điểm durability đã công bố.
- [ ] Crash trước/sau COMMIT và trước ACK đã được kiểm thử.
- [ ] Có kiểm tra same ID/different payload khi cần.
- [ ] Business invariant chống duplicate khác eventId.
- [ ] Có chính sách ordering, aggregate version và gap.
- [ ] External side effect có intent/outbox/idempotency hoặc đối soát.
- [ ] Worker lease có đường phục hồi và fencing/idempotency phù hợp.
- [ ] Retry/DLQ phân biệt transient và permanent failure.
- [ ] Không mark COMPLETED khi event chưa áp dụng đúng phần hiệu ứng đã cam kết.
- [ ] Retention ledger phù hợp replay/DLQ/archive và bảo đảm nghiệp vụ.
- [ ] Có kế hoạch projection rebuild tách khỏi việc gửi tác dụng phụ.
- [ ] Dữ liệu nhạy cảm, backup và deletion được kiểm soát.
- [ ] Có metric duplicate suppression, backlog, age, mismatch và incident.
- [ ] Có owner/runbook cho manual redrive và reconciliation.
- [ ] Đã đo chi phí DB/index và áp backpressure ở tải thật.

## 32. Ghi nhớ

**Inbox là điểm ghi nhận bền vững ở phía nhận để biến việc giao message có thể lặp thành xử lý nghiệp vụ có thể kiểm soát.** Với transactional ledger, marker chống trùng và thay đổi domain được commit trong cùng một local transaction, sau đó mới ACK broker. Với durable receiver inbox, message được lưu bền và ACK trước, rồi worker xử lý qua trạng thái/retry riêng.

Inbox **không** tự bảo đảm exactly-once delivery, không tự giải quyết ordering, không ngăn hai event khác ID đại diện cùng thao tác và không atomically bảo vệ external HTTP side effects. Để có luồng sự kiện đáng tin cậy, hãy kết hợp **event identity, unique business constraints, Outbox, idempotent consumers, checkpoint đúng, retention, DLQ, observability và reconciliation**. Thiết kế tốt không cố loại bỏ mọi lần giao trùng, mà bảo đảm **giao trùng không làm thay đổi sai kết quả nghiệp vụ**.
