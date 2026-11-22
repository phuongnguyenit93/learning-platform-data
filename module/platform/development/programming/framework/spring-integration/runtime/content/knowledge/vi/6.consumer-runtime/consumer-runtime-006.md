# receiveTimeout và chờ message

Trong Spring Integration, không phải channel nào cũng giữ message để consumer lấy ra sau. Một `DirectChannel` chuyển message đến subscriber ngay trong lời gọi `send()`, còn `QueueChannel` giữ message trong hàng đợi để một consumer khác gọi `receive()` khi sẵn sàng. Với loại channel thứ hai, thời gian chờ khi nhận message ảnh hưởng trực tiếp đến độ trễ, mức sử dụng thread và nhịp hoạt động của polling endpoint.

`receiveTimeout` mô tả thời gian một lần nhận message có thể chờ khi channel chưa có message. Nó giúp consumer tránh phải kiểm tra queue liên tục, đồng thời cho phép poller chờ một khoảng ngắn để nhận message mới. Tuy nhiên, timeout nhận message không phải timeout xử lý nghiệp vụ, không phải thời gian message được phép nằm trong queue và cũng không quyết định lịch kích hoạt poller.

## 1. PollableChannel và SubscribableChannel

Spring Integration có hai cách tiêu thụ message phổ biến:

| Loại channel | Cách consumer nhận message | Ví dụ |
|---|---|---|
| `PollableChannel` | Consumer chủ động gọi `receive()` hoặc `receive(timeout)` để lấy message | `QueueChannel`, `PriorityChannel`, `RendezvousChannel` |
| `SubscribableChannel` | Consumer đăng ký subscriber; channel dispatch message khi producer gọi `send()` | `DirectChannel`, `PublishSubscribeChannel`, `ExecutorChannel` |

`PollableChannel` phù hợp khi producer và consumer cần tách thời điểm gửi/nhận. Producer có thể gửi message vào queue rồi tiếp tục công việc; consumer lấy message khi có lượt polling hoặc khi code chủ động gọi `receive()`.

`SubscribableChannel` không cung cấp thao tác `receive(timeout)` vì consumer không đứng chờ lấy message. Nó đăng ký handler với channel, sau đó channel gọi handler khi có message. Vì vậy, cấu hình `receiveTimeout` chỉ có ý nghĩa ở đường tiêu thụ có thao tác receive, chẳng hạn polling consumer đọc từ `QueueChannel`.

## 2. Ý nghĩa của receive(timeout)

Interface `PollableChannel` cung cấp hai phương thức chính:

```java
Message<?> receive();
Message<?> receive(long timeout);
```

Tham số `timeout` được tính bằng millisecond. Với phương thức nhận có timeout, cách hiểu thông dụng là:

| Giá trị | Hành vi |
|---|---|
| `0` | Thử nhận ngay; nếu chưa có message thì trả về `null`. |
| Số dương, ví dụ `500` | Chờ tối đa khoảng thời gian đã chỉ định; có message thì trả về sớm, hết thời gian mà chưa có thì trả về `null`. |
| Âm | Chờ không giới hạn theo semantics của `PollableChannel`; chỉ dùng khi thật sự muốn thread có thể chờ vô hạn. |

`receive()` là dạng không truyền timeout tường minh và thường được dùng khi caller chấp nhận semantics chờ của channel. Trong code cần kiểm soát thời gian, nên truyền timeout hữu hạn để giới hạn thời gian giữ thread.

Ví dụ lấy message từ `QueueChannel`:

```java
QueueChannel ordersQueue = new QueueChannel(100);

Message<?> message = ordersQueue.receive(500);
if (message == null) {
    // Không có message trong thời gian chờ.
    return;
}

process(message);
```

Nếu message đến sau 50 ms, lời gọi có thể trả về sau khoảng 50 ms. Nếu không có message trong 500 ms, lời gọi trả về `null`. Thời gian thực tế còn phụ thuộc scheduler của hệ điều hành, contention và implementation channel.

### Timeout không phải lỗi xử lý message

