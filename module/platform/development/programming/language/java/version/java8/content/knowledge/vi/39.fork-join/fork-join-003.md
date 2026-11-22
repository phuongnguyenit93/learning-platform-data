# Executors.newWorkStealingPool trong Java — cơ chế work stealing và cách sử dụng

## 1. Giới thiệu

Khi có nhiều tác vụ độc lập hoặc phép tính có thể chia thành subtasks, chương trình Java cần cách gửi việc tới nhiều worker thay vì tự tạo một Thread cho mỗi việc. **Executors.newWorkStealingPool()** là factory thuộc java.util.concurrent.Executors, có từ Java 8 và **vẫn được hỗ trợ trên JDK hiện đại**. Nó trả một **ExecutorService** có cơ chế **work stealing** — worker rảnh có thể lấy một số công việc còn chờ từ hàng đợi của worker khác.

Bài thuộc chủ đề **Fork/Join** và chỉ trình bày API còn áp dụng hiện nay. Các chương trình độc lập dùng Java 17+, biên dịch bằng **javac --release 17**, với stdout đã kiểm chứng. Bạn sẽ nắm:

1. Hai overload newWorkStealingPool() và newWorkStealingPool(int parallelism).
2. Mục tiêu của work stealing và quan hệ với ForkJoinPool.
3. Lý do **parallelism là mức mục tiêu, không phải số Thread object cứng**.
4. Vì sao pool **không bảo đảm thứ tự chạy** task.
5. Cách dùng submit, execute, invokeAll, CompletionService và Future.get.
6. Cách tự chia một phép tính với RecursiveTask, fork và join.
7. Vòng đời shutdown/awaitTermination, exception, cancellation và lỗi blocking.
8. So sánh với fixed thread pool, commonPool và virtual-thread executor.
9. Tính đúng của kết quả đa luồng, truyền ngữ cảnh và kiểm thử bằng latch.
10. Khi nào nên và không nên chọn work-stealing executor.

## 2. Work stealing hoạt động ra sao?

Một worker có thể tạo hoặc nhận nhiều task. Nếu worker khác đã làm xong việc riêng, nó không nhất thiết phải đứng chờ trong khi worker thứ nhất còn hàng đợi dài. **Work stealing** cho phép một worker rảnh tìm và lấy việc có thể thực hiện từ worker khác, giúp cân bằng tải khi các nhánh có kích thước không đều.

~~~text
Task lớn được chia thành tác vụ nhỏ

  Worker A: [A1][A2][A3][A4]     Worker B: [B1]
              |                          |
             làm A1                     làm B1
              |                          |
             còn A2,A3,A4         B hết việc
              |                          |
              +-------- steal A4 <-------+
              |                          |
             A2,A3                  xử lý A4

Mục tiêu: worker rảnh tham gia xử lý việc đang chờ.
~~~

Sơ đồ là **mô hình ý tưởng**, không phải contract về số lượng queue, cách sắp xếp hay task cụ thể được lấy. JavaDoc không hứa một task luôn chạy trên cùng worker, cũng không hứa FIFO giữa các task được submit.

**Work stealing không tự chia một Callable lớn.** Nếu bạn gửi một Callable chứa vòng lặp chạy một triệu phép tính mà không tạo subtasks, đó vẫn là một task. Muốn nhiều core tham gia vào **cùng bài toán**, thuật toán phải chia công việc (RecursiveTask, parallel decomposition hoặc công cụ tương ứng) và chọn ngưỡng chia hợp lý.

Cơ chế có ích cho divide-and-conquer, nhiều tác vụ ngắn, tải không đồng đều; nhưng không tự biến workload blocking, giao dịch có thứ tự hoặc công việc truy cập tài nguyên độc quyền thành song song hiệu quả.

## 3. Hai cách tạo pool

### Không truyền parallelism

~~~java
// Mảnh mã, cần import java.util.concurrent.*.
ExecutorService pool = Executors.newWorkStealingPool();
~~~

Overload này chọn **số processor khả dụng** làm **mức song song mục tiêu**. Số processor JVM thấy có thể phụ thuộc container quota hoặc cấu hình runtime, không nhất thiết bằng số core vật lý của máy chủ.

### Truyền mức song song mục tiêu

~~~java
// Mảnh mã.
ExecutorService pool = Executors.newWorkStealingPool(4);
~~~

Theo JavaDoc:

- parallelism phải lớn hơn 0; giá trị 0 hoặc âm ném **IllegalArgumentException**.
- parallelism là **target parallelism level**, tức mức tham gia xử lý mong muốn.
- Các worker và thread nội bộ có thể được tạo, tạm dừng hoặc thay đổi động. **Actual thread count không phải một hằng số bằng tham số này**.
- Work-stealing pool có thể dùng nhiều queue để giảm tranh chấp.
- **Không bảo đảm thứ tự thực thi các tác vụ được submit.**
- Target parallelism **không phải quota cứng** cho tổng task đồng thời khi có cơ chế bù thread; cũng không thay được Semaphore/connection pool/rate limiter khi cần giới hạn tài nguyên.

Tạo pool parallelism=1 vẫn hợp lệ, nhưng khi chỉ có một worker đang xử lý CPU work, bạn không thể mong nhiều phép tính CPU cùng thực thi thực sự song song nhờ tên gọi “work stealing”.

**Quan hệ lớp:** Phương thức factory trả kiểu **ExecutorService**. Các JDK thông dụng dùng **ForkJoinPool** phía dưới; nếu chỉ cần submit/get/shutdown, hãy code theo interface. Không cast mù sang ForkJoinPool để dùng API riêng. Nếu phải xem metrics nội bộ như getStealCount, hãy kiểm tra instanceof và hiểu các chỉ số là để quan sát/tuning, không phải dữ liệu giao dịch.

ForkJoinPool.commonPool() là pool dùng chung JVM; pool được tạo bằng newWorkStealingPool là **một pool riêng** cần quản lý vòng đời. Không giả định shutdown một pool riêng sẽ làm shutdown common pool hoặc ngược lại.
## 4. API ExecutorService: submit, execute, invokeAll

Một work-stealing pool vẫn cung cấp hợp đồng ExecutorService, nên ứng dụng không cần tự viết một protocol gửi task riêng.

| Phương thức | Kết quả | Ghi chú |
|---|---|---|
| execute(Runnable) | void | Gửi việc không nhận Future trực tiếp |
| submit(Runnable) | Future<?> | Có thể đợi completion/cancel và nhận lỗi qua Future |
| submit(Callable<T>) | Future<T> | Lấy giá trị T khi hoàn tất |
| invokeAll(Collection<Callable<T>>) | List<Future<T>> | Đợi tất cả, danh sách Future tương ứng thứ tự iterator đầu vào |
| invokeAny(Collection<Callable<T>>) | T | Lấy một kết quả thành công; các task khác có thể bị hủy |
| Future.get() | T hoặc exception | Đợi một task, có thể block caller |
| Future.get(timeout, unit) | T hoặc TimeoutException | Timeout của việc **chờ**, không tự bảo đảm dừng công việc |
| shutdown() | void | Không nhận task mới, cho task đã nhận tiếp tục chạy |
| shutdownNow() | List<Runnable> | Cố ngăn task đang chờ và ngắt task đang thực thi, **best effort** |
| awaitTermination(timeout, unit) | boolean | Chờ pool kết thúc sau khi shutdown |

