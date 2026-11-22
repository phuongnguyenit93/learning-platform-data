# MessageDispatcher và nhiệm vụ chọn handler

Trong Spring Integration, message đi vào một channel có thể được chuyển tới một hoặc nhiều consumer đã đăng ký. Với các channel kiểu `SubscribableChannel`, Spring cần một thành phần quản lý danh sách subscriber và quyết định handler nào sẽ được gọi khi producer gửi message. Thành phần đó là `MessageDispatcher`.

Dispatcher là cơ chế dispatch bên trong channel. Nó chọn hoặc gọi các `MessageHandler` đã subscribe, theo semantics của channel và cấu hình load balancing/failover. Nó không phân tích payload để quyết định message thuộc loại nghiệp vụ nào, cũng không tự chọn output channel. Những công việc đó thuộc router.

Điểm cần phân biệt là **chọn một handler**, **gọi tất cả handler** và **lưu message để consumer poll** là ba hành vi khác nhau. `DirectChannel` thường dùng unicast dispatcher để chọn một handler; `PublishSubscribeChannel` dùng broadcasting dispatcher để gọi các subscriber; `QueueChannel` lưu message và để polling consumer lấy ra.

## 1. MessageDispatcher nằm ở đâu trong kiến trúc?

Một `IntegrationFlow` thường gồm producer, channel, endpoint và handler. Với channel có subscriber, endpoint đăng ký handler vào channel. Khi producer gọi `send(message)`, channel chuyển message cho dispatcher. Dispatcher dựa vào danh sách handler hiện tại để thực hiện việc dispatch.

Sơ đồ khái quát:

~~~mermaid
flowchart LR
    P["Producer"] --> C["SubscribableChannel"]
    E1["Endpoint A"] -->|subscribe| D["MessageDispatcher"]
    E2["Endpoint B"] -->|subscribe| D
    E3["Endpoint C"] -->|subscribe| D
    C --> D
    D --> H{"Chính sách dispatch"}
    H -->|"Unicast"| U["Một handler được chọn"]
    H -->|"Broadcast"| B["Tất cả subscriber"]
    U --> W["Handler xử lý"]
    B --> W
~~~

Trong runtime:

1. Endpoint được khởi tạo và đăng ký handler vào input channel.
2. Channel giữ dispatcher và danh sách subscriber.
3. Producer gửi message vào channel.
4. Dispatcher chọn thứ tự hoặc tập handler theo semantics của channel.
5. Handler được gọi trực tiếp hoặc thông qua executor, tùy implementation.
6. Kết quả dispatch và exception được trả về hoặc chuyển qua error handling tùy mô hình đồng bộ/bất đồng bộ.

`MessageDispatcher` là abstraction của Spring Integration, thuộc package `org.springframework.integration.dispatcher`. Trong ứng dụng thông thường, ta cấu hình channel và endpoint; không cần tự tạo dispatcher hoặc gọi trực tiếp API nội bộ của nó.

## 2. Dispatcher giải quyết bài toán gì?

Một channel có thể có nhiều endpoint subscribe. Nếu tất cả cùng nhận một message, channel sẽ trở thành broadcast. Nếu chỉ một endpoint nên xử lý mỗi message, channel cần cơ chế chọn một subscriber.

Dispatcher cung cấp chính sách cho tình huống đó:

- Quản lý các handler đã đăng ký.
- Chọn handler hoặc thứ tự thử handler.
- Thực hiện dispatch theo kiểu unicast hoặc broadcast tùy implementation.
- Báo lỗi khi không có subscriber hoặc không handler nào xử lý được.
- Với unicast dispatcher, áp dụng load balancing và failover nếu được cấu hình.

Dispatcher không quyết định endpoint nào được tạo trong flow. Việc đăng ký subscriber đến từ cấu hình endpoint, lifecycle và channel. Nếu endpoint chưa start hoặc đã stop, tập subscriber mà dispatcher nhìn thấy có thể khác.

### MessageHandler là đích dispatch

Một handler thường thực thi thông qua abstraction:

~~~java
public interface MessageHandler {
    void handleMessage(Message<?> message);
}
~~~

Các service activator, transformer, filter, router và nhiều endpoint khác có thể được adapter thành message handler. Dispatcher chỉ cần biết đối tượng nhận message qua `handleMessage()`; nó không cần biết handler đang gọi repository, REST client hay một bước biến đổi dữ liệu.

## 3. Hai dispatcher quan trọng: unicast và broadcast

Spring Integration có hai cách dispatch thường gặp:

| Dispatcher | Channel thường dùng | Semantics |
|---|---|---|
| `UnicastingDispatcher` | `DirectChannel`, `ExecutorChannel` | Thử các handler theo thứ tự chính sách cho tới khi một handler xử lý thành công; mỗi message có tối đa một handler xử lý thành công |
| `BroadcastingDispatcher` | `PublishSubscribeChannel` | Phát message tới tất cả subscriber |

Cần hiểu "unicast" là mỗi message được giao cho một handler thành công. Khi failover bật, dispatcher có thể thử handler tiếp theo nếu handler trước ném exception. Vì vậy, trong một lần dispatch có thể có nhiều lần gọi handler, dù mục tiêu cuối cùng vẫn là một handler xử lý thành công.

Broadcast có mục tiêu khác: mỗi subscriber đều nhận message. Nếu cần gửi event tới nhiều consumer độc lập, hãy dùng publish-subscribe semantics thay vì trông đợi failover của unicast sẽ gọi tất cả.

## 4. UnicastingDispatcher chọn handler như thế nào?

`UnicastingDispatcher` cố gắng dispatch một message tới tối đa một handler xử lý thành công. Nếu có nhiều handler, thứ tự thử được quyết định bởi `LoadBalancingStrategy` nếu được cấu hình.

Quy trình khái quát:

1. Lấy danh sách handler đã subscribe.
2. Xác định handler bắt đầu theo load-balancing strategy hoặc thứ tự cố định.
3. Gọi handler được chọn.
4. Nếu handler xử lý mà không ném exception, dispatch kết thúc.
5. Nếu handler ném exception và failover được bật, thử handler tiếp theo theo chính sách.
6. Nếu mọi handler được thử đều ném exception, dispatcher phát sinh lỗi tổng hợp.
7. Nếu không có handler, dispatcher báo lỗi không có subscriber.

Javadoc mô tả `UnicastingDispatcher` sẽ trả về `true` khi message được dispatch thành công; nếu không có handler, `MessageDispatchingException` được ném ra; nếu mọi handler đều ném exception, dispatcher có thể ném `AggregateMessageDeliveryException`.

### Không có handler

Một channel được tạo nhưng chưa có endpoint subscribe có thể chưa có consumer để nhận message. Với unicast dispatcher, dispatch message trong trạng thái không có handler sẽ tạo `MessageDispatchingException`.

Điều này thường xuất hiện khi:

- Producer gửi trước khi consumer endpoint được khởi động.
- Input channel của endpoint bị cấu hình sai tên hoặc sai bean.
- Endpoint đã stop hoặc bị gỡ khỏi context.
- Dynamic flow chưa được register/start.
- Tất cả subscriber đã unsubscribe.

Cần kiểm tra channel thực tế producer đang dùng và trạng thái endpoint đã đăng ký vào channel đó.

## 5. Load balancing: round-robin và thứ tự cố định

`LoadBalancingStrategy` quyết định thứ tự các handler được thử. Với `DirectChannel`, mặc định là round-robin load balancing và failover được bật.

### Round-robin

Round-robin xoay vòng handler bắt đầu cho các message liên tiếp. Giả sử channel có ba subscriber A, B và C:

| Message | Handler bắt đầu |
|---|---|
| M1 | A |
| M2 | B |
| M3 | C |
| M4 | A |
| M5 | B |
| M6 | C |

Đây là cách phân phối lượt dispatch, không phải cam kết chia đều thời gian CPU hoặc thời gian xử lý. Nếu A xử lý một message mất 10 ms còn B mất 2 giây, số lượt có thể tương đương nhưng tải thực tế không cân bằng.

