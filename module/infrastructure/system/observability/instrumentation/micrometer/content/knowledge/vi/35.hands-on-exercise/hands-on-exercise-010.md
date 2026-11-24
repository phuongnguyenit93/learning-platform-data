# Tìm rồi sửa một trường hợp Gauge mất dữ liệu hoặc tag gây quá nhiều meter

## Mục tiêu thực hành

Bài thực hành này mô phỏng hai lỗi instrumentation thường gặp trong ứng dụng Java dùng Micrometer:

- **Case A — Gauge mất dữ liệu:** Gauge được đăng ký với một object chỉ tồn tại trong biến cục bộ. Micrometer giữ weak reference đến object nguồn, nên object có thể bị garbage collection và Gauge không còn đọc được giá trị.
- **Case B — Cardinality tăng bất thường:** Counter gắn order ID vào tag. Mỗi đơn hàng tạo một Meter.Id khác nhau, khiến registry và backend có quá nhiều meter/time series.

Hai case độc lập. Người học có thể chọn một case theo triệu chứng được giao hoặc hoàn thành cả hai để luyện cách chẩn đoán. Mỗi case yêu cầu tìm nguyên nhân từ code, sửa instrumentation và bổ sung test hồi quy.

Bài thuộc module **OBSERVABILITY_INSTRUMENTATION_MICROMETER**: sử dụng Counter, Gauge, Timer, DistributionSummary và tag có kiểm soát; tích hợp Spring Boot, xuất metrics đến hệ giám sát và diễn giải số đo vận hành.

## Kết quả cần đạt

Sau bài thực hành, bạn có thể:

1. Phân biệt Gauge value bất thường với Gauge source bị garbage collection.
2. Giải thích vì sao Micrometer Gauge không giữ object nguồn sống mãi.
3. Giữ strong reference đến object nguồn trong đúng vòng đời.
4. Nhận biết tag có giá trị duy nhất đang tạo meter mới.
5. Đo số meter trước và sau khi chạy workload.
6. Thay ID động bằng dimension có tập giá trị hữu hạn.
7. Dùng SimpleMeterRegistry để viết test tái hiện và test hồi quy.
8. Xác minh kết quả trong registry và endpoint/exporter.

## Chuẩn bị môi trường

Cần có:

- Java và một project Spring Boot có Micrometer.
- Dependency Actuator và registry đang dùng, hoặc chỉ Micrometer core cho bài unit test.
- JUnit 5 và AssertJ.
- Kiến thức cơ bản về Counter, Gauge, MeterRegistry, tag và weak reference.

Ví dụ dependency Gradle nếu project chưa có:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    runtimeOnly("io.micrometer:micrometer-registry-prometheus")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
~~~

Để unit test độc lập, dùng SimpleMeterRegistry. Không cần Prometheus hoặc OpenTelemetry Collector để tái hiện hai lỗi trong bộ nhớ.

---

## Case A — Gauge mất dữ liệu vì object nguồn không còn strong reference

### Triệu chứng

Ứng dụng expose Gauge cho số worker đang hoạt động. Sau một thời gian, dashboard hiển thị NaN, không có sample hoặc giá trị không còn cập nhật. Code đăng ký Gauge vẫn chạy và meter name vẫn xuất hiện trong registry.

Một cách tái hiện lỗi:

~~~java
public final class WorkerMetrics {

    private final MeterRegistry registry;

    public WorkerMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public void registerPool(String poolName) {
        AtomicInteger activeWorkers = new AtomicInteger();

        Gauge.builder(
                "worker.active",
                activeWorkers,
                AtomicInteger::get
            )
            .tag("pool", poolName)
            .description("Number of active workers")
            .register(registry);
    }
}
~~~

### Nhiệm vụ điều tra

Trước khi sửa, hãy trả lời các câu hỏi:

1. Object nào là nguồn dữ liệu của Gauge?
2. Sau khi registerPool kết thúc, còn field hoặc collection nào giữ object đó không?
3. Gauge có giữ strong reference đến object nguồn không?
4. Vì sao meter vẫn có thể tồn tại trong registry nhưng value không còn hợp lệ?
5. Có thể nhầm lỗi này với việc queue/worker thực sự có giá trị bằng 0 không?
6. Cần kiểm tra cả giá trị Gauge trong registry và cách object nguồn được sở hữu ở đâu?

Gợi ý: Micrometer Gauge thường giữ weak reference đến object được quan sát để registry không giữ object nghiệp vụ sống ngoài ý muốn. Biến cục bộ activeWorkers không còn strong reference sau khi method kết thúc. Garbage collector có thể thu hồi object đó.

