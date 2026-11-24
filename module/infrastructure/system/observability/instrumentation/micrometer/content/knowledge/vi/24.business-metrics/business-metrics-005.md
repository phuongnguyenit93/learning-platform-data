# Đo hàng đợi, số tác vụ hiện hành và thời gian chờ riêng với thời gian xử lý

Một worker xử lý hàng đợi cần trả lời ít nhất bốn câu hỏi: còn bao nhiêu tác vụ đang chờ, có bao nhiêu tác vụ đang được xử lý, mỗi tác vụ đã chờ bao lâu trước khi được nhận và worker mất bao lâu để xử lý sau khi bắt đầu. Bốn đại lượng này mô tả các trạng thái khác nhau và cần được instrument riêng.

Micrometer cung cấp Gauge để quan sát queue depth và số tác vụ đang chạy, Timer để ghi thời gian chờ và thời gian xử lý, cùng Counter để đếm số tác vụ được nhận, hoàn tất, thất bại hoặc bị từ chối. Khi tách đúng các phép đo, dashboard có thể chỉ ra worker đang thiếu năng lực tiêu thụ, xử lý chậm hay bị nghẽn ở giai đoạn chờ.

Bài học thuộc module OBSERVABILITY_INSTRUMENTATION_MICROMETER. Module này hướng dẫn sử dụng Micrometer để đo lường ứng dụng Java bằng counter, gauge, timer, distribution summary và nhãn có kiểm soát; tích hợp Spring Boot, xuất metrics đến hệ giám sát, kiểm soát cardinality, kiểm thử instrumentation và diễn giải số đo vận hành.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt queue depth, in-flight tasks, queue wait time và processing time.
- Chọn Gauge cho giá trị hiện tại và Timer cho thời lượng của từng tác vụ.
- Ghi thời điểm enqueue bằng đồng hồ monotonic để tính thời gian chờ.
- Đo thời gian xử lý riêng sau khi worker bắt đầu thực thi tác vụ.
- Theo dõi số tác vụ hoàn tất, thất bại và bị từ chối bằng Counter.
- Thiết kế tag có cardinality thấp cho queue và worker.
- Kiểm thử các meter bằng SimpleMeterRegistry.
- Diễn giải queue depth, in-flight count và hai phân phối thời gian để tìm điểm nghẽn.

## 1. Bốn đại lượng cần đo riêng

Xét một worker nhận tác vụ từ hàng đợi rồi xử lý. Mỗi tác vụ đi qua hai giai đoạn chính:

1. Tác vụ được đưa vào hàng đợi và chờ đến khi một worker lấy ra.
2. Worker bắt đầu xử lý và tiếp tục cho đến khi hoàn tất hoặc thất bại.

Ngoài thời gian, tại một thời điểm bất kỳ còn có hai số lượng cần quan sát: số tác vụ đang nằm trong hàng đợi và số tác vụ đang được xử lý.

| Đại lượng | Câu hỏi | Meter phù hợp | Ý nghĩa |
| --- | --- | --- | --- |
| Queue depth | Hiện còn bao nhiêu tác vụ đang chờ? | Gauge | Số phần tử hiện có trong queue |
| In-flight tasks | Hiện có bao nhiêu tác vụ đang chạy? | Gauge | Số tác vụ đã được worker nhận nhưng chưa kết thúc |
| Queue wait time | Một tác vụ chờ bao lâu trước khi được xử lý? | Timer | Thời gian từ lúc enqueue đến lúc worker bắt đầu xử lý |
| Processing time | Worker mất bao lâu để xử lý tác vụ? | Timer | Thời gian từ lúc bắt đầu xử lý đến lúc kết thúc |

Có thể thêm các Counter để theo dõi luồng tác vụ:

- `worker.tasks.submitted`: số tác vụ được đưa vào queue thành công.
- `worker.tasks.rejected`: số tác vụ không được nhận do queue đầy hoặc chính sách từ chối.
- `worker.tasks.completed`: số tác vụ hoàn tất.
- `worker.tasks.failed`: số tác vụ xử lý thất bại.

Queue depth và in-flight count là giá trị hiện tại, có thể tăng hoặc giảm, nên dùng Gauge. Counter phù hợp với tổng số sự kiện tích lũy. Timer ghi nhận nhiều mẫu thời lượng và cung cấp count, total time, mean, max, histogram hoặc percentile theo cấu hình.

