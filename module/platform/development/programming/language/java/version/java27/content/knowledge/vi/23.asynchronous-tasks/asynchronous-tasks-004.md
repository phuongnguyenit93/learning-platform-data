# Chọn executor và tránh chặn common pool trong Java 27

**Executor** là thành phần quyết định một tác vụ được thực thi ở đâu và được lên lịch ra sao. Trong Java, việc gọi `CompletableFuture.supplyAsync(...)`, chạy `parallelStream()` hoặc gửi tác vụ vào `ExecutorService` đều có thể tạo công việc bất đồng bộ, nhưng **không có nghĩa mọi lựa chọn executor đều phù hợp với mọi loại tải**.

Một lỗi thiết kế phổ biến là gửi nhiều tác vụ **chặn lâu** (đọc mạng, chờ database, `Thread.sleep`, chờ future khác) vào `ForkJoinPool.commonPool()`. Vì common pool là tài nguyên dùng chung và chủ yếu được tối ưu cho công việc có thể tiến triển nhờ các worker sẵn có, việc chặn không kiểm soát có thể làm các tác vụ không liên quan bị chậm hoặc không còn worker để tiến triển.

Bài học thuộc chương **Tác vụ bất đồng bộ** của module **Java 27 và các kiến thức liên quan**. Nội dung sử dụng các API Java chính thức đang được hỗ trợ, gồm `Executor`, `ExecutorService`, `Executors`, `ThreadPoolExecutor`, `ForkJoinPool`, `CompletableFuture` và **virtual threads**. Không dựa trên tính năng preview hoặc API nội bộ để giải quyết vấn đề này.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt công việc **CPU-bound**, **blocking I/O-bound** và công việc **thực sự bất đồng bộ/không cần chặn thread gọi**.
2. Giải thích vai trò của `Executor`, `ExecutorService`, `ForkJoinPool` và common pool.
3. Biết khi nào `CompletableFuture` sử dụng executor mặc định, khi nào cần truyền executor tường minh.
4. Tránh gọi `join()`/`get()` hoặc các API chặn không cần thiết trong common-pool worker.
5. Chọn fixed pool cho công việc CPU, virtual-thread-per-task executor cho nhiều tác vụ blocking phù hợp, và thread pool có giới hạn khi cần backpressure.
6. Xây pipeline `CompletableFuture` bằng `thenApply`, `thenCompose`, `thenCombine` và các biến thể `Async` phù hợp.
7. Phân biệt timeout/completion/cancellation của future với việc dừng **thực sự** công việc đang chạy.
8. Thiết kế vòng đời executor, giới hạn tài nguyên, xử lý lỗi và quan sát hệ thống.
9. Áp dụng các quy tắc qua ví dụ Java tự chứa và bài tập thực hành.

## 2. Bất đồng bộ không đồng nghĩa song song hay không chặn

Ba khái niệm cần tách bạch:

| Khái niệm | Câu hỏi | Ví dụ |
|---|---|---|
| **Asynchronous** | Caller có phải chờ tác vụ hoàn tất ngay ở lời gọi không? | `CompletableFuture.supplyAsync(...)` trả future trước khi tác vụ xong |
| **Parallel** | Nhiều tác vụ có thể chạy cùng thời điểm không? | Các tác vụ CPU chạy trên nhiều core |
| **Non-blocking** | Đường đi thực thi có cần giữ thread bị chặn để chờ tiến triển không? | API I/O bất đồng bộ không cần giữ một thread chờ dữ liệu trong lúc chờ |

Một `CompletableFuture` có thể bất đồng bộ đối với caller nhưng task bên trong lại đang **block thread worker**:

```java
CompletableFuture<String> future = CompletableFuture.supplyAsync(() -> {
    try {
        Thread.sleep(100); // Chặn thread thực thi tác vụ trong khoảng này.
        return "done";
    } catch (InterruptedException exception) {
        Thread.currentThread().interrupt();
        throw new java.util.concurrent.CompletionException(exception);
    }
});
```

Lời gọi `supplyAsync` thường trả ngay; nhưng `Thread.sleep` vẫn là thao tác blocking trong lambda. Nếu không truyền executor, tác vụ này thường sử dụng common pool theo chính sách của `CompletableFuture`.

Đối với virtual thread, nhiều thao tác blocking hỗ trợ việc nhường carrier thread, nên chi phí chờ khác platform thread. Tuy nhiên, **API blocking vẫn có hành vi chờ** và không tự đảm bảo thời gian hoàn tất hay quyền truy cập tài nguyên bên ngoài.

## 3. Ba kiểu workload thường gặp

### 3.1. CPU-bound

Tác vụ tiêu thụ phần lớn thời gian để tính toán: mã hóa, hash, phân tích ảnh, tính quy tắc nặng hoặc thuật toán trên tập số lớn.

Đặc điểm:

- Nhu cầu chạy đồng thời thực tế thường bị giới hạn bởi số core và ngân sách CPU.
- Tạo quá nhiều thread có thể tăng context switching, contention và giảm throughput.
- Một executor với số worker có giới hạn hợp lý thường là điểm bắt đầu tốt.

Ví dụ:

```java
static long sumSquares(int start, int end) {
    long result = 0;
    for (int value = start; value < end; value++) {
        result += (long) value * value;
    }
    return result;
}
```

### 3.2. Blocking I/O-bound

Tác vụ dành nhiều thời gian **chờ** kết quả từ database, mạng, file hoặc một nguồn ngoài.

Ví dụ:

```java
static String simulatedRemoteCall(String id) {
    try {
        Thread.sleep(100); // Giả lập chờ I/O, không phải HTTP thật.
        return "data-" + id;
    } catch (InterruptedException exception) {
        Thread.currentThread().interrupt();
        throw new java.util.concurrent.CompletionException(exception);
    }
}
```

Tác vụ loại này không cần CPU liên tục, nhưng nếu chạy trên các **platform worker** có số lượng nhỏ, chờ đợi vẫn chiếm worker.

### 3.3. I/O thực sự có API bất đồng bộ

Một số API trả future hoặc cung cấp callback mà không yêu cầu bạn tự bọc lời gọi blocking vào `supplyAsync`. Ví dụ `java.net.http.HttpClient.sendAsync`:

```java
// Minh họa ý tưởng; cần tạo HttpClient/HttpRequest thật để chạy.
// CompletableFuture<HttpResponse<String>> response =
//         httpClient.sendAsync(request, BodyHandlers.ofString());
```

Nếu thư viện đã có API async phù hợp, không nhất thiết tạo thêm một thread chỉ để chờ `get()` trên future của chính API đó. Thường nên **kết hợp các stage bằng callback/future composition** và xác định rõ executor cho bước xử lý CPU nặng.

## 4. Executor, ExecutorService và ThreadFactory

### 4.1. Executor

`Executor` chỉ có một phương thức quan trọng:

```java
void execute(Runnable command);
```

Đây là hợp đồng gửi công việc đến một bộ thực thi, không mặc định quy định công việc phải chạy trên thread khác. Một executor có thể chạy ngay trên caller thread, tạo thread mới, hoặc sử dụng worker pool.

### 4.2. ExecutorService

`ExecutorService` mở rộng khả năng quản lý tác vụ và vòng đời:

- `submit(Callable<T>)` trả `Future<T>`.
- `submit(Runnable)` trả future biểu thị hoàn tất.
- `shutdown()` ngừng nhận tác vụ mới, cho phép các tác vụ đã nhận tiếp tục theo hợp đồng.
- `shutdownNow()` cố dừng tác vụ đang chạy và lấy lại danh sách tác vụ chưa bắt đầu.
- `awaitTermination(...)` hỗ trợ đợi executor kết thúc theo thời gian giới hạn.
- `close()` được hỗ trợ bởi `ExecutorService` trong Java hiện hành; dùng try-with-resources khi muốn chờ các tác vụ hoàn tất và giải phóng pool.

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

