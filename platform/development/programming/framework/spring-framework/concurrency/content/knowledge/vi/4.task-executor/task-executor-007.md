# TaskRejectedException và hợp đồng khi không nhận được tác vụ trong Spring TaskExecutor

Khi một ứng dụng Spring gửi công việc nền cho `TaskExecutor`, đôi khi executor không thể hoặc không muốn nhận thêm tác vụ. Đây là một tình huống vận hành bình thường cần được thiết kế trước, đặc biệt khi hệ thống chịu tải cao hoặc đang shutdown. Trong Spring, `TaskRejectedException` là tín hiệu quan trọng của tình huống đó. Hiểu đúng tín hiệu này giúp tránh trả lời “đã nhận việc” khi thực tế chưa có nơi nào chịu trách nhiệm xử lý công việc.

Bài học tập trung vào **hợp đồng tại thời điểm submit**, nguyên nhân từ chối, chính sách xử lý khi quá tải và cách ứng dụng Spring phản hồi. Nó không giả định rằng mọi `TaskExecutor` đều chạy bất đồng bộ hoặc mọi tác vụ đều được lưu bền vững.

## 1. Sau bài học, bạn cần phân biệt được điều gì?

- Phân biệt **executor nhận tác vụ**, **tác vụ được bắt đầu**, **tác vụ hoàn thành** và **kết quả nghiệp vụ được lưu bền vững**.
- Xác định khi nào `TaskExecutor.execute(Runnable)` có thể ném `TaskRejectedException` và quan hệ của nó với `RejectedExecutionException` trong JDK.
- Hiểu trình tự sử dụng `corePoolSize`, hàng đợi, `maxPoolSize` và thời điểm pool đạt giới hạn.
- So sánh `AbortPolicy`, `CallerRunsPolicy`, `DiscardPolicy`, `DiscardOldestPolicy` theo **hợp đồng mất việc, độ trễ và backpressure**.
- Cấu hình `ThreadPoolTaskExecutor` có giới hạn, bắt lỗi ở ranh giới gửi việc, và thiết kế response/retry phù hợp với mức bảo đảm thực tế.
- Kiểm thử tình huống từ chối **một cách xác định bằng latch**, thay vì dựa vào `Thread.sleep()`.

## 2. `TaskExecutor` hứa điều gì?

Spring định nghĩa `org.springframework.core.task.TaskExecutor` kế thừa `java.util.concurrent.Executor`, với phương thức:

~~~java
void execute(Runnable task);
~~~

Lời gọi chuyển một `Runnable` cho executor. Tùy implementation, tác vụ có thể chạy ngay trên thread gọi (`SyncTaskExecutor`), chạy trên worker thread hoặc được xếp vào hàng đợi. API không trả về job ID, kết quả, trạng thái hoàn thành hay cam kết lưu bền vững.

Theo hợp đồng `TaskExecutor`, khi không chấp nhận được tác vụ, `execute` có thể ném **`TaskRejectedException`** (unchecked). Đây là lỗi **tại ranh giới giao việc**. Không đồng nhất nó với exception xảy ra bên trong `Runnable.run()` sau khi tác vụ đã bắt đầu.

### Bốn cột mốc khác nhau

| Cột mốc | Ý nghĩa | Điều chưa được bảo đảm |
| --- | --- | --- |
| `execute` được gọi | Bên gửi yêu cầu executor nhận việc | Chưa biết có nhận hay không |
| Không có rejection trong cấu hình báo lỗi rõ ràng | Executor đã nhận việc theo chính sách đang dùng, hoặc có thể đã chạy đồng bộ | Chưa bảo đảm task bắt đầu, hoàn thành, thành công hoặc bền vững |
| `Runnable.run()` bắt đầu | Worker/caller bắt đầu thực thi công việc | Công việc có thể lỗi, bị hủy hoặc dừng giữa chừng |
| Tác vụ hoàn tất và kết quả được commit | Có một kết quả thực thi; mức bền vững do tầng lưu trữ quyết định | Không có cam kết chống trùng lặp nếu retry không được thiết kế |

**Ngoại lệ quan trọng:** nếu cấu hình chính sách **im lặng bỏ tác vụ** như `DiscardPolicy`, `execute` có thể trở về bình thường dù tác vụ không hề được chạy hay xếp hàng. Vì vậy câu “không ném exception tức là chắc chắn đã nhận việc” chỉ có thể dựa vào **chính sách từ chối cụ thể** (ví dụ `AbortPolicy`), không phải một sự thật cho mọi executor.

Để đáp ứng yêu cầu “mỗi job phải được xử lý”, một hàng đợi in-memory và lời gọi `execute` thành công **chưa đủ**. Cần có nơi tiếp nhận bền vững, định danh job, cơ chế khôi phục, theo dõi trạng thái và quy tắc retry/idempotency.

## 3. `TaskRejectedException` có ý nghĩa thế nào?

