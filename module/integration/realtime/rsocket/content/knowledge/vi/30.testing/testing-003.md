# Điều khiển nhu cầu nhận và hủy trong kiểm thử backpressure

Backpressure giúp một subscriber kiểm soát tốc độ publisher phát dữ liệu. Trong RSocket, cơ chế này đặc biệt quan trọng với Request-Stream và Request-Channel, nơi một tương tác có thể phát nhiều payload trong thời gian dài. Kiểm thử chỉ xác nhận “có nhận được dữ liệu” chưa đủ: cần kiểm tra publisher chỉ phát theo demand, cancellation đi ngược về nguồn và các operator buffer/prefetch không làm thay đổi hành vi ngoài dự kiến.

Trong module `INTEGRATION_REALTIME_RSOCKET`, Spring handler thường trả `Flux<T>` và client nhận bằng `RSocketRequester.retrieveFlux(...)`. Reactor Test cung cấp `StepVerifier` để điều khiển số phần tử được yêu cầu, cùng `TestPublisher` để chủ động phát dữ liệu và xác minh nguồn đã nhận request hoặc cancellation. Bài viết này hướng dẫn kiểm thử ở cả cấp publisher và qua RSocket transport, đồng thời chỉ ra các giới hạn cần lưu ý để test không phụ thuộc chi tiết triển khai nội bộ.

## 1. Demand trong Reactive Streams

Reactive Streams dùng `Subscription.request(n)` để subscriber yêu cầu publisher phát tối đa `n` phần tử bổ sung. Demand là số lượng tích lũy chưa được đáp ứng; publisher không được phát `onNext` vượt quá demand hiện có.

```text
Subscriber                         Publisher
    |                                  |
    |------ subscribe ---------------->|
    |<----- onSubscribe(subscription) -|
    |                                  |
    |------ request(2) --------------->|
    |<----- onNext(item-1) ------------|
    |<----- onNext(item-2) ------------|
    |                                  |
    |------ request(1) --------------->|
    |<----- onNext(item-3) ------------|
    |                                  |
    |------ cancel() ---------------->|
    |                                  |
```

Các quy tắc quan trọng:

- `request(n)` yêu cầu thêm `n` phần tử; `n` phải lớn hơn 0.
- Demand chưa dùng được cộng dồn qua nhiều lần `request`.
- Publisher có thể phát ít hơn demand nếu chưa có dữ liệu hoặc đã kết thúc.
- Publisher không được phát nhiều hơn demand.
- `cancel()` yêu cầu publisher dừng việc phát dữ liệu cho subscription đó.
- Cancellation không phải `onComplete` hoặc `onError`; subscriber không nhận terminal signal chỉ vì đã cancel.

Ví dụ, subscriber gọi `request(2)` rồi nhận hai phần tử. Nếu gọi thêm `request(3)`, publisher có thể phát tối đa ba phần tử nữa. Không được diễn giải `request(3)` là tổng demand của subscription chỉ còn ba.

## 2. Vì sao cần kiểm soát demand trong test?

Nếu test dùng subscriber mặc định yêu cầu vô hạn, publisher có thể phát toàn bộ dữ liệu ngay lập tức. Test khi đó không phát hiện được các lỗi như:

- Publisher phát nhanh hơn demand.
- Operator vô tình yêu cầu upstream vô hạn rồi giữ dữ liệu trong buffer.
- Subscriber hủy nhưng nguồn database/listener vẫn tiếp tục chạy.
- Stream có thể tích lũy quá nhiều phần tử khi consumer chậm.
- Request-Channel không tôn trọng demand độc lập ở hai hướng.
- Một operator `publishOn`, `flatMap` hoặc `onBackpressureBuffer` tạo prefetch vượt quá mức test dự kiến.

Một test backpressure có ý nghĩa thường phải điều khiển demand ban đầu, yêu cầu một lượng nhỏ, kiểm tra phần tử nhận được, sau đó hủy subscription và xác minh nguồn đã được cleanup.

## 3. StepVerifier: subscriber do test điều khiển

`StepVerifier` cho phép viết kỳ vọng theo thứ tự tín hiệu Reactive Streams. Với `StepVerifier.create(publisher)`, demand ban đầu mặc định là không giới hạn. Muốn kiểm tra backpressure, hãy dùng overload có `initialRequest`, thường đặt bằng `0` để test tự cấp demand bằng `thenRequest(n)`.

