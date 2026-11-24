# Đo tác vụ ExecutorService bằng binder phù hợp

`ExecutorService` quản lý việc thực thi tác vụ bất đồng bộ trên các worker thread. Để quan sát tình trạng pool và thời gian chạy tác vụ, Micrometer cung cấp `ExecutorServiceMetrics`. API `ExecutorServiceMetrics.monitor(...)` đăng ký các meter phù hợp với implementation executor và trả về một executor đã được bọc để đo thời gian thực thi tác vụ.

Với `ThreadPoolExecutor`, binder có thể cung cấp các số đo như số thread đang hoạt động, kích thước pool, số tác vụ đang chờ, số tác vụ đã hoàn tất và thời gian thực thi. Với một implementation chỉ khai báo qua interface `ExecutorService` mà không cung cấp thông tin pool, các số đo nội bộ như queue size hoặc active thread có thể không có. Vì vậy, cần chọn binder phù hợp với loại executor thực tế và giữ lại executor mà `monitor(...)` trả về để gửi tác vụ qua đúng lớp instrumentation.

## 1. Cần quan sát những gì ở ExecutorService?

Một executor có nhiều khía cạnh vận hành khác nhau. Chỉ đo tổng số tác vụ hoàn tất không đủ để biết pool có đang quá tải hay không.

| Khía cạnh | Số đo cần quan sát | Câu hỏi vận hành |
| --- | --- | --- |
| Mức sử dụng worker | Số thread active và pool size | Pool đang sử dụng bao nhiêu worker? |
| Hàng đợi | Số tác vụ queued và queue capacity còn lại | Tác vụ có đang tích tụ trước khi được chạy? |
| Throughput | Số tác vụ hoàn tất | Pool xử lý được bao nhiêu tác vụ? |
| Thời gian thực thi | Timer cho task execution | Một tác vụ thường chạy trong bao lâu? |
| Giới hạn pool | Core size và maximum size | Pool có đang chạm giới hạn cấu hình? |
| Từ chối tác vụ | Số lần rejected | Hệ thống có gửi nhiều tác vụ hơn khả năng tiếp nhận? |

Các số đo này có ý nghĩa khác nhau. `active` là trạng thái tại thời điểm đọc; `completed` là số tác vụ đã hoàn tất; `queued` là số tác vụ đang đợi worker. Không nên xem chúng như các cách biểu diễn thay thế cho nhau.

## 2. ExecutorServiceMetrics là binder phù hợp cho executor

Micrometer cung cấp lớp `ExecutorServiceMetrics` trong package `io.micrometer.core.instrument.binder.jvm`. Lớp này có thể theo dõi executor và cung cấp một wrapper để ghi thời gian thực thi tác vụ.

API thường dùng:

```java
ExecutorService monitored = ExecutorServiceMetrics.monitor(
        registry,
        executor,
        "order-worker",
        Tags.of("component", "order-processing")
);
```

Các tham số gồm:

- `registry`: registry nhận các meter.
- `executor`: executor thật mà ứng dụng muốn quan sát.
- `executorName`: tên ổn định để phân biệt pool.
- `tags`: các tag bổ sung có cardinality thấp.

Giá trị trả về là executor cần được ứng dụng sử dụng sau khi instrument. Nếu tiếp tục submit task trực tiếp qua biến `executor` gốc, phần đo thời gian thực thi do wrapper cung cấp có thể bị bỏ qua. Hãy giữ và inject biến `monitored` vào các thành phần gửi tác vụ.

Không tạo `ExecutorServiceMetrics` mới cho từng task. Việc monitor nên diễn ra một lần trong lúc khởi tạo pool; các request sau đó dùng lại executor đã được instrument.

## 3. Tạo và instrument ThreadPoolExecutor

`ExecutorService` là interface chung, không định nghĩa các thông tin như active thread, queue size hoặc pool size. `ThreadPoolExecutor` cung cấp các API cụ thể để đọc những trạng thái này, vì vậy là lựa chọn phù hợp khi cần quan sát sâu một worker pool.

Ví dụ tạo pool có giới hạn và instrument ngay khi khởi tạo:

```java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.binder.jvm.ExecutorServiceMetrics;
import io.micrometer.core.instrument.Tags;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ExecutorConfiguration {
    @Bean(destroyMethod = "shutdown")
    ExecutorService orderExecutor(MeterRegistry registry) {
        ThreadPoolExecutor delegate = new ThreadPoolExecutor(
                4,
                8,
                60,
                TimeUnit.SECONDS,
                new ArrayBlockingQueue<>(500)
        );

        return ExecutorServiceMetrics.monitor(
                registry,
                delegate,
                "order-worker",
                Tags.of("component", "order-processing")
        );
    }
}
```

Trong ví dụ, pool có 4 core thread, có thể mở rộng đến 8 thread và giữ tối đa 500 tác vụ trong queue. `ExecutorServiceMetrics.monitor(...)` đăng ký các meter rồi trả về executor đã instrument. Spring quản lý bean và gọi `shutdown()` khi application context dừng.

Giới hạn queue giúp hệ thống có một ngưỡng backlog rõ ràng. Queue không giới hạn có thể tiếp tục tăng khi tốc độ nhận tác vụ lớn hơn tốc độ xử lý, làm tăng bộ nhớ và thời gian chờ. Pool có queue hữu hạn cần một chính sách từ chối phù hợp; mặc định `ThreadPoolExecutor` sử dụng `AbortPolicy` nếu không chỉ định policy khác.

## 4. Gửi tác vụ qua executor đã instrument

Service nghiệp vụ chỉ cần inject executor bean:

```java
import java.util.concurrent.ExecutorService;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;

@Service
public class OrderAsyncProcessor {
    private final ExecutorService orderExecutor;

    public OrderAsyncProcessor(
            @Qualifier("orderExecutor") ExecutorService orderExecutor) {
        this.orderExecutor = orderExecutor;
    }

    public void processAsync(Order order) {
        orderExecutor.execute(() -> process(order));
    }

    private void process(Order order) {
        // Xử lý nghiệp vụ bất đồng bộ.
    }
}
```

Mọi task được gửi qua `orderExecutor` đều đi qua executor đã được monitor. Không lấy executor delegate từ một nơi khác rồi sử dụng xen kẽ, vì khi đó một phần tác vụ sẽ không đi qua wrapper đo thời gian.

Nếu ứng dụng có nhiều pool cho các loại công việc khác nhau, hãy tạo bean riêng và đặt `executorName` ổn định cho từng pool, chẳng hạn `order-worker`, `email-worker` hoặc `report-worker`.

## 5. Các meter thường gặp

Với `ThreadPoolExecutor`, Micrometer có thể đăng ký các meter mang tên dạng `executor.*`. Tập meter cụ thể phụ thuộc loại executor, phiên bản Micrometer và các thông tin mà implementation cung cấp.

| Meter thường gặp | Ý nghĩa | Loại số đo |
| --- | --- | --- |
| `executor` | Thời gian thực thi task qua executor wrapper | Timer |
| `executor.completed` | Số task đã hoàn tất theo thống kê của pool | Function counter hoặc counter-like measurement |
| `executor.active` | Số worker thread đang thực thi task | Gauge |
| `executor.queued` | Số task đang chờ trong queue | Gauge |
| `executor.pool.size` | Tổng số worker thread hiện có | Gauge |
| `executor.pool.core` | Core pool size được cấu hình | Gauge |
| `executor.pool.max` | Maximum pool size được cấu hình | Gauge |
| `executor.queue.remaining` | Số vị trí còn trống trong queue có giới hạn | Gauge |

Một số implementation có thể cung cấp thêm số đo idle thread, task steal hoặc thông tin riêng của ForkJoinPool. Không giả định mọi executor đều có đầy đủ mọi meter trong bảng. Hãy kiểm tra tên và tag thực tế bằng `/actuator/metrics` hoặc trực tiếp trên registry.

### 5.1. Đọc active và pool size

`executor.active` cho biết số worker đang chạy task tại thời điểm lấy mẫu. `executor.pool.size` cho biết tổng số worker thread hiện có. Với pool có maximum size là 8, nếu active thường xuyên bằng 8 và queue liên tục tăng, pool có thể đang thiếu năng lực xử lý hoặc tác vụ đang chạy quá lâu.

