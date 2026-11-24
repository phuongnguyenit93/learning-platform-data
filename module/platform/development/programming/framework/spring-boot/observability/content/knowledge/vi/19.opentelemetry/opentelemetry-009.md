# SdkMeterProvider trong OpenTelemetry

Trong chương **OpenTelemetry** của module **SPRING_BOOT_OBSERVABILITY**, `SdkMeterProvider` là thành phần SDK quản lý các meter và quá trình thu thập metrics. Nó cung cấp `Meter` cho instrumentation, kết hợp resource metadata, views, aggregation và metric readers để biến các lần ghi dữ liệu thành metric streams rồi xuất tới hệ thống quan sát.

Khi triển khai Spring Boot, cần phân biệt hai con đường tích hợp. Phần lớn ứng dụng Spring Boot dùng **Micrometer Observation và MeterRegistry** do Spring Boot Actuator quản lý. Một ứng dụng hoặc thư viện chọn OpenTelemetry Metrics API trực tiếp có thể sử dụng **OpenTelemetry SDK với SdkMeterProvider**. Cả hai hướng đều có thể xuất metrics tới backend, nhưng không nên tạo hai pipeline độc lập chỉ để ghi cùng một phép đo.

Bài học thuộc module **SPRING_BOOT_OBSERVABILITY** tập trung vào metrics, logs và distributed tracing: hiểu vai trò SdkMeterProvider, cách tạo instruments, cấu hình Resource/Views/MetricReader, xuất OTLP, giới hạn cardinality và kiểm chứng dữ liệu từ ứng dụng tới backend.

## 1. MeterProvider nằm ở đâu trong kiến trúc OpenTelemetry?

OpenTelemetry phân chia **API** và **SDK**. API cung cấp những interface mà instrumentation sử dụng; SDK thực thi việc lưu nhận measurements, aggregation và xuất metrics. `MeterProvider` là abstraction của API, còn `SdkMeterProvider` là implementation thuộc OpenTelemetry SDK.

```text
Spring Boot application
    |
    +-- instrumentation (HTTP / business / database)
    |                  |
    |                  v
    |              MeterProvider API
    |                  |
    |                  v
    |              Meter
    |                  |
    |            instruments
    |        Counter / Histogram / Gauge
    |                  |
    |                  v
    |            measurements
    |                  |
    |                  v
    |             SdkMeterProvider
    |              /    |     \
    |        Resource  Views  MetricReaders
    |                            |
    |                            v
    |                      MetricExporter
    |                            |
    |                            v
    |                         OTLP
    |                            |
    |                            v
    |                    Collector / backend
    |
    +-- Micrometer MeterRegistry (một pipeline khác nếu app chọn)
```

| Thành phần | Trách nhiệm |
| --- | --- |
| `MeterProvider` | Cấp các Meter cho instrumentation |
| `SdkMeterProvider` | Quản lý instruments, aggregation, views và readers trong SDK |
| `Meter` | Nhóm instruments theo instrumentation scope |
| Instrument | Khai báo cách ghi measurement như counter hoặc histogram |
| `Resource` | Metadata về service/process tạo ra metrics |
| `View` | Điều chỉnh aggregation hoặc tập attributes của một instrument |
| `MetricReader` | Thu thập/đọc metric data từ SDK theo kiểu export phù hợp |
| `MetricExporter` | Chuyển metric data ra định dạng/transport của backend, ví dụ OTLP |

**SdkMeterProvider không phải metrics backend.** Nó giữ trạng thái aggregation trong tiến trình và cung cấp dữ liệu cho reader. Lưu trữ lịch sử, truy vấn theo khoảng thời gian và dashboard thuộc trách nhiệm của collector/backend như Prometheus hoặc một nền tảng metrics tương thích.

## 2. API và SDK: vì sao cần tách riêng?

Instrumentation thường nên phụ thuộc API để không khóa chặt vào một exporter/backend. Ứng dụng triển khai SDK và cấu hình provider ở composition root.

- **API:** `io.opentelemetry.api.metrics.MeterProvider`, `Meter`, `LongCounter`, `DoubleHistogram` và các instrument interfaces.
- **SDK:** `io.opentelemetry.sdk.metrics.SdkMeterProvider`, readers, views và aggregation.
- **Exporter:** module như OTLP metric exporter cung cấp transport ra ngoài.

