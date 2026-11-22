# Sinks.One và Sinks.Many trong Project Reactor

> **Module:** Spring Framework – reactive · **Chủ đề cha:** Nguồn nóng và lạnh. Bài học hướng dẫn dùng **Project Reactor Sinks** để chủ động phát tín hiệu từ code imperative, callback hoặc nhiều thành phần sản xuất dữ liệu. Nội dung bao gồm `Sinks.One`, `Sinks.Empty`, `Sinks.Many`, các kiểu unicast/multicast/replay, backpressure, xử lý producer đồng thời, kiểm thử và tích hợp Spring WebFlux.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích **Sink là một điểm phát tín hiệu chủ động** và vì sao nó thường đại diện một nguồn nóng (hot source).
2. Chọn `Sinks.One` cho một kết quả duy nhất, `Sinks.Empty` cho terminal signal không có dữ liệu, và `Sinks.Many` cho luồng nhiều phần tử.
3. Phân biệt `unicast`, `multicast`, `replay`, `directAllOrNothing` và `directBestEffort` theo số subscriber, lịch sử dữ liệu và backpressure.
4. Dùng `tryEmit...`/`emit...` đúng cách, đọc `Sinks.EmitResult` và xử lý `FAIL_NON_SERIALIZED`, `FAIL_OVERFLOW`, `FAIL_TERMINATED`.
5. Hiểu vì sao Sinks thread-safe mặc định vẫn có thể từ chối hai producer phát đồng thời; biết khi nào cần serialize producer hoặc dùng `EmitFailureHandler`.
6. Thiết kế giới hạn bộ đệm, vòng đời sink, terminal signal và hành vi khi không có subscriber hoặc subscriber đến muộn.
7. Viết chương trình Java 17+ chạy được, test bằng `StepVerifier`, và nối event hub vào endpoint SSE của Spring WebFlux.

**Ý tưởng cốt lõi:** `Mono` và `Flux` mô tả một chuỗi xử lý; `Sinks` cung cấp một cổng để **đẩy tín hiệu vào** chuỗi đó từ bên ngoài. Bạn điều khiển lúc nào giá trị, lỗi hoặc hoàn tất được phát. Chính vì vậy bạn phải quyết định rõ ai được nhận, dữ liệu có được giữ lại, điều gì xảy ra khi consumer chậm và cách xử lý nhiều producer.

## 2. Sink là gì? Khi nào cần dùng?

`Sinks` nằm trong `reactor.core.publisher`. Một Sink là một cấu trúc cho phép code **chủ động phát** Reactive Streams signal:
- `tryEmitNext(value)` / `emitNext(...)`: phát một giá trị.
- `tryEmitValue(value)` / `emitValue(...)`: phát một giá trị và hoàn tất, dành cho `Sinks.One`.
- `tryEmitEmpty()` / `emitEmpty(...)`: hoàn tất không có giá trị.
- `tryEmitError(error)` / `emitError(...)`: kết thúc bằng lỗi.
- `tryEmitComplete()` / `emitComplete(...)`: hoàn tất một `Sinks.Many`.

Sink thường được dùng để nối một nguồn phát dữ liệu theo kiểu imperative vào thế giới reactive: callback từ SDK, listener sự kiện, thông báo từ thread khác, job hoàn tất, hoặc một event hub trong ứng dụng. Sink có thể được expose ra downstream bằng **`asMono()`** hoặc **`asFlux()`**.

~~~text
Producer / callback / listener / thread
                |
                | tryEmitNext / tryEmitValue / tryEmitError
                v
             Sinks
                |
                | asFlux() hoặc asMono()
                v
       Reactor operators (map/filter/flatMap)
                |
                v
         WebFlux / Subscriber
~~~

**Sinks là hot source:** producer có thể phát khi không có subscriber, tùy loại sink và chính sách buffer/replay. Subscriber đến sau chỉ nhận những gì loại sink đã giữ lại hoặc những tín hiệu terminal được replay. Đây là khác biệt lớn với một cold Publisher như `Flux.defer(...)`, thường thực hiện nguồn mới cho mỗi subscription.

### 2.1. Không dùng Sink chỉ để làm mọi Flux thành hot

Nếu dữ liệu đã là một `Publisher`, thường compose trực tiếp bằng `map`, `flatMap`, `merge`, `share`, `cache`, `publish` hoặc `defer`. Nếu chỉ cần tạo Flux từ callback gắn riêng với từng subscription, `Flux.create`/`Mono.create` có thể phù hợp hơn vì lifecycle callback gắn với subscriber. Dùng `Sinks` khi bạn thật sự cần một **điểm phát độc lập** được nhiều thành phần gọi tới.

Một Sink thường tồn tại lâu hơn một subscription. Vì vậy cần nghĩ tới:
- ai sở hữu và hoàn tất sink;
- có subscriber nào được phép đăng ký;
- dữ liệu trước subscriber đầu tiên có bị giữ không;
- subscriber mới có được nhận lịch sử không;
- nếu không có ai nghe, producer tiếp tục, buffer hay thất bại;
- ứng dụng shutdown thì sink kết thúc thế nào.

### 2.2. Sinks thay thế cho Processor cũ

Các `Processor` cũ như `MonoProcessor`, `UnicastProcessor`, `EmitterProcessor`, `ReplayProcessor` đã bị deprecated trong Reactor hiện đại; hướng mới là `Sinks.One`, `Sinks.Empty` và các biến thể `Sinks.many()`. Sinks có API phát tín hiệu rõ hơn và phát hiện việc truy cập đồng thời không được serialize. Không bắt đầu dự án mới với Processor cũ.

## 3. Sinks.One: một kết quả, một lần hoàn tất

`Sinks.one()` tạo một **`Sinks.One<T>`**, có ngữ nghĩa Mono: tối đa một giá trị rồi hoàn tất, hoặc hoàn tất rỗng, hoặc lỗi. Nó giống một promise/future reactive mà producer có thể hoàn thành sau này. Kết quả terminal được giữ để subscriber đến muộn vẫn nhận cùng kết quả.

~~~java
Sinks.One<String> sink = Sinks.one();
Mono<String> result = sink.asMono();

