# Chi phí chuyển bộ lập lịch và hàng đợi trung gian

Trong **REACTIVE_PROGRAMMING**, `Mono` và `Flux` mô tả các luồng dữ liệu bất đồng bộ theo hợp đồng `Publisher–Subscriber`. Reactor cho phép chuyển nơi thực thi bằng `subscribeOn` và `publishOn`, đồng thời nhiều operator như `flatMap`, `buffer` hoặc `onBackpressureBuffer` có thể giữ dữ liệu trong queue. Những cơ chế này giúp tách biệt công việc, tận dụng tài nguyên và điều tiết tải, nhưng mỗi ranh giới bất đồng bộ đều có chi phí.

Chuyển scheduler có thể cần lập lịch task, chuyển thread, đồng bộ hóa và chuyển tín hiệu qua queue. Queue trung gian có thể tăng throughput khi hấp thụ burst hoặc tách producer khỏi consumer, nhưng cũng tiêu thụ bộ nhớ và làm tăng thời gian chờ. Tối ưu hiệu năng cần cân bằng số ranh giới, kích thước queue, concurrency và chi phí thực tế của từng bước xử lý.

## 1. Một lần chuyển scheduler phải trả những chi phí nào?

Khi một pipeline chuyển từ thread hiện tại sang scheduler khác, framework cần đưa công việc vào hàng đợi hoặc cơ chế lập lịch của scheduler, sau đó một worker lấy task và thực thi. Tùy operator, còn có queue giữ các phần tử dữ liệu chờ được xử lý.

Các khoản chi phí thường gặp gồm:

- **Lập lịch task:** tạo hoặc gửi một task đến worker của scheduler.
- **Chuyển ngữ cảnh:** CPU chuyển sang thực thi thread khác; nếu thread không chạy trên core ngay, task phải chờ.
- **Đồng bộ hóa:** queue, worker và trạng thái demand cần phối hợp giữa producer và consumer.
- **Queueing delay:** phần tử hoặc task chờ đến lượt được xử lý.
- **Allocation và quản lý bộ nhớ:** queue node, task wrapper, buffer và object phụ trợ có thể tạo thêm allocation.
- **Mất cơ hội tối ưu liên tục:** một ranh giới bất đồng bộ có thể ngăn một số operator chạy liền mạch hoặc kết hợp vòng lặp xử lý.

Chi phí không chỉ là thời gian đổi thread. Một pipeline có nhiều queue có thể giữ nhiều phần tử cùng lúc, tăng heap/direct memory và tạo thêm công việc cho garbage collector.

## 2. Phân biệt subscribeOn và publishOn

Hai operator này điều khiển hai vị trí khác nhau trong pipeline:

| Operator | Ảnh hưởng chính | Phạm vi |
|---|---|---|
| `subscribeOn(scheduler)` | Lập lịch quá trình subscribe và việc bắt đầu nguồn | Tác động đến upstream từ vị trí đặt operator |
| `publishOn(scheduler)` | Chuyển việc phát tín hiệu downstream sang worker của scheduler | Các operator phía sau ranh giới đó chạy trên scheduler được chọn cho đến một lần chuyển khác |

Ví dụ dùng `subscribeOn` để cô lập lời gọi blocking ở nguồn:

```java
Mono<Customer> customer = Mono.fromCallable(
        () -> legacyClient.loadCustomer(customerId)
    )
    .subscribeOn(Schedulers.boundedElastic());
```

`fromCallable` trì hoãn lời gọi đến lúc subscribe. `subscribeOn` đưa việc subscribe nguồn và lời gọi blocking lên bounded elastic. Nếu gọi `legacyClient.loadCustomer(customerId)` trước rồi truyền kết quả vào `Mono.just`, lời gọi đã chạy trong lúc lắp ráp; `subscribeOn` không thể chuyển ngược một lời gọi đã hoàn tất.

Ví dụ dùng `publishOn` để chuyển một đoạn xử lý phía downstream:

```java
Flux<Score> scores = inputEvents
    .map(this::normalize)
    .publishOn(Schedulers.parallel())
    .map(this::calculateScore)
    .map(this::toScore);
```

