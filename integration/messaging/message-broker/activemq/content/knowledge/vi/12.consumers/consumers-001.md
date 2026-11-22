# Nhận bằng receive, receiveNoWait và timeout

> **Chương:** Consumer  
> **Bối cảnh:** Java JMS/Jakarta Messaging với Apache ActiveMQ Classic và Apache Artemis. Các ví dụ chính dùng API `javax.jms` theo kiểu JMS 1.1; ý nghĩa nhận message áp dụng tương tự với `jakarta.jms` khi chọn đúng client.  
> **Mục tiêu:** Phân biệt nhận chờ vô hạn, nhận có thời hạn và nhận không chờ; lý giải đúng trường hợp trả về `null`; thiết kế vòng lặp consumer có khả năng dừng, xử lý lỗi và đo lường được.

## 1. Ba cách nhận: cùng một `MessageConsumer`, khác chính sách chờ

Giả sử dịch vụ `InvoiceWorker` tiêu thụ queue `invoices.issue`. Broker đang trống, rồi một producer gửi message sau 2 giây. Worker có ba lựa chọn:

| Lời gọi | Nếu đã có message sẵn để giao | Nếu hiện chưa có message phù hợp | Ý nghĩa |
|---|---|---|---|
| `consumer.receive()` | Trả về `Message` khi được delivery | **Chờ không giới hạn thời gian** cho đến khi có delivery hoặc sự kiện kết thúc/lỗi | Phù hợp consumer đồng bộ muốn chờ công việc |
| `consumer.receive(1500)` | Trả về `Message` khi được delivery | **Đợi tối đa khoảng 1.500 ms** ở thao tác nhận rồi trả `null` nếu hết thời gian | Phù hợp poll theo vòng lặp có kiểm tra tín hiệu dừng |
| `consumer.receiveNoWait()` | Có thể trả về `Message` đang khả dụng | **Trả ngay `null`** nếu không có message khả dụng ở thời điểm gọi | Phù hợp thử lấy việc trong vòng lặp sự kiện hoặc tiến trình có việc khác |

Cả ba phương thức đều là **nhận đồng bộ**: luồng Java gọi API và lấy message từ kết quả trả về. Chúng khác với `setMessageListener(...)`, nơi JMS provider gọi callback bất đồng bộ.

Một mô hình thời gian minh họa:

```text
Thời điểm:            0 ms       1500 ms       2000 ms
Broker có message:     -             -             M

receive():            [---------- chờ -----------] -> M
receive(1500):        [---- chờ ----] -> null
receiveNoWait():      [] -> null

Sau đó gọi receive(1500) lần nữa vào khoảng 1600 ms:
                      [---- chờ --- M] -> M
```

Các khoảng này là **minh họa**, không phải cam kết độ chính xác thời gian thực. Scheduling JVM, kết nối mạng, reconnect/failover và provider implementation có thể làm thời gian quan sát sai khác.

**Phân biệt quan trọng:** `receive(0)` có nghĩa là **chờ vô hạn**, tương đương mục đích của `receive()`; nó **không** có nghĩa “không chờ”. Muốn không chờ phải dùng `receiveNoWait()`. Chỉ truyền `timeout >= 0` theo hợp đồng API.

## 2. Điều kiện trước khi gọi receive: consumer phải thực sự được phép nhận

Một `MessageConsumer` gắn với một `Session`, còn Session thuộc một `Connection`. Đối với consumer đồng bộ, luồng khởi tạo phổ biến là:

```java
Connection connection = factory.createConnection();
Session session = connection.createSession(
        false, Session.AUTO_ACKNOWLEDGE);
Queue queue = session.createQueue("invoices.issue");
MessageConsumer consumer = session.createConsumer(queue);

connection.start();             // Bật việc giao message đến consumer
Message message = consumer.receive(1500);
```

### 2.1. `Connection.start()` là bước dễ quên

Sau khi tạo Connection, delivery thường ở trạng thái **stopped** cho đến khi gọi `connection.start()`. Vì vậy:

- Có message trong broker **không đồng nghĩa** `receiveNoWait()` nhận được nếu delivery chưa bật.
- `receive(timeout)` có thể hết thời gian và trả `null` dù queue đang có backlog khi connection vẫn stopped.
- `receive()` có thể chờ rất lâu vì không có delivery được bật.

`connection.start()` tác động tới **Connection**, nghĩa là những Session/consumer thuộc cùng Connection đều chịu ảnh hưởng. Không cho mỗi worker độc lập gọi `stop()/start()` trên một Connection dùng chung mà không có chủ sở hữu lifecycle.

### 2.2. Consumer chỉ nhận message phù hợp với destination và selector

```java
MessageConsumer vnConsumer = session.createConsumer(
        queue, "region = 'VN' AND eventType = 'IssueInvoice'");
```

Nếu queue đang có 100 message `region='SG'`, `vnConsumer.receive(1000)` vẫn có thể trả `null`. Trạng thái “queue không rỗng” và “có message phù hợp **để giao cho consumer này**” là hai điều khác nhau. Tương tự, message có thể đang được consumer khác giữ ở trạng thái *in-flight*, hoặc chưa đủ điều kiện giao do scheduled delivery, transaction, authorization hoặc flow control.

Với Topic, một non-durable subscriber chỉ nhận message theo vòng đời subscription của nó; tạo subscriber **sau** khi publisher gửi không biến `receive()` thành lệnh đọc lại lịch sử sự kiện. Durable subscription cũng cần được tạo trước thời điểm muốn lưu message khi subscriber offline.