```java
Flux<Integer> numbers = Flux.range(1, 10);

StepVerifier.create(numbers, 0)
    .expectSubscription()
    .thenRequest(2)
    .expectNext(1, 2)
    .thenRequest(1)
    .expectNext(3)
    .thenCancel()
    .verify(Duration.ofSeconds(3));
```

Test bắt đầu với demand bằng 0, yêu cầu hai phần tử, rồi yêu cầu thêm một phần tử. Cuối cùng, subscriber hủy stream. `verify(Duration)` đặt giới hạn thời gian để test không treo vô hạn nếu publisher không phát tín hiệu như dự kiến.

### 3.1. Kiểm tra publisher không phát trước khi có demand

`expectNoEvent(Duration)` xác nhận không có tín hiệu trong khoảng thời gian chỉ định. Sau `expectSubscription()`, có thể dùng nó để kiểm tra publisher chưa phát `onNext` khi demand vẫn bằng 0:

```java
StepVerifier.create(Flux.range(1, 5), 0)
    .expectSubscription()
    .expectNoEvent(Duration.ofMillis(100))
    .thenRequest(1)
    .expectNext(1)
    .thenCancel()
    .verify(Duration.ofSeconds(3));
```

`expectNoEvent` cũng xem các tín hiệu khác như `onComplete` là event. Dùng khoảng chờ vừa đủ để test ổn định; không dùng sleep dài để thay thế đồng bộ hóa. Với publisher bất đồng bộ, nên dùng tín hiệu readiness hoặc test fixture điều khiển được thay vì dựa vào thời gian ngẫu nhiên.

### 3.2. Kiểm tra nhiều lần request được cộng dồn

```java
StepVerifier.create(Flux.range(1, 8), 0)
    .expectSubscription()
    .thenRequest(2)
    .expectNext(1, 2)
    .thenRequest(3)
    .expectNext(3, 4, 5)
    .thenCancel()
    .verify(Duration.ofSeconds(3));
```

Sau hai lần request, subscriber đã cho phép nhận tổng cộng năm phần tử. Test kiểm tra publisher không phát các phần tử thứ sáu trở đi trước khi có demand mới.

## 4. Đo demand được chuyển tới upstream

Không chỉ quan sát những gì subscriber nhận, có thể gắn `doOnRequest` vào nguồn để ghi lại demand mà nguồn nhìn thấy.

```java
AtomicLong upstreamDemand = new AtomicLong();
AtomicBoolean cancelled = new AtomicBoolean();

Flux<Integer> source = Flux.range(1, 100)
    .doOnRequest(upstreamDemand::addAndGet)
    .doOnCancel(() -> cancelled.set(true));

StepVerifier.create(source, 0)
    .expectSubscription()
    .thenRequest(2)
    .expectNext(1, 2)
    .then(() -> assertThat(upstreamDemand.get()).isEqualTo(2))
    .thenCancel()
    .verify(Duration.ofSeconds(3));

assertThat(cancelled).isTrue();
```

Ở ví dụ này không có operator trung gian thay đổi demand, vì vậy nguồn nhận đúng request bằng 2. `doOnRequest` quan sát yêu cầu đi qua vị trí được đặt operator; nếu đặt nó ở vị trí khác trong pipeline, số liệu có thể khác.

Đây là cách kiểm tra demand ở ranh giới publisher. Khi có `publishOn`, `flatMap`, `limitRate` hoặc operator backpressure khác, không được mặc định demand upstream bằng đúng số mà subscriber cuối cùng yêu cầu.

## 5. TestPublisher: nguồn dữ liệu do test điều khiển

`TestPublisher` thuộc `reactor-test`, cho phép test chủ động phát phần tử, hoàn tất, phát lỗi và kiểm tra subscription. Nó hữu ích khi nguồn thực tế là database, broker, sensor callback hoặc listener bất đồng bộ.

Ví dụ test demand và cancellation:

```java
TestPublisher<Integer> source = TestPublisher.create();
AtomicLong requested = new AtomicLong();

Flux<Integer> result = source.flux()
    .doOnRequest(requested::addAndGet);

StepVerifier.create(result, 0)
    .expectSubscription()
    .thenRequest(1)
    .then(() -> source.next(42))
    .expectNext(42)
    .thenCancel()
    .verify(Duration.ofSeconds(3));

assertThat(requested.get()).isEqualTo(1);
source.assertCancelled();
```

