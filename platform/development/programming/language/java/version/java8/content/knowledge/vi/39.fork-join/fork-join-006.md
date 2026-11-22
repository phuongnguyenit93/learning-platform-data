# Giới hạn khi công việc Fork/Join chặn hoặc thực hiện I/O (Java 8+)

> **Chủ đề cha:** Fork/Join. `ForkJoinPool` hỗ trợ xử lý song song theo cơ chế *work-stealing*, rất phù hợp khi công việc chủ yếu **CPU-bound**, có thể chia thành các tác vụ tính toán nhỏ rồi gộp kết quả. Nếu tác vụ phải đợi **network, JDBC, file I/O, lock, latch, queue hoặc Future**, worker có thể bị chiếm mà không tính toán hữu ích. Bài này giải thích giới hạn đó, cách dùng `ForkJoinPool.ManagedBlocker`, cách tách CPU và I/O, cùng lựa chọn API hiện đại còn phù hợp trên JDK mới.

## 1. Mục tiêu học tập

Học xong, bạn có thể:

1. Giải thích vì sao work-stealing hoạt động tốt với CPU-bound divide-and-conquer.
2. Phân biệt `ForkJoinTask.join()` với chờ I/O/blocking tùy ý bên trong pool.
3. Nhận biết *thread starvation*, phụ thuộc chéo trong cùng pool và ảnh hưởng tới common pool.
4. Đánh giá `parallelStream` / `CompletableFuture.supplyAsync` có thể chiếm worker thế nào nếu callback blocking.
5. Viết `ForkJoinPool.ManagedBlocker` đúng hợp đồng `isReleasable()` và `block()`.
6. Tách blocking I/O sang executor riêng, quản lý giới hạn số tác vụ, timeout, backpressure, shutdown.
7. Biết khi nào dùng API I/O bất đồng bộ hoặc virtual threads từ **Java 21+** mà không nhầm với API Java 8.
8. Chạy chương trình Java 8 hoàn chỉnh minh họa phép chia để trị, I/O chặn trên executor riêng và managed blocking.

## 2. Vì sao Fork/Join đặc biệt hợp với tác vụ CPU-bound?

Một `RecursiveTask<V>` có thể chia vấn đề lớn thành các phần nhỏ; một worker tạo task con bằng `fork()`, tự tính một phần bằng `compute()`, rồi gộp kết quả với `join()`. Worker khác có thể *steal* subtasks và sử dụng lõi CPU đang rảnh.

```java
class SumTask extends RecursiveTask<Long> {
    // compute() chia vấn đề, fork một nửa,
    // tính trực tiếp nửa kia và join để gộp kết quả.
}
```

Đây là **sơ đồ class**, không phải file biên dịch độc lập. Chương trình ở phần 9 có `RangeSum` đầy đủ.

### 2.1. Work-stealing không có nghĩa mọi lần chờ đều vô hại

`ForkJoinTask.join()` có cơ chế phối hợp với ForkJoinPool; khi một worker đợi task con, pool có thể sử dụng các chiến lược trợ giúp thực hiện subtasks. Nhưng **`Thread.sleep`, `CountDownLatch.await`, `BlockingQueue.take`, socket read, JDBC query hoặc một blocking API bên ngoài** không nhất thiết được runtime nhận diện như một điểm chờ có thể bù worker.

Nếu worker giữ một task đang chờ I/O, worker ấy không thể đồng thời steal và thực thi những tác vụ CPU đã sẵn sàng. Khi nhiều worker cùng chặn, throughput giảm dù CPU của máy có thể vẫn rảnh.

### 2.2. Parallelism là mục tiêu, không phải giới hạn thread tuyệt đối

```java
ForkJoinPool cpuPool = new ForkJoinPool(2);
```

`2` là **target parallelism**, không nhất thiết là số thread tối đa tuyệt đối trong mọi tình huống. Với một số điểm chặn được quản lý, pool có thể bố trí worker bổ sung; việc đó có giới hạn, tốn tài nguyên và **không phải bảo đảm tạo vô hạn thread**. Không chọn `ForkJoinPool(1000)` như cách giải quyết 1000 kết nối mạng đang chờ.