Không được lẫn **thứ tự Future trong List** với **thứ tự các worker chạy task**. Nếu submit 1,2,3 và lấy kết quả bằng Future.get theo thứ tự 1,2,3, bạn chỉ xác định được vị trí kết quả, không chứng minh task 1 đã chạy trước task 2.

### Thứ tự không được bảo đảm

Javadoc của newWorkStealingPool ghi rõ: “A work-stealing pool makes no guarantees about the order in which submitted tasks are executed.” Vì thế:

- Không dùng pool để thay một queue FIFO nghiêm ngặt.
- Không giả định một tác vụ đã submit trước luôn bắt đầu/kết thúc trước.
- Nếu cần thứ tự business, truyền dependency rõ (CompletableFuture chain), dùng thiết kế serial executor hoặc hệ thống queue có order semantics.
- Nếu cần kết quả xuất theo một thứ tự ổn định, **map kết quả theo ID/index**, hoặc sắp xếp sau khi các task đã hoàn tất.
- Không biến output thread name hoặc thứ tự log của một lần chạy thành test bắt buộc.

### Vì sao không gọi Future.get ngay sau từng submit?

Nếu gửi task rồi lập tức get trước khi gửi task kế tiếp, caller có thể khiến việc submit trở nên **gần như tuần tự**:

~~~java
// PHẢN VÍ DỤ: dễ làm mất khả năng chạy song song.
for (int i = 1; i <= 5; i++) {
    int result = pool.submit(() -> doWork()).get();
    consume(result);
}
~~~

doWork/consume chỉ là hàm minh họa. Đúng hơn, thường **submit toàn bộ task độc lập trước**, rồi thu các Future. Điều này cho phép các worker thực thi những công việc khác nhau đồng thời khi đủ tài nguyên.

## 5. Ví dụ Java hoàn chỉnh 1 — submit nhiều Callable và lấy kết quả

Tạo file **WorkStealingBasicsDemo.java**:

~~~java
import java.util.*;
import java.util.concurrent.*;

public class WorkStealingBasicsDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newWorkStealingPool(3);
        try {
            List<Future<Integer>> futures = new ArrayList<>();
            for (int i = 1; i <= 5; i++) {
                final int number = i;
                futures.add(pool.submit(() -> number * number));
            }

            List<Integer> values = new ArrayList<>();
            for (Future<Integer> future : futures) {
                values.add(future.get());
            }
            int total = values.stream().mapToInt(Integer::intValue).sum();
            System.out.println("results=" + values);
            System.out.println("sum=" + total);
        } finally {
            pool.shutdown();
            System.out.println("shutdown=" + pool.isShutdown());
            System.out.println("terminated="
                    + pool.awaitTermination(10, TimeUnit.SECONDS));
        }
    }
}
~~~

Chạy:

~~~text
javac --release 17 WorkStealingBasicsDemo.java
java WorkStealingBasicsDemo
~~~

Stdout:

~~~text
results=[1, 4, 9, 16, 25]
sum=55
shutdown=true
terminated=true
~~~

**Phân tích từng phần:**

1. Pool có target parallelism=3; 5 Callable tính bình phương lần lượt được submit.
2. Danh sách Future được lưu theo thứ tự **code gửi việc**, không phụ thuộc worker chạy task nào.
3. Duyệt Future và get cho ra [1,4,9,16,25] có thứ tự, dù scheduler không cam kết execution order.
4. Đợi các Future hoàn tất trước khi lấy tổng 55, không thử đoán theo sleep.
5. finally gọi shutdown và awaitTermination để đóng pool được tạo riêng. In true có nghĩa pool thực sự kết thúc trong timeout ở lần chạy kiểm thử.

### Tham số parallelism có giới hạn thực thi không?

Trong ví dụ, target=3 nhưng không in ra “thread count = 3”. Thông tin cần kiểm thử là **tất cả 5 tác vụ hoàn tất và kết quả đúng**. Một thread pool có thể quản lý số lượng thread khác nhau theo thời điểm. Nếu ứng dụng cần quota cứng, hãy có cơ chế hạn chế cấp việc/permit ngoài mức target parallelism.

## 6. Làm sao chứng minh hai tác vụ đang hoạt động cùng lúc?

Dùng Thread.sleep rồi nhìn số thread thường không đáng tin. **CountDownLatch** cho phép hai worker báo đã vào phần xử lý, chờ main xác nhận rồi mới tiếp tục. Với hai task đều đang chờ latch giải phóng, ta biết có hai task đã bắt đầu trước khi đọc active.

Quy tắc:

1. Tăng AtomicInteger active khi vào lambda; cập nhật peak.
2. Gửi tín hiệu started cho main rồi đợi release.
3. Main chờ đủ hai tín hiệu started, đọc active/peak trước khi mở khóa.
4. Main release và lấy Future.get() của cả hai task.
5. finally luôn release latch để không giữ worker vô hạn nếu có exception.

Đây là kiểm thử **trạng thái song song ở một điểm kiểm soát**, không phải benchmark tốc độ, và không dựa vào CPU scheduling cụ thể của các phép tính.
## 7. Ví dụ Java hoàn chỉnh 2 — hai task đồng thời bằng latch

Tạo file **ConcurrentTasksDemo.java**:

~~~java
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;

public class ConcurrentTasksDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newWorkStealingPool(2);
        CountDownLatch started = new CountDownLatch(2);
        CountDownLatch release = new CountDownLatch(1);
        AtomicInteger active = new AtomicInteger();
        AtomicInteger peak = new AtomicInteger();

        Callable<String> first = () -> {
            int current = active.incrementAndGet();
            peak.accumulateAndGet(current, Math::max);
            started.countDown();
            try {
                release.await();
                return "alpha";
            } finally {
                active.decrementAndGet();
            }
        };
        Callable<String> second = () -> {
            int current = active.incrementAndGet();
            peak.accumulateAndGet(current, Math::max);
            started.countDown();
            try {
                release.await();
                return "beta";
            } finally {
                active.decrementAndGet();
            }
        };

        try {
            Future<String> a = pool.submit(first);
            Future<String> b = pool.submit(second);
            if (!started.await(30, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Tasks did not start");
            }
            System.out.println("activeBeforeRelease=" + active.get());
            System.out.println("peak=" + peak.get());
            release.countDown();
            System.out.println("results=" + a.get() + "," + b.get());
            System.out.println("activeAfter=" + active.get());
        } finally {
            release.countDown();
            pool.shutdownNow();
        }
    }
}
~~~

Chạy:

~~~text
javac --release 17 ConcurrentTasksDemo.java
java ConcurrentTasksDemo
~~~

