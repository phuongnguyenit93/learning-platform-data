# Vị trí nhiều điểm chuyển bộ lập lịch và chi phí chuyển ngữ cảnh

Trong một pipeline Reactor, việc chuyển sang scheduler khác có thể giúp tách công việc blocking khỏi event loop, đưa phép tính CPU sang nhóm thread phù hợp hoặc gom thao tác cập nhật vào một luồng xử lý riêng. Tuy nhiên, mỗi điểm chuyển lịch cũng tạo thêm công việc điều phối. Nếu đặt `publishOn` liên tục mà không có lý do rõ ràng, pipeline có thể tốn thời gian đưa tín hiệu qua hàng đợi, lập lịch task và chuyển giữa các thread mà không tăng được năng lực xử lý.

Bài học thuộc chương **Luồng thực thi** của module `REACTIVE_PROGRAMMING`. Module hướng dẫn tư duy reactive qua các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và cơ chế backpressure của Reactive Streams; người học thực hành `Mono`, `Flux`, kết hợp toán tử, điều khiển scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java. Trọng tâm ở đây là vị trí đặt nhiều ranh giới scheduler, sự khác nhau giữa `publishOn` và `subscribeOn`, cùng chi phí thực tế của việc chuyển ngữ cảnh.

Sau bài học, bạn có thể:

- Dự đoán phần nào của pipeline chạy trên scheduler nào khi có nhiều `publishOn`.
- Giải thích vì sao `subscribeOn` không tạo ranh giới chuyển thread cho từng toán tử downstream.
- Nhận diện các điểm chuyển lịch thừa và tác động đến latency, throughput, bộ nhớ.
- Phân biệt việc Reactor chuyển task giữa worker với context switch ở cấp hệ điều hành.
- Đặt ranh giới scheduler quanh công việc blocking, CPU-bound và thao tác cần thứ tự.
- Kiểm tra thread thực thi và hành vi pipeline mà không dựa vào giả định về tên thread.

## 1. Scheduler boundary là gì?

Scheduler quyết định nơi một phần công việc reactive được thực thi. Trong Reactor, hai toán tử thường dùng để điều khiển scheduler là:

- `subscribeOn(scheduler)`: điều phối quá trình subscribe và các yêu cầu upstream trên scheduler được chọn. Nó chủ yếu quyết định nơi nguồn được subscribe.
- `publishOn(scheduler)`: tạo ranh giới thực thi cho các tín hiệu đi xuống phía sau toán tử. Các toán tử downstream tiếp theo chạy trên worker của scheduler đó cho đến khi có ranh giới khác thay đổi nơi thực thi.

Ví dụ:

```java
Flux<Integer> values = Flux.range(1, 3)
    .map(value -> decode(value))
    .publishOn(Schedulers.parallel())
    .map(value -> calculate(value))
    .publishOn(Schedulers.single())
    .map(value -> updateViewModel(value));
```

Có hai ranh giới `publishOn`:

1. Trước `calculate`: tín hiệu downstream được chuyển sang worker của `Schedulers.parallel()`.
2. Trước `updateViewModel`: tín hiệu được chuyển sang worker của `Schedulers.single()`.

`decode` nằm trước ranh giới đầu tiên nên chạy trên thread phát tín hiệu upstream. `calculate` chạy sau ranh giới thứ nhất. `updateViewModel` chạy sau ranh giới thứ hai.

Một ranh giới scheduler không nhất thiết đồng nghĩa với việc tên thread luôn thay đổi. Scheduler có thể cấp worker dùng cùng một thread nền, hoặc worker mới có thể được thực thi trên thread đã dùng trước đó. Điều được bảo đảm là nơi thực thi downstream được điều phối qua scheduler đã chọn, không phải mỗi tín hiệu chắc chắn chuyển sang một thread hệ điều hành khác.

## 2. Nhiều `publishOn`: mỗi vị trí ảnh hưởng phần downstream

Mỗi `publishOn` có hiệu lực từ vị trí của nó trở đi. Vì vậy, khi có nhiều điểm chuyển lịch, hãy đọc pipeline từ trên xuống và xác định vùng thực thi giữa hai ranh giới.

```java
Flux<Result> results = source
    .map(this::parse)                              // Vùng A
    .publishOn(Schedulers.parallel())              // Ranh giới 1
    .map(this::calculate)                          // Vùng B
    .filter(this::isRelevant)
    .publishOn(Schedulers.boundedElastic())         // Ranh giới 2
    .map(this::callBlockingLegacyService)           // Vùng C
    .publishOn(Schedulers.single())                 // Ranh giới 3
    .doOnNext(this::updateLocalProjection);         // Vùng D
```

