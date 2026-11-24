# MeterConvention và phạm vi hỗ trợ tùy biến binder theo phiên bản

Micrometer cung cấp MeterBinder để đăng ký một nhóm meter có liên quan đến một thành phần hoặc tài nguyên, chẳng hạn bộ nhớ JVM, class loader, thread, CPU hoặc executor. Mỗi binder thường chọn sẵn tên metric và tag để mô tả dữ liệu mà nó thu thập. Khi quy ước mặc định không khớp chuẩn đặt tên của tổ chức, cần phân biệt cách tùy biến mà phiên bản Micrometer đang dùng thực sự hỗ trợ.

Từ Micrometer 1.16.0, MeterConvention cung cấp một mô hình riêng để mô tả tên chuẩn và tag của một meter cụ thể. Một số binder JVM nhận các convention này và cho phép thay đổi tên hoặc tag trước khi đăng ký meter. Ở nhánh 1.18, một số binder bổ sung builder theo từng meter convention, giúp cấu hình rõ ràng hơn. API này không áp dụng tự động cho mọi MeterBinder; phạm vi hỗ trợ phụ thuộc vào từng binder và phiên bản thư viện.

## Mục tiêu

Sau bài học, bạn có thể:

- Giải thích MeterBinder và MeterConvention có trách nhiệm gì.
- Phân biệt meter convention với MeterFilter, NamingConvention và ObservationConvention.
- Chọn cách tùy biến tương thích với phiên bản Micrometer.
- Tùy chỉnh tên và tag của một số JVM binder bằng convention.
- Tự thiết kế convention cho một binder của ứng dụng.
- Nhận diện những meter trong một binder không được convention điều khiển.
- Kiểm soát tag để tránh cardinality cao và giữ metric ổn định khi nâng cấp.

## MeterBinder đăng ký các meter cho một thành phần

MeterBinder là interface có phương thức bindTo(MeterRegistry). Khi được bind, implementation đăng ký một hoặc nhiều meter mô tả trạng thái của thành phần mà nó theo dõi.

Ví dụ, các binder JVM phổ biến cung cấp metrics về:

| Binder | Dữ liệu được theo dõi |
|---|---|
| ClassLoaderMetrics | Số class hiện đang được nạp và số class đã unload |
| JvmMemoryMetrics | Bộ nhớ heap/non-heap, memory pool và buffer pool |
| JvmThreadMetrics | Số thread theo trạng thái, thread daemon và peak |
| ProcessorMetrics | Số processor, CPU time và CPU load |
| JvmGcMetrics | Sự kiện và thống kê garbage collection |

Đăng ký binder cơ bản:

~~~java
MeterRegistry registry = new SimpleMeterRegistry();

new ClassLoaderMetrics().bindTo(registry);
new JvmMemoryMetrics().bindTo(registry);
new JvmThreadMetrics().bindTo(registry);
new ProcessorMetrics().bindTo(registry);
~~~

Mỗi binder chịu trách nhiệm biết cách đọc nguồn dữ liệu và tạo meter phù hợp. Ví dụ, JvmMemoryMetrics đọc các MemoryPoolMXBean, còn ProcessorMetrics đọc thông tin CPU mà JVM cung cấp. Mã ứng dụng không cần tự viết lại phần truy cập MXBean nếu binder đã cung cấp dữ liệu cần thiết.

## MeterConvention mô tả tên chuẩn và tag của một meter

Một meter convention mô tả quy ước cho một meter cụ thể:

- Tên canonical (tên chuẩn) của meter.
- Các tag gắn với meter đó.
- Trong một số convention, tag có thể được tạo từ context tại thời điểm binder đăng ký meter.

Interface MeterConvention<C> nằm trong package io.micrometer.core.instrument.binder và có hai phương thức chính:

~~~java
public interface MeterConvention<C> {
    String getName();

    default Tags getTags(C context) {
        return Tags.empty();
    }
}
~~~

