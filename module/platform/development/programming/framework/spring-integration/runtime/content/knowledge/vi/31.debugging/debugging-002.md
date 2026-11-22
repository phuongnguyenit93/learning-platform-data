# Khoanh vùng channel không có subscriber

Khi vận hành Spring Integration, một lỗi thường gặp là message đã được gửi vào channel nhưng không có endpoint nào nhận. Log có thể chứa cụm **<code>Dispatcher has no subscribers</code>**, một <code>MessageDispatchingException</code>, hoặc chỉ xuất hiện triệu chứng không có reply. Các biểu hiện này **không tương đương nhau**: có channel bắt buộc phải có subscriber ngay lúc gửi, có channel chuyên lưu message để poller lấy sau, và có channel phát sự kiện cho phép số subscriber bằng 0 theo cấu hình.

Bài học **“Khoanh vùng channel không có subscriber”** thuộc chương **Debugging** của module **SPRING_INTEGRATION_RUNTIME**. Mục tiêu là lần theo các bước message flow qua channel, consumer endpoint, poller, executor, router và dynamic <code>IntegrationFlow</code>; phân biệt lỗi wiring với lỗi lifecycle hoặc delivery; sau đó dùng quan sát runtime, thử nghiệm Java/JUnit và kiểm tra transaction, retry, error channel, correlation để tìm đúng nguyên nhân.

> **Quy tắc đầu tiên:** Trước khi sửa cấu hình, xác định **kiểu channel cụ thể**, **số subscriber tại thời điểm lỗi** và **luồng xử lý lỗi nằm ở thread nào**. Không vội gắn một subscriber giả để làm mất exception: như vậy có thể biến sự cố giao hàng thành mất dữ liệu âm thầm.

## 1. Subscriber thực sự là gì?

Trong Spring Messaging, <code>SubscribableChannel</code> cho phép một <code>MessageHandler</code> đăng ký bằng <code>subscribe(handler)</code> và hủy bằng <code>unsubscribe(handler)</code>. Những endpoint nhận message theo cơ chế sự kiện của Spring Integration, ví dụ <code>EventDrivenConsumer</code> hoặc endpoint của <code>@ServiceActivator</code> gắn với <code>DirectChannel</code>, quản lý đăng ký handler tương ứng khi endpoint chạy.

Ở một flow:

~~~text
HTTP adapter / gateway
   → orders.input (DirectChannel)
   → orders.consumer (EventDrivenConsumer)
   → OrderService.process() (MessageHandler)
   → orders.out
~~~

**Channel** có nhiệm vụ chuyển message. **Endpoint** nối channel với handler và quản lý vòng đời. **Handler** thực hiện logic. Tạo một bean handler **không mặc nhiên** có nghĩa nó đã subscribe vào channel mong muốn; cần endpoint/DSL/annotation wiring đúng và đang chạy.

~~~mermaid
flowchart LR
    P["Producer"] --> C["orders.input<br/>DirectChannel"]
    E["EventDrivenConsumer<br/>STARTED"] --> H["Order handler"]
    C -- "dispatch nếu subscribed" --> E
    S["SmartLifecycle"] -. "start: subscribe" .-> E
    S -. "stop: unsubscribe" .-> E
    C -. "0 subscriber" .-> X["MessageDispatchingException"]
~~~

Sơ đồ minh họa endpoint event-driven. Nó **không** mô tả <code>QueueChannel</code>: queue không cần <code>MessageHandler</code> đăng ký trực tiếp, mà được polling consumer lấy message bằng <code>receive()</code>.

## 2. Bảng phân loại: kiểu channel quyết định dấu hiệu lỗi

| Channel | Cách consumer nhận message | Không có consumer/subscriber thì sao? | Kiểm tra đầu tiên |
|---|---|---|---|
| <code>DirectChannel</code> | <code>SubscribableChannel</code>; dispatch ngay trên thread sender | <code>UnicastingDispatcher</code> không có handler sẽ phát <code>MessageDispatchingException</code> | <code>getSubscriberCount()</code>, endpoint <code>isRunning()</code> |
| <code>ExecutorChannel</code> | Subscriber được gọi qua executor/worker | Không có handler là lỗi dispatch; có handler thì send có thể trả về trước khi worker xử lý xong | Subscriber count, executor queue/rejection, worker log |
| <code>PublishSubscribeChannel</code> | Phát tới tất cả subscriber | **Mặc định** <code>minSubscribers=0</code>; send có thể được coi là thành công dù không ai nhận. <code>requireSubscribers=true</code> làm không có subscriber thành lỗi | <code>getSubscriberCount()</code>, <code>requireSubscribers</code>, <code>minSubscribers</code> |
| <code>QueueChannel</code> | <code>PollableChannel.receive()</code>; thường do poller gọi | Không có subscriber là **bình thường**; message có thể nằm trong queue cho tới khi được lấy hoặc queue đầy | Queue size, poller lifecycle, <code>receiveTimeout</code> |
| <code>FluxMessageChannel</code> | Reactive Streams <code>Publisher</code> và demand của subscriber | Không phải <code>SubscribableChannel</code> hay <code>PollableChannel</code>; cần quan sát reactive subscription/backpressure, không kiểm bằng số subscriber kiểu imperative | Subscriber reactive, <code>request(n)</code>, completion/error |
| Global <code>errorChannel</code> | Thường là publish–subscribe channel phục vụ lỗi | Từ Spring Integration 5.4.3, error channel mặc định yêu cầu subscriber; lỗi thứ cấp có thể báo không có subscriber khi error flow không sẵn sàng | Xác định lỗi gốc và error channel nhận message |

Vì vậy, câu “channel này có **0 subscriber**” chỉ đủ kết luận **có vấn đề** khi kênh đó được thiết kế để dispatch trực tiếp tới handler cần thiết. Với <code>QueueChannel</code>, câu hỏi đúng là “poller đã nhận message chưa?”, không phải “ai đã subscribe?”.

### Hai cấu hình dễ nhầm nhất

<code>DirectChannel</code> là point-to-point, yêu cầu ít nhất một handler để dispatch. <code>PublishSubscribeChannel</code> là broadcast: theo mặc định từ Spring Integration 3.0, ngưỡng <code>minSubscribers</code> bằng 0 nên một send có thể hợp lệ dù hiện chưa có subscriber.

