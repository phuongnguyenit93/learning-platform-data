# Xây dựng đường đi thông điệp trong bộ nhớ từ bên gửi tới bộ xử lý

## Mục tiêu

Sau bài này, bạn có thể:

- Giải thích vai trò của Message, MessageChannel và MessageHandler trong một luồng xử lý message.
- Xây dựng một đường đi message trong cùng JVM bằng Spring Integration.
- Gửi payload cùng metadata qua MessageBuilder.
- Kết nối bên gửi, channel và processor bằng DirectChannel.
- Phân biệt DirectChannel, QueueChannel, PublishSubscribeChannel và ExecutorChannel.
- Hiểu tác động của channel tới thread, đồng bộ, buffering, ordering và transaction.
- Kiểm thử luồng bằng một chương trình Java 17+ có thể biên dịch và chạy.
- Nhận biết giới hạn của in-memory messaging khi cần durability, nhiều instance hoặc giao tiếp qua mạng.

Bài này thuộc chủ đề **Spring Framework - messaging**, nhánh **Thực hành**. Ta sẽ dựng một pipeline nhỏ trong bộ nhớ: sender tạo message, gửi vào channel, processor nhận và biến đổi payload, rồi chuyển kết quả tới handler cuối.

## 1. Các thành phần trong đường đi message

Spring Messaging cung cấp abstraction Message và MessageChannel. Spring Integration bổ sung các implementation channel và endpoint để xây dựng các Enterprise Integration Patterns (EIP).

Một message thường có hai phần:

- **Payload:** dữ liệu nghiệp vụ, ví dụ nội dung đơn hàng hoặc một lệnh.
- **Headers:** metadata đi kèm, ví dụ correlationId, contentType, timestamp hoặc thông tin định tuyến.

MessageChannel là điểm giao tiếp mà bên gửi dùng để chuyển message. Bên gửi không cần biết handler cụ thể nào sẽ xử lý. MessageHandler là thành phần nhận và xử lý message.

Đường đi cơ bản:

~~~text
Sender
  |
  | Message(payload + headers)
  v
MessageChannel
  |
  v
MessageHandler / Processor
  |
  | transformed Message
  v
Output Channel
  |
  v
Next Handler
~~~

Lợi ích của cách tổ chức này là tách sender khỏi processor. Sender chỉ cần biết channel mà nó gửi tới; processor có thể được thay thế hoặc mở rộng mà không buộc sender phải gọi trực tiếp class xử lý.

### 1.1. Message là một envelope

Ví dụ một message đơn giản:

~~~text
Payload: "  order-42  "
Headers:
  correlationId = "corr-1001"
  contentType   = "text/plain"
~~~

Payload chứa dữ liệu cần xử lý. Header correlationId giúp liên kết log hoặc trace của nhiều bước thuộc cùng một luồng nghiệp vụ.

Message trong Spring Messaging được thiết kế theo hướng bất biến: không sửa trực tiếp header của một message đã tạo. Khi cần thay đổi payload hoặc metadata, tạo message mới bằng MessageBuilder. Payload object vẫn có thể mutable; nếu chia sẻ giữa nhiều handler, nên dùng payload bất biến hoặc quy định rõ quyền sở hữu dữ liệu.

### 1.2. MessageChannel là abstraction

Ứng dụng có thể khai báo biến kiểu MessageChannel và thay implementation theo nhu cầu:

- DirectChannel: dispatch trực tiếp tới một subscriber.
- QueueChannel: lưu message trong queue để consumer poll.
- PublishSubscribeChannel: broadcast tới tất cả subscriber.
- ExecutorChannel: dispatch qua TaskExecutor.

Tên channel trong ứng dụng là điểm nối logic. Nó không nhất thiết là topic, queue hay destination của một broker bên ngoài.

## 2. Chuẩn bị môi trường

Ví dụ dùng Java 17 và Spring Integration 7.1.1. Spring Integration 7.1.x yêu cầu Java SE 17 trở lên và Spring Framework 7.0 trở lên. Dùng dependency trực tiếp của Spring Integration Core để chạy chương trình độc lập, không cần broker hoặc Spring Boot.

