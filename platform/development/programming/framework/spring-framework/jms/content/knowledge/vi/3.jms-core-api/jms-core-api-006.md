# MessageConsumer và thao tác nhận trong Jakarta JMS / Spring JMS

## 1. Mục tiêu bài học

`MessageConsumer` là giao diện của Jakarta Messaging (JMS) dùng để **nhận message từ một destination** (`Queue` hoặc `Topic`). Một consumer được tạo trong một `Session`, gắn với destination và có thể nhận theo hai kiểu:

- **Đồng bộ:** code chủ động gọi `receive()`, `receive(timeout)` hoặc `receiveNoWait()`.
- **Bất đồng bộ:** đăng ký `MessageListener` để JMS provider gọi `onMessage(Message)` khi có message.

Trong Spring Framework, bạn vẫn cần hiểu `MessageConsumer` để nắm chính xác cơ chế nhận, thời gian chờ, vòng đời kết nối, acknowledgment và transaction. Tuy vậy, code nghiệp vụ thường dùng `JmsTemplate` để nhận đồng bộ hoặc `@JmsListener` để nhận bất đồng bộ; Spring quản lý nhiều tài nguyên JMS thay cho ứng dụng.

Bài này tập trung vào **API nhận message** và những điều kiện khiến một message được giao, được xác nhận, được giao lại hoặc không được nhận ngay. Các ví dụ sử dụng **Jakarta Messaging 3.x, Java 17+ và Spring Boot 3.5.x**; package Java là `jakarta.jms`, không phải `javax.jms` của hệ Java EE/JMS cũ.

## 2. MessageConsumer nằm ở đâu trong kiến trúc JMS?

Một luồng nhận tiêu biểu:

~~~mermaid
flowchart LR
    P["MessageProducer"] --> D[("Queue / Topic")]
    D --> C["MessageConsumer"]
    C --> R{"Cách nhận"}
    R --> S["receive(...) trong thread gọi"]
    R --> A["MessageListener.onMessage(...)"]
    C --- SE["Session"]
    SE --- CO["Connection"]
    CO --- F["ConnectionFactory"]
~~~

- **`ConnectionFactory`** tạo kết nối đến JMS provider/broker.
- **`Connection`** đại diện cho kết nối JMS, có trạng thái bắt đầu/tạm dừng giao message. `connection.start()` cho phép giao message đến consumer; chỉ tạo consumer chưa đủ.
- **`Session`** là ngữ cảnh một luồng logic để tạo message, producer và consumer; đồng thời chứa chế độ acknowledgment và transaction.
- **`Destination`** là `Queue` hoặc `Topic`. `Session.createQueue("orders.queue")` tạo đối tượng biểu diễn tên đích; **không nhất thiết tạo queue vật lý trên broker**. Việc provision/auto-create tùy provider.
- **`MessageConsumer`** đăng ký quan tâm đến một destination; tùy trường hợp có message selector. Consumer nhận một `Message` và xử lý dữ liệu cùng metadata.

Ví dụ Queue: nếu có nhiều consumer độc lập trên cùng queue, chúng cạnh tranh những lần giao message. Ví dụ Topic: các subscription có thể nhận bản sao tương ứng. `MessageConsumer` dùng được cho cả hai nhưng cách tồn tại của message/subscription và fan-out khác nhau.

Một consumer gắn với `Session` đã tạo ra nó; không dùng nó như một đối tượng độc lập có thể chia sẻ tùy ý giữa thread hay ứng dụng.

## 3. Tạo MessageConsumer đúng cách

Trong API cổ điển (vẫn là API chuẩn của Jakarta Messaging 3.x):

~~~java
import jakarta.jms.Connection;
import jakarta.jms.ConnectionFactory;
import jakarta.jms.MessageConsumer;
import jakarta.jms.Queue;
import jakarta.jms.Session;

// Đoạn minh họa bên trong method đã có ConnectionFactory factory:
try (Connection connection = factory.createConnection();
     Session session = connection.createSession(
             false, Session.AUTO_ACKNOWLEDGE)) {

    Queue queue = session.createQueue("orders.queue");
    try (MessageConsumer consumer = session.createConsumer(queue)) {
        connection.start();
        // Gọi consumer.receive(...) hoặc đăng ký MessageListener.
    }
}
~~~

Đoạn trên cần `factory` đã được khởi tạo và queue có sẵn trên broker, nên **không phải chương trình Java độc lập**. Nó minh họa thứ tự khởi tạo, bắt đầu nhận và đóng tài nguyên.

Các overload cần biết:

| Lời gọi của `Session` | Công dụng |
| --- | --- |
| `createConsumer(destination)` | Nhận message từ destination không có selector. |
| `createConsumer(destination, selector)` | Chỉ nhận những message phù hợp biểu thức selector trên header/property. |
| `createConsumer(destination, selector, noLocal)` | Thêm tùy chọn không nhận message do chính connection phát; **`noLocal` có ý nghĩa với Topic**, không phải cách lọc Queue theo ứng dụng gửi. |
| `createDurableConsumer(topic, name)` | Consumer cho durable Topic subscription, có các điều kiện về subscription/client ID. |
| `createSharedConsumer(topic, name)` / `createSharedDurableConsumer(...)` | Shared Topic subscription, cho phép nhiều consumer chia một subscription. |

Đừng nhầm `session.createConsumer(queue)` với `connection.createConsumer(...)`: consumer cổ điển được tạo bởi **`Session`**. Nếu dùng API đơn giản hóa, `JMSContext` tạo **`JMSConsumer`** — một interface khác, xem mục 10.

### 3.1. Thời điểm gọi `connection.start()`

Thông thường:

1. Tạo `Connection`.
2. Tạo `Session`.
3. Tạo `MessageConsumer` và, nếu cần, `setMessageListener`.
4. Gọi `connection.start()`.
5. Nhận/ xử lý message; cuối cùng đóng tài nguyên.

Connection mới tạo thường ở trạng thái **stopped** đối với việc giao message. Producer vẫn có thể gửi khi connection chưa `start()`; thao tác `start()` điều khiển luồng **giao đến consumer**, không phải một bước “kết nối tới máy chủ” mới. `connection.stop()` tạm dừng delivery và `start()` cho tiếp tục; `close()` giải phóng kết nối.

Đối với listener, hãy hoàn tất việc tạo consumer/đăng ký listener **trước khi start**, nhất là khi nhiều listener dùng chung một session. Session có các ràng buộc nghiêm ngặt về thread (mục 7).

## 4. Ba phương thức nhận đồng bộ

`MessageConsumer` trả về đối tượng `jakarta.jms.Message` hoặc `null` theo điều kiện của API:

| Phương thức | Hành vi | Khi nên dùng |
| --- | --- | --- |
| `receive()` | Chờ vô thời hạn cho đến khi có message hoặc consumer bị đóng. | Worker chủ động chờ, có cơ chế shutdown/interrupt ở mức thiết kế. |
| `receive(5000)` | Chờ tối đa khoảng 5.000 ms. Trả `null` nếu hết thời gian hoặc consumer bị đóng trước khi nhận. | Polling có giới hạn, job theo lịch, xử lý có deadline. |
| `receive(0)` | **Cũng chờ vô thời hạn**, không phải non-blocking. | Tránh dùng nhầm khi muốn thăm dò tức thời. |
| `receiveNoWait()` | Trả ngay message nếu đang khả dụng, nếu không trả `null`. | Kiểm tra không chặn thread; không bảo đảm message sẽ không xuất hiện ngay sau đó. |

Đơn vị `timeout` của `receive(long)` là **mili giây**. `null` cho biết *lần gọi này không nhận được message*; không có nghĩa queue trống vĩnh viễn, một producer chưa từng gửi, hay message đã bị mất. Với Queue có nhiều consumer, message có thể vừa được giao cho consumer khác.

Ví dụ xử lý đúng `null` và loại payload:

~~~java
// Fragment trong method đã có MessageConsumer consumer:
Message message = consumer.receive(2_000);

if (message == null) {
    System.out.println("Chưa có message trong 2 giây");
} else if (message instanceof jakarta.jms.TextMessage text) {
    System.out.println("Nhận: " + text.getText());
} else {
    System.out.println("Loại message khác: "
            + message.getClass().getSimpleName());
}
~~~

`receive()` và `receive(timeout)` là thao tác **blocking** trên thread gọi; đừng gọi không thời hạn trên request thread của HTTP server. `receiveNoWait()` không tiêu tốn thời gian đợi message nhưng gọi liên tục trong vòng lặp không nghỉ có thể trở thành *busy polling*. Nếu cần xử lý liên tục theo sự kiện, ưu tiên listener bất đồng bộ.

### 4.1. Đọc body và metadata

Message nhận được có kiểu cụ thể: `TextMessage`, `BytesMessage`, `MapMessage`, `ObjectMessage`, v.v. Có thể dùng `message.getBody(String.class)` cho nội dung tương thích (ví dụ `TextMessage`). Nếu loại body không phù hợp, API có thể ném `MessageFormatException`; không ép mọi message thành chuỗi.

Các trường hữu ích khi chẩn đoán gồm:

- `getJMSMessageID()`: định danh do JMS provider gán khi gửi (nếu bật).
- `getJMSCorrelationID()`: nối message với request/response hoặc dòng xử lý liên quan.
- `getJMSRedelivered()`: cờ cho biết message có thể đã được giao trước đó.
- `getJMSReplyTo()`: destination có thể dùng để trả lời.
- `getJMSTimestamp()`, `getJMSExpiration()`, `getJMSPriority()`, `getJMSDeliveryMode()`: thông tin thời gian/chính sách giao.
- `getStringProperty("region")`, `getIntProperty("attempt")`, `getIntProperty("JMSXDeliveryCount")`: đọc custom/JMS properties nếu có.

