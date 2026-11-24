# Sinks.One, Sinks.Many và lựa chọn cơ chế phát

Trong Project Reactor, nhiều nguồn dữ liệu được tạo từ một Publisher có sẵn, chẳng hạn `Flux.range`, `Mono.fromCallable` hoặc một reactive client. Nhưng đôi khi dữ liệu lại đến từ một callback bên ngoài, một luồng xử lý khác hoặc một hành động do ứng dụng chủ động kích hoạt. Khi đó, ứng dụng cần một điểm phát tín hiệu để chuyển dữ liệu vào pipeline reactive.

Reactor cung cấp nhóm API `Sinks` cho mục đích này. `Sinks.One` biểu diễn một kết quả đơn lẻ, còn `Sinks.Many` biểu diễn nhiều phần tử. Với `Sinks.Many`, ta còn phải chọn cách phân phối cho một subscriber, nhiều subscriber đang hoạt động hoặc cả subscriber đến muộn; đồng thời xác định cách xử lý khi downstream không theo kịp nguồn phát.

Bài học thuộc chương **Project Reactor** của module **REACTIVE_PROGRAMMING**. Module hướng dẫn tư duy reactive qua các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và backpressure của Reactive Streams; các sink trong bài kết nối trực tiếp với Mono, Flux, toán tử, scheduler, xử lý lỗi và kiểm thử pipeline Java.

Các đoạn mã sử dụng Project Reactor. Những tên như orderService, eventBus hoặc Event đại diện cho thành phần của ứng dụng; hãy bổ sung import và kiểu miền tương ứng khi áp dụng vào dự án.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vai trò của Sinks trong việc chuyển sự kiện từ mã imperative hoặc callback vào pipeline reactive.
- Chọn Sinks.One cho một kết quả đơn và Sinks.Many cho một luồng nhiều phần tử.
- Phân biệt unicast, multicast và replay.
- Chọn chính sách phát có buffer, phát trực tiếp hoặc lưu lịch sử theo nhu cầu subscriber.
- Xử lý kết quả phát thất bại, backpressure và các lần phát đồng thời.
- Kiểm thử giá trị, tín hiệu kết thúc, subscriber đến muộn và lỗi phát bằng StepVerifier.

## 1. Sinks là cầu nối giữa mã ứng dụng và Publisher

Một Publisher thường mô tả cách tạo dữ liệu. Ví dụ, `Mono.fromCallable` gọi một hàm khi có subscription, còn `Flux.interval` phát dữ liệu theo nhịp thời gian. Tuy nhiên, trong một số tích hợp, dữ liệu được đẩy vào ứng dụng từ bên ngoài:

- SDK gọi callback khi nhận được thông báo.
- Một thao tác imperative hoàn thành và cần chuyển kết quả sang pipeline reactive.
- Một thành phần khác phát sự kiện trạng thái.
- Một bộ điều phối nhận lệnh từ nhiều luồng thực thi.

`Sinks` cho phép ứng dụng chủ động phát phần tử hoặc tín hiệu kết thúc, sau đó cung cấp giao diện Publisher để các thành phần reactive đăng ký:

~~~text
Callback / imperative code
          |
          | tryEmitNext / tryEmitValue
          v
       Sinks
          |
          | asFlux() / asMono()
          v
   Reactive pipeline
          |
          v
     Subscribers
~~~

Sink là nơi phát dữ liệu, còn `asFlux()` hoặc `asMono()` cung cấp góc nhìn Publisher cho downstream. Việc tạo sink không tự thực hiện xử lý nghiệp vụ; các subscriber chỉ bắt đầu nhận tín hiệu khi đăng ký.

Sinks là nguồn phát nóng (hot source): phần tử được phát tại thời điểm gọi phương thức emit. Subscriber không đăng ký đúng thời điểm sẽ không nhất thiết nhận được những phần tử đã phát trước đó. Ngoại lệ là các loại sink có chính sách lưu và phát lại lịch sử, như replay.

## 2. Sinks.One: phát một kết quả duy nhất

`Sinks.One<T>` phù hợp khi một tác vụ sẽ tạo ra tối đa một giá trị. Có thể hình dung nó như một cầu nối để hoàn thành một `Mono<T>` từ một callback hoặc một thành phần khác:

~~~java
Sinks.One<Order> orderSink = Sinks.one();

