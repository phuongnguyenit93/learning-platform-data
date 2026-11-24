# Điều chỉnh nạp trước, kích thước lô và bộ đệm

Một pipeline reactive có thể chậm hoặc tiêu thụ nhiều bộ nhớ dù từng operator riêng lẻ đều đơn giản. Nguyên nhân thường nằm ở cách dữ liệu được yêu cầu trước, gom thành lô và giữ trong hàng đợi giữa các bước. Nạp trước (prefetch) giúp một operator chuẩn bị dữ liệu cho downstream; batching gom nhiều phần tử thành một đơn vị xử lý; buffering giữ các phần tử đang chờ khi tốc độ producer và consumer khác nhau. Điều chỉnh ba yếu tố này giúp cân bằng throughput, latency và bộ nhớ trong ứng dụng Reactor.

Bài học thuộc chương **Hiệu năng** của module `REACTIVE_PROGRAMMING`. Module hướng dẫn tư duy reactive qua các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và cơ chế backpressure của Reactive Streams; người học thực hành `Mono`, `Flux`, kết hợp toán tử, kiểm soát scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java. Trọng tâm ở đây là hiểu prefetch và demand, chọn kích thước batch, kiểm soát queue và nhận biết khi buffering chỉ che giấu một consumer đang quá chậm.

Sau bài học, bạn có thể:

- Phân biệt demand downstream, prefetch của operator và capacity của buffer.
- Điều chỉnh `limitRate`, `publishOn` và `flatMap` theo tải thực tế.
- Chọn `buffer`, `bufferTimeout` hoặc `window` theo cách xử lý lô.
- Ước lượng bộ nhớ bị giữ bởi nhiều queue và inner Publisher.
- Chọn chính sách overflow phù hợp với nguồn nóng không tuân thủ demand.
- Nhận diện các cấu trúc dễ gây tích lũy bộ nhớ như `collectList`, unbounded buffer và group không được tiêu thụ.
- Đo throughput, latency và queueing để điều chỉnh thông số có căn cứ.

## 1. Demand, prefetch và buffer là ba khái niệm khác nhau

Reactive Streams dùng demand để subscriber báo số phần tử mà nó sẵn sàng nhận thông qua `Subscription.request(n)`. Backpressure truyền nhu cầu từ downstream về upstream, giúp nguồn có thể điều tiết tốc độ phát.

Trong một pipeline, operator có thể yêu cầu upstream trước một lượng phần tử để giữ cho downstream không phải chờ mỗi lần xử lý xong mới yêu cầu tiếp. Lượng yêu cầu trước này thường được gọi là **prefetch**. Phần tử đã được yêu cầu nhưng chưa được xử lý có thể nằm trong queue nội bộ của operator hoặc scheduler boundary.

**Buffer capacity** là sức chứa của một vùng lưu trữ. Nó có thể được cấu hình rõ ràng bằng `onBackpressureBuffer`, queue của `publishOn`, hoặc phát sinh từ cấu trúc gom lô. Capacity không đồng nghĩa với demand: một buffer có thể có chỗ trống nhưng upstream vẫn chưa được yêu cầu thêm dữ liệu, hoặc demand đã được phát nhưng dữ liệu đang chờ trong queue.

| Khái niệm | Ý nghĩa | Câu hỏi cần trả lời |
|---|---|---|
| Demand | Số phần tử downstream yêu cầu | Consumer đang sẵn sàng nhận bao nhiêu? |
| Prefetch | Số phần tử operator yêu cầu trước để xử lý liên tục | Operator cần chuẩn bị bao nhiêu phần tử? |
| Buffer capacity | Số phần tử có thể được giữ trong một queue/buffer | Khi consumer chậm, dữ liệu có thể chờ tối đa bao nhiêu? |
| Batch size | Số phần tử gom thành một lô | Mỗi lần gọi tầng xử lý hoặc ghi dữ liệu nên chứa bao nhiêu phần tử? |

