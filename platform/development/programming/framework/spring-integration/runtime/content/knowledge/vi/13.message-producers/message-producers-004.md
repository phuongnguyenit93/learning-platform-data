# Output channel không có subscriber

Trong Spring Integration, một output channel chỉ chuyển message tiếp khi có consumer phù hợp với loại channel đó. Với `SubscribableChannel` như `DirectChannel` hoặc `ExecutorChannel`, dispatcher cần có ít nhất một subscriber để chuyển message. Nếu không có subscriber, thao tác gửi thường thất bại ngay tại send path. Đây là lỗi topology hoặc lifecycle cần được điều tra ở channel và endpoint.

Tuy nhiên, “không có subscriber” không phải tình huống giống nhau ở mọi loại channel. `QueueChannel` và `RendezvousChannel` là `PollableChannel`: consumer lấy message bằng `receive()` hoặc poller, không đăng ký subscriber theo cơ chế của `DirectChannel`. Vì vậy, trước khi xử lý lỗi, cần xác định output channel là loại nào và message đang được chuyển giao theo semantics nào.

## 1. Subscriber là gì trong Spring Integration?

Subscriber là thành phần đăng ký nhận message trên một `SubscribableChannel`. Các endpoint như service activator, transformer, filter hoặc router có thể subscribe vào input channel khi endpoint được khởi tạo và start.

Với một `DirectChannel`, đường đi cơ bản là:

~~~mermaid
flowchart LR
    P[Producer / upstream endpoint] --> C[DirectChannel]
    C --> D[UnicastingDispatcher]
    D --> S[Subscriber endpoint]
    S --> H[Message handler]
~~~

Dispatcher chuyển message tới subscriber. Nếu danh sách subscriber rỗng, dispatcher không có nơi để gửi message. Với unicast channel như `DirectChannel` và `ExecutorChannel`, trường hợp này thường phát sinh lỗi dispatch, ví dụ `MessageDispatchingException` với thông báo dispatcher không có subscriber. Exception có thể được bọc trong exception delivery của tầng gọi.

`DirectChannel` chỉ chọn một subscriber cho mỗi message. Nếu có nhiều subscriber, dispatcher phân phối theo load-balancing strategy; mặc định thường là round robin. Do đó, “có subscriber” không đồng nghĩa mọi subscriber đều nhận cùng một message.

## 2. Phân biệt SubscribableChannel và PollableChannel

Đây là bước đầu tiên khi chẩn đoán output channel.

| Loại channel | Cách consumer nhận message | Khi chưa có consumer |
|---|---|---|
| `DirectChannel` | Subscriber được dispatcher gọi trực tiếp trên thread gửi | Send không có subscriber thường thất bại |
| `ExecutorChannel` | Subscriber được dispatcher giao việc qua executor | Vẫn cần subscriber; executor không thay thế consumer |
| `PublishSubscribeChannel` | Broadcast tới các subscriber | Mặc định `requireSubscribers=false` và `minSubscribers=0`, nên send có thể thành công dù không có subscriber; có thể yêu cầu subscriber bằng cấu hình riêng |
| `QueueChannel` | Poller/consumer gọi `receive()` để lấy message | Message có thể nằm trong queue cho tới khi consumer nhận; capacity và send timeout quyết định kết quả gửi |
| `RendezvousChannel` | Consumer gọi `receive()` để handoff trực tiếp | Producer phải chờ receiver hoặc hết send timeout |

`SubscribableChannel` dùng đăng ký subscriber. `PollableChannel` dùng thao tác nhận message. Một `PollingConsumer` không subscribe vào `QueueChannel` như service activator trên `DirectChannel`; nó được cấu hình để poll channel và gọi `receive()`.

Vì thế, đừng dùng subscriber count để kết luận `QueueChannel` không có consumer. Với pollable channel, hãy kiểm tra polling endpoint, trạng thái endpoint và backlog.

## 3. Triệu chứng và exception thường gặp

Với output channel là `DirectChannel` hoặc `ExecutorChannel`, lỗi có thể xuất hiện khi producer gọi `send()` hoặc khi endpoint trước đó chuyển message sang output channel.