Stdout trên JDK 17 đã kiểm thử:

~~~text
activeBeforeRelease=2
peak=2
results=alpha,beta
activeAfter=0
~~~

**Giải thích:**

- Pool target=2, main submit hai Callable. Mỗi task tăng active, báo started rồi đứng chờ.
- Main chỉ in active sau khi cả hai task đã báo started; tại thời điểm đó active=2 và peak=2.
- Khi release, hai task hoàn tất, Future.get được lấy theo thứ tự a trước b: alpha,beta **không hứa alpha chạy trước beta**.
- activeAfter=0 vì cả hai task đã hoàn tất và thực hiện khối finally giảm active.
- Nếu môi trường không cho cả hai task bắt đầu trong 30 giây, demo báo lỗi rõ thay vì chờ vĩnh viễn.
- Đây là phép thử concurrency, **không đo CPU speedup**. Hai task đang đồng thời tồn tại/đợi không chứng minh chúng cùng sử dụng CPU tại cùng một chu kỳ máy.

## 8. Fork/Join: tự chia bài toán thì mới khai thác được work stealing

Với bài toán cộng dãy số 1..N, một vòng lặp độc lập dài có thể được chia thành hai nửa. **RecursiveTask<V>** cho phép một task tự trả về giá trị V, được thực thi bởi cơ chế Fork/Join.

Thuật toán phổ biến:

~~~text
RangeSum(1..10000)
        |
       chia đôi
        |
        +-------- RangeSum(1..5000)
        |
        +-------- RangeSum(5001..10000)
                       |
                  tiếp tục chia
                       |
                  nhánh đủ nhỏ
                       |
                tính tổng tuần tự
                       |
                 join các nhánh
~~~

Tại mỗi lần compute:

1. Nếu số phần tử đã nhỏ hơn ngưỡng, tính tuần tự và trả kết quả.
2. Nếu còn lớn, tạo hai RecursiveTask đại diện nửa trái/nửa phải.
3. **fork một nhánh**, tính nhánh còn lại ngay trong worker hiện tại.
4. **join nhánh đã fork** và cộng kết quả.

Chiến lược **fork một nhánh, compute một nhánh, join** giúp giảm overhead so với việc fork cả hai nhánh rồi chỉ đứng đợi. Nhưng không có bảo đảm mọi nhánh được chạy trên các worker khác nhau. Worker rảnh có thể steal một subtask, tùy tình trạng tải.

### Chọn ngưỡng chia task

**Ngưỡng quá nhỏ** sinh vô số task rất ngắn, tốn overhead tạo object, queue/scheduling/join. **Ngưỡng quá lớn** khiến ít nhánh đủ để thực thi song song và mất hiệu quả cân bằng. Ngưỡng phù hợp phụ thuộc chi phí phần việc, dữ liệu, cache, số core và workload; không có một con số tối ưu chung. Ví dụ dùng 1.000 phần tử cho dễ đọc, **không phải benchmark chọn threshold tốt nhất**.

### Dùng RecursiveTask trong pool do newWorkStealingPool tạo

Vì API factory trả ExecutorService, chương trình dưới đây submit một Callable. Callable chạy trong worker của pool và gọi **RangeSum.invoke()**. Trong implementation ForkJoinPool của JDK 17, những nhánh fork được xử lý trong pool hiện tại. Không cast ExecutorService sang ForkJoinPool một cách không cần thiết.

Nếu chương trình chuyên biệt cần API ForkJoinPool như invoke(ForkJoinTask), có thể khai báo **new ForkJoinPool(target)** trực tiếp để phụ thuộc implementation tường minh. Với factory newWorkStealingPool, nên tiếp cận qua contract ExecutorService khi có thể.

## 9. Ví dụ Java hoàn chỉnh 3 — chia để trị với RecursiveTask

Tạo file **RecursiveRangeSumDemo.java**:

~~~java
import java.util.concurrent.*;

public class RecursiveRangeSumDemo {
    static final class RangeSum extends RecursiveTask<Long> {
        private final int first;
        private final int last;

        RangeSum(int first, int last) {
            this.first = first;
            this.last = last;
        }

        @Override
        protected Long compute() {
            if (last - first < 1000) {
                long sum = 0;
                for (int n = first; n <= last; n++) {
                    sum += n;
                }
                return sum;
            }
            int middle = first + (last - first) / 2;
            RangeSum left = new RangeSum(first, middle);
            RangeSum right = new RangeSum(middle + 1, last);
            left.fork();
            long rightTotal = right.compute();
            return left.join() + rightTotal;
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newWorkStealingPool(4);
        try {
            Future<Long> total = pool.submit(
                    () -> new RangeSum(1, 10_000).invoke());
            System.out.println("sum1to10000=" + total.get());
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Pool did not terminate");
            }
        }
    }
}
~~~

Chạy:

~~~text
javac --release 17 RecursiveRangeSumDemo.java
java RecursiveRangeSumDemo
~~~

Stdout:

~~~text
sum1to10000=50005000
~~~

**Đọc đúng:** Tổng 1 + ... + 10.000 là 10.000 × 10.001 / 2 = 50.005.000. Tính toán đã được chia theo các RecursiveTask; việc worker nào chạy nhánh nào không được in vì lịch chạy không cố định. Không dùng kết quả này để kết luận fork/join nhanh hơn một vòng lặp 10.000 phần tử: với dữ liệu nhỏ, overhead fork/join có thể làm **chậm hơn tuần tự**.

### Khi nào không chia thành RecursiveTask?

- Task là một lệnh I/O đồng bộ không thể chia thành các công việc độc lập.
- Chi phí per-subtask nhỏ hơn nhiều so với scheduling overhead.
- Các subtasks cần cập nhật một shared mutable object dưới lock lớn khiến thực thi vẫn bị tuần tự hóa.
- Thuật toán không có quan hệ join rõ hoặc có side effect phụ thuộc thứ tự.
- Có rủi ro mỗi task chờ một task khác trong cùng pool bằng Future.get gây liveness kém.
## 10. Thu thập kết quả: thứ tự submit và thứ tự completion

Đối với công việc độc lập có thời gian thực thi khác nhau, bạn có thể muốn đọc kết quả **theo input order** hoặc **ngay khi task nào hoàn tất**. Đây là hai hợp đồng khác nhau.

### invokeAll trả danh sách Future theo thứ tự đầu vào

~~~java
// Mảnh mã, jobs là List<Callable<String>>.
List<Future<String>> futures = pool.invokeAll(jobs);
for (Future<String> future : futures) {
    System.out.println(future.get());
}
~~~

invokeAll đợi tất cả task hoàn tất, rồi Future trong danh sách kết quả tương ứng với thứ tự iterator của collection đầu vào. Điều đó **không** có nghĩa task được thực thi theo thứ tự ấy. Khi một task ném lỗi, Future tương ứng có trạng thái exceptional và get ném ExecutionException.

### ExecutorCompletionService trả theo thứ tự hoàn tất

