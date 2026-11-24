# Đánh giá API mới như MeterProvider hoặc MeterConvention theo phiên bản thực tế

Khi nâng cấp Micrometer, tên một API mới xuất hiện trong tài liệu hiện hành chưa có nghĩa dự án đang dùng đã có API đó. Cần xác định chính xác phiên bản micrometer-core được resolve, phiên bản Spring Boot/BOM đang quản lý dependency và phiên bản của registry implementation. Sau đó mới đánh giá API có sẵn, mục đích sử dụng và tác động đến metric schema.

Hai API đáng chú ý là Meter.MeterProvider và MeterConvention. MeterProvider giúp tái sử dụng một cấu hình meter chung rồi thêm tags thay đổi theo từng kết quả. MeterConvention mô tả tên chuẩn và tags của một meter thuộc instrumentation cụ thể. Chúng giải quyết hai vấn đề khác nhau và không thay thế MeterFilter, NamingConvention hay ObservationConvention.

Theo tài liệu Micrometer hiện hành được đối chiếu cho bài này, Meter.MeterProvider có từ Micrometer 1.12.0; MeterConvention và SimpleMeterConvention có từ 1.16.0; builder mới để tùy biến conventions của một số JVM binders có từ 1.18.0. Vì vậy, khi đọc ví dụ trên tài liệu mới, hãy kiểm tra mốc API thay vì sao chép nguyên mẫu vào một dự án đang chạy phiên bản cũ hơn.

Bài học thuộc module OBSERVABILITY_INSTRUMENTATION_MICROMETER. Module này hướng dẫn sử dụng Micrometer để đo lường ứng dụng Java bằng counter, gauge, timer, distribution summary và nhãn có kiểm soát; tích hợp Spring Boot, xuất metrics đến hệ giám sát, kiểm soát cardinality, kiểm thử instrumentation và diễn giải số đo vận hành.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Xác định phiên bản Micrometer thực tế mà Gradle hoặc Maven resolve.
- Phân biệt API có từ 1.12.0, 1.16.0 và 1.18.0.
- Dùng Meter.MeterProvider để tái sử dụng builder với tags động.
- Dùng MeterConvention để chuẩn hóa tên và tags cho một loại instrumentation.
- Nhận biết các JVM binder đã cung cấp builder tùy biến convention.
- Phân biệt MeterProvider của Micrometer với MeterProvider trong OpenTelemetry.
- Phân biệt MeterConvention, NamingConvention, MeterFilter và ObservationConvention.
- Đánh giá cardinality, metric schema và tính tương thích dashboard khi đổi convention.
- Viết test xác nhận meter ID, tags và giá trị sau khi áp dụng API mới.

## 1. Vì sao phải đánh giá API theo phiên bản thực tế?

Tài liệu Micrometer hiện hành thường hiển thị ví dụ từ phiên bản mới nhất. Một API có thể đã được thêm sau khi dự án khóa phiên bản dependency, hoặc một constructor cũ có thể đã bị deprecated trong bản mới nhưng vẫn đang được dùng trong ứng dụng.

Có ba phiên bản cần phân biệt:

1. Phiên bản Spring Boot của ứng dụng.
2. Phiên bản Micrometer do Spring Boot BOM hoặc dependency management resolve.
3. Phiên bản registry implementation và các module Micrometer liên quan.

Thông thường Spring Boot quản lý một tập phiên bản Micrometer tương thích. Nếu chỉ nâng micrometer-core mà giữ các registry hoặc micrometer-observation ở phiên bản khác, ứng dụng có thể gặp lỗi compile, NoSuchMethodError hoặc hành vi không nhất quán.

### Mốc API cần nhớ

| API | Có từ | Ý nghĩa |
| --- | --- | --- |
| Meter.MeterProvider | Micrometer 1.12.0 | Tạo meter theo mẫu builder chung, bổ sung tags khi cần |
| MeterConvention | Micrometer 1.16.0 | Mô tả tên chuẩn và tags của một meter cụ thể |
| SimpleMeterConvention | Micrometer 1.16.0 | Triển khai đơn giản của MeterConvention |
| JVM binder convention interfaces | Micrometer 1.16.0 | Cung cấp convention cho các meter thuộc JVM binders |
| Builder tùy biến convention trên một số JVM binders | Micrometer 1.18.0 | Cấu hình convention riêng bằng builder API |
| openTelemetryConventions() trên các binder hỗ trợ | Micrometer 1.18.0 | Chọn bộ convention OpenTelemetry được binder hỗ trợ |

Mốc trong bảng là mốc xuất hiện của API Micrometer tương ứng, không phải mốc Spring Boot. Spring Boot cần một dependency management tương thích để ứng dụng dùng được phiên bản đó.

