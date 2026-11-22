# MessageProducer và thao tác gửi trong JMS

## 1. Vai trò của MessageProducer: “gửi” thực chất là làm gì?

Trong **Jakarta Messaging (JMS)**, `MessageProducer` là API phía **producer** dùng để gửi một đối tượng `Message` tới một `Destination` (queue hoặc topic). Ứng dụng tạo thông điệp bằng `Session`, cấu hình metadata và chính sách gửi, sau đó gọi `send(...)`. Provider/broker chịu trách nhiệm tiếp nhận, định tuyến và lưu giữ thông điệp theo hợp đồng JMS cùng cấu hình thực tế.

~~~text
Ứng dụng publisher
  ├─ ConnectionFactory → Connection → Session
  │                                     ├─ tạo Message (body + properties)
  │                                     └─ createProducer(destination)
  └─ MessageProducer.send(message) → JMS provider/broker → Queue/Topic
                                                            ↓
                                                        consumer
~~~

Cần phân biệt ba mốc:

1. **Chuẩn bị message:** ứng dụng đã có object `Message` trong bộ nhớ; chưa đồng nghĩa broker thấy message.
2. **Thao tác gửi hoàn tất:** phương thức gửi đồng bộ trả về thành công hoặc callback gửi bất đồng bộ báo hoàn tất. Mức bảo đảm cụ thể phụ thuộc delivery mode, transaction và provider.
3. **Nghiệp vụ được xử lý:** consumer nhận, xử lý, xác nhận/commit và ghi kết quả nghiệp vụ. **`send(...)` thành công không chứng minh consumer đã xử lý**.

Bài học tập trung vào **MessageProducer của classic JMS API** (`jakarta.jms.MessageProducer`), dùng với `Connection` và `Session`. **`JMSProducer`** là API đơn giản hóa khác dùng với `JMSContext`; **Spring `JmsTemplate`** là abstraction ở tầng framework. Hiểu MessageProducer giúp đọc chính xác cách các abstraction cao hơn thực hiện send.

> **Phiên bản:** Ví dụ dùng Java 17+, Spring Framework 6+/Spring Boot 3+ khi nhắc tới Spring, và Jakarta Messaging 3.1 (`jakarta.jms`). Với code Java EE/JMS cũ, package có thể là `javax.jms`; không trộn hai hệ package trong cùng dự án mà chưa kiểm tra compatibility của provider.

## 2. Tạo producer: cố định destination hoặc chọn destination khi gửi

### 2.1. Những đối tượng đứng trước MessageProducer

| Thành phần | Nhiệm vụ | Ai tạo |
| --- | --- | --- |
| `ConnectionFactory` | Factory để lấy kết nối tới JMS provider; địa chỉ, xác thực, TLS/pooling phụ thuộc cấu hình | Container, DI hoặc bootstrap ứng dụng |
| `Connection` | Đại diện kết nối JMS; có thể phục vụ nhiều session theo quy tắc provider | `connectionFactory.createConnection()` |
| `Session` | Ngữ cảnh **một luồng xử lý logic**; tạo message, producer và quản lý local JMS transaction | `connection.createSession(...)` |
| `Destination` (`Queue`, `Topic`) | Đích logic mà provider nhận message | Được lookup qua JNDI/DI hoặc tạo đối tượng destination bằng session |
| `MessageProducer` | Gửi message đến destination đã gắn, hoặc đến destination đưa vào mỗi lần gửi | `session.createProducer(...)` |

Chẳng hạn:

~~~java
// Các biến connection và session ở đây được tạo và quản lý
// bởi cùng một luồng trong đoạn mã bao ngoài.
Queue orders = session.createQueue("orders.events");
MessageProducer producer = session.createProducer(orders);
~~~

`session.createQueue("orders.events")` tạo **đối tượng đại diện queue**, không phải cam kết rằng broker đã provisioning queue đó theo chính sách mong muốn. Broker có thể cho phép auto-create hoặc yêu cầu người vận hành tạo trước. Với production, xác định queue/topic, quyền truy cập, durability, retention, DLQ và auto-create policy theo provider.

### 2.2. Producer gắn đích và producer không gắn đích

**Producer gắn đích** (identified producer):

~~~java
MessageProducer producer = session.createProducer(orders);
producer.send(session.createTextMessage("one"));
~~~

`send(Message)` dùng `orders` đã gắn lúc tạo producer. Gọi `send(destination, message)` trên producer gắn đích là sai API; thao tác dạng đó dành cho producer **không gắn đích**.

**Producer không gắn đích** (unidentified producer):

~~~java
Queue orders = session.createQueue("orders.events");
Queue audit = session.createQueue("orders.audit");