## 3. Các kiểu chặn và rủi ro

| Công việc | Đặc điểm | Trong ForkJoinPool |
| --- | --- | --- |
| CPU compute, chia để trị | Tính toán hữu ích, có subtasks | Phù hợp nếu kích thước task hợp lý |
| `ForkJoinTask.join()` | Chờ task con theo giao thức Fork/Join | Pool có cơ chế trợ giúp task |
| `CountDownLatch.await()` | Đợi tín hiệu ngoài | Worker có thể bị giữ, làm đói task phát tín hiệu |
| `BlockingQueue.take()` | Đợi producer tạo dữ liệu | Có thể gây starvation nếu producer nằm cùng pool |
| `Thread.sleep(...)` | Ngừng thực thi nhưng giữ worker | Giảm parallelism hữu ích |
| `Future.get()` / `CompletableFuture.join()` | Đợi kết quả một task khác | Cần kiểm tra dependency, executor và tính blocking |
| Socket, HTTP/JDBC sync, file I/O | Đợi tài nguyên ngoài | Work-stealing không tự biến I/O thành nonblocking |

Không nói mọi `Future.get` đều có cùng cài đặt: JDK có các cơ chế phối hợp nội bộ riêng trong một số loại task/future. **Quy tắc thiết kế vẫn là không dựa vào việc bù worker tự động cho blocking I/O tùy ý**.

### 3.1. Cạm bẫy phụ thuộc chéo

```text
ForkJoinPool(parallelism = 1)

Task A đang chiếm worker duy nhất
    -> latch.await() chờ Task B

Task B được submit vào chính pool đó
    -> đợi worker rảnh để gọi latch.countDown()

Nếu A chặn không được quản lý và không có ai bên ngoài mở latch,
cả hai có thể không tiến được: starvation hoặc deadlock.
```

Đây chỉ là **sơ đồ nguy cơ**, không phải code khuyến nghị chạy: một demo có thể treo vô hạn không phù hợp cho bài thực hành.

### 3.2. Triệu chứng khi pool bị nghẽn

Có thể thấy CPU chưa dùng hết, hàng đợi tác vụ tăng, độ trễ p95/p99 tăng, nhiều worker đứng ở `await`/`read`/`get` trong thread dump, cùng các phép tính CPU không liên quan cũng chậm. Hãy kiểm tra đồng thời thread dump, độ trễ I/O, connection-pool saturation, queue depth, số worker hoạt động và tải `ForkJoinPool.commonPool()`. Chỉ nhìn CPU thấp chưa đủ kết luận.

## 4. Common pool và các tác vụ “async” dễ gây hiểu lầm

```java
ForkJoinPool shared = ForkJoinPool.commonPool();
```

Common pool là tài nguyên dùng chung trong JVM. Các thao tác `CompletableFuture.supplyAsync` không chỉ định executor và nhiều parallel stream có thể sử dụng common pool, tùy ngữ cảnh/runtime.

```java
CompletableFuture<String> f =
        CompletableFuture.supplyAsync(() -> {
            // Nếu thay bằng client.send(...) hay JDBC blocking:
            // thread thực thi supplier vẫn phải đợi I/O.
            return "sample";
        });
```

**`supplyAsync` không biến blocking I/O thành nonblocking I/O**: nó chỉ lập lịch supplier chạy trên executor. Nếu supplier chặn, thread của executor vẫn bị chiếm. Đổi tên method sang `thenApplyAsync`/`runAsync` không tự giải quyết giới hạn I/O.

### 4.1. Parallel stream cũng không phải công cụ mặc định cho mạng/DB

```java
List<Integer> nums = Arrays.asList(1, 2, 3, 4);
int sum = nums.parallelStream()
        .mapToInt(Integer::intValue)
        .sum();
```