### Cách quan sát

Trong môi trường test hoặc debugger:

1. Đặt breakpoint sau lệnh register.
2. Kiểm tra activeWorkers có được lưu trong field hoặc map sống lâu không.
3. Kiểm tra các strong reference còn lại sau khi method kết thúc.
4. Đọc Gauge qua registry trước và sau khi nguồn thay đổi vòng đời.
5. Nếu muốn quan sát garbage collection, dùng WeakReference hoặc heap inspection để kiểm tra object có còn được giữ hay không.

Có thể thử yêu cầu JVM garbage collection để quan sát hiện tượng, nhưng System.gc() chỉ là gợi ý cho JVM, không bảo đảm object được thu hồi ngay. Không viết test CI phụ thuộc vào thời điểm GC hoặc khẳng định System.gc() luôn làm Gauge thành NaN.

### Yêu cầu sửa

Sửa WorkerMetrics để:

- Lưu object nguồn vào field hoặc collection có strong reference.
- Cập nhật chính object đó khi số worker thay đổi.
- Không tạo object mới mỗi lần update.
- Giữ tag pool trong một tập giá trị được kiểm soát.
- Nếu pool có vòng đời động, xác định thời điểm remove Gauge khi pool đóng.

### Lời giải tham chiếu

~~~java
public final class WorkerMetrics {

    private final MeterRegistry registry;
    private final ConcurrentMap<String, AtomicInteger> activeByPool =
        new ConcurrentHashMap<>();

    public WorkerMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public void registerPool(String poolName) {
        AtomicInteger activeWorkers = activeByPool.computeIfAbsent(
            poolName,
            ignored -> new AtomicInteger()
        );

        Gauge.builder(
                "worker.active",
                activeWorkers,
                AtomicInteger::get
            )
            .tag("pool", poolName)
            .description("Number of active workers")
            .register(registry);
    }

    public void updateActiveWorkers(String poolName, int count) {
        AtomicInteger activeWorkers = activeByPool.get(poolName);
        if (activeWorkers == null) {
            throw new IllegalStateException(
                "Pool has not been registered: " + poolName
            );
        }
        activeWorkers.set(count);
    }

    public int activeWorkers(String poolName) {
        AtomicInteger activeWorkers = activeByPool.get(poolName);
        if (activeWorkers == null) {
            throw new IllegalStateException(
                "Pool has not been registered: " + poolName
            );
        }
        return activeWorkers.get();
    }
}
~~~

ConcurrentMap giữ strong reference đến từng AtomicInteger trong khi pool còn được quản lý. Gauge đọc giá trị hiện tại từ cùng object đó. updateActiveWorkers thay đổi object nguồn, không đăng ký Gauge mới.

Trong ứng dụng thực tế, poolName phải đến từ tập cấu hình hữu hạn nếu mỗi pool tạo một tag value. Nếu pool được tạo và hủy với số lượng lớn, cần bổ sung lifecycle cleanup hoặc chuyển sang Gauge tổng hợp. Không dùng map vô hạn để sửa lỗi weak reference rồi vô tình tạo một lỗi bộ nhớ khác.

### Kiểm thử hồi quy

~~~java
class WorkerMetricsTest {

    @Test
    void gaugeReadsTheCurrentValueFromOwnedSource() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        WorkerMetrics metrics = new WorkerMetrics(registry);

        metrics.registerPool("critical");
        metrics.updateActiveWorkers("critical", 4);

        Gauge gauge = registry.get("worker.active")
            .tag("pool", "critical")
            .gauge();

        assertThat(gauge).isNotNull();
        assertThat(gauge.value()).isEqualTo(4.0);

        metrics.updateActiveWorkers("critical", 9);

        assertThat(gauge.value()).isEqualTo(9.0);
    }
}
~~~

Test này xác minh Gauge đọc được cùng nguồn dữ liệu sau nhiều lần cập nhật. Việc giữ strong reference được thể hiện bằng ownership của activeByPool; không cần ép garbage collection trong test.

### Kiểm tra thêm trong ứng dụng

Nếu Actuator metrics endpoint được bật, có thể đọc meter theo tên và tag:

~~~text
GET /actuator/metrics/worker.active?tag=pool:critical
~~~

Nếu dùng Prometheus registry, kiểm tra sample tương ứng trong /actuator/prometheus và xác nhận giá trị thay đổi khi worker active count thay đổi.

