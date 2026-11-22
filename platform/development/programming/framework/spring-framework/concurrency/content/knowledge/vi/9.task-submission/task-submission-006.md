# Thời điểm gửi tác vụ khác với thời điểm bắt đầu chạy

Trong ứng dụng Spring Framework, khi controller gọi một phương thức `@Async` hoặc service gửi `Runnable` qua `TaskExecutor.execute(...)`, lời gọi gửi tác vụ có thể hoàn tất **trước khi tác vụ bắt đầu thực thi**. Điều đó xảy ra khi executor nhận task vào hàng đợi nhưng chưa có worker rảnh. Ngược lại, một worker rảnh có thể bắt đầu chạy ngay trước khi phương thức gửi kịp trả về; một executor đồng bộ còn có thể chạy cả task trên thread gọi.

Vì vậy phải phân biệt **gửi tác vụ (submit)**, **được nhận (accept)**, **bắt đầu chạy (start)**, **hoàn tất (finish)** và **thời điểm caller nhận lại quyền điều khiển (return)**. Bài học giải thích cơ chế, hệ quả với `Future` và `@Async`, cách đo độ trễ chờ trong Spring và ví dụ Java 17 chạy độc lập.

## 1. Các mốc thời gian không đồng nghĩa nhau

~~~text
Caller                         Executor / queue                     Worker
  |                                   |                               |
  |---- execute(task) --------------->|                               |
  |       t_submit                    |                               |
  |                                   |-- accept / enqueue ---------->|
  |                                   |      t_accept                 |
  |<--- execute trả về ---------------|                               |
  |       t_return                    |                               |
  |                                   |  chờ worker rảnh              |
  |                                   |---- dispatch task ---------->|
  |                                   |                          t_start
  |                                   |                        chạy task
  |                                   |                          t_finish
~~~

Các mốc có ý nghĩa khác nhau:

1. **`t_submit`**: caller bắt đầu yêu cầu executor thực thi task (gọi `execute`/`submit` hoặc đi qua proxy `@Async`).
2. **`t_accept`**: executor nhận task, cho chạy ngay hoặc đưa vào queue. Không phải executor nào cũng cung cấp timestamp này qua API.
3. **`t_return`**: phương thức gửi trả quyền điều khiển cho caller. `execute(Runnable)` trả `void`, còn `ExecutorService.submit(...)` trả `Future` khi tác vụ được nhận.
4. **`t_start`**: worker bắt đầu chạy phần thực thi mà executor quản lý, ví dụ callback `Runnable.run()`.
5. **`t_finish`**: callback kết thúc, bình thường hoặc do exception; một `Future` còn có thể hoàn tất do cancellation.

Ba khoảng thời gian cần đo riêng:

| Khoảng thời gian | Phép đo gần đúng | Trả lời câu hỏi |
| --- | --- | --- |
| Thời gian gửi (*submission duration*) | `t_return − t_submit` | Caller tốn bao lâu để gửi yêu cầu? |
| Thời gian chờ trước khi chạy (*wait/queue latency*) | `t_start − t_submit` | Task được gửi bao lâu thì mới có worker chạy? |
| Thời gian chạy (*execution duration*) | `t_finish − t_start` | Worker mất bao lâu để thực thi callback? |
| End-to-end của task | `t_finish − t_submit` | Từ yêu cầu gửi tới khi task thực sự hoàn tất là bao lâu? |

Trong một pool có queue và workers đang bận, thứ tự thường thấy là `t_submit < t_return < t_start < t_finish`. Tuy nhiên **không có bảo đảm chung rằng `t_return` luôn trước `t_start`**: task rất ngắn có thể được worker chạy ngay trong lúc caller vẫn ở phương thức `execute`. Với `SyncTaskExecutor` hoặc `CallerRunsPolicy`, callback còn có thể thực thi **ngay trên caller trước khi `execute` trả về**.

**Sự khác biệt giữa submit và start là khái niệm, không phải lời hứa mọi task đều phải chờ queue.**

## 2. Vì sao gửi thành công nhưng task vẫn chưa chạy?

### 2.1. Worker đang bận, task chờ trong queue

Giả sử executor có một worker. Task A giữ worker 5 giây; task B được gửi sau khi A đã bắt đầu:

~~~text
Thời gian      0s          1s                  5s         5,1s
               |-----------|-------------------|-----------|
Worker:        [================ Task A =======][ Task B ]
Caller:        submit A    submit B -> trả về
Queue:                     [ B chờ .............]
                           ^                   ^
                           đã gửi              B mới bắt đầu
