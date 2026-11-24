# SimpleMeterRegistry để kiểm tra count, tag và giá trị trong bộ nhớ

`SimpleMeterRegistry` là registry gọn nhẹ của Micrometer, lưu meter trong bộ nhớ và cho phép đọc trực tiếp giá trị đã ghi. Nó phù hợp cho unit test và ví dụ nhỏ vì không cần Prometheus, OTLP collector hoặc backend giám sát. Test có thể tạo registry mới, ghi dữ liệu, tìm meter theo tên và tag, rồi kiểm tra count, value hoặc tổng lượng đã ghi.

Một bài test tốt cần xác minh ba điều: meter được đăng ký với đúng identity, tag có giá trị mong đợi, và phép đo phản ánh chính xác thao tác đã thực hiện. Bài này dùng JUnit 5, AssertJ và các meter phổ biến gồm Counter, Gauge, Timer và DistributionSummary.

## 1. SimpleMeterRegistry là gì?

Micrometer tách API instrumentation khỏi backend xuất dữ liệu. Ứng dụng ghi vào `MeterRegistry`; registry cụ thể quyết định cách lưu trữ và xuất meter.

`SimpleMeterRegistry` là implementation trong bộ nhớ:

- Giữ meter trong chính tiến trình test.
- Cho phép truy vấn meter và giá trị trực tiếp.
- Không gửi dữ liệu đến hệ thống giám sát bên ngoài.
- Không cần khởi động exporter hoặc collector.
- Có thể đóng và tạo mới giữa các test để tránh dùng chung state.

Ví dụ khởi tạo:

~~~java
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

SimpleMeterRegistry registry = new SimpleMeterRegistry();
~~~

Khi test kết thúc, đóng registry để giải phóng tài nguyên mà registry quản lý:

~~~java
registry.close();
~~~

Trong JUnit 5, có thể tạo registry trong từng test hoặc dùng lifecycle method `@BeforeEach` và `@AfterEach`. Tạo registry riêng cho từng test giúp kết quả không phụ thuộc thứ tự chạy.

## 2. Dependency cần thiết

`SimpleMeterRegistry` nằm trong artifact `micrometer-core`. Nếu ứng dụng đã dùng Spring Boot Actuator hoặc một Micrometer registry, dependency này thường đã có trong runtime/test classpath.

Với Maven:

~~~xml
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-core</artifactId>
</dependency>
~~~

Với Gradle:

~~~kotlin
implementation("io.micrometer:micrometer-core")
~~~

Nếu Spring Boot quản lý dependency, để BOM của Spring Boot chọn phiên bản Micrometer tương thích. Tránh khai báo một phiên bản `micrometer-core` khác với các module Micrometer còn lại.

Các test bên dưới dùng JUnit Jupiter và AssertJ:

~~~kotlin
testImplementation("org.junit.jupiter:junit-jupiter")
testImplementation("org.assertj:assertj-core")
~~~

## 3. Identity của một meter

Trong Micrometer, một meter được nhận diện chủ yếu bằng tên và tập tag key-value. Hai lần đăng ký cùng tên và cùng tag values sẽ tìm đến cùng meter. Khi một tag value thay đổi, đó là một meter khác.

~~~java
Counter web = registry.counter(
        "orders.created",
        "channel", "web"
);

Counter mobile = registry.counter(
        "orders.created",
        "channel", "mobile"
);
~~~

Hai Counter trên có cùng tên nhưng khác tag `channel`, vì vậy là hai meter riêng.

Ngược lại:

~~~java
Counter first = registry.counter(
        "orders.created",
        "channel", "web"
);
Counter second = registry.counter(
        "orders.created",
        "channel", "web"
);

assertThat(second).isSameAs(first);
~~~

Lời gọi thứ hai lấy lại meter đã đăng ký với cùng identity. Đây là đặc điểm quan trọng khi kiểm thử: hãy xác minh đúng tên và tag, không chỉ kiểm tra rằng một Counter nào đó tồn tại.

