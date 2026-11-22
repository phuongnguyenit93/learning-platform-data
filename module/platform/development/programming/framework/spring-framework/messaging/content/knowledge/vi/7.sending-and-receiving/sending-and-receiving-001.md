# MessageSendingOperations và gửi thông điệp tới một đích

Trong Spring Messaging, **MessageSendingOperations<D>** là abstraction dành cho phía gửi: ứng dụng gửi một message đã được tạo hoặc gửi payload để framework chuyển thành message rồi chuyển đến một đích. Interface này giúp code nghiệp vụ làm việc với thao tác gửi theo destination mà không phải tự xây dựng mọi bước chuyển đổi và đóng gói message.

Điểm quan trọng là **destination không có một ý nghĩa cố định cho mọi implementation**. Với một template cụ thể, destination có thể là đường dẫn STOMP, tên logical destination hoặc một địa chỉ do adapter định nghĩa. Interface chỉ cung cấp hợp đồng gửi; implementation quyết định destination được ánh xạ vào channel hoặc transport như thế nào.

## 1. MessageSendingOperations là gì?

Interface **org.springframework.messaging.core.MessageSendingOperations<D>** thuộc Spring Messaging. Tham số generic D biểu diễn kiểu dữ liệu destination mà implementation chấp nhận. Trong trường hợp destination là chuỗi, kiểu thường dùng là **MessageSendingOperations<String>**.

Hai nhóm thao tác cốt lõi:

- **send(destination, message):** gửi một Spring Message đã có payload và headers đến destination chỉ định.
- **convertAndSend(destination, payload):** chuyển payload thành Spring Message bằng MessageConverter, sau đó gửi message đến destination.

Có thể hình dung:

~~~text
Ứng dụng
   |
   | send(destination, Message)
   | hoặc convertAndSend(destination, payload)
   v
MessageSendingOperations<D>
   |
   +-- MessageConverter (khi cần)
   |
   +-- gắn destination / headers theo implementation
   |
   v
Channel hoặc transport đích
~~~

MessageSendingOperations là abstraction phía producer. Nó không phải broker, không phải queue và cũng không tự định nghĩa cách consumer nhận message. Những trách nhiệm đó thuộc implementation, channel và hạ tầng transport.

### Các phương thức thường dùng

| Phương thức | Mục đích |
|---|---|
| **send(destination, message)** | Gửi một Message đã được tạo đến destination chỉ định. |
| **send(message)** | Gửi message đến default destination nếu implementation đã cấu hình đích mặc định. |
| **convertAndSend(destination, payload)** | Chuyển payload thành Message rồi gửi đến destination. |
| **convertAndSend(destination, payload, headers)** | Gửi payload kèm headers do ứng dụng cung cấp. |
| **convertAndSend(destination, payload, postProcessor)** | Cho phép chỉnh sửa Message sau khi conversion và trước khi gửi. |
| **convertAndSend(payload)** | Dùng default destination của implementation. |

Các overload không truyền destination chỉ dùng được khi implementation có default destination phù hợp. Nếu chưa cấu hình default destination, thao tác gửi không có địa chỉ đích sẽ thất bại.

## 2. Phân biệt send và convertAndSend

### send: ứng dụng tự tạo Message

Dùng send khi ứng dụng cần kiểm soát payload và headers trước khi gửi:

~~~java
Message<String> message = MessageBuilder
        .withPayload("Order created")
        .setHeader("app.correlationId", "checkout-001")
        .setHeader("app.eventType", "OrderCreated")
        .build();

operations.send("/topic/orders", message);
~~~

Trong ví dụ này, payload và metadata đã nằm trong Message. Template chịu trách nhiệm chuyển message đến destination theo cách implementation quy định.

### convertAndSend: đưa payload cho converter

Dùng convertAndSend khi ứng dụng muốn gửi một object mà không cần tự tạo Message:

~~~java
OrderCreated event = new OrderCreated(
        "ORD-1001",
        Instant.parse("2026-11-07T03:00:00Z")
);

operations.convertAndSend("/topic/orders", event);
~~~

MessageConverter sẽ chuyển payload thành Message phù hợp. Converter cụ thể quyết định object được giữ nguyên trong message nội bộ hay được chuyển sang dạng biểu diễn khác. Khi đi qua ranh giới mạng, adapter hoặc transport thường cần serialization và contract rõ ràng.

Không nên hiểu convertAndSend là luôn tự chuyển mọi object thành JSON. Việc chuyển thành JSON phụ thuộc converter được cấu hình và implementation của template.

