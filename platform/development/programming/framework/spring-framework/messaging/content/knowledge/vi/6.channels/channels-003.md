# PollableChannel và mô hình chủ động lấy thông điệp

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích PollableChannel là hợp đồng nhận thông điệp theo kiểu pull trong Spring Messaging.
- Phân biệt PollableChannel với SubscribableChannel và mô hình push.
- Sử dụng receive() và receive(timeout) để lấy Message.
- Hiểu khi nào thread consumer bị chặn, cách timeout hoạt động và vì sao polling không tự động đồng nghĩa với bất đồng bộ.
- Phân biệt PollableChannel trong Spring Framework với QueueChannel và poller trong Spring Integration.
- Thiết kế consumer có kiểm soát tải, xử lý timeout, lỗi và shutdown.
- Nhận biết giới hạn của queue trong bộ nhớ và khi nào cần broker hoặc kho lưu trữ bền vững.

## 1. PollableChannel giải quyết bài toán gì?

Trong mô hình messaging, producer gửi Message tới một channel và consumer nhận Message để xử lý. Có hai cách phổ biến để tổ chức phía nhận:

- **Push:** consumer đăng ký handler; channel chủ động gọi handler khi có thông điệp.
- **Pull hoặc polling:** consumer chủ động yêu cầu channel trả về thông điệp bằng cách gọi receive().

PollableChannel là hợp đồng của Spring Messaging dành cho cách nhận thứ hai. Consumer kiểm soát thời điểm gọi receive, có thể chọn chờ thông điệp hoặc chờ trong một khoảng thời gian nhất định.

Mô hình này hữu ích khi consumer muốn chủ động điều tiết tốc độ xử lý, chạy một vòng lặp nhận thông điệp, hoặc để một polling endpoint định kỳ kiểm tra channel. Producer không cần biết consumer đang gọi receive vào lúc nào; producer chỉ gửi Message theo hợp đồng MessageChannel.

Một điểm cần phân biệt ngay từ đầu: PollableChannel là interface mô tả cách nhận. Nó không tự quy định dữ liệu được lưu trong RAM, database hay broker. Cách lưu trữ, giới hạn queue, hành vi khi channel đầy và khả năng phục hồi phụ thuộc implementation cụ thể.

## 2. Vị trí của PollableChannel trong Spring Messaging

PollableChannel thuộc package org.springframework.messaging. Nó mở rộng MessageChannel và bổ sung hai phương thức nhận:

- receive(): lấy một Message, có thể chờ cho tới khi có thông điệp.
- receive(timeout): lấy một Message và chỉ chờ tối đa thời gian được chỉ định, tính bằng mili giây.

Mô hình khái niệm:

~~~mermaid
flowchart TB
    P["Producer"]
    C["MessageChannel"]
    PC["PollableChannel"]
    SC["SubscribableChannel"]
    Q["Queue hoặc storage<br/>do implementation quyết định"]
    R["Consumer gọi receive()"]
    H["MessageHandler được đăng ký"]

    P --> C
    C --> PC
    C --> SC
    PC --> Q
    R --> PC
    SC --> H
~~~

Sơ đồ nhấn mạnh hai kiểu nhận khác nhau. Một implementation cụ thể có thể cung cấp cơ chế lưu đệm và phân phối riêng; chỉ nhìn interface không thể suy ra toàn bộ hành vi vận hành.

Trong Spring Framework, PollableChannel là API nền tảng. Một implementation quen thuộc là QueueChannel của Spring Integration. QueueChannel nằm trong module Spring Integration, không phải class có sẵn chỉ nhờ dependency spring-messaging.

## 3. Hai phương thức receive()

### 3.1. receive() — chờ cho tới khi có thông điệp

Hợp đồng receive() cho phép consumer lấy một Message và chờ nếu chưa có thông điệp. Với implementation dạng queue thông thường, thread gọi receive() sẽ bị chặn cho tới khi có Message hoặc implementation kết thúc thao tác theo chính sách riêng.

