# CPU-bound workload không tự nhanh hơn nhờ virtual threads

## Mục tiêu bài học

Sau bài này, bạn có thể:

- Giải thích vì sao **virtual thread** tiết kiệm chi phí giữ thread khi chờ nhưng **không làm một phép tính CPU chạy nhanh hơn**.
- Phân biệt **concurrency** (nhiều công việc cùng tồn tại và tiến triển) với **parallelism** (thực sự tính toán đồng thời trên nhiều bộ xử lý).
- Hiểu quan hệ giữa virtual threads, carrier/platform threads, CPU cores, hàng đợi công việc, mức song song và throughput.
- Chọn chiến lược hợp lý cho tác vụ thuần CPU, tác vụ thường xuyên chờ I/O và workload pha trộn.
- Viết ví dụ Java 21+ để kiểm tra kết quả, đo hiệu năng cẩn thận và nhận diện các bẫy benchmark.

Bài học chỉ sử dụng Java SE và các khái niệm concurrency của JVM.

## 1. Virtual threads giải quyết vấn đề gì?

Java 21 đưa **virtual threads** thành tính năng chính thức. Chúng vẫn là `java.lang.Thread`, nhưng được JVM quản lý nhẹ hơn và không sở hữu một OS thread cố định trong toàn bộ vòng đời. Một platform thread thường gắn với một OS thread. Khi virtual thread thực hiện thao tác chờ tương thích với cơ chế của JVM, nó có thể **unmount** khỏi carrier thread; carrier được dùng để chạy virtual thread khác.

Khái niệm thiết yếu:

| Thuật ngữ | Ý nghĩa |
| --- | --- |
| **Virtual thread** | Luồng nhẹ do JVM lập lịch, phù hợp việc có nhiều tác vụ độc lập thường bị chặn để chờ. |
| **Carrier thread** | Platform thread hiện đang thực thi mã Java của một virtual thread khi virtual thread được mount. |
| **Mount / unmount** | Gắn virtual thread lên carrier để chạy / tạm tách ra trong những thao tác chờ được hỗ trợ. |
| **CPU-bound** | Phần lớn thời gian thực sự tiêu thụ CPU để tính toán, ví dụ tính hash hàng loạt, biến đổi dữ liệu, nén, thuật toán số. |
| **I/O-bound / blocking-heavy** | Phần lớn thời gian chờ socket, cơ sở dữ liệu, tệp hoặc thao tác chặn khác; CPU không tính toán liên tục trong lúc đợi. |
| **Throughput** | Số tác vụ hoàn thành trên một đơn vị thời gian. |
| **Latency** | Thời gian một tác vụ mất từ lúc bắt đầu yêu cầu đến khi hoàn tất; có thể bao gồm cả thời gian xếp hàng. |

**Virtual threads là công cụ mở rộng khả năng phục vụ nhiều tác vụ đang chờ; chúng không phải phiên bản chạy phép cộng, phép nhân, mã hóa hoặc tính toán nhanh hơn của platform threads.** Khi một virtual thread bận thực hiện vòng lặp tính toán, nó vẫn phải chạy trên một carrier, và carrier vẫn dùng một luồng CPU thực tế.

### Concurrency khác parallelism

Giả sử máy có 4 logical processors:

~~~text
100 virtual threads CPU-bound được tạo ra
        |
        v
JVM scheduler sắp lịch chạy trên các carrier
        |
        v
CPU 0 | CPU 1 | CPU 2 | CPU 3
        |
        v
Chỉ một số công việc có thể thực thi CPU thực sự tại cùng một thời điểm.
Những công việc còn lại phải chờ đến lượt hoặc chia sẻ CPU.
~~~

Hình trên minh họa giới hạn năng lực CPU; số carrier thực tế và cách JVM lập lịch phụ thuộc phiên bản JVM, cấu hình scheduler, môi trường container và hành vi blocking. `Runtime.getRuntime().availableProcessors()` cung cấp số logical processors mà JVM thấy; nó không phải bảo đảm số phép tính luôn chạy song song hiệu quả.

