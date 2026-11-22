# Java 7 — Fork/Join: ForkJoinPool và cơ chế đánh cắp tác vụ

## 1. Học xong bài này, bạn sẽ hiểu gì?

`ForkJoinPool` thuộc `java.util.concurrent`, được giới thiệu trong Java 7 và **vẫn là một cơ chế xử lý song song hiện hành trên Java 17+**. Điểm đặc biệt của nó là *work-stealing*: khi một worker hết việc, nó có thể tìm và lấy việc từ hàng đợi tác vụ của worker khác, nhờ đó cân bằng tải linh hoạt cho những phép tính có thể chia nhỏ.

Bài học tập trung vào chính `ForkJoinPool` và cơ chế đánh cắp tác vụ; bạn sẽ:

1. Nêu được vấn đề mà work-stealing giải quyết và phân biệt **thread**, **task**, **worker**, **pool**, **parallelism**.
2. Phân biệt công việc **CPU-bound có thể phân chia** với I/O hoặc tác vụ chặn lâu không thích hợp.
3. Hiểu hàng đợi cục bộ của worker, hành vi kiểu LIFO khi fork/join mặc định, và cách worker khác *steal* tác vụ.
4. Trình bày quy trình **fork một nhánh, tính nhánh còn lại, rồi join** thay vì tạo vô hạn threads.
5. Sử dụng `ForkJoinPool`, `ForkJoinTask`, `RecursiveTask<V>`, `RecursiveAction`.
6. Sử dụng `invoke`, `submit`, `execute`, `fork`, `join` đúng ngữ cảnh.
7. Phân biệt `join()` với `Future.get()` về lỗi, interrupt và timeout.
8. Biết chọn **ngưỡng chia nhỏ (threshold/granularity)** dựa trên chi phí tính toán và benchmarking.
9. Phân biệt pool riêng với `ForkJoinPool.commonPool()`, lifecycle và tác động khi dùng chung với parallel streams/`CompletableFuture`.
10. Hiểu `asyncMode=true` là **lập lịch FIFO cục bộ cho forked tasks kiểu event không bao giờ join**, không phải “bật async cho toàn bộ Java”.
11. Đọc các chỉ số `getStealCount()`, `getQueuedTaskCount()`, `getQueuedSubmissionCount()` và biết chúng là **ước lượng**, không dùng làm assertion số steals cố định.
12. Hiểu hệ quả khi tác vụ chặn I/O/synchronization và vai trò giới hạn của `ForkJoinPool.ManagedBlocker`.
13. Quản lý exception, cancellation, shutdown, tính đúng dữ liệu và memory visibility.
14. Chạy các chương trình Java 17+ và đối chiếu stdout đã được kiểm thử.

**Chủ đề cha:** Fork/Join. **Đề bài trực tiếp:** ForkJoinPool và cơ chế đánh cắp tác vụ. Toàn bộ API chính vẫn còn dùng được trên Java hiện đại; ví dụ Java 17 không khuyến khích API lỗi thời.

## 2. Vì sao Fork/Join tồn tại?

Giả sử bạn cần tính tổng một mảng có 10 triệu số nguyên, phân tích hàng triệu pixel, tìm kiếm theo cấu trúc cây hoặc thực hiện phép biến đổi trên các vùng dữ liệu **độc lập**.

Cách tuần tự:

```text
Một thread:
  [toàn bộ dữ liệu] ----------------> [kết quả]
```

Cách chia-để-trị:

```text
                    [mảng ban đầu]
                   /               \
             [nửa trái]          [nửa phải]
             /       \           /        \
         [khối A] [khối B]   [khối C]   [khối D]
             \       /           \        /
              [tổng trái]       [tổng phải]
                   \               /
                    [tổng cuối]
```

Với Fork/Join, **không tạo một hệ điều hành thread mới cho từng khối**. Các khối là `ForkJoinTask` nhẹ, được xử lý bằng số lượng workers được điều phối trong một `ForkJoinPool`.

### 2.1. Ba điều kiện làm mô hình phù hợp

- **Có thể phân chia:** một bài toán lớn thành nhiều bài toán con tương đối độc lập.
- **Có điểm dừng:** khi kích thước dưới ngưỡng, tính tuần tự thay vì fork thêm.
- **Có phép kết hợp hợp lệ:** có thể kết hợp các kết quả từ những vùng độc lập thành kết quả cuối.

Một tác vụ không có khả năng phân chia hoặc mất nhiều thời gian đợi mạng/đĩa/DB chưa chắc hưởng lợi từ ForkJoinPool.

### 2.2. Khác concurrency và parallelism

**Concurrency:** nhiều công việc đang tồn tại, tiến triển xen kẽ; không nhất thiết thực thi cùng lúc.

**Parallelism:** nhiều phần tính toán đang thực thi trên các CPU cores ở cùng thời điểm.

ForkJoinPool có cơ chế concurrency/scheduling giúp tận dụng parallelism khi điều kiện cho phép. Kết quả có thể vẫn đúng và hoạt động trên máy chỉ có một core, nhưng không vì vậy mà luôn nhanh hơn tuần tự.

## 3. Mô hình của ForkJoinPool

`ForkJoinPool` là một `ExecutorService` chuyên quản lý các `ForkJoinTask`. Các thành phần:

| Thành phần | Vai trò |
| --- | --- |
| `ForkJoinPool` | Nhận submissions, quản lý workers, scheduling và metrics |
| `ForkJoinWorkerThread` | Worker thread thực thi tasks |
| `ForkJoinTask<V>` | Task nhẹ, có result/lifecycle, hỗ trợ fork/join |
| `RecursiveTask<V>` | Task đệ quy **có giá trị trả về** |
| `RecursiveAction` | Task đệ quy **không trả về kết quả** |
| `CountedCompleter<T>` | Cơ chế hoàn tất phụ thuộc nhiều tác vụ, thích hợp mẫu nâng cao |
| `commonPool()` | Pool chia sẻ toàn JVM theo cấu hình runtime |
| `parallelism` | Mức song song mục tiêu, **không đơn thuần là task count** |
| `getStealCount()` | Số lượng tác vụ do worker khác thực thi (ước lượng) |

**Task ≠ thread.** Có thể có hàng chục nghìn tasks nhưng chỉ vài workers. Công việc được chia và lịch chạy phụ thuộc pool, khả năng CPU, blocking và runtime.

### 3.1. Pool không cam kết tạo đúng N threads mọi thời điểm

`new ForkJoinPool(4)` đặt **target parallelism=4**. Điều này không có nghĩa cứ tạo đúng 4 threads ngay lập tức; worker threads được tạo, kích hoạt hoặc tạm ngừng dựa trên tình trạng công việc. Trong một số tình huống blocking được quản lý, pool có thể dùng cơ chế compensation; không dựa vào count=4 như một invariant về số threads thực tại mọi thời điểm.

### 3.2. Cơ chế phổ biến: workers tự tìm việc

Một worker có thể:

1. Lấy task ở hàng đợi riêng.
2. Chạy task đó.
3. Khi task `fork` các subtasks, thêm những subtasks vào hàng đợi phù hợp.
4. Nếu worker hết việc, tìm tasks sẵn có từ các workers khác hoặc submissions bên ngoài.
5. Khi chờ một `join`, có thể hỗ trợ thực thi tác vụ để giúp tiến trình chung.
6. Nếu không còn việc sẵn có, đợi cho đến khi có việc mới.

Chính cách worker **lấy công việc từ hàng đợi khác** là *work-stealing*. Nó làm giảm nhu cầu đặt mọi task qua một hàng đợi dùng chung đơn nhất và giúp cân bằng khi các nhánh tính toán có độ dài không đồng đều.

## 4. Work-stealing được hình dung như thế nào?

Giả sử pool có worker W1, W2, W3:

```text
W1: đang tính nhánh trái
    local tasks: [A][B][C]

W2: đang tính nhánh phải
    local tasks: [D]

W3: đã hoàn tất nhánh trước và đang rảnh
    local tasks: []

                 ┌─────────────┐
W3 tìm việc  --->│ W1's deque  │ ---> lấy một task có thể steal
                 └─────────────┘

W1 và W3 có thể xử lý những nhánh khác nhau.
```

Một `fork` thường **không** bắt buộc task chạy ngay trên một thread khác. Nó làm task đủ điều kiện scheduling. Worker tạo task có thể tự chạy task ấy sau này, hoặc một worker khác lấy task khi cần.

### 4.1. Vì sao deque (double-ended queue) hữu ích?

Trong mô hình fork/join mặc định:

- Worker sở hữu hàng đợi thường xử lý công việc cục bộ theo kiểu **LIFO** ở một đầu (gần với call stack, ưu tiên việc mới tạo).
- Worker đi steal thường lấy từ **đầu đối diện** để giảm xung đột và thường lấy nhánh có thể đủ lớn.
- Hành vi của submissions từ bên ngoài và những chế độ scheduling khác không cần giống hệt hàng đợi worker.

Đây là **mô hình tư duy**, không phải API public cho phép bạn quản lý trực tiếp hai đầu deque. Không suy rằng tác vụ A luôn hoàn tất trước B hoặc số steals cố định; concurrent scheduling có tính không xác định.

### 4.2. Vì sao local LIFO thường tốt cho divide-and-conquer?

Khi một task chia làm trái/phải và xử lý một nhánh ngay, nhánh kia được fork, dữ liệu liên quan thường có locality trong cache. Việc xử lý gần cây đệ quy hiện tại giúp giảm overhead so với luôn round-trip mọi task qua queue toàn cục.

Worker rảnh có thể steal một nhánh chưa chạy. Nếu nhánh ấy đủ lớn, nó cũng có thể chia tiếp thành subtasks; do đó work-stealing phù hợp với cây tác vụ mất cân bằng.

### 4.3. Work-stealing không đảm bảo có steal

Nếu chỉ có một worker, hoặc tasks hoàn tất quá nhanh trước khi worker khác rảnh, có thể **không hề phát sinh steals**. Không viết test:

```java
if (pool.getStealCount() == 0)
    throw new AssertionError("ForkJoinPool broken");
```

