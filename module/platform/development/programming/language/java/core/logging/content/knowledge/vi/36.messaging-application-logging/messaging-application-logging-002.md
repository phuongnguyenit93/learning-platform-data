# Log message producer trong Java: quan sát đúng từng giai đoạn gửi message

## 1. Message producer là gì và vì sao cần logging riêng?

Trong hệ thống message-driven, **message producer** là thành phần tạo và gửi sự kiện/lệnh tới một broker, topic, exchange hoặc queue để một hay nhiều consumer xử lý về sau. Trong Java, producer có thể dùng Apache Kafka, RabbitMQ, Jakarta Messaging (JMS), thư viện client khác hoặc một giao diện nội bộ bọc các hệ thống trên.

Logging ở phía producer giúp trả lời: **ứng dụng định gửi message gì (ở mức metadata an toàn), gửi tới đâu, kết quả gửi được xác nhận đến mức nào, xảy ra lỗi gì, có retry không và làm sao liên kết với yêu cầu nghiệp vụ gốc?** Nó không chỉ nhằm in ra payload để “xem producer làm gì”.

Phải phân biệt ba sự kiện vốn dễ bị đánh đồng:

- **Producer đã gọi `send()`:** code đã bắt đầu thao tác; chưa đủ bằng chứng broker nhận.
- **Client/broker thông báo gửi thành công:** kết quả theo giao thức và cấu hình ACK; không nhất thiết consumer đã xử lý.
- **Consumer đã xử lý nghiệp vụ thành công:** xảy ra ở phía nhận, có thể rất lâu sau, thất bại hoặc được retry; producer không tự biết nếu không có cơ chế phản hồi nghiệp vụ.

Nguyên tắc quan trọng nhất: **không ghi “published successfully” ngay sau khi gọi một API gửi bất đồng bộ nếu chưa nhận được kết quả tương ứng từ callback/Future/confirm**. Lời gọi có thể chỉ đưa record vào bộ đệm RAM của client.

Logging producer cần kết hợp **structured events, callback, correlation ID, metrics, retry policy và bảo vệ dữ liệu**. Với message có ý nghĩa audit/giao dịch, cần thêm cơ chế lưu bền vững độc lập với log chẩn đoán.

## 2. Những mốc trong vòng đời một lần publish

Một producer thường đi qua các giai đoạn sau:

~~~text
Business operation / HTTP request / scheduled task
        │
        ▼
Tạo eventId, correlationId; kiểm tra dữ liệu và schema
        │
        ▼
[1] SEND_ATTEMPT (đề nghị gửi, chưa có kết quả)
        │
        ▼
Serialize / chọn topic, partition, routing key
        │
        ├─ lỗi tức thời ở call site → [2a] CLIENT_REJECTED
        ▼
Đưa vào client buffer / gửi qua mạng
        │
        ├─ timeout, broker reject, lỗi serialize...
        ▼
Broker xử lý theo cấu hình ACK/confirm
        │
        ├─ callback/error → [2b] SEND_FAILED / OUTCOME_UNKNOWN
        └─ callback/confirm → [3] BROKER_ACKED
                                    │
                                    ▼
                           Consumer nhận message
                                    │
                                    ▼
                           Consumer xử lý và commit/ACK riêng
~~~

Từ `SEND_ATTEMPT` tới `BROKER_ACKED` có thể là vài mili giây hoặc lâu hơn tùy tải và broker. Callback có thể chạy **trên thread khác**. Nếu chỉ gắn MDC ở thread gửi và không propagate context, log callback có thể thiếu `traceId` hoặc lẫn ngữ cảnh.

Đừng đồng nhất `BROKER_ACKED` với “delivered to all subscribers”, “consumer đã chạy”, “database consumer đã commit” hoặc “mãi mãi không mất dữ liệu”. Ý nghĩa ACK phụ thuộc broker, durability, cấu hình và thời điểm fail.

Một số client có bước trả về `Future` hoặc `CompletionStage`; đó là handle của thao tác, **không phải success result** tại thời điểm nhận được object này.

## 3. Những event nên log và level tham khảo

| Event code | Khi nào phát | Mức gợi ý | Ý nghĩa chính xác |
| --- | --- | --- | --- |
| `PRODUCE_ATTEMPT` | Trước mỗi lần ứng dụng chủ động gọi send | DEBUG/FINE hoặc metric | Đã bắt đầu một application attempt |
| `PRODUCE_ENQUEUED` | Client xác nhận chấp nhận vào local buffer (nếu có tín hiệu đáng tin) | DEBUG/FINE | Chưa có broker ACK |
| `PRODUCE_ACKED` | Callback/confirm thành công theo hợp đồng broker | INFO hoặc DEBUG theo nhu cầu | Broker/client xác nhận kết quả gửi |
| `PRODUCE_REJECTED` | Validation/serialization hoặc client API từ chối ngay | WARN | Lần gọi không được chấp nhận theo contract |
| `PRODUCE_FAILED` | Future/callback báo lỗi | WARN/ERROR | Gửi bị báo lỗi; cần xét loại và mức chắc chắn |
| `PRODUCE_OUTCOME_UNKNOWN` | Hết hạn/đứt mạng khi không xác định broker đã nhận hay chưa | WARN | Không thể kết luận message đã mất |
| `PRODUCE_RETRY_SCHEDULED` | Ứng dụng tự quyết định retry | DEBUG/INFO hoặc metric | Sắp có attempt mới, có nguy cơ trùng |
| `PRODUCE_EXHAUSTED` | Hết budget retry và xử lý thất bại theo policy | ERROR/WARN | Không còn ứng dụng retry thông thường |
| `OUTBOX_COMMITTED` | Event đã được commit trong outbox bền vững | INFO/audit theo policy | Đã lưu local durable intent, chưa phải broker ACK |
| `CONSUMER_PROCESSED` | Do **consumer** phát sau kết quả nghiệp vụ | Kênh riêng | Producer không tự được phát event này |

Các mức chỉ là **khuyến nghị**, không phải một chuẩn cố định cho mọi tổ chức. Ở throughput rất cao, log `PRODUCE_ACKED` cho từng message có thể quá đắt; nên dùng metric tổng hợp, sampling hoặc kênh theo event class. Nhưng nếu event bắt buộc audit, chính sách không được làm mất bằng chứng chỉ vì log level bị giảm.

Đặc biệt **không ghi cùng một success ở cả phía trước và trong callback**. Nếu có log “start” và “ack”, chúng phải có tên sự kiện khác nhau và cùng `eventId` để không bị đếm như hai lần publish thành công.

## 4. Thiết kế schema producer log có thể truy vết

Một producer event hữu ích nên có **trường cố định**, kiểu dữ liệu, ý nghĩa và chính sách bảo vệ rõ ràng:

| Field | Công dụng | Lưu ý |
| --- | --- | --- |
| `eventCode` | Phân loại trạng thái, ví dụ `PRODUCE_ACKED` | Mã ổn định, không phụ thuộc message tự do |
| `messageId` hoặc `eventId` | Định danh message từ ứng dụng | Giữ ổn định qua retry; không lấy từ payload bí mật |
| `messageType` / `schemaVersion` | Loại sự kiện và phiên bản nội dung | Dùng allowlist; hỗ trợ điều tra lỗi schema |
| `correlationId` / `requestId` | Kết nối với HTTP request và business operation | Không tự là identity proof |
| `traceId` / `spanId` | Liên kết distributed tracing | Cần propagate chuẩn qua header |
| `destination` / `topic` / `exchange` | Nơi gửi | Kiểm tra giá trị không chứa credential |
| `partition` / `offset` hoặc `publishSeqNo` | Metadata broker trả về | Chỉ ghi nếu có và có nghĩa theo broker |
| `attempt` | Lần thử gửi do **ứng dụng** quản lý | Không nhầm với retry nội bộ client |
| `outcome` | `ACKED`, `FAILED`, `UNKNOWN` theo contract | Không dùng `CONSUMED` từ producer |
| `reasonCode` / `exceptionClass` | Phân loại lỗi | Không đưa raw exception message chứa secret |
| `elapsedMs` | Độ trễ từ mốc xác định tới kết quả | Dùng monotonic clock cho duration |
| `producerInstance` | Nhận diện instance/region khi điều tra | Không log host token hoặc config secret |
| `timestamp` | Thời điểm ghi sự kiện | UTC và đồng bộ clock |

Ví dụ JSON **minh họa**, không phải output mặc định của JUL hay Kafka:

~~~json
{
  "eventCode": "PRODUCE_ACKED",
  "messageId": "evt-001",
  "messageType": "ORDER_CREATED",
  "schemaVersion": 2,
  "correlationId": "req-8fd",
  "destination": "orders.events",
  "partition": 0,
  "offset": 501,
  "attempt": 1,
  "outcome": "ACKED",
  "elapsedMs": 18
}
~~~

Không giả định mọi broker có `partition` và `offset`. Kafka cung cấp những trường này trong `RecordMetadata`; RabbitMQ dùng sequence/confirm theo channel; JMS có message ID và metadata theo provider.

**Phân biệt ID:**

- `messageId` là ID ứng dụng cấp trước khi publish để nối các attempt.
- `correlationId` nối message với request hay workflow; một request có thể tạo nhiều message.
- `traceId` liên kết các span chẩn đoán; có thể bị sampling nhưng business ID vẫn phải tồn tại.
- `Kafka key` là khóa phân vùng/ngữ nghĩa dữ liệu, không tự là ID bất biến.
- `Kafka offset` là vị trí record trong một topic-partition, không phải ID duy nhất toàn hệ thống.

## 5. Hai luồng lỗi: ném ngay và callback thất bại

Một client message có thể báo lỗi ở **hai thời điểm khác nhau**.

**Lỗi đồng bộ (trước/sau khi gọi `send` nhưng trên thread caller):** validate topic, khóa serializer, serialization, cấu hình, trạng thái producer đã đóng, thiếu metadata hoặc không cấp phát được buffer. Tùy API, `send()` có thể ném exception thay vì trả về Future.

**Lỗi bất đồng bộ:** callback/Future/CompletionListener nhận lỗi sau khi network/broker đã được thử. Đây mới là nơi quan sát nhiều lỗi ACK, broker, timeout hoặc authorization phát sinh muộn.

Mẫu Java **khái niệm**:

~~~java
try {
    // Một số client nhận callback để trả kết quả bất đồng bộ.
    // Khi callback thành công mới log ACK theo hợp đồng backend.
    client.send(message, (result, error) -> {
        if (error != null) {
            logSendFailed(messageId, classify(error));
        } else {
            logBrokerAcked(messageId, result);
        }
    });
} catch (RuntimeException error) {
    logClientRejected(messageId, classify(error));
}
~~~

Đây **không** phải API chung có thể biên dịch với mọi client; `client`, `message` và các method xử lý là giả định để minh họa hai nơi lỗi xuất hiện. Với từng broker cần dùng chính xác API tương ứng ở các mục sau.

Không tự động log ở cả `catch` và callback cho cùng một failure nếu client có thể gọi callback và ném theo một hợp đồng khác thường. **Đọc Javadoc của client** để biết exception tại call site có ngăn callback được gọi hay không.

Với timeout sau khi yêu cầu đã rời client, trạng thái có thể là **UNKNOWN**: broker đã ghi nhưng phản hồi bị mất. Retry cần dựa vào idempotency/dedup chứ không suy ra “chắc chắn message chưa tới broker”.

## 6. Ví dụ Java 17 chạy độc lập: log theo kết quả gửi bất đồng bộ

Chương trình dưới đây **mô phỏng** message broker bằng `CompletableFuture` và một thread gửi. Nó chạy với JDK 17, **không cần Kafka/RabbitMQ/JMS** và không kết nối broker thật. Chương trình chủ động tạo một sự kiện thành công và một sự kiện timeout giả ở lần thử đầu, sau đó retry thành công.

Mục đích kiểm chứng:

1. Log `send attempt` ở `FINE` trước khi gửi, có thể bật/tắt.
2. Log `publish acknowledged` ở `INFO` sau khi Future hoàn thành thành công.
3. Log `publish failed` ở `WARNING` khi Future hoàn thành lỗi.
4. Giữ cùng `messageId` khi retry nhưng tăng `attempt`.
5. Không ghi nội dung `payload`, exception message thô hoặc PII.
6. Callback chạy trên một executor nhưng log vẫn mang ID qua biến đã capture, không cần dựa vào thread-local MDC.
7. Đợi hoàn tất bằng `join()` trong **demo** để có đầu ra thứ tự xác định; production nên sử dụng pipeline async có giới hạn tải thay vì đợi từng message.

Tạo tệp **ProducerLoggingDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeoutException;
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class ProducerLoggingDemo {
    private static final Logger LOG = Logger.getLogger("demo.producer");

    record Outbound(String messageId, String topic, String payload) {}
    record Receipt(int partition, long offset) {}

    static final class FakeBroker implements AutoCloseable {
        private final ExecutorService executor =
                Executors.newSingleThreadExecutor();

        CompletableFuture<Receipt> send(Outbound message, int attempt) {
            return CompletableFuture.supplyAsync(() -> {
                if ("evt-002".equals(message.messageId()) && attempt == 1) {
                    throw new CompletionException(
                            new TimeoutException("simulated timeout"));
                }
                return new Receipt(0, "evt-001".equals(
                        message.messageId()) ? 501L : 502L);
            }, executor);
        }

        @Override
        public void close() {
            executor.shutdown();
        }
    }

    private static String reason(Throwable error) {
        Throwable root = error;
        for (int depth = 0; depth < 8 && root.getCause() != null; depth++) {
            root = root.getCause();
        }
        return root instanceof TimeoutException
                ? "BROKER_TIMEOUT" : "SEND_ERROR";
    }

    private static boolean sendAndObserve(
            FakeBroker broker, Outbound message, int attempt) {
        LOG.log(Level.FINE,
                "send attempt messageId={0} topic={1} attempt={2}",
                new Object[]{message.messageId(), message.topic(), attempt});

        // Callback reflects completion, not just local send invocation.
        return broker.send(message, attempt).handle((receipt, error) -> {
            if (error != null) {
                LOG.log(Level.WARNING,
                        "publish failed messageId={0} topic={1} reasonCode={2} attempt={3}",
                        new Object[]{message.messageId(), message.topic(),
                                reason(error), attempt});
                return false;
            }
            LOG.log(Level.INFO,
                    "publish acknowledged messageId={0} topic={1} partition={2} offset={3} attempt={4}",
                    new Object[]{message.messageId(), message.topic(),
                            receipt.partition(), receipt.offset(), attempt});
            return true;
        }).join(); // Demo waits for deterministic output.
    }

    public static void main(String[] args) {
        if (args.length > 1 ||
                (args.length == 1 && !"--debug".equals(args[0]))) {
            System.err.println("Usage: java ProducerLoggingDemo [--debug]");
            System.exit(2);
            return;
        }
        ConsoleHandler handler = new ConsoleHandler();
        handler.setLevel(Level.ALL);
        handler.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName() + " "
                        + formatMessage(record) + System.lineSeparator();
            }
        });
        LOG.setUseParentHandlers(false);
        LOG.setLevel(args.length == 1 ? Level.FINE : Level.INFO);
        LOG.addHandler(handler);
        try (FakeBroker broker = new FakeBroker()) {
            sendAndObserve(broker,
                    new Outbound("evt-001", "orders.events",
                            "PRIVATE_SAMPLE_DO_NOT_LOG"), 1);
            Outbound second = new Outbound(
                    "evt-002", "orders.events", "SENSITIVE_BODY");
            if (!sendAndObserve(broker, second, 1)) {
                sendAndObserve(broker, second, 2);
            }
        } finally {
            LOG.removeHandler(handler);
            handler.flush();
            handler.close();
        }
    }
}
~~~

