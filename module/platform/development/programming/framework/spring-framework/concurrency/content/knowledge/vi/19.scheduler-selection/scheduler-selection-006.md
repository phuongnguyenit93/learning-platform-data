# SimpleAsyncTaskScheduler tách cơ chế kích hoạt với cách chạy tác vụ

## 1. Vấn đề đặt ra

Một bộ lập lịch phải giải quyết **hai trách nhiệm khác nhau**: biết *khi nào*
phải kích hoạt công việc và quyết định *ở đâu* công việc thực sự chạy. Nếu một
callback chặn I/O trong vài giây, việc nhầm lẫn hai trách nhiệm này dẫn đến
chẩn đoán sai: có lịch đã được kích hoạt đúng giờ nhưng công việc chưa hoàn
thành, hoặc một callback làm trễ lịch của callback khác.

Từ Spring Framework **6.1**, `SimpleAsyncTaskScheduler` là một hiện thực
`TaskScheduler` dùng **một scheduler thread** để quản lý kích hoạt. Với
fixed-rate và cron, nó có thể giao mỗi lần chạy sang thread riêng; trên
**JDK 21+** có thể bật virtual threads. Đây không phải là
`ThreadPoolTaskScheduler` có số worker cố định. Đặc biệt,
**fixed-delay là ngoại lệ quan trọng**, sẽ được phân tích trong bài 7.

## 2. Hình dung luồng thực thi

```text
Clock / Trigger / @Scheduled
          |
          v
  Single scheduler thread
          |    tính toán và đánh dấu thời điểm kích hoạt
          |----> task A -> execution thread A
          |----> task B -> execution thread B
          |----> task C -> execution thread C
          |
          +----> fixed-delay: ngoại lệ, chạy trên scheduler thread
```

Với thread-per-task, không có pool tái sử dụng thread thông thường. Virtual
threads có thể làm cho việc chờ I/O nhẹ hơn so với platform threads, nhưng
**không** làm tăng số lõi CPU, số kết nối database hoặc giới hạn API phía sau.
Một hệ thống vẫn cần timeout, giới hạn đồng thời và backpressure.

## 3. Cấu hình trong Spring

Ví dụ Java 21 và Spring Framework 6.1+:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.scheduling.concurrent.SimpleAsyncTaskScheduler;
import org.springframework.stereotype.Component;

@Configuration
@EnableScheduling
class SchedulingConfiguration {
    @Bean("reportScheduler")
    SimpleAsyncTaskScheduler reportScheduler() {
        SimpleAsyncTaskScheduler scheduler = new SimpleAsyncTaskScheduler();
        scheduler.setThreadNamePrefix("report-schedule-");
        scheduler.setVirtualThreads(true); // Chỉ dùng với Java 21+
        scheduler.setConcurrencyLimit(16); // Giới hạn đồng thời, không phải DB pool size
        return scheduler;
    }
}

@Component
class ReportJobs {
    @Scheduled(scheduler = "reportScheduler", fixedRate = 10_000)
    public void refresh() {
        // Gọi service đã được inject, có timeout và idempotency phù hợp.
        System.out.println("Executing on " + Thread.currentThread());
    }
}
```

Tên scheduler trong `@Scheduled` dùng để chọn bean; không nên để nhiều bean
scheduler gây mơ hồ. Việc `setVirtualThreads(true)` cần môi trường Java 21+.
Nếu dự án chạy Java thấp hơn, không bật tùy chọn này.

## 4. Khi nào dùng target executor riêng?

`SimpleAsyncTaskScheduler.setTargetTaskExecutor(Executor)` cho phép chuyển
phần **thực thi** tác vụ đã được kích hoạt sang một `Executor` khác, ví dụ
`ThreadPoolTaskExecutor` do ứng dụng sở hữu. Khi đó scheduler vẫn chủ yếu
đảm nhiệm thời điểm kích hoạt; executor đích kiểm soát worker và queue.

```java
@Bean("reportScheduler")
SimpleAsyncTaskScheduler reportScheduler(ThreadPoolTaskExecutor reportWorkers) {
    SimpleAsyncTaskScheduler scheduler = new SimpleAsyncTaskScheduler();
    scheduler.setTargetTaskExecutor(reportWorkers);
    return scheduler;
}
```

Ví dụ trên chỉ minh họa cơ chế ủy quyền; cần khai báo bean `reportWorkers`
với giới hạn pool/queue và chính sách từ chối rõ ràng. **Không coi**
`SimpleAsyncTaskScheduler` + target executor là `ThreadPoolTaskScheduler`:
đường tính lịch và ý nghĩa completion khác nhau.

## 5. Tự kiểm chứng

1. Ghi lại timestamp trước khi task bắt đầu, thread name, `isVirtual()`
   và timestamp task hoàn tất; chạy hai callback fixed-rate độc lập.
2. Cho một callback chờ `CountDownLatch`; kiểm tra callback khác có thể
   bắt đầu trong thread khác hay không.
3. Dùng các ngưỡng tải tăng dần, quan sát số tác vụ đang chạy, số kết nối DB
   và rejection ở executor đích. Không dùng `Thread.sleep()` để *chứng minh*
   tính đúng đắn của lịch.
4. Thử hủy lịch trong lúc một callback đã được giao cho worker; phân biệt
   **ngừng các lần kích hoạt tương lai** với **dừng tác vụ đang chạy**.

## 6. Kết luận

Lựa chọn `SimpleAsyncTaskScheduler` khi cần một đường lập lịch gọn, có
khả năng giao từng lần chạy sang thread riêng, đặc biệt phù hợp kiểu workload
I/O trên Java 21. Không dùng đặc tính đó như bằng chứng tự động của
fixed-delay song song, giới hạn tài nguyên, durability hoặc completion.

**Tham khảo:** [Spring Scheduling Reference](https://docs.spring.io/spring-framework/reference/integration/scheduling.html);
[SimpleAsyncTaskScheduler Javadoc](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/scheduling/concurrent/SimpleAsyncTaskScheduler.html).