Đây là **anti-pattern**. Steal count = 0 có thể hoàn toàn bình thường. Thay vì ép số steals, kiểm **kết quả tính toán, data races, trạng thái hoàn tất và hiệu năng đo được**.

## 5. Vòng đời của một ForkJoinTask

Một task được tạo, được submit/fork, thực thi rồi hoàn tất bình thường hoặc bất thường:

```text
NEW TASK
   |
   +-- pool.invoke(task) --------> starts/waits ---> RESULT
   |
   +-- pool.submit(task) --------> Future/ForkJoinTask
   |                                   |
   |                              get()/join()
   |
   +-- task.fork() --------------> queued/eligible
                                       |
                              compute()/run()
                                       |
                           normal / exception / cancellation
```

Các phương thức:

- `fork()`: sắp xếp task để chạy bất đồng bộ trong pool đang chứa phép tính (hoặc common pool khi không ở trong pool).
- `join()`: đợi task hoàn tất rồi trả kết quả hoặc ném unchecked exception.
- `invoke()`: bắt đầu task (có thể ngay trên current thread) và chờ kết quả.
- `invokeAll(...)`: fork/join một tập tasks theo hợp đồng.
- `isDone()`: đã kết thúc theo một cách nào đó, **kể cả cancelled hoặc failed**.
- `isCompletedNormally()`, `isCompletedAbnormally()`, `isCancelled()`: phân biệt outcome.

`ForkJoinTask` có thể chứa các subtasks ở rất nhiều mức. Thiết kế thuật toán phải đảm bảo mỗi task đạt trạng thái hoàn tất hoặc báo lỗi rõ ràng.

### 5.1. Tại sao không fork mọi thứ rồi đợi ngay?

```java
right.fork();
return right.join();
```

Đây là mảnh minh họa kém hiệu quả: fork rồi lập tức join mà không làm việc hữu ích khác có thể tăng scheduling overhead vô ích. Trong một phép chia hai nhánh, thường:

```java
left.fork();
R rightValue = right.compute();
R leftValue  = left.join();
return combine(leftValue, rightValue);
```

Đây là **pseudocode Java-like**: `R` và `combine` là ký hiệu minh họa, không phải class độc lập để biên dịch. Một nhánh fork, nhánh kia được tính ngay, sau đó join kết quả. Điều này tận dụng current worker và tạo cơ hội steal nhánh đã fork.

## 6. RecursiveTask<V> — phép tính có kết quả

`RecursiveTask<V>` kế thừa `ForkJoinTask<V>`. Bạn override:

```java
@Override
protected V compute() {
    // Nếu nhỏ: tính tuần tự rồi return.
    // Nếu lớn: fork, tính nhánh kia, join, kết hợp.
}
```

Đây là **mảnh minh họa generic**, không tự biên dịch như một class. Trong chương trình đầy đủ, `V` được thay bằng một kiểu cụ thể, ví dụ `Long`.

### 6.1. Mẫu thuật toán chia-để-trị đúng

```text
compute(range):
   if range.size <= THRESHOLD:
       return sequential(range)
   mid = middle(range)
   left  = new Task(leftRange)
   right = new Task(rightRange)
   left.fork()
   rightResult = right.compute()
   leftResult  = left.join()
   return combine(leftResult,rightResult)
```

Đặc điểm:

1. **Có threshold** để không sinh tasks vô hạn.
2. Các nhánh làm việc trên **dữ liệu độc lập hoặc chỉ đọc**.
3. `fork()` tạo việc có thể được worker khác xử lý.
4. `join()` lấy kết quả sau khi task hoàn tất, không đọc kết quả chia sẻ trước completion.
5. Hàm kết hợp dùng operation đúng với business semantics.

Đối với sum, hai nửa không chồng lấn và phép cộng kết hợp được khi không có side effects. Đối với floating-point, thứ tự cộng có thể ảnh hưởng sai số (xem phần 25).

## 7. Chương trình A — RecursiveSumDemo.java

Chương trình tính tổng số từ 1 đến 100.000 bằng pool có target parallelism 4. Mỗi leaf xử lý tối đa 1.000 phần tử. Các subtasks được đếm bằng `AtomicInteger` để đối chiếu cấu trúc cây chia đôi; **không** đếm số threads.

```java
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;

public final class RecursiveSumDemo {
    static final class SumTask extends RecursiveTask<Long> {
        static final AtomicInteger created = new AtomicInteger();

        final long[] values;
        final int from, to, threshold;

        SumTask(long[] v, int f, int t, int cutoff) {
            values = v;
            from = f;
            to = t;
            threshold = cutoff;
            created.incrementAndGet();
        }

        protected Long compute() {
            if (to - from <= threshold) {
                long sum = 0;
                for (int i = from; i < to; i++) sum += values[i];
                return sum;
            }

            int mid = (from + to) >>> 1;
            SumTask left = new SumTask(
                    values, from, mid, threshold);
            SumTask right = new SumTask(
                    values, mid, to, threshold);

            left.fork();
            long rightValue = right.compute();
            return rightValue + left.join();
        }
    }

    public static void main(String[] args) throws Exception {
        long[] data = new long[100000];
        for (int i = 0; i < data.length; i++) data[i] = i + 1L;

        ForkJoinPool pool = new ForkJoinPool(4);
        try {
            long actual = pool.invoke(
                    new SumTask(data, 0, data.length, 1000));
            long expected = (long) data.length *
                    (data.length + 1) / 2;

            System.out.println("actual=" + actual);
            System.out.println("expected=" + expected);
            System.out.println("matches=" + (actual == expected));
            System.out.println("tasksCreated=" +
                    SumTask.created.get());
            System.out.println("parallelism=" +
                    pool.getParallelism());
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS))
                throw new IllegalStateException(
                        "pool not terminated");
        }
    }
}
```

Biên dịch/chạy:

```bash
javac --release 17 -encoding UTF-8 RecursiveSumDemo.java
java RecursiveSumDemo
```

**Stdout đã kiểm chứng:**

```text
actual=5000050000
expected=5000050000
matches=true
tasksCreated=255
parallelism=4
```

### 7.1. Vì sao kết quả là 5.000.050.000?

Công thức tổng số từ 1 tới N:

\[
\sum_{i=1}^{N}i = \frac{N(N+1)}{2}
\]

Với N=100.000 → 5.000.050.000, vượt `Integer.MAX_VALUE` nên dùng `long` và `RecursiveTask<Long>`. Trong công thức, cast `(long) data.length` **trước phép nhân** để không overflow kiểu int.

### 7.2. Vì sao có 255 tasks?

Mỗi lần chia đôi cho đến khi leaf ≤ 1.000 phần tử. Với 100.000 phần tử:

- Cần 7 tầng chia: 100.000 / 2⁷ ≈ 781,25.
- Có 128 leaves, mỗi leaf không quá 1.000.
- Cây nhị phân đầy có 127 internal nodes.
- Tổng task objects: 128 + 127 = **255**.

Con số này phản ánh **cách chia cây deterministic của code**, không phải số task bị steal hay số workers đã chạy.

### 7.3. Cơ chế work-stealing đang ở đâu?

`left.fork()` đặt việc trái để pool xử lý. Current worker tiếp tục `right.compute()`. Một worker khác đang rảnh có thể steal phần việc trái; nếu không, current worker vẫn có thể xử lý khi cần `left.join()`. Do đó code đúng **dù có hay không có steal**.

### 7.4. Tại sao task không được ghi vào một shared long sum?

Nếu các leaves cùng ghi `sharedSum += localSum`, sẽ có data race trừ khi đồng bộ. Trong mẫu `RecursiveTask`, mỗi leaf trả result của nó, parent kết hợp sau `join`; không cần shared mutable sum. Đây là ưu điểm về correctness.

### 7.5. Vì sao threshold không thể luôn là 1000?

1.000 chỉ là giá trị minh họa. Với phép tính cực nhẹ, threshold quá nhỏ khiến overhead tạo task/scheduling lớn hơn lợi ích song song. Với phép tính nặng mỗi phần tử, threshold có thể nhỏ hơn. Benchmark với dữ liệu, CPU và JVM thực tế.

## 8. RecursiveAction — tác vụ chia nhỏ không cần return result

`RecursiveAction` là `ForkJoinTask<Void>` theo logic xử lý không trả dữ liệu. Ví dụ transform một mảng **tại các vùng không chồng lấn**.

Các nguyên tắc:

- Mỗi task chỉ sửa vùng của nó.
- Các vùng con không giao nhau để tránh data race.
- Parent chờ `join` trước khi coi toàn bộ biến đổi hoàn thành.
- Đừng đọc mảng đang bị workers sửa nếu chưa có synchronization/completion.
- Dùng threshold để không tạo task cho từng ký tự trong workload lớn.

## 9. Chương trình B — RecursiveActionDemo.java

```java
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;

public final class RecursiveActionDemo {
    static final class UpperAction extends RecursiveAction {
        static final AtomicInteger leaves = new AtomicInteger();

        final char[] arr;
        final int from, to;

        UpperAction(char[] a, int f, int t) {
            arr = a;
            from = f;
            to = t;
        }

        protected void compute() {
            if (to - from <= 2) {
                leaves.incrementAndGet();
                for (int i = from; i < to; i++)
                    arr[i] = Character.toUpperCase(arr[i]);
                return;
            }

            int mid = (from + to) >>> 1;
            UpperAction left = new UpperAction(arr, from, mid);
            UpperAction right = new UpperAction(arr, mid, to);

            left.fork();
            right.compute();
            left.join();
        }
    }

    public static void main(String[] args) throws Exception {
        char[] data = "forkjoin".toCharArray();
        ForkJoinPool pool = new ForkJoinPool(2);

        try {
            pool.invoke(new UpperAction(data, 0, data.length));
            System.out.println("result=" + new String(data));
            System.out.println("leaves=" + UpperAction.leaves.get());
            System.out.println("length=" + data.length);
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS))
                throw new IllegalStateException();
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 RecursiveActionDemo.java
java RecursiveActionDemo
```

**Stdout đã kiểm chứng:**

```text
result=FORKJOIN
leaves=4
length=8
```

### 9.1. Tính đúng nhờ vùng không chồng lấn

