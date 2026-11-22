# Inbound channel và outbound channel

## Mục tiêu bài học

Trong chương **Messaging bridge** của module **SPRING_INTEGRATION_CORE**, bài học này tập trung vào hai phía của một bridge: channel mà bridge nhận message và channel mà bridge gửi message tới. Đây là kiến thức nền để ghép các endpoint, gateway và luồng Java DSL thành một luồng thông điệp có hành vi rõ ràng.

Sau bài học, bạn có thể:

- Xác định input channel và output channel khi đọc sơ đồ hoặc cấu hình bridge.
- Phân biệt hướng inbound/outbound của bridge với hướng của channel adapter.
- Chọn channel phù hợp và đặt poller đúng endpoint.
- Theo dõi payload, headers, luồng thực thi và lỗi khi message đi qua bridge.
- Thiết kế cách kiểm chứng việc chuyển tiếp message trong một ví dụ Java DSL.

## 1. Inbound và outbound phải gắn với một điểm nhìn

Xét một hệ thống tiếp nhận đơn hàng:

~~~text
Nguồn đơn hàng
    → ordersReceived
    → bridge
    → ordersForProcessing
    → endpoint xử lý đơn
~~~

Đứng tại bridge:

| Thành phần | Vai trò |
| --- | --- |
| Nguồn đơn hàng | Producer gửi message vào channel phía trước bridge |
| ordersReceived | Inbound channel của bridge, tức input channel |
| Bridge | Endpoint nhận message ở phía vào rồi chuyển sang phía ra |
| ordersForProcessing | Outbound channel của bridge, tức output channel |
| Endpoint xử lý đơn | Consumer tiếp theo trong luồng |

“Inbound channel” và “outbound channel” trong bài là cách gọi **vai trò tương đối với bridge**. Khi cấu hình XML, các thuộc tính tương ứng là input-channel và output-channel. Chúng không phải hai lớp channel riêng có tên InboundChannel và OutboundChannel.

Một channel có thể mang hai vai trò khi nhìn từ các endpoint khác nhau:

~~~text
Endpoint A ──gửi──> channel X ──nhận──> Endpoint B
~~~

channel X là đầu ra của A và đầu vào của B. Bởi vậy, tên như ordersReceived hoặc ordersReady thường thể hiện ý nghĩa nghiệp vụ tốt hơn tên chung chung inbound và outbound.

