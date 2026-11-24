# Không có phân vị hoặc bucket do cấu hình hoặc hệ thống nhận không hỗ trợ

Khi xem dashboard, bạn có thể chỉ thấy số lần ghi nhận (`count`), tổng thời gian (`sum`) hoặc giá trị lớn nhất (`max`), nhưng không thấy p50/p95/p99 hay các bucket của histogram. Điều này không nhất thiết có nghĩa Timer hoặc DistributionSummary không hoạt động. Micrometer mặc định không bật mọi dạng thống kê phân phối; percentile histogram phải được cấu hình, còn hệ thống nhận phải hiểu và xuất được loại dữ liệu tương ứng.

Trước khi sửa dashboard, cần phân biệt ba dạng dữ liệu: percentile được tính ngay trong ứng dụng, histogram bucket được gửi để backend tự tính percentile, và bucket SLO do ứng dụng chỉ định. Ba dạng này có cấu hình, khả năng tổng hợp và mức hỗ trợ backend khác nhau.

Trong module `OBSERVABILITY_INSTRUMENTATION_MICROMETER`, bài này hướng dẫn truy nguyên từ cấu hình meter đến registry, endpoint exposition và truy vấn backend để xác định chính xác vì sao percentile hoặc bucket không xuất hiện.

## 1. Phân biệt count/sum, percentile và histogram bucket

Timer và DistributionSummary ghi nhận các observation số học. Từ cùng một tập observation, Micrometer có thể xuất nhiều loại thống kê:

| Dữ liệu | Cách tạo | Dùng để làm gì? | Có thể gộp giữa instance? |
| --- | --- | --- | --- |
| `count` | Đếm số observation | Throughput, số lần thực thi | Có, nếu backend hỗ trợ counter aggregation |
| `sum` | Cộng các giá trị đã ghi | Tính trung bình cùng count | Có |
| `max` | Giá trị lớn nhất trong cửa sổ thống kê | Phát hiện spike gần đây | Không nên cộng/gộp như histogram |
| Client-side percentile | Micrometer ước lượng percentile trong ứng dụng | p50/p95/p99 theo từng Meter ID | Không; percentile giữa instance không thể cộng hoặc lấy trung bình đúng cách |
| Percentile histogram | Micrometer xuất các bucket được chọn sẵn | Backend tính quantile theo cửa sổ truy vấn | Có, bằng cách gộp bucket trước khi tính quantile |
| SLO buckets | Bucket tại các ngưỡng do ứng dụng chỉ định | Tỷ lệ observation nằm trong ngưỡng SLO | Có, nếu registry/backend xuất bucket tương ứng |

Ví dụ, `count=1000` và `sum=250` cho biết có 1000 observation với tổng giá trị 250 đơn vị. Hai số này không đủ để suy ra p95. Muốn tính percentile, cần các quantile đã tính ở client hoặc phân phối dữ liệu dạng histogram.

### Client-side percentile

Micrometer tính percentile trong process và xuất giá trị có tag `quantile` hoặc cách biểu diễn tương ứng của backend. Ví dụ `publishPercentiles(0.5, 0.95)` yêu cầu p50 và p95. Giá trị này chỉ mô tả Meter ID tương ứng, tức tên và tập tag của meter đó. Nếu ứng dụng có nhiều instance, không thể lấy trung bình p95 của các instance để có p95 toàn dịch vụ.

### Percentile histogram

Micrometer ghi nhận observation vào histogram và xuất các bucket. Backend dùng query language để tính percentile. Với Prometheus, dùng `histogram_quantile()`. Có thể gộp bucket của nhiều instance hoặc nhóm tag trước khi tính percentile, vì vậy đây thường là lựa chọn phù hợp cho dashboard toàn dịch vụ.

### SLO buckets

SLO buckets là các ranh giới cố định do bạn chọn, ví dụ 100 ms, 300 ms và 1 giây. Chúng hữu ích khi câu hỏi chính là “bao nhiêu phần trăm request hoàn thành trong 300 ms?”. SLO buckets không tự tạo p95 nếu không có đủ bucket phù hợp để backend nội suy quantile, nhưng chúng cho phép tính tỷ lệ đáp ứng ngưỡng một cách trực tiếp.

## 2. Mặc định không bật percentile histogram

