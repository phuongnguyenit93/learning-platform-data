# Tách kiểm thử phép đo đơn vị với kiểm thử tích hợp qua hệ thống nhận

## Vì sao cần tách hai loại kiểm thử?

Một phép đo Micrometer có thể đúng trong registry của ứng dụng nhưng vẫn không đến được hệ thống giám sát. Ngược lại, endpoint có thể trả về dữ liệu nhưng meter lại đếm sai sự kiện nghiệp vụ. Hai vấn đề này nằm ở hai lớp khác nhau và cần cách kiểm thử khác nhau.

**Kiểm thử đơn vị phép đo** tập trung vào instrumentation trong tiến trình: meter có được đăng ký đúng tên, loại, đơn vị và tag không; Counter có tăng đúng; Timer có ghi đúng count và duration; Gauge có phản ánh đúng trạng thái; filter có chặn meter ngoài phạm vi không.

**Kiểm thử tích hợp qua hệ thống nhận** xác minh dữ liệu đi qua cấu hình ứng dụng, registry exporter, transport, receiver và backend. Ví dụ, Prometheus có scrape endpoint và lưu series; OpenTelemetry Collector nhận OTLP metrics rồi chuyển đến backend; hệ thống nhận có thể truy vấn được giá trị đã gửi.

Trong module OBSERVABILITY_INSTRUMENTATION_MICROMETER, các meter như Counter, Gauge, Timer và DistributionSummary được dùng để đo ứng dụng Java, tích hợp Spring Boot và xuất dữ liệu đến hệ giám sát. Một chiến lược kiểm thử tốt phải chứng minh cả hai điều: instrumentation ghi đúng trong ứng dụng và pipeline chuyển dữ liệu đến nơi tiêu thụ hoạt động đúng.

Không nên dùng một bài test có mock toàn bộ MeterRegistry để tuyên bố đã kiểm tra exporter. Cũng không cần khởi động cả Prometheus hoặc Collector cho mọi test Counter đơn giản. Mỗi tầng nên kiểm tra đúng trách nhiệm của nó.

## Bản đồ các tầng kiểm thử

| Tầng | Thành phần được kiểm tra | Công cụ thường dùng | Kết luận có thể rút ra |
|---|---|---|---|
| Unit test | Logic ghi meter và semantics của meter | SimpleMeterRegistry | Code instrumentation đăng ký và cập nhật meter đúng |
| Spring integration test | Auto-configuration, binder, Observation/AOP và endpoint Actuator | Spring Boot Test, MockMvc, WebTestClient | Ứng dụng cấu hình registry và công bố exposition đúng |
| Exporter integration test | Gửi payload qua HTTP/gRPC hoặc scrape contract | Mock HTTP receiver, test server, registry thật | Exporter tạo request đúng protocol, path và payload |
| End-to-end test | Receiver, Collector, backend và truy vấn dữ liệu | Prometheus/Collector/backend trong container hoặc môi trường test | Hệ thống nhận thực sự lưu và truy vấn được metric |

Các tầng có thể dùng chung một fixture nhưng không thay thế nhau. Unit test nhanh và ổn định nên chạy thường xuyên; integration test kiểm tra cấu hình framework; end-to-end test ít hơn nhưng cần xác nhận pipeline thực tế trước khi phát hành hoặc thay đổi cấu hình quan trọng.

## Unit test với SimpleMeterRegistry

### Kiểm tra Counter

SimpleMeterRegistry lưu meter trong bộ nhớ và không gửi dữ liệu ra ngoài. Nó phù hợp để kiểm tra code instrumentation mà không cần network hoặc backend.

Ví dụ component:

~~~java
public final class OrderMetrics {

    private final Counter completed;
    private final Counter failed;

    public OrderMetrics(MeterRegistry registry) {
        this.completed = Counter.builder("orders.completed")
            .description("Committed orders")
            .baseUnit("orders")
            .register(registry);

        this.failed = Counter.builder("orders.failed")
            .description("Failed order attempts")
            .baseUnit("attempts")
            .register(registry);
    }

    public void recordCompleted() {
        completed.increment();
    }

    public void recordFailure() {
        failed.increment();
    }
}
~~~

Unit test xác minh số lần ghi:

~~~java
@Test
void recordsOrderOutcomes() {
    SimpleMeterRegistry registry = new SimpleMeterRegistry();
    OrderMetrics metrics = new OrderMetrics(registry);

    metrics.recordCompleted();
    metrics.recordCompleted();
    metrics.recordFailure();

    assertThat(registry.get("orders.completed").counter().count())
        .isEqualTo(2.0);

    assertThat(registry.get("orders.failed").counter().count())
        .isEqualTo(1.0);
}
~~~

Test này xác nhận component ghi đúng số lần vào registry. Nó chưa xác nhận Counter được xuất thành tên metric nào ở Prometheus hoặc payload OTLP ra sao.

Nên tạo registry riêng cho từng test và đóng registry sau khi dùng nếu implementation có tài nguyên cần giải phóng. Không chia sẻ một global registry giữa các test độc lập vì count và meter cũ có thể làm kết quả bị nhiễm.

### Kiểm tra Timer bằng dữ liệu xác định

Không nên đo thời gian thực của một đoạn code rất ngắn rồi khẳng định kết quả phải bằng chính xác một con số. Scheduler, JIT, GC và độ phân giải clock làm thời lượng thay đổi.

Để kiểm tra phép ghi và chuyển đổi đơn vị, ghi duration xác định trực tiếp:

~~~java
@Test
void recordsTimerCountAndTotalTime() {
    SimpleMeterRegistry registry = new SimpleMeterRegistry();
    Timer timer = Timer.builder("orders.processing")
        .register(registry);

    timer.record(50, TimeUnit.MILLISECONDS);
    timer.record(150, TimeUnit.MILLISECONDS);

    assertThat(timer.count()).isEqualTo(2);
    assertThat(timer.totalTime(TimeUnit.MILLISECONDS))
        .isCloseTo(200.0, within(0.001));
}
~~~

Test này xác minh count và total time của Timer. Một test khác có thể gọi method nghiệp vụ qua Timer.record(Runnable) để xác nhận khối mã được thực thi và Timer được cập nhật, nhưng chỉ nên kiểm tra count và duration lớn hơn 0 hoặc nằm trong khoảng hợp lý.

Nếu cần kiểm thử thời gian một cách hoàn toàn xác định, dùng clock giả hoặc công cụ thời gian được hỗ trợ bởi phiên bản Micrometer đang dùng. Tránh phụ thuộc vào sleep dài để tạo duration.

### Kiểm tra DistributionSummary

DistributionSummary phù hợp với giá trị như payload size, batch size hoặc số bản ghi trong một lô:

~~~java
@Test
void recordsDistributionValues() {
    SimpleMeterRegistry registry = new SimpleMeterRegistry();
    DistributionSummary summary =
        DistributionSummary.builder("request.payload.size")
            .baseUnit("bytes")
            .register(registry);

    summary.record(100);
    summary.record(200);
    summary.record(500);

    assertThat(summary.count()).isEqualTo(3);
    assertThat(summary.totalAmount()).isEqualTo(800.0);
    assertThat(summary.max()).isEqualTo(500.0);
}
~~~

Test này xác minh dữ liệu ghi nhận trong registry đơn giản. Nó không kiểm tra histogram bucket hoặc percentile được exporter tạo ra. Những phần đó cần kiểm tra ở registry có cấu hình distribution phù hợp hoặc ở tầng exposition/exporter.

### Kiểm tra Gauge và vòng đời nguồn dữ liệu

Gauge thường giữ weak reference đến object được quan sát. Test phải giữ strong reference đến nguồn trong suốt thời gian kiểm tra:

~~~java
@Test
void gaugeReflectsCurrentQueueDepth() {
    SimpleMeterRegistry registry = new SimpleMeterRegistry();
    AtomicInteger queueDepth = new AtomicInteger(4);

    Gauge.builder(
            "jobs.queue.depth",
            queueDepth,
            AtomicInteger::get
        )
        .register(registry);

    Gauge gauge = registry.get("jobs.queue.depth").gauge();
    assertThat(gauge.value()).isEqualTo(4.0);

    queueDepth.set(9);

    assertThat(gauge.value()).isEqualTo(9.0);
}
~~~

