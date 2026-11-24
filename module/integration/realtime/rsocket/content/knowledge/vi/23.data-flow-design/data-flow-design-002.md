# Phát dữ liệu qua Reactor Sinks và xử lý kết quả phát thất bại

Trong một ứng dụng realtime, dữ liệu có thể đến từ callback của thiết bị, listener của thư viện, message broker hoặc một thread xử lý nền. Những nguồn này thường phát dữ liệu theo kiểu imperative: khi có sự kiện thì gọi một hàm để đẩy giá trị đi. Trong khi đó, phần còn lại của ứng dụng lại sử dụng Reactor với `Mono` và `Flux`. **Reactor Sinks** là cầu nối cho phép ứng dụng chủ động phát tín hiệu reactive và cung cấp một `Flux` hoặc `Mono` để các thành phần khác subscribe.

Gọi `tryEmitNext` không có nghĩa giá trị chắc chắn đã đến mọi subscriber. Sink trả về `Sinks.EmitResult` để mô tả trạng thái tại thời điểm phát. Producer phải hiểu kết quả đó và quyết định giữ lại, thử lại, bỏ, ghi log hoặc kết thúc luồng. Nếu bỏ qua kết quả phát, ứng dụng có thể mất sự kiện khi buffer đầy, phát đồng thời sai cách hoặc tiếp tục gửi vào một sink đã kết thúc.

Bài học này tập trung vào cách chọn loại sink, phát dữ liệu, đọc từng trạng thái thất bại và tích hợp luồng sự kiện vào RSocket request-stream trong Spring.

Sau bài học, bạn có thể:

- Giải thích vai trò của `Sinks` trong một pipeline Reactor.
- Chọn `Sinks.One` hoặc `Sinks.Many` theo số lượng phần tử và subscriber.
- Phân biệt unicast, multicast, direct và replay sink.
- Sử dụng `tryEmitNext`, `tryEmitComplete` và `tryEmitError`.
- Xử lý `OK`, `FAIL_OVERFLOW`, `FAIL_ZERO_SUBSCRIBER`, `FAIL_CANCELLED`, `FAIL_TERMINATED` và `FAIL_NON_SERIALIZED`.
- Thiết kế chính sách overflow, retry và tuần tự hóa nhiều producer.
- Kết nối `Sinks.Many` với `@MessageMapping` và RSocket request-stream.
- Kiểm thử kết quả phát và cancellation bằng StepVerifier.

## 1. Sinks giải quyết vấn đề gì?

Một `Flux` thường mô tả cách tạo dữ liệu từ một nguồn: đọc database, gọi HTTP, nhận message hoặc kết hợp các publisher. Nhưng đôi khi dữ liệu được đẩy vào từ bên ngoài pipeline. Ví dụ:

- Thư viện thiết bị gọi callback khi có số đo mới.
- Listener của broker nhận một event.
- Một tác vụ nền tính xong trạng thái.
- Một API imperative gọi `publish(event)` để thông báo cho các subscriber.
- Một server RSocket cần phát dữ liệu realtime tới các client đang theo dõi.

Có thể dùng `Sinks` để tạo một publisher có thể phát thủ công:

~~~java
Sinks.Many<String> sink =
    Sinks.many().multicast().onBackpressureBuffer();

Flux<String> events = sink.asFlux();

Sinks.EmitResult result = sink.tryEmitNext("connected");
~~~

`asFlux()` cung cấp view để downstream subscribe. Producer gọi `tryEmitNext` để phát một phần tử. Sink kiểm tra trạng thái và trả về `EmitResult` thay vì để ứng dụng gọi trực tiếp `Subscriber.onNext`.

~~~mermaid
flowchart LR
    A[External callback] --> B[Publisher service]
    B --> C[Sinks.Many]
    C --> D[asFlux]
    D --> E[Reactor operators]
    E --> F[RSocket request-stream]
    F --> G[Remote client]
    C --> H[EmitResult]
    H --> I[Success or failure policy]
~~~

`Sinks` phù hợp khi ứng dụng cần một điểm phát dữ liệu imperative có thể được dùng như Publisher. Nếu nguồn dữ liệu đã là `Flux` hoặc `Mono`, hãy compose trực tiếp publisher đó khi có thể; không cần bọc mọi nguồn reactive bằng sink.

## 2. Chọn Sinks.One hay Sinks.Many

Reactor có hai nhóm sink chính:

| Loại | Số phần tử | View | Trường hợp sử dụng |
|---|---:|---|---|
| `Sinks.One<T>` | Tối đa một giá trị | `Mono<T>` | Kết quả của một thao tác bất đồng bộ |
| `Sinks.Empty<T>` | Không phát giá trị | `Mono<T>` | Chỉ cần complete hoặc error |
| `Sinks.Many<T>` | Nhiều giá trị | `Flux<T>` | Event stream, broadcast hoặc queue |

### Sinks.One cho một kết quả

