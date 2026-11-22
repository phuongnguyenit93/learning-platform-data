# SubscribableChannel và subscription của consumer

Trong Spring Integration Runtime, message flow được ghép từ channel, endpoint và consumer. Channel quyết định cách message được chuyển tiếp; endpoint kết nối channel với một `MessageHandler`; consumer thực hiện công việc xử lý ở phía sau handler. Bài này tập trung vào `SubscribableChannel`: cơ chế đăng ký consumer, cách channel phân phối message và cách vòng đời endpoint quản lý subscription.

## 1. SubscribableChannel nằm ở đâu trong message flow?

`MessageChannel` là điểm gửi message trong Spring Integration. Producer gọi `send(message)` mà không cần biết thành phần nào sẽ xử lý message. Cách channel tiếp nhận consumer được thể hiện qua các interface chuyên biệt:

- `SubscribableChannel`: consumer đăng ký một `MessageHandler` với channel. Khi có message, channel chủ động dispatch message đến các handler đã đăng ký.
- `PollableChannel`: message được giữ trong channel để consumer lấy ra bằng thao tác receive. Một poller thường điều khiển nhịp lấy message.
- `MessageChannel`: interface nền cung cấp thao tác gửi message.

Với `SubscribableChannel`, consumer không liên tục hỏi channel xem có message mới hay chưa. Channel gọi handler khi producer gửi message. Đây là mô hình event-driven, phù hợp với luồng xử lý cần phản hồi ngay và không cần hàng đợi trung gian.

~~~mermaid
flowchart LR
    P[Producer] -->|send(Message)| C[SubscribableChannel]
    C -->|dispatch| E[Consumer endpoint]
    E --> H[MessageHandler]
    H --> S[Service hoặc ứng dụng]
~~~

Trong flow được khai báo bằng Java DSL, một bước như `handle(...)` tạo ra endpoint cùng handler. Khi endpoint được khởi động, endpoint đăng ký handler vào input channel. Vì vậy, subscription thường được framework quản lý theo vòng đời endpoint; ứng dụng không cần tự gọi `subscribe()` cho mỗi service activator.

## 2. Hai thành phần của subscription

Một subscription có hai phía:

**Channel** cung cấp hợp đồng đăng ký và hủy đăng ký:

~~~java
public interface SubscribableChannel extends MessageChannel {
    boolean subscribe(MessageHandler handler);
    boolean unsubscribe(MessageHandler handler);
}
~~~

**MessageHandler** là đối tượng nhận message:

~~~java
public interface MessageHandler {
    void handleMessage(Message<?> message);
}
~~~

Handler nhận toàn bộ `Message<?>`, gồm payload và headers. Payload là dữ liệu nghiệp vụ; headers mang metadata như message ID, timestamp, correlation ID, reply channel hoặc error channel.

Kết quả boolean của `subscribe` và `unsubscribe` cho biết thao tác đăng ký hoặc gỡ đăng ký có làm thay đổi danh sách handler hay không. Khi đăng ký thủ công, cần giữ lại đúng instance handler để có thể gỡ nó sau này. Tạo một lambda mới có nội dung giống lambda cũ không đảm bảo đó là cùng một handler instance.

Subscription không đồng nghĩa với việc channel lưu lịch sử message. Một handler đăng ký sau thời điểm message đã được gửi sẽ không tự nhận lại message cũ. Các channel kiểu subscribable thường dispatch trực tiếp; nếu cần đệm, lưu bền hoặc phát lại message, hãy chọn cơ chế queue, message store hoặc broker phù hợp.

## 3. Channel quyết định một consumer hay nhiều consumer nhận message

Cùng triển khai `SubscribableChannel`, nhưng các channel có chính sách dispatch khác nhau. Chọn đúng loại channel là quyết định quan trọng nhất khi nhiều endpoint cùng đăng ký vào một input channel.

| Channel | Cách phân phối | Đặc điểm runtime |
|---|---|---|
| `DirectChannel` | Chọn một subscriber cho mỗi message | Gọi handler đồng bộ trên thread gửi |
| `PublishSubscribeChannel` | Gửi message đến các subscriber | Mặc định xử lý đồng bộ; có thể cấu hình executor |
| `ExecutorChannel` | Chọn một subscriber cho mỗi message | Giao việc cho `TaskExecutor`, thường tách thread gửi và thread xử lý |

### 3.1 DirectChannel: các consumer cạnh tranh

`DirectChannel` phù hợp khi một message chỉ nên được xử lý bởi một consumer trong nhóm subscriber. Nếu có nhiều handler đăng ký, dispatcher chọn một handler cho mỗi lần gửi. Cấu hình mặc định dùng chiến lược load balancing dạng round-robin; cơ chế failover có thể cho phép thử handler khác khi handler được chọn gặp lỗi.

