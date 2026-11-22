# RejectedExecutionHandler và bốn chính sách từ chối trong Java

## 1. Vì sao ThreadPoolExecutor phải từ chối công việc?

`ThreadPoolExecutor` quản lý số luồng làm việc và hàng đợi `BlockingQueue<Runnable>`. Khi lượng công việc đến nhanh hơn khả năng xử lý, executor phải quyết định điều gì xảy ra với một tác vụ mới thay vì nhận vô hạn và khiến bộ nhớ, độ trễ hoặc tài nguyên tăng mất kiểm soát.

`RejectedExecutionHandler` là giao diện định nghĩa hành động **khi một tác vụ không được `ThreadPoolExecutor` chấp nhận**. Đây là cơ chế của **Java Concurrency trong `java.util.concurrent`**, áp dụng độc lập với bất kỳ framework nào.

Có hai trường hợp chính kích hoạt từ chối:

1. **Quá tải (saturation):** số worker đã đạt `maximumPoolSize` và hàng đợi không thể nhận thêm tác vụ. Một cấu hình dùng hàng đợi có dung lượng giới hạn giúp sự kiện này xảy ra rõ ràng.
2. **Executor đang đóng/đã đóng:** sau `shutdown()` hoặc `shutdownNow()`, tác vụ mới không còn được nhận, ngay cả khi hàng đợi vẫn còn chỗ. Những thay đổi trạng thái đồng thời với thao tác nhận việc cũng có thể khiến tác vụ vừa đưa vào hàng đợi bị gỡ ra rồi chuyển sang handler.

Ví dụ: `corePoolSize = 1`, `maximumPoolSize = 1`, hàng đợi chứa tối đa 1 tác vụ. Khi A đang chạy, B đang đợi và C được gửi tới, C sẽ bị từ chối; **chính sách từ chối** quyết định số phận C. Ngược lại, nếu executor đã đóng, chính sách cũng được gọi khi gửi C, không phụ thuộc độ đầy của hàng đợi.

> “Rejected” không đồng nghĩa “task đã chạy và thất bại”. Nó có nghĩa executor **không chấp nhận giao tác vụ đó để thực hiện** theo cơ chế thông thường. Một handler có thể ném lỗi, thực thi bằng luồng gọi, bỏ tác vụ hoặc tự định tuyến lại.

## 2. Thứ tự nhận việc và điểm kích hoạt handler

Đơn giản hóa luồng `execute(command)` của `ThreadPoolExecutor`:

1. Nếu số worker đang tồn tại thấp hơn `corePoolSize`, cố tạo worker mới để xử lý `command`.
2. Nếu không tạo worker ở bước 1 và executor còn ở trạng thái nhận việc, thử đưa `command` vào `workQueue`.
3. Sau khi xếp hàng thành công, **kiểm tra lại trạng thái executor** để xử lý cuộc đua với `shutdown`; nếu đã đóng và gỡ tác vụ khỏi queue thành công, tác vụ bị từ chối. Executor cũng bảo đảm có worker khi cần.
4. Nếu queue không nhận `command`, thử tạo thêm worker đến `maximumPoolSize`.
5. Nếu vẫn không được (đã đóng, hoặc đã đạt giới hạn worker và queue), gọi `RejectedExecutionHandler.rejectedExecution(command, executor)`.

Đây là trình tự khái niệm để hiểu các ngưỡng, không phải cam kết rằng mọi phép kiểm tra trong triển khai nội bộ đều là một thao tác nguyên tử.

`RejectedExecutionHandler` là một functional interface:

```java
@FunctionalInterface
public interface RejectedExecutionHandler {
    void rejectedExecution(Runnable r, ThreadPoolExecutor executor);
}
```

- `r` là tác vụ đang bị từ chối; nếu lời gọi ban đầu là `submit(...)`, nó thường là một `RunnableFuture` do `submit` tạo ra.
- `executor` là pool liên quan, cho phép xem trạng thái, hàng đợi và các chỉ số.
- Handler có thể ném `RejectedExecutionException`. Nếu handler tự trả về bình thường, `execute` có thể trả về bình thường **dù công việc đã bị bỏ**. Không được coi việc “không thấy ngoại lệ” là bằng chứng tác vụ đã hoàn thành.
- Mặc định, `ThreadPoolExecutor` sử dụng `AbortPolicy`. Có thể truyền handler vào constructor hoặc thay bằng `setRejectedExecutionHandler(...)` khi cần; cấu hình trước khi nhận tải là dễ kiểm soát nhất.

