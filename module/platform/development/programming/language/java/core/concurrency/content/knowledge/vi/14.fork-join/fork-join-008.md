# ForkJoinPool.commonPool() và tác vụ dùng chung trong Java

> **Cốt lõi:** `ForkJoinPool.commonPool()` trả về một **Fork/Join executor dùng chung trong cùng JVM**, không tạo pool riêng cho mỗi lời gọi hoặc module. Nhiều tác vụ `ForkJoinTask`, các thao tác bất đồng bộ `CompletableFuture` không chỉ định executor (theo quy tắc mặc định) và nhiều parallel-stream computations có thể cùng chia sẻ hạ tầng thực thi này. Do đó tác vụ CPU nặng hoặc blocking không kiểm soát ở thành phần A có thể làm thành phần B bị chậm. Cần phân biệt **chia sẻ pool**, **chia sẻ worker**, **chia sẻ dữ liệu** và **cô lập tài nguyên**: đây là những khái niệm khác nhau.

Bài thuộc nhóm **Fork/Join** của **Java concurrency nói chung**, sử dụng Java SE 17+. Không sử dụng hoặc phân tích Spring.

## 1. Common pool là gì và tại sao tồn tại?

`ForkJoinPool` triển khai `ExecutorService`, được thiết kế cho công việc có thể chia nhỏ (*fork*) rồi kết hợp (*join*). Implementation dùng cơ chế **work-stealing** để một worker còn rảnh có thể nhận bớt công việc của worker khác. Điều này đặc biệt hữu ích cho thuật toán chia để trị, ví dụ tính tổng các đoạn mảng, xử lý cây hoặc một số phép tính song song.

Từ Java 8, JDK có một pool toàn cục trong tiến trình:

~~~java
// Snippet API — thêm import và đặt trong class/method khi dùng.
ForkJoinPool pool = ForkJoinPool.commonPool();
~~~

Các lời gọi `commonPool()` trong ứng dụng thông thường nhận cùng một instance. Điều đó làm giảm nhu cầu tạo riêng một pool mới cho mỗi tác vụ nhỏ, nhưng cũng đồng nghĩa **nhiều thành phần dùng chung resource**.

~~~text
                  CÙNG MỘT JVM
Module A ── ForkJoinTask ──────────┐
Module B ── CompletableFuture ─────┼──> ForkJoinPool.commonPool()
Module C ── parallel stream ───────┘             │
                                                ▼
                                       Các worker dùng chung
                                       [task A, task B, task C]
~~~

Đây là sơ đồ khái niệm. Không bảo đảm mọi call site của `CompletableFuture` hay mọi hoạt động stream luôn chạy trên common-pool worker trong **mọi cấu hình**, vì default execution có ngoại lệ và caller thread cũng có thể tham gia.

**Phạm vi dùng chung:** trong một JVM, không phải một pool phân tán xuyên nhiều JVM. Common pool không tạo quota riêng cho từng thư viện, request hoặc tenant.

### Những điều common pool KHÔNG cung cấp

- Không có một lock chung tự bảo vệ object nghiệp vụ.
- Không tự biến `HashMap`, `ArrayList` hay counter mutable thành thread-safe.
- Không bảo đảm task submit trước sẽ hoàn tất trước.
- Không cam kết deadline/p99 latency hoặc tài nguyên dành riêng cho module của bạn.
- Không tạo thêm CPU chỉ nhờ work-stealing.
- Không cho component riêng đóng shared pool khi component ấy kết thúc.
- Không tự hủy/rollback side effects khi caller bỏ cuộc.

## 2. Work-stealing và cách dùng `fork`/`join`

Một worker Fork/Join có các task đang chờ; worker khác còn rảnh có thể lấy bớt task từ worker ấy. Thuật toán điển hình:

1. Một nhánh quá lớn được chia thành hai bài toán nhỏ hơn.
2. `fork()` một nhánh để pool có thể thực thi nó.
3. Worker hiện tại xử lý nhánh còn lại qua `compute()`.
4. Gọi `join()` trên nhánh đã fork để lấy kết quả.
5. Gộp kết quả thành giá trị của nhánh cha.

~~~text
                           SumTask(0..8)
                         /               \
                 SumTask(0..4)       SumTask(4..8)
                    /     \              /     \
                 leaf     leaf        leaf     leaf
                    \     /              \     /
                   merge                 merge
                         \               /
                           final result
~~~

Work-stealing không đồng nghĩa mỗi leaf luôn được chạy bởi một thread khác. Với dữ liệu nhỏ hoặc ít CPU, nhiều nhánh có thể chạy tuần tự. Cũng không cam kết thứ tự fork, steal hay completion phù hợp với thứ tự xuất hiện trong source code.

### ForkJoinTask và Future

`ForkJoinTask<V>` triển khai `Future<V>` và thêm API `fork()`, `join()`, `invoke()`. `join()` dùng cơ chế chờ/kết hợp của Fork/Join; `Future.get()` có hợp đồng checked exceptions như `InterruptedException` và `ExecutionException`. Khi task ném exception, `join()` có thể truyền lại unchecked exception/Error; không xem nó như `Future.get()` về kiểu exception.

