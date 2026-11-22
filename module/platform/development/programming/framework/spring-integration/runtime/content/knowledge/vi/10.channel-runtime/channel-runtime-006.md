# QueueChannel và queue state trong memory

Trong Spring Integration, `QueueChannel` là một `PollableChannel` giữ message trong hàng đợi để consumer lấy ra sau. Producer gửi message vào channel và có thể tiếp tục; polling consumer nhận message theo lịch riêng. Vì vậy, `QueueChannel` tạo ra một ranh giới đệm giữa tốc độ gửi và tốc độ xử lý.

Queue của `QueueChannel` thường nằm trong bộ nhớ của JVM. Điều này giúp truyền message giữa các thread và hấp thụ những đợt tải ngắn, nhưng cũng có nghĩa message mặc định không tồn tại sau khi process bị dừng hoặc crash. Khi vận hành, cần theo dõi queue depth, remaining capacity, thời gian message chờ và trạng thái consumer để biết backlog đang tăng vì producer gửi nhanh hay consumer xử lý chậm.

Sau bài này, bạn có thể:

- Giải thích vai trò của `QueueChannel` và khác biệt với `DirectChannel`.
- Phân biệt queue bounded và unbounded, hiểu ảnh hưởng đến memory và back-pressure.
- Điều khiển send/receive timeout khi queue đầy hoặc rỗng.
- Theo dõi trạng thái message đang chờ, đã dequeue và đang xử lý.
- Kết hợp `QueueChannel` với polling consumer và nhiều worker.
- Hiểu giới hạn durability của queue trong memory và cách thiết kế phục hồi.

## 1. QueueChannel là PollableChannel

`QueueChannel` triển khai `PollableChannel`, tức consumer chủ động gọi `receive()` để lấy message. Khác với `SubscribableChannel`, nó không đăng ký handler để channel tự dispatch ngay khi producer gửi message.

```text
Producer
   |
   | send(message)
   v
QueueChannel (BlockingQueue)
   |  message A
   |  message B
   |  message C
   |
   | receive() theo poller
   v
PollingConsumer ---> MessageHandler
```

QueueChannel tạo ra vùng đệm giữa producer và consumer. Producer có thể enqueue message trước khi consumer poll đến, miễn queue còn chỗ và thao tác send được chấp nhận. Consumer lấy message ra khi poller kích hoạt.

Một `QueueChannel` thường sử dụng `BlockingQueue<Message<?>>` ở bên trong. Constructor không chỉ định capacity thường tạo queue không giới hạn theo cách triển khai mặc định; constructor có capacity tạo queue có giới hạn. Có thể cung cấp một `BlockingQueue` tùy chỉnh nếu cần semantics hàng đợi khác. Hãy kiểm tra constructor và implementation đang dùng khi phụ thuộc vào thứ tự hoặc capacity cụ thể.

Với queue FIFO thông dụng, message được lấy theo thứ tự enqueue. Nếu có nhiều consumer, message được phân phối cho consumer lấy được nó trước; thứ tự hoàn tất xử lý không được bảo đảm vì các handler có thể chạy đồng thời và mất thời gian khác nhau.

## 2. QueueChannel khác DirectChannel như thế nào?

Hai channel này tạo ra hai kiểu điều phối message khác nhau:

| Tiêu chí | `DirectChannel` | `QueueChannel` |
|---|---|---|
| Loại channel | `SubscribableChannel` | `PollableChannel` |
| Cách consumer nhận | Handler subscribe; channel dispatch khi send. | Consumer gọi receive theo poller. |
| Thời điểm xử lý | Thường ngay trong lời gọi send. | Có thể muộn hơn thời điểm send. |
| Buffer message | Không có queue giữ message chờ consumer. | Message được giữ trong queue cho đến khi receive. |
| Thread | Thường cùng thread gửi. | Thường là thread của polling task/consumer. |
| Back-pressure | Phụ thuộc dispatch và downstream đồng bộ. | Có thể giới hạn bằng capacity và send timeout. |
| Khi consumer dừng | Không có subscriber để xử lý message. | Message đã enqueue có thể chờ trong queue. |