Round-robin cũng không cung cấp affinity theo business key. Hai message cùng `orderId` có thể đi tới hai handler khác nhau. Nếu cần xử lý tuần tự theo key, cần thiết kế partitioning, routing theo key hoặc cơ chế đồng bộ riêng.

### Không load balancing: thứ tự cố định

Nếu muốn luôn bắt đầu với handler đầu tiên, có thể tắt load balancing. Khi đó dispatcher thử handler theo thứ tự được định nghĩa; failover vẫn có thể chuyển sang handler kế tiếp khi handler trước ném exception.

Ví dụ Java:

~~~java
@Bean
DirectChannel primaryFirstChannel() {
    // null strategy: không round-robin; bắt đầu theo thứ tự handler
    return new DirectChannel(null);
}
~~~

Cách này phù hợp với mô hình primary/secondary khi handler đầu tiên là primary và handler sau là fallback. Thứ tự endpoint nên được cấu hình rõ ràng; nếu không, thứ tự đăng ký có thể trở thành yếu tố quyết định.

### Custom LoadBalancingStrategy

Khi round-robin hoặc thứ tự cố định không đáp ứng yêu cầu, có thể cung cấp implementation của `LoadBalancingStrategy` và tham chiếu nó từ channel configuration.

Ví dụ XML:

~~~xml
<int:channel id="ordersChannel">
    <int:dispatcher load-balancer-ref="ordersLoadBalancer"
                    failover="true"/>
</int:channel>

<bean id="ordersLoadBalancer"
      class="com.example.integration.OrdersLoadBalancingStrategy"/>
~~~

Strategy tùy chỉnh có thể áp dụng chính sách lựa chọn riêng, nhưng cần bảo đảm thread-safety, tính ổn định và chi phí tính toán thấp. Không nên dựa vào trạng thái mutable không đồng bộ nếu nhiều producer gửi message đồng thời.

## 6. Failover: thử handler tiếp theo khi handler trước lỗi

Load balancing chọn handler bắt đầu. Failover quyết định dispatcher có tiếp tục thử handler khác khi handler hiện tại ném exception hay không.

Với `DirectChannel` mặc định:

- Round-robin được bật.
- Failover được bật.
- Nếu handler bắt đầu ném exception, dispatcher có thể thử handler tiếp theo.
- Nếu tất cả handler được thử đều thất bại, lỗi tổng hợp được phát ra.

Có thể tắt failover:

~~~java
@Bean
DirectChannel failFastChannel() {
    DirectChannel channel = new DirectChannel();
    channel.setFailover(false);
    return channel;
}
~~~

Khi failover tắt, lỗi của handler được chọn kết thúc lần dispatch; dispatcher không thử handler kế tiếp.

### Failover không phải retry cùng một handler

Cần phân biệt ba cơ chế:

| Cơ chế | Hành vi |
|---|---|
| Dispatcher failover | Chuyển cùng message sang handler khác khi handler trước ném exception |
| Retry advice | Thử lại thao tác hoặc handler theo retry policy, thường có số lần thử và backoff |
| Broker redelivery | Broker giao lại message theo acknowledgment và delivery policy |

Failover không gọi lại handler vừa lỗi. Nó chuyển sang handler tiếp theo trong tập subscriber. Retry advice mới là cơ chế phù hợp nếu muốn thử lại cùng một thao tác. Broker redelivery lại phụ thuộc adapter và broker.

### Rủi ro side effect trùng lặp

Giả sử handler A đã ghi một bản ghi vào database nhưng ném exception khi gửi thông báo ra ngoài. Dispatcher thấy exception và chuyển cùng message sang handler B. Nếu B cũng ghi bản ghi đó, nghiệp vụ có thể bị thực hiện hai lần.

Do đó, failover chỉ an toàn khi các handler có thể thay thế nhau và side effect được bảo vệ bằng idempotency hoặc transaction phù hợp. Nếu lỗi xảy ra sau một phần side effect, dispatcher không thể tự biết thao tác đã hoàn tất đến đâu.

