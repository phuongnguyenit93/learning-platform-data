# Phân biệt dispatcher với router

Trong Spring Integration, dispatcher và router đều liên quan đến việc message đi tới đâu, nhưng chúng làm việc ở hai tầng khác nhau. Dispatcher là cơ chế của channel để chuyển message tới subscriber đã đăng ký trên channel đó. Router là một endpoint xử lý message, đọc payload hoặc header rồi quyết định message cần được gửi tới channel nào.

Hiểu nhầm hai khái niệm này dễ dẫn đến cấu hình sai: mong `DirectChannel` tự định tuyến theo loại đơn hàng, hoặc mong router tự thực hiện load balancing giữa các handler cùng subscribe một channel. Muốn đọc đúng flow, hãy lần theo hai bước: router chọn output channel; dispatcher của output channel chuyển message tới subscriber.

## 1. Dispatcher làm việc ở tầng channel

Một channel có thể có một hoặc nhiều subscriber. Với các channel dạng subscribable, dispatcher nhận message được gửi vào channel và thực hiện chính sách chuyển giao tới subscriber.

Trong Spring Integration, hai implementation nội bộ thường gặp là:

- `UnicastingDispatcher`: chọn một subscriber để nhận message.
- `BroadcastingDispatcher`: gửi message tới các subscriber đã đăng ký.

Dispatcher không đọc quy tắc nghiệp vụ như loại đơn hàng, tenant hay giá trị header để quyết định output channel. Nó thực hiện chính sách dispatch của channel dựa trên danh sách subscriber và cấu hình của channel.

### DirectChannel và UnicastingDispatcher

`DirectChannel` dùng cơ chế unicast: mỗi lần gửi message được dispatch tới một subscriber. Nếu có nhiều subscriber, channel dùng load-balancing strategy; mặc định là round robin. Vì xử lý thường diễn ra trên thread gửi, `DirectChannel` phù hợp với flow đồng bộ và có thể truyền exception của handler về phía producer.

Có thể hình dung:

~~~mermaid
flowchart TD
    M[Message gửi vào DirectChannel] --> D[UnicastingDispatcher]
    D -->|Lần lượt chọn theo load balancing| A[Subscriber A]
    D -->|Lần kế tiếp| B[Subscriber B]
    D -->|Lần tiếp theo| C[Subscriber C]
~~~

Nếu channel có ba subscriber và dùng round robin, các message liên tiếp được phân phối lần lượt qua các subscriber. Dispatcher không kiểm tra subscriber nào xử lý loại message nào. Nếu cần phân luồng theo nội dung, hãy dùng router trước các channel đích.

`DirectChannel` hỗ trợ cấu hình load-balancing strategy và failover. Khi failover được bật, dispatcher có thể thử subscriber khác nếu subscriber được chọn ném exception. Cần hiểu rõ hệ quả: handler đầu tiên có thể đã thực hiện một phần side effect rồi mới lỗi; handler tiếp theo nhận cùng message có thể thực hiện side effect lần nữa. Vì vậy, các handler tham gia failover cần có tính idempotent hoặc phải có cơ chế chống xử lý trùng.

### PublishSubscribeChannel và BroadcastingDispatcher

`PublishSubscribeChannel` dùng broadcast: một message được gửi tới nhiều subscriber đã đăng ký. Đây là fan-out ở tầng channel, thường dùng khi cùng một sự kiện cần được xử lý bởi nhiều nhánh độc lập.

~~~mermaid
flowchart TD
    M[Message gửi vào PublishSubscribeChannel] --> D[BroadcastingDispatcher]
    D --> A[Subscriber A: audit]
    D --> B[Subscriber B: notification]
    D --> C[Subscriber C: analytics]
~~~

Nếu channel được cấu hình executor, việc dispatch tới subscriber có thể diễn ra bất đồng bộ. Nếu không, subscriber thường được gọi trên thread gửi. Tùy cấu hình `ignoreFailures`, lỗi từ một subscriber có thể ảnh hưởng việc dispatch tới các subscriber còn lại. Nếu cần tất cả nhánh độc lập tiếp tục dù một nhánh lỗi, hãy cấu hình và kiểm thử chính sách lỗi phù hợp.

## 2. Router làm việc ở tầng message flow

Router là một `MessageHandler` endpoint. Nó nhận message từ input channel, đánh giá payload hoặc header, rồi chọn một hay nhiều output channel để gửi message tiếp.

Một số router thường dùng:

| Router | Cách chọn output |
|---|---|
| `HeaderValueRouter` | Dựa trên giá trị của một message header |
| `PayloadTypeRouter` | Dựa trên kiểu payload |
| `RecipientListRouter` | Chọn một danh sách recipient/channel theo logic cấu hình |
| `ExceptionTypeRouter` | Chọn channel dựa trên kiểu exception trong error flow |
| Custom router | Dựa trên quy tắc nghiệp vụ riêng |

Router có thể chọn một channel hoặc nhiều channel tùy loại router và kết quả định tuyến. Nó không phải dispatcher của input channel: router là một endpoint subscriber trên input channel, còn dispatcher của input channel chịu trách nhiệm chuyển message tới endpoint router đó.

Ví dụ, `@Router` chọn output channel theo loại đơn hàng:

~~~java
@Component
public class OrderRouter {

    @Router(inputChannel = "orders.input")
    public String route(Order order) {
        return order.isPriority()
                ? "orders.priority"
                : "orders.standard";
    }
}
~~~

Ở đây router đọc dữ liệu nghiệp vụ `isPriority()` và trả về tên channel đích. Cần bảo đảm các channel `orders.priority` và `orders.standard` đã được khai báo hoặc có thể được giải quyết trong application context.

Các flow đích có thể được khai báo riêng:

~~~java
@Bean
IntegrationFlow priorityOrderFlow(OrderService orderService) {
    return IntegrationFlow.from("orders.priority")
            .handle(orderService, "processPriority")
            .get();
}

@Bean
IntegrationFlow standardOrderFlow(OrderService orderService) {
    return IntegrationFlow.from("orders.standard")
            .handle(orderService, "processStandard")
            .get();
}
~~~

Router quyết định channel nào nhận message. Sau khi message đến channel đích, dispatcher của channel đó tiếp tục quyết định subscriber nào thực thi.

## 3. Hai tầng dispatch trong cùng một flow

Hãy xét một flow có router gửi đơn hàng ưu tiên vào `orders.priority`, còn đơn hàng thường đi vào `orders.standard`. Nếu `orders.priority` là `DirectChannel` và có hai subscriber, dispatcher của channel sẽ chọn một subscriber theo load-balancing strategy.

~~~mermaid
flowchart TD
    IN[orders.input] --> D1[Input channel dispatcher]
    D1 --> R[Router endpoint]
    R -->|priority| P[orders.priority]
    R -->|standard| S[orders.standard]
    P --> DP[UnicastingDispatcher]
    DP --> P1[Priority handler A]
    DP --> P2[Priority handler B]
    S --> DS[Dispatcher của standard channel]
    DS --> SH[Standard handler]
~~~

Trong sơ đồ:

1. Dispatcher của `orders.input` chuyển message tới router endpoint đã subscribe.
2. Router đọc payload và chọn output channel.
3. Dispatcher của output channel chọn subscriber hoặc broadcast tùy loại channel.

Đây là hai quyết định độc lập. Nếu muốn chia theo nghiệp vụ, dùng router. Nếu muốn nhiều subscriber cùng nhận một sự kiện, dùng `PublishSubscribeChannel`. Nếu muốn phân phối lần lượt giữa các consumer cùng xử lý một loại message, dùng unicast channel có nhiều subscriber và cấu hình load balancing phù hợp.

## 4. Load balancing không phải routing

Load balancing phân phối message giữa các subscriber cùng một channel theo chiến lược dispatch. Routing chọn channel dựa trên nội dung message hoặc quy tắc định tuyến.

| Tiêu chí | Load balancing của dispatcher | Routing của router |
|---|---|---|
| Đầu vào | Danh sách subscriber của channel | Một message và dữ liệu của nó |
| Quyết định | Subscriber nào nhận message | Channel nào nhận message |
| Căn cứ | Strategy như round robin hoặc strategy tùy chỉnh | Payload, header, exception hoặc business rule |
| Kết quả | Một subscriber hoặc nhiều subscriber tùy loại dispatcher | Một hoặc nhiều output channel |
| Ví dụ | Chia message giữa các worker cùng subscribe `orders.work` | Đơn VIP sang `orders.priority`, đơn thường sang `orders.standard` |

Round robin không bảo đảm cùng một khách hàng luôn vào cùng worker, cũng không bảo đảm thứ tự hoàn tất. Nếu cần partition theo customer ID hoặc order ID, hãy định tuyến theo key hoặc dùng cơ chế partitioning có chủ đích.

## 5. UnicastingDispatcher và failover