Các thông số này có quan hệ nhưng không thể thay thế lẫn nhau. Tăng prefetch không làm consumer xử lý nhanh hơn; tăng batch size không tự tạo thêm demand; tăng buffer capacity chỉ cho phép giữ nhiều dữ liệu đang chờ hơn.

## 2. `limitRate`: chia nhỏ request upstream

`limitRate` điều tiết cách downstream demand được chuyển thành các request nhỏ hơn gửi upstream. Nó hữu ích khi subscriber phía sau yêu cầu một lượng lớn phần tử, nhưng ta muốn upstream nhận request theo từng đợt có giới hạn.

```java
Flux<Event> events = eventSource
    .limitRate(100);
```

Trong ví dụ, `limitRate(100)` giới hạn lượng request được phát lên upstream theo từng đợt high-tide. Operator có thể yêu cầu thêm trước khi toàn bộ đợt đã được tiêu thụ, dựa trên low-tide/replenishment strategy.

Overload cho phép chỉ định cả high-tide và low-tide:

```java
Flux<Event> events = eventSource
    .limitRate(100, 25);
```

- `highTide=100`: kích thước đợt request tối đa được yêu cầu upstream.
- `lowTide=25`: khi số phần tử còn lại xuống ngưỡng replenishment, operator yêu cầu thêm để duy trì lượng dữ liệu sẵn sàng.

Nếu đặt `lowTide=0`, operator yêu cầu theo các đợt nghiêm ngặt hơn: đợi đợt hiện tại được tiêu thụ hết rồi mới yêu cầu đợt tiếp theo. Cách này có thể giảm lượng phần tử được giữ trước nhưng làm tăng khoảng chờ giữa các đợt nếu upstream phản hồi chậm.

`limitRate` không phải giới hạn tốc độ theo thời gian. Nó không có nghĩa “100 phần tử mỗi giây”; nó điều chỉnh kích thước request theo demand. Nếu cần giới hạn tốc độ phát, hãy xem các toán tử như `limitRequest`, `delayElements`, `sample` hoặc cơ chế rate limiter phù hợp với yêu cầu.

## 3. Prefetch của `publishOn`

`publishOn` tạo ranh giới xử lý tín hiệu downstream trên scheduler đã chọn. Để worker có thể xử lý liên tục, operator yêu cầu trước một số phần tử từ upstream và giữ các phần tử đang chờ trong queue.

```java
Flux<Result> results = source
    .publishOn(Schedulers.parallel(), 32)
    .map(this::cpuBoundTransform);
```

Tham số `32` là prefetch của boundary trong ví dụ. Nó điều khiển lượng phần tử được yêu cầu trước và có thể được giữ chờ worker xử lý. Giá trị phù hợp phụ thuộc vào kích thước payload, thời gian xử lý mỗi phần tử và tốc độ upstream.

Prefetch lớn có thể:

- Giữ worker bận hơn khi upstream có độ trễ phát tín hiệu.
- Hấp thụ burst ngắn và giảm số lần request nhỏ.
- Tăng số phần tử nằm trong queue, kéo theo bộ nhớ và latency chờ.

Prefetch nhỏ có thể:

- Giảm lượng dữ liệu đang chờ trong boundary.
- Làm pipeline nhạy hơn với độ trễ giữa các lần request.
- Giảm throughput nếu worker thường xuyên hết dữ liệu để xử lý.

Một pipeline có nhiều `publishOn` có thể có nhiều queue độc lập. Nếu mỗi boundary giữ tối đa một lượng phần tử đáng kể, tổng số phần tử đang chờ có thể lớn hơn nhiều so với prefetch của một operator đơn lẻ.

Không nên thêm `publishOn` chỉ để tăng prefetch. Hãy tạo scheduler boundary khi cần thay đổi execution context; điều chỉnh prefetch là bước tinh chỉnh sau khi đã xác định đúng vị trí chuyển lịch.

## 4. Prefetch và concurrency của `flatMap`

`flatMap` có hai thông số thường được điều chỉnh:

```java
Flux<Detail> details = ids
    .flatMap(id -> client.fetchDetail(id), 16, 8);
```

- `concurrency=16`: giới hạn số inner Publisher được subscribe đồng thời.
- `prefetch=8`: lượng phần tử yêu cầu trước từ mỗi inner Publisher.

Với inner Publisher nhiều phần tử, lượng dữ liệu có thể được yêu cầu và giữ lại phụ thuộc vào cả concurrency lẫn prefetch. Ví dụ trên có thể duy trì đến 16 inner Publisher; mỗi inner có thể có lượng dữ liệu đang chờ riêng. Đây không phải cam kết rằng luôn có đúng `16 × 8` phần tử trong bộ nhớ, nhưng tích số đó là một cách ước lượng sơ bộ cho phần dữ liệu được prefetch từ các inner.

Nếu mapper trả về `Mono` chỉ phát tối đa một phần tử, prefetch của inner ít ảnh hưởng hơn so với trường hợp mỗi inner là một `Flux` dài. Nếu mapper trả về stream nhiều phần tử, cần xem xét cả concurrency và prefetch.

### Concurrency không phải batch size

`flatMap(..., concurrency)` giới hạn số inner Publisher đang hoạt động. Nó không gom các phần tử nguồn thành một danh sách và không bảo đảm mỗi inner nhận một batch cố định.

Nếu muốn gửi dữ liệu theo lô, dùng `buffer` trước bước xử lý:

```java
Flux<WriteResult> writes = events
    .buffer(100)
    .flatMap(batch -> repository.writeBatch(batch), 4);
```

Pipeline này tạo batch tối đa 100 sự kiện, sau đó cho phép tối đa 4 thao tác ghi batch hoạt động đồng thời. Đây là hai giới hạn khác nhau: batch size điều khiển số phần tử mỗi lần ghi; concurrency điều khiển số lần ghi đồng thời.

## 5. Gom dữ liệu bằng `buffer`

`buffer(maxSize)` gom tối đa `maxSize` phần tử thành một `List` rồi phát danh sách đó xuống downstream. Khi nguồn hoàn tất, batch cuối chưa đủ kích thước vẫn được phát nếu có phần tử.

```java
Flux<List<Event>> batches = eventSource
    .buffer(100);
```

Với 235 sự kiện, kết quả là hai batch 100 phần tử và một batch 35 phần tử. `buffer` không chờ đủ 100 phần tử mãi mãi sau khi nguồn hoàn tất; batch cuối được phát khi nhận `onComplete`.

Ví dụ ghi batch vào repository:

```java
Flux<BatchResult> results = eventSource
    .buffer(100)
    .concatMap(repository::writeBatch);
```

`concatMap` xử lý từng batch theo thứ tự, đợi batch trước hoàn tất rồi mới xử lý batch sau. Nếu các batch độc lập và repository chịu được ghi đồng thời, có thể dùng `flatMap` với concurrency giới hạn:

```java
Flux<BatchResult> results = eventSource
    .buffer(100)
    .flatMap(repository::writeBatch, 4);
```

Đổi từ `concatMap` sang `flatMap` thay đổi thứ tự và concurrency. Chỉ làm vậy khi nghiệp vụ cho phép các batch hoàn tất không theo thứ tự.

### Kích thước batch ảnh hưởng latency và throughput

Batch lớn thường giảm số lần gọi repository hoặc remote API, tăng hiệu quả xử lý theo lô. Nhưng nó cũng có thể:

- Làm phần tử đầu tiên phải chờ lâu hơn để batch đủ kích thước.
- Tăng bộ nhớ vì mỗi batch giữ nhiều payload hơn.
- Tăng thời gian xử lý và retry khi một batch lỗi.
- Tăng kích thước transaction hoặc câu lệnh database đến mức vượt giới hạn hệ thống.

Batch nhỏ giảm thời gian chờ và bộ nhớ mỗi batch, nhưng làm tăng số lần gọi và overhead cố định. Hãy đo với payload và dependency thực tế thay vì chọn một con số lớn theo cảm tính.

