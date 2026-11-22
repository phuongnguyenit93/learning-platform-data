# BroadcastingDispatcher phát đến nhiều handler

Trong Spring Integration, một message có thể cần được xử lý bởi nhiều thành phần độc lập: lưu audit, cập nhật metric, gửi thông báo, đồng bộ cache hoặc kích hoạt một quy trình phụ. Với kiểu xử lý fan-out này, `PublishSubscribeChannel` cho phép nhiều handler đăng ký cùng một channel. Dispatcher đứng sau channel sẽ phát message đến các subscriber đã đăng ký.

`BroadcastingDispatcher` là thành phần thực hiện việc phát message đến nhiều handler trong `PublishSubscribeChannel`. Điểm quan trọng là nó có semantics khác `UnicastingDispatcher`: broadcasting hướng đến tất cả subscriber phù hợp, còn unicasting chọn một handler cho mỗi lần dispatch. Hiểu rõ cách phát, cách xử lý lỗi và việc có dùng executor hay không giúp thiết kế flow fan-out mà không nhầm lẫn giữa gửi thành công, xử lý hoàn tất và bảo đảm mọi nhánh đều thành công.

## 1. BroadcastingDispatcher nằm ở đâu?

`PublishSubscribeChannel` là một `SubscribableChannel`. Các endpoint hoặc handler đăng ký làm subscriber. Khi producer gửi một message vào channel, `BroadcastingDispatcher` duyệt các subscriber và dispatch message đến từng handler.

```text
                         +--> AuditHandler
                         |
Producer --> PublishSubscribeChannel --> NotificationHandler
                         |
                         +--> MetricsHandler
                         |
                         +--> CacheUpdateHandler
```

Các subscriber nhận cùng một sự kiện đầu vào để thực hiện các công việc khác nhau. Producer chỉ cần gửi một message; channel chịu trách nhiệm phân phối message đến những handler đã đăng ký.

Một cấu hình đơn giản:

```java
@Bean
public PublishSubscribeChannel orderEvents() {
    return new PublishSubscribeChannel();
}

@Component
public class OrderEventHandlers {

    @ServiceActivator(inputChannel = "orderEvents")
    public void writeAudit(OrderCreated event) {
        // Lưu dấu vết kiểm toán.
    }

    @ServiceActivator(inputChannel = "orderEvents")
    public void updateMetrics(OrderCreated event) {
        // Cập nhật số liệu đơn hàng.
    }

    @ServiceActivator(inputChannel = "orderEvents")
    public void notifyCustomer(OrderCreated event) {
        // Gửi thông báo cho khách hàng.
    }
}
```

Khi `orderEvents` nhận message, các service activator cùng subscribe channel đều là đích dispatch. Mỗi handler chịu trách nhiệm cho một nhánh công việc.

## 2. Broadcasting khác Unicasting

Hai dispatcher giải quyết hai kiểu phân phối khác nhau:

| Đặc điểm | BroadcastingDispatcher | UnicastingDispatcher |
|---|---|---|
| Channel thường dùng | `PublishSubscribeChannel` | `DirectChannel` |
| Số handler được gọi | Tất cả subscriber được chọn để dispatch | Một handler cho mỗi lần dispatch |
| Mục đích | Fan-out một sự kiện cho nhiều nhánh | Chọn một consumer xử lý message |
| Cấu hình liên quan | `applySequence`, `ignoreFailures`, `minSubscribers` | Load balancing, failover |
| Kết quả nghiệp vụ | Nhiều nhánh có thể tạo side effect riêng | Một nhánh được chọn thực hiện công việc |

Ví dụ, khi một đơn hàng được tạo:

- Nếu audit, notification và metrics đều cần nhận sự kiện, dùng publish-subscribe.
- Nếu có nhiều worker cùng xử lý các đơn hàng và mỗi đơn chỉ cần một worker nhận, dùng unicast với channel phù hợp.

Không dùng `PublishSubscribeChannel` để thay thế load balancing. Khi broadcast, mỗi subscriber được gọi; nếu có năm worker đăng ký, một message có thể kích hoạt cả năm worker. Điều này khác với việc phân phối năm message cho năm worker theo kiểu competing consumers.

## 3. Subscriber được đăng ký và gỡ như thế nào?