### Vai trò của loại queue

| Queue | Hệ quả thực tế với ngưỡng từ chối |
| --- | --- |
| `ArrayBlockingQueue<>(N)` | Queue có dung lượng N; khi đầy và không thể thêm worker, handler có cơ hội được gọi. |
| `LinkedBlockingQueue<>(N)` | Hàng đợi có giới hạn N; hành vi quá tải tương tự nhưng chi phí cấu trúc dữ liệu khác. |
| `LinkedBlockingQueue<>()` | Gần như không bị chặn bởi ngưỡng nhỏ do ứng dụng đặt; sau khi đạt core worker, việc thường đi vào queue và `maximumPoolSize` ít có tác dụng mở rộng khi queue vẫn nhận được. Độ trễ/bộ nhớ có thể tăng trước khi có từ chối. |
| `SynchronousQueue<>` | Không chứa phần tử chờ: một tác vụ cần được chuyển giao trực tiếp cho worker. Khi không thể chuyển giao hoặc tạo worker mới, có thể bị từ chối; `DiscardOldestPolicy` đặc biệt không phù hợp vì không có phần tử nào để `poll()`. |

`corePoolSize` là ngưỡng ưu tiên tạo worker ban đầu, không có nghĩa executor luôn duy trì bấy nhiêu luồng; pool có thể khởi tạo worker khi nhận việc. `maximumPoolSize` là giới hạn worker, không phải tổng số tác vụ đang chạy cộng số tác vụ trong queue.

## 3. So sánh bốn chính sách tích hợp

Tất cả đều là lớp lồng trong `ThreadPoolExecutor`, triển khai `RejectedExecutionHandler`.

| Chính sách | Khi pool còn hoạt động nhưng quá tải | Khi pool đã shutdown | Đánh đổi chính |
| --- | --- | --- | --- |
| `AbortPolicy` | Ném `RejectedExecutionException` cho luồng gửi việc | Ném `RejectedExecutionException` | Thất bại tường minh; caller phải xử lý. |
| `CallerRunsPolicy` | Chạy tác vụ ngay trên **luồng gọi `execute`**, đồng bộ trước khi lời gọi trả về | Bỏ tác vụ | Tạo backpressure tự nhiên, nhưng chặn caller và thay đổi ngữ cảnh thực thi. |
| `DiscardPolicy` | Im lặng bỏ tác vụ mới | Im lặng bỏ tác vụ | Tác vụ có thể mất mà người gọi không biết. |
| `DiscardOldestPolicy` | Bỏ phần tử ở **đầu hàng đợi chờ**, rồi thử `execute` lại với tác vụ mới | Bỏ tác vụ mới | Mất tác vụ đã xếp hàng; retry có thể lại bị từ chối. |

### 3.1. AbortPolicy: thất bại rõ ràng

```java
RejectedExecutionHandler policy = new ThreadPoolExecutor.AbortPolicy();
```

Handler luôn ném `RejectedExecutionException`, kể cả khi executor đã shutdown. Đây là lựa chọn mặc định và thường là điểm khởi đầu an toàn khi mỗi tác vụ có giá trị: bên gửi có thể ghi log, tăng metric, phát tín hiệu bận, thực hiện retry **có giới hạn** hoặc chuyển tác vụ sang cơ chế bền vững.

Ví dụ xử lý tại ranh giới gửi công việc (đoạn mã minh họa, biến `pool` và `task` được tạo ở nơi khác):

```java
try {
    pool.execute(task);
} catch (RejectedExecutionException rejected) {
    // Ghi nhận và chuyển quyết định cho tầng gọi thích hợp.
    // Không retry vô hạn ngay trên cùng pool đang quá tải.
    System.err.println("Task was not accepted: " + rejected.getMessage());
}
```

**Lỗi phổ biến:** chỉ bắt rồi bỏ qua ngoại lệ, khiến `AbortPolicy` trên thực tế trở thành mất dữ liệu âm thầm; hoặc retry tức thì, không giới hạn, làm tình trạng quá tải trầm trọng hơn.

### 3.2. CallerRunsPolicy: giảm tốc luồng gửi việc

```java
RejectedExecutionHandler policy = new ThreadPoolExecutor.CallerRunsPolicy();
```

