# Đo khoảng cách thời gian giữa các phần tử

Trong một luồng sự kiện bất đồng bộ, khoảng cách giữa hai phần tử liên tiếp có thể cho biết nguồn đang phát đều, bị chậm hoặc vừa trải qua một đợt tăng tải. Ví dụ, dịch vụ theo dõi đơn hàng có thể cần phát hiện khi cập nhật từ đối tác vận chuyển đến quá thưa; hệ thống telemetry có thể cần đo nhịp dữ liệu cảm biến; một pipeline xử lý thông điệp có thể cần xác định thời gian chờ giữa các lần nhận.

Reactor cung cấp các toán tử thời gian để quan sát nhịp phát của tín hiệu. Với mục tiêu đo khoảng cách giữa các phần tử, toán tử thường dùng là `elapsed()`. Toán tử này gắn mỗi phần tử với thời gian đã trôi qua kể từ tín hiệu `onNext` trước đó; với phần tử đầu tiên, khoảng thời gian được tính từ lúc subscription bắt đầu. Kết quả giúp phân tích nhịp phát mà không cần tự quản lý timestamp cho từng phần tử.

Bài học thuộc module `REACTIVE_PROGRAMMING`, nơi người học thực hành các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và cơ chế backpressure của Reactive Streams; đồng thời sử dụng `Mono`, `Flux`, kết hợp toán tử, kiểm soát scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java. Nội dung tập trung vào cách đo khoảng cách thời gian đúng tại ranh giới cần quan sát, phân biệt khoảng cách tín hiệu với thời điểm nghiệp vụ, và kiểm thử kết quả bằng thời gian ảo.

## 1. `elapsed()` đo điều gì?

`elapsed()` biến mỗi phần tử `T` thành một cặp `Tuple2<Long, T>`:

- `getT1()` là khoảng thời gian tính bằng mili giây kể từ tín hiệu `onNext` trước đó.
- `getT2()` là phần tử gốc được phát ra.

Với phần tử đầu tiên, mốc bắt đầu là lúc subscription được thiết lập. Với các phần tử tiếp theo, mốc bắt đầu là thời điểm toán tử quan sát phần tử trước đó.

```java
Flux<String> events = Flux.just("created", "paid", "packed");

Flux<Tuple2<Long, String>> measured = events.elapsed();

measured.subscribe(tuple -> {
    Long gapMs = tuple.getT1();
    String event = tuple.getT2();
    System.out.println(event + " arrived after " + gapMs + " ms");
});
```

`Flux.just` phát các phần tử gần như ngay lập tức, nên các khoảng đo thường rất nhỏ. Trong ứng dụng thật, nguồn có thể là socket, message broker, timer hoặc một publisher bất đồng bộ có độ trễ thực tế.

Sơ đồ dưới đây minh họa cách tính khoảng cách:

```text
Subscription
     |
     |---- 120 ms ---- onNext(A)
                          |
                          |---- 450 ms ---- onNext(B)
                                               |
                                               |---- 80 ms ---- onNext(C)

elapsed output:
  (120, A), (450, B), (80, C)
```

`elapsed()` đo thời gian quan sát được giữa các tín hiệu tại vị trí đặt operator. Nó không tự biết sự kiện đã xảy ra ở hệ thống nguồn vào thời điểm nào, cũng không đo thời gian xử lý nghiệp vụ trước khi sự kiện được phát vào pipeline.

### Phần tử đầu tiên và luồng rỗng

Với một `Flux` có phần tử, cặp đầu tiên đo thời gian từ lúc subscription đến khi phần tử đầu tiên đến `elapsed`. Với `Mono` có một giá trị, kết quả cũng có một cặp biểu diễn thời gian từ subscription đến giá trị đó. Nếu nguồn hoàn tất mà không phát phần tử, không có cặp nào được tạo.

Toán tử không tạo một phần tử bổ sung khi nguồn hoàn tất hoặc phát lỗi. Nó chỉ gắn thời gian cho các tín hiệu `onNext`. Vì vậy, khoảng thời gian từ phần tử cuối cùng đến `onComplete` không xuất hiện trong kết quả `elapsed()`.

## 2. Sử dụng kết quả `Tuple2` trong pipeline