Một số biểu hiện thường thấy:

- Log báo `Dispatcher has no subscribers`.
- `MessageDispatchingException` hoặc `MessageDeliveryException` xuất hiện trong send path.
- Message không đến handler phía sau dù endpoint upstream đã chạy.
- Flow hoạt động trong một số thời điểm nhưng lỗi khi consumer bị stop, chưa start hoặc chưa đăng ký.

Ví dụ một channel không có endpoint nhận:

~~~java
@Bean
DirectChannel ordersOutput() {
    return new DirectChannel();
}

// Producer gửi vào ordersOutput(), nhưng không có endpoint nào subscribe.
~~~

Nếu producer gửi message vào channel này trước khi một endpoint được đăng ký, dispatcher không thể chuyển message. Với `DirectChannel`, channel không lưu message để chờ subscriber xuất hiện sau đó.

Không nên chỉ bắt exception rồi bỏ qua. Nếu lỗi bị nuốt, upstream có thể tưởng message đã được chuyển tiếp trong khi flow đã dừng tại output channel.

## 4. Nguyên nhân phổ biến

### Không có endpoint khai báo trên input channel

Producer gửi tới một channel nhưng không có service activator, transformer, filter, router hoặc flow nào sử dụng channel đó làm input. Kiểm tra tên channel ở nơi gửi và nơi khai báo consumer.

### Tên channel không khớp

Ví dụ producer gửi tới `orders.output`, trong khi endpoint lại nghe `orders.out`. Đây là hai channel khác nhau. Nếu channel được tạo tự động hoặc được tham chiếu qua string, lỗi chính tả có thể khó nhận ra khi đọc flow.

Ưu tiên khai báo channel thành bean có tên rõ ràng và inject cùng bean vào producer lẫn flow. Với cấu hình string-based, kiểm tra chính xác bean name và channel resolution.

### Endpoint chưa start hoặc đã stop

Endpoint thường đăng ký làm subscriber trong quá trình khởi tạo và start. Nếu endpoint có `autoStartup(false)`, bị stop trong maintenance hoặc lifecycle chưa chạy, subscriber có thể chưa sẵn sàng.

Kiểm tra trạng thái endpoint bằng `isRunning()` và log lifecycle. `autoStartup(false)` chỉ ngăn tự động start theo context; ứng dụng phải gọi `start()` khi điều kiện sẵn sàng.

### Flow chưa được đăng ký hoặc đã bị gỡ

Với flow khai báo bằng `@Bean`, endpoint được tạo trong quá trình khởi tạo ApplicationContext. Với flow động, `IntegrationFlowContext` phải đăng ký flow trước khi producer gửi message. Nếu flow bị `remove(flowId)` hoặc registration bị stop, endpoint không còn hoạt động như trước.

Nếu producer có thể chạy ngay khi ứng dụng khởi động, hãy điều phối thứ tự readiness: tạo và start consumer trước khi mở nguồn phát message. Không dựa vào timing ngẫu nhiên giữa startup của producer và consumer.

### Consumer dùng sai loại channel

`QueueChannel` cần polling consumer; `DirectChannel` cần subscriber endpoint. Nếu thiết kế consumer không phù hợp với loại channel, message có thể không được nhận dù bean handler đã tồn tại.

### Router gửi sang channel khác

Output channel mà producer nhìn thấy có thể không phải channel cuối cùng mà router chọn. Kiểm tra route key, header, default output channel và tên channel thực tế được chọn.

### Subscriber bị gỡ do lifecycle hoặc cấu hình động

Flow theo tenant/partner có thể được stop hoặc unregister khi cấu hình thay đổi. Nếu producer vẫn gửi tới channel của flow đó, subscriber count có thể về 0. Cần đồng bộ việc ngừng producer với việc gỡ flow.

## 5. Khai báo consumer đúng channel

Ví dụ dùng một `DirectChannel` được chia sẻ rõ ràng giữa producer và consumer:

~~~java
@Configuration
@EnableIntegration
public class OrderFlowConfiguration {

