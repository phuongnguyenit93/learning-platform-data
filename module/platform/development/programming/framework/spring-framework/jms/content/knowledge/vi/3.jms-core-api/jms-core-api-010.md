# Quản lý tài nguyên bằng API gốc so với JmsTemplate

## Mục tiêu và bối cảnh

Bài này đặt **Jakarta Messaging (JMS) API gốc** bên cạnh **Spring `JmsTemplate`**, tập trung vào một câu hỏi thực hành: khi gửi hoặc nhận message, **ai tạo, sở hữu, kết thúc và giải phóng `Connection`, `Session`, `MessageProducer`, `MessageConsumer`?** Từ đó, bạn có thể chọn cách viết phù hợp, tránh rò rỉ tài nguyên, phân biệt cleanup với commit và hiểu đúng vai trò transaction/caching trong ứng dụng Spring.

Trong Spring Framework hiện đại, API JMS dùng package `jakarta.jms`. Các dự án cũ có thể dùng `javax.jms`; hai namespace không thể hoán đổi trực tiếp mà không chọn phiên bản dependency phù hợp.

## 1. Các tài nguyên cần quản lý

Ở JMS classic API, đồ thị sử dụng phổ biến:

```text
ConnectionFactory (cấu hình do ứng dụng/container quản lý)
        |
        +-- createConnection() --> Connection (kênh tới broker)
                                       |
                                       +-- createSession(...) --> Session
                                                                    |
                                                                    +-- MessageProducer
                                                                    +-- MessageConsumer
                                                                    +-- Queue / Topic*
                                                                    +-- TextMessage / BytesMessage*
```

Dấu `*` chỉ đối tượng tạo ra để biểu diễn destination hoặc nội dung message; chúng không có cùng vòng đời tài nguyên như connection, session, producer hay consumer.

| Đối tượng | Vai trò | Điểm cần nhớ khi quản lý |
| --- | --- | --- |
| `ConnectionFactory` | Cấu hình và tạo connection tới JMS provider | Thường được cấu hình/inject một lần. Không tạo factory mới cho mọi message. |
| `Connection` | Đại diện kết nối tới provider, có thể chứa nhiều session | Đóng khi hết phạm vi sử dụng; `close()` cũng giải phóng các session và producer/consumer liên quan. |
| `Session` | Ngữ cảnh đơn luồng để tạo message, producer/consumer và điều khiển acknowledge/transaction | Không tự ý dùng đồng thời từ nhiều thread; có thể đóng riêng hoặc được đóng qua connection. |
| `MessageProducer` | Gửi message đến destination | Đóng sau khi dùng nếu tự quản lý; Jakarta Messaging 3.1 cho phép `try-with-resources`. |
| `MessageConsumer` | Nhận message, đồng bộ hoặc qua listener | Đóng khi không còn nhận; bản thân `receive()` có thể chờ lâu. |
| `JMSContext` | Simplified JMS API: gom connection + session | `AutoCloseable`; `try-with-resources` phù hợp khi do ứng dụng tự tạo. |
| `JmsTemplate` | Lớp Spring thực thi thao tác JMS và quản lý tài nguyên nền | Một bean dùng chung sau khi cấu hình; gọi `send`/`receive`/`execute` thay vì tự tạo/đóng session. |

**Quan trọng:** `ConnectionFactory` là điểm xuất phát chung, nhưng **API gốc và `JmsTemplate` có quy tắc sở hữu khác nhau**. Trong callback Spring, session được framework cho mượn; trong mã tự gọi `createConnection()`, ứng dụng sở hữu các tài nguyên vừa tạo. Không đóng thủ công một session do `JmsTemplate` truyền vào callback.

### Cleanup không phải commit

- `close()` giải phóng tài nguyên; nó **không** tự biến mọi xử lý nghiệp vụ thành giao dịch thành công.
- Với **session transacted**, ứng dụng phải `commit()` khi muốn xác nhận transaction JMS cục bộ. Khi một session transacted bị đóng với transaction đang mở, transaction đó bị rollback.
- Với **client-acknowledge**, đóng connection/session **không** có nghĩa các message chưa acknowledge được xác nhận.
- Nếu phiên nhận lỗi trước commit/acknowledge, broker có thể phát lại message theo chính sách. Việc giải phóng tài nguyên đúng không đồng nghĩa “exactly once” ở tầng nghiệp vụ.

