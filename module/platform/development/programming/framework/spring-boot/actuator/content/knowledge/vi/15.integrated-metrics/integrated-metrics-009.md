# Theo dõi executor, task scheduler và hàng đợi công việc

## 1. Vì sao API nhanh nhưng công việc vẫn chậm?

Một API nhận yêu cầu tạo báo cáo, chuyển việc cho luồng nền rồi trả về ngay. Thời gian HTTP chỉ vài chục mili giây, nhưng người dùng phải đợi nhiều phút mới nhận được báo cáo. HTTP metrics chưa phản ánh toàn bộ đường đi của công việc:

```text
Tiếp nhận → gửi vào executor → chờ được chạy → thực thi → thành công hoặc lỗi
                                  ↑
                   Scheduler còn phải đợi đúng thời điểm
```

**Bộ thực thi (executor)** nhận tác vụ và bố trí luồng chạy. **Nhóm luồng (thread pool)** tái sử dụng một số luồng. **Hàng đợi (work queue)** giữ những tác vụ chưa bắt đầu. **Bộ lập lịch (task scheduler)** quyết định lúc một tác vụ đủ điều kiện chạy.

Trong phạm vi metrics tích hợp của Spring Boot Actuator, cần trả lời bốn câu hỏi:

1. Bao nhiêu luồng đang làm việc, và pool còn khả năng tăng thêm không?
2. Bao nhiêu tác vụ đang chờ, và chúng chờ bao lâu?
3. Công việc hoàn tất với tốc độ nào, có bị từ chối hoặc thất bại không?
4. Công việc định kỳ có bắt đầu đúng lịch và tạo ra kết quả mong muốn không?

Một biểu đồ số luồng không trả lời được cả bốn câu hỏi. Ta kết hợp số đo trạng thái của pool với số đo vòng đời công việc.

Bài sử dụng mô hình thread pool truyền thống trên Java 17+, tập trung Spring Boot 3.3.x, Spring Framework 6.1 và Micrometer 1.13. Phần thí nghiệm Java thuần chạy độc lập; các đoạn Spring được đặt trong ứng dụng Spring Boot có sẵn.

## 2. Hiểu quan hệ giữa luồng, hàng đợi và giới hạn pool

Với `ThreadPoolExecutor` thông thường, trình tự tiếp nhận khi pool đang hoạt động có thể hiểu như sau:

```text
Gửi tác vụ
  ├─ Số luồng < corePoolSize → tạo luồng
  └─ Đã đạt corePoolSize
       ├─ Hàng đợi nhận được → xếp hàng
       └─ Hàng đợi đầy
            ├─ Số luồng < maximumPoolSize → tạo thêm luồng
            └─ Đã đạt maximumPoolSize → áp dụng chính sách từ chối
```

Pool còn kiểm tra trạng thái tắt và các thay đổi đồng thời; sơ đồ trên là mô hình để đọc metrics, không phải mã thay thế thuật toán JDK.

Ví dụ `core=2`, `max=4`, hàng đợi chứa tối đa hai việc, mọi việc đều bị giữ lại để chưa kết thúc:

| Số việc đã gửi | Luồng đang chạy việc | Việc chờ | Ý nghĩa |
| --- | ---: | ---: | --- |
| 2 | 2 | 0 | Dùng hết hai luồng lõi |
| 4 | 2 | 2 | Ưu tiên xếp hàng |
| 6 | 4 | 2 | Hàng đợi đầy nên pool tăng đến bốn luồng |
| 7 | 4 | 2 | Việc mới bị từ chối nếu dùng chính sách ném ngoại lệ |

Đây là tình huống có kiểm soát. Ngoài thực tế, việc kết thúc xen kẽ lúc gửi, nên không suy số lượng chính xác từ số lần gọi `execute`.

Ba loại hàng đợi dẫn đến cách đọc khác nhau:

- **Có giới hạn:** theo dõi số việc chờ và chỗ trống để thấy áp lực tiếp nhận.
- **Không giới hạn thực tế:** hàng đợi có thể tăng rất lớn, pool thường không tăng vượt số luồng lõi vì hàng đợi vẫn nhận việc. Tăng `maxPoolSize` chưa chắc giúp.
- **Bàn giao trực tiếp bằng `SynchronousQueue`:** không lưu công việc như một hàng đợi thông thường. `size=0` và `remainingCapacity=0` không chứng minh hệ thống rảnh; phải xem luồng, độ trễ và số lần từ chối.

Cơ chế này được mô tả trong [JDK 21 — ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html).

## 3. Actuator tự thu thập được gì?

