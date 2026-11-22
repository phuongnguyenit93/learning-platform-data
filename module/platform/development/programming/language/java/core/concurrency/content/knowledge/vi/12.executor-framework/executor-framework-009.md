# Lựa chọn pool size cho CPU-bound và I/O-bound trong Java

## 1. Vì sao pool size là một quyết định về năng lực hệ thống?

Trong Executor Framework, thread pool tái sử dụng các worker thread để xử lý nhiều tác vụ. Số worker ảnh hưởng trực tiếp đến **throughput** (số tác vụ hoàn thành mỗi giây), **latency** (thời gian đáp ứng), mức sử dụng CPU, bộ nhớ, chuyển ngữ cảnh và hàng đợi chờ.

- **Quá ít thread:** CPU có thể nhàn rỗi khi worker đang chờ I/O; tác vụ phải xếp hàng dù hệ thống còn khả năng xử lý.
- **Quá nhiều thread:** tác vụ CPU tranh nhau cùng lõi xử lý, tăng context switching, bộ nhớ stack, GC và tranh chấp lock. Với I/O, quá nhiều request đồng thời còn có thể làm nghẽn connection pool, database hoặc dịch vụ phía sau.
- **Đúng kích thước:** giữ tài nguyên có ích luôn bận ở mức mục tiêu, đồng thời khống chế hàng đợi và giới hạn năng lực của các phụ thuộc.

**Không có một con số pool size tốt cho mọi ứng dụng.** Công thức chỉ là điểm khởi đầu. Giá trị cuối cùng phải được kiểm chứng bằng tải đại diện, mức CPU được cấp, hành vi blocking, độ trễ và giới hạn downstream.

## 2. Nhận diện bản chất tác vụ

| Đặc điểm | CPU-bound | I/O-bound |
|---|---|---|
| Phần lớn thời gian | Đang thực thi tính toán trên CPU | Chờ đọc/ghi file, network, JDBC, remote service... |
| Nút thắt thông thường | Số lõi CPU và chi phí điều phối | Độ trễ I/O và giới hạn tài nguyên bên ngoài |
| Tăng thread vượt ngưỡng | Ít tăng throughput, có thể chậm hơn | Có thể che giấu thời gian chờ, đến khi chạm giới hạn khác |
| Ví dụ | Nén dữ liệu, tính toán hash, biến đổi ảnh, tính toán số học | Đọc file blocking, gọi HTTP blocking, truy vấn JDBC, chờ socket |

Một tác vụ có thể **mixed workload**: parse JSON bằng CPU, gọi dịch vụ qua mạng, rồi xử lý dữ liệu tiếp. Hãy đo phần **thực thi CPU** và phần **đợi** trong cùng vòng đời tác vụ, thay vì gắn nhãn theo tên phương thức. Một lệnh truy vấn database vừa tốn CPU tại server vừa khiến thread Java phía client chờ I/O; hai nguồn lực đó phải được đánh giá riêng.

Phân biệt thêm:

- **Blocking:** worker thread bị chiếm trong lúc đợi, ví dụ Thread.sleep, blocking socket read hoặc Future.get. Thread đó không chạy tác vụ khác.
- **Non-blocking/asynchronous I/O:** thread có thể phục vụ công việc khác khi I/O chưa hoàn thành. Không được áp nguyên công thức của blocking thread pool cho event loop.
- **Lock contention:** thread chờ monitor/lock không dùng CPU hữu ích nhưng tăng số worker chưa chắc giúp ích; trước hết kiểm tra nguyên nhân tranh chấp.

## 3. CPU-bound: bắt đầu gần số CPU thực sự có

Gọi **N** là số logical processor hiệu dụng mà tiến trình Java được phép sử dụng, **U** là mục tiêu sử dụng CPU (0–1), và **P** là số worker chạy tác vụ tính toán độc lập. Một điểm xuất phát thường dùng là:

**P ≈ N × U**, sau đó đo và điều chỉnh, thường kiểm thử quanh **N** worker.