Với Timer và DistributionSummary, mặc định Micrometer không bật client-side percentile hoặc percentile histogram. Vì vậy, việc chỉ thấy `count`, `sum` và `max` là hành vi bình thường nếu chưa cấu hình distribution statistics.

Với Prometheus Timer, exposition mặc định thường có các series tương ứng với:

```text
checkout_operation_duration_seconds_count
checkout_operation_duration_seconds_sum
checkout_operation_duration_seconds_max
```

Khi bật percentile histogram hoặc khai báo SLO boundaries, registry có thể xuất thêm series bucket:

```text
checkout_operation_duration_seconds_bucket{le="0.1"}
checkout_operation_duration_seconds_bucket{le="0.3"}
checkout_operation_duration_seconds_bucket{le="1.0"}
checkout_operation_duration_seconds_bucket{le="+Inf"}
```

Đây là ví dụ tên đã được Prometheus chuẩn hóa; tên thực tế phụ thuộc meter name, base unit, tag và phiên bản registry. Với classic histogram, bucket là bộ đếm tích lũy: bucket `le="0.3"` chứa tất cả observation có giá trị nhỏ hơn hoặc bằng 0.3 giây. Bucket `+Inf` phải bằng tổng count.

## 3. Bật histogram bằng Spring Boot properties

Spring Boot cho phép cấu hình phân phối theo prefix tên meter. Ví dụ bật percentile histogram cho Timer `checkout.operation.duration`, đồng thời giới hạn miền giá trị dự kiến và thêm các ngưỡng SLO:

```yaml
management:
  metrics:
    distribution:
      percentiles-histogram:
        checkout.operation.duration: true
      minimum-expected-value:
        checkout.operation.duration: 1ms
      maximum-expected-value:
        checkout.operation.duration: 10s
      slo:
        checkout.operation.duration:
          - 100ms
          - 300ms
          - 1s
```

Các thuộc tính có ý nghĩa:

| Property | Tác dụng |
| --- | --- |
| `percentiles-histogram` | Yêu cầu xuất histogram để backend có thể tính percentile nếu registry hỗ trợ |
| `minimum-expected-value` | Giới hạn dưới của miền bucket được chọn |
| `maximum-expected-value` | Giới hạn trên của miền bucket được chọn |
| `slo` | Thêm bucket tại các ranh giới SLO được chỉ định |
| `percentiles` | Yêu cầu Micrometer tính và xuất percentile phía client |
| `expiry`, `buffer-length` | Điều khiển cửa sổ thống kê phân phối có suy giảm theo thời gian |

Các key dưới `management.metrics.distribution.*` khớp theo tiền tố tên meter; cấu hình cụ thể nhất được ưu tiên. Ví dụ trên chỉ bật histogram cho meter được nêu, tránh tăng bucket cho tất cả meter không cần thiết.

Nếu muốn cấu hình percentile phía client thay vì histogram, có thể thêm:

```yaml
management:
  metrics:
    distribution:
      percentiles:
        checkout.operation.duration:
          - 0.5
          - 0.95
          - 0.99
```

Giá trị percentile nằm trong khoảng 0.0 đến 1.0: `0.5` là p50, `0.95` là p95 và `0.99` là p99. Client-side percentile không thay thế histogram nếu cần tổng hợp giữa nhiều instance.

Không bật đồng thời hai dạng chỉ vì nghĩ rằng càng nhiều dữ liệu càng tốt. Chọn loại phù hợp với backend và câu hỏi truy vấn; việc xuất cả percentile và histogram làm tăng số series, bộ nhớ và chi phí ingest.

## 4. Cấu hình trực tiếp trên Timer.Builder

Nếu ứng dụng tự đăng ký Timer, có thể cấu hình distribution statistics ngay trên builder:

```java
import java.time.Duration;

import io.micrometer.core.instrument.Timer;

Timer timer = Timer.builder("checkout.operation.duration")
        .description("Time spent processing checkout")
        .publishPercentileHistogram()
        .serviceLevelObjectives(
                Duration.ofMillis(100),
                Duration.ofMillis(300),
                Duration.ofSeconds(1))
        .minimumExpectedValue(Duration.ofMillis(1))
        .maximumExpectedValue(Duration.ofSeconds(10))
        .register(registry);
```

