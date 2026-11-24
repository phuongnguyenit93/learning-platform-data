# Giới hạn luồng, hàng đợi và hành vi khi tài nguyên thực thi đầy

Trong **REACTIVE_PROGRAMMING**, `Mono` và `Flux` mô tả luồng dữ liệu bất đồng bộ theo hợp đồng `Publisher–Subscriber`. Reactor dùng `Scheduler` để quyết định nơi các tác vụ được thực thi. Mỗi scheduler có giới hạn về số thread hoặc cách xếp hàng tác vụ; các toán tử như `publishOn`, `subscribeOn` và `flatMap` cũng có thể tạo ranh giới bất đồng bộ hoặc giữ dữ liệu đang chờ.

Khi tải tăng, thread có thể bận lâu, hàng đợi có thể đầy và scheduler có thể từ chối tác vụ mới. Nếu không hiểu rõ các giới hạn này, ứng dụng dễ tích tụ độ trễ, giữ quá nhiều dữ liệu trong bộ nhớ hoặc biến tình trạng quá tải thành một đợt retry làm hệ thống nặng hơn. Bài này phân biệt các loại hàng đợi, cách đặt giới hạn và cách thiết kế hành vi khi không còn chỗ thực thi.

## 1. Thread và queue giải quyết hai vấn đề khác nhau

Thread là năng lực thực thi công việc. Queue là nơi giữ công việc đã được gửi nhưng chưa đến lượt chạy.

- **Thread cap** giới hạn số tác vụ có thể chạy đồng thời trên một scheduler.
- **Queue capacity** giới hạn số tác vụ đang chờ được thực thi.
- **Concurrency của operator** giới hạn số Publisher con hoặc tác vụ logic đang hoạt động tại một bước trong pipeline.
- **Prefetch** điều chỉnh số phần tử mà một operator yêu cầu trước từ upstream.
- **Backpressure demand** là số phần tử downstream cho phép upstream phát.

Các giới hạn này không thay thế lẫn nhau. Ví dụ, giới hạn bốn thread không có nghĩa toàn pipeline chỉ giữ bốn phần tử. Nếu mỗi thread có queue lớn, rất nhiều tác vụ vẫn có thể chờ. Tương tự, `flatMap(..., 8)` giới hạn số inner Publisher đang hoạt động tại toán tử đó, nhưng không tự đặt giới hạn cho queue của HTTP client hoặc scheduler khác.

## 2. Ba loại hàng đợi cần phân biệt

Trong một pipeline thực tế, dữ liệu hoặc công việc có thể chờ ở nhiều nơi:

| Loại hàng đợi | Lưu gì? | Ví dụ | Điều khiển bằng |
|---|---|---|---|
| Queue của scheduler | Runnable hoặc task chờ thread thực thi | Tác vụ gửi qua `publishOn` hoặc `subscribeOn` | Cấu hình scheduler, thread cap, queue cap |
| Queue của operator | Phần tử dữ liệu đã được nhận nhưng chưa phát tiếp | Buffer của `publishOn`, inner queue trong `flatMap` | `prefetch`, `concurrency`, `limitRate`, chính sách backpressure |
| Queue của dependency | Request hoặc công việc chờ tài nguyên bên ngoài | Connection pool, HTTP client, driver database | Pool size, pending acquire limit, timeout, quota |

Ví dụ, `publishOn(scheduler, 64)` có thể yêu cầu và giữ trước dữ liệu ở queue của operator. Khi callback downstream chạy, nó cũng cần một task được scheduler thực thi. Nếu scheduler bận, task có thể phải chờ trong queue của scheduler. Sau đó, callback có thể tiếp tục chờ connection trong pool database. Đây là ba nơi chờ khác nhau với ba giới hạn khác nhau.

Khi điều tra độ trễ, hãy đo từng ranh giới. Chỉ nhìn vào số thread hoặc heap tổng thể không cho biết dữ liệu đang chờ ở scheduler, operator hay dependency.