Mono<Order> orderResult = orderSink.asMono();

// Khi tác vụ bên ngoài có kết quả:
Sinks.EmitResult result =
    orderSink.tryEmitValue(order);

if (result != Sinks.EmitResult.OK) {
    log.warn("Không thể phát kết quả: {}", result);
}
~~~

`asMono()` trả về Publisher biểu diễn kết quả đơn. Khi `tryEmitValue(order)` thành công, subscriber nhận một phần tử rồi nhận `onComplete`. Một giá trị đã được phát không thể bị thay thế bằng giá trị thứ hai.

Sinks.One còn có thể kết thúc mà không phát giá trị:

~~~java
orderSink.tryEmitEmpty();
~~~

Khi đó, Mono hoàn tất rỗng: subscriber nhận `onComplete` mà không nhận `onNext`. Nếu tác vụ thất bại, có thể phát lỗi:

~~~java
orderSink.tryEmitError(
    new IllegalStateException("Không tìm thấy đơn hàng")
);
~~~

Ba kết quả có ý nghĩa khác nhau:

| Cách phát | Tín hiệu subscriber nhận |
|---|---|
| `tryEmitValue(value)` | Một `onNext(value)`, sau đó `onComplete` |
| `tryEmitEmpty()` | `onComplete` mà không có `onNext` |
| `tryEmitError(error)` | `onError(error)` |

Một sink One chỉ chấp nhận một kết quả kết thúc. Sau khi đã phát giá trị, empty completion hoặc error, các lần phát tiếp theo không thể thay đổi kết quả đó và thường trả về `FAIL_TERMINATED`.

### Ví dụ: hoàn thành Mono từ callback

Giả sử thư viện thanh toán cung cấp callback khi có kết quả:

~~~java
Mono<PaymentResult> pay(PaymentRequest request) {
    Sinks.One<PaymentResult> sink = Sinks.one();

    paymentSdk.submit(
        request,
        result -> sink.tryEmitValue(result),
        error -> sink.tryEmitError(error)
    );

    return sink.asMono();
}
~~~

Ví dụ minh họa cách nối callback thành Mono. Trong ứng dụng thật, cần cân nhắc thời điểm SDK có thể gọi callback trước khi subscriber đăng ký, chính sách timeout, hủy yêu cầu và xử lý trường hợp callback bị gọi nhiều lần. Sinks.One có thể giữ kết quả đã phát để subscriber đăng ký sau vẫn nhận được kết quả terminal, nhưng việc hủy Mono downstream không tự động hủy yêu cầu ở SDK. Muốn hủy tác vụ bên ngoài, cần nối cancellation với API cancel/dispose của SDK.

Nếu callback có thể phát cả success và error do lỗi thiết kế hoặc race condition, chỉ lần phát hợp lệ đầu tiên được chấp nhận. Hãy kiểm tra EmitResult của các lần phát để phát hiện callback đến trễ hoặc gọi lặp.

## 3. Sinks.Many: phát nhiều phần tử

`Sinks.Many<T>` phù hợp khi ứng dụng cần phát nhiều giá trị theo thời gian. Nó cung cấp Publisher dạng Flux qua `asFlux()`:

~~~java
Sinks.Many<Event> eventSink =
    Sinks.many().multicast().onBackpressureBuffer();

Flux<Event> events = eventSink.asFlux();

Sinks.EmitResult result =
    eventSink.tryEmitNext(new Event("ORDER_CREATED"));

if (result != Sinks.EmitResult.OK) {
    log.warn("Không phát được sự kiện: {}", result);
}
~~~

Sau khi phát nhiều phần tử, ứng dụng cần gửi một tín hiệu kết thúc khi nguồn không còn hoạt động:

~~~java
eventSink.tryEmitComplete();
~~~

Hoặc kết thúc bằng lỗi:

~~~java
eventSink.tryEmitError(
    new IllegalStateException("Nguồn sự kiện ngừng hoạt động")
);
~~~

Sau `tryEmitComplete()` hoặc `tryEmitError(...)`, sink đã kết thúc. Không thể tiếp tục phát phần tử mới vào cùng sink. Nếu cần một phiên phát mới, hãy tạo sink mới và quản lý vòng đời của nó ở thành phần sở hữu.

### Phân biệt Sinks.One và Sinks.Many