Test này xác nhận Gauge đọc trạng thái hiện tại từ object nguồn. Nếu object nguồn bị garbage collection, test có thể thất bại hoặc Gauge không còn giá trị hữu ích. Trong ứng dụng, component sở hữu Gauge phải giữ nguồn sống đủ lâu.

### Kiểm tra tag và cardinality

Test cần xác nhận tag mang ý nghĩa phân loại và có tập giá trị hữu hạn. Không tạo tag theo request ID, user ID hoặc order ID chỉ để test dễ truy vấn.

Có thể kiểm tra số meter sau nhiều lần ghi cùng một danh tính:

~~~java
@Test
void repeatedUpdatesReuseTheSameMeter() {
    SimpleMeterRegistry registry = new SimpleMeterRegistry();
    Counter counter = Counter.builder("orders.completed")
        .tag("outcome", "success")
        .register(registry);

    for (int i = 0; i < 1_000; i++) {
        counter.increment();
    }

    assertThat(registry.getMeters()).hasSize(1);
    assertThat(counter.count()).isEqualTo(1_000.0);
}
~~~

Một test khác có thể tạo meter với các tag value hợp lệ và xác nhận số meter nằm trong ngân sách dự kiến. Nếu test cố tình đưa ID duy nhất vào tag để chứng minh cardinality tăng, chỉ thực hiện trong registry cô lập và không đưa quy ước đó vào production.

### Kiểm tra MeterFilter

MeterFilter có thể được kiểm tra bằng registry đơn giản:

~~~java
@Test
void deniesMetersOutsideTheAllowedGroup() {
    SimpleMeterRegistry registry = new SimpleMeterRegistry();

    registry.config()
        .meterFilter(MeterFilter.denyNameStartsWith("debug."));

    registry.counter("debug.internal.events").increment();
    registry.counter("orders.completed").increment();

    assertThat(registry.find("debug.internal.events").counter())
        .isNull();

    assertThat(registry.find("orders.completed").counter())
        .isNotNull();
}
~~~

Test này xác nhận filter áp dụng tại registry. Nếu chính sách filter được Spring Boot cấu hình bằng property, cần thêm Spring integration test để xác nhận property thực sự được bind và filter được đăng ký.

## Unit test instrumentation của service

Một service có thể nhận MeterRegistry qua constructor và gọi Counter/Timer ở đúng điểm nghiệp vụ. Test có thể dùng SimpleMeterRegistry thật để kiểm tra cả kết quả nghiệp vụ lẫn meter.

Ví dụ:

~~~java
class CheckoutServiceTest {

    private final SimpleMeterRegistry registry =
        new SimpleMeterRegistry();

    private final OrderMetrics metrics = new OrderMetrics(registry);

    @Test
    void incrementsCompletedOnlyAfterSuccessfulCommit() {
        CheckoutService service = new CheckoutService(
            command -> new Order("order-1"),
            metrics
        );

        service.checkout(new CheckoutCommand());

        assertThat(registry.get("orders.completed").counter().count())
            .isEqualTo(1.0);
    }
}
~~~

Ví dụ này minh họa cách kiểm tra điểm ghi metric gắn với kết quả nghiệp vụ. Trong test thực tế, dependency database hoặc repository nên được thay bằng fake/in-memory fixture nếu mục tiêu chỉ là logic service. Nếu cần xác minh transaction commit, phải có integration test với transaction manager và database phù hợp.

Không dùng metric làm nguồn sự thật cho dữ liệu nghiệp vụ. Counter có thể nằm trong bộ nhớ và không có tính bền vững như transaction database. Test nghiệp vụ vẫn phải xác minh kết quả chuẩn từ service hoặc repository.

## Spring Boot integration test

### Kiểm tra auto-configuration và binder

Spring Boot có thể tự đăng ký meter cho JVM, HTTP server, DataSource, cache, executor và các thành phần được hỗ trợ. Integration test cần khởi tạo ApplicationContext thật để xác minh dependency, bean condition và property.

Ví dụ:

~~~java
@SpringBootTest
class BuiltInMetricsIntegrationTest {

    @Autowired
    MeterRegistry registry;

    @Test
    void registersExpectedJvmMeter() {
        assertThat(registry.find("jvm.memory.used").gauge())
            .isNotNull();
    }
}
~~~