~~~java
// Mảnh mã, imports java.util.concurrent.*.
CompletionService<Integer> results =
        new ExecutorCompletionService<>(pool);
results.submit(() -> 10);
Future<Integer> firstCompleted = results.take();
~~~

take() chờ một Future **đã hoàn tất**. Nếu nhiều task đã xong trước khi consumer lấy, thứ tự nhận phản ánh queue completion, không phải danh sách submission. **Không được giả định firstCompleted là task đầu tiên submit**, cũng không được sử dụng completion order như một thứ tự nghiệp vụ ổn định.

Nếu muốn vừa xử lý sớm vừa xuất báo cáo có thứ tự, gắn **ID/input index** vào kết quả rồi sort hoặc dùng cấu trúc map theo index sau khi hoàn tất. Việc sort làm output deterministic nhưng không thay đổi lịch thực thi của pool.

## 11. Ví dụ Java hoàn chỉnh 4 — invokeAll và CompletionService

Tạo file **InvokeAllResultsDemo.java**:

~~~java
import java.util.*;
import java.util.concurrent.*;

public class InvokeAllResultsDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newWorkStealingPool(3);
        try {
            List<Callable<String>> jobs = List.of(
                    () -> "task-A",
                    () -> "task-B",
                    () -> "task-C"
            );
            List<Future<String>> futures = pool.invokeAll(jobs);
            List<String> results = new ArrayList<>();
            for (Future<String> future : futures) {
                results.add(future.get());
            }
            System.out.println("submissionMappedResults=" + results);

            CompletionService<Integer> completion =
                    new ExecutorCompletionService<>(pool);
            for (int n : new int[]{5, 2, 8}) {
                final int value = n;
                completion.submit(() -> value * 10);
            }
            List<Integer> completed = new ArrayList<>();
            for (int i = 0; i < 3; i++) {
                completed.add(completion.take().get());
            }
            Collections.sort(completed);
            System.out.println("sortedCompleted=" + completed);
        } finally {
            pool.shutdown();
            pool.awaitTermination(10, TimeUnit.SECONDS);
        }
    }
}
~~~

Chạy:

~~~text
javac --release 17 InvokeAllResultsDemo.java
java InvokeAllResultsDemo
~~~

Stdout:

~~~text
submissionMappedResults=[task-A, task-B, task-C]
sortedCompleted=[20, 50, 80]
~~~

Giải thích:

1. invokeAll bảo đảm danh sách Future tương ứng với thứ tự jobs nên output có thứ tự A,B,C.
2. CompletionService thu ba giá trị bằng take theo lịch completion thực tế, nhưng code **sort** lại trước khi in, nên output [20,50,80] xác định.
3. Nếu bỏ sort, thứ tự printed list có thể khác giữa các lần chạy. Đó là **behavior hợp lệ**, không phải lỗi.
4. Các Callable đủ nhỏ, không có side effect phụ thuộc thứ tự.
5. finally đóng pool, không dựa vào việc daemon worker tự biến mất.

### invokeAny có được coi là “task submit đầu tiên” không?

Không. invokeAny trả một kết quả thành công từ một trong các tác vụ. Lựa chọn có thể phụ thuộc completion timing. Nếu cần kết quả từ task có **độ ưu tiên nghiệp vụ** hoặc **index nhỏ nhất**, không dùng invokeAny thay cho bộ so sánh kết quả.

## 12. Hoàn tất lỗi: Future.get và RejectedExecutionException

Các tác vụ chạy đồng thời có thể ném exception. Với **submit(Callable<T>)**, exception được nắm giữ trong Future. Khi gọi **get()**, caller nhận **ExecutionException**, và nguyên nhân ban đầu nằm trong **getCause()**.

~~~java
// Mảnh mã, một Callable ném IllegalStateException.
Future<String> failure = pool.submit(() -> {
    throw new IllegalStateException("bad input");
});
try {
    failure.get();
} catch (ExecutionException ex) {
    Throwable cause = ex.getCause();
    // Log/handle cause theo chính sách.
}
~~~

Khi pool đã **shutdown**, nó không chấp nhận tác vụ mới. Lời gọi submit thường ném **RejectedExecutionException**. Nếu hệ thống dùng custom rejection policy hoặc saturation, cũng cần xử lý việc từ chối khi tài nguyên không đủ.

### Khi một worker lỗi thì pool có hoàn toàn ngừng chạy không?

Không nên suy luận như vậy. Exception của một Callable được chuyển thành exceptional completion của Future; pool có thể tiếp tục xử lý các tác vụ khác. Ứng dụng cần đọc get/kiểm tra lỗi của từng Future quan trọng và quyết định retry, fail-fast hoặc partial success. Không bỏ Future rồi cho rằng exception sẽ tự xuất hiện trong thread main.

### Timeout không tự giết công việc

Future.get(1, SECONDS) có thể ném TimeoutException khi caller chờ quá lâu. Nó không chứng minh underlying task đã dừng. Future.cancel(true) yêu cầu hủy và có thể gửi interrupt theo implementation, nhưng task có thể không phản hồi interruption. Cần thiết kế timeout ở lớp I/O, cancellation cooperation và dọn resource. Không sử dụng shutdownNow như một cam kết cưỡng chế dừng mọi Runnable.

## 13. Ví dụ Java hoàn chỉnh 5 — xử lý lỗi và shutdown pool

Tạo file **FailureAndLifecycleDemo.java**:

~~~java
import java.util.concurrent.*;

public class FailureAndLifecycleDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newWorkStealingPool(2);
        try {
            Future<String> good = pool.submit(() -> "ok");
            Future<String> bad = pool.submit(() -> {
                throw new IllegalStateException("failed");
            });
            System.out.println("good=" + good.get());
            try {
                bad.get();
            } catch (ExecutionException expected) {
                System.out.println("errorType="
                        + expected.getCause().getClass().getSimpleName());
            }
        } finally {
            pool.shutdown();
        }
        try {
            pool.submit(() -> 99);
        } catch (RejectedExecutionException expected) {
            System.out.println("submitAfterShutdown=RejectedExecutionException");
        }
        System.out.println("terminated="
                + pool.awaitTermination(10, TimeUnit.SECONDS));
    }
}
~~~

Chạy:

~~~text
javac --release 17 FailureAndLifecycleDemo.java
java FailureAndLifecycleDemo
~~~

Stdout:

~~~text
good=ok
errorType=IllegalStateException
submitAfterShutdown=RejectedExecutionException
terminated=true
~~~

**Kết quả:** Một task thất bại không làm mất kết quả của task good; lỗi được lấy qua Future.get. Sau shutdown, pool từ chối submit mới. Chương trình gọi awaitTermination để chờ kết thúc, tránh rò rỉ tài nguyên. Đây là demo với task hữu hạn; trên production, có thể cần timeout, escalation, logging và handling khi awaitTermination trả false.

### Chiến lược shutdown chuẩn

