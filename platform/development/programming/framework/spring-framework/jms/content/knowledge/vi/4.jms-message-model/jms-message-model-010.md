# JMSDeliveryTime và thời điểm được phép giao trong Spring JMS

## 1. Mục tiêu và bối cảnh

Trong hệ thống bất đồng bộ, không phải message nào cũng cần được xử lý ngay khi producer gửi. Ví dụ: khi đơn hàng mới được tạo, ứng dụng muốn **đợi 5 phút** rồi mới nhắc khách hoàn tất thanh toán. Producer có thể gửi một message vào broker ngay bây giờ, nhưng yêu cầu **consumer không được nhận trước thời điểm được phép**.

Jakarta Messaging (JMS) hỗ trợ điều này bằng hai khái niệm:

- **Delivery delay**: khoảng trì hoãn tối thiểu, tính bằng mili giây, được cấu hình trên producer trước khi gửi.
- **`JMSDeliveryTime`**: header chuẩn do JMS provider gán, biểu diễn **thời điểm sớm nhất** message có thể được giao đến consumer.

Sau bài học, bạn phải giải thích được cách tính `JMSDeliveryTime`, dùng `MessageProducer`/`JMSProducer`/`JmsTemplate` để cấu hình delay, phân biệt `JMSTimestamp`, `JMSExpiration` và thời điểm thực nhận, hiểu ảnh hưởng của transaction, TTL, Queue/Topic, retry, cũng như viết được ví dụ Java 17+.

**Phạm vi:** bài học nói về **thời điểm một message được phép giao** theo Jakarta Messaging và cách sử dụng từ Spring JMS. Nó không thay thế các cơ chế lên lịch nhiều ngày, quản lý deadline nghiệp vụ hay retry chuyên biệt của từng broker.

## 2. Định nghĩa chính xác của JMSDeliveryTime

`JMSDeliveryTime` là header kiểu `long` (số mili giây kể từ 00:00:00 UTC ngày 01/01/1970, tức Unix epoch), có từ JMS 2.0 và tiếp tục tồn tại trong Jakarta Messaging 3.x.

Theo đặc tả, provider xác định:

~~~text
JMSDeliveryTime = sendTime + deliveryDelay
~~~

Trong đó:

- `sendTime` là thời điểm client thực hiện send theo JMS provider, **không phải mốc transaction commit**.
- `deliveryDelay` là khoảng trì hoãn tối thiểu theo mili giây, được đặt trên producer; **mặc định 0**.
- `JMSDeliveryTime` là thời điểm **sớm nhất** mà broker được phép làm message có thể giao tới consumer.
- Consumer **không được nhận trước** mốc đó. Việc nhận đúng vào mốc đó **không được bảo đảm**.

Sơ đồ minh họa:

~~~mermaid
flowchart LR
    A["10:00:00 Producer gửi"] --> B["Broker nhận message"]
    B --> C["10:00:00–10:04:59 Chưa được giao"]
    C --> D["10:05:00 Bắt đầu được phép giao"]
    D --> E["Consumer thực nhận lúc >= 10:05:00"]
~~~

Ví dụ, `deliveryDelay = 300_000L` nghĩa là **5 phút**, không phải 300.000 giây. Nếu producer gửi lúc 10:00, message sẽ có `JMSDeliveryTime` xấp xỉ 10:05. Nó có thể được nhận lúc 10:05:00 hoặc 10:05:07, thậm chí lâu hơn khi broker/consumer chưa sẵn sàng. Không được hiểu delay là cam kết xử lý đúng phút/giây.

**Không cần `Thread.sleep` ở producer hoặc consumer.** Broker/provider chịu trách nhiệm giữ message chưa đủ điều kiện. Việc sleep ở phía consumer xảy ra **sau khi message đã được giao**, giữ thread bận và có thể kéo dài transaction/acknowledgment.

## 3. Phân biệt các mốc thời gian liên quan

| Trường hoặc mốc | Ý nghĩa | Nguồn giá trị |
| --- | --- | --- |
| `JMSTimestamp` | Thời điểm message được bàn giao cho JMS provider để gửi, không nhất thiết là thời điểm vật lý đến broker. | Provider đặt sau send; có thể bằng 0 nếu client yêu cầu tắt timestamp và provider chấp nhận. |
| `JMSDeliveryTime` | **Mốc sớm nhất** message được phép giao. | Provider tính từ thời điểm send + delivery delay. |
| `JMSExpiration` | Mốc message hết hạn khi có TTL; 0 là không có hạn theo TTL JMS. | Provider tính từ thời điểm send + time-to-live. |
| `receivedAt` | Thời điểm consumer thực tế nhận message hoặc listener bắt đầu xử lý. | Do ứng dụng ghi nhận; không phải một JMS header chuẩn. |
| Business `scheduledAt` | Deadline/thời gian mục tiêu của nghiệp vụ. | Ứng dụng lưu hoặc gửi trong message để quản lý lịch độc lập với broker. |

Ví dụ:

~~~text
sendTime         = 10:00:00
deliveryDelay    = 5 phút
timeToLive       = 30 phút

