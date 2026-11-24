# Giám sát executor, số luồng hoạt động và tác vụ chờ

Executor là thành phần nhận tác vụ và điều phối việc thực thi trên một hoặc nhiều luồng. Khi tải tăng, executor có thể dùng hết số luồng, tích lũy tác vụ trong hàng đợi hoặc từ chối tác vụ mới. Nếu chỉ theo dõi CPU và request latency, người vận hành có thể không nhận ra hàng đợi đang tăng cho đến khi độ trễ của ứng dụng đã cao.

Micrometer cung cấp binder để quan sát các executor phổ biến của Java. Với ThreadPoolExecutor, các metrics thường cho biết số luồng đang hoạt động, số tác vụ đang chờ, số tác vụ đã hoàn tất, kích thước pool, core/max pool size và sức chứa còn lại của queue. Những số liệu này giúp nhận biết executor thiếu năng lực xử lý, cấu hình queue chưa phù hợp hoặc workload đang dồn ứ.

Trong module **OBSERVABILITY_INSTRUMENTATION_MICROMETER**, bài này tập trung vào việc bind executor với MeterRegistry, đọc ý nghĩa các metrics, cấu hình pool có giới hạn, xây dựng truy vấn và cảnh báo, đồng thời kiểm thử để xác nhận số liệu phản ánh trạng thái thực tế.

## 1. Executor và các trạng thái cần quan sát

Một ThreadPoolExecutor quản lý một tập worker thread và một hàng đợi tác vụ. Khi ứng dụng submit một Runnable hoặc Callable, executor quyết định chạy ngay, đưa vào queue hay từ chối.

Với ThreadPoolExecutor, luồng xử lý thường theo thứ tự:

1. Nếu số worker đang chạy nhỏ hơn corePoolSize, executor có thể tạo worker mới để chạy tác vụ.
2. Khi đã đạt corePoolSize, tác vụ mới thường được đưa vào queue nếu queue còn chỗ.
3. Khi queue đầy, executor có thể tạo thêm worker cho đến maximumPoolSize.
4. Khi cả queue và pool đều đạt giới hạn, tác vụ mới bị xử lý theo RejectedExecutionHandler.

Vì vậy, chỉ nhìn số luồng hoạt động chưa đủ. Một pool có thể còn ít thread đang chạy nhưng queue đã tăng do tác vụ bị chặn hoặc xử lý chậm; ngược lại, active thread cao nhưng queue gần 0 có thể là trạng thái bình thường khi pool đang bận và vẫn xử lý kịp.

Các trạng thái cần theo dõi gồm:

- Số luồng đang thực thi tác vụ.
- Số tác vụ đang chờ trong queue.
- Số tác vụ đã hoàn tất.
- Số thread hiện có trong pool.
- Core size và maximum size.
- Sức chứa còn lại của queue nếu queue hỗ trợ truy vấn capacity.

## 2. Bind ExecutorService với Micrometer

Micrometer cung cấp ExecutorServiceMetrics trong package binder.jvm để đăng ký các meter cho executor được hỗ trợ. Có thể dùng phương thức monitor để bind executor vào registry:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Tags;
import io.micrometer.core.instrument.binder.jvm.ExecutorServiceMetrics;

public class WorkerPoolFactory {

    public ThreadPoolExecutor create(MeterRegistry registry) {
        ThreadPoolExecutor executor = new ThreadPoolExecutor(
                8,
                32,
                60,
                TimeUnit.SECONDS,
                new ArrayBlockingQueue<>(200)
        );

        ExecutorServiceMetrics.monitor(
                registry,
                executor,
                "worker",
                Tags.of("pool", "worker")
        );

        return executor;
    }
}
~~~

Trong ví dụ:

- Core pool có 8 thread.
- Maximum pool có 32 thread.
- Thread vượt core có thể được giữ tối đa 60 giây khi idle.
- Queue chứa tối đa 200 tác vụ.
- Tag pool phân biệt executor này với các pool khác.

Hãy bind một lần cho mỗi executor. Không gọi monitor mỗi lần submit tác vụ hoặc mỗi lần refresh metrics; làm vậy có thể tạo đăng ký lặp và gây khó khăn khi quản lý vòng đời meter.

Tên meter và các tag cụ thể phụ thuộc binder và phiên bản Micrometer. Ví dụ sử dụng tag pool do ứng dụng cung cấp để phân biệt pool; khi dùng Prometheus, tên meter có thể được chuẩn hóa dấu chấm thành dấu gạch dưới và Counter/FunctionCounter có thể có hậu tố theo quy ước exporter. Luôn kiểm tra endpoint export để xác nhận tên thực tế.