Đoạn này chỉ tính CPU, thực tế dữ liệu rất nhỏ nên parallel có thể chậm hơn sequential do overhead. Nếu biến `map` trong stream thành RPC/JDBC đồng bộ cho hàng nghìn phần tử, các worker có thể đợi I/O, ảnh hưởng cả tác vụ khác dùng chung pool. Ngoài ra giới hạn kết nối phía downstream không tự tăng theo số worker.

## 5. Lựa chọn 1: tách CPU-bound và blocking I/O

Một thiết kế rõ ràng:

```text
Tác vụ tính CPU ──> ForkJoinPool / CPU executor ──> kết quả tính
Tác vụ chờ I/O ───> ExecutorService dành cho I/O ──> dữ liệu đọc
```

```java
ForkJoinPool cpuPool = new ForkJoinPool(2);
ExecutorService ioPool = Executors.newFixedThreadPool(2);
try {
    Future<String> response = ioPool.submit(() -> {
        // Trong ứng dụng thật, thay bằng I/O có timeout.
        return "ready";
    });
    // Gửi tính toán CPU độc lập vào cpuPool.
    String content = response.get();
} finally {
    ioPool.shutdownNow();
    cpuPool.shutdownNow();
}
```

Đây là **snippet phân tách executor**, không phải chương trình runnable độc lập. Trong ví dụ đầy đủ dưới đây, một task I/O giả lập thật sự chờ latch, trong lúc CPU pool vẫn tính xong tổng.

### 5.1. Fixed thread pool có thể có hàng đợi không giới hạn

`Executors.newFixedThreadPool(n)` giữ số worker cố định nhưng **không tự đặt dung lượng queue hữu hạn**. Với production, nếu request I/O đến nhanh hơn khả năng phục vụ, hàng đợi có thể tăng gây memory pressure và latency. Cần thiết kế:

- Giới hạn concurrency theo connection pool/downstream quota;
- Hàng đợi có capacity hoặc `ThreadPoolExecutor` cấu hình queue hữu hạn và rejection/backpressure rõ;
- Connect/read/request timeout, rate limit, retry có giới hạn và circuit breaker nếu phù hợp;
- Lifecycle của executor theo ứng dụng (không tạo pool mới mỗi request).

Không “chữa” nghẽn mạng bằng executor vô hạn thread. Nó thường chỉ chuyển nghẽn thành cạn bộ nhớ, quá tải DB hoặc vượt quota của dịch vụ đích.

### 5.2. Compose kết quả thay vì chặn giữa pipeline

```java
CompletableFuture<String> data =
        CompletableFuture.supplyAsync(() -> "abc", ioPool);

CompletableFuture<Integer> result =
        data.thenApply(String::length);
```

Khi logic CPU nặng, có thể dùng `thenApplyAsync(fn, cpuExecutor)`. Nên **truyền tiếp stage** thay vì `join()` trong worker để đợi tác vụ khác đang nằm ở cùng một executor có ít thread. Đây là ví dụ cơ chế; supplier thực tế có blocking I/O vẫn cần được cấp resource/timeout phù hợp.

## 6. Lựa chọn 2: `ForkJoinPool.managedBlock` cho điểm chặn có kiểm soát

`ForkJoinPool.managedBlock(ForkJoinPool.ManagedBlocker)` cho pool biết một task **có khả năng phải chặn**. Nếu đang thực thi trong ForkJoinPool, runtime **có thể** kích hoạt hoặc bố trí thêm worker nhằm duy trì mức song song khi cần. Nó **không bảo đảm** mở worker vô hạn hay bù được mọi tình huống.

Interface `ForkJoinPool.ManagedBlocker` có hai phương thức:

```java
boolean isReleasable();                      // Có thể tiếp tục ngay?
boolean block() throws InterruptedException; // Chờ nếu cần.
```

- `isReleasable()` được phép gọi **nhiều lần**; cần nhẹ, thread-safe, tránh side effect và thường không nên chặn.
- `block()` chặn nếu cần và trả `true` khi không cần chặn thêm; có thể ném `InterruptedException`.
- `managedBlock` kiểm tra và gọi hai method theo hợp đồng cho tới khi đã releasable. Khi gọi **ngoài một ForkJoinPool**, nó vẫn thực hiện giao thức chờ nhưng **không kích hoạt cơ chế bù worker của pool**.