- **Concurrency:** có 100 tác vụ được quản lý cùng lúc.
- **Parallelism:** nếu chỉ có 4 logical processors sẵn có, không thể biến 100 tác vụ thuần CPU thành 100 phép tính thực sự diễn ra đồng thời chỉ nhờ đổi loại thread.
- **I/O waiting:** khi 96 tác vụ đang chờ I/O, một số virtual threads khác có thể tiếp tục chạy bằng carrier được giải phóng. Đây là lợi ích rất khác với gia tốc phép tính.

Câu hỏi cần đặt là **“tác vụ đang tốn thời gian tính toán hay đang tốn thời gian chờ?”**, chứ không đơn thuần “số thread hiện có là bao nhiêu?”.

## 2. Tại sao CPU-bound không tự tăng tốc?

### 2.1. Vẫn chịu giới hạn tài nguyên tính toán

Một phép tính CPU thuần phải thực hiện số lượng phép toán nhất định. Virtual thread và platform thread đều sử dụng cùng CPU, cache, băng thông bộ nhớ và các đơn vị thực thi. Chuyển từ:

~~~java
executor.submit(this::calculate);
~~~

sang:

~~~java
Thread.startVirtualThread(this::calculate);
~~~

không thay đổi độ phức tạp thuật toán của `calculate()`, không tăng số lõi CPU và không tự động vector hóa phép tính. Cả hai đoạn là mã minh họa; `executor` và `calculate()` phải được khai báo trong chương trình thực tế.

Nếu chỉ có **một** tác vụ CPU-bound chạy trên một logical processor, việc tạo thêm virtual threads không làm **chính tác vụ đó** chia thành nhiều phần độc lập. Muốn tận dụng nhiều lõi, cần chia bài toán theo dữ liệu hoặc tác vụ, xử lý đồng thời và kết hợp kết quả đúng cách.

### 2.2. Virtual thread không phải CPU worker “miễn phí”

Khi một virtual thread tính toán mà không chặn, nó giữ carrier suốt đoạn chạy đó (cho đến khi hoàn tất hoặc tới điểm chuyển trạng thái phù hợp). Các virtual threads khác cần CPU vẫn phải được lập lịch. Tạo hàng nghìn virtual threads để tính toán đồng thời:

- Không tăng tổng năng lực CPU vật lý.
- Có thể thêm chi phí tạo task, chuyển ngữ cảnh, quản lý đối tượng và bộ nhớ.
- Có thể làm tăng tranh chấp cache/băng thông, lock hoặc chi phí GC.
- Không bảo đảm giảm thời gian của từng task; thậm chí tăng latency vì nhiều task tranh cùng CPU.

**Chú ý:** không nên kết luận mọi workload CPU-bound chạy trên virtual threads đều chậm hơn. Nếu so với một triển khai platform thread trước đây bị giới hạn quá thấp, chương trình mới có thể nhanh hơn do **mức parallelism tăng**. Đó là lợi ích của việc dùng thêm CPU còn rảnh, không phải vì một virtual thread thực thi mã CPU nhanh hơn. Để so sánh công bằng, phải xem xét cùng công việc và mức song song thực tế.

### 2.3. Giới hạn bởi phần tuần tự và tài nguyên chung

Ngay cả chương trình có thể dùng nhiều lõi, tốc độ tối đa vẫn bị phần tuần tự, thao tác đồng bộ, bộ nhớ và truyền dữ liệu giới hạn. Theo **định luật Amdahl**, nếu phần tuần tự chiếm tỷ lệ `s` và phần còn lại có thể song song trên `p` bộ xử lý:

\[
S(p) \leq \frac{1}{s+\frac{1-s}{p}}
\]