Kết quả `elapsed()` thường được chuyển ngay thành một kiểu dữ liệu domain để phần còn lại của pipeline không phải thao tác trực tiếp với `Tuple2`.

```java
record EventGap(OrderEvent event, Duration sincePrevious) {}

Flux<EventGap> gaps = orderEvents
    .elapsed()
    .map(tuple -> new EventGap(
        tuple.getT2(),
        Duration.ofMillis(tuple.getT1())
    ));
```

Sau khi chuyển thành `Duration`, có thể áp dụng các phép so sánh và quy tắc nghiệp vụ rõ ràng hơn:

```java
Flux<EventGap> delayedEvents = gaps
    .filter(gap -> gap.sincePrevious().compareTo(Duration.ofSeconds(5)) > 0);
```

Pipeline này giữ lại những sự kiện có khoảng cách với sự kiện trước lớn hơn năm giây. Lưu ý rằng phần tử đầu tiên được so với thời điểm subscription, nên nếu không muốn đánh giá thời gian chờ khởi động nguồn, có thể xử lý riêng phần tử đầu tiên hoặc lưu một cờ đánh dấu trong bước chuyển đổi.

Ví dụ xử lý riêng phần tử đầu tiên:

```java
Flux<EventGap> gapsAfterFirst = orderEvents
    .elapsed()
    .skip(1)
    .map(tuple -> new EventGap(
        tuple.getT2(),
        Duration.ofMillis(tuple.getT1())
    ));
```

`skip(1)` loại bỏ cặp đầu tiên, sau đó các cặp còn lại chỉ phản ánh khoảng cách giữa hai phần tử liên tiếp. Cách này phù hợp nếu yêu cầu là đo nhịp giữa các sự kiện và không quan tâm thời gian khởi động đến sự kiện đầu tiên.

## 3. Đặt `elapsed()` ở đâu trong pipeline?

Vị trí đặt operator quyết định khoảng thời gian nào được quan sát. Hãy xem xét hai pipeline:

```java
Flux<EventGap> sourceGaps = eventSource
    .elapsed()
    .publishOn(Schedulers.parallel())
    .map(this::process);

Flux<EventGap> downstreamGaps = eventSource
    .publishOn(Schedulers.parallel())
    .elapsed()
    .map(this::process);
```

Ở pipeline thứ nhất, `elapsed()` nằm trước `publishOn`, nên đo khoảng cách khi các tín hiệu đi qua ranh giới của `eventSource` và `elapsed`. Độ trễ do hàng đợi và lịch chạy ở `publishOn` nằm sau điểm đo.

Ở pipeline thứ hai, `elapsed()` nằm sau `publishOn`, nên đo khoảng cách giữa các tín hiệu mà downstream quan sát được sau khi chúng đi qua hàng đợi và scheduler. Khoảng đo có thể bao gồm ảnh hưởng của việc chuyển luồng, hàng đợi và độ trễ lập lịch.

Chọn vị trí dựa trên câu hỏi cần trả lời:

- Muốn đo nhịp sự kiện đến từ nguồn: đặt `elapsed()` ngay sau nguồn.
- Muốn đo nhịp tín hiệu tại một tầng xử lý cụ thể: đặt operator ngay trước tầng đó.
- Muốn quan sát nhịp sau khi chuyển scheduler: đặt sau `publishOn` tương ứng.
- Muốn đo khoảng cách giữa các kết quả sau khi lọc hoặc gộp: đặt sau operator làm thay đổi luồng phần tử.

Ví dụ, nếu đặt `elapsed()` sau `filter`, khoảng cách đo được là giữa các phần tử còn lại sau lọc. Những phần tử đã bị loại bỏ không xuất hiện và thời gian của chúng vẫn nằm trong khoảng đo giữa hai phần tử được giữ lại. Nếu đặt trước `filter`, mỗi khoảng được tính trên toàn bộ sự kiện đầu vào, kể cả sự kiện sau đó bị loại bỏ.

## 4. Chọn scheduler cho phép đo

Reactor cung cấp overload `elapsed(Scheduler)` để chỉ định scheduler dùng làm nguồn thời gian cho phép đo. Overload không tham số sử dụng scheduler mặc định của Reactor (`Schedulers.parallel()`).