### 6.1. ManagedBlocker cho CountDownLatch

```java
static final class LatchBlocker implements ForkJoinPool.ManagedBlocker {
    private final CountDownLatch gate;

    LatchBlocker(CountDownLatch gate) {
        this.gate = gate;
    }

    @Override
    public boolean isReleasable() {
        return gate.getCount() == 0L;
    }

    @Override
    public boolean block() throws InterruptedException {
        gate.await();
        return true;
    }
}
```

Đây là **inner class** cần import hai loại tương ứng, đã có đầy đủ trong chương trình sau. `gate.await` vẫn chặn worker; `managedBlock` chỉ giúp pool có cơ hội bù worker. Không coi đây là API I/O bất đồng bộ.

### 6.2. Khi nào managedBlock hợp lý?

- Bạn buộc phải chờ một điều kiện **trong chính ForkJoinTask** và kiểm soát rõ điểm chặn;
- Có thể định nghĩa `isReleasable` bằng một kiểm tra nhanh (ví dụ queue poll/latch) và `block` có thể chờ đúng cách;
- Đã đánh giá chi phí thêm worker, giới hạn tài nguyên, cách interrupt/cancel và tình huống fail.

Đừng mặc định mọi lời gọi `InputStream.read`/JDBC/HTTP được wrapped thành managed blocking. Việc bọc một thao tác I/O dài chỉ **thông báo điểm chặn**, không làm DB truy vấn nhanh hơn, không tăng giới hạn kết nối và không thay thế timeout. Nếu workload chủ yếu là network I/O sync, một executor I/O hoặc virtual threads thường đơn giản hơn một ForkJoinPool phải bù worker liên tục.

## 7. Lựa chọn 3: I/O bất đồng bộ thật sự và virtual threads

**API I/O async thực sự:** Chẳng hạn `HttpClient.sendAsync` từ Java 11 trả `CompletableFuture` để quản lý tác vụ I/O bất đồng bộ, khác với chạy `HttpClient.send` đồng bộ bên trong `supplyAsync`. Vẫn phải quản lý timeout, retry, resource limits và error handling.

**Virtual threads trên Java 21+:** `Executors.newVirtualThreadPerTaskExecutor()` phù hợp với rất nhiều blocking I/O tasks viết theo cách đồng bộ, giúp tránh giữ một platform thread riêng cho mỗi task trong nhiều trường hợp. Ví dụ **chỉ dùng trên Java 21+**, không nằm trong chương trình Java 8:

```java
try (ExecutorService io =
        Executors.newVirtualThreadPerTaskExecutor()) {
    Future<String> result = io.submit(() -> {
        // Thay bằng I/O blocking của ứng dụng thật.
        return "ok";
    });
    System.out.println(result.get());
}
```

Virtual threads **không làm phép tính CPU nhanh hơn**, không tạo vô hạn kết nối DB, không tự thiết lập backpressure và không loại bỏ nhu cầu giới hạn request. Dự án Java 8 vẫn có thể áp dụng executor cho I/O, `ManagedBlocker`, hoặc thư viện async phù hợp phiên bản; không bê nguyên `newVirtualThreadPerTaskExecutor` vào dự án Java 8.

## 8. Chọn phương án theo yêu cầu

| Tình huống | Hướng xử lý |
| --- | --- |
| Tính toán chia để trị, CPU-bound, ít blocking | `RecursiveTask`/`RecursiveAction` trong ForkJoinPool |
| Blocking I/O là phần lớn workload trên Java 8 | ExecutorService I/O riêng, giới hạn tài nguyên |
| Bắt buộc đợi ngắn/đợi queue trong ForkJoinTask, kiểm soát blocker | `ForkJoinPool.managedBlock` |
| Thư viện hỗ trợ I/O async thật sự | Dùng async API, compose kết quả |
| Nhiều blocking I/O trên Java 21+ | Virtual threads với giới hạn downstream |
| Tác vụ cần CPU sau khi I/O trả kết quả | Chuyển callback CPU sang executor tính toán phù hợp |
| Cần độ trễ ổn định, tránh một nhóm I/O ảnh hưởng nhóm khác | Tách executor/resource pool, đặt timeout/backpressure |
| Muốn “song song nhanh hơn” trên dữ liệu rất nhỏ | Đo trước; sequential có thể tốt hơn |


