# Connection và vòng đời kết nối trong JMS

> **Chủ đề:** API JMS cốt lõi trong Spring Framework. Bài này giải thích `ConnectionFactory`, `Connection`, quan hệ với `Session`, các trạng thái `start/stop/close`, cách quản lý tài nguyên trong Jakarta Messaging và cách Spring JMS quản lý kết nối thay cho ứng dụng.

## 1. Tại sao vòng đời Connection quan trọng?

JMS (Jakarta Messaging) cung cấp một API chuẩn để ứng dụng Java gửi và nhận thông điệp qua một **messaging provider/broker**, chẳng hạn ActiveMQ Artemis. `Connection` đại diện cho kết nối logic từ JMS client đến provider. Provider có thể dùng một hoặc nhiều tài nguyên mạng, phiên xác thực và tài nguyên nội bộ để triển khai kết nối đó. Không nên đồng nhất một đối tượng `Connection` với đúng một TCP socket trong mọi provider.

Nếu mở kết nối liên tục mà không giải phóng, ứng dụng có thể cạn tài nguyên, tăng thời gian bắt tay kết nối, tiêu thụ thread/socket và làm broker gặp giới hạn kết nối. Nếu đóng hoặc dừng nhầm kết nối đang được dùng bởi listener khác, việc nhận message có thể bị gián đoạn.

Có ba vấn đề cần phân biệt:
1. **Vòng đời tài nguyên:** tạo, dùng lại và đóng `Connection` cùng các `Session`/producer/consumer.
2. **Vòng đời nhận message:** `start()` và `stop()` điều khiển khả năng *giao message đến consumer*.
3. **Vòng đời nghiệp vụ:** một message được gửi/nhận/xác nhận chưa tự động chứng minh toàn bộ thao tác database hoặc hệ thống ngoài đã hoàn tất.

Mục tiêu sau bài: biết cấu trúc JMS API, giải thích chính xác `start()`/`stop()`/`close()`, dùng `try-with-resources` an toàn và phân biệt việc quản lý kết nối thủ công với `JmsTemplate`/`@JmsListener` trong Spring.

## 2. Những đối tượng liên quan

| API | Vai trò | Vòng đời và trách nhiệm |
| --- | --- | --- |
| `jakarta.jms.ConnectionFactory` | Đối tượng cấu hình/factory để tạo kết nối đến provider | Thường cấu hình một lần và dùng lại; do Spring Boot, JNDI hoặc mã khởi tạo provider cung cấp |
| `jakarta.jms.Connection` | Kết nối logic đến provider; tạo `Session`; điều khiển việc giao message đến consumer | Mới tạo ở trạng thái **stopped**; gọi `start()` để nhận, `stop()` để tạm dừng, `close()` để giải phóng |
| `jakarta.jms.Session` | Ngữ cảnh làm việc, tạo destination/producer/consumer/message, quản lý acknowledge hoặc transaction cục bộ | Thuộc một `Connection`; dùng tuần tự trên một thread tại một thời điểm; đóng khi không cần |
| `jakarta.jms.MessageProducer` | Gửi message đến destination | Tạo từ `Session`, đóng khi xong nếu quản lý thủ công |
| `jakarta.jms.MessageConsumer` | Nhận đồng bộ bằng `receive` hoặc bất đồng bộ qua `MessageListener` | Tạo từ `Session`; cần connection ở trạng thái started để message được giao |
| `jakarta.jms.Destination` | Đích gửi/nhận, chẳng hạn `Queue` hay `Topic` | Biểu diễn tên/định danh đích; việc đích tồn tại hoặc được tạo tự động phụ thuộc broker |
| `jakarta.jms.JMSContext` | API rút gọn gộp Connection và Session (`JMS 2.0+`) | `AutoCloseable`; mặc định tự start khi tạo consumer, có thể thay bằng `setAutoStart(false)` |

**Quan hệ đối tượng (API cổ điển):**

~~~text
ConnectionFactory (cấu hình cho provider)
    |
    +-- createConnection() --> Connection
                                  |
                                  +-- createSession() --> Session A
                                  |                       |
                                  |                       +--> MessageProducer
                                  |                       +--> MessageConsumer
                                  |
                                  +-- createSession() --> Session B
                                                          |
                                                          +--> MessageConsumer

