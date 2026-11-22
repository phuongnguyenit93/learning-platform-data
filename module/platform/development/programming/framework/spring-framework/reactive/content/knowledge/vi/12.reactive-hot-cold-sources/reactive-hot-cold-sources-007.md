# Unicast, multicast và replay theo nhu cầu sử dụng trong Reactor

## 1. Bài toán: một nguồn sự kiện, nhiều cách phân phối

Trong Spring WebFlux và Project Reactor, một nguồn dữ liệu có thể là sự kiện từ cảm biến, callback của thư viện, thông báo nội bộ, cập nhật trạng thái hoặc dữ liệu từ dịch vụ bên ngoài. Khi có một hay nhiều subscriber, cần xác định:

- Có **một subscriber duy nhất** hay cần phát cho **nhiều subscriber**?
- Subscriber đến muộn chỉ nhận sự kiện mới, hay phải nhận lại một phần/toàn bộ lịch sử?
- Nếu subscriber xử lý chậm, producer phải chờ, buffer, báo lỗi hay bỏ sự kiện?
- Dữ liệu có bắt đầu lại cho từng subscriber, hay producer phát độc lập với subscriber?
- Khi không còn subscriber, nguồn có dừng không? Khi nguồn đã hoàn tất, subscriber đến sau sẽ thấy điều gì?

Trong nhóm `Sinks.Many`, ba lựa chọn cốt lõi là:

- **Unicast:** một sink dành cho tối đa một subscriber; dữ liệu có thể được buffer trước khi subscriber đầu tiên đăng ký.
- **Multicast:** một sink phát sự kiện mới tới nhiều subscriber đang tham gia; subscriber đến muộn thường chỉ thấy sự kiện phát sau lúc đăng ký.
- **Replay:** một sink multicast có lưu lịch sử; subscriber đến muộn nhận phần lịch sử được giữ lại rồi tiếp tục nhận sự kiện mới.

**Replay là một chính sách lưu lịch sử của multicast.** Ba khái niệm này liên quan nhưng không thay thế cho nhau. Chọn sai có thể làm subscriber bỏ lỡ sự kiện, giữ bộ nhớ quá lâu hoặc khiến producer bị nghẽn do backpressure.

Sau bài học, bạn có thể giải thích unicast/multicast/replay, phân biệt chúng với cold/hot publisher, chọn `Sinks.Many` phù hợp, quản lý buffer và emission failure, dùng `publish`, `share`, `replay`, `cache`, viết ví dụ Java 17+ và kiểm thử với StepVerifier.

## 2. Hai trục độc lập: cold/hot và unicast/multicast/replay

Trước khi chọn sink, cần tách hai câu hỏi.

**Cold hay hot** nói về mối quan hệ giữa quá trình tạo dữ liệu và subscription:

- **Cold publisher:** mỗi subscriber mới thường kích hoạt một lần thực thi nguồn mới, bắt đầu lại từ đầu. Ví dụ `Flux.range(1, 3)` hoặc `Mono.fromCallable(...)`.
- **Hot publisher:** producer có thể phát dữ liệu độc lập với một subscriber cụ thể. Subscriber đến muộn thường chỉ nhận tín hiệu phát sau khi họ đăng ký, trừ khi nguồn có chính sách replay/cache.

**Unicast, multicast hay replay** nói về cách phân phối dữ liệu của một nguồn tới subscriber:

- **Unicast:** chỉ một subscriber được phép đăng ký.
- **Multicast:** nhiều subscriber cùng nhận sự kiện mới.
- **Replay:** nhiều subscriber nhận sự kiện mới và subscriber đến muộn còn được phát lại lịch sử đã giữ.

Hai trục không đồng nghĩa:

| Nguồn | Cold/hot | Subscriber và lịch sử |
| --- | --- | --- |
| `Flux.range(1, 3)` | Cold | Mỗi subscriber có một lượt phát mới; không chia sẻ lịch sử |
| `Sinks.many().unicast().onBackpressureBuffer()` | Producer sink chủ động, thường được dùng như nguồn hot | Một subscriber; buffer dữ liệu trước subscriber đầu tiên |
| `Sinks.many().multicast().onBackpressureBuffer()` | Hot | Nhiều subscriber; phát sự kiện mới, không replay lịch sử cho subscriber đến sau |
| `Sinks.many().replay().limit(10)` | Hot | Nhiều subscriber; replay tối đa 10 phần tử gần nhất |
| `source.cache(10)` | Chia sẻ và cache kết quả của lần subscribe đầu | Subscriber sau có thể nhận lịch sử đã cache |

Một publisher cold có thể được chia sẻ qua `share()` hoặc `publish()`. Một nguồn hot có thể có hoặc không có replay. Do đó không nên dùng từ “hot” như thể nó luôn có nghĩa “multicast có replay”.

## 3. Unicast: một producer sink, một subscriber

### 3.1. Đặc điểm

Tạo một unicast sink:

~~~java
Sinks.Many<Integer> sink =
    Sinks.many().unicast().onBackpressureBuffer();

Flux<Integer> view = sink.asFlux();
~~~

- `Sinks.Many` là đối tượng producer; ứng dụng phát dữ liệu qua `tryEmitNext`, `emitNext`, `tryEmitComplete` hoặc `tryEmitError`.
- `asFlux()` cung cấp góc nhìn Publisher để consumer subscribe.
- Chỉ **một subscriber** được chấp nhận. Subscriber thứ hai vào cùng unicast view bị từ chối và nhận lỗi.
- `onBackpressureBuffer()` giữ các phần tử khi subscriber chưa request đủ.
- Nếu producer phát trước khi subscriber đầu tiên đăng ký, những phần tử ấy được buffer và chuyển cho subscriber đầu tiên khi họ đến.
- Đây là buffer chờ **subscriber duy nhất**, không phải replay cho nhiều subscriber đến muộn.

Ví dụ:

~~~java
Sinks.Many<Integer> sink =
    Sinks.many().unicast().onBackpressureBuffer();

sink.tryEmitNext(10);
sink.tryEmitNext(20);

sink.asFlux().subscribe(System.out::println);

sink.tryEmitNext(30);
sink.tryEmitComplete();
~~~

Output:

~~~text
10
20
30
~~~

