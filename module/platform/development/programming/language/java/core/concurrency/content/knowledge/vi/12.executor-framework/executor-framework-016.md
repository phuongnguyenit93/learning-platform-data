# AbortPolicy, CallerRunsPolicy, DiscardPolicy và DiscardOldestPolicy: hệ quả khi quá tải

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích **ThreadPoolExecutor.RejectedExecutionHandler** và thời điểm một tác vụ bị executor từ chối, đặc biệt khi **mọi worker đang bận, hàng đợi đầy hoặc executor đã shutdown**.
- Phân biệt chính xác bốn handler mặc định của JDK: **AbortPolicy**, **CallerRunsPolicy**, **DiscardPolicy**, **DiscardOldestPolicy**.
- Dự đoán **thread thực thi**, **tác vụ bị mất**, **exception tại nơi submit**, **thay đổi thứ tự công việc**, **backpressure** và **trạng thái Future** dưới từng policy.
- Thiết kế **ThreadPoolExecutor có queue giới hạn**, kiểm thử bốn policy bằng những lịch chạy được điều khiển để không phụ thuộc Thread.sleep().
- Nhận biết vì sao **submit() trả Future không bảo đảm Future sẽ hoàn tất** nếu handler âm thầm bỏ một RunnableFuture khỏi queue hoặc bỏ task mới.
- Chọn chính sách từ chối theo **mức độ được phép mất dữ liệu**, **idempotency**, **thread confinement**, **latency**, **retries**, **shutdown** và hợp đồng với producer.
- Ghi nhận metrics, kiểm soát lỗi, xử lý graceful shutdown và giải thích những giới hạn của mỗi cơ chế trong phạm vi Java concurrency.

Phạm vi là **Executor Framework của Java 17+**, chỉ nói các API thuộc JDK. Các cơ chế executor riêng của Spring được trình bày trong chương khác.

## 2. Rejection không chỉ là lỗi kỹ thuật: đó là quyết định về dữ liệu

Trong một hệ thống có tài nguyên hữu hạn, đôi khi **không thể nhận thêm công việc** đúng thời hạn. Một executor có thể chỉ có 2 worker và hàng đợi cho 10 task. Nếu cả worker đều bận và 10 task đã ở queue, task thứ 13 sẽ đi tới **rejection handler** nếu không thể bố trí thêm worker.

~~~text
Producer gửi task
        |
        v
ThreadPoolExecutor.execute(command)
        |
        +-- Có thể tạo worker theo corePoolSize? ----> Thực thi
        |
        +-- Queue nhận được command? ----------------> Đợi trong queue
        |
        +-- Có thể tăng worker tới maximumPoolSize? -> Thực thi
        |
        +-- Không thể nhận / đã shutdown ------------> reject(command)
                                                         |
                                               RejectedExecutionHandler
~~~

Đây là sơ đồ khái niệm: ThreadPoolExecutor còn có kiểm tra trạng thái và race khi shutdown, số worker thay đổi và queue thay đổi; các quyết định thực tế theo hợp đồng JDK. Điểm chính: **rejection handler được gọi khi execute không thể nhận task theo trạng thái và cấu hình hiện tại**.

Với application, mỗi hành vi mang hậu quả khác nhau:

- **Ném lỗi** cho producer để producer biết chưa được nhận.
- **Chạy task ngay trên thread producer**, chuyển áp lực lên phía gửi.
- **Lặng lẽ bỏ task vừa gửi**.
- **Bỏ task đang đợi lâu nhất trong queue**, thử đưa task mới vào.

Một nhiệm vụ có thể là log debug được phép mất hoặc lệnh ghi thanh toán không được mất. **Không thể chọn cùng một policy một cách máy móc cho mọi loại task.**

## 3. Điều kiện để ThreadPoolExecutor thực sự bão hòa

Một constructor thường dùng:

~~~java
// Đoạn minh họa trong một phương thức Java; không phải file độc lập.
ThreadPoolExecutor pool = new ThreadPoolExecutor(
    2, 2,
    0L, TimeUnit.MILLISECONDS,
    new ArrayBlockingQueue<>(10),
    new ThreadPoolExecutor.AbortPolicy()
);
~~~

Cần import các lớp tương ứng từ java.util.concurrent.

Ý nghĩa:

| Thành phần | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| corePoolSize | 2 | Mốc worker cốt lõi, thường được tạo theo nhu cầu |
| maximumPoolSize | 2 | Số worker tối đa |
| keepAliveTime | 0 | Thời gian giữ worker dư so với core; với core=max không có worker dư |
| workQueue | ArrayBlockingQueue<>(10) | Tối đa 10 task đang chờ trong queue |
| rejectedExecutionHandler | AbortPolicy | Xử lý khi executor không thể nhận thêm task |

**Worker đang chạy không nằm trong queue.** Với pool 2 worker, queue capacity 10, số task đang hoạt động/chờ tối đa trong cấu hình này là **2 đang chạy + 10 đang đợi**, trước khi tính những task đã hoàn thành; không phải “10 task tổng cộng”.

Nếu dùng **Executors.newFixedThreadPool(n)** hoặc **newSingleThreadExecutor()** mặc định, queue kiểu LinkedBlockingQueue có giới hạn rất lớn, nên những executor này **không có backpressure hữu ích chỉ nhờ giới hạn worker**. Trong thực tế queue có thể lớn đến mức gây cạn heap. Nếu dùng **newCachedThreadPool()**, pool thường có SynchronousQueue và maximumPoolSize rất lớn: khi không có worker rảnh, executor có thể tạo nhiều platform thread, làm cạn tài nguyên trước khi có tín hiệu overload hữu ích.

Muốn quan sát rejection một cách chủ động, ví dụ trong bài dùng **một worker + queue một chỗ + handler chỉ định**.

### Thuật toán nhận task giản lược

1. Nếu số worker ít hơn **corePoolSize**, executor cố tạo worker mới cho command.
2. Nếu đã đủ core, nó thường thử **enqueue** command khi đang running.
3. Nếu queue không nhận được, executor cố tạo worker khác nếu vẫn dưới **maximumPoolSize**.
4. Nếu không thể enqueue và không thể thêm worker, hoặc executor không nhận việc do shutdown, command được **reject**.

Với queue không giới hạn thực dụng, bước 2 gần như luôn nhận thêm task cho đến lúc hết tài nguyên, nên tăng maximumPoolSize cao hơn core **không nhất thiết khiến pool mở thêm worker**. Đây là lý do phải xem **worker, queue và handler cùng một lúc**.