Nếu chỉ có API mà không có SDK/provider implementation phù hợp, một số instrument có thể hoạt động theo dạng no-op; code vẫn biên dịch nhưng không có dữ liệu được xuất. Việc gọi `GlobalOpenTelemetry.getMeterProvider()` không tự chứng minh đã cài SDK hoặc có exporter.

Không nên để từng thư viện tạo `SdkMeterProvider` và exporter riêng. Nhiều provider có thể làm dữ liệu bị chia thành các pipeline không đồng nhất, lặp series, dùng resource khác nhau hoặc gây khó khăn khi shutdown. Một ứng dụng nên có **một nơi sở hữu rõ ràng** provider và lifecycle cho từng pipeline metrics chủ đạo.

## 3. Instruments: ghi nhận dữ liệu theo đúng ý nghĩa

Meter cung cấp các instruments. Chọn loại phù hợp ngữ nghĩa quan trọng hơn việc chọn API dễ viết nhất.

| Instrument | Semantics | Ví dụ |
| --- | --- | --- |
| Counter | Giá trị tăng đơn điệu; không giảm | Tổng đơn được chấp nhận |
| UpDownCounter | Giá trị có thể tăng/giảm | Số tác vụ đang chờ |
| Histogram | Phân phối các giá trị được ghi | Thời gian xử lý, payload size |
| Gauge / ObservableGauge | Giá trị hiện tại được quan sát tại thời điểm collection | Số connection đang active |
| ObservableCounter | Tổng tích lũy đọc từ callback | Tổng bytes từ một nguồn chỉ đọc |
| ObservableUpDownCounter | Giá trị quan sát có thể tăng/giảm | Kích thước hàng đợi đang tồn tại |

Không dùng counter để ghi giá trị hiện tại như số connection active; không giảm counter khi request kết thúc. Với thời gian xử lý, histogram thường phù hợp vì có thể tổng hợp phân phối ở backend. Gauge phù hợp trạng thái tức thời nhưng không thể áp dụng `rate()` như counter.

### Ví dụ tạo Meter và Counter

Đoạn code sau dùng OpenTelemetry Metrics API:

```java
import io.opentelemetry.api.metrics.LongCounter;
import io.opentelemetry.api.metrics.Meter;
import io.opentelemetry.api.metrics.MeterProvider;

public final class OrderMetrics {
    private final LongCounter acceptedOrders;

    public OrderMetrics(MeterProvider meterProvider) {
        Meter meter = meterProvider
                .meterBuilder("orders.business")
                .setInstrumentationVersion("1.0.0")
                .build();

        this.acceptedOrders = meter
                .counterBuilder("orders.accepted")
                .setDescription("Number of accepted orders")
                .setUnit("{order}")
                .build();
    }

    public void recordAccepted(String channel) {
        acceptedOrders.add(
                1,
                io.opentelemetry.api.common.Attributes.of(
                        io.opentelemetry.api.common.AttributeKey
                                .stringKey("channel"),
                        channel));
    }
}
```

Trong ứng dụng thực tế, `channel` phải là một giá trị hữu hạn đã chuẩn hóa như `web`, `mobile` hoặc `partner`. Không lấy trực tiếp header tùy ý từ client nếu nó có thể chứa hàng nghìn giá trị.

Metric name, description và unit là một phần của hợp đồng telemetry. Tên nên ổn định, đơn vị rõ ràng, mô tả đủ ý nghĩa. Không đổi cùng một metric name từ “seconds” sang “milliseconds” mà không quản lý migration.

### Histogram đo thời gian xử lý

```java
import io.opentelemetry.api.metrics.DoubleHistogram;
import io.opentelemetry.api.metrics.Meter;

public final class CheckoutMetrics {
    private final DoubleHistogram duration;

    public CheckoutMetrics(Meter meter) {
        this.duration = meter.histogramBuilder("checkout.duration")
                .setDescription("Checkout operation duration")
                .setUnit("s")
                .build();
    }

    public void recordDuration(double seconds, String outcome) {
        duration.record(
                seconds,
                io.opentelemetry.api.common.Attributes.of(
                        io.opentelemetry.api.common.AttributeKey
                                .stringKey("outcome"),
                        outcome));
    }
}
```

