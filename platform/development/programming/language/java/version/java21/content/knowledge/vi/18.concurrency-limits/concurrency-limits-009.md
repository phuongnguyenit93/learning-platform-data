# Phối hợp tác vụ CPU-bound với executor có mức song song phù hợp

Tác vụ CPU-bound dành phần lớn thời gian thực hiện tính toán, xử lý dữ liệu hoặc thuật toán và ít chờ I/O. Với loại tải này, hiệu năng phụ thuộc chủ yếu vào số lõi CPU mà tiến trình có thể sử dụng. Tạo thật nhiều thread không làm tăng năng lực tính toán; nó có thể làm tăng chuyển đổi ngữ cảnh, tranh chấp CPU và bộ nhớ.

Trong Java 21, hãy chọn executor có số worker phù hợp với năng lực CPU, giới hạn lượng task chờ và đo hiệu năng bằng workload thực tế. Virtual thread rất hữu ích cho nhiều tác vụ blocking, nhưng không phải cách tăng tốc cho phép tính CPU-bound. Các lựa chọn phổ biến cho công việc tính toán là một ThreadPoolExecutor dùng platform thread với số worker cố định hoặc ForkJoinPool cho công việc có thể chia nhỏ thành các task đệ quy.

## 1. Phân biệt concurrency và parallelism

Hai khái niệm thường bị nhầm lẫn:

- **Concurrency (đồng thời):** nhiều tác vụ có thể tiến triển trong cùng khoảng thời gian; chúng có thể luân phiên sử dụng tài nguyên.
- **Parallelism (song song):** nhiều tác vụ thực sự chạy cùng thời điểm trên các đơn vị xử lý khác nhau.

Một ứng dụng có thể có hàng nghìn task đang tồn tại nhưng chỉ một số task được CPU thực thi tại cùng thời điểm. Với tác vụ CPU-bound, tăng số worker vượt xa số CPU khả dụng thường không làm tăng throughput.

Ví dụ, nếu JVM được cấp 8 processor khả dụng, một nhóm khoảng 8 worker CPU-bound có thể khai thác song song 8 processor. Tạo 200 worker để cùng tính toán thường chỉ khiến các worker cạnh tranh 8 processor đó.

## 2. Vì sao CPU-bound cần mức song song có giới hạn?

Một worker đang chạy phép tính CPU-bound liên tục sẽ chiếm thời gian xử lý của CPU. Khác với tác vụ I/O-bound, nó ít có thời gian chờ để nhường worker cho task khác.

Nếu số worker lớn hơn nhiều so với CPU khả dụng, hệ điều hành phải thường xuyên chuyển đổi giữa các thread runnable. Điều này tạo thêm chi phí:

- Context switching tăng.
- Cache CPU có thể kém hiệu quả do worker thay đổi liên tục.
- Các thread tranh chấp lock hoặc dữ liệu dùng chung.
- Độ trễ p95/p99 có thể tăng dù throughput không tăng.
- Bộ nhớ dành cho thread và trạng thái task tăng.

Vì vậy, executor CPU-bound nên có số worker hữu hạn. Khi tất cả worker đang bận, hệ thống cần một chính sách rõ ràng cho task mới: xếp vào hàng đợi có giới hạn, từ chối hoặc áp dụng backpressure.

## 3. Ước lượng số worker theo CPU khả dụng

Có thể bắt đầu bằng:

```java
int processors = Runtime.getRuntime().availableProcessors();
```

Phương thức này trả về số processor mà JVM hiện có thể sử dụng theo môi trường chạy. Trong container, giá trị có thể phản ánh giới hạn CPU mà JVM nhận biết được, thay vì tổng số lõi vật lý của máy chủ.

Với workload chủ yếu CPU-bound, số worker ban đầu thường nên xấp xỉ số processor khả dụng:

```java
int parallelism = Math.max(
        1,
        Runtime.getRuntime().availableProcessors()
);
```

Đây là điểm bắt đầu để benchmark, không phải con số tối ưu cho mọi ứng dụng. Có thể chọn thấp hơn nếu:

- Tiến trình cần chia CPU với các dịch vụ khác.
- Một số worker dành cho công việc khác trong cùng ứng dụng.
- Thuật toán bị giới hạn bởi băng thông bộ nhớ hoặc lock contention.
- Thư viện native bên dưới tự tạo nhiều thread để tính toán.
- Mục tiêu là giữ latency ổn định thay vì sử dụng hết CPU.