`null` từ `receive(timeout)` thường có nghĩa là không có message được nhận trong khoảng chờ. Nó không tự biểu thị handler thất bại, message bị hỏng hoặc kết nối tới hệ thống ngoài gặp lỗi.

Phân biệt ba kết quả:

- **Nhận được message:** channel trả về một `Message<?>`; consumer có thể chuyển sang bước xử lý.
- **Hết thời gian chờ:** channel trả về `null`; consumer có thể kết thúc lượt polling hoặc tiếp tục theo chính sách.
- **Có exception:** thao tác receive hoặc thành phần liên quan phát sinh lỗi; exception cần được xử lý theo cơ chế error handling tương ứng.

Không nên ghi log ở mức ERROR mỗi khi một lần receive trả về `null`. Với poller chạy định kỳ, việc không có message là trạng thái bình thường. Nếu cần quan sát, hãy dùng metric như số lần poll không có message hoặc thời gian chờ trung bình.

## 3. QueueChannel và thời gian chờ nhận

`QueueChannel` là một `PollableChannel` dựa trên hàng đợi. Producer gửi message vào queue; consumer nhận message bằng `receive()`. Có thể tạo queue có giới hạn dung lượng:

```java
@Bean
public QueueChannel ordersQueue() {
    return new QueueChannel(500);
}
```

Khi queue còn chỗ, `send()` có thể đưa message vào. Khi queue đầy, hành vi gửi phụ thuộc `sendTimeout` và implementation channel. `sendTimeout` là thời gian producer có thể chờ để gửi message; nó khác với thời gian consumer chờ nhận message.

| Thuộc tính/thao tác | Bên chịu ảnh hưởng | Câu hỏi được trả lời |
|---|---|---|
| `sendTimeout` | Producer | Queue đầy thì producer chờ bao lâu để gửi được? |
| `receiveTimeout` / `receive(timeout)` | Consumer | Queue rỗng thì consumer chờ bao lâu để nhận được message? |
| Queue capacity | Cả producer và consumer | Queue có thể giữ tối đa bao nhiêu message đang chờ? |
| Poller trigger | Consumer endpoint | Khi nào poller bắt đầu một lượt lấy message? |

Ví dụ producer gửi có giới hạn thời gian:

```java
boolean sent = ordersQueue.send(
    MessageBuilder.withPayload(order).build(),
    200
);

if (!sent) {
    // Queue không nhận được message trong thời gian chờ gửi.
}
```

Một hệ thống có thể cấu hình `sendTimeout` dài nhưng `receiveTimeout` ngắn, hoặc ngược lại. Hãy chọn riêng theo yêu cầu producer và consumer; không dùng một giá trị timeout chung cho mọi thao tác.

### Một message chỉ được một consumer lấy khỏi queue

Khi `QueueChannel.receive()` trả về message, message đó đã được lấy khỏi queue. Nếu nhiều consumer cùng nhận từ một queue, một message cụ thể chỉ được một consumer lấy ra theo semantics của queue. Đây là mô hình competing consumers, khác với `PublishSubscribeChannel` vốn có thể phát một message đến nhiều subscriber.

Với nhiều consumer, thứ tự hoàn tất xử lý có thể khác thứ tự message được đưa vào queue. Nếu nghiệp vụ yêu cầu thứ tự theo khóa, cần thiết kế partitioning hoặc tuần tự hóa theo khóa thay vì chỉ tăng số consumer.

## 4. receiveTimeout trong polling consumer

Polling consumer sử dụng poller để định kỳ lấy message từ `PollableChannel`. Có hai mốc thời gian cần phân biệt:

- **Poller trigger:** xác định lúc nào một lượt polling được kích hoạt, ví dụ mỗi 500 ms.
- **Receive timeout:** xác định một lần `receive()` trong lượt đó có thể chờ message tối đa bao lâu.

Ví dụ Java DSL:

```java
@Bean
public IntegrationFlow ordersConsumer(
        @Qualifier("ordersQueue") PollableChannel ordersQueue,
        OrderHandler orderHandler) {

    return IntegrationFlow.from(ordersQueue, endpoint -> endpoint.poller(
            Pollers.fixedDelay(500)
                .maxMessagesPerPoll(10)
                .receiveTimeout(100)))
        .handle(orderHandler, "handle")
        .get();
}
```

