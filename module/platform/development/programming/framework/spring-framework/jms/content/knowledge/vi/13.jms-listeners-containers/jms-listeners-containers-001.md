# Nhận bất đồng bộ bằng MessageListener trong Spring Framework JMS

## 1. Mục tiêu bài học

Trong JMS, có hai cách cơ bản để consumer lấy thông điệp: **nhận đồng bộ** bằng `MessageConsumer.receive(...)` (thread gọi đợi một message) và **nhận bất đồng bộ** bằng cách đăng ký một `MessageListener`. Với cách thứ hai, client đăng ký phương thức xử lý trước; khi broker có message phù hợp, JMS provider hoặc Spring listener container chủ động **gọi `onMessage(Message)`** ở luồng xử lý nhận, thay vì business code phải tự lặp `receive`.

Chủ đề này thuộc **Listener và container** của Spring Framework JMS. Ta sẽ nối kiến thức từ chuẩn Jakarta Messaging lên cách Spring tổ chức consumer, lifecycle và xử lý lỗi.

Sau bài, bạn có thể:

1. Viết class hoặc lambda implement `jakarta.jms.MessageListener` và đăng ký qua `MessageConsumer.setMessageListener(...)`.
2. Hiểu vai trò của `Connection.start()`, `Session`, callback thread, resource lifecycle và lý do không trộn `receive()` với listener trên cùng session.
3. Cấu hình một **Spring `DefaultMessageListenerContainer`** nhận message bằng `MessageListener` thuần, không cần code tự mở/đóng session.
4. Phân biệt `SimpleMessageListenerContainer`, `DefaultMessageListenerContainer`, `@JmsListener`, `SessionAwareMessageListener`, `CompletionListener` và `ExceptionListener`.
5. Thiết kế acknowledge, local transaction, rollback, retry/DLQ, concurrency và idempotency đúng thực tế.
6. Chạy ví dụ Java 17+ / Spring Boot 3.5.x / Apache ActiveMQ Artemis và hiểu output, điều kiện môi trường cùng các tình huống lỗi.

**Giới hạn:** bài nói về việc **nhận bất đồng bộ**, không phải asynchronous send. Nơi JMS dùng `jakarta.jms.*` là Jakarta Messaging 3.x / Spring Framework 6.x; thư viện JMS cũ dùng `javax.jms.*` không tự tương thích với namespace mới.

## 2. MessageListener là gì?

`jakarta.jms.MessageListener` là functional interface của Jakarta Messaging:

```java
package jakarta.jms;

@FunctionalInterface
public interface MessageListener {
    void onMessage(Message message);
}
```

Đây là **chữ ký rút gọn để giải thích**, không phải interface phải tự tạo trong project. Method `onMessage`:

- Được JMS provider gọi khi có một `Message` được phân phối đến consumer đã đăng ký listener.
- Trả về `void`; ứng dụng xử lý body, headers, properties và tác vụ nghiệp vụ bên trong callback.
- Không khai báo `throws JMSException`, nên lỗi khi đọc `TextMessage.getText()` phải được catch và chuyển sang unchecked exception hoặc xử lý theo policy.
- Được chạy theo cơ chế dispatch của provider/container, **không phải thread đang gọi `setMessageListener`**.
- Có thể nhận `TextMessage`, `BytesMessage`, `MapMessage`, `ObjectMessage` hoặc kiểu message khác. Không cast mọi message thành `TextMessage` mà không kiểm tra.

Ví dụ callback tối giản:

```java
MessageListener listener = message -> {
    if (!(message instanceof TextMessage text)) {
        throw new IllegalArgumentException("Expected TextMessage");
    }
    try {
        System.out.println("body=" + text.getText());
    } catch (JMSException e) {
        throw new IllegalStateException("Cannot read JMS text", e);
    }
};
```

Đoạn này là **snippet**; cần import `jakarta.jms.MessageListener`, `TextMessage` và `JMSException`. Nó chỉ tạo Java object, **chưa đăng ký với JMS consumer**; không có message nào tự đến cho đến khi bạn cấu hình consumer và bắt đầu delivery.

### 2.1. Dòng thời gian nhận bất đồng bộ

```text
Ứng dụng                         JMS client / broker
   |
   | createConnection()
   | createSession()
   | createConsumer(queue)
   | consumer.setMessageListener(listener)
   | connection.start()
   |----------------------------------------> bắt đầu nhận message
   |
   | làm việc khác / đợi signal
   |                                      broker có message
   |                                           |
   |                              provider chọn consumer phù hợp
   |                                           |
   |                           gọi listener.onMessage(message)
   |                                           |
   |                           chạy xử lý + ack/tx theo cấu hình
   |
   | khi shutdown: stop/close tài nguyên ở thread điều phối
```

**Bất đồng bộ không đồng nghĩa xử lý song song vô hạn.** Jakarta Messaging bảo đảm các callback thuộc **một Session được gọi tuần tự**. Muốn nhiều message xử lý đồng thời phải có nhiều session/consumer phù hợp hoặc mô hình container scale-out.

### 2.2. MessageListener khác các loại listener nào?

| Cơ chế | Phía giao tiếp | Callback / API | Trách nhiệm |
| --- | --- | --- | --- |
| `MessageListener` | **Nhận** JMS message | `onMessage(Message)` | Xử lý thông điệp đến. |
| `CompletionListener` | **Gửi** JMS bất đồng bộ | `onCompletion` / `onException` | Báo trạng thái thao tác gửi. |
| `ExceptionListener` | **Kết nối** JMS | `onException(JMSException)` | Thông báo lỗi kết nối không có nơi báo qua lời gọi thông thường. |
| Spring `@JmsListener` | **Nhận** JMS, ở mức POJO method | Method được annotation | Container tạo listener adapter/converter giúp bạn. |
| Spring `SessionAwareMessageListener` | **Nhận** JMS có truy cập `Session` | `onMessage(Message, Session)` | Xử lý và có thể gửi reply trên session được container cấp. |

Đừng dùng `CompletionListener` để chờ message từ Queue: tên giống nhau nhưng đó là callback **phía producer**. Đừng nhầm `ExceptionListener` là nơi bắt mọi exception do logic `onMessage` ném ra.

## 3. Nhận bất đồng bộ bằng Jakarta Messaging API gốc

### 3.1. Năm bước cơ bản

Với Classic Jakarta Messaging:

1. Lấy `ConnectionFactory` phù hợp broker.
2. Tạo `Connection` và `Session`.
3. Tạo `MessageConsumer` gắn Queue/Topic.
4. Gọi `consumer.setMessageListener(listener)`.
5. Gọi `connection.start()` để cho phép delivery bắt đầu.

Thứ tự **đăng ký listener rồi mới start connection** giúp tránh message đến trước khi ứng dụng thiết lập xong callback.

```java
try (Connection connection = connectionFactory.createConnection();
     Session session =
             connection.createSession(Session.AUTO_ACKNOWLEDGE);
     MessageConsumer consumer =
             session.createConsumer(session.createQueue("orders.queue"))) {

    consumer.setMessageListener(message -> {
        System.out.println("received type=" + message.getClass().getName());
    });

    connection.start();

    // Giữ application/lifecycle hoạt động để provider còn gọi onMessage.
}
```

