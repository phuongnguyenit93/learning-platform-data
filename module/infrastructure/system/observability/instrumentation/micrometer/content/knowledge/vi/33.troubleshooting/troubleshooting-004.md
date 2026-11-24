# Gauge trả NaN do mất đối tượng nguồn hoặc lỗi hàm đọc

Gauge của Micrometer là phép đo một giá trị tức thời. Khi registry lấy mẫu, Gauge gọi hàm đọc trên đối tượng nguồn và xuất giá trị tại thời điểm đó. Nếu Gauge trả `NaN`, cần kiểm tra hai nguyên nhân thường gặp trước tiên: đối tượng nguồn chỉ còn weak reference nên đã bị garbage collector thu gom, hoặc hàm đọc ném exception. Một số trường hợp khác cũng tạo ra `NaN`, chẳng hạn hàm đọc chủ động trả `Double.NaN`, nguồn dữ liệu đang null hoặc phép tính tạo ra giá trị không hữu hạn.

Micrometer giữ weak reference đến đối tượng được đo để meter không vô tình kéo dài vòng đời của state object. Vì vậy, code ứng dụng phải giữ strong reference đến đối tượng đó trong suốt thời gian Gauge cần hoạt động. Với hàm đọc, cần bảo đảm nó nhanh, thread-safe, không blocking và có thể đọc trạng thái hiện tại mà không gây side effect.

## 1. Gauge được lấy mẫu khi nào?

Gauge không tích lũy các thay đổi giữa hai lần đọc. Nó giữ một tham chiếu đến nguồn dữ liệu và gọi hàm đọc khi registry quan sát hoặc publish metric.

Ví dụ, Gauge theo dõi số phần tử trong queue:

~~~java
Gauge.builder("worker.queue.size", queue, Queue::size)
    .register(registry);
~~~

Mỗi lần scrape hoặc publish, Micrometer gọi `Queue.size()` để lấy giá trị hiện tại. Nếu queue tăng từ 2 lên 10 rồi giảm về 4 giữa hai lần scrape, backend chỉ nhìn thấy giá trị được lấy mẫu tại thời điểm đọc. Gauge không ghi lại các giá trị trung gian.

Vòng đời lấy mẫu có thể hình dung như sau:

~~~mermaid
sequenceDiagram
    participant App as Ứng dụng
    participant Gauge as Micrometer Gauge
    participant Registry as MeterRegistry
    participant Backend as Backend

    App->>Gauge: Đăng ký source object + value function
    Note over Gauge: Giữ weak reference đến source
    Registry->>Gauge: Đọc value khi scrape/publish
    Gauge->>Gauge: Lấy source từ WeakReference
    alt Source còn sống
        Gauge->>App: Gọi value function
        App-->>Gauge: Giá trị hiện tại
        Gauge-->>Registry: VALUE
        Registry-->>Backend: Publish sample
    else Source đã bị GC
        Gauge-->>Registry: NaN hoặc không có sample
        Registry-->>Backend: Tùy registry/exporter
    end
~~~

Các registry có thể biểu diễn Gauge đã mất nguồn khác nhau. Một số xuất `NaN`; một số không xuất sample hoặc series có thể biến mất. Vì vậy, cần kiểm tra cả Gauge trong ứng dụng lẫn payload của exporter.

## 2. Nguyên nhân 1: đối tượng nguồn chỉ còn weak reference

Các cách đăng ký Gauge thông thường của Micrometer không giữ strong reference đến state object. Thiết kế này tránh việc một meter vô tình giữ lại collection, cache, pool hoặc object nghiệp vụ đã hết vòng đời.

Hàm đọc được Gauge giữ lại. Vì vậy, tránh tạo callback có capture chính source object ngoài tham số của hàm. Ví dụ `queue::size` là bound method reference và giữ receiver `queue`; `Queue::size` là unbound method reference, nhận queue qua tham số. Dùng callback không capture state object giúp weak-reference semantics hoạt động như dự kiến.

Đoạn code sau có lỗi vòng đời:

~~~java
void registerQueueGauge(MeterRegistry registry) {
    Queue<Job> queue = new ConcurrentLinkedQueue<>();

    Gauge.builder("worker.queue.size", queue, Queue::size)
        .register(registry);
}
~~~

Khi method kết thúc, biến cục bộ `queue` không còn strong reference từ code ứng dụng. Gauge chỉ giữ weak reference, nên queue đủ điều kiện bị garbage collector thu gom. Khi Micrometer lấy mẫu sau đó, source không còn tồn tại và Gauge trả `NaN` hoặc không xuất giá trị.

Triệu chứng thường gặp là metric có giá trị lúc ứng dụng vừa khởi động, sau đó chuyển thành `NaN` hoặc biến mất sau một khoảng thời gian. Thời điểm chính xác phụ thuộc lịch chạy GC, không nhất thiết xảy ra ngay khi method return.

## 3. Giữ strong reference trong bean hoặc component sở hữu state

Cách khắc phục thường tốt nhất là giữ đối tượng được đo trong một field có vòng đời dài hơn Gauge. Ví dụ, một Spring singleton bean sở hữu queue và đăng ký Gauge từ chính queue đó:

~~~java
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

import java.util.Queue;
import java.util.concurrent.ConcurrentLinkedQueue;

@Component
public class JobQueueMetrics {

    private final Queue<Job> queue = new ConcurrentLinkedQueue<>();

    public JobQueueMetrics(MeterRegistry registry) {
        Gauge.builder("worker.queue.size", queue, Queue::size)
            .description("Số job đang chờ xử lý")
            .register(registry);
    }

    public void enqueue(Job job) {
        queue.add(job);
    }

    public Job poll() {
        return queue.poll();
    }
}
~~~

Field `queue` giữ strong reference trong suốt vòng đời bean. Gauge có thể đọc queue khi scrape mà không ngăn queue bị giải phóng sau khi component kết thúc vòng đời.

Có thể dùng cùng cách cho:

- Collection đang theo dõi số phần tử.
- Map đang theo dõi số entry.
- Connection pool hoặc executor có vòng đời ổn định.
- State object lưu số lượng task đang hoạt động.
- Cache hoặc buffer do một service quản lý.

Đối tượng phải được giữ ở nơi có quyền sở hữu vòng đời rõ ràng. Đừng tạo một biến static chỉ để giữ Gauge source nếu state thực tế thuộc về một component có vòng đời ngắn hơn.

## 4. Dùng AtomicInteger hoặc AtomicLong cho giá trị có thể thay đổi

Nếu chỉ cần theo dõi một số có thể tăng hoặc giảm, hãy giữ một atomic number làm state object:

~~~java
@Component
public class ActiveRequestMetrics {

    private final AtomicInteger activeRequests = new AtomicInteger();

    public ActiveRequestMetrics(MeterRegistry registry) {
        Gauge.builder(
                "http.server.active.requests",
                activeRequests,
                AtomicInteger::doubleValue
            )
            .description("Số request đang được xử lý")
            .register(registry);
    }

    public void requestStarted() {
        activeRequests.incrementAndGet();
    }

    public void requestFinished() {
        activeRequests.decrementAndGet();
    }
}
~~~

AtomicInteger vừa là nguồn dữ liệu, vừa cung cấp thao tác cập nhật thread-safe. Field final giữ object sống cùng bean. Gauge đọc giá trị hiện tại khi được lấy mẫu.

Nếu số lượng có thể vượt giới hạn Integer, dùng AtomicLong. Không tạo AtomicInteger mới mỗi lần cập nhật và đăng ký lại Gauge; registry nhận diện meter bằng name và tags nên lần đăng ký sau có thể trả về meter đã tồn tại.

## 5. Khi cần thay thế source object trong lúc ứng dụng chạy

Một số component có thể được khởi tạo lại, ví dụ connection pool đổi cấu hình hoặc cache được thay thế. Nếu đăng ký Gauge trực tiếp trên object cũ, việc tạo Gauge mới với cùng name và tags không tự thay nguồn của meter cũ.

