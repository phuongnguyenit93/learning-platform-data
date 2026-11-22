# Queue và delivery trong logging của ứng dụng xử lý message (Java)

## 1. Queue và delivery có nghĩa gì khi ứng dụng dùng message broker?

Ứng dụng hướng message trao đổi công việc qua một **queue/topic** thay vì gọi trực tiếp tất cả thành phần theo kiểu request–response. Producer tạo message; broker giữ và phân phối; consumer nhận message, thực thi nghiệp vụ rồi phản hồi theo giao thức. Logging giúp theo dõi từng giai đoạn, nhưng **một dòng log không tự bảo đảm message đã đến nơi hoặc xử lý thành công**.

Ví dụ:

```text
Order API (producer)
   |
   | send event OrderCreated
   v
Broker queue / topic
   |
   | deliver
   v
Payment Worker (consumer)
   |
   +-- process payment
   |
   +-- ACK / NACK / commit offset / retry / DLQ
   |
   v
Order service / database / downstream

Tại từng bước: application log -> appender -> agent -> collector
                                 (pipeline log riêng)
```

Có **hai hệ thống queue/delivery** cần phân biệt:

1. **Delivery của business message:** broker giao thông điệp cho consumer; quyết định ACK, redelivery, retry, DLQ và độ bền của dữ liệu nghiệp vụ.
2. **Delivery của bản ghi log:** backend logging có thể enqueue event vào async appender; sink có thể đang lỗi hoặc collector chậm. Message đã ACK với broker **không có nghĩa audit log của việc xử lý đã được lưu**.

Ví dụ `logger.info("Processed order {}", id)` không biến thao tác xử lý thành transaction; việc gọi logger có thể bị lọc bởi level, event có thể nằm trong queue chưa drain, hoặc collector có thể không nhận được.

Mục tiêu học tập: nhận diện các trạng thái message và thời điểm có thể ghi log chính xác, lựa chọn hợp đồng ACK/retry phù hợp, liên kết log của nhiều lần giao cùng một message, tránh duplicate side effect, rồi kiểm chứng bằng test/fault injection.

## 2. Thuật ngữ nền tảng

| Thuật ngữ | Ý nghĩa | Lưu ý khi ghi log |
| --- | --- | --- |
| **Producer** | Thành phần gửi business message | Ghi yêu cầu gửi và kết quả broker xác nhận riêng |
| **Broker** | Hệ thống nhận/lưu/chuyển message | Sức chứa, replication, retention và ack tùy công nghệ |
| **Queue** | Kênh công việc có consumer nhận giao | Không phải mọi broker đều triển khai queue giống nhau |
| **Topic/partition** | Kênh phát message có thể phân vùng | Kafka dùng offset trong mỗi partition |
| **Consumer** | Thành phần nhận và xử lý message | Cần ghi nhận attempt, outcome, duration |
| **Delivery** | Một lần broker chuyển/cho consumer đọc message | Một message có thể được giao nhiều lần |
| **ACK** | Tín hiệu xác nhận đã nhận/xử lý theo hợp đồng | ACK broker ≠ audit/log durability |
| **NACK/reject** | Không chấp nhận lần giao hiện tại | Có thể requeue, retry hoặc DLQ tùy broker |
| **Offset commit** | Consumer ghi nhận vị trí đã xử lý trong partition | Không phải xóa message khỏi topic |
| **Retry** | Thử xử lý lại sau lỗi | Dễ có duplicate effect nếu thiếu idempotency |
| **Redelivery** | Broker giao lại cùng message logic | Có thể sau crash, timeout, reject/requeue |
| **DLQ / dead-letter** | Nơi cô lập message không xử lý theo chính sách | Không đồng nghĩa lỗi được giải quyết |
| **Backpressure** | Cơ chế điều tiết producer/consumer khi quá tải | Buffer hữu hạn vẫn cần xử lý khi đầy |
| **Idempotency** | Thực thi lặp cùng operation không tạo tác dụng phụ ngoài ý muốn | Phải dựa vào dữ liệu bền vững khi production |
| **Correlation ID** | Liên kết log qua nhiều service/attempt | Không nên dùng token/PII làm ID |

Không phải giao thức nào cũng có nút ACK và NACK như nhau. RabbitMQ AMQP hỗ trợ consumer acknowledgments; Kafka thường theo dõi **offset/position** và có cơ chế commit. Các lựa chọn cụ thể phải được hiểu theo backend và client library đang sử dụng.

## 3. Vòng đời của một message và các điểm có thể ghi log

Một quy trình có thể tách thành các mốc:

```text
Producer:
  CREATED -> SEND_ATTEMPTED -> BROKER_CONFIRMED / SEND_FAILED
                                      |
                                      v
Consumer:
  DELIVERED -> PROCESSING -> BUSINESS_COMMITTED
                                      |
                             ACK/COMMIT_ATTEMPTED
                                      |
                            ACK_CONFIRMED/UNCERTAIN
         \-> RETRY_SCHEDULED / REQUEUED / DEAD_LETTERED
```

Đây là **mô hình quan sát khái niệm**, không phải state machine tự động có sẵn của mọi broker. Tên event log phải biểu thị việc **đã xác nhận được**, tránh thông điệp mơ hồ như `message success`.

### Producer: gửi không đồng nghĩa broker đã lưu

Một producer có thể:

1. Tạo message và ID.
2. Gọi API gửi bất đồng bộ.
3. Nhận callback/future xác nhận hoặc lỗi.
4. Ghi log với trạng thái đúng mốc.

`SEND_ATTEMPTED` mô tả có yêu cầu gửi. `BROKER_CONFIRMED` chỉ nên xuất hiện sau tín hiệu xác nhận theo contract broker. Nếu kết nối lỗi **sau khi broker nhận nhưng trước khi callback về**, producer có thể không biết message đã tới hay chưa: không mặc nhiên khẳng định `SEND_FAILED` đồng nghĩa message chưa tồn tại; cần retry với key/idempotency phù hợp.

### Consumer: nhận chưa phải đã xử lý

`DELIVERED` (hoặc `RECEIVED`) nghĩa là consumer nhìn thấy message. Nó **không** đồng nghĩa đã ghi thành công vào database hoặc gửi email. `BUSINESS_COMMITTED` chỉ nên ghi sau khi có bằng chứng side effect đã đạt mốc hợp đồng. Khi đã xong nghiệp vụ, consumer mới quyết định ACK/commit offset theo chính sách.