1. Dừng tiếp nhận công việc mới bằng shutdown().
2. awaitTermination với timeout hợp lý.
3. Nếu quá hạn và business cho phép, gọi shutdownNow() để yêu cầu hủy các task đang chờ/đang chạy.
4. Khôi phục cờ interrupted nếu thread hiện tại bị InterruptException.
5. Theo dõi các Future/công việc chưa hoàn tất để không bỏ dữ liệu nghiệp vụ.

**Lưu ý JDK:** ExecutorService.close() là API hiện đại ở các JDK mới, nhưng để các ví dụ biên dịch bằng Java 17, bài sử dụng shutdown/awaitTermination. Không đưa lệnh close() vào demo được gắn nhãn Java 17.
## 14. CompletableFuture và chọn đúng Executor

CompletableFuture có các overload **supplyAsync(Supplier<T>, Executor)** và **runAsync(Runnable, Executor)**. Nếu muốn một pipeline sử dụng **pool riêng** bạn đã tạo, phải truyền pool vào đúng nơi cần:

~~~java
// Mảnh mã: tính dữ liệu trên pool do mình quản lý.
ExecutorService pool = Executors.newWorkStealingPool(4);
CompletableFuture<Integer> calculated =
        CompletableFuture.supplyAsync(() -> 21 * 2, pool);
~~~

Nếu bỏ tham số Executor, **CompletableFuture.supplyAsync(...)** thường dùng default async execution facility; với CompletableFuture chuẩn, đó là **ForkJoinPool.commonPool()** (hoặc fallback thread khi common pool không hỗ trợ parallelism ít nhất 2). Nó **không tự tìm pool** được tạo bởi newWorkStealingPool trong một dòng khác.

Tương tự, **thenApply(...)** không tạo một scheduling boundary và có thể chạy ở thread hoàn tất upstream hoặc caller completion khác. Nếu phần tiếp theo phải chạy trên workload-specific executor, dùng **thenApplyAsync(fn, pool)** hoặc phương thức Async tương ứng có Executor.

### ThreadLocal không tự động truyền qua pool

Các thông tin đặt vào ThreadLocal của caller, logging MDC, trace ID, tenant ID, principal hay transaction context **không tự động đi theo một Runnable/Callable** được gửi tới worker:

~~~java
// Mảnh mã minh họa:
ThreadLocal<String> trace = new ThreadLocal<>();
trace.set("request-17");

Future<String> value = pool.submit(() -> trace.get());
// Worker thường thấy null nếu chưa được set context riêng.
~~~

**Ưu tiên** đưa business context vào tham số hoặc immutable record rồi capture nó tường minh trong lambda. Nếu framework thực sự cần MDC/ThreadLocal, dùng cơ chế propagation của framework hoặc snapshot/restore giá trị trong try/finally; không để dữ liệu request trước đó rò rỉ trên worker tái sử dụng.

Không copy tùy tiện transaction hoặc security context thread-bound chỉ bằng một ThreadLocal: chúng còn ràng buộc lifecycle, resource và quyền truy cập.

## 15. Ví dụ Java hoàn chỉnh 6 — CompletableFuture và request context

Tạo file **FutureContextDemo.java**:

~~~java
import java.util.concurrent.*;

public class FutureContextDemo {
    private static final ThreadLocal<String> TRACE = new ThreadLocal<>();

    public static void main(String[] args) {
        ExecutorService pool = Executors.newWorkStealingPool(2);
        try {
            TRACE.set("request-17");
            String captured = TRACE.get();

            CompletableFuture<String> without =
                    CompletableFuture.supplyAsync(
                            () -> String.valueOf(TRACE.get()), pool);
            CompletableFuture<String> with =
                    CompletableFuture.supplyAsync(
                            () -> captured + ":done", pool);

            System.out.println("mainTrace=" + TRACE.get());
            System.out.println("workerTrace=" + without.join());
            System.out.println("explicitContext=" + with.join());
        } finally {
            TRACE.remove();
            pool.shutdown();
        }
    }
}
~~~

Chạy:

~~~text
javac --release 17 FutureContextDemo.java
java FutureContextDemo
~~~

Stdout:

~~~text
mainTrace=request-17
workerTrace=null
explicitContext=request-17:done
~~~

**Phân tích:**

1. Main có TRACE=request-17.
2. Task Async được gửi tới worker qua pool riêng. ThreadLocal thông thường trên worker không kế thừa giá trị của main, nên workerTrace=null.
3. Mã capture chuỗi bất biến captured ở main và dùng tường minh trong lambda, cho explicitContext=request-17:done.
4. Trong finally, ThreadLocal của main được remove và pool được shutdown.
5. Demo không dựa vào tên worker, thứ tự chạy hai Future hoặc số worker cụ thể; nó kiểm chứng semantics của context.

**Cảnh báo:** Nếu context chứa thông tin nhạy cảm, capture đúng giá trị tối thiểu cần thiết, bảo đảm quyền truy cập và vòng đời của nó. Ví dụ chỉ là một trace ID đơn giản, **không phải công thức copy security/session/transaction context**.

## 16. Pool work stealing có phù hợp với blocking I/O không?

Cơ chế ForkJoinPool tối ưu cho những task có thể tính toán, chia nhánh và join theo cấu trúc. Nếu nhiều task thực hiện **blocking I/O không được quản lý** như JDBC đồng bộ, socket read hoặc chờ lock lâu, những worker có thể bị giữ và không còn đủ worker để xử lý task khác.

JavaDoc ForkJoinPool nói rằng pool có thể cố giữ mức parallelism bằng việc bù worker trong một số tình huống join/managed blocking, **nhưng không bảo đảm điều chỉnh trong trường hợp blocking I/O hoặc synchronization không được quản lý**.

### ForkJoinPool.ManagedBlocker

API **ForkJoinPool.managedBlock(ManagedBlocker)** cho phép mô tả một blocking operation theo cách pool có thể nhận diện để bù worker trong một số trường hợp. Nó không biến mọi thao tác I/O thành non-blocking, cũng không tự cấp backpressure, timeout hoặc bảo đảm worker mới luôn có thể được tạo.

Nếu dùng ManagedBlocker, phải triển khai đúng **isReleasable()** và **block()**, có handling InterruptedException và test liveness; đừng thêm vào một chương trình đơn giản chỉ vì pool có chữ ForkJoin.

### Vòng lặp chờ có thể gây starvation

Một anti-pattern:

~~~java
// PHẢN VÍ DỤ: một worker của pool ít thread chờ task
// khác cũng phải được gửi tới cùng pool.
Future<Integer> outer = pool.submit(() -> {
    Future<Integer> inner = pool.submit(() -> 42);
    return inner.get(); // Có rủi ro liveness khi worker khan hiếm.
});
~~~

Ví dụ chỉ minh họa rủi ro, **không yêu cầu thực thi như chương trình độc lập**. Với cùng một pool, có thể có trường hợp nested wait được hỗ trợ, nhưng không được dựa vào cơ chế bù worker để giải quyết mọi vòng chờ do ứng dụng tạo ra. Một chuỗi tác vụ vừa block I/O vừa đợi Future có thể dẫn tới thread starvation hoặc deadlock tùy điều kiện.