## 2. Vòng đời tác vụ và điểm bắt đầu/kết thúc phép đo

Cần định nghĩa rõ các mốc thời gian trước khi viết instrumentation:

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant Q as Queue
    participant W as Worker
    participant M as Micrometer

    P->>Q: Enqueue task
    Note over P,Q: Lưu thời điểm enqueue
    M->>M: Queue depth tăng
    W->>Q: Take task
    Note over W: Bắt đầu queue wait sample
    M->>M: Ghi queue wait Timer
    M->>M: In-flight Gauge tăng
    Note over W: Bắt đầu processing Timer
    W->>W: Xử lý tác vụ
    W->>M: Ghi completed hoặc failed
    M->>M: Dừng processing Timer
    M->>M: In-flight Gauge giảm
~~~

Hai Timer có ranh giới khác nhau:

- Queue wait bắt đầu tại thời điểm tác vụ được chấp nhận vào queue và kết thúc khi worker đã lấy tác vụ để bắt đầu xử lý.
- Processing bắt đầu ngay trước khi gọi logic xử lý và kết thúc sau khi logic đó hoàn tất hoặc ném exception.

Không đo toàn bộ vòng lặp worker bằng một Timer processing. Nếu Timer bao gồm cả lời gọi `queue.take()`, nó sẽ tính cả thời gian thread nằm chờ khi queue rỗng. Khi đó, processing time bị phóng đại và không còn phản ánh thời gian xử lý tác vụ.

## 3. Queue depth là Gauge

Queue depth cho biết số phần tử hiện đang chờ trong queue. Đây là giá trị tại thời điểm registry lấy mẫu, không phải tổng số tác vụ từng được gửi.

Với một `BlockingQueue`, có thể đăng ký Gauge trực tiếp:

~~~java
import java.util.concurrent.BlockingQueue;

import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;

public final class QueueMetrics {

    private final BlockingQueue<?> queue;

    public QueueMetrics(
            MeterRegistry registry,
            BlockingQueue<?> queue,
            String queueName
    ) {
        this.queue = queue;

        Gauge.builder("worker.queue.depth", queue, q -> q.size())
                .description("Số tác vụ hiện đang chờ trong queue")
                .tag("queue", queueName)
                .register(registry);
    }
}
~~~

Gauge đọc `queue.size()` khi registry lấy mẫu. Không cần gọi increment hoặc decrement cho Gauge này; giá trị được lấy từ đối tượng queue đang được quan sát.

### Giữ tham chiếu đến đối tượng được đo

Micrometer Gauge thường giữ weak reference đến đối tượng quan sát. Nếu queue chỉ là biến cục bộ và không còn tham chiếu mạnh, Gauge có thể không đọc được giá trị mong muốn sau khi đối tượng bị garbage collection.

Ví dụ trên giữ queue trong field `this.queue`, nhờ đó queue còn sống cùng vòng đời của QueueMetrics. Tương tự, nếu dùng AtomicInteger làm nguồn Gauge, hãy giữ AtomicInteger trong field của component.

Queue depth và in-flight được scrape độc lập, không phải một snapshot transaction. Trong khoảng rất ngắn giữa lúc `take()` lấy phần tử và lúc worker tăng in-flight, một lần scrape có thể thấy cả hai Gauge thấp hơn trạng thái logic ngay sau đó. Đây là đặc tính của các phép đo trạng thái đồng thời; không nên dùng hai Gauge này như một phép kiểm kê nguyên tử.

### Chú ý chi phí của size()

Độ phức tạp và độ chính xác của `size()` phụ thuộc queue implementation. Với một số queue, thao tác này có thể tốn kém hoặc chỉ phản ánh snapshot gần đúng khi có nhiều producer/consumer đồng thời. Không nên gọi một phép tính O(n) trên mỗi lần scrape nếu queue có thể rất lớn.

Nếu queue không cung cấp size rẻ và đáng tin cậy, có thể duy trì một AtomicInteger làm queue depth. Hãy tăng sau khi enqueue thành công và giảm đúng một lần khi dequeue hoặc loại bỏ thành công. Việc cập nhật phải nằm trong cùng luồng thao tác với queue để tránh đếm sai khi enqueue thất bại, dequeue đồng thời hoặc hủy tác vụ.

