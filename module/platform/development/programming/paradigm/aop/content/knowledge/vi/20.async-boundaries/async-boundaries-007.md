# Hủy tác vụ, thời gian chờ và dọn dẹp tại ranh giới bất đồng bộ trong Aspect (AOP)

## 1. Vấn đề mà Aspect cần giải quyết

Trong lập trình hướng khía cạnh (Aspect-Oriented Programming, AOP), **hủy tác vụ**, **thời gian chờ (timeout)** và **dọn dẹp tài nguyên (cleanup)** là các mối quan tâm cắt ngang: nhiều thao tác nghiệp vụ cần cùng một chính sách nhưng không nên lặp lại mã quản lý thời gian, hủy bỏ và quan sát trạng thái ở từng phương thức.

Điểm khó nằm ở **ranh giới bất đồng bộ**. Một phương thức có thể trả về `Future` hoặc `CompletionStage` gần như ngay lập tức, trong khi công việc thực sự vẫn chạy ở luồng khác. Vì vậy, “phương thức đã trả về” không đồng nghĩa với “tác vụ đã kết thúc”. Một Aspect chỉ bao quanh lời gọi ban đầu có thể bỏ lỡ lỗi, kết quả và tài nguyên được giải phóng sau đó.

Mục tiêu của bài:

- Phân biệt yêu cầu hủy, trạng thái đã hủy, timeout chờ kết quả và việc công việc thực tế đã dừng.
- Xác định Aspect nên gắn chính sách vào **lời gọi**, **đối tượng kết quả bất đồng bộ** và **vòng đời tác vụ** như thế nào.
- Quản lý deadline, truyền tín hiệu hủy và dọn dẹp đúng chủ sở hữu; tránh đóng tài nguyên khi tác vụ còn dùng.
- Nhìn rõ giới hạn của các API Java như `Future` và `CompletableFuture`, kiểm soát race condition và kiểm thử được chính sách.

Bài dùng **AOP tổng quát**, minh họa bằng Java tiêu chuẩn với dynamic proxy/decorator để thể hiện lời khuyên quanh lời gọi (around advice). Các nguyên tắc tương tự áp dụng cho các cơ chế weaving khác nếu cơ chế đó có thể chặn đúng join point.

## 2. Mô hình vòng đời: lời gọi, kết quả, tác vụ

Xét một thao tác `submit()` trả về `Future<Result>`:

~~~text
Luồng gọi                 Aspect                   Worker
    |                       |                        |
    |--- gọi submit() ----->|--- gọi nghiệp vụ ------>|
    |                       |<-- trả Future ----------|
    |<-- nhận Future -------|                        | đang làm việc...
    |                       |                        |
    |--- get()/cancel() ------------------------------|
    |                       |          hoàn tất / lỗi / nhận yêu cầu hủy
    |                       |                        | finally/close
~~~

Có **ba thời điểm** cần tách:

1. **Kết thúc lời gọi đồng bộ**: `submit()` trả về một handle. Advice kiểu “sau khi trả về” tại join point này chỉ quan sát được handle.
2. **Kết thúc logic của handle**: `Future` báo thành công, lỗi hoặc bị hủy; một handle cũng có thể được hoàn tất giả bằng timeout.
3. **Kết thúc thực sự của worker**: không còn dùng tài nguyên; `finally` đã chạy. Đây mới là mốc an toàn để giải phóng những tài nguyên do worker sở hữu.

Các mốc 2 và 3 **không nhất thiết trùng nhau**. Đặc biệt, `cancel(true)` có thể đánh dấu `Future` là cancelled ngay khi worker còn đang xử lý ngắt; `CompletableFuture.orTimeout(...)` có thể hoàn tất đối tượng kết quả trong lúc phép tính nền vẫn tiếp diễn.

Một hợp đồng Aspect hữu ích nên trả lời được: ai sở hữu tác vụ, ai được hủy, deadline bắt đầu từ khi nào, đối tượng nào truyền trạng thái và thành phần nào chịu trách nhiệm cleanup.

## 3. Hủy tác vụ: tín hiệu hợp tác thay vì nút dừng tuyệt đối