## 3. `receive()`: khi nào nên chờ vô hạn?

`MessageConsumer.receive()` chặn luồng gọi cho tới khi nhận được message, consumer bị đóng hoặc gặp tình huống kết thúc/lỗi theo hợp đồng JMS và cách provider xử lý.

```java
Message message = consumer.receive();
if (message != null) {
    process(message);
}
```

Cách gọi này có ích với chương trình chuyên dụng có một consumer cần liên tục chờ job và cơ chế quản trị vòng đời do container/provider điều khiển. Tuy nhiên, trong dịch vụ Java tự quản lý thread, **chờ vô hạn khiến shutdown khó dự đoán**:

- Một cờ `running=false` không thể được kiểm tra nếu thread vẫn mắc trong `receive()`.
- `Thread.interrupt()` không phải một cơ chế hủy receive được chuẩn JMS bảo đảm hoạt động giống mọi provider.
- Khi broker mất kết nối, failover transport có thể tự reconnect và kéo dài thời gian chờ.
- Đóng Connection/consumer từ luồng khác trong khi receive đang chạy cần tuân thủ quy tắc lifecycle của provider; không coi mọi cách đóng đồng thời đều an toàn.

Nếu cần kiểm tra tín hiệu dừng, nên dùng `receive(timeout)` với khoảng chờ hữu hạn, hoặc giao việc quản lý consumer cho một listener container đã hỗ trợ shutdown.

**Không dùng `receive()` bên trong một HTTP request/response handler** nếu không có chính sách chờ cụ thể: request có thể treo khi không có message và làm cạn thread pool.

## 4. `receive(long timeout)`: giới hạn chờ nhận, không giới hạn toàn bộ nghiệp vụ

```java
Message message = consumer.receive(2_000L);
if (message == null) {
    // Không nhận được message phù hợp trong khoảng chờ của lần gọi.
} else {
    // Bắt đầu xử lý message.
}
```

Ở đây `2_000L` được đo theo **mili giây**. Nếu message khả dụng sớm hơn, method có thể trả ngay. Nếu không có message khả dụng trong khoảng chờ, kết quả thông thường là `null`.

### 4.1. Timeout của receive **không** phải các timeout khác

| Loại timeout | Nó giới hạn điều gì? | Có làm message hết hạn hoặc chuyển DLQ không? |
|---|---|---|
| `consumer.receive(2000)` | Thời gian chờ message ở **một lần gọi nhận** | **Không** |
| JMS message TTL/`JMSExpiration` | Vòng đời hợp lệ của message theo chính sách expiration | Có thể dẫn tới expiration/expiry address theo broker policy |
| Producer send/connection timeout | Quá trình gửi hoặc kết nối theo provider/config | Không phải timeout của consumer receive |
| Handler/DB timeout | Thời gian xử lý nghiệp vụ sau khi receive đã trả message | Không trực tiếp; transaction/rollback do app quản lý |
| Redelivery delay | Khoảng trễ trước khi broker giao lại message đã xử lý lỗi | Không phát sinh chỉ vì `receive()` trả `null` |
| Shutdown deadline | Tổng thời gian cho phép worker kết thúc | Phải phối hợp cả vòng lặp, xử lý nghiệp vụ và transport |

Một `receive(2000)` trả message sau 20 ms, rồi DB mất 10 giây mới xử lý xong: phương thức nhận **đã hoàn tất ở 20 ms**, còn toàn bộ bước nghiệp vụ kéo dài hơn 2 giây là hợp lệ. Muốn timeout end-to-end cần thiết kế riêng ở tầng app và nguồn dữ liệu.

### 4.2. Vì sao timeout hữu ích cho shutdown?

Một loop tiêu thụ có thể chủ động kiểm tra:

```java
while (running.get()) {
    Message message = consumer.receive(1_000L);
    if (message == null) {
        continue; // Có thể kiểm tra cờ running ở vòng tiếp theo.
    }
    process(message);
}
```

Nếu không có message, loop có dịp đọc cờ dừng sau mỗi lần timeout. Đây là cách đơn giản để tránh một luồng bị mắc trong `receive()` khi queue im lặng.

**Giới hạn thực tế:** `receive(1000)` không nhất thiết bảo đảm thread kết thúc trong đúng 1 giây khi có reconnect/failover đang diễn ra hoặc `process(message)` chưa xong. Shutdown deadline còn phụ thuộc cấu hình client, DB timeout và chính sách drain in-flight.

### 4.3. Đừng dùng timeout bằng 0 để thăm dò

```java
consumer.receive(0);       // Chờ vô hạn!
consumer.receiveNoWait();   // Không đợi message mới.
```

Lỗi `receive(0)` xuất hiện khi ứng dụng đọc timeout từ config: `timeoutMs` bị default thành `0` và lập trình viên tưởng “poll ngay”. Hãy validate config theo semantics:

```java
if (receiveTimeoutMs <= 0) {
    throw new IllegalArgumentException(
        "receiveTimeoutMs phải > 0 cho consumer cần kiểm tra shutdown");
}
```

## 5. `receiveNoWait()`: lấy ngay message khả dụng, tránh busy polling

```java
Message message = consumer.receiveNoWait();
if (message == null) {
    doOtherWork();
} else {
    process(message);
}
```

`receiveNoWait()` hữu ích khi luồng đã có lịch làm việc khác, ví dụ thăm dò queue vào các checkpoint hoặc một command-line tool muốn kiểm tra ngay có message sẵn không.