## 6. `bufferTimeout`: đóng batch theo kích thước hoặc thời gian

Trong luồng liên tục, `buffer(100)` có thể không phát batch nếu nguồn chỉ phát 20 phần tử rồi im lặng nhưng không hoàn tất. `bufferTimeout` giải quyết bằng cách đóng batch khi đủ số phần tử hoặc hết thời gian.

```java
Flux<List<Event>> batches = eventSource
    .bufferTimeout(100, Duration.ofMillis(500));
```

Một batch được phát khi đạt 100 phần tử hoặc khi đã chờ tối đa khoảng 500 ms theo timer của operator. Điều này cân bằng giữa batch đủ lớn và giới hạn thời gian chờ.

Ví dụ xử lý telemetry:

```java
Flux<WriteResult> writes = telemetry
    .bufferTimeout(250, Duration.ofSeconds(1))
    .concatMap(repository::insertMeasurements);
```

Nếu telemetry phát nhanh, batch đóng khi đạt 250 phần tử. Nếu phát chậm, batch đang có sẽ được phát khi timer đến hạn. Khi nguồn hoàn tất, phần tử còn lại được phát thành batch cuối.

`bufferTimeout` tạo thêm yếu tố thời gian vào pipeline. Trong kiểm thử, nên dùng virtual time khi cần xác nhận batch đóng theo timeout mà không chờ đồng hồ thực. Cũng cần kiểm tra scheduler/timer được dùng theo overload và phiên bản Reactor trong dự án.

### Overlapping và gapped buffer

Một số overload `buffer` cho phép chỉ định `maxSize` và `skip`:

```java
Flux<List<Integer>> overlapping = Flux.range(1, 6)
    .buffer(3, 1);
```

Với `maxSize=3` và `skip=1`, một phần tử mới mở batch mới trong khi các batch trước vẫn có thể đang thu thập. Kết quả có các batch chồng lấp như `[1,2,3]`, `[2,3,4]`, `[3,4,5]`... tùy thời điểm đóng.

Nếu `skip` lớn hơn `maxSize`, sẽ có khoảng cách giữa các batch và một số phần tử không thuộc batch nào. Overlap có thể nhân số lần một phần tử xuất hiện trong các batch, làm tăng bộ nhớ và chi phí xử lý. Chỉ dùng khi nghiệp vụ thực sự cần cửa sổ trượt.

## 7. `window`: chia thành các luồng con thay vì List

`window` có mục tiêu gần với `buffer`, nhưng thay vì phát `List<T>`, nó phát `Flux<T>` đại diện cho từng nhóm:

```java
Flux<Flux<Event>> windows = eventSource
    .window(100);
```

Mỗi window là một Publisher con. Có thể xử lý từng window bằng operator reactive:

```java
Flux<Summary> summaries = eventSource
    .window(100)
    .concatMap(window -> window
        .reduce(Summary.empty(), Summary::add));
```

`window` hữu ích khi cần biến đổi hoặc tổng hợp dữ liệu theo nhóm mà không nhất thiết phải tạo `List` trước. Tuy nhiên, Publisher con cần được subscribe và tiêu thụ đúng cách. Nếu tạo nhiều window nhưng xử lý không kịp, các phần tử và subscription con có thể tiếp tục giữ tài nguyên hoặc tích lũy backlog.

| Tiêu chí | `buffer` | `window` |
|---|---|---|
| Kiểu phần tử phát ra | `List<T>` | `Flux<T>` |
| Cách xử lý | Có sẵn collection để gọi API batch | Có thể áp dụng operator reactive trong từng nhóm |
| Bộ nhớ | Giữ phần tử trong collection đến khi batch đóng | Quản lý các Publisher con và dữ liệu chờ theo vòng đời window |
| Phù hợp | API database nhận danh sách, bulk write | Tổng hợp reactive, xử lý theo nhóm bằng operator |

Nếu API downstream bắt buộc nhận một danh sách, `buffer` thường đơn giản hơn. Nếu cần tiếp tục xử lý reactive trong từng nhóm, `window` có thể biểu đạt tốt hơn.