### 3.1. Ý nghĩa của các API

| Cơ chế | Nó bảo đảm điều gì? | Điều nó không bảo đảm |
| --- | --- | --- |
| `Future.cancel(false)` | Cố chuyển handle sang trạng thái cancelled; nếu tác vụ chưa chạy, nó có thể bị ngăn không chạy | Không cưỡng bức dừng tác vụ đang chạy |
| `Future.cancel(true)` | Yêu cầu hủy và **có thể interrupt** luồng đang thực hiện với triển khai như `FutureTask` | Không bảo đảm mã nghiệp vụ dừng tức thì; interrupt phải được hợp tác xử lý |
| `Future.isCancelled()` | Trạng thái hủy của handle | Không chứng minh worker đã chạy xong `finally` |
| `Future.get()` sau hủy | Có thể ném `CancellationException` | Không cho biết chắc nguyên nhân là caller hủy hay deadline hết |
| `CompletableFuture.cancel(true)` | Hoàn tất `CompletableFuture` ở trạng thái cancelled | Tham số `mayInterruptIfRunning` **không** làm ngắt phép tính nền theo hợp đồng của `CompletableFuture` |
| `CompletionStage` | Mô tả chuỗi xử lý và kết quả bất đồng bộ | Bản thân interface này không có phương thức `cancel` |

**Interrupt là tín hiệu hợp tác.** Worker nên kiểm tra `Thread.currentThread().isInterrupted()` ở các bước tính toán dài, hoặc phản ứng với `InterruptedException` tại các thao tác chặn có hỗ trợ ngắt. Khi bắt `InterruptedException` nhưng không ném tiếp, thường phải khôi phục cờ bằng `Thread.currentThread().interrupt()` trước khi thoát. Không nuốt ngắt rồi âm thầm chạy tiếp.

Với yêu cầu từ xa hoặc I/O không hỗ trợ interrupt, cancellation có thể cần API riêng để hủy request, đóng kết nối có kiểm soát hoặc truyền cancellation token. Không đồng nhất việc đã ngắt thread với việc server từ xa đã ngừng xử lý.

### 3.2. Quyền sở hữu và lan truyền yêu cầu hủy

Một Aspect chỉ nên hủy tác vụ nền nếu **hợp đồng cho phép nó sở hữu quyền hủy**. Nếu nhiều caller dùng chung một phép tính (single-flight, cache dùng chung, subscription nhiều người), việc một caller timeout không tự động đồng nghĩa được dừng tác vụ cho tất cả.

Phân biệt hai chính sách:

- **Caller-scoped timeout/cancel**: một người gọi ngừng chờ, tách subscriber hoặc trả lỗi riêng; phép tính chung vẫn chạy.
- **Operation-scoped timeout/cancel**: deadline thuộc chính tác vụ; nếu vượt giới hạn, thành phần điều phối có thể yêu cầu hủy và giải phóng tài nguyên khi worker dừng.

Khi chuỗi bất đồng bộ có các tác vụ con, phải định nghĩa hướng lan truyền: hủy cha có hủy con không, một nhánh lỗi có hủy các nhánh còn lại không, hủy một nhánh chia sẻ có ảnh hưởng nhánh khác không. Không giả định mọi thư viện tự truyền cancellation theo cùng cách.

### 3.3. Chuyển trạng thái và race condition

Các sự kiện “hoàn thành”, “hết giờ” và “caller hủy” có thể xảy ra gần như đồng thời. Đặt chính sách là **ai thắng trước thì công bố trạng thái tương ứng**, dùng thao tác nguyên tử hoặc cơ chế hoàn tất được thư viện cung cấp. Aspect không được báo vừa thành công vừa timeout cho cùng một kết quả logic.

Các trường hợp cần tính đến:

- Tác vụ xong trước khi timer bắn: timer kiểm tra trạng thái và không hủy.
- Timer bắn trước hoàn tất: handle có thể cancelled nhưng worker phải đi hết đường thoát và cleanup.
- Hủy trước khi worker bắt đầu: tài nguyên chỉ được cấp phát **bên trong** worker sẽ không tồn tại, do đó không có cleanup ở đường này.
- Hủy lặp lại: hành vi nên idempotent; một tài nguyên không được đóng hai lần do hai luồng xử lý timeout và cancel.
- Kết quả xuất hiện muộn: nếu caller đã timeout, không được ghi đè câu trả lời timeout hoặc tái sử dụng tài nguyên đã đóng; xử lý/loại bỏ kết quả muộn có chủ đích.

Nếu cần phân biệt chính xác lý do kết thúc (deadline, caller, shutdown), lưu lý do riêng bằng trạng thái đồng bộ/atomic; chỉ nhìn `CancellationException` thường không đủ.

## 4. Timeout: phân biệt chờ, hoàn tất logic và dừng thực tế

### 4.1. Timeout của người chờ

`future.get(200, TimeUnit.MILLISECONDS)` giới hạn **thời gian chờ của lời gọi `get`**. Khi ném `TimeoutException`, tác vụ nền **vẫn có thể chạy**. Hệ thống chỉ yêu cầu hủy nếu chính sách chủ động gọi `future.cancel(true)` hoặc cơ chế dừng phù hợp khác.

`CompletableFuture.orTimeout(duration, unit)` đặt thời điểm hoàn tất **exceptionally bằng `TimeoutException` cho chính `CompletableFuture` đó** nếu nó chưa hoàn tất. Nó **không tự ngắt** worker đang chạy. Tương tự, `completeOnTimeout(fallback, ...)` hoàn tất chính đối tượng đó bằng giá trị dự phòng và cũng không dừng công việc nền. Không dùng các API này như bằng chứng tài nguyên đã an toàn để đóng.

### 4.2. Timeout của thao tác và deadline tổng

Timeout tương đối cho từng bước có thể vượt tổng ngân sách. Ví dụ, một yêu cầu có ngân sách 600 ms nhưng ba bước nối tiếp đều được cấp 500 ms có thể kéo dài nhiều hơn 600 ms. Aspect điều phối nên dùng **deadline tổng** rồi tính ngân sách còn lại tại từng ranh giới.

Với đo thời gian trôi qua trong một tiến trình, dùng đồng hồ đơn điệu:

~~~java
long deadlineNanos = System.nanoTime()
        + TimeUnit.MILLISECONDS.toNanos(600);

// Trước mỗi thao tác chặn:
long remainingNanos = deadlineNanos - System.nanoTime();
if (remainingNanos <= 0) {
    throw new TimeoutException("Đã hết ngân sách thời gian");
}
String result = future.get(remainingNanos, TimeUnit.NANOSECONDS);
~~~

Đoạn này minh họa một phần phương thức đang có biến `future` kiểu `Future<String>` và được khai báo `throws InterruptedException, ExecutionException, TimeoutException`. `System.nanoTime()` dùng để đo khoảng thời gian, **không phải** thời gian lịch để ghi log hay truyền trực tiếp qua máy khác. Nếu truyền deadline giữa các dịch vụ, cần thỏa thuận cách biểu diễn và xử lý lệch đồng hồ; thường truyền ngân sách còn lại đã được kiểm soát.

Chính sách timeout cần ghi rõ nó tính từ **lúc caller bắt đầu gọi**, **lúc nhiệm vụ được xếp hàng** hay **lúc worker bắt đầu thực hiện**; ba mốc này cho kết quả rất khác nhau khi executor quá tải. Cũng cần phân biệt thời gian chờ trong queue, thời gian thực thi, timeout I/O và thời gian chờ lấy kết quả.

### 4.3. Timer cũng là tài nguyên

Một Aspect thường dùng `ScheduledExecutorService` để phát tín hiệu hủy khi quá hạn. Timer phải được hủy khi có thể xác nhận công việc hoàn tất; một scheduler nên được dùng chung và có vòng đời rõ ràng, tránh tạo một thread/timer service cho từng request. Với `Future` thuần không có callback hoàn tất, có thể chấp nhận một watchdog ngắn sống đến deadline, hoặc bổ sung lớp giám sát hoàn tất nếu cần thu hồi timer sớm.