`publishPercentileHistogram()` yêu cầu histogram bucket được xuất nếu registry hỗ trợ percentile aggregation. `serviceLevelObjectives(...)` thêm các bucket cố định tại ngưỡng cần theo dõi. `minimumExpectedValue(...)` và `maximumExpectedValue(...)` giới hạn miền bucket và footprint histogram.

Nếu chỉ cần client-side percentiles, dùng cấu hình riêng:

```java
Timer timer = Timer.builder("checkout.operation.duration")
        .publishPercentiles(0.5, 0.95, 0.99)
        .register(registry);
```

Khi kiểm thử Prometheus Java Client 1.x, không cấu hình client-side quantiles và histogram cho cùng một metric family. Prometheus Java Client mới yêu cầu metric family có một kiểu nhất quán; Micrometer ưu tiên histogram khi cả hai cùng được yêu cầu và có thể bỏ qua client-side percentiles. Hãy chọn histogram và tính quantile bằng PromQL nếu cần tổng hợp.

## 5. Cấu hình DistributionSummary khác Timer ở đơn vị

`DistributionSummary` cũng hỗ trợ `publishPercentiles`, `publishPercentileHistogram`, `serviceLevelObjectives`, `minimumExpectedValue` và `maximumExpectedValue`. Khác Timer, summary không tự chuẩn hóa duration về giây; miền giá trị phụ thuộc dữ liệu bạn ghi.

Ví dụ đo kích thước payload theo byte:

```java
import io.micrometer.core.instrument.DistributionSummary;

DistributionSummary payloadSize = DistributionSummary.builder("http.response.payload.size")
        .baseUnit("bytes")
        .publishPercentileHistogram()
        .serviceLevelObjectives(1_024, 10_240, 102_400)
        .minimumExpectedValue(1.0)
        .maximumExpectedValue(1_000_000.0)
        .register(registry);
```

Với summary đo tỷ lệ trong khoảng 0 đến 1, histogram bucket mặc định có thể không phù hợp nếu không giới hạn miền. Có thể scale dữ liệu lên 100 để biểu diễn phần trăm, rồi cấu hình `maximumExpectedValue(100)` và các SLO như 70, 80, 90. Điều quan trọng là phải thống nhất đơn vị ở lúc record, tên metric, cấu hình bucket và dashboard.

## 6. Registry phải hỗ trợ dạng dữ liệu được yêu cầu

`publishPercentileHistogram()` không buộc mọi backend nhận histogram. Micrometer chỉ xuất aggregable percentile histogram cho các registry có khả năng hỗ trợ. Theo tài liệu Micrometer, Prometheus và Atlas là các hệ thống có thể tính percentile từ histogram; với hệ thống không hỗ trợ, cờ percentile histogram có thể không tạo bucket nào.

`serviceLevelObjectives(...)` là cách yêu cầu các ranh giới bucket cụ thể. Micrometer có thể xuất histogram chỉ gồm các SLO boundaries trên một số hệ thống không hỗ trợ percentile histogram tổng quát, nhưng kết quả cuối cùng vẫn phụ thuộc adapter và kiểu metric mà backend nhận hỗ trợ.

| Hệ thống nhận | Cách tiếp cận | Điều cần xác minh |
| --- | --- | --- |
| Prometheus | Percentile histogram hoặc SLO buckets; tính quantile bằng `histogram_quantile()` | Raw scrape có `_bucket`, `_count`, `_sum`; phiên bản Prometheus registry/client |
| Atlas | Percentile histogram và truy vấn percentile của Atlas | Backend nhận histogram và cấu hình step/rollup |
| Datadog | Kiểu distribution/histogram tùy registry adapter và transport | Registry dùng API hay DogStatsD; backend metric type và query syntax |
| InfluxDB | Hỗ trợ phụ thuộc registry adapter, phiên bản và schema export | Raw line protocol/measurement có trường hoặc bucket cần thiết hay chỉ count/sum |
| Backend chỉ nhận gauge/summary đơn giản | Có thể không có bucket hoặc percentile server-side | Dùng client-side percentile nếu adapter/backend hỗ trợ, hoặc đổi pipeline/registry |

Không suy luận khả năng backend từ việc Micrometer API có method `publishPercentileHistogram()`. Hãy kiểm tra tài liệu adapter của đúng phiên bản và dữ liệu thực tế sau khi export.

## 7. Xác minh cấu hình có áp dụng cho đúng meter