Connection.start()/stop() -> điều khiển nhận message cho các consumer thuộc connection
Connection.close()        -> giải phóng connection và các tài nguyên con
~~~

Một connection có thể phục vụ **nhiều session**. Điều này hữu ích khi mỗi luồng/worker có session riêng, trong khi nhà cung cấp hoặc tầng pool/cache có thể tái sử dụng kết nối vật lý. **Không chia sẻ một Session đồng thời giữa nhiều thread**: Session được thiết kế để truy cập tuần tự. Nguyên tắc này cũng áp dụng cho `JMSContext` vì nó bao gồm một session.

Trong code Spring Boot 3.x/Spring Framework 6.x, import **`jakarta.jms.*`**. Nhiều bài JMS/Spring 5 cũ dùng **`javax.jms.*`**; không trộn hai namespace trong cùng ví dụ mà chưa kiểm tra mức tương thích dependency.

## 3. Trạng thái và chuyển trạng thái của Connection

Sơ đồ dưới đây là **mô hình giải thích**, không phải một enum trạng thái public của JMS:

~~~text
     ConnectionFactory.createConnection()
                    |
                    v
             CREATED / STOPPED
                    |
           start()  |    send() vẫn có thể hoạt động
                    v
                 STARTED <---------------------+
                    |                          |
              stop()|                          | start()
                    v                          |
                 STOPPED ----------------------+
                    |
              close() từ mọi trạng thái còn mở
                    v
                 CLOSED
               (kết thúc)
~~~

### 3.1. `createConnection()` — tạo kết nối

~~~java
Connection connection = connectionFactory.createConnection();
~~~

JMS provider có thể xác thực, mở đường truyền và cấp phát tài nguyên khi tạo kết nối (chi tiết tùy provider). Connection **mặc định ở trạng thái stopped**, nhờ đó ứng dụng có thể tạo session/consumer/listener trước khi bắt đầu nhận message.

Tạo được `Connection` không có nghĩa broker sẽ luôn khỏe hoặc mọi lần gửi/nhận sau đó đều thành công. Lỗi có thể phát sinh ở `createConnection`, `send`, `receive`, transaction hoặc trong listener.

### 3.2. `start()` — cho phép giao message đến consumer

~~~java
connection.start();
~~~

Khi connection được start, JMS có thể giao message cho các `MessageConsumer` thuộc connection. Với `receive(timeout)`, đây là điều kiện cần để việc nhận message diễn ra bình thường. Với `setMessageListener(...)`, callback cũng không được gọi khi connection còn stopped.

**Điểm dễ nhầm:** `start()` **không phải điều kiện để gửi**. Theo đặc tả Jakarta Messaging, producer vẫn có thể `send()` khi connection chưa start hoặc đã stop. Lệnh `start()` lặp lại trên connection đã started được bỏ qua.

### 3.3. `stop()` — tạm dừng giao message đến consumer

~~~java
connection.stop();
~~~

`stop()` **tạm dừng delivery đến consumer**, không đóng connection, không hủy session, không xóa queue và không làm mất mọi message đang chờ trong broker. Một cuộc gọi `start()` sau đó có thể tiếp tục delivery.

Một số chi tiết quan trọng:
- Gửi message vẫn có thể hoạt động trong lúc stopped.
- Lời gọi `receive(timeout)` có thể hết timeout và trả `null` khi connection còn stopped; không dùng `receive()` không giới hạn chỉ để “thử xem stop đã chạy chưa”.
- `stop()` phải phối hợp với message listener đang chạy và có thể **chờ callback hiện tại kết thúc** trước khi trả về; không xem nó là công tắc tức thời.
- Đừng gọi `stop()` từ chính listener đang xử lý trên cùng connection: tùy provider/hành vi phù hợp đặc tả, tình huống này có thể sinh ngoại lệ hoặc ảnh hưởng luồng xử lý. Hãy điều khiển vòng đời từ một thành phần quản lý độc lập.

Một số broker có cơ chế prefetch/buffering nội bộ. Điều JMS bảo đảm ở đây là **không giao message cho mã consumer khi connection stopped**; đừng suy luận về từng packet mạng.

### 3.4. `close()` — kết thúc connection

~~~java
connection.close();
~~~