**Không dùng `JMSMessageID` thay thế tuyệt đối khóa nghiệp vụ chống xử lý trùng.** Producer có thể gửi lại cùng nghiệp vụ trong một message mới mang JMS ID mới. Nên có `eventId` ổn định theo nghiệp vụ.

## 5. Ví dụ chạy được: nhận đồng bộ và bất đồng bộ bằng MessageConsumer

Ví dụ sử dụng **Spring Boot chỉ để cấu hình `ConnectionFactory` và khởi động ActiveMQ Artemis embedded**; thao tác tạo `Session`, `MessageProducer` và `MessageConsumer` đều thực hiện bằng **Jakarta JMS API**, giúp thấy rõ vòng đời thật.

Yêu cầu: **Java 17+, Maven 3.6.3+**. Cấu trúc:

~~~text
message-consumer-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/jmsconsumer/
    │   └── MessageConsumerDemoApplication.java
    └── resources/application.properties
~~~

### 5.1. Maven

`pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>message-consumer-demo</artifactId>
    <version>1.0.0</version>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-artemis</artifactId>
        </dependency>
        <dependency>
            <groupId>org.apache.activemq</groupId>
            <artifactId>artemis-jakarta-server</artifactId>
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
~~~

Spring Boot quản lý phiên bản Artemis từ dependency BOM. Starter cấp JMS client và cơ chế auto-configuration; `artemis-jakarta-server` phục vụ broker nhúng.

### 5.2. Cấu hình

`src/main/resources/application.properties`:

~~~properties
spring.artemis.mode=embedded
spring.artemis.embedded.queues=demo.sync,demo.async
spring.artemis.embedded.persistent=false
spring.main.banner-mode=off
~~~

Hai queue độc lập tránh việc consumer đồng bộ “giành” message của phần bất đồng bộ. Persistence tắt có chủ ý để thực hành; **không dùng demo này làm bằng chứng cho khả năng giữ message khi broker restart**.

### 5.3. Mã Java hoàn chỉnh

`src/main/java/com/example/jmsconsumer/MessageConsumerDemoApplication.java`:

~~~java
package com.example.jmsconsumer;

import jakarta.jms.Connection;
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.MessageConsumer;
import jakarta.jms.MessageProducer;
import jakarta.jms.Queue;
import jakarta.jms.Session;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

@SpringBootApplication
public class MessageConsumerDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(MessageConsumerDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner runDemo(ConnectionFactory factory) {
        return args -> {
            receiveSynchronously(factory);
            receiveAsynchronously(factory);
        };
    }

    private static void receiveSynchronously(ConnectionFactory factory)
            throws JMSException {

        try (Connection connection = factory.createConnection();
             Session session =
                     connection.createSession(false, Session.AUTO_ACKNOWLEDGE)) {

            Queue queue = session.createQueue("demo.sync");

            try (MessageProducer producer = session.createProducer(queue);
                 MessageConsumer consumer = session.createConsumer(queue)) {

                producer.send(session.createTextMessage("HELLO-SYNC"));
                connection.start();

                Message message = consumer.receive(5_000);
                if (message == null) {
                    throw new IllegalStateException("Timeout waiting for demo.sync");
                }

                System.out.println("sync: " + message.getBody(String.class));

                Message other = consumer.receiveNoWait();
                System.out.println("no-wait empty: " + (other == null));
            }
        }
    }

    private static void receiveAsynchronously(ConnectionFactory factory)
            throws JMSException, InterruptedException {

        CountDownLatch delivered = new CountDownLatch(1);
        AtomicReference<JMSException> callbackError = new AtomicReference<>();

        try (Connection connection = factory.createConnection();
             Session session =
                     connection.createSession(false, Session.AUTO_ACKNOWLEDGE)) {

            Queue queue = session.createQueue("demo.async");

            try (MessageProducer producer = session.createProducer(queue);
                 MessageConsumer consumer = session.createConsumer(queue)) {

                // Đăng ký callback TRƯỚC khi bắt đầu giao message.
                consumer.setMessageListener(message -> {
                    try {
                        System.out.println(
                                "async: " + message.getBody(String.class));
                    } catch (JMSException exception) {
                        callbackError.set(exception);
                        throw new IllegalStateException(exception);
                    } finally {
                        delivered.countDown();
                    }
                });

                producer.send(session.createTextMessage("HELLO-ASYNC"));
                connection.start();

                if (!delivered.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                            "Timeout waiting for async callback");
                }
                if (callbackError.get() != null) {
                    throw new IllegalStateException(
                            "Callback failed", callbackError.get());
                }
            }
        }
    }
}
~~~

**Giải thích chi tiết:**

1. `ConnectionFactory` do Spring Boot tạo được inject vào `ApplicationRunner`.
2. Mỗi phương thức dùng **Connection + Session riêng** và có một consumer, rồi đóng bằng `try-with-resources`.
3. `producer.send(...)` thực hiện trước `connection.start()` để chắc chắn message đã được gửi vào queue trước khi phần nhận chạy.
4. `receive(5_000)` có timeout để ứng dụng không treo vô thời hạn nếu cấu hình/broker lỗi.
5. `receiveNoWait()` kiểm tra ngay queue `demo.sync` sau khi đã nhận message duy nhất.
6. Ví dụ bất đồng bộ đăng ký `setMessageListener`, rồi `start()`. Provider gọi callback trên luồng delivery của session; thread gọi không cần tự vòng lặp `receive`.
7. `CountDownLatch` giúp chương trình demo chờ callback tối đa năm giây trước khi đóng consumer. Việc callback chạy xong và việc broker xác nhận delivery là hai thời điểm logic liên quan nhưng không phải một phép đo cam kết nghiệp vụ.
8. Dấu lỗi callback được giữ để báo lỗi về luồng chạy demo. Trong ứng dụng sản xuất cần chiến lược xử lý lỗi, transaction và redelivery cụ thể.

Chạy tại thư mục `message-consumer-demo`:

~~~bash
mvn spring-boot:run
~~~

Ngoài các log khởi động Spring/Artemis, với broker demo mới và không có producer khác, sẽ xuất hiện các dòng ứng dụng:

~~~text
sync: HELLO-SYNC
no-wait empty: true
async: HELLO-ASYNC
~~~

Đây là **các dòng do mã ứng dụng in**, không phải toàn bộ stdout của Maven/Spring Boot. Dòng `async` được in từ callback; `CountDownLatch` chỉ phối hợp thời điểm kết thúc demo, không làm callback trở thành gọi đồng bộ theo nghĩa JMS.

## 6. Nhận bất đồng bộ với MessageListener

`setMessageListener(MessageListener listener)` yêu cầu provider gửi message tới `listener.onMessage(Message)` khi connection cho phép delivery. Khi không còn cần listener, đóng consumer hoặc tài nguyên bao ngoài. `getMessageListener()` đọc listener đã đăng ký; `getMessageSelector()` đọc selector mà consumer đang dùng.

### 6.1. Callback khác gì vòng lặp receive?

| Nhận đồng bộ | Nhận bất đồng bộ |
| --- | --- |
| Ứng dụng gọi `receive` để lấy message. | JMS provider gọi `onMessage` khi có message. |
| Thread gọi có thể bị chặn chờ message. | Thread gọi có thể làm việc khác; callback chạy trong ngữ cảnh giao của provider. |
| Dễ tạo quy trình “lấy một message rồi trả kết quả”. | Thích hợp cho worker phản ứng liên tục với sự kiện. |
| Ứng dụng phải chủ động tổ chức vòng lặp/polling. | Provider/container điều phối delivery; ứng dụng quản lý lifecycle. |

**Không trộn `receive()` và listener trên cùng `Session`.** Đặc tả JMS coi Session là ngữ cảnh đơn luồng logic: khi có listener nhận bất đồng bộ, session được dành cho luồng giao và không được đồng thời sử dụng nhận đồng bộ. Việc thay đổi listener ngay khi consumer đang nhận cũng có hành vi không được định nghĩa; hãy cấu hình trước `connection.start()`.

Nếu callback thực hiện công việc chậm, các message khác **trên cùng session** phải chờ vì session tuần tự hóa việc gọi listener. Muốn xử lý song song cần nhiều session/consumer; một connection có thể chứa nhiều session nhưng phải tôn trọng giới hạn thread của từng session. Spring listener container có thể cung cấp cơ chế concurrency thay cho tự tạo thread.

### 6.2. Xử lý lỗi callback

`MessageListener.onMessage` không khai báo `throws JMSException`, vì vậy lỗi checked khi đọc message phải được bắt. **Đừng chỉ catch exception, ghi log rồi return bình thường** nếu điều đó khiến provider/container coi message đã được xử lý thành công.

Cần tách hành vi giữa Jakarta JMS thuần và Spring container:

- Với **JMS thuần**, việc `onMessage` ném `RuntimeException` ảnh hưởng tùy acknowledge mode; riêng **transacted Session không tự rollback chỉ vì `onMessage` ném RuntimeException**. Ứng dụng phải quản lý `commit()/rollback()` theo đúng ngữ cảnh của session.
- Với **Spring `DefaultMessageListenerContainer` được cấu hình session transacted**, exception thoát khỏi listener thường khiến container rollback JMS transaction và broker thực hiện redelivery theo chính sách.
- Với `AUTO_ACKNOWLEDGE`, acknowledgment diễn ra khi `receive` thành công trả về hoặc listener **hoàn thành thành công**; không nên đánh đồng với việc mọi thao tác bên ngoài (DB, HTTP) đã commit.
- Với callback xử lý dài hoặc không ổn định, nên dùng timeout, quan sát xử lý, DLQ và idempotency. Chính sách số lần retry/độ trễ thuộc broker.

### 6.3. Consumer.close() có tác dụng gì?

`consumer.close()` dừng delivery đến consumer và giải phóng tài nguyên provider. Nếu thread khác đang thực hiện `receive()`, thao tác đóng phải chờ receive kết thúc; receive đang chờ có thể trả `null` khi consumer bị đóng. Nếu listener đang chạy, đóng phải đợi callback đó kết thúc. `close()` là phương thức duy nhất trên `MessageConsumer` được đặc tả cho phép gọi đồng thời theo cách này.

Đóng consumer **không tự commit JMS transaction và không tự acknowledge mọi message chưa xử lý**. Trạng thái acknowledgment/transaction thuộc `Session`. Khi xong, cũng đóng session/connection hoặc để Spring container quản lý. Tránh đóng chính connection/session từ trong callback theo cách khiến khóa hoặc hành vi provider khó dự đoán.

## 7. Session, acknowledgment và transaction khi nhận

`MessageConsumer` không quyết định independently rằng một message “đã xử lý”. Quyết định được đặt trong **`Session`**, mode của session và transaction.

| Chế độ `Session` | Khi nào xác nhận message? | Hệ quả |
| --- | --- | --- |
| `AUTO_ACKNOWLEDGE` | Sau `receive` trả thành công hoặc sau `onMessage` trả thành công. | Đơn giản; nếu update DB sau `receive` mà lỗi, message có thể đã được ack. |
| `CLIENT_ACKNOWLEDGE` | Ứng dụng gọi `message.acknowledge()`. | Một lần ack có thể xác nhận **tất cả message đã được giao trong cùng session**. |
| `DUPS_OK_ACKNOWLEDGE` | Provider có thể trì hoãn ack. | Giảm overhead trong vài tình huống nhưng chấp nhận giao lại nhiều hơn. |
| `SESSION_TRANSACTED` | `session.commit()` xác nhận các message đã nhận trong transaction; `rollback()` hủy phần xử lý JMS của transaction và cho phép giao lại. | Phù hợp khi cần kiểm soát ranh giới nhận/xử lý; không tự gộp transaction DB bên ngoài. |

### 7.1. Vì sao AUTO_ACKNOWLEDGE có thể quá sớm?

Trong nhận **đồng bộ**, ngay sau khi `consumer.receive(...)` trả thành công, JMS có thể đã xác nhận delivery. Nếu code sau đó ghi DB mà gặp lỗi, broker có thể không còn message để retry. Trong nhận **bất đồng bộ**, acknowledgment thường ở cuối callback thành công, nhưng không biến giao dịch DB thành một phần của transaction JMS.

Với tác vụ cần retry đáng tin cậy, cân nhắc transacted session, Spring transacted listener container, hoặc phối hợp transaction thích hợp thay vì mặc định dùng `AUTO_ACKNOWLEDGE`.

### 7.2. CLIENT_ACKNOWLEDGE: phạm vi ack là toàn session

Ví dụ minh họa trong method đã sở hữu session và queue; **fragment, không phải chương trình độc lập**:

~~~java
Session session = connection.createSession(
        false, Session.CLIENT_ACKNOWLEDGE);
MessageConsumer consumer = session.createConsumer(queue);

// Sau khi connection.start() ở đúng thời điểm:
Message first = consumer.receive(3_000);
if (first != null) {
    // Thực hiện xử lý nghiệp vụ thành công trước.
    first.acknowledge();
}
~~~

Nếu session đã nhận nhiều message chưa ack, `acknowledge()` trên một message có thể xác nhận **toàn bộ message mà session đã tiêu thụ**, không chỉ đối tượng `first`. Khi muốn yêu cầu giao lại các message chưa ack trong session không transacted, API cung cấp `session.recover()` (cần hiểu các hạn chế về threading/ngữ cảnh listener).

### 7.3. Transacted receive: commit hoặc rollback

Ví dụ fragment để hiểu điểm đặt transaction:

~~~java
// Minh họa các bước trong method đã tạo Connection connection
// và Queue queue, có xử lý nghiệp vụ process(message).
Session tx = connection.createSession(true, Session.SESSION_TRANSACTED);
MessageConsumer consumer = tx.createConsumer(queue);
connection.start();

Message message = consumer.receive(5_000);
if (message != null) {
    try {
        process(message);   // Hàm nghiệp vụ do ứng dụng định nghĩa.
        tx.commit();        // Xác nhận nhận message trong JMS transaction.
    } catch (Exception exception) {
        tx.rollback();      // Cho phép redelivery theo chính sách provider.
        throw exception;
    }
}
~~~

Đoạn này **không độc lập** vì `connection`, `queue`, `process` là thành phần do ứng dụng cung cấp và cần xử lý đóng tài nguyên ở phạm vi bao ngoài. Trong transacted session, tham số acknowledge mode thông thường bị bỏ qua; chính commit/rollback mới điều khiển xác nhận.

Điểm cần nhớ: **local JMS transaction không tự bao gồm việc ghi JDBC, gọi REST, gửi email, thanh toán**. Ví dụ consumer ghi DB thành công rồi crash trước JMS commit: broker có thể giao lại message, nên cần idempotent consumer dựa trên `eventId` nghiệp vụ; khi gửi message từ DB transaction có thể cân nhắc outbox.

## 8. Message selector: nhận có điều kiện

`Session.createConsumer(destination, selector)` tạo consumer chỉ nhận message có **headers/properties phù hợp** biểu thức theo cú pháp selector của JMS (một tập con kiểu SQL-92), không đọc trực tiếp JSON/text body.

Ví dụ producer gắn property, consumer lọc:

~~~java
// Fragment: producer, session và queue đã được tạo.
TextMessage order = session.createTextMessage("ORDER-101");
order.setStringProperty("region", "VN");
order.setIntProperty("amount", 120);
producer.send(order);

// Tạo consumer trước khi connection.start().
MessageConsumer selected = session.createConsumer(
        queue, "region = 'VN' AND amount >= 100");
~~~

Trong tệp Java thật, cần import `jakarta.jms.TextMessage` cùng các API liên quan. Consumer này không nhận message chỉ có `region='US'`, hoặc property không phù hợp điều kiện. Message không khớp có thể tiếp tục đợi consumer khác; selector không “xóa” message.

Cần phân biệt:

- `region = 'VN'` truy cập **string property** `region`.
- `amount >= 100` truy cập **numeric property** `amount`.
- `NULL`/property vắng mặt và quy tắc kiểu dữ liệu có thể làm điều kiện không match.
- Muốn lọc theo trường JSON `customer.region`, hãy đưa dữ liệu lọc cần thiết thành JMS property lúc producer tạo message hoặc thiết kế queue/route riêng.
- Khi một queue có các consumer dùng selector khác nhau, phải bảo đảm mọi loại message quan trọng đều có consumer phù hợp, tránh tồn đọng vô thời hạn.
- Selector **không thay thế authorization hoặc bảo vệ dữ liệu nhạy cảm**.

`consumer.getMessageSelector()` trả biểu thức đã cấu hình hoặc `null` nếu không có selector.

## 9. Những ràng buộc về thứ tự, song song và redelivery

### 9.1. Một session không tự tạo parallel processing

Session tuần tự hóa delivery tới tất cả listener trong session đó. Hai consumer trên **cùng session** không có nghĩa là hai callback chạy đồng thời. Để tăng throughput cần **nhiều session** (thường mỗi listener/worker có session riêng), hoặc Spring `@JmsListener` kết hợp cấu hình concurrency của listener container.

Với Queue, hai consumer đồng thời có thể hoàn thành khác thứ tự bắt đầu. Với Topic, mỗi subscription có semantics riêng; số lượng message một consumer nhận còn phụ thuộc loại subscription (shared/durable/unshared), thời gian consumer tồn tại và selector.

### 9.2. Giao lại không đồng nghĩa “xử lý chính xác một lần”

Các tình huống có thể tạo redelivery/duplicate nghiệp vụ:

1. Consumer nhận message nhưng chưa commit/ack, sau đó mất kết nối.
2. Transaction bị rollback.
3. Application đã ghi DB rồi lỗi trước JMS commit.
4. Producer retry gửi một nghiệp vụ bằng message mới vì không chắc lần gửi đầu đã thành công.

Đọc `JMSRedelivered` và `JMSXDeliveryCount` để quan sát, nhưng **không dựa hoàn toàn vào cờ/đếm này để quyết định bỏ qua nghiệp vụ**. Thiết kế consumer idempotent: `eventId` ổn định, unique constraint, transactional inbox hoặc cơ chế tương đương.

### 9.3. Một số sai lầm về tài nguyên và thread

- Dùng chung `Session` giữa nhiều thread gọi `receive` cùng lúc: **sai mô hình threading**; cần session riêng.
- Đăng ký `setMessageListener` rồi tiếp tục gọi `receive` trên session đó: **không hợp lệ**.
- Dùng `receive(0)` với kỳ vọng không chờ: thực tế chờ vô thời hạn.
- Dùng `AUTO_ACKNOWLEDGE` rồi xử lý DB sau khi synchronous receive trả về, kỳ vọng broker retry khi DB lỗi: có thể mất cơ hội retry.
- Quên `connection.start()`: consumer được tạo nhưng không được giao message.
- Quên đóng consumer/session/connection: rò rỉ tài nguyên broker và thread.
- Tạo thêm consumer chỉ để “xem có message không”: có thể **lấy message ra khỏi queue**. Nếu cần quan sát không tiêu thụ, xem `QueueBrowser` hoặc chỉ số quản trị broker; browser là một API khác và chỉ phản ánh một snapshot không ổn định.
- Catch lỗi trong listener rồi return như thể thành công: có thể khiến message bị ack và không được retry theo kỳ vọng.
- Coi `createQueue("name")` là thao tác bắt buộc tạo queue vật lý: hành vi provision thuộc provider.

## 10. Từ Jakarta JMS thuần sang Spring Framework

Spring cung cấp các abstraction tiết kiệm mã quản lý lifecycle và lỗi:

| Nhu cầu | Jakarta JMS trực tiếp | Spring JMS |
| --- | --- | --- |
| Nhận đồng bộ | `MessageConsumer.receive(timeout)` | `JmsTemplate.receive(...)`, `receiveAndConvert(...)` |
| Nhận có selector | `session.createConsumer(queue, selector)` | `JmsTemplate.receiveSelected(...)` hoặc `@JmsListener(selector=...)` |
| Nhận bất đồng bộ | `consumer.setMessageListener(...)` | `@JmsListener(destination=...)` |
| Quản lý session/connection | Code ứng dụng đóng tài nguyên, quản lý concurrency | `JmsTemplate` / listener container quản lý phần lớn lifecycle |
| Transaction listener | Code tự `commit()/rollback()` trên local JMS session | Cấu hình container transacted hoặc transaction manager thích hợp |
| Chuyển đổi payload | Tự đọc `Message`/body | `MessageConverter` và mapping tham số listener |

### 10.1. JmsTemplate cho receive đồng bộ

Ví dụ trong Spring bean đã inject `JmsTemplate`:

~~~java
// Fragment trong Spring-managed bean:
jmsTemplate.setReceiveTimeout(2_000);
Object payload = jmsTemplate.receiveAndConvert("orders.queue");
if (payload == null) {
    System.out.println("Chưa nhận được message");
}
~~~

`setReceiveTimeout(2_000)` giới hạn thời gian chờ khoảng 2 giây. Với `JmsTemplate`, **0 là chờ vô thời hạn; giá trị âm như `-1` nghĩa là no-wait**. Mặc định của `JmsTemplate` là chờ vô thời hạn, nên hãy cấu hình rõ khi chạy trên thread có giới hạn thời gian. Nếu dùng `receive(...)` trả về raw `jakarta.jms.Message`; `receiveAndConvert(...)` chuyển dữ liệu thông qua converter và có thể trả về `null`.

**Lưu ý transaction:** `JmsTemplate.receiveAndConvert` nhận và chuyển dữ liệu, nhưng thời điểm commit/ack có thể đã xảy ra trước khi ứng dụng xử lý nghiệp vụ sau lời gọi. Nếu công việc phải có cùng ranh giới transaction với việc nhận, cần thiết kế transaction bao quanh logic theo cấu hình phù hợp hoặc dùng listener transacted.

### 10.2. @JmsListener cho receive bất đồng bộ

~~~java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class OrderListener {

    @JmsListener(destination = "orders.queue", concurrency = "2")
    public void onOrder(String orderId) {
        System.out.println("Received " + orderId);
    }
}
~~~

Đây là **class Spring-managed**, yêu cầu đã bật JMS listener infrastructure (ví dụ `@EnableJms`) và có `ConnectionFactory` hợp lệ. Spring tạo consumer trong listener container; bạn không gọi `connection.start()` hoặc `MessageConsumer.receive()` bằng tay.

`concurrency="2"` cho phép hai listener consumers/sessions cạnh tranh message khi destination là Queue; việc xử lý song song có thể làm thay đổi thứ tự hoàn tất. Trong ứng dụng quan trọng, cấu hình transaction/acknowledgment và retry/DLQ ở listener container và broker; ví dụ này chỉ minh họa API.

### 10.3. JMSConsumer trong simplified API

Jakarta Messaging 2.0+ còn cung cấp `JMSContext` và `JMSConsumer`, giúp giảm lượng code checked exception và thường tự start delivery khi context ở chế độ auto-start:

~~~java
// Fragment khi đã có jakarta.jms.ConnectionFactory factory.
try (jakarta.jms.JMSContext context = factory.createContext()) {
    jakarta.jms.Queue queue = context.createQueue("orders.queue");
    jakarta.jms.JMSConsumer consumer = context.createConsumer(queue);
    String body = consumer.receiveBody(String.class, 2_000);
    if (body != null) {
        System.out.println(body);
    }
}
~~~

`JMSConsumer` và `MessageConsumer` là hai giao diện khác nhau nhưng đều thực hiện vai trò nhận. `JMSContext` vẫn bao hàm session và chịu **ràng buộc thread tương tự**; auto-start không có nghĩa là có thể gọi tùy tiện từ nhiều thread. Trên Spring Boot 3.x, cả hai đều dùng package `jakarta.jms`.

## 11. Chẩn đoán lỗi khi không nhận được message

| Triệu chứng | Kiểm tra đầu tiên | Hướng xử lý |
| --- | --- | --- |
| `receive(timeout)` luôn trả `null` | Đúng queue/topic name chưa? Có `connection.start()` chưa? Selector có match không? | Xác minh tên destination, trạng thái connection, headers/properties, broker metrics. |
| `receive()` treo lâu | Không có message phù hợp; hoặc connection chưa start | Sử dụng timeout hữu hạn trong luồng tương tác; kiểm tra log và queue depth. |
| `receiveNoWait()` trả `null` dù vừa gửi | Delivery chưa sẵn sàng ngay lúc kiểm tra; message có thể đang in-flight/được consumer khác nhận | Không giả định no-wait bảo đảm quan sát message; dùng timeout ngắn khi thích hợp. |
| Listener không được gọi | Chưa đăng ký, chưa start, listener container không chạy, sai selector | Kiểm tra lifecycle và cấu hình destination. |
| Xử lý trùng sau lỗi | Rollback, kết nối gián đoạn, producer retry | Xem redelivery counters, triển khai idempotent consumer. |
| Throughput thấp | Callback chậm, chỉ một session, DB chậm, prefetch/flow control | Đo thời gian xử lý; điều chỉnh số session/consumer và downstream capacity. |
| Callback đã chạy nhưng message lại xuất hiện | Chưa ack/commit; callback ném lỗi; provider redelivery | Kiểm tra acknowledge mode, commit/rollback, DLQ/retry policy. |
| Queue tăng nhưng service vẫn online | Consumer sai selector, bị treo, downstream nghẽn, transaction lỗi | Xem queue depth, in-flight, consumer count, oldest message age và lỗi xử lý. |

Khi phân tích một message cụ thể, nên log **event ID nghiệp vụ**, JMS message ID, correlation ID, `JMSRedelivered`, `JMSXDeliveryCount` nếu có, loại message, tên destination và thời lượng xử lý. Không log payload chứa dữ liệu nhạy cảm ngoài mục đích quản trị được cho phép.

## 12. Câu hỏi luyện tập và đáp án

1. **Vì sao `receive(0)` có thể khiến request HTTP bị treo?** Vì JMS quy định timeout bằng 0 là chờ vô thời hạn. Dùng timeout dương hoặc thiết kế async.
2. **`receiveNoWait() == null` có chứng minh queue rỗng vĩnh viễn không?** Không. Nó chỉ cho biết tại thời điểm gọi không có message khả dụng cho consumer đó.
3. **Có thể dùng `setMessageListener` và `receive()` song song trong cùng session không?** Không. Session có mô hình một luồng logic; hai cơ chế không được phối hợp như vậy.
4. **Khi nào `AUTO_ACKNOWLEDGE` xác nhận message?** Khi `receive` trả thành công, hoặc listener xử lý và trả về thành công.
5. **`CLIENT_ACKNOWLEDGE` xác nhận một message hay cả session?** Lệnh ack trên message xác nhận các message đã được session tiêu thụ thuộc phạm vi ack đó; không được suy diễn luôn chỉ một message.
6. **Ném `RuntimeException` từ raw transacted `MessageListener` có tự rollback không?** Không. Ứng dụng phải quản lý JMS transaction; Spring listener container cấu hình transacted có thể rollback khi listener thất bại.
7. **Vì sao tăng consumer từ 1 lên 4 không đảm bảo thứ tự xử lý?** Các session chạy đồng thời, thời gian xử lý và redelivery khác nhau.
8. **Khi nào nên chọn `@JmsListener` thay vì tự tạo consumer?** Khi cần worker bất đồng bộ dài hạn với lifecycle, concurrency, converter và transaction được Spring quản lý.
9. **Muốn xem nội dung queue mà không lấy message ra thì dùng gì?** `QueueBrowser` hoặc công cụ quản trị broker; `MessageConsumer.receive` là thao tác tiêu thụ.
10. **Điều gì xảy ra khi đóng `MessageConsumer`?** Dừng delivery và giải phóng tài nguyên consumer; việc ack/transaction vẫn do session quản lý.

## 13. Tài liệu chuẩn

- [Jakarta Messaging 3.1 — MessageConsumer API](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/messageconsumer).
- [Jakarta Messaging 3.1 — Session API](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/session), đặc biệt acknowledgment, transactions và threading.
- [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html), các phần về synchronous/asynchronous delivery, receive và closing consumers.
- [Spring Framework — Receiving a Message](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html).
- [Spring Framework — Annotation-driven JMS Listener Endpoints](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html).
- [Spring Boot 3.5 — JMS/ActiveMQ Artemis](https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html).

**Cốt lõi cần nắm:** `MessageConsumer` là điểm nhận message, nhưng **`Session` mới xác định ack/transaction và giới hạn luồng**, còn `Connection.start()` quyết định thời điểm delivery được phép chạy. Chọn `receive(timeout)` khi cần chủ động nhận có thời hạn; chọn listener và Spring container khi xây dựng consumer bất đồng bộ dài hạn.