## 2. API JMS classic: tự tạo và tự đóng tài nguyên

Một lần gửi message bằng API gốc có nhiều bước: tạo connection, tạo session, xác định Queue, tạo producer, tạo message, gửi, rồi giải phóng theo thứ tự ngược lại.

Ví dụ Java 17+ sau đây là **phương thức có thể biên dịch trong ứng dụng đã có Jakarta JMS dependency**, chưa phải chương trình độc lập vì `ConnectionFactory` phải do provider cấp.

```java
import jakarta.jms.Connection;
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSException;
import jakarta.jms.MessageProducer;
import jakarta.jms.Queue;
import jakarta.jms.Session;

public final class ClassicJmsSender {

    public static void send(ConnectionFactory factory,
                            String queueName,
                            String body) throws JMSException {
        try (Connection connection = factory.createConnection();
             Session session =
                     connection.createSession(Session.AUTO_ACKNOWLEDGE);
             MessageProducer producer =
                     session.createProducer(session.createQueue(queueName))) {

            producer.send(session.createTextMessage(body));
        }
    }
}
```

`try-with-resources` sẽ đóng `producer`, sau đó `session`, cuối cùng `connection`, **kể cả khi `send()` ném exception**. `Connection`, `Session`, `MessageProducer` và `MessageConsumer` đều là `AutoCloseable` trong Jakarta Messaging 3.1. Không cần thêm `finally` thủ công để đóng cùng những đối tượng đó. Nếu exception phát sinh cả trong body và trong quá trình đóng, Java giữ exception chính và gắn lỗi đóng thành `suppressed exception`.

Khi tự viết `finally` trong dự án cũ, lỗi phổ biến là chỉ đóng khi thao tác thành công, quên đóng producer hoặc để lỗi `close()` che khuất lỗi gửi. `try-with-resources` khắc phục phần lớn vấn đề quản lý scope đó.

### Vì sao không gọi connection.start() khi chỉ gửi?

`Connection.start()` bắt đầu việc **delivery đến consumer**. Gửi message bằng producer không yêu cầu gọi `start()` trước. Với **nhận đồng bộ** bằng classic API, bạn cần `connection.start()` để delivery diễn ra.

```java
import jakarta.jms.Connection;
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.MessageConsumer;
import jakarta.jms.Session;
import jakarta.jms.TextMessage;

public final class ClassicJmsReceiver {

    public static String receive(ConnectionFactory factory,
                                 String queueName,
                                 long timeoutMillis) throws JMSException {
        try (Connection connection = factory.createConnection();
             Session session =
                     connection.createSession(Session.AUTO_ACKNOWLEDGE);
             MessageConsumer consumer =
                     session.createConsumer(session.createQueue(queueName))) {

            connection.start();
            Message message = consumer.receive(timeoutMillis);

            if (message == null) {
                return null; // Hết thời gian chờ, không có message.
            }
            if (!(message instanceof TextMessage text)) {
                throw new IllegalArgumentException(
                        "Expected TextMessage, got " + message.getClass());
            }
            return text.getText();
        }
    }
}
```

`receive(2000)` chờ tối đa khoảng 2 giây rồi trả về `null` nếu không có message; `receive(0)` có thể chờ vô hạn. Trong một Queue có consumer khác, message có thể được consumer khác nhận trước. Khi dùng `AUTO_ACKNOWLEDGE`, đừng giả định gọi thành công một hàm database ở phía sau mới quyết định acknowledgement của lần `receive` này; cần thiết kế transaction/acknowledgement riêng nếu yêu cầu xử lý tin cậy.

### Quản lý manual có chi phí gì?

Một hàm đơn giản đã phải khai báo `JMSException`, thao tác với `Session`, tự quyết định `start`, `close`, timeout và transaction. Điều này hữu ích khi cần quyền điều khiển mức thấp, nhưng dễ lặp code và quên một bước ở nhiều điểm gửi/nhận.

## 3. API gốc dạng simplified: JMSContext giảm boilerplate

Jakarta Messaging còn cung cấp **simplified API**, không phải Spring: `JMSContext` kết hợp vai trò connection và session; `JMSProducer` cung cấp thao tác gửi ngắn gọn.

```java
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSContext;
import jakarta.jms.Queue;

public final class SimplifiedJmsSender {

    public static void send(ConnectionFactory factory,
                            String queueName,
                            String body) {
        try (JMSContext context =
                     factory.createContext(JMSContext.AUTO_ACKNOWLEDGE)) {
            Queue queue = context.createQueue(queueName);
            context.createProducer().send(queue, body);
        }
    }
}
```

