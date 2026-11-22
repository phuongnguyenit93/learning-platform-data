# corePoolSize và maxPoolSize

## 1. Bối cảnh: vì sao một thread pool cần hai giới hạn?

Trong ứng dụng Spring Framework, `ThreadPoolTaskExecutor` thường nhận nhiều tác vụ từ controller, service, listener hoặc phương thức `@Async`. Mỗi tác vụ cần một thread để chạy, nhưng số thread đang thực thi không nên tăng vô hạn. Hai thuộc tính quan trọng nhất của pool là:

- **`corePoolSize`**: ngưỡng số worker lõi mà pool ưu tiên tạo khi nhận tác vụ. Theo chính sách thông thường, các thread lõi được giữ lại khi rảnh, trừ khi bật `allowCoreThreadTimeOut`.
- **`maxPoolSize`**: **giới hạn trên** số worker mà pool được tạo để xử lý tải; nó chỉ phát huy vai trò mở rộng khi cơ chế xếp hàng không nhận thêm tác vụ.

Hai con số phải được hiểu cùng **`queueCapacity`**. Nếu không xét hàng đợi, rất dễ tưởng `corePoolSize=2, maxPoolSize=10` nghĩa là cứ nhiều tác vụ thì pool sẽ tự chạy đồng thời tới 10 thread. Với hàng đợi còn chỗ, `ThreadPoolExecutor` thường **ưu tiên xếp hàng sau khi đạt core**, nên không tạo thêm thread tới max.

Bài này tập trung vào `ThreadPoolTaskExecutor` của Spring và cơ chế `java.util.concurrent.ThreadPoolExecutor` bên dưới. Những nguyên tắc đó không áp dụng nguyên xi cho mọi `TaskExecutor` khác: ví dụ `SyncTaskExecutor` không có thread pool để cấu hình hai thuộc tính này.

## 2. Ý nghĩa chính xác của từng thuộc tính

| Thuộc tính | Vai trò | Điều dễ hiểu nhầm |
| --- | --- | --- |
| `corePoolSize` | Ngưỡng worker lõi: khi nhận task và số worker thấp hơn core, pool ưu tiên tạo worker | Không có nghĩa khi khởi động bean đã tồn tại sẵn từng ấy thread |
| `maxPoolSize` | Số worker tối đa pool được phép có tại một thời điểm | Không có nghĩa pool sẽ lập tức đạt tới max khi core bận |
| `queueCapacity` | Số task có thể chờ trong hàng đợi (không tính task đang chạy) | Không phải giới hạn số task đang chạy hoặc tổng số task trong toàn hệ thống |
| `keepAliveSeconds` | Thời gian worker **vượt core** có thể tiếp tục rảnh trước khi bị thu hồi | Không phải timeout của mỗi task |
| `allowCoreThreadTimeOut` | Khi bật, cho phép cả worker lõi rút lui sau thời gian rảnh | Không làm tăng `maxPoolSize` hoặc thay đổi quy tắc queue |

Các điểm cần nhớ:

1. `0 <= corePoolSize <= maxPoolSize`, và `maxPoolSize >= 1` trong `ThreadPoolExecutor` JDK. Cấu hình `core > max` không hợp lệ.
2. `corePoolSize` **không phải số thread luôn tồn tại ngay từ đầu**. Core worker thường được tạo khi có tác vụ; `prestartAllCoreThreads` là lựa chọn riêng để tạo trước.
3. `maxPoolSize` là trần thread, **không phải trần độ dài hàng đợi** và cũng không phải mục tiêu số thread cần đạt.
4. Worker đang rảnh vượt `corePoolSize` có thể bị thu hồi sau `keepAliveSeconds`. Worker lõi mặc định được giữ khi idle, trừ khi `allowCoreThreadTimeOut=true`.

Theo JavaDoc của Spring `ThreadPoolTaskExecutor`, giá trị mặc định của **chính class này** là `corePoolSize=1`, `maxPoolSize=Integer.MAX_VALUE`, `queueCapacity=Integer.MAX_VALUE`. Vì queue thực tế rất lớn, thiết lập mặc định thường vận hành gần giống một executor chạy một tác vụ tại một thời điểm. **Đừng nhầm mặc định này với executor được Spring Boot tự cấu hình**: Boot có thể dùng giá trị khác theo phiên bản và cấu hình ứng dụng.

