# Platform thread và chi phí tạo tài nguyên trong Java

## 1. Mục tiêu và phạm vi

Sau bài này, bạn có thể giải thích platform thread gắn với luồng thực thi của hệ điều hành như thế nào; phân biệt đối tượng Thread, luồng native và CPU core; xác định các nguồn chi phí khi tạo, duy trì, lập lịch, chặn và hủy thread; lựa chọn cách giới hạn concurrency cho ứng dụng Java; đo đạc trước khi tối ưu. Nội dung tập trung vào **Java SE và JVM**, với ví dụ tương thích **Java 17+**.

Câu hỏi cốt lõi: vì sao tạo một platform thread cho mỗi công việc có thể hoạt động tốt với vài chục công việc nhưng trở thành gánh nặng khi hàng nghìn yêu cầu cùng chờ I/O?

## 2. Platform thread là gì?

Trong các JVM phổ biến như HotSpot, **platform thread** là Java thread được JVM ánh xạ gần với mô hình **một Java platform thread ↔ một native OS thread**. Hệ điều hành cấp tài nguyên và lập lịch native thread lên các CPU logic. JVM quản lý ngữ nghĩa Java: thực thi mã, trạng thái Thread, interrupt, Java Memory Model, stack trace và tương tác với garbage collector.

Ba khái niệm cần tách biệt:

| Thành phần | Vai trò |
|---|---|
| Đối tượng java.lang.Thread | Đối tượng Java trên heap dùng để định danh và điều khiển thread (start, join, interrupt, getState...). |
| Native/platform execution thread | Ngữ cảnh chạy do JVM/hệ điều hành hỗ trợ, có stack và trạng thái lập lịch riêng; được tạo khi khởi động thread thực sự. |
| CPU core / logical processor | Tài nguyên xử lý có thể thực thi mã tại một thời điểm. Số thread có thể lớn hơn số core rất nhiều; chỉ một phần thread đang chạy đồng thời trên CPU. |

Với đối tượng Thread mới, lệnh new Thread(runnable) **chưa** tạo một luồng thực thi đang chạy. Lệnh start() yêu cầu JVM khởi động thread mới và gọi run() trên thread đó. Gọi trực tiếp run() chỉ là lời gọi phương thức bình thường trên thread hiện tại.

Các trạng thái Java như NEW, RUNNABLE, BLOCKED, WAITING, TIMED_WAITING, TERMINATED mô tả vòng đời quan sát từ Java. **RUNNABLE không bảo đảm đang sử dụng CPU**: nó có thể đang chạy hoặc sẵn sàng chờ hệ điều hành xếp lịch. Java Thread.State không phải bản sao một-một của mọi trạng thái scheduler native.

## 3. Những tài nguyên một platform thread tiêu thụ

Tạo platform thread không chỉ cấp phát một đối tượng Java. Chi phí thực tế thay đổi theo JVM, hệ điều hành, kiến trúc CPU, tùy chọn chạy và cách ứng dụng sử dụng thread.

| Nguồn tài nguyên | Khi nào phát sinh? | Ý nghĩa |
|---|---|---|
| Đối tượng Thread và dữ liệu liên quan trên Java heap | Khởi tạo đối tượng và liên kết các cấu trúc quản lý | Tăng số đối tượng cần theo dõi/thu gom; bản thân đối tượng không phản ánh toàn bộ chi phí. |
| Native thread và cấu trúc quản lý của OS/JVM | Khi start() tạo thành công luồng thực thi | Có chi phí tạo, hủy và giới hạn số native thread/process của môi trường chạy. |
| Stack riêng của thread | Khi native thread được khởi tạo | Giữ local variables, lời gọi hàm, địa chỉ trở về, frame Java/native; tiêu tốn vùng địa chỉ và một phần bộ nhớ vật lý khi sử dụng. |
| Dữ liệu TLS/ThreadLocal và ngữ cảnh thực thi | Khi thread hoạt động hoặc ứng dụng gán dữ liệu | Có thể giữ tham chiếu lâu hơn dự kiến, đặc biệt trong thread pool. |
| Thời gian CPU lập lịch | Khi có nhiều thread sẵn sàng chạy | OS phải phân phối thời gian chạy; nhiều context switch có thể giảm locality của cache. |
| Tương tác runtime (GC, safepoint, quan sát stack...) | Khi JVM cần duyệt hoặc phối hợp với các thread | Số thread và số frame đang sống có thể tăng chi phí quản lý/quan sát. |

