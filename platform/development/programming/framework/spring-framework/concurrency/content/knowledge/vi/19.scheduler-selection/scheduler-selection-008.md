# Tách bộ lập lịch khỏi nhóm luồng xử lý khi cần kiểm soát hai loại tải

## 1. Hai tải khác nhau, hai chính sách khác nhau

Một scheduled callback thường chỉ cần kích hoạt đúng thời điểm, còn công việc
thực tế có thể phải truy cập database, gọi HTTP, kết xuất báo cáo hoặc chạy
batch lâu. Để tránh callback chậm chiếm tài nguyên tính lịch, có thể phân
tách:

```text
@Scheduled / TaskScheduler       ThreadPoolTaskExecutor
  [trigger pool]                       [worker pool]
        |                                   |
        +--- giới hạn nhịp kích hoạt ------> +--- tác vụ nghiệp vụ
               schedule lag                    queue / running / timeout
```

Trong Spring Framework, `ThreadPoolTaskScheduler` chịu trách nhiệm lập
lịch; `ThreadPoolTaskExecutor` là một lựa chọn để thực thi công việc nền.
Hai bean có thể có kích thước pool, queue, deadline, metric, và chính sách
shutdown khác nhau.

## 2. Ví dụ cấu hình có giới hạn

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableScheduling
class JobsConfiguration {
    @Bean("timeScheduler")
    ThreadPoolTaskScheduler timeScheduler() {
        ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(2);
        scheduler.setThreadNamePrefix("time-");
        return scheduler;
    }

    @Bean("jobWorkers")
    ThreadPoolTaskExecutor jobWorkers() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(16);
        executor.setThreadNamePrefix("job-");
        return executor;
    }
}
```

Ở đây scheduler có pool riêng; executor có tối đa bốn worker và queue hữu
hạn. Số lượng chỉ là giá trị minh họa, **không** phải khuyến nghị chung.
Phải sizing theo thời gian CPU, thời gian chờ, số kết nối DB/HTTP và SLA.

## 3. Giao việc phải có hợp đồng rõ ràng

```java
import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.core.task.TaskRejectedException;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.stereotype.Component;

@Component
class ScheduledReport {
    private final ThreadPoolTaskExecutor workers;
    private final AtomicBoolean inFlight = new AtomicBoolean();

    ScheduledReport(ThreadPoolTaskExecutor workers) {
        this.workers = workers;
    }

    @Scheduled(scheduler = "timeScheduler", fixedRate = 10_000)
    public void trigger() {
        // Chặn overlap trong một instance; không phải distributed lock.
        if (!inFlight.compareAndSet(false, true)) {
            return;
        }
        try {
            workers.execute(() -> {
                try {
                    doReport();
                } finally {
                    inFlight.set(false);
                }
            });
        } catch (TaskRejectedException ex) {
            inFlight.set(false);
            // Ghi metric và đưa ra quyết định retry/dead-letter có chủ đích.
        }
    }

    private void doReport() {
        // Xử lý nghiệp vụ có timeout và transaction boundary riêng.
    }
}
```

**Quan trọng:** `inFlight` chỉ bảo vệ trong *một JVM*. Ứng dụng triển khai
nhiều replica cần lease, distributed lock hoặc cơ chế điều kiện ở database
theo bất biến nghiệp vụ. Nếu policy của executor silently discard task,
không có lỗi từ `execute` để giải phóng cờ; vì vậy cần chọn rejection
policy theo hợp đồng tiếp nhận. Ví dụ này giả định policy báo lỗi khi từ chối.

## 4. Các lớp hoàn tất và rủi ro

| Tín hiệu | Ý nghĩa thực tế |
| --- | --- |
| Trigger fired | Scheduler đã đến thời điểm kích hoạt |
| Handoff accepted | Executor đã nhận yêu cầu thực thi, có thể còn nằm trong queue |
| Worker started | Task thật sự bắt đầu chạy trên worker |
| Worker completed | Task kết thúc; vẫn phải phân biệt thành công và lỗi |
| Business committed | Bất biến nghiệp vụ đã được xác nhận theo transaction/DB |

Việc callback `trigger()` trả về rất nhanh **không chứng minh** báo cáo đã
xong. Nếu submit lặp nhanh hơn năng lực worker, queue sẽ tăng, gây trễ hoặc
rejection. Cần giám sát queue depth, active workers, rejection, start lag,
duration, failure và business completion.

## 5. Bài tập kiểm chứng

1. Tạo một `CountDownLatch` giữ job đầu trong worker; quan sát scheduler
   vẫn kích hoạt nhưng `inFlight` ngăn gửi thêm.
2. Tắt single-flight, tạo backlog có giới hạn và đo thời gian từ trigger
   tới lúc worker bắt đầu; thử trường hợp queue đầy.
3. Kiểm tra liệu exception ở worker được báo về monitoring hay bị bỏ qua;
   thêm metric và log có correlation id.
4. Thử stop/shutdown: xác định có chờ worker đang chạy không, và những job
   được queue có bị đánh mất không.

## 6. Kết luận

Tách scheduler khỏi worker giúp kiểm soát hai tải riêng, nhưng bổ sung một
ranh giới async: trigger success khác job success. Hãy thiết kế acceptance,
backpressure, idempotency và completion theo hợp đồng của hệ thống.

**Tham khảo:** [Spring Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html);
[Spring Boot Task Execution and Scheduling](https://docs.spring.io/spring-boot/reference/features/task-execution-and-scheduling.html).