Không nên đăng ký hai service activator có nghiệp vụ khác nhau vào cùng một DirectChannel rồi xem failover như cách dự phòng chung. Các subscriber của unicast channel thường là các worker thay thế nhau cho cùng một loại công việc.

## 7. Failover theo loại exception từ Spring Integration 6.3

Từ Spring Integration 6.3, các channel dựa trên `UnicastingDispatcher` có thể dùng `Predicate<Exception> failoverStrategy` thay cho lựa chọn boolean đơn giản.

Predicate cho phép quyết định có chuyển sang handler kế tiếp hay không dựa trên exception vừa phát sinh. Điều này hữu ích khi chỉ một số lỗi được xem là lý do để thử subscriber khác.

Ví dụ về chính sách ở mức ý tưởng:

| Exception | Quyết định failover có thể phù hợp |
|---|---|
| Handler tạm thời không khả dụng trước khi tạo side effect | Có thể thử handler kế tiếp nếu các handler thực sự thay thế được nhau |
| Validation exception | Không nên thử handler khác vì dữ liệu đầu vào vẫn sai |
| Business rejection | Thường không nên xem là lỗi khả dụng của handler |
| Database constraint violation | Thử handler khác thường không giải quyết nguyên nhân |
| Timeout không rõ trạng thái commit | Cần thận trọng vì side effect có thể đã xảy ra |

Predicate chỉ quyết định có tiếp tục dispatch hay không. Nó không thay thế retry policy, phân loại lỗi nghiệp vụ hoặc cơ chế routing lỗi phức tạp. Với phân tích exception nâng cao, có thể dùng `ErrorMessageExceptionTypeRouter` trong error flow.

## 8. DirectChannel: dispatcher chọn một subscriber

`DirectChannel` là `SubscribableChannel` có point-to-point semantics. Nó dispatch mỗi message tới một subscriber xử lý thành công. Khi chỉ có một subscriber, việc dispatch đơn giản; khi có nhiều subscriber, load balancing và failover quyết định handler nào được thử.

Cấu hình mặc định:

~~~java
@Bean
DirectChannel ordersWorkChannel() {
    return new DirectChannel();
}
~~~

Nếu có nhiều endpoint cùng dùng channel làm input, các endpoint đó cạnh tranh nhận message theo dispatcher. Ví dụ, ba worker cùng subscribe một DirectChannel sẽ chia nhau message theo round-robin mặc định; chúng không phải ba nhánh cùng nhận một bản sao.

### Khi nào nên dùng?

- Nhiều worker cùng xử lý một loại message.
- Muốn phân phối lượt dispatch giữa các subscriber.
- Muốn giữ xử lý trên thread gửi để transaction có thể bao quanh downstream đồng bộ.
- Muốn có failover giữa các handler thay thế nhau khi một handler ném exception.

Nếu cần mỗi consumer nhận một bản sao, hãy dùng `PublishSubscribeChannel`. Nếu cần buffer hoặc tách thời điểm gửi và nhận, dùng `QueueChannel` hoặc một channel phù hợp khác.

## 9. ExecutorChannel cũng dùng unicast dispatcher

`ExecutorChannel` là point-to-point channel sử dụng `TaskExecutor` để thực hiện dispatch. Nó hỗ trợ cấu hình load balancing và failover tương tự DirectChannel, nhưng việc gọi handler được bàn giao sang executor.

Ví dụ:

~~~java
@Bean
MessageChannel asyncOrdersChannel(
        @Qualifier("integrationExecutor") TaskExecutor executor
) {
    return new ExecutorChannel(executor);
}
~~~

Khác biệt quan trọng:

| DirectChannel | ExecutorChannel |
|---|---|
| Handler thường chạy trên thread gọi `send()` | Handler chạy trên worker do executor cấp |
| Dispatch đồng bộ trong call stack gửi | Dispatch được bàn giao cho executor |
| Exception đồng bộ có thể truyền về caller | Lỗi handler xảy ra sau đó không thể truyền ngược theo call stack sender |
| Có thể giữ transaction thread-bound xuyên qua channel | Transaction của sender không tự động truyền sang worker |

