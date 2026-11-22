# So sánh Message của Spring với jakarta.jms.Message

Trong hệ sinh thái Java, từ “message” có thể chỉ một phong bì dữ liệu ở bên trong ứng dụng hoặc một thông điệp được gửi qua hệ thống messaging. Hai kiểu thường gặp là **org.springframework.messaging.Message<T>** của Spring Messaging và **jakarta.jms.Message** của Jakarta Messaging (JMS).

Cả hai đều mô tả dữ liệu đi kèm metadata, nhưng chúng phục vụ những tầng khác nhau:

- **Spring Message<T>** là abstraction message tổng quát của Spring. Nó mang payload có kiểu Java và headers để các thành phần trong ứng dụng trao đổi với nhau.
- **jakarta.jms.Message** là kiểu message của API JMS. Nó đại diện cho thông điệp được gửi/nhận qua một provider JMS, chẳng hạn broker hỗ trợ Jakarta Messaging, với body, JMS headers, properties và quy tắc gửi nhận của JMS.

Spring Message không phải là JMS Message. Khi ứng dụng cần dùng JMS, Spring JMS cung cấp converter và adapter để chuyển đổi giữa hai mô hình.

## 1. Hai interface và hai mục đích

### Spring Messaging Message<T>

Interface **org.springframework.messaging.Message<T>** có hai phần chính:

- **getPayload()** trả về dữ liệu chính với kiểu generic T.
- **getHeaders()** trả về metadata dưới dạng **MessageHeaders**.

Ví dụ:

~~~java
Message<String> message = MessageBuilder
        .withPayload("Order created")
        .setHeader("eventType", "OrderCreated")
        .setHeader("correlationId", "checkout-001")
        .build();
~~~

Thông điệp trên tồn tại như một object trong JVM. Nó có thể được truyền qua **MessageChannel**, xử lý bởi **MessageHandler**, đi qua Spring Integration hoặc được một adapter chuyển tiếp đến hạ tầng khác.

Bản thân interface này không quy định cách gửi message qua mạng, lưu message trên broker, bảo đảm giao nhận, retry hay xác nhận tiêu thụ. Những hành vi đó thuộc channel, adapter, broker và tầng tích hợp đang sử dụng.

### Jakarta Messaging Message

Interface **jakarta.jms.Message** thuộc Jakarta Messaging API. Nó mô tả một message trong mô hình JMS, gồm:

- Các JMS headers tiêu chuẩn, ví dụ **JMSMessageID**, **JMSTimestamp**, **JMSCorrelationID**, **JMSReplyTo** và **JMSDestination**.
- User-defined properties, ví dụ **eventType**, **schemaVersion** hoặc **tenantId**.
- Body, có thể được truy cập qua API body hoặc các interface con chuyên biệt.

JMS có những kiểu message phổ biến:

| Kiểu message | Nội dung body |
|---|---|
| **TextMessage** | Văn bản, thường dùng cho JSON, XML hoặc text. |
| **BytesMessage** | Dữ liệu nhị phân. |
| **MapMessage** | Tập các cặp tên/giá trị được hỗ trợ bởi JMS. |
| **StreamMessage** | Chuỗi giá trị được đọc/ghi theo thứ tự. |
| **ObjectMessage** | Một object Java được serialize theo cơ chế JMS. |
| **Message** | Message tổng quát, có thể không có body ứng dụng. |

Ví dụ tạo một **TextMessage** bằng JMS Session:

~~~java
TextMessage message = session.createTextMessage(
        "{\"orderId\":\"ORD-1001\",\"total\":125.50}"
);
message.setStringProperty("eventType", "OrderCreated");
message.setJMSCorrelationID("checkout-001");
~~~

Đoạn mã cần một **jakarta.jms.Session** đã được tạo từ **ConnectionFactory**; nó minh họa cách tạo message và gắn metadata. Việc gửi message còn cần producer hoặc **JMSContext/JMSProducer** tùy cách sử dụng API.

## 2. So sánh cấu trúc: payload/headers và body/headers/properties

