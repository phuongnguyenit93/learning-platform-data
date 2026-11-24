# Độ an toàn luồng của meter và của đối tượng chứa trạng thái nguồn

Trong ứng dụng Java nhiều luồng, nhiều request hoặc worker có thể cập nhật cùng một meter Micrometer tại một thời điểm. Các implementation meter chuẩn của Micrometer được thiết kế để nhận bản ghi đồng thời; tuy nhiên, điều đó không tự làm cho đối tượng nguồn mà Gauge hoặc function-tracking meter đọc trở nên an toàn luồng.

Cần phân biệt hai trách nhiệm: **meter** chịu trách nhiệm ghi nhận hoặc công bố số đo; **source state** là đối tượng chứa trạng thái thực tế mà meter đọc. `Counter.increment()` hay `Timer.record()` có thể được gọi đồng thời an toàn, nhưng nếu Gauge đọc một `int` đang bị nhiều thread cập nhật bằng phép `++`, giá trị vẫn có thể mất cập nhật hoặc không có visibility đúng. Hãy thiết kế source state bằng primitive đồng bộ phù hợp như `AtomicInteger`, `AtomicLong`, `LongAdder`, `volatile` cho trường hợp chỉ cần công bố một giá trị, hoặc immutable snapshot được thay thế nguyên tử.

Trong module `OBSERVABILITY_INSTRUMENTATION_MICROMETER`, mục tiêu là sử dụng Micrometer để đo lường ứng dụng Java bằng counter, gauge, timer, distribution summary và nhãn có kiểm soát; tích hợp Spring Boot, xuất metrics đến hệ giám sát, kiểm soát cardinality, kiểm thử instrumentation và diễn giải số đo vận hành. Độ an toàn luồng quyết định liệu các phép đo đó còn phản ánh đúng khi nhiều request hoặc worker cùng hoạt động; đặc biệt, source object của Gauge và function meter phải cung cấp trạng thái có thể đọc đồng thời an toàn.

## 1. Hai lớp thread safety cần kiểm tra

Một meter có thể thread-safe trong khi nguồn dữ liệu của nó không thread-safe. Ví dụ, `Gauge` có thể gọi hàm đọc giá trị từ nhiều thread scrape cùng lúc; nếu hàm đó đọc một `ArrayList` đang bị sửa đồng thời mà không đồng bộ, ứng dụng vẫn có thể gặp race condition.

| Lớp | Đối tượng | Trách nhiệm |
| --- | --- | --- |
| Meter | `Counter`, `Timer`, `DistributionSummary`, `Gauge` và implementation tương ứng | Nhận bản ghi đồng thời hoặc đọc giá trị theo hợp đồng của meter. |
| Registry | `MeterRegistry` và các meter đã đăng ký | Quản lý danh tính meter và truy cập meter trong ứng dụng nhiều luồng. |
| Source state | `AtomicInteger`, queue, pool, object nghiệp vụ hoặc state holder được Gauge đọc | Bảo đảm cập nhật, visibility và đọc trạng thái đúng theo semantics nghiệp vụ. |
| Callback | Hàm đọc Gauge, FunctionCounter hoặc FunctionTimer | An toàn khi được gọi đồng thời, nhanh, không block và không có side effect. |

Đừng suy luận rằng `Gauge` thread-safe có nghĩa mọi object mà nó quan sát cũng thread-safe. Meter chỉ gọi hàm đọc; đồng bộ hóa trạng thái nguồn là trách nhiệm của ứng dụng hoặc của implementation nguồn.

## 2. Các meter chuẩn hỗ trợ ghi nhận đồng thời

Trong các implementation Micrometer thông dụng, những thao tác ghi nhận như `Counter.increment()`, `Timer.record(...)` và `DistributionSummary.record(...)` được thiết kế để nhiều thread cùng cập nhật. Vì vậy, có thể chia sẻ một meter đã đăng ký cho nhiều request hoặc worker thay vì tạo meter riêng cho từng thread.

Ví dụ:

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.util.concurrent.TimeUnit;

public final class RequestMetrics {
    private final Counter requests;
    private final Timer duration;

