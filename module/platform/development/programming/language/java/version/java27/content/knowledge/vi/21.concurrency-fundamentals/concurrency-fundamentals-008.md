# ExecutorService, Future và lập lịch với ScheduledExecutorService

## 1. Vấn đề cần giải quyết: ai quản lý công việc chạy đồng thời?

Trong ứng dụng Java, không phải mọi công việc đều nên chạy trực tiếp trên thread đang xử lý yêu cầu. Đọc dữ liệu từ nhiều nguồn, xử lý các tác vụ nền, gửi thông báo hoặc thực thi công việc theo lịch có thể yêu cầu một bộ phận chịu trách nhiệm **nhận tác vụ, phân phối việc thực thi, trả kết quả và quản lý vòng đời thread**.

**ExecutorService** giải quyết phần lớn những việc này mà không buộc mỗi tác vụ tự tạo và quản lý một Thread. **Future** đại diện cho kết quả hoặc trạng thái của công việc được gửi đi. **ScheduledExecutorService** bổ sung khả năng chạy một công việc sau một khoảng trì hoãn hoặc thực hiện định kỳ.

~~~mermaid
flowchart LR
    A["Luồng gọi: submit / schedule"] --> B["ExecutorService"]
    B --> C["Hàng đợi / chính sách lập lịch"]
    C --> D["Worker thread thực hiện Callable/Runnable"]
    D --> E["Kết quả / exception"]
    E --> F["Future hoặc ScheduledFuture"]
    F --> G["Caller: get, timeout, cancel"]
    B --> H["shutdown / close: quản lý vòng đời"]
~~~

Mục tiêu của bài là lựa chọn đúng API cho từng yêu cầu, phân biệt **đã gửi tác vụ** với **đã hoàn tất**, xử lý thất bại và hủy có kiểm soát, đồng thời tránh các lỗi vận hành như tạo quá nhiều thread, chờ vô hạn hoặc chạy lịch sai ý nghĩa thời gian.

**Phạm vi phiên bản:** Những API được trình bày đã là thành phần chính thức của Java SE và tiếp tục áp dụng trong **Java 27**. ExecutorService là AutoCloseable từ Java 19; virtual thread executor là API chính thức từ Java 21. Bài không phụ thuộc vào các API preview hoặc cơ chế cũ không còn được khuyến nghị.

## 2. Phân biệt Executor, ExecutorService, ScheduledExecutorService và Future

| Interface / lớp | Vai trò | Điểm cần nhớ |
|---|---|---|
| **Executor** | Nhận một Runnable bằng **execute(Runnable)** | Không tự cung cấp Future hoặc API shutdown |
| **ExecutorService** | Nhận Runnable/Callable, quản lý vòng đời, thực hiện nhóm tác vụ | Có **submit**, **invokeAll**, **invokeAny**, **shutdown**, **close** |
| **ScheduledExecutorService** | ExecutorService hỗ trợ trì hoãn và tác vụ định kỳ | Có **schedule**, **scheduleAtFixedRate**, **scheduleWithFixedDelay** |
| **Future<V>** | Tay nắm để chờ kết quả, kiểm tra hoàn tất, hủy | Có **get**, **cancel**, **isDone**, **isCancelled** |
| **ScheduledFuture<V>** | Future của tác vụ đã được lập lịch | Kết hợp Future với thông tin trì hoãn |
| **Executors** | Lớp factory để tạo các executor thường dùng | Lựa chọn factory tùy tải và chính sách tài nguyên |
| **ThreadPoolExecutor** | Lớp triển khai thread pool có thể cấu hình chi tiết | Pool size, queue, rejection policy |
| **ScheduledThreadPoolExecutor** | Lớp triển khai scheduler có thể cấu hình | Chính sách giữ/xóa các tác vụ theo lịch |

**Quan hệ kế thừa**: ScheduledExecutorService **extends ExecutorService**, còn ExecutorService **extends Executor**. **ScheduledFuture** extends Future và Delayed; nó không phải chính ExecutorService.

Một executor **không phải** một thread. Nó là bộ phận điều phối thực thi, có thể sử dụng một thread, nhiều platform threads hoặc tạo virtual thread cho mỗi tác vụ, tùy implementation.

## 3. Task là Runnable hoặc Callable

Hai dạng công việc phổ biến:

- **Runnable**: có phương thức **void run()**, không trả giá trị; không khai báo checked exception.
- **Callable<V>**: có phương thức **V call() throws Exception**, trả giá trị kiểu V và có thể khai báo checked exception.

~~~java
import java.util.concurrent.Callable;

Runnable notifyUser = () ->
    System.out.println("Notification requested");

Callable<Integer> calculate = () -> 7 * 7;
~~~

Dùng Runnable khi kết quả của tác vụ không cần trả về qua Future. Dùng Callable khi cần một giá trị, hoặc muốn exception được ghi nhận trong kết quả bất đồng bộ.

Không nên suy ra Runnable luôn có tác dụng phụ và Callable luôn thuần khiết. Cả hai đều là code Java bình thường; chúng có thể đọc/ghi trạng thái, gọi I/O và ném các unchecked exceptions.

## 4. Tạo ExecutorService bằng Executors

Một số lựa chọn hiện hành:

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

ExecutorService fixed = Executors.newFixedThreadPool(4);
ExecutorService sequential = Executors.newSingleThreadExecutor();
ExecutorService virtual = Executors.newVirtualThreadPerTaskExecutor();
~~~

Các factory phục vụ mô hình khác nhau:

| Factory | Đặc tính | Phù hợp khi |
|---|---|---|
| **newFixedThreadPool(n)** | Có n platform threads hoạt động tối đa; hàng đợi tác vụ có thể tăng | Muốn giới hạn số worker cho tải tương đối kiểm soát được |
| **newSingleThreadExecutor()** | Thực hiện các tác vụ tuần tự qua một worker | Cần thứ tự xử lý và không muốn hai tác vụ cùng chạy |
| **newCachedThreadPool()** | Tái sử dụng thread rảnh, có thể tạo thêm rất nhiều platform threads khi tải cao | Chỉ khi kiểm soát nguồn phát sinh công việc và hiểu rõ rủi ro |
| **newVirtualThreadPerTaskExecutor()** | Tạo virtual thread cho mỗi tác vụ, không phải fixed-size pool | Nhiều tác vụ chờ I/O, có cấu trúc tài nguyên hợp lý |
| **newScheduledThreadPool(n)** | Pool gồm các worker để thực thi tác vụ theo thời điểm trì hoãn/định kỳ | Scheduler có nhiều công việc cần lập lịch |

**Lưu ý về tải:** Fixed thread pool thường dùng hàng đợi **không giới hạn dung lượng**; nó giới hạn số worker nhưng không tự giới hạn số tác vụ đang chờ. Cached thread pool không cung cấp giới hạn thread nghiêm ngặt. Cần đặt giới hạn từ tầng tiếp nhận hoặc dùng ThreadPoolExecutor cấu hình queue và rejection policy khi tải có thể bùng nổ.