```java
Flux<Tuple2<Long, Event>> measured = eventSource
    .elapsed(Schedulers.parallel());
```

Việc truyền scheduler tường minh hữu ích khi cần kiểm soát clock trong kiểm thử hoặc muốn đồng bộ cách đo với một scheduler được quản lý trong ứng dụng. Cần phân biệt scheduler dùng để đo thời gian với scheduler thực thi callback downstream: `elapsed(scheduler)` chọn nguồn thời gian cho phép đo, còn `publishOn` và `subscribeOn` điều khiển nơi thực thi các phần của pipeline.

Ví dụ tách hai mục đích:

```java
Flux<EventGap> gaps = eventSource
    .elapsed(Schedulers.parallel())
    .map(tuple -> new EventGap(
        tuple.getT2(),
        Duration.ofMillis(tuple.getT1())
    ))
    .publishOn(Schedulers.boundedElastic())
    .map(this::persistGap);
```

Ở đây scheduler của `elapsed` cung cấp clock cho phép đo; `publishOn` chuyển phần xử lý lưu kết quả sang scheduler dành cho tác vụ blocking. Hai vai trò không nên bị nhầm lẫn.

## 5. Phân biệt khoảng cách với timestamp tuyệt đối

`elapsed()` và `timestamp()` đều có thể trả về `Tuple2<Long, T>`, nhưng ý nghĩa của phần tử đầu tiên khác nhau:

| Toán tử | Giá trị thời gian | Câu hỏi trả lời |
|---|---|---|
| `elapsed()` | Số mili giây kể từ tín hiệu `onNext` trước đó; phần tử đầu tiên tính từ subscription. | Hai tín hiệu cách nhau bao lâu? |
| `timestamp()` | Timestamp tại thời điểm tín hiệu được quan sát, tính theo mili giây epoch. | Tín hiệu được quan sát vào thời điểm nào? |
| `timed()` | Bọc phần tử trong `Timed<T>`, cung cấp khoảng cách, timestamp và thời gian từ subscription. | Cần nhiều thông tin thời gian cho cùng một tín hiệu? |

Ví dụ dùng `timestamp()`:

```java
Flux<Tuple2<Long, Event>> stamped = eventSource.timestamp();

stamped.subscribe(tuple -> {
    Instant observedAt = Instant.ofEpochMilli(tuple.getT1());
    Event event = tuple.getT2();
    audit(event, observedAt);
});
```

Timestamp này là thời điểm Reactor quan sát tín hiệu tại vị trí đặt operator. Nó không nhất thiết là thời điểm sự kiện được tạo trong hệ thống nguồn. Nếu sự kiện đã mang `occurredAt`, hãy giữ timestamp đó riêng để phân biệt thời điểm nghiệp vụ với thời điểm nhận.

### Dùng `timed()` khi cần đối tượng thời gian đầy đủ

`timed()` phát `Timed<T>`, cung cấp các thông tin thời gian có ngữ nghĩa rõ hơn so với tuple:

```java
Flux<Timed<Event>> timedEvents = eventSource.timed();

timedEvents.subscribe(timed -> {
    Event event = timed.get();
    Duration gap = timed.elapsed();
    Instant observedAt = timed.timestamp();
    Duration sinceSubscription = timed.elapsedSinceSubscription();

    recordTiming(event, gap, observedAt, sinceSubscription);
});
```

Các trường thông tin giúp phân biệt:

- `elapsed()`: thời gian từ tín hiệu trước đến tín hiệu hiện tại; với phần tử đầu tiên là từ subscription.
- `timestamp()`: thời điểm quan sát tín hiệu dưới dạng `Instant`.
- `elapsedSinceSubscription()`: tổng thời gian kể từ subscription đến tín hiệu hiện tại.

Nếu chỉ cần khoảng cách tính bằng mili giây, `elapsed()` thường đủ và kết quả nhẹ, đơn giản. Nếu cần đồng thời khoảng cách, timestamp và thời gian từ subscription, `timed()` diễn đạt mục tiêu rõ hơn.

## 6. Đo nhịp sự kiện trong các tình huống thực tế

### Phát hiện khoảng im lặng giữa các sự kiện