`close()` giải phóng tài nguyên do connection sở hữu, đồng thời kết thúc session, producer, consumer thuộc connection. Nó có thể cần chờ thao tác nhận/listener đang chạy kết thúc có trật tự. Sau `close()`, connection đó **không thể start lại**; muốn hoạt động tiếp phải tạo một connection hợp lệ khác (hoặc lấy handle mới từ tầng pool/cache).

`close()` không phải “commit nghiệp vụ”: đóng một **session có transaction chưa commit** làm rollback transaction đó; đóng connection không tự acknowledge các message còn chưa được xác nhận trong session `CLIENT_ACKNOWLEDGE`. Quy tắc redelivery thực tế chịu ảnh hưởng bởi broker, loại destination, transaction và cấu hình consumer.

**Nguyên tắc:** với tài nguyên JMS do chính code tạo ra, đóng tài nguyên theo thứ tự ngược khi cấp phát; Java `try-with-resources` giúp giải phóng ngay cả khi có exception. Với connection do **Spring container/pool** quản lý, tuân theo hợp đồng của container, không tự ý đóng “kết nối dùng chung” bên dưới.

## 4. Ví dụ chạy được: quan sát send trước start, stop rồi start lại

Ví dụ sử dụng **Java 17+, Spring Boot 3.3.5, Artemis JMS client**. Spring Boot tạo `ConnectionFactory` từ cấu hình, nhưng phần mã bên dưới **trực tiếp dùng Jakarta JMS API** để làm rõ vòng đời. Chạy với broker Artemis ở `tcp://localhost:61616`, user `demo`/password `demo`, có queue `demo.lifecycle` và quyền gửi/nhận; nếu broker cho phép auto-create queue thì có thể để client tạo đích.

Ở ví dụ học tập này, **tắt Spring JMS session cache** để API thao tác với connection của provider thay vì proxy chia sẻ tài nguyên; không áp dụng thiết lập đó như một khuyến nghị mặc định cho production.

**Cấu trúc:**

~~~text
jms-connection-lifecycle/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/demo/LifecycleApplication.java
    └── resources/application.yml
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'jms-connection-lifecycle'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-artemis'
}
~~~

`src/main/resources/application.yml`:

~~~yaml
spring:
  main:
    web-application-type: none
  artemis:
    mode: native
    broker-url: tcp://localhost:61616
    user: demo
    password: demo
  jms:
    cache:
      enabled: false
~~~

`src/main/java/demo/LifecycleApplication.java`:

~~~java
package demo;

import jakarta.jms.Connection;
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.MessageConsumer;
import jakarta.jms.MessageProducer;
import jakarta.jms.Queue;
import jakarta.jms.Session;
import jakarta.jms.TextMessage;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LifecycleApplication implements ApplicationRunner {

    private final ConnectionFactory connectionFactory;

    public LifecycleApplication(ConnectionFactory connectionFactory) {
        this.connectionFactory = connectionFactory;
    }

    public static void main(String[] args) {
        SpringApplication.run(LifecycleApplication.class, args);
    }

    @Override
    public void run(ApplicationArguments args) throws Exception {
        try (Connection connection = connectionFactory.createConnection();
             Session session = connection.createSession(Session.AUTO_ACKNOWLEDGE)) {

            Queue queue = session.createQueue("demo.lifecycle");

            try (MessageProducer producer = session.createProducer(queue);
                 MessageConsumer consumer = session.createConsumer(queue)) {

                connection.setExceptionListener(error ->
                    System.err.println("Asynchronous JMS error: "
                        + error.getMessage()));

                // Connection vẫn stopped, nhưng producer được phép gửi.
                producer.send(session.createTextMessage("before-start"));
                System.out.println("sent-before-start");

                connection.start(); // Cho phép consumer nhận message.
                System.out.println("received-1=" + readText(consumer.receive(5000)));

                connection.stop(); // Tạm dừng nhận, không đóng.
                producer.send(session.createTextMessage("while-stopped"));
                System.out.println("sent-while-stopped");

                connection.start(); // Cho phép nhận trở lại.
                System.out.println("received-2=" + readText(consumer.receive(5000)));
            }
        } // Đóng consumer, producer, session, connection theo thứ tự ngược.
    }

    private static String readText(Message message) throws JMSException {
        if (message instanceof TextMessage text) {
            return text.getText();
        }
        if (message == null) {
            throw new IllegalStateException("Timed out waiting for message");
        }
        throw new IllegalStateException("Expected TextMessage, got "
                + message.getClass().getName());
    }
}
~~~

