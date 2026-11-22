# Quản lý retry phía producer để tránh nhân bản thông điệp

> **Chương:** Producer  
> **Bối cảnh:** Ứng dụng Java dùng JMS để gửi sự kiện hoặc lệnh bất đồng bộ tới Apache ActiveMQ Classic/Artemis. Bài tập trung vào **retry của producer**, thời điểm không thể biết chắc broker đã nhận message, chiến lược giới hạn số lần thử và cách ngăn một sự kiện nghiệp vụ bị xử lý nhiều lần. Các ví dụ tách rõ cơ chế JMS chung, ActiveMQ Classic và tính năng riêng của Artemis.

## 1. Vấn đề cốt lõi: lỗi khi gửi không đồng nghĩa broker chưa nhận

Giả sử Order Service phát lệnh `InvoiceRequested` với `eventId=EVT-1001` vào queue `billing.commands`. Producer gọi `send()` hoặc `commit()` nhưng mất kết nối đúng lúc broker đang phản hồi.

Có hai diễn biến có cùng biểu hiện ở phía ứng dụng:

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant B as Broker
    P->>B: SEND EVT-1001
    Note over B: Trường hợp A: chưa ghi nhận message
    B--xP: Mất kết nối trước khi chấp nhận
    Note over P: Producer thấy lỗi; retry là cần thiết
~~~

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant B as Broker
    P->>B: SEND/COMMIT EVT-1001
    B->>B: Chấp nhận/commit message
    B--xP: ACK/response bị mất trên mạng
    Note over P: Producer cũng thấy lỗi/timeout
    P->>B: Retry EVT-1001
    Note over B: Có nguy cơ lưu thêm một message
~~~

**Producer không thể luôn phân biệt hai trường hợp từ một exception.** Đây là bài toán *ambiguous outcome* hoặc *uncertain commit*: broker có thể đã thành công, nhưng ứng dụng không nhận được bằng chứng xác nhận.

Nếu tự động gọi lại `send()` và tạo một message JMS mới, hệ thống có thể có **hai message mang cùng ý nghĩa nghiệp vụ**. Dù hai message có `JMSMessageID` khác nhau, chúng vẫn yêu cầu phát hành cùng một hóa đơn.

**Mục tiêu thực tế** là:

- Bảo đảm sự kiện quan trọng không bị bỏ quên khi gặp lỗi tạm thời.
- Giới hạn số lần retry, độ trễ và lượng công việc tích lũy.
- Gắn **một định danh nghiệp vụ ổn định** với mọi lần thử cho cùng một sự kiện.
- Cho phép nhận trùng ở tầng transport nhưng **không thực hiện tác động nghiệp vụ trùng**.
- Phân biệt cơ chế chống duplicate của broker với idempotency của consumer.

Không nên hứa hẹn "exactly-once end-to-end" chỉ vì producer bật persistent delivery hoặc JMS transaction.

## 2. Những ranh giới xác nhận của một producer JMS

Xét pipeline:

~~~text
Database nghiệp vụ
    |
    | Tạo event EVT-1001
    v
Producer -> client JMS -> broker -> queue -> consumer -> database Billing
           ^           ^
           |           |
         send()      broker commit/accept
~~~

Một producer có thể nhận lỗi tại nhiều thời điểm:

| Thời điểm | Điều producer biết | Có thể tồn tại message ở broker? | Hành động |
|---|---|---|---|
| Chưa bắt đầu `send()` vì validation lỗi | Không hề gọi provider gửi | Không do lần thử này | Sửa lỗi, không retry mạng |
| Không tạo được connection tới broker | Chưa thiết lập phiên gửi | Không do phiên chưa gửi này | Retry kết nối có giới hạn nếu là lỗi tạm thời |
| `send()` bị lỗi/timeout sau khi bắt đầu | Kết quả chưa chắc chắn | **Có thể** | Dùng cùng `eventId`, ghi nhận trạng thái không chắc chắn |
| `send()` trả về bình thường ở session transacted nhưng chưa `commit()` | Transaction chưa hoàn tất | Có thể tồn tại dữ liệu chưa commit, chưa được publish ổn định | Phải `commit()`; rollback nếu chủ động hủy transaction |
| `commit()` ném lỗi hoặc mất phản hồi | Không biết transaction commit ở broker chưa | **Có thể** | Coi outcome là **unknown**, retry có chống duplicate |
| `commit()` trả về thành công | Local JMS transaction đã hoàn thành theo hợp đồng provider | Đã được broker chấp nhận trong phạm vi bảo đảm cấu hình | Có thể đánh dấu phát thành công ở phía outbox |
| Consumer hoàn tất nghiệp vụ và ACK | Producer thường không quan sát trực tiếp mốc này | Message có thể đã rời backlog của consumer | Cần nghiệp vụ/monitoring riêng nếu muốn biết đã xử lý |

**Lưu ý đối với transacted producer:** `send()` có thể chỉ đưa message vào transaction đang mở; điểm xác nhận có ý nghĩa để đánh dấu “đã publish” là `session.commit()`. Không coi một lần `send()` trả về là đủ nếu session còn chưa commit.

Với session không transacted, contract của `send()` phụ thuộc mode, đồng bộ/bất đồng bộ và cấu hình client/provider. Một API trả về nhanh không tương đương với việc downstream đã xử lý. Đặc biệt các tối ưu gửi bất đồng bộ có thể thay đổi ranh giới báo lỗi mà caller nhìn thấy.

### 2.1. Vì sao persistent delivery vẫn chưa ngăn duplicate?