| Vùng | Toán tử | Scheduler thực thi |
|---|---|---|
| A | `parse` | Thread phát tín hiệu từ `source` hoặc scheduler đã được cấu hình upstream. |
| B | `calculate`, `isRelevant` | Worker của `Schedulers.parallel()`. |
| C | `callBlockingLegacyService` | Worker của `Schedulers.boundedElastic()`. |
| D | `updateLocalProjection` | Worker của `Schedulers.single()`. |

Các toán tử đồng bộ nằm giữa hai ranh giới thường dùng chung worker xử lý tín hiệu của vùng đó. Không cần đặt một `publishOn` trước mỗi `map` hoặc `filter`. Chỉ thêm ranh giới khi có lý do thay đổi execution context, chẳng hạn chuyển từ xử lý CPU sang API blocking hoặc sang một vùng cần tuần tự hóa.

### Ranh giới có thể hữu ích

- Trước một đoạn xử lý blocking để không chặn event loop.
- Trước một nhóm phép tính CPU-bound cần chạy trên scheduler dành cho CPU.
- Trước một vùng cập nhật trạng thái cần chạy tuần tự trên một worker.
- Sau một nguồn có thread callback riêng để đưa các tín hiệu tiếp theo về execution context mà ứng dụng kiểm soát.

### Ranh giới thường không cần thiết

- Giữa hai toán tử đồng bộ nhẹ chỉ vì muốn “tách” từng bước.
- Lặp lại cùng một `publishOn` giữa các `map` mà không có yêu cầu đổi execution context.
- Chuyển qua lại giữa nhiều scheduler cho một phép biến đổi nhỏ, khiến chi phí điều phối lớn hơn công việc thực tế.

## 3. `subscribeOn` không phân vùng từng đoạn xử lý

`subscribeOn` điều phối quá trình subscribe nguồn và các yêu cầu upstream. Vị trí của nó trong chuỗi không có ý nghĩa phân vùng downstream giống `publishOn`.

```java
Flux<Integer> values = Flux.range(1, 3)
    .doOnNext(value -> logThread("source", value))
    .subscribeOn(Schedulers.single())
    .map(value -> logAndReturn("map-1", value))
    .subscribeOn(Schedulers.boundedElastic())
    .map(value -> logAndReturn("map-2", value));
```

Trong ví dụ này, các `subscribeOn` có thể tạo thêm lần điều phối trong quá trình subscription/request. `subscribeOn` gần nguồn nhất quyết định scheduler nơi nguồn được subscribe. Nhưng chúng không tạo ra ranh giới `onNext` riêng để `map-1` chạy trên `single` còn `map-2` chạy trên `boundedElastic`. Khi nguồn phát đồng bộ, tín hiệu thường đi tiếp trên thread phát của nguồn cho đến `publishOn` đầu tiên.

Nếu mục tiêu là đưa một nguồn blocking sang `boundedElastic`, thường chỉ cần đặt một `subscribeOn` gần nguồn:

```java
Mono<LegacyRecord> record = Mono.fromCallable(
        () -> legacyClient.fetchRecord(recordId)
    )
    .subscribeOn(Schedulers.boundedElastic())
    .publishOn(Schedulers.parallel())
    .map(this::transform);
```

`fromCallable` trì hoãn việc gọi `fetchRecord` đến khi subscribe. `subscribeOn` đưa thao tác blocking đó sang `boundedElastic`. Khi kết quả phát ra, `publishOn` chuyển phần xử lý `transform` sang `parallel`.

Không thêm nhiều `subscribeOn` để cố gắng điều khiển từng đoạn `map`. Nếu cần thay đổi thread xử lý tín hiệu ở một vị trí cụ thể, dùng `publishOn` tại vị trí đó.

## 4. Chi phí của một scheduler boundary

Một ranh giới `publishOn` có thể tạo ra nhiều loại chi phí:

1. **Đưa tín hiệu vào hàng đợi:** tín hiệu upstream cần được chuyển giao cho worker downstream. Tùy operator và cấu hình, Reactor sử dụng queue/prefetch để đệm các phần tử.
2. **Lập lịch công việc:** worker cần được đánh thức hoặc nhận task để tiếp tục xử lý. Việc submit và dispatch task có chi phí dù thread nền đã tồn tại.
3. **Đồng bộ giữa các thread:** cơ chế chuyển giao phải bảo đảm visibility và phối hợp truy cập queue, trạng thái và demand.
4. **Chi phí cache và locality:** khi xử lý chuyển sang thread khác, dữ liệu nóng trong CPU cache có thể không còn thuận lợi như trước.
5. **Context switch ở cấp hệ điều hành:** nếu thread đang chạy bị thay bằng thread khác, hệ điều hành phải lưu và khôi phục trạng thái thực thi. Đây là một phần chi phí có thể xuất hiện, nhưng không phải mọi scheduler boundary đều gây một OS context switch.

Điểm cuối cần được hiểu chính xác: Reactor scheduling handoff và OS context switch không phải một khái niệm. `publishOn` tạo điểm chuyển giao công việc trong pipeline. Nếu worker tiếp tục chạy trên thread đang rảnh hoặc cùng thread nền, có thể không có lần chuyển thread hệ điều hành nào tại ranh giới đó. Dù vậy, queueing và scheduling vẫn có overhead.

Với một phép tính rất nhỏ như cộng hai số, chi phí chuyển lịch có thể lớn hơn chính phép tính. Với một thao tác blocking kéo dài hàng chục mili giây, chi phí chuyển lịch nhỏ thường đáng chấp nhận để bảo vệ event loop.

## 5. Nhiều boundary có thể tăng buffering và latency

`publishOn` có thể prefetch phần tử upstream vào hàng đợi để worker downstream xử lý. Overload cho phép chỉ định prefetch:

```java
Flux<Result> results = source
    .publishOn(Schedulers.parallel(), 32)
    .map(this::firstStage)
    .publishOn(Schedulers.boundedElastic(), 16)
    .map(this::secondStage);
```

Các con số `32` và `16` là giới hạn prefetch cho từng boundary trong ví dụ, không phải số phần tử mỗi giây và cũng không phải giới hạn tổng số phần tử toàn pipeline. Khi có nhiều boundary, mỗi boundary có thể giữ phần tử đang chờ của riêng nó. Điều đó ảnh hưởng đến:

- Số phần tử đang nằm trong bộ đệm ở các vùng khác nhau.
- Lượng bộ nhớ tiêu thụ khi payload lớn.
- Thời gian một phần tử chờ trước khi đến bước tiếp theo.
- Cách demand được truyền ngược qua các ranh giới.

Một pipeline có nhiều queue có thể hấp thụ burst ngắn, nhưng cũng có thể che giấu việc downstream chậm bằng cách tích lũy latency và bộ nhớ. Hãy chọn prefetch dựa trên kích thước payload, tốc độ xử lý, khả năng burst và giới hạn bộ nhớ; đừng tăng prefetch chỉ để làm số liệu throughput ngắn hạn đẹp hơn.

### Ví dụ về hàng đợi tích lũy

Giả sử nguồn phát 10.000 sự kiện/giây, vùng A xử lý 9.000/giây và vùng B chỉ xử lý 2.000/giây. Nếu giữa A và B có queue, phần tử sẽ tích lũy tại đó vì tốc độ đến lớn hơn tốc độ tiêu thụ. Thêm một `publishOn` nữa phía sau B không làm B xử lý nhanh hơn; nó có thể chỉ chuyển điểm tích lũy sang queue tiếp theo.

Khi thấy latency tăng, hãy tìm đoạn có tốc độ tiêu thụ thấp hơn tốc độ đầu vào, đo queue/prefetch và kiểm tra thời gian xử lý mỗi bước. Đừng mặc định rằng thêm scheduler sẽ giải quyết được nút thắt.

## 6. Chọn scheduler theo loại công việc

Chọn scheduler theo tính chất công việc và thời gian sống của nó:

| Scheduler | Dùng cho | Điều cần tránh |
|---|---|---|
| `Schedulers.parallel()` | Công việc CPU-bound, ngắn, không blocking. | Chờ I/O đồng bộ, sleep hoặc khóa lâu trên worker. |
| `Schedulers.boundedElastic()` | API blocking hoặc tác vụ có thể chờ I/O, với số thread được giới hạn. | Dùng như pool vô hạn hoặc chuyển mọi toán tử nhẹ sang đây. |
| `Schedulers.single()` | Một luồng xử lý tuần tự dùng chung. | Công việc blocking dài làm nghẽn mọi tác vụ dùng scheduler đó. |
| `Schedulers.immediate()` | Thực thi ngay trên thread gọi hiện tại. | Mong đợi chuyển thread hoặc bất đồng bộ. |