### ACK có thể mơ hồ

Consumer có thể xử lý và commit database thành công, gửi ACK, rồi mất kết nối trước khi biết broker nhận ACK chưa. Broker có thể giao lại cùng message. Do đó:

- `ACK_ATTEMPTED` là sự kiện **consumer đã thử xác nhận**.
- `ACK_CONFIRMED` chỉ dùng khi client/protocol có tín hiệu đủ để xác minh.
- `ACK_UNCERTAIN` có ý nghĩa khi mất kết nối hoặc kết quả không rõ.
- Một lần nhận lại không tự chứng minh consumer đã rollback lần trước.

Ghi log theo **ranh giới đã xác minh**, không phải cảm giác “thường là thành công”.

## 4. Các bảo đảm delivery: at-most-once, at-least-once, exactly-once

| Mô hình | Ý tưởng | Hệ quả | Dùng trong thực tế |
| --- | --- | --- | --- |
| **At-most-once** | Không thử giao lại sau một điểm xác nhận sớm hoặc không giữ lại message khi lỗi | Ít duplicate, có thể mất công việc | Telemetry ít quan trọng hoặc yêu cầu chấp nhận mất |
| **At-least-once** | Message còn khả năng giao lại cho tới khi đạt ack/commit phù hợp | Có thể xử lý lặp | Worker nghiệp vụ phổ biến, cần idempotency |
| **Exactly-once** | Không tạo tác dụng quan sát được lặp trong một phạm vi cụ thể | Thường cần transaction, dedup/idempotency và thiết kế kỹ | Khả năng đặc thù của broker/pipeline |

**Không dùng “exactly once” như cam kết chung cho cả ứng dụng.** Kafka có các cơ chế giao dịch/idempotent producer và xử lý chính xác một lần trong những phạm vi Kafka hỗ trợ, nhưng cập nhật database, gửi email hoặc gọi cổng thanh toán bên ngoài **không tự nằm trong cùng transaction Kafka**. Ở phía RabbitMQ, delivery ACK cũng không tạo exactly-once cho side effect nghiệp vụ.

### ACK trước hay sau nghiệp vụ?

Giả sử một message yêu cầu cập nhật số dư:

```text
Phương án A:
  ACK/commit progress -> cập nhật DB
  Crash giữa hai bước -> tiến độ đã tiến nhưng DB chưa cập nhật
  => nguy cơ mất thao tác.

Phương án B:
  cập nhật DB -> ACK/commit progress
  Crash giữa hai bước -> DB đã cập nhật, broker có thể giao lại
  => nguy cơ thao tác trùng.
```

Để có khả năng chịu lỗi thường dùng **xử lý nghiệp vụ trước, rồi ACK**, kết hợp consumer idempotent; nhưng việc ACK muộn không đủ nếu side effect không có cách chống trùng.

### At-least-once không có nghĩa mọi lần thử đều kết thúc thành công

Retry có thể gặp lỗi thường trực, backlog có thể đầy, TTL có thể hết, message có thể bị DLQ hoặc vượt giới hạn retry. Delivery guarantee chỉ có ý nghĩa trong **phạm vi và giả định** của hạ tầng: retention, độ bền, cấu hình ack, mất mạng, crash và chính sách dừng.

## 5. Ghi log theo từng lần giao và theo logical message

Một message logic cần được phân biệt với các delivery attempts của nó.

| Trường | Công dụng | Quy tắc |
| --- | --- | --- |
| `messageId` | ID của business message | Giữ qua các lần redelivery của cùng message |
| `operationId` | Hành động nghiệp vụ mà message phục vụ | Dùng liên kết nhiều message của cùng workflow |
| `correlationId` | Truy theo request/tracing | Kiểm soát nguồn/độ dài, không dùng secret |
| `deliveryAttempt` | Số lần giao/thử xử lý | Tăng có căn cứ; broker có thể không cung cấp sẵn số đếm tuyệt đối |
| `consumerGroup` / `consumerName` | Ai nhận message | Chỉ dùng tên định danh kỹ thuật cần thiết |
| `topic` / `queue` | Nơi message đến | Không copy tên/giá trị không tin cậy vào schema không escape |
| `partition` / `offset` | Vị trí trong Kafka | Có ý nghĩa trong phạm vi topic-partition |
| `deliveryTag` | Định danh giao của AMQP channel | Không xem là message ID toàn hệ thống |
| `eventType` | `MESSAGE_RECEIVED`, `PROCESSING_FINISHED`... | Diễn đạt mốc trong lifecycle |
| `outcome` | `SUCCEEDED`, `FAILED`, `RETRY_SCHEDULED`... | Kết quả của mốc đã xác minh |
| `durationMs` | Thời gian một attempt | Không tính chung cả các lần retry nếu chưa định nghĩa |
| `reasonCode` | Mã phân loại lỗi an toàn | Tránh raw exception message chứa dữ liệu nhạy cảm |

Ví dụ:

```json
{
  "schemaVersion": 1,
  "eventId": "log-201",
  "timestamp": "2026-01-01T10:00:00Z",
  "service": "payment-worker",
  "eventType": "MESSAGE_PROCESSING_FINISHED",
  "messageId": "msg-73",
  "operationId": "order-19",
  "queue": "payments",
  "deliveryAttempt": 2,
  "outcome": "SUCCEEDED",
  "durationMs": 24
}
```

Đây là event minh họa, không phải schema của RabbitMQ/Kafka hay một log đã chạy thật. `eventId` ở ví dụ có thể là ID của event log/telemetry; không nên thay thế `messageId` bằng `eventId` nếu muốn biết **hai lần xử lý cùng business message**.

### Tên event nên phản ánh kết quả đo được

| Log event | Điều người đọc có thể kết luận |
| --- | --- |
| `MESSAGE_RECEIVED` | Consumer đã nhận/đọc lần giao |
| `PROCESSING_STARTED` | Đã bắt đầu attempt |
| `BUSINESS_EFFECT_COMMITTED` | Side effect đã đạt mốc đã định nghĩa |
| `ACK_REQUESTED` | Ứng dụng đã gọi xác nhận/commit |
| `ACK_CONFIRMED` | Có tín hiệu xác nhận nếu protocol/API hỗ trợ |
| `REDELIVERY_OBSERVED` | Cùng message logic được nhận lại |
| `RETRY_SCHEDULED` | Có cơ chế lưu lịch retry được xác nhận |
| `DEAD_LETTERED` | Message đã được chuyển đến DLQ theo hợp đồng |
| `PROCESSING_FAILED` | Attempt xử lý lỗi; không tự nói kết quả operation cuối |