Subscriber thường được đăng ký khi endpoint được khởi tạo trong `ApplicationContext`. Ví dụ `@ServiceActivator(inputChannel = "orderEvents")` tạo endpoint đăng ký handler vào channel. Với Java DSL, flow bắt đầu từ một `PublishSubscribeChannel` cũng đăng ký endpoint làm subscriber.

```java
@Bean
public IntegrationFlow auditFlow(PublishSubscribeChannel orderEvents,
                                 AuditService auditService) {
    return IntegrationFlow.from(orderEvents)
        .handle(auditService, "record")
        .get();
}

@Bean
public IntegrationFlow notificationFlow(PublishSubscribeChannel orderEvents,
                                         NotificationService notifications) {
    return IntegrationFlow.from(orderEvents)
        .handle(notifications, "send")
        .get();
}
```

Hai flow cùng subscribe một channel nên mỗi message được dispatch đến cả hai nhánh. Khi endpoint dừng hoặc flow được gỡ khỏi context, subscriber tương ứng được unregister theo lifecycle của endpoint.

Với flow động được quản lý qua `IntegrationFlowContext`, việc đăng ký và remove flow làm thay đổi danh sách subscriber trong runtime. Nếu một subscriber được thêm hoặc gỡ trong lúc hệ thống đang có tải, message tiếp theo được dispatch theo danh sách subscriber tại thời điểm dispatch. Không nên giả định một subscriber đã bị remove vẫn nhận message mới, hoặc một subscriber vừa được thêm sẽ nhận lại những message đã gửi trước đó.

## 4. Dispatch đồng bộ khi không cấu hình Executor

`PublishSubscribeChannel` có thể hoạt động mà không cần executor. Khi đó, dispatcher gọi các handler đồng bộ trên thread gửi message.

```java
@Bean
public PublishSubscribeChannel synchronousEvents() {
    PublishSubscribeChannel channel = new PublishSubscribeChannel();
    channel.setApplySequence(true);
    return channel;
}
```

Với dispatch đồng bộ:

1. Producer gọi `send()`.
2. Channel gọi lần lượt các subscriber.
3. Mỗi handler chạy trên thread gọi `send()`.
4. Lời gọi gửi chỉ hoàn tất sau khi quá trình dispatch đồng bộ kết thúc hoặc phát sinh lỗi.

Ví dụ producer gọi channel từ một service:

```java
Message<OrderCreated> message = MessageBuilder
    .withPayload(new OrderCreated("ORD-1001"))
    .build();

boolean accepted = synchronousEvents.send(message);
```

Nếu một handler chạy lâu, producer cũng phải chờ. Đây có thể là lựa chọn phù hợp khi muốn giữ flow đơn giản và cần biết lỗi đồng bộ ngay trong lời gọi gửi. Tuy nhiên, fan-out có nhiều nhánh blocking có thể làm tăng latency của producer.

Thứ tự gọi handler phụ thuộc thứ tự subscriber mà dispatcher quản lý và metadata ordering của endpoint. Có thể dùng `@Order` hoặc cơ chế order phù hợp khi cần sắp xếp subscriber đồng bộ, nhưng không nên dùng thứ tự gọi như một cơ chế điều phối nghiệp vụ. Nếu một nhánh bắt buộc chạy sau kết quả của nhánh khác, hãy mô hình hóa quan hệ đó thành các bước tuần tự trong flow.

## 5. Dispatch bất đồng bộ bằng Executor

Có thể truyền `Executor` vào `PublishSubscribeChannel` để dispatcher giao việc gọi subscriber cho executor:

```java
@Bean("fanoutExecutor")
public ThreadPoolTaskExecutor fanoutExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(12);
    executor.setQueueCapacity(300);
    executor.setThreadNamePrefix("fanout-worker-");
    return executor;
}

@Bean
public PublishSubscribeChannel asynchronousEvents(
        @Qualifier("fanoutExecutor") TaskExecutor executor) {
    return new PublishSubscribeChannel(executor);
}
```

Trong cấu hình này, channel gửi các tác vụ dispatch handler sang executor. Producer thường chỉ chờ việc dispatch được submit theo khả năng của executor, không chờ tất cả handler hoàn tất. Mỗi handler có thể chạy trên worker thread khác nhau.

Hệ quả quan trọng:

- `send()` trả về không đồng nghĩa mọi subscriber đã xử lý xong.
- Thời gian hoàn tất của các nhánh có thể khác nhau.
- Exception trong worker thread không thể mặc định truyền về caller ban đầu.
- Queue của executor có thể tăng nếu message đến nhanh hơn tốc độ xử lý.
- Cần cấu hình error handling và giám sát cho các tác vụ bất đồng bộ.

Executor giúp tách latency của producer khỏi thời gian xử lý các subscriber, nhưng cũng làm tăng độ phức tạp về concurrency, lỗi và shutdown. Hãy dùng queue có giới hạn, timeout cho I/O và thread prefix riêng để dễ theo dõi.

## 6. Cấu hình thứ tự và sequence headers

Khi broadcast một message đến nhiều nhánh rồi muốn gom kết quả bằng `Aggregator`, các nhánh cần thông tin nhận diện nhóm và thứ tự message. `PublishSubscribeChannel` hỗ trợ `applySequence` để thêm sequence headers vào các message được phát.

```java
@Bean
public PublishSubscribeChannel orderEventsForAggregation() {
    PublishSubscribeChannel channel = new PublishSubscribeChannel();
    channel.setApplySequence(true);
    return channel;
}
```

Khi bật `applySequence`, message gửi đến các subscriber được bổ sung metadata sequence, bao gồm:

- `correlationId`: thông tin liên kết các message trong cùng nhóm.
- `sequenceNumber`: vị trí của message trong nhóm.
- `sequenceSize`: số message dự kiến trong nhóm broadcast.

Các header này hữu ích khi các nhánh biến đổi hoặc tạo reply rồi đưa kết quả đến aggregator. `Aggregator` có thể dùng correlation strategy để nhóm message và release strategy để quyết định khi nào nhóm đã đủ.

Ví dụ flow khái niệm:

```text
OrderCreated
     |
     v
PublishSubscribeChannel (applySequence=true)
     |                         |
     v                         v
Validate branch            Price branch
     |                         |
     +------------+------------+
                  |
                  v
              Aggregator
                  |
                  v
             OrderSummary
```

Không bật `applySequence` nếu các subscriber chỉ thực hiện side effect độc lập và không cần gom kết quả. Nếu một nhánh có thể không tạo reply hoặc thất bại, aggregator cần timeout/release strategy phù hợp để không chờ vô hạn.

## 7. minSubscribers và requireSubscribers

Broadcasting có thể cần một số lượng subscriber tối thiểu để message được xem là dispatch hợp lệ. `PublishSubscribeChannel` cung cấp cấu hình `minSubscribers` và `requireSubscribers` cho mục đích này.

- `minSubscribers` đặt số subscriber tối thiểu cần có để dispatch được chấp nhận. Nếu số subscriber thấp hơn mức yêu cầu, việc dispatch có thể thất bại bằng `MessageDispatchingException`.
- `requireSubscribers` yêu cầu phải có subscriber. Cấu hình này giúp phát hiện trường hợp message được gửi vào channel không có endpoint nào nhận.

Ví dụ yêu cầu tối thiểu hai subscriber:

```java
@Bean
public PublishSubscribeChannel criticalEvents() {
    PublishSubscribeChannel channel = new PublishSubscribeChannel();
    channel.setMinSubscribers(2);
    channel.setRequireSubscribers(true);
    return channel;
}
```

Các tùy chọn này kiểm tra số lượng subscriber tại thời điểm dispatch. Chúng không chứng minh các handler đã xử lý thành công hoặc side effect đã commit. Nếu cần một nhánh cụ thể luôn hiện diện, kiểm tra topology và health của endpoint đó theo tên/định danh nghiệp vụ, thay vì chỉ dựa vào tổng số subscriber.

## 8. ignoreFailures và lỗi của một subscriber

Trong dispatch đồng bộ, một handler có thể ném exception. `BroadcastingDispatcher` hỗ trợ chính sách `ignoreFailures` để quyết định dispatcher có tiếp tục gọi các subscriber còn lại khi một subscriber lỗi hay không.

```java
@Bean
public PublishSubscribeChannel tolerantEvents() {
    PublishSubscribeChannel channel = new PublishSubscribeChannel();
    channel.setIgnoreFailures(true);
    return channel;
}
```

Khi `ignoreFailures` bật, lỗi của một subscriber được bỏ qua cho mục đích tiếp tục broadcast và dispatcher tiếp tục xử lý các subscriber còn lại. Điều này phù hợp khi các nhánh độc lập và một nhánh lỗi không nên ngăn những nhánh khác nhận sự kiện.