`UnicastingDispatcher` chịu trách nhiệm chọn một subscriber cho mỗi lần dispatch. Với `DirectChannel`, chiến lược mặc định là round robin khi có nhiều subscriber. Có thể cấu hình load balancing strategy khác để phù hợp yêu cầu, nhưng chiến lược tùy chỉnh phải được kiểm tra về thread safety và tính công bằng.

Failover là chính sách xử lý khi subscriber được chọn không xử lý thành công. Khi bật, dispatcher có thể tiếp tục thử subscriber khác theo thứ tự dispatch. Điều này không tương đương retry bền vững: dispatcher không lưu message để thử lại sau khi JVM restart và cũng không đảm bảo chỉ chạy một lần.

Hãy phân biệt:

- **Failover subscriber:** thử subscriber khác trong cùng lần dispatch.
- **Retry advice:** gọi lại thao tác theo retry policy, thường có giới hạn số lần và backoff.
- **Broker redelivery:** broker giao lại message theo acknowledgment/transaction semantics.
- **Dead-letter/error flow:** chuyển message lỗi tới nơi xử lý riêng.

Không bật failover một cách máy móc nếu nhiều subscriber cùng thực hiện side effect. Nếu handler A ghi database thành công một phần rồi lỗi, handler B có thể nhận lại message và ghi trùng. Hãy dùng idempotency key, unique constraint hoặc phân chia trách nhiệm subscriber rõ ràng.

## 6. BroadcastingDispatcher và fan-out

`BroadcastingDispatcher` gửi một message tới các subscriber của `PublishSubscribeChannel`. Khác với router, broadcast không cần chọn một nhánh duy nhất dựa trên payload; mọi subscriber được cấu hình tham gia nhận message.

Một số cấu hình có thể ảnh hưởng hành vi:

- Executor: quyết định subscriber chạy đồng bộ hay được dispatch bất đồng bộ.
- `ignoreFailures`: quyết định cách xử lý exception từ subscriber khi broadcast.
- `applySequence`: có thể bổ sung sequence metadata cho message được gửi tới nhiều subscriber.
- `minSubscribers`: đặt số subscriber tối thiểu cần có để gửi được message trong các phiên bản hỗ trợ thuộc tính này.

Broadcast không tự tạo durability. Nếu subscriber không hoạt động hoặc message bị lỗi sau khi dispatch, channel không phải một event log để replay về sau. Nếu từng nhánh cần đảm bảo nhận độc lập, hãy cân nhắc broker/topic hoặc các queue riêng cho từng consumer.

## 7. Router không tìm được channel đích

Router cần giải quyết tên output channel thành channel thực tế. Lỗi định tuyến có thể xuất hiện khi:

- Không có channel mapping cho giá trị header/payload.
- Channel đích chưa được khai báo hoặc tên bị sai.
- Router không có default output channel trong trường hợp không tìm được mapping.
- Cấu hình yêu cầu channel resolution thành công nhưng không có bean tương ứng.

Khi thiết kế router, cần quyết định rõ message không khớp sẽ được xử lý thế nào: gửi vào default channel, chuyển sang error channel, bỏ qua có chủ đích hoặc phát sinh lỗi để upstream xử lý. Không để trường hợp unmatched trở thành hành vi ngầm khó quan sát.

Ví dụ về quy tắc fallback:

~~~java
@Router(inputChannel = "orders.input",
        defaultOutputChannel = "orders.unmatched")
public String route(Order order) {
    return switch (order.getType()) {
        case PRIORITY -> "orders.priority";
        case STANDARD -> "orders.standard";
        default -> null;
    };
}
~~~

Tên channel trong annotation và giá trị trả về phải phù hợp với channel bean trong application context. Hãy kiểm thử cả giá trị hợp lệ lẫn không khớp; đặc biệt kiểm tra router trả `null` có đi đúng default output channel theo cấu hình hay không.

## 8. Chọn channel và router theo mục tiêu

| Mục tiêu | Cơ chế phù hợp |
|---|---|
| Một trong nhiều handler cùng xử lý message, chia tải | `DirectChannel` với nhiều subscriber và load-balancing strategy |
| Gọi handler trên thread gửi, giữ call stack đồng bộ | `DirectChannel` |
| Chuyển xử lý sang worker executor | `ExecutorChannel` |
| Nhiều subscriber cùng nhận một message | `PublishSubscribeChannel` |
| Buffer message để consumer nhận sau | `QueueChannel` hoặc broker-backed channel |
| Chọn output theo header | `HeaderValueRouter` |
| Chọn output theo kiểu payload | `PayloadTypeRouter` |
| Chọn output theo nghiệp vụ tùy chỉnh | Custom router hoặc `@Router` |
| Gửi tới một tập recipient được xác định | `RecipientListRouter` hoặc publish-subscribe channel, tùy semantics |

