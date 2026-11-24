# Dọn meter khi tài nguyên động được tạo hoặc giải phóng

## Mục tiêu

Một ứng dụng có thể tạo và giải phóng tài nguyên trong lúc chạy: worker pool, connection pool, consumer, session, tenant runtime hoặc một client kết nối đến dịch vụ bên ngoài. Mỗi tài nguyên có thể cần một nhóm metrics để theo dõi số tác vụ đang hoạt động, số lần xử lý, thời gian xử lý hoặc trạng thái kết nối.

Khi tài nguyên được tạo, ứng dụng đăng ký các meter tương ứng vào MeterRegistry. Khi tài nguyên bị giải phóng, nhóm meter chỉ còn mô tả một đối tượng không còn tồn tại. Nếu không dọn chúng, registry tiếp tục giữ các meter cũ, số lượng meter tăng theo số tài nguyên từng được tạo và dữ liệu export chứa những series không còn hữu ích.

Micrometer cung cấp MeterRegistry.remove(...) để gỡ một meter đã đăng ký. Tuy nhiên, ứng dụng phải quản lý vòng đời meter một cách có chủ đích:

- Ghi nhớ chính các meter đã đăng ký cho tài nguyên.
- Dừng nhận công việc và chờ các thao tác đang chạy kết thúc.
- Gỡ các meter do tài nguyên sở hữu khi tài nguyên đóng.
- Bảo đảm thao tác đóng có thể gọi lặp lại an toàn.
- Không xóa meter dùng chung với tài nguyên khác.

Sau bài này, bạn có thể phân biệt MeterBinder với đăng ký meter theo vòng đời tài nguyên, xây dựng đối tượng quản lý meter có thể đóng, dùng MeterRegistry.remove đúng cách, xử lý gauge và tag động, và kiểm thử việc dọn meter.

## Vòng đời của meter gắn với tài nguyên

Một tài nguyên động thường có ba giai đoạn:

1. **Create:** tài nguyên được khởi tạo; instrumentation đăng ký gauge, counter, timer hoặc meter liên quan.
2. **Use:** tài nguyên hoạt động; mã nghiệp vụ cập nhật các meter đã đăng ký.
3. **Close:** tài nguyên ngừng nhận công việc; các thao tác đang chạy được hoàn tất hoặc hủy theo chính sách; sau đó meter được gỡ khỏi registry.

Sơ đồ vòng đời:

~~~text
Tạo tài nguyên
      |
      v
Đăng ký meter vào MeterRegistry
      |
      v
Tài nguyên hoạt động và ghi nhận metrics
      |
      v
Ngừng nhận công việc mới
      |
      v
Chờ hoặc hủy công việc đang chạy
      |
      v
Gỡ meter do tài nguyên sở hữu
      |
      v
Giải phóng tài nguyên
~~~

Việc gỡ meter là một phần của vòng đời instrumentation. Nó không tự đóng connection pool, dừng executor hoặc giải phóng tài nguyên nghiệp vụ. Hai việc cần được điều phối bởi cùng một thành phần quản lý vòng đời.

## MeterBinder phù hợp với tài nguyên ổn định

MeterBinder là một interface có phương thức bindTo(MeterRegistry). Một binder đăng ký một hoặc nhiều meter để mô tả trạng thái của một thành phần ứng dụng hoặc container.

Ví dụ, một queue dùng chung trong toàn bộ vòng đời ứng dụng có thể được instrument bằng bean MeterBinder:

~~~java
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.binder.MeterBinder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.util.Queue;

@Configuration
public class QueueMetricsConfiguration {
    @Bean
    MeterBinder queueSize(Queue<?> queue) {
        return registry -> Gauge.builder(
                "worker.queue.size",
                queue,
                Queue::size
        ).register(registry);
    }
}
~~~

Spring Boot tự động bind các bean MeterBinder vào MeterRegistry do Spring quản lý. Cách này phù hợp khi dependency của metric là một bean ổn định, có vòng đời gắn với application context.

