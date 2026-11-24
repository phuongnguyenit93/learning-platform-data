# Bộ nhớ tăng hoặc công bố chậm do nhiều tag, bucket hoặc công việc lấy mẫu

Khi ứng dụng dùng Micrometer, bộ nhớ heap có thể tăng và việc scrape hoặc push metrics có thể chậm nếu số lượng meter, tổ hợp tag hoặc bucket histogram tăng quá lớn. Một nguyên nhân khác là mỗi Timer hoặc DistributionSummary giữ thêm trạng thái để tính percentile, max và histogram. Việc ghi một observation thường không phải vấn đề lớn; chi phí tăng khi mỗi operation tạo ra một meter identity mới hoặc khi mỗi meter phải duy trì quá nhiều thống kê phân phối.

Hãy điều tra theo ba lớp: số meter và tag trong ứng dụng, số bucket và trạng thái thống kê của từng meter, rồi thời gian serialize và truyền dữ liệu đến backend. Ba lớp có thể cùng xuất hiện nhưng cần cách xử lý khác nhau.

## Nhận diện triệu chứng trước khi thay đổi cấu hình

Một số biểu hiện thường gặp:

- Heap tăng theo số request hoặc theo số tenant, URI, user hay exception value xuất hiện.
- Số meter trong registry tăng liên tục và không giảm sau khi request kết thúc.
- Garbage collection chạy thường xuyên hơn, allocation tăng và thời gian pause dài hơn.
- Endpoint /actuator/prometheus trả chậm hoặc response chứa quá nhiều dòng.
- Prometheus scrape timeout hoặc scrape_duration_seconds tăng.
- Push registry mất nhiều thời gian serialize hoặc gửi batch, xuất hiện timeout và retry.
- Một Timer có histogram tạo nhiều series hơn nhiều lần so với Counter cùng tag.
- Tắt percentile histogram làm giảm heap hoặc thời gian export rõ rệt.

Không kết luận ngay rằng Micrometer đang rò rỉ bộ nhớ. Một registry thường giữ meter đã đăng ký để tái sử dụng; nếu tag thay đổi theo từng request, số meter tăng là kết quả của cardinality không giới hạn. Đây là tăng trưởng cấu trúc dữ liệu theo thiết kế hiện tại, không nhất thiết là object bị mất tham chiếu ngoài ý muốn.

## Phân biệt số meter với số time series

Một meter được nhận diện bởi tên và tập tag. Hai meter cùng tên nhưng khác một tag value là hai meter identity khác nhau trong registry.

Ví dụ:

~~~java
registry.counter("orders.created", "region", "north").increment();
registry.counter("orders.created", "region", "south").increment();
~~~

Đoạn code trên tạo hai meter identity vì tag region khác nhau. Nếu tag customerId có hàng trăm nghìn giá trị, cùng một Counter có thể tạo ra hàng trăm nghìn meter.

Số tổ hợp tag tối đa có thể ước lượng bằng tích số giá trị của từng tag:

~~~text
Số tổ hợp tối đa
  = số giá trị uri
  × số giá trị method
  × số giá trị status
  × số giá trị region
~~~

Giả sử một metric có 1.000 URI, 5 HTTP method, 6 status group và 3 region:

~~~text
1.000 × 5 × 6 × 3 = 90.000 tổ hợp
~~~

Đây là ước lượng trên nếu các chiều kết hợp đầy đủ; số tổ hợp thực tế có thể thấp hơn. Tuy vậy, chỉ một tag không giới hạn như raw URI hoặc request ID cũng đủ làm số meter tăng theo lượng request.

Phân biệt:

| Khái niệm | Ý nghĩa |
|---|---|
| Meter identity | Một meter name cùng bộ tag cụ thể trong Micrometer |
| Time series | Một chuỗi dữ liệu được backend lưu theo metric name và labels |
| Histogram bucket series | Một series cho mỗi bucket boundary và bộ tag |
| Observation | Một lần operation được đo; nhiều Observation có thể ghi vào cùng một meter |

Mục tiêu là nhiều operation ghi vào một tập meter identity ổn định. Không tạo Counter, Timer hoặc DistributionSummary mới theo từng request với tag chứa dữ liệu riêng của request.

## Vì sao tag động làm heap tăng?