| Khía cạnh | Spring **Message<T>** | Jakarta **Message** |
|---|---|---|
| Dữ liệu chính | Payload T, lấy bằng **getPayload()**. | Body, có thể lấy bằng API body hoặc interface con như **TextMessage**. |
| Metadata | **MessageHeaders**, một map header của Spring. | JMS headers tiêu chuẩn và user-defined properties. |
| Kiểu dữ liệu | Generic T giúp kiểm tra kiểu ở thời điểm biên dịch trong code Java. | Interface không generic; body và properties tuân theo kiểu dữ liệu JMS. |
| Định danh | Header **id** do Spring tạo nếu chưa có. | **JMSMessageID** thường do provider gán khi gửi. |
| Thời gian | Header **timestamp** của Spring ghi thời điểm tạo message trong ứng dụng. | **JMSTimestamp** thường do provider gán khi gửi message. |
| Đích | Không có destination phổ quát trong core Message; channel hoặc adapter quyết định đường đi. | **JMSDestination** mô tả destination JMS của message. |
| Phản hồi | Có thể dùng header **replyChannel** trong luồng Spring phù hợp. | Dùng **JMSReplyTo** với một JMS Destination. |
| Tương quan | Có thể dùng header do ứng dụng định nghĩa, hoặc abstraction của module khác. | Có header chuẩn **JMSCorrelationID**. |
| Giao nhận | Không định nghĩa broker acknowledgment hoặc delivery mode. | Tích hợp với session, producer, consumer, acknowledgment mode và delivery metadata của JMS. |
| Mục đích | Trao đổi message trong các abstraction của Spring. | Trao đổi message theo giao thức/API JMS giữa ứng dụng và provider. |

### Payload và body không phải cùng một kiểu hợp đồng

Spring Message<T> giữ payload dưới dạng object Java. Ví dụ payload có thể là một record **OrderCreated**. Khi message đi qua channel trong cùng JVM, consumer có thể nhận object đó mà chưa cần serialize.

JMS message được thiết kế để gửi qua provider. Body phải tuân theo một dạng message được JMS hỗ trợ hoặc được chuyển đổi thành dạng mà provider và consumer có thể trao đổi. Với JSON, body thường là chuỗi trong **TextMessage** hoặc bytes trong **BytesMessage**.

Generic T của Spring không được truyền tự động thành một schema trên broker. Nếu payload là **OrderCreated**, consumer ở một tiến trình khác cần biết cách deserialize JSON/bytes thành kiểu dữ liệu tương ứng.

### Headers của Spring và JMS properties

**MessageHeaders** có thể chứa metadata dạng object theo quy ước Spring. Các header thường gặp gồm **id**, **timestamp**, **contentType**, **replyChannel** và **errorChannel**; ứng dụng cũng có thể thêm header riêng.

JMS tách metadata thành hai nhóm:

- **JMS headers** là các trường chuẩn do API/provider định nghĩa, như **JMSCorrelationID**, **JMSReplyTo**, **JMSDestination**, **JMSDeliveryMode**, **JMSPriority**, **JMSExpiration** và **JMSRedelivered**.
- **JMS properties** là metadata do ứng dụng đặt tên. Giá trị property phải thuộc các kiểu JMS hỗ trợ như boolean, byte, short, int, long, float, double hoặc String. Không thể đặt tùy ý một Java object vào property như cách có thể đặt một object vào header map của Spring.

Ví dụ:

~~~java
jmsMessage.setStringProperty("eventType", "OrderCreated");
jmsMessage.setIntProperty("schemaVersion", 2);
jmsMessage.setBooleanProperty("requiresAudit", true);
~~~

Nếu metadata là một object phức tạp, hãy đưa nó vào body hoặc serialize thành chuỗi theo contract đã thống nhất.

## 3. Khác biệt về vòng đời và trách nhiệm giao nhận

Đây là khác biệt quan trọng khi chọn abstraction.

### Vòng đời của Spring Message

Spring Message là một object message trong mô hình lập trình Spring. Sau khi tạo, message thường được xem như một envelope bất biến: nếu cần thay đổi payload hoặc headers, tạo message mới bằng **MessageBuilder** hoặc accessor thích hợp.

Một luồng xử lý có thể diễn ra trong bộ nhớ:

~~~text
MessageBuilder
      |
      v
Message<T>
      |
      v
MessageChannel
      |
      v
MessageHandler
~~~

Message có thể được giữ trong queue nội bộ của một channel, nhưng hành vi queueing và dispatch phụ thuộc implementation của channel. Core Message không tự bảo đảm message đã được lưu bền vững hoặc consumer đã xử lý thành công.

### Vòng đời của JMS Message

JMS message đi qua các thành phần của API/provider:

~~~text
Producer
   |
   | send(message)
   v
JMS Provider / Broker
   |
   | deliver
   v
Consumer
   |
   | process + acknowledge
   v
Provider cập nhật trạng thái giao nhận
~~~

Provider và cấu hình JMS quyết định nhiều chi tiết: message được gửi vào destination nào, delivery mode persistent hay non-persistent, priority, expiration, redelivery và transaction.