MeterBinder chỉ cung cấp hook bindTo. Interface này không định nghĩa unbind hoặc close. Vì vậy, một bean binder tồn tại suốt vòng đời ứng dụng rất thuận tiện cho metrics cấp ứng dụng; còn một tài nguyên được tạo và hủy liên tục cần một đối tượng quản lý riêng để ghi nhớ và gỡ meter.

Một số binder cụ thể của Micrometer cũng triển khai AutoCloseable để giải phóng listener hoặc tài nguyên phụ mà chính binder đã tạo. Điều đó phụ thuộc implementation; không nên giả định gọi close() trên mọi MeterBinder sẽ tự gỡ các meter khỏi registry. Hãy kiểm tra contract của binder cụ thể và quản lý meter handle nếu cần loại bỏ chúng.

## Đăng ký meter theo từng tài nguyên động

Giả sử ứng dụng tạo nhiều worker pool trong thời gian chạy. Mỗi pool cần ba metrics:

- Gauge số worker đang hoạt động.
- Counter số tác vụ đã hoàn tất.
- Timer thời gian xử lý tác vụ.

Có thể tạo một đối tượng WorkerPoolMetrics cho mỗi pool. Đối tượng này sở hữu các meter handle mà nó đăng ký:

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.Meter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

import java.time.Duration;
import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;

public final class WorkerPoolMetrics implements AutoCloseable {
    private final MeterRegistry registry;
    private final WorkerPool pool;
    private final List<Meter> ownedMeters;
    private final Counter completedTasks;
    private final Timer taskDuration;
    private final AtomicBoolean closed = new AtomicBoolean();

    public WorkerPoolMetrics(
            MeterRegistry registry,
            WorkerPool pool,
            String poolName) {
        this.registry = registry;
        this.pool = pool;

        Gauge activeWorkers = Gauge.builder(
                "worker.pool.active",
                pool,
                WorkerPool::activeWorkers
        )
                .description("Số worker đang hoạt động")
                .tag("pool", poolName)
                .register(registry);

        this.completedTasks = Counter.builder("worker.pool.tasks.completed")
                .description("Số tác vụ hoàn tất trong worker pool")
                .tag("pool", poolName)
                .register(registry);

        this.taskDuration = Timer.builder("worker.pool.task.duration")
                .description("Thời gian xử lý tác vụ trong worker pool")
                .tag("pool", poolName)
                .register(registry);

        this.ownedMeters = List.of(activeWorkers, completedTasks, taskDuration);
    }

    public synchronized void recordCompletedTask(Duration elapsed) {
        if (closed.get()) {
            throw new IllegalStateException("Metrics have already been closed");
        }

        completedTasks.increment();
        taskDuration.record(elapsed);
    }

    @Override
    public synchronized void close() {
        if (!closed.compareAndSet(false, true)) {
            return;
        }

        for (Meter meter : ownedMeters) {
            registry.remove(meter);
        }
    }
}
~~~

Interface WorkerPool trong ví dụ chỉ cần cung cấp số worker hiện tại:

~~~java
public interface WorkerPool extends AutoCloseable {
    double activeWorkers();

    @Override
    void close() throws Exception;
}
~~~

Đối tượng WorkerPoolMetrics giữ tham chiếu đến pool trong suốt vòng đời metrics. Điều này quan trọng với Gauge vì Micrometer thường giữ tham chiếu yếu đến state object được quan sát. Nếu không còn tham chiếu mạnh, đối tượng có thể bị garbage collector thu hồi và gauge không còn đọc được trạng thái hữu ích.

Danh sách ownedMeters lưu chính các đối tượng meter trả về từ builder. Khi đóng, registry.remove(meter) gỡ đúng các meter đã đăng ký cho pool này. Cách làm này cũng tránh phải tự dựng lại Meter.Id sau khi registry đã áp dụng MeterFilter.

