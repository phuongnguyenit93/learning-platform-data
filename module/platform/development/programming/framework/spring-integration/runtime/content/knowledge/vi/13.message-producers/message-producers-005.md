# Send timeout và lỗi khi channel đầy

Producer trong Spring Integration gửi message qua `MessageChannel.send(...)`. Kết quả gửi phụ thuộc loại channel, trạng thái consumer, capacity và timeout. Với channel có buffer giới hạn như `QueueChannel`, producer có thể phải chờ khi queue đầy. Nếu không đặt giới hạn phù hợp, các thread tạo message có thể bị giữ lại, làm cạn thread pool và lan truyền tình trạng quá tải về upstream.

`sendTimeout` là giới hạn thời gian chờ để channel chấp nhận hoặc chuyển giao message theo semantics của channel. Nó không phải thời gian tối đa để handler xử lý nghiệp vụ. Muốn kiểm soát hệ thống khi channel đầy, cần thiết kế cả capacity, timeout, chính sách từ chối, retry và cách phản hồi cho caller.

## 1. Hợp đồng của MessageChannel.send

`MessageChannel` có hai phương thức gửi thường dùng:

~~~java
boolean send(Message<?> message);
boolean send(Message<?> message, long timeout);
~~~

Timeout được tính bằng milliseconds. Với các channel hỗ trợ chờ khi gửi, quy ước thông thường là:

| Timeout | Ý nghĩa |
|---|---|
| `0` | Không chờ; thử gửi ngay và trả kết quả nếu chưa thể gửi |
| Giá trị dương | Chờ tối đa số milliseconds đã chỉ định |
| Giá trị âm (thường là `-1`) | Chờ vô hạn theo contract của channel |

`send(message)` sử dụng send timeout mặc định của channel. Với `AbstractMessageChannel`, có thể đặt giá trị mặc định bằng `setSendTimeout(...)`. Lệnh `send(message, timeout)` cho phép producer chọn timeout riêng cho từng lần gửi.

Kết quả trả về:

- `true`: channel đã chấp nhận hoặc chuyển giao message theo semantics của nó.
- `false`: message không được gửi, ví dụ hết thời gian chờ hoặc interceptor từ chối message trong `preSend`.
- Exception: quá trình gửi gặp lỗi delivery hoặc lỗi runtime; cần xử lý theo loại channel và nguyên nhân.

Không nên chỉ kiểm tra exception. Một lần gửi có thể trả `false` mà không ném exception. Ngược lại, exception có thể xuất hiện do subscriber, executor, interceptor hoặc transport. Producer phải xử lý cả ba kết quả: `true`, `false` và exception.

## 2. Send timeout phụ thuộc loại channel

Không phải mọi channel đều có buffer hoặc dùng timeout giống nhau.

| Channel | Khi producer gửi | Vai trò của timeout |
|---|---|---|
| `QueueChannel` có capacity hữu hạn | Enqueue message vào queue | Chờ slot trống; hết timeout thì send có thể trả `false` |
| `RendezvousChannel` | Chờ một consumer nhận message trực tiếp | Chờ tới khi có receiver hoặc hết timeout |
| `DirectChannel` | Gọi subscriber đồng bộ trên thread gửi | Không tạo deadline xử lý handler; producer có thể chờ toàn bộ lời gọi handler |
| `ExecutorChannel` | Dispatch task qua executor | Khả năng chờ/từ chối phụ thuộc executor và rejection policy |
| `PublishSubscribeChannel` | Gửi tới các subscriber | Phụ thuộc dispatch đồng bộ hay executor và cấu hình subscriber |
| Broker-backed channel/adapter | Gửi qua transport tới broker | Phụ thuộc timeout và xác nhận của client/broker; không đồng nghĩa consumer đã xử lý |

`sendTimeout` không phải một timeout tổng quát cho mọi bước trong flow. Với `DirectChannel`, handler chạy đồng bộ nên thời gian gọi handler có thể kéo dài lâu hơn dự kiến; send timeout không tự ngắt method đang chạy. Với `ExecutorChannel`, task có thể đã được executor nhận nhưng handler vẫn chưa bắt đầu. Với broker, producer confirmation và consumer acknowledgment là các mốc khác nhau.