Tạo cấu trúc thư mục:

~~~text
in-memory-message-flow/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── example/
                └── InMemoryMessageFlow.java
~~~

### 2.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>in-memory-message-flow</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.integration</groupId>
            <artifactId>spring-integration-core</artifactId>
            <version>7.1.1</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>example.InMemoryMessageFlow</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Spring Integration Core kéo theo các dependency Spring Messaging cần thiết. Không cần tự thêm broker client vì toàn bộ ví dụ chạy trong bộ nhớ của một tiến trình.

## 3. Tạo đường đi bằng DirectChannel

DirectChannel là lựa chọn đơn giản để sender chuyển message trực tiếp tới một handler. Khi gọi send, handler được gọi ngay trên thread của sender. Vì vậy sender chỉ hoàn tất lời gọi send sau khi việc dispatch đồng bộ kết thúc.

Ta dùng hai channel:

1. inputChannel nhận message từ sender.
2. outputChannel nhận message đã được processor chuẩn hóa.

Processor đăng ký làm subscriber của inputChannel. Khi nhận message, nó đọc payload, chuẩn hóa chuỗi, tạo message mới và gửi sang outputChannel.

### 3.1. Source code hoàn chỉnh

Lưu file tại src/main/java/example/InMemoryMessageFlow.java:

~~~java
package example;

import java.util.Locale;

import org.springframework.integration.channel.DirectChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public class InMemoryMessageFlow {

    public static void main(String[] args) {
        DirectChannel inputChannel = new DirectChannel();
        DirectChannel outputChannel = new DirectChannel();

        // Handler cuối nhận kết quả đã xử lý.
        outputChannel.subscribe(message -> {
            System.out.println(
                "PROCESSED: " + message.getPayload()
                    + " | correlationId="
                    + message.getHeaders().get("correlationId")
            );
        });

        // Processor nhận message từ sender và chuyển đổi payload.
        inputChannel.subscribe(message -> {
            String rawPayload = (String) message.getPayload();

            String normalized = rawPayload
                .trim()
                .toUpperCase(Locale.ROOT);

            Message<String> result = MessageBuilder
                .withPayload(normalized)
                .setHeader(
                    "correlationId",
                    message.getHeaders().get("correlationId")
                )
                .setHeader("processed", true)
                .build();

            outputChannel.send(result);
        });

        // Sender tạo envelope gồm payload và metadata.
        Message<String> incoming = MessageBuilder
            .withPayload("  order-42  ")
            .setHeader("correlationId", "corr-1001")
            .build();

        boolean accepted = inputChannel.send(incoming);

        System.out.println("SEND_ACCEPTED=" + accepted);
    }
}
~~~

### 3.2. Biên dịch và chạy

Mở terminal tại thư mục in-memory-message-flow và chạy:

~~~bash
mvn -q clean compile exec:java
~~~

Output:

~~~text
PROCESSED: ORDER-42 | correlationId=corr-1001
SEND_ACCEPTED=true
~~~

Kết quả cho thấy:

1. Sender tạo payload có khoảng trắng ở đầu và cuối.
2. Sender gửi message tới inputChannel.
3. DirectChannel dispatch message tới processor ngay trên cùng thread.
4. Processor trim chuỗi, chuyển thành chữ hoa và giữ correlationId.
5. Processor tạo message mới rồi gửi tới outputChannel.
6. Handler cuối in kết quả.
7. Sau khi các handler đồng bộ hoàn tất, lời gọi inputChannel.send trả về true.

### 3.3. Đọc luồng theo từng dòng

**Tạo channel**

~~~java
DirectChannel inputChannel = new DirectChannel();
DirectChannel outputChannel = new DirectChannel();
~~~

Hai channel tồn tại trong cùng JVM. Chúng không mở socket, không kết nối broker và không ghi message xuống đĩa.

**Đăng ký handler**

~~~java
inputChannel.subscribe(message -> {
    // process message
});
~~~