~~~

Từ góc nhìn caller, `submit(B)` có thể trả về rất nhanh. Từ góc nhìn B, nó phải chờ nhiều giây mới được chạy. Nếu chỉ ghi log thời gian thực thi *bên trong* method B, hệ thống có thể báo “B chạy 100 ms”, dù người dùng thấy độ trễ hơn 4 giây.

### 2.2. Thứ tự tiếp nhận trong ThreadPoolExecutor

`ThreadPoolTaskExecutor` của Spring thường bọc `ThreadPoolExecutor` của Java, với thứ tự cơ bản:

1. Nếu số worker hiện có nhỏ hơn `corePoolSize`, thử tạo worker mới cho task.
2. Nếu đã đạt core, thử đưa task vào queue.
3. Nếu queue không nhận được, thử mở worker mới đến `maxPoolSize`.
4. Nếu không thể nhận, hoặc executor đã shutdown, task bị từ chối theo policy.

Vì **queue được ưu tiên sau core**, đặt `maxPoolSize=16` không có nghĩa task thứ ba sẽ lập tức chạy trên worker #3 khi `corePoolSize=2` và queue vẫn còn chỗ. Với queue rất lớn, pool có thể giữ gần core workers dù task chờ ngày càng nhiều. Queue không giới hạn về mặt cấu hình còn có thể tích tụ công việc đến mức tăng thời gian chờ và tiêu thụ bộ nhớ.

Ngược lại, với `queueCapacity=0` ở `ThreadPoolTaskExecutor`, Spring dùng `SynchronousQueue` để bàn giao trực tiếp; khi không có worker nhận task và pool dưới max, nó có thể tạo worker mới. Vì thế **độ trễ start phụ thuộc cả queue, core, max, tốc độ hoàn thành và tải thực tế**, không chỉ một tham số.

### 2.3. Worker bị chặn không có nghĩa CPU đang bận

Worker vẫn chiếm một slot của pool khi nó chờ JDBC connection, HTTP response, lock hoặc `Future.get()`. Nếu nhiều worker bị chặn I/O, queue wait có thể tăng dù CPU không cao. Muốn xử lý đúng phải phân biệt bão hòa CPU, worker thiếu do blocking và downstream cạn tài nguyên.

## 3. Java 17: chương trình xác nhận submit B trước khi start B

Tạo tệp **`SubmissionVsStartDemo.java`**. Chương trình dùng một worker và các `CountDownLatch` để tạo thứ tự xác định, không cần đoán thời gian bằng `Thread.sleep(...)`:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class SubmissionVsStartDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch firstStarted = new CountDownLatch(1);
        CountDownLatch releaseFirst = new CountDownLatch(1);
        CountDownLatch secondStarted = new CountDownLatch(1);
        try {
            Future<?> first = pool.submit(() -> {
                firstStarted.countDown();
                try {
                    releaseFirst.await();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                }
            });
            if (!firstStarted.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("First task did not start");
            }
            System.out.println("1. Task A started");
            Future<?> second = pool.submit(() -> {
                secondStarted.countDown();
                System.out.println("4. Task B started");
            });
            System.out.println("2. Task B submitted");
            System.out.println("3. Task B started yet? "
                    + (secondStarted.getCount() == 0));
            releaseFirst.countDown();
            first.get(5, TimeUnit.SECONDS);
            second.get(5, TimeUnit.SECONDS);
            System.out.println("5. Task B completed");
        } finally {
            releaseFirst.countDown();
            pool.shutdownNow();
        }
    }
}
~~~

Chạy với JDK 17 trở lên:

~~~bash
javac --release 17 SubmissionVsStartDemo.java
java SubmissionVsStartDemo
~~~

Stdout đã xác minh bằng cách biên dịch với `--release 17` và chạy chương trình:

~~~text
1. Task A started
2. Task B submitted
3. Task B started yet? false
4. Task B started
5. Task B completed
~~~

Giải thích từng bước:

- `firstStarted.await(...)` xác nhận task A đã bắt đầu trên worker duy nhất.
- A chờ `releaseFirst`, vì vậy worker chưa thể chuyển sang B.
- `submit(B)` trả về một `Future<?>` khi B được nhận. Dù vậy, B đang **nằm trong queue**.
- Khi kiểm tra `secondStarted.getCount()`, main chưa nhả A nên B chắc chắn chưa bắt đầu; dòng thứ ba in `false`.
- Sau `releaseFirst.countDown()`, A có thể thoát; worker chạy B và in dòng thứ tư.
- `second.get(...)` chờ B hoàn tất, rồi main mới in dòng thứ năm.

