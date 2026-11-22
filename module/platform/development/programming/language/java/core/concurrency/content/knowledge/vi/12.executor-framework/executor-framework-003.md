# Fixed, cached và single-thread executors trong Java

## 1. Mục tiêu và phạm vi

Sau bài học, bạn có thể:

- Phân biệt ba factory method **Executors.newFixedThreadPool(n)**, **Executors.newCachedThreadPool()** và **Executors.newSingleThreadExecutor()** theo số worker, cơ chế tạo/tái sử dụng thread, loại hàng đợi, độ tuần tự và giới hạn tài nguyên.
- Hiểu mối liên hệ giữa **Executor**, **ExecutorService**, **ThreadPoolExecutor**, **Runnable**, **Callable** và **Future**.
- Giải thích vì sao một **fixed pool không có hàng đợi giới hạn mặc định**, vì sao **cached pool không có giới hạn thread thực tế do người dùng chỉ định**, và vì sao **single-thread executor không đồng nghĩa Thread object cố định mãi mãi**.
- Chọn executor cho công việc độc lập, CPU-bound, blocking I/O, pipeline cần tuần tự hoặc tài nguyên cần concurrency cố định; không nhầm “tối đa N worker” với “tối đa N công việc được nhận”.
- Dùng **submit()**, **execute()**, **Future.get()**, **shutdown()**, **shutdownNow()**, **awaitTermination()** và xử lý lỗi, hủy, timeout, interrupt đúng hợp đồng.
- Tự tạo **ThreadPoolExecutor với bounded queue và rejection policy** khi cần kiểm soát tải thay vì dùng factory mặc định không giới hạn.
- Chạy ví dụ Java 17+ có stdout xác định, biết cách kiểm chứng tính chất concurrency mà không dựa vào Thread.sleep() hay thứ tự log ngẫu nhiên.

Phạm vi là **Java concurrency nói chung trong JDK 17+**, không đề cập cấu hình executor, lifecycle hay annotation riêng của Spring. Ví dụ dùng platform threads của Java 17. Các API virtual thread xuất hiện từ phiên bản JDK mới hơn không phải một trong ba factory được so sánh ở đây.

## 2. Trước tiên: executor là gì?

Thay vì tạo một Thread riêng cho mọi đơn vị công việc, ứng dụng có thể **giao task** cho một executor quản lý việc thực thi.

~~~java
// Đoạn minh họa, không phải chương trình độc lập:
ExecutorService pool = Executors.newFixedThreadPool(2);
try {
    Future<Integer> result = pool.submit(() -> 6 * 7);
    System.out.println(result.get());
} finally {
    pool.shutdown();
}
~~~

Trong một file Java thật cần import các kiểu trong java.util.concurrent và xử lý/khai báo checked exceptions từ get(). Ý nghĩa của từng thành phần:

- **Runnable**: nhiệm vụ không trả kết quả qua phương thức run(), nhưng có thể có side effect.
- **Callable<T>**: nhiệm vụ trả T hoặc ném exception từ call().
- **Executor.execute(Runnable)**: yêu cầu executor thực thi Runnable.
- **ExecutorService**: bổ sung submit(), Future, shutdown, invokeAll, invokeAny và điều khiển vòng đời.
- **Future<T>**: đại diện cho kết quả/cancel/completion, có phương thức get() để chờ.
- **ThreadPoolExecutor**: một triển khai executor quản lý các worker platform thread, queue và chính sách nhận/từ chối task.

**Executor** phân tách **gửi công việc** khỏi **cách công việc được chạy**. Việc dùng một executor không tự khiến các task thread-safe: nếu hai task cùng sửa một HashMap mutable mà thiếu đồng bộ hóa, data race vẫn có thể xảy ra.

### Task, worker và queue là ba đại lượng khác nhau

~~~text
Producer gọi submit(task)
           |
           v
     ExecutorService
        |        |
        |        +-- Work queue: task đang chờ
        |
        +-- Worker threads: task đang được chạy
                  |
                  +-- Future trả kết quả/lỗi/hủy
~~~

Một **task được chấp nhận** chưa chắc **đang chạy ngay**: nó có thể còn trong queue. Một **thread pool có 4 worker** không đồng nghĩa queue chỉ nhận 4 task. Nếu task chờ nhiều hơn tốc độ xử lý, queue hoặc số worker có thể lớn dần tùy factory.

## 3. Bảng so sánh ba loại executor

| Tiêu chí | newFixedThreadPool(n) | newCachedThreadPool() | newSingleThreadExecutor() |
| --- | --- | --- | --- |
| Số thread làm task cùng lúc | Tối đa **n** | Có thể tăng theo nhu cầu; giới hạn tối đa nội bộ rất lớn | **1** |
| Kích thước pool thường trực | Có thể tạo worker khi cần đến n; mặc định core không tự hết hạn | Thread rảnh có thể bị thu hồi sau thời gian idle | Một worker nếu cần; có thể thay worker đã chết |
| Queue mặc định | **LinkedBlockingQueue không giới hạn thực dụng** | **SynchronousQueue**, handoff trực tiếp, không giữ backlog theo hàng đợi thông thường | **LinkedBlockingQueue không giới hạn thực dụng** |
| Khi task đến mà mọi worker bận | Đưa vào queue | Thường tạo thêm worker (nếu chưa tới giới hạn và tài nguyên cho phép) | Đưa vào queue, không chạy song song |
| Thread rảnh được tái sử dụng | Có | Có; đặc trưng cached | Có; worker được thay thế nếu chết |
| Giữ thứ tự thực thi task | Không bảo đảm hoàn tất theo thứ tự gửi | Không bảo đảm | Task được thực hiện tuần tự theo thứ tự đưa vào queue |
| Có thể gây vấn đề do tải không giới hạn | Queue tăng/bộ nhớ | Thread tăng/bộ nhớ/thread exhaustion | Queue tăng/độ trễ |
| Mục đích điển hình | Giới hạn concurrency của nhóm task | Nhiều task ngắn, đến từng đợt, có kiểm soát tải bên ngoài | Tuần tự hóa một dòng công việc/state |

