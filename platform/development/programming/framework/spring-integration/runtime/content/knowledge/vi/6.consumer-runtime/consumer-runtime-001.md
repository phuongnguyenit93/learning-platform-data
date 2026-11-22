# Event-driven consumer nhận message từ SubscribableChannel

Trong Spring Integration, event-driven consumer nhận message ngay khi producer gửi message vào một `SubscribableChannel`. Consumer endpoint đăng ký một `MessageHandler` làm subscriber của channel; khi message đến, channel phân phối message đến handler theo semantics của loại channel. Cơ chế này không cần poller để hỏi channel xem có message mới hay chưa.

Endpoint đứng giữa channel và handler. Khi endpoint được start, nó đăng ký handler; khi endpoint stop, nó hủy đăng ký theo lifecycle. Vì vậy, việc bean handler tồn tại chưa đủ để chứng minh message đang được tiêu thụ. Cần kiểm tra endpoint đã chạy, subscriber đã được đăng ký và loại channel có phân phối message theo cách mong muốn hay không.

Sau bài này, bạn có thể:

- Giải thích `SubscribableChannel`, `MessageHandler` và `EventDrivenConsumer` phối hợp ra sao.
- Theo dõi vòng đời subscribe/unsubscribe của consumer endpoint.
- Phân biệt cách phân phối message của `DirectChannel`, `PublishSubscribeChannel` và `ExecutorChannel`.
- Xác định message chạy đồng bộ hay qua executor.
- Chẩn đoán tình huống không có subscriber, xử lý trùng hoặc lỗi trong handler.

## 1. SubscribableChannel là gì?

`SubscribableChannel` là abstraction của một channel cho phép message handler đăng ký nhận message. Contract cơ bản có hai thao tác:

```java
public interface SubscribableChannel extends MessageChannel {

    boolean subscribe(MessageHandler handler);

    boolean unsubscribe(MessageHandler handler);
}
```

`subscribe()` đăng ký handler làm subscriber; `unsubscribe()` gỡ đăng ký. Channel chịu trách nhiệm phân phối message đến các subscriber theo cách triển khai cụ thể.

Điểm khác biệt quan trọng là `SubscribableChannel` hướng đến phân phối theo sự kiện: khi producer gọi `send()`, channel thực hiện dispatch đến subscriber. Nó không phải abstraction để consumer gọi `receive()` định kỳ. Với `QueueChannel`, consumer thường dùng polling endpoint vì đây là `PollableChannel`; với `DirectChannel`, consumer thường là event-driven vì channel có thể gọi subscriber ngay trong thao tác gửi.

```text
Producer
   |
   | send(message)
   v
SubscribableChannel
   |
   | dispatch(message)
   v
MessageHandler
```

Channel không nhất thiết lưu message để consumer lấy sau. Với `DirectChannel`, dispatch thường diễn ra ngay trong thread gửi. Với channel dùng executor, công việc có thể được giao sang thread khác; khi đó hàng đợi task thuộc executor và chính sách của executor, không nên nhầm với một `QueueChannel`.

## 2. EventDrivenConsumer nối channel với handler

`EventDrivenConsumer` là consumer endpoint dành cho `SubscribableChannel`. Endpoint giữ channel và message handler, sau đó quản lý đăng ký handler trong vòng đời của endpoint.

```text
ApplicationContext tạo endpoint
             |
             v
EventDrivenConsumer (stopped)
             |
       lifecycle start
             |
             v
SubscribableChannel.subscribe(handler)
             |
             v
Channel dispatch message đến handler
             |
       lifecycle stop
             |
             v
SubscribableChannel.unsubscribe(handler)
```

Khi endpoint start, handler được đăng ký để channel có thể dispatch message đến nó. Khi endpoint stop, handler được gỡ khỏi channel. Bean endpoint và handler vẫn có thể tồn tại trong ApplicationContext; stop chỉ thay đổi trạng thái tiêu thụ message.

Trong ứng dụng thông thường, bạn hiếm khi tự tạo `EventDrivenConsumer`. Java DSL, XML hoặc annotation support tạo endpoint từ cấu hình. Ví dụ Java DSL:

```java
@Configuration
class OrderIntegrationConfiguration {

    @Bean
    MessageChannel orders() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow ordersFlow(OrderHandler handler) {
        return IntegrationFlow.from("orders")
                .handle(handler, "handle")
                .get();
    }
}

@Component
class OrderHandler {

    public void handle(Order order) {
        // Xử lý đơn hàng.
    }
}
```

Với flow trên, bước `.handle(...)` được chuyển thành handler và consumer endpoint nối handler đó với input channel `orders`. Vì `orders` là `DirectChannel`, endpoint là event-driven. Khi endpoint được start và đã subscribe, lệnh gửi vào channel có thể kích hoạt handler ngay.

Có thể khai báo consumer bằng annotation:

```java
@Component
class OrderListener {

    @ServiceActivator(inputChannel = "orders")
    public void handle(Order order) {
        // Xử lý đơn hàng.
    }
}
```

Annotation `@ServiceActivator` yêu cầu Spring Integration tạo endpoint gắn phương thức handler với channel có tên `orders`. Với channel là `SubscribableChannel`, endpoint hoạt động theo cơ chế event-driven. Không cần thêm poller chỉ để nhận message từ `DirectChannel`.

## 3. DirectChannel: một subscriber được chọn cho mỗi message

`DirectChannel` là loại `SubscribableChannel` phổ biến cho giao tiếp point-to-point. Nó sử dụng dispatcher để chọn một subscriber xử lý mỗi message. Nếu có nhiều subscriber, chúng thường đóng vai trò các consumer cạnh tranh: một message được chuyển đến một handler được chọn, thay vì broadcast cho tất cả.

```text
                       +--> Handler A
Producer --> Direct ---+--> Handler B   (chọn một subscriber)
                       +--> Handler C
```

Theo cấu hình mặc định thông dụng, `DirectChannel` sử dụng chiến lược load balancing để phân phối message giữa các subscriber. Có thể cấu hình chiến lược phân phối và chính sách failover. Failover là hành vi dispatch thử subscriber khác theo cấu hình khi subscriber được chọn gặp lỗi; nó không đồng nghĩa với cơ chế retry nghiệp vụ có backoff, giới hạn lần thử hoặc lưu trạng thái.

Một đặc điểm quan trọng của `DirectChannel` là handler thường chạy trong cùng thread gọi `send()`. Điều này có một số hệ quả:

- Producer thường chỉ tiếp tục sau khi lời gọi handler đồng bộ kết thúc.
- Exception từ handler có thể truyền ngược về thread gửi theo semantics của channel và cấu hình dispatch.
- Transaction gắn với thread gửi có thể bao quanh phần xử lý đồng bộ nếu transaction boundary được cấu hình phù hợp.
- Một handler chậm sẽ làm chậm producer đang gửi message.

Do đó, `DirectChannel` phù hợp khi cần lời gọi đồng bộ, flow ngắn hoặc muốn giữ xử lý trong cùng transaction/thread. Nó không tự tạo thread nền và không cung cấp hàng đợi để giữ message khi không có subscriber.

## 4. PublishSubscribeChannel: broadcast đến nhiều subscriber

`PublishSubscribeChannel` cũng là `SubscribableChannel`, nhưng semantics chính là publish/subscribe: một message được phát đến các subscriber đã đăng ký, thay vì chọn một consumer duy nhất.

```text
                         +--> Handler A
Producer --> Publish ---+--> Handler B
                         +--> Handler C
```

Mặc định, việc gọi các subscriber có thể diễn ra đồng bộ trong thread gửi. Channel cũng có thể được cấu hình với executor để dispatch bất đồng bộ. Khi dùng broadcast, cần xác định rõ mỗi subscriber có được phép thực hiện cùng một tác động nghiệp vụ hay không. Nếu ba handler cùng ghi một bản ghi hoặc cùng gửi một khoản thanh toán, broadcast có thể tạo tác động lặp ngoài ý muốn.

`PublishSubscribeChannel` hữu ích khi một sự kiện cần được nhiều nhánh độc lập quan sát, ví dụ cập nhật audit, gửi thông báo và cập nhật chỉ số. Mỗi subscriber nên có trách nhiệm riêng và xử lý idempotent khi message có thể được phát lại.