Không đưa ID thay đổi theo từng request vào tag. Mỗi giá trị mới có thể tạo thêm meter và làm cardinality tăng nhanh.

## 4. Tạo registry mới cho mỗi test

Một test cơ bản có thể tạo registry trong phương thức test:

~~~java
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class SimpleMeterRegistryTest {

    @Test
    void startsWithNoMeters() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        try {
            assertThat(registry.getMeters()).isEmpty();
        } finally {
            registry.close();
        }
    }
}
~~~

Registry mới bắt đầu không có meter do test tạo. Một số môi trường có thể đăng ký meter mặc định qua cấu hình ứng dụng; với unit test trực tiếp như trên, chỉ có các meter được tạo từ registry này.

Nếu nhiều test cùng dùng một registry ở field static hoặc singleton, count và tag values từ test trước có thể còn tồn tại. Tạo registry mới cho mỗi test hoặc reset state theo cách rõ ràng.

## 5. Kiểm tra Counter count

Counter phù hợp với sự kiện chỉ tăng, ví dụ số đơn hàng được tạo hoặc số lần retry.

~~~java
@Test
void recordsCounterCount() {
    SimpleMeterRegistry registry = new SimpleMeterRegistry();
    try {
        Counter counter = registry.counter(
                "orders.created",
                "channel", "web"
        );

        counter.increment();
        counter.increment(2.0);

        assertThat(counter.count()).isEqualTo(3.0);
    } finally {
        registry.close();
    }
}
~~~

`count()` trả về `double`, vì vậy assertion dùng `3.0`. Counter không dùng để giảm giá trị; khi cần biểu diễn số lượng hiện tại có thể tăng hoặc giảm, hãy cân nhắc Gauge.

Có thể truy vấn lại Counter từ registry:

~~~java
Counter found = registry.find("orders.created")
        .tag("channel", "web")
        .counter();

assertThat(found).isNotNull();
assertThat(found.count()).isEqualTo(3.0);
~~~

Việc truy vấn lại xác minh meter được đăng ký đúng tên và tag thay vì chỉ kiểm tra object mà test đang giữ.

Thực hiện truy vấn trước khi đóng registry. Sau `registry.close()`, không tiếp tục dùng registry như nguồn dữ liệu của test.

## 6. Kiểm tra tag values và số meter

Ví dụ đăng ký Counter cho hai kênh:

~~~java
registry.counter("orders.created", "channel", "web").increment();
registry.counter("orders.created", "channel", "mobile").increment();
registry.counter("orders.created", "channel", "partner").increment();
~~~

Kiểm tra từng tag:

~~~java
assertThat(registry.find("orders.created")
        .tag("channel", "web")
        .counter()
        .count()).isEqualTo(1.0);

assertThat(registry.find("orders.created")
        .tag("channel", "mobile")
        .counter()
        .count()).isEqualTo(1.0);
~~~

Kiểm tra số meter cùng tên:

~~~java
long orderMeters = registry.getMeters().stream()
        .filter(meter -> meter.getId().getName().equals("orders.created"))
        .count();

assertThat(orderMeters).isEqualTo(3);
~~~

Số meter ở đây là số tổ hợp tag đã đăng ký, không phải tổng số lần Counter tăng.

## 7. Dùng registry.find khi meter có thể chưa tồn tại

`registry.find(name)` hỗ trợ truy vấn không bắt buộc phải có meter. Có thể kiểm tra meter vắng mặt:

~~~java
assertThat(registry.find("orders.cancelled").counter()).isNull();
~~~

Sau khi đăng ký:

~~~java
registry.counter("orders.cancelled", "reason", "customer").increment();

assertThat(registry.find("orders.cancelled")
        .tag("reason", "customer")
        .counter()).isNotNull();
~~~