Chạy trong thư mục dự án bằng Gradle/JDK 17+:

~~~bash
gradle bootRun
~~~

Với queue ban đầu **trống**, không có consumer khác tranh chấp, broker khả dụng và cấu hình đúng, các dòng từ chương trình lần lượt là:

~~~text
sent-before-start
received-1=before-start
sent-while-stopped
received-2=while-stopped
~~~

Spring Boot có thể in thêm các dòng log khi khởi động và đóng ứng dụng. Chương trình không chứng minh hành vi timeout khi stopped vì nó **không gọi `receive` trong lúc stopped**; nó chỉ chứng minh producer vẫn gửi được, và consumer nhận sau `start()`. Nếu broker chưa chạy, credentials sai, queue không tồn tại và broker không cho auto-create, hoặc queue chứa message cũ, kết quả sẽ khác hay chương trình ném lỗi. Đừng biến output demo thành cam kết về thứ tự giữa nhiều consumer.

**Tại sao dùng `try-with-resources` ở đây?** `Connection`, `Session`, `MessageProducer` và `MessageConsumer` đều mở rộng `AutoCloseable` trong Jakarta Messaging. Chúng được đóng kể cả khi `send`/`receive` ném exception, giúp tránh rò rỉ tài nguyên. Ví dụ này quản lý kết nối **riêng** cho tác vụ ngắn; không khuyến nghị tạo connection mới cho từng message trong dịch vụ tải lớn.

## 5. API rút gọn: `JMSContext` và auto-start

Jakarta Messaging 2.0+ bổ sung `JMSContext` để gộp các trách nhiệm thông thường của `Connection` và `Session`. Nó tạo producer/consumer trực tiếp và dùng exception dạng runtime. Khác với API `Connection` cổ điển, `JMSContext` mặc định **tự gọi start khi consumer đầu tiên được tạo**. Để thiết lập consumer đầy đủ trước khi nhận, có thể tắt auto-start:

~~~java
// Minh họa bổ sung; đặt trong phương thức có connectionFactory hợp lệ.
try (var context = connectionFactory.createContext()) {
    context.setAutoStart(false);
    var queue = context.createQueue("demo.lifecycle");
    try (var consumer = context.createConsumer(queue)) {
        context.createProducer().send(queue, "hello-context");
        context.start();
        String body = consumer.receiveBody(String.class, 5000);
        System.out.println(body);
    }
}
~~~

Đoạn này là **snippet** dùng cùng `ConnectionFactory` đã cấu hình; không phải file Java chạy độc lập. Bảo đảm queue đang trống/nội dung phù hợp nếu muốn nhận đúng `hello-context`.

`JMSContext.close()` đóng session và tài nguyên con của context; connection nền chỉ đóng khi không còn context khác hợp lệ đang dùng chung nó. `JMSContext` **không được chia sẻ đồng thời giữa các thread** như một API thread-safe tự động. Nếu cần xử lý song song, phân chia context/session hợp lệ cho từng luồng công việc.

## 6. Spring JMS quản lý Connection khác gì so với JMS thuần?

Một ứng dụng Spring thường **không cần** tự gọi `createConnection()`, `start()` và `close()` cho mỗi thao tác. Spring cung cấp abstraction với quyền sở hữu tài nguyên rõ ràng:

### 6.1. `JmsTemplate` — gửi/nhận theo thao tác

~~~java
// Snippet tích hợp trong Spring: inject JmsTemplate do Boot cấu hình.
@Service
public class NotificationPublisher {
    private final JmsTemplate jmsTemplate;