Queue depth không nên dùng Counter vì số phần tử đang chờ có thể giảm khi worker lấy tác vụ ra. Counter chỉ tăng và không biểu diễn trạng thái hiện tại.

## 4. In-flight tasks là Gauge

In-flight tasks là số tác vụ worker đã nhận và đang xử lý. Giá trị này tăng khi worker bắt đầu xử lý và giảm khi xử lý kết thúc, kể cả khi có exception.

Dùng AtomicInteger để chia sẻ số lượng giữa các worker thread:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;

public final class InFlightMetrics {

    private final AtomicInteger inFlight = new AtomicInteger();

    public InFlightMetrics(MeterRegistry registry, String queueName) {
        Gauge.builder(
                "worker.tasks.inflight",
                inFlight,
                AtomicInteger::get
        )
        .description("Số tác vụ hiện đang được xử lý")
        .tag("queue", queueName)
        .register(registry);
    }

    public void taskStarted() {
        inFlight.incrementAndGet();
    }

    public void taskFinished() {
        inFlight.decrementAndGet();
    }
}
~~~

Đối tượng AtomicInteger được giữ trong field để Gauge luôn có nguồn dữ liệu. Khi có nhiều thread cùng xử lý một queue, tất cả phải cập nhật cùng bộ đếm in-flight của queue đó. Nếu mỗi worker có một AtomicInteger riêng, metric sẽ phản ánh số tác vụ theo từng worker; hãy chọn phạm vi tag và phạm vi bộ đếm theo câu hỏi cần trả lời.

Luôn đặt thao tác giảm in-flight trong khối `finally`. Nếu chỉ giảm sau khi xử lý thành công, một exception có thể khiến số tác vụ đang chạy bị giữ lại mãi và Gauge tăng sai.

## 5. Đo queue wait time bằng đồng hồ monotonic

Queue wait time là khoảng thời gian từ lúc producer đưa tác vụ vào queue đến lúc worker bắt đầu xử lý. Cần lưu mốc enqueue cùng tác vụ để worker tính được thời lượng khi lấy ra.

Trong cùng một JVM, dùng `System.nanoTime()` để đo khoảng thời gian:

~~~java
import java.util.concurrent.TimeUnit;

import io.micrometer.core.instrument.Timer;

public record QueuedTask<T>(
        T payload,
        long enqueuedAtNanos
) {
    public static <T> QueuedTask<T> create(T payload) {
        return new QueuedTask<>(payload, System.nanoTime());
    }

    public void recordQueueWait(Timer queueWaitTimer) {
        long waitNanos = System.nanoTime() - enqueuedAtNanos;
        queueWaitTimer.record(waitNanos, TimeUnit.NANOSECONDS);
    }
}
~~~

`System.nanoTime()` là đồng hồ monotonic dành cho đo khoảng thời gian. Giá trị gốc không phải timestamp lịch và không có ý nghĩa nếu so sánh với `Instant.now()`. Chỉ lấy hiệu giữa hai lần đọc nanoTime trong cùng tiến trình.

Không dùng `System.currentTimeMillis()` hoặc `Instant.now()` làm đồng hồ chính để tính duration nội bộ nếu có thể dùng nanoTime. Đồng hồ lịch có thể được điều chỉnh bởi NTP hoặc thao tác hệ thống, làm khoảng thời gian âm hoặc nhảy bất thường.

### Ghi nhận queue wait khi dequeue

Khi worker lấy được tác vụ, tính thời gian chờ trước khi bắt đầu xử lý:

~~~java
QueuedTask<Task> item = queue.take();

long startedAt = System.nanoTime();
long waitNanos = startedAt - item.enqueuedAtNanos();

queueWaitTimer.record(waitNanos, TimeUnit.NANOSECONDS);
~~~

Mốc `startedAt` được lấy ngay sau khi `take()` trả về. Vì vậy, thời gian đo bao gồm thời gian tác vụ nằm trong queue và khoảng trễ lập lịch rất ngắn cho đến khi worker bắt đầu thực thi. Đây là một định nghĩa thực tế của queue wait time.