try (ExecutorService executor = Executors.newSingleThreadExecutor()) {
    Future<Integer> result = executor.submit(() -> 40 + 2);
    System.out.println(result.get()); // 42
}
```

Đây là một ví dụ đầy đủ về cú pháp khi đặt vào một method có khai báo/bắt các checked exception của `Future.get()`. `get()` **chặn thread gọi** cho đến khi có kết quả hoặc lỗi phù hợp.

### 4.3. ThreadFactory

`ThreadFactory` quyết định cách tạo thread cho một số executor, chẳng hạn dùng tên dễ quan sát hoặc chính sách riêng. Nó **không** tự giới hạn số tác vụ đang chờ hay làm bộ thực thi trở thành thread-safe theo một cơ chế mới.

Đối với virtual threads, Java cung cấp executor có mục đích rõ ràng, thường không cần tự xây `ThreadFactory` để quản lý vòng đời.

## 5. ForkJoinPool và work stealing

`ForkJoinPool` được thiết kế để thực thi công việc có thể chia nhỏ (*fork*) rồi tổng hợp kết quả (*join*). Các worker có thể **work-steal**: một worker lấy công việc phù hợp từ queue của worker khác để tận dụng năng lực xử lý.

Tình huống thường phù hợp:

- Thuật toán chia để trị có nhiều nhánh tính toán CPU.
- Nhiều tác vụ nhỏ độc lập có thể xử lý song song.
- Các bước tính toán không phải chờ I/O chậm ngoài kiểm soát.

Một fork/join task dùng `RecursiveTask<T>` có thể có dạng:

```java
import java.util.concurrent.RecursiveTask;

final class SumTask extends RecursiveTask<Long> {
    private static final int THRESHOLD = 1_000;

    private final int from;
    private final int to;

    SumTask(int from, int to) {
        this.from = from;
        this.to = to;
    }

    @Override
    protected Long compute() {
        if (to - from <= THRESHOLD) {
            long result = 0;
            for (int i = from; i < to; i++) {
                result += i;
            }
            return result;
        }

        int middle = (from + to) / 2;
        SumTask left = new SumTask(from, middle);
        SumTask right = new SumTask(middle, to);

        left.fork();
        long rightResult = right.compute();
        return left.join() + rightResult;
    }
}
```

Lời gọi `left.join()` ở đây thuộc mô hình phối hợp fork/join **có liên quan trực tiếp đến task được fork**. Đừng đồng nhất nó với việc đặt `future.join()` để chờ một hoạt động I/O tùy ý trên common pool.

## 6. Common pool là gì và tại sao cần thận trọng?

`ForkJoinPool.commonPool()` là một pool dùng chung trong JVM cho những công việc lựa chọn cơ chế thực thi mặc định của nó. Các thư viện và code khác nhau có thể cùng sử dụng tài nguyên này.

```java
import java.util.concurrent.ForkJoinPool;

ForkJoinPool common = ForkJoinPool.commonPool();

System.out.println(common.getParallelism());
```

`getParallelism()` cung cấp mức target parallelism được cấu hình, **không phải lời hứa rằng từng thời điểm có đúng bấy nhiêu task chạy**. Giá trị có thể bị ảnh hưởng bởi cấu hình môi trường và thuộc tính hệ thống; không hard-code giả định "common pool luôn có N core - 1 worker".

### 6.1. Các API thường liên quan đến common pool

- `CompletableFuture.runAsync(runnable)` và `supplyAsync(supplier)` **không truyền Executor** thường dùng `ForkJoinPool.commonPool()`.
- Những biến thể `Async` của `CompletableFuture` không truyền executor thường dùng **default asynchronous execution facility** của stage; với một `CompletableFuture` thông thường, cơ chế đó là common pool trong điều kiện bình thường.
- `parallelStream()` và `stream.parallel()` thường sử dụng cơ chế fork/join, và trong cách gọi phổ biến từ thread thông thường là common pool.

**Ngoại lệ kỹ thuật cần biết:** theo đặc tả `CompletableFuture`, các async method không nhận executor sử dụng common pool **trừ khi** common pool không hỗ trợ parallelism ít nhất 2; trong trường hợp đó có thể tạo thread mới cho từng task. Vì vậy không suy rằng mọi máy và cấu hình đều dùng cùng số worker hay cùng thread name.

### 6.2. Common pool không thuộc riêng một request

Nếu request A dùng common pool để xử lý ảnh, request B cũng dùng common pool để chạy phép biến đổi và một thư viện C dùng parallel stream, những công việc đó có thể cạnh tranh cùng nguồn lực.

Khi nhiều tác vụ chặn lâu lấp đầy worker, các task khác có thể chờ lâu không lường trước. Vấn đề là **cô lập tài nguyên và tiến triển toàn hệ thống**, không chỉ là kết quả của một phương thức đơn lẻ.

### 6.3. Không shutdown common pool để "dọn dẹp"

Không gọi `ForkJoinPool.commonPool().shutdown()` như cách quản lý vòng đời một pool do chính ứng dụng tạo. Common pool là tài nguyên dùng chung do runtime quản lý; `shutdown()`/`shutdownNow()` trên common pool không có hiệu lực dừng theo cách áp dụng với pool riêng.

Nếu cần quyền kiểm soát lifecycle, **tạo executor riêng** và đóng nó tại ranh giới có chủ sở hữu rõ ràng.

## 7. Vì sao chặn common pool gây giảm throughput?

Giả sử một common pool có số worker hữu hạn và mỗi worker thực hiện:

```java
CompletableFuture<String> result = CompletableFuture.supplyAsync(() -> {
    return blockingServiceCall(); // Một lời gọi blocking thật.
});
```

Trong ví dụ, `blockingServiceCall()` là tên phương thức minh họa, không phải API chuẩn. Nếu tác vụ chờ network hàng giây, worker bị giữ trong thời gian chờ. Khi số tác vụ như vậy nhiều, các tác vụ CPU nhẹ cũng có thể phải xếp hàng.

Một biểu đồ đơn giản:

```text
ForkJoinPool.commonPool
  worker-1 -> [chờ database................]
  worker-2 -> [chờ HTTP....................]
  worker-3 -> [chờ Future.get()............]
  worker-4 -> [chờ file/lock................]
  queue    -> [CPU stage] [callback] [task khác] ...