Trong ví dụ:

1. Poller được kích hoạt theo fixed delay 500 ms.
2. Mỗi lượt có thể nhận tối đa 10 message theo `maxMessagesPerPoll`.
3. Mỗi lần receive có thể chờ tối đa 100 ms khi queue chưa có message.
4. Message nhận được được chuyển đến `OrderHandler.handle`.

Các giá trị trên chỉ để minh họa. Khi chọn timeout, phải tính cả thời gian xử lý message, số message tối đa mỗi lượt và số thread poller có sẵn. Nếu một lượt polling kéo dài hơn chu kỳ trigger, lịch thực tế có thể bị trễ hoặc các lượt tiếp theo không diễn ra đúng thời điểm mong muốn.

### maxMessagesPerPoll và receiveTimeout phối hợp ra sao?

`maxMessagesPerPoll` giới hạn số message mà một lượt polling xử lý. Giá trị dương giới hạn số lần nhận trong lượt; cấu hình tiếp tục polling đến khi không còn message cần được cân nhắc cẩn thận vì có thể làm một lượt chạy kéo dài khi queue luôn có dữ liệu.

`receiveTimeout` được áp dụng cho thao tác chờ nhận. Nếu poller có thể thực hiện nhiều lần receive trong một lượt, tổng thời gian chờ có thể lớn hơn một receive timeout đơn lẻ. Ví dụ tối đa 10 lần nhận, mỗi lần có thể chờ 100 ms, về lý thuyết có thể dành đáng kể thời gian cho chờ message nếu mỗi lần đều gần hết timeout.

Vì vậy, không nên chỉ nhìn vào fixed delay để ước tính thời gian phản hồi. Hãy tính cả receive timeout, số message mỗi lượt, thời gian handler và khả năng queue liên tục có dữ liệu.

## 5. Poller trigger không phải receiveTimeout

Hai cấu hình này thường bị nhầm lẫn:

| Cấu hình | Ví dụ | Ý nghĩa |
|---|---|---|
| `fixedDelay` | `Pollers.fixedDelay(500)` | Khoảng nghỉ giữa các lần kích hoạt theo fixed-delay semantics. |
| `fixedRate` | `Pollers.fixedRate(500)` | Lịch kích hoạt theo nhịp cố định. |
| `receiveTimeout` | `.receiveTimeout(100)` | Thời gian một lần nhận có thể chờ message. |

Giả sử poller có fixed delay 1 giây và receive timeout 200 ms. Poller không có nghĩa là consumer luôn đợi đúng 1 giây để nhận message; scheduler kích hoạt lượt poll, rồi thao tác receive có thể chờ thêm tối đa 200 ms khi queue rỗng. Khi queue đã có message, receive thường trả về sớm.

Nếu tăng receive timeout quá lớn, mỗi lần polling có thể giữ thread lâu khi queue rỗng. Nếu giảm quá thấp, consumer có thể thường xuyên kết thúc receive ngay khi chưa có message và phải đợi trigger tiếp theo. Giá trị phù hợp phụ thuộc tốc độ message đến, số poller, tài nguyên thread và độ trễ mà ứng dụng chấp nhận.

## 6. Threading và tác động của thời gian chờ

Trong polling consumer, thread thực hiện poll thường được lấy từ scheduler hoặc executor được cấu hình cho endpoint. Khi thread đó gọi `receive(timeout)`, nó bị giữ trong thời gian chờ. Nếu handler được gọi trực tiếp sau receive, cùng thread có thể tiếp tục xử lý message trước khi kết thúc lượt poll.

Điều này có một số hệ quả:

- Nhiều poller với timeout dài có thể chiếm phần lớn thread của scheduler.
- Handler xử lý lâu có thể làm chậm các lượt polling tiếp theo nếu dùng chung pool.
- Tăng `maxMessagesPerPoll` có thể tăng throughput nhưng cũng kéo dài thời gian một lượt polling chiếm thread.
- Executor riêng cho downstream có thể tách thread xử lý, nhưng thêm queue và ranh giới bất đồng bộ cần quản lý.