Ví dụ nếu 20% thời gian không thể song song hóa (`s = 0,2`), ngay cả khi số bộ xử lý tăng rất lớn thì speedup lý tưởng cũng không vượt `1 / 0,2 = 5` lần; các chi phí phối hợp thực tế còn khiến kết quả thấp hơn. Việc dùng virtual threads không xóa bỏ phần tuần tự này.

## 3. Ví dụ chạy được: cùng bài toán CPU trên hai loại executor

Chương trình đếm số nguyên tố nhỏ hơn 1.000.000 bằng 100 task độc lập, mỗi task xử lý một khoảng 10.000 số:

- Cách A: `Executors.newFixedThreadPool(...)` với số worker gần mức CPU mà JVM quan sát.
- Cách B: `Executors.newVirtualThreadPerTaskExecutor()`, mỗi task dùng một virtual thread.
- Cả hai thực hiện **cùng phép tính** và phải trả về **cùng kết quả**.
- Thời gian đo một lần chỉ để quan sát. Không được xem đây là kết luận benchmark vì JVM cần warm-up, JIT, CPU có thể thay đổi xung/khối lượng công việc và hệ điều hành có lịch chạy khác nhau.

Tạo tệp `CpuWorkloadDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class CpuWorkloadDemo {
    private static final int LIMIT = 1_000_000;
    private static final int CHUNK = 10_000;

    public static void main(String[] args) throws Exception {
        int cpuCount = Runtime.getRuntime().availableProcessors();
        int fixedWorkers = Math.max(1, Math.min(cpuCount, LIMIT / CHUNK));

        long beginFixed = System.nanoTime();
        int fixedCount;
        try (ExecutorService pool = Executors.newFixedThreadPool(fixedWorkers)) {
            fixedCount = countAll(pool);
        }
        long fixedMillis = TimeUnit.NANOSECONDS.toMillis(
                System.nanoTime() - beginFixed);

        long beginVirtual = System.nanoTime();
        int virtualCount;
        try (ExecutorService pool = Executors.newVirtualThreadPerTaskExecutor()) {
            virtualCount = countAll(pool);
        }
        long virtualMillis = TimeUnit.NANOSECONDS.toMillis(
                System.nanoTime() - beginVirtual);

        System.out.println("Platform pool: " + fixedCount + " primes");
        System.out.println("Virtual threads: " + virtualCount + " primes");
        System.out.println("Equal results: " + (fixedCount == virtualCount));
        System.out.printf("Measured times (ms): fixed=%d, virtual=%d%n",
                fixedMillis, virtualMillis);
    }

    private static int countAll(ExecutorService pool) throws Exception {
        List<Future<Integer>> results = new ArrayList<>();
        for (int from = 0; from < LIMIT; from += CHUNK) {
            final int low = from;
            final int high = Math.min(from + CHUNK, LIMIT);
            results.add(pool.submit(() -> countPrimes(low, high)));
        }
        int count = 0;
        for (Future<Integer> result : results) {
            count += result.get();
        }
        return count;
    }

    private static int countPrimes(int low, int high) {
        int count = 0;
        for (int n = low; n < high; n++) {
            if (isPrime(n)) {
                count++;
            }
        }
        return count;
    }

    private static boolean isPrime(int n) {
        if (n < 2) return false;
        for (int divisor = 2; divisor * divisor <= n; divisor++) {
            if (n % divisor == 0) return false;
        }
        return true;
    }
}
~~~

Biên dịch và chạy bằng **JDK 21 trở lên** (virtual threads là tính năng chính thức từ Java 21):

~~~bash
javac --release 21 CpuWorkloadDemo.java
java CpuWorkloadDemo
~~~

Ba dòng đầu ra cố định:

~~~text
Platform pool: 78498 primes
Virtual threads: 78498 primes
Equal results: true
~~~

Dòng cuối có dạng `Measured times (ms): fixed=<số đo>, virtual=<số đo>`; hai số thay đổi theo máy và lần chạy. Đây là phép kiểm tra chức năng đồng thời giới thiệu cách ghi nhận thời gian, **không** đủ để công bố tốc độ của hai mô hình.

**Phân tích:**

1. `countPrimes(low, high)` là tác vụ CPU-bound, không cố ý chờ network/file/lock.
2. `countAll` submit toàn bộ 100 task, rồi lấy các `Future`; vì `get()` nằm ở thread điều phối `main`, không có worker nào phải chờ task con trên chính pool của nó.
3. Pool platform cố định dùng số worker không lớn hơn số CPU logic (và không lớn hơn số task); virtual-thread-per-task executor cấp một virtual thread cho mỗi task.
4. Cả hai phải trả 78.498; nếu khác, trước tiên kiểm tra lỗi tính toán/partition, chưa bàn tốc độ.
5. Nếu một lần chạy virtual nhanh hơn hoặc chậm hơn, có thể do JVM warm-up, JIT compilation, GC, số worker, chi phí tạo executor, thermal throttling hoặc tác vụ quá nhỏ. Thứ tự “fixed chạy trước, virtual chạy sau” cũng tạo thiên lệch vì đoạn code đã được JVM tối ưu dần ở lần chạy thứ hai.

### Bài toán chia nhỏ đến mức nào?

Chia một triệu phần tử thành một triệu task cực nhỏ có thể tạo nhiều chi phí quản lý hơn là thời gian tính toán hữu ích. Ngược lại, chỉ chia thành một task sẽ không dùng hết nhiều CPU. Chọn **granularity** dựa trên kích thước công việc, chi phí chia/gộp, bộ nhớ và throughput đo được. Với CPU-bound, mô hình **bounded parallelism** (số worker hợp lý, các task đủ lớn) thường là điểm xuất phát có thể dự đoán được.

## 4. Khi nào virtual threads thật sự có lợi? Tác vụ thường xuyên phải chờ

Giả sử 24 yêu cầu độc lập, mỗi yêu cầu cần chờ 200 ms (ví dụ tượng trưng cho một thao tác I/O). Với pool gồm 4 platform threads, thường phải xử lý thành nhiều đợt vì mỗi thread bị giữ trong lúc chờ. Với virtual threads, khi `Thread.sleep` park virtual thread, carrier có thể dùng cho công việc khác.

Đây là **mô phỏng thời gian chờ**, không phải phép đo mạng hay cơ sở dữ liệu thật. Tạo `WaitingWorkloadDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class WaitingWorkloadDemo {
    private static final int TASK_COUNT = 24;

    public static void main(String[] args) throws Exception {
        long fixed = run(Executors.newFixedThreadPool(4));
        long virtual = run(Executors.newVirtualThreadPerTaskExecutor());

        System.out.printf("Measured times (ms): fixed=%d, virtual=%d%n",
                fixed, virtual);
    }

    private static long run(ExecutorService pool) throws Exception {
        long start = System.nanoTime();
        try (pool) {
            List<Callable<Integer>> tasks = new ArrayList<>();
            for (int i = 0; i < TASK_COUNT; i++) {
                tasks.add(() -> {
                    Thread.sleep(200);
                    return 1;
                });
            }
            List<Future<Integer>> futures = pool.invokeAll(tasks);
            int total = 0;
            for (Future<Integer> future : futures) {
                total += future.get();
            }
            System.out.println("Completed: " + total);
        }
        return TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - start);
    }
}
~~~

