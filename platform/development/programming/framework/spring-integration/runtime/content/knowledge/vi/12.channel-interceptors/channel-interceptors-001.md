# ChannelInterceptor trước và sau send

Trong Spring Integration, `MessageChannel` là ranh giới mà producer gửi message vào và consumer nhận message từ đó. **`ChannelInterceptor`** cho phép quan sát hoặc thay đổi message tại ranh giới này mà không phải sửa từng producer hay handler.

Interceptor thường dùng cho các concern xuyên suốt như logging có kiểm soát, metrics, tracing, audit metadata, kiểm tra điều kiện kỹ thuật hoặc chặn message theo chính sách hạ tầng. Với một interceptor, có thể xử lý trước khi send, sau khi send, và ở thời điểm send hoàn tất để dọn tài nguyên.

Điều quan trọng là hiểu đúng ý nghĩa từng callback. `preSend` có thể thay message hoặc chặn send; `postSend` quan sát kết quả trả về của thao tác send; `afterSendCompletion` dùng để cleanup kể cả khi có exception. Các callback receive chỉ áp dụng cho `PollableChannel`.

## 1. ChannelInterceptor nằm ở đâu trong message flow?

Một flow cơ bản có producer, channel và consumer:

~~~mermaid
flowchart LR
    A["Producer"] --> B["preSend"]
    B --> C["MessageChannel"]
    C --> D["postSend"]
    D --> E["Consumer / Handler"]
    B -. "send hoàn tất hoặc lỗi" .-> F["afterSendCompletion"]
~~~

`ChannelInterceptor` chặn thao tác trên channel. Nó không phải một endpoint nghiệp vụ riêng và không thay thế transformer, filter, router hay service activator.

Các package thường dùng:

- `org.springframework.messaging.Message` và `MessageChannel` mô tả message và channel.
- `org.springframework.messaging.support.ChannelInterceptor` định nghĩa interceptor.
- `org.springframework.messaging.support.InterceptableChannel` cung cấp khả năng đăng ký interceptor trực tiếp trên channel.
- `org.springframework.integration.config.GlobalChannelInterceptor` dùng để đăng ký interceptor toàn cục theo pattern tên channel.

Một interceptor có thể áp dụng cho một channel hoặc nhiều channel. Nếu cùng một logic logging, metrics hoặc policy cần chạy ở nhiều ranh giới, global interceptor giúp tránh cấu hình lặp lại.

## 2. Sáu callback của ChannelInterceptor

Interface có sáu callback chính:

~~~java
public interface ChannelInterceptor {

    Message<?> preSend(Message<?> message, MessageChannel channel);

    void postSend(Message<?> message, MessageChannel channel, boolean sent);

    void afterSendCompletion(
            Message<?> message,
            MessageChannel channel,
            boolean sent,
            Exception ex);

    boolean preReceive(MessageChannel channel);

    Message<?> postReceive(Message<?> message, MessageChannel channel);

    void afterReceiveCompletion(
            Message<?> message,
            MessageChannel channel,
            Exception ex);
}
~~~

Các method trong interface hiện đại có default implementation no-op hoặc trả lại message/giá trị mặc định. Vì vậy class chỉ cần override callback thực sự sử dụng.

| Callback | Thời điểm | Có thể thay đổi luồng? |
|---|---|---|
| `preSend` | Trước khi channel thực hiện send | Trả message mới hoặc `null` để chặn send |
| `postSend` | Ngay sau lời gọi send | Quan sát boolean `sent`, không thay message |
| `afterSendCompletion` | Khi send hoàn tất, kể cả có exception | Cleanup; nhận trạng thái `sent` và exception |
| `preReceive` | Trước khi channel poll/receive | Trả `false` để không thực hiện receive |
| `postReceive` | Sau khi lấy được message, trước khi trả cho consumer | Trả message đã chỉnh sửa hoặc `null` để dừng chuỗi interceptor |
| `afterReceiveCompletion` | Khi receive hoàn tất, kể cả có exception | Cleanup; nhận message và exception |