Các phương thức ghi nhận và đóng trong ví dụ được đồng bộ hóa để minh họa việc tránh ghi metrics đồng thời với lúc gỡ meter. Với hệ thống tải cao, có thể điều phối việc dừng nhận tác vụ và chờ worker hoàn tất ở lớp quản lý pool, sau đó gọi close() khi không còn cập nhật mới.

## Gắn cleanup với vòng đời tài nguyên

Lớp quản lý tài nguyên nên đóng tài nguyên trước, sau đó dọn metrics trong finally để meter luôn được gỡ kể cả khi thao tác đóng tài nguyên gặp lỗi:

~~~java
public final class ManagedWorkerPool implements AutoCloseable {
    private final WorkerPool pool;
    private final WorkerPoolMetrics metrics;

    public ManagedWorkerPool(
            WorkerPool pool,
            WorkerPoolMetrics metrics) {
        this.pool = pool;
        this.metrics = metrics;
    }

    @Override
    public void close() throws Exception {
        try {
            pool.close();
        } finally {
            metrics.close();
        }
    }
}
~~~

Trong ví dụ thực tế, WorkerPool có thể là executor hoặc một abstraction khác có phương thức shutdown/close. Quy trình đóng nên:

1. Ngừng nhận công việc mới.
2. Chờ công việc đang chạy hoàn tất trong thời hạn cho phép.
3. Hủy công việc còn lại nếu chính sách shutdown yêu cầu.
4. Gỡ meter.
5. Hoàn tất giải phóng tài nguyên.

Nếu pool có API shutdown và awaitTermination riêng, hãy thực hiện hai bước đó trước metrics.close(). Không gỡ meter khi tài nguyên vẫn tiếp tục xử lý công việc, vì những thao tác sau đó sẽ không còn được export.

## MeterRegistry.remove có những lựa chọn nào?

MeterRegistry cung cấp một số phương thức xóa meter:

| Phương thức | Cách xác định meter | Khi nên dùng |
|---|---|---|
| remove(Meter) | Dùng meter handle đã nhận khi đăng ký | Lựa chọn thuận tiện nhất khi tài nguyên giữ các handle |
| remove(Meter.Id) | Dùng Meter.Id đã được mapping | Khi có ID sau khi áp dụng MeterFilter |
| removeByPreFilterId(Meter.Id) | Dùng ID trước khi áp dụng MeterFilter | Khi chỉ còn ID ban đầu trước bước mapping |
| clear() | Xóa toàn bộ meter trong registry | Chỉ dùng khi thật sự muốn làm sạch toàn registry |

Ưu tiên lưu Meter handle ngay khi đăng ký và gọi remove(handle) khi tài nguyên đóng. Tài liệu API ghi rõ remove(Meter) mong đợi meter có cùng Meter.Id với meter đã được trả về khi đăng ký; ID đó đã bao gồm các MeterFilter được áp dụng.

Nếu chỉ lưu ID, cần phân biệt ID trước và sau filter:

- remove(mappedId) dùng ID như hiện tại và không chạy MeterFilter trên ID đó.
- removeByPreFilterId(preFilterId) áp dụng các MeterFilter của registry lên ID đầu vào trước khi tìm meter.

Các phương thức remove được đánh dấu Incubating trong một số phiên bản Micrometer. Hãy kiểm tra Javadoc của phiên bản mà BOM dự án đang quản lý trước khi phụ thuộc vào API này trong thư viện dùng chung.

Không gọi registry.clear() để đóng một tài nguyên đơn lẻ. Registry thường chứa metrics JVM, HTTP, database và các thành phần khác. clear() sẽ xóa cả meter không thuộc tài nguyên đang giải phóng.

## Quản lý ownership và tránh xóa nhầm meter

Meter được định danh bằng tên và tập tag. Nếu hai tài nguyên đăng ký cùng tên và cùng tag vào một registry, chúng nhận cùng một meter đã tồn tại; registry không tạo meter độc lập cho từng đối tượng chỉ vì hai lần gọi đăng ký khác nhau.