## 3. QueueChannel đầy có nghĩa gì?

`QueueChannel` lưu message cho consumer nhận sau. Khi tạo channel với capacity hữu hạn, số message đang chờ bị giới hạn:

~~~java
@Bean
QueueChannel ordersQueue() {
    QueueChannel channel = new QueueChannel(500);
    channel.setSendTimeout(250);
    return channel;
}
~~~

Trong ví dụ, queue chứa tối đa 500 message đang chờ. Khi đủ 500 message, lần gửi tiếp theo phải đợi consumer lấy bớt message. Producer có thể chờ tối đa 250 ms theo send timeout mặc định của channel.

Có thể override timeout cho một lần gửi:

~~~java
boolean accepted = ordersQueue.send(message, 100);
~~~

Nếu queue không có slot trong 100 ms, send có thể trả `false`. Giá trị timeout riêng này không thay đổi timeout mặc định của channel cho những lần gửi khác.

Capacity hữu hạn giúp giới hạn bộ nhớ và tạo tín hiệu backpressure. Queue không làm hệ thống xử lý nhanh hơn; nó chỉ hấp thụ burst trong một khoảng thời gian. Nếu tốc độ message đến lâu dài lớn hơn tốc độ consumer xử lý, queue cuối cùng vẫn đầy.

## 4. Tính capacity và thời gian chờ

Gọi:

- \(\lambda\): tốc độ message đến, tính bằng message/giây.
- \(\mu\): tốc độ consumer xử lý, tính bằng message/giây.
- \(C\): số slot của queue.
- \(Q\): số message hiện đang chờ.

Nếu \(\lambda < \mu\) trong thời gian đủ dài, consumer có khả năng xử lý hết tải trung bình. Nếu \(\lambda > \mu\), backlog tăng xấp xỉ theo tốc độ \(\lambda-\mu\) cho tới khi queue đầy.

Khi queue đang có \(Q\) message và consumer xử lý ổn định ở tốc độ \(\mu\), thời gian chờ thô trước khi một slot được giải phóng có thể ước lượng khoảng:

\[
T_{wait} \approx \frac{Q}{\mu}
\]

Nếu \(\lambda > \mu\), thời gian ước lượng để queue tăng từ mức hiện tại tới đầy là:

\[
T_{full} \approx \frac{C-Q}{\lambda-\mu}
\]

Đây chỉ là ước lượng khi tốc độ tương đối ổn định; message có thời gian xử lý khác nhau, nhiều consumer, batch polling và retry sẽ làm kết quả thay đổi. Dùng metric queue depth và tuổi message cũ nhất để hiệu chỉnh capacity theo tải thật.

Ví dụ, producer tạo 120 message/giây, consumer xử lý 100 message/giây và queue còn 1.000 slot trống. Backlog tăng khoảng 20 message/giây, nên queue có thể đầy sau khoảng 50 giây nếu tốc độ giữ nguyên. Tăng capacity sẽ kéo dài thời gian trước khi đầy, nhưng không giải quyết chênh lệch throughput.

## 5. Producer xử lý kết quả send

Producer nên coi kết quả gửi là một phần của hợp đồng ứng dụng. Nếu channel từ chối message vì timeout, cần có quyết định rõ ràng: trả lỗi cho caller, retry có giới hạn, lưu vào outbox hoặc chuyển sang một đường xử lý quá tải.

~~~java
@Component
public class OrderMessageProducer {

    private final MessageChannel ordersChannel;

    public OrderMessageProducer(
            @Qualifier("ordersQueue") MessageChannel ordersChannel) {
        this.ordersChannel = ordersChannel;
    }

    public void publish(Order order) {
        Message<Order> message = MessageBuilder.withPayload(order)
                .setHeader("correlationId", order.getRequestId())
                .build();

        try {
            boolean accepted = ordersChannel.send(message, 200);
            if (!accepted) {
                throw new MessageRejectedException(
                        message, "Orders channel did not accept the message");
            }
        }
        catch (MessageDeliveryException ex) {
            throw ex;
        }
    }
}
~~~