## 8. Buffer cho nguồn nóng và chính sách overflow

Một nguồn tuân thủ Reactive Streams có thể điều chỉnh tốc độ phát theo demand. Nhưng một số nguồn nóng hoặc callback API có thể phát sự kiện mà không chờ consumer yêu cầu. Khi đó, cần quyết định điều gì xảy ra nếu producer nhanh hơn consumer.

Reactor có các operator như:

- `onBackpressureBuffer`: giữ phần tử đang đến trong buffer.
- `onBackpressureDrop`: bỏ phần tử khi downstream không yêu cầu kịp.
- `onBackpressureLatest`: chỉ giữ giá trị mới nhất trong lúc downstream chậm.
- `onBackpressureError`: phát lỗi khi nguồn phát vượt quá demand.

Ví dụ buffer có giới hạn:

```java
Flux<SensorEvent> events = hotSensorSource
    .onBackpressureBuffer(
        1_000,
        dropped -> metrics.increment("sensor.buffer.evicted")
    );
```

Khi buffer đạt giới hạn và không thể nhận thêm, overload có callback overflow có thể báo lỗi theo semantics của operator. Cần chọn overload phù hợp với hành vi khi đầy và xác minh API của phiên bản Reactor đang dùng.

Nếu dữ liệu cũ không còn giá trị khi đã có dữ liệu mới hơn, `onBackpressureLatest` có thể phù hợp:

```java
Flux<DashboardReading> latestReadings = hotDashboardSource
    .onBackpressureLatest();
```

Với telemetry dùng để hiển thị trạng thái hiện tại, bỏ các mẫu trung gian có thể chấp nhận được. Với giao dịch tài chính hoặc audit log, drop dữ liệu thường không chấp nhận được; cần lưu bền vững, giới hạn producer hoặc phát lỗi để báo quá tải.

### Tránh buffer không giới hạn

`onBackpressureBuffer()` không có capacity hữu hạn có thể giữ ngày càng nhiều phần tử nếu producer liên tục nhanh hơn consumer. Điều đó biến backpressure thành tích lũy bộ nhớ và cuối cùng có thể gây `OutOfMemoryError`.

Hãy đặt capacity có căn cứ và định nghĩa rõ chính sách khi đầy: fail, drop, latest hoặc lưu vào một hệ thống bền vững. Không dùng buffer như cách che giấu một consumer chậm trong thời gian dài.

## 9. `collectList` và các thao tác gom toàn bộ nguồn

`collectList()` gom toàn bộ phần tử của `Flux` vào một `List` và chỉ phát list khi nguồn hoàn tất:

```java
Mono<List<Event>> allEvents = eventSource.collectList();
```

Điều này phù hợp với nguồn hữu hạn, có kích thước biết trước và giới hạn rõ. Với nguồn vô hạn hoặc stream lâu dài, `collectList` không phát kết quả và giữ phần tử ngày càng nhiều trong bộ nhớ.

Nếu chỉ cần xử lý theo batch, không gom toàn bộ nguồn:

```java
Flux<WriteResult> writes = eventSource
    .buffer(500)
    .concatMap(repository::writeBatch);
```

Đoạn code này giữ từng batch rồi giải phóng khi batch được xử lý, thay vì đợi toàn bộ nguồn hoàn tất. Tuy nhiên, nếu downstream xử lý batch chậm và upstream/buffer khác tiếp tục tích lũy, vẫn cần kiểm soát demand và queue ở các tầng khác.

## 10. Ước lượng bộ nhớ đang chờ

Một cách ước lượng đơn giản là nhân số phần tử có thể được giữ với kích thước trung bình của payload, sau đó cộng overhead của object, queue và cấu trúc quản lý.

Giả sử một pipeline có:

- Một `publishOn` với prefetch 64.
- `flatMap` concurrency 8, mỗi inner prefetch 16.
- Một batch đang được tạo với tối đa 100 phần tử.

