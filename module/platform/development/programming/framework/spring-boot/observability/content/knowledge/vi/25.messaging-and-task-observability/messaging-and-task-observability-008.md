# Executor observation trong Spring Boot

Khi Spring Boot chuyển tác vụ sang thread pool, request ban đầu có thể kết thúc trước khi công việc nền hoàn tất. Nếu chỉ quan sát HTTP request, ta thấy response đã trả về nhưng không biết task mất bao lâu, đang chờ trong queue hay thất bại ở worker thread. **Executor observation** bổ sung khả năng quan sát vòng đời task: thời gian chờ, thời gian chạy, kết quả, lỗi và context liên quan. Nó giúp phân biệt queue delay với execution time, phát hiện pool saturation và liên kết task với request đã khởi tạo nó.

Trong module **SPRING_BOOT_OBSERVABILITY**, Executor observation thuộc chương **Messaging và task observability**, kết hợp Micrometer Observation, metrics, logs và distributed tracing. Bài tập trung vào cách quan sát task qua Executor/ThreadPoolTaskExecutor, tích hợp ObservationRegistry, truyền trace/MDC context qua thread boundary, đo queue và pool health, xử lý exception/cancellation/rejection, tránh instrumentation trùng và kiểm thử trong môi trường Spring.

## Mục tiêu học tập

1. Mô tả vòng đời task từ submit, queue, execution đến completion.
2. Phân biệt queue wait time, task execution time và end-to-end duration.
3. Dùng Micrometer Observation để mô tả task operation.
4. Cấu hình Spring ThreadPoolTaskExecutor và TaskDecorator.
5. Propagate tracing/MDC context đúng cách qua thread boundary.
6. Theo dõi pool size, active threads, queue depth và rejected tasks.
7. Xử lý exception, cancellation, timeout và shutdown.
8. Tránh spans/metrics trùng khi executor đã được instrument.
9. Viết test cho Observation lifecycle, context restoration và executor saturation.

## 1. Task lifecycle và ba loại thời gian

Executor nhận task và quyết định task chạy ngay hay chờ trong queue.

~~~text
Caller
  └─ submit(task)
       ├─ accepted -> worker available -> execute
       ├─ accepted -> queue -> worker takes task -> execute
       └─ rejected -> rejection policy
  Task execution
       ├─ completed
       ├─ failed with exception
       └─ cancelled/interrupted
~~~

| Thời gian | Bắt đầu/kết thúc | Ý nghĩa |
| --- | --- | --- |
| Queue wait | Task enqueue → worker bắt đầu | Thời gian task chờ |
| Execution time | Worker bắt đầu → task kết thúc | Thời gian code chạy |
| End-to-end task time | Submit → task kết thúc | Tổng thời gian từ submit |

Ví dụ task submit lúc 10:00:00.000, worker bắt đầu 10:00:00.250 và kết thúc 10:00:01.000: queue wait 250 ms, execution 750 ms, tổng 1.000 ms. Chỉ đo execution time sẽ bỏ qua backlog; chỉ đo tổng thời gian sẽ khó phân biệt queue delay với code chạy lâu.

Executor metrics mô tả pool: active threads, pool size, queue depth, completed task count. Task Observation mô tả operation cụ thể: tên, duration, outcome và context. Hai loại dữ liệu bổ sung cho nhau.

## 2. Task lifecycle và context boundary

~~~mermaid
sequenceDiagram
    participant Caller
    participant Executor
    participant Queue
    participant Worker
    participant Observation
    Caller->>Observation: Capture task context
    Observation->>Executor: submit(task)
    Executor->>Queue: enqueue if no worker
    Queue-->>Worker: dequeue task
    Worker->>Observation: Activate task scope
    Worker->>Worker: Execute business logic
    Worker->>Observation: Record outcome/error and stop
    Observation-->>Caller: Future completion
~~~

Task có thể chạy trên thread khác caller. ThreadLocal values từ caller không tự đi theo task. Tracing context, MDC và context khác cần được capture/restore bằng cơ chế phù hợp.

Với fire-and-forget, caller submit task rồi tiếp tục; HTTP Observation có thể kết thúc trước task. Với Future/CompletableFuture, caller có thể chờ kết quả hoặc compose continuation. Nếu task chạy độc lập sau response, tạo task span/Observation riêng và liên kết với context nguồn theo semantics nghiệp vụ.