Chọn `DirectChannel` khi muốn dispatch đồng bộ và kết hợp xử lý ngay trong cùng call stack. Chọn `QueueChannel` khi cần tách producer khỏi consumer bằng một hàng đợi trong process. Nếu cần giữ message qua restart, `QueueChannel` trong memory không đáp ứng yêu cầu durability mặc định.

## 3. Tạo QueueChannel bounded và unbounded

### 3.1. Queue không giới hạn

Có thể tạo queue không chỉ định capacity:

```java
@Bean
QueueChannel ordersQueue() {
    return new QueueChannel();
}
```

Queue không giới hạn giúp producer ít bị chặn khi consumer tạm thời chậm. Tuy nhiên, nếu tốc độ gửi liên tục cao hơn tốc độ xử lý, backlog có thể tăng cho đến khi JVM thiếu heap. Không có giới hạn số message không có nghĩa là hệ thống có tài nguyên vô hạn.

### 3.2. Queue có capacity

Với queue bounded, khai báo capacity rõ ràng:

```java
@Bean
QueueChannel ordersQueue() {
    return new QueueChannel(500);
}
```

Queue có thể giữ tối đa 500 message đang chờ. Khi queue đầy, thao tác send chịu ảnh hưởng bởi timeout và chính sách gửi. Bounded queue giúp giới hạn số phần tử trong bộ nhớ và tạo back-pressure ở producer.

Capacity tính theo số message, không phải số byte. Một message chứa payload lớn có thể giữ nhiều heap hơn message nhỏ. Khi sizing, hãy ước lượng kích thước object graph của payload, headers, số message tối đa và số queue tồn tại đồng thời.

### 3.3. Dùng BlockingQueue tùy chỉnh

`QueueChannel` có thể nhận một `BlockingQueue<Message<?>>` được tạo trước:

```java
@Bean
QueueChannel priorityQueue() {
    BlockingQueue<Message<?>> queue =
            new PriorityBlockingQueue<>(100, messageComparator());
    return new QueueChannel(queue);
}
```

Ví dụ chỉ minh họa điểm mở rộng; `messageComparator()` phải trả về comparator hợp lệ và payload/header dùng để so sánh phải có quy tắc rõ ràng. Với queue ưu tiên, thứ tự lấy message có thể khác thứ tự gửi. Không dùng queue tùy chỉnh nếu chưa xác định semantics ordering, capacity và hành vi khi cạnh tranh giữa nhiều producer/consumer.

## 4. Send timeout khi queue đầy

Khi queue bounded đã đầy, producer không thể enqueue thêm ngay. `MessageChannel.send(message, timeout)` cho phép kiểm soát thời gian chờ:

- Timeout `0`: thử gửi ngay, không chờ nếu queue đang đầy.
- Timeout dương: chờ tối đa số milliseconds được chỉ định để có chỗ trống.
- Timeout âm theo contract của channel: chờ vô hạn.

Ví dụ:

```java
boolean accepted = ordersQueue.send(message, 1_000);

if (!accepted) {
    log.warn("Queue is full; message was not accepted");
    // Chuyển sang recovery, retry có giới hạn hoặc báo lỗi upstream.
}
```

Ví dụ trên chờ tối đa một giây để enqueue. Nếu hết thời gian mà queue vẫn đầy, send có thể trả về `false`. Các lỗi khác trong lúc dispatch hoặc khi channel đóng có thể được biểu diễn bằng exception tùy implementation.

Có thể cấu hình send timeout mặc định trên `AbstractMessageChannel` hoặc truyền timeout tại từng lần gửi. Nên chọn timeout tường minh theo yêu cầu của producer. Chờ vô hạn có thể giữ request thread hoặc scheduler thread quá lâu; timeout bằng 0 có thể khiến producer phải xử lý nhiều lần từ chối hơn.

Không nên bỏ qua kết quả boolean từ `send()`. Nếu message quan trọng mà send thất bại, cần một chính sách recovery rõ ràng: retry có backoff, ghi trạng thái lỗi, chuyển sang broker khác hoặc trả lỗi về caller. Retry phải có giới hạn để tránh tạo vòng gửi vô hạn khi consumer ngừng hoạt động.