Không nên dùng `PublishSubscribeChannel` nếu ý định thực tế là chia tải giữa các worker và chỉ muốn một worker xử lý mỗi message; trong trường hợp đó, `DirectChannel` hoặc một cơ chế competing consumers phù hợp hơn.

## 5. ExecutorChannel: event-driven nhưng dispatch bất đồng bộ

`ExecutorChannel` là một `SubscribableChannel` sử dụng `TaskExecutor` để thực thi việc dispatch. Nó vẫn hoạt động theo sự kiện: producer gửi message và channel giao việc cho executor, không cần consumer polling. Tuy nhiên, handler thường chạy trên thread của executor thay vì thread gửi.

```text
Producer thread
      |
      | send(message)
      v
ExecutorChannel
      |
      | submit task
      v
TaskExecutor queue / worker threads
      |
      v
MessageHandler
```

Ví dụ cấu hình executor và channel:

```java
@Bean
ThreadPoolTaskExecutor integrationExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(8);
    executor.setQueueCapacity(100);
    executor.setThreadNamePrefix("orders-");
    return executor;
}

@Bean
MessageChannel asyncOrders(ThreadPoolTaskExecutor integrationExecutor) {
    return new ExecutorChannel(integrationExecutor);
}
```

Trong ví dụ, Spring quản lý lifecycle của `ThreadPoolTaskExecutor` như một bean. Cần cấu hình pool size, queue capacity, rejection policy và shutdown behavior phù hợp với tải thực tế. Queue task quá lớn có thể làm độ trễ tăng; queue quá nhỏ có thể khiến executor từ chối task khi quá tải.

Khi dùng executor, producer không nên giả định handler đã hoàn tất ngay sau khi `send()` trả về. Lỗi xảy ra trong worker thread cũng không thể được bắt như một exception đồng bộ trên call stack của producer. Cần cấu hình error handling phù hợp, quan sát log/metrics và xem xét error channel hoặc cơ chế xử lý lỗi dành cho tác vụ bất đồng bộ.

ExecutorChannel thường phân phối message đến một subscriber được chọn; nó không có nghĩa là broadcast. Nếu cần broadcast bất đồng bộ, hãy xem xét `PublishSubscribeChannel` có executor.

## 6. So sánh các SubscribableChannel thường gặp

| Channel | Cách phân phối | Thread xử lý thường gặp | Mục đích |
|---|---|---|---|
| `DirectChannel` | Chọn một subscriber cho mỗi message. | Thread gửi message. | Point-to-point, xử lý đồng bộ. |
| `PublishSubscribeChannel` | Phát message đến các subscriber. | Thread gửi theo mặc định; có thể cấu hình executor. | Fan-out sự kiện đến nhiều nhánh. |
| `ExecutorChannel` | Chọn subscriber để xử lý message. | Thread của `TaskExecutor`. | Dispatch event-driven bất đồng bộ. |

Điểm chung là cả ba đều nhận handler đăng ký qua `subscribe()`. Khác biệt nằm ở cách dispatch, số subscriber được gọi và thread thực thi. Chọn channel theo semantics nghiệp vụ và yêu cầu vận hành, không chỉ theo tên gọi.

## 7. Vòng đời subscriber và thời điểm gửi message

Một lỗi thường gặp là producer gửi message trước khi consumer endpoint đã start. Với event-driven consumer, channel chỉ dispatch đến những subscriber đã đăng ký tại thời điểm gửi. Nếu endpoint chưa start, đã stop hoặc đăng ký thất bại, message có thể không được xử lý bởi endpoint mong đợi.

Hãy phân biệt các trạng thái:

| Trạng thái | Ý nghĩa |
|---|---|
| Handler bean tồn tại | Phương thức xử lý đã được Spring tạo thành bean. |
| Endpoint bean tồn tại | Spring đã tạo consumer endpoint và wiring liên quan. |
| Endpoint running | Lifecycle của endpoint đang ở trạng thái chạy. |
| Handler đã subscribe | Channel đã đăng ký handler để nhận message. |
| Message đã được xử lý | Handler thực sự đã nhận và hoàn tất xử lý message cụ thể. |

`isRunning()` hữu ích nhưng không thay thế kiểm tra topology, subscriber và kết quả xử lý. Trong vận hành, cần xác nhận endpoint đúng input channel, trạng thái lifecycle và log/metrics ở handler.