Đơn vị giây được chọn trong ví dụ để phù hợp với duration. Giá trị `outcome` nên có tập giá trị giới hạn như `success`, `declined` và `error`. Không đưa order ID, Trace ID hoặc exception message vào metric attributes.

## 4. Tạo SdkMeterProvider với Resource và MetricReader

Một provider cần biết:

1. **Resource:** service name, service version, environment và metadata ổn định về process.
2. **Reader:** cơ chế thu thập dữ liệu, ví dụ định kỳ push qua OTLP hoặc pull qua một exporter/reader phù hợp.
3. **View (nếu cần):** aggregation, buckets hoặc attribute filtering cho instrument.
4. **Lifecycle:** khi nào provider được khởi tạo, giữ sống và shutdown.

Ví dụ cấu hình độc lập sử dụng OTLP/gRPC exporter:

```java
import io.opentelemetry.api.common.AttributeKey;
import io.opentelemetry.api.common.Attributes;
import io.opentelemetry.exporter.otlp.metrics.OtlpGrpcMetricExporter;
import io.opentelemetry.sdk.OpenTelemetrySdk;
import io.opentelemetry.sdk.metrics.SdkMeterProvider;
import io.opentelemetry.sdk.metrics.export.PeriodicMetricReader;
import io.opentelemetry.sdk.resources.Resource;
import java.time.Duration;
import java.util.concurrent.TimeUnit;

public final class StandaloneMetrics {
    public static void main(String[] args) {
        Resource resource = Resource.getDefault().merge(
                Resource.create(Attributes.of(
                        AttributeKey.stringKey("service.name"),
                        "orders-service",
                        AttributeKey.stringKey("deployment.environment.name"),
                        "development")));

        var exporter = OtlpGrpcMetricExporter.builder()
                .setEndpoint("http://localhost:4317")
                .build();

        var reader = PeriodicMetricReader.builder(exporter)
                .setInterval(Duration.ofSeconds(30))
                .build();

        SdkMeterProvider meterProvider = SdkMeterProvider.builder()
                .setResource(resource)
                .registerMetricReader(reader)
                .build();

        OpenTelemetrySdk openTelemetry = OpenTelemetrySdk.builder()
                .setMeterProvider(meterProvider)
                .build();

        OrderMetrics orderMetrics =
                new OrderMetrics(openTelemetry.getMeterProvider());
        orderMetrics.recordAccepted("web");

        // Flush measurements của demo trước khi kết thúc process.
        boolean flushed = meterProvider.forceFlush()
                .join(10, TimeUnit.SECONDS);
        if (!flushed) {
            throw new IllegalStateException("Metrics flush did not complete");
        }

        meterProvider.close();
    }
}
```

Đây là ví dụ **SDK độc lập** nhằm minh họa wiring. Một chương trình chạy rồi thoát ngay có thể đóng provider trước chu kỳ collection; dữ liệu vừa ghi có thể chưa được export. Trong ứng dụng dài hạn, giữ provider sống suốt thời gian service hoạt động. Các API exporter/reader có thể thay đổi giữa phiên bản OpenTelemetry; cần dùng BOM tương thích và xác minh package/module.

### Resource attributes

Resource mô tả **nơi tạo telemetry**, không mô tả từng request:

| Attribute | Ví dụ | Có nên thay đổi theo request? |
| --- | --- | --- |
| `service.name` | `orders-service` | Không |
| `service.version` | `2.4.1` | Không trong cùng process |
| `deployment.environment.name` | `production` | Không trong cùng deployment |
| `service.instance.id` | ID instance/pod | Không theo request |
| `tenant.id` | Tenant hiện tại | Không đặt làm resource cho service đa tenant |

Không đưa user ID, order ID, Trace ID hay giá trị request-specific vào Resource. Những giá trị đó làm phân mảnh identity hoặc tăng cardinality không cần thiết.

## 5. MetricReader và MetricExporter