Dùng JDK 17 trở lên:

~~~bash
javac --release 17 ProducerLoggingDemo.java
java ProducerLoggingDemo
~~~

**Standard error (stderr) chính xác ở chế độ mặc định:**

~~~text
INFO publish acknowledged messageId=evt-001 topic=orders.events partition=0 offset=501 attempt=1
WARNING publish failed messageId=evt-002 topic=orders.events reasonCode=BROKER_TIMEOUT attempt=1
INFO publish acknowledged messageId=evt-002 topic=orders.events partition=0 offset=502 attempt=2
~~~

**Standard output (stdout):** trống. Exit code: `0`. `ConsoleHandler` của JUL ghi vào stderr.

Chạy thêm:

~~~bash
java ProducerLoggingDemo --debug
~~~

**Standard error (stderr) khi bật `FINE`:**

~~~text
FINE send attempt messageId=evt-001 topic=orders.events attempt=1
INFO publish acknowledged messageId=evt-001 topic=orders.events partition=0 offset=501 attempt=1
FINE send attempt messageId=evt-002 topic=orders.events attempt=1
WARNING publish failed messageId=evt-002 topic=orders.events reasonCode=BROKER_TIMEOUT attempt=1
FINE send attempt messageId=evt-002 topic=orders.events attempt=2
INFO publish acknowledged messageId=evt-002 topic=orders.events partition=0 offset=502 attempt=2
~~~

Standard output vẫn trống; exit code `0`. Những số offset **501/502 là giá trị giả lập của FakeBroker**, không phải offset từ Kafka thực tế.

**Lưu ý giới hạn:** `FakeBroker` luôn cho thành công ở attempt thứ hai của `evt-002`. Trong broker thật, timeout chưa chắc đồng nghĩa message chưa được ghi; nếu retry, có thể xuất hiện bản sao. Demo này không kiểm thử durability, broker ACK thật, transaction, distributed tracing hoặc outbox. `reason(...)` trả **mã lỗi an toàn** thay vì ghi exception message giả chứa dữ liệu ngoài kiểm soát.

## 7. Phân tích ví dụ: vì sao không log “success” ngay sau `send()`?

Trong code demo, `sendAndObserve` gọi `broker.send(...)` và nhận `CompletableFuture<Receipt>`. Future có thể **chưa hoàn thành**. Chỉ khi handler `handle((receipt,error)->...)` được gọi với `error==null` mới ghi `publish acknowledged`.

Có hai vòng đời khác nhau:

~~~text
Thread gửi                   Thread callback / simulated broker
-----------                  ----------------------------------
log FINE attempt
send(...) ------------------> async work
nhận Future                   (gửi/thử gửi...)
                              ├── success: log INFO acknowledged
                              └── error: log WARNING failed
join() chờ kết quả <--------- kết quả handler
~~~

Nếu ứng dụng chỉ ghi:

~~~java
var future = producer.send(record);
log.info("published successfully");
~~~

thì đây là một **đoạn code sai về ngữ nghĩa quan sát** khi `send` là asynchronous; dòng log có thể chạy trước khi broker phản hồi, hoặc ngay cả lúc request sau đó thất bại. `record`, `producer` và `log` trong đoạn trên là biến của ứng dụng có API thích hợp, không phải chương trình Java độc lập.

Cách sửa là **ghi ở callback hoặc xử lý Future khi hoàn thành**; hoặc đợi Future khi thực sự cần đồng bộ và chấp nhận chi phí latency. Không biến mọi lần publish thành `future.get()/join()` trong request thread chỉ để dễ logging.

## 8. Apache Kafka: log trong callback của `KafkaProducer.send`

Kafka Producer Java hỗ trợ:

- `KafkaProducer.send(ProducerRecord<K,V>, Callback)`: gửi bất đồng bộ và callback khi broker ACK hoặc có lỗi.
- `RecordMetadata` trong callback thành công: thông tin như `topic()`, `partition()`, `offset()`, timestamp tùy tình huống.
- `send(...)` cũng trả `Future<RecordMetadata>`; lấy Future **không** chứng minh hoàn tất.
- Một số lỗi có thể ném trên thread gọi `send` trước khi callback, ví dụ serialization/cấu hình/buffer/metadata. Điều kiện và loại exception phụ thuộc phiên bản.
- Callback Kafka thường chạy trên I/O thread của producer. **Không chặn callback** bằng mạng, truy vấn DB hoặc định dạng log payload khổng lồ.

Đoạn minh họa trong ứng dụng có `producer` kiểu `KafkaProducer<String,byte[]>`, `record` kiểu `ProducerRecord<String,byte[]>`, cùng `messageId` đã tạo an toàn:

~~~java
// Minh họa Kafka API: yêu cầu kafka-clients tương thích.
try {
    producer.send(record, (metadata, error) -> {
        if (error != null) {
            LOG.warn("producer outcome=FAILED messageId={} topic={} errorClass={}",
                    messageId, record.topic(),
                    error.getClass().getSimpleName());
            return;
        }
        LOG.info("producer outcome=ACKED messageId={} topic={} partition={} offset={}",
                messageId, metadata.topic(), metadata.partition(),
                metadata.offset());
    });
} catch (RuntimeException error) {
    LOG.warn("producer outcome=CLIENT_REJECTED messageId={} topic={} errorClass={}",
            messageId, record.topic(), error.getClass().getSimpleName());
}
~~~

Đây **không** phải ví dụ Java độc lập: `LOG` là logger SLF4J đã cấu hình và các biến Kafka được khởi tạo. Sử dụng thư viện và exception policy theo phiên bản `kafka-clients` của dự án.

**Điểm quan trọng về Kafka ACK:**

