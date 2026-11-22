# ForkJoinPool.commonPool và tài nguyên dùng chung trong Java

## 1. Bức tranh tổng quan: một pool chung trong JVM

`ForkJoinPool` thuộc `java.util.concurrent`; nó chạy các `ForkJoinTask` bằng cơ chế **work-stealing**. Từ Java 8, Java cung cấp `ForkJoinPool.commonPool()`: một **pool dùng chung được tạo và quản lý bởi runtime**, để các tác vụ Fork/Join không nhất thiết phải tự tạo thread pool cho mỗi lời gọi.

```java
ForkJoinPool shared = ForkJoinPool.commonPool();
ForkJoinPool same = ForkJoinPool.commonPool();

boolean reused = shared == same; // true
```

Đây là snippet trong method với `import java.util.concurrent.ForkJoinPool;`. Hai lần gọi trong cùng JVM trả về **cùng common pool**, không tạo thêm hai executor độc lập. Pool này thường được các tác vụ Fork/Join và một số API xử lý song song mặc định sử dụng. Sự tiện lợi đi kèm một trách nhiệm: **code ở một thư viện hoặc module có thể chiếm tài nguyên mà code ở module khác đang chờ**.

Cần phân biệt ba cấp:

- **`ForkJoinPool.commonPool()`:** executor Fork/Join dùng chung **trong JVM**; tài nguyên có giới hạn và workload của các thành phần có thể ảnh hưởng nhau.
- **`new ForkJoinPool(n)`:** tạo một pool **riêng**, có vòng đời do ứng dụng quản lý; dùng khi có lý do cần cô lập và điều khiển mức song song.
- **`ExecutorService` khác** (ví dụ `ThreadPoolExecutor`): thường là lựa chọn dễ kiểm soát hơn cho các công việc blocking I/O theo hàng đợi và chính sách tải riêng.

**Không nhầm common pool với một dịch vụ phân tán.** Hai JVM hoặc hai pod khác nhau không dùng chung object executor này. Nhưng trong **cùng một JVM**, các thư viện dùng pool mặc định có thể tạo **tranh chấp CPU, worker, queue và độ trễ**.

### 1.1. Kết quả cần đạt

Sau bài này, người học có thể:

1. Giải thích tại sao `commonPool` được chia sẻ và vòng đời của nó không do từng module sở hữu.
2. Phân biệt Fork/Join, parallel stream và `CompletableFuture` trong các tình huống **có thể sử dụng** common pool.
3. Phân biệt tác vụ CPU-bound với **blocking I/O**, lý do starvation và nested waits xảy ra.
4. Dùng `RecursiveTask`/`fork`/`join` một cách có cấu trúc; chọn pool riêng khi cần cô lập.
5. Tránh tự gọi `shutdown` cho common pool, quản lý `shutdown` với pool riêng.
6. Hiểu `ManagedBlocker`, metrics, cấu hình common pool và các caveat theo phiên bản JDK.
7. Viết ví dụ Java 8 có kết quả ổn định, không phụ thuộc số core hay tên worker thread.

## 2. `ForkJoinPool` khác thread pool hàng đợi thông thường ở điểm nào?

`ForkJoinPool` được thiết kế tốt cho các phép tính **chia nhỏ thành nhiều tác vụ độc lập**, sau đó **ghép kết quả**. Một tác vụ có thể tạo các tác vụ con; các worker tự lấy việc trong queue của mình và **steal** việc từ worker khác khi rảnh, tăng khả năng tận dụng các CPU core.

```text
Tác vụ gốc: SUM[1..100)
          |
      chia đôi
      /      \
 SUM[1..50)  SUM[50..100)
    |             |
 chia tiếp       chia tiếp
    |             |
 local queues / work-stealing giữa các worker
    \             /
       join kết quả
            |
          SUM
```

`RecursiveTask<V>` phù hợp khi trả một giá trị, `RecursiveAction` khi tác vụ không trả payload. `ForkJoinPool` là một `ExecutorService`, nên cũng có `submit`/`execute`/`invoke` cho nhiều loại task. Nhưng mục tiêu của work-stealing là **công việc có thể chia nhỏ và ghép**; không phải thay thế mọi executor của ứng dụng.

### 2.1. Tư duy fork/join đúng

```java
protected Integer compute() {
    if (end - start <= THRESHOLD) {
        return calculateDirectly(start, end);
    }
    int middle = (start + end) / 2;
    SumTask left = new SumTask(start, middle);
    SumTask right = new SumTask(middle, end);

    left.fork();                  // lên lịch tác vụ con
    int rightValue = right.compute(); // tính một nhánh tại đây
    int leftValue = left.join();      // đợi nhánh đã fork
    return leftValue + rightValue;
}
```

Đây là **method snippet**, cần class `SumTask extends RecursiveTask<Integer>`, các trường `start`/`end`, `THRESHOLD` và method `calculateDirectly` do ví dụ định nghĩa. Phần runnable ở mục 14 cung cấp một bản hoàn chỉnh.

Mẫu **fork một nhánh, tự tính nhánh còn lại, rồi join** thường giảm việc tạo task không cần thiết so với fork cả hai nhánh trong mọi trường hợp. `THRESHOLD` cần đủ lớn để tránh chi phí phân task lớn hơn công tính thật, nhưng không quá lớn đến mức chỉ có một vài task chạy.

### 2.2. Tác vụ quá nhỏ không phải miễn phí

Mỗi task tạo/sắp lịch có overhead; khi mỗi task chỉ cộng vài số, fork/join có thể **chậm hơn** vòng `for` tuần tự. Ngược lại, chia quá ít thì không tận dụng concurrency. Tối ưu threshold dựa trên workload và benchmark, không áp đặt con số tối ưu chung cho mọi CPU/JDK.

## 3. `commonPool()`: tạo một lần và chia sẻ rộng

Chữ ký:

```java
public static ForkJoinPool commonPool()
```

`commonPool()` trả về đối tượng pool chung được dựng tĩnh bởi Java runtime. Đây là **API Java 8 và vẫn áp dụng trên các JDK hiện đại**.

```java
ForkJoinPool pool = ForkJoinPool.commonPool();
Future<Integer> answer = pool.submit(() -> 6 * 7);

// get() chờ task có kết quả.
int value = answer.get(); // 42
```

Đây là snippet trong method có `throws Exception` hoặc xử lý checked exceptions từ `Future.get`; cần import `ForkJoinPool`, `Future`. `submit` không đòi hỏi phải khởi tạo `new ForkJoinPool`, nhưng task này sẽ cùng chia worker/queue với những code khác dùng common pool.

### 3.1. Shared không có nghĩa không giới hạn

Common pool có số worker **hữu hạn**, khả năng tạo thread bù chịu giới hạn runtime, và CPU cũng hữu hạn. Nếu một module gửi hàng nghìn task chạy lâu, các module khác có thể tăng thời gian chờ ngay cả khi logic của chúng hoàn toàn đúng.

Đừng diễn giải `ForkJoinPool.commonPool()` như "sẽ có một thread riêng cho request này" hoặc "không bao giờ bị nghẽn vì Java tự tạo worker vô hạn".

### 3.2. Một common pool không sở hữu tất cả thread trong JVM

Không phải mọi API bất đồng bộ Java đều tự động chạy trên common pool. `new Thread(...)` tạo thread riêng; `Executors.newFixedThreadPool(...)` có executor riêng; client HTTP/DB/framework có thể dùng event loop hoặc pool được quản lý khác.

Ngay cả trong `CompletableFuture`, overload có `Executor` có thể đưa task ra ngoài common pool. Vì vậy, khi debug hiệu năng, hãy nhìn **đường gửi công việc thực tế**, đừng suy đoán chỉ vì mã có chữ “async”.

