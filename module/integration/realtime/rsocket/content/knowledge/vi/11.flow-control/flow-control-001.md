# Điều tiết theo nhu cầu (backpressure) và vấn đề bên nhận chậm

Trong một hệ thống realtime, bên gửi có thể tạo dữ liệu nhanh hơn khả năng xử lý của bên nhận. Nếu cứ tiếp tục đẩy dữ liệu, các phần tử sẽ tích tụ trong hàng đợi, độ trễ tăng dần và bộ nhớ có thể cạn. **Backpressure** là cơ chế để bên tiêu thụ báo cho bên sản xuất biết nó có thể nhận thêm bao nhiêu dữ liệu, từ đó điều tiết tốc độ phát theo nhu cầu thực tế.

RSocket xây dựng flow control ở cấp stream và kết hợp với mô hình Reactive Streams. Trong Java, `Mono` và `Flux` của Reactor cho phép ứng dụng thể hiện demand, xử lý từng phần tử, giới hạn prefetch và hủy luồng. Hiểu rõ cơ chế này giúp thiết kế dịch vụ realtime ổn định khi client chậm, mạng có độ trễ hoặc nguồn sự kiện phát liên tục.

## 1. Vấn đề khi bên nhận xử lý chậm

Giả sử server phát 5.000 sự kiện mỗi giây, trong khi client chỉ xử lý được 500 sự kiện mỗi giây. Nếu server gửi liên tục mà không có cơ chế điều tiết, chênh lệch 4.500 sự kiện mỗi giây sẽ tích tụ ở một hoặc nhiều hàng đợi.

```text
Producer: 5.000 events/s
       |
       v
  Network / queues  ----->  Consumer: 500 events/s
       |
       +-- backlog tăng khoảng 4.500 events/s
```

Hệ quả thường gặp:

- **Tăng bộ nhớ:** các phần tử chưa xử lý nằm trong buffer, queue hoặc object graph đang chờ.
- **Tăng độ trễ:** một sự kiện mới phải chờ các sự kiện cũ được xử lý trước.
- **Cạn tài nguyên:** buffer không giới hạn có thể gây `OutOfMemoryError`; nhiều stream chậm có thể làm cạn thread, connection hoặc pool.
- **Phản hồi dây chuyền:** dịch vụ phía sau chậm khiến queue phía trước tăng, làm các request khác cũng bị trễ.
- **Mất dữ liệu hoặc lỗi:** nếu buffer có giới hạn, hệ thống phải có chính sách khi đầy; nếu không, có thể phát sinh overflow hoặc drop không mong muốn.

Vấn đề không chỉ nằm ở tốc độ mạng. Client có thể nhận bytes nhanh nhưng xử lý JSON, ghi database, gọi API phụ hoặc cập nhật giao diện chậm. Backpressure cần phản ánh khả năng tiêu thụ ở tầng ứng dụng, bên cạnh điều tiết byte của TCP.

## 2. Backpressure trong Reactive Streams

Reactive Streams định nghĩa cách một subscriber báo nhu cầu dữ liệu với publisher. Ba thành phần cốt lõi là:

| Thành phần | Trách nhiệm |
|---|---|
| `Publisher<T>` | Phát các phần tử, hoặc kết thúc bằng hoàn tất/lỗi. Trong Reactor, `Flux<T>` có thể phát nhiều phần tử. |
| `Subscriber<T>` | Nhận tín hiệu `onSubscribe`, `onNext`, `onError` và `onComplete`. |
| `Subscription` | Kết nối subscriber với publisher; cung cấp `request(n)` để cấp demand và `cancel()` để hủy. |

Trình tự cơ bản:

1. Subscriber đăng ký với publisher.
2. Publisher gọi `onSubscribe(subscription)`.
3. Subscriber gọi `request(n)` để cho phép phát tối đa `n` phần tử bổ sung.
4. Publisher phát các phần tử qua `onNext` trong giới hạn demand.
5. Subscriber có thể yêu cầu thêm khi xử lý xong một phần, hoặc hủy bằng `cancel()`.
6. Luồng kết thúc bằng `onComplete()` hoặc `onError(error)`.