Nếu dùng API tìm kiếm dạng `registry.get(name)`, Micrometer kỳ vọng meter tồn tại; truy vấn meter chưa được đăng ký có thể ném exception. Với test kiểm tra sự vắng mặt, `find` diễn đạt ý định rõ hơn.

## 8. Kiểm tra Gauge value thay đổi

Gauge đo giá trị hiện tại của một object hoặc hàm đọc. Nó phù hợp với queue depth, số connection đang dùng hoặc số tác vụ đang chờ.

~~~java
import io.micrometer.core.instrument.Gauge;
import java.util.concurrent.atomic.AtomicInteger;

@Test
void readsCurrentGaugeValue() {
    SimpleMeterRegistry registry = new SimpleMeterRegistry();
    AtomicInteger queueDepth = new AtomicInteger(3);

    try {
        Gauge gauge = Gauge.builder(
                "worker.queue.depth",
                queueDepth,
                AtomicInteger::get
        ).tag("pool", "email").register(registry);

        assertThat(gauge.value()).isEqualTo(3.0);

        queueDepth.set(8);

        assertThat(gauge.value()).isEqualTo(8.0);
    } finally {
        registry.close();
    }
}
~~~

Gauge không cộng dồn các lần thay đổi. Khi object đổi từ 3 sang 8, giá trị Gauge được đọc là 8; nó không trở thành 11.

Giữ tham chiếu mạnh đến object được Gauge quan sát trong suốt test. Một số Gauge giữ tham chiếu yếu đến object để tránh ngăn garbage collection; nếu object bị thu hồi, giá trị có thể trở thành `NaN`.

## 9. Kiểm tra Gauge bằng collection

Có thể đo kích thước một collection:

~~~java
List<String> pendingJobs = new ArrayList<>();
Gauge.builder("worker.pending.jobs", pendingJobs, List::size)
        .register(registry);

pendingJobs.add("job-a");
pendingJobs.add("job-b");

assertThat(registry.find("worker.pending.jobs")
        .gauge()
        .value()).isEqualTo(2.0);
~~~

Gauge chỉ đọc giá trị khi được lấy mẫu. Với collection đồng thời, hãy dùng cấu trúc dữ liệu thread-safe hoặc một hàm đọc an toàn với concurrency của ứng dụng.

## 10. Kiểm tra Timer count và total time

Timer ghi nhận số lần thực hiện và tổng thời gian. Có thể kiểm tra bằng cách ghi một Duration cố định, không cần ngủ thread:

~~~java
import io.micrometer.core.instrument.Timer;
import java.time.Duration;
import java.util.concurrent.TimeUnit;

@Test
void recordsTimerCountAndTotalTime() {
    SimpleMeterRegistry registry = new SimpleMeterRegistry();
    try {
        Timer timer = registry.timer(
                "orders.processing",
                "result", "success"
        );

        timer.record(Duration.ofMillis(120));
        timer.record(Duration.ofMillis(80));

        assertThat(timer.count()).isEqualTo(2);
        assertThat(timer.totalTime(TimeUnit.MILLISECONDS))
                .isEqualTo(200.0);
    } finally {
        registry.close();
    }
}
~~~

Ghi Duration trực tiếp giúp test xác định: tổng thời gian kỳ vọng không phụ thuộc scheduler hoặc độ trễ của máy test.

Không dùng `Thread.sleep(120)` rồi mong Timer trả đúng 120 ms. Scheduler, GC và tải máy có thể làm thời gian thực tế khác nhau.

## 11. Kiểm tra Timer qua tag

Nếu Timer được phân loại theo kết quả:

~~~java
registry.timer("orders.processing", "result", "success")
        .record(Duration.ofMillis(100));
registry.timer("orders.processing", "result", "failure")
        .record(Duration.ofMillis(250));
~~~

Truy vấn từng meter:

~~~java
Timer success = registry.find("orders.processing")
        .tag("result", "success")
        .timer();

