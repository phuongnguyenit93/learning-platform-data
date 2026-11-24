# Gom nguồn vô hạn hoặc tạo bộ đệm không có giới hạn

Trong **REACTIVE_PROGRAMMING**, `Mono` và `Flux` biểu diễn dữ liệu bất đồng bộ theo hợp đồng `Publisher–Subscriber`. Một `Flux` có thể hữu hạn và hoàn tất, hoặc có thể phát liên tục mà không có tín hiệu `onComplete` tự nhiên. Khi ứng dụng gom toàn bộ dữ liệu của nguồn vô hạn, giữ lịch sử không giới hạn hoặc đặt một queue không có giới hạn giữa producer và consumer, bộ nhớ sẽ tăng theo thời gian.

Đây là lỗi thiết kế phổ biến trong pipeline reactive: code vẫn không block thread nhưng có thể giữ vô hạn phần tử trong heap, direct memory hoặc queue của thư viện. Reactive không đồng nghĩa với bộ nhớ tự giới hạn. Muốn hệ thống ổn định, cần xác định rõ dữ liệu nào phải giữ, giữ tối đa bao nhiêu, khi đầy thì làm gì và điều kiện nào kết thúc việc thu thập.

## 1. Nguồn vô hạn không tự hoàn tất

Một Publisher hữu hạn thường phát một số phần tử rồi gửi `onComplete`. Nguồn vô hạn có thể tiếp tục phát cho đến khi bị cancel hoặc lỗi:

```java
Flux<Long> ticks = Flux.interval(Duration.ofSeconds(1));
```

`Flux.interval` phát số tăng dần theo chu kỳ. Nếu không có toán tử giới hạn hoặc điều kiện dừng, nguồn tiếp tục chạy và không hoàn tất bình thường.

Các nguồn có thể hoạt động vô hạn gồm:

- Timer, heartbeat và polling định kỳ.
- Server-Sent Events, WebSocket hoặc event stream.
- Message broker consumer đọc liên tục.
- Watcher theo dõi file hoặc thay đổi hệ thống.
- Callback từ thiết bị, cảm biến hoặc API push.
- Stream metrics, log hoặc telemetry.

Nguồn vô hạn thường là hợp lệ. Lỗi xuất hiện khi pipeline xử lý nó như thể nguồn sẽ sớm hoàn tất, hoặc khi lưu mọi phần tử mà không có giới hạn.

## 2. Gom toàn bộ nguồn vô hạn sẽ không phát kết quả

Các operator như `collectList()` cần đợi nguồn hoàn tất để trả danh sách cuối cùng. Với nguồn không bao giờ hoàn tất, danh sách không được phát ra; các phần tử tiếp tục được giữ trong bộ nhớ:

```java
Mono<List<Long>> allTicks = Flux.interval(Duration.ofMillis(100))
    .collectList();
```

`collectList()` không phát một danh sách từng phần theo thời gian. Nó giữ các phần tử cho đến `onComplete`. Vì `interval` không hoàn tất tự nhiên, `Mono<List<Long>>` không phát kết quả và danh sách tiếp tục tăng cho đến khi bị hủy hoặc tiến trình hết bộ nhớ.

Những operator cần đặc biệt chú ý với nguồn vô hạn:

| Operator | Hành vi | Rủi ro với nguồn vô hạn |
|---|---|---|
| `collectList()` | Gom mọi phần tử thành một `List` khi nguồn hoàn tất | Danh sách tăng mãi và không phát kết quả cuối |
| `collectMap()` / `collectMultimap()` | Gom phần tử vào map | Map tăng theo số khóa/giá trị và chờ nguồn hoàn tất |
| `buffer()` không giới hạn theo kích thước/thời gian | Gom phần tử thành buffer cho đến khi có điều kiện phát | Buffer có thể không bao giờ được phát nếu chờ complete |
| `sort()` | Thu thập phần tử rồi sắp xếp | Không thể phát thứ tự toàn cục khi nguồn không hoàn tất |
| `reduce()` với accumulator tăng không giới hạn | Tích lũy vào một cấu trúc lớn | Accumulator có thể tăng mãi dù chỉ phát một kết quả cuối |

`reduce` không phải lúc nào cũng nguy hiểm. Ví dụ, cộng các số vào một `long` có kích thước cố định không giữ toàn bộ lịch sử, dù với nguồn vô hạn nó vẫn không phát kết quả cuối. Rủi ro bộ nhớ phụ thuộc vào kích thước accumulator, không chỉ tên operator.