### Gắn headers khi gửi payload

Có thể truyền metadata cùng payload:

~~~java
Map<String, Object> headers = Map.of(
        "app.correlationId", "checkout-001",
        "app.eventType", "OrderCreated"
);

operations.convertAndSend("/topic/orders", event, headers);
~~~

Headers giúp consumer biết ngữ cảnh xử lý. Nên giữ metadata kỹ thuật như correlation ID, event type, content type hoặc tenant context ở headers; dữ liệu nghiệp vụ như order ID, tổng tiền và thời điểm tạo đơn nên thuộc payload.

Nếu cần xử lý Message sau khi converter tạo ra nó, có thể dùng MessagePostProcessor. Ví dụ:

~~~java
operations.convertAndSend(
        "/topic/orders",
        event,
        message -> MessageBuilder.fromMessage(message)
                .setHeader("app.traceId", "trace-001")
                .build()
);
~~~

Post processor chạy sau bước conversion và trước khi gửi, vì vậy có thể bổ sung hoặc điều chỉnh metadata của Message.

## 3. Destination có ý nghĩa theo implementation

Tham số destination là kiểu generic D. Với nhiều template, D là String; nhưng chuỗi destination có ý nghĩa gì phụ thuộc implementation.

| Implementation / tầng | Ví dụ destination | Ý nghĩa |
|---|---|---|
| **SimpMessagingTemplate** | **/topic/orders** | Đích trong mô hình Spring WebSocket/STOMP; broker hoặc application destination prefix quyết định nơi message được xử lý. |
| Spring Integration | Tên channel hoặc endpoint được cấu hình | Đích logical trong message flow; việc phân giải phụ thuộc integration flow và adapter. |
| JMS | Queue hoặc Topic | Destination JMS; thường được thao tác qua JMS API hoặc Spring JMS abstractions. |
| Apache Kafka | Topic | Tên topic; việc gửi còn liên quan key, partition và producer configuration. |

Không nên coi mọi destination String là queue hoặc topic của broker. Ví dụ **/topic/orders** trong SimpMessagingTemplate là destination theo quy ước STOMP/Spring messaging, không tự động trở thành Kafka topic hoặc JMS queue.

### MessageChannel khác destination

MessageChannel là abstraction gửi message trong Spring Messaging. Producer có thể gọi send(message) trực tiếp trên channel.

MessageSendingOperations bổ sung tầng gửi theo destination. Implementation có thể dùng destination để chọn channel nội bộ hoặc chuyển tiếp đến transport tương ứng.

~~~text
Producer
   |
   | MessageSendingOperations.send(destination, message)
   v
Template / Adapter
   |
   | ánh xạ destination
   v
MessageChannel hoặc transport
   |
   v
Consumer / Broker / Endpoint
~~~

Hai abstraction liên quan nhưng không thay thế trực tiếp cho nhau:

- MessageChannel nhận một Message và không nhất thiết biết địa chỉ ngoài.
- MessageSendingOperations nhận destination cùng Message hoặc payload.
- Template/adapter chịu trách nhiệm kết nối destination với channel hoặc hạ tầng đích.

## 4. SimpMessagingTemplate: implementation phổ biến

**SimpMessagingTemplate** là implementation của **MessageSendingOperations<String>** dành cho mô hình Spring messaging hỗ trợ WebSocket/STOMP. Nó gửi message vào một MessageChannel nội bộ, gắn destination theo quy ước Simp và để message broker/application destination xử lý tiếp.

Ví dụ:

~~~java
SimpMessagingTemplate template = new SimpMessagingTemplate(outboundChannel);

template.convertAndSend(
        "/topic/orders",
        "OrderCreated: ORD-1001"
);
~~~

Trong cấu hình WebSocket/STOMP thực tế, outboundChannel được kết nối với message broker hoặc broker relay. Destination như **/topic/orders** thường được broker xử lý theo prefix đã cấu hình. Destination dành cho application handler có thể dùng prefix khác, ví dụ **/app/orders**.

Một số điểm cần nhớ:

- **/topic** thường được dùng cho publish/subscribe trong mô hình broker STOMP.
- **/app** thường được cấu hình để định tuyến đến application message handlers.
- Đây là quy ước phổ biến, không phải hai giá trị bắt buộc của mọi ứng dụng.
- SimpMessagingTemplate không phải KafkaTemplate hoặc JmsTemplate.

### Gửi đến một người dùng cụ thể