`org.springframework.core.task.TaskRejectedException` **kế thừa `java.util.concurrent.RejectedExecutionException`**. Nó là runtime exception biểu thị rằng một `TaskExecutor` không nhận tác vụ theo hợp đồng của Spring. Khi `ThreadPoolTaskExecutor` nhận `RejectedExecutionException` từ JDK executor bên dưới, nó thường chuyển thành `TaskRejectedException` để phía Spring có loại exception nhất quán.

Hệ quả khi bắt lỗi:

~~~java
try {
    taskExecutor.execute(task);
} catch (TaskRejectedException ex) {
    // Hợp đồng Spring: job không được tiếp nhận.
    // Phải công khai trạng thái không nhận việc cho caller.
}
~~~

Đây là **đoạn minh họa đặt trong phương thức** có `taskExecutor` và `task` hợp lệ; phần xử lý trong `catch` phải do yêu cầu nghiệp vụ quyết định. Nếu gọi trực tiếp `java.util.concurrent.ThreadPoolExecutor`, exception tương ứng thường là `RejectedExecutionException`. Vì `TaskRejectedException` là subclass, một `catch (RejectedExecutionException ex)` cũng bắt được nó, nhưng bắt loại cụ thể của Spring thường truyền tải ý định rõ hơn ở tầng ứng dụng Spring.

Không được diễn giải `TaskRejectedException` thành “task đã chạy rồi lỗi”, “đã retry”, hoặc “tự động xử lý ở lần sau”. Tại thời điểm đó, ứng dụng phải quyết định có trả lỗi, giảm tải, lưu việc để gửi lại hay chuyển sang cơ chế dự phòng.

### Phân biệt với exception từ tác vụ

Giả sử đã gửi được một task:

~~~java
taskExecutor.execute(() -> {
    throw new IllegalStateException("Không đọc được tệp đầu vào");
});
~~~

Trong mô hình executor **bất đồng bộ** thông thường, exception của `run()` xảy ra trên worker thread, **không** quay lại lời gọi `execute` ở thread ban đầu theo cách tương tự rejection. Nếu implementation chạy đồng bộ, exception của body có thể xuất hiện ngay trên caller thread. Các lớp `Future`/`CompletableFuture` có đường truyền kết quả hoặc lỗi riêng; cần đọc đúng completion state thay vì chỉ bắt `TaskRejectedException`.

## 4. Khi nào một pool từ chối?

Với `ThreadPoolTaskExecutor` thường dùng trong Spring, lớp nền là `ThreadPoolExecutor` của JDK. Hai nguyên nhân điển hình:

1. **Đạt giới hạn tải:** các worker hiện có đang bận, queue đã đầy và không còn chỗ tăng thread dưới `maxPoolSize`.
2. **Đã/đang shutdown:** executor ngừng chấp nhận tác vụ mới theo vòng đời hoặc chính sách shutdown.

Các implementation khác có thể có quy tắc riêng. Ví dụ executor có concurrency limit, chính sách chờ hoặc chạy đồng bộ có ngữ nghĩa khác; **không** áp công thức của `ThreadPoolExecutor` lên mọi `TaskExecutor`.

### Trình tự phân bổ công việc của một `ThreadPoolExecutor` thông thường

1. Nếu số worker hiện có nhỏ hơn `corePoolSize`, ưu tiên tạo worker để chạy task mới.
2. Sau mức core, thử **đưa task vào queue**.
3. Khi queue không còn nhận thêm, nếu số worker nhỏ hơn `maxPoolSize` thì thử mở rộng pool.
4. Nếu đã hết khả năng nhận task, gọi `RejectedExecutionHandler`.

Ví dụ cấu hình `corePoolSize=2`, `maxPoolSize=4`, `queueCapacity=3`: dưới tải liên tục khiến task đang chạy chưa xong, pool dùng 2 worker core; sau đó 3 task chờ; tiếp theo có thể mở rộng lên 4 worker; tác vụ tiếp theo bị từ chối nếu cả worker và queue vẫn bão hòa. Đây là mô hình **tại thời điểm tài nguyên đang bận**; trong thực tế task kết thúc đồng thời có thể làm thay đổi kết quả.

### Đừng bỏ qua cấu hình mặc định

`ThreadPoolTaskExecutor` thường mặc định `corePoolSize=1`, `maxPoolSize=Integer.MAX_VALUE` và `queueCapacity=Integer.MAX_VALUE`. Với queue gần như không giới hạn, pool khó tăng vượt core và số job tồn đọng có thể tăng lớn, thậm chí gây thiếu bộ nhớ. **Không thấy rejection không có nghĩa hệ thống khỏe mạnh.**

Một vài lựa chọn queue cần hiểu:

- `queueCapacity > 0`: Spring dùng `LinkedBlockingQueue` có sức chứa khai báo.
- `queueCapacity = 0`: Spring dùng `SynchronousQueue`, không có buffer; task cần được giao cho worker hoặc dẫn tới mở rộng pool/rejection.
- Queue hữu hạn cùng `maxPoolSize` hữu hạn giúp xác định được ngưỡng nhận việc và đường xử lý overload.
- Tăng `maxPoolSize` không giải quyết được queue quá lớn nếu cơ chế vẫn luôn đưa vào queue trước khi tăng worker.

