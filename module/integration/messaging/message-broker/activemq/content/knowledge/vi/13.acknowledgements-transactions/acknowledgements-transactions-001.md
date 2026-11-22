# AUTO_ACKNOWLEDGE và thời điểm xác nhận theo cách nhận thông điệp

> **Chương:** Xác nhận và giao dịch  
> **Phạm vi:** Apache ActiveMQ Classic và Apache ActiveMQ Artemis thông qua Java/JMS. Bài tập trung vào **thời điểm xác nhận tự động** khi consumer dùng phương thức nhận đồng bộ so với callback **MessageListener** bất đồng bộ; các hệ quả khi mã nghiệp vụ phát sinh lỗi và cách kiểm chứng bằng broker.

## 1. Câu hỏi thực sự của AUTO_ACKNOWLEDGE

Giả sử một consumer đọc lệnh **ChargePayment** và gọi dịch vụ thanh toán. Khi nào broker được quyền coi message đã được consumer tiếp nhận xong?

Với chế độ **Session.AUTO_ACKNOWLEDGE** (hoặc **JMSContext.AUTO_ACKNOWLEDGE**), ứng dụng **không gọi message.acknowledge()** để xác nhận từng message. JMS provider quyết định mốc xác nhận theo **cách consumer nhận message**:

| Cách nhận | Mốc xác nhận theo hợp đồng JMS | Hệ quả đối với phần xử lý nghiệp vụ |
|---|---|---|
| **Đồng bộ:** MessageConsumer.receive(), receive(timeout), receiveNoWait() | Sau khi lần gọi **receive** trả về thành công một message cho ứng dụng | Mã xử lý **sau** receive chạy khi message về mặt JMS đã được xác nhận |
| **Đồng bộ qua API đơn giản:** JMSConsumer.receive(), receiveBody(...) | Tương tự: sau khi lệnh nhận trả về thành công | Lỗi sau khi lấy body không tự hoàn tác việc nhận |
| **Bất đồng bộ:** MessageListener.onMessage(message) do JMS provider gọi | Khi callback **onMessage** hoàn tất và **trả về thành công** | Công việc phải thực sự hoàn tất **trước khi callback trở về** nếu muốn gắn nó với mốc ack tự động |

**Mốc quy định ở trên là mốc logic của JMS API.** ACK trên wire, việc gom nhiều ACK, cập nhật bộ đếm hoặc ghi trạng thái bền vững tại broker có thể được provider tối ưu hóa. Vì thế không suy luận từng ACK frame hay từng lần flush đĩa từ thời điểm một dòng Java được thực thi.

Những điểm không thay đổi dù dùng ActiveMQ Classic hay Artemis:

- **AUTO_ACKNOWLEDGE chỉ nói về xác nhận phía messaging**, không chứng thực transaction của database hoặc cổng thanh toán ngoài.
- **Không có thao tác rollback ứng dụng** tương ứng trong một non-transacted AUTO_ACKNOWLEDGE session.
- Nếu consumer hoặc kết nối chết **trước khi mốc xác nhận hoàn thành**, broker có thể giao lại; thời điểm phát lại tùy chính sách và nhà cung cấp.
- Với lỗi trong **MessageListener**, đặc biệt khi callback ném **RuntimeException**, **không được giả định mọi provider chắc chắn redeliver theo cùng cách**. Muốn quyết định rõ commit/rollback, dùng session transacted và thiết kế idempotency.

**Kết quả học tập:** tự vẽ được vị trí ACK trong hai timeline; dự đoán được hậu quả của lỗi trước/sau mốc đó; chạy thử để phân biệt một message **đã dispatch**, **đã ack** và **đã hoàn thành nghiệp vụ**.

## 2. Timeline A: nhận đồng bộ qua receive()

Consumer gọi **receive()** hoặc **receive(timeout)** trên một MessageConsumer và nhận được một Message.

~~~mermaid
sequenceDiagram
    participant C as Consumer
    participant J as JMS Provider
    participant B as Broker
    participant DB as Database
    C->>J: receive(5000)
    J->>B: Nhận / dispatch message khi có thể
    B-->>J: Message M
    J-->>C: receive trả về M thành công
    Note over C,J: AUTO_ACKNOWLEDGE: mốc xác nhận của receive
    C->>DB: Bắt đầu xử lý nghiệp vụ
    DB-->>C: Lỗi / timeout
    Note over C: Lỗi sau receive không rollback ACK
~~~

Chú ý điều kiện **“trả về thành công một message”**:

- **receive()** chờ tới khi có message hoặc kết nối/consumer bị đóng hay xảy ra lỗi.
- **receive(5000)** chờ tối đa khoảng 5 giây; nếu không có message thì trả về **null**. Không có message nào để ack.
- **receiveNoWait()** trả về ngay; nếu không có message thì cũng không có ACK.
- Khi có message, về mặt JMS ACK tự động gắn với thao tác **receive** đã hoàn tất, **không** đợi khối code tiếp theo của ứng dụng hoàn thành.

### 2.1. Ví dụ lỗi sau receive

~~~java
import javax.jms.JMSContext;
import javax.jms.JMSConsumer;
import javax.jms.Message;
import javax.jms.Queue;

// factory là ConnectionFactory tương thích với broker.
// Queue "lab.autoack.sync" đã được provision trên broker test.
try (JMSContext ctx = factory.createContext(
        user, password, JMSContext.AUTO_ACKNOWLEDGE)) {

    Queue queue = ctx.createQueue("lab.autoack.sync");
    JMSConsumer consumer = ctx.createConsumer(queue);

    Message message = consumer.receive(5000);
    if (message == null) {
        System.out.println("Queue đang trống");
        return;
    }

    System.out.println("Nhận " + message.getJMSMessageID());

    // Lỗi xảy ra SAU khi receive đã trả về thành công.
    // Nó không làm provider tự hủy ACK trong AUTO_ACKNOWLEDGE.
    throw new IllegalStateException("Database không phản hồi");
}
~~~

Trong điều kiện chạy bình thường với provider hoạt động đúng, **message đã được ACK khi receive trả về**. Thay việc ném exception bằng một vòng retry nghiệp vụ cũng không biến message trở lại queue. Nếu tiến trình chết trong một cửa sổ lỗi mạng/ACK chưa được broker ghi nhận, vẫn có khả năng redelivery, nhưng **không nên dựa vào sự cố đó để thiết kế retry**.

### 2.2. Sai lầm thường gặp với đồng bộ

~~~java
Message m = consumer.receive(5000);
if (m != null) {
    try {
        chargeCard(m);  // Có thể lỗi.
    } catch (Exception e) {
        // Sai kỳ vọng: không có cơ chế AUTO_ACK "để nguyên message"
        // chỉ vì code xử lý trả lỗi ở đây.
        logError(e);
    }
}
~~~

Nếu **chargeCard** lỗi sau receive, message có thể đã hoàn tất ở tầng messaging. Ứng dụng không thể chỉ **ném lại exception** và mong broker biết rằng cần rollback một ACK đã hoàn tất.

**Nhận xét thiết kế:** AUTO_ACKNOWLEDGE + synchronous receive là lựa chọn phù hợp khi việc mất cơ hội retry tự động sau lần nhận **được chấp nhận**, hoặc khi ứng dụng đã có cơ chế lưu công việc riêng. Với **thanh toán, thay đổi tồn kho, tác vụ không thể bỏ sót**, cần chiến lược xác nhận có kiểm soát hơn.

## 3. Timeline B: nhận bất đồng bộ qua MessageListener.onMessage()

Khi JMS provider gọi một **MessageListener**, ứng dụng xử lý message trong callback. Với AUTO_ACKNOWLEDGE, mốc xác nhận logic nằm **sau khi onMessage kết thúc bình thường**.

~~~mermaid
sequenceDiagram
    participant B as Broker
    participant J as JMS Provider
    participant L as MessageListener
    participant DB as Database
    B->>J: Dispatch message M
    J->>L: onMessage(M)
    L->>DB: Xử lý nghiệp vụ đồng bộ
    DB-->>L: Thành công
    L-->>J: onMessage trả về bình thường
    Note over J,B: AUTO_ACKNOWLEDGE: ACK cho callback thành công
    J->>B: ACK theo cơ chế provider
~~~

Khác biệt thiết yếu với **receive()**: phần xử lý **bên trong onMessage** nằm trước mốc ACK logic. Tuy nhiên, điều này chỉ có ý nghĩa nếu callback **thực sự đợi** công việc xử lý hoàn tất.

### 3.1. Listener xử lý đồng bộ và trả về thành công

~~~java
consumer.setMessageListener(message -> {
    try {
        // Thực hiện nghiệp vụ đồng bộ tại đây.
        // Không trả về trước khi thao tác cần thiết hoàn tất.
        processAndCommitBusinessResult(message);

        // Khi onMessage trở về bình thường, JMS provider
        // có thể thực hiện AUTO_ACKNOWLEDGE.
    } catch (Exception e) {
        // Cần chiến lược lỗi được kiểm chứng;
        // xem mục 4 về exception và redelivery.
        throw new IllegalStateException("Xử lý thất bại", e);
    }
});
~~~

