# Chi phí đăng ký, tra cứu và ghi nhận meter trong đường xử lý thường xuyên

## Vì sao cần quan tâm đến chi phí instrumentation?

Micrometer được thiết kế để việc ghi nhận metrics có thể dùng thường xuyên trong ứng dụng Java. Tuy vậy, instrumentation vẫn tiêu thụ CPU, bộ nhớ và thời gian thực thi. Ở một endpoint có lưu lượng lớn, một thao tác nhỏ được gọi hàng chục nghìn lần mỗi giây cũng có thể tạo ra chi phí đáng kể.

Cần phân biệt ba nhóm chi phí:

1. **Đăng ký meter:** tạo Meter.Id, chuẩn hóa tên và tag, chạy MeterFilter, tra registry để tìm meter hiện có hoặc tạo meter mới.
2. **Tra cứu meter:** lấy Counter, Timer, Gauge hoặc meter khác từ registry theo tên và tag. Tra cứu lặp lại trong hot path có thể tạo thêm công việc không cần thiết.
3. **Ghi nhận measurement:** gọi increment, record, observe hoặc cập nhật nguồn dữ liệu của Gauge. Chi phí phụ thuộc loại meter, cấu hình histogram, số tag, mức đồng thời và registry.

Ngoài ba nhóm này còn có chi phí thu thập và xuất dữ liệu. Prometheus scrape có thể duyệt nhiều meter và đọc Gauge; OTLP registry có thể gom và gửi dữ liệu theo chu kỳ; backend tiếp tục xử lý, lưu trữ và truy vấn các time series. Những chi phí đó thường không diễn ra đồng bộ trên từng lần increment, nhưng vẫn ảnh hưởng tài nguyên của toàn hệ thống.

Mục tiêu không phải loại bỏ instrumentation khỏi đường xử lý. Mục tiêu là đăng ký meter ổn định, dùng lại reference, giới hạn cardinality, chọn đúng loại meter và đo overhead trong tải thực tế.

## Vòng đời của một meter

### Đăng ký một lần, ghi nhận nhiều lần

Meter thường có danh tính dựa trên tên và tập tag. Khi ứng dụng đăng ký meter với cùng danh tính trong cùng registry, registry thường trả về meter đã có. Khi tên hoặc tag khác, registry có thể tạo một meter mới.

Luồng phù hợp:

~~~text
Application startup
       |
       v
Create MeterRegistry
       |
       v
Register Counter / Timer / Gauge
       |
       v
Cache meter references in bean
       |
       v
Request hot path
       |
       +--> counter.increment()
       |
       +--> timer.record(...)
       |
       v
Registry collects / exports later
~~~

Đăng ký meter khi Spring bean được tạo hoặc trong MeterBinder giúp chi phí tạo meter xảy ra ở giai đoạn khởi động. Mỗi request sau đó chỉ dùng reference đã có.

Ví dụ, một Counter cho số đơn hàng hoàn tất nên được đăng ký trong constructor của component metrics. Không cần gọi builder và register lại mỗi khi một đơn hàng hoàn tất.

### Đăng ký lặp vẫn có chi phí dù registry trả lại meter cũ

Một số API tiện dụng như registry.counter(name, tags) có thể tìm meter đã đăng ký và trả lại cùng meter khi danh tính trùng. Điều đó giúp tránh tạo một meter mới cho mỗi lần gọi, nhưng lời gọi vẫn phải xử lý tên, tag và tra cứu registry.

Dùng Counter.builder(...).register(registry) lặp lại trong mỗi request còn có thể tạo thêm builder, Meter.Id và cấu trúc tạm trước khi registry xác định meter đã tồn tại. Cách này không phù hợp với hot path.

Đăng ký lặp với tag động còn tệ hơn: mỗi tập tag mới có thể tạo meter và time series mới. Vì vậy, hãy tách rõ giai đoạn cấu hình instrumentation và giai đoạn ghi nhận.

## Cache meter reference trong component

### Ví dụ đăng ký Counter và Timer khi khởi tạo bean

~~~java
@Component
public class OrderMetrics {

    private final Counter completed;
    private final Counter failed;
    private final Timer processing;

    public OrderMetrics(MeterRegistry registry) {
        this.completed = Counter.builder("orders.completed")
            .description("Committed orders")
            .baseUnit("orders")
            .register(registry);

        this.failed = Counter.builder("orders.failed")
            .description("Failed order processing attempts")
            .baseUnit("attempts")
            .register(registry);

        this.processing = Timer.builder("orders.processing")
            .description("Order processing duration")
            .register(registry);
    }