## 3. Giới hạn thời gian hoặc số phần tử trước khi aggregate

Nếu nghiệp vụ chỉ cần một khoảng dữ liệu hữu hạn, hãy đặt điều kiện kết thúc trước operator gom:

```java
Mono<List<Long>> firstTenTicks = Flux.interval(Duration.ofMillis(100))
    .take(10)
    .collectList();
```

`take(10)` nhận tối đa mười phần tử, sau đó hoàn tất downstream và cancel upstream. `collectList()` lúc này có thể phát danh sách hữu hạn.

Có thể giới hạn theo thời gian:

```java
Mono<List<Event>> eventsInWindow = eventSource()
    .take(Duration.ofSeconds(5))
    .collectList();
```

Nguồn bị dừng sau khoảng thời gian đã chọn và danh sách chỉ chứa những phần tử đến trong khoảng đó. Cần lưu ý `take(Duration)` tạo một cửa sổ thời gian hữu hạn; nó không phù hợp nếu yêu cầu là theo dõi liên tục mãi mãi.

Nếu cần kết quả định kỳ, dùng `bufferTimeout` hoặc một cơ chế cửa sổ thay vì chờ toàn bộ nguồn hoàn tất:

```java
Flux<List<Event>> batches = eventSource()
    .bufferTimeout(100, Duration.ofSeconds(1));
```

Mỗi batch phát khi đủ 100 phần tử hoặc khi hết một giây theo semantics của operator. Kích thước tối đa của batch được giới hạn, và consumer có thể xử lý từng batch trong khi nguồn tiếp tục hoạt động.

## 4. Phân biệt buffer hữu hạn và không giới hạn

Buffer tạo ranh giới giữa producer và consumer. Nếu consumer chậm, phần tử chưa được xử lý có thể được giữ trong queue.

```text
Producer nhanh
     |
     v
  [ Buffer ] -----> Consumer chậm
     |
     +-- dung lượng hữu hạn: có điểm đầy và chính sách overflow
     +-- không giới hạn: backlog có thể tăng theo thời gian
```

Buffer không giới hạn có thể hấp thụ burst ngắn, nhưng không giải quyết tình trạng producer nhanh hơn consumer kéo dài. Khi chênh lệch tốc độ duy trì, queue tăng mãi.

Reactor có các cách tạo buffer với ngữ nghĩa khác nhau:

```java
// Không giới hạn: không phù hợp nếu producer có thể vượt consumer lâu dài.
Flux<Event> unsafe = source.onBackpressureBuffer();

// Giới hạn số phần tử đang chờ; khi vượt giới hạn, luồng báo overflow.
Flux<Event> bounded = source.onBackpressureBuffer(512);
```

`onBackpressureBuffer()` không tham số có thể giữ số phần tử chưa tiêu thụ mà không đặt giới hạn kích thước. Overload có `maxSize` giới hạn số phần tử; khi vượt ngưỡng, mặc định phát lỗi overflow. Đây là cách phát hiện quá tải thay vì âm thầm giữ thêm dữ liệu.

Một buffer hữu hạn vẫn cần chính sách khi đầy. Báo lỗi, bỏ phần tử mới, bỏ phần tử cũ hay giữ giá trị mới nhất là các quyết định nghiệp vụ khác nhau.

## 5. Chọn chính sách overflow theo ý nghĩa dữ liệu

Không có một chiến lược backpressure phù hợp cho mọi luồng:

| Chiến lược | Hành vi | Phù hợp khi |
|---|---|---|
| Buffer có giới hạn và báo lỗi | Giữ phần tử đến khi đầy; khi vượt ngưỡng, phát lỗi | Mất dữ liệu không được phép và ứng dụng cần biết quá tải |
| `onBackpressureDrop()` | Bỏ phần tử đến khi downstream chưa có demand | Dữ liệu mẫu có thể mất, như telemetry phụ |
| `onBackpressureLatest()` | Giữ giá trị mới nhất, thay thế giá trị đang chờ cũ hơn | Trạng thái hiện tại quan trọng hơn lịch sử trung gian |
| `onBackpressureBuffer(maxSize)` | Giữ tối đa số phần tử đã cấu hình, sau đó báo overflow | Cần hấp thụ burst ngắn và có thể xử lý lỗi quá tải |
| Rate limit / admission control | Giảm hoặc từ chối lượng công việc mới theo chính sách | Cần bảo vệ dependency và giới hạn tải theo thời gian |