**Ghi chú “không giới hạn”:** Java không hứa bộ nhớ vô hạn. Mặc định fixed và single dùng queue có capacity ở mức rất lớn (thực dụng xem như unbounded), nên overload có thể gây cạn heap trước khi chạm giới hạn số phần tử. Cached pool có ngưỡng worker tối đa rất lớn, nhưng hệ điều hành/JVM có thể hết tài nguyên tạo thread sớm hơn rất nhiều. Vì vậy “không giới hạn thực dụng” là **rủi ro**, không phải lời hứa khả năng mở rộng vô hạn.

## 4. Fixed thread pool: giới hạn số worker, không giới hạn backlog mặc định

Tạo pool:

~~~java
// Đoạn minh họa; cần import java.util.concurrent.Executors.
ExecutorService pool = Executors.newFixedThreadPool(4);
~~~

Những đặc điểm cốt lõi của **newFixedThreadPool(nThreads)**:

1. Khi cần, executor dùng tối đa **nThreads** worker để xử lý các task.
2. Các task đến khi mọi worker bận được đặt vào queue, thay vì tạo thread thứ n+1.
3. Worker rảnh được tái sử dụng cho task sau.
4. Nếu một worker chấm dứt do lỗi trước shutdown, executor có thể tạo worker thay thế để tiếp tục phục vụ các task.
5. Worker platform thread của pool mặc định **không tự hết hạn vì nhàn rỗi** như cached pool khi pool còn chạy.
6. Factory dùng một queue không có giới hạn hữu ích để tạo **backpressure mặc định**; số task chờ có thể tăng đến khi ảnh hưởng memory/latency.

**Điều được cố định là mức concurrency tối đa**, không phải tổng số task được submit, thời gian hoàn tất hay số thread tuyệt đối mãi mãi trong mọi hoàn cảnh.

### Khi nào chọn fixed?

- Tác vụ độc lập và muốn **giới hạn số tác vụ chạy đồng thời**, ví dụ tính toán xử lý dữ liệu.
- Có thể điều tiết tốc độ submit hoặc workload đã được giới hạn từ bên ngoài.
- Có nhu cầu một pool phục vụ nhiều task vừa/nhỏ, giảm chi phí tạo Thread mới từng lần.
- Có kế hoạch shutdown và kiểm soát lỗi.

**Không dùng factory này mà mặc định đã giải quyết overload.** Nếu producer gửi 100.000 task nhưng 4 worker chỉ xử lý được vài trăm task/giây, backlog tích lũy và tail latency tăng. Một executor giới hạn worker nhưng queue không giới hạn **không giới hạn lượng công việc đã nhận**.

### Ví dụ 1: fixed pool không chạy quá hai task đồng thời

Ta dùng CountDownLatch để buộc hai task đầu giữ worker trong một khoảng logic, rồi kiểm tra có đúng hai task đang hoạt động. Không cần dùng sleep để “may mắn” bắt gặp concurrency.

Tệp **FixedPoolDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicInteger;

public class FixedPoolDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        CountDownLatch twoStarted = new CountDownLatch(2);
        CountDownLatch release = new CountDownLatch(1);
        AtomicInteger active = new AtomicInteger();
        AtomicInteger peak = new AtomicInteger();

        Callable<Integer> task = () -> {
            int now = active.incrementAndGet();
            peak.accumulateAndGet(now, Math::max);
            twoStarted.countDown();
            try {
                release.await();
                return 1;
            } finally {
                active.decrementAndGet();
            }
        };

        try {
            List<Future<Integer>> futures = new ArrayList<>();
            for (int i = 0; i < 4; i++) {
                futures.add(pool.submit(task));
            }

            twoStarted.await();
            System.out.println("first wave active = " + active.get());
            release.countDown();

            int sum = 0;
            for (Future<Integer> f : futures) {
                sum += f.get();
            }
            System.out.println("completed = " + sum);
            System.out.println("peak <= 2 = " + (peak.get() <= 2));
        } finally {
            release.countDown();
            pool.shutdownNow();
        }
    }
}
~~~

Lệnh chạy:

~~~bash
javac -encoding UTF-8 FixedPoolDemo.java
java FixedPoolDemo
~~~

Stdout trong điều kiện chạy bình thường, không có interrupt bên ngoài:

~~~text
first wave active = 2
completed = 4
peak <= 2 = true
~~~

**Giải thích:**

- Hai worker vào task, tăng active rồi chờ release. Vì pool có tối đa 2 worker, hai task còn lại phải chờ trong queue.
- Khi main thấy latch twoStarted về 0, cả hai task đầu vẫn chờ release nên active bằng 2.
- Sau release, bốn task cùng hoàn thành theo lịch khác nhau, nhưng mỗi task trả 1 nên tổng là 4.
- Peak không vượt 2 dù đã submit 4 task.
- finally giải phóng latch nếu đường chờ gặp exception và yêu cầu pool dừng. Trong sản phẩm thật, shutdown hợp tác và chờ kết thúc theo policy thường tốt hơn shutdownNow vô điều kiện.

**Không được suy ra** fixed pool luôn làm hai task hoạt động. Nếu workload không có đủ task hoặc JVM chưa tạo xong worker, số task đang chạy có thể ít hơn n. Ví dụ trên cố ý dùng latch để quan sát được hai worker cùng hoạt động.

## 5. Cached thread pool: tái sử dụng worker rảnh, tăng worker khi không có người nhận

~~~java
// Đoạn minh họa, không phải chương trình độc lập:
ExecutorService pool = Executors.newCachedThreadPool();
~~~

Mẫu cached pool phổ biến sử dụng các đặc điểm của ThreadPoolExecutor:

- **Core pool size = 0**.
- **Maximum pool size** rất lớn (tối đa được cấu hình bằng Integer.MAX_VALUE trong factory JDK).
- **SynchronousQueue**: hàng đợi kiểu **direct handoff**; nó không tích lũy một danh sách các task chờ theo cách LinkedBlockingQueue làm.
- **Keep-alive mặc định 60 giây**: worker nhàn rỗi có thể bị thu hồi nếu không còn nhận việc.
- Task đến sẽ được trao cho worker rảnh phù hợp; nếu không có worker sẵn sàng nhận, executor có thể tạo worker mới.

Cached pool **không giới hạn concurrency bằng một số nhỏ cố định**. Nó phù hợp khi task ngắn, các burst có giới hạn kiểm soát được, và số thread tạo mới không đe dọa tài nguyên.

### Rủi ro với blocking I/O kéo dài