C là kiểu context dùng để tạo tag. Ví dụ, một convention cho memory pool có thể nhận MemoryPoolMXBean để lấy tên pool; convention cho thread count có thể nhận Thread.State để tạo tag trạng thái.

Micrometer cũng cung cấp SimpleMeterConvention<C> cho các trường hợp chỉ cần một tên cố định và tag cố định hoặc tag được tạo bằng hàm:

~~~java
MeterConvention<String> convention =
    new SimpleMeterConvention<>(
        "worker.queue.depth",
        queueName -> Tags.of("queue", queueName)
    );
~~~

Khi binder dùng convention này với context orders, tên meter là worker.queue.depth và tag là queue=orders. Convention xác định danh tính metric ở lớp instrumentation trước khi registry đăng ký meter.

### MeterConvention khác NamingConvention

Hai khái niệm này xử lý hai giai đoạn khác nhau:

| Khái niệm | Trách nhiệm | Ví dụ |
|---|---|---|
| MeterConvention | Chọn tên canonical và tag theo ý nghĩa instrumentation | http.server.requests, route=/orders/{id} |
| NamingConvention | Chuyển tên và tag sang cú pháp mà backend yêu cầu | Prometheus dùng dấu gạch dưới; Atlas dùng camel case |

Ví dụ, cùng một timer canonical http.server.requests có thể được registry chuyển thành http_server_requests_duration_seconds khi export Prometheus hoặc httpServerRequests với Atlas. Meter convention không cần biết backend nào đang được dùng; naming convention của registry thực hiện bước chuyển đổi định dạng sau đó.

### MeterConvention khác MeterFilter

MeterFilter là cơ chế tổng quát ở cấp registry. Nó có thể chấp nhận hoặc từ chối meter, đổi tên, đổi tag hoặc điều chỉnh cấu hình phân phối khi meter được đăng ký. Vì vậy filter có thể tác động đến meter từ nhiều instrumentation khác nhau.

MeterConvention là quy ước thuộc về một loại instrumentation hoặc một meter cụ thể. Binder sử dụng convention để chọn tên và tag có ý nghĩa trước khi đăng ký meter. Cách này thể hiện rõ metric nào được tùy biến và tránh phải viết filter tổng quát chỉ để sửa một binder cụ thể.

Dùng convention khi binder có điểm mở rộng hỗ trợ nó. Dùng filter khi cần quy tắc chung cho nhiều meter hoặc binder hiện tại không cung cấp convention tương ứng.

### MeterConvention khác ObservationConvention

MeterConvention phù hợp với instrumentation gọi trực tiếp Metrics API, ví dụ gauge cho memory pool, function counter cho CPU time hoặc metric trạng thái thread.

Khi đo vòng đời một thao tác như HTTP request, gọi dịch vụ hoặc xử lý message, nên cân nhắc Observation API và ObservationConvention. Observation mô hình hóa một hoạt động có điểm bắt đầu/kết thúc và có thể tạo metrics, tracing hoặc các handler khác. MeterConvention không thay thế quy ước cho vòng đời request.

## Phạm vi API theo phiên bản Micrometer

MeterConvention không có mặt trong tất cả phiên bản Micrometer. Cần đối chiếu phiên bản micrometer-core mà ứng dụng thực sự resolve, thay vì chỉ nhìn phiên bản Spring Boot hoặc một dependency riêng lẻ.

| Phiên bản Micrometer | Khả năng tùy biến |
|---|---|
| 1.15.x và cũ hơn | Chưa có interface MeterConvention. Một số binder nhận Iterable<Tag> qua constructor để thêm tag; muốn đổi tên hoặc chuẩn hóa tag thường phải dùng MeterFilter hoặc viết binder riêng. |
| 1.16.0–1.17.x | MeterConvention được giới thiệu từ 1.16.0. Một số JVM binder có convention interface chuyên biệt và constructor nhận convention, ví dụ ProcessorMetrics, JvmMemoryMetrics, JvmThreadMetrics hoặc ClassLoaderMetrics. Không phải mọi binder đều có điểm mở rộng này. |
| 1.18.0-M2 và nhánh 1.18 | Bổ sung các kiểu convention riêng cho từng meter và builder pattern ở các JVM binder được hỗ trợ. Có thể cấu hình từng convention, extra tags và preset OpenTelemetry ở builder. |

