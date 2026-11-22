# Phân biệt TaskExecutor với TaskScheduler trong Spring Framework

Trong Spring Framework, **`TaskExecutor` trả lời câu hỏi “công việc này sẽ được thực thi bằng cơ chế nào?”**, còn **`TaskScheduler` trả lời câu hỏi “khi nào công việc này phải được kích hoạt?”**. Cả hai đều xử lý tác vụ (`Runnable`), nhưng khác nhau ở hợp đồng API, cách kích hoạt, cơ chế thời gian, đối tượng trả về và cách vận hành.

Ví dụ: người dùng vừa xác nhận đơn hàng và cần xử lý email nền → dùng `TaskExecutor`. Hệ thống phải kiểm tra đơn hàng quá hạn vào 09:00 mỗi ngày → dùng `TaskScheduler`. Nếu cứ 5 phút hệ thống phải kích hoạt một lô xử lý tốn nhiều thời gian, ta có thể **dùng scheduler để quyết định thời điểm, rồi executor để chạy phần công việc nặng**. Phân chia rõ hai trách nhiệm giúp cấu hình pool, giới hạn tải và theo dõi lỗi chính xác.

## 1. Bảng so sánh cốt lõi

| Tiêu chí | `TaskExecutor` | `TaskScheduler` |
| --- | --- | --- |
| Mục đích | Nhận và thực thi tác vụ được giao | Hẹn một lần chạy hoặc quy tắc chạy theo thời gian |
| Thời điểm kích hoạt | Caller chủ động gọi `execute(task)`; tác vụ chạy khi tài nguyên thực thi cho phép | Dựa trên `Instant`, chu kỳ `Duration` hoặc `Trigger` |
| Hợp đồng chính | `void execute(Runnable task)` | `schedule(Runnable, Instant/Trigger)`, `scheduleAtFixedRate(...)`, `scheduleWithFixedDelay(...)` |
| Phạm vi | Một lần submit không tự trở thành định kỳ | Một lần, fixed-rate, fixed-delay, cron/custom trigger |
| Kết quả thao tác API | `TaskExecutor.execute` không trả về Future; các API của `AsyncTaskExecutor` có thể trả Future | Các phương thức đặt lịch thường trả `ScheduledFuture<?>`; với Trigger không có lần chạy tiếp theo, có thể trả `null` |
| Annotation gắn với khái niệm | `@Async` và `@EnableAsync` | `@Scheduled` và `@EnableScheduling` |
| Triển khai thường gặp | `ThreadPoolTaskExecutor`, `SimpleAsyncTaskExecutor` | `ThreadPoolTaskScheduler`, `ConcurrentTaskScheduler`, `SimpleAsyncTaskScheduler` |
| Vấn đề khi dùng sai | Queue quá dài, pool bão hòa, task bị từ chối | Chạy muộn/lỡ nhịp, scheduler thread bị chặn, tác vụ định kỳ chồng lấn |

**Điểm quan trọng:** scheduler cũng cần luồng để thực thi callback; executor cũng có thể xếp queue nên không hứa “chạy ngay tức thì”. Sự khác biệt là **hợp đồng và ý nghĩa của lời gọi**, không phải hai loại luồng tách biệt tuyệt đối. Một lớp triển khai có thể hỗ trợ cả nhiều interface.

## 2. TaskExecutor: “hãy thực thi tác vụ này”

Spring định nghĩa giao diện tối thiểu:

~~~java
public interface TaskExecutor extends java.util.concurrent.Executor {
    void execute(Runnable task);
}
~~~

Đây là **chữ ký API rút gọn để giải thích**, không phải lớp nguồn cần tự viết lại trong ứng dụng. Caller gọi `execute` một lần cho mỗi công việc. Tùy implementation và cấu hình, lời gọi có thể được xử lý trên luồng khác, qua pool, hoặc theo một chiến lược thực thi cụ thể. `TaskExecutor` không có API biểu diễn “chạy lúc 9 giờ” hay “lặp lại mỗi 10 giây”.

### 2.1. `ThreadPoolTaskExecutor`