## 9. Chương trình Java 8 hoàn chỉnh và kết quả thực tế

Chương trình thực hành gồm ba tình huống:

1. **CPU Fork/Join:** tính tổng 1..10000 bằng `RecursiveTask<Long>`, mẫu `left.fork()`, `right.compute()`, `left.join()`.
2. **I/O executor riêng:** một task chờ `CountDownLatch.await()` để giả lập lời gọi I/O chưa có kết quả. Trong lúc ấy, CPU pool **không bị chiếm** và vẫn tính tổng 1..1000; thread main sau đó nhả latch để task I/O hoàn thành.
3. **Managed blocking trong pool nhỏ:** một task trong `ForkJoinPool(1)` gọi `managedBlock` để chờ tín hiệu; một task khác được submit vào cùng pool để giải phóng tín hiệu. Đây là minh họa runtime có thể bù worker khi nhận diện điểm chặn, **không phải lời hứa bù worker vô hạn**.

Có `get(..., 10, TimeUnit.SECONDS)` và `finally` để bài test không cố ý đợi vô hạn khi điều kiện demo không được đáp ứng. Những giới hạn thời gian này là cơ chế phòng vệ cho ví dụ, không thay timeout giao thức mạng/DB trong ứng dụng thật.

**Lưu file `ForkJoinBlockingDemo.java`:**


```java
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.ForkJoinTask;
import java.util.concurrent.Future;
import java.util.concurrent.RecursiveTask;
import java.util.concurrent.TimeUnit;

public class ForkJoinBlockingDemo {
    static final class RangeSum extends RecursiveTask<Long> {
        private final long from;
        private final long toExclusive;

        RangeSum(long from, long toExclusive) {
            this.from = from;
            this.toExclusive = toExclusive;
        }

        @Override
        protected Long compute() {
            if (toExclusive - from <= 1_000L) {
                long sum = 0L;
                for (long i = from; i < toExclusive; i++) {
                    sum += i;
                }
                return sum;
            }
            long middle = from + (toExclusive - from) / 2L;
            RangeSum left = new RangeSum(from, middle);
            left.fork();
            long right = new RangeSum(middle, toExclusive).compute();
            return left.join() + right;
        }
    }

    static final class LatchBlocker implements ForkJoinPool.ManagedBlocker {
        private final CountDownLatch gate;

        LatchBlocker(CountDownLatch gate) {
            this.gate = gate;
        }

        @Override
        public boolean isReleasable() {
            return gate.getCount() == 0L;
        }

        @Override
        public boolean block() throws InterruptedException {
            gate.await();
            return true;
        }
    }

    public static void main(String[] args) throws Exception {
        ForkJoinPool cpuPool = new ForkJoinPool(2);
        ExecutorService ioPool = Executors.newFixedThreadPool(2);
        ForkJoinPool managedPool = new ForkJoinPool(1);
        CountDownLatch ioGate = new CountDownLatch(1);
        CountDownLatch managedGate = new CountDownLatch(1);

        try {
            long cpuSum = cpuPool.invoke(new RangeSum(1, 10_001));
            System.out.println("CPU fork/join sum 1..10000: " + cpuSum);

            CountDownLatch ioStarted = new CountDownLatch(1);
            Future<String> response = ioPool.submit((Callable<String>) () -> {
                ioStarted.countDown();
                ioGate.await();
                return "ready";
            });
            if (!ioStarted.await(10, TimeUnit.SECONDS)) {
                throw new AssertionError("I/O task not started");
            }
            long independent = cpuPool.invoke(new RangeSum(1, 1_001));
            System.out.println("CPU finished while I/O waits: " + independent);
            ioGate.countDown();
            System.out.println("I/O response after release: "
                    + response.get(10, TimeUnit.SECONDS));

            CountDownLatch managedStarted = new CountDownLatch(1);
            ForkJoinTask<String> blocked = managedPool.submit(() -> {
                managedStarted.countDown();
                ForkJoinPool.managedBlock(new LatchBlocker(managedGate));
                return "released";
            });
            if (!managedStarted.await(10, TimeUnit.SECONDS)) {
                throw new AssertionError("Managed worker not started");
            }
            ForkJoinTask<?> unlocker = managedPool.submit(
                    () -> managedGate.countDown());
            unlocker.get(10, TimeUnit.SECONDS);
            System.out.println("Managed unblock task: done");
            System.out.println("Managed blocked task: "
                    + blocked.get(10, TimeUnit.SECONDS));

            if (cpuSum != 50_005_000L || independent != 500_500L
                    || !response.isDone() || !blocked.isDone()
                    || managedGate.getCount() != 0L) {
                throw new AssertionError("Unexpected result");
            }
            System.out.println("Checks passed.");
        } finally {
            ioGate.countDown();
            managedGate.countDown();
            ioPool.shutdownNow();
            managedPool.shutdownNow();
            cpuPool.shutdownNow();
        }
    }
}
```