Mảng 8 ký tự được chia thành 4 leaves, mỗi leaf 2 ký tự. Task trái và phải nhận ranges `[from,mid)` và `[mid,to)` nên không sửa chung chỉ số. Sau `pool.invoke(...)`, mọi task cần thiết đã hoàn tất; main mới in ra mảng đã đổi chữ hoa.

**Giới hạn ví dụ:** `Character.toUpperCase(char)` minh họa ASCII `forkjoin`. Xử lý case folding Unicode đầy đủ có thể đổi số code points/characters; không dùng transformation đơn giản này như một Unicode text processor tổng quát.

## 10. Fork, compute, join: chọn đúng thứ tự

Mẫu phổ biến:

```java
left.fork();
Result rightResult = right.compute();
Result leftResult = left.join();
return combine(leftResult, rightResult);
```

Đây là pseudocode, `Result`/`combine` cần được định nghĩa trong chương trình thật. Ý tưởng: fork một nhánh, tính nhánh còn lại ở worker hiện tại rồi join.

### 10.1. Vì sao fork cả hai nhánh thường không cần thiết?

```java
left.fork();
right.fork();
return left.join() + right.join();
```

Đây là mảnh minh họa số học. Nó có thể hoạt động, nhưng thêm scheduling overhead cho cả hai nhánh dù worker hiện tại có thể tính trực tiếp một nhánh. Trong divide-and-conquer thường ưu tiên **fork one, compute one, join one**.

### 10.2. Join không phải sleep vô điều kiện

`ForkJoinTask.join()` có thể khiến worker **hỗ trợ thực thi công việc** liên quan thay vì chỉ đợi bị động. Tài liệu JDK thiết kế cơ chế cho việc join các tasks trong pool hiệu quả hơn chờ một `Future.get` bình thường.

Tuy nhiên, không đảm bảo mọi dependency graph sẽ tiến triển. Deadlock vẫn có thể xảy ra nếu thiết kế chờ vòng, giữ lock rồi join task cần lock ấy, hoặc tasks chặn ngoại vi không được quản lý.

### 10.3. Join theo thứ tự hợp lý

Với nhiều subtasks đã fork, Javadoc khuyên join những tasks gần/được fork sau theo thứ tự phù hợp với recursion stack trong một số trường hợp, nhằm tận dụng local queues. Nhưng **đúng đắn của kết quả** phải không phụ thuộc một lịch chạy cụ thể.

## 11. Threshold/granularity là trọng tâm hiệu năng

Một vấn đề thường gặp: “Tôi đã dùng ForkJoinPool nhưng sao chương trình chậm hơn?”

Tổng thời gian không chỉ là tính toán:

```text
Total cost ≈ useful computation
           + task creation
           + scheduling/stealing
           + synchronization/join
           + memory/cache/GC overhead
```

Nếu tạo task cho mỗi phần tử nhỏ nhất, chi phí overhead có thể áp đảo công việc. Ngược lại, nếu threshold quá lớn, ít tasks để chia cho workers và dễ mất cân bằng.

### 11.1. Chọn ngưỡng như thế nào?

- Bắt đầu với **sequential baseline** đáng tin.
- Đo cost xử lý một leaf.
- Chọn threshold tạo đủ tasks để khai thác cores nhưng không tạo số lượng quá lớn.
- Xét độ lệch thời gian giữa các nhánh: các nhánh không đều là nơi work-stealing có ích.
- Dùng data-size và CPU-count khác nhau, warm up/JIT, tránh benchmark một lần rồi kết luận.
- Đo throughput, latency, GC, memory, context switching và số steals *ước lượng*.

**Không có ngưỡng 1.000/10.000 dùng đúng cho mọi bài.** Ngưỡng là quyết định thiết kế/benchmark.

## 12. Chương trình C — ThresholdGranularityDemo.java

Cùng phép tính sum 1..16 nhưng hai thresholds khác nhau: threshold16 tính trực tiếp một leaf; threshold2 tạo 8 leaves. Kết quả phải bằng nhau, còn số lượng tasks khác nhau.

```java
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;

public final class ThresholdGranularityDemo {
    static final class Sum extends RecursiveTask<Integer> {
        final int lo, hi, cutoff;
        final AtomicInteger leaves;

        Sum(int a, int b, int c, AtomicInteger l) {
            lo = a;
            hi = b;
            cutoff = c;
            leaves = l;
        }

        protected Integer compute() {
            if (hi - lo <= cutoff) {
                leaves.incrementAndGet();
                int s = 0;
                for (int i = lo; i < hi; i++) s += i;
                return s;
            }

            int mid = (lo + hi) >>> 1;
            Sum l = new Sum(lo, mid, cutoff, leaves);
            Sum r = new Sum(mid, hi, cutoff, leaves);

            l.fork();
            int result = r.compute();
            return result + l.join();
        }
    }

    public static void main(String[] args) throws Exception {
        ForkJoinPool pool = new ForkJoinPool(2);
        try {
            AtomicInteger coarse = new AtomicInteger();
            AtomicInteger fine = new AtomicInteger();

            int sumCoarse = pool.invoke(
                    new Sum(1, 17, 16, coarse));
            int sumFine = pool.invoke(
                    new Sum(1, 17, 2, fine));

            System.out.println("coarseSum=" + sumCoarse);
            System.out.println("coarseLeaves=" + coarse.get());
            System.out.println("fineSum=" + sumFine);
            System.out.println("fineLeaves=" + fine.get());
            System.out.println("sameResult=" +
                    (sumCoarse == sumFine));
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS))
                throw new IllegalStateException();
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 ThresholdGranularityDemo.java
java ThresholdGranularityDemo
```

**Stdout đã kiểm chứng:**

```text
coarseSum=136
coarseLeaves=1
fineSum=136
fineLeaves=8
sameResult=true
```

### 12.1. Bài học rút ra

Task granularity tác động **số leaves**, do đó thường tác động overhead. Nhưng kết quả đúng vẫn 136. Đừng suy ra “8 leaves nhanh hơn 1 leaf” từ chương trình này; nó **không đo throughput**. Với chỉ 16 số, chạy tuần tự thường đơn giản và thích hợp hơn.

### 12.2. Tránh tạo cây mất kiểm soát

Với một threshold quá nhỏ, số tasks có thể tăng tương ứng `O(N / threshold)`. Ngay cả khi số worker hữu hạn, tasks vẫn tiêu tốn đối tượng, hàng đợi, cache và GC. Phải có base case và không fork những subproblems bé hơn chi phí scheduling có thể chấp nhận.

## 13. Ba API đi vào pool: invoke, submit, execute

| API của ForkJoinPool | Ngữ nghĩa | Khi nên dùng |
| --- | --- | --- |
| `invoke(task)` | Bắt đầu task, **đợi hoàn tất** và trả result hoặc lỗi | Main/entry point muốn kết quả ngay |
| `submit(task)` | Đưa task vào pool, trả `ForkJoinTask`/`Future` để đợi sau | Muốn giữ handle, có thể làm việc khác |
| `execute(task)` | Sắp xếp thực thi, không trả result handle | Fire-and-track qua signal/application state riêng |
| `ForkJoinTask.fork()` | Trong task, sắp xếp subtask để pool xử lý | Chia nhỏ công việc bên trong `compute()` |
| `ForkJoinTask.join()` | Đợi subtask và lấy kết quả | Ghép kết quả các nhánh đã fork |

**Khác biệt ngữ cảnh:** Từ thread bên ngoài pool, thường `pool.invoke/submit/execute`; trong một phép tính fork/join, thường `fork/join`.

### 13.1. Không dùng execute mà quên kết quả/lỗi

`execute(Runnable)` không trả `Future`. Nếu ứng dụng cần biết khi nào xong hoặc có lỗi, dùng `submit`/`invoke` hoặc cơ chế đồng bộ/application result riêng. Tránh “fire-and-forget” trên công việc quan trọng mà không giám sát.

## 14. Chương trình D — PoolExecutionApiDemo.java

```java
import java.util.concurrent.*;

public final class PoolExecutionApiDemo {
    public static void main(String[] args) throws Exception {
        ForkJoinPool pool = new ForkJoinPool(2);
        try {
            RecursiveTask<Integer> task =
                    new RecursiveTask<>() {
                protected Integer compute() {
                    return 20 + 22;
                }
            };

            int invoked = pool.invoke(task);

            Future<String> future =
                    pool.submit(() -> "submitted");

            CountDownLatch finished = new CountDownLatch(1);
            pool.execute(finished::countDown);
            boolean executeDone =
                    finished.await(5, TimeUnit.SECONDS);

            boolean inside = pool.submit(
                    () -> ForkJoinTask.getPool() == pool)
                    .get(5, TimeUnit.SECONDS);

            System.out.println("invokeResult=" + invoked);
            System.out.println("submitResult=" +
                    future.get(5, TimeUnit.SECONDS));
            System.out.println("executeCompleted=" + executeDone);
            System.out.println("insidePool=" + inside);
            System.out.println("mainInsidePool=" +
                    ForkJoinTask.inForkJoinPool());
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS))
                throw new IllegalStateException();
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 PoolExecutionApiDemo.java
java PoolExecutionApiDemo
```

**Stdout đã kiểm chứng:**

```text
invokeResult=42
submitResult=submitted
executeCompleted=true
insidePool=true
mainInsidePool=false
```

### 14.1. Ý nghĩa của inForkJoinPool

`ForkJoinTask.inForkJoinPool()` chỉ ra current thread có phải `ForkJoinWorkerThread` đang thực thi phép tính trong pool hay không. Ở main thread của demo, false; trong callable do pool xử lý, true.

### 14.2. Future từ submit

`submit` có overloads cho `ForkJoinTask`, `Callable`, `Runnable`. Khi cần chờ có timeout hoặc phân biệt `ExecutionException`, dùng `Future.get(timeout,unit)`. Với `ForkJoinTask`, `join` là cơ chế chủ đạo bên trong thuật toán đệ quy.

## 15. Default scheduling và asyncMode

`ForkJoinPool` có constructor:

```java
new ForkJoinPool(
    parallelism,
    ForkJoinPool.defaultForkJoinWorkerThreadFactory,
    null,
    asyncMode);
```

Đây là mảnh minh họa; `parallelism` phải là một số hợp lệ >0, `asyncMode` là Boolean.