## 4. Bảng so sánh bốn chính sách mặc định

| Handler | Khi pool đang chạy nhưng bão hòa | Producer có được báo không? | Hệ quả quan trọng |
| --- | --- | --- | --- |
| **AbortPolicy** | Ném RejectedExecutionException | **Có**, qua exception đồng bộ tại execute/submit | Không nhận task; caller phải xử lý thất bại |
| **CallerRunsPolicy** | Thread gọi execute chạy task trực tiếp nếu executor chưa shutdown | Không ném vì riêng trạng thái bão hòa này | Producer có thể bị block; task chạy sai thread dự kiến |
| **DiscardPolicy** | Bỏ task mới mà không báo | **Không** | Mất task im lặng; Future có thể không bao giờ xong |
| **DiscardOldestPolicy** | Bỏ head của work queue rồi thử execute task mới nếu chưa shutdown | Thường không, nhưng lần retry có thể lại bị từ chối tùy cấu hình | Task đã đợi bị mất; phá thứ tự và Future của task bị bỏ có thể treo |

**Khi executor đã shutdown**, hành vi cũng quan trọng:

- **AbortPolicy** vẫn ném RejectedExecutionException.
- **CallerRunsPolicy** **không** chạy task trong caller khi executor đã shutdown; nó bỏ task.
- **DiscardPolicy** bỏ task mà không báo.
- **DiscardOldestPolicy** không thử xóa/đưa lại task khi executor đã shutdown, và bỏ task.

Đây là hành vi của các **implementation handler chuẩn của JDK**. Không suy luận rằng caller thấy execute() trả về bình thường thì task đã được enqueue, sẽ được chạy, hoặc đã hoàn thành.

## 5. AbortPolicy: fail-fast để producer chủ động quyết định

**ThreadPoolExecutor.AbortPolicy** là handler mặc định khi tạo ThreadPoolExecutor mà không cung cấp handler khác. Khi được gọi, nó ném **RejectedExecutionException**.

~~~java
// Đoạn minh họa trong method Java:
try {
    pool.execute(task);
} catch (RejectedExecutionException ex) {
    // Task chưa được nhận; xử lý theo hợp đồng nghiệp vụ.
}
~~~

**Rejection xảy ra tại lời gọi gửi task**, không phải exception từ code bên trong task. Đây là hai lớp lỗi khác nhau:

- Task chưa được nhận: **RejectedExecutionException** ngay khi gọi execute/submit.
- Task đã được nhận nhưng bản thân chạy thất bại: exception trong worker; với submit() thường được lưu trong Future và xuất hiện qua **Future.get() / ExecutionException**.

### Khi nào AbortPolicy phù hợp?

- Công việc **không được phép tự biến mất**, ví dụ cập nhật dữ liệu cần được ghi nhận.
- Producer có khả năng **thông báo bận**, giảm tốc, chuyển sang đường xử lý khác hoặc ghi một durable queue.
- Cần metrics/rejection rõ ràng để biết khi nào hệ thống quá tải.
- Có hợp đồng rõ về retry, timeout và idempotency của tác vụ.

**AbortPolicy không tự retry.** Nó chỉ đưa quyết định lại cho caller. Nếu caller lập tức retry vô hạn trong vòng lặp sát nhau, hệ thống có thể càng quá tải. Retry cần backoff, giới hạn số lần, tổng deadline và đánh giá lại nhu cầu.

**Không nên catch exception rồi giả vờ thành công**:

~~~java
// Anti-pattern: caller lờ đi trạng thái không nhận công việc.
try {
    pool.execute(saveOrder);
} catch (RejectedExecutionException ignored) {
    // Người gọi vẫn nhận phản hồi "đã lưu" là sai.
}
~~~

Đây là mã minh họa; pool và saveOrder cần được khai báo. Với task quan trọng, thất bại nhận việc phải hiện diện trong trạng thái/response hoặc được chuyển sang cơ chế lưu trữ đáng tin cậy theo thiết kế.

## 6. CallerRunsPolicy: tạo backpressure bằng chính thread gửi

**CallerRunsPolicy** có logic cốt lõi: nếu executor **chưa shutdown**, thread gọi execute(command) chạy **command.run()** trực tiếp.

Nghĩa là trong overload, producer không chỉ enqueue nữa mà **phải làm công việc vừa gửi ngay lúc đó**, làm chậm khả năng tiếp tục submit thêm. Đây là một dạng **backpressure thô**, có thể hữu ích khi producer và worker đều được phép thực thi cùng task.

~~~text
Bình thường:
Producer -> execute(task) -> Queue/worker -> thực thi

Pool bão hòa, CallerRunsPolicy:
Producer -> execute(task) -> task.run() ngay trên Producer thread
                            |
                            +-- Producer bị giữ tới khi task.run() kết thúc
~~~

Điều cần lưu ý:

1. **Caller thread có thể là main thread, request thread, event-loop thread hoặc thread đang giữ lock**; không phải worker do executor quản lý.
2. Nếu task block lâu, caller bị block lâu; request latency và responsiveness có thể bị ảnh hưởng.
3. Nếu task dựa vào ThreadLocal, thread name, security context, thread affinity hoặc ownership của worker, hành vi có thể thay đổi.
4. **Không bảo đảm thứ tự chạy giữa task được caller thực thi và task đang chờ queue**. Task mới có thể hoàn thành trước task cũ đang queue.
5. Nếu caller là task đang chạy trong **cùng executor**, CallerRunsPolicy có thể gây **thực thi lồng nhau** trên worker thread, tăng call depth và làm thay đổi giả định ordering.
6. **Nếu executor đã shutdown, handler không chạy task ở caller**, nên có thể âm thầm bỏ task.

### Khi nào nên dùng?

- Task **không phụ thuộc thread cụ thể** và an toàn khi chạy trên mọi thread producer.
- Producer chấp nhận bị chặn để hệ thống không nhận vô hạn việc mới.
- Có contract về latency, timeout và thread affinity rõ ràng.
- Đã đánh giá việc caller đang giữ lock, tham gia transaction hoặc xử lý network event loop.

### Trường hợp nguy hiểm: phá thread confinement