Khi `ignoreFailures` tắt, exception từ subscriber có thể làm dispatch đồng bộ thất bại và ngăn các subscriber tiếp theo được gọi. Producer có thể quan sát exception qua lời gọi gửi. Vì vậy, nếu muốn tất cả nhánh được thử ngay cả khi có nhánh lỗi, hãy cân nhắc `ignoreFailures` cùng cơ chế log/metric riêng cho từng nhánh.

Không nên bật `ignoreFailures` rồi bỏ qua quan sát lỗi. Nếu lỗi bị bỏ qua mà không có log, metric hoặc error flow, một nhánh có thể ngừng hoạt động trong thời gian dài mà không ai nhận ra.

### ignoreFailures không tạo rollback chung

Broadcast không phải một transaction phân tán bao trùm tất cả subscriber. Nếu nhánh audit đã ghi dữ liệu rồi nhánh notification thất bại, việc dispatch thất bại không tự động rollback bản ghi audit. Tương tự, `ignoreFailures=true` chỉ cho phép các nhánh khác tiếp tục; nó không biến kết quả của các nhánh thành một giao dịch nguyên tử.

Nếu nghiệp vụ yêu cầu tất cả side effect phải thành công hoặc cùng rollback, cần thiết kế một quy trình điều phối có transaction/outbox/saga phù hợp. Không dùng `PublishSubscribeChannel` trong bộ nhớ như một cam kết atomic fan-out.

## 9. Exception khi dùng Executor

Khi channel dùng executor, handler có thể chạy sau khi lời gọi `send()` đã kết thúc. Vì vậy, exception từ handler thường không truyền về thread gửi. Cần xác định error handler được cấu hình cho cơ chế thực thi bất đồng bộ và error channel mà message sẽ được chuyển đến.

Với Spring Integration, lỗi gắn với message có thể được công bố thành `ErrorMessage` tới error channel phù hợp, ví dụ error channel trong header `MessageHeaders.ERROR_CHANNEL` hoặc global `errorChannel`, tùy cấu hình và đường thực thi. Khi điều tra, cần kiểm tra cả exception trong worker, error handler của executor và error flow.

Không nên dựa vào `ignoreFailures` như một cơ chế thay thế error handling bất đồng bộ. Nó không đảm bảo producer nhận được kết quả xử lý của worker, cũng không thay thế việc theo dõi lỗi từng nhánh.

Một handler bất đồng bộ nên ghi nhận tối thiểu tên nhánh, message ID, correlation ID, loại exception và cause gốc. Nếu cần retry, hãy cấu hình retry ở endpoint/handler thích hợp. Nếu cần phát lại message, lưu dữ liệu cần thiết trước khi kết thúc đường xử lý lỗi.

## 10. Một message, nhiều subscriber và payload mutable

Spring `Message` có envelope bất biến, nhưng payload không mặc định bất biến. Khi broadcast, nhiều handler có thể cùng nhìn thấy một payload object. Nếu payload là object mutable và một handler sửa nó trong khi handler khác đang đọc, kết quả có thể phụ thuộc timing và tạo race condition.

Ví dụ rủi ro:

```java
public void addFlag(OrderEvent event) {
    event.getAttributes().put("processed", true);
}

public void publishAudit(OrderEvent event) {
    // Có thể nhìn thấy hoặc không nhìn thấy thay đổi tùy thứ tự/thread.
}
```

Với dispatch đồng bộ, thay đổi có thể quan sát được bởi handler chạy sau. Với executor, các handler có thể truy cập cùng object đồng thời. Hướng thiết kế an toàn:

- Dùng payload immutable, ví dụ record hoặc object chỉ đọc.
- Nếu mỗi nhánh cần biến đổi dữ liệu, tạo bản sao riêng ở nhánh đó.
- Không dùng payload làm vùng chia sẻ để trao đổi kết quả giữa subscriber.
- Đưa kết quả của từng nhánh thành message reply riêng và gom bằng aggregator nếu cần.

## 11. Thứ tự, concurrency và hiệu năng