Ví dụ, hai endpoint cùng nghe channel `orders` sẽ hoạt động như nhóm consumer cạnh tranh. Một đơn hàng được chuyển đến một endpoint, không tự động được gửi cho cả hai.

~~~java
@Bean
SubscribableChannel orders() {
    return new DirectChannel();
}

@Bean
IntegrationFlow orderProcessing(
        @Qualifier("orders") SubscribableChannel orders,
        OrderHandler handler) {

    return IntegrationFlow.from(orders)
            .handle(handler)
            .get();
}
~~~

Nếu tạo thêm một flow khác cùng lấy `orders` làm input, các handler sẽ cùng đăng ký vào một `DirectChannel`. Khi đó cần xác định rõ mục tiêu là chia tải hay phát sự kiện cho nhiều nơi. Không nên dùng nhiều subscriber trên `DirectChannel` với giả định mọi subscriber đều nhận mọi message.

### 3.2 PublishSubscribeChannel: phát đến nhiều subscriber

`PublishSubscribeChannel` phù hợp với fan-out: một message cần được chuyển đến nhiều nhánh độc lập, chẳng hạn vừa ghi audit vừa gửi thông báo và cập nhật chỉ số.

~~~java
@Bean
SubscribableChannel orderEvents() {
    return new PublishSubscribeChannel();
}

@Bean
IntegrationFlow auditFlow(
        @Qualifier("orderEvents") SubscribableChannel events,
        AuditHandler handler) {

    return IntegrationFlow.from(events)
            .handle(handler)
            .get();
}

@Bean
IntegrationFlow notificationFlow(
        @Qualifier("orderEvents") SubscribableChannel events,
        NotificationHandler handler) {

    return IntegrationFlow.from(events)
            .handle(handler)
            .get();
}
~~~

Khi ứng dụng gửi một message vào `orderEvents`, cả hai endpoint đều là subscriber và đều nhận message. Với cấu hình mặc định không có executor, việc gọi các subscriber diễn ra đồng bộ trong quá trình dispatch. Nếu cấu hình executor, các nhánh có thể chạy bất đồng bộ; thứ tự hoàn tất giữa các nhánh khi đó không được đảm bảo.

Có thể cấu hình ngưỡng subscriber tối thiểu bằng `minSubscribers` để kiểm soát điều kiện channel xem việc dispatch là thành công. Vì vậy, khi kiểm tra giá trị trả về của `send()`, hãy xét loại channel và cấu hình của nó thay vì suy luận một quy tắc chung cho mọi subscribable channel.

### 3.3 ExecutorChannel: dispatch qua executor

`ExecutorChannel` vẫn chọn một subscriber cho mỗi message, nhưng ủy thác việc gọi handler cho `TaskExecutor`. Đây là lựa chọn khi cần tách thời gian xử lý khỏi thread gửi và cho phép nhiều message được xử lý trên các worker thread.

~~~java
@Bean
SubscribableChannel asyncOrders(TaskExecutor integrationExecutor) {
    return new ExecutorChannel(integrationExecutor);
}
~~~

Executor phải được cấu hình theo năng lực xử lý và chính sách từ chối task. Khi hàng đợi executor đầy hoặc executor đã dừng, việc gửi có thể thất bại hoặc phát sinh lỗi tùy chính sách thực thi. Bất đồng bộ cũng làm thay đổi ngữ nghĩa lỗi và transaction: thread gửi thường không thể nhận trực tiếp exception phát sinh sau khi task đã được chuyển sang worker thread.

## 4. Endpoint đăng ký và hủy subscription theo vòng đời

Trong Spring Integration, endpoint là thành phần runtime nối input channel với một message handler. Với input channel triển khai `SubscribableChannel`, endpoint hướng event-driven sẽ đăng ký handler khi endpoint bắt đầu chạy và hủy đăng ký khi endpoint dừng.

Trình tự điển hình trong một application context:

1. Spring tạo channel, flow và các endpoint tương ứng.
2. Application context khởi động các endpoint theo vòng đời quản lý của Spring.
3. Endpoint đăng ký handler vào input channel.
4. Producer gửi message; channel dispatch message theo chính sách của channel.
5. Khi endpoint dừng hoặc bị hủy, endpoint gỡ handler khỏi channel.
6. Khi endpoint được khởi động lại, subscription được thiết lập lại.

