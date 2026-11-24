# Bọc tác vụ để thực thi có đo thời gian vào thời điểm khác

Trong nhiều ứng dụng Java, tác vụ được tạo ở một thời điểm nhưng chỉ chạy sau đó: executor đưa tác vụ vào hàng đợi, scheduler chờ đến giờ kích hoạt, hoặc một callback được gọi khi sự kiện bất đồng bộ xảy ra. Nếu chỉ đo thời gian lúc tạo hoặc đăng ký tác vụ, số đo không phản ánh thời gian thực thi thực tế.

Micrometer `Timer` cung cấp `wrap(Runnable)` để tạo một `Runnable` đã được bọc đo thời gian. Việc bọc không thực thi tác vụ ngay. Timer bắt đầu đo khi wrapper được gọi và dừng khi tác vụ kết thúc, kể cả khi tác vụ ném exception. Vì vậy có thể tạo wrapper trước, chuyển nó cho executor hoặc scheduler, rồi để nó ghi nhận thời gian tại thời điểm thực thi.

## Tạo Timer và bọc Runnable

Đăng ký một timer trước, sau đó dùng `wrap(...)` để tạo tác vụ có đo thời gian:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

public class JobSubmitter {
    private final ExecutorService executor = Executors.newFixedThreadPool(4);
    private final Timer executionTimer;
    private final JobWorker worker;

    public JobSubmitter(MeterRegistry registry, JobWorker worker) {
        this.worker = worker;
        this.executionTimer = Timer.builder("jobs.execution")
                .description("Thời gian thực thi job")
                .tag("job_type", "reconciliation")
                .register(registry);
    }

    public void submit(Job job) {
        Runnable measuredTask = executionTimer.wrap(() -> worker.process(job));
        executor.submit(measuredTask);
    }

    public void shutdown() throws InterruptedException {
        executor.shutdown();
        if (!executor.awaitTermination(30, TimeUnit.SECONDS)) {
            executor.shutdownNow();
        }
    }
}
```

`submit(...)` chỉ tạo wrapper và gửi nó đến executor. Timer bắt đầu đo khi một worker thực sự gọi `run()`, không phải lúc `submit(...)` được gọi. Thời gian nằm chờ trong hàng đợi không nằm trong `jobs.execution`.

Một wrapper có thể được giữ lại và chạy nhiều lần. Mỗi lần gọi `run()` là một lần thực thi và tạo một observation mới trong timer. Nếu cùng một `Runnable` được đưa vào lịch chạy định kỳ, mỗi lượt chạy hoàn tất sẽ làm `count()` tăng thêm một.

## Bọc tác vụ được scheduler thực thi sau một khoảng trễ

Với `ScheduledExecutorService`, có thể tạo wrapper trước rồi lên lịch chạy:

```java
ScheduledExecutorService scheduler = Executors.newScheduledThreadPool(2);
Timer cleanupTimer = registry.timer("maintenance.cleanup.duration");

Runnable cleanup = cleanupTimer.wrap(() -> cleanupExpiredSessions());

// Chạy sau 30 giây; timer chỉ đo phần cleanup thực sự chạy.
scheduler.schedule(cleanup, 30, TimeUnit.SECONDS);
```

Khoảng trễ 30 giây trước khi scheduler gọi `run()` không được tính vào `cleanupTimer`. Timer chỉ đo từ lúc bắt đầu chạy `cleanupExpiredSessions()` đến khi phương thức đó kết thúc. Đây thường là điều cần đo khi đánh giá chi phí thực thi của một job.

Nếu dùng `scheduleAtFixedRate(...)` hoặc `scheduleWithFixedDelay(...)`, có thể truyền cùng wrapper vào lịch chạy. Mỗi lần thực thi được đo riêng. Lưu ý rằng exception không được xử lý trong tác vụ có thể khiến scheduler ngừng các lần chạy định kỳ tiếp theo theo quy tắc của `ScheduledExecutorService`; wrapper ghi nhận thời lượng của lần chạy thất bại nhưng không tự xử lý lỗi thay cho ứng dụng.

## Phân biệt thời gian chờ và thời gian thực thi

Một tác vụ bất đồng bộ có thể tiêu tốn thời gian ở hai giai đoạn khác nhau:

- **Queue wait:** từ lúc ứng dụng gửi tác vụ đến executor đến lúc worker bắt đầu chạy.
- **Execution duration:** từ lúc worker bắt đầu xử lý đến khi tác vụ kết thúc.

`Timer.wrap(Runnable)` đo execution duration. Nếu cần quan sát cả độ trễ hàng đợi, hãy tạo một `Timer.Sample` khi submit và dừng sample ngay khi worker bắt đầu:

```java
Timer queueWaitTimer = registry.timer("jobs.queue.wait");
Timer executionTimer = registry.timer("jobs.execution");

