# Bản đồ thuật ngữ trong Spring Messaging: sender, receiver, channel, destination và broker

## Mục tiêu

Khi đọc hoặc thiết kế một luồng messaging trong ứng dụng Spring, cần phân biệt năm vai trò:

- **Sender / producer (bên gửi):** tạo và gửi thông điệp.
- **Receiver / consumer (bên nhận):** nhận và xử lý thông điệp.
- **Channel (kênh):** đường giao tiếp mà ứng dụng dùng để chuyển thông điệp giữa các thành phần.
- **Destination (đích):** địa chỉ logic mà thông điệp được gửi tới, thường là queue hoặc topic do hệ thống messaging quản lý.
- **Broker (bộ môi giới):** máy chủ trung gian nhận, định tuyến, lưu đệm hoặc phân phối thông điệp giữa các ứng dụng.

Các thuật ngữ này mô tả những phần khác nhau của một luồng. Một channel không mặc nhiên là một broker; một destination không phải là một consumer; và một ứng dụng có thể dùng channel nội bộ mà không cần broker bên ngoài.

## 1. Message là gì?

Trong Spring Messaging, một message là một gói dữ liệu có hai phần:

1. **Payload:** nội dung chính cần truyền, chẳng hạn một đối tượng Order, một chuỗi văn bản hoặc một sự kiện.
2. **Headers:** metadata đi kèm, chẳng hạn message ID, timestamp, thông tin nguồn gửi, correlation ID hoặc thông tin phục vụ định tuyến.

Spring biểu diễn gói này bằng interface `Message<T>`. Payload có kiểu `T`; headers được truy cập qua `MessageHeaders`. Có thể tạo message bằng `MessageBuilder`.

Ví dụ về mặt ý tưởng:

~~~text
Message<OrderCreated>
  payload:
    orderId = "ORD-42"
    total = 250000
  headers:
    messageId = ...
    timestamp = ...
    correlationId = "REQ-17"
    source = "checkout-service"
~~~

Payload trả lời câu hỏi “đang truyền dữ liệu gì?”. Header trả lời câu hỏi “thông điệp này có metadata nào để xử lý, theo dõi hoặc định tuyến?”. Không nên đưa mọi metadata vào payload nếu consumer cần dùng chúng như thông tin vận chuyển hoặc tương quan.

## 2. Năm thuật ngữ chính

| Thuật ngữ | Ý nghĩa | Câu hỏi cần đặt ra |
|---|---|---|
| Sender / producer | Thành phần tạo và gửi message. Có thể là service, controller, adapter hoặc một ứng dụng khác. | Ai phát sinh sự kiện hoặc yêu cầu? |
| Receiver / consumer | Thành phần nhận và xử lý message. Có thể là handler, listener hoặc một ứng dụng khác. | Ai chịu trách nhiệm xử lý message? |
| Channel | Abstraction hoặc đường truyền message giữa các thành phần trong ứng dụng. Trong Spring, `MessageChannel` định nghĩa thao tác gửi message. | Thành phần gửi chuyển message vào luồng nào? |
| Destination | Địa chỉ logic mà message hướng tới trong một messaging system, ví dụ queue, topic hoặc STOMP destination. | Message được gửi tới địa chỉ nào? |
| Broker | Hệ thống trung gian nhận message từ producer rồi định tuyến, lưu hoặc phân phối tới consumer theo cấu hình. | Thành phần trung gian nào quản lý việc chuyển giao? |

### Sender / producer — bên gửi

Sender là nơi bắt đầu việc gửi. Sender tạo payload, có thể bổ sung headers, rồi gọi API gửi message.

Trong Spring, API cụ thể tùy công nghệ:

- Gửi vào channel nội bộ: gọi `MessageChannel.send(message)`.
- Gửi qua JMS: dùng `JmsTemplate`.
- Gửi qua RabbitMQ: dùng `RabbitTemplate`.
- Gửi tới Kafka: dùng `KafkaTemplate`.
- Gửi tới STOMP destination trong ứng dụng WebSocket: dùng `SimpMessagingTemplate`.