MeterRegistry quản lý meter đã đăng ký để lần ghi sau tìm lại meter tương ứng. Khi code đưa ID duy nhất vào tag, registry phải giữ meter cho mỗi giá trị mới. Các meter này còn có thể chứa histogram state, timer statistics hoặc cấu trúc nội bộ khác.

Ví dụ nguy hiểm:

~~~java
Timer.builder("http.server.requests")
        .tag("uri", request.getRequestURI())
        .tag("userId", userId)
        .register(registry)
        .record(() -> handler.handle(request));
~~~

Nếu URI chứa ID tài nguyên hoặc userId thay đổi theo request, mỗi lần gọi có thể đăng ký meter mới. Gọi register(registry) lặp lại với cùng name và cùng tag thường lấy lại meter đã có; vấn đề nằm ở việc tag tạo ra identity mới liên tục.

Hãy dùng route template và nhóm giá trị hữu hạn:

~~~java
Timer.builder("http.server.requests")
        .tag("uri", "/orders/{orderId}")
        .tag("method", "GET")
        .tag("status", "2xx")
        .register(registry)
        .record(() -> handler.handle(request));
~~~

Trong Spring MVC hoặc WebFlux, ưu tiên URI template mà instrumentation framework cung cấp. Không tự lấy raw path rồi gắn vào tag. Với lỗi, dùng nhóm như timeout, validation, dependency hoặc unexpected; không dùng exception message.

## Các tag cần xem xét kỹ

| Tag | Rủi ro | Cách chuẩn hóa |
|---|---|---|
| uri hoặc path | Path có ID, slug hoặc query động | Dùng route template như /orders/{id} |
| userId, customerId | Gần như mỗi request có thể khác | Không dùng làm metric tag |
| requestId, traceId, spanId | Gần như duy nhất theo request | Đưa vào trace/log khi được phép |
| tenantId | Số tenant có thể tăng liên tục | Dùng nhóm tenant hoặc dimension được phê duyệt |
| exception | Có thể tạo nhiều class tùy biến | Ánh xạ về nhóm lỗi hữu hạn |
| status | Dùng status code chi tiết có giới hạn nhưng tạo nhiều tổ hợp | Chọn status code hoặc status family theo nhu cầu |
| region, provider, method | Thường có tập giá trị hữu hạn | Dùng enum hoặc allowlist |

Tag có ít giá trị vẫn có thể tạo cardinality lớn khi kết hợp nhiều chiều. Đánh giá tổng số tổ hợp của một metric, không chỉ nhìn từng tag riêng lẻ.

## Histogram và percentile làm tăng chi phí như thế nào?

Timer và DistributionSummary có thể xuất thống kê phân phối. Khi bật histogram, một meter không còn chỉ tạo count và sum; nó còn tạo các bucket series. Với Prometheus classic histogram, mỗi tag combination có thể tạo xấp xỉ:

~~~text
Số series ≈ số bucket + _count + _sum
~~~

Bucket +Inf cũng là một bucket. Số bucket thực tế phụ thuộc các percentile histogram boundaries và SLO boundaries được cấu hình. Vì vậy, nếu một metric có 90.000 tổ hợp tag và khoảng 27 bucket series tính cả +Inf, count và sum sẽ tạo xấp xỉ:

~~~text
90.000 × (27 + 2) = 2.610.000 series
~~~

Đây là phép tính minh họa cho classic histogram, không phải số bucket mặc định của mọi registry. Backend native histogram có mô hình lưu trữ khác; hãy kiểm tra loại histogram và exposition thực tế.

Client-side percentile và percentile histogram cũng khác nhau:

| Cấu hình | Nơi tính | Có thể aggregate percentile giữa nhiều instance? | Chi phí chính |
|---|---|---|---|
| publishPercentiles(0.5, 0.95, 0.99) | Trong ứng dụng | Không thể cộng/aggregate các quantile đã tính thành quantile toàn hệ thống | Trạng thái tính percentile trong từng meter và các series percentile |
| publishPercentileHistogram() | Xuất histogram buckets để backend tính | Có, nếu backend hỗ trợ histogram aggregation | Nhiều bucket series và histogram state |
| serviceLevelObjectives(...) | Ghi các boundary SLO | Có thể aggregate bucket SLO trên backend hỗ trợ | Thêm bucket cho mỗi boundary được cấu hình |

Không bật cả client-side percentile và percentile histogram theo thói quen. Chọn cách biểu diễn dựa trên câu hỏi cần trả lời và khả năng của backend. Với Prometheus, histogram buckets thường phù hợp hơn nếu cần tính p95/p99 sau khi gộp nhiều instance.