Trong Java hiện đại, nên dùng **try-with-resources** với ExecutorService có vòng đời ngắn, hoặc quản lý rõ ràng ở lifecycle của ứng dụng. Không nên để executor được tạo mới trên mỗi request mà không đóng.

## 5. execute khác submit như thế nào?

**execute(Runnable)** là phương thức của Executor: gửi việc để thực hiện, không trả tay nắm Future.

~~~java
import java.util.concurrent.*;

try (ExecutorService workers = Executors.newFixedThreadPool(2)) {
    workers.execute(() ->
        System.out.println("Running without a Future")
    );
}
~~~

**submit(...)** là phương thức của ExecutorService: trả **Future** để caller có thể chờ, lấy kết quả, kiểm tra hoặc yêu cầu hủy.

~~~java
import java.util.concurrent.*;

try (ExecutorService workers = Executors.newFixedThreadPool(2)) {
    Future<Integer> answer = workers.submit(() -> 40 + 2);
    System.out.println(answer.get()); // 42
}
~~~

Các overload quan trọng:

~~~java
Future<?> first = workers.submit(
    (Runnable) () -> System.out.println("done")
);

Future<String> second = workers.submit(
    (Runnable) () -> System.out.println("saved"),
    "OK"
);

Future<Integer> third = workers.submit(
    (Callable<Integer>) () -> 21 * 2
);
~~~

- **submit(Runnable)** có Future với kết quả bình thường là **null**.
- **submit(Runnable, result)** trả về đối tượng **result** khi Runnable hoàn tất bình thường.
- **submit(Callable<V>)** trả về giá trị từ **call()**.

Cả **execute** và **submit** đều có thể ném **RejectedExecutionException** khi executor từ chối tác vụ, ví dụ sau khi shutdown hoặc khi pool có chính sách từ chối do quá tải.

**Quan sát lỗi:** Với task gửi bằng submit, một unchecked exception thường được lưu trong Future và lộ ra khi gọi **get()**. Nếu bỏ quên Future, lỗi có thể không được quan sát ở điểm mong muốn. Đừng giả định rằng một **UncaughtExceptionHandler** sẽ tự xử lý mọi lỗi từ các task được submit.

## 6. Future: kết quả có thể chưa sẵn sàng

**Future<V>** đại diện cho một computation đã được gửi đi. Sau submit, việc tạo Future **không chứng minh** code của Callable đã chạy hoặc hoàn thành.

~~~java
Future<String> result = workers.submit(() -> "completed");

System.out.println(result.isDone()); // Có thể true hoặc false
System.out.println(result.get());    // Chờ rồi trả "completed"
~~~

Các API chính:

| Phương thức | Ý nghĩa |
|---|---|
| **get()** | Chờ đến khi hoàn thành rồi nhận kết quả; có thể chờ không giới hạn |
| **get(timeout, unit)** | Chờ tối đa khoảng thời gian quy định |
| **cancel(mayInterruptIfRunning)** | Cố yêu cầu hủy tác vụ |
| **isDone()** | Future đã vào trạng thái hoàn tất, bao gồm thành công, lỗi hoặc bị hủy |
| **isCancelled()** | Future bị hủy trước khi hoàn thành bình thường |
| **state()** | Trạng thái computation qua API Future hiện hành |
| **resultNow()**, **exceptionNow()** | Đọc kết quả/lỗi ngay khi trạng thái phù hợp, không chờ |

**isDone() == true không đồng nghĩa thành công.** Future có thể hoàn thành thất bại hoặc bị hủy. **isCancelled() == true** cho biết trạng thái Future đã bị hủy, nhưng không nhất thiết chứng minh mọi side effect của task đã dừng hoàn toàn.

Với **Future.state()**, trạng thái thuộc **Future.State** như RUNNING, SUCCESS, FAILED, CANCELLED. **resultNow()** chỉ phù hợp khi task đã thành công; **exceptionNow()** chỉ phù hợp khi task đã thất bại. Gọi không đúng trạng thái có thể ném **IllegalStateException**.

## 7. Lấy kết quả có timeout

**get()** không có giới hạn thời gian có thể khiến thread gọi chờ mãi khi công việc bị kẹt. Với các request hoặc tác vụ có thời hạn, dùng overload có timeout:

~~~java
import java.util.concurrent.*;

try (ExecutorService workers = Executors.newFixedThreadPool(2)) {
    Future<Integer> future = workers.submit(() -> 2 * 21);

    int value = future.get(2, TimeUnit.SECONDS);
    System.out.println(value); // 42
}
~~~

Nếu không kịp hoàn thành, **get(timeout, unit)** ném **TimeoutException**. Điều này có nghĩa **caller hết thời gian chờ**, **không tự động hủy** công việc đã gửi. Future có thể tiếp tục chạy và thực hiện side effects sau khi caller đã từ bỏ việc chờ.

~~~java
Future<String> future = workers.submit(this::callRemoteService);

try {
    String value = future.get(500, TimeUnit.MILLISECONDS);
    use(value);
} catch (TimeoutException timeout) {
    future.cancel(true); // Yêu cầu hủy, không bảo đảm task dừng ngay
    handleTimeout(timeout);
}
~~~

Trong đoạn trên, **callRemoteService**, **use** và **handleTimeout** là các phương thức minh họa của ứng dụng, không phải API JDK. Thao tác thật cần có hợp đồng hủy và giới hạn thời gian của I/O tương ứng; chỉ **Future.get(timeout)** không tạo timeout cho mọi API được gọi bên trong task.

## 8. Ba nhánh lỗi khi Future.get

Một phương thức chờ Future thường cần phân biệt:

- **InterruptedException**: thread đang chờ bị yêu cầu ngắt.
- **ExecutionException**: computation thất bại; dùng **getCause()** để lấy nguyên nhân.
- **TimeoutException**: vượt thời gian chờ do caller đặt.
- Ngoài ra **CancellationException** là unchecked exception khi Future đã bị hủy.

Ví dụ có chiến lược rõ ràng:

~~~java
import java.util.concurrent.*;

static <T> T await(Future<T> future, long timeoutMillis) {
    try {
        return future.get(timeoutMillis, TimeUnit.MILLISECONDS);

    } catch (InterruptedException interrupted) {
        future.cancel(true);
        Thread.currentThread().interrupt();
        throw new IllegalStateException("Waiting was interrupted", interrupted);

    } catch (TimeoutException timeout) {
        future.cancel(true);
        throw new IllegalStateException("Task exceeded time budget", timeout);

    } catch (ExecutionException failed) {
        throw new IllegalStateException("Task failed", failed.getCause());
    }
}
~~~

Việc chuyển checked exception thành unchecked ở đây là **một lựa chọn của adapter**, không phải luật bắt buộc. Nếu caller cần tự xử lý InterruptedException hoặc TimeoutException, tốt hơn có thể cho phương thức khai báo **throws** tương ứng.