| Đặc điểm | Sinks.One | Sinks.Many |
|---|---|---|
| Số phần tử dữ liệu | Tối đa một | Không giới hạn theo mô hình API; thực tế cần giới hạn tài nguyên |
| Publisher view | `Mono<T>` qua `asMono()` | `Flux<T>` qua `asFlux()` |
| Kết thúc | Giá trị, empty hoặc error | Complete hoặc error sau không hoặc nhiều phần tử |
| Trường hợp dùng | Kết quả một lần, phản hồi callback | Sự kiện, thông báo, luồng trạng thái |
| Lịch sử cho subscriber muộn | Kết quả đơn đã kết thúc có thể được quan sát | Phụ thuộc loại Many: unicast, multicast hoặc replay |

Không nên chọn sink chỉ dựa trên số lượng giá trị. Cần xem có bao nhiêu subscriber, subscriber đến vào thời điểm nào và điều gì xảy ra khi một subscriber không có demand.

## 4. Chọn kiểu Sinks.Many: unicast, multicast và replay

Reactor chia Sinks.Many thành ba nhóm chính theo cách phân phối dữ liệu.

### unicast: chỉ một subscriber

`unicast()` dành cho trường hợp chỉ có một subscriber tiêu thụ luồng. Một hàng đợi có thể giữ các phần tử được phát trước khi subscriber đăng ký hoặc trong lúc subscriber chưa có demand, tùy cấu hình queue:

~~~java
Sinks.Many<String> commands =
    Sinks.many().unicast().onBackpressureBuffer();

Flux<String> commandStream = commands.asFlux();
~~~

Kiểu này phù hợp với một worker hoặc một consumer sở hữu riêng một luồng lệnh. Nếu có subscriber thứ hai, sink không chấp nhận đăng ký đó; không nên dùng unicast khi nhiều thành phần cần cùng nhận một sự kiện.

Hàng đợi mặc định có thể tăng theo lượng dữ liệu chờ. Nếu nguồn có thể phát nhanh hơn consumer trong thời gian dài, cần chọn queue có giới hạn hoặc một cơ chế admission khác. Chỉ vì sink có backpressure buffer không có nghĩa bộ nhớ là vô hạn an toàn.

### multicast: nhiều subscriber đang hoạt động

`multicast()` phân phối tín hiệu đến nhiều subscriber. Subscriber mới thường chỉ nhận các phần tử được phát sau khi nó đăng ký; các phần tử trước đó không được phát lại như lịch sử:

~~~java
Sinks.Many<Notification> notifications =
    Sinks.many().multicast().onBackpressureBuffer();

Flux<Notification> stream = notifications.asFlux();
~~~

Kiểu này phù hợp với thông báo trực tiếp cho các thành phần đang hoạt động, chẳng hạn nhiều màn hình đang theo dõi trạng thái đơn hàng. Nếu một màn hình đăng ký muộn, nó không tự động nhận toàn bộ thông báo trước đó.

Multicast có nhiều chiến lược phát để xử lý subscriber chậm. Cần chọn rõ liệu sink sẽ đệm dữ liệu, yêu cầu mọi subscriber đều sẵn sàng hay bỏ dữ liệu cho subscriber không có demand.

### replay: phát lại lịch sử cho subscriber đến muộn

`replay()` lưu một phần hoặc toàn bộ lịch sử theo cấu hình để subscriber đăng ký muộn có thể nhận lại:

~~~java
Sinks.Many<StatusEvent> statusHistory =
    Sinks.many().replay().limit(20);

Flux<StatusEvent> statuses = statusHistory.asFlux();
~~~

Với giới hạn 20, sink giữ lại tối đa 20 phần tử gần nhất để phát lại cho subscriber mới. Các phần tử cũ hơn bị loại khỏi lịch sử khi giới hạn bị vượt qua.

Reactor còn có thể cấu hình replay toàn bộ lịch sử hoặc giới hạn theo thời gian tùy overload. Replay toàn bộ phù hợp với lịch sử nhỏ, hữu hạn; với nguồn dài hạn, lưu mọi phần tử sẽ làm bộ nhớ tăng theo thời gian. Hãy chọn giới hạn số lượng hoặc thời gian phù hợp với nhu cầu thực tế.

### Bảng lựa chọn