Ví dụ bỏ tick cũ khi downstream chậm:

```java
Flux<Long> ticks = Flux.interval(Duration.ofMillis(10))
    .onBackpressureDrop();
```

Ví dụ chỉ quan tâm trạng thái mới nhất:

```java
Flux<DeviceState> latestStates = deviceStateSource()
    .onBackpressureLatest();
```

Không dùng `DROP` hoặc `LATEST` cho lệnh thanh toán, event kiểm toán hoặc dữ liệu cần xử lý đủ từng phần tử. Mất một phần tử có thể làm sai trạng thái nghiệp vụ.

## 6. Backpressure không phải rate limiting

Reactive Streams demand biểu diễn số phần tử Subscriber cho phép upstream phát. Nó không đặt giới hạn số phần tử mỗi giây.

`limitRate` chia demand thành các đợt request nhỏ hơn:

```java
Flux<Record> records = source
    .limitRate(64)
    .map(this::process);
```

Operator này điều chỉnh cách yêu cầu phần tử từ upstream. Nó không bảo đảm tối đa 64 record/giây, không phải quota và không tự làm chậm một nguồn push không thể điều tiết.

Nếu cần giới hạn theo thời gian, dùng rate limiter hoặc operator thời gian phù hợp. Ví dụ `delayElements` có thể giãn nhịp phát nhưng cũng làm tăng thời gian xử lý và có thể tạo backlog ở nguồn nếu nguồn không hỗ trợ demand. Với API có quota, nên dùng token bucket hoặc cơ chế rate limit ở tầng ứng dụng/gateway.

## 7. Nguồn push không thể giảm tốc vẫn cần chính sách

Một số nguồn phát callback độc lập với demand của Subscriber. Ví dụ cảm biến hoặc listener sự kiện có thể tiếp tục gọi callback trong khi downstream đang bận.

Khi chuyển nguồn push sang Reactor, cần chọn cách xử lý rõ ràng:

- Giữ tối đa một số phần tử rồi báo overflow.
- Bỏ phần tử mới khi consumer chưa sẵn sàng.
- Chỉ giữ phần tử mới nhất.
- Ghi dữ liệu vào broker hoặc kho bền vững để consumer xử lý sau.
- Tạm dừng nguồn nếu API thiết bị hoặc thư viện cho phép.

Không thể tạo backpressure thật sự chỉ bằng cách bọc callback vào `Flux`. Nếu nguồn không có API pause/resume hoặc demand, ứng dụng chỉ có thể quản lý dữ liệu đã nhận bằng buffer/drop/error/persist.

## 8. Các nơi khác có thể giữ dữ liệu không giới hạn

Không phải chỉ `onBackpressureBuffer()` mới có thể giữ vô hạn dữ liệu. Cần xem toàn bộ pipeline:

### Cache và replay

```java
Flux<Event> cachedHistory = eventSource().cache();
```

`cache()` có thể giữ lại lịch sử tín hiệu để subscriber đến sau nhận lại dữ liệu. Với một nguồn dài hạn hoặc vô hạn, lịch sử được giữ có thể tăng mãi. Nếu chỉ cần một số phần tử gần nhất, dùng overload giới hạn history phù hợp, ví dụ `cache(1000)`, và xác minh semantics của phiên bản Reactor đang dùng.

`replay()` cũng có thể giữ lịch sử để phát lại. Chọn giới hạn theo số phần tử hoặc thời gian nếu nghiệp vụ không cần toàn bộ lịch sử. `share()` không tương đương replay toàn bộ lịch sử; nó chia sẻ subscription giữa các subscriber trong khi được kết nối.

### Grouping có cardinality lớn

`groupBy` tạo một `GroupedFlux` cho mỗi key. Nếu nguồn có số key không giới hạn hoặc consumer không subscribe/tiêu thụ các group kịp thời, group và dữ liệu chờ có thể tích tụ. Hãy kiểm soát cardinality của key, giới hạn concurrency tiêu thụ group và bảo đảm các group được drain.

### Window và buffer lồng nhau

`window` tạo các Publisher con đại diện cho cửa sổ dữ liệu. Nếu downstream không subscribe hoặc tiêu thụ các window kịp thời, dữ liệu vẫn có thể chờ trong cấu trúc trung gian. `buffer` giữ phần tử thành collection; cần giới hạn kích thước hoặc thời gian của mỗi buffer.