JMSTimestamp     ≈ 10:00:00
JMSDeliveryTime  = 10:05:00
JMSExpiration    = 10:30:00
receivedAt       = 10:05:08   (một lần chạy ví dụ)
~~~

Nếu `JMSExpiration != 0`, message chưa hết hạn và đủ điều kiện thời gian để giao khi:

~~~text
receivedAt >= JMSDeliveryTime
và
receivedAt < JMSExpiration
~~~

Đây mới chỉ là **điều kiện thời gian**; broker còn cần message đã commit, destination/subscription hợp lệ, consumer sẵn sàng và những điều kiện phân phối khác. Nếu `JMSExpiration == 0`, không có ràng buộc hết hạn do TTL tiêu chuẩn, nhưng policy bộ nhớ/dung lượng của broker vẫn có thể ảnh hưởng.

Đọc header trong consumer bằng API Jakarta Messaging:

~~~java
// Fragment: đã có jakarta.jms.Message message.
long earliestEpochMillis = message.getJMSDeliveryTime();
long sentEpochMillis = message.getJMSTimestamp();
long expirationEpochMillis = message.getJMSExpiration();

System.out.println(
        "earliest=" + java.time.Instant.ofEpochMilli(earliestEpochMillis));
System.out.println("sent=" + sentEpochMillis);
System.out.println("expires=" + expirationEpochMillis);
~~~

Đây là **fragment**, không phải chương trình độc lập. `JMSExpiration == 0` nghĩa là không có mốc hết hạn theo TTL; đừng chuyển 0 thành “thời điểm hết hạn thật” năm 1970. `JMSTimestamp` đôi khi bằng 0 do chính sách tắt timestamp; không lấy hiệu `JMSDeliveryTime - JMSTimestamp` làm công thức đáng tin trong mọi cấu hình.

`JMSDeliveryTime` lưu dưới dạng UTC epoch milliseconds. Muốn hiển thị giờ Việt Nam:

~~~java
// Fragment với long earliestEpochMillis đã đọc từ message.
java.time.ZonedDateTime local =
        java.time.Instant.ofEpochMilli(earliestEpochMillis)
                .atZone(java.time.ZoneId.of("Asia/Ho_Chi_Minh"));
System.out.println(local);
~~~

Múi giờ chỉ ảnh hưởng cách hiển thị; **không thay đổi thời điểm đủ điều kiện giao**.

## 4. Header do ai đặt? Cách cấu hình đúng

`Message.getJMSDeliveryTime()` dùng để **đọc** header. Header này được **JMS provider điền**, không phải thông tin client tùy ý ghi rồi bắt broker thực hiện.

| API | Vai trò | Cách dùng |
| --- | --- | --- |
| `MessageProducer.setDeliveryDelay(long)` | Đặt delay cho các send tiếp theo từ producer kiểu JMS cổ điển. | **Nên dùng** |
| `JMSProducer.setDeliveryDelay(long)` | Đặt delay khi dùng simplified API `JMSContext`. | **Nên dùng** |
| `Message.getJMSDeliveryTime()` | Đọc mốc provider đã gán. | **Nên dùng** |
| `Message.setJMSDeliveryTime(long)` | Setter cho provider điền header khi send. | **Không dùng để đặt lịch từ client** |
| `Message.DEFAULT_DELIVERY_DELAY` | Hằng số mặc định `0L`. | Dùng khi cần diễn đạt rõ |

Ví dụ **không đúng mục đích**:

~~~java
// Không dùng để tạo delayed message:
message.setJMSDeliveryTime(System.currentTimeMillis() + 60_000L);
producer.send(message);
~~~

Theo đặc tả, giá trị header mà client tự đặt trước send **không điều khiển lịch**, có thể bị provider bỏ qua/ghi đè khi gửi. Cách đúng với `MessageProducer` là:

~~~java
// Fragment: producer, message đã được tạo.
producer.setDeliveryDelay(60_000L);
producer.send(message);
~~~

Một `MessageProducer` có thể gửi nhiều message. Nếu đặt delay 60 giây, các lần send tiếp theo qua producer đó **tiếp tục dùng delay ấy**, trừ khi cấu hình lại. Nếu nhiều loại công việc có chính sách khác nhau, hãy kiểm soát vòng đời và trạng thái producer rõ ràng.

Một **send đồng bộ** thành công thì sau khi lời gọi send trả về, `JMSDeliveryTime` đã được provider gán cho đối tượng message gửi; phía consumer nhận được cùng giá trị. Nếu gọi **asynchronous send** qua `CompletionListener`, chỉ nên đọc các header provider gán **sau callback hoàn thành thành công**, vì send có thể chưa hoàn tất.

Lưu ý: quản trị broker có thể cấu hình **override** delivery delay theo chính sách nhà cung cấp. Khi đó, header được trả về phải phản ánh giá trị hiệu lực đã được provider áp dụng; không suy diễn mọi broker bắt buộc tôn trọng 100% con số yêu cầu của ứng dụng nếu đã có policy override.

## 5. Sử dụng classic Jakarta JMS API