Tên và loại meter cần xác minh theo phiên bản Spring Boot/Micrometer và cấu hình test. Không giả định mọi ứng dụng đều có cùng binder hoặc meter; điều kiện classpath và bean quyết định danh sách thực tế.

Nếu test cần xác minh DataSource hoặc cache metrics, hãy tạo bean tương ứng trong context và xác nhận binder đã bind. Không chỉ kiểm tra class dependency có trong classpath.

### Kiểm tra cấu hình bật/tắt

Có thể tạo context với property cụ thể:

~~~java
@SpringBootTest(properties = {
    "management.metrics.enable.jvm.memory.used=false"
})
class DisabledMetricIntegrationTest {

    @Autowired
    MeterRegistry registry;

    @Test
    void disabledMeterIsNotRegistered() {
        assertThat(registry.find("jvm.memory.used").gauge())
            .isNull();
    }
}
~~~

Ví dụ minh họa; tên property, meter name và loại meter cần đúng với phiên bản ứng dụng. Cũng cần xác minh filter hoặc registry khác không làm thay đổi kết quả.

### Kiểm tra Observation và AOP

Nếu instrumentation dùng Observation, test cần inject ObservationRegistry từ Spring context và xác minh handler metrics được cấu hình. Gọi Observation trong một registry rỗng không tự tạo Timer.

Nếu dùng @Timed hoặc @Counted, test phải gọi Spring bean qua proxy. Không tạo service bằng new khi mục tiêu là xác minh AOP. Cần kiểm tra aspect bean, proxy type, self-invocation và meter sau lời gọi.

Những test này xác nhận tích hợp bên trong ứng dụng. Chúng chưa chứng minh exporter đã gửi dữ liệu đến receiver bên ngoài.

## Kiểm tra exposition của ứng dụng

### PrometheusMeterRegistry.scrape()

Với Prometheus registry, có thể kiểm tra exposition được tạo ra:

~~~java
@Test
void exposesPrometheusSamples() {
    PrometheusMeterRegistry registry =
        new PrometheusMeterRegistry(PrometheusConfig.DEFAULT);

    registry.counter(
        "orders.completed",
        "outcome",
        "success"
    ).increment(3);

    String exposition = registry.scrape();

    assertThat(exposition)
        .contains("orders_completed_total")
        .contains("outcome=\"success\"");
}
~~~

Tên metric cụ thể phụ thuộc naming convention và phiên bản registry. Nên kiểm tra nội dung theo sample và label có ý nghĩa, tránh phụ thuộc toàn bộ chuỗi exposition nếu định dạng có thể thay đổi.

scrape() xác nhận PrometheusMeterRegistry có thể tạo exposition. Nó không khởi động Prometheus server, không scrape endpoint của ứng dụng và không lưu series trong Prometheus TSDB.

### Kiểm tra Actuator endpoint

Với Spring Boot, endpoint Prometheus thường được expose bằng cấu hình web exposure và dependency registry tương ứng:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
~~~

Một integration test có thể gọi endpoint bằng MockMvc hoặc WebTestClient:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class PrometheusEndpointTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void returnsPrometheusExposition() throws Exception {
        mockMvc.perform(get("/actuator/prometheus"))
            .andExpect(status().isOk())
            .andExpect(content().string(
                containsString("orders_completed")
            ));
    }
}
~~~

Trước khi gọi endpoint, test cần tạo một sự kiện nghiệp vụ hoặc đăng ký meter có giá trị xác định. Nếu endpoint không được expose hoặc dependency Prometheus registry không có, test cần phản ánh đúng cấu hình ứng dụng.

MockMvc kiểm tra endpoint trong ứng dụng. Nó không chứng minh Prometheus server bên ngoài đã scrape endpoint này thành công.

## Kiểm thử exporter với receiver giả lập

### Khi nào dùng mock HTTP receiver?

Với registry push như OTLP/HTTP, một mock HTTP server có thể xác nhận exporter gửi request đến đúng endpoint, dùng đúng method, content type và payload. Cách này hữu ích để kiểm tra cấu hình URL, header, TLS test hoặc lỗi HTTP mà không cần backend đầy đủ.

