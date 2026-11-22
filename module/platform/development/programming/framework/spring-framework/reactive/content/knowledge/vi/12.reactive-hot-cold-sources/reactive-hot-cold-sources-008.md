# `tryEmit`, `emit`, phát đồng thời và tràn bộ đệm trong Project Reactor Sinks

## 1. Mục tiêu và tình huống thực tế

Trong Spring WebFlux, phần lớn ứng dụng nên tạo dữ liệu bằng các Publisher như `Mono<T>`, `Flux<T>` và trả chúng cho framework xử lý. Tuy nhiên, đôi khi dữ liệu đến từ một API **imperative**: listener của thư viện cũ, callback của SDK, sự kiện từ một kết nối socket hoặc một thread bên ngoài Reactor. Khi đó, ta cần một điểm nối để mã bên ngoài **đẩy tín hiệu vào** một chuỗi reactive.

Project Reactor cung cấp `Sinks` cho tình huống này. Một `Sink` có thể được xem như đầu vào chủ động để phát `onNext`, `onError` và `onComplete`. Hai nhóm API quan trọng:

- `tryEmitNext(value)`: thử phát và trả về `Sinks.EmitResult` để ứng dụng tự quyết định xử lý kết quả.
- `emitNext(value, failureHandler)`: thử phát theo cơ chế có handler; handler có thể yêu cầu Reactor thử lại một số lỗi phát, hoặc để sink áp dụng hành vi lỗi mặc định.

Bài này tập trung vào ba vấn đề được hỏi trong module:

1. **`tryEmit` và `emit` khác nhau thế nào?**
2. **Nhiều producer phát cùng lúc** được xử lý ra sao?
3. **Buffer đầy hoặc subscriber không nhận kịp** thì kết quả là gì và cần xử lý thế nào?

Sau bài học, bạn sẽ biết đọc từng trạng thái `EmitResult`, chọn loại Sink theo số subscriber/lịch sử cần lưu, giới hạn bộ đệm, xử lý tranh chấp giữa các producer và nối callback ngoài vào Spring WebFlux.

## 2. Sink là cầu nối giữa mã imperative và Reactive Streams

Một `Sinks.Many<T>` có thể được cung cấp cho phía đọc dưới dạng `Flux<T>` qua `asFlux()`:

~~~java
Sinks.Many<String> sink = Sinks.many().multicast().onBackpressureBuffer();

Flux<String> events = sink.asFlux();

sink.tryEmitNext("created");
sink.tryEmitNext("updated");
sink.tryEmitComplete();
~~~

`events` là luồng mà consumer đăng ký. Mã producer chủ động gọi `tryEmitNext` để đưa tín hiệu vào Sink. Khi hoàn tất, sink phát `onComplete`; nếu gọi `tryEmitError(error)` thì phát `onError`.

Điểm khác với `Flux.just(...)`:

| Nguồn reactive thông thường | `Sinks.Many` |
| --- | --- |
| Toán tử tạo Publisher mô tả cách tạo/phối hợp dữ liệu | Producer bên ngoài chủ động phát từng tín hiệu |
| Nguồn thường được subscribe theo lifecycle Publisher | Sink có thể được giữ như một điểm nhận sự kiện lâu hơn một subscription |
| Subscriber điều khiển demand qua Reactive Streams | Sink phải xử lý việc producer phát khi subscriber chưa có demand |
| Hợp với xử lý reactive từ đầu đến cuối | Hợp với bridge từ callback/thread/API imperative |

Không dùng Sink chỉ để thay thế `Flux.just`, `Flux.fromIterable` hoặc `Mono.fromCallable`. Nếu nguồn đã có API reactive, giữ nguyên Publisher đó thường đơn giản và dễ quản lý backpressure hơn.

### 2.1. `Sinks.Many`, `Sinks.One` và `Sinks.Empty`

- `Sinks.Many<T>` có semantics gần `Flux<T>`: có thể phát nhiều phần tử.
- `Sinks.One<T>` có semantics gần `Mono<T>`: phát tối đa một giá trị rồi hoàn tất, hoặc hoàn tất rỗng/báo lỗi.
- `Sinks.Empty<T>` chỉ phát terminal signal (`onComplete` hoặc `onError`), không phát giá trị.

Ví dụ khi một callback chỉ hoàn thành một tác vụ:

~~~java
Sinks.One<String> resultSink = Sinks.one();

Mono<String> result = resultSink.asMono();

resultSink.tryEmitValue("done");
~~~

Với stream sự kiện liên tục, thường dùng `Sinks.Many`. Các ví dụ chính trong bài tập trung vào `Many` vì nó làm lộ rõ vấn đề concurrency, demand và overflow.

## 3. `tryEmitNext`: chủ động kiểm tra kết quả phát

### 3.1. Chữ ký và ý nghĩa

~~~java
Sinks.EmitResult result = sink.tryEmitNext(value);
~~~

`tryEmitNext` thử phát một giá trị **không-null** dưới dạng `onNext(value)`. Nó không trả về `boolean` đơn giản mà trả về enum `Sinks.EmitResult`. Vì vậy producer phải đọc kết quả và quyết định:

- Giá trị đã được sink chấp nhận?
- Không có subscriber nào nhận?
- Subscriber đã hủy?
- Sink đã kết thúc?
- Bộ đệm đã đầy?
- Một producer khác đang phát đồng thời?

**`OK` nghĩa là sink đã chấp nhận tín hiệu tại thời điểm gọi.** Nó không phải biên nhận nghiệp vụ rằng mọi subscriber đã xử lý xong dữ liệu. Subscriber có thể xử lý bất đồng bộ, đang thiếu demand hoặc bị hủy trong lúc producer phát.

Mẫu xử lý đơn giản:

~~~java
Sinks.EmitResult result = sink.tryEmitNext(event);

if (result.isSuccess()) {
    // Sink đã chấp nhận tín hiệu.
} else {
    // Phân loại result và áp dụng chính sách phù hợp.
}
~~~

Không bỏ qua kết quả chỉ vì chương trình “có vẻ chạy được”. Nếu giá trị bị từ chối mà producer vẫn tiếp tục như thể đã phát thành công, ứng dụng có thể mất sự kiện mà không biết.