Nếu task là phần tiếp nối trực tiếp của request, child span có thể phù hợp. Nếu task chạy muộn, có nhiều nguồn kích hoạt hoặc tổng hợp nhiều messages, span link có thể phù hợp hơn. Không giữ HTTP server span mở chỉ để chờ background task khi API contract không yêu cầu.

## 3. Cấu hình ThreadPoolTaskExecutor

Spring cung cấp ThreadPoolTaskExecutor để cấu hình pool như bean:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
public class TaskExecutorConfiguration {
    @Bean("applicationTaskExecutor")
    ThreadPoolTaskExecutor applicationTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(12);
        executor.setQueueCapacity(200);
        executor.setKeepAliveSeconds(60);
        executor.setThreadNamePrefix("app-task-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(30);
        return executor;
    }
}
~~~

Giá trị chỉ là ví dụ. Pool sizing phải dựa trên workload, CPU/IO profile, downstream capacity và tài nguyên. Queue lớn có thể che saturation và làm queue wait tăng; max pool lớn có thể overload database hoặc remote service.

- Core pool size: số worker nền được giữ theo policy.
- Max pool size: giới hạn worker tối đa.
- Queue capacity: số task có thể chờ.
- Keep-alive: thời gian worker vượt core có thể idle trước khi thu hồi.
- Rejection policy: behavior khi không còn capacity.

Với ThreadPoolExecutor, task thường được queue sau khi core threads bận; chỉ khi queue đầy mới mở rộng vượt core tới max. Vì vậy queue capacity ảnh hưởng mạnh tới việc pool có mở rộng hay không.

### 3.1. Rejection policy

- AbortPolicy: ném RejectedExecutionException.
- CallerRunsPolicy: caller tự chạy task, tạo backpressure nhưng có thể làm request thread chạy việc nặng.
- DiscardPolicy: bỏ task im lặng.
- DiscardOldestPolicy: bỏ task cũ nhất trong queue.

Không chọn discard policy cho công việc quan trọng nếu không có cơ chế phát hiện và bù. Rejection phải được ghi nhận và xử lý theo business semantics.

## 4. Micrometer Observation cho task

Micrometer Observation cung cấp lifecycle thống nhất. Observation có thể tạo metrics/spans qua handlers đã cấu hình. Ví dụ custom task observation:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Component;

@Component
public class ObservedTaskRunner {
    private final ObservationRegistry registry;

    public ObservedTaskRunner(ObservationRegistry registry) {
        this.registry = registry;
    }

    public void run(String taskType, Runnable task) {
        Observation.createNotStarted("application.task", registry)
                .lowCardinalityKeyValue("task.type", taskType)
                .observe(task);
    }
}
~~~

### 4.1. Observation đặt ở đâu?

Đặt observation tại ranh giới operation có ý nghĩa:
- submit boundary nếu cần đo submit-to-completion;
- worker boundary nếu cần đo execution;
- business task method nếu muốn tên theo nghiệp vụ.

Không đặt observation cùng tên ở caller, executor wrapper và worker mà không định nghĩa rõ mỗi span đại diện giai đoạn nào. Nếu cần queue wait riêng, đo nó riêng thay vì tạo nhiều spans trùng toàn bộ task.

### 4.2. Low-cardinality task metadata

Tag phù hợp có thể là task.type (email-delivery, invoice-export), task.queue (notifications, reports), task.outcome (success, failure, cancelled). Tránh task ID, user ID, file name, message body và exception message làm metric tags. Nếu cần task ID để tìm một task cụ thể, dùng trace/span context hoặc field logs được kiểm soát.

## 5. Context propagation qua executor

MDC và tracing context thường gắn với execution context. Khi task chạy trên worker thread, cần capture caller context lúc submit và restore worker context khi chạy task.

Với Spring Framework 6.1+ và Micrometer Context Propagation, ContextPropagatingTaskDecorator có thể capture/restore các context accessor đã đăng ký:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
public class PropagatingExecutorConfiguration {
    @Bean("observedTaskExecutor")
    ThreadPoolTaskExecutor observedTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("observed-");
        executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
        return executor;
    }
}
~~~

Decorator không tự biến mọi ThreadLocal thành context có thể propagate. Tracing/MDC accessors phải được đăng ký và integration tương ứng phải hoạt động. Kiểm tra version Spring/Micrometer và context registry thực tế.

Một context propagation mechanism đúng phải capture context ở thread submit, gắn vào worker trong thời gian task chạy, khôi phục context trước đó sau task kể cả khi ném exception, và không để giá trị task A xuất hiện trong task B do worker reuse.