public void submit(Job job) {
    Timer.Sample queuedAt = Timer.start(registry);

    executor.execute(() -> {
        queuedAt.stop(queueWaitTimer);
        executionTimer.record(() -> worker.process(job));
    });
}
```

Ở đây, `jobs.queue.wait` đo khoảng thời gian từ trước lệnh `execute(...)` đến khi worker bắt đầu; `jobs.execution` đo phần xử lý. Hai số đo trả lời hai câu hỏi vận hành khác nhau. Nếu executor từ chối tác vụ hoặc không bao giờ chạy nó, sample queue wait không được dừng; cần đo riêng số tác vụ bị từ chối hoặc bị hủy để giải thích trường hợp đó.

Không cộng queue wait vào execution duration nếu mục tiêu dashboard là tìm nguyên nhân chậm. Khi execution duration tăng, worker hoặc logic xử lý có thể chậm. Khi queue wait tăng trong khi execution duration ổn định, executor có thể thiếu worker, hàng đợi quá dài hoặc lưu lượng đầu vào vượt khả năng xử lý.

## Dùng wrapper với CompletableFuture

Với tác vụ chạy bất đồng bộ bằng `CompletableFuture.runAsync(...)`, wrapper có thể được truyền trực tiếp như một `Runnable`:

```java
Runnable measuredTask = executionTimer.wrap(() -> worker.process(job));

CompletableFuture<Void> result = CompletableFuture.runAsync(
        measuredTask,
        executor);
```

Timer đo phần thân `worker.process(job)` trên executor. Nó không đo thời gian tạo `CompletableFuture` hoặc thời gian chờ trước khi executor chạy tác vụ.

Đặc biệt, nếu phần thân được bọc chỉ khởi chạy một lời gọi bất đồng bộ rồi trả về ngay, timer sẽ dừng khi lời gọi khởi chạy kết thúc, không chờ I/O hoặc future bên trong hoàn tất. Ví dụ, đo một phương thức trả về `CompletableFuture<Response>` bằng `Timer.wrap(Runnable)` quanh lệnh gọi phương thức chỉ đo thời gian tạo future.

Nếu muốn đo từ lúc gửi yêu cầu bất đồng bộ đến khi future hoàn tất, dùng `Timer.Sample` và dừng nó trong callback hoàn tất:

```java
Timer.Sample sample = Timer.start(registry);

return remoteClient.sendAsync(request)
        .whenComplete((response, error) -> {
            String outcome = error == null ? "success" : "failure";
            sample.stop(registry.timer(
                    "remote.request.duration",
                    "outcome", outcome));
        });
```

`whenComplete(...)` được gọi khi future hoàn tất, nên sample bao phủ cả thời gian chờ phản hồi. Tag `outcome` có hai giá trị hữu hạn. Nếu cần đo riêng thời gian gửi request và thời gian chờ phản hồi, hãy tạo hai phép đo với điểm bắt đầu và kết thúc tương ứng.

## Đo kết quả thành công và thất bại

`Timer.wrap(Runnable)` đo thời lượng mỗi lần wrapper chạy và để exception tiếp tục truyền ra caller. Nó không tự gắn tag kết quả vì timer đã được chọn khi tạo wrapper. Nếu cần phân biệt `success` và `failure`, dùng `Timer.Sample` để chọn timer sau khi biết kết quả:

```java
Runnable measuredTask = () -> {
    Timer.Sample sample = Timer.start(registry);
    String outcome = "success";

    try {
        worker.process(job);
    } catch (RuntimeException exception) {
        outcome = "failure";
        throw exception;
    } finally {
        sample.stop(registry.timer(
                "jobs.execution",
                "outcome", outcome));
    }
};