// Producer quyết định hoàn tất sau:
Sinks.EmitResult emitted = sink.tryEmitValue("ready");
~~~

`asMono()` trả view Mono để các thành phần consumer subscribe. `tryEmitValue("ready")` phát `onNext("ready")` rồi `onComplete`; nó **không phải** một luồng phát nhiều giá trị. Nếu sink đã được hoàn tất trước khi subscriber đăng ký, subscriber đến sau vẫn thấy kết quả.

### 3.1. Ba cách hoàn tất

~~~java
Sinks.One<String> valueSink = Sinks.one();
valueSink.tryEmitValue("found");       // onNext("found"), onComplete

Sinks.One<String> emptySink = Sinks.one();
emptySink.tryEmitEmpty();              // onComplete, không onNext

Sinks.One<String> errorSink = Sinks.one();
errorSink.tryEmitError(new IllegalStateException("failed")); // onError
~~~

Các fragment dùng cùng kiểu `Sinks.One<String>` nhưng là **ba sink độc lập**. Mỗi sink chỉ có thể hoàn tất một lần; sau khi đã terminal, lần emit tiếp theo thường trả `FAIL_TERMINATED`. Không dùng `null` như dữ liệu: Reactive Streams không cho `onNext(null)`. Javadoc của `Sinks.One.tryEmitValue(null)` quy định `null` chỉ tạo complete rỗng; trong code nghiệp vụ hãy dùng `tryEmitEmpty()` để ý nghĩa rõ ràng.

### 3.2. Khi nào dùng One?

- Một callback HTTP/SDK chỉ trả một kết quả.
- Một job hoàn tất và cần expose kết quả cho nhiều consumer.
- Một thành phần cần công bố trạng thái khởi tạo xong.
- Một promise dùng chung giữa producer imperative và consumer reactive.

**Lưu ý:** `Sinks.One` là một nguồn dùng chung, không tự tạo một công việc mới cho mỗi subscriber. Nếu một subscriber hủy trước khi producer phát, điều đó không có nghĩa sink tự hủy hoặc producer đã dừng; sink vẫn có thể được hoàn tất cho subscriber khác hoặc subscriber đến sau. Cần xác định ai sở hữu sink và thời điểm timeout/dispose theo lifecycle của job.

## 4. Sinks.Empty: chỉ phát terminal signal

`Sinks.empty()` tạo `Sinks.Empty<T>`, expose dưới dạng `Mono<T>` nhưng không phát dữ liệu. Nó chỉ phát **onComplete** hoặc **onError**. Đây là cách biểu diễn một thao tác cần báo “đã xong” mà không có giá trị.

~~~java
Sinks.Empty<Void> completed = Sinks.empty();
Mono<Void> done = completed.asMono();

// Khi thao tác bên ngoài hoàn tất:
Sinks.EmitResult result = completed.tryEmitEmpty();
~~~

Dùng `Sinks.Empty<Void>` cho callback “hoàn tất”, hoặc generic khác nếu kiểu view Mono của API cần được khai báo. `tryEmitError(...)` kết thúc bằng lỗi. Subscriber đến sau vẫn nhận terminal signal theo semantics của sink.

**Phân biệt:** `Sinks.Empty<T>` không phải một `Sinks.Many<T>` rỗng; nó không phát `onNext` nào cả và chỉ có một lần terminal. `Sinks.One<T>` mở rộng semantics này bằng khả năng phát thêm một giá trị.

## 5. Sinks.Many: nhiều phần tử và nhiều subscriber

`Sinks.many()` là builder cho `Sinks.Many<T>`. Sink này có thể phát nhiều `onNext` trước khi hoàn tất hoặc lỗi; view consumer là `Flux<T>` qua `asFlux()`.

~~~java
Sinks.Many<String> events =
    Sinks.many().multicast().onBackpressureBuffer();

Flux<String> stream = events.asFlux();

events.tryEmitNext("created");
events.tryEmitNext("updated");
events.tryEmitComplete();
~~~

`Sinks.Many` có ba nhóm quan trọng: **unicast**, **multicast** và **replay**. Chọn nhóm theo số lượng subscriber và chính sách lịch sử, không theo tên nào nghe “nhanh” hơn.

| Loại | Subscriber | Dữ liệu trước subscriber đầu tiên | Subscriber đến muộn |
| --- | --- | --- | --- |
| `many().unicast().onBackpressureBuffer()` | Chỉ một subscriber | Buffer và phát lại khi subscriber đầu tiên đăng ký | Subscriber thứ hai bị từ chối |
| `many().multicast().onBackpressureBuffer()` | Nhiều subscriber | Có warm-up buffer giới hạn | Chỉ nhận sự kiện mới từ lúc đăng ký, không replay lịch sử cũ |
| `many().multicast().directAllOrNothing()` | Nhiều subscriber | Không buffer | Không replay; một subscriber chậm làm sự kiện bị từ chối cho tất cả |
| `many().multicast().directBestEffort()` | Nhiều subscriber | Không buffer | Không replay; subscriber chậm có thể bỏ lỡ riêng sự kiện |
| `many().replay().all()` | Nhiều subscriber | Lưu tất cả dữ liệu | Subscriber mới nhận toàn bộ lịch sử đã giữ |
| `many().replay().limit(n)` | Nhiều subscriber | Lưu tối đa n phần tử gần nhất | Subscriber mới nhận lịch sử tối đa n phần tử |

Tất cả các loại `Many` đều có thể nhận `tryEmitNext`, `tryEmitError` và `tryEmitComplete`, nhưng **kết quả khi không có subscriber, subscriber chậm hoặc buffer đầy phụ thuộc loại sink**.

## 6. Unicast: một producer channel cho một subscriber

`Sinks.many().unicast().onBackpressureBuffer()` cho phép **một subscriber duy nhất**. Điểm hữu ích là producer có thể phát trước khi subscriber đăng ký; các giá trị được buffer rồi chuyển tiếp khi subscriber đầu tiên đến. Sink tuân theo demand của subscriber đó.

~~~java
Sinks.Many<Integer> queue = Sinks.many()
    .unicast()
    .onBackpressureBuffer();

