# Consumer không nhận do Connection chưa start, selector hoặc sai destination

> **Chương:** Chẩn đoán sự cố  
> **Phạm vi:** Khoanh vùng producer đã gửi message nhưng consumer Java/JMS không nhận trong ActiveMQ Classic hoặc Artemis. Ba nguyên nhân trọng tâm là **Connection/JMSContext chưa start**, **message selector không match**, và **consumer nghe sai destination hoặc sai Queue/Topic**. Bài dùng bằng chứng broker, lifecycle JMS, property/selector và mô hình address/queue để tìm đúng nguyên nhân.

## 1. Định nghĩa triệu chứng trước khi sửa

“Consumer không nhận” có thể là:

1. Không tạo được connection hoặc session.
2. Connection tạo được nhưng chưa gọi start(), nên delivery chưa bắt đầu.
3. Consumer tồn tại nhưng selector loại message.
4. Consumer đăng ký destination khác tên, khác loại hoặc khác broker với producer.
5. Message đã được nhận nhưng handler lỗi, không log hoặc transaction chưa commit.
6. Queue consumer đang theo dõi không có pending message vì message đã ACK, hết hạn, vào DLQ hoặc được consumer khác lấy.

Hãy xác định bốn điểm: producer gửi tới broker nào; message được route tới address/queue/topic nào; consumer kết nối tới broker/destination nào; và connection/selector có cho phép message được dispatch không.

~~~mermaid
flowchart TD
    P["Producer send"] --> R{"Send/commit thành công?"}
    R -->|"Không"| E["Endpoint, auth, exception, transaction"]
    R -->|"Có"| D{"Đúng destination?"}
    D -->|"Không"| X["Queue/Topic, address, queue binding"]
    D -->|"Có"| Q{"Có pending message?"}
    Q -->|"Không"| M["ACK, expiry, DLQ hoặc consumer khác"]
    Q -->|"Có"| C{"Connection đã start?"}
    C -->|"Không"| S["Connection.start / JMSContext.start"]
    C -->|"Có"| F{"Selector match?"}
    F -->|"Không"| L["Kiểm tra property, type, selector"]
    F -->|"Có"| O["Lifecycle, dispatch, exception, ACK"]
~~~

**Không kết luận từ một dấu hiệu đơn lẻ.** Connection mở không chứng minh message ở đúng queue; queue có message không chứng minh consumer đã start; consumer count lớn hơn 0 không chứng minh selector match.

## 2. Phân biệt ba nguyên nhân

| Dấu hiệu | Connection chưa start | Selector không match | Sai destination |
|---|---|---|---|
| Connection tạo được | Thường có | Có | Có |
| Consumer object tạo được | Có thể có | Có | Có thể có |
| Queue producer có pending | Có thể có | Thường có | Có thể ở queue khác |
| Consumer count | Có thể tăng | Có thể tăng | Tăng ở destination consumer nghe |
| Message được dispatch | Chưa cho tới khi start | Không nếu selector false | Không ở destination khác |
| Kiểm tra chính | Lifecycle | Property + selector | Endpoint + type/name |

## 3. Nguyên nhân 1: Connection đã tạo nhưng chưa start

### 3.1. Ý nghĩa của Connection.start()

Trong JMS, ConnectionFactory.createConnection() tạo connection tới provider, nhưng **delivery tới consumer chỉ bắt đầu sau khi ứng dụng gọi Connection.start()**. Đây là bước lifecycle riêng với việc tạo connection, session và consumer.

Trình tự low-level JMS điển hình:

1. Tạo Connection.
2. Tạo Session.
3. Tạo Queue/Topic và MessageConsumer.
4. Gọi connection.start().
5. Gọi receive() hoặc chờ listener callback.
6. Đóng consumer, session và connection.

Nếu thiếu bước 4, code có thể không ném exception rõ ràng; receive(timeout) hết thời gian dù broker còn pending message.