    public void recordCompleted() {
        completed.increment();
    }

    public void recordFailure() {
        failed.increment();
    }

    public void recordProcessing(Runnable action) {
        processing.record(action);
    }
}
~~~

Component giữ reference bằng field final. Các method được gọi thường xuyên chỉ thao tác trên meter đã đăng ký.

Cách này cũng giúp tập trung tên, description, base unit và tag tại một nơi. Khi cần thay đổi tên hoặc tag, code review có thể nhìn thấy rõ thay đổi cardinality.

### Không tra registry trong mỗi lần xử lý nếu không cần

Ví dụ sau không nên dùng trong hot path:

~~~java
public void completeOrder() {
    registry.counter("orders.completed").increment();
}
~~~

Lời gọi này có thể trả về meter cũ nếu tên và tag ổn định, nhưng vẫn thực hiện lookup mỗi lần. Cách tốt hơn là inject một component giữ Counter đã đăng ký:

~~~java
public void completeOrder() {
    orderMetrics.recordCompleted();
}
~~~

Không cần biến mọi meter thành singleton toàn cục. Hãy giữ reference trong bean có trách nhiệm instrumentation và dùng dependency injection. Cách này làm lifecycle và test rõ ràng hơn.

### Với tag có tập giá trị hữu hạn, cache theo enum

Nếu cần phân loại outcome, có thể đăng ký trước một meter cho mỗi giá trị enum nhỏ và ổn định:

~~~java
public enum Outcome {
    SUCCESS,
    FAILURE,
    TIMEOUT
}

@Component
public class PaymentMetrics {

    private final Map<Outcome, Counter> outcomes;

    public PaymentMetrics(MeterRegistry registry) {
        Map<Outcome, Counter> meters = new EnumMap<>(Outcome.class);

        for (Outcome outcome : Outcome.values()) {
            meters.put(
                outcome,
                Counter.builder("payments.operations")
                    .tag("outcome", outcome.name().toLowerCase(Locale.ROOT))
                    .register(registry)
            );
        }

        this.outcomes = Map.copyOf(meters);
    }

    public void record(Outcome outcome) {
        outcomes.get(outcome).increment();
    }
}
~~~

Ví dụ chỉ tạo ba meter vì Outcome có ba giá trị cố định. Trong hot path, code tra một map nhỏ rồi increment Counter đã có.

Không nên áp dụng cách này cho tập giá trị lớn hoặc không giới hạn. Cache hàng triệu meter chỉ chuyển chi phí từ registry sang bộ nhớ của ứng dụng.

## Cardinality là chi phí dài hạn

### Mỗi tổ hợp tag có thể tạo một time series

Một meter có thể được phân biệt bởi các tổ hợp tag. Nếu có 4 giá trị method, 3 outcome và 5 region, số tổ hợp có thể lên tới:

~~~text
4 x 3 x 5 = 60 time series
~~~

Nếu thêm user ID có một triệu giá trị, số tổ hợp có thể tăng theo cấp số nhân. Với histogram, mỗi tổ hợp tag còn nhân với số bucket và các chuỗi liên quan như count, sum hoặc max tùy registry.

Không đưa các giá trị không giới hạn vào tag:

- Request ID, trace ID, span ID.
- User ID, order ID, payment reference.
- URL đầy đủ chứa resource ID.
- Exception message hoặc SQL statement tự do.
- Tên file, key hoặc message ID có giá trị biến đổi liên tục.

Dùng nhóm giá trị hữu hạn như method, outcome, route template, operation, region hoặc provider type. Nếu cần tìm một request cụ thể, dùng trace/log correlation hoặc exemplar thay vì metric tag.

### Tránh tạo meter theo dữ liệu request

Ví dụ không nên dùng:

~~~java
Counter.builder("orders.completed")
    .tag("order.id", orderId)
    .register(registry)
    .increment();
~~~

Mỗi order ID có thể tạo một meter riêng. Registry phải lưu meter, backend phải ingest series và hệ thống truy vấn phải quản lý dữ liệu tăng không giới hạn.

Nên dùng tag outcome hoặc channel có tập giá trị hữu hạn:

~~~java
Counter.builder("orders.completed")
    .tag("channel", channelGroup)
    .register(registry);
~~~

Tốt hơn nữa, đăng ký sẵn các meter cho những channel đã định nghĩa trong cấu hình hoặc enum và giữ reference như ví dụ trước.

### MeterFilter là hàng rào bảo vệ, không phải thiết kế cardinality