### 3.3. Tác vụ ForkJoin không nhất thiết luôn chạy trên common pool

`ForkJoinTask.fork()` trên một worker đang thực hiện trong một `ForkJoinPool` thông thường sẽ đưa subtasks vào **pool hiện tại**; khi sử dụng từ ngoài fork/join worker, tác vụ fork có thể dùng common pool. Nếu bạn **chủ động gửi root task** vào pool riêng, recursive task được fork từ worker của pool ấy sẽ tham gia pool riêng đó.

Ví dụ:

```java
ForkJoinPool dedicated = new ForkJoinPool(2);
try {
    int sum = dedicated.invoke(new RangeSum(1, 11));
    // RangeSum là RecursiveTask trong chương trình mục 14.
} finally {
    dedicated.shutdown();
}
```

Việc này giúp kiểm soát nơi chạy **cây ForkJoinTask do bạn trực tiếp viết**. Không nên suy ra một lời gọi `parallelStream()` tùy ý bên trong custom pool luôn được ràng buộc vào custom pool theo một hợp đồng API public ổn định; thiết kế như vậy có thể phụ thuộc implementation JDK.

## 4. Cách một `RecursiveTask` dùng common pool

Mã rút gọn cho bài toán cộng số:

```java
final class RangeSum extends RecursiveTask<Integer> {
    private final int from, toExclusive;

    RangeSum(int from, int toExclusive) {
        this.from = from;
        this.toExclusive = toExclusive;
    }

    @Override
    protected Integer compute() {
        if (toExclusive - from <= 3) {
            int sum = 0;
            for (int i = from; i < toExclusive; i++) sum += i;
            return sum;
        }
        int mid = (from + toExclusive) / 2;
        RangeSum left = new RangeSum(from, mid);
        RangeSum right = new RangeSum(mid, toExclusive);
        left.fork();
        int rightSum = right.compute();
        return left.join() + rightSum;
    }
}
```

Đây là **class snippet**, cần `import java.util.concurrent.RecursiveTask;`. Dùng một phép chia công việc nhỏ để thấy cấu trúc; với phép cộng đơn giản này, không khẳng định song song sẽ nhanh hơn.

```java
ForkJoinPool pool = ForkJoinPool.commonPool();
int sum = pool.invoke(new RangeSum(1, 11)); // 1+...+10 = 55
```

`invoke` chờ tác vụ gốc hoàn tất rồi trả kết quả. Mọi lần `join` trong `compute` được dùng để ghép kết quả subtasks. Với việc tính toán có nhiều mức fork, **không tự khởi động một blocking I/O** trong từng leaf task nếu không kiểm soát giới hạn; xem mục 8.

### 4.1. `fork`/`join` là một mô hình phụ thuộc

`fork` gửi subtask để có thể chạy song song; `join` đợi subtask hoàn thành và lấy result. Không nên tạo một vòng dependency **A chờ B, B chờ A**; không scheduler nào biến vòng chờ logic này thành một thuật toán đúng.

Nếu có task D mà không ai `join`, không có nghĩa tác vụ sẽ hoàn thành trước lúc `main` kết thúc. Thời điểm hoàn tất cần được biểu diễn bằng `Future`, `ForkJoinTask` hoặc quan hệ phụ thuộc rõ.

## 5. `parallelStream()` và common pool

Các phép toán parallel stream của thư viện stream chuẩn **thường sử dụng common ForkJoinPool khi được khởi phát từ thread ứng dụng thông thường**, để thực thi pipeline trên nhiều worker. Điều này giúp viết xử lý tập dữ liệu song song với ít mã:

```java
List<Integer> numbers = Arrays.asList(1, 2, 3, 4, 5);

int sum = numbers.parallelStream()
    .mapToInt(Integer::intValue)
    .sum(); // 15
```

Đây là snippet với `java.util.List` và `java.util.Arrays`. Kết quả 15 là phép reduction kết hợp được, nhưng **số thread và thứ tự phần tử được xử lý không được cố định**. Không viết test dựa trên tên thread `ForkJoinPool.commonPool-worker-...` hoặc cho rằng mỗi phần tử dùng một thread riêng.

### 5.1. Hai pipeline khác nhau có thể cạnh tranh worker

```text
Module báo cáo:   parallelStream() ---> common pool -----\
                                                        +--> cùng worker/CPU
Module phân tích: parallelStream() ---> common pool -----/
```

Nếu module báo cáo đang chạy một bước nặng hoặc blocking, việc hoàn thành của module phân tích có thể chậm. Việc một hàm dùng stream song song có thể gây **ảnh hưởng hiệu năng giữa các module không liên quan** trong cùng JVM.

### 5.2. Parallel stream có thể chạy một phần trên thread gọi

Không nên khẳng định "mọi lambda trong `parallelStream` chạy trên common worker". Trong một số pipeline và runtime, **thread gọi terminal operation cũng có thể tham gia**. Nếu lambda phụ thuộc vào ThreadLocal, context security hay tên worker, đây là bẫy.

Đọc/ghi context cần được thiết kế độc lập với tên/identity của thread. `parallel()` không phải lệnh chuyển luồng một cách bảo đảm cho từng phần tử.

### 5.3. Không tự xem parallel là nhanh hơn

`parallelStream` có thêm chi phí chia nhỏ, ghép, scheduling và synchronization. Với dataset nhỏ hoặc phép biến đổi rất nhẹ, `stream()` thường đơn giản và có thể nhanh hơn. Với `sorted()`, `distinct()`, encounter order hoặc các collector không concurrent, chi phí có thể tăng đáng kể.

```java
int sequential = numbers.stream()
    .mapToInt(Integer::intValue)
    .sum();

int parallel = numbers.parallelStream()
    .mapToInt(Integer::intValue)
    .sum();
// Cả hai bằng 15, hiệu năng phụ thuộc workload.
```

Đây là snippet, không phải một phép benchmark đủ cơ sở để kết luận speedup. Đo bằng workload thực và JMH nếu cần đánh giá tối ưu.

## 6. `CompletableFuture` mặc định cũng có thể dùng common pool

Trong Java 8, `CompletableFuture.supplyAsync(supplier)`, `runAsync(runnable)` và nhiều phương thức có hậu tố `Async` **không có đối số `Executor`** dùng cơ chế async mặc định dựa trên `ForkJoinPool.commonPool()`, với ngoại lệ khi common pool không hỗ trợ hơn một worker song song thì implementation sử dụng cơ chế tạo thread thay thế cho mỗi tác vụ.

```java
CompletableFuture<Integer> result =
    CompletableFuture.supplyAsync(() -> 21 * 2);

int value = result.join(); // 42
```

Đây là snippet với `import java.util.concurrent.CompletableFuture;`. **Không có cam kết** rằng `supplyAsync` này luôn dùng đúng một worker của common pool trong mọi cấu hình/JDK; đặc biệt trên môi trường có parallelism thấp, fallback executor có thể khác.

### 6.1. Không nhầm `thenApply` và `thenApplyAsync`

```java
CompletableFuture<String> original =
    CompletableFuture.completedFuture("java");

CompletableFuture<String> sync =
    original.thenApply(String::toUpperCase);

CompletableFuture<String> async =
    original.thenApplyAsync(String::toUpperCase);
```

`thenApply` **không có hậu tố Async** có thể chạy trên thread hoàn thành stage trước hoặc thread đăng ký continuation khi stage đã xong. `thenApplyAsync` không có executor yêu cầu cơ chế async mặc định; nó có thể đưa việc tới common pool hoặc fallback theo chính sách tương ứng.

Nhiều developer nghĩ "đã dùng `CompletableFuture` thì lúc nào cũng có thread mới", nhưng `completedFuture` là kết quả có sẵn và `thenApply` không buộc async.

