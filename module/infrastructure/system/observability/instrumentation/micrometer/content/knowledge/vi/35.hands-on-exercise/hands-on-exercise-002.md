# Đóng gói phép đo hàng đợi bằng MeterBinder có vòng đời rõ ràng

Trong một ứng dụng xử lý nền, hàng đợi (queue) là nơi nhận các tác vụ trước khi worker thực thi. Khi queue tăng nhanh, hệ thống cần biết số tác vụ đang chờ, số tác vụ đã được nhận, số tác vụ bị từ chối và kết quả xử lý. Những số liệu này giúp phát hiện worker thiếu năng lực, queue đầy hoặc tác vụ thất bại.

Bài thực hành này xây dựng một queue có giới hạn và đóng gói telemetry của nó trong `MeterBinder`. Binder đăng ký Gauge để đọc độ sâu queue và FunctionCounter để đọc các bộ đếm tích lũy. State được giữ trong cùng bean với queue, có vòng đời rõ ràng và được nhiều registry đọc mà không tạo meter trùng trong cùng registry.

Bài học thuộc chương Thực hành tổng hợp của module Micrometer, tập trung vào Counter, Gauge, Timer, DistributionSummary, tag có kiểm soát, tích hợp Spring Boot và xuất metrics đến hệ thống giám sát. Trọng tâm ở đây là thiết kế một MeterBinder có thể tái sử dụng, an toàn khi ứng dụng chạy và dễ kiểm thử.

## Kết quả cần đạt

Sau bài thực hành, bạn sẽ có một component `InstrumentedTaskQueue`:

- Giữ queue có giới hạn và các state counter trong cùng một đối tượng.
- Cài đặt `MeterBinder` và đăng ký meter trong `bindTo(MeterRegistry)`.
- Export Gauge `worker.queue.depth` và `worker.queue.capacity`.
- Export FunctionCounter cho số task accepted, rejected, dequeued, completed và failed.
- Dùng tag `queue` có tập giá trị ổn định, không chứa task ID hoặc request ID.
- Có thể được Spring Boot tự động bind vào registry được quản lý.
- Có thể bind tường minh khi dùng Micrometer độc lập.
- Không giữ Timer hoặc Counter handle thuộc một registry duy nhất trong field dùng chung.
- Có test cho queue behavior, meter values và binding lặp lại.

## Kịch bản thực hành

Một service có queue `orders` với capacity là 3. Producer gửi task vào queue; worker lấy task và thực thi. Khi queue đã đầy, task mới bị từ chối. Mỗi lần xử lý xong, hệ thống tăng completed hoặc failed.

~~~mermaid
flowchart LR
    P[Producer] --> Q[Queue orders, capacity 3]
    Q -->|poll| W[Worker]
    W -->|success| C[completed]
    W -->|exception| F[failed]
    Q -->|full| R[rejected]
    Q --> M[MeterBinder]
    M --> G[Gauge and FunctionCounter]
~~~

| Hành động | Kết quả nghiệp vụ | Metric thay đổi |
|---|---|---|
| Submit task A | Queue nhận task | depth +1, accepted +1 |
| Submit task B và C | Queue nhận thêm hai task | depth +2, accepted +2 |
| Submit task D | Queue đã đầy, task bị từ chối | rejected +1, depth giữ nguyên |
| Worker lấy task A | Task rời queue | depth -1, dequeued +1 |
| Task A chạy thành công | Xử lý hoàn tất | completed +1 |
| Task B ném exception | Xử lý thất bại | failed +1 |

Các metric là dữ liệu vận hành. Không đưa nội dung task, mã đơn hàng, user ID hoặc request ID vào tên meter hay tag. Tag `queue=orders` là giá trị ổn định; nếu có nhiều queue, chỉ dùng các tên queue được cấu hình trước.

## Thiết kế metric

| Metric | Loại meter | Ý nghĩa |
|---|---|---|
| `worker.queue.depth` | Gauge | Số task hiện đang chờ |
| `worker.queue.capacity` | Gauge | Sức chứa tối đa của queue |
| `worker.queue.tasks.accepted` | FunctionCounter | Tổng task được queue nhận |
| `worker.queue.tasks.rejected` | FunctionCounter | Tổng task bị từ chối |
| `worker.queue.tasks.dequeued` | FunctionCounter | Tổng task đã được worker lấy khỏi queue |
| `worker.queue.tasks.completed` | FunctionCounter | Tổng task xử lý thành công |
| `worker.queue.tasks.failed` | FunctionCounter | Tổng task xử lý thất bại |

