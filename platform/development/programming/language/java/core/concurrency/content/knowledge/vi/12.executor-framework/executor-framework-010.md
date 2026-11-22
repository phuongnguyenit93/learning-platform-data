# Submit tác vụ độc lập và tránh thread starvation trong Java Executor Framework

## Mục tiêu

Sau bài này, bạn có thể:

- Phân biệt việc **submit nhiều tác vụ độc lập** với việc một tác vụ đang chạy lại chờ kết quả của tác vụ khác.
- Hiểu `ExecutorService`, `submit`, `Future`, hàng đợi và số worker ảnh hưởng tới tiến độ như thế nào.
- Nhận ra tình huống **thread starvation**, đặc biệt là *thread-starvation deadlock* khi worker chờ công việc đang mắc kẹt trong chính executor của nó.
- Chọn cách phối hợp tác vụ không chặn worker một cách không cần thiết; dùng timeout, cancellation, chia pool và backpressure đúng mục đích.
- Quan sát, tái hiện và kiểm thử lỗi bằng các công cụ Java SE.

Phạm vi: Java concurrency và Executor Framework nói chung; các ví dụ không phụ thuộc framework ứng dụng.

## 1. Mô hình vận hành: task, worker và hàng đợi

`ExecutorService` nhận công việc (`Runnable` hoặc `Callable<T>`) và quản lý việc thực thi thông qua các thread. Với thread pool cố định:

~~~text
Thread gọi submit()
       |
       v
  ExecutorService
       |
       +--> Worker 1: chạy task A
       +--> Worker 2: chạy task B
       +--> ... (tối đa số worker của pool)
       |
       +--> Queue: task C, task D, ... đợi worker rảnh
~~~

**Submit** có nghĩa là chuyển công việc cho executor và nhận một đối tượng theo dõi; nó **không bảo đảm** task được chạy ngay hoặc các task chạy song song. Tiến độ thực tế phụ thuộc số worker, chính sách tạo thread, hàng đợi, tài nguyên bên ngoài và việc worker có bị chặn hay không.

Các API chính:

| API | Ý nghĩa cần nhớ |
| --- | --- |
| `execute(Runnable)` | Gửi công việc không trả `Future`; lỗi không được lấy về bằng `Future.get()`. |
| `submit(Runnable/Callable)` | Trả `Future`; ngoại lệ của task được ghi nhận và xuất hiện qua `get()` dưới dạng `ExecutionException`. |
| `Future.get()` | Chặn **thread đang gọi** cho tới khi có kết quả, lỗi hoặc bị ngắt; bản không có timeout có thể đợi vô hạn. |
| `Future.get(timeout, unit)` | Giới hạn thời gian chờ của **caller**; hết hạn ném `TimeoutException`, **không tự hủy task**. |
| `Future.cancel(true)` | Yêu cầu hủy và, nếu task đang chạy, thử interrupt thread; task phải hợp tác mới dừng kịp. |
| `shutdown()` | Ngừng nhận task mới và cố chạy xong task đã nhận. |
| `shutdownNow()` | Thử interrupt task đang chạy, trả về task chưa bắt đầu; không bảo đảm mọi task dừng ngay. |

### Thế nào là tác vụ độc lập?

Hai task độc lập khi task này **không cần kết quả hoặc tín hiệu hoàn thành của task kia để chạy xong**. Chẳng hạn xử lý ba đầu vào độc lập rồi tổng hợp kết quả ở thread điều phối. Nếu cả ba cùng sửa một biến toàn cục hoặc tranh cùng tài nguyên, bạn vẫn phải xử lý an toàn dữ liệu và giới hạn tài nguyên; “độc lập về đầu vào” không có nghĩa “không cần đồng bộ”.

Mẫu hợp lý là: **gửi tất cả task trước, rồi mới chờ kết quả ở nơi điều phối**. Chờ `Future.get()` tuần tự ở thread gọi không khiến ba task chạy tuần tự, vì chúng đã được submit trước đó. Tuy nhiên thứ tự lấy kết quả có thể làm việc hiển thị chậm hơn nếu future đầu tiên chưa xong.