### Stack: kích thước đặt trước khác bộ nhớ RAM thực dùng

Mỗi platform thread có stack riêng, không chia sẻ stack của thread khác. JVM/OS thường **dành sẵn vùng không gian địa chỉ** cho stack; số byte đã chạm tới hoặc thực sự được commit có thể nhỏ hơn phần reserved. Không được đồng nhất **reserved virtual memory** với **resident physical memory (RSS)**.

Tùy JVM/nền tảng, tùy chọn -Xss có thể điều chỉnh kích thước stack của Java platform thread. Ví dụ **giả định** mỗi stack được dành 1 MiB, 10.000 thread có thể tương ứng khoảng 10.000 MiB (xấp xỉ 9,77 GiB) **không gian địa chỉ dành cho stack**; đây **không phải khẳng định** tiến trình đã tiêu thụ 9,77 GiB RAM. Kích thước mặc định, guard pages, cách reserve/commit và giới hạn bộ nhớ đều phụ thuộc môi trường.

Stack quá nhỏ làm tăng nguy cơ StackOverflowError khi call stack sâu. Stack quá lớn khiến chi phí bảo lưu tài nguyên tăng, hạn chế số thread có thể tạo. Vì thế không chọn -Xss chỉ dựa trên phép nhân lý thuyết.

### Ngay cả thread đang chờ cũng chiếm tài nguyên

Một platform thread đợi socket, file, khóa, Condition hoặc sleep thường **không liên tục đốt CPU trong khi đợi**; tuy nhiên nó vẫn sở hữu ngữ cảnh thread, stack và các cấu trúc liên quan. Tỷ lệ thời gian chờ lớn khiến mô hình “mỗi request một platform thread” dễ cần số lượng thread lớn mà throughput CPU không tăng tương ứng.

Thread đang BLOCKED để vào synchronized khác với thread TIMED_WAITING do Thread.sleep(...) hoặc Object.wait(timeout). Cả ba trường hợp đều giữ tài nguyên thread trong lúc không làm công việc CPU hữu ích. Trạng thái cụ thể giúp chẩn đoán nguyên nhân chờ; không dùng mỗi số lượng thread để kết luận ứng dụng tắc nghẽn.

## 4. Tạo thread và chuyển ngữ cảnh tốn gì?

Một chu trình có thể bao gồm:

1. Tạo Thread object và liên kết Runnable hoặc logic run().
2. start() yêu cầu JVM/OS khởi tạo native thread, stack và dữ liệu điều khiển.
3. OS đưa thread vào hàng lập lịch; thread thực thi run() khi được cấp CPU.
4. Thread có thể chạy, chờ I/O/khóa, được đánh thức và bị hoán đổi CPU nhiều lần.
5. Khi run() kết thúc, thread đi đến TERMINATED; native resources được giải phóng theo cơ chế của runtime/OS, còn đối tượng Java chỉ được GC khi không còn tham chiếu tới nó.

Không có **một con số mili giây cố định** cho start() hoặc context switch trên mọi máy. Tạo thread có latency, bộ nhớ và hoạt động kernel; context switch còn phải lưu/khôi phục ngữ cảnh, có thể làm mất cache locality và gây cạnh tranh scheduler. Cường độ ảnh hưởng tăng khi có quá nhiều thread RUNNABLE so với CPU thực sự sẵn có.

Phân biệt hai vấn đề:

- **Tạo quá nhiều thread**: tốn native resource, stack, thời gian khởi tạo/hủy, dễ đụng giới hạn môi trường.
- **Có quá nhiều thread cùng tranh CPU**: tăng scheduling và context switching, có thể giảm throughput dù công việc mỗi thread không đổi.