Gauge phản ánh trạng thái hiện tại. FunctionCounter đọc các biến tích lũy chỉ tăng; registry lấy giá trị khi thu thập metrics. Do đó, state phải tồn tại lâu hơn meter và không được reset tùy tiện khi scrape.

`FunctionCounter` phù hợp khi component đã sở hữu một bộ đếm tích lũy và muốn Micrometer đọc giá trị đó. Nếu muốn chủ động gọi `increment()` trực tiếp trên meter, có thể dùng `Counter`; tuy nhiên, khi `MeterBinder` được bind vào nhiều registry, giữ một Counter handle duy nhất trong field sẽ không đại diện cho tất cả registry. Bài này dùng FunctionCounter để mỗi registry đăng ký meter đọc cùng một state.

## Bước 1: Tạo queue có giới hạn và state đo lường

Tạo class `InstrumentedTaskQueue`. Queue sử dụng `ArrayBlockingQueue` để có capacity cố định. Bộ đếm depth được cập nhật khi submit và poll; các counter tích lũy dùng `AtomicLong`.

~~~java
import java.util.Objects;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

public final class InstrumentedTaskQueue {

    private final ArrayBlockingQueue<Runnable> queue;
    private final int capacity;

    private final AtomicInteger depth = new AtomicInteger();
    private final AtomicLong accepted = new AtomicLong();
    private final AtomicLong rejected = new AtomicLong();
    private final AtomicLong dequeued = new AtomicLong();
    private final AtomicLong completed = new AtomicLong();
    private final AtomicLong failed = new AtomicLong();

    public InstrumentedTaskQueue(int capacity) {
        if (capacity <= 0) {
            throw new IllegalArgumentException("capacity must be positive");
        }

        this.capacity = capacity;
        this.queue = new ArrayBlockingQueue<>(capacity);
    }

    public boolean submit(Runnable task) {
        Objects.requireNonNull(task, "task");

        // Tăng trước offer để consumer không thể giảm depth trước khi
        // producer tăng nó. Nếu queue đầy thì rollback ngay.
        depth.incrementAndGet();

        if (!queue.offer(task)) {
            depth.decrementAndGet();
            rejected.incrementAndGet();
            return false;
        }

        accepted.incrementAndGet();
        return true;
    }

    public Runnable poll() {
        Runnable task = queue.poll();

        if (task != null) {
            depth.decrementAndGet();
            dequeued.incrementAndGet();
        }

        return task;
    }

    public void recordCompleted() {
        completed.incrementAndGet();
    }

    public void recordFailed() {
        failed.incrementAndGet();
    }

    public boolean runNext() {
        Runnable task = poll();

        if (task == null) {
            return false;
        }

        try {
            task.run();
            recordCompleted();
        }
        catch (RuntimeException exception) {
            recordFailed();
            throw exception;
        }

        return true;
    }

    public int depth() {
        return depth.get();
    }

    public int capacity() {
        return capacity;
    }

    public long accepted() {
        return accepted.get();
    }

    public long rejected() {
        return rejected.get();
    }

    public long dequeued() {
        return dequeued.get();
    }

    public long completed() {
        return completed.get();
    }

    public long failed() {
        return failed.get();
    }
}
~~~

### Vì sao cập nhật depth trước offer?

Producer phải tăng `depth` trước khi task trở nên khả dụng trong queue. Nếu tăng sau `offer`, một consumer khác có thể lấy task và giảm depth trước khi producer tăng, tạo ra giá trị âm tạm thời.

Với cách tăng trước rồi rollback nếu queue từ chối, sample có thể thấy depth tăng rất ngắn trước khi `offer` hoàn tất. Đây là một sai số thời điểm nhỏ của Gauge trong hệ thống concurrent; giá trị sẽ ổn định sau khi thao tác kết thúc. Nếu nghiệp vụ đòi hỏi snapshot tuyệt đối nhất quán, cần đồng bộ hóa cả thao tác queue và counter, đồng thời đo chi phí lock.