## 5. Receive timeout khi queue rỗng

Consumer lấy message bằng `receive()` hoặc `receive(timeout)`. Nếu queue đang rỗng, receive có thể chờ theo timeout được chỉ định:

- Timeout `0`: kiểm tra ngay; không có message thì trả về `null`.
- Timeout dương: chờ tối đa số milliseconds để có message.
- Timeout âm theo contract: chờ vô hạn đến khi có message hoặc thread bị interrupt.

Ví dụ:

```java
Message<?> message = ordersQueue.receive(500);

if (message == null) {
    log.debug("No message available within 500 ms");
}
else {
    process(message);
}
```

Polling endpoint thường quản lý việc gọi receive theo poller và cấu hình receive timeout tương ứng. Trigger của poller quyết định khi nào polling task bắt đầu; receive timeout quyết định mỗi lần receive có thể chờ message bao lâu. Hai giá trị này không phải một.

Nếu receive chờ vô hạn trên một thread dùng chung, thread đó có thể bị giữ lâu. Với polling consumer, hãy cấu hình timeout phù hợp và hiểu cách scheduler/executor được sử dụng trong phiên bản ứng dụng.

## 6. Queue state: message đang ở đâu?

Khi quan sát queue, cần phân biệt message đang chờ trong queue với message đã được lấy ra và đang xử lý:

```text
                 enqueue
Producer -------------------->
                               QueueChannel
                               [A] [B] [C]
                                  |
                                  | receive / dequeue
                                  v
                            In-flight handler
                                  |
                                  v
                              Completed
```

Queue depth chỉ đếm message còn nằm trong hàng đợi. Khi consumer gọi receive thành công, message được lấy khỏi queue trước khi handler hoàn tất. Vì vậy queue depth có thể giảm về 0 trong khi một hoặc nhiều message vẫn đang được xử lý.

Nếu handler ném exception sau khi message đã dequeue, message không tự động quay lại queue chỉ vì xử lý thất bại. Cơ chế retry, recovery, transaction hoặc redelivery cần được thiết kế riêng. Với queue trong memory thông thường, không nên giả định có acknowledgement và redelivery giống message broker.

Các trạng thái nên theo dõi riêng:

| Trạng thái | Ý nghĩa |
|---|---|
| Enqueued | Message đã được chấp nhận và đang chờ trong queue. |
| Dequeued | Consumer đã lấy message ra khỏi queue. |
| In-flight | Handler hoặc downstream đang xử lý message. |
| Completed | Xử lý đã kết thúc thành công theo nghiệp vụ. |
| Failed/recovered | Xử lý thất bại và được chuyển đến recovery/error flow hoặc ghi nhận lỗi. |

Không dùng queue size làm số liệu duy nhất để kết luận flow khỏe mạnh. Queue rỗng có thể vì consumer xử lý nhanh, nhưng cũng có thể vì consumer đã lấy message ra rồi bị kẹt ở downstream.

## 7. Kết hợp QueueChannel với polling consumer

`QueueChannel` là `PollableChannel`, nên thường được nối với polling endpoint. Ví dụ một flow nhận message từ queue mỗi 200 milliseconds và xử lý tối đa 10 message mỗi poll:

```java
@Configuration
class OrderQueueConfiguration {

    @Bean
    QueueChannel ordersQueue() {
        return new QueueChannel(500);
    }

    @Bean
    IntegrationFlow orderConsumer(OrderHandler handler) {
        return IntegrationFlow.from(
                "ordersQueue",
                endpoint -> endpoint.poller(
                        Pollers.fixedDelay(200)
                                .maxMessagesPerPoll(10)))
                .handle(handler, "process")
                .get();
    }
}
```

Producer gửi vào cùng channel:

```java
@Service
class OrderPublisher {

    private final MessageChannel ordersQueue;

    OrderPublisher(@Qualifier("ordersQueue") MessageChannel ordersQueue) {
        this.ordersQueue = ordersQueue;
    }

    public boolean publish(Order order) {
        Message<Order> message = MessageBuilder.withPayload(order).build();
        return ordersQueue.send(message, 500);
    }
}
```