`asyncMode=false` (mặc định):
- Scheduling cho forked tasks thường mang tính **local stack / LIFO**.
- Phù hợp kiểu fork → compute → join của divide-and-conquer.

`asyncMode=true`:
- Bật **local FIFO scheduling** cho *forked tasks không bao giờ joined*.
- Được Javadoc mô tả là có thể thích hợp cho **event-style asynchronous tasks**.
- **Không làm pool trở thành nonblocking I/O framework**.
- Không hứa global FIFO giữa mọi worker/submissions, không biến `Future.get()` thành nonblocking.
- Không chọn true chỉ để hy vọng mọi phép tính đệ quy chạy nhanh hơn.

### 15.1. Vì sao không dùng asyncMode làm công tắc hiệu năng tổng quát?

FIFO/LIFO cục bộ có trade-offs về locality, depth-first behavior và latency cho các loại tasks khác nhau. Muốn dùng mode nào phải dựa trên **kiểu workload**, không phải “async nghe hiện đại hơn”.

## 16. Chương trình E — AsyncModeDemo.java

```java
import java.util.concurrent.*;

public final class AsyncModeDemo {
    public static void main(String[] args) throws Exception {
        ForkJoinPool regular = new ForkJoinPool(2);

        ForkJoinPool async = new ForkJoinPool(
            2,
            ForkJoinPool.defaultForkJoinWorkerThreadFactory,
            null,
            true);

        try {
            System.out.println("regularAsyncMode=" +
                    regular.getAsyncMode());
            System.out.println("eventAsyncMode=" +
                    async.getAsyncMode());
            System.out.println("regularParallelism=" +
                    regular.getParallelism());
            System.out.println("eventParallelism=" +
                    async.getParallelism());
            System.out.println("eventResult=" +
                    async.submit(() -> 6 * 7)
                         .get(5, TimeUnit.SECONDS));
        } finally {
            regular.shutdown();
            async.shutdown();
            if (!regular.awaitTermination(5, TimeUnit.SECONDS) ||
                !async.awaitTermination(5, TimeUnit.SECONDS))
                throw new IllegalStateException();
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 AsyncModeDemo.java
java AsyncModeDemo
```

**Stdout đã kiểm chứng:**

```text
regularAsyncMode=false
eventAsyncMode=true
regularParallelism=2
eventParallelism=2
eventResult=42
```

Kết quả `getAsyncMode=true` chỉ xác nhận mode cấu hình, không chứng minh một thứ tự thực thi toàn cục. Không assert “task nào submit trước luôn chạy trước” vì work-stealing và concurrency có thể thay đổi thứ tự completion.

## 17. Metrics: xem work-stealing mà không tự bịa con số

`ForkJoinPool` có các chỉ số:

| Method | Ý nghĩa | Cần lưu ý |
| --- | --- | --- |
| `getParallelism()` | Mức song song mục tiêu | Không phải số threads sống mọi thời điểm |
| `getPoolSize()` | Số worker threads đã bắt đầu và chưa chấm dứt | Thay đổi theo runtime |
| `getActiveThreadCount()` | Ước lượng workers đang thực thi/stealing | Có thể overestimate |
| `getRunningThreadCount()` | Ước lượng workers không bị chặn trong join/managed sync | Có thể overestimate |
| `getStealCount()` | Ước lượng các tasks được worker khác hoàn tất | Có thể thấp hơn thực tế khi pool bận |
| `getQueuedTaskCount()` | Ước lượng tasks trong local worker queues | Không bao gồm pending external submissions |
| `getQueuedSubmissionCount()` | Ước lượng external submissions chưa chạy | Không giống local queued tasks |
| `hasQueuedSubmissions()` | Có external submissions chờ không | Snapshot, có race |
| `isQuiescent()` | Workers hiện có thể idle/không tìm được việc | Có thể chưa phản ánh tức thời |
| `toString()` | Snapshot phục vụ quan sát | Không ổn định để parse như protocol |

### 17.1. Steal count không phải tổng số task objects

Ví dụ một phép tính tạo 255 task objects. Không suy `getStealCount()==255`. Nhiều tasks có thể do chính owner worker thực thi, hoặc do một worker khác steal. Chỉ khi có work-stealing thực sự ở các điều kiện runtime thích hợp, steal count mới tăng.

### 17.2. Tại sao queuedTaskCount khác queuedSubmissionCount?

- **Local queued tasks** là những tasks workers đã fork và đang chờ trong hàng đợi của workers.
- **External submissions** là các tasks được thread ngoài pool submit mà chưa bắt đầu thực thi.

Đếm khác nhau giúp chẩn đoán task granularity và producer pressure, nhưng đây đều là **ước lượng tại thời điểm đọc**, có thể thay đổi ngay sau khi in.

### 17.3. Không dùng metrics làm điều kiện correctness

Một test đúng phải assert kết quả số học, không có data race, mọi tasks cần thiết hoàn tất. Metrics chỉ giúp tuning. Không nên đặt `getStealCount() > 0` làm điều kiện pass trong CI vì scheduling không được hứa.

## 18. Chương trình F — PoolMetricsDemo.java

```java
import java.util.concurrent.*;
import java.util.*;

public final class PoolMetricsDemo {
    static final class Sum extends RecursiveTask<Long> {
        final int from, to;
        final Set<String> seen;

        Sum(int f, int t, Set<String> threads) {
            from = f;
            to = t;
            seen = threads;
        }

        protected Long compute() {
            if (to - from <= 128) {
                seen.add(Thread.currentThread().getName());
                long s = 0;
                for (int i = from; i < to; i++) s += i + 1L;
                return s;
            }

            int mid = (from + to) >>> 1;
            Sum a = new Sum(from, mid, seen);
            Sum b = new Sum(mid, to, seen);

            a.fork();
            long bs = b.compute();
            return bs + a.join();
        }
    }

    public static void main(String[] args) throws Exception {
        ForkJoinPool pool = new ForkJoinPool(4);
        Set<String> seen = ConcurrentHashMap.newKeySet();

        try {
            long result = pool.invoke(new Sum(0, 4096, seen));

            System.out.println("sum=" + result);
            System.out.println("sumCorrect=" +
                    (result == 8390656L));
            System.out.println("observedWorkersPositive=" +
                    (!seen.isEmpty()));
            System.out.println("stealMetricNonnegative=" +
                    (pool.getStealCount() >= 0));
            System.out.println("queuedTasksNonnegative=" +
                    (pool.getQueuedTaskCount() >= 0));
            System.out.println("queuedSubmissionsNonnegative=" +
                    (pool.getQueuedSubmissionCount() >= 0));
            System.out.println("runningCountNonnegative=" +
                    (pool.getRunningThreadCount() >= 0));
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS))
                throw new IllegalStateException();
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 PoolMetricsDemo.java
java PoolMetricsDemo
```

**Stdout đã kiểm chứng:**

```text
sum=8390656
sumCorrect=true
observedWorkersPositive=true
stealMetricNonnegative=true
queuedTasksNonnegative=true
queuedSubmissionsNonnegative=true
runningCountNonnegative=true
```

### 18.1. Vì sao không in con số steal thực tế vào expected output?

Giá trị `getStealCount()` thay đổi giữa các lần chạy, số cores, OS scheduling, JIT, độ dài tasks và pool load. Nếu in một con số cụ thể rồi assert, README sẽ **bịa một guarantee không có trong Java API**.

Thay vào đó, demo chỉ kiểm tính không âm, kết quả sum đúng và ít nhất một worker thực thi leaf task. Trong production có thể log số steal thực tế để quan sát, nhưng không dùng làm golden output.

### 18.2. Pool không nhất thiết dùng đủ bốn workers

`parallelism=4` không ép bốn threads cùng hoạt động nếu workload quá ít hoặc CPU scheduler quyết định khác. Đừng dựa vào tên threads trong `seen` làm thứ tự output hay điều kiện `seen.size()==4`.

## 19. Công việc chặn (blocking) và nguy cơ starvation

`ForkJoinPool` được thiết kế phù hợp nhất với **CPU-bound, có thể chia nhỏ và hạn chế chặn ngoại vi**.

Những tác vụ như:

- Đợi HTTP/DB.
- Đọc file đồng bộ lâu.
- Chờ `Thread.sleep` để “giữ chỗ”.
- Chờ lock/synchronized đang được task khác trong cùng pool nắm.
- Đợi một `CountDownLatch` mà signal chỉ do một task còn đang nằm trong cùng pool thực hiện.

có thể làm cạn khả năng tiến triển nếu nhiều workers bị chặn. Work-stealing **không thể steal một thread đang bị block**; nó chỉ giúp workers đang rảnh tìm được tasks chờ.

### 19.1. Vì sao fork/join đỡ chặn khi join, nhưng không xử lý mọi loại chặn?

Pool biết một số tình huống waiting/join trong fork/join và có thể điều phối để tiếp tục thực thi subtask. Nhưng các thao tác **I/O hoặc synchronization tùy ý** có thể nằm ngoài khả năng phát hiện/bù threads của pool.

Javadoc cảnh báo pool **không bảo đảm luôn giữ đủ workers runnable** khi có uncontrolled blocking. Với tác vụ network/database I/O, thường hợp lý hơn dùng executor/async framework riêng có bounded concurrency và deadline.

## 20. ManagedBlocker: hỗ trợ pool nhận biết đoạn có thể block

`ForkJoinPool.ManagedBlocker` có hai method:

- `isReleasable()`: trả true nếu không cần block nữa; có thể được gọi nhiều lần.
- `block()`: thực sự chờ nếu cần; trả true khi không cần tiếp tục block.

`ForkJoinPool.managedBlock(blocker)` làm pool **có thể** cấp thêm worker tạm để giữ parallelism khi một worker phải block.

**Không có bảo đảm sẽ tạo đúng một worker mới mỗi lần.** Đây là cơ chế giúp pool phản ứng tốt hơn trong một số trường hợp, không thay thế kiến trúc tránh blocking hay biện pháp kiểm soát tải.

### 20.1. Mẫu đúng