Khi endpoint stop, handler được unsubscribe theo lifecycle. Nếu dùng `DirectChannel`, channel không giữ message chờ endpoint start lại. Nếu producer cần lưu message trong lúc consumer dừng, hãy dùng một channel có khả năng lưu trữ hoặc broker phù hợp thay vì kỳ vọng `SubscribableChannel` hoạt động như queue.

## 8. Kết quả send và trường hợp không có subscriber

`MessageChannel.send()` trả về boolean để thể hiện kết quả gửi theo semantics của channel. Producer cần xem xét kết quả này, nhất là khi channel có thể không có subscriber hoặc dispatch bị từ chối.

```java
void sendOrder(MessageChannel orders, Order order) {
    Message<Order> message = MessageBuilder.withPayload(order).build();

    boolean sent = orders.send(message);
    if (!sent) {
        log.warn("Order message was not dispatched: orderId={}", order.getId());
    }
}
```

Đoạn code minh họa kiểm tra kết quả gửi. Cách channel xử lý trường hợp không có subscriber, timeout hoặc lỗi dispatch còn phụ thuộc loại channel, cấu hình và phiên bản. Không nên giả định mọi lần gửi không thành công đều trả về `false`; một số lỗi có thể được ném thành exception.

Với `DirectChannel`, không có hàng đợi để giữ message khi không có consumer. Với `PublishSubscribeChannel`, số subscriber tối thiểu và hành vi khi thiếu subscriber có thể được cấu hình. Với `ExecutorChannel`, task có thể bị từ chối nếu executor quá tải. Những trường hợp này cần được phân biệt khi chẩn đoán.

## 9. Lỗi trong handler và error handling

Với dispatch đồng bộ như `DirectChannel` mặc định, exception trong handler thường nằm trên call stack gửi message. Producer hoặc upstream endpoint có thể quan sát lỗi theo semantics dispatch và cơ chế error handling đang cấu hình.

Với dispatch bất đồng bộ qua `ExecutorChannel` hoặc `PublishSubscribeChannel` có executor, producer có thể đã tiếp tục trước khi handler hoàn tất. Exception trong worker thread không thể được xử lý bằng một `try/catch` quanh lệnh `send()` như lỗi đồng bộ. Hãy cấu hình error handling cho executor/endpoint và error channel theo kiến trúc ứng dụng.

Khi xử lý lỗi, phân biệt các cơ chế:

- **Exception propagation:** lỗi đồng bộ được truyền ngược qua call stack.
- **Error channel:** nơi message lỗi có thể được chuyển đến để xử lý tập trung khi integration flow được cấu hình tương ứng.
- **Retry:** thử lại xử lý theo policy, thường có giới hạn và có thể có backoff.
- **Dead-letter hoặc recovery flow:** lưu/chuyển message không xử lý được để điều tra hoặc xử lý lại.

Không coi việc có nhiều subscriber trên `DirectChannel` là retry policy. Failover dispatch (nếu được cấu hình) chọn subscriber khác theo quy tắc của dispatcher; retry nghiệp vụ cần quản lý số lần thử, loại lỗi có thể thử lại và hậu quả lặp tác động.

## 10. Threading, transaction và thứ tự xử lý

Với `DirectChannel`, handler thường chạy cùng thread gửi. Nếu producer đang trong transaction và handler tham gia cùng transaction manager/boundary, phần xử lý đồng bộ có thể cùng transaction. Đây là một lợi thế khi cần kết hợp gửi message với cập nhật dữ liệu trong cùng tiến trình, nhưng transaction boundary phải được cấu hình đúng.

Với `ExecutorChannel`, việc xử lý chuyển sang thread khác. Transaction thread-bound ở producer không tự động lan sang worker thread. Nếu cần transaction ở consumer, hãy đặt transaction boundary tại consumer/handler hoặc poller phù hợp; không giả định transaction của thread gửi bao trùm tác vụ bất đồng bộ.

Thứ tự xử lý cũng phụ thuộc channel và executor. `DirectChannel` gọi handler đồng bộ theo từng lần dispatch; nhiều producer thread vẫn có thể gửi đồng thời. Với executor pool nhiều thread, các message có thể hoàn tất theo thứ tự khác thứ tự gửi. Nếu nghiệp vụ yêu cầu tuần tự theo key, hãy chọn cơ chế partition/serialization phù hợp và không dựa vào việc chỉ dùng một `SubscribableChannel`.