Ước lượng thô số phần tử có thể đang được giữ ở các tầng là:

\[
64 + (8 \times 16) + 100 = 292\text{ phần tử}
\]

Nếu payload trung bình chiếm khoảng 2 KB, phần payload thô đã khoảng 584 KB, chưa tính object header, reference, queue node, buffer collection và dữ liệu tạm trong operator. Đây chỉ là ước lượng để thấy các vùng đệm cộng dồn; số phần tử thực tế phụ thuộc demand, fusion, nguồn, thời điểm xử lý và operator cụ thể.

Khi có nhiều subscription đồng thời, cần nhân theo số pipeline đang hoạt động. Ví dụ 200 request cùng có thể giữ lượng dữ liệu tương tự thì tổng bộ nhớ chờ có thể lớn hơn nhiều lần một request.

### Công thức suy nghĩ về capacity

```text
Tổng bộ nhớ chờ xấp xỉ
  = số phần tử đang chờ
    × kích thước payload trung bình
    + overhead của queue / collection / object
```

Để đặt capacity, hãy biết:

- Kích thước payload trung bình và trường hợp lớn nhất.
- Số subscription đồng thời.
- Prefetch của từng boundary.
- Concurrency và prefetch của từng inner Publisher.
- Batch size và số batch đang hoạt động.
- Thời gian consumer có thể chậm hơn producer.

## 11. Backpressure không thay thế giới hạn tài nguyên bên ngoài

Backpressure giúp điều tiết số phần tử được yêu cầu giữa Publisher và Subscriber. Nó không tự giới hạn mọi tài nguyên khác như số kết nối database, số request HTTP đang mở, kích thước file hoặc số transaction đồng thời.

Ví dụ, `flatMap(..., 100)` có thể tạo tối đa 100 inner Publisher trong một subscription. Nếu mỗi inner mở một connection, pool database vẫn cần đủ capacity hoặc cần giới hạn concurrency thấp hơn. Nếu nhiều request cùng chạy pipeline, tổng số inner còn có thể lớn hơn.

Hãy kết hợp:

- Demand/backpressure để điều tiết phần tử trong stream.
- Concurrency giới hạn để kiểm soát số inner operation.
- Bulkhead hoặc semaphore dùng chung để giới hạn dependency ở phạm vi process.
- Connection pool và timeout để giới hạn tài nguyên transport.
- Queue có giới hạn và chính sách overflow để tránh backlog không kiểm soát.

Không dùng một con số prefetch để thay thế việc tính capacity của connection pool hoặc bulkhead.

## 12. Chọn kích thước batch theo mục tiêu

Không có một batch size tối ưu cho mọi pipeline. Kích thước phù hợp phụ thuộc chi phí cố định mỗi lần gọi, giới hạn của dependency, kích thước payload và latency mà người dùng chấp nhận.

| Tình huống | Hướng điều chỉnh ban đầu | Điều cần đo |
|---|---|---|
| Ghi database theo lô | Batch vừa phải, xử lý tuần tự hoặc concurrency thấp | Thời gian transaction, lock, throughput và lỗi batch. |
| Gửi HTTP bulk API | Theo giới hạn payload và API quota | Request size, response latency, rate limit. |
| Telemetry liên tục | `bufferTimeout` để giới hạn cả size và thời gian chờ | Độ trễ mẫu đầu tiên, số batch/giây, batch size trung bình. |
| Dashboard chỉ cần trạng thái mới nhất | Có thể dùng latest/drop | Tỷ lệ mẫu bỏ và độ trễ hiển thị. |
| Audit hoặc giao dịch không được mất | Không drop; queue hữu hạn hoặc lưu bền vững | Overflow, backlog, durability và tốc độ phục hồi. |

Quy trình điều chỉnh nên bắt đầu từ một giá trị bảo thủ, đo tải đại diện, tăng/giảm từng thông số một và so sánh kết quả. Nếu thay batch size, prefetch và concurrency cùng lúc, sẽ khó xác định yếu tố nào làm latency hoặc bộ nhớ thay đổi.