Đừng dựa vào con số cấu hình như một cam kết tuyệt đối về latency hoặc thông lượng. Tốc độ mỗi task, block I/O, thời gian chờ dependency, lịch CPU và chính sách từ chối mới quyết định tải thực tế.

## 5. Các `RejectedExecutionHandler` và mặt trái của từng chính sách

`ThreadPoolTaskExecutor` cho phép cấu hình `setRejectedExecutionHandler(...)` để chuyển chính sách từ chối xuống JDK pool. Bốn lựa chọn có sẵn của `ThreadPoolExecutor`:

| Chính sách | Khi pool bão hòa | Phù hợp khi | Rủi ro cần chủ động xử lý |
| --- | --- | --- | --- |
| `AbortPolicy` (mặc định) | Ném `RejectedExecutionException`; Spring thường chuyển thành `TaskRejectedException` | Muốn caller **biết chắc không nhận được việc** và quyết định retry/HTTP error | Nếu caller không bắt/không chuyển lỗi phù hợp sẽ lộ lỗi chưa kiểm soát |
| `CallerRunsPolicy` | Caller thread **tự chạy** task nếu pool chưa shutdown | Chấp nhận tăng latency của producer để tạo backpressure | Có thể chặn request thread, event loop, hoặc làm việc chạy đồng bộ bất ngờ; nếu pool đã shutdown, task có thể bị bỏ im lặng |
| `DiscardPolicy` | Bỏ task mà **không ném lỗi** | Chỉ với tín hiệu best-effort có thể mất và được thiết kế chấp nhận mất | Caller có thể tưởng đã nhận; `Future` tương ứng có thể không bao giờ hoàn thành |
| `DiscardOldestPolicy` | Bỏ phần tử ở đầu queue rồi thử gửi task mới, trừ trường hợp shutdown | Trường hợp đặc biệt nơi task chờ cũ được phép hy sinh | Mất job cũ, phá thứ tự, làm `Future` của job cũ treo nếu không hủy/báo lỗi, không phù hợp queue ưu tiên |

Với đơn hàng, xuất báo cáo cần truy vết hoặc xử lý dữ liệu nghiệp vụ, **`AbortPolicy` thường là lựa chọn an toàn để không che giấu việc bị từ chối**. Với metrics có thể mất, chính sách bỏ tác vụ có thể có lý nhưng phải đo số lần rơi và thỏa thuận rõ với consumer. Không nên chọn `CallerRunsPolicy` theo thói quen mà không tính ảnh hưởng đến thời gian phản hồi và thread gọi.

Chính sách tùy biến cũng có thể được triển khai qua `RejectedExecutionHandler`. Nếu muốn caller nhận được lỗi, custom handler phải **ném `RejectedExecutionException`**; handler chỉ log rồi return sẽ có nguy cơ biến lỗi thành thành công giả tại ranh giới `execute`.

~~~java
executor.setRejectedExecutionHandler((runnable, pool) -> {
    throw new java.util.concurrent.RejectedExecutionException(
            "Executor unavailable: saturated or shutting down");
});
~~~

Đoạn trên chỉ minh họa setter trong code đang cấu hình một `ThreadPoolTaskExecutor executor`, không phải một chương trình Java độc lập. Trong ứng dụng thật cần ghi chỉ số rejection nhưng tránh log dữ liệu nhạy cảm từ task và tránh xử lý I/O nặng ngay trong rejection handler.

## 6. Ví dụ Java 17+: tạo rejection một cách xác định

Ví dụ sau dùng **JDK `ThreadPoolExecutor` thuần** để học chính xác thời điểm queue đầy. Chúng ta chủ động giữ task đầu trong worker, xếp task thứ hai vào queue capacity 1, rồi gửi task thứ ba. Khi chưa thả latch, worker và queue đều không còn chỗ.

**Tệp `JdkRejectionDemo.java`**:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public final class JdkRejectionDemo {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch firstStarted = new CountDownLatch(1);
        CountDownLatch releaseFirst = new CountDownLatch(1);
        CountDownLatch done = new CountDownLatch(2);
        AtomicInteger completed = new AtomicInteger();

        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 1, 0, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(1),
                new ThreadPoolExecutor.AbortPolicy());

        try {
            pool.execute(() -> {
                firstStarted.countDown();
                try {
                    releaseFirst.await();
                    completed.incrementAndGet();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                } finally {
                    done.countDown();
                }
            });

            if (!firstStarted.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("First task did not start");
            }

            pool.execute(() -> {
                completed.incrementAndGet();
                done.countDown();
            });

            boolean rejected = false;
            try {
                pool.execute(() -> completed.incrementAndGet());
            } catch (RejectedExecutionException ex) {
                rejected = true;
            }

            System.out.println("rejected=" + rejected);
            if (!rejected) {
                throw new AssertionError("Expected a rejection");
            }

            releaseFirst.countDown();
            if (!done.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Tasks did not finish");
            }
            System.out.println("completed=" + completed.get());
        } finally {
            releaseFirst.countDown();
            pool.shutdownNow();
        }
    }
}
~~~