Một trong các nguyên nhân phổ biến là cấu hình dùng sai tên meter. Spring Boot properties khớp theo tên meter đã đăng ký, không phải tên class Java, tên endpoint tùy ý hoặc tên sau khi Prometheus đã chuẩn hóa.

Ví dụ code đăng ký:

```java
Timer.builder("checkout.operation.duration")
        .register(registry);
```

Property phải dùng chính tên Micrometer:

```yaml
management:
  metrics:
    distribution:
      percentiles-histogram:
        checkout.operation.duration: true
```

Không dùng tên Prometheus đã đổi dấu chấm thành dấu gạch dưới như `checkout_operation_duration_seconds_bucket` làm key cấu hình. Cũng cần chú ý các meter được tạo bởi instrumentation tự động có tên khác với meter custom của ứng dụng.

Các điểm cần kiểm tra:

- Tên meter chính xác, bao gồm prefix và dấu chấm.
- Meter có phải `Timer` hoặc `DistributionSummary` không; Counter/Gauge không có percentile histogram theo cách này.
- Meter có bị `MeterFilter` từ chối hoặc đổi tên không.
- `MeterFilter` cấu hình distribution có được gắn vào đúng registry không.
- Cấu hình có được nạp trong profile/environment đang chạy không.
- Meter đã được đăng ký trước khi cấu hình được áp dụng hay chưa.
- Nếu có nhiều registry, kiểm tra cấu hình và output của từng registry riêng.

Distribution config được dùng khi meter được đăng ký. Thay đổi properties hoặc filter sau khi meter đã tồn tại không tự biến meter hiện tại thành histogram. Trong ứng dụng đang chạy, cần tạo lại meter/registry hoặc khởi động lại theo cách triển khai phù hợp để xác nhận cấu hình mới.

## 8. Dùng MeterFilter để cấu hình một nhóm meter

Nếu meter đến từ thư viện dùng chung và không thể sửa builder, có thể dùng `MeterFilter` để áp dụng distribution config cho một prefix hoặc một tên cụ thể:

```java
import java.time.Duration;

import io.micrometer.core.instrument.Meter;
import io.micrometer.core.instrument.config.MeterFilter;
import io.micrometer.core.instrument.distribution.DistributionStatisticConfig;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class DistributionMetricsConfiguration {
    @Bean
    MeterFilter checkoutHistogramFilter() {
        return new MeterFilter() {
            @Override
            public DistributionStatisticConfig configure(
                    Meter.Id id, DistributionStatisticConfig config) {
                if (id.getName().equals("checkout.operation.duration")
                        && id.getType() == Meter.Type.TIMER) {
                    DistributionStatisticConfig checkoutConfig =
                            DistributionStatisticConfig.builder()
                                    .percentilesHistogram(true)
                                    .minimumExpectedValue(Duration.ofMillis(1).toNanos())
                                    .maximumExpectedValue(Duration.ofSeconds(10).toNanos())
                                    .build();
                    return checkoutConfig.merge(config);
                }
                return config;
            }
        };
    }
}
```

Với Timer, giá trị numeric trong `DistributionStatisticConfig` là nanoseconds. Khi dùng `Timer.Builder` hoặc Spring Boot properties, ưu tiên `Duration` để code dễ đọc và tránh nhầm đơn vị. Phương thức `merge(config)` giữ các cấu hình đã có theo quy tắc ưu tiên của Micrometer; cần kiểm tra thứ tự filter và cấu hình cuối cùng nếu có nhiều filter.

Không cấu hình histogram cho mọi meter nếu chỉ một vài Timer cần percentile. Mỗi bucket có thể tạo thêm một time series cho mỗi tổ hợp tag; bật histogram toàn cục dễ làm tăng mạnh cardinality và chi phí backend.

## 9. Kiểm tra raw exposition thay vì chỉ nhìn `/actuator/metrics`

Endpoint `/actuator/metrics/{name}` hữu ích để xác nhận meter tồn tại và đọc thống kê cơ bản. Tuy nhiên, endpoint này không phải lúc nào cũng biểu diễn đầy đủ bucket theo định dạng backend. Để xác minh Prometheus histogram, hãy xem raw exposition ở `/actuator/prometheus` hoặc gọi `PrometheusMeterRegistry.scrape()`.

