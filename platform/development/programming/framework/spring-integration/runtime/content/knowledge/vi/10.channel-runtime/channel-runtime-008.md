# RendezvousChannel và synchronous handoff

Trong Spring Integration, `RendezvousChannel` là một `PollableChannel` dùng cơ chế handoff đồng bộ giữa producer và consumer. Channel không giữ message trong một hàng đợi có capacity. Một lần gửi chỉ hoàn tất khi có consumer nhận message tương ứng; nếu chưa có consumer, thread gửi phải chờ hoặc hết thời gian chờ.

Đặc điểm này tạo ra backpressure trực tiếp: producer không thể gửi nhanh hơn khả năng consumer nhận message mà không phải chờ. Tuy nhiên, synchronous handoff không có nghĩa producer chờ consumer xử lý xong nghiệp vụ. Producer được giải phóng khi message đã được consumer nhận khỏi channel; handler có thể vẫn đang chạy trên thread consumer.

## 1. RendezvousChannel hoạt động như thế nào?

`RendezvousChannel` nằm trong package `org.springframework.integration.channel` và triển khai `PollableChannel`. Về cơ chế, nó dựa trên `SynchronousQueue` của Java. `SynchronousQueue` không có phần tử được lưu trữ: mỗi thao tác đưa phần tử vào phải bắt cặp với một thao tác lấy phần tử ở thread khác.

Luồng handoff:

~~~mermaid
sequenceDiagram
    participant P as Producer thread
    participant C as RendezvousChannel
    participant R as Poller / Consumer thread
    participant H as Message handler
    P->>C: send(message)
    Note over P,C: Producer chờ consumer nhận
    R->>C: receive()
    C-->>R: Trả message
    C-->>P: send() hoàn tất
    R->>H: Xử lý message
    Note over P,H: Producer có thể tiếp tục trong khi handler vẫn chạy
~~~

Điểm quan trọng nằm ở thời điểm handoff. Khi `receive()` lấy được message, thao tác `send()` có thể hoàn tất. Consumer sau đó mới gọi handler. Vì thế, kết quả `send() == true` xác nhận message đã được nhận khỏi channel, không phải xác nhận nghiệp vụ downstream đã commit hoặc xử lý thành công.

Channel không tạo backlog. Nếu chưa có consumer đang chờ nhận, message chưa được lưu ở đâu trong `RendezvousChannel`; producer giữ message trong lời gọi gửi và chờ một receiver phù hợp.

## 2. So sánh với các channel thường dùng

| Channel | Cách chuyển giao | Producer được giải phóng khi nào? | Có buffer? |
|---|---|---|---|
| `DirectChannel` | Gọi subscriber trực tiếp trên thread gửi | Sau khi lời gọi xử lý đồng bộ hoàn tất hoặc phát sinh lỗi | Không |
| `QueueChannel` | Enqueue message, consumer nhận sau | Khi message được enqueue thành công | Có, theo capacity/store cấu hình |
| `RendezvousChannel` | Handoff trực tiếp giữa send và receive | Khi consumer nhận message | Không |
| `ExecutorChannel` | Submit xử lý tới `TaskExecutor` | Khi task được dispatch theo executor/channel | Hàng đợi task phụ thuộc executor |

`DirectChannel` và `RendezvousChannel` đều có thể khiến producer phải chờ, nhưng khác nhau ở mô hình gọi. `DirectChannel` gọi handler trên thread gửi; `RendezvousChannel` ghép thread gửi với một thread khác đang receive. Với `RendezvousChannel`, producer không chờ handler hoàn tất.

`QueueChannel` cho phép producer tách rời khỏi consumer nhờ buffer. Nếu consumer tạm dừng, queue có thể giữ message cho tới khi capacity đầy. `RendezvousChannel` không có vùng đệm đó: consumer phải sẵn sàng nhận ngay trong thời gian timeout của producer.

`ExecutorChannel` cũng tạo bất đồng bộ, nhưng việc dispatch phụ thuộc executor và queue capacity của nó. `RendezvousChannel` không submit một handler task; nó ghép một lần send với một lần receive.

## 3. Khai báo RendezvousChannel

Có thể khai báo channel thành bean và dùng nó ở cả producer lẫn polling consumer:

~~~java
@Configuration
@EnableIntegration
public class HandoffConfiguration {

    @Bean
    RendezvousChannel handoffChannel() {
        return new RendezvousChannel();
    }
}
~~~

Import chính:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.RendezvousChannel;
~~~

Vì đây là `PollableChannel`, consumer thường là polling endpoint. Một flow có thể nhận message từ channel bằng Java DSL:

~~~java
@Bean
IntegrationFlow handoffConsumerFlow(RendezvousChannel handoffChannel,
                                    OrderService orderService) {
    return IntegrationFlow.from(handoffChannel,
                    endpoint -> endpoint.poller(
                            Pollers.fixedDelay(Duration.ofMillis(100))
                                    .receiveTimeout(100)))
            .handle(orderService, "process")
            .get();
}
~~~

Poller tạo thread nhận message. Khi producer gửi vào `handoffChannel`, lời gọi gửi sẽ chờ tới khi poller gọi `receive()` và lấy được message. Sau đó poller tiếp tục gọi `OrderService.process(...)`.

Chu kỳ poll và receive timeout cần được chọn theo đặc tính nguồn gửi. Poller quá thưa có thể khiến producer thường xuyên chờ lâu; receive timeout quá dài có thể làm thread poller chờ lâu ở mỗi lần nhận. Hãy đo thời gian handoff và cân nhắc số polling endpoint cùng nhận channel.

## 4. Gửi message với timeout hữu hạn

`MessageChannel.send(message, timeout)` nhận timeout tính bằng milliseconds. Với `RendezvousChannel`, timeout hữu hạn giúp producer không bị block vô thời hạn nếu consumer không hoạt động hoặc không có receiver phù hợp.

~~~java
public void submit(Order order) {
    Message<Order> message = MessageBuilder.withPayload(order)
            .setHeader("correlationId", order.getRequestId())
            .build();

    boolean accepted = handoffChannel.send(message, 2_000);
    if (!accepted) {
        throw new IllegalStateException(
                "No consumer received the message within 2 seconds");
    }
}
~~~

Nếu timeout hết trước khi có receiver, `send(...)` trả về `false`. Những lỗi delivery khác có thể được biểu diễn bằng `MessageDeliveryException`; vì vậy, producer cần xử lý cả kết quả timeout lẫn exception theo hợp đồng của ứng dụng.

`send(message)` sử dụng send timeout được cấu hình trên channel. Trong production, nên đặt timeout hữu hạn hoặc chọn chính sách block có chủ đích. Timeout quá ngắn có thể gây lỗi giả khi poller đang bận; timeout quá dài có thể giữ thread request hoặc worker quá lâu.

Không dùng `send()` mặc định mà không hiểu timeout của channel. Nếu timeout được cấu hình là chờ vô hạn, producer có thể bị treo khi consumer stopped, flow chưa start hoặc poller không còn hoạt động.

## 5. Consumer và producer phải ở các thread có thể tiến triển độc lập

Vì `send()` có thể block cho tới khi một thread khác gọi `receive()`, producer và consumer phải có khả năng chạy đồng thời. Một cấu hình thread pool sai có thể tự tạo deadlock hoặc thread starvation.

Ví dụ nguy hiểm: một task chạy trên executor chỉ có một worker, gọi `send()` tới `RendezvousChannel`, rồi chờ receiver. Nếu consumer cũng cần chính executor đó để chạy poller, worker duy nhất đang bị producer chiếm. Consumer không có thread để nhận message, vì vậy handoff không bao giờ xảy ra cho tới khi timeout hoặc ứng dụng bị dừng.

Các điều kiện nên kiểm tra:

- Poller đã start và thực sự đang poll channel.
- Producer không chiếm hết worker thread mà consumer cần sử dụng.
- Executor của poller có đủ worker để thực hiện receive trong lúc producer đang chờ.
- Không giữ lock hoặc tài nguyên độc quyền mà consumer cần trong khi producer đang block ở `send()`.
- Timeout và interruption được xử lý để giải phóng thread khi không thể handoff.

Không gọi `send()` tới một `RendezvousChannel` từ chính thread duy nhất có trách nhiệm thực hiện receive trên channel đó. Hãy tách executor/worker phù hợp hoặc dùng channel có buffer nếu producer và consumer không thể chạy đồng thời.

## 6. Synchronous handoff tạo backpressure nhưng không tạo durability

Do không có buffer, `RendezvousChannel` đưa áp lực của consumer ngược về producer. Khi consumer không nhận kịp, producer phải chờ. Đây là backpressure ở mức handoff, không phải cơ chế lưu trữ message.

| Tình huống | Hành vi |
|---|---|
| Consumer đang chờ receive | Producer có thể handoff ngay |
| Consumer đang xử lý message trước | Producer chờ tới lần receive tiếp theo |
| Consumer stopped | Producer chờ hoặc timeout |
| Poller bị nghẽn | Handoff chậm; producer threads có thể tích tụ |
| JVM dừng khi producer đang chờ | Không có message bền vững trong channel để phục hồi sau restart |