Biên dịch bằng JDK 17+ với ngôn ngữ/API Java 8 (hoặc dùng compiler JDK 8):

```bash
javac --release 8 ForkJoinBlockingDemo.java
java ForkJoinBlockingDemo
```

**Stdout đã kiểm tra trên OpenJDK 24:**


```text
CPU fork/join sum 1..10000: 50005000
CPU finished while I/O waits: 500500
I/O response after release: ready
Managed unblock task: done
Managed blocked task: released
Checks passed.
```

### 9.1. Đọc kết quả

- `CPU fork/join sum 1..10000` là tổng các số từ 1 đến 10000: 50.005.000. Đó là workload CPU, được chia thành tác vụ nhỏ.
- `CPU finished while I/O waits` bằng 500.500 cho 1..1000. Bởi I/O đang chờ trên executor riêng, CPU pool tiếp tục làm việc, không cần đợi mở `ioGate`.
- `I/O response after release` là `ready` sau khi main thread mở latch; nếu không mở latch, task mô phỏng sẽ tiếp tục chờ.
- `Managed unblock task` và `Managed blocked task` xác nhận kịch bản managedBlock với pool có target parallelism 1 chạy thành công trên runtime kiểm thử. **Không suy ra** mọi cấu hình sẽ tạo thêm worker khi hết tài nguyên.
- `Checks passed` chỉ in khi tất cả assert đều đúng.

### 9.2. Vì sao đây không phải benchmark?

Các lệnh in là kết quả **logic** có thể lặp lại chứ không đo tốc độ/throughput thực. Scheduling thực tế có thể khác nhau giữa JDK, CPU, hệ điều hành và tải máy. Chương trình chứng minh cơ chế với môi trường thử nghiệm, không xác nhận rằng `ManagedBlocker` có hiệu năng tốt nhất cho mọi hệ thống.

### 9.3. Xử lý interrupt và hủy tác vụ

`ManagedBlocker.block()` có thể ném `InterruptedException`. Trong ví dụ, lambda `Callable` cho phép truyền ngoại lệ ra Future, main chờ với timeout và `finally` mở latch rồi shutdown các executor.

Trong production, hãy quyết định rõ:
- Khi request bị cancel, có cancel task và đóng I/O resource không?
- `Future.get(timeout)` ném `TimeoutException` **không đồng nghĩa** công việc nền tự bị hủy.
- Nếu bắt `InterruptedException` ở một lớp không thể throws, thường phải khôi phục interruption flag bằng `Thread.currentThread().interrupt()` rồi kết thúc/propagate hợp lý.
- Timeout ở tầng network/DB/connection và giới hạn queue cần tồn tại độc lập với timeout chờ Future.