MeterFilter có thể giới hạn số meter, từ chối tên hoặc tag không phù hợp. Tuy nhiên, filter không thay thế việc tránh tạo danh tính meter động. Mỗi lần code cố đăng ký meter mới vẫn có thể phải tạo ID và chạy qua quá trình filter/lookup trước khi bị từ chối.

Các giới hạn như maximumAllowableMetrics hoặc maximumAllowableTags nên được xem là bảo vệ cuối cùng. Thiết kế tốt vẫn là dùng tên và tag ổn định ngay từ đầu.

## Chi phí ghi nhận của từng loại meter

### Counter

Counter.increment() cập nhật giá trị tích lũy. Khi meter đã đăng ký, đây thường là thao tác nhẹ và an toàn khi nhiều luồng cùng ghi. Tuy vậy, vẫn có chi phí đồng bộ hoặc cập nhật cấu trúc nội bộ; không nên giả định nó hoàn toàn miễn phí.

Không cần đọc lại Counter từ registry sau mỗi lần increment. Nếu cần tổng số trong code nghiệp vụ, hãy quản lý trạng thái nghiệp vụ riêng; Counter là công cụ quan sát và không phải nguồn dữ liệu giao dịch.

### Timer

Timer.record(...) đo thời lượng và cập nhật count, total time cùng các thống kê được cấu hình. Khi bật percentile histogram hoặc nhiều bucket SLO, mỗi observation có thể cập nhật thêm cấu trúc thống kê.

Chọn thống kê dựa trên câu hỏi cần trả lời. Histogram giúp tính percentile tổng hợp ở backend nhưng tăng chi phí ghi nhận, bộ nhớ và số time series. Không bật mọi percentile hoặc bucket cho mọi Timer nếu không có use case.

Với đoạn đồng bộ, Timer.record(Runnable) là API rõ ràng:

~~~java
processingTimer.record(() -> orderProcessor.process(command));
~~~

Nếu cần kiểm soát ranh giới bắt đầu/kết thúc, có thể dùng Timer.Sample. Hãy tránh tạo Timer.Sample hoặc tra registry nhiều lần hơn mức cần thiết. Đo overhead thực tế trước khi thay API tiện dụng bằng code thủ công.

### Gauge

Gauge đọc giá trị từ một object hoặc supplier tại thời điểm registry thu thập. Nó không ghi observation ở mỗi lần thay đổi trạng thái. Vì vậy, callback Gauge nên nhẹ, nhanh và không blocking.

~~~java
@Component
public class QueueMetrics {

    private final AtomicInteger queueDepth = new AtomicInteger();

    public QueueMetrics(MeterRegistry registry) {
        Gauge.builder(
                "jobs.queue.depth",
                queueDepth,
                AtomicInteger::get
            )
            .description("Current number of queued jobs")
            .baseUnit("jobs")
            .register(registry);
    }

    public void updateDepth(int depth) {
        queueDepth.set(depth);
    }
}
~~~

Micrometer Gauge thường giữ tham chiếu yếu đến object được quan sát. Component phải giữ tham chiếu mạnh đến queueDepth như field ở ví dụ; nếu object bị garbage collection, Gauge có thể không còn đọc được giá trị mong muốn.

Không thực hiện database query, gọi HTTP hoặc quét collection lớn trong supplier của Gauge. Callback có thể được gọi khi scrape hoặc export, và một callback chậm sẽ làm tăng chi phí thu thập metrics.

### DistributionSummary

DistributionSummary ghi nhận phân phối của giá trị số như payload size hoặc batch size. Mỗi lần record cập nhật count, total amount và các thống kê phân phối nếu được bật.

Giữ đơn vị nhất quán và không tạo meter mới cho từng kích thước hoặc ID. Kích thước là giá trị observation; nó không nên trở thành tag.

### Observation và AOP

Observation có thể được xử lý bởi nhiều handler, ví dụ metrics và tracing. Mỗi lifecycle có chi phí tạo context, mở/đóng scope và gọi handler. Custom handler nên giữ callback ngắn, không I/O và không tạo meter động.

@Timed qua Spring AOP còn có chi phí proxy/advice. Nó thuận tiện ở ranh giới method giữa các bean, nhưng không nên thêm nhiều lớp AOP trùng lặp cho cùng một đoạn code. Chọn một cách instrumentation phù hợp và đo overhead khi lưu lượng cao.

## Export và scrape cũng tiêu thụ tài nguyên