`ThreadPoolTaskExecutor` tích hợp với cơ chế `ThreadPoolExecutor` của Java, có thể cấu hình:

- `corePoolSize`: số worker lõi.
- `maxPoolSize`: giới hạn số worker trong điều kiện pool được phép tăng.
- `queueCapacity`: số tác vụ chờ tối đa trong queue.
- Chính sách khi hết khả năng nhận tác vụ, cách đặt tên luồng và lifecycle.

Với queue có dung lượng dương, sau khi đã đạt core size, tác vụ thường **vào queue trước**, rồi pool mới mở thêm worker tới max khi queue đầy. Vì vậy `maxPoolSize` lớn không bảo đảm các task sẽ chạy song song ngay. Với queue không giới hạn, có thể không cần tăng tới max. Executor bị quá tải có thể ném `TaskRejectedException`; phía gọi cần xử lý thay vì giả định mọi lần submit đều thành công.

`SimpleAsyncTaskExecutor` phù hợp với một số nhu cầu đơn giản nhưng về cơ bản **không phải pool tái sử dụng một nhóm worker cố định**; phải hiểu giới hạn concurrency và chi phí tạo luồng/virtual threads theo phiên bản. Không chọn implementation chỉ dựa vào chữ “async”.

### 2.2. `@Async` là một cách gửi công việc vào executor

Trong ứng dụng Spring:

~~~java
@Async("appExecutor")
public CompletableFuture<String> export(String reportId) {
    // Công việc chạy trong executor được chọn bởi @Async.
    return CompletableFuture.completedFuture("exported:" + reportId);
}
~~~

Đây là **phương thức minh họa bên trong một Spring-managed bean**, không phải chương trình độc lập. Cần bật `@EnableAsync`, có bean executor tên `appExecutor` và gọi phương thức thông qua Spring proxy. `@Async` không định nghĩa chu kỳ thời gian; mỗi lần bên ngoài gọi `export("r1")` sẽ yêu cầu thực thi một tác vụ.

Lưu ý: gọi `this.export(...)` từ chính instance thường **bỏ qua proxy trong chế độ proxy mặc định**, nên có thể không chuyển sang executor. Phương thức `@Async` trả về `void`, `Future` hoặc `CompletableFuture` (tùy API); đối với kiểu có Future, caller có thể theo dõi kết quả/lỗi, nhưng chờ bằng `join()`/`get()` sẽ khiến caller bị chặn. Exception của phương thức async trả `void` cần cơ chế theo dõi/xử lý lỗi phù hợp.

## 3. TaskScheduler: “hãy kích hoạt tác vụ theo lịch”

`TaskScheduler` có các nhóm API (chữ ký rút gọn theo Spring Framework 6.x):

~~~java
ScheduledFuture<?> schedule(Runnable task, Instant startTime);
ScheduledFuture<?> schedule(Runnable task, Trigger trigger);
ScheduledFuture<?> scheduleAtFixedRate(Runnable task, Duration period);
ScheduledFuture<?> scheduleWithFixedDelay(Runnable task, Duration delay);
~~~

Đây là **các chữ ký minh họa**, thuộc interface `TaskScheduler` trong Spring, không phải chương trình Java độc lập. Các overload cho phép định nghĩa thời điểm bắt đầu (`Instant`), chu kỳ (`Duration`) hoặc một chiến lược xác định lần chạy tiếp theo (`Trigger`). `CronTrigger` có thể biểu diễn lịch theo giờ/ngày trong tuần; `PeriodicTrigger` biểu diễn chu kỳ và có thể áp dụng qua interface `Trigger`.

- **Một lần tại thời điểm cụ thể:** `schedule(task, instant)`. Nếu thời điểm đã qua, việc thực thi có thể được đưa vào lịch sớm nhất có thể theo implementation; không dùng nó như bộ hẹn giờ chính xác tuyệt đối.
- **Fixed rate:** lịch nhắm tới khoảng cách đều giữa các **thời điểm bắt đầu**; nếu công việc quá lâu hoặc scheduler bận, lần chạy thực tế có thể muộn.
- **Fixed delay:** chờ hết một khoảng delay **sau khi lần chạy trước kết thúc** rồi mới chạy tiếp.
- **Cron/custom trigger:** lần chạy tiếp theo phụ thuộc biểu thức thời gian hoặc logic tính lịch; timezone và thay đổi giờ mùa hè có thể ảnh hưởng hành vi.