## 3. Các metrics executor thường gặp

Với ThreadPoolExecutor được hỗ trợ, binder thường cung cấp các meter sau:

| Meter Micrometer | Ý nghĩa | Cách diễn giải |
|---|---|---|
| executor.active | Số thread hiện đang thực thi tác vụ | Giá trị cao kéo dài có thể cho thấy pool luôn bận |
| executor.queued | Số tác vụ đang chờ trong queue | Tăng liên tục là dấu hiệu backlog |
| executor.completed | Tổng số tác vụ đã hoàn tất theo bộ đếm của executor | Dùng rate để xem throughput; giá trị có thể reset khi executor được tạo lại |
| executor.pool.size | Số thread hiện có trong pool | Cho biết pool đang có bao nhiêu worker |
| executor.pool.core | Core pool size | Ngưỡng worker cơ bản được cấu hình |
| executor.pool.max | Maximum pool size | Giới hạn số worker tối đa |
| executor.queue.remaining | Sức chứa còn lại của queue | Chỉ có ý nghĩa khi queue hỗ trợ báo capacity hữu hạn |

Không phải mọi implementation ExecutorService đều cung cấp đầy đủ các thông tin này. ThreadPoolExecutor có các phương thức như getActiveCount(), getQueue(), getPoolSize(), getCorePoolSize(), getMaximumPoolSize() và getCompletedTaskCount(); một executor khác có thể không có các khái niệm tương đương. Hãy kiểm tra meter thực tế được binder đăng ký.

Các giá trị active, queued và pool size là số liệu quan sát gần đúng tại thời điểm đọc, có thể thay đổi ngay sau đó khi thread bắt đầu hoặc kết thúc tác vụ. Không dùng chúng như một phép đếm giao dịch chính xác.

## 4. Đọc active threads và queued tasks cùng nhau

Hai chỉ số quan trọng nhất khi điều tra backlog là executor.active và executor.queued.

| Active | Queued | Diễn giải có thể xảy ra |
|---|---|---|
| Thấp | Thấp | Pool còn dư năng lực hoặc lưu lượng đang thấp |
| Cao, gần max | Thấp | Pool bận nhưng queue chưa tích lũy; kiểm tra throughput và thời gian tác vụ |
| Cao, gần max | Tăng liên tục | Năng lực xử lý không theo kịp tốc độ submit hoặc tác vụ bị chậm |
| Thấp | Cao | Có thể worker bị block, pool không mở rộng như dự kiến hoặc queue được dùng trước khi tăng thread |
| Cao | Cao nhưng ổn định | Có backlog nhưng hệ thống có thể đang xử lý ổn định; cần xem xu hướng và thời gian chờ |

Không kết luận sự cố chỉ từ một ảnh chụp. Queue có thể tăng tạm thời trong một burst rồi giảm khi tải hạ. Dấu hiệu đáng quan tâm hơn là queue tăng qua nhiều lần scrape, active giữ sát giới hạn, throughput không tăng và latency của tác vụ tiếp tục xấu đi.

Cũng cần hiểu cấu hình queue ảnh hưởng đến cách ThreadPoolExecutor mở rộng. Với queue không giới hạn như LinkedBlockingQueue không đặt capacity, executor thường tiếp tục enqueue sau khi đạt corePoolSize; maximumPoolSize có thể không được sử dụng như kỳ vọng. Queue có giới hạn giúp executor có cơ hội tăng thread đến max khi queue đầy, rồi áp dụng rejection policy nếu vẫn quá tải.

## 5. Cấu hình Spring Boot với ThreadPoolTaskExecutor

Trong ứng dụng Spring, ThreadPoolTaskExecutor là abstraction thường dùng để chạy tác vụ bất đồng bộ. Có thể cấu hình core/max size và queue capacity:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class WorkerExecutorConfiguration {

    @Bean
    public ThreadPoolTaskExecutor workerExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(8);
        executor.setMaxPoolSize(32);
        executor.setQueueCapacity(200);
        executor.setKeepAliveSeconds(60);
        executor.setThreadNamePrefix("worker-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(30);
        return executor;
    }
}
~~~