`MessageProducer.setDeliveryDelay(long)` có từ JMS 2.0. `ConnectionFactory`, `Connection`, `Session` và `MessageConsumer` vẫn thuộc mô hình JMS cốt lõi.

~~~java
// Fragment trong method đã nhận được jakarta.jms.ConnectionFactory factory.
try (jakarta.jms.Connection connection = factory.createConnection();
     jakarta.jms.Session session =
             connection.createSession(false,
                     jakarta.jms.Session.AUTO_ACKNOWLEDGE)) {

    jakarta.jms.Queue queue = session.createQueue("orders.delayed");

    try (jakarta.jms.MessageProducer producer =
                 session.createProducer(queue);
         jakarta.jms.MessageConsumer consumer =
                 session.createConsumer(queue)) {

        producer.setDeliveryDelay(3_000L);
        jakarta.jms.TextMessage outbound =
                session.createTextMessage("ORDER-123");

        producer.send(outbound);

        long permittedAt = outbound.getJMSDeliveryTime();
        System.out.println("Eligible at: " +
                java.time.Instant.ofEpochMilli(permittedAt));

        connection.start();

        jakarta.jms.Message inbound = consumer.receive(10_000L);
        if (inbound == null) {
            throw new IllegalStateException("Không nhận được message");
        }
        System.out.println("Received: " + inbound.getBody(String.class));
    }
}
~~~

**Cách hoạt động:**

1. `createQueue("orders.delayed")` tạo đối tượng destination, không nhất thiết tạo queue vật lý. Cần cấu hình/provision queue trên broker.
2. Producer đặt delay 3 giây rồi gửi `TextMessage`.
3. Sau send thành công, header `JMSDeliveryTime` đã có thể đọc.
4. `connection.start()` cho phép giao message tới consumer, nhưng **không bỏ qua delivery delay**.
5. `receive(10_000)` chờ tối đa 10 giây kể từ lúc gọi; nó **không làm broker thay đổi `JMSDeliveryTime`**.
6. Code cần `ConnectionFactory` thật và broker đã có queue; vì thế đây là **fragment**, không phải tệp chứa `main` độc lập.

**Không nhầm `receive(timeout)` với delay:** receive timeout là khoảng consumer **chịu chờ**, còn delivery delay là khoảng broker **không được giao sớm**.

## 6. Sử dụng simplified Jakarta JMS API

Từ JMS 2.0, `JMSContext`/`JMSProducer` cung cấp cách viết gọn hơn. `JMSProducer.setDeliveryDelay` trả lại producer để hỗ trợ chain:

~~~java
// Fragment với jakarta.jms.ConnectionFactory factory.
try (jakarta.jms.JMSContext context = factory.createContext()) {
    jakarta.jms.Queue queue = context.createQueue("orders.delayed");

    jakarta.jms.JMSProducer producer = context.createProducer()
            .setDeliveryDelay(3_000L);

    jakarta.jms.TextMessage outbound =
            context.createTextMessage("ORDER-123");
    producer.send(queue, outbound);

    System.out.println(
            java.time.Instant.ofEpochMilli(outbound.getJMSDeliveryTime()));
}
~~~

`JMSProducer` nhẹ, không cần `close()` riêng; `JMSContext` là tài nguyên cần đóng. Một `JMSContext` có thể tự start delivery theo mặc định; nếu ứng dụng gọi `setAutoStart(false)`, phải khởi động đúng thời điểm trước khi nhận.

**Cảnh báo về thread:** `JMSContext` và `Session` không được chia sẻ tùy ý cho nhiều thread để gửi/nhận đồng thời. Với Spring, hãy để template/listener container quản lý tài nguyên hoặc tạo ngữ cảnh thích hợp cho từng luồng xử lý.

## 7. Ví dụ chạy được với Java 17+ và Spring Boot

Dự án sau dùng **Spring Boot 3.5.7** để tạo `ConnectionFactory` và **ActiveMQ Artemis embedded** để thử nghiệm. Mã Java vẫn dùng trực tiếp `JMSProducer` và `JMSConsumer` để đọc được header gốc. Broker nhúng chỉ để học; ví dụ cố ý tắt persistence.

Cấu trúc dự án:

~~~text
delivery-time-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/deliverytime/
    │   └── DeliveryTimeDemoApplication.java
    └── resources/
        └── application.properties
~~~

### 7.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>delivery-time-demo</artifactId>
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

Spring Boot quản lý các phiên bản dependency cần thiết; không cần hardcode thêm version của Artemis server trong ví dụ.

### 7.2. application.properties

~~~properties
spring.artemis.mode=embedded
spring.artemis.embedded.queues=orders.delayed
spring.artemis.embedded.persistent=false
spring.main.banner-mode=off
~~~

- `mode=embedded` yêu cầu broker nhúng được khởi động cùng ứng dụng.
- `queues=orders.delayed` tạo queue thử nghiệm khi broker khởi động.
- `persistent=false` có nghĩa demo **không chứng minh message sống sót qua restart**. Production cần broker riêng hoặc cấu hình persistence và capacity đúng.