JMS có các acknowledgment mode và transaction session. **jakarta.jms.Message** còn có phương thức **acknowledge()** trong chế độ **CLIENT_ACKNOWLEDGE**; việc xác nhận có phạm vi và hành vi theo session acknowledgment mode. Với các chế độ khác, provider/session quản lý việc xác nhận theo hợp đồng JMS. Vì vậy, không nên suy ra rằng gọi **getBody()** hoặc đọc một message đồng nghĩa với việc message đã được acknowledge.

Spring Message<T> không có phương thức **acknowledge()**. Khi ứng dụng dùng Spring JMS listener, việc xác nhận giao nhận vẫn phụ thuộc cấu hình listener container, session transaction và provider; object Spring Message được tạo ra cho tầng xử lý không thay thế các quy tắc giao nhận JMS.

### Ai gán ID và timestamp?

Các trường có tên gần giống nhau không nhất thiết có cùng nguồn gốc:

- Spring header **id** và **timestamp** được tạo ở phía ứng dụng khi xây dựng message, nếu cơ chế tạo mặc định đang bật.
- JMS **JMSMessageID** và **JMSTimestamp** thường do provider gán khi gửi. Provider có thể được cấu hình để tắt việc tạo timestamp; message trước khi gửi cũng chưa nhất thiết có các giá trị này.

Do đó, timestamp của Spring Message phản ánh thời điểm tạo envelope trong ứng dụng; **JMSTimestamp** phản ánh thời điểm gửi do provider ghi nhận. Nếu cần event time của nghiệp vụ, hãy đưa nó vào payload hoặc metadata theo contract riêng.

## 4. Destination, reply và correlation

Spring Messaging và JMS có cách biểu diễn địa chỉ khác nhau.

### Spring channel

**MessageChannel** là abstraction nhận message ở phía Spring. Producer gửi qua channel bằng **send(message)**. Tên channel và cách nó kết nối với handler hoặc adapter do cấu hình ứng dụng quyết định.

Core Spring Message không bắt buộc phải có một header tên **destination**. Với Spring Integration, routing có thể dựa vào channel, router hoặc header do ứng dụng quy ước. Với các adapter khác, địa chỉ có thể được ánh xạ từ cấu hình bên ngoài.

### JMS destination

JMS sử dụng **Destination**, thường là **Queue** hoặc **Topic**. Producer gửi message đến destination; consumer đăng ký nhận từ destination tương ứng.

Một số trường chuẩn:

- **JMSDestination**: destination mà provider gắn với message.
- **JMSReplyTo**: destination để consumer gửi phản hồi.
- **JMSCorrelationID**: định danh liên kết request và reply hoặc nhóm message liên quan.

Ví dụ tạo reply destination:

~~~java
Queue replyQueue = session.createQueue("orders.reply");
TextMessage request = session.createTextMessage("{\"orderId\":\"ORD-1001\"}");
request.setJMSReplyTo(replyQueue);
request.setJMSCorrelationID("checkout-001");
~~~

Đoạn mã trên minh họa các trường JMS. Queue được tạo ở đây là đối tượng destination theo tên; việc queue có được broker provision sẵn hay tự tạo phụ thuộc provider và môi trường.

### Không ánh xạ tên header một cách máy móc

**replyChannel** của Spring và **JMSReplyTo** của JMS đều có thể xuất hiện trong request/reply, nhưng chúng không phải cùng một kiểu đối tượng. Một cái có thể đại diện cho channel nội bộ của Spring; cái kia là JMS Destination.

Tương tự, header **correlationId** do ứng dụng đặt trong Spring không tự động trở thành **JMSCorrelationID**. Adapter hoặc header mapper phải quy định rõ cách ánh xạ. Nếu tự xây dựng adapter, cần thống nhất tên, kiểu và quy tắc xử lý khi thiếu giá trị.

## 5. Chuyển đổi giữa Spring Message và JMS Message

Khi dùng JMS trong ứng dụng Spring, thông thường không cần tự sao chép từng trường giữa hai interface. Module **Spring JMS** cung cấp các converter để chuyển đổi payload và metadata.

Cần phân biệt hai abstraction converter:

- **org.springframework.messaging.converter.MessageConverter** thuộc Spring Messaging, chuyển đổi giữa payload/object và dạng message của Spring.
- **org.springframework.jms.support.converter.MessageConverter** thuộc Spring JMS, chuyển đổi giữa object ứng dụng và **jakarta.jms.Message**.

Spring JMS còn có **MessagingMessageConverter**, một adapter tích hợp hai mô hình. Nó chuyển đổi JMS message thành Spring Messaging Message và ngược lại, sử dụng payload converter cùng header mapper để xử lý body và metadata.