~~~java
PublishSubscribeChannel optionalEvents = new PublishSubscribeChannel();
// Không có subscriber vẫn có thể được coi là send thành công.

PublishSubscribeChannel mandatoryEvents =
    new PublishSubscribeChannel(true);
// Có requireSubscribers: không có subscriber thì báo lỗi dispatch.
~~~

<code>requireSubscribers</code> được hỗ trợ từ 5.4.3. Nếu nghiệp vụ bắt buộc phải có consumer, hãy cấu hình rõ ràng thay vì dựa vào việc publish–subscribe “có vẻ gửi được”.

## 3. Nhận diện stack trace: lỗi ở đâu và ở thời điểm nào?

Một lỗi điển hình có các dấu hiệu:

~~~text
org.springframework.integration.MessageDispatchingException:
Dispatcher has no subscribers for channel '...'
    at ...UnicastingDispatcher.dispatch(...)
    at ...AbstractSubscribableChannel.doSend(...)
    at ...AbstractMessageChannel.send(...)
~~~

Tên method/đoạn message cụ thể thay đổi theo phiên bản. <code>MessageDispatchingException</code> kế thừa <code>MessageDeliveryException</code> và phản ánh lỗi dispatch. Đừng lập trình dựa vào việc so khớp toàn bộ chuỗi exception; hãy dùng **loại exception, failed message/channel, cause và trạng thái runtime**.

Ba nhóm biểu hiện:

1. **Lỗi dispatch thực sự:** <code>MessageDispatchingException</code> được phát khi channel có cơ chế dispatch nhưng không có handler phù hợp, hoặc không thể dispatch theo điều kiện runtime.
2. **Send thành công nhưng không ai xử lý:** gặp ở publish–subscribe được phép 0 subscriber; hoặc queue đã nhận message nhưng không có poller nào lấy.
3. **Handler đã nhận nhưng không có reply:** có thể do handler one-way, router không khớp nhánh, downstream delay/async hoặc gateway timeout. Đây **không nhất thiết** là lỗi subscriber.

**Điểm kiểm tra cấp cứu:** Nếu log có chữ “no subscribers”, hãy xác định đó là lỗi của **business input channel**, của **channel downstream sau router**, hay của **errorChannel**. Một exception thứ hai do error channel không có subscriber có thể che khuất exception nghiệp vụ ban đầu.

## 4. Chiến lược khoanh vùng theo đường đi thực tế

Khi gặp lỗi, bắt đầu từ nơi message được gửi và đi theo **từng hop có tên**:

~~~mermaid
flowchart TD
    A["Lỗi / không có reply"] --> B{"Có tên channel và exception?"}
    B -->|Có| C["Xác định bean channel thực + type"]
    B -->|Không| D["Tìm từ producer, gateway, correlation ID"]
    D --> C
    C --> E{"SubscribableChannel?"}
    E -->|Có| F["Đọc subscriber count tại thời điểm điều tra"]
    E -->|Queue| Q["Đọc queue depth, poller/consumer running"]
    E -->|Reactive| R["Kiểm tra subscription, demand, onError"]
    F --> G{"count = 0?"}
    G -->|Có| H["Tìm endpoint/wiring/lifecycle"]
    G -->|Không| I["Tìm routing, handler failure, concurrency"]
    H --> J["Sửa đúng endpoint / start policy"]
    I --> J
    Q --> J
    R --> J
    J --> K["Test lại failure và recovery"]
~~~

Trình tự thao tác:

1. Thu thập **exception gốc**, thread, timestamp, channel name, message ID, correlation ID, tenant/flow ID đã che dữ liệu nhạy cảm.
2. Tìm **bean channel thực** từ <code>ApplicationContext</code>, không chỉ dựa vào tên trong mô tả tài liệu.
3. Xác định <code>DirectChannel</code>, <code>PublishSubscribeChannel</code>, <code>ExecutorChannel</code>, <code>QueueChannel</code> hay reactive channel.
4. Nếu là <code>SubscribableChannel</code>, đọc số subscriber **tại lúc chụp trạng thái**; nếu là queue, kiểm tra receiver/poller.
5. Với subscriber count bằng 0, kiểm tra endpoint được khai báo không, đã start chưa, wiring đúng channel chưa, bị stop/destroy lúc nào.
6. Với count lớn hơn 0, tiếp tục đọc lỗi handler, router, filter, advice, transaction và branch downstream.
7. Tái hiện tối thiểu bằng một test có ranh giới thread và assertion đúng loại channel.

Đừng cố giải quyết ngay bằng cách tăng <code>sendTimeout</code>: đây không phải giải pháp cho channel không có subscriber.

## 5. Đo subscriber count ngay trong runtime

Spring Integration có giao diện <code>SubscribableChannelManagement</code> với <code>getSubscriberCount()</code> cho các channel dispatch trực tiếp. Một số triển khai như <code>DirectChannel</code>, <code>ExecutorChannel</code> và <code>PublishSubscribeChannel</code> hỗ trợ API này.

~~~java
@Component
public class ChannelInspector {
    private final ApplicationContext applicationContext;

    public ChannelInspector(ApplicationContext applicationContext) {
        this.applicationContext = applicationContext;
    }

    public void inspect(String channelBeanName) {
        Object bean = applicationContext.getBean(channelBeanName);
        if (bean instanceof SubscribableChannelManagement managed) {
            System.out.printf(
                "channel=%s, type=%s, subscribers=%d%n",
                channelBeanName,
                bean.getClass().getSimpleName(),
                managed.getSubscriberCount());
        } else if (bean instanceof PollableChannel) {
            System.out.printf(
                "channel=%s is PollableChannel (không có subscriber trực tiếp)%n",
                channelBeanName);
        } else {
            System.out.printf(
                "channel=%s, type=%s: cần xem contract riêng%n",
                channelBeanName,
                bean.getClass().getName());
        }
    }
}
~~~

Các kiểu chính: <code>org.springframework.integration.support.management.SubscribableChannelManagement</code>, <code>org.springframework.messaging.PollableChannel</code>, <code>org.springframework.context.ApplicationContext</code>, <code>org.springframework.stereotype.Component</code>.

Ví dụ sử dụng:

~~~java
inspector.inspect("orders.input");
// channel=orders.input, type=DirectChannel, subscribers=1
~~~

**Chú ý:** Subscriber count là snapshot, không phải một khóa bảo đảm tình trạng không thay đổi. Thread khác có thể stop endpoint ngay sau khi bạn đọc <code>1</code>. Với dynamic flow hoặc rolling deployment, nên đo lặp có timestamp và đối chiếu các sự kiện lifecycle.

### Liệt kê tất cả subscribable managed channel

~~~java
Map<String, SubscribableChannelManagement> channels =
    applicationContext.getBeansOfType(SubscribableChannelManagement.class);

channels.forEach((name, channel) ->
    log.info("channel={}, subscribers={}",
        name, channel.getSubscriberCount()));
~~~

Đây là cách kiểm tra nhanh trong một application context; bean ở context khác, proxy hoặc graph dynamic có thể cần kiểm tra riêng. Không liệt kê mọi bean rồi dừng tại kết luận “không thấy subscriber” mà không xác định endpoint đang chạy ở **context/process nào**.

## 6. Đọc trạng thái endpoint thay vì chỉ xem channel

Một <code>EventDrivenConsumer</code> thường subscribe handler khi endpoint <code>start()</code> và unsubscribe khi <code>stop()</code>. Vì vậy nếu bean handler tồn tại nhưng channel không có subscriber, kiểm tra **endpoint lifecycle**:

~~~text
Channel "orders.input" tồn tại ✓
OrderService bean tồn tại      ✓
EventDrivenConsumer bean      ✓
isRunning()                   ✗
Subscriber count              0
~~~

Đây là trường hợp **wiring tồn tại nhưng endpoint không hoạt động**. Những nguyên nhân điển hình:

- <code>autoStartup=false</code> do cấu hình production hoặc test.
- Startup phase chưa đến hoặc một bean start lỗi.
- Endpoint từng được stop qua control plane/JMX/Control Bus hoặc code điều phối.
- Dynamic <code>IntegrationFlow</code> đã bị remove/destroy.
- Một conditional configuration/profile làm endpoint không được tạo.
- Test dùng <code>@SpringIntegrationTest(noAutoStartup=...)</code> và chưa start endpoint thủ công.

Với endpoint có ID ổn định, có thể tra cứu:

~~~java
SmartLifecycle consumer =
    applicationContext.getBean("orders.consumer", SmartLifecycle.class);

log.info("orders.consumer running={}, autoStartup={}",
    consumer.isRunning(), consumer.isAutoStartup());
~~~

<code>SmartLifecycle</code> thuộc <code>org.springframework.context</code>. Tên bean <code>orders.consumer</code> phải trùng **endpoint ID thực**, không phải tên class service. Nếu ứng dụng không đặt ID, đọc topology/bean registry để tìm endpoint tương ứng.

**Không bật start tự động ở production chỉ vì một endpoint đang stop.** Cần kiểm tra lý do stop: source đang bảo trì, tenant bị xóa, drain trước deploy hay khởi động có chủ đích bị trì hoãn.

## 7. Sửa wiring sai: bean channel, inputChannel và endpoint ID

### Trường hợp A — khai báo channel nhưng không có consumer

~~~java
@Configuration
@EnableIntegration
public class IncorrectConfig {
    @Bean(name = "orders.input")
    DirectChannel ordersInput() {
        return new DirectChannel();
    }

    // Không có endpoint nào đang subscribe "orders.input".
}
~~~

Khi gửi <code>Message</code> vào channel trên, channel không có handler để dispatch. Việc tên channel tồn tại trong Spring context chỉ chứng minh bean đã được tạo, **không** chứng minh có consumer đang nhận.

### Trường hợp B — handler được đăng ký vào kênh khác

~~~java
@Component
public class OrderConsumer {
    @ServiceActivator(inputChannel = "orders.inbound")
    public void process(OrderCommand command) {
        // ...
    }
}

// Producer lại gửi vào bean tên "orders.input".
~~~

Nếu <code>orders.inbound</code> là channel hợp lệ nhưng producer dùng <code>orders.input</code>, mỗi bên có thể chạy bình thường theo hướng riêng, khiến <code>orders.input</code> không có subscriber. Nếu channel không tồn tại, còn có thể gặp lỗi resolve bean/destination trước cả lúc send.

**Cách sửa:** Thống nhất tên channel theo hợp đồng, tốt nhất qua hằng số/typed wiring trong cùng module khi thích hợp; kiểm tra code producer, channel bean, annotation và router mapping. Đừng “sửa tạm” bằng cách tạo bean alias mà chưa xác nhận router/gateway lẽ ra phải gửi tới đâu.

### Trường hợp C — Java DSL tạo endpoint đúng tên

~~~java
public record OrderCommand(String orderId, int quantity) {}

@Service
public class OrderService {
    public void process(OrderCommand command) {
        if (command.quantity() <= 0) {
            throw new IllegalArgumentException("Quantity must be positive");
        }
        // xử lý nghiệp vụ; method one-way
    }
}

@Configuration
@EnableIntegration
public class OrdersFlowConfig {
    @Bean(name = "orders.input")
    DirectChannel ordersInput() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow ordersFlow(OrderService service) {
        return IntegrationFlow.from("orders.input")
            .handle(service, "process",
                endpoint -> endpoint.id("orders.consumer"))
            .get();
    }
}
~~~

Với endpoint start bình thường, <code>orders.input</code> sẽ có consumer. <code>orders.consumer</code> là tên endpoint cho quản lý/test, còn <code>OrderService</code> là bean nghiệp vụ. Handler <code>void</code> là terminal one-way: đừng dùng request–reply gateway rồi chờ nó tự tạo reply khi không có cấu hình reply tương ứng.

Ví dụ gửi và kiểm tra:

~~~java
DirectChannel input = context.getBean("orders.input", DirectChannel.class);
assertEquals(1, input.getSubscriberCount());
assertTrue(input.send(MessageBuilder
    .withPayload(new OrderCommand("O-42", 2))
    .setHeader("correlationId", "checkout-O-42")
    .build()));
~~~

Các import chính: <code>org.springframework.integration.dsl.IntegrationFlow</code>, <code>org.springframework.integration.config.EnableIntegration</code>, <code>org.springframework.integration.channel.DirectChannel</code>, <code>org.springframework.integration.support.MessageBuilder</code> và các annotation Spring Framework.