Đây là snippet thuộc method có biến `connectionFactory`; nó minh họa thứ tự nhưng **không giữ ứng dụng sống đủ lâu** nếu code thoát khỏi `try` ngay. Ra khỏi block, consumer/session/connection bị đóng và sẽ không tiếp tục nhận message. Mẫu đầy đủ có `CountDownLatch` được trình bày dưới đây.

### 3.2. Ví dụ Java 17+ hoàn chỉnh về logic JMS gốc

Class này có một method nhận **một message** bất đồng bộ, đồng thời tự gửi một message thử trên **session khác**, chờ listener phản hồi và cuối cùng đóng resource.

```java
package example.jms;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import jakarta.jms.Connection;
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSException;
import jakarta.jms.MessageConsumer;
import jakarta.jms.MessageProducer;
import jakarta.jms.Session;
import jakarta.jms.TextMessage;

public final class RawMessageListenerExample {

    private RawMessageListenerExample() {
    }

    public static boolean runOnce(ConnectionFactory factory)
            throws JMSException, InterruptedException {

        CountDownLatch observed = new CountDownLatch(1);

        try (Connection connection = factory.createConnection();
             Session receiveSession =
                     connection.createSession(Session.AUTO_ACKNOWLEDGE);
             Session sendSession =
                     connection.createSession(Session.AUTO_ACKNOWLEDGE);
             MessageConsumer consumer = receiveSession.createConsumer(
                     receiveSession.createQueue("learning.listener.queue"));
             MessageProducer producer = sendSession.createProducer(
                     sendSession.createQueue("learning.listener.queue"))) {

            consumer.setMessageListener(message -> {
                if (!(message instanceof TextMessage text)) {
                    throw new IllegalArgumentException(
                            "Expected TextMessage");
                }

                try {
                    System.out.println("rawReceived=" + text.getText());
                    observed.countDown();
                } catch (JMSException error) {
                    throw new IllegalStateException(
                            "Cannot read TextMessage", error);
                }
            });

            // Listener đã đăng ký xong, bây giờ mới mở delivery.
            connection.start();

            // Gửi từ Session riêng, không dùng receiveSession từ thread này.
            producer.send(
                    sendSession.createTextMessage("hello-raw-listener"));

            // Demo có deadline. Trong service thật, container quản lý lifecycle.
            return observed.await(10, TimeUnit.SECONDS);
        }
    }
}
```

Đây là **một class Java 17+ biên dịch được khi có Jakarta Messaging API/provider**, nhưng **không phải một `main` độc lập**: cần truyền `ConnectionFactory` do Artemis hoặc ứng dụng tạo khi gọi `RawMessageListenerExample.runOnce(...)`. Mẫu ở mục 5 cung cấp một Spring Boot application hoàn chỉnh dùng hạ tầng sẵn có để chạy thực tế.

Điểm kỹ thuật đáng chú ý:

- `receiveSession` được provider dùng để gọi listener. `sendSession` **khác** được dùng từ thread ứng dụng để gửi message; không có hai thread thao tác cùng `Session`.
- `CountDownLatch` chỉ giữ phương thức demo sống đến khi callback quan sát được một message. `observed.await(...)` là thao tác chờ ở thread **demo**, không phải `MessageConsumer.receive(...)`.
- `observed.countDown()` trong listener chứng minh callback đã chạy tới dòng đó, **không tự chứng minh toàn bộ transaction/acknowledgement downstream đã hoàn tất**.
- `try-with-resources` giữ connection, session, consumer và producer sống trong scope, rồi đóng theo thứ tự ngược khi method kết thúc. Không đóng chúng từ logic nghiệp vụ mỗi khi nhận message.
- Nếu Queue có message cũ hoặc consumer khác, output có thể khác. Dùng Queue dành riêng cho integration test và cô lập publisher/consumer.
- Nếu callback xử lý một message sai kiểu và ném lỗi trước khi `countDown`, demo có thể timeout; hành vi redelivery tùy ack mode/provider.

### 3.3. Vì sao không dùng receive() đồng thời trên cùng Session?

Một `Session` là một **ngữ cảnh xử lý một luồng logic tại một thời điểm**. Khi đã thiết lập asynchronous listener và connection được start, provider sở hữu luồng delivery của session đó. Gọi `consumer.receive()` từ thread ứng dụng trên cùng `Session` đồng thời là sai mô hình JMS. Jakarta Messaging quy định không dùng chung một session cho cả asynchronous delivery và synchronous receive.

**Đúng:** thread A cấu hình listener trên session A; thread B dùng session B cho send hoặc receive riêng. **Sai:** thiết lập listener trên session A rồi một thread khác tiếp tục `receive()`/`commit()` trên session A trong lúc callback đang chạy.

Nếu cần tạm ngưng toàn bộ delivery, JMS có `Connection.stop()` ở tầng connection; dùng ở **thread điều phối lifecycle** thay vì tùy ý gọi giữa callback. Khi nhiều consumer/session chia sẻ connection, thao tác stop ảnh hưởng nhiều hơn một listener.

### 3.4. JMSContext/JMSConsumer

Simplified API cũng cho phép:

```java
try (JMSContext context =
             connectionFactory.createContext(JMSContext.AUTO_ACKNOWLEDGE)) {

    JMSConsumer consumer = context.createConsumer(
            context.createQueue("orders.queue"));

    consumer.setMessageListener(message -> {
        System.out.println("async message received");
    });

    // Phải giữ context sống để callback tiếp tục nhận message.
}
```

Đây là snippet trong method có `connectionFactory`; vì scope kết thúc ngay nên **không phải server listener hoàn chỉnh**. `JMSContext` thường tự start connection khi tạo consumer do `autoStart=true`, khác Classic API phải gọi `connection.start()`. Nếu cần cấu hình listener và tài nguyên trước khi delivery, có thể `context.setAutoStart(false)` trước `createConsumer` rồi `context.start()` sau khi đã thiết lập listener.

`JMSContext` vẫn chịu quy tắc threading như session bên dưới, không phải singleton thread-safe dùng tùy ý cho mọi worker.

## 4. Vòng đời resource và threading trong callback

### 4.1. Một Session, một luồng callback tuần tự

Đặc tả quy định rằng khi nhiều `MessageListener` được đăng ký cho các consumer thuộc **cùng Session**, các lần gọi `onMessage` của session đó được serialize: không có callback thứ hai trên session ấy khi callback trước chưa kết thúc. Điều đó đơn giản hóa chương trình, nhưng cũng có hệ quả:

- Một callback chạy lâu sẽ giữ việc delivery tiếp theo trên cùng session.
- Tăng số lượng listener object trên **cùng một session** không tự tăng throughput.
- Muốn xử lý đồng thời thực sự, dùng **nhiều session**; trong Spring container, điều chỉnh số concurrent consumers và số instance ứng dụng.
- Một bean listener có thể được nhiều session khác nhau gọi đồng thời nếu Spring container có concurrency lớn hơn 1. **Thread-safe state ở bean là bắt buộc.**

Ví dụ sai khi bean singleton bị nhiều consumer chia sẻ:

```java
public final class UnsafeCounterListener implements MessageListener {
    private int handled;

    @Override
    public void onMessage(Message message) {
        handled++; // Race nếu nhiều Session gọi cùng instance.
    }
}
```

Thay bằng `LongAdder`, `AtomicLong`, state bất biến hoặc chuyển state vào database có cơ chế concurrency phù hợp. Lưu ý bộ đếm ở RAM không phải transaction log bền vững.

### 4.2. Đừng lạm dụng callback thread

Một callback lý tưởng:
- Validate kiểu message và metadata cần thiết.
- Thực hiện business logic có giới hạn thời gian.
- Để exception thoát ra **nếu container đang quản lý transaction và bạn muốn rollback**.
- Ghi log có correlation ID, cập nhật metrics rồi trả về.

Không nên giữ callback hàng phút vì một HTTP endpoint không có timeout, hoặc tạo hàng nghìn thread tùy ý từ mỗi `onMessage`. Nếu bạn chỉ đưa công việc sang executor rồi trả `onMessage` ngay, container có thể **ack/commit message trước khi công việc trong executor thành công**. Điều đó làm mất bảo đảm xử lý nếu executor/task hoặc JVM chết. Muốn xử lý background bền vững, hãy thiết kế queue công việc, outbox/inbox hoặc transaction riêng đúng nghĩa.

### 4.3. Graceful shutdown

Trong JMS gốc, owner cần stop/close connection, session, consumer khi ứng dụng dừng. `close` có thể chờ listener đang thực thi kết thúc; tránh đóng chính session của mình tùy tiện từ callback vì không portable.

Trong Spring, để `DefaultMessageListenerContainer` là bean do Spring quản lý. Nó có lifecycle start/stop và resource recovery. Khi ứng dụng dừng, Spring dừng nhận rồi dọn tài nguyên; bạn không gọi `connectionFactory.close()` trong mỗi `onMessage`.

Trước khi deploy, kiểm tra thời gian xử lý tối đa, khả năng drain in-flight message, restart/rolling deployment, prefetch và việc shutdown quá sớm có thể khiến broker redeliver.

## 5. Ví dụ Spring Boot thực tế: MessageListener + DefaultMessageListenerContainer

Ở ứng dụng Spring, tự tạo connection/session trong mỗi service thường không phải lựa chọn tối ưu. Thay vào đó, khai báo **một bean `MessageListener`** và một **`DefaultMessageListenerContainer`**, để Spring chủ động sở hữu vòng đời consumer.

Ví dụ dưới đây dùng:

- Java 17+.
- Spring Boot **3.5.8** (Spring Framework 6.x).
- Apache ActiveMQ Artemis broker **đang chạy bên ngoài**.
- `spring-boot-starter-artemis`.
- `DefaultMessageListenerContainer` nhận bất đồng bộ xét từ góc độ mã nghiệp vụ, gọi `MessageListener.onMessage`.
- JMS **local transaction** cho mỗi message, cấu hình `sessionTransacted=true`.
- Một `ApplicationRunner` gửi test message rồi đợi tín hiệu callback bằng `CountDownLatch`.

**Cần biết trước:** `DefaultMessageListenerContainer` của Spring khác `SimpleMessageListenerContainer` ở cách nhận bên dưới. DMLC thường dùng worker thread gọi `receive` rồi dispatch tới listener, chứ không nhất thiết đăng ký provider callback bằng `MessageConsumer.setMessageListener`. Từ góc nhìn business code, cả hai vẫn là **nhận bất đồng bộ qua MessageListener**; điểm này được giải thích sâu ở mục 7.

### 5.1. Cấu trúc dự án

```text
async-message-listener/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── example/
        │       └── jms/
        │           └── AsyncMessageListenerApplication.java
        └── resources/
            └── application.properties
```

### 5.2. pom.xml

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
    <artifactId>async-message-listener</artifactId>
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

`spring-boot-starter-artemis` cung cấp client Jakarta Messaging và Spring JMS phù hợp nhờ dependency management của Boot. Không tự thêm `javax.jms-api` đời cũ để tránh xung đột namespace.

### 5.3. application.properties

```properties
spring.artemis.mode=native
spring.artemis.broker-url=${JMS_BROKER_URL:tcp://localhost:61616}
spring.artemis.user=${JMS_USERNAME}
spring.artemis.password=${JMS_PASSWORD}

# Container tự quản lý connection/session/consumer trong ví dụ.
spring.jms.cache.enabled=false

# Phía gửi dùng Queue, không phải Topic.
spring.jms.pub-sub-domain=false
```

Giải thích:
- `spring.artemis.mode=native` dùng **Artemis broker ngoài ứng dụng**. Nó không tự khởi động broker.
- Username/password lấy từ environment, **không hardcode** credentials sản xuất; hai biến này phải có giá trị thực khi chạy.
- `spring.jms.cache.enabled=false` tránh một lớp `CachingConnectionFactory` bên ngoài listener container trong demo, vì DMLC đã có cache/recovery riêng. Trong hệ thống phức tạp có thể dùng factory/pool riêng cho publisher và listener sau khi đo thực tế.
- Queue sẽ là `learning.listener.queue`. Broker phải provision Queue trước **hoặc** hỗ trợ auto-create Queue theo security/routing policy.
- Producer minh họa dùng `JmsTemplate`; consumer dùng **JMS `MessageListener` thuần** do container gọi.

### 5.4. Toàn bộ Java file

**`src/main/java/example/jms/AsyncMessageListenerApplication.java`**

```java
package example.jms;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.MessageListener;
import jakarta.jms.TextMessage;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.listener.DefaultMessageListenerContainer;

@SpringBootApplication
public class AsyncMessageListenerApplication {

    private static final String QUEUE = "learning.listener.queue";

    public static void main(String[] args) {
        SpringApplication.run(AsyncMessageListenerApplication.class, args);
    }

    @Bean
    DemoOrderListener orderMessageListener() {
        return new DemoOrderListener();
    }

    @Bean
    DefaultMessageListenerContainer ordersContainer(
            ConnectionFactory connectionFactory,
            DemoOrderListener orderMessageListener) {

        var container = new DefaultMessageListenerContainer();
        container.setConnectionFactory(connectionFactory);
        container.setDestinationName(QUEUE);
        container.setMessageListener(orderMessageListener);
        container.setSessionTransacted(true);
        container.setConcurrency("1-2");
        container.setRecoveryInterval(5_000L);
        return container;
    }

    @Bean
    ApplicationRunner publishSample(
            JmsTemplate jmsTemplate,
            DemoOrderListener listener) {

        return args -> {
            jmsTemplate.convertAndSend(QUEUE, "event:demo-001");

            boolean invoked = listener.await(10, TimeUnit.SECONDS);
            System.out.println("listenerInvoked=" + invoked);

            if (!invoked) {
                throw new IllegalStateException(
                        "Listener did not receive a message in 10 seconds");
            }
        };
    }

    public static final class DemoOrderListener implements MessageListener {
        private final CountDownLatch observed = new CountDownLatch(1);

        @Override
        public void onMessage(Message message) {
            if (!(message instanceof TextMessage textMessage)) {
                throw new IllegalArgumentException(
                        "Expected TextMessage");
            }

            try {
                String body = textMessage.getText();
                if (!"event:demo-001".equals(body)) {
                    throw new IllegalArgumentException(
                            "Unexpected payload: " + body);
                }

                System.out.println("listenerBody=" + body);
                observed.countDown();
            } catch (JMSException error) {
                throw new IllegalStateException(
                        "Cannot read JMS text", error);
            }
        }

        public boolean await(long timeout, TimeUnit unit)
                throws InterruptedException {
            return observed.await(timeout, unit);
        }
    }
}
```