```

Vấn đề không phải **mỗi thao tác blocking đều tạo deadlock**, mà là **đưa sự chờ đợi khó kiểm soát vào tài nguyên chia sẻ cho nhiều tác vụ khác nhau** làm tăng nguy cơ starvation, tail latency và phụ thuộc chéo.

### 7.1. ForkJoinPool có cơ chế hỗ trợ managed blocking

`ForkJoinPool.ManagedBlocker` và `ForkJoinPool.managedBlock(...)` là API được hỗ trợ để giúp pool nhận biết một số thao tác blocking, từ đó có thể bù đắp worker khi cần.

Tuy nhiên:

- Không phải mọi hoạt động I/O hoặc `Future.get()` tùy ý đều được biến thành managed blocking đúng cách.
- Cơ chế bù worker có giới hạn tài nguyên và không tự bảo đảm ứng dụng không bị starvation.
- Để hệ thống có nhiều lời gọi blocking độc lập, việc chọn một executor phù hợp ngay từ đầu thường dễ hiểu và dễ vận hành hơn.

Do đó, **ManagedBlocker là công cụ cấp thấp có điều kiện**, không phải cách chữa chung cho việc đưa mọi tác vụ I/O vào common pool.

## 8. Quy tắc chọn executor theo workload

| Loại công việc | Lựa chọn khởi đầu | Điều cần kiểm soát |
|---|---|---|
| Tính toán CPU độc lập, dài vừa phải | `Executors.newFixedThreadPool(...)` | Số worker gần ngân sách CPU, hàng đợi |
| Thuật toán chia để trị | `ForkJoinPool` riêng hoặc thiết kế fork/join thích hợp | Mức parallelism, độ mịn task, tránh blocking lâu |
| Nhiều lời gọi I/O blocking độc lập | `Executors.newVirtualThreadPerTaskExecutor()` | Số kết nối/requests đồng thời, timeout |
| Blocking I/O với platform threads có hạn | `ThreadPoolExecutor` riêng, queue hữu hạn | Backpressure, reject policy, task cancellation |
| Công việc chỉ được thực thi tuần tự | `Executors.newSingleThreadExecutor()` | Task chặn, lifecycle, deadlock nếu tự chờ |
| Tác vụ chạy theo thời gian | `ScheduledThreadPoolExecutor` / `newScheduledThreadPool` | Không chặn scheduler lâu, chính sách retry |
| I/O có API thực sự async | API async và future composition | Callback, timeout, xử lý lỗi, CPU-heavy stages |
| Các bước nhỏ, CPU-bound không cần cô lập | Có thể dùng common pool có chủ đích | Ảnh hưởng tới phần còn lại của JVM |

Không có công thức pool size duy nhất cho mọi ứng dụng. Nếu chỉ có vài core và công việc CPU dày đặc, nhiều hơn hàng trăm platform worker thường không giúp nhanh hơn. Với I/O có độ trễ cao, concurrency hữu ích có thể lớn hơn số core nhưng cần giới hạn theo tài nguyên thật.

### 8.1. Chọn trên cơ sở sở hữu tài nguyên

Một module thư viện không nên tự ý tạo hàng chục pool rồi để chúng sống mãi. Với API có công việc đáng kể, cân nhắc **nhận `Executor` hoặc `ExecutorService` từ caller**:

```java
final class TaskService {
    private final java.util.concurrent.Executor executor;

    TaskService(java.util.concurrent.Executor executor) {
        this.executor = java.util.Objects.requireNonNull(executor);
    }

    java.util.concurrent.CompletableFuture<String> runTask() {
        return java.util.concurrent.CompletableFuture.supplyAsync(
                () -> "result",
                executor
        );
    }
}
```

Như vậy application owner quyết định giới hạn, vòng đời, monitoring và môi trường test. Nếu chỉ nhận `Executor`, class này **không sở hữu quyền shutdown** một executor có thể được chia sẻ.

## 9. Fixed thread pool dành cho CPU: ưu và nhược điểm

`Executors.newFixedThreadPool(n)` tạo executor với số platform worker cố định hoặc tối đa trong pool theo contract, tái sử dụng chúng cho nhiều tác vụ.

```java
int cpuWorkers = Math.max(1,
        Runtime.getRuntime().availableProcessors() - 1);

try (var cpuExecutor =
        java.util.concurrent.Executors.newFixedThreadPool(cpuWorkers)) {

    var task = java.util.concurrent.CompletableFuture.supplyAsync(
            () -> 2 * 21,
            cpuExecutor
    );

    System.out.println(task.join()); // 42
}
```

`availableProcessors() - 1` ở đây là **heuristic minh họa**, không phải quy tắc cứng: môi trường container, giới hạn CPU, nhu cầu dành core cho tác vụ khác và đặc tính workload có thể làm lựa chọn khác phù hợp hơn.

### 9.1. Cảnh báo: fixed thread pool có queue không giới hạn

`Executors.newFixedThreadPool` dùng một queue không có giới hạn sức chứa hữu hạn do ứng dụng cấu hình trực tiếp qua factory đó. Nếu producer gửi task nhanh hơn worker xử lý, queue có thể tăng và làm hệ thống tốn bộ nhớ.

Khi cần bảo vệ trước lượng request đột biến, dùng:

- `ThreadPoolExecutor` tự cấu hình queue hữu hạn.
- Semaphore hoặc một tầng backpressure ở trước khi submit.
- Cơ chế từ chối có kiểm soát và thông báo cho caller.

**Giới hạn số worker không tự giới hạn số task đang chờ.**

## 10. Virtual thread per task cho blocking I/O

Từ Java 21, virtual threads là tính năng ổn định. `Executors.newVirtualThreadPerTaskExecutor()` tạo một virtual thread mới cho mỗi task mà executor nhận, thay vì tái sử dụng một nhóm nhỏ platform worker cho tất cả công việc.

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

try (ExecutorService io =
        Executors.newVirtualThreadPerTaskExecutor()) {

    Future<String> first = io.submit(() -> simulatedRemoteCall("A"));
    Future<String> second = io.submit(() -> simulatedRemoteCall("B"));

    System.out.println(first.get());
    System.out.println(second.get());
}
```

Đoạn trên sử dụng `simulatedRemoteCall` đã định nghĩa ở mục 3 và cần được đặt cùng method/helper; `get()` nằm ở điểm điều phối trên caller thread.

### 10.1. Vì sao phù hợp với nhiều tác vụ blocking?

Virtual thread có chi phí tạo và giữ trạng thái chờ thấp hơn platform thread trong nhiều trường hợp. Với các thao tác blocking được JDK hỗ trợ, virtual thread có thể nhường carrier thread để carrier phục vụ virtual thread khác.

Điều này có lợi khi cần viết code tuần tự dễ đọc (ví dụ `httpClient.send(...)` hoặc JDBC blocking) nhưng phải xử lý rất nhiều công việc độc lập chờ I/O.

### 10.2. Không pool virtual threads theo cách pool platform threads

Ý tưởng của virtual-thread-per-task executor là **mỗi task có một virtual thread**. Không nên cố giữ cố định một số lượng nhỏ virtual threads nhằm tối ưu hóa việc tái sử dụng như platform workers.

**Giới hạn concurrency tại tài nguyên bị bảo vệ**, ví dụ số connection database, số HTTP request đang bay hoặc giới hạn đối tác, thường đúng hơn.

### 10.3. Virtual thread không làm CPU chạy nhanh hơn

Nếu 10.000 virtual threads đều tính toán CPU liên tục, số core vẫn có hạn. Virtual threads giúp mô hình **nhiều tác vụ chờ** có thể mở rộng hơn, không tạo thêm năng lực CPU.

Đồng thời không giả định mọi lời gọi native/library blocking đều có hành vi giống nhau. Hiệu quả phụ thuộc API và JDK; **không dựa vào những hạn chế pinning của phiên bản cũ như một quy tắc bất biến của Java 27**.

## 11. Giới hạn I/O concurrency bằng Semaphore

Virtual-thread-per-task executor không tự giới hạn số request gửi tới một dịch vụ bên ngoài. Nếu gọi đồng thời quá nhiều, dịch vụ có thể trả lỗi, áp dụng rate limit hoặc hết connection.

`Semaphore` cho phép giới hạn **số tác vụ đi vào một vùng có tài nguyên hữu hạn**:

```java
import java.util.concurrent.Semaphore;

Semaphore permits = new Semaphore(8);

static String withPermit(Semaphore permits, String id) {
    boolean acquired = false;

    try {
        permits.acquire();
        acquired = true;
        return simulatedRemoteCall(id);
    } catch (InterruptedException exception) {
        Thread.currentThread().interrupt();
        throw new java.util.concurrent.CompletionException(exception);
    } finally {
        if (acquired) {
            permits.release();
        }
    }
}
```

Phần trên là các đoạn minh họa đặt trong một class thích hợp. `Semaphore(8)` giới hạn tối đa 8 task cùng giữ permit trong một thời điểm; **nó không phải bộ giới hạn 8 request/giây**.

### 11.1. Tránh quên release khi lỗi

Nếu đã acquire permit nhưng task ném exception, `finally` phải giải phóng permit. Nếu acquire bị ngắt trước khi thành công, không được `release` một permit chưa sở hữu. Biến `acquired` trong ví dụ phân biệt hai trường hợp này.

### 11.2. Queue phía trước semaphore vẫn có thể tăng

Semaphore giới hạn vùng I/O đang chạy, nhưng nếu cứ tạo vô hạn futures/virtual threads chờ permit thì vẫn tiêu tốn bộ nhớ và tài nguyên điều phối. Với hệ thống nhận request không giới hạn, cần thêm backpressure hoặc giới hạn admission ở cấp trước đó.

## 12. CompletableFuture không truyền Executor sẽ chạy ở đâu?

Ví dụ:

```java
import java.util.concurrent.CompletableFuture;

CompletableFuture<String> future =
        CompletableFuture.supplyAsync(() -> "hello");
```

Với `CompletableFuture` thông thường và cấu hình common pool phổ biến, supplier được lên lịch trên common pool.

Nếu task có khả năng **blocking dài**, nên chỉ định executor:

```java
CompletableFuture<String> future =
        CompletableFuture.supplyAsync(
                () -> simulatedRemoteCall("customer"),
                ioExecutor
        );
```

`ioExecutor` ở đây là một `Executor` có chủ sở hữu rõ ràng, phù hợp với blocking I/O. Đoạn là snippet minh họa; phải khai báo, quản lý và đóng executor ở ngữ cảnh thực tế.

### 12.1. Từng stage có thể có executor khác nhau

Các method cần phân biệt:

| Method | Có hậu tố Async? | Mặc định về thread chạy hành động |
|---|---|---|
| `thenApply(fn)` | Không | Có thể chạy trên thread hoàn tất stage trước hoặc thread khác tham gia hoàn tất |
| `thenApplyAsync(fn)` | Có | Dùng default async execution facility của stage |
| `thenApplyAsync(fn, executor)` | Có | Dùng executor truyền vào |
| `thenCompose(fn)` | Không | Áp dụng composition không yêu cầu chuyển executor |
| `thenComposeAsync(fn, executor)` | Có | Chạy function tạo future qua executor truyền vào |
| `whenComplete(action)` | Không | Callback có thể chạy trên thread hoàn tất |
| `whenCompleteAsync(action, executor)` | Có | Chạy callback qua executor truyền vào |

**Đừng dựa vào tên thread quan sát được trong một lần chạy** để suy ra quy tắc lên lịch bất biến. Với non-async dependent methods, `CompletableFuture` cho phép hành động chạy bởi thread hoàn tất future hiện tại hoặc thread khác tham gia completion.

### 12.2. Một executor ở stage đầu không tự áp dụng cho mọi stage

Ví dụ:

```java
CompletableFuture<String> future =
        CompletableFuture.supplyAsync(
                () -> simulatedRemoteCall("A"),
                ioExecutor
        ).thenApplyAsync(
                value -> value.toUpperCase()
        );
```

Trong một `CompletableFuture` bình thường, `thenApplyAsync(...)` không có đối số executor sẽ dùng **default async executor** của stage, thường là common pool — **không tự kế thừa `ioExecutor`** của supplier.

Nếu bước chuyển đổi tốn nhiều CPU và cần cô lập tài nguyên:

```java
CompletableFuture<String> future =
        CompletableFuture.supplyAsync(
                () -> simulatedRemoteCall("A"),
                ioExecutor
        ).thenApplyAsync(
                String::toUpperCase,
                cpuExecutor
        );
```

Nếu bước chuyển đổi cực rẻ, `thenApply` không-async có thể giảm overhead chuyển executor; hãy hiểu rằng nó có thể chạy trên thread đang hoàn tất I/O.

## 13. Tránh chặn trong callback của CompletableFuture

Một anti-pattern dễ gặp:

```java
// KHÔNG nên: có thể chặn worker thực thi callback.
// CompletableFuture<String> result = CompletableFuture
//         .supplyAsync(() -> blockingCallA())
//         .thenApply(a -> {
//             return otherFuture.get(); // Chờ blocking ngay trong callback.
//         });
```

Nếu common-pool worker đang chờ một future mà công việc tạo kết quả cũng cần common pool, ta có thể làm tài nguyên bị cạn, giảm throughput hoặc tạo vòng phụ thuộc không thể tiến triển.

### 13.1. thenCompose thay cho future lồng trong future

Khi một bước đã trả `CompletionStage<R>`, dùng `thenCompose` để nối tiếp:

```java
CompletableFuture<String> result = CompletableFuture
        .supplyAsync(() -> "customer-42", ioExecutor)
        .thenCompose(customerId ->
                CompletableFuture.supplyAsync(
                        () -> simulatedRemoteCall(customerId),
                        ioExecutor
                )
        );
```

`thenCompose` tạo một stage đại diện cho việc hoàn tất của stage bên trong, không cần caller dùng `join()` ngay giữa các callback để "mở" future.

Ngược lại, `thenApply` với function trả future có thể tạo kiểu lồng:

```java
CompletableFuture<CompletableFuture<String>> nested =
        CompletableFuture.supplyAsync(
                () -> "customer-42",
                ioExecutor
        ).thenApply(id ->
                CompletableFuture.supplyAsync(
                        () -> simulatedRemoteCall(id),
                        ioExecutor
                )
        );
```

Khi mục tiêu là kết quả cuối cùng `String`, `thenCompose` thường phù hợp hơn.

### 13.2. thenCombine cho hai kết quả độc lập

`thenCombine` chạy function kết hợp khi **cả hai stage đã hoàn tất bình thường**:

```java
CompletableFuture<String> left =
        CompletableFuture.supplyAsync(
                () -> simulatedRemoteCall("left"),
                ioExecutor
        );

CompletableFuture<String> right =
        CompletableFuture.supplyAsync(
                () -> simulatedRemoteCall("right"),
                ioExecutor
        );

CompletableFuture<String> combined =
        left.thenCombine(right, (a, b) -> a + "|" + b);
```

Function kết hợp không cần chặn để chờ từng future: framework chỉ thực thi khi hai kết quả đã có. Nếu phép kết hợp là công việc CPU nặng, có thể dùng `thenCombineAsync(right, fn, cpuExecutor)`.

## 14. Ví dụ hoàn chỉnh: executor riêng cho I/O và CPU