Nhưng **không nên dùng một vòng lặp gọi liên tục không có backoff**:

```java
// SAI: vòng spin có thể đốt CPU khi queue trống.
while (running.get()) {
    Message message = consumer.receiveNoWait();
    if (message != null) {
        process(message);
    }
}
```

Một vòng loop trống có thể chạy hàng triệu lần mỗi giây, gây CPU overhead và không làm broker nhận/giao message nhanh hơn. Với consumer chuyên dụng, `receive(500)` hoặc `receive(1000)` thường dễ vận hành hơn vì nó đợi có kiểm soát.

Nếu kiến trúc buộc phải dùng non-blocking poll, hãy đặt **tần suất thăm dò**, backoff hoặc scheduler; cũng cần quản lý race giữa poll và dispatch. Ví dụ đơn giản cho một ứng dụng có hai công việc:

```java
Message message = consumer.receiveNoWait();
if (message != null) {
    process(message);
} else {
    runPeriodicMaintenance();
    // Để scheduler hoặc nhịp chạy tiếp theo quyết định lúc poll lại.
}
```

### 5.1. `null` từ `receiveNoWait()` không chứng minh queue rỗng

Với ActiveMQ Classic và Artemis, message có thể được **prefetch/buffer** tới client, hoặc broker dispatch theo credit/window. `receiveNoWait()` trả `null` khi không có message **khả dụng cho lần gọi hiện tại**; đó không phải câu lệnh quản trị hỏi “QueueSize có bằng 0 không?”.

Ví dụ:

- Queue đang có 500 message nhưng đều không match selector của consumer.
- Consumer khác đã nhận trước và đang giữ in-flight chưa ack.
- Connection chưa `start()`.
- Message được scheduled cho thời điểm tương lai.
- Client đang reconnect; dispatch chưa tới consumer.
- Một transaction đang giữ delivery state, hoặc broker đang áp flow control.

Do đó, không dùng `receiveNoWait()==null` để quyết định “hệ thống đã xử lý hết backlog” hoặc “an toàn để xóa queue”.

## 6. Ví dụ Java thực hành: so sánh ba chế độ trên cùng queue

Ví dụ dưới đây dùng client ActiveMQ Classic với `javax.jms`. Có thể thay `ConnectionFactory` bằng client Artemis phù hợp mà **giữ nguyên logic JMS**. Lưu ý dependency client, protocol, Java version và namespace `javax.jms`/`jakarta.jms` phải khớp với môi trường.

### 6.1. Chương trình gửi một message

```java
import javax.jms.Connection;
import javax.jms.DeliveryMode;
import javax.jms.JMSException;
import javax.jms.MessageProducer;
import javax.jms.Queue;
import javax.jms.Session;
import javax.jms.TextMessage;
import org.apache.activemq.ActiveMQConnectionFactory;

public final class SendDemo {
    public static void main(String[] args) throws JMSException {
        ActiveMQConnectionFactory factory =
            new ActiveMQConnectionFactory("tcp://127.0.0.1:61616");

        Connection connection = factory.createConnection();
        try {
            Session session = connection.createSession(
                    false, Session.AUTO_ACKNOWLEDGE);
            try {
                Queue queue = session.createQueue("demo.receive.modes");
                MessageProducer producer = session.createProducer(queue);
                try {
                    producer.setDeliveryMode(DeliveryMode.PERSISTENT);

                    TextMessage message = session.createTextMessage("invoice-42");
                    message.setStringProperty("eventId", "invoice:42");
                    producer.send(message);
                    System.out.println("Sent JMSMessageID="
                            + message.getJMSMessageID());
                } finally {
                    producer.close();
                }
            } finally {
                session.close();
            }
        } finally {
            connection.close();
        }
    }
}
```

Ở ví dụ này, `connection.start()` không cần thiết cho **producer chỉ gửi**; thao tác `start()` phục vụ bật delivery tới consumer. Client gửi persistent message không có nghĩa consumer xử lý thành công; đây chỉ là fixture để quan sát ba cách receive.

### 6.2. Chương trình nhận theo tham số mode

```java
import javax.jms.Connection;
import javax.jms.JMSException;
import javax.jms.Message;
import javax.jms.MessageConsumer;
import javax.jms.Queue;
import javax.jms.Session;
import javax.jms.TextMessage;
import org.apache.activemq.ActiveMQConnectionFactory;

public final class ReceiveModesDemo {

    public static void main(String[] args) throws JMSException {
        if (args.length != 1) {
            System.err.println("Usage: ReceiveModesDemo nowait|timed|blocking");
            return;
        }

        ActiveMQConnectionFactory factory =
            new ActiveMQConnectionFactory("tcp://127.0.0.1:61616");

        Connection connection = factory.createConnection();
        try {
            Session session = connection.createSession(
                    false, Session.AUTO_ACKNOWLEDGE);
            try {
                Queue queue = session.createQueue("demo.receive.modes");
                MessageConsumer consumer = session.createConsumer(queue);
                try {
                    connection.start(); // Bắt buộc để bật delivery.

                    long beginNanos = System.nanoTime();
                    Message message;

                    switch (args[0]) {
                        case "nowait":
                            message = consumer.receiveNoWait();
                            break;
                        case "timed":
                            message = consumer.receive(1_500L);
                            break;
                        case "blocking":
                            message = consumer.receive(); // Có thể chờ vô hạn.
                            break;
                        default:
                            throw new IllegalArgumentException(
                                    "Unknown mode: " + args[0]);
                    }

                    long elapsedMs =
                            (System.nanoTime() - beginNanos) / 1_000_000L;

                    if (message == null) {
                        System.out.println("No message, waited " +
                                elapsedMs + " ms");
                    } else {
                        String body = message instanceof TextMessage
                                ? ((TextMessage) message).getText()
                                : "<non-text>";
                        System.out.println("Received " + body
                                + ", eventId=" +
                                message.getStringProperty("eventId")
                                + ", waited " + elapsedMs + " ms");
                    }
                } finally {
                    consumer.close();
                }
            } finally {
                session.close();
            }
        } finally {
            connection.close();
        }
    }
}
```