Endpoint Actuator cần được bảo vệ theo chính sách truy cập của ứng dụng. Không expose endpoint quản trị metrics công khai chỉ để thuận tiện cho bài thực hành.

### Tiêu chí hoàn thành Case A

- Gauge có một nguồn dữ liệu sống lâu hơn Gauge.
- Giá trị Gauge thay đổi khi cập nhật AtomicInteger.
- Không tạo Gauge mới ở mỗi lần update.
- Test xác minh giá trị ban đầu và giá trị sau cập nhật.
- Nếu tài nguyên động, có quy tắc cleanup và giới hạn tag pool.

---

## Case B — Tag order ID tạo quá nhiều meter

### Triệu chứng

Sau khi chạy workload có nhiều đơn hàng, số meter trong registry tăng gần bằng số đơn hàng. Prometheus có nhiều series cùng tên orders.completed nhưng mỗi series có order.id khác nhau. Scrape payload lớn dần, query chậm và chi phí lưu trữ tăng.

Đoạn code có vấn đề:

~~~java
public final class OrderMetrics {

    private final MeterRegistry registry;

    public OrderMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public void recordCompleted(
            String orderId,
            String channel
    ) {
        registry.counter(
            "orders.completed",
            "order.id", orderId,
            "channel", channel
        ).increment();
    }
}
~~~

### Nhiệm vụ điều tra

Trước khi sửa, hãy chạy một workload nhỏ với nhiều order ID khác nhau, rồi kiểm tra:

1. Có bao nhiêu meter trong registry trước workload?
2. Sau 100, 1.000 hoặc 10.000 order ID, số meter tăng bao nhiêu?
3. Meter name có giữ nguyên nhưng Meter.Id khác nhau ở tag nào?
4. Tag nào có tập giá trị không giới hạn?
5. Người vận hành có thật sự cần tổng hợp metrics theo từng order ID không?
6. Nếu cần tìm một order cụ thể, log hoặc trace có phù hợp hơn metric tag không?

### Cách tái hiện bằng test

~~~java
@Test
void demonstratesOneMeterPerOrderId() {
    SimpleMeterRegistry registry = new SimpleMeterRegistry();
    OrderMetrics metrics = new OrderMetrics(registry);

    for (int i = 0; i < 1_000; i++) {
        metrics.recordCompleted("order-" + i, "web");
    }

    assertThat(registry.getMeters()).hasSize(1_000);
}
~~~

Test này cho thấy mỗi order ID tạo một tổ hợp tag khác nhau và registry tạo meter tương ứng. Số lượng chính xác có thể thay đổi nếu registry hoặc test fixture có meter khác; trong test cô lập này chỉ đăng ký meter của OrderMetrics.

### Yêu cầu sửa

Sửa instrumentation để:

- Bỏ order ID khỏi metric tag.
- Chỉ giữ dimension hữu hạn như channel hoặc outcome.
- Chuẩn hóa channel thành enum/allow-list.
- Đăng ký meter cho các giá trị channel hợp lệ và tái sử dụng reference.
- Nếu cần tra cứu một order, dùng log/trace correlation hoặc hệ thống nghiệp vụ.
- Không dùng MeterFilter làm giải pháp chính để che giấu tag cardinality sai.

### Lời giải tham chiếu

Định nghĩa tập channel có giới hạn:

~~~java
public enum OrderChannel {
    WEB("web"),
    MOBILE("mobile"),
    PARTNER("partner");

    private final String tagValue;

    OrderChannel(String tagValue) {
        this.tagValue = tagValue;
    }

    public String tagValue() {
        return tagValue;
    }
}
~~~

Đăng ký trước một Counter cho mỗi channel:

~~~java
public final class OrderMetrics {

    private final EnumMap<OrderChannel, Counter> completedByChannel =
        new EnumMap<>(OrderChannel.class);

    public OrderMetrics(MeterRegistry registry) {
        for (OrderChannel channel : OrderChannel.values()) {
            Counter counter = Counter.builder("orders.completed")
                .description("Number of completed orders")
                .baseUnit("orders")
                .tag("channel", channel.tagValue())
                .register(registry);

            completedByChannel.put(channel, counter);
        }
    }

    public void recordCompleted(
            String orderId,
            OrderChannel channel
    ) {
        Counter counter = completedByChannel.get(channel);
        if (counter == null) {
            throw new IllegalArgumentException(
                "Unsupported order channel: " + channel
            );
        }

        counter.increment();

        // orderId chỉ dùng cho log/trace correlation nếu cần và được phép.
    }
}
~~~