Trình tự test:

1. Tạo `TestPublisher` và lấy `Flux` từ nguồn.
2. Subscribe với demand ban đầu bằng 0.
3. Yêu cầu một phần tử.
4. Phát giá trị `42` từ test fixture.
5. Xác nhận subscriber nhận đúng giá trị.
6. Hủy subscription.
7. Xác nhận nguồn đã bị cancel.

`TestPublisher.create()` phù hợp để kiểm tra publisher tuân thủ demand. Chỉ dùng chế độ non-compliant của `TestPublisher` khi cố ý kiểm tra cách pipeline phản ứng với nguồn vi phạm Reactive Streams; không dùng nó làm nguồn mặc định cho test backpressure bình thường.

### 5.1. Phân biệt request count và số phần tử đã phát

`requested` ghi tổng số demand đi qua `doOnRequest`; nó không phải số phần tử nguồn đã phát. Một publisher có thể được yêu cầu 10 phần tử nhưng chỉ phát 3 rồi chờ dữ liệu. Ngược lại, một operator có thể yêu cầu upstream vô hạn rồi buffer dữ liệu để phát dần theo demand downstream.

Trong test, hãy xác định rõ đang kiểm tra điều gì:

- Subscriber cuối nhận bao nhiêu phần tử?
- Nguồn upstream được yêu cầu bao nhiêu demand?
- Nguồn đã phát bao nhiêu phần tử?
- Nguồn có nhận cancellation không?
- Pipeline có buffer hoặc drop phần tử theo policy không?

Không dùng một con số duy nhất để đại diện cho tất cả các khái niệm này.

## 6. Xác minh cancellation và cleanup

Khi subscriber hủy stream, cancellation cần truyền ngược qua pipeline tới nguồn có thể hủy. Điều này đặc biệt quan trọng khi nguồn đang giữ database cursor, broker consumer, file handle hoặc listener.

```java
TestPublisher<Event> source = TestPublisher.create();
AtomicBoolean cleanupCalled = new AtomicBoolean();

Flux<Event> stream = source.flux()
    .doOnCancel(() -> cleanupCalled.set(true));

StepVerifier.create(stream, 1)
    .expectSubscription()
    .then(() -> source.next(new Event("event-1")))
    .expectNextMatches(event -> event.id().equals("event-1"))
    .thenCancel()
    .verify(Duration.ofSeconds(3));

assertThat(cleanupCalled).isTrue();
source.assertCancelled();
```

`doOnCancel` phù hợp để quan sát cancellation hoặc kích hoạt thao tác cleanup ngắn. Nếu việc giải phóng tài nguyên là bất đồng bộ, hãy dùng resource operator phù hợp như `usingWhen` để gắn cleanup vào lifecycle và xử lý cả complete, error lẫn cancel.

Không dùng `doOnComplete` làm cleanup duy nhất: cancellation không phát `onComplete`. `doFinally` có thể quan sát cả `ON_COMPLETE`, `ON_ERROR` và `CANCEL`, nhưng callback vẫn nên ngắn và không blocking.

### 6.1. Cancellation không phải rollback nghiệp vụ

Cancel dừng việc nhận thêm tín hiệu qua subscription và yêu cầu nguồn dừng công việc nếu có thể. Nó không tự hoàn tác side effect đã commit. Nếu handler đã ghi dữ liệu hoặc gửi lệnh tới thiết bị trước khi nhận cancel, ứng dụng cần idempotency, transaction hoặc quy trình bù trừ riêng.

Test cancellation nên kiểm tra:

- Subscriber không nhận thêm `onNext` sau khi cancel.
- Nguồn upstream nhận cancellation.
- Database cursor/listener/broker subscription được đóng.
- Tác vụ đang chạy có dừng hoặc kết thúc theo chính sách.
- Side effect đã commit không bị giả định là rollback.

## 7. Operator có thể thay đổi demand

Demand mà nguồn nhìn thấy có thể khác demand của subscriber cuối do operator trung gian. Đây là nguyên nhân phổ biến khiến test backpressure bị viết sai.