Timer failure = registry.find("orders.processing")
        .tag("result", "failure")
        .timer();

assertThat(success.count()).isEqualTo(1);
assertThat(success.totalTime(TimeUnit.MILLISECONDS)).isEqualTo(100.0);
assertThat(failure.count()).isEqualTo(1);
assertThat(failure.totalTime(TimeUnit.MILLISECONDS)).isEqualTo(250.0);
~~~

Tag `result` có tập giá trị hữu hạn. Không thay nó bằng exception message hoặc request ID vì mỗi giá trị động có thể tạo một meter mới.

## 12. Đo code bằng Timer.record

Timer có thể tự đo thời gian thực thi của Runnable hoặc Callable:

~~~java
timer.record(() -> service.process());
~~~

Đây là API tiện lợi cho code production, nhưng test chỉ nên kiểm tra rằng callback được thực thi và Timer count tăng. Không assert một duration cố định khi đo thời gian thực.

~~~java
AtomicBoolean invoked = new AtomicBoolean();

timer.record(() -> invoked.set(true));

assertThat(invoked).isTrue();
assertThat(timer.count()).isEqualTo(1);
~~~

Nếu cần kiểm tra tổng thời gian chính xác, dùng `timer.record(Duration)` hoặc API có thể điều khiển clock.

## 13. Kiểm tra DistributionSummary count và total amount

DistributionSummary đo phân phối của một đại lượng số không phải thời gian, ví dụ payload size hoặc số item trong batch.

~~~java
import io.micrometer.core.instrument.DistributionSummary;

@Test
void recordsDistributionCountAndTotalAmount() {
    SimpleMeterRegistry registry = new SimpleMeterRegistry();
    try {
        DistributionSummary payloadSize = registry.summary(
                "http.request.payload.size",
                "format", "json"
        );

        payloadSize.record(512.0);
        payloadSize.record(1_024.0);
        payloadSize.record(2_048.0);

        assertThat(payloadSize.count()).isEqualTo(3);
        assertThat(payloadSize.totalAmount()).isEqualTo(3_584.0);
    } finally {
        registry.close();
    }
}
~~~

Count là số quan sát; total amount là tổng các giá trị đã ghi. Đơn vị cần được thể hiện rõ trong tên hoặc `baseUnit`, ví dụ bytes:

~~~java
DistributionSummary.builder("http.request.payload.size")
        .baseUnit("bytes")
        .register(registry);
~~~

## 14. Kiểm tra meter identity bằng tên và tag

Một helper có thể giúp test truy vấn meter nhất quán:

~~~java
static Counter findCounter(
        MeterRegistry registry,
        String name,
        String tagKey,
        String tagValue) {
    return registry.find(name)
            .tag(tagKey, tagValue)
            .counter();
}
~~~

Sau đó:

~~~java
Counter counter = findCounter(
        registry,
        "orders.created",
        "channel",
        "web"
);

assertThat(counter).isNotNull();
assertThat(counter.count()).isEqualTo(4.0);
~~~

Helper nên giữ đơn giản. Đừng viết một framework test riêng chỉ để bọc vài lời gọi `registry.find`; dùng API trực tiếp nếu test chỉ có một hoặc hai meter.

## 15. Kiểm tra tag đầy đủ, không chỉ một tag

Với meter có nhiều tag, lọc theo tất cả chiều quan trọng:

~~~java
Timer timer = registry.find("http.server.requests")
        .tags(
                "method", "GET",
                "status", "200",
                "uri", "/orders/{id}"
        )
        .timer();

assertThat(timer).isNotNull();
~~~

Truy vấn theo một tag có thể trả về meter đầu tiên phù hợp trong tập kết quả. Khi test yêu cầu một tổ hợp cụ thể, chỉ rõ đủ tag để tránh chọn nhầm meter.

Tag values nên được kiểm tra đúng như instrumentation đã đăng ký. Nếu ứng dụng chuẩn hóa URI, test phải xác minh URI template thay vì URL chứa ID thực.

