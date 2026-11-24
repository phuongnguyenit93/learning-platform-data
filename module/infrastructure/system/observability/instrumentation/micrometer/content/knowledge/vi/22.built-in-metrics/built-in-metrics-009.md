# Phân biệt metric tự động, metric cần bật và metric cần binder bổ sung

## Ba cách một metric xuất hiện trong ứng dụng

Trong ứng dụng Java dùng Spring Boot và Micrometer, không phải metric nào cũng được tạo theo cùng một cách. Có metric được framework tự đăng ký khi ứng dụng khởi động; có metric đã có instrumentation nhưng cần bật hoặc cấu hình thêm; cũng có số đo mà thư viện hay nghiệp vụ không cung cấp sẵn nên ứng dụng phải bổ sung binder.

Phân biệt ba trường hợp giúp xác định đúng nơi cần cấu hình khi một metric không xuất hiện:

1. **Metric tự động:** Spring Boot hoặc Micrometer tự đăng ký khi dependency và bean cần thiết có mặt.
2. **Metric cần bật hoặc cấu hình:** instrumentation đã tồn tại, nhưng bị tắt bởi cấu hình hoặc cần bật thêm một tính năng thống kê như histogram, percentile hay annotation support.
3. **Metric cần binder bổ sung:** chưa có thành phần nào đăng ký số đo đó; cần dùng binder có sẵn của Micrometer/thư viện hoặc tự viết MeterBinder.

Một metric chỉ xuất hiện trong backend khi các bước liên quan đều hoàn tất: instrumentation tạo meter, registry chấp nhận meter, exporter công bố dữ liệu và pipeline nhận dữ liệu hoạt động. Có dependency Actuator không đồng nghĩa mọi metric đều được bật; có meter trong registry cũng không đảm bảo nó đã được gửi đến backend.

## Metric tự động: framework đăng ký khi điều kiện phù hợp

### Vai trò của Spring Boot Actuator và Micrometer

Spring Boot Actuator tích hợp Micrometer để cung cấp các phép đo vận hành. Khi dependency Actuator và registry phù hợp có mặt, auto-configuration tạo các binder và instrumentation tích hợp với những thành phần ứng dụng đang chạy.

Một số nhóm phổ biến gồm:

| Nhóm | Ví dụ metric | Điều kiện thường gặp |
|---|---|---|
| JVM | jvm.memory.used, jvm.threads.live, jvm.gc.pause | Ứng dụng chạy trên JVM và metrics auto-configuration hoạt động |
| Class loader | jvm.classes.loaded, jvm.classes.unloaded | JVM metrics binder được cấu hình |
| Process | process.cpu.usage, process.uptime | Hệ điều hành và process metrics binder được hỗ trợ |
| System | system.cpu.usage, system.load.average.1m | Nền tảng cung cấp thông tin hệ thống tương ứng |
| HTTP server | http.server.requests | Ứng dụng dùng server được Spring Boot hỗ trợ và request instrumentation được cấu hình |
| Data source | jdbc.connections.active, jdbc.connections.max | Có DataSource bean và pool có thể được quan sát |
| Cache | cache.gets, cache.puts, cache.evictions | Có CacheManager/cache provider được hỗ trợ và cache được bind |
| Executor | executor.active, executor.queued | Executor được framework hoặc binder hỗ trợ và được đăng ký |
| Logback | logback.events | Dùng Logback và binder tương ứng có mặt |

Đây là các nhóm thường gặp, không phải cam kết mọi meter luôn tồn tại trong mọi ứng dụng. Tên và điều kiện cụ thể phụ thuộc phiên bản Spring Boot, Micrometer, dependency, loại server, cache provider, connection pool và cấu hình.

### Auto-configuration dựa trên dependency và bean

Spring Boot thường dùng điều kiện classpath và bean để quyết định tạo instrumentation nào. Ví dụ:

- Nếu ứng dụng có DataSource và pool được hỗ trợ, binder có thể đăng ký metrics của connection pool.
- Nếu ứng dụng có CacheManager tương thích, các cache có thể được bind để theo dõi hit, miss, put hoặc eviction.
- Nếu dùng embedded servlet container được hỗ trợ, HTTP server instrumentation có thể tạo metric request.
- Nếu thư viện client được tích hợp với Micrometer và dùng builder do Spring Boot cấu hình, HTTP client metrics có thể được ghi nhận.

Vì vậy, hai ứng dụng cùng dùng Actuator vẫn có danh sách metric khác nhau. Một ứng dụng có HikariCP sẽ có các meter của pool; ứng dụng khác dùng loại DataSource khác có thể có tên, số liệu hoặc mức hỗ trợ khác.

Khi metric không xuất hiện, hãy kiểm tra dependency và bean thực tế trước. Không nên bắt đầu bằng việc viết binder mới nếu Spring Boot đã có binder nhưng điều kiện kích hoạt chưa được đáp ứng.

### Xác minh metric tự động

Có thể kiểm tra registry trong lúc ứng dụng chạy bằng endpoint metrics nếu endpoint được expose, hoặc bằng cách truy vấn MeterRegistry trong test.

Ví dụ kiểm tra tên meter trong Java:

~~~java
@Autowired
MeterRegistry registry;

void inspectMeters() {
    registry.getMeters().forEach(meter ->
        System.out.println(meter.getId().getName())
    );
}
~~~

Đây là cách chẩn đoán trong môi trường phát triển hoặc kiểm thử. Không nên dump toàn bộ danh sách meter vào log thường xuyên trong production nếu registry có nhiều meter.

Với Actuator, endpoint metrics có thể giúp tra cứu một meter cụ thể. Endpoint này thường cần được expose riêng trong cấu hình web; sự hiện diện của endpoint không phải điều kiện để registry push metrics qua OTLP.

## Metric cần bật hoặc cấu hình thêm

### Instrumentation có sẵn nhưng bị tắt

Một meter có thể đã được hỗ trợ nhưng bị cấu hình tắt theo tên. Spring Boot cung cấp nhóm thuộc tính management.metrics.enable để cho phép hoặc từ chối meter.

Ví dụ tắt một meter JVM cụ thể:

~~~yaml
management:
  metrics:
    enable:
      "jvm.memory.used": false
~~~

Hoặc trong cấu hình properties:

~~~properties
management.metrics.enable.jvm.memory.used=false
~~~

Tên cần dùng là tên meter trong Micrometer trước khi registry áp dụng quy tắc đổi tên của backend. Ví dụ, tên trong ứng dụng có thể dùng dấu chấm, trong khi Prometheus xuất tên chuẩn hóa bằng dấu gạch dưới.

Nếu một nhóm metric không xuất hiện, kiểm tra cả cấu hình enable và các MeterFilter được ứng dụng hoặc thư viện đăng ký. Filter có thể từ chối meter ngay cả khi property cho phép.

### Metric có rồi nhưng histogram hoặc percentile chưa bật

Một trường hợp phổ biến là Timer đã tồn tại và count/sum được xuất, nhưng histogram bucket hoặc percentile không xuất hiện. Đây thường là cấu hình phân phối, không phải thiếu binder.

Có thể bật percentile histogram cho một meter cụ thể:

~~~yaml
management:
  metrics:
    distribution:
      percentiles-histogram:
        http.server.requests: true
      slo:
        http.server.requests:
          - 100ms
          - 300ms
          - 1s
~~~

Tên property và cách biểu diễn duration cần được đối chiếu với phiên bản Spring Boot đang dùng. Có thể cấu hình percentile phía client riêng nếu thực sự cần, nhưng percentile phía client và histogram bucket có semantics tổng hợp khác nhau.

Tương tự, cấu hình distribution có thể điều khiển percentile, SLO boundaries, minimum/maximum expected value hoặc expiry/buffer length. Những tùy chọn này làm thay đổi thống kê được công bố và có thể tăng cardinality hoặc bộ nhớ.

### Annotation hoặc instrumentation cần được kích hoạt