| Operator | Tác động cần kiểm tra |
|---|---|
| `publishOn(scheduler, prefetch)` | Yêu cầu trước một lượng phần tử để đưa qua queue của scheduler. |
| `flatMap(mapper, concurrency, prefetch)` | Có thể subscribe nhiều inner publisher và prefetch dữ liệu từ từng nhánh. |
| `concatMap(mapper, prefetch)` | Xử lý tuần tự nhưng vẫn có thể prefetch phần tử đầu vào. |
| `limitRate(highTide, lowTide)` | Chia demand thành các đợt request hữu hạn tới upstream. |
| `onBackpressureBuffer(...)` | Thường yêu cầu upstream không giới hạn rồi buffer khi downstream chưa có demand. |
| `onBackpressureDrop()` | Có thể yêu cầu upstream không giới hạn và loại phần tử khi downstream không theo kịp. |
| `onBackpressureLatest()` | Giữ giá trị mới nhất thay vì giữ mọi phần tử đang chờ. |

Ví dụ `publishOn` với prefetch:

```java
Flux<Integer> pipeline = Flux.range(1, 100)
    .doOnRequest(n -> log.debug("source requested={}", n))
    .publishOn(Schedulers.parallel(), 8);

StepVerifier.create(pipeline, 0)
    .expectSubscription()
    .thenRequest(1)
    .expectNext(1)
    .thenCancel()
    .verify(Duration.ofSeconds(3));
```

Subscriber cuối chỉ yêu cầu một phần tử, nhưng `publishOn` có thể yêu cầu trước một batch từ nguồn để lấp queue. Test không nên khẳng định nguồn chỉ nhận `request(1)` nếu pipeline có prefetch.

### 7.1. Kiểm tra limitRate

`limitRate` chia demand upstream thành các batch có giới hạn. Nó hữu ích khi muốn hạn chế lượng prefetch của một nguồn nhanh:

```java
Flux<Integer> limited = Flux.range(1, 100)
    .doOnRequest(n -> metrics.recordUpstreamRequest(n))
    .limitRate(16);

StepVerifier.create(limited, 0)
    .expectSubscription()
    .thenRequest(1)
    .expectNext(1)
    .thenCancel()
    .verify(Duration.ofSeconds(3));
```

Hãy kiểm tra hành vi giới hạn theo phiên bản Reactor và cấu hình high-tide/low-tide được dùng. `limitRate` không có nghĩa nguồn chỉ nhận đúng một request cho mỗi phần tử downstream; nó quản lý demand theo batch.

### 7.2. Kiểm tra bounded buffer và overflow policy

Nếu dùng `onBackpressureBuffer(maxSize, ...)`, test cần xác nhận cả giới hạn buffer lẫn hành vi khi đầy. Ví dụ giữ tối đa 16 phần tử và đếm số phần tử bị loại theo overflow strategy:

```java
AtomicInteger dropped = new AtomicInteger();

Flux<Event> buffered = source.flux()
    .onBackpressureBuffer(
        16,
        event -> dropped.incrementAndGet(),
        BufferOverflowStrategy.DROP_OLDEST
    );
```

`onBackpressureBuffer` có thể yêu cầu upstream không giới hạn rồi giữ phần tử trong buffer. Vì vậy, test demand ở subscriber cuối không chứng minh upstream bị giới hạn. Hãy test riêng kích thước buffer, overflow callback, phần tử bị drop và cleanup khi subscriber hủy.

## 8. Kiểm thử Request-Stream qua RSocket

Test ở cấp publisher xác minh semantics Reactor, nhưng chưa kiểm tra route, serialization, RSocket frame hoặc cancellation qua transport. Nên có thêm integration test với server thật trong test context và `RSocketRequester` client.

Ví dụ handler:

```java
@Controller
public class EventController {
    private final EventService eventService;

    public EventController(EventService eventService) {
        this.eventService = eventService;
    }

    @MessageMapping("events.watch")
    public Flux<Event> watch(@Payload WatchRequest request) {
        return eventService.watch(request)
            .doOnRequest(n -> metrics.recordDemand(n))
            .doOnCancel(() -> metrics.recordCancellation());
    }
}
```

Test client:

```java
Flux<Event> remote = requester
    .route("events.watch")
    .data(new WatchRequest())
    .retrieveFlux(Event.class);

StepVerifier.create(remote, 0)
    .expectSubscription()
    .expectNoEvent(Duration.ofMillis(100))
    .thenRequest(2)
    .expectNextCount(2)
    .thenCancel()
    .verify(Duration.ofSeconds(5));
```

Test này kiểm tra subscriber client không nhận payload trước khi test cấp demand, sau đó nhận hai phần tử rồi hủy tương tác. Nó không chứng minh server chỉ tạo đúng hai event hoặc transport không prefetch: RSocket client/server và operator trong handler có thể có buffer/prefetch riêng.

### 8.1. Kiểm tra cancellation phía server

Để xác minh cancellation đi qua RSocket transport, gắn tín hiệu test vào nguồn phía server:

```java
Sinks.One<Void> serverCancelled = Sinks.one();

Flux<Event> source = eventPublisher.flux()
    .doOnCancel(() -> serverCancelled.tryEmitEmpty());
```

Sau khi client đã subscribe và nhận một phần tử, client gọi `cancel()`. Test chờ `serverCancelled.asMono()` hoàn tất để xác nhận server đã nhận cancellation:

```java
StepVerifier.create(remote, 1)
    .expectNextMatches(event -> event.id().equals("event-1"))
    .thenCancel()
    .verify(Duration.ofSeconds(5));

StepVerifier.create(serverCancelled.asMono())
    .verifyComplete();
```

Đây là khung minh họa; test fixture cần bảo đảm `eventPublisher` đã có subscriber trước khi phát `event-1`, và route server đang dùng đúng nguồn này. Có thể thêm một tín hiệu `serverSubscribed` để đồng bộ trước khi phát dữ liệu, tránh race giữa handshake và test producer.

## 9. Request-Channel có hai hướng demand độc lập

Request-Channel vừa nhận luồng command từ client vừa phát luồng update về client. Cần test riêng demand ở hai hướng:

```text
Client command publisher  ----->  Server handler
          demand A                    |
                                      |
Client update subscriber  <-----  Server response publisher
          demand B
```

Ví dụ handler:

```java
@MessageMapping("device.control")
public Flux<DeviceUpdate> control(
        @Payload Flux<DeviceCommand> commands) {
    return commands.concatMap(deviceService::apply);
}
```

Ví dụ client:

```java
Flux<DeviceUpdate> updates = requester
    .route("device.control")
    .data(commands, DeviceCommand.class)
    .retrieveFlux(DeviceUpdate.class);

StepVerifier.create(updates, 0)
    .expectSubscription()
    .thenRequest(1)
    .expectNextMatches(update -> update.sequence() == 1)
    .thenCancel()
    .verify(Duration.ofSeconds(5));
```

`thenRequest(1)` ở đây điều khiển demand của luồng update đầu ra. Publisher `commands` có demand riêng từ phía server. Nếu cần kiểm tra đầu vào, dùng `TestPublisher<DeviceCommand>` và ghi nhận `doOnRequest`/cancellation ở nguồn command. Không suy ra demand đầu vào chỉ từ số update client yêu cầu.

Hoàn tất publisher command đầu vào là half-close theo hợp đồng channel: client ngừng gửi thêm command nhưng vẫn có thể tiếp tục nhận update. Hủy subscription nhận update là hủy toàn bộ tương tác từ phía client. Test cần phân biệt hai hành động này.

## 10. Không kiểm tra chính xác số REQUEST_N frame ở mọi test

RSocket flow control dùng request-N để điều tiết số payload mà peer được phép gửi. Với Request-Stream, initial request amount được mang trong frame mở đầu; các demand bổ sung được truyền qua frame `REQUEST_N`. Request-Channel có demand riêng cho hướng server-to-client và client-to-server.

Tuy nhiên, con số quan sát ở source `doOnRequest` không nhất thiết bằng một frame `REQUEST_N` cụ thể:

- Operator có thể prefetch hoặc chia demand thành batch.
- RSocket implementation có thể quản lý initial demand và buffer nội bộ.
- Serialization, scheduling và transport có thể tạo ranh giới subscription khác nhau.
- `limitRate`, `publishOn`, `flatMap` và buffer operator thay đổi số request upstream.

Vì vậy:

- Unit test nên xác minh demand tại ranh giới publisher mà test sở hữu.
- Integration test nên xác minh không phát vượt demand quan sát ở subscriber, cancellation tới được server và buffer được giới hạn.
- Chỉ kiểm tra frame `REQUEST_N` chính xác khi đang viết protocol-level test cho một implementation/version cụ thể và kiểm soát được mọi operator trung gian.
- Không hardcode một số prefetch nội bộ vào test nghiệp vụ; nâng phiên bản Reactor/RSocket có thể thay đổi batching mà không làm sai contract Reactive Streams.

## 11. Dùng Virtual Time khi nguồn phụ thuộc thời gian

Với publisher dùng timer, `StepVerifier.withVirtualTime(...)` giúp test không phải chờ thời gian thực:

```java
StepVerifier.withVirtualTime(
        () -> Flux.interval(Duration.ofSeconds(1)),
        0
    )
    .expectSubscription()
    .thenRequest(2)
    .thenAwait(Duration.ofSeconds(2))
    .expectNext(0L, 1L)
    .thenCancel()
    .verify(Duration.ofSeconds(3));
```

Virtual time chỉ hoạt động với scheduler được thay thế/điều khiển bởi Reactor Test. Không dùng virtual time để giả lập network socket, RSocket transport hoặc proxy thực. Với integration test qua TCP/WebSocket, dùng thời gian thực có giới hạn và đồng bộ bằng tín hiệu test.

`Flux.interval` có thể phát lỗi nếu tick xảy ra khi không có demand, vì nó không thể tự giữ vô hạn tick. Trong test backpressure, điều này có thể hữu ích để xác minh overflow, nhưng không phải nguồn mặc định tốt để minh họa mọi loại publisher. Dùng `TestPublisher` hoặc nguồn có thể điều tiết nếu muốn chủ động kiểm soát tốc độ phát.

## 12. Kiểm thử overflow và subscriber chậm

Backpressure có thể được giữ xuyên suốt hoặc thay bằng một policy buffer/drop. Hãy kiểm thử đúng policy mà ứng dụng chọn.

| Chính sách | Điều cần xác minh |
|---|---|
| Propagate demand | Upstream chỉ nhận demand theo pipeline; cancellation truyền ngược. |
| Bounded buffer | Buffer không vượt giới hạn; overflow phát lỗi hoặc gọi callback theo cấu hình. |
| Drop | Phần tử bị drop được đếm; subscriber nhận phần tử theo quy tắc đã chọn. |
| Latest | Khi chậm, subscriber nhận giá trị mới nhất theo semantics của operator. |
| Sampling/throttling | Tần suất đầu ra đúng giới hạn; không giữ backlog không cần thiết. |

Ví dụ test buffer overflow nên dùng một nguồn điều khiển được, không dùng `Flux.interval` với timing ngẫu nhiên. Phát nhiều phần tử hơn capacity trong lúc downstream chưa request, rồi xác nhận overflow callback hoặc error đúng theo policy. Khi kiểm tra `DROP_OLDEST`, xác nhận subscriber nhận các phần tử mới hơn theo thứ tự, đồng thời số phần tử drop đúng kỳ vọng.

Đối với command, giao dịch và event kiểm toán, không chọn drop/latest chỉ để test dễ pass. Chính sách phải phù hợp yêu cầu nghiệp vụ; nếu không được mất event, cần queue bền vững hoặc consumer riêng thay vì buffer trong memory.

## 13. Các lỗi thường gặp khi viết test backpressure

- **Dùng `StepVerifier.create(publisher)` mặc định:** subscriber yêu cầu vô hạn, nên test không điều khiển demand.
- **Gọi `thenCancel()` nhưng không kiểm tra nguồn:** test kết thúc nhưng không chứng minh upstream đã cleanup.
- **Chỉ kiểm tra số phần tử nhận:** không phát hiện buffer hoặc prefetch quá lớn.
- **Đòi upstream request đúng bằng downstream request:** operator trung gian có thể thay đổi demand.
- **Dùng sleep để chờ source subscribe:** dễ race và làm test chậm; dùng readiness signal hoặc test publisher.
- **Dùng nguồn phát nhanh không kiểm soát:** test phụ thuộc scheduler và thời gian chạy máy.
- **Dùng `doOnComplete` để xác nhận cancel:** cancellation không phát `onComplete`.
- **Giả định RSocket CANCEL rollback nghiệp vụ:** cancellation chỉ yêu cầu dừng stream/công việc còn có thể dừng.
- **Kiểm tra frame count trong business test:** gắn test với chi tiết implementation thay vì contract observable.
- **Bỏ qua hai hướng của Request-Channel:** demand đầu vào và đầu ra độc lập.

