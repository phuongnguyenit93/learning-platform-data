# Không làm thay đổi payload ngoài hợp đồng

Trong Spring Integration, `ChannelInterceptor` là điểm mở rộng nằm trên đường gửi hoặc nhận message của một channel. Nó phù hợp để thực hiện các tác vụ xuyên suốt như kiểm tra hợp đồng message, gắn metadata kỹ thuật, ghi nhận thời gian xử lý hoặc áp dụng chính sách truy cập. Interceptor không nên âm thầm thay đổi dữ liệu nghiệp vụ trong payload.

Một nguyên tắc quan trọng của thiết kế message flow là mỗi component chỉ thay đổi dữ liệu theo đúng trách nhiệm và hợp đồng đã công bố. Nếu một bước cần chuyển đổi payload, hãy biểu diễn việc đó bằng `Transformer` hoặc một endpoint xử lý có tên và đầu ra rõ ràng. Nếu interceptor chỉ cần bổ sung thông tin vận hành, hãy thay đổi header và giữ nguyên payload.

## 1. Payload là dữ liệu nghiệp vụ của message

Một Spring `Message<?>` gồm hai phần:

- **Payload:** nội dung chính mà consumer xử lý, chẳng hạn `OrderCommand`, `PaymentRequest`, một chuỗi hoặc một đối tượng domain.
- **Headers:** metadata đi kèm như `id`, `timestamp`, `correlationId`, `sequenceNumber`, `contentType` hoặc các header do ứng dụng định nghĩa.

Message và header của message được thiết kế theo hướng bất biến: không sửa trực tiếp một message đã tạo. Khi cần tạo message mới từ message cũ, dùng `MessageBuilder`. Tuy nhiên, tính bất biến của lớp `Message` không làm cho object payload tự động bất biến. Nếu payload là một object mutable, nhiều component vẫn có thể giữ cùng tham chiếu và sửa các field bên trong object đó.

Ví dụ, hai message có thể khác nhau ở header nhưng cùng trỏ đến một object payload:

```java
OrderCommand command = new OrderCommand("ORD-42", 3);

Message<OrderCommand> first = MessageBuilder.withPayload(command)
        .setHeader("source", "web")
        .build();

Message<OrderCommand> second = MessageBuilder.fromMessage(first)
        .setHeader("traceId", "trace-7f2")
        .build();

// first.getPayload() == second.getPayload() là true.
```

`MessageBuilder.fromMessage` giữ nguyên payload đang có và tạo message mới với header được cập nhật. Nó không clone sâu payload. Vì vậy, interceptor không được coi việc tạo message mới là giấy phép để sửa object payload cũ.

## 2. Hợp đồng của ChannelInterceptor

Các hook của `ChannelInterceptor` cho phép quan sát hoặc can thiệp vào vòng đời send/receive:

| Hook | Thời điểm | Cách dùng phù hợp |
| --- | --- | --- |
| `preSend(message, channel)` | Trước khi channel gửi message | Kiểm tra loại payload, header bắt buộc, quyền gửi; có thể trả lại message với metadata kỹ thuật được bổ sung |
| `postSend(message, channel, sent)` | Sau khi channel thực hiện send | Ghi nhận kết quả gửi và metric; `sent` cho biết channel có chấp nhận message hay không |
| `afterSendCompletion(message, channel, sent, ex)` | Khi quá trình send hoàn tất | Dọn tài nguyên hoặc ghi nhận kết quả cuối cùng, kể cả khi send phát sinh exception |
| `preReceive(channel)` | Trước khi pollable channel nhận message | Quyết định có thực hiện lần receive này hay không |
| `postReceive(message, channel)` | Sau khi pollable channel nhận được message | Quan sát message vừa lấy; nếu trả về message khác, phải giữ nguyên hợp đồng payload |
| `afterReceiveCompletion(message, channel, ex)` | Khi quá trình receive hoàn tất | Dọn tài nguyên hoặc ghi nhận kết quả receive |

Các hook receive chỉ có ý nghĩa với channel hỗ trợ thao tác poll/receive, chẳng hạn `QueueChannel`. `DirectChannel` và `ExecutorChannel` là subscribable channel; chúng không lấy message bằng poller nên không có chu trình receive tương ứng.

