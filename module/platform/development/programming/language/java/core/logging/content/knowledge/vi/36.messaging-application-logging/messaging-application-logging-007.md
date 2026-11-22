# Dead-letter message trong ứng dụng message Java

## 1. Dead-letter message là gì?

Trong ứng dụng dùng message broker, **dead-letter message** là một message không thể được xử lý thành công theo chính sách hiện tại và được **chuyển sang một nơi xử lý riêng** thay vì tiếp tục quay vòng vô hạn trên luồng chính. Nơi nhận thường gọi là **dead-letter queue (DLQ)** hoặc **dead-letter topic (DLT)**, tùy hệ thống.

Ví dụ: ứng dụng nhận sự kiện `OrderConfirmed`, nhưng schema của message thiếu một trường bắt buộc. Việc chạy lại cùng dữ liệu không làm schema tự đúng lên. Nếu liên tục nhận lại, ghi exception và retry vô hạn, consumer sẽ tốn tài nguyên, log bị spam và những message hợp lệ phía sau có thể bị chậm. Chuyển message lỗi sang DLQ giúp **cách ly vấn đề** để người vận hành hoặc một quy trình sửa lỗi xử lý tiếp.

~~~text
                Producer
                   |
                   v
           Main queue / topic
                   |
                   v
               Consumer
                   |
             Process message
                   |
        +----------+-----------+
        |                      |
     Success                 Failure
        |                      |
        v               Classify failure
   Ack / commit          /          \
                 Temporary            Permanent
                    |                    |
              Bounded retry              v
                    |                DLQ / DLT
           +--------+-------+             |
           |                |             v
        Success        Exhausted      Inspect / repair /
           |                |         approved replay
           v                v
      Ack / commit        DLQ / DLT
~~~

**Dead-letter message không phải một dòng log lỗi.** Log mô tả chuyện gì đã xảy ra; DLQ giữ **đối tượng message cần điều tra hoặc xử lý lại**. Cả hai bổ trợ nhau: DLQ giữ dữ liệu/message, còn logging cung cấp bối cảnh, nguyên nhân, số lần thử, trạng thái chuyển và khả năng quan sát vận hành.

### Phân biệt các thuật ngữ

| Thuật ngữ | Vai trò |
| --- | --- |
| **Message chính** | Dữ liệu do producer gửi cho consumer xử lý nghiệp vụ |
| **Retry / redelivery** | Thử xử lý lại cùng message sau thất bại |
| **Retry queue/topic** | Kênh hoặc cơ chế trì hoãn trước lần thử tiếp theo |
| **Dead-letter message** | Message được phân loại để đưa ra khỏi luồng chính sau thất bại |
| **DLQ/DLT** | Queue/topic lưu các dead-letter message |
| **Poison message** | Message khiến consumer tiếp tục thất bại theo cách không tự giải quyết bằng retry |
| **Parking lot/quarantine** | Khu lưu giữ lâu hơn để điều tra thủ công hoặc xử lý đặc biệt; có thể tách khỏi DLQ |

Tên gọi và cơ chế phụ thuộc broker/framework. Không phải broker nào cũng có khái niệm DLQ tự động theo cùng một ngữ nghĩa; một số hệ thống dùng topic thông thường do ứng dụng hoặc framework tự quản lý.

## 2. Vì sao message rơi vào dead-letter?

Một message thường cần chuyển sang DLQ khi:

1. **Payload không hợp lệ:** thiếu trường bắt buộc, định dạng sai hoặc phiên bản schema không được hỗ trợ.
2. **Quy tắc nghiệp vụ từ chối cố định:** một loại action không được phép hoặc trạng thái nghiệp vụ không thể xử lý bằng retry. Cần cân nhắc liệu đây là lỗi kỳ vọng nên kết thúc có kiểm soát, hay lỗi thực sự cần DLQ.
3. **Không giải mã/deserialize được:** JSON/Avro/Protobuf hoặc envelope không tương thích.
4. **Đã hết số lần retry:** lỗi tạm thời kéo dài quá ngân sách thử lại.
5. **Vượt giới hạn giao nhận:** một số broker hỗ trợ dead-letter khi message bị reject, TTL hết hạn, queue overflow hoặc vượt delivery limit, tùy cấu hình.
6. **Lỗi xử lý không thể phục hồi tại consumer:** ví dụ một message cũ không thể ánh xạ vào mô hình mới.

Điều quan trọng là **phân loại nguyên nhân** trước khi retry hay dead-letter.