queue.tryEmitNext(1);
queue.tryEmitNext(2);
queue.tryEmitNext(3);

// Subscriber đầu tiên đến sau:
Flux<Integer> values = queue.asFlux();
~~~

Với mặc định, internal buffer của unicast có thể **không giới hạn**. Nếu producer nhanh hơn subscriber hoặc subscriber chưa xuất hiện lâu, heap có thể tăng không kiểm soát. Có thể truyền queue hữu hạn:

~~~java
Queue<Integer> boundedQueue = new ArrayBlockingQueue<>(128);

Sinks.Many<Integer> queue = Sinks.many()
    .unicast()
    .onBackpressureBuffer(boundedQueue);
~~~

Fragment cần import `java.util.Queue` và `java.util.concurrent.ArrayBlockingQueue`. Queue được truyền vào phải đáp ứng tối thiểu semantics **Single Producer / Single Consumer (SPSC)** theo hợp đồng API. Khi queue đầy, việc emit có thể thất bại với `FAIL_OVERFLOW`; producer phải có chính sách xử lý thay vì bỏ qua kết quả.

**Chọn Unicast khi:** một consumer sở hữu channel, ví dụ một worker nhận công việc từ một producer/bridge callback. Không dùng unicast nếu cần broadcast cho nhiều HTTP client; subscriber thứ hai không được hỗ trợ.

## 7. Multicast: một nguồn phát tới nhiều subscriber

### 7.1. onBackpressureBuffer

`Sinks.many().multicast().onBackpressureBuffer()` cho phép nhiều subscriber nhận các sự kiện mới. Subscriber chỉ nhận dữ liệu được phát **sau khi họ đăng ký**, ngoại trừ một số giá trị warm-up được giữ trước subscriber đầu tiên. Sink phối hợp backpressure giữa các subscriber; nếu một subscriber quá chậm, buffer có thể đầy và emit thất bại.

~~~java
Sinks.Many<String> broadcast = Sinks.many()
    .multicast()
    .onBackpressureBuffer(256, false);
~~~

Trong overload này:
- `256` là buffer size tối đa được cấu hình.
- `false` là lựa chọn `autoCancel`: không tự đóng sink chỉ vì subscriber cuối cùng hủy. Hãy chọn theo lifecycle thực tế; một event hub cấp ứng dụng có thể cần tiếp tục tồn tại khi tạm thời không có client.
- Khi có nhiều subscriber, demand chậm nhất có thể ảnh hưởng việc phát chung. Nếu chênh lệch demand vượt buffer, `tryEmitNext` có thể trả `FAIL_OVERFLOW`; `emitNext` với xử lý mặc định có thể kết thúc sink bằng lỗi overflow.

`onBackpressureBuffer()` không phải replay history. Một subscriber đăng ký sau khi các subscriber khác đã nhận sự kiện trước đó **không nhận lại lịch sử**. Nếu cần lịch sử, chọn replay; nếu không muốn buffer, chọn direct variant.

### 7.2. directAllOrNothing

~~~java
Sinks.Many<Event> sink =
    Sinks.many().multicast().directAllOrNothing();
~~~

Không có buffer. Nếu **bất kỳ subscriber nào** không có demand tại thời điểm emit, sink báo `FAIL_OVERFLOW` và bỏ sự kiện cho **tất cả** subscriber; các subscriber không bị terminate chỉ vì lần emit đó. Phù hợp khi mọi subscriber phải thấy cùng một tập sự kiện hoặc cùng bỏ một sự kiện; không phù hợp nếu dữ liệu không được phép mất.

### 7.3. directBestEffort

~~~java
Sinks.Many<Event> sink =
    Sinks.many().multicast().directBestEffort();
~~~

Cũng không có buffer. Sink gửi sự kiện cho những subscriber đang có demand; subscriber chậm có thể bị bỏ qua riêng sự kiện đó. Nếu **không subscriber nào** có demand, emit thất bại. Đây là lựa chọn cho heartbeat, trạng thái UI hoặc thông báo tạm thời mà một client chậm có thể mất một cập nhật.

**Đừng nhầm `directBestEffort` với replay hoặc reliable delivery.** Nó không giữ lịch sử và không bảo đảm client reconnect nhận lại sự kiện đã bỏ lỡ. Với thông báo tài chính, đơn hàng hoặc nghiệp vụ không được mất, dùng message broker/persistence và event ID/ack phù hợp.

## 8. Replay: giữ lịch sử cho subscriber đến muộn

`Sinks.many().replay()` giữ lại các phần tử đã phát và gửi lịch sử phù hợp cho subscriber mới.

~~~java
Sinks.Many<String> history = Sinks.many()
    .replay()
    .limit(100);

history.tryEmitNext("event-1");
history.tryEmitNext("event-2");
history.tryEmitNext("event-3");

Flux<String> lateSubscriber = history.asFlux();
~~~

Các lựa chọn phổ biến:

| Factory | Lịch sử giữ lại | Khi dùng |
| --- | --- | --- |
| `replay().all()` | Tất cả phần tử | Lịch sử nhỏ, giới hạn vòng đời và số lượng rõ ràng |
| `replay().limit(n)` | Tối đa n phần tử mới nhất | Cửa sổ lịch sử theo số lượng |
| `replay().latest()` | Chỉ giá trị mới nhất | Snapshot/trạng thái hiện tại |
| `replay().latestOrDefault(value)` | Giá trị mới nhất hoặc default | Subscriber cần snapshot ngay cả khi chưa có event |
| `replay().limit(Duration)` | Các phần tử còn trong cửa sổ tuổi | Lịch sử theo thời gian |
| `replay().limit(n, Duration)` | Đồng thời giới hạn số lượng và tuổi | Cửa sổ lịch sử kiểm soát hơn |

**Cẩn thận với `all()` và `limit(Duration)`**: chúng có thể giữ nhiều dữ liệu trong một khoảng thời gian dài hoặc vô hạn nếu nguồn liên tục phát. Dùng `limit(n)` hoặc `limit(n, Duration)` khi cần giới hạn RAM theo số lượng và thời gian. Với biến thể theo thời gian, API kiểm tra tuổi khi có tín hiệu; không hiểu nó như một tác vụ nền liên tục quét dọn đúng từng mili-giây.