Biên dịch/chạy (JDK 17 trở lên):

~~~bash
javac JdkRejectionDemo.java
java JdkRejectionDemo
~~~

Kết quả chuẩn của lần chạy thành công:

~~~text
rejected=true
completed=2
~~~

**Vì sao kết quả xác định?** `firstStarted.await` chỉ tiếp tục khi task thứ nhất đang nắm worker; `releaseFirst` giữ worker đó chờ, nên task thứ hai nằm trong queue và task thứ ba không có chỗ. Sau khi bắt rejection, `releaseFirst.countDown()` cho phép xử lý nốt hai tác vụ đã nhận; `done.await()` đảm bảo đọc kết quả sau khi cả hai hoàn thành. Hai timeout 5 giây là chốt tránh treo vô hạn trên môi trường lỗi, không phải công cụ tạo race.

Nếu dùng **Spring `ThreadPoolTaskExecutor`** với cùng các giới hạn và `AbortPolicy`, nguyên lý bão hòa vẫn vậy, nhưng exception tại lời gọi `execute` của Spring sẽ là `TaskRejectedException`.

## 7. Cấu hình Spring `ThreadPoolTaskExecutor` để rejection có nghĩa rõ ràng

Mẫu dưới đây dùng cấu hình hữu hạn và `AbortPolicy`. Các thông số `2/4/20` chỉ là ví dụ, không phải sizing được khuyến nghị cho mọi ứng dụng.

**Tệp `ExportExecutorConfig.java` trong dự án Spring có dependency `spring-context`:**

~~~java
import java.util.concurrent.ThreadPoolExecutor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class ExportExecutorConfig {

    @Bean(name = "exportExecutor")
    public ThreadPoolTaskExecutor exportExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(20);
        executor.setThreadNamePrefix("export-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        return executor;
    }
}
~~~

Khi là Spring bean bình thường, container quản lý khởi tạo và lifecycle của executor. Nếu tự tạo `new ThreadPoolTaskExecutor()` ngoài container rồi trực tiếp sử dụng, phải gọi `initialize()` trước khi `execute` và quản lý shutdown thích hợp. Không đặt `setQueueCapacity` bằng một số rất lớn chỉ để che đi tín hiệu overload.

Một lớp service có thể để exception **đi tới điểm quyết định nghiệp vụ**, thay vì bắt và nuốt lỗi:

**Tệp `ExportSubmissionService.java`:**

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.core.task.TaskExecutor;
import org.springframework.stereotype.Service;

@Service
public class ExportSubmissionService {
    private final TaskExecutor exportExecutor;

    public ExportSubmissionService(
            @Qualifier("exportExecutor") TaskExecutor exportExecutor) {
        this.exportExecutor = exportExecutor;
    }

    public void submit(String exportId) {
        exportExecutor.execute(
                () -> System.out.println("Processing export " + exportId));
    }
}
~~~

Đây là ví dụ về đường giao việc, trong đó `System.out.println` đại diện cho một thao tác đơn giản có thể nhìn thấy. Nó **không** tạo job bền vững, không có trạng thái để truy vấn và không xử lý xuất tệp thật. Phần lưu job, transaction, retry và xử lý kết quả cần bổ sung theo yêu cầu nghiệp vụ.

Lớp gọi `submit` phải quyết định ý nghĩa khi gặp `TaskRejectedException`. Ví dụ một API không thể nhận thêm job tại thời điểm quá tải có thể trả HTTP 503, hoặc HTTP 429 khi thực sự áp giới hạn theo người gọi. Có thể cung cấp `Retry-After` nếu có chính sách retry đáng tin. **HTTP 202 Accepted** chỉ nên được sử dụng với ý nghĩa mà ứng dụng thực sự bảo đảm: nếu hứa chắc việc sẽ được xử lý về sau, hãy ghi nhận yêu cầu vào nơi lưu bền vững trước khi xác nhận.

### Phải đặt `catch` tại đúng ranh giới

~~~java
try {
    exportSubmissionService.submit(exportId);
    // Chỉ báo đã giao thành công theo hợp đồng executor và policy hiện tại.
} catch (TaskRejectedException ex) {
    // Không trả thành công giả. Chuyển thành phản hồi quá tải,
    // hoặc lưu công việc vào kênh dự phòng đáng tin cậy.
}
~~~

Đoạn này là **mẫu xử lý minh họa**, cần đặt trong một method có `exportSubmissionService`, `exportId` và phản hồi nghiệp vụ thích hợp. Không chạy lại ngay trong vòng lặp vô hạn: trong lúc pool đang bão hòa, việc retry liên tục chỉ làm tăng tải.