```java
ForkJoinPool.managedBlock(new ForkJoinPool.ManagedBlocker() {
    public boolean isReleasable() {
        return conditionAlreadySatisfied();
    }

    public boolean block() throws InterruptedException {
        waitForCondition();
        return true;
    }
});
```

Đây là **pseudocode minh họa**, `conditionAlreadySatisfied` và `waitForCondition` cần được định nghĩa. `isReleasable` phải an toàn khi được hỏi lại nhiều lần. Không tự làm vòng busy-wait chờ network thay cho block có timeout/quy trình phù hợp.

## 21. Chương trình G — ManagedBlockDemo.java

Chương trình có pool một worker, một `CountDownLatch` làm điều kiện chờ. Main thread biết worker đã vào `block()` rồi giải phóng latch. Demo kiểm **managedBlock hoàn tất đúng**, không assert pool luôn cấp worker thứ hai.

```java
import java.util.concurrent.*;

public final class ManagedBlockDemo {
    static final class LatchBlocker
            implements ForkJoinPool.ManagedBlocker {
        final CountDownLatch gate;
        final CountDownLatch entered;

        LatchBlocker(CountDownLatch g, CountDownLatch e) {
            gate = g;
            entered = e;
        }

        public boolean isReleasable() {
            return gate.getCount() == 0;
        }

        public boolean block() throws InterruptedException {
            entered.countDown();
            gate.await();
            return true;
        }
    }

    public static void main(String[] args) throws Exception {
        ForkJoinPool pool = new ForkJoinPool(1);
        CountDownLatch gate = new CountDownLatch(1);
        CountDownLatch entered = new CountDownLatch(1);

        try {
            Future<String> pending = pool.submit(() -> {
                ForkJoinPool.managedBlock(
                        new LatchBlocker(gate, entered));
                return "released";
            });

            boolean enteredBlock =
                    entered.await(5, TimeUnit.SECONDS);
            gate.countDown();
            String result = pending.get(5, TimeUnit.SECONDS);

            System.out.println("enteredBlock=" + enteredBlock);
            System.out.println("result=" + result);
        } finally {
            gate.countDown();
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS))
                throw new IllegalStateException();
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 ManagedBlockDemo.java
java ManagedBlockDemo
```

**Stdout đã kiểm chứng:**

```text
enteredBlock=true
result=released
```

### 21.1. Vì sao latch ở đây không gây deadlock?

Worker vào `managedBlock` rồi signal `entered`. Main thread (bên ngoài pool) chờ signal, sau đó `gate.countDown()` giải phóng worker. Điều kiện giải phóng **không phụ thuộc một task chỉ có thể chạy trên chính worker đang bị block**.

Nếu thay main bằng một task khác nằm trong cùng pool, cần phân tích cẩn thận dependency graph; `ManagedBlocker` có thể giúp compensation nhưng không được dùng để che giấu vòng chờ logic.

### 21.2. Khi nào nên dùng ManagedBlocker?

Một số synchronizers/queues tương thích mô hình này; Java docs đưa ra ví dụ dùng `ReentrantLock` hoặc `BlockingQueue`. Nhưng hãy cân nhắc **executor riêng cho blocking I/O** vì có thể đơn giản hơn và giảm rủi ro cạn resources.

## 22. join() và get(): hoàn tất bất thường

`ForkJoinTask` cũng là `Future`. Tuy vậy:

| Trường hợp | `task.join()` | `task.get()` |
| --- | --- | --- |
| Thành công | Trả kết quả V | Trả V |
| Task ném RuntimeException | Ném lại unchecked exception/Error | Bọc trong `ExecutionException` |
| Task bị cancel | `CancellationException` | `CancellationException` |
| Caller bị interrupt | Không kết thúc chờ bằng `InterruptedException` | `InterruptedException` |
| Timeout | `join` không nhận timeout | `get(timeout,unit)` có timeout |
| Dùng trong recursive compute | Thường phù hợp | Không cần thiết để chờ subtask đơn giản |
| Dùng ở application boundary | Có thể dùng | Hợp đồng Future đôi khi dễ xử lý hơn |

### 22.1. Không lấy isDone làm “thành công”

`isDone()==true` có nghĩa task kết thúc **bất kể** bình thường, exception hay cancellation. Hãy kiểm outcome:

- `isCompletedNormally()`.
- `isCompletedAbnormally()`.
- `isCancelled()`.
- `getException()` khi cần chẩn đoán.

### 22.2. Cancellation không phải bảo đảm interrupt worker

`ForkJoinTask.cancel(boolean mayInterruptIfRunning)` không nên được hiểu như cơ chế bảo đảm ngắt tức thì computation chạy trong pool. Tài liệu mô tả khác với nhiều blocking `FutureTask`: các fork/join tasks không nhất thiết sử dụng interrupts để điều khiển việc thực thi.

Đối với task CPU dài, nếu cần cancellation hợp tác, nên thiết kế flag/token và checkpoints có kiểm soát; không chỉ gọi `cancel(true)` rồi tuyên bố mọi side effects đã dừng.

## 23. Chương trình H — FailureAndCancellationDemo.java

```java
import java.util.concurrent.*;

public final class FailureAndCancellationDemo {
    public static void main(String[] args) throws Exception {
        ForkJoinPool pool = new ForkJoinPool(2);

        try {
            RecursiveTask<Integer> failing =
                    new RecursiveTask<>() {
                protected Integer compute() {
                    throw new IllegalStateException("boom");
                }
            };

            ForkJoinTask<Integer> sent = pool.submit(failing);
            boolean joinThrows = false, getWraps = false;

            try {
                sent.join();
            } catch (IllegalStateException e) {
                joinThrows = true;
            }

            try {
                sent.get();
            } catch (ExecutionException e) {
                getWraps = e.getCause()
                        instanceof IllegalStateException;
            }

            RecursiveTask<Integer> unused =
                    new RecursiveTask<>() {
                protected Integer compute() {
                    return 7;
                }
            };
            unused.cancel(true);
            boolean canceled = unused.isCancelled();

            boolean cancellationJoin = false;
            try {
                unused.join();
            } catch (CancellationException e) {
                cancellationJoin = true;
            }

            System.out.println("joinPropagatedUnchecked=" +
                    joinThrows);
            System.out.println("getWrappedCause=" + getWraps);
            System.out.println("cancelledTaskFlag=" + canceled);
            System.out.println("cancelledJoinThrows=" +
                    cancellationJoin);
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS))
                throw new IllegalStateException();
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 FailureAndCancellationDemo.java
java FailureAndCancellationDemo
```

**Stdout đã kiểm chứng:**

```text
joinPropagatedUnchecked=true
getWrappedCause=true
cancelledTaskFlag=true
cancelledJoinThrows=true
```

### 23.1. Vì sao cả join và get đều nhìn thấy lỗi?

Task đã được `submit` và hoàn tất bất thường. `join` truyền unchecked failure, trong khi `get` dùng contract của Future với `ExecutionException`. Một task có thể được quan sát outcome bởi cả hai phương thức sau khi đã kết thúc.

### 23.2. Tránh hiểu sai cancel

Task `unused` trong ví dụ **chưa submit vào pool**. Việc `cancel(true)` đặt trạng thái cancelled và `join` ném `CancellationException`; nó không phải test chứng minh một tác vụ CPU đang chạy được ngắt ngay lập tức. Production cần cooperative cancellation nếu business logic yêu cầu.

## 24. commonPool(): pool dùng chung và điểm cần lưu ý

`ForkJoinPool.commonPool()` trả về một **pool chia sẻ**, thường thích hợp cho nhiều tác vụ CPU-bound ngắn không có nhu cầu cách ly đặc biệt.

Đặc tính:

- Có thể dùng bởi ForkJoinTasks được `fork` mà không thuộc một pool cụ thể.
- Có thể được dùng bởi parallel streams và `CompletableFuture` async stages theo cơ chế tương ứng.
- Target parallelism chịu ảnh hưởng CPU count, JVM flags/properties và môi trường runtime.
- Là resource chia sẻ: một library làm tác vụ chặn/nặng có thể ảnh hưởng workload khác.
- Lifecycle của common pool khác private pool; gọi `commonPool.shutdown()` không tạo một shutdown thông thường với việc dừng common pool trước JVM exit.
- Daemon threads có nghĩa main program không nên kết thúc trước khi kết quả bắt buộc hoàn tất.

### 24.1. Có nên luôn dùng commonPool?

**Không.** Nếu ứng dụng có workload được quản lý riêng (CPU budget, isolation, SLA, observability, bảo mật hay cancel/shutdown policy), tạo `ForkJoinPool` riêng hoặc một Executor khác phù hợp có thể tốt hơn.

Đừng tạo một pool riêng cho từng request ngắn rồi không shutdown: đó là resource leak. Cũng không nên để libraries âm thầm gửi hàng triệu tasks CPU lâu vào shared pool nếu cần predictability.

### 24.2. commonPool parallelism không phải hằng số 7 hay CPU-1

Hệ thống có thể khác số cores, container quotas, JVM version và cấu hình. JDK có các system properties `java.util.concurrent.ForkJoinPool.common.parallelism`, `...threadFactory`, `...exceptionHandler`; phần cấu hình common pool cần được thiết lập sớm trước khi pool được tạo, và các thay đổi ảnh hưởng rộng tới JVM.

Tốt nhất **đọc và quan sát** `getCommonPoolParallelism()`, không dựa vào một con số hardcode cho mọi máy.

## 25. Chương trình I — CommonPoolDemo.java

```java
import java.util.concurrent.*;

public final class CommonPoolDemo {
    public static void main(String[] args) throws Exception {
        ForkJoinPool common = ForkJoinPool.commonPool();
        boolean same = common == ForkJoinPool.commonPool();

        boolean runningInside = common.submit(
                () -> ForkJoinTask.getPool() == common)
                .get(5, TimeUnit.SECONDS);

        System.out.println("commonSingleton=" + same);
        System.out.println("positiveParallelism=" +
                (common.getParallelism() >= 1));
        System.out.println("runsInsideCommon=" + runningInside);
        System.out.println("parallelismReported=" +
                (ForkJoinPool.getCommonPoolParallelism() >= 1));
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 CommonPoolDemo.java
java CommonPoolDemo
```

**Stdout đã kiểm chứng:**