Việc timeout không làm biến mất tác vụ nền: khi hủy không có hiệu lực, cần cơ chế giới hạn concurrency, backpressure và quan sát các tác vụ quá hạn đang còn chạy. Nếu không, hệ thống có thể trả timeout rất nhanh nhưng vẫn cạn luồng, kết nối hay bộ nhớ.

## 5. Dọn dẹp tài nguyên đúng vòng đời

### 5.1. Ai tạo thì chịu trách nhiệm đóng

Quy tắc thực dụng:

- **Worker sở hữu** file, socket, cursor, buffer hay resource được tạo để thực thi công việc: đóng bằng `try-with-resources` hoặc `finally` **ngay trong worker**, sau lần sử dụng cuối cùng.
- **Aspect sở hữu** timer, context snapshot, phép đo thời gian, đăng ký callback hoặc permit giới hạn đồng thời: thu hồi những tài nguyên này ở thời điểm phù hợp với vòng đời mà nó quản lý.
- **Caller sở hữu** quyền chờ kết quả: khi caller hết giờ, caller có thể dừng chờ mà không được tự ý đóng resource worker vẫn đang dùng.
- **Tài nguyên dùng chung**: chủ sở hữu quản lý reference count/lease hoặc vòng đời dịch vụ; mỗi invocation không được tùy tiện đóng.

Một anti-pattern nguy hiểm:

~~~java
// SAI nếu tác vụ nền vẫn dùng resource:
CompletableFuture<String> answer = computeUsing(resource)
        .orTimeout(200, TimeUnit.MILLISECONDS);
answer.whenComplete((value, error) -> resource.close());
~~~

Ở đây `orTimeout` có thể đánh dấu `answer` kết thúc trước khi computation ngừng, nên callback `close()` chạy quá sớm. Đây chỉ là **đoạn minh họa lỗi**, không phải một chương trình Java độc lập; cách sửa là để tác vụ thực sở hữu và đóng `resource` trong `finally`, hoặc có tín hiệu **physical completion** tách biệt khỏi kết quả đã timeout.

### 5.2. Callback sau khi hoàn tất: điểm mạnh và giới hạn

- `whenComplete((value, error) -> ...)` phù hợp để đo metric/log cho cả đường thành công lẫn exceptional; không nên mặc định nó được gọi trên một thread cụ thể.
- `whenCompleteAsync(..., executor)` đưa callback sang executor đã chỉ định; cần quản lý executor đó và cân nhắc callback bị trì hoãn hoặc từ chối khi shutdown.
- `thenApply(...)` chỉ chạy trên đường thành công, **không** đủ làm nơi cleanup cho mọi kết thúc.
- Callback có thể ném lỗi. Không để lỗi cleanup/telemetry che mất nguyên nhân nghiệp vụ; xử lý lỗi dọn dẹp riêng khi thích hợp. `try-with-resources` có cơ chế suppressed exceptions giúp giữ dấu vết khi cả thân xử lý và `close()` đều lỗi.

Quan trọng: callback trên một `CompletionStage` chỉ có ý nghĩa đối với **vòng đời logic của stage đó**. Nếu stage được hoàn tất sớm do timeout, callback không chứng minh worker đã thoát.

### 5.3. Nguyên tắc cleanup khi hủy

Trong worker, đặt vùng sử dụng tài nguyên trong `try/finally`; khi nhận interrupt, đi theo đường thoát hợp lệ và để `finally` chạy. Tránh tự tay gọi cleanup từ **cả** nhánh timeout của Aspect **và** `finally` của worker nếu chúng cùng sở hữu một resource. Nếu buộc phải có nhiều đường giải phóng, bảo vệ bằng trạng thái đồng bộ và một hợp đồng `close()` idempotent được thiết kế rõ ràng.

Sau khi một handle chuyển cancelled, đừng giả định mọi side effect đã rollback. Các tác vụ đã gửi email, ghi cơ sở dữ liệu hoặc gọi API từ xa có thể hoàn tất một phần. Cleanup bộ nhớ/connection và **bù trừ nghiệp vụ** là hai việc khác nhau; Aspect không thể tự động đảo ngược mọi side effect.