**Điều nên hiểu chính xác:** callback trả về bình thường là tín hiệu JMS provider dùng để hoàn thành ACK tự động. Nó **không kiểm tra** rằng database của ứng dụng đã commit; nếu **processAndCommitBusinessResult** chỉ gửi việc sang nơi khác rồi trả về, provider vẫn thấy callback thành công.

### 3.2. “Fire-and-forget trong callback” dễ ACK quá sớm

~~~java
consumer.setMessageListener(message -> {
    executor.submit(() -> {
        // Chạy sau trên thread khác.
        updateDatabase(message);
    });

    // onMessage trả về ngay:
    // AUTO_ACKNOWLEDGE có thể ACK trước khi task bắt đầu.
});
~~~

Ngay cả khi **executor.submit** thành công, task có thể thất bại, process có thể crash hoặc executor có thể bị shutdown. Broker không biết kết quả task vì callback đã trả về.

Nếu công việc bắt buộc xử lý xong trước ACK:

- Làm xong việc và kiểm tra kết quả **trong callback** trước khi trở về; hoặc
- Dùng kiến trúc có transaction/idempotency và cơ chế ack chủ động; hoặc
- Lưu yêu cầu bền vững vào một inbox/database trước khi callback trả về, rồi để worker khác xử lý theo một workflow có recovery.

Không chặn callback vô hạn nếu downstream chậm; đặt timeout, giới hạn mức đồng thời và định nghĩa rõ hậu quả sau timeout.

## 4. Listener ném exception: điểm khác với việc tự rollback

Đây là phần dễ bị hiểu quá mức. Với AUTO_ACKNOWLEDGE, **một callback ném RuntimeException không biến session thành transacted session**. JMS provider nhận biết callback kết thúc bất thường, nhưng **hành vi redelivery/đình chỉ consumer/ghi log có thể khác nhau giữa provider và cấu hình**.

| Kết quả trong onMessage | Mốc ACK theo AUTO_ACKNOWLEDGE | Điều cần quan sát |
|---|---|---|
| Xử lý xong, callback **return bình thường** | ACK tự động được tiến hành theo semantics listener | Queue không còn message chờ sau khi ACK hoàn tất |
| Bắt exception, **log rồi return** | Provider thấy callback **thành công** và có thể ACK message | Message lỗi có thể bị mất cơ hội retry |
| Ném **RuntimeException** ra ngoài callback | Không phải một lần callback thành công; provider xử lý lỗi theo implementation/policy | Có redelivery hay không, delay, delivery count, lỗi trong broker log |
| Task gửi sang executor rồi return | ACK có thể hoàn tất trước khi task xử lý | Lỗi task không làm message tự trở lại queue |
| Commit DB rồi process crash trước ACK của listener | Broker có thể redeliver message | Cần idempotency để không lặp hiệu ứng nghiệp vụ |

### 4.1. Bắt exception rồi bỏ qua là cách biến lỗi thành “thành công”

~~~java
consumer.setMessageListener(message -> {
    try {
        writeToDatabase(message);
    } catch (RuntimeException ex) {
        logger.error("Cannot process", ex);
        // Không throw lại, không có transaction:
        // callback kết thúc bình thường → AUTO_ACK.
    }
});
~~~

Đây là lỗi nghiêm trọng khi hệ thống kỳ vọng message được phát lại lúc database tạm dừng. **Log lỗi không thay đổi trạng thái ACK.**

### 4.2. Ném exception cũng không phải chính sách retry đủ tin cậy

~~~java
consumer.setMessageListener(message -> {
    validateAndProcess(message);
    // Nếu validateAndProcess ném RuntimeException ra ngoài:
    // cần đo hành vi của đúng JMS provider và redelivery policy.
});
~~~

Trong triển khai thực, Classic và Artemis có **redelivery policy / delivery attempt / DLQ** riêng. Phần xử lý RuntimeException còn phụ thuộc client, session, connection và framework listener container. Vì thế không viết yêu cầu nghiệp vụ kiểu **“cứ throw thì chắc chắn broker retry N lần”** mà chưa kiểm chứng.