## Giới hạn miền giá trị và số bucket

Với Timer, giới hạn giá trị kỳ vọng giúp tránh tạo histogram cho miền dữ liệu rộng hơn nhu cầu:

~~~java
import java.time.Duration;

import io.micrometer.core.instrument.Timer;

Timer requestTimer = Timer.builder("http.server.request.duration")
        .publishPercentileHistogram()
        .minimumExpectedValue(Duration.ofMillis(1))
        .maximumExpectedValue(Duration.ofSeconds(5))
        .serviceLevelObjectives(
                Duration.ofMillis(100),
                Duration.ofMillis(250),
                Duration.ofMillis(500),
                Duration.ofSeconds(1))
        .register(registry);
~~~

Với DistributionSummary, miền giá trị dùng đơn vị số đo của ứng dụng:

~~~java
DistributionSummary payloadSize = DistributionSummary
        .builder("message.payload.bytes")
        .publishPercentileHistogram()
        .minimumExpectedValue(1.0)
        .maximumExpectedValue(1_000_000.0)
        .serviceLevelObjectives(1_024.0, 16_384.0, 65_536.0)
        .register(registry);
~~~

Chọn min/max dựa trên miền nghiệp vụ và đơn vị đo. Nếu giá trị thực nằm ngoài miền kỳ vọng, thống kê histogram có thể không thể hiện chi tiết ngoài phạm vi đã chọn như mong muốn. Không đặt maximum quá thấp chỉ để giảm bucket nếu hệ thống vẫn cần quan sát tail latency hoặc payload lớn.

SLO boundary nên phản ánh ngưỡng có ý nghĩa vận hành. Mỗi boundary bổ sung có thể tạo thêm bucket series cho mỗi tổ hợp tag. Không thêm hàng chục boundary chỉ để có biểu đồ mịn hơn nếu dashboard không dùng chúng.

## Giảm trạng thái percentile theo cửa sổ thời gian

Timer và DistributionSummary có thể giữ trạng thái phân phối theo cửa sổ để tính max hoặc percentile. Hai tham số liên quan là expiry và buffer length:

- distributionStatisticExpiry: thời lượng của mỗi cửa sổ thống kê.
- distributionStatisticBufferLength: số cửa sổ được giữ trong buffer.

Tăng buffer length hoặc giữ cửa sổ lâu hơn có thể làm tăng lượng trạng thái được giữ. Giảm chúng có thể giảm bộ nhớ nhưng thay đổi thời gian dữ liệu còn ảnh hưởng đến max/percentile. Đừng thay đổi các giá trị này mà chưa xác định ý nghĩa thống kê mà dashboard cần.

Ví dụ cấu hình builder:

~~~java
Timer timer = Timer.builder("worker.execution.duration")
        .publishPercentileHistogram()
        .distributionStatisticExpiry(Duration.ofSeconds(30))
        .distributionStatisticBufferLength(2)
        .register(registry);
~~~

Ví dụ trên giữ hai cửa sổ, mỗi cửa sổ 30 giây theo cấu hình. Giá trị phù hợp phụ thuộc phiên bản Micrometer, loại registry và nhu cầu quan sát; hãy kiểm tra API và default của phiên bản dự án.

## Cấu hình phân phối trong Spring Boot

Spring Boot có thể cấu hình thống kê phân phối theo meter name:

~~~yaml
management:
  metrics:
    distribution:
      percentiles-histogram:
        http.server.requests: true
      slo:
        http.server.requests:
          - 100ms
          - 250ms
          - 500ms
          - 1s
      minimum-expected-value:
        http.server.requests: 1ms
      maximum-expected-value:
        http.server.requests: 5s
      expiry:
        http.server.requests: 30s
      buffer-length:
        http.server.requests: 2
~~~

Chỉ bật histogram cho metric cần percentile aggregation. Cấu hình SLO, min/max và buffer có thể áp dụng theo meter name; xác nhận property binding trên đúng phiên bản Spring Boot. Không bật histogram toàn cục cho mọi Timer hoặc DistributionSummary nếu chỉ một vài operation cần phân tích latency.

Nếu chỉ cần đo số request và tổng thời gian, Timer count và total time có thể đã đủ. Nếu cần alert theo SLO, cấu hình boundary phù hợp. Nếu cần phân tích percentile gộp nhiều replica, dùng histogram backend có thể aggregate.