### 3.2. Các giá trị `EmitResult`

| Kết quả | Nguyên nhân | Hướng xử lý thường gặp |
| --- | --- | --- |
| `OK` | Sink chấp nhận tín hiệu | Tiếp tục; không suy ra consumer đã xử lý xong |
| `FAIL_NON_SERIALIZED` | Có nhiều thao tác phát chồng lấn, chưa được tuần tự hóa | Tuần tự hóa producer hoặc retry có giới hạn khi tranh chấp |
| `FAIL_OVERFLOW` | Không còn sức chứa buffer hoặc subscriber không đủ demand theo chính sách Sink | Giảm tốc, giới hạn queue, drop có chủ đích hoặc chuyển sang lưu bền vững |
| `FAIL_ZERO_SUBSCRIBER` | Sink không có subscriber và không có khả năng buffer/warm-up cho tín hiệu đó | Đăng ký consumer trước, chọn loại Sink có buffer hoặc chấp nhận bỏ |
| `FAIL_CANCELLED` | Sink đã bị subscriber/người tiêu thụ hủy hoặc ngắt | Dừng producer hoặc khởi tạo vòng đời mới theo nghiệp vụ |
| `FAIL_TERMINATED` | Sink đã nhận terminal signal trước đó | Không phát thêm; kiểm tra lifecycle hoặc lỗi gọi lặp |

Không phải mọi loại Sink đều có thể tạo ra mọi trạng thái trong mọi tình huống. Ví dụ, một Sink replay có thể lưu dữ liệu trước khi subscriber đăng ký, trong khi direct multicast sink có thể trả `FAIL_ZERO_SUBSCRIBER` ngay khi chưa có người nghe. Cần hiểu chính sách của factory đã chọn.

### 3.3. Phân biệt `tryEmitNext` với terminal methods

Các phương thức tương ứng:

~~~java
Sinks.EmitResult next = sink.tryEmitNext(value);
Sinks.EmitResult complete = sink.tryEmitComplete();
Sinks.EmitResult error = sink.tryEmitError(new IllegalStateException("failed"));
~~~

- `tryEmitNext` bị ảnh hưởng bởi backpressure và sức chứa buffer.
- `tryEmitComplete` không phải phần tử dữ liệu, nên không cần một đơn vị demand `request(1)` để phát.
- `tryEmitError` cũng là terminal signal, không phải phần tử `onNext`.
- Sau `onComplete` hoặc `onError`, sink đã terminal; một lần `tryEmitNext` sau đó thường trả `FAIL_TERMINATED`.
- Không phát `null`. Reactive Streams và Sink yêu cầu phần tử/Throwable hợp lệ, không dùng null để biểu diễn “không có dữ liệu”.

### 3.4. Kiểm tra trạng thái cụ thể thay vì xử lý tất cả thất bại giống nhau

~~~java
switch (sink.tryEmitNext(event)) {
    case OK -> recordAccepted(event);
    case FAIL_NON_SERIALIZED -> enqueueForSingleWriter(event);
    case FAIL_OVERFLOW -> applyOverflowPolicy(event);
    case FAIL_ZERO_SUBSCRIBER -> handleNoConsumer(event);
    case FAIL_CANCELLED -> stopProducing();
    case FAIL_TERMINATED -> reportLateEvent(event);
}
~~~

Đây là **đoạn minh họa**: các hàm `recordAccepted`, `enqueueForSingleWriter`, `applyOverflowPolicy`, `handleNoConsumer`, `stopProducing` và `reportLateEvent` là các chính sách do ứng dụng định nghĩa. Đoạn này cho thấy phải quyết định theo nguyên nhân, không phải chương trình độc lập để copy nguyên xi.

## 4. `emitNext`: dùng EmitFailureHandler để xử lý thất bại

### 4.1. Chữ ký

~~~java
sink.emitNext(value, Sinks.EmitFailureHandler.FAIL_FAST);
~~~

`emitNext` là API tiện lợi xây trên `tryEmitNext`. Khi lần thử không thành công, Reactor hỏi `EmitFailureHandler` xem có nên **thử lại lần phát** hay không:

- Handler trả `true`: implementation được yêu cầu thử lại `tryEmitNext`.
- Handler trả `false`: sink áp dụng hành vi xử lý thất bại mặc định của implementation.

`Sinks.EmitFailureHandler.FAIL_FAST` là handler có sẵn, không yêu cầu retry. Với safe sink của Reactor, nếu thất bại là `FAIL_NON_SERIALIZED`, `emitNext` có thể ném `Sinks.EmissionException`. Nếu thất bại là overflow, hành vi mặc định của `emitNext` có thể đưa sink vào đường `onError` với lỗi overflow. Vì vậy `emitNext` **không phải** một cách “cứ gọi là chắc chắn phát thành công”.

### 4.2. Vì sao `tryEmitNext` thường là lựa chọn tốt khi cần kiểm soát?

`tryEmitNext` trả lại nguyên nhân để producer tự chọn hành động. Đây là lựa chọn phù hợp khi:

- Không có subscriber và ứng dụng muốn lưu sự kiện vào database.
- Buffer đầy và ứng dụng muốn trả lỗi cho caller.
- Có tranh chấp và ứng dụng muốn đưa sự kiện vào một queue tuần tự.
- Một event đã quá hạn hoặc sink đã terminal và cần ghi log/metric.

`emitNext` phù hợp khi ứng dụng muốn một chính sách handler rõ ràng và chấp nhận hành vi mặc định của sink cho các lỗi không được retry. Với logic nghiệp vụ quan trọng, việc kiểm tra `EmitResult` thường minh bạch hơn.

### 4.3. `busyLooping(Duration)` chỉ giải quyết tranh chấp phát đồng thời

Reactor cung cấp:

~~~java
sink.emitNext(
    event,
    Sinks.EmitFailureHandler.busyLooping(Duration.ofSeconds(2))
);
~~~

Handler `busyLooping` có thể chờ ngắn và thử lại khi sink báo `FAIL_NON_SERIALIZED`, tức các producer đang truy cập sink đồng thời. Cần nhớ:

1. Đây là **busy loop có deadline**, không phải hàng đợi bền vững.
2. Nên dùng thời gian đủ thực tế; tài liệu Reactor khuyến nghị trên 100 ms vì thời gian quá ngắn thường không có ý nghĩa.
3. **Tạo handler mới cho từng lần emit**; không cache và tái sử dụng một handler `busyLooping` vì deadline được tính từ lúc tạo handler.
4. Handler này không biến `FAIL_OVERFLOW` thành thành công; buffer đầy là vấn đề capacity/backpressure, không phải tranh chấp ngắn.
5. Không dùng busy loop vô hạn trên event-loop hoặc thread cần phục vụ request khác. Nếu contention kéo dài, hãy serialize producer bằng queue/lock hoặc thiết kế một luồng ghi duy nhất.

### 4.4. Không nhầm handler với retry nghiệp vụ

`EmitFailureHandler` chỉ quyết định có thử lại thao tác **đẩy tín hiệu vào Sink** sau một `EmitResult` thất bại hay không. Nó không gọi lại API HTTP, không chạy lại transaction và không khôi phục dữ liệu đã bị drop. Nếu producer tự retry event, cần bảo đảm không gửi trùng hoặc tạo side effect lặp.

## 5. Phát đồng thời: tại sao có `FAIL_NON_SERIALIZED`?

### 5.1. Reactive Streams yêu cầu tín hiệu được tuần tự hóa

Với cùng một Subscriber, các tín hiệu phải tuân thủ giao thức và không được phát đồng thời chồng lấn. Nếu hai thread cùng gọi:

~~~java
// Thread A
sink.tryEmitNext("A");

// Thread B, cùng thời điểm
sink.tryEmitNext("B");
~~~

thì một trong các lần phát có thể nhận `FAIL_NON_SERIALIZED`. Safe sinks mặc định của Reactor có cơ chế phát hiện concurrent access và từ chối thao tác không được tuần tự hóa; chúng **không tự xếp mọi producer vào một hàng đợi vô hạn**.

Không được hiểu “Sink thread-safe” là mọi lời gọi đồng thời luôn thành công. Tính an toàn ở đây có nghĩa sink bảo vệ hợp đồng tín hiệu và cho biết khi producer vi phạm serialization; producer vẫn phải xử lý kết quả.

### 5.2. Ba chiến lược xử lý

**Chiến lược A — Một writer duy nhất (thường dễ kiểm soát nhất)**

Nhiều thread đưa event vào một queue thread-safe. Chỉ một consumer đọc queue và gọi `tryEmitNext`. Như vậy thao tác phát tới Sink được tuần tự hóa tại một điểm.

~~~text
Producer A ----\
Producer B -----+--> bounded queue --> single writer --> Sink.asFlux()
Producer C ----/
~~~

Ưu điểm: dễ kiểm soát thứ tự, backpressure và overflow. Nhược điểm: cần quản lý queue, thread worker, lifecycle và chính sách khi queue đầy.

**Chiến lược B — Đồng bộ hóa ở producer**

~~~java
private final Object emitLock = new Object();

public Sinks.EmitResult publish(Event event) {
    synchronized (emitLock) {
        return sink.tryEmitNext(event);
    }
}
~~~

Cách này tuần tự hóa lời gọi phát trên cùng lock. Chỉ dùng khi vùng critical section ngắn, không gọi callback chậm hoặc blocking trong lock. Nếu có nhiều instance producer hoặc nhiều process, Java lock trong một object chỉ bảo vệ các thread dùng chung object đó, không tạo khóa phân tán.

**Chiến lược C — Retry tranh chấp có giới hạn**

~~~java
sink.emitNext(
    event,
    Sinks.EmitFailureHandler.busyLooping(Duration.ofSeconds(1))
);
~~~

Cách này có thể phù hợp khi tranh chấp rất ngắn và số producer/tải được kiểm soát. Nếu contention thường xuyên hoặc kéo dài, queue một writer thường dễ dự đoán hơn. Không dùng retry không giới hạn vì sẽ giữ thread producer và có thể tạo nghẽn.

### 5.3. Khi nào dùng `Sinks.unsafe()`?

`Sinks.unsafe().many()` bỏ một số kiểm tra thread-safety/serialization so với safe sinks. Nó chỉ dành cho advanced use case khi **ứng dụng đã bảo đảm mọi lời gọi emit được tuần tự hóa bằng cơ chế khác**. Nếu nhiều producer cùng phát mà không có bảo vệ bên ngoài, việc bỏ kiểm tra có thể phá vỡ giao thức và làm downstream nhận hành vi không hợp lệ.

Mặc định nên dùng các factory safe như `Sinks.many()`. Không chọn unsafe chỉ để loại bỏ `FAIL_NON_SERIALIZED`; cần sửa nguồn concurrency trước.

## 6. Tràn bộ đệm: hiểu nguyên nhân trước khi chọn chính sách

### 6.1. Buffer tồn tại vì producer có thể nhanh hơn consumer

Giả sử producer đẩy 10.000 sự kiện/giây nhưng subscriber chỉ xử lý 1.000 sự kiện/giây. Phần chênh lệch phải được xử lý theo một trong các cách:

- Tạm giữ trong buffer.
- Từ chối phát khi buffer đã đầy.
- Drop một phần hoặc toàn bộ sự kiện theo chính sách.
- Giảm tốc/điều khiển producer.
- Lưu bền vững ngoài bộ nhớ và đọc lại sau.

Buffer chỉ trì hoãn việc phải giải quyết chênh lệch tốc độ; nó không làm consumer xử lý nhanh hơn. Một buffer không giới hạn có thể biến overload thành tăng heap, GC pressure hoặc OutOfMemoryError.

### 6.2. `FAIL_OVERFLOW` nghĩa là gì?

`FAIL_OVERFLOW` cho biết Sink không có đủ capacity để nhận phần tử mới theo chính sách backpressure/buffering hiện tại. Nó có thể xảy ra khi:

- Một unicast sink có queue giới hạn đã đầy.
- Một multicast sink đang buffer cho các subscriber chậm và đã chạm giới hạn.
- Một direct sink không có subscriber nào có demand để nhận phần tử theo chính sách direct.
- Sự chênh lệch demand giữa các subscriber vượt buffer được cấu hình.

Đây không phải tín hiệu để busy-loop liên tục. Nếu subscriber không tiêu thụ, thử phát lại ngay chỉ tạo tải và có thể thất bại tiếp. Ứng dụng cần quyết định drop, retry sau khi consumer có khả năng nhận, giảm tốc, hoặc lưu bền vững.

### 6.3. Hành vi khác nhau giữa `tryEmitNext` và `emitNext` khi overflow

- `tryEmitNext` trả `FAIL_OVERFLOW` để producer tự xử lý. Sink không nhất thiết tự kết thúc chỉ vì lần thử này bị từ chối.
- Với hành vi mặc định của Reactor, `emitNext` khi gặp `FAIL_OVERFLOW` có thể chuyển Sink sang terminal error bằng lỗi overflow. Những subscriber đang theo dõi sẽ nhận `onError`.
- Nếu dùng `emitNext` với handler trả `true` cho overflow một cách thiếu cân nhắc, producer có thể lặp lại thao tác dù capacity không được giải phóng. Chỉ retry khi có cơ chế thực sự làm tăng khả năng thành công.

Với dữ liệu quan trọng, thường nên dùng `tryEmitNext`, xử lý `FAIL_OVERFLOW` một cách tường minh và không giả vờ rằng event đã được nhận.

## 7. Chọn đúng loại Sink: unicast, multicast, replay và direct

### 7.1. Unicast: một subscriber, buffer cho consumer đăng ký sau

~~~java
Sinks.Many<Event> sink =
    Sinks.many().unicast().onBackpressureBuffer();
~~~

- Chỉ chấp nhận **một Subscriber** trên Flux view.
- Các event được phát trước khi subscriber đăng ký có thể được buffer và phát khi subscriber đến.
- Factory không truyền queue mặc định dùng queue không giới hạn; nếu producer có thể phát nhiều trước khi consumer sẵn sàng, phải cân nhắc giới hạn.
- Có thể cung cấp queue tùy chỉnh, ví dụ `ArrayBlockingQueue` có capacity cố định, để có hành vi overflow rõ ràng.

~~~java
Sinks.Many<Event> bounded =
    Sinks.many().unicast()
        .onBackpressureBuffer(new ArrayBlockingQueue<>(256));
~~~

### 7.2. Multicast có backpressure buffer: nhiều subscriber cùng nhận event mới

~~~java
Sinks.Many<Event> sink =
    Sinks.many().multicast().onBackpressureBuffer();
~~~

- Cho phép nhiều subscriber.
- Subscriber chỉ nhận event phát sau khi đã subscribe (cùng phần đang buffer theo backpressure/warm-up).
- Chính sách tôn trọng demand của các subscriber; subscriber chậm có thể khiến buffer tích lũy.
- Có thể chỉ định capacity và `autoCancel` bằng overload phù hợp.
- Mặc định khi tất cả subscriber cancel, sink có thể xóa buffer và ngừng nhận subscriber mới; cần hiểu lifecycle trước khi dùng như event bus lâu dài.

Ví dụ capacity hữu hạn:

~~~java
Sinks.Many<Event> sink =
    Sinks.many().multicast().onBackpressureBuffer(
        512,  // bufferSize
        true  // autoCancel
    );
~~~

Khi chênh lệch demand giữa các subscriber vượt capacity, `tryEmitNext` có thể trả `FAIL_OVERFLOW`. Hãy chọn buffer dựa trên burst và thời gian consumer có thể chậm, không chọn một con số lớn tùy tiện.

### 7.3. Direct multicast: chọn chính sách drop thay vì buffer

`directAllOrNothing()` và `directBestEffort()` không cố buffer cho subscriber chậm như `onBackpressureBuffer`:

| Factory | Khi có subscriber không demand | Hệ quả |
| --- | --- | --- |
| `directAllOrNothing()` | Chỉ cần một subscriber chậm | Drop event cho tất cả subscriber ở lần phát đó; producer có thể nhận `FAIL_OVERFLOW` |
| `directBestEffort()` | Một số subscriber chậm nhưng subscriber khác có demand | Gửi cho subscriber đang sẵn sàng; drop riêng ở subscriber chậm |
| `directBestEffort()` khi không ai có demand | Không subscriber nào nhận được | Producer nhận thất bại overflow |
| Cả hai khi không có subscriber | Không có người nghe/warm-up buffer | `tryEmitNext` có thể trả `FAIL_ZERO_SUBSCRIBER` |

Chọn direct sink khi **drop là một phần hợp đồng được chấp nhận**, ví dụ cập nhật trạng thái mới nhất, telemetry không bắt buộc hoặc tín hiệu có thể mất. Không dùng direct sink cho đơn hàng, giao dịch hoặc event không được phép mất.

### 7.4. Replay: subscriber đến muộn vẫn nhận lịch sử

~~~java
Sinks.Many<Event> replayAll =
    Sinks.many().replay().all();

Sinks.Many<Event> last100 =
    Sinks.many().replay().limit(100);
~~~

Replay sink cache sự kiện và phát lại cho subscriber đến sau:

- `all()` giữ toàn bộ lịch sử, có nguy cơ tăng bộ nhớ không giới hạn.
- `limit(n)` chỉ giữ số lượng phần tử lịch sử giới hạn.
- Có thể dùng giới hạn theo thời gian hoặc kết hợp số lượng và thời gian.

Replay phù hợp với trạng thái/stream cần late subscriber nhận lại history. Nó không thay thế database/event log bền vững: dữ liệu trong Sink là bộ nhớ tiến trình và mất khi process dừng.

### 7.5. Chọn nhanh