`ArrayBlockingQueue` có giới hạn và `offer` trả về `false` khi đầy. Không tăng `accepted` nếu task bị từ chối. Không tăng `dequeued` nếu `poll` trả về `null`.

`runNext()` chỉ là cách mô phỏng worker để bài thực hành tự chứa. Trong hệ thống thực, executor có thể lấy task bằng worker loop riêng; khi đó hãy tăng `completed` hoặc `failed` tại nơi thực thi kết thúc.

## Bước 2: Cài đặt MeterBinder

`MeterBinder` định nghĩa phương thức `bindTo(MeterRegistry)`. Mỗi registry nhận một lần bind và tự quản lý meter của nó. Binder chỉ cần đăng ký meter từ state của queue; không nên lưu một Gauge hoặc FunctionCounter handle duy nhất rồi dùng chung cho nhiều registry.

~~~java
import io.micrometer.core.instrument.FunctionCounter;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.binder.MeterBinder;

import java.util.Objects;

public final class InstrumentedTaskQueueMetrics implements MeterBinder {

    private final String queueName;
    private final InstrumentedTaskQueue queue;

    public InstrumentedTaskQueueMetrics(
        String queueName,
        InstrumentedTaskQueue queue
    ) {
        this.queueName = Objects.requireNonNull(queueName, "queueName");
        this.queue = Objects.requireNonNull(queue, "queue");
    }

    @Override
    public void bindTo(MeterRegistry registry) {
        Gauge.builder(
                "worker.queue.depth",
                queue,
                InstrumentedTaskQueue::depth
            )
            .description("Số task hiện đang chờ trong queue")
            .baseUnit("tasks")
            .tag("queue", queueName)
            .register(registry);

        Gauge.builder(
                "worker.queue.capacity",
                queue,
                InstrumentedTaskQueue::capacity
            )
            .description("Sức chứa tối đa của queue")
            .baseUnit("tasks")
            .tag("queue", queueName)
            .register(registry);

        FunctionCounter.builder(
                "worker.queue.tasks.accepted",
                queue,
                q -> q.accepted()
            )
            .description("Tổng task được queue nhận")
            .baseUnit("tasks")
            .tag("queue", queueName)
            .register(registry);

        FunctionCounter.builder(
                "worker.queue.tasks.rejected",
                queue,
                q -> q.rejected()
            )
            .description("Tổng task bị queue từ chối")
            .baseUnit("tasks")
            .tag("queue", queueName)
            .register(registry);

        FunctionCounter.builder(
                "worker.queue.tasks.dequeued",
                queue,
                q -> q.dequeued()
            )
            .description("Tổng task đã được lấy khỏi queue")
            .baseUnit("tasks")
            .tag("queue", queueName)
            .register(registry);

        FunctionCounter.builder(
                "worker.queue.tasks.completed",
                queue,
                q -> q.completed()
            )
            .description("Tổng task xử lý thành công")
            .baseUnit("tasks")
            .tag("queue", queueName)
            .register(registry);

        FunctionCounter.builder(
                "worker.queue.tasks.failed",
                queue,
                q -> q.failed()
            )
            .description("Tổng task xử lý thất bại")
            .baseUnit("tasks")
            .tag("queue", queueName)
            .register(registry);
    }
}
~~~

Các meter có cùng tag `queue` để truy vấn theo từng queue. `queueName` phải là tên cấu hình ổn định, chẳng hạn `orders`, `emails` hoặc `notifications`. Không dùng tên task hoặc ID được tạo theo từng lần gọi làm tag value vì sẽ tạo cardinality cao.

### Vì sao binder không giữ meter handle?

Spring Boot có thể bind một `MeterBinder` vào nhiều registry. Mỗi registry cần tạo meter theo naming convention và cấu hình riêng. Nếu binder lưu một `Gauge` hoặc `FunctionCounter` handle trong field, field đó chỉ đại diện cho một registry và dễ bị ghi đè khi bind lần tiếp theo.