Có thể dùng một holder ổn định như `AtomicReference`:

~~~java
@Component
public class PoolMetrics {

    private final AtomicReference<PoolStats> currentPool =
        new AtomicReference<>();

    public PoolMetrics(MeterRegistry registry) {
        Gauge.builder(
                "database.pool.active",
                currentPool,
                reference -> {
                    PoolStats stats = reference.get();
                    return stats == null ? Double.NaN : stats.active();
                }
            )
            .description("Số connection đang được sử dụng")
            .register(registry);
    }

    public void replacePool(PoolStats poolStats) {
        currentPool.set(poolStats);
    }

    public void clearPool() {
        currentPool.set(null);
    }
}
~~~

Gauge giữ weak reference đến holder `currentPool`. Bean giữ holder bằng field final. Khi pool thay thế, chỉ cần cập nhật reference bên trong holder; Gauge vẫn đọc được nguồn hiện tại qua cùng một meter ID.

Ví dụ trả `NaN` khi pool chưa sẵn sàng là một lựa chọn thể hiện “chưa có dữ liệu”. Nếu hệ thống cần phân biệt trạng thái này, hãy xuất thêm Gauge trạng thái như `database.pool.available` với giá trị 0 hoặc 1. Không đổi trạng thái unknown thành 0 nếu 0 có nghĩa nghiệp vụ là “không có connection đang active”.

## 6. Dùng strongReference(true) khi thật sự cần

Micrometer có fluent builder cho phép giữ strong reference trực tiếp:

~~~java
Gauge.builder("worker.queue.size", queue, Queue::size)
    .strongReference(true)
    .register(registry);
~~~

Với lựa chọn này, Gauge giữ đối tượng nguồn sống cùng meter. API `strongReference(boolean)` được đánh dấu incubating trong Javadoc hiện hành; hãy kiểm tra phiên bản Micrometer được BOM của dự án quản lý trước khi sử dụng.

Strong reference có thể phù hợp khi:

- Đối tượng nguồn được tạo chỉ để phục vụ Gauge.
- Vòng đời của Gauge và object được chủ động quản lý cùng nhau.
- Không có component khác phù hợp để sở hữu object.
- Việc giữ object đến khi registry hoặc meter đóng là hành vi mong muốn.

Không bật strong reference một cách máy móc cho object lớn hoặc object có vòng đời thay đổi. Registry có thể giữ meter trong thời gian dài, khiến object nguồn cũng không được thu gom. Trong nhiều ứng dụng, field trong bean hoặc một holder ổn định là cách thể hiện quyền sở hữu rõ ràng hơn.

## 7. Nguyên nhân 2: hàm đọc ném exception

Ngay cả khi source object còn sống, hàm đọc vẫn có thể lỗi. Ví dụ:

~~~java
Gauge.builder(
        "database.pool.active",
        pool,
        value -> value.getPoolStats().active()
    )
    .register(registry);
~~~

Nếu `getPoolStats()` trả null hoặc ném exception khi pool chưa khởi tạo, việc đọc Gauge sẽ thất bại.

Trong implementation `DefaultGauge` hiện hành, Micrometer bắt lỗi phát sinh khi gọi value function, ghi log và trả `Double.NaN`. Logger dùng chính sách cảnh báo rồi giảm mức log cho các lần lặp tiếp theo. Do đó, lỗi có thể xuất hiện dưới dạng `NaN` mà không làm request scrape thất bại hoàn toàn.

Thông điệp log cần tìm thường có dạng:

~~~text
Failed to apply the value function for the gauge 'database.pool.active'.
~~~

Hãy xem stack trace đi kèm để tìm method hoặc dependency gây lỗi. Hành vi logging và cách exporter biểu diễn giá trị có thể khác theo phiên bản hoặc registry; kiểm tra implementation và log của phiên bản dự án đang chạy.

## 8. Kiểm tra hàm đọc độc lập trước khi đăng ký Gauge