`CountDownLatch` khiến quan sát có tính xác định. Không suy luận mối quan hệ submit/start bằng cách chỉ thêm `Thread.sleep(10)` trong bài test: sự thay đổi tải CPU và lịch OS dễ làm loại test đó chập chờn.

### 3.1. Future không phải timestamp bắt đầu

| Trạng thái Future | Có thể kết luận | Không thể kết luận |
| --- | --- | --- |
| `isDone() == false` | Task chưa đạt trạng thái hoàn tất | Task còn ở queue hay đang chạy |
| `isDone() == true` | Task đã hoàn tất theo hợp đồng Future (có thể thành công, lỗi hoặc hủy) | Task bắt đầu khi nào, mất bao lâu để chờ |
| `isCancelled() == true` | Future đã bị hủy | Side effect trước đó đã được hoàn tác |
| `get()` trả giá trị | Task hoàn thành thành công với giá trị đó | Thời gian queue wait |
| `get(timeout)` ném `TimeoutException` | Caller chờ quá thời hạn cho phép | Task tự động bị dừng |

Khi cần biết `t_start`, phải đo ở đầu callback hoặc dùng instrumentation của executor. `Future.get(timeout)` chỉ giới hạn lượt **chờ của caller**, không mặc nhiên đặt deadline cho công việc đang chờ hoặc đang thực thi.

## 4. Trong Spring, @Async cũng chỉ là yêu cầu chuyển việc sang executor

Ví dụ **mã tích hợp Spring Framework 6.x, Java 17+** (cần dependencies Spring, component scanning và `@EnableAsync`):

~~~java
package example.concurrency;

import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class ReportWorker {
    @Async("reportExecutor")
    public CompletableFuture<String> generate(String reportId) {
        // Logic thực tế bắt đầu khi worker của executor chạy lời gọi này.
        return CompletableFuture.completedFuture("ready:" + reportId);
    }
}
~~~

Caller ở một bean khác:

~~~java
CompletableFuture<String> result = reportWorker.generate("R-101");
// Lúc này task có thể đang chờ, đang chạy hoặc đã hoàn tất.
~~~

Đoạn caller giả định `reportWorker` đã được inject từ Spring context và lời gọi đi qua proxy. Tại thời điểm nhận `result`, **không có bằng chứng rằng method body đã bắt đầu**. Nếu caller lập tức gọi `result.join()` hoặc `get()`, caller sẽ phải chờ kết quả, làm nó mất khả năng tiếp tục công việc khác trong thời gian đó.

Điều kiện để `@Async` hoạt động đúng:

- Có `@EnableAsync` hoặc cơ chế kích hoạt tương đương.
- Có bean executor được chỉ rõ qua `@Async("reportExecutor")` và bean thực sự được Spring quản lý.
- Lời gọi đi **qua Spring proxy**. Trong chế độ proxy mặc định, gọi `this.generate(...)` từ cùng bean sẽ bỏ qua interceptor async và có thể chạy đồng bộ.
- Caller theo dõi cả **lỗi ở bước submit** (ví dụ pool từ chối) lẫn **lỗi trong lúc task đã bắt đầu chạy**. Future có thể biểu diễn lỗi thực thi; exception từ method `@Async` trả `void` cần cách xử lý riêng.

Điểm nữa: worker rảnh có thể bắt đầu chạy trước lúc lời gọi proxy trả về, nhất là với task ngắn. Do đó không nên suy luận “method body không thể bắt đầu trước khi caller có Future”.

## 5. Cấu hình pool Spring có queue để thấy khoảng chờ

Ví dụ một cấu hình bean rõ ràng:

~~~java
package example.concurrency;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
public class AsyncExecutorConfiguration {
    @Bean("reportExecutor")
    public ThreadPoolTaskExecutor reportExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(10);
        executor.setThreadNamePrefix("report-");
        return executor;
    }
}
~~~

Đây là **tệp tích hợp Spring**, không biên dịch độc lập bằng một lệnh `javac` thiếu classpath Spring. Spring quản lý lifecycle và khởi tạo bean executor khi được đăng ký bình thường trong ApplicationContext.

Giả sử hai core workers đều bận với công việc dài, queue còn chỗ. Tác vụ mới gửi đến có thể được **enqueue** và caller nhận lại quyền điều khiển, trong khi task thực tế chờ worker. Khi queue đầy, pool mới có thể tăng tới max=4; khi cả worker và queue đều không nhận được, nó có thể từ chối.