Backpressure chỉ có ích khi upstream có khả năng chờ hoặc giảm tốc. Nếu hàng trăm HTTP request threads cùng block trong `send()`, hệ thống vẫn có thể cạn thread. Vì vậy, cần giới hạn concurrency ở upstream, dùng timeout, circuit breaker hoặc trả trạng thái quá tải phù hợp.

Nếu yêu cầu là giữ message khi consumer tạm dừng, cần `QueueChannel` có capacity phù hợp hoặc broker bền vững. `RendezvousChannel` không thể thay thế queue hay durable messaging.

## 7. Handoff không bảo đảm handler đã xử lý thành công

Sau khi receiver lấy message, producer được giải phóng. Nếu handler ném exception sau thời điểm đó, exception thường xuất hiện ở luồng consumer/poller và error handling của endpoint. Producer không tự nhận được lỗi nghiệp vụ chỉ vì trước đó nó gọi `send()`.

Ví dụ trình tự:

1. Producer gọi `send(message)` và chờ.
2. Poller gọi `receive()`; channel ghép message với consumer.
3. `send()` trả về `true` cho producer.
4. Handler bắt đầu xử lý message trên thread poller.
5. Handler lỗi và error flow nhận exception.

Nếu producer cần biết kết quả xử lý cuối cùng, phải thiết kế reply channel, request/reply gateway, future/correlation store hoặc acknowledgment ở tầng nghiệp vụ. Không diễn giải kết quả `send()` như một xác nhận hoàn tất.

Đối với lỗi sau handoff, cần cấu hình `errorChannel`, error handler, retry advice hoặc cơ chế dead-letter phù hợp. Message đã rời `RendezvousChannel`; channel không tự giữ lại để retry. Nếu cần retry, phải xác định nơi lưu message và chính sách replay.

## 8. Transaction và message ordering

Producer và polling consumer thường chạy trên hai thread. Transaction gắn với thread/resource hiện tại không tự truyền từ producer sang consumer qua `RendezvousChannel`. Nếu producer đang ở trong transaction database, transaction đó không tự bao trùm handler trên poller thread.

Nếu consumer cần transaction, cấu hình transaction advice cho poller/endpoint hoặc mở transaction trong service xử lý trên thread consumer. Cần xác định transaction bao quanh thao tác receive, handler hay từng message theo đúng semantics của nguồn dữ liệu. `RendezvousChannel` là channel trong bộ nhớ; handoff không tạo một transaction phân tán giữa producer và consumer.

Về thứ tự, một `SynchronousQueue` chỉ ghép các lần send với các lần receive; nó không phải hàng đợi FIFO có backlog. Khi có nhiều producer và nhiều consumer cạnh tranh, không nên dựa vào nó như cơ chế đảm bảo thứ tự nghiệp vụ. Nếu cần thứ tự theo key hoặc theo toàn bộ luồng, hãy dùng partitioning, một consumer tuần tự hoặc channel/queue có semantics phù hợp.

## 9. Kiểm thử handoff xác định

Nên kiểm thử hai trường hợp cốt lõi: producer được giải phóng khi receiver lấy message, và producer timeout nếu không có receiver.

Ví dụ dùng một receiver thread:

~~~java
@Test
void sendCompletesWhenAnotherThreadReceives() throws Exception {
    RendezvousChannel channel = new RendezvousChannel();
    Message<String> message = MessageBuilder.withPayload("hello").build();

    ExecutorService receiverExecutor = Executors.newSingleThreadExecutor();
    try {
        Future<Message<?>> received = receiverExecutor.submit(
                () -> channel.receive(2_000));

        boolean sent = channel.send(message, 2_000);

        assertTrue(sent);
        assertSame(message, received.get(2, TimeUnit.SECONDS));
    }
    finally {
        receiverExecutor.shutdownNow();
    }
}
~~~

Ví dụ kiểm tra timeout khi không có receiver:

~~~java
@Test
void sendTimesOutWithoutReceiver() {
    RendezvousChannel channel = new RendezvousChannel();
    Message<String> message = MessageBuilder.withPayload("hello").build();

    assertFalse(channel.send(message, 100));
}
~~~

Trong test thực tế, nên đặt timeout rõ ràng cho mọi `Future.get`, dọn executor trong `finally` và tránh sleep tùy ý để tạo đồng bộ. Có thể dùng `CountDownLatch` để xác nhận receiver đã bắt đầu trước khi producer gửi nếu cần loại bỏ race trong bài test.