`DeliveryMode.PERSISTENT` yêu cầu provider xử lý message theo semantics lưu bền. Nó giúp giảm mất message do lỗi broker nhưng **không làm một business event chỉ xuất hiện một lần** khi producer retry bằng những message mới.

Các trạng thái khác nhau:

- *Durable*: broker cố gắng giữ message theo hợp đồng persistence.
- *At least once*: message có thể được giao lại khi chưa ACK.
- *Idempotent*: thực hiện hai lần cùng thao tác có kết quả nghiệp vụ tương đương một lần.
- *Exactly once processing*: một mục tiêu nghiệp vụ phức tạp hơn, đòi hỏi ranh giới transaction/deduplication được chứng minh, không tự có nhờ một flag JMS.

Bài này tập trung rủi ro **duplicate publish từ producer**; duplicate consumer do crash sau DB commit nhưng trước ACK vẫn phải được xét trong thiết kế cuối.

## 3. Quy tắc số một: một sự kiện, một `eventId` qua mọi lần gửi

Mỗi sự kiện nghiệp vụ cần một định danh duy nhất, ví dụ `EVT-1001` hoặc UUID, được **tạo một lần** lúc hình thành sự kiện và được lưu bền cùng ý định publish.

~~~text
Order #O-1001 tạo InvoiceRequested:
    eventId = EVT-1001
    orderId = O-1001
    type    = invoice.requested.v1

Attempt #1 -> JMSMessageID = ID:broker-...:1
Attempt #2 -> JMSMessageID = ID:broker-...:2
Attempt #3 -> JMSMessageID = ID:broker-...:3

Mọi attempt đều có eventId = EVT-1001.
~~~

`JMSMessageID` do JMS provider quản lý cho message/lần gửi. Khi retry bằng message mới hoặc qua một provider khác, ID có thể khác; **đừng dùng JMSMessageID để quyết định hai lần gửi có cùng tác động nghiệp vụ hay không**.

Ví dụ Java:

~~~java
TextMessage message = session.createTextMessage(payload);
message.setStringProperty("eventId", stableEventId);
message.setJMSType("invoice.requested.v1");
producer.send(message);
~~~

Mỗi attempt có thể tạo một `TextMessage` mới trong session mới, miễn là vẫn dùng **cùng** `stableEventId` và cùng nội dung nghiệp vụ tương đương. Tốt nhất lưu payload/version cùng eventId trong transactional outbox để việc restart không sinh một sự kiện khác.

**Tránh lỗi phổ biến:**

~~~java
for (int attempt = 1; attempt <= 5; attempt++) {
    String eventId = UUID.randomUUID().toString(); // SAI: đổi ID mỗi retry
    publish(eventId, payload);
}
~~~

Cách đúng là sinh và lưu ID **trước vòng retry**, hoặc đọc lại ID đã lưu bền:

~~~java
String eventId = existingOutboxRecord.getEventId();
for (int attempt = 1; attempt <= 5; attempt++) {
    publish(eventId, existingOutboxRecord.getPayload());
}
~~~

Ví dụ thứ hai minh họa quy tắc dữ liệu; `existingOutboxRecord` và `publish` thuộc mã ứng dụng, không phải đối tượng của JMS.

## 4. Phân loại lỗi trước khi retry

Không nên retry mọi `JMSException` như nhau. Khi exception là lỗi mạng/timeout sau khi send bắt đầu, kết quả có thể **unknown**; nếu là sai credentials hoặc sai destination thì retry tức thì không có ích.

| Nhóm lỗi | Ví dụ | Retry? | Điều cần lưu |
|---|---|---|---|
| **Lỗi đầu vào** | Payload thiếu trường bắt buộc, schema sai | Không | Đưa vào luồng sửa dữ liệu |
| **Lỗi cấu hình/quyền** | ACL từ chối send, sai credential, address không tồn tại khi auto-create tắt | Không retry liên tục | Alert, sửa cấu hình |
| **Mất kết nối trước khi bắt đầu send** | Broker chưa sẵn sàng, chưa tạo được connection | Có, hữu hạn | Giữ sự kiện pending |
| **Timeout/mất kết nối khi send/commit** | ACK phản hồi thất lạc, socket đóng giữa commit | Có nhưng **kết quả lần trước chưa biết** | Giữ eventId, ghi attempt/unknown |
| **Broker quá tải** | Producer flow control, backlog/disk đầy, quota | Chờ/backoff theo tín hiệu | Tránh bắn retry gây tăng tải |
| **Lỗi không rõ nguồn** | Mã lỗi không phân loại được | Tùy policy; ưu tiên trạng thái cần điều tra | Không kết luận broker chưa nhận |

**Không có một bộ mã lỗi JMS chuẩn đủ để khẳng định mọi exception là retryable.** Ứng dụng cần classifier theo phiên bản ActiveMQ client, loại exception, error code, exception được liên kết (`getLinkedException()`) và kiến trúc triển khai. Nếu không nhận diện được, đừng biến nó thành một vòng retry vô hạn.

Một nguyên tắc an toàn: **retry chỉ là cách tăng khả năng message được chấp nhận; deduplication/idempotency mới là lớp bảo vệ khi kết quả cũ không chắc chắn.**

## 5. Thiết kế retry policy: giới hạn, backoff, jitter và ngân sách

### 5.1. Giới hạn số lần thử

Chọn `maxAttempts`, tính cả lần đầu. Ví dụ:

~~~text
maxAttempts = 4

attempt 1: gửi
attempt 2: gửi lại sau backoff
attempt 3: gửi lại sau backoff
attempt 4: thử cuối
sau đó: giữ trạng thái pending/unknown và báo lỗi vận hành
~~~