subscribe đăng ký MessageHandler vào channel. Khi sender gửi message, DirectChannel dispatch tới một subscriber theo semantics unicast.

**Tạo message**

~~~java
Message<String> incoming = MessageBuilder
    .withPayload("  order-42  ")
    .setHeader("correlationId", "corr-1001")
    .build();
~~~

MessageBuilder tạo envelope có payload kiểu String và header correlationId. Sender không cần biết processor được viết bằng class nào.

**Gửi message**

~~~java
boolean accepted = inputChannel.send(incoming);
~~~

Giá trị boolean cho biết channel chấp nhận/dispatch message theo semantics của channel. Với DirectChannel, handler được gọi đồng bộ trước khi send trả về. Nếu handler ném exception, lỗi có thể truyền ngược về sender; không có retry tự động chỉ vì dùng MessageChannel.

**Tạo message mới**

~~~java
Message<String> result = MessageBuilder
    .withPayload(normalized)
    .setHeader("correlationId", message.getHeaders().get("correlationId"))
    .setHeader("processed", true)
    .build();
~~~

Processor tạo message mới thay vì sửa message đầu vào. Nó giữ correlationId để liên kết kết quả với request ban đầu và thêm header processed để minh họa metadata sau xử lý.

## 4. DirectChannel: xử lý đồng bộ, point-to-point

DirectChannel là một SubscribableChannel. Khi send được gọi, nó dispatch message trực tiếp tới subscriber. Đây là channel mặc định thường gặp trong Spring Integration khi khai báo một channel thông thường.

Đặc điểm:

- Point-to-point: mỗi message được dispatch tới một handler trong nhóm subscriber.
- Synchronous: handler chạy trên thread gọi send.
- Không có queue buffer riêng để tách sender và receiver.
- Sender có thể quan sát lỗi handler trong cùng lời gọi.
- Có thể phối hợp với transaction của thread hiện tại khi các thao tác tham gia cùng transaction manager.

Nếu một DirectChannel có nhiều subscriber, dispatcher có thể dùng load-balancing strategy và failover. Nó không broadcast message tới tất cả subscriber. Muốn broadcast, dùng PublishSubscribeChannel.

DirectChannel phù hợp khi:

- Logic xử lý cần hoàn tất ngay trong luồng gọi.
- Muốn giữ call stack và transaction context đồng bộ.
- Cần nối các bước xử lý trong cùng process mà không cần queue.

Không dùng DirectChannel với kỳ vọng sender và processor chạy độc lập. Một handler chậm sẽ làm lời gọi send chậm theo.

## 5. QueueChannel: buffer message trong bộ nhớ

QueueChannel là PollableChannel. Nó lưu message trong queue; sender có thể gửi trước khi consumer sẵn sàng nhận.

Ví dụ:

~~~java
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

QueueChannel queue = new QueueChannel(100);

Message<String> job = MessageBuilder
    .withPayload("job-42")
    .build();

boolean queued = queue.send(job, 0);

Message<?> received = queue.receive(0);
~~~

Ở đây:

- QueueChannel có capacity 100.
- send(job, 0) thử gửi ngay, không chờ nếu queue đầy.
- receive(0) lấy message ngay nếu queue có dữ liệu.
- Nếu queue đầy, send với timeout 0 có thể trả false.
- Nếu queue rỗng, receive với timeout 0 trả null.

QueueChannel có constructor không tham số với capacity rất lớn (Integer.MAX_VALUE). Trong ứng dụng thực tế, nên cân nhắc capacity hữu hạn để giới hạn bộ nhớ. Nếu queue đầy, send có thể chờ chỗ trống theo timeout đã chọn.

QueueChannel chỉ cung cấp buffer trong bộ nhớ của process. Nó không có persistence như broker. Khi JVM dừng đột ngột, message đang nằm trong queue có thể mất.

### 5.1. Ai lấy message khỏi QueueChannel?