    @Bean
    DirectChannel ordersOutput() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow ordersConsumerFlow(DirectChannel ordersOutput,
                                       OrderService orderService) {
        return IntegrationFlow.from(ordersOutput)
                .handle(orderService, "process")
                .get();
    }
}
~~~

Flow này tạo endpoint tiêu thụ `ordersOutput` và đăng ký endpoint làm subscriber trong lifecycle của IntegrationFlow. Producer inject cùng bean `ordersOutput` để gửi message.

Có thể dùng annotation-based endpoint:

~~~java
@Component
public class OrderHandler {

    private final OrderService orderService;

    public OrderHandler(OrderService orderService) {
        this.orderService = orderService;
    }

    @ServiceActivator(inputChannel = "ordersOutput")
    public void handle(Order order) {
        orderService.process(order);
    }
}
~~~

Trong ví dụ annotation, bảo đảm channel bean tên `ordersOutput` tồn tại và cấu hình annotation-driven integration được bật. Không khai báo hai consumer ngoài ý muốn trên cùng một `DirectChannel` nếu không muốn load balancing giữa chúng.

## 6. Kiểm tra subscriber count và trạng thái runtime

Với `AbstractSubscribableChannel`, có thể kiểm tra số subscriber hiện tại:

~~~java
@Component
public class ChannelDiagnostics {

    private final AbstractSubscribableChannel ordersOutput;

    public ChannelDiagnostics(
            @Qualifier("ordersOutput") AbstractSubscribableChannel ordersOutput) {
        this.ordersOutput = ordersOutput;
    }

    public int subscriberCount() {
        return ordersOutput.getSubscriberCount();
    }
}
~~~

Nếu kết quả là `0` trên `DirectChannel`, hiện không có endpoint nào đăng ký nhận message. Nếu lớn hơn `0`, điều đó chỉ xác nhận có subscriber; chưa chứng minh handler xử lý thành công hoặc dependency phía sau đang healthy.

Với `QueueChannel`, không dùng `getSubscriberCount()` làm chỉ báo consumer. Kiểm tra polling endpoint có running không, poller có thực sự chạy không, queue depth và tuổi message cũ nhất.

Khi cần quan sát toàn bộ topology, có thể dùng Integration Graph/Actuator integration graph nếu ứng dụng đã bật và expose endpoint tương ứng. Đối chiếu tên channel, endpoint và trạng thái runtime với log có message ID/Correlation ID.

## 7. Chẩn đoán theo loại channel

### DirectChannel

1. Xác minh producer và consumer dùng đúng cùng một bean channel.
2. Kiểm tra `getSubscriberCount()`.
3. Xác minh endpoint đã được tạo và start.
4. Kiểm tra exception trong dispatcher/handler.
5. Nếu có nhiều subscriber, xác nhận load balancing có chủ đích.

Không có subscriber thường là lỗi ngay tại send path. `DirectChannel` không có buffer để giữ message chờ endpoint xuất hiện.

### ExecutorChannel

1. Kiểm tra subscriber endpoint trước tiên; executor không tự tạo subscriber.
2. Kiểm tra executor pool, queue capacity và rejected task.
3. Xác định message đã được dispatch hay task bị từ chối.
4. Tìm log ở worker thread bằng message ID/Correlation ID.

Nếu subscriber tồn tại nhưng worker không xử lý, vấn đề có thể ở executor saturation hoặc task rejection, không phải subscriber count.

### PublishSubscribeChannel

`PublishSubscribeChannel` broadcast tới các subscriber. Mặc định `minSubscribers` là `0`, nên send được coi là thành công ngay cả khi không có subscriber. Từ Spring Integration 5.4.3, có thể bật `requireSubscribers` để không âm thầm bỏ message khi danh sách subscriber rỗng; khi bật, dispatcher ném `MessageDispatchingException` với thông báo `Dispatcher has no subscribers`. `minSubscribers` và `requireSubscribers` phục vụ hai mục đích liên quan nhưng khác nhau: `minSubscribers` đặt số lượng tối thiểu để `send()` trả về `true`, còn `requireSubscribers` yêu cầu ít nhất một subscriber và phát lỗi nếu không có ai.