Một dịch vụ có thể ghi nhận những khoảng cách bất thường lớn giữa các thông điệp:

```java
Flux<GapAlert> alerts = messageStream
    .elapsed()
    .filter(tuple -> tuple.getT1() > 10_000)
    .map(tuple -> new GapAlert(
        tuple.getT2().sourceId(),
        Duration.ofMillis(tuple.getT1())
    ));
```

Pipeline phát cảnh báo khi khoảng cách giữa hai tín hiệu quan sát được lớn hơn mười giây. Nếu nguồn không phát phần tử nào trong thời gian dài rồi hoàn tất, `elapsed()` không tự tạo cảnh báo cho khoảng im lặng cuối cùng. Khi cần phát hiện không có tín hiệu trong một khoảng thời gian, hãy xem xét `timeout` hoặc một timer giám sát riêng.

### Tính tốc độ đến gần đúng

Nếu các phần tử đến đều, khoảng cách trung bình có thể dùng để ước lượng tốc độ. Ví dụ, khoảng cách trung bình 20 ms tương ứng khoảng 50 phần tử mỗi giây. Tuy nhiên, không nên dùng một khoảng đo đơn lẻ để kết luận thông lượng ổn định; các luồng thực tế thường có burst và khoảng nghỉ.

Có thể tạo số liệu tích lũy đơn giản:

```java
record GapStats(long count, long totalMillis, long maxMillis) {
    GapStats add(long gap) {
        return new GapStats(
            count + 1,
            totalMillis + gap,
            Math.max(maxMillis, gap)
        );
    }

    double averageMillis() {
        return count == 0 ? 0.0 : (double) totalMillis / count;
    }
}

Flux<GapStats> stats = eventStream
    .elapsed()
    .map(Tuple2::getT1)
    .scan(new GapStats(0, 0, 0), GapStats::add);
```

Trong ví dụ này, `scan` phát trạng thái thống kê sau mỗi khoảng đo. `count` tính cả khoảng đầu tiên từ subscription đến phần tử đầu tiên. Nếu chỉ muốn thống kê khoảng cách giữa các phần tử, thêm `skip(1)` trước khi chuyển tuple thành số mili giây.

Để có số liệu vận hành đáng tin cậy, nên gom thống kê theo cửa sổ thời gian hoặc batch, đồng thời theo dõi trung vị, percentile và giá trị lớn nhất. Trung bình có thể che khuất các đợt trễ hiếm nhưng nghiêm trọng.

### So sánh thời điểm nghiệp vụ với thời điểm tiếp nhận

Giả sử mỗi sự kiện có `occurredAt` do hệ thống nguồn tạo và adapter gắn `receivedAt` khi nhận. Có thể dùng timestamp để ghi nhận thời điểm nhận và tính độ trễ truyền tải:

```java
Flux<ObservedEvent> observed = eventStream
    .timestamp()
    .map(tuple -> new ObservedEvent(
        tuple.getT2(),
        Instant.ofEpochMilli(tuple.getT1())
    ));
```

Sau đó, nếu đồng hồ nguồn và hệ thống nhận đã được đồng bộ phù hợp, có thể tính `receivedAt - occurredAt` để ước lượng độ trễ. Cần ghi rõ giả định về đồng bộ đồng hồ; nếu không, chênh lệch có thể phản ánh sai lệch clock thay vì độ trễ mạng.

`elapsed()` phù hợp hơn để đo nhịp tín hiệu quan sát tại một điểm trong pipeline. `timestamp()` phù hợp hơn để lưu thời điểm quan sát. Thông tin do nguồn cung cấp nên được giữ riêng để phục vụ phân tích thời điểm nghiệp vụ.

## 7. Phân biệt `elapsed`, `delayElements`, `timeout` và `interval`

Các operator thời gian có tên gọi gần nhau nhưng mục đích khác nhau:

| Operator | Tác dụng | Có đo khoảng cách hiện tại không? |
|---|---|---|
| `elapsed()` | Gắn mỗi phần tử với thời gian kể từ tín hiệu trước. | Có. |
| `delayElements(duration)` | Trì hoãn việc chuyển từng phần tử xuống downstream. | Không; nó thay đổi thời điểm quan sát. |
| `timeout(duration)` | Phát lỗi nếu không có tín hiệu tiếp theo trong thời hạn quy định. | Không; nó kiểm tra giới hạn chờ. |
| `interval(period)` | Tạo một luồng số theo nhịp thời gian. | Không; nó tạo nhịp mới. |
| `timestamp()` | Gắn thời điểm quan sát vào mỗi phần tử. | Không; nó ghi mốc tuyệt đối. |

