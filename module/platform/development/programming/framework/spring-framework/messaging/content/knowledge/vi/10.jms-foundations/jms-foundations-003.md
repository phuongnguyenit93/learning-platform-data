# ConnectionFactory, Connection, Session, Producer và Consumer

> Mục tiêu: hiểu vai trò và vòng đời của các tài nguyên cốt lõi trong Jakarta Messaging (JMS), biết cách producer gửi message và consumer nhận message, nắm rõ transaction/acknowledgement, đồng thời hiểu Spring JMS quản lý các tài nguyên này qua `JmsTemplate` và listener container như thế nào.

## 1. Bức tranh tổng thể của JMS

JMS (Jakarta Messaging; trước đây là Java Message Service) là API chuẩn để ứng dụng Java gửi và nhận message thông qua một messaging provider như ActiveMQ Artemis, IBM MQ hoặc một sản phẩm hỗ trợ JMS khác. Provider quản lý kết nối đến broker, destination, lưu trữ và phân phối message theo khả năng của sản phẩm.

Một luồng gửi/nhận điển hình có các thành phần:

```text
Application
    |
    v
ConnectionFactory
    | createConnection()
    v
Connection
    | createSession()
    v
Session
    |                         |
    v                         v
MessageProducer           MessageConsumer
    |                         ^
    v                         |
Destination (Queue / Topic) --+
```

Các thành phần trả lời những câu hỏi khác nhau:

- `ConnectionFactory`: tạo kết nối đến JMS provider.
- `Connection`: đại diện cho kết nối của client đến provider.
- `Session`: ngữ cảnh tạo message, tạo producer/consumer và quản lý transaction hoặc acknowledgement.
- `MessageProducer`: gửi message đến destination.
- `MessageConsumer`: nhận message từ destination theo kiểu đồng bộ hoặc bất đồng bộ.
- `Destination`: đích gửi/nhận, thường là queue hoặc topic.

Trong Spring, ứng dụng thường inject `ConnectionFactory` rồi dùng `JmsTemplate` để gửi hoặc listener container để nhận. Spring quản lý phần lớn việc tạo, sử dụng và đóng tài nguyên cho từng thao tác.

## 2. ConnectionFactory: điểm khởi đầu tạo kết nối

`jakarta.jms.ConnectionFactory` là interface do JMS provider cung cấp. Implementation cụ thể biết cách kết nối đến broker, sử dụng địa chỉ máy chủ, thông tin xác thực, TLS và các tùy chọn riêng của provider.

Ứng dụng thường nhận `ConnectionFactory` qua dependency injection hoặc cấu hình JNDI. Không nên tự tạo implementation của provider trong logic nghiệp vụ.

Ví dụ tạo kết nối theo JMS API:

```java
import jakarta.jms.Connection;
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSException;

Connection createConnection(ConnectionFactory connectionFactory)
        throws JMSException {
    return connectionFactory.createConnection();
}
```

`ConnectionFactory` là factory dùng để tạo các connection. Trong môi trường production, nó thường được cấu hình với endpoint, credential, TLS, timeout và cơ chế reconnect theo provider. Credential nên lấy từ secret manager hoặc cấu hình bảo mật của môi trường, không ghi cứng trong mã nguồn.

Connection factory cũng là nơi có thể tích hợp connection pooling hoặc caching. Việc dùng pool/cache nào cần dựa trên provider và mô hình triển khai; không tự tạo một connection mới cho mọi message trong code nghiệp vụ.

## 3. Connection: kết nối client với provider

`Connection` đại diện cho kết nối đang mở giữa ứng dụng và JMS provider. Từ connection, ứng dụng tạo một hoặc nhiều `Session`.

Các thao tác quan trọng:

- `createSession(...)`: tạo session để làm việc với message.
- `start()`: bắt đầu phân phối message đến consumer. Với consumer nhận bất đồng bộ, connection phải được start trước khi provider chuyển message đến listener.
- `stop()`: tạm dừng phân phối message đến consumer.
- `close()`: đóng connection và giải phóng các session, producer, consumer liên quan.

Connection có thể phục vụ nhiều session. Tuy nhiên, việc tạo connection và duy trì socket thường tốn tài nguyên hơn việc tạo một message; vì vậy Spring listener container thường giữ các consumer lâu dài và tái sử dụng tài nguyên theo cấu hình.

Với producer chỉ gửi message, ứng dụng thường không cần gọi `start()` để bắt đầu nhận message. `start()` đặc biệt quan trọng khi connection có consumer cần nhận message.

## 4. Session: ngữ cảnh tạo và xử lý message