Spring Boot ví dụ:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
```

Chỉ expose endpoint cần thiết và bảo vệ endpoint metrics theo chính sách mạng/xác thực của môi trường. Khi truy cập `/actuator/prometheus`, tìm tên đã chuẩn hóa của meter và các series:

```text
checkout_operation_duration_seconds_bucket{le="0.1",...} 42
checkout_operation_duration_seconds_bucket{le="0.3",...} 91
checkout_operation_duration_seconds_bucket{le="1.0",...} 99
checkout_operation_duration_seconds_bucket{le="+Inf",...} 100
checkout_operation_duration_seconds_count{...} 100
checkout_operation_duration_seconds_sum{...} 18.4
```

Nếu chỉ thấy `_count`, `_sum` và `_max`, hãy kiểm tra histogram/SLO config và registry support. Nếu thấy `_bucket` ở endpoint nhưng dashboard không có p95, vấn đề nhiều khả năng nằm ở scrape, relabeling, query hoặc dữ liệu chưa đủ.

## 10. Tính percentile từ histogram bằng PromQL

Với classic histogram, bucket có nhãn `le` là giới hạn trên và giá trị bucket là counter tích lũy. Tính p95 cho một meter:

```promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(checkout_operation_duration_seconds_bucket[5m])
  )
)
```

Nếu cần giữ chiều `outcome`:

```promql
histogram_quantile(
  0.95,
  sum by (le, outcome) (
    rate(checkout_operation_duration_seconds_bucket[5m])
  )
)
```

Nếu muốn tính p95 toàn dịch vụ từ nhiều instance, không giữ nhãn `instance` trong phép `sum`; histogram bucket được cộng trước, sau đó `histogram_quantile` mới nội suy quantile. Không lấy trung bình p95 của từng instance.

Với client-side percentile, truy vấn thường lọc series có nhãn `quantile="0.95"`:

```promql
checkout_operation_duration_seconds{quantile="0.95"}
```

Series này chỉ có ý nghĩa trong phạm vi Meter ID đã được tính. Không cộng hoặc lấy trung bình quantile giữa instance để suy ra p95 tổng.

## 11. Tính tỷ lệ đáp ứng SLO từ bucket

Nếu chỉ quan tâm tỷ lệ request hoàn tất trong 300 ms, không nhất thiết phải tính p95. Với bucket `le="0.3"`, có thể lấy tốc độ request dưới ngưỡng chia cho tổng tốc độ request:

```promql
sum(rate(checkout_operation_duration_seconds_bucket{le="0.3"}[5m]))
/
sum(rate(checkout_operation_duration_seconds_count[5m]))
```

Kết quả là tỷ lệ observation có duration nhỏ hơn hoặc bằng 300 ms trong cửa sổ 5 phút. Nếu cần phân nhóm theo outcome, thêm nhãn tương ứng vào cả tử số và mẫu số, hoặc dùng `sum by (outcome)` để giữ chiều đó.

Bucket SLO phải được cấu hình ở đúng đơn vị. Với Timer, `Duration.ofMillis(300)` được chuyển thành 0.3 giây trong Prometheus exposition. Với DistributionSummary, giá trị là số đo raw mà ứng dụng ghi, ví dụ byte hoặc phần trăm.

## 12. Kiểm tra registry Prometheus mới và legacy

Micrometer hỗ trợ hai adapter Prometheus:

| Dependency | Prometheus Java Client | Lưu ý |
| --- | --- | --- |
| `micrometer-registry-prometheus` | Client 1.x mới | Là lựa chọn hiện đại; kiểm tra quy tắc metric family nghiêm ngặt |
| `micrometer-registry-prometheus-simpleclient` | Client 0.x legacy | Dành cho ứng dụng còn phụ thuộc client cũ; có khác biệt exposition và migration |

Với client 1.x, không thể xuất client-side quantiles và histogram trong cùng một metric family như thể đó là một loại metric hợp lệ duy nhất. Micrometer ưu tiên histogram và bỏ qua quantiles nếu cả hai được yêu cầu cùng metric name. Điều này có thể khiến bạn không thấy nhãn `quantile` dù đã cấu hình `percentiles`.

Hãy kiểm tra dependency thực tế trong runtime classpath và migration guide của phiên bản Micrometer đang dùng. Không vội hạ phiên bản registry hoặc quay lại client legacy chỉ để giữ cách query cũ; trước tiên hãy chuyển dashboard sang histogram và `histogram_quantile()` nếu backend hỗ trợ.

## 13. Kiểm thử histogram bằng PrometheusMeterRegistry

`SimpleMeterRegistry` phù hợp để kiểm tra count và total time, nhưng không phải lựa chọn tốt để xác minh Prometheus bucket exposition. Dùng registry Prometheus trong test để kiểm tra dữ liệu raw:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;
import java.util.concurrent.TimeUnit;

import io.micrometer.core.instrument.Timer;
import io.micrometer.prometheusmetrics.PrometheusConfig;
import io.micrometer.prometheusmetrics.PrometheusMeterRegistry;
import org.junit.jupiter.api.Test;

class PrometheusHistogramTest {
    @Test
    void exportsBucketsWhenHistogramIsEnabled() {
        try (PrometheusMeterRegistry registry =
                new PrometheusMeterRegistry(PrometheusConfig.DEFAULT)) {
            Timer timer = Timer.builder("checkout.operation.duration")
                    .publishPercentileHistogram()
                    .serviceLevelObjectives(
                            Duration.ofMillis(100),
                            Duration.ofMillis(300))
                    .minimumExpectedValue(Duration.ofMillis(1))
                    .maximumExpectedValue(Duration.ofSeconds(10))
                    .register(registry);

            timer.record(80, TimeUnit.MILLISECONDS);
            timer.record(250, TimeUnit.MILLISECONDS);
            timer.record(700, TimeUnit.MILLISECONDS);

            String scrape = registry.scrape();
            assertThat(scrape).contains("checkout_operation_duration_seconds_bucket");
            assertThat(scrape).contains("le=\"0.1\"");
            assertThat(scrape).contains("le=\"0.3\"");
            assertThat(scrape).contains("checkout_operation_duration_seconds_count");
        }
    }
}
```