Replay cũng phát lại terminal signal cho subscriber đến sau: nếu sink đã complete/error, subscriber mới nhận lịch sử còn giữ rồi terminal signal tương ứng. Sink replay là cache trong **bộ nhớ tiến trình**, không phải event log bền vững; restart ứng dụng sẽ mất lịch sử.

## 9. Emit API: tryEmit và emit khác nhau thế nào?

### 9.1. `tryEmit...`: tự quyết định lỗi

`tryEmitNext`, `tryEmitValue`, `tryEmitEmpty`, `tryEmitError`, `tryEmitComplete` trả về `Sinks.EmitResult`. Đây thường là lựa chọn tốt khi ứng dụng muốn **tự xử lý từng tình huống**.

~~~java
Sinks.Many<String> sink = Sinks.many().replay().limit(10);

Sinks.EmitResult result = sink.tryEmitNext("hello");

if (result == Sinks.EmitResult.OK) {
    // Sink chấp nhận lần emit.
} else {
    // Phải quyết định rõ cách xử lý result.
}
~~~

`OK` có nghĩa lần emit thành công theo trạng thái sink tại thời điểm gọi; **không phải bằng chứng mọi subscriber đã xử lý xong giá trị**. Việc phát và việc subscriber tiêu thụ là hai bước bất đồng bộ. Cũng không dùng `currentSubscriberCount()` như một kiểm tra chắc chắn trước emit: đây chỉ là snapshot best-effort, subscriber có thể thay đổi ngay sau đó.

### 9.2. Các EmitResult thường gặp

| Kết quả | Ý nghĩa | Hành động nên cân nhắc |
| --- | --- | --- |
| `OK` | Emit thành công | Ghi metric thành công nếu cần; không đồng nghĩa downstream đã xử lý xong |
| `FAIL_NON_SERIALIZED` | Có truy cập emit chồng lấn, không serialize | Serialize producer, đưa event vào queue đơn luồng hoặc retry có giới hạn |
| `FAIL_OVERFLOW` | Buffer không còn capacity/demand phù hợp | Backpressure, drop, retry sau khi có capacity hoặc báo lỗi |
| `FAIL_ZERO_SUBSCRIBER` | Không có subscriber và sink không có chỗ buffer | Chấp nhận drop, lưu event hoặc chờ subscriber tùy domain |
| `FAIL_CANCELLED` | Sink đã bị consumer hủy/ngắt | Dừng producer hoặc kết thúc lifecycle theo chính sách |
| `FAIL_TERMINATED` | Sink đã complete hoặc error trước đó | Không phát tiếp; xem lại vòng đời hoặc tạo sink mới |

Một số result phụ thuộc loại sink. Ví dụ `unicast` có thể buffer trước subscriber; `multicast().directBestEffort()` không buffer; `replay()` giữ history. Không viết một handler tổng quát giả định mọi sink luôn trả mọi loại result.

### 9.3. `emit...`: cung cấp FailureHandler

`emitNext(value, handler)` là cách tiện lợi gọi `tryEmitNext` và để `EmitFailureHandler` quyết định có retry hay không. `Sinks.EmitFailureHandler.FAIL_FAST` không retry. `busyLooping(Duration)` thử lại trong thời gian hữu hạn khi gặp contention `FAIL_NON_SERIALIZED`.

~~~java
sink.emitNext(
    value,
    Sinks.EmitFailureHandler.busyLooping(Duration.ofMillis(200))
);
~~~

**Lưu ý bắt buộc với `busyLooping`:**
- Handler này có thể **busy-loop trên thread producer** tới deadline; nó không phải queue không chặn.
- Tạo một handler **riêng cho mỗi lần emit**; không cache/reuse instance.
- Tài liệu Reactor khuyến nghị timeout lớn hơn khoảng 100ms; giá trị quá nhỏ thường không có ích.
- Chỉ dùng khi contention ngắn và caller có thể chịu chi phí retry; không đặt trên Netty event-loop hoặc thread nhạy latency.
- Không xử lý `FAIL_OVERFLOW`, `FAIL_TERMINATED` như thể chúng là `FAIL_NON_SERIALIZED`; chúng có nguyên nhân khác và retry mù thường không giải quyết được.

Với hệ thống nhiều producer liên tục, cách tốt hơn thường là **serialize đầu vào** qua queue/actor hoặc một consumer phát tuần tự, thay vì để nhiều thread tranh nhau emit và spin.

## 10. Thread safety: an toàn không có nghĩa mọi emit đồng thời đều thành công

Các Sink mặc định của Reactor là **thread-safe theo nghĩa phát hiện truy cập đồng thời và tránh vi phạm Reactive Streams**. Nếu hai thread cố phát đồng thời, một lần có thể thất bại với `FAIL_NON_SERIALIZED`; sink không tự biến mọi producer thành một hàng đợi vô hạn. Đây là cải tiến so với Processor cũ mà caller phải tự đồng bộ để tránh hành vi không xác định.

Ví dụ producer đồng thời:

~~~java
Sinks.Many<Integer> sink = Sinks.many().replay().all();

// Thread A:
Sinks.EmitResult a = sink.tryEmitNext(1);

// Thread B, nếu đụng đúng lúc A đang emit:
Sinks.EmitResult b = sink.tryEmitNext(2);
~~~

Không nên dự đoán `b` luôn là `FAIL_NON_SERIALIZED` vì hai thao tác có thể không thật sự chồng nhau; kết quả phụ thuộc thời điểm. Nếu `b` nhận result này, hãy quyết định retry/serialize thay vì bỏ qua.

### 10.1. Cách quản lý nhiều producer

- **Một producer:** gọi `tryEmit...` và xử lý result.
- **Nhiều producer nhưng cần thứ tự:** chuyển các message qua một queue hoặc dispatcher đơn luồng, rồi chỉ một consumer emit vào sink.
- **Nhiều producer, contention ngắn:** có thể dùng `emit...` với handler có giới hạn, hiểu chi phí blocking/busy-loop.
- **Nhiều producer và throughput cao:** thiết kế partition/actor/single-writer theo key hoặc dùng broker phù hợp; đừng biến `Sinks` thành hệ thống phân phối message không giới hạn.