**Không nuốt InterruptedException.** Khi không truyền nó lên dưới dạng checked exception, thường nên khôi phục cờ interrupt bằng **Thread.currentThread().interrupt()** trước khi kết thúc luồng điều khiển đang chờ.

**Không đổi mọi lỗi task thành null hoặc giá trị mặc định.** Cách làm đó dễ khiến lỗi hạ tầng bị hiểu nhầm là một kết quả nghiệp vụ hợp lệ.

## 9. cancel(false), cancel(true) và hủy hợp tác

**Future.cancel(boolean mayInterruptIfRunning)** yêu cầu hủy execution. Hành vi:

| Lời gọi | Ý định | Giới hạn |
|---|---|---|
| **cancel(false)** | Hủy tác vụ chưa chạy; nếu đang chạy thì không cố interrupt thread | Task đang chạy có thể hoàn tất code của nó |
| **cancel(true)** | Hủy, đồng thời cố interrupt thread đang thực thi nếu biết thread | Task có thể bỏ qua interrupt hoặc đang ở thao tác không phản ứng tức thì |

**cancel(true) không phải “kill thread”**. Java không cung cấp cơ chế an toàn tổng quát để cưỡng bức dừng mọi phép tính. Interruption là tín hiệu hợp tác; task phải viết code biết quan sát và xử lý nó.

~~~java
Callable<Integer> cooperativeTask = () -> {
    int processed = 0;

    while (!Thread.currentThread().isInterrupted()) {
        // Mô phỏng công việc có khả năng bị ngắt.
        Thread.sleep(50);
        processed++;

        if (processed == 5) {
            return processed;
        }
    }

    throw new InterruptedException("Task cancelled");
};
~~~

**Thread.sleep** có thể ném InterruptedException và xóa interrupted status khi ném; trong task được phép khai báo **throws Exception** như Callable, có thể truyền tiếp exception này để việc hủy không bị nuốt.

Khi đã có side effect như ghi vào DB hoặc gửi request, hủy Future không đồng nghĩa những side effect ấy được rollback. Cần transaction, idempotency hoặc cơ chế phục hồi riêng.

## 10. Quan hệ happens-before và an toàn dữ liệu

Java Memory Model quy định một số bảo đảm quan trọng:

1. Những hành động trong một thread **trước khi gửi Runnable/Callable** vào ExecutorService *happen-before* hành động của task đó.
2. Những hành động của task **happen-before** caller nhận thành công kết quả qua **Future.get()** tương ứng.

Điều này giúp việc công bố dữ liệu qua submit/get có ngữ nghĩa bộ nhớ xác định, nhưng **không biến mọi truy cập đồng thời thành thread-safe**.

Ví dụ một **AtomicInteger** cho phép nhiều task cập nhật bộ đếm với tính nguyên tử:

~~~java
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;

AtomicInteger counter = new AtomicInteger();

try (ExecutorService workers = Executors.newFixedThreadPool(4)) {
    Future<?> a = workers.submit((Runnable) counter::incrementAndGet);
    Future<?> b = workers.submit((Runnable) counter::incrementAndGet);

    a.get();
    b.get();
}

System.out.println(counter.get()); // 2
~~~

Nếu thay AtomicInteger bằng một biến int mutable dùng chung và cho nhiều task tăng bằng **counter++** mà không đồng bộ, có thể xảy ra **data race** và mất cập nhật. ExecutorService chỉ điều phối thực thi, không tự bảo vệ trạng thái dùng chung.

## 11. Quản lý vòng đời: shutdown, shutdownNow và awaitTermination

Một ứng dụng phải xác định **ai sở hữu executor** và khi nào cần đóng nó.

~~~text
RUNNING
  | shutdown()
  v
SHUTDOWN (không nhận task mới, xử lý task đã nhận)
  | tất cả task hoàn tất
  v
TERMINATED
~~~

Các phương thức:

| Phương thức | Hành vi |
|---|---|
| **shutdown()** | Bắt đầu dừng có trật tự, không nhận task mới; không chờ |
| **shutdownNow()** | Cố ngắt các task đang chạy, lấy các task chưa bắt đầu ra khỏi hàng đợi; không chờ |
| **awaitTermination(timeout, unit)** | Chờ executor chấm dứt hoặc hết thời gian chờ |
| **isShutdown()** | Đã nhận yêu cầu shutdown chưa |
| **isTerminated()** | Đã hoàn tất việc chấm dứt chưa |
| **close()** | Đóng ExecutorService, bắt đầu orderly shutdown và chờ chấm dứt |

**shutdownNow() là best effort**. Nó không bảo đảm mọi task thực sự dừng; những task không phản ứng với interrupt có thể tiếp tục chạy. Danh sách trả về là các tác vụ chưa bắt đầu; cần quyết định rõ có hủy, lưu lại hay xử lý lại chúng không.

**close()** trên ExecutorService là API chính thức từ Java 19. Với **try-with-resources**, nó đợi tác vụ hoàn tất trước khi rời phạm vi:

~~~java
try (ExecutorService workers = Executors.newFixedThreadPool(3)) {
    workers.submit(() -> System.out.println("task A"));
    workers.submit(() -> System.out.println("task B"));
} // close() chờ executor kết thúc
~~~

Không dùng **close()** như một cơ chế timeout. Nếu task bị kẹt hoặc không bao giờ kết thúc, **close() cũng có thể chờ rất lâu**. Với periodic task không được hủy, càng phải đặc biệt chú ý vòng đời trước khi đóng scheduler.

## 12. Ví dụ shutdown có timeout và phản ứng với interrupt

Với executor sống theo vòng đời một ứng dụng dài hạn, có thể chủ động dừng bằng quy trình rõ ràng:

~~~java
import java.util.concurrent.*;

static void stopExecutor(ExecutorService executor) {
    executor.shutdown();

    try {
        if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
            executor.shutdownNow();

            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                System.err.println("Executor did not terminate");
            }
        }
    } catch (InterruptedException interrupted) {
        executor.shutdownNow();
        Thread.currentThread().interrupt();
    }
}
~~~

Đây là ví dụ chiến lược lifecycle: sau khi yêu cầu shutdown và hết budget, thử shutdownNow; khi thread chờ bị interrupt, yêu cầu dừng mạnh hơn rồi khôi phục interrupted status.

Nếu các tác vụ quản lý dữ liệu quan trọng, phải xác định chính sách hoàn tất/rollback/checkpoint trước khi yêu cầu hủy. Không áp dụng ngẫu nhiên thời hạn 5 giây cho mọi hệ thống: con số thích hợp phụ thuộc yêu cầu và SLA.

## 13. invokeAll: chạy một nhóm tác vụ rồi nhận danh sách Future

**invokeAll(tasks)** gửi toàn bộ nhóm Callable và chờ chúng hoàn tất. Kết quả là **List<Future<T>>** theo **thứ tự danh sách task đầu vào**, không theo thứ tự kết thúc thực tế.

~~~java
import java.util.List;
import java.util.concurrent.*;