Với ExecutorChannel, kết quả gửi thường chỉ phản ánh task đã được executor tiếp nhận. Nó không xác nhận handler đã hoàn tất. Nếu task bị từ chối do executor bão hòa, caller có thể nhận lỗi submit; nếu handler ném exception sau khi task chạy, cần error handling phù hợp với execution thread.

Với ExecutorChannel, failover (nếu bật) được áp dụng bên trong dispatch task trên worker thread khi dispatcher đang thử các handler. Sender không quan sát exception đó qua call stack của `send()`. Nếu các handler được thử đều thất bại hoặc task phát sinh lỗi ngoài quá trình dispatch, cần cấu hình error handling bất đồng bộ và cơ chế phục hồi riêng.

## 10. PublishSubscribeChannel dùng BroadcastingDispatcher

`PublishSubscribeChannel` có semantics broadcast: mỗi subscriber nhận message. Nó dùng `BroadcastingDispatcher` thay cho `UnicastingDispatcher`.

Ví dụ:

~~~java
@Bean
PublishSubscribeChannel orderEventsChannel() {
    return new PublishSubscribeChannel();
}
~~~

Nếu có ba subscriber A, B và C, một message được phát tới cả ba. Điều này phù hợp cho event notification, ví dụ sau khi đơn hàng được gửi thành công thì nhiều consumer cùng cập nhật search index, gửi email hoặc ghi audit.

| Tình huống | Dispatcher phù hợp |
|---|---|
| Một trong nhiều worker xử lý mỗi message | UnicastingDispatcher |
| Tất cả subscriber đều nhận mỗi message | BroadcastingDispatcher |
| Chọn channel theo payload/header | Message router |
| Lưu message chờ consumer poll | QueueChannel và PollingConsumer |

Nếu PublishSubscribeChannel không cấu hình executor, subscriber thường được gọi trên thread gửi. Nếu có executor, việc xử lý subscriber có thể bất đồng bộ; khi đó lỗi được xử lý qua error handler/error channel theo cấu hình, thay vì luôn truyền về sender.

## 11. QueueChannel không dùng MessageDispatcher để chọn consumer

`QueueChannel` là `PollableChannel`, không phải `SubscribableChannel`. Producer gửi message vào queue; polling consumer gọi `receive()` để lấy message.

Vì vậy, không có `UnicastingDispatcher` chọn subscriber theo round-robin cho mỗi lần send. Việc cạnh tranh message diễn ra ở thao tác receive của các consumer, tùy queue implementation và số polling consumer.

Một điểm dễ nhầm:

- DirectChannel chọn handler tại thời điểm dispatch.
- QueueChannel lưu message; consumer lấy message khi poll.
- PublishSubscribeChannel broadcast message ngay khi send.
- ExecutorChannel chọn handler theo unicast dispatcher rồi bàn giao việc dispatch qua executor.

Khi cần quan sát “handler nào nhận message”, hãy xác định channel đang dùng semantics nào trước khi kiểm tra dispatcher.

## 12. Dispatcher khác MessageRouter như thế nào?

Đây là khác biệt quan trọng trong thiết kế flow.

**Dispatcher** chọn handler trong tập subscriber của một channel. Nó thường dựa trên load-balancing strategy, thứ tự handler và failover.

**Router** phân tích message rồi chọn output channel tiếp theo. Router có thể dựa trên payload, header, expression, recipient list hoặc cấu hình định tuyến nghiệp vụ.

Ví dụ:

~~~mermaid
flowchart LR
    P["Message"] --> R["MessageRouter"]
    R -->|"type=urgent"| C1["urgentChannel"]
    R -->|"type=normal"| C2["normalChannel"]
    C1 --> D1["Dispatcher của channel"]
    C2 --> D2["Dispatcher của channel"]
    D1 --> H1["Handler worker"]
    D2 --> H2["Handler worker"]