`preSend` có thể trả về `null` để ngăn message được gửi tiếp. Đây là hành vi chặn message có chủ đích, gần với một filter ở tầng channel. Không dùng `null` như cách biểu thị lỗi kiểm tra hoặc vô tình làm rơi message. Nếu payload không đáp ứng hợp đồng, hãy phát sinh lỗi rõ ràng hoặc chuyển quyết định lọc đến một `MessageFilter` có chủ đích.

## 3. Giữ nguyên payload khi kiểm tra hợp đồng

Một interceptor có thể kiểm tra payload mà không sửa nó. Ví dụ sau chỉ cho phép channel nhận `OrderCommand`:

```java
public final class OrderPayloadContractInterceptor
        implements ChannelInterceptor {

    @Override
    public Message<?> preSend(
            Message<?> message,
            MessageChannel channel) {

        if (!(message.getPayload() instanceof OrderCommand)) {
            throw new IllegalArgumentException(
                    "ordersChannel chỉ chấp nhận OrderCommand");
        }

        return message;
    }
}
```

Interceptor trả về chính message nhận được. Nó không sửa payload, không thay đổi header và không tạo side effect nghiệp vụ. Nếu cần kiểm tra sâu hơn, hãy đọc các field và xác thực điều kiện; không gọi setter hoặc sửa collection nằm bên trong payload.

Đăng ký interceptor trực tiếp vào channel:

```java
@Bean
DirectChannel ordersChannel() {
    DirectChannel channel = new DirectChannel();
    channel.addInterceptor(new OrderPayloadContractInterceptor());
    return channel;
}
```

Mọi message đi qua `ordersChannel` sẽ được kiểm tra trước khi dispatcher chuyển đến subscriber. Nếu channel dùng chung cho nhiều loại message hợp lệ, hãy định nghĩa hợp đồng rõ ràng cho từng loại hoặc dùng các channel chuyên biệt. Một interceptor kiểm tra sai phạm vi có thể chặn nhầm message hợp lệ.

## 4. Bổ sung metadata mà không đổi payload

Nhiều interceptor cần gắn thông tin kỹ thuật như trace ID. Hãy tạo message mới từ message hiện tại và chỉ cập nhật header:

```java
public final class TraceHeaderInterceptor implements ChannelInterceptor {

    private static final String TRACE_ID = "traceId";

    @Override
    public Message<?> preSend(
            Message<?> message,
            MessageChannel channel) {

        if (message.getHeaders().containsKey(TRACE_ID)) {
            return message;
        }

        return MessageBuilder.fromMessage(message)
                .setHeader(TRACE_ID, UUID.randomUUID().toString())
                .build();
    }
}
```

Ví dụ này chỉ tạo trace ID khi message chưa có. Khi đã có ID từ upstream, interceptor giữ nguyên để trace xuyên suốt nhiều channel. Payload của message mới vẫn là cùng object payload của message đầu vào.

Không nên ghi đè các header có ý nghĩa nghiệp vụ hoặc correlation nếu không thuộc quyền sở hữu của interceptor. Đặc biệt, `correlationId`, `sequenceNumber` và `sequenceSize` có thể được các endpoint như aggregator dùng để ghép message. Thay đổi chúng có thể làm hỏng luồng correlation dù payload vẫn còn nguyên.

Một số quy tắc khi bổ sung header:

- Chỉ thêm header thuộc phạm vi trách nhiệm của interceptor.
- Dùng tên header ổn định và thống nhất giữa các flow.
- Giữ nguyên giá trị header do producer hoặc upstream tạo nếu interceptor không phải chủ sở hữu của giá trị đó.
- Không đưa bí mật, token truy cập hoặc dữ liệu cá nhân vào header chỉ để tiện log.
- Không giả định mọi header tùy chỉnh đều được giữ nguyên qua mọi adapter hoặc hệ thống trung gian; hãy xác minh mapping của từng integration boundary.

## 5. Những thay đổi payload cần tránh

Các ví dụ sau vi phạm ranh giới trách nhiệm của interceptor nếu hợp đồng channel không công bố việc biến đổi đó:

```java
// Không làm: thay đổi object payload đang được chia sẻ.
OrderCommand command = (OrderCommand) message.getPayload();
command.setQuantity(0);

// Không làm: thay payload bằng một kiểu dữ liệu khác trong interceptor.
return MessageBuilder.withPayload(command.toString()).build();
```

Việc sửa object payload có thể ảnh hưởng đến producer, các subscriber khác hoặc một nhánh xử lý đang chạy song song. Việc thay kiểu payload còn có thể khiến consumer phía sau nhận dữ liệu không đúng kiểu mà endpoint mong đợi.