### 6.2. Chọn executor rõ ràng khi cần cô lập

```java
ExecutorService isolated = Executors.newFixedThreadPool(4);

try {
    CompletableFuture<String> stage =
        CompletableFuture.supplyAsync(
            () -> fetchFromRemoteService(),
            isolated);
    String data = stage.join(); // chỉ để minh họa demo/test
} finally {
    isolated.shutdown();
}
```

Đây là **snippet kiến trúc**, `fetchFromRemoteService` do ứng dụng định nghĩa; cần import `ExecutorService`, `Executors`, `CompletableFuture`. Trong ứng dụng production, thường **tái sử dụng một executor theo vòng đời service**, không tạo pool rồi `join` trong từng request. Với I/O có thời gian chờ, cần timeout của client và chính sách giới hạn concurrency/queue; một `newFixedThreadPool` đơn thuần không tự đặt bound cho queue mặc định.

### 6.3. Bài toán cạnh tranh giữa `parallelStream` và CompletableFuture

```text
Request A: CompletableFuture.supplyAsync(CPU) ---> \
                                                  common pool
Request B: parallelStream(CPU) -----------------> /
Request C: CompletableFuture.runAsync(blocking) ->/
```

Trong cùng JVM, các workload có thể cùng ảnh hưởng **khả năng chạy task**. Nếu request C chiếm worker để chờ I/O lâu, request A/B có thể gặp latency khó dự đoán. Không suy ra ngữ nghĩa công việc sai chỉ từ việc chậm; hãy quan sát queue, active threads và thread dumps trước khi kết luận.

## 7. Các loại tài nguyên dùng chung và giới hạn cần quan sát

`commonPool` chia sẻ không chỉ **thread**. Trong một JVM, các tác vụ còn cạnh tranh:

- **CPU time và core:** task tính toán nặng có thể làm các task khác phải chờ.
- **Worker availability:** task đang block giữ một worker mà không làm công việc hữu ích.
- **Work queues:** nhiều task nhỏ hoặc task tới nhanh hơn tốc độ xử lý có thể tăng backlog.
- **Bộ nhớ:** task, closure và các object chứa dữ liệu vẫn chiếm heap khi đang chờ/chạy.
- **Cache, memory bandwidth và GC:** nhiều task có thể cùng gây áp lực lên tài nguyên máy.
- **Tài nguyên bên ngoài:** mọi tác vụ có thể cùng tranh DB connections, API rate limit hoặc disk I/O nếu dùng chung client/pool khác.

**Một pool có parallelism phù hợp với CPU không giới hạn số request mạng đồng thời** và không tự áp dụng rate limit của dịch vụ ngoài. Dùng semaphore, client connection pool, hàng đợi giới hạn hoặc một hệ thống concurrency control riêng khi yêu cầu.

### 7.1. Một thư viện có thể ảnh hưởng cả dịch vụ

Nếu một dependency bên thứ ba mặc định gửi tác vụ vào `commonPool`, thay đổi cách dùng ở một module có thể ảnh hưởng module khác. Khi triển khai một service có SLA chặt, cần biết các chỗ gọi `CompletableFuture.*Async` không executor và những `parallelStream` có thể chiếm tài nguyên chung.

### 7.2. ThreadLocal và request context không tự được truyền

Thread của common pool được **tái sử dụng** giữa các tác vụ; context trong `ThreadLocal` của thread request không tự được sao chép một cách bảo đảm sang worker. Log tracing, security principal, MDC và dữ liệu theo request cần propagation **tường minh** (hoặc qua framework đã định nghĩa cơ chế).

Không dựa vào `InheritableThreadLocal` như một cơ chế truyền request context đáng tin cho thread pool đã tạo trước đó. Nếu code có sử dụng ThreadLocal trên worker, phải cleanup thích hợp để tránh rò rỉ ngữ cảnh sang việc khác.

## 8. CPU-bound, blocking I/O và nguy cơ starvation

Work-stealing có ích khi worker **đang tính toán** và có các subtask sẵn để lấy. Nhưng một worker bị chặn ở:

- `Thread.sleep`,
- I/O mạng/đọc file hoặc truy vấn JDBC,
- `CountDownLatch.await`/`BlockingQueue.take`/`Object.wait`,
- một lời gọi blocking `Future.get` ngoài cơ chế fork/join,
- hoặc một lock dùng không đúng,

thì worker đó có thể **không làm tác vụ CPU khác** trong lúc chờ. `ForkJoinPool` có cơ chế phối hợp cho các `ForkJoinTask.join` và `ManagedBlocker`, nhưng không bảo đảm tự bù số worker trong mọi loại **unmanaged blocking**.

### 8.1. Một ví dụ gây chậm do tài nguyên chung

```java
// Ví dụ KHÔNG khuyến nghị cho I/O lâu:
CompletableFuture<String> data =
    CompletableFuture.supplyAsync(() -> {
        return blockingHttpCall();
    });
```

Đây là snippet kiến trúc, `blockingHttpCall` do ứng dụng định nghĩa. Không truyền executor khiến task thường đi qua cơ chế async mặc định, có khả năng cạnh tranh common pool với tác vụ CPU của phần khác. Nếu số call tăng mạnh, thread bị chặn có thể gây **starvation** hoặc tăng tail latency.

### 8.2. Nested waiting có thể tạo vòng chờ logic

Ví dụ khái niệm:

```text
Task A trên pool chờ kết quả B.
Task B được xếp hàng trên cùng pool hoặc cần A giải phóng tài nguyên.
Không còn worker đủ điều kiện để B hoàn thành.
=> A chờ rất lâu hoặc deadlock do phụ thuộc.
```

Không khẳng định mọi `join/get` trong ForkJoinPool đều gây deadlock; implementation có những cơ chế trợ giúp/phụ bù cho dạng chờ nhận biết được. Nhưng **vòng phụ thuộc nghiệp vụ** hoặc blocking không được quản lý vẫn có thể gây liveness problem.

**Tốt hơn:** diễn đạt phụ thuộc bằng `thenCompose`/`thenCombine` để không chiếm worker chỉ nhằm ngồi chờ; nếu phải gọi I/O blocking, chuyển sang executor riêng có giới hạn tải, hoặc API nonblocking thật.

### 8.3. Java 21+ virtual threads không phải thay đổi mặc định của common pool

Nếu ứng dụng chạy trên Java hiện đại có virtual threads, có thể cân nhắc mô hình concurrency phù hợp với blocking I/O (cùng giới hạn concurrency/rate limits). Nhưng đây là **năng lực bổ sung sau Java 8**, không có nghĩa `parallelStream` hay `ForkJoinPool.commonPool()` tự chuyển thành một executor virtual-thread chuyên dụng. Bài này giữ ví dụ runnable trong phạm vi Java 8.

## 9. `ForkJoinPool.ManagedBlocker`: thông báo thao tác có thể block

Java 8 cung cấp `ForkJoinPool.managedBlock(ForkJoinPool.ManagedBlocker)` để các tác vụ cần chờ có thể **thông báo cho ForkJoinPool** biết việc blocking. Khi được gọi bởi worker ForkJoinPool, runtime **có thể** kích hoạt worker bù để duy trì mức song song phù hợp.

Giao diện `ManagedBlocker` có hai method:

- `isReleasable()`: kiểm tra **không cần chờ nữa** hay chưa; nên rẻ và không block.
- `block()`: thực hiện bước chờ hoặc thao tác có thể block, rồi trả boolean thể hiện việc có thể kết thúc chu kỳ blocking.

`managedBlock` có thể gọi lặp lại `isReleasable` và `block`; implementation **không đảm bảo sẽ luôn tạo thêm thread** trong mọi cấu hình hay khi đã chạm giới hạn tài nguyên.

