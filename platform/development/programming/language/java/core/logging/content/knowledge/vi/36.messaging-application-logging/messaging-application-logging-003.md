# Message identifier trong logging của ứng dụng message (Java Core)

## 1. Vì sao cần Message identifier?

Ứng dụng bất đồng bộ thường giao tiếp qua queue, topic hoặc broker. Khi producer gửi một thông điệp, consumer có thể xử lý sau vài giây hoặc vài giờ; khi xảy ra lỗi, broker có thể chuyển lại thông điệp cho consumer khác, đẩy sang dead-letter queue (DLQ) hoặc gửi lại sau retry. Log của producer và consumer vì vậy không còn liên kết đơn giản bằng một call stack Java.

**Message identifier (message ID)** là định danh giúp nhận diện một **thông điệp logic** hoặc một **record trong hệ thống message**, tùy hợp đồng của ứng dụng/broker. Khi thiết kế đúng, ID giúp trả lời:

- Thông điệp nào được tạo, publish, broker chấp nhận và consumer nhận?
- Consumer đã thấy **cùng message** hai lần (redelivery) hay hai message khác nhau có payload giống nhau?
- Bước xử lý nào thất bại, ở lần giao/attempt thứ mấy, và đã ack/commit hay chưa?
- Một reply, sự kiện phát sinh hoặc tác vụ downstream được tạo từ message nguồn nào?
- Log ở nhiều service, thread, pod và thời điểm khác nhau có thuộc cùng một thông điệp không?

Ví dụ các log có thể được nối bằng `messageId`:

~~~text
service=checkout event=message_created   messageId=msg-1001 correlationId=flow-42
service=checkout event=publish_confirmed messageId=msg-1001 destination=orders
service=billing  event=message_received  messageId=msg-1001 correlationId=flow-42 attempt=1
service=billing  event=processing_failed messageId=msg-1001 attempt=1
service=billing  event=message_received  messageId=msg-1001 correlationId=flow-42 attempt=2
service=billing  event=message_processed messageId=msg-1001 attempt=2
~~~

Hai lần nhận ở đây dùng **cùng message ID** nhưng khác `attempt`, bởi cùng thông điệp có thể được giao lại. Tuy nhiên, định danh giống nhau **không tự chứng minh** việc xử lý nghiệp vụ chỉ xảy ra một lần: điều đó cần hợp đồng idempotency và cơ chế lưu trạng thái riêng.

## 2. Phân biệt các loại ID thường bị nhầm

| Trường | Đơn vị mà trường nhận diện | Sinh ở đâu? | Có nên giữ qua retry/redelivery? |
| --- | --- | --- | --- |
| **`messageId`** (application logical ID) | Một message logic do ứng dụng định nghĩa | Thường producer hoặc outbox tạo trước publish | **Có** nếu đang gửi lại cùng message logic |
| **Broker record identity** | Một record cụ thể trong broker | Broker/transport cung cấp, ví dụ Kafka topic–partition–offset | Thường giữ cho cùng record được đọc lại; republish thành record mới sẽ có identity mới |
| **`deliveryId`/delivery tag** | Một lần giao message cụ thể | Broker, client hoặc application wrapper | **Không nhất thiết**; delivery mới có identity khác |
| **`correlationId`** | Một chuỗi xử lý/request/transaction hoặc cặp request–reply | Ứng dụng gốc hoặc giao thức | Thường giữ xuyên qua các bước cùng workflow |
| **`causationId`** | Message/event đã dẫn tới message mới | Producer ở bước downstream | Thường trỏ tới ID message cha |
| **`requestId`** | Một HTTP/gRPC request hoặc lệnh vào hệ thống | Gateway/entry point | Có thể truyền vào message như ngữ cảnh, nhưng không thay message ID |
| **`traceId` và `spanId`** | Distributed trace và từng span | Tracing framework/instrumentation | Dùng để kết nối quan sát, **không phải** khóa idempotency |
| **`idempotencyKey`** | Một tác vụ nghiệp vụ cần xử lý không lặp | Client/server theo contract nghiệp vụ | Tùy mục tiêu, thường bền qua retry cùng thao tác |
| **`eventId` của một log record** | Một sự kiện log riêng | Logging/ingest pipeline nếu có | Chỉ giữ khi chính log record đó được vận chuyển lại |

**Không có một ID nào thay thế tất cả.** Một request có thể phát nhiều message; một message có thể được giao nhiều lần; một consumer có thể sinh nhiều message con. Khi các trường này bị ghi chung dưới tên `id`, người điều tra khó biết có retry hợp lệ hay nhân bản ngoài ý muốn.

Ví dụ chuỗi quan hệ:

~~~text
HTTP request: requestId=req-1, correlationId=flow-42
   |
   +--> Message A: messageId=msg-A, causationId=req-1
          |
          +--> delivery 1 của A -> thất bại
          +--> delivery 2 của A -> thành công
          |
          +--> Message B: messageId=msg-B,
                          causationId=msg-A,
                          correlationId=flow-42
~~~

Message B **phải có ID mới** nếu nó là một thông điệp logic mới. Nó giữ `correlationId` để tham gia cùng workflow, và mang `causationId=msg-A` để ghi quan hệ nhân quả. Nếu chỉ republish lại A do timeout/ACK không chắc chắn, nên giữ **logical message ID của A**; broker có thể gán **record identity mới** cho bản republish đó.