Số 2/4/10 chỉ là ví dụ. Pool thật phải được sizing theo CPU, thời gian I/O, connection pool, throughput, p95/p99 và tải đỉnh. Queue quá lớn có thể biến lỗi rõ ràng thành thời gian chờ kéo dài.

### 5.1. Submit được nhận, bị từ chối hay chạy trên caller?

Ba kết quả cần phân biệt:

1. **Được nhận, chạy bất đồng bộ:** task có thể chạy ngay hoặc chờ queue.
2. **Bị từ chối:** với chính sách mặc định dựa trên `AbortPolicy`, Spring có thể ném `TaskRejectedException` khi executor đã bão hòa hoặc đóng. Không có `t_start` cho task không được nhận.
3. **Caller thực thi thay worker:** nếu cấu hình `CallerRunsPolicy` và pool chưa shutdown, tác vụ bị bão hòa có thể chạy ngay trên thread gửi. Khi ấy lời gọi `execute(...)` bị chặn tới khi thực thi xong.

Vì vậy không thể định nghĩa “submit luôn không chặn” cho mọi implementation/policy của `TaskExecutor`. `SyncTaskExecutor` còn chủ động thực thi đồng bộ trên thread caller và có ích trong một số môi trường test.

## 6. Đo độ trễ từ submit đến start bằng TaskDecorator

`ThreadPoolTaskExecutor.setTaskDecorator(...)` cho phép bọc callback được executor thực thi. Có thể ghi một dấu thời gian lúc tạo wrapper và một dấu lúc wrapper bắt đầu chạy.

Dưới đây là **phiên bản thay thế** của bean `reportExecutor` ở mục 5, không khai báo hai bean cùng tên trong một ApplicationContext:

~~~java
package example.concurrency;

import java.util.concurrent.TimeUnit;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
public class AsyncExecutorConfiguration {
    @Bean("reportExecutor")
    public ThreadPoolTaskExecutor reportExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(10);
        executor.setThreadNamePrefix("report-");

        executor.setTaskDecorator(callback -> {
            long submittedNanos = System.nanoTime();
            return () -> {
                long startedNanos = System.nanoTime();
                long waitMillis = TimeUnit.NANOSECONDS.toMillis(
                        startedNanos - submittedNanos);
                System.out.println("executor wait (ms): " + waitMillis);
                try {
                    callback.run();
                } finally {
                    long finishedNanos = System.nanoTime();
                    long runMillis = TimeUnit.NANOSECONDS.toMillis(
                            finishedNanos - startedNanos);
                    System.out.println("executor run (ms): " + runMillis);
                }
            };
        });
        return executor;
    }
}
~~~

Ví dụ tích hợp này **không có stdout cố định**: các giá trị đo thay đổi theo scheduling và workload. Trong production, nên gửi hai mẫu số đo tới histogram/timer của hệ thống metrics, kèm tag phù hợp, thay vì in log mỗi task.

Lưu ý khi giải thích metric:

- `System.nanoTime()` dùng đo **hiệu thời gian trong cùng JVM**, không phải giờ UTC và không so sánh số tuyệt đối giữa các máy.
- Callback mà `TaskDecorator` thấy có thể là **wrapper của Spring**, không nhất thiết là `Runnable`/`Callable` gốc. Thời gian đo là thời gian chờ và chạy callback được executor bọc.
- Một task bị reject không chạy wrapper, nên số lần reject phải đo riêng.
- Với `submit(...)`, callback có thể là `FutureTask` giữ exception bên trong Future. Bắt exception quanh `callback.run()` không bảo đảm thấy mọi exception nghiệp vụ.
- Nếu callback chỉ submit task khác rồi trả về, thời gian thực thi callback không bằng thời gian hoàn tất của task đã submit tiếp.
- Nếu policy chạy trên caller, “wait” đo được có thể rất ngắn và “run” xảy ra ngay trong lời gọi gửi. Đừng suy ra đó là worker nền.

### 6.1. Khi nào dùng timestamp đồng hồ?

Để tương quan log từ request đến worker, nên ghi job id/correlation id với timestamp có timezone (ví dụ UTC), ở cả mốc submit và start. Để tính duration chính xác trong cùng process, nên dùng monotonic timer như `System.nanoTime()`. Hai mục đích bổ trợ nhau nhưng không thể hoán đổi trực tiếp.