Ví dụ, hai pool cùng đăng ký:

~~~java
registry.counter(
        "worker.pool.tasks.completed",
        "pool", "shared"
);
~~~

Hai pool này có thể cùng cập nhật một counter. Nếu một pool đóng và gọi remove(counter), meter dùng chung sẽ bị gỡ dù pool còn lại vẫn hoạt động.

Hãy chọn một trong các cách quản lý sau:

- Mỗi tài nguyên sở hữu một bộ tên/tag riêng và chỉ chủ sở hữu đó được gỡ meter.
- Nếu nhiều tài nguyên cố ý chia sẻ cùng một meter, tạo một component sở hữu chung và chỉ gỡ khi tài nguyên cuối cùng ngừng sử dụng.
- Nếu chỉ cần số liệu tổng hợp, đăng ký một meter ở cấp manager thay vì một meter cho từng tài nguyên.

Không dùng request ID, session ID, UUID ngẫu nhiên hoặc dữ liệu người dùng làm tag chỉ để phân biệt mọi lần tạo tài nguyên. Số lượng meter có thể tăng theo vòng đời hệ thống. Hãy ưu tiên nhóm hữu hạn như loại worker, vai trò pool, shard cố định hoặc loại kết nối.

## Cleanup không xóa lịch sử ở backend

Gọi registry.remove(meter) làm meter không còn thuộc tập meter mà registry tiếp tục thu thập và export. Nó không gửi lệnh xóa lịch sử tới Prometheus, Datadog hoặc hệ thống lưu trữ bên ngoài.

Backend có thể tiếp tục giữ các mẫu đã nhận cho đến khi dữ liệu hết hạn theo retention policy hoặc cơ chế staleness của backend. Vì vậy, cleanup có hai mục đích khác nhau:

- **Trong ứng dụng:** giảm số meter đang đăng ký, ngừng export dữ liệu của tài nguyên đã đóng và tránh giữ tham chiếu không cần thiết.
- **Trong backend:** dữ liệu lịch sử được quản lý theo chính sách lưu trữ và truy vấn của hệ thống giám sát.

Nếu tài nguyên được tạo và hủy liên tục với một tag ID duy nhất, việc remove giúp registry không giữ vô hạn các meter đang hoạt động, nhưng backend vẫn có thể lưu rất nhiều series lịch sử. Hãy giảm churn cardinality ngay từ thiết kế tag.

## Kiểm thử việc đăng ký và dọn meter

SimpleMeterRegistry phù hợp cho unit test vì lưu meter trong bộ nhớ và không cần backend:

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Meter;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class DynamicMeterLifecycleTest {
    @Test
    void removesMetersWhenResourceCloses() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        try {
            Counter counter = registry.counter(
                    "worker.pool.tasks.completed",
                    "pool", "batch"
            );

            counter.increment();
            assertThat(registry.find("worker.pool.tasks.completed")
                    .tag("pool", "batch")
                    .counter()).isNotNull();

            Meter removed = registry.remove(counter);

            assertThat(removed).isNotNull();
            assertThat(registry.find("worker.pool.tasks.completed")
                    .tag("pool", "batch")
                    .counter()).isNull();
        } finally {
            registry.close();
        }
    }
}
~~~

Với lớp quản lý metrics của tài nguyên, hãy kiểm thử thêm:

- Constructor đăng ký đủ các meter mong đợi.
- recordCompletedTask() làm count và timer tăng khi tài nguyên còn mở.
- close() gỡ toàn bộ meter đã đăng ký.
- Gọi close() nhiều lần không gây lỗi.
- Không thể ghi thêm metrics sau khi đã đóng.
- Meter của tài nguyên khác vẫn còn trong registry.
- Hai tài nguyên có identity khác nhau không vô tình dùng chung meter.

