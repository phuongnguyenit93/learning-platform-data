# Xử lý phát đồng thời và kết quả phát không thành công

Một nguồn reactive có thể nhận dữ liệu từ nhiều callback, thread hoặc thành phần độc lập. Ví dụ, một service tổng hợp sự kiện từ nhiều kết nối mạng, hoặc một adapter nhận callback đồng thời từ thư viện Java cũ. Nếu nhiều producer cùng phát vào một nguồn chia sẻ, thứ tự và tính hợp lệ của tín hiệu phải được kiểm soát. Việc phát cũng có thể thất bại vì nguồn đã kết thúc, bị hủy, không có subscriber hoặc không còn chỗ chứa dữ liệu.

Trong Reactor, `Sinks.Many<T>` cung cấp API phát dữ liệu chủ động và trả về kết quả rõ ràng qua `Sinks.EmitResult`. Hiểu kết quả này giúp chọn cách tuần tự hóa, thử lại hoặc xử lý sự kiện bị từ chối mà không làm mất dữ liệu âm thầm. Đây là một phần của việc tạo nguồn trong Reactive Programming: nguồn phải tuân thủ hợp đồng tín hiệu, phối hợp với backpressure và kết thúc đúng cách.

## 1. Vì sao phát đồng thời cần được quản lý?

Giả sử hai thread cùng phát sự kiện vào một sink:

```java
Sinks.Many<Event> sink = Sinks.many().multicast().onBackpressureBuffer();
Flux<Event> events = sink.asFlux();

// Hai producer có thể chạy đồng thời.
producerA.execute(() -> sink.tryEmitNext(eventA));
producerB.execute(() -> sink.tryEmitNext(eventB));
```

Hai lệnh phát có thể chạm vào cùng một sink tại cùng thời điểm. Nếu sink yêu cầu tín hiệu được phát tuần tự, một lời gọi có thể thành công trong khi lời gọi cạnh tranh nhận `FAIL_NON_SERIALIZED`. Kết quả này cho biết thao tác phát hiện tại không được chấp nhận vì một thao tác phát khác đang diễn ra; nó không có nghĩa sink đã nhận cả hai sự kiện.

Reactor Sinks được thiết kế để phát hiện một số trường hợp gọi đồng thời và báo lỗi phát thay vì âm thầm tạo chuỗi tín hiệu không hợp lệ. Điều này giúp ứng dụng quyết định rõ cách phối hợp producer. Đừng giả định rằng mọi sink đều tự xếp hàng mọi lời gọi đồng thời hoặc rằng thứ tự giữa các producer luôn xác định.

## 2. Tạo sink và kiểm tra kết quả phát

Một `Sinks.Many<T>` vừa là nơi producer phát tín hiệu, vừa cung cấp publisher để subscriber nhận dữ liệu:

```java
Sinks.Many<Event> sink = Sinks.many().multicast().onBackpressureBuffer();
Flux<Event> eventStream = sink.asFlux();

Sinks.EmitResult result = sink.tryEmitNext(new Event("order-created"));

if (result != Sinks.EmitResult.OK) {
    log.warn("Không phát được sự kiện: {}", result);
}
```

`asFlux()` tạo góc nhìn publisher cho downstream. Producer dùng `tryEmitNext` để phát một phần tử và nhận lại kết quả ngay. Cách gọi này hữu ích khi ứng dụng muốn tự quyết định chính sách với từng lần phát.

Các phương thức kết thúc như `tryEmitComplete()` và `tryEmitError(error)` cũng trả về `EmitResult`. Một sink chỉ có thể kết thúc một lần. Sau khi đã hoàn tất hoặc lỗi, các lần phát tiếp theo không thể tiếp tục chuỗi tín hiệu đó.

## 3. Ý nghĩa của các EmitResult

Các kết quả phổ biến cần được xử lý theo nguyên nhân:

| Kết quả | Ý nghĩa | Cách xử lý thường dùng |
| --- | --- | --- |
| `OK` | Tín hiệu đã được sink chấp nhận | Không cần thử lại |
| `FAIL_NON_SERIALIZED` | Có lời gọi phát khác đang cạnh tranh; thao tác này chưa được chấp nhận | Tuần tự hóa producer hoặc thử lại có giới hạn |
| `FAIL_TERMINATED` | Sink đã kết thúc bằng complete hoặc error | Không phát tiếp vào sink đó; chuyển sang vòng đời/nguồn mới nếu nghiệp vụ cho phép |
| `FAIL_CANCELLED` | Sink hoặc luồng phát đã bị hủy | Dừng producer hoặc giải phóng tài nguyên liên quan |
| `FAIL_OVERFLOW` | Bộ đệm của sink không thể nhận thêm phần tử | Áp dụng backpressure, giảm tốc độ, lưu bền vững hoặc chính sách overflow rõ ràng |
| `FAIL_ZERO_SUBSCRIBER` | Kiểu sink đang dùng không có subscriber để nhận và không giữ phần tử trong trạng thái đó | Chờ subscriber, lưu sự kiện ở nơi khác hoặc chọn sink có chính sách buffer phù hợp |