Hai phần tử đầu được phát trước khi subscriber tồn tại, nhưng được buffer. Khi subscriber đầu tiên đăng ký, chúng được chuyển xuống; phần tử 30 được phát trực tiếp sau đó.

### 3.2. Backpressure và giới hạn bộ nhớ

Unicast sink tôn trọng demand của subscriber duy nhất. Tuy nhiên, `onBackpressureBuffer()` mặc định có thể dùng queue không giới hạn. Nếu producer phát nhanh hơn consumer trong thời gian dài, queue tăng và có thể gây áp lực bộ nhớ.

Có thể cung cấp một queue riêng qua overload `onBackpressureBuffer(Queue<T>)`. Queue đó phải đáp ứng yêu cầu single-producer/single-consumer của API. Nếu queue có giới hạn và đầy, producer có thể nhận `FAIL_OVERFLOW`. Cần chọn chính sách cụ thể:

- Dùng queue có giới hạn nếu dữ liệu tồn đọng phải được giới hạn.
- Xử lý `FAIL_OVERFLOW` bằng cách từ chối, thử lại có kiểm soát hoặc báo lỗi nghiệp vụ.
- Nếu không thể buffer và muốn subscriber nhận lỗi khi không có demand, xem xét `Sinks.many().unicast().onBackpressureError()`.

Không nên coi buffer là bộ nhớ vô hạn để “chống mất dữ liệu”. Buffer chỉ chuyển vấn đề chậm từ thời điểm hiện tại sang bộ nhớ và thời gian chờ; nếu tốc độ producer luôn cao hơn consumer thì backlog vẫn tăng.

### 3.3. Khi nào dùng unicast?

Phù hợp khi một thành phần tạo dữ liệu và một thành phần duy nhất chịu trách nhiệm tiêu thụ, ví dụ adapter chuyển callback từ thư viện imperative thành một `Flux` cho một consumer, một hàng đợi nội bộ có một worker tiêu thụ, hoặc một phiên xử lý có một subscriber sở hữu luồng.

Không dùng unicast nếu nhiều service cần nhận độc lập cùng một sự kiện. Khi ấy cần multicast hoặc một message broker/queue có semantics phù hợp.

## 4. Multicast: một nguồn phát tới nhiều subscriber

### 4.1. Multicast live-only

Tạo multicast sink:

~~~java
Sinks.Many<String> sink =
    Sinks.many().multicast().onBackpressureBuffer();

Flux<String> events = sink.asFlux();
~~~

Mọi subscriber đang đăng ký đều có thể nhận sự kiện mới. Subscriber đăng ký **sau khi** một sự kiện đã được phát không tự động nhận lại sự kiện cũ.

Ví dụ:

~~~java
Sinks.Many<String> sink =
    Sinks.many().multicast().onBackpressureBuffer();

Flux<String> events = sink.asFlux();

events.subscribe(value -> System.out.println("A: " + value));
sink.tryEmitNext("one");
sink.tryEmitNext("two");

events.subscribe(value -> System.out.println("B: " + value));
sink.tryEmitNext("three");
sink.tryEmitComplete();
~~~

Output:

~~~text
A: one
A: two
A: three
B: three
~~~

Subscriber A đã đăng ký trước khi phát `one` và `two`, nên nhận cả hai. Subscriber B đến sau, nên chỉ nhận `three`.

**Lưu ý warm-up:** một số overload multicast buffer có thể giữ một số phần tử phát **trước subscriber đầu tiên** để khởi động sink. Điều này không biến multicast thành replay cho mọi subscriber đến muộn. Cần phân biệt dữ liệu warm-up trước subscriber đầu tiên với lịch sử đã phát cho subscriber trước đó.

### 4.2. Backpressure của nhiều subscriber

Với `multicast().onBackpressureBuffer(...)`, Reactor điều tiết theo demand của các subscriber. Khi một subscriber chậm hoặc chưa request, subscriber đó có thể khiến nguồn phải giữ dữ liệu trong buffer. Nếu chênh lệch demand vượt sức chứa buffer, `tryEmitNext` có thể trả `FAIL_OVERFLOW`; nếu dùng `emitNext` với failure handler, hành vi lỗi sẽ phụ thuộc handler đã chọn.

Overload cho phép cấu hình buffer và `autoCancel`:

~~~java
Sinks.Many<Event> sink =
    Sinks.many().multicast().onBackpressureBuffer(
        256,
        true
    );
~~~

Đây là snippet: `Event` là kiểu dữ liệu của ứng dụng. Tham số 256 là giới hạn buffer; `true` bật `autoCancel`. Theo mặc định, khi tất cả subscriber hủy, multicast sink sẽ tự hủy trạng thái hoạt động, xóa buffer và ngừng nhận subscriber mới. Có thể điều chỉnh hành vi này bằng tham số `autoCancel` khi có lý do vòng đời rõ ràng.

### 4.3. Hai chế độ multicast không buffer

Reactor có hai chế độ direct để lựa chọn cách xử lý subscriber chậm:

| Sink | Khi một subscriber không có demand | Các subscriber khác |
| --- | --- | --- |
| `directAllOrNothing()` | Sự kiện hiện tại bị bỏ đối với tất cả nếu có ít nhất một subscriber không sẵn sàng | Không ai nhận sự kiện đó |
| `directBestEffort()` | Chỉ subscriber chậm bị bỏ sự kiện hiện tại | Subscriber có demand vẫn nhận |

Cả hai chế độ direct đều không replay lịch sử và không buffer theo cách của `onBackpressureBuffer`. Subscriber chậm không bị terminate chỉ vì bỏ lỡ sự kiện; khi họ request lại, họ tiếp tục nhận những sự kiện mới.

Dùng `directBestEffort()` cho thông báo cập nhật trạng thái mà subscriber có thể tự lấy snapshot mới, ví dụ vị trí hiện tại hoặc số liệu dashboard. Dùng `directAllOrNothing()` khi mọi subscriber cần quan sát cùng một tập sự kiện và một subscriber không sẵn sàng thì không phát sự kiện cho bất kỳ ai. Với dữ liệu giao dịch hoặc audit cần đảm bảo xử lý, việc drop có thể không phù hợp; cần một cơ chế lưu trữ/queue đáng tin cậy.

### 4.4. Khi nào dùng multicast?