Tracing context chứa span context và parent relationship. MDC là map phục vụ logging. Copy traceId/spanId vào MDC không tạo parent span. Dùng tracing context propagation để tạo hierarchy đúng; logging integration sẽ đưa correlation fields vào log event.

Spring Security context có cơ chế propagation riêng. Không giả định TaskDecorator tự động thay thế mọi security propagation. Nếu task cần principal/authorization context, cấu hình và kiểm tra riêng, giới hạn quyền và tránh giữ context lâu hơn cần thiết.

## 6. Async methods và CompletableFuture

Spring @Async chạy method trên executor được cấu hình:

~~~java
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;
import java.util.concurrent.CompletableFuture;

@Service
public class ReportService {
    @Async("observedTaskExecutor")
    public CompletableFuture<String> generateReport() {
        return CompletableFuture.completedFuture("generated");
    }
}
~~~

Cần bật async processing bằng configuration phù hợp và dùng đúng executor bean. Self-invocation trong cùng bean không đi qua Spring proxy, nên @Async có thể không áp dụng nếu method gọi trực tiếp method khác trong cùng instance.

Một continuation có thể chạy trên thread khác tùy overload và executor. Ví dụ thenApplyAsync không chỉ rõ executor có thể dùng common ForkJoinPool. Nếu cần quản lý context và metrics, truyền executor tường minh:

~~~java
CompletableFuture.supplyAsync(this::loadData, observedExecutor)
        .thenApplyAsync(this::transform, observedExecutor);
~~~

Mỗi continuation có thể có lifecycle riêng. Không giả định context tự propagate qua mọi CompletableFuture chain nếu executor/instrumentation không hỗ trợ.

Scheduled task thường không có incoming HTTP parent. Có thể tạo root task observation mỗi lần chạy với task name ổn định. Quan sát duration, schedule lag, failure và missed executions; không giữ một span mở qua nhiều lần chạy.

## 7. Executor metrics và saturation

Tên meter phụ thuộc binder/framework/version; kiểm tra registry thực tế.

| Measurement | Ý nghĩa | Dấu hiệu cần chú ý |
| --- | --- | --- |
| Pool size | Số worker hiện có | Tăng liên tục hoặc chạm max |
| Active threads | Worker đang chạy task | Gần max kéo dài |
| Queue size | Số task chờ | Tăng liên tục |
| Remaining capacity | Số slot còn trống | Gần 0 |
| Completed task count | Task đã hoàn tất | Không tăng khi pool kẹt |
| Rejected count | Task bị từ chối | Tăng bất thường |
| Task duration | Thời gian chạy | P95/p99 tăng |
| Queue wait | Thời gian chờ | Tăng khi backlog |

Spring Boot có thể instrument executor được quản lý/nhận diện qua auto-configuration hoặc Micrometer binders. Executor tự tạo thủ công có thể cần bind/register rõ ràng. Không giả định mọi Executor bean đều tự xuất đủ metrics.

Queue tăng trong khi active threads ở max cho thấy task đến nhanh hơn khả năng xử lý. Queue lớn có thể giữ công việc chưa xử lý rất lâu và tăng memory pressure. Capacity nên phản ánh latency budget và khả năng chịu tải.

Nếu mọi worker chờ Future khác được submit vào chính pool đó, pool có thể starvation/deadlock. Tránh blocking wait trong cùng pool nếu dependency task không thể chạy.

Rejection báo hệ thống hết capacity. Tùy business semantics, từ chối request đồng bộ, retry có giới hạn/backoff, ghi task vào durable queue, giảm tốc producer hoặc áp dụng bulkhead riêng. Không retry vô hạn trong caller thread.

## 8. Error, cancellation và shutdown

Task có thể kết thúc thành công, ném exception, bị cancel hoặc bị interrupt khi shutdown. Observation cần ghi outcome tương ứng và đóng scope trong mọi nhánh.

Nếu wrapper bắt exception rồi chỉ log và bỏ qua, tracing handler có thể không thấy error outcome. Record exception và rethrow hoặc chuyển sang business error result rõ ràng. Không swallow exception mà không ghi nhận.

Cancellation của Future không nhất thiết dừng ngay code đang chạy. cancel(true) yêu cầu interrupt; task phải hợp tác bằng cách kiểm tra interrupt hoặc dùng API interruptible. Record cancellation riêng nếu quan trọng, không phân loại nhầm thành success.