Không kết luận pool quá tải chỉ từ một sample active cao. Hãy xem xu hướng trong một khoảng thời gian, queue depth, task duration và rejected count.

### 5.2. Đọc queued và queue remaining

`executor.queued` phản ánh backlog hiện tại. `executor.queue.remaining` phản ánh dung lượng còn lại của queue nếu queue hỗ trợ khái niệm capacity hữu hạn.

Nếu queued tăng liên tục và remaining giảm về 0, executor đang tiếp nhận task nhanh hơn khả năng xử lý. Khi queue đầy, chính sách rejection có thể từ chối task hoặc thực thi task ở caller thread tùy policy.

### 5.3. Đọc completed và task duration

`executor.completed` là số task đã hoàn tất theo thống kê executor. Nó không có nghĩa mọi task đều thành công về nghiệp vụ. Một task kết thúc bằng exception vẫn có thể được tính là đã hoàn tất ở mức executor.

Timer `executor` ghi nhận thời gian thực thi task qua wrapper. Đây là thời gian task chạy trên worker theo semantics của instrumentation; không nên mặc định nó bao gồm toàn bộ thời gian task nằm trong queue trước khi được worker nhận.

Nếu cần phân biệt task thành công, thất bại và bị từ chối, hãy tạo counter nghiệp vụ riêng với tag `result` có tập giá trị hữu hạn.

## 6. Phân biệt thời gian chờ queue và thời gian thực thi

Một task bất đồng bộ có ít nhất hai khoảng thời gian cần quan sát:

1. **Queue wait time**: từ lúc submit đến lúc worker bắt đầu chạy task.
2. **Execution time**: từ lúc worker bắt đầu chạy đến lúc task kết thúc.

`ExecutorServiceMetrics` cung cấp các số đo trạng thái pool và timer thực thi task qua executor wrapper. Nếu cần queue wait time, hãy đo riêng tại điểm submit và điểm bắt đầu chạy. Không suy ra queue wait chỉ từ timer execution.

Ví dụ đo queue wait bằng `System.nanoTime()`:

```java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.TimeUnit;

public final class QueueWaitRecorder {
    private final ExecutorService executor;
    private final Timer queueWait;

    public QueueWaitRecorder(ExecutorService executor, MeterRegistry registry) {
        this.executor = executor;
        this.queueWait = Timer.builder("app.executor.queue.wait")
                .description("Time a task waits before a worker starts it")
                .tag("pool", "order-worker")
                .register(registry);
    }

    public void execute(Runnable task) {
        long submittedAt = System.nanoTime();
        executor.execute(() -> {
            queueWait.record(
                    System.nanoTime() - submittedAt,
                    TimeUnit.NANOSECONDS
            );
            task.run();
        });
    }
}
```

Queue wait được ghi ngay khi worker bắt đầu chạy task. Task bị từ chối trước khi vào queue hoặc bị hủy trước khi bắt đầu sẽ không tạo sample trong timer này; nếu cần theo dõi các trường hợp đó, hãy instrument rejection và cancellation riêng.

Không dùng `currentTimeMillis()` để đo khoảng thời gian ngắn vì đồng hồ hệ thống có thể bị điều chỉnh. `System.nanoTime()` phù hợp để đo elapsed time.

## 7. Theo dõi task bị từ chối

Với queue hữu hạn, `ThreadPoolExecutor` có thể từ chối task khi đã đạt giới hạn thread và queue. Hành vi phụ thuộc `RejectedExecutionHandler`:

| Policy | Hành vi | Ảnh hưởng đến metrics |
| --- | --- | --- |
| `AbortPolicy` | Ném `RejectedExecutionException` | Có thể đếm rejection tại nơi submit bắt exception. |
| `CallerRunsPolicy` | Chạy task trên thread gọi submit | Có thể làm chậm request thread và thay đổi thời gian phản hồi. |
| `DiscardPolicy` | Bỏ task bị từ chối | Cần metric riêng nếu muốn biết task bị bỏ. |
| `DiscardOldestPolicy` | Bỏ task cũ nhất trong queue rồi thử submit task mới | Cần metric riêng để quan sát task bị loại. |