`preReceive`, `postReceive` và `afterReceiveCompletion` chỉ liên quan đến `PollableChannel`. `SubscribableChannel` không có API `receive()`; message được dispatch trực tiếp đến subscriber khi producer gửi vào channel.

## 3. preSend: kiểm tra hoặc biến đổi message trước khi gửi

`preSend` nhận message sắp được gửi và channel đích. Nó có thể:

- Trả lại message ban đầu nếu không cần thay đổi.
- Tạo message mới bằng `MessageBuilder` để thêm hoặc cập nhật header.
- Ném exception nếu có lỗi kỹ thuật hoặc vi phạm điều kiện cần dừng send.
- Trả `null` để chặn thao tác send.

Ví dụ thêm header nguồn cho message đi vào channel đơn hàng:

~~~java
@Component
class SourceHeaderInterceptor implements ChannelInterceptor {

    @Override
    public Message<?> preSend(
            Message<?> message,
            MessageChannel channel) {

        return MessageBuilder.fromMessage(message)
                .setHeaderIfAbsent("app.channel", "orders.input")
                .build();
    }
}
~~~

Message và `MessageHeaders` được thiết kế theo hướng bất biến. Vì vậy, khi cần thay header, hãy tạo message mới bằng `MessageBuilder`; không sửa trực tiếp map header.

### Trả null có nghĩa là chặn send

Một interceptor có thể chủ động từ chối message:

~~~java
@Override
public Message<?> preSend(
        Message<?> message,
        MessageChannel channel) {

    if (!isAllowed(message)) {
        return null;
    }

    return message;
}
~~~

Khi `preSend` trả `null`, lời gọi send thực tế không diễn ra. Đây là một lần veto, không phải một message rỗng. Producer thường quan sát kết quả send là `false`; cần kiểm tra cách caller xử lý kết quả này.

Dùng cơ chế này cho policy kỹ thuật ở ranh giới channel. Nếu điều kiện là quy tắc nghiệp vụ như đơn hàng có hợp lệ hay không, thường nên dùng `MessageFilter` hoặc handler trong flow để quyết định rõ ràng và có thể quan sát kết quả nghiệp vụ.

Không nên trả `null` âm thầm mà không có metric hoặc log phù hợp. Nếu không, message bị chặn có thể trông giống như message chưa từng được gửi.

## 4. postSend: quan sát kết quả lời gọi send

`postSend` chạy ngay sau thao tác send của channel và nhận boolean `sent`. Giá trị này phản ánh kết quả trả về của lời gọi send.

- `sent=true`: channel chấp nhận send theo semantics của nó.
- `sent=false`: send không thành công theo kết quả boolean, ví dụ do timeout hoặc không thể chấp nhận message.
- Nếu send ném exception, cần xử lý exception ở `afterSendCompletion`; không giả định mọi đường lỗi đều có một lần `postSend` bình thường.

Ví dụ đếm số lần send không thành công:

~~~java
@Component
class SendOutcomeInterceptor implements ChannelInterceptor {

    private final MeterRegistry registry;

    SendOutcomeInterceptor(MeterRegistry registry) {
        this.registry = registry;
    }

    @Override
    public void postSend(
            Message<?> message,
            MessageChannel channel,
            boolean sent) {

        if (!sent) {
            registry.counter(
                    "integration.channel.send",
                    "channel", channelName(channel),
                    "outcome", "not-sent")
                    .increment();
        }
    }

    private String channelName(MessageChannel channel) {
        return channel.toString();
    }
}
~~~

Trong production, nên dùng tên channel ổn định do ứng dụng quản lý thay vì phụ thuộc `toString()` nếu giá trị đó không phải hợp đồng định danh. Tag metric phải có cardinality thấp.