Nếu executor chưa đóng, handler gọi `r.run()` trên **chính luồng đang gửi tác vụ**. Ví dụ `main` gửi việc và pool đã bão hòa thì `main` trực tiếp chạy tác vụ được từ chối; sau khi hoàn tất mới trở về từ `execute`. Đây là một dạng backpressure: producer tốn thời gian tự xử lý, vì vậy không thể liên tục bơm thêm việc với tốc độ cũ.

Điểm cần đánh giá kỹ:

- Tác vụ được chạy **đồng bộ**; caller có thể là luồng xử lý giao diện, vòng sự kiện, luồng giữ lock hoặc một worker khác, dẫn đến độ trễ, deadlock hay thiếu tài nguyên nếu chọn sai.
- Không còn bảo đảm tác vụ chạy trên worker được cấu hình (tên luồng, `ThreadLocal`, security context, request context, cách quản lý MDC...). Tác vụ không nên dựa vào identity của thread pool.
- Exception unchecked từ `Runnable.run()` thực thi trực tiếp có thể lan tới caller, khác với lỗi tác vụ chạy trên worker. Với tác vụ được đóng gói bởi `submit`, `FutureTask` lại ghi nhận lỗi bên trong `Future`.
- Khi executor đã shutdown, chính sách này **bỏ tác vụ**, không tự chuyển sang chạy trên caller.

Nên dùng khi producer có thể bị chặn, tác vụ không lệ thuộc worker thread và người thiết kế chấp nhận việc chuyển chi phí thực thi sang caller.

### 3.3. DiscardPolicy: bỏ tác vụ mới không báo lỗi

```java
RejectedExecutionHandler policy = new ThreadPoolExecutor.DiscardPolicy();
```

Handler không ném lỗi và không chạy tác vụ. Nó chỉ phù hợp khi bỏ một số sự kiện là **chủ đích nghiệp vụ**, ví dụ cập nhật trạng thái gần nhất có thể tái tạo, phép lấy mẫu best-effort, hoặc công việc định kỳ mà vòng sau sẽ thay thế vòng trước. Dù vậy, thường vẫn cần đếm số lần bị từ chối để phát hiện mất tải.

Không thích hợp cho giao dịch, ghi dữ liệu, thanh toán, xử lý job phải hoàn tất, thao tác cần hồi đáp, hoặc các tác vụ trả `Future` được hệ khác chờ. Sau `submit`, một `FutureTask` bị bỏ có thể mãi ở trạng thái chưa hoàn thành, khiến `get()` chờ vô hạn nếu không có timeout hoặc hủy riêng.

### 3.4. DiscardOldestPolicy: bỏ tác vụ đang chờ ở đầu queue

```java
RejectedExecutionHandler policy = new ThreadPoolExecutor.DiscardOldestPolicy();
```

Khi pool chưa đóng, handler gọi `executor.getQueue().poll()` để loại phần tử chờ ở đầu hàng đợi và gửi lại tác vụ mới qua `execute`. Nó **không** hủy tác vụ đang chạy. Với queue FIFO, đó thường là công việc được xếp hàng lâu nhất; với queue ưu tiên, `poll()` chọn đầu queue theo thứ tự ưu tiên, **không nhất thiết là tác vụ vào sớm nhất**.

Những hệ quả dễ bị bỏ sót:

- Tác vụ cũ bị loại không nhận ngoại lệ trực tiếp tại luồng đã gửi nó; nếu là `FutureTask`, người đang đợi `Future.get()` có thể bị treo vì Future chưa được hủy.
- Retry **không bảo đảm thành công**: có thể lại bị từ chối do cạnh tranh với producer khác hoặc tình trạng shutdown. Với queue không chứa phần tử như `SynchronousQueue`, `poll()` không tạo được chỗ trống; việc thử lại có thể lặp quá sâu. Không sử dụng chính sách này cho cấu hình đó.
- Thay “việc cũ” bằng “việc mới” chỉ hợp lý nếu dữ liệu cũ thật sự có thể mất. Bỏ phần tử ở đầu `PriorityBlockingQueue` có thể phá hỏng mức ưu tiên mong đợi.
- Khi executor đã shutdown, chính sách bỏ ngay tác vụ mới, không retry.

Tài liệu JDK cũng cảnh báo đây là chính sách hiếm khi phù hợp nếu có bên chờ hoàn thành tác vụ; trường hợp cần “thay thế công việc cũ” thường nên thiết kế hàng đợi gộp/cập nhật trạng thái và cơ chế hủy, thông báo thất bại rõ ràng.