Reader quyết định **khi nào và theo cách nào metrics được thu thập**. Exporter quyết định **đưa dữ liệu tới đâu và bằng transport nào**.

| Reader/export pattern | Hoạt động | Trường hợp phù hợp |
| --- | --- | --- |
| `PeriodicMetricReader` | Thu thập theo interval và chuyển dữ liệu tới exporter | OTLP push định kỳ |
| Pull reader/exporter phù hợp | Expose metrics để scraper lấy mẫu | Backend dùng pull model, khi exporter/SDK hỗ trợ |
| Custom reader/processor | Tích hợp đặc thù | Chỉ nên dùng khi có nhu cầu rõ và kiểm soát lifecycle |

Với periodic reader, interval là một lựa chọn vận hành. Interval quá ngắn tăng network/export overhead; quá dài khiến dữ liệu trễ và có thể mất batch khi process shutdown bất thường. Chọn interval theo nhu cầu freshness, kích thước batch, tải và backend capacity.

OTLP metric exporter thường gửi metrics tới collector, rồi collector route tới backend. Endpoint `localhost:4317` chỉ đúng nếu collector ở cùng network namespace hoặc có port mapping phù hợp. Trong Docker/Kubernetes, dùng DNS/service name thực tế, cấu hình TLS/auth khi cần.

**Không đồng nhất OTLP export với Prometheus scrape.** OTLP thường là push tới receiver; Prometheus truyền thống scrape endpoint exposition. Nếu muốn dùng Prometheus pull, chọn integration tương ứng và xác minh output/temporality thay vì giả định chỉ cần đổi URL.

## 6. Views: kiểm soát aggregation và attributes

View cho phép cấu hình cách một instrument được tổng hợp và tập attributes được giữ trong metric stream. Nó hữu ích khi:

- Cần histogram aggregation với explicit bucket boundaries phù hợp SLO.
- Muốn bỏ một số attributes không cần thiết.
- Muốn chuẩn hóa output metric stream cho backend.
- Cần tránh đưa tag có cardinality cao tới exporter.

Ví dụ minh họa tạo View cho histogram:

```java
import io.opentelemetry.api.common.AttributeKey;
import io.opentelemetry.sdk.metrics.InstrumentSelector;
import io.opentelemetry.sdk.metrics.View;
import io.opentelemetry.sdk.metrics.Aggregation;
import java.util.List;

var selector = InstrumentSelector.builder()
        .setName("checkout.duration")
        .build();

var view = View.builder()
        .setAggregation(
                Aggregation.explicitBucketHistogram(
                        List.of(0.05, 0.1, 0.25, 0.5, 1.0, 2.5)))
        .setAttributeFilter(key ->
                !key.equals(AttributeKey.stringKey("debug.payload")))
        .build();
```

API View/aggregation và cách filter có thể khác theo phiên bản SDK. Cần đăng ký View với builder của `SdkMeterProvider` tương ứng (thường qua instrument selector và view) và kiểm tra metric stream xuất thực tế. Đoạn trên chỉ minh họa nội dung View, chưa phải một provider hoàn chỉnh.

View không phải nơi thay thế việc thiết kế attributes hợp lý tại nguồn. Nên tránh tạo high-cardinality attributes ngay từ đầu; filter là lớp bảo vệ bổ sung, không phải giấy phép ghi tùy tiện.

### Explicit histogram boundaries

Bucket boundaries phải phản ánh đơn vị và ngưỡng vận hành. Với checkout duration tính bằng giây, các mốc 0,05; 0,1; 0,25; 0,5; 1 và 2,5 giây có thể hữu ích nếu phù hợp SLO. Nếu phần lớn request nằm dưới 10 ms hoặc trên 10 giây, bucket trên không phù hợp.

Không chọn bucket chỉ vì ví dụ trên mạng. Đọc histogram distribution thực tế, mục tiêu latency và lượng time series phát sinh. Số bucket, số combinations attributes và số instance cùng ảnh hưởng cardinality.

## 7. Cardinality và metric attributes

Một metric stream thường được xác định bởi metric identity, resource và attribute set. Nếu attributes có nhiều giá trị không giới hạn, số series có thể tăng rất nhanh.

Giả sử instrument có:

- `route`: 20 route templates.
- `method`: 4 phương thức.
- `status_class`: 5 nhóm.
- `region`: 3 vùng.

Tối đa theo tích đơn giản là 20 × 4 × 5 × 3 = 1.200 tổ hợp mỗi instance. Với 50 instance, có thể thành 60.000 series trước khi tính histogram buckets hoặc metrics khác. Nếu thêm `orderId` có hàng triệu giá trị, cardinality có thể vượt ngân sách rất nhanh.

| Attribute | Đánh giá | Lý do |
| --- | --- | --- |
| `route=/orders/{id}` | Phù hợp | Route template có tập giá trị hữu hạn |
| `method=GET/POST` | Phù hợp | Cardinality nhỏ |
| `status_class=2xx/4xx/5xx` | Phù hợp | Dễ tổng hợp |
| `provider=bank_a/bank_b` | Phù hợp nếu danh sách được quản lý | Phân tích dependency |
| `orderId` | Tránh | Mỗi giao dịch gần như tạo series riêng |
| `traceId` / `spanId` | Tránh | Gần như duy nhất theo trace/span |
| Raw URL/query string | Tránh | Có ID, token hoặc chuỗi không giới hạn |
| Exception message nguyên văn | Tránh | Vừa high-cardinality vừa có rủi ro dữ liệu |

OpenTelemetry SDK có thể áp dụng cardinality limits hoặc aggregation limits theo phiên bản/cấu hình. Khi đạt limit, SDK có thể gom các attributes vượt ngưỡng vào overflow series hoặc xử lý theo semantics được định nghĩa; phải đọc hành vi của version đang dùng. **Không dựa vào limit để hợp thức hóa attributes thiết kế sai.**

## 8. Temporality: cumulative và delta

Metrics exporter/reader cần semantics nhất quán về temporality:

- **Cumulative:** mỗi collection thể hiện tổng tích lũy kể từ điểm bắt đầu/reset của instrument/process.
- **Delta:** mỗi collection thể hiện phần thay đổi kể từ lần collection trước.

Ví dụ counter ghi 5, rồi ghi thêm 3:

| Lần collection | Cumulative | Delta |
| --- | ---: | ---: |
| Lần 1 | 5 | 5 |
| Lần 2 | 8 | 3 |

Backend cần hiểu temporality để tính rate, reset và aggregation đúng. Không cộng các điểm cumulative lặp như thể mỗi điểm là phần tăng mới. Không giả định mọi reader/exporter/backend sử dụng cùng temporality mặc định; kiểm tra OTLP payload, SDK temporality preference và semantics của backend.

Với histogram, delta/cumulative cũng ảnh hưởng cách diễn giải bucket counts, sum và count. Nếu đổi exporter hoặc backend, cần kiểm tra migration và tránh double counting trong giai đoạn chạy song song.

## 9. Observable instruments và callback

Counter/Histogram được ghi tại thời điểm sự kiện xảy ra. Observable instruments đọc giá trị từ callback khi SDK collection diễn ra. Chúng phù hợp với nguồn dữ liệu có trạng thái hiện tại, chẳng hạn queue size hoặc số worker active.

Ví dụ minh họa:

```java
import io.opentelemetry.api.metrics.Meter;
import io.opentelemetry.api.metrics.ObservableLongGauge;
import java.util.concurrent.atomic.AtomicLong;

public final class QueueMetrics implements AutoCloseable {
    private final AtomicLong queueSize;
    private final ObservableLongGauge gauge;

    public QueueMetrics(Meter meter, AtomicLong queueSize) {
        this.queueSize = queueSize;
        this.gauge = meter.gaugeBuilder("orders.queue.size")
                .ofLongs()
                .setDescription("Current number of queued orders")
                .setUnit("{order}")
                .buildWithCallback(measurement ->
                        measurement.record(queueSize.get()));
    }

    @Override
    public void close() {
        gauge.close();
    }
}
```

Callback phải nhẹ, không blocking, không gọi database hoặc remote service. Nó được thực thi theo chu kỳ collection; nếu callback làm việc nặng, chính lần scrape/export metrics có thể gây tải lên ứng dụng. Đóng observable instrument khi component sở hữu nó kết thúc để giải phóng callback registration.