### Kiểm tra phiên bản dependency đã resolve

Với Gradle:

~~~bash
./gradlew dependencyInsight --dependency micrometer-core --configuration runtimeClasspath
~~~

Nếu cần kiểm tra API ở compile classpath:

~~~bash
./gradlew dependencyInsight --dependency micrometer-core --configuration compileClasspath
~~~

Với Maven:

~~~bash
mvn dependency:tree -Dincludes=io.micrometer:micrometer-core
~~~

Nếu dự án dùng Spring Boot BOM, kiểm tra dependency management đang áp dụng và tránh ghi đè riêng một module Micrometer bằng phiên bản khác. Các module như micrometer-core, micrometer-observation, registry và tracing bridge cần được giữ tương thích theo BOM hoặc Micrometer BOM phù hợp.

Không dựa vào version ghi trong một đoạn build file nếu dependency có thể bị constraint, platform, dependency management hoặc plugin khác ghi đè. Kết quả dependency insight/tree mới cho biết phiên bản thực sự được resolve.

## 2. Meter.MeterProvider giải quyết việc tạo meter với tags động

Một trường hợp phổ biến là ghi Timer cho một công việc, trong đó tag outcome chỉ biết được sau khi công việc kết thúc.

Cách làm trực tiếp:

~~~java
Timer.Sample sample = Timer.start(registry);

Result result = job.execute();

Timer timer = Timer.builder("job.execution")
        .tag("job.name", "reconcile")
        .tag("outcome", result.outcome())
        .register(registry);

sample.stop(timer);
~~~

Cách này hợp lệ nhưng mỗi lần thực thi lại tạo Timer.Builder và lặp lại phần cấu hình cố định. Khi có nhiều meter hoặc nhiều luồng công việc, phần cấu hình chung trở nên dài và khó giữ nhất quán.

MeterProvider cho phép tạo một template một lần:

~~~java
import io.micrometer.core.instrument.Meter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

public final class JobMetrics {

    private final Meter.MeterProvider<Timer> timerProvider;
    private final MeterRegistry registry;

    public JobMetrics(MeterRegistry registry) {
        this.registry = registry;

        this.timerProvider = Timer.builder("job.execution")
                .description("Thời gian thực thi job")
                .tag("job.name", "reconcile")
                .withRegistry(registry);
    }

    public void execute(Job job) {
        Timer.Sample sample = Timer.start(registry);
        String outcome = "success";

        try {
            job.execute();
        } catch (RuntimeException | Error error) {
            outcome = "failure";
            throw error;
        } finally {
            sample.stop(timerProvider.withTag("outcome", outcome));
        }
    }
}
~~~

Phần cố định được định nghĩa trong builder: tên meter, description và tag job.name. Phần thay đổi theo lần thực thi được thêm qua withTag() khi lấy Timer từ provider.

### Cách hoạt động

1. Timer.builder() định nghĩa template.
2. withRegistry(registry) tạo MeterProvider cho registry đó.
3. withTag() hoặc withTags() bổ sung các tag động.
4. Provider đăng ký hoặc lấy meter tương ứng với tổ hợp tên và tags.
5. Timer.Sample.stop(timer) ghi thời lượng vào Timer được chọn.

Các tags trong builder được kết hợp với tags truyền vào provider. Nên tránh dùng cùng một key ở cả hai nơi với giá trị khác nhau vì điều đó làm convention khó hiểu và có thể gây xung đột khi tạo Meter.Id.

### Các meter hỗ trợ MeterProvider

Theo API hiện hành, MeterProvider được hỗ trợ cho:

- Counter
- Timer
- LongTaskTimer
- DistributionSummary

Không phải mọi Meter đều có withRegistry() trả về MeterProvider. Ví dụ Gauge không dùng mẫu builder này để tạo meter theo tags động.

### Dùng MeterProvider cho Counter

~~~java
Meter.MeterProvider<Counter> jobCounter =
        Counter.builder("job.executions")
                .description("Số lần thực thi job")
                .tag("job.name", "reconcile")
                .withRegistry(registry);

// Ghi nhận kết quả với tag có tập giá trị hữu hạn.
jobCounter.withTag("outcome", "success").increment();
jobCounter.withTag("outcome", "failure").increment();
~~~

MeterProvider hữu ích khi meter có nhiều thuộc tính cố định và chỉ một vài tags thay đổi tại thời điểm ghi nhận. Nó giúp tránh lặp builder và gom cấu hình chung về một nơi.

## 3. Khi nào MeterProvider thực sự hữu ích?

Không phải mọi meter đều cần MeterProvider. Nếu chỉ tạo một Counter với tags cố định, registry.counter() thường ngắn gọn hơn:

~~~java
Counter counter = registry.counter(
        "checkout.completed",
        "channel", "web"
);
~~~

Nên cân nhắc MeterProvider khi:

- Nhiều lần ghi cùng một loại meter có chung name, description, unit và phần lớn tags.
- Một hoặc hai tags chỉ biết được sau khi xử lý xong.
- Muốn tập trung cấu hình cố định trong constructor hoặc component cấu hình.
- Code hiện tại tạo builder lặp lại trong một hot path và muốn giảm boilerplate.
- Cần đảm bảo nhiều nhánh ghi nhận cùng dùng một meter schema.

Không nên dùng MeterProvider chỉ vì API mới hơn. Với một meter đơn giản, nó có thể làm code dài hơn mà không tạo thêm lợi ích.

### Đánh giá chi phí tạo builder

Tài liệu Micrometer nêu một lý do dùng MeterProvider là tránh tạo Timer.Builder mới trong mỗi lần thực thi. Điều này giảm số object builder được tạo và làm code ít lặp hơn. Tuy nhiên, không nên tuyên bố nó luôn tạo ra cải thiện hiệu năng đáng kể.

Nếu đường ghi nhận có lưu lượng rất cao, hãy benchmark với workload thực tế. Chi phí còn phụ thuộc registry, số tag, cache meter, backend và mức độ tranh chấp khi đăng ký meter mới.

MeterProvider không làm cho việc tạo hàng triệu tổ hợp tag trở nên rẻ. Mỗi tổ hợp name và tags mới vẫn có thể tạo một Meter.Id và một time series mới.

## 4. Kiểm soát cardinality khi thêm tags động

MeterProvider làm việc với tags động thuận tiện hơn, nhưng không tự kiểm soát cardinality. Mỗi giá trị tag khác nhau có thể tạo một meter khác nhau.

Ví dụ an toàn:

~~~java
jobCounter.withTag("outcome", "success").increment();
jobCounter.withTag("outcome", "failure").increment();
~~~

Hai giá trị outcome có tập hữu hạn.

Ví dụ rủi ro:

~~~java
jobCounter.withTag("order.id", orderId).increment();
jobCounter.withTag("request.id", requestId).increment();
~~~

Order ID và request ID thường gần như duy nhất. Dùng chúng làm metric tags có thể tạo số lượng time series tăng theo lượng request hoặc đơn hàng.

Nên dùng các nhóm giá trị có giới hạn:

| Tag | Giá trị phù hợp | Tránh |
| --- | --- | --- |
| outcome | success, failure, timeout | Exception message |
| region | ap-southeast-1, eu-west-1 | Region do người dùng nhập tự do |
| channel | web, mobile, partner | URL hoặc user agent đầy đủ |
| job.name | reconcile, cleanup, export | Job ID duy nhất mỗi lần chạy |
| status | accepted, rejected, retry | Request ID, trace ID |

Nếu cần định danh từng request hoặc job, dùng log hoặc trace attributes theo chính sách dữ liệu phù hợp. Metrics nên giữ dimensions có số lượng giá trị dự đoán được.

## 5. MeterConvention mô tả quy ước của một meter

MeterConvention là abstraction dành cho instrumentation trực tiếp bằng Metrics API. Nó mô tả:

- Tên canonical của meter.
- Tags thuộc về meter đó.
- Cách suy ra tags từ context của instrumentation, nếu có.

Giao diện có generic context type:

~~~java
import io.micrometer.core.instrument.Tags;

public interface MeterConvention<C> {
    String getName();

    default Tags getTags(C context) {
        return Tags.empty();
    }
}
~~~

SimpleMeterConvention là implementation cơ bản, hỗ trợ tên cùng tags cố định hoặc một function lấy tags từ context.

Ví dụ một convention cho bộ nhớ của MemoryPoolMXBean:

~~~java
import java.lang.management.MemoryPoolMXBean;

import io.micrometer.core.instrument.Tags;
import io.micrometer.core.instrument.binder.MeterConvention;
import io.micrometer.core.instrument.binder.SimpleMeterConvention;

MeterConvention<MemoryPoolMXBean> memoryUsedConvention =
        new SimpleMeterConvention<>(
                "runtime.jvm.memory.used",
                pool -> Tags.of("pool", pool.getName())
        );
~~~

Khi binder tạo Gauge, nó lấy tên và tags từ convention:

~~~java
Gauge.builder(
        memoryUsedConvention.getName(),
        memoryPool,
        pool -> pool.getUsage().getUsed()
)
.tags(memoryUsedConvention.getTags(memoryPool))
.description("Dung lượng bộ nhớ đang sử dụng trong pool")
.baseUnit("bytes")
.register(registry);
~~~