    public RequestMetrics(MeterRegistry registry) {
        this.requests = Counter.builder("app.requests.completed")
                .register(registry);
        this.duration = Timer.builder("app.request.duration")
                .register(registry);
    }

    public void record(long elapsedNanos) {
        requests.increment();
        duration.record(elapsedNanos, TimeUnit.NANOSECONDS);
    }
}
```

Một instance `RequestMetrics` có thể được inject vào nhiều service hoặc worker. Mỗi thread gọi `record()` trên cùng meter. Không cần đặt `synchronized` quanh mỗi lần `increment()` hoặc `record()` chỉ để bảo vệ meter chuẩn.

### 2.1. An toàn của từng thao tác không tạo thành giao dịch nhiều meter

Hai lời gọi riêng biệt như `requests.increment()` và `duration.record(...)` đều an toàn khi gọi đồng thời, nhưng không tạo thành một giao dịch nguyên tử chung. Một scrape có thể xảy ra giữa hai lần cập nhật và quan sát count mới nhưng timer count chưa cập nhật, hoặc ngược lại tùy thứ tự.

Nếu cần duy trì một invariant chặt chẽ giữa nhiều trường trạng thái, hãy quản lý invariant trong source state bằng atomic operation hoặc lock phù hợp. Metrics thường là dữ liệu quan sát gần thời gian thực; không dùng snapshot metrics làm nguồn sự thật cho logic nghiệp vụ hoặc quyết định giao dịch.

## 3. Chia sẻ meter thay vì tạo meter theo request

Meter được nhận diện bằng tên và tập tag. Khi nhiều thread đăng ký cùng một meter identity trên cùng registry, registry trả về meter tương ứng với identity đó; các call site có thể cùng ghi vào một meter. Vì vậy, hãy đăng ký meter một lần trong constructor/bean cấu hình và tái sử dụng.

```java
@Component
public class PaymentMetrics {
    private final Counter authorized;

    public PaymentMetrics(MeterRegistry registry) {
        this.authorized = Counter.builder("shop.payment.authorized")
                .tag("channel", "web")
                .register(registry);
    }

    public void recordAuthorized() {
        authorized.increment();
    }
}
```

Không tạo meter mới cho mỗi request, mỗi thread hoặc mỗi task. Việc đó làm tăng chi phí đăng ký, tạo thêm object và dễ dẫn đến cardinality cao nếu tag chứa dữ liệu động. Nếu cần phân loại, dùng tập tag value hữu hạn và ổn định.

## 4. Gauge đọc trạng thái nguồn chứ không lưu trạng thái thay ứng dụng

Gauge lấy giá trị từ một object hoặc hàm đọc tại thời điểm registry/backend lấy mẫu. Nó không tự quản lý cập nhật của object nguồn và cũng không lưu lịch sử từng thay đổi.

Ví dụ đăng ký Gauge đọc số tác vụ đang hoạt động:

```java
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import java.util.concurrent.atomic.AtomicInteger;

public final class WorkerState {
    private final AtomicInteger active = new AtomicInteger();

    public WorkerState(MeterRegistry registry) {
        Gauge.builder("app.worker.active", active, AtomicInteger::get)
                .description("Number of tasks currently executing")
                .register(registry);
    }

    public void started() {
        active.incrementAndGet();
    }

    public void finished() {
        active.decrementAndGet();
    }
}
```

`AtomicInteger` đảm bảo phép tăng/giảm được thực hiện nguyên tử. Gauge chỉ đọc giá trị bằng `get()`. Nếu nhiều worker cùng bắt đầu và kết thúc task, không có phép `++` hoặc `--` không an toàn trên biến thường.

## 5. Vì sao int hoặc long thông thường có thể mất cập nhật?

Phép `count++` không phải một thao tác nguyên tử. Nó gồm đọc giá trị, cộng một rồi ghi lại. Hai thread có thể cùng đọc một giá trị và cùng ghi kết quả giống nhau, khiến một lần tăng bị mất.

```java
// Không an toàn nếu nhiều thread cùng gọi.
private int active;