Chạy:

~~~bash
javac --release 21 WaitingWorkloadDemo.java
java WaitingWorkloadDemo
~~~

Hai dòng có kết quả cố định là:

~~~text
Completed: 24
Completed: 24
~~~

Dòng thứ ba in thời gian thực tế, thay đổi theo môi trường. Trong điều kiện ít tải, pool 4 platform workers thường cần khoảng 6 đợt chờ 200 ms (xấp xỉ 1,2 giây cộng overhead), còn virtual threads có thể cùng chờ và hoàn thành gần một đợt (xấp xỉ 200 ms cộng overhead). Đây là **lợi ích về khả năng đồng thời khi chờ**, không chứng minh virtual threads tính CPU nhanh hơn.

**Giới hạn thực tế:** kết nối mạng, connection pool, API rate limit và database không thể nhận số request vô hạn. Nếu tăng concurrency quá cao, hệ thống bên ngoài có thể nghẽn, timeout hoặc tăng latency. Dùng virtual threads không bỏ qua các giới hạn nghiệp vụ và tài nguyên.

## 5. Vì sao một bài đo CPU thấy virtual threads nhanh hơn?

Một kết quả như “virtual nhanh hơn 3 lần trong lần chạy đầu” cần được giải thích trước khi kết luận. Hãy kiểm tra:

| Hiện tượng | Câu hỏi cần xác minh |
| --- | --- |
| Đổi mã nguồn cùng lúc với đổi loại thread | Hai phiên bản có dùng cùng thuật toán, dữ liệu, chia task, thiết lập JVM và kết quả không? |
| Pool cũ chỉ 1–2 workers nhưng máy có nhiều lõi | Tốc độ tăng do sử dụng thêm CPU hay do virtual thread? |
| Fixed chạy trước, virtual chạy sau | JIT compilation, class loading, allocation và warm-up có tạo lợi thế cho lượt chạy sau không? |
| Bài toán quá nhỏ | Overhead tạo executor, Future, submit có lấn át tính toán không? |
| Máy đang có tải khác | Background processes, CPU frequency, GC, container quota có khác nhau không? |
| Một số task chờ disk/network/lock | Workload có thực sự CPU-bound hay đang pha trộn blocking? |
| Dùng “thời gian tạo hết thread” làm chuẩn | Bài đo có đợi **toàn bộ task hoàn tất** hay chỉ đo thời gian submit? |
| Đo tổng throughput nhưng so sánh độ trễ một task | Đang tối ưu chỉ số nào, và có tính cả thời gian queue không? |

Ví dụ, nếu một chương trình ban đầu dùng `newFixedThreadPool(1)` trên máy 8 lõi, sau đó chuyển sang nhiều virtual threads, throughput CPU có thể tăng đáng kể vì lúc trước chỉ dùng một lõi. Để phân tích nguyên nhân, hãy so sánh thêm với **platform thread pool có mức song song phù hợp**. Khi đó lợi thế chỉ do tạo ra nhiều logical threads sẽ không còn là lời giải thích đủ.

### Benchmark hợp lý cần làm gì?

- Sử dụng **JMH (Java Microbenchmark Harness)** khi đo vi mô, để xử lý warm-up, iteration/fork và tránh nhiều lỗi đo JVM. Không xem phép đo dùng `System.nanoTime()` một lần là benchmark kết luận.
- Đảm bảo chương trình thực sự sử dụng kết quả tính toán, không để JIT loại bỏ công việc không cần thiết.
- Thử các mức kích thước task, số tác vụ và mức CPU parallelism; ghi rõ JDK, số logical processors, container CPU quota và giới hạn bộ nhớ.
- Kiểm tra **CPU utilization**, throughput (task/giây), p50/p95/p99 latency, bộ nhớ/GC, chi phí scheduling và thời gian chờ.
- Cho mỗi cấu hình chạy nhiều iteration sau warm-up, thay đổi thứ tự chạy hoặc chạy trong các fork riêng, công bố độ phân tán kết quả.
- Đo đúng mục tiêu: một tác vụ CPU độc lập cần giảm latency, tổng lô CPU cần tăng throughput hay một dịch vụ pha trộn cần chịu nhiều kết nối đồng thời?