Các lời gọi lập lịch trả handle `ScheduledFuture<?>` để kiểm tra/cancel ở phạm vi mà implementation hỗ trợ. Đối với lịch lặp lại, Future không mang nghĩa “đã hoàn thành toàn bộ công việc định kỳ”; `cancel(...)` dừng việc lập lịch về sau và có thể yêu cầu ngắt công việc đang chạy, nhưng **không bảo đảm rollback một side effect đã xảy ra**. Với trigger không còn thời điểm hợp lệ, việc đặt lịch có thể trả `null`.

### 3.1. Fixed-rate và fixed-delay không giống nhau

Giả sử thời lượng một lần chạy là **8 giây**, chu kỳ đặt là **5 giây**, không tính độ trễ bổ sung:

| Cách lập lịch | Ý nghĩa | Mốc minh họa |
| --- | --- | --- |
| Fixed rate | Các thời điểm bắt đầu mục tiêu cách nhau 5 giây; lần đến hạn bị muộn nếu lần trước còn chạy | Dự kiến 0s, 5s, 10s...; nếu chỉ có một job tuần tự, thực tế có thể bắt đầu khoảng 0s, 8s, 16s... |
| Fixed delay | Chờ 5 giây sau **mỗi lần kết thúc** | Bắt đầu khoảng 0s → kết thúc 8s → bắt đầu 13s → kết thúc 21s → bắt đầu 26s |
| Cron | Khớp lịch trên đồng hồ theo biểu thức, không tính từ thời lượng tác vụ | Ví dụ 09:00 các ngày làm việc; nếu đang quá tải, cần hiểu chính sách lần chạy bị lỡ |

Các mốc trên chỉ giúp hình dung, không phải cam kết thời gian thực. `ThreadPoolTaskScheduler` truyền thống dùng `ScheduledThreadPoolExecutor`: các lần thực thi của **cùng một periodic task đã đăng ký** không tự chồng nhau trong executor này; tuy nhiên **nhiều đăng ký lịch khác nhau**, nhiều instance ứng dụng, hoặc callback chủ động gửi việc qua executor khác vẫn có thể khiến nghiệp vụ chạy đồng thời.

### 3.2. `@Scheduled` và cron

Ví dụ phương thức Spring-managed bean:

~~~java
@Scheduled(fixedDelay = 10_000, initialDelay = 2_000)
public void pollStatus() {
    // Mỗi lần kết thúc pollStatus(), đợi thêm 10 giây rồi gọi lần tiếp theo.
}
~~~

Hoặc một lịch cố định theo giờ Việt Nam:

~~~java
@Scheduled(cron = "0 0 9 * * MON-FRI", zone = "Asia/Ho_Chi_Minh")
public void prepareDailyReport() {
    // 09:00 thứ Hai đến thứ Sáu, theo múi giờ đã chỉ định.
}
~~~

Hai đoạn là **phương thức minh họa**, đặt trong các Spring bean và cần `@EnableScheduling`; không độc lập chạy bằng `javac`. Biểu thức cron của Spring dùng **6 trường**: giây, phút, giờ, ngày trong tháng, tháng, ngày trong tuần. `@Scheduled` được Spring kích hoạt theo lịch, nên phương thức thông thường **không nhận tham số nghiệp vụ từ caller**. Khác `@Async`, không cần có người gọi phương thức mỗi lần chạy.

**Không hiểu `fixedDelay` là khoảng giữa hai lần bắt đầu.** Định nghĩa đúng là khoảng sau **kết thúc callback mà scheduler trực tiếp quản lý**. Nếu callback chỉ submit một tác vụ nền rồi trả về, scheduler có thể xem callback đã xong dù tác vụ nền vẫn đang chạy; chi tiết này rất quan trọng khi kết hợp hai abstraction.

## 4. Mối quan hệ giữa interface, implementation và annotation