public void started() {
    active++;
}
```

Thêm `volatile` không giải quyết được vấn đề này:

```java
// Có visibility tốt hơn nhưng active++ vẫn không nguyên tử.
private volatile int active;
```

`volatile` đảm bảo visibility và một số quy tắc ordering cho lần đọc/ghi trường đó; nó không biến chuỗi read-modify-write thành một thao tác nguyên tử. Với bộ đếm tăng/giảm đồng thời, dùng `AtomicInteger`, `AtomicLong`, `LongAdder` hoặc lock tùy semantics.

## 6. Chọn AtomicInteger, AtomicLong, LongAdder hay volatile

Không có một primitive phù hợp cho mọi loại state. Hãy chọn theo loại thao tác và mức nhất quán cần có.

| Cơ chế | Phù hợp khi | Lưu ý |
| --- | --- | --- |
| `AtomicInteger` / `AtomicLong` | Cần tăng/giảm nguyên tử hoặc cập nhật một giá trị số duy nhất | Các thao tác CAS an toàn luồng; tranh chấp cao có thể gây contention. |
| `LongAdder` | Nhiều thread cộng dồn một số đếm với contention cao | `sum()` là snapshot gần đúng khi còn cập nhật đồng thời, không dùng làm phép kiểm tra invariant chính xác. |
| `volatile` | Một thread ghi giá trị, nhiều thread đọc; không cần read-modify-write nguyên tử | Không dùng cho `++`, `--` hoặc invariant nhiều trường. |
| `synchronized` / `Lock` | Cần cập nhật nhiều trường như một thao tác nhất quán | Giữ critical section ngắn; callback Gauge không nên chờ lock lâu. |
| `AtomicReference` | Cần thay thế một trạng thái hoặc immutable snapshot như một đơn vị | Dùng `getAndSet`/`updateAndGet` để publish snapshot nguyên tử. |

Với trạng thái số lượng active task, `AtomicInteger` thường dễ hiểu. Với một bộ đếm sự kiện nội bộ có tần suất cập nhật rất cao và chỉ cần tổng gần nhất quán, `LongAdder` có thể giảm contention. Nếu đã có `Counter` Micrometer cho sự kiện, hãy dùng Counter để đo sự kiện thay vì tạo một Gauge đếm tích lũy không đúng semantics.

## 7. LongAdder phù hợp với phép cộng dồn có contention cao

`LongAdder` phân tán cập nhật qua nhiều cell để giảm tranh chấp giữa thread. Khi cần đọc tổng, gọi `sum()`:

```java
import java.util.concurrent.atomic.LongAdder;

public final class EventState {
    private final LongAdder accepted = new LongAdder();

    public void accepted() {
        accepted.increment();
    }

    public long acceptedCount() {
        return accepted.sum();
    }
}
```

Có thể đăng ký một FunctionCounter đọc tổng tích lũy từ state này nếu cần theo dõi một bộ đếm do ứng dụng quản lý:

```java
FunctionCounter.builder(
        "app.events.accepted",
        eventState,
        state -> state.acceptedCount()
).register(registry);
```

FunctionCounter đọc giá trị từ đối tượng nguồn; nó không tăng giá trị thay cho ứng dụng. Nguồn phải là một tổng tích lũy không giảm theo semantics counter. Nếu `LongAdder.sum()` được đọc trong lúc các thread vẫn cập nhật, kết quả có thể không đại diện một snapshot nguyên tử tại đúng một thời điểm. Đây thường là đặc tính chấp nhận được cho metrics quan sát, nhưng không dùng giá trị đó làm quyết định đồng bộ hóa hoặc kiểm soát nghiệp vụ chính xác.

## 8. Dùng AtomicReference để công bố nhiều trường nhất quán

Nếu Gauge cần đọc nhiều trường có quan hệ với nhau, dùng một immutable snapshot và thay thế snapshot qua `AtomicReference`. Cách này giúp reader nhìn thấy một phiên bản state nhất quán thay vì đọc các trường đang thay đổi độc lập.

```java
import java.util.concurrent.atomic.AtomicReference;

public final class PoolSnapshot {
    private final int active;
    private final int queued;
    private final long completed;

    public PoolSnapshot(int active, int queued, long completed) {
        this.active = active;
        this.queued = queued;
        this.completed = completed;
    }