### 7.3. DeliveryTimeDemoApplication.java

~~~java
package com.example.deliverytime;

import java.time.Instant;

import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSConsumer;
import jakarta.jms.JMSContext;
import jakarta.jms.JMSProducer;
import jakarta.jms.Message;
import jakarta.jms.Queue;
import jakarta.jms.TextMessage;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DeliveryTimeDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DeliveryTimeDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner demonstrateDelay(ConnectionFactory factory) {
        return args -> {
            try (JMSContext context = factory.createContext()) {
                Queue queue = context.createQueue("orders.delayed");

                try (JMSConsumer consumer = context.createConsumer(queue)) {
                    JMSProducer producer = context.createProducer()
                            .setDeliveryDelay(2_000L);

                    TextMessage outbound =
                            context.createTextMessage("ORDER-123");

                    producer.send(queue, outbound);

                    long earliest = outbound.getJMSDeliveryTime();
                    System.out.println(
                            "Earliest: " + Instant.ofEpochMilli(earliest));

                    Message incoming = consumer.receive(10_000L);
                    if (!(incoming instanceof TextMessage received)) {
                        throw new IllegalStateException(
                                "Không nhận được TextMessage đúng thời hạn");
                    }

                    long receivedAt = System.currentTimeMillis();

                    System.out.println("Payload: " + received.getText());
                    System.out.println("Same delivery time: "
                            + (received.getJMSDeliveryTime() == earliest));
                    System.out.println("Received no earlier than allowed: "
                            + (receivedAt >= received.getJMSDeliveryTime()));
                }
            }
        };
    }
}
~~~

Giải thích từng bước:

1. Spring Boot inject `ConnectionFactory` đã kết nối tới Artemis embedded vào `ApplicationRunner`.
2. `JMSContext` và `JMSConsumer` được tạo một lần trong khối `try-with-resources`; sẽ được đóng khi runner hoàn tất.
3. Producer gọi `setDeliveryDelay(2_000L)`, sau đó gửi `TextMessage`. Không có `Thread.sleep`.
4. Sau send đồng bộ thành công, `outbound.getJMSDeliveryTime()` chứa mốc sớm nhất được giao.
5. Consumer gọi `receive(10_000)`; broker chưa được giao trước delivery time. Nếu không nhận được trong 10 giây, ví dụ báo lỗi.
6. Header trên message nhận được **phải bằng** header gắn khi gửi.
7. `receivedAt >= JMSDeliveryTime` kiểm tra bất biến về mặt thời gian. Phép so sánh dùng đồng hồ hệ thống JVM; môi trường có điều chỉnh giờ bất thường có thể ảnh hưởng kết quả quan sát, dù JMS broker vẫn tuân theo quy tắc của nó.

Chạy tại thư mục `delivery-time-demo`:

~~~bash
mvn spring-boot:run
~~~

Các dòng do chương trình in có dạng (bỏ qua log khởi động Spring/Artemis):

~~~text
Earliest: 2026-10-30T03:15:20Z
Payload: ORDER-123
Same delivery time: true
Received no earlier than allowed: true
~~~

**`Earliest` ở đây chỉ là giá trị minh họa; mỗi lần chạy sẽ in một timestamp khác.** Hai dòng `true` là kết quả mong đợi với một broker bình thường và đồng hồ không bị nhảy lùi. Đừng viết test yêu cầu elapsed đúng bằng 2.000 ms: broker có thể giao muộn hơn.

### 7.4. Thực nghiệm bổ sung

- Đổi `setDeliveryDelay(2_000L)` thành `setDeliveryDelay(0L)` để thấy message đủ điều kiện ngay khi send.
- Đổi thành delay 8 giây, còn consumer `receive(1_000L)`: một lần nhận trước lúc đủ điều kiện sẽ trả `null`; nếu sau đó muốn nhận thật, gọi `receive(12_000L)` trên cùng consumer.
- Giữ delay 8 giây nhưng dùng `receiveNoWait()` ngay sau send: thường nhận `null`; đó chỉ là snapshot tức thời. Nếu send bất ngờ mất trên 8 giây thì message có thể đã đủ điều kiện khi thăm dò.
- Thử tăng backlog bằng nhiều message và làm consumer xử lý chậm: timestamp đủ điều kiện không đảm bảo hoàn tất xử lý ngay lập tức.

## 8. Spring JmsTemplate và @JmsListener

Trong Spring Framework, `JmsTemplate` quản lý hầu hết phần gửi JMS và có setter `setDeliveryDelay(long)`.

### 8.1. Bean gửi message trễ

Tạo tệp `DelayedJmsConfig.java`:

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.core.JmsTemplate;

@Configuration
public class DelayedJmsConfig {

    @Bean("delayedOrdersTemplate")
    public JmsTemplate delayedOrdersTemplate(
            ConnectionFactory connectionFactory) {
        JmsTemplate template = new JmsTemplate(connectionFactory);
        template.setDeliveryDelay(5_000L);
        return template;
    }
}
~~~

Sau đó gọi template:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Service;

@Service
public class DelayedOrderPublisher {