Ví dụ, nếu scheduler chỉ có hai thread nhưng có mười poller cùng chờ receive trong 5 giây, một số poller có thể phải chờ đến lượt được scheduler thực thi. Không nên tăng pool size một cách tùy tiện; trước tiên hãy đo thời gian chờ, thời gian xử lý, số poller hoạt động và độ sâu queue.

Với workload có lưu lượng không đều, có thể chọn timeout vừa phải và poller trigger phù hợp. Nếu yêu cầu phản hồi rất thấp và cần đẩy message ngay khi có dữ liệu, hãy cân nhắc mô hình event-driven với `SubscribableChannel` hoặc inbound message-driven adapter thay vì cố làm poller phản ứng nhanh bằng cách đặt chu kỳ quá ngắn.

## 7. RendezvousChannel và cơ chế handoff

`RendezvousChannel` là một loại `PollableChannel` đặc biệt, dùng cơ chế handoff đồng bộ giữa sender và receiver. Sender không đơn giản đưa message vào một queue có sức chứa lớn rồi tiếp tục; thao tác gửi và nhận cần gặp nhau để hoàn tất trao đổi.

Do đó, cả thời gian chờ gửi và thời gian chờ nhận đều có ý nghĩa. Nếu không có receiver đang chờ, sender có thể phải đợi đến khi timeout hoặc bị ngắt. Channel này hữu ích khi cần handoff trực tiếp giữa hai thread, nhưng không thay thế queue bền vững và không phù hợp để giữ backlog dài.

Khi dùng `RendezvousChannel`, hãy kiểm tra cả `sendTimeout` lẫn receive timeout, đồng thời tránh đặt hai phía chờ vô hạn nếu không có cơ chế điều phối dừng. Nếu sender và receiver cùng phụ thuộc vào một pool nhỏ, cấu hình thread không hợp lý có thể gây starvation: mọi thread bị sender chiếm để chờ receiver nhưng receiver lại không có thread để chạy.

## 8. Timeout, transaction và xác nhận message

`receiveTimeout` chỉ điều khiển việc chờ lấy message. Nó không tự xác định transaction rollback, ack hoặc khả năng khôi phục message khi handler thất bại.

Với một `QueueChannel` trong bộ nhớ, khi receive thành công thì message đã được lấy khỏi queue. Nếu handler sau đó ném exception, channel không tự động đưa message trở lại queue như một broker có cơ chế redelivery. Muốn retry hoặc redrive, ứng dụng cần cấu hình advice, lưu message lỗi hoặc dùng nguồn message có semantics transaction/ack phù hợp.

Với inbound adapter kết nối broker hoặc hệ thống ngoài, hành vi ack/commit phụ thuộc adapter, container và transaction manager. Poller có thể được cấu hình transaction advice, nhưng phải xác định transaction bao phủ receive, xử lý hay cả hai và nguồn message có hỗ trợ rollback/redelivery ra sao.

Không nên suy luận rằng timeout nhận message sẽ rollback transaction. Timeout trả về `null` chỉ cho biết không nhận được message trong khoảng chờ. Nếu transaction bắt đầu quanh lượt poll, việc commit hay rollback còn tùy cấu hình và exception thực tế.

## 9. Lỗi, interrupt và timeout khi dừng ứng dụng

Một consumer có thể đang chờ trong `receive()` khi context bắt đầu đóng. Khi endpoint/poller dừng, runtime cần ngăn các lượt poll mới và kết thúc lượt đang chờ theo cơ chế lifecycle của endpoint/channel. Nếu ứng dụng tự gọi `receive()` trong thread riêng, ứng dụng phải tự quản lý việc đánh thức hoặc interrupt thread đó.

Không nên nuốt `InterruptedException` hoặc xóa trạng thái interrupt mà không có chủ đích. Nếu một API ném `InterruptedException`, hãy dừng công việc phù hợp và khôi phục cờ interrupt khi cần:

```java
BlockingQueue<Message<?>> queue = new LinkedBlockingQueue<>();

try {
    Message<?> message = queue.poll(1, TimeUnit.SECONDS);
    if (message != null) {
        process(message);
    }
}
catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    // Kết thúc vòng lặp consumer hoặc chuyển quyền dừng cho caller.
}
```

Ví dụ trên dùng `BlockingQueue` để minh họa API chờ có thể ném `InterruptedException`. Chữ ký `PollableChannel.receive(long)` không khai báo checked `InterruptedException`, vì vậy không bọc trực tiếp lời gọi đó trong `catch` này. Với consumer tự viết dựa trên `BlockingQueue`, `take()` hoặc `poll(timeout, unit)` có thể ném `InterruptedException`; hãy xử lý tại đúng API đó.

Khi shutdown, timeout hữu hạn giúp thread có cơ hội kiểm tra cờ dừng giữa các lần nhận. Tuy nhiên, timeout hữu hạn không thay thế cơ chế stop rõ ràng; một vòng lặp consumer cần có tín hiệu dừng và thoát đúng lúc.

## 10. Chọn receiveTimeout theo tải thực tế

Không có một giá trị timeout tối ưu cho mọi hệ thống. Có thể chọn theo những yếu tố sau:

| Yếu tố | Khi nào nên điều chỉnh |
|---|---|
| Tốc độ message đến | Message đến thường xuyên có thể dùng timeout ngắn hơn vì receive thường trả về sớm. |
| Độ trễ phản hồi | SLA thấp cần giới hạn tổng thời gian chờ và thời gian chờ đến poller tiếp theo. |
| Số poller và scheduler threads | Nhiều poller chờ lâu cần đủ thread hoặc giảm thời gian chờ. |
| Thời gian handler | Handler lâu có thể khiến một lượt poll chiếm thread lâu hơn dự kiến. |
| Queue capacity và sendTimeout | Producer có thể bị block khi queue đầy; cần phối hợp tốc độ nhận và gửi. |
| Shutdown budget | Timeout và thời gian xử lý phải phù hợp ngân sách dừng ứng dụng. |

Một cách bắt đầu thực tế là đo phân phối thời gian giữa các message đến, thời gian xử lý handler và độ sâu queue. Sau đó chọn fixed delay, receive timeout, max messages per poll và pool size cùng nhau. Thay đổi từng thông số một và quan sát throughput, latency, thread utilization và số lần poll không có message.

## 11. Chẩn đoán khi consumer không nhận được message

Khi message đã được gửi nhưng consumer không nhận được, kiểm tra theo thứ tự:

1. **Channel có phải PollableChannel không?** Nếu là `DirectChannel` hoặc `PublishSubscribeChannel`, consumer cần subscribe thay vì gọi `receive()`.
2. **Producer và consumer có dùng cùng channel instance không?** Hai bean có tên gần giống nhau hoặc hai context khác nhau có thể khiến producer gửi vào queue khác.
3. **Message có thực sự được gửi thành công không?** Kiểm tra kết quả `send()`, `sendTimeout`, queue capacity và exception phía producer.
4. **Poller có được khởi động không?** Kiểm tra endpoint lifecycle, trigger, cấu hình poller và trạng thái context.
5. **receiveTimeout có phù hợp không?** Giá trị quá ngắn có thể khiến poller liên tục không nhận được message; giá trị quá dài có thể giữ thread.
6. **maxMessagesPerPoll và handler có làm lượt poll kéo dài không?** Kiểm tra queue có backlog và thời gian xử lý mỗi message.
7. **Có nhiều consumer cạnh tranh không?** Consumer khác có thể đã lấy message trước.
8. **Có exception hoặc error flow không?** Message có thể đã được nhận rồi handler thất bại; khi đó vấn đề không nằm ở receive timeout.
9. **Có vấn đề thread hoặc executor không?** Kiểm tra scheduler starvation, executor queue đầy và task bị từ chối.