Ví dụ minh họa:

~~~java
Message<?> message = channel.receive();

if (message != null) {
    process(message);
}
~~~

Vì receive() có thể chờ vô hạn, chỉ nên dùng khi vòng đời consumer được quản lý rõ ràng. Ứng dụng cần có cách dừng thread, xử lý interrupt và giải phóng tài nguyên khi shutdown.

### 3.2. receive(timeout) — giới hạn thời gian chờ

Phương thức receive(timeout) nhận timeout theo mili giây. Nếu không có Message trong khoảng thời gian chờ, implementation pollable thường trả về null.

~~~java
Message<?> message = channel.receive(1_000);

if (message == null) {
    System.out.println("No message before timeout");
}
else {
    process(message);
}
~~~

Timeout giúp consumer định kỳ kiểm tra các điều kiện khác, chẳng hạn trạng thái shutdown, lịch bảo trì hoặc metric. Nó cũng tránh giữ thread ở trạng thái chờ không giới hạn.

Cần phân biệt timeout của receive với thời gian xử lý payload. receive(1_000) giới hạn thời gian chờ lấy Message; nó không tự giới hạn thời gian mà process(message) được phép chạy. Nếu xử lý nghiệp vụ cần timeout, hãy đặt timeout riêng cho I/O hoặc thao tác nghiệp vụ.

### 3.3. Giá trị trả về là Message

PollableChannel trả về Message<?> để consumer có cả payload và headers. Consumer có thể đọc:

~~~java
Object payload = message.getPayload();
Object correlationId = message.getHeaders().get("correlationId");
~~~

Nếu muốn làm việc trực tiếp với kiểu payload cụ thể, hãy kiểm tra kiểu dữ liệu hoặc dùng converter/template thích hợp. Đừng giả định mọi Message trong channel đều có cùng payload type nếu producer không thống nhất schema.

## 4. Luồng pull hoạt động như thế nào?

Với mô hình pull, consumer chủ động hỏi channel xem có thông điệp hay chưa. Nếu channel có Message, consumer nhận một Message và xử lý. Nếu chưa có, consumer có thể chờ hoặc quay lại sau tùy cách gọi receive.

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant Q as PollableChannel
    participant C as Consumer thread

    C->>Q: receive(timeout)
    Note over C,Q: Consumer chủ động lấy thông điệp
    P->>Q: send(message)
    Q-->>C: Trả về Message
    C->>C: Xử lý payload và headers
    C->>Q: receive(timeout) lần tiếp theo
    Q-->>C: Message tiếp theo hoặc null khi hết timeout
~~~

Producer không gọi trực tiếp phương thức nghiệp vụ của consumer. Consumer kiểm soát nhịp nhận và thời điểm xử lý. Cách này có thể làm giảm áp lực lên hệ thống nhận khi consumer chỉ muốn lấy số lượng công việc mà nó có khả năng xử lý.

Trong mô hình queue point-to-point, một Message được lấy khỏi queue thường chỉ được một consumer nhận. Nếu có nhiều consumer cùng polling, chúng cạnh tranh lấy các Message có sẵn. Đây là đặc tính của implementation queue như QueueChannel, không phải lời hứa chung cho mọi implementation của PollableChannel.

## 5. Polling không đồng nghĩa với bất đồng bộ

Hai khái niệm này mô tả hai trục khác nhau:

- **Pull/push:** consumer chủ động lấy Message hay channel chủ động gọi handler.
- **Đồng bộ/bất đồng bộ:** producer và consumer có phải chờ nhau trong cùng luồng thực thi hay không.

Ví dụ:

| Cách nhận | Thread và thời điểm | Nhận xét |
|---|---|---|
| PollableChannel.receive() trong thread riêng | Consumer chờ và xử lý độc lập với producer | Thường được dùng trong xử lý nền |
| PollableChannel.receive() ngay trong thread gửi | Thread đó phải chờ Message theo luồng điều khiển của chính nó | Có thể tạo hành vi chờ đồng bộ |
| SubscribableChannel gọi handler trực tiếp | Handler có thể chạy ngay trong thread gọi send | Push nhưng xử lý đồng bộ |
| SubscribableChannel dispatch qua executor | Handler chạy sau trên worker thread | Push và thường bất đồng bộ |

Vì vậy, không nên kết luận rằng cứ dùng PollableChannel là hệ thống đã bất đồng bộ. Consumer có thể polling trong cùng thread với producer, hoặc chạy trong thread riêng. Điều quyết định là cách tổ chức luồng thực thi.

## 6. QueueChannel: implementation pollable thường gặp trong Spring Integration

QueueChannel là một implementation PollableChannel của Spring Integration. Nó lưu Message trong một queue để producer gửi vào và consumer lấy ra bằng receive.

Các điểm cần hiểu:

- QueueChannel thuộc package org.springframework.integration.channel.
- Nó triển khai hợp đồng PollableChannel của Spring Messaging.
- Message được lưu trong queue và được lấy ra khi consumer gọi receive.
- Có thể cấu hình sức chứa hữu hạn để giới hạn số Message đang chờ.
- Với nhiều consumer, các consumer cạnh tranh lấy Message từ queue theo semantics của implementation.
- QueueChannel mặc định là cơ chế lưu trong bộ nhớ; không nên coi nó là durable broker.

Ví dụ tạo một queue có sức chứa giới hạn:

~~~java
QueueChannel channel = new QueueChannel(100);
~~~

Con số 100 là sức chứa được cấu hình cho queue trong ví dụ. Trong ứng dụng thực tế, chọn capacity dựa trên tốc độ producer, tốc độ consumer, kích thước Message và ngân sách bộ nhớ.

### 6.1. Khi queue đầy

Nếu queue có giới hạn và producer gửi nhanh hơn tốc độ consumer nhận, queue có thể đầy. Khi đó, việc gửi có thể chờ, timeout hoặc không được chấp nhận tùy implementation và timeout của thao tác send.

Đừng bỏ qua kết quả boolean của send. Nếu send trả về false, producer cần có chính sách phù hợp: ghi nhận lỗi, retry có giới hạn, giảm tốc độ phát hoặc chuyển công việc sang cơ chế lưu trữ khác.

Một queue hữu hạn giúp tạo giới hạn bộ nhớ và thể hiện áp lực ngược (back-pressure) ở ranh giới gửi. Tuy nhiên, chỉ đặt capacity không tự tạo một chiến lược back-pressure hoàn chỉnh; ứng dụng vẫn phải quyết định phản ứng khi queue đầy.

### 6.2. QueueChannel không phải broker bền vững

QueueChannel lưu Message trong bộ nhớ của ứng dụng. Nếu tiến trình dừng bất ngờ, các Message chưa được xử lý có thể mất. Nó không tự cung cấp replication, persistence qua restart, acknowledgement từ broker hoặc dead-letter queue.

Nếu yêu cầu thông điệp tồn tại qua lần khởi động lại hoặc được truyền giữa nhiều tiến trình, hãy dùng adapter/broker phù hợp như JMS, AMQP hoặc Kafka và hiểu rõ bảo đảm của công nghệ đó.

## 7. Ví dụ Java 17 chạy được với QueueChannel

Ví dụ dưới đây dùng QueueChannel của Spring Integration để minh họa cách producer gửi và consumer chủ động lấy Message bằng receive(timeout). Chương trình cũng minh họa kết quả null khi queue không còn thông điệp.

### 7.1. Cấu hình Maven

Tạo file pom.xml:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>pollable-channel-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.integration</groupId>
            <artifactId>spring-integration-core</artifactId>
            <version>6.5.0</version>
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
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Dependency spring-integration-core kéo theo spring-messaging tương thích. Nếu ứng dụng chỉ cần interface PollableChannel để tích hợp với một implementation khác, hãy dùng dependency phù hợp với integration thực tế thay vì thêm Spring Integration chỉ để có một interface đã nằm trong Spring Messaging.