**Khi cần rollback chắc chắn ở mức JMS**, dùng **SESSION_TRANSACTED** và **commit/rollback** có chủ đích (mục 8). Khi cần đảm bảo hiệu ứng nghiệp vụ, bổ sung **inbox/idempotency** vì transaction JMS riêng không bao trùm database ngoài.

## 5. Mốc ACK và trạng thái broker là hai tầng khác nhau

**ACK logic** là hợp đồng của API. Phía broker còn quản lý **message đã dispatch**, **in-flight/delivering**, **pending**, **dequeue/ack count** và storage.

~~~text
Broker queue:
  [Pending message] → [Dispatched / delivering] → [Acknowledged / removed]

Consumer sync AUTO_ACK:
  receive trả về Message
                 ↑ Mốc ACK logic gắn với lần receive thành công
  xử lý nghiệp vụ bắt đầu sau đó

Consumer async AUTO_ACK:
  onMessage bắt đầu → xử lý nghiệp vụ → onMessage return
                                        ↑ Mốc ACK logic
~~~

**Không suy luận “messageCount = 0” nghĩa là database cập nhật xong.** Broker có thể đã dispatch message ra phía client, trong khi application vẫn đang xử lý; cách tính từng counter tùy broker/version.

### 5.1. Client prefetch và ACK tối ưu

ActiveMQ Classic có cơ chế **prefetch**, và một số cấu hình client có thể **tối ưu/gom ACK**. Artemis có cơ chế **consumer window/credit** và dispatch khác. Chúng ảnh hưởng số message được broker đẩy sẵn và thời điểm nhìn thấy các counter thay đổi.

Điều quan trọng:

- **Dispatched** không đồng nghĩa **acknowledged**.
- Một message ở bộ đệm client vẫn có thể chưa được giao cho code nghiệp vụ.
- Cấu hình tối ưu có thể khiến **thời điểm gửi ACK qua network** khác với mốc logic của API.
- Không dùng độ trễ của dashboard hoặc số ACK frame để định nghĩa lại AUTO_ACKNOWLEDGE.

Để phân tích một phép thử, ghi song song **log ở trước/sau receive hoặc onMessage**, **message count**, **delivering count**, **ack/dequeue count** và **JMSRedelivered** nếu provider cung cấp.

## 6. Ví dụ chạy được: so sánh receive với MessageListener

Bài lab dùng **API JMS 2.x với namespace javax.jms** và **ActiveMQ Artemis JMS client**. Khi dùng ActiveMQ Classic, cần thay client factory bằng **org.apache.activemq.ActiveMQConnectionFactory** của Classic tương thích, đảm bảo đúng broker/protocol. Nếu dự án đã ở **jakarta.jms**, thay API và client library tương ứng; không trộn namespace.

**Chuẩn bị:**

1. Một broker Artemis thử nghiệm có acceptor Core phù hợp, ví dụ **tcp://localhost:61616** khi thực tế được cấu hình như vậy.
2. Provision hai **ANYCAST queues** riêng: **lab.autoack.sync** và **lab.autoack.listener**, hoặc cấu hình auto-create trong namespace lab; tránh dùng queue nghiệp vụ thật.
3. Tài khoản được quyền send/consume; đặt **MQ_URL**, **MQ_USER**, **MQ_PASSWORD** qua môi trường.
4. Maven/Gradle có dependency **org.apache.activemq:artemis-jms-client** tương thích với Java/JMS của dự án. Không pin phiên bản không phù hợp broker.
5. Một message thử sẽ được dùng cho mỗi lượt; nếu queue có dữ liệu cũ phải kiểm tra hoặc dọn riêng trong môi trường lab.

Chương trình hỗ trợ năm chế độ:

- **send-sync** / **send-listener**: gửi một message persistent tới queue tương ứng.
- **sync-fail**: đọc đồng bộ rồi cố tình phát sinh lỗi sau khi receive trả về.
- **listen-ok**: callback làm xong việc rồi return.
- **listen-catch**: callback giả lập lỗi, bắt exception rồi return bình thường.

~~~java
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import javax.jms.ConnectionFactory;
import javax.jms.DeliveryMode;
import javax.jms.JMSConsumer;
import javax.jms.JMSContext;
import javax.jms.Message;
import javax.jms.Queue;
import javax.jms.TextMessage;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