Một cách chẩn đoán nhanh là gọi cùng hàm đọc trực tiếp trong unit test hoặc qua một phương thức kiểm tra nội bộ:

~~~java
double readActiveConnections(PoolStats pool) {
    return pool.active();
}
~~~

Nếu hàm đọc ném exception khi gọi trực tiếp, vấn đề nằm ở state hoặc logic truy cập, không phải ở bộ scrape.

Với một getter có nhiều bước:

~~~java
double readQueueSize(WorkerManager manager) {
    WorkerPool pool = manager.currentPool();

    if (pool == null) {
        return Double.NaN;
    }

    return pool.queueSize();
}
~~~

Hãy xác định rõ null có phải trạng thái hợp lệ hay không. Nếu pool chưa sẵn sàng, có thể:

- Trả `NaN` để biểu thị chưa có số đo.
- Không đăng ký Gauge cho đến khi pool tồn tại.
- Dùng holder ổn định và xuất thêm metric availability.
- Trả giá trị dự phòng chỉ khi giá trị đó có nghĩa nghiệp vụ rõ ràng.

Không trả 0 chỉ để dashboard hết hiển thị NaN. Số 0 có thể bị hiểu là queue thật sự rỗng hoặc pool không có connection đang dùng.

## 9. Hàm đọc phải nhanh, thread-safe và không blocking

Gauge được lấy mẫu bởi registry khi scrape hoặc publish. Hàm đọc có thể chạy trên thread của exporter, scheduler hoặc request endpoint metrics. Vì vậy, không nên thực hiện I/O hoặc phép tính nặng trong callback.

Không nên:

~~~java
Gauge.builder(
        "remote.inventory.available",
        inventoryClient,
        client -> client.fetchInventoryFromRemoteSystem()
    )
    .register(registry);
~~~

Nếu gọi hệ thống bên ngoài mỗi lần scrape, endpoint metrics có thể chậm, timeout hoặc gây tải phụ lên dependency. Một lỗi mạng cũng có thể biến Gauge thành NaN.

Nên cập nhật snapshot ở một luồng refresh riêng, rồi để Gauge đọc snapshot trong bộ nhớ:

~~~java
public final class InventorySnapshot {

    private final AtomicLong available = new AtomicLong();

    public long available() {
        return available.get();
    }

    public void refresh(long newValue) {
        available.set(newValue);
    }
}
~~~

~~~java
Gauge.builder(
        "inventory.available",
        snapshot,
        state -> state.available()
    )
    .register(registry);
~~~

Hàm đọc nên:

- Chỉ đọc state hiện có trong bộ nhớ.
- Có thời gian thực thi ngắn và ổn định.
- Thread-safe khi nhiều registry hoặc scrape đồng thời.
- Không mutate object hoặc gọi API có side effect.
- Có chính sách rõ ràng cho null và trạng thái chưa sẵn sàng.
- Trả về số hữu hạn khi dữ liệu hợp lệ.

Nếu state được cập nhật từ nhiều thread, dùng AtomicInteger, AtomicLong, AtomicReference, volatile hoặc cấu trúc đồng bộ phù hợp. Không giả định Gauge tự đồng bộ hóa object nguồn.

## 10. Phân biệt NaN, Infinity, null và giá trị 0

Các trạng thái này có ý nghĩa khác nhau:

| Giá trị | Ý nghĩa có thể có | Cách xử lý |
|---|---|---|
| `NaN` | Không có số đo hợp lệ, source đã mất, callback lỗi hoặc phép tính không xác định | Kiểm tra source, callback và trạng thái dữ liệu |
| `+Infinity` / `-Infinity` | Phép tính vượt miền hoặc chia cho 0 | Kiểm tra công thức và mẫu số |
| `null` | State hoặc dữ liệu chưa được tạo | Xác định rõ chính sách null trước khi đọc |
| `0` | Giá trị thực bằng 0 | Chỉ trả 0 khi đó là trạng thái hợp lệ |
| Không có series | Meter chưa đăng ký, bị filter, exporter bỏ sample hoặc nguồn không được xuất | Kiểm tra registry, filter và scrape output |