### 7.2. Chương trình hoàn chỉnh

Tạo file src/main/java/demo/PollableChannelDemo.java:

~~~java
package demo;

import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public class PollableChannelDemo {

    public static void main(String[] args) {
        QueueChannel channel = new QueueChannel(10);

        Message<String> outbound = MessageBuilder
                .withPayload("ORD-74")
                .setHeader("eventType", "order.created")
                .build();

        boolean accepted = channel.send(outbound);
        System.out.println("sendAccepted=" + accepted);

        // Consumer chủ động lấy Message và chờ tối đa 1 giây.
        Message<?> received = channel.receive(1_000);

        if (received == null) {
            System.out.println("receivedPayload=null");
        }
        else {
            System.out.println("receivedPayload=" + received.getPayload());
            System.out.println(
                    "eventType=" + received.getHeaders().get("eventType")
            );
        }

        // Queue đã rỗng; lần receive này hết timeout và trả về null.
        Message<?> secondReceive = channel.receive(100);
        System.out.println(
                "secondReceive=" + (secondReceive == null ? "null" : "message")
        );
    }
}
~~~

Chạy từ thư mục chứa pom.xml:

~~~bash
mvn -q clean compile exec:java -Dexec.mainClass=demo.PollableChannelDemo
~~~

Stdout:

~~~text
sendAccepted=true
receivedPayload=ORD-74
eventType=order.created
secondReceive=null
~~~

### 7.3. Phân tích kết quả

Producer tạo Message có payload ORD-74 và header eventType, sau đó gửi vào QueueChannel. send trả về true vì queue chấp nhận Message.

Consumer gọi receive(1_000), chủ động yêu cầu một Message và chờ tối đa một giây. Message được lấy ra khỏi queue, vì vậy consumer đọc được payload và header.

Lần receive tiếp theo không còn Message để lấy. Sau thời gian chờ 100 mili giây, QueueChannel trả về null. Consumer có thể dùng kết quả này để quay lại vòng lặp, kiểm tra trạng thái dừng hoặc thực hiện công việc định kỳ khác.

Ví dụ chạy producer và consumer trên cùng thread để giữ stdout xác định. Trong ứng dụng thực tế, producer và consumer thường có thread hoặc component riêng. Việc dùng QueueChannel không tự tạo một thread consumer; ứng dụng hoặc endpoint polling phải gọi receive.

## 8. Consumer polling trong một thread riêng

Một consumer nền có thể chạy vòng lặp nhận thông điệp. Dùng timeout hữu hạn giúp thread có cơ hội kiểm tra trạng thái shutdown thay vì chờ vô hạn:

~~~java
while (running && !Thread.currentThread().isInterrupted()) {
    Message<?> message = channel.receive(1_000);

    if (message == null) {
        continue;
    }

    try {
        process(message);
    }
    catch (RuntimeException ex) {
        handleFailure(message, ex);
    }
}
~~~

Đây là mã minh họa; các biến running, process và handleFailure phải được ứng dụng định nghĩa. Trong triển khai thực tế, cần lưu ý:

- Không nuốt exception mà không ghi log hoặc metric.
- Xác định Message lỗi sẽ được retry, chuyển sang nơi lưu lỗi hay bỏ qua.
- Có cơ chế dừng thread và chờ consumer kết thúc khi ứng dụng shutdown.
- Không chạy nhiều tác vụ chặn lâu trên cùng một thread polling nếu cần throughput cao.
- Nếu dùng nhiều consumer thread, kiểm tra khả năng thread-safe của handler và tài nguyên nghiệp vụ.

Nếu receive() bị chặn vô hạn, việc dừng thread có thể phụ thuộc khả năng interrupt của implementation. Timeout hữu hạn thường giúp lifecycle dễ kiểm soát hơn.