## 8. `execute`, `submit`, `Future` và `@Async`: ba đường lỗi khác nhau

| Trường hợp | Lỗi xuất hiện ở đâu? | Caller nên làm gì? |
| --- | --- | --- |
| `TaskExecutor.execute` bị từ chối theo `AbortPolicy` | Tại thời điểm gọi `execute` bằng `TaskRejectedException` | Xử lý không nhận việc, trả trạng thái hoặc persist để retry |
| Task đã nhận nhưng `Runnable.run()` ném exception | Trên thread thực thi; với executor bất đồng bộ, không quay về `execute` thông thường | Quan sát log/task wrapper/status; bổ sung future nếu cần kết quả |
| `AsyncTaskExecutor.submit` nhận task, task chạy lỗi | `Future.get()` báo `ExecutionException` (cause là lỗi gốc) | Xử lý execution failure, phân biệt với rejection khi submit |
| `submit` không được executor nhận | Có thể ném `TaskRejectedException` **trước khi trả về `Future`** | Xử lý tại caller của `submit`; không chờ một future không tồn tại |
| `CompletableFuture` được tạo và tác vụ chạy lỗi | Future hoàn thành exceptionally; `join()` thường ném `CompletionException` | Quan sát `whenComplete/handle/exceptionally` hoặc `join/get` |
| `@Async` qua Spring proxy không gửi được task | Lỗi có thể phát sinh ở thread gọi khi proxy dispatch công việc | Bắt lỗi tại boundary gọi method; không dựa vào handler xử lý lỗi trong body |
| `@Async void` đã bắt đầu rồi ném lỗi | Đường `AsyncUncaughtExceptionHandler` cho exception không có Future | Cấu hình handler/ghi nhận job thất bại phù hợp |

`@Async` chỉ hoạt động theo proxy khi lời gọi thực sự đi **qua Spring proxy**; self-invocation trong cùng bean theo proxy mode mặc định thường không được intercept. Ngoài ra, nếu dùng `CallerRunsPolicy` khi bão hòa thì work có thể chạy trên chính thread gọi, dù đường code mang nhãn async. Vì vậy không được xây dựng hợp đồng nghiệp vụ chỉ dựa vào kỳ vọng “method này luôn chạy trên thread khác”.

**Cần đặc biệt tránh:** kết hợp `submit` với `DiscardPolicy` hoặc `DiscardOldestPolicy` cho công việc cần kết quả. Task/Future có thể bị bỏ mà không nhận completion/cancellation tương ứng, khiến chờ `Future.get()` mãi không xong. Nếu chủ động bỏ task, phải có cơ chế ghi nhận kết quả “dropped” hoặc hủy future một cách thích hợp.

## 9. Thiết kế hợp đồng từ góc nhìn bên gửi việc

Trước khi code, cần trả lời: **khi không nhận được việc, hệ thống phải bảo đảm điều gì cho người gọi?** Có thể dùng bảng quyết định:

| Loại công việc | Có thể mất không? | Hợp đồng đề xuất khi bị reject |
| --- | --- | --- |
| Cập nhật biểu đồ thống kê best-effort | Có, nếu đã được thống nhất | Đo rejected/dropped; có thể bỏ với cảnh báo vận hành |
| Render ảnh tạm có thể sinh lại | Có thể retry | Trả “bận”, retry có giới hạn hoặc lưu yêu cầu ở kênh khác |
| Email giao dịch, báo cáo người dùng đặt tạo | Thông thường không nên mất âm thầm | Ghi job bền vững; xử lý lại có idempotency và trạng thái tra cứu |
| Trừ tiền, thay đổi số dư hay tồn kho | Không được dựa vào RAM queue | Dùng transaction/điều kiện cập nhật ở database và cơ chế phát việc sau commit |
| Yêu cầu HTTP làm việc nền ngắn và không cần bền vững | Tùy SLA | Thông báo rõ nếu không nhận; không trả thành công giả |

### Một state machine tối thiểu cho job cần bảo đảm

Một hệ thống có lưu trữ job có thể có trạng thái:

~~~text
RECEIVED -> PENDING -> RUNNING -> SUCCEEDED
                     \-> FAILED_RETRYABLE -> PENDING
                     \-> FAILED_FINAL
~~~

Nếu từ chối trước khi lưu và trước khi nhận job, phản hồi phải nêu rõ **NOT_ACCEPTED/REJECTED** hoặc equivalent của API. Nếu ghi bền vững thành công nhưng executor đang đầy, job vẫn có thể ở **PENDING** để worker về sau lấy lại; đó là một kiến trúc khác với enqueue in-memory đơn thuần.

Với thay đổi database và phát tác vụ cần nhất quán, cân nhắc **transactional outbox**: ghi dữ liệu nghiệp vụ và thông điệp outbox trong cùng transaction; worker/dispatcher gửi về sau và chỉ đánh dấu hoàn tất khi có chứng cứ. Đây là một giải pháp phổ biến để giảm rủi ro mất việc giữa commit và submit. Handler vẫn có thể retry nên consumer phải xử lý idempotency theo business key/job ID.

