# Không chạy công việc dài trực tiếp trên thread quản trị trong Spring Framework JMX

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Hiểu lý do operation JMX dài có thể làm treo client và chiếm tài nguyên xử lý của MBeanServer/JMX connector.
- Phân biệt **thời gian phản hồi của invoke** với **thời gian hoàn tất tác vụ thực tế**.
- Áp dụng mô hình **request → job ID → status → result** để tránh chặn thread quản trị.
- Sử dụng Spring TaskExecutor, ThreadPoolTaskExecutor hoặc queue bền vững theo yêu cầu.
- Kiểm soát số tác vụ đồng thời, queue capacity, rejection policy và shutdown.
- Định nghĩa idempotency, trạng thái lỗi, cancellation và audit cho tác vụ dài.
- Kiểm thử JMX operation trả về nhanh trong khi worker chạy độc lập.

## 2. Vấn đề của lời gọi JMX đồng bộ

Một lời gọi JMX operation điển hình:

\`\`\`java
server.invoke(name, "rebuildIndex", new Object[0], new String[0]);
\`\`\`

Tầng JMX gọi method của MBean và đợi method trả kết quả hoặc exception. Nếu method rebuild chỉ hoàn thành sau vài phút, thread tham gia xử lý yêu cầu có thể bị giữ trong khoảng thời gian đó.

Các hệ quả có thể gặp:

1. JConsole hoặc client chờ lâu, timeout.
2. Nhiều operator cùng gọi gây tăng số invocation đang chờ.
3. CPU, I/O, connection pool và lock bị chiếm.
4. Client tưởng lời gọi thất bại rồi gửi lại, tạo công việc trùng.
5. Khó biết tác vụ đã bắt đầu, đang chạy hay hoàn tất.
6. Shutdown/redeploy có thể bị trì hoãn bởi task chưa kết thúc.

Không phải mọi lời gọi chậm đều làm toàn bộ MBeanServer ngừng hoạt động: chi tiết phụ thuộc implementation và connector. Tuy nhiên **không nên để hoạt động bảo trì kéo dài nằm trên đường request-response của JMX**.

\`\`\`text
JConsole/Client
     |
     v
MBeanServer.invoke()
     |
     v
MBean.rebuildAll()
     |
     +-- database scan
     +-- index rebuild
     +-- network calls
     +-- waits and locks
     |
     v
return after minutes
\`\`\`

Một getter JMX cũng cần tránh tính toán dữ liệu quá tốn tài nguyên; polling getter mỗi giây có thể tạo tải không khác một operation.

## 3. Mô hình request/status

Thay một operation blocking:

\`\`\`java
void rebuildAllIndexes();
\`\`\`

bằng hợp đồng:

\`\`\`text
requestRebuild() -> String requestId
getRebuildStatus(String requestId) -> String
cancelRebuild(String requestId) -> boolean
\`\`\`

Ý nghĩa:

- requestRebuild chỉ validate và enqueue công việc.
- Request ID dùng để tra cứu, retry hoặc audit.
- Worker thực thi ở executor/queue riêng.
- Client theo dõi trạng thái mà không giữ một lời gọi JMX dài.
- Trạng thái terminal phân biệt SUCCEEDED, FAILED và CANCELLED.

\`\`\`text
JMX requestRebuild()
       |
       v
validate + check capacity
       |
       v
enqueue job
       |
       v
return ID immediately
       |
       +---- worker: QUEUED -> RUNNING -> SUCCEEDED/FAILED
       |
Client polls getRebuildStatus(ID)
\`\`\`

**Request accepted không đồng nghĩa job completed.** Description của operation phải nêu rõ nó chỉ nhận yêu cầu.

## 4. Ví dụ antipattern

\`\`\`java
@ManagedResource(
    objectName = "com.example:type=Maintenance,name=Search"
)
public class MaintenanceMBean {
    private final SearchRebuildService service;

    public MaintenanceMBean(SearchRebuildService service) {
        this.service = service;
    }

    @ManagedOperation(description = "Rebuild indexes")
    public void rebuildAll() {
        service.rebuildAllIndexes(); // Có thể chạy hàng phút.
    }
}
\`\`\`

Trong ví dụ này, thao tác JMX block theo thời lượng của service. Nếu client mất kết nối, không thể mặc định công việc đã ngừng.

Một biến thể tưởng là async nhưng vẫn blocking:

\`\`\`java
@ManagedOperation
public String rebuildAll() throws Exception {
    Future<String> future = executor.submit(
        service::rebuildAllIndexesAndReturnResult
    );
    return future.get(); // Vẫn chờ ngay trên thread JMX.
}
\`\`\`

Chuyển công việc vào executor rồi gọi get/join ngay không đáp ứng yêu cầu phản hồi nhanh.

## 5. Chọn chiến lược thực thi

| Loại công việc | Cách xử lý phù hợp |
| --- | --- |
| Kiểm tra trạng thái rất nhẹ | Getter hoặc operation đồng bộ ngắn. |
| Tính toán ngắn, bounded | Có thể đồng bộ với giới hạn rõ. |
| Bảo trì dài nhưng mất khi restart chấp nhận được | Executor riêng có giới hạn và status in-memory. |
| Job phải sống qua restart | Durable queue, scheduler hoặc batch framework. |
| Job nhiều giai đoạn | Checkpoint, state store, resume và cancel hợp lệ. |
| Job rủi ro cao | Authorization, rate limit, audit, phê duyệt nếu cần. |

Không nên sử dụng executor in-memory khi nghiệp vụ cần bảo đảm giao hàng, checkpoint và retry sau JVM crash.

## 6. ThreadPoolTaskExecutor trong Spring

\`\`\`java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class JmxMaintenanceConfiguration {
    @Bean("jmxMaintenanceExecutor")
    public ThreadPoolTaskExecutor jmxMaintenanceExecutor() {
        ThreadPoolTaskExecutor e = new ThreadPoolTaskExecutor();
        e.setCorePoolSize(1);
        e.setMaxPoolSize(2);
        e.setQueueCapacity(10);
        e.setThreadNamePrefix("jmx-maintenance-");
        e.setWaitForTasksToCompleteOnShutdown(true);
        e.setAwaitTerminationSeconds(20);
        e.initialize();
        return e;
    }
}
\`\`\`

Giá trị cấu hình mang tính minh họa. Số worker, queue capacity và thời gian shutdown phải theo tài nguyên và SLA thực tế.

### Tại sao không dùng queue vô hạn?

Nếu operation trả nhanh và người dùng tiếp tục gửi hàng nghìn yêu cầu, một queue vô hạn có thể tích tụ backlog và làm cạn heap. Một executor có queue hữu hạn có thể từ chối request mới khi đầy; sự từ chối đó là tín hiệu bảo vệ hệ thống.

### Bẫy CallerRunsPolicy

\`ThreadPoolExecutor.CallerRunsPolicy\` cho phép task bị từ chối chạy trên **thread gọi execute**. Nếu caller là JMX request thread, tác vụ nặng lại chạy trực tiếp trên thread quản trị. Muốn operation chắc chắn không blocking do fallback này, dùng policy từ chối rõ và xử lý \`TaskRejectedException\`.

## 7. Định nghĩa trạng thái công việc

\`\`\`java
public enum JobState {
    QUEUED,
    RUNNING,
    SUCCEEDED,
    FAILED,
    CANCEL_REQUESTED,
    CANCELLED
}
\`\`\`

Một record có thể lưu:

\`\`\`java
import java.time.Instant;
import java.util.concurrent.atomic.AtomicReference;

public final class JobRecord {
    private final String id;
    private final Instant createdAt = Instant.now();
    private final AtomicReference<JobState> state =
        new AtomicReference<>(JobState.QUEUED);

    private volatile Instant finishedAt;
    private volatile String errorType;

    public JobRecord(String id) { this.id = id; }
    public String getId() { return id; }
    public JobState getState() { return state.get(); }
    public void running() { state.set(JobState.RUNNING); }
    public void success() {
        finishedAt = Instant.now();
        state.set(JobState.SUCCEEDED);
    }
    public void fail(Throwable error) {
        errorType = error.getClass().getSimpleName();
        finishedAt = Instant.now();
        state.set(JobState.FAILED);
    }
}
\`\`\`

Mẫu này chỉ minh họa lưu trạng thái. Một state machine production cần transition có kiểm soát để không bị race giữa success, cancellation và failure.

### Lưu trạng thái ở đâu?

- ConcurrentHashMap phù hợp với demo một JVM.
- Cache có TTL phù hợp khi cần giữ bản ghi ngắn hạn.
- Database/Redis/queue metadata phù hợp với yêu cầu lâu dài, nhiều instance.
- Job store có retention để không giữ vô hạn mọi request ID.

Không đưa request ID động làm label của metrics time-series vì có thể gây cardinality quá cao.

## 8. Coordinator thực thi ngoài thread quản trị

\`\`\`java
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.core.task.TaskRejectedException;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.stereotype.Service;

@Service
public class MaintenanceJobCoordinator {

    private final ThreadPoolTaskExecutor executor;
    private final SearchRebuildService service;
    private final Map<String, JobRecord> records =
        new ConcurrentHashMap<>();

    public MaintenanceJobCoordinator(
            ThreadPoolTaskExecutor jmxMaintenanceExecutor,
            SearchRebuildService service) {
        this.executor = jmxMaintenanceExecutor;
        this.service = service;
    }

    public String requestRebuild() {
        String id = UUID.randomUUID().toString();
        JobRecord record = new JobRecord(id);
        records.put(id, record);

        try {
            executor.execute(() -> {
                record.running();
                try {
                    service.rebuildAllIndexes();
                    record.success();
                } catch (Exception ex) {
                    record.fail(ex);
                }
            });
        } catch (TaskRejectedException ex) {
            records.remove(id);
            throw new IllegalStateException(
                "Maintenance queue is full", ex
            );
        }

        return id;
    }

    public String status(String id) {
        JobRecord record = records.get(id);
        return record == null ? "UNKNOWN"
                              : record.getState().name();
    }
}
\`\`\`

\`SearchRebuildService\` là interface nghiệp vụ do ứng dụng định nghĩa. Mẫu demo không tự xử lý authorization, idempotency, cancellation hay cleanup bản ghi. Cần bổ sung các cơ chế này khi triển khai thật.

Khi pool từ chối, coordinator không trả ID như thể đã enqueue thành công. Khi task được nhận, trạng thái sẽ chuyển từ QUEUED sang RUNNING rồi trạng thái kết thúc.

## 9. JMX adapter chỉ gửi lệnh

\`\`\`java
import org.springframework.jmx.export.annotation.*;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example:type=Maintenance,name=Search",
    description = "Search maintenance"
)
public class SearchMaintenanceAdmin {
    private final MaintenanceJobCoordinator coordinator;

    public SearchMaintenanceAdmin(
            MaintenanceJobCoordinator coordinator) {
        this.coordinator = coordinator;
    }

    @ManagedOperation(
        description = "Queue rebuild and return request ID"
    )
    public String requestRebuild() {
        return coordinator.requestRebuild();
    }

    @ManagedOperation(
        description = "Get status for a prior request ID"
    )
    @ManagedOperationParameters({
        @ManagedOperationParameter(
            name = "requestId",
            description = "ID from requestRebuild"
        )
    })
    public String getRebuildStatus(String requestId) {
        return coordinator.status(requestId);
    }
}
\`\`\`

MBean này không đợi \`rebuildAllIndexes()\`. Với \`MBeanExporter\` hoặc Spring Boot JMX auto-configuration phù hợp, hai operations có thể được công bố qua \`MBeanServer\`.

Cần kiểm tra runtime \`MBeanInfo\` để xác nhận đúng operations và signature trước khi đưa vào môi trường thực.

## 10. Gọi qua MBeanServer

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "com.example:type=Maintenance,name=Search"
);

String id = (String) server.invoke(
    name, "requestRebuild",
    new Object[0], new String[0]
);

String status = (String) server.invoke(
    name, "getRebuildStatus",
    new Object[] { id },
    new String[] { "java.lang.String" }
);

System.out.println(id + " -> " + status);
\`\`\`

Nếu Spring exporter dùng custom MBeanServer, phải lấy đúng server thay vì mặc định platform server. Khi client JMX remote mất kết nối, không nên suy luận job chưa chạy.

## 11. Kiểm thử không blocking với CountDownLatch

Thay \`Thread.sleep(300000)\` bằng latch để test có tính quyết định:

\`\`\`java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

public final class BlockingRebuildService
        implements SearchRebuildService {
    final CountDownLatch started = new CountDownLatch(1);
    final CountDownLatch release = new CountDownLatch(1);

    @Override
    public void rebuildAllIndexes() {
        started.countDown();
        try {
            if (!release.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Test timeout");
            }
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(ex);
        }
    }
}
\`\`\`

Các bước test:

1. Gọi \`requestRebuild()\` qua MBeanServer.
2. Xác nhận lời gọi đã trả request ID trước khi release latch.
3. Đợi started latch để chắc worker đã bắt đầu.
4. Kiểm tra status RUNNING.
5. Release latch.
6. Đợi trạng thái SUCCEEDED.
7. Đóng Spring context và executor.

Mẫu này chứng minh JMX caller không cần đợi toàn bộ công việc. Test cũng nên xác nhận lỗi từ worker chuyển trạng thái FAILED, không bị nuốt mất.

## 12. Thời lượng lời gọi JMX khác thời lượng job

Có thể đo:

\`\`\`java
long start = System.nanoTime();

String id = (String) server.invoke(
    name, "requestRebuild",
    new Object[0], new String[0]
);

long requestMillis =
    java.util.concurrent.TimeUnit.NANOSECONDS
        .toMillis(System.nanoTime() - start);
\`\`\`

\`requestMillis\` đo thời gian gọi JMX đến lúc nhận ID. Job duration cần được đo riêng trong worker từ khi bắt đầu đến khi kết thúc.

Một request được nhận trong 5 ms không có nghĩa rebuild xong trong 5 ms. Một job hoàn tất nhanh cũng không chứng minh non-blocking nếu operation đã chờ nó: cần test với latch như phần trên.

## 13. Timeout không bảo đảm server ngừng làm

Với remote JMX:

\`\`\`text
Client sends request
       |
       v
Server accepts job ----> worker executes
       |
       X network timeout
       |
Client sees error
\`\`\`

Sau timeout, job có thể chưa bắt đầu, đang chạy hoặc đã kết thúc. Retry operation tạo job mới có thể làm thực hiện công việc hai lần.

Một chiến lược là dùng idempotency key của client:

\`\`\`java
String requestRebuild(String requestKey);
\`\`\`

Coordinator lưu ánh xạ requestKey → requestId. Gửi lại key cũ trả về requestId đã tồn tại thay vì enqueue lần nữa. Cơ chế deduplication phải nguyên tử khi concurrent requests và có retention phù hợp.

Nếu cần bền qua crash, idempotency state phải ở storage ngoài JVM.

## 14. Bảo vệ concurrency và tải nghiệp vụ

Chuyển task ra executor không có nghĩa hệ thống đã an toàn. Worker vẫn có thể:

- Mở transaction database quá lâu.
- Giữ lock bảng hoặc tài nguyên.
- Sử dụng nhiều CPU/I/O.
- Lấy quá nhiều connection.
- Làm chậm HTTP requests và consumer khác.
- Tạo backlog lớn sau nhiều lời gọi JMX.

Cần giới hạn số job cùng loại, chia thành batches nhỏ và thiết kế checkpoint khi cần. Có thể đặt semaphore hoặc locking theo resource để không có hai rebuild đồng thời.

Ví dụ điều phối đơn giản:

\`\`\`java
if (!rebuildLock.tryLock()) {
    throw new IllegalStateException(
        "Rebuild already in progress"
    );
}
try {
    service.rebuildAllIndexes();
} finally {
    rebuildLock.unlock();
}
\`\`\`

Đoạn này thuộc **worker thread**, không phải phương thức JMX trực tiếp. Khi cần lock phân tán giữa nhiều JVM, \`ReentrantLock\` local không đủ.

## 15. Cancellation có hợp đồng riêng

\`\`\`text
cancelRebuild(requestId) -> boolean
\`\`\`

Phải định nghĩa boolean có nghĩa đã tiếp nhận yêu cầu hủy hay đã dừng thật. \`Future.cancel(true)\` chỉ cố gắng interrupt, không bảo đảm worker đã dừng hoặc rollback mọi side effect.

Công việc dài nên kiểm tra cancellation token giữa các batch:

\`\`\`java
while (hasNextBatch()) {
    if (cancelToken.isCancelled()
            || Thread.currentThread().isInterrupted()) {
        recordCancelled();
        return;
    }
    processNextBatch();
}
\`\`\`

Đừng hủy giữa thao tác thay đổi dữ liệu nếu không có recovery/transaction. Phân biệt CANCEL_REQUESTED và CANCELLED khi việc dừng không tức thời.

## 16. @Async có đủ hay không?

Spring \`@Async\` có thể điều phối method sang executor khi lời gọi đi qua Spring proxy và \`@EnableAsync\` được bật.

\`\`\`java
@Service
public class RebuildWorker {
    @Async("jmxMaintenanceExecutor")
    public CompletableFuture<Void> rebuild() {
        service.rebuildAllIndexes();
        return CompletableFuture.completedFuture(null);
    }
}
\`\`\`

Các bẫy:

- Self-invocation (\`this.rebuild()\`) bypass proxy.
- Thiếu \`@EnableAsync\`.
- Executor chạy đồng bộ theo cấu hình.
- Adapter gọi \`future.get()\` trước khi trả.
- Async exception không có nơi được quan sát.
- Executor queue đầy và policy làm chạy task ở caller.

Với job cần ID, status, cancellation và idempotency, một coordinator riêng thường rõ ràng hơn chỉ thêm annotation.

## 17. Logging, metrics và audit

Những chỉ số hữu ích:

| Tín hiệu | Ý nghĩa |
| --- | --- |
| \`maintenance_jobs_active\` | Số job đang chạy. |
| \`maintenance_jobs_queued\` | Số job chờ. |
| \`maintenance_jobs_rejected_total\` | Số yêu cầu không được nhận. |
| \`maintenance_jobs_failed_total\` | Số job lỗi. |
| \`maintenance_job_duration_seconds\` | Thời lượng chạy job. |
| \`jmx_operation_latency_seconds\` | Latency operation JMX. |
| \`maintenance_oldest_queued_age_seconds\` | Tuổi request chờ lâu nhất. |

Đây là ví dụ metric do ứng dụng tự định nghĩa, không phải toàn bộ metrics Spring tự tạo. Có thể dùng Micrometer/Actuator để công bố theo kiến trúc observability của dự án.

Log nên có request ID, operation, state transition và lỗi đã sanitize. Audit một operation rủi ro cao nên ghi actor từ hệ xác thực đáng tin, thời điểm và kết quả, không log secret hoặc toàn bộ payload nhạy cảm.

Đối với metrics time-series, không đưa request ID động làm label.

## 18. Security cho lệnh bảo trì

Một JMX operation trả nhanh vẫn có thể kích hoạt khối lượng công việc khổng lồ, nên phải có:

1. Authentication và authorization.
2. Giới hạn concurrency/queue/rate.
3. Validation input.
4. Audit.
5. Idempotency.
6. Network restriction và TLS cho remote JMX.
7. Tách monitoring MBean khỏi control MBean khi phù hợp.
8. Trạng thái rõ để tránh người vận hành bấm invoke lặp lại.

\`MBeanOperationInfo.getImpact()\` và \`@ManagedOperation\` không phải authorization rule. Quyền readwrite của JMX connector có thể rất rộng; cần thiết kế theo khả năng thực sự của connector và service.

## 19. Shutdown và restart

Khi Spring context đóng, executor có thể chờ tasks hoàn tất một khoảng thời gian. Nhưng JVM bị kill cứng hoặc Pod hết termination grace period có thể làm job dở dang.

\`\`\`java
executor.setWaitForTasksToCompleteOnShutdown(true);
executor.setAwaitTerminationSeconds(20);
\`\`\`

không bảo đảm task 5 phút sẽ hoàn tất trong 20 giây. Nếu job phải tồn tại qua restart, dùng durable queue/state store và checkpoint.

Một status Map trong JVM sẽ mất sau restart. Client phải hiểu UNKNOWN có thể nghĩa job ID không được giữ trong instance hiện tại, không mặc nhiên là job thất bại.

## 20. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| JConsole treo khi invoke | Operation chạy tác vụ dài hoặc đợi Future. | Trả ID nhanh, dùng request/status. |
| Đã dùng executor mà vẫn block | \`Future.get()\`, \`join()\` hoặc CallerRunsPolicy. | Không đợi trên JMX thread; dùng rejection rõ. |
| Executor queue tăng mãi | Queue không giới hạn hoặc tốc độ gửi lớn hơn xử lý. | Bounded queue, backpressure, rate limit. |
| Timeout và job chạy hai lần | Client retry khi chưa biết request đã được nhận. | Idempotency key, kiểm tra status. |
| Job lỗi nhưng invoke vẫn thành công | Lỗi xảy ra sau khi enqueue. | Theo dõi FAILED và audit. |
| Task còn chạy khi shutdown | Worker không hỗ trợ cancel/termination. | Shutdown policy và cooperative cancellation. |
| Status records tăng không giới hạn | Không có TTL/retention. | Giới hạn và cleanup. |
| Một JVM có quá nhiều job nặng | Không giới hạn concurrency. | Pool/semaphore/queue capacity. |
| \`@Async\` không chạy async | Self-invocation hoặc advice chưa bật. | Test thread/executor, gọi qua proxy. |
| Không có MBean trên server kiểm tra | Sai ObjectName hoặc MBeanServer. | Xem exporter và runtime metadata. |

## 21. Quy trình triển khai

1. Xác định operation có thực sự dài hay có thể bound dưới một ngưỡng nhỏ.
2. Định nghĩa hợp đồng request ID, status và result rõ ràng.
3. Chọn executor riêng hoặc durable job queue theo yêu cầu.
4. Đặt giới hạn concurrency, queue và resource quota.
5. Ghi trạng thái QUEUED/RUNNING/SUCCEEDED/FAILED và thời điểm chuyển trạng thái.
6. Thiết kế idempotency và cancellation.
7. Export một JMX adapter mỏng, không chạy business job trên thread invoke.
8. Kiểm tra MBeanInfo, ObjectName và signature.
9. Test bằng latch để chứng minh invoke trả nhanh.
10. Test rejection, worker failure, shutdown, timeout và retry.
11. Bật authentication, TLS và audit cho remote JMX.
12. Giám sát request latency tách biệt với job duration.

## 22. Bài tập thực hành

### Bài tập 1 — Chứng minh blocking

Tạo operation \`rebuildAll()\` gọi công việc giả kéo dài 3 giây trong lab. Đo thời gian \`MBeanServer.invoke\`, sau đó thay bằng request/status.

### Bài tập 2 — Bounded executor

Tạo pool một worker, queue capacity một và gửi nhiều request. Assert request vượt giới hạn bị từ chối, không chạy trên JMX caller thread.

### Bài tập 3 — Latch test

Tạo fake service giữ worker chờ latch, gọi JMX request và xác nhận ID đã trả trước khi release. Sau release, kiểm tra SUCCEEDED.

### Bài tập 4 — Failure tracking

Cho worker ném exception. Xác nhận request được nhận nhưng status chuyển FAILED. Ghi log loại lỗi thay vì nuốt exception.

### Bài tập 5 — Deduplication

Gọi \`requestRebuild(key)\` đồng thời hai lần với cùng key; kiểm tra chỉ một job được tạo.

### Bài tập 6 — Cancellation

Thiết kế worker chia batch có cancellation token, gửi yêu cầu hủy, quan sát CANCEL_REQUESTED rồi CANCELLED.

### Bài tập 7 — Shutdown

Đóng Spring context khi job đang chạy trong môi trường test. Đối chiếu shutdown timeout với thời gian công việc, nêu trường hợp cần durable storage.

## 23. Câu hỏi ôn tập

**1. Vì sao không chạy công việc dài trên thread quản trị?** Vì lời gọi có thể block client/connector, gây timeout, chiếm thread và tăng rủi ro tải.

**2. Dùng executor có đủ để operation nhanh không?** Không, nếu method vẫn đợi Future hoặc policy từ chối chạy task trên caller.

**3. Request ID cho biết điều gì?** Yêu cầu đã được nhận theo hợp đồng, không bảo đảm job hoàn tất.

**4. Timeout ở client có nghĩa task bị ngắt không?** Không, task server có thể vẫn chạy.

**5. Khi nào cần idempotency key?** Khi retry có thể tạo tác vụ trùng với hậu quả đáng kể.

**6. Vì sao tránh queue vô hạn?** Vì backlog có thể tăng đến mức cạn heap/tài nguyên.

**7. CallerRunsPolicy có nguy cơ gì?** Nó có thể thực thi task trên thread JMX caller và làm operation block.

**8. Future.cancel(true) có chắc hủy task không?** Không, worker phải hỗ trợ interruption/cancellation.

**9. Trạng thái in-memory có sống qua restart không?** Không, cần persistence cho yêu cầu durability.

**10. Hai latency cần đo là gì?** Thời gian nhận lệnh JMX và thời lượng thực thi job.

## 24. Tổng kết

**Không chạy công việc dài trực tiếp trên thread quản trị** giúp bảo vệ độ phản hồi của JMX và giảm nguy cơ operator/client gửi thao tác lặp khi timeout. Với tác vụ dài, thiết kế operation nhận yêu cầu và trả request ID nhanh, sau đó thực thi trên executor/hàng đợi có giới hạn, cho phép truy vấn trạng thái và kết quả.

Spring \`ThreadPoolTaskExecutor\` có thể xử lý tác vụ nền trong một JVM, nhưng cần bounded queue, rejection phù hợp, concurrency control, idempotency, retention, cancellation và shutdown có kế hoạch. Khi công việc phải sống qua restart, sử dụng storage/queue bền vững. Luôn xác minh bằng integration test qua \`MBeanServer.invoke\`, đồng thời bảo vệ operation bằng phân quyền và quan sát trạng thái.

## Tài liệu tham khảo

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework Reference — Task Execution and Scheduling: https://docs.spring.io/spring-framework/reference/integration/scheduling.html
- Spring Framework Javadoc — \`ThreadPoolTaskExecutor\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html
- Spring Framework Javadoc — \`TaskRejectedException\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/task/TaskRejectedException.html
- Java SE 21 — \`MBeanServer\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
- Java SE 21 — \`ThreadPoolExecutor.CallerRunsPolicy\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.CallerRunsPolicy.html