## 9. Poller trong Spring Integration

Spring Integration có khái niệm poller để tự động gọi receive trên PollableChannel theo lịch. Nhờ đó, ứng dụng không phải tự viết vòng lặp polling cho từng endpoint.

Ví dụ cấu hình annotation minh họa:

~~~java
@Configuration
@EnableIntegration
public class MessagingConfiguration {

    @Bean
    public QueueChannel ordersChannel() {
        return new QueueChannel(100);
    }

    @Bean
    @ServiceActivator(
            inputChannel = "ordersChannel",
            poller = @Poller(
                    fixedDelay = "1000",
                    maxMessagesPerPoll = "10"
            )
    )
    public MessageHandler orderHandler() {
        return message -> System.out.println(
                "Handling order: " + message.getPayload()
        );
    }
}
~~~

Trong ví dụ:

- QueueChannel lưu Message để consumer lấy sau.
- Service activator đăng ký logic xử lý cho input channel.
- Poller kích hoạt endpoint theo fixed delay một giây.
- maxMessagesPerPoll giới hạn số Message được xử lý trong một chu kỳ polling theo cấu hình.

Đây là cấu hình thuộc Spring Integration. Các annotation và endpoint như EnableIntegration, ServiceActivator và Poller không thuộc riêng module spring-messaging.

### 9.1. Polling interval và receive timeout khác nhau

Hai giá trị thường bị nhầm:

- **Polling interval/fixed delay:** khoảng thời gian scheduler chờ giữa các lần kích hoạt poller theo cấu hình.
- **Receive timeout:** thời gian một lần gọi receive có thể chờ Message.

Ví dụ poller chạy mỗi giây và mỗi lần receive chờ tối đa 200 mili giây. Consumer có thể chờ tối đa 200 mili giây trong lần nhận đó; lịch poller quyết định thời điểm endpoint được kích hoạt lần kế tiếp.

Không nên đặt receive timeout quá dài mà không xét scheduler thread pool, vì một lần poll bị chặn lâu có thể chiếm thread của scheduler. Cần chọn interval, timeout và số Message mỗi chu kỳ theo tải thực tế.

### 9.2. maxMessagesPerPoll và tốc độ xử lý

maxMessagesPerPoll giới hạn số Message được nhận trong một lần poll. Giá trị thấp giúp mỗi chu kỳ nhường thời gian cho công việc khác; giá trị cao có thể tăng throughput nhưng làm một chu kỳ kéo dài.

Cần cân bằng:

- Tốc độ producer đưa Message vào channel.
- Thời gian trung bình và độ biến thiên của handler.
- Số consumer hoặc polling endpoint.
- Queue capacity và ngân sách bộ nhớ.
- Độ trễ mà nghiệp vụ chấp nhận được.

## 10. Nhiều consumer cùng polling

Với QueueChannel dạng point-to-point, nhiều consumer có thể gọi receive trên cùng queue. Khi một Message được một consumer lấy ra, consumer khác không nhận cùng Message đó từ queue.

Điều này phù hợp với mô hình competing consumers: tăng số consumer để chia tải xử lý.

Tuy nhiên, cần lưu ý:

- Thứ tự bắt đầu xử lý và thứ tự hoàn tất có thể khác nhau khi nhiều consumer chạy song song.
- Một consumer xử lý chậm có thể giữ một Message trong thời gian dài, trong khi consumer khác tiếp tục lấy Message mới.
- Nếu các Message cùng cập nhật một đơn hàng, có thể xảy ra race condition hoặc sai thứ tự nghiệp vụ.
- Cần phân vùng theo khóa, khóa dữ liệu hoặc tuần tự hóa xử lý khi thứ tự là yêu cầu bắt buộc.

Nếu cần phát cùng một Message tới nhiều subscriber, hãy dùng mô hình publish-subscribe phù hợp. Không nên dùng QueueChannel với kỳ vọng mỗi consumer đều nhận một bản sao của mọi Message.