Không đăng ký callback mới mỗi request. Nên tạo instrument một lần trong lifecycle của bean/service và để callback đọc state đã có.

## 10. Tích hợp SdkMeterProvider với Spring Boot: chọn một chủ sở hữu

Spring Boot Actuator thường dùng Micrometer `MeterRegistry` để instrument HTTP, JVM, DataSource và Observation. Nếu dự án dùng Micrometer làm abstraction chính, Spring Boot auto-configuration và Micrometer registry là đường tích hợp tự nhiên.

Nếu dự án có thư viện hoặc instrumentation OpenTelemetry Metrics API trực tiếp, có thể cần OTel SDK. Khi đó phải quyết định rõ cách ứng dụng sở hữu provider và export:

**Phương án A — Micrometer-first**

- Spring Boot quản lý `MeterRegistry`.
- Custom business metrics dùng Micrometer API.
- Registry/exporter được cấu hình theo backend đã chọn.
- Tracing có thể dùng Micrometer Tracing bridge.

**Phương án B — OpenTelemetry SDK-first**

- Ứng dụng cấu hình `SdkMeterProvider` và `MetricReader`.
- OTel API instrumentation ghi trực tiếp qua `MeterProvider`.
- Exporter gửi metrics tới collector/backend.
- Lifecycle provider/reader do ứng dụng hoặc framework tích hợp sở hữu.

**Không ghi cùng một business event qua cả hai pipeline** nếu backend tổng hợp chúng như hai metric độc lập. Ví dụ cùng một order được increment ở Micrometer Counter và OTel Counter có thể bị đếm đôi.

### Spring configuration cho provider do ứng dụng sở hữu

Một cấu hình Spring có thể đăng ký provider thành bean có lifecycle rõ ràng. Ví dụ khái niệm:

```java
import io.opentelemetry.exporter.otlp.metrics.OtlpGrpcMetricExporter;
import io.opentelemetry.sdk.metrics.SdkMeterProvider;
import io.opentelemetry.sdk.metrics.export.PeriodicMetricReader;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import java.time.Duration;

@Configuration(proxyBeanMethods = false)
class OpenTelemetryMetricsConfiguration {

    @Bean(destroyMethod = "close")
    SdkMeterProvider sdkMeterProvider() {
        var exporter = OtlpGrpcMetricExporter.builder()
                .setEndpoint("http://otel-collector:4317")
                .build();

        var reader = PeriodicMetricReader.builder(exporter)
                .setInterval(Duration.ofSeconds(30))
                .build();

        return SdkMeterProvider.builder()
                .registerMetricReader(reader)
                .build();
    }
}
```

Đây là minh họa khi **chính ứng dụng sở hữu OTel metrics provider**. Cần bổ sung Resource/Views/attributes phù hợp, dùng đúng BOM và endpoint, đồng thời bảo đảm instrumentation nhận đúng bean provider (qua constructor injection hoặc OpenTelemetry SDK đã được tích hợp). Chỉ khai báo bean này không tự chuyển toàn bộ Micrometer Actuator metrics sang OTel SDK.

Nếu Spring Boot version hoặc starter đã auto-configure OTel SDK/bridge, không tạo thêm bean độc lập cùng chức năng. Xác định API thực tế mà instrumentation đang dùng.

## 11. SdkMeterProvider và liên kết với traces/logs

Metrics thường trả lời câu hỏi “bao nhiêu”, “bao lâu”, “tỷ lệ nào” trong một khoảng thời gian. Tracing cho thấy đường đi của một request được ghi nhận; logs mô tả lỗi và sự kiện chi tiết.

```text
Metrics:
  checkout.duration histogram p95 tăng
  payment.authorizations{outcome="error"} tăng
              |
              v
       tìm thời điểm/route có vấn đề
              |
              v
Trace (nếu sampled và export thành công):
  POST /checkout
    order.confirm
      payment.authorize
        HTTP provider call (slow)
              |
              v
Logs có traceId/spanId:
  "provider timeout"
```