```text
commonSingleton=true
positiveParallelism=true
runsInsideCommon=true
parallelismReported=true
```

### 25.1. Vì sao không in chính xác common parallelism?

Con số có thể khác theo machine/JVM properties. Bài kiểm tính chất phù hợp thay vì chốt một output phụ thuộc host.

### 25.2. Vì sao không shutdown commonPool trong ví dụ?

Đây là pool dùng chung. Quản lý lifecycle ở ứng dụng phải biết các thư viện khác có thể đang dùng. Demo chỉ submit một tác vụ và đợi completion; không thay đổi trạng thái của common pool.

## 26. Liên hệ với parallel streams và CompletableFuture

### 26.1. Java parallel streams

`IntStream.range(...).parallel()` hoặc `collection.parallelStream()` có thể dùng cơ chế Fork/Join để chia nhỏ pipeline CPU. Tuy nhiên:

- Không bảo đảm từng phần tử được xử lý trên một worker cụ thể.
- Không nên dùng side effects không đồng bộ hóa bên trong `forEach`.
- Encounter order có thể khác execution order.
- Source/spliterator, stateful operations và workload quyết định hiệu quả.
- Việc dùng common pool cho parallel streams thường gặp; **đừng xem private ForkJoinPool wrapping luôn là API ràng buộc stream execution vào pool ấy ở mọi môi trường**.

Khi cần phân quyền CPU/concurrency chắc chắn, nên benchmark và cân nhắc dùng ForkJoinTask trực tiếp hoặc API hỗ trợ executor tường minh.

### 26.2. CompletableFuture

Với Java 17:

- Các async methods của `CompletableFuture` **không truyền Executor** mặc định dùng `ForkJoinPool.commonPool()` nếu common pool có parallelism ít nhất 2.
- Nếu không đạt mức này, có fallback dùng thread mới mỗi async task theo Javadoc; subclasses có thể override defaultExecutor.
- Truyền `Executor` tường minh là cách rõ ràng để kiểm soát pool, isolation và lifecycle.

```java
CompletableFuture<Integer> result =
    CompletableFuture.supplyAsync(() -> 6 * 7, pool)
        .thenApplyAsync(x -> x + 1, pool);
```

Đây là mảnh minh họa; `pool` phải là Executor đang sống và được quản lý.

## 27. Chương trình J — ExplicitExecutorDemo.java

```java
import java.util.concurrent.*;

public final class ExplicitExecutorDemo {
    public static void main(String[] args) throws Exception {
        ForkJoinPool pool = new ForkJoinPool(2);
        try {
            CompletableFuture<Integer> result =
                CompletableFuture.supplyAsync(() -> 6 * 7, pool)
                    .thenApplyAsync(x -> x + 1, pool);

            System.out.println("pipeline=" +
                    result.get(5, TimeUnit.SECONDS));
            System.out.println("usesCustomPool=" +
                    (pool.getParallelism() == 2));
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS))
                throw new IllegalStateException();
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 ExplicitExecutorDemo.java
java ExplicitExecutorDemo
```

**Stdout đã kiểm chứng:**

```text
pipeline=43
usesCustomPool=true
```

Trong ví dụ, cả hai async stages đều nhận tham số executor `pool`, không phụ thuộc defaults của `CompletableFuture`. Đây là hướng minh bạch khi app muốn workload chạy trên một pool cụ thể.

### 27.1. Có nên dùng FJP cho blocking CompletableFuture stages?

Nếu một stage gửi HTTP request đồng bộ và chờ nhiều giây, việc dùng FJP CPU chung có thể cản trở các stages CPU khác. Với I/O, cân nhắc async API hoặc executor riêng có giới hạn, timeout và backpressure.

## 28. Lifecycle của private pool

Pool riêng cần được quản lý rõ:

```java
ForkJoinPool pool = new ForkJoinPool(4);
try {
    // Gửi tasks, đợi các results quan trọng.
} finally {
    pool.shutdown();
    if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
        // Xử lý timeout/shutdown policy.
    }
}
```

Đây là mảnh minh họa; cần import `ForkJoinPool`, `TimeUnit`, và `awaitTermination` có thể ném `InterruptedException`. Các demo đầy đủ ở trên xử lý `throws Exception` tại main.

### 28.1. shutdown() khác shutdownNow()

- `shutdown()`: không nhận submissions mới; các tasks đã gửi vẫn có cơ hội được chạy.
- `shutdownNow()`: cố gắng dừng/cancel tasks; không bảo đảm mọi tác vụ CPU hiện tại bị ngắt ngay.
- `awaitTermination(timeout,unit)`: đợi pool shutdown xong; nếu timeout, trả false.
- Sau shutdown, submit thêm có thể nhận `RejectedExecutionException`.

**Không xem shutdownNow như rollback** của các side effects đã xảy ra. Kết quả chỉ được công nhận sau khi các tasks quan trọng hoàn tất và data invariants được kiểm.

### 28.2. commonPool có lifecycle riêng

Javadoc nói `shutdown` và `shutdownNow` không tác động đến trạng thái thực thi của common pool theo cách của private pool. Vì đây là shared service, đừng “dọn dẹp” common pool như private pool.

### 28.3. Đừng dựa vào daemon threads khi cần kết quả

Workers là daemon threads; nếu main thread thoát mà không đợi task quan trọng, JVM có thể kết thúc trước khi công việc ứng dụng hoàn tất. Hãy dùng `invoke`/`join`/`get`/completion handling thích hợp.

## 29. Tính đúng dữ liệu và memory visibility

### 29.1. Fork/Join không làm shared mutable state tự thread-safe

Sai:

```java
// Nhiều subtasks cùng làm:
sharedCounter++;
```

Đây là anti-pattern; tăng int/long theo kiểu read-modify-write không có atomicity thích hợp. Work-stealing không đồng bộ hóa thay bạn.

Các cách đúng:

- Trả kết quả theo cây `RecursiveTask<V>` rồi combine sau joins.
- Sử dụng vùng data **không chồng lấn** như RecursiveActionDemo.
- Dùng `AtomicLong`/`LongAdder` khi yêu cầu cập nhật shared counter, nhưng xem contention/semantics.
- Dùng immutable input và tránh side effects không cần thiết.

### 29.2. Đợi completion trước khi đọc kết quả

`ForkJoinTask.join`, `invoke` hoặc các mechanisms Future completion tạo quan hệ đồng bộ hóa cần thiết để caller quan sát kết quả đã được task tính xong, theo hợp đồng Java concurrency. Không tự đọc một mảng đang bị workers sửa trước completion rồi nghĩ cache sẽ tự đồng bộ đúng mọi thời điểm.

### 29.3. Tránh lock + join gây deadlock

Ví dụ worker A giữ lock, fork task B, rồi join B; task B cần cùng lock để hoàn tất. Nếu A vẫn giữ lock trong khi chờ, có thể deadlock. Đừng bao một `synchronized` block dài quanh `join` khi subtasks có thể phụ thuộc cùng lock.

### 29.4. Không để mỗi task giữ reference đến cả dataset không cần thiết

Tasks có thể là lightweight nhưng vẫn là objects giữ references. Một cây tasks quá lớn giữ mảng, lists, closures và metadata lâu hơn dự kiến, gây áp lực memory/GC. Hạn chế số tasks bằng threshold, tránh giữ các kết quả trung gian không cần thiết.

## 30. Các giới hạn nâng cao của work-stealing

### 30.1. Không có bảo đảm thứ tự thực thi

Fork tasks theo thứ tự A, B, C không đồng nghĩa thực hiện A rồi B rồi C. Worker có thể lấy task mới ở local queue hoặc steal từ worker khác. Nếu nghiệp vụ yêu cầu order, thiết kế dependency graph và synchronization rõ.

### 30.2. Ưu tiên locality không phải guarantee cache hit

Local LIFO giúp tạo điều kiện xử lý gần dữ liệu liên quan, nhưng cache behavior phụ thuộc CPU topology, memory bandwidth, dữ liệu, JIT và scheduler. Không hứa một thuật toán sẽ nhanh gấp số cores chỉ vì có work-stealing.

### 30.3. Độ lệch tác vụ ảnh hưởng hiệu năng

Nếu một branch tính 95% công việc, còn branches khác rất nhỏ, pool có thể có workers idle dù vẫn còn một nhánh lớn chưa được chia. Hãy chia được branch lớn thành đủ subtasks hoặc chọn decomposition phù hợp.

### 30.4. Oversubscription cũng có chi phí

Tăng parallelism cao hơn số cores không tự tăng throughput CPU-bound. Nó có thể tăng context switches, tranh chấp cache/memory và scheduler overhead. Tránh cấu hình các pools khác nhau đều có parallelism rất cao mà không xét tổng CPU budget.

### 30.5. Work-stealing không thay thế load balancing toàn hệ thống

Pool cân bằng **tasks trong một process/pool**, không tự phân bổ jobs giữa các hosts/containers/regions. Với distributed compute, cần queue, partition, retries và fault tolerance ở tầng riêng.

## 31. CPU-bound hay I/O-bound: chọn công cụ đúng

| Workload | ForkJoinPool phù hợp? | Lưu ý |
| --- | --- | --- |
| Sum/transform mảng lớn chia vùng | Thường có | Threshold + baseline |
| Xử lý cây/đồ thị có nhánh độc lập | Có thể | Độ sâu, cạnh phụ thuộc, visited-state concurrency |
| Recursive divide-and-conquer thuần toán | Thường có | Avoid tiny tasks |
| Image processing theo tiles | Có thể | Memory bandwidth/cache |
| Merge sort tùy kích thước | Có thể | Test so với Arrays.parallelSort/standard library |
| API HTTP chặn vài giây | Thường không lý tưởng | I/O executor hoặc async |
| Database query blocking | Thường không lý tưởng | Bounded I/O pool, quotas |
| Chờ file/network read đồng bộ dài | Thường không lý tưởng | Async I/O/managedBlock chỉ khi hợp lý |
| Sleep/chờ khóa vô hạn | Không phù hợp | Có thể starvation/deadlock |
| Tác vụ cực nhỏ vài phép cộng | Thường không | Scheduling overhead |
| UI main-thread blocking | Không | Giữ UI responsive, completion trên context phù hợp |
| Parallel streams | Có thể dùng cơ chế tương tự | Source/collector, side effects, pool shared |