## 11. Xử lý lỗi, retry và tính bền vững

PollableChannel chỉ định nghĩa cách lấy Message. Nó không tự đảm bảo chính sách xử lý lỗi hoặc lưu trữ bền vững.

Khi consumer lấy một Message rồi xử lý thất bại, ứng dụng cần quyết định:

- Có retry ngay không?
- Có retry với backoff hay giới hạn số lần không?
- Có đưa Message sang error channel hoặc dead-letter queue không?
- Có ghi lại trạng thái để phục hồi sau restart không?
- Làm thế nào để tránh thực hiện nghiệp vụ hai lần nếu Message được gửi lại?

Với QueueChannel trong bộ nhớ, khi receive lấy Message ra, ứng dụng không nên giả định Message sẽ tự quay lại queue nếu handler thất bại. Nếu cần redelivery hoặc rollback, phải thiết kế transaction, error flow hoặc adapter lưu trữ phù hợp.

Với broker bên ngoài, acknowledgement, redelivery, visibility timeout, offset commit và dead-letter có semantics riêng. Hãy dựa trên tài liệu của broker và Spring integration tương ứng.

Một consumer nên xử lý theo hướng idempotent khi có khả năng retry: cùng một Message được xử lý lặp không tạo ra tác động nghiệp vụ sai hoặc trùng lặp.

## 12. Quan sát và điều tiết tải

Polling tạo ra một số tín hiệu cần theo dõi:

- **Queue depth:** số Message đang chờ.
- **Wait time:** thời gian Message nằm trong queue trước khi được nhận.
- **Processing time:** thời gian handler xử lý mỗi Message.
- **Poll frequency:** số lần polling trong một khoảng thời gian.
- **Empty poll count:** số lần receive timeout mà không có Message.
- **Failure/retry count:** số lỗi và số lần thử lại.
- **Rejection/send timeout:** số lần producer không thể đưa Message vào channel.

Nếu queue depth tăng liên tục, producer đang tạo tải nhanh hơn khả năng tiêu thụ. Tăng số worker có thể giúp, nhưng cần kiểm tra database, API ngoài, CPU và các tài nguyên phía sau consumer để tránh chuyển nút thắt sang nơi khác.

Một queue hữu hạn giúp giới hạn bộ nhớ. Khi queue gần đầy, ứng dụng có thể giảm tốc độ producer, từ chối công việc mới hoặc ghi nhận yêu cầu vào một kho bền vững để xử lý sau.

## 13. Khi nào nên dùng PollableChannel?

| Nhu cầu | PollableChannel có phù hợp? | Gợi ý |
|---|---|---|
| Consumer muốn tự quyết định thời điểm nhận | Có | Dùng receive hoặc polling endpoint |
| Consumer cần kiểm soát số Message xử lý mỗi lượt | Có | Kết hợp poller hoặc vòng lặp có giới hạn |
| Cần worker cạnh tranh lấy Message từ queue | Có, tùy implementation | QueueChannel là ví dụ point-to-point |
| Cần đẩy ngay Message tới handler đã đăng ký | Có thể dùng cơ chế khác | Xem SubscribableChannel |
| Cần broadcast tới mọi subscriber | Không nên giả định từ PollableChannel | Dùng publish-subscribe |
| Cần lưu Message qua restart hoặc giữa nhiều máy | Interface không đủ | Dùng broker hoặc MessageStore phù hợp |
| Cần xử lý bất đồng bộ | Có thể | Chạy consumer ở thread riêng hoặc dùng poller |
| Cần phản hồi ngay cho request hiện tại | Tùy bài toán | Xem request-reply hoặc API đồng bộ |

PollableChannel phù hợp khi consumer cần pull và điều tiết nhịp nhận. Nếu cần broker bền vững, broadcast hoặc các bảo đảm phân phối cụ thể, hãy chọn integration tương ứng.