Mốc 1.16.0 là thời điểm interface MeterConvention được giới thiệu. Builder theo từng convention là thay đổi ở nhánh 1.18.0-M2; không nên lấy ví dụ builder của 1.18 để áp dụng trực tiếp vào dự án 1.16 hoặc 1.17.

Các binder có API tùy biến trong tài liệu JVM hiện hành gồm:

- ClassLoaderMetrics
- JvmMemoryMetrics
- JvmThreadMetrics
- ProcessorMetrics

Danh sách này không có nghĩa mọi metric do từng binder tạo ra đều có convention riêng. Một binder có thể chỉ cho phép thay đổi một số meter, còn những meter khác vẫn dùng tên/tag cố định. Hãy đọc Javadoc đúng phiên bản và kiểm tra danh sách convention mà binder cung cấp.

## Tùy biến ở Micrometer 1.16.x–1.17.x bằng constructor convention

Ở các phiên bản 1.16.x và 1.17.x, một số binder nhận interface convention chuyên biệt qua constructor. Ví dụ ProcessorMetrics nhận JvmCpuMeterConventions:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Tags;
import io.micrometer.core.instrument.binder.MeterConvention;
import io.micrometer.core.instrument.binder.SimpleMeterConvention;
import io.micrometer.core.instrument.binder.system.ProcessorMetrics;
import io.micrometer.core.instrument.binder.jvm.convention.JvmCpuMeterConventions;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

public class ProcessorConventionDemo {

    public static void main(String[] args) {
        MeterRegistry registry = new SimpleMeterRegistry();

        try {
            JvmCpuMeterConventions conventions = new JvmCpuMeterConventions() {
                @Override
                public MeterConvention<Object> cpuCountConvention() {
                    return new SimpleMeterConvention<>(
                        "host.cpu.count",
                        Tags.of("unit", "core")
                    );
                }

                @Override
                public MeterConvention<Object> cpuTimeConvention() {
                    return new SimpleMeterConvention<>(
                        "host.cpu.time",
                        Tags.of("unit", "nanoseconds")
                    );
                }

                @Override
                public MeterConvention<Object> processCpuLoadConvention() {
                    return new SimpleMeterConvention<>("process.cpu.load");
                }
            };

            new ProcessorMetrics(Tags.empty(), conventions).bindTo(registry);
        } finally {
            registry.close();
        }
    }
}
~~~

Ở đây ứng dụng thay tên và tag của ba meter CPU mà JvmCpuMeterConventions mô tả. SimpleMeterConvention đủ dùng vì các tag trong ví dụ là cố định. Nếu tag cần phụ thuộc context, có thể cung cấp hàm tạo Tags hoặc tự triển khai convention tương ứng.

Một lưu ý về constructor của một số binder 1.16.x: tham số extraTags không nhất thiết được ghép vào các meter đã được điều khiển bởi convention. Javadoc của ProcessorMetrics ghi rõ extra tags không được kết hợp với convention tags cho các meter thuộc convention; convention cần tự cung cấp tag muốn dùng. Vì vậy, đừng giả định truyền extra tags vào constructor sẽ tự thêm chúng lên mọi meter.

API constructor và danh sách convention có thể khác giữa các binder. Đoạn code trên minh họa ProcessorMetrics trong API 1.16.x–1.17.x; cần kiểm tra Javadoc của đúng phiên bản đang sử dụng trước khi sao chép sang binder khác.

## Tùy biến ở nhánh 1.18 bằng builder theo từng meter