Với builder nhận `ToDoubleFunction<T>`, hàm phải trả primitive double. Nếu dereference null hoặc ném exception, implementation mặc định có thể trả NaN. Một số overload nhận Supplier trong API hiện hành cũng chuyển kết quả null thành NaN; đừng dựa vào hành vi này nếu chưa xác nhận phiên bản Micrometer của ứng dụng.

## 11. Không đăng ký lại Gauge để thay giá trị hoặc nguồn

MeterRegistry chỉ giữ một meter cho mỗi tổ hợp name và tags. Khi gọi builder rồi register lần nữa với cùng ID, registry trả về meter đã tồn tại; nguồn object mới không thay thế nguồn cũ.

~~~java
AtomicInteger firstSource = new AtomicInteger(10);
AtomicInteger secondSource = new AtomicInteger(99);

Gauge first = Gauge.builder(
        "cache.entries",
        firstSource,
        AtomicInteger::doubleValue
    )
    .register(registry);

Gauge second = Gauge.builder(
        "cache.entries",
        secondSource,
        AtomicInteger::doubleValue
    )
    .register(registry);
~~~

Hai biến `first` và `second` có thể tham chiếu cùng một Gauge đã đăng ký. Việc đăng ký lần hai không có nghĩa Gauge bắt đầu đọc `secondSource`. Nếu `firstSource` bị thu gom, Gauge vẫn có thể trả NaN dù `secondSource` còn sống.

Cách đúng là giữ một source ổn định và cập nhật giá trị bên trong nó, hoặc dùng holder như AtomicReference để trỏ tới source hiện hành. Nếu cần một meter độc lập, hãy dùng name hoặc tags khác có ý nghĩa riêng.

## 12. Kiểm thử Gauge đọc giá trị và cập nhật state

Dùng SimpleMeterRegistry để kiểm tra Gauge mà không phụ thuộc backend:

~~~java
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

import java.util.concurrent.atomic.AtomicInteger;

import static org.junit.jupiter.api.Assertions.assertEquals;

class GaugeValueTest {

    @Test
    void gaugeReadsCurrentValueFromStronglyOwnedState() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        AtomicInteger queueSize = new AtomicInteger(3);

        Gauge gauge = Gauge.builder(
                "worker.queue.size",
                queueSize,
                AtomicInteger::doubleValue
            )
            .register(registry);

        assertEquals(3.0, gauge.value());

        queueSize.set(8);

        assertEquals(8.0, gauge.value());
    }
}
~~~

Test giữ biến `queueSize` trong scope và xác nhận Gauge đọc trạng thái hiện tại thay vì snapshot lúc đăng ký. Trong ứng dụng thật, field của bean đảm nhận vai trò giữ strong reference tương tự.

## 13. Kiểm thử hàm đọc ném exception

Có thể dùng cờ để mô phỏng lỗi tạm thời:

~~~java
@Test
void gaugeReturnsNaNWhenValueFunctionThrows() {
    SimpleMeterRegistry registry = new SimpleMeterRegistry();
    AtomicInteger state = new AtomicInteger(7);
    AtomicBoolean fail = new AtomicBoolean(false);

    Gauge gauge = Gauge.builder(
            "worker.queue.size",
            state,
            value -> {
                if (fail.get()) {
                    throw new IllegalStateException("source unavailable");
                }
                return value.doubleValue();
            }
        )
        .register(registry);

    assertEquals(7.0, gauge.value());

    fail.set(true);

    assertTrue(Double.isNaN(gauge.value()));

    fail.set(false);
    state.set(9);

    assertEquals(9.0, gauge.value());
}
~~~

Test này xác nhận lỗi callback tạo NaN trong implementation mặc định, đồng thời Gauge có thể đọc lại thành công khi nguồn phục hồi. Log cảnh báo có thể được phát ra trong lúc test; cấu hình logging của test nên cho phép nhìn thấy lỗi nếu cần chẩn đoán.