- Broadcast trạng thái cho nhiều màn hình hoặc WebSocket session đang hoạt động.
- Gửi cập nhật nội bộ tới nhiều thành phần cùng quan tâm sự kiện mới.
- Fan-out dữ liệu mà subscriber đến sau không cần lịch sử.
- Một producer phát cùng sự kiện cho nhiều consumer trong cùng tiến trình.

Nếu subscriber phải có thể offline một thời gian rồi đọc lại mọi sự kiện đã bỏ lỡ, multicast live-only không đáp ứng yêu cầu; dùng replay giới hạn hoặc message broker có retention/offset.

## 5. Replay: multicast có lưu lịch sử cho subscriber đến muộn

### 5.1. Replay theo số phần tử

Tạo replay sink:

~~~java
Sinks.Many<Integer> sink =
    Sinks.many().replay().limit(3);

Flux<Integer> events = sink.asFlux();
~~~

`limit(3)` giữ tối đa ba phần tử gần nhất. Subscriber mới nhận các phần tử lịch sử còn trong giới hạn rồi tiếp tục nhận sự kiện mới.

Ví dụ:

~~~java
Sinks.Many<Integer> sink =
    Sinks.many().replay().limit(3);

Flux<Integer> events = sink.asFlux();

sink.tryEmitNext(1);
sink.tryEmitNext(2);
sink.tryEmitNext(3);
sink.tryEmitNext(4);

events.subscribe(value -> System.out.println("late: " + value));

sink.tryEmitNext(5);
sink.tryEmitComplete();
~~~

Output:

~~~text
late: 2
late: 3
late: 4
late: 5
~~~

Khi subscriber đăng ký, lịch sử đang được giữ là `[2, 3, 4]`; sau đó sự kiện 5 được phát trực tiếp. Replay không tạo lại source từ đầu; nó gửi những phần tử sink đã lưu.

### 5.2. Các cấu hình replay

| Cấu hình | Lịch sử được giữ | Phù hợp với |
| --- | --- | --- |
| `replay().all()` | Toàn bộ phần tử đã phát | Luồng hữu hạn, lịch sử nhỏ và có giới hạn rõ |
| `replay().limit(n)` | Tối đa n phần tử gần nhất | Snapshot/event gần đây, giới hạn bộ nhớ theo số lượng |
| `replay().limit(Duration)` | Phần tử còn trong cửa sổ tuổi tối đa | Sự kiện chỉ có giá trị trong một khoảng thời gian |
| `replay().limit(n, Duration)` | Đồng thời giới hạn số lượng và tuổi | Kiểm soát cả bộ nhớ và độ cũ của dữ liệu |
| `replay().latest()` | Giá trị mới nhất | Trạng thái hiện tại, khi subscriber chỉ cần snapshot mới nhất |
| `replay().latestOrDefault(value)` | Giá trị mới nhất hoặc giá trị mặc định ban đầu | Subscriber cần luôn có một giá trị khởi tạo |

`replay().all()` có thể giữ toàn bộ lịch sử trong bộ nhớ; với nguồn vô hạn, điều này có nguy cơ làm bộ nhớ tăng không giới hạn. Ưu tiên `limit(n)` hoặc giới hạn theo thời gian nếu yêu cầu nghiệp vụ không cần toàn bộ lịch sử.

Với replay theo thời gian, Reactor kiểm tra tuổi phần tử khi có tín hiệu; không nên hiểu nó như một tác vụ nền chạy chính xác vào từng mili giây để xóa mọi phần tử ngay khi hết hạn. Nếu yêu cầu retention/audit nghiêm ngặt, hãy dùng kho lưu trữ có retention policy rõ ràng.

### 5.3. Replay không đồng nghĩa event store bền vững

Replay sink giữ lịch sử trong bộ nhớ của tiến trình. Khi ứng dụng restart, dữ liệu đã giữ không tự khôi phục từ đĩa. Nó cũng không cung cấp offset/checkpoint bền vững như Kafka hoặc một hệ thống event log.

Dùng replay cho subscriber đến muộn trong cùng vòng đời ứng dụng, cache ngắn hạn hoặc snapshot gần đây. Nếu yêu cầu là khôi phục sau restart, xử lý lại từ offset, audit hoặc bảo đảm không mất sự kiện, cần một nguồn lưu trữ bền vững.

## 6. So sánh unicast, multicast và replay

| Tiêu chí | Unicast | Multicast | Replay |
| --- | --- | --- | --- |
| Số subscriber | Tối đa 1 | Nhiều | Nhiều |
| Subscriber đến muộn | Subscriber đầu tiên nhận dữ liệu đã buffer trước đó | Chỉ nhận sự kiện mới sau khi đăng ký, ngoài warm-up trước subscriber đầu tiên | Nhận lịch sử còn được giữ rồi nhận sự kiện mới |
| Buffer/lịch sử | Queue cho một subscriber | Buffer phục vụ demand của các subscriber hiện tại | Lịch sử replay có giới hạn hoặc không giới hạn |
| Backpressure | Theo demand của subscriber duy nhất | Demand của nhiều subscriber; subscriber chậm có thể ảnh hưởng buffer | Mỗi subscriber đọc lịch sử/live theo demand riêng |
| Nguy cơ chính | Một consumer duy nhất; queue tăng | Subscriber chậm làm buffer đầy hoặc dữ liệu bị drop trong direct modes | Giữ lịch sử quá lớn, replay dữ liệu cũ |
| Use case | Một consumer sở hữu stream | Broadcast live | Broadcast có lịch sử cho subscriber mới |

Hãy chọn dựa trên **hợp đồng phân phối dữ liệu**, không dựa trên tên operator quen thuộc. Một câu hỏi hữu ích là: “Nếu subscriber đến muộn 10 giây, nó phải nhận những gì?” Câu trả lời thường xác định được live-only hay replay.

## 7. Các operator chia sẻ publisher khác

Không phải lúc nào cũng cần tạo sink thủ công. Nếu đã có một `Flux` nguồn, Reactor có operator chia sẻ/chờ kết nối/cache.

### 7.1. publish và ConnectableFlux

`publish()` tạo một `ConnectableFlux`. Các subscriber có thể đăng ký trước, rồi ứng dụng gọi `connect()` để bắt đầu subscribe vào source:

~~~java
ConnectableFlux<Integer> shared =
    Flux.range(1, 3).publish();

shared.subscribe(value -> System.out.println("A " + value));
shared.subscribe(value -> System.out.println("B " + value));

shared.connect();
~~~

Hai subscriber được tập hợp trước khi nguồn bắt đầu, nên cả hai nhận các phần tử của nguồn. `connect()` trả một `Disposable` có thể dùng để ngắt kết nối.

Các biến thể thường dùng:

- `publish().autoConnect(n)`: tự kết nối khi có đủ n subscriber; sau khi kết nối, nguồn không tự ngắt chỉ vì subscriber giảm.
- `publish().refCount(n)`: tự kết nối khi có đủ n subscriber và theo dõi hủy; khi số subscriber xuống dưới ngưỡng, nguồn có thể bị disconnect.
- `publish().refCount(n, gracePeriod)`: thêm thời gian chờ trước khi disconnect để subscriber mới có cơ hội tham gia.

`publish()` điều phối demand của các subscriber đang tham gia và có thể tạm dừng request lên nguồn khi một subscriber không có demand.

### 7.2. share

`share()` là lựa chọn gọn để chia sẻ một nguồn cho các subscriber đồng thời:

~~~java
Flux<Event> live = eventSource.share();
~~~

Nhiều subscriber đang cùng tham gia có thể chia sẻ một lượt subscribe upstream. Subscriber đến muộn không nhận lại lịch sử đã phát; họ nhận những sự kiện từ thời điểm tham gia. `share()` không phải replay/cache.

Vì `share()` có semantics kết nối theo subscriber, cần hiểu vòng đời khi tất cả subscriber hủy và khi nguồn complete/error. Nếu cần điều khiển rõ số subscriber và grace period, dùng `publish().refCount(...)`.

### 7.3. replay và cache

Nếu muốn lưu lịch sử của một `Flux` có sẵn:

~~~java
Flux<Event> recent = eventSource.replay(100).autoConnect(1);
~~~

Đây là một `ConnectableFlux` replay tối đa 100 phần tử; `autoConnect(1)` bắt đầu nguồn khi subscriber đầu tiên đăng ký.

Nếu muốn cache tự động khi subscriber đầu tiên đến:

~~~java
Flux<Event> cached = eventSource.cache(100);
~~~

Các lựa chọn `cache()` có thể giữ toàn bộ tín hiệu; `cache(n)` giới hạn số phần tử, `cache(Duration)` giới hạn thời gian, và `cache(n, Duration)` kết hợp cả hai. Cache thay đổi vòng đời của nguồn: các subscriber sau có thể nhận kết quả đã cache thay vì kích hoạt một lần thực thi upstream mới.

**Chú ý:** không cache publisher chứa dữ liệu cá nhân/request-specific hoặc kết quả thay đổi theo quyền của từng người dùng nếu cache dùng chung mà không có khóa phân vùng/lifecycle thích hợp. Chia sẻ một kết quả giữa nhiều subscriber có thể làm lộ dữ liệu hoặc trả snapshot cũ.

### 7.4. Khi nào dùng Sinks thay cho operator?

- Dùng `Sinks.Many` khi **ứng dụng cần chủ động phát sự kiện** từ callback, listener hoặc một nguồn imperative.
- Dùng `share`, `publish`, `replay`, `cache` khi đã có một publisher và chỉ cần thay đổi cách subscribe/chia sẻ/lưu lịch sử của publisher ấy.
- Dùng broker/event log khi cần retention bền vững, consumer độc lập, replay sau restart hoặc giao tiếp qua nhiều tiến trình.

Không tạo `Sinks.Many` chỉ để chia sẻ một `Flux.range` vốn có thể dùng `share()` hoặc `publish()`.

## 8. Phát dữ liệu an toàn: tryEmitNext và emitNext

`Sinks` được thiết kế để thay thế việc gọi trực tiếp `onNext` trên các Processor cũ. Những sink mặc định phát hiện các thao tác phát đồng thời không được serialize để tránh vi phạm Reactive Streams.

Có hai nhóm API:

- `tryEmitNext(value)`, `tryEmitComplete()`, `tryEmitError(error)`: trả về `Sinks.EmitResult`, cho phép caller kiểm tra việc phát thành công hay thất bại.
- `emitNext(value, failureHandler)`, `emitComplete(failureHandler)`, `emitError(error, ...)`: dùng một `EmitFailureHandler` để quyết định cách xử lý một số trường hợp thất bại.

Ví dụ:

~~~java
Sinks.EmitResult result = sink.tryEmitNext(event);

if (result != Sinks.EmitResult.OK) {
    // Chọn chính sách cụ thể: retry có giới hạn,
    // ghi log/metric, từ chối hoặc chuyển sang error.
}
~~~

Không bỏ qua kết quả `tryEmitNext`. Một lần phát có thể thất bại vì sink đã terminal, đã bị cancel, buffer đầy, không có subscriber phù hợp hoặc có emission đồng thời chưa serialize. Xử lý tùy loại sink và kết quả trả về.

`emitNext(value, Sinks.EmitFailureHandler.FAIL_FAST)` là cách phát có failure handler fail-fast; khi thất bại, nó có thể ném exception theo contract. `EmitFailureHandler.busyLooping(timeout)` có thể thử lại trong thời gian giới hạn khi gặp contention, nhưng không nên dùng như giải pháp chung cho producer quá tải. Nếu producer liên tục vượt khả năng consumer, retry spin chỉ tiêu tốn CPU.

### 8.1. Nhiều producer thread

Ví dụ có hai thread cùng gọi `tryEmitNext` tại một thời điểm. Sink mặc định phát hiện tín hiệu concurrent không serialize và có thể trả `FAIL_NON_SERIALIZED`. Điều đó có nghĩa producer phải quyết định cách serialize/queue các lần phát; không được giả định sink tự biến mọi lời gọi đồng thời thành một hàng đợi vô hạn.

Các cách xử lý:

1. Đưa event vào một queue có giới hạn và dùng một producer/dispatcher phát tuần tự vào sink.
2. Dùng `emitNext` với failure handler retry có giới hạn nếu contention ngắn và có thể chấp nhận.
3. Nếu thứ tự nghiệp vụ quan trọng, gắn sequence number hoặc serialize từ tầng nguồn trước khi emit.
4. Chỉ cân nhắc `Sinks.unsafe()` khi ứng dụng tự bảo đảm mọi tín hiệu được serialize đúng đặc tả. Không expose unsafe sink ra API công khai nếu caller không thể bảo đảm điều đó.

Thread-safe ở đây có nghĩa sink phát hiện/xử lý tranh chấp theo contract; không có nghĩa mọi producer đồng thời luôn được chấp nhận, mọi event luôn thành công hoặc thứ tự nghiệp vụ tự được bảo toàn.

## 9. Backpressure và subscriber chậm: cần chọn chính sách

Giả sử producer phát 1.000 sự kiện/giây, subscriber A xử lý 1.000 sự kiện/giây, subscriber B chỉ xử lý 100 sự kiện/giây. Với multicast có buffer, phần tử chờ của B có thể làm buffer tăng cho tới giới hạn. Có bốn quyết định phổ biến:

| Chính sách | Hành vi | Khi phù hợp |
| --- | --- | --- |
| Buffer | Giữ sự kiện chờ demand | Tốc độ chậm chỉ tạm thời và có giới hạn backlog |
| Fail/overflow | Báo thất bại khi buffer đầy | Mất dữ liệu không chấp nhận được; producer phải xử lý áp lực |
| Drop slow subscriber | Bỏ sự kiện ở subscriber không có demand | Subscriber có thể tự lấy snapshot mới |
| Drop all | Nếu có subscriber chậm thì không phát sự kiện đó cho ai | Cần mọi subscriber cùng nhìn thấy cùng một tập sự kiện |

Trong Reactor multicast:

- `onBackpressureBuffer` dùng buffer và có thể overflow.
- `directBestEffort` chỉ drop đối với subscriber chậm.
- `directAllOrNothing` drop cho tất cả nếu bất kỳ subscriber nào không có demand.

**Không có lựa chọn đúng cho mọi nghiệp vụ.** Với event audit, lệnh thanh toán hoặc sự kiện cần xử lý đúng một lần theo contract, không nên chọn drop chỉ để hệ thống “không bị nghẽn”. Với dashboard hiển thị trạng thái mới nhất, drop các trạng thái trung gian có thể chấp nhận được.

Backpressure không tự động điều chỉnh tốc độ của một callback bên ngoài nếu callback cứ phát dữ liệu bất chấp demand. Khi đó cần queue có giới hạn, rate limit, drop policy, hoặc một giao thức upstream hỗ trợ demand.

## 10. Chương trình Java 17+ chạy được: so sánh ba loại sink

Ví dụ dưới đây dùng Reactor Core 3.8.6. Nó phát dữ liệu theo thứ tự đồng bộ để output dễ kiểm chứng.

Tạo `build.gradle`:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'io.projectreactor:reactor-core:3.8.6'
}

application {
    mainClass = 'BroadcastModesDemo'
}
~~~