Giả sử state mutable chỉ được phép một worker trong single-thread executor sửa. Nếu thay executor bằng một ThreadPoolExecutor một worker dùng **CallerRunsPolicy**, khi queue đầy, một producer có thể chạy task cập nhật state **trực tiếp trên thread producer**. Như vậy **một tác vụ trên worker và một tác vụ trên producer có thể cùng truy cập state**, gây race hoặc phá thứ tự.

Không chỉ là vấn đề hiệu năng: **CallerRunsPolicy có thể thay đổi mô hình đúng đắn**. Không được chọn nó chỉ vì tên gọi “backpressure” mà quên rằng task không còn chắc chắn chạy trên owner worker.

## 7. DiscardPolicy: bỏ task mới một cách im lặng

**DiscardPolicy** thực hiện **không hành động** khi reject. Lời gọi execute có thể trở về bình thường nhưng command **không được chạy**.

Đối với task kiểu log debug được phép mất, cách làm này đôi khi là lựa chọn có chủ đích để giữ hệ thống chính hoạt động. Nhưng nó nguy hiểm cho các tác vụ:

- Ghi dữ liệu tài chính hoặc nghiệp vụ bắt buộc.
- Gửi thông báo cần bảo đảm giao nhận.
- Giải phóng/đóng tài nguyên thuộc bước sau.
- Báo completion cho thread khác.
- Ghi log kiểm toán bắt buộc.
- Các task mà caller trả phản hồi “đã chấp nhận” chỉ vì execute() không ném lỗi.

**Silent loss** còn ảnh hưởng debugging: producer có thể không có dấu hiệu trực tiếp cho biết yêu cầu chưa chạy, và không có metric nếu không thêm handler/telemetry ngoài.

### Điểm tinh vi khi dùng submit()

**ExecutorService.submit()** thường đóng gói command thành một **RunnableFuture** rồi chuyển tới execute(). Nếu DiscardPolicy bỏ RunnableFuture, Future trả về caller có thể **không bao giờ chuyển sang trạng thái done**, vì task chưa được chạy và không được cancel.

Hậu quả:

- **future.get()** có thể chờ vô hạn.
- **future.get(timeout)** có thể hết thời gian chờ, nhưng điều này không chứng minh task đã từng được nhận.
- **future.isDone()** có thể vẫn là false ngay cả sau khi executor đã terminated.
- **shutdown()** không tự biến Future bị bỏ thành canceled.

Do đó, nếu cho phép silent discard, phải thiết kế cách thông báo/kiểm tra kết quả độc lập hoặc **không cung cấp Future với kỳ vọng chắc chắn hoàn tất**.

## 8. DiscardOldestPolicy: bỏ task cũ đang chờ, thử nhận task mới

Khi executor còn running và không nhận được command mới, **DiscardOldestPolicy** thực hiện gần tương đương:

~~~java
// Giả mã minh họa hành vi chính của handler mặc định:
if (!executor.isShutdown()) {
    executor.getQueue().poll(); // Bỏ head của hàng đợi.
    executor.execute(newTask);  // Thử nhận task mới lần nữa.
}
~~~

Đây là đoạn mô tả cần biến executor/newTask đã được khai báo; không phải chương trình độc lập.

**“Oldest” ở đây có nghĩa phần tử đầu work queue theo cơ chế của queue**, không phải task đang chạy lâu nhất, cũng không phải “task có timestamp nhỏ nhất toàn hệ thống”.

Với **FIFO ArrayBlockingQueue/LinkedBlockingQueue**, head thường là task đang chờ lâu nhất. Tuy nhiên:

- **Task đang chạy không bị lấy ra và dừng**.
- **Task trong queue bị bỏ không tự được cancel**.
- Nếu queue không có phần tử để poll, retry có thể vẫn reject; trong một số cấu hình không có capacity hữu ích (như SynchronousQueue), một vòng retry qua handler có thể lặp không tiến triển. Không dùng DiscardOldestPolicy một cách mù quáng với mọi loại queue.
- Với queue có thứ tự ưu tiên, head có nghĩa theo **ordering của queue**, không nhất thiết oldest theo thời gian submit; mất head có thể phá chính sách ưu tiên.
- Khi executor đã shutdown, handler không thực hiện chuỗi poll/re-execute theo logic chuẩn, và task mới bị bỏ.

### Hậu quả nghiệp vụ

Giả sử các command đến theo thứ tự:

~~~text
A đang thực thi trên worker
B chờ trong queue (capacity=1)
C được submit khi worker vẫn bận

DiscardOldestPolicy:
  B bị lấy khỏi queue và bỏ
  C được thử đưa vào queue
  Khi A hoàn thành -> C được chạy
  Kết quả: A, C chạy; B bị mất
~~~

Với tác vụ **cập nhật trạng thái có phụ thuộc thứ tự**, kết quả có thể sai: C có thể giả định B đã thực hiện. Nếu B là lệnh debit và C là lệnh xác nhận, việc bỏ B là lỗi dữ liệu nghiêm trọng. Nếu chỉ cập nhật **ảnh trạng thái mới nhất** và các bản cũ có thể bị bỏ, logic coalescing có chủ đích có thể phù hợp hơn, nhưng vẫn cần xử lý Future/metrics và tính đúng đắn của thứ tự.

## 9. Ví dụ 1: so sánh trực tiếp cả bốn policy bằng lịch xác định

Ví dụ tạo **1 worker, queue capacity=1**. Task A giữ worker cho đến khi main cho phép, task B nằm trong queue, task C gây rejection. Kết quả được sắp chữ sau completion để không phụ thuộc thứ tự log giữa thread.

Tệp **RejectionPolicyMatrixDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.RejectedExecutionHandler;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class RejectionPolicyMatrixDemo {
    static String runCase(RejectedExecutionHandler policy)
            throws InterruptedException {

        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 1, 0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(1), policy
        );

        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        List<String> ran = Collections.synchronizedList(new ArrayList<>());
        boolean rejected = false;

        try {
            pool.execute(() -> {
                started.countDown();
                try {
                    release.await();
                    ran.add("A");
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                }
            });

            started.await();
            pool.execute(() -> ran.add("B"));

            try {
                pool.execute(() -> ran.add("C"));
            } catch (RejectedExecutionException ex) {
                rejected = true;
            }

            release.countDown();
            pool.shutdown();

            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("pool did not terminate");
            }

            List<String> finished = new ArrayList<>(ran);
            Collections.sort(finished);
            return "rejected=" + rejected
                    + ", ran=" + String.join("", finished);
        } finally {
            release.countDown();
            if (!pool.isTerminated()) {
                pool.shutdownNow();
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        System.out.println(
                "AbortPolicy: "
                + runCase(new ThreadPoolExecutor.AbortPolicy())
        );
        System.out.println(
                "CallerRunsPolicy: "
                + runCase(new ThreadPoolExecutor.CallerRunsPolicy())
        );
        System.out.println(
                "DiscardPolicy: "
                + runCase(new ThreadPoolExecutor.DiscardPolicy())
        );
        System.out.println(
                "DiscardOldestPolicy: "
                + runCase(new ThreadPoolExecutor.DiscardOldestPolicy())
        );
    }
}
~~~