Khi ứng dụng dừng, ngừng nhận task mới theo lifecycle, cho task đang chạy thời gian hoàn tất, giới hạn await termination, ghi nhận task bị reject/cancel và tránh giữ process vô hạn. waitForTasksToCompleteOnShutdown và awaitTerminationSeconds cần chọn theo SLA. Queue in-memory không phải durable storage; task không được phép mất cần messaging/job store có persistence.

## 9. Cardinality và privacy

| Giá trị | Metric tag? | Lý do |
| --- | --- | --- |
| task.type | Có, nếu tập hữu hạn | Phân nhóm operation |
| executor.name | Có | Pool name ổn định |
| task.outcome | Có | Success/failure/cancelled |
| queue.name | Có, nếu hữu hạn | Workload category |
| task.id | Không | Gần như duy nhất |
| user.id | Không | High cardinality/PII |
| file path/name | Không | Động, có thể nhạy cảm |
| message body | Không | Nội dung nghiệp vụ |
| exception message | Không | Giá trị tự do |
| traceId/spanId | Không | Correlation fields, không metric labels |

Trace attributes có thể giữ thêm context đã kiểm soát nhưng cần giới hạn kích thước và quyền truy cập. Không copy toàn bộ MDC, SecurityContext hoặc message headers vào Observation.

## 10. Kiểm thử Executor observation

### 10.1. Test custom Observation

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import io.micrometer.observation.tck.TestObservationRegistry;
import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.assertThat;

class TaskObservationTest {
    @Test
    void recordsTaskOperation() {
        TestObservationRegistry registry = TestObservationRegistry.create();
        Observation.createNotStarted("application.task", registry)
                .lowCardinalityKeyValue("task.type", "report")
                .observe(() -> { });
        assertThat(registry.getCompletedObservationContexts()).hasSize(1);
    }
}
~~~

Assertion API phụ thuộc Micrometer version. Test này chỉ chứng minh Observation lifecycle; không chứng minh executor metrics hay trace export.

### 10.2. Test context propagation và cleanup

Dùng executor một worker để buộc tái sử dụng thread:
1. Đặt parent span/MDC value trong caller.
2. Submit task A qua executor có context propagation.
3. Assert task A nhìn thấy trace context và MDC phù hợp.
4. Kết thúc task A và scope.
5. Submit task B không có context.
6. Assert task B không thấy traceId/MDC của A.
7. Ném exception trong task C và xác minh context vẫn được restore.

### 10.3. Queue wait, rejection và cancellation tests

Dùng executor một thread. Task A giữ worker có kiểm soát; submit task B và đo thời gian B chờ. Assert thứ tự/lifecycle thay vì assert milliseconds chính xác vì test runtime có jitter.

Với rejection, dùng pool một worker, queue nhỏ và task blocking có latch. Submit đủ task để pool/queue đầy rồi xác minh policy. Luôn release latch trong finally để test không treo.

Với exception/cancellation, xác minh failure outcome, Future cancellation khác success và task bị interrupt không để scope/context tồn tại trên worker.

## 11. Troubleshooting Executor observation

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Task logs thiếu traceId | Context không được capture/propagate | Kiểm tra TaskDecorator và accessor |
| Task mang traceId request cũ | Worker context không restore | Test thread reuse |
| Có executor metrics nhưng không có task spans | Binder chỉ đo pool | Thêm task Observation/instrumentation |
| Task spans bị duplicate | Auto instrumentation và custom wrapper cùng tạo span | Chọn một owner |
| Queue wait không được đo | Chỉ đo execution trong worker | Instrument submit-to-start |
| Active threads max, queue tăng | Pool saturation | Xem task duration, arrival rate, downstream |
| RejectedExecutionException tăng | Queue/pool hết capacity | Backpressure, capacity, rejection policy |
| Task chạy trên common pool | CompletableFuture không chỉ executor | Truyền executor tường minh |
| @Async chạy đồng bộ | Self-invocation hoặc proxy/config sai | Kiểm tra bean boundary và EnableAsync |
| Exception không có trong trace | Wrapper swallow exception | Record error và propagate outcome |
| Shutdown mất task | Queue in-memory hoặc timeout ngắn | Graceful shutdown/durable queue |
| Context mất trong Reactor | ThreadLocal không đủ reactive context | Micrometer Context Propagation |
| Security principal thiếu | Security context propagation chưa cấu hình | Cấu hình và test riêng |

### 11.1. Quy trình điều tra