Nếu task có cả tính toán và thời gian chờ đáng kể, cần đo tỷ lệ CPU và thời gian chờ trước khi chọn số worker. Công thức ước lượng cho workload có thời gian chờ có thể đưa ra số worker lớn hơn số CPU, nhưng không nên áp dụng máy móc cho tác vụ CPU-bound thuần túy.

## 4. Dùng ThreadPoolExecutor với số worker cố định và queue có giới hạn

Với một nhóm task tính toán độc lập, ThreadPoolExecutor cho phép kiểm soát số platform thread, kích thước hàng đợi và chính sách từ chối task.

Ví dụ dưới đây cấu hình số worker tối đa theo số processor khả dụng và giới hạn hàng đợi:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

int parallelism = Math.max(
        1,
        Runtime.getRuntime().availableProcessors()
);

int queueCapacity = 200;

ThreadPoolExecutor cpuExecutor = new ThreadPoolExecutor(
        parallelism,
        parallelism,
        0L,
        TimeUnit.MILLISECONDS,
        new ArrayBlockingQueue<>(queueCapacity),
        Thread.ofPlatform().name("cpu-worker-", 0).factory(),
        new ThreadPoolExecutor.AbortPolicy()
);
```

Các tham số có ý nghĩa:

| Tham số | Ý nghĩa |
|---|---|
| corePoolSize | Mức worker lõi; các thread thường được tạo khi có task và được giữ lại trong pool |
| maximumPoolSize | Số worker tối đa; bằng corePoolSize để giữ mức song song cố định |
| keepAliveTime | Thời gian worker vượt core có thể chờ trước khi bị loại; không có tác dụng đáng kể khi core và max bằng nhau |
| workQueue | Hàng đợi task đang chờ; ArrayBlockingQueue có capacity hữu hạn |
| ThreadFactory | Tạo platform thread với tên dễ quan sát |
| RejectedExecutionHandler | Quyết định hành vi khi executor không nhận thêm task |

Khi tất cả worker đều bận và queue đã đầy, AbortPolicy ném RejectedExecutionException. Tầng gọi có thể bắt exception này để từ chối request, trả trạng thái quá tải hoặc đưa công việc vào một cơ chế lưu trữ khác nếu nghiệp vụ cho phép.

Capacity 200 trong ví dụ chỉ là giá trị minh họa. Hãy chọn kích thước queue theo ngân sách bộ nhớ, thời gian chờ tối đa của task và tốc độ xử lý; queue dài có thể làm latency tăng dù không có task nào bị từ chối.

Không nên mặc định dùng queue không giới hạn cho hệ thống nhận tải liên tục. Queue không giới hạn có thể che giấu overload trong một thời gian, nhưng task chờ vẫn chiếm bộ nhớ và latency tăng dần.

### Đóng executor đúng cách

ExecutorService triển khai AutoCloseable trong Java 21, vì vậy có thể dùng try-with-resources khi phạm vi công việc có thời điểm bắt đầu và kết thúc rõ ràng:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.Future;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

int parallelism = Math.max(
        1,
        Runtime.getRuntime().availableProcessors()
);

try (var executor = new ThreadPoolExecutor(
        parallelism,
        parallelism,
        0L,
        TimeUnit.MILLISECONDS,
        new ArrayBlockingQueue<>(200),
        Thread.ofPlatform().name("cpu-worker-", 0).factory(),
        new ThreadPoolExecutor.AbortPolicy()
)) {
    Future<Long> result = executor.submit(() -> calculateRange(0, 1_000_000));
    System.out.println(result.get());
}
```

Khi rời khỏi khối try, close() bắt đầu orderly shutdown và chờ task đã được nhận hoàn tất. Với executor sống lâu theo vòng đời ứng dụng, hãy đóng nó ở giai đoạn shutdown của ứng dụng thay vì tạo và đóng executor cho từng request.

## 5. Chính sách khi executor hết capacity

Khi worker đều bận và queue đã đầy, RejectedExecutionHandler quyết định điều gì xảy ra với task mới.