Ví dụ tiến trình thực sự có thể dùng 8 logical CPU, mục tiêu CPU khoảng 80–90% thì thử khoảng 6–8 worker tính toán. Đây là **phạm vi thử nghiệm**, không phải quy tắc làm tròn bắt buộc; CPU còn phục vụ GC, runtime, các luồng khác và dịch vụ cùng máy.

Nếu toàn bộ tác vụ luôn runnable và tiêu thụ CPU, tăng từ 8 lên 80 worker trên máy chỉ có năng lực 8 logical CPU không tạo thêm tài nguyên CPU. Nó thường làm tăng run queue, context switching và cạnh tranh cache, trong khi throughput bão hòa.

**Cẩn thận khi xác định N:**

1. Runtime.getRuntime().availableProcessors() là tín hiệu tiện dùng, nhưng cần đối chiếu với CPU quota/cpuset của container, cấu hình JVM và số CPU thực sự được phân bổ. Giới hạn CPU thực tế có thể khác CPU vật lý của host; phiên bản JVM và cấu hình container awareness cũng ảnh hưởng số trả về.
2. Logical CPU từ SMT/Hyper-Threading không đồng nghĩa từng CPU có năng lực của một core vật lý độc lập. Hãy benchmark tác vụ thật.
3. Nếu nhiều pool CPU-bound cùng dùng chung JVM, không phân bổ **N worker chạy kín CPU cho từng pool** như thể mỗi pool có N lõi riêng.
4. Công việc có synchronized, JNI, cấp phát/GC nặng hoặc truy cập bộ nhớ thường không scale tuyến tính với số thread; kiểm tra profile để tìm giới hạn thực.

## 4. I/O-bound dạng blocking: tính cả thời gian chờ

Đặt:

- **N:** năng lực CPU hiệu dụng.
- **U:** mức sử dụng CPU mục tiêu, ví dụ 0,8.
- **C:** thời gian CPU mà một tác vụ tiêu thụ trung bình.
- **W:** tổng thời gian tác vụ **không tiêu thụ CPU hữu ích** trong khoảng xử lý, chủ yếu do blocking/waiting, với cùng đơn vị đo như C.
- **P:** số worker của pool.

Công thức ước lượng thường gặp:

**P ≈ N × U × (1 + W / C)**

Diễn giải: nếu tác vụ chỉ chạy CPU 1 phần trong tổng (C + W) phần thời gian, cần nhiều worker hơn số CPU để lúc một worker đợi, worker khác có thể chạy. Công thức giả định tải đều, các tác vụ tương đối độc lập, chờ có thể chồng lấp và CPU là ràng buộc đang mô hình hóa. **Nó không bảo đảm pool có kích thước đó sẽ an toàn cho database, API hoặc bộ nhớ.**

**Ví dụ:** N = 8, U = 0,8, mỗi tác vụ tốn C = 5 ms CPU và W = 45 ms chờ I/O.

~~~text
W / C = 45 / 5 = 9
P ≈ 8 × 0,8 × (1 + 9) = 64 worker
~~~

Có thể thử 32, 48, 64 worker dưới tải thực tế rồi so sánh throughput, p95/p99 latency, CPU, queue wait và lỗi downstream. Nếu database chỉ cho phép 20 kết nối hữu dụng, tăng lên 64 worker không tạo được 64 truy vấn database song song: phần dư sẽ đợi kết nối, làm queue và tail latency tệ hơn. **Giới hạn downstream có thể quyết định mức đồng thời nhỏ hơn công thức.**

Một cách viết tương đương, khi đặt tỷ lệ thời gian đợi là b = W/(C+W), là **P ≈ N × U / (1-b)** với 0 ≤ b < 1. Khi C rất nhỏ, tỷ lệ W/C cực lớn và công thức có thể cho kết quả phi thực tế; lúc đó cần đặt giới hạn concurrency/queue/memory trước, không tạo hàng nghìn platform thread theo kết quả máy tính.

### Không nhầm throughput với concurrency

Giả sử hệ thống nhận trung bình λ tác vụ/giây và mỗi tác vụ ở trong hệ thống trung bình T giây. Theo **Little's Law**, lượng tác vụ đồng thời trung bình **L = λ × T** trong trạng thái ổn định. Ví dụ 200 tác vụ/giây với thời gian xử lý trung bình 0,2 giây tương ứng khoảng 40 tác vụ đang xử lý/đợi trong hệ thống.