Những khác biệt cần nhớ:

- `JMSContext` do ứng dụng **tự gọi `createContext()`** vẫn phải được đóng; `try-with-resources` làm điều đó.
- Simplified API chủ yếu dùng `JMSRuntimeException` (unchecked), thay vì yêu cầu mọi caller khai báo checked `JMSException` như classic API.
- `JMSContext` đại diện một session nên **không an toàn để chia sẻ và gọi đồng thời giữa nhiều thread**. Không lưu một `JMSContext` tự tạo làm singleton cho nhiều request.
- Khi tạo `JMSConsumer` từ `JMSContext`, delivery mặc định có thể tự bắt đầu (`autoStart`); khác với classic API cần `Connection.start()` cho nhận.
- Khi `JMSContext` được container Jakarta EE quản lý/inject, lifecycle có quy tắc container riêng. Đừng áp dụng máy móc `close()` bằng tay cho đối tượng do container sở hữu.

**Phân biệt:** `JMSContext` giảm số lượng API phải gọi nhưng **vẫn là JMS API gốc**; nó không tự cung cấp Spring transaction synchronization, `MessageConverter` hoặc exception translation của `JmsTemplate`.

## 4. Spring JmsTemplate: giao thao tác cho template, giao cleanup cho framework

Spring Framework dùng `org.springframework.jms.core.JmsTemplate` cho gửi và nhận message **đồng bộ**. Cấu hình template với `ConnectionFactory`; phần lớn business code không cần nhìn thấy `Connection` hay `Session`.

```java
import org.springframework.jms.core.JmsTemplate;

public final class TemplateSender {
    private final JmsTemplate jmsTemplate;

    public TemplateSender(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    public void send(String orderId) {
        jmsTemplate.convertAndSend("orders.queue", orderId);
    }
}
```

Một lời gọi `convertAndSend` về mặt khái niệm đi theo chuỗi:

```text
Business service
    -> JmsTemplate.convertAndSend(...)
        -> tìm Session tham gia transaction hiện tại (nếu có)
           hoặc lấy/tạo Connection + Session thích hợp
        -> chuyển String thành JMS TextMessage
        -> lấy/tạo producer và gửi
        -> đóng hoặc trả tài nguyên theo chính sách Spring/ConnectionFactory
    <- kết quả / unchecked Spring JmsException
```

**Template quản lý lifecycle logic, không đồng nghĩa mỗi lần đều tạo một kết nối TCP mới.** Nếu `ConnectionFactory` phía sau được pool hoặc cache, việc gọi `close` trên đối tượng logic có thể là trả session vào cache. Không tự dựa vào số lần tạo connection vật lý để suy ra số lần gọi `send`.

`JmsTemplate` còn xử lý:

1. **Message conversion:** `convertAndSend` và `receiveAndConvert` dùng `MessageConverter`; mặc định `String` có thể được chuyển thành `TextMessage`.
2. **Destination resolution:** có thể dùng chuỗi tên Queue/Topic, tùy `DestinationResolver`; không phải lúc nào cũng bắt buộc tự gọi `session.createQueue`.
3. **Exception translation:** chuyển các lỗi checked `jakarta.jms.JMSException` từ operation sang họ unchecked `org.springframework.jms.JmsException`; ứng dụng có thể xử lý ở biên service thay vì khai báo `throws JMSException` liên tục.
4. **Transaction integration:** khi có `JmsTransactionManager` và cùng `ConnectionFactory` đúng, template có thể dùng session đang được ràng buộc với transaction.
5. **Callback tùy biến:** khi cần thao tác thấp hơn `convertAndSend`, template đưa `Session` hoặc producer vào callback mà vẫn giữ quyền sở hữu tài nguyên bao ngoài.

`JmsTemplate` **thread-safe sau khi cấu hình xong**. Hãy inject bean dùng chung, cấu hình `receiveTimeout`, converter và Quality-of-Service trước khi các luồng sử dụng; tránh thay đổi config của bean liên tục giữa các request.

### Với MessageCreator và callback, ai đóng gì?

Khi muốn tạo `TextMessage` và thuộc tính JMS cụ thể:

```java
jmsTemplate.send("orders.queue", session -> {
    var message = session.createTextMessage("order-42");
    message.setStringProperty("source", "checkout");
    return message;
});
```

