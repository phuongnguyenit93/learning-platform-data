# MessageProducer, MessageConsumer và Destination trong JMS

> **Chương:** Lập trình JMS  
> **Phạm vi:** Cách ứng dụng Java sử dụng ba đối tượng JMS cốt lõi để gửi và nhận thông điệp với Apache ActiveMQ Classic hoặc Artemis. Trọng tâm là API, thời điểm tạo và đóng tài nguyên, ý nghĩa của queue/topic, các tùy chọn gửi/nhận và cách kiểm chứng. Ví dụ chính dùng ActiveMQ Classic 5.x với `javax.jms`; phần đối chiếu sử dụng Artemis và `jakarta.jms`.

## 1. Bức tranh tổng thể: ba vai trò, một đường giao tiếp

Giả sử dịch vụ đặt hàng muốn gửi yêu cầu xử lý hóa đơn bất đồng bộ, thay vì gọi trực tiếp dịch vụ hóa đơn qua HTTP. Nó gửi một thông điệp đến queue `orders.invoice.work`, còn các worker lấy công việc từ queue đó.

Trong JMS, ba đối tượng có vai trò khác nhau:

| Đối tượng | Vai trò | Ví dụ |
|---|---|---|
| `Destination` | Đại diện cho **đích logic** mà message được gửi tới hoặc consumer đăng ký đọc | `Queue orders.invoice.work`, `Topic orders.events` |
| `MessageProducer` | Được tạo từ `Session` để **gửi** message đến destination | Gửi `TextMessage` chứa `orderId=O-1001` |
| `MessageConsumer` | Được tạo từ `Session` để **nhận** message từ destination | Worker nhận, xử lý và xác nhận message |

Producer và consumer **không gọi trực tiếp lẫn nhau**. Broker nhận và định tuyến message dựa trên destination; khi consumer tắt hoặc có nhiều consumer, chính broker và cấu hình subscription/queue quyết định việc giữ và phân phối message.

~~~mermaid
flowchart LR
    S["Order Service"] --> P["MessageProducer"]
    P --> D["Destination: queue orders.invoice.work"]
    D --> B["ActiveMQ broker"]
    B --> C1["MessageConsumer A"]
    B --> C2["MessageConsumer B"]
    C1 --> I["Invoice Service"]
    C2 --> I
~~~

Với **queue**, A và B cạnh tranh nhận công việc: một lần delivery thành công thuộc về một consumer, thay vì tự động phát bản sao cho cả hai. Với **topic**, mỗi subscription thích hợp có thể nhận một bản của cùng thông điệp.

**Kết quả học tập:** bạn cần biết tạo đúng ba đối tượng, viết producer/consumer có đóng tài nguyên an toàn, và lý giải được các tình huống “gửi thành công nhưng không ai nhận”, “consumer nhận lại message”, “topic mất sự kiện khi offline” và “selector không khớp”.

## 2. Ba đối tượng nằm ở đâu trong vòng đời JMS?

Các đối tượng không được tạo trực tiếp bằng `new MessageProducer(...)` hay `new MessageConsumer(...)`. Ở API JMS truyền thống, quan hệ sở hữu thường là:

~~~mermaid
flowchart TD
    CF["ConnectionFactory"] --> CO["Connection"]
    CO --> SE["Session"]
    SE --> DE["Destination: Queue / Topic / Temporary..."]
    SE --> PR["MessageProducer"]
    SE --> CU["MessageConsumer"]
    PR -->|send| DE
    DE -->|receive| CU
~~~

Một trình tự phổ biến:

1. Tạo `ConnectionFactory` phù hợp broker và giao thức.
2. Từ factory tạo `Connection` tới broker.
3. Từ connection tạo `Session` với chế độ transaction/acknowledgment phù hợp.
4. Từ session lấy đối tượng `Destination` có tên định trước.
5. Tạo `MessageProducer` hoặc `MessageConsumer` gắn với destination đó.
6. Producer gửi; consumer bắt đầu nhận sau `connection.start()`.
7. Xác nhận/commit theo hợp đồng JMS rồi đóng consumer, producer, session và connection.

Ví dụ tạo các đối tượng trong ActiveMQ Classic:

~~~java
ActiveMQConnectionFactory factory =
        new ActiveMQConnectionFactory("tcp://localhost:61616");

Connection connection = factory.createConnection("app", "lab-secret");
Session session = connection.createSession(
        false, Session.CLIENT_ACKNOWLEDGE);

Queue orders = session.createQueue("orders.invoice.work");
MessageProducer producer = session.createProducer(orders);
MessageConsumer consumer = session.createConsumer(orders);
~~~

Đây là đoạn minh họa, chưa bao gồm `try/finally` và `connection.start()`. Các ví dụ đầy đủ ở phần sau sẽ làm rõ cách dọn tài nguyên.

**Phân biệt tạo đối tượng phía client với tạo tài nguyên broker:** gọi `session.createQueue("orders.invoice.work")` tạo ra **đối tượng JMS Queue để tham chiếu tên**. Broker có tự tạo physical queue hay từ chối destination chưa tồn tại hay không phụ thuộc provider và cấu hình. Không mặc định lời gọi `createQueue()` đã cấp phát một queue bền trên server.

### 2.1. `Session` có tác dụng gì?

`Session` là ngữ cảnh gửi/nhận message, quy định cách acknowledgment và transaction hoạt động, đồng thời tạo producer, consumer và message. Trong JMS 1.1, **một session là ngữ cảnh tuần tự, không được sử dụng đồng thời tùy tiện từ nhiều thread**. Ứng dụng nhiều worker thường cấp session riêng cho mỗi worker, hoặc giao quản lý concurrency cho listener container/framework.