Ở đây binder chỉ giữ queue state và tên queue. Mỗi lần `bindTo` nhận registry, nó đăng ký meter vào registry đó. Cùng một Meter ID đăng ký lại trong cùng registry sẽ được registry quản lý như meter đã tồn tại, thay vì tạo một series mới khác biệt.

Gauge của Micrometer thường giữ weak reference tới object được đo. Binder giữ strong reference tới queue qua field `queue`, và bean Spring giữ binder sống trong thời gian ứng dụng chạy. Vì vậy queue state không bị garbage collector thu hồi trong khi meter còn được sử dụng.

## Bước 3: Đăng ký binder trong Spring Boot

Tạo bean cho queue và binder:

~~~java
import io.micrometer.core.instrument.binder.MeterBinder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class QueueMetricsConfiguration {

    @Bean
    InstrumentedTaskQueue ordersQueue() {
        return new InstrumentedTaskQueue(3);
    }

    @Bean
    MeterBinder ordersQueueMetrics(InstrumentedTaskQueue ordersQueue) {
        return new InstrumentedTaskQueueMetrics("orders", ordersQueue);
    }
}
~~~

Spring Boot tự động phát hiện các bean kiểu `MeterBinder` và bind chúng vào registry được quản lý. Khi ứng dụng có Prometheus registry, các meter của queue có thể xuất hiện trên `/actuator/prometheus`. Khi ứng dụng có thêm một registry khác, binder cũng có thể được gọi cho registry đó.

Không gọi `bindTo` thủ công cho bean đã được Spring Boot tự động bind. Nếu vừa auto-bind vừa bind thủ công, registry vẫn quản lý Meter ID trùng trong cùng registry, nhưng cấu hình trở nên khó hiểu và test có thể vô tình kiểm tra sai registry.

### Khi dùng Micrometer độc lập

Trong ứng dụng không có Spring Boot, tạo registry và bind rõ ràng:

~~~java
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

InstrumentedTaskQueue queue = new InstrumentedTaskQueue(3);
InstrumentedTaskQueueMetrics binder =
    new InstrumentedTaskQueueMetrics("orders", queue);

SimpleMeterRegistry registry = new SimpleMeterRegistry();
binder.bindTo(registry);
~~~

Ở cách này, vòng đời registry do ứng dụng quản lý. Khi kết thúc ứng dụng hoặc test, đóng registry nếu implementation hỗ trợ `close()`.

## Bước 4: Chạy kịch bản và quan sát metrics

Dùng queue capacity 3:

~~~java
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

InstrumentedTaskQueue queue = new InstrumentedTaskQueue(3);
SimpleMeterRegistry registry = new SimpleMeterRegistry();
new InstrumentedTaskQueueMetrics("orders", queue).bindTo(registry);

queue.submit(() -> System.out.println("task A"));
queue.submit(() -> System.out.println("task B"));
queue.submit(() -> System.out.println("task C"));

boolean accepted = queue.submit(() -> System.out.println("task D"));
// accepted == false vì queue đã đầy.

queue.runNext(); // A hoàn tất.
queue.runNext(); // B hoàn tất.

double currentDepth = registry.get("worker.queue.depth")
    .tag("queue", "orders")
    .gauge()
    .value();
// currentDepth == 1.0

registry.close();
~~~

Sau hai task hoàn tất, trạng thái dự kiến:

| Metric | Giá trị |
|---|---:|
| `worker.queue.depth{queue="orders"}` | 1 |
| `worker.queue.capacity{queue="orders"}` | 3 |
| `worker.queue.tasks.accepted{queue="orders"}` | 3 |
| `worker.queue.tasks.rejected{queue="orders"}` | 1 |
| `worker.queue.tasks.dequeued{queue="orders"}` | 2 |
| `worker.queue.tasks.completed{queue="orders"}` | 2 |
| `worker.queue.tasks.failed{queue="orders"}` | 0 |

Các bộ đếm là tích lũy. Gauge depth có thể tăng hoặc giảm. Nếu queue được tạo mới khi ứng dụng restart, bộ đếm trong bộ nhớ bắt đầu lại từ 0; backend Prometheus xử lý counter reset khi dùng hàm `rate()`.

### Kiểm thử task thất bại