## 16. Kiểm tra service ghi meter

Nên kiểm tra cả hành vi service và kết quả trong registry. Ví dụ service ghi Counter khi đơn hàng được tạo:

~~~java
final class OrderService {
    private final MeterRegistry registry;

    OrderService(MeterRegistry registry) {
        this.registry = registry;
    }

    void create(String channel) {
        // Thực hiện nghiệp vụ tạo đơn hàng tại đây.
        registry.counter(
                "orders.created",
                "channel", channel
        ).increment();
    }
}
~~~

Test:

~~~java
@Test
void recordsOrderByChannel() {
    SimpleMeterRegistry registry = new SimpleMeterRegistry();
    try {
        OrderService service = new OrderService(registry);

        service.create("web");
        service.create("web");
        service.create("mobile");

        assertThat(registry.find("orders.created")
                .tag("channel", "web")
                .counter()
                .count()).isEqualTo(2.0);

        assertThat(registry.find("orders.created")
                .tag("channel", "mobile")
                .counter()
                .count()).isEqualTo(1.0);
    } finally {
        registry.close();
    }
}
~~~

Test này xác minh instrumentation ở cấp service, không chỉ kiểm tra API Counter hoạt động. Trong ứng dụng thực tế, nghiệp vụ có thể được giả lập bằng dependency hoặc repository mock.

## 17. Kiểm tra exception path với Timer

Nếu Timer đo một thao tác có thể ném exception, cần xác minh count vẫn tăng khi thao tác kết thúc lỗi:

~~~java
Timer timer = registry.timer("orders.validation");

assertThatThrownBy(() ->
        timer.record((Runnable) () -> {
            throw new IllegalArgumentException("invalid order");
        })
).isInstanceOf(IllegalArgumentException.class);

assertThat(timer.count()).isEqualTo(1);
~~~

`Timer.record(Runnable)` dừng Timer khi Runnable kết thúc, kể cả khi ném RuntimeException, rồi ném lại exception. Test nên kiểm tra cả hai điều: thời lượng được ghi và exception nghiệp vụ vẫn đến caller.

Nếu tự quản lý `Timer.Sample`, dùng `try/finally` để bảo đảm sample được dừng:

~~~java
Timer.Sample sample = Timer.start(registry);
try {
    service.validate(order);
} finally {
    sample.stop(timer);
}
~~~

Không đặt `sample.stop` chỉ ở nhánh thành công nếu mục tiêu là đo mọi lần hoàn tất.

## 18. Phân biệt test SimpleMeterRegistry với test exporter

`SimpleMeterRegistry` kiểm tra meter trong bộ nhớ. Nó không chứng minh exporter xuất dữ liệu đúng định dạng.

| Nội dung | SimpleMeterRegistry | Registry exporter thật |
|---|---|---|
| Counter count | Có | Có |
| Gauge value | Có | Có, theo quy tắc exporter |
| Timer count/total time | Có | Có |
| DistributionSummary count/total amount | Có | Có |
| Tên metric sau chuẩn hóa backend | Không | Có thể kiểm tra |
| Prometheus scrape format | Không | Có |
| OTLP payload và temporality | Không | Có |
| Histogram bucket do exporter hỗ trợ | Không xác minh đầy đủ | Có thể kiểm tra |
| Kết nối collector/backend | Không | Có thể kiểm tra tích hợp |

Unit test bằng SimpleMeterRegistry nhanh và cô lập. Với yêu cầu về naming convention, histogram, resource attributes, export interval hoặc giao thức, hãy viết integration test dùng registry/exporter thật hoặc test server tương ứng.

## 19. SimpleMeterRegistry không mô phỏng toàn bộ Spring Boot

Nếu service nhận `MeterRegistry` qua constructor, có thể truyền SimpleMeterRegistry trong unit test:

~~~java
OrderService service = new OrderService(new SimpleMeterRegistry());
~~~