| Chính sách | Hành vi | Khi cân nhắc |
|---|---|---|
| AbortPolicy | Ném RejectedExecutionException | Phù hợp khi tầng gọi phải biết task bị từ chối |
| CallerRunsPolicy | Thread gọi submit/execute tự chạy task | Có thể tạo backpressure, nếu thread gọi được phép thực hiện công việc CPU |
| DiscardPolicy | Bỏ task mới mà không báo lỗi | Chỉ dùng khi mất task là hành vi được chấp nhận rõ ràng |
| DiscardOldestPolicy | Loại task đầu hàng đợi rồi thử submit task mới | Chỉ dùng khi chính sách bỏ task cũ đã được thiết kế và kiểm soát |

Với API server, CallerRunsPolicy có thể làm request thread phải chạy tính toán thay executor. Điều này đôi khi làm chậm tốc độ nhận request, nhưng cũng có thể làm nghẽn event loop hoặc thread điều phối quan trọng. Vì task chạy bên ngoài worker của pool, nhiều thread gọi đồng thời cũng có thể làm số phép tính đang chạy vượt số worker đã cấu hình; CallerRunsPolicy không phải giới hạn CPU concurrency tuyệt đối. Cần hiểu thread nào gọi submit trước khi chọn chính sách này.

AbortPolicy thường dễ quan sát và kiểm soát hơn: tầng gọi nhận được tín hiệu từ chối để phản hồi overload hoặc áp dụng admission control. Không nên âm thầm bỏ task nếu người gọi đang chờ kết quả.

### Vì sao không nên dùng fixed thread pool một cách mặc định?

`Executors.newFixedThreadPool(n)` giới hạn số worker, nhưng dùng hàng đợi không giới hạn. Vì vậy, nó giới hạn số task đang chạy chứ không giới hạn số task chờ. Khi đầu vào liên tục vượt tốc độ xử lý, hàng đợi có thể tăng rất lớn.

Nếu cần kiểm soát overload, hãy dùng ThreadPoolExecutor với queue hữu hạn và chính sách từ chối tường minh. Fixed thread pool vẫn có thể phù hợp với workload có lượng task được kiểm soát từ trước, nhưng không tự cung cấp backpressure.

## 6. Dùng ForkJoinPool cho công việc có thể chia nhỏ

ForkJoinPool phù hợp với công việc tính toán có thể chia thành các task con độc lập rồi kết hợp kết quả. Nó sử dụng work-stealing: worker có thể lấy task từ hàng đợi của worker khác khi hàng đợi của mình đã hết việc.

Mô hình này phù hợp với thuật toán chia để trị, ví dụ:

- Tính tổng hoặc thống kê trên mảng lớn.
- Xử lý cây hoặc cấu trúc dữ liệu phân cấp.
- Chia tập dữ liệu thành các phân vùng độc lập.
- Tính toán đệ quy có thể chia thành các phần nhỏ.

Ví dụ dùng RecursiveTask để tính tổng một đoạn mảng:

```java
import java.util.concurrent.RecursiveTask;

final class SumTask extends RecursiveTask<Long> {
    private static final int THRESHOLD = 10_000;

    private final int[] values;
    private final int start;
    private final int end;

    SumTask(int[] values, int start, int end) {
        this.values = values;
        this.start = start;
        this.end = end;
    }

    @Override
    protected Long compute() {
        int length = end - start;

        if (length <= THRESHOLD) {
            long sum = 0;
            for (int i = start; i < end; i++) {
                sum += values[i];
            }
            return sum;
        }

        int middle = start + length / 2;
        SumTask left = new SumTask(values, start, middle);
        SumTask right = new SumTask(values, middle, end);

        left.fork();
        long rightResult = right.compute();
        long leftResult = left.join();

        return leftResult + rightResult;
    }
}
```

Chạy task bằng một ForkJoinPool có mức song song được chỉ định:

```java
import java.util.concurrent.ForkJoinPool;

int parallelism = Math.max(
        1,
        Runtime.getRuntime().availableProcessors()
);

try (ForkJoinPool pool = new ForkJoinPool(parallelism)) {
    long total = pool.invoke(new SumTask(values, 0, values.length));
    System.out.println(total);
}
```

Ngưỡng THRESHOLD cần được benchmark. Nếu chia task quá nhỏ, chi phí tạo và điều phối task có thể lớn hơn phần tính toán. Nếu chia quá lớn, số task song song có thể không đủ để khai thác CPU.