Mỗi channel hợp lệ có một Counter ổn định. orderId không còn là metric tag nên số meter bị giới hạn bởi số giá trị enum. Reference Counter được cache trong EnumMap và không cần tra registry ở mỗi lần hoàn tất đơn hàng.

Trong hệ thống thực tế, không log raw order ID nếu chính sách dữ liệu không cho phép. Nếu cần correlation, dùng ID đã được phê duyệt hoặc cơ chế trace/log an toàn. High-cardinality trong trace cũng cần kiểm soát quyền truy cập và dữ liệu nhạy cảm.

### Kiểm thử hồi quy cardinality

~~~java
class OrderMetricsTest {

    @Test
    void meterCountDoesNotGrowWithOrderIds() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        OrderMetrics metrics = new OrderMetrics(registry);

        for (int i = 0; i < 1_000; i++) {
            metrics.recordCompleted(
                "order-" + i,
                OrderChannel.WEB
            );
        }

        assertThat(registry.getMeters()).hasSize(3);

        Counter webCounter = registry.get("orders.completed")
            .tag("channel", "web")
            .counter();

        assertThat(webCounter.count()).isEqualTo(1_000.0);
        assertThat(registry.find("orders.completed")
            .tag("order.id", "order-42")
            .counter()).isNull();
    }
}
~~~

Vì constructor đăng ký trước ba channel, registry có đúng ba meter trong test cô lập. Dù ghi 1.000 order khác nhau, số meter không tăng theo order ID.

Nếu ứng dụng chỉ muốn một tổng Counter và không cần phân tích theo channel, có thể bỏ tag channel hoàn toàn và chỉ đăng ký một meter. Chỉ thêm dimension khi nó trả lời câu hỏi vận hành cụ thể.

### Vì sao MeterFilter không phải cách sửa chính?

Có thể dùng MeterFilter làm giới hạn bảo vệ cuối cùng, ví dụ từ chối meter khi một tag vượt số giá trị cho phép. Tuy nhiên, filter không làm cho order ID trở thành dimension đúng. Khi giới hạn bị chạm, các meter mới có thể bị từ chối và metrics của một số đơn hàng sẽ biến mất.

Thiết kế đúng là loại order ID khỏi metric tag ngay từ nguồn. MeterFilter chỉ là hàng rào bổ sung để phát hiện hoặc giới hạn lỗi cấu hình khác.

### Kiểm tra thêm trong Prometheus

Sau khi sửa, kiểm tra exposition:

~~~promql
count by (channel) (orders_completed_total)
~~~

Và tổng số series của metric:

~~~promql
count(orders_completed_total)
~~~

Tên sample có thể khác theo NamingConvention và registry. Hãy dùng tên thực tế từ /actuator/prometheus. Kết quả mong đợi là số series bị giới hạn theo channel và các dimension hạ tầng hợp lệ, không tăng theo số order ID.

### Tiêu chí hoàn thành Case B

- Không còn tag order.id trên metric.
- Channel có allow-list hữu hạn.
- Counter được đăng ký trước và cache.
- Sau 1.000 order ID, số meter vẫn cố định.
- Count của channel web bằng 1.000.
- Có cách correlation an toàn ngoài metric tag nếu cần tìm một order.

---

## Quy trình điều tra chung

Dùng quy trình sau cho cả hai case:

1. **Ghi nhận triệu chứng:** Gauge không có sample, value thành NaN, hoặc meter/series tăng bất thường.
2. **Khoanh vùng metric:** lấy tên, loại, tag và registry đang sử dụng.
3. **Kiểm tra nguồn:** với Gauge, xác định object nguồn và strong reference; với cardinality, liệt kê mọi tag key/value.
4. **Tái hiện:** dùng workload nhỏ, xác định và registry cô lập.
5. **Đặt giả thuyết:** nêu nguyên nhân có thể kiểm chứng, tránh sửa theo phỏng đoán.
6. **Sửa tại nguồn:** giữ object Gauge sống đúng vòng đời hoặc loại ID động khỏi tag.
7. **Viết test hồi quy:** chứng minh triệu chứng không quay lại.
8. **Kiểm tra exposition:** xác nhận sample, tag và giá trị sau khi registry thu thập.
9. **Kiểm tra tác động:** theo dõi meter count, series count, scrape size và dashboard.
10. **Ghi lại hợp đồng:** cập nhật metric catalog nếu semantics, unit hoặc tag thay đổi.

## Bảng phân biệt nhanh