Một số API chỉ tạo metric khi ứng dụng đăng ký thành phần hỗ trợ tương ứng. Ví dụ, dùng annotation để đo thời gian cho method không có nghĩa mọi method tự động được instrument. Cần kiểm tra API đang dùng, cấu hình aspect hoặc Observation handler cần thiết, và phiên bản framework.

Với Micrometer, có thể dùng Timer trực tiếp, Observation API hoặc annotation support tùy trường hợp. Nếu chọn annotation, hãy xác nhận component xử lý annotation đã được đăng ký và AOP/proxy hoạt động đúng. Nếu chọn Observation, hãy xác nhận ObservationRegistry và handler tương ứng được cấu hình.

Không nên thêm cả annotation, aspect và Timer thủ công cho cùng một thao tác nếu chúng tạo ra các meter trùng ý nghĩa. Điều đó có thể khiến count hoặc duration bị ghi hai lần.

### Phân biệt bật meter với expose endpoint

Cấu hình endpoint Actuator chỉ quyết định endpoint có thể được truy cập qua HTTP hay không. Ví dụ:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
~~~

Cấu hình này expose các endpoint được liệt kê. Nó không tự tạo JVM, HTTP hoặc business meter.

Ngược lại, meter có thể được đăng ký và gửi qua OTLP push dù endpoint Prometheus không được expose. Cần phân biệt ba câu hỏi:

- Instrumentation có tạo meter không?
- Registry có chấp nhận và xuất meter không?
- Endpoint hoặc exporter có công bố dữ liệu đến nơi tiêu thụ không?

Mỗi bước có cấu hình riêng và lỗi ở mỗi bước có biểu hiện khác nhau.

## Metric cần binder bổ sung

### Khi nào cần binder?

Cần binder bổ sung khi không có auto-configuration hoặc instrumentation sẵn có cho đại lượng cần đo. Ví dụ:

- Độ sâu của một queue do ứng dụng tự quản lý.
- Số tác vụ đang chạy trong một scheduler riêng.
- Số kết nối hoặc trạng thái của client thư viện không tích hợp Micrometer.
- Thống kê từ một thư viện nội bộ chỉ cung cấp API đọc số liệu.
- Số đơn hàng hoàn tất, số giao dịch thất bại hoặc số bản ghi xử lý theo nghiệp vụ.
- Một thành phần hạ tầng có API thống kê nhưng chưa có Micrometer binder tương ứng.

Trước khi tự viết binder, hãy kiểm tra thư viện có cung cấp binder sẵn hoặc Spring Boot đã tự bind bean đó chưa. Việc đăng ký trùng một meter cùng tên và tag có thể tạo xung đột hoặc làm số liệu bị ghi trùng.

### MeterBinder là điểm tích hợp chuẩn

Micrometer định nghĩa interface MeterBinder với phương thức bindTo(MeterRegistry). Binder nhận registry và đăng ký các meter cần thiết.

Ví dụ binder theo dõi độ sâu của queue:

~~~java
public final class JobQueueMetrics implements MeterBinder {

    private final JobQueue queue;

    public JobQueueMetrics(JobQueue queue) {
        this.queue = queue;
    }

    @Override
    public void bindTo(MeterRegistry registry) {
        Gauge.builder(
                "jobs.queue.depth",
                queue,
                JobQueue::size
            )
            .description("So job dang cho xu ly")
            .baseUnit("jobs")
            .register(registry);
    }
}
~~~

Đăng ký binder như một bean:

~~~java
@Configuration(proxyBeanMethods = false)
public class JobMetricsConfiguration {

    @Bean
    MeterBinder jobQueueMetrics(JobQueue queue) {
        return new JobQueueMetrics(queue);
    }
}
~~~

Spring Boot có thể phát hiện các bean MeterBinder và bind chúng vào registry được cấu hình. Nếu ứng dụng tự tạo nhiều registry hoặc dùng composite tùy chỉnh, cần xác minh binder được bind vào đúng registry và đúng số lần.