Rủi ro đặc biệt rõ với `PublishSubscribeChannel`: nhiều subscriber có thể cùng nhận message và cùng tham chiếu đến một payload mutable. Nếu một nhánh sửa object, nhánh khác có thể quan sát trạng thái đã bị thay đổi. Với `ExecutorChannel`, các worker thread có thể xử lý message đồng thời; việc sửa payload dùng chung có thể tạo race condition. Vì vậy, nên dùng payload immutable như record, value object bất biến hoặc cấu trúc dữ liệu chỉ đọc.

Nếu cần chuyển đổi nghiệp vụ, đặt một `Transformer` trong flow để thể hiện đầu vào và đầu ra:

```java
@Bean
IntegrationFlow normalizeOrderFlow() {
    return IntegrationFlow.from("rawOrdersChannel")
            .transform(RawOrder.class, raw ->
                    new OrderCommand(raw.orderId(), normalizeQuantity(raw.quantity())))
            .channel("ordersChannel")
            .get();
}
```

Khi đó, sự thay đổi từ `RawOrder` sang `OrderCommand` là một bước được đặt tên trong message flow. Consumer sau transformer có thể dựa vào hợp đồng mới mà không cần đoán rằng một interceptor đã âm thầm thay payload.

## 6. Phân biệt interceptor với các endpoint xử lý message

| Thành phần | Trách nhiệm chính | Có nên thay payload? |
| --- | --- | --- |
| `ChannelInterceptor` | Quan sát và áp dụng chính sách xuyên suốt tại ranh giới channel | Giữ nguyên theo mặc định; chỉ thay đổi message trong phạm vi hợp đồng kỹ thuật rõ ràng |
| `Transformer` | Chuyển đổi dữ liệu đầu vào thành dữ liệu đầu ra | Có; đây là trách nhiệm chính |
| `MessageFilter` | Quyết định message có được đi tiếp hay không | Không cần đổi payload; có thể loại message không đạt điều kiện |
| `HeaderEnricher` | Bổ sung hoặc tính toán metadata | Giữ nguyên payload, thay đổi header theo cấu hình |
| `ServiceActivator` | Thực thi nghiệp vụ hoặc gọi service | Có thể tạo kết quả message mới theo hợp đồng endpoint |

Nếu yêu cầu là xác thực payload, dùng interceptor để kiểm tra ở ranh giới channel hoặc dùng validator ở endpoint phù hợp. Nếu yêu cầu là chuẩn hóa dữ liệu, dùng transformer. Nếu yêu cầu là bỏ qua message không đạt điều kiện, dùng filter. Nếu yêu cầu là thêm metadata nghiệp vụ hoặc kỹ thuật, cân nhắc header enricher hoặc interceptor tùy phạm vi áp dụng.

## 7. Lưu ý theo loại channel và threading

Interceptor chạy trong đường gọi channel, vì vậy thời điểm hook được gọi và ý nghĩa của kết quả phụ thuộc loại channel:

- **`DirectChannel`:** `preSend`, `postSend` và `afterSendCompletion` nằm trong đường gửi đồng bộ. Handler được gọi trên thread gửi. Nếu interceptor làm I/O chậm, producer cũng bị chậm.
- **`ExecutorChannel`:** interceptor quan sát việc gửi và giao task cho executor. `postSend` không có nghĩa handler nghiệp vụ đã hoàn tất; worker có thể tiếp tục xử lý sau khi lời gọi gửi kết thúc.
- **`QueueChannel`:** send đưa message vào queue; các hook receive được gọi khi poller hoặc consumer lấy message. Interceptor không nên sửa payload sau khi message đã được đưa vào queue.
- **`PublishSubscribeChannel`:** message được fan-out đến các subscriber. Tránh payload mutable vì nhiều nhánh có thể quan sát cùng dữ liệu và chạy đồng thời nếu có executor.

Không đặt truy vấn cơ sở dữ liệu, gọi HTTP hoặc xử lý nghiệp vụ nặng trong `preSend` chỉ để “tiện” kiểm tra. Interceptor nằm trên đường gửi nên chi phí đó có thể làm tăng latency cho mọi producer. Nếu kiểm tra cần truy cập dữ liệu bên ngoài, hãy cân nhắc endpoint nghiệp vụ riêng, timeout rõ ràng và error flow phù hợp.

## 8. Kiểm thử hợp đồng payload