Ví dụ `delayElements`:

```java
Flux<Event> slowed = eventStream
    .delayElements(Duration.ofMillis(200));
```

Mỗi phần tử được trì hoãn trước khi chuyển xuống. Nếu đặt `elapsed()` sau `delayElements`, khoảng đo sẽ phản ánh cả nhịp nguồn và độ trễ được thêm vào bởi operator. Nếu mục tiêu là quan sát nhịp gốc, đặt `elapsed()` trước `delayElements`.

Ví dụ `timeout`:

```java
Flux<Event> monitored = eventStream
    .timeout(Duration.ofSeconds(15));
```

Nếu không có tín hiệu trong khoảng thời gian quy định, pipeline phát lỗi timeout. `elapsed()` chỉ báo khoảng thời gian đã trôi qua khi có phần tử tiếp theo đến; nó không tự phát lỗi chỉ vì một khoảng đo lớn.

Ví dụ `interval`:

```java
Flux<Long> heartbeat = Flux.interval(Duration.ofSeconds(1));
```

`interval` tạo một nguồn nhịp định kỳ, thường dùng cho heartbeat hoặc polling. `elapsed` quan sát nhịp của một nguồn đã có; `interval` tạo ra nguồn thời gian mới.

## 8. Khoảng cách đo được chịu ảnh hưởng của pipeline

Khoảng cách giữa các tín hiệu tại một operator có thể khác với khoảng cách giữa sự kiện tại nguồn. Một số yếu tố thường ảnh hưởng:

- **Backpressure:** nguồn tuân thủ demand có thể chờ subscriber yêu cầu thêm phần tử, khiến nhịp quan sát thay đổi theo tốc độ tiêu thụ.
- **Buffer và prefetch:** phần tử có thể được lấy trước rồi chờ trong hàng đợi; phép đo sau hàng đợi bao gồm thời gian chờ đó.
- **Scheduler:** việc chuyển luồng có thể thêm độ trễ lập lịch và cạnh tranh tài nguyên.
- **Operator lọc hoặc gộp:** khi đặt `elapsed` sau các bước này, phép đo phản ánh nhịp của phần tử còn lại sau biến đổi.
- **Xử lý đồng bộ:** một callback downstream chậm có thể ảnh hưởng đến thời điểm phần tử tiếp theo được quan sát trong những pipeline chạy tuần tự.

Do đó, hãy ghi lại vị trí đo cùng tên metric. Chẳng hạn `source.interarrival.ms` và `after-enrichment.interarrival.ms` là hai phép đo khác nhau, dù cùng dùng `elapsed()`.

### Không dùng `elapsed()` để đo thời gian xử lý một phần tử

Giả sử mỗi phần tử đi qua một hàm xử lý mất 100 ms. `elapsed()` sau nguồn đo khoảng cách giữa các phần tử đến điểm đo; nó không tự đo thời gian mapper bắt đầu và kết thúc cho từng phần tử.

Để đo thời gian xử lý của từng phần tử, có thể ghi mốc bắt đầu và kết thúc trong bước xử lý:

```java
Flux<ProcessedEvent> processed = eventStream.map(event -> {
    long started = System.nanoTime();
    try {
        return process(event);
    } finally {
        long durationNanos = System.nanoTime() - started;
        processingTimer.record(durationNanos, TimeUnit.NANOSECONDS);
    }
});
```

`System.nanoTime()` phù hợp để đo khoảng thời gian trong cùng JVM vì nó dùng clock đơn điệu cho phép tính chênh lệch. Không dùng `System.currentTimeMillis()` để đo thời lượng ngắn nếu có thể tránh được, vì clock hệ thống có thể được điều chỉnh.