SimpMessagingTemplate còn cung cấp API gửi đến user destination thông qua **convertAndSendToUser(...)** hoặc các phương thức tương ứng của SimpMessageSendingOperations.

Ví dụ minh họa:

~~~java
template.convertAndSendToUser(
        "alice",
        "/queue/notifications",
        "Your order has shipped"
);
~~~

Đích cuối cùng được Spring user-destination infrastructure ánh xạ theo session/user đang kết nối. Không nên ghép trực tiếp username vào một chuỗi destination rồi giả định nó tương đương với user destination semantics.

## 5. Ví dụ Java chạy được: gửi qua MessageSendingOperations

Ví dụ sau sử dụng SimpMessagingTemplate với một MessageChannel đơn giản để quan sát message sau khi template gắn destination. Nó chạy trong JVM và không cần mở WebSocket server hoặc broker. Channel trong ví dụ chỉ nhận message và in thông tin; nó không thực hiện truyền mạng.

### Maven

Tạo file **pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>message-sending-operations-demo</artifactId>
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

Tạo file **src/main/java/com/example/messaging/MessageSendingExample.java**:

~~~java
package com.example.messaging;

import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.core.MessageSendingOperations;
import org.springframework.messaging.simp.SimpMessagingTemplate;

public class MessageSendingExample {

    public static void main(String[] args) {
        MessageChannel outboundChannel = new MessageChannel() {
            @Override
            public boolean send(Message<?> message) {
                return send(message, MessageChannel.INDEFINITE_TIMEOUT);
            }

            @Override
            public boolean send(Message<?> message, long timeout) {
                System.out.println(
                        "destination=" + message.getHeaders().get("simpDestination")
                );
                System.out.println("payload=" + message.getPayload());
                return true;
            }
        };

        MessageSendingOperations<String> operations =
                new SimpMessagingTemplate(outboundChannel);

        operations.convertAndSend(
                "/topic/orders",
                "OrderCreated: ORD-1001"
        );
    }
}
~~~

Chạy từ thư mục chứa **pom.xml**:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=com.example.messaging.MessageSendingExample
~~~

Output:

~~~text
destination=/topic/orders
payload=OrderCreated: ORD-1001
~~~

Trong ví dụ:

1. MessageChannel được triển khai bằng lambda vì chỉ cần xử lý một phương thức send.
2. SimpMessagingTemplate được gán cho interface MessageSendingOperations<String>.
3. convertAndSend nhận destination và payload.
4. Template tạo Message, gắn destination theo quy ước Simp rồi gửi đến channel.
5. Channel nhận Message và in destination cùng payload.

Ví dụ này chứng minh thao tác gửi và việc template ánh xạ destination vào message. Nó không kiểm thử broker STOMP hoặc giao tiếp WebSocket thật; để gửi ra client, cần cấu hình broker/message broker infrastructure và các channel tương ứng.

## 6. Default destination và cấu hình gửi

Một số implementation hỗ trợ default destination. Khi cấu hình đích mặc định, ứng dụng có thể dùng overload không truyền destination:

~~~java
template.setDefaultDestination("/topic/orders");
template.convertAndSend("OrderCreated: ORD-1001");
~~~

Default destination phù hợp khi một template chủ yếu phục vụ một đích cố định. Với ứng dụng gửi đến nhiều destination, nên truyền destination tường minh để code dễ đọc và tránh gửi nhầm.

Không nên cấu hình một default destination chung cho nhiều loại event nếu chúng cần các tuyến xử lý khác nhau. Destination nên phản ánh hợp đồng trao đổi và được quản lý nhất quán theo môi trường.

## 7. Chuyển đổi payload và xử lý headers

Khi dùng convertAndSend, template dựa vào MessageConverter để tạo Spring Message. Quá trình này có thể giữ nguyên payload Java hoặc chuyển đổi payload tùy converter.

Cần chú ý:

- Kiểu payload có tương thích với converter không?
- Content type có mô tả đúng định dạng payload không?
- Các header ứng dụng có được giữ sau bước conversion không?
- Header nào được phép chuyển qua transport?
- Có cần MessagePostProcessor để bổ sung correlation ID, trace ID hoặc metadata sau conversion không?

Một converter không được cấu hình đúng có thể khiến payload không chuyển đổi như mong muốn hoặc phát sinh MessageConversionException. Nếu message được chuyển tiếp qua adapter, header mapper có thể loại bỏ hoặc ánh xạ lại một số headers.