~~~java
Sinks.One<PaymentReceipt> resultSink = Sinks.one();

Mono<PaymentReceipt> result = resultSink.asMono();

resultSink.tryEmitValue(
    new PaymentReceipt("payment-42", "APPROVED")
);
~~~

`Sinks.One` có thể phát một giá trị, hoàn tất rỗng hoặc phát lỗi. Khi đã nhận một tín hiệu terminal, sink không thể được dùng để phát kết quả thứ hai.

### Sinks.Empty cho complete hoặc error

~~~java
Sinks.Empty<Void> completionSink = Sinks.empty();

Mono<Void> completion = completionSink.asMono();

completionSink.tryEmitEmpty();
~~~

Dùng `Sinks.Empty` khi cần biểu diễn một thao tác hoàn tất mà không có response value.

### Sinks.Many cho luồng sự kiện

~~~java
Sinks.Many<PriceTick> priceSink =
    Sinks.many().multicast().onBackpressureBuffer(128);

Flux<PriceTick> prices = priceSink.asFlux();
~~~

`Sinks.Many` phù hợp khi nhiều sự kiện được phát theo thời gian và một hoặc nhiều subscriber cần nhận chúng. Phải chọn đúng chính sách subscriber, replay và backpressure trước khi đưa sink vào production.

## 3. Các loại Sinks.Many

Không có một sink phù hợp cho mọi tình huống. Sự khác nhau nằm ở số subscriber, hành vi với subscriber đến muộn và cách xử lý demand.

| Factory | Subscriber | Dữ liệu đến trước subscriber | Backpressure và replay |
|---|---|---|---|
| `many().unicast().onBackpressureBuffer()` | Một | Được buffer | Tôn trọng demand của subscriber duy nhất |
| `many().multicast().onBackpressureBuffer()` | Nhiều | Warm-up buffer có giới hạn | Tôn trọng demand chậm nhất, có buffer |
| `many().multicast().directBestEffort()` | Nhiều | Không buffer | Subscriber chậm có thể bỏ lỡ item |
| `many().multicast().directAllOrNothing()` | Nhiều | Không buffer | Nếu một subscriber thiếu demand, lần phát bị từ chối cho tất cả |
| `many().replay().limit(n)` | Nhiều | Lưu lịch sử | Subscriber mới nhận lại tối đa n item gần nhất |
| `many().replay().all()` | Nhiều | Lưu toàn bộ | Replay không giới hạn lịch sử |

### Unicast: một consumer

~~~java
Sinks.Many<WorkItem> workQueue =
    Sinks.many().unicast().onBackpressureBuffer();
~~~

Unicast chỉ cho phép một subscriber đăng ký vào `asFlux()`. Các phần tử được phát trước khi subscriber đăng ký sẽ được giữ lại trong queue và phát sau khi subscriber bắt đầu yêu cầu dữ liệu.

Queue mặc định có thể không giới hạn. Nếu producer nhanh hơn consumer trong thời gian dài, bộ nhớ có thể tăng liên tục. Với tải lớn, hãy cung cấp queue có giới hạn và hỗ trợ semantics single-producer/single-consumer theo hợp đồng của API. Khi queue đầy, producer cần xử lý việc không thể nhận thêm phần tử.

### Multicast có buffer: nhiều consumer

~~~java
Sinks.Many<PriceTick> broadcast =
    Sinks.many().multicast().onBackpressureBuffer(128);
~~~

Multicast gửi các phần tử mới tới các subscriber hiện tại. Nó không phải replay sink: subscriber mới không tự nhận lại toàn bộ lịch sử đã phát trước khi đăng ký. Khi nhiều subscriber có tốc độ khác nhau, sink phải tôn trọng demand chậm nhất và dùng buffer cho phần chênh lệch.

`bufferSize` giới hạn khả năng đệm. Nếu một subscriber chậm quá mức và buffer không còn chỗ, `tryEmitNext` có thể trả `FAIL_OVERFLOW`. Producer cần có chính sách rõ ràng cho tình huống đó.

Multicast mặc định tự hủy khi tất cả subscriber hủy đăng ký. Nếu cần sink tiếp tục tồn tại để các client mới đăng ký sau đó, có thể cấu hình `autoCancel`:

~~~java
Sinks.Many<PriceTick> broadcast =
    Sinks.many().multicast().onBackpressureBuffer(128, false);
~~~

Khi đặt `autoCancel` thành false, sink không tự đóng chỉ vì subscriber cuối cùng đã hủy. Ứng dụng vẫn phải gọi complete/error khi vòng đời của event source kết thúc.

### DirectBestEffort: ưu tiên subscriber nhanh

~~~java
Sinks.Many<PriceTick> liveTicks =
    Sinks.many().multicast().directBestEffort();
~~~

Nếu một subscriber không có demand, subscriber đó có thể bỏ lỡ phần tử mới; các subscriber còn demand vẫn nhận được. Nếu không subscriber nào có demand để nhận, lần phát trả về `FAIL_OVERFLOW`.