`normalize` chạy theo thread upstream. Các operator phía sau `publishOn` chạy trên worker của scheduler parallel. Ranh giới này có ích nếu phần tính điểm cần chuyển sang nhóm thread CPU, nhưng nó tạo một điểm bàn giao bất đồng bộ và queue dữ liệu.

## 3. Mỗi publishOn là một ranh giới bất đồng bộ

Một `publishOn` thường dùng một worker để thực thi phần downstream và queue để chuyển các phần tử từ upstream sang worker đó. Tham số `prefetch` điều khiển lượng phần tử được yêu cầu trước từ upstream:

```java
Flux<Result> results = source
    .publishOn(Schedulers.parallel(), 128)
    .map(this::transform)
    .filter(this::isUseful);
```

`128` là prefetch của operator `publishOn`, không phải số thread, không phải queue capacity của toàn scheduler và cũng không phải giới hạn số phần tử mỗi giây. Operator có thể yêu cầu trước một lượng phần tử để worker luôn có dữ liệu xử lý; khi consumer tiêu thụ, demand được bổ sung theo cơ chế của operator.

Thêm nhiều ranh giới:

```java
Flux<Result> results = source
    .publishOn(Schedulers.parallel(), 128)
    .map(this::normalize)
    .publishOn(Schedulers.boundedElastic(), 64)
    .map(this::callBlockingAdapter)
    .publishOn(Schedulers.parallel(), 128)
    .map(this::buildResult);
```

Pipeline này có ba ranh giới `publishOn`. Mỗi ranh giới có thể thêm task scheduling, queue, đồng bộ hóa và độ trễ chờ. Việc chuyển sang bounded elastic rồi quay lại parallel có thể hợp lý nếu thật sự có một bước blocking ở giữa, nhưng nếu `callBlockingAdapter` không blocking thì hai lần chuyển scheduler có thể chỉ tạo overhead.

Không nên thêm `publishOn` sau mọi operator. Hãy nhóm các bước cần cùng loại thực thi vào một đoạn liên tục và chỉ chuyển scheduler tại ranh giới có mục đích rõ ràng.

## 4. Queue của scheduler khác queue của operator

Một pipeline có thể có nhiều loại queue. Cần xác định queue nào đang giữ task và queue nào đang giữ phần tử dữ liệu:

| Queue | Nội dung | Ví dụ điều khiển |
|---|---|---|
| Queue của scheduler | Runnable/task chờ worker thực thi | Thread cap và queue cap của scheduler |
| Queue của `publishOn` | Phần tử upstream đã phát, chờ downstream xử lý | `prefetch` của `publishOn` |
| Queue của `flatMap` | Kết quả từ các inner Publisher chờ được hợp nhất/phát | `maxConcurrency` và `prefetch` |
| Queue backpressure | Phần tử được giữ theo chính sách buffer/drop/latest | `onBackpressureBuffer`, `onBackpressureDrop`, `onBackpressureLatest` |
| Queue của dependency | Request chờ connection hoặc tài nguyên ngoài | Connection pool và pending acquire limit |

Giảm queue của scheduler không tự giảm queue của operator. Giảm prefetch ở `publishOn` cũng không tự giới hạn pending request của HTTP client. Khi điều tra bộ nhớ và latency, hãy đo từng tầng thay vì gom mọi thứ thành một khái niệm “queue”.

## 5. Queue lớn có thể che giấu consumer chậm

Queue hấp thụ được burst ngắn khi producer tạm thời phát nhanh hơn consumer. Nhưng nếu tốc độ đến trung bình lớn hơn tốc độ xử lý trong thời gian dài, backlog sẽ tăng cho đến khi queue đầy hoặc bộ nhớ cạn.

Với một hệ thống ổn định, định luật Little mô tả quan hệ trung bình:

\[
L = \lambda W
\]

Trong đó:

- \(L\) là số công việc trung bình đang ở trong hệ thống hoặc hàng chờ, tùy ranh giới đo.
- \(\lambda\) là throughput trung bình (công việc/giây).
- \(W\) là thời gian trung bình một công việc ở trong hệ thống.

Ví dụ, nếu pipeline xử lý 2.000 phần tử mỗi giây và thời gian trung bình một phần tử nằm trong ranh giới đo là 50 ms, số phần tử trung bình trong hệ thống xấp xỉ 100. Khi queue tăng mà throughput không tăng, thời gian chờ cũng tăng.