| Nhóm lỗi | Ví dụ | Hướng xử lý thường gặp |
| --- | --- | --- |
| **Permanent / non-retryable** | Schema không hợp lệ, dữ liệu thiếu bắt buộc | DLQ sớm, kèm reason code ổn định |
| **Transient / retryable** | Timeout mạng, dịch vụ phụ thuộc tạm dừng | Retry có backoff, jitter và giới hạn |
| **Unknown / unexpected** | Bug mới chưa phân loại | Retry giới hạn hoặc cách ly theo policy; cảnh báo |
| **Business rejection có kiểm soát** | Lệnh bị từ chối hợp lệ, không phải lỗi kỹ thuật | Có thể ghi outcome nghiệp vụ thay vì coi là poison |
| **Infrastructure delivery failure** | Không publish được DLQ hoặc không xác nhận được ack | Không âm thầm bỏ message; kích hoạt đường xử lý lỗi giao nhận |

Không nên chuyển mọi exception sang DLQ ngay lập tức: timeout tạm thời có thể hết sau vài giây. Ngược lại, không nên retry vô hạn một message có schema không hợp lệ vì chỉ làm chậm hệ thống.

## 3. Vòng đời của một dead-letter message

Một quy trình thông thường:

1. Consumer nhận message, giữ được **ID**, nguồn nhận, headers đã được phê duyệt, thông tin tracing và bối cảnh delivery.
2. Consumer thử xử lý; nếu thành công, xác nhận thành công theo cơ chế broker.
3. Nếu lỗi, phân loại **retryable** hay **non-retryable**, ghi event logging đã chuẩn hóa.
4. Với lỗi tạm thời, dùng retry có giới hạn và chính sách trì hoãn; không tạo vòng lặp nóng.
5. Với lỗi vĩnh viễn hoặc vượt giới hạn, chuyển message sang DLQ/DLT, giữ dữ liệu cần thiết cho điều tra/replay.
6. Chỉ xác nhận message gốc đã hoàn tất **khi việc chuyển DLQ đã được xác nhận theo hợp đồng của hệ thống**; hoặc dùng cơ chế dead-letter tự động đáng tin mà broker cung cấp.
7. Hệ thống giám sát phát cảnh báo khi DLQ tăng, message tồn đọng quá lâu hoặc một loại lỗi tăng đột ngột.
8. Người có quyền điều tra xác định nguyên nhân, sửa lỗi, rồi replay hoặc kết thúc xử lý theo quy trình.

**Không có bảo đảm “gửi DLQ rồi ack nguồn” là nguyên tử trong mọi broker.** Nếu hai hành động diễn ra riêng lẻ, có thể xuất hiện cửa sổ lỗi; việc thiết kế cần phù hợp broker, transaction/ack semantics và yêu cầu nghiệp vụ.

## 4. DLQ liên quan gì đến logging?

DLQ quản lý message bị cách ly; logging cho biết **vì sao, khi nào, ở đâu, với chính sách nào** message được chuyển. Log cần đủ metadata nhưng tránh ghi nguyên payload nếu chứa dữ liệu cá nhân hoặc bí mật.

Một event log tốt, ví dụ:

~~~text
event=message_dead_lettered
messageId=msg-1042
source=orders.confirmed
destination=orders.confirmed.dlq
consumer=shipping-worker
attempt=3
reasonCode=SCHEMA_INVALID
traceId=trace-demo-001
outcome=DLQ_PUBLISH_CONFIRMED
~~~

Đây chỉ là **mẫu schema minh họa**, không phải output của chương trình Java ở phần sau. Trong thực tế, message ID, trace ID, destination và tên consumer cũng có thể làm lộ thông tin nội bộ; cần phân loại theo chính sách.

Nên cân nhắc các trường:

| Trường | Tác dụng |
| --- | --- |
| `event` | Phân biệt `message_retry_scheduled`, `message_dead_lettered`, `message_replayed` |
| `messageId` / `eventId` | Tương quan các lần thử và hỗ trợ deduplication |
| `source` | Queue/topic/subscription gốc |
| `destination` | DLQ/DLT hoặc retry channel |
| `consumer` / `service` | Thành phần xử lý |
| `attempt` | Số lần thử theo **chính sách được định nghĩa rõ** |
| `reasonCode` | Mã lỗi ổn định để tổng hợp, cảnh báo |
| `exceptionType` | Loại lỗi đã được kiểm soát, không bắt buộc ghi message thô |
| `traceId` / `correlationId` | Liên kết với request hoặc tác vụ nguồn |
| `outcome` | Phân biệt đề xuất gửi DLQ với gửi đã xác nhận |
| `occurredAt` | Thời gian event, tốt nhất định dạng UTC khi xuất JSON |
| `retryPolicyVersion` | Hữu ích khi cấu hình retry thay đổi theo thời gian |