Spring quản lý vòng đời bean và khởi tạo ThreadPoolTaskExecutor. Nếu cần bind thủ công với ExecutorServiceMetrics, hãy lấy ThreadPoolExecutor bên trong sau khi ThreadPoolTaskExecutor đã được khởi tạo. Có thể dùng SmartInitializingSingleton để thực hiện việc bind sau khi các singleton đã được tạo:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Tags;
import io.micrometer.core.instrument.binder.jvm.ExecutorServiceMetrics;
import org.springframework.beans.factory.SmartInitializingSingleton;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class WorkerExecutorMetricsConfiguration {

    @Bean
    SmartInitializingSingleton bindWorkerExecutorMetrics(
            ThreadPoolTaskExecutor workerExecutor,
            MeterRegistry registry) {

        return () -> ExecutorServiceMetrics.monitor(
                registry,
                workerExecutor.getThreadPoolExecutor(),
                "worker",
                Tags.of("pool", "worker")
        );
    }
}
~~~

Cách bind thủ công này cần thiết khi ứng dụng chưa tự động instrument executor tương ứng. Một số phiên bản Spring Boot có thể tự cấu hình metrics cho các executor bean được hỗ trợ. Trước khi thêm binder thủ công, hãy kiểm tra registry đã có meter cho pool đó chưa để tránh đăng ký trùng hoặc tạo hai bộ metrics cùng mô tả một executor.

Nếu Spring Boot tự động instrument executor, nên dùng cơ chế cấu hình và tag mà phiên bản đó hỗ trợ. Nếu không, binder Micrometer có thể được gắn sau khi executor đã sẵn sàng như ví dụ trên.

## 6. Chọn queue capacity và pool size

Queue quá nhỏ có thể khiến tác vụ bị từ chối trong các đợt burst ngắn. Queue quá lớn có thể giữ nhiều tác vụ chờ lâu, làm tăng latency và bộ nhớ, đồng thời che giấu việc pool không đủ năng lực xử lý.

Một số yếu tố cần cân nhắc:

- Thời gian thực thi trung bình và p95/p99 của tác vụ.
- Tốc độ submit tác vụ ở tải bình thường và tải đỉnh.
- Mức độ CPU-bound hay I/O-bound của tác vụ.
- Bộ nhớ mỗi tác vụ giữ trong closure, request context hoặc payload.
- Khả năng chịu trễ của nghiệp vụ.
- Chính sách khi queue đầy: caller-runs, abort, discard hoặc cơ chế tùy chỉnh.

Không có công thức core/max size phù hợp cho mọi ứng dụng. Với tác vụ CPU-bound, số worker thường cần gần với số CPU khả dụng; với tác vụ I/O-bound, có thể dùng nhiều worker hơn nhưng phải tính đến giới hạn kết nối, downstream và bộ nhớ. Cần benchmark trên workload đại diện.

Ví dụ một queue 200 phần tử không có nghĩa ứng dụng có thể nhận an toàn mọi burst 200 tác vụ. Nếu mỗi tác vụ giữ payload 2 MB, queue có thể giữ xấp xỉ 400 MB dữ liệu payload chưa tính overhead object. Queue capacity phải được đánh giá cả theo số lượng và kích thước tác vụ.

## 7. Dùng PromQL để quan sát pool

Sau khi xác nhận tên series thực tế trên endpoint Prometheus, có thể dùng các truy vấn dạng sau. Các tên bên dưới là ví dụ sau khi exporter chuẩn hóa tên meter; hãy thay bằng tên chính xác mà ứng dụng đang xuất.

Số thread đang hoạt động:

~~~promql
executor_active{pool="worker"}
~~~

Số tác vụ đang chờ:

~~~promql
executor_queued{pool="worker"}
~~~

Tốc độ hoàn tất tác vụ:

~~~promql
rate(executor_completed_total{pool="worker"}[5m])
~~~

Tỷ lệ thread đang hoạt động so với maximum pool size:

~~~promql
executor_active{pool="worker"}
/
executor_pool_max{pool="worker"}
~~~

Tỷ lệ này chỉ có ý nghĩa khi maximum pool size lớn hơn 0 và cả hai series có cùng tag. Nó là một tín hiệu bận của pool, không phải phần trăm CPU.

Với queue có capacity hữu hạn, có thể ước lượng mức sử dụng queue bằng số tác vụ đang chờ chia cho tổng số vị trí đang dùng và còn trống:

~~~promql
executor_queued{pool="worker"}
/
(
  executor_queued{pool="worker"}
  +
  executor_queue_remaining{pool="worker"}
)
~~~

Truy vấn này chỉ phù hợp khi queue.remaining được export và phản ánh capacity hữu hạn. Nếu queue không hỗ trợ remaining capacity hoặc metric không tồn tại, không dùng biểu thức này; hãy theo dõi queued tuyệt đối và cấu hình capacity riêng.