try (MessageProducer producer = session.createProducer(null)) {
    producer.send(orders, session.createTextMessage("created"));
    producer.send(audit, session.createTextMessage("audit-record"));
}
~~~

Trong trường hợp `createProducer(null)`, mỗi lần `send` phải truyền `Destination`. Không được gọi `send(message)` mà bỏ destination. Hai cách tạo phù hợp hai nhu cầu:

- Gửi nhiều message vào **một destination cố định**: producer gắn đích rõ ràng, giảm khả năng gửi nhầm đích.
- Gửi tới **nhiều destination** từ cùng session, chẳng hạn trả lời vào `JMSReplyTo`: producer không gắn đích có thể hữu ích.

Không vì một `MessageProducer` chọn được nhiều đích mà coi nó an toàn để chia sẻ tự do giữa các thread: `Session` của classic JMS là ngữ cảnh một luồng logic, cần tuân thủ threading restrictions.

## 3. Phương thức send: hiểu đúng chữ ký và thứ tự tham số

Các overload **đồng bộ** quan trọng nhất:

| API | Dùng khi nào |
| --- | --- |
| `send(Message message)` | Producer có destination cố định; dùng QoS mặc định của producer |
| `send(Message message, int deliveryMode, int priority, long timeToLive)` | Producer có destination cố định; ghi đè QoS cho **lần gửi này** |
| `send(Destination destination, Message message)` | Producer không gắn đích; truyền destination cho lần gửi |
| `send(Destination destination, Message message, int deliveryMode, int priority, long timeToLive)` | Producer không gắn đích và ghi đè QoS cho lần gửi |

Thứ tự của ba tham số QoS luôn là **delivery mode → priority → TTL**. Ví dụ:

~~~java
producer.send(
    message,
    DeliveryMode.PERSISTENT, // yêu cầu persistent delivery
    7,                       // priority từ 0 đến 9
    60_000L                  // TTL = 60 giây; đơn vị mili-giây
);
~~~

Đây là **classic MessageProducer API**. Các overload bất đồng bộ còn nhận thêm `CompletionListener` ở cuối; được giải thích sau. Không có tham số `deliveryDelay` trong overload `send(...)` classic: nếu cần delay, đặt qua `producer.setDeliveryDelay(milliseconds)`.

### 3.1. Giá trị mặc định và phạm vi cấu hình

~~~java
producer.setDeliveryMode(DeliveryMode.PERSISTENT);
producer.setPriority(4);
producer.setTimeToLive(300_000L);
producer.setDeliveryDelay(2_000L);
producer.send(message); // dùng mặc định vừa đặt
~~~

Các setter trên cấu hình mặc định **của producer**, không viết lại payload. `send(message, mode, priority, ttl)` chỉ ghi đè ba thuộc tính đó **cho lần gửi tương ứng**, không thay đổi các default của producer. Delay vẫn là thuộc tính producer.

- `DeliveryMode.PERSISTENT`: provider áp dụng cơ chế bền vững theo chuẩn và cấu hình. **Mặc định JMS là PERSISTENT**, song hiệu quả thực tế khi broker hỏng còn phụ thuộc chính sách broker, transaction, storage, cluster, TTL và tình trạng vận hành.
- `DeliveryMode.NON_PERSISTENT`: thường ít chi phí hơn nhưng có thể mất message khi provider gặp lỗi; chỉ dùng khi chấp nhận đánh đổi phù hợp yêu cầu nghiệp vụ.
- **Priority:** số nguyên **0–9**, mặc định **4**. Provider cố gắng ưu tiên mức cao hơn; đây không phải lịch trình thực thi chính xác hay SLA latency.
- **Time-to-live (TTL):** số mili-giây; **0** nghĩa là không đặt thời hạn hết hạn từ TTL. Với TTL dương, `JMSExpiration` được xác lập dựa trên **thời điểm gửi** cộng TTL, kể cả khi gửi trong transaction (không tính lại từ lúc commit).
- **Delivery delay:** số mili-giây không âm; mặc định **0**. Provider không được giao trước khoảng chờ tối thiểu tính từ **thời điểm gửi**, kể cả trong transaction. Đây **không phải** scheduler với thời điểm nhận chính xác.

**Quan hệ TTL và delay:** nếu delay = 10 giây nhưng TTL = 5 giây, message có thể hết hạn trước lúc đủ điều kiện được giao. Hãy thiết kế TTL lớn hơn delay cộng khoảng thời gian xử lý/đệm mong muốn, rồi xác minh trên broker thực tế.

Hai setter `setDisableMessageID(true)` và `setDisableMessageTimestamp(true)` chỉ là **yêu cầu cho phép provider bỏ qua tạo ID/timestamp để tối ưu**; provider có thể không chấp nhận hoặc bỏ qua gợi ý. Không bật khi ứng dụng cần `JMSMessageID` để truy vết hoặc đang dùng timestamp; đây không phải tính năng đảm bảo hiệu năng.