Các điều cần xác minh:

- Request được gửi đến đúng path, thường là /v1/metrics cho OTLP metrics.
- Transport đúng với cấu hình: OTLP/HTTP hay OTLP/gRPC.
- Content type và encoding phù hợp với exporter.
- Resource attributes như service.name có trong payload.
- Metric name, unit, attributes và data point có đúng.
- Histogram hoặc temporality phù hợp với cấu hình.
- Exporter xử lý response lỗi và timeout theo chính sách của nó.

Nếu dùng mock HTTP receiver, việc chỉ xác nhận request đến không chứng minh payload được Collector hoặc backend chấp nhận. Nếu cần kiểm tra cấu trúc payload, giải mã OTLP protobuf hoặc dùng receiver có khả năng parse và xác minh metric data.

### Chú ý chu kỳ export

OTLP MeterRegistry thường export theo step/chu kỳ. Test cần cấu hình chu kỳ phù hợp và chờ request đến receiver bằng cơ chế await có giới hạn. Không giả định increment xong thì HTTP request được gửi đồng bộ ngay lập tức.

Tránh dùng một Thread.sleep ngắn cố định rồi kết luận exporter không hoạt động. Dùng Awaitility hoặc polling có timeout để chờ điều kiện quan sát được, đồng thời giữ test duration có giới hạn.

Không đóng registry trước khi chu kỳ export cần kiểm tra đã diễn ra, trừ khi implementation và test đang chủ đích kiểm tra hành vi shutdown. Cần xác minh cách phiên bản registry flush hoặc dừng scheduler khi close.

## End-to-end test qua hệ thống nhận

### Prometheus pull pipeline

Với Prometheus, ứng dụng expose endpoint metrics và Prometheus chủ động scrape. End-to-end test nên chạy cả ứng dụng và Prometheus trong môi trường test:

1. Khởi động ứng dụng với Prometheus registry và endpoint được expose.
2. Khởi động Prometheus với scrape target trỏ đến endpoint ứng dụng.
3. Gửi một workload xác định vào ứng dụng.
4. Chờ ít nhất một scrape thành công sau khi workload hoàn tất.
5. Truy vấn Prometheus HTTP API cho metric và label dự kiến.
6. Xác minh giá trị phù hợp với workload và semantics của meter.

Có thể dùng Testcontainers hoặc môi trường container test riêng. Khi truy vấn, phân biệt metric counter cumulative với rate/increase theo cửa sổ. Một scrape chưa xảy ra hoặc target down không phải lỗi instrumentation trong code; đó là lỗi pipeline scrape.

### OTLP push qua OpenTelemetry Collector

Với OTLP, ứng dụng gửi metrics đến Collector. Một end-to-end test có thể:

1. Khởi động Collector với OTLP receiver đúng protocol và port.
2. Cấu hình pipeline metrics và exporter đến backend test có thể truy vấn.
3. Khởi động ứng dụng với Micrometer OTLP registry trỏ đến Collector.
4. Phát workload có số lượng và outcome xác định.
5. Chờ registry export và Collector xử lý dữ liệu.
6. Truy vấn backend để xác minh metric, resource attributes, tags và giá trị.
7. Kiểm tra lỗi export hoặc receiver nếu dữ liệu không xuất hiện.

Ví dụ cấu hình receiver OTLP/HTTP tối giản trong Collector:

~~~yaml
receivers:
  otlp:
    protocols:
      http:
        endpoint: 0.0.0.0:4318

processors:
  batch:

exporters:
  debug:
    verbosity: detailed

service:
  pipelines:
    metrics:
      receivers: [otlp]
      processors: [batch]
      exporters: [debug]
~~~

Debug exporter phù hợp để smoke test hoặc xem payload trong log. Với assertion tự động, nên chuyển tiếp sang test exporter/backend có thể truy vấn dữ liệu hoặc dùng receiver test chuyên biệt. Chỉ thấy log debug không chứng minh metric đã được lưu trong backend production tương tự.

Nếu dùng OTLP/gRPC, Collector phải mở protocol gRPC và exporter phải dùng cùng transport. Không trỏ HTTP exporter vào cổng gRPC hoặc nhầm endpoint traces với metrics.