| Nhu cầu | Loại phù hợp |
| --- | --- |
| Một consumer duy nhất; event đến trước subscriber phải được giữ | `unicast().onBackpressureBuffer(...)` |
| Nhiều consumer cùng nhận event mới, có buffer theo demand | `multicast().onBackpressureBuffer(...)` |
| Nhiều consumer; drop tất cả nếu một consumer chậm | `multicast().directAllOrNothing()` |
| Nhiều consumer; drop riêng ở consumer chậm | `multicast().directBestEffort()` |
| Consumer mới cần xem lại lịch sử giới hạn | `replay().limit(n)` |
| Chỉ cần giữ lịch sử trong một cửa sổ thời gian | `replay().limit(Duration)` hoặc overload kết hợp |
| Chỉ một giá trị hoặc một kết quả async | `Sinks.one()` |
| Chỉ cần complete/error không có dữ liệu | `Sinks.empty()` |

## 8. Đọc và xử lý từng lỗi phát

### 8.1. `FAIL_NON_SERIALIZED` — nhiều producer phát cùng lúc

Hành động phù hợp:

- Chuyển sang single-writer queue.
- Dùng lock nếu critical section ngắn và tất cả producer chia sẻ cùng lock.
- Dùng `emitNext` với `busyLooping` nếu contention ngắn, có deadline.
- Không đổi sang `unsafe()` để che lỗi.

Đừng retry bằng cách tạo thêm thread mới cho mỗi lần thất bại; điều đó có thể làm contention nặng hơn.

### 8.2. `FAIL_OVERFLOW` — buffer không còn chỗ

Hành động phù hợp:

- Giảm tốc producer hoặc áp backpressure ở nguồn callback nếu API cho phép.
- Giảm concurrency, tăng tốc consumer hoặc chia tải hợp lý.
- Drop theo chính sách được nghiệp vụ cho phép và đếm số event đã drop.
- Đưa event vào queue/database bền vững rồi phát lại khi downstream sẵn sàng.
- Trả lỗi cho producer để upstream quyết định retry có delay.

Không dùng `busyLooping` như cách xử lý overflow: buffer không tự có thêm chỗ chỉ vì producer bận chờ.

### 8.3. `FAIL_ZERO_SUBSCRIBER` — chưa có consumer

Câu hỏi cần trả lời: event phát trước subscriber có cần được giữ không?

- Nếu có, chọn unicast buffer hoặc replay phù hợp.
- Nếu không, direct sink có thể trả thất bại; producer có thể bỏ qua có ghi metric.
- Nếu consumer bắt buộc phải có trước khi producer chạy, quản lý startup order và chỉ bắt đầu producer sau khi subscription đã được thiết lập.

`currentSubscriberCount()` chỉ là phép quan sát best-effort tại một thời điểm; đừng dùng nó làm kiểm tra bảo đảm trước khi emit vì trạng thái có thể thay đổi ngay sau đó.

### 8.4. `FAIL_CANCELLED` — consumer đã hủy

Khi subscriber rời đi, producer cần biết có nên dừng nguồn ngoài hay không. Ví dụ, nếu Sink đại diện một socket subscription dành riêng cho một client, cancellation có thể là lúc unregister listener/đóng socket. Nếu Sink là event bus dùng chung cho nhiều consumer, một subscriber cancel chưa chắc là lý do dừng producer.

Không bỏ qua cancellation rồi tiếp tục tạo event vô hạn vào một sink không còn ai đọc.

### 8.5. `FAIL_TERMINATED` — phát sau terminal

Một Sink chỉ kết thúc một lần. Sau `tryEmitComplete` hoặc `tryEmitError` thành công, mọi `onNext` tiếp theo là event đến muộn hoặc lỗi lifecycle. Hãy kiểm tra:

- Producer có còn chạy sau khi ứng dụng đóng không?
- Có hai nơi cùng gọi complete/error không?
- Callback cũ có tiếp tục phát sau khi request/session đã kết thúc?
- Có cần tạo Sink mới cho một lifecycle mới thay vì tái sử dụng Sink đã terminal?

### 8.6. `FAIL_ZERO_SUBSCRIBER` và terminal signal có thể khác nhau

Một số Sink có thể lưu terminal signal để subscriber đăng ký sau nhận được `onComplete`/`onError`; hành vi cụ thể phụ thuộc loại Sink. Vì vậy đừng áp một kết luận của `tryEmitNext` cho `tryEmitComplete` hoặc `tryEmitError`. Đọc Javadoc của factory đang sử dụng và xử lý từng kết quả riêng.

## 9. Ví dụ Java 17+ hoàn chỉnh: overflow và producer đồng thời

Ví dụ dùng Project Reactor Core **3.8.8**, Java 17+ và Maven. Chương trình thể hiện:

1. `tryEmitNext` với queue unicast giới hạn một phần tử, cho thấy `FAIL_OVERFLOW`.
2. Phát đồng thời từ hai producer vào một safe sink bằng `emitNext` và handler `busyLooping`.
3. Đóng sink bằng `tryEmitComplete` sau khi tất cả producer đã xong.

Cấu trúc dự án:

~~~text
reactor-sinks-demo/
├── pom.xml
└── src/main/java/example/SinksEmissionDemo.java
~~~

### 9.1. Tệp `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>reactor-sinks-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.8.8</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
                <configuration>
                    <mainClass>example.SinksEmissionDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 9.2. Tệp `src/main/java/example/SinksEmissionDemo.java`

~~~java
package example;

import java.time.Duration;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import reactor.core.publisher.Sinks;

public final class SinksEmissionDemo {

    private static void demonstrateOverflow() {
        System.out.println("== bounded buffer ==");

        Sinks.Many<Integer> bounded = Sinks.many()
            .unicast()
            .onBackpressureBuffer(new ArrayBlockingQueue<>(1));

        System.out.println("first=" + bounded.tryEmitNext(1));
        System.out.println("second=" + bounded.tryEmitNext(2));
        System.out.println("complete=" + bounded.tryEmitComplete());

        bounded.asFlux().subscribe(
            value -> System.out.println("received=" + value),
            error -> System.out.println("error=" + error.getClass().getSimpleName()),
            () -> System.out.println("downstream complete")
        );
    }