## 4. Xây dựng message đúng trước khi gửi

`Session` tạo được các loại message như `TextMessage`, `BytesMessage`, `MapMessage`, `StreamMessage`, `ObjectMessage`. Với giao tiếp giữa hệ thống, văn bản JSON hoặc dữ liệu bytes có schema thường dễ version hóa hơn object serialization Java. `ObjectMessage` có rủi ro deserialize dữ liệu không tin cậy.

Một message chứa:

| Vùng dữ liệu | Ví dụ | Chủ thể quyết định |
| --- | --- | --- |
| **Body** | JSON đơn hàng | Ứng dụng |
| **Application properties** | `eventType`, `eventId`, `schemaVersion` | Ứng dụng đặt bằng `setStringProperty`, `setIntProperty`,… |
| **Application headers phù hợp** | `JMSCorrelationID`, `JMSReplyTo`, `JMSType` | Ứng dụng khi có mô hình sử dụng rõ ràng |
| **Provider-assigned headers** | `JMSMessageID`, `JMSTimestamp`, `JMSDestination`, `JMSDeliveryMode`, `JMSPriority`, `JMSExpiration` | Provider cập nhật khi gửi |

Ví dụ tạo payload và metadata **trước** `send`:

~~~java
TextMessage message = session.createTextMessage("""
        {"type":"OrderCreated","orderId":"O-42","schemaVersion":1}
        """.strip());
message.setStringProperty("eventType", "OrderCreated");
message.setStringProperty("eventId", "evt-42");
message.setIntProperty("schemaVersion", 1);
message.setJMSCorrelationID("request-42");
producer.send(message);
~~~

Ở ví dụ này, `eventId` là ID **nghiệp vụ** do producer cấp; nó nên ổn định khi retry cùng một sự kiện và dùng làm khóa chống xử lý trùng tại consumer. `JMSMessageID` do provider cấp cho từng lần gửi, thường khác giữa các lần phát lại bởi producer. `JMSCorrelationID` chủ yếu giúp ghép luồng xử lý/request–reply; không tự thay thế `eventId`. `JMSReplyTo` thích hợp khi consumer cần biết destination gửi phản hồi.

**Không tự dự đoán hoặc gán trước giá trị header do provider chịu trách nhiệm.** Sau send đồng bộ thành công, có thể đọc `message.getJMSMessageID()` (nếu ID không bị vô hiệu hóa); với send bất đồng bộ phải chờ callback trước khi đọc các trường provider có thể sửa. JMS message selector đánh giá **header và property**, không tự đọc sâu JSON body.

## 5. Ví dụ Java hoàn chỉnh ở tầng JMS API: gửi một sự kiện

Tệp `src/main/java/com/example/jms/OrderMessageSender.java`:

~~~java
package com.example.jms;

import jakarta.jms.Connection;
import jakarta.jms.ConnectionFactory;
import jakarta.jms.DeliveryMode;
import jakarta.jms.JMSException;
import jakarta.jms.MessageProducer;
import jakarta.jms.Queue;
import jakarta.jms.Session;
import jakarta.jms.TextMessage;

public final class OrderMessageSender {
    private final ConnectionFactory connectionFactory;

    public OrderMessageSender(ConnectionFactory connectionFactory) {
        this.connectionFactory = connectionFactory;
    }

    public String sendOrderCreated(String eventId) throws JMSException {
        if (eventId == null || eventId.isBlank()) {
            throw new IllegalArgumentException("eventId must not be blank");
        }

        try (Connection connection = connectionFactory.createConnection();
             Session session = connection.createSession(
                     false, Session.AUTO_ACKNOWLEDGE)) {

            Queue orders = session.createQueue("orders.events");
            try (MessageProducer producer = session.createProducer(orders)) {
                producer.setDeliveryMode(DeliveryMode.PERSISTENT);
                producer.setPriority(4);
                producer.setTimeToLive(300_000L); // 5 phút

                TextMessage message = session.createTextMessage(
                        """
                        {"type":"OrderCreated","orderId":"O-42","schemaVersion":1}
                        """.strip()
                );
                message.setStringProperty("eventType", "OrderCreated");
                message.setStringProperty("eventId", eventId);
                message.setIntProperty("schemaVersion", 1);

                producer.send(message);
                return message.getJMSMessageID();
            }
        }
    }
}
~~~