**Đây là chương trình Java đầy đủ**, với một class public và một nested class, dùng Spring Boot và broker Artemis sẵn sàng. Không cần thêm `@EnableJms` vì ta **tạo trực tiếp bean `DefaultMessageListenerContainer`**, không đăng ký endpoint annotation `@JmsListener`.

**Các bước diễn ra:**

1. Boot dựng `ConnectionFactory` và `JmsTemplate` từ starter/properties.
2. Spring tạo `DemoOrderListener` rồi cấu hình `DefaultMessageListenerContainer` nhận ở Queue `learning.listener.queue`.
3. Container được Spring quản lý bằng lifecycle, tự mở session/consumer khi bắt đầu nhận message và tự khôi phục khi broker tạm unavailable.
4. `ApplicationRunner` dùng `JmsTemplate.convertAndSend(...)` gửi một `TextMessage`.
5. Container lấy message và gọi `DemoOrderListener.onMessage(message)` ở worker thread của container.
6. Callback kiểm tra kiểu, đọc body, in ra stdout và báo `CountDownLatch`.
7. `ApplicationRunner` quan sát latch rồi in trạng thái. Khi callback trả về bình thường, local JMS transaction được container commit; khi callback ném lỗi, container rollback.
8. Khi Spring context đóng, container dừng nhận và dọn các resource của nó.

**Ý nghĩa của latch:** `observed.countDown()` xảy ra **bên trong callback**, trước thời điểm framework hoàn tất xử lý transaction. Vì vậy `listenerInvoked=true` chỉ chứng minh callback đã chạy tới điểm báo thành công logic; nó **không phải xác nhận JMS commit hoàn tất**. Muốn kiểm thử commit/redelivery, cần integration test và quan sát trạng thái broker.

### 5.5. Chạy và quan sát

Giả định broker Artemis đang chạy trên `tcp://localhost:61616`, account có quyền send/consume và Queue dành riêng cho demo không còn message cũ. Trong PowerShell:

```powershell
$env:JMS_BROKER_URL = "tcp://localhost:61616"
$env:JMS_USERNAME = "dev-user"
$env:JMS_PASSWORD = "dev-password"
mvn spring-boot:run
```

Với shell POSIX:

```bash
JMS_BROKER_URL=tcp://localhost:61616 \
JMS_USERNAME=dev-user \
JMS_PASSWORD=dev-password \
mvn spring-boot:run
```

Thay `dev-user`/`dev-password` bằng thông tin thực của broker. Lưu ý Spring Boot ứng dụng mặc định vẫn đang chạy sau `ApplicationRunner` vì có listener container; dừng bằng Ctrl+C để kiểm tra graceful shutdown.

**Hai dòng do code chủ động in khi điều kiện demo thành công:**

```text
listenerBody=event:demo-001
listenerInvoked=true
```

Các log Spring/Artemis cũng xuất hiện. Thứ tự hai dòng do code in ở ví dụ này được đồng bộ bởi `CountDownLatch` (listener in body rồi mới countDown), nhưng **log của framework vẫn có thể xen giữa**. Nếu Queue có message khác, listener có thể ném lỗi và bị redeliver; nếu nhiều consumer khác đang chạy, message có thể tới consumer khác và demo timeout. Không coi stdout trong môi trường không cô lập là bất biến.

Build để kiểm tra biên dịch khi chưa chạy broker:

```bash
mvn -q -DskipTests package
```

Việc biên dịch không chứng minh kết nối broker, quyền Queue hay transaction hoạt động. Muốn kiểm chứng end-to-end, cần chạy với broker thật hoặc môi trường integration test có Artemis tương thích.

## 6. Vì sao phải dùng listener container trong Spring?

Nếu mỗi lần Spring service khởi chạy lại tự gọi `ConnectionFactory.createConnection()`, `Session.createConsumer()` và `setMessageListener(...)`, ứng dụng phải tự giải quyết:

- Connection/session lifecycle, shutdown và cleanup.
- Retry/reconnect khi broker mất kết nối.
- Cơ chế thread, concurrency, health/recovery.
- Transaction và acknowledgement.
- Cấu hình Queue/Topic, message selector, durable subscription.
- Logging, monitor và giới hạn resource.

**Message listener container** giải quyết hầu hết hạ tầng này. Bạn truyền vào `ConnectionFactory`, tên destination và listener; Spring chủ động quản lý consumer/threads/transaction rồi invoke callback khi có message.

Có hai container quan trọng:

| Tiêu chí | `SimpleMessageListenerContainer` | `DefaultMessageListenerContainer` |
| --- | --- | --- |
| Cơ chế nhận bên dưới | Đăng ký `MessageConsumer.setMessageListener(...)`; provider dispatch callback. | Thường dùng worker task tự `receive`/polling rồi invoke listener. |
| Quản lý consumer | Số session/consumer cố định từ lúc startup. | Hỗ trợ mức concurrency lõi/tối đa và scale theo tải. |
| Recovery khi broker down | Ít chức năng recovery hơn, không linh hoạt bằng DMLC. | Có cơ chế recovery/retry khi connection lỗi, cấu hình backoff được. |
| External/JTA transaction | Không hỗ trợ tham gia externally managed transaction theo cách DMLC. | Có thể tham gia transaction manager ngoài, kể cả JTA khi được cấu hình. |
| Local JMS transaction | Có, qua `setSessionTransacted(true)`. | Có, qua `setSessionTransacted(true)`. |
| Phù hợp | Ứng dụng đơn giản, muốn gần với JMS native callback. | Phần lớn Spring application thực tế cần quản trị và reliability. |

**Điểm dễ nhầm:** `DefaultMessageListenerContainer` có chữ “listener” và gọi `MessageListener.onMessage`, nhưng **không bắt buộc provider đã được gọi `setMessageListener`**. Spring tự polling trên task thread. Vì thế đừng suy ngược các điều kiện callback/ack chính xác của JMS raw provider thành hành vi của mọi Spring container. Xem đặc tả và Javadoc đúng loại container.

### 6.1. Cấu hình SimpleMessageListenerContainer khi nào?

Đây là **phương án thay thế** cho DMLC ở ví dụ chính, không đăng ký cả hai container lên cùng Queue trong cùng demo:

```java
@Bean
SimpleMessageListenerContainer simpleListenerContainer(
        ConnectionFactory factory,
        MessageListener listener) {

    var container = new SimpleMessageListenerContainer();
    container.setConnectionFactory(factory);
    container.setDestinationName("orders.queue");
    container.setMessageListener(listener);
    container.setConcurrentConsumers(2);
    container.setSessionTransacted(true);
    return container;
}
```