~~~java
InstrumentedTaskQueue failureQueue = new InstrumentedTaskQueue(1);
failureQueue.submit(() -> {
    throw new IllegalStateException("simulated failure");
});

try {
    failureQueue.runNext();
}
catch (IllegalStateException expected) {
    // Worker hoặc tầng gọi quyết định cách xử lý lỗi.
}
~~~

Sau khi task thất bại:

- `depth` giảm vì task đã được lấy khỏi queue.
- `dequeued` tăng.
- `failed` tăng.
- `completed` không tăng.

Điểm này quan trọng: một task rời queue không đồng nghĩa với task đã hoàn thành thành công.

## Bước 5: Kiểm thử binder và queue behavior

Dùng `SimpleMeterRegistry` để kiểm tra Meter ID, tag và giá trị đọc được. Test đầu tiên xác minh queue đầy và task được xử lý:

~~~java
import io.micrometer.core.instrument.FunctionCounter;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class InstrumentedTaskQueueMetricsTest {

    @Test
    void exposesQueueStateAndMonotonicCounters() {
        InstrumentedTaskQueue queue = new InstrumentedTaskQueue(2);
        InstrumentedTaskQueueMetrics binder =
            new InstrumentedTaskQueueMetrics("orders", queue);

        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        binder.bindTo(registry);

        assertTrue(queue.submit(() -> { }));
        assertTrue(queue.submit(() -> { }));
        assertFalse(queue.submit(() -> { }));

        Gauge depth = registry.get("worker.queue.depth")
            .tag("queue", "orders")
            .gauge();

        Gauge capacity = registry.get("worker.queue.capacity")
            .tag("queue", "orders")
            .gauge();

        FunctionCounter accepted = registry.get("worker.queue.tasks.accepted")
            .tag("queue", "orders")
            .functionCounter();

        FunctionCounter rejected = registry.get("worker.queue.tasks.rejected")
            .tag("queue", "orders")
            .functionCounter();

        assertEquals(2.0, depth.value());
        assertEquals(2.0, capacity.value());
        assertEquals(2.0, accepted.count());
        assertEquals(1.0, rejected.count());

        assertTrue(queue.runNext());

        assertEquals(1.0, depth.value());
        assertEquals(1.0, registry.get("worker.queue.tasks.dequeued")
            .tag("queue", "orders")
            .functionCounter()
            .count());
        assertEquals(1.0, registry.get("worker.queue.tasks.completed")
            .tag("queue", "orders")
            .functionCounter()
            .count());

        registry.close();
    }
}
~~~

Test thứ hai xác minh lỗi được đếm riêng:

~~~java
@Test
void countsFailedTaskWithoutCountingItAsCompleted() {
    InstrumentedTaskQueue queue = new InstrumentedTaskQueue(1);
    SimpleMeterRegistry registry = new SimpleMeterRegistry();

    new InstrumentedTaskQueueMetrics("orders", queue).bindTo(registry);

    queue.submit(() -> {
        throw new IllegalStateException("expected");
    });

    try {
        queue.runNext();
    }
    catch (IllegalStateException expected) {
        // Lỗi đã được ghi nhận ở queue; test tiếp tục kiểm tra metrics.
    }

    assertEquals(0.0, registry.get("worker.queue.depth")
        .tag("queue", "orders").gauge().value());

    assertEquals(1.0, registry.get("worker.queue.tasks.failed")
        .tag("queue", "orders").functionCounter().count());

    assertEquals(0.0, registry.get("worker.queue.tasks.completed")
        .tag("queue", "orders").functionCounter().count());

    registry.close();
}
~~~

Test không cần sleep vì FunctionCounter đọc trực tiếp AtomicLong. Mỗi lần gọi `count()` sẽ lấy giá trị state hiện tại.

## Bước 6: Kiểm tra bind lặp và nhiều registry

Một binder nên hoạt động đúng khi được bind vào từng registry. Test sau bind cùng binder vào hai `SimpleMeterRegistry` và xác minh cả hai nhìn thấy cùng state:

~~~java
@Test
void canBindSameStateToMultipleRegistries() {
    InstrumentedTaskQueue queue = new InstrumentedTaskQueue(5);
    InstrumentedTaskQueueMetrics binder =
        new InstrumentedTaskQueueMetrics("orders", queue);

    SimpleMeterRegistry firstRegistry = new SimpleMeterRegistry();
    SimpleMeterRegistry secondRegistry = new SimpleMeterRegistry();

    binder.bindTo(firstRegistry);
    binder.bindTo(secondRegistry);

    queue.submit(() -> { });

    assertEquals(1.0, firstRegistry.get("worker.queue.depth")
        .tag("queue", "orders").gauge().value());

    assertEquals(1.0, secondRegistry.get("worker.queue.depth")
        .tag("queue", "orders").gauge().value());

    firstRegistry.close();
    secondRegistry.close();
}
~~~

Có thể bind cùng binder hai lần vào một registry để xác minh registry không tạo meter có cùng ID thành hai meter độc lập:

~~~java
@Test
void repeatedBindingDoesNotCreateDuplicateMeterIds() {
    InstrumentedTaskQueue queue = new InstrumentedTaskQueue(5);
    InstrumentedTaskQueueMetrics binder =
        new InstrumentedTaskQueueMetrics("orders", queue);

    SimpleMeterRegistry registry = new SimpleMeterRegistry();

    binder.bindTo(registry);
    int meterCountAfterFirstBind = registry.getMeters().size();

    binder.bindTo(registry);

    assertEquals(meterCountAfterFirstBind, registry.getMeters().size());

    registry.close();
}
~~~

Test này kiểm tra hành vi registry với Meter ID trùng. Trong ứng dụng, vẫn nên để framework quản lý lifecycle bind và không gọi binder thủ công nhiều lần nếu Spring Boot đã tự động bind.

## Bước 7: Xác minh bằng Actuator và Prometheus

Nếu dùng Spring Boot và Prometheus registry, expose endpoint cần thiết:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
~~~

Tra cứu Gauge theo tên chuẩn tắc:

~~~bash
curl -s "http://localhost:8080/actuator/metrics/worker.queue.depth?tag=queue:orders"
~~~

Tra cứu counter bị từ chối:

~~~bash
curl -s "http://localhost:8080/actuator/metrics/worker.queue.tasks.rejected?tag=queue:orders"
~~~

Đọc exposition Prometheus:

~~~bash
curl -s "http://localhost:8080/actuator/prometheus"
~~~

Prometheus có thể chuẩn hóa dấu chấm thành dấu gạch dưới và thêm hậu tố theo loại meter/đơn vị. Vì vậy hãy tìm metric trong raw exposition thay vì giả định tên export giống tên builder. Actuator tra cứu theo tên chuẩn tắc của Meter ID.

Một số truy vấn PromQL sau khi xác nhận tên thực tế trong exposition:

~~~promql
worker_queue_depth{queue="orders"}
~~~

~~~promql
rate(worker_queue_tasks_rejected_total{queue="orders"}[5m])
~~~

~~~promql
rate(worker_queue_tasks_completed_total{queue="orders"}[5m])
~~~

Các tên PromQL trên là dạng minh họa theo Prometheus naming convention. Hãy đối chiếu endpoint export của ứng dụng trước khi đưa vào dashboard hoặc alert.

## Bước 8: Đánh giá thiết kế vòng đời

Một `MeterBinder` tốt cần có ownership rõ ràng:

| Đối tượng | Vòng đời | Ai sở hữu? |
|---|---|---|
| InstrumentedTaskQueue | Theo vòng đời service/bean | Spring container hoặc ứng dụng |
| InstrumentedTaskQueueMetrics | Theo vòng đời queue bean | Spring container hoặc ứng dụng |
| Queue state counters | Sống cùng queue | InstrumentedTaskQueue |
| Gauge/FunctionCounter trong registry | Sống theo registry | MeterRegistry |
| Registry | Theo ứng dụng hoặc test | Spring Boot hoặc code khởi tạo registry |

Những quy tắc cần giữ:

- Không tạo queue state mới mỗi lần `bindTo` được gọi; mọi registry phải đọc cùng state của queue.
- Không giữ một meter handle của registry A để ghi vào registry B.
- Giữ strong reference tới queue state vì Gauge có thể giữ weak reference.
- Không reset các AtomicLong khi registry scrape.
- Không đăng ký tag value thay đổi theo từng task.
- Đóng registry do test hoặc ứng dụng tự tạo khi kết thúc vòng đời.
- Để Spring Boot quản lý binder bean nếu đang dùng auto-configuration.

