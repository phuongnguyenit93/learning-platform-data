# Chi phí lấy mẫu Gauge và nguy cơ hàm đọc thực hiện công việc chậm

Micrometer Gauge biểu diễn một giá trị hiện tại như số phần tử trong queue, số worker đang hoạt động hoặc dung lượng đang sử dụng. Khác với Counter và Timer, Gauge không tích lũy mọi thay đổi xảy ra giữa hai lần thu thập. Registry đọc hàm lấy giá trị khi meter được quan sát hoặc export; kết quả tại thời điểm đọc là sample được gửi tới backend.

Cách hoạt động này khiến hàm đọc Gauge trở thành một phần của đường thu thập telemetry. Nếu hàm chỉ đọc một biến atomic, chi phí thường rất nhỏ. Nếu hàm duyệt hàng nghìn phần tử, chờ lock, gọi database hoặc truy vấn một dịch vụ khác, chính thao tác scrape/export có thể bị chậm. Bài học này tập trung vào chi phí lấy mẫu, những lỗi thường gặp và cách thay hàm đọc tốn kém bằng trạng thái đã được cập nhật sẵn.

## Mục tiêu

Sau bài học, bạn có thể:

- Giải thích thời điểm Micrometer gọi hàm lấy giá trị Gauge.
- Ước lượng chi phí lấy mẫu theo số Gauge, tần suất scrape và số instance.
- Nhận diện hàm đọc có độ phức tạp cao, blocking I/O hoặc lock contention.
- Hiểu tác động của Gauge chậm lên endpoint Prometheus và chu kỳ export.
- Thay phép tính tốn kém bằng AtomicInteger, AtomicLong hoặc snapshot.
- Theo dõi tuổi snapshot và lỗi làm mới để không che giấu dữ liệu cũ.
- Phân biệt giá trị hiện tại của Gauge với số sự kiện hoặc cực trị trong một khoảng.
- Đo và benchmark chi phí instrumentation trước khi triển khai.

## Gauge lấy mẫu khi nào?

Gauge là một handle để đọc giá trị hiện tại. Khi registry hoặc thành phần đọc meter gọi phép đo của Gauge, hàm được đăng ký sẽ được thực thi để lấy sample. Với Prometheus, việc này thường xảy ra trong lần scrape endpoint metrics. Với registry đẩy dữ liệu theo chu kỳ, việc đọc thường xảy ra trong quá trình registry thu thập và xuất batch metrics.

Điều này có ba hệ quả:

1. Hàm đọc Gauge chạy theo chu kỳ thu thập hoặc mỗi lần giá trị được yêu cầu, không chạy mỗi khi trạng thái nghiệp vụ thay đổi.
2. Nếu có nhiều registry, nhiều reader hoặc nhiều lần thu thập, hàm đọc có thể được gọi nhiều lần. Không thiết kế hàm dựa trên giả định rằng nó chỉ được gọi đúng một lần.
3. Giá trị ở giữa hai lần sample không được Gauge giữ lại. Một đỉnh ngắn xuất hiện rồi biến mất giữa hai lần scrape có thể không bao giờ xuất hiện trong backend.

Micrometer mô tả Gauge là meter được lấy mẫu khi được quan sát. Nếu một giá trị thay đổi nhiều lần giữa hai lần thu thập, backend chỉ nhận sample tại thời điểm đọc; các giá trị trung gian không được cộng dồn.

~~~mermaid
sequenceDiagram
    participant App as Ứng dụng
    participant State as Trạng thái
    participant Registry as MeterRegistry
    participant Backend as Backend
    App->>State: Cập nhật trạng thái
    App->>State: Cập nhật trạng thái
    App->>State: Cập nhật trạng thái
    Backend->>Registry: Scrape hoặc export
    Registry->>State: Gọi hàm đọc Gauge
    State-->>Registry: Giá trị hiện tại
    Registry-->>Backend: Gửi sample
~~~

Ví dụ, queue lần lượt có độ sâu 10, 30, 5 rồi trở về 12 trước lần scrape tiếp theo. Gauge có thể chỉ gửi giá trị 12. Nếu cần biết queue từng đạt đỉnh 30, phải ghi nhận cực trị hoặc phân phối bằng một cơ chế tích lũy riêng; chỉ dùng Gauge hiện tại là chưa đủ.