Ví dụ dùng fixed delay 200 ms và giới hạn 10 message mỗi polling cycle. Đây là giá trị minh họa; cần chọn theo thời gian handler, queue capacity và tải downstream. Nếu mỗi message xử lý lâu, batch 10 có thể khiến một polling task chiếm thread đáng kể.

Nếu muốn endpoint không tự start cùng ApplicationContext, có thể cấu hình `autoStartup(false)` ở endpoint và chủ động start khi hệ thống sẵn sàng. Queue vẫn có thể nhận message trước khi consumer start, miễn capacity và send timeout cho phép. Hãy nhớ rằng queue nằm trong memory của process.

## 8. Nhiều consumer cùng đọc một QueueChannel

Có thể có nhiều polling consumer cùng nhận message từ một `QueueChannel`. Các consumer này cạnh tranh lấy message: mỗi message được một consumer lấy khỏi queue, không broadcast đến tất cả consumer.

```text
                         +--> PollingConsumer A --> Worker A
Producer --> QueueChannel+
                         +--> PollingConsumer B --> Worker B
```

Mô hình này có thể tăng throughput khi handler xử lý độc lập và nguồn dữ liệu cho phép chạy song song. Tuy nhiên:

- Thứ tự dequeue có thể theo queue, nhưng thứ tự hoàn tất xử lý không được bảo đảm.
- Hai worker có thể xử lý đồng thời message cùng business key.
- Tăng số consumer làm tăng tải lên database/API downstream.
- Nếu handler không idempotent, retry hoặc gửi lại có thể gây tác động trùng.
- Cần giới hạn concurrency và thiết kế transaction phù hợp.

Nếu cần tuần tự theo order ID hoặc tenant, hãy phân vùng queue theo key, serialize xử lý hoặc dùng cơ chế khóa ở tầng dữ liệu. Không nên dựa vào một queue FIFO duy nhất để bảo đảm thứ tự hoàn tất khi có nhiều consumer.

## 9. Queue depth, remaining capacity và metrics

`QueueChannel` cung cấp thông tin về queue để hỗ trợ giám sát, bao gồm kích thước queue và dung lượng còn lại khi queue có giới hạn:

```java
@Component
class QueueMonitor {

    private final QueueChannel ordersQueue;

    QueueMonitor(@Qualifier("ordersQueue") QueueChannel ordersQueue) {
        this.ordersQueue = ordersQueue;
    }

    void report() {
        log.info("ordersQueue size={}, remainingCapacity={}",
                ordersQueue.getQueueSize(),
                ordersQueue.getRemainingCapacity());
    }
}
```

Tên và khả năng truy cập các phương thức quản lý cần đối chiếu với phiên bản Spring Integration đang sử dụng. Với queue không giới hạn, remaining capacity có thể được biểu diễn như một giá trị rất lớn thay vì một giới hạn hữu ích cho vận hành.

Theo dõi các số liệu theo thời gian:

- **Queue depth:** số message đang chờ.
- **Remaining capacity:** số phần tử có thể enqueue thêm với queue bounded.
- **Enqueue rate:** tốc độ producer gửi message thành công.
- **Dequeue rate:** tốc độ consumer lấy message.
- **Queue wait time:** thời gian message nằm trong queue trước khi được nhận.
- **In-flight count:** số message đã dequeue nhưng chưa hoàn tất xử lý.
- **Send timeout/rejection:** số lần producer không enqueue được trong thời gian cho phép.
- **Processing duration/error rate:** thời gian và tỷ lệ lỗi của handler.

Nếu enqueue rate liên tục lớn hơn dequeue rate, queue depth sẽ tăng. Nếu queue depth thấp nhưng in-flight count cao và handler duration tăng, vấn đề nằm ở downstream. Một ảnh chụp queue size chỉ phản ánh một thời điểm và có thể thay đổi ngay do producer/consumer hoạt động đồng thời; không dùng nó làm cơ chế đồng bộ nghiệp vụ.

## 10. Back-pressure và cách chọn capacity