Đối với task con cùng ForkJoinPool, pattern `fork / compute / join` là điểm mạnh của framework. Không suy rộng rằng mọi `Future.get()`, mạng hoặc blocking I/O tùy ý đều được work-stealing xử lý an toàn.

## 3. Ví dụ 1 — hai lời gọi cùng trả một common pool

Tạo `CommonPoolIdentity.java` (Java 17+):

~~~java
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.ForkJoinTask;

public class CommonPoolIdentity {
    public static void main(String[] args) {
        ForkJoinPool a = ForkJoinPool.commonPool();
        ForkJoinPool b = ForkJoinPool.commonPool();

        System.out.println("same instance = " + (a == b));

        ForkJoinTask<Integer> task = a.submit(() -> 6 * 7);
        System.out.println("answer = " + task.join());

        System.out.println("still shared = "
                + (b == ForkJoinPool.commonPool()));
    }
}
~~~

Chạy:

~~~bash
javac CommonPoolIdentity.java
java CommonPoolIdentity
~~~

Stdout bình thường:

~~~text
same instance = true
answer = 42
still shared = true
~~~

`a` và `b` trỏ đến cùng executor instance. `ForkJoinTask<Integer>` giúp đợi giá trị `42` được tính xong. Chương trình **không gọi `shutdown()`** lên common pool: đây không phải tài nguyên sở hữu riêng của method `main()`.

## 4. Ví dụ 2 — RecursiveTask chia để trị và hợp nhất kết quả

Tạo `CommonPoolSum.java` (Java 17+):

~~~java
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveTask;

public class CommonPoolSum {
    private static final class SumTask extends RecursiveTask<Long> {
        private static final int THRESHOLD = 2;

        private final int[] values;
        private final int from;
        private final int to;

        SumTask(int[] values, int from, int to) {
            this.values = values;
            this.from = from;
            this.to = to;
        }

        @Override
        protected Long compute() {
            if (to - from <= THRESHOLD) {
                long total = 0;
                for (int i = from; i < to; i++) {
                    total += values[i];
                }
                return total;
            }

            int mid = from + (to - from) / 2;
            SumTask left = new SumTask(values, from, mid);
            SumTask right = new SumTask(values, mid, to);

            left.fork();
            long rightResult = right.compute();
            long leftResult = left.join();

            return leftResult + rightResult;
        }
    }