Nhờ vậy, logic thu thập số liệu và chính sách đặt tên/tag được tách riêng. Có thể thay convention để đổi schema mà không cần viết lại cách đọc dữ liệu từ MemoryPoolMXBean.

### MeterConvention không tự đăng ký meter

MeterConvention chỉ mô tả name và tags. Binder hoặc instrumentation phải đọc convention rồi dùng nó khi tạo meter.

Nó không phải một global registry config. Nếu muốn áp dụng chính sách rộng cho mọi meter trong registry, MeterFilter thường phù hợp hơn.

## 6. Tạo convention riêng cho custom MeterBinder

Giả sử ứng dụng có nhiều queue và muốn thống nhất tên cùng tag của queue depth. Có thể tạo một convention riêng:

~~~java
import java.util.concurrent.BlockingQueue;

import io.micrometer.core.instrument.Tags;
import io.micrometer.core.instrument.binder.MeterConvention;
import io.micrometer.core.instrument.binder.SimpleMeterConvention;

final class QueueMetricContext {

    private final String queueName;
    private final BlockingQueue<?> queue;

    QueueMetricContext(String queueName, BlockingQueue<?> queue) {
        this.queueName = queueName;
        this.queue = queue;
    }

    String queueName() {
        return queueName;
    }

    BlockingQueue<?> queue() {
        return queue;
    }
}

MeterConvention<QueueMetricContext> queueDepthConvention =
        new SimpleMeterConvention<>(
                "worker.queue.depth",
                context -> Tags.of("queue", context.queueName())
        );
~~~

Binder dùng convention khi đăng ký Gauge:

~~~java
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.binder.MeterBinder;

public final class QueueDepthBinder implements MeterBinder {

    private final QueueMetricContext context;
    private final MeterConvention<QueueMetricContext> convention;

    public QueueDepthBinder(
            QueueMetricContext context,
            MeterConvention<QueueMetricContext> convention
    ) {
        this.context = context;
        this.convention = convention;
    }

    @Override
    public void bindTo(MeterRegistry registry) {
        Gauge.builder(
                convention.getName(),
                context.queue(),
                queue -> queue.size()
        )
        .tags(convention.getTags(context))
        .description("Số tác vụ đang chờ trong queue")
        .register(registry);
    }
}
~~~

Trong thiết kế lớn hơn, convention có thể được inject hoặc tạo từ cấu hình. Điểm quan trọng là mọi meter thuộc binder dùng cùng quy tắc đặt tên và tags.

Queue name phải thuộc tập đã kiểm soát. Nếu queue name được tạo tự do từ tenant hoặc request, convention vẫn có thể gây cardinality cao.

## 7. MeterConvention trong các JVM binder có sẵn

Micrometer cung cấp conventions cho một số JVM metrics. Các binder liên quan gồm:

- ClassLoaderMetrics
- JvmMemoryMetrics
- JvmThreadMetrics
- ProcessorMetrics

Ở các phiên bản mới, những binder này có builder cho phép tùy biến từng convention hoặc chọn convention theo OpenTelemetry semantic conventions.

Ví dụ cấu hình tên và tag riêng cho JVM memory used:

~~~java
import io.micrometer.core.instrument.Tags;
import io.micrometer.core.instrument.binder.jvm.JvmMemoryMetrics;
import io.micrometer.core.instrument.binder.jvm.convention.JvmMemoryUsedMeterConvention;

JvmMemoryMetrics memoryMetrics = JvmMemoryMetrics.builder()
        .memoryUsedConvention(
                JvmMemoryUsedMeterConvention.of(
                        "runtime.jvm.memory.used",
                        pool -> Tags.of("pool", pool.getName())
                )
        )
        .build();

memoryMetrics.bindTo(registry);
~~~

Builder giúp thay đổi convention của một meter cụ thể trong binder. Các meter còn lại có thể tiếp tục dùng convention mặc định.

### Chuyển từ constructor convention cũ sang builder

Trong Micrometer 1.16.x, một số JVM binder cho phép truyền một object conventions vào constructor. Ví dụ với memory binder:

~~~java
import io.micrometer.core.instrument.Tags;
import io.micrometer.core.instrument.binder.jvm.JvmMemoryMetrics;
import io.micrometer.core.instrument.binder.jvm.convention.micrometer.MicrometerJvmMemoryMeterConventions;

new JvmMemoryMetrics(
        Tags.empty(),
        new MicrometerJvmMemoryMeterConventions()
).bindTo(registry);
~~~

Constructor nhận JvmMemoryMeterConventions được đánh dấu deprecated trong Micrometer 1.18.0 và hướng người dùng sang builder để cấu hình từng meter riêng:

~~~java
JvmMemoryMetrics.builder()
        .openTelemetryConventions()
        .build()
        .bindTo(registry);
~~~

Khi nâng cấp, không chỉ thay constructor bằng builder một cách máy móc. Hãy chuyển từng convention đang dùng sang phương thức tương ứng như memoryUsedConvention(), memoryCommittedConvention() hoặc memoryMaxConvention(), rồi xác nhận tên và tags đầu ra không đổi ngoài chủ đích.

### Chọn OpenTelemetry semantic conventions

Các binder hỗ trợ có convenience method openTelemetryConventions() trên builder. Dùng static builder() để tạo builder:

~~~java
JvmMemoryMetrics.builder()
        .openTelemetryConventions()
        .build()
        .bindTo(registry);
~~~

Có thể áp dụng tương tự với ClassLoaderMetrics, JvmThreadMetrics và ProcessorMetrics khi phiên bản Micrometer đang dùng cung cấp builder tương ứng.

Convenience method có thể bổ sung convention mới trong các minor release khi OpenTelemetry semantic conventions liên quan được đánh dấu stable và được Micrometer hỗ trợ. Nếu cần schema ổn định nghiêm ngặt qua các lần nâng cấp, hãy cấu hình từng convention cụ thể thay vì phụ thuộc vào một preset có thể mở rộng.

### Tránh đăng ký binder hai lần

Spring Boot có thể đã tự động đăng ký các JVM binders. Nếu tự tạo và bind thêm một binder tùy biến, hãy kiểm tra cấu hình auto-configuration để tránh tạo meter trùng hoặc thêm một bộ tên/tag song song.

Nếu cần thay đổi convention của binder do ứng dụng quản lý, hãy cấu hình đúng bean/binder đang được sử dụng. Đừng thêm một binder mới mà không kiểm tra meter hiện có.

## 8. Phân biệt MeterConvention, NamingConvention, MeterFilter và ObservationConvention

Các API này đều có thể ảnh hưởng đến tên hoặc tags nhưng hoạt động ở những lớp khác nhau.

| API | Phạm vi | Trách nhiệm chính | Dùng khi |
| --- | --- | --- | --- |
| MeterConvention | Một loại meter trong instrumentation/binder | Định nghĩa canonical name và tags | Muốn tùy biến schema của một binder cụ thể |
| NamingConvention | Registry/backend | Chuyển tên và tag key sang format backend | Prometheus, Graphite hoặc backend có quy tắc tên riêng |
| MeterFilter | MeterRegistry | Accept, deny, map hoặc configure meter | Chính sách chung cho registry |
| ObservationConvention | Observation | Chuẩn hóa tên, contextual name và key-values của thao tác | Instrument request hoặc operation lifecycle bằng Observation |

### MeterConvention và NamingConvention

MeterConvention định nghĩa tên chuẩn của meter trước khi đăng ký. NamingConvention chuyển tên canonical và tag key sang cú pháp của backend.

Ví dụ một meter có canonical name là runtime.jvm.memory.used. Prometheus naming convention có thể chuyển nó sang runtime_jvm_memory_used hoặc dạng tương ứng với quy tắc exporter.

Không dùng MeterConvention để thay thế NamingConvention. Một convention có thể được dùng trên nhiều registry, trong khi mỗi registry có thể cần cách biểu diễn khác nhau.

### MeterConvention và MeterFilter

MeterFilter áp dụng ở registry khi meter được đăng ký. Nó có thể đổi tên hoặc tags của meter trên diện rộng. MeterConvention đặt quy tắc gần với binder hoặc instrumentation tạo meter đó.

Nên dùng MeterConvention khi thay đổi chỉ dành cho một loại meter cụ thể. Dùng MeterFilter khi chính sách cần áp dụng chung cho registry, ví dụ deny meter theo prefix hoặc thêm common transformation.

### MeterConvention và ObservationConvention

Nếu đang đo một thao tác có thời lượng hoặc vòng đời như HTTP request, database call hay checkout, Observation API thường phù hợp hơn. ObservationConvention chuẩn hóa Observation name và key-values.

MeterConvention dành cho instrumentation trực tiếp bằng Metrics API như Gauge, FunctionCounter hoặc các resource meter. Không dùng MeterConvention để thay thế ObservationConvention cho request lifecycle.

## 9. Phân biệt Meter.MeterProvider của Micrometer với MeterProvider của OpenTelemetry

Tên MeterProvider cũng xuất hiện trong OpenTelemetry API. Hai kiểu này không giống nhau.

Micrometer:

~~~java
Meter.MeterProvider<Timer> timerProvider =
        Timer.builder("job.execution")
                .tag("job.name", "reconcile")
                .withRegistry(registry);