Trong ví dụ, queue là đối tượng nguồn của Gauge. Binder giữ tham chiếu mạnh đến queue thông qua field, bảo đảm đối tượng vẫn có thể được đọc trong vòng đời của binder. Hàm size nên nhẹ và an toàn khi được gọi từ luồng thu thập metrics.

### Chọn loại meter theo ngữ nghĩa

Binder không quyết định loại meter thay cho người viết. Cần chọn loại phù hợp với đại lượng:

| Đại lượng | Meter phù hợp | Lý do |
|---|---|---|
| Tổng số job đã hoàn tất | Counter | Sự kiện tích lũy |
| Số job hiện đang chờ | Gauge | Trạng thái hiện tại |
| Thời gian xử lý mỗi job | Timer | Ghi từng thời lượng |
| Kích thước batch | DistributionSummary | Phân phối giá trị số |
| Count và tổng thời gian do thư viện tự tích lũy | FunctionCounter/FunctionTimer | Đọc thống kê có sẵn |

Không dùng Counter để biểu diễn số job đang chờ vì giá trị có thể giảm. Không dùng Gauge để ghi tổng số sự kiện vì Gauge chỉ phản ánh trạng thái tại thời điểm đọc.

### Binder nên đăng ký meter một lần

MeterBinder thường được bind trong giai đoạn khởi tạo registry. Không tạo lại binder hoặc đăng ký meter trong mỗi request. Meter được định danh bằng tên, loại và tag; số tổ hợp tag nên có giới hạn rõ ràng.

Ví dụ, tag queue_name có thể hợp lý nếu ứng dụng chỉ có vài queue cố định. Không đưa job ID, request ID hoặc user ID vào tag vì mỗi giá trị duy nhất có thể tạo một time series mới.

Nếu binder theo dõi nhiều queue, có thể lặp qua tập queue ổn định khi bind. Nếu queue được tạo và hủy động, cần thiết kế lifecycle meter rõ ràng, giới hạn cardinality và xử lý việc gỡ meter khi queue kết thúc nếu phù hợp.

## Bảng quyết định: tự động, cần bật hay cần binder

| Dấu hiệu | Phân loại | Việc cần làm |
|---|---|---|
| Meter xuất hiện khi có Actuator và bean/dependency tương ứng | Tự động | Kiểm tra điều kiện auto-configuration và registry |
| Meter được hỗ trợ nhưng property hoặc filter đang từ chối | Cần bật/cấu hình | Điều chỉnh management.metrics.enable hoặc MeterFilter |
| Timer có count/sum nhưng thiếu bucket/percentile | Cần bật/cấu hình thống kê | Cấu hình distribution histogram/SLO/percentile |
| Annotation không tạo meter | Cần bật instrumentation hỗ trợ | Kiểm tra aspect, ObservationRegistry và AOP |
| Không có binder cho thư viện hoặc đại lượng nghiệp vụ | Cần binder bổ sung | Dùng binder thư viện hoặc tự viết MeterBinder |
| Có meter trong registry nhưng backend không thấy | Lỗi export/pipeline | Kiểm tra registry exporter, endpoint, transport và Collector |
| Endpoint metrics không truy cập được nhưng OTLP vẫn nhận dữ liệu | Endpoint exposure riêng | Kiểm tra Actuator web exposure và bảo mật |

Bảng này giúp khoanh vùng nguyên nhân. Không nên mặc định metric vắng mặt đồng nghĩa cần viết binder; trước tiên xác định nó thuộc lớp nào.

## Quy trình tìm nguyên nhân khi metric không xuất hiện

Có thể đi theo thứ tự sau:

1. **Xác định meter name mong đợi.** Tìm tên trong tài liệu binder hoặc kiểm tra Meter.Id của instrumentation.
2. **Kiểm tra dependency và bean.** Xác nhận Actuator, registry exporter, client, DataSource, CacheManager hoặc executor liên quan thực sự có mặt.
3. **Kiểm tra auto-configuration.** Xác nhận điều kiện classpath/bean của binder được đáp ứng.
4. **Kiểm tra enable property.** Xem management.metrics.enable có tắt meter không.
5. **Kiểm tra MeterFilter.** Tìm filter DENY, maximum allowable limits hoặc filter tùy chỉnh.
6. **Kiểm tra cấu hình thống kê.** Nếu chỉ thiếu histogram, percentile hoặc SLO, xem management.metrics.distribution.
7. **Kiểm tra registry.** Xác nhận meter đã được đăng ký trong MeterRegistry.
8. **Kiểm tra exporter.** Xác nhận endpoint, transport, authentication và chu kỳ xuất.
9. **Kiểm tra backend.** Xem Collector, Prometheus hoặc nền tảng giám sát có nhận đúng signal không.
10. **Chỉ bổ sung binder khi thực sự chưa có instrumentation.**

Quy trình này tách lỗi instrumentation khỏi lỗi registry và lỗi vận chuyển. Nó cũng tránh tạo thêm binder trong khi meter đã được framework đăng ký nhưng bị filter hoặc exporter chặn.

## Tích hợp với nhiều registry

Một ứng dụng có thể xuất cùng meter đến Prometheus, OTLP hoặc backend khác. MeterBinder có thể được bind vào các registry mà framework quản lý, nhưng registry tùy chỉnh có thể có lifecycle và cấu hình riêng.

Nếu dùng CompositeMeterRegistry, hãy xác định meter được đăng ký trên composite hay registry thành phần. Filter, naming convention và exporter có thể khác nhau giữa các registry. Một meter xuất hiện ở Prometheus nhưng không có ở OTLP có thể là vấn đề cấu hình registry hoặc filter riêng, không nhất thiết là binder thiếu.

Khi chuyển backend, nên kiểm tra lại:

- Tên meter sau NamingConvention.
- Đơn vị xuất.
- Cumulative hoặc delta temporality.
- Histogram bucket và percentile.
- Resource attributes và meter tags.
- Bộ lọc và giới hạn cardinality.
- Chu kỳ step hoặc scrape/push.

Instrumentation có thể giữ nguyên nhưng cách backend biểu diễn số liệu thay đổi.

## Kiểm thử ba nhóm metrics

### Kiểm tra metric tự động

Dùng Spring Boot integration test để khởi tạo application context với dependency thực tế. Sau đó truy vấn MeterRegistry và xác nhận meter dự kiến xuất hiện khi bean điều kiện có mặt.

Ví dụ kiểm tra:

~~~java
assertThat(registry.find("jvm.memory.used").gauge())
    .isNotNull();
~~~

Tên meter và loại meter cần được xác minh theo phiên bản Micrometer đang dùng. Không giả định mọi JVM metric có cùng loại hoặc tên giữa các phiên bản.

### Kiểm tra metric cần bật

Khởi tạo context với cấu hình bật và tắt:

~~~java
@SpringBootTest(properties = {
    "management.metrics.enable.jvm.memory.used=false"
})
class MetricsConfigurationTest {

    @Autowired
    MeterRegistry registry;

    @Test
    void disabledMeterIsNotRegistered() {
        assertThat(registry.find("jvm.memory.used").gauge())
            .isNull();
    }
}
~~~

Ví dụ minh họa kiểm tra property theo tên meter. Cần dùng đúng tên và loại meter thực tế, đồng thời xác minh cách phiên bản Spring Boot áp dụng property. Có thể kiểm tra thêm cấu hình histogram để phân biệt meter bị tắt với thống kê phân phối chưa được bật.

### Kiểm tra binder bổ sung

Với binder tùy chỉnh, dùng SimpleMeterRegistry để xác minh meter được đăng ký và phản ánh nguồn:

~~~java
SimpleMeterRegistry registry = new SimpleMeterRegistry();
JobQueue queue = new JobQueue();

new JobQueueMetrics(queue).bindTo(registry);

queue.enqueue(new Job());

assertThat(registry.get("jobs.queue.depth")
    .gauge()
    .value()).isEqualTo(1.0);
~~~

Kiểm thử này xác nhận Gauge đọc trạng thái queue. Cần thêm kiểm thử cho nhiều queue, vòng đời queue và cardinality nếu binder tạo meter theo từng nhóm.

