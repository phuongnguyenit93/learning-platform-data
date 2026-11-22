# Chọn cách theo dõi hoàn tất theo hợp đồng của từng scheduler

## 1. Đừng nhầm ba lần hoàn tất khác nhau

Một API mang tên `schedule(...)` trả về `ScheduledFuture` không đồng nghĩa
với việc hệ thống đã hoàn tất tác vụ nghiệp vụ. Cần tách:

1. **Lịch được đăng ký / trigger đã kích hoạt:** scheduler biết khi nào gọi.
2. **Công việc đã được giao:** runnable được gửi sang một thread/executor.
3. **Công việc đã chạy xong:** callback hoặc job thực tế kết thúc, có thể lỗi.
4. **Nghiệp vụ đã commit:** dữ liệu/thao tác mong muốn được ghi nhận bền vững.

Đặc biệt, Javadoc `SimpleAsyncTaskScheduler` nêu rõ `ScheduledFuture` có
thể đại diện cho **handoff tới execution thread**, không phải completion của
callback đã được giao. Do đó `get()`/`isDone()` phải được diễn giải theo
implementation, không chỉ theo tên kiểu trả về.

## 2. One-shot và periodic khác nhau

Với `ThreadPoolTaskScheduler` dùng `ScheduledExecutorService`, một
one-shot `ScheduledFuture` thường cho phép quan sát callback đã chạy xong
theo ngữ nghĩa của executor bên dưới. Ngược lại:

- Với **periodic task**, future đại diện cho một chuỗi lần kích hoạt; nó có
  thể tiếp tục ở trạng thái chưa hoàn tất khi các tick vẫn đang hoạt động.
  `isDone() == false` không có nghĩa là “chưa có tick nào chạy”.
- Với **SimpleAsyncTaskScheduler**, future có thể chỉ phản ánh handoff, không
  đợi worker đã hoàn tất việc thật.
- Với một scheduler chỉ làm **trigger rồi offload**, future gắn với trigger
  cũng không chứng minh task phía executor đã thành công.
- `cancel(...)` thường giúp ngừng lịch hoặc cố gắng ngắt tác vụ theo ngữ
  nghĩa tương ứng; nó không tự rollback transaction, thu hồi thông điệp đã
  gửi hay đảo tác dụng phụ bên ngoài.

## 3. Ví dụ theo dõi one-shot bằng ScheduledFuture

```java
import java.time.Instant;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import org.springframework.scheduling.TaskScheduler;

class OneShotProbe {
    private final TaskScheduler scheduler;

    OneShotProbe(TaskScheduler scheduler) {
        this.scheduler = scheduler;
    }

    void scheduleOneShot() throws Exception {
        ScheduledFuture<?> handle = scheduler.schedule(
            () -> System.out.println("callback finished"),
            Instant.now().plusSeconds(1)
        );
        if (handle == null) {
            throw new IllegalStateException("Không còn thời điểm kích hoạt");
        }
        handle.get(5, TimeUnit.SECONDS);
        // Chỉ kết luận theo contract của scheduler implementation thực tế.
    }
}
```

Ví dụ dành cho phân tích contract của scheduler. Với
`SimpleAsyncTaskScheduler`, kể cả khi `handle.get(...)` trả về, callback
được handoff có thể chưa hoàn tất. Ngoài ra, một `get(timeout)` hết hạn
**không** mặc nhiên ngừng callback.

## 4. Khi cần completion nghiệp vụ: tự sở hữu trạng thái

Với job nền có ích cho người dùng hoặc có tác dụng phụ, hãy theo dõi một
`jobId` riêng:

```text
PLANNED -> ACCEPTED -> RUNNING -> SUCCEEDED
                     \\-> FAILED
          \\-> REJECTED
RUNNING   \\-> CANCEL_REQUESTED -> CANCELLED / FAILED / SUCCEEDED
```

Worker là nơi cập nhật trạng thái cuối cùng sau khi xử lý thực tế.
Nếu hệ thống có nhiều instance hoặc cần phục hồi qua restart, lưu job state
ở một nơi bền vững có điều kiện cập nhật trạng thái (DB/queue/job store).
Không giữ job state chỉ bằng một `ConcurrentHashMap` nếu SLA yêu cầu dữ
liệu sống qua restart hoặc điều phối nhiều instance.

Một `CompletableFuture` riêng được hoàn tất bởi worker cũng hữu ích trong
một JVM nhưng **không phải** job store bền vững. Khi điều phối qua database
hoặc message broker, nên phân biệt trạng thái `ACCEPTED` với việc handler
đã commit dữ liệu, và phải có cách xử lý timeout/retry/idempotency.

## 5. Ma trận lựa chọn cách kiểm chứng

| Nhu cầu | Nên quan sát |
| --- | --- |
| Hủy lịch tương lai | ScheduledFuture / API của scheduler |
| Biết trigger đã kích hoạt | Log/timestamp trigger, metric schedule lag |
| Biết worker thực sự chạy xong | Future/CompletionStage do worker hoàn tất, hoặc event kết quả |
| Biết transaction nghiệp vụ thành công | Trạng thái job được lưu bền vững, kết quả DB, event sau commit |
| Chạy định kỳ ở nhiều replica | Lock/lease, quyền sở hữu, cơ chế idempotency và audit |

## 6. Bài tập tự kiểm chứng

1. Với một one-shot, chặn callback bằng latch rồi kiểm tra `isDone()`
   của `ThreadPoolTaskScheduler` và `SimpleAsyncTaskScheduler`.
2. Với periodic task, ghi số lần callback chạy, `isDone()` và trạng thái
   sau `cancel`; kiểm tra còn tick mới hay không.
3. Tách trigger và worker thành hai executor; chứng minh future của trigger
   không phản ánh hoàn tất của worker.
4. Cho worker cập nhật trạng thái `SUCCEEDED` **sau** transaction commit,
   phân biệt với trạng thái chỉ đã nhận job.

## 7. Kết luận

Hợp đồng completion phải được chọn theo scheduler và kiểu công việc:
`ScheduledFuture` chủ yếu phục vụ quản lý lịch, còn kết quả nghiệp vụ
phải được theo dõi ở ranh giới worker/transaction thích hợp.

**Tham khảo:** [Spring TaskScheduler Reference](https://docs.spring.io/spring-framework/reference/integration/scheduling.html);
[SimpleAsyncTaskScheduler Javadoc](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/scheduling/concurrent/SimpleAsyncTaskScheduler.html).