Sender không nhất thiết phải biết consumer nào sẽ xử lý message. Trong mô hình broker, sender thường chỉ cần biết destination hoặc thông tin định tuyến.

### Receiver / consumer — bên nhận

Receiver là nơi tiếp nhận và xử lý message. Nó có thể kiểm tra payload, xác thực dữ liệu, cập nhật trạng thái, gọi nghiệp vụ hoặc phát ra message tiếp theo.

Trong Spring, receiver có thể là:

- Một `MessageHandler` đăng ký với `SubscribableChannel`.
- Một endpoint của Spring Integration.
- Một phương thức được đánh dấu `@JmsListener`, `@RabbitListener` hoặc `@KafkaListener` khi dùng module tương ứng.
- Một phương thức xử lý message STOMP/WebSocket, chẳng hạn dùng `@MessageMapping`.

Receiver nên xử lý message theo cách an toàn khi message được gửi lại. Với hệ thống có retry hoặc giao nhận ít nhất một lần, cùng một nghiệp vụ có thể được nhìn thấy nhiều lần; xử lý idempotent giúp tránh tạo đơn hàng hoặc trừ tiền lặp.

Sender và receiver là vai trò theo từng chiều truyền tin. Trong luồng request/reply, một thành phần có thể là sender của request và trở thành receiver của reply.

### Channel — kênh

Channel là abstraction kết nối các thành phần messaging. Trong Spring Messaging, interface `MessageChannel` cung cấp thao tác gửi một `Message`. Channel có thể nằm hoàn toàn trong bộ nhớ của tiến trình ứng dụng; nó không tự động đồng nghĩa với một queue trên máy chủ broker.

Các interface quan trọng:

- `MessageChannel`: abstraction gửi message.
- `SubscribableChannel`: channel cho phép handler đăng ký nhận message.
- `PollableChannel`: channel cho phép consumer chủ động gọi thao tác nhận message.
- `MessageHandler`: thành phần xử lý message.

Một số implementation channel thường gặp trong Spring:

| Channel | Nơi cung cấp | Cách hoạt động khái quát |
|---|---|---|
| `ExecutorSubscribableChannel` | Spring Messaging | Gửi tới các handler đã đăng ký; có thể dùng Executor để thực thi handler. |
| `DirectChannel` | Spring Integration | Gọi handler trực tiếp trong luồng gửi; thường dùng cho xử lý đồng bộ trong cùng ứng dụng. |
| `PublishSubscribeChannel` | Spring Integration | Phát message tới các subscriber; phù hợp khi nhiều thành phần cùng cần nhận một sự kiện. |
| `QueueChannel` | Spring Integration | Giữ message trong hàng đợi nội bộ để consumer nhận sau bằng thao tác poll/receive. |

Tên channel chỉ có ý nghĩa trong cấu hình của ứng dụng. Ví dụ, một channel có tên `orders` có thể nối service tạo đơn với một handler; tên đó không tự động tạo queue tên `orders` trên RabbitMQ hay Kafka.

### Destination — đích

Destination là địa chỉ mà producer nhắm tới trong một hệ thống messaging. Tùy công nghệ, destination có thể là:

- **Queue:** thường dùng cho mô hình point-to-point. Nhiều consumer có thể cạnh tranh nhận message; một message trong queue thường được giao cho một consumer tại một thời điểm theo semantics của hệ thống.
- **Topic:** thường dùng cho mô hình publish/subscribe. Các subscription độc lập có thể nhận bản sao của cùng một sự kiện.
- **STOMP destination:** một đường dẫn logic như `/topic/prices` hoặc `/queue/orders`. Ý nghĩa cụ thể phụ thuộc cấu hình broker và ứng dụng.
- **Kafka topic:** luồng sự kiện được chia thành partition. Consumer group quyết định cách các consumer chia nhau đọc partition.