public final class AutoAckTimingLab {
    private static final String SYNC_QUEUE = "lab.autoack.sync";
    private static final String LISTENER_QUEUE = "lab.autoack.listener";

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                "Use send-sync | send-listener | sync-fail "
                + "| listen-ok | listen-catch");
        }

        String mode = args[0];
        String url = required("MQ_URL");
        String user = required("MQ_USER");
        String password = required("MQ_PASSWORD");

        ConnectionFactory factory =
            new ActiveMQConnectionFactory(url);

        switch (mode) {
            case "send-sync":
                send(factory, user, password, SYNC_QUEUE);
                break;
            case "send-listener":
                send(factory, user, password, LISTENER_QUEUE);
                break;
            case "sync-fail":
                receiveThenFail(factory, user, password);
                break;
            case "listen-ok":
                listen(factory, user, password, false);
                break;
            case "listen-catch":
                listen(factory, user, password, true);
                break;
            default:
                throw new IllegalArgumentException("Unknown mode: " + mode);
        }
    }

    private static void send(ConnectionFactory factory,
                             String user, String password,
                             String queueName) throws Exception {
        try (JMSContext ctx = factory.createContext(
                 user, password, JMSContext.AUTO_ACKNOWLEDGE)) {

            Queue queue = ctx.createQueue(queueName);
            String id = UUID.randomUUID().toString();
            TextMessage message = ctx.createTextMessage(
                "{\"type\":\"LabJob\",\"id\":\"" + id + "\"}");
            message.setStringProperty("jobId", id);

            ctx.createProducer()
               .setDeliveryMode(DeliveryMode.PERSISTENT)
               .send(queue, message);

            System.out.println("Sent jobId=" + id
                + " JMSMessageID=" + message.getJMSMessageID());
        }
    }

    private static void receiveThenFail(
            ConnectionFactory factory, String user, String password)
            throws Exception {
        try (JMSContext ctx = factory.createContext(
                 user, password, JMSContext.AUTO_ACKNOWLEDGE)) {

            Queue queue = ctx.createQueue(SYNC_QUEUE);
            JMSConsumer consumer = ctx.createConsumer(queue);
            Message message = consumer.receive(5000);

            if (message == null) {
                System.out.println("No message in five seconds");
                return;
            }

            System.out.println("receive() RETURNED jobId="
                + message.getStringProperty("jobId"));
            System.out.println("JMSRedelivered="
                + message.getJMSRedelivered());

            // Lỗi sau khi receive thành công không thu hồi AUTO_ACK.
            throw new IllegalStateException(
                "Injected business failure AFTER receive()");
        }
    }

    private static void listen(
            ConnectionFactory factory, String user, String password,
            boolean catchFailure) throws InterruptedException {

        try (JMSContext ctx = factory.createContext(
                 user, password, JMSContext.AUTO_ACKNOWLEDGE)) {

            // Chủ động start sau khi listener đã được đăng ký.
            ctx.setAutoStart(false);
            Queue queue = ctx.createQueue(LISTENER_QUEUE);
            JMSConsumer consumer = ctx.createConsumer(queue);
            CountDownLatch callbackReturned = new CountDownLatch(1);

            consumer.setMessageListener(message -> {
                try {
                    System.out.println("onMessage BEGIN jobId="
                        + message.getStringProperty("jobId"));

                    if (catchFailure) {
                        try {
                            throw new IllegalStateException(
                                "Injected DB failure");
                        } catch (RuntimeException ex) {
                            System.out.println(
                                "Caught and swallowed: "
                                + ex.getMessage());
                            // Thao tác nghiệp vụ vẫn FAILED.
                        }
                    } else {
                        // Lab chỉ log; thay bằng transaction thực ở ứng dụng.
                        System.out.println("Business work SUCCESS");
                    }

                    System.out.println("onMessage RETURN NORMALLY");
                } catch (Exception ex) {
                    // Chuyển exception có checked type thành RuntimeException
                    // để minh họa đúng contract của MessageListener.
                    throw new IllegalStateException(ex);
                } finally {
                    callbackReturned.countDown();
                }
            });

            ctx.start();

            if (!callbackReturned.await(10, TimeUnit.SECONDS)) {
                System.out.println("No callback within ten seconds");
            }
            // callbackReturned báo đã vào finally, không phải ACK từ broker;
            // quan sát broker metrics để xác nhận kết quả cuối.
            consumer.close();
        }
    }

    private static String required(String name) {
        String value = System.getenv(name);
        if (value == null || value.trim().isEmpty()) {
            throw new IllegalArgumentException(
                "Missing environment variable: " + name);
        }
        return value;
    }
}
~~~

**Chú ý về CountDownLatch:** callback gọi **countDown()** trong **finally**, tức là latch chỉ xác nhận callback đã chạy tới phần kết thúc, **không phải một tín hiệu broker đã ghi ACK**. Khi listener trả về bình thường, provider mới hoàn thành mốc xác nhận; cần đọc queue/ACK metrics sau khi consumer đóng ổn định.