**Đặc biệt:** log `DLQ_PUBLISH_ATTEMPTED` không có nghĩa DLQ đã lưu message. Chỉ báo `DLQ_PUBLISH_CONFIRMED` khi có tín hiệu xác nhận phù hợp với broker và chính sách durability; một số thư viện không cung cấp bảo đảm này mặc định.

Không đưa nguyên body, credential, token, cookie, thông tin thanh toán hoặc exception chứa payload nhạy cảm vào log. Nếu cần điều tra nội dung, giữ bản message trong **kênh DLQ được bảo vệ** và truy cập theo quyền hạn, thay vì sao chép nó vào nhiều hệ thống log.

## 5. Ví dụ Java 17 chạy độc lập: retry có giới hạn rồi DLQ

Chương trình dưới đây mô phỏng **consumer, retry queue và DLQ trong bộ nhớ**, không cần broker hoặc dependency ngoài JDK. Mục tiêu là hiểu trạng thái và logging, không phải chứng minh giao nhận thực tế.

Bốn message giả:

- `m-1`, loại `OK`: thành công ngay.
- `m-2`, loại `FLAKY`: thất bại tạm thời ở hai lần đầu, thành công lần thứ ba.
- `m-3`, loại `INVALID`: schema sai, vào DLQ ngay.
- `m-4`, loại `UNAVAILABLE`: lỗi tạm thời liên tục, vào DLQ sau ba lần thử.

Các `kind` chỉ là nhãn điều khiển demo, **không phải payload thật**, để log không in thông tin nhạy cảm.

Tạo file **`DeadLetterMessageDemo.java`**:

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.List;
import java.util.Queue;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class DeadLetterMessageDemo {
    private static final int MAX_ATTEMPTS = 3;

    record Message(String id, String kind) {}
    record Delivery(Message message, int attempt) {}
    record DeadLetter(Message original, String reasonCode, int attempts) {}

    static class InvalidMessage extends RuntimeException {}
    static class TemporaryFailure extends RuntimeException {}

    private static void process(Delivery delivery) {
        String kind = delivery.message().kind();
        switch (kind) {
            case "OK" -> { }
            case "FLAKY" -> {
                if (delivery.attempt() < 3) {
                    throw new TemporaryFailure();
                }
            }
            case "UNAVAILABLE" -> throw new TemporaryFailure();
            default -> throw new InvalidMessage();
        }
    }

    private static Logger newDemoLogger() {
        Logger logger = Logger.getLogger("demo.message.deadletter");
        logger.setLevel(Level.INFO);
        logger.setUseParentHandlers(false);

        Handler handler = new Handler() {
            @Override
            public void publish(LogRecord record) {
                if (isLoggable(record)) {
                    System.out.print(getFormatter().format(record));
                }
            }

            @Override
            public void flush() {
                System.out.flush();
            }

            @Override
            public void close() {
                flush();
            }
        };
        handler.setLevel(Level.INFO);
        handler.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName() + ": "
                        + formatMessage(record)
                        + System.lineSeparator();
            }
        });
        logger.addHandler(handler);
        return logger;
    }

    public static void main(String[] args) {
        Queue<Delivery> deliveries = new ArrayDeque<>();
        deliveries.add(new Delivery(new Message("m-1", "OK"), 1));
        deliveries.add(new Delivery(new Message("m-2", "FLAKY"), 1));
        deliveries.add(new Delivery(new Message("m-3", "INVALID"), 1));
        deliveries.add(new Delivery(new Message("m-4", "UNAVAILABLE"), 1));

        List<DeadLetter> dlq = new ArrayList<>();
        Logger logger = newDemoLogger();
        int acknowledged = 0;

        try {
            while (!deliveries.isEmpty()) {
                Delivery delivery = deliveries.remove();
                Message message = delivery.message();
                try {
                    process(delivery);
                    acknowledged++;
                    logger.info("ACK id=" + message.id()
                            + " attempt=" + delivery.attempt());
                } catch (InvalidMessage ex) {
                    dlq.add(new DeadLetter(
                            message, "SCHEMA_INVALID", delivery.attempt()));
                    logger.warning("DLQ id=" + message.id()
                            + " reason=SCHEMA_INVALID attempts="
                            + delivery.attempt());
                } catch (TemporaryFailure ex) {
                    if (delivery.attempt() < MAX_ATTEMPTS) {
                        int next = delivery.attempt() + 1;
                        deliveries.add(new Delivery(message, next));
                        logger.info("RETRY id=" + message.id()
                                + " nextAttempt=" + next);
                    } else {
                        dlq.add(new DeadLetter(
                                message, "RETRY_EXHAUSTED",
                                delivery.attempt()));
                        logger.warning("DLQ id=" + message.id()
                                + " reason=RETRY_EXHAUSTED attempts="
                                + delivery.attempt());
                    }
                }
            }
            logger.info("SUMMARY acknowledged=" + acknowledged
                    + " deadLetters=" + dlq.size());
        } finally {
            for (Handler handler : logger.getHandlers()) {
                logger.removeHandler(handler);
                handler.close();
            }
        }
    }
}
~~~