Các ví dụ trên không hoàn toàn thay thế cho nhau. Queue, topic, STOMP destination và Kafka topic có semantics, cơ chế lưu trữ và cách phân phối riêng. Cần đọc tài liệu của công nghệ đang dùng trước khi suy ra bảo đảm giao nhận.

Destination trả lời “gửi tới đâu?”. Channel trả lời “ứng dụng chuyển message qua abstraction nào?”. Một adapter có thể nối channel nội bộ với destination bên ngoài.

### Broker — bộ môi giới

Broker là máy chủ hoặc dịch vụ messaging trung gian. Producer gửi message tới broker; broker áp dụng quy tắc định tuyến và giao message cho consumer hoặc subscription phù hợp.

Broker thường có thể đảm nhiệm một số việc sau, tùy sản phẩm và cấu hình:

- Quản lý queue, topic, partition hoặc các cấu trúc định tuyến.
- Nhận kết nối từ producer và consumer.
- Lưu hoặc buffer message khi consumer chưa sẵn sàng.
- Định tuyến message tới queue hoặc subscription.
- Hỗ trợ acknowledgement, retry, redelivery và persistence.
- Theo dõi trạng thái consumer hoặc subscription.

Ví dụ broker và hệ sinh thái thường gặp là RabbitMQ, ActiveMQ Artemis và Apache Kafka. Kafka thường được mô tả chính xác hơn là một distributed event streaming platform, dù các Kafka broker vẫn là thành phần máy chủ nhận và lưu dữ liệu cho topic partitions.

Spring Framework không phải là broker. Spring cung cấp abstraction và các integration module/client để ứng dụng giao tiếp với broker hoặc với channel nội bộ.

## 3. Hai luồng cần phân biệt

### Luồng nội bộ, không có broker

~~~mermaid
flowchart LR
    S["Sender"] --> M["Message: payload + headers"]
    M --> C["MessageChannel"]
    C --> H["MessageHandler / Receiver"]
~~~

Ví dụ: một service tạo message, gửi vào `ExecutorSubscribableChannel`, rồi handler đã đăng ký xử lý message. Tất cả có thể diễn ra trong cùng một tiến trình Java. Không cần queue server, mạng hoặc broker bên ngoài.

### Luồng đi qua broker

~~~mermaid
flowchart LR
    S["Sender / producer"] --> T["Spring template hoặc outbound adapter"]
    T --> B["Broker"]
    B --> D["Destination: queue / topic"]
    D --> I["Inbound adapter hoặc listener"]
    I --> R["Receiver / consumer"]
~~~

Broker nhận message, áp dụng cấu hình định tuyến và chuyển message tới destination/subscription thích hợp. Consumer có thể ở tiến trình hoặc máy chủ khác với producer.

### Khi dùng Spring Integration để nối channel với broker

~~~mermaid
flowchart LR
    P["Producer"] --> C1["Channel nội bộ"]
    C1 --> O["Outbound adapter"]
    O --> B["Broker"]
    B --> D["Queue / topic"]
    D --> I["Inbound adapter"]
    I --> C2["Channel nội bộ"]
    C2 --> H["Message handler"]
~~~

Outbound adapter chuyển message từ luồng Spring sang hệ thống bên ngoài. Inbound adapter đưa message từ hệ thống bên ngoài trở lại luồng Spring. Adapter là cầu nối; channel nội bộ và destination trên broker vẫn là hai khái niệm khác nhau.

## 4. Spring cung cấp những phần nào?

Cần xác định module đang dùng vì các API có vai trò khác nhau:

| Thành phần | Vai trò |
|---|---|
| Spring Messaging (`spring-messaging`) | Cung cấp mô hình message và các abstraction như `Message`, `MessageChannel`, `MessageHandler`, `MessageBuilder`. |
| Spring Integration | Cung cấp channel, endpoint, adapter và flow để kết nối các thành phần hoặc hệ thống. Những channel như `DirectChannel` và `QueueChannel` thuộc module này. |
| Spring WebSocket / STOMP | Cho phép xử lý message qua WebSocket; có `@MessageMapping`, `SimpMessagingTemplate` và hỗ trợ simple broker hoặc broker relay. |
| Spring JMS | Kết nối ứng dụng với hệ thống JMS thông qua API như `JmsTemplate` và `@JmsListener`. |
| Spring AMQP | Kết nối với hệ thống AMQP, thường gặp là RabbitMQ, qua `RabbitTemplate` và `@RabbitListener`. |
| Spring for Apache Kafka | Kết nối Kafka qua `KafkaTemplate` và `@KafkaListener`. |

Không phải mọi API trong bảng đều nằm trong module Spring Messaging. Ví dụ, `DirectChannel` là implementation của Spring Integration; `@JmsListener` thuộc Spring JMS; `@RabbitListener` thuộc Spring AMQP. Phân biệt module giúp chọn đúng dependency và tra cứu đúng tài liệu.

## 5. Ví dụ Java: sender gửi qua channel nội bộ

Ví dụ dưới đây dùng `ExecutorSubscribableChannel` của Spring Messaging. Handler đăng ký trực tiếp với channel. Channel này chỉ minh họa trao đổi trong cùng ứng dụng; ví dụ không tạo broker hay destination bên ngoài.

Cấu trúc project:

~~~text
spring-messaging-map/
  pom.xml
  src/
    main/
      java/
        demo/
          MessagingMapDemo.java
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>spring-messaging-map</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <spring-framework.version>6.2.8</spring-framework.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-messaging</artifactId>
            <version>${spring-framework.version}</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### MessagingMapDemo.java

~~~java
package demo;

import org.springframework.messaging.Message;
import org.springframework.messaging.SubscribableChannel;
import org.springframework.messaging.support.ExecutorSubscribableChannel;
import org.springframework.messaging.support.MessageBuilder;

public class MessagingMapDemo {

    public static void main(String[] args) {
        // Channel nội bộ trong ứng dụng.
        SubscribableChannel channel = new ExecutorSubscribableChannel();

        // Receiver đăng ký làm handler của channel.
        channel.subscribe(message -> System.out.printf(
                "receiver=order-handler, sender=%s, payload=%s%n",
                message.getHeaders().get("sender"),
                message.getPayload()
        ));

        // Sender tạo message gồm payload và metadata.
        Message<String> message = MessageBuilder.withPayload("order-42")
                .setHeader("sender", "checkout-service")
                .build();

        // Gửi message vào channel.
        System.out.println("sent=" + channel.send(message));
    }
}
~~~

Chạy từ thư mục project bằng Java 17+ và Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.MessagingMapDemo
~~~

Kết quả stdout:

~~~text
receiver=order-handler, sender=checkout-service, payload=order-42
sent=true
~~~

Cách đọc ví dụ:

1. `checkout-service` đóng vai trò sender và tạo message có payload `order-42`.
2. Header `sender` mang metadata về nguồn gửi. Header này không phải destination và không tự định tuyến message.
3. `ExecutorSubscribableChannel` là channel nội bộ. Handler đăng ký bằng `subscribe` đóng vai trò receiver.
4. `send` chuyển message tới channel; với channel mặc định không truyền Executor, handler được gọi trong luồng gửi.
5. Kết quả `true` cho biết thao tác gửi qua channel thành công trong ví dụ này. Nó không phải acknowledgement từ broker và cũng không phải xác nhận một nghiệp vụ ở hệ thống bên ngoài đã hoàn tất.