## 6. Aspect gắn chính sách ở đâu?

Một lời khuyên quanh lời gọi (around advice) có thể:

1. Đọc cấu hình/hợp đồng: deadline, loại tác vụ được phép hủy, chiến lược báo lỗi và chủ sở hữu resource.
2. Gọi phương thức gốc **đúng một lần**, ghi thời điểm bắt đầu và nhận `Future`/`CompletionStage`.
3. Gắn timer, callback quan sát, propagation token hoặc trả một wrapper điều phối; tránh chặn luồng gọi trừ khi API thực sự yêu cầu đồng bộ.
4. Khi hoàn tất/timeout/cancel, báo đúng trạng thái và thu hồi **resource do Aspect sở hữu**.
5. Giữ quyền quản lý cleanup của worker trong worker; xử lý các race giữa kết thúc, timeout và caller cancellation.

Đối với advice chỉ chạy quanh **phương thức trả về handle**, “after returning” thấy handle chứ không nhất thiết thấy giá trị cuối cùng; “after throwing” tại lời gọi không bắt được lỗi phát sinh về sau trong worker. Muốn quan sát kết quả cuối, cần gắn callback hoặc bọc abstraction bất đồng bộ phù hợp.

Khi dùng AOP nâng cao, xác định rõ **join point được weave** (lời gọi dịch vụ, thao tác submit, xử lý callback hay một lớp executor), tránh chặn trùng nhiều tầng gây đặt hai timer hoặc đếm cleanup hai lần. Dù dùng proxy hay weaving, các lời gọi nội bộ không đi qua interception boundary tương ứng có thể không bị advice bắt; đặc tính chính xác phụ thuộc cơ chế AOP.

## 7. Ví dụ chạy được: Aspect áp deadline cho Future bằng JDK dynamic proxy

Ví dụ dưới dùng Java 17+, chỉ thư viện chuẩn. `DeadlineAspect` chặn phương thức trên interface, nhận `Future` rồi đặt watchdog. Khi quá 250 ms, Aspect **yêu cầu** hủy bằng `cancel(true)`. Worker đang ngủ phản ứng với interrupt và luôn thực hiện `finally`.

Tạo file `DeadlineAspectDemo.java`:

~~~java
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.concurrent.CancellationException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;

public class DeadlineAspectDemo {
    interface JobService {
        Future<String> submit();
    }

    static final class JobServiceImpl implements JobService {
        private final ExecutorService workers;

        JobServiceImpl(ExecutorService workers) {
            this.workers = workers;
        }

        @Override
        public Future<String> submit() {
            return workers.submit(() -> {
                System.out.println("worker: bat dau");
                try {
                    Thread.sleep(1_200);
                    return "OK";
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    throw e;
                } finally {
                    System.out.println("worker: don dep");
                }
            });
        }
    }

    static final class DeadlineAspect implements InvocationHandler {
        private final JobService target;
        private final ScheduledExecutorService scheduler;

        DeadlineAspect(JobService target, ScheduledExecutorService scheduler) {
            this.target = target;
            this.scheduler = scheduler;
        }