### Backend nhận là tiêu chuẩn cuối cùng của pipeline

Một integration test có thể xác nhận request HTTP được gửi, nhưng backend vẫn có thể từ chối dữ liệu vì schema, resource, label hoặc temporality. Với thay đổi quan trọng về exporter, Collector hoặc backend, cần ít nhất một test end-to-end có thể truy vấn dữ liệu đã nhận.

Nếu backend không có API query thuận tiện, dùng test receiver có thể parse payload và assert metric data. Mục tiêu là xác minh dữ liệu đến đúng ranh giới nhận và được diễn giải đúng, không chỉ xác minh socket đã mở.

## Kiểm tra histogram, unit và resource attributes

Một test exporter hoặc backend cần kiểm tra nhiều hơn tên metric:

- **Metric name:** tên sau NamingConvention có đúng không?
- **Unit:** Timer có xuất thời gian theo đơn vị mà backend mong đợi không?
- **Attributes/tags:** key và value có đúng, không chứa ID duy nhất không?
- **Resource:** service.name, service.instance.id và environment có đúng không?
- **Histogram:** bucket boundaries, count và sum có khớp không?
- **Temporality:** cumulative hoặc delta có phù hợp với backend không?
- **Timestamp:** dữ liệu có nằm trong khoảng test run không?
- **Exemplar:** nếu bật, liên kết trace có xuất đúng mà không tạo metric tag không?

Không so sánh raw exposition giữa các registry khác nhau như thể chúng có cùng naming convention. Prometheus có thể chuẩn hóa tên và đơn vị; OTLP dùng cấu trúc metric data riêng. So sánh theo semantics của meter và dữ liệu sau khi backend diễn giải.

## Kiểm thử lỗi và độ bền của pipeline

Một hệ thống quan sát cần được kiểm tra cả khi receiver hoặc backend gặp sự cố. Các tình huống nên có:

- Receiver không chạy hoặc DNS không phân giải.
- HTTP 4xx/5xx hoặc gRPC status lỗi.
- TLS certificate hoặc authentication sai.
- Network timeout hoặc kết nối bị reset.
- Collector quá tải hoặc queue đầy.
- Backend tạm thời không nhận dữ liệu.
- Ứng dụng shutdown trong lúc còn dữ liệu chờ export.

Mục tiêu là xác nhận lỗi telemetry được xử lý theo chính sách mà ứng dụng chọn và không làm hỏng nghiệp vụ. Với exporter bất đồng bộ, lỗi có thể được ghi log hoặc retry mà không truyền trực tiếp về request thread; hành vi cụ thể phụ thuộc registry/exporter.

Không khẳng định mọi exporter luôn retry hoặc luôn fail-open. Hãy kiểm tra implementation, cấu hình retry/queue/timeout và quan sát log/health trong phiên bản đang dùng. Nếu yêu cầu nghiệp vụ là không phụ thuộc backend metrics, test cần chứng minh request vẫn hoàn tất khi receiver metrics ngừng hoạt động.

Cũng cần kiểm tra shutdown: dữ liệu cuối cùng có được export theo lifecycle của registry hay không, thời gian chờ shutdown có phù hợp không và ứng dụng có dừng scheduler/exporter đúng cách không.

## Tránh test dễ sai hoặc khó bảo trì

| Cách làm | Vấn đề | Cách thay thế |
|---|---|---|
| Mock toàn bộ MeterRegistry | Không kiểm tra semantics registry, filter hay meter | Dùng SimpleMeterRegistry cho unit test |
| Dùng SimpleMeterRegistry để tuyên bố OTLP hoạt động | Registry không gửi network | Test exporter với receiver |
| Chỉ kiểm tra Prometheus scrape() | Chưa có Prometheus server scrape và lưu dữ liệu | Chạy Prometheus và truy vấn API |
| Assert toàn bộ chuỗi exposition | Dễ vỡ khi format/naming thay đổi | Parse sample hoặc kiểm tra tên/label cần thiết |
| Dùng sleep cố định cho OTLP step | Test chập chờn theo máy và scheduler | Await condition có timeout |
| Dùng registry global giữa test | Meter/count bị rò giữa test | Registry riêng cho từng test |
| So Timer với thời gian test tuyệt đối | Scheduler và GC làm kết quả dao động | Ghi duration xác định hoặc dùng tolerance |
| Đưa run ID vào metric tag | Cardinality tăng theo từng lần chạy | Dùng DB fixture, log hoặc test context |
| Chỉ test HTTP request được gửi | Backend có thể từ chối payload | Test Collector/backend có thể truy vấn |
| Không test receiver down | Không biết tác động đến nghiệp vụ | Test timeout, lỗi receiver và shutdown |