    private static void demonstrateConcurrentProducers() throws Exception {
        System.out.println("== concurrent producers ==");

        Sinks.Many<Integer> sink = Sinks.many()
            .unicast()
            .onBackpressureBuffer();

        List<Integer> received =
            Collections.synchronizedList(new ArrayList<>());
        AtomicReference<Throwable> failure = new AtomicReference<>();
        CountDownLatch completed = new CountDownLatch(1);

        sink.asFlux().subscribe(
            received::add,
            failure::set,
            completed::countDown
        );

        ExecutorService pool = Executors.newFixedThreadPool(2);
        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch start = new CountDownLatch(1);
        List<Future<?>> tasks = new ArrayList<>();

        for (int producer = 0; producer < 2; producer++) {
            final int base = producer * 10;

            tasks.add(pool.submit(() -> {
                ready.countDown();

                if (!start.await(2, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("start timeout");
                }

                for (int i = 0; i < 10; i++) {
                    // Tạo handler mới cho từng lần emit.
                    sink.emitNext(
                        base + i,
                        Sinks.EmitFailureHandler.busyLooping(
                            Duration.ofSeconds(2))
                    );
                }
                return null;
            }));
        }

        if (!ready.await(2, TimeUnit.SECONDS)) {
            throw new IllegalStateException("producer not ready");
        }
        start.countDown();

        for (Future<?> task : tasks) {
            task.get();
        }

        pool.shutdown();
        if (!pool.awaitTermination(2, TimeUnit.SECONDS)) {
            throw new IllegalStateException("producer pool did not stop");
        }

        System.out.println("complete=" + sink.tryEmitComplete());

        if (!completed.await(2, TimeUnit.SECONDS)) {
            throw new IllegalStateException("sink did not complete");
        }
        if (failure.get() != null) {
            throw new IllegalStateException("downstream failed", failure.get());
        }

        List<Integer> sorted = new ArrayList<>(received);
        Collections.sort(sorted);

        System.out.println("received count=" + sorted.size());
        System.out.println("values=" + sorted);
    }

    public static void main(String[] args) throws Exception {
        demonstrateOverflow();
        demonstrateConcurrentProducers();
    }
}
~~~

Chạy từ thư mục `reactor-sinks-demo` (đã cài JDK 17+ và Maven):

~~~bash
mvn -q compile exec:java
~~~

**Stdout dự kiến:**

~~~text
== bounded buffer ==
first=OK
second=FAIL_OVERFLOW
complete=OK
received=1
downstream complete
== concurrent producers ==
complete=OK
received count=20
values=[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19]
~~~

Giải thích:

- Queue đầu tiên có capacity 1 và chưa có subscriber. `tryEmitNext(1)` chiếm chỗ; `tryEmitNext(2)` bị từ chối với `FAIL_OVERFLOW`. Việc thử phát thứ hai bằng `tryEmitNext` không tự làm queue có thêm chỗ.
- `tryEmitComplete` vẫn có thể gửi terminal signal dù queue còn một phần tử; khi subscriber đăng ký, phần tử đã nhận được buffer được phát rồi complete.
- Ví dụ concurrent có một subscriber và hai producer cùng gọi Sink. `busyLooping` chỉ xử lý tranh chấp `FAIL_NON_SERIALIZED` trong khoảng thời gian giới hạn; mỗi lần emit tạo một handler mới.
- Thứ tự thực tế giữa hai producer có thể xen kẽ khác nhau. Chương trình sắp xếp bản sao danh sách trước khi in để stdout ổn định; Sink không hứa thứ tự theo thời điểm bắt đầu của hai producer.
- `received count=20` chứng minh ví dụ đã nhận đủ 20 giá trị; nó không chứng minh busy-looping là giải pháp tối ưu cho mọi tải. Với hệ thống lớn, hãy cân nhắc một writer duy nhất và queue có giới hạn.
- `Collections.synchronizedList` bảo vệ danh sách nhận khi callback có thể chạy trên các producer thread khác nhau. Trong code production, dùng cấu trúc concurrent hoặc consumer phù hợp với yêu cầu thực tế.

## 10. `tryEmitNext` kiểm tra trạng thái: ví dụ cho từng kết quả

Một số trạng thái phụ thuộc loại Sink và thời điểm. Ví dụ:

~~~java
// FAIL_ZERO_SUBSCRIBER: direct sink không buffer khi chưa có người nghe.
Sinks.Many<Integer> direct =
    Sinks.many().multicast().directAllOrNothing();

Sinks.EmitResult noSubscriber = direct.tryEmitNext(1);

// FAIL_TERMINATED: phát sau khi sink đã hoàn tất.
Sinks.Many<Integer> finished =
    Sinks.many().replay().all();

finished.tryEmitComplete();
Sinks.EmitResult afterComplete = finished.tryEmitNext(2);
~~~

`FAIL_CANCELLED` xảy ra khi sink đã bị hủy bởi consumer/lifecycle. `FAIL_NON_SERIALIZED` xảy ra khi safe sink phát hiện hai thao tác phát chồng lấn. `FAIL_OVERFLOW` được minh họa trong chương trình mục 9. Không cố tạo các trạng thái race trong unit test bằng cách dựa vào timing ngẫu nhiên; hãy kiểm thử chính sách xử lý theo từng kết quả bằng cách tách logic quyết định ra thành hàm độc lập.

### 10.1. Mẫu xử lý kết quả có hành động rõ ràng

~~~java
void publish(Event event) {
    Sinks.EmitResult result = sink.tryEmitNext(event);

    switch (result) {
        case OK -> metrics.accepted();
        case FAIL_NON_SERIALIZED -> retryViaSingleWriter(event);
        case FAIL_OVERFLOW -> persistOrReject(event);
        case FAIL_ZERO_SUBSCRIBER -> metrics.noConsumer();
        case FAIL_CANCELLED -> stopSource();
        case FAIL_TERMINATED -> metrics.lateEvent();
    }
}
~~~

Đây là **mẫu thiết kế**, các hàm metric/queue/persistence do ứng dụng định nghĩa. Chỉ tăng counter mà không có chính sách cho event quan trọng vẫn có thể làm mất dữ liệu.

## 11. Kết nối Sink với Spring WebFlux

### 11.1. Bridge từ callback API

Giả sử một SDK cũ đăng ký callback để thông báo trạng thái thiết bị. Có thể dùng Sink làm điểm nối:

~~~java
@Component
public class DeviceEventBridge {