### 9.1. Ví dụ wrapper cho `CountDownLatch`

```java
static final class LatchBlocker
        implements ForkJoinPool.ManagedBlocker {
    private final CountDownLatch latch;

    LatchBlocker(CountDownLatch latch) {
        this.latch = latch;
    }

    @Override
    public boolean isReleasable() {
        return latch.getCount() == 0L;
    }

    @Override
    public boolean block() throws InterruptedException {
        if (!isReleasable()) {
            latch.await();
        }
        return true;
    }
}

// Dùng trong method có quyền propagate InterruptedException:
ForkJoinPool.managedBlock(new LatchBlocker(doneLatch));
```

Đây là **snippet trong class và method**, cần `ForkJoinPool`, `CountDownLatch`, biến `doneLatch` đã khai báo. Mục đích là **minh họa hợp đồng ManagedBlocker**, không phải khuyến nghị mọi ứng dụng chờ latch theo cách này.

### 9.2. Không biến `ManagedBlocker` thành giải pháp cho I/O không giới hạn

`ManagedBlocker` giúp worker-aware waiting trong một số tình huống, nhưng:

- Không giảm số request đang đợi database hoặc network.
- Không áp giới hạn connection, rate limit hay timeout.
- Không khắc phục vòng dependency sai.
- Không làm một thư viện blocking tự có cancellation an toàn.
- Không bảo đảm bù vô hạn worker khi nhiều task cùng block.

Nếu thiết kế thật sự chủ yếu là I/O blocking, **isolation bằng executor phù hợp hoặc API nonblocking** thường rõ ràng hơn việc gói mọi call vào `managedBlock`.

## 10. Vì sao và khi nào nên tạo `ForkJoinPool` riêng?

Khi một workload CPU song song nặng có thể chiếm common pool quá lâu hoặc cần mức song song riêng, `new ForkJoinPool(parallelism)` cho phép tạo **pool độc lập**.

```java
ForkJoinPool cpuPool = new ForkJoinPool(2);
try {
    int total = cpuPool.invoke(new RangeSum(1, 9));
    // total == 36
} finally {
    cpuPool.shutdown();
}
```

`RangeSum` là class `RecursiveTask` được định nghĩa ở mục 4 và chương trình đầy đủ mục 14. Khởi tạo pool riêng là quyết định quản trị tài nguyên, nên nó có **owner**, cơ chế khởi tạo một lần, metrics và chính sách shutdown khi service dừng.

### 10.1. Ưu điểm và chi phí

**Ưu điểm:** workload có thể được giao thread budget riêng, dễ quan sát metrics riêng và không trực tiếp gửi root ForkJoinTask của bạn vào common pool.

**Chi phí:** thêm worker threads, bộ nhớ, CPU context switching và một executor cần đóng đúng lúc. Nếu có 50 module mỗi module tạo `new ForkJoinPool(32)`, tổng tài nguyên có thể còn tệ hơn chia sẻ một common pool.

Một custom pool không tự cô lập CPU core vật lý với ứng dụng còn lại; tất cả vẫn cùng dùng CPU của hệ điều hành, nên **isolation của queue/worker khác với isolation tài nguyên máy tuyệt đối**.

### 10.2. Không tạo pool cho mỗi phần tử/request

**Không nên:**

```java
for (Record record : records) {
    ForkJoinPool temporary = new ForkJoinPool(4);
    try {
        temporary.submit(() -> process(record)).join();
    } finally {
        temporary.shutdown();
    }
}
```

Đây là snippet anti-pattern, với `Record`/`records`/`process` được ứng dụng định nghĩa. Nó tạo, gửi, chờ rồi đóng một pool cho mỗi record: rất tốn kém và gần như tuần tự vì mỗi vòng lập tức `join`.

**Nên:** tái sử dụng pool thuộc vòng đời service hoặc submit một cây task/reduction có thể chia hiệu quả; khi không cần concurrency thật thì dùng vòng lặp tuần tự.

### 10.3. Phải có shutdown/awaitTermination cho pool riêng

`ForkJoinPool` riêng là executor mà ứng dụng sở hữu. Khi kết thúc vòng đời, gọi `shutdown()`, xử lý thời gian chờ và có chính sách `shutdownNow()`/cancellation khi cần. Đừng đóng pool riêng khi còn request sẽ submit task mới.

```java
cpuPool.shutdown();
try {
    if (!cpuPool.awaitTermination(10, TimeUnit.SECONDS)) {
        cpuPool.shutdownNow();
    }
} catch (InterruptedException ex) {
    cpuPool.shutdownNow();
    Thread.currentThread().interrupt();
}
```

Đây là snippet lifecycle, chỉ chạy **khi service thật sự ngừng nhận công việc**, cần `TimeUnit`. Không coi `shutdownNow()` là một phép bảo đảm mọi task đang chạy dừng ngay: task có thể bỏ qua interruption hoặc còn thao tác bên ngoài.

## 11. `ExecutorService` riêng cho blocking I/O

Một workload chờ mạng/JDBC thường không được hưởng lợi từ work-stealing theo kiểu CPU divide-and-conquer. Chọn executor chuyên dụng với **giới hạn concurrency**, chính sách queue, timeout và connection pool hợp lý.

```java
ExecutorService blockingPool = Executors.newFixedThreadPool(4);

try {
    CompletableFuture<String> response =
        CompletableFuture.supplyAsync(
            () -> "response-from-service",
            blockingPool);
    String text = response.join(); // "response-from-service"
} finally {
    blockingPool.shutdown();
}
```

Đây là snippet chạy được trong method nếu có imports `ExecutorService`, `Executors`, `CompletableFuture`. Trong production, không dựng executor cho mỗi call; dùng một executor **được quản lý ở cấp service**, và không gọi `join` trong luồng xử lý nonblocking chỉ để lấy kết quả.

**Quan trọng:** `Executors.newFixedThreadPool(n)` có thể dùng queue không bị giới hạn theo số lượng task. Nó giới hạn số worker đang chạy nhưng **không tự giới hạn backlog**, nên phải bổ sung admission control/bounded queue hoặc giải pháp executor phù hợp nếu dịch vụ có nguy cơ overload.

### 11.1. Chia pool theo loại công việc, không chia tùy tiện

Ví dụ phân tách:

| Loại công việc | Đường chạy thường phù hợp | Tại sao |
| --- | --- | --- |
| Tính toán CPU nhỏ và có thể chia | Common pool hoặc custom ForkJoinPool | Work-stealing/parallel reductions |
| Batch CPU rất nặng có SLA riêng | Custom ForkJoinPool có budget | Tránh làm cạn worker chung |
| HTTP/JDBC blocking | Executor I/O giới hạn hoặc client async thật | Worker budget theo công việc chờ |
| Tác vụ đã có kết quả | `CompletableFuture.completedFuture(value)` | Không cần scheduling |
| Tác vụ event loop nonblocking | Cơ chế event loop/client được quản lý | Không chiếm worker để chờ |
| Task có thứ tự/độc quyền | Executor chuyên dụng/hàng đợi rõ | ForkJoin không tự giữ business ordering |
| Task kéo dài suốt vòng đời service | Executor riêng/cơ chế worker service | Không chiếm common pool vô thời hạn |

Không có công thức cứng "CPU pool = N, I/O pool = 100N". Số thread phù hợp phụ thuộc thời gian chờ, memory, connection pool, latency SLO, rate limits và khả năng backpressure.

## 12. Cấu hình common pool và đếm parallelism

Trong Java 8, các JVM system properties thường được tài liệu hóa để ảnh hưởng quá trình xây dựng common pool:

- `java.util.concurrent.ForkJoinPool.common.parallelism` — target parallelism (giá trị không âm theo contract common pool).
- `java.util.concurrent.ForkJoinPool.common.threadFactory` — tên factory cho worker threads.
- `java.util.concurrent.ForkJoinPool.common.exceptionHandler` — handler cho exception không được xử lý ở worker.

Ví dụ cấu hình ở **startup**, không phải đặt trong một task đã chạy:

```bash
java -Djava.util.concurrent.ForkJoinPool.common.parallelism=4 App
```

Đây là **lệnh minh họa**, `App` là main class do ứng dụng định nghĩa. Các thuộc tính được xét khi **common pool khởi tạo**; không nên kỳ vọng `System.setProperty` ở giữa vòng đời sẽ điều chỉnh ngay pool đã tạo.

JDK hiện đại có thể bổ sung cấu hình/khả năng điều chỉnh pool và thay đổi chính sách sizing. **Đừng cứng hóa một giá trị mặc định áp dụng cho mọi phiên bản JVM/container**. Kiểm tra API/flags đúng JDK đang triển khai. Việc chỉnh common pool là **quyết định toàn ứng dụng**, không phải một cấu hình riêng cho một method.

### 12.1. `getCommonPoolParallelism` và `getParallelism` nói về target, không cam kết thread count đúng bằng

```java
int commonTarget = ForkJoinPool.getCommonPoolParallelism();
ForkJoinPool common = ForkJoinPool.commonPool();
int poolTarget = common.getParallelism();
int currentWorkers = common.getPoolSize();
```

Đây là snippet; không in số cụ thể vì phụ thuộc cấu hình/JDK. Một target parallelism không có nghĩa mỗi request được sở hữu ngần ấy thread hoặc `getPoolSize` luôn bằng target. Trong tình huống blocking đã được quản lý, pool có thể thay đổi số worker theo chính sách/giới hạn hiện hành.

### 12.2. Giảm common parallelism về 0 là thay đổi nguy hiểm

Javadoc Java 8 ghi nhận có thể hạn chế hoặc vô hiệu hóa worker chung bằng parallelism quá thấp hoặc factory đặc biệt; điều này **có thể khiến task chưa được join không có worker để chạy**. `CompletableFuture` trên một số cấu hình có thể dùng cơ chế executor dự phòng; đừng dựa vào điều đó để chữa mọi tình huống của `ForkJoinTask`.

Không đặt parallelism = 0 như cách "tối ưu CPU" trong production mà chưa hiểu tất cả code/framework phụ thuộc common pool. Ưu tiên quản lý từng workload bằng executor rõ owner và thử nghiệm tải trước.

### 12.3. Số CPU thấy được không luôn bằng số worker thực

`Runtime.getRuntime().availableProcessors()` có thể phản ánh mức CPU do JVM/OS/container nhận diện. Đừng suy diễn từ số lõi vật lý của máy chủ rằng common pool có số worker cố định tương ứng. Trong container hoặc khi cấu hình JVM thay đổi, số khả dụng có thể khác.

Vì vậy **không đặt expected stdout là “parallelism=7”**, không viết test mặc định scheduler tạo bao nhiêu thread, và không so thời gian chạy của hai bài toán nhỏ như một tuyên bố cải thiện hiệu năng.

## 13. Lifecycle: vì sao không gọi `shutdown` trên common pool?

`ForkJoinPool.commonPool()` thuộc runtime và được chia sẻ. Theo Javadoc, lời gọi `shutdown()` hoặc `shutdownNow()` **không làm thay đổi run state của common pool**. Không có ý nghĩa "module A sở hữu pool này, vậy module A đóng nó khi xong".

```java
ForkJoinPool shared = ForkJoinPool.commonPool();

// Không làm trong lifecycle riêng của một service:
// shared.shutdown();
// shared.shutdownNow();
```

Đây là snippet minh họa **điều cần tránh**, không phải code chạy lệnh shutdown. Với custom pool **do bạn tạo**, trách nhiệm đóng thuộc về owner của pool đó.

### 13.1. Common pool và lúc kết thúc JVM

Worker threads của ForkJoinPool thường là **daemon**. Đặc biệt với common pool, chương trình không nên khởi chạy task async rồi để `main` kết thúc mà không có cơ chế đợi kết quả; khi JVM dừng, phần công việc còn chạy **không có bảo đảm hoàn tất**.

```java
CompletableFuture<Void> stored =
    CompletableFuture.runAsync(() -> writeImportantData());

// Nếu ứng dụng cần biết dữ liệu được ghi xong,
// phải đợi theo contract, ví dụ stored.join(), hoặc tổ chức
// lifecycle/structured dependencies riêng.
```

Đây là snippet, `writeImportantData` do ứng dụng định nghĩa. `join` dùng để minh họa điểm đồng bộ tại ranh giới; không nên gọi `join` trong mọi request handler nonblocking.

`awaitQuiescence(timeout, unit)` là phương thức chờ/giúp thực thi cho pool tới khi **quiescent**; với common pool đang được **cả JVM chia sẻ**, đây **không phải cách đáng tin để đợi riêng những task thuộc service của bạn** nếu nơi khác vẫn gửi công việc liên tục. Giữ và đợi **chính các Future/CompletableFuture mà bạn sở hữu** là rõ ngữ nghĩa hơn.

### 13.2. `awaitTermination` của common pool không phải shutdown bình thường

Vì common pool không bị terminate bởi `shutdown` của caller, không dùng `commonPool().awaitTermination(...)` như thể nó sẽ biến common pool thành một executor đã dừng. Những method chờ toàn pool và method chờ một Future là hai cấp trách nhiệm khác nhau.

Nếu app phải hoàn thành công việc trước khi dừng server, dùng cơ chế graceful shutdown của **chính service**, các task handle riêng và timeout phù hợp.

## 14. Chương trình Java 8 hoàn chỉnh: pool chung và pool riêng

Chương trình dưới đây dùng **chỉ API từ Java 8 còn được hỗ trợ** và không thay đổi cấu hình common pool. Nó minh họa:

1. `ForkJoinPool.commonPool()` là **cùng một đối tượng** qua nhiều lời gọi.
2. Root `RecursiveTask` chạy qua common pool và qua một custom pool.
3. `CompletableFuture.supplyAsync` không truyền executor có đường async mặc định; chỉ kiểm tra **giá trị**, không kiểm tra worker name.
4. Parallel stream cho kết quả reduction xác định.
5. `completedFuture` có kết quả ngay, không cần scheduling.
6. `supplyAsync`/`runAsync` có executor tường minh chạy trên resource riêng.
7. Shutdown đúng custom pool và blocking executor, giữ common pool hoạt động.

Tạo file **CommonPoolSharedDemo.java**:

```java
import java.util.Arrays;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveTask;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class CommonPoolSharedDemo {
    static final class RangeSum extends RecursiveTask<Integer> {
        private final int from;
        private final int toExclusive;

        RangeSum(int from, int toExclusive) {
            this.from = from;
            this.toExclusive = toExclusive;
        }

        @Override
        protected Integer compute() {
            if (toExclusive - from <= 3) {
                int total = 0;
                for (int i = from; i < toExclusive; i++) {
                    total += i;
                }
                return total;
            }
            int middle = (from + toExclusive) / 2;
            RangeSum left = new RangeSum(from, middle);
            RangeSum right = new RangeSum(middle, toExclusive);
            left.fork();
            int rightResult = right.compute();
            return left.join() + rightResult;
        }
    }

    public static void main(String[] args) throws Exception {
        ForkJoinPool common = ForkJoinPool.commonPool();
        System.out.println("Common instance reused: " +
            (common == ForkJoinPool.commonPool()));
        System.out.println("Shared pool sum 1..10: " +
            common.invoke(new RangeSum(1, 11)));

        CompletableFuture<Integer> defaultAsync =
            CompletableFuture.supplyAsync(() -> 21 * 2);
        System.out.println("Default async result: " +
            defaultAsync.join());

        List<Integer> numbers = Arrays.asList(1, 2, 3, 4, 5);
        System.out.println("Parallel stream sum: " +
            numbers.parallelStream().mapToInt(Integer::intValue).sum());

        CompletableFuture<Integer> immediate =
            CompletableFuture.completedFuture(99);
        System.out.println("CompletedFuture done: " +
            immediate.isDone());
        System.out.println("CompletedFuture value: " +
            immediate.join());

        ForkJoinPool privatePool = new ForkJoinPool(2);
        ExecutorService blockingPool = Executors.newFixedThreadPool(2);
        try {
            System.out.println("Private pool separate: " +
                (privatePool != common));
            System.out.println("Private fork/join sum 1..8: " +
                privatePool.invoke(new RangeSum(1, 9)));

            CompletableFuture<String> privateAsync =
                CompletableFuture.supplyAsync(
                    () -> "CPU_OK", privatePool);
            CompletableFuture<String> isolatedBlocking =
                CompletableFuture.supplyAsync(
                    () -> "IO_OK", blockingPool);

            System.out.println("Private async result: " +
                privateAsync.join());
            System.out.println("Explicit blocking pool result: " +
                isolatedBlocking.join());

            AtomicInteger invocations = new AtomicInteger();
            CompletableFuture<Void> signal =
                CompletableFuture.runAsync(
                    invocations::incrementAndGet, blockingPool);
            signal.join();
            System.out.println("Explicit runAsync count: " +
                invocations.get());
        } finally {
            privatePool.shutdown();
            blockingPool.shutdown();
        }
        System.out.println("Private pool shutdown: " +
            privatePool.isShutdown());
        System.out.println("Blocking pool shutdown: " +
            blockingPool.isShutdown());
        System.out.println("Common still handles tasks: " +
            common.submit(() -> 7).get(5, TimeUnit.SECONDS));
    }
}
```

Biên dịch và chạy với JDK hỗ trợ `--release`:

```bash
javac --release 8 -encoding UTF-8 CommonPoolSharedDemo.java
java CommonPoolSharedDemo
```

Nếu biên dịch **trực tiếp trên JDK 8**, bỏ `--release 8` khỏi lệnh `javac`. **Stdout chính xác:**

```text
Common instance reused: true
Shared pool sum 1..10: 55
Default async result: 42
Parallel stream sum: 15
CompletedFuture done: true
CompletedFuture value: 99
Private pool separate: true
Private fork/join sum 1..8: 36
Private async result: CPU_OK
Explicit blocking pool result: IO_OK
Explicit runAsync count: 1
Private pool shutdown: true
Blocking pool shutdown: true
Common still handles tasks: 7
```

### 14.1. Giải thích vì sao output không phụ thuộc CPU count

- `commonPool()` là pool chung; hai lời gọi trả cùng object. Chúng ta **không in** `getParallelism` vì thông số phụ thuộc máy/JDK.
- `RangeSum(1,11)` tính các số 1 đến 10 bằng fork/join, cho đúng `55`. Pool riêng tính 1 đến 8 được `36`. Không giả định các task được chạy theo một thứ tự cụ thể.
- `supplyAsync(() -> 21*2)` cho 42 bất kể worker nào thực hiện. Không in thread ID/name vì trong cấu hình common parallelism thấp, CompletableFuture có thể dùng executor fallback.
- Parallel stream giảm `1+2+3+4+5` thành 15 mà không phụ thuộc thứ tự xử lý các phần tử.
- `completedFuture(99)` đã xong ngay; `join` lấy 99 mà không cần producer thread.
- `privatePool` là đối tượng khác `common`. `privateAsync` và `isolatedBlocking` truyền rõ executor nên có chính sách tài nguyên tách khỏi common.
- `runAsync` tăng `AtomicInteger` một lần; `signal.join()` bảo đảm in sau completion, không cần sleep.
- Pool riêng và blocking pool được đóng trong `finally`, nhưng common pool **không bị shutdown**. Cuối cùng common vẫn chạy được một task mới và trả 7.

**Đây là minh họa cơ chế, không phải benchmark**. Không đưa ra con số speedup nếu không có dữ liệu đo tin cậy.

## 15. Quan sát common pool trong production

Những phương thức hữu ích của `ForkJoinPool`:

| Phương thức | Diễn giải | Cảnh báo |
| --- | --- | --- |
| `getCommonPoolParallelism()` | Mức parallelism mục tiêu của common pool | Phụ thuộc cấu hình và JDK |
| `getParallelism()` | Mức song song mục tiêu của pool | Không phải số task tối đa tuyệt đối |
| `getPoolSize()` | Số worker đang thuộc pool | Có thể thay đổi |
| `getActiveThreadCount()` | Số thread hoạt động ước lượng | Chỉ là phép lấy mẫu |
| `getRunningThreadCount()` | Worker đang chạy task và không bị chặn theo định nghĩa API | Không bao quát mọi kiểu chờ tùy implementation |
| `getQueuedTaskCount()` | Ước lượng số task trong các queue của worker | Không thay thế `getQueuedSubmissionCount()` |
| `getQueuedSubmissionCount()` | Ước lượng submissions chưa thực thi | Giá trị thay đổi dưới tải |
| `getStealCount()` | Ước lượng số task đã bị steal | Không phải chỉ số chất lượng riêng lẻ |
| `isQuiescent()` | Pool hiện không có task đang hoạt động theo nghĩa API | Không phải điều kiện kết thúc riêng service |
| `toString()` | Tóm tắt trạng thái cho debug | Không parse format thành contract ổn định |

```java
ForkJoinPool common = ForkJoinPool.commonPool();

long queuedTasks = common.getQueuedTaskCount();
long queuedSubmissions = common.getQueuedSubmissionCount();
int activeThreads = common.getActiveThreadCount();
long stolen = common.getStealCount();
```

Đây là snippet chỉ **lấy mẫu**, không nên dùng `queuedTasks == 0` làm một rào đồng bộ cho tính đúng nghiệp vụ. Trong lúc gọi từng getter, pool có thể đã thay đổi.

### 15.1. Đo điều quan trọng thay vì đo chỉ số đẹp

Để biết common pool có quá tải hay không, theo dõi kết hợp:

- **Latency** của task, đặc biệt p95/p99.
- Thời gian queue/wait trước khi bắt đầu chạy, nếu hạ tầng cho phép đo.
- Tỷ lệ và thời gian **blocking** (I/O, lock, latch, join).
- CPU saturation, GC, memory, số thread.
- Active/running/queued submissions và steal rate trên cửa sổ thời gian.
- Trạng thái của **tài nguyên ngoài** (DB connection pool, HTTP rate limit).

Một `getStealCount` tăng không có nghĩa lỗi: work-stealing vốn là cơ chế bình thường. Một `getQueuedTaskCount` bằng 0 cũng không chứng minh mọi thứ đã xong, vì task có thể đang chạy hoặc caller vẫn chuẩn bị submit.

### 15.2. Thread dumps và JFR

Khi nghi ngờ starvation, dùng thread dump và Java Flight Recorder (nếu JDK/triển khai hỗ trợ) để kiểm tra worker đang **RUNNABLE**, **WAITING**, **BLOCKED** hay chờ I/O. Xem stack traces, queue/backlog, critical sections và đường gọi tác vụ, thay vì đoán thủ phạm từ thread name.

Đừng log toàn bộ dữ liệu request hoặc các object nhạy cảm chỉ để phân tích thread pool; dùng correlation ID và metadata an toàn.