Từ nhánh 1.18, một số JVM binder cung cấp builder() và phương thức cấu hình riêng cho từng meter convention. Ví dụ với ClassLoaderMetrics:

~~~java
import io.micrometer.core.instrument.Tags;
import io.micrometer.core.instrument.binder.jvm.ClassLoaderMetrics;
import io.micrometer.core.instrument.binder.jvm.convention.JvmClassCountMeterConvention;
import io.micrometer.core.instrument.binder.jvm.convention.JvmClassLoadedMeterConvention;
import io.micrometer.core.instrument.binder.jvm.convention.JvmClassUnloadedMeterConvention;

ClassLoaderMetrics classLoaderMetrics = ClassLoaderMetrics.builder()
    .classCountConvention(
        JvmClassCountMeterConvention.of(
            "runtime.classes.count",
            Tags.of("kind", "all")
        )
    )
    .classLoadedConvention(
        JvmClassLoadedMeterConvention.of("runtime.classes.loaded")
    )
    .classUnloadedConvention(
        JvmClassUnloadedMeterConvention.of("runtime.classes.unloaded")
    )
    .build();

classLoaderMetrics.bindTo(registry);
~~~

Builder giúp cấu hình độc lập từng meter do binder tạo ra. Có thể chỉ thay đổi class count mà giữ nguyên convention mặc định cho loaded/unloaded, hoặc thay cả ba để thống nhất tên và tag theo quy ước của hệ thống.

Một số builder còn hỗ trợ extraTags(...) để gắn tag chung lên các meter do binder tạo. Nếu extra tag trùng key với convention tag, quy tắc ưu tiên phụ thuộc API binder; tài liệu 1.18 mô tả convention tag được ưu tiên trong builder JVM tương ứng. Vẫn nên tránh thiết kế hai nguồn cùng định nghĩa một key.

### Dùng preset OpenTelemetry

Các builder JVM được hỗ trợ có thể cung cấp openTelemetryConventions() để chọn convention theo OpenTelemetry semantic conventions:

~~~java
ClassLoaderMetrics classLoaderMetrics =
    ClassLoaderMetrics.builder()
        .openTelemetryConventions()
        .build();

classLoaderMetrics.bindTo(registry);
~~~

Các binder JVM có builder hỗ trợ preset này gồm ClassLoaderMetrics, JvmMemoryMetrics, JvmThreadMetrics và ProcessorMetrics. Phạm vi convention áp dụng phụ thuộc từng binder và các semantic convention tương ứng đã ổn định, được Micrometer hỗ trợ.

Preset có thể được mở rộng ở các minor release sau khi có thêm OpenTelemetry semantic conventions ổn định. Nếu hệ thống yêu cầu tên và tag không thay đổi khi nâng cấp Micrometer, hãy cấu hình từng convention cụ thể thay vì phụ thuộc hoàn toàn vào preset tự động.

Mốc 1.44.0 thường được nhắc trong tài liệu ở đây là phiên bản của OpenTelemetry semantic conventions được tham chiếu, không phải phiên bản Micrometer.

## Tự dùng MeterConvention trong binder của ứng dụng

Không phải binder nào cũng do Micrometer cung cấp. Ứng dụng có thể viết MeterBinder riêng và nhận convention qua constructor để tách quy ước metric khỏi logic đọc dữ liệu.

Ví dụ, một worker có độ sâu queue cần xuất gauge theo tên và tag có thể thay đổi theo quy ước triển khai:

~~~java
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Tags;
import io.micrometer.core.instrument.binder.MeterBinder;
import io.micrometer.core.instrument.binder.MeterConvention;

import java.util.concurrent.atomic.AtomicInteger;

public final class QueueMetrics implements MeterBinder {

    private final AtomicInteger queueDepth;
    private final String queueName;
    private final MeterConvention<String> convention;

    public QueueMetrics(
        AtomicInteger queueDepth,
        String queueName,
        MeterConvention<String> convention
    ) {
        this.queueDepth = queueDepth;
        this.queueName = queueName;
        this.convention = convention;
    }