~~~text
A. Yêu cầu phát sinh từ nghiệp vụ
HTTP / service method / event
          |
          v
  TaskExecutor.execute(task)
          |
          v
  ThreadPoolTaskExecutor
          |
          v
    Worker thực thi

B. Công việc cần chạy theo thời điểm
Instant / fixed-rate / fixed-delay / CronTrigger
          |
          v
    TaskScheduler
          |
          v
  ThreadPoolTaskScheduler
          |
          v
    Callback được kích hoạt

C. Kết hợp khi có công việc nặng
TaskScheduler --> callback ngắn --> TaskExecutor --> worker làm việc
                         |
                         +--> callback xong KHÔNG có nghĩa worker xong
~~~

`@Async` liên quan đến việc **chuyển lời gọi phương thức sang executor**. `@Scheduled` liên quan đến việc **đăng ký một lịch gọi phương thức**. Cả hai đều là tính năng do Spring quản lý, nhưng dùng các bean và chính sách khác nhau. `@EnableAsync` không thay thế `@EnableScheduling`; bật scheduling cũng không tự biến mọi phương thức thành async.

### 4.1. Có implementation làm được cả hai việc không?

Có. Ví dụ, `ThreadPoolTaskScheduler` truyền thống cũng hỗ trợ một số hợp đồng thực thi tác vụ ngoài `TaskScheduler`. Vì thế không nên định nghĩa khác biệt theo kiểu “hai interface không thể cùng tồn tại trong một object”.

Tuy nhiên việc dùng **riêng** `ThreadPoolTaskExecutor` cho khối lượng blocking/CPU-bound và `ThreadPoolTaskScheduler` cho điều phối thời gian có thể dễ kiểm soát hơn. Tác vụ chạy lâu trực tiếp trên scheduler chiếm scheduler worker, khiến các lịch khác bị chậm. Sự tách biệt là một quyết định kiến trúc có lý do, không phải ràng buộc bắt buộc của Spring.

## 5. Java 17: ví dụ chạy độc lập để hiểu “execute” và “schedule”

Trước khi kết nối với Spring, ta có thể nhìn ý tưởng tương đương trong Java chuẩn: `ExecutorService` tiếp nhận công việc, `ScheduledExecutorService` hẹn công việc. Ví dụ này **không sử dụng Spring** nhưng cho phép kiểm chứng sự khác biệt bằng JDK 17.

Tạo tệp `ExecutorVsSchedulerDemo.java`:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;

public class ExecutorVsSchedulerDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        ScheduledExecutorService scheduler = Executors.newSingleThreadScheduledExecutor();
        try {
            CountDownLatch firstDone = new CountDownLatch(1);
            executor.execute(() -> {
                System.out.println("executor: task completed");
                firstDone.countDown();
            });
            if (!firstDone.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Executor task timed out");
            }

            ScheduledFuture<?> later = scheduler.schedule(
                    () -> System.out.println("scheduler: task completed"),
                    100, TimeUnit.MILLISECONDS);
            later.get(5, TimeUnit.SECONDS);
            System.out.println("main: finished");
        } finally {
            executor.shutdownNow();
            scheduler.shutdownNow();
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 ExecutorVsSchedulerDemo.java
java ExecutorVsSchedulerDemo
~~~

Kết quả đã kiểm chứng trên OpenJDK (thứ tự được bảo đảm bằng `CountDownLatch` và `Future.get()`):

~~~text
executor: task completed
scheduler: task completed
main: finished
~~~

`executor.execute(...)` giao một việc để thực hiện, còn `scheduler.schedule(..., 100, MILLISECONDS)` đặt việc thứ hai chạy **sau ít nhất khoảng trễ đã yêu cầu** (thời gian thực tế phụ thuộc lịch hệ điều hành). `CountDownLatch` đảm bảo việc thứ nhất đã xong mới đặt lịch cho việc thứ hai; `later.get(...)` chờ việc đã hẹn hoàn tất. Chương trình hủy nguồn lực trong `finally`. Trong Spring, implementation có thể bọc hoặc quản lý các executor Java này, nhưng API của Spring cung cấp sự trừu tượng để không gắn trực tiếp nghiệp vụ vào cách tạo luồng.

## 6. Ví dụ Spring Framework: cấu hình cả executor và scheduler

Các đoạn dưới đây dành cho dự án **Java 17+, Spring Framework 6.x** có `spring-context` trên classpath và component scanning; có thể dùng trong Spring Boot 3.x. Chúng là **mã tích hợp nhiều tệp**; không thể chỉ biên dịch một tệp bằng `javac` nếu thiếu Spring dependencies.

### 6.1. Cấu hình hai bean với trách nhiệm rõ ràng

Tệp `ConcurrencyConfig.java`, trong package ví dụ `example.concurrency`:

~~~java
package example.concurrency;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;

@Configuration
@EnableAsync
@EnableScheduling
public class ConcurrencyConfig {
    @Bean("appExecutor")
    public ThreadPoolTaskExecutor appExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(32);
        executor.setThreadNamePrefix("work-");
        return executor;
    }

    @Bean("taskScheduler")
    public ThreadPoolTaskScheduler taskScheduler() {
        ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(2);
        scheduler.setThreadNamePrefix("schedule-");
        return scheduler;
    }
}
~~~