    private final Sinks.Many<DeviceEvent> sink =
        Sinks.many().multicast().onBackpressureBuffer(256, true);

    public Flux<DeviceEvent> events() {
        return sink.asFlux();
    }

    public void onSdkEvent(DeviceEvent event) {
        Sinks.EmitResult result = sink.tryEmitNext(event);

        if (result != Sinks.EmitResult.OK) {
            // Áp chính sách cụ thể: metric, persist, reject hoặc stop source.
            handleRejectedEvent(event, result);
        }
    }

    public void close() {
        Sinks.EmitResult result = sink.tryEmitComplete();
        if (result != Sinks.EmitResult.OK) {
            recordCloseResult(result);
        }
    }

    private void handleRejectedEvent(
        DeviceEvent event,
        Sinks.EmitResult result
    ) {
        // Implementation phụ thuộc yêu cầu nghiệp vụ.
    }

    private void recordCloseResult(Sinks.EmitResult result) {
        // Ghi metric/log nếu cần.
    }
}
~~~

Đây là **mã minh họa Spring**, cần các import, bean configuration, class `DeviceEvent` và SDK callback thực tế. Những điểm quan trọng:

- SDK callback là producer imperative; nó gọi `onSdkEvent`.
- Controller/service reactive nhận `Flux<DeviceEvent>` qua `events()`.
- `handleRejectedEvent` phải quyết định cụ thể khi event không được sink nhận; không bỏ qua lỗi.
- `close()` cần được gọi đúng lifecycle (ví dụ khi bean/application shutdown) và sau khi SDK producer đã dừng, tránh callback tiếp tục phát sau terminal.
- Với nhiều subscriber, cần chọn multicast buffer và capacity phù hợp. Nếu event chỉ có một consumer, unicast có thể phù hợp hơn.

### 11.2. Controller trả Publisher cho framework

~~~java
@RestController
@RequestMapping("/devices")
public class DeviceController {

    private final DeviceEventBridge bridge;

    public DeviceController(DeviceEventBridge bridge) {
        this.bridge = bridge;
    }