## Quy trình lựa chọn tầng kiểm thử

Với mỗi thay đổi instrumentation, có thể đi theo quy trình:

1. **Xác định hợp đồng meter:** tên, loại, đơn vị, tag và sự kiện được đo.
2. **Unit test:** dùng SimpleMeterRegistry để kiểm tra count, duration, value và filter.
3. **Service test:** xác minh meter được ghi ở đúng nhánh nghiệp vụ, kể cả success/failure.
4. **Spring integration test:** xác minh binder, Observation/AOP, property và registry auto-configuration.
5. **Endpoint test:** kiểm tra Actuator hoặc Prometheus exposition của ứng dụng.
6. **Exporter test:** xác nhận protocol, path, headers, resource và payload đến receiver giả lập.
7. **End-to-end test:** chạy Prometheus hoặc Collector/backend và truy vấn metric đã nhận.
8. **Failure test:** ngắt receiver hoặc tạo timeout để xác minh hành vi khi pipeline lỗi.
9. **Cleanup:** đóng registry, container và server test để tránh rò thread hoặc port.
10. **Report:** ghi phiên bản dependency, cấu hình registry, workload, thời gian chờ export và kết quả đối chiếu.

Không cần chạy toàn bộ backend stack cho mỗi lần sửa một Counter đơn giản. Nhưng thay đổi exporter, endpoint, resource attributes, temporality hoặc cấu hình Collector cần kiểm thử tích hợp ở tầng tương ứng.

## Checklist tách unit test và integration test

Trước khi hoàn tất kiểm thử metrics, hãy xác minh:

1. Unit test dùng registry thật trong bộ nhớ thay vì mock toàn bộ API không?
2. Counter, Timer, Gauge và DistributionSummary có test theo semantics riêng không?
3. Timer test dùng duration xác định hoặc tolerance hợp lý không?
4. Gauge test giữ strong reference đến nguồn dữ liệu không?
5. Tag và cardinality được kiểm tra bằng tập giá trị hữu hạn không?
6. MeterFilter và binder được kiểm tra ở đúng registry/context không?
7. Spring integration test khởi tạo ApplicationContext thật không?
8. Observation/AOP test gọi bean qua context/proxy khi cần không?
9. Endpoint test có phân biệt exposition của ứng dụng với server scrape thật không?
10. Exporter test xác minh protocol, path, payload và resource attributes không?
11. End-to-end test truy vấn được metric ở hệ thống nhận không?
12. Test có chờ step/export/scrape bằng điều kiện có timeout không?
13. Có kiểm tra histogram, unit, temporality và label semantics không?
14. Có kiểm tra receiver lỗi và tác động đến nghiệp vụ không?
15. Registry, server và container test có được cleanup không?

## Kết luận

Unit test và integration test trả lời hai câu hỏi khác nhau. Unit test với SimpleMeterRegistry xác nhận instrumentation đăng ký và ghi meter đúng trong ứng dụng. Integration test qua Spring Boot, endpoint, exporter, receiver và backend xác nhận dữ liệu được chuyển và diễn giải đúng ở hệ thống nhận.

Hãy dùng registry trong bộ nhớ để kiểm tra nhanh Counter, Timer, Gauge, DistributionSummary, tag và filter; dùng Spring context để kiểm tra binder, Observation/AOP và Actuator; dùng receiver giả lập để kiểm tra contract exporter; và dùng Prometheus hoặc OpenTelemetry Collector cùng backend có thể truy vấn cho end-to-end test. Chờ export/scrape theo điều kiện có timeout, kiểm tra lỗi receiver và cleanup tài nguyên test. Tách đúng tầng giúp test nhanh, ổn định và vẫn chứng minh được toàn bộ đường đi của telemetry khi cần.