```text
Subscriber                         Publisher
    |                                  |
    |---------- subscribe() ---------->|
    |<------ onSubscribe(subscription)-|
    |                                  |
    |---------- request(2) ----------->|
    |<----------- onNext(A) -----------|
    |<----------- onNext(B) -----------|
    |                                  |
    |---------- request(3) ----------->|
    |<----------- onNext(C) -----------|
    |<----------- onNext(D) -----------|
    |<----------- onNext(E) -----------|
```

`request(n)` mang ý nghĩa cấp thêm `n` phần tử, không phải đặt tổng demand thành `n`. Mỗi lần publisher phát một phần tử, một đơn vị demand được tiêu thụ. `request(Long.MAX_VALUE)` biểu thị demand không giới hạn. `request(0)` hoặc số âm không hợp lệ theo Reactive Streams.

Điểm quan trọng là publisher tuân thủ demand của subscriber. Subscriber chậm xử lý có thể tạm thời không yêu cầu thêm; publisher phải chờ demand mới trước khi phát phần tử tiếp theo. Đây là cách backpressure truyền ngược từ consumer về producer.

## 3. RSocket flow control: initial N và REQUEST_N

RSocket đưa demand vào wire protocol để hai peer điều tiết dữ liệu qua TCP hoặc WebSocket. Với request-stream, requester gửi frame `REQUEST_STREAM` chứa **initial request N**, tức số payload ban đầu mà nó sẵn sàng nhận. Khi cần thêm, requester gửi frame `REQUEST_N` để cấp thêm demand.

```text
Requester (Client)                         Responder (Server)
       |                                           |
       | REQUEST_STREAM, streamId=1, initialN=2   |
       |------------------------------------------>|
       |                                           |
       | PAYLOAD, streamId=1                       |
       |<------------------------------------------|
       | PAYLOAD, streamId=1                       |
       |<------------------------------------------|
       |                                           |
       | REQUEST_N, streamId=1, n=3                |
       |------------------------------------------>|
       |                                           |
       | PAYLOAD, streamId=1                       |
       |<------------------------------------------|
```

Các quy tắc chính:

- Initial N trong `REQUEST_STREAM` phải là số dương và đếm số payload response, không đếm byte.
- `REQUEST_N(n)` cấp thêm `n` payload cho stream hiện tại; `n` phải dương.
- Mỗi frame `PAYLOAD` mang cờ `NEXT` tiêu thụ một đơn vị demand.
- Demand được quản lý riêng theo từng stream ID. Một stream không thể dùng demand của stream khác.
- `REQUEST_N` và các `PAYLOAD` liên quan giữ nguyên stream ID của request-stream ban đầu.
- Khi requester không còn cần dữ liệu, nó có thể hủy stream; runtime truyền cancellation bằng frame `CANCEL` khi tương tác còn hoạt động.

RSocket request-response chỉ có tối đa một response nên không cần cấp demand nhiều lần như request-stream. Request-channel có dữ liệu theo hai chiều; mỗi hướng phát cần tuân thủ demand do peer tương ứng cấp. Dù kiểu tương tác khác nhau, nguyên tắc vẫn là không phát payload vượt quá quyền nhận đã được cấp.

## 4. Backpressure theo phần tử và flow control theo byte

Không nên nhầm backpressure của Reactive Streams/RSocket với flow control của TCP:

| Cơ chế | Điều tiết theo | Phạm vi |
|---|---|---|
| Reactive Streams `request(n)` | Số phần tử | Publisher và subscriber trong pipeline ứng dụng. |
| RSocket initial N / `REQUEST_N` | Số payload | Một stream RSocket cụ thể. |
| TCP receive window | Số byte có thể nhận | Kết nối TCP giữa hai endpoint. |
| Congestion control | Tình trạng tắc nghẽn và tốc độ truyền byte | Đường truyền mạng. |