`shutdownNow()` chỉ là lời yêu cầu ngắt các tác vụ và trả về các tác vụ chưa bắt đầu; không bảo đảm mọi I/O tự thoát ngay nếu thư viện không hỗ trợ interrupt/cancellation. Với service thực, nên có lifecycle phối hợp shutdown và `awaitTermination` phù hợp. Trong demo, latch được mở ở finally để giúp các task chờ thoát.

## 10. Checklist thiết kế trước khi chọn ForkJoinPool

| Câu hỏi | Ý nghĩa thiết kế |
| --- | --- |
| Task chủ yếu CPU hay đợi I/O? | CPU → Fork/Join, I/O blocking → cân nhắc executor/virtual threads |
| Có tác vụ nguồn cần đợi nằm trong **chính pool** không? | Tránh phụ thuộc chéo làm nghẽn worker |
| Callback có thể chặn vô hạn không? | Đặt timeout và cơ chế cancel |
| Có khả năng dùng ManagedBlocker đúng hợp đồng không? | Pool có thể bù worker nếu cần |
| Common pool đang được những module nào dùng? | Tránh một RPC chặn làm chậm module khác |
| I/O downstream cho phép bao nhiêu kết nối? | Không tăng parallelism quá quota |
| Executor I/O có queue vô hạn không? | Thêm capacity, backpressure và rejection policy |
| Những thao tác CPU có đủ lớn để đáng chia không? | Đo overhead và target parallelism |
| Kết quả cần xử lý theo thứ tự cụ thể không? | Xây dependency rõ ràng, đừng dựa vào scheduling |
| Có thể dùng I/O async hoặc virtual threads không? | Xem phiên bản JDK và thư viện thật |

## 11. Các lỗi phổ biến

| Sai lầm | Vì sao nguy hiểm | Cách khắc phục |
| --- | --- | --- |
| Cho mọi HTTP/JDBC sync vào commonPool | Worker chờ mạng, công việc không liên quan bị ảnh hưởng | Executor I/O riêng, I/O async hoặc virtual threads |
| Nghĩ `supplyAsync` tự làm I/O nonblocking | Blocking call vẫn chiếm executor thread | Phân biệt async scheduling với async I/O |
| Dùng `parallelStream()` để gọi RPC cho mỗi phần tử | Saturation common pool và downstream | Giới hạn concurrency/backpressure |
| Đặt target parallelism = số request mạng | Fork/Join không phải connection scheduler | Thiết kế executor theo resource limits |
| Chờ Future của task được submit vào pool đang hết worker | Starvation/dependency cycle | Composition hoặc tách executor |
| Dùng `Thread.sleep` trong RecursiveTask để chờ dữ liệu | Worker không tính toán, làm giảm throughput | Cơ chế async hoặc managed blocking phù hợp |
| Nghĩ `ManagedBlocker` luôn tạo worker mới | Chỉ *có thể* bù, có giới hạn | Không phụ thuộc tuyệt đối vào compensation |
| Viết `isReleasable` có side effect | Runtime có thể gọi lại nhiều lần | Hàm kiểm tra nhẹ, thread-safe |
| Nuốt `InterruptedException` | Task không thể hủy đúng cách | Propagate/restore flag và dừng hợp lý |
| Có Future timeout nhưng không cancel/close tài nguyên | Công việc nền tiếp tục chạy | Chính sách cancellation/lifecycle |
| Dùng fixed thread pool nhưng bỏ qua queue capacity | Queue có thể phình và tăng latency | Bounded queue và rejection policy |
| Chọn virtual threads để tăng tốc CPU | Virtual threads không tăng CPU cores | Fork/Join hoặc CPU executor |
| Benchmark bằng một lần chạy demo | Sai vì JIT, scheduling, tải môi trường | Đo bằng JMH/load test thích hợp |

## 12. Bài tập thực hành và đáp án