Biên dịch và chạy bằng Java 17+:

~~~bash
javac -encoding UTF-8 RejectionPolicyMatrixDemo.java
java RejectionPolicyMatrixDemo
~~~

Stdout khi chạy bình thường, không bị interrupt từ bên ngoài:

~~~text
AbortPolicy: rejected=true, ran=AB
CallerRunsPolicy: rejected=false, ran=ABC
DiscardPolicy: rejected=false, ran=AB
DiscardOldestPolicy: rejected=false, ran=AC
~~~

**Lập luận từng trường hợp:**

- **AbortPolicy**: A giữ worker, B giữ chỗ trong queue, C không được nhận và làm execute() ném exception. A và B chạy.
- **CallerRunsPolicy**: khi C bị reject, thread main gọi trực tiếp C.run() trước khi release A. Sau đó A/B tiếp tục. C vẫn được thực thi, nhưng không phải trên worker của pool.
- **DiscardPolicy**: C bị bỏ, execute() không báo lỗi. A và B chạy.
- **DiscardOldestPolicy**: B bị bỏ khỏi queue và C được enqueue; sau khi A rời worker, C chạy.
- **Collections.sort** chỉ dùng để in tên các task đã chạy theo thứ tự ổn định; nó **không khẳng định thứ tự thực thi**.
- Sau khi awaitTermination trả true, các task đã chạy và việc thay đổi list đã kết thúc, nên đọc kết quả là phù hợp.

Trong ứng dụng thật, **đừng dùng cách bỏ B hoặc C như một chính sách mặc định** nếu business yêu cầu không mất task. Ví dụ ở đây cố ý mô phỏng bão hòa để hiểu ngữ nghĩa của từng handler.

## 10. Ví dụ 2: CallerRuns thực sự chạy ở thread gửi

Ví dụ trước cho thấy cả ba task chạy khi dùng CallerRunsPolicy; dưới đây kiểm chứng **thread identity** bằng so sánh Thread object, không dựa vào tên thread do JVM gán.