## Chi phí của một lần lấy mẫu

Một Gauge thường thực hiện một phép đọc khi được thu thập. Tổng chi phí của lần thu thập phụ thuộc số Gauge và chi phí hàm đọc của từng Gauge:

| Thành phần | Ảnh hưởng |
|---|---|
| Số lượng Gauge | Càng nhiều hàm đọc được gọi trong một lần thu thập |
| Độ phức tạp hàm đọc | O(1) thường rẻ hơn duyệt collection O(n) |
| Tần suất scrape/export | Chu kỳ càng ngắn, cùng hàm đọc chạy càng thường xuyên |
| Số instance | Tổng công việc trên toàn hệ thống tăng theo số replica |
| Số registry/reader | Một state object có thể bị đọc qua nhiều đường thu thập |
| Tranh chấp tài nguyên | Lock, CPU, I/O hoặc connection pool bị chia sẻ với workload |

Có thể dùng mô hình gần đúng để lập ngân sách:

\[
C_{total} \approx N \times F \times \sum_{i=1}^{M} C_i
\]

Trong đó:

- N là số instance.
- F là số lần thu thập mỗi giây trên mỗi instance.
- M là số Gauge được thu thập.
- C_i là chi phí trung bình của hàm đọc Gauge thứ i.

Đây là mô hình ước lượng công việc, không phải công thức dự đoán latency chính xác. Một hàm đọc blocking có thể làm thời gian thu thập tăng theo thời gian chờ, còn các hàm đọc chạy song song có thể cạnh tranh CPU, lock hoặc connection pool.

Ví dụ, một service có 20 replica, mỗi replica có 100 Gauge và Prometheus scrape mỗi 15 giây. Mỗi instance thực hiện khoảng 100 / 15 = 6.7 lượt đọc Gauge mỗi giây; toàn cụm thực hiện khoảng 20 × 100 / 15 = 133.3 lượt đọc mỗi giây nếu mỗi lần scrape đọc mỗi Gauge một lần. Nếu một Gauge thực hiện truy vấn database mất 40 ms, nó có thể chiếm khoảng 40 ms trong mỗi lần scrape của từng replica, đồng thời tạo thêm tải database theo chu kỳ.

Không nên đánh giá chi phí chỉ bằng số micro giây của một lần đọc. Hãy xem cả số lần gọi, số replica, số collector, mức tranh chấp và tác động lên thời gian scrape.

## Hàm đọc Gauge chậm gây ra vấn đề gì?

Hàm đọc được gọi trong đường thu thập telemetry. Tùy registry và cách thu thập, một hàm chậm có thể gây ra:

- **Endpoint scrape phản hồi chậm:** Prometheus phải chờ ứng dụng tạo toàn bộ exposition response.
- **Scrape timeout:** nếu endpoint không trả kết quả trước scrape timeout, lần scrape có thể thất bại và nhiều metric cùng bị mất ở lần đó.
- **Chu kỳ export kéo dài:** registry push có thể hoàn thành batch muộn hơn dự kiến.
- **Tắc nghẽn thread:** nhiều lần scrape đồng thời có thể chiếm các thread phục vụ endpoint metrics.
- **Lock contention:** hàm đọc chờ lock đang được luồng nghiệp vụ giữ, hoặc chính nó giữ lock quá lâu.
- **Tải phụ lên dependency:** scrape metrics liên tục gọi database hoặc API sẽ tạo tải không thuộc nghiệp vụ.
- **Hiệu ứng khuếch đại:** số replica và tần suất scrape tăng làm chi phí của hàm đọc nhân lên.

Một điểm cần nhớ: scrape là hoạt động giám sát. Nếu scrape endpoint phải đợi truy vấn database chỉ để biết queue depth, hệ thống giám sát có thể làm database bận hơn ngay khi ứng dụng đang quá tải.

## Anti-pattern: duyệt queue trong hàm đọc

Một ví dụ dễ gặp là dùng size của ConcurrentLinkedQueue làm Gauge:

~~~java
import java.util.concurrent.ConcurrentLinkedQueue;

import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;

public final class QueueMetrics {

    private final ConcurrentLinkedQueue<Runnable> queue =
        new ConcurrentLinkedQueue<>();

    public QueueMetrics(MeterRegistry registry) {
        Gauge.builder("worker.queue.depth", queue, ConcurrentLinkedQueue::size)
            .description("Số phần tử hiện có trong worker queue")
            .register(registry);
    }
}
~~~

Mã trên ngắn nhưng có chi phí ẩn. Java API ghi rõ ConcurrentLinkedQueue.size() không phải thao tác constant-time; nó phải duyệt O(n) các phần tử và có thể trả về kết quả không chính xác khi queue bị thay đổi đồng thời. Với queue lớn, mỗi lần scrape có thể duyệt hàng nghìn hoặc hàng triệu node.

Đặc biệt, queue có thể tăng đúng lúc hệ thống chịu tải cao. Khi đó scrape càng chậm, request metrics càng chiếm tài nguyên và làm việc chẩn đoán khó khăn hơn.

Không phải mọi collection.size() đều có cùng độ phức tạp. Hãy kiểm tra implementation cụ thể. Ví dụ, một số cấu trúc lưu sẵn counter size có thể trả về O(1), trong khi collection concurrent khác phải duyệt. Không suy luận chi phí chỉ từ tên phương thức size().

## Những công việc không nên đặt trong hàm đọc

Hàm đọc Gauge nên có chi phí thấp, không blocking và không gây side effect. Tránh các thao tác sau:

| Thao tác trong hàm đọc | Rủi ro |
|---|---|
| Gọi repository.count() hoặc truy vấn SQL | Dùng connection pool và tải database theo chu kỳ scrape |
| Gọi HTTP/gRPC dependency | Scrape phụ thuộc latency hoặc availability của dịch vụ khác |
| Duyệt collection lớn | Chi phí O(n), tăng theo kích thước dữ liệu |
| Serialize object hoặc tạo snapshot lớn | CPU và allocation tăng trong lúc scrape |
| Chờ synchronized lock | Scrape bị chặn bởi luồng nghiệp vụ đang giữ lock |
| Tính toán nhiều lần cùng một đại lượng | Lặp công việc mà ứng dụng có thể tính trước |
| Ghi log hoặc cập nhật trạng thái | Hàm đọc không còn thuần đọc; nhiều lần scrape tạo side effect lặp lại |
| Lazy load dữ liệu | Lần scrape đầu có thể kích hoạt khởi tạo hoặc I/O không dự kiến |

Ví dụ không nên dùng:

~~~java
Gauge.builder(
    "orders.pending",
    orderRepository,
    repository -> repository.countByStatus("PENDING")
).register(registry);
~~~

Hàm trên biến mỗi lần lấy mẫu thành một truy vấn database. Nếu nhiều instance cùng scrape, truy vấn có thể chạy đồng thời trên toàn cụm. Khi database chậm, endpoint metrics cũng chậm theo.

## Mẫu tốt: cập nhật AtomicInteger theo sự kiện

Nếu cần số lượng tác vụ đang chờ, có thể duy trì một biến đếm được cập nhật khi enqueue và dequeue. Gauge chỉ đọc giá trị atomic:

~~~java
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.Objects;

import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;

public final class WorkerQueue {

    private final ConcurrentLinkedQueue<Runnable> queue =
        new ConcurrentLinkedQueue<>();

    private final AtomicInteger pendingTasks = new AtomicInteger();

    public WorkerQueue(MeterRegistry registry) {
        Gauge.builder(
                "worker.queue.depth",
                pendingTasks,
                AtomicInteger::get
            )
            .description("Số tác vụ đang chờ xử lý, được cập nhật khi enqueue/dequeue")
            .baseUnit("tasks")
            .register(registry);
    }

    public void submit(Runnable task) {
        Objects.requireNonNull(task, "task");
        pendingTasks.incrementAndGet();
        queue.offer(task);
    }

    public Runnable poll() {
        Runnable task = queue.poll();
        if (task != null) {
            pendingTasks.decrementAndGet();
        }
        return task;
    }
}
~~~