Khi dispatch đồng bộ, các subscriber được gọi tuần tự theo thứ tự dispatcher quản lý. Một subscriber xử lý chậm có thể kéo dài thời gian gửi tổng thể. Khi dispatch qua executor, các task được giao cho executor và thời gian bắt đầu/kết thúc giữa các nhánh không được bảo đảm theo thứ tự submit.

| Cấu hình | Hành vi | Tác động |
|---|---|---|
| Không executor | Gọi subscriber đồng bộ | Dễ quan sát lỗi, nhưng latency tổng phụ thuộc các nhánh. |
| Executor nhỏ | Các nhánh dùng chung worker pool | Giới hạn concurrency nhưng một nhánh chậm có thể chiếm worker của nhánh khác. |
| Executor đủ lớn và queue giới hạn | Nhiều nhánh có thể chạy song song | Tăng throughput nhưng cần kiểm soát tài nguyên và thứ tự. |
| Queue lớn hoặc không giới hạn | Chấp nhận nhiều task đang chờ | Có thể làm latency và bộ nhớ tăng khi consumer chậm. |

Không nhất thiết cần một executor riêng cho mỗi subscriber. Tuy nhiên, nếu một nhánh thực hiện I/O chậm hoặc có SLA khác biệt, cân nhắc tách pool hoặc đưa nhánh đó qua queue riêng để tránh chiếm worker của các nhánh quan trọng.

Khi đo hiệu năng, theo dõi thời gian `send()`, thời gian hoàn tất từng handler, số task active, queue depth, rejection và tỷ lệ lỗi theo nhánh. Với dispatch bất đồng bộ, đo riêng latency producer và latency xử lý subscriber; một giá trị `send()` thấp không có nghĩa fan-out đã hoàn tất nhanh.

## 12. Broadcasting không phải durable delivery

`PublishSubscribeChannel` là channel trong bộ nhớ của ứng dụng. Nó phân phối message đến subscriber đang đăng ký, nhưng không tự cung cấp persistence, replay hoặc đảm bảo message được xử lý sau khi tiến trình dừng.

Nếu ứng dụng gửi message vào channel rồi process dừng trước khi executor xử lý xong, task đang chờ có thể bị mất cùng tiến trình. Nếu một subscriber thất bại sau khi các nhánh khác đã thành công, không có cơ chế tự động chạy lại riêng subscriber lỗi trừ khi ứng dụng cấu hình.

Khi yêu cầu độ tin cậy cao:

- Lưu sự kiện nghiệp vụ bền vững bằng transactional outbox hoặc cơ chế tương đương.
- Dùng broker hoặc durable queue cho subscriber cần replay/redelivery.
- Thiết kế consumer idempotent để chịu được message lặp.
- Ghi trạng thái hoàn tất theo từng nhánh nếu cần biết subscriber nào đã xử lý.
- Xây dựng retry/redrive có giới hạn và audit được.

Fan-out trong bộ nhớ phù hợp cho các nhánh nội bộ cần nhận cùng một message trong cùng tiến trình. Với các subscriber có vòng đời độc lập hoặc cần bảo đảm giao nhận, nên cân nhắc messaging broker và topology bền vững.

## 13. Chẩn đoán khi một handler không nhận message

Khi một nhánh không được gọi, kiểm tra theo thứ tự:

1. **Channel có đúng là `PublishSubscribeChannel` không?** Nếu đang dùng `DirectChannel`, mỗi message chỉ dispatch đến một subscriber.
2. **Handler đã subscribe chưa?** Kiểm tra endpoint đã được tạo, khởi động và chưa bị stop/remove.
3. **Có đúng channel instance không?** Các flow phải cùng tham chiếu bean channel, không phải các instance riêng có tên giống nhau.
4. **Có ràng buộc subscriber không?** Kiểm tra `minSubscribers` và `requireSubscribers`.
5. **Một subscriber trước đó có ném exception không?** Với dispatch đồng bộ và `ignoreFailures=false`, lỗi có thể ngăn các nhánh sau được gọi.
6. **Executor có nhận task không?** Kiểm tra queue, worker, rejection policy và `RejectedExecutionException`.
7. **Lỗi async được gửi đi đâu?** Kiểm tra error channel header, global `errorChannel` và error handler.
8. **Handler có chạy nhưng không tạo side effect?** Kiểm tra log, transaction, dependency và điều kiện nghiệp vụ bên trong handler.
9. **Payload có bị chia sẻ mutable?** Kiểm tra race condition nếu nhiều nhánh chạy đồng thời.