        @Override
        public Object invoke(Object proxy, Method method, Object[] args)
                throws Throwable {
            Object returned;
            try {
                returned = method.invoke(target, args);
            } catch (InvocationTargetException e) {
                throw e.getCause();
            }

            if (returned instanceof Future<?> future) {
                scheduler.schedule(() -> {
                    if (!future.isDone() && future.cancel(true)) {
                        System.out.println("aspect: yeu cau huy do qua han");
                    }
                }, 250, TimeUnit.MILLISECONDS);
            }
            return returned;
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService workers = Executors.newSingleThreadExecutor();
        ScheduledExecutorService scheduler =
                Executors.newSingleThreadScheduledExecutor();
        try {
            JobService service = (JobService) Proxy.newProxyInstance(
                    JobService.class.getClassLoader(),
                    new Class<?>[] { JobService.class },
                    new DeadlineAspect(new JobServiceImpl(workers), scheduler));

            Future<String> result = service.submit();
            try {
                System.out.println("caller: " + result.get());
            } catch (CancellationException e) {
                System.out.println("caller: future da bi huy");
            }
        } finally {
            workers.shutdown();
            scheduler.shutdown();
            if (!workers.awaitTermination(2, TimeUnit.SECONDS)) {
                workers.shutdownNow();
            }
            if (!scheduler.awaitTermination(2, TimeUnit.SECONDS)) {
                scheduler.shutdownNow();
            }
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac DeadlineAspectDemo.java
java DeadlineAspectDemo
~~~

Khi worker kịp bắt đầu và bị ngắt sau deadline, sẽ xuất hiện các thông báo:

~~~text
worker: bat dau
aspect: yeu cau huy do qua han
caller: future da bi huy
worker: don dep
~~~

**Thứ tự hai dòng giữa/cuối có thể khác nhau**: caller có thể nhận `CancellationException` khi worker còn đang vào `finally`, và scheduler có thể in log sau khi `Future` chuyển trạng thái. Nếu worker chưa kịp bắt đầu trước lúc bị hủy, dòng “worker: bat dau” và cleanup trong worker có thể không xuất hiện. Đó là tính chất của concurrency, không phải lỗi cú pháp.

Các giới hạn cố ý của ví dụ:

- JDK proxy chặn được lời gọi qua **interface** `JobService`; nó không tự chặn mọi phương thức hay mọi lời gọi nội bộ.
- Timer đặt deadline từ khi Aspect nhận `Future`. Mốc này có thể khác thời điểm công việc bắt đầu trong queue.
- `cancel(true)` hiệu quả với `Thread.sleep` vì thao tác này phản ứng với interrupt. Worker không hợp tác thì có thể tiếp tục chạy.
- Ở ví dụ tối giản, watchdog còn được xếp lịch đến 250 ms kể cả khi tác vụ xong sớm. Bản production nên quản lý việc hủy timer theo completion thực tế, theo dõi lý do hủy và xử lý lifecycle của executor.
- `result.get()` nhận `CancellationException`, **không phải `TimeoutException`**: đây là chính sách timeout được biểu diễn bằng hành động hủy handle. Nếu API yêu cầu phân biệt “quá hạn” với “người dùng hủy”, cần một lớp trạng thái/kết quả riêng.

## 8. Ví dụ chạy được: CompletableFuture và cancellation token hợp tác

`CompletableFuture.cancel(true)` không ngắt computation nền như ví dụ `FutureTask`. Một lựa chọn khi thiết kế worker thuộc quyền kiểm soát của mình là **cancellation token** dùng chung. Ví dụ dưới giới hạn thời gian chờ phía caller rồi bật token; worker kiểm tra token ở mỗi bước và tự đóng resource sau khi thực sự thoát.

Tạo file `CooperativeCleanupDemo.java`:

~~~java
import java.util.concurrent.CancellationException;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicBoolean;

public class CooperativeCleanupDemo {
    static final class Resource implements AutoCloseable {
        @Override
        public void close() {
            System.out.println("resource: da dong");
        }
    }

    static CompletableFuture<String> start(
            ExecutorService executor, AtomicBoolean cancelled) {
        return CompletableFuture.supplyAsync(() -> {
            try (Resource resource = new Resource()) {
                for (int step = 0; step < 5; step++) {
                    if (cancelled.get()) {
                        throw new CancellationException("Da yeu cau huy");
                    }
                    Thread.sleep(100);
                }
                return "OK";
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                throw new CompletionException(e);
            }
        }, executor).whenComplete((value, error) -> {
            System.out.println("observer: worker da ket thuc");
        });
    }

    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        AtomicBoolean cancelled = new AtomicBoolean(false);
        try {
            CompletableFuture<String> result = start(executor, cancelled);
            try {
                System.out.println("caller: " + result.get(180, TimeUnit.MILLISECONDS));
            } catch (TimeoutException e) {
                cancelled.set(true);
                System.out.println("caller: het gio, da gui tin hieu huy");
            }
        } finally {
            executor.shutdown();
            if (!executor.awaitTermination(2, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac CooperativeCleanupDemo.java
java CooperativeCleanupDemo
~~~

Thông thường chương trình in ba thông báo sau (thứ tự dòng phía observer/resource với dòng caller có thể xen kẽ do scheduler luồng):

~~~text
caller: het gio, da gui tin hieu huy
resource: da dong
observer: worker da ket thuc
~~~

Ở đây `get(180, ...)` chỉ giới hạn **chờ**; `AtomicBoolean` mới là tín hiệu worker hợp tác kiểm tra. `Resource` được tạo và đóng bên trong worker; caller không đóng nó vào đúng mốc timeout. Chương trình giữ executor sống đủ lâu để worker đi hết đường dọn dẹp.

Không suy luận rằng token có thể làm dừng ngay một thao tác không kiểm tra token: muốn hủy nhanh các lần I/O dài, phải thiết kế timeout/I/O cancellation riêng. Ở ví dụ này, worker có thể mất tối đa xấp xỉ một bước ngủ nữa trước khi nhận tín hiệu, tùy lịch chạy.

## 9. Xử lý lỗi tại ranh giới bất đồng bộ

Một Aspect cần phân biệt các nhóm lỗi và truyền chúng đúng hợp đồng:

| Tình huống | Điều caller thường thấy | Hướng xử lý |
| --- | --- | --- |
| Lỗi ném ngay khi gọi phương thức | Exception tại join point đồng bộ | Advice đồng bộ xử lý, log rồi truyền tiếp theo hợp đồng |
| Worker lỗi khi thực thi `Callable` | `ExecutionException` khi `Future.get()`; nguyên nhân nằm trong `getCause()` | Quan sát nguyên nhân; đừng quy mọi exception thành timeout |
| `CompletableFuture` hoàn tất lỗi | `CompletionException` qua `join()`, hoặc `ExecutionException` qua `get()` | Giữ chuỗi nguyên nhân và ngữ cảnh bất đồng bộ |
| Caller `get(timeout)` hết giờ | `TimeoutException` tại thao tác chờ | Xác định chỉ ngừng chờ hay yêu cầu hủy operation |
| `Future` được hủy | `CancellationException` khi lấy kết quả | Phân biệt lý do hủy bằng metadata/trạng thái riêng nếu cần |
| Worker nhận interrupt | Có thể là `InterruptedException` hoặc đường thoát tùy code | Khôi phục cờ interrupt khi thích hợp, chạy `finally` |
| Cleanup lỗi | Exception khi đóng resource/callback | Giữ nguyên nhân chính, ghi nhận lỗi cleanup; tránh báo success giả |

Nếu Aspect chuyển lỗi thành fallback, cần nêu rõ fallback **chỉ giải quyết kết quả logic**, chưa chắc đã dừng tác vụ vật lý. Với retry, mỗi lần chạy phải dùng ngân sách deadline còn lại, và không retry trên cancellation hoặc timeout đã hết budget nếu không có chính sách cho phép. Không retry mù các thao tác có side effect không idempotent.

## 10. Các tình huống thiết kế nâng cao

### 10.1. Context qua ranh giới luồng

Thông tin truy vết, correlation ID, định danh người gọi hoặc các giá trị `ThreadLocal` không tự chuyển sang executor khác một cách đáng tin. Nếu Aspect chụp context trước `submit` và phục hồi trong worker, phải:

- Chụp **giá trị cần thiết**, tránh giữ tham chiếu tới dữ liệu mutable không an toàn.
- Thiết lập context ngay khi worker bắt đầu, rồi khôi phục/xóa trong `finally` để không rò sang tác vụ kế tiếp dùng lại thread.
- Truyền ngữ cảnh phù hợp vào callback có thể chạy ở thread khác.
- Không dùng thời điểm caller hết giờ để xóa context mà worker còn cần; phân biệt context caller và context worker.

### 10.2. Bulkhead, concurrency và tài nguyên dùng chung

Nếu Aspect lấy semaphore permit trước khi submit, phải xác định permit được trả khi nào. **Trả permit ngay lúc Future bị đánh dấu cancelled có thể sai** nếu worker vẫn đang chạy và dùng resource cần giới hạn. Với limit số worker thực sự hoạt động, chỉ trả permit khi worker vật lý kết thúc trong `finally`. Với limit số lời gọi caller đang chờ, lifetime có thể khác. Hai loại giới hạn không nên dùng chung một bộ đếm mơ hồ.

Đối với queue đã nhận tác vụ nhưng chưa chạy, hủy trước khi bắt đầu đòi hỏi bộ điều phối thu hồi slot/permit của tác vụ chờ; dựa hoàn toàn vào `finally` của worker sẽ không xử lý đường “chưa từng được thực thi”.

### 10.3. Nested async, fan-out và partial success

Một thao tác có thể gọi nhiều nhánh đồng thời. Khi một nhánh timeout, chính sách có thể chờ các nhánh khác, hủy toàn bộ nhóm, trả kết quả một phần hoặc đợi cleanup toàn bộ trước khi công bố “operation drained”. Aspect cần chọn rõ semantics và deadline tổng; đừng mặc định `allOf`, chuỗi `thenApply` hay việc hủy một `CompletableFuture` tự hủy tất cả phép tính phía dưới.

### 10.4. Kết quả muộn và callback chạy sau hủy

Nếu observer nhận hai tín hiệu theo các đường cạnh tranh (timeout và completion), hãy dùng trạng thái nguyên tử để công bố **một terminal event logic**. Có thể vẫn cần một sự kiện riêng cho “worker thực sự đã thoát” để quản lý resource và metric. Đừng đồng nhất metric “request timeout” với metric “task stopped”.

Nếu một callback vừa ghi kết quả vừa cleanup, bảo đảm xử lý đúng khi timeout đến giữa hai thao tác; xử lý cleanup riêng khỏi publish result và dùng primitive đồng bộ thích hợp cho tài nguyên chia sẻ.

## 11. Checklist thiết kế và kiểm thử

Trước khi áp dụng Aspect timeout/cancel/cleanup cho một API bất đồng bộ, xác nhận:

1. **Đúng phạm vi join point**: chặn lời gọi nào, lời gọi nào bypass proxy/weaving, có intercept trùng không?
2. **Đúng vòng đời**: ghi riêng invocation return, logical completion và physical completion; xác định owner cho từng resource.
3. **Deadline nhất quán**: tính từ mốc nào, ngân sách cha truyền cho con ra sao, đo elapsed time bằng đồng hồ đơn điệu.
4. **Hủy có hợp đồng**: ai được hủy, hủy handle hay worker, interrupt/token/transport có thực sự được hỗ trợ không, các subscriber có chia sẻ công việc không?
5. **Cleanup an toàn**: chạy khi resource hết được sử dụng, xử lý cả thành công/lỗi/hủy, bảo toàn lỗi gốc và tránh double-close.
6. **Quan sát đầy đủ**: phân biệt deadline, cancellation chủ động, worker failure và cleanup failure; cảnh báo worker còn sống sau timeout.
7. **Kiểm thử race**: dùng `CountDownLatch`, `Phaser` hoặc executor kiểm soát được lịch thay vì chỉ `Thread.sleep`; tạo các trường hợp hoàn tất đúng lúc timeout, hủy trước khi chạy, hủy đang chạy, hủy lặp, lỗi tại cleanup, worker phớt lờ interrupt và shutdown đồng thời.
8. **Kiểm thử bảo toàn tài nguyên**: xác minh mỗi resource được thu hồi đúng một lần, không sử dụng sau khi đóng, timer/permit được trả đúng thời điểm và không còn tác vụ mồ côi sau khi caller kết thúc.

Khi một timeout xảy ra, câu hỏi chính không chỉ là “caller đã nhận lỗi chưa?”, mà còn là “**tác vụ vật lý còn đang chạy không, ai giữ tài nguyên, và ai sẽ đưa nó về trạng thái an toàn?**”. Đó là trách nhiệm cốt lõi của một chính sách AOP được thiết kế đúng tại ranh giới bất đồng bộ.