~~~

| Câu hỏi | Thành phần trả lời |
|---|---|
| Message thuộc loại đơn hàng nào và cần đi channel nào? | Router |
| Trong các subscriber của channel này, handler nào được gọi? | Dispatcher |
| Mỗi consumer có nhận một bản sao không? | Channel semantics và dispatcher |
| Message được lưu chờ để nhận sau không? | Pollable channel/queue |

Không dùng nhiều subscriber trên DirectChannel để thay thế router. Nếu cần phân loại message theo `priority`, `tenantId` hoặc loại nghiệp vụ, hãy định tuyến rõ ràng tới các channel tương ứng.

## 13. Ví dụ: hai worker cùng subscribe một DirectChannel

Giả sử có hai worker có cùng trách nhiệm xử lý một loại đơn hàng. Chúng được đăng ký làm hai service activator trên cùng input channel:

~~~xml
<int:channel id="ordersWorkChannel">
    <int:dispatcher load-balancer="round-robin" failover="true"/>
</int:channel>

<int:service-activator input-channel="ordersWorkChannel"
                       ref="orderWorkerA"
                       method="process"
                       order="1"/>

<int:service-activator input-channel="ordersWorkChannel"
                       ref="orderWorkerB"
                       method="process"
                       order="2"/>
~~~

Với cấu hình này:

1. Message đầu tiên bắt đầu ở worker A.
2. Message kế tiếp bắt đầu ở worker B theo round-robin.
3. Nếu A ném exception, dispatcher có thể thử B cho chính message đó vì failover đang bật.
4. Nếu B cũng ném exception, dispatch thất bại và exception tổng hợp được phát ra.
5. Message tiếp theo tiếp tục theo lượt load balancing.

Worker A và B phải có khả năng xử lý thay thế nhau. Nếu A và B thực hiện hai nghiệp vụ khác nhau, hãy tách channel và dùng router hoặc publish-subscribe theo đúng ý nghĩa.

### Tắt failover khi lỗi phải được nhìn thấy ngay

Nếu chỉ muốn gọi đúng handler được chọn và để lỗi trả về caller trong flow đồng bộ, đặt:

~~~java
@Bean
DirectChannel ordersFailFastChannel() {
    DirectChannel channel = new DirectChannel();
    channel.setFailover(false);
    return channel;
}
~~~

Cách này tránh chuyển cùng message sang handler khác sau exception. Nó phù hợp khi các handler không phải bản thay thế hoặc khi việc fallback có thể tạo side effect trùng lặp.

## 14. Lỗi dispatch và cách quan sát

Khi dispatch không thành công, cần phân biệt lỗi ở cấp channel, dispatcher và handler.

| Triệu chứng | Nguyên nhân cần kiểm tra |
|---|---|
| `Dispatcher has no subscribers` hoặc `MessageDispatchingException` | Không có handler đăng ký vào channel tại thời điểm send |
| `AggregateMessageDeliveryException` | Các handler đã được thử đều ném exception |
| Chỉ một handler nhận message dù có nhiều endpoint | Channel có unicast semantics; dispatcher chọn một handler |
| Handler thay đổi theo từng message | Round-robin hoặc load-balancing strategy đang hoạt động |
| Luôn bắt đầu ở một handler | Load balancing bị tắt hoặc thứ tự cố định được cấu hình |
| Handler khác chạy sau khi handler đầu lỗi | Failover đang bật |
| Sender không nhìn thấy exception của handler | Có ranh giới bất đồng bộ như ExecutorChannel hoặc executor trong dispatcher |
| Một nghiệp vụ bị chạy hai lần | Failover sau partial side effect, retry hoặc redelivery; kiểm tra idempotency |

### Quy trình chẩn đoán

