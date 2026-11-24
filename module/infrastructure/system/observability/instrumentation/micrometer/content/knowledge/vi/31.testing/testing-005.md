# Kiểm thử Gauge với đối tượng có vòng đời được kiểm soát

Gauge biểu diễn giá trị hiện tại của một đối tượng hoặc trạng thái có thể thay đổi: số phần tử đang chờ trong queue, số kết nối đang mở, kích thước cache hoặc số worker đang hoạt động. Khác với Counter, Gauge không tích lũy tổng số lần sự kiện xảy ra; registry đọc giá trị hiện tại thông qua một hàm khi backend thu thập metrics hoặc khi test truy vấn meter.

Một điểm quan trọng khi kiểm thử Gauge là **vòng đời của đối tượng được quan sát**. Micrometer thường giữ tham chiếu yếu đến đối tượng mà Gauge đọc. Vì vậy, việc đăng ký Gauge không đảm bảo đối tượng đó sống đủ lâu. Nếu đối tượng bị garbage collector thu hồi, Gauge có thể trả về `NaN`. Test cần giữ tham chiếu mạnh đến state object trong suốt thời gian kiểm tra, thay đổi state có kiểm soát và đọc lại giá trị Gauge sau mỗi thay đổi.

Trong module **OBSERVABILITY_INSTRUMENTATION_MICROMETER**, bài này hướng dẫn kiểm thử Gauge bằng `SimpleMeterRegistry`, quản lý object lifetime, quan sát mutable state, đo kích thước collection và queue, kiểm tra registry isolation và tránh các test phụ thuộc vào thời điểm garbage collection.

## 1. Gauge đo giá trị hiện tại

Gauge phù hợp với dữ liệu có thể tăng hoặc giảm theo thời gian:

- Số tác vụ đang chờ trong executor queue.
- Số kết nối hiện đang được pool sử dụng.
- Số entry hiện có trong cache.
- Số request đang xử lý đồng thời.
- Dung lượng hiện tại của một buffer.

Ví dụ một queue có thể tăng khi submit task và giảm khi worker lấy task:

~~~text
Queue size
   ^
  8|              ┌───┐
  6|          ┌───┘   └──┐
  4|      ┌───┘          └──┐
  2|  ┌───┘                 └─
  0|──┴────────────────────────> time
~~~

Gauge trả lời câu hỏi "hiện tại có bao nhiêu phần tử?". Nếu cần tổng số tác vụ đã được submit trong suốt vòng đời ứng dụng, hãy dùng Counter. Nếu cần thời gian một tác vụ chờ hoặc xử lý, dùng Timer.

Không dùng Gauge để mô tả một đại lượng chỉ tăng đơn điệu. Counter và FunctionCounter phù hợp hơn với tổng số sự kiện; Gauge dành cho trạng thái có thể thay đổi theo cả hai chiều.

## 2. Gauge tham chiếu đến object được quan sát

Có thể đăng ký Gauge bằng một object và hàm lấy giá trị:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;

public class QueueMetrics {

    private final AtomicInteger queueDepth = new AtomicInteger();

    public QueueMetrics(MeterRegistry registry) {
        Gauge.builder(
                "worker.queue.depth",
                queueDepth,
                AtomicInteger::get
        ).register(registry);
    }

    public void taskQueued() {
        queueDepth.incrementAndGet();
    }

    public void taskStarted() {
        queueDepth.updateAndGet(value -> Math.max(0, value - 1));
    }
}
~~~

Gauge không chụp một bản sao của giá trị `queueDepth` khi đăng ký. Nó giữ tham chiếu đến object và gọi `AtomicInteger::get` khi đọc giá trị. Vì `queueDepth` là mutable object, mỗi lần đọc có thể nhận được giá trị mới nhất.

Micrometer thường giữ weak reference đến object được quan sát. Trong ví dụ, field `queueDepth` của `QueueMetrics` giữ strong reference nên object tồn tại cùng component. Nếu chỉ tạo object trong một biến local rồi bỏ tham chiếu sau khi đăng ký, object có thể bị garbage collector thu hồi.

## 3. Vì sao test phải giữ strong reference?

Ví dụ sau dễ tạo Gauge không ổn định:

~~~java
void registerGauge(MeterRegistry registry) {
    AtomicInteger depth = new AtomicInteger(3);

    Gauge.builder("worker.queue.depth", depth, AtomicInteger::get)
            .register(registry);
}
~~~

Khi method kết thúc, biến local `depth` không còn được giữ bởi scope bên ngoài. Vì Gauge thường giữ weak reference, object có thể bị thu hồi. Khi đó, đọc Gauge có thể trả `NaN`.

Test đúng cần giữ object trong một biến hoặc field sống đến khi assertion hoàn tất:

~~~java
AtomicInteger depth = new AtomicInteger(3);

Gauge.builder("worker.queue.depth", depth, AtomicInteger::get)
        .register(registry);

assertThat(registry.get("worker.queue.depth")
        .gauge()
        .value()).isEqualTo(3.0);
~~~

Biến `depth` vẫn đang được test giữ strong reference. Điều này làm test có vòng đời rõ ràng và không phụ thuộc vào thời điểm GC.

Không gọi `System.gc()` để ép object biến mất rồi khẳng định Gauge trả `NaN` trong unit test thông thường. JVM không đảm bảo thời điểm chạy GC; test kiểu đó dễ chập chờn giữa các môi trường.

## 4. Dùng SimpleMeterRegistry để kiểm thử không cần backend

`SimpleMeterRegistry` lưu meter trong bộ nhớ và cho phép đọc trực tiếp giá trị, phù hợp với unit test cho instrumentation. Test không cần Prometheus, OTLP Collector hoặc monitoring server.

Ví dụ kiểm tra Gauge phản ánh state sau khi thay đổi:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.concurrent.atomic.AtomicInteger;

import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

class QueueGaugeTest {

    @Test
    void gaugeReadsCurrentMutableValue() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        AtomicInteger depth = new AtomicInteger(2);

        try {
            Gauge.builder("worker.queue.depth", depth, AtomicInteger::get)
                    .register(registry);

            assertThat(registry.get("worker.queue.depth")
                    .gauge()
                    .value()).isEqualTo(2.0);

            depth.set(7);

            assertThat(registry.get("worker.queue.depth")
                    .gauge()
                    .value()).isEqualTo(7.0);

            depth.set(0);

            assertThat(registry.get("worker.queue.depth")
                    .gauge()
                    .value()).isZero();
        }
        finally {
            registry.close();
        }
    }
}
~~~

Test xác nhận ba trạng thái:

1. Giá trị ban đầu là 2.
2. Sau khi state chuyển thành 7, Gauge đọc được 7.
3. Sau khi state về 0, Gauge đọc được 0.

Giá trị Gauge là `double`, do đó assertion có thể so sánh với `2.0` hoặc `7.0`. `SimpleMeterRegistry` không cần đợi một chu kỳ scrape định kỳ; test đọc meter trực tiếp.

## 5. Không dùng boxed immutable value làm state thay đổi

Một lỗi thường gặp là đăng ký Gauge với một giá trị `Integer` hoặc `Long` rồi mong Gauge tự nhận biến local mới:

~~~java
Integer size = 5;

Gauge.builder("cache.size", size, Number::doubleValue)
        .register(registry);

size = 10;
~~~

Phép gán `size = 10` chỉ làm biến local trỏ sang object `Integer` mới. Gauge vẫn tham chiếu object cũ có giá trị 5. Ngoài ra, object cũ có thể bị GC vì Gauge không giữ strong reference.

Hãy dùng một object mutable có vòng đời ổn định:

~~~java
AtomicInteger size = new AtomicInteger(5);

Gauge.builder("cache.size", size, AtomicInteger::get)
        .register(registry);

size.set(10);
~~~

Với dữ liệu cần cập nhật đồng thời từ nhiều thread, ưu tiên `AtomicInteger`, `AtomicLong`, `LongAdder` hoặc cấu trúc concurrent phù hợp. Tránh đọc một field mutable không có cơ chế đồng bộ nếu ứng dụng cập nhật nó đồng thời.

## 6. Kiểm thử kích thước collection và queue

Gauge thường đo trực tiếp một collection hoặc queue:

~~~java
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;

import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;

public class PendingTasksMetrics {