## 3. Chọn scheduler theo loại công việc

Reactor cung cấp các scheduler thường dùng với mục đích khác nhau:

| Scheduler | Đặc điểm | Công việc phù hợp |
|---|---|---|
| `Schedulers.parallel()` | Pool thread cố định, hướng đến công việc không blocking | Tính toán CPU-bound, xử lý dữ liệu ngắn |
| `Schedulers.boundedElastic()` | Pool có khả năng mở rộng trong giới hạn và queue hữu hạn | Tích hợp API blocking hoặc tác vụ I/O cũ |
| `Schedulers.single()` | Một thread dùng chung | Công việc tuần tự, ngắn và không blocking |
| `Schedulers.immediate()` | Thực thi ngay trên thread gọi | Trường hợp cần thực thi trực tiếp, không tạo ranh giới thread |

Không nên dùng `parallel` để chạy thao tác blocking kéo dài. Một tác vụ blocking có thể chiếm thread cần phục vụ nhiều pipeline khác. Với API blocking, bọc lời gọi trong nguồn lazy rồi chuyển sang bounded elastic:

```java
Mono<Customer> customer = Mono.fromCallable(
        () -> legacyCustomerClient.load(customerId)
    )
    .subscribeOn(Schedulers.boundedElastic());
```

`fromCallable` trì hoãn lời gọi đến subscription. `subscribeOn` đưa việc subscribe và thực thi nguồn lên scheduler đã chọn. Chỉ thêm `subscribeOn` sau `Mono.just(legacyCall())` không thể chuyển lời gọi đã xảy ra ở assembly sang thread khác.

## 4. Bounded elastic giới hạn thread và tác vụ chờ

`Schedulers.boundedElastic()` là scheduler dùng chung được thiết kế cho công việc blocking. Nó có giới hạn số thread và giới hạn số tác vụ có thể xếp hàng theo thread. Các giá trị mặc định phụ thuộc phiên bản Reactor và cấu hình hệ thống; không nên giả định một con số mặc định giống nhau ở mọi ứng dụng.

Khi cần kiểm soát giới hạn rõ ràng cho một nhóm công việc, có thể tạo scheduler riêng:

```java
Scheduler legacyIo = Schedulers.newBoundedElastic(
    4,       // tối đa bốn thread backing
    100,     // giới hạn task chờ trên mỗi backing thread
    "legacy-io"
);

Mono<Response> response = Mono.fromCallable(
        () -> legacyClient.fetch(requestId)
    )
    .subscribeOn(legacyIo);
```

Trong ví dụ, scheduler có tối đa bốn thread backing và giới hạn queue task theo từng thread. Khi các thread đều bận và hàng đợi đã đạt giới hạn, scheduler không thể nhận thêm task. Cấu hình queue cap là giới hạn tác vụ đang chờ, không phải giới hạn số phần tử dữ liệu của toàn pipeline.

Scheduler tự tạo bằng `newBoundedElastic` thuộc quyền sở hữu của ứng dụng. Khi thành phần sở hữu scheduler dừng và không còn công việc hợp lệ cần chạy, hãy gọi `dispose()` để giải phóng thread và tài nguyên liên quan. Ví dụ, một component có thể gắn việc này vào lifecycle hook dừng ứng dụng:

```java
void onApplicationShutdown() {
    legacyIo.dispose();
}
```

Không tạo scheduler mới cho từng phần tử hoặc từng request. Việc đó làm tăng số pool, thread và queue, khiến giới hạn khó kiểm soát. Thông thường, tạo scheduler theo nhóm công việc ở cấp thành phần ứng dụng, tái sử dụng nó và dispose khi thành phần dừng.

## 5. Scheduler bão hòa thì điều gì xảy ra?

Một scheduler có thể từ chối task khi:

- Đã đạt giới hạn thread và queue không còn chỗ nhận thêm task.
- Scheduler đã bị dispose.
- Executor bên dưới từ chối task vì chính sách hoặc tài nguyên của nó.