**Hết số lần retry không có nghĩa được xóa sự kiện.** Với lệnh nghiệp vụ quan trọng, lưu nó trong outbox/queue bền để xử lý lại ở một chu kỳ sau, hoặc đưa vào trạng thái cần vận hành kiểm tra. Nếu chỉ giữ event trong RAM, process crash giữa các lần thử có thể làm mất ý định publish.

### 5.2. Exponential backoff có jitter

Một cách tính phù hợp với lỗi tạm thời:

~~~text
baseDelay = 250 ms
maxDelay  = 8_000 ms

cap(attempt) = min(maxDelay, baseDelay * 2^(attempt - 1))
sleep        = random(0, cap(attempt))   // full jitter
~~~

Ví dụ `attempt=1` có cap 250 ms, `attempt=2` có cap 500 ms, `attempt=3` có cap 1.000 ms. Jitter khiến nhiều producer bị lỗi cùng lúc **không thức dậy để gửi đồng loạt**.

Khi có rất nhiều producer, nên thêm **rate limit/circuit breaker** chung để tránh "thundering herd". Chờ retry theo tín hiệu backpressure từ broker, deadline nghiệp vụ và dung lượng hàng đợi chứ không chỉ theo timer.

### 5.3. Tính tổng timeout, không chỉ delay

Một policy hữu hạn vẫn có thể mất hàng phút nếu từng `send/commit` chờ quá lâu. Tổng ngân sách gồm:

~~~text
T_total <= tổng timeout của mỗi attempt + tổng backoff + overhead mở connection
~~~

Đối với API đồng bộ, timeout kết nối, timeout send và failover reconnect có thể do những lớp khác nhau kiểm soát. Chọn **một retry owner** rõ ràng: transport/client failover tự reconnect ở mức giao thức; vòng retry ứng dụng đảm nhận **một lần publish logic** và vẫn phải bảo vệ trường hợp uncertain outcome.

### 5.4. Retry không tự kéo dài hiệu lực của nghiệp vụ

Nếu một sự kiện chỉ còn ý nghĩa trong 60 giây từ khi đơn hàng được tạo, đừng retry ngày hôm sau với TTL mới 60 giây như thể sự kiện vừa xảy ra.

Lưu một `businessExpiresAt` độc lập và kiểm tra trước khi publish:

~~~text
occurredAt         = 2026-11-17T10:00:00Z
businessExpiresAt  = 2026-11-17T10:01:00Z

Attempt #1 lúc 10:00:10: còn hợp lệ
Attempt #2 lúc 10:00:30: còn hợp lệ
Attempt #3 lúc 10:02:00: đã quá hạn nghiệp vụ -> dừng publish, xử lý expiry
~~~

TTL JMS là chính sách **thời gian sống của một lần gửi**; retry tạo message mới có thể tạo mốc expiration mới. Hai chính sách cần được thiết kế cùng nhau.

## 6. Ví dụ Java ActiveMQ Classic: bounded retry với event ID ổn định

Ví dụ sau dùng **ActiveMQ Classic 5.x, JMS 1.1 (`javax.jms`)** và client Maven `org.apache.activemq:activemq-client` phiên bản tương thích broker/JDK. Chương trình gửi một lệnh `InvoiceRequested` bằng **PERSISTENT + transacted Session**, với tối đa 4 lần thử.

**Giới hạn minh họa:** code retry mọi `JMSException` để dễ thấy cấu trúc; production phải phân loại lỗi vĩnh viễn, có outbox bền và cảnh báo. Mỗi lần gửi mở connection/session mới để tách rõ attempt; ứng dụng thông lượng cao nên dùng connection pool/lifecycle hợp lý. Thông tin đăng nhập trong code chỉ dùng cho môi trường lab.

~~~java
import java.util.concurrent.ThreadLocalRandom;
import java.util.UUID;

import javax.jms.Connection;
import javax.jms.DeliveryMode;
import javax.jms.JMSException;
import javax.jms.MessageProducer;
import javax.jms.Queue;
import javax.jms.Session;
import javax.jms.TextMessage;

import org.apache.activemq.ActiveMQConnectionFactory;

public final class ClassicRetryPublisher {
    private static final String URL = "tcp://localhost:61616";
    private static final String USER = "app";
    private static final String PASSWORD = "lab-secret";
    private static final int MAX_ATTEMPTS = 4;

    public static void main(String[] args) throws Exception {
        // Chỉ để demo: trong production lấy eventId từ outbox đã commit.
        String eventId = UUID.randomUUID().toString();
        String payload =
                "{\"eventId\":\"" + eventId
                + "\",\"orderId\":\"O-1001\"}";

        publishWithRetry(eventId, payload);
    }

    static void publishWithRetry(String eventId, String payload)
            throws InterruptedException, JMSException {
        JMSException last = null;

        for (int attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
            try {
                sendOneTransaction(eventId, payload);
                System.out.println("Published eventId=" + eventId
                        + ", attempt=" + attempt);
                return;
            } catch (JMSException failure) {
                last = failure;

                // UNKNOWN: commit có thể đã thành công trên broker.
                System.err.println("Attempt " + attempt
                        + " uncertain for eventId=" + eventId
                        + ": " + failure.getMessage());

                if (attempt == MAX_ATTEMPTS) {
                    break;
                }

                long capMillis = Math.min(
                        8_000L, 250L << (attempt - 1));
                long delayMillis = ThreadLocalRandom.current()
                        .nextLong(capMillis + 1);
                Thread.sleep(delayMillis);
            }
        }

        // Caller/outbox phải giữ event ở trạng thái chờ hoặc unknown.
        throw new JMSException(
                "No confirmed publish after " + MAX_ATTEMPTS
                + " attempts for eventId=" + eventId
                + "; do not discard the event",
                last == null ? null : last.getErrorCode());
    }