**Đừng đồng nhất retry với an toàn:** nếu một job đã chạy một phần rồi crash, retry có thể lặp hành động bên ngoài. Thiết kế idempotency, deduplication và trạng thái bền vững quan trọng hơn một vòng lặp gọi lại `execute`.

## 10. Retry và backpressure: kiểm soát tải thay vì tạo bão retry

Khi chính sách báo rejection, có nhiều lựa chọn tùy mức quan trọng:

1. **Fail fast:** trả lỗi bận cho caller (ví dụ 503), kèm thông tin retry khi có cơ sở. Dễ bảo toàn tài nguyên và không che giấu giới hạn.
2. **Retry có hạn:** dùng số lần tối đa, deadline, backoff và jitter; chỉ retry khi hợp đồng cho phép và tác vụ có tính idempotent phù hợp. Tránh giữ request thread quá lâu trong lúc chờ.
3. **Durable queue / database job table:** xác nhận sau khi đã persist; một worker riêng rút backlog theo năng lực thực thi. Cần vận hành, monitoring và cơ chế xử lý dead-letter/failure.
4. **Caller-runs backpressure:** chấp nhận chuyển độ trễ sang caller; phù hợp một số batch producer nhưng không nên dùng tùy tiện cho request handler nhạy latency hoặc event-loop.
5. **Giới hạn ngay từ nguồn:** rate limiting, bounded input queue, semaphore/permit, kiểm soát concurrency của upstream, circuit breaker cho dependency. Tính được tốc độ cung cấp việc và tốc độ hoàn thành hữu ích hơn cố tăng số thread không giới hạn.

Ví dụ đánh giá năng lực sơ bộ: nếu có 4 worker và mỗi tác vụ trung bình giữ worker 200 ms, **mức hoàn thành lý thuyết** khoảng 20 tác vụ/giây khi mọi worker luôn hữu dụng, chưa tính overhead và phân phối đuôi độ trễ. Nếu bên gửi đẩy 100 tác vụ/giây liên tục, queue 20 sẽ đầy nhanh; tăng queue chỉ trì hoãn rejection trong khi latency tăng. Trong thực tế phải đo thời gian thực thi và phân phối p95/p99, không lấy phép tính đơn giản làm sizing cuối cùng.

Cần lưu ý `CallerRunsPolicy` khi executor shutdown: theo hợp đồng JDK, handler có thể **bỏ tác vụ mà không chạy**, do đó chính sách này không giải quyết bài toán dừng nhận việc một cách chắc chắn. Nếu yêu cầu luôn báo lỗi lúc shutdown, ưu tiên `AbortPolicy` hoặc custom handler ném lỗi rõ ràng.

## 11. Shutdown và cạnh tranh đúng lúc ngừng nhận việc

Tình huống khó không chỉ xuất hiện ở giờ cao điểm. Khi Spring ApplicationContext đóng, executor có thể không nhận thêm task dù request vẫn đang tới hoặc một component khác còn đang dispatch. Ngoài rejection, những task **đã được nhận nhưng còn nằm trong queue** có được chạy tiếp hay bị hủy phụ thuộc vào chính sách shutdown.

Cần phân biệt:

- **Không nhận task mới:** signal rejection nếu dùng chính sách throw.
- **Task đã queue nhưng chưa chạy:** có thể hoàn tất, bị hủy hoặc bị dừng tùy vòng đời; acceptance chưa phải completion.
- **Task đang chạy:** có thể bị interrupt hoặc được phép hoàn thành khi graceful shutdown, tùy cấu hình.
- **Job bền vững:** có thể hồi phục sau restart nếu trạng thái và giao thức re-drive được thiết kế đúng.

`ThreadPoolTaskExecutor` có các cấu hình về chờ task hoàn thành lúc shutdown và khoảng đợi terminate (ví dụ `setWaitForTasksToCompleteOnShutdown` và `setAwaitTerminationSeconds`). Cần đọc đúng phiên bản Spring và chọn theo ngân sách shutdown thực tế của hạ tầng. Không nên tự gọi `shutdownNow()` trên Spring-managed bean bất kỳ lúc nào chỉ để “giải phóng tài nguyên”.

### Đường ranh giới với `@Transactional`

Một tác vụ chạy trên worker thread không tự động thừa hưởng transaction database đang gắn với thread gửi. Nếu gửi việc trước khi transaction chính commit, worker có thể đọc dữ liệu chưa commit hoặc sự kiện nghiệp vụ cuối cùng bị rollback. Khi cần ngữ nghĩa “sau commit”, dùng after-commit integration hoặc outbox, tùy yêu cầu độ bền. Tránh dùng JVM executor làm nguồn sự thật cho giao dịch xuyên tiến trình.

## 12. Observability: biết vì sao và khi nào bị reject

