# MessageListenerAdapter và ánh xạ tới phương thức của đối tượng

## Mục tiêu

Trong Spring JMS, `MessageListenerAdapter` cho phép dùng một POJO làm message-driven listener mà không bắt buộc POJO phải implement trực tiếp `jakarta.jms.MessageListener`. Adapter nhận JMS message từ listener container, chuyển nội dung message thành kiểu Java phù hợp, rồi gọi một phương thức trên delegate object.

Cơ chế này tách nghiệp vụ xử lý message khỏi API JMS. Delegate có thể chỉ nhận `String`, `byte[]`, `Map` hoặc một kiểu Java đã được converter tạo ra.

Sau bài này, bạn có thể:

- Giải thích vị trí của `MessageListenerAdapter` trong Spring JMS.
- Phân biệt adapter với `jakarta.jms.MessageListener` và `SessionAwareMessageListener`.
- Gắn một POJO làm delegate và chọn phương thức nhận message.
- Hiểu tên phương thức mặc định, `setDefaultListenerMethod` và overload theo kiểu tham số.
- Điều khiển việc chuyển JMS Message thành payload bằng Spring JMS `MessageConverter`.
- Nhận message thô như `TextMessage` khi cần.
- Tạo reply từ giá trị trả về và định tuyến qua `JMSReplyTo` hoặc default response destination.
- Cấu hình adapter cùng listener container và xử lý lỗi/transaction.
- Phân biệt adapter này với cơ chế `@JmsListener`.
- Chạy ví dụ request/reply với Spring Boot và ActiveMQ Artemis embedded.

## 1. MessageListenerAdapter giải quyết vấn đề gì?

JMS định nghĩa interface chuẩn `jakarta.jms.MessageListener` với một callback:

~~~java
public interface MessageListener {
    void onMessage(Message message);
}
~~~

Một class implement interface này phải làm việc trực tiếp với JMS Message. Nếu message là `TextMessage`, listener tự gọi `getText()`; nếu là `BytesMessage`, listener tự đọc bytes; nếu cần metadata, listener phải truy cập JMS headers/properties.

Ví dụ listener gắn chặt với JMS:

~~~java
public class RawOrderListener implements MessageListener {

    @Override
    public void onMessage(Message message) {
        if (message instanceof TextMessage textMessage) {
            try {
                String orderId = textMessage.getText();
                processOrder(orderId);
            }
            catch (JMSException ex) {
                throw new IllegalStateException(ex);
            }
        }
    }

    private void processOrder(String orderId) {
        // Business logic
    }
}
~~~

Cách này hợp lệ, nhưng class nghiệp vụ phải biết về JMS. Khi muốn tái sử dụng logic xử lý từ REST, scheduler hoặc một loại messaging khác, sự phụ thuộc này gây khó khăn.

`MessageListenerAdapter` đóng vai trò cầu nối:

~~~text
JMS Provider / Broker
        |
        v
Listener Container
        |
        v
MessageListenerAdapter
        |
        +--> đọc JMS Message
        |
        +--> MessageConverter
        |
        +--> chọn phương thức trên delegate
        |
        v
POJO delegate (business logic)
        |
        +--> void/null: chỉ xử lý
        |
        +--> object: chuyển thành JMS reply nếu có đích trả lời
~~~

Delegate có thể là POJO thông thường, không cần import JMS API và không cần implement `MessageListener`.

## 2. Các thành phần và package cần biết

`MessageListenerAdapter` nằm trong package:

~~~java
org.springframework.jms.listener.adapter.MessageListenerAdapter
~~~

Các thành phần liên quan:

| Thành phần | Package | Vai trò |
|---|---|---|
| `MessageListenerAdapter` | `org.springframework.jms.listener.adapter` | Chuyển callback JMS thành lời gọi phương thức delegate. |
| `AbstractAdaptableMessageListener` | `org.springframework.jms.listener.adapter` | Cung cấp hạ tầng trích xuất payload, converter và gửi response. |
| `MessageListener` | `jakarta.jms` | Callback chuẩn JMS với `onMessage(Message)`. |
| `SessionAwareMessageListener` | `org.springframework.jms.listener` | Callback Spring có thêm JMS Session để gửi reply trong cùng session. |
| `MessageConverter` | `org.springframework.jms.support.converter` | Chuyển JMS Message thành object và object thành JMS Message. |
| `DefaultMessageListenerContainer` | `org.springframework.jms.listener` | Quản lý consumer, thread, session, transaction và vòng đời listener. |
| `JmsTemplate` | `org.springframework.jms.core` | Gửi và nhận message đồng bộ. |