Biên dịch và chạy với **JDK 17 trở lên**:

~~~bash
javac DeadLetterMessageDemo.java
java DeadLetterMessageDemo
~~~

**Stdout chính xác trong bản demo đơn luồng:**

~~~text
INFO: ACK id=m-1 attempt=1
INFO: RETRY id=m-2 nextAttempt=2
WARNING: DLQ id=m-3 reason=SCHEMA_INVALID attempts=1
INFO: RETRY id=m-4 nextAttempt=2
INFO: RETRY id=m-2 nextAttempt=3
INFO: RETRY id=m-4 nextAttempt=3
INFO: ACK id=m-2 attempt=3
WARNING: DLQ id=m-4 reason=RETRY_EXHAUSTED attempts=3
INFO: SUMMARY acknowledged=2 deadLetters=2
~~~

**Stderr:** không có trong trường hợp chạy thành công vì custom JUL `Handler` chủ động in ra `System.out`; `ConsoleHandler` chuẩn của JUL thường dùng stderr.

### Giải thích kết quả

- `m-1` được xử lý thành công ngay và ghi `ACK`.
- `m-2` được đưa lại hàng đợi ở lần thử thứ 2 và 3; đến lần 3 thì thành công, nên **không vào DLQ**.
- `m-3` không hợp lệ, nên **vào DLQ ở lần 1**, không retry vô nghĩa.
- `m-4` luôn thất bại tạm thời; khi hết ngân sách 3 lần, nó **vào DLQ** với `RETRY_EXHAUSTED`.
- `acknowledged=2`, `deadLetters=2` là số message của mô phỏng, không phải số lần delivery. Tổng số lần gọi xử lý nhiều hơn số message gốc vì có retry.

`DeadLetter` **giữ đối tượng `Message original` trong danh sách DLQ**; logger chỉ ghi ID và reason code. Trong hệ thống thật, DLQ phải giữ đủ dữ liệu để điều tra hoặc replay theo policy, nhưng các trường nhạy cảm vẫn cần bảo vệ. `MAX_ATTEMPTS=3` được hiểu là **tổng cộng ba lần xử lý**, gồm lần đầu, không phải ba lần retry sau lần đầu.

**Giới hạn quan trọng:** hàng đợi trong demo nằm trong RAM; một process crash làm mất dữ liệu. Lần retry được đưa ngay vào cuối queue, **không có delay, backoff, ack, transaction hay broker confirms**. Thứ tự xử lý mô phỏng không đại diện cho Kafka partition, RabbitMQ, JMS hoặc SQS. Do đó chỉ dùng code này để học phân loại lỗi và ghi log, không dùng nguyên mẫu để triển khai vận hành.

## 6. Retry khác gì dead-letter?

**Retry** kỳ vọng nguyên nhân lỗi có thể hết; **dead-letter** cách ly một message khi quy trình tự động không còn muốn xử lý nó trên luồng chính.

| Khía cạnh | Retry | Dead-letter |
| --- | --- | --- |
| Mục tiêu | Thử lại để hoàn tất xử lý | Giữ message lỗi phục vụ sửa, điều tra hoặc quyết định bỏ |
| Trạng thái | Còn nằm trong đường xử lý tự động | Tách khỏi đường xử lý chính |
| Phù hợp | Timeout, dịch vụ phụ thuộc tạm lỗi | Schema không hợp lệ, lỗi vĩnh viễn, vượt giới hạn retry |
| Giới hạn | Số lần thử, tuổi message, tổng thời gian | Dung lượng lưu, retention, quyền truy cập, backlog |
| Quan sát | `message_retry_scheduled`, attempt, delay | `message_dead_lettered`, reason, original destination |
| Rủi ro | Retry storm, duplicate side effects, chặn luồng | DLQ đầy, message bị lãng quên, replay gây lỗi lặp |

Một chính sách retry phổ biến là **exponential backoff có jitter**; ví dụ chờ khoảng 1 giây, 2 giây, 4 giây rồi giới hạn tối đa. Cần đặt trần tổng số lần, thời gian chờ và ngân sách tải lên dependency. Với consumer theo thứ tự hoặc partition, trì hoãn một message có thể ảnh hưởng các message phía sau; không thể giả định mọi broker cho phép đưa message ra rồi phát lại mà không đổi ordering.