Gauge chỉ gọi AtomicInteger.get(), có chi phí O(1) và không phải duyệt queue. Biến đếm được cập nhật theo sự kiện nghiệp vụ, không phải tính lại toàn bộ trạng thái trong lúc scrape.

Ví dụ trên dùng ConcurrentLinkedQueue không giới hạn, nên offer trả true sau khi task đã được kiểm tra khác null. Nếu thay bằng queue có giới hạn, chỉ tăng counter khi enqueue thành công và rollback khi thao tác bị từ chối hoặc gián đoạn. Tất cả đường thêm và lấy task phải đi qua lớp quản lý này; nếu code khác sửa queue trực tiếp, pendingTasks sẽ lệch khỏi trạng thái queue.

Với thao tác concurrent, biến đếm có thể phản ánh một snapshot rất ngắn trước hoặc sau khi queue được cập nhật. Nếu cần tính nhất quán tuyệt đối giữa queue và counter, phải thiết kế đồng bộ hóa cho cả hai thao tác và đo chi phí lock. Với dashboard vận hành, một gauge gần đúng, rẻ và có ngữ nghĩa được mô tả rõ thường hữu ích hơn một phép duyệt đắt tiền trên mỗi lần scrape.

## Mẫu tốt: snapshot cho phép tính hoặc truy vấn tốn kém

Có những giá trị không thể duy trì bằng một phép increment/decrement đơn giản, chẳng hạn số bản ghi đang chờ trong nhiều partition hoặc thống kê được tổng hợp từ nhiều nguồn. Trong trường hợp này, hãy tách việc tính toán khỏi hàm đọc Gauge.

Mô hình gồm ba phần:

1. Một tác vụ riêng làm mới snapshot theo chu kỳ có kiểm soát.
2. Snapshot mới được công bố qua AtomicReference.
3. Gauge chỉ đọc trường đã tính sẵn trong snapshot.

~~~java
import java.util.concurrent.atomic.AtomicReference;
import java.util.concurrent.TimeUnit;

import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;

public final class QueueSnapshotMetrics {

    private static final class Snapshot {
        private final long pending;
        private final long capturedAtNanos;

        private Snapshot(long pending, long capturedAtNanos) {
            this.pending = pending;
            this.capturedAtNanos = capturedAtNanos;
        }
    }

    private final AtomicReference<Snapshot> snapshot =
        new AtomicReference<>(new Snapshot(0, System.nanoTime()));

    public QueueSnapshotMetrics(MeterRegistry registry) {
        Gauge.builder(
                "worker.queue.depth",
                snapshot,
                ref -> ref.get().pending
            )
            .description("Số tác vụ chờ theo snapshot gần nhất")
            .baseUnit("tasks")
            .register(registry);

        Gauge.builder(
                "worker.queue.snapshot.age",
                snapshot,
                ref -> TimeUnit.NANOSECONDS.toSeconds(
                    System.nanoTime() - ref.get().capturedAtNanos
                )
            )
            .description("Tuổi của snapshot queue gần nhất")
            .baseUnit("seconds")
            .register(registry);
    }

    public void refresh(long pendingCount) {
        snapshot.set(new Snapshot(pendingCount, System.nanoTime()));
    }
}
~~~

Một scheduler hoặc luồng nền có thể gọi refresh sau khi đọc dữ liệu nguồn. Gauge không truy cập repository hoặc database; nó chỉ đọc AtomicReference và một object bất biến.

Snapshot có thời điểm tạo để người vận hành biết số liệu cũ đến đâu. Nếu tác vụ refresh thất bại, giữ snapshot thành công gần nhất và tăng một Counter lỗi refresh riêng. Không thay lỗi bằng giá trị 0 vì 0 có thể bị hiểu là queue rỗng.

### Lập lịch refresh có kiểm soát

~~~java
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;

public final class QueueSnapshotRefresher implements AutoCloseable {

    private final ScheduledExecutorService scheduler =
        Executors.newSingleThreadScheduledExecutor();

    private final QueueSnapshotMetrics metrics;
    private final QueueRepository repository;
    private final Counter refreshFailures;