### Kiểm tra exporter

Cuối cùng, kiểm thử endpoint hoặc payload của registry exporter. Một meter có trong SimpleMeterRegistry không chứng minh Prometheus hoặc OTLP nhận dữ liệu. Với exporter thực tế, xác nhận tên, unit, tags, temporality và histogram theo đúng backend.

## Những sai lầm thường gặp

**Cho rằng có Actuator thì mọi metric đều tự xuất hiện.** Auto-configuration phụ thuộc dependency, bean và điều kiện của từng binder.

**Viết binder mới trước khi kiểm tra binder có sẵn.** Có thể tạo meter trùng hoặc ghi số liệu hai lần. Kiểm tra auto-configuration và thư viện trước.

**Nhầm meter bị tắt với histogram chưa bật.** Timer vẫn có thể xuất count/sum trong khi bucket hoặc percentile chưa được cấu hình.

**Nhầm endpoint exposure với đăng ký meter.** Ẩn /actuator/metrics hoặc /actuator/prometheus không tự dừng registry push.

**Dùng sai meter name trong property.** Cấu hình được đánh giá trên tên Micrometer; tên sau khi exporter chuẩn hóa có thể khác.

**Cho rằng MeterBinder tự tạo dữ liệu.** Binder chỉ kết nối đối tượng nguồn với registry. Nguồn phải được cập nhật đúng và có lifecycle phù hợp.

**Đăng ký binder hoặc meter trong mỗi request.** Điều này có thể tạo nhiều meter trùng hoặc cardinality không kiểm soát. Đăng ký trong lifecycle khởi tạo.

**Dùng Gauge cho tổng sự kiện hoặc Counter cho trạng thái hiện tại.** Chọn meter theo semantics của đại lượng.

**Chỉ kiểm tra MeterRegistry mà không kiểm tra exporter.** Meter có thể tồn tại trong ứng dụng nhưng không đến backend do endpoint, transport hoặc Collector sai.

## Checklist lựa chọn cách tạo metric

Trước khi triển khai một metric, hãy xác minh:

1. Spring Boot hoặc Micrometer đã tự cung cấp meter này chưa?
2. Dependency và bean cần thiết có mặt không?
3. Metric có bị management.metrics.enable hoặc MeterFilter từ chối không?
4. Chỉ thiếu histogram, percentile hoặc SLO hay toàn bộ meter chưa tồn tại?
5. Annotation/Observation có cần aspect hoặc handler bổ sung không?
6. Thư viện đã có MeterBinder chính thức chưa?
7. Nếu cần tự viết binder, nguồn dữ liệu có API đọc ổn định và nhẹ không?
8. Loại meter có đúng ngữ nghĩa: Counter, Gauge, Timer, DistributionSummary hay Function meter?
9. Binder có được đăng ký một lần và giữ đối tượng nguồn đủ lâu không?
10. Tag có cardinality thấp và tập giá trị hữu hạn không?
11. Meter đã xuất qua registry và exporter thực tế chưa?
12. Kiểm thử có bao phủ auto-configuration, property bật/tắt và binder tùy chỉnh không?

## Kết luận

Metric trong Spring Boot và Micrometer có thể đến từ ba nguồn. Metric tự động được framework đăng ký khi dependency và bean phù hợp; metric cần bật đã có instrumentation nhưng cần cấu hình enable, distribution hoặc annotation; metric cần binder bổ sung khi chưa có thành phần nào kết nối nguồn dữ liệu với registry.

Hãy kiểm tra dependency, bean, auto-configuration và filter trước khi viết binder. Nếu meter đã tồn tại nhưng thiếu histogram hoặc percentile, hãy điều chỉnh cấu hình thống kê. Chỉ tạo MeterBinder khi thực sự chưa có instrumentation, chọn meter theo đúng ngữ nghĩa, giữ nguồn dữ liệu ổn định và kiểm tra cả registry lẫn exporter. Cách phân loại này giúp tránh meter trùng, giảm công việc bảo trì và giữ số liệu vận hành nhất quán giữa các môi trường.