    public NotificationPublisher(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    public void publish(String body) {
        jmsTemplate.convertAndSend("notifications.queue", body);
    }
}
~~~

Trong snippet trên, cần import `org.springframework.stereotype.Service` và `org.springframework.jms.core.JmsTemplate`. `JmsTemplate` quản lý việc lấy/trả các tài nguyên JMS cần thiết cho lời gọi và chuyển đổi exception JMS sang exception Spring phù hợp. Tùy `ConnectionFactory`, “trả/close một handle” có thể là giải phóng tài nguyên thật hoặc **trả về cache/pool**. Đừng tạo một connection thủ công chỉ để gửi một message rồi bỏ quên nó.

### 6.2. `@JmsListener` — container sở hữu vòng đời consumer

~~~java
// Snippet Spring; bật @EnableJms trên một @Configuration thích hợp.
@Component
public class NotificationConsumer {
    @JmsListener(id = "notifications", destination = "notifications.queue")
    public void onMessage(String body) {
        System.out.println("Processed: " + body);
    }
}
~~~

Trong snippet trên cần import `org.springframework.stereotype.Component` và `org.springframework.jms.annotation.JmsListener`. Với `@EnableJms` và listener factory thích hợp, Spring tạo listener container cho method. Container chịu trách nhiệm khởi tạo consumer, start/stop tiếp nhận message, phân bổ session/worker và dọn tài nguyên khi ứng dụng đóng. Không gọi trực tiếp `Connection.stop()` từ method listener chỉ để “tạm ngừng queue”.

Khi cần điều khiển listener trong runtime, dùng `JmsListenerEndpointRegistry` và `MessageListenerContainer` theo ID đã đặt:

~~~java
// Snippet quản trị, không phải file độc lập.
MessageListenerContainer container =
        registry.getListenerContainer("notifications");
if (container != null) {
    container.stop();  // Dừng listener này qua lifecycle Spring.
    // Khi điều kiện phục hồi đã đáp ứng: container.start();
}
~~~

Cần import `org.springframework.jms.listener.MessageListenerContainer` và inject `org.springframework.jms.config.JmsListenerEndpointRegistry`. Hãy định nghĩa quyền quản trị và quy trình xử lý công việc đang chạy trước khi cho phép tác vụ runtime dừng listener.

### 6.3. `SingleConnectionFactory`, `CachingConnectionFactory` và pool

| Tầng | Mục đích | Điều cần nhớ |
| --- | --- | --- |
| Native `ConnectionFactory` | Provider trực tiếp tạo/đóng connection | Tạo quá nhiều connection thường tốn kém; lỗi và reconnect phụ thuộc provider |
| Spring `SingleConnectionFactory` | Dùng chung một connection nền; các handle có thể bỏ qua `close()` vật lý | Có ích cho thử nghiệm/ứng dụng độc lập; **không coi mỗi `createConnection` là một kết nối vật lý mới** |
| Spring `CachingConnectionFactory` | Mở rộng `SingleConnectionFactory`, cache thêm session/producer/consumer | `sessionCacheSize` điều khiển số session được giữ lại theo loại; đóng logical Session để trả cache |
| Native/JMS connection pool (ví dụ pooled-jms) | Quản lý nhiều connection/session dựa trên hạn mức | Đọc kỹ cấu hình, quy tắc mượn/trả, idle/eviction và transaction |

Spring Boot 3.x thường cấu hình `CachingConnectionFactory` bọc provider factory và cho chỉnh bằng `spring.jms.cache.*`. Ví dụ `spring.jms.cache.session-cache-size: 5` có thể phù hợp khi có nhiều thao tác đồng thời, nhưng **không phải công thức tối ưu cho mọi hệ thống**. Caching và pooling giải quyết những khía cạnh khác nhau; không xếp chồng nhiều tầng chỉ vì muốn “tăng hiệu năng”.

Spring cũng phân biệt **kết nối dùng cho producer/template** với **listener container**. Với `DefaultMessageListenerContainer`, việc lấy, giữ và làm mới connection/session/consumer phụ thuộc `cacheLevel`, transaction manager, concurrency và cơ chế recovery. Trong môi trường có transaction manager bên ngoài, mức cache phù hợp có thể khác với standalone JMS; kiểm tra cấu hình thực tế và broker.

**Quy tắc ownership:** nếu bạn chỉ inject `JmsTemplate` hoặc dùng `@JmsListener`, hãy để Spring quản lý lifecycle. Khi chủ động gọi API Jakarta JMS thuần trên provider factory, bạn chịu trách nhiệm đóng tài nguyên do code mở. Không gọi `resetConnection()` hoặc `destroy()` trên bean dùng chung như cách xử lý lỗi tạm thời nếu chưa kiểm soát toàn bộ consumer bị ảnh hưởng.

## 7. Connection, Session và transaction khác nhau thế nào?

`Connection.start()` chỉ bật việc giao message đến consumer. Nó **không** bắt đầu một transaction database và **không** thay thế acknowledge/commit của session. Xét:

~~~java
try (Connection connection = connectionFactory.createConnection();
     Session session = connection.createSession(Session.SESSION_TRANSACTED)) {

    Queue queue = session.createQueue("orders.queue");
    try (MessageProducer producer = session.createProducer(queue)) {
        producer.send(session.createTextMessage("order-created"));
        session.commit(); // Commit transaction JMS cục bộ.
    }
}
~~~

Đây là snippet minh họa **JMS local transaction**. Nếu lệnh `commit()` không chạy hoặc transaction còn mở khi `Session.close()` xảy ra, transaction JMS chưa hoàn tất sẽ bị rollback. Việc commit JMS không tự động commit một transaction database khác. Nếu phải bảo đảm “ghi order vào DB + phát event” nhất quán, cân nhắc transactional outbox hoặc cấu hình giao dịch phối hợp chuyên biệt phù hợp hạ tầng.

Với consumer ở `AUTO_ACKNOWLEDGE`, cơ chế xác nhận do JMS runtime áp dụng theo kiểu nhận và callback tương ứng. Với `CLIENT_ACKNOWLEDGE`, ứng dụng phải xác nhận hợp lệ; **đóng Connection không tự biến message chưa ack thành đã ack**. Một session đã đóng không dùng để tiếp tục nhận, commit, rollback hay acknowledge.

Nguyên tắc production thường là: xử lý trùng an toàn bằng idempotency key, quản lý redelivery/DLQ, thiết kế transaction rõ ràng. **Không dùng kết nối được start hay đóng để suy ra message đã xử lý chính xác một lần.**

## 8. Xử lý mất kết nối và phục hồi

Một connection có thể mất hiệu lực do broker restart/failover, lỗi mạng, hết hạn xác thực, quota, timeout, DNS hoặc cấu hình TLS sai. Các dấu hiệu gồm exception khi tạo session/send/receive, consumer dừng nhận, broker báo client disconnect, hoặc queue backlog tăng.

Với JMS thuần:
- `setExceptionListener(...)` cho phép nhận một số lỗi bất đồng bộ ở cấp connection. Nó **không thay thế** xử lý `JMSException` tại lời gọi `createConnection`/`send`/`receive`/`commit` và không bảo đảm callback cho mọi lỗi.
- Sau lỗi, phân loại connection còn hợp lệ hay không theo provider; dọn tài nguyên hỏng rồi tạo lại theo chiến lược recovery có kiểm soát.
- Tránh retry vô hạn và vòng lặp kết nối nóng: backoff, giới hạn attempts, jitter và alert khi hết khả năng phục hồi.
- Kiểm tra chính sách reconnect/failover của Artemis hoặc provider thực tế; JMS spec không áp đặt một thuật toán reconnect chung cho tất cả broker.

Với Spring:
- `DefaultMessageListenerContainer` có cơ chế recovery cho các lỗi listener setup và connection, tùy `recoveryInterval`/`BackOff` cùng cấu hình resource cache.
- `CachingConnectionFactory` có tùy chọn xử lý lỗi/reconnect underlying connection nhưng không bảo đảm tự khôi phục **mọi** trạng thái nghiệp vụ, session transaction, subscription hoặc message đang xử lý.
- Khi ứng dụng dừng, container tiến hành shutdown listener theo lifecycle framework. Đặt timeout chờ phù hợp với độ dài tác vụ; nếu bị kill đột ngột, message chưa được commit/ack có thể được phát lại.

**Không gán trạng thái “connected” chỉ vì còn đối tượng `Connection` trong heap.** Để biết hệ thống khỏe, kết hợp kiểm tra broker và luồng gửi/nhận thực tế theo cách quan sát được, thay vì chỉ kiểm tra bean tồn tại.

## 9. Những lỗi thường gặp trong dự án

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Producer gửi được nhưng consumer mãi không nhận | Kết nối chưa `start()`; sai queue; consumer/selector không khớp | Kiểm tra destination, trạng thái connection, selector và queue depth |
| `receive()` treo | Dùng receive không timeout khi connection stopped hoặc queue rỗng | Dùng `receive(timeout)`, kiểm tra `start()` và tách luồng nhận phù hợp |
| Broker có quá nhiều connections | Tạo connection mới cho mỗi message mà không đóng hoặc không pooling | Dùng lại `ConnectionFactory` và `JmsTemplate`/pool; đóng tài nguyên manual |
| Lúc chạy nhiều thread có lỗi khó tái hiện | Dùng chung một `Session`/`JMSContext` đồng thời | Tạo session/context riêng cho mỗi luồng xử lý |
| `close()` khiến listener khác ngừng nhận | Đóng shared connection của framework/pool | Không tự đóng physical connection do Spring quản lý |
| Listener không hồi phục sau broker restart | Cache/recovery/failover không phù hợp | Kiểm tra listener container, backoff, broker HA và logs |
| Message xuất hiện trở lại sau restart | Transaction chưa commit hoặc message chưa ack | Đảm bảo commit/ack đúng và consumer idempotent |
| Stop listener nhưng vẫn thấy tác vụ hoàn tất | Một callback đã chạy trước khi stop và được phép hoàn tất | Phân biệt “không nhận message mới” với “hủy tác vụ đang chạy” |

Các lỗi này cần được đánh giá cùng cấu hình broker và transaction hiện hành, không nên “sửa” bằng tăng `sessionCacheSize`/thread count một cách tùy tiện.

## 10. Checklist cấu hình và vận hành

Khi cấu hình JMS trong Spring, hãy xác nhận:
- **Ownership:** connection do code, Spring container, application server hay pool sở hữu?
- **Start/stop:** listener nào được tự động start; lúc bảo trì muốn dừng consumer nào; có cần chờ in-flight task không?
- **Concurrency:** số consumer và session tối đa; một session không chia sẻ giữa các worker; phù hợp giới hạn broker/database.
- **Tài nguyên:** số connection vật lý, session cache, idle timeout và thời điểm đóng khi shutdown.
- **Khả dụng:** broker endpoints, TLS/auth, failover/reconnect, backoff, quota và alert khi không thể tạo connection.
- **Tin cậy:** transaction/acknowledge, retry, DLQ, duplicate handling, idempotency và message retention.
- **Quan sát:** connection count, active consumers, send/receive error, thời gian hồi phục, queue depth/age, số message redelivered và DLQ.

### Câu hỏi tự kiểm tra

1. Vì sao tạo `Connection` chưa đủ để `MessageConsumer.receive(...)` trả message?
2. Nếu connection đã `stop()`, producer còn `send()` được không? `stop()` có xóa message đang nằm ở broker không?
3. Sau `Connection.close()` có thể gọi `start()` trên chính object đó để dùng tiếp không?
4. Vì sao đưa một `Session` vào nhiều thread cùng lúc là lỗi, dù các thread cùng dùng một `Connection`?
5. `JmsTemplate`/`@JmsListener` làm thay đổi trách nhiệm quản lý `Connection` của lập trình viên như thế nào?
6. Vì sao `Session.commit()` hoặc `Connection.close()` không tương đương với việc “đã commit toàn bộ nghiệp vụ trong database”?

**Ghi nhớ:** `ConnectionFactory` cấp connection; `Connection.start()/stop()` điều khiển **giao message tới consumer**; `Connection.close()` kết thúc tài nguyên; `Session` kiểm soát acknowledgement/transaction JMS; còn trong Spring, template và listener container thường nhận trách nhiệm vòng đời thay cho code ứng dụng.

## Tài liệu tham khảo

- Jakarta Messaging 3.1 Specification (sections Connections, Sessions, JMSContext): https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
- Jakarta Messaging 3.1 API – Connection: https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/connection
- Spring Framework – Using Spring JMS: https://docs.spring.io/spring-framework/reference/integration/jms/using.html
- Spring Framework – Annotation-driven JMS Listener Endpoints: https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html
- Spring Boot – JMS & ActiveMQ Artemis: https://docs.spring.io/spring-boot/3.4/reference/messaging/jms.html