Nếu chỉ log mỗi lần ném exception mà không đo tình trạng pool, rất khó quyết định nên giảm tải hay tăng năng lực. Một bộ quan sát có ích:

- **Rejection count/rate** theo executor, loại task, lý do bão hòa/shutdown nếu xác định được; tránh gắn label job ID gây nổ cardinality.
- **Pool size / active threads**, **queue size / capacity** và số job đang chờ. `ThreadPoolTaskExecutor` cung cấp `getPoolSize()`, `getActiveCount()` và `getQueueSize()` để quan sát.
- **Queue wait time**, thời gian chạy task, throughput, timeout, cancelled, retry và số job lỗi cuối cùng.
- **Thread pool/queue utilization** đi cùng p95/p99 response time của API, tỷ lệ 429/503 và độ trễ hệ thống downstream.
- **Shutdown/cancel events** để phân biệt rejection do tải cao với rejection do vòng đời.

Trong hệ dùng Micrometer/Actuator, có thể instrument executor và publish các metrics phù hợp; đừng giả định mọi cấu hình Spring đều tự xuất đủ mọi chỉ số. Nếu viết custom rejection counter, chú ý code có thể chạy trên caller thread: metric nên rẻ, không gây blocking kéo dài.

Một log lỗi có ích thường chứa tên executor, loại công việc, correlation ID hoặc job ID an toàn, lý do quan sát được, kích thước queue/active thread và quyết định fallback. Tránh log toàn bộ nội dung tác vụ hoặc thông tin cá nhân.

## 13. Kiểm thử rejection đúng cách

**Không dùng `Thread.sleep(100)` để “hy vọng pool đầy”.** Scheduler và máy CI có thể khác nhau. Hãy dùng latch như ví dụ JDK để kiểm soát chính xác lúc worker đang bận và queue đã chứa task.

Các kịch bản nên có:

| Kịch bản | Điều cần chứng minh |
| --- | --- |
| Pool cấu hình 1 worker, queue 1, giữ task đầu bằng latch rồi gửi task thứ ba | `AbortPolicy` báo rejection; trong Spring bắt `TaskRejectedException` |
| Pool còn capacity | Task được nhận; không kết luận task đã hoàn thành chỉ từ việc `execute` trả về |
| Pool đã shutdown | Gửi mới bị từ chối theo policy đã chọn; không có success giả |
| Task đã nhận rồi ném lỗi trong body | Không bị gắn nhầm nhãn “rejected”; quan sát bằng future/status/error handler |
| `CallerRunsPolicy` dưới tải | Task thứ ba chạy trên caller thread; latency tăng; không vượt ràng buộc capacity theo cách của pool |
| `DiscardPolicy`/`DiscardOldestPolicy` | Chứng minh đường mất tác vụ và đánh giá hợp đồng quan sát/cancel để không chờ future vô hạn |
| Nhiều request đồng thời | Không có vòng retry vô hạn, không mất đơn hàng im lặng, metric phản ánh rejection |
| Graceful shutdown và restart | Job bền vững không mất; worker xử lý lại được và idempotency vẫn đúng |

Đối với integration test của Spring, khởi tạo `ThreadPoolTaskExecutor` có `core=1, max=1, queue=1`, đặt `AbortPolicy`, rồi dùng cùng chiến lược latch. Nếu tự khởi tạo executor trong test, nhớ `initialize()` và đóng nó trong `finally`; nếu dùng bean do Spring quản lý, để container đảm nhiệm vòng đời. Trong test HTTP, assert đúng response/status và không đánh dấu “accepted” khi submit bị reject.

## 14. Những lỗi triển khai thường gặp

1. **Nuốt `TaskRejectedException` rồi trả HTTP 200/202 vô điều kiện.** Caller tưởng đã giao việc; phải làm rõ nghĩa của accepted và thông báo no-capacity.
2. **Mặc định queue không giới hạn, chờ overload tự biến mất.** Đây thường biến từ chối sớm thành tồn đọng tăng dần và có nguy cơ thiếu bộ nhớ.
3. **Tăng `maxPoolSize` nhưng giữ queue rất lớn.** Pool có thể vẫn dừng ở mức core vì task đi vào queue trước.
4. **Bắt lỗi trong `Runnable.run()` để xử lý rejection.** Lỗi từ chối xảy ra lúc gửi, trước khi Runnable có cơ hội chạy.
5. **Dùng `@Async void` rồi cho rằng `AsyncUncaughtExceptionHandler` bắt luôn mọi rejection khi dispatch.** Submission failure và body failure là hai đường khác nhau.
6. **Dùng `CallerRunsPolicy` trong request/event-loop mà không tính độ trễ.** Tải cao có thể khiến logic nặng chạy ngay trong thread của người gọi, phá kỳ vọng phản hồi nhanh.
7. **Dùng `DiscardPolicy` cho công việc có nghĩa vụ phải hoàn thành.** Việc mất task trở nên im lặng, khó khôi phục; có thể khiến future treo.
8. **Retry liên tục trong `catch`.** Khi pool đầy, retry nóng làm CPU/logging tăng và cản hệ thống hồi phục.
9. **Cho rằng có `Future` tức task nhất định đã được xử lý.** Future thể hiện pending completion, không tự bảo đảm durability hoặc completion nếu task bị bỏ qua.
10. **Dùng queue in-memory thay cho job store sau khi đã hứa với khách hàng.** Restart hoặc shutdown có thể làm mất việc chưa chạy.
11. **Không ghi nhận rejection metric.** Không phân biệt tải vượt thiết kế, shutdown hay lỗi cấu hình.
12. **Test bằng timing ngẫu nhiên.** Dùng latch/barrier để khóa interleaving và assert chính xác rejection.
13. **Cấu hình executor ở một bean nhưng `@Async` dùng executor khác.** Dùng qualifier `@Async("exportExecutor")` khi cần chọn cụ thể, và kiểm chứng đường gọi qua proxy.
14. **Tưởng transaction từ thread submit tự chảy sang thread worker.** Cần thiết kế đường lưu trạng thái, after-commit hoặc outbox phù hợp.