    public QueueSnapshotRefresher(
        QueueSnapshotMetrics metrics,
        QueueRepository repository,
        MeterRegistry registry
    ) {
        this.metrics = metrics;
        this.repository = repository;
        this.refreshFailures = Counter.builder(
                "worker.queue.snapshot.refresh.failures"
            )
            .description("Số lần refresh snapshot queue thất bại")
            .register(registry);
    }

    public void start() {
        scheduler.scheduleWithFixedDelay(
            () -> {
                try {
                    long pending = repository.countPending();
                    metrics.refresh(pending);
                } catch (RuntimeException exception) {
                    refreshFailures.increment();
                }
            },
            0,
            5,
            TimeUnit.SECONDS
        );
    }

    @Override
    public void close() {
        scheduler.shutdown();
    }
}
~~~

Tác vụ refresh chạy trên executor riêng và dùng scheduleWithFixedDelay nên một lần chạy trên scheduler này hoàn tất trước khi lần tiếp theo bắt đầu. Tuy vậy, repository vẫn cần timeout phù hợp. Nếu truy vấn treo vô thời hạn, snapshot sẽ cũ và scheduler không thể làm mới tiếp. Hãy giám sát snapshot age, refresh failures và tình trạng executor.

Không tăng tần suất refresh chỉ để dashboard trông mượt hơn. Chọn chu kỳ theo độ mới dữ liệu mà quyết định vận hành cần. Nếu snapshot có thể trễ 5 giây mà vẫn hữu ích, không cần truy vấn nguồn mỗi 100 ms.

## Giữ strong reference cho đối tượng được Gauge quan sát

Micrometer Gauge thường giữ weak reference tới object được đo để không ngăn garbage collector thu hồi object đó. Nếu ứng dụng không giữ strong reference, object có thể bị GC; Gauge khi đó có thể báo NaN hoặc biến mất tùy registry.

Ví dụ nên giữ state object thành field sống cùng component:

~~~java
public final class PoolMetrics {

    private final AtomicInteger activeConnections = new AtomicInteger();

    public PoolMetrics(MeterRegistry registry) {
        Gauge.builder(
                "db.pool.connections.active",
                activeConnections,
                AtomicInteger::get
            )
            .register(registry);
    }
}
~~~

Trong ví dụ, PoolMetrics giữ tham chiếu mạnh đến AtomicInteger. Nếu tạo một object tạm chỉ để đăng ký Gauge rồi không lưu ở đâu khác, object có thể bị thu hồi sau khi constructor kết thúc.

Không giữ strong reference vào object lớn hoặc vòng đời dài hơn dự kiến chỉ để Gauge hoạt động. Hãy chọn một state object nhỏ, chuyên biệt, có vòng đời rõ ràng. Có thể dùng builder option strongReference khi phiên bản Micrometer hỗ trợ, nhưng giữ object ở field của component thường làm ownership rõ ràng hơn.

## Thread safety của hàm đọc

Hàm đọc Gauge có thể được gọi trong lúc luồng nghiệp vụ đang thay đổi state. Vì vậy, hàm đọc và state object cần có semantics concurrency rõ ràng:

- Dùng AtomicInteger, AtomicLong hoặc AtomicReference cho scalar/snapshot.
- Dùng object snapshot bất biến rồi thay reference một lần khi refresh hoàn tất.
- Tránh đọc một nhóm field mutable rời rạc nếu cần chúng nhất quán với nhau.
- Không giữ lock lâu trong hàm đọc.
- Không dùng một field tạm chung để lưu kết quả tính toán.
- Chấp nhận rõ sai số thời điểm nếu giá trị chỉ mang tính vận hành gần đúng.

Với nhiều giá trị cần nhất quán, một immutable snapshot thường dễ hiểu hơn nhiều atomic riêng lẻ. Ví dụ, snapshot có thể chứa queue depth, active workers và timestamp được tạo cùng một lần; Gauge đọc từng field từ cùng object snapshot.

## Chọn Gauge hay meter tích lũy?

Gauge phù hợp với trạng thái hiện tại. Không nên dùng Gauge để theo dõi số sự kiện tăng mãi theo thời gian.