**Retry không miễn phí:** cùng một message có thể đã ghi database thành công nhưng consumer mất kết nối trước khi ack. Lần nhận sau có thể tạo side effect trùng. Vì vậy **idempotency** cần được xem xét ngay cả khi message cuối cùng chưa vào DLQ.

### Tránh retry vô hạn và vòng lặp nóng

Một anti-pattern:

~~~text
consume -> exception -> nack(requeue=true)
             ^               |
             +---------------+
~~~

Nếu message không bao giờ xử lý thành công, vòng lặp này có thể tạo hàng nghìn lần delivery/exception, làm nghẽn consumer và lấp log. Phải dùng retry delay phù hợp, ngưỡng lần thử, phân loại permanent error và cơ chế dead-letter/parking lot.

## 7. Quy tắc ack khi gửi DLQ

Với cơ chế tiêu thụ message có thao tác **acknowledgment**, một quy tắc thiết kế thường là:

**Không coi message gốc đã được xử lý xong nếu việc gửi sang DLQ chưa được xác nhận phù hợp với mức tin cậy yêu cầu.**

~~~text
Consumer nhan original message
           |
    Decide dead-letter
           |
    Publish to DLQ
           |
       Confirmed?
       /        \
     No         Yes
      |          |
 Retry/preserve  Ack original
 without drop       |
                  Done
~~~

Nếu ứng dụng **ack original trước rồi publish DLQ**: process có thể chết sau ack nhưng trước publish, làm mất message.

Nếu **publish DLQ trước rồi ack original**: process có thể chết sau publish thành công nhưng trước ack, khiến original được giao lại và DLQ chứa bản sao. Đây là lý do cần **ID ổn định, deduplication và idempotency**, chứ không tuyên bố “đã gửi DLQ là exactly once”.

Một số broker cung cấp dead-lettering nội bộ khi một consumer reject/nack theo cách được hỗ trợ. Cơ chế ấy khác với ứng dụng tự publish DLQ rồi ack original; **khả năng bảo đảm giao nhận, xử lý publisher confirm/transaction và rủi ro mất/nhân đôi message phụ thuộc broker, loại queue, phiên bản và cấu hình**. Cần đọc tài liệu đang dùng và kiểm thử sự cố thực tế.

### Nếu DLQ publish thất bại

- Ghi sự kiện lỗi chuyển DLQ, cùng **message ID, destination, mã lỗi và kết quả không xác nhận**; tránh log nguyên body.
- Không âm thầm bỏ message gốc.
- Áp dụng retry hoặc giữ message ở nơi bền vững phù hợp; tránh retry nóng gây thêm áp lực lên hệ thống.
- Cảnh báo vận hành nếu DLQ hoặc đường dead-letter không khả dụng.
- Kiểm tra cơ chế dead-letter mặc định của broker không vô tình tạo vòng lặp giữa các queue/topic.

Nếu broker không hỗ trợ giao dịch chung giữa thay đổi nghiệp vụ, publish và ack, có thể cần **transactional outbox/inbox**, event ID và idempotent consumer, tùy yêu cầu độ tin cậy.

## 8. Một số hệ sinh thái message và cách nhìn DLQ/DLT

### RabbitMQ / AMQP

RabbitMQ có cơ chế **dead-letter exchange (DLX)**. Tùy cấu hình queue và chính sách, message có thể được dead-letter khi bị reject/nack với `requeue=false`, hết TTL, queue vượt giới hạn hoặc vượt giới hạn delivery trong các loại queue hỗ trợ. Message có thể được route từ DLX sang queue lưu dead-letter theo routing key.

Điểm cần hiểu:

- `basicReject`/`basicNack` với `requeue=true` **không tương đương** gửi vào DLQ; nó cho phép redelivery.
- DLX là **exchange**, không phải bản thân queue; cần binding/routing phù hợp để message tới đúng DLQ.
- Chính sách dead-letter, retention, giới hạn queue và mức an toàn giao nhận cần được kiểm tra. Có thể có các điều kiện khiến message được chuyển đi không thành công theo cấu hình; không mặc nhiên coi dead-letter an toàn tuyệt đối.
- Các header lịch sử như thông tin dead-letter của broker chỉ nên dùng đúng ngữ nghĩa của phiên bản đang chạy; tránh tự suy số lần xử lý nghiệp vụ từ một giá trị không được định nghĩa như vậy.

### Apache Kafka

Kafka sử dụng **topic**. Trong nhiều hệ thống, DLT là **mẫu thiết kế do consumer/framework tự triển khai**, không phải một loại topic mặc định tự động nhận mọi record bị lỗi. Consumer có thể publish record lỗi vào topic riêng; sau đó mới xử lý offset của record gốc theo hợp đồng ứng dụng.