Không nhầm Spring JMS `MessageConverter` với `org.springframework.messaging.converter.MessageConverter`. Hai interface có package và ranh giới chuyển đổi khác nhau.

## 3. Adapter hoạt động như thế nào?

Khi broker giao một message cho listener container, container gọi adapter. Adapter thực hiện các bước chính:

1. Nhận JMS `Message` và, trong đường gọi của Spring, có thể nhận thêm `Session`.
2. Trích xuất nội dung từ JMS message bằng `MessageConverter`.
3. Xác định tên phương thức delegate cần gọi.
4. Tạo danh sách tham số và tìm phương thức tương thích trên delegate.
5. Gọi phương thức bằng reflection.
6. Nếu phương thức trả về object khác null và có session phù hợp, chuyển object thành JMS response message rồi gửi tới response destination.

Ví dụ:

~~~java
MessageListenerAdapter adapter =
        new MessageListenerAdapter(new OrderDelegate());

adapter.setDefaultListenerMethod("processOrder");
~~~

Khi nhận một `TextMessage` chứa `ORD-42`, converter mặc định có thể trích xuất String `"ORD-42"`. Adapter gọi:

~~~java
delegate.processOrder("ORD-42");
~~~

POJO không cần biết message ban đầu là JMS `TextMessage`. Nếu converter được thay đổi, cùng một delegate method có thể nhận kiểu payload khác.

## 4. Delegate object và phương thức mặc định

Có hai cách cung cấp phương thức xử lý:

- Truyền một delegate object vào constructor hoặc gọi `setDelegate`.
- Không truyền delegate; khi đó các phương thức xử lý phải được định nghĩa trong một subclass của adapter.

Ví dụ delegate:

~~~java
public class OrderDelegate {

    public void handleMessage(String orderId) {
        System.out.println("processing order=" + orderId);
    }
}
~~~

Cấu hình adapter:

~~~java
@Bean
MessageListenerAdapter orderMessageListener(OrderDelegate delegate) {
    return new MessageListenerAdapter(delegate);
}
~~~

Tên phương thức mặc định là `handleMessage`. Đây là giá trị của hằng `ORIGINAL_DEFAULT_LISTENER_METHOD`.

Nếu POJO dùng tên khác, cấu hình rõ ràng:

~~~java
@Bean
MessageListenerAdapter orderMessageListener(OrderDelegate delegate) {
    MessageListenerAdapter adapter = new MessageListenerAdapter(delegate);
    adapter.setDefaultListenerMethod("processOrder");
    return adapter;
}
~~~

Delegate tương ứng:

~~~java
public class OrderDelegate {

    public void processOrder(String orderId) {
        System.out.println("processing order=" + orderId);
    }
}
~~~

Tên trong `setDefaultListenerMethod` phải khớp với phương thức có thể được gọi trên delegate. Nếu sai tên hoặc không có phương thức phù hợp với tham số sau conversion, việc dispatch tới delegate thất bại.

`setDefaultListenerMethod` chỉ đặt tên phương thức mặc định. Nó không tự tạo phương thức và cũng không tự quyết định queue/topic.

## 5. Ánh xạ theo kiểu tham số và method overloading

Adapter có thể dùng nhiều phương thức cùng tên nhưng nhận các kiểu payload khác nhau.

~~~java
public class MessageDelegate {

    public void handleMessage(String text) {
        System.out.println("text=" + text);
    }

    public void handleMessage(Map<?, ?> values) {
        System.out.println("map=" + values);
    }

    public void handleMessage(byte[] bytes) {
        System.out.println("bytes=" + bytes.length);
    }

    public void handleMessage(Serializable value) {
        System.out.println("serializable=" + value.getClass().getSimpleName());
    }
}
~~~

Nếu converter trích xuất payload thành String, adapter tìm overload tương thích với String. Nếu converter trả về Map hoặc byte array, overload phù hợp có thể được chọn.

Cách tổ chức này hữu ích khi một destination nhận nhiều kiểu JMS message. Tuy nhiên, cần thiết kế method signature rõ ràng:

- Tránh nhiều overload có kiểu tham số quá rộng và cùng tương thích với một payload.
- Ưu tiên kiểu cụ thể như String, Map hoặc byte array.
- Nếu các định dạng khác nhau cần quy trình nghiệp vụ khác nhau, dùng tên method riêng hoặc destination riêng để code dễ đọc.
- Không giả định adapter tự đọc một header tùy ý rồi đổi tên method. Mặc định, tên phương thức là tên đã cấu hình.

Trong implementation mặc định, `getListenerMethodName(originalMessage, extractedMessage)` trả về default listener method. Có thể subclass `MessageListenerAdapter` và override phương thức này nếu cần chọn tên method dựa trên JMS message hoặc nội dung đã trích xuất. Đây là extension point nâng cao; phải kiểm tra loại message, method tồn tại và routing policy một cách rõ ràng.

## 6. MessageConverter mặc định và kiểu payload delegate nhận được

`MessageListenerAdapter` mặc định sử dụng Spring JMS `SimpleMessageConverter`. Converter này trích xuất nội dung phù hợp từ các loại JMS message thường gặp:

| JMS message | Payload delegate thường nhận |
|---|---|
| `TextMessage` | `String` |
| `BytesMessage` | `byte[]` |
| `MapMessage` | `Map` |
| `ObjectMessage` | Object Serializable |
| JMS `Message` không có body | Tùy kiểu message và converter |

Ví dụ:

- Gửi một `TextMessage` chứa `ORD-42`: delegate method có thể nhận `String`.
- Gửi một `BytesMessage`: delegate method có thể nhận `byte[]`.
- Gửi một `MapMessage`: delegate method có thể nhận `Map`.

Đây là chuyển đổi của Spring JMS, không phải serialize JSON tự động. Nếu cần JSON thành POJO, cấu hình một converter JSON phù hợp trong Spring JMS và thống nhất schema giữa producer/consumer.

### Đặt converter riêng

~~~java
MessageListenerAdapter adapter = new MessageListenerAdapter(delegate);
adapter.setMessageConverter(customJmsMessageConverter);
~~~

Converter được dùng cho cả hai chiều:

- Inbound: JMS Message thành tham số của delegate method.
- Outbound: object trả về từ delegate thành JMS response Message.

Nếu converter không thể chuyển đổi payload, adapter không thể gọi delegate theo kiểu mong muốn. Hãy kiểm tra lỗi conversion, JMS message type và target parameter.

### Khi muốn nhận JMS Message thô

Nếu delegate cần đọc trực tiếp JMS headers, properties hoặc gọi API đặc thù như `TextMessage.getText()`, có thể tắt chuyển đổi tự động bằng cách đặt converter thành null:

~~~java
MessageListenerAdapter adapter = new MessageListenerAdapter(delegate);
adapter.setDefaultListenerMethod("receiveRaw");
adapter.setMessageConverter(null);
~~~

Delegate nhận đối tượng JMS Message:

~~~java
public class RawDelegate {

    public void receiveRaw(TextMessage message) throws JMSException {
        System.out.println("raw text=" + message.getText());
    }
}
~~~

Khi converter là null, phương thức delegate cần nhận đúng loại JMS Message được gửi tới. Ví dụ trên yêu cầu message là `TextMessage`; nếu nhận loại khác, lời gọi có thể thất bại do kiểu tham số không tương thích.

## 7. Adapter hỗ trợ reply như thế nào?

Một khả năng quan trọng là delegate method có thể trả về object. Nếu kết quả khác null, adapter có thể chuyển nó thành JMS Message và gửi response.

Ví dụ:

~~~java
public class OrderDelegate {

    public String processOrder(String orderId) {
        return "accepted:" + orderId;
    }
}
~~~

Khi nhận request `ORD-42`, phương thức trả về `"accepted:ORD-42"`. Với converter mặc định, String thường được chuyển thành JMS `TextMessage`.

Adapter xác định response destination theo thứ tự:

1. Destination trong header JMS `JMSReplyTo` của request.
2. Default response destination được cấu hình trên adapter.
3. Nếu không có destination nào, adapter ném `InvalidDestinationException`.

Có thể cấu hình default response destination:

~~~java
adapter.setDefaultResponseQueueName("orders.reply");
~~~

Hoặc truyền một đối tượng `Destination`:

~~~java
adapter.setDefaultResponseDestination(replyQueue);
~~~