Ví dụ bật yêu cầu subscriber:

~~~java
@Bean
PublishSubscribeChannel orderEventsChannel() {
    PublishSubscribeChannel channel = new PublishSubscribeChannel(true);
    channel.setMinSubscribers(1);
    return channel;
}
~~~

Nếu ứng dụng cần hỗ trợ phiên bản Spring Integration trước 5.4.3, kiểm tra API của phiên bản đó trước khi dùng constructor có `requireSubscribers`.

### QueueChannel

Queue channel có thể nhận message trước khi consumer poll. Nếu chưa có polling consumer, message sẽ nằm trong queue cho tới khi consumer xuất hiện hoặc queue đầy. Kiểm tra capacity, send timeout, receive timeout và lifecycle của polling endpoint.

### RendezvousChannel

Rendezvous channel không có buffer. Producer chờ một consumer gọi `receive()` để handoff. Nếu consumer không poll, producer sẽ block hoặc timeout. Đây không phải lỗi “dispatcher không có subscriber” của `SubscribableChannel`, mà là chưa có receiver cho lần handoff.

## 8. Kiểm thử tình huống không có subscriber

Với `DirectChannel`, có thể viết test xác nhận gửi khi chưa đăng ký subscriber sẽ phát sinh lỗi messaging:

~~~java
@Test
void directChannelWithoutSubscriberCannotDispatch() {
    DirectChannel channel = new DirectChannel();
    Message<String> message = MessageBuilder.withPayload("hello").build();

    assertThrows(MessagingException.class, () -> channel.send(message));
}
~~~

Test này kiểm tra topology thiếu subscriber ở mức channel. Với `PublishSubscribeChannel`, cần test riêng theo `minSubscribers`; với `QueueChannel`, test send/receive và capacity; với `RendezvousChannel`, test receiver handoff và timeout. Không dùng một test chung cho mọi channel vì semantics khác nhau.

Một integration test nên khởi tạo ApplicationContext, xác nhận endpoint đã start và gửi một message có Correlation ID. Sau đó kiểm tra handler được gọi đúng một lần, hoặc đúng số nhánh nếu dùng publish-subscribe. Test cũng nên stop endpoint và xác minh hành vi send khi subscriber đã bị gỡ.

## 9. Xử lý khi consumer chưa sẵn sàng

Nếu consumer chưa sẵn sàng tại thời điểm producer phát message, chọn giải pháp theo yêu cầu nghiệp vụ:

| Yêu cầu | Hướng xử lý |
|---|---|
| Consumer phải có trước khi nhận traffic | Điều phối startup/readiness; chỉ mở producer sau khi endpoint running |
| Cho phép message chờ consumer | Dùng `QueueChannel` với capacity và timeout phù hợp |
| Cần giữ message qua JVM restart | Dùng broker hoặc persistent message store có durability phù hợp |
| Flow được bật theo tenant khi runtime | Đăng ký/start flow trước khi mở route cho tenant |
| Consumer tạm dừng bảo trì | Chặn producer hoặc chuyển traffic sang queue/broker trước khi stop |
| Không có consumer là cấu hình sai | Fail fast, log rõ channel và message ID, alert vận hành |

Không đổi `DirectChannel` thành `QueueChannel` chỉ để che lỗi subscriber nếu yêu cầu nghiệp vụ cần xử lý đồng bộ. Việc thay channel làm thay đổi thread model, thời điểm xác nhận send, error propagation và transaction boundary.

## 10. Error flow không tự sửa lỗi topology

Nếu dispatcher không có subscriber, message chưa tới handler dự kiến. Error flow có thể nhận exception tùy nơi phát sinh và cấu hình, nhưng nó không tự tạo subscriber cho output channel đang thiếu consumer.

Phân biệt các trường hợp:

- **Không có subscriber:** sửa cấu hình endpoint, tên channel hoặc lifecycle.
- **Handler ném exception:** cấu hình error channel, retry advice hoặc dead-letter phù hợp.
- **Queue đầy:** xử lý send timeout, capacity và backpressure ở producer.
- **Executor từ chối task:** điều chỉnh pool/queue hoặc giảm concurrency.
- **Router chọn sai output:** sửa route key, mapping hoặc default output.