**Vì sao demo chọn `AUTO_ACKNOWLEDGE`?** Để quan sát riêng tác động của ba API nhận. Với synchronous receive thành công, provider tự ack theo semantics `AUTO_ACKNOWLEDGE` khi method nhận trả message. **Nếu chương trình crash khi xử lý sau `receive()`, message có thể đã được ack**; vì vậy demo không đại diện cho consumer nghiệp vụ cần bảo đảm retry.

Với hệ thống có database và không chấp nhận mất công việc, dùng transacted Session/rollback hoặc cơ chế acknowledgment được thiết kế rõ ở phần 8.

### 6.3. Ma trận chạy thử

Chạy trong queue test riêng đã được làm sạch bằng quy trình test, rồi thực hiện:

| Bước | Thao tác | Kỳ vọng |
|---|---|---|
| 1 | Queue trống; chạy `ReceiveModesDemo nowait` | Trả `null` gần như tức thì |
| 2 | Queue trống; chạy `ReceiveModesDemo timed` | Trả `null` sau khoảng 1.500 ms |
| 3 | Queue trống; chạy `ReceiveModesDemo blocking` | Tiếp tục chờ; gửi bằng `SendDemo` từ tiến trình khác |
| 4 | Sau khi gửi, quan sát lệnh blocking | Nhận message và kết thúc |
| 5 | Gửi trước bằng `SendDemo` rồi chạy `timed` | Thường trả message nhanh khi đã sẵn sàng |
| 6 | Gửi trước bằng `SendDemo` rồi chạy `nowait` | Có thể nhận ngay nếu đã dispatch; **không dùng một lần null để kết luận queue rỗng** |

Để so sánh công bằng, cần reset queue/broker test về trạng thái dự kiến giữa các lần chạy; message đã nhận và auto-ack không còn nằm pending như lúc đầu. Khi message đang có consumer khác, độ trễ và kết quả có thể thay đổi.

## 7. Mẫu consumer chạy lâu: timed receive + transacted Session

Mẫu dưới đây phù hợp dịch vụ Java tự quản lý worker. Mỗi worker **tự tạo Session và MessageConsumer**, nhận với timeout hữu hạn, commit JMS khi hoàn tất nghiệp vụ và rollback khi xử lý lỗi. Đây là khung cơ chế, chưa bao gồm orchestration, JDBC, metrics hay connection recovery hoàn chỉnh.

```java
import java.util.concurrent.atomic.AtomicBoolean;
import javax.jms.Connection;
import javax.jms.ConnectionFactory;
import javax.jms.JMSException;
import javax.jms.Message;
import javax.jms.MessageConsumer;
import javax.jms.Queue;
import javax.jms.Session;
import javax.jms.TextMessage;

public final class InvoiceWorker implements Runnable {

    private final ConnectionFactory factory;
    private final AtomicBoolean running = new AtomicBoolean(true);

    public InvoiceWorker(ConnectionFactory factory) {
        this.factory = factory;
    }

    public void requestStop() {
        running.set(false);
    }

    @Override
    public void run() {
        Connection connection = null;
        Session session = null;
        MessageConsumer consumer = null;

        try {
            connection = factory.createConnection();
            session = connection.createSession(
                    true, Session.SESSION_TRANSACTED);
            Queue queue = session.createQueue("invoices.issue");
            consumer = session.createConsumer(queue);
            connection.start();

            while (running.get()) {
                Message message = consumer.receive(1_000L);
                if (message == null) {
                    continue; // Không có transaction xử lý message để commit.
                }

                try {
                    if (!(message instanceof TextMessage)) {
                        throw new IllegalArgumentException("Expected TextMessage");
                    }
                    String eventId = message.getStringProperty("eventId");
                    String payload = ((TextMessage) message).getText();

                    issueInvoiceOnce(eventId, payload); // Phải idempotent.
                    session.commit(); // Ack việc nhận trong JMS transaction.
                } catch (JMSException | RuntimeException error) {
                    try {
                        session.rollback(); // Cho phép redelivery theo policy.
                    } catch (JMSException rollbackFailure) {
                        error.addSuppressed(rollbackFailure);
                        throw rollbackFailure;
                    }
                    // Production: log có eventId, metrics và retry/backoff.
                    System.err.println("Rolled back invoice: " + error);
                }
            }
        } catch (JMSException error) {
            // Production: báo unhealthy, supervisor tái tạo tài nguyên.
            System.err.println("JMS worker stopped: " + error);
        } finally {
            closeQuietly(consumer);
            closeQuietly(session);
            closeQuietly(connection);
        }
    }

    private static void issueInvoiceOnce(String eventId, String payload) {
        if (eventId == null || eventId.isEmpty()) {
            throw new IllegalArgumentException("Missing eventId");
        }
        // Production: dùng unique eventId trong DB transaction cùng side effect.
        System.out.println(eventId + " -> " + payload);
    }

    private static void closeQuietly(MessageConsumer consumer) {
        if (consumer != null) {
            try { consumer.close(); }
            catch (JMSException error) { System.err.println(error); }
        }
    }

    private static void closeQuietly(Session session) {
        if (session != null) {
            try { session.close(); }
            catch (JMSException error) { System.err.println(error); }
        }
    }

    private static void closeQuietly(Connection connection) {
        if (connection != null) {
            try { connection.close(); }
            catch (JMSException error) { System.err.println(error); }
        }
    }
}
```