Kết quả có thể phụ thuộc loại sink và trạng thái subscription. Ví dụ, `multicast().onBackpressureBuffer()` có chính sách đệm riêng, trong khi các biến thể multicast trực tiếp có thể từ chối phát khi không có subscriber. Vì vậy, không nên xem `FAIL_ZERO_SUBSCRIBER` là kết quả luôn xảy ra hoặc không bao giờ xảy ra với mọi `Sinks.Many`.

Không nên gộp tất cả kết quả khác `OK` thành một lần retry chung. `FAIL_NON_SERIALIZED` thường là xung đột tạm thời giữa các producer. `FAIL_TERMINATED` và `FAIL_CANCELLED` là trạng thái vòng đời; retry trên cùng sink không thể làm sink sống lại. `FAIL_OVERFLOW` đòi hỏi giải quyết tốc độ tiêu thụ hoặc dung lượng. `FAIL_ZERO_SUBSCRIBER` cần quyết định có giữ dữ liệu để phát sau hay không.

## 4. Xử lý kết quả bằng tryEmitNext

Với `tryEmitNext`, producer tự kiểm tra kết quả và chọn hành động. Một mẫu xử lý có thể tách riêng từng loại thất bại:

```java
void publish(Event event) {
    Sinks.EmitResult result = sink.tryEmitNext(event);

    switch (result) {
        case OK -> { }
        case FAIL_NON_SERIALIZED -> retryQueue.offer(event);
        case FAIL_OVERFLOW -> durableQueue.store(event);
        case FAIL_ZERO_SUBSCRIBER -> pendingEvents.offer(event);
        case FAIL_TERMINATED, FAIL_CANCELLED -> stopProducer();
    }
}
```

Đây là khung chính sách minh họa; `retryQueue`, `durableQueue` và `pendingEvents` phải được triển khai theo yêu cầu thực tế. Nếu hệ thống không cho phép mất sự kiện, chỉ ghi log rồi bỏ phần tử là không đủ. Producer cần giữ lại payload, báo lỗi cho caller hoặc chuyển sự kiện vào hàng đợi bền vững.

Trong mã thực tế, nên gom việc diễn giải `EmitResult` vào một hàm riêng để tất cả producer áp dụng cùng chính sách. Nếu có thể, giữ nguyên event ID và thông tin thứ tự khi đưa một sự kiện bị từ chối vào hàng đợi retry; điều đó giúp tránh phát trùng và hỗ trợ đối soát.

## 5. Tuần tự hóa các producer

Cách dễ kiểm soát nhất là đưa mọi thao tác phát qua một hàng đợi hoặc một executor đơn luồng. Nhiều thread có thể gửi công việc vào executor, nhưng sink chỉ được gọi từ một thread phát:

```java
final class EventPublisher {
    private final Sinks.Many<Event> sink =
        Sinks.many().multicast().onBackpressureBuffer();
    private final ExecutorService emitter =
        Executors.newSingleThreadExecutor();

    Flux<Event> stream() {
        return sink.asFlux();
    }

    void publish(Event event) {
        emitter.execute(() -> {
            Sinks.EmitResult result = sink.tryEmitNext(event);
            if (result != Sinks.EmitResult.OK) {
                handleFailure(event, result);
            }
        });
    }

    void close() {
        emitter.execute(() -> sink.tryEmitComplete());
        emitter.shutdown();
    }
}
```

Mọi lệnh phát và lệnh complete được xếp vào cùng một executor, nên thứ tự thực hiện được tuần tự hóa theo thứ tự công việc vào hàng đợi. Trong ứng dụng thực, cần định nghĩa cách xử lý `RejectedExecutionException` nếu executor đã shutdown, cách chờ executor dừng và cách báo lỗi khi `tryEmitComplete()` không thành công. Nếu cần đóng ngay lập tức, hãy phối hợp dừng producer trước khi phát terminal signal.