Nếu dùng MeterFilter để đổi tên hoặc thêm tag, hãy kiểm thử việc remove bằng chính meter handle đã trả về. Điều này xác nhận ID sau mapping được dùng đúng khi gỡ meter.

## Những lỗi thường gặp

**Chỉ đóng tài nguyên mà không gỡ meter.** Pool đã dừng nhưng meter vẫn còn trong registry. Hãy gắn cleanup với close/dispose của resource owner.

**Dựa vào garbage collection để dọn meter.** Gauge có thể giữ weak reference đến state object, nhưng meter registration vẫn có thể tồn tại trong registry. Hãy remove meter rõ ràng.

**Tạo meter mới cho mọi lần request.** Đăng ký meter theo ID hoặc URL động làm cardinality tăng không giới hạn. Meter nên được tạo theo tài nguyên hoặc nhóm có vòng đời và identity rõ ràng.

**Gọi clear() khi một pool đóng.** clear() ảnh hưởng đến tất cả meter trong registry. Chỉ remove những meter do pool sở hữu.

**Xóa meter dùng chung.** Hai resource cùng tên/tag có thể nhận cùng meter. Cần ownership rõ ràng hoặc reference counting trước khi remove.

**Gỡ meter trước khi dừng cập nhật.** Tác vụ còn chạy có thể tiếp tục ghi vào handle đã bị remove và dữ liệu không còn được export. Hãy dừng hoặc drain công việc trước.

**Cho rằng remove xóa lịch sử backend.** remove chỉ thay đổi registry cục bộ; dữ liệu đã export vẫn tuân theo retention của backend.

## Checklist khi quản lý meter theo vòng đời tài nguyên

1. Xác định rõ component nào sở hữu tài nguyên và các meter của nó.
2. Chọn MeterBinder cho thành phần ổn định theo application context.
3. Với tài nguyên động, tạo một đối tượng quản lý metrics theo từng resource hoặc nhóm resource.
4. Lưu Meter handle trả về từ builder/registry.
5. Dùng tag hữu hạn, có ý nghĩa và không tạo cardinality không kiểm soát.
6. Dừng nhận công việc mới và chờ công việc đang chạy trước khi remove.
7. Gỡ đúng các meter đã đăng ký bằng registry.remove(meter).
8. Làm cho close() idempotent và tránh race với thao tác ghi metrics.
9. Không xóa meter thuộc resource khác hoặc meter dùng chung còn owner.
10. Kiểm thử registry sau create, use và close.
11. Xác nhận backend ngừng nhận mẫu mới; quản lý dữ liệu lịch sử bằng retention policy riêng.

## Kết luận

MeterBinder phù hợp để đăng ký metrics cho thành phần ổn định trong ứng dụng, đặc biệt khi Spring Boot tự bind bean vào registry. Tài nguyên động cần một chủ sở hữu vòng đời rõ ràng: đăng ký meter khi tạo, lưu các meter handle và gỡ chúng khi tài nguyên đóng. Dùng MeterRegistry.remove(meter) cho đúng meter đã đăng ký, dừng cập nhật trước khi remove và không xóa meter dùng chung. Cleanup giữ registry gọn và ngừng export số liệu của tài nguyên đã giải phóng; lịch sử đã gửi tới backend vẫn được quản lý theo retention của backend đó.

## Tài liệu tham khảo

- [Spring Boot - Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): cách Spring Boot tự động bind các bean MeterBinder vào MeterRegistry.
- [Micrometer - MeterBinder API](https://javadoc.io/doc/io.micrometer/micrometer-core/latest/io/micrometer/core/instrument/binder/MeterBinder.html): contract bindTo(MeterRegistry).
- [Micrometer - MeterRegistry API](https://javadoc.io/doc/io.micrometer/micrometer-core/latest/io/micrometer/core/instrument/MeterRegistry.html): remove(Meter), remove(Meter.Id), removeByPreFilterId và clear().