    @Override
    public void bindTo(MeterRegistry registry) {
        Gauge.builder(
                convention.getName(),
                queueDepth,
                AtomicInteger::get
            )
            .tags(convention.getTags(queueName))
            .description("Số tác vụ đang chờ trong queue")
            .register(registry);
    }

    public static MeterConvention<String> defaultConvention() {
        return new MeterConvention<String>() {
            @Override
            public String getName() {
                return "worker.queue.depth";
            }

            @Override
            public Tags getTags(String queue) {
                return Tags.of("queue", queue);
            }
        };
    }
}
~~~

Khi khởi tạo binder:

~~~java
AtomicInteger depth = new AtomicInteger();
MeterConvention<String> convention = QueueMetrics.defaultConvention();

new QueueMetrics(depth, "orders", convention).bindTo(registry);
~~~

Binder chịu trách nhiệm lấy giá trị từ queueDepth; convention chỉ mô tả tên và tag. Nếu tổ chức muốn dùng tên jobs.waiting hoặc tag key queue_name, có thể truyền một convention khác mà không thay đổi logic đọc queue.

Trong ứng dụng thực tế, chỉ dùng các giá trị queue có miền hữu hạn. Không đưa queue ID sinh ngẫu nhiên, request ID hoặc user ID vào tag. Convention cho phép tách phần định danh metric, nhưng không tự kiểm soát cardinality của dữ liệu do ứng dụng cung cấp.

## Chọn convention hay MeterFilter?

| Tình huống | Lựa chọn |
|---|---|
| Binder có API convention và chỉ muốn đổi metric của binder đó | Dùng MeterConvention của binder |
| Muốn thay từng tên/tag của JVM binder được hỗ trợ | Dùng convention interface hoặc builder theo phiên bản |
| Muốn chuẩn hóa tên/tag trên nhiều binder hoặc thư viện | Dùng MeterFilter |
| Binder không cung cấp hook convention | Dùng MeterFilter hoặc viết binder riêng |
| Muốn đổi cú pháp tên cho backend cụ thể | Cấu hình NamingConvention của registry |
| Đo request hoặc thao tác có vòng đời | Dùng Observation API và ObservationConvention khi phù hợp |

Không nên dùng MeterFilter để đổi tất cả metric có cùng tiền tố nếu chỉ một binder cần quy ước khác. Ngược lại, không cần tạo convention riêng nếu mục tiêu là chuẩn hóa toàn registry theo một quy tắc chung.

## Kiểm tra kết quả sau khi bind

Sau khi bind, có thể duyệt các meter để xác nhận tên và tag mà registry đã nhận:

~~~java
for (Meter meter : registry.getMeters()) {
    Meter.Id id = meter.getId();

    if (id.getName().startsWith("runtime.classes")) {
        System.out.println(id.getName() + " " + id.getTags());
    }
}
~~~

Khi kiểm tra, phân biệt tên canonical trước export với tên đã được registry chuyển đổi cho backend. Với Prometheus, endpoint scrape có thể hiển thị tên khác do NamingConvention và quy tắc đặt tên của Prometheus registry.

Nên kiểm tra ít nhất các điểm sau:

- Binder có được bind đúng một lần trong vòng đời ứng dụng không.
- Tên meter sau convention có đúng quy ước không.
- Tag keys và values có đúng, không trùng hoặc xung đột không.
- Những meter không được convention hỗ trợ có còn tên/tag mặc định như mong muốn không.
- Không có tag động làm cardinality tăng ngoài dự kiến.
- Tên và tag export thực tế có khớp dashboard, alert và recording rule không.

Khi đổi tên hoặc tag của metric đang chạy trong production, dashboard và alert phải được cập nhật cùng kế hoạch triển khai. Backend sẽ xem tên hoặc tập label mới là chuỗi khác; dữ liệu lịch sử không tự chuyển sang danh tính mới.

## Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Dùng builder() trên phiên bản cũ | Không biên dịch vì API chưa tồn tại | Kiểm tra version; dùng constructor convention hoặc MeterFilter phù hợp |
| Nghĩ mọi MeterBinder hỗ trợ MeterConvention | Không tìm thấy hook tùy biến trên binder | Kiểm tra Javadoc của từng binder |
| Nghĩ convention áp dụng cho toàn registry | Các meter ngoài binder vẫn giữ quy ước riêng | Dùng MeterFilter khi cần quy tắc toàn cục |
| Cho rằng extra tags luôn được ghép vào convention tags | Một số meter không nhận tag như dự kiến | Đọc Javadoc constructor/builder và đưa tag vào convention khi cần |
| Nhầm MeterConvention với NamingConvention | Cố đổi cú pháp backend ở sai lớp | Giữ canonical name trong convention; cấu hình naming ở registry |
| Dùng preset OpenTelemetry nhưng kỳ vọng metric ổn định tuyệt đối | Minor release có thể bổ sung convention mới | Cấu hình từng convention nếu cần kiểm soát chặt |
| Đưa tên tài nguyên động vào tag | Cardinality tăng cao | Chuẩn hóa về nhóm hữu hạn hoặc bỏ chiều phân tích |
| Nâng cấp Micrometer nhưng không kiểm tra metric | Dashboard hoặc alert mất chuỗi dữ liệu | So sánh tên/tag trước và sau nâng cấp |

## Ghi nhớ

- MeterBinder đăng ký một hoặc nhiều meter vào MeterRegistry.
- MeterConvention mô tả tên canonical và tag cho một meter cụ thể.
- MeterConvention được giới thiệu từ Micrometer 1.16.0.
- Trong 1.16.x–1.17.x, một số binder JVM nhận convention interface qua constructor; API và phạm vi hỗ trợ khác nhau theo binder.
- Nhánh 1.18 bổ sung builder theo từng meter convention cho một số JVM binder.
- Không phải mọi MeterBinder đều hỗ trợ convention; custom binder phải chủ động dùng interface này.
- MeterFilter tác động tổng quát ở cấp registry; NamingConvention chuyển định dạng cho backend; ObservationConvention phục vụ Observation API.
- Preset OpenTelemetry tiện lợi, nhưng convention tường minh phù hợp hơn khi cần ổn định metric qua các lần nâng cấp.
- Luôn kiểm tra tag, tên canonical và tên export thực tế sau khi bind.

Khi chọn đúng điểm mở rộng theo phiên bản, có thể tùy biến tên và tag của binder mà vẫn giữ nguyên logic thu thập dữ liệu. Trước khi nâng cấp Micrometer, hãy kiểm tra builder và convention của từng binder đang sử dụng để biết metric nào có thể đổi và metric nào vẫn theo mặc định.

## Tài liệu tham khảo

- [Micrometer: Meter Convention](https://docs.micrometer.io/micrometer/reference/concepts/meter-convention.html) — khái niệm convention và mối quan hệ với NamingConvention.
- [Micrometer: JVM Metrics](https://docs.micrometer.io/micrometer/reference/reference/jvm.html) — binder JVM, builder và preset OpenTelemetry.
- [MeterConvention API, Micrometer 1.16.6](https://javadoc.io/static/io.micrometer/micrometer-core/1.16.6/io/micrometer/core/instrument/binder/MeterConvention.html) — API nền tảng và mốc giới thiệu.
- [ProcessorMetrics API, Micrometer 1.16.6](https://javadoc.io/static/io.micrometer/micrometer-core/1.16.6/io/micrometer/core/instrument/binder/system/ProcessorMetrics.html) — constructor nhận convention và phạm vi extra tags.
- [Micrometer 1.18.0-M2 release notes](https://github.com/micrometer-metrics/micrometer/releases/tag/v1.18.0-M2) — builder pattern theo từng meter convention.