**Điều kiện chạy:** Ví dụ là một class đầy đủ biên dịch bằng Java 17+ với dependency `jakarta.jms-api` 3.1 và **JMS provider** tương thích. Class **không có `main`**, vì ứng dụng phải cung cấp `ConnectionFactory` đã kết nối tới broker (qua Spring DI, JNDI hoặc bootstrap đặc thù). Không thể chạy riêng bằng `java OrderMessageSender` khi chưa có provider và code khởi động. Destination `orders.events` cũng phải được broker chấp nhận/provisioning theo cấu hình.

Đọc ví dụ theo thứ tự:

1. `ConnectionFactory.createConnection()` lấy kết nối; `createSession(false, Session.AUTO_ACKNOWLEDGE)` tạo session **không transaction**. `AUTO_ACKNOWLEDGE` là thiết lập liên quan nhận message, không có nghĩa producer đang chờ consumer ack.
2. `session.createQueue(...)` tạo đối tượng queue; `session.createProducer(orders)` tạo producer gắn với destination ấy.
3. `session.createTextMessage(...)` tạo body; các property được đặt **trước** khi gửi.
4. `setDeliveryMode`, `setPriority` và `setTimeToLive` thiết lập QoS. `send` mặc định đồng bộ; khi trả thành công, `getJMSMessageID()` cho phép quan sát ID do provider gán nếu ID được tạo.
5. `try-with-resources` đóng producer, session và connection. Các interface JMS này kế thừa `AutoCloseable`; session/connection còn xử lý tài nguyên liên quan khi đóng.

**Chú ý:** Không cần `connection.start()` chỉ để **gửi**; phương thức ấy chủ yếu khởi động quá trình **nhận/giao** message tới consumer. Cũng không tạo một connection/session mới cho từng message trong ứng dụng lưu lượng cao nếu provider/framework đã có cơ chế caching/pooling an toàn; ví dụ tạo/đóng trọn tài nguyên để minh họa lifecycle cho một phép gửi.

**Không có stdout cố định:** hàm trả về `JMSMessageID` do broker cấp (hoặc giá trị có thể là `null` nếu provider bỏ tạo ID theo cấu hình). Kết quả phụ thuộc provider, nên không dựng sẵn một ID hoặc log giả.

## 6. Gửi nhiều message: lựa chọn chính sách theo từng lần

Đoạn dưới giả định `session` và `producer` hợp lệ, producer đã gắn queue:

~~~java
TextMessage normal = session.createTextMessage("normal");
producer.send(normal); // QoS mặc định của producer

TextMessage urgent = session.createTextMessage("urgent");
producer.send(
        urgent,
        DeliveryMode.PERSISTENT,
        8,
        30_000L
);
~~~

Thông điệp `urgent` dùng QoS tường minh của lần gửi này; các thiết lập mặc định của producer vẫn giữ nguyên cho những lần gửi sau. Không đồng nhất priority 8 với “chắc chắn được xử lý trước”: nhiều consumer, broker policies, redelivery và concurrency có thể thay đổi thứ tự quan sát.

Với producer không gắn đích, truyền destination trước message:

~~~java
try (MessageProducer producer = session.createProducer(null)) {
    Queue billing = session.createQueue("billing.tasks");
    Topic events = session.createTopic("orders.events");

    producer.send(billing, session.createTextMessage("invoice:O-42"));
    producer.send(events, session.createTextMessage("created:O-42"));
}
~~~

Hai lần gọi này gửi đến **hai destination riêng**, **không** tạo một thao tác transaction nguyên tử khi session không transacted. Đặc biệt, tạo producer không gắn đích không tự biến queue thành topic hoặc ngược lại. Một message nên tương ứng một sự kiện/lệnh rõ ràng và hợp đồng gửi cụ thể; thường tạo `Message` mới cho mỗi sự kiện nghiệp vụ để không vô tình tái sử dụng header/property cũ.

## 7. Khi send trả thành công, khi send báo lỗi, và “kết quả chưa rõ”

### 7.1. Gửi đồng bộ

~~~text
Producer gọi send
   ├─ Trả về thành công → send hoàn tất theo bảo đảm của JMS provider/QoS
   │                      → chưa chứng minh listener đã xử lý
   └─ Ném JMSException  → thao tác có lỗi
                          → chưa chắc xác định được broker đã nhận hay chưa
~~~

`MessageProducer.send(...)` đồng bộ có thể ném `JMSException` hoặc các subtype như `InvalidDestinationException`, `MessageFormatException`. Với sự cố mạng tại ranh giới broker nhận message nhưng phản hồi chưa về, ứng dụng có thể **không biết chắc** trạng thái thực tế; retry có thể tạo bản gửi trùng. Đừng suy diễn “có exception thì message chắc chắn chưa tới broker”.

Thiết kế retry gửi cần phân loại:

- **Lỗi không thể khôi phục ngay**: payload vi phạm hợp đồng, destination sai/không có quyền, tên hoặc cấu hình không hợp lệ; cần sửa đầu vào hoặc cấu hình.
- **Lỗi tạm thời**: broker không sẵn sàng, timeout, kết nối bị ngắt; retry có giới hạn, backoff và cảnh báo.
- **Kết quả không rõ**: timeout hoặc mất phản hồi sát thời điểm broker nhận; cần phát lại có định danh nghiệp vụ ổn định và consumer idempotent.

JMS không thay thế **transactional outbox** khi yêu cầu “DB lưu sự kiện và message chắc chắn được phát” trong cùng nghiệp vụ. Nếu commit DB trước rồi send JMS và tiến trình chết giữa hai bước, message có thể chưa được gửi; nếu send rồi DB rollback thì message có thể mô tả trạng thái chưa tồn tại. Outbox giải quyết bằng cách ghi trạng thái nghiệp vụ và bản ghi sự kiện trong **cùng DB transaction**, sau đó publisher phát lại an toàn; consumer vẫn cần chịu được bản gửi lặp.

### 7.2. Delivery và xử lý là hai phạm vi khác nhau

| Tín hiệu | Bạn biết gì | Chưa thể kết luận |
| --- | --- | --- |
| `send` đồng bộ trả thành công | Provider hoàn tất thao tác send theo hợp đồng QoS | Consumer đã nhận/commit |
| `message.getJMSMessageID()` có giá trị | Provider đã gán JMS message ID | Sự kiện nghiệp vụ chỉ xuất hiện đúng một lần |
| Broker có queue depth tăng | Broker đang giữ message chờ xử lý, tùy thời điểm quan sát | Consumer có thể xử lý chính xác/tức thời |
| Consumer báo thành công | Handler chạy qua một đường xử lý | Tác dụng phụ bên ngoài đã có bảo đảm exactly-once |
| Đã ghi `eventId` vào DB với unique constraint | Có cơ chế từ chối áp dụng lại cùng event trong phạm vi transaction được thiết kế | Mọi hệ thống ngoài DB cũng tự động chống trùng |

Đối với gửi message quan trọng, quan sát cả phía publisher (send success/error/latency, retry/outbox backlog) và broker/consumer (queue depth, tuổi message, DLQ, redelivery, thời gian xử lý).

## 8. Local JMS transaction: gửi hai message hoặc không gửi message nào

Trong **Java SE hoặc Jakarta EE application-client environment**, một JMS session transacted có thể nhóm nhiều send thành một local transaction. Provider chỉ commit các thao tác JMS đó khi gọi `session.commit()`; `session.rollback()` hủy những send chưa commit. Ví dụ:

~~~java
package com.example.jms;

import jakarta.jms.Connection;
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSException;
import jakarta.jms.MessageProducer;
import jakarta.jms.Queue;
import jakarta.jms.Session;

public final class TransactionalSender {
    public static void publishPair(ConnectionFactory factory)
            throws JMSException {

        try (Connection connection = factory.createConnection();
             Session session = connection.createSession(
                     true, Session.SESSION_TRANSACTED)) {

            Queue queue = session.createQueue("orders.events");
            try (MessageProducer producer = session.createProducer(queue)) {
                try {
                    producer.send(
                            session.createTextMessage("order-created:O-42"));
                    producer.send(
                            session.createTextMessage("audit-created:O-42"));
                    session.commit();
                } catch (JMSException | RuntimeException ex) {
                    try {
                        session.rollback();
                    } catch (JMSException rollbackFailure) {
                        ex.addSuppressed(rollbackFailure);
                    }
                    throw ex;
                }
            }
        }
    }
}
~~~

**Phạm vi:** Đây là ví dụ local JMS transaction; provider và broker phải hỗ trợ tương ứng. Nếu đang trong Jakarta EE web/EJB container hoặc JTA transaction do container quản lý, quy tắc tạo session, `commit/rollback` khác với Java SE; cần để container transaction manager điều phối, không tùy ý gọi `commit()`.

**Kết quả mong muốn:** hai send trong cùng session/transaction được commit như một đơn vị JMS, hoặc rollback cùng nhau nếu lỗi trước commit. Tuy nhiên, nếu đường mạng đứt đúng lúc `commit`, producer vẫn có thể không xác định chắc broker đã commit hay chưa; unique event ID và cơ chế retry vẫn có ích.

**Giới hạn rất quan trọng:** local JMS transaction **không tự bao gồm** transaction của cơ sở dữ liệu SQL, lệnh HTTP hoặc thao tác gửi email. Để phối hợp DB → JMS, ưu tiên outbox/idempotency theo yêu cầu ứng dụng; transaction phân tán cần thiết kế, hạ tầng và đánh đổi riêng.