Theo [tài liệu Messaging Bridge](https://docs.spring.io/spring-integration/reference/bridge.html), bridge nối các message channel; một tình huống điển hình là nối channel có thể polling với channel có subscriber.

### Phân biệt với inbound adapter và outbound adapter

Khi nói về **adapter**, điểm nhìn thường là ứng dụng tích hợp:

~~~mermaid
flowchart LR
    S["Hệ thống nguồn"] --> IA["Inbound adapter"]
    IA --> I["Input channel của bridge"]
    I --> B["Messaging bridge"]
    B --> O["Output channel của bridge"]
    O --> OA["Outbound adapter"]
    OA --> T["Hệ thống đích"]
~~~

- Inbound adapter đưa dữ liệu từ nguồn vào luồng message của ứng dụng.
- Outbound adapter chuyển dữ liệu từ luồng message tới đích.
- Bridge nối hai điểm trong luồng và không tự trở thành adapter cho một giao thức.

Ví dụ, adapter đọc file chịu trách nhiệm tiếp xúc với hệ thống file. Adapter gửi JMS chịu trách nhiệm giao tiếp với JMS. Đặt bridge giữa hai channel không tự bổ sung khả năng đọc file, kết nối broker hay cấu hình xác thực. Xem [Channel Adapter](https://docs.spring.io/spring-integration/reference/channel-adapter.html).

Một hệ thống có thể dùng bridge chỉ giữa hai luồng nội bộ, hoàn toàn không có hệ thống bên ngoài trong đoạn nối đó.

## 2. Hợp đồng của hai phía channel

### 2.1. MessageChannel là hợp đồng gửi

Ở mức sử dụng cơ bản:

~~~java
boolean accepted = channel.send(message, 1_000);
~~~

Producer cần một MessageChannel để gửi. Giá trị trả về biểu thị kết quả gửi theo cơ chế của channel; khi gặp lỗi dispatch hoặc lỗi xử lý đồng bộ, lời gọi cũng có thể ném exception.

Không thể suy ra rằng accepted bằng true luôn có nghĩa đơn hàng đã được xử lý xong. Ý nghĩa cụ thể còn phụ thuộc channel nhận message.

### 2.2. PollableChannel có thao tác nhận chủ động

PollableChannel bổ sung receive():

~~~java
Message<?> message = queueChannel.receive(1_000);

if (message != null) {
    // Xử lý message vừa nhận.
}
~~~

QueueChannel là ví dụ quen thuộc. Một consumer phải chủ động lấy message ra khỏi queue. Với endpoint do Spring Integration quản lý, công việc đó thường được thực hiện bằng poller.

### 2.3. SubscribableChannel chuyển message tới handler đã đăng ký

SubscribableChannel có cơ chế đăng ký MessageHandler. Nó không cung cấp receive() để consumer polling.

DirectChannel là một triển khai phổ biến. Endpoint gắn với channel này được gọi theo cơ chế dispatch khi có message gửi tới.

Các hợp đồng send, receive và subscribe được mô tả trong [The MessageChannel Interface](https://docs.spring.io/spring-integration/reference/channel/interfaces.html).

> Hướng vào/ra trả lời “message đang đi đâu so với endpoint?”. Pollable/subscribable trả lời “endpoint nhận message bằng cơ chế nào?”. Đây là hai câu hỏi khác nhau.

## 3. Bridge chuyển tiếp những gì?

BridgeHandler là handler thực hiện việc chuyển tiếp message. Trong trường hợp thông thường, nó đưa message nhận được sang output channel mà không áp dụng phép biến đổi nghiệp vụ. Xem [BridgeHandler API](https://docs.spring.io/spring-integration/api/org/springframework/integration/handler/BridgeHandler.html).

Giả sử message vào có:

~~~text
payload = "ORDER-1001"

headers:
  traceId  = "trace-1001"
  tenantId = "shop-vn"
~~~

Một bridge thuần không có bước biến đổi phải cho phép phía sau tiếp tục nhận payload và các header đó. Khi kiểm chứng, nên so sánh dữ liệu cần bảo toàn, thay vì mặc định mọi pipeline đều giữ cùng một tham chiếu Java: interceptor hoặc endpoint bổ sung có thể ảnh hưởng kết quả.

Đối chiếu với các thành phần khác trong module:

| Nhu cầu nghiệp vụ | Thành phần phù hợp |
| --- | --- |
| Chuyển nguyên message từ channel A sang channel B | Bridge |
| Đổi payload từ chuỗi JSON thành đối tượng đơn hàng | Transformer |
| Chọn channel đích theo loại đơn | Router |
| Loại đơn không đạt điều kiện | Filter |
| Gom nhiều message theo correlation thành một kết quả | Aggregator |
| Cung cấp giao diện phương thức để gọi vào luồng message | Messaging gateway |

Bảng này là cách lựa chọn thiết kế cho ví dụ đơn hàng. Nếu hai hệ thống cần hai định dạng dữ liệu khác nhau, hãy biểu diễn bước chuyển đổi rõ ràng trong luồng.

## 4. Kiểu channel đầu vào quyết định cách bridge nhận message

### 4.1. DirectChannel ở đầu vào

~~~text
Producer thread
    → DirectChannel
    → BridgeHandler
    → output channel
~~~

Bridge được gắn vào input channel qua endpoint có cơ chế subscription. Không cần poller để lấy message từ DirectChannel.

Nếu output cũng là DirectChannel, chuỗi xử lý thông thường tiếp tục trên thread đang gửi, cho tới khi gặp một ranh giới thực thi khác.

### 4.2. QueueChannel ở đầu vào

~~~text
Producer thread
    → QueueChannel
    → producer có thể tiếp tục

Poller thread
    → receive từ QueueChannel
    → BridgeHandler
    → output channel
~~~

Bridge cần một polling consumer để lấy message. Cấu hình poller thuộc **endpoint tiêu thụ input channel**, không phải một tác vụ tự chạy bên trong QueueChannel.

Cần cung cấp poller riêng hoặc có default poller phù hợp trong context. Trong ví dụ của bài, poller được khai báo tường minh ngay trên bridge.

Spring Integration phân biệt EventDrivenConsumer và PollingConsumer theo kiểu channel mà endpoint tiêu thụ. Xem [Poller](https://docs.spring.io/spring-integration/reference/polling-consumer.html).

### 4.3. Bảng phối hợp input và output

Bảng dưới áp dụng cho DirectChannel và QueueChannel thông thường:

| Input channel | Output channel | Bridge lấy message bằng cách nào? | Sau khi bridge gửi ra |
| --- | --- | --- | --- |
| DirectChannel | DirectChannel | Subscription, không polling | Dispatch tiếp tới subscriber |
| QueueChannel | DirectChannel | Poller của bridge gọi receive() | Dispatch tới subscriber trên thread đang thực thi poll |
| DirectChannel | QueueChannel | Subscription, không polling | Message được đưa vào queue đầu ra |
| QueueChannel | QueueChannel | Poller lấy từ queue đầu vào | Message được đưa vào queue đầu ra |

Điểm cần tách biệt là **poller của bridge đọc phía vào**, còn **consumer kế tiếp đọc phía ra**. Nếu output là QueueChannel, endpoint phía sau vẫn cần cơ chế lấy message của riêng nó.

Với ExecutorChannel hoặc PublishSubscribeChannel, hãy xét thêm executor và cơ chế phân phối cụ thể. Không nên kết luận mọi SubscribableChannel đều xử lý trên thread của producer. Xem [Message Channel Implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html).

## 5. Ví dụ Java DSL: QueueChannel → bridge → DirectChannel

### 5.1. Bài toán và điều kiện sử dụng

Ứng dụng nhận một lượng đơn hàng tăng đột biến. Ta muốn:

1. Đưa đơn vào queue có dung lượng giới hạn.
2. Lấy tối đa năm message trong một lượt polling.
3. Chuyển message sang channel xử lý theo cơ chế subscription.
4. Thu message ở cuối luồng để quan sát payload và headers.

Ví dụ dưới là mã minh họa trong tệp BridgeDemo.java. Cần spring-integration-core và spring-context tương thích; nếu dùng Spring Boot, có thể sử dụng dependency management của Boot để đồng bộ phiên bản. Cú pháp dùng IntegrationFlow.from của Java DSL, với các dependency đáp ứng yêu cầu JDK của phiên bản bạn chọn.

~~~java
package example.bridge;

import java.time.Duration;
import java.util.Objects;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

public class BridgeDemo {

    @Configuration
    @EnableIntegration
    public static class BridgeConfig {

        @Bean
        public QueueChannel bridgeInbound() {
            return new QueueChannel(100);
        }

        @Bean
        public DirectChannel bridgeOutbound() {
            return new DirectChannel();
        }

        @Bean
        public QueueChannel observedMessages() {
            return new QueueChannel(100);
        }

        @Bean
        public IntegrationFlow forwardingFlow() {
            return IntegrationFlow.from("bridgeInbound")
                    .bridge(endpoint -> endpoint
                            .id("ordersBridge")
                            .poller(Pollers.fixedDelay(Duration.ofMillis(100))
                                    .receiveTimeout(0)
                                    .maxMessagesPerPoll(5)))
                    .channel("bridgeOutbound")
                    .get();
        }

        @Bean
        public IntegrationFlow observationFlow() {
            return IntegrationFlow.from("bridgeOutbound")
                    .handle((Message<?> message) -> {
                        boolean accepted =
                                observedMessages().send(message, 1_000);

                        if (!accepted) {
                            throw new IllegalStateException(
                                    "Observation queue is full");
                        }
                    })
                    .get();
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(BridgeConfig.class)) {

            MessageChannel input =
                    context.getBean("bridgeInbound", MessageChannel.class);
            QueueChannel observed =
                    context.getBean("observedMessages", QueueChannel.class);

            Message<String> sent = MessageBuilder
                    .withPayload("ORDER-1001")
                    .setHeader("traceId", "trace-1001")
                    .setHeader("tenantId", "shop-vn")
                    .build();

            if (!input.send(sent, 1_000)) {
                throw new IllegalStateException("Input queue is full");
            }

            Message<?> received = observed.receive(3_000);

            if (received == null) {
                throw new IllegalStateException(
                        "No message reached the observation queue");
            }

            if (!Objects.equals(sent.getPayload(), received.getPayload())
                    || !Objects.equals(
                            sent.getHeaders().get("traceId"),
                            received.getHeaders().get("traceId"))
                    || !Objects.equals(
                            sent.getHeaders().get("tenantId"),
                            received.getHeaders().get("tenantId"))) {
                throw new IllegalStateException(
                        "Payload or business headers changed");
            }

            System.out.println(received.getPayload() + " / "
                    + received.getHeaders().get("traceId"));
        }
    }
}
~~~

Đầu ra dự kiến:

~~~text
ORDER-1001 / trace-1001
~~~

observedMessages là điểm thu phục vụ minh họa. Trong luồng nghiệp vụ, observationFlow có thể được thay bằng service activator xử lý đơn hoặc outbound adapter chuyển dữ liệu tới hệ thống đích.

### 5.2. Đọc từng phần cấu hình

| Cấu hình | Ý nghĩa trong ví dụ |
| --- | --- |
| from("bridgeInbound") | Channel mà endpoint bridge sẽ tiêu thụ |
| bridge(...) | Đưa BridgeHandler vào luồng và cấu hình endpoint của nó |
| id("ordersBridge") | Đặt tên endpoint để nhận diện |
| fixedDelay(Duration.ofMillis(100)) | Khoảng nghỉ giữa các lượt poll, tính sau khi tác vụ trước hoàn tất trong cấu hình đang dùng |
| receiveTimeout(0) | Không chờ khi thử nhận từ queue đang rỗng |
| maxMessagesPerPoll(5) | Giới hạn số message được lấy trong một lượt |
| channel("bridgeOutbound") | Đích gửi của bridge |
| observationFlow | Subscriber tiêu thụ bridgeOutbound |
| observed.receive(3_000) | Điểm chờ có thời hạn để quan sát kết quả |

IntegrationFlow phải được đăng ký thành bean để hạ tầng Spring Integration tạo và quản lý các thành phần của luồng. Xem [Java DSL](https://docs.spring.io/spring-integration/reference/dsl.html).

Các overload fixedDelay và fixedRate nhận Duration được mô tả trong [Pollers API](https://docs.spring.io/spring-integration/api/org/springframework/integration/dsl/Pollers.html).

### 5.3. Trình tự thực thi

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant Q as bridgeInbound: QueueChannel
    participant T as Poller
    participant B as BridgeHandler
    participant D as bridgeOutbound: DirectChannel
    participant H as Observation handler
    participant R as observedMessages: QueueChannel

    P->>Q: send(message, 1000)
    Q-->>P: true khi đưa vào queue thành công
    T->>Q: receive(0)
    Q-->>T: message
    T->>B: handleMessage(message)
    B->>D: send(message)
    D->>H: handleMessage(message)
    H->>R: send(message, 1000)
~~~

Trong cấu hình này, handler quan sát chạy trên thread đang thực thi poll vì bridgeOutbound là DirectChannel. Producer ban đầu có thể đã tiếp tục công việc ngay sau khi đưa message vào bridgeInbound.

Vì vậy, try/catch quanh input.send() chỉ bao quanh giai đoạn gửi vào queue. Nó không thu được exception xảy ra sau đó trên tác vụ polling.

### 5.4. Năm message mỗi lượt không phải một message chứa năm đơn

maxMessagesPerPoll(5) giới hạn số lần lấy và xử lý message trong một lượt. Nó không gom năm payload thành danh sách; nếu cần gom nhóm, đó là nhiệm vụ của aggregator.

Queue rỗng sớm thì lượt poll có thể xử lý ít hơn năm message. Thời gian xử lý phía sau cũng ảnh hưởng nhịp thực tế.

Ước tính cho chính cấu hình này, khi queue luôn có dữ liệu và tác vụ chạy tuần tự:

~~~text
thông lượng gần đúng
    ≈ số message mỗi lượt / (thời gian xử lý một lượt + fixedDelay)

Ví dụ:
    5 message / (0,04 giây + 0,10 giây)
    ≈ 35,7 message/giây
~~~

Đây là phép ước tính từ giả định của ví dụ, không phải cam kết thông lượng. Với executor, nhiều consumer, lỗi hoặc cấu hình lịch khác, phải đánh giá lại mô hình thực thi.

## 6. Cùng hướng nối khi đọc XML

Đoạn cấu hình sau minh họa cùng hướng nối. Giả sử namespace int đã được khai báo là http://www.springframework.org/schema/integration trong tài liệu Spring XML:

~~~xml
<int:channel id="bridgeInbound">
    <int:queue capacity="100"/>
</int:channel>

<int:channel id="bridgeOutbound"/>

<int:bridge id="ordersBridge"
            input-channel="bridgeInbound"
            output-channel="bridgeOutbound">
    <int:poller fixed-delay="100"
                receive-timeout="0"
                max-messages-per-poll="5"/>
</int:bridge>
~~~

Đây là một đoạn cấu hình, cần có consumer đăng ký với bridgeOutbound để hoàn thiện luồng, giống observationFlow của ví dụ Java DSL.

Đọc theo thứ tự:

- input-channel là nơi bridge lấy message.
- output-channel là nơi bridge chuyển message tới.
- poller nằm dưới bridge vì bridgeInbound là QueueChannel.

Chọn XML hoặc Java DSL cho cùng endpoint. Nếu khai báo cả hai phiên bản bridge cùng tiêu thụ một QueueChannel, bạn đã tạo thêm consumer cạnh tranh lấy message.

## 7. Khi output channel là queue

Một cách phối hợp khác là cho producer gửi đồng bộ tới bridge rồi đưa message vào queue đầu ra:

~~~java
@Bean
public DirectChannel immediateInput() {
    return new DirectChannel();
}

@Bean
public QueueChannel bufferedOutput() {
    return new QueueChannel(100);
}

@Bean
public IntegrationFlow bufferFlow() {
    return IntegrationFlow.from("immediateInput")
            .bridge(endpoint -> endpoint.id("bufferBridge"))
            .channel("bufferedOutput")
            .get();
}
~~~

Đặt các bean này trong một lớp @Configuration có @EnableIntegration; các import channel và DSL giống ví dụ trước.

bufferBridge không cần poller vì input của nó là DirectChannel. bufferedOutput chỉ lưu message để consumer khác lấy sau.

Ba thời điểm cần phân biệt trong thiết kế là:

~~~text
1. Producer gọi send().
2. Message được đưa thành công vào bufferedOutput.
3. Consumer phía sau lấy và xử lý xong message.
~~~

Thành công ở thời điểm 2 chưa xác nhận thời điểm 3. Nếu yêu cầu là “trả về kết quả xử lý đơn”, hãy thiết kế thêm hợp đồng request/reply, chẳng hạn qua messaging gateway.

Không thêm poller cho bridge chỉ vì nhìn thấy QueueChannel ở đầu ra. Poller cần đặt tại endpoint nào thực sự đọc queue đó.

## 8. Output channel tường minh và replyChannel

Cách dễ theo dõi nhất là chỉ rõ output channel của bridge. Tuy nhiên, bridge cũng có thể chuyển message theo replyChannel header khi không có output channel được cấu hình. Nếu cả hai đều không có, bridge không có đích gửi và việc xử lý sẽ thất bại. Quy tắc này được nêu trong [Messaging Bridge](https://docs.spring.io/spring-integration/reference/bridge.html).

Ví dụ độc lập, không dùng chung tên channel với cấu hình chính:

~~~xml
<int:channel id="requests"/>

<int:bridge id="replyBridge"
            input-channel="requests"/>
~~~

Caller của luồng này phải cung cấp reply channel, chẳng hạn:

~~~java
QueueChannel replies = new QueueChannel(1);

Message<String> request = MessageBuilder
        .withPayload("PING")
        .setReplyChannel(replies)
        .build();

// requests là MessageChannel lấy từ context chứa cấu hình XML trên.
if (!requests.send(request, 1_000)) {
    throw new IllegalStateException("Request was not accepted");
}

Message<?> reply = replies.receive(1_000);

if (reply == null) {
    throw new IllegalStateException("No reply received");
}
~~~

replies ở đây là QueueChannel do caller giữ để nhận kết quả. Bridge thuần sẽ chuyển tiếp payload "PING"; nó không tự tạo một kết quả nghiệp vụ mới.

Trong một luồng cố định, output channel tường minh giúp người đọc nhìn thấy đích gửi ngay trong cấu hình. Chỉ dùng cơ chế replyChannel khi đó là một phần chủ ý của hợp đồng gọi.

## 9. Dung lượng, thời gian chờ và lỗi

### 9.1. Queue có giới hạn cần chính sách khi đầy

Với new QueueChannel(100), sức chứa được giới hạn ở 100 message. API cung cấp các thao tác quan sát như getQueueSize() và getRemainingCapacity(); xem [QueueChannel API](https://docs.spring.io/spring-integration/api/org/springframework/integration/channel/QueueChannel.html).

Ví dụ bài học dùng send(message, 1_000) và kiểm tra boolean để tránh chờ không giới hạn ở điểm gửi trực tiếp vào queue.

Phân biệt các thông số thời gian:

| Thông số | Chờ ở đâu? |
| --- | --- |
| Timeout trong input.send(message, timeout) | Khi gửi vào input channel |
| receiveTimeout của poller | Khi poller thử lấy message từ input queue |
| send timeout của handler chuyển tiếp | Khi handler gửi tới output channel |
| Timeout trong observed.receive(timeout) | Khi phía quan sát chờ message kết quả |

Đặt timeout ở producer không tự cấu hình timeout của mọi bước phía sau. Nếu output queue có thể đầy, hãy xác định rõ thời gian chờ gửi của handler và cách xử lý khi không chuyển tiếp được.

### 9.2. Lỗi đi theo ranh giới thực thi

| Luồng | Nơi quan sát lỗi xử lý |
| --- | --- |
| Producer → DirectChannel → bridge → DirectChannel → handler | Exception thường truyền về caller qua cùng call stack |
| Producer → QueueChannel → poller → bridge → handler | Lỗi phía sau queue phát sinh trong tác vụ poll |
| Bridge → QueueChannel → consumer khác | Lỗi xử lý sau đó thuộc lần thực thi của consumer đó |

Với tác vụ polling do hạ tầng Spring Integration quản lý, cơ chế mặc định có thể công bố ErrorMessage tới error channel. Đích thường được xác định từ errorChannel header của message, nếu có, hoặc channel toàn cục errorChannel. Cần xét lại nếu tự thay error handler hoặc scheduler.

Chỉ gắn errorChannel header không tự biến exception trong một lời gọi DirectChannel đồng bộ thành xử lý bất đồng bộ. Xem [Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html).

Khi điều tra ví dụ đơn hàng, nên ghi nhận tên endpoint, traceId, thời điểm nhận/gửi, kích thước queue và nguyên nhân lỗi để biết message đã đi tới đâu.

### 9.3. Bridge không bổ sung bảo đảm lưu trữ

QueueChannel thông thường trong ví dụ giữ message trong bộ nhớ. Bridge không tự cung cấp lưu trữ bền vững, retry hay bảo đảm exactly-once cho toàn hệ thống.

Một tình huống cần dự kiến khi thiết kế:

~~~text
Poller lấy message khỏi input queue
    → gửi tới output
    → downstream gặp lỗi
~~~

Không nên mặc định message sẽ tự quay lại input queue. Hành vi phục hồi phải được thiết kế dựa trên queue/message store, transaction, retry và khả năng của adapter hoặc broker được sử dụng.

Nếu nghiệp vụ yêu cầu không mất đơn và chịu được xử lý lặp, hãy chọn cơ chế lưu trữ/phục hồi phù hợp và thiết kế consumer idempotent theo mã đơn. Đây là quyết định bổ sung cho luồng; việc đặt một bridge giữa hai channel chưa giải quyết đủ yêu cầu đó.

## 10. Những nhầm lẫn thường gặp

| Hiện tượng hoặc cách hiểu | Điểm cần kiểm tra |
| --- | --- |
| Đã gửi vào QueueChannel nhưng không thấy message đi tiếp | Endpoint đọc queue có hoạt động và có poller phù hợp chưa? |
| Thêm poller vì output là QueueChannel | Hãy xác định input của chính endpoint bridge |
| DirectChannel báo không có subscriber | Endpoint phía nhận có được đăng ký và đang chạy không? |
| Đơn chỉ đi qua một trong hai bridge | Có nhiều consumer cạnh tranh trên cùng input channel không? |
| Muốn gửi một bản cho mỗi nhánh nhưng dùng DirectChannel | Cần xem lại yêu cầu broadcast và kiểu channel |
| Bridge nối thành công nhưng hệ thống đích không hiểu payload | Thiếu bước chuyển đổi định dạng hoặc hợp đồng dữ liệu không khớp |
| send() thành công nên kết luận đơn đã xử lý xong | Xác định channel chỉ nhận vào queue hay đã gọi handler đồng bộ |
| Không khai báo output vì cho rằng message sẽ tự kết thúc | Bridge cần đích gửi tường minh hoặc replyChannel hợp lệ |
| Sau khi thêm queue, caller không bắt được lỗi như trước | Queue đã tách lần gửi khỏi lần xử lý sau đó |
| Chỉ đổi tên channel để đảo hướng luồng | Hướng được quyết định bởi cấu hình endpoint và nơi gửi message |

Đặc biệt, hai bridge cùng đọc một queue không tạo ra hai bản sao message cho hai bên. Nếu yêu cầu là hai nghiệp vụ đều nhận một sự kiện, phải biểu diễn rõ cơ chế phân phối tương ứng.

## 11. Thực hành kiểm chứng

Các bước sau dành cho người học thực hành trên ví dụ; chúng không phải báo cáo rằng mã đã được chạy trong môi trường của bạn.

### Bài tập 1: Kiểm chứng hợp đồng chuyển tiếp

Gửi message có payload "ORDER-1001", traceId và tenantId như ví dụ. Nhận tại observedMessages với timeout hữu hạn rồi kiểm tra:

1. Nhận được message.
2. Payload đúng giá trị đã gửi.
3. traceId và tenantId được bảo toàn.
4. Không tự suy ra thành công nghiệp vụ từ kết quả send() vào bridgeInbound.

Không dùng Thread.sleep cố định để đoán message đã tới. receive(timeout) cho phép chờ đúng sự kiện cần quan sát và phát hiện trường hợp không có kết quả.

### Bài tập 2: Đổi kiểu input channel

Trong một bản sao cấu hình dùng để thực hành, thay bridgeInbound thành DirectChannel và bỏ poller khỏi ordersBridge.

Ghi lại tên thread tại producer và observation handler, sau đó đối chiếu với cấu hình QueueChannel ban đầu. Giải thích điểm nào trong luồng đã tạo ra sự khác biệt về thread.

### Bài tập 3: Đổi kiểu output channel

Chuyển bridgeOutbound thành QueueChannel và cấu hình poller cho endpoint quan sát đang đọc nó.

Trước khi chạy, vẽ lại hai điểm polling:

~~~text
bridgeInbound queue
    → poller của bridge
    → bridgeOutbound queue
    → poller của endpoint quan sát
~~~

Giải thích vì sao chỉ đổi bean DirectChannel thành QueueChannel mà không xem lại consumer phía sau có thể làm cấu hình thiếu cơ chế nhận message.

### Bài tập 4: Quan sát lỗi có chủ đích

Cho observation handler ném exception khi nhận một mã đơn xác định. So sánh:

- Input là DirectChannel: caller gửi message quan sát lỗi ra sao?
- Input là QueueChannel: caller đã nhận kết quả send() chưa khi lỗi xử lý xảy ra?
- Error flow có đủ traceId và thông tin message thất bại để truy vết không?

Giữ các bài tập độc lập, không đăng ký đồng thời nhiều bridge ngoài ý muốn trên cùng input channel.

## 12. Điểm cần nhớ

Khi thiết kế hai phía của một messaging bridge, hãy xác định lần lượt:

1. **Hướng:** channel nào là input và channel nào là output của endpoint đang xét?
2. **Cách nhận:** input được tiêu thụ bằng subscription hay polling?
3. **Cách chuyển tiếp:** output dispatch ngay hay lưu message để xử lý sau?
4. **Hợp đồng dữ liệu:** cần giữ nguyên message hay cần thêm bước biến đổi?
5. **Kết quả và lỗi:** send() xác nhận giai đoạn nào, lỗi phát sinh trên thread nào?
6. **Khả năng phục hồi:** message chờ ở đâu và điều gì xảy ra khi bước kế tiếp thất bại?

Trả lời được sáu câu hỏi này giúp bạn ghép bridge vào luồng Spring Integration mà vẫn theo dõi được đường đi, dữ liệu và trạng thái xử lý của từng message.