Nên log channel, endpoint/subscriber, message ID, correlation ID, thread name và thời điểm nhận. Tránh ghi toàn bộ payload nếu có dữ liệu nhạy cảm.

## 14. Kiểm thử BroadcastingDispatcher

Có thể kiểm tra fan-out bằng một `PublishSubscribeChannel` và hai subscriber đơn giản:

```java
PublishSubscribeChannel channel = new PublishSubscribeChannel();
AtomicInteger firstCount = new AtomicInteger();
AtomicInteger secondCount = new AtomicInteger();

channel.subscribe(message -> firstCount.incrementAndGet());
channel.subscribe(message -> secondCount.incrementAndGet());

channel.send(MessageBuilder.withPayload("event").build());

assertEquals(1, firstCount.get());
assertEquals(1, secondCount.get());
```

Test này xác minh cả hai subscriber đều được gọi trong dispatch đồng bộ. Có thể mở rộng kiểm tra:

- Không có subscriber và cấu hình `requireSubscribers`.
- Số subscriber nhỏ hơn `minSubscribers`.
- Một subscriber ném exception với `ignoreFailures=false` và `true`.
- `applySequence=true` tạo sequence headers phù hợp cho các nhánh.
- Executor khiến handler chạy trên worker thread và `send()` không chờ handler hoàn tất.
- Executor từ chối task khi queue đầy.
- Subscriber được unregister khi endpoint hoặc dynamic flow dừng.
- Handler không sửa payload mutable dùng chung.

Với test bất đồng bộ, dùng `CountDownLatch` hoặc `CompletableFuture` để chờ kết quả có giới hạn. Không dùng `Thread.sleep()` để đoán rằng mọi nhánh đã hoàn tất.

## 15. Những lỗi thiết kế thường gặp

- **Nhầm broadcast với load balancing.** Broadcast gọi nhiều subscriber; unicast chọn một handler.
- **Cho rằng `send()` trả về là mọi handler đã xong.** Điều này không đúng khi dùng executor.
- **Dùng `ignoreFailures=true` mà không ghi nhận lỗi.** Nhánh hỏng có thể bị che khuất.
- **Dựa vào thứ tự subscriber để điều phối nghiệp vụ.** Executor có thể làm các nhánh hoàn tất không theo thứ tự.
- **Cho rằng broadcast có transaction chung.** Side effect đã commit ở nhánh này không tự rollback khi nhánh khác lỗi.
- **Dùng payload mutable giữa nhiều handler.** Các nhánh có thể ghi đè dữ liệu hoặc phát sinh race condition.
- **Coi PublishSubscribeChannel là durable queue.** Message trong bộ nhớ không có replay sau khi tiến trình dừng.
- **Không kiểm tra subscriber khi deploy flow động.** Message có thể được gửi lúc chưa có handler hoặc sau khi handler đã bị gỡ.
- **Dùng một pool chung không giới hạn cho mọi nhánh.** Một subscriber chậm có thể làm backlog ảnh hưởng các nhánh khác.

## 16. Checklist thiết kế

Trước khi dùng broadcast, hãy xác định:

- Message cần đến tất cả subscriber hay chỉ một consumer?
- Những handler nào bắt buộc phải đăng ký để dispatch hợp lệ?
- Các nhánh có độc lập hay có quan hệ thứ tự/phụ thuộc kết quả?
- Dispatch đồng bộ hay bất đồng bộ phù hợp với latency và error semantics?
- Có cần `applySequence` để aggregator gom kết quả không?
- Khi một handler lỗi, các handler còn lại có tiếp tục không?
- Lỗi của subscriber được ghi log, publish hay retry ở đâu?
- Payload có immutable hoặc được copy an toàn cho từng nhánh không?
- Có cần durable delivery, replay và trạng thái hoàn tất theo nhánh không?
- Executor có queue giới hạn, metric và shutdown policy phù hợp không?

`BroadcastingDispatcher` giúp một message kích hoạt nhiều nhánh xử lý trong cùng message flow. Khi chọn đúng synchronous/asynchronous dispatch, cấu hình rõ lỗi và concurrency, đồng thời xác định yêu cầu durability, fan-out sẽ dễ vận hành và không tạo ra kỳ vọng sai về việc mọi nhánh luôn thành công cùng lúc.