    public int active() { return active; }
    public int queued() { return queued; }
    public long completed() { return completed; }
}

public final class PoolState {
    private final AtomicReference<PoolSnapshot> current =
            new AtomicReference<>(new PoolSnapshot(0, 0, 0));

    public PoolSnapshot snapshot() {
        return current.get();
    }

    public void publish(PoolSnapshot next) {
        current.set(next);
    }
}
```

Gauge có thể đọc một trường từ snapshot:

```java
Gauge.builder("app.pool.active", poolState,
        state -> state.snapshot().active())
        .register(registry);
```

Producer phải tự tính snapshot mới từ nguồn dữ liệu nhất quán rồi publish. `AtomicReference.set()` công bố một object immutable; reader không thấy object bị sửa từng trường sau khi publish. Nếu nhiều producer cùng tính snapshot, cần đảm bảo phép tính và cập nhật không ghi đè mất thay đổi của nhau; có thể dùng `updateAndGet(...)` hoặc một lock quanh quá trình tổng hợp.

## 9. Giữ source object sống trong suốt vòng đời Gauge

Micrometer Gauge thường giữ weak reference đến object nguồn để meter không ngăn object được garbage-collect. Điều này có nghĩa nếu ứng dụng chỉ truyền một object tạm thời vào `Gauge.builder(...)` mà không giữ strong reference ở nơi khác, object có thể bị thu gom và Gauge không còn đọc được giá trị hữu ích.

Ví dụ không an toàn về lifecycle:

```java
Gauge.builder("app.queue.depth",
        new QueueState(),
        QueueState::depth)
    .register(registry);
```

Nếu không có tham chiếu mạnh nào khác giữ `QueueState`, object có thể bị garbage-collect. Hãy giữ state object trong field của bean hoặc trong thành phần sở hữu vòng đời tương ứng:

```java
@Component
public class QueueMetrics {
    private final QueueState queueState = new QueueState();

    public QueueMetrics(MeterRegistry registry) {
        Gauge.builder("app.queue.depth", queueState, QueueState::depth)
                .register(registry);
    }

    public QueueState state() {
        return queueState;
    }
}
```

Strong reference đảm bảo object còn sống; nó không tự đảm bảo thread safety. `QueueState.depth()` và các thao tác cập nhật bên trong vẫn phải được thiết kế an toàn khi chạy đồng thời.

## 10. Gauge callback phải nhanh và an toàn khi được gọi đồng thời

Gauge callback có thể được gọi từ thread scrape hoặc thread đọc registry. Không nên giả định callback chỉ chạy một lần hoặc chạy trên thread nghiệp vụ. Callback nên đọc một giá trị sẵn có, không làm thay đổi state.

Một callback phù hợp:

```java
Gauge.builder("app.worker.active", activeTasks, AtomicInteger::get)
        .register(registry);
```

Một callback không phù hợp:

```java
// Không gọi database hoặc dịch vụ ngoài trong lúc scrape.
Gauge.builder("app.inventory.remote", inventoryClient,
        client -> client.fetchCurrentStock())
        .register(registry);