Tạo file `ExecutorChoiceDemo.java`. Chương trình dùng virtual threads để giả lập lời gọi blocking, sau đó dùng executor CPU riêng cho một stage tính toán. `join()` chỉ được gọi ở **ranh giới main** sau khi xây graph, không ở giữa supplier/callback đang chiếm worker.

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class ExecutorChoiceDemo {

    static String loadRemote(String id) {
        try {
            Thread.sleep(80); // Giả lập I/O blocking.
            return "product-" + id;
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new CompletionException(exception);
        }
    }

    static long computeScore(String text) {
        long score = 0;
        for (int i = 0; i < text.length(); i++) {
            score += text.charAt(i);
        }
        return score;
    }

    public static void main(String[] args) {
        int cpuThreads = Math.max(
                1,
                Runtime.getRuntime().availableProcessors() - 1
        );

        try (ExecutorService io =
                     Executors.newVirtualThreadPerTaskExecutor();
             ExecutorService cpu =
                     Executors.newFixedThreadPool(cpuThreads)) {

            CompletableFuture<String> a =
                    CompletableFuture.supplyAsync(
                            () -> loadRemote("A"), io
                    );

            CompletableFuture<String> b =
                    CompletableFuture.supplyAsync(
                            () -> loadRemote("B"), io
                    );

            CompletableFuture<Long> score =
                    a.thenCombineAsync(
                            b,
                            (first, second) ->
                                    computeScore(first + second),
                            cpu
                    );

            System.out.println("Score: " + score.join());
        }
    }
}
```

Biên dịch và chạy với JDK có virtual threads chính thức (Java 21 trở lên):

```bash
javac ExecutorChoiceDemo.java
java ExecutorChoiceDemo
```

Kết quả xác định theo nội dung chuỗi:

```text
Score: 1759
```

Giá trị được tính từ tổng mã UTF-16 của các ký tự trong `"product-Aproduct-B"`. Thứ tự thực thi `loadRemote("A")` và `loadRemote("B")` **không được bảo đảm**, nhưng cách ghép `a.thenCombineAsync(b, ...)` giữ đúng vị trí đối số nên kết quả có thể dự đoán.

> **Lưu ý thiết kế:** `computeScore` trong ví dụ rất nhẹ để dễ kiểm tra. Với phép tính nhỏ như vậy, dùng riêng một CPU executor có thể không tối ưu; mục đích là minh họa cách **định tuyến stage**. Trong thực tế chỉ tách sang CPU pool khi xử lý đủ đáng kể hoặc cần cô lập tải.

### 14.1. Vì sao chương trình không làm nghẽn common pool?

- Hai supplier blocking đều chạy trên `io`, không nhờ default common pool.
- Stage kết hợp được đặt tường minh lên `cpu`.
- `main` là nơi gọi `join()` để chờ kết quả cuối.
- Cả hai executor đều có chủ sở hữu và được đóng khi rời `try-with-resources`.

Không nên hiểu điều này thành "mọi lời gọi CompletableFuture trong cùng method đều tự động không dùng common pool". Nếu thêm một `thenApplyAsync(fn)` mà không truyền executor, quy tắc default vẫn áp dụng.

## 15. Ví dụ hoàn chỉnh: virtual threads và giới hạn 3 I/O đồng thời

Tạo file `BoundedIoDemo.java`. Chương trình lập lịch nhiều task qua virtual threads, nhưng dùng semaphore để bảo đảm nhiều nhất ba tác vụ cùng nằm trong vùng giả lập I/O.

```java
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Semaphore;
import java.util.stream.IntStream;

public class BoundedIoDemo {

    static String callService(Semaphore permits, int jobId) {
        boolean acquired = false;

        try {
            permits.acquire();
            acquired = true;

            Thread.sleep(50); // Giả lập tác vụ blocking.
            return "OK-" + jobId;
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new CompletionException(exception);
        } finally {
            if (acquired) {
                permits.release();
            }
        }
    }

    public static void main(String[] args) {
        Semaphore permits = new Semaphore(3);

        try (ExecutorService io =
                     Executors.newVirtualThreadPerTaskExecutor()) {

            List<CompletableFuture<String>> tasks =
                    IntStream.rangeClosed(1, 8)
                            .mapToObj(jobId ->
                                    CompletableFuture.supplyAsync(
                                            () -> callService(permits, jobId),
                                            io
                                    )
                            )
                            .toList();

            CompletableFuture<?>[] all =
                    tasks.toArray(new CompletableFuture<?>[0]);

            // Chờ ở caller thread, không block common pool.
            CompletableFuture.allOf(all).join();

            List<String> results =
                    tasks.stream()
                            .map(CompletableFuture::join)
                            .toList();

            System.out.println(results);
        }
    }
}
```

Chạy:

```bash
javac BoundedIoDemo.java
java BoundedIoDemo
```

Kết quả:

```text
[OK-1, OK-2, OK-3, OK-4, OK-5, OK-6, OK-7, OK-8]
```

Các task có thể hoàn thành **không theo thứ tự gửi**, nhưng việc duyệt `tasks` theo thứ tự ban đầu cho ra danh sách kết quả có thứ tự ổn định. `Semaphore(3)` giới hạn số task đồng thời giữ permit; nó không hạn chế số future đã được tạo.

### 15.1. allOf không tạo thêm thread để chờ từng kết quả

`CompletableFuture.allOf(...)` trả một future hoàn tất khi các future đầu vào hoàn tất. Nó không yêu cầu một worker thực thi `join()` cho mỗi phần tử. Trong ví dụ, `allOf(...).join()` được gọi ở main khi cần kết thúc ứng dụng.

`allOf` không tự xây danh sách kết quả có kiểu; vì vậy sau khi biết toàn bộ task đã hoàn tất bình thường, chương trình đọc kết quả từ danh sách future ban đầu.

Nếu có future kết thúc bất thường, `allOf` cũng kết thúc bất thường theo hợp đồng; code cần xác định chính sách tổng hợp lỗi và xử lý những task đang chạy, thay vì giả định mọi task đã thành công.

## 16. Lỗi starvation và deadlock do task tự chờ cùng executor

Một trường hợp nguy hiểm là **single-thread executor** có task A đang chạy và chờ task B, trong khi task B cũng chỉ được lên lịch trên executor đó.

```java
// KHÔNG CHẠY: ví dụ có thể treo vô hạn.
//
// ExecutorService one = Executors.newSingleThreadExecutor();
//
// CompletableFuture<String> outer = CompletableFuture.supplyAsync(() -> {
//     CompletableFuture<String> inner =
//             CompletableFuture.supplyAsync(() -> "done", one);
//     return inner.join(); // Task A chiếm worker, chờ task B.
// }, one);
//
// outer.join(); // Task B không có worker để bắt đầu.
```

Diễn tiến:

1. Worker duy nhất bắt đầu task A.
2. A gửi task B vào chính executor đó.
3. A gọi `inner.join()` và chờ.
4. B nằm trong queue, không có worker khác để chạy.
5. A không nhường worker đến khi B hoàn tất, B không thể bắt đầu: **thread-starvation deadlock**.

Đây không phải lỗi đặc trưng riêng của common pool. Nó cho thấy mọi executor hữu hạn đều có thể bị phá tiến triển khi task **chờ công việc khác phụ thuộc vào chính tài nguyên đang bị giữ**.

### 16.1. Sửa bằng composition

```java
CompletableFuture<String> result =
        CompletableFuture.supplyAsync(
                () -> "start",
                one
        ).thenCompose(text ->
                CompletableFuture.supplyAsync(
                        () -> text + "-done",
                        one
                )
        );
```

Ở ví dụ sửa, stage đầu không block worker để chờ stage thứ hai; nó chỉ tạo và nối future. `one` là executor đã được tạo ở ngữ cảnh caller phù hợp; chờ `result.join()` ở caller bên ngoài executor đó, không bên trong worker của chính `one`.

**Nếu có vòng phụ thuộc logic giữa future**, chỉ thay `join` bằng `thenCompose` chưa chắc giải quyết được; vẫn phải phân tích và xóa dependency cycle.

## 17. Bounded ThreadPoolExecutor và backpressure

Khi dùng platform threads cho I/O hoặc muốn giới hạn rõ số worker và queue, có thể cấu hình `ThreadPoolExecutor`:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

try (ExecutorService limited = new ThreadPoolExecutor(
        4,
        4,
        0L,
        TimeUnit.MILLISECONDS,
        new ArrayBlockingQueue<>(100),
        new ThreadPoolExecutor.CallerRunsPolicy()
)) {
    // Submit công việc từ phía caller ở đây.
}
```