Đây là lựa chọn cho dữ liệu cập nhật liên tục mà giá trị mới có thể thay thế giá trị cũ, ví dụ vị trí hiện tại hoặc giá thị trường tức thời. Không dùng nó cho lệnh thanh toán, giao dịch hoặc sự kiện cần mọi consumer nhận đủ.

### DirectAllOrNothing: tất cả cùng nhận hoặc không ai nhận

~~~java
Sinks.Many<DomainEvent> coordinated =
    Sinks.many().multicast().directAllOrNothing();
~~~

Nếu bất kỳ subscriber nào không có demand, lần phát bị từ chối cho tất cả subscriber. Các subscriber không bị kết thúc chỉ vì lần phát đó thất bại; producer nhận kết quả và quyết định chính sách tiếp theo.

Dùng khi các subscriber phải quan sát cùng một tập sự kiện hoặc producer cần biết có subscriber nào đang chậm. Hãy nhớ rằng `FAIL_OVERFLOW` ở đây có thể xảy ra dù không có queue bị đầy; nguyên nhân là thiếu demand.

### Replay: phát lại lịch sử có giới hạn

~~~java
Sinks.Many<AuditEvent> recentEvents =
    Sinks.many().replay().limit(100);
~~~

Replay sink giữ lại lịch sử và phát các phần tử đó cho subscriber đến muộn trước khi tiếp tục phát dữ liệu mới. Có thể giới hạn theo số phần tử hoặc khoảng thời gian:

~~~java
Sinks.Many<AuditEvent> recentEvents =
    Sinks.many().replay().limit(100);

Sinks.Many<AuditEvent> recentByTime =
    Sinks.many().replay().limit(Duration.ofMinutes(5));
~~~

`replay().all()` lưu toàn bộ lịch sử và có thể làm bộ nhớ tăng không giới hạn. Chỉ dùng khi số phần tử hữu hạn và được kiểm soát. Với event log dài hạn, hãy dùng broker hoặc kho lưu trữ có retention thay vì giữ toàn bộ trong heap của một tiến trình.

## 4. Phát dữ liệu bằng tryEmitNext

`tryEmitNext(value)` là API phát một phần tử và trả ngay `Sinks.EmitResult`. Đây thường là lựa chọn phù hợp khi ứng dụng muốn tự quyết định cách xử lý thất bại.

~~~java
Sinks.Many<String> sink =
    Sinks.many().multicast().onBackpressureBuffer(64);

Sinks.EmitResult result = sink.tryEmitNext("price-updated");

if (result.isSuccess()) {
    log.debug("Sink accepted the event");
} else {
    log.warn("Cannot emit event: {}", result);
}
~~~

Các trạng thái `EmitResult` thường gặp:

| Kết quả | Ý nghĩa | Hướng xử lý |
|---|---|---|
| `OK` | Sink chấp nhận tín hiệu | Ghi nhận accepted; không đồng nghĩa mọi client đã xử lý |
| `FAIL_OVERFLOW` | Buffer/demand không còn khả năng nhận | Drop có chủ đích, retry có giới hạn, persist hoặc giảm tốc producer |
| `FAIL_ZERO_SUBSCRIBER` | Không có subscriber và sink không thể buffer tín hiệu | Giữ lại, bỏ theo chính sách hoặc chờ subscriber |
| `FAIL_CANCELLED` | Sink đã bị consumer hủy/ngắt | Dừng phát hoặc tạo sink mới theo lifecycle |
| `FAIL_TERMINATED` | Sink đã complete hoặc error | Không retry trên sink đã terminal |
| `FAIL_NON_SERIALIZED` | Nhiều producer gọi đồng thời không được tuần tự hóa | Tuần tự hóa hoặc retry contention có giới hạn |

Các trạng thái có thể khác nhau tùy loại sink. Ví dụ unicast có thể buffer trước subscriber; direct multicast không buffer trước subscriber. Không suy ra hành vi của một factory từ factory khác.

### OK không có nghĩa là client đã nhận

`OK` chỉ nói rằng sink chấp nhận tín hiệu theo trạng thái tại thời điểm gọi. Subscriber có thể xử lý phần tử bất đồng bộ sau đó; subscriber cũng có thể hủy ngay sau khi producer phát. Do đó, không dùng kết quả `OK` làm xác nhận giao dịch nghiệp vụ hoặc xác nhận mọi RSocket client đã nhận dữ liệu.

Nếu nghiệp vụ cần xác nhận xử lý, hãy thiết kế acknowledgement riêng: ví dụ client gửi ACK với event ID, hoặc server ghi trạng thái đã giao/đã xử lý trong một store.

## 5. Phát tín hiệu terminal

`Sinks.Many` có thể kết thúc bằng complete hoặc error:

~~~java
Sinks.EmitResult completed = sink.tryEmitComplete();

Sinks.EmitResult failed =
    sink.tryEmitError(new IllegalStateException("Source unavailable"));