### 10.2. Vì sao không nên dùng `Sinks.unsafe()`?

`Sinks.unsafe()` tạo biến thể không phát hiện/synchronize concurrent access. Nó có ít overhead hơn nhưng **caller phải đảm bảo external synchronization** để tuân thủ Reactive Streams. Chỉ dùng trong operator/framework nội bộ khi đã chứng minh luồng gọi được serialize. Ứng dụng Spring thông thường nên dùng safe sink mặc định; đừng chọn unsafe chỉ vì benchmark một phép emit nhỏ.

## 11. Terminal signal và vòng đời sink

Một Sink chỉ được terminate một lần:
- `tryEmitComplete()` hoặc `tryEmitEmpty()` kết thúc thành công.
- `tryEmitError(error)` kết thúc bằng lỗi.
- Với `Sinks.One`, `tryEmitValue(value)` vừa phát giá trị vừa complete.
- Sau terminal, các lần emit dữ liệu tiếp theo thường trả `FAIL_TERMINATED`; giá trị/error mới không được nối vào cùng một luồng.

**Ai gọi complete/error?** Thành phần sở hữu vòng đời sink nên là nơi quyết định khi nào luồng dừng: service shutdown, job hoàn tất, listener bị unregister hoặc nguồn ngoài báo lỗi. Nếu không có chủ sở hữu rõ ràng, sink có thể sống mãi, giữ subscriber, queue hoặc lịch sử trong heap.

Đối với sink cấp ứng dụng:
1. Tạo sink ở component có lifecycle rõ (ví dụ singleton service).
2. Expose `asFlux()`/`asMono()` thay vì cho mọi caller sửa cấu trúc nội bộ.
3. Chỉ expose phương thức `publish`, `complete`, `fail` theo hợp đồng nghiệp vụ.
4. Khi shutdown, ngừng nhận producer mới, emit terminal signal và cleanup listener/timer.
5. Theo dõi subscriber count, buffer/overflow, emit failure và tuổi của sink.
6. Nếu cần restart hoặc replay qua nhiều instance, dùng persistence/message broker thay cho state in-memory.

**Không dùng một Sink singleton cho mọi request nếu mỗi request cần nguồn độc lập.** Điều đó sẽ trộn subscriber, dữ liệu và lifecycle của nhiều người dùng vào cùng một kênh.

## 12. Chương trình Java 17+ chạy được

Ví dụ sau minh họa `Sinks.One`, `Sinks.Empty`, unicast, multicast và replay. Nó dùng Reactor Core 3.8.8 và Maven. Chương trình CLI gọi `block()` **chỉ ở điểm cuối để thu kết quả và in stdout**; không sao chép cách này vào controller WebFlux.

### 12.1. Cấu trúc thư mục

~~~text
reactor-sinks-demo/
├── pom.xml
├── src/main/java/com/example/sinks/SinksDemo.java
└── src/test/java/com/example/sinks/SinksDemoTest.java
~~~

### 12.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
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
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <version>3.8.8</version>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
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
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 12.3. Chương trình `SinksDemo.java`

**src/main/java/com/example/sinks/SinksDemo.java**

~~~java
package com.example.sinks;

import java.util.ArrayList;
import java.util.List;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.publisher.Sinks;

public final class SinksDemo {
    private SinksDemo() {}

    private static void requireOk(Sinks.EmitResult result) {
        if (result != Sinks.EmitResult.OK) {
            throw new IllegalStateException("Emit failed: " + result);
        }
    }

    public static void main(String[] args) {
        // One: một kết quả được replay cho subscriber đến muộn.
        Sinks.One<String> one = Sinks.one();
        Mono<String> oneView = one.asMono();
        requireOk(one.tryEmitValue("ready"));
        System.out.println("one=" + oneView.block());
        System.out.println("oneLate=" + oneView.block());

        // Empty: chỉ hoàn tất, không có onNext.
        Sinks.Empty<Void> empty = Sinks.empty();
        Mono<Void> completion = empty.asMono();
        requireOk(empty.tryEmitEmpty());
        completion.block();
        System.out.println("empty=complete");

        // Unicast: giữ phần tử trước subscriber đầu tiên.
        Sinks.Many<Integer> unicast = Sinks.many()
            .unicast()
            .onBackpressureBuffer();
        requireOk(unicast.tryEmitNext(1));
        requireOk(unicast.tryEmitNext(2));
        requireOk(unicast.tryEmitComplete());
        List<Integer> queued = unicast.asFlux().collectList().block();
        System.out.println("unicast=" + queued);

        // Multicast: cả hai subscriber đăng ký trước khi phát.
        Sinks.Many<Integer> multicast = Sinks.many()
            .multicast()
            .onBackpressureBuffer(8, false);
        List<Integer> first = new ArrayList<>();
        List<Integer> second = new ArrayList<>();
        Flux<Integer> live = multicast.asFlux();
        live.subscribe(first::add);
        live.subscribe(second::add);

        requireOk(multicast.tryEmitNext(10));
        requireOk(multicast.tryEmitNext(20));
        requireOk(multicast.tryEmitComplete());
        System.out.println("multicastA=" + first);
        System.out.println("multicastB=" + second);

        // Replay: subscriber đến muộn chỉ nhận hai phần tử cuối.
        Sinks.Many<Integer> replay = Sinks.many()
            .replay()
            .limit(2);
        requireOk(replay.tryEmitNext(1));
        requireOk(replay.tryEmitNext(2));
        requireOk(replay.tryEmitNext(3));
        requireOk(replay.tryEmitComplete());
        List<Integer> history = replay.asFlux().collectList().block();
        System.out.println("replayLate=" + history);

        System.out.println("afterComplete=" + replay.tryEmitNext(4));
    }
}
~~~

### 12.4. Chạy và stdout

Trong thư mục chứa `pom.xml`, cần JDK 17+ và Maven:

~~~bash
java -version
mvn -version
mvn test
mvn -q exec:java -Dexec.mainClass=com.example.sinks.SinksDemo
~~~

**Stdout từ các dòng `System.out.println` trong main** (không tính log Maven):

~~~text
one=ready
oneLate=ready
empty=complete
unicast=[1, 2]
multicastA=[10, 20]
multicastB=[10, 20]
replayLate=[2, 3]
afterComplete=FAIL_TERMINATED
~~~

Kết quả giải thích:
- `Sinks.One` lưu kết quả và subscriber đến sau vẫn nhận `"ready"`.
- `Sinks.Empty` complete mà không phát phần tử.
- Unicast buffer `1,2` trước subscriber đầu tiên.
- Hai multicast subscriber đã đăng ký trước khi phát nên cả hai nhận `10,20`.
- Replay giới hạn hai phần tử, nên subscriber đến sau nhận `2,3`.
- Sau khi replay sink complete, emit `4` trả `FAIL_TERMINATED`.

Đây là ví dụ nhỏ để hiểu semantics; trong production phải quyết định buffer size, subscriber lifecycle và cách xử lý mọi `EmitResult`.

## 13. Kiểm thử bằng StepVerifier

Không chỉ test danh sách giá trị; nên kiểm tra **hành vi subscriber đến muộn, giới hạn số subscriber, terminal signal và EmitResult**.

**src/test/java/com/example/sinks/SinksDemoTest.java**

~~~java
package com.example.sinks;

import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Sinks;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class SinksDemoTest {

    @Test
    void oneReplaysItsSingleValueToLateSubscribers() {
        Sinks.One<String> sink = Sinks.one();
        Flux<String> notUsed = Flux.empty();

        assertEquals(Sinks.EmitResult.OK, sink.tryEmitValue("done"));

        StepVerifier.create(sink.asMono())
            .expectNext("done")
            .verifyComplete();

        StepVerifier.create(sink.asMono())
            .expectNext("done")
            .verifyComplete();

        assertEquals(Sinks.EmitResult.FAIL_TERMINATED,
            sink.tryEmitValue("late"));
    }

    @Test
    void oneCanCompleteEmpty() {
        Sinks.One<String> sink = Sinks.one();
        assertEquals(Sinks.EmitResult.OK, sink.tryEmitEmpty());

        StepVerifier.create(sink.asMono())
            .verifyComplete();
    }

    @Test
    void unicastBuffersBeforeFirstSubscriber() {
        Sinks.Many<Integer> sink = Sinks.many()
            .unicast()
            .onBackpressureBuffer();

        assertEquals(Sinks.EmitResult.OK, sink.tryEmitNext(1));
        assertEquals(Sinks.EmitResult.OK, sink.tryEmitNext(2));
        assertEquals(Sinks.EmitResult.OK, sink.tryEmitComplete());

        StepVerifier.create(sink.asFlux())
            .expectNext(1, 2)
            .verifyComplete();

        StepVerifier.create(sink.asFlux())
            .expectError(IllegalStateException.class)
            .verify();
    }

    @Test
    void replayLimitKeepsOnlyRecentValuesForLateSubscriber() {
        Sinks.Many<Integer> sink = Sinks.many().replay().limit(2);
        sink.tryEmitNext(1);
        sink.tryEmitNext(2);
        sink.tryEmitNext(3);
        sink.tryEmitComplete();

        StepVerifier.create(sink.asFlux())
            .expectNext(2, 3)
            .verifyComplete();
    }

    @Test
    void multicastLateSubscriberReceivesOnlyNewSignals() {
        Sinks.Many<Integer> sink = Sinks.many()
            .multicast()
            .onBackpressureBuffer(8, false);

        List<Integer> early = new ArrayList<>();
        List<Integer> late = new ArrayList<>();
        Flux<Integer> view = sink.asFlux();

        view.subscribe(early::add);
        assertEquals(Sinks.EmitResult.OK, sink.tryEmitNext(1));

        view.subscribe(late::add);
        assertEquals(Sinks.EmitResult.OK, sink.tryEmitNext(2));
        assertEquals(Sinks.EmitResult.OK, sink.tryEmitComplete());

        assertEquals(List.of(1, 2), early);
        assertEquals(List.of(2), late);
    }

    @Test
    void emissionAfterTerminationReturnsFailure() {
        Sinks.Many<Integer> sink = Sinks.many().replay().all();
        assertEquals(Sinks.EmitResult.OK, sink.tryEmitNext(1));
        assertEquals(Sinks.EmitResult.OK, sink.tryEmitComplete());

        assertEquals(Sinks.EmitResult.FAIL_TERMINATED,
            sink.tryEmitNext(2));
    }
}
~~~

Test trên dùng `StepVerifier` để xác nhận signal và assertion JUnit để kiểm tra kết quả emit. Trong code thật, cần thêm test cho overflow với buffer hữu hạn, subscriber chậm, autoCancel, direct variants và race producer nếu đó là những đường hoạt động của hệ thống. Không viết test cạnh tranh đòi một thread cố định thắng; race phải kiểm tra invariant và xử lý tất cả result có thể xảy ra.

## 14. Tích hợp Spring WebFlux: event hub và SSE

Một ứng dụng có thể dùng `Sinks.Many` làm event hub **trong một tiến trình**. Service expose Flux cho controller, producer gọi `tryEmitNext`. Ví dụ chọn `directBestEffort()` cho cập nhật tạm thời: subscriber chậm có thể mất sự kiện riêng; không buffer và không replay.

### 14.1. EventHub

~~~java
package com.example.web;

import java.util.concurrent.atomic.AtomicLong;

import org.springframework.stereotype.Component;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Sinks;

@Component
public class EventHub {
    public record AppEvent(long id, String type, String message) {}

    private final AtomicLong ids = new AtomicLong();
    private final Sinks.Many<AppEvent> sink =
        Sinks.many().multicast().directBestEffort();

    public Flux<AppEvent> events() {
        return sink.asFlux();
    }