### 7.1. Cách dừng mà không cắt ngang transaction

Coordinator giữ `InvoiceWorker worker` và `Future<?> future`, rồi:

1. Ngừng cấp việc mới ở tầng ứng dụng (nếu có).
2. Gọi `worker.requestStop()`.
3. Đợi worker kết thúc lần `receive(1000)` hiện tại hoặc xử lý xong message đã nhận; đặt thời hạn chờ shutdown phù hợp.
4. Đọc kết quả từ `Future` để phát hiện exception; nếu worker không dừng đúng hạn, có quy trình escalation theo provider.
5. Đóng Connection/Session/consumer **trong owner worker** khi vòng lặp kết thúc.

Trong ví dụ, mỗi worker có Connection riêng để giữ ownership rõ ràng. Nếu dùng **Connection chung** cho nhiều workers, chỉ coordinator nên quản lý lifecycle Connection; mỗi worker vẫn cần Session/consumer riêng.

**Không mặc định `Future.cancel(true)` sẽ ngắt được lệnh JMS receive đang block** hoặc dừng JDBC side effect một cách an toàn. Đặt timeout ở cả tầng broker client/DB, quản lý shutdown theo framework và kiểm thử stop/failover thật.

### 7.2. Vì sao `receive(timeout)==null` không gọi `rollback()`?

Khi receive chưa trao message nào, không có message vừa nhận để đánh dấu lỗi xử lý. `null` chỉ là “lần gọi chưa có message khả dụng”, **không phải message poison hoặc delivery failure**. Không đẩy vào DLQ, không tăng retry counter và không log error liên tục.

Nếu application cố thực hiện nhiều thao tác send/receive khác trong cùng transacted Session, cần xét phạm vi transaction đang tồn tại. Mẫu `InvoiceWorker` ở trên chủ ý chỉ xử lý **một message rồi commit/rollback** để ranh giới rõ ràng.

## 8. Acknowledgment: thời điểm receive trả message không đồng nghĩa đã xử lý nghiệp vụ

Cả ba method đều trả `Message` hoặc `null`; độ tin cậy lại phụ thuộc **acknowledgment mode và transaction** của Session.

| Chế độ Session | Sau khi `receive*` trả message | Khi business handler lỗi |
|---|---|---|
| `AUTO_ACKNOWLEDGE` | Provider tự acknowledge theo semantics nhận đồng bộ; message có thể đã được ack trước khi business logic phía sau chạy xong | Exception trong business code **không tự làm broker redeliver** message đã auto-ack |
| `CLIENT_ACKNOWLEDGE` | Message chưa được ack cho tới khi gọi `acknowledge()` theo hợp đồng Session | Có thể dùng `session.recover()` để yêu cầu redelivery của message chưa ack; cần hiểu phạm vi ack |
| `SESSION_TRANSACTED` | Message nhận thuộc transaction hiện tại | `session.rollback()` khiến message chưa commit đủ điều kiện redelivery; `commit()` xác nhận |
| Provider-specific mode | Theo tài liệu client/broker | Không suy diễn từ JMS chuẩn khi dùng extension |

Với `CLIENT_ACKNOWLEDGE`, **một lời gọi `message.acknowledge()` trong JMS 1.1 có phạm vi tất cả message đã được Session đó tiêu thụ**, không chỉ object message đang gọi. Nếu nhận A rồi B trong cùng Session và ack B, A cũng được ack theo semantics. Không chia sẻ cùng Session cho nhiều thread đang xử lý độc lập.

### 8.1. Lỗi nguy hiểm: dùng `AUTO_ACKNOWLEDGE` cho nghiệp vụ chậm

```java
Session session = connection.createSession(
        false, Session.AUTO_ACKNOWLEDGE);

Message message = consumer.receive(1_000L);
// Đến đây một message trả về thành công có thể đã auto-ack.
writeInvoiceToDatabase(message); // Có thể throw hoặc process crash.
```

Nếu DB write thất bại sau receive, không thể mặc định broker sẽ giao lại. Với công việc phải hoàn thành, dùng **transacted Session** hoặc một acknowledgment strategy phù hợp và thiết kế idempotency ở DB. Kể cả với transacted Session, nếu DB commit xong nhưng JVM chết trước JMS commit, message có thể redeliver, vì vậy vẫn phải chống trùng.

### 8.2. Timeout không làm thay đổi delivery count

```java
Message message = consumer.receive(500L);
if (message == null) {
    // Không có message được giao ở lần gọi này.
}
```

Không có message được trả về thì không có việc “nhận thất bại” để broker tự tăng `JMSXDeliveryCount` hoặc chuyển DLQ. Retry/redelivery áp dụng khi broker **đã delivery message** và sau đó thấy transaction/ack không hoàn tất hoặc xử lý theo policy lỗi. Lặp lại `receive(500)` trên queue trống 100 lần không được coi là 100 redelivery.

### 8.3. Khi consumer crash sau DB commit