~~~

Terminal signal kết thúc publisher. Sau khi sink đã complete hoặc error, không thể dùng lại để phát phần tử mới. Những lần gọi tiếp theo thường nhận `FAIL_TERMINATED`.

Nên gắn terminal signal với vòng đời của nguồn dữ liệu:

- Gọi `tryEmitComplete()` khi nguồn hoàn tất bình thường.
- Gọi `tryEmitError(error)` khi muốn kết thúc toàn bộ stream bằng lỗi.
- Không gửi `onError` cho một sự kiện lỗi đơn lẻ nếu luồng còn có thể tiếp tục. Trong trường hợp đó, biểu diễn lỗi như một event data, chẳng hạn `PriceFeedStatus.UNAVAILABLE`.
- Nếu cần khởi động lại nguồn sau terminal signal, tạo sink mới và thay thế trong connection/event manager theo lifecycle rõ ràng.

`FAIL_TERMINATED` là dấu hiệu producer đang phát vào một publisher đã kết thúc. Thử lại cùng thao tác trên chính sink đó không thể khôi phục luồng.

## 6. Xử lý FAIL_OVERFLOW

`FAIL_OVERFLOW` có nghĩa sink không thể nhận thêm phần tử theo chính sách backpressure hiện tại. Nguyên nhân có thể là queue đầy hoặc subscriber không có demand, tùy loại sink.

Không nên xử lý mọi overflow bằng cách gọi `tryEmitNext` liên tục trong vòng lặp. Nếu consumer vẫn chậm, retry ngay sẽ chỉ lặp lại thất bại và làm producer chiếm CPU.

Hãy chọn một trong các chính sách phù hợp với ý nghĩa dữ liệu:

| Chính sách | Khi phù hợp | Đánh đổi |
|---|---|---|
| Drop latest | Event mới ít quan trọng hơn dữ liệu đang chờ | Mất cập nhật mới |
| Drop oldest | Chỉ cần trạng thái mới nhất | Mất lịch sử cũ |
| Coalesce | Nhiều event có thể gộp thành một trạng thái | Cần quy tắc gộp đúng |
| Retry sau backoff | Overflow có tính tạm thời | Tăng latency và cần giới hạn |
| Persist vào broker/database | Không được mất event | Thêm I/O và cơ chế replay |
| Reject producer | Caller có thể giảm tốc hoặc thử lại | Cần truyền lỗi ngược về caller |

Ví dụ trả kết quả rõ ràng cho caller:

~~~java
public enum PublishStatus {
    ACCEPTED,
    BACKPRESSURED,
    NO_SUBSCRIBER,
    CLOSED,
    CANCELLED,
    CONCURRENT_EMISSION
}

public PublishStatus publish(PriceTick tick) {
    return switch (sink.tryEmitNext(tick)) {
        case OK -> PublishStatus.ACCEPTED;
        case FAIL_OVERFLOW -> PublishStatus.BACKPRESSURED;
        case FAIL_ZERO_SUBSCRIBER -> PublishStatus.NO_SUBSCRIBER;
        case FAIL_TERMINATED -> PublishStatus.CLOSED;
        case FAIL_CANCELLED -> PublishStatus.CANCELLED;
        case FAIL_NON_SERIALIZED -> PublishStatus.CONCURRENT_EMISSION;
    };
}
~~~

Caller có thể quyết định tiếp tục, ghi event vào hàng đợi bền vững hoặc trả trạng thái quá tải. Không nên biến `BACKPRESSURED` thành `ACCEPTED` nếu event thực tế chưa được sink nhận.

## 7. Xử lý FAIL_ZERO_SUBSCRIBER

`FAIL_ZERO_SUBSCRIBER` xảy ra khi sink không có subscriber và loại sink đó không thể lưu phần tử tại thời điểm phát. Đây không nhất thiết là lỗi hệ thống; có thể đơn giản là chưa có client nào theo dõi.

Chính sách phụ thuộc nghiệp vụ:

- Với telemetry tức thời, có thể bỏ event nếu không có người nghe.
- Với trạng thái mới nhất, lưu snapshot gần nhất để client lấy khi kết nối.
- Với event bắt buộc giao, ghi vào broker/database và phát lại khi có subscriber.
- Với một luồng chỉ được tạo sau khi client subscribe, trì hoãn việc khởi tạo nguồn tới thời điểm có subscription.

Phân biệt hành vi trước subscriber:

| Sink | Khi chưa có subscriber |
|---|---|
| Unicast có buffer | Giữ phần tử để subscriber duy nhất nhận sau |
| Multicast có buffer | Có warm-up buffer với giới hạn |
| Direct multicast | Thường từ chối phát ngay |
| Replay | Lưu lịch sử để subscriber đến muộn nhận lại |

