# TemporaryQueue và TemporaryTopic trong JMS / Spring JMS

## 1. Mục tiêu: destination tạm thời giải quyết việc gì?

Trong JMS (Java Message Service, nay được chuẩn hóa dưới tên **Jakarta Messaging**), ứng dụng thường gửi hoặc nhận message qua hai loại `Destination`:

- **`Queue`**: kênh point-to-point, một message thường được trao cho một consumer thích hợp.
- **`Topic`**: kênh publish/subscribe, các subscription đang hợp lệ có thể nhận bản sao của message được xuất bản.

Thông thường queue/topic là các destination có vòng đời dài, do hệ thống quản trị broker hoặc cấu hình hạ tầng chuẩn bị. Nhưng có những trường hợp ứng dụng cần một điểm nhận phản hồi **riêng biệt, ngắn hạn**, chỉ phục vụ một client hay một phiên trao đổi. JMS cung cấp hai interface chuyên dụng:

- **`TemporaryQueue extends Queue`**: queue tạm thời.
- **`TemporaryTopic extends Topic`**: topic tạm thời.

Hai destination này được provider tạo với định danh duy nhất theo ngữ cảnh của connection, sống trong **vòng đời của connection tạo ra chúng** và có quy tắc sở hữu đặc biệt: **chỉ connection đã tạo destination mới được tạo consumer trên destination đó; producer từ connection khác vẫn có thể gửi tới destination.** Vì vậy chúng rất hữu ích cho mẫu **request–reply**: bên yêu cầu tạo hộp thư phản hồi tạm thời, gửi địa chỉ hộp thư qua header `JMSReplyTo`, bên xử lý gửi kết quả về đó.

Đây là **destination thật do JMS provider/broker quản lý**, không phải chỉ một Java object trong bộ nhớ. Tạo nhiều temporary destination có thể tiêu thụ tài nguyên broker; cần đóng consumer và xóa destination sớm khi không cần.

### Hình dung nhanh

~~~text
Request client (connection A)                     Reply service (connection B)
┌─────────────────────────────────┐                ┌─────────────────────────────┐
│ Tạo TemporaryQueue reply-A      │                │ Consume từ requests.queue │
│ Consumer chỉ được tạo bởi A     │                │                             │
│ Gửi request tới requests.queue ─┼───────────────>│ Đọc payload + JMSReplyTo    │
│   JMSReplyTo = reply-A          │                │ Tạo response               │
│                                 │<───────────────┼─ Send response tới reply-A │
│ Nhận response từ reply-A        │                │ (B được phép PRODUCE)      │
│ Đóng consumer, delete reply-A   │                └─────────────────────────────┘
└─────────────────────────────────┘
~~~

**Điểm phân biệt**: connection B **được gửi** vào `reply-A` nhưng **không được tự tạo consumer** để đọc nó. Điều này bảo vệ mô hình nhận của chủ sở hữu, nhưng không thay thế phân quyền bảo mật của broker.

## 2. So sánh chi tiết TemporaryQueue và TemporaryTopic

| Tiêu chí | `TemporaryQueue` | `TemporaryTopic` |
| --- | --- | --- |
| Kiểu cha | `Queue` | `Topic` |
| Ngữ nghĩa phân phối | Point-to-point: một message được giao cho một consumer trong các consumer cạnh tranh trên queue | Publish/subscribe: các subscription thích hợp có thể nhận message |
| Tạo từ classic API | `Session.createTemporaryQueue()` | `Session.createTemporaryTopic()` |
| Tạo từ simplified API | `JMSContext.createTemporaryQueue()` | `JMSContext.createTemporaryTopic()` |
| Ai được tạo consumer? | Chỉ connection sở hữu | Chỉ connection sở hữu |
| Ai được gửi message? | Producer trên connection sở hữu hoặc connection khác, nếu broker cho phép | Producer trên connection sở hữu hoặc connection khác, nếu broker cho phép |
| Vòng đời | Theo connection đã tạo, hoặc xóa sớm bằng `delete()` | Tương tự |
| Điểm dùng điển hình | Một địa chỉ trả lời tạm cho request–reply một kết quả | Phát sự kiện tạm thời cho các subscription trong phạm vi connection sở hữu |
| Durable subscription? | Không áp dụng theo kiểu Topic | **Không tạo durable subscription** cho temporary topic; mô hình durable trái với bản chất tạm thời |
| API xóa | `TemporaryQueue.delete()` | `TemporaryTopic.delete()` |