QueueChannel không tự tạo worker xử lý. Consumer cần gọi receive hoặc được nối với một poller/endpoint Spring Integration. Một ứng dụng có thể dùng poller để đọc message theo chu kỳ, hoặc dùng cơ chế khác để kích hoạt consumer.

Không nên gọi receive không timeout trên thread quan trọng nếu queue có thể rỗng, vì lời gọi có thể block vô thời hạn.

## 6. PublishSubscribeChannel: gửi cùng message tới nhiều handler

PublishSubscribeChannel broadcast message tới tất cả subscriber. Nó phù hợp với event cần nhiều thành phần cùng nhận, ví dụ một event đơn hàng được dùng cho audit, analytics và notification.

Ví dụ:

~~~java
PublishSubscribeChannel events = new PublishSubscribeChannel();

events.subscribe(message ->
    System.out.println("AUDIT: " + message.getPayload())
);

events.subscribe(message ->
    System.out.println("ANALYTICS: " + message.getPayload())
);

events.send(MessageBuilder.withPayload("order-created").build());
~~~

Với cấu hình mặc định không có TaskExecutor, các subscriber được gọi trên thread gửi message. Nếu cấu hình executor, việc dispatch có thể bất đồng bộ.

PublishSubscribeChannel không phải queue để consumer poll. Subscriber là MessageHandler và được gọi khi message được publish.

Nếu một message phải được xử lý bởi đúng một worker trong nhóm, dùng DirectChannel hoặc QueueChannel theo semantics phù hợp, không dùng publish-subscribe.

## 7. ExecutorChannel: dispatch qua thread pool

ExecutorChannel là point-to-point channel sử dụng TaskExecutor để dispatch tới handler. Nó hữu ích khi muốn tách thread sender khỏi thread xử lý.

~~~text
Sender thread
    |
    v
ExecutorChannel
    |
    v
TaskExecutor queue / worker
    |
    v
MessageHandler
~~~

Khác biệt quan trọng so với DirectChannel:

- Sender thường không chờ handler hoàn tất.
- Handler có thể chạy trên worker thread.
- Exception xảy ra trong handler có thể không truyền về lời gọi send đã hoàn tất.
- Transaction context của sender không tự động truyền sang handler.
- Executor và queue cần giới hạn để tránh tích tụ task và tăng bộ nhớ.

ExecutorChannel không phải durable queue. Nếu process dừng, task đang chờ trong executor có thể mất. Nếu cần durable delivery, acknowledgement và redelivery, cần broker hoặc cơ chế persistence phù hợp.

## 8. So sánh các channel trong thực tế

| Channel | Semantics | Dispatch | Buffer | Nên dùng khi |
|---|---|---|---|---|
| DirectChannel | Point-to-point | Đồng bộ trên sender thread | Không | Pipeline đơn giản, cần kết quả xử lý trong lời gọi |
| QueueChannel | Point-to-point | Consumer poll | Có, giới hạn theo capacity | Cần tách gửi và nhận bằng queue trong JVM |
| PublishSubscribeChannel | Broadcast | Đồng bộ mặc định; có thể dùng executor | Không phải pollable queue | Nhiều handler cần nhận cùng event |
| ExecutorChannel | Point-to-point | Qua TaskExecutor | Dựa vào executor queue | Cần dispatch sang worker thread |

Chọn channel theo semantics nghiệp vụ, không chỉ theo tốc độ. Một channel bất đồng bộ có thể giảm thời gian sender chờ nhưng làm thay đổi cách quan sát lỗi, transaction và ordering.

## 9. Message headers và correlation

Trong pipeline nhiều bước, payload mô tả dữ liệu nghiệp vụ còn headers mô tả ngữ cảnh truyền tải.

Một số header thường hữu ích:

- correlationId: liên kết các message thuộc cùng một request/flow.
- contentType: mô tả format payload.
- replyChannel: channel dùng cho reply trong một số pattern.
- errorChannel: channel dùng cho lỗi trong một số flow.
- timestamp: thời điểm tạo message nếu hợp đồng cần.