```mermaid
sequenceDiagram
    participant B as Broker
    participant C as Consumer
    participant D as Database
    B->>C: deliver message eventId=evt-42
    C->>D: INSERT invoice + processed_event(evt-42)
    D-->>C: DB commit
    Note over C: Process chết trước session.commit()
    B->>C: Redelivery trên consumer mới
    C->>D: processOnce(evt-42)
    D-->>C: Đã xử lý; không phát sinh hóa đơn thứ hai
    C->>B: JMS session.commit()
```

Muốn bảo đảm **một lần tác dụng phụ nghiệp vụ**, dùng unique `eventId`/constraint trong DB transaction cùng side effect. `receive(timeout)` chỉ giúp điều phối đợi message, không giải quyết vấn đề transaction phân tán này.

## 9. ActiveMQ Classic và Artemis: vì sao cùng API có thời điểm trả khác nhau?

JMS chuẩn hóa cách ứng dụng gọi `receive`, còn broker/client thực thi **dispatch, prefetch/credits và failover** khác nhau. Hai hệ thống có cùng queue depth vẫn có thể có latency nhận khác nhau.

### 9.1. ActiveMQ Classic: prefetch theo số message

ActiveMQ Classic có `prefetch policy`, thường tính theo **số message**. Broker có thể đẩy trước message tới consumer. Một lần `receiveNoWait()` đọc được message đã khả dụng ở client sẽ nhanh; nhưng `null` vẫn không nói chắc queue broker trống.

Ví dụ cấu hình cho riêng consumer queue bằng client Classic:

```java
import org.apache.activemq.ActiveMQConnectionFactory;
import org.apache.activemq.ActiveMQPrefetchPolicy;

ActiveMQConnectionFactory factory =
        new ActiveMQConnectionFactory("tcp://127.0.0.1:61616");

ActiveMQPrefetchPolicy prefetch = new ActiveMQPrefetchPolicy();
prefetch.setQueuePrefetch(20); // Ví dụ, không phải giá trị tối ưu chung.
factory.setPrefetchPolicy(prefetch);
```

**Đừng tăng prefetch để sửa mọi trường hợp `receiveNoWait()==null`**. Prefetch lớn có thể tăng message in-flight, dùng nhiều RAM client, làm mất cân bằng consumer hoặc làm thời gian redelivery sau crash kéo dài.

### 9.2. Artemis Core JMS: consumer window và credit

Artemis Core JMS có cơ chế client-side flow control với `consumerWindowSize` thường tính bằng **byte**, không giống Classic `queuePrefetch` tính theo số message.

```java
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

ActiveMQConnectionFactory factory =
        new ActiveMQConnectionFactory("tcp://127.0.0.1:61616");

factory.setConsumerWindowSize(256 * 1024); // 256 KiB, giá trị thử nghiệm.
```

Window/credits ảnh hưởng lượng message có thể được đẩy tới client, memory và độ trễ. Với Artemis đang dùng OpenWire hoặc AMQP, cơ chế client/protocol có thể khác, nên không áp một tham số cho mọi giao thức.

**Đo đạc thực tế:** dùng cùng workload, số consumer, message size, selector, ack mode, persistence và network latency để so sánh `receive(timeout)`/`receiveNoWait()`. Đừng suy hiệu năng chỉ từ tên broker.

### 9.3. Queue metrics để giải thích một lần receive trả null

Khi consumer liên tục không nhận được message mà dashboard báo queue có backlog, cần đối chiếu:

- Pending/ready message count, delivering/in-flight, scheduled và expired.
- Consumer count và destination thực tế, gồm tên/case và Queue so với Topic.
- Selector hoặc queue filter; durable subscription identity.
- Connection started/stopped, reconnect/failover và authentication/authorization.
- Prefetch/consumer window và khả năng dispatch.
- Broker đang tắc nghẽn, flow control, memory/page/disk hoặc consumer khác giữ message chưa ack.

Đặc biệt: **queue depth = 0** chưa chắc đồng nghĩa toàn bộ business work đã xong; message có thể ở trạng thái in-flight và chưa commit. `receiveNoWait()==null` còn cung cấp ít thông tin hơn queue depth.

## 10. Không trộn synchronous receive với `MessageListener` trên cùng consumer/Session

Có hai mô hình khác nhau:

**Synchronous polling:**

```java
Message m = consumer.receive(1_000L);
if (m != null) {
    process(m);
}
```

**Asynchronous listener:**

```java
consumer.setMessageListener(m -> process(m));
// Provider/container gọi callback khi có delivery.
```

Trên một consumer/Session, không cố vừa gọi `receive*` từ thread ứng dụng vừa để provider gọi `onMessage()`. Việc chia quyền sở hữu Session/consumer không đúng có thể gây race và hành vi không được JMS đảm bảo.

Một Session là ngữ cảnh **một luồng tại một thời điểm**. Nếu muốn xử lý nhiều message song song, tạo **nhiều Session + consumer** hoặc dùng listener container với mức concurrency đã cấu hình; không tạo 10 threads cùng gọi `receive()` trên một consumer.

Trong Spring, `JmsTemplate.receive(...)` có cơ chế **receive timeout** được cấu hình bằng `setReceiveTimeout(...)`; nếu dùng `@JmsListener`, container thường quản lý nhận/ack và thread. Không nên vừa gọi `JmsTemplate.receive` vừa dùng listener container để tranh cùng message nếu thiết kế không chủ ý. Khi dùng Spring Boot 3/Jakarta, namespace import là `jakarta.jms`; chọn provider client phù hợp.

## 11. Chọn API theo tình huống