`session` ở đây do `JmsTemplate` cung cấp. **Không** gọi `session.close()` trong callback; template còn cần session để gửi message và cleanup đúng sau callback.

Với thao tác nâng cao hơn, `SessionCallback` cho quyền truy cập session:

```java
import jakarta.jms.MessageProducer;
import org.springframework.jms.core.SessionCallback;

jmsTemplate.execute((SessionCallback<Void>) session -> {
    try (MessageProducer producer =
                 session.createProducer(session.createQueue("audit.queue"))) {
        producer.send(session.createTextMessage("event-1"));
        producer.send(session.createTextMessage("event-2"));
    }
    return null;
});
```

Trong ví dụ này, **producer do callback tự tạo** nên callback chủ động đóng bằng `try-with-resources`. **Session do Spring truyền vào** nên callback không đóng. Với `ProducerCallback`, Spring có thể cung cấp cặp session/producer do template quản lý, tránh tạo thêm producer thủ công.

Hai lần `send` trong cùng callback dùng cùng một session, nhưng **không được tự suy ra atomicity**: muốn cả hai lần gửi cùng commit hoặc cùng rollback, phải bật session transacted hoặc dùng transaction manager đúng cách.

### Nhận đồng bộ bằng JmsTemplate

```java
// Cấu hình khi khởi tạo bean, trước khi bean được dùng đồng thời:
jmsTemplate.setReceiveTimeout(2_000L);

// Bên trong service:
Object payload = jmsTemplate.receiveAndConvert("orders.queue");
if (payload == null) {
    // Không nhận được message trong thời gian chờ.
}
```

`receiveAndConvert` tiện cho các request/reply ngắn hoặc polling có giới hạn. Nếu cần lắng nghe liên tục, dùng `@JmsListener` và Spring listener container; không tự viết vòng `while(true)` tạo vô hạn `JmsTemplate.receive()` trong request thread. Template không tự biến synchronous receive thành asynchronous listener.

## 5. Ví dụ Spring Boot hoàn chỉnh: so sánh ba cách gửi

Ví dụ sau dùng **Java 17+**, **Spring Boot 3.5.8**, API `jakarta.jms` và **Apache ActiveMQ Artemis broker riêng**. Nó gửi ba message vào cùng Queue qua (1) classic JMS, (2) simplified `JMSContext`, (3) Spring `JmsTemplate`. Cả ba cùng dùng `ConnectionFactory` do Spring Boot cung cấp.

**Điều kiện chạy:** có broker Artemis đang lắng nghe `tcp://localhost:61616`, thông tin đăng nhập hợp lệ và Queue `demo.resources.queue` được tạo sẵn hoặc broker cho phép auto-create. Không có broker thì ví dụ ném lỗi kết nối; Maven không tự khởi động broker bên ngoài.

**`pom.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.8</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>jms-resource-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-artemis</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

**`src/main/resources/application.properties`**

```properties
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
# Bật nếu broker có yêu cầu xác thực:
# spring.artemis.user=my-user
# spring.artemis.password=my-password
```

**`src/main/java/example/jms/ResourceManagementDemo.java`**

```java
package example.jms;

import jakarta.jms.Connection;
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSContext;
import jakarta.jms.JMSException;
import jakarta.jms.MessageProducer;
import jakarta.jms.Session;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.core.JmsTemplate;

@SpringBootApplication
public class ResourceManagementDemo {

    private static final String QUEUE = "demo.resources.queue";

    public static void main(String[] args) {
        SpringApplication.run(ResourceManagementDemo.class, args);
    }

    @Bean
    ApplicationRunner runExample(ConnectionFactory factory,
                                 JmsTemplate template) {
        return args -> {
            classicSend(factory, QUEUE, "from-classic");
            simplifiedSend(factory, QUEUE, "from-context");
            template.convertAndSend(QUEUE, "from-template");
            System.out.println("sent=3");
        };
    }

    static void classicSend(ConnectionFactory factory,
                            String destination,
                            String body) throws JMSException {
        try (Connection connection = factory.createConnection();
             Session session =
                     connection.createSession(Session.AUTO_ACKNOWLEDGE);
             MessageProducer producer =
                     session.createProducer(session.createQueue(destination))) {

            producer.send(session.createTextMessage(body));
        }
    }