    private final JmsTemplate delayed;

    public DelayedOrderPublisher(
            @Qualifier("delayedOrdersTemplate") JmsTemplate delayed) {
        this.delayed = delayed;
    }

    public void publish(String orderId) {
        delayed.convertAndSend("orders.delayed", orderId);
    }
}
~~~

Đây là **hai class riêng** trong một ứng dụng Spring đã có JMS `ConnectionFactory`; cần khai báo `package` phù hợp khi đưa vào dự án. Spring đặt delivery delay trên producer được dùng cho các lần send qua template đó.

**Mặc định đáng nhớ:**

- Producer chuẩn JMS có delivery delay **0L**.
- `JmsTemplate` mặc định có thuộc tính `deliveryDelay = -1`, nghĩa là **không truyền override** đến broker. `-1` là sentinel nội bộ của Spring, **không phải delay âm hợp lệ gửi tới JMS producer**.
- `JmsTemplate.setExplicitQosEnabled(true)` là công tắc dùng các giá trị delivery mode, priority và TTL do template cấu hình; delivery delay có setter riêng và **không phụ thuộc phải bật công tắc ấy**.

`JmsTemplate` thường được dùng chung giữa các thread sau khi cấu hình. **Không thay đổi `setDeliveryDelay` liên tục ngay trước từng `convertAndSend` trên một shared bean**: request song song có thể dùng nhầm giá trị của nhau. Nếu cần nhiều khoảng delay, cấu hình nhiều template/producer theo chính sách hoặc dùng một producer riêng chỉ trong phạm vi thao tác gửi.

### 8.2. Consumer Spring không phải tự canh giờ

~~~java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class DelayedOrderListener {

    @JmsListener(destination = "orders.delayed")
    public void onMessage(String orderId) {
        System.out.println("Order ready: " + orderId);
    }
}
~~~

Listener này cần hạ tầng `@JmsListener` được bật và `ConnectionFactory` hoạt động. Spring container tạo consumer và broker giao message khi đủ điều kiện; listener **không tự so sánh đồng hồ hay `sleep`** để thực thi delay ban đầu.

Những ví dụ của mục 8 minh họa cách ghép vào hệ thống đã có Spring; ví dụ độc lập tự chạy đầy đủ nằm ở mục 7. Khi xử lý nghiệp vụ quan trọng, cấu hình transaction/acknowledgment, idempotency, retry và DLQ riêng.

## 9. Delivery delay và Time-to-live (TTL)

**Delivery delay** trả lời “sớm nhất **khi nào được giao**?”. **TTL** trả lời “message **khi nào hết hạn**?”. Cả hai được tính từ thời điểm send, không phải từ lúc consumer bắt đầu nghe.

| Gửi lúc | Delay | TTL | Ý nghĩa |
| --- | --- | --- | --- |
| 10:00 | 5 phút | 30 phút | Được phép giao từ 10:05; hết hạn 10:30. |
| 10:00 | 5 phút | 2 phút | Hết hạn 10:02 trước khi đủ điều kiện 10:05; consumer không được nhận message đã hết hạn. |
| 10:00 | 0 | 0 | Đủ điều kiện ngay; không có hạn theo TTL JMS. |
| 10:00 | 10 phút | 0 | Được phép giao từ 10:10; không hết hạn theo TTL JMS. |

Cấu hình trực tiếp qua `MessageProducer`:

~~~java
// Fragment với MessageProducer producer, Message message đã được tạo.
producer.setDeliveryDelay(5 * 60_000L);
producer.setTimeToLive(30 * 60_000L);
producer.send(message);
~~~

Cấu hình qua `JMSProducer`:

~~~java
// Fragment với JMSProducer producer, Queue queue đã được tạo.
producer.setDeliveryDelay(5 * 60_000L)
        .setTimeToLive(30 * 60_000L)
        .send(queue, "ORDER-456");
~~~

Giá trị `setTimeToLive(0L)` nghĩa là **không hết hạn theo TTL**, không phải “hết hạn lập tức”. Provider xác định `JMSExpiration` khi send; message hết hạn không được tiếp tục giao. Một số broker có **expiry address/expiry queue** hoặc quy định xóa message hết hạn; cần cấu hình rõ để không tưởng nhầm hết hạn là xử lý thành công.

**Thiết kế đúng:** TTL phải dài đủ cho **delay + thời gian broker/consumer có thể phải chờ + biên dự phòng xử lý chậm**. Nếu TTL ngắn hơn delay, message sẽ hết hạn trước khi có cơ hội giao. Nếu TTL bằng delay, message có thể hết hạn đúng lúc đến mốc cho phép, nên cũng không đáng tin cho nghiệp vụ phải chạy.

## 10. Transaction: tính từ send, không tính từ commit

Đặc tả Jakarta Messaging có quy tắc rõ: với send trong transaction, **delivery time được tính từ thời điểm client gửi message**, không phải từ lúc JMS transaction commit.

Ví dụ A:

~~~text
10:00  send M1, delay 5 phút => JMSDeliveryTime = 10:05
10:02  commit transaction
10:05  M1 bắt đầu đủ điều kiện giao
~~~