Ví dụ đếm rejection khi submit:

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.RejectedExecutionException;

public final class MeasuredSubmission {
    private final ExecutorService executor;
    private final Counter rejected;

    public MeasuredSubmission(ExecutorService executor, MeterRegistry registry) {
        this.executor = executor;
        this.rejected = Counter.builder("app.executor.rejected")
                .description("Number of tasks rejected during submission")
                .tag("pool", "order-worker")
                .register(registry);
    }

    public void execute(Runnable task) {
        try {
            executor.execute(task);
        } catch (RejectedExecutionException exception) {
            rejected.increment();
            throw exception;
        }
    }
}
```

Đoạn code này phù hợp với policy ném `RejectedExecutionException`. Với policy bỏ task mà không ném exception, cần một `RejectedExecutionHandler` có instrumentation riêng; không thể dựa vào catch này để đếm mọi trường hợp bị loại.

## 8. Giới hạn của binder theo implementation executor

`ExecutorService` chỉ định nghĩa các thao tác submit, execute, shutdown và lấy trạng thái Future. Nó không có API chung để đọc queue size, active thread hoặc pool size. Vì vậy:

- `ThreadPoolExecutor` cung cấp nhiều thông tin để binder đăng ký gauge.
- `ForkJoinPool` cung cấp các thống kê riêng như parallelism, active/running thread, queued task và steal count.
- Một executor tùy chỉnh có thể không expose các thống kê nội bộ; binder không thể tự suy ra queue depth hoặc pool saturation nếu implementation không cung cấp dữ liệu.

Nếu dùng executor tùy chỉnh, hãy cung cấp meter riêng dựa trên API trạng thái mà executor đó hỗ trợ. Tránh truy cập reflection vào field nội bộ của JDK hoặc thư viện vì dễ vỡ khi nâng phiên bản.

### 8.1. Không instrument cùng một pool nhiều lần

Đăng ký binder nhiều lần cho cùng executor và cùng registry có thể dẫn đến meter trùng danh tính hoặc xung đột nguồn đo. Hãy gọi `ExecutorServiceMetrics.monitor(...)` một lần trong cấu hình bean và chia sẻ executor đã instrument.

Không tạo wrapper mới cho mỗi service hoặc mỗi request. Nếu nhiều service cùng gửi task vào một pool, hãy inject chung một bean executor đã instrument.

## 9. Cardinality và tag cho executor

Tag của executor nên nhận diện pool hoặc nhóm công việc, không nhận diện từng task. Ví dụ phù hợp:

- `pool=order-worker`
- `pool=email-worker`
- `component=report-generation`
- `workload=background`

Tránh các tag có giá trị thay đổi liên tục:

- task ID hoặc request ID;
- user ID, order ID hoặc tenant ID không giới hạn;
- tên thread chứa số thứ tự tăng dần;
- exception message hoặc tên class động do wrapper tự tạo.

Nếu có 5 pool cố định và mỗi pool có 3 tag value hữu hạn, số meter có thể dự đoán. Nếu tạo một pool hoặc tag mới theo từng request, cardinality và chi phí lưu trữ có thể tăng không giới hạn.

Tên executor truyền vào `monitor` nên ổn định. Tag bổ sung cũng nên có giá trị cố định và không trùng với các chiều mà registry đã gắn tự động.

## 10. Vòng đời và shutdown của executor

Executor thường là tài nguyên dùng chung trong suốt vòng đời application context. Hãy tạo nó trong cấu hình Spring, inject qua constructor và để Spring gọi shutdown khi ứng dụng dừng.

Khi dùng `ExecutorServiceMetrics.monitor(...)`, bean nên trả về executor đã instrument để mọi nơi sử dụng cùng wrapper. `destroyMethod = "shutdown"` gọi shutdown trên đối tượng được Spring quản lý; wrapper do Micrometer trả về ủy quyền thao tác lifecycle cho executor bên dưới theo implementation của nó.

Không đóng `MeterRegistry` từ service sử dụng executor. Registry do application context hoặc cấu hình metrics quản lý. Cũng không để executor tiếp tục nhận task sau khi context đã dừng.

Nếu ứng dụng cần chờ task đang chạy hoàn tất, hãy cấu hình shutdown policy và thời gian chờ phù hợp. Có thể gọi `awaitTermination` trong lifecycle owner sau `shutdown`, nhưng cần timeout hữu hạn để quá trình dừng ứng dụng không bị treo vô hạn.

## 11. Kiểm thử binder và executor metrics

Có thể dùng `SimpleMeterRegistry` để kiểm tra binder đăng ký meter, wrapper thực thi task và registry nhận được dữ liệu:

```java
import static org.assertj.core.api.Assertions.assertThat;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Tags;
import io.micrometer.core.instrument.binder.jvm.ExecutorServiceMetrics;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;