    static void sendOneTransaction(String eventId, String payload)
            throws JMSException {
        ActiveMQConnectionFactory factory =
                new ActiveMQConnectionFactory(URL);

        Connection connection = null;
        Session session = null;
        MessageProducer producer = null;

        try {
            connection = factory.createConnection(USER, PASSWORD);
            session = connection.createSession(
                    true, Session.SESSION_TRANSACTED);

            Queue queue = session.createQueue("billing.commands");
            producer = session.createProducer(queue);
            producer.setDeliveryMode(DeliveryMode.PERSISTENT);

            TextMessage message = session.createTextMessage(payload);
            message.setJMSType("invoice.requested.v1");
            message.setStringProperty("eventId", eventId);

            producer.send(message);
            session.commit(); // Chỉ khi trả về thành công mới xác nhận publish.
        } finally {
            // Session chưa commit được đóng sẽ bỏ transaction còn pending.
            // Nếu commit phản hồi thất lạc, đóng local session không chứng minh
            // broker đã rollback; retry vẫn có thể sinh duplicate.
            closeQuietly(producer);
            closeQuietly(session);
            closeQuietly(connection);
        }
    }

    static void closeQuietly(MessageProducer producer) {
        if (producer != null) {
            try { producer.close(); }
            catch (JMSException ignored) { /* log ở production */ }
        }
    }

    static void closeQuietly(Session session) {
        if (session != null) {
            try { session.close(); }
            catch (JMSException ignored) { /* log ở production */ }
        }
    }

    static void closeQuietly(Connection connection) {
        if (connection != null) {
            try { connection.close(); }
            catch (JMSException ignored) { /* log ở production */ }
        }
    }
}
~~~

**Phân tích thiết kế:**

1. `eventId` được tạo **ngoài vòng retry**. Với outbox thật, nó phải được ghi bền trước khi dispatcher gửi, để restart không tạo ID khác.
2. Mỗi attempt tạo `Session.SESSION_TRANSACTED`. `producer.send()` và `session.commit()` thuộc một local JMS transaction.
3. Nếu `commit()` trả về bình thường, caller có bằng chứng publish đã hoàn tất theo provider. Nếu ném `JMSException`, caller coi kết quả **chưa chắc chắn**, ngay cả khi một bản có thể đã tồn tại trên broker.
4. Backoff có full jitter và số lần thử hữu hạn.
5. `Session`/`Connection` trong JMS 1.1 không phải `AutoCloseable`, nên dùng `finally` để đóng. Hàm `closeQuietly` tránh exception khi cleanup che lấp lỗi gửi ban đầu; production nên ghi log lỗi cleanup.
6. `JMSException` tạo sau khi hết số lần thử chứa thông báo “không có xác nhận publish”, **không phải khẳng định broker không có message**. Caller cần giữ event pending/unknown.

**Quan trọng:** code trên chưa cung cấp retry classification, timeout gửi, outbox bền, deduplication của broker hay idempotent consumer. Nó là phép thử vòng retry ở phía producer, không phải công thức chứng minh exactly-once. Tại production, chỉ retry lỗi có thể phục hồi và dùng một cơ chế kết nối/transport đã được kiểm soát thời gian.

### 6.1. Một cải tiến cần thiết: dừng retry khi lỗi vĩnh viễn

Thay vì catch mọi `JMSException` và retry, hệ thống thực nên phân loại lỗi theo provider:

~~~text
if credential/configuration/destination/authorization error:
    mark OUTBOX_BLOCKED; alert; không retry nhanh

if transient connection/broker unavailable:
    mark OUTBOX_PENDING; retry with backoff + jitter

if send/commit outcome unknown:
    mark OUTBOX_UNKNOWN; retry cùng eventId + deduplication
    hoặc đối soát theo hợp đồng nghiệp vụ
~~~

Không có một phương thức `isRetryable(JMSException)` chung cho mọi JMS provider. Classifier là adapter phụ thuộc client/broker version và loại lỗi thực tế; cần được kiểm thử bằng lỗi được tạo có chủ đích.

## 7. Classic Failover Transport: tránh hai tầng retry tranh nhau

ActiveMQ Classic Java client có **Failover Transport** để tự kết nối lại khi broker tạm thời không sẵn sàng. Ví dụ URL minh họa:

~~~text
failover:(tcp://broker-a:61616,tcp://broker-b:61616)?randomize=false&initialReconnectDelay=250&maxReconnectDelay=4000&maxReconnectAttempts=5
~~~

Tác dụng của failover transport là quản lý **reconnect/transport request replay theo cơ chế client Classic**. Nó không tự biến một thao tác nghiệp vụ thành exactly-once. Một request gửi bị gián đoạn và được client phục hồi không có cùng ranh giới quan sát với việc app **tự tạo message mới và gọi send lại**.

Nếu cùng lúc dùng:

- Failover transport có thời gian reconnect dài;
- vòng retry JMS ứng dụng có `maxAttempts`;
- scheduler replay outbox mỗi vài giây;

thì số kết nối, số yêu cầu gửi và thời gian chờ có thể khó dự đoán. Cần chọn **một ranh giới kiểm soát cho mỗi lớp**:

| Lớp | Trách nhiệm hợp lý | Không nên làm |
|---|---|---|
| Failover transport | Tái kết nối, xử lý gián đoạn network trong giới hạn cấu hình | Chờ vô hạn mà ứng dụng không có deadline |
| JMS send transaction | Xác nhận gửi bằng `commit()` | Suy từ `send()` rằng business đã hoàn tất |
| Outbox dispatcher | Giữ ý định publish, giới hạn retry, ghi attempt/unknown | Sinh event ID mới cho mỗi attempt |
| Consumer/business DB | Chống thực thi nghiệp vụ trùng | Coi JMSMessageID luôn là khóa duy nhất cho business event |

Nếu dùng `timeout`, `maxReconnectAttempts` hoặc tùy chọn async send của Classic, cần đọc tài liệu đúng phiên bản và thử tình huống broker chết trong lúc `send/commit`. **Timeout không chứng minh broker chưa chấp nhận message.** Đồng thời, client failover giữ/replay các message trong giới hạn cache và cơ chế riêng; đừng mặc định mọi cấu hình cache/replay đều an toàn với mọi tải và transaction.

## 8. Artemis duplicate detection: giảm nhân bản tại broker khi gửi lại

Artemis có cơ chế **duplicate message detection** riêng, sử dụng một **duplicate detection ID** gắn vào message. Đây là bổ sung hữu ích ở **đường gửi vào broker**, bên cạnh `eventId` ứng dụng và idempotent consumer.

Trong Artemis JMS client, có thể đặt property có tên `_AMQ_DUPL_ID` với ID ổn định cho cùng sự kiện:

~~~java
// Jakarta JMS, chỉ dùng với Artemis client/broker hỗ trợ cơ chế này.
TextMessage message = context.createTextMessage(payload);

message.setStringProperty("eventId", stableEventId);    // Nghiệp vụ
message.setStringProperty("_AMQ_DUPL_ID", stableEventId); // Broker Artemis

context.createProducer()
       .setDeliveryMode(DeliveryMode.PERSISTENT)
       .send(queue, message);
~~~

Khi Artemis nhận các message mang duplicate detection ID đã xuất hiện trong **bộ nhớ đệm ID của address**, broker có thể phát hiện và bỏ bản gửi trùng theo semantics của tính năng. Đây là cơ chế kiểm tra **ID của message tại broker**, không phải truy vấn trạng thái hóa đơn ở database.

### 8.1. Giới hạn của duplicate ID cache

- **Cache có kích thước hữu hạn**, ID có thể bị đẩy ra khi có nhiều message khác. Retry quá muộn có thể không còn bị phát hiện là trùng.
- Tùy cấu hình, cache có thể được persist; cần xác minh hành vi qua restart/failover/replication.
- Phạm vi nhận diện liên quan **address**, nên việc đổi address, topology, cluster hoặc đường routing có thể thay đổi kết quả.
- ID phải giống nhau **qua mọi attempt của cùng một sự kiện**, và phải khác nhau giữa hai sự kiện độc lập.
- Một ID bị tái sử dụng nhầm cho hai sự kiện khác nhau có thể khiến message hợp lệ bị bỏ.
- Tính năng duplicate detection **không thay thế unique key/idempotency ở database tiêu thụ**.

Cấu hình Artemis thường có các tham số lõi liên quan cache:

~~~xml
<!-- Các tham số minh họa bên trong <core> của broker.xml.
     Kiểm tra schema/phiên bản Artemis đang dùng. -->
<id-cache-size>20000</id-cache-size>
<persist-id-cache>true</persist-id-cache>
~~~

`id-cache-size` và `persist-id-cache` phải được đánh giá theo thông lượng, khoảng retry tối đa và topology HA. Ví dụ 20.000 ID ở mức 2.000 event/giây, nếu cache chủ yếu giữ các sự kiện khác nhau, chỉ tương ứng khoảng 10 giây lịch sử trong điều kiện đơn giản. Con số đó không đủ bảo vệ retry sau vài phút; không dùng phép chia này như một SLA chính thức mà phải đo với luồng thực.

**Không dùng property `_AMQ_DUPL_ID` như một yêu cầu JMS chuẩn bắt buộc ActiveMQ Classic cũng phải hiểu.** Tính năng này là đặc thù Artemis và cần kiểm tra khi client qua AMQP/OpenWire, bridge hoặc broker version khác. Một ứng dụng đa broker nên giữ `eventId` chuẩn riêng của mình và bật duplicate detection như tối ưu tương ứng từng broker.

### 8.2. Tách ba mức chống duplicate

| Mức | Cơ chế | Ngăn được gì? | Không bảo đảm gì? |
|---|---|---|---|
| **Producer/outbox** | Giữ event ID, giới hạn retry | Không sinh các sự kiện logic mới khi retry | Không chặn broker nhận hai bản cùng event |
| **Artemis broker** | `_AMQ_DUPL_ID` và duplicate ID cache | Bỏ một số bản gửi trùng còn nằm trong phạm vi cache | Không kiểm soát tác động DB hoặc duplicate ngoài cache |
| **Consumer DB** | Unique key/inbox, transaction nghiệp vụ | Không thực hiện business side effect hai lần cho cùng event | Không ngăn broker nhận/lưu hai message |

Cách nhìn này giúp tránh nhầm “broker đã bỏ message trùng” với “cả hệ thống đã đạt exactly-once”.

## 9. Transactional outbox: không mất ý định publish khi tiến trình chết

Vòng retry trong RAM chỉ hữu ích khi process vẫn còn sống. Nếu Order Service đã commit DB rồi crash trước khi đưa event vào broker, dữ liệu đơn hàng đã tồn tại nhưng `InvoiceRequested` có thể không bao giờ được gửi.

**Transactional outbox** giải quyết khoảng trống giữa database nghiệp vụ và thao tác phát message:

~~~mermaid
flowchart LR
    A["Business transaction"] --> B["Commit Order + Outbox row cùng DB transaction"]
    B --> C["Outbox dispatcher"]
    C -->|JMS send/commit| D["ActiveMQ queue"]
    C -->|publish được xác nhận| E["Đánh dấu SENT"]
    D --> F["Consumer"]
    F --> G["Inbox / unique event ID + business DB commit"]
    G --> H["ACK JMS"]
~~~

### 9.1. Ví dụ schema tối thiểu

Ví dụ PostgreSQL:

~~~sql
CREATE TABLE outbox_events (
    event_id        UUID PRIMARY KEY,
    event_type      TEXT NOT NULL,
    destination     TEXT NOT NULL,
    payload_json    TEXT NOT NULL,
    status          TEXT NOT NULL CHECK (status IN ('PENDING', 'SENT', 'BLOCKED')),
    attempts        INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    sent_at         TIMESTAMPTZ
);
~~~

Khi tạo đơn hàng, một transaction database ghi **đơn hàng và hàng outbox** cùng nhau:

~~~sql
BEGIN;

INSERT INTO orders(id, status) VALUES ('O-1001', 'CREATED');

INSERT INTO outbox_events(
    event_id, event_type, destination, payload_json, status)
VALUES (
    'b6a3ecb6-0d48-4b46-9a90-efcbba08ea45',
    'invoice.requested.v1',
    'billing.commands',
    '{"eventId":"b6a3ecb6-0d48-4b46-9a90-efcbba08ea45","orderId":"O-1001"}',
    'PENDING'
);

COMMIT;
~~~

Dispatcher chọn bản ghi pending đã đến hạn, **claim bằng cơ chế lease/lock phù hợp** để nhiều instance không cùng publish một hàng; đọc eventId/payload đã lưu, rồi gửi qua JMS. Khi send/commit được xác nhận, mới cập nhật `SENT`.

Nếu broker đã commit message nhưng dispatcher crash trước khi update `SENT`, hàng outbox vẫn pending và sẽ được gửi lại. Đây là hành vi có chủ ý: **at-least-once publish + eventId ổn định + idempotent consumer**.

### 9.2. Những lỗi cần tránh khi vận hành outbox

- Không xóa outbox row ngay khi gọi `send()` mà chưa có xác nhận/commit tương ứng.
- Không tạo lại `eventId` khi lấy lại một row sau process restart.
- Không đánh dấu `SENT` chỉ vì một lời gọi async đã được enqueue vào bộ đệm client.
- Không giữ transaction database đang lock row **trong nhiều giây/phút** chỉ để chờ broker reconnect; dùng lease/ownership có expiry và giới hạn timeout.
- Không làm mất khả năng retry khi `SENT` chưa ghi được; nếu broker có message rồi, bản retry phải giữ ID như cũ.
- Không xóa các hàng pending/unknown chỉ vì vượt ngưỡng retry. Có thể chuyển `BLOCKED` để vận hành xử lý, tùy mức độ quan trọng.
- Không dùng outbox làm lý do bỏ qua việc kiểm tra latency, queue lag và số bản duplicate thực tế.

### 9.3. Trạng thái nghiệp vụ nên diễn giải thế nào?

| Outbox status | Ý nghĩa đúng |
|---|---|
| `PENDING` | Cần tiếp tục publish; broker có thể đã nhận một bản nếu attempt trước không rõ kết quả |
| `SENT` | Dispatcher đã quan sát được kết quả publish thành công, chưa khẳng định Billing xử lý thành công |
| `BLOCKED` | Có lỗi cần sửa/duyệt trước khi tiếp tục; không đồng nghĩa event bị hủy |
| `UNKNOWN` (nếu hệ thống bổ sung) | Chưa xác nhận được outcome của một lần gửi; phải đối soát hoặc retry cùng ID |

Dòng nào đáng xem nhất khi điều tra duplicate? Các row có cùng `eventId` và nhiều lần gửi, cùng log broker/consumer cho biết thời điểm retry và lý do. Bản ghi `SENT` không có nghĩa “đã hóa đơn hóa”; nếu cần, hệ thống phải có business status hoặc phản hồi xác nhận riêng.

## 10. Idempotent consumer: ranh giới cuối để không nhân đôi nghiệp vụ

Producer kiểm soát số lần gửi nhưng không thể đảm bảo consumer không gặp duplicate do:

- Producer retry sau unknown commit.
- Broker/client replay một delivery sau network interruption.
- Consumer xử lý thành công rồi crash trước ACK.
- Vận hành replay lại message từ DLQ hoặc lịch sử outbox.

Consumer phải xử lý cùng `eventId` theo cách **an toàn khi lặp**. Ví dụ bảng inbox:

~~~sql
CREATE TABLE consumed_events (
    consumer_name TEXT NOT NULL,
    event_id      UUID NOT NULL,
    processed_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Trong **một database transaction** của consumer Billing:

~~~text
BEGIN DB TRANSACTION
  INSERT INTO consumed_events(consumer_name, event_id)
  VALUES ('billing-service', eventId)
  ON CONFLICT DO NOTHING
  RETURNING event_id

  Nếu INSERT thành công:
      Tạo invoice / cập nhật business state trong CÙNG DB transaction

  Nếu row đã tồn tại:
      Bỏ qua side effect vì event này đã xử lý
COMMIT DB TRANSACTION

Sau DB commit thành công -> ACK/commit JMS
~~~

Nếu database transaction thất bại, **không ACK message như đã xử lý**. Nếu DB commit xong nhưng JMS ACK thất bại, lần delivery lại tìm thấy inbox row và bỏ qua side effect, sau đó ACK an toàn.

**Điều kiện:** thao tác side effect và ghi inbox phải cùng transaction hoặc có cơ chế idempotency tương đương. Nếu consumer gọi API bên thứ ba (email, thanh toán), cần thêm khóa idempotency mà hệ bên ngoài hỗ trợ hoặc workflow riêng để tránh gọi trùng.

## 11. Bài kiểm thử fault injection: chứng minh duplicate xảy ra và được xử lý

Kiểm thử chỉ ở điều kiện broker ổn định sẽ không bộc lộ vấn đề. Thiết kế các tình huống sau với queue test, eventId rõ và cách quan sát cả producer lẫn consumer.

### Thử nghiệm A — Retry khi broker chưa nhận

1. Tắt broker trước khi tạo connection.
2. Lưu `EVT-A` với payload ổn định trong outbox; chạy dispatcher.
3. Quan sát attempt thất bại và backoff tăng dần.
4. Bật broker và cho dispatcher retry.
5. Kiểm tra queue nhận được thông điệp và outbox chuyển `SENT` khi publish được xác nhận.

**Kỳ vọng:** sau khi broker trở lại, message có thể được gửi thành công; không có outbox row nào biến mất do timeout.

### Thử nghiệm B — Phản hồi commit thất lạc

1. Sử dụng proxy mạng/test harness có thể cắt kết nối **sau khi broker đã commit** nhưng trước khi producer nhận response.
2. Producer nhìn thấy lỗi `commit()`; ghi trạng thái unknown, giữ nguyên `eventId=EVT-B`.
3. Cho dispatcher retry thành công.
4. Kiểm tra có thể tồn tại hai JMS messages cùng `EVT-B` nhưng `JMSMessageID` khác nhau.
5. Consumer với bảng inbox chỉ tạo **một** invoice và ACK tất cả delivery hợp lệ.

**Kỳ vọng:** ứng dụng không mất event và cũng không tạo hai hóa đơn. Lỗi rất khó tái hiện bằng việc “tắt broker ngẫu nhiên”; phải biết rõ thời điểm cắt response để minh họa outcome không chắc chắn.

### Thử nghiệm C — Dispatcher chết trước khi đánh dấu `SENT`

1. Gửi và commit message thành công.
2. Cố ý dừng dispatcher **trước** khi cập nhật outbox `SENT`.
3. Khởi động lại; dispatcher thấy outbox pending, gửi lại cùng ID.
4. Quan sát duplicate delivery và behavior của idempotent consumer.

**Kỳ vọng:** một event logic, có thể nhiều send attempts, **một business side effect**.

### Thử nghiệm D — Artemis duplicate detection

1. Khai báo queue `billing.commands` trên Artemis và bật cấu hình duplicate ID cache phù hợp.
2. Gửi hai message mang cùng `_AMQ_DUPL_ID=EVT-D` vào **cùng address**.
3. Quan sát broker chỉ chấp nhận message theo semantics duplicate-detection khi ID còn trong cache.
4. Thử hai ID khác nhau để chứng minh hai event độc lập vẫn được nhận.
5. Kiểm thử lại sau restart/HA theo `persist-id-cache`, sau khi cache có nhiều ID khác và sau khi đổi address để tìm giới hạn.

**Kỳ vọng:** cơ chế có thể chặn duplicate ngắn hạn tại broker, nhưng **inbox consumer vẫn cần thiết** cho duplicate đến ngoài phạm vi cache hoặc phát sinh ở đường khác.

### Thử nghiệm E — Lỗi vĩnh viễn

1. Dùng tài khoản không có quyền send hoặc một destination bị cấm.
2. Quan sát producer không tạo vòng retry nóng vô hạn.
3. Đưa row `BLOCKED`, alert đầy đủ mã lỗi, destination, eventId nhưng không log nội dung nhạy cảm.
4. Sau khi sửa quyền, duyệt phát lại cùng eventId.

**Kỳ vọng:** retry policy tách được lỗi phục hồi với lỗi cấu hình.

### Thử nghiệm F — Backpressure

1. Cho consumer dừng và gửi tải đủ lớn ở môi trường lab.
2. Quan sát producer latency, queue backlog, broker memory/store usage và kết quả timeout.
3. Thêm jitter/rate limiting, đo số attempt/phút khi broker đầy.
4. Khởi động consumer; kiểm tra backlog giảm và dispatcher tiếp tục gửi.

**Kỳ vọng:** retry không làm tắc nghẽn trầm trọng hơn; hệ thống có cơ chế giảm áp lực và không tự đốt CPU khi broker đã chậm.

## 12. Metric và log tối thiểu để vận hành retry

Một bộ log có cấu trúc cho mỗi attempt nên ghi:

~~~json
{
  "eventId": "EVT-1001",
  "destination": "billing.commands",
  "attempt": 3,
  "state": "UNKNOWN",
  "elapsedMs": 1700,
  "errorClass": "JMSException",
  "nextRetryDelayMs": 890
}
~~~

Tránh log toàn bộ payload nhạy cảm. Nếu có `JMSMessageID` sau khi send, dùng nó để tương quan với broker log, nhưng **eventId mới là khóa chính của một publish logic**.

Các metric hữu ích:

| Metric | Ý nghĩa |
|---|---|
| `outbox_pending_total` | Số event chưa có xác nhận publish |
| `outbox_oldest_age_seconds` | Thời gian chờ của event cũ nhất |
| `publish_attempts_total{result}` | Số lần thử theo success/unknown/rejected |
| `publish_retry_delay_seconds` | Backoff và áp lực kết nối |
| `publish_confirmed_latency_seconds` | Thời gian từ tạo event đến xác nhận publish |
| `duplicate_event_detected_total` | Consumer inbox hoặc broker phát hiện event trùng |
| `publish_blocked_total{reason}` | Lỗi không thể tự phục hồi |
| `broker_queue_depth`, `producer_send_latency` | Đánh giá backpressure và năng lực broker |

Alert phải xét **tuổi outbox pending** và **tỷ lệ lỗi**, không chỉ xem producer có đang retry hay không. Một hệ thống retry liên tục nhưng không bao giờ publish được vẫn là sự cố.

## 13. Các bẫy thường gặp

| Nhận định sai | Hệ quả | Cách đúng |
|---|---|---|
| “`send()` ném exception thì chắc broker chưa nhận.” | Retry có thể tạo bản thứ hai | Coi outcome sau send/commit là unknown khi không có chứng cứ |
| “JMS transaction cho exactly-once từ Order DB đến Billing DB.” | Giao dịch hai database/broker không tự nguyên tử | Outbox + inbox/idempotency hoặc XA được thiết kế, kiểm chứng riêng |
| “Retry phải sinh UUID mới để message luôn unique.” | Mất khả năng nhận biết cùng event | Một eventId ổn định qua mọi attempt |
| “Dùng JMSMessageID là đủ.” | Mỗi lần gửi mới có thể có ID khác | Dùng eventId nghiệp vụ |
| “Producer persistent không bao giờ gửi trùng.” | Nhầm độ bền với deduplication | Tách durability, retry và idempotency |
| “Retry 100 lần ngay lập tức giúp hệ thống hồi phục nhanh.” | Gây retry storm khi broker quá tải | Bounded retries + backoff + jitter + rate limit |
| “Failover transport bảo đảm không bao giờ nhân bản message.” | Không phủ hết retry từ app/outbox, unknown commit | Kiểm thử transport và xử lý duplicate ở tầng nghiệp vụ |
| “Artemis `_AMQ_DUPL_ID` thay thế consumer idempotency.” | Cache hữu hạn, có thể miss duplicate | Chỉ coi là lớp giảm duplicate bổ sung |
| “Đánh dấu outbox SENT trước commit broker để giảm latency.” | Có thể mất event vĩnh viễn khi broker gửi thất bại | Chỉ mark SENT sau xác nhận publish |
| “Hết 4 attempts thì xóa event.” | Mất ý định publish khi lỗi kéo dài | Giữ pending/blocked và có runbook |
| “Tạo lại message mỗi retry đồng nghĩa phải thay đổi payload.” | Hai bản cùng event mang payload mâu thuẫn | Persist payload/schema cùng eventId |
| “TTL JMS của retry tự giữ deadline nghiệp vụ cũ.” | Retry muộn làm sống lại event đã quá hạn | Lưu `businessExpiresAt` và kiểm tra trước gửi |

## 14. Checklist review producer trước production

- [ ] `eventId` được tạo một lần khi hình thành event và **lưu bền** cùng payload.
- [ ] Cơ chế publish hỗ trợ process restart, tránh bỏ quên các event chưa xác nhận.
- [ ] Lỗi đầu vào/quyền/cấu hình được phân loại khác lỗi tạm thời.
- [ ] Timeout `send/commit` được coi là **unknown** khi không thể chứng minh rollback.
- [ ] Mỗi attempt giới hạn thời gian; số attempts, backoff, jitter và total deadline đều có cấu hình.
- [ ] Chỉ có một ranh giới retry rõ giữa transport failover, JMS publisher và outbox dispatcher.
- [ ] Gửi `PERSISTENT`/transaction đúng yêu cầu, nhưng không suy ra đã xử lý nghiệp vụ.
- [ ] Nếu dùng Artemis duplicate detection, ID ổn định, cache có dung lượng/độ bền phù hợp, đã kiểm thử restart và retry ngoài cache.
- [ ] Consumer chống side effect trùng bằng event ID và transaction nghiệp vụ.
- [ ] Khi hết retry, event vẫn tồn tại trong hàng chờ hoặc trạng thái blocked cần xử lý.
- [ ] Metric cho pending age, attempt result, duplicate, broker backlog và cảnh báo đã sẵn sàng.
- [ ] Đã thử broker down, response mất giữa commit, dispatcher crash sau commit, backpressure và lỗi ACL.

## 15. Kết luận

Retry ở phía producer giải quyết bài toán **tăng khả năng gửi được message khi gặp lỗi tạm thời**; nó đồng thời tạo ra khả năng nhân bản khi broker đã nhận nhưng response bị mất. Cách thiết kế đúng là **giữ một eventId qua mọi attempt**, dùng **bounded retry với backoff/jitter và error classification**, lưu ý định publish bằng **transactional outbox**, và bảo đảm **consumer idempotent**.

ActiveMQ Classic có thể giúp với persistent delivery, transaction JMS và failover transport; Artemis bổ sung duplicate detection thông qua `_AMQ_DUPL_ID` và cache broker. Những cơ chế này cải thiện độ tin cậy, nhưng không thay thế hợp đồng nghiệp vụ về “một sự kiện, một tác động”, nhất là qua crash, retry muộn và các hệ thống database bên ngoài.