| Nhu cầu | Meter nên dùng | Lý do |
|---|---|---|
| Số tác vụ đang chờ | Gauge | Trạng thái hiện tại, có thể tăng/giảm |
| Số connection đang mở | Gauge | Trạng thái hiện tại của pool |
| Tổng request đã xử lý | Counter | Cần tích lũy mọi lần xảy ra |
| Tổng lỗi theo loại | Counter | Cần đếm mọi sự kiện lỗi |
| Thời gian xử lý request | Timer | Cần count, total time và phân phối thời lượng |
| Kích thước payload mỗi request | DistributionSummary | Cần tích lũy phân phối các sample |
| Đỉnh queue depth giữa hai lần scrape | Bộ tích lũy cực trị hoặc DistributionSummary | Gauge hiện tại có thể bỏ lỡ đỉnh ngắn |

Nếu yêu cầu là “đã xảy ra bao nhiêu lần”, hãy dùng Counter. Nếu yêu cầu là “hiện có bao nhiêu”, hãy dùng Gauge. Nếu yêu cầu là “giá trị lớn nhất trong một cửa sổ”, hãy duy trì cực trị theo cửa sổ hoặc ghi nhận các quan sát vào meter phân phối phù hợp.

## Tần suất lấy mẫu và freshness

Tăng tần suất scrape làm dữ liệu mới hơn nhưng cũng gọi hàm đọc thường xuyên hơn. Với hàm O(1) đọc AtomicLong, tăng tần suất có thể chấp nhận được trong ngân sách. Với hàm đọc O(n) hoặc I/O, tăng tần suất có thể làm vấn đề nghiêm trọng hơn.

Khi thiết kế chu kỳ, cân nhắc:

- Mức trễ dữ liệu tối đa mà dashboard và alert chấp nhận.
- Số instance và số registry đọc cùng meter.
- Thời gian p95/p99 của endpoint metrics.
- Scrape timeout và scrape interval.
- Export step và thời gian batch gửi đi với push registry.
- Tác động lên CPU, allocation, GC và dependency.
- Tuổi snapshot nếu dùng refresh riêng.

Đừng nhầm scrape interval với chu kỳ cập nhật dữ liệu nguồn. Gauge có thể được đọc mỗi 15 giây nhưng snapshot chỉ được làm mới mỗi 60 giây; lúc đó backend nhận sample mới nhưng giá trị bên trong có thể vẫn cũ. Hãy export thêm snapshot age để phân biệt sample mới với dữ liệu nguồn mới.

## Đo và benchmark chi phí hàm đọc

Để đánh giá hàm đọc, cần đo cả thời gian thực thi và tác động của nó lên luồng thu thập.

Một phép thử đơn giản với SimpleMeterRegistry có thể xác nhận hàm được gọi khi Gauge được đọc:

~~~java
import org.junit.jupiter.api.Test;

import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import static org.junit.jupiter.api.Assertions.assertEquals;

class GaugeSamplingTest {

    @Test
    void samplesStateWhenValueIsRead() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        AtomicLong state = new AtomicLong(42);
        AtomicInteger reads = new AtomicInteger();

        Gauge gauge = Gauge.builder(
                "test.gauge",
                state,
                value -> {
                    reads.incrementAndGet();
                    return value.get();
                }
            )
            .register(registry);

        assertEquals(0, reads.get());

        double first = gauge.value();
        assertEquals(42.0, first, 0.0);
        assertEquals(1, reads.get());

        state.set(99);
        double second = gauge.value();
        assertEquals(99.0, second, 0.0);
        assertEquals(2, reads.get());

        registry.close();
    }
}
~~~

Bài test cho thấy hàm đọc được gọi khi value được lấy, không phải khi state được cập nhật. Trong test thực tế, nên kiểm tra cả giá trị, số lần đọc và việc object state vẫn được giữ sống.

### Benchmark những gì?

Dùng JMH hoặc công cụ benchmark phù hợp để so sánh:

- Hàm đọc atomic O(1).
- Hàm đọc collection size.
- Hàm duyệt collection O(n).
- Hàm đọc snapshot đã tính sẵn.
- Hàm truy vấn nguồn nếu đang đánh giá anti-pattern hiện có.