Ví dụ, một payload chứa ảnh 5 MB và một payload chứa chuỗi ngắn đều tiêu thụ một đơn vị demand của RSocket. Vì vậy, demand theo phần tử không giới hạn trực tiếp kích thước byte. Ứng dụng vẫn cần giới hạn kích thước payload, giới hạn số phần tử đang xử lý và quan sát buffer ở các tầng.

TCP có thể giảm tốc độ gửi khi cửa sổ nhận thu hẹp, nhưng điều đó không thay thế backpressure ở tầng ứng dụng. Một client có thể đọc bytes từ socket rất nhanh, đưa chúng vào queue, rồi xử lý chậm ở worker thread. Từ góc nhìn TCP, bytes đã được nhận; từ góc nhìn ứng dụng, backlog vẫn tiếp tục tăng.

## 5. Nhận diện nơi gây nghẽn

Khi một client bị chậm, cần xác định điểm nghẽn nằm ở đâu trước khi chọn chính sách:

| Dấu hiệu | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Demand không tăng hoặc stream tạm dừng | Subscriber đang xử lý chậm hoặc downstream chưa yêu cầu thêm. | Theo dõi `doOnRequest`, thời gian xử lý mỗi phần tử và trạng thái subscriber. |
| Queue tăng liên tục | Producer không backpressure-aware hoặc buffer được cấu hình quá lớn. | Theo dõi queue depth, số phần tử đang chờ và overflow. |
| CPU cao ở client | Mapping, giải mã, tính toán hoặc callback đồng bộ quá nặng. | Profile CPU, đo thời gian `onNext`, kiểm tra operator tốn CPU. |
| Event loop bị chặn | Có thao tác blocking trong pipeline chạy trên event loop. | Kiểm tra thread dump, log cảnh báo blocking và vị trí gọi `block()`/JDBC đồng bộ. |
| Độ trễ tăng dù queue nhỏ | Gọi dịch vụ phụ chậm, lock contention hoặc database chậm. | Đo latency từng bước và trace qua các dịch vụ. |
| Chỉ một stream chậm | Consumer hoặc nguồn của stream đó có vấn đề riêng. | Phân tích demand và metric theo stream, không chỉ theo connection. |

Các tín hiệu hữu ích gồm: số phần tử được yêu cầu, số phần tử phát ra, queue depth, số phần tử bị drop, số lần overflow, thời gian xử lý mỗi phần tử, độ trễ đầu-cuối, số stream đang hoạt động và số lần cancellation. Không cần ghi toàn bộ payload vào log; metadata có thể chứa token hoặc thông tin nhạy cảm.

## 6. Chiến lược xử lý bên nhận chậm

Không có một chính sách duy nhất phù hợp cho mọi loại dữ liệu. Hãy chọn theo yêu cầu về tính đầy đủ, độ mới và độ trễ.

| Chiến lược | Khi phù hợp | Đánh đổi |
|---|---|---|
| Propagate demand | Nguồn có thể dừng/chậm phát theo demand. | Tăng độ trễ của producer nhưng giữ được dữ liệu và giới hạn backlog. |
| Bounded buffer | Cần hấp thụ các đợt tăng tải ngắn. | Khi buffer đầy phải chọn drop, reject hoặc lỗi; buffer lớn làm tăng latency. |
| Drop | Dữ liệu cũ hoặc một số sự kiện có thể bỏ qua. | Có thể mất sự kiện; cần metric hoặc thông báo drop. |
| Keep latest | Chỉ cần trạng thái mới nhất, như giá hiển thị hoặc vị trí hiện tại. | Bỏ qua các trạng thái trung gian. |
| Sample/throttle | Chỉ cần quan sát theo chu kỳ. | Không nhận mọi mẫu. |
| Batch/window | Có thể xử lý nhiều phần tử cùng lúc. | Chờ đủ batch hoặc hết cửa sổ làm tăng độ trễ. |
| Reject/load shed | Hệ thống phải bảo vệ tài nguyên khi quá tải. | Caller cần xử lý từ chối và có thể retry có kiểm soát. |
| Persist and replay | Sự kiện không được mất, cần đọc lại sau gián đoạn. | Cần lưu trữ bền vững, offset, retention và cơ chế xác nhận. |