Nếu ứng dụng cần topic mặc định, API tương ứng là `setDefaultResponseTopicName`. Adapter dùng `DestinationResolver` để resolve tên response destination.

### Không có reply khi method trả void hoặc null

- Method trả `void`: adapter không có object response để gửi.
- Method trả `null`: adapter không gửi response.
- Method trả object khác null: adapter xử lý response destination và gửi JMS message.

Nếu method trả object nhưng request không có `JMSReplyTo` và adapter không có default destination, request processing có thể gặp lỗi vì không xác định được nơi gửi response. Hãy chỉ trả về response khi reply path đã được thiết kế.

### Reply cần SessionAwareMessageListener

`MessageListenerAdapter` triển khai cả JMS `MessageListener` và Spring `SessionAwareMessageListener`. Tuy nhiên, hai entry point không có cùng khả năng:

| Entry point | Có Session? | Có thể gửi response từ return value? |
|---|---|---|
| `onMessage(Message)` của JMS `MessageListener` | Không | Không |
| `onMessage(Message, Session)` của Spring `SessionAwareMessageListener` | Có | Có |

Khi adapter được sử dụng trong Spring listener container, container có thể gọi entry point SessionAware để adapter gửi reply bằng session hiện tại. Nếu đăng ký adapter trực tiếp như một JMS `MessageListener` chuẩn ngoài cơ chế SessionAware, không dựa vào return value để gửi response.

Đây là lý do ví dụ request/reply nên sử dụng Spring listener container.

## 8. MessageListenerAdapter và listener container

Adapter không tự kết nối tới broker và không tự subscribe queue/topic. Listener container đảm nhiệm việc:

- Tạo và quản lý connection/session/consumer.
- Đăng ký listener với destination.
- Nhận message và gọi adapter.
- Quản lý thread, concurrency, recovery và lifecycle.
- Áp dụng acknowledgement/transaction policy.

Ví dụ cấu hình:

~~~java
@Bean
MessageListenerAdapter orderMessageListener(OrderDelegate delegate) {
    MessageListenerAdapter adapter = new MessageListenerAdapter(delegate);
    adapter.setDefaultListenerMethod("processOrder");
    return adapter;
}

@Bean
DefaultMessageListenerContainer orderListenerContainer(
        ConnectionFactory connectionFactory,
        MessageListenerAdapter orderMessageListener) {

    DefaultMessageListenerContainer container =
            new DefaultMessageListenerContainer();
    container.setConnectionFactory(connectionFactory);
    container.setDestinationName("orders.queue");
    container.setMessageListener(orderMessageListener);
    container.setSessionTransacted(true);
    return container;
}
~~~

`setDestinationName` cho phép container resolve destination theo tên. Với queue mặc định, domain phải được cấu hình đúng. Nếu ứng dụng dùng topic, cần cấu hình pub-sub domain tương ứng và bảo đảm broker có topic phù hợp.

### Vì sao cần listener container?

Nếu chỉ tạo adapter mà không đăng ký nó với provider hoặc listener container, adapter sẽ không tự nhận message.

Trong ứng dụng Spring, container thường là `DefaultMessageListenerContainer` hoặc `SimpleMessageListenerContainer`. `DefaultMessageListenerContainer` phù hợp với phần lớn use case cần concurrency, recovery và transaction linh hoạt.

## 9. Lỗi và transaction

Lỗi có thể xuất hiện ở nhiều giai đoạn:

| Giai đoạn | Ví dụ |
|---|---|
| JMS receive | Provider hoặc connection gặp lỗi. |
| Payload extraction | MessageConverter không đọc được message type/body. |
| Method resolution | Delegate không có method phù hợp hoặc method name cấu hình sai. |
| Delegate execution | Nghiệp vụ ném exception. |
| Reply conversion | Return object không được converter hỗ trợ. |
| Reply routing | Không có JMSReplyTo/default destination hoặc destination không hợp lệ. |
| Reply send | Provider từ chối gửi response hoặc session lỗi. |

Cách exception được xử lý phụ thuộc entry point và container:

- Với entry point JMS `MessageListener.onMessage(Message)`, adapter gọi `handleListenerException` khi có lỗi; implementation mặc định log lỗi.
- Với Spring `SessionAwareMessageListener` entry point, exception được trả về caller/container để xử lý.
- Listener container quyết định transaction, rollback, recovery và redelivery theo cấu hình.
- Không mặc định mọi exception đều được trả về producer. Producer đã gửi request thường cần nhận lỗi qua reply/error protocol riêng.