Chỉ ghi mẫu queue wait cho tác vụ thực sự được worker lấy ra. Nếu enqueue bị từ chối, hãy tăng rejected counter. Nếu tác vụ bị hủy khi còn trong queue, hãy ghi nhận cancellation bằng Counter riêng nếu cần phân tích; không tạo một mẫu queue wait giả cho tác vụ chưa bao giờ được xử lý.

## 6. Đo processing time bằng Timer riêng

Processing time chỉ bao gồm thời gian thực thi logic xử lý. Có thể dùng Timer.Sample để bắt đầu và dừng phép đo trong khối `try/finally`:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

Timer.Sample sample = Timer.start(registry);

try {
    processor.process(task);
} finally {
    sample.stop(processingTimer);
}
~~~

Cách này bảo đảm Timer được ghi khi method kết thúc bình thường hoặc ném exception. Nếu muốn phân biệt success và failure, có thể dùng hai Timer có tag outcome cố định hoặc một Timer chung kết hợp với Counter failure.

Ví dụ tách theo outcome:

~~~java
Timer processingSuccess = Timer.builder("worker.task.processing")
        .tag("queue", "invoice")
        .tag("outcome", "success")
        .register(registry);

Timer processingFailure = Timer.builder("worker.task.processing")
        .tag("queue", "invoice")
        .tag("outcome", "failure")
        .register(registry);

Timer.Sample sample = Timer.start(registry);
Timer resultTimer = processingSuccess;

try {
    processor.process(task);
} catch (RuntimeException ex) {
    resultTimer = processingFailure;
    throw ex;
} finally {
    sample.stop(resultTimer);
}
~~~

Tag `outcome` chỉ có hai giá trị cố định nên cardinality được kiểm soát. Với hệ thống có nhiều loại exception, không nên dùng exception message làm tag. Có thể dùng exception class nếu danh mục class được giới hạn hoặc chuẩn hóa thành nhóm lỗi.

Nếu không cần phân tích processing time theo kết quả, một Timer chung thường đơn giản hơn. Có thể giữ Counter riêng để đếm số tác vụ thất bại.

## 7. Kết hợp queue, in-flight và Timer trong một worker

Ví dụ sau minh họa một worker dùng BlockingQueue. Tất cả consumer thread gọi `runOne()` trên cùng đối tượng worker để chia sẻ Gauge in-flight. Mã rút gọn tập trung vào ranh giới đo lường:

~~~java
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Consumer;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

public final class InstrumentedWorker<T> {

    private final BlockingQueue<QueuedTask<T>> queue;
    private final AtomicInteger inFlight = new AtomicInteger();

    private final Timer queueWait;
    private final Timer processing;
    private final Counter submitted;
    private final Counter rejected;
    private final Counter completed;
    private final Counter failed;
    private final MeterRegistry registry;

    public InstrumentedWorker(
            MeterRegistry registry,
            BlockingQueue<QueuedTask<T>> queue,
            String queueName
    ) {
        this.registry = registry;
        this.queue = queue;

        Gauge.builder("worker.queue.depth", queue, q -> q.size())
                .description("Số tác vụ hiện đang chờ")
                .tag("queue", queueName)
                .register(registry);

        Gauge.builder(
                "worker.tasks.inflight",
                inFlight,
                AtomicInteger::get
        )
        .description("Số tác vụ hiện đang được xử lý")
        .tag("queue", queueName)
        .register(registry);

        this.queueWait = Timer.builder("worker.queue.wait")
                .description("Thời gian tác vụ chờ trong queue")
                .tag("queue", queueName)
                .register(registry);

        this.processing = Timer.builder("worker.task.processing")
                .description("Thời gian xử lý tác vụ")
                .tag("queue", queueName)
                .register(registry);

        this.submitted = registry.counter(
                "worker.tasks.submitted", "queue", queueName);
        this.rejected = registry.counter(
                "worker.tasks.rejected", "queue", queueName);
        this.completed = registry.counter(
                "worker.tasks.completed", "queue", queueName);
        this.failed = registry.counter(
                "worker.tasks.failed", "queue", queueName);
    }

    public boolean submit(T payload) {
        QueuedTask<T> item = QueuedTask.create(payload);

        if (queue.offer(item)) {
            submitted.increment();
            return true;
        }

        rejected.increment();
        return false;
    }