Một kiểm thử tốt cần chứng minh interceptor không làm thay đổi payload, đồng thời xác nhận metadata được xử lý đúng:

```java
@Test
void shouldPreservePayloadWhenAddingTraceHeader() {
    OrderCommand payload = new OrderCommand("ORD-42", 3);
    Message<OrderCommand> original = MessageBuilder
            .withPayload(payload)
            .build();

    TraceHeaderInterceptor interceptor = new TraceHeaderInterceptor();
    Message<?> result = interceptor.preSend(original, new DirectChannel());

    assertSame(payload, result.getPayload());
    assertNotNull(result.getHeaders().get("traceId"));
    assertNull(original.getHeaders().get("traceId"));
}
```

Ngoài kiểm tra trên, nên xác minh các trường hợp sau:

1. Payload đúng kiểu và hợp lệ được gửi đi mà không thay đổi giá trị hoặc tham chiếu.
2. Payload sai hợp đồng bị từ chối bằng lỗi có thể chẩn đoán; interceptor không tự thay nó thành một kiểu khác.
3. Header `traceId` đã tồn tại được giữ nguyên qua interceptor.
4. Các header correlation và sequence không bị ghi đè.
5. Với payload mutable, interceptor không gọi setter hoặc sửa collection lồng bên trong.
6. Với `ExecutorChannel` và `PublishSubscribeChannel`, nhiều consumer chạy đồng thời không quan sát payload bị interceptor sửa ngoài dự kiến.

Nếu hợp đồng yêu cầu bất biến sâu, chỉ kiểm tra `assertSame` là chưa đủ. Hãy dùng payload immutable hoặc tạo snapshot trong kiểm thử và so sánh toàn bộ trạng thái trước/sau. Nếu payload được phép mutable theo hợp đồng, cần ghi rõ component nào sở hữu quyền thay đổi và thời điểm quyền sở hữu được chuyển giao.

## 9. Chẩn đoán khi payload bị thay đổi ngoài dự kiến

Khi consumer nhận payload khác với dữ liệu producer gửi, hãy khoanh vùng theo đường đi message:

1. Ghi nhận `messageId`, `correlationId`, tên channel, endpoint và thread xử lý; tránh log toàn bộ payload nhạy cảm.
2. Tìm các interceptor đã đăng ký trên channel, bao gồm interceptor toàn cục và interceptor cục bộ.
3. Kiểm tra `preSend` và `postReceive` xem có trả về message mới với payload khác hay không.
4. Tìm component nào giữ tham chiếu đến payload mutable và gọi setter hoặc sửa collection.
5. Kiểm tra các nhánh `PublishSubscribeChannel`, worker của `ExecutorChannel` và các lần retry có thể dùng chung dữ liệu.
6. Đặt kiểm thử snapshot ở ranh giới producer, channel và consumer để xác định bước đầu tiên làm thay đổi payload.

Khi cần log để điều tra, ưu tiên log kiểu payload, kích thước, ID kỹ thuật hoặc hash đã được thiết kế phù hợp. Log payload đầy đủ có thể làm lộ dữ liệu nhạy cảm và tăng chi phí serialize.

## 10. Quy tắc thiết kế nên áp dụng

- Xem payload là dữ liệu nghiệp vụ có hợp đồng rõ ràng; interceptor không tự ý thay đổi nó.
- Ưu tiên payload immutable để tránh chia sẻ trạng thái mutable giữa các consumer.
- Chỉ tạo message mới trong interceptor khi cần bổ sung metadata hoặc thực hiện chính sách channel đã được công bố.
- Giữ nguyên các header nghiệp vụ, correlation và sequence nếu interceptor không sở hữu chúng.
- Dùng transformer cho mọi chuyển đổi payload có ý nghĩa nghiệp vụ.
- Dùng filter cho quyết định chấp nhận/loại message và nêu rõ lý do loại.
- Giữ interceptor ngắn, nhanh, dễ quan sát và an toàn khi được gọi đồng thời.
- Viết kiểm thử xác nhận cả giá trị payload lẫn tham chiếu payload được giữ nguyên khi chỉ thay đổi header.

Trong một message flow có nhiều channel và endpoint, tính nhất quán của payload giúp mỗi consumer có thể dựa vào hợp đồng đã công bố. `ChannelInterceptor` nên bảo vệ và quan sát ranh giới đó; mọi biến đổi nghiệp vụ cần xuất hiện thành một bước rõ ràng trong flow.