Cấu hình minh họa:

- 4 worker platform threads.
- Queue chứa tối đa 100 task chờ.
- Khi queue đầy và worker đã đạt giới hạn, `CallerRunsPolicy` có thể **chạy task trên thread submit** để làm chậm producer.

### 17.1. CallerRunsPolicy là một lựa chọn có đánh đổi

Ưu điểm: khi quá tải, caller có thể phải tự thực hiện tác vụ, khiến tốc độ gửi chậm lại.

Rủi ro:

- Nếu caller là event-loop hoặc request thread nhạy latency, việc bắt nó chạy task blocking có thể làm nghẽn chính caller.
- Khi executor đã shutdown, chính sách này có hành vi khác; không dựa vào nó để đảm bảo mọi task được chạy trong mọi trạng thái.
- Nó không tự cung cấp deadline, retry, isolation hay bảo vệ dịch vụ ngoài.

Tùy hợp đồng có thể dùng `AbortPolicy` để từ chối bằng `RejectedExecutionException`, rồi trả tín hiệu quá tải cho tầng nhận request.

### 17.2. Giới hạn queue và giới hạn I/O là hai việc khác nhau

Một thread pool có thể giới hạn **số worker** nhưng task của nó lại mở nhiều connection phụ nếu mỗi task tạo thêm fan-out. Ngược lại, semaphore có thể giới hạn connection nhưng vẫn có quá nhiều task chờ permit. Hệ thống lớn có thể cần cả hai hoặc một cơ chế admission control rõ ràng.

## 18. CompletableFuture: xử lý exception ở đúng tầng

Tác vụ async có thể thất bại vì timeout, HTTP error, database error, parse lỗi hoặc lỗi logic.

Các phương thức phổ biến:

| Method | Khi nào chạy | Kết quả |
|---|---|---|
| `exceptionally(fn)` | Khi stage trước hoàn tất bất thường | Có thể trả giá trị fallback |
| `handle((value, error) -> ...)` | Khi stage trước hoàn tất (thành công hoặc lỗi) | Có thể biến đổi kết quả hoặc phục hồi lỗi |
| `whenComplete((value, error) -> ...)` | Khi stage trước hoàn tất | Dùng cho quan sát/side effect, thường giữ outcome gốc nếu callback thành công |
| `thenApply(fn)` | Khi stage trước hoàn tất bình thường | Biến đổi giá trị |
| `thenCompose(fn)` | Khi stage trước hoàn tất bình thường | Nối một stage khác |

Ví dụ fallback:

```java
CompletableFuture<String> result =
        CompletableFuture.supplyAsync(
                () -> simulatedRemoteCall("A"),
                ioExecutor
        ).exceptionally(error -> "fallback");
```

`exceptionally` không được gọi nếu tác vụ thành công. Việc trả `"fallback"` là quyết định nghiệp vụ, **không nên che mọi lỗi bằng một giá trị giả** nếu caller cần biết kết quả không đáng tin cậy.

### 18.1. join và get báo lỗi khác nhau

- `CompletableFuture.join()` chờ và có thể ném `CompletionException` không checked.
- `CompletableFuture.get()` chờ, có thể ném `InterruptedException` và `ExecutionException`; cũng có overload với timeout.

**Cả hai đều có thể block caller.** Việc `join` không yêu cầu khai báo checked exception không làm nó non-blocking.

Một số code nên đặt `join` ở ranh giới đã quyết định chờ (như main hoặc integration boundary), thay vì trong callback đang chiếm worker trên executor hữu hạn.

### 18.2. whenComplete không phải cơ chế retry

`whenComplete` là stage quan sát kết quả và có thể thực hiện log/metrics; nó không tự thử lại tác vụ đã lỗi. Nếu cần retry, phải thiết kế chính sách số lần, delay, idempotency và phân loại lỗi.

## 19. Timeout future không đảm bảo dừng tác vụ gốc

`CompletableFuture` có:

- `orTimeout(timeout, unit)`: hoàn tất future bất thường với `TimeoutException` nếu chưa xong đúng hạn.
- `completeOnTimeout(value, timeout, unit)`: hoàn tất future bằng giá trị dự phòng nếu chưa xong đúng hạn.

Ví dụ:

```java
CompletableFuture<String> future =
        CompletableFuture.supplyAsync(
                () -> simulatedRemoteCall("slow"),
                ioExecutor
        ).orTimeout(200, java.util.concurrent.TimeUnit.MILLISECONDS);
```

**Điểm đặc biệt quan trọng:** timeout của `CompletableFuture` có thể làm future hoàn tất sớm, nhưng **không tự bảo đảm chặn hoặc hủy tác vụ underlying**. Nếu tác vụ gốc đang chờ network, nó có thể tiếp tục thực hiện và thậm chí gây side effect sau khi caller nhận timeout.

### 19.1. Cancellation của CompletableFuture

`CompletableFuture.cancel(true)` không giống lệnh chắc chắn ngắt thread đang chạy supplier. Theo contract của `CompletableFuture`, đối số `mayInterruptIfRunning` **không có hiệu lực điều khiển việc interrupt** như một số implementation của `FutureTask`. Cancel là một dạng hoàn tất bất thường với `CancellationException`.

Khi cần hủy hoạt động thật:

- Dùng timeout của HTTP/database/client nếu có.
- Dùng cơ chế cancellation mà thư viện thật hỗ trợ.
- Xây task hợp tác với `interrupt` hoặc token dừng nếu model phù hợp.
- Theo dõi lifecycle resource để đóng connection hoặc release permit đúng cách.
- Đảm bảo kết quả đến muộn không được commit khi request đã hết hạn nếu hợp đồng yêu cầu.

### 19.2. Timeout ở nhiều tầng

Có thể cần phân biệt:

1. **Connection timeout**: mất bao lâu để thiết lập kết nối.
2. **Read/request timeout**: thời gian cho hoạt động I/O.
3. **Workflow deadline**: toàn bộ chuỗi nhiều bước phải xong trước khi hết hạn.
4. **Queue timeout**: task chờ executor quá lâu trước khi bắt đầu.

Chỉ đặt timeout ở future tổng không thay thế những giới hạn này.

## 20. Vòng đời executor và đóng tài nguyên

### 20.1. Ai tạo executor thì thường sở hữu lifecycle

Một service được tiêm `Executor` từ ứng dụng không nên shutdown nó tùy tiện khi service hoàn tất một request. Một executor có thể dùng chung nhiều service.

Ví dụ ứng dụng tự tạo:

```java
try (var executor =
        java.util.concurrent.Executors.newVirtualThreadPerTaskExecutor()) {

    // Tạo các task và chờ kết quả theo contract.
}
```

Khi rời `try`, `ExecutorService.close()` thực hiện cơ chế đóng và chờ các task theo contract. Nếu task bị treo vô hạn vì I/O không timeout, **việc đóng cũng có thể kéo dài**. Do đó cần giới hạn thời gian và kế hoạch shutdown.

### 20.2. shutdown vs shutdownNow

`shutdown()` không nhận thêm task mới, cho phép các task đã gửi hoàn tất.