## 13. Đo throughput, latency và backlog

Chỉ nhìn số phần tử xử lý mỗi giây là chưa đủ. Một pipeline có throughput cao nhưng giữ queue lớn có thể có latency rất cao và tăng bộ nhớ theo thời gian.

Nên theo dõi ít nhất:

- **Throughput:** số phần tử hoặc batch xử lý mỗi giây.
- **End-to-end latency:** thời gian từ lúc phần tử được tạo đến khi kết quả được xử lý.
- **Queue depth/backlog:** số phần tử đang chờ ở các boundary hoặc ingress buffer.
- **In-flight operations:** số inner Publisher hoặc request dependency đang hoạt động.
- **Batch size thực tế:** số phần tử trung bình, p95 và số batch đóng do timeout.
- **Overflow/drop:** số phần tử bị bỏ hoặc số lần buffer đầy.
- **Memory/GC:** heap sử dụng, allocation rate và pause time.

Nếu throughput không tăng nhưng queue tăng liên tục, consumer có thể đang là bottleneck. Tăng prefetch hoặc buffer chỉ kéo dài thời gian trước khi đầy. Hãy tối ưu bước xử lý chậm, giới hạn producer, tăng capacity thực sự hoặc áp dụng chính sách giảm tải.

### Một ví dụ đo thời gian batch

```java
Flux<WriteResult> writes = events
    .bufferTimeout(200, Duration.ofMillis(300))
    .flatMap(batch -> {
        long started = System.nanoTime();
        return repository.writeBatch(batch)
            .doFinally(signal -> {
                long elapsed = System.nanoTime() - started;
                metrics.recordBatch(batch.size(), elapsed, signal);
            });
    }, 3);
```

Ví dụ minh họa việc ghi nhận kích thước batch, thời gian xử lý và terminal signal. Trong production, nên dùng Micrometer timer/distribution summary hoặc instrumentation thống nhất thay vì tự ghi metric bằng một hàm chung không có tag/cardinality kiểm soát.

## 14. Kiểm thử batching và demand

`StepVerifier` giúp xác nhận batch được phát theo kích thước và batch cuối khi nguồn hoàn tất:

```java
StepVerifier.create(
        Flux.range(1, 7).buffer(3)
    )
    .expectNext(List.of(1, 2, 3))
    .expectNext(List.of(4, 5, 6))
    .expectNext(List.of(7))
    .verifyComplete();
```

### Kiểm thử `bufferTimeout` với virtual time

```java
StepVerifier.withVirtualTime(() ->
        Flux.concat(
            Flux.just(1, 2),
            Flux.never()
        ).bufferTimeout(3, Duration.ofSeconds(1))
    )
    .thenAwait(Duration.ofSeconds(1))
    .expectNext(List.of(1, 2))
    .thenCancel()
    .verify();
```

Hai phần tử không đủ batch size 3, nhưng timer đóng batch sau một giây. Nguồn `never` không hoàn tất nên test chủ động cancel sau khi xác nhận batch. Virtual time cần được cấu hình đúng cho scheduler mà operator sử dụng; hãy tạo pipeline trong supplier của `withVirtualTime`.

### Kiểm thử `limitRate` theo request

Có thể quan sát demand upstream bằng `doOnRequest`:

```java
AtomicLong requested = new AtomicLong();

Flux<Integer> source = Flux.range(1, 20)
    .doOnRequest(requested::addAndGet)
    .limitRate(5, 0);

StepVerifier.create(source, 0)
    .thenRequest(3)
    .expectNext(1, 2, 3)
    .thenRequest(2)
    .expectNext(4, 5)
    .thenCancel()
    .verify();
```

Trong kiểm thử này, `limitRate` chia demand thành các đợt upstream có high-tide 5 và low-tide 0. Hãy quan sát request thực tế bằng log hoặc `doOnRequest`; đừng giả định tổng `requested` luôn bằng số phần tử downstream đã nhận, vì operator có thể prefetch theo đợt.