## 3. Core và max phải được đọc cùng queueCapacity

Hai giới hạn worker không hoạt động độc lập: khi chưa đủ core workers, executor ưu tiên tạo worker; sau khi tới core, nó thử đưa task vào queue; chỉ khi queue không nhận mới thử mở rộng đến max, rồi áp dụng rejection policy nếu cũng không thể mở rộng. Với queue đủ lớn, rất nhiều task có thể chờ mà pool chưa dùng đến max.

Bài này sử dụng quy tắc trên để **tính số worker theo hai ngưỡng**. Thuật toán nhận việc đầy đủ, kiểm tra khi shutdown và tình huống task đến sau chạy trước task cũ được trình bày ở bài “Thứ tự nhận tác vụ: tạo luồng cơ bản, xếp hàng, mở rộng rồi từ chối”. Bảng mô phỏng và chương trình bên dưới sẽ kiểm chứng ảnh hưởng của core/max.

## 4. Mô phỏng với core=2, max=4, queueCapacity=2

Giả sử các task đều giữ thread bận và không hoàn tất trong lúc gửi lần lượt bảy tác vụ. Đặt:

```text
corePoolSize  = 2
maxPoolSize   = 4
queueCapacity = 2
```

Quá trình nhận việc diễn ra như sau:

| Tác vụ mới | Số worker sau khi nhận | Số task chờ queue | Giải thích |
| --- | ---: | ---: | --- |
| Task 1 | 1 | 0 | Dưới core nên tạo worker thứ nhất |
| Task 2 | 2 | 0 | Dưới core nên tạo worker thứ hai |
| Task 3 | 2 | 1 | Đã đạt core, queue còn chỗ |
| Task 4 | 2 | 2 | Queue đầy |
| Task 5 | 3 | 2 | Queue đầy, còn dưới max nên thêm worker |
| Task 6 | 4 | 2 | Thêm worker cuối cùng tới max |
| Task 7 | 4 | 2 | Pool và queue đều đầy, bị từ chối theo chính sách mặc định |

Hình dung trạng thái ngay trước Task 7:

```text
Đang thực thi:  [worker-1: task-1] [worker-2: task-2]
                [worker-3: task-5] [worker-4: task-6]
Queue đang chờ: [task-3] [task-4]
Task mới tới:   [task-7]  --> REJECTED (mặc định)
```

Tổng **sức chứa tức thời trong tình huống này** là tối đa 4 task đang chiếm thread cộng 2 task đang chờ = 6 task, với giả định tất cả tác vụ đều chặn và không có task nào kết thúc khi đang submit. **Không có công thức `max + queue` cho throughput hoặc sức chứa cố định trong mọi thời điểm**: task có thể kết thúc, worker mới nhận việc, queue rút ngắn và đợt task mới lại được nhận.

Khi hai worker vượt core hết việc và rảnh đủ lâu, chúng có thể bị thu hồi về gần mức core. Không thể kết luận `poolSize` lúc nào cũng là 4 chỉ từ cấu hình `maxPoolSize=4`.

## 5. Ví dụ Java 17+ chạy được và có kết quả xác định

Để thấy rõ từng ngưỡng, chương trình dưới đây dùng `ThreadPoolExecutor` JDK với cùng chiến lược lập lịch mà `ThreadPoolTaskExecutor` bao quanh. Một `CountDownLatch` giữ cả sáu task đầu chưa hoàn thành, vì vậy các con số được in không phụ thuộc vào việc CPU chạy nhanh hay chậm.