`Session` là ngữ cảnh làm việc chính giữa ứng dụng và provider. Session được tạo từ `Connection` và dùng để:

- Tạo `Queue`, `Topic` hoặc destination object khác.
- Tạo `MessageProducer` và `MessageConsumer`.
- Tạo các loại message như `TextMessage`, `BytesMessage` hoặc `MapMessage`.
- Quản lý transaction và acknowledgement trong phạm vi session.

Một nguyên tắc quan trọng của JMS là **Session không được thiết kế để nhiều thread sử dụng đồng thời**. Hãy dùng một session theo một luồng xử lý tại một thời điểm. Nếu cần concurrency, tạo nhiều session/consumer theo cách provider và listener container hỗ trợ thay vì chia sẻ cùng session cho nhiều thread.

### Tạo session và chọn acknowledgement mode

API cổ điển tạo session có dạng:

```java
Session session = connection.createSession(
        false,
        Session.AUTO_ACKNOWLEDGE
);
```

Tham số thứ nhất cho biết session có dùng transaction cục bộ hay không. Tham số thứ hai là acknowledgement mode khi session không transacted. Nếu session transacted, việc xác nhận message do `commit()` hoặc `rollback()` quyết định; acknowledgement mode riêng lẻ không điều khiển giao dịch đó.

Các acknowledgement mode chuẩn:

| Mode | Ý nghĩa | Lưu ý |
|---|---|---|
| `AUTO_ACKNOWLEDGE` | Provider tự xác nhận theo quy tắc của JMS sau khi message được nhận/xử lý theo kiểu nhận | Dễ dùng, nhưng cần hiểu thời điểm xác nhận của receive hoặc listener |
| `CLIENT_ACKNOWLEDGE` | Client chủ động gọi `Message.acknowledge()` | Trong JMS, acknowledge trên một message có thể xác nhận các message đã được session tiêu thụ trước đó |
| `DUPS_OK_ACKNOWLEDGE` | Cho phép provider xác nhận theo lô/lười hơn | Có thể xuất hiện duplicate; consumer cần idempotent |
| `SESSION_TRANSACTED` | Không phải acknowledgement mode truyền vào khi tạo session; transaction được bật bằng tham số `transacted=true` | Dùng `commit()` hoặc `rollback()` trên session |

Hãy chọn chế độ dựa trên yêu cầu giao nhận, transaction và khả năng xử lý trùng. Không nên coi acknowledgement là bằng chứng rằng toàn bộ nghiệp vụ ở hệ thống downstream đã hoàn tất.

## 5. Destination: Queue và Topic

Producer gửi message đến một `Destination`; consumer đăng ký nhận từ destination đó. Hai kiểu destination phổ biến:

- **Queue:** mô hình point-to-point. Một message được phân phối cho một consumer trong nhóm nhận cạnh tranh theo chính sách của provider.
- **Topic:** mô hình publish–subscribe. Các subscriber phù hợp có thể nhận bản sao message theo subscription và chính sách lưu giữ của provider.

Ví dụ tạo destination bằng session:

```java
Queue ordersQueue = session.createQueue("orders.incoming");
Topic orderEvents = session.createTopic("orders.events");
```

Tên queue/topic là tên logic theo hợp đồng của provider. Việc gọi `createQueue` hoặc `createTopic` tạo destination object trong client; nó không nhất thiết tạo tài nguyên vật lý trên broker. Một số provider hỗ trợ auto-create, nhưng production thường quản lý destination, quyền truy cập và chính sách qua công cụ quản trị hoặc Infrastructure as Code.

## 6. MessageProducer: gửi message

`MessageProducer` được tạo từ session và destination. Producer tạo hoặc nhận message rồi gửi đến queue/topic.

JMS định nghĩa nhiều loại message:

- `TextMessage`: nội dung văn bản, thường dùng cho JSON/XML hoặc text.
- `BytesMessage`: dữ liệu nhị phân.
- `MapMessage`: tập hợp các cặp tên/giá trị thuộc các kiểu JMS hỗ trợ.
- `ObjectMessage`: object Java có thể serialize; cần đặc biệt cẩn trọng với deserialization và nguồn dữ liệu không tin cậy.
- `StreamMessage`: chuỗi giá trị có thứ tự được đọc theo kiểu dữ liệu.
- `Message`: message chỉ có headers và properties, không có body ứng dụng.

Ví dụ gửi `TextMessage` bằng JMS API:

```java
import jakarta.jms.Connection;
import jakarta.jms.ConnectionFactory;
import jakarta.jms.MessageProducer;
import jakarta.jms.Queue;
import jakarta.jms.Session;
import jakarta.jms.TextMessage;

Connection connection = connectionFactory.createConnection();
Session session = null;
MessageProducer producer = null;
try {
    session = connection.createSession(false, Session.AUTO_ACKNOWLEDGE);
    Queue queue = session.createQueue("orders.incoming");
    producer = session.createProducer(queue);

    TextMessage message = session.createTextMessage(
            "{\"orderId\":\"ORD-100\",\"itemCount\":2}"
    );
    producer.send(message);
} finally {
    if (producer != null) producer.close();
    if (session != null) session.close();
    connection.close();
}
```

Đây là đoạn mã minh họa vòng đời tài nguyên; trong chương trình đầy đủ cần xử lý `JMSException` và bảo đảm việc đóng tài nguyên không che mất exception gốc. `connection.start()` không cần thiết cho thao tác gửi đơn thuần vì ví dụ không nhận message.

Producer có thể thiết lập các tùy chọn gửi như delivery mode, priority và time-to-live. Ví dụ message có thể được gửi ở chế độ persistent để provider lưu bền vững theo cấu hình, hoặc non-persistent để ưu tiên hiệu năng. Độ bền thực tế còn phụ thuộc broker, storage và cấu hình provider.

## 7. MessageConsumer: nhận message

`MessageConsumer` được tạo từ session và destination. Có hai cách nhận phổ biến:

- **Đồng bộ:** gọi `receive()`, `receive(timeout)` hoặc `receiveNoWait()` để chủ động lấy message.
- **Bất đồng bộ:** đăng ký `MessageListener`; provider gọi `onMessage` khi message đến.

Với consumer đồng bộ, connection cần được start trước khi chờ nhận message:

```java
import jakarta.jms.Connection;
import jakarta.jms.Message;
import jakarta.jms.MessageConsumer;
import jakarta.jms.Queue;
import jakarta.jms.Session;
import jakarta.jms.TextMessage;

Connection connection = connectionFactory.createConnection();
Session session = null;
MessageConsumer consumer = null;
try {
    session = connection.createSession(false, Session.AUTO_ACKNOWLEDGE);
    Queue queue = session.createQueue("orders.incoming");
    consumer = session.createConsumer(queue);

    connection.start();
    Message received = consumer.receive(3000);
    if (received instanceof TextMessage textMessage) {
        System.out.println(textMessage.getText());
    }
} finally {
    if (consumer != null) consumer.close();
    if (session != null) session.close();
    connection.close();
}
```

Nếu nhận được message mẫu ở trên, phần in ra là:

```text
{"orderId":"ORD-100","itemCount":2}
```

Nếu không có message trong ba giây, `receive(3000)` trả về `null`. Đây là ví dụ minh họa; ứng dụng thực tế cần xử lý ngoại lệ và quản lý lifecycle phù hợp. Không nên giữ thread chờ `receive()` vô thời hạn trong một request web thông thường.

### Nhận bất đồng bộ bằng MessageListener

Consumer có thể đăng ký listener:

```java
consumer.setMessageListener(message -> {
    try {
        if (message instanceof TextMessage textMessage) {
            process(textMessage.getText());
        }
    } catch (JMSException ex) {
        throw new IllegalStateException("Cannot read JMS message", ex);
    }
});
connection.start();
```

Provider gọi listener khi message được chuyển đến. Thời gian xử lý listener ảnh hưởng đến throughput và acknowledgement. Cần giữ callback ngắn gọn hoặc chuyển công việc sang service phù hợp, nhưng phải hiểu transaction/session và không dùng session đồng thời từ nhiều thread.

## 8. Headers, properties và correlation

JMS message có các trường header chuẩn như:

- `JMSMessageID`: định danh message do provider cấp.
- `JMSCorrelationID`: liên kết message với một request hoặc message khác.
- `JMSReplyTo`: destination dùng để gửi reply trong mô hình request–reply.
- `JMSType`: thông tin loại message theo hợp đồng ứng dụng; nó không đồng nghĩa với MIME `Content-Type`.
- `JMSDestination`: destination mà message được gửi đến.
- `JMSDeliveryMode`, `JMSPriority`, `JMSExpiration` và `JMSRedelivered`: metadata về giao nhận.

Ngoài header chuẩn, producer có thể thêm application properties để consumer định tuyến hoặc xử lý theo hợp đồng. Không dùng properties thay cho validation; consumer vẫn phải kiểm tra giá trị và nguồn gửi.

Ví dụ gắn correlation ID:

```java
TextMessage message = session.createTextMessage(json);
message.setJMSCorrelationID("corr-ORD-100");
message.setStringProperty("eventType", "OrderCreated");
producer.send(message);
```

Correlation ID giúp ghép request và reply hoặc theo dõi một luồng qua nhiều thành phần. Nó không thay thế message ID: một request có thể tạo ra nhiều message khác nhau nhưng dùng chung correlation ID.

## 9. Transaction và acknowledgement

JMS hỗ trợ transaction ở cấp session. Khi tạo session với `transacted=true`, producer send và consumer receive trong session có thể được commit hoặc rollback theo ranh giới transaction của session.

```java
Session session = connection.createSession(true, Session.SESSION_TRANSACTED);
try {
    // Nhận message, cập nhật dữ liệu hoặc gửi message tiếp theo.
    session.commit();
} catch (JMSException | RuntimeException ex) {
    session.rollback();
    throw ex;
}
```

Đây là đoạn mã phác họa transaction JMS; mã thực tế phải quản lý exception, session lifecycle và transaction manager phù hợp. `commit()` xác nhận các thao tác JMS trong transaction session; `rollback()` hủy các thao tác JMS chưa commit và có thể khiến message nhận được được giao lại theo provider.

Một transaction JMS cục bộ không tự động bao trùm transaction database. Nếu handler ghi database rồi commit JMS, hoặc commit database rồi ack JMS, lỗi giữa hai thao tác có thể tạo trạng thái không đồng nhất. Với yêu cầu atomic giữa nhiều resource, cần XA/JTA nếu provider và database hỗ trợ, hoặc thiết kế transactional outbox/inbox phù hợp.

Redelivery có thể xảy ra sau rollback hoặc lỗi consumer. Consumer nên idempotent và có chính sách xử lý message lỗi, retry có giới hạn và dead-letter.

## 10. Spring JMS quản lý các tài nguyên như thế nào?

Spring JMS cung cấp abstraction để ứng dụng không phải tự tạo và đóng connection, session, producer cho từng thao tác:

- `JmsTemplate`: gửi message, thực hiện receive đồng bộ và quản lý việc lấy/giải phóng tài nguyên JMS trong thao tác.
- `DefaultMessageListenerContainer`: quản lý consumer chạy nền, session, listener thread, concurrency và phục hồi kết nối theo cấu hình.
- `@JmsListener`: khai báo phương thức nhận message; Spring tạo listener endpoint và gắn với container.
- `JmsTransactionManager`: quản lý transaction JMS cục bộ cho một `ConnectionFactory`.
- `CachingConnectionFactory`: có thể cache các tài nguyên JMS để giảm chi phí tạo lặp, tùy cấu hình và cách dùng.

Trong ứng dụng Spring, thường inject một `ConnectionFactory` do provider hoặc Spring Boot cấu hình. `JmsTemplate` và listener container dùng cùng factory để giao tiếp với broker.

### Gửi bằng JmsTemplate

```java
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Service;

@Service
class OrderPublisher {
    private final JmsTemplate jmsTemplate;

    OrderPublisher(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    void publish(String json) {
        jmsTemplate.convertAndSend("orders.incoming", json);
    }
}
```

Với `String`, `SimpleMessageConverter` mặc định chuyển nội dung thành `TextMessage`. Nếu gửi DTO hoặc định dạng phức tạp, hãy cấu hình `MessageConverter` và hợp đồng serialization rõ ràng; không mặc định mọi object Java đều được chuyển thành JSON.

### Nhận bằng @JmsListener

```java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
class OrderListener {
    @JmsListener(destination = "orders.incoming")
    public void receive(String json) {
        processOrder(json);
    }
}
```

Spring tạo listener container và chuyển message sang kiểu tham số phù hợp bằng converter đã cấu hình. `@JmsListener` không tự định nghĩa broker, credential hoặc destination provisioning; ứng dụng vẫn cần `ConnectionFactory` và hạ tầng JMS hợp lệ.

### Cấu hình listener container

```java
import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Configuration
@EnableJms
class JmsConfiguration {
    @Bean
    DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory connectionFactory) {
        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setConcurrency("2-8");
        factory.setSessionTransacted(true);
        return factory;
    }
}
```

Ví dụ đặt concurrency trong khoảng 2 đến 8 consumer và dùng transacted session cho listener. Cần chọn số consumer theo năng lực broker, database pool và downstream service. Khi listener ném exception, rollback/redelivery phụ thuộc cấu hình container, transaction manager và chính sách provider.