Spring Boot 3.3 tự gắn bộ đo cho các bean `ThreadPoolTaskExecutor` và `ThreadPoolTaskScheduler` có executor nền đã được khởi tạo. Tag `name` được lấy từ tên bean. Một executor tự tạo bằng `new` rồi giấu trong service không tự nhiên trở thành bean được cơ chế này phát hiện.

Cần phân biệt hai thao tác của Micrometer:

- `new ExecutorServiceMetrics(pool, name, tags).bindTo(registry)` đọc trạng thái executor.
- `ExecutorServiceMetrics.monitor(...)` trả về đối tượng bọc có thêm phép đo thời gian; tác vụ phải thực sự đi qua đối tượng được trả về.

Spring Boot 3.3 dùng cách `bindTo` cho bean pool. Vì vậy không mặc định khẳng định có timer `executor` hoặc `executor.idle` chỉ vì đã thêm Actuator. Xem [mã TaskExecutorMetricsAutoConfiguration của Spring Boot 3.3.13](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/metrics/task/TaskExecutorMetricsAutoConfiguration.java).

Các số đo dưới đây áp dụng cho `ThreadPoolExecutor` mà binder truy cập được:

| Tên trong MeterRegistry / Actuator | Loại | Câu hỏi được trả lời |
| --- | --- | --- |
| `executor.active` | Gauge | Có bao nhiêu luồng đang thực thi tác vụ? |
| `executor.pool.size` | Gauge | Hiện pool có bao nhiêu luồng? |
| `executor.pool.core` | Gauge | Số luồng lõi được cấu hình là bao nhiêu? |
| `executor.pool.max` | Gauge | Giới hạn luồng tối đa được cấu hình là bao nhiêu? |
| `executor.queued` | Gauge | Hàng đợi hiện chứa bao nhiêu tác vụ? |
| `executor.queue.remaining` | Gauge | Hàng đợi còn khả năng nhận thêm bao nhiêu phần tử? |
| `executor.completed` | FunctionCounter | Bộ đếm hoàn tất tích lũy của executor là bao nhiêu? |

`active`, `queued` và `completed` dựa trên thống kê xấp xỉ của executor. Hai lần đọc liên tiếp có thể gặp hai trạng thái khác nhau.

**Gauge** cho biết trạng thái tại lúc quan sát; một đợt hàng đợi tăng rồi giảm giữa hai lần thu thập có thể không xuất hiện trên biểu đồ. **FunctionCounter** đọc giá trị tích lũy từ đối tượng nền; khi tiến trình khởi động lại, bộ đếm cũng bắt đầu lại.

`executor.completed` không phải bộ đếm nghiệp vụ thành công: tác vụ kết thúc bằng lỗi vẫn có thể được tính là đã hoàn tất xử lý bởi executor. Nó cũng không đại diện mọi việc bị từ chối, bị loại khỏi queue hoặc bị hủy trước khi chạy.