Ví dụ B:

~~~text
10:00  send M2, delay 5 phút => JMSDeliveryTime = 10:05
10:05  thời điểm đủ điều kiện đã qua
10:07  mới commit transaction
10:07+ M2 có thể được giao; không phải chờ thêm 5 phút
~~~

Có thể hình dung thời điểm sớm nhất về thực tế là **sau khi cả hai điều kiện đều thỏa**: message đã được commit và đã đến `JMSDeliveryTime`. Nếu transaction rollback, message gửi trong transaction đó không được công bố, cho dù tính toán header ban đầu ra mốc nào.

Ví dụ fragment trong method đã có `jakarta.jms.Connection connection` và `jakarta.jms.Queue queue`:

~~~java
jakarta.jms.Session session = connection.createSession(
        true, jakarta.jms.Session.SESSION_TRANSACTED);

try {
    try (jakarta.jms.MessageProducer producer =
                 session.createProducer(queue)) {

        producer.setDeliveryDelay(60_000L);
        jakarta.jms.TextMessage message =
                session.createTextMessage("ORDER-789");

        producer.send(message);

        long eligibleAt = message.getJMSDeliveryTime();
        session.commit();

        System.out.println("Eligible: " +
                java.time.Instant.ofEpochMilli(eligibleAt));
    }
} finally {
    session.close();
}
~~~

**Lưu ý:** local JMS transaction khác DB transaction. Gọi `@Transactional` với transaction manager cho JDBC không tự bao gồm một JMS send. Nếu yêu cầu “trì hoãn đúng 5 phút sau khi DB commit”, cần mô hình phối hợp rõ (ví dụ transactional outbox phát sau commit, hoặc scheduler quản lý deadline), không suy ra tự động từ delivery delay.

## 11. Queue, Topic, ordering và consumer

### 11.1. Với Queue

Message đến queue có thể được broker lưu ngay nhưng chỉ **đủ điều kiện giao** khi đến `JMSDeliveryTime`. Khi có nhiều consumer cạnh tranh, broker chọn consumer thích hợp ở thời điểm giao; delay **không định danh một consumer cụ thể**.

M1 được send trước M2 nhưng có thể được giao sau:

~~~text
10:00:00  send M1, delay 60 giây => eligible 10:01:00
10:00:01  send M2, delay 0        => eligible 10:00:01

M2 có thể được giao trước M1.
~~~

Vì vậy đừng cho rằng queue delayed sẽ giữ nguyên thứ tự hoàn tất theo thứ tự producer gửi. Priority, nhiều session/consumer, transaction và redelivery còn ảnh hưởng thêm.

### 11.2. Với Topic

Với message publish lên Topic có delivery delay, subscription **phải tồn tại tại thời điểm publish/send** để có cơ hội nhận message; việc tạo subscriber **sau send nhưng trước mốc delivery time** không có nghĩa là nó được nhận lại message đã publish.

~~~text
10:00  E1 publish lên topic, delay 5 phút
10:02  subscriber B mới đăng ký
10:05  E1 đến mốc đủ điều kiện giao

Subscriber B không tự nhận E1 chỉ vì đã tồn tại trước 10:05.
~~~

Việc subscription durable/shared, selector và trạng thái kết nối tác động tới cách broker lưu/giao, nhưng delivery delay **không biến Topic thành hệ thống replay lịch sử**.

## 12. Retry và redelivery delay là chuyện khác

`JMSDeliveryTime` được tính cho **lần send ban đầu**. Nếu consumer nhận message rồi rollback hoặc mất kết nối, message có thể được giao lại; điều đó **không có nghĩa** JMS tự tính `JMSDeliveryTime = thời điểm retry + delay ban đầu`.

Một broker có thể được cấu hình **redelivery delay/backoff**, ví dụ thử lại sau 30 giây, 1 phút, 5 phút. Đây là chính sách **retry sau lỗi**, độc lập với producer delivery delay. Header `JMSDeliveryTime` vẫn phản ánh thời điểm do provider xác định khi send; đừng lấy header đó làm lịch retry.

Ví dụ timeline:

~~~text
10:00  producer send M, delay 2 phút
10:02  JMSDeliveryTime đến; consumer nhận M
10:03  consumer xử lý lỗi => rollback
10:05  broker redelivery theo policy retry 2 phút
~~~

`JMSRedelivered` và, nếu provider hỗ trợ, `JMSXDeliveryCount` có thể giúp quan sát lần giao lại; chúng **không thay thế** idempotent consumer dựa vào `eventId` nghiệp vụ. Delivery delay không cam kết exactly-once processing.

## 13. Lập lịch theo thời điểm tuyệt đối

JMS API nhận **delay tương đối**, không nhận trực tiếp `Instant` từ business logic. Nếu cần gửi message “không trước 20:00 ngày mai”, ứng dụng tính số mili giây còn lại:

~~~java
// Fragment: có java.time.Instant target,
// jakarta.jms.JMSProducer producer và Queue queue.
long delayMillis = Math.max(
        0L,
        target.toEpochMilli() - System.currentTimeMillis());