Ghi Counter hoặc Timer vào meter đã đăng ký thường cập nhật dữ liệu trong tiến trình. Với registry phổ biến, việc gửi dữ liệu đến backend diễn ra theo cơ chế thu thập riêng:

- Prometheus scrape endpoint đọc dữ liệu khi Prometheus scrape.
- OTLP registry thường gom và export metrics theo step.
- Một số registry hoặc integration có thể có hành vi export khác; cần kiểm tra implementation cụ thể.

Do đó, không nên mô tả mọi increment là một network request. Tuy nhiên, số meter, số tag, số histogram bucket và callback Gauge càng lớn thì scrape/export càng tốn CPU, bộ nhớ, băng thông và chi phí ingest.

Endpoint exposition có thể phải duyệt qua nhiều meter và định dạng nhiều sample. Nếu một ứng dụng có hàng chục nghìn meter hoặc histogram với nhiều tổ hợp tag, scrape có thể trở thành tải đáng kể ngay cả khi code nghiệp vụ chỉ gọi increment rất nhẹ.

Hãy theo dõi thời gian scrape, kích thước payload, số series, số meter và chi phí export. Đừng chỉ benchmark method ghi Counter rồi kết luận toàn pipeline metrics không có overhead.

## Những việc nên tránh trong hot path

| Thực hành | Vì sao tốn kém hoặc rủi ro | Cách làm phù hợp |
|---|---|---|
| Builder/register meter trong mỗi request | Tạo ID, tag, lookup và có thể cấp phát meter mới | Đăng ký lúc khởi tạo bean |
| Tra registry lặp lại khi đã có meter | Lookup không cần thiết trong đường thường xuyên | Cache Counter/Timer reference |
| Tag bằng ID duy nhất | Tạo nhiều meter và time series | Dùng nhóm giá trị hữu hạn |
| Tạo meter theo từng event name động | Registry tăng liên tục | Dùng một Counter hoặc nhóm event cố định |
| Gauge supplier gọi database | Scrape/export có thể chậm hoặc gây tải DB | Đọc snapshot đã được cập nhật trong bộ nhớ |
| Ghi log hoặc I/O trong ObservationHandler | Tăng latency của operation | Callback ngắn, không blocking |
| Bật histogram cho mọi meter | Tăng cập nhật thống kê, bộ nhớ và series | Chỉ bật ở metric phục vụ SLO/percentile |
| Duyệt registry trong mỗi request | Lặp lại công việc chẩn đoán và enumeration | Chỉ inspect trong test hoặc công cụ chẩn đoán |
| Đăng ký nhiều aspect cho cùng method | Có thể ghi trùng và tăng overhead | Một cơ chế instrumentation rõ ràng |
| Dùng metrics làm nguồn dữ liệu nghiệp vụ | Meter không đảm bảo transaction durability | Dùng database/event ledger cho dữ liệu chuẩn |

## Đo overhead thay vì đoán

### So sánh các cấu hình có kiểm soát

Để đánh giá instrumentation, tạo các trường hợp so sánh:

1. Baseline không có instrumentation.
2. Counter đã đăng ký và cache reference.
3. Counter lookup trong mỗi lần gọi.
4. Timer record với cấu hình thống kê cơ bản.
5. Timer có histogram/SLO.
6. Observation với metrics handler.
7. @Timed qua proxy nếu ứng dụng dùng AOP.

Dùng cùng workload, cùng JVM, cùng cấu hình và cùng dữ liệu đầu vào. Warm-up JVM trước khi đo; chạy nhiều fork hoặc nhiều lần lặp để giảm ảnh hưởng của JIT, GC và trạng thái máy.

Đo ít nhất:

- Throughput.
- p50, p95 và p99 latency.
- CPU utilization.
- Allocation rate và garbage collection.
- Số meter và số time series.
- Kích thước payload scrape/export.
- Thời gian scrape hoặc export.

Không chỉ nhìn thời gian trung bình. Một instrumentation có thể ít ảnh hưởng throughput trung bình nhưng làm tăng tail latency khi registry tạo meter mới hoặc khi scrape đồng thời.

### JMH cho phép đo vi mô

JMH phù hợp để so sánh các thao tác nhỏ như increment trên meter đã cache với lookup registry lặp lại. Cần thiết kế benchmark để kết quả không bị tối ưu bỏ, warm-up đầy đủ và có nhiều thread nếu workload thực tế đồng thời.

Benchmark vi mô không mô phỏng đầy đủ Spring Boot, exporter, network, scrape hoặc tải của backend. Dùng nó để hiểu chi phí tương đối của thao tác, không dùng một con số nanosecond duy nhất làm dự báo production.