Các chế độ thường thấy:

| Tạo session | Ý nghĩa |
|---|---|
| `createSession(false, Session.AUTO_ACKNOWLEDGE)` | Session không transacted; provider xử lý ACK theo quy tắc AUTO |
| `createSession(false, Session.CLIENT_ACKNOWLEDGE)` | Ứng dụng chủ động gọi `Message.acknowledge()` |
| `createSession(true, Session.SESSION_TRANSACTED)` | Send/receive thuộc local JMS transaction; dùng `commit()` hoặc `rollback()` |

Trong session transacted, đối số ACK mode không quyết định ACK thực tế; transaction mới là ranh giới hoàn tất. `SESSION_TRANSACTED` **không tự gom SQL transaction** của database vào cùng transaction với JMS.

## 3. `Destination`: tên đích, loại đích và phạm vi

### 3.1. `Queue` và `Topic`

`Destination` là interface nền; hai interface con thường dùng là `Queue` và `Topic`:

~~~java
Queue workQueue = session.createQueue("orders.invoice.work");
Topic orderEvents = session.createTopic("orders.events");
~~~

Tên `orders.invoice.work` hay `orders.events` là **tên logic** của destination theo provider. Khi hai chương trình muốn liên lạc, chúng phải thống nhất **loại** và **tên** đích.

| Tiêu chí | JMS Queue | JMS Topic |
|---|---|---|
| Mô hình nhận | Các consumer cùng queue cạnh tranh xử lý | Nhiều subscription có thể nhận bản sao riêng |
| Hai worker cùng đọc | Một message được hoàn tất bởi một consumer của queue | Nếu mỗi worker có subscription riêng, mỗi subscription nhận message phù hợp |
| Consumer chưa hoạt động | Message hợp lệ có thể chờ trên queue | Non-durable subscriber vắng mặt thường không có backlog |
| Muốn nhận sau khi offline | Dùng queue với persistence/TTL phù hợp | Đăng ký durable subscription trước khi publish, hoặc cấu trúc queue subscription đã khai báo |
| Tình huống | Job, tác vụ cần một nhóm xử lý | Event phát tới Billing, Email, Analytics |

Hai destination cùng chuỗi tên nhưng khác loại **không thể thay thế cho nhau**. `Queue orders.events` và `Topic orders.events` có semantics khác nhau. Trong Artemis, cách queue/topic được ánh xạ vào mô hình address/queue/routing type cũng cần được cấu hình đúng.

### 3.2. Destination không phải nội dung message

Destination trả lời **“gửi/đọc ở đâu?”**; message trả lời **“mang dữ liệu gì?”**. Với JMS, producer có thể tạo:

~~~java
TextMessage message = session.createTextMessage("orderId=O-1001");
message.setStringProperty("eventType", "InvoiceRequested");
message.setStringProperty("eventId", "E-1001");
~~~

Destination có thể là `orders.invoice.work` còn `eventType` là **property của message**. Đừng dùng `setStringProperty` để thay thế việc chọn queue/topic, và đừng nghĩ tên queue tự quyết định body phải ở định dạng gì. Việc dùng JSON, Avro, Protobuf hoặc text thuần là một hợp đồng payload riêng giữa hai dịch vụ.

### 3.3. `TemporaryQueue`, `TemporaryTopic` và `JMSReplyTo`

JMS còn cung cấp temporary destinations, thường dùng cho mô hình request/reply:

~~~java
TemporaryQueue replyQueue = session.createTemporaryQueue();
Queue requestQueue = session.createQueue("pricing.requests");

TextMessage request = session.createTextMessage("sku=BK-01");
request.setJMSReplyTo(replyQueue);
request.setJMSCorrelationID("req-1001");
~~~

Producer gửi request đến `pricing.requests`, còn worker xử lý lấy `request.getJMSReplyTo()` làm nơi gửi phản hồi. Client tạo temporary queue thường là client có quyền tiêu thụ từ queue đó; client khác có thể gửi reply nếu broker/protocol/ACL cho phép. Temporary destination có vòng đời gắn với connection tạo ra nó, nên không dùng làm kho backlog dài hạn. Trong request/reply, cần có timeout và correlation ID để ghép phản hồi đúng yêu cầu.

### 3.4. Client object và provisioning

Hai mô hình vận hành thường gặp:

- **Provision trước:** admin hoặc deployment tạo queue/topic/address với routing, quyền và policy; ứng dụng chỉ tham chiếu bằng tên.
- **Auto-create:** provider/broker được phép tự tạo tài nguyên khi client gửi/nhận; tiện cho lab nhưng dễ sinh queue do gõ nhầm.

Ví dụ consumer dùng `session.createQueue("orders.invoice.wrok")` (sai `work` thành `wrok`). Nếu broker tự tạo queue, ứng dụng có thể chờ mãi trên queue sai. Trong Artemis, cần xét `auto-create-queues`, `auto-create-addresses` và mapping JMS; trong Classic cần xét hành vi tạo destination/authorization của phiên bản triển khai.

## 4. `MessageProducer`: gửi message có hợp đồng rõ ràng

### 4.1. Producer gắn đích và producer không gắn đích

Có hai kiểu sử dụng JMS 1.1:

~~~java
// Producer gắn với một destination; thích hợp cho một luồng cố định.
Queue work = session.createQueue("orders.invoice.work");
MessageProducer bound = session.createProducer(work);
bound.send(session.createTextMessage("orderId=O-1001"));