Cần phân biệt:

- **Commit offset** cho partition thể hiện tiến độ tiêu thụ, không phải một `ack` riêng độc lập cho từng message như một số queue broker.
- Một record lỗi có thể ảnh hưởng thứ tự các record tiếp theo trong cùng partition; việc skip, retry hay đưa DLT thay đổi behavior ordering.
- Publish vào DLT rồi commit offset có các cửa sổ lỗi tương tự; muốn bảo đảm chặt hơn phải xem khả năng transaction Kafka, idempotent producer, consumer-group semantics và giới hạn của các side effect ngoài Kafka.
- Framework như Spring for Apache Kafka có thể cung cấp error handler/DLT publisher, nhưng retry topic, backoff, recoverer và offset commit phụ thuộc cấu hình cụ thể.

### JMS và các broker khác

Trong JMS, khái niệm redelivery, acknowledgment và DLQ phụ thuộc **JMS provider**. Không có một tên queue hay policy dead-letter phổ quát áp dụng cho mọi triển khai. Các broker có thể dùng redelivery limit, error destination hoặc dead-letter queue tùy hệ thống.

Trong các dịch vụ queue được quản lý, DLQ thường đi kèm **redrive policy** hoặc giới hạn số lần nhận. Cần kiểm tra quy tắc retention, visibility timeout, max receive count và quyền replay. Những khái niệm đó không thể chuyển nguyên sang Kafka/JMS mà không xem hợp đồng của sản phẩm cụ thể.

**Kết luận:** chọn thuật toán retry/ack và cơ chế dead-letter theo **broker thật sự được dùng**, không chỉ đổi tên phương thức từ một backend sang backend khác.

## 9. Metadata cần giữ trong dead-letter record

Một dead-letter record tốt thường cần **message gốc hoặc dữ liệu đủ để xử lý lại** và metadata truy vết. Ví dụ cấu trúc khái niệm:

~~~json
{
  "messageId": "msg-1042",
  "originalDestination": "orders.confirmed",
  "originalKey": "order-42",
  "deadLetterReason": "SCHEMA_INVALID",
  "attempts": 1,
  "consumer": "shipping-worker",
  "firstSeenAt": "2026-01-15T10:00:00Z",
  "deadLetteredAt": "2026-01-15T10:00:03Z",
  "traceId": "trace-demo-001",
  "schemaVersion": 2,
  "payloadRef": "protected-store-ref-123"
}
~~~

Đây là **mẫu metadata** không phải định dạng JSON chuẩn chung của các broker. Trong thực tế, message body có thể nằm ngay trong DLT hoặc được tham chiếu tới kho an toàn. Nếu payload bị lỗi serialization thì việc phục hồi dữ liệu gốc cần kế hoạch riêng; không nên tạo lại một message chỉ từ error string.

Các điểm cần quyết định:

- **Message ID ổn định:** giữ ID gốc khi chuyển và replay; có thể thêm `deliveryId`/`replayId` riêng để phân biệt các lần giao.
- **Nguồn gốc:** topic/queue, partition/offset hoặc routing key khi phù hợp.
- **Lỗi có phân loại:** `reasonCode`, exception type; tránh nhúng toàn bộ stack trace và body vào header.
- **Số lần xử lý:** định nghĩa rõ attempt đầu tiên là 1 hay 0 và ai tăng bộ đếm; broker redelivery flag không nhất thiết bằng tổng lần gọi handler.
- **Thời gian:** thời điểm nhận đầu, retry gần nhất và chuyển DLQ; dùng timestamp đã được chuẩn hóa.
- **Truy vết:** trace/correlation ID phù hợp chính sách; không log token xác thực.
- **Phiên bản:** schema, app release, retry policy để biết message lỗi dưới phiên bản nào.

**Bảo mật:** DLQ có thể chứa PII, tài liệu khách hàng hoặc dữ liệu thanh toán. Chỉ người có quyền mới được truy cập; đặt retention, encryption và audit hoạt động đọc/replay. Việc copy nguyên message vào log cảnh báo hoặc ticket hỗ trợ có thể tạo thêm nhiều bản sao không kiểm soát.

## 10. Quan sát DLQ trong logging và monitoring

Không chỉ theo dõi `ERROR` hoặc số exception; cần theo dõi **dòng đời message**.