Tạo tệp `PoolSizingDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Future;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public final class PoolSizingDemo {
    public static void main(String[] args) throws Exception {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                2, 4, 30, TimeUnit.SECONDS, new ArrayBlockingQueue<>(2));

        CountDownLatch release = new CountDownLatch(1);
        List<Future<?>> accepted = new ArrayList<>();

        try {
            for (int i = 0; i < 6; i++) {
                accepted.add(pool.submit(() -> {
                    release.await(); // Giữ worker bận cho tới khi main cho phép.
                    return null;
                }));
            }

            System.out.println("poolSize = " + pool.getPoolSize());
            System.out.println("queued = " + pool.getQueue().size());

            try {
                pool.submit(() -> {
                    release.await();
                    return null;
                });
                System.out.println("rejected = false");
            } catch (RejectedExecutionException ex) {
                System.out.println("rejected = true");
            }
        } finally {
            release.countDown(); // Không để các worker bị giữ mãi.
            pool.shutdown();
        }

        for (Future<?> future : accepted) {
            future.get(); // Chỉ tiếp tục khi cả sáu task kết thúc.
        }
        System.out.println("completed = " + accepted.size());

        if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Pool did not terminate");
        }
    }
}
```

Chạy:

```bash
javac PoolSizingDemo.java
java PoolSizingDemo
```

Stdout chính xác của ví dụ:

```text
poolSize = 4
queued = 2
rejected = true
completed = 6
```

Giải thích:

- Sáu lần `submit` đầu đều được nhận. Hai task đầu tạo core workers, hai task tiếp theo vào queue, hai task cuối làm pool mở rộng lên 4 workers.
- Vì `release` chưa được hạ, **không worker nào hoàn tất**, nên lúc đo luôn có 4 worker và 2 phần tử queue.
- Task thứ bảy bị từ chối bằng `RejectedExecutionException` theo `AbortPolicy` mặc định của JDK.
- Khối `finally` thả latch và yêu cầu dừng pool. `Future.get()` chứng minh sáu tác vụ được nhận đã kết thúc trước dòng cuối.

Ví dụ này dùng JDK độc lập để tránh phải khởi chạy Spring chỉ nhằm quan sát thuật toán. Trong Spring, `ThreadPoolTaskExecutor` dùng `ThreadPoolExecutor` tương ứng, nhưng exception khi giao việc bị từ chối theo hợp đồng Spring thường là `TaskRejectedException`.

## 6. Cấu hình trong Spring Framework

Trong một ứng dụng Spring-managed, có thể định nghĩa bean với ba tham số cùng quyết định hành vi:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
public class WorkerPoolConfig {
    @Bean("workerPool")
    public ThreadPoolTaskExecutor workerPool() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(2);
        executor.setKeepAliveSeconds(30);
        executor.setThreadNamePrefix("worker-");
        return executor;
    }
}
```

Đây là **class cấu hình Spring**, cần project có thư viện `spring-context` tương thích với JDK đang dùng và được container quét/đăng ký. Không thể biên dịch riêng class này chỉ bằng JDK thuần. Khi bean do Spring quản lý, container thực hiện lifecycle khởi tạo và hủy thích hợp; không cần gọi `initialize()` ngay trong phương thức `@Bean`.

Service có thể inject bằng interface:

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.core.task.TaskExecutor;
import org.springframework.stereotype.Service;

@Service
public class ReportService {
    private final TaskExecutor workerPool;

    public ReportService(@Qualifier("workerPool") TaskExecutor workerPool) {
        this.workerPool = workerPool;
    }

    public void requestReport(String id) {
        workerPool.execute(() -> generateReport(id));
    }

    private void generateReport(String id) {
        // Ví dụ: xử lý báo cáo theo mã id.
    }
}
```

Đây là **mảnh tích hợp trong Spring**; code nghiệp vụ dùng `TaskExecutor.execute`, còn chính sách số thread được cấu hình ở `WorkerPoolConfig`. `execute` không trả Future và có thể trở về trước khi task hoàn tất. Muốn lấy kết quả/lỗi của một tác vụ bất đồng bộ, dùng API có Future như `AsyncTaskExecutor.submit` hoặc thiết kế cơ chế hoàn tất rõ ràng.

Nếu ứng dụng dùng `@Async`, cần xác định phương thức thực sự sử dụng bean executor mong muốn (ví dụ `@Async("workerPool")` và lời gọi đi qua proxy). Thay đổi bean không tác động tới một `@Async` đang dùng executor khác.

## 7. Queue quyết định khi nào maxPoolSize có tác dụng

`ThreadPoolTaskExecutor.setQueueCapacity` chọn hàng đợi dựa trên giá trị:

### Queue có sức chứa dương

Với `queueCapacity > 0`, Spring dùng `LinkedBlockingQueue` có giới hạn tương ứng. Ví dụ `core=2, max=8, queue=100`: khi 2 thread lõi bận, task mới thường sẽ vào queue; chỉ khi queue 100 phần tử không nhận thêm tác vụ, pool mới có lý do tăng worker lên 3...8. Kích thước queue lớn giúp hấp thụ burst ngắn nhưng có thể tăng thời gian chờ.

### Queue mặc định rất lớn

Theo JavaDoc, `queueCapacity=Integer.MAX_VALUE` là mặc định của `ThreadPoolTaskExecutor`. Trong điều kiện thực tế, queue này thường không đầy trước khi tài nguyên hệ thống cạn, vì vậy `maxPoolSize` hiếm khi được dùng để mở rộng. Nếu đặt:

```java
executor.setCorePoolSize(2);
executor.setMaxPoolSize(20);
// Không đặt queueCapacity: vẫn dùng mặc định rất lớn.
```

thì *không thể* kỳ vọng pool thường tạo 20 worker dù có hàng trăm tác vụ chờ. Đây là một lý do phổ biến khiến việc “tăng max mà không thấy tăng số thread” xảy ra. Mảnh mã trên là **minh họa cấu hình một executor đã được tạo**.

### QueueCapacity bằng 0

Với `queueCapacity=0`, Spring sử dụng `SynchronousQueue`, tức cơ chế **bàn giao trực tiếp**, không lưu backlog trong queue. Khi không có worker sẵn sàng nhận tác vụ và chưa đạt max, pool có thể tạo thêm worker nhanh hơn. Vì vậy `maxPoolSize` có ảnh hưởng trực tiếp hơn tới số task chạy đồng thời.

Điều này cũng làm hệ thống chạm trần thread và từ chối task nhanh hơn nếu tải liên tục; nên đặt giới hạn max và chiến lược xử lý quá tải có chủ đích.

| Cấu hình | Khi đã có `core` worker bận | Khả năng mở rộng |
| --- | --- | --- |
| Queue rất lớn | Task tiếp tục chờ trong queue | Thường duy trì gần core |
| Queue dương, giới hạn nhỏ | Task chờ tới khi queue đầy | Sau đó tăng dần worker tới max |
| Queue bằng 0 | Cố bàn giao trực tiếp | Có thể mở thêm worker tới max nhanh hơn |

## 8. Thay đổi core và max ảnh hưởng gì tới hiệu năng?

**Tăng `corePoolSize`** có thể giúp xử lý đồng thời nhiều task sớm hơn và giảm thời gian đợi queue khi có tải liên tục. Nhưng quá nhiều thread với việc nặng CPU làm tăng chuyển ngữ cảnh, tranh chấp và độ trễ. Thread lõi cũng tiêu thụ tài nguyên khi rảnh.

**Tăng `maxPoolSize`** chỉ hữu ích nếu cơ chế queue thực sự cho phép mở rộng và hệ thống còn tài nguyên để thực thi thêm. Nếu mỗi task phải chờ một connection JDBC từ pool chỉ có 10 connections, việc tăng worker lên 100 thường chỉ tạo thêm nhiều thread chờ connection, có thể làm chậm hệ thống.

**Giảm `queueCapacity`** thường làm pool mở rộng sớm hơn nhưng cũng khiến saturation/rejection xảy ra sớm hơn khi đạt max. **Tăng queue** giúp chịu burst nhưng có thể biến thời gian chờ thành vấn đề khó thấy. Cả hai đều cần đo bằng lưu lượng, độ trễ và tài nguyên thực tế.

Để chọn cấu hình:

1. Xác định task chủ yếu dùng CPU, block I/O, chờ database hay gọi dịch vụ ngoài. Không có con số `core`/`max` dùng tốt cho mọi workload.
2. Đo lượng task đến, thời gian xử lý, thời gian đợi queue, độ trễ p95/p99, số worker đang hoạt động và số task bị từ chối dưới tải thực tế.
3. Giới hạn thread phù hợp với CPU, memory, connection pool, quota của dịch vụ ngoài và thời gian sống của tác vụ.
4. Chọn queue đủ hấp thụ biến động ngắn hạn mà không che giấu tình trạng quá tải lâu dài. Bổ sung chính sách giới hạn đầu vào/retry hoặc hàng đợi bền vững khi cần.
5. Load test theo các đợt burst và lúc tải kéo dài, quan sát sự ổn định thay vì chỉ đo throughput trong một lần thử.