L ở đây có thể gồm cả tác vụ **trong queue**, nên không được tự động coi L là số worker cần tạo. Để sizing, cần quan sát riêng queue wait, thời gian đang xử lý và tài nguyên mà mỗi giai đoạn sử dụng. Nếu tốc độ đến vượt năng lực xử lý bền vững, queue vẫn tăng dù có tăng nhẹ pool size.

## 5. Đo C, W và khả năng chịu tải như thế nào?

**Bước 1 — phân loại từng loại công việc.** Ghi lại đường đi của request: phần tính toán, blocking I/O, lock, chờ connection, retry và giới hạn bên ngoài. Pool chuyên xử lý request gồm nhiều giai đoạn cần đo trên đúng kiểu request; không lấy tỷ lệ của một tác vụ nhỏ rồi áp cho mọi tác vụ.

**Bước 2 — đo dưới tải đại diện.** Thu thập thời gian từ lúc submit đến khi bắt đầu chạy (**queue wait**), thời gian chạy từ start đến finish (**task wall time**), CPU time thực thi trong worker, độ trễ gọi I/O, timeout/rejection, số kết nối đang sử dụng, CPU utilization và throughput. JFR, thread dump, profiler, metrics của executor, ThreadMXBean và metric của downstream có thể hỗ trợ.

Với ThreadMXBean, getCurrentThreadCpuTime() đo CPU time của thread hiện hành khi JVM hỗ trợ và bật chức năng; không phải cứ lấy tổng wall time trừ CPU time là thu được chính xác riêng **thời gian chờ I/O**. Phần chênh còn chứa scheduling, lock waits và các khoảng không được đo khác. Hãy đo từng đoạn I/O bằng timer và kiểm tra ở cấp hệ thống. Với tác vụ rất ngắn, overhead đo có thể đáng kể.

**Bước 3 — thử dải giá trị.** Giữ workload, input, thời gian warm-up, CPU quota và dependency tương đương, sau đó thay **một tham số**: ví dụ CPU pool = 4/6/8/12 hoặc blocking I/O pool = 16/32/48/64. Đánh giá throughput, p50/p95/p99, error/timeout, CPU, memory, thread count, queue depth và GC. Đừng chọn cấu hình chỉ vì throughput cao nhất nếu p99 hoặc số lỗi tăng mạnh.

**Bước 4 — tải đột biến và quá tải.** Kiểm tra cả tải ổn định, burst, dependency chậm, connection pool cạn và shutdown. Sizing thành công phải có hành vi backpressure/rejection rõ ràng khi vượt công suất.

## 6. Ví dụ Java 17 chạy được: tách CPU pool và blocking I/O pool

Chương trình sau cố ý mô phỏng hai lớp công việc: vòng lặp tính toán chiếm CPU và Thread.sleep mô phỏng **thời gian một platform thread phải chờ**. Chương trình minh họa cách tạo pool riêng, submit Callable, chờ Future và shutdown; **đây không phải benchmark** để suy ra pool size tối ưu. Trong ứng dụng thật, Thread.sleep không thay thế cho đo latency I/O.