## 15. Tình huống áp dụng

**Tình huống A — tạo báo cáo nặng:** pool dành cho report có `core=2, max=4, queue=20`. Request số 27 đến khi cả worker và queue vẫn đang bận theo ngưỡng không được nhận. API không nên trả “báo cáo đang xử lý” khi không có job ID bền vững. Có thể trả 503 cho caller retry có giới hạn; tốt hơn, nếu phải đảm bảo xử lý, persist job trước và để worker xử lý backlog theo tốc độ của mình.

**Tình huống B — log/telemetry không quan trọng:** bỏ một số event khi quá tải có thể được phép, nhưng cần theo dõi drop rate và chấp nhận được mất dữ liệu. `DiscardPolicy` không phù hợp nếu dashboard hoặc hệ thống cảnh báo đang mặc định mọi event được thu đủ.

**Tình huống C — batch producer:** một producer chuyên dụng tạo task nhanh hơn pool hoàn tất. `CallerRunsPolicy` có thể giảm tốc producer vì khi pool bão hòa producer phải tự chạy task, nhưng cách đó đổi mô hình latency, thread context và xử lý shutdown. Chỉ dùng khi người sở hữu producer chấp nhận những thay đổi đó.

**Tình huống D — shutdown rolling deployment:** một instance bắt đầu ngừng nhận việc nhưng request vẫn đến. `TaskRejectedException` báo cần định tuyến sang instance khác hoặc trả unavailable; nếu job đã lưu trong database/message queue thì worker khác có thể tiếp tục. Chỉ một `ThreadPoolTaskExecutor` nội bộ không tạo được cơ chế chuyển giao giữa các replica.

## 16. Tự kiểm tra

1. `TaskExecutor.execute` trả bình thường có luôn đồng nghĩa “task chắc chắn hoàn thành”? Cấu hình nào có thể làm nó thậm chí không được đưa vào queue?
2. Với `corePoolSize=2, maxPoolSize=4, queueCapacity=3`, vì sao task thứ ba thường được đưa vào queue thay vì làm pool tăng ngay lên 3 worker?
3. Vì sao một Spring `ThreadPoolTaskExecutor` với `AbortPolicy` báo `TaskRejectedException`, trong khi JDK `ThreadPoolExecutor` trực tiếp thường báo `RejectedExecutionException`?
4. Vì sao `CallerRunsPolicy` có thể làm thời gian phản hồi HTTP tăng mạnh? Điều gì xảy ra khi pool đã shutdown?
5. Lỗi do `Runnable.run()` ném và lỗi `TaskRejectedException` khác nhau về thời điểm và đường quan sát thế nào?
6. Tại sao gửi việc trong transaction chưa commit có thể khiến worker đọc trạng thái sai?
7. Khi API trả 202 Accepted, cần thêm những thành phần nào để hứa job không bị mất qua restart?
8. Hãy thiết kế integration test không dùng `Thread.sleep()` để chứng minh queue 1 + worker 1 có thể từ chối task thứ ba.

## 17. Tài liệu tham khảo chính thức

- [Spring Framework — TaskExecutor API (6.1)](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/core/task/TaskExecutor.html)
- [Spring Framework — TaskRejectedException API (6.1)](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/core/task/TaskRejectedException.html)
- [Spring Framework — ThreadPoolTaskExecutor API (6.1)](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html)
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html)
- [Java SE 17 — ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)
- [Java SE 17 — RejectedExecutionHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/RejectedExecutionHandler.html)

**Nguyên tắc thực hành:** Một executor hữu hạn cần có **chính sách từ chối rõ ràng**, ranh giới xử lý rejection có thể quan sát được, và hợp đồng nói chính xác caller nhận lại điều gì. “Đã gửi vào pool” chỉ là bước đầu; độ bền, kết quả và retry thuộc trách nhiệm kiến trúc của ứng dụng.