ForkJoinPool cũng có thể chạy các task có blocking, nhưng blocking không được quản lý đúng cách có thể làm giảm parallelism. Với workload CPU-bound, nên giữ task ngắn, không chờ I/O và tránh khóa dùng chung.

## 7. Chọn ForkJoinPool hay ThreadPoolExecutor?

Hai executor phục vụ các mô hình công việc khác nhau:

| Tiêu chí | ThreadPoolExecutor | ForkJoinPool |
|---|---|---|
| Mô hình task | Nhiều task độc lập gửi vào một hàng đợi | Task có thể chia nhỏ và fork/join |
| Số worker | Cấu hình core/max rõ ràng | Cấu hình parallelism của pool |
| Hàng đợi | Có thể chọn queue hữu hạn để kiểm soát backlog | Hàng đợi work-stealing nội bộ |
| Rejection | Có handler khi queue đầy hoặc executor shutdown | Không phải cơ chế admission control chung cho ứng dụng |
| Phù hợp | Tác vụ độc lập, batch, xử lý CPU theo request | Thuật toán chia để trị, đệ quy, work-stealing |
| Lưu ý | Cần chọn queue capacity và rejection policy | Tránh blocking lâu và task quá nhỏ |

Nếu mỗi request là một phép tính độc lập, ThreadPoolExecutor với số worker cố định và queue hữu hạn thường dễ vận hành. Nếu một phép tính lớn có thể chia thành nhiều nhánh đệ quy, ForkJoinPool thường phù hợp hơn.

Không nên chọn ForkJoinPool chỉ vì nó có tên “parallel”. Cấu trúc task và cách phối hợp mới là yếu tố quyết định.

## 8. CompletableFuture và executor dành riêng cho CPU

Các phương thức async của CompletableFuture cho phép thực hiện một bước tính toán trên executor. Nếu không truyền executor vào các phương thức như supplyAsync hoặc thenApplyAsync, chúng thường sử dụng ForkJoinPool.commonPool().

Với ứng dụng có nhiều loại workload, nên truyền executor rõ ràng để tách công việc CPU khỏi các tác vụ khác:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

int parallelism = Math.max(
        1,
        Runtime.getRuntime().availableProcessors()
);