    private final BlockingQueue<Runnable> pendingTasks =
            new LinkedBlockingQueue<>();

    public PendingTasksMetrics(MeterRegistry registry) {
        Gauge.builder(
                "worker.pending.tasks",
                pendingTasks,
                BlockingQueue::size
        ).register(registry);
    }

    public void submit(Runnable task) {
        pendingTasks.add(task);
    }

    public Runnable poll() {
        return pendingTasks.poll();
    }

    public BlockingQueue<Runnable> queue() {
        return pendingTasks;
    }
}
~~~

Test có thể thêm và lấy task khỏi queue rồi đọc Gauge:

~~~java
@Test
void gaugeTracksQueueSize() {
    SimpleMeterRegistry registry = new SimpleMeterRegistry();
    PendingTasksMetrics metrics = new PendingTasksMetrics(registry);

    try {
        metrics.submit(() -> { });
        metrics.submit(() -> { });

        assertThat(registry.get("worker.pending.tasks")
                .gauge()
                .value()).isEqualTo(2.0);

        metrics.poll();

        assertThat(registry.get("worker.pending.tasks")
                .gauge()
                .value()).isEqualTo(1.0);
    }
    finally {
        registry.close();
    }
}
~~~

`PendingTasksMetrics` giữ queue bằng field, nên object queue còn sống khi component còn sống. Test giữ `metrics` trong biến local cho đến khi kiểm tra xong.

Với collection đồng thời thay đổi, `size()` thường là snapshot gần đúng tại thời điểm gọi. Không dùng Gauge để khẳng định một invariant nghiệp vụ cần tính chính xác tuyệt đối trong lúc nhiều thread đang thêm/xóa phần tử.

## 7. Gauge đọc giá trị khi được poll

Gauge không nhận callback mỗi khi object thay đổi. Thay vào đó, registry gọi hàm lấy giá trị khi meter được đọc hoặc khi registry export metrics.

Ví dụ:

~~~java
AtomicInteger activeRequests = new AtomicInteger();

Gauge.builder(
        "http.server.active.requests",
        activeRequests,
        AtomicInteger::get
).register(registry);
~~~

Khi request bắt đầu, ứng dụng tăng `activeRequests`; khi request kết thúc, ứng dụng giảm. Gauge sẽ phản ánh state ở lần đọc tiếp theo.

Vì vậy:

- Thay đổi state không tự tạo một sample ngay lập tức.
- Nếu không có scrape hoặc lần đọc meter, backend chưa thấy giá trị mới.
- Nếu state đổi nhiều lần giữa hai lần scrape, backend chỉ nhận giá trị ở lần quan sát tiếp theo; các giá trị trung gian không được lưu lại.
- Một scrape có thể đọc state ở thời điểm hơi khác so với thời điểm test vừa cập nhật.
- Với unit test dùng SimpleMeterRegistry, đọc trực tiếp `gauge().value()` để kiểm tra đồng bộ.

Không viết test kiểu "đợi 1 giây rồi hy vọng scrape đã chạy" khi đang kiểm tra logic Gauge. Hãy đọc meter trực tiếp ở unit test; dùng integration test riêng khi cần xác minh endpoint export.

## 8. Đăng ký Gauge một lần và giữ object ổn định

Gauge nên được đăng ký khi component hoặc meter owner được khởi tạo, sau đó object state được cập nhật trong suốt vòng đời component.

Không nên tạo Gauge mỗi lần xử lý request:

~~~java
public void handleRequest(MeterRegistry registry) {
    AtomicInteger active = new AtomicInteger(1);

    Gauge.builder("request.active", active, AtomicInteger::get)
            .register(registry);
}
~~~

Mỗi lần gọi method có thể tạo một object mới nhưng cùng tên và tag. Registry không tạo một Gauge độc lập cho từng request như cách code có thể tưởng; meter identity vẫn là name + tags, và đăng ký trùng có thể trả về meter đã tồn tại. Function của lần đăng ký đầu tiên tiếp tục được dùng, trong khi object mới không phải object mà Gauge đang quan sát.

Cách đúng là dùng một state object ổn định cho một đại lượng tổng hợp:

~~~java
public class RequestMetrics {
    private final AtomicInteger active = new AtomicInteger();