Snippet này thuộc một class `@Configuration`, cần import `@Bean`, `ConnectionFactory`, `MessageListener` và `org.springframework.jms.listener.SimpleMessageListenerContainer`. Nó sử dụng provider callback qua `MessageConsumer.setMessageListener`. Với concurrency 2, container có nhiều session; cùng một bean listener cần thread-safe. Đây không phải lựa chọn mặc định cho mọi deployment, đặc biệt khi cần JTA hoặc dynamic recovery.

**Không cài cùng lúc** ví dụ `SimpleMessageListenerContainer` và `DefaultMessageListenerContainer` lên Queue nếu bạn muốn mỗi message luôn được demo listener chính nhận, vì hai container trở thành competing consumers.

## 7. Transaction và acknowledgement: nhận message rồi có thể mất/nhận lại không?

Đây là phần quan trọng nhất cho tính tin cậy. **Callback được gọi không đồng nghĩa message đã được xử lý và commit chắc chắn.** Hành vi phụ thuộc JMS session/ack mode **và** listener container.

### 7.1. Classic JMS native MessageListener

Trong Jakarta Messaging API gốc:

- `AUTO_ACKNOWLEDGE`: provider tự acknowledge sau khi `onMessage` trở về thành công. Nếu callback ném `RuntimeException`, đặc tả có quy tắc redelivery phụ thuộc ack mode, nhưng đồng thời coi việc listener ném unchecked exception là lỗi lập trình mà ứng dụng nên tránh.
- `DUPS_OK_ACKNOWLEDGE`: provider có thể ack trì hoãn, nên ứng dụng phải chấp nhận khả năng redelivery.
- `CLIENT_ACKNOWLEDGE`: ứng dụng phải gọi `message.acknowledge()` phù hợp; lời gọi acknowledge thường ack **mọi message đã được giao trong cùng Session**, không chỉ một message riêng.
- `SESSION_TRANSACTED`: việc nhận được xác nhận bằng commit, được khôi phục bằng rollback.

**Sự thật dễ bị bỏ qua:** Với **raw provider `MessageListener` trên session transacted**, ném `RuntimeException` từ `onMessage` **không tự bắt buộc provider rollback transaction**. Đặc tả nói session vẫn cần được commit hoặc rollback một cách đúng đắn. Đừng sao chép kỳ vọng “ném exception là tự rollback” từ Spring container sang JMS raw code mà không cấu hình ownership.

### 7.2. Spring listener container thay đổi cách điều phối lỗi

Ở `DefaultMessageListenerContainer` với `setSessionTransacted(true)`, Spring quản lý local JMS transaction cho mỗi lần xử lý. Nếu listener kết thúc thành công, container commit; nếu listener ném exception và nó thoát ra đến container, Spring rollback và broker có thể redeliver theo policy.

**Cảnh báo với AUTO_ACKNOWLEDGE mặc định:** Tài liệu Spring lưu ý rằng `DefaultMessageListenerContainer` thường **ack trước khi chạy listener** trong mode này, nên nếu business code ném exception, không có redelivery tin cậy chỉ bằng exception. `SimpleMessageListenerContainer` có timing khác do provider callback, nhưng cũng không nên dựa vào AUTO_ACK khi yêu cầu delivery/recovery đáng tin cậy. Với Queue chứa công việc quan trọng, hãy cân nhắc **`sessionTransacted=true`**.

### 7.3. Nếu listener ném exception thì sao?

Giả sử có:

```java
@Override
public void onMessage(Message message) {
    throw new IllegalStateException("Processing failed");
}
```

Snippet này mô phỏng lỗi business trong listener. Với **Spring container transacted**, framework nhìn thấy exception, rollback việc nhận, và broker có thể redeliver message. Số lần retry, khoảng delay, dead-letter address và thứ tự redelivery phụ thuộc broker (ví dụ Artemis) và cấu hình policy.

Không làm:

```java
@Override
public void onMessage(Message message) {
    try {
        doBusinessWork(message);
    } catch (Exception ex) {
        log.error("Processing failed", ex);
        // return bình thường = container có thể COMMIT.
    }
}
```

Đây là **anti-pattern minh họa**, chưa phải code chạy độc lập vì `doBusinessWork`/`log` chưa định nghĩa. Trong transacted listener, nếu bạn **nuốt exception rồi trả về bình thường**, container có thể commit và message không được redeliver dù business work thất bại.

Trường hợp business quyết định “lỗi không retry” thì nên thiết kế rõ DLQ/parking queue hoặc record lỗi bền vững, không chỉ log rồi bỏ.

### 7.4. JMS local transaction không bao luôn database

Nếu `onMessage` ghi SQL rồi trả về, có thể xảy ra:

```text
SQL commit thành công
    |
JMS commit thất bại / JVM chết trước commit
    |
Broker redeliver cùng message
    |
Business action bị thực hiện lần hai nếu không idempotent
```

`setSessionTransacted(true)` chỉ áp dụng local JMS transaction. Nó **không** tự đưa JDBC/HTTP/API đối tác vào cùng transaction. Giải pháp thực tế thường là idempotent consumer + inbox/dedup table theo `eventId`, hoặc outbox/JTA/XA khi thực sự có yêu cầu và hạ tầng phù hợp.

### 7.5. Xem thông tin redelivery

Khi nhận lại message, JMS có:

- `message.getJMSRedelivered()`: header cho biết message được đánh dấu đã redeliver.
- `message.getIntProperty("JMSXDeliveryCount")`: số lần provider giao message theo đặc tả, nếu thuộc tính hiện diện trên provider hỗ trợ đúng quy tắc.

Ví dụ:

```java
try {
    String messageId = message.getJMSMessageID();
    boolean redelivered = message.getJMSRedelivered();
    int attempts = message.propertyExists("JMSXDeliveryCount")
            ? message.getIntProperty("JMSXDeliveryCount")
            : -1;
    System.out.printf(
            "id=%s redelivered=%s deliveries=%d%n",
            messageId, redelivered, attempts);
} catch (JMSException e) {
    throw new IllegalStateException("Cannot read headers", e);
}
```

Đoạn trên dùng `message` thuộc callback và cần `JMSException`; nó là snippet, không phải app độc lập. Thông tin này giúp debug, nhưng **không** nên dùng làm căn cứ duy nhất cho idempotency: một event có thể bị publisher gửi trùng với JMSMessageID khác. Hãy tạo business event ID bền vững.

## 8. Concurrency và thứ tự xử lý message

### 8.1. Mỗi session serialize callback, nhiều session có thể chạy song song

Với Spring DMLC:

```java
container.setConcurrency("1-4");
```

Nghĩa là container thường giữ tối thiểu một consumer/worker và có thể tăng tối đa bốn dưới tải, tùy cấu hình và triển khai. Nó không đồng nghĩa callback xử lý đúng bốn message cùng lúc trong mọi trường hợp.