`shutdownNow()` cố gắng dừng task đang chạy (thường thông qua interruption) và thu hồi những task chưa bắt đầu, nhưng không đảm bảo task đang chạy sẽ dừng nếu chúng không hợp tác.

### 20.3. awaitTermination

`awaitTermination(duration, unit)` chờ tối đa khoảng thời gian được cung cấp để xác nhận pool đã kết thúc; nó không tự kích hoạt shutdown. Khi có nhu cầu shutdown có hạn, thường phải gọi `shutdown` trước rồi chờ, đánh giá tình trạng và xử lý tiếp theo theo hợp đồng.

Không bỏ qua `InterruptedException`: nếu không thể ném ra tiếp, khôi phục interrupt flag bằng `Thread.currentThread().interrupt()` và bảo đảm cleanup thích hợp.

## 21. Bài toán quan sát và vận hành

Khi có nhiều executor, cần biết chúng đang hoạt động như thế nào.

### 21.1. Chỉ số hữu ích

| Chỉ số | Ý nghĩa |
|---|---|
| Số task đang chạy | Mức sử dụng worker/permit |
| Số task chờ trong queue | Dấu hiệu producer nhanh hơn consumer |
| Queue wait time | Độ trễ từ submit đến lúc bắt đầu |
| Execution time | Thời gian thực thi task |
| Completion/error/timeout rate | Độ tin cậy của pipeline |
| Rejection count | Executor từ chối do quá tải hoặc shutdown |
| In-flight I/O requests | Áp lực lên dependency bên ngoài |
| CPU utilization | Phù hợp hay không với mức worker CPU |
| Tail latency (p95/p99) | Ảnh hưởng xấu tới request chậm nhất |

### 21.2. Không chỉ quan sát tên thread

Một log ghi `ForkJoinPool.commonPool-worker-*` gợi ý công việc đang chạy trên common pool, nhưng tên thread có thể bị tùy chỉnh. Hãy tin **cấu hình executor và ngữ nghĩa API** hơn là đoán từ tên thread.

### 21.3. Tracing qua callback

Một pipeline có thể chuyển qua nhiều executor, nên context logging/tracing đặt trong `ThreadLocal` không tự được truyền qua mọi thread. Virtual thread cũng có mô hình ThreadLocal riêng; không được mặc định lấy ThreadLocal từ caller sẽ xuất hiện ở mọi task async.

Khi framework có hỗ trợ context propagation, hãy dùng cơ chế chuẩn của framework hoặc truyền context tường minh, bảo đảm không rò dữ liệu giữa request.

## 22. Parallel stream và tránh I/O blocking

`parallelStream()` rất tiện cho phép biến đổi phần tử độc lập:

```java
int total = java.util.stream.IntStream.range(0, 1_000)
        .parallel()
        .map(n -> n * n)
        .sum();
```

Mẫu phù hợp hơn với tính toán có thể song song hóa, không có side effect dùng chung và đủ công việc để bù overhead.

Mẫu đáng cân nhắc lại:

```java
// KHÔNG nên dùng tự động cho I/O blocking nhiều:
// List<Result> results = urls.parallelStream()
//         .map(url -> blockingHttpCall(url))
//         .toList();
```

Trong ngữ cảnh gọi phổ biến, parallel streams sử dụng common pool; nếu từng phần tử chờ network lâu, pool có thể bị nghẽn và tác động tới các phép tính song song khác.

Nếu nguồn dữ liệu là các request network độc lập, hãy cân nhắc:

- API HTTP async thực sự.
- Virtual threads với giới hạn concurrent requests.
- Executor riêng có giới hạn task và chính sách quá tải.

### 22.1. Parallel không tự tăng tốc

Nếu thao tác mỗi phần tử quá nhỏ, overhead phân chia và hợp nhất có thể lớn hơn lợi ích. Với pipeline có thứ tự, side effects hoặc cập nhật dữ liệu chia sẻ, parallel hóa có thể làm code vừa khó đúng vừa chậm hơn.

## 23. Hạn chế callback quá nặng trên thread hoàn tất I/O

Với `thenApply` không-async, function có thể chạy trên thread hoàn tất stage trước. Nếu stage trước là một tác vụ I/O, function đó có thể giữ thread hoàn tất để thực thi công việc CPU lâu:

```java
CompletableFuture<Report> report = fetchAsync()
        .thenApply(data -> expensiveCpuTransform(data));
```

Đây là **mã ý tưởng**, trong đó `fetchAsync` và `expensiveCpuTransform` là method do ứng dụng định nghĩa.

Khi cần cô lập bước CPU:

```java
CompletableFuture<Report> report = fetchAsync()
        .thenApplyAsync(
                data -> expensiveCpuTransform(data),
                cpuExecutor
        );
```

Điều này giúp cấu trúc rõ ý nghĩa: nguồn dữ liệu hoàn tất khi có thể, còn xử lý CPU được đặt lên tài nguyên dành riêng. Tuy nhiên, nếu phép biến đổi rẻ, overhead chuyển pool có thể không đáng. Quyết định nên dựa trên workload và mục tiêu cô lập.

## 24. Checklist khi review code bất đồng bộ

### 24.1. Về lựa chọn executor

- Tác vụ chủ yếu tính CPU hay chờ I/O?
- Có dùng `CompletableFuture.supplyAsync` mà không truyền executor cho công việc blocking không?
- Có `thenApplyAsync`, `thenComposeAsync` hay `whenCompleteAsync` không truyền executor ở stage quan trọng không?
- Mọi executor riêng có chủ sở hữu và lifecycle rõ chưa?
- Pool có giới hạn số worker, queue, in-flight connection phù hợp chưa?
- Có tránh shutdown common pool và tránh tạo nhiều pool ngắn hạn không cần thiết không?

### 24.2. Về tiến triển

- Có `join()`/`get()` trong callback hoặc task của executor hữu hạn không?
- Task A có chờ task B được submit vào cùng pool, trong khi A giữ worker duy nhất hoặc tất cả worker đang bận chờ không?
- Có dependency cycle hoặc chờ lẫn nhau giữa các future không?
- Có timeout ở đúng tầng I/O và workflow không?
- Có đường xử lý interruption/cancellation thật sự không?

### 24.3. Về dữ liệu và vận hành

- Lambda có cập nhật mutable state không thread-safe không?
- Side effect có thể bị thực hiện sau timeout hoặc cancellation không?
- Có giới hạn resource tại dependency ngoài bằng semaphore/connection pool không?
- Nếu task bị từ chối, tầng gọi có phản hồi quá tải rõ ràng không?
- Có metrics cho queue wait, task duration, saturation, timeouts và errors không?
- Chương trình có đóng executor do mình sở hữu khi dừng không?

## 25. Những lỗi phổ biến