Không dựa vào `currentSubscriberCount()` để quyết định chắc chắn lần phát tiếp theo thành công. Đây chỉ là ảnh chụp trạng thái tại một thời điểm; subscriber có thể hủy hoặc đăng ký ngay sau khi kiểm tra. Hãy luôn xử lý kết quả `tryEmitNext`.

## 8. Xử lý FAIL_TERMINATED và FAIL_CANCELLED

`FAIL_TERMINATED` có nghĩa sink đã nhận complete hoặc error trước đó. Hãy tìm nguyên nhân terminal signal và kết thúc producer tương ứng. Không retry cùng sink.

`FAIL_CANCELLED` cho biết sink đã bị consumer hủy/ngắt theo semantics của sink. Đây thường là tín hiệu lifecycle: subscriber hoặc nguồn liên quan không còn hoạt động.

Ví dụ quản lý lifecycle:

~~~java
public void stop() {
    Sinks.EmitResult result = sink.tryEmitComplete();

    if (result == Sinks.EmitResult.OK) {
        log.info("Event stream completed");
    } else if (result == Sinks.EmitResult.FAIL_TERMINATED) {
        log.debug("Event stream was already terminated");
    } else {
        log.warn("Cannot complete event stream: {}", result);
    }
}
~~~

Không gọi complete khi chỉ một RSocket subscriber hủy request-stream nếu sink còn phục vụ các subscriber khác. Subscription của một client và lifecycle của sink dùng chung là hai phạm vi khác nhau.

## 9. Xử lý FAIL_NON_SERIALIZED khi có nhiều producer

Các sink an toàn mặc định phát hiện trường hợp nhiều thread gọi đồng thời. Nếu hai producer cạnh tranh cùng phát một tín hiệu, một lần phát có thể nhận `FAIL_NON_SERIALIZED`. Điều này giúp tránh vi phạm Reactive Streams và lỗi khó đoán ở downstream.

Có ba cách xử lý phổ biến:

1. Tuần tự hóa các lần phát bằng một executor hoặc scheduler duy nhất.
2. Đồng bộ đoạn phát nếu số producer ít và critical section ngắn.
3. Dùng `emitNext` với failure handler retry contention trong thời gian giới hạn.

Ví dụ đồng bộ việc phát:

~~~java
public final class SerializedEventPublisher {

    private final Object emitLock = new Object();

    private final Sinks.Many<DomainEvent> sink =
        Sinks.many().multicast().onBackpressureBuffer(128);

    public Sinks.EmitResult publish(DomainEvent event) {
        synchronized (emitLock) {
            return sink.tryEmitNext(event);
        }
    }

    public Flux<DomainEvent> events() {
        return sink.asFlux();
    }
}
~~~

Cách này tuần tự hóa các producer cùng dùng `emitLock`. Giữ đoạn synchronized ngắn; không thực hiện I/O, gọi dịch vụ hoặc chờ subscriber bên trong lock.

Nếu producer đến từ callback có thể chạy trên event-loop, hãy tránh thao tác blocking trong critical section. Với tải cao, thường tốt hơn là chuyển event vào một luồng producer tuần tự có queue giới hạn, rồi để một producer duy nhất gọi sink.

Không chọn `Sinks.unsafe().many()` chỉ để giảm một ít overhead. Unsafe sink bỏ cơ chế phát hiện producer cạnh tranh và yêu cầu ứng dụng tự bảo đảm tuần tự hóa mọi tín hiệu. Chỉ cân nhắc trong thành phần nội bộ đã kiểm soát chặt nguồn gọi; API dùng chung của ứng dụng nên giữ safe sink mặc định.

### Retry contention có giới hạn

`emitNext(value, failureHandler)` có thể thử lại khi failure handler yêu cầu. Reactor cung cấp `Sinks.EmitFailureHandler.busyLooping(Duration)` để chờ contention trong một khoảng thời gian giới hạn:

~~~java
sink.emitNext(
    event,
    Sinks.EmitFailureHandler.busyLooping(Duration.ofMillis(500))
);
~~~

Đây là ví dụ cho contention ngắn và hiếm. Mỗi lần gọi nên tạo handler mới; không cache và tái sử dụng một handler `busyLooping`. Reactor khuyến nghị thời gian chờ thực tế lớn hơn 100 ms. Busy loop tiêu thụ CPU trong lúc chờ nên không phù hợp để che giấu tranh chấp kéo dài hoặc overflow do consumer chậm.

`busyLooping` chỉ giúp xử lý contention có thể biến mất. Nó không tạo thêm buffer khi `FAIL_OVERFLOW`, không mở lại sink đã terminal và không tạo subscriber mới.

## 10. tryEmitNext và emitNext khác nhau thế nào?

| API | Kết quả | Khi nên dùng |
|---|---|---|
| `tryEmitNext(value)` | Trả `EmitResult` ngay | Khi ứng dụng cần tự quyết định mọi trường hợp thất bại |
| `emitNext(value, handler)` | Không trả `EmitResult`; xử lý theo failure handler | Khi muốn dùng chính sách retry/failure có sẵn |