Ví dụ: màn hình giá realtime thường ưu tiên giá mới nhất; bỏ qua các tick trung gian có thể chấp nhận được. Với giao dịch hoặc audit event, drop có thể không chấp nhận được; nên lưu sự kiện bền vững và cho consumer đọc lại theo offset.

## 7. Các operator backpressure trong Reactor

Reactor cung cấp operator để điều tiết demand hoặc xử lý khi downstream không theo kịp.

### Giới hạn demand upstream bằng limitRate

```java
Flux<Quote> quotes = quoteService.stream("ACME")
    .limitRate(64)
    .map(this::enrichQuote);
```

`limitRate(64)` chia demand thành các đợt nhỏ hơn khi truyền lên upstream. Điều này giúp tránh yêu cầu một lượng lớn phần tử cùng lúc. Giá trị `64` là tham số điều tiết trong pipeline; không nên hiểu rằng mỗi frame wire chắc chắn sẽ là `REQUEST_N(n=64)`, vì runtime và các operator có thể gộp hoặc chia demand.

### Buffer có giới hạn

```java
Flux<Event> buffered = hotEvents.onBackpressureBuffer(
    256,
    dropped -> metrics.incrementOverflow(),
    BufferOverflowStrategy.DROP_OLDEST
);
```

Ví dụ này giữ tối đa 256 phần tử chờ và bỏ phần tử cũ nhất khi buffer đầy. Hãy dùng chính sách này chỉ khi dữ liệu cũ có thể bị thay thế bởi dữ liệu mới. Nếu cần bảo toàn mọi sự kiện, chọn cách lưu trữ bền vững hoặc báo lỗi overflow để caller xử lý.

Các operator `onBackpressureBuffer` thường yêu cầu upstream không giới hạn để hấp thụ dữ liệu vào buffer, do đó chúng có thể làm yếu backpressure truyền ngược tới nguồn. Buffer có giới hạn và overflow strategy là bắt buộc khi dùng với nguồn phát nhanh.

### Drop hoặc giữ giá trị mới nhất

```java
Flux<Event> dropping = hotEvents
    .onBackpressureDrop(event -> metrics.incrementDropped());

Flux<PriceSnapshot> latest = priceSnapshots
    .onBackpressureLatest();
```

`onBackpressureDrop` bỏ phần tử đến khi downstream chưa có demand; callback có thể ghi nhận số lượng bị bỏ. `onBackpressureLatest` giữ lại giá trị mới nhất trong lúc downstream chưa sẵn sàng. Hai operator phù hợp với dữ liệu trạng thái, telemetry hoặc giao diện, khi giá trị mới có thể thay thế giá trị cũ.

### Báo lỗi khi không theo kịp

```java
Flux<Event> guarded = hotEvents.onBackpressureError();
```

Chính sách này biến tình trạng không có demand thành lỗi thay vì tích lũy vô hạn. Nó phù hợp khi hệ thống muốn phát hiện quá tải sớm và yêu cầu caller khởi tạo lại, giảm tải hoặc chuyển sang nguồn lưu trữ.

## 8. Giới hạn concurrency và prefetch

Một pipeline có thể tạo backlog ngay cả khi nguồn và subscriber đều reactive, nếu các operator cho phép quá nhiều tác vụ đồng thời hoặc prefetch quá lớn.