Đo ở các kích thước collection và mức concurrency gần với production. Thu thập:

| Chỉ số | Mục đích |
|---|---|
| Average và p50 | Chi phí thường gặp |
| p95/p99 | Đuôi latency của hàm đọc |
| Throughput | Số lần lấy mẫu xử lý mỗi giây |
| CPU | Chi phí tính toán |
| Allocation rate | Object được tạo mỗi lần sample |
| GC pause | Tác động của allocation lên ứng dụng |
| Scrape duration | Tác động tổng hợp lên endpoint metrics |
| Scrape failures/timeouts | Mức độ ảnh hưởng tới pipeline giám sát |
| Dependency load | Truy vấn hoặc request phát sinh do lấy mẫu |

Không benchmark chỉ với một queue rỗng. Chi phí O(n) có thể không đáng kể khi n nhỏ nhưng tăng mạnh khi queue đầy. Cũng không chạy benchmark trong production traffic mà không có kế hoạch kiểm soát tác động.

## Kiểm tra trong production

Có thể theo dõi endpoint metrics và scrape duration để phát hiện hàm đọc chậm. Với Prometheus, xem trạng thái target và các metric scrape như scrape duration, sample count, scrape timeout hoặc scrape failure. Nếu endpoint ứng dụng trả chậm, phân tích thread dump hoặc profiler để xác định thread đang ở trong hàm đọc Gauge, đang chờ lock hay đang chờ dependency.

Một số dấu hiệu cần điều tra:

- Thời gian endpoint metrics tăng theo kích thước queue.
- Scrape timeout xuất hiện khi database chậm.
- CPU tăng theo tần suất scrape dù traffic nghiệp vụ không đổi.
- Thread dump cho thấy thread xử lý scrape chờ connection pool hoặc lock.
- Snapshot age tăng trong khi refresh failure cũng tăng.
- Nhiều instance cùng tạo truy vấn định kỳ giống nhau.

Với Prometheus, có thể bắt đầu bằng các truy vấn sau để tìm target có scrape chậm hoặc thất bại:

~~~promql
scrape_duration_seconds{job="checkout"}
up{job="checkout"}
scrape_samples_scraped{job="checkout"}
~~~

scrape_duration_seconds cho biết thời gian scrape target; up bằng 0 cho biết lần scrape gần nhất thất bại. Nếu thời gian scrape tăng cùng kích thước queue hoặc thời điểm database chậm, hãy kiểm tra các hàm Gauge đọc queue/database. Các metric này cho biết hiện tượng ở phía Prometheus; profiler hoặc thread dump của ứng dụng giúp tìm đúng hàm đọc gây chậm.

Không chỉ tăng scrape timeout để che vấn đề. Timeout lớn hơn có thể làm scrape thread bị giữ lâu hơn và khiến lần thu thập chồng lấn nếu hệ thống không giới hạn concurrency. Hãy làm hàm đọc rẻ hơn hoặc tách việc tính toán khỏi đường scrape.

## Checklist thiết kế Gauge an toàn

- [ ] Hàm đọc chỉ lấy một giá trị hiện tại, không thực hiện side effect.
- [ ] Độ phức tạp của hàm đọc đã được xác định.
- [ ] Không có database query, HTTP call hoặc blocking I/O trong hàm đọc.
- [ ] Không duyệt collection lớn nếu có thể duy trì count hoặc snapshot.
- [ ] Không chờ lock có thể bị luồng nghiệp vụ giữ lâu.
- [ ] State object có strong reference và vòng đời rõ ràng.
- [ ] State có semantics thread-safe phù hợp.
- [ ] Sample có thể gần đúng ở thời điểm đọc và sai số được chấp nhận.
- [ ] Nếu dùng snapshot, có metric theo dõi snapshot age và refresh failures.
- [ ] Tần suất scrape/export phù hợp với ngân sách chi phí.
- [ ] Đã benchmark ở kích thước và concurrency gần production.
- [ ] Đã quan sát scrape duration, timeout, CPU và allocation sau triển khai.

## Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Scrape endpoint chậm khi queue lớn | Hàm đọc gọi queue.size() có độ phức tạp O(n) | Duy trì atomic count hoặc snapshot |
| Scrape gây tải database | Gauge gọi repository hoặc SQL trong callback | Refresh dữ liệu riêng và publish snapshot |
| Giá trị Gauge nhảy hoặc không nhất quán | Đọc nhiều field mutable ở các thời điểm khác nhau | Dùng immutable snapshot |
| Gauge báo NaN hoặc biến mất | Object được đo chỉ còn weak reference và đã bị GC | Giữ strong reference trong component |
| Không thấy đỉnh ngắn của queue | Sample thưa và Gauge chỉ báo giá trị tại thời điểm đọc | Dùng bộ tích lũy cực trị hoặc meter phân phối |
| Tăng scrape frequency làm CPU tăng | Hàm đọc đắt được gọi thường xuyên hơn | Giảm chi phí hàm đọc trước khi tăng tần suất |
| Snapshot vẫn có sample nhưng dữ liệu cũ | Refresh task lỗi hoặc bị treo | Export snapshot age và refresh failure |
| Đếm queue depth bị âm hoặc lệch | Một số đường enqueue/dequeue không cập nhật counter | Đóng gói thao tác trong abstraction và kiểm thử concurrency |
| Hàm đọc chờ lock | Lock dùng chung với xử lý nghiệp vụ | Đọc atomic/snapshot, rút ngắn critical section |
| Test không phát hiện hàm đọc chậm | Chỉ kiểm tra giá trị, không đo thời gian hoặc độ phức tạp | Benchmark với dữ liệu lớn và concurrency thực tế |

## Ghi nhớ

- Gauge lấy mẫu giá trị khi registry hoặc reader thu thập; nó không tích lũy các giá trị trung gian.
- Chi phí tổng thể phụ thuộc số Gauge, chi phí hàm đọc, tần suất scrape/export, số instance và số reader.
- Hàm đọc Gauge phải nhanh, không blocking, không side effect và an toàn khi được gọi đồng thời.
- Tránh truy vấn database, HTTP call, duyệt collection lớn hoặc chờ lock trong hàm đọc.
- ConcurrentLinkedQueue.size() là O(n), có thể trả kết quả không chính xác khi queue thay đổi đồng thời.
- Duy trì AtomicInteger/AtomicLong theo sự kiện hoặc publish snapshot bất biến để Gauge chỉ đọc O(1).
- Giữ strong reference tới state object vì Gauge thường dùng weak reference.
- Export snapshot age và refresh failures để nhận biết dữ liệu cũ hoặc nguồn refresh lỗi.
- Dùng Counter cho sự kiện tích lũy, Timer cho thời lượng và Gauge cho trạng thái hiện tại.
- Benchmark cả p95/p99, CPU, allocation, scrape duration và timeout ở quy mô gần production.

Một Gauge tốt không cố gắng tính lại toàn bộ hệ thống mỗi khi backend hỏi dữ liệu. Nó đọc một trạng thái nhỏ, có vòng đời rõ ràng và được cập nhật ở nơi thích hợp. Khi hàm đọc rẻ và snapshot có freshness được theo dõi, metrics có thể phản ánh trạng thái vận hành mà không trở thành một workload mới.

## Tài liệu tham khảo

- [Micrometer: Gauges](https://docs.micrometer.io/micrometer/reference/concepts/gauges.html) — ngữ nghĩa lấy mẫu, giá trị trung gian bị bỏ qua, weak reference và cách đăng ký Gauge.
- [Micrometer: Meters](https://docs.micrometer.io/micrometer/reference/concepts/meters.html) — lựa chọn loại meter theo đại lượng cần đo.
- [Java API: ConcurrentLinkedQueue](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ConcurrentLinkedQueue.html) — size() cần duyệt O(n) và có thể không chính xác khi queue thay đổi đồng thời.
- [Prometheus: Jobs and instances](https://prometheus.io/docs/concepts/jobs_instances/) — scrape target, instance và quan hệ với job.
- [Prometheus configuration](https://prometheus.io/docs/prometheus/latest/configuration/configuration/) — scrape_interval và scrape_timeout.