### 6.1. Kịch bản 1 — Đồng bộ, lỗi sau receive

~~~text
Terminal A:
    AutoAckTimingLab send-sync

Terminal B:
    AutoAckTimingLab sync-fail

Quan sát:
    receive() RETURNED jobId=...
    Exception: Injected business failure AFTER receive()
~~~

Sau khi consumer **sync-fail** thoát, đợi broker cập nhật trạng thái rồi đọc queue **lab.autoack.sync**. Trong điều kiện bình thường, message đã được ACK ở lần receive trả về, nên **không tự động trở lại queue chỉ vì business code ném exception**.

Nếu message bất ngờ xuất hiện lại, đừng vội kết luận “AUTO_ACKNOWLEDGE retry lỗi nghiệp vụ”; cần kiểm tra provider log, kết nối bị lỗi trước ACK, consumer cũ, jobId và policy redelivery.

### 6.2. Kịch bản 2 — Listener trả về sau xử lý thành công

~~~text
Terminal A:
    AutoAckTimingLab send-listener

Terminal B:
    AutoAckTimingLab listen-ok

Log:
    onMessage BEGIN jobId=...
    Business work SUCCESS
    onMessage RETURN NORMALLY
~~~

Theo JMS, xác nhận tự động xảy ra **sau khi onMessage kết thúc thành công**. Với queue còn một message duy nhất, broker sẽ tiến đến trạng thái đã ack và không còn pending/in-flight sau khi xử lý ổn định.

### 6.3. Kịch bản 3 — Listener nuốt exception

~~~text
Terminal A:
    AutoAckTimingLab send-listener

Terminal B:
    AutoAckTimingLab listen-catch

Log:
    onMessage BEGIN jobId=...
    Caught and swallowed: Injected DB failure
    onMessage RETURN NORMALLY
~~~

Mặc dù thao tác nghiệp vụ giả lập thất bại, callback **trả về bình thường**. Với AUTO_ACKNOWLEDGE, provider có cơ sở để ACK message. Đây là bài học quan trọng hơn việc chỉ nhìn exception trong log.

**Không chạy đồng thời listen-ok và listen-catch trên cùng một queue khi đo từng kịch bản**: competing consumers có thể chia message, khiến phép thử không còn xác định consumer nào nhận.

## 7. Bài thử lỗi ngay trong MessageListener

Muốn khảo sát RuntimeException, sửa tạm callback của **môi trường lab** để ném exception ra khỏi onMessage:

~~~java
consumer.setMessageListener(message -> {
    System.out.println("onMessage ENTER");
    throw new IllegalStateException("Intentional listener failure");
});
~~~

Giữ kết nối đủ lâu, ghi:

- Broker/Java client đang dùng (Classic/OpenWire hay Artemis/Core), phiên bản và cấu hình.
- Lần đầu message được giao, giá trị **JMSRedelivered** và **JMSXDeliveryCount** nếu provider cung cấp.
- Callback có được gọi lại không, có delay hay bị consumer ngắt không?
- Broker log, queue pending/delivering, dequeue/ack counter và DLQ.
- Sau khi dừng consumer, message thực tế đang ở đâu?

**Không khẳng định số lần redelivery cố định** nếu chưa đặt policy. Càng không dùng việc ném RuntimeException làm “lệnh rollback JMS” có đảm bảo tương đương **SESSION_TRANSACTED**.

Nếu listener chạy qua một **framework container** như Spring JMS, phải kiểm tra chế độ listener container và session mà framework sử dụng. Một container có thể nhận message **bằng receive() nội bộ rồi gọi business listener**, làm mốc ACK quan sát được khác với việc trực tiếp đăng ký **MessageListener** trên JMSConsumer. Không suy từ chữ **AUTO_ACKNOWLEDGE** trong file Spring rằng callback ứng dụng luôn được gọi trước ACK.

## 8. Khi AUTO_ACKNOWLEDGE không đáp ứng yêu cầu nghiệp vụ

Một hệ thống cần retry đáng tin cậy cho **payment command**, **trừ tồn kho**, **ghi nhận hóa đơn** thường phải kiểm soát thời điểm hoàn tất message.

### 8.1. So sánh ngắn giữa các chế độ