producer.setDeliveryDelay(delayMillis).send(queue, "REMINDER-123");
~~~

Điều cần hiểu:

1. `Math.max(0, ...)` bảo đảm không truyền delay âm; nếu deadline đã qua, message được phép giao ngay theo delay 0.
2. Thời gian tính delay và thời gian thực hiện send **không trùng tuyệt đối**; ở giữa có độ trễ ứng dụng, vì vậy `JMSDeliveryTime` có thể lệch một chút so với business target.
3. Đồng hồ broker/producer/consumer cần được đồng bộ phù hợp, đặc biệt khi tính deadline giữa nhiều máy.
4. Đối với lịch dài ngày, phải có nhu cầu hủy/sửa và audit, thường nên lưu `scheduledAt` cùng trạng thái trong DB/scheduler. JMS chuẩn **không đưa ra API chung để sửa một message đang chờ theo ID**.
5. Nếu business deadline thay đổi, cần chiến lược cập nhật lịch, đánh dấu phiên bản và idempotency thay vì giả định chỉnh được `JMSDeliveryTime` của message đã gửi.

**Phân biệt điều kiện thời gian của broker với hành động của nghiệp vụ:** message được giao lúc 20:00+ chưa chứng minh email/thanh toán/cập nhật DB đã hoàn thành. Tác vụ có thể bắt đầu muộn, retry hoặc thất bại.

## 14. Quan sát và kiểm thử

### 14.1. Những thông tin nên ghi log

Để chẩn đoán thực tế, ghi lại `eventId`/job ID nghiệp vụ, `JMSMessageID`, queue/topic, `JMSTimestamp`, `JMSDeliveryTime`, `JMSExpiration`, `receivedAt`, trạng thái transaction, delay cấu hình, redelivery count và thời gian xử lý.

**Late delivery** có thể ước tính bằng:

~~~text
lateByMillis = receivedAtEpochMillis - JMSDeliveryTime
~~~

Nếu kết quả âm, cần điều tra **clock skew/đồng hồ hệ thống** hoặc lỗi cách ghi nhận thời gian trước khi kết luận JMS provider giao sớm. Để đo **độ dài thời gian** trên cùng JVM, ưu tiên đồng hồ đơn điệu (`System.nanoTime()` hoặc thư viện metrics). Để so sánh **mốc tuyệt đối** thì dùng Unix epoch millis, kèm đồng bộ đồng hồ đa máy.

Không log payload nhạy cảm chỉ để chẩn đoán scheduling.

### 14.2. Kiểm thử tích hợp có ý nghĩa

Một integration test với broker thật nên:

1. Gửi message với delay đủ lớn để quan sát (ví dụ 2–3 giây).
2. Đọc `JMSDeliveryTime` **sau send**, xác nhận mốc nằm sau send time một khoảng phù hợp cấu hình.
3. Khi đồng hồ còn **trước** mốc, consumer không được nhận message; tránh viết assertion dựa vào `Thread.sleep(100)` mang tính may rủi.
4. Chờ đến sau mốc với timeout có dư địa để broker xử lý, kiểm tra đúng payload và header `JMSDeliveryTime` không đổi.
5. Kiểm tra độc lập TTL nhỏ hơn delay: message hết hạn trước khi được phép giao.
6. Với transacted send, kiểm tra message không giao trước commit, kể cả khi delivery time đã tới.

Không assert broker phải gọi consumer tại mili giây chính xác. Đó không phải bảo đảm của Jakarta Messaging.

### 14.3. Bảng chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| Header `JMSDeliveryTime` gần `JMSTimestamp` dù cần delay | Producer/template chưa cấu hình hoặc bị broker override. | In header sau send; kiểm tra producer và cấu hình broker. |
| Message đến “sớm” hơn deadline nghiệp vụ | Sai đơn vị, tính giờ địa phương như UTC, dùng nhầm producer/template. | Chuyển toàn bộ thời gian về epoch millis; so sánh `scheduledAt` và `JMSDeliveryTime`. |
| Consumer nhận muộn hơn header | Broker backlog, listener không chạy, selector, consumer chậm, transaction commit muộn. | Xem queue depth, consumer count, transaction và broker metrics. |
| `receive(1000)` trả `null` | Message chưa đủ điều kiện, chưa commit, đã hết hạn hoặc không có message phù hợp. | Kiểm tra delay, TTL, queue/selector và trạng thái listener. |
| Message không bao giờ được xử lý | TTL ngắn hơn delay, expiry policy, topic subscription không tồn tại lúc send. | Xem `JMSExpiration`, expiry/DLQ metrics, quy tắc subscription. |
| Retry đến chậm hơn dự đoán | Broker có redelivery delay/backoff riêng. | Kiểm tra retry policy, tách khỏi send delivery delay. |
| Delay từng message sai ngẫu nhiên | Shared `JmsTemplate` bị mutate delay động giữa các thread. | Cấu hình template theo chính sách cố định, không đổi setter khi đang gửi đồng thời. |
| M1 gửi trước nhưng M2 xử lý trước | M1 bị delay, priority/transaction khác nhau hoặc nhiều consumer. | Đánh giá ràng buộc thứ tự nghiệp vụ; không giả định FIFO toàn cục. |