Có thể hình dung:

~~~text
Ứng dụng Spring
    |
    | Message<OrderCreated>
    v
MessagingMessageConverter
    |
    | payload converter + JMS header mapper
    v
jakarta.jms.Message
    |
    v
JMS Provider / Broker
~~~

Chiều nhận diễn ra ngược lại: Spring JMS đọc JMS message, chuyển body thành payload phù hợp và ánh xạ những header được hỗ trợ vào Spring Message.

### Ví dụ gửi và nhận bằng Spring JMS

Với **JmsTemplate**, ứng dụng có thể gửi object qua **convertAndSend** nếu đã cấu hình một JMS MessageConverter phù hợp:

~~~java
jmsTemplate.convertAndSend("orders.queue", orderCreated);
~~~

Ở phía nhận, listener có thể nhận DTO nếu converter của listener container chuyển body thành đúng kiểu:

~~~java
@JmsListener(destination = "orders.queue")
public void handle(OrderCreated event) {
    orderService.process(event);
}
~~~

Đây là các đoạn mã minh họa phần gửi/nhận; chúng cần **ConnectionFactory**, cấu hình converter, destination và broker phù hợp. Nếu không cấu hình converter cho JSON hoặc kiểu DTO, converter mặc định có thể xử lý các kiểu đơn giản nhưng không tự bảo đảm mọi object đều được chuyển thành JSON.

### Chọn converter theo contract

- Dùng converter văn bản/JSON khi nhiều service cần trao đổi dữ liệu có schema rõ ràng.
- Dùng bytes khi payload là định dạng nhị phân hoặc ứng dụng tự kiểm soát serialization.
- Chỉ dùng object serialization khi cả hai phía kiểm soát chặt phiên bản class và chấp nhận các rủi ro về tương thích, bảo mật và phụ thuộc Java.
- Kiểm tra header mapper để biết header nào được ánh xạ giữa Spring và JMS; không giả định mọi header nội bộ đều được chuyển tiếp.

## 6. Ví dụ chạy được với Spring Message<T>

Ví dụ sau tạo Spring Message thuần để thấy payload và headers. Nó không cần broker JMS, bởi mục tiêu là minh họa abstraction của Spring Messaging.

### Maven

Tạo file **pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>spring-message-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-messaging</artifactId>
            <version>6.1.8</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.2.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### Java

Tạo file **src/main/java/com/example/messaging/SpringMessageExample.java**:

~~~java
package com.example.messaging;

import java.math.BigDecimal;
import java.time.Instant;

import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.util.MimeTypeUtils;

public class SpringMessageExample {

    public record OrderCreated(
            String orderId,
            BigDecimal total,
            Instant occurredAt
    ) {
    }

    public static void main(String[] args) {
        OrderCreated payload = new OrderCreated(
                "ORD-1001",
                new BigDecimal("125.50"),
                Instant.parse("2026-11-07T03:00:00Z")
        );

        Message<OrderCreated> message = MessageBuilder
                .withPayload(payload)
                .setHeader(
                        MessageHeaders.CONTENT_TYPE,
                        MimeTypeUtils.APPLICATION_JSON
                )
                .setHeader("eventType", "OrderCreated")
                .setHeader("correlationId", "checkout-001")
                .build();

        System.out.println("payloadType="
                + message.getPayload().getClass().getSimpleName());
        System.out.println("orderId=" + message.getPayload().orderId());
        System.out.println("contentType="
                + message.getHeaders().get(MessageHeaders.CONTENT_TYPE));
        System.out.println("eventType="
                + message.getHeaders().get("eventType"));
        System.out.println("correlationId="
                + message.getHeaders().get("correlationId"));
        System.out.println("idPresent="
                + (message.getHeaders().get(MessageHeaders.ID) != null));
        System.out.println("timestampPresent="
                + (message.getHeaders().get(MessageHeaders.TIMESTAMP) != null));
    }
}
~~~

Chạy từ thư mục chứa **pom.xml**:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=com.example.messaging.SpringMessageExample
~~~

Output:

~~~text
payloadType=OrderCreated
orderId=ORD-1001
contentType=application/json
eventType=OrderCreated
correlationId=checkout-001
idPresent=true
timestampPresent=true
~~~

Ví dụ cho thấy **Message<T>** giữ nguyên object **OrderCreated** làm payload. Header content type mô tả định dạng dự kiến nếu payload được chuyển đổi, nhưng việc gọi **MessageBuilder** không tự serialize record thành JSON và cũng không gửi message qua broker.