| Tình huống | Lựa chọn hợp lý | Điều kiện đi kèm |
|---|---|---|
| Công cụ CLI một lần: lấy message nếu đã có | `receiveNoWait()` | Không diễn giải `null` thành “queue trống tuyệt đối” |
| Worker tự quản lý cần shutdown dự đoán được | `receive(500–2000)` theo đo đạc | Có cờ dừng, xử lý in-flight, session transaction và timeout downstream |
| Consumer chuyên dụng do provider/container quản lý | `receive()` hoặc listener container | Có cơ chế stop/close/recovery đã kiểm thử |
| HTTP request cần chờ reply JMS | `receive(timeout)` ở request/reply consumer được quản lý phù hợp | Timeout end-to-end, correlation ID, cleanup temporary destination; không treo vô hạn |
| Ứng dụng vừa poll queue vừa làm việc khác | `receiveNoWait()` theo scheduler, hoặc timeout ngắn | Không busy-spin, có backoff/nhịp thăm dò |
| Throughput cao với nhiều worker | N Sessions/consumers hoặc listener container | Concurrency, prefetch/window, DB pool, idempotency, backpressure |
| Không được phép mất công việc khi handler lỗi | `SESSION_TRANSACTED` + bounded receive | Commit sau xử lý; rollback, redelivery, DLQ và idempotency |

Nếu hệ thống là consumer message thuần túy, thường không có ích khi “kiểm tra queue mỗi 10 ms bằng `receiveNoWait()`”; broker vốn có thể đợi và đánh thức consumer khi delivery sẵn sàng. Dùng `receive(timeout)` hoặc listener container giúp tránh polling nóng.

## 12. Thực hành kiểm chứng có thể lặp lại

### Bài A — Phân biệt `receive(0)` và `receiveNoWait()`

1. Tạo queue test trống, bật `connection.start()`.
2. Cho thread test gọi `receiveNoWait()` và đo thời gian.
3. Cho một thread khác gọi `receive(0)`, sau 2 giây mới gửi message.
4. Đối chiếu kết quả và thời gian.

**Đạt:** `receiveNoWait()` trả `null` ngay khi không có message khả dụng; `receive(0)` chờ cho tới khi có delivery. Thực hiện ở test process có đường dừng rõ, tránh tạo thread treo ngoài ý muốn.

### Bài B — Timeout không kéo theo DLQ

1. Queue trống, consumer dùng transacted Session gọi `receive(250)` liên tiếp 20 lần.
2. Ghi `null` và số lần chờ; đọc queue metrics, redelivery count và DLQ.
3. Gửi một message rồi nhận và commit.

**Đạt:** 20 lần `null` không làm message bị retry hay chuyển DLQ. Một khi có message và consumer xử lý thành công, broker mới ghi nhận ack/commit.

### Bài C — Thiếu `connection.start()`

1. Tạo Connection/Session/consumer nhưng chưa gọi `start()`.
2. Gửi một message persistent vào queue test từ producer khác.
3. Gọi `receive(500)`, sau đó `connection.start()` rồi gọi `receive(1500)`.
4. Kiểm tra queue và message nhận được.

**Đạt:** giải thích được vì sao connection stopped ngăn delivery và việc bật start thay đổi khả năng nhận. Không suy ra message mất chỉ từ `null` lúc connection chưa start.

### Bài D — Selector khiến một queue có backlog nhưng consumer nhận null

1. Gửi 10 message có property `region='SG'`.
2. Tạo consumer selector `region='VN'` và gọi `receive(1000)`.
3. Kiểm tra pending queue và số message in-flight.
4. Tạo consumer khác không selector (hoặc selector SG) để nhận.

**Đạt:** consumer VN có thể `null` mặc dù queue vẫn còn message; kiểm chứng bằng backlog và consumer SG.

### Bài E — AUTO_ACK so với transaction

1. Với `AUTO_ACKNOWLEDGE`, nhận message rồi cố tình gây lỗi DB sau khi method receive trả message.
2. Quan sát khả năng nhận lại message.
3. Lặp lại với `SESSION_TRANSACTED` và `rollback()` khi DB lỗi.
4. Cho DB xử lý thành công, `commit()`, rồi đối chiếu số business effects duy nhất theo `eventId`.

**Đạt:** phân biệt timeout với ack/rollback và giải thích được vì sao cần transaction + idempotency.

### Bài F — Shutdown và reconnect

1. Chạy `InvoiceWorker` trên queue trống, gọi `requestStop()` và đo thời gian kết thúc.
2. Gửi message để worker đang xử lý, gọi requestStop giữa handler, xác nhận xử lý/commit hoặc rollback đúng trước khi đóng tài nguyên.
3. Trong môi trường test, ngắt kết nối broker khi consumer đang `receive(timeout)`.
4. Quan sát exception, failover delay và thời gian shutdown thực tế, thêm cấu hình supervisor/recovery nếu cần.

**Đạt:** không dựa duy nhất vào `Thread.interrupt()`; có cơ chế vận hành rõ khi client mất kết nối hoặc handler bị kẹt.

### Bảng thu kết quả

| Test | API | Queue ready | Selector/connection | Đo thời gian | Trả về | Kết luận |
|---|---|---:|---|---|---|---|
| A1 | `receiveNoWait()` | 0 | started | | `null` | |
| A2 | `receive(0)` | 0→1 sau 2s | started | | Message | |
| B | `receive(250)` x20 | 0 | started, tx | | `null` x20 | |
| C1 | `receive(500)` | 1 | stopped | | `null` | |
| C2 | `receive(1500)` | 1 | started | | Message | |
| D | `receive(1000)` | 10 | selector VN, data SG | | `null` | |
| E | `receive(1500)` | 1 | transacted rollback | | Message/redelivery | |