- Bean `appExecutor` dùng cho `@Async("appExecutor")`; `4/8/32` chỉ là thông số minh họa, phải tuning theo tải, thời gian xử lý, bộ nhớ và giới hạn dịch vụ phía sau.
- Bean `taskScheduler` là scheduler duy nhất và mang tên thông dụng mà cơ chế `@Scheduled` của Spring có thể tìm thấy. `setPoolSize(2)` giới hạn concurrency của các callback chạy trực tiếp trong scheduler pool, không phải số lần thực thi nghiệp vụ mà các callback có thể submit sang executor.
- `@EnableAsync` bật xử lý annotation async; `@EnableScheduling` bật xử lý annotation scheduled. Việc đặt tên và chọn bean cụ thể tránh phụ thuộc vào các mặc định có thể thay đổi tùy cách cấu hình Spring Boot.
- Để Spring tự quản lý lifecycle, dùng các bean trong application context. Không tự tạo hàng loạt scheduler/executor thô mà quên shutdown khi ứng dụng dừng.

### 6.2. Tác vụ được yêu cầu bất đồng bộ

Tệp `ReportWorker.java`:

~~~java
package example.concurrency;

import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class ReportWorker {
    @Async("appExecutor")
    public CompletableFuture<String> generate(String reportId) {
        // Minh họa thao tác nghiệp vụ; thay bằng xử lý thật với timeout hợp lý.
        return CompletableFuture.completedFuture("generated:" + reportId);
    }
}
~~~

Khi một controller/service khác gọi `reportWorker.generate("R-7")` qua bean Spring, tác vụ được submit vào `appExecutor`. Người gọi có thể tiếp tục xử lý và nhận `CompletableFuture<String>`. Không có lịch chạy định kỳ trong method này; **một lời gọi tương ứng một lần yêu cầu công việc**. Dù return value của method minh họa là `completedFuture`, bản thân lời gọi `@Async` vẫn được Spring proxy chuyển sang executor nếu wiring đúng.

### 6.3. Scheduler quyết định khi nào kích hoạt việc

Tệp `ReportSchedule.java`:

~~~java
package example.concurrency;

import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class ReportSchedule {
    private final ReportWorker reportWorker;

    public ReportSchedule(ReportWorker reportWorker) {
        this.reportWorker = reportWorker;
    }

    @Scheduled(fixedDelay = 10_000, initialDelay = 2_000)
    public void requestReport() {
        reportWorker.generate("periodic")
                .whenComplete((result, error) -> {
                    if (error != null) {
                        System.err.println("Report failed: " + error.getMessage());
                    } else {
                        System.out.println(result);
                    }
                });
    }
}
~~~

Một lần chạy điển hình:

1. `taskScheduler` gọi `requestReport()` sau lần trễ khởi đầu.
2. Callback gọi sang **bean khác** `ReportWorker`, vì vậy lời gọi `@Async` đi qua Spring proxy.
3. `appExecutor` nhận nhiệm vụ và worker thực hiện `generate(...)`.
4. `requestReport()` trở về sau khi gửi tác vụ và gắn callback hoàn thành, không chờ báo cáo thật sự xong.
5. `fixedDelay=10_000` tính từ **lúc `requestReport()` hoàn tất**; nó **không đảm bảo** hai lượt `generate(...)` cách nhau 10 giây hoặc không chồng lấn.

Ví dụ minh họa đầy đủ cách hai abstraction phối hợp. Trong sản phẩm thật, nếu **không cho phép hai báo cáo xử lý đồng thời**, cần kiểm soát một-job-at-a-time bằng trạng thái `in-flight`, giới hạn nhận việc hoặc cơ chế khóa phù hợp; không chỉ dựa vào `fixedDelay` trên callback gửi việc. Tương tự, queue `appExecutor` có thể đầy và lời submit có thể bị từ chối; cần quan sát lỗi và chính sách xử lý cụ thể.

### 6.4. Dùng TaskScheduler trực tiếp khi lịch đến từ dữ liệu nghiệp vụ

`@Scheduled` thuận tiện cho lịch tương đối cố định bằng annotation. Khi thời điểm chạy là dữ liệu runtime (ví dụ “gửi thông báo vào lúc khách hàng đã chọn”), có thể dùng API `TaskScheduler`:

~~~java
package example.concurrency;

import java.time.Instant;
import java.util.concurrent.ScheduledFuture;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.core.task.TaskExecutor;
import org.springframework.scheduling.TaskScheduler;
import org.springframework.stereotype.Component;

@Component
public class DeferredTaskService {
    private final TaskScheduler scheduler;
    private final TaskExecutor executor;

    public DeferredTaskService(
            @Qualifier("taskScheduler") TaskScheduler scheduler,
            @Qualifier("appExecutor") TaskExecutor executor) {
        this.scheduler = scheduler;
        this.executor = executor;
    }

    public ScheduledFuture<?> scheduleDispatch(Instant when, Runnable job) {
        return scheduler.schedule(() -> executor.execute(job), when);
    }
}
~~~

Đây cũng là **mã tích hợp Spring**, không phải ví dụ `javac` độc lập. `scheduleDispatch(when, job)` trả về handle của **callback gửi tác vụ**; nếu callback đã submit thành công, `ScheduledFuture<?>` có thể đã hoàn thành dù `job` còn đang chạy trong `appExecutor`. Không dùng handle đó làm bằng chứng xử lý nghiệp vụ đã thành công. Nếu muốn theo dõi tiến độ/kết quả thật, thiết kế thêm `Future`, job id, trạng thái lưu trữ hoặc callback hoàn thành thuộc executor. Việc hủy lịch chỉ có hiệu lực phù hợp với trạng thái chưa kích hoạt/đã kích hoạt, không tự động hủy mọi tác vụ nền đã được submit.

Lịch lưu trong bộ nhớ scheduler cũng không phải **lịch bền vững**: ứng dụng restart có thể mất đăng ký một lần chưa được khôi phục. Khi lịch là cam kết nghiệp vụ, cần lưu dữ liệu lịch bền vững và phục hồi/điều phối lại theo thiết kế.

## 7. Chọn đúng abstraction cho tình huống thực tế

| Tình huống | Dùng gì? | Vì sao? |
| --- | --- | --- |
| API vừa nhận yêu cầu xuất file và trả response sớm | `TaskExecutor` hoặc `@Async` | Công việc xuất hiện khi có request, không cần trigger thời gian |
| Sau 30 phút mới thực hiện một thao tác | `TaskScheduler.schedule(..., Instant)` | Có thời điểm thực hiện trong tương lai |
| Cứ 10 giây kiểm tra trạng thái | `@Scheduled(fixedDelay=...)` / `TaskScheduler` | Muốn tự động kích hoạt lặp lại |
| 09:00 mỗi ngày làm việc tổng hợp báo cáo | Cron trên `TaskScheduler` / `@Scheduled(cron=...)` | Lịch theo thời gian trên đồng hồ và timezone |
| Scheduler phát hiện dữ liệu mới rồi cần xử lý nhiều tác vụ nặng | `TaskScheduler` + `TaskExecutor` | Một lớp điều phối nhịp, lớp kia quản lý concurrency công việc |
| Controller gọi đồng thời nhiều bước I/O có thể chạy độc lập | `TaskExecutor` hoặc cơ chế bất đồng bộ thích hợp | Điều phối song song theo yêu cầu, không phải lịch định kỳ |
| Nhiều instance cần **duy nhất một** lượt chạy toàn cụm | Scheduler **kèm cơ chế điều phối phân tán** | `@Scheduled` mặc định đăng ký trên mỗi application context, không tự cung cấp exactly-once toàn cụm |