Bounded `QueueChannel` có thể tạo back-pressure: khi queue đầy, producer phải chờ đến khi có chỗ trống hoặc xử lý kết quả timeout. Điều này ngăn backlog tăng không giới hạn trong heap, nhưng back-pressure chỉ hiệu quả khi producer thực sự tôn trọng timeout và kết quả send.

Ví dụ chọn capacity cần dựa trên:

1. Tốc độ message vào trung bình và đỉnh.
2. Thời gian consumer có thể ngừng hoặc xử lý chậm.
3. Kích thước payload và headers trung bình/tối đa.
4. Số consumer và throughput xử lý thực tế.
5. Heap dành cho queue cùng các object khác trong ứng dụng.
6. Hành vi producer khi send timeout hoặc queue đầy.

Một ước lượng sơ bộ: nếu producer có thể gửi 100 message/giây và muốn hấp thụ một đợt consumer dừng 5 giây, cần ít nhất khoảng 500 slot để chứa lượng message đến trong khoảng đó, chưa tính backlog ban đầu và headroom. Đây chỉ là ước lượng số phần tử; phải tính thêm kích thước payload, tốc độ burst và thời gian drain sau khi consumer hoạt động lại.

Không tăng capacity chỉ để che giấu việc consumer xử lý chậm kéo dài. Queue lớn hơn có thể làm message chờ lâu hơn, tăng memory và khiến hệ thống phát hiện quá tải muộn hơn. Khi backlog tăng liên tục, hãy điều chỉnh producer rate, tối ưu handler, tăng consumer có kiểm soát hoặc chuyển sang broker phù hợp.

## 11. QueueChannel trong memory có durable không?

`QueueChannel` với queue trong memory giữ tham chiếu đến message trong heap của JVM. Nó có thể tiếp tục giữ message khi polling endpoint tạm stop rồi start lại trong cùng process, nhưng mặc định không phải persistent queue.

Các hệ quả:

- Khi JVM/process bị restart hoặc crash, message còn trong queue memory bị mất.
- Queue không tự tạo bản sao message trên disk.
- Queue không cung cấp broker acknowledgement/redelivery mặc định.
- Payload mutable vẫn có thể bị thay đổi qua tham chiếu object dù message/header map được thiết kế bất biến.
- Message giữ payload và object graph, nên queue depth thấp vẫn có thể tiêu thụ nhiều heap nếu payload lớn.

Nếu cần message tồn tại qua restart, hãy dùng broker như RabbitMQ/Kafka/JMS hoặc cơ chế persistent `MessageStore`/queue-backed store được Spring Integration phiên bản đang dùng hỗ trợ và cấu hình đúng. Cần xác minh semantics lưu trữ, transaction, recovery và serialization của giải pháp cụ thể; không suy ra durability chỉ từ việc component mang tên `QueueChannel`.

Với queue trong memory, hãy thiết kế graceful shutdown để dừng producer, cho consumer xử lý backlog trong giới hạn thời gian và ghi nhận công việc chưa hoàn tất. Nhưng graceful shutdown vẫn không bảo đảm chống mất dữ liệu khi process bị kill đột ngột hoặc máy chủ mất điện.

## 12. Xử lý lỗi sau khi dequeue

Khi consumer gọi `receive()` thành công, message được lấy khỏi queue. Nếu handler thất bại sau đó, queue không tự động đưa message trở lại. Vì thế, cần quyết định chính sách lỗi theo yêu cầu nghiệp vụ:

- Retry đồng bộ có giới hạn nếu lỗi tạm thời và thao tác idempotent.
- Chuyển message sang error channel/recovery flow nếu không thể xử lý tại chỗ.
- Ghi trạng thái thất bại và business ID để có thể điều tra hoặc phát lại.
- Dùng broker có acknowledgement/redelivery nếu cần bảo đảm giao nhận qua sự cố.
- Dùng transaction/persistent store phù hợp nếu cần rollback trạng thái queue cùng transaction; không giả định `BlockingQueue` trong memory tự rollback khi database transaction thất bại.