## 7. Khi nào dùng từng loại?

| Nhu cầu | Lựa chọn phù hợp |
|---|---|
| Truyền payload và metadata giữa các thành phần Spring trong JVM. | **org.springframework.messaging.Message<T>**. |
| Gửi/nhận message qua JMS provider hoặc broker hỗ trợ JMS. | **jakarta.jms.Message** cùng **ConnectionFactory**, producer/consumer hoặc Spring JMS. |
| Xử lý channel và handler theo abstraction của Spring. | Spring Messaging và **MessageChannel**. |
| Cần queue/topic, JMS headers, properties, delivery mode và acknowledgment. | Jakarta Messaging API và provider JMS. |
| Muốn dùng Spring abstraction nhưng vận chuyển bằng JMS. | Spring JMS converter/adapter, chẳng hạn **MessagingMessageConverter**, cùng listener container hoặc **JmsTemplate**. |
| Trao đổi message giữa nhiều ngôn ngữ hoặc service độc lập. | Chọn wire format và schema rõ ràng như JSON/Avro/Protobuf; dùng JMS hoặc broker phù hợp nếu cần transport. |

Trong một ứng dụng Spring Boot, có thể dùng Spring Messaging ở tầng xử lý nội bộ và Spring JMS ở tầng giao tiếp broker. Hai kiểu message cùng xuất hiện trong một luồng nhưng mỗi kiểu giữ trách nhiệm của tầng mình.

## 8. Những nhầm lẫn thường gặp

1. **“Spring Message<T> chính là JMS Message.”** Không đúng. Một cái là abstraction message của Spring, một cái thuộc Jakarta Messaging API.
2. **“Payload của Spring luôn được serialize khi tạo Message.”** Không đúng. **MessageBuilder** chỉ tạo envelope trong bộ nhớ. Serialization xảy ra khi converter hoặc adapter thực hiện.
3. **“JMS properties có thể chứa mọi object Java.”** Không đúng. JMS properties chỉ hỗ trợ các kiểu dữ liệu được JMS quy định; dữ liệu phức tạp thuộc body hoặc phải serialize.
4. **“Spring headers và JMS headers là cùng một tập trường.”** Không đúng. Spring có header map riêng; JMS có trường chuẩn và properties với quy tắc riêng. Cần header mapper để chuyển đổi.
5. **“Spring Message có acknowledgment như JMS.”** Không đúng. Core Spring Message không quản lý acknowledgment; JMS Message có API **acknowledge()** và việc xác nhận còn phụ thuộc session mode.
6. **“timestamp của Spring và JMSTimestamp có cùng ý nghĩa.”** Không nhất thiết. Spring ghi thời điểm tạo message trong ứng dụng; JMS provider thường ghi thời điểm gửi.
7. **“replyChannel và JMSReplyTo có thể thay thế trực tiếp cho nhau.”** Không đúng. Một cái là metadata phục vụ luồng Spring; cái kia là JMS Destination.
8. **“Đã dùng Spring Boot thì không cần biết JMS API.”** Không đúng nếu ứng dụng giao tiếp với JMS provider. Hiểu destination, body, headers, properties, acknowledgment và transaction vẫn rất quan trọng.
9. **“Chỉ cần đổi import javax.jms thành jakarta.jms là mọi phiên bản tương thích.”** Không đúng. Spring Framework 6 và Spring Boot 3 chuyển sang namespace Jakarta; cần chọn phiên bản JMS provider, API và thư viện Spring tương thích với nhau.

## 9. Ghi nhớ

- **org.springframework.messaging.Message<T>** gồm payload có kiểu Java và **MessageHeaders**; nó là abstraction trao đổi message của Spring.
- **jakarta.jms.Message** mô tả message theo Jakarta Messaging, với body, JMS headers, properties và quy tắc giao nhận của provider.
- Spring Message không tự cung cấp broker, delivery guarantee hay acknowledgment.
- JMS Message tham gia vào giao nhận qua session/provider; delivery mode, destination, expiration, priority và acknowledgment thuộc hợp đồng JMS.
- Spring JMS có converter và adapter để nối hai mô hình; cần hiểu rõ payload conversion và header mapping.
- Khi trao đổi giữa các hệ thống, hãy thống nhất wire format và schema thay vì phụ thuộc vào generic type hoặc Java class của một tiến trình.

Hãy xác định trước message đang phục vụ giao tiếp nội bộ trong Spring hay giao tiếp qua provider JMS. Từ đó chọn đúng abstraction, converter và nơi chịu trách nhiệm cho định tuyến, serialization và giao nhận.