    public static void main(String[] args) {
        int[] numbers = {1, 2, 3, 4, 5, 6, 7, 8};
        long sum = ForkJoinPool.commonPool().invoke(
                new SumTask(numbers, 0, numbers.length));
        System.out.println("sum = " + sum);
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac CommonPoolSum.java
java CommonPoolSum
~~~

Đầu ra:

~~~text
sum = 36
~~~

Các leaf đọc các phần tử khác nhau của `numbers` và trả về giá trị cục bộ. Không có `long sharedTotal` để nhiều worker cập nhật bằng `sharedTotal += ...` nên không có lost update. Kết quả gộp bằng `leftResult + rightResult` sau khi cả hai nhánh có kết quả.

`THRESHOLD=2` chỉ để dễ thấy recursion. Với workload thật, một threshold quá nhỏ tạo rất nhiều tasks và overhead; một threshold quá lớn làm ít nhánh có thể chạy song song. Cần benchmark trước khi chọn.

**Lưu ý:** Nếu các leaf cùng ghi vào một `ArrayList` không khóa hoặc cùng sửa object mutable, Fork/Join **không tự bảo vệ dữ liệu ấy**. Nên giảm trên giá trị bất biến, phân vùng output riêng rồi merge, hoặc áp dụng synchronization đúng invariant.

## 5. Hai client cùng pool có thể can nhiễu nhau

Một module sử dụng common pool không sở hữu toàn bộ workers. Khi module A submit nhiều task CPU nặng, module B cũng dùng common pool có thể phải chờ worker rảnh, mặc dù B chỉ có vài task ngắn. Đây là hiện tượng **noisy neighbor** trong một JVM.

~~~text
Load bình thường:
    workers: [A] [B] [idle] [idle]
    task B có cơ hội được xử lý sớm

Khi A tạo nhiều CPU tasks:
    workers: [A] [A] [A] [A]
    các task B có thể phải chờ tùy scheduling
    độ trễ B có thể tăng
~~~

Đây là mô hình minh họa, không phải số worker hoặc kết quả được cam kết. Work stealing giúp phân phối việc, nhưng **không bảo đảm** deadline hoặc fairness theo module.

### Ví dụ 3 — hai thành phần submit cùng resource

Tạo `SharedClientsDemo.java` (Java 17+):

~~~java
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.ForkJoinTask;

public class SharedClientsDemo {
    private static final class ClientA {
        static ForkJoinTask<String> submit() {
            return ForkJoinPool.commonPool().submit(() -> "A");
        }
    }

    private static final class ClientB {
        static ForkJoinTask<String> submit() {
            return ForkJoinPool.commonPool().submit(() -> "B");
        }
    }

    public static void main(String[] args) {
        ForkJoinTask<String> a = ClientA.submit();
        ForkJoinTask<String> b = ClientB.submit();

        System.out.println("results = " + a.join() + b.join());
        System.out.println("same executor = "
                + (ForkJoinPool.commonPool() == ForkJoinPool.commonPool()));
    }
}
~~~

Chạy:

~~~bash
javac SharedClientsDemo.java
java SharedClientsDemo
~~~

Stdout:

~~~text
results = AB
same executor = true
~~~

Dòng `AB` là do **main ghép kết quả theo thứ tự `a.join() + b.join()`**, không chứng minh task A chạy trước task B. Hai tasks có thể được thực hiện theo thứ tự khác nhau. Chương trình chứng minh sự chia sẻ instance, không cố biến một lần stress test thành bảo đảm lịch chạy.

## 6. CompletableFuture và default async executor

Trong Java 17, các method như `CompletableFuture.supplyAsync(supplier)` và `runAsync(runnable)` **không chỉ định executor** thường sử dụng `ForkJoinPool.commonPool()` làm default asynchronous execution facility.

**Ngoại lệ quan trọng trong API Java 17:** Nếu common pool **không hỗ trợ parallelism ít nhất 2**, implementation có thể tạo **một Thread mới cho mỗi async task**. Do đó không viết test yêu cầu mọi `supplyAsync` luôn thực thi trên thread có tên `ForkJoinPool.commonPool-worker-...`.

Phân biệt các kiểu method:

~~~java
// Các snippet, chưa là chương trình độc lập.
CompletableFuture<Integer> a =
        CompletableFuture.supplyAsync(() -> 21);

CompletableFuture<Integer> b =
        CompletableFuture.supplyAsync(() -> 21, dedicatedExecutor);

CompletableFuture<Integer> c =
        a.thenApply(x -> x * 2);

CompletableFuture<Integer> d =
        a.thenApplyAsync(x -> x * 2, dedicatedExecutor);
~~~

- `a` dùng default async facility, thường là common pool.
- `b` chỉ định executor riêng, không phụ thuộc vào default facility cho **chính stage đó**.
- `c` là synchronous continuation, có thể thực thi trong thread hoàn tất stage trước hoặc caller theo timing; không suy ra thread cố định.
- `d` chỉ định executor cho asynchronous continuation.

Khi muốn cô lập toàn bộ pipeline, audit **từng async continuation**: chỉ định executor ở `supplyAsync` đầu tiên nhưng tiếp tục gọi `thenApplyAsync` không có executor có thể khiến stage sau quay về default facility.

### Ví dụ 4 — default facility và explicit Executor

Tạo `CompletableFuturePools.java` (Java 17+):

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class CompletableFuturePools {
    public static void main(String[] args) throws InterruptedException {
        ExecutorService dedicated = Executors.newFixedThreadPool(2);

        try {
            CompletableFuture<Integer> defaultTask =
                    CompletableFuture.supplyAsync(() -> 20);

            CompletableFuture<Integer> explicitTask =
                    CompletableFuture.supplyAsync(() -> 22, dedicated);

            System.out.println("sum = "
                    + (defaultTask.join() + explicitTask.join()));
        } finally {
            dedicated.shutdown();
            if (!dedicated.awaitTermination(10, TimeUnit.SECONDS)) {
                dedicated.shutdownNow();
            }
        }

        System.out.println("dedicated shutdown = "
                + dedicated.isShutdown());
    }
}
~~~

Chạy:

~~~bash
javac CompletableFuturePools.java
java CompletableFuturePools
~~~

Stdout:

~~~text
sum = 42
dedicated shutdown = true
~~~

Kết quả không phụ thuộc vào thứ tự thực thi hai tasks. Pool được tạo tường minh là **tài nguyên của module**, phải shutdown; common pool không cần và không nên shutdown bởi đoạn code này.

`newFixedThreadPool(2)` ở đây dùng để minh họa **ownership/isolation**, không phải một cấu hình production an toàn dưới overload: factory này thường sử dụng unbounded queue. Với producer không được giới hạn tốc độ, cần bounded queue/backpressure/rejection phù hợp.

## 7. Parallel stream cũng có thể chia sẻ hạ tầng Fork/Join

`stream.parallel()` hoặc `parallelStream()` kích hoạt đánh giá các phần tử theo hướng song song khi terminal operation chạy. Trong implementation JDK thông dụng, parallel streams liên quan common Fork/Join infrastructure; **thread gọi terminal operation cũng có thể tham gia**.

Kết quả về giá trị có thể xác định với reduction thuần, nhưng thứ tự worker/thời điểm hoàn tất từng phần tử không được cố định.

### Ví dụ 5 — phép reduce song song có kết quả ổn định

Tạo `ParallelStreamSum.java` (Java 17+):

~~~java
import java.util.stream.IntStream;

public class ParallelStreamSum {
    public static void main(String[] args) {
        long sum = IntStream.rangeClosed(1, 100)
                .parallel()
                .mapToLong(x -> x)
                .sum();

        System.out.println("sum = " + sum);
    }
}
~~~

Chạy:

~~~bash
javac ParallelStreamSum.java
java ParallelStreamSum
~~~

Stdout:

~~~text
sum = 5050
~~~

Phép cộng `long` trên 1..100 không overflow và là reduction thuần. Dù thứ tự chia phần tử thay đổi, tổng vẫn `5050`. Ngược lại, `parallel().forEach(System.out::println)` có thứ tự output không xác định.

**Phản ví dụ không an toàn** (snippet, không phải chương trình độc lập):

~~~java
List<Integer> results = new ArrayList<>();
IntStream.range(0, 1_000).parallel().forEach(results::add);
~~~

`ArrayList` không thread-safe với nhiều writers. Dùng collector/reduction phù hợp hoặc một data structure/synchronization protocol đáp ứng invariant thay vì thay một vòng for bằng `parallel()` rồi bỏ qua race.

### Parallel không tự nhanh hơn

- Dữ liệu quá ít: overhead phân chia/join lớn hơn tính toán.
- Công việc mỗi phần tử quá nhẹ: không đủ CPU work để bù overhead.
- Blocking call: dùng chung pool có thể giảm throughput và can nhiễu module khác.
- Stateful operations/shared locks: tranh chấp/serialization.
- Memory allocations/GC: các nhánh tạo nhiều object trung gian.
- Số lõi CPU bị giới hạn bởi container hoặc các process khác.

Đo workload thực trước khi dùng parallel stream, đặc biệt trong thư viện phục vụ nhiều request.

## 8. Pool dùng chung + blocking I/O: nguyên nhân latency khó tìm

Fork/Join hiệu quả nhất với các task **tính toán** có thể phân tách và phối hợp. Khi worker bị chặn bởi network/database/file I/O lâu hoặc chờ một latch không có worker nào giải phóng, pool mất khả năng dùng worker đó cho task khác.

~~~text
commonPool workers:
  W1 -> blocking HTTP
  W2 -> blocking database
  W3 -> blocking wait
  W4 -> CPU work

Các tasks của module khác cùng pool:
  có thể chờ, tăng queueing delay và p99 latency
~~~

Một call `CompletableFuture.supplyAsync(() -> blockingRemoteCall())` không tự biến `blockingRemoteCall()` thành non-blocking I/O. Nó chỉ chuyển computation sang một nơi thực thi bất đồng bộ đối với caller; **một worker vẫn có thể bị block**.

Các phương án khi workload chủ yếu blocking I/O:

- Dùng **ExecutorService riêng** cho I/O, có giới hạn worker/in-flight và thời gian chờ.
- Bọc queue bằng bounded admission hoặc policy rejection/backpressure rõ ràng.
- Áp dụng connect/read/request timeout và cancellation cooperative khi khả thi.
- Giảm việc giữ locks qua I/O; không đợi một task cần cùng lock.
- Dùng asynchronous/non-blocking I/O thật sự khi thư viện hỗ trợ.
- Khi phải block trong ForkJoin worker, xem `ForkJoinPool.ManagedBlocker` và giới hạn của nó.

**Không** chỉ tăng common-pool parallelism để chữa mọi vấn đề: DB connection pool, API rate limits, sockets và CPU vẫn có giới hạn. Nhiều threads đôi khi làm contention/GC nặng hơn.

## 9. ManagedBlocker: thông báo cho ForkJoinPool biết đang chờ

`ForkJoinPool.ManagedBlocker` có hai phương thức:

- `isReleasable()`: trả true khi có thể tiếp tục mà không cần block.
- `block()`: thực hiện chờ (nếu cần) rồi trả true khi đã có thể tiến triển.

Khi gọi `ForkJoinPool.managedBlock(blocker)` từ ForkJoin worker, pool có thể cố **compensate** cho worker bị chặn bằng cách điều chỉnh workers trong một số điều kiện. Điều đó **không** bảo đảm luôn tạo thread thay thế, không biến I/O thành non-blocking và không bảo đảm deadline.

Snippet Java 17+ minh họa ý tưởng (chưa phải chương trình standalone; biến `latch` ở lời gọi cần có scope thích hợp):

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ForkJoinPool;

final class LatchBlocker implements ForkJoinPool.ManagedBlocker {
    private final CountDownLatch latch;

    LatchBlocker(CountDownLatch latch) {
        this.latch = latch;
    }

    @Override
    public boolean isReleasable() {
        return latch.getCount() == 0;
    }

    @Override
    public boolean block() throws InterruptedException {
        latch.await();
        return true;
    }
}

// Trong method throws InterruptedException:
ForkJoinPool.managedBlock(new LatchBlocker(latch));
~~~

Không dùng ManagedBlocker như “lệnh xin thêm vô hạn workers”; giới hạn tài nguyên vẫn tồn tại, và nếu không có ai phát tín hiệu cho latch thì worker vẫn có thể đợi mãi. Trong nhiều ứng dụng, tách I/O vào executor riêng với capacity rõ ràng dễ kiểm soát hơn.

## 10. Nested waits và thread starvation

Không phải mọi thao tác chờ đều được Fork/Join hỗ trợ như `ForkJoinTask.join()` trong một thuật toán đệ quy.

Tình huống nguy hiểm:

~~~text
Task A đang giữ lock L và chờ Future của task B.
Task B cần lock L mới hoàn thành.
A chờ B; B chờ A nhả L -> có thể deadlock.
~~~

Hoặc một nhóm tasks chiếm hết workers rồi chờ một external event được tạo bởi những tasks **đang chờ** được schedule trong cùng executor. Work stealing có thể giúp cân bằng task có thể chạy, nhưng không tạo khả năng tiến triển cho một dependency cycle không thể giải.

Với `CompletableFuture`, cân nhắc diễn đạt quan hệ phụ thuộc bằng `thenCompose`, `thenCombine`, `allOf` thay vì block `join()`/`get()` bên trong mọi stage. Tuy nhiên, **composition không tạo thêm CPU/worker** và không sửa một downstream bottleneck; audit executor và failure policy.

Với Fork/Join recursive task, pattern thường hiệu quả là `left.fork(); right.compute(); left.join();` chứ không fork mọi nhánh rồi block chờ toàn bộ ở mọi mức đệ quy.

## 11. Common pool và vòng đời: không shutdown tài nguyên chung

`ForkJoinPool.commonPool()` thuộc cơ chế dùng chung của JVM. Theo tài liệu `ForkJoinPool`, những lời gọi shutdown trên **common pool** không có hiệu lực shutdown theo cách dùng pool tự tạo.

Hệ quả:

- Module A **không** thể dựa vào `commonPool().shutdown()` để dừng riêng tasks của A.
- Module B vẫn có thể đang sử dụng common pool.
- `awaitQuiescence(timeout, unit)` liên quan trạng thái quiescent của **pool**, có thể bị ảnh hưởng bởi task của các client khác; không phải “join toàn bộ tasks của riêng mình”.
- Để quản lý tasks của chính mình, giữ `ForkJoinTask`/`Future` handles và chờ/hủy theo protocol phù hợp.
- Nếu cần đóng workers khi module dừng, hãy tạo một pool **sở hữu riêng**, theo dõi tasks và shutdown nó.
- `ForkJoinPool` trong Java 17 không nên được viết như một `AutoCloseable` dùng try-with-resources theo kiểu các phiên bản JDK mới hơn; dùng shutdown/awaitTermination rõ ràng khi sở hữu pool.

### Ví dụ 6 — pool riêng có thể shutdown

Tạo `DedicatedForkJoinPool.java` (Java 17+):

~~~java
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.ForkJoinTask;
import java.util.concurrent.TimeUnit;

public class DedicatedForkJoinPool {
    public static void main(String[] args) throws InterruptedException {
        ForkJoinPool owned = new ForkJoinPool(2);

        try {
            ForkJoinTask<Integer> first = owned.submit(() -> 3 * 3);
            ForkJoinTask<Integer> second = owned.submit(() -> 4 * 4);

            System.out.println("sum of squares = "
                    + (first.join() + second.join()));
        } finally {
            owned.shutdown();
            if (!owned.awaitTermination(10, TimeUnit.SECONDS)) {
                owned.shutdownNow();
            }
        }

        System.out.println("owned shutdown = " + owned.isShutdown());
        System.out.println("common still shared = "
                + (ForkJoinPool.commonPool() == ForkJoinPool.commonPool()));
    }
}
~~~

Chạy:

~~~bash
javac DedicatedForkJoinPool.java
java DedicatedForkJoinPool
~~~

Stdout bình thường:

~~~text
sum of squares = 25
owned shutdown = true
common still shared = true
~~~

Pool `owned` tách worker queues và có lifecycle riêng. Nhưng tất cả pools trong một JVM vẫn **tranh CPU, heap, GC và tài nguyên OS**, nên isolation ở mức executor không đồng nghĩa bảo đảm CPU quota riêng hay hard real-time scheduling.

Không tạo một `ForkJoinPool` mới **cho từng request**. Pool thường được tạo theo lifecycle của một component, được tái sử dụng, giám sát và đóng khi không còn người dùng.

## 12. Parallelism, hệ thống properties và cấu hình JVM

`ForkJoinPool.getCommonPoolParallelism()` trả target parallelism của common pool. Trong cấu hình thường gặp, JDK chọn mức này dựa trên số processor JVM nhìn thấy; cấu hình có thể chịu ảnh hưởng bởi container/cpu quotas và JVM settings.

Có thể chỉ định một số cấu hình qua system properties, ví dụ:

~~~bash
java -Djava.util.concurrent.ForkJoinPool.common.parallelism=4 MyApplication
~~~

Đây là ví dụ syntax, **không phải khuyến nghị đặt 4 cho mọi ứng dụng**. Tài liệu `ForkJoinPool` còn mô tả những thuộc tính khác liên quan common-pool thread factory và exception handler.

Cẩn trọng:

1. Đặt property **trước khi common pool được khởi tạo**; `System.setProperty` sau đó không phải cách resize pool đã tồn tại.
2. Không cố định công thức “số lõi trừ một” cho mọi JDK/container/settings.
3. Target parallelism không phải lời hứa số workers đang chạy bằng đúng con số ấy tại mọi thời điểm.
4. Parallelism thấp có thể khiến default async facility của `CompletableFuture` đi vào đường fallback tạo threads mới.
5. Parallelism quá cao có thể gây context switching hoặc downstream overload.
6. Đổi cấu hình toàn JVM ảnh hưởng **tất cả modules** có dùng common pool, không riêng feature đang tối ưu.

Nếu nhu cầu tuning chỉ xuất hiện ở một workload, **pool riêng** thường là biên giới cấu hình rõ ràng hơn.

## 13. ThreadLocal và context khi dùng shared workers

`ThreadLocal` gắn dữ liệu với **thread hiện tại**, không tự truyền state từ thread submit sang worker khác.

~~~java
// Snippet cấu trúc, không phải chương trình độc lập.
ThreadLocal<String> requestContext = new ThreadLocal<>();
requestContext.set("request-1");

ForkJoinPool.commonPool().execute(() -> {
    String observed = requestContext.get();
    // Không được mặc định observed == "request-1".
});
~~~

Một số parallel-stream computations còn dùng thread caller tham gia, nên việc phụ thuộc ThreadLocal để quyết định quyền truy cập hoặc logic nghiệp vụ càng dễ tạo hành vi không ổn định theo thời điểm.

Khi cần context, ưu tiên truyền **immutable task input** gồm request ID, deadline, correlation ID hoặc các giá trị cần thiết. Nếu chủ động set ThreadLocal trên worker, dọn dẹp trong `finally` và hiểu quy tắc kế thừa/retention của implementation. Không dùng một shared worker như nơi lưu state riêng của từng request.

Không áp dụng mô hình request-context của framework; bài đang nói về Java `ThreadLocal` nói chung.

## 14. Cancellation của ForkJoinTask có semantics riêng

`ForkJoinTask` implements `Future` nhưng không phải `FutureTask` thông thường. Theo Java 17 API, với default `ForkJoinTask` implementation, tham số `mayInterruptIfRunning` của `cancel(boolean)` **không có tác dụng interrupt worker theo cách người đọc có thể kỳ vọng**; interruption không phải phương pháp mặc định để điều khiển ForkJoinTask cancellation.

Vì vậy:

- `task.cancel(true)` có thể đánh dấu task cancelled, nhưng không bảo đảm một body đang chạy dừng tức khắc.
- `isDone()` sau cancel là trạng thái Future, không phải bằng chứng side effects/cleanup đã hoàn tất.
- `CompletableFuture.cancel(true)` cũng **không dùng tham số mayInterruptIfRunning để điều khiển computation** trong implementation CompletableFuture.
- Nếu computation CPU dài cần bị ngừng, phải thiết kế **cooperative cancellation token**, chẳng hạn `AtomicBoolean` được kiểm tra ở những điểm an toàn.
- Với task có I/O, thêm I/O deadline/timeout; interrupt hoặc cancel không tự rollback database.
- Một task đã gửi email, gọi payment API hoặc ghi DB có thể có side effects ngay cả khi Future bị hủy sau đó.

Đừng diễn giải “pool chung” thành “không thể cancel task nào”; vẫn có thể hủy các **handles cụ thể**, nhưng phải hiểu đúng semantics của từng loại task.

## 15. Quan sát và đo lường common pool

Một số metric của `ForkJoinPool`:

| API | Ý nghĩa |
| --- | --- |
| `getCommonPoolParallelism()` | Target parallelism chung |
| `getParallelism()` | Target parallelism của instance |
| `getPoolSize()` | Số worker hiện có, dạng snapshot |
| `getActiveThreadCount()` | Ước lượng active worker count |
| `getRunningThreadCount()` | Ước lượng worker đang chạy hữu ích theo contract |
| `getQueuedTaskCount()` | Ước lượng số task trong work queues |
| `getQueuedSubmissionCount()` | Ước lượng external submissions chờ xử lý |
| `getStealCount()` | Ước lượng số work-steal operations |
| `isQuiescent()` | Quan sát pool có quiescent tại thời điểm đọc không |
| `toString()` | Trạng thái pool tóm tắt cho giám sát/debug |

Các giá trị này là observations/estimates, không tạo một **snapshot atomically consistent** của toàn bộ pool. `getQueuedTaskCount()==0` không chứng minh tasks của module bạn đều hoàn tất: chúng có thể đang chạy, chờ external resource, hoặc còn ở submission queue. Hãy chờ `join()`/`get()`/ack riêng của tasks thực tế.

### Chẩn đoán noisy neighbor

Cần tách:

- **Submission-to-start latency**: task đợi được schedule bao lâu?
- **Execution latency**: body chạy bao lâu?
- **End-to-end latency**: tính cả hai và chi phí khác.
- **CPU saturation**: có thực sự hết CPU, hay workers chủ yếu đang block?
- **GC/heap**: queued tasks có giữ object graph lớn?
- **Blocking time**: network, DB, lock, latch, Future wait.
- **Queued submissions/tasks và steal count**: có xu hướng backlog không?
- **Failures/cancellation/timeouts**: mất công việc hay task vô ích vẫn chạy?
- **Đồng thời nhiều modules**: peak của module A có trùng p99 tăng ở B không?

Không suy ra nguyên nhân từ một lần gọi `getActiveThreadCount()` hoặc `getStealCount()`; cần đo xu hướng, workload đại diện và các bottleneck khác.

## 16. Benchmark và kiểm thử đúng

- Trước hết kiểm tra **correctness** của thuật toán chia để trị và invariant của shared state.
- Dùng input đủ lớn và threshold hợp lý; với input quá nhỏ, overhead forks có thể áp đảo.
- Không benchmark bằng vài phép tính cực ngắn rồi khẳng định common pool “luôn nhanh hơn”.
- So sánh sequential, common pool và dedicated pool trên cùng workload, xem throughput, p95/p99 và CPU.
- Đo blocking, GC, queueing và downstream saturation cùng lúc.
- Test với nhiều modules cùng tải để đánh giá interference.
- Đừng giả định tên worker hoặc thứ tự log luôn cố định.
- Nếu test một blocking workload, dùng **pool riêng và timeout**, không cố chiếm hết common-pool workers của test suite.
- Đóng dedicated pool trong `finally` và `awaitTermination` có timeout để tránh để worker sống qua test.

### Một test có tính quyết định

Với `CommonPoolSum`, output `sum=36` là invariant; không cần đoán nhánh nào chạy trên worker nào. Với `SharedClientsDemo`, `results=AB` chỉ là cách ghép hai Future đã hoàn thành; không chứng minh lịch A-before-B.

Với cancellation, Future state và **body thực sự dừng** có thể khác nhau; nếu cần test tiến triển của body, dùng latch/ack riêng thay vì tin `isDone()` là đã cleanup.

## 17. Chọn common pool hay pool riêng?

### Dùng common pool khi

- Tác vụ thiên về CPU, tương đối ngắn và có thể chia nhỏ.
- Không có blocking I/O dài hoặc dependency cycles không kiểm soát.
- Không yêu cầu latency isolation nghiêm ngặt giữa modules.
- Không cần đóng executor riêng theo lifecycle component.
- Số lượng tác vụ và shared-memory invariants được thiết kế rõ.
- Đã đo dưới workload thật khi những thư viện khác cùng hoạt động.

### Cân nhắc pool riêng khi

- Một feature có SLA/p99 riêng và dễ bị noisy neighbor ảnh hưởng.
- Có blocking I/O hoặc cần concurrency limits theo downstream.
- Có nhiều recursive tasks và muốn điều chỉnh parallelism theo workload.
- Cần thread factory, monitoring, failure/rejection hoặc lifecycle riêng.
- Muốn chủ động shutdown/cancel những tasks của một module khi module dừng.
- Cần kiểm thử mà không ảnh hưởng resource toàn JVM.

**Lưu ý:** Một `ForkJoinPool` riêng phù hợp với work-stealing computation; khi workload là nhiều blocking I/O requests, có thể phù hợp hơn với `ThreadPoolExecutor` được sizing và bounded queue rõ ràng. “Pool riêng” cô lập công việc ở executor-level, không phải CPU/heap/DB độc lập.

## 18. Những hiểu nhầm thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “`commonPool()` tạo mới mỗi lần.” | Nhiều callers cùng nhận common pool instance |
| “Common pool tự tạo tài nguyên riêng cho mỗi thư viện.” | Có shared workers; noisy neighbors có thể xuất hiện |
| “Fork/Join là FIFO của task submits.” | Work stealing không cam kết thứ tự hoàn thành |
| “Fork/Join làm mọi object thread-safe.” | Shared mutable state vẫn cần synchronization |
| “Chia mỗi phần tử thành một ForkJoinTask luôn nhanh.” | Overhead và GC có thể lớn hơn công việc leaf |
| “CompletableFuture async luôn là common-pool thread.” | Có fallback khi parallelism không đủ; có explicit Executor |
| “Truyền executor vào stage đầu là cả pipeline đều dùng pool ấy.” | Continuations async không có executor có thể dùng default facility |
| “Parallel stream luôn nhanh.” | Workload nhỏ/blocking/stateful có thể chậm hoặc sai |
| “Work-stealing chắc chắn ngăn starvation.” | Blocking, dependency cycles và tài nguyên hữu hạn vẫn gây kẹt |
| “ManagedBlocker luôn mở thêm worker.” | Compensation chỉ là cơ chế có điều kiện, không có deadline guarantee |
| “`shutdown()` đóng common pool.” | Shutdown common pool không có hiệu lực theo contract |
| “`getQueuedTaskCount()==0` chứng minh xong.” | Có thể còn active tasks hoặc external submissions |
| “`cancel(true)` chắc ngắt ForkJoinTask.” | Default ForkJoinTask cancellation không dùng interruption như FutureTask |
| “Dedicated pool loại bỏ mọi ảnh hưởng lẫn nhau.” | CPU, heap, GC, I/O downstream vẫn dùng chung |
| “ThreadLocal caller tự có trong common worker.” | Không có context propagation tự động |
| “Mỗi request nên tạo một pool.” | Pool creation/destruction per request thường tốn kém và phá budget |

## 19. Câu hỏi tự kiểm tra

**Câu 1.** Hai modules cùng gọi `ForkJoinPool.commonPool()`. Chúng có nhận hai pools khác nhau không?  
**Đáp án:** Không, chúng dùng chung instance và có thể tranh workers.

**Câu 2.** `CompletableFuture.supplyAsync(supplier)` có luôn chạy trên common-pool worker không?  
**Đáp án:** Thông thường dùng common pool, nhưng Java 17 có fallback tạo Thread mới nếu common pool không hỗ trợ parallelism ít nhất 2.

**Câu 3.** Vì sao `left.fork(); right.compute(); left.join();` thường phù hợp hơn fork cả hai nhánh rồi chờ?  
**Đáp án:** Worker tự xử lý một nhánh, đồng thời cho nhánh kia cơ hội được steal, giảm overhead và chờ không cần thiết.

**Câu 4.** Một parallel stream gọi `forEach(out::add)` trên `ArrayList` shared. Có an toàn không?  
**Đáp án:** Không. Cần collector/reduction phù hợp hoặc synchronization.

**Câu 5.** Library A gửi nhiều blocking tasks vào common pool, module B chạy CPU computation qua common pool. B có thể chậm không?  
**Đáp án:** Có thể; workers/resources được chia sẻ và blocking gây giảm công suất.

**Câu 6.** `ForkJoinPool.managedBlock` có bảo đảm luôn tạo worker thay thế không?  
**Đáp án:** Không; compensation còn phụ thuộc điều kiện, giới hạn pool và OS.

**Câu 7.** Một component gọi `ForkJoinPool.commonPool().shutdown()` để tự dừng. Có đúng ownership không?  
**Đáp án:** Không. Common pool là shared resource; shutdown calls không có hiệu lực trên common pool theo API.

**Câu 8.** `ForkJoinTask.cancel(true)` có chắc gửi interrupt tới body đang chạy không?  
**Đáp án:** Không; implementation mặc định không dùng interrupt để điều khiển cancellation.

**Câu 9.** Một dedicated pool có làm JVM có thêm CPU cores không?  
**Đáp án:** Không. Chỉ cô lập executor-level workers/queues/lifecycle; CPU, memory và downstream vẫn chung.

**Câu 10.** `getQueuedTaskCount()==0` có chứng minh công việc của module xong chưa?  
**Đáp án:** Không. Cần chờ Future/ack cụ thể.

**Câu 11.** `thenApplyAsync(fn)` không có Executor sau `supplyAsync(..., ownPool)` có thể chạy ở đâu?  
**Đáp án:** Nó có thể dùng default async facility, thường common pool; hãy truyền executor cho continuation khi cần isolation.

**Câu 12.** Có thể xác minh correctness của `CommonPoolSum` qua thứ tự log các nhánh không?  
**Đáp án:** Không nên. Xác minh tổng `36` và các invariant thay vì phụ thuộc scheduler.

## Tài liệu tham khảo Java SE 17

- [`ForkJoinPool`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ForkJoinPool.html): work-stealing, `commonPool`, parallelism, managed blocking, monitoring và lifecycle.
- [`ForkJoinTask`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ForkJoinTask.html): `fork`, `join`, `invoke`, cancellation semantics.
- [`RecursiveTask`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/RecursiveTask.html): tác vụ đệ quy trả kết quả.
- [`CompletableFuture`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): default async executor, overload truyền Executor và cancellation.
- [`ExecutorService`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): submit, Future và lifecycle.
- [`Future`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): kết quả, completion và cancellation.
- [Stream package](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/package-summary.html): parallel stream, stateless behavior, reductions.
- [`ThreadLocal`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ThreadLocal.html): ngữ nghĩa per-thread context.
- [Java Language Specification `17](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): synchronization và happens-before.

**Ghi nhớ:** `ForkJoinPool.commonPool()` giảm chi phí tạo pool riêng cho công việc Fork/Join thích hợp, nhưng mang theo **shared-resource interference**. Hãy hiểu API nào có thể sử dụng pool chung, tránh blocking dài trong shared workers, quản lý Future/task của chính mình và chuyển sang executor riêng nếu cần isolation, tuning hoặc shutdown độc lập.