Thread đang đợi I/O không nhất thiết tạo nhiều context switch liên tục; ngược lại hàng nghìn thread chạy vòng lặp CPU cùng lúc có thể làm scheduler quá tải. Dựa vào profile và workload thật để phân biệt.

## 5. Ví dụ Java 17+: 12 tác vụ, 3 platform worker

Ví dụ này tạo **12 công việc** mô phỏng thời gian chờ nhưng chỉ dùng tối đa **3 platform thread** trong pool. ThreadFactory đặt tên và đếm đúng số worker được tạo. Hàng đợi hữu hạn (ArrayBlockingQueue) khiến năng lực tiếp nhận công việc được xác định rõ.

Lưu tệp **PlatformThreadCostDemo.java**:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class PlatformThreadCostDemo {
    public static void main(String[] args) throws InterruptedException {
        int taskCount = 12;
        int workerCount = 3;
        AtomicInteger createdWorkers = new AtomicInteger();

        ThreadFactory platformFactory = job ->
                new Thread(job, "platform-worker-" +
                        createdWorkers.incrementAndGet());

        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                workerCount,
                workerCount,
                0L,
                TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(taskCount),
                platformFactory,
                new ThreadPoolExecutor.AbortPolicy()
        );

        CountDownLatch finished = new CountDownLatch(taskCount);

        for (int i = 0; i < taskCount; i++) {
            pool.execute(() -> {
                try {
                    // Mô phỏng công việc phải chờ, không đo năng suất.
                    Thread.sleep(40);
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                } finally {
                    finished.countDown();
                }
            });
        }

        finished.await();
        pool.shutdown();
        boolean terminated = pool.awaitTermination(1, TimeUnit.MINUTES);

        System.out.println("tasksCompleted=" +
                (taskCount - finished.getCount()));
        System.out.println("platformWorkersCreated=" +
                createdWorkers.get());
        System.out.println("executorTerminated=" + terminated);
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac PlatformThreadCostDemo.java
java PlatformThreadCostDemo
~~~

Kết quả trong điều kiện thực thi bình thường (không có lỗi cấp phát native thread hay gián đoạn bên ngoài):

~~~text
tasksCompleted=12
platformWorkersCreated=3
executorTerminated=true
~~~

**Giải thích cơ chế:**

- Ba lần execute(...) đầu tiên khiến ThreadPoolExecutor khởi tạo đủ ba core worker; các tác vụ tiếp theo vào hàng đợi có sức chứa 12, đủ cho ví dụ này. Không tạo một thread cho mỗi tác vụ.
- Mỗi worker lấy và xử lý nhiều tác vụ nối tiếp nhau. Lệnh sleep(40) giải phóng CPU để scheduler chạy công việc khác trong thời gian chờ nhưng **worker vẫn là một native thread** đang tồn tại.
- CountDownLatch làm kết quả số công việc hoàn tất độc lập với thứ tự thực thi; mã không suy diễn thời gian chạy hay hiệu năng từ sleep.
- finally bảo đảm đếm xuống ngay cả khi tác vụ bị interrupt. Khi thử nghiệm thực tế, tác vụ cần có chính sách xử lý hủy/interrupt đúng theo yêu cầu nghiệp vụ.
- shutdown() dừng nhận tác vụ mới và để tác vụ đã nhận hoàn tất; awaitTermination(...) đợi pool kết thúc. Trong ứng dụng thật, phải xử lý tình huống timeout và cơ chế shutdown có kiểm soát.

Ví dụ **minh họa reuse và giới hạn số worker**; nó không đo chính xác chi phí tạo OS thread, bộ nhớ stack hay hiệu suất xử lý tác vụ. Benchmark nghiêm túc cần tải đủ lớn, warmup, lặp nhiều lần, cùng giới hạn concurrency và quan sát CPU, RSS, GC, latency, throughput.

## 6. Chiến lược quản lý platform thread

### Tạo mới theo tác vụ hay dùng thread pool?

**Một thread cho mỗi tác vụ** đơn giản về mặt mô hình, nhưng số thread có thể tăng theo số tác vụ đồng thời. Với một lượng nhỏ tác vụ độc lập và sống lâu, thiết kế này có thể phù hợp; với lượng request lớn, khó kiểm soát tài nguyên.

**Thread pool** tái sử dụng một nhóm platform thread để thực hiện nhiều tác vụ. Nó giúp giới hạn số luồng native được tạo và giảm overhead tạo/hủy liên tục. Tuy nhiên, pool **không tự giải quyết quá tải** nếu queue tăng không giới hạn hoặc task giữ khóa/chờ vô thời hạn.

Các tham số phải được hiểu cùng nhau:

| Thành phần | Quyết định |
|---|---|
| corePoolSize / maximumPoolSize | Giới hạn số platform worker tùy cấu hình và trạng thái pool. |
| Queue có giới hạn | Giới hạn số tác vụ đang chờ; nếu đầy phải thực thi chính sách từ chối hoặc điều tiết đầu vào. |
| RejectedExecutionHandler | Xử lý khi task không thể nhận: AbortPolicy ném RejectedExecutionException; CallerRunsPolicy có thể chạy task trên luồng gửi yêu cầu, tạo áp lực ngược. |
| Task timeout, cancellation, interrupt | Tránh giữ worker vô thời hạn và cho phép dừng có kiểm soát. |
| shutdown / awaitTermination / shutdownNow | Quản lý vòng đời pool và xử lý công việc đang chạy/chưa chạy. |

**Cảnh báo về chính sách từ chối:** CallerRunsPolicy làm tác vụ chạy trên caller khi pool còn hoạt động và bão hòa; có thể làm chậm hoặc chặn chính thread tiếp nhận request, nên phải cân nhắc bối cảnh. AbortPolicy yêu cầu caller xử lý RejectedExecutionException. Với hàng đợi không giới hạn như LinkedBlockingQueue mặc định trong Executors.newFixedThreadPool(...), số worker cố định nhưng số task đợi vẫn có thể tăng rất lớn. Ngay cả với bounded queue, phải xác định cách phản hồi và phục hồi khi hệ thống quá tải.

**Ví dụ chọn số worker theo loại tải:**

- **CPU-bound:** Khi tác vụ chủ yếu tính toán và ít chờ, điểm xuất phát hợp lý thường gần số CPU logic thực sự cấp cho tiến trình; sau đó benchmark. Dùng thêm nhiều thread không tạo ra thêm core CPU.
- **I/O-bound:** Tác vụ chờ lâu có thể đạt throughput tốt hơn với số worker lớn hơn số CPU, nhưng native thread vẫn có chi phí. Đo tỉ lệ waiting, độ trễ dịch vụ ngoài, số connection và giới hạn tài nguyên; không tăng worker vô hạn.
- **Tải hỗn hợp:** Tách pool cho công việc CPU và công việc blocking khi cần cô lập độ trễ; theo dõi queue, rejection và saturation thay vì áp cùng một kích thước pool cho mọi việc.

Có thể dùng công thức ước lượng sơ bộ cho workload ổn định: **N ≈ P × (1 + W/C)**, trong đó P là số CPU hữu dụng, W là thời gian chờ trung bình và C là thời gian dùng CPU trung bình của mỗi tác vụ. Đây chỉ là **heuristic khởi điểm**, không phải bảo đảm tối ưu: giới hạn external service, memory, lock contention, burst traffic và SLO thường quan trọng ngang hoặc hơn công thức. Nếu C gần 0, công thức mất ý nghĩa thực tế; hãy đo và đặt trần rõ ràng.

### Backpressure khác với chỉ tăng số thread

Giả sử 200 request/giây đến nhưng backend chỉ xử lý ổn định 100 request/giây. Tăng pool có thể làm backend quá tải nhanh hơn; queue không giới hạn sẽ tích lũy việc chờ, tăng latency và cuối cùng có nguy cơ hết bộ nhớ. Một giải pháp có trách nhiệm cần giới hạn nhận việc, thời gian chờ, timeout, và phản hồi khi quá tải (đợi có giới hạn, giảm tốc phía gửi hoặc từ chối có kiểm soát). Pool chỉ là một thành phần của cơ chế điều tiết.

## 7. Chẩn đoán và đo đạc đúng chi phí

Các tín hiệu đáng quan sát cùng một lúc:

1. **Số thread:** thread đang sống, peak thread count, daemon, số worker theo pool và số native thread của tiến trình.
2. **Trạng thái chờ:** tỉ lệ RUNNABLE/BLOCKED/WAITING/TIMED_WAITING, thread dump lặp lại để thấy trạng thái dai dẳng.
3. **CPU và scheduler:** CPU usage, load, số context switch, số thread sẵn sàng chạy, mức độ cạnh tranh khóa.
4. **Bộ nhớ:** heap, native memory, RSS, virtual address space, stack reservation/commit và các giới hạn OS/container.
5. **Tải nghiệp vụ:** throughput, p50/p95/p99 latency, queue depth, task wait time, rejected tasks, số connection và timeout.

**Trong Java** có thể lấy số liệu cơ bản qua java.lang.management.ThreadMXBean:

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadMXBean;

public class ThreadMetricsDemo {
    public static void main(String[] args) {
        ThreadMXBean threads = ManagementFactory.getThreadMXBean();
        System.out.println("live=" + threads.getThreadCount());
        System.out.println("peak=" + threads.getPeakThreadCount());
        System.out.println("daemon=" + threads.getDaemonThreadCount());
    }
}
~~~

Lưu thành **ThreadMetricsDemo.java**, chạy javac ThreadMetricsDemo.java rồi java ThreadMetricsDemo. Các con số thay đổi theo JVM và thời điểm nên **không có stdout cố định**. ThreadMXBean đếm live Java threads theo định nghĩa của API, không thay thế bộ đếm native threads của OS hoặc một phép đo memory.

**Công cụ thực tế:** Với JDK có jcmd, lệnh jcmd <pid> Thread.print giúp lấy thread dump; Java Flight Recorder (JFR) hỗ trợ phân tích profile, allocation và chờ/khóa khi cấu hình sự kiện phù hợp. HotSpot Native Memory Tracking (NMT), nếu bật từ lúc khởi động bằng -XX:NativeMemoryTracking=summary, có thể quan sát phân loại bộ nhớ JVM qua jcmd <pid> VM.native_memory summary; tính năng này có overhead và không đồng nghĩa toàn bộ RSS. Trên Linux, công cụ OS như top -H -p <pid> hoặc ps -L -p <pid> hỗ trợ nhìn native threads. Cú pháp và độ sẵn có phụ thuộc JDK/OS.

Để tránh hiểu nhầm các chỉ số:

- **Nhiều WAITING threads:** có thể là pool rảnh và không phải lỗi; xét queue, demand và latency.
- **Nhiều BLOCKED threads:** xem điểm khóa/monitor và độ dài critical section.
- **RUNNABLE đông nhưng CPU bị bão hòa:** xem oversubscription và CPU contention.
- **RSS tăng khi tạo thêm threads:** không tự quy toàn bộ cho stack; đối chiếu heap, native memory và thread count.
- **Lỗi OutOfMemoryError: unable to create native thread** (hoặc thông điệp tương đương): kiểm tra cả thread count, giới hạn OS/container, stack size, vùng nhớ native và chính sách cấp phát; tăng heap đơn thuần thường không giải quyết đúng nguyên nhân.

Nếu benchmark chi phí tạo thread, tách riêng ít nhất ba kịch bản: (a) tạo và join một số lượng thread hữu hạn theo đợt; (b) nhiều task qua pool cố định; (c) tải blocking có số concurrency và timeout kiểm soát. Warmup JVM, đo nhiều lần, báo cấu hình JDK/OS/CPU, số lượng tác vụ, throughput và tail latency; không so sánh dựa trên một lần chạy hoặc số sleep giả lập.

## 8. Những lỗi thiết kế thường gặp

**1. Đồng nhất Thread object với native thread đang chạy.** new Thread(...) chỉ tạo đối tượng; start() mới yêu cầu chạy song song. start() lần hai trên cùng Thread ném IllegalThreadStateException. Thread hoàn thành không thể khởi động lại; muốn reuse **worker** thì dùng executor.

**2. “Một request = một platform thread” trong mọi tình huống.** Khi nhiều request cùng đợi I/O, native resources tăng mạnh. Thiết kế nên đặt giới hạn concurrency, queue và timeout theo khả năng hệ thống, hoặc cân nhắc mô hình concurrency khác khi phù hợp.

**3. Xem thread pool là tài nguyên miễn phí.** Pool cố định chặn số worker, nhưng hàng đợi không giới hạn và task bị kẹt vẫn gây memory/latency problem. Cần đo cả queue wait và rejection.

**4. Bỏ qua interrupt và shutdown.** Thread.interrupt() là tín hiệu hợp tác, không “giết” thread tức thì. sleep/wait/join có thể ném InterruptedException; khi không xử lý đầy đủ, thường cần khôi phục interrupt flag bằng Thread.currentThread().interrupt() rồi thoát hoặc trả quyền quyết định cho tầng gọi.

**5. Đặt biến dữ liệu lớn trong ThreadLocal của pool.** Worker sống lâu có thể giữ dữ liệu giữa các task; phải remove() trong finally khi kết thúc scope sử dụng. Tránh rò rỉ thông tin request hoặc classloader references qua thread reuse.

**6. Dựa vào Thread.setPriority(...) để sửa lỗi hiệu năng.** Mức ưu tiên có ý nghĩa phụ thuộc OS/JVM và không phải cơ chế đảm bảo fairness, deadline hay throughput. Đo scheduler và thiết kế tải trước.

**7. Lạm dụng daemon threads cho công việc quan trọng.** JVM có thể kết thúc khi chỉ còn daemon threads; không dựa vào daemon để hoàn tất ghi dữ liệu, transaction hoặc shutdown có thứ tự.

**8. Tối ưu -Xss tùy tiện.** Giảm stack có thể làm hỏng workload gọi sâu; tăng stack có thể giảm số native threads khả dụng. Phải kiểm tra stack depth, giới hạn bộ nhớ và lỗi thực tế trên môi trường triển khai.

## 9. Platform thread và virtual thread: liên hệ cần biết

Từ **Java 21**, virtual threads là tính năng chính thức, cho phép nhiều Java thread nhẹ được JVM lập lịch trên số platform carrier threads nhỏ hơn. Với nhiều công việc chủ yếu **chờ I/O**, virtual thread có thể giảm đáng kể chi phí dành một native thread cho mỗi tác vụ; tuy vậy **không biến CPU core thành tài nguyên vô hạn** và không tự giải quyết việc backend hoặc connection pool bị giới hạn.

Platform thread vẫn quan trọng để chạy mã CPU-bound, làm carrier cho virtual threads và thực thi các executor có kiểm soát. Không so sánh “virtual luôn nhanh hơn platform”: đo throughput/latency trong workload thật, phân biệt concurrency lớn do thời gian chờ với song song thực sự trên CPU. Khi làm việc với JDK 17, virtual threads chưa có dưới dạng tính năng chuẩn; ví dụ ở bài này dùng platform threads.

## 10. Checklist áp dụng

Trước khi quyết định tạo nhiều platform threads, tự trả lời:

- Công việc chiếm CPU hay chờ I/O/khóa? Thời gian chờ chiếm bao nhiêu?
- Cần tối đa bao nhiêu công việc đang chạy, bao nhiêu công việc được xếp hàng, và khi đầy thì hệ thống phản hồi thế nào?
- Có timeout, interrupt, hủy và shutdown rõ ràng không?
- Queue, thread count, stack/native memory, CPU, context switches, p95/p99 latency đang được đo ra sao?
- Số worker có được thử dưới tải mục tiêu, spike traffic và giới hạn container/OS thật không?

**Ghi nhớ:** Platform thread là đơn vị thực thi gắn với native OS thread nên có giá tài nguyên riêng. Thread đang chờ có thể ít dùng CPU nhưng không miễn phí; tăng thread count vượt nhu cầu không đồng nghĩa tăng tốc. Tái sử dụng worker, giới hạn concurrency và backpressure, đo bằng số liệu thực tế là nền tảng để vận hành Java concurrency ổn định.