`jcmd`, Java Flight Recorder và Java Mission Control giúp quan sát thread states, CPU samples, allocation và blocking. Đọc dữ liệu đo cùng nhau: ví dụ CPU đã gần bão hòa mà hàng đợi tăng thì tăng thêm virtual threads khó có thể giảm phần tính toán CPU.

## 6. Lựa chọn executor phù hợp theo workload

| Loại công việc | Điểm xuất phát hợp lý | Vì sao |
| --- | --- | --- |
| Ít task, mỗi task tính CPU nặng | Xử lý trực tiếp hoặc pool platform kích thước phù hợp số CPU | Tận dụng CPU có giới hạn, ít overhead chia task. |
| Nhiều khối CPU độc lập có thể chia đều | Fixed thread pool / `ForkJoinPool` / parallel algorithm khi phù hợp | Kiểm soát mức parallelism, work-stealing với thuật toán chia nhỏ phù hợp. |
| Nhiều request chủ yếu chờ I/O | Virtual thread per task executor | Worker hệ điều hành không phải bị chiếm suốt thời gian chờ tương thích. |
| Task pha trộn CPU và I/O | Đo profile, tách phần blocking và phần tính toán hoặc giới hạn CPU work | Tránh việc tăng số task đang chờ đẩy CPU vào overload. |
| Phụ thuộc dịch vụ ngoài có quota/connection pool | Virtual threads + giới hạn concurrency/queue hoặc backpressure | Virtual threads không tăng sức chứa của dịch vụ ngoài. |
| Một phép tính tuần tự đơn lẻ | Tối ưu thuật toán, dữ liệu hoặc chia bài toán đúng cách | Chỉ đổi thread type không tạo ra parallel algorithm. |

### Chọn số lượng CPU worker

`Runtime.getRuntime().availableProcessors()` là **điểm bắt đầu** để đo, không phải công thức tối ưu bất biến. Workload dùng CPU cache/memory bandwidth, SMT/hyper-threading và giới hạn CPU của container có thể làm mức worker hiệu quả khác số logical processors. Pool platform cố định cho CPU-bound giúp giới hạn lượng task hoạt động; task vượt số worker có thể chờ trong hàng đợi. Với công việc tính toán có thể chia nhỏ một cách đệ quy, `ForkJoinPool` có thể thích hợp nhưng cũng cần profile vì một thuật toán chia việc kém vẫn gây overhead.

### Đừng dùng virtual threads như CPU pool tự động

`Executors.newVirtualThreadPerTaskExecutor()` tạo một virtual thread mới cho mỗi task; nó **không cố giới hạn số virtual threads theo CPU**. Với CPU-bound, gửi hàng triệu task nhỏ có thể tạo hàng triệu đối tượng, Future, metadata và kết quả chờ, ngay cả khi chỉ một phần đang chạy trên CPU.

Không nên xây “pool các virtual threads” như cách tái sử dụng platform threads; điểm mạnh của virtual threads là rẻ khi tạo theo task. Nhưng **rẻ không đồng nghĩa miễn phí**. Khi nguồn dữ liệu rất lớn, hãy giới hạn số task được tạo đồng thời từ phía producer, chia batch, hoặc dùng bounded executor phù hợp thay vì submit vô hạn. Với tác vụ I/O, giới hạn concurrency theo tài nguyên ngoài bằng `Semaphore`, connection pool và rate limiting; đừng dùng số virtual threads làm đại diện cho capacity của backend.

## 7. Điều xảy ra trong scheduler và ảnh hưởng của pinning

Virtual threads được JVM lập lịch trên các carrier platform threads. Khi virtual thread chạy mã CPU không chặn, nó vẫn chiếm carrier trong khoảng thời gian chạy đó. Khi gặp thao tác blocking được JVM hỗ trợ để unmount, carrier có thể rảnh để làm việc khác. Scheduler của virtual threads thường có mức parallelism mục tiêu liên quan số processor, nhưng đây không phải cam kết rằng mọi virtual thread đang tồn tại đều chạy song song, cũng không có “một CPU riêng cho mỗi virtual thread”.