`sent=true` chỉ xác nhận channel đã nhận send theo hợp đồng của channel. Nó không chứng minh consumer đã xử lý xong, database đã commit hay hệ thống đích đã hoàn tất nghiệp vụ. Với `QueueChannel`, message có thể mới được đưa vào queue; với `ExecutorChannel`, task có thể mới được dispatch cho executor.

## 5. afterSendCompletion: cleanup sau khi send kết thúc

`afterSendCompletion` được gọi sau khi send hoàn tất, bất kể thao tác có ném exception hay không, để interceptor có thể giải phóng tài nguyên hoặc hoàn tất phép đo.

Method nhận:

- `message`: message tham gia vào thao tác send.
- `channel`: channel đang được gọi.
- `sent`: kết quả boolean của send nếu có.
- `ex`: exception nếu send gặp lỗi; có thể là `null`.

Callback này được gọi khi `preSend` của interceptor đã chạy thành công và trả về một `Message`. Nếu chính `preSend` trả `null`, `afterSendCompletion` của interceptor đó không được gọi. Điều này cần được tính đến khi thiết kế việc mở/đóng tài nguyên.

Ví dụ ghi duration của lời gọi send bằng `ThreadLocal` stack:

~~~java
@Component
class SendTimingInterceptor implements ChannelInterceptor {

    private final MeterRegistry registry;
    private final ThreadLocal<Deque<Long>> starts =
            ThreadLocal.withInitial(ArrayDeque::new);

    SendTimingInterceptor(MeterRegistry registry) {
        this.registry = registry;
    }

    @Override
    public Message<?> preSend(
            Message<?> message,
            MessageChannel channel) {

        starts.get().push(System.nanoTime());
        return message;
    }

    @Override
    public void afterSendCompletion(
            Message<?> message,
            MessageChannel channel,
            boolean sent,
            Exception ex) {

        Deque<Long> stack = starts.get();

        try {
            if (!stack.isEmpty()) {
                long elapsed = System.nanoTime() - stack.pop();
                String outcome = ex != null
                        ? "error"
                        : sent ? "sent" : "not-sent";

                Timer.builder("integration.channel.send.duration")
                        .tag("channel", "orders.input")
                        .tag("outcome", outcome)
                        .register(registry)
                        .record(elapsed, TimeUnit.NANOSECONDS);
            }
        }
        finally {
            if (stack.isEmpty()) {
                starts.remove();
            }
        }
    }
}
~~~

Stack thay vì một giá trị đơn giúp xử lý trường hợp send lồng nhau trên cùng thread. `ThreadLocal` được xóa khi stack rỗng để tránh giữ dữ liệu trên thread pool lâu dài.

Phép đo này là thời gian của lời gọi send tại channel:

- Với `DirectChannel`, nó có thể bao gồm thời gian subscriber/handler chạy đồng bộ.
- Với `ExecutorChannel`, nó thường đo thời gian dispatch/handoff sang executor, không phải thời gian worker xử lý handler.
- Với `QueueChannel`, nó đo thao tác đưa message vào queue, có thể bao gồm thời gian producer chờ nếu queue đầy.

Muốn đo handler time, hãy instrument handler hoặc dùng cơ chế quan sát riêng ở execution boundary. Không diễn giải send duration thành end-to-end processing time.

## 6. Luồng callback và thứ tự thực thi

Trong cùng một lời gọi send, `preSend` luôn đứng trước `postSend`. `afterSendCompletion` chạy khi thao tác send kết thúc và các callback completion được gọi theo thứ tự ngược với các callback pre tương ứng, tương tự quá trình unwind của stack.

Với nhiều interceptor đăng ký theo thứ tự A rồi B, có thể hình dung:

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant A as Interceptor A
    participant B as Interceptor B
    participant C as Channel
    P->>A: preSend
    A->>B: preSend
    B->>C: send
    C-->>B: kết quả send
    B-->>A: postSend
    B-->>A: afterSendCompletion (reverse cleanup)
    A-->>P: trả kết quả
~~~