Với bounded elastic, khi queue đạt giới hạn, tác vụ mới có thể bị từ chối; Reactor thường biểu diễn tình trạng này bằng `RejectedExecutionException` hoặc tín hiệu lỗi tại ranh giới scheduling. Chi tiết cụ thể phụ thuộc loại scheduler, cách gọi API và phiên bản implementation.

Sơ đồ minh họa một scheduler có một thread và queue chỉ nhận hai task chờ:

```text
                    Scheduler
              +-------------------+
Task A -----> | Thread: đang chạy |
              +-------------------+
Task B -----> | Queue slot 1      |
Task C -----> | Queue slot 2      |
Task D -----> | REJECTED          |
              +-------------------+
```

Từ chối task là tín hiệu bảo vệ tài nguyên. Nó giúp hệ thống không tiếp tục tích tụ công việc vượt quá giới hạn đã đặt. Tuy nhiên, nếu ứng dụng không xử lý lỗi này, request có thể thất bại đột ngột. Nếu tự động retry ngay lập tức, tải có thể tăng thêm và làm scheduler tiếp tục bão hòa.

## 6. Xử lý từ chối theo chính sách nghiệp vụ

Khi scheduler không nhận thêm task, ứng dụng cần quyết định có nên báo bận, fallback, đưa công việc vào hàng đợi bền vững hay thử lại sau. Không có một cách xử lý đúng cho mọi loại công việc.

### Trả lỗi quá tải cho caller

Với request đồng bộ về mặt nghiệp vụ, có thể chuyển lỗi từ chối thành lỗi miền rõ ràng:

```java
Mono<Response> response = Mono.fromCallable(
        () -> legacyClient.fetch(requestId)
    )
    .subscribeOn(legacyIo)
    .onErrorMap(
        RejectedExecutionException.class,
        error -> new ServiceBusyException("Legacy service is busy", error)
    );
```

Caller có thể nhận biết tình trạng quá tải và áp dụng chính sách như trả HTTP 503, hiển thị trạng thái thử lại sau hoặc chuyển yêu cầu sang một hàng đợi bền vững.

### Fallback khi có kết quả thay thế hợp lệ

Nếu nghiệp vụ có dữ liệu cache hoặc kết quả dự phòng, có thể dùng `onErrorResume`:

```java
Mono<Config> config = loadRemoteConfig()
    .onErrorResume(
        RejectedExecutionException.class,
        error -> loadCachedConfig()
    );
```

Fallback chỉ phù hợp khi kết quả thay thế đáp ứng yêu cầu nghiệp vụ. Không nên trả dữ liệu cũ như thể đó là dữ liệu mới nếu tính nhất quán yêu cầu phải có kết quả cập nhật.

### Retry có backoff khi lỗi thực sự có thể phục hồi

Nếu từ chối chỉ xảy ra tạm thời và công việc có thể thử lại an toàn, hãy giới hạn số lần thử và thêm backoff/jitter. Tránh retry tức thì hoặc retry vô hạn:

```java
Mono<Response> response = callLegacyService()
    .retryWhen(
        Retry.backoff(2, Duration.ofMillis(200))
            .maxBackoff(Duration.ofSeconds(2))
            .jitter(0.5)
            .filter(this::isTransientCapacityFailure)
    );
```

Backoff không tạo thêm năng lực xử lý; nó chỉ giãn thời điểm thử lại. Cần đặt timeout tổng thể để request không chờ vô hạn. Nếu scheduler vẫn bão hòa kéo dài, nên từ chối sớm hoặc giảm lượng công việc mới thay vì tiếp tục retry.

## 7. Backpressure không đồng nghĩa với queue của scheduler

Reactive Streams backpressure kiểm soát số phần tử mà Subscriber yêu cầu qua `request(n)`. Queue của scheduler lưu task chờ được thực thi. Hai cơ chế có thể tương tác nhưng không giống nhau.