Metrics hữu ích gồm queue depth, số message nhận được, số lần receive trả về rỗng, thời gian chờ receive, thời gian handler, số task đang active và số task bị từ chối. Log nên chứa channel, endpoint, message ID và correlation ID để phân biệt message chưa được nhận với message đã nhận nhưng xử lý thất bại.

## 12. Kiểm thử hành vi timeout

Có thể kiểm tra trực tiếp `QueueChannel` mà không cần khởi động toàn bộ ứng dụng:

```java
QueueChannel channel = new QueueChannel(10);

long started = System.nanoTime();
Message<?> absent = channel.receive(100);
long elapsedMillis = TimeUnit.NANOSECONDS.toMillis(
    System.nanoTime() - started
);

assertNull(absent);
assertTrue(elapsedMillis >= 80);

channel.send(MessageBuilder.withPayload("ready").build());
Message<?> received = channel.receive(100);

assertNotNull(received);
assertEquals("ready", received.getPayload());
```

Ngưỡng thời gian trong test nên có khoảng dung sai vì CI và máy phát triển có độ trễ scheduler khác nhau. Tránh khẳng định thời gian thực tế phải chính xác bằng timeout. Có thể bổ sung test gửi message từ thread khác trong lúc receive đang chờ để xác minh consumer được đánh thức sớm khi message xuất hiện.

Với polling endpoint, dùng test context và message channel để xác minh poller nhận message, giới hạn số message mỗi lượt và dừng đúng lúc khi context đóng. Nếu kiểm tra thứ tự hoặc concurrency, hãy đồng bộ bằng latch/barrier thay vì phụ thuộc vào `Thread.sleep()`.

## 13. Những nhầm lẫn thường gặp

- **Nhầm receiveTimeout với fixedDelay.** Một giá trị điều khiển thời gian chờ trong receive; giá trị kia điều khiển lịch poller.
- **Nhầm receiveTimeout với sendTimeout.** Một giá trị dành cho consumer; giá trị kia dành cho producer khi gửi vào channel.
- **Coi null là exception.** `null` thường biểu thị hết thời gian chờ mà không có message.
- **Dùng receive trên SubscribableChannel.** Loại channel này dispatch đến subscriber, không có semantics polling receive.
- **Đặt timeout vô hạn cho nhiều poller.** Có thể giữ toàn bộ scheduler threads khi queue rỗng.
- **Tăng maxMessagesPerPoll mà không xem thời gian handler.** Một lượt poll có thể chiếm thread quá lâu.
- **Cho rằng QueueChannel tự redeliver sau exception.** Message đã lấy khỏi queue không tự quay lại khi handler thất bại.
- **Dùng QueueChannel như queue bền vững.** Queue trong bộ nhớ không thay thế broker hoặc persistent message store.
- **Cho rằng timeout là deadline xử lý nghiệp vụ.** Handler có thể tiếp tục chạy sau khi receive đã trả về message; cần timeout riêng cho công việc downstream.

## 14. Ghi nhớ khi thiết kế

Khi thiết kế consumer dùng polling, hãy trả lời được các câu hỏi sau:

- Channel có hỗ trợ polling receive hay consumer phải subscribe?
- Consumer chờ bao lâu khi queue rỗng và timeout được tính bằng đơn vị nào?
- Poller được kích hoạt theo fixed delay, fixed rate hay trigger khác?
- Mỗi lượt poll xử lý tối đa bao nhiêu message?
- Scheduler có đủ thread cho tất cả poller đang hoạt động không?
- Queue đầy thì producer chờ bao lâu và xử lý send thất bại ra sao?
- Khi handler lỗi, message được retry, lưu lại hay redrive bằng cơ chế nào?
- Khi context đóng, consumer đang chờ sẽ được dừng và thread được giải phóng ra sao?

Khi phân biệt rõ receive timeout, poller trigger, send timeout và thời gian xử lý handler, việc điều chỉnh consumer trở nên có cơ sở. Consumer có thể chờ đủ lâu để tránh polling rỗng liên tục, nhưng vẫn giải phóng thread đúng hạn, giữ throughput ổn định và có hành vi shutdown dự đoán được.