try (ExecutorService workers = Executors.newFixedThreadPool(3)) {
    List<Callable<Integer>> tasks = List.of(
        () -> 10 + 1,
        () -> 20 + 2,
        () -> 30 + 3
    );

    List<Future<Integer>> futures = workers.invokeAll(tasks);

    for (Future<Integer> future : futures) {
        System.out.println(future.get());
    }
}
~~~

Kết quả có thứ tự **11, 22, 33**, dù ba công việc có thể chạy trên các worker khác nhau.

Overload **invokeAll(tasks, timeout, unit)** chờ đến khi toàn bộ hoàn tất hoặc hết budget chung; các tác vụ chưa hoàn tất sẽ bị hủy trước khi phương thức trả về. Cần kiểm tra **isCancelled** trên từng Future trước khi lấy kết quả.

**Một task ném exception không khiến invokeAll tự ném ExecutionException ngay tại lệnh invokeAll.** Exception của task sẽ được quan sát qua **get()** của Future tương ứng.

## 14. invokeAny: lấy kết quả thành công đầu tiên

**invokeAny(tasks)** trả về kết quả của **một tác vụ hoàn thành thành công**, không phải nhất thiết là tác vụ kết thúc đầu tiên nếu tác vụ đó thất bại.

~~~java
import java.util.List;
import java.util.concurrent.*;

try (ExecutorService workers = Executors.newFixedThreadPool(3)) {
    List<Callable<String>> replicas = List.of(
        () -> "response from A",
        () -> "response from B",
        () -> "response from C"
    );

    String response = workers.invokeAny(replicas);
    System.out.println(response);
}
~~~

Kết quả là một trong ba chuỗi, thứ tự phụ thuộc thời gian thực thi và scheduling. Khi có kết quả hợp lệ, các tác vụ còn lại được hủy theo hợp đồng invokeAny; tương tự, nếu không tác vụ nào thành công, API có thể ném **ExecutionException**.

Overload có timeout cho phép đặt tổng ngân sách chờ. Không dùng invokeAny cho những tác vụ có side effects không thể lặp hoặc không thể hủy, ví dụ ba thao tác ghi thanh toán vào ba hệ thống, vì việc nhận một kết quả không tự rollback những thao tác khác.

**Nên dùng invokeAny** khi thật sự muốn lấy một kết quả từ những nguồn tương đương và đã thiết kế hủy/giải phóng tài nguyên an toàn.

## 15. Saturation, backpressure và hàng đợi không giới hạn

Thread pool cố định chỉ giới hạn **số tác vụ chạy đồng thời**, không tự giới hạn số tác vụ nằm chờ. Nếu tốc độ gửi công việc vượt tốc độ xử lý trong thời gian dài, hàng đợi có thể tăng và tiêu thụ bộ nhớ.

~~~text
Producer: 2000 jobs/s
        |
        v
Queue tăng liên tục
        |
        v
4 workers: chỉ xử lý 100 jobs/s
        |
        v
Latency và bộ nhớ tăng
~~~

Những cơ chế cần cân nhắc:

1. **Giới hạn lượng việc nhận vào** tại API/consumer trước khi submit.
2. **Bounded queue** với ThreadPoolExecutor để kiểm soát backlog.
3. **RejectedExecutionHandler** có chính sách rõ ràng khi bão hòa.
4. **Metrics** theo số lượng task đang đợi, đang chạy, latency và rejection.
5. **Cancellation và timeout** cho những việc không còn có giá trị.
6. **Phân chia pool theo loại workload** nếu task chậm có thể làm đói những task quan trọng.

Ví dụ cấu hình pool giới hạn queue:

~~~java
import java.util.concurrent.*;

ThreadPoolExecutor workers = new ThreadPoolExecutor(
    2,                      // corePoolSize
    2,                      // maximumPoolSize
    0, TimeUnit.MILLISECONDS,
    new ArrayBlockingQueue<>(100),
    new ThreadPoolExecutor.AbortPolicy()
);

try (workers) {
    workers.execute(() -> System.out.println("Work"));
}
~~~

Với **AbortPolicy**, khi pool không còn khả năng nhận việc, **RejectedExecutionException** được ném để caller có thể thực hiện backpressure, trả lỗi phù hợp hoặc điều phối retry có kiểm soát.

**CallerRunsPolicy** là một lựa chọn khác: khi executor chưa shutdown và từ chối vì bão hòa, task có thể chạy ngay trên thread gửi, tạo hiệu ứng làm chậm producer. Nhưng điều này làm thay đổi độ trễ của caller, và chính sách đó bỏ tác vụ khi executor đã shutdown; phải hiểu kỹ hợp đồng trước khi áp dụng.

## 16. Đặt tên worker và phân chia trách nhiệm

Trong môi trường production, tên thread có thể giúp chẩn đoán thread dump và log. Java có API tạo ThreadFactory hiện đại:

~~~java
import java.util.concurrent.*;

ThreadFactory factory =
    Thread.ofPlatform().name("payment-worker-", 0).factory();

try (ExecutorService workers =
         Executors.newFixedThreadPool(3, factory)) {

    Future<String> future = workers.submit(
        () -> Thread.currentThread().getName()
    );

    System.out.println(future.get()); // payment-worker-0, ...
}
~~~

Đặt tên theo trách nhiệm nghiệp vụ thay vì một tên chung cho toàn bộ tác vụ nền. Điều này không thay thế tracing hoặc request ID: thread pool có thể tái sử dụng cùng worker cho nhiều yêu cầu khác nhau.

Cân nhắc pool chuyên biệt cho các loại việc có đặc tính tài nguyên khác nhau; tránh dùng một pool nhỏ cho tác vụ khóa dài rồi gửi các task ngắn phụ thuộc vào chính pool đó.

## 17. Lỗi deadlock khi chờ Future trong cùng một pool quá nhỏ

Một tình huống nguy hiểm:

~~~java
// Anti-pattern: không chạy đoạn này.
ExecutorService single = Executors.newSingleThreadExecutor();

Future<Integer> parent = single.submit(() -> {
    Future<Integer> child = single.submit(() -> 42);
    return child.get(); // Parent giữ worker; child không có worker để chạy
});

System.out.println(parent.get()); // Có thể chờ mãi
~~~

Vì chỉ có một worker, task cha giữ worker trong lúc chờ task con; task con lại phải đợi worker rảnh. Đó là **thread-starvation deadlock**.

Cách xử lý phụ thuộc bài toán:

- Nếu task con chỉ là tính toán nhỏ, gọi trực tiếp thay vì submit lại vào cùng pool.
- Nếu cần nhiều tác vụ độc lập, sắp xếp luồng điều phối để không giữ worker trong khi chờ một tác vụ phụ thuộc vào chính pool đó.
- Nếu workload có nhiều lời gọi I/O, cân nhắc virtual threads hoặc một cấu trúc concurrency phù hợp, nhưng vẫn phải kiểm soát số kết nối và trạng thái phụ thuộc.

Không chỉ tăng pool size lên 2 rồi coi vấn đề đã được giải quyết vĩnh viễn: nếu độ sâu lồng nhau hoặc số task đồng thời tăng, deadlock/starvation có thể tái xuất hiện.