    static void simplifiedSend(ConnectionFactory factory,
                               String destination,
                               String body) {
        try (JMSContext context =
                     factory.createContext(JMSContext.AUTO_ACKNOWLEDGE)) {

            context.createProducer().send(context.createQueue(destination), body);
        }
    }
}
```

**Chạy** tại thư mục chứa `pom.xml` khi broker đã sẵn sàng:

```bash
mvn spring-boot:run
```

Dòng stdout do chương trình chủ động in khi **cả ba lệnh gửi đều hoàn tất mà không ném lỗi**:

```text
sent=3
```

Spring Boot còn in log khởi động tùy môi trường. Dòng `sent=3` là số thao tác gửi thành công theo kết quả lời gọi trong ví dụ; **không chứng minh broker đã nhận bền vững theo chính sách mong muốn hay consumer đã xử lý đúng một lần**. Mỗi lần chạy lại demo sẽ gửi thêm ba message. Nếu có consumer khác đọc Queue, message có thể được tiêu thụ ngay và không còn trong pending Queue.

Quan sát mã:

- `classicSend` cho thấy app phải mở/đóng `Connection`, `Session` và `MessageProducer`.
- `simplifiedSend` chỉ quản lý một `JMSContext` và dùng unchecked API.
- `template.convertAndSend` chỉ nêu destination và payload; Spring thực hiện phần vòng đời JMS và message conversion.
- **Không có `Connection.start()`** vì ví dụ chỉ gửi; nếu thêm phần nhận bằng classic `MessageConsumer`, cần gọi `start()` trước `receive()`.

## 6. Transaction: cần hiểu ranh giới trước khi chọn API

### 6.1 Classic JMS với local transaction

Khi nhiều message phải cùng thuộc một **giao dịch JMS** tại provider, có thể dùng session transacted và điều khiển `commit/rollback` bằng tay:

```java
static void sendTwoAtomicallyWithinJms(
        ConnectionFactory factory, String queueName) throws JMSException {

    try (Connection connection = factory.createConnection();
         Session session = connection.createSession(Session.SESSION_TRANSACTED);
         MessageProducer producer =
                 session.createProducer(session.createQueue(queueName))) {

        try {
            producer.send(session.createTextMessage("first"));
            producer.send(session.createTextMessage("second"));
            session.commit(); // Cùng một local JMS transaction.
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
```

Đây là **phương thức minh họa thêm**: đặt vào class có đủ các import ở ví dụ phía trên để biên dịch. Lựa chọn `SESSION_TRANSACTED` có ý nghĩa giao dịch; `AUTO_ACKNOWLEDGE` không thay thế nó. Đóng session transacted khi còn transaction chưa commit sẽ rollback theo đặc tả. Với trường hợp broker bị ngắt đúng lúc commit, kết quả có thể mơ hồ từ góc nhìn client; hệ thống vẫn cần thiết kế chống phát trùng.

Với simplified API, cùng ý tưởng dùng `factory.createContext(JMSContext.SESSION_TRANSACTED)` rồi gọi `context.commit()` hoặc `context.rollback()`; các lỗi chủ yếu là unchecked `JMSRuntimeException`.

### 6.2 JmsTemplate không tự gom mọi lời gọi vào một transaction

Nếu cấu hình `jmsTemplate.setSessionTransacted(true)` nhưng **không** có transaction Spring bao quanh, từng lời gọi template thường có session/transaction riêng. Hai lần gọi `convertAndSend` liên tiếp không mặc nhiên tạo một đơn vị nguyên tử chung.

Nếu cần nhiều lời gọi template cùng dùng một transaction JMS, hãy cấu hình `JmsTransactionManager` cho **cùng ConnectionFactory** và tạo biên transaction trong Spring:

```java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.connection.JmsTransactionManager;

@Configuration
class JmsTxConfiguration {
    @Bean
    JmsTransactionManager jmsTransactionManager(ConnectionFactory factory) {
        return new JmsTransactionManager(factory);
    }
}
```

```java
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class TwoMessagePublisher {
    private final JmsTemplate template;

    TwoMessagePublisher(JmsTemplate template) {
        this.template = template;
    }

    @Transactional(transactionManager = "jmsTransactionManager")
    public void publish() {
        template.convertAndSend("orders.queue", "order-created");
        template.convertAndSend("audit.queue", "audit-created");
    }
}
```

**Hai đoạn này là cấu hình/thành phần để ghép vào ứng dụng Spring đã có**, không phải hai file Java có `main()` độc lập. Phương thức `publish()` phải được gọi **qua Spring proxy** (thường là từ bean khác) thì advice `@Transactional` mới chạy theo mô hình proxy thông thường; self-invocation nội bộ không tạo transaction mới. Việc hai Queue cùng commit JMS phụ thuộc broker và hỗ trợ transaction cho các destination liên quan.

Cảnh báo phạm vi: `JmsTransactionManager` quản lý **JMS resource**; nó không tự biến cập nhật SQL bằng `DataSourceTransactionManager` thành một transaction nguyên tử chung. Nếu message gửi thành công nhưng database rollback, hoặc ngược lại, có thể phát sinh dữ liệu không nhất quán. Những lựa chọn như **transactional outbox**, idempotent consumer, hoặc XA/JTA cần được cân nhắc theo yêu cầu chứ không suy từ việc có `@Transactional`.

### 6.3 Không tự tạo Connection/Session thô bên trong transaction Spring rồi kỳ vọng tự tham gia

Khi trong một phương thức có `@Transactional(transactionManager = "jmsTransactionManager")`, `JmsTemplate` được thiết kế để tìm session ràng buộc với transaction hiện tại. Trái lại, gọi thẳng `connectionFactory.createConnection()` / `createSession()` trên một factory thông thường thường tạo resource độc lập. Đừng mặc định lệnh JMS thô đó tự đi theo transaction đang có.

Nếu bắt buộc dùng classic JMS bên trong transaction do Spring quản lý, cần hiểu `ConnectionFactoryUtils` và `TransactionAwareConnectionFactoryProxy`, hoặc thiết kế API qua callback template; không tự ý đổi factory hoặc đóng một session đã ràng buộc với transaction. Khuyến nghị trong phần lớn service Spring: dùng `JmsTemplate` nhất quán ở tầng publisher để dễ dự đoán transaction ownership.

## 7. Caching, pooling và lifetime thực tế

Một hiểu lầm phổ biến: nhìn thấy `JmsTemplate` không có `close()` rồi kết luận ứng dụng giữ kết nối mãi mãi, hoặc ngược lại tin mỗi `send` đều mở/đóng một socket vật lý. Cả hai đều không được bảo đảm.

`JmsTemplate` phụ thuộc vào `ConnectionFactory`:

- Với factory tạo kết nối mới mỗi lần, template có thể mở và đóng connection cho từng thao tác.
- Với `CachingConnectionFactory` hoặc pool phù hợp, một số đối tượng trả về là wrapper; `close()` logic có thể **trả session/connection về cache** thay vì đóng vật lý ngay.
- Khi đang có transaction, Spring có thể dùng lại session đã gắn với thread/transaction cho nhiều thao tác.
- Mức cache/pool tối ưu phụ thuộc broker, số request đồng thời, producer/consumer, transaction, prefetch và giới hạn connection/session của provider.

Việc cache producer hoặc consumer phụ thuộc cấu hình và JMS provider. Đừng tự giữ một `Session` của lần gửi đầu tiên trong field của singleton Spring service để “tối ưu”, vì session có ràng buộc thread/lifecycle, rất dễ lỗi khi đồng thời, timeout hoặc reconnect.

**Ví dụ chọn vòng đời:** Một HTTP service nhận hàng trăm request/giây nên inject **một `JmsTemplate` đã cấu hình** và dùng factory có caching/pooling phù hợp. Điều đó khác với giữ **một `JMSContext` mutable** cho mọi request: JMSContext bao cả session không hỗ trợ concurrent use tùy ý.

## 8. Xử lý lỗi và cleanup đúng cách

| Tình huống | Classic API | Simplified JMS API | JmsTemplate |
| --- | --- | --- | --- |
| Lỗi tạo connection | Thường `JMSException` (checked) | Thường `JMSRuntimeException` (unchecked) | Họ Spring `JmsException` (unchecked) |
| Gửi message | Tự tạo `Message` và producer, tự xử lý lỗi | `JMSProducer.send` ngắn gọn | `send`/`convertAndSend`; template điều phối |
| Cleanup thành công | `try-with-resources` hoặc `finally` | `JMSContext` trong `try-with-resources` | Template đảm nhiệm tài nguyên nó sở hữu |
| Cleanup sau exception | Tự bảo đảm ở mọi nhánh | `try-with-resources` tự đóng | Template cleanup và ném exception đã dịch |
| Session/producer tùy chỉnh | Trực tiếp điều khiển | Qua `JMSContext` | `MessageCreator`, `SessionCallback`, `ProducerCallback` |
| Transaction nhiều thao tác | `SESSION_TRANSACTED` + `commit/rollback` | `JMSContext.SESSION_TRANSACTED` + `commit/rollback` | Dùng đúng `JmsTransactionManager`/biên `@Transactional` khi cần |
| Receiver chạy lâu | Tự quản lý consumer/thread/lifecycle | Tự quản lý context/consumer | Dùng `@JmsListener` + listener container cho async |

Một số rủi ro cần xử lý **dù dùng API nào**:

1. **Kết nối lỗi giữa chừng:** đảm bảo lỗi được log đủ context (destination, correlation/business ID) và có chính sách retry phù hợp. Cleanup đúng không thay thế reconnect strategy.
2. **Kết quả gửi không chắc chắn khi mất kết nối:** có thể không biết broker đã nhận message hay chưa. Retry mù có thể tạo hai message nghiệp vụ; sử dụng ID ổn định và idempotency downstream khi cần.
3. **Nhận rồi xử lý DB thất bại:** acknowledge/transaction của JMS phải được thiết kế có chủ đích. `receiveAndConvert` không tự giữ message trong khi một service khác xử lý bất đồng bộ.
4. **Nuốt exception:** trong listener transacted, bắt lỗi rồi trả về bình thường có thể khiến transaction JMS được commit, ngăn redelivery mong muốn.
5. **Đóng nhầm resource:** callback không được `close()` session do Spring cung cấp; mã manual không được bỏ mặc session/producer do mình tạo.
6. **Rò rỉ khi receiver chạy dài:** không mở consumer mới trong từng vòng lặp mà không đóng; ưu tiên listener container cho workload nhận liên tục.
7. **Hết connection/session:** kiểm tra pool size, active sessions, idle timeouts, broker logs và lượng request đồng thời thay vì chỉ tăng số connection.

### Mẫu lỗi và cách sửa

Mẫu dễ rò rỉ tài nguyên:

```java
Connection c = factory.createConnection();
Session s = c.createSession(Session.AUTO_ACKNOWLEDGE);
MessageProducer p = s.createProducer(s.createQueue("orders.queue"));
p.send(s.createTextMessage("order-42"));
// Nếu send ném lỗi, không còn bước đảm bảo đóng p/s/c.
```

Mẫu sửa bằng classic API:

```java
try (Connection c = factory.createConnection();
     Session s = c.createSession(Session.AUTO_ACKNOWLEDGE);
     MessageProducer p = s.createProducer(s.createQueue("orders.queue"))) {
    p.send(s.createTextMessage("order-42"));
}
```

Trong Spring, với thao tác tương đương:

```java
jmsTemplate.convertAndSend("orders.queue", "order-42");
```

Ba đoạn là **mã minh họa tại một điểm gọi đã có `factory`/`jmsTemplate`**, không phải file Java độc lập. Phần không có trong ví dụ ngắn của Spring (tạo/đóng session) chính là công việc template đảm nhiệm.

## 9. Chọn API nào cho từng tình huống?

| Nhu cầu | Gợi ý | Lý do |
| --- | --- | --- |
| Spring service gửi String, byte array, object có converter | `JmsTemplate.convertAndSend` | Mã nghiệp vụ gọn, xử lý lifecycle và chuyển đổi message nhất quán. |
| Spring service cần header, property JMS | `JmsTemplate.send(MessageCreator)` hoặc `convertAndSend(..., MessagePostProcessor)` | Vẫn dùng cleanup của Spring, tùy chỉnh message đúng điểm cần thiết. |
| Spring service cần điều khiển `Session` / producer trong thao tác đặc biệt | `JmsTemplate.execute` với callback | Truy cập JMS API mà không mất cơ chế transaction/lifecycle do Spring quản lý. |
| Java SE không dùng Spring | `JMSContext` tự tạo trong `try-with-resources` | API chuẩn gọn và tự đóng tài nguyên đúng scope. |
| Legacy/integration yêu cầu API mức thấp, giao thức/provider đặc biệt | Classic `Connection/Session/Producer/Consumer` | Kiểm soát đầy đủ, đổi lại phải tự chịu trách nhiệm cleanup, threading và transaction. |
| Nhận bất đồng bộ lâu dài trong Spring | `@JmsListener` + listener container | Quản lý consumer, lifecycle, concurrency, transaction cho listener. |
| Nhiều lần gửi JMS cần cùng commit/rollback trong Spring | `JmsTransactionManager` + `@Transactional` + `JmsTemplate` | Đồng bộ session và biên transaction một cách rõ ràng. |

Không chọn classic chỉ để “nhanh hơn”: các API đều gọi xuống cùng JMS provider; tốc độ thực tế chủ yếu phụ thuộc broker, cấu hình connection/session, payload, batching, persistent delivery, network và workload. Đo bằng thử tải trước khi tối ưu.

## 10. Checklist và bài tập tự kiểm tra

**Trước khi đưa vào production:**

- Xác định rõ ai tạo và ai đóng `Connection`/`Session`/`JMSContext`; tách tài nguyên ứng dụng tạo và framework quản lý.
- Dùng `try-with-resources` ở các đoạn sở hữu tài nguyên JMS gốc; không chia sẻ `Session` hoặc `JMSContext` một cách không an toàn giữa nhiều thread.
- Dùng một `JmsTemplate` được cấu hình trước khi chạy đồng thời; thiết lập `receiveTimeout` hữu hạn cho các lần nhận đồng bộ cần giới hạn thời gian.
- Xác định rõ kiểu transaction, điều kiện commit và cách xử lý trường hợp lỗi giữa gửi JMS với ghi database.
- Thiết lập metrics/log cho kết nối, producer/consumer, lỗi retry, transaction rollback, Queue backlog và thời gian xử lý; không ghi mật khẩu broker vào log.
- Kiểm thử khi broker tắt rồi bật lại, khi consumer rollback, khi database commit nhưng JMS commit thất bại, và khi hai thread gọi cùng service.

**Tự hỏi:**

1. Vì sao gọi `Connection.start()` trong đoạn classic receiver nhưng không có trong classic sender?
2. Trong `JmsTemplate.execute(SessionCallback)`, ai đóng session? Nếu callback tự tạo producer, ai đóng producer?
3. Vì sao hai lệnh `convertAndSend` gọi nối tiếp có thể không cùng một JMS transaction?
4. Vì sao trả session vào `CachingConnectionFactory` không đồng nghĩa đóng socket vật lý?
5. Vì sao `try-with-resources` và `@Transactional` giải quyết **hai** vấn đề khác nhau?

**Đáp án ngắn:** (1) `start()` kích hoạt delivery đến consumer; gửi không cần. (2) Template sở hữu session; callback sở hữu producer do chính nó tạo. (3) Cần biên transaction chung và đúng manager; session transacted trên từng operation chưa đủ. (4) Caching giữ tài nguyên để tái sử dụng. (5) `try-with-resources` bảo đảm đóng scope tài nguyên; transaction xác định commit/rollback thay đổi JMS.

## Kết luận

Sự khác biệt then chốt là **quyền sở hữu và vòng đời**. Classic JMS cho phép kiểm soát trực tiếp nhưng ứng dụng phải đóng tài nguyên và xử lý checked exceptions; `JMSContext` rút gọn API gốc nhưng ứng dụng tự tạo vẫn phải đóng; `JmsTemplate` giao lifecycle, conversion và exception translation cho Spring, đồng thời phối hợp với transaction manager khi cấu hình đúng. Giải phóng tài nguyên an toàn là điều kiện vận hành cơ bản; transaction, redelivery và idempotency cần được thiết kế riêng để đạt độ tin cậy nghiệp vụ.

## Tài liệu tham khảo

- Jakarta Messaging 3.1 — specification, tài nguyên và transaction: https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
- Jakarta Messaging 3.1 — `MessageProducer` API: https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/messageproducer
- Jakarta Messaging 3.1 — `JMSContext` API: https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/jmscontext
- Spring Framework — JMS integration: https://docs.spring.io/spring-framework/reference/integration/jms.html
- Spring Framework — Sending a message và callback: https://docs.spring.io/spring-framework/reference/integration/jms/sending.html
- Spring Framework — Receiving a message: https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html
- Spring Framework — Using Spring JMS: https://docs.spring.io/spring-framework/reference/integration/jms/using.html
- Spring Framework — `JmsTransactionManager`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/connection/JmsTransactionManager.html
- Spring Boot — Artemis và JMS: https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html