Khi đo, ghi thêm phiên bản Classic/Artemis, client namespace, protocol (OpenWire/Core/AMQP), prefetch/window, delivery mode, consumer count và số message in-flight; đây là điều kiện giúp so sánh kết quả có ý nghĩa.

## 13. Những lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân thường gặp | Kiểm tra/sửa |
|---|---|---|
| `receive()` “treo” mãi | Queue im lặng, thiếu `connection.start()`, selector sai, connection đang reconnect | Xác minh start/selector/consumer count; dùng timeout hữu hạn nếu cần stop |
| `receive(0)` không thoát khi queue trống | `0` nghĩa là chờ vô hạn | Đổi thành số ms dương hoặc `receiveNoWait()` |
| `receiveNoWait()` trả `null` dù console QueueSize > 0 | Prefetch/dispatch, selector, message in-flight, stopped connection, scheduling | So sánh ready/delivering, selector và connection status |
| CPU cao khi queue rỗng | Gọi `receiveNoWait()` trong vòng spin | Dùng `receive(timeout)` hoặc scheduler/backoff |
| Consumer nhận message nhưng DB lỗi không redeliver | `AUTO_ACKNOWLEDGE` đã ack khi receive trả về | Dùng transacted Session/ack strategy phù hợp |
| Message bị xử lý hai lần sau restart | DB commit xảy ra trước JMS commit | Idempotency theo `eventId` trong DB |
| Mọi worker ngừng nhận sau `connection.stop()` | Connection dùng chung bị worker khác stop | Coordinator sở hữu lifecycle |
| Timeout 1 giây nhưng shutdown lâu | Handler/DB đang chạy, failover/transport kéo dài, cleanup blocking | Đo từng pha, timeouts downstream và shutdown orchestration |
| Poll nhiều lần `null` rồi message cuối cùng vào DLQ | Nhầm nguyên nhân; retry/DLQ đến từ rollback hoặc policy khác | Truy log delivery attempts, DLQ reason, transaction boundary |
| 10 threads cùng gọi `receive` nhưng throughput tệ | Dùng chung Session/consumer trái semantics | Mỗi worker một Session/consumer, điều chỉnh concurrency |

## 14. Checklist trước khi đưa consumer vào production

- [ ] Biết chính xác khi nào nên dùng `receive()`, `receive(timeout)` và `receiveNoWait()`.
- [ ] Không nhầm `receive(0)` với non-blocking.
- [ ] Connection đã `start()` trước khi mong đợi nhận message.
- [ ] Không dùng `null` làm bằng chứng queue trống hoặc message hết hạn.
- [ ] Receive loop có timeout hữu hạn khi cần kiểm tra shutdown, không busy-spin.
- [ ] Session/consumer không bị nhiều thread dùng đồng thời.
- [ ] Ack/commit diễn ra sau khi business side effect đã hoàn thành theo hợp đồng.
- [ ] Có rollback/redelivery/DLQ khi handler lỗi; có idempotency khi message giao lại.
- [ ] Prefetch/consumer window được đo theo payload, latency, concurrency và memory.
- [ ] Khi không nhận được message, kiểm tra selector, destination, in-flight, stopped connection và scheduled message.
- [ ] Có metrics cho số `null`/idle polls, receive wait latency, handler duration, ack/rollback, reconnect và queue age.
- [ ] Thử cả các trường hợp broker offline, graceful shutdown, pending message và message đang xử lý.
- [ ] Chốt namespace và client artifact phù hợp với ActiveMQ Classic/Artemis và phiên bản framework.

## 15. Tài liệu tra cứu chính thức

1. [JMS MessageConsumer API (`javax.jms`)](https://docs.oracle.com/javaee/7/api/javax/jms/MessageConsumer.html): `receive()`, `receive(long)`, `receiveNoWait()`.
2. [JMS Connection API](https://docs.oracle.com/javaee/7/api/javax/jms/Connection.html): ý nghĩa `start()` và `stop()` cho delivery.
3. [JMS Session API](https://docs.oracle.com/javaee/7/api/javax/jms/Session.html): transaction và acknowledgment.
4. [Jakarta Messaging specification](https://jakarta.ee/specifications/messaging/3.1/): semantics hiện đại của JMS/Jakarta Messaging.
5. [ActiveMQ Classic — Prefetch](https://activemq.apache.org/components/classic/documentation/what-is-the-prefetch-limit-for): dispatch và prefetch theo message count.
6. [Apache ActiveMQ Artemis — Flow Control](https://artemis.apache.org/components/artemis/documentation/latest/flow-control.html): credits/consumer window.
7. [Spring Framework — JMS Integration](https://docs.spring.io/spring-framework/reference/integration/jms.html): synchronous receive qua `JmsTemplate` và listener containers.

> **Ghi nhớ:** `receive()` chờ không giới hạn, `receive(timeout>0)` chờ hữu hạn, `receiveNoWait()` thử lấy message ngay. **`null` chỉ có nghĩa lần gọi chưa nhận được message phù hợp**; không chứng minh queue rỗng, không kích hoạt retry/DLQ và không xác định thành bại nghiệp vụ. Ack/transaction, connection lifecycle và xử lý lỗi phải được thiết kế riêng với chính sách chờ.