## 11. Chẩn đoán event-driven consumer không nhận message

Khi message không đến handler, kiểm tra theo trình tự:

1. **Kiểm tra channel type.** Input có phải `SubscribableChannel` không? Nếu là `QueueChannel`, consumer cần polling endpoint.
2. **Kiểm tra endpoint.** Endpoint có tồn tại và `isRunning()` không? Có bị `autoStartup=false` hoặc đã stop không?
3. **Kiểm tra subscription.** Handler đã được đăng ký với đúng channel chưa? Tên channel trong DSL/annotation có khớp bean không?
4. **Kiểm tra dispatch semantics.** Direct chọn subscriber, PublishSubscribe broadcast, ExecutorChannel giao task cho executor.
5. **Kiểm tra kết quả send.** Producer có nhận `false`, timeout hoặc exception không?
6. **Kiểm tra thread và executor.** Với async channel, pool có cạn thread, task queue có đầy hoặc có rejected execution không?
7. **Kiểm tra lỗi handler.** Đọc log, error channel, retry và downstream dependency.

| Triệu chứng | Khả năng cần kiểm tra |
|---|---|
| Handler không được gọi, send trả về false | Chưa có subscriber hoặc endpoint chưa start. |
| Handler khác được gọi thay vì handler dự kiến | Nhiều subscriber trên DirectChannel và dispatcher chọn subscriber khác. |
| Nhiều handler cùng nhận một message | Đang dùng PublishSubscribeChannel hoặc có nhiều nhánh fan-out. |
| Producer không thấy lỗi nhưng handler lỗi | Dispatch bất đồng bộ; kiểm tra error handling của worker. |
| Độ trễ tăng và task queue tăng | Executor thiếu năng lực xử lý hoặc handler bị chậm. |
| Message không được giữ khi consumer stop | Channel là SubscribableChannel không có queue lưu message. |

## 12. Tự kiểm tra

**Tình huống:** Một flow dùng `DirectChannel` có hai consumer endpoint đăng ký cùng channel. Producer gửi một message nhưng chỉ một handler được gọi. Nhóm phát triển mong cả hai handler cùng nhận message.

1. Vì sao chỉ một handler được gọi?
2. Nên dùng loại channel nào nếu muốn broadcast?
3. Nếu chuyển sang `ExecutorChannel`, điều gì thay đổi về thread và error handling?
4. Nếu endpoint chưa start khi producer gửi message, channel có tự giữ message chờ endpoint không?

**Gợi ý trả lời:** (1) `DirectChannel` chọn một subscriber để xử lý mỗi message. (2) Dùng `PublishSubscribeChannel` nếu cần phát đến tất cả subscriber. (3) Handler chạy trên executor thread; producer có thể tiếp tục trước khi xử lý hoàn tất và cần error handling cho tác vụ bất đồng bộ. (4) Không; `SubscribableChannel` không phải queue. Cần channel/broker có lưu trữ nếu muốn giữ message.

**Bài tập thực hành:** Tạo ba flow nhận message từ cùng một channel, lần lượt dùng `DirectChannel`, `PublishSubscribeChannel` và `ExecutorChannel`. Đăng ký hai handler, gửi nhiều message và ghi lại handler nào được gọi, thread name, thứ tự hoàn tất và cách exception được quan sát. Dừng một endpoint rồi gửi tiếp message để xác minh tác động của unsubscribe.

## Tài liệu tham khảo

- [Spring Integration Reference — Message Channels](https://docs.spring.io/spring-integration/reference/channel.html)
- [Spring Integration Reference — Event-driven Consumer Endpoint](https://docs.spring.io/spring-integration/reference/endpoint.html)
- [Spring Integration Javadoc — SubscribableChannel](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/SubscribableChannel.html)
- [Spring Integration Javadoc — EventDrivenConsumer](https://docs.spring.io/spring-integration/api/org/springframework/integration/endpoint/EventDrivenConsumer.html)
- [Spring Integration Javadoc — DirectChannel](https://docs.spring.io/spring-integration/api/org/springframework/integration/channel/DirectChannel.html)