    public RequestMetrics(MeterRegistry registry) {
        Gauge.builder("request.active", active, AtomicInteger::get)
                .register(registry);
    }

    public void requestStarted() {
        active.incrementAndGet();
    }

    public void requestFinished() {
        active.decrementAndGet();
    }
}
~~~

Một Gauge đại diện số request đang hoạt động của component, không đại diện một Gauge mới cho mỗi request.

## 9. Nếu đối tượng được thay thế, Gauge vẫn trỏ đến object cũ

Giả sử component thay một queue bằng queue mới:

~~~java
private BlockingQueue<Runnable> queue = new LinkedBlockingQueue<>();

public void replaceQueue() {
    queue = new LinkedBlockingQueue<>();
}
~~~

Nếu Gauge được đăng ký trực tiếp với object queue ban đầu, phép gán `queue = ...` không tự đổi object mà Gauge đang quan sát. Gauge tiếp tục tham chiếu yếu đến queue ban đầu.

Nếu state object cần được thay thế, có thể dùng một holder ổn định như `AtomicReference`:

~~~java
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.atomic.AtomicReference;

import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;

public class ReplaceableQueueMetrics {

    private final AtomicReference<BlockingQueue<Runnable>> currentQueue =
            new AtomicReference<>(new LinkedBlockingQueue<>());

    public ReplaceableQueueMetrics(MeterRegistry registry) {
        Gauge.builder(
                "worker.queue.size",
                currentQueue,
                reference -> reference.get().size()
        ).register(registry);
    }

    public void replaceQueue() {
        currentQueue.set(new LinkedBlockingQueue<>());
    }

    public BlockingQueue<Runnable> currentQueue() {
        return currentQueue.get();
    }
}
~~~

Gauge giữ weak reference đến `AtomicReference` ổn định; component giữ strong reference đến holder. Mỗi lần đọc, hàm lấy queue hiện tại từ holder. Khi thay queue, Gauge tự đọc object mới mà không cần đăng ký meter lần nữa.

Test cần giữ `ReplaceableQueueMetrics` sống và kiểm tra trước/sau khi thay queue.

## 10. Kiểm thử object lifetime mà không phụ thuộc GC

Unit test nên kiểm tra contract mà ứng dụng kiểm soát được:

- Component giữ state object bằng field.
- Gauge được đăng ký một lần.
- State được cập nhật.
- Gauge đọc lại đúng giá trị.
- Khi thay state, holder ổn định trỏ đến state mới.
- Registry được đóng hoặc meter được loại bỏ khi fixture kết thúc.

Không nên dựa vào `System.gc()`, `Thread.sleep()` hoặc kiểm tra thời gian object bị thu hồi. GC là hoạt động do JVM quyết định; việc gọi `System.gc()` chỉ là gợi ý và không bảo đảm object bị thu hồi ngay.

Nếu cần kiểm tra hành vi khi owner kết thúc, hãy kiểm thử ở mức lifecycle của component hoặc integration test với context đóng/mở. Không dùng một assertion dựa vào NaN ngay sau khi bỏ biến local vì compiler/JIT và GC có thể làm thời điểm thu hồi thay đổi.

## 11. Kiểm thử registry isolation và meter identity

MeterRegistry giữ meter đã đăng ký. Nếu dùng chung một registry cho nhiều test, meter từ test trước có thể làm test sau đọc nhầm state hoặc gặp meter identity đã tồn tại.

Nên tạo registry mới cho từng test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class CacheGaugeTest {

    private SimpleMeterRegistry registry;

    @BeforeEach
    void setUp() {
        registry = new SimpleMeterRegistry();
    }

    @AfterEach
    void tearDown() {
        registry.close();
    }

    @Test
    void readsCacheEntryCount() {
        Map<String, String> cache = new ConcurrentHashMap<>();

        Gauge.builder("cache.entries", cache, Map::size)
                .register(registry);

        cache.put("a", "one");
        cache.put("b", "two");

        assertThat(registry.get("cache.entries")
                .gauge()
                .value()).isEqualTo(2.0);
    }
}
~~~

Mỗi test có registry riêng nên không bị ảnh hưởng bởi meter cùng tên từ test khác. Nếu cần test nhiều meter có cùng tên nhưng tag khác nhau, hãy khai báo tag rõ ràng và truy vấn đúng tag set.