Không bắt mọi `MessagingException` rồi retry vô hạn. Nếu topology không đổi, retry chỉ lặp lại cùng một lỗi và có thể làm cạn thread producer.

## 11. Checklist điều tra output channel không có subscriber

- [ ] Xác định channel thực tế và loại channel (`SubscribableChannel` hay `PollableChannel`).
- [ ] Kiểm tra producer và consumer tham chiếu cùng bean/name.
- [ ] Với `DirectChannel`/`ExecutorChannel`, kiểm tra subscriber count.
- [ ] Xác minh endpoint đã được đăng ký và `isRunning()` là `true`.
- [ ] Kiểm tra `autoStartup`, lifecycle phase và thứ tự startup.
- [ ] Nếu dùng `IntegrationFlowContext`, xác minh flow đã register, start và chưa bị remove.
- [ ] Với `QueueChannel`, kiểm tra poller, queue depth, capacity và receive timeout.
- [ ] Với `PublishSubscribeChannel`, kiểm tra subscriber và `minSubscribers`.
- [ ] Với `RendezvousChannel`, kiểm tra consumer có gọi receive trong thời gian send timeout.
- [ ] Kiểm tra router output, default channel và channel resolution.
- [ ] Dùng Integration Graph cùng log message ID/Correlation ID để xác nhận đường đi.
- [ ] Chỉ retry sau khi đã khắc phục nguyên nhân hoặc có chính sách retry hữu hạn.

Output channel không có subscriber thường là dấu hiệu producer và consumer chưa được nối với nhau tại runtime. Xác định đúng loại channel sẽ cho biết cần đăng ký subscriber, khởi động polling consumer, hay chuyển sang một cơ chế có buffer. Sau đó kiểm tra bean name, lifecycle và topology để bảo đảm message được nhận ở đúng thời điểm, đúng endpoint và theo đúng semantics mà flow yêu cầu.

## Tài liệu tham khảo