    public void runOne(Consumer<T> processor)
            throws InterruptedException {

        QueuedTask<T> item = queue.take();

        long startedAt = System.nanoTime();
        queueWait.record(
                startedAt - item.enqueuedAtNanos(),
                TimeUnit.NANOSECONDS
        );

        inFlight.incrementAndGet();
        Timer.Sample sample = Timer.start(registry);

        try {
            processor.accept(item.payload());
            completed.increment();
        } catch (RuntimeException ex) {
            failed.increment();
            throw ex;
        } finally {
            sample.stop(processing);
            inFlight.decrementAndGet();
        }
    }
}
~~~

Record mang timestamp enqueue:

~~~java
public record QueuedTask<T>(
        T payload,
        long enqueuedAtNanos
) {
    public static <T> QueuedTask<T> create(T payload) {
        return new QueuedTask<>(payload, System.nanoTime());
    }
}
~~~

Các điểm quan trọng trong ví dụ:

- Queue depth được đọc từ chính BlockingQueue.
- In-flight dùng AtomicInteger và được cập nhật trong mọi đường kết thúc xử lý.
- Queue wait được ghi ngay sau khi lấy tác vụ ra.
- Processing Timer bắt đầu sau khi đã ghi queue wait.
- Processing Timer dừng trong finally để bao gồm cả lần xử lý ném RuntimeException.
- Submitted chỉ tăng khi queue nhận tác vụ.
- Rejected tăng khi offer trả về false.
- Completed và failed phản ánh kết quả xử lý.
- Tag queue là giá trị cố định, không chứa task ID.

Ví dụ giả định `processor` ném RuntimeException cho lỗi nghiệp vụ. Nếu ứng dụng cần xử lý checked exception, có thể định nghĩa functional interface riêng cho processor và vẫn giữ cấu trúc `try/catch/finally`. Nếu worker có cơ chế retry, cần quyết định Timer đo mỗi lần thử hay toàn bộ vòng đời tác vụ; không trộn hai ngữ nghĩa vào cùng một metric.

## 8. Tác vụ đang chạy lâu và LongTaskTimer

Gauge in-flight trả lời câu hỏi hiện có bao nhiêu tác vụ đang xử lý. Timer thông thường chỉ ghi mẫu khi tác vụ kết thúc, nên dashboard chưa thấy thời lượng của một tác vụ vẫn đang chạy.

Nếu cần quan sát các tác vụ dài đang hoạt động, Micrometer có LongTaskTimer. LongTaskTimer theo dõi số task đang active và thời gian hoạt động của chúng trước khi hoàn tất. Có thể bắt đầu một sample khi worker nhận task và dừng sample khi task kết thúc.

~~~java
import io.micrometer.core.instrument.LongTaskTimer;

LongTaskTimer activeTaskTimer = LongTaskTimer
        .builder("worker.task.active")
        .tag("queue", "invoice")
        .register(registry);

LongTaskTimer.Sample activeSample = activeTaskTimer.start();

try {
    processor.process(task);
} finally {
    activeSample.stop();
}
~~~

LongTaskTimer bổ sung góc nhìn về công việc đang chạy lâu. Nó không thay thế processing Timer nếu vẫn cần phân phối thời gian của các tác vụ đã hoàn tất. Cũng không cần tạo LongTaskTimer cho mọi tác vụ ngắn nếu Gauge in-flight và Timer thông thường đã trả lời đủ câu hỏi vận hành.

## 9. Tag và cardinality cho metrics của queue

Một bộ tag nhỏ giúp so sánh các queue hoặc worker pool:

| Tag | Giá trị phù hợp | Tránh |
| --- | --- | --- |
| `queue` | invoice, email, image | Tên queue do user tạo tùy ý |
| `worker` | import, notification, thumbnail | Thread ID hoặc worker instance ID biến đổi liên tục |
| `outcome` | success, failure, timeout | Exception message |
| `priority` | low, normal, high | Giá trị priority tự do không giới hạn |

Không đưa task ID, message ID, user ID, order ID hoặc payload vào tag. Các ID này phù hợp với log hoặc trace context, không phù hợp với metric dimension.

Nếu có nhiều instance chạy cùng queue, Resource attributes hoặc tag instance có thể giúp phân biệt nguồn dữ liệu tùy backend. Tuy nhiên, hãy thống nhất mô hình nhận diện instance ở registry/exporter và tránh lặp lại dimension không cần thiết.

### Cấu hình histogram cho thời gian chờ và xử lý