Tạo `src/main/java/BroadcastModesDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.List;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Sinks;

public final class BroadcastModesDemo {
    private static void emit(Sinks.Many<Integer> sink, int value) {
        Sinks.EmitResult result = sink.tryEmitNext(value);
        if (result != Sinks.EmitResult.OK) {
            throw new IllegalStateException("emit failed: " + result);
        }
    }

    private static void complete(Sinks.Many<Integer> sink) {
        Sinks.EmitResult result = sink.tryEmitComplete();
        if (result != Sinks.EmitResult.OK) {
            throw new IllegalStateException("complete failed: " + result);
        }
    }

    public static void main(String[] args) {
        // 1. UNICAST: buffer trước subscriber đầu tiên, chỉ một subscriber.
        Sinks.Many<Integer> unicast =
            Sinks.many().unicast().onBackpressureBuffer();
        List<Integer> unicastValues = new ArrayList<>();

        emit(unicast, 1);
        emit(unicast, 2);
        unicast.asFlux().subscribe(unicastValues::add);
        emit(unicast, 3);
        complete(unicast);

        System.out.println("unicast=" + unicastValues);

        // 2. MULTICAST: subscriber muộn không nhận lịch sử đã phát.
        Sinks.Many<Integer> multicast =
            Sinks.many().multicast().onBackpressureBuffer();
        Flux<Integer> live = multicast.asFlux();

        List<Integer> early = new ArrayList<>();
        List<Integer> late = new ArrayList<>();

        live.subscribe(early::add);
        emit(multicast, 1);
        emit(multicast, 2);

        live.subscribe(late::add);
        emit(multicast, 3);
        complete(multicast);

        System.out.println("multicast early=" + early);
        System.out.println("multicast late=" + late);

        // 3. REPLAY: subscriber muộn nhận lại hai phần tử gần nhất.
        Sinks.Many<Integer> replay =
            Sinks.many().replay().limit(2);
        Flux<Integer> history = replay.asFlux();

        List<Integer> replayEarly = new ArrayList<>();
        List<Integer> replayLate = new ArrayList<>();

        history.subscribe(replayEarly::add);
        emit(replay, 1);
        emit(replay, 2);
        emit(replay, 3);

        history.subscribe(replayLate::add);
        emit(replay, 4);
        complete(replay);

        System.out.println("replay early=" + replayEarly);
        System.out.println("replay late=" + replayLate);
    }
}
~~~

Chạy bằng `gradle run --quiet`, hoặc `./gradlew run --quiet` nếu dự án có Gradle Wrapper.

Stdout:

~~~text
unicast=[1, 2, 3]
multicast early=[1, 2, 3]
multicast late=[3]
replay early=[1, 2, 3, 4]
replay late=[2, 3, 4]
~~~

Giải thích:

1. **Unicast:** 1 và 2 được emit trước khi subscriber xuất hiện; buffer giữ lại cho subscriber duy nhất. Subscriber nhận 1, 2 rồi nhận live event 3.
2. **Multicast:** A đã đăng ký trước event 1 và 2 nên nhận cả ba. B đăng ký sau event 2 nên chỉ nhận event 3.
3. **Replay:** sink giới hạn lịch sử ở hai phần tử. Khi B đến, lịch sử còn 2 và 3; sau đó B nhận live event 4. A đã tham gia từ đầu nên nhận 1, 2, 3, 4.

Ví dụ dùng `subscribe(Consumer)` nên subscriber mặc định request không giới hạn; nó minh họa lịch sử và số lượng subscriber, không phải kiểm thử tình huống subscriber chậm. Mọi lần emit đều kiểm tra `EmitResult`, không bỏ qua lỗi phát.

`block()` không được dùng trong demo này; sink phát đồng bộ và list được cập nhật trực tiếp khi `onNext` chạy.

## 11. Kiểm thử với JUnit 5 và StepVerifier

Có thể kiểm thử semantics mà không mở socket, không dùng thread ngủ và không phụ thuộc timing. Thay khối `dependencies` trong `build.gradle` bằng:

~~~groovy
dependencies {
    implementation 'io.projectreactor:reactor-core:3.8.6'
    testImplementation 'io.projectreactor:reactor-test:3.8.6'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.12.2'
}

test {
    useJUnitPlatform()
}
~~~

Tạo `src/test/java/BroadcastModesTest.java`:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Sinks;
import reactor.test.StepVerifier;

class BroadcastModesTest {
    @Test
    void unicastBuffersUntilItsOnlySubscriberArrives() {
        Sinks.Many<Integer> sink =
            Sinks.many().unicast().onBackpressureBuffer();

        assertEquals(Sinks.EmitResult.OK, sink.tryEmitNext(1));
        assertEquals(Sinks.EmitResult.OK, sink.tryEmitNext(2));
        assertEquals(Sinks.EmitResult.OK, sink.tryEmitComplete());

        StepVerifier.create(sink.asFlux())
            .expectNext(1, 2)
            .verifyComplete();
    }

    @Test
    void multicastLateSubscriberReceivesOnlyNewSignals() {
        Sinks.Many<Integer> sink =
            Sinks.many().multicast().onBackpressureBuffer();

        Flux<Integer> view = sink.asFlux();
        List<Integer> first = new ArrayList<>();
        List<Integer> late = new ArrayList<>();

        view.subscribe(first::add);
        assertEquals(Sinks.EmitResult.OK, sink.tryEmitNext(1));
        assertEquals(Sinks.EmitResult.OK, sink.tryEmitNext(2));

        view.subscribe(late::add);
        assertEquals(Sinks.EmitResult.OK, sink.tryEmitNext(3));
        assertEquals(Sinks.EmitResult.OK, sink.tryEmitComplete());

        assertEquals(List.of(1, 2, 3), first);
        assertEquals(List.of(3), late);
    }

    @Test
    void replaySinkKeepsOnlyConfiguredHistory() {
        Sinks.Many<Integer> sink =
            Sinks.many().replay().limit(2);

        assertEquals(Sinks.EmitResult.OK, sink.tryEmitNext(1));
        assertEquals(Sinks.EmitResult.OK, sink.tryEmitNext(2));
        assertEquals(Sinks.EmitResult.OK, sink.tryEmitNext(3));
        assertEquals(Sinks.EmitResult.OK, sink.tryEmitComplete());

        StepVerifier.create(sink.asFlux())
            .expectNext(2, 3)
            .verifyComplete();
    }
}
~~~

Chạy `gradle test` hoặc `./gradlew test`.

Ba test kiểm tra ba contract khác nhau:

- Unicast giữ phần tử trước subscriber đầu tiên và phát lại cho đúng một subscriber.
- Multicast không gửi lịch sử đã phát cho subscriber đến sau.
- Replay chỉ giữ và phát lại số phần tử lịch sử nằm trong giới hạn.

Test dùng sink đồng bộ và subscriber lambda có demand mặc định; nếu cần kiểm thử subscriber request từng phần hoặc overflow, hãy dùng `StepVerifier.create(publisher, initialRequest)` và điều khiển `thenRequest(n)` để tạo demand rõ ràng.

## 12. Ứng dụng trong Spring WebFlux

### 12.1. Broadcast trạng thái mới nhất cho nhiều client

Giả sử một service nhận callback cập nhật trạng thái từ một thiết bị. Nếu màn hình chỉ cần **giá trị hiện tại**, không nhất thiết cần mọi trạng thái trung gian:

~~~java
@Service
public class DeviceStatusService {
    private final Sinks.Many<DeviceStatus> sink =
        Sinks.many().replay().limit(1);

    public Flux<DeviceStatus> statusStream() {
        return sink.asFlux();
    }

    public Sinks.EmitResult publish(DeviceStatus status) {
        return sink.tryEmitNext(status);
    }
}
~~~

Đây là snippet service; `DeviceStatus` và cách nhận callback do ứng dụng định nghĩa. `replay().limit(1)` cho subscriber mới giá trị trạng thái gần nhất rồi tiếp tục nhận cập nhật. Caller phải kiểm tra kết quả của `publish`; service có thể ghi metric/log hoặc áp dụng policy riêng khi emit thất bại.

### 12.2. Endpoint Server-Sent Events

Controller có thể trả `Flux` trực tiếp:

~~~java
@RestController
class DeviceController {
    private final DeviceStatusService service;

    DeviceController(DeviceStatusService service) {
        this.service = service;
    }

    @GetMapping(
        value = "/devices/status",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE
    )
    Flux<DeviceStatus> status() {
        return service.statusStream();
    }
}
~~~

Đây là snippet WebFlux; cần import `MediaType`, `GetMapping`, `RestController`, `Flux` và định nghĩa service/DTO. Mỗi HTTP subscriber tham gia vào stream theo chính sách sink đã chọn. Khi dùng replay limit 1, client mới nhận snapshot cuối gần nhất trước các cập nhật mới.

**Cần cân nhắc vòng đời:** một sink singleton trong Spring service có thể tồn tại suốt đời application context. Cần quyết định khi nào complete/error, cách giải phóng tài nguyên callback và hành vi khi không còn client. Đừng tạo một sink mới trong mỗi lần gọi controller nếu mục tiêu là chia sẻ cùng một luồng trạng thái.

### 12.3. Khi nào WebSocket/SSE cần replay?

- Dashboard trạng thái: replay 1 hoặc latest có thể đủ.
- Client cần vài cập nhật gần nhất để dựng UI: replay giới hạn theo số lượng hoặc thời gian.
- Chat/event history phải đầy đủ: dùng database/event store; sink replay chỉ là bộ nhớ trong tiến trình.
- Sự kiện có tính giao dịch: dùng hệ thống lưu bền vững, consumer offset và deduplication thay vì dựa vào multicast/drop.

## 13. Vòng đời, kết thúc và hủy

Một sink không chỉ phát `onNext`. Producer còn có thể phát terminal signal:

- `tryEmitComplete()` / `emitComplete(...)`: kết thúc bình thường; không phát thêm phần tử sau đó.
- `tryEmitError(error)` / `emitError(error, ...)`: kết thúc bằng lỗi.
- Subscriber gọi `cancel§/hủy `Disposable`: không còn muốn nhận dữ liệu.
- Với multicast có `autoCancel`, khi mọi subscriber hủy, sink có thể xóa buffer và dừng nhận subscriber mới theo cấu hình.