Nếu hai Gauge có cùng name và tag trong cùng registry, registry coi chúng có cùng meter identity. Đừng kỳ vọng đăng ký lần thứ hai sẽ thay thế function hoặc object mà Gauge đầu tiên đang quan sát.

## 12. Kiểm thử function gauge cho cache hoặc pool

Function gauge phù hợp khi object đã có API đọc trạng thái:

~~~java
Map<String, Object> cache = new ConcurrentHashMap<>();

Gauge.builder("cache.entries", cache, Map::size)
        .description("Current number of entries in cache")
        .register(registry);
~~~

Test:

~~~java
cache.put("customer-1", new Object());
cache.put("customer-2", new Object());

assertThat(registry.get("cache.entries")
        .gauge()
        .value()).isEqualTo(2.0);

cache.remove("customer-1");

assertThat(registry.get("cache.entries")
        .gauge()
        .value()).isEqualTo(1.0);
~~~

Hàm đọc Gauge nên nhẹ và nhanh. Không thực hiện truy vấn database, gọi HTTP hoặc quét một cấu trúc dữ liệu rất lớn mỗi lần scrape. Nếu giá trị cần tính toán tốn kém, cập nhật một state snapshot bằng tác vụ riêng rồi để Gauge đọc snapshot đó.

Với cache có API `estimatedSize()` hoặc pool có API `getActiveCount()`, có thể dùng trực tiếp nếu hàm đọc an toàn và đủ nhẹ. Kiểm tra semantics của API; một số giá trị là ước lượng hoặc snapshot nhất thời.

## 13. Test nhiều trạng thái của queue bằng một kịch bản có thể lặp lại

Một test tốt không chỉ kiểm tra một giá trị ban đầu. Hãy tạo các chuyển trạng thái rõ ràng:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;

import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

class QueueGaugeLifecycleTest {

    @Test
    void gaugeTracksQueueLifecycle() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        BlockingQueue<String> queue = new LinkedBlockingQueue<>();

        try {
            Gauge.builder("worker.queue.size", queue, BlockingQueue::size)
                    .register(registry);

            assertQueueSize(registry, 0);

            queue.add("task-1");
            assertQueueSize(registry, 1);

            queue.add("task-2");
            assertQueueSize(registry, 2);

            queue.poll();
            assertQueueSize(registry, 1);

            queue.clear();
            assertQueueSize(registry, 0);
        }
        finally {
            registry.close();
        }
    }

    private void assertQueueSize(
            MeterRegistry registry,
            double expected) {
        assertThat(registry.get("worker.queue.size")
                .gauge()
                .value()).isEqualTo(expected);
    }
}
~~~

Test này không dùng thread hoặc sleep nên kết quả lặp lại được. Nếu cần kiểm tra trạng thái queue trong executor thực tế, dùng `CountDownLatch` để giữ task đang chạy và đặt task khác vào queue; tránh dựa vào timing ngẫu nhiên.

## 14. Kiểm thử concurrent update

Trong ứng dụng thật, nhiều thread có thể cập nhật state cùng lúc. Hãy dùng cấu trúc thread-safe:

~~~java
LongAdder completedInWindow = new LongAdder();

Gauge.builder(
        "worker.completed.in.window",
        completedInWindow,
        LongAdder::sum
).register(registry);
~~~

Tuy nhiên, nếu `completedInWindow` chỉ tăng và biểu diễn tổng số công việc đã hoàn tất, Counter thường phù hợp hơn. Gauge chỉ nên dùng khi giá trị có thể được reset hoặc thay đổi theo một cửa sổ trạng thái có ý nghĩa.

Với test concurrent, không nên assert một giá trị trung gian trong lúc worker vẫn đang cập nhật. Dùng `CountDownLatch` hoặc `Future.get()` để đợi tất cả task hoàn tất, rồi đọc Gauge. Điều đó giúp test xác nhận một trạng thái ổn định.