**ForkJoinPool không phải lời giải mặc định cho mọi loại multithreading.** Nếu là I/O-bound, mục tiêu là tránh giữ CPU worker khi đang chờ remote resource.

## 32. Cách benchmark đúng ForkJoinPool

Để đánh giá có lợi ích hay không:

1. Viết một **bản tuần tự** và assert kết quả.
2. Viết bản fork/join có threshold.
3. Dùng dữ liệu đủ lớn để đo có ý nghĩa.
4. Warm-up để JIT hoạt động; tránh kết luận từ lần chạy đầu.
5. Thay đổi threshold, pool parallelism, số phần tử và độ lệch công việc.
6. Đo qua nhiều iterations; ưu tiên JMH khi cần microbenchmark nghiêm túc.
7. Theo dõi GC/memory, CPU utilization, throughput/latency, steal/queue metrics.
8. Tránh benchmark in ra console trong từng leaf task (I/O và lock của console làm sai phép đo).
9. Không so “fork/join trên máy nóng” với “sequential trên máy vừa khởi động”.
10. Test correct results sau mỗi cấu hình.

### 32.1. Cẩn thận với “đếm threads” và metrics

`Thread.currentThread().getName()` hữu ích khi debug nhưng tên worker và số workers tham gia **không phải một contract cố định**. Không assert tên như `ForkJoinPool-1-worker-3` trong unit test.

### 32.2. Chú ý phép cộng số thực

Phép cộng `double` không có tính kết hợp tuyệt đối do sai số làm tròn:

```text
(a+b)+c may differ from a+(b+c)
```

Vì fork/join đổi thứ tự nhóm phép tính, kết quả double có thể khác chút so với sequential. Nếu cần reproducibility nghiêm ngặt, thiết kế reduction/order và tolerance theo domain; không tự cho rằng song song sum double luôn bit-identical.

## 33. Thiết kế task tốt và giới hạn thực tế

### 33.1. Tasks nên độc lập, ít side effects

Subtasks đọc immutable input và trả result thường dễ hiểu/dễ kiểm thử hơn subtasks chạm global variables. Nếu có output array, gán ranges riêng; tránh shared mutable collections không đồng bộ.

### 33.2. Chọn cơ chế join đầy đủ

Parent phải join tất cả subtasks mà kết quả phụ thuộc vào chúng. Nếu quên join một branch, main có thể thấy thiếu dữ liệu/partial result dù root task đã return.

### 33.3. Task không nên tự fork lại cùng instance tùy ý

`ForkJoinTask` có lifecycle. Theo Javadoc, fork một instance lần nữa khi chưa hoàn tất/reinitialize là cách dùng sai. Tạo task object riêng cho mỗi subproblem; không dùng chung một object RecursiveTask cho nhiều nhánh đang chạy.

### 33.4. Không fork từ bên ngoài rồi kỳ vọng vào private pool bất kỳ

`task.fork()` khi caller không ở trong một ForkJoinPool phù hợp có thể đi vào **common pool**. Nếu muốn đảm bảo dùng private pool, gửi root bằng `pool.invoke(root)` hoặc `pool.submit(root)` rồi fork subtasks **bên trong phép tính ấy**.

### 33.5. Avoid contention trong combine

Một phép tính song song tốt vẫn có thể chậm nếu mọi leaf phải cập nhật cùng một synchronized collection, disk, logger hoặc atomic counter. Hạn chế combine ở parent sau join, hoặc dùng per-task aggregation thích hợp.

### 33.6. Task creation/stack limits

Phân chia đệ quy không dừng gây StackOverflowError hoặc resource exhaustion. Base case cần được kiểm với N=0,1 và các phân vùng trống. Không dùng mid calculation có nguy cơ overflow trên ranges lớn; cách tổng quát là `from + (to - from)/2` khi chỉ số không âm.

## 34. CountedCompleter: biết đúng chỗ, không ép dùng

`CountedCompleter<T>` cũng là một subtype `ForkJoinTask`; nó dùng số pending completions để biểu diễn các cấu trúc task phụ thuộc, có thể hợp với một số loại parallel traversal/event-style graph computations mà không cần mỗi parent `join` tất cả children theo hình thức truyền thống.

Không cần đổi mọi `RecursiveTask` thành `CountedCompleter`. Với bài toán có kiểu chia-để-trị, tính kết quả rồi combine rõ ràng, `RecursiveTask` là điểm khởi đầu dễ đúng. Chỉ cân nhắc CountedCompleter khi dependency/completion pattern cần nó và team có khả năng kiểm thử state machine cẩn thận.

## 35. Common pool, virtual threads và Java hiện đại

### 35.1. Java 17 là baseline của các ví dụ

Các API `ForkJoinPool`, `RecursiveTask`, `RecursiveAction`, `ManagedBlocker` đều tồn tại và dùng được trong Java 17. `CompletableFuture` được đưa vào Java 8, nhưng Java 17 có thể dùng nó và explicit executor.

### 35.2. Virtual threads không thay thế ForkJoinPool cho mọi loại CPU task

Virtual threads trở thành tính năng hoàn chỉnh ở **Java 21**, không có trong `--release 17`. Chúng hỗ trợ mô hình concurrency nhiều tác vụ chờ I/O theo hướng khác; **không** làm một CPU-bound computation tự chạy trên nhiều cores nếu thuật toán vẫn tuần tự.

Fork/Join vẫn hữu ích cho divide-and-conquer CPU-bound. Không dùng virtual threads trong các ví dụ Java17 để giữ compatibility và tránh trộn hai bài toán.

### 35.3. Ưu tiên API tiêu chuẩn khi bài toán đã có cách giải đơn giản

Với phép cộng/sort trên dữ liệu nhỏ, vòng for, `Arrays`, `Stream` hoặc thư viện chuẩn có thể đơn giản và đủ nhanh. Chỉ viết custom ForkJoinTask khi thực sự cần kiểm soát decomposition, threshold, pool và kết quả.

## 36. Bảng lỗi sai thường gặp

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| Nghĩ mỗi task là thread | Bịa số threads và overhead | Task nhẹ; workers hữu hạn |
| Mỗi phần tử là một task | Overhead queue/GC | Threshold phù hợp |
| Thiếu base case | Chia vô hạn/stack lỗi | Ngưỡng dừng rõ |
| Fork hai nhánh, join ngay | Scheduling overhead | Fork một, compute một, join |
| Không join task con | Trả result khi chưa hoàn tất | Join đầy đủ dependencies |
| Dùng chung sharedSum++ | Race, kết quả sai | Recursive reduction/atomic phù hợp |
| Hai actions sửa cùng một vùng | Data race | Phân vùng không chồng |
| Assert stealCount >0 | Flaky CI | Assert result; metrics chỉ tuning |
| Assert đúng số worker threads | Flaky CI | Đọc parallelism và kết quả |
| Dùng I/O chặn dài trên commonPool | Starvation | I/O executor hoặc controlled managedBlock |
| Cho rằng managedBlock luôn tạo thêm thread | Sai expectation | Chỉ “có thể” compensate |
| Dùng asyncMode=true cho mọi workload | Không tối ưu, hiểu sai FIFO | Đúng event-style không join |
| Hiểu FIFO là completion order | Sai với parallel scheduling | Quản lý dependencies/ordering |
| Gọi fork ngoài pool mà mong private pool | Task vào common pool | Submit root vào đúng private pool |
| Re-fork cùng task chưa hoàn tất | Sai lifecycle | Task object riêng |
| Dùng isDone nghĩa là success | Che lỗi/cancellation | isCompletedNormally/getException |
| Coi cancel(true) chắc chắn interrupt | Side effects vẫn có thể chạy | Cooperative cancellation |
| Shutdown commonPool để “dọn” | Tác dụng không như private pool | Chỉ shutdown pools do mình sở hữu |
| Quên shutdown private pool | Resource leak | shutdown/awaitTermination |
| Main exit không đợi tasks | Có thể mất kết quả | invoke/join/get |
| Dùng commonPool không xét workloads khác | Contention/latency | Explicit private executor nếu cần |
| Bắt ngoại lệ join như Future.get | Sai kiểu exception | Phân biệt unchecked và ExecutionException |
| Dựa tên threads cho logic | Không portable | Thread-safe state và futures |
| Cho rằng parallel luôn nhanh hơn | Overhead lớn | Benchmark baseline |
| Dùng floating-point reduction exact equality | Khác do order | Tolerance/controlled order |
| Giữ lock rồi join task cần cùng lock | Deadlock | Tránh lock dependencies vòng |

## 37. Ma trận kiểm thử với Java 17

| Test | Kỳ vọng đúng | Không nên giả định |
| --- | --- | --- |
| Sum 1..100000 | 5.000.050.000, matches=true | Tất cả 4 workers đều chạy |
| Threshold1000 | 255 task objects do cây chia | 255 tasks bị steal |
| RecursiveAction 8 ký tự | FORKJOIN, 4 leaves | Thread names/order cố định |
| Threshold16 vs2 | Cùng sum 136, leaves1 vs8 | More leaves chắc chắn nhanh hơn |
| Pool.invoke | Result42 | Không block caller |
| Pool.submit | Future result | Completed theo thứ tự submit |
| Pool.execute | Task sẽ thực thi theo executor semantics | Có Future trả về |
| InForkJoinPool | true trong worker, false tại main | Mọi callable luôn chạy chính worker tên nào |
| AsyncMode | false mặc định, true khi request | Global FIFO completion |
| Metrics | Không âm và sum đúng | StealCount>0 |
| ManagedBlocker | Latch giải phóng; future trả released | Luôn sinh một worker bù |
| join failed | Ném unchecked IllegalStateException | Đều bọc ExecutionException |
| get failed | ExecutionException cause | join và get giống hoàn toàn |
| Cancel chưa submit | Task isCancelled, join throws | Đã ngắt một task đang chạy |
| commonPool | Shared singleton | Parallelism giống mọi JVM |
| CompletableFuture explicit pool | Pipeline43 | Phụ thuộc global default executor |
| Private shutdown | Không nhận submissions sau shutdown | Tự rollback side effects |
| CPU-bound threshold | Có thể speedup khi đủ workload | Luôn speedup ×cores |
| External blocking | Có thể gây starvation | Work-stealing tự sửa I/O block |