1. Xác định executor thực tế mà task sử dụng.
2. Kiểm tra pool metrics: active, queue, remaining capacity, completed và rejection.
3. Đo queue wait riêng với execution time.
4. Kiểm tra task Observation/span có được tạo đúng một lần.
5. Kiểm tra trace parent/context ở caller và worker.
6. Test cleanup khi task thành công, lỗi, cancel và thread reuse.
7. Kiểm tra CompletableFuture có chuyển sang executor khác không.
8. Đối chiếu shutdown policy và durable delivery requirement.

## 12. Production checklist

| Tiêu chí | Bằng chứng |
| --- | --- |
| Executor có tên và cấu hình rõ | Bean/configuration được quản lý |
| Pool sizing theo workload | Core/max/queue dựa trên load test |
| Queue wait và execution tách biệt | Có measurements phù hợp |
| Executor metrics được expose | Active, pool, queue, completed, rejection |
| Task observation có tên ổn định | task.type và outcome low-cardinality |
| Context propagation được test | Trace/MDC được capture/restore |
| Không rò rỉ context | Thread reuse test pass |
| Exception/cancel được ghi nhận | Outcome và error semantics rõ |
| Rejection có backpressure | Không silently discard task quan trọng |
| Shutdown có giới hạn | Graceful timeout và policy |
| Durable task có storage phù hợp | Không phụ thuộc queue RAM khi cần bảo đảm |
| Privacy/cardinality được kiểm soát | Không task ID/user ID/body thành metric tags |
| Không duplicate spans | Một instrumentation owner cho mỗi boundary |

## 13. Bài thực hành: quan sát task nền tạo báo cáo

**Bối cảnh:** order-service nhận yêu cầu tạo báo cáo. HTTP endpoint enqueue task vào ThreadPoolTaskExecutor và trả 202 Accepted. Task đọc dữ liệu JDBC, tạo file và ghi trạng thái hoàn tất. Đội vận hành cần biết queue backlog, execution latency, lỗi và request nguồn.

**Nhiệm vụ:**
1. Tạo ThreadPoolTaskExecutor bean có core/max/queue/rejection/shutdown policy rõ.
2. Bật executor metrics và xác minh active, queue size, completed và rejection.
3. Tạo custom Observation report.generate cho task lifecycle.
4. Tách queue wait khỏi execution duration.
5. Cấu hình ContextPropagatingTaskDecorator và xác minh trace/MDC ở worker.
6. Xác định task là child span hay span có link tới request nguồn theo semantics nghiệp vụ.
7. Ghi nhận exception/cancel outcome và bảo đảm scope cleanup.
8. Dùng một worker và queue nhỏ để tạo saturation/rejection có kiểm soát.
9. Kiểm tra CompletableFuture/@Async dùng đúng executor.
10. Kiểm tra logs không có user ID, file path nhạy cảm hoặc message body trong tags.
11. Test thread reuse để xác minh task kế tiếp không nhận context cũ.
12. Viết runbook cho queue backlog, rejected task, missing trace context và shutdown.

**Kết quả mong đợi:** executor configuration, task Observation, pool metrics, trace/log correlation, test lifecycle/context/rejection và runbook vận hành.

## 14. Ghi nhớ

**Executor observation** cho biết task được submit, chờ trong queue, chạy và kết thúc như thế nào. Queue wait time giúp nhận diện backlog; execution time giúp tìm task chậm; executor metrics cho biết pool còn capacity hay đang saturation. Micrometer Observation mô tả task operation và tạo metrics/spans qua handlers, nhưng phải đặt đúng boundary để tránh đo trùng.

Thread boundary yêu cầu context propagation có capture/restore và cleanup. Dùng TaskDecorator/accessors phù hợp version để truyền tracing/MDC; không coi việc copy traceId vào MDC là propagation của parent span. Đặt executor tường minh cho async continuations, ghi nhận rejection/exception/cancellation và thiết kế shutdown theo yêu cầu durability. Dùng metrics để vận hành pool, traces để liên kết task với request và logs để điều tra outcome; giữ tags low-cardinality và không export dữ liệu nhạy cảm.

**Tài liệu tham khảo:**
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework — Context Propagation](https://docs.spring.io/spring-framework/reference/integration/observability.html)
- [Spring Boot — Task Execution and Scheduling](https://docs.spring.io/spring-boot/reference/features/task-execution-and-scheduling.html)
- [Micrometer Observation — Reference](https://docs.micrometer.io/micrometer/reference/observation.html)
- [Micrometer Context Propagation](https://docs.micrometer.io/context-propagation/reference/)
- [Micrometer Tracing — Reference](https://docs.micrometer.io/tracing/reference/)
- [Java ExecutorService](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html)