## 18. ScheduledExecutorService: trì hoãn và lập lịch định kỳ

**ScheduledExecutorService** mở rộng ExecutorService để hỗ trợ chạy việc sau khoảng trì hoãn hoặc lặp lại theo chu kỳ. Các phương thức chính:

| Phương thức | Tác dụng | Giá trị trả về |
|---|---|---|
| **schedule(Runnable, delay, unit)** | Chạy Runnable một lần sau khoảng trì hoãn | ScheduledFuture<?> |
| **schedule(Callable<V>, delay, unit)** | Chạy Callable một lần rồi trả kết quả | ScheduledFuture<V> |
| **scheduleAtFixedRate(Runnable, initialDelay, period, unit)** | Lặp với nhịp bắt đầu được tính từ mốc đầu | ScheduledFuture<?> |
| **scheduleWithFixedDelay(Runnable, initialDelay, delay, unit)** | Lặp với khoảng chờ tính từ khi lần trước kết thúc | ScheduledFuture<?> |

Tạo scheduler:

~~~java
import java.util.concurrent.*;

ScheduledExecutorService scheduler =
    Executors.newScheduledThreadPool(2);
~~~

Một scheduler có thể có nhiều worker để thực hiện nhiều tác vụ độc lập. Nó không bảo đảm chính xác đến từng nano giây: thời điểm chạy thực tế phụ thuộc worker rảnh, hệ điều hành, độ trễ thực thi và tải máy.

**Các tham số delay/period thuộc kiểu tương đối**, không phải mốc ngày giờ trên đồng hồ. Scheduling này không trực tiếp thay thế hệ thống lịch việc “09:00 sáng mỗi ngày theo múi giờ” khi cần xử lý DST và thay đổi quy tắc thời gian.

## 19. Chạy tác vụ một lần sau thời gian chờ

Một-shot scheduling:

~~~java
import java.util.concurrent.*;

try (ScheduledExecutorService scheduler =
         Executors.newSingleThreadScheduledExecutor()) {

    ScheduledFuture<String> future = scheduler.schedule(
        () -> "ready",
        100,
        TimeUnit.MILLISECONDS
    );

    System.out.println(future.get(2, TimeUnit.SECONDS)); // ready
}
~~~

**schedule** trả Future ngay; việc xử lý thực tế chỉ được lên lịch để chạy sau delay tối thiểu trong điều kiện thông thường. Delay bằng 0 hoặc âm được coi là yêu cầu chạy ngay. Số period/delay âm hoặc bằng 0 **không hợp lệ** ở hai phương thức lập lịch định kỳ.

**ScheduledFuture.getDelay(unit)** có thể dùng để xem khoảng trì hoãn còn lại theo đơn vị mong muốn. Kết quả này có thể đổi theo thời gian và thậm chí âm khi tác vụ đã đến hạn nhưng chưa được chạy; không dùng nó làm đồng hồ tuyệt đối.

Nếu tác vụ chỉ cần chạy một lần, hãy dùng **schedule**, không dùng periodic method rồi tự thiết kế biến đếm để hủy sau lần đầu trừ khi có lý do đặc biệt.

## 20. scheduleAtFixedRate: cố duy trì nhịp bắt đầu

Cú pháp:

~~~java
ScheduledFuture<?> periodic = scheduler.scheduleAtFixedRate(
    () -> pollStatus(),
    0,
    5,
    TimeUnit.SECONDS
);
~~~

Ở đây **pollStatus()** là phương thức minh họa. Các mốc đủ điều kiện chạy được định nghĩa gần như:

~~~text
lần 1: initialDelay
lần 2: initialDelay + period
lần 3: initialDelay + 2 * period
lần 4: initialDelay + 3 * period
...
~~~

Nếu task chạy lâu hơn period, lần sau có thể bắt đầu muộn. **Các lần thực thi của cùng một tác vụ định kỳ không chồng lên nhau**, dù executor có nhiều worker; nhưng các task định kỳ *khác nhau* có thể chạy đồng thời.

Ví dụ period 5 giây mà một lần xử lý kéo dài 8 giây: lịch bắt đầu lần tiếp theo bị trễ, không có bảo đảm rằng số lần chạy bám đúng tần suất lý tưởng. Phương thức này phù hợp khi mục tiêu là **duy trì nhịp kiểm tra** và thời gian chạy thông thường nhỏ so với period.

**Không đồng nhất fixed rate với exactly-once scheduling**. Nó không tự lưu trạng thái lịch bền vững; tiến trình dừng/restart có thể làm mất các lần chạy, và việc gọi hàm trong task có thể thất bại.

## 21. scheduleWithFixedDelay: đợi sau khi lần trước kết thúc

Cú pháp:

~~~java
ScheduledFuture<?> periodic = scheduler.scheduleWithFixedDelay(
    () -> refreshCache(),
    0,
    5,
    TimeUnit.SECONDS
);
~~~

Ở đây **refreshCache()** là phương thức minh họa. Phương thức này tính khoảng trì hoãn giữa:

**Thời điểm kết thúc một lần chạy → thời điểm đủ điều kiện bắt đầu lần tiếp theo.**

~~~text
Task bắt đầu ── chạy 8 giây ── kết thúc
                               └── đợi 5 giây ── task tiếp theo
~~~

Khác với fixed-rate, fixed-delay không cố bám các mốc **initialDelay + n × period**. Nó phù hợp với việc cần **thời gian nghỉ sau mỗi lần chạy**, như quét hàng đợi hoặc đồng bộ cache để tránh hai lần xử lý quá sát nhau.

Tương tự fixed-rate, các lần chạy của **cùng một periodic task** không chồng lên nhau. Những tác vụ khác vẫn có thể chạy trên thread khác nếu executor có tài nguyên.

| Thuộc tính | Fixed rate | Fixed delay |
|---|---|---|
| Mốc tính lần tiếp theo | Từ lịch bắt đầu lý tưởng | Từ lúc lần trước kết thúc |
| Task chạy chậm | Có thể gây lần sau bắt đầu muộn, sát lần trước | Luôn có khoảng đợi sau khi hoàn tất |
| Các lần chạy cùng task chồng lên nhau | Không | Không |
| Phù hợp | Kiểm tra theo nhịp cố định | Polling/cập nhật cần khoảng nghỉ |

## 22. Ngoại lệ trong periodic task có thể dừng cả lịch

Một điểm đặc biệt quan trọng: nếu Runnable được lập lịch bằng **scheduleAtFixedRate** hoặc **scheduleWithFixedDelay** ném exception không được xử lý, **các lần thực thi tiếp theo của cùng periodic task bị ngừng**.

~~~java
ScheduledFuture<?> periodic = scheduler.scheduleAtFixedRate(
    () -> {
        throw new IllegalStateException("polling failed");
    },
    0, 1, TimeUnit.SECONDS
);
~~~