Mean queue wait thấp không bảo đảm mọi tác vụ đều được xử lý nhanh. Một số tác vụ có thể chờ rất lâu trong khi phần lớn được xử lý ngay. Histogram hoặc percentile giúp quan sát phần đuôi phân phối.

Ví dụ cấu hình SLO boundaries:

~~~java
Timer queueWait = Timer.builder("worker.queue.wait")
        .tag("queue", "invoice")
        .serviceLevelObjectives(
                Duration.ofMillis(50),
                Duration.ofMillis(250),
                Duration.ofSeconds(1),
                Duration.ofSeconds(5)
        )
        .register(registry);
~~~

Chọn ngưỡng theo yêu cầu nghiệp vụ. Queue gửi email có thể chấp nhận chờ vài giây, trong khi queue xử lý giao dịch có thể cần ngưỡng thấp hơn. Histogram làm tăng số chuỗi thời gian theo bucket và tổ hợp tag, nên chỉ bật cho những queue cần phân tích phân phối.

## 10. Kiểm thử bằng SimpleMeterRegistry

SimpleMeterRegistry phù hợp để kiểm tra Gauge và Timer trong bộ nhớ mà không cần backend. Test dưới đây minh họa bốn đại lượng được giữ riêng:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

class WorkerQueueMetricsTest {

    @Test
    void recordsQueueDepthInflightAndSeparateDurations() {
        var registry = new SimpleMeterRegistry();
        var queue = new LinkedBlockingQueue<String>();
        var inFlight = new AtomicInteger();

        Gauge.builder("worker.queue.depth", queue, q -> q.size())
                .register(registry);

        Gauge.builder(
                "worker.tasks.inflight",
                inFlight,
                AtomicInteger::get
        ).register(registry);

        Timer queueWait = registry.timer("worker.queue.wait");
        Timer processing = registry.timer("worker.task.processing");

        queue.add("task-1");
        inFlight.set(2);

        queueWait.record(120, TimeUnit.MILLISECONDS);
        processing.record(45, TimeUnit.MILLISECONDS);

        assertThat(registry.get("worker.queue.depth")
                .gauge().value()).isEqualTo(1.0);

        assertThat(registry.get("worker.tasks.inflight")
                .gauge().value()).isEqualTo(2.0);

        assertThat(queueWait.count()).isEqualTo(1L);
        assertThat(queueWait.totalTime(TimeUnit.MILLISECONDS))
                .isEqualTo(120.0);

        assertThat(processing.count()).isEqualTo(1L);
        assertThat(processing.totalTime(TimeUnit.MILLISECONDS))
                .isEqualTo(45.0);
    }
}
~~~

Test dùng thời lượng cố định để kiểm tra hai Timer không bị trộn lẫn. Trong test cho worker thật, hãy gọi submit, chạy một consumer và xác nhận queue depth giảm sau dequeue, in-flight tăng trong khi processor đang chạy rồi giảm khi processor kết thúc.

Có thể dùng CountDownLatch để giữ processor ở trạng thái đang chạy trong lúc test đọc Gauge. Tránh dùng sleep dài vì test sẽ chậm và phụ thuộc lịch chạy thread.

### Các trường hợp nên kiểm thử thêm

- Queue còn rỗng: queue depth bằng 0.
- Enqueue thành công: submitted tăng và queue depth tăng.
- Queue đầy: rejected tăng, không ghi queue wait cho tác vụ bị từ chối.
- Worker dequeue: queue depth giảm và queue wait có một mẫu.
- Processor thành công: completed tăng, processing Timer có một mẫu, in-flight trở về 0.
- Processor ném exception: failed tăng, processing Timer vẫn ghi nhận và in-flight trở về 0.
- Nhiều worker chạy song song: in-flight phản ánh tổng số tác vụ đang xử lý trong phạm vi đã chọn.
- Hủy tác vụ trước dequeue: queue depth giảm và cancellation được ghi nhận theo chính sách.
- Retry: xác nhận metric ghi theo từng attempt hay theo toàn bộ task lifecycle.

## 11. Diễn giải metrics để tìm điểm nghẽn

Không nên xem queue depth riêng lẻ. Kết hợp queue depth, in-flight, queue wait và processing time sẽ cho bức tranh rõ hơn.