```java
Flux<EnrichedQuote> enriched = quoteService.stream("ACME")
    .flatMap(
        quote -> enrichmentService.enrich(quote),
        8,   // concurrency: tối đa 8 tác vụ đang hoạt động
        16   // prefetch: số phần tử lấy trước cho mỗi inner publisher
    );
```

`flatMap` cho phép xử lý bất đồng bộ song song. Giới hạn `concurrency` giúp kiểm soát số tác vụ đang chạy; `prefetch` giới hạn số phần tử được yêu cầu trước ở mỗi inner publisher. Nếu thứ tự đầu ra phải giống thứ tự đầu vào, cân nhắc `concatMap`, đổi lại các tác vụ được xử lý tuần tự và có thể tăng latency.

`publishOn` cũng có hàng đợi prefetch riêng:

```java
Flux<QuoteView> views = quoteService.stream("ACME")
    .publishOn(Schedulers.parallel(), 32)
    .map(this::calculateView);
```

Scheduler giúp tách công việc downstream khỏi thread phát tín hiệu upstream, nhưng bản thân nó không làm công việc nhanh hơn. Mỗi lần chuyển scheduler có thể thêm queue và độ trễ; cần giới hạn prefetch và đo tải thực tế.

Không chạy JDBC đồng bộ, gọi HTTP blocking hoặc `Thread.sleep()` trên event loop của RSocket. Nếu phải tích hợp thư viện blocking, cô lập phần đó trên scheduler phù hợp như `Schedulers.boundedElastic()` hoặc chuyển sang driver reactive.

## 9. Tích hợp backpressure trong Spring RSocket

Ở phía server, handler request-stream nên trả `Flux<T>` để framework gắn demand của peer với publisher:

```java
@Controller
public class EventController {

    private final EventService eventService;

    public EventController(EventService eventService) {
        this.eventService = eventService;
    }

    @MessageMapping("events.stream")
    public Flux<Event> stream(EventRequest request) {
        return eventService.stream(request.topic())
            .limitRate(64);
    }
}
```

Không gọi `subscribe()` bên trong handler. Nếu tự subscribe, framework không còn kiểm soát đầy đủ demand, lỗi và cancellation theo vòng đời stream của client.

Ở client, requester trả về `Flux`:

```java
Flux<Event> events = requester
    .route("events.stream")
    .data(new EventRequest("prices"))
    .retrieveFlux(Event.class)
    .limitRate(32);
```

Khi subscriber yêu cầu dữ liệu, Reactor truyền demand qua pipeline và RSocket runtime quản lý initial request N/`REQUEST_N`. Nếu downstream chậm, demand mới có thể được cấp chậm lại; responder phải chờ demand trước khi phát thêm payload. Các operator buffer/drop ở client có thể thay đổi lượng demand mà requester truyền lên remote peer, nên cần chọn chính sách có chủ đích.

Với request-channel, cả client và server đều có thể phát dữ liệu. Hãy kiểm soát demand cho từng hướng và giới hạn buffer riêng cho từng nguồn. Đừng giả định backpressure ở chiều server-to-client tự động bảo vệ queue ở chiều client-to-server.

## 10. Ví dụ chọn chính sách theo loại dữ liệu

### Giá thị trường: ưu tiên trạng thái mới nhất

Một bảng giá trên giao diện thường không cần render mọi tick. Nếu client đang bận, giá mới có thể thay thế giá cũ:

```java
Flux<PriceSnapshot> uiPrices = marketFeed
    .onBackpressureLatest()
    .publishOn(Schedulers.parallel(), 1)
    .map(this::toDisplayModel);
```

Prefetch nhỏ giúp hạn chế số phần tử chờ ở ranh giới scheduler; `onBackpressureLatest` giữ trạng thái mới nhất khi downstream không theo kịp. Cần đánh giá lại nếu mỗi tick có ý nghĩa nghiệp vụ riêng.

### Audit event: bảo toàn và đọc lại

Với audit event, drop không phù hợp. Nguồn nên ghi sự kiện vào log bền vững hoặc message store, sau đó consumer đọc theo offset và chỉ xác nhận sau khi xử lý:

```text
Event producer -> durable log -> RSocket stream -> consumer
                                     |
                                     +-> demand chậm: đọc chậm theo offset
                                     +-> reconnect: tiếp tục từ offset đã xác nhận
```

RSocket backpressure điều tiết số payload đang được gửi, nhưng không tự cung cấp tính bền vững, replay hay exactly-once cho nghiệp vụ. Các thuộc tính đó cần được xây dựng ở tầng lưu trữ và giao thức ứng dụng.

## 11. Cancellation và giải phóng tài nguyên

Khi client đóng màn hình hoặc không còn quan tâm tới stream, nó nên hủy subscription. Với `Flux`, có thể giới hạn số phần tử bằng `take` hoặc giữ `Disposable` khi tự subscribe:

```java
Flux<Event> firstHundred = requester
    .route("events.stream")
    .data(new EventRequest("prices"))
    .retrieveFlux(Event.class)
    .take(100);
```

`take(100)` hoàn tất downstream sau tối đa 100 phần tử và hủy upstream. RSocket runtime có thể gửi `CANCEL` để responder dừng việc phát dữ liệu. Phía server nên dùng publisher và API hỗ trợ cancellation, đồng thời giải phóng tài nguyên trong `doFinally` hoặc operator quản lý tài nguyên phù hợp.

Cancellation không phải rollback. Nếu server đã ghi dữ liệu hoặc gọi dịch vụ phụ có side effect, hủy stream không tự động đảo ngược hành động đó. Với thao tác cần tính nhất quán, hãy dùng transaction, idempotency key hoặc quy trình bù trừ phù hợp.

## 12. Kiểm thử và quan sát backpressure

`StepVerifier` cho phép điều khiển demand và xác minh publisher không phát vượt quá lượng phần tử được yêu cầu:

```java
Flux<Integer> source = Flux.range(1, 5);

StepVerifier.create(source, 0)
    .thenRequest(2)
    .expectNext(1, 2)
    .thenRequest(3)
    .expectNext(3, 4, 5)
    .verifyComplete();
```

Đây là kiểm thử ở tầng Reactive Streams. Để xác minh wire flow control, cần kiểm thử tích hợp requester-responder hoặc quan sát frame: initial N trong `REQUEST_STREAM`, các lần `REQUEST_N`, số `PAYLOAD` có `NEXT`, và frame terminal.

Có thể gắn hook để quan sát pipeline:

```java
Flux<Event> observed = eventService.stream()
    .doOnRequest(n -> metrics.recordRequested(n))
    .doOnNext(event -> metrics.recordReceived())
    .doOnError(error -> metrics.recordStreamError())
    .doFinally(signal -> metrics.recordTermination(signal));
```

Theo dõi tối thiểu các metric sau:

- Demand được yêu cầu và số payload đã phát/nhận.
- Queue depth, buffer occupancy và số lần overflow.
- Số phần tử bị drop hoặc thay thế bởi giá trị mới nhất.
- Thời gian xử lý mỗi phần tử và độ trễ đầu-cuối.
- Số stream hoạt động, số lần hủy và lỗi theo stream.
- CPU, heap, GC, event-loop utilization và tình trạng các connection pool.

Khi điều tra sự cố, phân tích theo stream ID để xác định stream nào bị chậm. Một connection có thể multiplex nhiều stream với tốc độ tiêu thụ khác nhau; số liệu tổng theo connection có thể che khuất một consumer đang bị nghẽn.

## 13. Những lỗi thường gặp