Sau lần đầu thất bại, **periodic.isDone()** trở thành true và **periodic.get()** ném **ExecutionException** chứa lỗi gốc. **Future.get() của một periodic task bình thường không bao giờ trả về thành công**, vì đó là tác vụ không được xác định điểm kết thúc; nó chỉ chấm dứt do hủy, executor dừng hoặc lỗi.

Nếu yêu cầu hệ thống là tiếp tục chạy sau **lỗi dự kiến có thể phục hồi**, hãy xử lý chúng bên trong task và ghi nhận tín hiệu vận hành:

~~~java
Runnable resilientPolling = () -> {
    try {
        pollOnce();
    } catch (TemporaryDependencyException expected) {
        recordFailure(expected);
    }
};
~~~

Trong ví dụ, **pollOnce**, **recordFailure** và **TemporaryDependencyException** là thành phần giả định của ứng dụng. Chỉ nên catch những lỗi đã có chính sách phục hồi; không dùng **catch (Throwable)** để nuốt cả lỗi nghiêm trọng hoặc tiếp tục chạy trên trạng thái hỏng.

Khi lỗi không thể phục hồi, dừng tác vụ và báo động thường đúng hơn là lặp vô hạn mà không có observability.

## 23. Hủy lịch và chính sách shutdown của scheduler

Một periodic task thường phải được hủy chủ động:

~~~java
ScheduledFuture<?> handle = scheduler.scheduleAtFixedRate(
    () -> System.out.println("heartbeat"),
    0, 1, TimeUnit.SECONDS
);

// Sau khi đạt điều kiện dừng:
handle.cancel(false);
~~~

Với phương thức **cancel(false)**, lần chạy đang thực hiện có thể tiếp tục tới khi kết thúc; các lần được lên lịch sau đó sẽ bị ngừng theo hợp đồng Future. Với **cancel(true)**, executor cố interrupt một lần chạy đang hoạt động.

**Quan trọng khi đóng scheduler:**

- Với ScheduledThreadPoolExecutor, các periodic tasks **không tiếp tục lặp sau shutdown theo chính sách mặc định**.
- Các tác vụ one-shot đã được trì hoãn nhưng chưa đến hạn **có thể vẫn được thực hiện sau shutdown** theo chính sách mặc định.
- **close()** đợi executor chấm dứt; nếu còn delayed task rất xa trong tương lai và chính sách cho phép nó chạy, close có thể chờ lâu.

Nếu bạn sở hữu ScheduledThreadPoolExecutor và cần thay chính sách, có thể cấu hình:

~~~java
import java.util.concurrent.ScheduledThreadPoolExecutor;

ScheduledThreadPoolExecutor timer =
    new ScheduledThreadPoolExecutor(2);

timer.setExecuteExistingDelayedTasksAfterShutdownPolicy(false);
timer.setContinueExistingPeriodicTasksAfterShutdownPolicy(false);
timer.setRemoveOnCancelPolicy(true);
~~~

- **setExecuteExistingDelayedTasksAfterShutdownPolicy(false)**: không tiếp tục những one-shot delayed tasks chưa đến hạn sau shutdown.
- **setContinueExistingPeriodicTasksAfterShutdownPolicy(false)**: không tiếp tục periodic tasks sau shutdown.
- **setRemoveOnCancelPolicy(true)**: xóa các tác vụ đã hủy khỏi delayed queue sớm hơn, giúp hạn chế giữ tham chiếu khi hủy số lượng lớn lịch xa tương lai.

Chỉ cấu hình những chính sách bạn thật sự cần; các giá trị mặc định và tác động phải được xem trong tài liệu của implementation tương ứng.

## 24. Không dùng fixed-rate 24 giờ cho lịch 09:00 mỗi ngày

Một nhiệm vụ “gửi báo cáo lúc 09:00 hằng ngày theo múi giờ của người dùng” **không đồng nhất** với “chạy mỗi 24 giờ”, đặc biệt khi có thay đổi DST.

**ScheduledExecutorService** nhận delay tương đối. Để lập lịch theo thời gian dân sự:

1. Xác định **ZoneId**, **LocalTime**, quy tắc ngày được phép chạy và chính sách DST.
2. Tính lần chạy **ZonedDateTime** kế tiếp theo quy tắc lịch.
3. Đổi thành **Instant** rồi tính delay từ đồng hồ hiện tại.
4. Gọi **schedule** cho đúng một lần chạy.
5. Sau khi xử lý, tính lại lần chạy tiếp theo từ quy tắc lịch (không cộng 24 giờ vào Instant cũ).
6. Xử lý restart và missed executions theo yêu cầu nghiệp vụ.

Ví dụ xác định ngày/giờ kế tiếp ở một vùng:

~~~java
import java.time.*;

static ZonedDateTime nextDailyRun(
        Clock clock, ZoneId zone, LocalTime localTime) {

    ZonedDateTime now = ZonedDateTime.now(clock.withZone(zone));
    ZonedDateTime candidate = now.toLocalDate()
        .atTime(localTime)
        .atZone(zone);

    if (!candidate.toInstant().isAfter(now.toInstant())) {
        candidate = now.toLocalDate().plusDays(1)
            .atTime(localTime)
            .atZone(zone);
    }

    return candidate;
}
~~~

Khi có giá trị **candidate**, có thể lấy delay:

~~~java
Instant current = Instant.now(clock);
Duration delay = Duration.between(current, candidate.toInstant());

long delayMillis = Math.max(0, delay.toMillis());

ScheduledFuture<?> alarm = scheduler.schedule(
    () -> runDailyJob(),
    delayMillis,
    TimeUnit.MILLISECONDS
);
~~~

Đây là khung minh họa; **runDailyJob()** là hàm nghiệp vụ. Với hệ thống thực tế, phải định nghĩa **gap/overlap DST**, cách xử lý độ phân giải làm tròn, lịch bỏ lỡ, thay đổi múi giờ và chênh lệch đồng hồ. Nếu lịch yêu cầu bảo đảm bền vững qua restart, chỉ một in-memory scheduler là chưa đủ: cần lưu lịch và trạng thái thực thi hoặc dùng hệ thống job scheduler phù hợp.

## 25. Virtual threads và ExecutorService trong Java 27

**Executors.newVirtualThreadPerTaskExecutor()** là API chính thức từ Java 21. Nó tạo một virtual thread riêng cho mỗi tác vụ được gửi, không phải một pool platform threads cố định.

~~~java
import java.util.concurrent.*;

try (ExecutorService tasks =
         Executors.newVirtualThreadPerTaskExecutor()) {

    Future<String> result = tasks.submit(() -> {
        // Minh họa: tác vụ chờ I/O có thể sử dụng virtual thread.
        return "done";
    });

    System.out.println(result.get()); // done
}
~~~

Virtual threads đặc biệt hữu ích khi có nhiều tác vụ **chờ I/O**. Không nên hiểu rằng chúng làm tác vụ **CPU-bound** nhanh hơn theo cùng một tỷ lệ hoặc loại bỏ nhu cầu giới hạn kết nối DB/API. Tài nguyên hữu hạn nằm ở database connections, network, memory và downstream rate limits vẫn cần được bảo vệ.