~~~

OpenTelemetry có API riêng để lấy MeterProvider hoặc Meter từ OpenTelemetry instance, sau đó tạo instruments như Counter, Histogram hoặc ObservableGauge. Package và lifecycle khác với Micrometer.

Khi import, dùng rõ kiểu Micrometer:

~~~java
import io.micrometer.core.instrument.Meter;
~~~

Không nhầm nó với:

~~~java
import io.opentelemetry.api.metrics.MeterProvider;
~~~

Không trộn hai API trong cùng ví dụ nếu mục tiêu chỉ là tạo meter bằng Micrometer. Nếu ứng dụng đang migration từ Micrometer Metrics sang OpenTelemetry Metrics, hãy đánh giá riêng bridge, instrument semantics, naming, temporality và exporter.

## 10. Đánh giá tác động đến metric schema khi đổi convention

Tên và tags là một phần của Meter.Id. Khi thay convention, tổ hợp name và tags có thể thay đổi, tạo một time series mới.

Ví dụ trước:

~~~text
jvm.memory.used{area=heap,id=G1 Old Gen}
~~~

Sau khi đổi convention:

~~~text
runtime.jvm.memory.used{pool=G1 Old Gen}
~~~

Dù cả hai đo cùng một đại lượng, backend có thể xem đây là hai series khác nhau. Dashboard, alert, recording rule và SLO query dựa trên tên/tag cũ sẽ không tự động cập nhật.

Trước khi đổi convention, cần xác định:

- Tên canonical cũ và mới.
- Tag key cũ và mới.
- Tag value có thay đổi semantics không?
- Unit và meter type có giữ nguyên không?
- Backend naming convention có làm biến đổi tên khác nhau không?
- Dashboard, alert và recording rule đang tham chiếu series nào?
- Có cần một giai đoạn chuyển đổi để cập nhật query không?

Không đổi metric name hoặc tag chỉ để đồng nhất hình thức nếu không có lợi ích rõ ràng. Metric schema là giao diện giữa ứng dụng và hệ thống giám sát.

### Kế hoạch chuyển đổi có kiểm soát

1. Lập danh sách meter bị ảnh hưởng và các query sử dụng chúng.
2. Chốt convention đích và kiểm tra cardinality.
3. Viết test cho Meter.Id mới và exposition thực tế.
4. Cập nhật dashboard, alert và recording rules.
5. Triển khai theo môi trường, quan sát series mới.
6. Xác nhận các consumer đã chuyển sang schema mới.
7. Loại bỏ schema cũ theo kế hoạch nếu có giai đoạn phát song song.

Nếu cần giữ tính liên tục lịch sử, có thể giữ nguyên schema cũ hoặc thực hiện migration ở tầng query/backend. Phát đồng thời hai meter chỉ nên dùng khi có kế hoạch kết thúc rõ ràng vì nó làm tăng số series và chi phí ingest.

## 11. Kiểm thử MeterProvider

Có thể dùng SimpleMeterRegistry để kiểm tra provider tạo meter với tags cố định và động:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Meter;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

class MeterProviderTest {

    @Test
    void createsMetersFromCommonTemplateAndDynamicTags() {
        try (SimpleMeterRegistry registry = new SimpleMeterRegistry()) {
            Meter.MeterProvider<Counter> provider =
                    Counter.builder("job.executions")
                            .tag("job.name", "reconcile")
                            .withRegistry(registry);

            provider.withTag("outcome", "success").increment();
            provider.withTag("outcome", "failure").increment();
            provider.withTag("outcome", "success").increment();

            assertThat(registry.get("job.executions")
                    .tag("job.name", "reconcile")
                    .tag("outcome", "success")
                    .counter()
                    .count())
                    .isEqualTo(2.0);

            assertThat(registry.get("job.executions")
                    .tag("job.name", "reconcile")
                    .tag("outcome", "failure")
                    .counter()
                    .count())
                    .isEqualTo(1.0);
        }
    }
}
~~~

Test xác nhận provider giữ tag cố định job.name và tạo hai meter theo outcome. Cũng nên kiểm tra tổng số meter đã đăng ký nếu cần phát hiện việc vô tình tạo quá nhiều tag combinations.

## 12. Kiểm thử MeterConvention

Có thể kiểm tra convention độc lập trước khi dùng trong binder:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import io.micrometer.core.instrument.Tag;
import io.micrometer.core.instrument.Tags;
import io.micrometer.core.instrument.binder.MeterConvention;
import io.micrometer.core.instrument.binder.SimpleMeterConvention;
import org.junit.jupiter.api.Test;

class MeterConventionTest {