### 37.1. Vì sao stdout ví dụ ổn định?

Các chương trình dùng input nhỏ/cố định, không in raw thread names, đo durations hoặc exact steal counts. Chúng dùng `invoke`/`get`/`join`/latch để đợi completion trước khi kiểm. Vì vậy, kết quả in ra có thể được đối chiếu chính xác trong môi trường QA.

Không đồng nhất **stdout đã kiểm chứng trên một JDK** với lời hứa về performance và scheduling của mọi JVM.

## 38. Bài tập tự luyện

**Bài 1.** Một ForkJoinPool(4) có 1000 ForkJoinTask, có phải tạo 1000 threads? **Không.** Tasks được workers hữu hạn xử lý.

**Bài 2.** Work-stealing là gì? **Worker rảnh lấy task khả dụng ở hàng đợi worker khác** để cân bằng công việc.

**Bài 3.** Local deque dùng LIFO hay FIFO mặc định? **Thường local LIFO** cho fork/join; worker khác steal ở đầu đối diện theo mô hình phổ biến.

**Bài 4.** Tại sao không assert getStealCount()>0? **Scheduler có thể chạy mọi task không cần steal**.

**Bài 5.** `fork()` có bắt buộc chạy task trên thread khác? **Không**. Nó sắp xếp task đủ điều kiện chạy.

**Bài 6.** Một task cần kết quả, chọn RecursiveAction hay RecursiveTask? **RecursiveTask<V>**.

**Bài 7.** Một task sửa từng phần của mảng và không trả result, chọn gì? **RecursiveAction**, mỗi vùng riêng.

**Bài 8.** Bài toán chia đôi, nên fork nhánh trái và compute nhánh phải thế nào? **left.fork(); right.compute(); left.join()**.

**Bài 9.** Tại sao phải chọn threshold? **Tránh tasks quá nhỏ tạo scheduling overhead**.

**Bài 10.** Tính tổng 1..16 bằng threshold16 và threshold2 có phải cùng kết quả? **Có, 136**, chỉ số leaves khác.

**Bài 11.** Parent quên join task trái mà trả result được không? **Không**, có thể thiếu dữ liệu.

**Bài 12.** SharedSum++ ở nhiều leaves có an toàn không? **Không**, có race.

**Bài 13.** Nếu hai RecursiveAction sửa hai vùng không chồng lấn, có cần khóa từng phần tử? **Không nhất thiết**, nhưng phải đợi tất cả hoàn tất trước khi dùng kết quả.

**Bài 14.** Trong root task, nên dùng `pool.submit(subtask)` hay `subtask.fork()`? **Thường fork()**, theo hợp đồng within-computation.

**Bài 15.** `invoke` khác `submit` ở điểm nào? **invoke đợi result ngay; submit trả handle/Future**.

**Bài 16.** `execute` có trả Future không? **Không**, dùng submit nếu cần handle.

**Bài 17.** `join` của task throw IllegalStateException ra sao? **Ném unchecked exception**, không phải `ExecutionException`.

**Bài 18.** `Future.get` khi task throw IllegalStateException? **ExecutionException** bao cause.

**Bài 19.** `isDone` có chứng minh task thành công? **Không**, cancelled/failed cũng done.

**Bài 20.** `cancel(true)` có đảm bảo interrupt computation đang chạy không? **Không**, cần cancellation policy/checkpoints.

**Bài 21.** `asyncMode=true` dùng FIFO ở phạm vi nào? **Local scheduling cho forked tasks không join**, không bảo đảm global order.

**Bài 22.** Có nên bật asyncMode cho mọi RecursiveTask? **Không**, chọn theo workload.

**Bài 23.** `commonPool()` có phải singleton shared pool? **Có**, nhưng parallelism phụ thuộc config.

**Bài 24.** Có nên shutdown commonPool như private pool? **Không**; lifecycle khác.

**Bài 25.** Một thư viện gửi blocking DB requests vào commonPool có thể gây điều gì? **Starvation/contension với CPU tasks khác**.

**Bài 26.** ManagedBlocker có đảm bảo luôn tăng worker count? **Không**, chỉ hỗ trợ pool có thể compensate.

**Bài 27.** Dữ liệu `getStealCount()==3` có đủ chứng minh 3 workers đã chạy không? **Không**. Chỉ là ước lượng tasks được worker khác hoàn tất.

**Bài 28.** `getQueuedTaskCount` và `getQueuedSubmissionCount` khác nhau gì? **Local queues vs external submissions**.

**Bài 29.** Timeout của `future.get` có làm task tự hủy không? **Không**, cần cancellation/ownership policy.

**Bài 30.** Hai tasks có dependencies vòng qua một lock, work-stealing có sửa được không? **Không**, có thể deadlock.

**Bài 31.** Vì sao tính tổng double song song có thể khác số bit? **Thứ tự cộng và floating-point rounding**.

**Bài 32.** Vì sao parallelism vượt CPU cores chưa chắc tốt? **Contention, context switches, memory bandwidth**.

**Bài 33.** CompletableFuture không truyền executor dùng gì trên Java17? **Thông thường commonPool nếu parallelism ít nhất2, nếu không fallback thread mới theo docs**.

**Bài 34.** Muốn CompletableFuture stage chạy trong pool riêng? **Truyền Executor tường minh**.

**Bài 35.** Khi nào chọn JMH? **Khi đo hiệu năng/microbenchmark nghiêm túc**, không dùng một System.nanoTime đơn lẻ.

**Bài 36.** Có nên chọn ForkJoinPool làm thread-per-request server I/O? **Thường không**; cân nhắc async/bounded I/O executor.

**Bài 37.** Java21 virtual threads có khiến CPU-bound task tự song song? **Không**; vẫn cần thuật toán chia nhỏ.

**Bài 38.** Làm sao kiểm đúng “work-stealing” trong CI? **Assert results, no races, outcome và metrics hợp lệ; đo steals như telemetry không phải golden value.**

## 39. Checklist trước khi triển khai

- [ ] Bài toán CPU-bound và có thể chia thành nhánh tương đối độc lập.
- [ ] Có sequential baseline đúng.
- [ ] `RecursiveTask` khi cần result, `RecursiveAction` khi chỉ mutate vùng riêng.
- [ ] Base case luôn dừng recursion.
- [ ] Threshold dựa benchmark, không fork từng phần tử vô ích.
- [ ] Thiết kế fork một nhánh, compute một nhánh, join đúng dependencies.
- [ ] Không chia ranges chồng lấn nếu có mutations.
- [ ] Không dùng shared mutable accumulator không đồng bộ.
- [ ] Không fork một task instance nhiều lần khi chưa completed/reinitialized.
- [ ] Root task được submit vào đúng pool được quản lý.
- [ ] Không dựa vào thread names/worker scheduling order.
- [ ] Không assert một giá trị getStealCount nhất định.
- [ ] Phân biệt local queued tasks và external submissions.
- [ ] Phân biệt parallelism target với số worker thực tế.
- [ ] Không dùng asyncMode như switch hiệu năng chung.
- [ ] Chỉ dùng asyncMode FIFO khi workload event-style phù hợp.
- [ ] Không dùng commonPool cho blocking I/O lâu khi chưa đánh giá impact.
- [ ] `ManagedBlocker` chỉ hỗ trợ compensation, không cam kết.
- [ ] Không giữ locks khi join tasks cần cùng lock.
- [ ] Quản lý exception của join và get đúng type.
- [ ] Không coi isDone nghĩa là success.
- [ ] Cancellation có protocol; không tin cancel(true) chắc chắn interrupt.
- [ ] Pools riêng có shutdown/awaitTermination và không leak.
- [ ] Không shutdown commonPool như pool do mình sở hữu.
- [ ] Main/application boundaries đợi kết quả quan trọng trước khi kết thúc.
- [ ] CompletableFuture dùng explicit executor khi cần isolation.
- [ ] Đo JIT warm-up, GC, core count, benchmark metrics.
- [ ] Với floating-point reduction, thiết kế tolerance/reproducibility.
- [ ] Hiểu tính năng vẫn hợp lệ trên Java 17+; không dùng API lỗi thời.

## 40. Tài liệu Java 17 chính thức

- [`ForkJoinPool` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ForkJoinPool.html): work-stealing, parallelism, asyncMode, commonPool, lifecycle, metrics.
- [`ForkJoinTask<V>` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ForkJoinTask.html): fork/join/invoke, dependencies, exception/cancellation, task state.
- [`RecursiveTask<V>` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/RecursiveTask.html): task chia-để-trị có kết quả, base case và granularity.
- [`RecursiveAction` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/RecursiveAction.html): task đệ quy không có return result.
- [`ForkJoinPool.ManagedBlocker` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ForkJoinPool.ManagedBlocker.html): managed blocking và compensation.
- [`CountedCompleter<T>` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountedCompleter.html): graph-like completion patterns nâng cao.
- [`ExecutorService` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): submit/execute/shutdown/termination.
- [`Future<V>` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): get, timeout, cancellation.
- [`CompletableFuture<T>` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): default async executor và explicit executor.
- [`ConcurrentHashMap` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html): concurrent sets trong test telemetry.
- [`AtomicInteger` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html): đếm task objects/leaves an toàn trong demos.

**Kết luận:** `ForkJoinPool` xử lý các bài toán chia-để-trị bằng **một tập workers và nhiều tasks nhẹ**. Workers có thể **đánh cắp công việc** khi rảnh, nhưng thứ tự chạy, số steals và số threads tham gia không phải những kết quả có thể hardcode. Muốn đúng và hiệu quả, hãy dùng `fork/compute/join`, đặt threshold có cơ sở, hạn chế shared state, tránh blocking, quản lý common/private pool và đo hiệu năng thực tế. Mục tiêu cuối cùng là kết quả tính toán đúng, resource usage có kiểm soát và speedup được chứng minh bằng benchmark — chứ không phải tạo thật nhiều tasks hoặc đẩy steal count lên cao.