Không dùng `PublishSubscribeChannel` chỉ để thay router nếu chỉ một nhánh cần xử lý. Ngược lại, không tạo nhiều router endpoint chỉ để broadcast cùng một sự kiện tới mọi subscriber khi một publish-subscribe channel đã thể hiện rõ ý định.

## 9. Quan sát dispatcher và router trong runtime

Khi message không đến đúng handler, hãy xác định message dừng ở tầng nào:

1. Message có được gửi vào input channel không?
2. Channel có subscriber và dispatcher có chọn được subscriber không?
3. Nếu subscriber là router, router có tính được output channel mong muốn không?
4. Output channel có tồn tại và có subscriber/consumer không?
5. Dispatcher của output channel có dispatch thành công không?
6. Handler có xử lý thành công hay phát sinh exception/error flow?

Log nên chứa channel/component name, message ID, Correlation ID, route key và output channel đã chọn. Tránh ghi toàn bộ payload nếu chứa dữ liệu nhạy cảm.

Các triệu chứng thường gặp:

| Triệu chứng | Khả năng cần kiểm tra |
|---|---|
| Message vào channel nhưng không thấy handler | Subscriber chưa đăng ký, endpoint chưa start hoặc channel không có consumer |
| Message luôn đến cùng một handler | Chỉ có một subscriber, load-balancing strategy hoặc topology không như dự kiến |
| Message bị xử lý bởi handler không đúng loại | Đang dùng load balancing thay vì router nghiệp vụ |
| Router không tìm thấy output | Thiếu mapping, sai tên channel hoặc thiếu default output channel |
| Một message chạy ở nhiều nhánh | `PublishSubscribeChannel` hoặc router trả nhiều recipient/channel |
| Side effect bị lặp sau exception | Failover subscriber, retry hoặc redelivery; kiểm tra idempotency |
| Một subscriber lỗi khiến nhánh khác không chạy | Kiểm tra `ignoreFailures` và semantics của BroadcastingDispatcher |

Message History và Integration Graph có thể hỗ trợ xác định các component/channel đã đi qua và topology đang được đăng ký. Tuy nhiên, graph chỉ mô tả cấu trúc runtime; log theo message ID/Correlation ID mới giúp xác định message cụ thể đã chọn nhánh nào.

## 10. Checklist thiết kế

- [ ] Xác định cần chọn subscriber hay chọn output channel.
- [ ] Dùng `DirectChannel`/unicast dispatcher cho một subscriber trong mỗi lần dispatch.
- [ ] Dùng `PublishSubscribeChannel`/broadcast dispatcher khi mọi subscriber cần nhận message.
- [ ] Dùng router khi quyết định phụ thuộc payload, header hoặc quy tắc nghiệp vụ.
- [ ] Không nhầm round robin với routing theo key hoặc tenant.
- [ ] Đánh giá failover và khả năng side effect bị thực hiện nhiều lần.
- [ ] Cấu hình default output/error path cho message không khớp.
- [ ] Kiểm tra channel đích có subscriber hoặc consumer đang hoạt động.
- [ ] Xác định executor và thread boundary khi dispatch bất đồng bộ.
- [ ] Ghi log route key, component/channel name và message ID để chẩn đoán.

Dispatcher và router bổ sung cho nhau. Router chọn nơi message cần tới dựa trên nội dung hoặc quy tắc nghiệp vụ; dispatcher của channel thực hiện việc chuyển giao tới subscriber theo chính sách channel. Khi tách rõ hai tầng này, ta có thể thiết kế routing, load balancing và fan-out chính xác, đồng thời chẩn đoán được lỗi xảy ra ở quyết định chọn nhánh hay ở bước dispatch.

## Tài liệu tham khảo

- [Spring Integration Reference: Message Channels](https://docs.spring.io/spring-integration/reference/channel.html)
- [Spring Integration Reference: Routers](https://docs.spring.io/spring-integration/reference/router.html)
- [Spring Integration API: DirectChannel](https://docs.spring.io/spring-integration/docs/6.4.x/api/org/springframework/integration/channel/DirectChannel.html)
- [Spring Integration API: PublishSubscribeChannel](https://docs.spring.io/spring-integration/docs/6.4.x/api/org/springframework/integration/channel/PublishSubscribeChannel.html)
- [Spring Integration API: AbstractMessageRouter](https://docs.spring.io/spring-integration/docs/6.4.x/api/org/springframework/integration/router/AbstractMessageRouter.html)