| Quan sát | Diễn giải có thể | Hướng kiểm tra |
| --- | --- | --- |
| Queue depth tăng liên tục, in-flight ở gần giới hạn worker | Tốc độ producer lớn hơn năng lực consumer | Tăng consumer có kiểm soát, tối ưu xử lý hoặc áp dụng backpressure |
| Queue depth cao, in-flight thấp | Worker không nhận việc, bị pause hoặc không đủ consumer hoạt động | Kiểm tra thread pool, worker health, lock và dependency |
| Queue wait tăng, processing time ổn định | Tác vụ chờ lâu trước khi được xử lý | Kiểm tra số worker, lịch chạy và tốc độ enqueue |
| Processing time tăng, queue wait cũng tăng | Worker xử lý chậm làm backlog tích tụ | Kiểm tra CPU, GC, database và dịch vụ phụ thuộc |
| Queue depth thấp nhưng queue wait p95 cao | Có burst ngắn hoặc thời gian chờ biến động mà snapshot Gauge không thể hiện | Xem histogram queue wait theo cửa sổ thời gian |
| In-flight cao nhưng processing time thấp | Có nhiều tác vụ đồng thời, mỗi tác vụ nhanh | Kiểm tra concurrency limit và tải đầu vào |
| Rejected tăng | Queue đầy hoặc chính sách từ chối đang hoạt động | Kiểm tra capacity, producer rate và backpressure |
| Failed tăng cùng processing time tăng | Lỗi dependency hoặc xử lý thất bại kéo dài | Phân tích exception class, retry và dependency latency |

Queue depth là snapshot tại thời điểm scrape. Một queue có thể tăng vọt rồi giảm giữa hai lần scrape; Timer queue wait vẫn giữ lại các mẫu thời gian chờ của tác vụ đã được lấy ra. Vì vậy, kết hợp Gauge và Timer giúp quan sát cả trạng thái hiện tại lẫn trải nghiệm chờ đã xảy ra.

### Ví dụ PromQL

Nếu dùng Prometheus và đã bật histogram cho các Timer, có thể truy vấn p95 queue wait:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, queue) (
    rate(worker_queue_wait_seconds_bucket[5m])
  )
)
~~~

P95 processing time:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, queue) (
    rate(worker_task_processing_seconds_bucket[5m])
  )
)
~~~

Queue depth hiện tại:

~~~promql
worker_queue_depth
~~~

Số tác vụ đang xử lý:

~~~promql
worker_tasks_inflight
~~~

Tốc độ hoàn tất tác vụ:

~~~promql
sum by (queue) (
  rate(worker_tasks_completed_total[5m])
)
~~~

Tên series minh họa theo NamingConvention của Prometheus registry. Hãy xác nhận tên thực tế tại endpoint scrape trước khi đưa truy vấn vào dashboard. Nếu chưa bật histogram, không thể tính p95 từ các series count và sum đơn thuần.

## 12. Phân biệt queue wait, processing và end-to-end time

Với một tác vụ chỉ đi qua một queue và một lần xử lý, end-to-end time có thể được xem gần đúng là:

`end-to-end = queue wait + processing time`

Tuy nhiên, hai phân phối không thể cộng percentile với nhau để tạo percentile end-to-end. Ví dụ, p95 queue wait cộng p95 processing không nhất thiết bằng p95 tổng thời gian của từng tác vụ. Nếu cần latency end-to-end, hãy đo trực tiếp từ lúc tiếp nhận đến khi hoàn tất bằng một Timer thứ ba.

Với retry, tác vụ có thể trải qua nhiều chu kỳ queue wait và processing. Hãy quyết định rõ:

- Queue wait và processing được ghi theo từng attempt.
- End-to-end time được ghi một lần cho toàn bộ task lifecycle.
- Retry count được ghi bằng Counter hoặc một đại lượng phù hợp.

Không cộng các Timer đã ghi theo từng attempt rồi gọi đó là thời gian toàn bộ tác vụ nếu có thời gian backoff, chuyển queue hoặc chờ giữa các attempt.

### Queue trong cùng JVM và message broker phân tán

Ví dụ dùng `System.nanoTime()` chỉ đúng khi enqueue và dequeue diễn ra trong cùng JVM. Giá trị nanoTime không thể truyền từ producer process sang consumer process để so sánh.