// Producer không gắn đích; mỗi lần send phải cung cấp Destination.
MessageProducer unbound = session.createProducer(null);
unbound.send(
        session.createQueue("orders.audit"),
        session.createTextMessage("orderId=O-1001; state=CREATED"));
~~~

Dùng `createProducer(destination)` giúp mã đơn giản, giảm nguy cơ gửi nhầm luồng khi producer chỉ phục vụ một destination. Dùng `createProducer(null)` khi cần gửi đến nhiều destination qua cùng producer và provider/API hỗ trợ.

Ở ví dụ này phải **đóng cả hai producer** sau khi dùng. Việc tạo producer không tạo ra một thread riêng để tự gửi message; hành vi gửi diễn ra khi gọi `send(...)`.

### 4.2. Message được tạo trong cùng session

Các kiểu message có sẵn gồm `TextMessage`, `BytesMessage`, `MapMessage`, `ObjectMessage` và `StreamMessage`. Trong tích hợp liên ngôn ngữ, text/bytes với schema rõ ràng thường dễ liên thông hơn một `ObjectMessage` chứa Java serialization.

~~~java
TextMessage order = session.createTextMessage(
        "{\"eventId\":\"E-1001\",\"orderId\":\"O-1001\"}");
order.setStringProperty("eventType", "InvoiceRequested");
order.setStringProperty("schemaVersion", "1");
order.setJMSCorrelationID("trace-2026-1001");

producer.send(order);
~~~

Producer có thể gán property/header ứng dụng trước khi gửi. Provider thường gán các header như `JMSMessageID`, `JMSTimestamp`, `JMSExpiration` và `JMSDestination` theo semantics của send. Đừng dùng chuỗi body làm căn cứ duy nhất để xác định loại sự kiện nếu hệ thống đã có property/schema rõ ràng.

### 4.3. Delivery mode, priority và TTL

JMS cung cấp các tùy chọn gửi thường dùng:

~~~java
producer.setDeliveryMode(DeliveryMode.PERSISTENT);
producer.setPriority(4);
producer.setTimeToLive(5 * 60_000L); // 5 phút, đơn vị milliseconds
producer.send(order);
~~~

| Tùy chọn | Ý nghĩa | Điều không được suy ra |
|---|---|---|
| `PERSISTENT` | Yêu cầu broker dùng semantics lưu bền phù hợp | Không có nghĩa consumer đã ghi database |
| `NON_PERSISTENT` | Chấp nhận bảo đảm lưu bền thấp hơn khi broker gặp sự cố | Không bảo đảm mất message trong mọi lần restart sạch |
| Priority `0..9` | Mức ưu tiên JMS; `4` là giá trị mặc định phổ biến | Không cam kết thứ tự toàn cục nếu có nhiều consumer và retry |
| TTL > 0 | Message có expiration sau khoảng thời gian cấu hình | Không phải khoảng đợi trước khi message được giao |
| TTL = 0 | Producer không áp đặt expiration | Không đồng nghĩa broker phải giữ message vô hạn bất chấp policy/admin |

Cú pháp gửi với option cho từng message cũng có sẵn ở producer gắn đích:

~~~java
producer.send(order, DeliveryMode.PERSISTENT, 7, 30_000L);
~~~

Nên chọn giá trị theo nhu cầu nghiệp vụ. Ví dụ `InvoiceRequested` cần bền và có TTL đủ dài để khắc phục gián đoạn; sự kiện hiển thị dashboard thời gian thực có thể có TTL ngắn hơn.

**Producer send thành công không có nghĩa consumer đã xử lý thành công.** Nó chỉ cho thấy thao tác gửi đã hoàn tất theo hợp đồng producer/provider và trạng thái transaction đang sử dụng. Với transacted session, cần `session.commit()` trước khi coi giao dịch gửi đã hoàn thành.

### 4.4. Sự cố giữa send và commit

Nếu ứng dụng không nhận được phản hồi do mất kết nối đúng lúc gửi, có thể xảy ra tình huống producer **không biết chắc** broker đã nhận message hay chưa. Retry gửi lại có thể tạo duplicate. Vì vậy message nghiệp vụ nên có `eventId` ổn định để consumer áp dụng idempotency, không dựa duy nhất vào `JMSMessageID` được provider tạo cho từng lần gửi.

## 5. `MessageConsumer`: nhận message, lọc message và xác nhận

### 5.1. Nhận đồng bộ

Tạo consumer từ destination:

~~~java
Queue work = session.createQueue("orders.invoice.work");
MessageConsumer consumer = session.createConsumer(work);

connection.start();              // Bắt đầu delivery cho consumer.
Message message = consumer.receive(10_000L); // Chờ tối đa 10 giây.
if (message == null) {
    System.out.println("Chưa có message phù hợp trong 10 giây");
}
~~~

Ba cách nhận trong API JMS truyền thống:

| Lời gọi | Cách hoạt động | Dùng khi |
|---|---|---|
| `receive()` | Chờ đến khi có message, bị đóng/ngắt hoặc gặp lỗi | Consumer chuyên dụng được quản lý vòng đời rõ |
| `receive(timeout)` | Chờ tối đa khoảng timeout; trả `null` nếu hết thời gian | Poll có giới hạn để test hoặc shutdown |
| `receiveNoWait()` | Kiểm tra không chặn | Cần thử đọc ngay một lần |