## 15. Những nhầm lẫn hay gặp

**“Set delay 5 phút thì producer phải chờ 5 phút mới gửi?”** Không. Producer gửi ngay; broker mới hạn chế thời điểm giao cho consumer.

**“`JMSDeliveryTime` là thời gian chắc chắn callback `@JmsListener` được chạy?”** Không. Nó chỉ là **earliest eligible time**; consumer có thể nhận muộn hơn.

**“Dùng `message.setJMSDeliveryTime(...)` được không?”** Không dùng để lên lịch. Client phải dùng `setDeliveryDelay` trên producer.

**“Tôi muốn không đợi chút nào thì phải set delay = -1?”** Với producer JMS, mặc định là **0**. Con số `-1` là sentinel của **`JmsTemplate`** để không override option, không phải JMS delivery delay âm.

**“TTL bắt đầu sau khi delay kết thúc?”** Không. TTL và delay đều tính từ send, nên có thể xảy ra `JMSExpiration < JMSDeliveryTime`.

**“Commit sau 5 phút sẽ tự bắt đầu một delay 5 phút khác?”** Không. Trong transacted send, delay vẫn tính từ send; nhưng message chưa commit không được giao.

**“Tôi dùng `receiveNoWait()` nhận `null`, vậy message bị mất?”** Không. Tại thời điểm thăm dò chưa có message khả dụng cho consumer đó, trong đó có khả năng message đang chờ delivery time.

**“Message có delay thì mọi subscriber tạo trước delivery time đều nhận?”** Không. Với Topic, subscription phải đáp ứng điều kiện tồn tại tại thời điểm **publish/send**.

## 16. Câu hỏi tự luyện và đáp án

1. Producer gửi lúc 08:00, delivery delay 10 phút, TTL 30 phút. Mốc sớm nhất được giao và mốc hết hạn? **08:10 và 08:30**.
2. Gửi lúc 08:00, delay 10 phút, TTL 3 phút. Có thể giao lúc 08:10 không? **Không; message đã hết hạn lúc 08:03**.
3. Gửi trong transaction lúc 08:00 với delay 5 phút, commit lúc 08:08. Khi nào có thể giao sớm nhất? **Sau commit lúc 08:08**, vì mốc header 08:05 đã qua.
4. Producer gọi `message.setJMSDeliveryTime(now + 60000)` rồi send. Có phải broker buộc chờ một phút? **Không; setter này dành cho provider**.
5. Message giao lúc 08:12 với `JMSDeliveryTime = 08:10`. Có vi phạm chuẩn? **Không; broker được giao muộn hơn**.
6. JMS default `deliveryDelay` bằng bao nhiêu? **0L**. `JmsTemplate` default `deliveryDelay` là gì? **-1**, nghĩa là không override.
7. Producer gửi M1 trước M2, nhưng M1 delay 30 giây, M2 delay 0. M2 có thể được nhận trước M1 không? **Có**.
8. Cấu hình retry của broker đợi 2 phút sau rollback có phải `JMSDeliveryTime` bị cộng thêm 2 phút? **Không; retry delay là quy tắc riêng**.
9. Muốn lưu lịch hủy/sửa được trong nhiều ngày thì chỉ dùng delay JMS đã đủ chưa? **Thường chưa; cần quản lý lịch nghiệp vụ và cơ chế hủy/sửa**.
10. Muốn lấy header sau async send, đọc ngay khi gọi `send(..., CompletionListener)` có chắc đúng không? **Không; đợi completion callback thành công**.

## 17. Nguồn chuẩn

- [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html): mục 3.4.13 về `JMSDeliveryTime`, mục 7.9 về delivery delay, và quy định TTL/transaction.
- [Jakarta Messaging Message API](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/message): `getJMSDeliveryTime()`, `setJMSDeliveryTime()`, `getJMSExpiration()`.
- [Jakarta Messaging MessageProducer API](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/messageproducer): `setDeliveryDelay(long)`, `setTimeToLive(long)`.
- [Jakarta Messaging JMSProducer API](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/jmsproducer): simplified API producer.
- [Spring Framework 6.2 — JmsTemplate API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/core/JmsTemplate.html): setter `setDeliveryDelay`.
- [Spring Boot 3.5 — JMS/Artemis](https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html): embedded broker và kết nối.
- [Apache ActiveMQ Artemis — Scheduled Messages](https://artemis.apache.org/components/artemis/documentation/latest/scheduled-messages): cơ chế scheduled messages riêng của broker.

**Điểm nhớ lâu:** `JMSDeliveryTime = sendTime + deliveryDelay` là **mốc sớm nhất JMS provider được phép giao message**, không phải mốc hết hạn, cũng không phải thời điểm xử lý chính xác. Đặt delay trên producer; provider ghi header; transaction, TTL, trạng thái broker/consumer quyết định khi nào message thực sự được giao.