class ExecutorMetricsTest {
    @Test
    void registersMetricsAndMeasuresSubmittedTask() throws Exception {
        try (SimpleMeterRegistry registry = new SimpleMeterRegistry()) {
            ThreadPoolExecutor delegate = new ThreadPoolExecutor(
                    1, 1, 0, TimeUnit.MILLISECONDS,
                    new ArrayBlockingQueue<>(10)
            );
            ExecutorService monitored = ExecutorServiceMetrics.monitor(
                    registry,
                    delegate,
                    "test-worker",
                    Tags.of("component", "test")
            );

            try {
                CountDownLatch completed = new CountDownLatch(1);
                monitored.execute(completed::countDown);

                assertThat(completed.await(2, TimeUnit.SECONDS)).isTrue();
                assertThat(registry.getMeters()).isNotEmpty();
                assertThat(registry.getMeters().stream()
                        .anyMatch(meter -> meter.getId().getName()
                                .startsWith("executor"))).isTrue();
            } finally {
                monitored.shutdownNow();
                monitored.awaitTermination(2, TimeUnit.SECONDS);
            }
        }
    }
}
```

Test này xác minh đường instrument được sử dụng và có meter trong registry. Khi kiểm tra sâu hơn, hãy truy vấn đúng meter name/tag của phiên bản Micrometer trong dự án và xác nhận timer có count tăng sau khi task hoàn tất.

### 11.1. Kiểm thử queue và rejection

Để kiểm thử queue depth hoặc rejection, dùng pool một thread với queue nhỏ và một task giữ worker bằng `CountDownLatch`. Submit thêm task để tạo backlog, sau đó xác minh gauge queued tăng. Khi queue đầy, submit thêm task và xác minh policy rejection đúng như cấu hình.

Test cần giải phóng latch trong `finally` và shutdown executor dù assertion thành công hay thất bại. Tránh dùng `Thread.sleep()` dài để chờ trạng thái; latch và timeout hữu hạn giúp test xác định hơn.

## 12. Đọc executor metrics qua Actuator hoặc backend

Trong Spring Boot, nếu endpoint metrics được expose, có thể khám phá meter:

```bash
curl.exe http://localhost:8080/actuator/metrics
```

Sau đó đọc một meter cụ thể, ví dụ:

```bash
curl.exe "http://localhost:8080/actuator/metrics/executor.active"
curl.exe "http://localhost:8080/actuator/metrics/executor.queued"
curl.exe "http://localhost:8080/actuator/metrics/executor.completed"
```

Tên meter thực tế và tag có thể khác theo implementation, phiên bản và cấu hình. Hãy lấy tên từ danh sách `names` và dùng `availableTags` để tìm tag `name` hoặc tag pool tương ứng trước khi lọc.

Với Prometheus, registry có thể chuẩn hóa tên thành dạng như `executor_active_threads` hoặc tên tương tự theo convention. Không sao chép tên từ Actuator JSON sang PromQL mà không kiểm tra `/actuator/prometheus`.

## 13. Diễn giải dấu hiệu quá tải

Không có một metric đơn lẻ đủ để kết luận executor bị quá tải. Hãy kết hợp các tín hiệu:

| Quan sát | Có thể chỉ ra | Cần kiểm tra thêm |
| --- | --- | --- |
| Active gần bằng max trong thời gian dài | Worker thường xuyên bận | Task duration, CPU, I/O blocking và throughput |
| Queue tăng liên tục | Tốc độ submit lớn hơn tốc độ hoàn tất | Task arrival rate, completed rate và queue capacity |
| Queue remaining thường xuyên bằng 0 | Queue chạm giới hạn | Rejection count và caller-runs behavior |
| Task duration tăng | Công việc chạy chậm hơn | Dependency latency, lock contention, GC hoặc CPU |
| Completed rate giảm trong khi active cao | Worker bị giữ lâu hoặc bị block | Thread dump, downstream call và deadlock |
| Rejected tăng | Pool không tiếp nhận được tải hiện tại | Giới hạn pool, queue, backpressure và tốc độ producer |

Tăng số thread không phải lúc nào cũng giải quyết được vấn đề. Nếu task chủ yếu chờ I/O, thêm thread có thể tăng concurrency; nếu task bị giới hạn CPU, thêm thread có thể làm context switching tăng. Nếu queue tăng do downstream chậm, cần xem lại timeout, bulkhead, retry và backpressure.

## 14. Những lỗi thường gặp

- **Chỉ instrument interface `ExecutorService` và kỳ vọng có mọi gauge pool:** interface không cung cấp queue size hoặc active thread.
- **Bỏ qua executor wrapper trả về từ `monitor`:** task không đi qua lớp đo thời gian.
- **Submit qua executor gốc ở một số call site:** số liệu task duration không phản ánh toàn bộ tác vụ.
- **Gọi monitor nhiều lần cho cùng pool:** tạo đăng ký lặp và khó kiểm soát identity meter.
- **Dùng queue không giới hạn:** backlog có thể tăng vô hạn mà không có tín hiệu capacity rõ ràng.
- **Coi completed là task thành công:** task kết thúc bằng exception vẫn có thể được tính completed.
- **Nhầm execution time với queue wait time:** cần đo hai khoảng riêng.
- **Không đo rejected task:** bỏ qua tín hiệu pool đã đạt giới hạn.
- **Gắn task ID hoặc thread ID vào tag:** cardinality tăng theo số tác vụ.
- **Không shutdown executor:** thread còn sống sau khi application context dừng.
- **Đóng registry từ service:** phá vỡ lifecycle metrics dùng chung.

## 15. Checklist triển khai ExecutorService metrics

- [ ] Chọn implementation có API trạng thái phù hợp, thường là `ThreadPoolExecutor` hoặc `ForkJoinPool`.
- [ ] Tạo executor một lần trong application lifecycle.
- [ ] Gọi `ExecutorServiceMetrics.monitor(...)` một lần với registry và tên pool ổn định.
- [ ] Giữ executor wrapper được trả về và inject wrapper vào mọi nơi submit task.
- [ ] Dùng queue có giới hạn và chọn rejection policy có chủ đích.
- [ ] Theo dõi active, pool size, queued, remaining capacity và completed.
- [ ] Phân biệt task execution time với queue wait time.
- [ ] Đếm rejection và kết quả nghiệp vụ riêng nếu cần.
- [ ] Giữ tag có cardinality thấp, không dùng task/user/request ID.
- [ ] Để Spring hoặc lifecycle owner shutdown executor đúng cách.
- [ ] Kiểm thử meter registration, task execution, queue backlog và rejection.
- [ ] Đọc tên/tag thực tế qua Actuator hoặc endpoint export trước khi tạo dashboard.

`ExecutorServiceMetrics` giúp biến trạng thái worker pool và thời gian thực thi task thành metrics có thể quan sát. Hãy instrument đúng executor một lần, sử dụng wrapper được trả về, theo dõi đồng thời worker, queue, completed và rejection. Nếu cần đo thời gian chờ trước khi task bắt đầu, hãy ghi thêm queue-wait timer riêng. Việc phân biệt các khoảng thời gian và trạng thái này giúp xác định pool thiếu worker, queue quá tải hay bản thân tác vụ đang chạy chậm.