Với `receive(timeout)`, `null` **không chứng minh queue mãi mãi rỗng**. Có thể không có message phù hợp selector, consumer chưa được start, broker chưa gửi kịp, hoặc message đang thuộc trạng thái in-flight của consumer khác.

**Đối với JMS 1.1, gọi `connection.start()` để consumer bắt đầu nhận.** Producer chỉ gửi thường không cần `start()`, nhưng consumer cần. Đây là một lỗi cơ bản khi chạy hai chương trình Java riêng.

### 5.2. Message selector

Consumer có thể chọn message theo property/header, sử dụng cú pháp biểu thức selector của JMS (gần với SQL-92 subset):

~~~java
MessageConsumer invoiceConsumer = session.createConsumer(
        session.createQueue("orders.work"),
        "eventType = 'InvoiceRequested' AND region = 'VN'");
~~~

Producer phải gán đúng property:

~~~java
TextMessage message = session.createTextMessage("orderId=O-1001");
message.setStringProperty("eventType", "InvoiceRequested");
message.setStringProperty("region", "VN");
producer.send(message);
~~~

Lưu ý:

- Selector dùng **property/header**, không tự parse nội dung JSON body.
- Kiểu dữ liệu có ý nghĩa: property kiểu số và string không được so sánh tùy tiện như một chuỗi giống nhau.
- Hai nhánh xử lý trên **cùng queue** không giống hai subscription topic độc lập; một message chỉ thuộc queue đó, và việc dispatch phụ thuộc consumer nào có selector phù hợp.
- Selector không làm broker tự đổi tên destination hoặc chuyển message sang queue khác.
- Nếu selector không khớp thì `receive()` có thể tiếp tục chờ dù queue đang có message dành cho consumer khác.

### 5.3. Nhận bất đồng bộ qua `MessageListener`

Ngoài polling, JMS truyền thống có callback:

~~~java
MessageConsumer consumer = session.createConsumer(
        session.createQueue("orders.invoice.work"));

consumer.setMessageListener(message -> {
    try {
        if (!(message instanceof TextMessage)) {
            throw new IllegalArgumentException("Unexpected type");
        }
        String payload = ((TextMessage) message).getText();
        processInvoice(payload);
    } catch (JMSException e) {
        throw new RuntimeException(e);
    }
});

connection.start();
~~~

Ở đây `processInvoice` là hàm nghiệp vụ do ứng dụng tự định nghĩa; đoạn minh họa giả định đã có `Connection` và `Session`. Cần **giữ connection/session/consumer còn mở** trong thời gian nhận callback. Nếu method tạo listener xong lập tức đóng session, listener không còn hoạt động.

Đối với production, nên quản lý listener bằng cơ chế container hoặc framework có cấu hình concurrency, transaction, exception, redelivery và shutdown rõ ràng. **Đừng giả định ném RuntimeException từ `onMessage` bảo đảm mọi provider luôn retry y hệt nhau.** Muốn kiểm soát ranh giới ACK, chọn chế độ transaction thích hợp và thử nghiệm với broker/client thật.

### 5.4. ACK không đồng nghĩa xử lý đúng một lần

Ba lựa chọn thường thấy:

- `AUTO_ACKNOWLEDGE`: tự xác nhận theo quy tắc JMS. Dễ dùng cho ví dụ đơn giản.
- `CLIENT_ACKNOWLEDGE`: app gọi `message.acknowledge()` sau khi xử lý. Theo JMS, ACK **bao phủ các message đã được consume trong cùng session kể từ lần xác nhận trước**; không nên diễn giải như ACK độc lập từng message trong một session nhận song song.
- **Transacted session**: `session.commit()` xác nhận receive (và các send thuộc transaction), `rollback()` khiến message chưa hoàn tất có thể được giao lại.

Nếu consumer ghi hóa đơn vào database rồi crash trước ACK, message có thể được giao lại và tạo hóa đơn trùng nếu code không idempotent. Một ràng buộc unique theo `eventId` hoặc `orderId` ở database thường thiết thực hơn kỳ vọng “message chỉ đến đúng một lần”.

## 6. Ví dụ hoàn chỉnh với ActiveMQ Classic 5.x và JMS 1.1

Để thống nhất API, hai chương trình dưới đây sử dụng:

- ActiveMQ Classic 5.x và Maven artifact `org.apache.activemq:activemq-client` có API `javax.jms` tương thích.
- Một broker lab chạy tại `tcp://localhost:61616` và cho phép tài khoản `app` gửi/nhận. Mật khẩu ví dụ `lab-secret` không dùng trong source production.
- Java 8+ để dùng code đơn giản.
- Hai file class riêng `ClassicOrderProducer.java` và `ClassicOrderConsumer.java`.

Đừng trộn `javax.jms` của ví dụ Classic 5.x với `jakarta.jms` của Artemis ở phần sau trong cùng source file. Phiên bản Classic/client khác có thể sử dụng dependency hoặc namespace khác; cần kiểm tra đúng cặp broker/client.

### 6.1. Producer gửi message vào Queue hoặc Topic

~~~java
import javax.jms.Connection;
import javax.jms.DeliveryMode;
import javax.jms.Destination;
import javax.jms.JMSException;
import javax.jms.MessageProducer;
import javax.jms.Session;
import javax.jms.TextMessage;
import org.apache.activemq.ActiveMQConnectionFactory;