`tryEmitNext` thường dễ quan sát và kiểm soát hơn. `emitNext` tiện lợi hơn nhưng nếu failure handler không retry, Reactor sẽ áp dụng hành vi mặc định cho từng loại lỗi. Ví dụ overflow có thể làm sink kết thúc bằng lỗi; `FAIL_NON_SERIALIZED` có thể ném `Sinks.EmissionException`.

Vì vậy, khi cần chính sách nghiệp vụ như persist event, drop latest hoặc trả trạng thái backpressure cho caller, hãy ưu tiên `tryEmitNext` và xử lý kết quả tường minh.

## 11. Tích hợp Reactor Sinks với RSocket request-stream

Một ứng dụng Spring có thể expose `Sinks.Many` thành request-stream. Mỗi client gọi route để đăng ký nhận sự kiện.

Event hub:

~~~java
@Component
public class PriceEventHub {

    private final Sinks.Many<PriceTick> sink =
        Sinks.many().multicast().onBackpressureBuffer(128, false);

    public Flux<PriceTick> watch() {
        return sink.asFlux();
    }

    public Sinks.EmitResult publish(PriceTick tick) {
        return sink.tryEmitNext(tick);
    }

    public void close() {
        sink.tryEmitComplete();
    }
}
~~~

RSocket controller:

~~~java
@Controller
public class PriceStreamController {

    private final PriceEventHub eventHub;

    public PriceStreamController(PriceEventHub eventHub) {
        this.eventHub = eventHub;
    }

    @MessageMapping("prices.watch")
    public Flux<PriceTick> watch() {
        return eventHub.watch();
    }
}
~~~

Client:

~~~java
Flux<PriceTick> ticks = requester
    .route("prices.watch")
    .retrieveFlux(PriceTick.class);
~~~

Khi client subscribe, Spring gắn request-stream với `Flux` do sink cung cấp. Khi event hub gọi `publish`, các client đang theo dõi có thể nhận dữ liệu theo demand của RSocket/Reactive Streams.

Một client hủy stream sẽ hủy subscription của chính client đó. Vì sink được chia sẻ và `autoCancel` đã tắt, các client khác vẫn có thể tiếp tục nhận event. Ứng dụng cần đóng sink khi event source hoặc application context kết thúc.

### Gửi kết quả phát thất bại tới producer

Không bỏ qua `EmitResult` khi publish:

~~~java
public void onExternalPrice(PriceTick tick) {
    Sinks.EmitResult result = eventHub.publish(tick);

    switch (result) {
        case OK ->
            metrics.increment("price.emit.accepted");
        case FAIL_OVERFLOW ->
            metrics.increment("price.emit.overflow");
        case FAIL_ZERO_SUBSCRIBER ->
            metrics.increment("price.emit.no-subscriber");
        case FAIL_NON_SERIALIZED ->
            log.warn("Concurrent price emission");
        case FAIL_CANCELLED, FAIL_TERMINATED ->
            log.debug("Price stream is no longer active: {}", result);
    }
}
~~~

Đây là chỗ thích hợp để quyết định có lưu event, bỏ event hoặc báo quá tải. Không đưa trực tiếp lỗi phát nội bộ của sink thành response RSocket cho một client bất kỳ; lỗi đó thuộc về producer/event hub, trừ khi giao thức ứng dụng có quy định rõ.

## 12. Backpressure ở sink và RSocket

RSocket request-stream có backpressure. Client gửi demand bằng REQUEST_N; server chỉ phát response item theo nhu cầu được yêu cầu. Khi response stream được tạo từ `sink.asFlux()`, demand đó đi ngược vào pipeline Reactor.

Tuy nhiên, nguồn imperative gọi `tryEmitNext` không tự động chờ demand. Sink phải áp dụng chính sách riêng:

- Buffer một số phần tử.
- Từ chối khi buffer đầy.
- Bỏ phần tử theo semantics direct sink.
- Phát cho subscriber nhanh và bỏ cho subscriber chậm.
- Dùng replay để giữ một lịch sử giới hạn.

~~~mermaid
sequenceDiagram
    participant P as Event producer
    participant S as Reactor Sink
    participant R as RSocket responder
    participant C as RSocket client
    C->>R: REQUEST_STREAM
    R->>S: Subscribe to asFlux()
    C->>R: REQUEST_N demand
    P->>S: tryEmitNext(event)
    S->>R: onNext(event)
    R-->>C: PAYLOAD
    Note over S,P: Nếu demand/buffer không đủ,<br/>tryEmitNext có thể thất bại
    S-->>P: EmitResult
~~~

Đừng giả định `onBackpressureBuffer` sau `asFlux()` có thể làm producer imperative chờ không giới hạn. Nếu producer không thể bị chậm lại, hãy đặt buffer hữu hạn ở đúng ranh giới và xử lý overflow.

## 13. Chọn chính sách cho từng loại dữ liệu