Với xử lý bất đồng bộ trả về `Mono` hoặc `Flux`, đặt phép đo quanh publisher con bằng các operator như `doOnSubscribe` và `doFinally`, hoặc dùng một abstraction đo thời gian có hỗ trợ reactive để thời gian được tính trọn từ lúc subscribe đến khi complete, error hoặc cancel. Không chỉ đo thời gian tạo publisher trong mapper vì thao tác bất đồng bộ có thể hoàn tất sau đó.

## 9. Đo thời gian hoàn tất toàn luồng

`elapsed()` không phát một giá trị tổng thời gian khi nguồn hoàn tất. Nếu cần đo thời gian sống của cả subscription, có thể ghi mốc lúc subscribe và tính thời lượng trong `doFinally`:

```java
Flux<Event> measuredLifetime = Flux.defer(() -> {
    long started = System.nanoTime();

    return eventSource.doFinally(signalType -> {
        long duration = System.nanoTime() - started;
        subscriptionTimer.record(duration, TimeUnit.NANOSECONDS);
        log.info("Subscription finished with {}", signalType);
    });
});
```

`Flux.defer` tạo mốc bắt đầu riêng cho mỗi subscription. `doFinally` được gọi khi subscription kết thúc bằng complete, error hoặc cancel, nên phép đo bao gồm toàn bộ vòng đời quan sát của subscription.

Nếu chỉ cần thời gian từ lúc subscribe đến lúc một `Mono` phát giá trị, có thể dùng `timed()` hoặc `elapsed()` trên `Mono`. Nếu cần thời gian đến terminal signal kể cả khi không có giá trị hoặc khi bị cancel, hãy đo vòng đời bằng `doFinally` như trên.

## 10. Kiểm thử khoảng cách bằng thời gian ảo

Không nên dùng `Thread.sleep` trong kiểm thử để tạo khoảng cách giữa các phần tử. Nó làm bài kiểm thử chậm, dễ dao động theo tải máy và khó xác minh chính xác. Reactor Test cung cấp `StepVerifier.withVirtualTime` để điều khiển thời gian mà không phải chờ thật.

Ví dụ kiểm thử `elapsed()` với `Flux.interval`:

```java
StepVerifier.withVirtualTime(() ->
        Flux.interval(Duration.ofSeconds(1))
            .take(3)
            .elapsed()
    )
    .thenAwait(Duration.ofSeconds(3))
    .assertNext(tuple -> {
        assertEquals(1_000L, tuple.getT1());
        assertEquals(0L, tuple.getT2());
    })
    .assertNext(tuple -> {
        assertEquals(1_000L, tuple.getT1());
        assertEquals(1L, tuple.getT2());
    })
    .assertNext(tuple -> {
        assertEquals(1_000L, tuple.getT1());
        assertEquals(2L, tuple.getT2());
    })
    .verifyComplete();
```

Supplier truyền vào `withVirtualTime` tạo pipeline sau khi scheduler ảo được cài đặt. Ba phần tử của `interval` xuất hiện cách nhau một giây; vì phần tử đầu tiên cũng được đo từ subscription, khoảng đầu tiên là một giây.

Nếu muốn bỏ qua khoảng từ subscription đến phần tử đầu tiên, có thể thêm `skip(1)` sau `elapsed()` và chỉ kiểm tra hai khoảng còn lại. Khi kiểm thử một pipeline có scheduler được truyền tường minh, cần bảo đảm scheduler đó cũng là scheduler ảo đang được điều khiển; nếu dùng một scheduler thực khác, `thenAwait` không thể tự điều khiển clock của scheduler đó.

Các trường hợp nên kiểm thử:

- Phần tử đầu tiên được đo từ thời điểm subscription.
- Các phần tử tiếp theo có khoảng cách đúng theo thời gian ảo.
- Nguồn rỗng không phát tuple nào và hoàn tất bình thường.
- Nguồn lỗi vẫn phát lỗi, không tạo tuple giả cho terminal signal.
- `skip(1)` loại bỏ đúng khoảng đo đầu tiên nếu yêu cầu chỉ quan tâm khoảng giữa các phần tử.
- Vị trí của `elapsed` trước hoặc sau `publishOn`, `filter` và `delayElements` tạo ra phép đo đúng với ranh giới cần quan sát.

## 11. Tình huống thực tế: giám sát nhịp cập nhật vận chuyển