**Pinning** là khi virtual thread không thể unmount khỏi carrier trong một thao tác chờ nhất định; carrier tiếp tục bị giữ, có thể làm giảm khả năng mở rộng của workload blocking:

- **JDK 21–23:** thao tác blocking trong vùng `synchronized` có thể gây pinning carrier; native/foreign code cũng có những tình huống pinning.
- **JDK 24 trở lên:** JEP 491 thay đổi cơ chế monitor để blocking bên trong `synchronized` không còn là nguyên nhân pinning thông thường; vẫn còn những trường hợp liên quan native/foreign interaction cần quan sát.
- Với cả hai giai đoạn, **mã CPU-bound không cần unmount** vì nó đang dùng CPU để tính; sửa pinning không làm phép tính tự thực thi nhanh hơn.

Không chọn API dựa trên mẹo “thay mọi `synchronized` bằng `ReentrantLock`” áp dụng cho mọi phiên bản. Phân tích theo JDK thực tế và đo bằng JFR khi có vấn đề. Tránh nhầm giữa **pinning**, **lock contention**, **CPU saturation** và **thread starvation**: đó là những nguyên nhân khác nhau, dù đều có thể gây giảm throughput.

## 8. Bảo vệ tính đúng và tài nguyên khi dùng concurrency lớn

Khi chia bài toán ra nhiều task, loại thread không giải quyết các rủi ro thông thường:

- **Race condition / data race:** mỗi task cập nhật chung một bộ đếm không đồng bộ có thể mất kết quả. Trong ví dụ, mỗi task trả `Integer` riêng và thread điều phối cộng các kết quả để tránh ghi chung.
- **Overhead phối hợp:** hàng chục nghìn task nhỏ có thể dành nhiều thời gian cho submit, Future và queue hơn cho công việc tính toán.
- **Unbounded fan-out:** tạo quá nhiều task đồng thời có thể dùng nhiều heap/metadata; cần kiểm soát lượng work-in-flight ở producer.
- **Blocking trong CPU pool:** một task CPU worker lại chờ Future/task con từ chính pool đã bão hòa có thể gây thread-starvation deadlock. Dùng composition hoặc đợi ở thread điều phối bên ngoài pool.
- **Cancellation:** `Future.cancel(true)` gửi tín hiệu interrupt, không cưỡng ép mã CPU đang phớt lờ interrupt dừng ngay. Tác vụ dài nên chủ động kiểm tra tín hiệu dừng tại điểm phù hợp và dọn tài nguyên trong `finally`.
- **ThreadLocal:** mỗi virtual thread có thể có biến `ThreadLocal`, nhưng nếu tạo rất nhiều virtual threads thì dùng nó làm nơi cache đối tượng đắt tiền theo thread có thể phình bộ nhớ, khác mô hình platform thread pool tái sử dụng ít worker.
- **Observability:** luôn đo kết quả đúng, thời gian hoàn tất, CPU và độ dài queue; một dòng log “started 100k threads” không cho biết công việc được xử lý nhanh hay chậm.

`ExecutorService` hỗ trợ `close()` khi dùng try-with-resources trên Java 21+, giúp đợi task hoàn tất khi đóng trong các demo. Ứng dụng thực tế vẫn cần chính sách timeout, ngắt, backpressure và lifecycle phù hợp; một tác vụ treo có thể khiến chương trình chờ đóng executor lâu hơn dự kiến.

## 9. Bài tập thực hành và cách đọc kết quả

**Bài 1 — Giữ nguyên loại thread, thay mức song song.** Chạy `CpuWorkloadDemo` với platform pool lần lượt 1, 2, 4, 8 workers (theo giới hạn môi trường). Quan sát tốc độ tăng có ngừng khi tới giới hạn CPU hay không; đối chiếu kết quả đếm luôn là 78.498.