### Queue ở scheduler và dependency

`publishOn`, `flatMap`, connection pool, HTTP client, broker consumer và executor đều có thể giữ công việc hoặc dữ liệu chờ. Một pipeline có backpressure vẫn có thể dùng nhiều bộ đệm ở các ranh giới khác nhau.

## 9. Đừng gom toàn bộ lịch sử khi chỉ cần trạng thái hiện tại

Một số ứng dụng lưu mọi event để tính trạng thái mới nhất:

```java
Mono<DeviceState> state = deviceEvents
    .collectList()
    .map(this::rebuildState);
```

Với event stream dài hạn, cách này giữ toàn bộ lịch sử và chờ nguồn hoàn tất. Nếu chỉ cần trạng thái hiện tại, hãy dùng accumulator có kích thước cố định hoặc lưu trạng thái vào store:

```java
Flux<DeviceState> states = deviceEvents
    .scanWith(
        DeviceState::initial,
        DeviceState::apply
    );
```

`scanWith` phát trạng thái sau mỗi event. Nếu `DeviceState` chỉ giữ các trường trạng thái hiện tại với kích thước giới hạn, bộ nhớ không tăng theo toàn bộ lịch sử. Nếu accumulator giữ một `List` hoặc `Map` tăng mãi, `scanWith` vẫn có thể gây tăng bộ nhớ; hãy xem cấu trúc dữ liệu bên trong accumulator.

Nếu cần lịch sử phục vụ audit hoặc replay, lưu vào kho chuyên dụng có retention và chính sách lưu trữ. Không dùng heap của một subscription dài hạn làm event store.

## 10. Tính ngân sách bộ nhớ cho buffer

Giới hạn buffer theo số phần tử chưa chắc giới hạn đủ chặt bộ nhớ nếu kích thước phần tử thay đổi lớn.

Ước lượng đơn giản:

\[
M \approx N \times (S + O)
\]

Trong đó:

- \(M\) là bộ nhớ ước tính cho buffer.
- \(N\) là số phần tử tối đa đang chờ.
- \(S\) là kích thước payload trung bình.
- \(O\) là overhead trung bình cho object/queue reference.

Ví dụ, buffer 1.000 phần tử với payload trung bình 64 KiB có thể giữ khoảng 62,5 MiB payload, chưa tính object, queue node, metadata, direct buffer và bản sao trong codec. Nếu có nhiều subscription đồng thời, lượng bộ nhớ tổng cộng có thể nhân lên.

Đây chỉ là ước lượng để thiết kế ngân sách. Payload có thể có phân phối kích thước lệch mạnh; hãy đo p95/p99 kích thước và tính tổng số buffer có thể tồn tại ở mọi ranh giới.

Với dữ liệu có kích thước không đồng đều, nên giới hạn cả số phần tử lẫn tổng byte. Có thể cần một weighted semaphore, byte budget hoặc cơ chế admission control ở tầng ứng dụng thay vì chỉ dựa trên `maxSize` theo phần tử.

## 11. Cancellation phải giải phóng queue và tài nguyên phần tử

Khi downstream không còn cần dữ liệu, cancellation nên truyền ngược upstream để dừng nguồn nếu có thể. Nhưng phần tử đã nằm trong queue có thể cần cleanup, nhất là khi chúng giữ `DataBuffer`, `ByteBuf`, file handle hoặc tài nguyên có reference count.

Với các operator hỗ trợ discard, có thể đăng ký cleanup:

```java
Flux<Message> messages = pooledFrames
    .filter(ByteBuf::isReadable)
    .doOnDiscard(ByteBuf.class, ByteBuf::release)
    .map(this::decodeAndCopy);
```

`doOnDiscard` cần đặt ở downstream của operator có thể loại bỏ phần tử và chỉ hoạt động với operator hỗ trợ discard. Phần tử được tiêu thụ bình thường cần được giải phóng trong đường xử lý tương ứng. Không được giải phóng hai lần cùng một buffer.

Với resource gắn với toàn bộ subscription như cursor hoặc connection, dùng `using` hoặc `usingWhen` để cleanup khi complete, error và cancel. Không chỉ dựa vào `doOnComplete`, vì cancellation không phát `onComplete`.

## 12. Xử lý overflow thay vì để bộ nhớ tự tăng