Package `io.micrometer.prometheusmetrics` thuộc adapter Prometheus Java Client 1.x. Nếu dự án dùng adapter legacy `micrometer-registry-prometheus-simpleclient`, package và API registry khác; dùng đúng import theo dependency đang có.

Để xác nhận lỗi do cấu hình, có thể viết test đối chứng tạo Timer không bật histogram và xác nhận exposition không có `_bucket`, sau đó bật histogram và xác nhận bucket xuất hiện. Test như vậy chứng minh khác biệt do cấu hình chứ không phải do Prometheus endpoint hoặc query.

## 14. Chẩn đoán theo biểu hiện

| Biểu hiện | Nguyên nhân có thể | Cách kiểm tra và xử lý |
| --- | --- | --- |
| Chỉ có count/sum/max | Histogram và SLO chưa bật | Bật `percentiles-histogram` hoặc `slo` cho đúng meter |
| Đã bật histogram nhưng không có bucket | Registry không hỗ trợ aggregable histogram | Kiểm tra adapter/backend; thử SLO boundaries hoặc backend khác |
| Có `quantile` nhưng không có `_bucket` | Chỉ bật client-side `percentiles` | Bật percentile histogram nếu cần aggregation |
| Có `_bucket` nhưng không có p95 trên dashboard | Query sai tên/đơn vị hoặc chưa dùng `histogram_quantile` | Kiểm tra raw exposition và PromQL |
| Property không có tác dụng | Key dùng tên meter sai hoặc profile không được nạp | So sánh với tên trong code và kiểm tra effective configuration |
| Một số Timer có bucket, số khác không | Filter chỉ áp dụng một nhóm hoặc meter type khác | Kiểm tra `MeterFilter`, tên prefix và type |
| Bucket không bao phủ latency thực tế | Min/max expected value quá hẹp | Điều chỉnh miền dự kiến, thêm SLO boundary phù hợp |
| Bucket quá nhiều | Miền min/max rộng hoặc quá nhiều tag | Giới hạn miền, chỉ bật meter cần thiết, giảm cardinality |
| Có bucket nhưng số liệu bằng 0 | Chưa có observation trong cửa sổ query hoặc meter chưa được record | Tạo dữ liệu thử, mở rộng time range và kiểm tra scrape interval |
| `quantile` biến mất sau nâng cấp | Prometheus Java Client 1.x hoặc migration behavior | Chuyển sang histogram và query server-side |
| SLO threshold không khớp | Nhầm ms, seconds hoặc đơn vị summary | Xác minh unit của Timer/DistributionSummary và `le` label |
| Bucket có ở một instance nhưng không ở instance khác | Cấu hình/profile/dependency không đồng nhất | So sánh version, config, tag schema và runtime classpath |