Tránh log `ACK_SUCCESS` nếu API chỉ enqueue một lệnh ACK chưa có xác nhận. Với Kafka, không nên coi `commitAsync` được gọi là offset commit thành công trước khi callback cho kết quả.

## 6. Retry, redelivery và poison message

**Transient error** có thể là timeout mạng ngắn, dependency quá tải hoặc sự cố kết nối có thể phục hồi. **Permanent/business error** có thể là schema không hợp lệ, thiếu trường bắt buộc hoặc một loại message mà consumer không hỗ trợ. Chính sách cần phân biệt, tránh retry một lỗi không thể giải quyết.

Một quy trình khái niệm:

```text
PROCESS
  |
  +-- Success ------------------------> ACK
  |
  +-- Retryable error -- attempts left -> retry with backoff
  |
  +-- Invalid / attempts exhausted ---> DLQ + alert
  |
  +-- Result unknown -----------------> reconcile/idempotency check
```

### Phân loại lỗi

| Loại lỗi | Hành động gợi ý | Nội dung log |
| --- | --- | --- |
| Timeout tạm thời | Retry có delay/backoff và jitter | `RETRY_SCHEDULED`, attempt, next delay |
| Rate limit | Tôn trọng retry-after khi có, giới hạn concurrency | `RATE_LIMITED`, source, thời điểm thử tiếp |
| Schema không hợp lệ | Reject hoặc DLQ theo chính sách | `REJECTED`, mã lỗi không nhạy cảm |
| Credential/cấu hình sai | Alert, tạm ngừng hoặc DLQ; không retry nóng vô hạn | `CONFIGURATION_FAILURE`, service liên quan |
| Nghi ngờ đã commit | Query/idempotency/reconcile trước khi lặp side effect | `RESULT_UNCERTAIN` |
| Nhiều lần thất bại | Chuyển DLQ hoặc cách ly | `RETRY_EXHAUSTED`, số lần, DLQ id |

**Không dùng một vòng `while(true)` retry không giới hạn.** Backoff, jitter, retry budget và dead-letter policy bảo vệ broker/consumer khi downstream lỗi. Nếu requeue tức thì vào đầu queue, cùng poison message có thể chạy liên tục và ngăn những message khỏe mạnh được xử lý.

### Dead-letter queue không tự chữa lỗi

DLQ lưu message chưa thể xử lý theo chính sách, nhưng vẫn cần:
- Quyền đọc/ghi rõ ràng, retention đủ để điều tra và tránh tràn dung lượng.
- Alert số lượng/tốc độ message đi vào DLQ.
- Công cụ xem metadata và reason code an toàn, không phơi bày raw payload nhạy cảm trên dashboard.
- Quy trình sửa nguyên nhân gốc và **re-drive** sau kiểm tra tương thích schema, tránh lặp vô hạn.
- Cơ chế giữ message ID/correlation ID và ghi event `REPLAY_REQUESTED`/`REPLAY_COMPLETED` khi cần.
- Kiểm tra có thể xử lý trùng sau khi replay; DLQ không loại bỏ yêu cầu idempotency.

Không giả định mọi broker tự động DLQ sau 3 lần: cần cấu hình counter, policy, queue binding/dead-letter exchange hoặc middleware phù hợp.

## 7. Java 17 chạy độc lập: redelivery, mất ACK, idempotency và DLQ

Ví dụ này **mô phỏng một broker trong bộ nhớ**, không dùng RabbitMQ hoặc Kafka thật. Nó cố tình cho message `m1` xử lý thành công nhưng ACK không được ghi nhận, nên message được giao lại; consumer có bộ nhớ ID đã xử lý để không áp dụng side effect hai lần. Message `m2` luôn gặp lỗi và được đưa vào DLQ sau ba lần thử.

Ví dụ cho thấy **đường đi trạng thái** và cách tạo log phân biệt, không khẳng định memory queue/set cung cấp độ bền hay exactly-once.

### 7.1. Mã nguồn `QueueDeliveryDemo.java`

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

public class QueueDeliveryDemo {
    record Message(String id, String body) {}
    record Delivery(Message message, int attempt) {}

    static final class FakeBroker {
        private final Deque<Delivery> queue = new ArrayDeque<>();
        private final List<Delivery> dlq = new ArrayList<>();

        void publish(String id, String body) {
            queue.addLast(new Delivery(new Message(id, body), 1));
            System.out.println("PUBLISHED id=" + id);
        }

        Delivery next() {
            return queue.pollFirst();
        }

        void ack(Delivery delivery) {
            System.out.println("ACK id=" + delivery.message().id());
        }

        void redeliverAfterLostAck(Delivery delivery) {
            int nextAttempt = delivery.attempt() + 1;
            queue.addLast(new Delivery(delivery.message(), nextAttempt));
            System.out.println("REDELIVERED id="
                    + delivery.message().id()
                    + " attempt=" + nextAttempt);
        }

        void nackRetryOrDlq(Delivery delivery, int maxAttempts) {
            String id = delivery.message().id();

            if (delivery.attempt() >= maxAttempts) {
                dlq.add(delivery);
                System.out.println("DLQ id=" + id
                        + " attempts=" + delivery.attempt());
            } else {
                int nextAttempt = delivery.attempt() + 1;
                queue.addLast(new Delivery(
                        delivery.message(), nextAttempt));
                System.out.println("REQUEUED id=" + id
                        + " attempt=" + nextAttempt);
            }
        }

        int pendingCount() {
            return queue.size();
        }

        int dlqCount() {
            return dlq.size();
        }
    }

    static final class Consumer {
        private final Set<String> applied = new HashSet<>();