Một queue hữu hạn cần định nghĩa điều gì xảy ra khi đầy. Các lựa chọn thường là:

- **Fail fast:** phát lỗi overflow để upstream hoặc caller biết hệ thống không nhận thêm.
- **Drop newest:** bỏ phần tử mới đến.
- **Drop oldest:** loại phần tử cũ đang chờ để nhường chỗ cho dữ liệu mới.
- **Keep latest:** chỉ giữ trạng thái mới nhất.
- **Persist:** ghi dữ liệu vào broker/log/database để xử lý sau.
- **Pause producer:** tạm dừng nguồn nếu giao thức hoặc API hỗ trợ.

Với dữ liệu quan trọng, fail fast hoặc persist thường dễ bảo toàn semantics hơn việc âm thầm drop. Với telemetry không quan trọng hoặc trạng thái hiện tại, drop/latest có thể hợp lý.

Nếu dùng `onBackpressureBuffer(maxSize)`, overflow mặc định sẽ trở thành lỗi. Có thể xử lý lỗi ở ranh giới phù hợp:

```java
Flux<Event> bounded = source
    .onBackpressureBuffer(512)
    .onErrorResume(Exceptions::isOverflow, error -> {
        metrics.increment("event-buffer-overflow");
        return Flux.error(new ServiceOverloadedException(error));
    });
```

Trong mã thực tế, hãy dùng đúng kiểu exception overflow của phiên bản Reactor đang dùng hoặc kiểm tra nguyên nhân theo API đã cấu hình. Không bắt mọi lỗi rồi thay bằng empty stream, vì điều đó có thể làm mất dữ liệu và che giấu sự cố.

## 13. Retry không phải cách xử lý queue đầy

Khi queue overflow, retry ngay toàn bộ pipeline có thể tạo thêm subscription và thêm tải vào nguồn vốn đã quá tải. Nếu nguồn phát lại dữ liệu từ đầu, retry còn có thể tạo phần tử trùng hoặc lặp lại side effect.

Chỉ retry khi lỗi có khả năng tạm thời, có giới hạn số lần, backoff/jitter và thao tác có tính idempotent. Với overflow do consumer chậm kéo dài, cần giảm tải đầu vào, tăng năng lực xử lý trong giới hạn dependency hoặc từ chối công việc mới.

Không nên dùng retry vô hạn cho `onBackpressureBuffer()` không giới hạn hoặc một queue đã đầy. Retry không làm tăng tốc độ tiêu thụ và có thể khiến backlog tăng nhanh hơn.

## 14. Kiểm thử nguồn vô hạn và giới hạn buffer

Kiểm thử cần xác minh nguồn được giới hạn, queue có hành vi overflow đúng và cancellation dừng việc giữ dữ liệu.

### Xác minh nguồn vô hạn được giới hạn bằng take

```java
StepVerifier.withVirtualTime(() ->
        Flux.interval(Duration.ofSeconds(1)).take(3)
    )
    .thenAwait(Duration.ofSeconds(3))
    .expectNext(0L, 1L, 2L)
    .verifyComplete();
```

Virtual time giúp kiểm thử timer mà không phải chờ ba giây thực. `take(3)` bảo đảm pipeline hoàn tất sau ba phần tử.

### Kiểm thử buffer hữu hạn bị overflow

```java
TestPublisher<Integer> source = TestPublisher.create();

StepVerifier.create(source.flux().onBackpressureBuffer(2), 0)
    .then(() -> source.next(1, 2, 3))
    .expectError()
    .verify();
```

Subscriber bắt đầu với demand bằng 0. Buffer chỉ giữ tối đa hai phần tử; phần tử thứ ba vượt giới hạn và pipeline phát lỗi overflow. Test này xác minh giới hạn phần tử, không đo chính xác byte được cấp phát.

### Kiểm thử cancellation

```java
AtomicInteger cancelled = new AtomicInteger();

StepVerifier.withVirtualTime(() ->
        Flux.interval(Duration.ofMillis(100))
            .doOnCancel(cancelled::incrementAndGet)
    )
    .thenAwait(Duration.ofMillis(100))
    .expectNext(0L)
    .thenCancel()
    .verify();

assertEquals(1, cancelled.get());
```

Test xác nhận cancellation được truyền đến nguồn interval. Với queue chứa tài nguyên, cần bổ sung assertion cleanup/discard để xác nhận phần tử chờ đã được giải phóng.