Định luật này mô tả hệ thống ổn định trong một khoảng đo phù hợp. Nếu tốc độ đến liên tục vượt năng lực phục vụ, queue không có trạng thái ổn định; cần giảm tải, tăng năng lực xử lý hoặc từ chối công việc trước khi tài nguyên cạn.

## 6. Prefetch là công cụ điều tiết, không phải mục tiêu tối đa hóa

Prefetch lớn có thể giữ worker bận và giảm khoảng trống khi downstream tiêu thụ nhanh. Nhưng nó cũng có thể giữ nhiều phần tử hơn trong bộ nhớ, đặc biệt khi mỗi phần tử có payload lớn hoặc chứa tài nguyên pooled.

Ví dụ:

```java
Flux<DecodedFrame> frames = networkFrames
    .publishOn(Schedulers.parallel(), 16)
    .map(this::decode);
```

Prefetch 16 có thể phù hợp khi frame lớn và consumer xử lý tương đối nhanh. Nếu frame nhỏ và cần throughput cao, giá trị lớn hơn có thể có lợi; nếu frame lớn hoặc downstream chậm, prefetch thấp hơn có thể giảm lượng dữ liệu đang giữ.

Không có một giá trị tối ưu cho mọi pipeline. Hãy đo throughput, p95/p99 latency, queue depth, allocation và heap/direct memory khi thay đổi prefetch.

## 7. flatMap cũng tạo queue và concurrency riêng

`flatMap` ghép nhiều Publisher con bất đồng bộ. Hai tham số quan trọng là concurrency và prefetch:

```java
Flux<Profile> profiles = userIds
    .flatMap(
        id -> profileClient.fetch(id),
        8,  // tối đa tám inner Publisher hoạt động đồng thời
        4   // prefetch cho mỗi inner Publisher
    );
```

`maxConcurrency` giới hạn số inner Publisher đang được subscribe đồng thời. `prefetch` điều chỉnh lượng phần tử được yêu cầu trước từ mỗi inner Publisher. Khi inner phát nhiều phần tử, queue nội bộ có thể giữ kết quả đang chờ được hợp nhất hoặc phát ra downstream.

Nếu mỗi inner là `Mono` chỉ phát tối đa một phần tử, prefetch lớn hơn một thường không làm tăng số kết quả của inner đó. Nếu inner là `Flux` phát nhiều phần tử, prefetch ảnh hưởng rõ hơn đến dữ liệu được yêu cầu và giữ trước.

Concurrency của `flatMap` không phải số thread. Tám inner Publisher có thể thực hiện I/O non-blocking trên một số ít event loop; ngược lại, nếu mỗi inner dùng `subscribeOn` riêng, chúng có thể tạo nhiều task trên scheduler dùng chung. Cần xem xét đồng thời giới hạn của operator, scheduler và dependency.

## 8. Operator fusion có thể giảm overhead

Reactor có thể kết hợp một số operator tương thích thông qua cơ chế operator fusion. Thay vì mỗi operator tạo một lớp callback và truyền từng tín hiệu qua nhiều tầng, các operator fuseable có thể phối hợp để giảm lời gọi trung gian và allocation.

Ví dụ một chuỗi xử lý đồng bộ:

```java
Flux<Integer> values = Flux.range(1, 1_000_000)
    .map(value -> value + 1)
    .filter(value -> value % 2 == 0)
    .map(value -> value * 3);
```

Các operator đồng bộ tương thích có thể được tối ưu bằng fusion. Khi thêm một ranh giới bất đồng bộ như `publishOn`, dữ liệu cần được chuyển qua queue và execution tách ra; điều này có thể thay đổi cách fusion hoạt động. Reactor cũng có các dạng queue fusion để phối hợp producer/consumer, nên không nên khẳng định mọi ranh giới đều tắt toàn bộ fusion.

Điểm thực tế là một pipeline thuần đồng bộ, ngắn thường có cơ hội chạy liền mạch với ít overhead hơn. Thêm scheduler boundary chỉ để “làm cho reactive hơn” có thể khiến pipeline chậm hơn. Hãy đo trên đúng phiên bản Reactor và kiểu nguồn đang dùng.

## 9. Tránh tạo scheduler mới cho từng request hoặc phần tử