Có thể dùng một khóa chung quanh lời gọi phát để tuần tự hóa, nhưng không nên thực hiện I/O blocking hoặc công việc lâu trong vùng khóa. Việc phát có thể gọi downstream đồng bộ tùy nguồn và scheduler; giữ khóa trong thời gian dài dễ làm producer khác bị nghẽn hoặc gây tương tác khó đoán. Một executor đơn luồng hoặc hàng đợi chuyên dụng thường giúp ranh giới phát rõ ràng hơn.

Thứ tự được bảo đảm bởi hàng đợi là thứ tự công việc được đưa vào hàng đợi. Nếu nghiệp vụ yêu cầu thứ tự theo timestamp, sequence number hoặc thứ tự giao dịch từ nhiều nguồn, hãy gắn thông tin thứ tự ở tầng miền nghiệp vụ và sắp xếp/đối soát trước khi phát. Đồng bộ hóa chỉ tuần tự hóa thao tác gọi sink, không tự xác định thứ tự nghiệp vụ mong muốn giữa các producer.

## 6. Thử lại khi gặp FAIL_NON_SERIALIZED

Nếu xung đột phát chỉ xảy ra ngắn hạn, có thể thử lại sau khi thao tác cạnh tranh kết thúc. Reactor cung cấp `Sinks.EmitFailureHandler` cho các phương thức `emitNext`:

```java
sink.emitNext(
    event,
    Sinks.EmitFailureHandler.busyLooping(Duration.ofMillis(100))
);
```

`busyLooping` thử lại khi thất bại do phát không được tuần tự hóa trong khoảng thời gian giới hạn. Tạo handler mới cho mỗi lần phát; không lưu và tái sử dụng một handler busy-looping cho nhiều sự kiện. Cách này có thể hữu ích khi xung đột ngắn và hiếm, nhưng nó tiêu thụ CPU trong lúc chờ và có thể làm tăng độ trễ khi cạnh tranh kéo dài.

Nếu sau thời gian chờ vẫn không phát được, `emitNext` sẽ báo thất bại bằng exception. Caller phải bắt và xử lý exception theo chính sách của ứng dụng. Không dùng busy loop kéo dài cho tải cao hoặc producer có thể liên tục cạnh tranh; hãy ưu tiên tuần tự hóa bằng executor/hàng đợi khi nhiều producer thường xuyên phát đồng thời.

Một handler tùy chỉnh có thể chỉ retry đúng trường hợp xung đột:

```java
Sinks.EmitFailureHandler retrySerializationConflict =
    (signalType, emitResult) ->
        emitResult == Sinks.EmitResult.FAIL_NON_SERIALIZED;

sink.emitNext(event, retrySerializationConflict);
```

Handler này cho phép retry không giới hạn nếu xung đột tiếp diễn, nên cần thêm giới hạn hoặc thời hạn nếu dùng trong hệ thống thực. Không trả về `true` cho `FAIL_OVERFLOW`, `FAIL_TERMINATED` hay `FAIL_CANCELLED`; các kết quả đó không được giải quyết bằng cách lặp lại cùng thao tác phát.

## 7. Xử lý overflow và backpressure

`FAIL_OVERFLOW` báo rằng sink không thể tiếp nhận thêm phần tử theo chính sách buffer hiện tại. Nguyên nhân thường là producer phát nhanh hơn khả năng tiêu thụ hoặc buffer đã đạt giới hạn. Việc retry ngay lập tức không giải quyết nguyên nhân nếu downstream vẫn chưa yêu cầu hoặc xử lý thêm dữ liệu.

Các chiến lược thường gặp:

- **Giảm tốc producer:** chỉ phát khi downstream có demand hoặc khi có tín hiệu cho phép tiếp tục.
- **Đệm có giới hạn:** đặt dung lượng tối đa và quyết định rõ khi đầy sẽ từ chối, bỏ phần tử cũ hay bỏ phần tử mới.
- **Lưu trữ bền vững:** chuyển sự kiện vào broker hoặc hàng đợi lưu trữ khi cần bảo đảm không mất dữ liệu.
- **Giới hạn tải:** điều tiết số producer, batch hoặc concurrency để tốc độ phát phù hợp năng lực downstream.

Không nên thay buffer hữu hạn bằng buffer vô hạn chỉ để tránh `FAIL_OVERFLOW`. Nếu producer liên tục nhanh hơn consumer, bộ nhớ sẽ tăng cho tới khi hệ thống không còn ổn định. Backpressure, giới hạn bộ nhớ và chính sách khi quá tải phải được thiết kế cùng nhau.

## 8. Terminal signal và vòng đời của sink

Khi nguồn không còn phát dữ liệu, producer có thể kết thúc bằng `tryEmitComplete()` hoặc báo lỗi bằng `tryEmitError(error)`:

```java
Sinks.EmitResult completion = sink.tryEmitComplete();
if (completion != Sinks.EmitResult.OK) {
    log.warn("Không thể hoàn tất sink: {}", completion);
}
```

Sau khi sink đã complete hoặc error, nó không thể nhận thêm `onNext`. `FAIL_TERMINATED` là dấu hiệu producer đang gửi dữ liệu vào một nguồn đã kết thúc. Không nên tạo vòng retry vô hạn cho kết quả này. Nếu ứng dụng cần một phiên phát mới, hãy tạo một sink mới với lifecycle và publisher mới, rồi chuyển subscriber sang nguồn mới theo thiết kế của ứng dụng.

Khi sink đã bị hủy, `FAIL_CANCELLED` cũng báo rằng vòng đời phát hiện tại không còn hoạt động. Producer nên dừng, giải phóng callback/listener hoặc chuyển dữ liệu sang thành phần sở hữu phiên tiếp theo. Đừng nhầm `cancel` với `complete`: cancel thường đến từ việc subscriber hoặc operator hủy subscription; complete là terminal signal do nguồn phát.

Các lệnh phát dữ liệu và lệnh kết thúc cũng phải được phối hợp. Nếu một thread gọi complete trong khi thread khác đang phát, một trong các thao tác có thể thất bại do cạnh tranh hoặc do sink đã kết thúc. Đưa `tryEmitNext`, `tryEmitError` và `tryEmitComplete` qua cùng cơ chế tuần tự hóa để xác định thứ tự kết thúc và tránh producer tiếp tục phát sau khi shutdown.

## 9. Kiểm thử kết quả phát và trạng thái terminal

Có thể kiểm thử trực tiếp `EmitResult` và tín hiệu downstream bằng `StepVerifier`. Ví dụ dưới đây dùng sink unicast để kiểm tra phát thành công, hoàn tất và từ chối phát sau terminal signal:

```java
Sinks.Many<Integer> sink = Sinks.many().unicast().onBackpressureBuffer();

StepVerifier.create(sink.asFlux())
    .then(() -> assertEquals(Sinks.EmitResult.OK, sink.tryEmitNext(1)))
    .then(() -> assertEquals(Sinks.EmitResult.OK, sink.tryEmitComplete()))
    .expectNext(1)
    .verifyComplete();

assertEquals(
    Sinks.EmitResult.FAIL_TERMINATED,
    sink.tryEmitNext(2)
);
```

Subscriber được đăng ký khi `StepVerifier` bắt đầu xác minh; các lệnh phát trong `then` diễn ra sau khi subscription đã được thiết lập. Sau `tryEmitComplete`, phần tử `1` được chuyển tới downstream rồi luồng hoàn tất. Lần phát `2` xảy ra sau đó nên nhận `FAIL_TERMINATED`.

Để kiểm thử producer đồng thời, hãy xác minh cả số sự kiện được chấp nhận, số sự kiện bị từ chối và chính sách retry/queue. Không chỉ kiểm tra rằng không có exception: một producer có thể đã bỏ qua kết quả thất bại mà không làm test ném lỗi. Với grace period, timeout hoặc scheduler, dùng virtual time và công cụ đồng bộ hóa phù hợp để test không phụ thuộc vào `Thread.sleep` tùy ý.

## 10. Chọn chính sách phát theo yêu cầu của nguồn

Khi một nguồn có nhiều producer, hãy quyết định trước cách tuần tự hóa và cách xử lý mỗi loại `EmitResult`. Nếu producer có thể phối hợp qua một executor đơn luồng, đây thường là cách đơn giản để duy trì thứ tự phát. Nếu xung đột chỉ thoáng qua, `EmitFailureHandler` có giới hạn có thể là lựa chọn phù hợp. Nếu buffer đầy, cần giải quyết tốc độ và dung lượng. Nếu sink đã kết thúc hoặc bị hủy, producer phải dừng hoặc chuyển sang một vòng đời mới. Nếu không có subscriber, hãy chọn rõ giữa giữ dữ liệu, chờ subscriber hoặc từ chối sự kiện.

Không bỏ qua kết quả từ `tryEmitNext`, `tryEmitComplete` hay `tryEmitError`. Mỗi kết quả là thông tin về việc sink đã nhận tín hiệu hay chưa và lý do thao tác bị từ chối. Kết hợp kiểm tra `EmitResult`, tuần tự hóa producer, chính sách backpressure và quản lý terminal signal giúp nguồn reactive phát dữ liệu đồng thời một cách có kiểm soát trong hệ sinh thái Java.