    @Test
    void definesCanonicalNameAndContextTags() {
        MeterConvention<String> convention =
                new SimpleMeterConvention<>(
                        "runtime.jvm.memory.used",
                        poolName -> Tags.of("pool", poolName)
                );

        assertThat(convention.getName())
                .isEqualTo("runtime.jvm.memory.used");
        assertThat(convention.getTags("test-pool"))
                .containsExactly(Tag.of("pool", "test-pool"));
    }
}
~~~

Test dùng context nhỏ để xác nhận cả canonical name lẫn tag được tạo từ context. Khi kiểm thử binder, có thể kiểm tra Meter.Id sau khi bind:

~~~java
Meter meter = registry.find("runtime.jvm.memory.used")
        .tag("pool", "test-pool")
        .gauge();
~~~

Ví dụ này minh họa cách truy vấn meter theo convention. Trong test thực tế, cần cung cấp nguồn Gauge hợp lệ và giữ tham chiếu đến nguồn đó.

### Kiểm thử exposition

Tên canonical trong Meter.Id có thể khác tên được export. Vì vậy, ngoài unit test convention, nên có integration test cho registry đích:

- Xác nhận canonical meter name và tag set.
- Xác nhận NamingConvention chuyển đổi đúng.
- Xác nhận unit và suffix phù hợp.
- Xác nhận backend exposition không tạo tag ngoài dự kiến.
- Xác nhận histogram hoặc percentile config vẫn được giữ nếu meter có distribution statistics.

## 13. Chẩn đoán khi API không tồn tại hoặc không hoạt động

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Không tìm thấy withRegistry() | Micrometer core thấp hơn 1.12 hoặc builder không hỗ trợ provider | Kiểm tra phiên bản và meter type |
| Không tìm thấy MeterConvention | Micrometer core thấp hơn 1.16 | Kiểm tra dependency đã resolve |
| Không tìm thấy SimpleMeterConvention | Micrometer core thấp hơn 1.16 hoặc import sai package | Dùng đúng package binder |
| Không có JvmMemoryMetrics.builder() | Phiên bản binder chưa có builder API | Kiểm tra mốc 1.18 và dùng API được hỗ trợ |
| Không có openTelemetryConventions() | Binder hoặc phiên bản chưa cung cấp preset | Cấu hình convention riêng hoặc giữ mặc định |
| Compile được nhưng runtime NoSuchMethodError | Micrometer modules lệch phiên bản | Đồng bộ qua Spring Boot/Micrometer BOM |
| Có meter nhưng tên không như convention | Binder chưa dùng convention hoặc NamingConvention biến đổi tên | Kiểm tra Meter.Id và exposition |
| Có hai bộ metric JVM | Binder mặc định và binder tùy biến cùng được đăng ký | Kiểm tra auto-configuration và bean |
| Số series tăng mạnh sau migration | Dynamic tags hoặc convention tạo thêm dimensions | Giới hạn tag values và xem lại schema |
| Dashboard mất dữ liệu sau đổi tên | Query còn dùng tên/tag cũ | Cập nhật dashboard và alert theo kế hoạch |

## 14. Quy trình đánh giá API mới khi nâng cấp

Khi thấy một API mới trong tài liệu hoặc release note, thực hiện theo thứ tự:

1. Xác định bài toán thực tế: giảm builder lặp, chuẩn hóa tên/tag hay thay đổi Observation.
2. Tìm API trong Javadoc của đúng phiên bản đang resolve.
3. Xác nhận mốc @since và trạng thái deprecated nếu có.
4. Kiểm tra API thuộc micrometer-core, micrometer-observation hay module khác.
5. Kiểm tra registry implementation và Spring Boot BOM có tương thích không.
6. Tạo một ví dụ nhỏ compile trên dependency thật của dự án.
7. Viết test Meter.Id, tags và exposition.
8. Đánh giá cardinality và chi phí tạo meter.
9. Kiểm tra dashboard, alert, SLO và recording rules chịu ảnh hưởng.
10. Chỉ sau đó mới quyết định thay API trong instrumentation production.

### Gradle và Maven khi nâng cấp

Không nâng một module Micrometer đơn lẻ nếu BOM đang quản lý cả bộ phiên bản. Nếu cần thử API mới, hãy nâng platform/BOM theo hướng tương thích và xem dependency tree trước khi sửa code.

Gradle có thể dùng dependencyInsight để xác định lý do một phiên bản được chọn. Maven có thể dùng dependency:tree để tìm phiên bản được resolve và dependency nào kéo nó vào.

Nếu API chưa có trong phiên bản hiện tại, có ba lựa chọn:

- Giữ cách triển khai cũ nếu vẫn phù hợp.
- Nâng phiên bản nền tảng theo kế hoạch tương thích.
- Viết abstraction nội bộ tạm thời nếu cần giữ code dùng chung giữa nhiều phiên bản.