## 15. Theo dõi dấu hiệu bộ đệm không giới hạn

Các chỉ số nên quan sát:

1. Heap used, old-generation occupancy và tốc độ garbage collection.
2. Direct memory và pooled buffer usage.
3. Queue depth, số phần tử đang chờ và số lần overflow.
4. Số phần tử bị drop hoặc thay thế theo chính sách.
5. Tốc độ phần tử đến so với tốc độ xử lý.
6. Consumer lag và tuổi của phần tử cũ nhất đang chờ.
7. Số subscription dài hạn, cache/replay size và số group đang mở.
8. Số request đang hoạt động, pending acquire và cancellation.

Nếu heap tăng tuyến tính theo thời gian trong khi số request đồng thời ổn định, hãy tìm cấu trúc giữ lịch sử hoặc queue không giới hạn. Nếu heap ổn định nhưng direct memory tăng, kiểm tra DataBuffer/ByteBuf và vòng đời release. Nếu queue tăng rồi giảm sau burst, buffer có thể đang hoạt động đúng; nếu queue không giảm, consumer có thể không theo kịp hoặc không còn drain dữ liệu.

## 16. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| `collectList()` trên nguồn vô hạn | Giữ mọi phần tử và không phát danh sách cuối | Dùng `take`, window, bufferTimeout hoặc accumulator hữu hạn |
| `onBackpressureBuffer()` không giới hạn | Queue tăng theo chênh lệch producer/consumer | Dùng maxSize và chính sách overflow |
| `cache()`/`replay()` giữ toàn bộ lịch sử | Bộ nhớ tăng theo số phần tử đã phát | Giới hạn history hoặc dùng store bền vững |
| `groupBy` với key không giới hạn | Tạo quá nhiều group và dữ liệu chờ | Giới hạn cardinality, concurrency và drain group |
| `buffer()` chờ nguồn complete | Buffer có thể không phát với nguồn vô hạn | Dùng giới hạn kích thước hoặc thời gian |
| Nghĩ `limitRate` là rate limit | Không giới hạn phần tử mỗi giây | Dùng rate limiter theo thời gian |
| Chỉ giới hạn số phần tử, bỏ qua kích thước payload | Một queue nhỏ vẫn có thể chiếm nhiều bộ nhớ | Tính byte budget và giới hạn payload |
| Retry khi queue overflow | Tạo thêm tải và có thể xử lý trùng | Giảm tải, persist, fail fast hoặc điều chỉnh capacity |
| Không cleanup phần tử bị discard | Rò rỉ pooled buffer hoặc resource | Dùng discard hook và cleanup theo ownership |

## 17. Checklist trước khi triển khai stream dài hạn

Trước khi đưa một `Flux` chạy lâu dài vào production, hãy trả lời:

1. Nguồn có hoàn tất không, hay cần được xem là vô hạn?
2. Có operator nào gom toàn bộ dữ liệu hoặc chờ `onComplete` không?
3. Cache, replay, group và window có giữ lịch sử hoặc queue tăng không giới hạn không?
4. Mọi buffer có `maxSize`, thời gian hoặc byte budget rõ ràng chưa?
5. Khi đầy, hệ thống fail, drop, latest, persist hay pause producer?
6. Producer có thực sự hỗ trợ demand/pause, hay chỉ là nguồn push?
7. `flatMap` concurrency và prefetch có giới hạn phù hợp không?
8. Cancellation có dừng nguồn và cleanup phần tử đang chờ không?
9. Retry có giới hạn, backoff và idempotency không?
10. Metrics có theo dõi queue depth, lag, drop, overflow và memory không?
11. Test có bao phủ nguồn vô hạn, overflow, cancellation và cleanup không?

Nguồn vô hạn là mô hình hợp lệ cho event stream, timer và message consumer; điều nguy hiểm là gom toàn bộ lịch sử hoặc để backlog tăng mà không có giới hạn. Hãy dùng `take` khi cần phạm vi hữu hạn, window/buffer có kích thước hoặc thời gian khi cần xử lý theo lô, accumulator hữu hạn khi chỉ cần trạng thái hiện tại, và queue có giới hạn cùng overflow policy khi consumer có thể chậm. Kết hợp byte budget, cancellation, cleanup và metrics giúp pipeline reactive duy trì bộ nhớ có thể dự đoán ngay cả khi nguồn hoạt động liên tục.