### Component scanning và @EnableIntegration

Nếu class có <code>@ServiceActivator</code> không nằm trong phạm vi component scan, nó sẽ không trở thành bean và endpoint không được tạo. Nếu một cấu hình Spring Integration bị vô hiệu hóa do <code>@Profile</code>, <code>@ConditionalOnProperty</code> hoặc bean initialization lỗi, subscriber cũng có thể vắng mặt.

Trong một dự án Spring Boot, autoconfiguration có thể khởi tạo nền tảng Spring Integration tùy dependency; trong Spring context thủ công có thể cần <code>@EnableIntegration</code>. Cần kiểm tra **đúng context thực tế**, không đoán framework đã quét package vì class có annotation.

## 8. Không nhìn thấy reply chưa chắc không có subscriber

Hai dòng thời gian sau có dấu hiệu từ bên ngoài giống nhau nhưng nguyên nhân khác:

~~~mermaid
sequenceDiagram
    participant S as Sender/Gateway
    participant C as DirectChannel
    participant H as Handler
    participant O as Output/Reply
    alt Channel không có subscriber
      S->>C: send(request)
      C--xS: MessageDispatchingException
    else Subscriber tồn tại nhưng handler one-way
      S->>C: send(request)
      C->>H: handle
      H-->>C: hoàn tất, không phát reply
      C-->>S: send thành công
      Note over S,O: Gateway có thể timeout vì không có reply
    end
~~~

Vì vậy khi gặp <code>MessageTimeoutException</code> hoặc gateway timeout:

1. Kiểm tra channel có subscriber hay không.
2. Kiểm tra handler có tạo reply hay chỉ nhận one-way.
3. Kiểm tra <code>replyChannel</code>, output channel và các filter/router.
4. Kiểm tra có chuyển qua <code>ExecutorChannel</code>/<code>QueueChannel</code> làm reply đến muộn không.
5. Kiểm tra downstream có ném lỗi hoặc error flow đã recover mà không trả reply không.

Không đổi một terminal handler <code>void</code> thành request–reply chỉ để làm test qua: phải quyết định rõ hợp đồng của flow.

## 9. QueueChannel không có subscriber: khoanh vùng theo poller

Với <code>QueueChannel</code>, việc có 0 subscriber không nói lên vấn đề. Message được đặt vào queue, sau đó một polling consumer dùng <code>receive()</code> để lấy.

~~~java
QueueChannel queue = new QueueChannel(2);
Message<String> message = MessageBuilder.withPayload("O-42").build();

assertTrue(queue.send(message));
assertEquals("O-42", queue.receive(0).getPayload());
~~~

Nếu queue tồn đọng:

| Dấu hiệu | Cần kiểm tra |
|---|---|
| Queue depth tăng liên tục | Poller không chạy, tốc độ xử lý thấp hơn tốc độ gửi, consumer lỗi |
| Poller <code>isRunning=false</code> | <code>autoStartup</code>, lỗi start, stop có chủ đích, phase |
| Poller running nhưng không receive | <code>receiveTimeout</code>, trigger, worker pool, message source, lock/transaction |
| Message bị lấy nhưng không hoàn tất | Handler downstream lỗi, transaction rollback/retry, blocking IO |
| Queue trống nhưng producer báo gửi thành công | Consumer đã nhận nhanh; cần metric/log tại consumer thay vì nhìn snapshot queue |
| Persistent queue tăng qua restart | <code>JdbcChannelMessageStore</code>, ACK/rollback, khả năng deserialize và schema |

Khi một flow dùng:

~~~text
orders.queue (QueueChannel) → PollingConsumer → OrderHandler
~~~

đừng “sửa” bằng cách subscribe <code>MessageHandler</code> trực tiếp vào <code>QueueChannel</code>: interface này không hỗ trợ <code>subscribe()</code>. Điều cần kiểm tra là **poller và endpoint đã được đăng ký, cấu hình và start chưa**.

## 10. PublishSubscribeChannel: một nguồn mất message âm thầm

<code>PublishSubscribeChannel</code> thường dùng cho notifications. Với cấu hình mặc định, nếu subscriber count bằng 0, <code>send()</code> vẫn có thể được đánh dấu thành công vì <code>minSubscribers=0</code>.

~~~java
PublishSubscribeChannel notifications = new PublishSubscribeChannel();
assertEquals(0, notifications.getSubscriberCount());
assertTrue(notifications.send(
    MessageBuilder.withPayload("event").build()));
// Không có handler nào nhận event, nhưng send được coi là thành công.
~~~

Khi thông báo là bắt buộc, có thể yêu cầu subscriber:

~~~java
PublishSubscribeChannel required = new PublishSubscribeChannel(true);

assertThrows(MessageDispatchingException.class, () ->
    required.send(MessageBuilder.withPayload("event").build()));
~~~

<code>MessageDispatchingException</code> thuộc <code>org.springframework.integration</code>. Còn <code>setMinSubscribers(n)</code> đặt ngưỡng tối thiểu để <code>send()</code> được coi là thành công theo channel. Khi có executor, sự thành công ở đây chỉ xác nhận số subscriber đủ điều kiện **tại dispatch**, không bảo đảm tất cả subscriber hoàn thành nghiệp vụ.

**Không dùng <code>requireSubscribers=false</code> như cách che lỗi** nếu thông báo là phần bắt buộc của một transaction hoặc phải giao tới audit consumer. Trong trường hợp event không được phép mất, cân nhắc transactional outbox/broker bền vững và contract redelivery/idempotency.

### Global errorChannel có quy tắc riêng

Global <code>errorChannel</code> mặc định của Spring Integration là publish–subscribe channel đặc biệt. Từ 5.4.3, nó được cấu hình <code>requireSubscribers=true</code> để tránh im lặng bỏ lỗi khi không ai đang nhận; thuộc tính <code>spring.integration.channels.error.requireSubscribers</code> có thể điều chỉnh hành vi này.

Nếu lỗi “no subscribers” xuất hiện ở <code>errorChannel</code>:

1. Tìm **exception gốc** ở worker/poller/adapter đã tạo <code>ErrorMessage</code>.
2. Kiểm tra error subscriber có được đăng ký và vẫn đang chạy hay đã bị stop/shutdown.
3. Kiểm tra <code>errorChannel</code> header của message có trỏ kênh riêng không, và kênh ấy có subscriber không.
4. Xem điều kiện ACK, retry và transaction của nguồn, vì lỗi phát <code>ErrorMessage</code> có thể ảnh hưởng quyết định nacking/redelivery.

Error flow **không phải** nơi nên đăng ký một handler <code>message -> {}</code> chỉ để triệt lỗi: nếu không lưu/quan sát được nguyên nhân, sự cố giao hàng có thể biến thành mất dấu vết.

## 11. ExecutorChannel: khi lỗi xảy ra ở thread khác

<code>ExecutorChannel</code> cũng dựa trên subscriber nhưng giao việc qua executor. Cần phân biệt hai trường hợp:

- **Không có subscriber lúc dispatch:** channel không có nơi nhận; lỗi có thể xuất hiện ngay khi producer gửi.
- **Có subscriber nhưng handler downstream lỗi:** producer có thể đã được trả kết quả send thành công; exception xuất hiện trong worker, được xử lý theo error handler/error flow được cấu hình.

~~~mermaid
sequenceDiagram
    participant P as Producer thread
    participant C as ExecutorChannel
    participant X as Executor worker
    participant H as Handler
    P->>C: send(message)
    alt no subscriber
       C--xP: lỗi dispatch
    else subscribed
       C->>X: submit task
       C-->>P: send accepted
       X->>H: handle message
       H--xX: exception
       Note over P,H: Lỗi sau handoff không nằm trên call stack của producer
    end
~~~

Đừng chỉ bắt exception quanh <code>send()</code> rồi kết luận tất cả message đều thành công. Cần xem subscriber count, executor active/queue/rejection, error handler và trạng thái worker. Việc tăng thread pool không sửa được một channel **không có handler**.

Trong <code>DirectChannel</code>, handler chạy trên thread sender nên có thể tham gia transaction thread-bound đang mở. Qua <code>ExecutorChannel</code>, transaction của sender không tự truyền sang worker. Vì vậy thay channel để “né” lỗi dispatch có thể vô tình đổi ranh giới transaction, thứ tự và cơ chế retry.

## 12. Dynamic IntegrationFlow: subscriber biến mất sau stop/remove

Một flow động có thể được đăng ký bằng <code>IntegrationFlowContext</code> rồi stop hoặc destroy:

~~~java
var registration = flowContext.getRegistrationById("tenant.flow.T42");

if (registration != null) {
    log.info("Flow vẫn có registration, id={}", registration.getId());
    // Xem isRunning() trên endpoint SmartLifecycle của flow tương ứng.
    // Thao tác stop/destroy chỉ thực hiện theo quy trình vận hành.
}
~~~

<code>IntegrationFlowRegistration</code> cung cấp <code>getId()</code>, <code>start()</code>, <code>stop()</code> và <code>destroy()</code>; **không có method <code>isRunning()</code> riêng trên interface này**. Để biết thành phần có đang chạy hay không, truy xuất <code>SmartLifecycle</code> của endpoint phù hợp hoặc graph/lifecycle state tương ứng.

<code>registration.stop()</code> có thể khiến endpoint event-driven unsubscribe khỏi input channel; <code>registration.destroy()</code> hoặc <code>flowContext.remove(id)</code> gỡ registration và bean phụ thuộc được quản lý. Channel dùng chung có thể **vẫn tồn tại** dù subscriber thuộc flow vừa bị xóa.

Một race thường xảy ra:

~~~text
Thread A: kiểm tra tenant flow đang ACTIVE
Thread B: stop/destroy registration
Thread A: gửi vào shared DirectChannel
→ MessageDispatchingException: không còn subscriber
~~~

**Cách xử lý đúng:** admission gate chặn message mới trước khi stop, drain công việc đang chạy, rồi mới gỡ flow. Dùng trạng thái tenant/generation bền vững nếu nhiều pod có thể provision/delete cùng flow. Không tự động start lại một flow của tenant đã DELETING chỉ vì monitor thấy subscriber count bằng 0.

Sau khi thêm/gỡ flow động, graph topology có thể được cache. Nếu dùng <code>IntegrationGraphServer</code>, gọi <code>rebuild()</code> theo nhu cầu để nhìn snapshot mới, không dựa vào graph cũ rồi kết luận handler vẫn đang subscribe.

## 13. Dùng IntegrationGraphServer để kiểm tra wiring

<code>IntegrationGraphServer</code> xuất runtime graph gồm channel, handler, endpoint và những liên kết tìm được. Nó giúp trả lời:

- Producer đang gửi tới **channel node** nào?
- Channel có một endpoint input tương ứng không?
- Endpoint có đang nối đến handler nào, hoặc chỉ có một node nằm cô lập?
- Sau router/splitter, đường đi có nhánh nào kết thúc ở channel không có consumer?
- Topology hiện tại khác gì trước lần dynamic registration/deployment?

~~~java
IntegrationGraphServer graphServer =
    applicationContext.getBean(IntegrationGraphServer.class);

Graph snapshot = graphServer.rebuild();
log.debug("Integration topology: {}", snapshot);
~~~

Các kiểu thuộc <code>org.springframework.integration.graph</code>. Đoạn code giả định đã khai báo bean <code>IntegrationGraphServer</code> (hoặc ứng dụng quản trị đã tạo nó). <code>rebuild()</code> có ý nghĩa khi thành phần đã được thêm/gỡ; <code>getGraph()</code> trả snapshot graph hiện có.

**Đừng coi graph là bằng chứng cuối cùng của một lần giao message.** Nó mô tả topology trong lúc xây dựng snapshot, trong khi trạng thái <code>SmartLifecycle</code> và subscriber count có thể thay đổi ngay sau đó. Kết hợp graph, log start/stop và một test send có kiểm soát.

### Những chỗ dễ mất liên kết