Ví dụ dùng timeout 200 ms để giới hạn thời gian producer chờ. `MessageRejectedException` biểu diễn trường hợp ứng dụng quyết định từ chối tiếp tục khi channel không nhận message. Trong hệ thống thực tế, exception có thể được ánh xạ thành phản hồi HTTP 429/503, trạng thái retry hoặc kết quả nghiệp vụ phù hợp.

Nếu không cần phân loại exception, có thể dùng exception ứng dụng riêng. Điều quan trọng là không bỏ qua giá trị `false`, vì làm vậy producer có thể báo thành công trong khi message chưa được chấp nhận.

## 6. Send timeout khác receive timeout và processing timeout

Ba timeout thường bị nhầm lẫn:

| Timeout | Kiểm soát điều gì? | Ví dụ |
|---|---|---|
| Send timeout | Thời gian producer chờ channel chấp nhận/chuyển giao message | `channel.send(message, 200)` |
| Receive timeout | Thời gian consumer chờ message trên pollable channel | `receive(500)` hoặc cấu hình poller |
| Processing timeout | Thời gian tối đa cho handler hoặc lời gọi nghiệp vụ | HTTP client timeout, transaction timeout, deadline ở service |

Send timeout không hủy handler đã bắt đầu chạy. Receive timeout không giới hạn thời gian xử lý message sau khi nhận. Processing timeout phải được cấu hình tại service/client hoặc cơ chế xử lý phù hợp.

Với `DirectChannel`, send đồng bộ thường đợi handler trả về; nếu cần giới hạn thời gian nghiệp vụ, cấu hình timeout cho dependency và tránh block không kiểm soát trong handler. Với `QueueChannel`, producer thường chỉ đợi enqueue, còn xử lý diễn ra sau đó; thời gian chờ của handler không nằm trong send timeout.

## 7. Retry khi channel đầy

Retry có thể giúp producer vượt qua tình trạng quá tải ngắn hạn, nhưng retry không giới hạn sẽ khuếch đại tải và làm channel càng khó phục hồi.

Một chính sách retry hợp lý cần:

- Giới hạn số lần thử và tổng thời gian retry.
- Có backoff tăng dần, thường thêm jitter để nhiều producer không retry cùng một thời điểm.
- Chỉ retry khi kết quả cho biết message chưa được chấp nhận hoặc khi thao tác có idempotency phù hợp.
- Không giữ transaction database hoặc lock trong toàn bộ thời gian ngủ chờ retry.
- Có fallback như outbox, durable broker hoặc trả lỗi quá tải cho caller.

Với channel nội bộ, `send()` trả `false` thường chỉ ra message chưa được nhận theo contract của channel; tuy nhiên, nếu interceptor có thể từ chối message, retry mù quáng sẽ lặp lại một điều kiện từ chối cố định. Hãy phân biệt queue full với policy rejection.

Với hệ thống từ xa, timeout có thể tạo kết quả không rõ ràng: broker/client có thể đã nhận message nhưng producer chưa nhận được confirmation. Nếu retry, có nguy cơ gửi trùng. Dùng message ID hoặc idempotency key và thiết kế consumer có thể deduplicate.

Không viết vòng lặp `while (!send(...))` không có delay hoặc giới hạn. Vòng lặp đó có thể chiếm CPU và làm cạn thread producer. Nếu cần retry bất đồng bộ, dùng retry advice hoặc scheduler/queue riêng để quản lý lần thử tiếp theo.

## 8. Backpressure và lựa chọn khi queue đầy

Khi channel đầy, có một số chính sách thường dùng:

| Chính sách | Hành vi | Phù hợp khi |
|---|---|---|
| Fail fast | Timeout bằng 0, trả `false` ngay | Caller có thể thử lại hoặc từ chối nhanh |
| Bounded wait | Chờ trong khoảng thời gian hữu hạn | Burst ngắn, caller còn ngân sách latency |
| Block có giới hạn | Chờ consumer giải phóng slot với timeout rõ ràng | Upstream có thể chịu backpressure |
| Spill to durable store | Ghi message vào outbox/broker bền vững | Không muốn mất yêu cầu khi consumer tạm chậm |
| Load shedding | Trả 429/503 hoặc từ chối theo quota | Hệ thống cần bảo vệ tài nguyên khi quá tải |