SdkMeterProvider không tự quản lý TracerProvider hay logs SDK. Các tín hiệu cần được cấu hình riêng nhưng có thể cùng Resource/service identity để liên kết ở backend. Có thể dùng exemplars nếu registry/exporter/backend hỗ trợ để một metric sample trỏ tới trace representative mà không đưa Trace ID vào metric labels.

Không gắn `traceId` hoặc `spanId` vào attributes của counter/histogram. Các ID gần như duy nhất và có thể làm nổ số series. Hãy dùng low-cardinality attributes như route template, operation, status class và outcome.

Tracing sampling cũng không quyết định metric sampling. Nếu trace bị sampled out, metrics vẫn có thể được ghi qua SdkMeterProvider/MetricReader hoặc Micrometer registry. Điều này đặc biệt quan trọng khi tính SLI: dùng metrics có độ bao phủ phù hợp thay vì suy request count từ số traces đã sampled.

## 12. Lỗi thường gặp khi cấu hình SdkMeterProvider

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Code tạo Meter nhưng backend không có dữ liệu | API no-op, provider không có reader, exporter không chạy | Xem SDK dependency, provider wiring và reader registration |
| Backend có service name sai | Resource thiếu hoặc bị override | Kiểm tra Resource attributes trong metric stream |
| Metrics chỉ xuất một lần rồi dừng | Reader lifecycle/interval hoặc app shutdown sai | Kiểm tra PeriodicMetricReader và provider lifecycle |
| Counter bị đếm hai lần | Cùng sự kiện ghi ở Micrometer và OTel | Kiểm kê instrumentation và pipeline |
| Series tăng bất thường | Attribute cardinality cao, histogram nhiều buckets | Xem attribute combinations, Views và cardinality limits |
| Gauge không cập nhật | Callback không được đăng ký, đọc state sai hoặc instrument bị đóng | Xem callback lifecycle và collection interval |
| Export timeout hoặc queue tăng | Collector/backend không đáp ứng | Kiểm tra network, retry, batch và capacity |
| Rate sai sau đổi reader/exporter | Temporality hoặc reset semantics khác | Xác minh cumulative/delta và cách backend query |
| Một instance không có metric | Service không scrape/export hoặc labels khác | Kiểm tra target, resource, endpoint và discovery |
| Collector có metrics nhưng dashboard trống | Query hoặc datasource không khớp | Xem tên sau conversion, unit và labels thực tế |

### Không nhầm tên metric API với tên backend

Instrumentation tạo metric name như `orders.accepted`; exporter có thể chuẩn hóa tên hoặc đơn vị theo định dạng backend. Không viết PromQL hay dashboard dựa trên tên phỏng đoán. Kiểm tra exposition/OTLP data và tên series thực tế sau khi qua pipeline.

## 13. Quy trình kiểm chứng từ instrument tới backend

1. **Kiểm tra dependency/version:** OpenTelemetry API, SDK và exporter cùng BOM tương thích; không có nhiều provider ngoài ý muốn.
2. **Kiểm tra provider wiring:** instrumentation lấy Meter từ provider đang hoạt động, không phải no-op/default provider ngoài pipeline.
3. **Kiểm tra Resource:** service name, version và environment đúng; không chứa metadata request-specific.
4. **Ghi một measurement xác định:** increment counter một số lần, record histogram với giá trị đã biết.
5. **Kiểm tra reader:** reader được đăng ký, interval phù hợp và process đủ lâu để collection xảy ra.
6. **Kiểm tra exporter:** endpoint/protocol/TLS/auth và collector receiver đúng; xem errors/drops.
7. **Kiểm tra backend:** metric name, unit, attributes, temporality và Resource labels khớp.
8. **Kiểm tra cardinality:** số series theo instrument, attributes, buckets và instances nằm trong budget.
9. **Kiểm tra shutdown:** provider close/flush theo lifecycle để không mất batch cuối khi dừng có kiểm soát.
10. **Đối chiếu Micrometer:** nếu app có Actuator, xác định metrics nào đi qua MeterRegistry và metrics nào đi trực tiếp qua OTel để tránh double counting.

### Ma trận thử nghiệm