1. Với `acks=0`, producer không chờ broker acknowledgement theo cách `acks=all`; không gắn nhãn “broker xác nhận ghi bền vững” cho callback thành công trong cấu hình này. Offset được cung cấp có thể là `-1`.
2. Với `acks=1` hay `acks=all`, mức bảo đảm phụ thuộc leader, replicas trong ISR, `min.insync.replicas` và cấu hình liên quan.
3. Kafka callback ACK cho một record **không** nói rằng consumer đã poll record hoặc xử lý nghiệp vụ.
4. `partition` và `offset` có nghĩa trong phạm vi topic/partition; consumer lag là phép đo khác.
5. Nếu một lỗi timeout xảy ra sau khi request được gửi, kết quả có thể bất định. Không log “message LOST” chỉ từ một `TimeoutException`.

Dựa trên tài liệu `KafkaProducer.send`, callback gửi vào broker là mốc đúng để log kết quả gửi, đồng thời cần kiểm tra ngoại lệ đồng bộ ở nơi gọi.

## 9. Kafka retries, idempotence và transaction: cách đặt nhãn log

Kafka producer có thể **retry nội bộ**; vì vậy phải phân biệt:

- `attempt` do **ứng dụng** gọi lại `send` sau một kết quả lỗi.
- `retry` của Kafka client bên trong một lời gọi send.
- `redelivery` ở consumer do consumer fail hoặc replay.
- `duplicate business event` do hai transaction/outbox publish cùng ý định nghiệp vụ.

Đừng ghi `attempt=3` dựa trên suy đoán từ số lần Kafka tự gửi lại trên mạng nếu ứng dụng không có dữ liệu chính xác. Một callback không nhất thiết chạy mỗi lần client thực hiện network retry.

**Idempotent producer:** bật/duy trì cấu hình Kafka phù hợp với idempotence để giảm nguy cơ trùng record do retry nội bộ trong phạm vi được hỗ trợ. Điều này **không** ngăn ứng dụng tự phát hai business events với hai message IDs hoặc consumer xử lý lặp.

**Transactions:** Kafka transactional producer dùng `beginTransaction()`, `commitTransaction()` và `abortTransaction()` theo API thích hợp. Một callback gửi record có thể hoàn tất trước khi transaction được commit; với yêu cầu trạng thái “visible/committed”, phải log thêm outcome ở **mốc transaction commit** thay vì gọi mỗi record ACK là “transaction complete”.

**Timeout:** khi không nhận được kết quả chắc chắn, mã trạng thái `OUTCOME_UNKNOWN` thường rõ hơn `LOST`. Nếu retry ở tầng ứng dụng, dùng cùng business event ID, exponential backoff có jitter, retry budget và cơ chế idempotency phù hợp.

Các property như `acks`, `enable.idempotence`, `delivery.timeout.ms`, `request.timeout.ms` và `max.block.ms` cần được chọn theo phiên bản, yêu cầu delivery và workload. Không thay đổi bừa bãi chỉ để làm “ít log WARN” hơn.

## 10. RabbitMQ: publisher confirms, routing và correlation

Với RabbitMQ Java client AMQP 0-9-1, producer thường gọi `channel.basicPublish(...)`. Method trả về không có nghĩa broker đã gửi publisher confirm. Khi cần biết broker đã xử lý publish ở mức giao thức tương ứng, sử dụng **publisher confirms**.

Tài liệu RabbitMQ mô tả ba lựa chọn:

1. Gửi từng message rồi `waitForConfirmsOrDie(timeout)` — dễ hiểu nhưng giảm throughput.
2. Gửi batch rồi chờ confirm — nhanh hơn nhưng khó quy lỗi cho một message.
3. `channel.confirmSelect()` rồi đăng ký `addConfirmListener(...)` — callback async nhận ACK/NACK, cần bảng correlation.

Đoạn minh họa cách bật confirms, giả định `channel` là RabbitMQ `com.rabbitmq.client.Channel` đã kết nối:

~~~java
channel.confirmSelect();
channel.addConfirmListener(
        (deliveryTag, multiple) -> {
            // ACK: đối chiếu deliveryTag với messageId đã lưu trước publish.
        },
        (deliveryTag, multiple) -> {
            // NACK: ghi mã lỗi an toàn và đưa việc retry sang worker riêng.
        });
~~~

Đây là đoạn cấu hình callback trong ứng dụng có RabbitMQ client, không phải class độc lập; logic correlation đầy đủ cần map có vòng đời và đồng bộ phù hợp.

**Đặc trưng cần log đúng:**