Ví dụ:

```java
Flux<Result> results = requests
    .flatMap(
        request -> Mono.fromCallable(() -> blockingCall(request))
            .subscribeOn(legacyIo),
        4,  // tối đa bốn inner Publisher hoạt động đồng thời
        1   // prefetch cho mỗi inner Publisher
    );
```

`flatMap` giới hạn số inner Publisher hoạt động tại bước đó. Mỗi inner gọi tác vụ blocking trên `legacyIo`. Scheduler lại có giới hạn thread và queue riêng. Nếu có nhiều pipeline cùng chia sẻ scheduler, tổng task từ mọi pipeline vẫn có thể làm scheduler bão hòa dù từng `flatMap` có concurrency nhỏ.

Không nên xem `onBackpressureDrop` là cách xử lý tự động cho `RejectedExecutionException`. Toán tử drop xử lý phần tử theo demand/backpressure ở ranh giới Publisher; nó không tự bắt mọi lỗi từ scheduler hoặc executor. Nếu cần bỏ phần tử khi downstream chậm, hãy đặt chính sách backpressure ở đúng ranh giới nguồn. Nếu scheduler từ chối task, hãy xử lý lỗi scheduling theo chính sách riêng.

## 8. Queue của publishOn và subscribeOn

`publishOn` tạo ranh giới thực thi cho các toán tử phía downstream và có queue phần tử riêng. Tham số `prefetch` điều chỉnh lượng phần tử được yêu cầu trước từ upstream:

```java
Flux<Report> reports = events
    .publishOn(Schedulers.parallel(), 32)
    .map(this::buildReport);
```

`32` là prefetch của `publishOn`, tức lượng phần tử mà operator yêu cầu trước để xử lý phía downstream. Nó không phải queue capacity của `Schedulers.parallel()` và cũng không phải giới hạn tổng số task của ứng dụng.

`subscribeOn` điều khiển nơi quá trình subscribe và nguồn bắt đầu thực thi:

```java
Mono<Data> data = Mono.fromCallable(this::readBlockingFile)
    .subscribeOn(Schedulers.boundedElastic());
```

`subscribeOn` không đặt một giới hạn queue chung cho toàn pipeline. Nếu có nhiều subscription đồng thời, mỗi nguồn có thể tạo công việc trên cùng scheduler dùng chung. Thread cap và queue cap của scheduler vẫn quyết định khả năng nhận task.

Khi `publishOn` nhận dữ liệu nhanh hơn downstream xử lý, operator có thể giữ phần tử trong queue nội bộ và điều tiết demand upstream. Nếu nguồn không tuân thủ backpressure hoặc có buffer khác ở trước, dữ liệu vẫn có thể tích tụ ở nơi khác. Cần kiểm tra từng ranh giới thay vì suy ra từ một tham số prefetch.

## 9. Không dùng parallel scheduler cho tác vụ blocking

`Schedulers.parallel()` có số thread cố định, thường tương ứng năng lực CPU. Nó phù hợp cho các bước tính toán ngắn, không blocking:

```java
Flux<Score> scores = inputs
    .publishOn(Schedulers.parallel())
    .map(this::calculateScore);
```

Nếu `calculateScore` thực hiện công việc CPU-bound, việc dùng parallel có thể tận dụng nhiều core. Nhưng nếu bước này gọi JDBC blocking, chờ file hoặc `Thread.sleep`, thread parallel bị giữ trong lúc chờ và các tác vụ khác phải đợi. Với API blocking, chuyển lời gọi sang bounded elastic; với API non-blocking, ưu tiên giữ Publisher bất đồng bộ và không bọc nó thành blocking call.

Reactor đánh dấu các thread scheduler dành cho non-blocking work. Một số API blocking của Reactor khi được gọi trên các thread đó có thể ném `IllegalStateException`. Đây là dấu hiệu cấu hình thực thi sai; không nên khắc phục bằng cách tắt kiểm tra mà hãy chuyển công việc blocking sang scheduler phù hợp.