Scheduler là tài nguyên thực thi có lifecycle. Tạo một scheduler mới cho mỗi request làm tăng số pool, thread, queue và chi phí khởi tạo; đồng thời làm khó kiểm soát tổng năng lực xử lý.

Không nên:

```java
Flux<Result> process(Flux<Input> input) {
    return input.flatMap(value -> {
        Scheduler scheduler = Schedulers.newParallel("per-item", 2);
        return Mono.fromCallable(() -> calculate(value))
            .subscribeOn(scheduler);
    });
}
```

Mẫu này tạo scheduler lặp lại theo từng phần tử và không có lifecycle dispose rõ ràng.

Nên tái sử dụng scheduler theo nhóm công việc hoặc để Reactor quản lý scheduler dùng chung:

```java
final class ScoringService {
    private final Scheduler cpuScheduler = Schedulers.parallel();

    Flux<Score> process(Flux<Input> input) {
        return input
            .publishOn(cpuScheduler)
            .map(this::calculate);
    }
}
```

`Schedulers.parallel()` trả scheduler dùng chung của Reactor. Nếu tự tạo scheduler bằng `newParallel` hoặc `newBoundedElastic`, component sở hữu nó phải dispose khi dừng. Không dispose scheduler dùng chung của Reactor từ một component không sở hữu lifecycle của nó.

## 10. Chọn số lần chuyển scheduler theo loại công việc

Một pipeline thường cần ít ranh giới hơn khi nhóm công việc theo loại thực thi:

```java
Mono<Report> report = Mono.fromCallable(this::readLegacySource)
    .subscribeOn(Schedulers.boundedElastic())
    .map(this::normalize)
    .publishOn(Schedulers.parallel())
    .map(this::calculateReport)
    .map(this::toReport);
```

Trong ví dụ, nguồn blocking chạy trên bounded elastic; các bước biến đổi và tính toán phía sau chuyển sang parallel. Chỉ có một lần chuyển rõ ràng giữa hai nhóm công việc. Nếu `normalize` cũng CPU-bound và không cần chạy cùng thread nguồn blocking, có thể đặt nó sau `publishOn`; nếu nó nhẹ và có thể chạy ngay sau khi đọc, hãy đo trước khi thêm ranh giới.

Quy tắc lựa chọn:

- **CPU-bound:** dùng `parallel` cho các tác vụ tính toán độc lập, đủ dài để bù chi phí lập lịch.
- **Blocking I/O:** cô lập bằng `boundedElastic` hoặc executor được quản lý riêng.
- **Non-blocking I/O:** ưu tiên giữ Publisher bất đồng bộ trên event loop phù hợp; không chuyển thread nếu không có nhu cầu cụ thể.
- **Tuần tự hóa trạng thái:** dùng operator/worker tuần tự theo đúng phạm vi state, không tạo scheduler mới cho từng event.
- **Tác vụ rất ngắn:** cân nhắc giữ trong cùng đoạn thực thi nếu không có lý do phải chuyển scheduler.

## 11. Batching có thể giảm số lần bàn giao

Nếu mỗi phần tử chỉ cần một phép xử lý rất nhỏ, chi phí scheduling hoặc gọi dependency cho từng phần tử có thể chiếm tỷ lệ lớn. Gom các phần tử thành batch có thể giảm số lần bàn giao:

```java
Flux<BatchResult> results = events
    .buffer(100)
    .filter(batch -> !batch.isEmpty())
    .flatMap(batch -> batchClient.process(batch), 4);
```

Thay vì gọi `process` cho từng event, pipeline gửi một batch gồm tối đa 100 phần tử. Điều này có thể giảm số request, số lần schedule và overhead giao thức.

Batching có các đánh đổi:

- Phần tử đầu tiên phải chờ batch đủ số lượng hoặc hết thời gian nếu dùng buffer theo thời gian.
- Batch lớn giữ nhiều dữ liệu trong bộ nhớ.
- Một lỗi batch có thể ảnh hưởng nhiều phần tử cùng lúc.
- Retry batch có thể lặp lại side effect cho các phần tử đã xử lý nếu API không idempotent.
- Batch quá lớn có thể vượt giới hạn payload của database hoặc dịch vụ từ xa.