Trong Spring Boot integration test, ứng dụng có thể dùng registry do Actuator auto-configure, thường là composite hoặc registry exporter cụ thể. Tạo một SimpleMeterRegistry riêng trong test mà không inject vào service sẽ không thấy các meter mà ứng dụng ghi ở registry khác.

Hãy chọn một trong hai cách:

- Unit test: tạo SimpleMeterRegistry và inject trực tiếp vào class đang kiểm thử.
- Spring context test: lấy MeterRegistry từ ApplicationContext và truy vấn chính registry đó.

Không kiểm tra một registry trong khi code thực tế ghi vào registry khác.

## 20. Quy tắc cô lập state giữa các test

Các meter giữ count và state trong registry. Để test độc lập:

1. Tạo registry mới cho mỗi test.
2. Không dùng static registry chia sẻ giữa các test.
3. Đóng registry sau test.
4. Không phụ thuộc thứ tự test.
5. Dùng tag cố định và dữ liệu đầu vào xác định.

Ví dụ với JUnit:

~~~java
class OrderMetricsTest {
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
    void countsCreatedOrders() {
        registry.counter("orders.created").increment();

        assertThat(registry.counter("orders.created").count())
                .isEqualTo(1.0);
    }
}
~~~

Không dùng `registry.clear()` như cách mặc định để reset mọi state nếu API đó không có trong phiên bản Micrometer của dự án. Tạo registry mới thường rõ ràng và ít phụ thuộc phiên bản hơn.

## 21. Tránh kiểm thử bằng giá trị thời gian không xác định

Các test sau dễ chập chờn:

~~~java
timer.record(() -> Thread.sleep(100));
assertThat(timer.totalTime(TimeUnit.MILLISECONDS)).isEqualTo(100.0);
~~~

Thời gian thực tế có thể dài hơn 100 ms do scheduler, GC hoặc tải máy. Cách tốt hơn:

~~~java
timer.record(Duration.ofMillis(100));
assertThat(timer.totalTime(TimeUnit.MILLISECONDS)).isEqualTo(100.0);
~~~

Nếu cần kiểm thử code sử dụng clock để tạo duration, dùng `MockClock` và registry nhận clock đó. Điều này giúp kiểm soát thời gian mà không phụ thuộc tốc độ máy test.

## 22. Kiểm tra đơn vị và tên meter

Meter có thể khai báo base unit:

~~~java
Counter.builder("orders.created")
        .description("Number of created orders")
        .tag("channel", "web")
        .register(registry);

DistributionSummary.builder("http.request.payload.size")
        .baseUnit("bytes")
        .register(registry);
~~~

Test có thể kiểm tra metadata:

~~~java
Meter meter = registry.find("http.request.payload.size").meter();

assertThat(meter).isNotNull();
assertThat(meter.getId().getBaseUnit()).isEqualTo("bytes");
~~~

Metadata như description và base unit giúp tài liệu hóa meter. Không phải backend nào cũng giữ nguyên mọi metadata; kiểm tra trực tiếp ở registry chỉ xác minh phần Micrometer đã đăng ký.

## 23. Kiểm tra cardinality cơ bản

Một test có thể xác minh cùng một tập tag hữu hạn tạo đúng số meter:

~~~java
for (String channel : List.of("web", "mobile", "partner")) {
    registry.counter("orders.created", "channel", channel).increment();
}

long meterCount = registry.getMeters().stream()
        .filter(meter -> meter.getId().getName().equals("orders.created"))
        .count();

assertThat(meterCount).isEqualTo(3);
~~~

Đây là kiểm tra cấu trúc cho một tập đầu vào xác định. Nó không thay thế HighCardinalityTagsDetector hoặc kiểm tra tải với dữ liệu production-like, nhưng có thể bắt lỗi vô tình thêm tag động trong instrumentation.

## 24. Các lỗi thường gặp