MeterBinder không có phương thức `close()`. Nó đăng ký meter; vòng đời meter gắn với registry. Nếu queue cần dừng worker hoặc giải phóng tài nguyên, hãy quản lý lifecycle đó trong component queue/service bằng `SmartLifecycle`, `DisposableBean` hoặc `@PreDestroy` tùy kiến trúc. Không coi việc registry đóng là tín hiệu tự động dừng queue.

## Mở rộng: thêm Timer cho thời gian thực thi task

Gauge và FunctionCounter cho biết độ sâu và số lượng, nhưng chưa trả lời task chạy mất bao lâu. Có thể thêm Timer ở worker service, nơi đã có `MeterRegistry`:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Component;

@Component
public class QueueTaskRunner {

    private final InstrumentedTaskQueue queue;
    private final Timer executionTimer;

    public QueueTaskRunner(
        InstrumentedTaskQueue queue,
        MeterRegistry registry
    ) {
        this.queue = queue;
        this.executionTimer = Timer.builder("worker.task.execution")
            .description("Thời lượng thực thi một task")
            .tag("queue", "orders")
            .register(registry);
    }

    public boolean runNext() {
        Runnable task = queue.poll();

        if (task == null) {
            return false;
        }

        try {
            executionTimer.record(task);
            queue.recordCompleted();
        }
        catch (RuntimeException exception) {
            queue.recordFailed();
            throw exception;
        }

        return true;
    }
}
~~~

Phần mở rộng này dùng Timer được đăng ký trên registry inject vào worker. Với Spring Boot, registry được inject thường là registry composite do framework quản lý. Nếu tự quản lý nhiều registry riêng biệt, hãy đăng ký Timer trên từng registry hoặc dùng Observation có các handler tương ứng; không lưu một Timer handle của registry này rồi giả định nó đại diện cho mọi registry khác.

`Timer.record(Runnable)` ghi thời gian cả khi Runnable ném exception, nhưng exception vẫn được truyền ra caller. Đây là hành vi phù hợp để đo latency của cả task thành công và thất bại.

## Các lỗi cần tránh

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Gauge trỏ tới object tạm | Object có thể bị GC và Gauge không còn giá trị | Binder giữ strong reference tới queue |
| Binder lưu một Counter handle dùng chung | Không phù hợp khi binder được bind vào nhiều registry | Đăng ký meter trong từng `bindTo` hoặc dùng function-tracking meter |
| Tạo queue mới trong `bindTo` | Các registry quan sát các state khác nhau | Queue được tạo một lần trong constructor/bean |
| Tăng accepted trước khi biết offer thành công | Counter đếm cả task bị từ chối | Chỉ tăng accepted sau offer thành công |
| Giảm depth khi poll trả null | Gauge có thể âm hoặc sai | Chỉ giảm khi poll lấy được task |
| Đếm task lấy khỏi queue là completed | Task có thể thất bại sau dequeue | Tách dequeued, completed và failed |
| Tag chứa task ID | Cardinality tăng theo số task | Dùng queue name ổn định |
| Tạo meter name động theo queue/request | Số meter tăng không kiểm soát | Giữ meter name cố định và dùng tag hữu hạn |
| Gọi bindTo thủ công đồng thời với Spring auto-bind | Cấu hình khó hiểu và dễ gây test sai | Chọn một cơ chế quản lý binding |
| Reset counter khi scrape | FunctionCounter có thể giảm và mất semantics monotonic | Chỉ tăng counter trong vòng đời state |
| Không đóng registry trong test | Tài nguyên test bị giữ lại | Đóng registry sau test |
| Nghĩ MeterBinder quản lý worker shutdown | Queue/thread có thể còn chạy sau khi context đóng | Quản lý worker lifecycle riêng bằng Spring lifecycle |

## Bài tập tự hoàn thành

Sau khi hoàn thành các bước chính, hãy thử các thay đổi sau:

1. Tạo queue thứ hai tên `emails` và capacity 10; xác minh hai queue có cùng meter name nhưng tag `queue` khác nhau.
2. Tạo `MeterFilter.maximumAllowableTags` để giới hạn tập queue name; quan sát hành vi khi đăng ký queue thứ ba.
3. Thêm Timer cho task execution và so sánh count, total time, max và percentile histogram khi bật distribution statistics.
4. Tạo test concurrent producers/consumers và xác minh depth cuối cùng bằng 0 sau khi tất cả task được xử lý.
5. Thêm một test cho task thất bại rồi xác minh failed tăng nhưng completed không tăng.
6. Bind binder vào hai registry khác loại nếu dự án có dependency phù hợp; so sánh tên trong Meter ID với tên export của từng registry.

Không đưa queue name tùy ý từ request vào tag. Nếu queue được tạo động, hãy dùng một tập tên đã cấu hình hoặc nhóm theo loại queue để giữ cardinality có giới hạn.

## Tiêu chí hoàn thành

- [ ] Queue có capacity dương và từ chối task khi đầy.
- [ ] Depth tăng khi submit thành công và giảm khi poll thành công.
- [ ] Accepted chỉ tăng khi queue nhận task.
- [ ] Rejected tăng khi queue đầy.
- [ ] Dequeued, completed và failed được phân biệt rõ.
- [ ] MeterBinder đăng ký hai Gauge và năm FunctionCounter.
- [ ] Tất cả meter dùng tag `queue` có giá trị ổn định.
- [ ] Queue state được giữ sống trong toàn bộ thời gian meter sử dụng.
- [ ] Cùng binder có thể bind vào nhiều registry.
- [ ] Bind lặp trong cùng registry không tạo Meter ID mới trùng lặp.
- [ ] Test xác minh queue state và meter values.
- [ ] Actuator và Prometheus export được kiểm tra bằng tên đúng lớp.
- [ ] Worker shutdown và registry shutdown có ownership rõ ràng.

## Ghi nhớ

- `MeterBinder` đóng gói đăng ký meter cho một component có state và vòng đời rõ ràng.
- `bindTo(MeterRegistry)` được gọi theo từng registry; không giữ một meter handle duy nhất để dùng chung nhiều registry.
- Gauge đọc trạng thái hiện tại; FunctionCounter đọc bộ đếm tích lũy chỉ tăng.
- Giữ strong reference tới queue state để Gauge không mất đối tượng được đo.
- Dùng queue name ổn định làm tag; không dùng task ID hoặc request ID.
- Phân biệt accepted, rejected, dequeued, completed và failed để diễn giải đúng trạng thái queue.
- Spring Boot tự động bind các bean MeterBinder; ứng dụng Micrometer độc lập có thể bind thủ công.
- MeterBinder không thay thế lifecycle quản lý worker hoặc tài nguyên queue.
- Kiểm thử cả queue behavior, Meter ID, registry binding và dữ liệu export.

Sau bài thực hành, queue không chỉ là một cấu trúc lưu task mà còn là một component có telemetry được đóng gói theo đúng vòng đời. Khi state được giữ ổn định, meter name và tag được kiểm soát, và binder không phụ thuộc vào một registry duy nhất, ứng dụng có thể mở rộng hệ thống giám sát mà không làm rối logic xử lý queue.

## Tài liệu tham khảo

- [Micrometer: Meter Binders](https://docs.micrometer.io/micrometer/reference/concepts/meter-binders.html) — vai trò và cách triển khai MeterBinder.
- [Micrometer: Gauges](https://docs.micrometer.io/micrometer/reference/concepts/gauges.html) — giá trị được lấy mẫu, weak references và vòng đời object.
- [Micrometer: Function-tracking Counters](https://docs.micrometer.io/micrometer/reference/concepts/counters.html) — FunctionCounter và bộ đếm tích lũy do ứng dụng quản lý.
- [Micrometer: Meters](https://docs.micrometer.io/micrometer/reference/concepts/meters.html) — meter types, naming và tag cardinality.
- [Spring Boot: Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html) — auto-configured registries, MeterBinder beans và MeterRegistryCustomizer.
- [Java API: ArrayBlockingQueue](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html) — queue có giới hạn và hành vi offer/poll.