## 16. Các lỗi thiết kế thường gặp

### 16.1. Dùng common pool cho mọi tác vụ I/O blocking

**Sai:** đưa hàng nghìn JDBC calls đang chờ mạng vào `supplyAsync` mặc định và cho rằng runtime tự tạo vô số worker.  
**Đúng:** dùng I/O executor/client async phù hợp, giới hạn concurrent requests và có timeout ở tầng I/O.

### 16.2. Đặt `parallel()` rồi cho rằng kết quả sẽ nhanh

**Sai:** đổi mọi `stream()` thành `parallelStream()` mà không đo.  
**Đúng:** lựa chọn theo khối lượng dữ liệu, chi phí từng phần tử, tính độc lập, overhead split/merge và contention.

### 16.3. Phụ thuộc số core hoặc tên thread trong test

**Sai:** assert `getCommonPoolParallelism() == 7` hoặc tên worker luôn có một chuỗi nhất định.  
**Đúng:** assert **kết quả và contract**, không phụ thuộc môi trường.

### 16.4. Tự gọi `shutdown()` trên common pool trong một module

**Sai:** coi shared executor là tài sản private của component.  
**Đúng:** không đóng common pool; chỉ shutdown executor có owner rõ do service tự tạo.

### 16.5. Tạo custom pool cho mỗi request

**Sai:** mỗi request mới tạo `ForkJoinPool(16)` và quên cleanup.  
**Đúng:** tái sử dụng pool được quản lý cấp service, sizing và admission control.

### 16.6. Dùng custom ForkJoinPool nhưng không quản lý vòng đời

**Sai:** tạo pool riêng rồi để worker/task tồn tại không kiểm soát.  
**Đúng:** graceful shutdown có timeout, xử lý cancel/interrupt theo contract.

### 16.7. Cho rằng custom pool cô lập hoàn toàn CPU

**Sai:** hai pool cùng JVM nhưng "không cạnh tranh CPU".  
**Đúng:** tách queue/worker chỉ giảm một số ảnh hưởng scheduling; CPU/memory toàn máy vẫn được chia sẻ.

### 16.8. Dùng `Future.get`/`join` trong một vòng chờ lồng nhau trên pool nhỏ

**Sai:** task A block để chờ task B mà chỉ A có thể kích hoạt B, hoặc B cần một tài nguyên A đang giữ.  
**Đúng:** biểu diễn dependency có cấu trúc, tránh vòng chờ và dùng async composition khi thích hợp.

### 16.9. Tưởng `ManagedBlocker` bảo đảm có thread thay thế

**Sai:** mọi blocking I/O đều được bù thread chính xác và vô hạn.  
**Đúng:** nó là tín hiệu để pool **có thể** điều chỉnh, phụ thuộc giới hạn và tình huống.

### 16.10. Sử dụng `ThreadLocal` như một request context tự truyền qua pool

**Sai:** caller set ThreadLocal, sau đó lambda của `supplyAsync` chắc chắn thấy giá trị đó.  
**Đúng:** truyền context tường minh hoặc dùng cơ chế propagation của framework; dọn ThreadLocal trên worker khi dùng.

### 16.11. Không quản lý side effects trong parallel stream

**Sai:** nhiều task cùng `list.add(x)` vào một `ArrayList` không đồng bộ.  
**Đúng:** dùng reduction/collector phù hợp, tránh mutable shared state không được bảo vệ.

### 16.12. Nhầm pool song song với transaction

**Sai:** một `join` trả về nghĩa mọi email/DB commit đã đúng một lần xuyên hệ thống.  
**Đúng:** Fork/Join chỉ quản lý task completion; idempotency/transaction nằm ở lớp nghiệp vụ.

### 16.13. Mong `commonPool().awaitQuiescence` đợi riêng workflow của mình

**Sai:** toàn pool được chia sẻ nên các task từ nơi khác có thể làm điều kiện quiescence không đạt, hoặc service chưa biểu diễn dependency riêng.  
**Đúng:** giữ Future/CompletionStage của workflow và chờ **chính kết quả của workflow đó**.

### 16.14. Dùng `completedFuture` mà vẫn submit task nền để bọc giá trị

**Sai:** đã có cache hit nhưng `supplyAsync(() -> cached)` chỉ để tạo một Future.  
**Đúng:** `CompletableFuture.completedFuture(cached)` tránh scheduling không cần thiết.

### 16.15. Đổi system property ở runtime rồi tưởng common pool đổi ngay

**Sai:** `System.setProperty("...common.parallelism","4")` sau khi pool đã khởi tạo, rồi kỳ vọng target được cập nhật tự động.  
**Đúng:** cấu hình theo startup và phiên bản JDK; với custom pool, dùng API quản lý thích hợp theo đúng version.

### 16.16. Hiểu `parallelism` là "số thread tối đa của mọi tình huống"

**Sai:** số target luôn bằng số worker thực tế và worker không bao giờ thay đổi.  
**Đúng:** đó là mục tiêu scheduling, còn trạng thái pool/compensation phụ thuộc JDK và workload.

### 16.17. Dùng `Thread.sleep` thay kiểm thử đồng bộ

**Sai:** test dùng sleep 50ms rồi giả định task chắc chắn đã chạy.  
**Đúng:** dùng `Future.get(timeout,unit)`, `CountDownLatch`, `Phaser` và asserts dựa trên completion; không dựa vào timing ngẫu nhiên.

### 16.18. Chia task quá nhỏ

**Sai:** mỗi lần cộng một số tạo một `RecursiveTask` riêng, overhead task lớn hơn tính toán.  
**Đúng:** chọn threshold đủ lớn và chỉ chia khi có lượng công việc thực cần thiết.

## 17. Thiết kế tình huống thực tế

### 17.1. Service tính báo cáo CPU nặng cạnh API cần phản hồi nhanh

**Vấn đề:** module báo cáo dùng `parallelStream` phân tích một lượng dữ liệu lớn; API khác sử dụng `CompletableFuture.supplyAsync` không executor. Cả hai có thể tranh common pool, khiến p99 latency tăng trong giờ cao điểm.

**Giải pháp khả thi:** tách workload phân tích CPU nặng sang **custom ForkJoinPool** hoặc worker service riêng với concurrency limit, để đường API quan trọng không phụ thuộc trực tiếp vào backlog đó. Cân nhắc dùng custom `RecursiveTask`/explicit `Executor` thay vì giả định việc chạy một `parallelStream` bên trong custom worker luôn sẽ cô lập toàn bộ task.

### 17.2. Pipeline gọi nhiều endpoint mạng

**Vấn đề:** mỗi request gọi nhiều endpoint bằng `supplyAsync` mặc định, nhưng bên trong lambda là một HTTP client **blocking**. Khi gọi đông, worker chung bị giữ lâu.

**Giải pháp:** dùng client async/nonblocking thực sự khi có thể, hoặc một **executor riêng cho blocking I/O** với giới hạn đồng thời và timeout. Tách logic parse/aggregate CPU khỏi chờ I/O. Đừng dùng pool CPU như resource manager của hàng nghìn socket.

### 17.3. Ứng dụng CLI chạy xong main nhưng còn async task

**Vấn đề:** CLI gọi `CompletableFuture.runAsync` rồi thoát `main`, tưởng daemon workers sẽ tự giúp hoàn tất file export.

**Giải pháp:** giữ future và `join()/get()` trước khi ứng dụng đóng, hoặc thiết kế shutdown lifecycle. Lỗi của future phải được xử lý/log có chủ đích; không chỉ chờ rồi bỏ qua exceptional completion.

### 17.4. Thư viện muốn giữ lợi ích từ common pool