## 9. Asynchronous send bằng CompletionListener

Từ **JMS 2.0** (và Jakarta Messaging 3.x), `MessageProducer` có overload gửi bất đồng bộ. Cú pháp:

~~~java
producer.send(message, new CompletionListener() {
    @Override
    public void onCompletion(Message completedMessage) {
        System.out.println("JMS send completed");
    }

    @Override
    public void onException(Message failedMessage, Exception cause) {
        System.err.println("JMS send failed: " + cause.getMessage());
    }
});
~~~

Đoạn này là **một phần bên trong phương thức** đã có `producer`, `message` hợp lệ và import `jakarta.jms.CompletionListener` cùng `jakarta.jms.Message`; nó không phải chương trình `main` độc lập. Lifecycle owner phải giữ tài nguyên sống đủ lâu để callback được gọi, và theo dõi kết quả trong callback.

Quy tắc then chốt:

1. **`send(..., CompletionListener)` trả về chưa chắc đã gửi xong.** Chỉ khi provider gọi `onCompletion` thì ứng dụng mới có mức tin cậy tương đương send đồng bộ thành công. `onException` báo lỗi nhưng cũng có thể còn **không chắc message đã được broker nhận hay chưa**.
2. Nếu lỗi được phát hiện và throw trực tiếp **trong lệnh `send`**, không mong đợi callback lại được gọi cho cùng lần send ấy. Nếu lỗi không thể throw đồng bộ, provider gọi `onException`.
3. **Không đọc/sửa header, property hoặc body của chính `Message` sau khi `send` trả về cho tới khi callback được gọi**: provider có thể đang dùng và thay đổi object ở thread khác. Sau `onException`, giá trị các header do provider thiết lập có thể không xác định.
4. Callback **không được gọi `close()` trên chính producer/session/connection hay `commit()/rollback()` trên session sở hữu nó**. Không dùng session từ callback đồng thời với một thread ứng dụng khác.
5. Provider bảo đảm thứ tự callback tương ứng các send trên cùng producer và không gọi callback trên thread đang thực hiện lệnh `send`. **Session vẫn là ngữ cảnh một luồng logic**; callback không biến nó thành đối tượng thread-safe.
6. Khi `close` trên producer/session/connection, hoặc `commit/rollback` trên transacted session, provider phải chờ các send bất đồng bộ chưa hoàn tất và callback liên quan hoàn thành. Cần hiểu tác động khi shutdown và tránh callback bị treo.
7. Các phương thức async send có hạn chế sử dụng trong Jakarta EE web/EJB container; kiểm tra quy tắc môi trường và provider. Spring Boot độc lập có thể dùng nhưng phải quản lý lifecycle và lỗi cẩn thận.

**Khi nào nên dùng async?** Khi throughput hoặc độ trễ chờ phản hồi từ broker là nút thắt và hệ thống có cách quản lý callback, backpressure, shutdown, retry/outbox thật sự. Đừng chọn async chỉ để làm cho API “không chặn”: nó làm ranh giới xác nhận và xử lý lỗi khó hơn.

## 10. MessageProducer trong Spring JMS: JmsTemplate giúp việc gì?

Trong ứng dụng Spring, `JmsTemplate` quản lý việc lấy session, tạo message/producer, send và giải phóng tài nguyên theo `ConnectionFactory` cùng transaction context đã cấu hình. Tầng ứng dụng thường **không giữ `MessageProducer` làm singleton**; thay vào đó, dùng `JmsTemplate.send(...)` khi cần tự xây dựng `Message` và `convertAndSend(...)` khi muốn converter tạo message từ đối tượng Java.

Ví dụ hai class có thể đặt trong cùng tệp `src/main/java/com/example/jms/JmsOutboundConfiguration.java` của một ứng dụng Spring Boot 3.x có provider JMS đã kết nối:

~~~java
package com.example.jms;

import jakarta.jms.ConnectionFactory;
import jakarta.jms.DeliveryMode;
import jakarta.jms.TextMessage;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;

@Configuration
public class JmsOutboundConfiguration {
    @Bean
    JmsTemplate jmsTemplate(ConnectionFactory connectionFactory) {
        JmsTemplate template = new JmsTemplate(connectionFactory);
        template.setExplicitQosEnabled(true);
        template.setDeliveryMode(DeliveryMode.PERSISTENT);
        template.setPriority(4);
        template.setTimeToLive(300_000L);
        return template;
    }
}

@Component
class OrderEventPublisher {
    private final JmsTemplate jmsTemplate;