Ví dụ có ý nghĩa: một task nặng CPU không thể tăng tốc vô hạn nhờ nhiều thread hơn số lõi CPU; một task thường chờ I/O có thể dùng nhiều worker hơn nhưng phải xét giới hạn connection và dịch vụ ngoài. Quyết định cuối cùng nên dựa trên phép đo.

## 9. Tương tác với keepAlive, timeout và cấu hình lúc chạy

`ThreadPoolTaskExecutor` cho phép thay đổi `corePoolSize`, `maxPoolSize` và `keepAliveSeconds` lúc runtime qua API quản lý thích hợp, với các điều kiện hợp lệ của `ThreadPoolExecutor`.

Những điểm cần nhớ:

- Worker **vượt core** thường có thể rút lui sau `keepAliveSeconds` rảnh; việc giảm từ max về core không cần chờ restart ứng dụng.
- Bật `setAllowCoreThreadTimeOut(true)` cho phép worker lõi cũng nghỉ khi rảnh đủ lâu; không làm tăng khả năng nhận task vượt max.
- Thay đổi `corePoolSize` hay `maxPoolSize` không có nghĩa ngay lập tức đúng từng ấy worker đang sống hoặc đang chạy task. Quan sát `getPoolSize()`, `getActiveCount()`, `getQueueSize()` để hiểu trạng thái hiện tại.
- **Không sửa `queueCapacity` như một núm vặn runtime thông thường.** Loại work queue được tạo khi executor khởi tạo; thay đổi giá trị cấu hình trên bean đã chạy không tự tạo lại queue hiện có.
- Khi thay đổi đồng thời hai giới hạn, luôn duy trì `core <= max`. Chẳng hạn muốn tăng core lên cao hơn max hiện tại, phải nâng max trước; muốn hạ max xuống thấp hơn core hiện tại, phải hạ core trước.

`getActiveCount()` và queue size là phép quan sát tại một thời điểm, có thể đổi ngay trong lúc đọc. Chúng thích hợp cho metric/trend, không nên dùng làm nền tảng duy nhất cho một thuật toán đồng bộ chính xác giữa các luồng.

## 10. Khi pool đạt giới hạn: rejection và khả năng xử lý lỗi

Nếu queue đã đầy, worker đã đạt max và executor không thể nhận thêm, Spring `ThreadPoolTaskExecutor` theo chính sách mặc định báo **`TaskRejectedException`** ở phía gọi `execute`/`submit`. Nó phản ánh **lỗi giao tác vụ**, khác với exception xảy ra *bên trong task sau khi đã được nhận*.

Minh họa phía gọi Spring:

```java
try {
    workerPool.execute(() -> process(data));
} catch (org.springframework.core.task.TaskRejectedException rejected) {
    // Phản hồi quá tải, retry có giới hạn hoặc chuyển sang cơ chế bền vững.
}
```

Đây là **mảnh code minh họa** giả sử `workerPool` và `process(data)` đã được định nghĩa. Khi `Runnable` chạy bất đồng bộ rồi ném exception, exception đó không tự nhảy về thread đã gọi `execute` trong `catch` ở trên. Nếu cần nhận kết quả, dùng Future hoặc cơ chế thông báo/lưu trạng thái riêng.

Không nên tự động chọn `CallerRunsPolicy` để “không bị mất task” mà bỏ qua hệ quả: chính sách ấy có thể khiến thread gọi (ví dụ request thread) chạy tác vụ và kéo dài độ trễ; khi pool đã shutdown, hành vi còn phụ thuộc hợp đồng policy. Tương tự, hàng đợi in-memory không giữ được task khi tiến trình chết đột ngột. Với nghiệp vụ cần delivery bền vững, cân nhắc messaging/queue có lưu trữ.

## 11. Những lỗi cấu hình thường gặp