Đừng suy luận tên “temporary” nghĩa là “không có persistence ở mọi tầng” hoặc “bảo đảm message được nhận trước khi kết thúc”. Đặc tả nói về **phạm vi tồn tại của destination**; chính sách broker, delivery mode, thời hạn message, kết nối, lỗi mạng và giao dịch vẫn ảnh hưởng việc giao nhận. Nếu connection sở hữu đóng trước khi phản hồi tới, destination biến mất, thông điệp phản hồi có thể lỗi hoặc không tới được client tùy provider.

### 2.1. TemporaryQueue không phải queue đặt tên ngẫu nhiên

Ví dụ hai thao tác khác nhau:

~~~java
Queue namedQueue = context.createQueue("reply.order.123");
TemporaryQueue realTemporaryQueue = context.createTemporaryQueue();
~~~

`createQueue("reply.order.123")` tạo một **đối tượng Queue đại diện cho tên destination**, không có nghĩa JMS vừa tạo một queue tạm thời trong broker. Việc broker tự tạo queue theo tên hay đòi admin provision phụ thuộc provider/cấu hình. Trong khi đó `createTemporaryQueue()` yêu cầu provider tạo một temporary destination có vòng đời/quy tắc sở hữu được đặc tả.

Tương tự: `createTopic("news")` khác `createTemporaryTopic()`. Chỉ thêm tiền tố như `temp.` vào tên queue/topic thường **không mang lại** quyền consumer/lifecycle đặc biệt của `TemporaryQueue` hoặc `TemporaryTopic`.

### 2.2. Vòng đời dựa trên connection, không dựa trên session

Classic JMS dùng `Connection` chứa một hoặc nhiều `Session`. Lệnh tạo temporary destination thường được gọi từ một `Session`, nhưng phạm vi tồn tại là **cả connection**.

- Session S1 trên connection A tạo temporary queue T.
- Session S2 **cũng trên connection A** có thể tạo consumer để đọc T (theo quy tắc sử dụng session của JMS).
- Session trên connection B không được tạo consumer trên T.
- Connection B vẫn có thể tạo producer gửi message tới T, khi có quyền và destination còn tồn tại.
- Đóng S1 **không mặc nhiên xóa** T vì connection A có thể vẫn còn mở; xóa T bằng `delete()` hoặc đóng **connection A**.
- `JMSContext` ở simplified API quản lý connection/session bên dưới; đóng context tạo ra destination có thể làm connection liên quan đóng tùy quan hệ context/provider. Không chuyển reference temporary destination sang một connection mới sau reconnect và kỳ vọng nó còn hiệu lực.

JMS chuẩn hóa quyền tạo consumer theo connection. Với connection pooling, caching và failover, **đừng suy từ bean Java hoặc đối tượng wrapper để khẳng định hai thao tác dùng cùng physical connection**: kiểm tra cấu hình `ConnectionFactory` và vòng đời tài nguyên thực tế.

## 3. Tạo, sử dụng và xóa bằng Jakarta Messaging API

Các ví dụ dùng `jakarta.jms.*`, phù hợp thế hệ **Jakarta Messaging 3.x / Spring Framework 6+ / Spring Boot 3+**. Dự án Spring/JMS đời cũ có thể dùng `javax.jms.*`; không trộn hai bộ interface trong cùng provider mà chưa có cơ chế chuyển đổi được hỗ trợ.

### 3.1. Classic API: hiểu rõ connection và session

~~~java
import jakarta.jms.Connection;
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSException;
import jakarta.jms.Session;
import jakarta.jms.TemporaryQueue;
import jakarta.jms.TemporaryTopic;

// Một phương thức minh họa, nhận ConnectionFactory đã được cấu hình.
// Đây không phải file Java chạy độc lập.
static void showCreation(ConnectionFactory factory) throws JMSException {
    try (Connection connection = factory.createConnection()) {
        try (Session session =
                 connection.createSession(false, Session.AUTO_ACKNOWLEDGE)) {
            TemporaryQueue replyQueue = session.createTemporaryQueue();
            TemporaryTopic eventTopic = session.createTemporaryTopic();
            try {
                // Trước khi đọc, cần tạo consumer và connection.start().
                // Có thể truyền replyQueue/eventTopic qua JMSReplyTo.
            } finally {
                // Phải đóng mọi consumer sử dụng destination trước khi xóa.
                replyQueue.delete();
                eventTopic.delete();
            }
        }
    }  // Đóng connection cũng chấm dứt các temporary destination còn lại.
}
~~~

Giải thích:

1. `factory` phải có **implementation của JMS provider** và cấu hình kết nối broker; chỉ thêm API jar là chưa đủ để chạy.
2. `Connection` đại diện ngữ cảnh sở hữu. Session là nơi thuận tiện để tạo queue/topic tạm, nhưng không “sở hữu” riêng vòng đời destination.
3. Nếu đã có `MessageConsumer` hoặc `JMSConsumer` dùng destination, **đóng consumer trước khi gọi `delete()`**; theo API, xóa khi vẫn còn receiver/subscriber đang dùng có thể phát sinh `JMSException`.
4. Chỉ gọi `connection.start()` khi thực sự bắt đầu nhận message với classic API; nếu quên, lời gọi receive có thể đợi dù broker đã có message.
5. `try-with-resources` bảo đảm đóng session và connection kể cả khi có exception, nhưng đối với temporary destination đang dùng lâu, nên xóa có chủ đích sớm khi kết thúc.

Đoạn trên không send/receive nên không cần gọi `connection.start()`; điều kiện ở bước 4 áp dụng cho các chương trình có consumer.

### 3.2. Simplified API: thực hành nhỏ với TemporaryQueue

~~~java
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSConsumer;
import jakarta.jms.JMSContext;
import jakarta.jms.JMSException;
import jakarta.jms.TemporaryQueue;

// Đoạn phương thức có thể đặt trong một class, với factory từ provider.
// Yêu cầu broker hoạt động và quyền gửi/nhận phù hợp.
static String temporaryQueueRoundTrip(ConnectionFactory factory)
        throws JMSException {
    try (JMSContext owner = factory.createContext();
         JMSContext other = factory.createContext()) {

        TemporaryQueue replyQueue = owner.createTemporaryQueue();
        try (JMSConsumer replyConsumer = owner.createConsumer(replyQueue)) {
            // Đơn giản hóa: other giả lập một dịch vụ gửi phản hồi.
            other.createProducer().send(replyQueue, "response-42");

            // Owner được nhận; chỉ đợi tối đa 3 giây.
            return replyConsumer.receiveBody(String.class, 3_000);
        } finally {
            // Consumer đã đóng khi rời try-with-resources.
            replyQueue.delete();
        }
    }
}
~~~

Nếu broker có sẵn và message được giao trong hạn, phương thức trả về `"response-42"`; nếu hết 3 giây, trả về `null`. Ví dụ này kiểm chứng **producer từ context khác có thể gửi tới temporary queue**, còn consumer thuộc context sở hữu. `JMSContext` mặc định tự khởi động connection khi nhận message; không cần gọi `start()` trong tình huống mặc định này.

Lưu ý về pooling: hai `JMSContext` không nhất thiết tương đương hai physical connection độc lập trong mọi bộ wrapper. Dù được pool tối ưu hóa thế nào, quy tắc “chỉ connection sở hữu được consume” vẫn là ràng buộc tại tầng JMS.

### 3.3. Simplified API: dùng TemporaryTopic

~~~java
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSConsumer;
import jakarta.jms.JMSContext;
import jakarta.jms.JMSException;
import jakarta.jms.TemporaryTopic;

// Đoạn phương thức minh họa; cần ConnectionFactory provider hợp lệ.
static String temporaryTopicExample(ConnectionFactory factory)
        throws JMSException {
    try (JMSContext subscriberContext = factory.createContext();
         JMSContext publisherContext = factory.createContext()) {

        TemporaryTopic topic = subscriberContext.createTemporaryTopic();
        try (JMSConsumer subscriber = subscriberContext.createConsumer(topic)) {
            // Producer khác gửi tới địa chỉ topic đã được chia sẻ.
            publisherContext.createProducer().send(topic, "notice-42");

            // Với message đang được publish và subscriber đã tồn tại,
            // subscriber phía chủ sở hữu có thể nhận thông báo.
            return subscriber.receiveBody(String.class, 3_000);
        } finally {
            topic.delete();
        }
    }
}
~~~

Nếu message đến trước timeout, kết quả là `"notice-42"`; nếu không, `null`. Khác queue, một temporary topic có thể có **nhiều consumer/subscription hợp lệ trong phạm vi connection sở hữu**, mỗi subscription có thể được phân phối bản sao message theo quy tắc pub/sub. Không tạo durable subscription cho destination này: nó được thiết kế mất đi khi connection hết vòng đời.

**Đoạn API 3.2 và 3.3 là phương thức, không phải chương trình `main` độc lập.** Để chạy, ứng dụng phải có `ConnectionFactory` thực, dependency provider, broker và quyền truy cập. Phần 5 có project Spring Boot đầy đủ để chạy mẫu request–reply thông dụng.