**Dùng registry dùng chung giữa test.** Count từ test trước còn tồn tại. Tạo registry mới cho mỗi test.

**Chỉ assert object Counter vừa tạo.** Test có thể bỏ sót sai tag hoặc sai tên. Truy vấn lại bằng `registry.find(name).tag(...)`.

**Nhầm count với số meter.** Counter count là số lần sự kiện; số meter là số identity name/tag đã đăng ký.

**Nghĩ Gauge cộng dồn.** Gauge đọc giá trị hiện tại của object; thay đổi object làm value đổi theo.

**Để object Gauge bị garbage collection.** Giữ tham chiếu mạnh đến object được quan sát trong test.

**Dùng Thread.sleep để kiểm tra Timer chính xác.** Dùng Duration cố định hoặc MockClock.

**Không kiểm tra tag đầy đủ.** Cùng tên có thể có nhiều meter theo các tag combinations khác nhau. Lọc theo đủ tag cần thiết.

**Tạo SimpleMeterRegistry riêng nhưng service ghi vào registry khác.** Inject đúng registry vào class đang test hoặc lấy registry từ Spring context.

**Cho rằng SimpleMeterRegistry kiểm tra được Prometheus/OTLP.** Nó không kiểm tra scrape format, payload, temporality hoặc backend.

**Đưa ID vào tag trong test rồi quên bỏ ở production.** Test nên phản ánh chính sách cardinality của instrumentation thật.

## 25. Checklist viết test với SimpleMeterRegistry

Trước khi hoàn thành test, hãy xác minh:

- [ ] Mỗi test có registry độc lập hoặc state được reset rõ ràng.
- [ ] Registry được đóng sau test.
- [ ] Meter name đúng với hợp đồng instrumentation.
- [ ] Tag keys và values được truy vấn chính xác.
- [ ] Counter count phản ánh số lần increment.
- [ ] Gauge value thay đổi theo object được quan sát.
- [ ] Timer count và total time được kiểm tra bằng Duration xác định.
- [ ] DistributionSummary count và total amount được xác minh.
- [ ] Exception path vẫn ghi duration và giữ nguyên exception.
- [ ] Không dùng sleep để assert thời gian chính xác.
- [ ] Object được Gauge tham chiếu còn sống trong thời gian test.
- [ ] Test dùng đúng registry mà service thực sự ghi vào.
- [ ] Yêu cầu exporter/backend được kiểm tra bằng integration test riêng.

## 26. Kết luận

`SimpleMeterRegistry` giúp kiểm tra instrumentation Micrometer trong bộ nhớ mà không cần backend. Hãy dùng nó để xác minh identity của meter theo tên và tag, Counter count, Gauge value hiện tại, Timer count/total time và DistributionSummary count/total amount. Truy vấn lại meter bằng `registry.find` để chắc chắn tên và tag đúng.

Giữ test xác định bằng cách tạo registry riêng, ghi Duration cố định, giữ tham chiếu đến object Gauge và không dựa vào `Thread.sleep`. SimpleMeterRegistry phù hợp cho unit test về hành vi meter; khi cần xác minh format, histogram, temporality, exporter hoặc kết nối backend, bổ sung integration test với registry tương ứng.

## Tài liệu tham khảo

- [Micrometer – Registry concepts](https://docs.micrometer.io/micrometer/reference/concepts/registry.html)
- [Micrometer – Counters](https://docs.micrometer.io/micrometer/reference/concepts/counters.html)
- [Micrometer – Gauges](https://docs.micrometer.io/micrometer/reference/concepts/gauges.html)
- [Micrometer – Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html)
- [Micrometer – Distribution Summaries](https://docs.micrometer.io/micrometer/reference/concepts/distribution-summaries.html)
- [Micrometer – SimpleMeterRegistry API](https://javadoc.io/doc/io.micrometer/micrometer-core/latest/io/micrometer/core/instrument/simple/SimpleMeterRegistry.html)