## 14. Ma trận test khuyến nghị

| Cấp test | Công cụ | Nội dung kiểm tra |
|---|---|---|
| Publisher/unit | `StepVerifier` | Initial demand, `thenRequest`, thứ tự phần tử, no-signal, cancel. |
| Nguồn upstream | `TestPublisher` | Request count, emission có kiểm soát, cancellation và overflow. |
| Operator pipeline | `StepVerifier` + metrics/AtomicLong | Prefetch, `limitRate`, buffer/drop/latest và bounded queue. |
| RSocket integration | Server test + `RSocketRequester` | Route, codec, demand quan sát được, response stream và cancellation qua transport. |
| Request-Channel | TestPublisher ở input + StepVerifier ở output | Demand độc lập hai hướng, half-close và full cancel. |
| Load/stress | Nhiều client/stream đồng thời | Subscriber chậm, buffer occupancy, drop, memory và cleanup. |

Một bộ test tối thiểu cho route realtime nên bao gồm: không phát trước demand ở publisher boundary, cấp demand từng phần, xác nhận đúng số phần tử, cancel sau một số phần tử, xác nhận upstream cleanup và kiểm tra overflow policy nếu pipeline có buffer.

## 15. Quan sát khi test và production

Nên thu thập các metric giúp phát hiện subscriber chậm và nguồn không được hủy:

- Số subscription đang hoạt động theo route.
- Demand/request count tại những boundary quan trọng.
- Số phần tử phát, nhận, buffer và drop.
- Buffer occupancy và số lần overflow.
- Số cancellation, thời gian từ client cancel tới source cleanup.
- Số publisher còn hoạt động sau khi client disconnect.
- Latency xử lý từng phần tử và thời gian sống của stream.
- Số stream/channel lỗi do consumer không theo kịp.

Không log từng payload hoặc từng request ở mức cao trong production chỉ để đo backpressure. Dùng counter, histogram và sampling; metric label nên có cardinality thấp như route template, interaction model và service.

## 16. Checklist hoàn thành test backpressure

- Test dùng `StepVerifier` với initial demand hữu hạn hoặc bằng 0.
- Có `thenRequest(n)` để cấp demand theo từng bước.
- Xác nhận publisher không phát `onNext` vượt demand.
- Kiểm tra demand tại đúng upstream boundary bằng `doOnRequest` hoặc `TestPublisher`.
- Xác nhận cancellation truyền tới nguồn bằng `assertCancelled` hoặc cleanup signal.
- Phân biệt cancel với complete/error.
- Đánh giá prefetch của `publishOn`, `flatMap`, `concatMap` và `limitRate`.
- Nếu có buffer/drop/latest, kiểm tra capacity và overflow policy.
- Request-Channel được kiểm thử riêng cho hai hướng demand và half-close.
- Integration test xác nhận cancellation qua RSocket transport.
- Không hardcode chi tiết prefetch/REQUEST_N nội bộ vào test nghiệp vụ.
- Mọi test bất đồng bộ có timeout và cơ chế đồng bộ rõ ràng.

## 17. Kết luận

Muốn kiểm thử backpressure đúng, hãy kiểm soát demand từ subscriber bằng `StepVerifier.create(publisher, 0)` và `thenRequest(n)`, dùng `TestPublisher` để điều khiển nguồn, rồi xác minh cả request count lẫn cancellation ở upstream. Kiểm tra riêng hành vi của các operator vì prefetch, buffer và drop có thể thay đổi demand mà nguồn nhìn thấy. Với RSocket, bổ sung integration test qua `RSocketRequester` để xác nhận stream và cancellation qua transport, nhưng tránh phụ thuộc số frame `REQUEST_N` hoặc prefetch nội bộ. Request-Channel cần test demand độc lập ở hai hướng. Cuối cùng, xác nhận cleanup thực sự xảy ra; `cancel()` không phải `onComplete` và cũng không phải rollback side effect nghiệp vụ.