Chọn kích thước batch theo latency mục tiêu, kích thước payload và khả năng dependency. Với stream liên tục, có thể dùng buffer theo cả kích thước và thời gian để tránh batch nhỏ chờ quá lâu.

## 12. Backpressure không loại bỏ chi phí queue

Reactive Streams demand giúp giới hạn lượng phần tử upstream được phép phát. Tuy nhiên, các operator có thể yêu cầu trước một số phần tử để làm việc hiệu quả; queue vẫn có thể tồn tại ở ranh giới bất đồng bộ.

Ví dụ:

```java
Flux<Result> results = source
    .publishOn(Schedulers.parallel(), 64)
    .map(this::transform);
```

Downstream tiêu thụ theo demand, nhưng `publishOn` có thể prefetch dữ liệu theo cấu hình. Backpressure ngăn nguồn phát vượt demand đã được yêu cầu; nó không có nghĩa pipeline không giữ dữ liệu đang chờ.

Nếu một queue hữu hạn đầy, operator có thể ngừng yêu cầu thêm dữ liệu, áp dụng chính sách overflow hoặc phát lỗi tùy loại operator. Nếu một nguồn không thể điều tiết, cần chọn buffer/drop/latest/error phù hợp và giới hạn bộ nhớ. Không dùng queue lớn như cách che giấu consumer chậm.

## 13. Đo chi phí thay vì đếm số operator

Số lượng operator không trực tiếp cho biết pipeline chậm. Một pipeline có nhiều `map` đồng bộ và fuseable có thể rẻ hơn pipeline ngắn nhưng chuyển scheduler nhiều lần. Hãy đo các chỉ số:

1. Throughput (phần tử/giây).
2. p50, p95 và p99 latency.
3. Thời gian chờ trong queue và queue depth.
4. Số task được schedule và thời gian task chờ worker.
5. CPU utilization và context switches.
6. Allocation rate, heap, direct memory và garbage collection.
7. Số thread hoạt động, số task bị reject và số lần queue chạm giới hạn.
8. Số request downstream đang chờ và thời gian giữ connection.

Micrometer/Reactor metrics có thể cung cấp một phần thông tin về scheduler và pipeline khi được cấu hình. JFR và profiler giúp xác định CPU, allocation, lock contention và context switching. Không nên chỉ dựa vào một metric tổng như CPU hoặc heap để kết luận queue nào là nguyên nhân.

## 14. Benchmark các phương án chuyển scheduler

Khi so sánh pipeline, hãy giữ dữ liệu và công việc tương đương, chạy warmup, nhiều lần đo và tránh dùng `System.nanoTime()` một lần trên một luồng nhỏ làm kết luận.

Một benchmark JMH có thể so sánh pipeline thuần đồng bộ với pipeline có ranh giới scheduler:

```java
@State(Scope.Benchmark)
public class SchedulerBoundaryBenchmark {

    private Flux<Integer> source;

    @Setup
    public void setup() {
        source = Flux.range(1, 10_000)
            .map(value -> value + 1)
            .filter(value -> (value & 1) == 0);
    }

    @Benchmark
    public List<Integer> withoutBoundary() {
        return source
            .map(value -> value * 3)
            .collectList()
            .block();
    }

    @Benchmark
    public List<Integer> withBoundary() {
        return source
            .publishOn(Schedulers.parallel(), 256)
            .map(value -> value * 3)
            .collectList()
            .block();
    }
}
```

Đây là phác thảo benchmark: dự án cần thêm dependency JMH, cấu hình warmup/measurement/forks và bảo đảm scheduler được khởi tạo ngoài phần đo nếu muốn cô lập chi phí pipeline. `block()` ở đây chỉ dùng để thu kết quả trong benchmark; không nên sao chép cách này vào request handler reactive production.

Khi benchmark scheduler, nên đo riêng:

- Chi phí pipeline không có boundary.
- Một boundary với các mức prefetch khác nhau.
- Nhiều boundary liên tiếp.
- Tải đồng thời với nhiều subscription.
- Phần tử nhỏ so với payload lớn.
- CPU-bound so với blocking hoặc I/O giả lập.

Kết quả phụ thuộc CPU, số core, phiên bản JVM, Reactor, scheduler và tải đồng thời. Không có một con số benchmark chung áp dụng cho mọi môi trường.