Sơ đồ thể hiện các pha chính; chi tiết callback `postSend` và xử lý lỗi phụ thuộc đường thực thi của channel. Điều có thể dựa vào là `preSend` trước `postSend`, và các callback completion chạy sau thao tác tương ứng theo thứ tự đảo ngược của chuỗi pre.

### Không suy luận thứ tự send và receive giữa hai thread

Với `QueueChannel`, sender và receiver có thể chạy trên hai thread khác nhau. Nếu receiver đã chờ sẵn, trình tự quan sát có thể là:

- `preSend`
- `preReceive`
- `postReceive`
- `postSend`

Nếu sender đã gửi xong trước khi receiver poll, trình tự có thể là:

- `preSend`
- `postSend`
- Một khoảng thời gian chờ
- `preReceive`
- `postReceive`

Vì vậy không được giả định callback send luôn hoàn tất trước callback receive. Chỉ dựa vào thứ tự nội bộ của từng thao tác send hoặc receive.

## 7. preReceive và postReceive trên PollableChannel

Các callback receive chỉ được gọi khi consumer lấy message từ `PollableChannel`, ví dụ `QueueChannel` hoặc `PriorityChannel`.

`preReceive` chạy trước khi lấy message. Trả `false` để bỏ qua thao tác receive trong lần gọi đó. Điều này có thể dùng cho điều kiện kỹ thuật như circuit breaker hoặc trạng thái bảo trì, nhưng cần có metric để biết receive đang bị chặn.

`postReceive` chạy sau khi message được lấy ra nhưng trước khi trả cho caller. Nó có thể trả message mới hoặc `null` để ngăn message đi tiếp qua chuỗi interceptor/đến consumer.

Ví dụ thêm metadata sau khi nhận:

~~~java
@Override
public Message<?> postReceive(
        Message<?> message,
        MessageChannel channel) {

    if (message == null) {
        return null;
    }

    return MessageBuilder.fromMessage(message)
            .setHeader("app.receivedFrom", "orders.queue")
            .build();
}
~~~

Từ Spring Integration 5.1, `postReceive` không còn được gọi khi không có message được nhận. Nếu cần cleanup hoặc đo cả trường hợp receive trả `null`, hãy dùng `afterReceiveCompletion`, callback này được gọi khi receive hoàn tất nếu `preReceive` đã trả `true`.

`afterReceiveCompletion` nhận message có thể là `null` và exception có thể có giá trị. Callback này thích hợp để giải phóng tài nguyên hoặc kết thúc timer mở trong `preReceive`.

## 8. Đăng ký interceptor trực tiếp trên channel

Nếu chỉ muốn áp dụng interceptor cho một channel, có thể đăng ký trực tiếp trên channel triển khai `InterceptableChannel`.

~~~java
@Bean
DirectChannel ordersInput(
        SourceHeaderInterceptor interceptor) {

    DirectChannel channel = new DirectChannel();
    channel.addInterceptor(interceptor);
    return channel;
}
~~~

Cách này phù hợp khi interceptor chỉ có ý nghĩa với một channel hoặc khi cấu hình channel được kiểm soát ngay tại nơi tạo bean.

XML cũng hỗ trợ cấu hình interceptor cục bộ:

~~~xml
<int:channel id="ordersInput">
    <int:interceptors>
        <ref bean="sourceHeaderInterceptor"/>
    </int:interceptors>
</int:channel>
~~~

Nên tách implementation interceptor thành bean riêng để dễ tái sử dụng, kiểm thử và quản lý dependency.

## 9. Đăng ký global interceptor

Nếu một interceptor cần áp dụng cho nhiều channel, dùng `@GlobalChannelInterceptor`:

~~~java
@Configuration
class ChannelInterceptorConfiguration {

    @Bean
    @GlobalChannelInterceptor(
            patterns = {"orders.*", "payments.*"},
            order = -1)
    ChannelInterceptor auditChannelInterceptor(
            MeterRegistry registry) {
        return new AuditChannelInterceptor(registry);
    }
}
~~~