executor.execute(measuredTask);
```

`finally` bảo đảm timer được dừng cho cả nhánh thành công và exception. Exception vẫn được ném lại để executor, future hoặc cơ chế xử lý lỗi hiện tại nhận biết. Không nuốt exception chỉ để timer ghi nhận được số đo.

Khi không cần phân loại kết quả, `Timer.wrap(...)` ngắn gọn hơn. Khi cần tag phụ thuộc kết quả, thời điểm kết thúc hoặc trạng thái được xác định sau khi tác vụ chạy, `Timer.Sample` phù hợp hơn.

## Mỗi lần thực thi là một observation

Giả sử wrapper được tạo một lần và chạy ba lần:

```java
Timer timer = registry.timer("batch.run.duration", "batch", "daily");
Runnable measuredBatch = timer.wrap(() -> runBatch());

measuredBatch.run();
measuredBatch.run();
measuredBatch.run();

System.out.println("Executions = " + timer.count()); // 3
```

`count()` bằng 3 vì wrapper đã chạy ba lần. `totalTime(...)` là tổng thời gian của cả ba lần. `Timer` không chỉ giữ thời gian của lần gần nhất. Nếu một lần chạy bị scheduler retry, lần retry cũng là một lần thực thi và được ghi nhận riêng.

Nếu yêu cầu nghiệp vụ chỉ được tính thành công một lần dù job có thể chạy lại, hãy dùng metric riêng cho số lần thử và số kết quả hoàn tất. Timer của tác vụ thường đo mọi lần thực thi, kể cả lần thất bại; counter nghiệp vụ thành công chỉ tăng sau khi kết quả mới được xác nhận. Việc chống xử lý lặp cần cơ chế idempotency của nghiệp vụ, không phải `Timer`.

## Kiểm thử wrapper mà không cần backend

`SimpleMeterRegistry` cho phép kiểm tra wrapper ghi nhận đúng số lần và thời lượng mà không cần kết nối hệ thống giám sát:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

class TimerWrapTest {
    @Test
    void recordsEachExecutionWhenRunnableIsInvoked() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        Timer timer = registry.timer("test.task.duration");
        AtomicInteger calls = new AtomicInteger();

        Runnable measured = timer.wrap(calls::incrementAndGet);

        assertThat(timer.count()).isZero();

        measured.run();
        measured.run();

        assertThat(calls.get()).isEqualTo(2);
        assertThat(timer.count()).isEqualTo(2);
        assertThat(timer.totalTime(TimeUnit.NANOSECONDS)).isGreaterThanOrEqualTo(0);

        registry.close();
    }
}
```

Ví dụ cần các import `java.util.concurrent.atomic.AtomicInteger` và `java.util.concurrent.TimeUnit`. Assertion `timer.count()` trước khi gọi wrapper chứng minh việc tạo wrapper không tự thực thi tác vụ. Hai lần gọi `run()` tạo hai observation. Thời lượng thực tế phụ thuộc môi trường nên test không nên yêu cầu một con số mili giây cố định.

Với executor hoặc scheduler, test nên đợi `Future.get(...)`, latch hoặc tín hiệu hoàn tất trước khi đọc `count()`. Nếu đọc ngay sau `submit(...)`, tác vụ có thể chưa chạy và timer vẫn bằng 0; đó là trạng thái hợp lệ chứ không phải lỗi của wrapper.

## Chọn đúng ranh giới cần đo

| Mục tiêu | Cách đo phù hợp | Phạm vi thời gian |
|---|---|---|
| Đo phần thân Runnable chạy muộn | `timer.wrap(runnable)` | Từ lúc `run()` bắt đầu đến khi kết thúc |
| Đo một lần gọi đồng bộ | `timer.record(runnable)` | Trong lần gọi `record(...)` |
| Đo queue wait | `Timer.Sample` khi submit, dừng khi worker bắt đầu | Từ lúc submit đến lúc bắt đầu chạy |
| Đo toàn bộ lời gọi bất đồng bộ | `Timer.Sample`, dừng trong `whenComplete(...)` | Từ lúc gửi đến khi future hoàn tất |
| Gắn tag theo kết quả thực thi | `Timer.Sample` và chọn timer ở `stop(...)` | Theo thời lượng và outcome thực tế |