Đối chiếu [ExecutorServiceMetrics 1.13.13](https://raw.githubusercontent.com/micrometer-metrics/micrometer/v1.13.13/micrometer-core/src/main/java/io/micrometer/core/instrument/binder/jvm/ExecutorServiceMetrics.java) và [Micrometer — Gauges](https://docs.micrometer.io/micrometer/reference/concepts/gauges.html).

## 4. Cấu hình một pool và một scheduler có tên rõ ràng

Ứng dụng cần các dependency sau; để Spring Boot quản lý phiên bản tương thích:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
```

Đây là phần `dependencies` bổ sung trong dự án đã áp dụng plugin/BOM Spring Boot, không phải toàn bộ `build.gradle`.

Cấu hình dưới đây phục vụ thí nghiệm trên máy cá nhân:

```yaml
management:
  server:
    port: 8081
    address: 127.0.0.1
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
```

`metrics` dùng để kiểm tra từng meter; `prometheus` phục vụ hệ thống thu thập. Trong môi trường triển khai, chọn mạng quản trị và cơ chế xác thực phù hợp thay vì mở tùy tiện các endpoint. Nếu ứng dụng đã có Spring Security, yêu cầu truy cập vẫn chịu cấu hình bảo mật của ứng dụng.

Tạo `WorkConfiguration.java` trong package được ứng dụng quét:

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import java.util.concurrent.RejectedExecutionException;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;

@Configuration(proxyBeanMethods = false)
@EnableScheduling
public class WorkConfiguration {

    @Bean
    public ThreadPoolTaskExecutor jobsExecutor(MeterRegistry registry) {
        Counter rejected = Counter.builder("app.jobs.rejected")
                .tag("pool", "jobs")
                .register(registry);

        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(2);
        pool.setMaxPoolSize(4);
        pool.setQueueCapacity(20);
        pool.setThreadNamePrefix("jobs-");
        pool.setRejectedExecutionHandler((task, executor) -> {
            rejected.increment();
            throw new RejectedExecutionException("jobs executor rejected task");
        });
        return pool;
    }

    @Bean
    public ThreadPoolTaskScheduler taskScheduler() {
        ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(2);
        scheduler.setThreadNamePrefix("schedule-");
        scheduler.setRemoveOnCancelPolicy(true);
        return scheduler;
    }
}
```

Spring quản lý khởi tạo và hủy các bean này; không tự gọi `initialize()` trong phương thức `@Bean`. `@EnableScheduling` kích hoạt xử lý `@Scheduled`, còn việc khai báo một scheduler chưa tự tạo ra công việc định kỳ.

Ở đây có hai kiểu tên với hai mục đích:

- `name=jobsExecutor` và `name=taskScheduler` là tag metrics tích hợp, xuất phát từ tên bean.
- `jobs-` và `schedule-` là tiền tố tên luồng, giúp đọc log/thread dump; không thay thế tag `name`.
- `pool=jobs` là tag do ứng dụng chủ động đặt cho metrics nghiệp vụ.

`app.jobs.rejected` cũng là metric tự bổ sung, không thuộc nhóm `executor.*` mặc định. Nó đếm mọi lần handler trên được gọi, bao gồm lúc executor đã tắt; vì vậy phải phân biệt quá tải với việc gửi nhầm trong giai đoạn dừng. Khi đi qua `ThreadPoolTaskExecutor`, phía gọi có thể nhận `TaskRejectedException` của Spring.

Do ví dụ khai báo pool trực tiếp bằng setter, không giả định các thuộc tính `spring.task.execution.pool.*` tự sửa bean này. Các thuộc tính ấy dành cho cơ chế auto-configuration/builder có liên quan; một bean cấu hình thủ công phải được gắn cấu hình một cách chủ động.

Cần bảo đảm tác vụ thực sự dùng đúng pool. Ví dụ gọi trực tiếp `jobsExecutor.execute(...)` qua bean đã inject; nếu dùng `@Async` thì bật `@EnableAsync` và chỉ định `@Async("jobsExecutor")` trên phương thức được gọi qua proxy Spring. Gọi nội bộ cùng đối tượng có thể bỏ qua proxy. `CompletableFuture.runAsync(task)` không truyền executor sử dụng pool mặc định của JDK, không tự chuyển sang `jobsExecutor`.

Tham khảo [Spring Boot 3.3 — Task Execution and Scheduling](https://docs.spring.io/spring-boot/3.3/reference/features/task-execution-and-scheduling.html) và [ThreadPoolTaskExecutor 6.1.21](https://raw.githubusercontent.com/spring-projects/spring-framework/v6.1.21/spring-context/src/main/java/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.java).

## 5. Kiểm tra đúng pool qua Actuator

Khởi động ứng dụng, rồi gọi các lệnh sau; trên PowerShell có thể dùng `curl.exe` để tránh nhầm alias:

```bash
curl "http://127.0.0.1:8081/actuator/metrics"
curl "http://127.0.0.1:8081/actuator/metrics/executor.active?tag=name:jobsExecutor"
curl "http://127.0.0.1:8081/actuator/metrics/executor.queued?tag=name:jobsExecutor"
curl "http://127.0.0.1:8081/actuator/metrics/executor.queue.remaining?tag=name:jobsExecutor"
curl "http://127.0.0.1:8081/actuator/metrics/executor.completed?tag=name:jobsExecutor"
curl "http://127.0.0.1:8081/actuator/metrics/executor.active?tag=name:taskScheduler"
curl "http://127.0.0.1:8081/actuator/prometheus"
```

Khi chưa có việc, `executor.pool.size` có thể bằng 0 vì luồng thường được tạo khi cần; điều đó không có nghĩa bean không được đo.

Trong JSON của một gauge, tìm `measurements` với `statistic="VALUE"`. Với FunctionCounter, tìm `statistic="COUNT"`. Giá trị chạy thực tế phụ thuộc tải, không có một JSON số liệu cố định đúng cho mọi máy.

Nếu một meter có nhiều pool mà bỏ bộ lọc `tag=name:...`, endpoint metrics có thể cộng số đo của nhiều meter phù hợp. Con số tổng đó dễ che mất một pool nhỏ đang quá tải. Khi tìm lỗi, chọn đúng pool trước.

Tên dùng ở `/actuator/metrics` là tên có dấu chấm trong registry. Định dạng Prometheus thường chuyển thành:

| Actuator | Prometheus với binder tiêu chuẩn |
| --- | --- |
| `executor.active` | `executor_active_threads` |
| `executor.queued` | `executor_queued_tasks` |
| `executor.queue.remaining` | `executor_queue_remaining_tasks` |
| `executor.completed` | `executor_completed_tasks_total` |
| `executor.pool.size` | `executor_pool_size_threads` |
| `executor.pool.max` | `executor_pool_max_threads` |

Luôn xem nội dung endpoint của phiên bản đang chạy trước khi viết truy vấn. Không lấy tên `executor_active_threads` đưa vào đường dẫn `/actuator/metrics/...`.

Các quy tắc tra cứu và lọc tag được trình bày trong [Spring Boot 3.3 — Metrics endpoint](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html#actuator.metrics.endpoint).

## 6. Đo thời gian chờ, thời gian thực thi và kết quả công việc

Một tác vụ có thể chờ 30 giây rồi chạy trong 100 ms. Chỉ đo phần thân công việc sẽ bỏ mất phần lớn độ trễ mà người dùng cảm nhận.

Nên phân biệt:

```text
Thời gian chờ = lúc bắt đầu thực thi − lúc gửi việc
Thời gian thực thi = lúc kết thúc − lúc bắt đầu thực thi
Thời gian từ gửi đến kết thúc = thời gian chờ + thời gian thực thi
```

Ở đây “thời gian chờ” bao gồm chi phí chuyển giao và lập lịch từ khi gọi gửi việc, không khẳng định chỉ đo thời gian một phần tử nằm trong queue. Dùng đồng hồ đơn điệu cho khoảng thời gian trong cùng tiến trình để tránh ảnh hưởng của việc chỉnh đồng hồ hệ thống.

Có thể bọc một `ExecutorService` do ứng dụng sở hữu bằng `ExecutorServiceMetrics.monitor` để có các timer `executor` và `executor.idle`. Phải giữ và sử dụng chính đối tượng bọc; nếu vẫn gọi executor cũ thì các tác vụ ấy không đi qua phép đo thời gian. Không đăng ký lại chồng chéo cùng tên/tag lên pool mà Boot đã quản lý nếu chưa có thiết kế rõ ràng.

Một lựa chọn dễ kiểm soát là đo tại điểm gửi việc của ứng dụng. Tạo `MeasuredJobs.java` bên cạnh cấu hình ở trên:

```java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.stereotype.Component;

@Component
public class MeasuredJobs {
    private final ThreadPoolTaskExecutor executor;
    private final MeterRegistry registry;
    private final Timer queueWait;
    private final Timer success;
    private final Timer error;

    public MeasuredJobs(
            @Qualifier("jobsExecutor") ThreadPoolTaskExecutor executor,
            MeterRegistry registry) {
        this.executor = executor;
        this.registry = registry;
        this.queueWait = registry.timer("app.jobs.queue.wait", "pool", "jobs");
        this.success = registry.timer(
                "app.jobs.execution", "pool", "jobs", "outcome", "success");
        this.error = registry.timer(
                "app.jobs.execution", "pool", "jobs", "outcome", "error");
    }

    public void submit(Runnable work) {
        Timer.Sample waiting = Timer.start(registry);
        executor.execute(() -> {
            waiting.stop(queueWait);
            Timer.Sample running = Timer.start(registry);
            boolean succeeded = false;
            try {
                work.run();
                succeeded = true;
            } finally {
                running.stop(succeeded ? success : error);
            }
        });
    }
}
```

Ví dụ đo `Runnable` đồng bộ trong luồng worker. Nếu `work.run()` chỉ khởi động một tác vụ bất đồng bộ khác rồi trả về, timer dừng ở lúc trả về ấy; muốn đo toàn bộ phải dừng tại tín hiệu hoàn tất thật.

Ý nghĩa và giới hạn của đoạn đo:

- Timer thời gian chờ chỉ có mẫu khi việc bắt đầu chạy. Việc còn kẹt trong queue chưa đóng góp mẫu, nên phải đọc kèm `executor.queued`.
- Timer thực thi ghi cả nhánh thành công và nhánh thoát bằng lỗi; đoạn mã không nuốt ngoại lệ.
- Việc bị từ chối chưa chạy thân lambda nên không tạo mẫu hai timer này. Bộ đếm từ chối trong cấu hình xử lý trường hợp đó.
- Đây chưa phải sổ cái công việc bền vững. Muốn đối soát retry, hủy, mất việc khi tiến trình chết và kết quả nghiệp vụ phải có mô hình trạng thái riêng.
- Tag `pool` và `outcome` có tập giá trị nhỏ. Không gắn `taskId`, email, mã đơn hàng hoặc nội dung lỗi tùy ý vào tag.

Timer cung cấp số mẫu và tổng thời gian; phân vị cần cấu hình phù hợp. Một thời gian trung bình thấp vẫn có thể che những việc chờ rất lâu. Xem [Micrometer — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html).

Nếu muốn quan sát p95 thời gian chờ bằng Prometheus, có thể thêm:

```yaml
management:
  metrics:
    distribution:
      percentiles-histogram:
        "app.jobs.queue.wait": true
```

Hợp nhất phần này vào cấu hình `management` hiện có, không tạo hai khóa `management` trùng nhau. Histogram tạo thêm chuỗi dữ liệu cho mỗi tổ hợp tag; chỉ bật cho những timer cần phân tích phân bố.

## 7. Scheduler: có việc trong queue chưa chắc là chậm

`ThreadPoolTaskScheduler` thực thi công việc trên chính các luồng scheduler. Một công việc chặn lâu có thể làm các công việc khác bắt đầu muộn nếu không còn luồng trống. Xem [Spring Framework 6.1 — ThreadPoolTaskScheduler](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskScheduler.html).

Scheduler nền `ScheduledThreadPoolExecutor` dùng hàng đợi theo thời điểm. Việc hẹn chạy ngày mai vẫn nằm trong hàng đợi hôm nay. Vì vậy:

- `executor.queued{name="taskScheduler"} > 0` có thể hoàn toàn bình thường.
- Tăng số lịch hẹn khiến queue dài hơn mà chưa gây trễ.
- `executor.queue.remaining` rất lớn không chứng minh hệ thống có đủ năng lực chạy.
- `executor.pool.max` không phải thước đo khả năng tăng luồng hữu ích của scheduler kiểu này.
- Một tác vụ định kỳ chạy chậm không nhất thiết tạo thêm một phần tử queue cho mỗi chu kỳ bị trễ.

Với `ScheduledThreadPoolExecutor`, hai lượt của cùng một tác vụ định kỳ không chạy chồng lên nhau; điều này không ngăn các lịch đăng ký khác nhau hoặc công việc đã chuyển sang một executor khác chạy đồng thời. Queue không có giới hạn thực tế và khả năng thực thi chủ yếu do số luồng lõi quyết định. Các hành vi này được mô tả trong [JDK 21 — ScheduledThreadPoolExecutor](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ScheduledThreadPoolExecutor.html).

Cần thêm bằng chứng ở cấp công việc định kỳ:

| Số đo chủ động bổ sung | Ý nghĩa |
| --- | --- |
| Timer thời gian chạy | Mỗi lượt mất bao lâu? |
| Timer độ trễ bắt đầu | Lúc thực tế bắt đầu muộn hơn thời điểm dự kiến bao lâu? |
| Thời điểm thành công gần nhất | Công việc còn tạo kết quả đúng hạn không? |
| Số lượt thành công/lỗi | Công việc chạy nhưng có liên tục thất bại không? |

Đây là gợi ý thiết kế metrics ứng dụng, không phải danh sách meter có sẵn của mọi `@Scheduled` trong Boot 3.3.

Ví dụ lịch chu kỳ cố định (`fixedRate`) năm giây có các mốc dự kiến 0, 5, 10 giây; bắt đầu tại giây 13 cho mốc 10 nghĩa là trễ ba giây. Với khoảng nghỉ sau khi hoàn tất (`fixedDelay`), mốc dự kiến tiếp theo phải tính từ lần hoàn tất trước cộng khoảng nghỉ. Không lấy công thức `fixedRate` áp cho `fixedDelay`. Với cron phải dùng thời điểm do lịch cron cùng múi giờ tính ra.

Đo độ trễ theo mốc đã biết của chính lịch, tránh coi mọi khoảng chờ có chủ đích trước giờ hẹn là quá tải. Có thể đo tuổi lần thành công gần nhất bằng `thời gian hiện tại − thời điểm thành công gần nhất`, nhưng phải xử lý cả trường hợp chưa từng thành công và trường hợp series bị mất.

Với việc hẹn xa trong tương lai rồi bị hủy nhiều lần, `setRemoveOnCancelPolicy(true)` giúp loại bỏ phần tử đã hủy khỏi queue sớm. Việc bỏ khỏi queue không có nghĩa nghiệp vụ đã hoàn thành.

Nếu scheduler chỉ làm nhiệm vụ kích hoạt rồi chuyển việc nặng sang `jobsExecutor`, theo dõi cả hai nơi: lịch có thể kích hoạt đúng giờ trong khi queue của executor xử lý vẫn tăng. Khi đó cần phân biệt “đã kích hoạt”, “đã được tiếp nhận” và “đã hoàn tất”.

## 8. Thí nghiệm Java độc lập: bão hòa pool và lịch hẹn tương lai

Lưu nguyên chương trình sau thành `ExecutorQueueDemo.java`. Không cần Spring hay thư viện ngoài. Các latch giữ tác vụ đứng yên để kiểm tra trạng thái, tránh dùng `sleep` rồi đoán luồng đã chạy.

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.ScheduledThreadPoolExecutor;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class ExecutorQueueDemo {
    private static void await(CountDownLatch latch) throws InterruptedException {
        if (!latch.await(5, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Timed out waiting for workers");
        }
    }

    public static void main(String[] args) throws InterruptedException {
        CountDownLatch firstTwoStarted = new CountDownLatch(2);
        CountDownLatch fourStarted = new CountDownLatch(4);
        CountDownLatch release = new CountDownLatch(1);

        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                2, 4, 30, TimeUnit.SECONDS,
                new ArrayBlockingQueue<Runnable>(2),
                new ThreadPoolExecutor.AbortPolicy());

        Runnable blocked = () -> {
            firstTwoStarted.countDown();
            fourStarted.countDown();
            try {
                release.await();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        };

        try {
            pool.execute(blocked);
            pool.execute(blocked);
            await(firstTwoStarted);

            pool.execute(blocked);
            pool.execute(blocked);
            pool.execute(blocked);
            pool.execute(blocked);
            await(fourStarted);

            System.out.println("active=" + pool.getActiveCount());
            System.out.println("poolSize=" + pool.getPoolSize());
            System.out.println("queued=" + pool.getQueue().size());
            System.out.println("remaining=" + pool.getQueue().remainingCapacity());
            System.out.println("completedBefore=" + pool.getCompletedTaskCount());

            boolean rejected = false;
            try {
                pool.execute(blocked);
            } catch (RejectedExecutionException ex) {
                rejected = true;
            }
            System.out.println("seventhRejected=" + rejected);

            release.countDown();
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Pool did not terminate");
            }
            System.out.println("completedAfter=" + pool.getCompletedTaskCount());
        } finally {
            release.countDown();
            pool.shutdownNow();
        }

        ScheduledThreadPoolExecutor scheduler =
                new ScheduledThreadPoolExecutor(1);
        scheduler.setRemoveOnCancelPolicy(true);
        try {
            ScheduledFuture<?> future = scheduler.schedule(
                    () -> System.out.println("should not run"),
                    1, TimeUnit.DAYS);
            System.out.println("scheduledQueued=" + scheduler.getQueue().size());
            future.cancel(false);
            System.out.println("scheduledAfterCancel=" + scheduler.getQueue().size());
        } finally {
            scheduler.shutdownNow();
        }
    }
}
```

Biên dịch và chạy trên JDK 17 trở lên:

```bash
javac --release 17 ExecutorQueueDemo.java
java ExecutorQueueDemo
```

Stdout khi chương trình chạy thành công:

```text
active=4
poolSize=4
queued=2
remaining=0
completedBefore=0
seventhRejected=true
completedAfter=6
scheduledQueued=1
scheduledAfterCancel=0
```

Giải thích kết quả:

1. Hai việc đầu chiếm hai luồng lõi; latch xác nhận chúng đã bắt đầu.
2. Hai việc tiếp theo nằm trong queue; hai việc sau nữa làm pool tăng lên bốn luồng.
3. Bốn luồng đều chờ `release` nên các giá trị không đổi trong lúc in trạng thái.
4. Việc thứ bảy bị `AbortPolicy` từ chối, không tăng tổng hoàn tất.
5. Sau khi mở latch và đợi pool dừng, sáu việc được nhận đã hoàn tất.
6. Scheduler có một phần tử chờ dù việc đó còn một ngày mới đến hạn. Hủy cùng chính sách loại bỏ ngay làm queue về 0.

Thí nghiệm thứ hai là phản ví dụ trực tiếp cho suy luận “scheduler có queue tức là đang quá tải”.

## 9. Đọc biểu đồ và thiết lập cảnh báo có căn cứ

Các truy vấn sau dành cho Prometheus, giả định tên meter và tag đúng như ví dụ. Chúng là mẫu phân tích; ngưỡng phải dựa trên mục tiêu độ trễ và tải của hệ thống.

### 9.1. Luồng đang bận so với số luồng hiện có

```promql
executor_active_threads{name="jobsExecutor"}
/
clamp_min(executor_pool_size_threads{name="jobsExecutor"}, 1)
```

Tỷ lệ gần 1 nghĩa là phần lớn luồng hiện có đang chạy tác vụ; chưa chứng minh đã đạt giới hạn tối đa. Đọc kèm `executor_pool_max_threads`, queue và thời gian chờ. Luồng đang chờ I/O cũng có thể được tính là active.

### 9.2. Tỷ lệ sử dụng hàng đợi có giới hạn

```promql
executor_queued_tasks{name="jobsExecutor"}
/
clamp_min(
  executor_queued_tasks{name="jobsExecutor"}
  + executor_queue_remaining_tasks{name="jobsExecutor"},
  1
)
```

Chỉ dùng cho queue có giới hạn và có ý nghĩa dung lượng. Không dùng để kết luận mức đầy của `SynchronousQueue` hay queue lịch hẹn không giới hạn. Một lần thu thập các gauge cũng không phải ảnh chụp nguyên tử của executor đang thay đổi.

### 9.3. Tốc độ hoàn tất và từ chối

```promql
rate(executor_completed_tasks_total{name="jobsExecutor"}[5m])
```

```promql
increase(app_jobs_rejected_total{pool="jobs"}[5m]) > 0
```

Bộ đếm thô tăng là bình thường; cần xem tốc độ thay đổi. `rate`/`increase` cần đủ mẫu và có xử lý reset của counter. Không áp dụng `rate` vào gauge số việc chờ rồi gọi kết quả là thông lượng xử lý.

Từ chối trong lúc dừng ứng dụng có nguyên nhân khác từ chối trong thời gian phục vụ. Chính sách `CallerRunsPolicy` có thể khiến luồng gửi việc tự xử lý, làm API chậm trong khi queue không tăng thêm; không dùng biểu đồ queue đơn lẻ để cho rằng hệ thống ổn. Chính sách loại bỏ im lặng còn đòi hỏi phép đếm chủ động để phát hiện mất việc.

### 9.4. Trung bình và p95 thời gian chờ

Với timer tự tạo `app.jobs.queue.wait`:

```promql
sum by (pool) (rate(app_jobs_queue_wait_seconds_sum{pool="jobs"}[5m]))
/
sum by (pool) (rate(app_jobs_queue_wait_seconds_count{pool="jobs"}[5m]))
```

Khi không có mẫu, mẫu số có thể bằng 0; không biến kết quả không xác định thành bằng chứng “chờ 0 giây”.

Khi histogram đã bật và đã có mẫu:

```promql
histogram_quantile(
  0.95,
  sum by (le, pool) (
    rate(app_jobs_queue_wait_seconds_bucket{pool="jobs"}[5m])
  )
)
```

Các hàm được định nghĩa trong [Prometheus — Query functions](https://prometheus.io/docs/prometheus/2.55/querying/functions/). Trung bình tổng hợp phải lấy tổng thời gian chia tổng số mẫu; không lấy trung bình đơn giản của các giá trị trung bình ở từng instance.

Dashboard nên giữ chiều `instance` để tìm một bản chạy quá tải dù số tổng toàn cụm vẫn đẹp. Với cảnh báo kéo dài, chẳng hạn queue sử dụng trên 80% trong hai phút, hãy kết hợp thời gian chờ vượt mục tiêu hoặc số lần từ chối, thay vì mặc định một ngưỡng phù hợp mọi hệ thống.

## 10. Chẩn đoán theo tổ hợp tín hiệu

| Dấu hiệu quan sát | Giả thuyết cần kiểm tra | Bằng chứng tiếp theo |
| --- | --- | --- |
| Active gần giới hạn, queue và thời gian chờ cùng tăng | Năng lực xử lý không theo kịp lượng gửi | Thời gian chạy, CPU, tốc độ gửi và hoàn tất |
| Active cao, CPU thấp, việc chạy lâu | Worker đang chờ I/O, khóa hoặc tài nguyên ngoài | Thread dump, độ trễ DB/HTTP, connection pool |
| Queue tăng trong khi pool đứng ở số luồng lõi | Queue vẫn nhận việc nên chưa kích hoạt tăng luồng | Loại queue, dung lượng và cấu hình core/max |
| Queue bằng 0 nhưng có từ chối | Bàn giao trực tiếp, trạng thái tắt hoặc giới hạn luồng | Chính sách tiếp nhận, trạng thái executor |
| Scheduler queue có phần tử nhưng không trễ | Công việc đang chờ đúng giờ hẹn | Mốc dự kiến, thời điểm bắt đầu thực tế |
| Scheduler active cao và nhiều lịch bắt đầu muộn | Công việc chiếm luồng lập lịch quá lâu | Thời gian mỗi lượt và stack của scheduler |
| Completed tăng nhưng nghiệp vụ vẫn lỗi | Tác vụ kết thúc không đồng nghĩa thành công | Timer theo outcome, log lỗi và trạng thái nghiệp vụ |
| Không thấy metrics của pool mong đợi | Sai loại bean, sai pool hoặc binder không gắn được | Tên bean, kiểu thực tế, khởi tạo, cấu hình lọc meter |

Đây là hướng điều tra, chưa phải kết luận nhân quả. Nếu CPU đã bão hòa, tăng số luồng có thể làm cạnh tranh tài nguyên nặng hơn. Nếu DB chỉ cho phép một số kết nối nhất định, tăng worker có thể chỉ dời hàng chờ sang connection pool.

Tăng queue giúp hấp thụ đợt tải ngắn nhưng cũng giữ thêm dữ liệu trong bộ nhớ và kéo dài thời gian chờ. Với tải đến liên tục vượt khả năng xử lý, queue lớn hơn chỉ trì hoãn lúc lộ vấn đề.

Với hàng đợi công việc bên ngoài tiến trình, như broker hoặc bảng công việc trong DB, `executor.queued` chỉ phản ánh queue trong executor. Cần đo riêng số việc còn chờ ở nguồn, tuổi việc cũ nhất, retry và trạng thái xử lý. Không gán các metrics của broker cho queue của thread pool.

Nếu bật virtual threads trên Java 21, Boot có thể chọn `SimpleAsyncTaskExecutor` / `SimpleAsyncTaskScheduler` cho cấu hình tự động. Mô hình core/max/queue của thread pool truyền thống không áp dụng nguyên xi. Kiểm tra kiểu bean thực tế trước khi kết luận “Actuator bị mất metrics”.

## 11. Các lỗi phổ biến và cách tự kiểm chứng

- **Đăng ký meter nhưng việc chạy qua pool khác:** kiểm tra chỗ gọi `execute`, cấu hình `@Async` và executor truyền cho `CompletableFuture`.
- **Coi số việc hoàn tất là số việc thành công:** bổ sung kết quả theo nghiệp vụ; kiểm tra ngoại lệ được giữ trong `Future` khi dùng `submit`.
- **Đo cả việc gửi bằng một timer rồi gọi đó là thời gian thực thi:** xác định rõ điểm bắt đầu/kết thúc; timer quanh lời gọi gửi thường chỉ đo chi phí tiếp nhận.
- **Bật queue không giới hạn rồi chỉ tăng max pool:** kiểm tra quy tắc ưu tiên xếp hàng trước khi đổi cấu hình.
- **Cảnh báo scheduler chỉ dựa vào queue khác 0:** đo độ trễ bắt đầu và lần thành công gần nhất.
- **Đặt tag theo từng việc:** dùng tập tag nhỏ, ổn định; để mã công việc trong log/tracing.
- **Gắn timer hai lần cho cùng một đường chạy:** kiểm tra lớp bọc, decorator và điểm đo để tránh số mẫu khó giải thích.
- **Chỉ đo tác vụ đã kết thúc:** xem đồng thời active, queue và tuổi công việc; việc kẹt chưa tạo mẫu thời gian hoàn tất.
- **Scrape thưa nên bỏ lỡ đợt quá tải ngắn:** bổ sung counter từ chối và phân bố độ trễ; cân nhắc chu kỳ thu thập theo nhu cầu.
- **Tự tạo gauge trên một biến số bất biến hoặc đối tượng không còn được giữ:** quan sát đối tượng trạng thái còn sống; không dùng gauge thay counter tích lũy.

## 12. Thực hành

1. Chạy `ExecutorQueueDemo` và giải thích tại sao queue đầy trước khi pool tăng từ hai lên bốn luồng.
2. Đổi `maximumPoolSize` từ 4 thành 2, đồng thời điều chỉnh số tác vụ và latch để thí nghiệm không chờ bốn worker. Dự đoán thời điểm từ chối trước khi chạy lại.
3. Trong ứng dụng Boot, gửi việc qua `MeasuredJobs`; tạo tải ngắn có kiểm soát và đọc `executor.active`, `executor.queued` cùng timer thời gian chờ. Không giữ endpoint tạo tải trong môi trường phục vụ thật.
4. Đăng ký một lịch hẹn tương lai, rồi đối chiếu queue với độ trễ bắt đầu. Giải thích vì sao một phần tử trong queue chưa phải việc trễ.
5. Cho một tác vụ ném ngoại lệ: so sánh bộ đếm hoàn tất của executor với timer `outcome=error`.
6. Thiết kế cảnh báo cho báo cáo phải bắt đầu trong hai giây: chọn số đo thời gian chờ, tín hiệu từ chối và thời gian duy trì điều kiện. Nêu rõ cách xử lý khi không có mẫu hoặc không còn dữ liệu.

Sau bài này, người học cần đọc được đường đi **gửi việc → chờ → chạy → kết thúc**, xác định đúng pool qua tag, và phân biệt công việc chờ xử lý với công việc chờ đến lịch. Chính sự kết hợp ấy giúp metrics Actuator giải thích được độ trễ thực tế của tác vụ nền.