- `deliveryTag`/publisher sequence number có phạm vi **channel**; không thay thế business `messageId`.
- Tham số `multiple=true` có thể xác nhận một dải sequence number, không chỉ một message. Correlation map phải xử lý đúng dải đó.
- Publisher confirm ACK có nghĩa broker đã xử lý message theo quy tắc confirm; nó **không** đồng nghĩa consumer đã nhận và ACK.
- **Publisher confirm khác consumer acknowledgment**. Consumer ACK là sự kiện riêng ở phía nhận.
- Khi sử dụng `mandatory`, cần xử lý **basic.return` cho message không route được theo policy. Một publisher confirm ACK **không đủ** để kết luận message đã tới một queue dự kiến nếu routing không đạt. Phải quan sát cả returned messages.
- Callback confirm của RabbitMQ có thể chạy trên thread I/O của client; tránh gọi lại publish và thao tác I/O/blocking nặng ngay trong callback. Chuyển việc retry sang executor/queue phù hợp.
- Sequence và callback có thể đến không theo thứ tự ứng dụng kỳ vọng; event ID cần tồn tại độc lập trong header/metadata theo policy.

Một log WARN “publish NACK” nên chứa `messageId`, exchange, routing key an toàn, delivery tag, attempt và reason code; **không** in raw body để tìm message.

## 11. Jakarta Messaging/JMS: send đồng bộ và `CompletionListener`

Jakarta Messaging định nghĩa `MessageProducer` và `JMSProducer`, có thể gửi đồng bộ hoặc bất đồng bộ tùy API và môi trường hỗ trợ.

Với gửi bất đồng bộ của `MessageProducer`, `CompletionListener.onCompletion(Message)` báo thao tác gửi đã hoàn tất **với mức tin cậy mà một lệnh send đồng bộ tương ứng có thể có**. `onException(Message, Exception)` báo lỗi xảy ra trong quá trình gửi async. Không tự suy luận callback luôn chứng minh dữ liệu đã được fsync bền vững, vì còn tùy provider, delivery mode và transaction.

Đoạn **minh họa API** (không phải class độc lập) với producer/message/`messageId` đã có:

~~~java
producer.send(message, new jakarta.jms.CompletionListener() {
    @Override
    public void onCompletion(jakarta.jms.Message completed) {
        LOG.info("JMS send completed messageId={}", messageId);
    }

    @Override
    public void onException(jakarta.jms.Message failed, Exception error) {
        LOG.warn("JMS send failed messageId={} errorClass={}",
                messageId, error.getClass().getSimpleName());
    }
});
~~~

Trong đoạn này, `LOG` là logger SLF4J. **Không log toàn bộ `Message`** vì headers/body có thể chứa dữ liệu bí mật.

Các lưu ý theo Jakarta Messaging 3.1:

- Lỗi có thể ném ngay trên thread gọi `send`; callback không thay thế xử lý lỗi đồng bộ.
- Provider quyết định công việc nào được làm trong thread gọi và thread background.
- Session/Message có các giới hạn sử dụng đồng thời; không đọc hoặc sửa `Message` bất đồng bộ một cách tùy tiện trước callback.
- Các method asynchronous send này bị **hạn chế/không được phép theo specification trong Jakarta EE web/EJB containers**; phải kiểm tra API và môi trường thay vì copy ví dụ vào bất cứ ứng dụng server nào.
- Với session transacted, send completion không tự có nghĩa transaction đã commit; mốc commit/rollback phải được quan sát riêng.
- JMS message ID, correlation ID và TTL có ngữ nghĩa riêng; đừng giả định chúng tương đương Kafka offset.

## 12. Correlation ID, trace context và header propagation

Nếu một HTTP request tạo ra message rồi được consumer xử lý ở process khác, log ở producer và consumer phải kết nối được **mà không cần in payload**.

Ví dụ luồng:

~~~text
HTTP request:
  requestId=req-8fd
  traceId=tr-281

Producer:
  messageId=evt-001
  topic=orders.events
  correlationId=req-8fd
  traceparent=<trace-context-value>
  outcome=ACKED

Consumer (ở ứng dụng khác):
  messageId=evt-001
  correlationId=req-8fd
  outcome=PROCESSED hoặc RETRY
~~~

Mẫu trên là sơ đồ, không phải output chạy. `traceparent` là header ngữ cảnh phân tán theo W3C Trace Context/OpenTelemetry khi sử dụng instrumentation tương ứng; không tự tạo text `traceparent` tùy ý rồi coi là hợp lệ.

**Quy tắc thực tế:**

1. Sinh `messageId` **trước lần gửi đầu tiên** và giữ ổn định qua application retry cho cùng logical event.
2. Gắn `correlationId` và tracing headers vào envelope/header nếu broker và chính sách cho phép; không dùng payload text để tìm ID.
3. Trên callback bất đồng bộ, capture các ID bất biến trong closure hoặc snapshot context rõ ràng. `MDC` của thread caller không bảo đảm tự đi sang thread callback.
4. Ở consumer, trích xuất header theo định dạng chuẩn rồi tạo span/context mới; làm sạch ThreadLocal/MDC sau xử lý để tránh lẫn message.
5. Tránh nhầm business actor ID với correlation ID: chúng có thể liên kết dữ liệu cá nhân và phải có retention/quyền truy cập phù hợp.

**Một message có thể được retry/duplicate** nhưng vẫn mang cùng ID logic. Bản ghi mỗi attempt thêm `attempt` hoặc `deliveryAttempt` tùy ngữ cảnh để phân biệt hoạt động thực tế.

## 13. Producer logging và quyền riêng tư: không log raw payload

Message body có thể chứa tên, địa chỉ, email, token, thông tin thanh toán, file hoặc dữ liệu thuộc quyền riêng tư. Các kiểu log sau rất nguy hiểm:

~~~java
// Tránh: toàn bộ payload/domain object có thể được in ra.
LOG.debug("publishing message={}", message);
LOG.info("sending payload={}", new String(bytes, java.nio.charset.StandardCharsets.UTF_8));
LOG.error("publish failed body={} exception={}", body, error.getMessage());
~~~

Các dòng trên là minh họa cho API logger dạng SLF4J; không phải code JDK độc lập. `toString()` của DTO/record và `Exception.getMessage()` có thể chứa dữ liệu vượt quyền.

Nên log các trường đã qua allowlist:

~~~text
eventCode=PRODUCE_ACKED
messageId=evt-001
messageType=ORDER_CREATED
topic=orders.events
partition=0
offset=501
attempt=1
payloadBytes=482
~~~

`payloadBytes` là kích thước, không phải nội dung; dù vậy các đặc tính như message type, topic, size hoặc ID vẫn có thể nhạy cảm trong một số hệ thống, cần đánh giá.

Khi cần điều tra một payload cụ thể, sử dụng **kho dữ liệu/trace có quyền kiểm soát riêng** theo quy trình được phê duyệt, chứ không bật DEBUG để xuất toàn bộ nội dung mọi message trên production.

Đối với Kafka key, Rabbit routing key, JMS properties và headers: cũng phải kiểm tra dữ liệu nhạy cảm. Tránh in `Authorization`, cookie, secret hay credential của kết nối broker.

## 14. Log exception đúng cách nhưng không gây rò rỉ

Một callback có `Throwable` hoặc `Exception`. Có hai mục tiêu cần cân bằng:

- **Phân loại sự cố nhanh:** lỗi serialization, auth, network timeout, broker reject, topic/queue không tồn tại, record quá lớn, quá tải.
- **Không lộ secret trong message/stack trace**: exception từ HTTP/JDBC/serializer có thể chứa URL, dữ liệu nhập, headers hoặc body.

Log tại kênh vận hành nên dùng `errorClass` và `reasonCode` từ allowlist; khi chính sách cho phép, có thể ghi stack trace vào kênh giới hạn quyền sau khi đã kiểm soát dữ liệu. Không log `error.toString()` một cách vô điều kiện.

Ví dụ phân loại:

| Loại lỗi | Mã gợi ý | Hành động |
| --- | --- | --- |
| Không serialize được payload | `SERIALIZATION_FAILED` | Kiểm tra schema/codec, thường không retry cùng dữ liệu thô |
| Thiếu quyền topic/exchange | `AUTHORIZATION_DENIED` | Cảnh báo cấu hình/quyền; không retry mù |
| Metadata/destination sai | `INVALID_DESTINATION` | Sửa tên và cấu hình |
| Tạm mất kết nối | `NETWORK_UNAVAILABLE` | Có thể retry/backoff trong giới hạn |
| Timeout không chắc broker đã ghi hay chưa | `OUTCOME_UNKNOWN` | Cần idempotency và đối chiếu |
| Broker NACK | `BROKER_NACK` | Phân tích confirm/routing và retry policy |
| Client buffer đầy | `PRODUCER_BACKPRESSURE` | Giảm tốc, giới hạn pending, điều chỉnh pipeline |
| Producer bị đóng | `CLIENT_CLOSED` | Sửa lifecycle và shutdown order |

Mã lỗi là taxonomy do ứng dụng lựa chọn; **không có bộ enum thống nhất** cho tất cả Kafka/RabbitMQ/JMS. Khi client đổi phiên bản, cần kiểm tra exception mapping.

**Không nhầm log WARN với đảm bảo ứng dụng xử lý lỗi.** Logging chỉ ghi nhận hiện tượng. Retry, DLQ, outbox, signal readiness và quyết định trả kết quả nghiệp vụ phải được implement rõ.

## 15. Retry, trùng lặp và trường `attempt`

Retry là phần quan trọng của producer, đồng thời dễ làm log bị hiểu sai.

Một message logic `evt-002` có thể có ba lần thử:

~~~text
evt-002 attempt=1 SEND_ATTEMPT
evt-002 attempt=1 OUTCOME_UNKNOWN
evt-002 attempt=2 SEND_ATTEMPT
evt-002 attempt=2 BROKER_ACKED
~~~

Nếu timeout ở lần đầu nhưng broker đã nhận, lần thứ hai có thể tạo **duplicate**. Log “attempt 1 failed” không chứng minh bản copy đầu không tồn tại. Vì vậy:

- Dùng cùng logical `eventId` khi retry, thêm attempt number cho application-level retries.
- Thiết kế consumer idempotent hoặc áp dụng dedup key phù hợp với hệ thống.
- Dùng backoff có jitter, giới hạn số lần retry/thời hạn, phân biệt lỗi tạm thời và lỗi không thể retry.
- Không tự động retry vô hạn trong callback của client hoặc ngay trên thread I/O.
- Dùng metric `publish_attempt_total`, `publish_acked_total`, `publish_error_total`, `retry_scheduled_total` để kiểm soát khối lượng; các tên metric ở đây chỉ là gợi ý.
- Đừng đếm mỗi retry là **một business event** mới. Business ID và transport attempt phải là hai khái niệm riêng.

**Idempotency không tạo exactly-once end-to-end một cách tự động.** Consumer vẫn có thể xử lý lặp do redelivery, ứng dụng phát hai logical messages hoặc write side-effect không có transaction/dedup.

## 16. Gửi message và transaction nghiệp vụ: tránh dual-write

Một vấn đề lớn không giải quyết được bằng debug log:

~~~text
Business DB COMMIT thành công
       │
       ▼
producer.send(...) lỗi mạng hoặc JVM crash
       │
       ▼
DB đã đổi nhưng message không chắc đến broker
~~~

Ngược lại, nếu gửi message trước rồi transaction DB rollback, consumer có thể xử lý một sự kiện mô tả trạng thái chưa bao giờ được commit.

Với hệ thống cần bảo toàn **ý định phát sự kiện sau thay đổi nghiệp vụ**, có thể dùng **transactional outbox**:

~~~text
BEGIN DB transaction
  UPDATE order
  INSERT outbox(eventId, destination, safeEventPayload, state)
COMMIT
    │
    ▼
Outbox worker đọc bản ghi đã commit
    │
    ▼
Gửi message tới broker, theo dõi callback/ACK
    │
    ├── ACK: đánh dấu DELIVERED theo hợp đồng
    └── lỗi/UNKNOWN: retry có idempotency
~~~

Producer log có thể gồm `OUTBOX_COMMITTED`, `PRODUCE_ATTEMPT`, `BROKER_ACKED` và `OUTBOX_DELIVERED`; các mốc khác nhau và phải được định nghĩa. **Không** gọi `PRODUCE_ACKED` là DB transaction success.

Những điều outbox **không tự bảo đảm**:

- Broker nhận message ngay khi database commit.
- Không có duplicate nếu worker crash sau khi publish nhưng trước khi đánh dấu delivered.
- Consumer xử lý đúng một lần khi side-effect khác cần transaction.
- Outbox và broker luôn cùng một giao dịch vật lý.

Outbox thường dẫn tới mô hình **at-least-once delivery** ở phía ứng dụng; cần ID cố định, dedup và đo backlog. Payload nằm trong outbox cũng cần encryption, access control và retention.

## 17. Ngữ nghĩa “thành công” phải được diễn đạt chính xác

Không dùng một từ `SUCCESS` cho tất cả tình huống:

| Mốc quan sát | Câu diễn đạt chính xác | Điều chưa chứng minh |
| --- | --- | --- |
| Lời gọi `send` bắt đầu | “Publishing attempted” | Client chấp nhận |
| Có Future hoặc local enqueue | “Submission buffered/initiated” | Broker ACK |
| Kafka callback thành công với `acks` phù hợp | “Broker acknowledged according to producer config” | Consumer xử lý, side-effect hoàn tất |
| RabbitMQ publisher confirm ACK | “Broker confirmed publish” | Message đã tới queue mong muốn nếu routing/return chưa được xét; consumer đã ACK |
| JMS CompletionListener thành công | “Async send completed under provider's contract” | Transaction session đã commit nếu chưa có mốc đó |
| Outbox commit | “Publish intent stored durably in business DB” | Đã đến broker |
| Consumer ACK/commit | “Consumer delivery/process state reported” | Toàn bộ workflow downstream hoàn tất |
| Business completion event | “Business operation completed per application contract” | Các hệ thống ngoài chưa phản hồi nếu không có chứng cứ |

**Logging tốt không sửa được một giao thức giao nhận thiết kế sai.** Nó chỉ giúp diễn đạt trạng thái đúng để người vận hành không nhầm lẫn.

Nếu producer cần biết consumer đã xử lý, phải có **reply message, status store, callback nghiệp vụ hoặc correlation flow** phù hợp; producer không thể tự suy ra từ Kafka offset hoặc Rabbit publisher confirm.

## 18. Tương quan giữa logging, metrics và tracing

Ba công cụ phục vụ các mức quan sát khác nhau:

**Logs:** mô tả sự kiện và lý do cho một message cụ thể (event ID, destination, outcome, errorCode), nhất là khi lỗi.

**Metrics:** thống kê số event/giây, số failure, tỉ lệ retry, latency percentiles, pending/inflight, queue fullness, destination health. Đây là cách phù hợp khi throughput cao hơn mức nên log mọi ACK.

**Distributed traces:** nối HTTP request → business service → producer → broker → consumer, với span boundaries và trace context theo tiêu chuẩn. Traces có thể sampling; vì vậy **không** coi span bị thiếu là không có event.

Ví dụ dashboard producer:

- `messages_attempted_total`, `messages_acked_total`, `messages_failed_total`.
- `messages_outcome_unknown_total` và `retries_scheduled_total`.
- `publish_ack_latency_seconds` histogram với p95/p99.
- `producer_inflight_messages`, buffered records và backpressure.
- `outbox_oldest_pending_age_seconds` nếu có outbox.
- `broker_connectivity_status` và tỷ lệ auth failures.

Các metric trên chỉ là **gợi ý đặt tên**; client Kafka/RabbitMQ có hệ metric riêng. Khi xuất Prometheus, tránh đặt `messageId`, email hoặc `traceId` thành metric labels vì cardinality vô hạn và rủi ro dữ liệu. Dùng low-cardinality labels như destination đã chuẩn hóa và errorCode.

## 19. Performance: log mỗi message không phải lúc nào cũng đúng

Trên hệ thống gửi hàng chục nghìn messages/giây, một dòng INFO cho mỗi attempt và một dòng cho mỗi ACK sẽ tạo lưu lượng log rất lớn, tăng I/O, GC và chi phí lưu trữ.

**Chiến lược thông thường:**

1. Log chi tiết `PRODUCE_ATTEMPT` ở DEBUG/FINE khi điều tra, không bật vô thời hạn.
2. Ghi warning/error có cấu trúc cho failure/timeout/outcome unknown nhưng kiểm soát tần suất nếu cùng một sự cố bùng nổ.
3. Dùng **metrics** cho lượng ACK thành công; audit events quan trọng có pipeline riêng và không bị sampling tùy ý.
4. Nếu cần sampling success logs, ghi rõ tỷ lệ và không dùng log đã sampling để đối chiếu số message tuyệt đối.
5. Dùng parameterized logging thay vì nối chuỗi/serialize payload trước khi kiểm tra level.
6. Đừng block callback Kafka/RabbitMQ/JMS bằng disk sync, network API call hoặc query DB.
7. Giới hạn hàng đợi retry/pending và quan sát backpressure; producer log cũng có thể dùng async appender nên có khả năng bị drop khi JVM crash.

Ví dụ code có `LOG.log(Level.FINE, "send attempt ...", args)` để demo khi bật `--debug`, nhưng ứng dụng thực cần benchmark tổng chi phí và xác định dữ liệu nào có giá trị lâu dài.

## 20. Shutdown: đợi send thật sự hoàn tất và ghi kết quả

Một ứng dụng dừng theo lệnh triển khai không nên đơn giản “đã gọi `send()` hết rồi, thoát JVM luôn”. Đặc biệt nếu producer có buffer, send chưa hoàn thành có thể bị mất.

Một trình tự **graceful shutdown** tham khảo:

~~~text
Ngừng nhận công việc/message mới
     │
     ▼
Đợi các producer task còn hoạt động hoàn tất theo deadline
     │
     ▼
Gọi API close/flush của client broker đúng phiên bản
     │
     ▼
Đợi callback/Future/confirm trong phạm vi contract và timeout
     │
     ▼
Đánh dấu outbox/pending dựa trên kết quả chắc chắn
     │
     ▼
Stop async logging appenders và giải phóng tài nguyên
     │
     ▼
Thoát JVM
~~~

**Không đồng nhất:**

- Kafka `producer.flush()` chờ những record trước đó hoàn tất theo hợp đồng của producer, nhưng không biến thất bại thành ACK.
- Kafka `close(Duration)` có hành vi timeout/shutdown cụ thể cần đọc theo phiên bản; không gọi close từ chính callback I/O.
- RabbitMQ cần quản lý confirmation còn chờ, connection/channel lifecycle; một số callback không được thực hiện publish I/O trên cùng callback thread.
- JMS async close/commit có yêu cầu chờ callback và các ràng buộc threading; phải tuân theo provider/container.
- Logging appender flush chỉ xả **dữ liệu log**, không đợi broker xử lý message.

SIGKILL, JVM fatal crash hoặc mất điện có thể bỏ qua graceful shutdown. Sự kiện quan trọng cần recovery bằng outbox/queue bền vững, không chỉ dựa vào `finally` hay shutdown hook.

## 21. Kiểm thử producer logging trước khi production

Một bộ test tốt cần dùng **fake producer/test broker** và bản ghi thực ở appender/collector, không chỉ mock `LOG.info(...)`.

| Trường hợp | Hành vi test | Kỳ vọng |
| --- | --- | --- |
| Send success | Client callback success | Có `BROKER_ACKED` với ID và metadata hợp lệ |
| Send API throw | Serializer/config từ chối ngay | Có `CLIENT_REJECTED`; không báo ACK |
| Async failure | Future/callback báo lỗi | Có `PRODUCE_FAILED` và error code đúng |
| Timeout bất định | Không nhận ACK trong deadline | Có `OUTCOME_UNKNOWN`; không tự log “LOST” |
| Retry thành công | Attempt 1 lỗi, attempt 2 ACK | Cùng logical ID, hai attempt, một success được xác nhận |
| Retry gây duplicate | Broker đã nhận trước timeout | Dedup/idempotency của consumer/producer ứng xử theo policy |
| Kafka `acks=0` | Không có broker ACK theo giao thức | Log không khẳng định durable ACK |
| Rabbit publisher confirm ACK + return | Broker xác nhận nhưng không route đúng | Phân biệt confirmed vs routed |
| JMS async | `onCompletion/onException` | Log tương ứng, tuân thủ threading/session |
| Callback thread khác | MDC trên caller không tự truyền | Capture correlation ID/trace context chính xác |
| Shutdown có pending | Close/flush và các callback chưa hoàn tất | Không khẳng định delivered trước khi có tín hiệu |
| Producer crash | JVM dừng đột ngột | Có recovery từ outbox nếu chính sách yêu cầu |
| Payload chứa secret giả | Event body chứa `TEST_SECRET_DO_NOT_LOG` | Secret không xuất ở logs, metrics, trace hoặc error message |
| Thông điệp dài/định dạng lạ | JSON, binary, unicode | Log schema an toàn, không dump body |
| Burst tải cao | Queue gần đầy, broker chậm | Metrics/alert về inflight, backpressure, drop |
| Khi debug tắt/bật | Level thay đổi | Kết quả ACK/FAIL quan trọng vẫn được quan sát theo policy |

Trong unit test, lưu ý callback có thể chạy **ngay lập tức, muộn hoặc trên thread khác**. Tránh dựa vào `Thread.sleep(100)` để khẳng định callback đã xong; dùng `CompletableFuture`, `CountDownLatch`, test executor hoặc mock confirm với deadline rõ.

Khi dùng test broker thực, kiểm tra cả phía broker và consumer, kể cả topic/queue durability, publisher confirms, retry, headers, record metadata và cảnh báo khi mất mạng.

## 22. Tình huống điều tra: đã báo gửi nhưng consumer không thấy

**Triệu chứng:** phía HTTP service trả 202, producer log “message sent”, nhưng hệ thống downstream không có dữ liệu.

Đặt các câu hỏi theo thứ tự:

1. Producer có log **attempt** hay **broker ACK thực sự**? Có callback? Có lỗi đồng bộ không?
2. Kafka record có `topic/partition/offset` hợp lệ theo `acks` và cấu hình broker không? Nếu RabbitMQ, confirm ACK có đi cùng routing/return chính xác không?
3. Consumer subscribe đúng topic/queue, có group lag, permission, pause, rebalance hay không?
4. Schema/serializer có làm consumer từ chối và đưa message vào DLQ không?
5. Message có TTL, retention, compaction, dead lettering hoặc expiry không?
6. Consumer có xử lý rồi fail ở database và retry/rollback không?
7. Correlation ID có đi xuyên các hop và được ghi an toàn ở consumer không?
8. Có khả năng producer retry khiến consumer thấy hai bản sao và dedup thành một kết quả không?

Nếu chỉ tìm `logger.info("sent")` ngay sau `send()`, kết luận không đáng tin. Cần quan sát mốc và hệ thống tương ứng. Trường hợp “ACK đúng nhưng consumer không xử lý” chủ yếu cần điều tra consumer/routing/schema chứ không chỉ thêm retry ở producer.

## 23. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Log `SUCCESS` ngay sau `producer.send(...)` | Đánh dấu thành công khi chưa ACK | Ghi completion trong callback/Future/confirm |
| Không bắt lỗi ở call site | Mất các lỗi serialization/config trước callback | Xử lý cả synchronous và asynchronous failures |
| Coi mọi timeout là “broker không nhận” | Retry có thể tạo duplicate | Outcome UNKNOWN, idempotency và đối chiếu |
| Coi publisher confirm là consumer ACK | Báo hoàn tất nghiệp vụ sai | Phân biệt từng ranh giới xác nhận |
| Log raw payload/key/headers | Rò PII, credentials, tăng I/O | Chỉ dùng allowlisted metadata |
| Ghi `exception.getMessage()` tự do | Message có thể chứa secret | Error code/class an toàn; stack trace hạn chế |
| Chỉ dựa vào MDC caller | Callback thiếu/lẫn correlation | Snapshot ID, propagate context rõ, cleanup |
| Retry ngay trong I/O callback | Block event loop, deadlock hoặc tăng latency | Đưa retry vào worker/queue chuyên trách |
| Log INFO mỗi message tại tải cao | Log storm, chi phí GC/I/O | Metrics, sampling success theo policy |
| Dùng `attempt` để đếm client internal retry | Sai số lần ứng dụng chủ động gửi | Phân biệt application và transport retries |
| Coi Kafka offset là ID toàn hệ thống | Định danh không duy nhất giữa partition/topic | Dùng application eventId |
| Không kiểm tra Rabbit mandatory return | ACK nhưng message không route theo kỳ vọng | Theo dõi returns và confirms riêng |
| Coi JMS callback = transaction commit | Báo hoàn tất trước commit | Quan sát mốc commit/rollback riêng |
| Cho rằng outbox = exactly-once | Crash tạo duplicate/replay | Dedup và idempotent consumer |
| Đóng producer sớm, sau đó mới đóng log | Pending messages mất, callback không chạy | Shutdown theo thứ tự với timeout rõ |
| Gọi `logger.flush()` để chờ broker | Flush log là tầng khác | Dùng API producer/confirm đúng broker |
| Không giám sát pending/unknown | Lỗi có thể kéo dài dù log WARN | Metrics, alerts, DLQ/outbox backlog |
| Đặt message ID hoặc trace ID vào metric label | Cardinality cao, tăng chi phí và nguy cơ privacy | Dùng labels phân loại ít biến thiên |

## 24. Checklist review trước triển khai

1. Có định nghĩa rõ **mốc thành công của producer** và tách khỏi mốc xử lý consumer không?
2. Log có `messageId`, destination, eventCode, outcome, attempt và error code khi cần không?
3. Mọi `send()` bất đồng bộ đều có cơ chế quan sát callback/Future/confirm đúng API không?
4. Có xử lý ngoại lệ được ném **ngay tại nơi gọi** và lỗi trả về **sau đó** không?
5. Có tránh ghi `SUCCESS` khi chỉ mới buffer/enqueue không?
6. Khi timeout, có biểu diễn trạng thái UNKNOWN thay vì chắc chắn mất chưa?
7. Retry có backoff, jitter, giới hạn số lần và cơ chế idempotency/dedup không?
8. Có phân biệt retry nội bộ client với application-level attempt không?
9. Correlation ID/trace context có nằm trong envelope/header và được capture đúng ở callback thread không?
10. Có bảo vệ payload, key, header, exception message, MDC và schema log khỏi PII/secret không?
11. Các metric ACK/error/retry/inflight/backpressure/outbox có alert phù hợp không?
12. Callback có nhanh, không block I/O thread và không gọi lại publish trực tiếp khi bị cấm không?
13. Có test thành công, callback failure, synchronous exception, timeout, broker down và retry duplicate không?
14. Có test shutdown/crash, pending sends và callback completion theo thời hạn không?
15. Nếu nghiệp vụ cần tính bền vững, có outbox/transaction/recovery và kiểm tra theo ID độc lập với log không?
16. Có tài liệu theo backend đang chạy (Kafka/RabbitMQ/JMS phiên bản phù hợp) và kiểm chứng tại sink cuối cùng không?

## 25. Câu hỏi tự luyện

1. Vì sao một Future trả về từ `KafkaProducer.send` chưa cho phép log “đã gửi thành công”?
2. Callback Kafka thành công với `acks=0` có chứng minh broker đã ACK bền vững không?
3. Kafka `RecordMetadata.partition()/offset()` khác application `messageId` thế nào?
4. Khi `send()` ném exception trước khi Future được tạo, nên log ở đâu?
5. Tại sao timeout nên được diễn đạt `OUTCOME_UNKNOWN` trong nhiều tình huống?
6. Trong RabbitMQ, publisher ACK/NACK và consumer ACK khác nhau ra sao?
7. Vì sao publisher confirm ACK có thể chưa đủ để kết luận message được route tới queue đích?
8. `multiple=true` trong Rabbit publisher confirm có ý nghĩa gì?
9. Jakarta Messaging `CompletionListener.onCompletion` có luôn đồng nghĩa transaction commit không?
10. Tại sao không nên truyền raw payload hoặc `record.toString()` vào log DEBUG?
11. Callback có thể mất MDC từ thread gửi vì lý do gì? Nên làm gì?
12. Một message ID được retry ba lần có phải ba business events khác nhau không?
13. Outbox giúp tránh vấn đề dual-write như thế nào và còn cần idempotency vì sao?
14. Khi throughput cao, vì sao metric ACK rate có thể tốt hơn log INFO mỗi message?
15. Có thể suy ra consumer đã xử lý từ broker ACK tại producer không?
16. Vì sao đóng logging appender không tự drain pending network sends của producer?

**Gợi ý trả lời:** (1) send là async, Future còn pending; (2) không, acks=0 không đợi ACK broker; (3) vị trí broker vs ID ứng dụng; (4) catch ở caller; (5) phản hồi có thể mất nhưng broker đã nhận; (6) gửi tới broker vs consumer xử lý giao hàng; (7) routing/return là cơ chế riêng; (8) xác nhận một dải sequence number; (9) không, commit riêng; (10) rò PII/secret và tốn I/O; (11) MDC là thread-local, cần capture/propagate và clear; (12) cùng event logic với nhiều attempt; (13) ghi intent cùng transaction nhưng delivery có thể lặp; (14) giảm log storm/cardinality; (15) không; (16) hai subsystem có queue/contract khác nhau.

## 26. Tài liệu tham khảo chính thức

- [Apache Kafka — KafkaProducer Javadoc](https://kafka.apache.org/44/javadoc/org/apache/kafka/clients/producer/KafkaProducer.html): `send(ProducerRecord, Callback)`, `Future<RecordMetadata>`, lỗi synchronous/asynchronous và callback thread.
- [Apache Kafka — Callback Javadoc](https://kafka.apache.org/44/javadoc/org/apache/kafka/clients/producer/Callback.html): cách nhận metadata và exception từ thao tác send.
- [Apache Kafka — ProducerRecord](https://kafka.apache.org/44/javadoc/org/apache/kafka/clients/producer/ProducerRecord.html): key/value, topic, partition và timestamp.
- [RabbitMQ — Publisher Confirms Java Tutorial](https://www.rabbitmq.com/tutorials/tutorial-seven-java): `confirmSelect`, `addConfirmListener`, sequence number, `multiple` và callback/threading.
- [RabbitMQ — Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms): ý nghĩa ACK/NACK, durability, routing và điều kiện xác nhận.
- [Jakarta Messaging 3.1 — MessageProducer](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/messageproducer): `send`, `CompletionListener`, threading, close và transaction.
- [Jakarta Messaging 3.1 — Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html): quy tắc gửi asynchronous và hạn chế tại Jakarta EE web/EJB container.
- [Java SE 17 — CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): `handle`, `join`, điều phối completion.
- [Java SE 17 — java.util.logging.Logger](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html): level, logging parameters và handlers.
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): log có cấu trúc, dữ liệu nhạy cảm, sanitization và quản lý log.