Tạo tệp **PoolSizingDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class PoolSizingDemo {
    public static void main(String[] args)
            throws InterruptedException, ExecutionException {
        int cpus = Math.max(1, Runtime.getRuntime().availableProcessors());

        // Giá trị khởi đầu để minh họa; phải đo để cấu hình thực tế.
        int cpuPoolSize = cpus;
        int blockingIoPoolSize = Math.min(32, Math.max(4, cpus * 4));

        List<Callable<Long>> cpuTasks = new ArrayList<>();
        for (int task = 0; task < 20; task++) {
            cpuTasks.add(() -> {
                long sum = 0;
                for (int number = 1; number <= 100_000; number++) {
                    sum += number;
                }
                return sum;
            });
        }

        List<Callable<Integer>> ioTasks = new ArrayList<>();
        for (int task = 0; task < 20; task++) {
            ioTasks.add(() -> {
                Thread.sleep(30); // Mô phỏng chờ I/O blocking.
                return 1;
            });
        }

        long checksum = 0;
        for (long value : execute(cpuPoolSize, cpuTasks)) {
            checksum += value;
        }

        int completed = 0;
        for (int value : execute(blockingIoPoolSize, ioTasks)) {
            completed += value;
        }

        System.out.println("CPU checksum = " + checksum);
        System.out.println("I/O completed = " + completed);
    }

    private static <T> List<T> execute(
            int poolSize, List<Callable<T>> tasks)
            throws InterruptedException, ExecutionException {
        ExecutorService executor = Executors.newFixedThreadPool(poolSize);
        try {
            List<Future<T>> futures = executor.invokeAll(tasks);
            List<T> results = new ArrayList<>();
            for (Future<T> future : futures) {
                results.add(future.get());
            }
            return results;
        } finally {
            executor.shutdown();
        }
    }
}
~~~

Chạy bằng JDK 17+:

~~~bash
javac PoolSizingDemo.java
java PoolSizingDemo
~~~

Kết quả chuẩn (không phụ thuộc thứ tự thread):

~~~text
CPU checksum = 100001000000
I/O completed = 20
~~~

Mỗi tác vụ CPU tính 1 + 2 + ... + 100000 = 5.000.050.000; 20 tác vụ cộng lại thành 100.001.000.000. Hai kích thước pool chỉ là cấu hình **minh họa**. Không lấy thời gian chạy ngẫu nhiên của chương trình làm kết luận benchmark vì JIT, warm-up và scheduling có thể thay đổi.

Ở ví dụ này invokeAll đợi toàn bộ công việc hoàn tất trước khi trả về; shutdown nằm trong finally để không tiếp nhận task mới. Với lifecycle thực tế, cần quản lý shutdown có thời hạn, xử lý InterruptedException đúng cách và cân nhắc shutdownNow khi không thể chờ thêm.

## 7. Pool size chỉ là một nửa: hàng đợi, giới hạn và rejection

**Executors.newFixedThreadPool(n)** sử dụng n worker và hàng đợi LinkedBlockingQueue không giới hạn dung lượng một cách tường minh. Tăng tốc độ submit cao hơn tốc độ hoàn thành khiến queue có thể phình lớn, ngốn heap và tạo latency rất cao, dù số thread cố định.

Với dịch vụ cần giới hạn tải, có thể dùng ThreadPoolExecutor cùng **bounded queue** và chính sách rejection có chủ đích:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class BoundedPoolDemo {
    public static void main(String[] args) {
        ThreadPoolExecutor executor = new ThreadPoolExecutor(
                4, 4,
                0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(100),
                new ThreadPoolExecutor.AbortPolicy()
        );

        try {
            executor.execute(() -> System.out.println("Task accepted"));
        } catch (RejectedExecutionException rejected) {
            System.err.println("Pool overloaded or shutting down");
        } finally {
            executor.shutdown();
        }
    }
}
~~~

Lưu ở **BoundedPoolDemo.java**, chạy:

~~~bash
javac BoundedPoolDemo.java
java BoundedPoolDemo
~~~

Với chương trình đơn nhiệm vụ ở trên, stdout là:

~~~text
Task accepted
~~~

Ở tải thật, AbortPolicy báo RejectedExecutionException khi không thể nhận task, giúp phía gọi phản ứng rõ ràng (trả lỗi quá tải, ghi metric, retry **có giới hạn và backoff** hoặc điều tiết producer). CallerRunsPolicy có thể làm thread submit tự chạy task để giảm tốc độ đưa việc vào, nhưng có thể kéo dài latency của caller; cần xem kỹ hành vi lúc pool shutdown. Không dùng DiscardPolicy nếu không chấp nhận mất việc thầm lặng.