Với Kafka, RabbitMQ hoặc broker phân tán:

- Dùng timestamp do broker cung cấp hoặc timestamp sự kiện được chuẩn hóa để ước lượng message age.
- Kiểm tra clock synchronization và sai lệch đồng hồ giữa producer/consumer.
- Ưu tiên broker lag/consumer lag metrics khi chúng đã phản ánh đúng semantics của hệ thống.
- Dùng tracing context để phân tích hành trình qua nhiều service.
- Đo processing time cục bộ bằng nanoTime tại consumer như bình thường.

Không trừ hai giá trị nanoTime lấy từ hai JVM khác nhau.

## 13. Các lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Dùng Counter cho queue depth | Không thể biểu diễn số phần tử đang giảm | Dùng Gauge |
| Dùng một Timer bao quanh cả queue.take() và xử lý | Processing time gồm cả thời gian thread chờ queue rỗng | Tách queue wait và processing Timer |
| Ghi queue wait tại lúc producer enqueue | Chỉ đo được thời gian tạo item, chưa đo thời gian chờ | Lưu mốc enqueue và ghi khi dequeue |
| Dùng currentTimeMillis để đo duration nội bộ | Clock adjustment có thể làm sai thời lượng | Dùng System.nanoTime |
| Dùng nanoTime giữa hai JVM | Hai mốc không cùng origin | Dùng broker timestamp hoặc telemetry phân tán |
| Không giảm in-flight trong finally | Exception làm Gauge bị kẹt ở giá trị cao | Giảm trong finally |
| Gauge giữ đối tượng tạm thời | Weak reference có thể mất nguồn dữ liệu | Giữ queue hoặc AtomicInteger trong field |
| Gọi queue.size() tốn kém trên queue lớn | Scrape làm tăng tải ứng dụng | Kiểm tra implementation hoặc duy trì depth counter an toàn |
| Dùng task ID làm tag | Cardinality tăng theo số tác vụ | Dùng queue/worker/outcome có tập giá trị hữu hạn |
| Đếm tác vụ retry không rõ semantics | Count và latency khó diễn giải | Phân biệt attempt-level và task-level |
| Chỉ nhìn queue depth | Bỏ lỡ thời gian chờ và tốc độ xử lý | Kết hợp Gauge, Timer và Counter |
| Cộng p95 queue wait với p95 processing | Ước lượng end-to-end sai | Đo end-to-end Timer trực tiếp nếu cần |

## 14. Checklist triển khai

Trước khi đưa metrics cho worker vào production, hãy xác nhận:

1. Queue depth có phản ánh số tác vụ đang chờ tại thời điểm lấy mẫu không?
2. In-flight Gauge có tăng khi bắt đầu và giảm trong finally không?
3. Queue wait bắt đầu tại enqueue và kết thúc khi worker bắt đầu xử lý không?
4. Processing Timer có loại trừ thời gian queue rỗng và thời gian chờ lấy việc không?
5. Timestamp nội bộ có dùng nanoTime trong cùng JVM không?
6. Queue size có chi phí phù hợp với queue implementation không?
7. Enqueue bị từ chối, tác vụ bị hủy và retry có semantics riêng không?
8. Tag queue, worker và outcome có tập giá trị hữu hạn không?
9. Histogram hoặc SLO boundary có phù hợp với yêu cầu nghiệp vụ không?
10. Test đã xác nhận cả đường thành công, thất bại và concurrency chưa?

## Kết luận

Queue depth và in-flight tasks là hai Gauge mô tả trạng thái hiện tại; queue wait time và processing time là hai Timer mô tả hai giai đoạn khác nhau trong vòng đời tác vụ. Counter bổ sung số lượt gửi, từ chối, hoàn tất và thất bại. Tách các phép đo này giúp phân biệt backlog do consumer thiếu năng lực với xử lý chậm bên trong worker.

Hãy lưu mốc enqueue bằng nanoTime khi queue và worker cùng chạy trong một JVM, ghi queue wait ngay khi dequeue và chỉ đo processing quanh logic xử lý. Giữ tham chiếu đến nguồn Gauge, giảm in-flight trong finally, chuẩn hóa tag và kiểm thử cả trạng thái đồng thời. Khi cần thời gian toàn hành trình, đo end-to-end riêng thay vì cộng các percentile của hai Timer thành phần.