## 15. Khi Gauge trả NaN hoặc giá trị không như mong đợi

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Gauge trả NaN | Object được quan sát đã bị GC | Kiểm tra strong reference ở component/test |
| Gauge luôn giữ giá trị cũ | Dùng boxed immutable value hoặc đăng ký với object cũ | Dùng AtomicInteger/holder ổn định |
| Gauge không thay đổi khi collection thay đổi | Function đọc nhầm object hoặc meter identity bị đăng ký trước | Kiểm tra object truyền vào builder |
| Gauge không xuất hiện | Meter bị MeterFilter deny hoặc registry chưa nhận meter | Kiểm tra registry và filter |
| Test đọc nhầm state | Dùng registry chung giữa nhiều test hoặc meter name/tag trùng | Tạo registry mới cho mỗi test |
| Gauge trả số liệu chập chờn | State bị nhiều thread cập nhật không đồng bộ hoặc API trả snapshot gần đúng | Dùng atomic/concurrent state và hiểu semantics |
| Gauge tạo meter trùng lặp | Đăng ký nhiều lần với cùng name/tag | Bind một lần trong lifecycle component |

Nếu Gauge trả NaN trong production, đừng chỉ đổi sang strong reference ngay. Trước hết xác định object nào đang bị quan sát và component nào phải sở hữu object đó. Giữ strong reference đúng nơi giúp lifecycle rõ ràng; giữ quá nhiều object không cần thiết có thể gây memory retention.

## 16. Kiểm tra Gauge qua endpoint export

Unit test với SimpleMeterRegistry xác nhận logic đọc state. Nếu muốn xác minh endpoint Prometheus hoặc registry khác, cần một integration test riêng:

1. Tạo ứng dụng context với registry/exporter tương ứng.
2. Đăng ký Gauge bằng một state object được component giữ.
3. Thay đổi state qua API hoặc test fixture.
4. Gọi endpoint metrics.
5. Kiểm tra sample có tên và tag mong đợi, cùng giá trị mới.
6. Đóng context sau test để dọn executor, registry và các tài nguyên liên quan.

Không dùng một test unit SimpleMeterRegistry để kết luận Prometheus exposition đã đúng. Registry cụ thể có thể chuẩn hóa tên, thêm suffix hoặc biểu diễn Gauge theo quy ước riêng.

## 17. Checklist kiểm thử Gauge

Trước khi chấp nhận một Gauge trong production, xác nhận:

- Gauge đại diện một trạng thái có thể tăng và giảm.
- Đối tượng được quan sát có owner giữ strong reference trong thời gian cần thiết.
- Gauge được đăng ký một lần với name/tag ổn định.
- State mutable dùng atomic hoặc concurrent structure phù hợp.
- Test giữ object trong scope và kiểm tra nhiều giá trị sau mutation.
- Không dùng boxed immutable value để mong Gauge tự theo dõi phép gán mới.
- Không dùng `System.gc()` hoặc `Thread.sleep()` để đồng bộ test.
- Test tạo registry riêng và đóng registry sau khi chạy.
- Nếu object có thể thay thế, Gauge đọc qua holder ổn định.
- Hàm đọc Gauge nhẹ, không gọi I/O hoặc tính toán tốn kém.
- Đã phân biệt số liệu snapshot của Gauge với tổng sự kiện của Counter.
- Có integration test riêng nếu cần xác minh endpoint export.

Gauge kiểm thử ổn định khi test kiểm soát được cả state và vòng đời object. Giữ strong reference đến đối tượng được quan sát, dùng mutable state có cơ chế đồng bộ, đăng ký meter một lần và đọc lại giá trị sau từng thay đổi sẽ giúp xác nhận Gauge phản ánh đúng trạng thái. Tránh phụ thuộc vào GC hoặc timing ngẫu nhiên; dùng `SimpleMeterRegistry` cho unit test và integration test riêng cho endpoint export.

## Tài liệu tham khảo

- [Micrometer - Gauges](https://docs.micrometer.io/micrometer/reference/concepts/gauges.html)
- [Micrometer - MeterRegistry](https://docs.micrometer.io/micrometer/reference/concepts/registry.html)
- [Micrometer - Installing and using the in-memory registry](https://docs.micrometer.io/micrometer/reference/installing.html)
- [Micrometer - Gauge API](https://javadoc.io/doc/io.micrometer/micrometer-core/latest/io/micrometer/core/instrument/Gauge.html)