Một subscriber đến sau khi sink đã terminal có thể nhận terminal signal ngay; replay sink còn có thể phát lịch sử còn giữ trước terminal. Điều này khác với một nguồn đang hoạt động mà subscriber đến muộn chỉ nhận dữ liệu mới.

**Không dùng `complete` để mô phỏng tạm ngừng.** Terminal là kết thúc không thể mở lại sink đó để phát thêm dữ liệu. Nếu cần một phiên mới, tạo một publisher/sink mới theo lifecycle nghiệp vụ.

Khi client HTTP ngắt kết nối, subscriber của endpoint có thể bị cancel. Điều đó không có nghĩa producer singleton phải tự complete toàn bộ sink, vì những client khác có thể vẫn đang nghe. Hãy phân biệt cancellation của một subscriber với shutdown của nguồn dùng chung.

## 14. Các lỗi thường gặp và cách sửa

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Dùng unicast cho nhiều service cùng nghe | Subscriber thứ hai bị từ chối | Dùng multicast hoặc replay |
| Nghĩ multicast tự gửi lại lịch sử cho client mới | Client đến muộn bỏ lỡ các sự kiện trước đó | Dùng replay/cache hoặc tải snapshot riêng |
| Dùng replay `all` cho luồng vô hạn | Lịch sử giữ trong RAM tăng không giới hạn | Dùng `limit(n)`, TTL hoặc kho lưu trữ bền vững |
| Nghĩ buffer unicast trước subscriber là replay nhiều người | Chỉ subscriber duy nhất được nhận queue đó | Phân biệt unicast queue với replay history |
| Bỏ qua `Sinks.EmitResult` | Sự kiện có thể không được phát nhưng ứng dụng không biết | Kiểm tra mọi kết quả emit và có policy cụ thể |
| Dùng `directBestEffort` cho audit cần đủ dữ liệu | Subscriber chậm bị mất event | Dùng durable queue/log và ack/offset |
| Dùng `directAllOrNothing` mà không biết subscriber chậm | Một subscriber không demand có thể làm tất cả bỏ event | Đánh giá semantics toàn nhóm trước khi chọn |
| Buffer multicast không giới hạn hoặc quá lớn | Backlog chiếm RAM và tăng latency | Chọn capacity, overflow policy và metric |
| Cho rằng Sinks tự serialize mọi producer thread | Concurrent emit có thể trả `FAIL_NON_SERIALIZED` | Serialize producer hoặc dùng failure handler có giới hạn |
| Dùng `Sinks.unsafe()` từ nhiều caller | Có thể vi phạm Reactive Streams | Chỉ dùng khi tự bảo đảm serialize |
| Dùng `share()` rồi mong subscriber mới nhận lịch sử | `share` là live sharing, không replay | Dùng `replay()` hoặc `cache()` nếu cần history |
| Dùng `cache()` cho dữ liệu theo user nhưng cache dùng chung | Có thể chia sẻ kết quả sai/nguy cơ lộ dữ liệu | Phân vùng cache theo key/quyền/lifecycle |
| Complete sink khi một client ngắt kết nối | Những client còn lại mất stream | Cancel subscriber riêng, quản lý lifecycle producer độc lập |
| Tạo sink mới trong mỗi controller call | Không còn một nguồn chung để broadcast | Quản lý sink ở service/scope phù hợp |
| Coi replay trong RAM là event store | Restart ứng dụng làm mất lịch sử | Dùng DB/broker có retention và offset |

## 15. Bài tập tự kiểm tra có đáp án

**Câu 1.** Một unicast sink đã phát 1, 2 trước khi có subscriber. Subscriber đầu tiên đến sau đó có nhận hai phần tử này không?

**Đáp án:** Có, nếu dùng `unicast().onBackpressureBuffer()`. Chúng được buffer cho subscriber duy nhất. Subscriber thứ hai không được chấp nhận.

**Câu 2.** Một multicast sink đã phát A và B cho subscriber thứ nhất. Subscriber thứ hai đăng ký sau B. Nó nhận gì?

**Đáp án:** Nó chỉ nhận sự kiện mới sau khi đăng ký, ví dụ C. Multicast live-only không replay A/B đã phát trước đó cho subscriber đến muộn.

**Câu 3.** `replay().limit(2)` đã phát 10, 20, 30. Subscriber mới nhận gì trước khi có sự kiện tiếp theo?

**Đáp án:** 20 và 30. Hai phần tử gần nhất còn trong lịch sử được giữ lại.

**Câu 4.** Replay sink `all` có phù hợp cho một luồng cảm biến chạy nhiều tháng không?

**Đáp án:** Thường không, vì toàn bộ lịch sử có thể giữ trong bộ nhớ. Chọn giới hạn số lượng/thời gian hoặc một event store bền vững.

**Câu 5.** `directBestEffort()` gặp một subscriber không có demand nhưng subscriber khác có demand. Điều gì xảy ra?

**Đáp án:** Subscriber chậm bỏ sự kiện đó; subscriber có demand vẫn nhận. Subscriber chậm không bị terminate chỉ vì lần drop này.

**Câu 6.** `directAllOrNothing()` có một subscriber không demand. Sự kiện hiện tại được phát cho subscriber nhanh không?

**Đáp án:** Không. Sự kiện bị bỏ cho tất cả vì chế độ này yêu cầu mọi subscriber đều có demand.

**Câu 7.** `tryEmitNext` trả về `FAIL_OVERFLOW`. Có nên bỏ qua kết quả vì sink là thread-safe không?