    OrderEventPublisher(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    public void publish(String eventId) {
        jmsTemplate.send("orders.events", session -> {
            TextMessage message = session.createTextMessage(
                    "{\"type\":\"OrderCreated\",\"orderId\":\"O-42\"}");
            message.setStringProperty("eventId", eventId);
            message.setStringProperty("eventType", "OrderCreated");
            return message;
        });
    }
}
~~~

**Điểm dễ bỏ sót:** `JmsTemplate.setDeliveryMode/ setPriority/ setTimeToLive` không nhất thiết có hiệu lực nếu **không** bật `setExplicitQosEnabled(true)`. Spring mặc định có thể để provider dùng QoS được quản trị tại `ConnectionFactory`. Vì vậy hãy xác minh giá trị thực tế bằng broker thay vì chỉ nhìn properties trên bean. Spring cũng hỗ trợ `JmsTemplate.setDeliveryDelay(...)` nếu dùng JMS 2.0+; chỉ đặt khi provider tương thích.

Ví dụ trên là **mã nằm trong Spring Boot application** (cần starter/provider, broker, destination, package scanning và cấu hình). Không có stdout cố định, không phải ứng dụng độc lập chạy bằng `javac`/`java`. Khi cần theo dõi kết quả publish, xử lý exception ở tầng nghiệp vụ và bổ sung outbox/retry khi có yêu cầu nhất quán.

**So sánh ngắn:**

| Cách gửi | Đối tượng chính | Phù hợp |
| --- | --- | --- |
| Classic JMS | `Session` + `MessageProducer` | Học lifecycle/QoS/async/transaction; tích hợp tầng thấp |
| Simplified JMS | `JMSContext` + `JMSProducer` | API thuận tiện, thao tác fluent, giảm mã boilerplate |
| Spring JMS | `JmsTemplate` + `MessageCreator` hoặc converter | Tích hợp DI, cấu hình, quản lý tài nguyên và transaction cùng Spring |

`JMSProducer` là **interface khác** với `MessageProducer`. Ví dụ simplified API:

~~~java
try (var context = connectionFactory.createContext()) {
    Queue queue = context.createQueue("orders.events");
    context.createProducer()
            .setTimeToLive(60_000L)
            .send(queue, "OrderCreated:O-42");
}
~~~

`JMSProducer.send(Destination, String)` dùng simplified API và tạo message thích hợp; cú pháp này **không** phải overload của `MessageProducer`. `JMSContext` chủ sở hữu vòng đời session/connection trong ví dụ. Các exception của simplified API thường là `JMSRuntimeException` (unchecked) thay vì `JMSException` checked của classic API.

## 11. Những quyết định thiết kế phía publisher

### 11.1. Gửi lệnh hay phát sự kiện?

- **Command** như `CreateInvoice`: thường gửi tới queue dành cho một loại tác vụ. Message phải mang đủ thông tin để worker xử lý; cân nhắc timeout, retry và idempotency.
- **Event** như `OrderCreated`: có thể phát tới topic để các subscription độc lập nhận. Nếu phải đảm bảo subscriber offline bắt kịp, thiết kế durable subscription/retention đúng; đó là thiết lập destination/subscriber, **không phải thuộc tính của một MessageProducer**.
- **Request–reply**: `JMSReplyTo` và `JMSCorrelationID` giúp định tuyến phản hồi và ghép request; vẫn cần timeout, cleanup và xử lý duplicate responses.

### 11.2. Một chiến lược retry gửi an toàn cần có gì?

1. **Stable business key**: sự kiện `eventId` không đổi giữa các lần retry; đừng sinh ID mới mỗi lần thử nếu đó vẫn là cùng một sự kiện.
2. **Trạng thái có thể phục hồi**: nếu publish là phần của DB transaction, sử dụng outbox; publisher có thể thử lại khi broker không sẵn sàng hoặc khi kết quả send không rõ.
3. **Backoff và giới hạn**: tránh vòng lặp nóng làm nghẽn broker. Phân loại lỗi vĩnh viễn (payload/permission) khỏi lỗi tạm thời.
4. **Consumer idempotent**: message có thể được gửi hoặc giao lại; consumer áp dụng thay đổi nghiệp vụ theo unique key/transaction phù hợp.
5. **Observability**: đo tỷ lệ send lỗi, retry count, publish latency, outbox lag, queue depth và message expiry, tránh kết luận thành công chỉ từ log “đã gọi send”.

### 11.3. Tài nguyên, hiệu năng và an toàn

- **Không share `Session` giữa nhiều thread**; một `Connection` có thể hỗ trợ nhiều session, nhưng mỗi session có ownership/lifecycle riêng. `MessageProducer` gắn session đó không phải một publisher singleton dùng chung đa luồng tùy tiện.
- Mở/đóng connection trong mỗi lần gửi có thể rất tốn chi phí. Dùng caching/pooling do Spring/provider quản lý khi có tải; đừng tự viết pool của `Session` không kiểm soát transaction và close.
- Xác định chính sách **payload size** và dữ liệu nhạy cảm; tránh gửi credential hoặc thông tin bảo mật vào log. Kiểm soát quyền publish tới destination.
- **PERSISTENT** thường tốn chi phí lưu trữ hơn NON_PERSISTENT; chỉ giảm bảo đảm khi yêu cầu nghiệp vụ cho phép. Producer throughput cao còn phải xét broker capacity và backpressure.
- Retry, priority và delay không thay thế xử lý message lỗi ở consumer: **DLQ** chủ yếu xử lý message không thể tiêu thụ thành công; lỗi publish trước khi tới broker cần cơ chế publisher-side riêng.

## 12. Bài tập thực hành theo thứ tự

**Bài tập 1 – Fixed destination:** Tạo `Session` không transacted, một queue, một `MessageProducer`, gửi `TextMessage` chứa `eventId`. Quan sát `JMSMessageID` sau `send` đồng bộ và message trên broker. Đặt câu hỏi: bước nào đã thành công, bước nào chưa kiểm chứng?

**Bài tập 2 – Unidentified producer:** Tạo `session.createProducer(null)`, gửi hai `TextMessage` khác nhau tới hai destination. Thử dùng `send(message)` không kèm destination và ghi nhận lỗi API. Không thử sai trực tiếp trên broker production.

**Bài tập 3 – QoS:** Gửi message với `PERSISTENT`/`NON_PERSISTENT`, priority 4/8 và TTL 5 giây. Khởi động lại broker trong môi trường thử nghiệm, quan sát nội dung tồn tại, thứ tự thực tế, thời hạn hết hạn. Không mặc định mọi broker xử lý giống nhau.

**Bài tập 4 – Delay so với TTL:** Đặt deliveryDelay 10 giây và TTL 5 giây; kiểm tra message có đến consumer không. Sau đó đổi TTL 30 giây. Giải thích vì sao “send thành công” vẫn có thể không dẫn tới delivery.

**Bài tập 5 – Atomic JMS send:** Dùng transacted session gửi hai message, cố tình throw exception trước `session.commit()` và gọi `rollback()`; xác minh broker không thấy hai message chưa commit. Lặp lại với `commit()` thành công. So sánh riêng với thao tác DB nằm ngoài JMS transaction.

**Bài tập 6 – Async completion:** Dùng `CompletionListener`, log rõ thời điểm gọi `send`, khi `send` trả về và khi callback đến. Không đọc object `Message` trước callback. Thử broker unavailable và phân biệt exception đồng bộ với callback `onException`.

**Bài tập 7 – Mất phản hồi send:** Ở test broker/network, tạo lỗi giao tiếp sát lúc send hoàn tất, thử lại bằng **cùng `eventId`**, xác minh consumer có idempotency. Ghi nhận trường hợp “kết quả chưa rõ” thay vì ép câu trả lời thành “đã gửi” hoặc “chưa gửi”.

### Checklist tự đánh giá

- Tôi phân biệt `MessageProducer`, `JMSProducer` và `JmsTemplate`, và biết đối tượng nào sở hữu `Session`.
- Tôi nhớ chữ ký của `send(message, deliveryMode, priority, timeToLive)` cùng đơn vị mili-giây của TTL/delay.
- Tôi biết dùng `createProducer(destination)` so với `createProducer(null)` và chọn đúng overload `send`.
- Tôi tạo body/property trước `send`, hiểu header provider gán sau khi gửi và không lạm dụng `JMSMessageID` làm event ID nghiệp vụ.
- Tôi giải thích được sync return, async callback, lỗi kết quả không rõ, JMS transaction và giới hạn khi DB giao dịch riêng.
- Tôi có thể xây dựng thí nghiệm kiểm tra message expiry, broker failure, retry và xử lý trùng, có bằng chứng quan sát cụ thể.

## Tài liệu tham chiếu

1. [Jakarta Messaging 3.1 – MessageProducer Javadoc](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/messageproducer): đầy đủ overload `send`, QoS, delivery delay, lifecycle và async completion.
2. [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html): sections về producing, threading, delivery mode, TTL, delay, transaction, exception semantics.
3. [Jakarta Messaging 3.1 – Session Javadoc](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/session): session factory, createProducer, local transaction và resource lifecycle.
4. [Spring Framework – Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html): `JmsTemplate` và cấu hình explicit QoS.

**Kết quả cần nắm:** `MessageProducer` giải quyết **thao tác gửi** và các tùy chọn của message; ứng dụng vẫn phải thiết kế transaction, retry, định danh nghiệp vụ, xử lý trùng và quan sát end-to-end để đạt độ tin cậy thực sự.