## 14. Lỗi thường gặp

1. **Cho rằng PollableChannel tự lưu thông điệp:** interface không định nghĩa storage; implementation quyết định.
2. **Cho rằng PollableChannel luôn bất đồng bộ:** receive có thể chạy trong chính thread producer hoặc thread gọi nó.
3. **Dùng receive() vô hạn mà không có shutdown strategy:** consumer có thể bị giữ ở trạng thái chờ khi ứng dụng cần dừng.
4. **Nhầm receive timeout với thời gian xử lý:** timeout chỉ giới hạn việc chờ lấy Message.
5. **Không kiểm tra null:** receive(timeout) có thể trả về null khi hết thời gian chờ.
6. **Bỏ qua kết quả send:** queue đầy hoặc channel từ chối có thể khiến Message không được chấp nhận.
7. **Dùng queue không giới hạn:** tải tăng có thể làm bộ nhớ tăng liên tục.
8. **Kỳ vọng QueueChannel có durability:** queue trong bộ nhớ không thay thế broker lưu bền.
9. **Cho rằng nhiều consumer đều nhận cùng Message:** queue point-to-point thường phân phối mỗi Message cho một consumer lấy được nó.
10. **Không kiểm soát thứ tự:** nhiều consumer có thể hoàn tất Message không theo thứ tự phát.
11. **Xử lý lỗi rồi bỏ Message mà không ghi nhận:** cần retry, error flow hoặc chính sách bỏ có chủ đích.
12. **Nhầm PollableChannel với QueueChannel:** PollableChannel là hợp đồng của Spring Messaging; QueueChannel là implementation của Spring Integration.

## 15. Câu hỏi tự kiểm tra

1. PollableChannel khác SubscribableChannel ở cách consumer nhận Message như thế nào?
2. receive() khác receive(timeout) ở hành vi chờ ra sao?
3. Đơn vị timeout của receive(timeout) là gì?
4. Vì sao receive(timeout) có thể trả về null?
5. Polling có luôn đồng nghĩa với bất đồng bộ không?
6. QueueChannel thuộc module nào và triển khai hợp đồng nào?
7. Điều gì xảy ra khi nhiều consumer cùng polling một QueueChannel?
8. Vì sao QueueChannel trong bộ nhớ không đáp ứng yêu cầu durable delivery?
9. Polling interval khác receive timeout ở điểm nào?
10. Khi consumer xử lý lỗi sau khi đã lấy Message khỏi queue, cần thiết kế những cơ chế nào?

## 16. Kết luận

PollableChannel là hợp đồng nhận Message theo kiểu pull trong Spring Messaging. Consumer chủ động gọi receive() hoặc receive(timeout), kiểm soát thời điểm lấy dữ liệu và có thể giới hạn thời gian chờ. Cách nhận này hữu ích khi muốn điều tiết tốc độ consumer hoặc tổ chức xử lý theo từng lượt.

PollableChannel không tự quy định cách lưu trữ hay tính bền vững. QueueChannel của Spring Integration là một implementation dạng queue thường gặp, còn poller của Spring Integration giúp kích hoạt việc nhận theo lịch. Khi triển khai, cần phân biệt rõ interface, implementation và hạ tầng broker; đồng thời quản lý timeout, queue capacity, concurrency, shutdown và xử lý lỗi.

## Tài liệu tham khảo chính thức

- Spring Framework PollableChannel API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/PollableChannel.html
- Spring Framework MessageChannel API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/MessageChannel.html
- Spring Framework SubscribableChannel API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/SubscribableChannel.html
- Spring Integration channel reference: https://docs.spring.io/spring-integration/reference/channel.html
- Spring Integration QueueChannel API: https://docs.spring.io/spring-integration/api/org/springframework/integration/channel/QueueChannel.html
- Spring Integration endpoint and poller reference: https://docs.spring.io/spring-integration/reference/endpoint.html