Điều cần ghi nhớ:
- Queue có **competing consumers**: một message thường giao cho một consumer tại một thời điểm.
- Nhiều consumer của một Queue có thể xử lý song song, nên **thứ tự kết thúc business work khác thứ tự message được gửi**.
- Với Topic, nhiều subscriber có thể mỗi người nhận một bản; đừng dùng ý tưởng “tăng concurrent consumers giống Queue” trên Topic một cách máy móc.
- Listener bean có thể được dùng chung trên nhiều worker threads: field mutable không đồng bộ dễ gây race.
- Nếu nghiệp vụ yêu cầu thứ tự theo `orderId`, cân nhắc message grouping/partitioning theo provider hoặc concurrency phù hợp.

### 8.2. Ví dụ thread-safe counter

```java
import java.util.concurrent.atomic.LongAdder;
import jakarta.jms.Message;
import jakarta.jms.MessageListener;

public final class CountingListener implements MessageListener {

    private final LongAdder processed = new LongAdder();

    @Override
    public void onMessage(Message message) {
        // Thực thi nghiệp vụ ở đây.
        processed.increment();
    }

    public long processedCount() {
        return processed.sum();
    }
}
```

Đây là Java 17+ code minh họa thread-safe counter trong RAM. **Bộ đếm không atomic cùng JMS transaction**; nếu onMessage increment rồi container rollback, counter vẫn tăng. Với business audit/dedup cần lưu trạng thái bền vững cùng cơ chế nhất quán.

### 8.3. Tránh giữ lock toàn cục trong listener

Nếu cả bốn concurrent consumers đều gọi `synchronized` trên một singleton listener cho toàn bộ xử lý lâu, bạn vô tình serialize chúng ở tầng ứng dụng, làm mất lợi ích concurrency. Dùng lock theo business key hoặc xử lý thread-safe fine-grained, và đo latency dưới tải.

## 9. Queue, Topic, selector và việc chọn destination

`MessageListener` chỉ xác định **cách xử lý message khi được giao**; destination và subscription do `MessageConsumer` hoặc Spring container quy định.

| Trường hợp | Cách cấu hình | Điều cần lưu ý |
| --- | --- | --- |
| Nhận Queue | `session.createQueue("orders.queue")` / `setDestinationName("orders.queue")` với domain Queue | Có competing consumers; số consumer lớn giúp throughput nhưng mất thứ tự xử lý tổng thể. |
| Nhận Topic | `session.createTopic("events.topic")` / `setPubSubDomain(true)` ở container | Mỗi subscription có semantics riêng; durable/shared cần thêm cấu hình phù hợp. |
| Lọc message | JMS selector ví dụ `eventType = 'ORDER_CREATED'` | Selector lọc theo JMS headers/properties, không phải parse body JSON. |
| Durable Topic | Durable subscription với client ID / subscription name theo provider | Cần quản trị subscription, vòng đời và tính duy nhất của client ID. |
| Request/reply | Dùng `JMSReplyTo`/`JMSCorrelationID` | Tên destination và correlation phải nhất quán, không tự biến callback thành reply protocol. |

**Ví dụ selector** là snippet thêm vào DMLC bean **trước khi start**:

```java
container.setMessageSelector("eventType = 'ORDER_CREATED'");
```

Sender phải đặt property phù hợp, ví dụ:

```java
jmsTemplate.send("orders.queue", session -> {
    var msg = session.createTextMessage("order-1");
    msg.setStringProperty("eventType", "ORDER_CREATED");
    return msg;
});
```

Đây là snippet trong Spring component có `jmsTemplate`; không phải một class độc lập. Nếu selector không khớp, listener không được gọi dù Queue có message thuộc loại khác. Đây không phải lỗi `MessageListener`.

## 10. MessageListener, SessionAwareMessageListener và @JmsListener

### 10.1. MessageListener thuần

`MessageListener` dùng hợp đồng JMS chuẩn:

```java
public void onMessage(Message message)
```

Không có tham số `Session`. Thích hợp khi bạn cần mã portable giữa Spring và JMS provider hoặc muốn truy cập trực tiếp headers/body trong logic nhận.

### 10.2. Spring SessionAwareMessageListener

Spring cung cấp extension `org.springframework.jms.listener.SessionAwareMessageListener<Message>`:

```java
import jakarta.jms.Destination;
import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.MessageProducer;
import jakarta.jms.Session;
import jakarta.jms.TextMessage;
import org.springframework.jms.listener.SessionAwareMessageListener;

public final class ReplyingListener
        implements SessionAwareMessageListener<Message> {

    @Override
    public void onMessage(Message request, Session session)
            throws JMSException {

        Destination replyTo = request.getJMSReplyTo();
        if (replyTo == null) {
            return;
        }

        try (MessageProducer producer = session.createProducer(replyTo)) {
            TextMessage reply =
                    session.createTextMessage("processed");
            reply.setJMSCorrelationID(request.getJMSCorrelationID());
            producer.send(reply);
        }
    }
}
```

Class Java trên cần Spring JMS và Jakarta API; khi triển khai phải đăng ký vào Spring listener container thích hợp. Với local transacted container, reply được gửi bằng **cùng JMS Session** trong giao dịch nhận, có thể commit/rollback cùng message được nhận. Nhưng API SQL hoặc HTTP gọi trong callback **không tự trở thành atomic**.

`SessionAwareMessageListener` là interface của **Spring**, không phải `jakarta.jms.MessageListener`. Khi muốn portability tối đa hoặc dùng listener container không hỗ trợ extension, chọn standard `MessageListener`.

### 10.3. @JmsListener: viết POJO không phải implement MessageListener

Cách quen thuộc trong Spring Boot:

```java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class OrderListenerService {

    @JmsListener(destination = "orders.queue")
    public void handleOrder(String body) {
        System.out.println("order=" + body);
    }
}
```

Annotation infrastructure tạo container và dùng adapter/converter để gọi method `handleOrder`. Method này **không implement `MessageListener`**, nhưng vẫn nhận bất đồng bộ ở góc nhìn ứng dụng.

Nếu tự khai báo factory:

```java
@Bean(name = "jmsListenerContainerFactory")
DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
        ConnectionFactory connectionFactory) {

    var factory = new DefaultJmsListenerContainerFactory();
    factory.setConnectionFactory(connectionFactory);
    factory.setSessionTransacted(true);
    factory.setConcurrency("1-3");
    return factory;
}
```

Snippet này thuộc class cấu hình có import `@Bean`, `DefaultJmsListenerContainerFactory` và `ConnectionFactory`. Với Spring Framework thuần, cần bật `@EnableJms`. Spring Boot thường tự kích hoạt annotated JMS listener infrastructure khi starter tương ứng có trên classpath.

**Không đăng ký đồng thời cả `@JmsListener` và container thủ công của ví dụ mục 5 cùng đích** nếu mục tiêu demo là một consumer nhận độc quyền; đó sẽ là hai consumer tranh nhau lấy message.

### 10.4. Khi nào dùng MessageListenerAdapter?

`org.springframework.jms.listener.adapter.MessageListenerAdapter` thích hợp khi muốn một POJO nhận message qua một method khác, ví dụ `handleMessage(String body)`, mà không dùng annotation. Adapter giúp chuyển đổi payload và gọi method đã cấu hình. Đây là cách trung gian giữa raw `MessageListener` và `@JmsListener`.

Với ứng dụng Spring hiện đại, `@JmsListener` thường ngắn gọn hơn, còn `MessageListener` thuần hữu ích khi cần kiểm soát các trường JMS và muốn reuse contract trực tiếp.