Với Java DSL, `IntegrationFlow` mô tả cấu trúc xử lý. Các endpoint do framework tạo ra mới là thành phần trực tiếp tham gia subscription. Các annotation như `@ServiceActivator(inputChannel = "...")` cũng tạo endpoint theo cùng nguyên tắc.

Không nên tự đăng ký thêm cùng một handler vào channel nếu endpoint đã quản lý subscription đó. Làm vậy có thể khiến handler nhận message nhiều lần hoặc khiến việc dừng endpoint không dọn được subscription thủ công.

### Flow được đăng ký động

Khi tạo flow trong lúc ứng dụng đang chạy, có thể dùng `IntegrationFlowContext` để đăng ký flow và nhận về một `IntegrationFlowRegistration`. Khi không còn cần flow, gọi `destroy()` trên registration để hủy flow runtime và giải phóng các endpoint, subscription thuộc flow đó.

~~~java
IntegrationFlowRegistration registration =
        flowContext.registration(dynamicFlow).register();

// Khi kết thúc vòng đời của flow:
registration.destroy();
~~~

Đối với flow khai báo như Spring bean thông thường, hãy để application context quản lý start/stop. Đối với flow đăng ký động, vòng đời của registration cần được quản lý rõ ràng; bỏ quên bước hủy có thể để lại endpoint vẫn nghe channel.

## 5. Subscription ảnh hưởng đến thread, transaction và lỗi như thế nào?

### Đồng bộ với DirectChannel

Với `DirectChannel`, handler chạy trên thread gọi `send()`. Lệnh gửi thường chỉ hoàn tất sau khi handler xử lý xong. Điều này tạo một call path dễ theo dõi và cho phép các bước đồng bộ tham gia cùng ngữ cảnh thread, bao gồm transaction gắn với thread nếu ứng dụng đã mở transaction phù hợp.

Đổi lại, thời gian xử lý của consumer làm tăng thời gian gửi của producer. Handler chậm có thể kéo dài request hoặc làm nghẽn thread gọi. Exception đồng bộ thường có thể truyền ngược về phía gọi `send()`, trừ khi có cơ chế xử lý lỗi bao quanh.

### Bất đồng bộ với ExecutorChannel hoặc PublishSubscribeChannel có executor

Khi dispatch qua executor, worker thread thực hiện handler sau khi task được chấp nhận. Transaction gắn với thread gửi không tự động truyền sang worker thread. Nếu cần transaction ở phía consumer, hãy thiết lập transaction cho chính bước xử lý trên worker thread.

Tương tự, producer có thể đã nhận kết quả gửi trước khi consumer xử lý xong. Exception xảy ra trong worker thread không thể được ném ngược về call stack của producer đã kết thúc. Hãy cấu hình error flow hoặc error channel phù hợp và theo dõi `ErrorMessage` để quan sát lỗi bất đồng bộ.

### Không nhầm subscription với độ bền message

Subscription chỉ xác định handler nhận message tại thời điểm dispatch. Nó không tự cung cấp:

- Lưu trữ bền vững khi ứng dụng dừng.
- Retry vô hạn hoặc bảo đảm xử lý đúng một lần.
- Phát lại message cho subscriber mới.
- Thứ tự toàn cục khi có nhiều producer hoặc xử lý song song.

Nếu cần các bảo đảm đó, phải thiết kế thêm retry, transaction, message store, persistent queue hoặc broker. Việc chọn `SubscribableChannel` tự nó không tạo ra các bảo đảm này.

## 6. Đăng ký handler thủ công

Trong một số tích hợp đặc biệt, có thể đăng ký trực tiếp một `MessageHandler`:

~~~java
SubscribableChannel channel = ...;

MessageHandler metricsHandler = message -> {
    Object payload = message.getPayload();
    // Ghi nhận metric hoặc quan sát metadata của message.
};

boolean added = channel.subscribe(metricsHandler);

// Khi thành phần quan sát dừng:
boolean removed = channel.unsubscribe(metricsHandler);
~~~

Cách này hữu ích khi một thành phần tự quản lý vòng đời đăng ký. Thành phần đó phải chịu trách nhiệm gỡ handler khi dừng, xử lý trường hợp đăng ký lặp và tránh giữ tham chiếu đến handler sau khi không còn sử dụng.

Trong flow nghiệp vụ thông thường, nên khai báo endpoint bằng Java DSL hoặc annotation để Spring Integration quản lý subscription cùng vòng đời endpoint. Dùng subscription thủ công khi thực sự cần kiểm soát trực tiếp việc gắn và tháo handler.

## 7. Chẩn đoán vấn đề subscription trong runtime

Khi message không đến consumer như dự kiến, kiểm tra theo thứ tự sau:

1. **Đúng channel chưa?** Xác minh producer gửi vào đúng bean/channel mà endpoint dùng làm input. Tên channel giống nhau trong cấu hình khác nhau có thể dẫn đến nối nhầm flow.
2. **Endpoint đã chạy chưa?** Kiểm tra trạng thái lifecycle của endpoint và thời điểm gửi message. Một endpoint chưa start thì chưa có subscription do endpoint quản lý.
3. **Channel có đúng chính sách dispatch không?** Nếu chỉ một trong nhiều handler nhận message trên `DirectChannel`, đó là hành vi chia tải. Nếu mọi handler phải nhận message, dùng `PublishSubscribeChannel`.
4. **Có ranh giới executor không?** Với channel bất đồng bộ, kiểm tra worker thread, kích thước pool, hàng đợi và chính sách từ chối task. Không kết luận consumer chưa chạy chỉ vì producer đã nhận kết quả gửi.
5. **Có lỗi ở handler không?** Với xử lý đồng bộ, xem exception trên call path gửi. Với xử lý bất đồng bộ, kiểm tra error channel/error flow và log của worker thread.
6. **Subscription có được dọn đúng không?** Nếu flow động đã kết thúc nhưng handler vẫn nhận message, kiểm tra registration đã được `destroy()` hay handler thủ công đã được `unsubscribe()` chưa.

Một số dấu hiệu thường gặp:

| Triệu chứng | Nguyên nhân cần kiểm tra |
|---|---|
| `send()` trả về `false` | Không có subscriber phù hợp, endpoint chưa start hoặc dispatcher không chấp nhận message |
| Chỉ một consumer nhận mỗi message | Channel đang dùng chính sách unicast như `DirectChannel` hoặc `ExecutorChannel` |
| Producer chậm bất thường | Handler đồng bộ mất nhiều thời gian hoặc consumer đang chặn thread gửi |
| Producer kết thúc nhưng xử lý còn tiếp tục | Message đã được chuyển sang executor |
| Handler nhận message lặp | Có nhiều endpoint/subscription ngoài dự kiến hoặc handler bị đăng ký thủ công thêm lần nữa |
| Consumer mới không nhận message cũ | SubscribableChannel không phải nơi lưu lịch sử để phát lại message |

Nếu ứng dụng bật Spring Boot Actuator và endpoint Integration Graph được cấu hình, đồ thị integration runtime có thể giúp kiểm tra quan hệ giữa channel và endpoint. Kết hợp đồ thị với log khởi động và log xử lý message để xác định endpoint nào đang nối vào channel.

## 8. Chọn channel theo yêu cầu xử lý

Trước khi thêm subscriber, hãy xác định ý nghĩa nghiệp vụ của message:

- Chọn `DirectChannel` khi một message chỉ cần một consumer xử lý và muốn luồng đồng bộ, dễ quan sát.
- Chọn `PublishSubscribeChannel` khi mọi nhánh đăng ký đều cần nhận cùng một sự kiện.
- Chọn `ExecutorChannel` khi một consumer xử lý mỗi message nhưng cần chuyển việc sang executor.
- Chọn `QueueChannel` hoặc một broker khi cần lưu message để consumer lấy sau, điều tiết tốc độ hoặc tách producer khỏi thời điểm xử lý.

Đừng dựa vào số lượng subscriber để suy ra hành vi. Chính sách dispatch của channel mới quyết định một message được gửi đến một consumer hay nhiều consumer.

## 9. Bài tập thực hành

1. Tạo một `DirectChannel` và một flow có `MessageHandler`; gửi ba message và xác nhận handler nhận đủ.
2. Đăng ký hai flow vào cùng `DirectChannel`; quan sát message được chia giữa các handler. Giải thích vì sao đây là competing consumers.
3. Đổi channel thành `PublishSubscribeChannel`; gửi lại message và xác nhận cả hai handler đều nhận được.
4. Chuyển sang `ExecutorChannel`; ghi log tên thread ở producer và handler để quan sát ranh giới bất đồng bộ.
5. Dừng endpoint rồi gửi message; quan sát kết quả dispatch. Khởi động endpoint lại và xác nhận subscription được thiết lập lại.
6. Đăng ký một handler thủ công, sau đó gọi `unsubscribe()`; kiểm tra handler không còn nhận message.

Sau bài tập, hãy tự trả lời: ai sở hữu subscription của một endpoint, channel nào chia tải, channel nào broadcast, và điều gì thay đổi khi dispatch chuyển sang executor? Những câu trả lời này giúp đọc và chẩn đoán message flow ở runtime một cách chính xác.