## 7. Queue wait ảnh hưởng đến timeout, SLA và kết quả nghiệp vụ

Ví dụ giả định:

| Giai đoạn | Thời gian |
| --- | ---: |
| Caller gửi task | 2 ms |
| Task nằm trong queue | 2.500 ms |
| Worker thực thi | 300 ms |
| Tổng từ submit tới hoàn tất | Khoảng 2.802 ms |

Nếu dashboard chỉ tính thời gian bên trong `@Async`, nó hiển thị khoảng **300 ms**, còn người dùng thấy gần **2,8 giây**. Queue wait phải được đưa vào phép đo end-to-end và cân nhắc khi thiết kế deadline.

Cần phân biệt:

- **Request timeout:** giới hạn thời gian HTTP caller chờ response; có thể xảy ra trước khi tác vụ bắt đầu.
- **Future timeout:** `Future.get(timeout)` hết giờ chỉ dừng caller chờ; task có thể tiếp tục trong queue/worker.
- **I/O timeout:** giới hạn thao tác HTTP/JDBC/network thực tế, không tự giải quyết thời gian chờ queue.
- **Business deadline:** thời điểm hết giá trị của công việc. Worker có thể cần kiểm tra deadline trước khi thực hiện side effect.
- **Cancellation:** có thể yêu cầu hủy task nhưng không đảo ngược mọi hiệu ứng đã xảy ra; việc ngắt còn phụ thuộc mã thực thi và thư viện đang chặn.

Nếu API trả `202 Accepted` với job id, phải định nghĩa rõ “accepted” là đã ghi vào hệ thống nào. Một executor có queue **chỉ trong bộ nhớ** không tự bảo đảm công việc tồn tại sau khi tiến trình chết hoặc restart. Nếu nghiệp vụ cần tiếp nhận bền vững, phải có job store/hàng đợi bền vững và trạng thái theo dõi phù hợp.

## 8. Thứ tự submit không phải thứ tự start hoặc finish

Với nhiều workers, B có thể hoàn thành trước A dù A được submit trước. Ngay cả khi queue là FIFO, task mới vẫn có thể được giao trực tiếp cho non-core worker khi queue đã đầy; trong khi task cũ còn chờ worker lấy từ queue.

~~~text
Caller:   submit A ---- submit B ---- submit C
Worker 1: [----------------- A ----------------]
Worker 2:                            [-- C --]
Queue:               [----- B đang chờ -----]
~~~

Sơ đồ minh họa một tình huống có thể xảy ra tùy cấu hình pool và tải. Quy tắc FIFO của một queue **không đồng nghĩa** với thứ tự hoàn tất toàn hệ thống.

Nếu nghiệp vụ đòi hỏi tác vụ của cùng một customer id chạy theo thứ tự, phải thiết kế ordering theo key/partition/transaction hoặc một hàng đợi tuần tự phù hợp. Chỉ gọi `submit(A)` trước `submit(B)` chưa đủ để bảo đảm side effect của A luôn trước B.

## 9. Cách chẩn đoán khi task đến chậm

Thu thập các thông tin dưới đây ở cả caller và worker:

| Dữ liệu | Mục đích |
| --- | --- |
| Job/correlation id | Ghép log của submit, queue, start, finish |
| Timestamp submit và kết quả admission | Phân biệt task được nhận và task bị từ chối |
| Timestamp start, finish, failure | Đo queue wait, execution duration và end-to-end |
| Active workers / pool size | Xem worker có bị chiếm hết không |
| Queue depth và tuổi task chờ | Phát hiện backlog trước khi request timeout |
| Rejection count, executor shutdown | Phân biệt quá tải và không còn nhận task |
| CPU, lock wait, DB/HTTP pool | Tìm tài nguyên khiến worker không tiến triển |
| p50/p95/p99 wait và run duration | Nhìn tác động lên các request chậm nhất |

Các bước kiểm tra:

1. Xác nhận ứng dụng đang dùng **bean executor nào**, `@Async` có đi qua proxy không và có vô tình dùng executor đồng bộ không.
2. Tách lỗi **không được nhận** với **được nhận nhưng chưa chạy**; không ghi queue wait cho task đã reject.
3. Đo từ submit đến start trên cùng một job id, rồi đo riêng khoảng worker chạy.
4. Xem core/max/queueCapacity/rejection policy. Với queue còn chỗ, pool có thể không mở tới max.
5. Kiểm tra thread dump và downstream: worker có đang chờ JDBC, HTTP, lock hoặc task con trong cùng pool không?
6. Thử tải tăng dần, so sánh throughput, queue wait, run duration, timeout, rejection, CPU và connection wait trước/sau khi đổi cấu hình.