**Giải pháp:** Dùng ForkJoinTask.fork/join theo cấu trúc nếu bài toán divide-and-conquer, hoặc CompletableFuture.thenCompose khi có dependency bất đồng bộ. Đưa blocking workload vào executor được quản lý phù hợp (ví dụ pool I/O giới hạn hoặc virtual-thread executor trên JDK 21+ khi phù hợp), đồng thời đặt giới hạn kết nối, timeout và cancellation.

## 17. Chọn giữa các loại executor

| Executor | Đặc tính | Nên cân nhắc khi | Không tự bảo đảm |
|---|---|---|---|
| newWorkStealingPool(n) | Work stealing, parallelism mục tiêu | Nhiều task CPU hoặc fork/join không đồng đều | FIFO, thread count cố định |
| newFixedThreadPool(n) | Số worker hoạt động giới hạn theo cấu hình, hàng đợi chung | Muốn mô hình worker dễ dự đoán cho task đơn giản | Queue bounded (factory mặc định dùng queue unbounded) |
| ForkJoinPool.commonPool() | Pool dùng chung trong JVM | Nhiều phép tính nhỏ, tài nguyên chung chấp nhận được | Cô lập workload hoặc lifecycle riêng |
| newSingleThreadExecutor() | Thực thi tuần tự, một worker hoạt động | Cần tránh cập nhật đồng thời, xử lý theo hàng tuần tự | Throughput song song |
| newVirtualThreadPerTaskExecutor() (Java 21+) | Virtual thread cho mỗi task, đặc biệt hữu ích với blocking I/O phù hợp | Mã blocking có concurrency cao | Giới hạn số việc đang chạy hoặc limit DB connections |
| newScheduledThreadPool(n) | Lập lịch task trễ/định kỳ | Timer, retry sau delay, periodic jobs | Thay thế work stealing cho CPU fork/join |

**Lưu ý phiên bản:** Virtual threads được chuẩn hóa từ Java 21; ví dụ Java 17 trong bài không sử dụng chúng. Không có một executor đúng cho mọi hệ thống. Có thể chọn ForkJoinPool trực tiếp nếu cần điều khiển các tham số nâng cao/monitoring; có thể chọn ThreadPoolExecutor nếu cần queue giới hạn và rejection policy cụ thể.

### Thread daemon không thay thế shutdown

JavaDoc ForkJoinPool hiện hành cho biết worker do pool tạo có trạng thái **daemon**. Vì thế chương trình không được dựa vào các worker daemon để giữ JVM sống sau khi main thoát. Dù vậy, bạn **vẫn phải quản lý lifecycle** và đợi các task quan trọng, không xem daemon là cơ chế dọn tài nguyên thay cho shutdown/awaitTermination.

### Không dùng work stealing khi cần thứ tự nghiêm ngặt

Nếu một hệ thống xử lý sự kiện phải ghi theo thứ tự 1, 2, 3 để bảo toàn nghiệp vụ, pool work stealing không phải công cụ giữ thứ tự. Hãy dùng một queue có ordering contract, partition theo key, một serial executor hoặc ràng buộc dependency trực tiếp. Đừng thử giải quyết bằng cách sleep hoặc dựa vào thread name.
## 18. Những lỗi phổ biến cần tránh

### 18.1. Tưởng newWorkStealingPool tự động chia mỗi Callable

**Sai.** Nếu Callable là một phép tính lớn không chia subtasks, một worker có thể phải xử lý toàn bộ. Work stealing phân phối **các task có sẵn**; không tự biến một vòng lặp tuần tự thành thuật toán song song.

### 18.2. Cho rằng parallelism=n là pool có đúng n thread bất biến

**Sai.** Đây là mức song song mục tiêu; số thread thực có thể thay đổi và cơ chế bù worker có thể tạo thread bổ sung. Không dùng tham số làm hard capacity limit cho kết nối DB hoặc yêu cầu đồng thời.

### 18.3. Cho rằng submit theo thứ tự thì chạy theo thứ tự

**Sai.** JavaDoc ghi không bảo đảm execution order. Thứ tự kết quả từ List<Future> hoặc invokeAll chỉ phản ánh cách **caller thu thập kết quả**.

### 18.4. Gọi Future.get sau mỗi submit

Khi caller đợi task trước xong mới submit task sau, việc gửi tác vụ bị tuần tự hóa, hạn chế parallelism. Đối với các tác vụ độc lập, submit một batch rồi thu kết quả theo nhu cầu.

### 18.5. Nghĩ fork/join luôn nhanh hơn for-loop tuần tự

**Sai.** Tạo, lên lịch và join subtasks có overhead. Với đầu vào nhỏ hoặc task quá nhẹ, thuật toán tuần tự có thể nhanh hơn. Benchmark khi quy mô thực tế và so sánh correctness trước.

### 18.6. Fork quá nhiều subtasks siêu nhỏ

Threshold quá thấp làm nổ số task, gây allocation/scheduling overhead. Dùng ngưỡng có cơ sở từ workload và performance measurement.

### 18.7. Join/get task khác trong pool ít worker mà không kiểm tra liveness

Nested blocking có thể làm worker khan hiếm hoặc deadlock. Dùng ForkJoinTask.fork/join theo thiết kế hoặc composition không blocking, và quản lý tài nguyên.

### 18.8. Đưa toàn bộ blocking I/O lên work-stealing pool

Không có bảo đảm bù worker cho I/O blocking tùy ý. Cần pool dành cho I/O, virtual threads JDK 21+ hoặc async I/O nếu phù hợp; kết hợp timeout, backpressure và giới hạn tài nguyên.

### 18.9. Tin rằng shutdownNow dừng được mọi Runnable tức thì

Đây chỉ là **best-effort**. Task có thể bỏ qua interrupt hoặc kẹt I/O không phản hồi. Cần cơ chế hủy hợp tác và cleanup.

### 18.10. Quên đóng pool riêng

Pool tạo bởi newWorkStealingPool không phải commonPool tự động được ứng dụng chia sẻ theo lifecycle. Cần shutdown, awaitTermination hoặc resource owner quản lý; worker daemon không bảo đảm task quan trọng kết thúc trước khi JVM dừng.

### 18.11. Cho rằng Future.get(timeout) ngắt tác vụ khi hết hạn

Timeout chỉ kết thúc **lần chờ của caller**, không bảo đảm computation đã dừng. Nếu cần cancel, gọi cancel với chính sách phù hợp và quản lý cleanup.

### 18.12. Bỏ Future mà không xử lý exception

Callable có thể thất bại và exception nằm trong Future. Nếu không get hoặc không giám sát outcome, lỗi nghiệp vụ có thể bị bỏ sót.

### 18.13. Truyền ThreadLocal/MDC ngầm sang các worker

Worker thường không có context của caller; worker pool tái sử dụng thread có thể gây nhiễm context. Truyền immutable context hoặc dùng propagation đúng của framework với restore/clear trong finally.