| Session mode | Quyền kiểm soát ACK/rollback | Khi phù hợp |
|---|---|---|
| **AUTO_ACKNOWLEDGE** | Provider xác nhận ở mốc receive / callback thành công | Xử lý nhanh, chấp nhận rủi ro lỗi sau sync receive hoặc có recovery riêng |
| **CLIENT_ACKNOWLEDGE** | Ứng dụng chủ động gọi **message.acknowledge()** sau xử lý; ACK có thể bao gồm **mọi message đã tiêu thụ chưa ACK trong session** | Cần ack sau nghiệp vụ, chấp nhận quản lý session cẩn thận |
| **SESSION_TRANSACTED** | Ứng dụng **commit()** hoặc **rollback()** JMS session | Cần quyết định rõ hoàn tất hoặc redelivery |
| **DUPS_OK_ACKNOWLEDGE** | Provider được phép lazy-ack, có thể có duplicate delivery nhiều hơn | Workload chấp nhận duplicate và có idempotency |

Bảng chỉ nhắc những khác biệt cần thiết để quyết định trong bài này; cơ chế transaction, client ack và DLQ có thể nghiên cứu sâu ở các chủ đề riêng.

### 8.2. Chuyển từ sync AUTO_ACK sang transaction JMS

~~~java
try (JMSContext ctx = factory.createContext(
        user, password, JMSContext.SESSION_TRANSACTED)) {

    Queue queue = ctx.createQueue("billing.payment.commands.v1");
    Message message = ctx.createConsumer(queue).receive(5000);

    if (message != null) {
        try {
            // Cần có idempotency và transaction nghiệp vụ ở đây.
            processAndCommitBusinessResult(message);

            ctx.commit();   // Hoàn tất receive ở cấp JMS.
        } catch (RuntimeException ex) {
            ctx.rollback(); // Message đủ điều kiện redelivery theo policy.
            throw ex;
        }
    }
}
~~~

**Thứ tự đúng:** commit nghiệp vụ phù hợp trước, commit JMS sau. Nhưng vẫn còn **cửa sổ lỗi giữa hai commit**, vì session JMS không tự động là một transaction với database ngoài. Nếu database đã commit rồi tiến trình chết trước JMS commit, broker có thể phát lại message.

Giải quyết bằng **commandId/eventId** ổn định và **idempotent inbox/unique constraint**, hoặc dùng thiết kế tích hợp giao dịch khác được đánh giá riêng. Không hứa “exactly-once business effect” chỉ bằng cách đổi AUTO_ACKNOWLEDGE thành SESSION_TRANSACTED.

### 8.3. Với client acknowledge

~~~java
try (JMSContext ctx = factory.createContext(
        user, password, JMSContext.CLIENT_ACKNOWLEDGE)) {

    Queue queue = ctx.createQueue("lab.manualack.commands");
    Message message = ctx.createConsumer(queue).receive(5000);
    if (message != null) {
        processAndCommitBusinessResult(message);
        message.acknowledge();
    }
}
~~~

Mẫu này đẩy thời điểm xác nhận đến sau xử lý; tuy vậy, **CLIENT_ACKNOWLEDGE theo JMS không nhất thiết chỉ xác nhận message duy nhất đang cầm trong tay**: với cùng một session, nó thường xác nhận mọi message đã tiêu thụ trước đó mà session chưa ACK. Nếu phải quản lý độc lập từng message, thiết kế session/consumer và concurrency cẩn thận, hoặc dùng transaction phù hợp.

## 9. Khác biệt Classic và Artemis cần xác minh

**Quy tắc mốc ACK** ở mục 1 xuất phát từ API JMS nên giống nhau ở mức hợp đồng. Nhưng hành vi thực tế khi lỗi và metrics cần đối chiếu sản phẩm, phiên bản và client:

| Chủ đề kiểm chứng | ActiveMQ Classic | ActiveMQ Artemis |
|---|---|---|
| Client Java điển hình | ActiveMQ Classic JMS client, thường OpenWire | Artemis JMS client, thường Core; phiên bản/namespace phải khớp |
| Consumer buffering | Prefetch policy | Consumer window/credits và dispatch |
| ACK tối ưu | Có các tùy chọn client như optimized acknowledgement trong những cấu hình/version | Cơ chế client/protocol riêng; không áp mặc định Classic |
| Lỗi listener | RuntimeException, kết nối/session và redelivery policy theo client/broker | RuntimeException, consumer delivery policy và address-settings |
| Gửi lại, DLQ | Redelivery và dead-letter strategy riêng | max-delivery-attempts, redelivery delay, dead-letter-address trong address-settings |
| Quan sát | Queue metrics qua console/JMX và log client | Queue/consumer metrics, management API/console và log |