Không phải mọi producer đều có thể block. HTTP request thread, scheduler thread và worker pool có capacity hữu hạn. Nếu mọi thread đều chờ channel đầy, consumer có thể không còn thread hoặc connection để xử lý message và giải phóng queue. Đây là dạng thread starvation/deadlock cần tránh.

Với API công khai, phản hồi quá tải sớm thường tốt hơn giữ request thread quá lâu. Với tác vụ nội bộ có thể thử lại, bounded wait kết hợp retry có backoff có thể phù hợp hơn. Với nghiệp vụ không được mất yêu cầu, dùng durable outbox hoặc broker và xác định rõ thời điểm xác nhận cho caller.

## 9. Transaction và outbox khi producer gửi message

Nếu producer đang mở transaction database rồi block khi gửi vào channel đầy, transaction có thể giữ connection, lock và tài nguyên trong suốt thời gian chờ. Khi nhiều producer cùng làm vậy, database pool có thể cạn trước cả khi consumer phục hồi.

Không nên giữ transaction dài chỉ để chờ một queue trong bộ nhớ có slot. Nếu cần bảo đảm dữ liệu nghiệp vụ và message được ghi nhận nhất quán, cân nhắc transactional outbox:

1. Trong transaction nghiệp vụ, ghi dữ liệu domain và một outbox record vào cùng database.
2. Một publisher riêng đọc các record chưa gửi và publish tới broker/channel phù hợp.
3. Chỉ đánh dấu đã publish theo confirmation semantics đã chọn.
4. Consumer xử lý idempotent để chịu được publish lại khi publisher restart hoặc confirmation bị mất.

`QueueChannel` trong bộ nhớ không trở thành durable chỉ vì producer gửi message bên trong transaction database. Transaction không tự rollback một message đã enqueue vào một queue không tham gia transaction đó. Hãy xác định rõ resource nào tham gia transaction và resource nào cần outbox/compensation.

## 10. Channel đầy và lỗi xử lý là hai loại sự cố khác nhau

Không phải mọi lỗi message đều được đưa vào `errorChannel`.

| Tình huống | Nơi phát hiện | Cách xử lý |
|---|---|---|
| `QueueChannel` đầy, send timeout | Producer khi gọi `send()` | Xử lý `false`, retry có giới hạn hoặc trả lỗi quá tải |
| `preSend` interceptor từ chối | Producer/channel send path | Kiểm tra policy/interceptor; không coi mặc định là queue full |
| Không có subscriber trên `DirectChannel` | Send/dispatch path | Kiểm tra endpoint registration và channel topology |
| Handler lỗi sau khi message được enqueue | Consumer/endpoint | Error flow, retry advice, dead-letter hoặc xử lý lỗi nghiệp vụ |
| Executor từ chối task | Executor dispatch path | Kiểm tra pool, queue capacity và rejection policy |
| Broker từ chối hoặc timeout khi publish | Producer adapter/client | Kiểm tra broker response, confirmation và retry semantics |

`errorChannel` thường xử lý exception phát sinh trong quá trình endpoint xử lý message. Nếu producer không gửi được message vì channel đầy và `send()` trả `false`, producer phải xử lý kết quả đó; không nên chờ error flow của consumer tự giải quyết.

## 11. Quan sát send timeout và queue saturation

Để phát hiện quá tải trước khi producer bắt đầu timeout hàng loạt, theo dõi:

- Số lần send được chấp nhận, trả `false` và ném exception.
- Send latency p50/p95/p99 theo channel hoặc nhóm channel.
- Queue depth, capacity và tỷ lệ sử dụng.
- Tuổi của message cũ nhất trong queue.
- Throughput producer so với throughput consumer.
- Số consumer/poller đang hoạt động và thời gian xử lý trung bình.
- Executor active threads, queue size và rejected tasks nếu channel dispatch qua executor.
- Số lần retry, thời gian backoff và số message chuyển sang outbox/dead-letter.

Metric tag nên có cardinality thấp. Dùng channel group, channel type và kết quả gửi; không gắn order ID, customer ID hoặc message ID làm tag. Các ID chi tiết nên nằm trong log hoặc trace.

Một cảnh báo hữu ích có thể dựa trên queue utilization duy trì cao, tuổi message tăng liên tục hoặc tỷ lệ send timeout vượt ngưỡng. Chỉ nhìn queue depth tức thời có thể bỏ qua tình trạng message bị kẹt lâu dù số lượng chưa đạt capacity.