## 15. Kiểm thử tính đúng đắn khi thay đổi scheduler

Tối ưu bằng cách bỏ hoặc gộp scheduler boundary có thể thay đổi thread thực thi, thứ tự cạnh tranh và thời điểm quan sát. Trước khi benchmark, hãy bảo đảm semantics vẫn đúng:

- Kiểm tra giá trị và thứ tự bằng `StepVerifier`.
- Kiểm tra cancellation có truyền đến nguồn.
- Kiểm tra lỗi từ callback và scheduler được chuyển đúng.
- Kiểm tra state mutable không bị chia sẻ ngoài ý muốn.
- Kiểm tra resource cleanup khi task bị hủy.
- Kiểm tra concurrency và prefetch không làm vượt giới hạn dependency.

`StepVerifier.withVirtualTime` hữu ích để kiểm tra operator thời gian như `delay` hoặc `timeout`, nhưng không đo hiệu năng thread thật. Đo scheduling overhead cần benchmark/load test trên scheduler và môi trường thực tế.

## 16. Các lỗi tối ưu thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Thêm `publishOn` sau mọi operator | Tăng số lần bàn giao, queue và queueing delay | Nhóm các bước cùng loại thực thi và chuyển tại ranh giới cần thiết |
| Dùng `subscribeOn` như thể nó đổi thread tại mọi bước | Hiểu sai phạm vi thực thi và thêm operator không cần thiết | Dùng `subscribeOn` cho nguồn; `publishOn` cho đoạn downstream cần chuyển |
| Tăng prefetch để che consumer chậm | Tăng bộ nhớ và thời gian chờ | Đo queue depth, throughput và latency; chọn prefetch hữu hạn |
| Tạo scheduler theo request/phần tử | Tăng thread, queue và chi phí lifecycle | Tái sử dụng scheduler theo nhóm công việc |
| Chạy blocking trên `parallel` | Chiếm thread CPU và làm chậm pipeline khác | Chuyển blocking I/O sang bounded elastic hoặc executor riêng |
| Nghĩ backpressure đồng nghĩa không có queue | Đánh giá thấp bộ nhớ đang giữ | Theo dõi queue của operator, scheduler và dependency riêng |
| Benchmark không warmup hoặc chỉ chạy một lần | Kết quả nhiễu bởi JIT, GC và tải nền | Dùng JMH, warmup, nhiều fork và môi trường ổn định |
| Dùng virtual time để kết luận scheduling nhanh/chậm | Virtual time không mô phỏng chi phí thread thật | Dùng benchmark/load test trên scheduler thực |

## 17. Checklist giảm chi phí chuyển scheduler và queue

Trước khi thay đổi pipeline, hãy xác định:

1. Công việc nào thực sự cần chạy trên scheduler khác?
2. `subscribeOn` có đặt đúng ở nguồn lazy cần cô lập không?
3. Có `publishOn` liên tiếp hoặc ranh giới nào không tạo giá trị không?
4. Mỗi `publishOn` có prefetch phù hợp với kích thước phần tử và tốc độ downstream không?
5. `flatMap` concurrency và prefetch có phù hợp với scheduler và dependency không?
6. Queue nào đang giữ task, queue nào đang giữ dữ liệu và queue nào thuộc dependency?
7. Có thể nhóm/batch công việc để giảm số lần bàn giao không?
8. Operator fusion có thể giảm overhead trong đoạn xử lý đồng bộ không?
9. Scheduler tự tạo có được tái sử dụng và dispose đúng lifecycle không?
10. Benchmark có đo throughput, p95/p99 latency, allocation và queueing delay không?
11. Kiểm thử có xác minh semantics, cancellation và cleanup sau tối ưu không?

Chuyển scheduler là một ranh giới thực thi có chi phí; queue trung gian là nơi dữ liệu hoặc task chờ được xử lý. `subscribeOn` phù hợp để điều khiển quá trình subscribe nguồn, `publishOn` chuyển đoạn downstream, còn concurrency và prefetch điều chỉnh lượng công việc được phép hoạt động hoặc yêu cầu trước. Giữ các bước đồng loại liền nhau, dùng queue hữu hạn, tái sử dụng scheduler và đo trên tải thực giúp giảm overhead mà vẫn giữ được khả năng điều tiết của pipeline reactive.