**Ý nghĩa corePoolSize / maximumPoolSize:** ThreadPoolExecutor thường ưu tiên tạo thread tới corePoolSize, sau đó **đưa vào queue**, rồi chỉ tạo thêm thread tới maximumPoolSize nếu queue không nhận thêm. Với queue không giới hạn, maximumPoolSize hầu như không tăng thread quá corePoolSize. Khi lựa chọn size, cần thiết kế **pool + queue + rejection + timeout** cùng lúc.

Tách thêm hai giới hạn:

- **Số worker:** số Java thread đang chạy/chờ.
- **Số request tới dependency:** số kết nối, RPC hay transaction đồng thời mà tài nguyên ngoài chịu được.

Ví dụ pool có 64 worker nhưng database pool tối đa 16 connection thì có thể dùng Semaphore hoặc cơ chế giới hạn kết nối để giữ tối đa 16 truy vấn đồng thời; lúc đó vẫn phải thiết kế queue/wait timeout cho phần còn lại. Đừng tăng cả hai giới hạn chỉ để làm biến mất queue khi database đã bão hòa.

## 8. Khi nào tách pool, khi nào dùng virtual threads?

**Tách pool khi tính chất công việc khác nhau.** Nếu 8 tác vụ tính toán dài dùng kín 8 worker và tác vụ blocking I/O cũng nằm trong cùng pool 8 thread, công việc I/O có thể bị starve. Một CPU pool nhỏ và một blocking I/O pool lớn hơn, có giới hạn riêng, làm chính sách tài nguyên dễ quan sát hơn. Nhưng không nên tạo hàng loạt pool cho từng phương thức; tổng worker của toàn JVM vẫn chịu giới hạn chung.

**ForkJoinPool / work-stealing** phù hợp với một số tác vụ CPU nhỏ chia để trị và các tác vụ có quan hệ fork/join. Nó không phải lựa chọn mặc định cho I/O blocking tùy ý; blocking thiếu khai báo có thể khiến worker bị chiếm và giảm song song. Với logic cụ thể, xem cơ chế ManagedBlocker và đặc tính các API dùng common pool.

**Virtual threads (Java 21+):** với nhiều tác vụ I/O blocking theo mô hình thread-per-request, virtual threads cho phép số lượng tác vụ đồng thời lớn mà không cần một pool platform thread tương ứng. Khi đó thường **không sizing pool virtual thread theo N × (1 + W/C)**; tạo virtual thread theo task và giới hạn concurrency tại tài nguyên khan hiếm như connection, API hoặc rate limit. Virtual threads **không làm CPU nhanh hơn**; code CPU-bound vẫn tranh chấp số CPU thực tế. Một số blocking/native/monitor scenarios có thể ảnh hưởng carrier threads tùy phiên bản JDK; cần quan sát thực tế. Code Java 17 phía trên vẫn dùng platform threads, không giả định Java 21.

Ví dụ cú pháp Java 21+ (độc lập với chương trình Java 17 ở trên):

~~~java
import java.util.concurrent.Executors;
import java.util.concurrent.Semaphore;

public class VirtualThreadIoDemo {
    public static void main(String[] args) throws Exception {
        Semaphore downstreamLimit = new Semaphore(10);
        try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
            for (int i = 0; i < 100; i++) {
                executor.submit(() -> {
                    downstreamLimit.acquire();
                    try {
                        // Thay bằng I/O blocking thực tế tới dependency có giới hạn.
                        Thread.sleep(20);
                    } finally {
                        downstreamLimit.release();
                    }
                    return null;
                });
            }
        }
        System.out.println("100 tasks submitted and completed");
    }
}
~~~

Chạy bằng JDK 21+ sau khi lưu **VirtualThreadIoDemo.java**; khối try-with-resources chờ executor kết thúc các task khi close. Semaphore giới hạn số task **đi vào đoạn I/O** đồng thời là 10; 100 virtual thread được tạo không có nghĩa là 100 kết nối tới downstream. Với tình huống production, cần thêm timeout, cancellation và xử lý interruption phù hợp.

## 9. Quy trình chọn cấu hình cho một hệ thống cụ thể