Đừng biến mọi tác vụ chạy nền thành `@Scheduled` chỉ vì nó ở background. Nếu không có nhu cầu **thời gian kích hoạt**, một executor đủ. Ngược lại, nếu phải chạy lại theo lịch, một executor thuần không tự quản lý cron/độ trễ.

## 8. Giới hạn, lỗi thường gặp và cách chẩn đoán

### 8.1. “Đã dùng @Async nhưng vẫn chạy trên caller thread”

Kiểm tra `@EnableAsync`, vị trí bean do Spring quản lý, tên executor và lời gọi thông qua proxy. Self-invocation như `this.generate()` trong cùng bean có thể bypass interception. Thêm `@Scheduled` không làm `@Async` hoạt động trở lại. Ghi thread name và kiểm tra stack chỉ để xác nhận wiring, tránh phụ thuộc vào tên luồng như một hợp đồng API.

### 8.2. “Đã dùng @Scheduled nhưng lịch không chạy”

Kiểm tra `@EnableScheduling`, bean có thực sự được đăng ký, cron có đúng **6 trường** và timezone không, ứng dụng có đang chạy, scheduler có bị block hoặc ngừng không. Tác vụ ném exception cần được ghi nhận qua error handling/metrics. Không giả định một lịch sẽ chạy chính xác từng mili giây hoặc các lần bị trễ được tự chạy bù giống nhau trong mọi Trigger.

### 8.3. “Tăng pool scheduler thì tác vụ async có nhanh hơn?”

Không nhất thiết. `taskScheduler.setPoolSize(...)` tăng worker có thể dùng cho callback của scheduler; `appExecutor.setCorePoolSize(...)`/`setMaxPoolSize(...)` ảnh hưởng executor nhận tác vụ nghiệp vụ. Nếu callback chỉ submit nhanh vào executor, bottleneck có thể ở `appExecutor`, DB pool hoặc dịch vụ bên ngoài. Đo đúng queue và độ trễ ở từng tầng; tăng một pool không thay thế kiểm tra nút thắt phía sau.

### 8.4. “Fixed-delay đã cấu hình nhưng các job vẫn chồng nhau”

Nếu phương thức scheduled **trực tiếp chạy đồng bộ toàn bộ công việc**, fixed-delay tính từ khi công việc đó kết thúc. Nếu phương thức scheduled **chỉ gọi `@Async`** và trả về sớm, fixed-delay chỉ bao quanh lượt *dispatch*. Một công việc vẫn chạy khi lượt dispatch tiếp theo đến. Giải pháp là chờ có kiểm soát nếu phù hợp, kiểm soát `in-flight` trước khi submit hoặc dùng mô hình hàng đợi/idempotency/lock phân tán theo yêu cầu. Đừng chặn scheduler vô hạn để “chắc chắn không chồng lấn”.

### 8.5. “TaskScheduler và TaskExecutor có thể deadlock/cạn luồng không?”

Có. Nếu mọi scheduler thread đều chờ `Future.get()` từ những task mà executor không còn tài nguyên chạy, lịch bị trì hoãn; nếu worker trong executor lại chờ chính scheduler để giải phóng tài nguyên, có thể xuất hiện chu trình phụ thuộc. Không chặn executor worker chờ task con của cùng pool; không giữ khóa qua I/O chặn lâu; đặt timeout và kiểm soát giới hạn queue/connection.

### 8.6. “Một job scheduled chạy trên nhiều pod có bình thường không?”