| Kiểu | Số subscriber | Subscriber đến muộn | Trường hợp điển hình |
|---|---|---|---|
| unicast | Một | Nhận dữ liệu được giữ trong queue theo cấu hình | Một worker tiêu thụ lệnh |
| multicast | Nhiều subscriber đang hoạt động | Không nhận lịch sử trước lúc đăng ký | Thông báo trực tiếp |
| replay | Nhiều | Nhận lại lịch sử theo giới hạn | Trạng thái gần nhất hoặc lịch sử ngắn |

## 5. Chọn chính sách phát và backpressure cho multicast

Với multicast, các subscriber có thể có tốc độ tiêu thụ khác nhau. Một subscriber có thể xử lý nhanh trong khi subscriber khác tạm thời không request thêm. Sink cần một chính sách cho tình huống đó.

### onBackpressureBuffer: giữ phần tử chờ subscriber

~~~java
Sinks.Many<Event> sink =
    Sinks.many().multicast().onBackpressureBuffer();
~~~

Chính sách này đệm các phần tử khi subscriber chưa có demand. Nó phù hợp khi cần giữ dữ liệu cho các subscriber nhưng vẫn phải quản lý capacity. Khi buffer không thể nhận thêm dữ liệu, lần phát có thể thất bại với `FAIL_OVERFLOW`.

Buffer không làm consumer nhanh hơn. Nếu subscriber chậm kéo dài, lượng dữ liệu chờ có thể tăng và gây áp lực bộ nhớ. Với dữ liệu quan trọng, hãy chọn giới hạn, chính sách overflow và cách báo lỗi rõ ràng thay vì để queue tăng không kiểm soát.

### directAllOrNothing: tất cả hoặc không subscriber nào nhận

~~~java
Sinks.Many<Event> sink =
    Sinks.many().multicast().directAllOrNothing();
~~~

Chiến lược trực tiếp này chỉ phát một phần tử khi tất cả subscriber hiện tại đều có demand. Nếu ít nhất một subscriber chưa sẵn sàng, lần phát không được chuyển cho bất kỳ subscriber nào. Chính sách này giữ tính nhất quán giữa các subscriber ở mức mỗi lần phát, nhưng một consumer chậm có thể làm cả nhóm không nhận được phần tử mới.

Dùng khi tất cả subscriber cần nhìn thấy cùng tập sự kiện và ứng dụng có thể xử lý việc phát thất bại, chẳng hạn thử lại có giới hạn hoặc báo nghẽn cho producer.

### directBestEffort: phát cho subscriber sẵn sàng

~~~java
Sinks.Many<Event> sink =
    Sinks.many().multicast().directBestEffort();
~~~

Chiến lược này phát phần tử cho subscriber đang có demand. Subscriber không có demand có thể bỏ lỡ phần tử đó, trong khi subscriber khác vẫn nhận. Cách này hữu ích cho telemetry hoặc cập nhật giao diện mà một số mẫu trung gian có thể bị bỏ.

Không dùng directBestEffort cho luồng mà mọi subscriber phải nhận đầy đủ từng sự kiện, chẳng hạn audit hoặc xử lý giao dịch.

### So sánh chiến lược multicast

| Chiến lược | Subscriber chậm | Tác động đến subscriber khác | Khi phù hợp |
|---|---|---|---|
| onBackpressureBuffer | Phần tử được đệm trong giới hạn | Có thể phát khi subscriber có demand trở lại | Cần giữ dữ liệu, có capacity và overflow policy |
| directAllOrNothing | Làm lần phát thất bại nếu một subscriber thiếu demand | Không subscriber nào nhận phần tử đó | Cần mọi subscriber đồng bộ tập sự kiện |
| directBestEffort | Bỏ phần tử ở subscriber thiếu demand | Subscriber có demand vẫn nhận | Cho phép mất cập nhật trung gian |

Backpressure ở đây là hợp đồng giữa sink và các subscriber. Sink không tự động làm chậm một callback bên ngoài nếu callback đó không biết hoặc không tuân theo demand. Producer cần kiểm tra kết quả phát và quyết định buffer, retry, drop hoặc từ chối theo chính sách nghiệp vụ.

## 6. Kiểm tra EmitResult thay vì bỏ qua kết quả phát

Các phương thức `tryEmit...` trả về `Sinks.EmitResult`. Kết quả cho biết phần tử hoặc tín hiệu đã được chấp nhận hay vì sao lần phát thất bại.