## 12. Kiểm thử channel đầy và send timeout

Có thể kiểm tra hành vi bounded queue mà không cần chạy scheduler:

~~~java
@Test
void boundedQueueRejectsWhenFullWithoutWaiting() {
    QueueChannel channel = new QueueChannel(1);
    Message<String> first = MessageBuilder.withPayload("first").build();
    Message<String> second = MessageBuilder.withPayload("second").build();

    assertTrue(channel.send(first, 0));
    assertFalse(channel.send(second, 0));
}
~~~

Kiểm thử timeout dương khi queue đang đầy:

~~~java
@Test
void sendWaitsOnlyUpToConfiguredTimeout() {
    QueueChannel channel = new QueueChannel(1);
    channel.send(MessageBuilder.withPayload("first").build(), 0);

    long started = System.nanoTime();
    boolean sent = channel.send(
            MessageBuilder.withPayload("second").build(), 100);
    long elapsedMillis = TimeUnit.NANOSECONDS.toMillis(
            System.nanoTime() - started);

    assertFalse(sent);
    assertTrue(elapsedMillis >= 80);
    assertTrue(elapsedMillis < 1_000);
}
~~~

Khoảng thời gian trong test dùng biên rộng để tránh phụ thuộc chính xác vào scheduler của hệ điều hành. Không nên assert thời gian bằng đúng 100 ms. Trong test tích hợp, bổ sung consumer lấy message để xác nhận producer được giải phóng khi có slot trống.

Các trường hợp nên kiểm thử thêm:

- Timeout bằng 0, timeout dương và timeout âm theo chính sách được chọn.
- Consumer tạm dừng rồi hoạt động lại.
- Nhiều producer cạnh tranh một queue có capacity nhỏ.
- Producer bị interrupt trong lúc chờ.
- Interceptor trả `null` trong `preSend`.
- Handler lỗi sau khi message đã được nhận.
- Retry không tạo duplicate side effect.
- Ứng dụng restart khi message đang ở queue trong bộ nhớ và khi message ở durable broker.

## 13. Checklist thiết kế producer

- [ ] Chọn channel có semantics phù hợp: direct, queue, rendezvous, executor hay broker.
- [ ] Dùng capacity hữu hạn nếu cần giới hạn backlog trong bộ nhớ.
- [ ] Đặt send timeout theo latency budget của producer; tránh block vô hạn ngoài chủ đích.
- [ ] Kiểm tra cả `true`, `false` và exception từ `send()`.
- [ ] Không nhầm send timeout với handler processing timeout hoặc broker acknowledgment.
- [ ] Phân biệt queue full với interceptor rejection và executor rejection.
- [ ] Thiết kế retry có giới hạn, backoff và idempotency.
- [ ] Không giữ transaction/lock dài trong lúc chờ channel.
- [ ] Dùng outbox hoặc durable broker nếu yêu cầu không được mất message.
- [ ] Theo dõi queue depth, oldest message age, send latency và tỷ lệ timeout.
- [ ] Kiểm thử saturation, timeout, interrupt, recovery và duplicate handling.

Send timeout là một phần của chính sách backpressure giữa producer và channel. Khi capacity, timeout, retry và phản hồi quá tải được thiết kế cùng nhau, hệ thống có thể giới hạn tài nguyên bị giữ, bảo vệ consumer và thông báo rõ cho upstream khi không thể nhận thêm message. Điều đó quan trọng hơn việc chỉ tăng queue capacity hoặc kéo dài timeout để trì hoãn lúc quá tải xuất hiện.

## Tài liệu tham khảo

- [Spring Framework API: MessageChannel](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/messaging/MessageChannel.html)
- [Spring Integration Reference: Message Channels](https://docs.spring.io/spring-integration/reference/channel.html)
- [Spring Integration API: QueueChannel](https://docs.spring.io/spring-integration/docs/6.4.x/api/org/springframework/integration/channel/QueueChannel.html)
- [Spring Integration API: AbstractMessageChannel](https://docs.spring.io/spring-integration/docs/6.4.x/api/org/springframework/integration/channel/AbstractMessageChannel.html)