1. **Chỉ tăng `maxPoolSize` mà không đổi queue.** Nếu queue còn rất rộng, pool không mở rộng; phải xét cả `queueCapacity`.
2. **Cho rằng `corePoolSize` là số thread có sẵn khi khởi tạo.** Core worker có thể được tạo lười; muốn prestart phải cấu hình riêng.
3. **Nhầm `maxPoolSize` với số task tối đa trong hệ thống.** Pool còn queue; task chờ không chiếm worker nhưng vẫn chiếm bộ nhớ và chịu độ trễ.
4. **Đặt `corePoolSize > maxPoolSize`.** Cấu hình không hợp lệ; khi chỉnh runtime cần giữ bất biến `core <= max`.
5. **Đặt queue quá lớn để không bị rejection.** Có thể che giấu backlog, tăng độ trễ và nguy cơ cạn bộ nhớ.
6. **Đặt `maxPoolSize` quá cao cho tác vụ phụ thuộc database/API.** Tăng số worker không tăng năng lực của dependency; chỉ tăng tranh chấp.
7. **Tin rằng mọi Spring `TaskExecutor` đều có cùng tham số.** `SyncTaskExecutor`, `SimpleAsyncTaskExecutor` và executor virtual thread có cơ chế khác.
8. **Thử tải không giữ task bận rồi kết luận pool không mở rộng.** Task quá nhanh có thể kết thúc trước khi queue đầy, nên cần kịch bản đo lường tái lập được.
9. **Không quan sát queue và rejection.** Chỉ nhìn CPU hoặc chỉ nhìn số thread không đủ biết backlog và chất lượng dịch vụ.
10. **Nhầm thread timeout với task timeout.** `keepAliveSeconds` áp dụng khi worker rảnh; nó không cắt task đang chạy lâu.
11. **Bỏ qua executor thực tế dùng bởi `@Async`.** Phải xác định bean được chọn trước khi giải thích vì sao cấu hình thay đổi mà luồng thực thi không đổi.

## 12. Tự kiểm tra và ghi nhớ

**Câu 1.** `core=2, max=12, queueCapacity=1000`, có 20 task đồng thời giữ thread bận. Pool thường tạo ngay bao nhiêu worker?  
**Đáp án:** Khoảng 2 worker lõi; 18 task còn lại có thể chờ trong queue còn rộng. Không có cơ sở để khẳng định pool sẽ tạo 12 worker ngay.

**Câu 2.** `core=2, max=4, queue=2`; sáu task được nhận và đều chưa kết thúc. Task thứ bảy sẽ ra sao với policy mặc định?  
**Đáp án:** Pool đang có 4 worker, queue 2 phần tử; task thứ bảy bị từ chối.

**Câu 3.** Giảm `queueCapacity` từ 100 xuống 0 có làm pool luôn chạy bằng `maxPoolSize`?  
**Đáp án:** Không. Queue 0 khiến việc bàn giao trực tiếp và tạo thêm worker xảy ra sớm hơn khi cần, nhưng số thread thực tế vẫn phụ thuộc lượng task, worker rảnh, max và trạng thái pool.

**Câu 4.** Tăng `maxPoolSize` có luôn làm task nặng CPU nhanh hơn?  
**Đáp án:** Không. Nhiều worker có thể gây tranh chấp, quá nhiều chuyển ngữ cảnh và độ trễ, đặc biệt khi vượt năng lực CPU.

**Câu 5.** Khi pool chạy xong một đợt tải cao, vì sao `poolSize` có thể giảm từ 4 về 2?  
**Đáp án:** Hai worker vượt core có thể rút lui sau thời gian rảnh `keepAliveSeconds` theo chính sách mặc định.

Khi phân tích một cấu hình Spring, hãy đọc **ba giá trị theo thứ tự `corePoolSize` → `queueCapacity` → `maxPoolSize`**. Chỉ sau khi hiểu ngưỡng xếp hàng mới suy luận đúng khi nào pool mở rộng và khi nào từ chối tác vụ.

### Tài liệu tham khảo

- [Spring Framework — ThreadPoolTaskExecutor JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html)
- [Java SE 17 — ThreadPoolExecutor JavaDoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