    public void publish(String type, String message) {
        AppEvent event = new AppEvent(
            ids.incrementAndGet(), type, message);

        Sinks.EmitResult result = sink.tryEmitNext(event);

        switch (result) {
            case OK -> { }
            case FAIL_ZERO_SUBSCRIBER, FAIL_OVERFLOW -> {
                // Với event tạm thời, không có người nhận/consumer chậm
                // có thể là tình huống chấp nhận được.
            }
            default -> throw new IllegalStateException(
                "Cannot publish event: " + result);
        }
    }

    public void close() {
        Sinks.EmitResult result = sink.tryEmitComplete();
        if (result != Sinks.EmitResult.OK &&
                result != Sinks.EmitResult.FAIL_TERMINATED) {
            throw new IllegalStateException(
                "Cannot close event hub: " + result);
        }
    }
}
~~~

Đây là class có thể tích hợp vào Spring Boot WebFlux với component scanning. `close()` cần được gọi bởi lifecycle owner khi ứng dụng shutdown; nếu event hub là singleton, không đóng sau mỗi HTTP request. Nếu có nhiều producer, cần serialize lời gọi `publish` hoặc xử lý `FAIL_NON_SERIALIZED` đúng cách; ví dụ cố ý surface lỗi thay vì lặng lẽ bỏ.

**Chính sách `directBestEffort`:**
- Client không có demand có thể bị bỏ qua một event.
- Nếu một số subscriber có demand, họ vẫn nhận event; subscriber chậm bị bỏ lỡ event đó.
- Nếu không subscriber nào có thể nhận, emit trả failure phù hợp.
- Sink không giữ history để phục vụ reconnect.

### 14.2. Controller SSE

~~~java
package com.example.web;

import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;

@RestController
public class EventController {
    private final EventHub hub;

    public EventController(EventHub hub) {
        this.hub = hub;
    }