Có thể hoàn toàn bình thường: mỗi instance Spring có `@EnableScheduling` và bean `@Scheduled` sẽ đăng ký lịch của nó. `TaskScheduler` không tự thực hiện leader election. Với yêu cầu chỉ một lần toàn cụm, cần thiết kế distributed lock, leader election, job store hoặc hệ thống điều phối phù hợp và bảo vệ idempotency. Cần làm rõ khác biệt giữa “lịch chạy đúng giờ trên từng instance” và “xử lý đúng một lần toàn hệ thống”.

### 8.7. Đo những gì?

- **Ở scheduler:** số callback kích hoạt, thời điểm dự kiến và thực tế, độ trễ kích hoạt, thời lượng callback, lần chạy lỗi, lần chạy bị bỏ lỡ theo trigger.
- **Ở executor:** active threads, kích thước pool, queue depth/queue wait, số tác vụ hoàn tất, rejection, duration và exception.
- **Ở nghiệp vụ:** số job đang chạy, thời gian end-to-end, số job thành công/thất bại, kết quả side effect, khả năng retry.
- **Ở downstream:** connection pool, timeout, CPU quota, độ trễ DB/HTTP; nhiều worker không tạo thêm năng lực cho một dịch vụ bị giới hạn.

Với các API async, callback lỗi phải ghi nhận exception. Với lịch một lần quan trọng, phải nghĩ tới restart và cancel. Với tác vụ lặp lại, cần chọn chính sách khi trễ, chống chạy chồng, retry/backoff và shutdown một cách rõ ràng.

## 9. Câu hỏi tự kiểm tra

**1. Có phải TaskExecutor luôn tạo thread mới?** Không. `TaskExecutor` là hợp đồng giao tác vụ. `ThreadPoolTaskExecutor` thường tái sử dụng worker, còn implementation khác có thể dùng chiến lược riêng.

**2. Muốn chạy job lúc 09:00 thứ Hai–thứ Sáu nên dùng gì?** `TaskScheduler` với cron/`@Scheduled(cron=...)` và timezone rõ ràng. Executor có thể được dùng thêm nếu callback cần offload việc nặng.

**3. `@Async` làm cho method tự lặp sau 10 giây không?** Không. Nó gắn với việc submit mỗi lần method được gọi, không phải cơ chế tính thời điểm gọi lại.

**4. `fixedDelay=10_000` trên callback chỉ submit một `@Async` task có bảo đảm cách nhau 10 giây giữa hai lần task *kết thúc* không?** Không. Delay tính sau khi callback scheduled trở về; worker xử lý thật có thể tiếp tục chạy.

**5. `ScheduledFuture<?>` trả từ `scheduler.schedule(() -> executor.execute(job), when)` đại diện cho điều gì?** Việc đặt lịch và hoàn thành callback **submit job**; không bảo đảm `job` đã hoàn tất thành công trong executor.

**6. Nếu scheduler có 2 threads và executor có 8 workers, hệ thống có tổng cộng chỉ 2 công việc nghiệp vụ cùng lúc không?** Không. Nếu scheduler chỉ dispatch ngắn, các công việc nghiệp vụ có thể chạy trong executor với giới hạn của executor và downstream. Cần phân biệt số callback đang chạy với số job đã gửi.

**7. Nếu nhiều replica đều có cùng `@Scheduled`, Spring có tự đảm bảo toàn cụm chỉ chạy một lần không?** Không. Phải có cơ chế điều phối phân tán và thiết kế chống thực thi trùng khi nghiệp vụ yêu cầu.

## 10. Tài liệu tham khảo

- Spring Framework Reference — Task Execution and Scheduling: https://docs.spring.io/spring-framework/reference/integration/scheduling.html
- Spring Framework API — TaskExecutor: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/core/task/TaskExecutor.html
- Spring Framework API — TaskScheduler: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/scheduling/TaskScheduler.html
- Spring Framework API — ThreadPoolTaskExecutor: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html
- Spring Framework API — ThreadPoolTaskScheduler: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskScheduler.html
- Java SE 17 API — ScheduledExecutorService: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledExecutorService.html