Nếu queue wait tăng mạnh còn run duration giữ nguyên, có thể tốc độ đến đang lớn hơn năng lực phục vụ hoặc pool bị giới hạn worker. Nếu run duration cũng tăng, tìm bottleneck về I/O, DB, lock và CPU trước khi tăng số luồng.

## 10. Các nhầm lẫn thường gặp

**“`@Async` trả Future nghĩa là method body đã chạy.”** Sai: Future có thể được trả khi task vẫn đang nằm trong queue.

**“`Future.isDone() == false` nghĩa là task chưa start.”** Sai: Future chưa hoàn tất có thể đang chạy hoặc đang chờ.

**“Khi có worker rảnh, submit phải trả về trước start.”** Không có bảo đảm như vậy; worker có thể bắt đầu rất nhanh, trước khi caller hoàn tất thao tác gửi.

**“Đặt maxPoolSize lớn là không có queue wait.”** Sai: sau core, executor thường ưu tiên enqueue trước khi mở worker bổ sung.

**“Executor có nghĩa luôn chạy trên luồng nền.”** Sai: Spring có `SyncTaskExecutor`; `CallerRunsPolicy` còn có thể khiến caller trực tiếp thực thi task khi pool quá tải.

**“TaskDecorated wrapper catch exception là đếm đủ mọi lỗi.”** Sai: với wrapper `FutureTask`, exception có thể được giữ lại trong Future.

**“Chỉ cần đo thời gian bên trong `run()` để biết latency.”** Sai: phép đo đó bỏ qua khoảng chờ từ submit tới start.

**“Không có rejection tức là không quá tải.”** Sai: queue dài có thể tích tụ task, tăng thời gian chờ và bộ nhớ mà chưa reject.

**“Submit thành công có nghĩa xử lý chắc chắn được bảo toàn qua restart.”** Sai: queue in-memory không cung cấp độ bền như một message broker/job store.

## 11. Câu hỏi tự kiểm tra

**Câu 1.** B được gửi thành công khi một worker đang bận 3 giây, B chạy 100 ms. Tổng thời gian của B tính từ submit có thể khoảng bao nhiêu?

**Đáp án:** khoảng 3,1 giây trong mô hình một worker và không có độ trễ khác: 3 giây chờ và 0,1 giây chạy.

**Câu 2.** Nhận được `CompletableFuture` nghĩa là method body `@Async` đã bắt đầu chưa?

**Đáp án:** chưa chắc. Có thể queue, đang chạy hoặc đã xong; cần mốc start/metric để biết.

**Câu 3.** `Future.isDone()==true` có thể có ý nghĩa nào khác thành công?

**Đáp án:** có thể task kết thúc bằng exception hoặc Future bị cancel.

**Câu 4.** Trong ví dụ Java 17, tại sao B luôn chưa start khi main kiểm tra?

**Đáp án:** A đã giữ worker duy nhất và chờ latch; main chưa mở latch ở thời điểm kiểm tra.

**Câu 5.** Với `CallerRunsPolicy`, `execute(task)` có thể chờ task chạy xong trước khi trả về không?

**Đáp án:** có. Khi policy được kích hoạt và pool chưa shutdown, caller tự chạy task.

**Câu 6.** Vì sao dashboard đo riêng thời gian trong method async thường thấp hơn độ trễ người dùng?

**Đáp án:** nó không tính thời gian task đợi worker trong queue.

**Câu 7.** Nếu pool có core=2, max=8 và queueCapacity=100, vì sao task thứ ba có thể chưa chạy ngay?

**Đáp án:** vì sau core, executor ưu tiên đưa task vào queue khi còn chỗ thay vì mở thêm worker.

**Câu 8.** Khi task bị từ chối, nên ghi nhận sự kiện gì?

**Đáp án:** ghi submission failure/rejection với thông tin pool và caller; không gán cho task một start timestamp không tồn tại.

## 12. Tài liệu tham khảo

- Spring Framework — Task Execution and Scheduling: https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html
- Spring Framework — `ThreadPoolTaskExecutor`, `setTaskDecorator(...)`: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html
- Java SE 17 — `ThreadPoolExecutor`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html
- Java SE 17 — `Future`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html
- Java SE 17 — `System.nanoTime()`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#nanoTime()