### Local JMS transaction

Có thể bật local transaction trên listener container:

~~~java
container.setSessionTransacted(true);
~~~

Khi listener xử lý lỗi, session có thể rollback và broker giao lại message theo semantics của provider. Reply gửi qua cùng session nằm trong local JMS transaction đó.

Database transaction không tự động tham gia cùng local JMS transaction. Nếu database đã commit nhưng JMS rollback, message có thể được giao lại và nghiệp vụ chạy lần nữa. Vì vậy delegate cần idempotent hoặc dùng event/business key để phát hiện xử lý trùng.

Nếu cần transaction phối hợp JMS và database, cần XA/JTA hoặc một kiến trúc như transactional outbox phù hợp với yêu cầu hệ thống.

## 10. Delegate phải thread-safe

Listener container có thể chạy nhiều consumer đồng thời. Một delegate singleton có thể được nhiều thread gọi cùng lúc.

Do đó:

- Ưu tiên delegate stateless, giữ dependency qua constructor injection.
- Không lưu payload hiện tại trong field dùng chung.
- Không dùng mutable collection không đồng bộ để lưu kết quả message.
- Nếu có cache hoặc counter dùng chung, dùng cấu trúc thread-safe hoặc synchronization phù hợp.
- Cấu hình concurrency dựa trên năng lực database và downstream service, không chỉ dựa trên số thread có thể tạo.

Một lỗi phổ biến là dùng một field `currentOrderId` trong delegate rồi giả định chỉ có một message được xử lý tại một thời điểm. Khi container tăng concurrency, dữ liệu giữa hai message có thể ghi đè lẫn nhau.

## 11. Phân biệt MessageListenerAdapter với @JmsListener

Hai cơ chế có liên quan nhưng không phải cùng một class:

| Cơ chế | Thành phần chính | Cách hoạt động |
|---|---|---|
| Classic POJO adapter | `MessageListenerAdapter` | Gọi method delegate theo tên mặc định/cấu hình và kiểu payload đã convert. |
| Annotation-based endpoint | `@JmsListener` và `MessagingMessageListenerAdapter` | Dùng method invocation infrastructure, argument resolver, annotation và message handler method factory. |

Ví dụ annotation:

~~~java
@Component
public class AnnotatedOrderListener {

    @JmsListener(destination = "orders.queue")
    public String processOrder(String orderId) {
        return "accepted:" + orderId;
    }
}
~~~

Cơ chế `@JmsListener` có thể sử dụng `@SendTo` để chỉ định response destination:

~~~java
@JmsListener(destination = "orders.queue")
@SendTo("orders.reply")
public String processOrder(String orderId) {
    return "accepted:" + orderId;
}
~~~

Chọn `MessageListenerAdapter` khi cần gắn một POJO hoặc một delegate method vào JMS listener container theo cấu hình tường minh. Chọn `@JmsListener` khi muốn khai báo endpoint ngay trên method, dùng annotation để bind payload/header và quản lý reply theo messaging annotation.

Không dùng `@JmsListener` và `MessageListenerAdapter` như thể hai tên gọi của cùng một class. Spring dùng `MessagingMessageListenerAdapter` cho annotation-based endpoint.

## 12. Ví dụ Java 17+ chạy được: POJO delegate và request/reply

Ví dụ sử dụng Spring Boot 4.1.2 và embedded ActiveMQ Artemis. Ứng dụng gửi một JMS request tới `orders.queue`, request đặt `JMSReplyTo` là `orders.reply`; adapter chuyển TextMessage thành String, gọi POJO method và gửi String response về reply queue.

### Cấu trúc project

~~~text
message-listener-adapter-demo/
  pom.xml
  src/
    main/
      java/
        demo/
          MessageListenerAdapterApplication.java
          OrderDelegate.java
      resources/
        application.properties
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>message-listener-adapter-demo</artifactId>
    <version>1.0.0</version>

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
            <scope>runtime</scope>
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

### application.properties

~~~properties
spring.artemis.mode=embedded
spring.artemis.embedded.queues=orders.queue,orders.reply
spring.artemis.embedded.persistent=false
spring.jms.pub-sub-domain=false
~~~