| Thử nghiệm | Kết quả mong đợi |
| --- | --- |
| Tạo counter và increment 3 lần | Tổng counter thể hiện 3 theo temporality/backend semantics |
| Record histogram với các giá trị đã biết | Count/sum/buckets phản ánh phép đo |
| Đặt Resource service name | Metric stream có resource/service identity đúng |
| Không đăng ký MetricReader | Không có pipeline export qua reader đó |
| Collector không reachable | Export lỗi/retry/drop được quan sát, backend thiếu dữ liệu |
| Đổi sampling probability của tracing | Không làm thay đổi trực tiếp counter metrics |
| Thêm attribute có hàng triệu giá trị | Cardinality tăng mạnh; cần loại bỏ/giới hạn |
| Đóng ObservableGauge | Callback không còn được collection sau lifecycle |
| Đổi cumulative sang delta | Backend query/aggregation phải diễn giải đúng temporality |
| Ghi cùng event ở hai registry | Có nguy cơ double count khi backend nhận cả hai series |

## 14. Bài tập tình huống

Một ứng dụng Spring Boot có hai pipeline. HTTP server metrics và business counters được tạo qua Micrometer, còn một thư viện nội bộ ghi OTel Counter trực tiếp. Sau triển khai, dashboard cho thấy số đơn đã nhận gần gấp đôi số đơn thực tế.

**Câu hỏi:**

1. Vì sao SdkMeterProvider không tự làm cho Micrometer registry và OTel metrics trở thành cùng một pipeline?
2. Cách nào xác định event đang được ghi ở cả hai nơi?
3. Nếu giữ OTel SDK cho thư viện, cần bảo đảm điều gì về provider, resource và exporter?
4. Có nên gắn order ID vào OTel Counter để tìm từng đơn không?

**Gợi ý phân tích:**

- Micrometer MeterRegistry và OpenTelemetry SdkMeterProvider là các implementation/pipeline riêng trừ khi có bridge/integration cụ thể.
- Kiểm tra metric names, resource attributes, exporter output và call sites ghi counter; cùng một event có thể bị ghi ở hai pipeline rồi dashboard cộng hai series.
- Chọn một nơi sở hữu phép đo hoặc xác định rõ hai metric có semantics khác nhau; tránh cộng chúng như cùng một sự kiện.
- Nếu giữ OTel, bảo đảm instrumentation được cấp đúng MeterProvider, SdkMeterProvider có MetricReader/exporter hoạt động, Resource dùng service identity thống nhất và lifecycle đóng đúng.
- Không đưa order ID vào metric attributes vì cardinality cao; dùng trace/log/business query có kiểm soát để điều tra từng giao dịch.

### Checklist hoàn thành

| Nội dung | Có thể giải thích/kiểm tra |
| --- | --- |
| API và SDK | Phân biệt MeterProvider và SdkMeterProvider |
| Meter và instruments | Chọn Counter, UpDownCounter, Histogram, Gauge đúng semantics |
| Resource | Đặt service identity ổn định |
| MetricReader/exporter | Giải thích collection và export |
| PeriodicMetricReader | Hiểu interval, batch và lifecycle |
| Views | Kiểm soát aggregation, buckets và attributes |
| Cardinality | Tránh Trace ID/order ID/raw URL làm metric attributes |
| Temporality | Phân biệt cumulative và delta |
| Observable instruments | Callback nhẹ, đăng ký một lần, đóng đúng lifecycle |
| Spring Boot boundary | Không vô tình tạo hai pipeline Micrometer/OTel |
| End-to-end | Kiểm tra measurement, export, ingest và backend query |

**Ghi nhớ:** `SdkMeterProvider` là trung tâm SDK quản lý Meter, instruments, Resource, Views và MetricReaders để thu thập metrics. Instrumentation ghi measurement; reader thu thập; exporter gửi dữ liệu; backend lưu và truy vấn lịch sử. Trong Spring Boot, cần chọn rõ Micrometer-first hay OpenTelemetry SDK-first cho từng phép đo, tránh double counting, giới hạn attribute cardinality, kiểm tra temporality và quản lý lifecycle. Metrics được liên kết với logs/traces ở backend nhưng có sampling và pipeline riêng; đừng dùng Trace ID làm metric label hoặc coi SdkMeterProvider là nơi lưu trữ metrics.