| Hiểu lầm | Rủi ro | Cách sửa |
|---|---|---|
| Mọi `supplyAsync` đều không block | Lambda có thể chờ I/O và chiếm worker | Truyền executor phù hợp hoặc dùng async I/O thật |
| Common pool là pool riêng của ứng dụng | Cạnh tranh với thư viện và tác vụ khác | Cô lập workload quan trọng |
| `thenApplyAsync` tự dùng executor của stage đầu | Có thể quay về default async facility | Truyền executor ở stage cần kiểm soát |
| `thenApply` luôn chạy trên thread gọi method | Có thể chạy trên thread hoàn tất stage | Không dựa vào thread identity |
| Có `get()` trong async callback là bình thường | Có thể starve pool và tạo deadlock | Dùng `thenCompose`/`thenCombine` |
| Tạo fixed pool là đã giới hạn queue | Factory fixed pool có queue không giới hạn hữu hạn | Bounded queue/backpressure |
| Virtual thread tăng năng lực CPU | CPU vẫn bị giới hạn số core | Dùng cho blocking I/O, giới hạn tài nguyên |
| Có semaphore thì không còn quá tải | Task chờ permit vẫn có thể tích tụ | Admission control và queue limit |
| `CompletableFuture.cancel(true)` chắc chắn interrupt supplier | Đối số không điều khiển interrupt trong CF | Cancellation hợp tác/timeout API thực |
| `orTimeout` dừng HTTP/database request | Chỉ hoàn tất future theo deadline | Timeout/cancel ở client và nguồn |
| `allOf` tự trả `List<T>` | Nó trả `CompletableFuture<Void>` | Tập hợp kết quả từ futures ban đầu |
| `CallerRunsPolicy` không có tác dụng phụ | Caller có thể bị chặn bởi task | Chọn chính sách quá tải theo latency |
| `ForkJoinPool.ManagedBlocker` giải quyết mọi blocking | Chỉ hỗ trợ một số cơ chế quản lý blocking | Executor phù hợp, giới hạn I/O |
| Có virtual threads thì không cần timeout | Task blocking vẫn có thể treo | Timeout và resource budget |
| `shutdownNow()` chắc chắn dừng mọi task | Dừng thường dựa trên interruption hợp tác | Đóng tài nguyên và kiểm soát tiến trình |
| Parallel stream luôn tốt hơn sequential | Overhead, ordering, shared state và common pool | Benchmark, chọn workload phù hợp |

## 26. Bài tập thực hành

### Bài 1. Phân loại workload

Cho các tác vụ: tính hash trên 100.000 chuỗi, gọi HTTP tới 500 endpoint, tính trung bình 10 triệu số, chờ kết quả database, ghi log nhẹ, parse JSON lớn. Hãy phân loại CPU-bound, blocking I/O-bound hoặc hỗn hợp và đề xuất executor cho từng trường hợp.

### Bài 2. Phát hiện common pool ngầm

Viết `CompletableFuture.supplyAsync(() -> "A")`, sau đó `thenApplyAsync` và `thenApply`. Dự đoán stage nào có thể dùng common pool và stage nào có thể chạy trên thread hoàn tất trước. Sửa toàn bộ các bước quan trọng để executor được chọn rõ ràng.

### Bài 3. Sửa pipeline chặn future

Cho hai tác vụ async độc lập tạo chuỗi. Viết lại một callback đang `join()` trên future thứ hai thành `thenCombine`. Giải thích vì sao cách này không cần block worker chỉ để chờ dữ liệu đã có trong future.

### Bài 4. Deadlock trong single-thread pool

Phân tích task A gửi task B vào cùng `newSingleThreadExecutor` rồi A gọi `B.join()`. Vẽ sơ đồ dependency, mô tả tại sao hệ thống có thể treo và viết lại bằng `thenCompose`.

### Bài 5. Dùng virtual thread cho blocking I/O

Viết ví dụ submit 20 tác vụ giả lập I/O lên `newVirtualThreadPerTaskExecutor`. Dùng `Semaphore(4)` giới hạn số tác vụ cùng thực hiện I/O. Xác nhận rằng số kết quả trả về là 20 và không có permit bị rò khi ném exception.

### Bài 6. ThreadPoolExecutor có backpressure

Tạo một `ThreadPoolExecutor` gồm 3 worker và queue 10 task. Thử `AbortPolicy` hoặc `CallerRunsPolicy` khi submit nhiều hơn khả năng xử lý. Mô tả điều gì xảy ra với thread gọi và cách trả lỗi quá tải cho request.

### Bài 7. Timeout và cancel

Tạo một supplier giả lập blocking 2 giây và `orTimeout(100, MILLISECONDS)`. Quan sát future kết thúc ra sao. Giải thích vì sao không nên kết luận supplier đã bị dừng, và đề xuất cách kiểm soát timeout ngay bên trong I/O.

### Bài 8. Quản lý vòng đời

Tạo executor trong một method, submit vài task và đóng bằng try-with-resources. So sánh với một service nhận `Executor` từ ngoài. Ai có quyền `shutdown` trong mỗi trường hợp?

### Bài 9. CPU stage sau I/O

Tạo pipeline đọc dữ liệu bằng executor I/O, xử lý tính toán nặng bằng executor CPU và trả kết quả cuối qua future. So sánh `thenApply` với `thenApplyAsync(fn, cpuExecutor)`, kiểm tra kết quả mà không chặn giữa các stage.

### Bài 10. Thiết kế hệ thống thực tế

Một API gateway nhận 1.000 request/giây; mỗi request có thể gọi hai dịch vụ ngoài và tính toán một kết quả CPU. Hãy phác họa kiến trúc gồm executor, giới hạn in-flight request, deadline, lỗi fallback, cơ chế quá tải và metrics. Giải thích vì sao không gửi mọi thứ vào common pool và không tạo vô hạn virtual threads mà không kiểm soát tài nguyên.

## 27. Tóm tắt

**Chọn executor theo đặc tính công việc** là bước quan trọng để pipeline bất đồng bộ ổn định:

- **CPU-bound:** cân nhắc số worker hữu hạn theo ngân sách CPU; dùng fixed pool hoặc fork/join thích hợp, đồng thời kiểm soát queue.
- **Blocking I/O-bound:** dùng executor riêng; trong Java hiện hành, virtual-thread-per-task là lựa chọn hữu ích cho rất nhiều tác vụ blocking phù hợp, nhưng vẫn cần timeout và giới hạn tài nguyên bên ngoài.
- **I/O thực sự async:** ưu tiên API async và kết hợp future bằng `thenCompose`/`thenCombine`, không tạo thread chỉ để chờ kết quả không cần thiết.

**`ForkJoinPool.commonPool()` là tài nguyên chia sẻ**. Những lời gọi `supplyAsync` hay `thenApplyAsync` không truyền executor có thể sử dụng nó. Đặt nhiều công việc chặn lâu vào common pool gây cạnh tranh worker và tăng nguy cơ starvation. **Đừng nhầm bất đồng bộ với non-blocking**, đừng mặc định mọi stage kế thừa executor của stage đầu, và đừng gọi `join()`/`get()` trong callback trên một pool hữu hạn khi có thể dùng composition.

Cuối cùng, **timeout hoặc cancellation của CompletableFuture không tự bảo đảm dừng thao tác underlying**. Hệ thống vận hành tốt phải có owner của executor, giới hạn queue và in-flight resources, đường cleanup khi lỗi, quan sát contention/tail latency và chính sách shutdown hợp tác. Mục tiêu không phải "tránh mọi blocking" mà là **đặt công việc lên đúng tài nguyên và tránh chặn nơi có thể phá tiến triển của hệ thống**.

## Tài liệu tham khảo

- [Java SE 27 API — java.util.concurrent.Executor](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/Executor.html)
- [Java SE 27 API — java.util.concurrent.ExecutorService](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/ExecutorService.html)
- [Java SE 27 API — java.util.concurrent.Executors](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/Executors.html)
- [Java SE 27 API — ForkJoinPool](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/ForkJoinPool.html)
- [Java SE 27 API — CompletableFuture](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [Java SE 27 API — ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)
- [Java SE 27 API — Semaphore](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/Semaphore.html)
- [Java SE 27 API — Future](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/Future.html)
- [Java SE 27 API — Thread](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Thread.html)
- [JEP 444 — Virtual Threads (finalized in Java 21)](https://openjdk.org/jeps/444)