Đối với hệ thống nhiều service, hãy xác định wire format và schema rõ ràng. Không dựa vào việc hai service cùng dùng một Java class để giả định object có thể truyền qua broker mà không serialize.

## 8. Gửi message không đồng nghĩa consumer đã xử lý xong

Phương thức của MessageSendingOperations thường trả về void. Khi lệnh gửi hoàn tất, điều đó không tự chứng minh consumer đã xử lý nghiệp vụ thành công.

Tùy implementation:

- Template có thể đã chuyển message vào một channel nội bộ.
- Channel có thể đã chuyển message đến một subscriber.
- Adapter có thể đã gửi message đến broker.
- Broker có thể đã nhận message nhưng consumer chưa xử lý.
- Consumer có thể xử lý thất bại sau khi producer đã gửi thành công.

Nếu cần biết kết quả nghiệp vụ, dùng request/reply, callback/acknowledgment của transport hoặc một event kết quả riêng theo hợp đồng đã thiết kế. Không dùng việc convertAndSend không ném exception làm bằng chứng rằng downstream business operation đã thành công.

### Lỗi trong quá trình gửi

Các lỗi có thể xuất hiện khi destination không hợp lệ, converter thất bại, channel từ chối gửi hoặc transport không sẵn sàng. Tùy implementation, exception có thể được biểu diễn bằng các loại như MessageDeliveryException hoặc MessageConversionException, hoặc exception đặc thù của adapter.

Nên phân biệt:

- Lỗi trước khi gửi: payload không chuyển đổi, thiếu destination, header không hợp lệ.
- Lỗi ở channel/adapter: không thể chuyển message đến bước kế tiếp.
- Lỗi sau khi gửi: broker/consumer xử lý thất bại, cần error flow hoặc acknowledgment riêng.

Retry chỉ nên áp dụng với lỗi có thể phục hồi và cần giới hạn số lần, backoff, idempotency cùng cơ chế dead-letter/quarantine phù hợp.

## 9. Những nhầm lẫn thường gặp

1. **“MessageSendingOperations là broker.”** Không đúng. Đây là abstraction phía gửi, implementation kết nối thao tác gửi với channel hoặc transport.
2. **“Destination luôn là tên queue.”** Không đúng. Destination phụ thuộc implementation; SimpMessagingTemplate thường dùng destination theo quy ước STOMP.
3. **“send và convertAndSend giống hệt nhau.”** Không hoàn toàn. send nhận Message đã tạo; convertAndSend nhận payload và chạy conversion.
4. **“convertAndSend luôn serialize thành JSON.”** Không đúng. Converter quyết định cách chuyển đổi và có thể giữ payload ở dạng object.
5. **“MessageChannel và MessageSendingOperations là cùng một interface.”** Không đúng. Channel gửi Message; Operations gửi Message hoặc payload đến destination.
6. **“Gửi thành công nghĩa là consumer đã xử lý xong.”** Không đúng. Kết quả của thao tác gửi không đại diện cho kết quả nghiệp vụ downstream.
7. **“Mọi template đều dùng cùng quy tắc destination.”** Không đúng. Cần hiểu semantics của implementation cụ thể.
8. **“Default destination luôn có sẵn.”** Không đúng. Implementation phải được cấu hình; overload không có destination có thể thất bại nếu chưa có default.
9. **“Header bất kỳ đều được giữ khi gửi qua broker.”** Không đúng. Converter và header mapper quyết định metadata nào được chuyển tiếp.

## 10. Ghi nhớ

- **MessageSendingOperations<D>** cung cấp abstraction gửi Message hoặc payload đến một destination.
- **send(destination, message)** dùng khi ứng dụng đã tạo Message.
- **convertAndSend(destination, payload)** dùng khi muốn template chuyển payload thành Message bằng converter.
- Destination có semantics theo implementation; không mặc định là queue, topic hoặc URL.
- **SimpMessagingTemplate** là một implementation cho mô hình Spring WebSocket/STOMP.
- MessageChannel là tầng gửi Message nội bộ; template có thể ánh xạ destination sang channel/transport.
- Gửi message thành công không chứng minh consumer đã hoàn thành nghiệp vụ.
- Cần kiểm tra converter, headers, timeout, lỗi channel/adapter và delivery semantics của transport.

Khi thiết kế producer, hãy chọn đúng template theo transport, định nghĩa destination rõ ràng, xác định schema payload và quyết định cách xác nhận kết quả downstream. Điều đó giúp thao tác gửi có hợp đồng ổn định và dễ vận hành.