`patterns` chọn channel theo tên. Pattern `*` mặc định khớp mọi channel; từ Spring Integration 5.0, pattern phủ định bắt đầu bằng `!` cũng được hỗ trợ. Ví dụ `!internal.*` loại trừ nhóm channel nội bộ theo quy tắc pattern của framework.

`order` quyết định vị trí interceptor toàn cục so với interceptor khác trên channel:

- Giá trị âm đặt interceptor trước các interceptor khai báo trực tiếp.
- Giá trị dương đặt interceptor sau các interceptor khai báo trực tiếp.
- Giá trị mặc định là `0`.

Từ Spring Integration 5.1, global interceptor cũng áp dụng cho channel được đăng ký động, ví dụ thông qua `IntegrationFlowContext` hoặc bean được khởi tạo sau khi application context refresh. Nếu ứng dụng dùng phiên bản cũ hơn, hãy xác minh hành vi trên flow động.

XML có cấu hình tương đương bằng `<int:channel-interceptor>` với `pattern` và `order`.

## 10. ChannelInterceptor và ExecutorChannelInterceptor

`ChannelInterceptor` quan sát ranh giới gửi/nhận của channel. Với `ExecutorChannel`, send có thể chỉ dispatch message sang executor rồi trả về trước khi handler chạy.

Nếu cần callback bao quanh chính lần gọi `MessageHandler` trên worker thread, Spring Messaging có `ExecutorChannelInterceptor`. Interface này mở rộng khả năng intercept cho execution của handler, ví dụ:

- `beforeHandle`: trước khi handler được gọi trên worker.
- `afterMessageHandled`: sau khi handler hoàn tất hoặc ném exception.

Đây là ranh giới khác với `postSend` và `afterSendCompletion`:

| Mục tiêu | Dùng |
|---|---|
| Đo thời gian producer gửi vào channel | `ChannelInterceptor` |
| Biết channel có chấp nhận send hay không | `postSend` |
| Cleanup sau khi send hoàn tất | `afterSendCompletion` |
| Đo thời gian task chờ worker | Instrument executor/`TaskDecorator` |
| Đo thời gian handler thực sự chạy trên executor | `ExecutorChannelInterceptor` hoặc instrumentation ở handler |

Không dùng `postSend` để kết luận handler đã xử lý xong trên `ExecutorChannel`. Callback đó chỉ thuộc thao tác send/dispatch ở phía producer.

## 11. WireTap là một interceptor có sẵn

Spring Integration cung cấp `WireTap` để gửi một bản message sang channel phụ nhằm logging, giám sát hoặc kiểm thử mà không thay đổi đường đi chính của message.

Ví dụ global wire tap:

~~~java
@Bean
@GlobalChannelInterceptor(patterns = "orders.*")
WireTap ordersWireTap(
        @Qualifier("orders.audit") MessageChannel auditChannel) {
    return new WireTap(auditChannel);
}
~~~

WireTap hữu ích để quan sát message flow mà không phải thêm service activator chỉ để copy message. Tuy nhiên, cần tránh vòng lặp: nếu audit channel lại khớp pattern của cùng wire tap, message có thể bị gửi lặp vô hạn. Hãy loại trừ channel đích bằng pattern hoặc cơ chế veto phù hợp.

Với interceptor tùy chỉnh giữ tham chiếu đến một channel khác, cân nhắc `VetoCapableInterceptor` để tránh áp dụng interceptor lên chính channel mà nó sử dụng. Đây là cách ngăn circular reference và recursive interception.

## 12. Thread safety và hiệu năng của interceptor

Interceptor bean thường là singleton và có thể được gọi đồng thời từ nhiều thread. Vì vậy:

- Không lưu message hiện tại vào một field mutable dùng chung.
- Nếu cần state theo lần gọi, dùng state gắn với thread và luôn cleanup trong callback completion, hoặc dùng cấu trúc đồng thời có khóa/ID rõ ràng.
- Không giữ tham chiếu message/payload lâu hơn cần thiết.
- Tránh gọi API từ xa hoặc truy vấn database đồng bộ trong `preSend`.
- Giữ logic callback ngắn và có timeout nếu phải chạm dependency.
- Không log toàn bộ payload hoặc header nhạy cảm.