Tệp **CallerRunsThreadDemo.java**:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Future;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class CallerRunsThreadDemo {
    public static void main(String[] args) throws Exception {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 1, 0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(1),
                new ThreadPoolExecutor.CallerRunsPolicy()
        );

        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        Thread caller = Thread.currentThread();

        try {
            Future<Integer> first = pool.submit(() -> {
                started.countDown();
                release.await();
                return 1;
            });

            started.await();
            Future<Integer> second = pool.submit(() -> 2);

            Future<Boolean> third = pool.submit(
                    () -> Thread.currentThread() == caller
            );

            System.out.println(
                    "third on caller = " + third.get()
            );

            release.countDown();
            int completed = first.get() + second.get();
            System.out.println("worker sum = " + completed);
        } finally {
            release.countDown();
            pool.shutdownNow();
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 CallerRunsThreadDemo.java
java CallerRunsThreadDemo
~~~

Stdout:

~~~text
third on caller = true
worker sum = 3
~~~

**Vì sao xác định được?** Worker duy nhất đang chờ release, queue chứa task second, vì vậy third không thể vào worker/queue. CallerRunsPolicy gọi RunnableFuture.run() ngay trên main; Callable bên trong trả **true** vì Thread.currentThread() == caller. Future của third hoàn tất ngay trong lời submit. Main sau đó mở latch để first/second chạy xong.

**Hệ quả về thiết kế:** Nếu task dùng ThreadLocal hoặc chỉ được phép sửa state trên worker, third có thể vận hành với context khác dự kiến. Nếu thread gửi là request thread, nó bị giữ trong suốt thời gian chạy third, làm tăng request latency. Nếu thread gửi đang giữ khóa mà third cần, có thể xảy ra reentrancy, chờ khóa hoặc deadlock tùy giao thức.

## 11. Ví dụ 3: Future của task bị DiscardOldest có thể không bao giờ done

Với submit(), command trong queue thường là một **FutureTask**. DiscardOldestPolicy lấy nó ra bằng queue.poll() nhưng **không gọi cancel()**. Ta quan sát trạng thái sau khi pool đã terminated; tuyệt đối không gọi get() vô thời hạn trên Future bị bỏ.

Tệp **DiscardedFutureDemo.java**:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Future;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class DiscardedFutureDemo {
    public static void main(String[] args) throws Exception {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 1, 0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(1),
                new ThreadPoolExecutor.DiscardOldestPolicy()
        );

        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            Future<Integer> first = pool.submit(() -> {
                started.countDown();
                release.await();
                return 1;
            });

            started.await();
            Future<Integer> dropped = pool.submit(() -> 2);
            Future<Integer> newest = pool.submit(() -> 3);

            release.countDown();
            pool.shutdown();

            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("pool did not terminate");
            }

            System.out.println("first = " + first.get());
            System.out.println("newest = " + newest.get());
            System.out.println("dropped done = " + dropped.isDone());
            System.out.println("dropped cancelled = " + dropped.isCancelled());
        } finally {
            release.countDown();
            if (!pool.isTerminated()) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 DiscardedFutureDemo.java
java DiscardedFutureDemo
~~~

Stdout:

~~~text
first = 1
newest = 3
dropped done = false
dropped cancelled = false
~~~

**Vì sao đáng chú ý?**

1. first đang chạy và chờ latch; dropped nằm trong queue capacity=1.
2. newest đến khi pool bão hòa; handler loại dropped khỏi queue, rồi enqueue newest.
3. first và newest hoàn thành, executor chấm dứt, nhưng Future tên dropped **chưa được run hoặc cancel**.
4. dropped.isDone() vẫn false, dropped.isCancelled() cũng false. Nếu gọi dropped.get() không timeout, caller có thể chờ không có điểm kết thúc.
5. **Sự chấm dứt của pool không khiến mọi Future từng trả ra tự động done** khi policy đã bỏ task một cách im lặng.

Hành vi tương tự có thể xảy ra với **DiscardPolicy** khi nó loại ngay RunnableFuture mới gửi. Khi yêu cầu kết quả/ack cho mọi request, tránh dùng silent-discard handler mặc định hoặc cần có một giao thức hoàn tất/cancel tường minh.

## 12. Ví dụ 4: custom rejection handler báo lỗi và ghi nhận metric

Trong vận hành, cần biết hệ thống từ chối bao nhiêu request và vì sao. Một handler tùy chỉnh có thể tăng counter rồi ném RejectedExecutionException, để producer có tín hiệu rõ ràng.

Tệp **MeasuredRejectionDemo.java**:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.RejectedExecutionHandler;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class MeasuredRejectionDemo {
    public static void main(String[] args) throws Exception {
        AtomicInteger rejections = new AtomicInteger();

        RejectedExecutionHandler handler = (task, executor) -> {
            rejections.incrementAndGet();
            throw new RejectedExecutionException("capacity exceeded");
        };

        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 1, 0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(1), handler
        );

        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        AtomicInteger completed = new AtomicInteger();

        try {
            pool.execute(() -> {
                started.countDown();
                try {
                    release.await();
                    completed.incrementAndGet();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                }
            });

            started.await();
            pool.execute(completed::incrementAndGet);

            boolean rejected = false;
            try {
                pool.execute(completed::incrementAndGet);
            } catch (RejectedExecutionException ex) {
                rejected = true;
            }

            release.countDown();
            pool.shutdown();

            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("pool did not terminate");
            }

            System.out.println("caller saw rejection = " + rejected);
            System.out.println("rejections = " + rejections.get());
            System.out.println("completed = " + completed.get());
        } finally {
            release.countDown();
            if (!pool.isTerminated()) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 MeasuredRejectionDemo.java
java MeasuredRejectionDemo
~~~

Stdout:

~~~text
caller saw rejection = true
rejections = 1
completed = 2
~~~

**Ý nghĩa:** task đầu đã giữ worker, task thứ hai nằm trong queue, task thứ ba làm handler được gọi. Handler vừa tăng metric vừa ném lỗi. Caller biết task không được nhận, có thể báo quá tải hoặc chuyển công việc sang kênh khác. Sau khi nhả latch, hai task đã được nhận hoàn thành.

Đối với production, metric nên phân biệt **đã từ chối do pool bão hòa** với **đã từ chối vì executor shutdown**, nếu thông tin này cần cho vận hành. Đừng lạm dụng metric/logging chậm hoặc blocking I/O trong rejection handler: nó chạy trên đường submit và có thể làm producer càng chậm hoặc gây contention.

## 13. Cẩn thận với submit(), execute() và Future

### execute(Runnable)

execute() nhận Runnable. Nếu handler **AbortPolicy** ném, caller bắt được lỗi gửi task. Nếu **CallerRunsPolicy** chạy Runnable ngay, execute chỉ trở về khi Runnable.run() đã kết thúc trên caller. Nếu **DiscardPolicy** hoặc **DiscardOldestPolicy** âm thầm bỏ task, execute có thể trở về bình thường dù task không được thực hiện.

### submit(Runnable/Callable)

submit() thường tạo một **RunnableFuture**, sau đó gọi execute(RunnableFuture):

~~~text
submit(callable)
    |
    v
new RunnableFuture
    |
    v
execute(runnableFuture)
    |
    +-- worker/queue nhận -> Future có thể hoàn tất
    |
    +-- CallerRunsPolicy -> FutureTask.run trên caller -> Future done
    |
    +-- AbortPolicy -> ném RejectedExecutionException,
    |                  không trả Future thành công
    |
    +-- DiscardPolicy -> bỏ FutureTask -> Future có thể không bao giờ done
    |
    +-- DiscardOldestPolicy -> FutureTask cũ bị loại khỏi queue
                               -> Future cũ có thể không bao giờ done
~~~

**Future.get() chỉ có hợp đồng chờ kết quả của Future**, không phải hợp đồng phát hiện task đã bị silent discard bởi một handler tùy ý. Đối với các policy mất task, caller cần giao thức xác nhận **đã được chấp nhận và sẽ có trạng thái cuối** nếu đó là yêu cầu nghiệp vụ.

### Exception trong task khác rejection

Một task đã được nhận, chạy rồi ném IllegalArgumentException là **failure của task**. Với submit(), Future.get() sẽ ném ExecutionException chứa cause, không phải RejectedExecutionException của bước gửi.

Hệ thống cần phân biệt tối thiểu:

- **Rejected**: không được nhận vào executor.
- **Queued**: đã được nhận, chưa chắc đã bắt đầu.
- **Running**: đang thực hiện.
- **Succeeded / Failed**: task đã kết thúc với kết quả.
- **Cancelled / Timed out while waiting**: trạng thái Future và trạng thái nghiệp vụ có thể khác nhau.

Nếu task bị silent discard nhưng Future chưa done, nó không tự thuộc các trạng thái cuối ở trên. Đây là lý do silent policy khó dùng cho workflow đòi tracking.

## 14. Rejection do shutdown: không phải lúc nào cũng do tải cao

Khi đã gọi **shutdown()**, executor **không nhận task mới**, dù queue đang rỗng và không có worker nào bận. Lời submit tiếp theo có thể đi vào rejection handler.

- Với AbortPolicy, caller thường nhận RejectedExecutionException.
- Với CallerRunsPolicy, task bị bỏ khi executor đã shutdown: **không chạy trên caller**.
- Với DiscardPolicy, task bị bỏ.
- Với DiscardOldestPolicy, task bị bỏ mà không cố enqueue lại.

**Đây là sự khác biệt quan trọng giữa “hết capacity” và “đã đóng nhận việc”**. Nếu handler chỉ tăng counter “overloaded”, metric sẽ bị sai khi shutdown. Một custom handler có thể kiểm tra executor.isShutdown() để phân loại, nhưng snapshot đó có thể thay đổi do race; muốn tính toán chính xác số loại lỗi có thể phải có giao thức lifecycle/telemetry chặt hơn.

### Không chọn CallerRunsPolicy để ép chạy sau shutdown

Một số người dùng CallerRunsPolicy với kỳ vọng “task sẽ luôn được chạy dù pool đã đóng”. **Không đúng.** Handler chỉ chạy task trên caller nếu executor **chưa shutdown**. Một execute() quay về bình thường sau shutdown dưới CallerRunsPolicy không phải bằng chứng task đã thực thi.

### Submit sau shutdown với DiscardPolicy

Future trả về từ submit sau shutdown dưới DiscardPolicy có thể bị bỏ mà không done, giống tình huống bão hòa. Vì vậy cần quản lý vòng đời producer và executor: **dừng producer trước khi shutdown executor**, hoặc quy định cách báo lỗi rõ khi gửi vào executor đã đóng.

## 15. CallerRunsPolicy là backpressure nhưng không phải điều tiết hoàn hảo

Khi producer tự chạy task, tốc độ submit thường giảm, giảm áp lực lên queue. Tuy nhiên mức độ phụ thuộc vào đặc tính task:

- Nếu task rất nhanh, caller chạy nó rất nhanh và có thể tiếp tục flood ngay lập tức.
- Nếu producer có nhiều thread, **nhiều caller có thể cùng chạy task**, làm tổng số task đang thực thi **vượt số worker của pool**. Do đó **maximumPoolSize không còn là giới hạn tổng concurrency** nếu tính cả caller-run tasks.
- Nếu caller là event-loop thread, request thread hoặc thread đang giữ lock, chạy task có thể ảnh hưởng lớn đến độ trễ và tiến độ của hệ thống khác.
- Nếu task yêu cầu thread name, ThreadLocal, transaction context hoặc security context nhất định, chạy trên caller thay đổi các giả định đó.
- Nếu task có thể block trên nguồn lực mà producer đang giữ, chờ có thể tạo deadlock.

### Trường hợp cần hard cap tổng concurrency

Nếu yêu cầu là “không quá K thao tác gọi dịch vụ bên ngoài đồng thời từ **mọi thread**”, **CallerRunsPolicy không tự bảo đảm K**. Cân nhắc Semaphore/quota độc lập bao quanh nơi gọi dịch vụ, hoặc policy từ chối rõ ràng khi bão hòa, với ranh giới permit hợp lệ.

Một executor chỉ giới hạn **worker của chính nó**; nó không quản lý số task chạy trực tiếp trên mọi producer.

## 16. Khi nào được phép bỏ task?

Một chiến lược loss-tolerant phải dựa trên đặc tả, không chỉ theo tên policy:

| Loại công việc | Có thể cân nhắc mất task? | Điều kiện cần thiết |
| --- | --- | --- |
| Telemetry debug tần suất cao | Có thể | Được phép thiếu mẫu; có metric dropped |
| Metrics cập nhật liên tục | Có thể | Snapshot kế tiếp thay thế được snapshot trước |
| Cache warm-up | Có thể | Cache miss vẫn có đường xử lý đúng |
| UI preview frame cũ | Có thể | Chỉ trạng thái mới nhất quan trọng, có cơ chế coalescing rõ |
| Ghi hóa đơn / chuyển tiền | Thường không | Cần xác nhận hoặc durable handoff, retry idempotent |
| Gửi kết quả task mà caller đang Future.get() | Không nên silent discard | Future phải đạt trạng thái cuối hoặc báo lỗi rõ |
| Tác vụ cleanup tài nguyên | Thường không | Bỏ task có thể gây rò tài nguyên |
| Xử lý lệnh có dependency trước-sau | Không thể bỏ tùy ý | Bỏ B có thể làm C sai điều kiện |

**DiscardOldestPolicy không tự tương đương “chỉ giữ giá trị mới nhất của mỗi key”.** Nó bỏ head của **toàn queue**, không coalesce theo key, không xem các dependency, không biết tính thay thế của payload. Nếu business cần latest-per-key, hãy tự định nghĩa queue/coalescing theo key và hợp đồng completion rõ ràng.

## 17. Chọn policy theo đặc tả: decision matrix

| Yêu cầu chính | Policy khởi đầu | Vì sao |
| --- | --- | --- |
| Task bắt buộc được nhận hoặc báo lỗi rõ | **AbortPolicy** / custom handler ném lỗi | Producer không bị silent loss |
| Producer có thể tự làm task và chấp nhận bị giữ | **CallerRunsPolicy** | Tạo áp lực ngược, nhưng phải chứng minh thread affinity và concurrency |
| Task mới có thể bỏ an toàn, không ai chờ Future | **DiscardPolicy**, kèm telemetry | Silent drop chỉ hợp lệ với loss-tolerant contract |
| Snapshot cũ trong queue có thể thay bằng task mới | **DiscardOldestPolicy** sau khi phân tích FIFO/order/dependency | Có thể giảm độ cũ, nhưng mất task chờ và Future |
| Nghiệp vụ không được mất việc qua restart | Không policy nào đủ | Cần durable queue/transaction/outbox hoặc giao thức persistence |
| Cần hard cap concurrency của resource | Executor bounded + quota/permit phù hợp | CallerRuns có thể chạy ngoài worker pool |
| Task bắt buộc chạy trên một owner thread | **Không dùng CallerRunsPolicy** | Caller execution phá confinement |
| Muốn người gửi giảm tốc có kiểm soát | Custom backpressure rõ, deadline hoặc bounded handoff | Không đồng nghĩa im lặng bỏ task |

**Lựa chọn mặc định an toàn để phát triển ứng dụng có yêu cầu không mất việc** thường là **AbortPolicy** hoặc custom handler vừa ghi metric vừa báo lỗi. CallerRunsPolicy là công cụ hữu ích nhưng phải xét **latency và execution context**. Discard và DiscardOldest chỉ phù hợp khi loss semantics thực sự được chấp thuận.

## 18. Hệ quả khi queue đầy và chính sách không thay đổi tài nguyên thật

Một sai lầm là nghĩ chọn handler tốt sẽ “giải quyết được overload”. Handler chỉ quyết định **điều gì xảy ra tại điểm không nhận được task**; nó không làm CPU, RAM, DB pool hay remote service mạnh hơn.

Giả sử:

~~~text
Input rate: 1.000 tasks/giây
Service capacity: 200 tasks/giây
Backlog growth: khoảng 800 tasks/giây nếu cứ nhận tất cả
~~~

Các hành vi:

- **AbortPolicy**: làm lộ hiện tượng overload; producer phải giảm tốc hoặc chuyển đường xử lý.
- **CallerRunsPolicy**: producer tự làm một phần công việc, thường bị chậm; nhưng có thể đẩy tải sang request thread hoặc nơi khác.
- **DiscardPolicy**: không để một số task mới tích lũy nhưng mất dữ liệu.
- **DiscardOldestPolicy**: ưu tiên task đến sau bằng cách loại task đang chờ trước; độ mới có thể tăng, nhưng việc mất task vẫn tồn tại.

Muốn ổn định lâu dài cần **capacity planning, admission control, rate limiting, bounded queue, deadline, autoscaling phù hợp, đo throughput** hoặc thay đổi thiết kế workload. Chọn handler chỉ là một phần của overload strategy.

## 19. Những lỗi thực tế thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Tạo fixed pool và tin rằng queue tự giới hạn | Memory/backlog tăng trước khi reject | Dùng bounded queue khi cần backpressure rõ |
| Chỉ kiểm tra số worker mà bỏ qua queue | Nhầm trạng thái còn capacity | Xem worker, queue, active count và submit rate cùng nhau |
| Catch RejectedExecutionException rồi trả success | Task không nhận nhưng business báo hoàn thành | Propagate/report/retry có kiểm soát |
| CallerRunsPolicy trên task phải chạy ở owner worker | Race và sai thứ tự | Không dùng caller-run cho task thread-affine |
| CallerRunsPolicy trên request thread có SLA chặt | Latency đuôi tăng mạnh | Dùng hạn mức nhận việc hoặc báo bận rõ |
| Dùng CallerRunsPolicy để giới hạn tổng concurrency | Caller tasks cộng thêm ngoài worker | Quota/permit ở ranh giới resource |
| DiscardPolicy cho task bắt buộc | Mất task im lặng | Abort/custom handler/durable handoff |
| submit với DiscardPolicy rồi Future.get vô hạn | Future có thể không bao giờ done | Không silent discard hoặc có giao thức terminal state |
| DiscardOldestPolicy với FIFO command phụ thuộc nhau | Bị mất command cũ, sai workflow | Không bỏ tùy ý; giữ order hoặc coalesce có chủ đích |
| DiscardOldestPolicy với queue không có head thích hợp | Retry reject không tiến triển | Chọn handler hợp queue; tránh policy này với SynchronousQueue |
| Hiểu oldest là task đang chạy lâu nhất | Sai task được loại | Chỉ head trong work queue bị poll |
| Dùng isShutdown() như kiểm tra đồng bộ độc lập trước submit | Race giữa check và submit | Xử lý rejection và lifecycle đúng |
| Cho rằng shutdown tự hoàn tất Future bị bỏ | Future vẫn có thể pending | Có cơ chế cancel/report riêng |
| Retry không giới hạn sau rejection | Amplify overload | Deadline, backoff, idempotency, giới hạn retry |
| Gọi blocking API trong handler tùy chỉnh khi đang giữ khóa khác | Tăng contention/deadlock | Handler ngắn, không blocking hoặc có thiết kế chứng minh được |
| Đổi từ Abort sang Discard chỉ để hết exception | Che giấu overload, mất dữ liệu | Sửa capacity và chiến lược backpressure |

## 20. Quan sát và kiểm chứng trong hệ thống thực

Để biết rejection policy đang hoạt động như mong đợi, theo dõi:

- **Số task đã submit** theo nhóm workload.
- **Số task được chấp nhận** vào queue/worker hoặc chạy tại caller.
- **Số task bị reject/drop** theo lý do capacity hay shutdown nếu phân biệt được.
- **Queue size** và **queue age** (thời gian từ submit đến start).
- **Active worker count**, pool size, completed task count.
- **CallerRuns invocations** và thời gian producer phải chạy task.
- **DiscardOldest evictions** nếu dùng custom telemetry.
- **Latency p95/p99**, memory, thread count, số lỗi/timeout/retry.
- **Future đã hoàn tất, pending và canceled**; không chỉ đếm task đã submit.

**Lưu ý về metric:** ThreadPoolExecutor.getTaskCount(), getCompletedTaskCount(), getQueue().size(), getActiveCount() là các số đo/snapshot có giới hạn và có thể thay đổi giữa lúc đọc. Không xây dựng business logic “còn đúng một chỗ trống” bằng cách kiểm tra size rồi execute, vì thread khác có thể submit ngay sau check.

Nếu cần chính xác hóa trạng thái nhận việc, thiết kế **acknowledgement** ở ranh giới ingress, không suy từ các số đo chẩn đoán.

### Test policy nên kiểm tra điều gì?

1. Giữ worker bằng **CountDownLatch**, lấp đầy queue, rồi submit task gây rejection.
2. Kiểm tra **task nào thực sự chạy** và nhánh exception nào xuất hiện.
3. Với CallerRunsPolicy, kiểm tra **Thread identity** của task thứ ba.
4. Với Discard/DiscardOldest, kiểm tra **Future được trả có thể vẫn pending**, không gọi get vô hạn.
5. Thử submit sau shutdown; đánh giá hành vi riêng của từng handler.
6. Giả lập lỗi task và phân biệt **ExecutionException** với **RejectedExecutionException**.
7. Kiểm tra **shutdown/cleanup** để test không tự treo vì worker đang chờ latch.
8. Lập luận dựa trên hợp đồng API và invariant; một stress test chạy không lỗi không chứng minh mọi lịch chạy đều đúng.

## 21. Shutdown, cancellation, interruption và trách nhiệm cuối cùng

**ThreadPoolExecutor.shutdown()** từ chối nhận task mới nhưng vẫn xử lý task đã được chấp nhận trước đó theo hợp đồng. **shutdownNow()** cố ngắt những task đang chạy và trả danh sách task chưa bắt đầu, nhưng không bảo đảm task đang chạy sẽ dừng ngay.

**Future.cancel(true)** là yêu cầu hủy có thể interrupt worker; không cưỡng chế rollback các side effect đã phát sinh. Với task bị DiscardPolicy/DiscardOldestPolicy loại bỏ mà Future chưa done, caller có thể gọi **cancel()** nếu giữ được reference, nhưng biết **khi nào task bị mất** mới là vấn đề. Handler silent mặc định không cung cấp callback cho caller biết việc đó.

Nếu công việc liên quan thanh toán, file hoặc trạng thái tại database:

- Rejection **không** nhất thiết nghĩa chưa có side effect từ các bước trước khi submit.
- Retry có thể tạo thao tác trùng nếu không có idempotency key.
- CallerRunsPolicy có thể thực hiện side effect **ngay trong lời submit**, không đợi worker.
- DiscardOldestPolicy có thể bỏ một bước mà các bước khác đã dựa vào.
- Shutdown trong lúc producer vẫn gửi việc cần giao thức rõ để không thất lạc công việc.

Do đó, policy chỉ bảo vệ **ranh giới đưa task vào executor trong JVM**, không phải bảo đảm transaction hay exactly-once giữa nhiều dịch vụ.

## 22. Checklist trước khi chốt policy

**Đặc tả công việc:**

- [ ] Task có được phép mất không? Nếu có, mất mới hay mất cũ hợp lý?
- [ ] Task có dependency thứ tự hoặc trạng thái không được bỏ qua không?
- [ ] Caller có cần biết chính xác trạng thái “được nhận” và “hoàn thành” không?
- [ ] Có Future.get() đang chờ mọi task sẽ eventually done không?
- [ ] Task có side effect cần idempotency, retry hay durable store không?

**Thread và tài nguyên:**

- [ ] Worker và queue đã có giới hạn phù hợp với thực tế chưa?
- [ ] Task có thể chạy an toàn trên thread caller không?
- [ ] Nếu CallerRuns, tổng concurrency thực tế ở resource có còn được giới hạn không?
- [ ] Có lock/thread-affinity/ThreadLocal nào bị thay đổi khi caller trực tiếp chạy task không?
- [ ] Có giải pháp riêng cho burst, long blocking I/O và overload kéo dài không?

**Vận hành và kiểm thử:**

- [ ] Có metric rejected, discarded, queue size/age và caller-run latency không?
- [ ] Có test deterministic cho bão hòa và submit sau shutdown không?
- [ ] Có cảnh báo về Future pending do silent discard không?
- [ ] Có đường phản hồi hoặc retry/backoff có giới hạn khi AbortPolicy ném lỗi không?
- [ ] Shutdown có dừng producer hoặc báo trạng thái từ chối rõ ràng không?
- [ ] Có thu thập exception của task đã nhận qua Future/handler đúng cách không?

## 23. Câu hỏi tự kiểm tra

**Câu 1.** Worker đã bận, queue đã đầy, AbortPolicy làm gì?  
**Đáp án:** Ném RejectedExecutionException ngay trên đường execute/submit; caller phải xử lý không nhận task.

**Câu 2.** CallerRunsPolicy có luôn chạy task trên worker pool không?  
**Đáp án:** Không. Khi bão hòa và chưa shutdown, nó gọi task.run() trên chính thread gọi execute, thường là producer.

**Câu 3.** Nếu executor đã shutdown, CallerRunsPolicy có chạy task mới trên caller để “cứu” task không?  
**Đáp án:** Không. Handler chuẩn không chạy task khi executor đã shutdown và có thể bỏ nó mà không ném lỗi.

**Câu 4.** DiscardPolicy có phù hợp nếu caller luôn gọi Future.get() không timeout không?  
**Đáp án:** Không nên. Một RunnableFuture bị bỏ có thể không bao giờ done hoặc canceled, khiến get() chờ vô hạn.

**Câu 5.** DiscardOldestPolicy bỏ task nào?  
**Đáp án:** Head của work queue, không phải task đang chạy. Với FIFO queue, thường là task đã chờ lâu nhất.

**Câu 6.** Vì sao CallerRunsPolicy có thể không giữ được hard cap 4 tác vụ thực thi đồng thời?  
**Đáp án:** Ngoài 4 worker, nhiều thread producer có thể tự chạy rejected task, làm tổng concurrency vượt 4.

**Câu 7.** Dùng DiscardOldestPolicy với PriorityBlockingQueue có nghĩa chắc chắn loại task submit sớm nhất không?  
**Đáp án:** Không. Queue head do ordering của queue quyết định, không nhất thiết theo thời điểm submit.

**Câu 8.** Cần xử lý task quan trọng không mất, nên bắt đầu xem policy nào?  
**Đáp án:** AbortPolicy/custom fail-fast kèm retry/backpressure/durable handoff phù hợp. Không handler nào một mình cung cấp durability.

**Câu 9.** Thay exception bằng DiscardPolicy có làm executor mạnh hơn không?  
**Đáp án:** Không. Nó chỉ che đi việc từ chối và bỏ công việc. Phải xử lý capacity, queue, producer rate và đo tải.

**Câu 10.** Future.isDone() false sau pool.awaitTermination(true) có mâu thuẫn không?  
**Đáp án:** Không nếu FutureTask từng bị silent discard khỏi queue mà không chạy hoặc cancel. Pool đã hết task còn quản lý, nhưng Future bên ngoài vẫn pending.

**Câu 11.** Tại sao shutdown() rồi submit mới có thể bị từ chối dù queue còn trống?  
**Đáp án:** Vì executor đã ngừng nhận công việc mới; rejection không chỉ do queue đầy.

**Câu 12.** Khi task trong pool thất bại sau khi đã nhận, caller nhận loại lỗi nào?  
**Đáp án:** Với submit(), Future.get() thường ném ExecutionException có cause; khác với RejectedExecutionException xảy ra ở giai đoạn gửi task không được nhận.

## 24. Tổng kết

Bốn **RejectedExecutionHandler** chuẩn của ThreadPoolExecutor đưa ra **bốn quyết định rất khác nhau** khi executor không nhận task:

- **AbortPolicy:** báo lỗi rõ ràng, thích hợp khi producer phải chịu trách nhiệm xử lý công việc không được nhận.
- **CallerRunsPolicy:** chạy task trên thread gửi khi pool còn hoạt động; tạo một dạng backpressure nhưng ảnh hưởng latency, execution context và hard cap concurrency.
- **DiscardPolicy:** bỏ task mới im lặng; chỉ phù hợp khi loss là một phần được chấp nhận rõ trong đặc tả.
- **DiscardOldestPolicy:** loại head của queue rồi thử nhận task mới; có thể bỏ task đã chờ và làm Future của task bị loại treo mãi.

Để áp dụng đúng, luôn xét **kiểu queue, core/max workers, trạng thái shutdown, Future, thứ tự/dependency, thread confinement, metrics và trách nhiệm nghiệp vụ khi mất task**. Một rejection policy không tự sửa overload hay bảo đảm dữ liệu; nó chỉ quyết định hệ thống phản ứng thế nào tại điểm quá tải hoặc ngừng nhận công việc.