        void handle(Delivery delivery, FakeBroker broker) {
            String id = delivery.message().id();
            int attempt = delivery.attempt();

            if (applied.contains(id)) {
                System.out.println("DEDUP id=" + id
                        + " attempt=" + attempt);
                broker.ack(delivery);
                return;
            }

            if ("m2".equals(id)) {
                System.out.println("FAILED id=" + id
                        + " attempt=" + attempt);
                broker.nackRetryOrDlq(delivery, 3);
                return;
            }

            // Mô phỏng business effect đã được áp dụng.
            applied.add(id);
            System.out.println("APPLIED id=" + id
                    + " attempt=" + attempt);

            if ("m1".equals(id) && attempt == 1) {
                // Cố ý mô phỏng ACK không được broker ghi nhận.
                System.out.println("ACK_LOST id=" + id);
                broker.redeliverAfterLostAck(delivery);
            } else {
                broker.ack(delivery);
            }
        }

        int appliedCount() {
            return applied.size();
        }
    }

    public static void main(String[] args) {
        FakeBroker broker = new FakeBroker();
        Consumer consumer = new Consumer();

        broker.publish("m1", "valid");
        broker.publish("m2", "always-fails");

        Delivery delivery;
        while ((delivery = broker.next()) != null) {
            consumer.handle(delivery, broker);
        }

        System.out.println("applied=" + consumer.appliedCount());
        System.out.println("dlq=" + broker.dlqCount());
        System.out.println("pending=" + broker.pendingCount());
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac QueueDeliveryDemo.java
java QueueDeliveryDemo
```

**Stdout chính xác** khi chạy riêng ví dụ này:

```text
PUBLISHED id=m1
PUBLISHED id=m2
APPLIED id=m1 attempt=1
ACK_LOST id=m1
REDELIVERED id=m1 attempt=2
FAILED id=m2 attempt=1
REQUEUED id=m2 attempt=2
DEDUP id=m1 attempt=2
ACK id=m1
FAILED id=m2 attempt=2
REQUEUED id=m2 attempt=3
FAILED id=m2 attempt=3
DLQ id=m2 attempts=3
applied=1
dlq=1
pending=0
```

### 7.2. Giải thích từng trạng thái

1. `PUBLISHED`: broker giả đã đưa cả hai message vào deque. Đây là **ghi nhận trong bộ nhớ**, không phải xác nhận disk/replication.
2. Consumer nhận `m1`, áp dụng business effect một lần rồi mô phỏng ACK thất lạc. Broker sắp xếp lại `m1` với `attempt=2`.
3. `m2` luôn lỗi ở attempt đầu; broker giả đưa message lại cuối queue, không làm mất event.
4. Khi `m1` được giao lần hai, tập `applied` đã có ID nên consumer ghi `DEDUP` và ACK, không áp dụng side effect thêm.
5. `m2` lỗi ở attempt 2, thử lần 3 rồi vào DLQ. Log `DLQ` là bằng chứng logic trong ví dụ đã di chuyển vào danh sách DLQ trong bộ nhớ.
6. Kết quả `applied=1`, `dlq=1` và `pending=0` phản ánh trạng thái hai collection giả. Không khẳng định ứng dụng/broker production sẽ có đúng thứ tự hay guarantee này.

### 7.3. Những điều ví dụ cố ý chưa giải quyết

- `HashSet` chống trùng **chỉ khi cùng process còn sống**; restart là mất dữ liệu.
- Việc `applied.add(id)` và hiệu lực nghiệp vụ chưa gắn trong transaction bền vững. Trong production, phải thiết kế update + dấu ID đã xử lý nguyên tử hoặc có cơ chế idempotency riêng.
- `FakeBroker` không có persistence, replication, ack protocol, timeout, nhiều consumer, concurrency hay partition.
- Loop retry trong ví dụ không có delay để stdout dễ xác minh. Production phải có backoff và giới hạn tải.
- Message body không được ghi ra console vì có thể chứa nội dung khách hàng/secret; ví dụ chỉ log ID, attempt và trạng thái.
- **Mất ACK** được mô phỏng có chủ đích: việc gọi `redeliverAfterLostAck` sau khi consumer thực thi không phải API mặc định có sẵn trong RabbitMQ/Kafka.

Ví dụ này phù hợp để học về lifecycle và kiểm thử quyết định, nhưng không thay thế integration test với broker và database thật.

## 8. Consumer idempotent: chống trùng phải đi kèm nghiệp vụ

Một thuật toán thường dùng:

```text
Nhận message với messageId
   |
   v
Bắt đầu transaction DB
   |
   +-- messageId đã xử lý? -> không làm lại effect
   |                           -> commit -> ACK
   |
   v
Kiểm tra điều kiện nghiệp vụ
   |
   v
Thực thi mutation + lưu dấu messageId đã xử lý
   |
   v
Commit transaction DB
   |
   v
ACK broker theo contract
```

Trong SQL, bảng dấu đã xử lý có thể có khóa duy nhất `(consumerName, messageId)`, hoặc dùng business key/idempotency key trong chính bảng nghiệp vụ. Khi nhiều consumer nhận cùng ID đồng thời, unique constraint/transaction đảm bảo hai lần không cùng áp dụng hiệu lực **nếu toàn bộ thao tác liên quan nằm trong cùng transaction**.

Pseudocode minh họa, không phải SQL script hoàn chỉnh cho mọi RDBMS:

```sql
BEGIN;

-- INSERT dấu messageId, nếu conflict thì xác định đã xử lý.
INSERT INTO processed_messages (consumer_name, message_id)
VALUES ('payment-worker', 'm1');

-- Chỉ khi insert mới thành công mới áp dụng side effect.
UPDATE orders
SET status = 'PAID'
WHERE id = 'order-19' AND status = 'PENDING';

COMMIT;
```

Phải kiểm tra kết quả `INSERT` và `UPDATE`, lock/isolation và mã lỗi unique-key theo DB được dùng. Nếu transaction rollback, cả dấu processed và mutation phải rollback. **Không ghi `SUCCESS` chỉ vì lệnh UPDATE không ném exception nhưng cập nhật 0 hàng.**

### Side effect bên ngoài transaction DB

Gửi email hoặc gọi cổng thanh toán không tự tham gia transaction của bảng `processed_messages`. Nếu email đã gửi thành công rồi process crash trước commit dấu processed, consumer redeliver có thể gửi lại email. Khi ấy cần:

- Idempotency key được hệ thống bên ngoài hỗ trợ; hoặc
- Transactional outbox cho lệnh gửi ra ngoài, kết hợp consumer downstream idempotent; hoặc
- Quy trình đối soát/trạng thái `UNKNOWN` khi kết quả remote không chắc.

Một transaction trong local database **không bảo đảm exactly-once cho mọi side effect bên ngoài**.

## 9. Transaction outbox và inbox cho hệ thống message

### Producer outbox

Một rủi ro ở phía producer:

```text
COMMIT order database
    |
    v
send OrderCreated tới broker
    X Process crash
=> Có order nhưng message chưa được phát.
```

Mẫu **transactional outbox** lưu thay đổi nghiệp vụ và bản ghi chờ publish trong cùng transaction database, sau đó dispatcher gửi outbox tới broker và đánh dấu đã giao theo ack policy.

```text
DB transaction:
  update order
  insert outbox(eventId, payload, status=PENDING)
  COMMIT
       |
       v
Dispatcher -> Broker (retry if needed)
       |
       v
Broker confirmation -> mark dispatched
```

Nếu broker đã nhận nhưng dispatcher mất response, cùng event có thể được gửi lại. Vì vậy consumer vẫn cần dedup/idempotency; outbox giải quyết một khoảng trống giữa DB commit và việc phát message, **không tự tạo exactly-once end-to-end**.

### Consumer inbox

Mẫu **inbox** lưu `messageId` đã xử lý theo khóa duy nhất cùng transaction side effect, để redelivery không thực hiện lại. Với workflow phức tạp có thể lưu trạng thái `RECEIVED/PROCESSING/COMPLETED/FAILED`, nhưng phải thiết kế lease/timeout và khôi phục process chết khi đang PROCESSING.

Mỗi trạng thái inbox có thể có log riêng, nhưng không coi `inbox.status=COMPLETED` là bằng chứng delivery log đã vào collector.

## 10. Áp dụng đúng với RabbitMQ

RabbitMQ (AMQP 0-9-1) có khái niệm **publisher confirms** và **consumer acknowledgments** — hai đường xác nhận khác nhau.

- Publisher confirm giúp producer biết broker đã chấp nhận publish theo ngữ nghĩa áp dụng. Nó **không** khẳng định consumer đã xử lý.
- Với manual consumer ack, consumer dùng `basicAck` khi hoàn tất công việc ở mốc đã chọn.
- `basicNack`/`basicReject` có thể từ chối một delivery; thuộc tính `requeue` ảnh hưởng khả năng đưa lại vào queue. Requeue tức thì khi consumer vẫn đang lỗi có thể tạo hot loop.
- `deliveryTag` chỉ có ý nghĩa trong phạm vi channel; không dùng nó làm message ID xuyên service.
- Khi connection/channel đóng trước khi ACK, message chưa ack thường có thể được redeliver theo cấu hình và trạng thái queue; không suy rằng luôn được giữ sau mọi kiểu lỗi hạ tầng.
- Prefetch (`basicQos`) giúp giới hạn số message đang unacked ở consumer, ảnh hưởng throughput/backpressure.

Đoạn minh họa **trong ứng dụng đã cấu hình RabbitMQ Java client**, không phải chương trình độc lập:

```java
long tag = delivery.getEnvelope().getDeliveryTag();
String messageId = delivery.getProperties().getMessageId();

try {
    processIdempotently(delivery.getBody(), messageId);
    channel.basicAck(tag, false);
    logger.info("message processed and ack attempted id={}", messageId);
} catch (TransientBusinessException e) {
    channel.basicNack(tag, false, true);
    logger.warn("message requeued id={}", messageId);
}
```

Đoạn code bỏ qua nhiều chi tiết thực tế: `delivery`/`channel`/`logger`/`processIdempotently` và loại exception là các thành phần ứng dụng; không thể biên dịch độc lập. `basicAck` thường gửi frame xác nhận; **việc API trả về không nhất thiết là broker đã ack bền vững** theo mọi tình huống kết nối. Trong thực tế cần xử lý channel/connection failure, lỗi thường trực, DLX/DLQ và policy retry tách biệt. Khi `basicNack` tự nó lỗi, log phải phản ánh ACK/NACK **không chắc**, không nói đã requeue chắc chắn.

### Message redelivered flag

Một số delivery có thể mang cờ `redeliver` từ broker, cho biết message từng được giao. Đây là tín hiệu hữu ích, nhưng **không dùng nó thay idempotency key** hoặc số lần thử bền vững. Một message có thể bị publish trùng với ID khác, hoặc broker không có đủ lịch sử để cung cấp attempt count mong muốn của ứng dụng.

## 11. Áp dụng đúng với Kafka

Kafka không có per-message ACK/NACK ở phía consumer giống RabbitMQ. Consumer đọc các record theo **topic-partition-offset** rồi lưu **committed offset** cho nhóm consumer để biết vị trí tiếp tục sau restart/rebalance.

- Offset trong mỗi partition định danh vị trí của record, không phải message ID toàn hệ thống.
- Auto-commit có thể không phù hợp khi xử lý cần side effect trước khi ghi nhận tiến độ. Manual commit giúp chủ động thứ tự xử lý–commit.
- Nếu side effect hoàn tất rồi consumer crash trước offset commit, record có thể được đọc lại. Consumer phải idempotent.
- Nếu commit offset trước side effect rồi crash, record có thể bị bỏ qua khi tiếp tục, gây mất tác vụ.
- Kafka thường commit **offset kế tiếp cần đọc**; khi record có offset `n` được xử lý thì vị trí commit biểu diễn `n+1` cho partition tương ứng.
- Rebalance có thể chuyển partition sang instance khác; phải quản lý in-flight tasks và quyền sở hữu partition cẩn thận.
- Một lỗi parse/validation thường trực có thể chặn tiến độ partition; dùng retry topic/DLQ/chính sách skip có kiểm soát, theo hợp đồng nghiệp vụ và kiểm toán.

Đoạn minh họa **trong Kafka consumer đã cấu hình và có biến `consumer`/`record`**, không độc lập:

```java
TopicPartition tp =
        new TopicPartition(record.topic(), record.partition());

try {
    processIdempotently(record.value(), record.key());
    consumer.commitSync(
        Map.of(tp, new OffsetAndMetadata(record.offset() + 1)));
    logger.info(
        "record processed; offset commit returned topic={} "
            + "partition={} offset={}",
        record.topic(), record.partition(), record.offset());
} catch (Exception e) {
    logger.warn(
        "processing or commit failed topic={} partition={} offset={}",
        record.topic(), record.partition(), record.offset());
    // Không tự tăng offset ở nhánh lỗi.
    // Phân loại lỗi và quyết định seek/retry/DLQ theo thiết kế.
}
```

Ví dụ không phù hợp để copy nguyên xi vào một loop poll nhiều records/partitions; trong batch cần quản lý khoảng offset liên tục đã xử lý và không commit qua record chưa thành công. `commitSync` có thể lỗi hoặc timeout; trạng thái offset commit đôi khi cần đối chiếu. Với rebalance, cần kiểm soát consumer thread ownership.

Kafka hỗ trợ idempotent producer và transaction cho một số luồng read-process-write vào Kafka, với điều kiện cấu hình consumer isolation level/transactions chính xác. **Không suy rằng transaction Kafka bao trùm database bên ngoài hoặc HTTP API.**

## 12. Logging đúng trong producer/consumer Java

### Tránh message tự do, chọn các trường có thể truy vấn

Trong hệ thống sử dụng SLF4J:

```java
logger.info(
    "message received id={} topic={} partition={} offset={} attempt={}",
    messageId, topic, partition, offset, attempt);

logger.info(
    "message processed id={} outcome={} durationMs={}",
    messageId, outcome, durationMs);

logger.warn(
    "message retry scheduled id={} reasonCode={} attempt={}",
    messageId, reasonCode, attempt);
```

Đây là code minh họa trong ứng dụng đã có các biến liên quan. Các lời gọi placeholder tạo **message text**, không tự động thành structured JSON. Với pipeline cần truy vấn field ổn định, dùng structured logging/JSON encoder phù hợp backend và kiểm tra output thực tế.

### Khi nào ghi ERROR, WARN, INFO?

Một chính sách gợi ý, không phải chuẩn bắt buộc:

- `DEBUG`: nhận message, chi tiết đường đi bình thường nếu số lượng lớn và không cần từng event.
- `INFO`: những mốc cần quan sát như processing completed, DLQ re-drive hoặc trạng thái nghiệp vụ theo yêu cầu.
- `WARN`: lỗi retryable, redelivery bất ngờ, offset commit chậm, backlog tăng.
- `ERROR`: message vượt retry budget, thất bại quan trọng, mất kết nối kéo dài, lỗi cấu hình hoặc sự kiện bắt buộc không được lưu.

Không dùng level để thay `outcome`. Một `DENIED` do chính sách nghiệp vụ có thể là kết quả bình thường và không nhất thiết là ERROR. Ngược lại, mất audit bắt buộc có thể là sự cố nghiêm trọng dù business message đã xử lý xong.

### Giữ correlation qua thread

MDC/ThreadContext có thể gắn `messageId`, `operationId` và `correlationId` vào log:

```java
// Ví dụ cho ứng dụng SLF4J: xử lý từng delivery trên một worker.
Map<String, String> before = MDC.getCopyOfContextMap();
try {
    MDC.put("messageId", validatedMessageId);
    MDC.put("operationId", validatedOperationId);
    processOneMessage();
} finally {
    if (before == null) {
        MDC.clear();
    } else {
        MDC.setContextMap(before);
    }
}
```

Đây là đoạn **không độc lập**, giả định đã import `java.util.Map` và `org.slf4j.MDC` và có các biến/phương thức thực tế. Điều kiện bảo mật: validate correlation IDs ở boundary, không chép token hoặc raw payload vào MDC. Khi dùng executor/reactive framework, MDC thường gắn với thread; cần truyền context theo cơ chế hỗ trợ của framework, không mặc định `CompletableFuture` tự sao chép.

Nếu handler không dọn MDC, worker thread tái sử dụng có thể ghi sai `messageId` của lần giao trước, khiến điều tra redelivery nhầm sang request khác.

## 13. Backpressure, consumer lag và queue sâu

Delivery không thể được bảo đảm nếu producer nhanh hơn consumer trong thời gian đủ dài mà hệ thống chỉ có tài nguyên hữu hạn.

Dấu hiệu vận hành thường gặp:

| Metric | Đọc thế nào |
| --- | --- |
| Queue depth / ready messages | Lượng công việc chờ, nếu broker expose |
| Unacked / in-flight | Message đã giao nhưng chưa ACK |
| Consumer lag | Chênh lệch tiến độ consumer và log end offset trong Kafka |
| Redelivery rate | Tần suất message cần giao lại |
| Retry scheduled / exhausted | Bao nhiêu sự kiện đang chờ hoặc vượt retry budget |
| DLQ ingress / age | Tốc độ và độ tuổi message vào DLQ |
| Processing p95/p99 | Độ trễ một attempt; tránh chỉ nhìn average |
| Ack/commit failure | Dấu hiệu tiến độ không được xác nhận |
| Outbox pending age | Chậm phát message dù business DB đã commit |
| Logging queue depth / drops | Khả năng quan sát log có đang gặp sự cố riêng |

Tên metric tùy broker/client/agent; bảng trên là loại thông tin nên tìm, **không phải những metric mặc định đều cùng tên**.

Khi queue backlog tăng, có thể:
- Tăng số consumer trong giới hạn partition/order và capacity của database.
- Giảm số message làm việc nặng hoặc batch hợp lý.
- Thiết lập prefetch/max in-flight để tránh giữ quá nhiều message trong memory.
- Retry có backoff để tránh đánh vào dependency đang quá tải.
- Tách poison message qua retry/DLQ có kiểm soát.
- Điều chỉnh producer rate hoặc admission control theo SLA.

**Thêm consumer không phải lúc nào cũng tăng throughput.** Kafka bị giới hạn tính song song trong một consumer group bởi số partition và cách phân bổ; database hoặc downstream có thể đã là nút thắt. Scale thiếu kiểm soát có thể tăng contention và số lần retry.

## 14. Ordering: thứ tự ghi log và thứ tự xử lý không giống nhau

Có thể một message m1 được publish trước m2, nhưng m2 lại hoàn thành trước do xử lý song song, retry hoặc sự cố mạng.

- **Queue đơn + một consumer tuần tự** có thể dễ quan sát FIFO hơn, nhưng vẫn phải xem tính chất delivery/requeue.
- **Kafka** giữ thứ tự record **trong một partition** theo offset; không bảo đảm thứ tự toàn cục giữa các partition.
- **RabbitMQ** có các quy tắc ordering cụ thể, nhưng multiple consumers, requeue và priority có thể làm thứ tự xử lý/hoàn tất khác thứ tự publish.
- **Async appender/log collector** cũng có thể hiển thị log đến muộn, được batch lại hoặc ingest khác thứ tự tạo.

Để dựng timeline, dùng `occurredAt` theo nguồn, `ingestedAt` nếu có, `messageId`, `operationId`, `attempt`, `partition+offset` hoặc `sequence` trong phạm vi được định nghĩa. Timestamp của hai host có thể lệch đồng hồ; không nên khẳng định causal order chỉ dựa vào sort timestamp.

### Log redelivery không tự chứng minh lỗi xử lý

Một consumer có thể:
1. Commit side effect thành công.
2. Gửi ACK nhưng mất kết nối.
3. Nhận lại cùng message.

Nhìn chỉ hai dòng `MESSAGE_RECEIVED` sẽ thấy hai lần nhận, không biết hiệu lực kinh doanh có lặp hay không. Cần log `PROCESSING_APPLIED` hoặc `DEDUPLICATED` theo ranh giới đúng, liên kết với idempotency store và event ID tin cậy.

## 15. Queue của logging backend: một tầng rủi ro khác

Ứng dụng message thường phát nhiều log trên hot path. Nếu dùng `AsyncAppender` của Logback, các event logging có thể vào **memory queue riêng** rồi worker mới ghi file/console/collector.

```text
Business producer -> broker -> consumer -> DB/ACK
                                    |
                                    v
                              logger.info(...)
                                    |
                                    v
                             AsyncAppender queue
                                    |
                                    v
                               logging sink
```

Cần phân biệt:

- Broker ACK chỉ nói về business message.
- Logger level/filter quyết định event có được phát không.
- AsyncAppender có thể giữ event trong memory; crash làm mất event chưa drain.
- Khi queue log đầy, backend có thể block producer log hoặc discard những level thấp theo cấu hình.
- Worker của async logging xử lý chậm không có nghĩa business consumer phải retry message.
- Graceful stop/drain log cần được thiết kế; ngay cả queue drain cũng không chứng minh collector từ xa đã durable nếu transport không có ack phù hợp.

Trong Logback, các tùy chọn `queueSize`, `discardingThreshold`, `neverBlock` và `maxFlushTime` điều chỉnh behavior của AsyncAppender; semantics khác giữa các backend. Không mặc định `neverBlock=true` giúp “không ảnh hưởng nghiệp vụ và không mất log”: khi queue đầy, nó có thể bỏ event.

**Audit quan trọng** như việc thay đổi quyền hoặc giao dịch không nên dựa chỉ vào một `INFO` async best-effort nếu yêu cầu độ bền. Dùng audit repository/outbox hoặc đường lưu có acknowledgment và kiểm tra khi sink không khả dụng.

## 16. Bảo mật dữ liệu message trong log

Business message có thể chứa thông tin thanh toán, định danh, địa chỉ, token, tài liệu hoặc payload lớn. Không log nguyên message body chỉ vì có message broker.

Nên ghi:
- `messageId`, `operationId`, `queue`/`topic`, `partition`/`offset` nếu cần.
- `schemaVersion`, loại message, outcome, reasonCode.
- Attempt, latency, retry delay, DLQ destination và status đã xác minh.
- ID tài nguyên **đã đánh giá** là phù hợp và an toàn để log.

Cần tránh:
- Password, private key, access/refresh token, session cookie, raw Authorization header.
- Toàn bộ payload JSON/XML hoặc object `toString()` có thể chứa PII.
- Exception message/stack trace chưa đánh giá nếu chứa URI/credential/query nhạy cảm.
- Giá trị `correlationId` do client tự đặt mà không validate, gây log injection.
- Business payload trong nhãn metric có cardinality cao hoặc quyền truy cập rộng.

Nếu cần lưu raw message để forensic, phải đặt trong kho có quyền truy cập, encryption, retention và audit access phù hợp, không gửi sang collector chung. DLQ cũng có thể chứa raw payload và cần chính sách bảo vệ tương đương.

## 17. Kiểm thử queue và delivery

### 17.1. Ma trận cơ bản

| Kịch bản | Kỳ vọng nghiệp vụ | Kỳ vọng log |
| --- | --- | --- |
| Publish thành công | Broker nhận theo contract | Có `SEND_ATTEMPTED` và `BROKER_CONFIRMED` ở đúng mốc |
| Publish timeout | Có thể đã nhận hoặc chưa | Trạng thái không chắc, ID giúp đối soát |
| Consumer nhận và xử lý thành công | Effect được xác minh rồi ACK | `RECEIVED`, `COMMITTED`, `ACK_ATTEMPTED` đúng thứ tự nhân quả |
| Consumer crash trước effect | Message còn khả năng giao lại theo hợp đồng | Không ghi `COMMITTED` giả |
| Crash sau effect, trước ACK | Có thể redelivery | Lần hai `DEDUPLICATED`, không áp dụng effect trùng |
| Lỗi transient | Retry có giới hạn/backoff | Attempt + reasonCode, không spam stack vô hạn |
| Poison message | Bị cách ly/DLQ sau policy | `RETRY_EXHAUSTED`/`DEAD_LETTERED` có ID |
| Kafka commit lỗi | Record có thể đọc lại | Không log commit confirmed nếu chưa xác minh |
| Queue backlog cao | Không vượt ngân sách memory/disk | Metric queue/lag/backpressure và alert |
| Log sink lỗi | Business policy vẫn đúng | Metric/status của logging độc lập; audit bắt buộc không mất âm thầm |
| Hai consumer song song | Không double-effect | So tập ID/effect, không ép thứ tự toàn cục |
| Re-drive DLQ | Chỉ replay event được phép | Giữ correlation, idempotency, lịch sử retry |

### 17.2. Unit test có thể làm ngay trên `QueueDeliveryDemo`

Với fake broker, viết test:
- Publish m1, m2 và drain queue: `appliedCount()==1`, `dlqCount()==1`, `pendingCount()==0`.
- Bắt stdout hoặc thay bằng collector event thử: phải có `APPLIED m1` chỉ **một lần**, và `DEDUP m1` ở lần nhận lại.
- m2 thử đúng ba lần và vào DLQ.
- NACK/requeue không được nhầm với ACK.
- Nếu thêm retry budget tùy cấu hình, kiểm tra điều kiện đạt ngưỡng không tạo vòng lặp vô hạn.

Không biến output text trong demo thành tiêu chuẩn logging production. Test nên quan sát **state và event cấu trúc**, sau đó xác nhận output của backend trong một integration test riêng.

### 17.3. Integration test với broker thật

Dùng broker/container test cô lập (RabbitMQ/Kafka theo stack ứng dụng), database test và event IDs duy nhất:

1. Gửi message, xác nhận ack/commit của producer theo giao thức.
2. Cho consumer bắt đầu, chặn đúng trước/sau business commit bằng latch/hook.
3. Kill/restart consumer trong các điểm lỗi khác nhau để đo redelivery.
4. Xác minh số business mutation với khóa idempotency, không chỉ đếm `RECEIVED`.
5. Kiểm tra log có đủ `messageId`, `attempt`, outcome và reasonCode.
6. Làm collector offline riêng; xác định phần nào mất log, phần nào vẫn xử lý message.
7. Test retry budget, DLQ và re-drive không sinh duplicate ngoài ý muốn.
8. Dọn queue/topic/test group và file tạm; không gửi payload thật hoặc kết nối production.

Khi kiểm tra async logging, dùng `BlockingQueue.poll(timeout)`, latch hoặc ack từ sink thực sự; **không dùng `Thread.sleep(500)` rồi kết luận message/log đã được giao**. Với kiểm tra sự kiện không được xuất hiện, cần ranh giới drain/sentinel/FIFO theo contract hoặc cơ chế xác nhận dứt điểm phù hợp.

### 17.4. Fault injection nên có

- Broker không khả dụng lúc producer send.
- Broker xác nhận nhưng producer mất response.
- Consumer xử lý xong nhưng ACK/commit không được ghi nhận.
- Consumer crash lúc transaction đang chạy.
- DB update conflict/rollback.
- Downstream side effect đã thành công nhưng callback timeout.
- Requeue ngay tạo hot loop và giải pháp backoff.
- Message payload không parse được.
- Đầy queue, hết retention hoặc DLQ đầy.
- Log appender/collector lỗi trong khi business processing còn chạy.

Một hệ thống tốt phải trả lời rõ **điểm nào có thể tạo duplicate**, **điểm nào có thể làm mất message**, **event nào chứng minh điều gì**, và **cách khôi phục** sau mỗi kiểu lỗi.

## 18. Sự cố thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| Nhiều `MESSAGE_RECEIVED` cho cùng ID | Redelivery, retry hoặc publish trùng | Phân biệt message ID vs attempt, kiểm tra ACK/dedup |
| Business chạy hai lần | ACK mất sau commit, không có idempotency | Transactional inbox/idempotency key |
| Log `PROCESSED` nhưng DB không đổi | Ghi log trước commit hoặc update 0 hàng | Chốt outcome sau xác minh mutation |
| Message “biến mất” | ACK sớm, retention, TTL, auto-commit, filter truy vấn | Đối chiếu broker metadata/offset và nguồn sản xuất |
| Queue bị kẹt một record | Poison message retry vô hạn | Retry bounded, backoff, DLQ |
| Kafka lag tăng dù consumer còn sống | Processing chậm, pause, rebalance, DB bottleneck | Profile xử lý, giới hạn concurrency, kiểm tra partition |
| RabbitMQ unacked tăng | Consumer không ACK, mất worker hoặc prefetch quá cao | Kiểm tra consumer lifecycle và unacked |
| DLQ tăng liên tục | Schema mismatch hoặc dependency lỗi kéo dài | Phân loại reason, sửa root cause trước re-drive |
| ACK được log nhưng vẫn redelivery | ACK mơ hồ/mất connection hoặc log tên sai mốc | Tách `ACK_REQUESTED` khỏi confirmed |
| Log mất nhưng message vẫn xử lý | Async logging queue discard hoặc collector down | Monitor kênh log riêng, audit durability |
| Log messageId của request khác | Rò MDC qua thread pool | Restore/clear MDC và test concurrency |
| Dashboard đảo thứ tự event | Ingest trễ, clock skew, nhiều partition | Dùng event ID, offset/sequence, source timestamp |
| Scaling consumer không cải thiện | Partition giới hạn hoặc downstream đã quá tải | Xác định throughput bottleneck trước khi scale |

## 19. Checklist thiết kế trước khi đưa vào production

- [ ] Phân biệt **business message delivery** và **log event delivery**.
- [ ] Định nghĩa tên và ý nghĩa các mốc `RECEIVED/COMMITTED/ACK_REQUESTED/RETRY/DLQ`.
- [ ] Producer biết khi nào nhận broker confirmation và cách xử lý kết quả gửi mơ hồ.
- [ ] Consumer chốt hiệu lực nghiệp vụ trước ACK/offset commit theo contract.
- [ ] Có idempotency key và bảo đảm transaction/durable state phù hợp.
- [ ] Retry có timeout, backoff, budget và phân loại transient/permanent.
- [ ] Có DLQ/re-drive, retention, quyền truy cập và cảnh báo tồn đọng.
- [ ] Có message ID, operation ID, attempt; Kafka có topic-partition-offset khi thích hợp.
- [ ] Không hứa thứ tự toàn cục hoặc exactly-once ngoài phạm vi broker/pipeline.
- [ ] MDC/correlation được truyền và dọn đúng ranh giới worker; không log raw payload.
- [ ] Theo dõi queue depth, lag, unacked, redelivery, DLQ và lỗi ACK/commit.
- [ ] Đường logging có metric/status độc lập và chính sách khi async queue đầy.
- [ ] Audit nghiệp vụ quan trọng có hợp đồng lưu bền vững thay vì chỉ `logger.info`.
- [ ] Có test crash ở cả trước/sau commit, lost ACK, duplicate, retry và collector outage.
- [ ] Có runbook đối soát message bị thiếu/đã xử lý lặp và replay an toàn.

**Ghi nhớ:** queue giúp tách thời điểm gửi và nhận, nhưng không tự bảo đảm “xử lý đúng một lần”. Log cần nói rõ **lần giao nào**, **thao tác nào**, **ACK đã đạt mốc nào**, **business effect đã commit chưa** và **đường log có đủ tin cậy không**. Kết hợp schema quan sát nhất quán, ACK đúng thời điểm, idempotency bền vững, retry/DLQ có kiểm soát và fault-injection test sẽ giúp hệ thống message dễ điều tra, phục hồi và vận hành an toàn.