```

Callback chậm hoặc block có thể kéo dài scrape, làm nhiều scrape chồng lấn và ảnh hưởng luồng vận hành. Nếu cần lấy dữ liệu từ nguồn ngoài, hãy cập nhật cache/state nền theo chu kỳ riêng rồi để Gauge đọc snapshot trong bộ nhớ.

Không tăng counter, sửa queue hoặc phát event bên trong callback Gauge. Backend có thể đọc Gauge nhiều lần; side effect sẽ khiến kết quả phụ thuộc số lần scrape thay vì sự kiện nghiệp vụ thực tế.

## 11. Source state có thể dùng collection concurrent

Nếu Gauge đọc trạng thái của collection, hãy dùng collection phù hợp với kiểu truy cập đồng thời:

- `ConcurrentLinkedQueue` cho queue không giới hạn theo mô hình concurrent.
- `BlockingQueue` như `ArrayBlockingQueue` hoặc `LinkedBlockingQueue` khi cần producer/consumer và capacity.
- `ConcurrentHashMap` cho map truy cập đồng thời.
- `CopyOnWriteArrayList` khi đọc rất nhiều và cập nhật ít.

Tuy nhiên, collection concurrent chỉ bảo vệ các thao tác theo hợp đồng của nó. Một chuỗi nhiều thao tác như kiểm tra size rồi thêm phần tử vẫn có thể race nếu không được gộp bằng API nguyên tử phù hợp hoặc lock.

Một số `size()` trên collection concurrent có thể là snapshot tạm thời khi có cập nhật đồng thời. Điều đó thường đủ cho Gauge vận hành, nhưng không dùng giá trị Gauge làm phép kiểm tra chính xác để quyết định có được nhận thêm công việc hay không. Quyết định admission phải dựa trên API queue/executor có semantics đồng bộ rõ ràng.

## 12. Không dùng Gauge thay cho Counter hoặc Timer

Chọn meter theo semantics của đại lượng:

| Nhu cầu | Meter phù hợp | Vì sao |
| --- | --- | --- |
| Tổng số request đã hoàn tất | `Counter` | Giá trị tích lũy tăng theo sự kiện. |
| Số task đang chạy tại thời điểm đọc | `Gauge` | Trạng thái có thể tăng và giảm. |
| Thời gian chạy task | `Timer` | Ghi count, total time và phân phối thời lượng nếu cấu hình. |
| Kích thước payload | `DistributionSummary` | Ghi phân phối của một đại lượng số. |
| Tổng tích lũy từ object khác | `FunctionCounter` | Đọc một nguồn counter bên ngoài. |

Không dùng Gauge để tăng một biến đếm sự kiện rồi kỳ vọng backend xử lý reset giống Counter. Không dùng Counter cho số lượng active vì giá trị cần tăng khi bắt đầu và giảm khi kết thúc; đó là trạng thái Gauge.

## 13. Kết hợp Gauge, Counter và Timer trong một state holder

Ví dụ dưới đây theo dõi tác vụ đang chạy, số tác vụ thành công/thất bại và thời gian thực thi. Meter được đăng ký một lần; `AtomicInteger` bảo vệ trạng thái active; mọi task cập nhật qua một method dùng chung.

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.stereotype.Component;

@Component
public class WorkerMetrics {
    private final AtomicInteger active = new AtomicInteger();
    private final Counter succeeded;
    private final Counter failed;
    private final Timer execution;

    public WorkerMetrics(MeterRegistry registry) {
        Gauge.builder("app.worker.active", active, AtomicInteger::get)
                .description("Tasks currently executing")
                .register(registry);

        this.succeeded = Counter.builder("app.worker.completed")
                .tag("result", "success")
                .register(registry);
        this.failed = Counter.builder("app.worker.completed")
                .tag("result", "error")
                .register(registry);
        this.execution = Timer.builder("app.worker.execution")
                .description("Task execution duration")
                .register(registry);
    }

    public void execute(Runnable task) {
        active.incrementAndGet();
        long started = System.nanoTime();
        try {
            task.run();
            succeeded.increment();
        } catch (RuntimeException | Error error) {
            failed.increment();
            throw error;
        } finally {
            execution.record(System.nanoTime() - started,
                    TimeUnit.NANOSECONDS);
            active.decrementAndGet();
        }
    }
}
```

`active` luôn được giảm trong `finally`, kể cả khi task ném exception. Timer cũng ghi nhận thời gian của cả task thành công và thất bại. Hai Counter có cùng tên nhưng tag `result` khác nhau nên là hai meter identity khác nhau với cardinality cố định.

Đoạn code này giả định `execute()` được gọi khi task thực sự bắt đầu chạy. Nếu muốn đo queue wait, hãy instrument tại điểm submit và điểm worker bắt đầu riêng. Nếu `task` có thể bị từ chối trước khi `execute()` được gọi, cần đếm rejection ở lớp submitter.

## 14. Function meter cũng phụ thuộc thread safety của nguồn

`FunctionCounter`, `FunctionTimer` và các function-tracking meter đọc giá trị từ một object do ứng dụng quản lý. Chúng không sao chép hoặc khóa toàn bộ source state thay ứng dụng.