1. **Xác định tải và mục tiêu:** số tác vụ/giây, concurrency, p95/p99 mục tiêu, SLA, giới hạn CPU/RAM, connection pool và rate limit.
2. **Phân loại từng loại tác vụ:** CPU-bound, blocking I/O, non-blocking I/O hay hỗn hợp; nêu rõ phụ thuộc nào bị gọi.
3. **Chọn baseline:** CPU pool thử quanh N; blocking I/O pool thử từ N × U × (1 + W/C) sau khi đo, rồi **chặn bởi giới hạn downstream, bộ nhớ và số platform thread khả dụng**.
4. **Chọn queue có hạn:** sức chứa phù hợp với burst và thời gian chờ chấp nhận được; xác định rejection, timeout và fallback.
5. **Load test:** tăng dần số worker và concurrency; đo throughput, CPU, độ trễ, queue wait, saturation, contention, timeout, GC và lỗi của dependency.
6. **Chọn cấu hình ổn định:** ưu tiên vùng throughput đã gần bão hòa nhưng tail latency, lỗi và tài nguyên còn an toàn; thử lại với burst và downstream chậm.

### Những dấu hiệu thực tế

| Quan sát | Gợi ý kiểm tra | Hành động thử |
|---|---|---|
| CPU gần 100%, queue tăng, thêm worker không tăng throughput | CPU saturation | Tối ưu thuật toán, giảm CPU/task hoặc mở rộng CPU; tránh tăng thread vô hạn |
| CPU thấp, nhiều worker TIMED_WAITING/WAITING ở I/O, queue dài | Blocking wait, connection starvation | Đo thời gian chờ; thử tăng worker có kiểm soát và kiểm tra giới hạn I/O |
| CPU thấp nhưng nhiều thread BLOCKED trên cùng lock | Contention | Giảm tranh chấp/critical section trước khi tăng pool |
| Độ trễ p99 tăng và queue phình khi burst | Chưa có backpressure, queue quá lớn | Bound queue, admission control, timeout và xử lý rejection |
| Timeout downstream tăng khi tăng pool | Dependency quá tải | Hạ concurrency downstream, giảm retry storm, đặt bulkhead/rate limit |
| Throughput ổn nhưng RAM/thread count tăng mạnh | Platform thread/queue quá nhiều | Giảm giới hạn, cân nhắc virtual threads cho blocking I/O Java 21+ |

### Lỗi thường gặp cần tránh

- Dùng một con số cố định như “pool = 2 × số core” cho mọi loại tác vụ.
- Áp công thức I/O cho CPU-bound hoặc coi thread count càng lớn thì nhanh hơn.
- Lấy Runtime.availableProcessors() làm bằng chứng đầy đủ về CPU quota, bỏ qua tài nguyên dùng chung.
- Đo wall time và gọi toàn bộ nó là CPU time; quên queue wait, lock contention và latency của dependency.
- Chọn maximumPoolSize rất cao trong khi dùng queue không giới hạn, rồi tưởng ThreadPoolExecutor sẽ tự tăng tối đa thread.
- Chỉ đo throughput trung bình, không theo dõi p99, rejection, timeout, RAM, GC hoặc overload.
- Tăng pool size để che giấu truy vấn chậm, khóa tranh chấp, connection pool nhỏ hoặc retry không giới hạn.
- Chạy CPU-heavy task trong pool dành cho blocking I/O rồi khiến các tác vụ I/O bị starvation.

## 10. Checklist khi hoàn thành

Một lựa chọn pool size được xem là có cơ sở khi bạn trả lời được: **N là bao nhiêu trong môi trường triển khai thật? C và W được đo thế nào? Giới hạn concurrency của dependency là bao nhiêu? Queue tối đa bao nhiêu task? Khi quá tải sẽ reject/backpressure ra sao? p95/p99 và throughput có còn đạt mục tiêu sau thử tải hay không?**

**Ghi nhớ:** CPU-bound thường bắt đầu gần năng lực CPU thực sự; blocking I/O có thể cần nhiều worker hơn để che thời gian chờ, nhưng mức đồng thời chỉ hợp lý khi nằm trong sức chịu đựng của hệ thống. Cấu hình chính xác đến từ đo đạc, thử tải và kiểm soát queue/downstream, không đến từ một công thức đơn lẻ.