Một số kết quả thường gặp:

| EmitResult | Ý nghĩa |
|---|---|
| `OK` | Tín hiệu đã được chấp nhận |
| `FAIL_TERMINATED` | Sink đã nhận tín hiệu kết thúc trước đó |
| `FAIL_OVERFLOW` | Không thể nhận thêm phần tử theo chính sách buffer/backpressure |
| `FAIL_NON_SERIALIZED` | Có nhiều lần phát đồng thời không được tuần tự hóa |
| `FAIL_ZERO_SUBSCRIBER` | Không có subscriber phù hợp để nhận tín hiệu trong chiến lược đang dùng |
| `FAIL_CANCELLED` | Sink hoặc đường tiêu thụ đã bị hủy |
| `FAIL_SUBSCRIBER_NOT_ALLOWED` | Kiểu sink không cho phép subscriber bổ sung, ví dụ unicast đã có subscriber |

Các trường hợp cụ thể phụ thuộc loại sink và trạng thái subscription. Hãy xử lý các kết quả mà chiến lược đang dùng có thể trả về, thay vì giả định mọi lần `tryEmitNext` đều thành công.

Ví dụ:

~~~java
Sinks.EmitResult result = eventSink.tryEmitNext(event);

switch (result) {
    case OK -> metrics.incrementEmitted();
    case FAIL_OVERFLOW -> metrics.incrementDroppedOrRejected();
    case FAIL_TERMINATED -> log.debug("Sink đã kết thúc");
    case FAIL_NON_SERIALIZED -> log.warn("Phát đồng thời chưa được tuần tự hóa");
    default -> log.warn("Phát thất bại: {}", result);
}
~~~

Đoạn switch minh họa cách phân loại kết quả; hãy đối chiếu các enum constant với phiên bản Reactor đang dùng và chính sách của sink cụ thể. Nếu dữ liệu quan trọng, không nên chỉ ghi log rồi bỏ qua lỗi. Có thể cần retry có giới hạn, lưu vào hàng đợi bền vững hoặc trả lỗi về thành phần phát.

### tryEmit và emit

- `tryEmitNext`, `tryEmitValue`, `tryEmitComplete` và `tryEmitError` trả về kết quả để ứng dụng tự quyết định bước tiếp theo.
- Các phương thức `emit...` nhận thêm một `EmitFailureHandler`, cho phép định nghĩa cách xử lý một số lỗi phát, chẳng hạn retry khi có tranh chấp phát đồng thời.

Với hệ thống cần kiểm soát chặt chẽ, `tryEmit...` thường dễ quan sát vì caller nhận được kết quả ngay. Dù chọn cách nào, hãy xác định rõ khi nào producer có thể thử lại và khi nào phải từ chối dữ liệu.

## 7. Phát đồng thời từ nhiều luồng

Sinks được thiết kế để phát hiện các lần phát không được tuần tự hóa. Nếu hai thread gọi emit gần như cùng lúc, một lần phát có thể thất bại với `FAIL_NON_SERIALIZED`. Cơ chế phát hiện giúp tránh làm hỏng trạng thái nội bộ, nhưng không tự quyết định thứ tự nghiệp vụ cho ứng dụng.

Có ba hướng xử lý phổ biến:

1. **Tuần tự hóa producer:** gửi mọi lệnh phát qua một executor hoặc event loop duy nhất.
2. **Dùng khóa ở ranh giới phát:** bảo đảm chỉ một thread gọi sink tại một thời điểm.
3. **Dùng EmitFailureHandler có retry:** chỉ khi chính sách ứng dụng cho phép retry tranh chấp và có giới hạn thời gian.

Ví dụ dùng khóa:

~~~java
private final Object emitLock = new Object();

void publish(Event event) {
    synchronized (emitLock) {
        Sinks.EmitResult result = eventSink.tryEmitNext(event);

        if (result != Sinks.EmitResult.OK) {
            handleEmitFailure(result, event);
        }
    }
}
~~~

Khóa chỉ tuần tự hóa các producer dùng chung `emitLock`. Nó không nên được giữ trong lúc thực hiện I/O hoặc công việc xử lý dài. Nếu thứ tự sự kiện là yêu cầu nghiệp vụ, hãy định nghĩa thứ tự ở tầng producer trước khi gọi sink.