Nếu cần gửi qua broker, ứng dụng phải dùng template/client hoặc adapter phù hợp, cấu hình destination và kết nối tới hệ thống messaging. Không thể chỉ đổi tên channel trong ví dụ trên thành tên queue rồi kỳ vọng broker tự xuất hiện.

## 6. Ví dụ API theo từng hệ thống

Các đoạn dưới đây minh họa cách gọi API; chúng không phải một project độc lập và cần dependency, cấu hình kết nối cùng tài nguyên tương ứng.

### STOMP / WebSocket

~~~java
messagingTemplate.convertAndSend("/topic/orders", event);
~~~

`/topic/orders` là STOMP destination. Broker hoặc simple broker được cấu hình trong ứng dụng phân phối message tới các subscription phù hợp. Khi dùng broker relay, Spring chuyển tiếp tới STOMP broker bên ngoài.

### JMS

~~~java
jmsTemplate.convertAndSend("orders.queue", event);
~~~

Tên `orders.queue` được phân giải thành JMS destination thông qua cấu hình JMS. Consumer có thể lắng nghe destination đó bằng `@JmsListener`. JMS provider/broker chịu trách nhiệm vận chuyển theo cấu hình.

### RabbitMQ qua Spring AMQP

~~~java
rabbitTemplate.convertAndSend("orders.exchange", "orders.created", event);
~~~

Trong ví dụ này, producer gửi tới exchange với routing key. Exchange áp dụng binding để định tuyến tới queue. Vì vậy, exchange, routing key và queue là các khái niệm riêng; không nên gọi tất cả là channel.

### Apache Kafka

~~~java
kafkaTemplate.send("orders", event);
~~~

`orders` là tên topic. Kafka lưu record trong partition của topic; consumer group phân chia việc đọc partition giữa các consumer thuộc cùng group. Cách phân phối này khác với queue truyền thống và phụ thuộc số partition, consumer group cùng offset.

## 7. Queue, topic và channel khác nhau thế nào?

| Khái niệm | Mục đích thường gặp | Nơi tồn tại |
|---|---|---|
| Spring channel | Nối các thành phần trong messaging flow của ứng dụng. | Trong mô hình hoặc runtime Spring; có thể nằm trong bộ nhớ. |
| Queue | Giữ message để consumer nhận theo mô hình point-to-point hoặc competing consumers. | Trong messaging system/broker, tùy công nghệ. |
| Topic | Phát sự kiện tới nhiều subscription hoặc consumer group. | Trong messaging system/broker, tùy công nghệ. |
| Destination | Tên gọi tổng quát cho địa chỉ nhận message. | Do protocol hoặc messaging system định nghĩa. |
| Broker | Quản lý việc tiếp nhận, lưu và phân phối message. | Tiến trình hoặc dịch vụ trung gian. |

Một ứng dụng có thể có channel tên `ordersChannel` nối tới outbound adapter; adapter gửi message tới RabbitMQ exchange; exchange định tuyến tới queue `orders.created`. Trong luồng đó có channel, adapter, exchange và queue. Chúng liên quan với nhau nhưng không phải cùng một đối tượng.

## 8. Vòng đời message và bảo đảm giao nhận

Một luồng messaging thường có các bước:

1. Sender tạo payload và headers.
2. Sender gửi message vào channel hoặc qua template/client.
3. Nếu có broker, broker nhận message và định tuyến tới destination theo cấu hình.
4. Receiver nhận message.
5. Receiver xử lý nghiệp vụ.
6. Hệ thống xác nhận, retry hoặc đưa message vào luồng lỗi tùy cơ chế được cấu hình.

Cần phân biệt ba loại xác nhận:

- **Send result:** API gửi cho biết thao tác gửi có được chấp nhận hay không.
- **Broker acknowledgement:** broker/provider xác nhận một bước giao nhận hoặc lưu trữ theo giao thức.
- **Business acknowledgement:** ứng dụng xác nhận nghiệp vụ đã hoàn tất, chẳng hạn đơn hàng đã được tạo.