## 8. Xây dựng cảnh báo theo xu hướng, không chỉ một ngưỡng

Một cảnh báo đơn giản có thể phát hiện queue liên tục tăng trong khi pool gần hết worker:

~~~promql
(
  executor_queued{pool="worker"} > 100
)
and
(
  executor_active{pool="worker"}
  /
  executor_pool_max{pool="worker"} > 0.9
)
~~~

Trong production, nên thêm for trong rule Prometheus để tránh cảnh báo do một spike ngắn:

~~~yaml
groups:
  - name: executor-alerts
    rules:
      - alert: WorkerExecutorBacklog
        expr: |
          executor_queued{pool="worker"} > 100
          and
          executor_active{pool="worker"}
            / executor_pool_max{pool="worker"} > 0.9
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: Worker executor is saturated
          description: Worker queue is above 100 while active threads are near the configured maximum.
~~~

Ngưỡng 100 và 90% chỉ là ví dụ. Hãy chọn theo queue capacity, SLA, thời gian xử lý và mức tải thực tế. Nếu max pool size có thể bằng 0 hoặc series bị thiếu, cần thêm điều kiện bảo vệ trong rule.

Cảnh báo nên kết hợp với latency của tác vụ, tỷ lệ lỗi và số tác vụ bị từ chối. Một queue tăng nhưng latency vẫn nằm trong SLA có thể chưa cần hành động; queue tăng cùng rejected tasks và latency cao là tín hiệu nghiêm trọng hơn.

## 9. Metrics có sẵn không đo hết mọi vấn đề của executor

Binder cung cấp trạng thái pool và số tác vụ hoàn tất, nhưng thường không tự cung cấp mọi chỉ số nghiệp vụ cần thiết.

Các số đo nên bổ sung nếu có nhu cầu:

- Task wait time: thời gian từ lúc submit đến lúc worker bắt đầu thực thi.
- Task execution time: thời gian chạy một tác vụ.
- Rejected tasks: số tác vụ bị từ chối khi queue/pool đầy.
- Task outcome: số tác vụ thành công và thất bại.
- Task age: thời gian của tác vụ cũ nhất đang chờ, nếu nguồn queue cho phép.

Có thể dùng Timer để đo thời gian thực thi và Counter để đếm rejection. Để đo queue wait, cần ghi thời điểm submit bằng monotonic clock và dừng đo khi worker bắt đầu; không dùng wall-clock timestamp để tính duration. Giữ tag ở mức hữu hạn như pool, task_type hoặc outcome; không đưa task ID, request ID hay user ID vào tag.

Ví dụ đếm tác vụ bị từ chối bằng một RejectedExecutionHandler tùy chỉnh:

~~~java
import java.util.concurrent.RejectedExecutionHandler;
import java.util.concurrent.ThreadPoolExecutor;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;

public class MeteredRejectionHandler implements RejectedExecutionHandler {
    private final Counter rejected;

    public MeteredRejectionHandler(MeterRegistry registry) {
        this.rejected = Counter.builder("executor.rejected")
                .description("Number of tasks rejected by an executor")
                .tag("pool", "worker")
                .register(registry);
    }

    @Override
    public void rejectedExecution(
            Runnable task,
            ThreadPoolExecutor executor) {
        rejected.increment();
        throw new java.util.concurrent.RejectedExecutionException(
                "Worker executor is saturated"
        );
    }
}
~~~

Đây là một lựa chọn chính sách từ chối. Nếu dùng CallerRunsPolicy hoặc một handler tùy chỉnh khác, cần giữ đúng semantics mong muốn: caller-runs có thể chạy tác vụ trên thread submit thay vì từ chối; không nên tăng rejected counter cho trường hợp tác vụ thực sự được chạy theo chính sách đó.

## 10. Kiểm thử metrics của executor

Có thể kiểm tra binder với SimpleMeterRegistry và một ThreadPoolExecutor có một worker cùng queue giới hạn. Dùng CountDownLatch để giữ tác vụ đầu tiên đang chạy, rồi submit tác vụ thứ hai vào queue:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

import io.micrometer.core.instrument.Tags;
import io.micrometer.core.instrument.binder.jvm.ExecutorServiceMetrics;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

class ExecutorMetricsTest {