## 11. Lỗi và redelivery: thiết kế callback an toàn

Một listener production không nên giả định dữ liệu luôn hợp lệ. Hãy tách ba nhóm lỗi:

1. **Lỗi payload không thể xử lý**: sai schema, trường bắt buộc thiếu, message type không hỗ trợ. Có thể xử lý qua DLQ/parking queue sau số lần thử xác định; retry vô hạn ít khi giúp.
2. **Lỗi tạm thời**: database/HTTP unavailable, lock timeout, broker tạm disconnect. Cần bounded retry/backoff và redelivery policy.
3. **Lỗi lập trình**: `NullPointerException`, race condition, dùng sai session/lifecycle. Log đầy đủ, sửa code, tránh “nuốt” exception rồi commit message.

### 11.1. Không coi onMessage là transaction tự động

JMS provider giao message bằng callback, nhưng mức tin cậy không được xác định chỉ bởi chữ “async”. Phải biết container có `sessionTransacted`, acknowledge mode và policy broker nào.

Một listener có thể được gọi nhiều lần cho **cùng một business event** do redelivery hoặc publisher retry. Do đó cần idempotent handler; ví dụ dùng key `eventId` làm unique constraint trong database, kiểm tra đã xử lý trước khi gây tác dụng phụ.

### 11.2. Vì sao catch rồi log không đủ?

```java
@Override
public void onMessage(Message message) {
    try {
        saveOrder(message);
    } catch (RuntimeException e) {
        logger.error("Cannot process order", e);
        // return bình thường -> Spring container có thể commit.
    }
}
```

Đây là **anti-pattern minh họa** vì `saveOrder` và `logger` chưa được định nghĩa. Nếu đang dùng `DefaultMessageListenerContainer` transacted, hãy propagate lỗi không thể hoàn thành hoặc ghi nhận một đường xử lý lỗi có kiểm soát vào nơi bền vững. Nếu lỗi poison message lặp mãi, broker DLQ/retry limit mới là cơ chế chống vô hạn phù hợp.

### 11.3. Quan sát trạng thái xử lý

Metrics tối thiểu:
- `jms_listener_received_total`.
- `jms_listener_processed_total` và `jms_listener_failure_total`.
- `jms_listener_processing_seconds` theo destination/type.
- Broker queue depth, in-flight/unacknowledged, consumer count, redelivery count và DLQ count.
- Số lần restart/reconnect của listener container, độ trễ recovery.
- Business-level duplicates bị idempotency loại bỏ.

Không dùng mỗi số dòng log `onMessage` để tính “một event đúng một lần”: một event có thể được nhận lại vì rollback, hoặc nhiều event chung payload.

## 12. Testing: chứng minh đúng hơn chỉ nhìn stdout

### 12.1. Happy path integration

1. Khởi động broker Artemis riêng cho test, tạo Queue `learning.listener.queue` hoặc bật auto-create.
2. Chạy Spring context có đúng **một listener container test**.
3. Gửi message có `eventId` riêng qua `JmsTemplate`.
4. Chờ listener nhận bằng `CountDownLatch` hoặc Awaitility với timeout hữu hạn.
5. Kiểm tra listener được gọi với đúng body/property và không có exception.
6. Để kiểm tra **commit**, cần quan sát broker trạng thái nhận/ack sau callback (latch chỉ báo callback đã chạy).

### 12.2. Rollback và redelivery

1. Cấu hình `setSessionTransacted(true)`.
2. Tạo listener test ném `RuntimeException` ở lần đầu, thành công ở lần sau.
3. Gửi một message.
4. Xác minh broker redeliver theo policy và `JMSXDeliveryCount`/`JMSRedelivered` thay đổi đúng kỳ vọng.
5. Kiểm tra business handler không gây duplicate side effects.

Không khẳng định broker luôn redeliver lập tức: redelivery delay, max delivery attempts và dead-letter address phụ thuộc cấu hình Artemis. Với raw `MessageListener` transacted do ứng dụng tự quản lý, **throw exception không mặc nhiên rollback**; test phải phản ánh cơ chế commit/rollback thực sự.

### 12.3. Concurrency

- Gửi nhiều message có ID riêng; bật `setConcurrency("2-4")`.
- Đảm bảo listener shared bean thread-safe và không mất update của state.
- Không assert thứ tự hoàn thành giống thứ tự producer gửi khi có competing consumers.
- Đo throughput, latency, số consumer thực và mức độ phân phối công việc, thay vì chỉ kiểm tra mỗi message “có log”.

### 12.4. Broker outage, reconnect và shutdown

- Tắt broker, xác nhận container log lỗi và thực hiện recovery/backoff.
- Bật broker lại, thử consumer reconnect và xử lý message còn pending.
- Dừng Spring application khi callback đang chạy, kiểm tra graceful shutdown cùng giới hạn thời gian chờ.
- Đảm bảo không có producer/consumer/session leak kéo dài sau nhiều restart.

### 12.5. Unit test listener không cần broker

`DemoOrderListener.onMessage` nhận interface `Message` nên có thể được unit test bằng một `TextMessage` mock hoặc instance provider test. Với Mockito:

```java
// Snippet minh họa bên trong JUnit test có Mockito.
TextMessage message = mock(TextMessage.class);
when(message.getText()).thenReturn("event:demo-001");

AsyncMessageListenerApplication.DemoOrderListener listener =
        new AsyncMessageListenerApplication.DemoOrderListener();

listener.onMessage(message);
assertTrue(listener.await(1, TimeUnit.SECONDS));
```

Đây không phải test class đầy đủ; cần dependency JUnit/Mockito và imports. Nó kiểm tra logic callback, **không** chứng minh broker delivery, ack hay Spring container transaction; các điều đó cần integration test.