Không phải event nào cũng có cùng yêu cầu giao nhận.

| Dữ liệu | Gợi ý sink | Chính sách khi phát thất bại |
|---|---|---|
| Giá thị trường mới nhất | `directBestEffort()` hoặc replay latest | Bỏ cập nhật cũ, giữ snapshot mới |
| Telemetry tần suất cao | Multicast có buffer giới hạn | Drop/sample khi quá tải nếu nghiệp vụ cho phép |
| Audit event | Replay giới hạn cho subscriber ngắn hạn, broker bền vững cho lưu trữ | Persist trước khi xác nhận |
| Lệnh nghiệp vụ | Không dùng sink broadcast làm hàng đợi duy nhất | Reject hoặc persist, xác nhận theo transaction |
| Một kết quả bất đồng bộ | `Sinks.One` | Chỉ phát một lần, terminal rõ ràng |
| Job queue cho một consumer | Unicast với queue có giới hạn | Reject hoặc backpressure producer |

Sinks là cấu trúc trong bộ nhớ của một tiến trình. Nó không bảo đảm dữ liệu bền vững qua restart, không tự tạo acknowledgement từ client và không thay thế message broker khi cần giao nhận tin cậy.

## 14. Quan sát và vận hành

Nên ghi nhận số liệu phát và thất bại theo loại sink và theo event stream:

- Tổng số lần phát thành công (`OK`).
- Số lần overflow.
- Số lần không có subscriber.
- Số lần `FAIL_NON_SERIALIZED`.
- Số lần phát vào sink đã terminal/cancelled.
- Số subscriber hiện tại.
- Độ trễ từ lúc producer tạo event đến khi client nhận.
- Số event bị drop hoặc persist để phát lại.

`currentSubscriberCount()` có thể dùng cho quan sát nhưng chỉ là ảnh chụp best-effort. Không dùng nó làm điều kiện duy nhất để bỏ qua việc kiểm tra `EmitResult`.

Khi log, nên ghi event ID, stream name và trạng thái phát. Tránh log toàn bộ payload nếu dữ liệu chứa thông tin nhạy cảm.

## 15. Kiểm thử phát thành công và thất bại

### Kiểm thử multicast phát dữ liệu

~~~java
@Test
void emitsEventToSubscriber() {
    Sinks.Many<String> sink =
        Sinks.many().multicast().onBackpressureBuffer();

    StepVerifier.create(sink.asFlux())
        .then(() ->
            assertThat(sink.tryEmitNext("event-1"))
                .isEqualTo(Sinks.EmitResult.OK)
        )
        .expectNext("event-1")
        .then(() ->
            assertThat(sink.tryEmitComplete())
                .isEqualTo(Sinks.EmitResult.OK)
        )
        .verifyComplete();
}
~~~

Test xác nhận subscriber nhận event và stream hoàn tất bình thường.

### Kiểm thử overflow với directAllOrNothing

~~~java
@Test
void reportsOverflowWhenSubscriberHasNoDemand() {
    Sinks.Many<Integer> sink =
        Sinks.many().multicast().directAllOrNothing();

    StepVerifier.create(sink.asFlux(), 0)
        .then(() ->
            assertThat(sink.tryEmitNext(1))
                .isEqualTo(Sinks.EmitResult.FAIL_OVERFLOW)
        )
        .thenRequest(1)
        .then(() -> sink.tryEmitComplete())
        .verifyComplete();
}
~~~

Subscriber được đăng ký nhưng chưa yêu cầu phần tử. `directAllOrNothing` từ chối lần phát vì thiếu demand và trả `FAIL_OVERFLOW`. Test sau đó hoàn tất sink và xác nhận subscriber nhận terminal signal.

### Kiểm thử sink đã terminal

~~~java
@Test
void rejectsEmissionAfterCompletion() {
    Sinks.Many<String> sink =
        Sinks.many().multicast().onBackpressureBuffer();

    assertThat(sink.tryEmitComplete())
        .isEqualTo(Sinks.EmitResult.OK);

    assertThat(sink.tryEmitNext("late-event"))
        .isEqualTo(Sinks.EmitResult.FAIL_TERMINATED);
}
~~~

Test này xác nhận producer không thể tái sử dụng sink sau complete.

### Kiểm thử cancellation

~~~java
@Test
void cancellingFluxRemovesSubscriber() {
    Sinks.Many<String> sink =
        Sinks.many().multicast().onBackpressureBuffer(16, false);

    StepVerifier.create(sink.asFlux())
        .thenCancel()
        .verify();

    assertThat(sink.currentSubscriberCount()).isZero();
}
~~~

Cancellation của subscriber không nhất thiết terminal sink. Với multicast có `autoCancel=false`, một subscriber mới vẫn có thể đăng ký và tiếp tục nhận event.

### Kiểm thử tích hợp RSocket

Ngoài unit test cho sink, nên chạy RSocket server/client test để xác nhận:

- Client subscribe route `prices.watch` và nhận event từ sink.
- Client hủy stream thì subscription của client được giải phóng.
- Một client chậm không làm mất dữ liệu của client khác nếu chính sách sink yêu cầu tất cả nhận.
- Overflow được ghi nhận và xử lý đúng.
- Event source kết thúc thì server phát terminal signal tới client.
- Nhiều producer không tạo `FAIL_NON_SERIALIZED` ngoài dự kiến.

## 16. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| `OK` nghĩa là mọi client đã xử lý event | `OK` chỉ có nghĩa sink chấp nhận tín hiệu tại thời điểm phát |
| Mọi sink đều buffer khi chưa có subscriber | Unicast/replay/multicast có warm-up khác direct sink |
| Replay luôn an toàn cho stream dài hạn | Replay không giới hạn có thể giữ toàn bộ lịch sử trong bộ nhớ |
| `FAIL_OVERFLOW` luôn có nghĩa queue đầy | Với direct sink, có thể do subscriber thiếu demand |
| Retry ngay mọi kết quả thất bại | Overflow, terminal và contention cần chính sách khác nhau |
| `FAIL_NON_SERIALIZED` là lỗi dữ liệu | Nó cho biết các lần phát cạnh tranh chưa được tuần tự hóa |
| `emitNext` luôn an toàn hơn `tryEmitNext` | `emitNext` áp dụng failure handler và hành vi mặc định; `tryEmitNext` cho phép tự quyết định |
| Subscriber hủy thì sink dùng chung phải đóng | Cancellation của một subscriber không nhất thiết kết thúc sink |
| Sinks bảo đảm giao nhận bền vững | Sink là cấu trúc trong bộ nhớ, không thay thế broker hoặc persistent log |

## 17. Quy trình triển khai Reactor Sinks

Khi đưa một sink vào luồng dữ liệu realtime, hãy thực hiện theo thứ tự:

1. Xác định nguồn imperative nào cần phát dữ liệu vào Reactor.
2. Chọn One hay Many theo số phần tử.
3. Chọn unicast, multicast, direct hay replay theo số subscriber và yêu cầu dữ liệu.
4. Đặt giới hạn buffer/replay phù hợp với kích thước event và tốc độ consumer.
5. Expose `asMono()` hoặc `asFlux()` cho downstream; không chia sẻ đối tượng sink cho mọi thành phần.
6. Dùng `tryEmitNext` khi cần kiểm soát từng kết quả phát.
7. Phân biệt overflow, không có subscriber, cancellation, terminal và concurrent emission.
8. Tuần tự hóa nhiều producer hoặc dùng retry contention có giới hạn.
9. Quy định rõ drop, retry, reject hoặc persist cho từng loại event.
10. Gắn terminal signal với lifecycle của event source.
11. Tích hợp Flux view vào `@MessageMapping` nếu cần phát request-stream cho RSocket client.
12. Đo emit result, subscriber count, queue pressure và latency; kiểm thử cancellation và overflow.

Reactor Sinks giúp nối nguồn phát dữ liệu imperative với pipeline reactive. Để luồng ổn định, producer phải chọn sink theo semantics của subscriber và coi `EmitResult` là một phần của hợp đồng phát dữ liệu. Khi mỗi loại thất bại có chính sách riêng, ứng dụng có thể kiểm soát mất dữ liệu, quá tải và vòng đời stream rõ ràng hơn.

## Ghi nhớ

- `Sinks.One` biểu diễn một kết quả; `Sinks.Many` biểu diễn nhiều phần tử.
- Unicast chỉ có một subscriber; multicast phát tới nhiều subscriber; replay giữ lịch sử cho subscriber đến muộn.
- Direct sink không buffer và có thể bỏ phần tử khi subscriber thiếu demand.
- `tryEmitNext` trả `Sinks.EmitResult`; phải kiểm tra kết quả.
- `OK` không chứng minh client đã nhận hoặc xử lý event.
- `FAIL_OVERFLOW` cần chính sách drop, backoff, persist hoặc reject.
- `FAIL_NON_SERIALIZED` cần tuần tự hóa hoặc retry contention có giới hạn.
- `FAIL_TERMINATED` và `FAIL_CANCELLED` là vấn đề lifecycle; không retry trên cùng sink.
- Buffer và replay phải có giới hạn nếu stream sống lâu.
- Sinks không thay thế broker bền vững hoặc acknowledgement nghiệp vụ.

## Tài liệu tham khảo

- [Project Reactor — Sinks Reference Guide](https://projectreactor.io/docs/core/release/reference/coreFeatures/sinks.html)
- [Project Reactor — Sinks API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Sinks.html)
- [Project Reactor — Sinks.Many API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Sinks.Many.html)
- [Project Reactor — Sinks.EmitResult API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Sinks.EmitResult.html)
- [Project Reactor — Sinks.MulticastSpec API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Sinks.MulticastSpec.html)
- [Spring Framework — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)