**Không có một API chuẩn tương đương “newScheduledVirtualThreadPerTaskExecutor” trong các factory thông dụng.** Có thể dùng một ScheduledExecutorService để kích hoạt việc theo lịch, sau đó chuyển tác vụ I/O sang virtual-thread executor có vòng đời riêng nếu thật sự cần. Khi làm vậy, phải thiết kế kỹ việc hủy, ngắt và đóng cả hai executor.

Không sử dụng preview structured-concurrency API chỉ để giải bài toán ExecutorService/Future cơ bản khi các API ổn định ở đây đã đáp ứng yêu cầu.

## 26. Future khác CompletableFuture ở điểm nào?

**Future** là một tay nắm đơn giản để kiểm tra/hủy/chờ một công việc. Nó không cung cấp chuỗi callback biến đổi kết quả theo kiểu pipeline làm mục tiêu chính.

**CompletableFuture** bổ sung các phương thức như **thenApply**, **thenCompose**, **thenCombine**, **exceptionally** và **handle**:

~~~java
import java.util.concurrent.CompletableFuture;

CompletableFuture<Integer> answer =
    CompletableFuture.supplyAsync(() -> 21)
        .thenApply(value -> value * 2);

System.out.println(answer.join()); // 42
~~~

Cần phân biệt:

- **ExecutorService + Future**: dễ hiểu khi muốn chủ động quản lý worker, submit nhiều Callable và chờ kết quả.
- **CompletableFuture**: thuận tiện khi muốn kết hợp các bước bất đồng bộ hoặc đăng ký hành động khi kết quả đến.
- **ScheduledExecutorService**: phù hợp khi cần thời điểm trì hoãn hoặc thực thi định kỳ.

CompletableFuture không tự thay thế scheduler và không tự bảo đảm tác vụ chạy trong thread pool có giới hạn. Với **supplyAsync** không truyền Executor, phải hiểu rõ executor mặc định được sử dụng và tác động đến tải chung.

## 27. Ví dụ hoàn chỉnh: executor, Future và scheduler

Ví dụ độc lập **ExecutorAndSchedulerDemo.java** kết hợp Callable, kết quả có timeout, one-shot schedule và periodic task với hủy rõ ràng.

~~~java
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;

public class ExecutorAndSchedulerDemo {
    static int square(int number) {
        return number * number;
    }