Ba điều này không đồng nghĩa. Ví dụ, `MessageChannel.send` trả về `true` không chứng minh một consumer từ xa đã xử lý đơn hàng.

Các bảo đảm như at-most-once, at-least-once, redelivery, ordering và persistence phụ thuộc công nghệ, cấu hình, transaction, acknowledgement và cách consumer xử lý lỗi. Retry có thể khiến cùng một message được xử lý lại. Vì vậy, consumer của nghiệp vụ quan trọng nên có chiến lược idempotency, chẳng hạn dùng event ID hoặc business key để phát hiện yêu cầu đã xử lý.

Khi message đi qua mạng, payload thường cần được serialize thành dạng truyền được và deserialize ở phía nhận. Converter/serializer phải thống nhất về kiểu dữ liệu, schema và phiên bản. Không nên mặc định object Java có thể được gửi trực tiếp giữa hai ứng dụng khác tiến trình mà không cần cấu hình chuyển đổi.

## 9. Cách đọc một sơ đồ messaging

Khi nhìn vào sơ đồ hoặc code, hãy lần lượt tìm:

1. **Ai tạo message?** Tìm service, controller, producer hoặc đoạn gọi template.
2. **Message đi qua đâu trong ứng dụng?** Tìm `MessageChannel`, tên channel và adapter.
3. **Có broker không?** Tìm cấu hình kết nối, client/template hoặc broker relay. Nếu chỉ thấy channel nội bộ, chưa đủ cơ sở kết luận có broker.
4. **Đích là gì?** Xác định queue, topic, STOMP destination, Kafka topic hoặc exchange/routing key.
5. **Ai nhận và xử lý?** Tìm handler, listener, subscription hoặc consumer.
6. **Điều gì xảy ra khi lỗi?** Kiểm tra acknowledgement, retry, dead-letter, transaction và idempotency.

## 10. Lỗi hiểu nhầm thường gặp

- **Gọi channel là broker:** channel thường là abstraction trong ứng dụng; broker là hệ thống trung gian có thể chạy riêng.
- **Coi destination là receiver:** destination là địa chỉ; receiver là thành phần xử lý message tại phía nhận.
- **Cho rằng mọi channel đều lưu message:** một channel có thể chuyển message trực tiếp; chỉ một số loại channel có buffer hoặc queue.
- **Cho rằng channel nội bộ cần broker:** channel như `ExecutorSubscribableChannel` có thể hoạt động trong một tiến trình.
- **Cho rằng send thành công nghĩa là nghiệp vụ thành công:** send result, broker acknowledgement và business acknowledgement là các mốc khác nhau.
- **Đồng nhất queue và topic:** chúng thường thể hiện mô hình phân phối khác nhau; semantics chính xác do công nghệ quyết định.
- **Cho rằng mọi API listener thuộc Spring Messaging:** `@JmsListener`, `@RabbitListener` và `@KafkaListener` đến từ các module tích hợp tương ứng.
- **Cho rằng header là payload:** header là metadata; payload là nội dung chính. Cũng không nên dùng một custom header tên `destination` rồi cho rằng nó tự định tuyến message.

## Ghi nhớ

- **Sender** tạo và gửi.
- **Receiver** nhận và xử lý.
- **Channel** là đường hoặc abstraction chuyển message trong ứng dụng.
- **Destination** là địa chỉ nhận trong một messaging system.
- **Broker** là hệ thống trung gian quản lý việc nhận, định tuyến và phân phối.
- **Message** mang payload cùng headers.
- **Adapter/template** nối API Spring với protocol hoặc broker cụ thể.

Khi phân tích một luồng, hãy xác định từng vai trò và ranh giới giữa ứng dụng với broker. Điều đó giúp chọn đúng Spring module, cấu hình đúng destination và hiểu chính xác message đã đi tới bước nào.