| Tín hiệu | Ý nghĩa vận hành |
| --- | --- |
| `message_processing_failed` | Một attempt thất bại, có thể còn retry |
| `message_retry_scheduled` | Retry đã được lập lịch/giao cho hệ thống tương ứng |
| `message_dead_lettered` | Message chuyển vào DLQ theo policy; phân biệt attempted và confirmed |
| `message_replay_requested` | Ai/cơ chế nào yêu cầu replay |
| `message_replay_completed` | Replay hoàn tất theo outcome đã xác nhận |
| `dlq_depth` / backlog | Số message đang tồn đọng |
| `dlq_oldest_age` | Message lâu nhất chưa được xử lý |
| `retry_attempts_total` | Tần suất retry, giúp phát hiện dependency đang lỗi |
| `dead_letter_rate` | Tỷ lệ message đi DLQ theo nguồn, reason code |
| `dlq_publish_failures` | Bản thân đường cách ly message đang có vấn đề |

**Metrics không thay thế log:** metric đo xu hướng, log truy xét từng message và DLQ giữ bản message cần xử lý. Nên kết nối qua `messageId`, `traceId`, `reasonCode` và destination nhưng tránh dùng ID từng message làm **metric label** vì cardinality quá lớn.

Ví dụ một cảnh báo hữu ích không chỉ là “DLQ count > 0”: một message kiểm thử đã biết có thể nằm ở DLQ theo chủ đích. Hãy phân biệt bất thường theo tỷ lệ, độ tuổi tồn đọng, loại lỗi, mức độ quan trọng và thất bại của đường gửi DLQ.

### Log có cấu trúc và thông tin riêng tư

Một mẫu event:

~~~text
event=message_retry_scheduled messageId=m-4
attempt=2 nextAttempt=3 reasonCode=DEPENDENCY_TIMEOUT
delayMs=2000 consumer=shipping-worker
~~~

Đây là ví dụ policy có delay, **không phải output demo mục 5**, nơi retry diễn ra ngay trong RAM. Không log nội dung message hoặc `exception.getMessage()` nếu nó có thể chứa dữ liệu khách hàng. Chỉ dùng enum/reason code ổn định và các field đã được kiểm duyệt.

## 11. Replay: xử lý lại message ở DLQ một cách có kiểm soát

DLQ không phải nơi “bỏ đi rồi quên”. Khi đã sửa code, schema hoặc dữ liệu phụ thuộc, có thể cần replay. Nhưng đưa tất cả message từ DLQ về queue gốc ngay có thể gây lỗi lặp.

Một quy trình replay tốt:

1. **Phân loại theo reason code:** xác định lỗi đã được sửa, lỗi nào vẫn không thể xử lý.
2. **Đối chiếu nghiệp vụ:** liệu hành động đã từng thành công một phần chưa; retry có tạo bản ghi/thanh toán/thông báo trùng không?
3. **Đánh giá schema/version:** consumer hiện tại có đọc được payload cũ không; cần migration không?
4. **Chọn phạm vi:** theo message ID, thời gian, lý do hoặc tenant, không replay toàn bộ tùy tiện.
5. **Dry-run hoặc thử nhỏ** nếu hệ thống có cách kiểm tra an toàn; đo tác động và backlog.
6. **Thực hiện replay có rate limit**, kiểm soát tải và số lần thử mới; tránh làm nghẽn luồng chính.
7. **Ghi audit event replay:** ai yêu cầu, khi nào, từ DLQ nào, outcome; không log PII không cần.
8. **Theo dõi sau replay:** xác định bao nhiêu message hoàn tất, bao nhiêu rơi lại DLQ; giữ traceability.
9. **Không xóa bản DLQ trước khi chắc đã xử lý xong**, theo chính sách bảo toàn và retention của hệ thống.

Cần tránh **vòng lặp replay tự động vô hạn**: message lại vào DLQ do chưa sửa nguyên nhân, rồi lại replay, khiến hệ thống mất ổn định. Những message không thể sửa được có thể cần quarantine dài hạn hoặc quy trình quyết định bỏ, có lưu dấu vết theo chính sách.

**Ordering và idempotency:** một message replay ở thời điểm muộn có thể đến sau các sự kiện mới hơn của cùng entity. Consumer cần quyết định xử lý message cũ theo version/sequence/state hiện tại; không phải lúc nào “chạy lại” cũng đúng về nghiệp vụ.