### Kiểm thử drop hoặc overflow

Với nguồn nóng, dùng `TestPublisher` để điều khiển phát dữ liệu và xác nhận chính sách overflow. Kiểm thử nên bao gồm buffer đầy, phần tử bị drop, lỗi overflow và cancellation. Không dựa vào sleep để tạo race; điều khiển demand và phát sự kiện tường minh giúp kết quả lặp lại được.

## 15. Những lỗi thường gặp

| Cách làm sai | Hậu quả | Cách xử lý |
|---|---|---|
| Tăng prefetch để sửa consumer chậm | Queue lớn hơn nhưng throughput không tăng; latency và heap tăng. | Tìm bước bottleneck và điều tiết producer. |
| Xem `limitRate` là rate limiter theo giây | Hiểu sai cơ chế request theo demand. | Dùng rate limiter hoặc thời gian hóa nguồn nếu cần giới hạn tốc độ. |
| Nhầm `flatMap` concurrency với batch size | Giới hạn sai số request hoặc số phần tử mỗi lần ghi. | Dùng `buffer` cho batch, concurrency cho số inner operation. |
| Dùng `collectList` với nguồn vô hạn | Không hoàn tất và giữ dữ liệu tăng liên tục. | Xử lý theo `buffer` hoặc `window` có giới hạn. |
| Dùng unbounded backpressure buffer | Có thể dẫn đến cạn heap khi producer nhanh hơn consumer lâu dài. | Dùng capacity hữu hạn và chính sách overflow. |
| Tạo batch lớn mà không đo latency | Phần tử đầu tiên chờ lâu và batch lỗi tốn kém hơn. | Cân bằng size với timeout và SLO. |
| Dùng `window` nhưng không tiêu thụ inner Publisher | Các nhóm không được xử lý đúng, backlog hoặc tài nguyên có thể bị giữ. | Subscribe/flatten từng window bằng operator phù hợp. |
| Chỉ đo throughput | Bỏ qua queue depth, tail latency và GC. | Theo dõi latency, backlog, memory và overflow cùng throughput. |
| Cộng các capacity riêng lẻ mà không xét concurrency | Đánh giá thấp bộ nhớ của nhiều request đồng thời. | Ước lượng theo số pipeline đang hoạt động và payload thực tế. |

## 16. Checklist điều chỉnh prefetch, batch và buffer

Trước khi đưa thông số vào production, hãy xác nhận:

- Nguồn có tuân thủ Reactive Streams demand hay là nguồn nóng/push?
- Operator nào đang prefetch và có bao nhiêu boundary/inner Publisher?
- `limitRate` có cần chia nhỏ request upstream không?
- `flatMap` concurrency có phù hợp với capacity dependency không?
- Batch size có phù hợp với giới hạn API/database và latency mục tiêu không?
- Có cần đóng batch theo timeout khi nguồn phát chậm không?
- Buffer có giới hạn hữu hạn và chính sách overflow rõ ràng không?
- Có nguy cơ giữ toàn bộ nguồn bằng `collectList` hoặc group không được tiêu thụ không?
- Tổng lượng dữ liệu đang chờ đã được ước lượng theo payload và số subscription chưa?
- Đã đo throughput, p95/p99 latency, queue depth, in-flight calls, heap và GC chưa?
- Kiểm thử đã xác nhận batch cuối, timeout, demand, overflow, drop và cancellation chưa?

Prefetch giúp operator duy trì công việc liên tục; batch size quyết định lượng dữ liệu xử lý trong mỗi lần gọi; buffer hấp thụ chênh lệch tốc độ trong một giới hạn nhất định. Điều chỉnh hiệu năng tốt cần xem chúng như một hệ thống: demand, concurrency, queue và kích thước payload cùng quyết định throughput, latency và bộ nhớ. Khi có capacity hữu hạn, chính sách overflow rõ ràng và số liệu đo đại diện, pipeline `Flux` có thể xử lý burst ổn định mà không che giấu một consumer đang quá tải.