**Bài 2 — Thay kích thước task.** Trong `CpuWorkloadDemo`, thử `CHUNK` bằng 1.000, 10.000, 100.000. Theo dõi số task, chi phí submit/gộp và khả năng phân phối công việc; giải thích vì sao rất nhỏ và rất lớn đều có thể kém.

**Bài 3 — Đổi chờ thành tính.** Trong `WaitingWorkloadDemo`, thay `Thread.sleep(200)` bằng một công đoạn tính CPU đủ nặng và vẫn trả về kết quả. Quan sát lợi ích về thời gian biến đổi như thế nào. Không so sánh bằng một lượt chạy; lập quy trình warm-up và đo nhiều lượt.

**Bài 4 — Phát hiện benchmark sai.** Xem một phép đo chỉ tính thời gian gọi `submit` nhưng không `get` hoặc `awaitTermination`. Hãy chỉ ra nó đang đo **thời gian gửi task**, không đo thời gian hoàn thành công việc. Sửa để có điểm hoàn tất rõ ràng, cùng input và checksum.

**Bài 5 — Đánh giá hệ thống pha trộn.** Giả sử một task đọc dữ liệu 300 ms rồi tính CPU 50 ms. Hãy nêu vì sao virtual threads có thể cải thiện concurrency khi đợi dữ liệu nhưng không làm phần CPU 50 ms chạy nhanh hơn; đề xuất giới hạn kết nối và CPU work-in-flight.

Khi thực hành, có thể quan sát hiện tượng trái với trực giác ở một lần chạy vì hệ điều hành và JIT không cố định. Hãy giải thích bằng tài nguyên thực tế, dữ liệu đo và kết quả đúng trước khi thay executor.

## 10. Tổng hợp để áp dụng

1. **Tập trung vào điểm nghẽn:** mã đang tính CPU hay đang chờ? Nếu là CPU, thay thread type không tạo thêm lõi và không làm thuật toán nhanh hơn.
2. **Với CPU-bound:** ưu tiên chia việc đúng, thuật toán phù hợp, bounded parallelism và benchmark có warm-up; kích thước thread pool thường bắt đầu từ số CPU mà JVM thấy rồi hiệu chỉnh theo phép đo.
3. **Với blocking-heavy:** virtual threads là lựa chọn rất hữu ích để phục vụ nhiều tác vụ đang chờ mà không phải giữ nhiều platform threads.
4. **Với workload pha trộn:** phân tích cả CPU, I/O, queue, backend capacity và latency; mở rộng số virtual threads phải đi cùng giới hạn tài nguyên ngoài.
5. **Không đọc một kết quả benchmark đơn lẻ thành quy luật:** cùng input, cùng công việc, cùng điều kiện, đủ warm-up và kết quả đo nhiều lần mới có cơ sở đánh giá.

**Thông điệp chính:** virtual threads làm việc quản lý **nhiều tác vụ đồng thời, đặc biệt là tác vụ chờ**, trở nên rẻ hơn. Một tác vụ **CPU-bound** vẫn phải tiêu thụ tài nguyên CPU thật; muốn nhanh hơn cần cải thiện thuật toán, song song hóa hợp lý hoặc thêm năng lực xử lý thực tế.

### Tài liệu Java tham khảo

- [JEP 444 — Virtual Threads](https://openjdk.org/jeps/444): mục tiêu thiết kế, giới hạn và cách dùng virtual threads.
- [Oracle Java 21 — Virtual Threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html): cơ chế mount/unmount, thread-per-task, trường hợp blocking phù hợp.
- [JEP 491 — Synchronize Virtual Threads without Pinning](https://openjdk.org/jeps/491): thay đổi cơ chế monitor từ Java 24.
- [JMH](https://openjdk.org/projects/code-tools/jmh/): công cụ benchmark hiệu năng vi mô cho JVM.