Không dùng reflection để che giấu khác biệt API nếu một compile-time dependency phù hợp có thể giải quyết vấn đề rõ ràng hơn.

## 15. Bảng quyết định chọn API

| Nhu cầu | API nên xem xét | Lý do |
| --- | --- | --- |
| Tạo Timer với tags cố định và một tag outcome động | MeterProvider | Giữ builder chung, thêm tag khi hoàn tất |
| Tạo Counter theo nhóm trạng thái hữu hạn | MeterProvider | Tái sử dụng template và giảm boilerplate |
| Đổi tên/tag của meter trong một binder cụ thể | MeterConvention | Quy tắc nằm gần instrumentation tạo meter |
| Chuẩn hóa tên/tag cho nhiều meter trong registry | MeterFilter | Chính sách ở cấp registry |
| Chuyển canonical name sang format Prometheus | NamingConvention | Quy tắc của backend |
| Đo HTTP request hoặc thao tác nghiệp vụ | Observation và ObservationConvention | Quản lý lifecycle, metrics và tracing |
| Đổi JVM metric sang OpenTelemetry semantic conventions | JVM binder convention builder nếu phiên bản hỗ trợ | Chọn schema convention đã được hỗ trợ |

## 16. Checklist trước khi áp dụng API mới

Trước khi merge thay đổi MeterProvider hoặc MeterConvention, hãy xác nhận:

1. Phiên bản micrometer-core thực tế đã được xác định bằng dependency insight/tree chưa?
2. API có mặt từ phiên bản nào và dự án có đáp ứng không?
3. Spring Boot BOM và registry implementation có tương thích không?
4. MeterProvider có thật sự giảm builder lặp trong trường hợp này không?
5. Tags động có tập giá trị hữu hạn không?
6. MeterConvention được dùng ở đúng binder hoặc instrumentation không?
7. NamingConvention của backend có làm biến đổi tên/tag không?
8. Có MeterFilter hoặc common tags tác động lên cùng meter không?
9. Có đăng ký binder mặc định và binder tùy biến trùng nhau không?
10. Metric schema mới có ảnh hưởng dashboard, alert hoặc SLO không?
11. Test đã xác nhận Meter.Id và exposition chưa?
12. Có kế hoạch chuyển đổi nếu tên hoặc tags thay đổi không?

## Kết luận

Meter.MeterProvider và MeterConvention giải quyết hai nhu cầu khác nhau. MeterProvider tái sử dụng một builder làm template và thêm tags động khi tạo Counter, Timer, LongTaskTimer hoặc DistributionSummary. MeterConvention định nghĩa canonical name và tags của một meter thuộc instrumentation cụ thể; nó hữu ích khi tùy biến MeterBinder mà không phải áp dụng một MeterFilter rộng cho cả registry.

Hãy kiểm tra phiên bản thực tế trước khi áp dụng: MeterProvider có từ 1.12.0, MeterConvention từ 1.16.0 và builder convention trên một số JVM binders từ 1.18.0. Phân biệt chúng với NamingConvention, MeterFilter, ObservationConvention và OpenTelemetry MeterProvider. Cuối cùng, kiểm tra cardinality và metric schema vì thay đổi tên hoặc tags có thể tạo time series mới và làm dashboard, alert hoặc SLO query ngừng khớp.

## Tài liệu tham khảo

- [Micrometer Meter Provider](https://docs.micrometer.io/micrometer/reference/concepts/meter-provider.html) — template builder, withRegistry(), withTag() và withTags().
- [Meter.MeterProvider Javadoc](https://javadoc.io/doc/io.micrometer/micrometer-core/latest/io/micrometer/core/instrument/Meter.MeterProvider.html) — API và mốc since 1.12.0.
- [Micrometer Meter Convention](https://docs.micrometer.io/micrometer/reference/concepts/meter-convention.html) — mục đích và cách dùng MeterConvention.
- [MeterConvention Javadoc](https://javadoc.io/doc/io.micrometer/micrometer-core/latest/io/micrometer/core/instrument/binder/MeterConvention.html) — canonical name, context tags và mốc since 1.16.0.
- [Micrometer JVM Metrics](https://docs.micrometer.io/micrometer/reference/reference/jvm.html) — builder conventions, OpenTelemetry semantic conventions và các JVM binders.
- [Micrometer Meter Filters](https://docs.micrometer.io/micrometer/reference/concepts/meter-filters.html) — chính sách accept, deny, map và configure meter ở registry.
- [Micrometer Observation](https://docs.micrometer.io/micrometer/reference/observation.html) — Observation lifecycle và ObservationConvention.