**Đáp án:** Không. Thread-safe không đồng nghĩa mọi lần emit đều thành công. Cần áp dụng policy overflow: backoff có giới hạn, từ chối, log/metric, hoặc chuyển sang một queue có giới hạn.

**Câu 8.** `share()` và `replay(10)` khác nhau ở điểm nào?

**Đáp án:** `share()` chia sẻ tín hiệu live giữa subscriber đang tham gia và không phát lại lịch sử. `replay(10)` giữ tối đa 10 phần tử gần nhất để subscriber đến muộn nhận lại.

**Câu 9.** Một client WebSocket cancel subscription. Có nên gọi `tryEmitComplete()` trên sink singleton không?

**Đáp án:** Không tự động. Cancel chỉ nói client đó không còn nhận; những client khác có thể vẫn đang dùng sink. Chỉ complete khi lifecycle của nguồn thực sự kết thúc.

**Câu 10.** Cần phục hồi đầy đủ sự kiện sau khi ứng dụng restart. Replay sink có đủ không?

**Đáp án:** Không. Replay sink lưu trong bộ nhớ tiến trình. Cần broker/event log/database có retention và cơ chế offset/checkpoint.

## 16. Checklist chọn giải pháp

Trước khi triển khai, trả lời lần lượt:

1. **Số subscriber:** đúng một hay nhiều subscriber độc lập?
2. **Subscriber đến muộn:** chỉ nhận sự kiện mới, nhận N phần tử gần nhất hay nhận toàn bộ lịch sử?
3. **Nguồn:** cold tạo lại cho từng subscriber hay hot producer phát độc lập?
4. **Subscriber chậm:** buffer, fail, drop riêng subscriber hay drop cho cả nhóm?
5. **Giới hạn tài nguyên:** buffer/replay history tối đa bao nhiêu phần tử hoặc bao lâu?
6. **Producer:** một thread hay nhiều thread; có serialize các lần emit không?
7. **Lifecycle:** ai complete/error/cancel sink và khi nào?
8. **Độ bền dữ liệu:** mất dữ liệu khi process restart có chấp nhận được không?
9. **Tính đúng đắn:** có cần event exactly-once, dedupe, ordering hoặc ack không?
10. **Quan sát:** đã đo số subscriber, backlog, overflow, emission failures và tốc độ tiêu thụ chưa?

| Nhu cầu | Lựa chọn ban đầu |
| --- | --- |
| Một consumer; producer có thể emit trước subscriber | `Sinks.many().unicast().onBackpressureBuffer()` |
| Nhiều consumer; chỉ cần live events | `Sinks.many().multicast().onBackpressureBuffer()` |
| Nhiều consumer; drop event cho subscriber chậm | `directBestEffort()` |
| Mọi subscriber phải cùng sẵn sàng mới nhận event | `directAllOrNothing()` |
| Subscriber mới cần N event gần nhất | `Sinks.many().replay().limit(N)` |
| Subscriber mới chỉ cần trạng thái cuối | `Sinks.many().replay().limit(1)` |
| Chia sẻ một publisher cold giữa subscriber đang hoạt động | `share()` hoặc `publish()` |
| Subscriber phải rendezvous trước khi source chạy | `publish()` + `connect()`/`autoConnect(n)` |
| Lưu lịch sử publisher cho subscriber sau | `replay()` hoặc `cache(...)` |
| Cần replay bền vững sau restart | Message broker/event store, không chỉ sink trong RAM |

## 17. Ghi nhớ và tài liệu tham khảo

- **Unicast = một subscriber; Multicast = nhiều subscriber nhận live events; Replay = nhiều subscriber nhận lịch sử đã lưu và sự kiện mới.**
- **Cold/hot là trục khác:** cold thường chạy lại source cho từng subscription; hot producer có thể phát độc lập với subscriber.
- `unicast().onBackpressureBuffer()` giữ dữ liệu trước subscriber đầu tiên nhưng không hỗ trợ nhiều subscriber.
- `multicast().onBackpressureBuffer()` điều tiết demand của subscriber; direct modes có thể drop theo chính sách.
- `replay().limit(n)` giới hạn lịch sử theo số phần tử; `replay().all()` có nguy cơ tăng RAM với nguồn vô hạn.
- Kiểm tra `Sinks.EmitResult`; thread-safe sink vẫn có thể từ chối emission do overflow hoặc concurrent emission.
- Replay sink là bộ nhớ trong tiến trình, không thay thế event store/broker bền vững.

Tài liệu chính thức:

1. [Project Reactor Reference — Sinks](https://projectreactor.io/docs/core/release/reference/coreFeatures/sinks.html): tạo sink, unicast/multicast/replay, phát sự kiện và thread safety.
2. [Project Reactor Reference — Hot Versus Cold](https://projectreactor.io/docs/core/release/reference/advancedFeatures/reactor-hotCold.html): vòng đời nguồn theo subscription.
3. [Project Reactor Reference — Broadcasting with ConnectableFlux](https://projectreactor.io/docs/core/release/reference/advancedFeatures/advanced-broadcast-multiple-subscribers-connectableflux.html): `publish`, `replay`, `connect`, `autoConnect`, `refCount`.
4. [Sinks API 3.8.6](https://javadoc.io/static/io.projectreactor/reactor-core/3.8.6/reactor/core/publisher/Sinks.html): các builder và contract.
5. [Sinks.UnicastSpec API](https://javadoc.io/static/io.projectreactor/reactor-core/3.8.6/reactor/core/publisher/Sinks.UnicastSpec.html): một subscriber, queue và backpressure.
6. [Sinks.MulticastSpec API](https://javadoc.io/static/io.projectreactor/reactor-core/3.8.6/reactor/core/publisher/Sinks.MulticastSpec.html): buffer, autoCancel, directAllOrNothing, directBestEffort.
7. [Sinks.MulticastReplaySpec API](https://javadoc.io/static/io.projectreactor/reactor-core/3.8.6/reactor/core/publisher/Sinks.MulticastReplaySpec.html): all, latest, limit theo số lượng/thời gian.
8. [Spring WebFlux Reference](https://docs.spring.io/spring-framework/reference/web/webflux.html): cách tích hợp publisher trong HTTP reactive stack của Spring.