Đừng bọc nhầm tầng. Một wrapper quanh đoạn mã chỉ gọi `executor.execute(...)` sẽ đo thời gian gửi tác vụ, không đo phần thân chạy trên worker. Một wrapper quanh đoạn mã tạo future sẽ đo thời gian tạo future, không đo thời gian future hoàn tất. Hãy đặt wrapper tại chính `Runnable` hoặc callback đại diện cho phần công việc cần quan sát.

## Các lưu ý về tag và vòng đời tác vụ

Tag của timer phải có tập giá trị hữu hạn, chẳng hạn `job_type`, `queue` hoặc `outcome`. Không gắn ID job, user ID, request ID hoặc tên file tự do làm tag. Nếu một job có hàng triệu định danh, dùng ID trong log hoặc trace để truy vết từng lần thực thi; metric chỉ nên phân nhóm theo loại công việc.

Không tạo một `Timer` mới cho mỗi lần submit. Đăng ký timer một lần theo tên và tag ổn định, sau đó tái sử dụng nó để bọc các tác vụ. MeterRegistry sẽ quản lý meter theo định danh; việc tạo nhiều tổ hợp tag động làm tăng cardinality.

Với tác vụ dài, hãy cân nhắc `LongTaskTimer` nếu cần quan sát số tác vụ đang chạy và thời gian của tác vụ chưa hoàn tất. `Timer.wrap(...)` ghi nhận một observation khi lần thực thi kết thúc; dashboard không thể dùng timer đó để biết chính xác số tác vụ vẫn đang chạy tại thời điểm hiện tại.

## Lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| Timer vẫn bằng 0 sau khi tạo wrapper | Wrapper chưa được gọi | Kiểm tra executor hoặc scheduler đã thực thi `run()` chưa |
| Timer đo thời gian quá ngắn | Chỉ bọc lệnh gửi tác vụ hoặc tạo future | Bọc phần thân Runnable hoặc dừng `Timer.Sample` khi async hoàn tất |
| Thời lượng gồm cả thời gian chờ lịch | Bắt đầu sample lúc lên lịch thay vì dùng wrapper thực thi | Phân biệt queue wait với execution duration |
| `count()` lớn hơn số job nghiệp vụ | Retry hoặc lịch chạy lặp tạo nhiều execution | Phân biệt attempt, execution và kết quả nghiệp vụ |
| Timer không ghi nhận khi tác vụ lỗi | Exception bị xử lý ở một wrapper khác hoặc đo ở sai điểm | Kiểm tra exception flow và dùng `finally` nếu tự quản lý `Timer.Sample` |
| Số liệu tăng quá nhiều | Tạo tag theo job ID hoặc giá trị tự do | Chuẩn hóa tag thành các nhóm hữu hạn |

## Checklist hoàn thành

- [ ] Timer được đăng ký một lần với tên và tag ổn định.
- [ ] Wrapper được tạo trước và chỉ thực thi khi executor hoặc scheduler gọi nó.
- [ ] Đã xác nhận mỗi lần chạy wrapper tạo một observation riêng.
- [ ] Thời gian chờ trong hàng đợi được phân biệt với thời gian thực thi.
- [ ] Với tác vụ bất đồng bộ, timer dừng ở callback hoàn tất nếu mục tiêu là đo toàn bộ thời gian chờ phản hồi.
- [ ] Exception được ghi nhận thời lượng và vẫn được truyền theo chính sách lỗi của ứng dụng.
- [ ] Test đợi tác vụ hoàn tất trước khi kiểm tra `count()`.
- [ ] Tag có cardinality thấp và không chứa định danh từng job.

`Timer.wrap(Runnable)` phù hợp khi cần chuẩn bị một tác vụ đã được đo trước rồi giao cho executor hoặc scheduler thực thi sau. Timer chỉ đo lúc wrapper thực sự chạy; mỗi lần chạy tạo một observation. Khi cần đo queue wait, kết quả bất đồng bộ hoặc tag phụ thuộc outcome, hãy chọn điểm bắt đầu và kết thúc rõ ràng bằng `Timer.Sample`.