Ví dụ, một pipeline có thể đọc từ thư viện blocking, tính toán và cập nhật projection tuần tự:

```java
Mono<EnrichedOrder> enrichedOrder = Mono.fromCallable(
        () -> legacyOrderClient.load(orderId)
    )
    .subscribeOn(Schedulers.boundedElastic())
    .publishOn(Schedulers.parallel())
    .map(this::calculateRisk)
    .publishOn(Schedulers.single())
    .map(this::updateProjection);
```

Đây là ba execution context có chủ đích:

- Đọc dữ liệu blocking trên `boundedElastic`.
- Tính toán CPU trên `parallel`.
- Cập nhật projection theo một luồng tuần tự trên `single`.

Nếu `updateProjection` cũng là thao tác blocking, `single` có thể trở thành nút thắt. Nếu projection có thể được cập nhật đồng thời an toàn, không nhất thiết phải chuyển sang một scheduler single. Mỗi boundary phải xuất phát từ yêu cầu thực tế về blocking, CPU hoặc thứ tự.

## 7. Không chuyển qua lại giữa scheduler một cách máy móc

Một anti-pattern thường gặp là đặt `publishOn` trước và sau gần như mọi operator:

```java
Flux<Result> inefficient = source
    .publishOn(Schedulers.parallel())
    .map(this::parse)
    .publishOn(Schedulers.boundedElastic())
    .map(this::normalize)
    .publishOn(Schedulers.parallel())
    .filter(this::isValid)
    .publishOn(Schedulers.single())
    .map(this::format);
```

Nếu `normalize` không blocking và `parse`, `filter`, `format` đều là thao tác nhẹ, các lần chuyển lịch này có thể không mang lại lợi ích. Chúng tạo thêm handoff, queue và độ trễ.

Hãy gom các operator đồng bộ có cùng yêu cầu thực thi thành một vùng:

```java
Flux<Result> grouped = source
    .publishOn(Schedulers.parallel())
    .map(this::parse)
    .map(this::normalize)
    .filter(this::isValid)
    .publishOn(Schedulers.single())
    .map(this::format);
```

Ví dụ đã giảm số boundary và gom các bước CPU-bound cùng một vùng. Trong thực tế, nếu `format` không cần chạy tuần tự, thậm chí có thể bỏ boundary `single`. Hãy giữ số lần chuyển lịch tối thiểu để đáp ứng đúng yêu cầu của pipeline.

### Một scheduler dùng chung không có nghĩa một worker duy nhất

`Schedulers.parallel()` là scheduler pool dành cho công việc CPU-bound; nhiều subscription có thể được thực thi trên các worker khác nhau. `Schedulers.single()` là scheduler đơn luồng dùng chung. Cần phân biệt scheduler với worker: scheduler quản lý việc lập lịch và cấp worker, còn worker là execution context cụ thể nhận task. Không nên tự tạo scheduler mới cho mỗi phần tử hoặc mỗi request vì chi phí quản lý thread và vòng đời sẽ tăng mạnh.

## 8. Backpressure qua các ranh giới scheduler

Một `publishOn` không loại bỏ backpressure. Nó tạo vùng đệm và điều phối demand giữa upstream và downstream. Khi downstream tiêu thụ chậm, queue có giới hạn sẽ đầy dần; Reactor giảm yêu cầu upstream theo cơ chế prefetch/replenishment. Nếu nguồn không tuân thủ demand hoặc là nguồn push nóng, cần chính sách overflow phù hợp.

Ví dụ:

```java
Flux<Event> processed = hotEventSource
    .onBackpressureBuffer(256)
    .publishOn(Schedulers.parallel(), 64)
    .map(this::process);
```

`onBackpressureBuffer(256)` là chính sách buffer cho nguồn nóng trong ví dụ. Nó không bảo đảm pipeline chịu tải vô hạn: nếu nguồn tiếp tục nhanh hơn consumer, buffer có thể đầy và overflow theo semantics của toán tử. `publishOn(..., 64)` có prefetch riêng. Khi thiết kế, hãy tính tổng lượng dữ liệu có thể đang chờ ở nhiều tầng, đồng thời xác định điều gì xảy ra khi buffer đầy: báo lỗi, bỏ phần tử, giữ giá trị mới nhất hay lưu bền vững ở một tầng khác.