Cấu hình trên tạo hai queue trong broker embedded. Đây là cấu hình demo trong bộ nhớ, không phải cấu hình durability cho production.

### OrderDelegate.java

~~~java
package demo;

public class OrderDelegate {

    public String processOrder(String orderId) {
        System.out.println("delegate received=" + orderId);
        return "accepted:" + orderId;
    }
}
~~~

POJO này không implement `MessageListener` và không import `jakarta.jms`.

### MessageListenerAdapterApplication.java

~~~java
package demo;

import jakarta.jms.ConnectionFactory;
import jakarta.jms.TextMessage;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.listener.DefaultMessageListenerContainer;
import org.springframework.jms.listener.adapter.MessageListenerAdapter;

@SpringBootApplication
public class MessageListenerAdapterApplication {

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                     SpringApplication.run(MessageListenerAdapterApplication.class, args)) {
            // ApplicationRunner sends the request and waits for the reply.
        }
    }

    @Bean
    OrderDelegate orderDelegate() {
        return new OrderDelegate();
    }

    @Bean
    MessageListenerAdapter orderMessageListener(OrderDelegate delegate) {
        MessageListenerAdapter adapter = new MessageListenerAdapter(delegate);
        adapter.setDefaultListenerMethod("processOrder");
        return adapter;
    }

    @Bean
    DefaultMessageListenerContainer orderListenerContainer(
            ConnectionFactory connectionFactory,
            MessageListenerAdapter orderMessageListener) {

        DefaultMessageListenerContainer container =
                new DefaultMessageListenerContainer();
        container.setConnectionFactory(connectionFactory);
        container.setDestinationName("orders.queue");
        container.setMessageListener(orderMessageListener);
        container.setSessionTransacted(true);
        return container;
    }

    @Bean
    ApplicationRunner requestReply(
            JmsTemplate jmsTemplate) {

        return args -> {
            jmsTemplate.setReceiveTimeout(5_000);

            jmsTemplate.send("orders.queue", session -> {
                TextMessage request = session.createTextMessage("ORD-42");
                request.setJMSReplyTo(session.createQueue("orders.reply"));
                return request;
            });

            Object response = jmsTemplate.receiveAndConvert("orders.reply");
            if (!(response instanceof String reply)) {
                throw new IllegalStateException("No String reply received");
            }

            System.out.println("reply=" + reply);
        };
    }
}
~~~

Chạy bằng Java 17+ và Maven:

~~~bash
mvn spring-boot:run
~~~

Các dòng stdout do ứng dụng in ra (bỏ qua log khởi động Spring Boot):

~~~text
delegate received=ORD-42
reply=accepted:ORD-42
~~~

### Giải thích luồng chạy

1. Spring Boot khởi tạo embedded Artemis và hai queue `orders.queue`, `orders.reply`.
2. Spring tạo POJO `OrderDelegate`.
3. `MessageListenerAdapter` nhận delegate và cấu hình method mặc định là `processOrder`.
4. `DefaultMessageListenerContainer` đăng ký adapter làm listener của `orders.queue`.
5. `JmsTemplate` gửi một TextMessage chứa `ORD-42` và đặt `JMSReplyTo` là `orders.reply`.
6. Container nhận request và gọi adapter qua SessionAware entry point.
7. Converter mặc định chuyển TextMessage thành String.
8. Adapter gọi `OrderDelegate.processOrder("ORD-42")`.
9. Delegate trả về `accepted:ORD-42`; adapter chuyển String thành TextMessage và gửi đến destination trong `JMSReplyTo`.
10. `JmsTemplate.receiveAndConvert` nhận reply và chuyển TextMessage thành String.

`receiveTimeout` được đặt để chương trình không chờ vô hạn nếu listener hoặc reply path bị lỗi. `sessionTransacted=true` giúp request receive và response send tham gia cùng local JMS transaction. Database hoặc hệ thống ngoài vẫn cần transaction/idempotency riêng.