**Bài 1.** Một `RecursiveTask` gọi HTTP đồng bộ trong `compute()`, các worker thường đứng chờ. Lựa chọn đầu tiên? — Tách HTTP blocking sang executor I/O hoặc dùng API I/O async, rồi truyền dữ liệu cho phần CPU; chỉ dùng managedBlock khi thật sự phải chặn trong pool.

**Bài 2.** `ForkJoinPool(1)` có A chờ latch và B mở latch nhưng B cũng nằm trong pool. Điều gì có thể xảy ra? — Nếu A blocking không được quản lý, B có thể không được chạy, gây starvation/deadlock.

**Bài 3.** `ForkJoinPool.managedBlock` có bảo đảm cấp thêm một thread mới không? — Không. Nó **có thể** bù worker khi cần và đủ điều kiện/tài nguyên.

**Bài 4.** Vì sao `isReleasable()` phải chịu gọi nhiều lần? — Framework kiểm tra lại xem còn cần chặn không; không đặt side effect chỉ được phép xảy ra một lần bên trong đó.

**Bài 5.** `ForkJoinTask.join()` và `InputStream.read()` có xử lý chờ như nhau không? — Không. `join()` là cơ chế phối hợp Fork/Join, còn blocking I/O tùy ý không nhất thiết được pool nhận diện.

**Bài 6.** `CompletableFuture.supplyAsync(() -> jdbcQuery())` có nghĩa query không blocking không? — Không. Supplier được lập lịch async nhưng `jdbcQuery` sync vẫn chặn worker.

**Bài 7.** Khi executor I/O `newFixedThreadPool(8)` quá tải, queue mặc định có hữu hạn không? — Không. Phải đặt giới hạn/backpressure riêng nếu cần kiểm soát memory/latency.

**Bài 8.** Java 21+ có lựa chọn nào cho nhiều blocking I/O task? — Virtual threads, nhưng vẫn cần giới hạn downstream và timeout.

**Bài 9.** `Future.get(2,SECONDS)` timeout thì future có tự bị cancel không? — Không nhất thiết; cần thiết kế cancellation và giải phóng tài nguyên.

**Bài 10.** Khi nào có thể giữ Fork/Join mà không cần ManagedBlocker? — Khi task chủ yếu CPU-bound, chia/gộp đúng và không có blocking đáng kể.

## 13. Tài liệu chính thức, còn áp dụng

- [Oracle Java SE 26 — ForkJoinPool](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ForkJoinPool.html): work-stealing, target parallelism, `commonPool` và `managedBlock`.
- [Oracle Java SE 26 — ForkJoinPool.ManagedBlocker](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ForkJoinPool.ManagedBlocker.html): `isReleasable`, `block` và cách pool có thể duy trì parallelism.
- [Oracle Java SE 26 — ForkJoinTask](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ForkJoinTask.html): fork/join subtasks và coordination.
- [Oracle Java SE 26 — Executors](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/Executors.html): executor cho I/O, work-stealing pools và virtual-thread executor từ Java 21.
- [Oracle Java SE 27 — Virtual Threads](https://docs.oracle.com/en/java/javase/27/core/virtual-threads.html): giải pháp hiện đại cho blocking I/O có nhiều tác vụ chờ.
- [Oracle Java SE 8 — ForkJoinPool](https://docs.oracle.com/javase/8/docs/api/java/util/concurrent/ForkJoinPool.html): kiểm tra những API chính (`ForkJoinPool`, `ManagedBlocker`) đã có từ Java 8.

**Ghi nhớ:** Work-stealing khai thác tốt CPU khi subtasks còn sẵn sàng; **blocking I/O chiếm worker** và có thể gây starvation. Ưu tiên tách I/O hoặc dùng async/virtual threads khi phù hợp. `managedBlock` giúp ForkJoinPool có cơ hội bù worker nhưng **không biến chặn thành nonblocking**, không tăng tốc network và không thay thế giới hạn tài nguyên. Thiết kế timeout, cancellation, backpressure và phép thử tải theo workload thực.