Một hệ thống nhận cập nhật vị trí xe từ đối tác vận chuyển. Dịch vụ cần phát hiện khi một xe ngừng gửi dữ liệu trong thời gian bất thường và ghi nhận nhịp cập nhật để phân tích chất lượng tích hợp.

Một pipeline có thể đo khoảng cách trước khi làm giàu dữ liệu:

```java
Flux<PositionGap> positionGaps = positionEvents
    .elapsed()
    .map(tuple -> new PositionGap(
        tuple.getT2().vehicleId(),
        tuple.getT2().position(),
        Duration.ofMillis(tuple.getT1())
    ));

Flux<PositionGap> slowUpdates = positionGaps
    .filter(gap -> gap.sincePrevious().compareTo(Duration.ofSeconds(30)) > 0);
```

Nếu mỗi xe có luồng riêng, nên nhóm theo `vehicleId` trước khi đo để khoảng cách được tính riêng cho từng xe. Nếu đo trực tiếp trên một luồng tổng hợp nhiều xe, sự kiện của xe khác có thể làm khoảng cách giữa hai phần tử ngắn đi và che khuất việc một xe cụ thể đã im lặng lâu.

Ví dụ phân nhóm:

```java
Flux<VehicleAlert> alerts = positionEvents
    .groupBy(PositionEvent::vehicleId)
    .flatMap(vehicleStream -> vehicleStream
        .elapsed()
        .skip(1)
        .filter(tuple -> tuple.getT1() > 30_000)
        .map(tuple -> new VehicleAlert(
            vehicleStream.key(),
            tuple.getT2(),
            Duration.ofMillis(tuple.getT1())
        ))
    );
```

Đoạn mã minh họa phép đo theo từng nhóm. Trong hệ thống có số lượng xe lớn hoặc thay đổi liên tục, cần quản lý số nhóm, vòng đời nhóm và cách giải phóng trạng thái. Ngoài ra, `elapsed()` chỉ phát cảnh báo khi có phần tử tiếp theo đến sau khoảng im lặng. Nếu muốn cảnh báo ngay khi vượt quá 30 giây mà chưa có sự kiện mới, cần kết hợp một timer hoặc `timeout` theo từng nhóm.

## 12. Checklist khi đo khoảng cách thời gian

- Xác định muốn đo từ subscription đến phần tử đầu tiên hay chỉ giữa các phần tử liên tiếp.
- Đặt `elapsed()` tại đúng ranh giới cần quan sát: trước hay sau filter, buffer, scheduler hoặc bước xử lý.
- Dùng `getT1()` như số mili giây và `getT2()` để lấy phần tử gốc.
- Chuyển sang `Duration` sớm nếu logic nghiệp vụ cần so sánh thời lượng.
- Dùng `timestamp()` khi cần thời điểm quan sát tuyệt đối; dùng timestamp trong payload khi cần thời điểm nghiệp vụ.
- Dùng `timed()` khi cần đồng thời khoảng cách, timestamp và thời gian từ subscription.
- Không nhầm đo khoảng cách với trì hoãn (`delayElements`), phát hiện quá hạn (`timeout`) hoặc tạo nhịp (`interval`).
- Không dùng `elapsed()` để đo thời gian xử lý từng phần tử hoặc tổng thời gian subscription.
- Dùng `System.nanoTime()` hoặc công cụ đo thời gian phù hợp cho thời lượng xử lý; dùng `doFinally` để đo vòng đời đến complete, error hoặc cancel.
- Dùng `StepVerifier.withVirtualTime` để kiểm thử thời gian mà không phụ thuộc `Thread.sleep`.
- Nếu đo luồng đã hợp nhất nhiều thực thể, cân nhắc nhóm theo khóa trước khi đo để không trộn nhịp của các thực thể khác nhau.

Khi đặt đúng ranh giới và hiểu rõ ý nghĩa của từng mốc, `elapsed()` cung cấp một cách đơn giản để quan sát nhịp phát của `Flux` hoặc `Mono`. Kết hợp nó với `timestamp`, `timed`, scheduler và kiểm thử thời gian ảo giúp phân biệt độ trễ giữa tín hiệu, thời điểm quan sát và thời gian xử lý trong một pipeline reactive.