    public static void main(String[] args) throws Exception {
        try (ExecutorService workers = Executors.newFixedThreadPool(2);
             ScheduledExecutorService timer =
                 Executors.newScheduledThreadPool(1)) {

            Future<Integer> first = workers.submit(() -> square(7));
            Future<Integer> second = workers.submit(() -> square(11));

            System.out.println("Results: "
                + first.get(2, TimeUnit.SECONDS)
                + ", "
                + second.get(2, TimeUnit.SECONDS));

            ScheduledFuture<String> once = timer.schedule(
                () -> "ready",
                100,
                TimeUnit.MILLISECONDS
            );

            System.out.println("One-shot: "
                + once.get(2, TimeUnit.SECONDS));

            CountDownLatch observedThree = new CountDownLatch(3);
            AtomicInteger counter = new AtomicInteger();

            ScheduledFuture<?> periodic = timer.scheduleWithFixedDelay(
                () -> {
                    int n = counter.incrementAndGet();
                    System.out.println("Tick " + n);
                    observedThree.countDown();
                },
                0, 75, TimeUnit.MILLISECONDS
            );

            try {
                boolean completed = observedThree.await(
                    3, TimeUnit.SECONDS
                );
                System.out.println("Observed three ticks: " + completed);

            } finally {
                // Hủy lịch định kỳ để close() không phải chờ vô hạn.
                periodic.cancel(false);
            }
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 ExecutorAndSchedulerDemo.java
java ExecutorAndSchedulerDemo
~~~

Đầu ra điển hình:

~~~text
Results: 49, 121
One-shot: ready
Tick 1
Tick 2
Tick 3
Observed three ticks: true
~~~

**Thứ tự và thời điểm thực tế của log có thể thay đổi.** Không viết unit test phụ thuộc vào việc các thread in ra theo trình tự chính xác nếu hợp đồng không yêu cầu thứ tự đó. Trên máy quá tải, một thao tác có timeout cũng có thể thất bại; khi đó chương trình minh họa sẽ ném exception theo **throws Exception** của main.

**Vì sao demo có thể kết thúc?** Future.get chờ các Callable hoàn thành; one-shot scheduled task có kết quả; CountDownLatch chờ đủ ba lần chạy; khối finally **cancel(false)** dừng các lần chạy periodic tiếp theo; try-with-resources đóng executor và scheduler.

## 28. Các lỗi phổ biến và cách phòng tránh

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Request xử lý chậm dù đã submit task | Caller gọi **get()** ngay và chờ | Chỉ block khi cần, dùng timeout hoặc mô hình khác |
| Future.isDone() true nhưng không có kết quả | Task lỗi hoặc bị cancel | Kiểm tra trạng thái; xử lý ExecutionException/CancellationException |
| **get(timeout)** hết hạn nhưng task vẫn chạy | Timeout chỉ giới hạn thời gian chờ | Xem xét cancel(true), timeout của I/O và hủy hợp tác |
| **cancel(true)** không dừng công việc | Task không phản ứng với interrupt | Thiết kế interruption, resource timeout, idempotency |
| Executor không tắt sau khi main xong | Pool còn hoạt động hoặc task không kết thúc | close/shutdown và lifecycle rõ ràng |
| close() chờ rất lâu | Task kẹt hoặc delayed task còn lâu mới chạy | Giới hạn task và chính sách shutdown scheduler |
| Fixed pool bị tăng RAM | Hàng đợi không giới hạn, producer nhanh hơn consumer | Bounded queue, backpressure, rejection |
| Cached pool tạo nhiều thread | Không có giới hạn hợp lý từ workload | Kiểm soát tải, chọn pool/virtual threads phù hợp |
| Nested Future.get bị treo trong single-thread pool | Task cha chờ task con cùng pool | Đổi cấu trúc phụ thuộc hoặc executor |
| Periodic task tự nhiên ngừng chạy | Một lần chạy ném exception | Quan sát ScheduledFuture; xử lý lỗi dự kiến |
| **periodicFuture.get()** không trả về | Tác vụ định kỳ không có kết quả thành công cuối cùng | Không dùng get để đợi “một tick”; dùng latch/metric/event |
| Fixed rate bị trễ khi task chạy chậm | Lần chạy lâu hơn period | Đánh giá fixed-delay, giảm workload, mở rộng năng lực có kiểm soát |
| Báo cáo hằng ngày lệch 1 giờ khi DST | Sử dụng fixed-rate 24 giờ | Tính lại giờ địa phương theo ZoneId |
| Shutdown không nhận task mới | Executor đã shutdown | Quản lý lifecycle và xử lý RejectedExecutionException |
| Dữ liệu bị mất khi nhiều task tăng counter | Trạng thái dùng chung không có đồng bộ | AtomicInteger, lock hoặc concurrent collections |
| Lỗi task không xuất hiện trong log | Future từ submit không được quan sát | Lưu và xử lý Future, có chính sách logging |
| Tưởng virtual threads là vô hạn tài nguyên | I/O/downstream vẫn có giới hạn | Semaphore/rate limit/connection pool |
| Tác vụ bị hủy nhưng side effect vẫn xảy ra | Hủy không rollback tác vụ đã chạy | Idempotency và transaction phù hợp |

## 29. Bài tập thực hành

**Bài tập 1 — Callable và Future:** Dùng fixed thread pool ba worker để tính bình phương các số 1 đến 10. Thu Future theo thứ tự và in kết quả; giải thích thứ tự kết quả có thể khác thứ tự hoàn tất task.

**Bài tập 2 — Timeout và interruption:** Tạo một Callable ngủ khoảng một giây và gọi get với timeout 100 ms. Bắt TimeoutException, gọi cancel(true), rồi cho task phản ứng đúng với InterruptedException. Không dựa vào kiểm tra isDone để suy ra mọi side effect chắc chắn đã dừng.

**Bài tập 3 — invokeAll/invokeAny:** Mô phỏng ba nguồn cung cấp dữ liệu có thời gian phản hồi khác nhau. So sánh invokeAll và invokeAny về thời điểm trả kết quả, thứ tự và cách hủy các tác vụ còn lại. Thêm trường hợp một nguồn lỗi.

**Bài tập 4 — Hai kiểu lịch định kỳ:** Với một Runnable xử lý trong 250 ms và khoảng lập lịch 100 ms, quan sát fixed-rate và fixed-delay. Dùng System.nanoTime để đo **khoảng cách các lần bắt đầu**, không suy ra deadline từ log thời gian tường.

**Bài tập 5 — Periodic exception:** Lập lịch một Runnable ném RuntimeException ở lần thứ ba. Quan sát **isDone**, **get** và việc những lần chạy sau bị ngừng. Đề xuất chính sách retry hoặc cách chuyển sang dừng và cảnh báo.

**Bài tập 6 — Bounded pool:** Dùng ThreadPoolExecutor với hai worker, hàng đợi nhỏ và AbortPolicy. Gửi nhiều task chậm rồi kiểm tra RejectedExecutionException. Xác định cách caller trả lời khi quá tải thay vì retry vô hạn.

**Bài tập 7 — Daily schedule:** Thiết kế lần chạy kế tiếp lúc 09:00 theo America/New_York cho ngày trước và sau DST. Trình bày cách tính delay từ Instant hiện tại và cách lên lịch lại sau mỗi lần hoàn tất.

**Bài tập 8 — Vòng đời:** Viết một service sở hữu ExecutorService, có phương thức start/stop. Khi stop, ngừng nhận task, cho task cũ một thời hạn hoàn tất, sau đó yêu cầu hủy và ghi metric. Kiểm thử riêng trường hợp thread chờ bị interrupt.

## 30. Checklist khi dùng ExecutorService trong Java 27

- [ ] Chọn **Runnable** khi không cần giá trị trả về, **Callable** khi cần result/checked exception.
- [ ] Biết rõ khác biệt giữa **execute** và **submit**.
- [ ] Không coi **submit** là bằng chứng tác vụ đã hoàn thành.
- [ ] Dùng **get(timeout, unit)** hoặc ngân sách chờ có ý nghĩa thay vì chờ vô hạn khi cần deadline.
- [ ] Phân biệt **ExecutionException**, **TimeoutException**, **InterruptedException** và **CancellationException**.
- [ ] Không nuốt interrupt; khôi phục interrupted status khi không truyền checked exception lên caller.
- [ ] Hiểu rằng **cancel(true)** chỉ cố gắng interrupt, không rollback side effect.
- [ ] Đảm bảo shared mutable state có cơ chế đồng bộ phù hợp.
- [ ] Tách vòng đời của executor khỏi vòng đời từng request khi cần.
- [ ] Dùng try-with-resources hoặc shutdown/awaitTermination với owner rõ ràng.
- [ ] Không coi **shutdownNow** là bảo đảm cưỡng bức chấm dứt mọi task.
- [ ] Giới hạn backlog hoặc có backpressure/rejection policy khi tải có thể tăng mạnh.
- [ ] Tránh deadlock khi một task chờ task con chạy trong cùng pool nhỏ.
- [ ] Chọn **schedule** cho one-shot, **fixed-rate** cho nhịp, **fixed-delay** cho khoảng nghỉ sau xử lý.
- [ ] Không gọi **get()** trên periodic future để đợi một lần chạy bình thường.
- [ ] Quan sát lỗi định kỳ; một lần ném exception có thể dừng cả lịch.
- [ ] Hủy periodic tasks và hiểu chính sách delayed tasks khi shutdown scheduler.
- [ ] Không dùng chu kỳ 24 giờ thay cho lịch 09:00 hằng ngày nếu có ZoneId/DST.
- [ ] Dùng virtual threads khi mô hình nhiều I/O-waiting tasks phù hợp, nhưng vẫn giới hạn tài nguyên ngoài.
- [ ] Viết test cho shutdown, cancel, timeout, rejection, interruption và lỗi định kỳ.

**Kết luận:** ExecutorService giúp tách hành vi “cần làm gì” khỏi quyết định “chạy ở thread nào và quản lý nó ra sao”. Future cung cấp kênh quan sát, chờ và yêu cầu hủy một công việc. ScheduledExecutorService bổ sung trì hoãn và thực thi định kỳ, nhưng không tự bảo đảm tính bền vững, chính xác theo lịch dân sự hoặc dừng task đã có side effect. Trong Java 27, cách dùng đáng tin cậy là định nghĩa rõ **vòng đời**, **giới hạn tài nguyên**, **hợp đồng lỗi**, **cơ chế hủy** và **ngữ nghĩa của lịch chạy**.

## Tài liệu tham khảo

- [Java SE 27 — ExecutorService](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/ExecutorService.html): submit, invokeAll/invokeAny, shutdown, close và happens-before.
- [Java SE 27 — Future](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/Future.html): get, cancel, isDone, isCancelled, state, resultNow.
- [Java SE 27 — ScheduledExecutorService](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/ScheduledExecutorService.html): schedule, scheduleAtFixedRate, scheduleWithFixedDelay.
- [Java SE 27 — ScheduledThreadPoolExecutor](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/ScheduledThreadPoolExecutor.html): hủy lịch và chính sách shutdown.
- [Java SE 27 — Executors](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/Executors.html): factory methods, fixed pools và virtual-thread-per-task executor.
- [Java SE 27 — ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html): queue, thread count và rejection policies.
- [Java SE 27 — TimeUnit](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/TimeUnit.html): đơn vị thời gian cho timeout/scheduling.
- [JEP 444 — Virtual Threads](https://openjdk.org/jeps/444): virtual threads là tính năng chính thức từ Java 21.