## 2. Ví dụ chạy được: submit ba task độc lập

Tạo tệp `IndependentTasksDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class IndependentTasksDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(3);

        try {
            List<Callable<Integer>> tasks = List.of(
                    () -> 10 * 10,
                    () -> 20 * 20,
                    () -> 30 * 30
            );

            List<Future<Integer>> futures = new ArrayList<>();
            for (Callable<Integer> task : tasks) {
                futures.add(pool.submit(task)); // Gửi hết trước
            }

            int total = 0;
            for (Future<Integer> future : futures) {
                total += future.get(2, TimeUnit.SECONDS); // Chờ ở main
            }

            System.out.println("Tổng = " + total);
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Chạy trên JDK 17 trở lên:

~~~bash
javac IndependentTasksDemo.java
java IndependentTasksDemo
~~~

Đầu ra xác định:

~~~text
Tổng = 1400
~~~

Cả ba `Callable` không chờ nhau, nên pool có thể phân công chúng cho các worker khác nhau. Vòng lặp `get` ở `main` chỉ tổng hợp kết quả. Trong chương trình thực tế, phải quyết định chính sách khi một future timeout hoặc thất bại: log/thu thập lỗi, hủy việc dư thừa, hoặc trả kết quả một phần. `shutdown` trong `finally` bảo đảm không tiếp tục nhận task mới khi đoạn điều phối kết thúc.

**Sai khác thường gặp:** submit một task rồi gọi `get` ngay trong từng vòng lặp sẽ làm người gọi đợi task đó hoàn tất trước khi gửi task kế tiếp. Cách đó làm mất cơ hội chạy đồng thời, dù chưa chắc gây starvation. Mẫu nên dùng là:

~~~java
// Tốt khi các task thật sự độc lập:
for (Callable<Integer> task : tasks) {
    futures.add(pool.submit(task));
}
for (Future<Integer> future : futures) {
    consume(future.get());
}
~~~

Đoạn trên là mã minh họa: `tasks`, `futures`, `pool` và `consume` cần được khai báo trong chương trình thực tế.

### Nếu cần xử lý theo thứ tự hoàn thành

`ExecutorCompletionService<T>` bọc một executor và đưa các future đã hoàn thành vào hàng đợi kết quả. `take()` chờ **một kết quả bất kỳ hoàn thành tiếp theo**, thay vì chờ future đầu tiên trong danh sách. Đây vẫn là thao tác chặn caller; hãy để thread điều phối chờ, tránh dùng worker trong chính pool để chờ các task cùng pool.

~~~java
// Đoạn minh họa khi pool và tasks đã được tạo:
java.util.concurrent.ExecutorCompletionService<Integer> completed =
        new java.util.concurrent.ExecutorCompletionService<>(pool);

for (Callable<Integer> task : tasks) {
    completed.submit(task);
}
for (int i = 0; i < tasks.size(); i++) {
    Integer result = completed.take().get();
    // Xử lý theo thứ tự hoàn thành, không giả định thứ tự submit.
}
~~~

## 3. Thread starvation xảy ra như thế nào?

**Thread starvation** là tình trạng một task không có cơ hội tiến triển trong khoảng thời gian đáng kể vì tài nguyên thực thi bị chiếm dụng: chẳng hạn mọi worker đều bận, bị block hoặc các task ưu tiên khác liên tục giành lượt. Một executor có hàng đợi vẫn có thể nhận thêm task trong khi không task nào trong hàng đợi được cấp worker.

Trường hợp đặc biệt là **thread-starvation deadlock**: các worker đang chạy task cha, nhưng task cha lại chờ task con đã được submit vào **chính pool không còn worker rảnh**. Quan hệ chờ tự khóa tiến độ:

~~~text
Pool có 1 worker
Worker-1: chạy Parent
  Parent: submit Child vào chính pool
  Parent: gọi child.get() -> WAITING
Queue: [Child]
Child cần Worker-1 -> Worker-1 lại đang chờ Child
=> Không task nào tự giải phóng được worker.
~~~

Điều này không nhất thiết có hai mutex khóa chéo nhau. Đây là vòng phụ thuộc giữa **lịch cấp phát worker** và **Future completion**. Chỉ tăng kích thước pool từ 1 lên 2 không phải cách sửa bền vững: hai parent cùng chạy có thể đồng thời chờ hai child đang nằm trong hàng đợi.

Ngoài dependency nói trên, starvation cũng có thể do task I/O/blocking kéo dài chiếm hết pool; hàng đợi quá dài so với tốc độ xử lý; hoặc các tác vụ cần lock/semaphore chung. “CPU thấp mà queue đầy” thường là dấu hiệu đáng điều tra, nhưng riêng CPU thấp chưa đủ để kết luận.

## 4. Tái hiện an toàn: parent chờ child trong single-thread executor

Tạo `StarvationDemo.java`:

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class StarvationDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();

        Future<Integer> parent = pool.submit(() -> {
            Future<Integer> child = pool.submit(() -> 42);
            return child.get(); // Worker duy nhất chờ task đang xếp hàng
        });

        try {
            System.out.println(parent.get(200, TimeUnit.MILLISECONDS));
        } catch (TimeoutException expected) {
            System.out.println("Timeout: task con không có worker để chạy");
        } finally {
            parent.cancel(true);  // Interrupt worker đang chờ Future.get()
            pool.shutdownNow();   // Không để chương trình demo treo
        }
    }
}
~~~

Chạy:

~~~bash
javac StarvationDemo.java
java StarvationDemo
~~~

Đầu ra kỳ vọng:

~~~text
Timeout: task con không có worker để chạy
~~~

`parent.get(200, ...)` được gọi ở `main` và giới hạn thời gian **main chờ**. Nó không làm `child` chạy được, cũng không sửa dependency bên trong worker. Trong `finally`, `cancel(true)` yêu cầu interrupt parent đang bị chặn tại `child.get()`; `shutdownNow()` cố dọn các tác vụ còn chờ. Mục tiêu là demo kết thúc được, không phải dùng timeout như giải pháp kiến trúc.

Trong tình huống có hai worker, lỗi tương tự vẫn xuất hiện khi cả hai worker đều chạy parent đang chờ child từ cùng pool. Kết luận cốt lõi: **đừng giữ worker của một executor chỉ để đợi một task đang cần chính worker của executor đó**.

## 5. Cách sửa chính: mô hình hóa dependency thay vì chặn worker

Nếu việc sau chỉ là biến đổi kết quả của việc trước, hãy dùng một pipeline: task tiếp theo chỉ được kích hoạt **sau khi** kết quả trước có sẵn. Với Java SE, `CompletableFuture` hỗ trợ `thenApply`, `thenCompose` và `thenCombine` để biểu diễn quan hệ đó.

Tạo `CompositionDemo.java`:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class CompositionDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();

        try {
            CompletableFuture<Integer> result =
                    CompletableFuture.supplyAsync(() -> 21, pool)
                            .thenApply(value -> value * 2);

            System.out.println("Kết quả = " + result.get(2, TimeUnit.SECONDS));
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Chạy:

~~~bash
javac CompositionDemo.java
java CompositionDemo
~~~

Đầu ra xác định:

~~~text
Kết quả = 42
~~~

`thenApply` không tạo ra một task con rồi chặn worker để đợi nó; hàm biến đổi được chạy khi giai đoạn trước hoàn thành. Với biến thể không có hậu tố `Async`, hành động có thể chạy trong thread hoàn thành giai đoạn trước hoặc thread đăng ký continuation nếu giai đoạn đã hoàn tất. Vì vậy **không giả định** mọi continuation có thread riêng.

Chọn phép phối hợp theo ý nghĩa:

| Nhu cầu | Cách biểu diễn |
| --- | --- |
| Biến đổi kết quả A thành B | `future.thenApply(transform)` |
| B là một bước bất đồng bộ trả về `CompletionStage<B>` | `future.thenCompose(startB)`, làm phẳng nested future |
| A và B độc lập, chỉ cần kết hợp khi cả hai xong | `a.thenCombine(b, combine)` |
| Chỉ cần tín hiệu hoàn tất của nhiều future | `CompletableFuture.allOf(...)` |
| Muốn xử lý kết quả của các `Callable` theo lúc hoàn tất | `ExecutorCompletionService` |

Ví dụ minh họa cho một bước phụ thuộc phải thực thi tiếp trong chính executor:

~~~java
// Dùng biến pool đã tồn tại, không gọi get()/join() trong worker.
CompletableFuture<String> chain =
        CompletableFuture.supplyAsync(() -> "java", pool)
                .thenCompose(text ->
                        CompletableFuture.supplyAsync(
                                () -> text.toUpperCase(java.util.Locale.ROOT), pool));
~~~

Ở đây, bước thứ hai **chỉ được submit khi bước thứ nhất đã hoàn thành**; một worker cũng có thể chạy xong chuỗi này vì không có worker nào bị giữ để đợi child. Nếu continuation có blocking I/O, cần cân nhắc executor riêng cho hoạt động blocking; tự động dùng `thenApplyAsync` không bảo đảm hết starvation nếu vẫn trỏ vào cùng pool đang nghẽn.

### Trường hợp không cần tạo child task

Nếu phép tính con ngắn và là phần tự nhiên của công việc cha, thực hiện trực tiếp trong task cha có thể là cách đơn giản nhất. Gửi thêm một task rồi `get` kết quả của nó không đem lại lợi ích nếu parent không có việc độc lập nào để làm trong lúc chờ.

## 6. Phân tách tải CPU và tải blocking

Một task CPU-bound thường chiếm CPU đến khi tính xong. Một task blocking (đọc file/network, đợi khóa, đợi dịch vụ khác) có thể giữ platform thread trong lúc CPU hầu như rảnh. Khi đặt cả hai loại trong pool nhỏ, blocking task có thể chiếm hết worker và trì hoãn công việc tính toán ngắn.

Các nguyên tắc thiết kế:

1. **Pool CPU-bound:** đặt mức đồng thời phù hợp số lõi CPU và phép đo thực tế; không mặc định “càng nhiều thread càng nhanh”.
2. **Pool blocking:** cân nhắc executor riêng và giới hạn tài nguyên phía sau (connection, rate limit, file descriptor); việc tăng thread quá mức có thể chuyển tắc nghẽn sang tài nguyên khác.
3. **Không dùng pool chung cho luồng orchestration phải chờ các task cùng pool:** khi buộc phải chờ, hãy chờ ở thread điều phối nằm ngoài pool phụ thuộc, hoặc thiết kế pipeline bất đồng bộ.
4. **Đo theo workload thực tế:** độ trễ, throughput, số task đang chạy, độ dài queue và thời gian chờ; pool size chỉ là một phần của bài toán.

`Executors.newFixedThreadPool(n)` thường dùng **hàng đợi không giới hạn dung lượng theo cấu hình** (`LinkedBlockingQueue`), nên task có thể tích tụ nhiều khi tốc độ submit vượt tốc độ xử lý; điều này dễ dẫn đến tăng bộ nhớ và độ trễ. `newCachedThreadPool()` có thể tăng số thread mạnh khi nhiều task bị block, cũng không thay thế kiểm soát tải.

### Hàng đợi hữu hạn và xử lý overload

Ví dụ cấu hình `ThreadPoolExecutor` (đoạn cấu hình minh họa, không phải chương trình độc lập):

~~~java
ThreadPoolExecutor pool = new ThreadPoolExecutor(
        4, 4,
        0L, TimeUnit.MILLISECONDS,
        new ArrayBlockingQueue<>(100),
        new ThreadPoolExecutor.AbortPolicy()
);
~~~

Hàng đợi chỉ chứa tối đa 100 task **đang chờ**, tách biệt tối đa 4 task đang chạy. Khi pool đang chạy đủ worker và queue đầy, `AbortPolicy` ném `RejectedExecutionException`; caller phải có chính sách cụ thể (giảm tốc độ gửi, báo quá tải, retry có giới hạn hoặc từ chối yêu cầu). Cần `import java.util.concurrent.*;` cho ví dụ này.

`CallerRunsPolicy` có thể tạo backpressure bằng cách cho caller chạy task khi pool quá tải, nhưng nó làm caller bị chặn và có hành vi khác khi executor đã shutdown. Không chọn rejection policy chỉ để che mất dấu hiệu overload; phải hiểu ngữ cảnh caller và điều kiện dừng.

Với dịch vụ ngoài có hạn mức, `Semaphore` hoặc cơ chế giới hạn request có thể cần thiết dù executor còn nhiều worker. **Giới hạn queue và giới hạn số request đồng thời giải quyết hai vấn đề khác nhau.**

## 7. Timeout, cancellation, interrupt và shutdown

Timeout là **ranh giới thời gian chờ**, không phải bằng chứng task đã bị hủy. Đoạn sau chỉ là mẫu điều khiển, giả định `future` đã được khởi tạo:

~~~java
try {
    Result value = future.get(1, TimeUnit.SECONDS);
    use(value);
} catch (TimeoutException timeout) {
    future.cancel(true);
    // Ghi nhận timeout và quyết định phản hồi cho caller.
}
~~~

`Result` và `use` là ký hiệu minh họa. Trong mã thật, cần xử lý `InterruptedException` (thường khôi phục cờ interrupt ở lớp điều phối phù hợp), `ExecutionException` và `CancellationException`; không được nuốt lỗi rồi coi như thành công.

Nếu task đang chặn ở API có thể bị interrupt, `cancel(true)` có thể khiến nó dừng; nếu task phớt lờ interrupt, đang dùng I/O không đáp ứng interrupt hoặc có code CPU chạy liên tục không kiểm tra cờ interrupt, việc hủy không bảo đảm hoàn tất ngay. Task nên có điểm kiểm tra trạng thái, timeout I/O riêng và `finally` để giải phóng tài nguyên.

Khi đóng executor, thông thường: ngừng nhận việc mới qua `shutdown()`, đợi có giới hạn qua `awaitTermination`, rồi mới `shutdownNow()` nếu cần. Không để pool sống vô hạn sau demo/tests; cũng không tắt pool dùng chung tùy tiện từ từng task.

**Một lưu ý quan trọng:** đặt `get(timeout)` ngay trong parent đang chạy ở chính pool nhỏ vẫn giữ worker cho đến timeout. Nó chỉ giới hạn tác hại theo thời gian, không loại bỏ cấu trúc chờ gây starvation.

## 8. Nhận diện và chẩn đoán trong ứng dụng Java

Dấu hiệu nghi vấn có thể gồm:

- Queue tiếp tục tăng hoặc chờ rất lâu; throughput giảm dù vẫn nhận task.
- Các worker của pool đều đang bận nhưng ít task hoàn thành; CPU có thể thấp nếu phần lớn thread đang chờ.
- Thread dump cho thấy nhiều worker ở trạng thái `WAITING`/`TIMED_WAITING` tại `FutureTask.get`, `CompletableFuture.join`, lock hoặc I/O; đồng thời queue chứa công việc mà các worker ấy đang đợi.
- Timeout tăng khi workload tăng; thêm worker chỉ làm hiện tượng xuất hiện muộn hơn.

Quy trình xác minh thay vì đoán:

1. Xác định **executor nào** nhận task cha/con và số worker thực tế; vẽ đồ thị “task A chờ task B” với nơi B được xếp hàng.
2. Lấy thread dump lúc nghẽn (ví dụ `jcmd <pid> Thread.print` với JDK phù hợp) và đối chiếu stack của worker đang chờ.
3. Nếu dùng `ThreadPoolExecutor`, quan sát `getPoolSize()`, `getActiveCount()`, `getQueue().size()` và `getCompletedTaskCount()` theo thời gian; các chỉ số chỉ là ảnh chụp gần đúng, không dùng riêng lẻ làm chứng cứ.
4. Đối chiếu thời gian xử lý CPU/I/O, thời gian đợi lock và độ dài queue; thử với tải có kiểm soát để xem bottleneck nằm ở đâu.
5. Sửa dependency/chia tải/giới hạn queue, rồi đo lại throughput, timeout và tài nguyên. Không dùng tăng pool size làm bằng chứng lỗi đã được xử lý triệt để.

**Phân biệt thuật ngữ:** deadlock khóa truyền thống thường là vòng chờ giữa các lock; thread-starvation deadlock ở đây là vòng phụ thuộc vào worker và task queue. “Starvation” rộng hơn, có thể chỉ là trì hoãn kéo dài do lịch chạy hoặc tranh tài nguyên, chưa chắc có vòng chờ tuyệt đối.

## 9. Tự kiểm thử những tình huống dễ bỏ sót

Các test có giá trị nên ép tiến độ bằng primitive đồng bộ có thời hạn (chẳng hạn `CountDownLatch`), tránh dựa vào `Thread.sleep` để “đoán” thứ tự. Những trường hợp nên tái hiện:

| Kịch bản | Điều cần kiểm tra |
| --- | --- |
| Ba task độc lập; pool đủ worker | Tất cả được submit trước khi caller chờ; kết quả không phụ thuộc thứ tự chạy. |
| Pool 1 worker, parent submit child rồi `get` | Phát hiện timeout, tránh để test treo và cleanup pool sau test. |
| Hai worker, hai parent cùng chờ hai child trong cùng pool | Hiểu rằng tăng từ 1 lên 2 worker không loại bỏ vấn đề kiến trúc. |
| Một task lỗi hoặc chạy lâu | Caller nhận đúng `ExecutionException`/`TimeoutException`, có chính sách hủy rõ ràng. |
| Queue đầy | Rejection được xử lý dự đoán được; không mất task âm thầm. |
| Task bị cancel/interrupt | Tài nguyên được đóng; task có thể phản hồi interrupt hoặc timeout I/O theo thiết kế. |

Khi viết test, **không dựa vào thứ tự thread chạy** hoặc thời lượng máy nhanh/chậm để xác nhận correctness. Kiểm tra kết quả, trạng thái timeout và quan hệ chờ có thể quan sát được. Một test có timeout ở tầng test runner vẫn cần cleanup executor trong `finally` để không làm kẹt cả bộ test.

## 10. Nguyên tắc quyết định nhanh

- **Task thật sự độc lập:** submit tất cả, rồi tập hợp kết quả ở caller; dùng `CompletionService` nếu cần xử lý theo thứ tự hoàn thành.
- **Task B phụ thuộc A:** dùng phép biến đổi/chaining như `thenApply` hoặc `thenCompose`; đừng chiếm worker của A để đợi B được xếp hàng trên cùng pool.
- **Task bị block vì I/O:** tách loại tải và đo giới hạn tài nguyên; cân nhắc executor phù hợp và timeout I/O thực.
- **Hàng đợi tăng mãi:** giới hạn queue, đưa ra backpressure/rejection policy và kiểm soát tốc độ producer.
- **Pool nhỏ thường “đứng im”:** kiểm tra thread dump, chuỗi `Future.get()/join()` và xem liệu công việc đang chờ có cần chính các worker bị giữ hay không.
- **Java 21+ có virtual threads:** `Executors.newVirtualThreadPerTaskExecutor()` hữu ích cho nhiều tác vụ blocking kiểu thread-per-task, nhưng không tự giới hạn tải lên dịch vụ ngoài, không chữa vòng phụ thuộc logic và không thay thế timeout/cancellation. Ví dụ chính của bài dùng API chạy được trên Java 17+.

Điểm cốt lõi: **gửi công việc độc lập để executor có cơ hội chạy chúng; biểu diễn công việc phụ thuộc thành chuỗi phối hợp; đừng để toàn bộ worker bị khóa trong lúc chờ chính hàng đợi mà chúng phải phục vụ.**