## 3. Chọn Message ID có phạm vi và hợp đồng rõ ràng

Một contract hữu ích cần xác định:

1. **Ai phát ID?** Thường producer tạo trước khi gửi, rồi ghi cả ID vào log và header/envelope. Không đặt điều kiện phải chờ consumer nhận mới sinh ID, vì mất thông tin nối từ phía publish.
2. **Độ duy nhất ở phạm vi nào?** Một broker, một tenant, một cluster, một môi trường, một workflow hay toàn hệ thống? Nếu dùng `messageId` làm dedup key đa hệ thống, cần định nghĩa namespace/source hoặc đủ tính duy nhất.
3. **Vòng đời và phiên bản:** ID được giữ qua retry, republish, DLQ/re-drive hay thay khi tạo sự kiện nghiệp vụ mới? Phân biệt với delivery ID để không nhầm.
4. **Tính bất biến:** sau khi message được phát, ID của cùng thông điệp logic không được thay tùy tiện trong consumer.
5. **Định dạng:** chuỗi an toàn để log, header và index, ví dụ UUID v4, ULID hoặc ID được tạo từ một hệ thống phân phối duy nhất. Đừng giả định mọi định dạng bảo đảm duy nhất tuyệt đối; collision, lỗi seed hay lỗi triển khai vẫn cần xem xét theo quy mô.
6. **Ngữ nghĩa bảo mật:** ID **không phải** chứng cứ authentication, quyền tenant, token truy cập hay secret. Người dùng có thể gửi ID giả; phải xác thực nguồn, kiểm tra tenant và ủy quyền độc lập.
7. **Cardinality:** ID của mỗi message gần như luôn khác nhau; lưu dưới dạng **log field** phù hợp cho tra cứu, nhưng không nên đưa mỗi `messageId` thành label của metric như Prometheus.

Không suy ID chỉ từ `payload.hashCode()` hoặc SHA-256 của payload: hai message hợp lệ có thể mang cùng payload, input có thể chứa dữ liệu nhạy cảm, và hash thuần không thể hiện đúng danh tính của từng lần publish. Nếu nghiệp vụ cần **idempotency key** dựa vào yêu cầu, hãy xây riêng contract canonicalization và thời hạn của key.

### Tạo ID ở producer Java

Với Java 17, cách đơn giản là `UUID.randomUUID()`:

~~~java
import java.util.UUID;

// Snippet tại thời điểm tạo một message logic.
String logicalMessageId = UUID.randomUUID().toString();
String correlationId = incomingCorrelationId != null
        ? incomingCorrelationId
        : UUID.randomUUID().toString();

MessageEnvelope envelope = new MessageEnvelope(
        logicalMessageId, correlationId, "order.created", payload);
publisher.publish(envelope);
~~~

Đoạn này **không phải chương trình độc lập**: `MessageEnvelope`, `publisher`, `payload` và `incomingCorrelationId` là thành phần do ứng dụng định nghĩa. `UUID.randomUUID()` sinh UUID version 4 từ bộ tạo số ngẫu nhiên đủ mạnh cho mục đích phổ biến, nhưng không có cơ chế chứng minh tuyệt đối không collision. Nếu payload/tenant hoặc header đầu vào chưa được kiểm tra, không dùng correlation ID do client cung cấp làm căn cứ bảo mật.

**Bước quan trọng:** tạo `logicalMessageId` **một lần khi tạo envelope**, lưu nó trong outbox nếu cần giao bền vững. Khi publish retry do mạng lỗi, lấy lại **cùng envelope/ID**; đừng gọi `randomUUID()` mỗi lần retry nếu đang muốn nhận diện cùng logical message.

## 4. Lưu message ID ở đâu để producer và consumer cùng đọc được?

Message ID nên nằm ở **envelope hoặc metadata/header được giao qua transport**, với tên field thống nhất giữa các service. Không chỉ gắn nó vào MDC tại producer: MDC nằm trong bộ nhớ thread của producer và không tự đi theo message sang consumer.

Ví dụ envelope JSON (minh họa, không chứa dữ liệu thật):

~~~json
{
  "messageId": "msg-1001",
  "correlationId": "flow-42",
  "causationId": "cmd-9",
  "type": "order.created",
  "schemaVersion": 1,
  "occurredAt": "2026-11-10T08:00:00Z",
  "tenantId": "tenant-a",
  "payload": {
    "orderRef": "order-demo-7"
  }
}
~~~

Có hai cách triển khai thông thường:

- **Header của broker:** `message-id`, `correlation-id`, `traceparent` (nếu tracing), và các trường ứng dụng trong headers. Phù hợp khi không muốn đưa metadata vào phần body, nhưng phải biết khả năng bảo toàn header của connector/broker/bridge và giới hạn độ dài/kiểu dữ liệu.
- **Envelope của ứng dụng:** metadata đứng cùng payload theo schema đã version. Phù hợp khi cần di chuyển giữa nhiều broker hoặc lưu outbox; phải validate, không serialize object tùy tiện và không ghi nguyên body lên log.