## Đặt MeterFilter làm hàng rào cardinality

Thiết kế tag ở nơi tạo meter là biện pháp chính. Có thể thêm MeterFilter để ngăn một tag vượt giới hạn dự kiến:

~~~java
import io.micrometer.core.instrument.config.MeterFilter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class MetricsConfiguration {
    @Bean
    MeterFilter limitHttpUriValues() {
        return MeterFilter.maximumAllowableTags(
                "http.server.requests",
                "uri",
                100,
                MeterFilter.deny());
    }
}
~~~

Filter này giới hạn số giá trị tag uri cho meter name bắt đầu bằng http.server.requests. Khi vượt ngưỡng, meter mới có tag value vượt giới hạn sẽ bị từ chối bởi filter được truyền vào. Đây là hàng rào bảo vệ, không phải cách chuẩn hóa URI.

Khi filter từ chối meter, dữ liệu của series bị từ chối sẽ không được ghi như mong đợi. Theo dõi log/cảnh báo và điều tra nguồn tạo tag; không đặt ngưỡng quá thấp rồi bỏ qua việc metric bị mất. Tên meter và tag key phải khớp instrumentation thực tế.

Không dùng filter để che giấu lỗi thiết kế tag. Nếu URI có hàng nghìn giá trị, sửa instrumentation để dùng route template. Filter là lớp phòng vệ bổ sung khi một thay đổi ngoài dự kiến làm cardinality tăng.

## Đăng ký meter một lần và tái sử dụng

Đăng ký meter ở constructor hoặc cấu hình khi khởi tạo service nếu tên và tag cố định:

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

public class OrderMetrics {
    private final Counter created;
    private final Timer processing;

    public OrderMetrics(MeterRegistry registry) {
        this.created = Counter.builder("orders.created")
                .tag("channel", "web")
                .register(registry);

        this.processing = Timer.builder("orders.processing.duration")
                .register(registry);
    }

    public void recordCreated() {
        created.increment();
    }

    public void recordProcessing(Runnable operation) {
        processing.record(operation);
    }
}
~~~

Không giữ một map meter có key là request ID, user ID hoặc object ID. Nếu cần phân loại theo nhóm, map chỉ nên dùng enum hoặc allowlist hữu hạn và phải có giới hạn rõ ràng.

Với tag phụ thuộc kết quả, có thể chọn một trong số ít Timer đã đăng ký trước, ví dụ success/failure. Không tạo tag từ exception message, URL đầy đủ hoặc payload.

## Phân biệt thời gian ghi metric với thời gian công bố

Chậm khi publish không nhất thiết do thao tác record() chậm. Có ít nhất ba khoảng thời gian:

1. **Recording:** cập nhật Counter, Timer hoặc histogram khi ứng dụng xử lý request.
2. **Collection/serialization:** registry duyệt meter, đọc snapshot và chuyển thành format export.
3. **Transport:** gửi dữ liệu qua HTTP/gRPC hoặc phục vụ endpoint để scraper đọc.

Nếu recording chậm, profile CPU và allocation quanh instrumentation; xem số meter, tag và histogram state. Nếu serialization chậm, xem kích thước exposition, bucket count và số meter. Nếu transport chậm, xem DNS, TLS, network, Collector/backend và timeout.

Đừng tăng timeout trước khi biết chậm ở lớp nào. Timeout lớn có thể làm request export treo lâu hơn và giữ thêm buffer hoặc connection mà không giải quyết nguyên nhân.

## Step registry và Prometheus scrape có ý nghĩa khác nhau

Với push registry như OTLP, step điều khiển chu kỳ publish. Step ngắn làm ứng dụng gửi thường xuyên hơn; step dài có thể giảm tần suất request export nhưng làm dữ liệu đến backend trễ hơn và có thể thay đổi cách tổng hợp theo interval.

Với Prometheus pull, tần suất scrape do Prometheus cấu hình. Thay đổi một thuộc tính step của push registry không làm giảm số lần Prometheus gọi /actuator/prometheus.

Nếu scrape chậm:

- Kiểm tra số meter và số dòng exposition.
- Kiểm tra số histogram bucket cho mỗi tag combination.
- Kiểm tra scrape_duration_seconds và scrape_samples_scraped.
- Kiểm tra scrape timeout, response size và network.

Nếu push chậm:

- Kiểm tra export interval, batch size và timeout.
- Kiểm tra exporter queue/retry nếu implementation có hỗ trợ.
- Kiểm tra HTTP status, Collector receiver và backend ingest.
- Kiểm tra số meter và distribution statistics cần serialize.

Không tăng step chỉ để che cardinality cao. Step thay đổi nhịp gửi, không làm biến mất meter identity đã được registry giữ.

## Sampling của tracing không giảm chi phí histogram metrics

Tracing sampler quyết định span nào được ghi hoặc export. Nó không tự giảm số Counter, Timer, tag combination hay histogram bucket được tạo bởi metrics handler.

Ví dụ, đặt tracing sampling probability xuống 10% có thể giảm số trace được export, nhưng metrics vẫn ghi nhận request nếu meter handler đang hoạt động. Nếu heap tăng do hàng nghìn URI tag hoặc hàng chục bucket trên mỗi Timer, giảm trace sampling không giải quyết nguyên nhân đó.

Tương tự, Timer.Sample chỉ lưu mốc thời gian bắt đầu và dừng phép đo vào Timer được chọn. Tạo một sample cục bộ cho mỗi operation thường không tạo meter mới. Meter mới xuất hiện khi tên hoặc tag identity thay đổi, hoặc khi code đăng ký metric động.

## Quy trình điều tra theo từng bước

### 1. Xác định heap tăng ở đâu

So sánh heap trước và sau khi tải tăng. Dùng heap dump hoặc profiler để xem số lượng Meter, Timer, histogram state, tag values và object liên quan đến registry. Nếu số meter tăng cùng số request hoặc tenant, ưu tiên điều tra tag động.

Không chỉ nhìn tổng heap. Xem object count, retained size và đường tham chiếu từ MeterRegistry để xác định registry đang giữ meter nào.

### 2. Đếm meter identity

Trong môi trường phát triển hoặc diagnostic có kiểm soát, có thể quan sát số meter:

~~~java
int meterCount = registry.getMeters().size();
~~~

Đếm số meter theo tên và tag key/value, nhưng không log toàn bộ giá trị có thể chứa ID hoặc dữ liệu nhạy cảm. Có thể tổng hợp số lượng giá trị khác nhau theo từng tag key để tìm chiều tăng nhanh.

Actuator /actuator/metrics giúp xem tên meter và các tag có sẵn trong registry. Endpoint này cần được bảo vệ và chỉ dùng ở môi trường được phép; không expose rộng rãi để debug cardinality.

### 3. Ước lượng histogram expansion

Với từng Timer hoặc DistributionSummary:

- Ghi lại số tổ hợp tag thực tế.
- Đếm bucket boundaries được export.
- Cộng count và sum series.
- Xác định client-side percentile có được bật thêm không.
- Xác định expiry và buffer length.

Ước lượng series giúp nhận ra một metric histogram có thể lớn hơn nhiều lần so với Counter. So sánh với số series thật ở endpoint hoặc backend.

### 4. Tắt thử histogram trên một metric trong canary

Trong một instance canary hoặc môi trường thử nghiệm, tắt publishPercentileHistogram cho một metric nghi ngờ, giữ nguyên tải và tag. So sánh heap, GC, scrape response size, export duration và dữ liệu SLO. Không tắt histogram toàn hệ thống trước khi xác nhận dashboard và alert không phụ thuộc bucket đó.

### 5. Chuẩn hóa tag trước khi giảm bucket

Nếu meter identity tăng do raw URI, user ID hoặc request ID, sửa tag trước. Giảm bucket trong khi vẫn có hàng chục nghìn tổ hợp tag chỉ làm chậm tốc độ tăng; không loại bỏ nguyên nhân.

### 6. Giảm thống kê chỉ ở meter cần thiết

Giữ histogram và SLO boundary cho latency quan trọng. Với metric ít được truy vấn, có thể chỉ giữ count/total hoặc dùng ít boundary hơn. Điều chỉnh min/max, expiry và buffer theo yêu cầu thực tế rồi kiểm tra lại percentile.

### 7. Xác định chậm ở recording, serialization hay network

Profile code khi ghi meter; đo thời gian endpoint scrape; theo dõi thời gian export và response từ Collector. Sửa đúng lớp gây chậm. Không dùng một timeout chung để xử lý mọi loại độ trễ.

## Ví dụ truy vấn Prometheus cho histogram