1. Xác định channel bean mà producer gửi vào.
2. Xác định channel là DirectChannel, ExecutorChannel, PublishSubscribeChannel hay QueueChannel.
3. Kiểm tra endpoint nào đã subscribe vào channel.
4. Kiểm tra số subscriber và lifecycle state của endpoint.
5. Với unicast channel, kiểm tra load-balancer, failover và thứ tự handler.
6. Xác định handler bắt đầu và handler tiếp theo bằng log có correlation ID.
7. Kiểm tra exception gốc và lỗi tổng hợp nếu mọi handler đều thất bại.
8. Nếu có executor, kiểm tra task rejection, worker thread và error channel.
9. Xác nhận message không bị side effect trùng khi failover hoặc retry.

Có thể bật log phù hợp cho Spring Integration và sử dụng Integration Graph/Actuator khi ứng dụng đã cấu hình management. Không nên chỉ dựa vào tên bean để suy ra endpoint đang active; kiểm tra trạng thái runtime và kết nối channel thực tế.

### Logging nên có gì?

Ở mức debug hoặc trace, nên ghi:

- Channel name.
- Message ID và correlation ID.
- Handler/endpoint ID được chọn.
- Thread name.
- Thời điểm dispatch bắt đầu và kết thúc.
- Handler có ném exception hay không.
- Failover có chuyển sang handler kế tiếp không.
- Dispatch hoàn tất, bị từ chối hay thất bại.

Không nên log toàn bộ payload nhạy cảm. Với production, cần cân nhắc sampling và tránh log mỗi message ở mức quá chi tiết nếu throughput cao.

## 15. Các nguyên tắc thiết kế khi có nhiều handler

- Chỉ đăng ký nhiều handler vào DirectChannel khi chúng có thể thay thế nhau hoặc có chính sách failover rõ ràng.
- Dùng PublishSubscribeChannel khi tất cả subscriber đều cần nhận message.
- Dùng router khi cần chọn channel theo dữ liệu nghiệp vụ.
- Dùng QueueChannel khi cần buffer và polling.
- Chọn round-robin nếu muốn phân phối lượt dispatch đơn giản; không coi nó là load balancing theo CPU hoặc latency.
- Tắt failover khi exception của handler phải kết thúc dispatch và không được chuyển sang worker khác.
- Chỉ dùng failover khi các handler thay thế nhau và side effect được bảo vệ bằng idempotency.
- Không nhầm failover với retry cùng handler hoặc broker redelivery.
- Với ExecutorChannel, quản lý lỗi sau dispatch qua error handling bất đồng bộ.
- Giữ strategy tùy chỉnh thread-safe, nhanh và không phụ thuộc vào mutable state thiếu đồng bộ.

Dispatcher là một phần nội bộ quan trọng của channel runtime. Khi hiểu đúng nó chọn handler nào, theo thứ tự nào và xử lý exception ra sao, có thể giải thích vì sao một message đi tới worker A thay vì B, vì sao handler thứ hai được gọi sau lỗi, hoặc vì sao một message chỉ tới một consumer dù có nhiều endpoint subscribe.

## Tài liệu tham khảo

- [Spring Integration — Configuring Message Channels](https://docs.spring.io/spring-integration/reference/channel/configuration.html) — cấu hình DirectChannel, load balancing, failover và PublishSubscribeChannel.
- [Spring Integration — Message Channel Implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html) — semantics của DirectChannel, ExecutorChannel, PublishSubscribeChannel và QueueChannel.
- [Spring Integration — UnicastingDispatcher API](https://docs.spring.io/spring-integration/api/org/springframework/integration/dispatcher/UnicastingDispatcher.html) — dispatcher unicast, handler selection, failover và lỗi dispatch.
- [Spring Integration — MessageDispatcher API](https://docs.spring.io/spring-integration/api/org/springframework/integration/dispatcher/MessageDispatcher.html) — abstraction dispatch message.
- [Spring Integration — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html) — ErrorMessage, errorChannel và định tuyến lỗi.

Một số cấu hình như `failoverStrategy`, load-balancer strategy và error handling có khác biệt theo phiên bản Spring Integration. Đặc biệt, predicate `failoverStrategy` được hỗ trợ từ Spring Integration 6.3; hãy đối chiếu tài liệu và API đúng dependency của ứng dụng.