Không nên dùng sink không có cơ chế phát hiện tranh chấp để thay thế việc thiết kế đồng bộ. Nếu dùng một biến thể unsafe, trách nhiệm tuần tự hóa hoàn toàn thuộc về ứng dụng.

## 8. Kết thúc sink và quản lý vòng đời

Một sink Many có thể phát nhiều phần tử nhưng chỉ có một lần kết thúc terminal. Khi nguồn không còn phát dữ liệu, hãy gửi complete hoặc error:

~~~java
eventSink.tryEmitComplete();
~~~

Sau đó, những lần `tryEmitNext` tiếp theo không thể tiếp tục luồng và sẽ thất bại. Tín hiệu kết thúc cũng được chuyển đến subscriber theo quy tắc của sink.

Một số nguyên tắc vòng đời:

- Thành phần tạo sink cần xác định ai chịu trách nhiệm kết thúc nó.
- Khi một phiên hoặc kết nối kết thúc, phát complete hoặc error đúng thời điểm.
- Nếu nguồn được chia sẻ, không để một subscriber riêng lẻ tự ý kết thúc sink mà các subscriber khác còn phụ thuộc.
- Nếu cần khởi động phiên mới, tạo sink mới thay vì cố tái sử dụng sink đã terminal.
- Khi subscriber hủy, xác định liệu producer bên ngoài có cần dừng hay vẫn phục vụ subscriber khác.

Cancellation của một subscriber không đồng nghĩa sink đã complete. Đối với nguồn từ SDK hoặc callback, cần nối lifecycle của subscription với thao tác hủy đăng ký hoặc dừng producer nếu ứng dụng sở hữu nguồn đó.

## 9. Kiểm thử Sinks với StepVerifier

Sink có thể được kiểm thử như một Publisher thông thường. Điểm quan trọng là điều khiển thời điểm phát để xác nhận subscriber nhận đúng giá trị và terminal signal.

### Kiểm thử Sinks.One

~~~java
Sinks.One<String> sink = Sinks.one();

StepVerifier.create(sink.asMono())
    .then(() -> assertEquals(
        Sinks.EmitResult.OK,
        sink.tryEmitValue("done")
    ))
    .expectNext("done")
    .verifyComplete();
~~~

Kiểm thử đăng ký trước, sau đó phát một giá trị. Subscriber nhận giá trị và complete.

Có thể kiểm thử empty completion:

~~~java
Sinks.One<String> emptySink = Sinks.one();

StepVerifier.create(emptySink.asMono())
    .then(() -> assertEquals(
        Sinks.EmitResult.OK,
        emptySink.tryEmitEmpty()
    ))
    .verifyComplete();
~~~

Không có phần tử nào được phát, nhưng Mono hoàn tất bình thường.

### Kiểm thử Sinks.Many unicast

~~~java
Sinks.Many<Integer> sink =
    Sinks.many().unicast().onBackpressureBuffer();

StepVerifier.create(sink.asFlux())
    .then(() -> {
        assertEquals(Sinks.EmitResult.OK, sink.tryEmitNext(1));
        assertEquals(Sinks.EmitResult.OK, sink.tryEmitNext(2));
        assertEquals(Sinks.EmitResult.OK, sink.tryEmitComplete());
    })
    .expectNext(1, 2)
    .verifyComplete();
~~~

Một subscriber nhận hai phần tử và tín hiệu hoàn tất. Kiểm thử này xác nhận đường phát cơ bản của unicast sink.

### Kiểm thử replay cho subscriber đến muộn

~~~java
Sinks.Many<Integer> history =
    Sinks.many().replay().limit(2);

history.tryEmitNext(10);
history.tryEmitNext(20);
history.tryEmitNext(30);

StepVerifier.create(history.asFlux())
    .expectNext(20, 30)
    .thenCancel()
    .verify();
~~~

Sink giữ hai phần tử gần nhất. Subscriber đăng ký sau chỉ nhận 20 và 30, sau đó kiểm thử hủy vì sink vẫn đang mở.

### Kiểm thử phát sau terminal

~~~java
Sinks.One<String> sink = Sinks.one();

assertEquals(
    Sinks.EmitResult.OK,
    sink.tryEmitValue("first")
);

assertEquals(
    Sinks.EmitResult.FAIL_TERMINATED,
    sink.tryEmitValue("second")
);
~~~