### 18.14. Đồng bộ hóa toàn bộ tác vụ bằng một lock lớn

Nhiều task chạy trên nhiều thread nhưng đều phải chờ một lock có thể hoạt động gần như tuần tự. Kiểm tra contention của **dữ liệu và lock**, không chỉ có bao nhiêu worker.

### 18.15. Dùng commonPool mà tưởng là pool vừa tạo

Nếu gọi CompletableFuture.supplyAsync mà không truyền Executor, nó không tự biết pool nào bạn đã tạo. Phải chỉ định pool tường minh tại các boundary cần cô lập.

### 18.16. Dựa trên chỉ số getStealCount như một counter giao dịch

ForkJoinPool metrics phục vụ tuning và có tính quan sát, không phải business ledger. getStealCount bằng 0 không chứng minh pool không thực hiện công việc hữu ích, và kết quả có thể thay đổi giữa lần đọc.

### 18.17. Dùng Thread.sleep để kiểm thử thứ tự chạy

Scheduler không hứa một task được start đúng sau N milliseconds. Dùng CountDownLatch, Future hoặc các điểm đồng bộ xác định; chỉ kiểm tra kết quả cần bảo đảm.

### 18.18. Quên rằng CPU quota và target parallelism có thể khác môi trường

Số processor khả dụng dưới container/VM có thể khác laptop. Tập tối ưu chỉ trên máy dev không bảo đảm production có throughput tương tự.

### 18.19. Dùng một work-stealing pool để bảo vệ tài nguyên hiếm

Mức parallelism không phải quota toàn hệ thống. Cần Semaphore, connection pool có max connections, rate limiter, queue bounded hoặc backpressure theo business constraint.

### 18.20. Dựa vào Thread/ForkJoinPool nội bộ khi contract chỉ trả ExecutorService

Factory hứa một work-stealing ExecutorService. Trên JDK dùng ForkJoinPool bạn có thể introspect, nhưng không cast mù nếu chưa xác minh; thiết kế trên interface khi chỉ cần lifecycle và Future.

## 19. Checklist đưa newWorkStealingPool vào production

1. Công việc chủ yếu CPU-bound, chia nhỏ được hay là blocking I/O?
2. Có những subtasks độc lập hoặc ForkJoinTask fork/join thật sự không?
3. Parallelism mục tiêu lấy theo processor khả dụng hay cấu hình explicit?
4. Có hiểu parallelism không phải giới hạn cứng của tổng thread/connection không?
5. Có tránh phụ thuộc vào thứ tự task được thực thi không?
6. Có gắn index/key để trả kết quả có thứ tự khi cần không?
7. Có tránh submit-get từng task gây thực thi gần tuần tự không?
8. Có threshold hợp lý nếu dùng RecursiveTask?
9. Có tránh join/get chặn worker cần để chạy chính việc đang được chờ không?
10. Nếu dùng CompletableFuture, đã truyền Executor vào supplyAsync/thenApplyAsync đúng boundary chưa?
11. Có truyền request/trace/tenant context tường minh và dọn ThreadLocal đúng không?
12. Có chặn high-cardinality/unbounded task submissions từ phía người dùng không?
13. Có đo queue wait, throughput, task latency, memory và worker saturation?
14. Có quy định timeout/cancellation và cách xử lý task lỗi?
15. Có shutdown/awaitTermination theo lifecycle của service/container?
16. Có test trên JDK và CPU quota gần môi trường thực tế?
17. Nếu dùng monitoring ForkJoinPool, có hiểu các số là quan sát và phụ thuộc implementation?
18. Nếu cần strict FIFO, rate limit hoặc blocking-heavy, có chọn executor/primitive phù hợp hơn không?

## 20. Đo hiệu năng cho đúng

Không có bảo đảm newWorkStealingPool luôn nhanh hơn newFixedThreadPool. Benchmark nên phản ánh đúng workload:

- **Nhiều task độc lập:** số task, kích thước task và độ lệch thời gian xử lý.
- **Divide-and-conquer:** ngưỡng chia, số nhánh, kích thước dữ liệu và chi phí join.
- **Read/write contention:** mức truy cập shared state, synchronization, atomic updates và cache.
- **Tài nguyên phần cứng:** số core thực, container quota, OS, JDK, warmup/JIT và GC.
- **Pool reuse:** không tính chi phí tạo pool mới trong mỗi request nếu production tái sử dụng pool.
- **End-to-end latency:** đo cả queue wait time, xử lý và completion; không chỉ tính thời gian trong Callable.
- **Saturation:** thử workload vượt năng lực xử lý và phản ứng khi quá tải.
- **Đo đúng:** dùng JMH cho microbenchmark có CPU measurement phù hợp, có warmup, forks và tránh dead-code elimination.

Không đưa ra “nhanh hơn X lần” nếu chưa đo. Thực thi song song giúp khi có **đủ việc độc lập và tài nguyên**; với task nhỏ, overhead phân chia và join có thể làm chậm hơn.

## 21. Bài tập tự kiểm tra

**Câu 1.** newWorkStealingPool() mặc định dùng tham số gì?

*Đáp án:* Số processor khả dụng làm target parallelism, không phải hard limit worker thread.

**Câu 2.** newWorkStealingPool(0) có hợp lệ không?

*Đáp án:* Không. Giá trị parallelism phải lớn hơn 0, nếu không ném IllegalArgumentException.

**Câu 3.** Pool có bảo đảm task được chạy theo thứ tự submit không?

*Đáp án:* Không. Work-stealing pool không hứa order of execution.

**Câu 4.** Tại sao List<Future> có thể cho output A,B,C dù task hoàn tất theo C,A,B?

*Đáp án:* Vì caller gọi Future.get theo các vị trí cố định trong danh sách Future, không in theo completion order.

**Câu 5.** Work stealing có tự chia một Callable lớn không?

*Đáp án:* Không. Chương trình cần tự tạo subtasks hoặc dùng thuật toán hỗ trợ chia việc.

**Câu 6.** RecursiveTask thường sử dụng fork và join như thế nào?

*Đáp án:* Chia bài toán, fork một nhánh, tính nhánh còn lại và join để tổng hợp; ngừng chia ở ngưỡng phù hợp.

**Câu 7.** CompletionService.take có lấy task đầu tiên submit không?

*Đáp án:* Không. Nó lấy Future từ queue những task đã hoàn tất theo thứ tự completion được nhận.

**Câu 8.** newWorkStealingPool có dùng chung object với ForkJoinPool.commonPool không?

*Đáp án:* Không. Nó tạo pool riêng, có lifecycle do ứng dụng sở hữu.

**Câu 9.** Vì sao nhiều blocking I/O có thể gây thiếu worker?

*Đáp án:* Các worker chờ I/O thay vì tính task khác; bù worker không được bảo đảm với mọi thao tác blocking không quản lý.

**Câu 10.** CompletableFuture.supplyAsync() không có Executor có tự chọn pool riêng của ứng dụng không?