## 4. Request–reply bằng TemporaryQueue

### 4.1. Quy trình từng bước

Ví dụ một service `OrderClient` muốn hỏi `OrderWorker` trạng thái đơn hàng:

1. Requester giữ connection A mở, tạo `TemporaryQueue` `replyDestination` và consumer chờ phản hồi.
2. Requester tạo request `TextMessage`, gắn `request.setJMSReplyTo(replyDestination)` rồi gửi tới queue cố định `orders.requests`.
3. Service trên connection B nhận request, đọc `request.getJMSReplyTo()`.
4. Service tạo response và gửi tới `Destination` thu được từ `JMSReplyTo`. Connection B là **producer**, không cần consumer trên temporary queue.
5. Requester nhận message từ temporary queue, kiểm tra kiểu body/correlation ID; sau đó đóng consumer và gọi `delete()`.
6. Nếu request timeout, requester không chờ vô hạn; phản hồi đến sau khi queue bị xóa có thể không còn đích để nhận.

~~~text
A                                Broker                                B
│ createTemporaryQueue()          │                                    │
│ createConsumer(reply)           │                                    │
│ -- request: JMSReplyTo=reply -->│ -- deliver orders.requests ------->│
│                                 │                                    │ xử lý
│                                 │<----------- send(reply, result) ----│
│<-------------- deliver result --│                                    │
│ close consumer; reply.delete()  │                                    │
~~~

Header `JMSReplyTo` chỉ **chỉ ra đích gửi phản hồi**; JMS không tự động xử lý toàn bộ request–reply. Ứng dụng hoặc framework còn phải đảm nhiệm xử lý timeout, lỗi, correlation và vòng đời.

### 4.2. `JMSCorrelationID`, `JMSMessageID` và ghép phản hồi

Có hai chiến lược phổ biến:

- **Echo request ID do ứng dụng tạo:** tạo một correlation ID duy nhất, đặt trong request; responder chép ID đó vào reply, requester kiểm tra trùng.
- **Dùng JMSMessageID của request:** sau khi request được gửi, provider gán `JMSMessageID`; responder đặt reply `JMSCorrelationID = request.getJMSMessageID()`, requester so sánh. Phải thống nhất convention vì hai chiến lược **không tương đương**.

Các field đều là header JMS, nhưng JMS không buộc mọi service phải tự tương quan request/reply theo một trong hai convention cụ thể. Nếu sử dụng **một temporary queue riêng cho từng request**, chính địa chỉ reply đã giúp cô lập kết quả. Khi dùng **một reply destination chung** cho nhiều request đồng thời, cần correlation, selector/dispatcher và xử lý message hết hạn để tránh người gọi nhận nhầm phản hồi.

Ví dụ responder thủ công, **mảnh code bên trong một phương thức** có `JMSContext responderContext` và `Message incoming` đã được cấp:

~~~java
Destination replyTo = incoming.getJMSReplyTo();
if (replyTo == null) {
    throw new IllegalArgumentException("Missing JMSReplyTo");
}

TextMessage response = responderContext.createTextMessage("DONE");
response.setJMSCorrelationID(incoming.getJMSMessageID());
responderContext.createProducer().send(replyTo, response);
~~~

Ở đây `Destination` có thể là `TemporaryQueue`, `TemporaryTopic` hoặc một destination thông thường. Responder gửi dựa trên destination thực có trong header; không được suy từ tên String rồi tạo một queue khác. Đoạn code này cần import `jakarta.jms.Destination`/`TextMessage`/`Message` và ngữ cảnh method có thể ném `JMSException`.

### 4.3. Vì sao TemporaryQueue thường phù hợp request–reply hơn TemporaryTopic?

Một request thường trông đợi **một kết quả** do **một requester** nhận. TemporaryQueue có semantics point-to-point nên tự nhiên với trường hợp đó. TemporaryTopic hữu ích khi một kết quả/thông báo tạm cần phát đến **nhiều subscription thuộc connection tạo ra topic**. Topic không tự tạo một reply một–một; với nhiều subscriber, một phản hồi có thể tới nhiều consumer. Cả hai đều không dành cho sự kiện cần được giữ lâu dài sau khi client disconnect.

## 5. Ví dụ Spring Boot chạy được: `JmsTemplate.sendAndReceive()`

Spring Framework cung cấp `JmsTemplate.sendAndReceive(...)`. Với overload gửi request thông thường, Spring **tự tạo `TemporaryQueue`**, đặt nó vào header `JMSReplyTo`, tạo consumer nhận reply và xóa temporary queue khi hoàn tất. Đây là cách quan sát TemporaryQueue mà business code không phải tự quản lý từng `Connection`/`Session`.