Có thể giữ cả ID trong envelope và trong header để thuận tiện, nhưng **phải có một nguồn sự thật** và kiểm tra trùng/không nhất quán: nếu `header.messageId` khác `body.messageId`, nên xử lý lỗi schema/tampering thay vì chọn ngẫu nhiên rồi ghi lẫn. Không cấp quyền truy cập chỉ vì ID hoặc tenant header có mặt.

### Tại sao ID không nên nằm trong message text?

~~~java
logger.info("received {}", message.toString());
~~~

Nếu `toString()` chứa cả payload, log có thể lộ email, token hoặc PII; nếu format thay đổi, tìm ID bằng substring rất mong manh. Ưu tiên message rõ sự kiện và trường có cấu trúc:

~~~java
// Snippet dùng SLF4J trong ứng dụng thực.
logger.info("event=message_received messageId={} correlationId={} type={}",
        messageId, correlationId, messageType);
~~~

Các biến ở trên cần đã được lấy/kiểm tra từ envelope. Không cần dump payload chỉ để có định danh thông điệp.

## 5. Kafka: topic + partition + offset không đồng nghĩa application message ID

Trong Kafka, `ConsumerRecord<K,V>` có `topic()`, `partition()`, `offset()`, `key()`, `headers()` và metadata khác. **Topic + partition + offset** xác định vị trí một **record trong log Kafka** ở phạm vi cluster/namespace đã biết. Nó rất hữu ích để tìm record consumer đã nhận hoặc debug việc commit offset.

Kafka không tự cung cấp một **logical application messageId chung, bắt buộc**, dùng để nhận diện cùng thông điệp qua các lần republish/biến đổi. Kafka record key cũng **không mặc nhiên là message ID**: key thường dùng để quyết định partition hoặc nhóm record theo entity; có thể có nhiều record cùng key.

Ví dụ code Kafka client **dạng snippet**, cần dependency `org.apache.kafka:kafka-clients` và `ConsumerRecord` đã được consumer nhận:

~~~java
import org.apache.kafka.clients.consumer.ConsumerRecord;

static void logRecord(ConsumerRecord<String, byte[]> record) {
    // Chỉ minh họa: logger, decodeHeader là helper của ứng dụng.
    String messageId = decodeHeader(record.headers(), "message-id");
    logger.info(
        "event=kafka_record_received topic={} partition={} offset={} messageId={}",
        record.topic(), record.partition(), record.offset(), messageId);
}
~~~

Đây **không phải chương trình độc lập**: `logger` và `decodeHeader` chưa được định nghĩa. Header Kafka có thể chứa nhiều giá trị cho cùng một key và nội dung là byte array; helper phải định rõ dùng header nào, charset nào, giới hạn kích thước nào, và xử lý thiếu/không hợp lệ ra sao. Không lấy `new String(header.value())` với default charset và tin rằng mọi producer cùng mã hóa.

**Ví dụ nhận diện:**

~~~text
Kafka record: topic=orders.events partition=2 offset=105 messageId=msg-1001
Consumer A đọc lại record 105 sau restart:
              topic=orders.events partition=2 offset=105 messageId=msg-1001
Producer republish cùng message logic:
              topic=orders.events partition=2 offset=118 messageId=msg-1001
~~~

Trong ví dụ, lần đọc lại record cũ có **cùng offset**; lần republish tạo **record mới với offset khác**, nhưng nếu ứng dụng giữ header thì cùng `messageId`. Việc consumer thấy cùng message ID chưa xác định nó thuộc cùng record hay đã được publish lại; khi điều tra hãy giữ **cả broker record identity và logical message ID**. Offset không phải global ID xuyên topic/partition/cluster và không là khóa idempotency thích hợp cho mọi kiểu republish.

Với transaction/idempotent producer của Kafka, ngữ nghĩa giao tin còn phụ thuộc cấu hình producer/consumer, isolation, commit offset và ranh giới side effect ngoài Kafka. Không khẳng định “Kafka đảm bảo exactly-once cho mọi database/email/http call” chỉ từ việc có một offset hoặc ID.

## 6. RabbitMQ: message_id khác delivery tag

Trong RabbitMQ AMQP 0-9-1, `message_id` và `correlation_id` là **message properties tùy chọn do publisher đặt**. RabbitMQ **không tự bắt buộc tạo message_id** cho mọi thông điệp. Vì vậy ứng dụng muốn dùng ID ổn định nên tạo nó tại producer và đặt vào properties/header.

Ngoài message properties, khi broker giao một message cho consumer còn có **delivery metadata**:

| Thuộc tính | Bản chất | Lưu ý |
| --- | --- | --- |
| `message_id` | ID message do publisher quy ước | Có thể thiếu; tính duy nhất phụ thuộc application contract |
| `correlation_id` | Liên kết request và reply/workflow | Không bắt buộc bằng message_id |
| `deliveryTag` | Mã delivery dùng cho ACK/NACK trên **channel** | **Chỉ có nghĩa trong channel đó**; không phải global message ID |
| `redelivered` | Cờ cho biết delivery có thể là lần gửi lại | Hữu ích để chẩn đoán, **không đủ** để quyết định idempotency |
| `exchange`, `routingKey`, `consumerTag` | Ngữ cảnh route/consumer | Không thay logical message ID |

Ví dụ code publisher **snippet**, cần RabbitMQ Java client và `Channel` có sẵn:

~~~java
import com.rabbitmq.client.AMQP;
import java.nio.charset.StandardCharsets;
import java.util.UUID;

String messageId = UUID.randomUUID().toString();
AMQP.BasicProperties props = new AMQP.BasicProperties.Builder()
        .messageId(messageId)
        .correlationId("flow-42")
        .contentType("application/json")
        .deliveryMode(2)
        .build();

channel.basicPublish("orders.exchange", "orders.created",
        props, jsonBody.getBytes(StandardCharsets.UTF_8));
~~~

`channel` và `jsonBody` thuộc ứng dụng; đây không phải file chạy độc lập. `deliveryMode(2)` thể hiện mong muốn persistent message trong bối cảnh phù hợp, nhưng **không tự bảo đảm** publisher biết message đã lưu an toàn. Dùng publisher confirms và kiểm tra routing/queue durability theo thiết kế. Khi retry publish cùng logical message sau lỗi ACK không chắc chắn, cần tái sử dụng `messageId`, không sinh ID mới mỗi lần phát lại.

Ở consumer, log `message_id`, `deliveryTag` (kèm channel/consumer context), `redelivered`, queue và attempt nếu có. **Không dùng delivery tag làm idempotency key xuyên channel**: tag có thể được dùng lại ở các channel khác nhau hoặc không giữ nguyên qua redelivery.

## 7. Jakarta Messaging / JMS: message ID do provider gán

Trong Jakarta Messaging (JMS), **`JMSMessageID`** là giá trị được **provider gán khi gửi**; theo đặc tả nó bắt đầu bằng `ID:` và tính duy nhất có phạm vi do provider xác định. Vì producer có thể chưa biết giá trị cuối trước khi gửi, nếu ứng dụng cần ID xuyên nhiều broker hoặc trước send, nên có **application logical ID riêng** trong property/envelope.

`JMSCorrelationID` là thuộc tính riêng, thường do ứng dụng đặt để liên kết request với reply hoặc một thông điệp với thông điệp khác. `JMSRedelivered` cho biết provider đánh dấu message được giao lại; không thay cơ chế idempotency.

Ví dụ consumer **snippet** cần `jakarta.jms.Message`:

~~~java
import jakarta.jms.Message;

static void auditDelivery(Message message) throws Exception {
    String providerId = message.getJMSMessageID();
    String correlationId = message.getJMSCorrelationID();
    boolean redelivered = message.getJMSRedelivered();

    // Logger do ứng dụng định nghĩa.
    logger.info(
        "event=jms_message_received providerMessageId={} correlationId={} redelivered={}",
        providerId, correlationId, redelivered);
}
~~~

Đây là snippet **không chạy độc lập** vì `logger` chưa được định nghĩa và cần JMS API/provider. Cũng không nên ép `JMSMessageID` thành chuỗi application message ID có định dạng UUID; nó thuộc namespace/provider của JMS. Khi nối log từ hai provider, ghi thêm `broker/system` hoặc dùng application-level ID riêng.

## 8. Java 17 runnable: một message ID, hai lần giao

Để quan sát rõ sự khác nhau giữa **message ID** và **attempt**, chương trình dưới đây chỉ dùng **JDK 17**, không phụ thuộc Kafka/RabbitMQ/JMS. Nó mô phỏng một message envelope được nhận hai lần. Mỗi lần nhận có attempt riêng, nhưng **messageId giữ nguyên**.

Tạo file **`MessageIdentifierDemo.java`**:

~~~java
import java.util.HashSet;
import java.util.Set;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class MessageIdentifierDemo {
    record Envelope(
            String messageId,
            String correlationId,
            String causationId,
            String type) {}

    private static final Logger LOG =
            Logger.getLogger("demo.messaging.ids");

    // Handler thử nghiệm chỉ in message để stdout không phụ thuộc thời gian.
    private static final class PlainHandler extends Handler {
        @Override
        public void publish(LogRecord record) {
            if (isLoggable(record)) {
                System.out.println(record.getMessage());
            }
        }

        @Override
        public void flush() {
            // Không có bộ đệm I/O.
        }

        @Override
        public void close() {
            // Không giữ tài nguyên ngoài.
        }
    }

    private static void receive(
            Envelope message, int attempt, Set<String> completed) {

        LOG.info("event=received messageId=" + message.messageId()
                + " correlationId=" + message.correlationId()
                + " causationId=" + message.causationId()
                + " attempt=" + attempt);

        // Chỉ là mô phỏng in-memory, KHÔNG phải idempotency production.
        if (!completed.add(message.messageId())) {
            LOG.info("event=duplicate_skipped messageId="
                    + message.messageId());
            return;
        }

        LOG.info("event=processed messageId=" + message.messageId());
    }

    public static void main(String[] args) {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.ALL);

        PlainHandler handler = new PlainHandler();
        handler.setLevel(Level.ALL);
        LOG.addHandler(handler);

        try {
            Envelope message = new Envelope(
                    "msg-1001", "flow-42", "cmd-9", "order.created");
            Set<String> completed = new HashSet<>();

            receive(message, 1, completed);
            receive(message, 2, completed);

            System.out.println("logical_messages=" + completed.size());
        } finally {
            LOG.removeHandler(handler);
            handler.close();
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 MessageIdentifierDemo.java
java MessageIdentifierDemo
~~~

**Stdout xác định:**

~~~text
event=received messageId=msg-1001 correlationId=flow-42 causationId=cmd-9 attempt=1
event=processed messageId=msg-1001
event=received messageId=msg-1001 correlationId=flow-42 causationId=cmd-9 attempt=2
event=duplicate_skipped messageId=msg-1001
logical_messages=1
~~~

Điểm cần hiểu:

1. `msg-1001` là ID demo cố định để stdout có thể kiểm chứng, **không phải cách tạo ID thực**. Producer thật có thể dùng `UUID.randomUUID()` hoặc ID của domain.
2. Hai dòng `event=received` tương ứng **hai delivery/attempt**, không phải hai message logic. Cả hai có `messageId=msg-1001`.
3. `correlationId=flow-42` gắn với workflow; `causationId=cmd-9` mô tả quan hệ đến command trước đó.
4. `HashSet` chỉ chứng minh ý tưởng nhận diện ID đã thấy **trong một process, một lần chạy**. Nó không bền qua restart, không có concurrency control, không kết nối giao dịch thật, không có expire/retention, và cập nhật set trước khi một side effect thực sự thành công có thể gây **mất xử lý** khi crash. **Không dùng nguyên mã này cho cơ chế exactly-once hoặc chống thanh toán trùng ở production.**
5. `PlainHandler` giúp minh họa cách record đi qua `java.util.logging` nhưng không đưa timestamp/thread ngẫu nhiên vào stdout; ứng dụng thực dùng handler/layout có cấu trúc, quản lý lifecycle và mức log phù hợp.

### Tại sao không “mỗi lần consume một UUID”?

Nếu consumer tạo `UUID.randomUUID()` mỗi lần nhận để dùng làm `messageId`, redelivery của cùng message sẽ có hai ID khác nhau và không nối được lịch sử. Consumer có thể tạo **delivery processing ID** riêng cho từng lần nhận, nhưng phải giữ **original messageId** từ envelope/broker.

## 9. Dùng MDC để nối log trong một lần xử lý message

Với SLF4J + backend hỗ trợ MDC (ví dụ Logback), ứng dụng có thể đưa `messageId` và `correlationId` vào **Mapped Diagnostic Context** để những log bên trong hàm xử lý cùng mang thông tin. **MDC là thread-local context**, không tự đi xuyên broker.

Ví dụ helper **snippet**, cần `org.slf4j.MDC`, không phải JDK-only program:

~~~java
import java.util.Map;
import org.slf4j.MDC;

static void withMessageContext(
        String messageId, String correlationId, Runnable processing) {

    Map<String, String> previous = MDC.getCopyOfContextMap();
    try {
        MDC.put("messageId", messageId);
        if (correlationId == null) {
            MDC.remove("correlationId");
        } else {
            MDC.put("correlationId", correlationId);
        }
        processing.run();
    } finally {
        if (previous == null) {
            MDC.clear();
        } else {
            MDC.setContextMap(previous);
        }
    }
}
~~~

Đây là phương thức minh họa trong class ứng dụng; caller phải validate `messageId` không null/blank, giới hạn ký tự/độ dài và không đưa token hay PII vào. Khi consumer lấy message, nó đọc metadata từ envelope/broker, thiết lập MDC trong `try/finally`, xử lý và dọn. Cần giữ `previous` để không làm mất context hợp lệ của lời gọi lồng nhau.

Ví dụ pattern Logback (snippet cấu hình appender đã có):

~~~xml
<encoder>
    <pattern>%d{ISO8601} [%thread] %-5level msg=%X{messageId} corr=%X{correlationId} %logger - %msg%n%ex</pattern>
</encoder>
~~~

`%X{messageId}` chỉ hiện giá trị **đã được code đặt vào MDC**. Pattern không tạo ID và không propagate ID tự động. Bên ngoài scope (startup/job scheduler không có message) có thể không có các field này; đừng tự gán một messageId ngẫu nhiên cho toàn bộ hệ thống chỉ để trường không trống.

### Worker thread và async boundary

Khi message handler giao việc cho `ExecutorService` hoặc `CompletableFuture`, task có thể chạy trong thread khác. Nếu chỉ đặt MDC ở consumer thread, worker có thể mất context; nếu không dọn, task của message B có thể mang ID của message A.

Mẫu capture/restore **snippet**:

~~~java
import java.util.Map;
import org.slf4j.MDC;

static Runnable withCapturedMdc(Runnable task) {
    Map<String, String> captured = MDC.getCopyOfContextMap();
    return () -> {
        Map<String, String> original = MDC.getCopyOfContextMap();
        try {
            if (captured == null) {
                MDC.clear();
            } else {
                MDC.setContextMap(captured);
            }
            task.run();
        } finally {
            if (original == null) {
                MDC.clear();
            } else {
                MDC.setContextMap(original);
            }
        }
    };
}
~~~

Gọi `withCapturedMdc(...)` **tại thời điểm submit**, khi context của message gốc còn tồn tại. Nếu worker pool đã có context cũ do code trước rò rỉ, việc restore `original` không tự sửa lỗi đó; hệ thống cần lifecycle rõ để mỗi task độc lập kết thúc với context phù hợp.

Khi dùng async logger/appender, filter và encoder phải đọc context snapshot trên **log event** (hoặc context carrier được backend hỗ trợ), không lấy `MDC.get("messageId")` từ thread writer và cho rằng nó thuộc message gốc.

## 10. Message ID và distributed tracing

Message ID liên kết các **lần gửi/nhận cùng message**, trong khi trace ID nối các span thực thi có quan hệ qua service và thời gian. Cả hai hữu ích và không thay thế nhau.

Một publish có thể tạo message, consumer xử lý rồi publish message khác. Để giữ trace, instrumentations thường truyền **W3C trace context** như `traceparent` trong message headers/envelope và consumer **extract** trước khi tạo span mới. OpenTelemetry có semantic conventions cho messaging spans và quy tắc về producer/consumer context; không nên coi việc truyền một chuỗi `correlationId` là đủ tạo trace liên service.

~~~text
traceId=trace-1
  producer span: publish A, messageId=msg-A
  consumer span: process A, messageId=msg-A
  producer span: publish B, messageId=msg-B, causationId=msg-A
  consumer span: process B, messageId=msg-B
~~~

Đây là mô hình minh họa, không phải định dạng `traceparent` thật. Trace parent/links có thể khác nhau tùy messaging API và instrumentation; đặc biệt batch receive, redelivery hay fan-out có nhiều ngữ cảnh. Đừng tự chế giá trị `traceparent` bằng cách ghép `messageId`. Và **traceId không phải khóa idempotency**: nhiều attempt/span có thể xử lý cùng message.

Khi thiết kế structured logging, có thể đưa cả `messageId`, `correlationId`, `traceId`, `spanId` nhưng phải bảo đảm không tạo thêm dữ liệu nhạy cảm không cần thiết và không bùng nổ kích thước mỗi dòng.

## 11. Idempotency, redelivery và tính đúng đắn nghiệp vụ

Message ID giúp **nhận ra message đã gặp**, nhưng tự nó không chặn xử lý lặp. Trong thực tế, message broker thường giao ít nhất một lần (at-least-once) khi có retry/reconnect, vì vậy side effect có thể diễn ra rồi consumer crash trước ACK/commit.

~~~text
Consumer nhận msg-1001
  -> ghi đơn hàng vào DB thành công
  -> crash trước khi ACK
Broker giao lại msg-1001
  -> nếu không có idempotency: ghi/trừ tiền lần hai
~~~

Để xử lý đúng, thường phải có **inbox/deduplication store bền vững** hoặc unique constraint gắn với một **processing scope** rõ ràng, và commit trạng thái đã xử lý **cùng transaction** với side effect ở nơi có thể bảo đảm atomicity. Ví dụ uniqueness của `(consumerName, messageId)` hoặc `(businessOperationType, idempotencyKey)`, tùy hợp đồng. Dùng `messageId` làm khóa toàn cục cho mọi consumer có thể sai: hai consumer khác nhau có thể **đều phải** xử lý cùng message.

Một flow tham khảo:

~~~text
Receive message
    |
    v
Validate schema, ID, tenant và quyền nguồn
    |
    v
Transaction: kiểm tra claim/idempotency key
    |
    +-- Already successfully processed -> không áp side effect thêm
    |
    +-- Chưa xử lý -> side effect + ghi trạng thái processed
    |
    v
Commit DB transaction thành công
    |
    v
ACK/commit broker progress theo contract
~~~

Không thể tự kết luận “exactly-once toàn hệ thống” chỉ vì đã ghi log và có một message ID. Với email, webhook, payment gateway hoặc DB ở hệ thống khác, một transaction nội bộ không nhất thiết bao trùm side effect ngoài; cần thêm idempotent API, outbox hoặc cơ chế saga/compensation tùy trường hợp.

**Quan hệ giữa các ID khi retry:**

- **Broker redeliver cùng message:** giữ `logicalMessageId`; tăng `deliveryAttempt` nếu ứng dụng/broker có metadata đủ tin cậy; delivery tag/offset có semantics của riêng transport.
- **Producer retry publish do confirm timeout:** cố giữ cùng logical ID, chấp nhận broker có thể tạo bản record mới; dedup ở consumer/storage theo contract.
- **Đưa vào DLQ:** giữ `originalMessageId` và metadata lỗi/source; nếu DLQ là một message wrapper mới, có thể có `dlqMessageId` riêng, không làm mất ID nguồn.
- **Re-drive/repair:** nếu xử lý lại cùng message, giữ identity nguồn và ghi `replayId`/`replayAttempt` riêng; nếu tạo một business event mới thực sự, dùng ID mới và `causationId` trỏ tới ID cũ.
- **Tạo message downstream:** tạo `messageId` mới, giữ `correlationId` phù hợp và `causationId` trỏ tới message nguồn.

## 12. Log tại những mốc nào?

Một message thường có vòng đời sau. Chỉ log ở những mốc đủ ý nghĩa; tránh INFO cho từng item nếu throughput lớn và đã có metrics/traces.

| Mốc | Event gợi ý | Metadata hữu ích |
| --- | --- | --- |
| Envelope được tạo | `message_created` | messageId, type, correlationId |
| Publish được yêu cầu | `publish_requested` | messageId, destination, producerInstance |
| Broker confirm/ack publish | `publish_confirmed` | messageId, brokerRecordIdentity nếu có |
| Consumer nhận | `message_received` | messageId, consumer, destination, delivery metadata |
| Bắt đầu xử lý | `processing_started` | messageId, attempt, traceId |
| Hoàn tất nghiệp vụ | `processing_succeeded` | messageId, processing outcome, duration |
| Lỗi có thể retry | `processing_retry_scheduled` | messageId, attempt, reasonCode, retry policy |
| Bỏ xử lý vì đã hoàn tất | `duplicate_ignored` | messageId, consumer scope |
| ACK/commit broker progress | `message_acknowledged` | messageId, offset/deliveryTag (đúng phạm vi) |
| Chuyển DLQ | `message_dead_lettered` | originalMessageId, reasonCode, source/destination |

**Không đánh đồng “processed” và “acked”.** Nghiệp vụ có thể commit thành công nhưng ACK thất bại; lần giao lại không nhất thiết là một xử lý nghiệp vụ mới. Tương tự, “publish requested” không chứng minh broker đã nhận; nên log confirm hoặc kết quả giao khi API/transport hỗ trợ.

Ví dụ một dòng có cấu trúc:

~~~json
{
  "event": "message_processed",
  "messageId": "msg-1001",
  "correlationId": "flow-42",
  "causationId": "cmd-9",
  "transport": "kafka",
  "destination": "orders.events",
  "partition": 2,
  "offset": 105,
  "consumer": "billing-worker",
  "attempt": 2,
  "outcome": "success",
  "durationMs": 27
}
~~~

JSON này **chỉ minh họa**. Ở môi trường thật, field `offset`/`partition` chỉ có nghĩa với broker phù hợp; `attempt=2` phải đến từ metadata theo chính sách, không nên tự đoán từ `redelivered=true`. Nếu log gồm nhiều tenant, `tenantId` phải lấy từ nguồn được xác thực, không dùng client-supplied header trực tiếp làm ranh giới truy cập.

## 13. Bảo mật, dữ liệu cá nhân và input không đáng tin

Message headers do producer gửi là dữ liệu **có thể không đáng tin**; service khác hoặc client bên ngoài có thể truyền một ID tùy ý. Trước khi đưa vào log/index/MDC:

- **Giới hạn kích thước và tập ký tự**, ví dụ UUID hoặc chuỗi ASCII cho phép; từ chối newline, carriage return, ký tự điều khiển nhằm giảm log injection.
- **Không tin ID là bằng chứng authentication/authorization**. Một attacker có thể biết messageId và tự gắn nó vào message giả; quyền tenant phải được xác thực ở layer nghiệp vụ.
- **Không dùng token truy cập, cookie, email, số điện thoại hoặc số giấy tờ làm messageId.** ID ổn định có thể cho phép liên kết lịch sử, nên vẫn cần retention/RBAC và đánh giá khả năng nhận diện.
- **Không dump toàn bộ headers/body** để lấy một ID. Header có thể chứa `Authorization`, JWT, PII, payload hoặc routing secret.
- **Giữ schema nhất quán và tránh lỗi format:** định danh thiếu không được âm thầm biến thành `"null"` có thể trộn nhiều message; tách `missing_message_id` để phát hiện sự cố.
- **Không tạo nhãn metric cho từng messageId**. Sử dụng metrics theo event type, queue, consumer, outcome, reasonCode (các tập giá trị hữu hạn). Tra cứu theo messageId thuộc log/traces có index và retention phù hợp.

Một đoạn code an toàn hơn phải xử lý null và control characters **trước** khi đưa ID vào log; không dựa vào việc `logger.info("id={}", id)` tự sanitize input. Khi không thể xác minh ID nguồn, có thể dùng ID tạm cho một **delivery** (đặt tên `deliveryLogId`), nhưng không giả vờ đó là logical messageId đã được xác thực; ghi cảnh báo về thiếu metadata và xử lý theo policy.

## 14. Kiểm thử message ID và quan sát được

### Test chức năng

1. **Producer tạo một logical message:** ID tồn tại, đúng format và không thay qua retry publish cùng envelope.
2. **Hai message khác nhau:** ID khác nhau theo contract (với UUID ngẫu nhiên dùng test không dựa tuyệt đối vào tính duy nhất; có thể inject ID generator deterministic).
3. **Redelivery:** cùng messageId ở hai attempt, log chứa `attempt`/delivery metadata phân biệt lần giao.
4. **Kafka:** cùng record đọc lại giữ topic/partition/offset; republish tạo record identity khác nhưng application message ID có thể giữ.
5. **RabbitMQ:** message_id tùy chọn, correlation_id riêng; deliveryTag channel-scoped; không dùng tag làm global ID.
6. **JMS:** JMSMessageID do provider gán, JMSCorrelationID do client liên kết; không giả định JMSMessageID là UUID.
7. **Consumer fan-out:** message downstream nhận ID mới, causation trỏ message cũ, correlation giữ theo workflow.
8. **MDC:** trên thread pool một worker, xử lý message A rồi B rồi task thiếu message, xác nhận không rò ID.
9. **DLQ/re-drive:** vẫn tìm được originalMessageId sau chuyển đổi/replay; metadata retry/attempt không bị xóa.
10. **Idempotency:** side effect không lặp lại với cùng message trong cùng processing scope, kể cả crash sau commit nhưng trước ACK (cần test integration với durable store/broker).
11. **Input ác ý:** ID chứa ký tự xuống dòng, quá dài, sai tenant, thiếu/mâu thuẫn giữa header–body; phải validate hoặc từ chối đúng policy.
12. **Performance:** thông điệp có throughput cao không làm index/metric cardinality và dung lượng log bùng nổ vì ghi payload/headers.

### Bảng chẩn đoán

| Hiện tượng | Nguyên nhân thường gặp | Cách sửa |
| --- | --- | --- |
| Producer có ID, consumer log trống | Header/envelope không được truyền, sai key/charset | Chuẩn hóa schema, assert trong integration test |
| Cùng message sau retry có ID khác | Retry tạo envelope/UUID mới | Sinh một lần, lưu ID trong outbox/message |
| Kafka offset khác nhưng application ID giống | Republish thành record mới | Log cả logical ID và topic/partition/offset |
| RabbitMQ deliveryTag giống giữa hai channel | Tag chỉ scoped trong channel | Không dùng tag làm global message ID |
| Log A mang ID B trong worker pool | MDC sót hoặc propagation sai | Capture/restore, dọn context từng task |
| Log thấy một message xử lý hai lần | Redelivery sau crash/ACK không chắc chắn | Durable dedup + idempotent side effect |
| Không nối được reply với request | Không đặt correlation ID hoặc đặt sai | Quy ước request–reply, giữ correlation khi reply |
| DLQ không truy ngược source | Wrapper mới làm mất originalMessageId | Bảo toàn source metadata/causation |
| Dashboard đếm một lần retry thành nhiều failure | Đếm từng delivery/ERROR như một logical operation | Đếm theo outcome/idempotency scope, phân biệt attempt |
| Message ID làm lộ dữ liệu | Dùng email/token/PII làm ID | Sinh ID độc lập, giữ log an toàn và access control |
| Trace không nối được dù có messageId | Message ID không phải trace context | Propagate traceparent/context theo instrumentation |

## 15. Quy trình triển khai gọn cho ứng dụng Java

1. **Định nghĩa contract**: `messageId` nhận diện logical message trong scope nào; `correlationId` cho workflow; `causationId` cho quan hệ cha–con; broker record/delivery metadata là trường riêng.
2. **Tạo ID tại producer** và đưa vào envelope/header, lưu trong outbox nếu dùng durable publish. Không thay messageId trong retry cùng message.
3. **Validate ở consumer**: ID đủ tin cậy/đúng format, schema version phù hợp, tenant/source được xác thực. Không lấy ID thay quyền truy cập.
4. **Log mốc rõ ràng**: created, publish requested/confirmed, received, processing outcome, retry, ACK/commit, DLQ. Phân biệt các trạng thái thành công khác nhau.
5. **Gắn MDC theo scope** của message và dọn trong `finally`; truyền snapshot qua async boundary, không để rò messageId giữa thread/tác vụ.
6. **Giữ broker identity** như Kafka topic/partition/offset, RabbitMQ delivery tag + channel hoặc JMS provider ID, nhưng không coi tất cả tương đương logical message ID.
7. **Thiết kế idempotency riêng** với transaction/inbox/unique constraint và side-effect contract; messageId chỉ là một đầu vào giúp nhận diện.
8. **Kiểm thử redelivery, republish, DLQ và multi-consumer**, cả khi crash/ACK thất bại và khi message thiếu header.
9. **Bảo vệ log**: không ghi payload/PII/secret, giới hạn ID đầu vào, RBAC/retention, tránh metrics label cardinality cao.
10. **Đo và cảnh báo**: tỉ lệ thiếu ID, duplicate delivery, retry, DLQ, lag/offset commit và chênh lệch publish–ack theo backend.

**Ghi nhớ:** Message identifier giúp truy vết **thông điệp logic**; broker record identity giúp định vị **record trong transport**; delivery metadata định danh **lần giao**; correlation/causation/trace nối **các bước của workflow**. Giữ các vai trò này rõ ràng, đặc biệt qua retry và redelivery, sẽ giúp log trả lời được điều gì đã xảy ra mà không đánh đồng nhiều lần giao với nhiều message nghiệp vụ.

### Tài liệu tham khảo chính thức

- Apache Kafka — [ConsumerRecord API: topic, partition, offset, headers](https://kafka.apache.org/42/javadoc/org/apache/kafka/clients/consumer/ConsumerRecord.html), [Documentation](https://kafka.apache.org/documentation/).
- RabbitMQ — [Consumers: message properties và delivery metadata](https://www.rabbitmq.com/docs/consumers), [Publishers: message properties, publisher confirms](https://www.rabbitmq.com/docs/publishers).
- Jakarta Messaging — [Message header fields và JMSMessageID/JMSCorrelationID](https://jakarta.ee/learn/docs/jakartaee-tutorial/current/messaging/jms-concepts/jms-concepts.html), [Messaging 3.1 specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html).
- OpenTelemetry — [Messaging semantic conventions và context propagation](https://opentelemetry.io/docs/specs/semconv/messaging/messaging-spans/), [W3C Trace Context](https://www.w3.org/TR/trace-context/).
- Java 17 — [UUID](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/UUID.html), [java.util.logging.Logger](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html).