Không nên viết test phụ thuộc vào `System.gc()` để chứng minh weak reference bị thu gom. GC không được bảo đảm chạy ngay hoặc chạy theo một lịch xác định, khiến test dễ chập chờn. Kiểm tra ownership qua code review và giữ strong reference rõ ràng; nếu cần test hành vi GC, dùng ReferenceQueue và timeout có kiểm soát trong một test chuyên biệt.

## 14. Kiểm thử holder khi nguồn có thể chưa sẵn sàng

~~~java
@Test
void stableHolderCanRepresentUnavailableSource() {
    SimpleMeterRegistry registry = new SimpleMeterRegistry();
    record PoolStats(double active) { }
    AtomicReference<PoolStats> current = new AtomicReference<>();

    Gauge gauge = Gauge.builder(
            "database.pool.active",
            current,
            reference -> {
                PoolStats pool = reference.get();
                return pool == null ? Double.NaN : pool.active();
            }
        )
        .register(registry);

    assertTrue(Double.isNaN(gauge.value()));

    current.set(new PoolStats(4));

    assertEquals(4.0, gauge.value());
}
~~~

Trong ví dụ, holder luôn còn sống; chỉ nội dung bên trong có thể null. Khi pool được tạo, cập nhật holder làm Gauge có giá trị mà không cần đăng ký meter lần nữa.

Trong production, nên có thêm metric availability nếu dashboard hoặc alert cần phân biệt “pool chưa sẵn sàng” với “pool có 0 connection active”.

## 15. Kiểm tra Gauge qua Actuator và exporter

Nếu ứng dụng dùng Spring Boot Actuator và endpoint metrics được expose, có thể đọc một meter cụ thể:

~~~text
GET /actuator/metrics/worker.queue.size
~~~

Endpoint Prometheus có thể được dùng để kiểm tra payload đã chuẩn hóa:

~~~text
GET /actuator/prometheus
~~~

Khi điều tra, so sánh ba lớp:

1. Gọi trực tiếp `Gauge.value()` trong test hoặc debugger.
2. Đọc `/actuator/metrics/{name}` để xem Micrometer cung cấp measurement gì.
3. Đọc payload exporter để xác định registry đã xuất sample nào.

Nếu Gauge.value() hợp lệ nhưng Actuator hoặc exporter không có series, kiểm tra meter có thực sự được đăng ký, endpoint exposure, MeterFilter, naming convention và cách registry xử lý NaN. Nếu Gauge.value() đã là NaN, tập trung vào source object và callback trước khi điều tra dashboard.

## 16. Quy trình chẩn đoán từng bước

Khi nhận cảnh báo Gauge trả NaN, thực hiện theo thứ tự:

1. **Xác nhận meter identity**: kiểm tra đúng name, tags và registry; tránh nhầm hai meter cùng tên nhưng khác tags.
2. **Đọc trực tiếp giá trị**: gọi Gauge.value() trong test hoặc debugger để tách lỗi instrumentation khỏi exporter.
3. **Kiểm tra source ownership**: tìm nơi giữ strong reference đến object được đo; nếu chỉ có biến cục bộ hoặc object tạm, sửa vòng đời.
4. **Kiểm tra callback**: tìm log “Failed to apply the value function”, rồi xem exception, null dereference hoặc dependency chưa sẵn sàng.
5. **Kiểm tra giá trị trả về**: xác minh công thức không tạo NaN hoặc Infinity và không đổi unknown thành 0.
6. **Kiểm tra đăng ký trùng**: xác nhận một meter ID không bị đăng ký lại với source object mới và tưởng rằng nguồn đã thay đổi.
7. **Kiểm tra exporter**: đối chiếu Actuator metrics endpoint và payload scrape; xem registry có bỏ sample NaN hay không.
8. **Kiểm tra tải và concurrency**: bảo đảm callback không blocking, không đua dữ liệu và không đọc object đang đóng.