| Cách làm hoặc giả định sai | Hệ quả | Cách xử lý |
|---|---|---|
| Dùng buffer không giới hạn để tránh mất dữ liệu. | Backlog tăng đến khi cạn heap. | Dùng buffer có giới hạn và chính sách overflow rõ ràng; nếu cần bảo toàn dữ liệu, lưu bền vững. |
| Nghĩ `REQUEST_N(n)` là số byte. | Điều tiết sai lượng dữ liệu. | Demand RSocket đếm payload; giới hạn thêm kích thước payload ở tầng ứng dụng. |
| Nghĩ TCP flow control thay thế backpressure. | Bytes có thể đã được đưa vào queue ứng dụng dù TCP đã nhận thành công. | Điều tiết theo demand ở tầng Reactive Streams/RSocket và giám sát queue ứng dụng. |
| Dùng drop cho giao dịch hoặc audit event. | Mất dữ liệu nghiệp vụ. | Dùng durable log, offset, replay và xác nhận sau xử lý. |
| Dùng `onBackpressureLatest` cho sự kiện cần đầy đủ lịch sử. | Chỉ còn trạng thái mới nhất, mất các chuyển đổi trung gian. | Chọn chính sách theo semantics của dữ liệu. |
| Đặt prefetch/concurrency quá lớn. | Queue và số tác vụ đồng thời tăng, gây áp lực lên heap hoặc dịch vụ phụ. | Giới hạn `flatMap` concurrency, prefetch và scheduler queue. |
| Block event loop. | Nhiều stream trên cùng event loop bị chậm. | Giữ pipeline non-blocking hoặc cô lập API blocking trên scheduler phù hợp. |
| Tự subscribe trong handler. | Mất kiểm soát demand, lỗi và cancellation của framework. | Trả `Flux`/`Mono` cho Spring quản lý. |
| Không đo overflow và dropped count. | Sự cố mất dữ liệu bị phát hiện muộn. | Xuất metric, cảnh báo và log nguyên nhân overflow. |

## 14. Quy trình chẩn đoán bên nhận chậm

Khi stream RSocket tăng latency hoặc tiêu thụ bộ nhớ bất thường, hãy kiểm tra theo thứ tự:

1. Xác định stream ID và kiểu tương tác (`REQUEST_STREAM` hay `REQUEST_CHANNEL`).
2. Đọc initial N và các frame `REQUEST_N`; xác định requester có đang cấp demand hay không.
3. Đếm `PAYLOAD` có `NEXT` để biết demand đang được tiêu thụ ra sao.
4. Đo thời gian xử lý mỗi phần tử ở subscriber và các bước downstream.
5. Kiểm tra queue do `publishOn`, `flatMap`, buffer và nguồn hot tạo ra; xác định giới hạn và overflow strategy.
6. Kiểm tra thread dump để tìm blocking trên event loop hoặc scheduler dùng chung.
7. Xem xét chính sách dữ liệu: có thể drop, giữ latest, batch, reject hay phải persist/replay?
8. Xác minh cancellation được truyền đến publisher phía server và tài nguyên được giải phóng.

Một stream không phát thêm payload chưa chắc là lỗi transport. Nếu demand đã về `0`, responder cần chờ `REQUEST_N` mới. Ngược lại, nếu demand vẫn còn nhưng không có payload, hãy kiểm tra nguồn dữ liệu, xử lý nghiệp vụ, queue và kết nối.

## Kết luận

Backpressure giúp producer điều chỉnh lượng dữ liệu theo khả năng tiêu thụ của receiver. Reactive Streams thể hiện nhu cầu bằng `Subscription.request(n)`; RSocket truyền demand của stream qua initial N và `REQUEST_N`, trong khi TCP điều tiết byte ở tầng vận chuyển. Khi receiver chậm, hãy xác định nơi backlog hình thành rồi chọn chính sách phù hợp: truyền demand ngược, buffer có giới hạn, drop/keep latest, batch, reject hoặc persist/replay. Với Spring RSocket, trả `Flux` từ handler, kiểm soát concurrency/prefetch, tránh blocking event loop và xử lý cancellation. Cách thiết kế này giúp hệ thống realtime giữ được giới hạn tài nguyên và độ trễ có thể dự đoán khi tải thay đổi.