## 13. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Không gọi được delegate method | Tên method mặc định sai hoặc không có method phù hợp | Kiểm tra `setDefaultListenerMethod` và tham số sau conversion |
| Delegate nhận TextMessage thay vì String | Converter bị đặt null hoặc converter tùy chỉnh trả raw message | Kiểm tra `setMessageConverter` |
| Delegate cần TextMessage nhưng nhận String | Converter mặc định đang trích xuất body | Đặt converter null nếu thực sự cần JMS Message thô |
| Method overload không được chọn như mong muốn | Kiểu payload tương thích với nhiều overload | Dùng kiểu cụ thể hoặc method name riêng |
| Không gửi được reply | Request thiếu `JMSReplyTo` và adapter không có default response destination | Đặt JMSReplyTo hoặc cấu hình default response destination |
| Reply gửi tới sai queue/topic | Reply destination hoặc resolver không đúng | Kiểm tra JMSReplyTo, resolver và destination provisioning |
| Method trả null nhưng client chờ reply | Không có response được gửi | Quy định rõ null/void semantics hoặc trả response object |
| Return value không chuyển được thành JMS Message | MessageConverter không hỗ trợ kiểu trả về | Cấu hình converter phù hợp |
| Listener exception không tới producer | Exception được xử lý tại adapter/container; request/reply không có error protocol | Thiết kế error response hoặc error destination riêng |
| Xử lý trùng message | Rollback/redelivery hoặc crash sau khi nghiệp vụ đã commit | Dùng idempotency key và transaction phù hợp |
| Delegate có race condition | Listener container gọi cùng delegate từ nhiều thread | Giữ delegate stateless/thread-safe |

## 14. Checklist triển khai

- [ ] Delegate là POJO có method nhận payload theo kiểu converter tạo ra.
- [ ] Method name khớp với default listener method hoặc custom routing.
- [ ] Method signature không mơ hồ khi dùng overload.
- [ ] Converter đúng với loại JMS message và định dạng payload.
- [ ] Chỉ tắt converter khi delegate thực sự cần JMS Message thô.
- [ ] Listener container đăng ký adapter với đúng queue/topic.
- [ ] Nếu method trả object, có JMSReplyTo hoặc default response destination.
- [ ] Reply converter hỗ trợ kiểu return.
- [ ] Reply flow dùng SessionAwareMessageListener entry point.
- [ ] Transaction/acknowledgement/redelivery được cấu hình có chủ đích.
- [ ] Delegate thread-safe khi container có concurrency lớn hơn một.
- [ ] Có test với payload hợp lệ, sai kiểu, method không tồn tại, reply-to thiếu và reply send failure.
- [ ] Không log toàn bộ message nếu body/properties có dữ liệu nhạy cảm.

## Ghi nhớ

- `MessageListenerAdapter` nằm trong `spring-jms` và biến POJO thành message-driven listener.
- Adapter mặc định gọi `handleMessage`; dùng `setDefaultListenerMethod` để chọn tên khác.
- Adapter dùng Spring JMS `SimpleMessageConverter` mặc định để trích payload như String, byte array hoặc Map.
- Dùng converter null nếu muốn delegate nhận raw JMS Message như `TextMessage`.
- Delegate method trả về object khác null có thể tạo JMS response message.
- Reply được gửi tới request `JMSReplyTo` trước; nếu không có thì dùng default response destination.
- Reply cần entry point `SessionAwareMessageListener`; standard JMS `MessageListener.onMessage(Message)` không gửi response từ return value.
- Listener container quản lý kết nối, consumer, transaction, recovery và vòng đời adapter.
- `@JmsListener` dùng `MessagingMessageListenerAdapter`, là cơ chế annotated endpoint riêng.
- Delegate cần thread-safe và idempotent khi xử lý bất đồng bộ, retry hoặc redelivery.

## Tài liệu chính thức

- [Spring Framework Reference 7.0: Receiving a Message](https://docs.spring.io/spring-framework/reference/7.0/integration/jms/receiving.html)
- [Spring Framework 7.0.10 Javadoc: MessageListenerAdapter](https://docs.spring.io/spring-framework/docs/7.0.10/javadoc-api/org/springframework/jms/listener/adapter/MessageListenerAdapter.html)
- [Spring Framework 7.0.10 Javadoc: AbstractAdaptableMessageListener](https://docs.spring.io/spring-framework/docs/7.0.10/javadoc-api/org/springframework/jms/listener/adapter/AbstractAdaptableMessageListener.html)
- [Spring Framework Javadoc: DefaultMessageListenerContainer](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html)
- [Spring Framework Javadoc: MessageConverter for JMS](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/support/converter/MessageConverter.html)
- [Spring Framework Reference: Annotated JMS Listener Endpoints](https://docs.spring.io/spring-framework/reference/7.0/integration/jms/annotated.html)
- [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html)