## 10. Đặt giới hạn ở nhiều tầng

Một thiết kế ổn định thường cần giới hạn đồng thời ở cả pipeline và dependency:

```text
Nguồn request
     |
     v
Backpressure / giới hạn demand
     |
     v
flatMap(concurrency = 8)
     |
     v
boundedElastic(threadCap = 4, queueCap = 100)
     |
     v
HTTP/DB client (connection pool + pending limit + timeout)
     |
     v
Dependency bên ngoài
```

Ví dụ này chỉ minh họa các tầng kiểm soát, không khẳng định các con số là cấu hình tối ưu. Nếu `flatMap` cho phép tám inner Publisher nhưng scheduler chỉ có bốn thread, một số tác vụ sẽ chờ scheduler. Nếu connection pool chỉ có hai kết nối, một số tác vụ có thể tiếp tục chờ ở pool. Mỗi queue cần có giới hạn và timeout phù hợp.

Khi chọn giá trị, hãy xem xét:

- Năng lực thực tế của dependency và giới hạn connection/quota.
- Thời gian xử lý trung bình và phân vị cao của mỗi tác vụ.
- Kích thước dữ liệu được giữ trong queue.
- Số pipeline hoặc request đồng thời cùng dùng scheduler.
- Độ trễ tối đa nghiệp vụ chấp nhận.
- Hành vi khi queue đầy: reject, fallback, drop, persist hoặc retry có giới hạn.

## 11. Kiểm thử scheduler khi queue đầy

Có thể kiểm tra hành vi từ chối của bounded elastic bằng scheduler nhỏ có giới hạn thấp. Dùng `CountDownLatch` để giữ thread đầu tiên đang chạy, đưa một task thứ hai vào queue, rồi thử gửi task thứ ba:

```java
Scheduler scheduler = Schedulers.newBoundedElastic(1, 1, "capacity-test");
Scheduler.Worker worker = scheduler.createWorker();
CountDownLatch started = new CountDownLatch(1);
CountDownLatch release = new CountDownLatch(1);

try {
    worker.schedule(() -> {
        started.countDown();
        try {
            release.await();
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
        }
    });

    assertTrue(started.await(1, TimeUnit.SECONDS));
    worker.schedule(() -> {}); // chiếm slot queue duy nhất

    assertThrows(
        RejectedExecutionException.class,
        () -> worker.schedule(() -> {})
    );
} finally {
    release.countDown();
    worker.dispose();
    scheduler.dispose();
}
```

Kiểm thử này minh họa tình huống một thread đang bận, queue đã chứa một task và task tiếp theo bị từ chối. Cần chạy với phiên bản Reactor thực tế của dự án vì chi tiết hàng đợi và exception thuộc implementation scheduler. Latch giúp xác định chắc chắn task đầu tiên đã bắt đầu trước khi lấp queue, tránh phụ thuộc vào timing ngẫu nhiên.

Ngoài test từ chối task, nên kiểm thử pipeline ở các trạng thái:

- Tải thấp: mọi task được thực thi và không có queue đáng kể.
- Burst ngắn: queue tăng tạm thời rồi giảm khi consumer theo kịp.
- Tải kéo dài vượt năng lực: queue chạm giới hạn và chính sách reject/fallback hoạt động.
- Dependency chậm: thread hoặc connection bị giữ lâu nhưng số công việc đang hoạt động vẫn nằm trong giới hạn.
- Cancellation: task chờ không còn cần thiết được hủy hoặc bỏ theo khả năng của scheduler và operator.
- Disposal: scheduler ngừng nhận công việc mới và tài nguyên được giải phóng.

Với toán tử thời gian như `delay` hoặc `timeout`, có thể dùng `StepVerifier.withVirtualTime` để kiểm thử thời điểm. Virtual time không thay thế kiểm thử capacity thực vì nó không mô phỏng tốc độ thread, queue hoặc áp lực CPU của scheduler.