    @GetMapping(value = "/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<DeviceEvent> events() {
        return bridge.events();
    }
}
~~~

Spring WebFlux quản lý subscription cho response. Nếu client ngắt kết nối, subscriber có thể cancel; bridge phải hiểu việc đó ảnh hưởng thế nào tới Sink và SDK. Với multicast dùng chung, một client cancel không nhất thiết đồng nghĩa phải dừng toàn bộ producer. Với unicast dành riêng một client, cancellation có thể là lúc hủy callback nguồn.

Không gọi `subscribe()` thủ công trong controller rồi trả một response độc lập. Hãy để framework quản lý lifecycle HTTP, lỗi và cancellation.

### 11.3. Không dùng Sink nếu có Publisher reactive sẵn

Nếu WebClient, R2DBC hoặc thư viện đã trả `Flux`/`Mono`, ưu tiên dùng trực tiếp:

~~~java
public Flux<Product> products() {
    return webClient.get()
        .uri("/products")
        .retrieve()
        .bodyToFlux(Product.class);
}
~~~

Tạo Sink thêm một ranh giới imperative, khiến ứng dụng phải tự quản lý concurrency, overflow, terminal signal và cleanup. Chỉ thêm nó khi thực sự cần bridge từ API ngoài Reactive Streams.

## 12. Quản lý lifecycle, terminal signal và cancellation

Một Sink không phải queue vĩnh viễn. Nó có lifecycle:

1. Khởi tạo factory.
2. Producer phát zero hoặc nhiều phần tử.
3. Consumer subscribe và xử lý theo demand.
4. Producer kết thúc bằng `tryEmitComplete` hoặc `tryEmitError`.
5. Producer dừng; các lần phát sau terminal được từ chối.

Một số quy tắc:

- Chỉ một terminal signal có hiệu lực; không gửi complete rồi lại error.
- Dừng nguồn imperative trước hoặc đồng bộ hóa việc shutdown để tránh callback phát sau terminal.
- Nếu subscriber cancel, xem xét có cần dừng upstream SDK, unregister listener hay đóng resource.
- Không giữ Sink sống lâu hơn dữ liệu/lifecycle mà nó đại diện; singleton event bus và per-request stream có yêu cầu cleanup khác nhau.
- Nếu Sink được tái sử dụng cho một session mới, thường nên tạo Sink mới cho lifecycle mới thay vì cố reset một Sink đã terminal.
- Đối với dữ liệu quan trọng, đừng dựa vào in-memory Sink như một durable event log. Cần persistence, acknowledgement hoặc message broker phù hợp.

## 13. Lỗi phổ biến và cách phòng tránh

**Lỗi 1 — Gọi `tryEmitNext` rồi bỏ qua kết quả.** Producer có thể mất event do overflow, cancellation hoặc no subscriber. Hãy phân loại `EmitResult`.

**Lỗi 2 — Nghĩ `OK` nghĩa là tất cả subscriber đã xử lý xong.** Nó chỉ cho biết lần phát được sink chấp nhận; không phải acknowledgement nghiệp vụ.

**Lỗi 3 — Dùng `emitNext` và nghĩ nó luôn thành công.** Nếu handler không retry, sink áp dụng hành vi thất bại mặc định; một số lỗi có thể ném exception hoặc terminate sink.

**Lỗi 4 — Nhiều producer gọi Sink cùng lúc mà không xử lý `FAIL_NON_SERIALIZED`.** Dùng single writer, lock có kiểm soát hoặc handler retry có deadline.

**Lỗi 5 — Dùng `busyLooping` cho overflow.** Busy loop xử lý contention không được serialize; nó không tạo capacity mới cho buffer đầy.

**Lỗi 6 — Dùng `busyLooping` vô hạn.** Giữ thread producer và làm nghẽn hệ thống. Luôn dùng deadline hợp lý; nếu contention phổ biến, thiết kế lại producer.

**Lỗi 7 — Tái sử dụng cùng một handler `busyLooping`.** Deadline được tính từ lúc tạo handler. Tạo handler mới cho từng lần emit.

**Lỗi 8 — Dùng unicast queue mặc định không giới hạn cho nguồn có thể phát lâu trước subscriber.** Bộ nhớ có thể tăng liên tục. Cân nhắc queue bounded và xử lý `FAIL_OVERFLOW`.

**Lỗi 9 — Dùng replay().all() cho stream vô hạn.** Lịch sử tăng theo thời gian. Dùng giới hạn số lượng hoặc thời gian nếu không cần giữ toàn bộ.

**Lỗi 10 — Chọn direct sink trong khi không được phép mất event.** directAllOrNothing/directBestEffort có thể drop theo demand. Chọn buffer hoặc persistence khi cần bảo toàn.

**Lỗi 11 — Nghĩ unicast có thể có nhiều subscriber.** Flux view chỉ chấp nhận một subscriber. Nếu cần fan-out, dùng multicast/replay.

**Lỗi 12 — Cho rằng multicast buffer có dung lượng vô hạn.** Capacity được giới hạn theo factory/cấu hình. Khi buffer đầy, producer phải có chính sách overflow.

**Lỗi 13 — Dùng Sink như thay thế cho mọi Flux.** Nếu nguồn đã reactive, Sink chỉ tăng độ phức tạp quản lý.

**Lỗi 14 — Dùng Sinks.unsafe() để che lỗi concurrency.** Unsafe bỏ kiểm tra bảo vệ; chỉ dùng khi external serialization đã được chứng minh.

**Lỗi 15 — Gọi complete/error nhiều lần hoặc phát sau terminal.** Kiểm tra lifecycle và dừng producer đúng thời điểm.

**Lỗi 16 — Dùng null để biểu diễn event rỗng.** Sink không phát null. Dùng kiểu dữ liệu rõ ràng hoặc terminal signal phù hợp.

**Lỗi 17 — Nghĩ buffer đầy là subscriber sẽ tự báo lỗi ngay.** Với `tryEmitNext`, producer nhận kết quả overflow và cần hành động; với `emitNext` hành vi mặc định có thể chuyển thành terminal error. Phân biệt API đang dùng.

**Lỗi 18 — Không giám sát drop và overflow.** Ghi metric số lần `FAIL_OVERFLOW`, `FAIL_NON_SERIALIZED`, event bị từ chối, queue depth và tốc độ consumer để phát hiện sớm.

## 14. Bài tập tự kiểm tra

1. `tryEmitNext(value)` trả về gì? **`Sinks.EmitResult`**, không phải boolean.
2. `OK` có đảm bảo consumer đã xử lý event xong không? **Không**, chỉ là sink chấp nhận tín hiệu tại thời điểm emit.
3. `FAIL_NON_SERIALIZED` nói lên điều gì? **Các thao tác emit chồng lấn, chưa được serialize**.
4. Có nên dùng `busyLooping` khi `FAIL_OVERFLOW` xảy ra không? **Không**, cần giải quyết capacity/demand.
5. `emitNext(value, FAIL_FAST)` có thể làm gì khi safe sink phát đồng thời? **Có thể ném `Sinks.EmissionException` do `FAIL_NON_SERIALIZED`**.
6. Một `unicast().onBackpressureBuffer()` có thể có hai subscriber không? **Không**, chỉ một subscriber.
7. `multicast().directBestEffort()` xử lý subscriber chậm thế nào? **Drop cho subscriber chậm, tiếp tục phát cho subscriber có demand**.
8. `multicast().directAllOrNothing()` xử lý khi một subscriber không có demand thế nào? **Drop event cho tất cả subscriber ở lần phát đó**.
9. Khi buffer bounded đầy, `tryEmitNext` thường trả gì? **`FAIL_OVERFLOW`**.
10. `tryEmitComplete` có cần demand như `onNext` không? **Không**, terminal signal không phải phần tử dữ liệu.
11. Vì sao không nên cache handler `busyLooping`? **Deadline được tính từ lúc tạo handler**, nên lần dùng sau có thể hết hạn.
12. `replay().all()` có rủi ro gì? **Lưu toàn bộ lịch sử trong bộ nhớ**, có thể tăng không giới hạn.
13. Khi callback SDK phát sau khi sink đã complete, kết quả gì có thể xuất hiện? **`FAIL_TERMINATED`**.
14. Khi đã có WebClient trả `Flux`, có nên bọc qua Sink không? **Thông thường không cần**; giữ Publisher reactive trực tiếp.
15. Vì sao safe Sink vẫn có thể trả `FAIL_NON_SERIALIZED`? Vì nó phát hiện concurrent access và từ chối tín hiệu không được tuần tự hóa, bảo vệ hợp đồng Reactive Streams.

## 15. Tài liệu tham khảo chính thức

- [Project Reactor Reference — Sinks](https://projectreactor.io/docs/core/release/reference/coreFeatures/sinks.html): các loại Sink, unicast/multicast/replay, phát đồng thời và cách chuyển sang `Flux`/`Mono`.
- [Project Reactor API — Sinks.Many](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Sinks.Many.html): `tryEmitNext`, `emitNext`, `tryEmitComplete`, `tryEmitError` và hành vi khi emit thất bại.
- [Project Reactor API — Sinks.EmitResult](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Sinks.EmitResult.html): ý nghĩa `OK`, `FAIL_NON_SERIALIZED`, `FAIL_OVERFLOW`, `FAIL_ZERO_SUBSCRIBER`, `FAIL_CANCELLED` và `FAIL_TERMINATED`.
- [Project Reactor API — Sinks.EmitFailureHandler](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Sinks.EmitFailureHandler.html): `FAIL_FAST`, `busyLooping(Duration)`, deadline và điều kiện retry.
- [Project Reactor API — Sinks.MulticastSpec](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Sinks.MulticastSpec.html): buffer capacity, `autoCancel`, directAllOrNothing và directBestEffort.
- [Project Reactor API — Sinks.UnicastSpec](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Sinks.UnicastSpec.html): một subscriber và custom queue.
- [Reactive Streams JVM Specification](https://github.com/reactive-streams/reactive-streams-jvm#specification): quy tắc tuần tự hóa tín hiệu, demand, terminal signal và cancellation.