Không chỉ sửa dashboard hoặc truy vấn Prometheus để loại bỏ NaN. Nếu nguồn object đã bị GC hoặc callback lỗi, thay đổi ở backend chỉ che dấu vấn đề.

## 17. Những lỗi thường gặp

| Lỗi | Triệu chứng | Cách xử lý |
|---|---|---|
| Truyền object tạm vào Gauge | NaN sau khi GC | Giữ object trong field hoặc holder |
| Nghĩ MeterRegistry giữ source object sống | Object vẫn bị GC | Nhớ rằng source mặc định chỉ được weakly referenced |
| Bật strongReference cho mọi Gauge | Object lớn sống lâu hơn dự kiến | Chỉ bật khi vòng đời được quản lý rõ |
| Callback dereference null | NaN và log exception | Xử lý trạng thái chưa sẵn sàng |
| Callback gọi API từ xa | Scrape chậm, timeout hoặc NaN | Đọc snapshot trong bộ nhớ |
| Callback không thread-safe | Giá trị sai hoặc lỗi cạnh tranh | Dùng atomic/volatile/synchronization phù hợp |
| Trả 0 khi dữ liệu không biết | Dashboard hiểu sai là giá trị thật bằng 0 | Biểu diễn unknown riêng |
| Đăng ký lại cùng name và tags với source mới | Gauge vẫn đọc source cũ | Dùng holder ổn định hoặc meter ID khác |
| Chỉ nhìn Prometheus mà không đọc Gauge.value() | Khó phân biệt lỗi nguồn và lỗi exporter | Kiểm tra từng lớp registry |
| Test dựa vào System.gc() | Test chập chờn | Kiểm tra ownership; dùng ReferenceQueue chỉ khi cần test GC chuyên biệt |

## 18. Checklist phòng tránh Gauge trả NaN

- [ ] Source object được giữ strong reference trong toàn bộ vòng đời Gauge.
- [ ] Không đăng ký Gauge với object tạm hoặc collection chỉ tồn tại trong method.
- [ ] Source có vòng đời phù hợp với bean hoặc component sở hữu nó.
- [ ] Dùng AtomicInteger/AtomicLong hoặc holder ổn định cho state thay đổi.
- [ ] Chỉ dùng `strongReference(true)` khi chủ động chấp nhận giữ object cùng meter.
- [ ] Callback không blocking, không I/O và có thời gian thực thi ổn định.
- [ ] Callback thread-safe và không có side effect.
- [ ] Xử lý null và trạng thái chưa sẵn sàng có chủ đích.
- [ ] Phân biệt NaN, Infinity, null, 0 và series không tồn tại.
- [ ] Không đăng ký lại cùng name/tags với kỳ vọng thay source object.
- [ ] Có unit test cho giá trị bình thường, exception và phục hồi.
- [ ] Kiểm tra log “Failed to apply the value function”.
- [ ] Xác minh Actuator và exporter sau khi sửa.

Gauge trả NaN thường là dấu hiệu Micrometer không đọc được một giá trị hợp lệ tại thời điểm lấy mẫu. Hãy giữ source object sống bằng strong reference do ứng dụng quản lý, kiểm tra exception trong value function và bảo đảm callback chỉ đọc state nhanh, thread-safe. Khi source có thể được thay thế hoặc chưa sẵn sàng, dùng holder ổn định và biểu diễn trạng thái unknown riêng; không đăng ký lại cùng meter ID để mong registry tự thay nguồn.

## Tài liệu tham khảo

- [Micrometer Gauges](https://docs.micrometer.io/micrometer/reference/concepts/gauges.html)
- [Gauge API](https://javadoc.io/doc/io.micrometer/micrometer-core/latest/io/micrometer/core/instrument/Gauge.html)
- [Gauge.Builder API](https://javadoc.io/doc/io.micrometer/micrometer-core/latest/io/micrometer/core/instrument/Gauge.Builder.html)
- [DefaultGauge implementation](https://github.com/micrometer-metrics/micrometer/blob/main/micrometer-core/src/main/java/io/micrometer/core/instrument/internal/DefaultGauge.java)