try (var cpuExecutor = new ThreadPoolExecutor(
        parallelism,
        parallelism,
        0L,
        TimeUnit.MILLISECONDS,
        new ArrayBlockingQueue<>(200),
        new ThreadPoolExecutor.AbortPolicy()
)) {
    CompletableFuture<Long> result =
            CompletableFuture.supplyAsync(
                    () -> calculateRange(0, 1_000_000),
                    cpuExecutor
            ).thenApplyAsync(
                    value -> normalize(value),
                    cpuExecutor
            );

    System.out.println(result.get());
}
```

Executor trong ví dụ có số worker cố định, queue hữu hạn và từ chối tường minh khi hết capacity. Tầng gọi cần xử lý `RejectedExecutionException` nếu việc submit có thể xảy ra khi executor đã đầy hoặc đang shutdown.

Các stage không có hậu tố Async có thể chạy trên thread hoàn thành stage trước đó hoặc thread hoàn tất thao tác CompletableFuture. Các stage Async không truyền executor sẽ dùng executor mặc định của CompletableFuture. Hãy truyền executor tường minh cho các bước CPU nặng cần cách ly.

Tránh thiết kế task trong cùng một pool vừa submit task con vừa block chờ task con khi tất cả worker có thể bị chiếm bởi task cha. Điều đó có thể gây starvation hoặc deadlock tùy cấu trúc pool. Với ForkJoinTask, dùng fork/join theo mô hình của ForkJoinPool; với ThreadPoolExecutor, tránh chờ đồng bộ các task con trong cùng pool có worker hữu hạn.

## 9. Vì sao virtual thread không phải lựa chọn tối ưu cho CPU-bound?

Virtual thread được thiết kế để xử lý nhiều tác vụ có thời gian chờ, đặc biệt là blocking I/O. Một tác vụ CPU-bound liên tục không thường xuyên park, nên virtual thread vẫn cần carrier để thực thi phép tính.

Nếu tạo hàng chục nghìn virtual thread chỉ để tính toán:

- Số phép tính chạy song song vẫn bị giới hạn bởi số carrier và CPU khả dụng.
- Các virtual thread còn lại chờ được scheduler chạy, không tạo thêm năng lực CPU.
- Trạng thái task và bộ nhớ vẫn phải được quản lý.
- Khó giới hạn số phép tính đồng thời theo một queue có capacity nếu chỉ dùng virtual-thread-per-task executor.

Không nên điều chỉnh scheduler parallelism của virtual thread để thay thế giới hạn CPU ở tầng ứng dụng. Scheduler là cơ chế thực thi virtual thread; nó không phải admission control cho từng nhóm tác vụ CPU-bound.

Có thể dùng virtual thread trong một request xử lý I/O rồi gọi một executor CPU-bound riêng cho đoạn tính toán. Cách này tách rõ hai loại tài nguyên:

- Virtual thread điều phối request và chờ I/O.
- Executor CPU-bound giới hạn số phép tính đang chạy đồng thời.

## 10. Chia nhỏ task và tránh contention

Để khai thác CPU tốt, mỗi task nên có lượng công việc đủ lớn để chi phí lập lịch không lấn át phần tính toán. Nếu task chỉ thực hiện vài phép toán rồi submit task khác, overhead có thể cao hơn lợi ích song song.

Các nguyên tắc hữu ích:

- Chia dữ liệu thành các chunk có kích thước hợp lý.
- Ưu tiên task độc lập, mỗi task xử lý một phân vùng riêng.
- Hạn chế ghi vào cùng một biến mutable từ nhiều worker.
- Dùng kết quả cục bộ rồi kết hợp ở cuối thay vì lock trên từng phép tính.
- Tránh tạo object trung gian quá nhiều trong vòng lặp nóng.
- Đo nhiều kích thước chunk và số worker để tìm điểm cân bằng.

Ví dụ, khi tính tổng mảng, mỗi task có thể tính tổng một đoạn riêng. Sau đó kết hợp các tổng con. Cách này giảm contention so với việc mọi worker liên tục cập nhật cùng một biến tổng dùng chung.

Nếu thuật toán bị giới hạn bởi băng thông bộ nhớ, tăng số worker vượt một ngưỡng có thể không cải thiện throughput. Đây là lý do phải benchmark trên dữ liệu và phần cứng đại diện.

## 11. Hủy task và shutdown

CPU-bound task không tự dừng ngay khi Future bị cancel. Khi gọi `cancel(true)`, executor yêu cầu interrupt thread đang chạy task. Code tính toán cần chủ động kiểm tra interrupt nếu có thể bị hủy:

```java
long calculate(int limit) {
    long result = 0;

    for (int i = 0; i < limit; i++) {
        if (Thread.currentThread().isInterrupted()) {
            throw new java.util.concurrent.CancellationException();
        }

        result += expensiveCalculation(i);
    }

    return result;
}
```

Không nên kiểm tra interrupt quá dày trong vòng lặp siêu nhỏ nếu chi phí đó ảnh hưởng đáng kể đến thuật toán; có thể kiểm tra theo từng block công việc. Khi hủy, hãy xác định dữ liệu trung gian có thể bỏ đi hay cần dọn dẹp.

Với executor sống lâu, quy trình shutdown thường gồm:

1. Ngừng nhận task mới bằng shutdown().
2. Chờ task đang chạy và task trong queue hoàn tất bằng awaitTermination().
3. Nếu quá thời hạn, gọi shutdownNow() để yêu cầu interrupt các task đang chạy và lấy lại task chưa bắt đầu.
4. Bảo đảm ứng dụng ghi nhận task bị từ chối hoặc bị hủy.

Không giả định interrupt sẽ dừng được một phép tính nếu task bỏ qua cờ interrupt.

## 12. Đo lường và điều chỉnh parallelism

Chọn số worker bằng availableProcessors là điểm khởi đầu. Để điều chỉnh, hãy chạy benchmark đại diện với nhiều mức song song, ví dụ:

- 1 worker.
- Một nửa số processor khả dụng.
- Xấp xỉ số processor khả dụng.
- Một mức cao hơn vừa phải để kiểm tra hiện tượng oversubscription.

Theo dõi các chỉ số:

| Chỉ số | Câu hỏi cần trả lời |
|---|---|
| Throughput | Mỗi giây hoàn thành bao nhiêu task? |
| CPU utilization | CPU có được sử dụng hiệu quả hay đã bão hòa? |
| Task queue depth | Queue có tăng liên tục hay thường xuyên đầy? |
| Rejection count | Có bao nhiêu task bị từ chối? |
| p50/p95/p99 latency | Thời gian hoàn tất có ổn định khi tải tăng không? |
| Context switches | Có tăng mạnh khi số worker tăng không? |
| Allocation và GC | Task có tạo quá nhiều object hoặc áp lực bộ nhớ không? |
| Lock contention | Worker có dành nhiều thời gian chờ lock không? |

Benchmark nên dùng dữ liệu đại diện, chạy đủ lâu để JVM warm up và lặp lại nhiều lần. Tránh kết luận từ một lần chạy ngắn hoặc chỉ nhìn CPU utilization. CPU đạt 100% không tự động có nghĩa throughput đang tối ưu.

## 13. Những lỗi thiết kế thường gặp

| Sai lầm | Hệ quả | Cách khắc phục |
|---|---|---|
| Tạo hàng nghìn thread cho CPU-bound task | Oversubscription và context switching | Giới hạn worker theo CPU khả dụng |
| Dùng virtual-thread-per-task cho phép tính thuần CPU | Không tăng năng lực CPU, task cạnh tranh carrier | Dùng executor CPU-bound có parallelism hữu hạn |
| Dùng fixed thread pool với queue không giới hạn cho tải không kiểm soát | Backlog và bộ nhớ tăng liên tục | Dùng ThreadPoolExecutor với queue hữu hạn |
| Dùng ForkJoinPool cho task blocking lâu | Worker bị giữ, giảm parallelism | Tách I/O khỏi task CPU hoặc dùng executor phù hợp |
| Chia task quá nhỏ | Overhead lập lịch lớn | Benchmark và tăng kích thước chunk |
| Mọi worker cập nhật cùng dữ liệu mutable | Lock contention và cache contention | Phân vùng dữ liệu, tổng hợp kết quả cục bộ |
| Không xử lý RejectedExecutionException | Task bị từ chối không được phản hồi đúng | Thiết kế admission/rejection policy rõ ràng |
| Chờ task con đồng bộ trong pool hữu hạn | Starvation hoặc deadlock | Dùng fork/join đúng mô hình hoặc thiết kế pipeline không block |

## 14. Quy trình chọn executor cho CPU-bound task

Có thể áp dụng quy trình sau:

1. Xác nhận task thực sự CPU-bound bằng profiling hoặc đo tỷ lệ thời gian CPU so với thời gian chờ.
2. Đọc số processor khả dụng bằng Runtime.getRuntime().availableProcessors().
3. Chọn ThreadPoolExecutor với số worker hữu hạn cho task độc lập, hoặc ForkJoinPool cho thuật toán chia để trị.
4. Nếu dùng ThreadPoolExecutor, đặt queue capacity và RejectedExecutionHandler theo chính sách tải.
5. Tách workload CPU khỏi I/O và các nhóm công việc có SLA khác nhau.
6. Giảm contention bằng phân vùng dữ liệu và kết quả cục bộ.
7. Đo throughput, latency, queue depth, rejection, context switching và GC.
8. Điều chỉnh parallelism, queue capacity và chunk size theo kết quả benchmark.
9. Thiết kế timeout, cancellation và shutdown để task không tồn tại ngoài vòng đời mong muốn.

## Kết luận

Với tác vụ CPU-bound trong Java 21, mức song song nên gắn với số processor khả dụng và đặc điểm thực tế của thuật toán. ThreadPoolExecutor có worker cố định cùng queue hữu hạn phù hợp cho task độc lập cần kiểm soát tải; ForkJoinPool phù hợp với công việc chia để trị và work-stealing. Virtual thread giúp xử lý nhiều tác vụ blocking, nhưng không làm phép tính CPU chạy nhanh hơn và không thay thế executor có giới hạn song song. Hãy đo workload, kiểm soát queue và rejection, giảm contention rồi điều chỉnh số worker dựa trên throughput và latency.

## Tài liệu tham khảo

- [Java SE 21 API — ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)
- [Java SE 21 API — ForkJoinPool](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ForkJoinPool.html)
- [Java SE 21 API — RecursiveTask](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/RecursiveTask.html)
- [Java SE 21 API — ExecutorService](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html)
- [Java SE 21 API — CompletableFuture](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [Java SE 21 API — Runtime.availableProcessors()](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Runtime.html)
- [JEP 444 — Virtual Threads](https://openjdk.org/jeps/444)