Giả sử có 2.000 request, mỗi task bị chặn chờ dịch vụ bên ngoài rất lâu. Nếu không có worker rảnh tại thời điểm task được giao, cached pool có thể tìm cách tạo rất nhiều thread. Mỗi platform thread dùng tài nguyên bộ nhớ, stack và scheduling. Hệ thống có thể gặp **thread exhaustion**, tăng context switching, giảm throughput hoặc thất bại khi tạo thread.

SynchronousQueue **không tự tạo backpressure** ở giới hạn nghiệp vụ mong muốn. Nếu cần ràng buộc tối đa số request đang hoạt động, dùng Semaphore, bounded executor hoặc hàng đợi giới hạn phù hợp, đồng thời xác định chính sách khi quá tải.

### Ví dụ 2: cached pool tạo đủ worker khi các task cùng chờ

Tệp **CachedPoolDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicInteger;

public class CachedPoolDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newCachedThreadPool();
        CountDownLatch threeStarted = new CountDownLatch(3);
        CountDownLatch release = new CountDownLatch(1);
        AtomicInteger active = new AtomicInteger();

        Callable<Integer> task = () -> {
            active.incrementAndGet();
            threeStarted.countDown();
            try {
                release.await();
                return 1;
            } finally {
                active.decrementAndGet();
            }
        };

        try {
            List<Future<Integer>> futures = new ArrayList<>();
            for (int i = 0; i < 3; i++) {
                futures.add(pool.submit(task));
            }

            threeStarted.await();
            System.out.println("concurrent active = " + active.get());

            release.countDown();

            int sum = 0;
            for (Future<Integer> f : futures) {
                sum += f.get();
            }
            System.out.println("completed = " + sum);
        } finally {
            release.countDown();
            pool.shutdownNow();
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 CachedPoolDemo.java
java CachedPoolDemo
~~~

Stdout:

~~~text
concurrent active = 3
completed = 3
~~~

Ba task cùng chờ trên release; không có worker rảnh để nhận task thứ hai và thứ ba, nên cached pool có thể mở rộng đủ để cả ba task bắt đầu. Cách dùng latch giúp kết quả quan sát có tính xác định trong ví dụ. **Điều này không có nghĩa cached pool luôn tạo thread mới cho mỗi task**: sau khi task kết thúc, worker có thể tái sử dụng cho task khác; khi rảnh lâu, worker có thể bị loại bỏ.

Nếu thiết kế chỉ được phép **2 request đồng thời**, cached pool không tự giữ giới hạn đó. Cần thêm control (ví dụ Semaphore) hoặc chọn executor giới hạn worker và chính sách backlog hợp lý.

## 6. Single-thread executor: một task chạy tại một thời điểm

~~~java
// Đoạn minh họa:
ExecutorService pool = Executors.newSingleThreadExecutor();
~~~

**newSingleThreadExecutor()** có hợp đồng:

1. Chỉ có **một worker hoạt động thực thi task** tại một thời điểm.
2. Task được **thực hiện tuần tự**; không có hai task trong cùng executor chạy chồng lên nhau.
3. Các task đi vào queue chờ lượt. Với factory mặc định, queue có tính chất **không giới hạn thực dụng**.
4. Nếu worker thất bại và chấm dứt trước shutdown, executor tạo worker thay thế khi cần; **không nên dựa vào cùng một Thread object sống mãi**.
5. Executor trả về là một lớp bao không cung cấp cách public đơn giản để chỉnh pool lên nhiều worker, trái với việc tự tạo ThreadPoolExecutor có core/max bằng 1.
6. Khi nhiều thread cùng submit, thứ tự chính xác giữa các lời gọi đồng thời do lịch submit quyết định; **không có thứ tự nghiệp vụ tự nhiên** nếu ứng dụng chưa định nghĩa nó.

Single-thread executor là cách dễ hiểu để xây dựng **mô hình một owner cập nhật shared mutable state**. Nhưng các thread khác không được trực tiếp sửa state ấy cùng lúc, nếu không confinement bị phá.

### Ví dụ 3: xử lý tuần tự ba command

Tệp **SingleThreadPoolDemo.java**:

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class SingleThreadPoolDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        StringBuilder state = new StringBuilder();

        try {
            pool.submit(() -> state.append("A"));
            pool.submit(() -> state.append("B"));
            pool.submit(() -> state.append("C"));

            Future<String> result = pool.submit(state::toString);
            System.out.println("state = " + result.get());
        } finally {
            pool.shutdown();
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 SingleThreadPoolDemo.java
java SingleThreadPoolDemo
~~~

Stdout:

~~~text
state = ABC
~~~

**Vì sao có thể dùng StringBuilder?** Các task thay đổi StringBuilder và task snapshot đều chạy tuần tự trên một executor. Main **không** đọc hoặc sửa StringBuilder trực tiếp khi worker đang xử lý; main chỉ nhận String qua Future.get(). Trong mô hình ví dụ này không có hai thread cùng truy cập mutable state.

**Lưu ý:** Không nên suy luận “dùng một executor tên single” sẽ khiến mọi lời gọi vào object tự đi qua executor. Nếu thread khác gọi trực tiếp state.append("X") trong lúc worker xử lý, vẫn có race. Và nếu task có side effect bên ngoài, việc chạy tuần tự trong một JVM không tự cung cấp transaction hay exactly-once.

### Không giữ một ThreadLocal như biến trạng thái nghiệp vụ bất biến theo worker

Single-thread executor **thường tái sử dụng một thread**, nhưng có thể thay thế worker khi thread trước chết. **ThreadLocal** gắn với thread cụ thể, không gắn với executor. Vì vậy nếu worker bị thay, giá trị ThreadLocal có thể biến mất; khi reuse worker, ngữ cảnh task cũ có thể còn nếu không remove(). Dữ liệu nghiệp vụ nên nằm trong một owner object có lifecycle rõ ràng thay vì dựa vào ThreadLocal như kho lưu trữ lâu dài.

## 7. Bảng chọn theo nhu cầu và kiểu task

| Bài toán | Lựa chọn khởi đầu | Điều cần kiểm soát thêm |
| --- | --- | --- |
| Tính toán độc lập, muốn tối đa N tác vụ hoạt động | Fixed pool | Kích thước theo CPU/workload, backlog, overload |
| Task ngắn, số task đến từng đợt nhưng concurrency được giới hạn bên ngoài | Cached pool có thể phù hợp | Số thread tối đa thực tế, blocking duration, tài nguyên OS |
| Command tuần tự lên cùng mutable state | Single-thread executor | Queue growth, head-of-line blocking, task failure |
| Hàng triệu request I/O chờ lâu | Không mặc định dùng cached platform-thread pool | Bounded resource model, backpressure, JDK/platform phù hợp |
| Xử lý request cần timeout và bounded backlog | ThreadPoolExecutor cấu hình giới hạn | Queue capacity, rejection, cancellation, shutdown |
| Muốn task hoàn thành theo thứ tự gửi | Single-thread executor hoặc giao thức sắp xếp kết quả | Thứ tự submit giữa nhiều producer, failure/slow task |
| Muốn giữ thứ tự output nhưng vẫn chạy song song | Fixed/cached + lưu Future theo index và kết hợp đúng | Completion order khác submission order |
| Một tác vụ submit task khác rồi chờ Future trên cùng một worker | Tránh mô hình phụ thuộc vòng | Thread-starvation deadlock |

**Đừng chọn chỉ theo con số thread.** Hãy xét thời gian chạy của task, thời gian block, tần suất gửi, RAM, nguy cơ queue tăng và mục tiêu latency. Với tác vụ CPU-bound, số worker gần mức CPU hiệu dụng có thể là điểm thử nghiệm ban đầu, nhưng không phải công thức cố định cho mọi workload.

## 8. Những gì xảy ra khi submit vượt khả năng phục vụ

Giả sử mỗi giây ứng dụng nhận 1.000 task nhưng pool xử lý được 100 task/giây. Nếu không có backpressure, backlog tăng khoảng 900 task/giây trong thời gian tải như vậy kéo dài.

### Fixed và single: queue tăng

~~~text
Incoming -> [Worker 1][Worker 2] + [Queue: task task task task ...]
                                          |
                                      backlog tăng
~~~

Nếu queue không bị giới hạn ở mức nghiệp vụ phù hợp, có thể tăng độ trễ rất lớn hoặc cạn bộ nhớ. **Không có giới hạn worker** khác với **không có giới hạn task chờ**.

### Cached: worker tăng

~~~text
Incoming -> [Worker 1][Worker 2][Worker 3][Worker 4] ...
                mỗi worker bị block lâu
                -> số platform threads tăng
~~~

Cached pool đặt trọng tâm vào tái sử dụng worker và mở rộng nhanh khi không có worker rảnh; dưới tải blocking không kiểm soát, có thể dùng cạn tài nguyên tạo thread.

### Single: head-of-line blocking

Một task đầu tiên chậm hoặc chờ I/O làm tất cả task sau **phải đợi lượt**. Nếu task đầu kẹt mãi, queue có thể tích lũy mà không công việc phía sau nào được chạy. Đó là trade-off của mô hình tuần tự.

**Backpressure** nghĩa là hệ thống chủ động giới hạn lượng việc chưa xử lý, để producer phải chờ, bị từ chối có kiểm soát, hoặc áp dụng một chính sách mất dữ liệu được phép theo đặc tả. Mặc định của ba factory không phải là một giải pháp backpressure tổng quát.

## 9. Cấu hình ThreadPoolExecutor có bounded queue

Khi cần giới hạn đồng thời cả số worker và queue, có thể tạo ThreadPoolExecutor tường minh.

Tệp **BoundedExecutorDemo.java**:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Future;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class BoundedExecutorDemo {
    public static void main(String[] args) throws Exception {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 1,
                0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(1),
                new ThreadPoolExecutor.AbortPolicy()
        );

        CountDownLatch workerStarted = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            Future<Integer> first = pool.submit(() -> {
                workerStarted.countDown();
                release.await();
                return 1;
            });

            workerStarted.await();   // Worker đang chạy task 1.
            Future<Integer> second = pool.submit(() -> 2); // Queue 1 slot.

            boolean rejected = false;
            try {
                pool.submit(() -> 3); // Worker bận, queue đầy.
            } catch (RejectedExecutionException ex) {
                rejected = true;
            }

            System.out.println("rejected = " + rejected);
            release.countDown();

            System.out.println("sum = " + (first.get() + second.get()));
        } finally {
            release.countDown();
            pool.shutdownNow();
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 BoundedExecutorDemo.java
java BoundedExecutorDemo
~~~

Stdout:

~~~text
rejected = true
sum = 3
~~~

**Giải thích chính xác:**

1. Core=max=1 nên pool có **một worker**.
2. ArrayBlockingQueue capacity=1 chỉ có **một task chờ**.
3. Task 1 đã báo started và đang đợi release, vì vậy task 2 nằm trong queue.
4. Task 3 không thể chạy ngay, queue đã đầy; AbortPolicy ném RejectedExecutionException ngay khi submit.
5. Main giải phóng task 1 rồi lấy kết quả của hai Future đã được nhận: 1 + 2 = 3.
6. finally bảo đảm release latch ngay cả khi lỗi và yêu cầu dừng pool.

Đây là ví dụ minh họa **giới hạn rõ ràng** chứ không đề xuất luôn bỏ task khi queue đầy. Cần quy định phản hồi thực tế khi rejection xảy ra: retry có giới hạn, thông báo bận, giảm tốc producer, hoặc đưa công việc sang cơ chế lưu trữ có độ bền phù hợp.

### Rejection policies và ý nghĩa

| Handler | Hành vi chủ yếu | Rủi ro |
| --- | --- | --- |
| **AbortPolicy** | Ném RejectedExecutionException | Caller phải xử lý; thích hợp khi không được âm thầm mất việc |
| **CallerRunsPolicy** | Khi chưa shutdown, thực thi task trong thread gọi execute | Có thể block producer và phá giả định “task luôn chạy trên worker chuyên dụng” |
| **DiscardPolicy** | Bỏ task bị từ chối mà không ném | Dễ mất việc âm thầm, khó xác định trạng thái |
| **DiscardOldestPolicy** | Loại task đầu queue rồi thử lại execute | Task cũ có thể bị mất, không phù hợp job bắt buộc xử lý |

**Đặc biệt với thread confinement:** Nếu dùng CallerRunsPolicy, một task bị từ chối có thể chạy **ngay trên thread submit**. Vì vậy một kiến trúc dựa vào “chỉ một worker thực thi mọi thao tác trên state” có thể bị phá nếu caller cũng thực thi task. Chính sách overload phải phù hợp với **ownership** và bất biến, không chỉ với throughput.

### Queue cũng ảnh hưởng cách pool tăng worker

Với ThreadPoolExecutor nói chung:

- Nếu số worker hiện có chưa đạt corePoolSize, pool thường tạo worker mới để xử lý task.
- Khi đã đủ core worker, executor thường **thử enqueue**.
- Nếu enqueue không được và số worker còn dưới maximumPoolSize, executor có thể tạo thêm worker.
- Nếu không thể enqueue và cũng không tạo worker, task sẽ bị từ chối.

Điều này giải thích vì sao **maximumPoolSize không có tác dụng mở rộng lên trên core** đối với một queue không giới hạn mà vẫn nhận enqueue. Muốn điều chỉnh số worker linh hoạt phải hiểu cả **core/max và loại queue**. Tránh đặt max rất lớn nhưng giữ queue unbounded rồi tin pool sẽ tự scale worker khi queue dồn.

## 10. submit(), execute() và cách xử lý exception

### execute(Runnable)

**execute()** giao Runnable cho executor. Nếu Runnable ném unchecked exception, việc xử lý exception phụ thuộc đường thực thi, thread factory/handler và ThreadPoolExecutor; lỗi có thể tới uncaught exception handler của worker thread, và worker bị thay. **Không được giả định caller của execute() trực tiếp bắt được exception bên trong task.**

### submit(Runnable/Callable)

**submit()** trả Future. Exception xảy ra trong task thường được lưu trong Future; caller gọi **Future.get()** sẽ nhận **ExecutionException** và xem cause. Nếu bỏ qua Future, lỗi task có thể không được người gửi nhìn thấy qua luồng điều khiển bình thường.

### Ví dụ 5: bắt lỗi từ Future.get()

Tệp **FutureFailureDemo.java**:

~~~java
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class FutureFailureDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(1);

        try {
            Future<Integer> result = pool.submit(() -> {
                throw new IllegalArgumentException("invalid input");
            });

            try {
                result.get();
            } catch (ExecutionException ex) {
                System.out.println(
                    "cause = " + ex.getCause().getClass().getSimpleName()
                );
            }
        } finally {
            pool.shutdown();
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 FutureFailureDemo.java
java FutureFailureDemo
~~~

Stdout:

~~~text
cause = IllegalArgumentException
~~~

**Future.get()** còn có thể ném InterruptedException nếu caller đang đợi bị ngắt; Future bị cancel có thể ném CancellationException. Không coi isDone() là thành công: **done bao gồm thành công, thất bại và hủy**.

### Thứ tự gửi không đồng nghĩa thứ tự hoàn tất

Fixed/cached executor có thể chạy task song song, nên task được submit sau vẫn có thể hoàn tất trước. Muốn lấy kết quả theo thứ tự đã lưu, main có thể giữ danh sách Future và gọi get() theo index; đó là **thứ tự thu kết quả**, không chứng minh task chạy tuần tự. Nếu muốn phản hồi theo **thứ tự hoàn thành thực tế**, xem **ExecutorCompletionService** hoặc cơ chế composition phù hợp.

Single-thread executor chạy tuần tự các task đã được xếp theo thứ tự vào executor, nhưng không thể suy ra thứ tự của các lời submit diễn ra đồng thời giữa nhiều producer chỉ từ tên executor.

## 11. Vòng đời: shutdown, shutdownNow và awaitTermination

ExecutorService cần có vòng đời rõ ràng. Trên Java 17, nên dùng try/finally để đảm bảo gọi phương thức shutdown khi không còn dùng pool.

| API | Hợp đồng cơ bản |
| --- | --- |
| **shutdown()** | Ngừng nhận task mới, tiếp tục xử lý task đã được chấp nhận trước shutdown |
| **shutdownNow()** | Cố dừng các task đang chạy (thường bằng interrupt), trả danh sách task chưa bắt đầu thực thi |
| **isShutdown()** | Đã được yêu cầu shutdown chưa |
| **isTerminated()** | Tất cả task đã kết thúc sau shutdown chưa |
| **awaitTermination(timeout, unit)** | Chờ tối đa thời gian chỉ định cho executor kết thúc; trả boolean |
| **submit sau shutdown** | Thường bị từ chối theo rejection policy |

**shutdown() không block** cho đến khi mọi task xong; nó chỉ bắt đầu quá trình đóng. **shutdownNow() không đảm bảo dừng được task đang chạy**, vì tác vụ có thể không xử lý interrupt. Danh sách trả về của shutdownNow() có thể chứa task đã chờ trong queue; policy gọi lại/ghi nhận những task này phải do ứng dụng tự quyết định.

Một ví dụ shutdown hợp tác:

~~~java
// Đoạn minh họa trong phương thức throws InterruptedException:
pool.shutdown();

if (!pool.awaitTermination(10, java.util.concurrent.TimeUnit.SECONDS)) {
    java.util.List<Runnable> pending = pool.shutdownNow();
    // Ghi nhận/sắp xếp xử lý pending theo yêu cầu nghiệp vụ.
    if (!pool.awaitTermination(10, java.util.concurrent.TimeUnit.SECONDS)) {
        // Ghi nhận rằng vẫn còn task không kết thúc.
    }
}
~~~

Không có main() trong đoạn này; biến pool cần là ExecutorService đã khởi tạo. Với hệ thống thật, nếu thread đang thực hiện I/O không interruptible, việc gọi shutdownNow không chắc làm nó kết thúc. **Dùng timeout không có nghĩa task đã bị hủy và side effect đã rollback**.

### Không tự chặn mình khi shutdown

Nếu một task chạy trong single-thread executor lại submit một task phụ **vào chính executor ấy** rồi gọi Future.get() để đợi task phụ, worker duy nhất đang bị task hiện tại chiếm nên task phụ không được chạy. Đây là **thread-starvation deadlock**.

Tương tự, cố chờ executor chấm dứt ngay từ một worker của chính executor, trong khi nó còn phải chờ worker ấy kết thúc, có thể dẫn tới vòng chờ. Phân tích **dependency graph**, không chỉ số thread.

## 12. Hủy tác vụ và interrupt

**Future.cancel(true)** yêu cầu hủy và có thể interrupt thread đang chạy tác vụ. Nó **không** cưỡng chế dừng ngay, không xóa thao tác I/O đã thực hiện và không rollback transaction. **cancel(false)** không yêu cầu ngắt task đang chạy nhưng vẫn có thể đánh dấu Future bị hủy theo hợp đồng.

Một task muốn hỗ trợ hủy nên:

- Có các điểm kiểm tra **Thread.currentThread().isInterrupted()** khi thực hiện vòng lặp lâu.
- Xử lý **InterruptedException** từ blocking APIs: propagate hoặc khôi phục interrupt flag và thoát theo policy.
- Giải phóng lock/permit/stream/resource đúng đường finally.
- Không gọi thao tác bên ngoài không idempotent vô kiểm soát trong đường retry.
- Phân biệt **request timeout** với **task thực sự đã ngừng** và **side effect đã commit**.

### Ví dụ 6: cancel task đang chờ latch

Tệp **ExecutorCancelDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class ExecutorCancelDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch neverReleased = new CountDownLatch(1);
        AtomicBoolean sawInterrupt = new AtomicBoolean();

        try {
            Future<?> task = pool.submit(() -> {
                entered.countDown();
                try {
                    neverReleased.await();
                } catch (InterruptedException ex) {
                    sawInterrupt.set(true);
                    Thread.currentThread().interrupt();
                }
            });

            entered.await();
            boolean cancelled = task.cancel(true);

            pool.shutdown();
            boolean terminated = pool.awaitTermination(
                    5, TimeUnit.SECONDS
            );

            System.out.println("cancel accepted = " + cancelled);
            System.out.println("worker interrupted = " + sawInterrupt.get());
            System.out.println("pool terminated = " + terminated);
        } finally {
            pool.shutdownNow();
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 ExecutorCancelDemo.java
java ExecutorCancelDemo
~~~

Stdout khi worker nhận interrupt và kết thúc theo giao thức (môi trường chạy bình thường):

~~~text
cancel accepted = true
worker interrupted = true
pool terminated = true
~~~

**Giải thích:**

- entered.await() đảm bảo task đã bắt đầu trước khi main gọi cancel.
- Worker chờ CountDownLatch không được phát tín hiệu, nên cancel(true) là yêu cầu interrupt phù hợp cho blocking wait đó.
- Worker bắt InterruptedException, ghi cờ quan sát và kết thúc.
- awaitTermination kiểm tra việc executor đã chấm dứt; caller chỉ in trạng thái sau khi đã yêu cầu shutdown và chờ.
- Future được đánh dấu canceled **không đồng nghĩa một tác vụ bất kỳ luôn nhận interrupt thành công**. Ví dụ này cố ý chọn CountDownLatch.await() để minh họa đường hủy hợp tác.

**Thực tiễn:** Nếu timeout 5 giây xảy ra do môi trường rất bận hoặc worker không phản hồi, pool terminated có thể là false; không dùng một khoảng chờ số học cố định để chứng minh JVM luôn kết thúc đúng deadline. Thông điệp ở đây là phải **kiểm tra kết quả awaitTermination**, chứ không mặc định thành công.

## 13. Java Memory Model: gửi task và lấy Future kết quả

ExecutorService có quy tắc memory consistency quan trọng:

- Các hành động trong thread **trước khi gửi Runnable/Callable tới ExecutorService** happens-before các hành động của task đó.
- Các hành động trong task **happens-before** hành động của thread khác **sau khi lấy kết quả bằng Future.get()**.

Nhờ đó, việc truyền input đã chuẩn bị trước submit và đọc output sau Future.get có cơ sở JMM.

~~~text
Producer thread                        Worker thread
----------------                       -------------
prepare input
submit(task)        --- happens-before -> task đọc input
                                         task tạo result
future.get()         <- happens-before -- task kết thúc
consume result
~~~

Tuy nhiên, **không được sửa input mutable đồng thời với task đang đọc** nếu không có đồng bộ hóa bổ sung. Happens-before của submit không cho phép producer tiếp tục viết không đồng bộ vào cùng object sau khi đã submit rồi mong worker thấy snapshot nhất quán.

Single-thread executor cũng không tự bảo vệ code bên ngoài executor truy cập state của worker. Trạng thái business chỉ thực sự confined nếu chỉ owner worker sửa nó và giao tiếp với thread khác qua kênh có hợp đồng rõ ràng.

## 14. Sử dụng task độc lập và state được chia sẻ

Một pool cho phép nhiều task **cùng chạy**, nhưng không đảm bảo safe access đến shared mutable state:

~~~java
// Anti-pattern minh họa khi pool có nhiều worker:
java.util.HashMap<String, Integer> totals = new java.util.HashMap<>();

pool.submit(() -> totals.put("a", 1));
pool.submit(() -> totals.put("b", 2));
~~~

Hai put vào HashMap có thể diễn ra đồng thời; HashMap không thread-safe theo hợp đồng. Không sửa bằng cách thêm Thread.sleep trong một task. Lựa chọn tùy bất biến:

- Nếu chỉ cần map hỗ trợ các operation concurrent, cân nhắc **ConcurrentHashMap** và các operation có ngữ nghĩa nguyên tử tương ứng.
- Nếu phải cập nhật nhiều field cùng nhau, dùng **lock** bảo vệ toàn giao dịch trong JVM.
- Nếu có thể, chuyển state về **single-thread owner** và gửi command tới owner.
- Nếu task độc lập, trả về immutable result rồi gộp kết quả ở một thread sau Future.get.

**Không suy ra mọi chuỗi operation trên ConcurrentHashMap cũng nguyên tử**: containsKey rồi put vẫn là check–then–act nếu không dùng operation có điều kiện như putIfAbsent/computeIfAbsent đúng hợp đồng.

### Khi nào single-thread giúp tránh lock?

Nếu một object mutable chỉ được chạm tới bởi các task chạy trên cùng single-thread executor, các thao tác trên object đó không có truy cập đồng thời từ các task của executor. Ta có thể giảm nhu cầu lock bên trong object. Nhưng nếu producer cầm tham chiếu tới object ấy và sửa trực tiếp, hoặc dùng CallerRunsPolicy khiến task chạy trên thread gọi, mô hình ownership bị phá.

### Khi nào fixed/cached cần atomic hoặc lock?

Khi task trong pool chia sẻ trạng thái mutable, mọi truy cập liên quan cần giao thức phù hợp: atomic increment cho counter, CAS cho trạng thái một biến, lock cho bất biến nhiều bước, hoặc message passing để tránh chia sẻ.

## 15. Không nhầm tên pool với thread identity và ThreadLocal

Cả fixed, cached và single-thread executor **tái sử dụng thread** theo chính sách của mình. Những lỗi thường gặp:

- Task A lưu ngữ cảnh vào ThreadLocal mà quên **remove()**; task B chạy sau trên cùng worker có thể thấy ngữ cảnh còn sót.
- Tên thread hoặc id không phải ID request: một worker có thể chạy rất nhiều task.
- Single-thread executor có thể thay worker nếu worker cũ chết; không nên lưu trạng thái nghiệp vụ chỉ trong ThreadLocal và mong không bao giờ mất.
- Cached pool có thể tạo thread mới cho task đến khi không còn worker rảnh, nên dữ liệu ThreadLocal của task trước không đảm bảo xuất hiện.
- Fixed pool có N thread nhưng không có cam kết task nào luôn thuộc cùng một worker cụ thể.

Với ngữ cảnh task, cách an toàn là **truyền dữ liệu cần thiết trong task object** hoặc đặt/clear ThreadLocal theo scope trong try/finally, nếu thật sự cần ThreadLocal. Mọi context được share qua reference mutable vẫn cần tính đến safe publication và ownership.

## 16. Sizing pool và nguyên tắc đo đạc

### CPU-bound

Với tác vụ tiêu tốn CPU liên tục, số worker gần với số CPU thực sự được cấp là **điểm bắt đầu để đo**. Quá nhiều worker CPU-bound có thể tăng context switching, cache contention và giảm hiệu năng. Không lấy Runtime.availableProcessors() làm công thức tuyệt đối: JVM có thể chịu quota container, hyper-threading, tác vụ hỗn hợp và ràng buộc của ứng dụng.

### Blocking I/O

Task có thể dành nhiều thời gian chờ socket/file/database. Có thể cần nhiều worker hơn số CPU, nhưng vẫn phải giới hạn **tài nguyên thật** như số connection, memory, remote rate limits và queue backlog. Cached pool không phải câu trả lời tự động cho mọi bài toán I/O.

### Single-thread

Một worker tốt khi correctness cần tuần tự và tải phù hợp với năng lực xử lý của một thread. Nhưng nó sẽ có head-of-line blocking khi task kéo dài. Nên đo **queue latency**, thời gian xử lý task và backlog, không chỉ CPU.

### Đo metric nào?

| Metric | Tại sao hữu ích |
| --- | --- |
| Throughput (task/giây) | Năng lực xử lý thực tế |
| Active worker count | Mức concurrency và contention |
| Queue size/age | Tải tồn đọng và nguy cơ latency |
| Rejection count | Quá tải đã vượt chính sách chấp nhận |
| Task execution latency | Thời gian chạy của task |
| Queue waiting latency | Thời gian từ submit tới bắt đầu chạy |
| Tail latency p95/p99 | Người dùng cuối bị ảnh hưởng khi tải dồn |
| Heap/thread count | Rủi ro memory/thread exhaustion |
| Error/cancel/timeout count | Task kết thúc vì gì, không chỉ isDone |

Không kết luận fixed nhanh hơn cached hoặc ngược lại chỉ từ một benchmark đơn. Hãy kiểm tra nhiều cỡ task, CPU, thời gian block, tốc độ producer, warmup/JIT và mức giới hạn tài nguyên. Có thể kết hợp **bounded concurrency** với cơ chế khác thay vì chọn chỉ một factory.

## 17. Deadlock và chờ vòng trong executor

### Single-thread task đợi task khác trên cùng pool

~~~java
// Anti-pattern minh họa; nếu đặt trong task chạy trên single pool:
Future<?> child = sameSinglePool.submit(() -> doChildWork());
child.get(); // Worker duy nhất đang đợi chính task chưa thể chạy.
~~~

Ví dụ không độc lập: sameSinglePool và doChildWork() là thành phần giả định; child.get() cần checked-exception handling. Nếu chỉ có một worker, task con bị queue phía sau task cha nhưng task cha lại đợi con; đó là **thread-starvation deadlock**.

### Fixed pool bị chiếm toàn bộ bởi các task chờ phụ thuộc

Không chỉ single-thread mới có vấn đề. Một fixed pool 4 worker có thể bị 4 task cha chiếm hết, mỗi cha lại submit task con vào cùng pool rồi chờ Future.get. Tất cả task con chờ queue, không còn worker để xử lý. Tăng pool lên 8 có thể chỉ đẩy ngưỡng lỗi nếu thiết kế phụ thuộc còn vòng.

### Chờ Future trong lúc giữ lock

Thread A giữ lock L rồi gọi Future.get chờ worker; worker muốn lấy lock L mới hoàn tất. Vòng chờ không giải quyết được bởi việc đổi cached thành fixed. Cần phân tích dependency graph, bỏ chờ bên trong critical section khi có thể hoặc thiết kế workflow bất đồng bộ phù hợp.

### Khi nào nên tách executor?

Một task parent cần chờ child thuộc một loại tài nguyên/chờ khác có thể được tổ chức ở executor khác, hoặc nối kết quả bất đồng bộ để không chiếm worker chờ vòng. Nhưng tạo thêm executor không tự sửa logic dependency sai, không thay thế timeout/cleanup và không có nghĩa cứ càng nhiều pool càng tốt.

## 18. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| Fixed pool chỉ nhận tối đa N task | N giới hạn số worker hoạt động; queue có thể nhận nhiều task hơn |
| Fixed pool luôn có sẵn đúng N Thread object từ lúc tạo | Worker có thể được tạo theo nhu cầu; có thể được thay khi lỗi |
| Cached pool giới hạn thread bằng số CPU | Không; cached có thể tạo rất nhiều platform thread |
| Cached pool giữ backlog trong LinkedBlockingQueue | Mẫu mặc định dùng SynchronousQueue handoff |
| Single-thread executor có một Thread object bất biến mãi mãi | Worker có thể được thay, nhưng contract tuần tự còn được giữ |
| Single-thread nghĩa nhiều thread submit sẽ có thứ tự nghiệp vụ xác định | Concurrent submitters cần quy tắc ordering riêng |
| Một pool có worker nghĩa task luôn được chạy ngay | Task có thể ở queue hoặc bị từ chối |
| Future.isDone() đồng nghĩa task thành công | Done cũng có thể là failure hoặc cancellation |
| submit() tự in lỗi khi task ném exception | Exception thường được lưu trong Future và thấy qua get() |
| shutdown() đợi tất cả task kết thúc trước khi trả về | Nó khởi động shutdown, không tự block |
| shutdownNow() chắc chắn dừng task ngay | Thường chỉ gửi interrupt/cố dừng; task cần hợp tác |
| Future.get(timeout) timeout nghĩa worker đã bị hủy | Nó chỉ giới hạn thời gian chờ của caller |
| Factory mặc định đã có backpressure | Fixed/single có queue không giới hạn thực dụng; cached tăng worker |
| Đặt maximumPoolSize cao hơn core luôn làm pool tự scale lên max | Unbounded queue có thể nhận hết backlog khiến pool không vượt core |
| CallerRunsPolicy chỉ làm ứng dụng chậm lại | Nó có thể chuyển nơi thực thi task, phá giả định owner thread |
| Một pool làm mọi shared state thread-safe | Phải dùng atomic/lock/confinement cho dữ liệu |
| Dùng ThreadLocal là dữ liệu thuộc executor | ThreadLocal thuộc thread cụ thể, không thuộc executor hoặc request |

## 19. Checklist khi chọn executor

**Đúng đắn:**

- [ ] Các task có độc lập hay cùng sửa mutable state?
- [ ] Có cần **tuần tự hóa** hay cho phép hoàn thành không theo thứ tự?
- [ ] Caller có thể đồng thời submit không, và quy tắc thứ tự task là gì?
- [ ] Có task nào submit task con rồi chờ kết quả trong cùng pool?
- [ ] Có callback hoặc side effect nào bị gọi khi đang giữ lock?
- [ ] ThreadLocal có được đặt và remove đúng scope từng task không?

**Tải và tài nguyên:**

- [ ] Loại task là CPU-bound hay blocking, và thời gian chờ điển hình là bao lâu?
- [ ] Biết concurrency mục tiêu, queue capacity và giới hạn connection/thread?
- [ ] Có backpressure hoặc rejection policy rõ khi quá tải?
- [ ] Có metric queue age, active count, rejection, timeout và error?
- [ ] Đã kiểm tra tail latency dưới burst/overload chưa?

**Vòng đời và lỗi:**

- [ ] Executor được shutdown khi hết vòng đời?
- [ ] Có awaitTermination hoặc cơ chế theo dõi shutdown phù hợp?
- [ ] Có chính sách khi task không phản hồi interrupt?
- [ ] Có bắt lỗi qua Future.get, CompletionService hoặc kênh báo lỗi khác?
- [ ] Timeout/cancel không bị nhầm với completion của side effect?
- [ ] Task được submit khi executor đã shutdown sẽ được xử lý thế nào?

## 20. Câu hỏi tự kiểm tra

**1. newFixedThreadPool(4) có chặn submit task thứ năm không?**  
Không theo nghĩa luôn chặn hoặc từ chối khi đã có 4 task. Thường task thứ năm được queue nếu bốn worker đang bận; default queue rất lớn. Muốn bounded backlog, dùng cấu hình/cơ chế khác.

**2. Cached pool có tự giới hạn số thread ở số core CPU không?**  
Không. Khi không có worker rảnh để nhận handoff, cached pool có thể tạo thêm platform thread rất nhiều, đến khi gặp giới hạn cấu hình hoặc tài nguyên.

**3. Single-thread executor có đảm bảo mọi task chạy trên đúng cùng một Thread object suốt đời không?**  
Không. Nó đảm bảo chỉ một task đang thực thi mỗi lúc và tuân theo thứ tự queue; thread thực tế có thể bị thay nếu worker chết.

**4. Nếu submit Callable ném exception, caller có thể lấy thông tin lỗi qua đâu?**  
Future.get() có thể ném ExecutionException chứa cause; cần kiểm tra/ghi nhận thay vì bỏ Future.

**5. ThreadPoolExecutor core=2, max=8 và queue không giới hạn có thường tăng lên 8 worker khi queue dài không?**  
Không nhất thiết. Queue tiếp tục nhận task sau khi đủ core, vì thế maximumPoolSize có thể không được dùng để mở rộng trong điều kiện bình thường.

**6. Khi nào CallerRunsPolicy nguy hiểm cho state chỉ một worker được phép sửa?**  
Khi queue đầy, task có thể chạy trên thread submit, không phải worker owner; giả định confinement bị phá.

**7. shutdown() có giống shutdownNow() không?**  
Không. shutdown không nhận task mới nhưng cho task đã nhận tiếp tục; shutdownNow cố dừng task đang chạy và trả lại task chưa bắt đầu, không bảo đảm dừng thành công.

**8. Future.get(timeout) ném TimeoutException có chứng minh task không còn chạy không?**  
Không. Chỉ caller ngừng chờ theo hạn; task có thể vẫn đang chạy.

**9. Nếu task đầu chạy chậm trong single-thread executor, task sau có chạy trước để giảm trễ không?**  
Không trong cùng executor theo thiết kế tuần tự; chúng đợi task trước, tạo head-of-line blocking.

**10. Có nên dùng cached pool cho mọi thao tác I/O không?**  
Không. Nếu blocking lâu hoặc số request không giới hạn, thread count có thể tăng quá mức. Phải đánh giá tải, tài nguyên và backpressure.

## 21. Tổng kết

**Fixed pool** phù hợp khi cần **giới hạn concurrency** ở mức N worker, nhưng phải quản lý backlog vì queue mặc định không giới hạn thực dụng. **Cached pool** phù hợp với workload task ngắn, từng đợt và có kiểm soát tải ngoài, nhưng có thể tăng số platform thread rất lớn khi tất cả worker đều bận. **Single-thread executor** phù hợp khi cần **tuần tự hóa task và một owner xử lý mutable state**, đổi lại có nguy cơ queue tăng và head-of-line blocking.

Cả ba đều là những cách triển khai của **ExecutorService**: hãy xét **task, worker, queue, rejection, cancellation, Future error và shutdown** cùng nhau. Khi yêu cầu tài nguyên hoặc backpressure chặt chẽ, có thể dùng **ThreadPoolExecutor cấu hình rõ bounded queue và rejection policy**. Executor không thay thế việc chứng minh **happens-before, atomicity và bất biến dữ liệu** của các task được thực thi.