- [Spring Integration Reference: Message Channels](https://docs.spring.io/spring-integration/reference/channel.html)
- [Spring Integration API: DirectChannel](https://docs.spring.io/spring-integration/docs/6.4.x/api/org/springframework/integration/channel/DirectChannel.html)
- [Spring Integration API: PublishSubscribeChannel](https://docs.spring.io/spring-integration/docs/6.4.x/api/org/springframework/integration/channel/PublishSubscribeChannel.html)
- [Spring Integration API: QueueChannel](https://docs.spring.io/spring-integration/docs/6.4.x/api/org/springframework/integration/channel/QueueChannel.html)
- [Spring Integration Reference: Configuring Message Channels](https://docs.spring.io/spring-integration/reference/channel/configuration.html)
- [Spring Integration Reference: Java DSL](https://docs.spring.io/spring-integration/reference/dsl/java.html)
# Output channel không có subscriber

Trong Spring Integration, một message producer tạo message rồi gửi message đó đến một `MessageChannel`. Với inbound adapter, service activator trả về kết quả, transformer, router hoặc một endpoint khác, channel đầu ra thường được cấu hình qua `outputChannel` hoặc bằng bước `.channel(...)` trong `IntegrationFlow`.

Khi output channel không có subscriber, kết quả phụ thuộc vào loại channel. Với channel đẩy như `DirectChannel`, message thường không thể được chuyển tiếp và thao tác gửi phát sinh lỗi. Với `PublishSubscribeChannel`, message có thể bị bỏ qua nếu cấu hình không yêu cầu subscriber tối thiểu. Với `QueueChannel`, message có thể nằm trong hàng đợi để consumer đọc sau. Vì vậy, cần xác định đúng loại channel và ý nghĩa giao nhận mà flow mong muốn trước khi sửa lỗi.

## Subscriber là gì?

Subscriber là thành phần đăng ký nhận message từ một channel có cơ chế push. Trong Spring Integration, consumer endpoint như service activator, transformer, router hoặc một `IntegrationFlow` bắt đầu từ channel có thể đăng ký làm subscriber. Endpoint thường đăng ký khi được khởi động và hủy đăng ký khi dừng.

Điều này có nghĩa là khai báo một bean channel chưa tạo ra consumer. Tương tự, việc một `IntegrationFlow` có bước `.channel("resultChannel")` chỉ định nơi gửi message; nó không tự bảo đảm rằng đã có endpoint nhận message ở đầu kia. Một flow khác phải lắng nghe channel đó, hoặc channel phải có cơ chế lưu message để consumer lấy ra sau.

Không nên đánh đồng subscriber với poller. Subscriber nhận message được channel đẩy tới. Poller định kỳ đọc message từ một `PollableChannel`. `QueueChannel` có thể nhận message dù chưa có consumer đang poll; `DirectChannel` cần subscriber để dispatch ngay.

## Điều gì xảy ra khi không có subscriber?

### `DirectChannel`

`DirectChannel` là channel push, point-to-point và đồng bộ. Khi producer gửi message, dispatcher gọi một trong các subscriber đã đăng ký ngay trên luồng gửi. Nếu không có subscriber, dispatcher không có handler để thực thi và thường ném `MessageDispatchingException` với thông báo tương tự `Dispatcher has no subscribers`.

Vì gửi đồng bộ, lỗi có thể truyền ngược về nơi gọi `send()` hoặc endpoint đang tạo output message. Một message producer vì vậy có thể trông như đã tạo message thành công nhưng flow vẫn thất bại ở bước chuyển message sang output channel.

### `ExecutorChannel`

`ExecutorChannel` chuyển việc dispatch sang executor để xử lý bất đồng bộ, nhưng vẫn là channel push có subscriber. Executor không thay thế consumer. Nếu không có subscriber, việc dispatch vẫn không có đích nhận và có thể thất bại trước hoặc trong quá trình gửi tác vụ, tùy đường đi thực thi.

Không nên chọn `ExecutorChannel` chỉ để né lỗi thiếu subscriber. Channel này thay đổi threading và thời điểm xử lý; nó không tạo ra một consumer còn thiếu.

### `PublishSubscribeChannel`

`PublishSubscribeChannel` phát một message đến các subscriber đã đăng ký. Thuộc tính `minSubscribers` quy định số subscriber tối thiểu cần có để thao tác gửi được xem là thành công. Giá trị mặc định là `0`, vì vậy channel có thể chấp nhận message ngay cả khi không có subscriber; khi đó không có endpoint nào xử lý message.

Nếu message bắt buộc phải được ít nhất một consumer xử lý, hãy đặt `minSubscribers` thành `1` hoặc cao hơn phù hợp với yêu cầu. Cấu hình này biến tình trạng thiếu subscriber thành lỗi quan sát được thay vì để message bị bỏ qua âm thầm. Chỉ giữ mức tối thiểu bằng `0` khi việc không có consumer là một tình huống được chấp nhận.

### `QueueChannel`

`QueueChannel` là channel pull. Producer đưa message vào hàng đợi; consumer lấy message ra bằng cách poll, thường thông qua một endpoint có poller. Vì vậy, không có consumer đang chạy không đồng nghĩa với việc không có nơi nhận message: message có thể chờ trong queue.

Khả năng đệm này có giới hạn thực tế. Nếu queue có capacity hữu hạn và đã đầy, thao tác gửi có thể chờ theo timeout hoặc trả về thất bại. Nếu consumer không bao giờ khởi động, message tiếp tục tồn tại trong queue cho đến khi được đọc hoặc bị mất theo vòng đời lưu trữ của ứng dụng. `QueueChannel` trong bộ nhớ cũng không tự cung cấp tính bền vững qua lần khởi động lại ứng dụng.

### `NullChannel`

`NullChannel` nhận và loại bỏ message có chủ đích. Nó hữu ích khi kết quả đầu ra không cần được xử lý tiếp, nhưng không phải cách khắc phục chung cho channel bị thiếu subscriber. Dùng nó chỉ khi việc bỏ message là một phần rõ ràng của thiết kế.

| Loại channel | Cách nhận message | Khi không có consumer |
| --- | --- | --- |
| `DirectChannel` | Push đồng bộ đến subscriber | Dispatch thất bại vì không có subscriber |
| `ExecutorChannel` | Push qua executor đến subscriber | Vẫn thiếu đích nhận; dispatch có thể thất bại |
| `PublishSubscribeChannel` | Broadcast đến các subscriber | Mặc định `minSubscribers=0` có thể chấp nhận rồi bỏ qua message; đặt mức tối thiểu để yêu cầu subscriber |
| `QueueChannel` | Lưu message, consumer poll để lấy | Message chờ trong queue; gửi có thể thất bại khi queue đầy |
| `NullChannel` | Nhận rồi loại bỏ | Message bị bỏ có chủ đích |

## Ví dụ: producer gửi vào `DirectChannel` chưa có consumer

Giả sử một flow xử lý dữ liệu đầu vào rồi chuyển kết quả sang `resultChannel`:

```java
@Bean
MessageChannel resultChannel() {
    return new DirectChannel();
}

@Bean
IntegrationFlow producerFlow() {
    return IntegrationFlow.from("inputChannel")
            .<String, String>transform(String::trim)
            .channel("resultChannel")
            .get();
}
```

Đoạn cấu hình trên chỉ tạo nơi gửi. Nếu không có endpoint nào subscribe `resultChannel`, khi message đi qua bước `.channel("resultChannel")`, `DirectChannel` không tìm thấy subscriber để dispatch. Với đường gửi đồng bộ, lỗi sẽ xuất hiện trong quá trình xử lý message đầu vào.

Thêm một consumer flow để đăng ký nhận message:

```java
@Bean
IntegrationFlow resultConsumerFlow() {
    return IntegrationFlow.from("resultChannel")
            .handle(String.class, (payload, headers) -> {
                log.info("Received result: {}", payload);
                return null;
            })
            .get();
}
```

Khi application context khởi động và endpoint của `resultConsumerFlow` được start, endpoint đăng ký với channel. Message được producer gửi sau đó có subscriber để nhận. Nếu consumer được cấu hình `autoStartup=false`, hoặc flow động chưa được đăng ký hay start, subscriber vẫn có thể vắng mặt tại thời điểm producer gửi.

## Cách chẩn đoán

1. **Xác định đúng channel đầu ra.** Lần theo `outputChannel`, bước `.channel(...)`, hoặc header `replyChannel` nếu flow dùng request-reply. Kiểm tra tên channel có trỏ đến đúng bean mà consumer sử dụng hay không.
2. **Xác định loại channel.** Kiểm tra bean là `DirectChannel`, `ExecutorChannel`, `PublishSubscribeChannel`, `QueueChannel` hay loại khác. Không áp dụng cách xử lý của pollable channel cho channel push.
3. **Tìm endpoint nhận message.** Xác nhận có service activator, consumer flow hoặc endpoint khác bắt đầu từ channel đó. Một bean channel đơn lẻ không phải là subscriber.
4. **Kiểm tra vòng đời endpoint.** Xác nhận application context đã hoàn tất khởi động, endpoint đã start, profile/condition chứa consumer đã được bật và flow động đã được đăng ký. Với flow đăng ký qua `IntegrationFlowContext`, kiểm tra registration và trạng thái start của registration.
5. **Đọc exception tại điểm gửi.** `MessageDispatchingException` cùng thông báo `Dispatcher has no subscribers` là dấu hiệu điển hình của một dispatcher không có subscriber. Xem stack trace để tìm endpoint producer hoặc bước flow đã gửi message.
6. **Quan sát runtime.** Bật log DEBUG có chọn lọc cho `org.springframework.integration` khi cần theo dõi đăng ký endpoint và dispatch. Nếu ứng dụng bật Spring Integration graph endpoint qua Actuator, xem graph để đối chiếu các endpoint và channel đang được runtime công bố.
7. **Kiểm tra queue riêng biệt.** Với `QueueChannel`, xem message có đang tích tụ, consumer poller có chạy và capacity có bị sử dụng hết hay không. Trạng thái queue không được chẩn đoán bằng số subscriber của `DirectChannel`.

Một consumer có thể đã được khai báo trong mã nguồn nhưng chưa hoạt động ở runtime. Vì thế, cần kiểm tra trạng thái endpoint đang chạy thay vì chỉ tìm tên channel hoặc lớp consumer trong source code.

## Các cách xử lý phù hợp

**Thêm consumer khi message phải được xử lý ngay.** Với `DirectChannel`, tạo hoặc bật endpoint nhận message và bảo đảm endpoint đã start trước khi producer gửi. Đây là lựa chọn phù hợp khi cần xử lý đồng bộ và muốn lỗi của consumer có thể truyền về bên gửi.

**Dùng `QueueChannel` khi cần tách thời điểm gửi và nhận.** Cấu hình consumer poller để lấy message theo lịch. Chọn capacity, timeout và chính sách lưu trữ phù hợp với tốc độ producer, tốc độ consumer và yêu cầu mất dữ liệu. Chỉ chuyển từ `DirectChannel` sang queue khi việc đệm và xử lý trễ phù hợp với nghiệp vụ.

**Đặt `minSubscribers` khi broadcast không được phép mất người nhận.** Với `PublishSubscribeChannel`, đặt mức subscriber tối thiểu theo yêu cầu xử lý. Nếu tất cả consumer đều bắt buộc phải nhận, đồng thời xác định cách ứng dụng phản ứng khi chỉ một phần consumer đang hoạt động.

**Dùng `NullChannel` khi chủ động bỏ kết quả.** Đây là lựa chọn rõ ràng cho một output không cần xử lý tiếp. Không dùng nó để che một consumer bị cấu hình thiếu, vì khi đó lỗi cấu hình sẽ biến thành mất message âm thầm.

**Xử lý lỗi ở đúng ranh giới.** `errorChannel` hoặc error flow có thể giúp ghi nhận và xử lý exception từ các endpoint bất đồng bộ. Chúng không tự tạo subscriber cho output channel. Với đường gửi đồng bộ, hãy xử lý exception tại nơi gọi hoặc endpoint thích hợp; với đường bất đồng bộ, xác nhận cơ chế chuyển lỗi của endpoint đó và cấu hình error flow tương ứng.

## Phòng tránh lỗi trong vòng đời runtime

- Khai báo rõ channel đầu ra và consumer tương ứng; đặt tên channel nhất quán giữa producer và consumer.
- Bảo đảm endpoint consumer được start trước khi nguồn message bắt đầu phát dữ liệu. Với flow động, hoàn tất đăng ký và start flow trước khi kích hoạt producer phụ thuộc vào flow đó.
- Nếu consumer có thể dừng hoặc khởi động lại độc lập, quyết định trước message cần thất bại ngay, được đệm trong queue hay được phép bỏ qua.
- Với `PublishSubscribeChannel`, đặt `minSubscribers` theo mức đảm bảo thực tế mà nghiệp vụ yêu cầu.
- Theo dõi exception dispatch, trạng thái endpoint và độ sâu queue. Cảnh báo khi consumer dừng hoặc queue tăng liên tục để phát hiện vấn đề trước khi producer gặp lỗi hoặc queue đầy.
- Viết kiểm thử tích hợp cho cả trường hợp consumer hoạt động và trường hợp consumer chưa được start. Kiểm thử nên xác nhận hành vi đúng với loại channel đã chọn, bao gồm việc lỗi được truyền về, message được lưu chờ hay message được bỏ qua có chủ đích.

Khi gặp lỗi output channel không có subscriber, hãy bắt đầu từ câu hỏi: channel này được thiết kế để đẩy message ngay, broadcast, lưu chờ hay loại bỏ? Sau đó đối chiếu subscriber và vòng đời endpoint với đúng ngữ nghĩa đó. Cách tiếp cận này giúp xử lý đúng nguyên nhân và giữ nguyên đặc tính giao nhận mà flow cần có.