Ngoài ra, nên có test tích hợp xác nhận handler chạy trên poller thread và producer đã thoát khỏi `send()` trước khi handler hoàn tất. Điều này chứng minh đúng semantics handoff, tránh vô tình giả định channel đợi xử lý nghiệp vụ.

## 10. Chẩn đoán khi producer bị block

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| `send()` chờ tới timeout | Không có consumer đang receive | Kiểm tra poller đã start, đúng channel và endpoint còn hoạt động |
| Producer threads tăng và đều chờ | Consumer chậm hoặc poller không nhận kịp | Xem thread dump, poll frequency, receive timeout và số consumer |
| Producer và consumer cùng không tiến triển | Thread starvation hoặc deadlock do dùng chung executor | Kiểm tra pool size, queue và thread đang block trong send |
| `send()` thành công nhưng nghiệp vụ lỗi | Handler lỗi sau khi handoff | Kiểm tra errorChannel, log poller và failed message |
| Message không được xử lý lại sau restart | Handoff đã lấy message khỏi channel; channel không durable | Thiết kế persistent queue/broker hoặc cơ chế retry riêng |
| Thứ tự hoàn tất thay đổi | Nhiều producer/consumer xử lý đồng thời | Kiểm tra concurrency và yêu cầu ordering theo key |

Khi lấy thread dump, tìm producer thread đang block trong thao tác send của channel và xác định thread nào có trách nhiệm poll/receive. Nếu consumer thread đang chờ một lock mà producer giữ, hoặc cả hai phụ thuộc cùng pool đã cạn worker, cần sửa cấu trúc điều phối trước khi tăng timeout.

## 11. Khi nào nên và không nên dùng RendezvousChannel?

Phù hợp khi:

- Producer cần biết có consumer nhận message ngay tại thời điểm gửi.
- Muốn handoff trực tiếp giữa hai thread mà không tạo backlog trong channel.
- Consumer có thể chạy đồng thời và hệ thống muốn áp lực chờ quay về producer.
- Có timeout và chính sách xử lý khi không có receiver.

Không phù hợp khi:

- Producer và consumer cần tách rời theo thời gian.
- Cần buffer để hấp thụ burst hoặc consumer tạm dừng.
- Cần lưu message bền vững qua JVM restart.
- Producer không thể block và thread pool upstream có giới hạn chặt.
- Cần FIFO/backlog hoặc thứ tự nghiệp vụ phức tạp.

Trong các trường hợp đó, cân nhắc `QueueChannel`, broker-backed channel, hoặc `ExecutorChannel` với executor được giới hạn phù hợp.

## 12. Checklist triển khai

- [ ] Dùng `RendezvousChannel` khi thực sự cần zero-capacity synchronous handoff.
- [ ] Xác nhận consumer/poller đã hoạt động trước khi producer gửi.
- [ ] Đặt send timeout hữu hạn và xử lý kết quả `false` cùng delivery exception.
- [ ] Cấu hình receive timeout và poller cadence theo độ trễ chấp nhận được.
- [ ] Bảo đảm producer và consumer có worker độc lập để tránh thread starvation.
- [ ] Không giữ lock hoặc tài nguyên mà consumer cần trong lúc producer block.
- [ ] Hiểu rằng `send()` hoàn tất khi receiver nhận message, không phải khi handler commit.
- [ ] Cấu hình error flow/retry riêng cho lỗi xảy ra sau handoff.
- [ ] Thiết kế transaction trên thread consumer; không giả định transaction producer được truyền qua channel.
- [ ] Dùng queue/broker bền vững nếu cần buffer hoặc durability.
- [ ] Kiểm thử timeout, receiver handoff, handler failure và concurrent producer/consumer.

`RendezvousChannel` là một cơ chế handoff có chủ đích: producer chờ cho tới khi consumer nhận message, nhờ đó áp lực được phản hồi ngay tại điểm chuyển giao. Nó không phải queue, không bảo đảm handler đã xử lý thành công và không lưu message bền vững. Khi hiểu rõ ranh giới đó, ta có thể dùng nó để phối hợp hai thread một cách có kiểm soát mà không nhầm lẫn giữa handoff, xử lý đồng bộ và durability.

## Tài liệu tham khảo

- [Spring Integration API: RendezvousChannel](https://docs.spring.io/spring-integration/docs/6.4.x/api/org/springframework/integration/channel/RendezvousChannel.html)
- [Spring Integration Reference: Message Channels](https://docs.spring.io/spring-integration/reference/channel.html)
- [Spring Framework API: MessageChannel](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/messaging/MessageChannel.html)
- [Java API: SynchronousQueue](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/SynchronousQueue.html)