Không nhét mọi metadata vào payload. Nhưng cũng không dùng headers thay cho dữ liệu nghiệp vụ bắt buộc phải được lưu bền vững hoặc truyền qua ranh giới broker nếu adapter không bảo toàn chúng.

Khi tạo message mới, quyết định rõ header nào cần giữ. MessageBuilder.fromMessage(message) có thể tạo builder từ message hiện tại rồi thay payload hoặc thêm header; nếu tạo message hoàn toàn mới, hãy copy những header cần thiết một cách có chủ đích.

Không đưa token, mật khẩu hoặc dữ liệu nhạy cảm vào header nếu chúng có thể bị log hoặc chuyển tiếp ngoài phạm vi dự kiến.

## 10. Xử lý lỗi trong đường đi message

Với DirectChannel, handler chạy trong lời gọi send. Nếu handler ném exception, lỗi có thể quay về sender. Sender có thể bắt lỗi và áp dụng chính sách phù hợp.

Với QueueChannel, sender có thể gửi thành công vào queue trước khi consumer xử lý. Lỗi xử lý xảy ra ở thời điểm receive/handler sau đó, nên sender ban đầu không thể nhận exception đó chỉ từ lời gọi send.

Với ExecutorChannel, sender thường đã trả về trước khi handler chạy. Lỗi cần được xử lý qua error handling của executor/endpoint hoặc flow.

Một số nguyên tắc:

1. Phân biệt lỗi gửi message với lỗi xử lý message.
2. Định nghĩa nơi chịu trách nhiệm retry.
3. Không retry vô hạn.
4. Với side effect có thể lặp, dùng idempotency key hoặc deduplication.
5. Nếu message phải sống qua restart, dùng broker/persistent store thay vì chỉ giữ trong memory.
6. Ghi correlationId và tên bước xử lý vào log để truy vết.

Một channel trong bộ nhớ không tự cung cấp dead-letter queue, acknowledgement bền vững hay exactly-once processing. Các bảo đảm này phải được thiết kế ở tầng ứng dụng hoặc middleware.

## 11. Kiểm thử đường đi message

Với pipeline DirectChannel đồng bộ, test có thể gửi message và kiểm tra kết quả ngay sau khi send trả về.

Ví dụ kiểm tra logic:

~~~java
DirectChannel input = new DirectChannel();
AtomicReference<Message<?>> captured = new AtomicReference<>();

input.subscribe(captured::set);

Message<String> message = MessageBuilder
    .withPayload("hello")
    .setHeader("correlationId", "test-1")
    .build();

boolean sent = input.send(message);

assert sent;
assert captured.get() != null;
assert "hello".equals(captured.get().getPayload());
assert "test-1".equals(
    captured.get().getHeaders().get("correlationId")
);
~~~

Đây là đoạn kiểm thử minh họa, cần chạy với assertions được bật hoặc chuyển thành JUnit assertions trong test suite. Với ExecutorChannel, không thể giả định handler đã chạy ngay sau send; test cần đồng bộ bằng latch/future hoặc cơ chế chờ có timeout. Với QueueChannel, test cần receive message sau khi send.

Các trường hợp nên kiểm tra:

- Không có subscriber: send có được chấp nhận hay không theo channel.
- Handler ném exception.
- Payload không đúng kiểu mong đợi.
- Header correlationId được giữ qua processor.
- Queue đầy hoặc queue rỗng.
- Nhiều subscriber trên DirectChannel.
- Nhiều subscriber trên PublishSubscribeChannel.
- Handler bất đồng bộ hoàn tất sau sender.
- Cancellation/shutdown khi có task đang chờ.

## 12. Khi nào in-memory messaging là đủ?

In-memory channel phù hợp khi các bước xử lý nằm trong cùng process và không cần lưu message bền vững. Nó thường hữu ích cho:

- Tách module sender và processor.
- Nối các bước xử lý trong cùng JVM.
- Thử nghiệm Enterprise Integration Patterns.
- Xây dựng pipeline nội bộ không cần network.
- Unit/integration test logic message handler.