    @GetMapping(path = "/api/events",
                produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<EventHub.AppEvent>> events() {
        return hub.events().map(event ->
            ServerSentEvent.<EventHub.AppEvent>builder()
                .id(Long.toString(event.id()))
                .event(event.type())
                .data(event)
                .build());
    }
}
~~~

Controller trả `Flux<ServerSentEvent<...>>`; WebFlux quản lý subscription và stream response. Khi client disconnect, subscription của response có thể bị hủy, nhưng điều đó không tự hủy cả event hub dùng chung. Các subscriber khác vẫn có thể tiếp tục nhận dữ liệu. Không gọi `subscribe()` thủ công trong controller.

**Nếu không được mất event:** đổi chính sách sang replay giới hạn hoặc dùng queue/broker/persistence có acknowledgement, event ID và replay khi reconnect. `Sinks.Many.replay().limit(n)` chỉ giữ lịch sử trong bộ nhớ một tiến trình; nó không thay Kafka, RabbitMQ hay transactional outbox và không chia sẻ lịch sử giữa nhiều instance.

## 15. Chọn loại Sink theo bài toán

| Nhu cầu | Gợi ý | Điều cần quyết định |
| --- | --- | --- |
| Một callback trả một kết quả cho nhiều consumer | `Sinks.one()` | Timeout, complete/error và ai sở hữu promise |
| Chỉ cần báo hoàn tất hoặc lỗi | `Sinks.empty()` | Khi nào terminal signal được phát |
| Một worker nhận một luồng command | `many().unicast().onBackpressureBuffer(queue)` | Queue hữu hạn, subscriber duy nhất |
| Broadcast sự kiện mới cho nhiều client, có buffer | `many().multicast().onBackpressureBuffer(size, autoCancel)` | Slowest subscriber, overflow, autoCancel |
| Broadcast tạm thời, bỏ event cho client chậm | `many().multicast().directBestEffort()` | Mất sự kiện có chấp nhận được không |
| Tất cả subscriber phải cùng thấy hoặc cùng bỏ | `many().multicast().directAllOrNothing()` | Một subscriber chậm ảnh hưởng cả nhóm |
| Subscriber đến muộn cần một số sự kiện gần nhất | `many().replay().limit(n)` | Kích thước history và retention |
| Subscriber chỉ cần trạng thái mới nhất | `many().replay().latest()` | Giá trị cũ bị bỏ |
| Producer là callback riêng theo mỗi subscriber | `Flux.create` / `Mono.create` | Cleanup và cancellation của từng subscription |
| Nhiều instance, cần bền và phân phối | Message broker / database outbox | Delivery semantics, ack, partition, replay |

**Câu hỏi quyết định đầu tiên:** sự kiện có được phép mất không? Nếu có, direct variant có thể hợp lý. Nếu không, cần buffer giới hạn hoặc hệ thống lưu trữ; chỉ dùng replay in-memory không đảm bảo dữ liệu qua restart.

## 16. Các lỗi thường gặp và cách xử lý

| Sai lầm | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| Dùng `Sinks.One` như một Flux nhiều giá trị | Emit thứ hai thất bại sau terminal | Chọn `Sinks.Many` cho nhiều phần tử |
| Dùng `Sinks.Many.unicast` nhưng có nhiều subscriber | Subscriber sau bị từ chối | Chọn multicast hoặc replay |
| Nghĩ multicast replay lại lịch sử cũ | Subscriber đến muộn bỏ lỡ event | Dùng replay sink nếu cần history |
| Dùng replay `.all()` không giới hạn | Heap tăng theo toàn bộ lịch sử | `limit(n)` hoặc `limit(n, Duration)` |
| Bỏ qua `EmitResult` | Mất event/overflow/concurrency mà không biết | Kiểm tra mọi result và đặt chính sách rõ |
| Nghĩ safe sink tự serialize mọi producer | Gặp `FAIL_NON_SERIALIZED` khi emit chồng lấn | Serialize producer hoặc retry có giới hạn |
| Busy-loop vô hạn để emit | CPU bị chiếm và hệ thống nghẽn | Queue/dispatcher đơn luồng hoặc deadline ngắn, hợp lý |
| Dùng `unsafe()` mà không lock | Vi phạm Reactive Streams, signal lỗi | Safe sink mặc định hoặc external synchronization chứng minh được |
| Buffer unicast mặc định không giới hạn | Tăng RAM khi consumer chậm/vắng mặt | Queue hữu hạn, overflow policy và metrics |
| Dùng direct sink cho event không được mất | Subscriber chậm không nhận event | Buffer/replay bền hoặc message broker |
| Gọi complete nhiều lần/emit sau terminal | `FAIL_TERMINATED` hoặc signal bị drop | Một lifecycle owner, terminal đúng một lần |
| Gọi `subscribe()` trong WebFlux controller | Tách công việc khỏi HTTP lifecycle, dễ leak | Trả `Mono`/`Flux` cho framework |
| Dùng sink singleton cho mọi request độc lập | Trộn dữ liệu và subscriber giữa người dùng | Scope sink theo job/session hoặc dùng event bus đúng chủ đích |
| Xem `OK` là subscriber đã xử lý xong | Sai metric và xác nhận giao hàng | Tách accepted, delivered, processed/acknowledged |
| Dùng Sinks thay broker phân tán | Mất event khi process restart, không chia sẻ giữa instance | Broker/outbox/persistence cho độ bền và phân phối |

## 17. Checklist triển khai production

- [ ] Đã chọn đúng `One`, `Empty` hoặc `Many` theo số lượng giá trị.
- [ ] Với `Many`, đã chọn unicast/multicast/replay/direct theo số subscriber và yêu cầu lịch sử.
- [ ] Đã xác định dữ liệu trước subscriber đầu tiên có được buffer hay drop.
- [ ] Buffer có giới hạn và overflow policy; không dựa vào queue vô hạn mặc định.
- [ ] Đã xác định subscriber chậm ảnh hưởng riêng họ hay tất cả subscriber.
- [ ] Mọi `tryEmit...` đều được kiểm tra `EmitResult`.
- [ ] Producer đồng thời được serialize hoặc có xử lý `FAIL_NON_SERIALIZED` rõ.
- [ ] Không dùng `busyLooping` trên event-loop hoặc thread nhạy latency; handler được tạo riêng từng lần.
- [ ] `Sinks.unsafe()` chỉ dùng khi đã có external synchronization được chứng minh.
- [ ] Sink có lifecycle owner và terminal signal chỉ phát một lần.
- [ ] `OK` được hiểu là emit accepted, không phải business processing đã hoàn tất.
- [ ] Test có subscriber trước/sau emit, overflow, terminal, unicast rejection và replay.
- [ ] WebFlux controller trả Flux/Mono, không tự subscribe.
- [ ] Nếu cần durable delivery, replay sau restart hoặc nhiều instance, đã chọn broker/persistence thay vì sink in-memory.

## 18. Bài tập thực hành

**Bài 1 – One hay Many?** Viết một `Sinks.One<String>` và thử emit hai giá trị. Xác nhận lần đầu `OK`, lần thứ hai `FAIL_TERMINATED`; đổi sang `Sinks.Many` và quan sát hai phần tử cùng được phát.

**Bài 2 – Unicast buffer:** Emit ba giá trị trước subscriber đầu tiên, sau đó subscribe. Kiểm tra cả ba giá trị được chuyển tiếp. Thử subscriber thứ hai và xác nhận bị từ chối.

**Bài 3 – Multicast:** Đăng ký subscriber A, emit event 1, đăng ký subscriber B, emit event 2 rồi complete. Kết quả: A thấy 1,2; B chỉ thấy 2. Đổi sang replay limit(10) và quan sát B nhận lại lịch sử theo giới hạn.

**Bài 4 – Direct backpressure:** Dùng `StepVerifier.create(sink.asFlux(), 0)` để tạo subscriber chưa request. So sánh `directAllOrNothing` với `directBestEffort` khi có một subscriber khác đang request; ghi lại `EmitResult` và phần tử mỗi subscriber nhận.

**Bài 5 – Overflow:** Tạo multicast buffer rất nhỏ và một subscriber chậm. Emit nhiều hơn capacity, kiểm tra `FAIL_OVERFLOW`; quyết định có retry, drop, ghi vào broker hay báo lỗi producer.

**Bài 6 – Concurrent producers:** Hai producer phát vào cùng sink bằng latch để tạo contention có kiểm soát. Quan sát `FAIL_NON_SERIALIZED`; sau đó đưa message qua một single-writer queue và so sánh kết quả. Không yêu cầu một thread cụ thể luôn thắng.

**Bài 7 – SSE:** Tạo EventHub với directBestEffort, mở hai client SSE, phát một event và quan sát cả hai. Đóng một client rồi phát tiếp; xác nhận client còn lại tiếp tục nhận. Giải thích tại sao event đã phát trước khi client mới kết nối không được replay.

## 19. Tài liệu tham khảo chính thức

1. Reactor Core 3.8.8 – `Sinks`: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Sinks.html
2. Reactor Core – `Sinks.One`: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Sinks.One.html
3. Reactor Core – `Sinks.Many`: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Sinks.Many.html
4. Reactor Core – `Sinks.EmitResult`: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Sinks.EmitResult.html
5. Reactor Core – `Sinks.EmitFailureHandler`: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Sinks.EmitFailureHandler.html
6. Reactor Core – `Sinks.UnicastSpec`: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Sinks.UnicastSpec.html
7. Reactor Core – `Sinks.MulticastSpec` và `MulticastReplaySpec`: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Sinks.MulticastSpec.html
8. Project Reactor Reference Guide – Sinks và backpressure: https://projectreactor.io/docs/core/release/reference/
9. Spring Framework – WebFlux streaming: https://docs.spring.io/spring-framework/reference/web/webflux.html

**Tự kiểm tra cuối:** Vì sao `Sinks.One` phù hợp cho một callback kết quả nhưng không phù hợp cho event stream? Vì sao `multicast().onBackpressureBuffer()` có thể bị ảnh hưởng bởi subscriber chậm? Khi nào chọn `directBestEffort` thay vì replay? Vì sao `tryEmitNext()` phải được kiểm tra ngay cả khi sink là thread-safe? Nếu giải thích được các điểm đó cùng với test late subscriber và overflow, bạn đã hiểu cách dùng Sinks đúng trong Reactor.