**Cách kiểm tra chuẩn:** chạy đúng mã với đúng client–protocol, đọc counter trước/sau mỗi lần; nếu thay Classic bằng Artemis, không giả định cùng tên metric hoặc cùng hành vi khi listener ném exception.

### 9.1. Ba sai lầm do trộn các lớp

- **Nhầm prefetched với acknowledged:** broker đã đẩy message vào client buffer chưa có nghĩa nghiệp vụ hoàn tất.
- **Nhầm AUTO_ACKNOWLEDGE với redelivery guarantee:** callback exception có thể dẫn đến hành vi riêng của provider; xác nhận phụ thuộc mốc nhận.
- **Nhầm ack của JMS với commit database:** broker không quan sát transaction bên ngoài. Idempotency và outbox/inbox giải quyết các cửa sổ lỗi liên hệ hai hệ thống.

## 10. Checklist kiểm chứng thời điểm ACK

Trước khi chấp nhận một consumer dùng **AUTO_ACKNOWLEDGE**, trả lời được các câu sau:

- [ ] Consumer gọi **receive() đồng bộ**, **receiveBody()**, hay được JMS provider gọi **MessageListener.onMessage()**?
- [ ] Mốc ACK logic tương ứng đã được ghi trên sơ đồ và giải thích trong code review?
- [ ] Nếu **receive** đã trả về rồi database thất bại, ứng dụng có cơ chế recovery khác không?
- [ ] Nếu dùng listener, callback có **đợi** xử lý xong hay chỉ submit sang executor?
- [ ] Có đoạn **catch lỗi rồi return bình thường** có thể biến lỗi thành ACK không?
- [ ] Khi listener throw RuntimeException, hành vi provider đã được thử thực tế theo phiên bản/client/retry policy?
- [ ] Có kiểm tra **queue pending, delivering, ACK/dequeue**, và dùng **jobId** để phân biệt các message?
- [ ] Có kiểm tra lỗi khi connection mất **trước và sau** mốc ACK, tránh suy luận ACK chắc chắn đến broker?
- [ ] Nếu nghiệp vụ cần retry an toàn, đã xem xét **SESSION_TRANSACTED** hoặc ack chủ động và idempotency?
- [ ] Khi ứng dụng dùng **framework listener container**, đã xác định container nhận message qua cơ chế nào và tự ACK lúc nào?
- [ ] Các phép thử chạy trên broker lab, không dùng hàng đợi thanh toán hay dữ liệu production?

### Bài tập tự trả lời

1. Consumer gọi **receive(5000)** rồi nhận **null**. Có message nào được ACK không? **Không.**
2. Consumer gọi **receive(5000)**, nhận một message, rồi ném exception ở bước ghi database. Exception có rollback AUTO_ACK không? **Không.**
3. **onMessage** gọi xử lý đồng bộ thành công rồi return. Mốc ACK logic ở đâu? **Sau khi callback hoàn tất bình thường.**
4. **onMessage** bắt exception rồi không ném lại. Provider nhìn thấy gì? **Callback kết thúc bình thường**, nên AUTO_ACK có thể hoàn tất.
5. **onMessage** chỉ gọi **executor.submit** rồi return. Nếu task thất bại sau đó, broker tự biết không? **Không.**
6. Consumer dùng AUTO_ACK nhưng message vẫn redeliver sau broker crash. Có mâu thuẫn tuyệt đối với bảng thời điểm ACK không? **Không**, còn các cửa sổ lỗi truyền thông và trạng thái ACK chưa được broker ghi nhận chắc chắn.
7. Đổi session sang **SESSION_TRANSACTED** có làm database commit và JMS commit nguyên tử không? **Không**, cần thiết kế giao dịch/idempotency bên ngoài.

**Kết luận:** Với **AUTO_ACKNOWLEDGE**, sự khác nhau quan trọng nhất là **receive đồng bộ được xác nhận tại lần nhận thành công**, còn **MessageListener bất đồng bộ được xác nhận sau khi callback trở về thành công**. Chỉ cần xử lý lỗi sai vị trí, nuốt exception hoặc trả về trước khi task hoàn tất là có thể đánh dấu message đã xử lý dù nghiệp vụ chưa xong. Hãy chọn chế độ xác nhận theo đúng mức độ tin cậy của từng tác vụ, và kiểm chứng bằng log lẫn trạng thái broker trong các tình huống lỗi có chủ đích.