## 15. Quy trình điều tra khi không có percentile hoặc bucket

Thực hiện lần lượt để tránh sửa dashboard khi dữ liệu chưa được xuất:

1. **Xác nhận loại meter:** kiểm tra meter là `Timer` hoặc `DistributionSummary`, không phải Counter/Gauge.
2. **Xác nhận cấu hình:** kiểm tra `publishPercentiles`, `publishPercentileHistogram`, `serviceLevelObjectives` hoặc Spring Boot distribution properties.
3. **Xác nhận tên:** đối chiếu tên meter trong code với key cấu hình; không dùng tên đã chuẩn hóa ở backend.
4. **Xác nhận registry:** kiểm tra đúng Prometheus/Atlas/Datadog/Influx adapter và phiên bản đang chạy.
5. **Xác nhận capability:** hỏi registry/backend có xuất aggregable histogram hoặc SLO buckets không.
6. **Kiểm tra filter:** xác nhận `MeterFilter` không loại meter và distribution config được áp dụng khi meter đăng ký.
7. **Tạo observation:** record nhiều giá trị khác nhau để có dữ liệu trong histogram.
8. **Đọc raw exposition:** xem `/actuator/prometheus` hoặc scrape output; tìm `_bucket`, `le`, `_count`, `_sum` hoặc `quantile`.
9. **Kiểm tra query:** dùng `histogram_quantile()` cho bucket; dùng nhãn quantile cho client-side percentile; không aggregate client quantile giữa instance.
10. **Kiểm tra đơn vị và thời gian:** xác minh giây/millisecond, cửa sổ `rate()` và scrape interval.
11. **Kiểm tra migration:** nếu vừa đổi Prometheus client hoặc Micrometer, so sánh raw output và metric family type.
12. **Đánh giá cardinality:** chỉ bật histogram cho các meter có nhu cầu và giới hạn tag/bucket phù hợp.

## 16. Nguyên tắc chọn cấu hình

| Nhu cầu | Cấu hình khuyến nghị |
| --- | --- |
| p95 toàn dịch vụ trên Prometheus | `publishPercentileHistogram()` hoặc Spring Boot `percentiles-histogram`, rồi dùng `histogram_quantile()` |
| Tỷ lệ request dưới ngưỡng 300 ms | SLO bucket tại 300 ms và truy vấn bucket/count |
| Backend không hỗ trợ server-side histogram nhưng nhận percentile | `publishPercentiles(...)`, theo dõi riêng từng Meter ID |
| Muốn giới hạn bộ nhớ/bucket | Đặt minimum/maximum expected value và chỉ bật histogram cho meter cần thiết |
| Muốn histogram cho thư viện không thể sửa code | Dùng `MeterFilter` theo tên meter |
| Muốn thống kê payload size | `DistributionSummary` với base unit và miền giá trị rõ ràng |

Không có percentile hoặc bucket thường xuất phát từ một trong ba nguyên nhân: chưa bật cấu hình, cấu hình không khớp meter, hoặc registry/backend không hỗ trợ loại dữ liệu yêu cầu. Hãy kiểm tra raw exposition trước, sau đó mới sửa query. Khi dùng Prometheus, percentile histogram cho phép gộp bucket giữa các instance và tính quantile ở server; khi chỉ cần kiểm tra ngưỡng SLO, bucket cố định thường đơn giản và rẻ hơn.

## Tài liệu tham khảo

- [Micrometer 1.18: Histograms and Percentiles](https://docs.micrometer.io/micrometer/reference/concepts/histogram-quantiles.html)
- [Micrometer 1.18: Prometheus Registry](https://docs.micrometer.io/micrometer/reference/implementations/prometheus.html)
- [Micrometer 1.18: Distribution Summaries](https://docs.micrometer.io/micrometer/reference/concepts/distribution-summaries.html)
- [Spring Boot 3.5: Metrics and distribution properties](https://docs.spring.io/spring-boot/3.5/reference/actuator/metrics.html)
- [Prometheus: Histograms and summaries](https://prometheus.io/docs/practices/histograms/)
- [Micrometer 1.13 Migration Guide: Histogram vs. Summary](https://github.com/micrometer-metrics/micrometer/wiki/1.13-Migration-Guide)