| Vị trí | Dấu hiệu | Kiểm tra |
|---|---|---|
| Producer output channel | Log send đến tên không như dự kiến | Endpoint <code>outputChannel</code>, header <code>replyChannel</code> |
| Router mapping | Chỉ một loại message lỗi, loại khác chạy | Router mapping, channel key, <code>defaultOutputChannel</code> |
| Splitter / aggregator | Một fragment lỗi hoặc nhóm không bao giờ release | Correlation, sequence, group store, discard/expire flow |
| Filter | Không có output nhưng không có exception | Filter discard policy, throwExceptionOnRejection |
| Service activator | Handler được tạo nhưng không thấy subscribe | Endpoint inputChannel, <code>isRunning()</code>, ID/bean |
| Outbound gateway | Request đi nhưng không có reply | Gateway reply timeout, remote I/O, consumer response |
| Error flow | Lỗi gốc xuất hiện rồi lỗi “no subscribers” thứ hai | Error channel bean, header, subscriber lifecycle |

## 14. Dùng log và observation mà không làm thay đổi hành vi

Với sự cố khó tái hiện, có thể tăng DEBUG log **có phạm vi** cho những package phù hợp:

~~~properties
logging.level.org.springframework.integration.channel=DEBUG
logging.level.org.springframework.integration.dispatcher=DEBUG
logging.level.org.springframework.integration.endpoint=DEBUG
~~~

Tên logger và mức độ chi tiết phụ thuộc phiên bản/loại channel. Không bật TRACE toàn bộ Spring Integration lâu dài ở production nếu message chứa payload lớn hoặc dữ liệu nhạy cảm.

Nên log ít nhất:

~~~text
timestamp
channelBeanName, channelType, subscriberCount (nếu áp dụng)
endpointId, isRunning, flowId
messageId, correlationId, businessEventId
threadName, exceptionType, failedMessageId
~~~

<code>MessageHeaders.ID</code> định danh **message cụ thể**; <code>correlationId</code> nối các bước/batch; business event ID giúp idempotency. Khi một transformer tạo message mới hoặc một nguồn redeliver, message ID có thể đổi. Không gắn raw ID có cardinality rất cao làm tag Micrometer cho mọi message.

### Thận trọng với wiretap và logging adapter

Một <code>WireTap</code> là channel interceptor sao chép/quan sát message sang một channel phụ. Nó **không tự biến một <code>DirectChannel</code> có 0 subscriber thành channel có business consumer**. Bạn có thể thấy log “message đã vào channel” do wiretap, trong khi dispatch chính vẫn thất bại.

Nếu thật sự muốn **kết thúc flow một chiều** và chủ động bỏ output, dùng đích như <code>nullChannel</code> hoặc terminal handler theo hợp đồng. Đây là quyết định thiết kế có chủ đích, không phải cách chữa no-subscriber cho một luồng bắt buộc giao message.

## 15. Bài thực hành: tái hiện rồi sửa no-subscriber bằng JUnit 5

### 15.1. DirectChannel không có subscriber phải fail

~~~java
@Test
void directChannelWithoutSubscriberFails() {
    DirectChannel channel = new DirectChannel();
    Message<String> request =
        MessageBuilder.withPayload("order-42").build();

    assertEquals(0, channel.getSubscriberCount());
    assertThrows(MessageDispatchingException.class,
        () -> channel.send(request));
}
~~~

Đoạn test này kiểm tra lỗi do thiếu subscriber; không dựa vào chuỗi exception nguyên văn.

### 15.2. Subscribe và unsubscribe làm trạng thái thay đổi

~~~java
@Test
void directChannelWorksOnlyWhileHandlerIsSubscribed() {
    DirectChannel channel = new DirectChannel();
    AtomicInteger calls = new AtomicInteger();

    MessageHandler handler = message -> calls.incrementAndGet();
    assertTrue(channel.subscribe(handler));
    assertEquals(1, channel.getSubscriberCount());

    Message<String> request =
        MessageBuilder.withPayload("order-42").build();
    assertTrue(channel.send(request));
    assertEquals(1, calls.get());

    assertTrue(channel.unsubscribe(handler));
    assertEquals(0, channel.getSubscriberCount());
    assertThrows(MessageDispatchingException.class,
        () -> channel.send(request));
}
~~~

Các kiểu: <code>org.springframework.integration.channel.DirectChannel</code>, <code>org.springframework.messaging.MessageHandler</code>, <code>org.springframework.integration.MessageDispatchingException</code>, <code>java.util.concurrent.atomic.AtomicInteger</code>, <code>org.springframework.integration.support.MessageBuilder</code> và assertions JUnit Jupiter.

Trong ứng dụng Spring Integration thật, **không nên dùng subscribe thủ công để vá một endpoint framework đã quản lý**. Nếu endpoint bị stop, hãy sửa lifecycle/wiring của endpoint và để framework subscribe/unsubscribe theo vòng đời.

### 15.3. PublishSubscribeChannel: kiểm chứng hai chính sách

~~~java
@Test
void publisherMayAllowZeroSubscribersUnlessRequired() {
    Message<String> message =
        MessageBuilder.withPayload("event").build();

    PublishSubscribeChannel optional = new PublishSubscribeChannel();
    assertEquals(0, optional.getSubscriberCount());
    assertTrue(optional.send(message));

    PublishSubscribeChannel required = new PublishSubscribeChannel(true);
    assertEquals(0, required.getSubscriberCount());
    assertThrows(MessageDispatchingException.class,
        () -> required.send(message));
}
~~~

Test trên là lời nhắc rằng **không có exception chưa chắc là có consumer**. Nếu dùng publish–subscribe cho audit/notifications quan trọng, policy bắt buộc subscriber phải được thể hiện trong cấu hình và test.

### 15.4. QueueChannel: đúng tiêu chí là poller/receive

~~~java
@Test
void queueChannelAcceptsWithoutDirectSubscriber() {
    QueueChannel channel = new QueueChannel(1);
    Message<String> message =
        MessageBuilder.withPayload("queued").build();

    assertTrue(channel.send(message));
    assertEquals("queued", channel.receive(0).getPayload());
    assertNull(channel.receive(0));
}
~~~

Test này không chứng minh một polling consumer đang chạy; nó chỉ xác nhận queue lưu và trả message. Để chứng minh consumer, cần test endpoint với trigger/poller thực hoặc kiểm soát bằng mock source và chờ completion.

## 16. Integration test: endpoint autoStartup=false làm subscriber biến mất