| Dấu hiệu | Gauge source bị thu hồi | Cardinality do tag động |
|---|---|---|
| Triệu chứng | Gauge value thành NaN hoặc mất sample | Meter/series tăng theo số tài nguyên |
| Kiểm tra code | Object nguồn chỉ là biến cục bộ | ID duy nhất nằm trong tag |
| Thành phần cần kiểm tra | Strong reference và vòng đời object | Meter.Id và tập giá trị tag |
| Cách sửa | Giữ source trong field/map sống lâu | Dùng dimension hữu hạn hoặc bỏ tag |
| Test chính | Gauge phản ánh giá trị sau update | Meter count không tăng theo ID |
| Rủi ro phụ | Giữ object quá lâu gây rò bộ nhớ | Tag hợp lệ vẫn có thể nhân cardinality |

## Bài tập mở rộng

Sau khi hoàn thành một hoặc cả hai case, hãy thử các tình huống sau:

1. **Gauge tài nguyên động:** mỗi worker pool có Gauge riêng. Thiết kế register/update/close sao cho source còn sống khi pool hoạt động và meter được remove sau khi writer drain.
2. **Gauge tổng hợp:** thay nhiều Gauge theo pool bằng một Gauge số pool active. So sánh khả năng chẩn đoán và cardinality.
3. **Tag không hợp lệ:** channel đến từ request dưới dạng chuỗi tự do. Chuẩn hóa sang enum hoặc giá trị other trước khi ghi meter.
4. **MeterFilter:** thêm giới hạn tag như hàng rào bảo vệ và kiểm thử hành vi khi giới hạn bị vượt.
5. **Prometheus:** so sánh số series trước/sau sửa và quan sát kích thước exposition.
6. **Regression under load:** chạy nhiều thread cập nhật Gauge/Counter đồng thời, xác minh count cuối và không tạo meter ngoài dự kiến.

Không dùng request ID, order ID hoặc user ID làm tag chỉ để làm bài test phong phú hơn. Dữ liệu thử nghiệm có thể dùng ID trong fixture hoặc log; metric dimensions vẫn phải có cardinality được kiểm soát.

## Báo cáo kết quả thực hành

Khi hoàn thành, ghi lại:

| Mục | Nội dung cần báo cáo |
|---|---|
| Case đã chọn | Gauge source hoặc dynamic tag |
| Triệu chứng ban đầu | Giá trị/số meter quan sát được |
| Nguyên nhân gốc | Bằng chứng từ code hoặc Meter.Id |
| Thay đổi | Object ownership hoặc tag schema đã sửa |
| Test hồi quy | Input, assertion và kết quả |
| Meter count | Trước và sau workload |
| Exposition | Sample/tag/value sau khi sửa |
| Rủi ro còn lại | Lifecycle, cardinality hoặc backend |
| Kết luận | Đạt/chưa đạt tiêu chí nghiệm thu |

## Tiêu chí nghiệm thu toàn bài

Bài thực hành đạt khi:

- Người học xác định được nguyên nhân gốc bằng bằng chứng.
- Bản sửa giải quyết lỗi ở nơi tạo hoặc sở hữu meter.
- Gauge giữ được nguồn dữ liệu trong suốt vòng đời cần quan sát.
- Tag không chứa định danh duy nhất hoặc giá trị không giới hạn.
- Số meter không tăng theo số request/order ID.
- Test hồi quy chạy độc lập bằng registry riêng.
- Kết quả được xác minh trong registry và, nếu có môi trường tích hợp, ở exposition/exporter.
- Không dùng System.gc() hoặc sleep tùy ý làm điều kiện bắt buộc của test.
- Có ghi chú về ownership, cardinality và cách correlation ngoài metric tag.

## Kết luận

Hai lỗi trong bài có biểu hiện khác nhau nhưng cùng bắt nguồn từ việc chưa quản lý đúng vòng đời và danh tính của meter. Gauge cần một object nguồn được giữ bằng strong reference trong thời gian quan sát; registry không tự giữ object nghiệp vụ sống mãi. Metric tag phải mô tả nhóm hữu hạn để tổng hợp; đưa order ID hoặc định danh duy nhất vào tag sẽ tạo meter/time series theo từng giá trị.

Hãy tái hiện bằng registry cô lập, kiểm tra object nguồn hoặc Meter.Id, sửa instrumentation tại nguồn và thêm test hồi quy. Sau đó xác minh giá trị Gauge, số meter, tag và exposition. Với chi tiết từng request, dùng log/trace correlation an toàn; với metrics, giữ dimension ổn định để dashboard và backend có thể tổng hợp lâu dài.