    @Test
    void reportsActiveAndQueuedTasks() throws Exception {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        ThreadPoolExecutor executor = new ThreadPoolExecutor(
                1, 1, 0, TimeUnit.SECONDS,
                new ArrayBlockingQueue<>(2)
        );

        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            ExecutorServiceMetrics.monitor(
                    registry, executor, "worker",
                    Tags.of("pool", "worker")
            );

            executor.submit(() -> {
                started.countDown();
                try {
                    release.await();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                }
            });

            assertThat(started.await(2, TimeUnit.SECONDS)).isTrue();

            executor.submit(() -> { });

            double active = registry.get("executor.active")
                    .tag("pool", "worker")
                    .gauge()
                    .value();

            double queued = registry.get("executor.queued")
                    .tag("pool", "worker")
                    .gauge()
                    .value();

            assertThat(active).isEqualTo(1.0);
            assertThat(queued).isEqualTo(1.0);
        } finally {
            release.countDown();
            executor.shutdown();
            assertThat(executor.awaitTermination(2, TimeUnit.SECONDS)).isTrue();
            registry.close();
        }
    }
}
~~~

Test này kiểm tra trạng thái trong một tình huống có thể điều khiển: một task đang chạy và một task đang chờ. Trong dự án thực tế, xác nhận tên meter và tag theo đúng phiên bản Micrometer. Nếu executor có cơ chế auto-instrumentation khác, bảo đảm test không bind cùng executor hai lần.

Có thể bổ sung kiểm thử cho queue đầy và rejection handler, pool tăng từ core lên max khi queue đầy, số task completed sau khi giải phóng latch, và hành vi shutdown khi còn task đang chờ.

## 11. Vận hành và xử lý sự cố

Khi queue tăng hoặc active threads giữ ở mức cao, kiểm tra theo thứ tự:

1. Xác nhận đúng executor/pool bằng tag và tên bean.
2. Xem active, queued, pool size, core và max cùng một khoảng thời gian.
3. Đối chiếu tốc độ completed với tốc độ submit nếu ứng dụng có metric submit riêng.
4. Kiểm tra task execution time và queue wait time để xác định worker chậm hay workload tăng đột biến.
5. Kiểm tra downstream như database connection pool, HTTP client connection pool hoặc dịch vụ bên ngoài; worker có thể đang chờ tài nguyên khác.
6. Kiểm tra rejected counter và log RejectedExecutionException.
7. Đánh giá queue capacity, core/max size và rejection policy.
8. Kiểm tra shutdown, task bị block lâu hoặc tác vụ không kết thúc.

Tăng maximumPoolSize không phải lúc nào cũng giải quyết được backlog. Nếu worker chủ yếu chờ database nhưng database connection pool chỉ có 10 kết nối, tăng executor lên 100 thread có thể làm tăng contention mà throughput không cải thiện. Tương tự, queue lớn hơn có thể chỉ làm tác vụ chờ lâu hơn và tiêu thụ thêm bộ nhớ.

Cần tìm nút thắt thực tế trước khi đổi cấu hình. Metrics executor cho biết nơi tác vụ đang chờ và số worker đang bận; Timer, database metrics, HTTP client metrics và trace giúp tìm nguyên nhân khiến mỗi tác vụ mất nhiều thời gian.

## 12. Checklist triển khai

Trước khi đưa executor metrics vào production, xác nhận:

- Executor được bind đúng một lần vào MeterRegistry.
- Mỗi pool có tag định danh ổn định và cardinality thấp.
- Đã kiểm tra metric active, queued, completed, pool size, core/max và queue remaining nếu có.
- Queue có capacity phù hợp và đã hiểu rejection policy.
- Đã kiểm tra executor có tự động được Spring Boot instrument để tránh bind trùng.
- Dashboard xem active và queued cùng với throughput và latency.
- Cảnh báo có thời gian duy trì để tránh báo động do spike ngắn.
- Có metric bổ sung cho queue wait, execution time và rejected tasks khi cần.
- Đã kiểm thử trạng thái active/queued, queue đầy và shutdown.
- Đã đối chiếu tên meter thực tế ở endpoint export và backend.

Executor metrics giúp nhìn thấy áp lực xử lý tác vụ trước khi backlog biến thành lỗi người dùng. Khi theo dõi đồng thời số luồng hoạt động, tác vụ đang chờ, throughput và thời gian thực thi, người vận hành có thể phân biệt pool đang bận bình thường với tình trạng quá tải. Kết hợp queue có giới hạn, rejection policy rõ ràng và cảnh báo theo xu hướng sẽ giúp executor giữ được khả năng phản hồi khi tải tăng.