## 4. Ví dụ Java 17+ chạy độc lập: cùng tải, bốn kết quả khác nhau

Chương trình cố định trạng thái **A đang chạy, B đang chờ, C là tác vụ đến lúc đầy tải** bằng `CountDownLatch`, tránh phụ thuộc vào `sleep()` hoặc tốc độ máy. Mỗi chính sách dùng một pool mới, giữ A chưa hoàn tất cho tới khi xử lý C, rồi mới giải phóng.

Lưu thành `RejectionPoliciesDemo.java`:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.RejectedExecutionHandler;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class RejectionPoliciesDemo {
    public static void main(String[] args) throws InterruptedException {
        runCase("AbortPolicy", new ThreadPoolExecutor.AbortPolicy());
        runCase("CallerRunsPolicy", new ThreadPoolExecutor.CallerRunsPolicy());
        runCase("DiscardPolicy", new ThreadPoolExecutor.DiscardPolicy());
        runCase("DiscardOldestPolicy",
                new ThreadPoolExecutor.DiscardOldestPolicy());
    }

    private static void runCase(
            String name, RejectedExecutionHandler policy)
            throws InterruptedException {

        List<String> events =
                Collections.synchronizedList(new ArrayList<>());
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 1, 0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(1),
                policy);

        try {
            pool.execute(() -> {
                events.add("A-start");
                started.countDown();
                try {
                    release.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
                events.add("A-end");
            });

            started.await(); // A đã chiếm worker
            pool.execute(() -> events.add("B")); // B đã vào queue

            try {
                pool.execute(() -> events.add("C")); // C bị từ chối
            } catch (RejectedExecutionException ex) {
                events.add("REJECTED-C");
            }
        } finally {
            release.countDown();
            pool.shutdown();
        }

        if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
            throw new AssertionError("Pool did not terminate: " + name);
        }
        System.out.println(name + " -> " + String.join(", ", events));
    }
}
```

Biên dịch và chạy:

```bash
javac RejectionPoliciesDemo.java
java RejectionPoliciesDemo
```

Kết quả xác định trong ví dụ này:

```text
AbortPolicy -> A-start, REJECTED-C, A-end, B
CallerRunsPolicy -> A-start, C, A-end, B
DiscardPolicy -> A-start, A-end, B
DiscardOldestPolicy -> A-start, A-end, C
```

Giải thích:

- `AbortPolicy`: C bị từ chối bằng exception; A rồi B vẫn thực hiện.
- `CallerRunsPolicy`: C chạy ngay trên thread `main` trước khi A được mở khóa; B tiếp tục đợi worker.
- `DiscardPolicy`: C biến mất; queue vẫn còn B.
- `DiscardOldestPolicy`: phần tử B trong queue bị loại, C thay vào vị trí chờ; sau khi A xong, C chạy.

Ví dụ này cố ý dùng `execute` để thấy trực tiếp cơ chế handler. **Thứ tự log ở các chương trình chạy đồng thời nói chung không tự nhiên cố định**; ở đây latch buộc thứ tự cần kiểm chứng. Trong thực tế không nên dùng latch để cố tạo quá tải; hãy đo thông lượng, độ trễ và tỷ lệ từ chối dưới tải thật.

## 5. `execute` và `submit`: hai cách gọi, một rủi ro lớn

Cả `execute(Runnable)` và `submit(...)` đều có thể đi qua cơ chế từ chối của `ThreadPoolExecutor`, nhưng `submit` đóng gói tác vụ trong `RunnableFuture` và trả về `Future` khi lời gọi trở về bình thường.

| Tình huống | Với `execute` | Với `submit` |
| --- | --- | --- |
| `AbortPolicy` từ chối | Exception được ném tại lệnh gửi | Exception cũng được ném trong thao tác gửi; không có Future được trả về thành công |
| `CallerRunsPolicy` khi chưa shutdown | Runnable chạy trong caller | `FutureTask` chạy trong caller, Future sau đó đã hoàn tất; vẫn có thể tốn nhiều thời gian |
| `DiscardPolicy` | Trả về bình thường dù tác vụ không chạy | Có thể trả về Future **không bao giờ completed** |
| `DiscardOldestPolicy` | Tác vụ mới có thể được nhận, tác vụ chờ bị thay thế | Future ứng với tác vụ bị loại khỏi queue có thể không bao giờ completed |

Các lời gọi `get(timeout, unit)` giúp tránh chờ vô hạn tại phía consumer, **nhưng không tự sửa sự mất tác vụ**. `isDone()` không chuyển sang `true` chỉ vì executor đã bỏ phần tử `FutureTask` khỏi hàng đợi. Nếu ứng dụng thực sự cho phép loại tác vụ, cần thiết kế cách `cancel(false)` Future đã bị bỏ và phát tín hiệu/metric cho nơi quan sát, hoặc chọn chính sách thể hiện thất bại tường minh.

Mẫu dễ gây lỗi: dùng `Executors.newFixedThreadPool(n)`, tưởng rằng luôn phát sinh rejection khi quá tải. Factory này sử dụng queue không giới hạn nhỏ theo cấu hình ứng dụng, nên queue có thể tăng rất lớn thay vì sớm kích hoạt handler. Nếu cần giới hạn mức chờ và kiểm soát từ chối, tạo `ThreadPoolExecutor` với queue có giới hạn phù hợp.

## 6. Tùy biến RejectedExecutionHandler một cách có trách nhiệm

Một handler tùy chỉnh hữu ích khi ứng dụng cần **đo được** tác vụ bị từ chối và đưa ra quyết định nhất quán. Mẫu “đếm rồi ném lỗi” giữ được hợp đồng thất bại tường minh:

```java
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.RejectedExecutionHandler;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.atomic.AtomicLong;