Một ca rất thực tế là test có đủ bean channel/handler nhưng endpoint không start do cấu hình. Có thể tạo một Spring context nhỏ dùng <code>OrdersFlowConfig</code> ở mục 7:

~~~java
@SpringJUnitConfig(OrdersFlowConfig.class)
@SpringIntegrationTest(noAutoStartup = "orders.consumer")
class SubscriberLifecycleTest {

    @Autowired
    @Qualifier("orders.input")
    DirectChannel input;

    @Autowired
    @Qualifier("orders.consumer")
    SmartLifecycle endpoint;

    @Test
    void endpointStartChangesSubscriberCount() {
        assertFalse(endpoint.isRunning());
        assertEquals(0, input.getSubscriberCount());

        Message<OrderCommand> request = MessageBuilder
            .withPayload(new OrderCommand("O-42", 2))
            .build();

        assertThrows(MessageDispatchingException.class,
            () -> input.send(request));

        endpoint.start();
        try {
            assertTrue(endpoint.isRunning());
            assertEquals(1, input.getSubscriberCount());
            assertTrue(input.send(request));
        } finally {
            endpoint.stop();
        }

        assertEquals(0, input.getSubscriberCount());
    }
}
~~~

<code>@SpringJUnitConfig</code> thuộc <code>org.springframework.test.context.junit.jupiter</code>; <code>@SpringIntegrationTest</code> thuộc <code>org.springframework.integration.test.context</code>. Mã minh họa test lifecycle; nếu chạy trong một suite dùng Spring TestContext cache, cần phục hồi trạng thái endpoint theo yêu cầu fixture sau test. Không đặt <code>@Transactional</code> lên test với mục tiêu suy luận trực tiếp transaction của handler.

### Những gì test này thực sự chứng minh

- Bean channel và bean handler **đều có thể tồn tại** khi endpoint đang stop.
- Với event-driven <code>DirectChannel</code>, endpoint start giúp xuất hiện subscriber.
- Stop có thể đưa subscriber count về 0, và send tiếp theo có thể thất bại.
- Test chưa chứng minh broker redelivery, queue persistence hay luồng xử lý sau executor handoff.

## 17. Khi count lớn hơn 0 nhưng vẫn thấy lỗi dispatch

Subscriber count là điều kiện cần đối với kênh dispatch, không phải cam kết mọi message đều được xử lý thành công.

| Triệu chứng | Điều có thể đang xảy ra |
|---|---|
| <code>getSubscriberCount()=1</code> nhưng log lỗi lúc trước | Endpoint vừa start sau sự cố; snapshot không cùng thời điểm |
| Lỗi báo channel B, kiểm tra channel A thấy có subscriber | Router/transformer đã chuyển sang **channel khác** |
| Có nhiều subscriber nhưng handler A luôn lỗi | Dispatcher thử handler theo failover/load-balancing; cần đọc chuỗi exception |
| <code>ExecutorChannel</code> có subscriber, không có output | Worker chưa chạy, executor quá tải, handler lỗi sau handoff |
| <code>PublishSubscribeChannel</code> có subscriber, send trả success | Với executor, success không có nghĩa subscriber đã hoàn tất |
| Subscriber tồn tại nhưng gateway timeout | Handler không phát reply hoặc reply gửi sai channel |
| Consumer nhận nhưng business DB không đổi | Transaction rollback, validation/filter loại message, retry chưa thành công |

Đối với <code>UnicastingDispatcher</code>, có thể có <code>AggregateMessageDeliveryException</code> nếu tất cả handler được thử đều ném exception; đó là câu chuyện **handler có nhưng không xử lý được**, khác với trường hợp dispatcher không có handler. Tách bạch exception type và nested cause để không sửa sai topology.

## 18. Transaction, retry và hậu quả giao hàng

No-subscriber có thể xảy ra **trước** khi một handler nào đó chạy. Khi đó retry ở **handler advice** có thể không kích hoạt vì không có handler được gọi. Muốn retry một lần gửi tới channel chưa sẵn sàng, cần cơ chế retry ở **sender/message source**, queue bền vững hoặc chiến lược chờ endpoint được start, theo yêu cầu nghiệp vụ.

| Đường xử lý | Lỗi no-subscriber đi đâu? | Hệ quả cần test |
|---|---|---|
| <code>DirectChannel</code> từ gateway/service đồng bộ | Exception có thể truyền ngược sender | Transaction phía sender có thể rollback nếu exception không bị nuốt |
| Poller gửi vào <code>DirectChannel</code> | Exception xuất hiện ở polling task | Error handler và rollback/redelivery của message source |
| Kafka/JMS inbound adapter gửi vào channel | Exception có thể đến callback/container | ACK, NACK, retry/redelivery theo adapter config |
| <code>ExecutorChannel</code> có subscriber rồi handler lỗi | Worker thread/error handler | Sender không nhất thiết nhìn thấy lỗi đó |
| <code>PublishSubscribeChannel</code> mặc định không subscriber | Có thể không ném lỗi | Nguy cơ mất sự kiện âm thầm; không có gì để retry nếu sender coi thành công |
| <code>QueueChannel</code> không poller | Enqueue có thể thành công; không có handler chạy | Backlog, memory/storage, năng lực khôi phục sau restart |

**Không khẳng định rằng “no subscribers sẽ luôn redeliver”**: message source/adapter, transaction manager, ACK mode và error recovery quyết định điều đó. Nếu error flow nuốt exception rồi trả success, upstream có thể coi message đã được xử lý dù handler nghiệp vụ chưa hề chạy.

Trong hệ thống cần tránh mất dữ liệu, các lựa chọn đáng cân nhắc gồm:

- chỉ bật producer khi consumer sẵn sàng và có health/admission gate phù hợp;
- đặt hàng đợi bền vững giữa producer và consumer khi có nhu cầu chịu downtime;
- áp dụng retry/backoff có giới hạn ở boundary có thể tái gửi message;
- dùng idempotency key nghiệp vụ, vì retry/redelivery có thể tạo duplicate;
- giữ trace/correlation và failed message trong DLQ/quarantine theo chính sách.

## 19. Case study: ba tình huống giống nhau ở giao diện người dùng

### Case A — vừa deploy xong đã thấy “Dispatcher has no subscribers”