Khi cần giao tiếp giữa nhiều process hoặc service, broker hoặc transport adapter phù hợp hơn. Ví dụ Kafka, RabbitMQ, JMS hoặc RSocket có thể cung cấp giao tiếp qua mạng và các semantics tương ứng.

Chọn broker khi cần một hoặc nhiều khả năng:

- Durable message storage.
- Consumer độc lập hoặc scale trên nhiều instance.
- Acknowledgement, retry và redelivery.
- Retention, replay hoặc event streaming.
- Kết nối các service triển khai độc lập.
- Broker-managed routing hoặc queueing.

Không chuyển sang broker chỉ vì ứng dụng có MessageChannel. Hãy bắt đầu từ yêu cầu về durability, topology, scale, failure recovery và ordering.

## 13. Lỗi phổ biến

- Nghĩ MessageChannel luôn là network channel hoặc broker destination.
- Cho rằng DirectChannel lưu message trong queue.
- Dùng DirectChannel nhưng mong sender và processor chạy trên hai thread khác nhau.
- Dùng QueueChannel không giới hạn capacity và để queue tích tụ vô hạn.
- Nghĩ QueueChannel tự khởi chạy consumer mà không có poller/receive.
- Dùng PublishSubscribeChannel khi chỉ một worker được xử lý message.
- Dùng DirectChannel khi mọi subscriber đều phải nhận event.
- Dùng ExecutorChannel nhưng kỳ vọng exception của handler truyền về sender.
- Cho rằng transaction của sender tự truyền qua ExecutorChannel.
- Không giữ correlationId qua các bước xử lý.
- Sửa trực tiếp header/message thay vì tạo message mới.
- Coi send trả true là bằng chứng nghiệp vụ đã hoàn tất.
- Coi in-memory queue là durable và an toàn qua restart.

## 14. Checklist thực hành

- [ ] Đã xác định payload và metadata của message.
- [ ] Đã tạo Message bằng MessageBuilder.
- [ ] Đã tạo input/output channel trong cùng JVM.
- [ ] Đã đăng ký MessageHandler cho từng bước.
- [ ] Đã gửi message từ sender tới processor.
- [ ] Processor tạo message mới và giữ correlationId.
- [ ] Đã kiểm tra kết quả xử lý và send status.
- [ ] Đã hiểu DirectChannel chạy đồng bộ trên sender thread.
- [ ] Đã phân biệt QueueChannel, PublishSubscribeChannel và ExecutorChannel.
- [ ] Đã xác định nơi xử lý lỗi, retry và deduplication.
- [ ] Đã quyết định in-memory channel có đáp ứng yêu cầu durability hay không.
- [ ] Đã chạy chương trình với Java 17 và Maven.

## Kết luận

Đường đi message trong bộ nhớ có thể bắt đầu bằng một MessageBuilder, đi qua DirectChannel, được xử lý bởi MessageHandler rồi chuyển sang output channel. MessageChannel giúp sender và processor phụ thuộc vào abstraction thay vì gọi trực tiếp nhau. DirectChannel phù hợp cho dispatch đồng bộ; QueueChannel thêm buffering và polling; PublishSubscribeChannel broadcast; ExecutorChannel dispatch qua executor. Tất cả đều chạy trong process và không tự tạo durability của broker, vì vậy cần chọn channel theo yêu cầu về thread, lỗi, transaction và khả năng phục hồi.

## Tài liệu tham khảo

- [Spring Integration Reference - Core Messaging](https://docs.spring.io/spring-integration/reference/core.html)
- [Spring Integration Reference - Message Channels](https://docs.spring.io/spring-integration/reference/channel/implementations.html)
- [Spring Integration Reference - Configuring Message Channels](https://docs.spring.io/spring-integration/reference/channel/configuration.html)
- [Spring Integration Reference - Java DSL](https://docs.spring.io/spring-integration/reference/dsl/java.html)
- [Spring Framework Reference - Messaging](https://docs.spring.io/spring-framework/reference/integration.html)
- [Spring Integration 7.1 Requirements](https://docs.spring.io/spring-integration/reference/preface.html)