Khi Timer được export thành classic histogram, có thể tính p95 bằng cách aggregate bucket trước rồi mới tính quantile:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, uri) (
    rate(http_server_requests_seconds_bucket[5m])
  )
)
~~~

Tên metric thực tế phụ thuộc naming convention của registry và phiên bản. Kiểm tra endpoint /actuator/prometheus trước khi dùng query. Không aggregate các client-side percentile series bằng cách lấy trung bình p95 của từng pod; kết quả đó không phải p95 toàn hệ thống.

Nếu chỉ cần SLO, có thể alert trực tiếp trên bucket boundary đã chọn thay vì xuất nhiều percentile hoặc bucket không được sử dụng.

## Những lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Heap tăng theo lượng request | Tag chứa request ID, user ID hoặc raw URI | Dùng route template và tập tag hữu hạn |
| Meter count không giảm | Registry giữ meter identity đã đăng ký | Loại tag động; không tạo meter theo request |
| Một Timer tạo nhiều series | Percentile histogram và nhiều bucket | Giảm boundary, giới hạn miền giá trị hoặc bỏ histogram nếu không cần |
| p95 giữa các pod không có ý nghĩa khi gộp | Dùng client-side percentile | Dùng histogram bucket có thể aggregate |
| Scrape endpoint trả rất chậm | Nhiều meter hoặc histogram series | Giảm cardinality và số bucket; đo response size |
| Push export timeout | Batch lớn, network/backend chậm hoặc export quá thường xuyên | Phân biệt serialization và transport; điều chỉnh step/timeout có căn cứ |
| Giảm trace sampling nhưng heap không giảm | Metrics cardinality/histogram vẫn giữ nguyên | Điều tra MeterRegistry và distribution config |
| Filter cardinality làm mất metric | Ngưỡng bị vượt và meter mới bị deny | Sửa tag source; theo dõi việc bị từ chối |
| Max/percentile dao động sau khi đổi buffer | Cửa sổ thống kê đã thay đổi | Kiểm tra expiry/buffer và xác nhận semantics |
| Chỉ một instance tăng heap | Cấu hình tag hoặc tải khác nhau giữa replica | So sánh route, tenant distribution và config hiệu lực |

## Checklist khắc phục

- [ ] Đã phân biệt heap của ứng dụng, số meter và số time series ở backend.
- [ ] Đã tìm tag có số giá trị tăng theo request.
- [ ] URI dùng route template; ID và trace ID không nằm trong metric tag.
- [ ] Meter có tên và tag identity ổn định, được đăng ký một lần và tái sử dụng.
- [ ] Đã tính số tổ hợp tag cho metric có nhiều chiều.
- [ ] Đã đếm bucket và percentile được xuất cho Timer/DistributionSummary.
- [ ] Chỉ bật histogram ở metric cần percentile aggregation hoặc SLO.
- [ ] Min/max expected value phản ánh miền nghiệp vụ thực tế.
- [ ] SLO boundary có số lượng nhỏ và gắn với alert/dashboard cụ thể.
- [ ] Expiry và buffer length phù hợp với nhu cầu thống kê.
- [ ] MeterFilter chỉ làm hàng rào bảo vệ, không thay thế chuẩn hóa tag.
- [ ] Đã phân biệt recording, serialization và transport latency.
- [ ] Đã phân biệt push registry step với Prometheus scrape interval.
- [ ] Không nhầm tracing sampling với metrics histogram hoặc cardinality.
- [ ] Đã xác minh thay đổi trong canary trước khi áp dụng rộng.

## Tài liệu tham khảo

- [Micrometer Histograms and Percentiles](https://docs.micrometer.io/micrometer/reference/concepts/histogram-quantiles.html)
- [Micrometer Meter Filters](https://docs.micrometer.io/micrometer/reference/concepts/meter-filters.html)
- [Micrometer Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html)
- [Spring Boot Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Prometheus Histograms](https://prometheus.io/docs/practices/histograms/)

Khi heap tăng hoặc export chậm, hãy đo số meter identity, số tổ hợp tag và số bucket trước khi điều chỉnh sampling hay timeout. Chuẩn hóa tag động là cách xử lý cardinality; giới hạn histogram, miền giá trị và cửa sổ thống kê là cách giảm chi phí phân phối. Sau cùng, xác định độ trễ nằm ở recording, serialization hay transport để thay đổi đúng thành phần và vẫn giữ được số đo cần cho SLO.