Không nên tăng số boundary để “tạo thêm backpressure”. Backpressure đến từ hợp đồng demand và các chính sách buffer/overflow, còn scheduler boundary chủ yếu thay đổi execution context và cách chuyển giao tín hiệu.

## 9. Kiểm tra vị trí thực thi bằng log thread

Trong quá trình phân tích, có thể ghi tên thread ở các điểm quan trọng:

```java
private <T> T trace(String stage, T value) {
    log.info("stage={} thread={} value={}",
        stage,
        Thread.currentThread().getName(),
        value
    );
    return value;
}

Flux<Integer> pipeline = Flux.range(1, 3)
    .map(value -> trace("before", value))
    .publishOn(Schedulers.parallel())
    .map(value -> trace("parallel", value))
    .publishOn(Schedulers.single())
    .map(value -> trace("single", value));
```

Log giúp quan sát vùng thực thi, nhưng không nên viết test phụ thuộc vào tên thread cụ thể như `parallel-1`. Tên thread có thể thay đổi theo môi trường, số worker và lịch chạy. Trong test, hãy xác minh dữ liệu, thứ tự, completion và cancellation; dùng log hoặc instrumentation để chẩn đoán thread khi cần.

### Kiểm thử hành vi pipeline

```java
StepVerifier.create(
        Flux.range(1, 3)
            .publishOn(Schedulers.parallel())
            .map(value -> value * 2)
            .publishOn(Schedulers.single())
            .map(value -> value + 1)
    )
    .expectNext(3, 5, 7)
    .verifyComplete();
```

Kiểm thử xác nhận các boundary không làm thay đổi kết quả hoặc thứ tự tín hiệu của pipeline. Nếu cần đo chi phí, hãy benchmark riêng với dữ liệu và tải đại diện; một bài test chức năng không thể chứng minh scheduler boundary nhanh hay chậm hơn trong production.

## 10. Reactor Context và ThreadLocal khi chuyển scheduler

Khi tín hiệu đi qua nhiều thread, `ThreadLocal` không tự động trở thành dữ liệu theo subscription. Ví dụ MDC logging hoặc một security context được giữ trong `ThreadLocal` có thể không xuất hiện như mong đợi sau `publishOn`.

Reactor cung cấp `Context` gắn với subscription để truyền metadata theo pipeline:

```java
Mono<String> greeting = Mono.deferContextual(context ->
        Mono.just("requestId=" + context.get("requestId"))
    )
    .publishOn(Schedulers.parallel())
    .contextWrite(context -> context.put("requestId", "req-42"));
```

`Context` không phụ thuộc vào một thread cụ thể và phù hợp để truyền metadata như request ID hoặc thông tin tracing. Nếu thư viện cũ chỉ đọc `ThreadLocal`, cần cấu hình cơ chế context propagation tương thích với phiên bản Reactor hoặc bridge rõ ràng. Không nên giả định chuyển scheduler sẽ tự sao chép mọi ThreadLocal.

## 11. Checklist tối ưu scheduler boundary

Trước khi thêm hoặc giữ một điểm chuyển lịch, hãy hỏi:

- Công việc trước và sau boundary có yêu cầu execution context khác nhau không?
- Đoạn nào thực sự blocking, đoạn nào CPU-bound, đoạn nào cần tuần tự?
- Có thể gom các operator đồng bộ vào cùng một vùng không?
- Có boundary nào chỉ chuyển qua lại giữa các scheduler mà không tạo lợi ích không?
- Prefetch và queue ở mỗi boundary có phù hợp với kích thước payload và tải burst không?
- Nhiều queue có làm tăng latency hoặc bộ nhớ đang chờ không?
- Scheduler có bị dùng sai mục đích, chẳng hạn blocking trên `parallel` hoặc `single` không?
- ThreadLocal/MDC có cần context propagation qua boundary không?
- Đã đo latency, throughput và mức sử dụng thread bằng tải đại diện chưa?

Một pipeline tốt thường có ít ranh giới scheduler nhưng mỗi ranh giới đều có lý do rõ ràng. `subscribeOn` giúp đặt nguồn vào execution context phù hợp; `publishOn` chuyển phần tín hiệu downstream tại vị trí được chọn. Khi gom các bước cùng loại công việc, kiểm soát prefetch và đo chi phí thực tế, bạn có thể tránh những lần handoff không cần thiết mà vẫn giữ được backpressure và thứ tự tín hiệu của Reactive Streams.