*Đáp án:* Không. Với CompletableFuture chuẩn, nó dùng default async facility; muốn dùng pool riêng cần truyền Executor.

**Câu 11.** Vì sao ThreadLocal của main không tự có trên worker?

*Đáp án:* ThreadLocal gắn với từng Thread. Truyền dữ liệu request tường minh hoặc propagation của framework.

**Câu 12.** Có nên dùng shutdownNow để dừng mọi I/O tức thì?

*Đáp án:* Không bảo đảm. shutdownNow chỉ cố gắng hủy/ngắt, cần handling hợp tác và timeout I/O.

**Câu 13.** Khi nào target parallelism không đủ để bảo vệ dữ liệu?

*Đáp án:* Khi cần limit tài nguyên hoặc atomic ordering. Dùng Semaphore, queue bounded, lock/CAS hoặc cơ chế nghiệp vụ riêng.

**Câu 14.** Vì sao cần CountDownLatch trong demo kiểm thử đồng thời?

*Đáp án:* Nó tạo điểm đồng bộ xác định giữa worker và main, thay vì dựa vào sleep/timing ngẫu nhiên.

**Câu 15.** Có thể kết luận work stealing nhanh hơn một for-loop dựa vào demo tính 1..10000 không?

*Đáp án:* Không. Cần đo benchmark có kiểm soát; overhead ForkJoinTask có thể lớn hơn lợi ích song song với bài nhỏ.

## 22. Các mẫu tích hợp theo từng nhu cầu

### Một batch tính toán dữ liệu, trả kết quả theo ID

Nếu bạn nhận nhiều input độc lập và cần kết quả theo đúng ID, hãy tạo một Future cho mỗi input, lưu trong map **ID -> Future<T>**, rồi lấy Future.get ở điểm tổng hợp và ghi lại cùng ID. Work-stealing pool chỉ được dùng làm cơ chế **thực thi**, không làm nguồn sự thật về thứ tự business. Nếu cần trả kết quả sớm, dùng CompletionService nhưng phải mang theo ID và quản lý lỗi của từng task.

### Phép tính chia để trị trên tập dữ liệu lớn

Nếu bài toán có thể chia thành các khoảng không giao nhau, dùng RecursiveTask với threshold phù hợp. Phép gộp của các nhánh phải **an toàn theo thứ tự** mà thuật toán gộp thực hiện; với các phép tổng hợp floating-point, thứ tự có thể ảnh hưởng kết quả số học. Với shared mutable accumulator, cần đồng bộ đúng hoặc để mỗi nhánh trả giá trị riêng rồi reduce.

### Dịch vụ có nhiều blocking request

Nếu mỗi task chủ yếu chờ DB hoặc HTTP, work stealing có thể không phải lựa chọn tốt nhất. Dùng kiến trúc I/O được quản lý, giới hạn kết nối, timeout và có thể virtual-thread-per-task executor trên JDK 21+ khi phù hợp. **Virtual threads không tự giới hạn số query hoặc số request**, vì vậy vẫn cần quota và backpressure.

### Tác vụ có thứ tự hoặc truy cập state có tính giao dịch

Nếu cần bảo toàn thứ tự cập nhật, nên xử lý theo một queue/partition có owner, hoặc dùng dependency chain. **Work stealing và một tập task độc lập không cung cấp transaction hay thứ tự toàn cục.** Nhiều worker cùng đọc rồi ghi một state không thread-safe có thể gây data race ngay cả khi các task được pool quản lý hợp lệ.

### Tách pool theo loại workload

Bạn có thể có một pool CPU work stealing riêng cho các phép chia việc, một pool I/O với concurrency giới hạn và một scheduler quản lý delayed tasks. Điều này giảm nguy cơ một workload block cả hệ thống. Nhưng đừng tạo **mỗi request một pool mới**; các pool nên do container/service quản lý lifecycle, metrics và shutdown.

## 23. Ghi chú tương thích và thay đổi JDK

- **Executors.newWorkStealingPool() và (int)** đã có từ Java 8 và vẫn còn trong JavaDoc JDK hiện đại.
- **ForkJoinPool** có thêm khả năng monitoring và lifecycle trong các JDK mới; code Java 17 ở đây chỉ dựa vào các API tương thích.
- **ExecutorService.close()** có trong các JDK mới hơn Java 17. Để các lệnh chạy vẫn tương thích **--release 17**, bài sử dụng **shutdown()/awaitTermination()**.
- **Executors.newVirtualThreadPerTaskExecutor()** có từ Java 21; đây là lựa chọn khác cho workload phù hợp, không phải lý do coi work-stealing pool là legacy.
- Behavior hiện tại của implementation ForkJoinPool không có nghĩa ứng dụng được bảo đảm về thread name, queue internals, số task được steal, hoặc FIFO.
- Tên pool trả về qua interface là ExecutorService; khi cần một tính năng ForkJoinPool-specific, ưu tiên chủ động chọn ForkJoinPool và document sự phụ thuộc, thay vì cast bất chấp implementation.

## Tài liệu tham khảo chính thức, còn được duy trì

- Oracle Java SE 25 — **Executors**, hai overload newWorkStealingPool và ý nghĩa parallelism: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Executors.html
- Oracle Java SE 25 — **ForkJoinPool**, work stealing, worker daemon, managedBlock và monitoring: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ForkJoinPool.html
- Oracle Java SE 25 — **ForkJoinTask**, fork/join/invoke và execution model: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ForkJoinTask.html
- Oracle Java SE 25 — **RecursiveTask**, compute và kết quả: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/RecursiveTask.html
- Oracle Java SE 25 — **ExecutorService**, shutdown, invokeAll, invokeAny và Future: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ExecutorService.html
- Oracle Java SE 25 — **Future**, get, cancel, timeout và outcome: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Future.html
- Oracle Java SE 25 — **ExecutorCompletionService**, queue kết quả khi hoàn tất: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ExecutorCompletionService.html
- Oracle Java SE 25 — **CompletableFuture**, supplyAsync và Executor: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/CompletableFuture.html
- Oracle Java SE 25 — **CountDownLatch**, điểm chờ xác định: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/CountDownLatch.html
- Oracle Java SE 25 — **ThreadLocal**, context gắn với thread: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ThreadLocal.html
- Oracle Java SE 25 — **ThreadPoolExecutor**, mô hình fixed pool, queue và rejection: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html

**Kết luận:** Executors.newWorkStealingPool là factory **hiện hành** cho ExecutorService hỗ trợ work stealing, hữu ích khi có nhiều công việc có thể xử lý song song và đặc biệt khi các nhánh fork/join có khối lượng khác nhau. **Parallelism là mục tiêu chứ không phải hard thread cap; thứ tự thực thi không được bảo đảm.** Work stealing phân phối các task có sẵn, không tự chia một Callable lớn. Chọn đúng kiểu task, tự xác định dependency/order khi cần, kiểm soát blocking, lifecycle và exception, dùng Future/CountDownLatch để kiểm thử thay vì đoán lịch chạy.