// Fragment minh họa; có thể đặt trong method cấu hình pool.
AtomicLong rejectedCount = new AtomicLong();
RejectedExecutionHandler handler = (task, executor) -> {
    rejectedCount.incrementAndGet();
    throw new RejectedExecutionException(
            "Executor rejected task; shutdown=" + executor.isShutdown());
};
```

Truyền `handler` vào constructor `ThreadPoolExecutor` như ví dụ trước. `AtomicLong` giúp thống kê số lần từ chối đồng thời, nhưng bộ đếm là **số lần gọi handler**, không nhất thiết bằng số công việc cuối cùng đã thất lạc nếu handler retry hoặc chuyển giao thành công. Dữ liệu theo thời gian nên có trong monitoring, cùng với tải đang chạy, độ sâu queue và thời gian chờ.

Khi viết một chính sách phức tạp hơn, cần đặt ra:

1. Tác vụ nào được phép bỏ? Có cần đảm bảo thứ tự, at-most-once, khả năng retry hoặc giao nhận bền vững?
2. Producer có thể bị chặn trong bao lâu? Có timeout, khả năng interrupt và đường thoát khi shutdown không?
3. Nếu phải loại `FutureTask` đang nằm trong queue, ai sẽ hủy Future và thông báo thất bại cho người đợi?
4. Handler có thể được gọi đồng thời từ nhiều luồng. Mọi cập nhật trạng thái phải thread-safe; không giữ khóa hoặc callback có nguy cơ gây deadlock.
5. Cần báo rõ trạng thái “không chấp nhận” cho tầng gửi việc; không giả vờ chấp nhận thành công nếu không thể bảo đảm xử lý.
6. Không gọi `execute` đệ quy mù quáng trên cùng pool đang đầy và không block vô hạn trong chính handler. Nếu có fallback queue, phải đặt capacity và chính sách shutdown riêng.

Một số hệ thống sẽ phù hợp hơn với admission control trước pool (ví dụ giới hạn số tác vụ đang lưu hành bằng `Semaphore`), đẩy sự kiện sang hàng đợi có độ bền, hoặc trả tín hiệu “busy” cho producer. Rejected handler chỉ là **điểm cuối** sau khi `ThreadPoolExecutor` đã từ chối, không thay thế thiết kế giới hạn tải toàn hệ thống.

## 7. Chọn chính sách theo đặc điểm tác vụ

| Yêu cầu | Lựa chọn khởi đầu | Cần kiểm tra trước khi đưa vào thực tế |
| --- | --- | --- |
| Không được mất tác vụ mà không biết | `AbortPolicy` | Bắt và xử lý rejection; retry có giới hạn hoặc lưu bền vững khi cần |
| Producer chấp nhận chạy chậm để giảm tải; công việc có thể chạy trên caller | `CallerRunsPolicy` | Không gọi từ event loop/luồng cần phản hồi nhanh hoặc đang giữ lock; shutdown vẫn làm rơi tác vụ |
| Sự kiện best-effort có thể bỏ và không ai chờ Future | `DiscardPolicy` | Mất tác vụ đúng với yêu cầu sản phẩm; theo dõi lượng bỏ |
| Dữ liệu cũ có thể bị thay thế bởi dữ liệu mới hơn | Cân nhắc thiết kế queue coalescing; chỉ cân nhắc `DiscardOldestPolicy` nếu hiểu rõ rủi ro | Queue FIFO, xử lý Future bị bỏ, tránh `SynchronousQueue` và retry không giới hạn |

**Không có “policy tốt nhất” cho mọi ứng dụng.** Điều quan trọng là tính chất của tác vụ, quy ước báo lỗi và khả năng chịu tải của producer/consumer. Với tác vụ bắt buộc hoàn tất, `AbortPolicy` cộng cơ chế tiếp nhận lại/ghi bền vững thường rõ ràng hơn một handler bỏ âm thầm.

### Checklist cấu hình và vận hành

- Chọn `corePoolSize` và `maximumPoolSize` dựa trên tác vụ CPU-bound hay I/O-bound, tài nguyên thực và benchmark; không đặt số luồng thật lớn chỉ để né rejection.
- Dùng queue **có capacity hữu hạn** nếu mục tiêu là giới hạn lượng việc đang chờ, chấp nhận trade-off giữa khả năng hấp thụ đột biến và độ trễ.
- Theo dõi ít nhất rejection count/rate, `getActiveCount()`, `getPoolSize()`, `getQueue().size()`, `getCompletedTaskCount()`, thời gian xử lý và độ trễ queue. Các getter pool/queue là **ảnh chụp gần đúng**, không phải phép kiểm tra capacity nguyên tử để ra quyết định chính xác.
- Phân biệt từ chối do overload và do shutdown bằng trạng thái executor/telemetry; đừng tự gộp hai tình huống thành “thiếu thread”.
- Khi cần shutdown có kiểm soát, dừng gửi việc, gọi `shutdown()`, `awaitTermination(...)` và xác định cách xử lý tác vụ chưa hoàn tất; `shutdownNow()` cố gắng ngắt worker và trả về tác vụ còn trong queue, nhưng không bảo đảm mọi tác vụ dừng ngay.
- Kiểm tra tác động của `submit`/`Future`, exception, timeout, cancellation; viết bài test có điều khiển bằng latch giống ví dụ thay vì trông chờ timing ngẫu nhiên.
- Thử tải tăng đột biến, caller chậm, queue đầy, nhiều producer cạnh tranh và cuộc đua shutdown. Chứng minh handler được gọi đúng và công việc mất/chuyển giao đúng theo hợp đồng.

## 8. Câu hỏi tự kiểm tra

1. Pool có `corePoolSize=2`, `maximumPoolSize=4`, queue hữu hạn 10 chỗ: khi đã có 2 worker bận và còn chỗ queue, executor sẽ xếp hàng hay tăng lên 3 worker? **Xếp hàng trước** trong trình tự thông thường; chỉ khi queue không nhận được mới thử tăng worker đến maximum.
2. Vì sao `CallerRunsPolicy` có thể giảm tốc producer? **Vì producer trực tiếp trả chi phí chạy task bị từ chối**, lời gọi `execute` bị giữ tới khi hoàn thành; nhưng không bảo đảm cơ chế này khi pool đã shutdown.
3. `DiscardOldestPolicy` có hủy task đang chạy không? **Không**; nó `poll()` từ queue chờ, rồi retry; tác vụ đang chạy không phải phần tử đầu queue.
4. Nếu `submit` bị `DiscardPolicy` bỏ, `Future.get()` có tự phát sinh `RejectedExecutionException` không? **Không**; handler đã im lặng và Future có thể vẫn chờ mãi nếu không bị hủy.
5. Gửi tác vụ vào pool đã `shutdown()` có thể được `CallerRunsPolicy` thực thi trên luồng gửi không? **Không**; policy bỏ tác vụ trong trường hợp executor đã shutdown.

## Tài liệu tham khảo

- Java SE 17 API: [ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)
- Java SE 17 API: [RejectedExecutionHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/RejectedExecutionHandler.html)
- Java SE 17 API: [AbortPolicy](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.AbortPolicy.html), [CallerRunsPolicy](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.CallerRunsPolicy.html), [DiscardPolicy](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.DiscardPolicy.html), [DiscardOldestPolicy](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.DiscardOldestPolicy.html)