Không retry vô hạn ngay trong handler vì có thể giữ worker và làm queue phía trước tiếp tục đầy. Cần giới hạn số lần thử, backoff và đường xử lý cuối cùng cho message không thể hoàn tất.

## 13. Chẩn đoán QueueChannel bị nghẽn

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Queue depth tăng liên tục | Producer nhanh hơn consumer. | So sánh enqueue/dequeue rate và handler duration. |
| Send chờ lâu hoặc trả về false | Queue bounded đã đầy. | Kiểm tra capacity, send timeout và remaining capacity. |
| Consumer không lấy message | Endpoint chưa start, poller chưa chạy hoặc nhận nhầm channel. | Kiểm tra lifecycle, poller và input channel. |
| Queue rỗng nhưng nghiệp vụ vẫn chậm | Message đã dequeue và đang in-flight hoặc downstream bị kẹt. | Đo in-flight count và handler duration. |
| Message mất sau restart | Queue chỉ nằm trong memory. | Chuyển sang broker hoặc persistent store phù hợp. |
| Message lỗi không được thử lại | Dequeue không tự redeliver sau handler exception. | Kiểm tra error flow, retry/recovery và acknowledgement semantics. |
| Hoàn tất sai thứ tự | Nhiều consumer xử lý song song. | Kiểm tra concurrency và yêu cầu ordering theo business key. |

Quy trình kiểm tra:

1. Xác nhận channel đúng là `QueueChannel` và xác định bounded/unbounded capacity.
2. Đo queue depth, remaining capacity và tốc độ enqueue/dequeue.
3. Kiểm tra endpoint/poller có running và có poll đều không.
4. Đo thời gian message chờ và thời gian handler xử lý.
5. Kiểm tra send timeout, receive timeout và log lỗi producer.
6. Kiểm tra message đã dequeue có bị kẹt ở downstream hoặc chuyển sang error flow không.
7. Xác nhận yêu cầu durability và recovery khi restart/crash.

## 14. Tự kiểm tra

**Tình huống:** Một `QueueChannel(100)` nhận message từ producer. Polling consumer tạm dừng trong 10 giây, trong khi producer vẫn gửi 20 message/giây. Sau đó consumer được start lại nhưng handler xử lý mỗi message mất 200 ms.

1. Queue có thể giữ tối đa bao nhiêu message đang chờ?
2. Sau 10 giây, producer đã gửi khoảng bao nhiêu message nếu không có message nào được dequeue?
3. Vì sao send có thể bị block hoặc thất bại khi queue đầy?
4. Khi queue depth về 0, có chắc mọi message đã xử lý thành công không?
5. Nếu process crash khi queue còn message, các message đó có được phục hồi mặc định không?

**Gợi ý trả lời:** (1) 100 message. (2) Khoảng 200 message, lớn hơn capacity nên một phần send phải chờ hoặc không được chấp nhận tùy timeout. (3) Queue bounded không còn slot; send timeout quyết định chờ bao lâu. (4) Không; message có thể đã dequeue và còn in-flight hoặc thất bại sau dequeue. (5) Không; queue memory mặc định mất khi process kết thúc.

**Bài tập thực hành:** Tạo `QueueChannel(20)` và polling consumer. Gửi nhanh 50 message với send timeout bằng 0, ghi số lần send thành công và thất bại. Sau đó bật consumer, đo queue depth và processing duration. Lặp lại với send timeout 500 ms và so sánh tác động back-pressure lên producer. Cuối cùng, dừng consumer khi queue còn message rồi restart process để quan sát giới hạn durability của queue trong memory.

## Tài liệu tham khảo

- [Spring Integration Reference — Message Channels](https://docs.spring.io/spring-integration/reference/channel.html)
- [Spring Integration Reference — Polling Consumer](https://docs.spring.io/spring-integration/reference/endpoint.html#polling-consumer)
- [Spring Integration Javadoc — QueueChannel](https://docs.spring.io/spring-integration/api/org/springframework/integration/channel/QueueChannel.html)
- [Spring Framework Javadoc — PollableChannel](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/PollableChannel.html)
- [Java Javadoc — BlockingQueue](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/BlockingQueue.html)