Các ví dụ trên dùng `jakarta.jms`, phù hợp với hệ sinh thái Spring Framework 6 trở lên. Spring Framework 5 và các ứng dụng JMS cũ thường dùng package `javax.jms`; không trộn hai namespace trong cùng một ứng dụng.

## 11. Quản lý vòng đời và hiệu năng

Tạo và đóng connection/session/producer/consumer liên tục có thể gây overhead. Một số nguyên tắc vận hành:

- Dùng `JmsTemplate` cho các thao tác gửi/nhận đồng bộ để Spring quản lý tài nguyên.
- Dùng listener container cho consumer chạy lâu dài thay vì tự tạo consumer trong từng request.
- Cân nhắc connection pooling hoặc caching phù hợp provider và Spring; đo hiệu quả trước khi tăng cache size.
- Đặt concurrency theo giới hạn CPU, database connection pool và năng lực xử lý của broker.
- Đóng consumer, producer, session và connection trong mã JMS thủ công; không để rò rỉ resource.
- Theo dõi số connection/session, consumer count, queue depth, message age, throughput và redelivery.

Không chia sẻ một `Session`, `MessageProducer` hoặc `MessageConsumer` cho nhiều thread đồng thời. Nếu cần tăng mức song song, dùng nhiều session/consumer do container hoặc pool quản lý.

## 12. Lỗi thường gặp

- **Nhầm ConnectionFactory với Connection:** factory tạo connection; connection đại diện kết nối đang mở.
- **Dùng một Session từ nhiều thread:** session không được thiết kế để sử dụng đồng thời; hãy tạo session riêng theo luồng/container.
- **Quên gọi `Connection.start()` khi nhận message:** consumer có thể không nhận được message bất đồng bộ cho đến khi connection được start.
- **Không đóng tài nguyên khi dùng JMS API trực tiếp:** connection/session/producer/consumer bị rò rỉ và cạn tài nguyên.
- **Coi `createQueue()` là thao tác chắc chắn tạo queue vật lý:** đây có thể chỉ là destination object; việc provisioning phụ thuộc provider.
- **Nhầm Queue và Topic:** queue phân phối theo mô hình point-to-point; topic dùng publish–subscribe.
- **Dùng ObjectMessage với dữ liệu không tin cậy:** deserialization object có rủi ro bảo mật và phụ thuộc class/version; ưu tiên schema rõ ràng như JSON hoặc định dạng được kiểm soát.
- **Coi AUTO_ACKNOWLEDGE là transaction database:** acknowledgement JMS không tự đồng bộ với commit database.
- **Không thiết kế redelivery/idempotency:** rollback hoặc mất kết nối có thể khiến message được giao lại.
- **Cho rằng @JmsListener tự tạo toàn bộ hạ tầng:** listener cần ConnectionFactory, broker và destination phù hợp.
- **Nhầm JMSType với Content-Type:** hai metadata phục vụ mục đích khác nhau.

## 13. Quy trình chọn và triển khai tài nguyên JMS

1. Chọn provider và cấu hình `ConnectionFactory` với endpoint, credential, TLS và timeout.
2. Xác định destination là queue hay topic, cùng chính sách provisioning và quyền truy cập.
3. Chọn mô hình gửi: `JmsTemplate` hay JMS `MessageProducer` trực tiếp.
4. Chọn mô hình nhận: synchronous `receive` hay asynchronous `MessageListener`/`@JmsListener`.
5. Xác định session transacted hay acknowledgement mode phù hợp.
6. Thiết kế message format, converter, correlation ID và properties.
7. Đặt concurrency, pooling/cache và timeout theo năng lực tài nguyên.
8. Thiết kế retry, redelivery, dead-letter và idempotency.
9. Kiểm thử gửi/nhận, commit/rollback, lỗi broker, reconnect và đóng tài nguyên.

## 14. Kết luận

`ConnectionFactory` tạo `Connection`; `Connection` tạo `Session`; `Session` tạo message, destination, `MessageProducer` và `MessageConsumer`. Producer gửi message đến queue/topic, còn consumer nhận đồng bộ bằng `receive` hoặc bất đồng bộ bằng `MessageListener`. Session là nơi quản lý transaction và acknowledgement, đồng thời không nên được chia sẻ giữa nhiều thread.

Trong ứng dụng Spring, ưu tiên `JmsTemplate` cho gửi/nhận đồng bộ và listener container/`@JmsListener` cho consumer chạy nền. Nắm rõ vòng đời tài nguyên, transaction, acknowledgement, concurrency và redelivery giúp ứng dụng giao tiếp với JMS provider ổn định, tránh rò rỉ tài nguyên và xử lý message trùng an toàn.