~~~mermaid
sequenceDiagram
    participant App as Consumer
    participant JMS as JMS client
    participant Broker
    App->>JMS: createConnection / createSession
    App->>JMS: createConsumer(queue)
    Note over JMS,Broker: Connection chưa start
    Broker-->>JMS: Message đang chờ
    Note over JMS: Chưa dispatch tới application
    App->>JMS: connection.start()
    Broker->>JMS: Deliver
    JMS-->>App: receive / onMessage
~~~

start() không khởi động broker. Nó chuyển connection client sang trạng thái cho phép nhận delivery.

### 3.2. Code lỗi và code đúng

Ví dụ lỗi: tạo consumer nhưng quên start connection.

~~~java
Connection connection = factory.createConnection(user, password);
Session session = connection.createSession(
        false, Session.AUTO_ACKNOWLEDGE);
Queue queue = session.createQueue("billing.commands");
MessageConsumer consumer = session.createConsumer(queue);

// Sai: chưa gọi connection.start().
Message message = consumer.receive(5_000L);
~~~

Cách sửa:

~~~java
Connection connection = factory.createConnection(user, password);
try {
    Session session = connection.createSession(
            false, Session.AUTO_ACKNOWLEDGE);
    try {
        Queue queue = session.createQueue("billing.commands");
        MessageConsumer consumer = session.createConsumer(queue);
        try {
            // Start chính connection chứa consumer này.
            connection.start();

            Message message = consumer.receive(5_000L);
            if (message == null) {
                System.out.println("NO_MESSAGE_WITHIN_TIMEOUT");
            } else {
                System.out.println("RECEIVED "
                        + message.getJMSMessageID());
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

Ví dụ dùng javax.jms, thường gặp với ActiveMQ Classic 5.x. Dự án Artemis Jakarta JMS dùng jakarta.jms và client artifact tương ứng. Không trộn hai namespace trong cùng compile unit; ý nghĩa lifecycle start vẫn giống nhau.

### 3.3. JMSContext cũng cần start()

JMSContext gom Connection và Session, nhưng **tạo context không đồng nghĩa delivery đã bắt đầu**. Ví dụ Artemis Jakarta JMS:

~~~java
import jakarta.jms.JMSConsumer;
import jakarta.jms.JMSContext;
import jakarta.jms.Message;
import jakarta.jms.Queue;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

try (ActiveMQConnectionFactory factory =
             new ActiveMQConnectionFactory("tcp://localhost:61616");
     JMSContext context = factory.createContext(
             user, password, JMSContext.AUTO_ACKNOWLEDGE)) {

    Queue queue = context.createQueue("billing.commands");
    JMSConsumer consumer = context.createConsumer(queue);

    context.start();

    Message message = consumer.receive(5_000L);
    if (message == null) {
        System.out.println("NO_MESSAGE");
    } else {
        System.out.println("RECEIVED " + message.getJMSMessageID());
    }
    consumer.close();
}
~~~

Nếu dùng ActiveMQ Classic 5.x, API phổ biến là javax.jms; kiểm tra đúng artifact/client generation. Ví dụ trên dùng Artemis Jakarta client và jakarta.jms.

### 3.4. Spring JMS quản lý start/stop

Với @JmsListener, Spring listener container quản lý connection/session/consumer và lifecycle. **Không gọi Connection.start() thủ công trong method listener.**

Kiểm tra:

- Listener container đã được khởi tạo và auto-start chưa?
- JmsListenerEndpointRegistry báo container running hay stopped?
- Có đặt autoStartup=false hoặc lifecycle phase trì hoãn start không?
- Có exception tạo connection/consumer trong startup log không?
- ConnectionFactory được inject có đúng provider và broker URL không?

Bean @JmsListener tồn tại trong ApplicationContext không chứng minh listener đã subscribe thành công. Nếu container stopped, hãy sửa lifecycle/configuration; đừng thêm start() vào callback.

## 4. Nguyên nhân 2: Selector không match

### 4.1. Selector lọc header/property, không đọc JSON body

JMS selector là biểu thức theo tập cú pháp kiểu SQL-92 subset. Nó thường xét JMS headers như JMSPriority, JMSCorrelationID, JMSType và application properties được đặt bằng setStringProperty, setIntProperty, setBooleanProperty…

Selector **không tự parse JSON/XML body**. Nếu orderType chỉ tồn tại trong JSON payload, selector orderType = 'EXPRESS' không tự tìm được trường đó.

Ví dụ consumer:

~~~java
MessageConsumer consumer = session.createConsumer(
        queue,
        "priority >= 5 AND region = 'south'");
~~~

Producer cần đặt property đúng tên và kiểu:

~~~java
TextMessage message = session.createTextMessage(
        "{\"orderId\":\"O-100\",\"kind\":\"EXPRESS\"}");
message.setIntProperty("priority", 7);
message.setStringProperty("region", "south");
message.setStringProperty("eventType", "OrderCreated");
producer.send(queue, message);
~~~

Nếu producer thay priority thành String "7", hoặc đặt Region thay vì region, selector cũ không còn tương đương. Selector so sánh theo kiểu dữ liệu; tên property phải thống nhất chính tả và case.

### 4.2. NULL, literal và kiểu dữ liệu

Trong selector, so sánh với property không tồn tại/NULL không trở thành TRUE; chỉ message có selector evaluate thành TRUE mới được chọn. Dùng IS NULL/IS NOT NULL, không dùng = NULL.

| Ý định | Selector |
|---|---|
| String bằng | region = 'south' |
| Numeric | attempt >= 3 |
| Boolean | urgent = TRUE |
| Một trong nhiều giá trị | kind IN ('created','updated') |
| Thiếu property | kind IS NULL |
| Có property | kind IS NOT NULL |
| Header correlation | JMSCorrelationID = 'req-9' |
| String có dấu nháy | owner = 'O''Reilly' |

Không viết region = south nếu south là giá trị String; literal String phải đặt trong dấu nháy đơn. Không viết attempt >= '3' nếu producer đặt property numeric.

### 4.3. Thu hẹp selector từng điều kiện

Giả sử selector:

~~~sql
eventType IN ('InvoiceCreated','InvoiceUpdated')
AND tenantId = 'vn-01'
AND priority >= 4
AND retryable = TRUE
~~~

Khoanh vùng theo thứ tự:

1. Trên queue test, tạo consumer không selector để xác nhận message tồn tại.
2. Thử selector đơn giản tenantId = 'vn-01'.
3. Thêm từng điều kiện: eventType, priority, retryable.
4. Kiểm tra producer đặt property cùng tên và đúng kiểu.
5. Dùng message có marker riêng, log property names/types trong test.
6. Sửa producer contract hoặc selector tại đúng điều kiện không match.

Không dùng consumer không selector trên queue production nếu nó có thể nhận và ACK message nghiệp vụ. Selector chỉ lọc message mà user đã có quyền consume; nó không thay authorization hay tenant isolation.

## 5. Nguyên nhân 3: Sai destination hoặc sai Queue/Topic

### 5.1. Queue và Topic không tương đương

| Producer | Consumer | Kết quả |
|---|---|---|
| Queue billing.commands | Queue billing.commands | Competing consumers chia sẻ message; một message giao cho một consumer |
| Topic billing.events | Topic billing.events | Mỗi subscription phù hợp nhận bản sao theo semantics topic |
| Queue billing.commands | Topic billing.commands | Không tự nhận message queue |
| Topic billing.events | Queue billing.events | Không tự nhận message topic |

Tên giống nhau không làm Queue và Topic thành cùng destination. Trong JMS, loại object được tạo (createQueue/createTopic) và broker mapping đều quan trọng.

Topic subscriber non-durable không online lúc publish thường không có backlog để nhận sau đó. Nếu cần nhận message khi offline, phải thiết kế durable subscription với client ID/subscription name và policy phù hợp.

### 5.2. ActiveMQ Classic: physical destination

JMS API tạo destination:

~~~java
Queue queue = session.createQueue("billing.commands");
Topic topic = session.createTopic("billing.events");
~~~

Đối chiếu physical destination trên Web Console/JMX:

- Queue hay Topic?
- Tên có khác chữ hoa/chữ thường, dấu chấm, dấu gạch hoặc prefix không?
- Producer dùng virtual/composite destination hay destination thông thường?
- Wildcard/pattern có đúng loại destination không?
- Producer và consumer có kết nối đúng broker URL/network topology không?

Producer dùng billing.command còn consumer nghe billing.commands là hai destination khác nhau; broker có thể tạo cả hai và không báo lỗi typo.

### 5.3. Artemis: address, queue và routing type

Artemis có mô hình address và queue:

- Producer gửi tới address.
- Queue bind vào address và giữ message theo routing type.
- ANYCAST thường dùng cho queue/point-to-point.
- MULTICAST thường dùng cho topic/fan-out.
- Một address có thể có nhiều queue; không suy tên queue chỉ từ tên address nếu mapping được cấu hình khác.

Ví dụ address/anycast queue:

~~~xml
<addresses>
  <address name="billing.commands">
    <anycast>
      <queue name="billing.commands" durable="true"/>
    </anycast>
  </address>
</addresses>
~~~

Ví dụ multicast address:

~~~xml
<addresses>
  <address name="billing.events">
    <multicast/>
  </address>
</addresses>
~~~

Đây là fragment broker.xml; ghép vào đúng phần addresses theo schema version. Topic subscription queues có thể được tạo theo cơ chế JMS/durable subscription; chỉ khai báo multicast address không tự chứng minh đã có durable subscriber.

Với queue dưới một address khác tên, Artemis hỗ trợ Fully Qualified Queue Name (FQQN) dạng:

~~~text
address::queue
~~~

Ví dụ billing::commands-v1 chỉ hợp lệ nếu address billing có queue commands-v1. Đối chiếu binding trên broker thay vì đoán FQQN.

### 5.4. Producer và consumer kết nối hai broker khác nhau

Trong cluster, producer ở A và consumer ở B chỉ chia sẻ message nếu cluster routing, queue binding và forwarding được cấu hình đúng. Hai broker độc lập có cùng destination name **không chia sẻ message**.

Đối chiếu broker URL/hostname/port, protocol (OpenWire, Artemis Core, AMQP), cluster connection/network connector, node đang giữ queue, message load balancing/forwarding/redistribution và endpoint mà client reconnect tới.
## 6. Phân biệt destination mismatch với authorization/auto-create

Nếu consumer tạo destination hoặc consumer thất bại, đọc exception trước khi kết luận queue sai:

| Lỗi/dấu hiệu | Hướng điều tra |
|---|---|
| Authentication failure | Username/password, JAAS/LDAP, secret version |
| Authorization denied | Quyền consume/browse/create queue/address |
| Destination not found khi auto-create disabled | Provision destination hoặc bật auto-create có kiểm soát |
| Consumer tạo được nhưng receive timeout | Connection start, selector, backlog, destination mapping |
| Producer send thành công nhưng queue dự kiến rỗng | Producer routing address/destination, endpoint, send transaction commit |
| Queue pending tăng nhưng consumer count bằng 0 | Consumer chưa tạo được hoặc đang nghe destination khác |
| Consumer count tăng nhưng delivering count bằng 0 | Chưa start, selector không match, message chưa được route tới queue đó, hoặc consumer không có credits |

Broker có thể tự tạo destination nếu auto-create được bật. Điều đó khiến lỗi typo **không nhất thiết fail fast**: producer gửi nhầm có thể tạo queue mới và message nằm ở đó. Với môi trường quan trọng, provision destination rõ ràng, giới hạn auto-create và giám sát destination lạ.

## 7. Probe nhỏ: kiểm tra connection, selector và destination có kiểm soát

Một probe hữu ích phải tách từng giả thuyết. Đừng dùng cùng một test vừa tạo queue, vừa gửi message, vừa chạy selector phức tạp, rồi không biết bước nào thất bại.

### 7.1. Gửi message test với marker duy nhất

~~~java
String testId = java.util.UUID.randomUUID().toString();

TextMessage message = session.createTextMessage("probe:" + testId);
message.setStringProperty("probeId", testId);
message.setStringProperty("probeType", "consumer-diagnostic");
message.setIntProperty("probeVersion", 1);

producer.send(queue, message);
session.commit(); // nếu session transacted
~~~

Nếu session không transacted, bỏ commit() và dùng acknowledgment/delivery mode phù hợp. Ghi lại destination, broker endpoint (đã che thông tin nhạy cảm), testId, timestamp và kết quả send.

### 7.2. Consumer probe không selector

Trên queue test:

~~~java
MessageConsumer consumer = session.createConsumer(queue);
connection.start();

Message message = consumer.receive(5_000L);
if (message == null) {
    System.out.println("NO_MESSAGE");
} else {
    System.out.println("PROBE_RECEIVED id="
            + message.getStringProperty("probeId")
            + " jmsId=" + message.getJMSMessageID());
}
~~~

Nếu không selector vẫn không nhận:

1. Xác minh connection.start().
2. Xác minh queue/address pending.
3. Xác minh producer đã commit.
4. Xác minh cùng broker và đúng physical destination.
5. Xác minh consumer có quyền và được tạo trên đúng queue.

Nếu không selector nhận được nhưng selector production không nhận, vấn đề nằm ở **property/selector contract** hoặc selector đang loại message.

### 7.3. Không dùng probe để lấy mất message nghiệp vụ

Trên queue production, một probe consumer có thể **consume message thật**. AUTO_ACKNOWLEDGE có thể ACK ngay sau receive, làm message biến mất dù probe chỉ in log. Không chạy consumer test trên destination production trừ khi có quy trình an toàn, message được chọn bằng selector marker riêng và acknowledgment/rollback đã được thiết kế rõ.

Tốt nhất dùng queue test riêng với cùng broker policy, hoặc một consumer quan sát management/browse không destructive nếu broker/provider hỗ trợ và quyền được cấp.

## 8. Trình tự chẩn đoán từ ít xâm lấn đến kiểm tra sâu

### Bước 1 — Xác nhận producer thật sự gửi thành công

- Log exception của send().
- Nếu transacted, xác nhận commit() thành công.
- Ghi broker URL, destination type/name, testId/business ID.
- Với persistent delivery, xác nhận delivery mode và queue durable theo yêu cầu.

send() thành công ở client không luôn chứng minh message đã nằm trong **queue mà consumer đang nghe**: producer có thể gửi tới topic, address khác hoặc broker khác.

### Bước 2 — Xác minh message đang ở broker nào và queue nào

Dùng management console/JMX/management API/CLI của đúng broker version:

- Tìm physical queue/address.
- Kiểm tra message count/pending, delivering count, consumer count.
- Kiểm tra DLQ, expiry address/queue và destination typo gần giống.
- Kiểm tra node nhận message nếu là cluster.

Đừng purge queue hoặc restart broker trước khi ghi lại bằng chứng.

### Bước 3 — Xác minh connection/consumer lifecycle

- Có log connection create/start không?
- Connection.start()/JMSContext.start() có chạy trên **đúng connection** chứa consumer không?
- Có exception xảy ra trước dòng start?
- Connection có bị đóng ngay sau khi tạo consumer?
- Listener container có running/auto-start không?

Một connection khác trong cùng process được start **không tự start connection chứa consumer**.

### Bước 4 — Bỏ selector trong môi trường test

Tạo consumer không selector trên queue test có một marker message. Nếu nhận được, thêm selector từng điều kiện để tìm property không match.

### Bước 5 — So sánh destination producer/consumer

Đối chiếu đồng thời:

| Thuộc tính | Producer | Consumer |
|---|---|---|
| Broker URL/endpoint | Giá trị thực tế | Giá trị thực tế |
| Protocol | OpenWire/Core/AMQP… | Protocol client đang dùng |
| Destination kind | Queue/Topic | Queue/Topic |
| JMS destination name | Physical/logical name | Physical/logical name |
| Artemis address | Nếu có | Address đang bind |
| Artemis queue/subscription | Routing target | Queue/consumer binding |
| Selector | Không áp dụng hoặc routing | Expression thực tế |
| Security principal | User gửi | User consume |

### Bước 6 — Kiểm tra permission và policy

Nếu create consumer thất bại, đọc authorization error. Nếu create được nhưng không có message, kiểm tra queue/address policy, auto-create, routing type và consumer selector. Không cấp quyền admin để “thử xem có nhận không”.

## 9. Ví dụ tình huống và cách kết luận

| Hiện tượng | Bằng chứng | Nguyên nhân có khả năng | Hành động |
|---|---|---|---|
| receive(5000) luôn null, queue có pending | Consumer code không có start() | Connection chưa start | Gọi start đúng connection sau create consumer |
| Consumer count tăng, queue pending không giảm, selector đang lọc tenant='a' | Message chỉ có tenantId='a' | Sai tên property | Đồng bộ producer/selector |
| Producer queue orders.new, consumer nghe orders | Management hiển thị hai queue | Destination typo | Sửa physical name, kiểm tra message cũ ở queue nhầm |
| Producer dùng Topic, consumer dùng Queue cùng tên | Destination type khác | Sai Queue/Topic | Đồng bộ semantics |
| Artemis address có queue commands.v2, consumer dùng queue commands | Binding không trùng | Sai queue/address/FQQN | Chỉ rõ address và queue |
| Producer gửi tới broker A, consumer tới broker B độc lập | Hai broker không có cluster/bridge | Khác broker | Sửa endpoint hoặc cấu hình forwarding |
| Consumer create ném security exception | Broker log authorization denied | Thiếu consume permission | Cấp đúng role least privilege |
| Consumer chạy trong Spring nhưng không có delivery | Container stopped/autoStartup false | Listener lifecycle chưa start | Start container, kiểm tra startup error |
| Consumer nhận nhưng không có business log | JMS callback có exception trước log hoặc thread chết | Lỗi adapter/handler | Log correlation ID, exception, thread lifecycle |

## 10. Các lỗi code thường gặp

### 10.1. Start nhầm connection

Một ứng dụng có hai connection:

~~~java
Connection producerConnection = factory.createConnection();
Connection consumerConnection = factory.createConnection();

Session consumerSession = consumerConnection.createSession(
        false, Session.AUTO_ACKNOWLEDGE);
Queue consumerQueue = consumerSession.createQueue("billing.commands");
MessageConsumer consumer = consumerSession.createConsumer(consumerQueue);

// Sai: chỉ start connection của producer, không start connection của consumer.
producerConnection.start();

// Đúng: start chính connection đang sở hữu consumer.
consumerConnection.start();

// Sau khi xử lý, đóng consumer, consumerSession và cả hai connection
// theo thứ tự ngược với lúc tạo.
~~~

Phải gọi start() trên consumerConnection, hoặc dùng một connection chung theo thiết kế ứng dụng và quản lý lifecycle nhất quán. Không dựa vào việc một connection khác đã start.

### 10.2. Tạo selector nhưng producer không đặt property

Consumer:

~~~java
MessageConsumer consumer =
        session.createConsumer(queue, "eventType = 'PaymentCaptured'");
~~~

Producer chỉ đặt body JSON:

~~~java
TextMessage message =
        session.createTextMessage("{\"eventType\":\"PaymentCaptured\"}");
producer.send(queue, message);
~~~

Message **không có JMS property eventType**. Sửa producer:

~~~java
TextMessage message =
        session.createTextMessage("{\"eventType\":\"PaymentCaptured\"}");
message.setStringProperty("eventType", "PaymentCaptured");
producer.send(queue, message);
~~~

Nếu muốn lọc trường trong JSON body, hãy chuyển trường đó thành JMS property khi publish hoặc dùng một tầng consumer/application filter. JMS selector không tự parse JSON.

### 10.3. Tạo Topic trong producer, Queue trong consumer

Producer:

~~~java
Topic events = session.createTopic("billing.events");
MessageProducer producer = session.createProducer(events);
~~~

Consumer:

~~~java
Queue events = session.createQueue("billing.events");
MessageConsumer consumer = session.createConsumer(events);
~~~

Hai object có cùng tên nhưng khác semantics. Đồng bộ destination type và cấu hình broker; nếu yêu cầu fan-out thì cả hai phía phải dùng topic/subscription tương ứng.

### 10.4. Consumer bị đóng ngay sau khi tạo

Ví dụ lifecycle lỗi:

~~~java
MessageConsumer createConsumer(Connection connection)
        throws Exception {
    Session session = connection.createSession(
            false, Session.AUTO_ACKNOWLEDGE);
    MessageConsumer consumer =
            session.createConsumer(session.createQueue("billing.commands"));
    session.close(); // consumer phụ thuộc session đã đóng
    return consumer;
}
~~~

MessageConsumer phụ thuộc Session; không trả consumer ra ngoài sau khi đóng session. Connection, Session, Consumer phải có lifetime bao trùm thời gian nhận và xử lý.

## 11. Spring JMS: xác minh container và factory

Ví dụ factory listener:

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Configuration
public class JmsListenerConfig {
    @Bean
    DefaultJmsListenerContainerFactory billingListenerFactory(
            ConnectionFactory connectionFactory) {

        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setConcurrency("1-4");
        factory.setSessionTransacted(true);
        return factory;
    }
}
~~~

Listener:

~~~java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class BillingListener {
    @JmsListener(
        destination = "billing.commands",
        containerFactory = "billingListenerFactory")
    public void onMessage(String payload) {
        System.out.println("received billing command");
        // Xử lý business; exception theo transaction policy.
    }
}
~~~

Ví dụ dùng Jakarta JMS; Classic 5.x với javax.jms cần Spring/provider generation tương ứng. Không trộn javax.jms.ConnectionFactory với listener container yêu cầu jakarta.jms.ConnectionFactory.

Spring container quản lý connection start khi container khởi động. Khi listener không nhận:

- Xem trạng thái container trong JmsListenerEndpointRegistry.
- Kiểm tra bean factory có được đăng ký đúng tên không.
- Kiểm tra autoStartup, lifecycle phase và context startup error.
- Kiểm tra destination và containerFactory trên annotation.
- Xem exception log của listener/connection recovery.
- Xác nhận listener không bị stop bởi management code.

Không gọi connection.start() trong callback onMessage; callback chỉ chạy sau khi container đã nhận delivery.

## 12. Kiểm tra bằng management console/JMX

### 12.1. Các chỉ số cần đối chiếu

Tên attribute cụ thể tùy broker/version, nhưng các khái niệm cần tìm:

| Chỉ số | Ý nghĩa chẩn đoán |
|---|---|
| Message count/pending | Có message đang chờ trong queue không? |
| Delivering count/in-flight | Broker đã dispatch nhưng chưa ACK bao nhiêu message? |
| Consumer count | Có consumer đăng ký queue không? |
| Enqueue/dequeue/ack count | Message được gửi, nhận và xác nhận thế nào? |
| Expired count | Message có hết TTL trước khi consumer nhận? |
| DLQ count | Message có bị chuyển khỏi queue chính? |
| Address/queue binding | Queue có bind vào address/routing type mong đợi? |
| Connection/session count | Client có kết nối và tạo session? |

Cách diễn giải:

- **Pending > 0, consumer = 0:** consumer chưa đăng ký, đang nghe destination khác, hoặc connection chưa start tùy broker metric.
- **Pending > 0, consumer > 0, delivering = 0:** nghi selector không match, connection chưa start, credits/prefetch hoặc routing.
- **Pending = 0, enqueue tăng:** message có thể đã được ACK, chuyển sang DLQ/expiry hoặc được consumer khác lấy.
- **Consumer count tăng trên queue khác:** destination mismatch rất có khả năng.

consumerCount không luôn có nghĩa consumer đang nhận được message; selector và lifecycle vẫn cần kiểm tra.

### 12.2. Artemis và Classic có công cụ quản trị riêng

- **Artemis:** management console/JMX/management API và CLI của Artemis cho address, queue, consumer, message count, delivering count, bindings.
- **Classic:** Web Console/JMX MBeans cho destination, enqueue/dequeue, consumer count, connections và DLQ.

Không copy câu lệnh CLI của một provider sang provider còn lại. Ghi broker version và endpoint quản trị trước khi chạy lệnh; dùng quyền read-only nếu chỉ điều tra.

## 13. Runbook 10 phút cho on-call

1. **Xác nhận gửi:** producer có send exception? Transaction đã commit? Ghi testId/business ID.
2. **Tìm message:** trên broker đúng endpoint, tìm queue/address/DLQ/expiry; ghi pending count.
3. **Đối chiếu destination:** Queue hay Topic? Exact name/case? Artemis address/queue/FQQN?
4. **Kiểm tra consumer:** connection/session/consumer được tạo chưa? Có create exception?
5. **Kiểm tra start:** low-level JMS có gọi Connection.start() trên đúng connection? JMSContext có start()?
6. **Kiểm tra selector:** thử trên queue test với selector đơn giản rồi thêm từng property.
7. **Kiểm tra security:** auth/authorization denied có được log không?
8. **Kiểm tra client framework:** Spring listener container có running và autoStartup không?
9. **Thử probe có kiểm soát:** destination test, marker riêng, timeout hữu hạn, tránh consume dữ liệu production.
10. **Sau sửa:** xác minh message cũ được xử lý hoặc vẫn nằm ở queue/DLQ đúng nơi; đối soát ID và ACK, không chỉ thấy một message mới chạy thành công.

Không purge queue, đổi selector thành rỗng hoặc bật auto-create toàn broker như một thao tác chữa cháy mặc định. Những thay đổi đó có thể che mất lỗi gốc và làm sai routing dữ liệu.

## 14. Checklist trước khi kết luận broker bị lỗi

- [ ] Producer đã gửi tới đúng broker URL/protocol/port?
- [ ] Transaction producer đã commit?
- [ ] Message đang ở đúng queue/address hay đang ở DLQ/expiry?
- [ ] Producer và consumer dùng cùng Queue/Topic semantics?
- [ ] Destination name chính xác cả dấu chấm, prefix và chữ hoa/thường?
- [ ] Artemis address có queue binding/routing type phù hợp?
- [ ] Consumer đang kết nối đúng node/broker?
- [ ] Connection chứa consumer đã được start?
- [ ] JMSContext đã gọi start() nếu dùng low-level JMSContext?
- [ ] Spring listener container đã running và không bị stop?
- [ ] Selector có property tồn tại, đúng tên, đúng kiểu và giá trị?
- [ ] Selector không cố đọc trường trong JSON/XML body?
- [ ] User có quyền consume và destination được provision đúng?
- [ ] Consumer/session không bị đóng trước khi nhận?
- [ ] Có bằng chứng từ pending/delivering/consumer count và log testId?

## 15. Kết luận

Khi consumer không nhận message, hãy tách ba câu hỏi: **connection đã start chưa**, **selector có match message không**, và **consumer có nghe đúng destination không**. JMS connection được tạo không có nghĩa delivery đã bắt đầu; selector chỉ lọc header/property theo cú pháp JMS; Queue và Topic cùng tên vẫn là hai mô hình phân phối khác nhau. Với Artemis, cần đối chiếu cả address, queue binding, routing type và FQQN khi sử dụng.

Quy trình hiệu quả là chứng minh producer đã commit, tìm message ở broker, đối chiếu destination, xác minh lifecycle start(), rồi giảm selector từng điều kiện. Với Spring, kiểm tra trạng thái listener container vì framework quản lý start/stop. Chỉ sau khi có bằng chứng về đúng broker, đúng queue và đúng consumer mới kết luận lỗi nằm ở broker.

Một chẩn đoán tốt để lại được bằng chứng: endpoint, destination type/name, selector, test ID, pending/delivering/consumer counts, lifecycle state và kết quả probe. Những dữ liệu đó giúp sửa đúng nguyên nhân mà không làm mất message hoặc vô tình mở rộng quyền truy cập.