## 12. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân khả dĩ | Hướng kiểm tra |
| --- | --- | --- |
| Consumer log exception liên tục | Message poison được requeue ngay vô hạn | Giới hạn retry, backoff, phân loại permanent |
| DLQ không có message dù có log “DLQ” | Chỉ ghi log intent, chưa publish hoặc chưa confirm | Phân biệt attempted/confirmed, kiểm tra destination/binding |
| Message bị mất sau khi handler lỗi | Ack/commit original trước khi DLQ persist | Sửa thứ tự hoặc thiết kế transaction/outbox phù hợp |
| Một message có hai bản trong DLQ | DLQ publish thành công nhưng ack nguồn lỗi, redelivery | Event ID, idempotent handoff và dedup |
| Retry quá lâu rồi mới DLQ | Attempt limit/TTL/backoff quá cao | Ngân sách retry theo SLA và loại lỗi |
| DLQ đầy hoặc backlog tăng mãi | Không có quy trình quan sát/repair/replay | Metrics depth/age, ownership, retention, alert |
| Replay lại thất bại | Chưa sửa schema, data hoặc dependency | Phân loại nguyên nhân trước replay |
| Replay gây dữ liệu trùng | Consumer không idempotent hoặc đã có side effect | Dedupe theo business key/event ID |
| Log chứa nguyên payload khách hàng | Logger in body hoặc exception thô | Allowlist metadata, bảo vệ DLQ và hạn chế log |
| Ordering bị thay đổi | Retry topic/DLT chuyển message ngoài partition gốc | Xem ordering contract theo broker và entity |
| Đếm attempt không nhất quán | Broker redelivery count khác policy ứng dụng | Định nghĩa cách đếm và ghi rõ nguồn |
| DLQ route quay lại queue chính | Binding/routing policy gây loop | Kiểm tra DLX bindings, retry routes và limits |

## 13. Checklist triển khai dead-letter trong ứng dụng Java

- [ ] Phân loại rõ lỗi transient, permanent, business rejection và unknown.
- [ ] Định nghĩa attempt budget, backoff, jitter, timeout và điều kiện dừng retry.
- [ ] Xác định DLQ/DLT theo từng nguồn hoặc nhóm lỗi, với tên và ownership rõ ràng.
- [ ] Đảm bảo message lỗi được lưu đủ dữ liệu để điều tra/replay theo yêu cầu.
- [ ] Giữ message ID, trace ID, original source và reason code; không nhúng secret vào log.
- [ ] Phân biệt publish attempted và confirmed, không ack original quá sớm.
- [ ] Đánh giá duplicate delivery, idempotency và ordering.
- [ ] Kiểm tra cấu hình broker cụ thể thay vì giả định mọi DLQ có cùng semantics.
- [ ] Giám sát độ sâu, tuổi backlog, tỷ lệ dead-letter, lỗi publish và replay.
- [ ] Có quy trình xử lý DLQ: review, sửa lỗi, replay có chọn lọc hoặc loại bỏ theo chính sách.
- [ ] Đặt phân quyền, encryption, retention và audit truy cập DLQ, vì payload có thể nhạy cảm.
- [ ] Test poison message, transient outage, consumer crash, DLQ outage, duplicate/replay và shutdown.

### Tự kiểm tra

**Câu 1.** Message thiếu field bắt buộc, retry mười lần có chắc giải quyết được không?  
**Đáp:** Không. Đây có thể là permanent/schema error; nên phân loại và dead-letter sớm.

**Câu 2.** `logger.error("sent to DLQ")` có chứng minh message đã lưu trong DLQ không?  
**Đáp:** Không. Log cần phân biệt trạng thái dự định gửi và trạng thái đã được broker xác nhận.

**Câu 3.** Nếu publish DLQ thành công nhưng ack original thất bại, điều gì có thể xảy ra?  
**Đáp:** Original được giao lại, dẫn đến duplicate; cần ID ổn định và idempotency/dedup.

**Câu 4.** Kafka có DLQ tự động y hệt cơ chế reject của mọi RabbitMQ queue không?  
**Đáp:** Không. Trong Kafka, DLT thường là pattern do ứng dụng/framework triển khai; offset, transaction và replay có semantics riêng.

**Câu 5.** Nên paste payload message lỗi vào Slack/ticket cho dễ sửa không?  
**Đáp:** Không mặc định. Payload có thể chứa PII hoặc secret; cần kênh truy cập có kiểm soát và log metadata tối thiểu.

**Câu 6.** Sau khi sửa bug, replay toàn bộ DLQ ngay có luôn an toàn không?  
**Đáp:** Không. Có thể gây side effect trùng, phá ordering hoặc phát sinh retry storm; cần chọn lọc, đo tải và xác nhận outcome.

**Ghi nhớ:** Dead-letter message là **message được cách ly sau thất bại xử lý**, không phải một dòng exception. Thiết kế tốt kết hợp phân loại lỗi, retry có giới hạn, chuyển DLQ có xác nhận phù hợp, logging có cấu trúc và an toàn dữ liệu, giám sát backlog, cùng quy trình replay idempotent. Khả năng không mất/không trùng message phụ thuộc hợp đồng của broker và toàn bộ đường xử lý, chứ không được bảo đảm chỉ vì đã có một queue mang tên `DLQ`.