Kiểm thử xác nhận kết quả đầu tiên không thể bị thay thế. Trong ứng dụng, cần ghi nhận hoặc xử lý callback lặp để tránh âm thầm bỏ qua lỗi logic.

## 10. Lựa chọn Sinks theo tình huống

| Nhu cầu | Lựa chọn gợi ý | Lý do |
|---|---|---|
| Một callback trả về một kết quả | `Sinks.One` | Chuyển kết quả thành Mono |
| Một worker nhận lệnh riêng | `Sinks.many().unicast()` | Một subscriber, có thể buffer |
| Phát thông báo đến các thành phần đang hoạt động | `multicast().onBackpressureBuffer()` | Nhiều subscriber và giữ dữ liệu theo demand/capacity |
| Subscriber chậm có thể làm lần phát thất bại cho tất cả | `directAllOrNothing()` | Đồng bộ tập phần tử được nhận |
| Subscriber chậm có thể bỏ lỡ phần tử | `directBestEffort()` | Subscriber có demand vẫn nhận |
| Subscriber đến muộn cần trạng thái gần đây | `replay().limit(n)` | Phát lại lịch sử trong giới hạn |
| Cần lịch sử đầy đủ và hữu hạn | `replay().all()` | Giữ mọi phần tử cho subscriber sau |

Trước khi chọn sink, hãy trả lời:

1. Nguồn phát một kết quả hay nhiều phần tử?
2. Có một subscriber hay nhiều subscriber?
3. Subscriber đăng ký muộn có cần nhận lại lịch sử không?
4. Subscriber chậm có được phép bỏ dữ liệu không?
5. Buffer tối đa bao nhiêu phần tử hoặc bao nhiêu byte?
6. Producer có thể retry, tạm dừng hoặc từ chối dữ liệu khi emit thất bại không?
7. Ai chịu trách nhiệm gửi complete/error và giải phóng nguồn bên ngoài?

## 11. Bài tập vận dụng

Một dịch vụ theo dõi đơn hàng nhận sự kiện từ SDK bên ngoài. Màn hình đang mở cần nhận thông báo mới ngay khi có sự kiện. Khi người dùng mở màn hình muộn, họ cần xem lại tối đa mười trạng thái gần nhất. Một thao tác xác nhận đơn hàng khác chỉ tạo một kết quả duy nhất.

Hãy thiết kế ba sink:

- Dùng multicast sink cho thông báo trực tiếp đến các màn hình đang hoạt động.
- Dùng replay sink có giới hạn mười phần tử cho lịch sử trạng thái.
- Dùng Sinks.One để chuyển kết quả của thao tác xác nhận thành Mono.

Sau đó trả lời:

1. Vì sao một multicast sink không tự phát lại các thông báo trước khi màn hình đăng ký?
2. Nếu một màn hình không request dữ liệu, bạn chọn buffer, directAllOrNothing hay directBestEffort? Hãy giải thích theo yêu cầu nghiệp vụ.
3. Điều gì xảy ra khi replay sink nhận phần tử thứ mười một với giới hạn mười?
4. Nếu SDK gọi callback success hai lần, EmitResult của lần phát thứ hai có thể là gì?
5. Nếu hai callback phát đồng thời vào cùng Many sink, làm thế nào để tránh FAIL_NON_SERIALIZED?
6. Ai chịu trách nhiệm complete hoặc error sink khi SDK đóng kết nối?

Hãy viết StepVerifier xác nhận một kết quả Sinks.One, một luồng Many có nhiều phần tử và một subscriber muộn nhận lại lịch sử giới hạn. Bổ sung kiểm thử cho trường hợp emit sau terminal và ghi nhận cách ứng dụng xử lý lỗi phát.

## Kết luận

Sinks là điểm phát dữ liệu chủ động để nối mã imperative hoặc callback vào hệ sinh thái Publisher–Subscriber. Sinks.One biểu diễn một kết quả đơn; Sinks.Many phát nhiều phần tử và cần chọn unicast, multicast hoặc replay theo số subscriber cùng nhu cầu lịch sử. Chính sách buffer, directAllOrNothing và directBestEffort quyết định cách xử lý subscriber chậm. Việc kiểm tra EmitResult, tuần tự hóa producer và quản lý complete/error giúp sink hoạt động có kiểm soát trong pipeline Reactor.