**Tín hiệu:** Producer gửi tới <code>orders.input</code>, exception xuất hiện tức thì trên thread request. <code>getSubscriberCount()</code> trả 0. Bean <code>orders.consumer</code> tồn tại nhưng <code>isRunning=false</code>.

**Khoanh vùng:** Điểm lỗi nằm ở lifecycle endpoint, không phải repository hay business validation. Xem <code>autoStartup</code>, startup phase, config test bị lẫn vào runtime hoặc một lệnh stop trước đó.

**Sửa:** Khởi động endpoint theo quy trình vận hành hợp lệ, bổ sung health/admission gate, rồi test lúc start/stop. Không tăng gateway timeout.

### Case B — gửi notification “thành công” nhưng không có audit

**Tín hiệu:** <code>PublishSubscribeChannel.send()</code> trả <code>true</code>, không có exception. Subscriber count bằng 0 vì audit consumer không được quét vào context.

**Khoanh vùng:** Chính sách publish–subscribe mặc định cho phép không có subscriber; kết quả send không chứng minh audit đã nhận.

**Sửa:** Khôi phục wiring; nếu audit là bắt buộc, chọn <code>requireSubscribers=true</code> và phương án giao sự kiện đáng tin cậy hơn (outbox/broker), có test kiểm chứng output.

### Case C — message “biến mất” khi traffic tăng

**Tín hiệu:** <code>QueueChannel.send()</code> vẫn thành công, business handler không chạy; queue depth tăng.

**Khoanh vùng:** Không phải lỗi thiếu subscriber trên channel. Poller có thể stop hoặc bị nghẽn bởi downstream/database/executor. Kiểm tra <code>isRunning()</code>, lịch poll, throughput, thread dump, receive/ACK.

**Sửa:** Khôi phục poller/capacity và xác định backlog policy, không subscribe handler trực tiếp vào <code>QueueChannel</code>.

## 20. Runbook ngắn cho môi trường production

| Thứ tự | Câu hỏi xác minh | Bằng chứng |
|---|---|---|
| 1 | Lỗi phát sinh tại channel nào? | Exception, failed message, stack trace, correlation ID |
| 2 | Kiểu channel là gì? | Bean type trong Spring context |
| 3 | Có yêu cầu subscriber ngay không? | Direct/Executor/PubSub policy hay Queue/Flux semantics |
| 4 | Count/lifecycle tại thời điểm xảy ra lỗi? | Subscriber count, endpoint ID, isRunning, start/stop log |
| 5 | Wiring có đúng tên và context? | Input/output channel, router branch, endpoint graph |
| 6 | Có dynamic flow, deploy hoặc shutdown đang diễn ra không? | Registration lifecycle, graph rebuilt, app status |
| 7 | Lỗi đồng bộ hay xảy ra ở worker/poller? | Thread, executor metrics, error channel |
| 8 | Message đã ACK, commit, lưu queue hoặc retry chưa? | Adapter/source, transaction log, store và DLQ |
| 9 | Sau sửa đã có test tái hiện đúng failure không? | JUnit/integration test cho no-subscriber, startup, recovery |

Nên thêm cảnh báo khi **subscriber count bằng 0 đối với channel bắt buộc có consumer**, nhưng chỉ khi endpoint được kỳ vọng ở trạng thái RUNNING. Không phát cảnh báo vô ích cho những channel được phép không có subscriber, hoặc những channel queue/pollable không có khái niệm subscriber.

### Checklist trước khi kết luận đã khắc phục

- [ ] Đã phân biệt <code>MessageDispatchingException</code> với gateway timeout, queue backlog và handler exception.
- [ ] Đã xác định đúng bean channel và kiểu <code>Direct</code>/<code>Executor</code>/<code>PublishSubscribe</code>/<code>Queue</code>/<code>Flux</code>.
- [ ] Với <code>SubscribableChannel</code>, đã kiểm tra <code>getSubscriberCount()</code> và trạng thái endpoint cùng thời điểm.
- [ ] Đã xác minh <code>@ServiceActivator</code>, Java DSL hoặc adapter wiring đúng <code>inputChannel</code>.
- [ ] Đã kiểm tra <code>autoStartup</code>, profile/component scan và dynamic flow stop/remove.
- [ ] Với publish–subscribe bắt buộc nhận event, đã xét <code>requireSubscribers</code> và reliability contract.
- [ ] Với queue, đã đo poller running, message backlog, receive/ACK/rollback thay vì tìm subscriber.
- [ ] Với async, đã quan sát lỗi ở worker/error channel thay vì chỉ bắt exception quanh <code>send()</code>.
- [ ] Đã đánh giá retry, transaction, DLQ và idempotency để không làm mất/trùng message khi khôi phục.
- [ ] Đã có test cho cả nhánh thành công, không subscriber và restart/stop trong phạm vi ứng dụng cần hỗ trợ.

**Kết luận:** “Channel không có subscriber” không phải một chẩn đoán chung cho mọi chỗ không có output. Với <code>DirectChannel</code>, thiếu subscriber thường là lỗi dispatch rõ ràng; với <code>PublishSubscribeChannel</code>, message có thể được chấp nhận dù chưa ai nhận; với <code>QueueChannel</code>, việc chưa có người poll là vấn đề backlog, không phải lỗi subscription. Khi đi theo **kiểu channel → subscriber count → endpoint lifecycle → wiring/topology → ranh giới lỗi và transaction**, ta có thể tìm đúng điểm đứt của message flow và khôi phục an toàn.

## Tài liệu tham khảo

- [Spring Integration Reference — Message Channel Implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html)
- [Spring Integration Reference — Configuring Message Channels](https://docs.spring.io/spring-integration/reference/channel/configuration.html)
- [Spring Integration Reference — Message Endpoints](https://docs.spring.io/spring-integration/reference/endpoint.html)
- [Spring Integration Javadoc — SubscribableChannelManagement](https://docs.spring.io/spring-integration/docs/6.3.5/api/org/springframework/integration/support/management/SubscribableChannelManagement.html)
- [Spring Integration Javadoc — MessageDispatchingException](https://docs.spring.io/spring-integration/docs/6.4.x/api/org/springframework/integration/MessageDispatchingException.html)
- [Spring Integration Reference — Integration Graph](https://docs.spring.io/spring-integration/reference/graph.html)
- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html)