`preSend` chạy trên đường gửi của producer. Nếu callback block 100 ms, producer cũng phải chịu phần latency đó. Với `DirectChannel`, downstream handler còn có thể chạy đồng bộ trong cùng send call; interceptor chậm sẽ làm tăng latency toàn flow.

Không nên dùng interceptor như nơi triển khai toàn bộ nghiệp vụ. Interceptor phù hợp với concern xuyên suốt ở channel boundary; filter, router, transformer và service activator phù hợp hơn cho logic nghiệp vụ có ý nghĩa riêng.

## 13. Lỗi và giới hạn của callback

Các callback có thể ném `RuntimeException`. Điều này có thể làm send/receive thất bại hoặc làm thay đổi kết quả quan sát của producer/consumer.

Một số tình huống cần phân biệt:

| Tình huống | Hành vi cần hiểu |
|---|---|
| `preSend` trả `null` | Send thực tế không được gọi; callback completion của interceptor trả `null` không chạy |
| `preSend` ném exception | Send bị dừng trước khi channel xử lý message |
| Channel trả `false` | `postSend` nhận `sent=false`; completion vẫn có thể chạy |
| Channel ném exception | Dùng `afterSendCompletion` để cleanup; exception được truyền theo đường send |
| `preReceive` trả `false` | Receive không được thực hiện |
| `postReceive` trả `null` | Message không tiếp tục đến caller qua chuỗi interceptor |
| Receive không có message | Từ Spring Integration 5.1, `postReceive` không được gọi; `afterReceiveCompletion` vẫn là điểm cleanup |

`afterSendCompletion` và `afterReceiveCompletion` được gọi theo thứ tự ngược với các callback pre tương ứng, cho phép giải phóng tài nguyên theo kiểu stack. Không ném exception mới từ callback cleanup nếu không có lý do rõ ràng; exception trong cleanup có thể che khuất lỗi ban đầu hoặc làm kết quả send khó phân tích.

Interceptor không tự tạo retry hoặc transaction. Nếu cần retry handler, dùng advice phù hợp; nếu cần transaction cho polling hoặc handler, cấu hình transaction boundary ở endpoint/poller theo thiết kế.

## 14. Security và audit ở channel boundary

Channel interceptor có thể là nơi áp dụng một số policy kỹ thuật, nhưng phải xác định rõ ranh giới tin cậy.

- Chỉ log metadata cần thiết; redact token, cookie, authorization và dữ liệu cá nhân.
- Không tin header `tenantId`, `userId` hoặc `role` đến từ caller nếu chưa được xác thực.
- Nếu bổ sung audit header, dùng namespace rõ ràng như `app.audit.*`.
- Không cho header không tin cậy quyết định channel nội bộ hoặc đường đi nhạy cảm nếu chưa kiểm tra.
- Nếu chặn send bằng `preSend`, ghi nhận số lần chặn và lý do dưới dạng metric/log an toàn.
- Không đưa payload hoặc ID nghiệp vụ có cardinality cao vào metric tags.

Audit interceptor nên ghi nhận event metadata như tên channel, loại thao tác, kết quả send và correlation ID đã được chuẩn hóa theo chính sách log. Nếu cần lưu audit bền vững, cân nhắc một flow audit riêng hoặc outbox thay vì thực hiện ghi database đồng bộ trong mọi `preSend`.

## 15. Kiểm thử ChannelInterceptor

Kiểm thử nên xác nhận cả callback và ảnh hưởng lên message flow.

Các trường hợp cơ bản:

1. `preSend` trả lại message ban đầu và message được gửi bình thường.
2. `preSend` tạo message mới; consumer nhận được header đã bổ sung.
3. `preSend` trả `null`; subscriber không nhận message và send bị veto.
4. `postSend` nhận đúng giá trị `sent`.
5. `afterSendCompletion` chạy khi send hoàn tất bình thường và khi có exception.
6. `afterSendCompletion` không chạy cho interceptor có `preSend` trả `null`.
7. `preReceive=false` ngăn pollable channel lấy message.
8. `postReceive` có thể thay đổi message trước khi consumer nhận.
9. `afterReceiveCompletion` cleanup kể cả khi không có message hoặc receive ném exception.
10. Global interceptor chỉ áp dụng đúng các channel khớp pattern.

Ví dụ kiểm thử đơn giản với `DirectChannel`:

~~~java
@Test
void preSendAddsHeaderBeforeHandler() {
    DirectChannel channel = new DirectChannel();
    channel.addInterceptor(new SourceHeaderInterceptor());

    AtomicReference<Message<?>> received = new AtomicReference<>();
    channel.subscribe(received::set);

    channel.send(MessageBuilder.withPayload("order-1").build());

    assertThat(received.get()).isNotNull();
    assertThat(received.get().getHeaders())
            .containsEntry("app.channel", "orders.input");
}
~~~

Với `QueueChannel`, cần kiểm thử riêng các callback receive. Với `ExecutorChannel`, dùng latch hoặc test executor để xác nhận khác biệt giữa thời điểm send hoàn tất và thời điểm handler thực sự chạy. Tránh dựa vào `Thread.sleep()` dài để suy luận thứ tự callback giữa các thread.

## 16. Checklist khi đưa interceptor vào production

Trước khi bật interceptor trên channel thật, hãy kiểm tra:

- Interceptor đang gắn vào channel nào và theo pattern nào?
- Callback nào thực sự cần override?
- `preSend` có trả message mới đúng cách hoặc có thể veto ngoài ý muốn không?
- `postSend` có phân biệt `sent=false` với exception không?
- `afterSendCompletion` có cleanup đầy đủ và không che lỗi gốc không?
- Receive callback có chỉ được kỳ vọng trên `PollableChannel` không?
- Global interceptor có áp dụng lên dynamic channel theo phiên bản đang dùng không?
- `order` có đặt đúng vị trí so với interceptor cục bộ và global khác không?
- Interceptor singleton có thread-safe và cleanup ThreadLocal không?
- Callback có làm chậm producer hoặc giữ scheduler/consumer thread không?
- Có vòng lặp WireTap hoặc recursive interception không?
- Metric tags có cardinality thấp và log đã redact dữ liệu nhạy cảm chưa?
- Test đã bao gồm success, veto, false send, exception và concurrency chưa?

`ChannelInterceptor` hữu ích nhất khi giữ đúng phạm vi: quan sát và áp dụng concern kỹ thuật tại ranh giới channel. Hiểu rõ `preSend`, `postSend` và `afterSendCompletion` giúp đo đúng thời gian, xử lý lỗi đúng nơi và tránh nhầm việc channel nhận message với việc handler đã hoàn thành nghiệp vụ.

## Tài liệu tham khảo

Các tài liệu dưới đây mô tả API và semantics theo phiên bản Spring Framework/Spring Integration. Hãy đối chiếu dependency của ứng dụng trước khi áp dụng chi tiết callback hoặc cấu hình global interceptor.

- [Spring Integration — Channel Interceptors](https://docs.spring.io/spring-integration/reference/channel/interceptors.html)
- [Spring Integration — Configuring Message Channels](https://docs.spring.io/spring-integration/reference/channel/configuration.html)
- [Spring Framework — ChannelInterceptor Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/ChannelInterceptor.html)
- [Spring Integration — GlobalChannelInterceptor API](https://docs.spring.io/spring-integration/docs/latest-ga/api/org/springframework/integration/config/GlobalChannelInterceptor.html)
- [Spring Integration — Wire Tap](https://docs.spring.io/spring-integration/reference/channel/interceptors.html)