Không phải lúc nào cũng cần pool riêng. Với tác vụ tính toán ngắn, ít blocking và không có SLA cô lập chặt, `commonPool` giúp giảm chi phí tạo/đóng executor và tận dụng worker đang có. Việc chọn riêng/chung phải dựa trên **số liệu tải và yêu cầu vận hành**, không phải một quy tắc "common pool luôn xấu".

## 18. Checklist trước khi dùng common pool trong production

- [ ] Công việc là **CPU-bound, có thể chia nhỏ**, hay chủ yếu chờ I/O?
- [ ] Có bao nhiêu module/framework khác đang sử dụng common pool?
- [ ] Có tác vụ nào giữ worker lâu, ngủ, chờ latch, JDBC hoặc network?
- [ ] Có nơi nào gọi `CompletableFuture.*Async` mà không truyền executor?
- [ ] Có pipeline `parallelStream()` nào dùng side effect hoặc state không thread-safe?
- [ ] Thời gian chạy từng task có đủ lớn để bù chi phí fork/merge?
- [ ] Task có vòng dependency `join/get` hoặc cần worker khác cùng pool?
- [ ] Có timeout của công việc thật và cleanup tài nguyên ngoài?
- [ ] Có executor private được tạo theo **vòng đời service**, không phải mỗi request?
- [ ] Pool private được shutdown có timeout và chính sách hủy rõ?
- [ ] Không gọi `shutdown`/`shutdownNow` trên `commonPool`?
- [ ] ThreadLocal/MDC/security context có cơ chế truyền an toàn và cleanup?
- [ ] Có đo p95/p99 latency, queued submissions, CPU, GC và số I/O chờ?
- [ ] Unit test không phụ thuộc thứ tự scheduling, core count hoặc tên thread?
- [ ] Đã phân biệt mức version Java 8 với tính năng async/virtual threads mới hơn?

## 19. Câu hỏi tự luyện và đáp án

**1. `ForkJoinPool.commonPool()` tạo pool mới ở mỗi lần gọi không?**  
Không. Đây là một common pool được chia sẻ trong JVM.

**2. Dùng `commonPool()` có bảo đảm một thread riêng cho request không?**  
Không. Worker/CPU/queues là tài nguyên chung, không có quyền sở hữu per request.

**3. Tác vụ `RecursiveTask` phù hợp workload thế nào?**  
Công việc có thể chia nhỏ thành các phần độc lập, tính rồi ghép kết quả.

**4. `fork` khác `join` ra sao?**  
`fork` cho phép subtask được lên lịch chạy; `join` chờ và lấy kết quả subtask.

**5. `parallelStream()` có luôn nhanh hơn `stream()` không?**  
Không. Overhead, dữ liệu, ordering và contention quyết định hiệu năng.

**6. `CompletableFuture.supplyAsync(supplier)` luôn tạo một thread mới không?**  
Không. Thường dùng common pool trên Java 8, có fallback executor trong một số cấu hình parallelism thấp.

**7. Làm sao chọn executor rõ ràng cho CompletableFuture?**  
Dùng overload `supplyAsync(supplier, executor)` hoặc `runAsync(runnable, executor)`.

**8. Vì sao không nên gửi hàng nghìn JDBC blocking calls lên common pool?**  
Chúng giữ worker đang chờ I/O, có thể tăng backlog và starvation cho tác vụ khác.

**9. `ManagedBlocker` có tự tạo vô hạn worker mới không?**  
Không. Nó giúp pool nhận biết blocking và có thể bù worker theo chính sách/giới hạn.

**10. Có nên gọi `commonPool().shutdown()` khi module kết thúc không?**  
Không. Common pool thuộc runtime, không có owner riêng; Javadoc nói shutdown không làm thay đổi run state của nó.

**11. `new ForkJoinPool(4)` có bảo đảm chỉ dùng bốn core CPU riêng không?**  
Không. Nó đặt mức parallelism mục tiêu cho pool riêng, nhưng CPU vật lý vẫn chia sẻ với các thread/pool khác.

**12. `awaitQuiescence` trên common pool có phải wait chỉ cho task của tôi không?**  
Không. Nó quan sát/chờ tính quiescence của toàn pool chung.

**13. Nếu `completedFuture(10)` có sẵn kết quả, có cần `supplyAsync(() -> 10)` không?**  
Không; factory hoàn thành sẵn tránh scheduling.

**14. `ThreadLocal` của thread HTTP request có tự được truyền sang common worker không?**  
Không bảo đảm; cần propagation tường minh hoặc cơ chế được framework hỗ trợ.

**15. Vì sao không assert tên worker trong unit test?**  
Tên và nơi chạy task phụ thuộc môi trường/JDK, không phải contract kết quả nghiệp vụ.

**16. Khi nào nên tạo custom pool?**  
Khi workload CPU song song đủ lớn, cần phân bổ resource riêng, SLA/observability hoặc tránh tranh chấp common pool; vẫn phải quản lý vòng đời.

**17. `newFixedThreadPool(4)` có giới hạn backlog là bốn task không?**  
Không. Nó giới hạn worker đang chạy nhưng queue của factory này có thể tăng nếu gửi quá nhiều task.

**18. Tại sao CLI cần chờ future trước khi thoát?**  
Các worker daemon/common pool không bảo đảm async job vẫn được hoàn thành sau khi JVM kết thúc.

**19. Tác vụ parallel stream có thể chạy trên thread gọi terminal operation không?**  
Có thể; đừng giả định mọi lambda luôn trên common worker.

**20. Một module đổi cấu hình common pool có ảnh hưởng các module khác không?**  
Có thể. Đây là cấu hình **mang tính JVM**, cần đánh giá trên toàn ứng dụng và theo version runtime.

## 20. Nguồn API chính thức và kiến thức còn áp dụng

Tài liệu dưới đây là API còn được duy trì. Bài phân biệt rõ những kiến thức Java 8 tương thích với API của các JDK hiện đại, không sử dụng cơ chế/thuật toán ForkJoin đã legacy.

- [`ForkJoinPool` — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ForkJoinPool.html): commonPool, work-stealing, shutdown của shared pool, ManagedBlocker, cấu hình, giám sát và lifecycle.
- [`ForkJoinPool` — Java 8](https://docs.oracle.com/javase/8/docs/api/java/util/concurrent/ForkJoinPool.html): đối chiếu API Java 8, common.parallelism và shared pool.
- [`ForkJoinTask` — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ForkJoinTask.html): `fork`, `join` và các quy tắc thực thi task.
- [`RecursiveTask` — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/RecursiveTask.html): mẫu chia nhỏ tác vụ có kết quả.
- [`CompletableFuture` — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/CompletableFuture.html): `supplyAsync`, `runAsync`, async continuations, executor mặc định và overload nhận executor.
- [`java.util.stream` — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/package-summary.html): stream song song, pipeline, ordering và reduction.
- [`ExecutorService` — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ExecutorService.html): vòng đời executor, shutdown/awaitTermination và quản lý tài nguyên.
- [`CountDownLatch` — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/CountDownLatch.html): kiểm thử task concurrency theo mốc phối hợp thay vì sleep.
- [JMH — OpenJDK Microbenchmark Harness](https://openjdk.org/projects/code-tools/jmh/): benchmark công việc Java có warm-up/forks/measurement.

**Tóm lại:** `commonPool()` giúp dùng tài nguyên đồng thời hiệu quả khi các tác vụ ngắn, có thể chia và không blocking kéo dài. Vì pool này **được chia sẻ**, phải quản lý tải và tác động lẫn nhau của các module; nếu workload cần cô lập hoặc chờ I/O, chọn executor riêng phù hợp và quản lý vòng đời. Đây là các nguyên tắc vẫn có giá trị trên Java hiện đại.