Mẫu này sử dụng **Java 17+**, **Maven**, **Spring Boot 3.5.7** (API `jakarta.jms`) và **Apache ActiveMQ Artemis** chạy Docker. Thực hành local để quan sát dòng request–reply; phiên bản thư viện thực tế nên đồng nhất với BOM của dự án.

### 5.1. Khởi động Artemis local

~~~bash
docker run --rm -d --name artemis-temp-demo \
  -p 127.0.0.1:61616:61616 \
  apache/artemis:latest-alpine
~~~

Image chính thức dùng tài khoản mặc định `artemis/artemis`. Lệnh bind cổng trên loopback để thực hành local; triển khai thực tế cần user, TLS, quyền truy cập và cấu hình broker riêng.

Nếu broker chưa sẵn sàng, xem log bằng `docker logs artemis-temp-demo` rồi chạy ứng dụng sau khi broker khởi động. Broker demo thường được cấu hình tự tạo queue phù hợp; với hệ production, chủ động quản lý queue `demo.requests` và chính sách routing.

### 5.2. Tạo project Maven

Tại thư mục mới, tạo `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>temporary-jms-demo</artifactId>
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
~~~

`spring-boot-starter-artemis` mang vào Spring JMS và provider/client cần thiết. API `jakarta.jms` chỉ định kiểu Java, còn provider Artemis mới là thành phần kết nối broker.

### 5.3. Khai báo `src/main/resources/application.properties`

~~~properties
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.artemis.user=artemis
spring.artemis.password=artemis

spring.jms.template.receive-timeout=5s
~~~

- `native`: kết nối tới broker đang chạy, không khởi tạo embedded broker.
- `receive-timeout=5s`: tránh block vô hạn nếu service không phản hồi.
- Với demo queue, không cần đổi `spring.jms.pub-sub-domain` mặc định (false). TemporaryQueue do `sendAndReceive` tạo thuộc Queue model bất kể tên destination cố định.
- Thông số kết nối là cấu hình **provider/broker**, không phải quy tắc cố định của JMS API.

### 5.4. Java source hoàn chỉnh

Tạo `src/main/java/com/example/jms/TemporaryDestinationApplication.java`:

~~~java
package com.example.jms;

import jakarta.jms.Message;
import jakarta.jms.TextMessage;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;

@SpringBootApplication
public class TemporaryDestinationApplication {
    public static void main(String[] args) {
        SpringApplication.run(TemporaryDestinationApplication.class, args);
    }

    @Bean
    CommandLineRunner requestOnce(JmsTemplate jmsTemplate) {
        return args -> {
            Message reply = jmsTemplate.sendAndReceive(
                    "demo.requests",
                    session -> session.createTextMessage("order-42")
            );

            if (reply == null) {
                System.out.println("Reply timeout");
                return;
            }
            if (!(reply instanceof TextMessage textReply)) {
                throw new IllegalStateException(
                        "Expected TextMessage, got " + reply.getClass().getName()
                );
            }
            System.out.println("Reply: " + textReply.getText());
        };
    }
}

@Component
class RequestResponder {
    @JmsListener(destination = "demo.requests")
    public String handle(String requestPayload) {
        return "ACK:" + requestPayload;
    }
}
~~~

### 5.5. Chạy và giải thích

Trong thư mục có `pom.xml`, chạy:

~~~bash
mvn spring-boot:run
~~~

Khi broker đã hoạt động và listener xử lý thành công, console của ứng dụng sẽ có dòng:

~~~text
Reply: ACK:order-42
~~~

Các dòng log Spring/Artemis và thứ tự log không cố định. Nếu broker hoặc listener không phản hồi trước timeout thì dòng do code in ra là:

~~~text
Reply timeout
~~~

**Phân tích đường đi:**

1. `JmsTemplate.sendAndReceive` tạo `TextMessage`, dùng một temporary queue nội bộ và đặt vào `JMSReplyTo`.
2. Spring gửi request đến queue cố định `demo.requests`, rồi chờ reply trên temporary queue.
3. Listener `@JmsListener` lấy payload `order-42`, trả về String `ACK:order-42`. Với request có `JMSReplyTo`, Spring listener adapter chuyển kết quả thành reply message và gửi về destination trong header.
4. Requester nhận `TextMessage` rồi in kết quả.
5. Khi `sendAndReceive` kết thúc, `JmsTemplate` đóng các JMS resource cần thiết và xóa temporary queue mà nó tạo.

Trong trường hợp này developer **không cần tự gọi `createTemporaryQueue()` hoặc `delete()`**; Spring quản lý theo phạm vi lời gọi. Tính năng này **không tự cung cấp** retry vô hạn, bảo đảm end-to-end exactly-once, hay khả năng phục hồi response nếu connection requester mất.

Dừng app bằng Ctrl+C; đóng broker demo:

~~~bash
docker stop artemis-temp-demo
~~~

> Trong ứng dụng server, tránh gọi đồng bộ `sendAndReceive()` trên luồng có yêu cầu độ trễ rất thấp mà không cân nhắc thời gian chờ, backpressure, số kết nối và số temporary destination đang mở. Hãy đặt timeout, metrics và chính sách retry rõ ràng.

## 6. Khác biệt giữa Spring JMS và manual TemporaryTopic

Với Spring JMS, `JmsTemplate` và `@JmsListener` là abstraction thao tác JMS. Tuy nhiên **`sendAndReceive` mặc định dùng TemporaryQueue**, bởi request–reply đơn thường muốn một người nhận. Nếu nghiệp vụ đòi TemporaryTopic, có thể tạo nó qua `Session.createTemporaryTopic()` hoặc `JMSContext.createTemporaryTopic()` và quản lý consumer, connection, xóa destination theo vòng đời của chính ứng dụng.

Không nên đổi `spring.jms.pub-sub-domain=true` rồi cho rằng `JmsTemplate.sendAndReceive` sẽ tự dùng `TemporaryTopic`. Setting này ảnh hưởng cách Spring phân giải các destination dạng tên và listener trong cấu hình, **không đổi logic tạo TemporaryQueue của overload request–reply mặc định**.

Trong một service đa luồng dùng **CachingConnectionFactory** hoặc pooling, temporary destination gắn với connection bên dưới. Việc đóng wrapper hoặc session không nên bị xem là bằng chứng chắc chắn rằng physical connection đã kết thúc. Nếu tự tạo temporary queue/topic, hãy kiểm tra chiến lược cache và **xóa chủ động** khi consumer đã đóng. Không cache lâu dài `TemporaryQueue`/`TemporaryTopic` trong singleton Spring bean để tái dùng bất chấp reconnect.

## 7. Khi nào không nên dùng temporary destination?

Dùng temporary destination cho request–reply ngắn hạn, phiên tương tác còn kết nối hoặc subscription có vòng đời nhỏ. Đừng dùng nếu cần:

- **Phản hồi tồn tại sau khi client offline/restart:** dùng queue lâu dài hoặc persistence/state store với correlation ID và TTL.
- **Subscription lâu dài, bền vững sau reconnect:** dùng topic thông thường cùng durable subscription phù hợp; temporary topic không dành cho durability.
- **Gửi thông tin cho nhiều microservice độc lập tiêu thụ:** dùng topic/queue được quản trị, bởi chỉ connection sở hữu mới được tạo consumer trên temporary destination.
- **Rất nhiều request đồng thời với giới hạn tài nguyên broker thấp:** cân nhắc reply queue dùng chung, correlation ID và listener dispatcher; phải giải quyết cạnh tranh consumer, failover, load balancing và message cũ đúng cách.
- **Response cần đi qua broker/cluster/bridge khác:** phải kiểm tra khả năng route temporary destination xuyên topology. Không mặc định tên internal destination có ý nghĩa ở broker khác.

### 7.1. So sánh chiến lược reply

| Thiết kế | Điểm mạnh | Đánh đổi |
| --- | --- | --- |
| Mỗi request một `TemporaryQueue` | Isolation rõ, tự dọn theo connection/lệnh xóa; rất trực quan | Tốn round trip tạo/xóa destination; nhiều request đồng thời có thể nhiều resource |
| Một temporary queue mỗi connection, dùng nhiều request | Giảm số destination; owner connection vẫn nắm quyền consume | Cần correlation, dispatch nhiều lời gọi, xử lý concurrency/reconnect |
| Reply queue cố định | Có thể tồn tại qua restart, dễ quản lý tập trung | Cần routing ID, selector/consumer strategy, TTL, cleanup message cũ, bảo mật |
| Callback/event bất đồng bộ | Không chặn thread chờ reply | Cần lưu trạng thái, định nghĩa completion/correlation và cơ chế timeout khác |

Điểm chọn lựa phụ thuộc SLA, số request/giây, số connection, chi phí broker và yêu cầu khôi phục. Không có một chiến lược tối ưu cho mọi hệ.

## 8. Lỗi phổ biến và cách khắc phục

### Lỗi 1: Consumer được tạo trên connection khác

**Tình huống:** connection A tạo `TemporaryQueue`, connection B lấy destination reference rồi gọi `createConsumer(tempQueue)`.

**Vì sao lỗi:** JMS chỉ cho phép chính connection A tạo consumer trên temporary destination. Connection B **được gửi** tới tempQueue nhưng **không được consume**.

**Sửa:** consumer reply phải nằm trên connection đã tạo destination; nếu nhiều service muốn đọc thì thiết kế lại bằng queue/topic thông thường.

### Lỗi 2: Đóng connection trước khi service trả lời

**Tình huống:** requester tạo temp queue, gửi request, kết thúc try-with-resources/đóng connection, service mới gửi reply.

**Hậu quả:** temp queue đã hết vòng đời; response có thể không gửi được hoặc không còn consumer nhận.

**Sửa:** giữ owner connection và consumer sống đến khi reply, timeout hoặc cancellation; xóa sau khi hoàn thành.

### Lỗi 3: Không đóng consumer trước `delete()`

`TemporaryQueue.delete()`/`TemporaryTopic.delete()` có thể ném `JMSException` nếu destination còn consumer/subscriber đang dùng.

**Sửa:** đóng consumer trước rồi xóa trong `finally`; dùng try-with-resources để bảo đảm cleanup dù receive bị lỗi.

### Lỗi 4: Hiểu nhầm session close là temporary destination close

`Session` tạo temp destination nhưng không định nghĩa vòng đời riêng của nó. Một connection vẫn sống có thể có session khác consume destination đã được tạo.

**Sửa:** xác định đúng connection sở hữu, xóa destination nếu kết thúc sử dụng, xử lý connection lifecycle trong pool/cache.

### Lỗi 5: Gọi receive vô hạn

Một service bị lỗi hoặc broker bị nghẽn khiến requester chờ mãi nếu không đặt timeout.

**Sửa:** `receive(timeout)`, `receiveBody(..., timeout)` hoặc `spring.jms.template.receive-timeout=5s`; phải xác định hành vi khi nhận `null`, timeout, hủy request và retry. Retry có thể tạo request trùng nên nghiệp vụ nên hỗ trợ idempotency.

### Lỗi 6: Nhận nhầm response khi reply queue dùng chung

Có nhiều request đồng thời nhưng không có correlation, consumer cạnh tranh giành message.

**Sửa:** tạo correlation ID duy nhất, định nghĩa cách responder echo, dùng message selector/dispatcher hợp lý; xử lý late reply, duplicate reply, timeout và TTL.

### Lỗi 7: Chờ response trong cùng transaction chưa commit request

Nếu gửi request trong một JMS transaction chưa commit rồi block chờ response, responder có thể **chưa thấy request**. Transaction giữ lệnh gửi chưa được commit.

**Sửa:** gửi request và commit trước khi đợi response, hoặc thiết kế request–reply bất đồng bộ; tránh giữ DB transaction mở khi chờ mạng. `sendAndReceive` đơn giản sử dụng luồng gửi/nhận thông thường nhưng caller vẫn cần hiểu cấu hình giao dịch thực tế.

### Lỗi 8: Cho rằng temporary destination tồn tại qua failover

Reconnect thường tạo connection mới; temporary queue/topic cũ gắn với connection trước đó. Provider có thể có tính năng recovery riêng, nhưng **đừng mặc định** destination cũ được khôi phục và còn consumer hợp lệ.

**Sửa:** tạo lại temporary destination trên connection mới, gửi lại request theo idempotency policy, ghi nhận timeout/recovery bằng metrics.

### Lỗi 9: Dùng TemporaryTopic như durable Topic

Durable subscription cần sống độc lập lâu hơn một connection, trái với bản chất temporary topic.

**Sửa:** dùng topic thông thường và durable subscription được quản lý đúng client ID/subscription name theo phiên bản JMS, hoặc dùng queue lâu dài nếu yêu cầu point-to-point.

### Lỗi 10: Hiểu nhầm bảo mật và phạm vi giao tiếp

“Chỉ owner consume” là **quy tắc API**. Nó không chứng minh producer bất kỳ được phép gửi: quyền send, auth/TLS, user/role và routing vẫn do broker quyết định.

**Sửa:** giữ `JMSReplyTo` như destination object; xác nhận quyền send, topology và chính sách bảo mật. Không nhầm temporary destination với cơ chế authorization toàn diện.

## 9. Checklist triển khai thực tế

1. **Mục đích:** cần reply ngắn hạn một-một (TemporaryQueue) hay tạm phát nhiều subscription cùng connection (TemporaryTopic)?
2. **Ownership:** connection nào tạo, connection nào consume, connection nào send? Có framework cache/transaction proxy nào?
3. **Lifecycle:** thời điểm tạo, timeout, đóng consumer, `delete()`, close connection và failover có được thiết kế rõ?
4. **Correlation:** một destination riêng mỗi request hay destination chung; dùng `JMSCorrelationID` hay request `JMSMessageID` và thống nhất cả hai phía?
5. **Semantics:** queue vs topic, acknowledgment, transaction, redelivery, duplicate/late response, message TTL?
6. **Tài nguyên:** giới hạn temporary destination, số connection, tốc độ create/delete, metrics leak, timeout rate?
7. **Tích hợp:** producer có route tới temporary destination trong cluster/broker bridging không, có quyền send không?
8. **Kiểm thử:** request success, timeout, connection loss, retry, concurrent requests, consumer close, delete under load.

## 10. Tự kiểm tra

**Câu 1.** Session S1 trên connection A tạo TemporaryQueue. S1 đóng; session S2 thuộc A còn hoạt động. S2 có thể tạo consumer không?  
**Đáp:** Có, miễn temporary queue chưa bị delete và connection A còn tồn tại. Phạm vi temporary destination là **connection**, không phải S1.

**Câu 2.** Connection B có thể send vào TemporaryTopic do A tạo không?  
**Đáp:** Có, nếu destination còn hợp lệ và broker cho phép gửi. B không được tạo consumer của temporary topic đó.

**Câu 3.** `createQueue("tmp.reply")` có tương đương `createTemporaryQueue()` không?  
**Đáp:** Không. Cái đầu tạo đối tượng định danh queue theo tên; cái sau yêu cầu provider cấp temporary queue với lifetime và quyền consumer riêng.

**Câu 4.** Đóng consumer có tự xóa temporary destination?  
**Đáp:** Không nên giả định. Đóng consumer ngừng tiêu thụ; cần `delete()` hoặc đóng connection sở hữu để kết thúc lifetime.

**Câu 5.** Khi reply đến sau timeout và temporary queue đã bị xóa thì sao?  
**Đáp:** Không thể giả định reply vẫn tới requester; việc send late reply sẽ gặp destination không hợp lệ hoặc bị broker xử lý theo chính sách riêng.

**Câu 6.** Có nên dùng durable subscription trên TemporaryTopic không?  
**Đáp:** Không. Durable subscription và temporary topic có vòng đời mâu thuẫn.

**Câu 7.** Khi gọi `JmsTemplate.sendAndReceive`, ai tạo và dọn TemporaryQueue?  
**Đáp:** Spring `JmsTemplate` quản lý temporary queue phục vụ lượt request–reply, đặt nó vào `JMSReplyTo` và dọn khi phương thức kết thúc.

**Câu 8.** Vì sao cùng một reply queue dùng cho 100 request cần thêm thiết kế?  
**Đáp:** Cần ghép từng response về requester tương ứng bằng correlation/dispatcher, xử lý concurrency và timeout; riêng việc có một destination không giải quyết được việc này.

## 11. Tài liệu chính thức để đọc sâu

- [Jakarta Messaging 3.1 Specification — Creating temporary destinations, TemporaryQueue/TemporaryTopic và Request/reply](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html)
- [Jakarta EE Tutorial — Creating Temporary Destinations](https://jakartaee.github.io/jakartaee-documentation/jakartaee-tutorial/current/messaging/jms-concepts/jms-concepts.html)
- [Jakarta Messaging API — TemporaryQueue](https://javadoc.io/static/jakarta.jms/jakarta.jms-api/3.1.0/jakarta.messaging/jakarta/jms/TemporaryQueue.html)
- [Jakarta Messaging API — TemporaryTopic](https://javadoc.io/static/jakarta.jms/jakarta.jms-api/3.1.0/jakarta.messaging/jakarta/jms/TemporaryTopic.html)
- [Spring Framework — Using Spring JMS, JmsTemplate and Listener Endpoints](https://docs.spring.io/spring-framework/reference/integration/jms/using.html)
- [Spring Framework — Annotation-driven Listener Endpoints và phản hồi qua JMSReplyTo](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html)
- [Spring Framework 6.2 — JmsTemplate.sendAndReceive API](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/core/JmsTemplate.html)
- [Spring Boot — Messaging with JMS](https://spring.io/guides/gs/messaging-jms/)
- [Apache ActiveMQ Artemis — Official Docker Image](https://artemis.apache.org/components/artemis/documentation/latest/docker.html)