Ví dụ `FunctionCounter`:

```java
FunctionCounter.builder(
        "app.cache.evictions",
        cacheStats,
        stats -> stats.evictionCount())
    .register(registry);
```

`cacheStats.evictionCount()` phải có semantics đọc đồng thời an toàn theo implementation của cache. Nếu thư viện cache công bố statistic qua atomic/volatile hoặc snapshot thread-safe thì có thể dùng trực tiếp. Nếu statistic lấy từ cấu trúc mutable riêng, cần đồng bộ hóa hoặc publish snapshot trước khi function meter đọc.

Function callback cần trả về giá trị tích lũy đúng semantics và không thực hiện công việc nặng. Đừng cho callback truy cập object đã bị đóng hoặc đã hết lifecycle.

## 15. Các lỗi thường gặp về thread safety

- **Cho rằng mọi state an toàn vì Counter/Timer thread-safe:** object nghiệp vụ hoặc Gauge source vẫn có thể race.
- **Dùng `int++` hoặc `long++` từ nhiều thread:** có thể mất cập nhật.
- **Cho rằng `volatile` làm phép tăng nguyên tử:** volatile chỉ đảm bảo visibility/ordering phù hợp, không bảo vệ read-modify-write.
- **Dùng `LongAdder` khi cần snapshot chính xác:** `sum()` trong lúc cập nhật có thể không phải snapshot nguyên tử.
- **Dùng Gauge để đếm sự kiện:** semantics nên là Counter hoặc FunctionCounter.
- **Không giữ strong reference cho Gauge source:** object có thể bị garbage-collect.
- **Gauge callback gọi database/HTTP:** scrape chậm và có thể gây tải phụ lên hệ thống.
- **Sửa state trong callback:** kết quả phụ thuộc tần suất scrape.
- **Dùng collection không concurrent:** đọc và ghi đồng thời có thể lỗi hoặc cho kết quả không xác định.
- **Đọc nhiều trường riêng lẻ khi cần invariant:** snapshot có thể ghép các giá trị từ những thời điểm khác nhau.
- **Tạo meter theo request/thread:** tăng chi phí và cardinality.
- **Dùng metrics làm nguồn quyết định nghiệp vụ chính xác:** sample có thể là snapshot gần đúng và không nguyên tử giữa meter.

## 16. Kiểm thử cập nhật đồng thời

Nên kiểm thử rằng nhiều worker cùng ghi vào meter không làm mất sự kiện, đồng thời Gauge đọc được trạng thái source an toàn. Ví dụ dùng `SimpleMeterRegistry`, `ExecutorService` và `CountDownLatch`:

```java
import static org.assertj.core.api.Assertions.assertThat;

import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;

class WorkerMetricsConcurrencyTest {
    @Test
    void recordsConcurrentTasksAndReturnsActiveGaugeToZero() throws Exception {
        try (SimpleMeterRegistry registry = new SimpleMeterRegistry()) {
            WorkerMetrics metrics = new WorkerMetrics(registry);
            ExecutorService pool = Executors.newFixedThreadPool(8);
            int taskCount = 1_000;
            CountDownLatch done = new CountDownLatch(taskCount);

            try {
                for (int i = 0; i < taskCount; i++) {
                    pool.execute(() -> {
                        try {
                            metrics.execute(() -> { /* work */ });
                        } finally {
                            done.countDown();
                        }
                    });
                }

                assertThat(done.await(10, TimeUnit.SECONDS)).isTrue();
                assertThat(registry.get("app.worker.completed")
                        .tag("result", "success")
                        .counter().count()).isEqualTo(taskCount);
                assertThat(registry.get("app.worker.active")
                        .gauge().value()).isEqualTo(0.0);
                assertThat(registry.get("app.worker.execution")
                        .timer().count()).isEqualTo(taskCount);
            } finally {
                pool.shutdownNow();
                pool.awaitTermination(5, TimeUnit.SECONDS);
            }
        }
    }
}
```

Test xác minh số lần ghi nhận sau khi tất cả task đã hoàn tất. Nếu test có thể phát sinh exception bên trong task, hãy kiểm tra thêm counter `result=error`. Trong production, cũng cần kiểm tra pool shutdown và task cancellation theo semantics của ứng dụng.