### Load test và profiling cho toàn ứng dụng

Sau benchmark vi mô, chạy load test trên ứng dụng gần với môi trường triển khai. Giữ số instance, registry, tag, histogram và scrape/export interval tương tự production.

Dùng Java Flight Recorder hoặc profiler để tìm:

- Thời gian CPU trong registry lookup hoặc meter creation.
- Allocation liên quan đến builder, tag và Meter.Id.
- Lock contention hoặc cập nhật thống kê histogram.
- Gauge callback chậm.
- Observation/AOP handler tiêu tốn CPU.
- Chi phí định dạng và export exposition.

Nếu instrumentation chiếm tỷ lệ nhỏ trong profile nhưng hệ thống vẫn chậm, hãy tìm bottleneck chính thay vì tối ưu metrics một cách mù quáng.

## Kiểm thử để ngăn meter tăng ngoài dự kiến

### Kiểm tra số meter ổn định

Một test có thể chạy nhiều operation với cùng tag và xác minh registry chỉ có một meter cho danh tính đó:

~~~java
SimpleMeterRegistry registry = new SimpleMeterRegistry();

Counter completed = Counter.builder("orders.completed")
    .tag("outcome", "success")
    .register(registry);

for (int i = 0; i < 10_000; i++) {
    completed.increment();
}

assertThat(registry.getMeters()).hasSize(1);
assertThat(completed.count()).isEqualTo(10_000.0);
~~~

Test này xác nhận reference đã đăng ký được tái sử dụng và count tăng đúng. Nó không benchmark chi phí của registry hoặc exporter.

### Kiểm tra tag không tăng theo request ID

Chạy nhiều request có ID khác nhau nhưng cùng các dimension hợp lệ. Xác minh số meter không tăng theo số request. Nếu ID chỉ được dùng trong trace/log, nó không nên xuất hiện như metric tag.

### Kiểm tra Gauge callback

Test Gauge nên xác minh giá trị thay đổi theo nguồn dữ liệu và callback không phụ thuộc database/network. Giữ object nguồn sống trong suốt test để tránh trường hợp weak reference bị thu hồi.

### Kiểm tra cấu hình histogram

Xác minh chỉ những Timer/DistributionSummary cần percentile hoặc SLO mới bật histogram. Kiểm tra bucket boundaries, số series và payload exporter để phát hiện thay đổi cardinality sau khi cấu hình.

## Checklist tối ưu instrumentation

Trước khi đưa meter vào hot path, hãy xác minh:

1. Meter được đăng ký một lần ở giai đoạn khởi tạo chưa?
2. Component có giữ reference Counter/Timer ổn định không?
3. Có lookup registry hoặc builder/register trong mỗi request không?
4. Tên meter và tag có ổn định, hữu hạn không?
5. Số tổ hợp tag và histogram bucket có nằm trong ngân sách không?
6. Counter, Gauge, Timer và DistributionSummary có đúng ngữ nghĩa không?
7. Gauge source có được giữ tham chiếu mạnh và callback có nhẹ không?
8. ObservationHandler và AOP advice có làm việc trùng lặp không?
9. Callback instrumentation có tránh I/O và blocking không?
10. Scrape/export có bị ảnh hưởng bởi số meter, bucket và Gauge callback không?
11. Benchmark có so baseline với instrumentation bằng cùng workload không?
12. Load test có kiểm tra p95/p99, CPU, allocation và GC không?
13. Test có bảo đảm meter count ổn định khi số request tăng không?
14. Có dùng profiler để xác định bottleneck trước khi tối ưu không?

## Kết luận

Chi phí instrumentation phụ thuộc vào nơi meter được đăng ký, cách tra cứu, loại measurement và số lượng series mà registry phải quản lý. Đăng ký meter ổn định khi khởi tạo bean, cache reference trong component và chỉ dùng tag có tập giá trị hữu hạn. Tránh builder/register, lookup không cần thiết và meter có ID động trong hot path.

Ghi nhận trên meter đã đăng ký thường nhẹ hơn tạo meter mới, nhưng Timer histogram, Observation handler, Gauge callback, scrape và export vẫn tiêu thụ tài nguyên. Hãy chọn thống kê theo nhu cầu, giữ callback ngắn, đo bằng JMH cho thao tác vi mô và load test/profiling cho toàn ứng dụng. Kiểm thử số meter và cardinality khi workload tăng để bảo đảm instrumentation cung cấp tín hiệu vận hành mà không trở thành bottleneck của chính ứng dụng.