## 13. Troubleshooting — những lỗi dễ gặp nhất

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra/sửa |
| --- | --- | --- |
| `onMessage` không bao giờ được gọi trong JMS raw | Chưa `connection.start()`, chưa set listener hoặc method thoát/đóng resource quá sớm | Đăng ký listener trước `start`, giữ connection/consumer sống. |
| `onMessage` không chạy trong Spring | Bean container chưa được scan/start, Queue sai, broker unavailable | Kiểm tra `@Bean`, context lifecycle, Queue/address, logs/recovery. |
| `ClassCastException` từ `TextMessage` | Producer gửi BytesMessage/ObjectMessage hoặc converter khác | Kiểm tra `instanceof` và quy ước schema/payload. |
| `JMSException` khi đọc text | Lỗi provider/message | Catch rồi chuyển unchecked hoặc xử lý theo policy. |
| Message bị xử lý rồi nhưng Queue còn/được gửi lại | Transaction rollback, JVM chết trước ack, redelivery policy | Xem JMS transaction/ack mode, JMSRedelivered, JMSXDeliveryCount. |
| Listener lỗi mà message không retry trong DMLC | `AUTO_ACKNOWLEDGE`, hoặc exception bị catch rồi nuốt | Đặt `sessionTransacted=true` và propagate lỗi phù hợp. |
| Xử lý hai lần khi DB ghi thành công | JMS commit thất bại/JVM chết và message được redeliver | Dùng idempotent consumer/inbox/unique event ID. |
| Chạy với concurrency 4 nhưng chỉ thấy một callback mỗi lúc | Queue ít message, lock chung, scaling config hoặc provider prefetch | Đo consumer/task thực, state/locks, tải thực. |
| Message không tới listener do selector | Property không khớp biểu thức selector | Kiểm tra JMS property names và selector syntax. |
| Dùng Topic nhưng muốn Queue competing consumers | Khác mô hình subscription | Cấu hình `pubSubDomain` và durable/shared đúng. |
| Tạo thêm `@JmsListener` rồi demo không nhận | Competing consumer khác lấy message | Chỉ dùng một cơ chế consumer trong demo cô lập. |
| `MessageListener` dùng session từ nhiều thread | Vi phạm quy tắc Jakarta Messaging session | Tách session hoặc để Spring container quản lý. |
| Retry vô hạn với poison message | Không có max delivery/DLQ | Đặt policy broker và xử lý poison message riêng. |
| Broker down khiến ứng dụng cứ retry | Recovery interval/backoff chưa phù hợp | Chỉnh backoff, alert, readiness và broker health. |
| Đóng JMS factory trong `onMessage` | Phá resource chia sẻ và lifecycle | Để container dừng/đóng khi shutdown. |
| Nhầm `CompletionListener` với `MessageListener` | Đặt callback sai phía producer/consumer | Chọn đúng API: receiving vs sending. |

## 14. Checklist production

- Chọn Queue hay Topic và xác định semantics của subscription trước khi đăng ký listener.
- Với Jakarta Messaging gốc: tạo consumer, `setMessageListener` rồi `connection.start()`; giữ connection/session sống đúng lifecycle.
- Không trộn synchronous `receive` và async listener trên cùng `Session` đang hoạt động.
- Với Spring: để listener container quản lý tài nguyên; ưu tiên `DefaultMessageListenerContainer` cho hầu hết trường hợp cần recovery/transaction linh hoạt.
- Kiểm tra `sessionTransacted=true` nếu Queue chứa dữ liệu quan trọng; hiểu sự khác biệt acknowledgement giữa JMS raw và từng container.
- Đừng nuốt exception khiến container commit; dùng retry/DLQ để xử lý lỗi tạm thời và poison message.
- Đảm bảo bean listener thread-safe nếu có nhiều concurrent sessions, và không đòi hỏi global ordering khi concurrency lớn hơn 1.
- Gắn `eventId` và triển khai idempotent consumer, nhất là khi xử lý database/HTTP ngoài transaction JMS.
- Theo dõi processing latency, rollback/redelivery, backlog, broker reconnect và shutdown.
- Thử nghiệm trên broker thực; đừng suy kết quả transaction từ log “onMessage invoked”.
- Tách môi trường Spring Boot standalone với Jakarta EE container khi chọn API JMS và resource factory.
- Dùng secrets/TLS và quyền send/consume theo nguyên tắc least privilege; không in mật khẩu broker.

## 15. Tự kiểm tra kiến thức

**1. MessageListener giúp ứng dụng không phải viết vòng lặp `receive()` như thế nào?**

Consumer đăng ký `onMessage`; provider hoặc Spring listener container chủ động dispatch message đến callback khi có thông điệp phù hợp.

**2. Nếu đăng ký listener mà không gọi `connection.start()` trong Classic JMS, chuyện gì xảy ra?**

Delivery có thể chưa bắt đầu, nên callback không được gọi dù broker có message.

**3. Tại sao một `Session` với ba MessageConsumer không tự xử lý ba message song song?**

Jakarta Messaging serialize các callback listener thuộc cùng `Session`. Muốn parallelism thực cần nhiều session.

**4. `DefaultMessageListenerContainer` có bắt buộc dùng `consumer.setMessageListener` để cung cấp async receiving cho app không?**

Không. DMLC thường dùng worker threads gọi `receive` rồi invoke listener. `SimpleMessageListenerContainer` mới gần với native provider callback qua `setMessageListener`.

**5. Với Spring DMLC `sessionTransacted=true`, callback ném exception có tác dụng gì?**

Container rollback local JMS transaction, broker có thể redeliver theo policy. Ngược lại, nuốt exception rồi trả bình thường có thể khiến container commit.

**6. Với raw transacted `MessageListener`, ném RuntimeException có tự bảo đảm rollback không?**

Không. Theo Jakarta Messaging, cần kiểm soát commit/rollback session đúng cơ chế, không được suy từ Spring container sang JMS raw.

**7. Tăng concurrency từ 1 lên 4 có bảo đảm giữ thứ tự business hoàn tất không?**

Không. Nhiều consumer có thể xử lý cùng lúc, thứ tự hoàn tất không còn được bảo đảm theo thứ tự gửi trên Queue.

**8. Khi xử lý SQL rồi JMS message bị redeliver, điều gì ngăn update SQL hai lần?**

Thiết kế idempotent consumer/inbox/dedup bằng business `eventId`, hoặc transaction coordination thật sự khi phù hợp. Local JMS transaction không bao gồm SQL transaction.

## Kết luận

`jakarta.jms.MessageListener` là giao diện cốt lõi để **nhận JMS message bất đồng bộ**: định nghĩa `onMessage(Message)` và đăng ký nó với một `MessageConsumer`. Trong Jakarta Messaging gốc, provider điều phối callback, mỗi `Session` serialize xử lý và `Connection.start()` mở delivery.

Trong Spring Framework, cùng interface này có thể được cấp cho `SimpleMessageListenerContainer` hoặc `DefaultMessageListenerContainer`. Container chịu trách nhiệm kết nối, consumer, thread, recovery, acknowledgement và transaction. `@JmsListener` là lớp abstraction cao hơn cho POJO, không phải API khác về việc gửi message. Với hệ thống quan trọng, kết hợp **local JMS transaction, redelivery/DLQ policy, idempotency và quan sát vận hành**; tuyệt đối không coi “`onMessage` đã chạy” là “toàn bộ nghiệp vụ đã commit chính xác một lần”.

## Tài liệu tham khảo

- Jakarta Messaging 3.1 — `MessageListener` Javadoc: https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/messagelistener
- Jakarta Messaging 3.1 — Specification, mục 6.2.5, 6.2.13–14 và 8.7 (*Receiving messages asynchronously*): https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
- Spring Framework 6.2 — *Receiving a Message* và *Asynchronous Receipt: Message-Driven POJOs*: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/receiving.html
- Spring Framework 6.2 — *Message Listener Containers*: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/using.html
- Spring Framework 6.2 — *Annotation-driven Listener Endpoints*: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/annotated.html
- Spring Framework 6.2 — `DefaultMessageListenerContainer` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html
- Spring Framework 6.2 — `SessionAwareMessageListener` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/listener/SessionAwareMessageListener.html
- Spring Boot 3.5 — JMS và Artemis: https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html
- Spring Guide — *Messaging with JMS*: https://spring.io/guides/gs/messaging-jms/
- Apache ActiveMQ Artemis — *Using JMS*: https://artemis.apache.org/components/artemis/documentation/latest/using-jms