## 12. Quan sát tình trạng bão hòa

Nên theo dõi cả năng lực thực thi lẫn dữ liệu đang chờ:

1. Số thread đang hoạt động, số thread được tạo và thời gian task chạy.
2. Số task chờ, thời gian chờ trong queue và số lần scheduler từ chối task.
3. Tỷ lệ hoàn tất, lỗi, timeout và cancellation.
4. Queue/prefetch của operator và concurrency của `flatMap`.
5. Connection pool đang dùng, pending acquire và timeout của client.
6. Heap, garbage collection và kích thước phần tử đang được giữ.
7. Độ trễ đầu cuối và chênh lệch giữa tốc độ đến với tốc độ hoàn tất.

Nếu queue tăng liên tục trong khi throughput không tăng, thêm thread hoặc tăng queue có thể chỉ chuyển điểm nghẽn sang dependency phía sau. Nếu scheduler liên tục reject, cần xem lại concurrency, thời gian blocking, queue cap và khả năng mở rộng của dependency.

## 13. Các lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Chạy blocking trên `parallel` | Chiếm thread dành cho công việc CPU/non-blocking | Bọc lời gọi bằng `fromCallable` và dùng bounded elastic |
| Tăng queue không giới hạn | Độ trễ và heap tăng đến khi hệ thống cạn tài nguyên | Đặt queue cap, timeout và chính sách overflow/reject |
| Tạo scheduler cho từng request | Tăng số thread/pool và khó quản lý lifecycle | Tái sử dụng scheduler theo nhóm công việc |
| Nghĩ prefetch là queue cap của scheduler | Đánh giá sai tổng lượng công việc chờ | Đo riêng queue operator và queue scheduler |
| Dùng retry tức thì khi scheduler reject | Tạo thêm tải trong lúc scheduler đang bão hòa | Trả lỗi quá tải hoặc retry có backoff/jitter và giới hạn |
| Dùng drop để xử lý mọi lỗi scheduling | Phần tử có thể không bị drop theo demand mà task vẫn bị reject | Xử lý `RejectedExecutionException` ở ranh giới scheduling |
| Chỉ giới hạn thread, bỏ qua connection pool | Task chạy được nhưng tiếp tục chờ dependency | Đặt giới hạn đồng bộ ở scheduler, concurrency và client pool |
| Không dispose scheduler tự tạo | Thread và tài nguyên tồn tại sau khi thành phần dừng | Quản lý lifecycle và gọi `dispose()` |

## 14. Checklist trước khi đưa scheduler vào vận hành

1. Công việc là CPU-bound, non-blocking I/O hay blocking I/O?
2. Scheduler nào phù hợp và có bao nhiêu thread tối đa?
3. Queue capacity được cấu hình ở scheduler hay operator nào?
4. Bao nhiêu pipeline cùng chia sẻ scheduler đó?
5. `flatMap` concurrency và prefetch có phù hợp với thread cap và dependency không?
6. Khi queue đầy, ứng dụng trả lỗi, fallback, persist hay retry có giới hạn?
7. Retry có backoff, jitter và timeout tổng thể không?
8. Có metric cho task đang chạy, task chờ, rejection và latency không?
9. Scheduler tự tạo có được dispose khi ứng dụng dừng không?
10. Kiểm thử có bao phủ burst, saturation, cancellation và disposal không?

Giới hạn thread quyết định năng lực thực thi đồng thời; queue capacity quyết định lượng công việc có thể chờ; demand và prefetch điều khiển luồng phần tử giữa các Publisher; còn concurrency giới hạn số tác vụ logic đang hoạt động. Khi tách bạch các giới hạn này, chọn scheduler theo loại công việc và định nghĩa rõ hành vi khi queue đầy, pipeline Reactor có thể phản ứng có kiểm soát trước tải vượt năng lực thay vì tích tụ công việc vô hạn.