public final class ClassicOrderProducer {
    public static void main(String[] args) throws JMSException {
        boolean topicMode = args.length > 0 && "topic".equals(args[0]);
        String destinationName = topicMode
                ? "orders.events"
                : "orders.invoice.work";

        ActiveMQConnectionFactory factory =
                new ActiveMQConnectionFactory("tcp://localhost:61616");

        Connection connection =
                factory.createConnection("app", "lab-secret");
        try {
            Session session = connection.createSession(
                    false, Session.AUTO_ACKNOWLEDGE);
            try {
                Destination destination = topicMode
                        ? session.createTopic(destinationName)
                        : session.createQueue(destinationName);

                MessageProducer producer = session.createProducer(destination);
                try {
                    producer.setDeliveryMode(DeliveryMode.PERSISTENT);
                    producer.setPriority(4);
                    producer.setTimeToLive(5 * 60_000L);

                    TextMessage message = session.createTextMessage(
                            "{\"eventId\":\"E-1001\",\"orderId\":\"O-1001\"}");
                    message.setStringProperty("eventType", "InvoiceRequested");
                    message.setStringProperty("eventId", "E-1001");

                    producer.send(message);
                    System.out.println("Sent to "
                            + (topicMode ? "Topic " : "Queue ")
                            + destinationName);
                    System.out.println("JMSMessageID="
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
~~~

**Điểm cần kiểm chứng:** producer tạo destination đúng loại; `TextMessage` được tạo từ session; thuộc tính gửi được đặt trước `send`; chương trình không gọi `connection.start()` vì không nhận message. Cú pháp `try/finally` được dùng vì các interface `javax.jms.Connection`/`Session` trong JMS 1.1 không mở rộng `AutoCloseable`.

Chạy chương trình ở chế độ mặc định để gửi **Queue**; truyền đối số `topic` để gửi **Topic**. Mỗi lần chạy gửi một message có cùng `eventId=E-1001` để dễ quan sát, nhưng trong ứng dụng thật mỗi sự kiện mới cần một event ID mới; khi retry một sự kiện cũ phải giữ cùng ID.

### 6.2. Consumer đồng bộ, có selector và ACK sau xử lý

~~~java
import javax.jms.Connection;
import javax.jms.Destination;
import javax.jms.JMSException;
import javax.jms.Message;
import javax.jms.MessageConsumer;
import javax.jms.Session;
import javax.jms.TextMessage;
import org.apache.activemq.ActiveMQConnectionFactory;

public final class ClassicOrderConsumer {

    public static void main(String[] args) throws Exception {
        boolean topicMode = args.length > 0 && "topic".equals(args[0]);
        String destinationName = topicMode
                ? "orders.events"
                : "orders.invoice.work";

        ActiveMQConnectionFactory factory =
                new ActiveMQConnectionFactory("tcp://localhost:61616");

        Connection connection =
                factory.createConnection("app", "lab-secret");
        try {
            Session session = connection.createSession(
                    false, Session.CLIENT_ACKNOWLEDGE);
            try {
                Destination destination = topicMode
                        ? session.createTopic(destinationName)
                        : session.createQueue(destinationName);

                MessageConsumer consumer = session.createConsumer(
                        destination, "eventType = 'InvoiceRequested'");
                try {
                    connection.start(); // Consumer mới bắt đầu nhận delivery.
                    Message message = consumer.receive(10_000L);

                    if (message == null) {
                        System.out.println("No matching message in 10 seconds");
                        return;
                    }

                    if (!(message instanceof TextMessage)) {
                        session.recover();
                        throw new IllegalStateException(
                                "Expected TextMessage, got "
                                + message.getClass().getName());
                    }

                    try {
                        String payload = ((TextMessage) message).getText();
                        String eventId =
                                message.getStringProperty("eventId");

                        persistInvoiceOnce(eventId, payload);
                        message.acknowledge(); // Chỉ sau khi nghiệp vụ thành công
                        System.out.println("ACK " + eventId);
                    } catch (Exception error) {
                        // Chưa ACK, yêu cầu phục hồi delivery trong session.
                        session.recover();
                        throw error;
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

    private static void persistInvoiceOnce(
            String eventId, String payload) {
        // Minh họa: production ghi database với unique key eventId.
        System.out.println("Processing " + eventId + ": " + payload);
    }
}
~~~

Trong mã trên, `persistInvoiceOnce` mới chỉ in ra console; tên hàm biểu thị **hợp đồng cần triển khai**, chưa phải cơ chế deduplication thực sự. Production phải lưu trạng thái xử lý với unique constraint/transaction trong database hoặc tương đương.

Những điểm kỹ thuật:

1. `MessageConsumer` được tạo từ cùng `Session` với `Destination`.
2. `connection.start()` xảy ra **trước `receive()`**.
3. Selector chỉ nhận message có `eventType = 'InvoiceRequested'`.
4. Nếu xử lý thành công, consumer mới `acknowledge()`; nếu thất bại, `session.recover()` yêu cầu session không transacted phát lại các message chưa ACK theo quy tắc JMS.
5. Chương trình chỉ nhận **một message rồi thoát**, phù hợp cho demo; worker production cần vòng nhận liên tục/lifecycle do framework quản lý.
6. Khi nhận một message duy nhất trên session này, tác dụng ACK theo session dễ quan sát; với nhiều message hoặc nhiều consumer chung session, phạm vi ACK sẽ rộng hơn.

Đừng đặt retry vô hạn ngay trong hàm xử lý. Giới hạn redelivery, độ trễ, DLQ và cách replay cần được thiết kế ở broker/client tương ứng, có quan sát lỗi và khóa chống trùng.

### 6.3. Thứ tự chạy để tránh nhầm Queue và Topic

**Thử Queue:**

1. Chạy `ClassicOrderProducer` trước để gửi tới `orders.invoice.work`.
2. Chạy `ClassicOrderConsumer` sau.
3. Nếu broker cho phép queue tồn tại và message PERSISTENT còn hợp lệ, consumer nhận và ACK message.
4. Chạy thêm hai instance consumer đọc cùng queue, rồi gửi nhiều event với ID khác nhau để quan sát việc chia công việc.

**Thử Topic:**

1. Chạy `ClassicOrderConsumer topic` **trước**, khi nó đang chờ `receive(10_000)`.
2. Chạy `ClassicOrderProducer topic` trong khoảng thời gian đó.
3. Lặp lại với hai consumer topic đang cùng online để quan sát mỗi non-durable subscription phù hợp có thể nhận một bản.
4. Thử gửi **trước khi khởi động** consumer topic: consumer non-durable tạo sau lúc publish không tự nhận lịch sử đã qua.

Nếu muốn subscriber vẫn nhận topic event lúc offline, cần dùng **durable subscription**, có danh tính ổn định và được tạo **trước** khi producer phát message cần giữ. Điều đó khác với việc chỉ đặt `DeliveryMode.PERSISTENT` trên producer.

## 7. Consumer topic bền và sự khác biệt giữa consumer với subscription

Một `MessageConsumer` trên topic thường đại diện một non-durable subscription đang hoạt động. Với JMS 1.1, durable subscription được tạo qua API riêng:

~~~java
Connection connection = factory.createConnection("app", "lab-secret");
try {
    connection.setClientID("billing-service");

    Session session = connection.createSession(
            false, Session.CLIENT_ACKNOWLEDGE);
    try {
        Topic topic = session.createTopic("orders.events");
        MessageConsumer consumer =
                session.createDurableSubscriber(topic, "billing-events");
        try {
            connection.start();
            Message message = consumer.receive(10_000L);
            if (message != null) {
                process(message);
                message.acknowledge();
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
~~~

Đây là đoạn code minh họa bên trong môi trường có `factory` và hàm `process(Message)`; hai biểu tượng đó cần được định nghĩa khi đưa vào chương trình thực. Các điều kiện cần nhớ:

- `clientID` và subscription name xác định danh tính durable subscription trong mô hình JMS truyền thống. **Chúng phải ổn định** giữa các lần kết nối.
- Đóng `consumer` và `connection` **không tự hủy** durable subscription. Broker có thể tiếp tục lưu message phù hợp trong lúc offline.
- `session.unsubscribe("billing-events")` là hành động hủy subscription có chủ ý, phải thực hiện khi subscription không còn active và theo điều kiện JMS/provider. Nó có thể loại bỏ backlog chưa nhận.
- Cùng một durable subscription truyền thống **không phải** phương án tùy ý cho nhiều connection đồng thời với cùng `clientID`. Nếu muốn chia tải trong cùng nhóm subscriber, cần chọn cơ chế shared subscription (ở phiên bản API/provider hỗ trợ) hoặc queue group riêng.
- TTL, selector, message persistence và chính sách tài nguyên vẫn ảnh hưởng backlog của durable subscription.

Phần code chính trước đó dùng queue để tránh phải quản lý danh tính subscription. Còn ví dụ này chỉ làm rõ rằng **MessageConsumer là phiên đọc đang hoạt động; durable subscription là quyền nhận còn tồn tại qua những lần phiên đọc đó đóng**.

## 8. Đối chiếu JMS 1.1 và API hiện đại khi dùng Artemis

Trong code Classic 5.x ở trên, các interface nằm trong `javax.jms`:

~~~text
ConnectionFactory -> Connection -> Session
Session.createProducer(...) -> MessageProducer
Session.createConsumer(...) -> MessageConsumer
~~~

Ở những ứng dụng dùng Jakarta Messaging (ví dụ Jakarta JMS trên Artemis), có thêm API rút gọn `JMSContext`:

~~~text
ConnectionFactory.createContext(...) -> JMSContext
JMSContext.createProducer()         -> JMSProducer
JMSContext.createConsumer(...)      -> JMSConsumer
~~~

**`JMSProducer` và `JMSConsumer` không phải hai interface trùng tên với `MessageProducer` và `MessageConsumer`.** Đây là lớp API tiện dụng của JMS 2.0/Jakarta Messaging; không lấy nguyên các lời gọi `MessageProducer.send(Message)` để thay bằng kiểu mới mà không kiểm tra overload.

Ví dụ Artemis với `org.apache.activemq:artemis-jakarta-client` và `jakarta.jms`, dùng queue `orders.invoice.work` đã được khai báo hoặc được broker cho phép tạo:

~~~java
import jakarta.jms.DeliveryMode;
import jakarta.jms.JMSConsumer;
import jakarta.jms.JMSContext;
import jakarta.jms.JMSProducer;
import jakarta.jms.Message;
import jakarta.jms.Queue;
import jakarta.jms.TextMessage;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

public final class ArtemisJmsContextExample {
    public static void main(String[] args) throws Exception {
        ActiveMQConnectionFactory factory =
                new ActiveMQConnectionFactory(
                        "tcp://localhost:61616", "app", "lab-secret");

        try (JMSContext sender =
                     factory.createContext(JMSContext.AUTO_ACKNOWLEDGE)) {
            Queue queue = sender.createQueue("orders.invoice.work");

            JMSProducer producer = sender.createProducer()
                    .setDeliveryMode(DeliveryMode.PERSISTENT)
                    .setTimeToLive(5 * 60_000L)
                    .setProperty("eventType", "InvoiceRequested")
                    .setProperty("eventId", "E-2001");

            producer.send(queue, "orderId=O-2001");
        }

        try (JMSContext receiver =
                     factory.createContext(JMSContext.CLIENT_ACKNOWLEDGE)) {
            Queue queue = receiver.createQueue("orders.invoice.work");
            JMSConsumer consumer = receiver.createConsumer(
                    queue, "eventType = 'InvoiceRequested'");

            Message message = consumer.receive(10_000L);
            if (message instanceof TextMessage) {
                String payload = ((TextMessage) message).getText();
                System.out.println("Received " + payload);
                message.acknowledge();
            }
        }
    }
}
~~~

`JMSContext` hỗ trợ `AutoCloseable` nên có thể dùng `try-with-resources`. Lưu ý:

- `JMSContext` mặc định hỗ trợ tự start khi tạo consumer theo API; ví dụ dùng hành vi chuẩn đó, khác với việc gọi `Connection.start()` rõ ràng trong JMS 1.1.
- Trong ví dụ cùng chương trình, sender và receiver là hai context riêng để thấy rõ pha gửi/nhận; hệ thống thật có hai service/process độc lập.
- Chọn namespace và artifact khớp broker/framework: `javax.jms.*` và `jakarta.jms.*` là hai kiểu API khác nhau.
- Artemis dùng **address/routing type/queue** ở lõi; JMS queue thường được ánh xạ qua queue anycast phù hợp, JMS topic qua multicast/subscription. Không giả định một tên client tự định nghĩa đã tạo đúng routing nếu broker không cấu hình.
- Không hard-code credential trong production. Lấy secret qua cơ chế an toàn của môi trường.

## 9. Các lỗi thường gặp khi ghép Producer, Consumer và Destination

| Triệu chứng | Nguyên nhân thường gặp | Cách xác minh hoặc sửa |
|---|---|---|
| Producer gửi xong nhưng consumer không nhận | Sai tên queue/topic, consumer đọc nhầm broker/port | Log đầy đủ loại và tên `Destination`, kiểm tra console/management |
| Queue có message nhưng `receive()` luôn chờ | Chưa `connection.start()`, selector không khớp hoặc message đang in-flight | Start connection, bỏ selector tạm trong lab, kiểm tra consumer/in-flight |
| Topic consumer tạo sau khi publish không nhận message cũ | Non-durable subscription chưa tồn tại lúc publish | Khởi động subscriber trước, hoặc dùng durable subscription đúng mục đích |
| Hai instance cùng nhận mỗi message | Mỗi instance mở topic subscription riêng thay vì cùng queue | Dùng queue để competing consumers, hoặc shared subscription phù hợp |
| Worker xử lý một đơn hai lần | Crash sau DB commit nhưng trước ACK; rollback/reconnect | Dùng eventId idempotency và kiểm tra delivery count |
| ACK có hiệu lực ngoài message dự kiến | Nhiều receive trên một session `CLIENT_ACKNOWLEDGE` | Một session cho mỗi worker/nhóm xử lý phù hợp, hiểu phạm vi ACK |
| Lỗi khi chạy ví dụ Classic trên client Artemis | Trộn `javax.jms` và `jakarta.jms` hoặc sai provider | Chọn API/dependency theo broker và phiên bản |
| Ứng dụng gửi được nhưng broker không tồn tại queue như dự kiến | Đối tượng `Queue` phía client không đồng nghĩa provisioning | Kiểm tra auto-create, ACL và physical address/queue |
| Consumer bất đồng bộ dừng ngay sau startup | Connection/session/consumer bị đóng khi method kết thúc | Giữ lifecycle do service/container quản lý |
| Message biến mất khỏi backlog | Đã ACK, TTL hết hạn, policy xóa/expiry/DLQ hoặc nhầm subscription | Đọc metric và thông tin message theo đúng queue/subscription |
| Producer gặp timeout khi backlog lớn | Flow control, tài nguyên broker đầy hoặc mất kết nối | Đo producer latency, queue lag, disk/memory và policy liên quan |

Không nên “chữa” mọi trường hợp bằng cách tăng timeout của `receive()`. Hãy xác định trước client đang đọc **đúng destination** hay chưa, có **subscription phù hợp** hay không, rồi mới điều tra transport, acknowledgment và sức khỏe broker.

## 10. Bài thực hành có đáp án

### Bài A — Queue và Topic dùng cùng tên

Một chương trình producer gọi:

~~~java
Destination d = session.createTopic("orders.events");
MessageProducer producer = session.createProducer(d);
producer.send(session.createTextMessage("O-1001"));
~~~

Consumer khác lại dùng:

~~~java
Destination d = session.createQueue("orders.events");
MessageConsumer consumer = session.createConsumer(d);
~~~

**Câu hỏi:** Vì hai chương trình dùng cùng chuỗi `orders.events`, consumer có chắc nhận message không?

**Đáp án:** **Không.** Producer gửi tới JMS **Topic**, còn consumer đọc JMS **Queue**. Broker và provider có thể tạo/mapping hai loại tài nguyên khác nhau. Sửa bằng cách thống nhất loại và tên destination, sau đó kiểm chứng routing của broker.

### Bài B — Chọn đúng cách tạo producer

Một ứng dụng gửi cùng `TextMessage` theo hai loại thông báo:

~~~text
orders.invoice.work
orders.audit
~~~

Có hai phương án:

~~~java
MessageProducer p1 =
        session.createProducer(session.createQueue("orders.invoice.work"));

MessageProducer p2 = session.createProducer(null);
~~~

**Câu hỏi:** Phương án nào cần cung cấp destination ở mỗi lần gửi?

**Đáp án:** `p2`. Nó là producer không gắn sẵn destination nên dùng `p2.send(destination, message)`. `p1` gắn với queue `orders.invoice.work`, thường dùng `p1.send(message)`. Cả hai phải được đóng sau khi dùng.

### Bài C — Vì sao `receive(3000)` trả `null`?

Consumer tạo trên `orders.invoice.work` có selector:

~~~java
"eventType = 'InvoiceRequested'"
~~~

Producer gửi message có:

~~~java
message.setStringProperty("eventType", "InvoiceCompleted");
~~~

**Đáp án:** Message không khớp selector, nên consumer có thể chờ đến timeout và nhận `null`. Kiểm tra property trên message và biểu thức selector. Timeout không chứng minh queue trống; có thể có message khác chỉ phù hợp với consumer khác.

### Bài D — Thứ tự start của Topic

Một non-durable topic consumer được khởi tạo lúc 10:05, trong khi producer đã publish sự kiện lúc 10:00. Message được gửi với `PERSISTENT` và TTL một giờ.

**Câu hỏi:** Consumer mới có tự nhận sự kiện 10:00 không?

**Đáp án:** **Không.** Non-durable subscription chưa tồn tại lúc publish; `PERSISTENT` không biến một subscriber tạo sau thành kho lưu lịch sử. Cần tạo durable subscription trước thời điểm publish nếu muốn nhận khi subscriber offline (và vẫn chịu TTL/policy).

### Bài E — ACK sau khi ghi database

Consumer đọc `InvoiceRequested(E-1001)`:

~~~text
Receive E-1001
-> INSERT invoice vào database (COMMIT thành công)
-> ứng dụng crash trước message.acknowledge()
~~~

**Câu hỏi:** Khi chạy lại, broker có thể giao lại E-1001 không? Làm sao tránh tạo hai hóa đơn?

**Đáp án:** **Có thể giao lại** do message chưa được xác nhận. Dùng `eventId=E-1001` làm khóa duy nhất trong database hoặc bảng inbox trạng thái xử lý; consumer nhận lại phải phát hiện đã xử lý và ACK an toàn. Không đặt kỳ vọng idempotency lên riêng `MessageConsumer`.

### Bài F — Sửa chương trình consumer không bao giờ nhận

Có:

~~~java
Connection c = factory.createConnection();
Session s = c.createSession(false, Session.AUTO_ACKNOWLEDGE);
MessageConsumer mc =
        s.createConsumer(s.createQueue("orders.invoice.work"));
Message m = mc.receive();
~~~

**Lỗi nổi bật:** chưa gọi `c.start()` trước `receive()`. Cần thêm `c.start()`, quản lý timeout/shutdown và đóng tài nguyên trong `finally`. Ngoài ra kiểm tra credentials, quyền, broker address và sự tồn tại của message.

## 11. Checklist trước khi đưa JMS client vào ứng dụng

- **Destination:** Producer và consumer đã thống nhất `Queue` hay `Topic`, tên chính xác và broker endpoint?
- **Provisioning:** Tài nguyên broker có được tạo trước hoặc auto-create được kiểm soát?
- **Gửi:** Đã đặt delivery mode, TTL, priority theo yêu cầu và có event ID ổn định?
- **Nhận:** Đã start connection/thiết lập consumer, selector đúng property và message type?
- **Concurrency:** Có session/context riêng cho các worker chạy song song, tránh chia session bất hợp lệ?
- **ACK:** ACK/commit diễn ra sau xử lý business phù hợp; đã hiểu phạm vi session?
- **Retry:** Consumer có chiến lược rollback/recover, DLQ, delay và xử lý poison message?
- **Idempotency:** Có unique key/inbox để xử lý việc nhận trùng khi crash hoặc failover?
- **Lifecycle:** Producer, consumer, session và connection được đóng đúng lúc, callback không mất connection?
- **Observability:** Log message ID/event ID, tên destination, thời điểm gửi/nhận, selector và số lần redelivery?
- **Compatibility:** Đúng phiên bản client, broker, JMS namespace `javax`/`jakarta` và giao thức?
- **Security:** Kết nối được xác thực, quyền send/consume phù hợp và secret không lưu trong source?

## 12. Điều cần ghi nhớ

`Destination` chỉ rõ **tên và loại đích**; `MessageProducer` **tạo và gửi message** đến đích đó; `MessageConsumer` **đăng ký và nhận message** từ đích. Cả producer và consumer được tạo trong `Session`, chịu ảnh hưởng vòng đời connection, selector, acknowledgment và transaction.

Trong ActiveMQ Classic 5.x, bộ ba này thường được sử dụng qua `javax.jms` với `Connection → Session → MessageProducer/MessageConsumer`. Artemis hỗ trợ hợp đồng JMS tương ứng và có API `JMSContext/JMSProducer/JMSConsumer` hiện đại qua `jakarta.jms`, nhưng mapping vào address/queue và cách provisioning vẫn phải xác minh.

Một client JMS đúng cần đáp ứng ba câu hỏi thực tế: **gửi đến đúng destination nào, consumer nào được nhận, và lúc nào broker được coi là đã hoàn tất trách nhiệm giao message?** Câu trả lời rõ ràng cho ba câu hỏi đó là nền tảng của producer/consumer Java đáng tin cậy.