### 16.1. Kiểm thử race condition của source state

Để phát hiện việc dùng biến thường không an toàn, có thể so sánh số lần tăng mong đợi với giá trị sau khi nhiều thread cùng cập nhật. Test race condition có thể không tái hiện lỗi trong mọi lần chạy, vì vậy không nên chỉ dựa vào một test đơn lẻ; hãy dùng primitive đồng bộ đúng ngay từ thiết kế và bổ sung stress test khi state có contention cao.

## 17. Hiệu năng và lựa chọn đồng bộ hóa

Thread safety có chi phí. Atomic operation thường rẻ hơn một lock lớn nhưng có thể tranh chấp CAS khi nhiều thread cập nhật cùng một biến. `LongAdder` giảm contention cho phép cộng dồn, nhưng đổi lại việc đọc tổng không phải snapshot nguyên tử. Lock giúp cập nhật nhiều trường nhất quán, nhưng có thể làm worker chờ nhau.

Hãy chọn theo nhu cầu:

- Một số đếm active chính xác tại thời điểm đọc: `AtomicInteger` thường phù hợp.
- Một bộ đếm sự kiện có write contention cao và chỉ cần tổng quan sát: `LongAdder` hoặc Counter phù hợp theo semantics.
- Một trạng thái gồm nhiều trường cần nhất quán: immutable snapshot qua `AtomicReference` hoặc lock ngắn.
- Một giá trị được cập nhật thưa và đọc thường xuyên: `volatile` có thể đủ nếu không có read-modify-write.
- Một pool executor chuẩn: ưu tiên binder Micrometer thay vì tự đọc và đồng bộ nhiều field nội bộ.

Không thêm lock quanh callback Gauge chỉ để làm callback có vẻ an toàn. Hãy làm cho source state an toàn trước, sau đó callback chỉ đọc state qua API đồng bộ phù hợp.

## 18. Checklist thiết kế meter và source state an toàn luồng

- [ ] Đăng ký meter một lần và chia sẻ meter chuẩn giữa các thread.
- [ ] Không tạo meter mới cho từng request, thread hoặc task.
- [ ] Phân biệt thread safety của meter với thread safety của source object.
- [ ] Dùng AtomicInteger/AtomicLong cho phép tăng giảm cần nguyên tử.
- [ ] Dùng LongAdder cho phép cộng dồn contention cao khi snapshot gần đúng là đủ.
- [ ] Dùng volatile chỉ cho visibility của giá trị đơn, không dùng thay atomic increment.
- [ ] Dùng AtomicReference/immutable snapshot hoặc lock khi nhiều trường cần nhất quán.
- [ ] Giữ strong reference đến object được Gauge quan sát.
- [ ] Bảo đảm Gauge/function callback nhanh, thread-safe, không block và không side effect.
- [ ] Dùng collection concurrent khi state được nhiều thread truy cập.
- [ ] Chọn Counter, Gauge, Timer và DistributionSummary theo đúng semantics.
- [ ] Không dùng metrics làm nguồn quyết định nghiệp vụ chính xác.
- [ ] Kiểm thử với nhiều thread, xác minh count, timer và trạng thái Gauge sau khi hoàn tất.
- [ ] Đo contention và overhead trong môi trường gần production trước khi tối ưu primitive.

Meter chuẩn của Micrometer hỗ trợ ghi nhận đồng thời, nhưng dữ liệu mà Gauge hoặc function meter đọc vẫn phụ thuộc hoàn toàn vào source state. Hãy đăng ký meter một lần, chia sẻ chúng giữa các worker, bảo vệ state bằng primitive phù hợp và giữ callback chỉ đọc nhanh. Khi nhiều trường cần nhất quán, publish một snapshot nguyên tử hoặc dùng lock có phạm vi ngắn; khi chỉ cần đếm sự kiện, chọn Counter thay vì biến Gauge tích lũy. Sự phân tách rõ ràng giữa meter và source object giúp instrumentation an toàn trong môi trường nhiều luồng mà không biến metrics thành điểm nghẽn của ứng dụng.
