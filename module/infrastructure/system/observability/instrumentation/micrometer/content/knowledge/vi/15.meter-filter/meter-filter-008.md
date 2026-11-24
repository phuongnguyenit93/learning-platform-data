# Cấu hình thống kê phân phối theo nhóm meter

Trong module `OBSERVABILITY_INSTRUMENTATION_MICROMETER`, `Timer` và `DistributionSummary` có thể ghi nhận phân phối của các giá trị quan sát. Tùy backend, ứng dụng có thể cần histogram, percentile hoặc các ngưỡng SLO để trả lời câu hỏi vận hành. Nếu cấu hình riêng từng meter bằng builder, nhiều thành phần có thể lặp lại cùng một thiết lập và dễ lệch nhau.

`MeterFilter` cho phép áp dụng cấu hình thống kê theo nhóm meter ngay tại `MeterRegistry`. Dựa vào tên, loại meter và tag trong `Meter.Id`, filter có thể bật percentile histogram, đặt SLO và giới hạn miền giá trị cho một nhóm `Timer` hoặc `DistributionSummary`. Bài này trình bày cách thiết kế các nhóm, cách chọn đơn vị đúng cho từng loại meter và cách xác minh cấu hình ở endpoint export.

## 1. Thống kê phân phối được cấu hình ở đâu?

Khi ứng dụng ghi nhận một `Timer` hoặc `DistributionSummary`, meter lưu thống kê cơ bản như số lần ghi nhận và tổng giá trị. Nếu cần xem phân phối chi tiết, Micrometer có thể bổ sung percentile phía client hoặc histogram bucket tùy cấu hình và registry.

Các cấu hình thường gặp gồm:

- `percentilesHistogram`: yêu cầu tạo histogram bucket phù hợp với registry hỗ trợ.
- `percentiles`: chọn các percentile được tính ở phía client, chẳng hạn p50, p95 và p99.
- `serviceLevelObjectives`: khai báo các ngưỡng cần quan sát, ví dụ request dưới 100 ms hoặc payload dưới 4 KiB.
- `minimumExpectedValue` và `maximumExpectedValue`: giới hạn miền giá trị cho histogram, giúp kiểm soát số bucket và chi phí bộ nhớ.
- `expiry` và `bufferLength`: điều chỉnh cửa sổ lưu trữ thống kê phân phối trong các implementation hỗ trợ.

Builder của từng meter có thể khai báo trực tiếp các giá trị này. `MeterFilter.configure(...)` cho phép đặt chính sách chung cho mọi meter phù hợp với điều kiện lọc, nhờ đó các nhóm endpoint hoặc nhóm nghiệp vụ dùng cấu hình nhất quán.

## 2. MeterFilter.configure hoạt động như thế nào?

`MeterFilter` là một bộ lọc được áp dụng khi meter được đăng ký vào registry. Phương thức `configure(Meter.Id, DistributionStatisticConfig)` nhận định danh meter cùng cấu hình phân phối hiện có và trả về cấu hình cần dùng cho meter đó.

`Meter.Id` cung cấp các thông tin có thể dùng để phân nhóm:

- `getName()`: tên meter, ví dụ `http.server.requests` hoặc `orders.payload.size`.
- `getType()`: loại meter, ví dụ `TIMER` hoặc `DISTRIBUTION_SUMMARY`.
- `getTag(key)`: giá trị tag, ví dụ `uri`, `method`, `result` hoặc `format` nếu meter có tag đó.

Một filter có thể chỉ áp dụng cho meter tên bắt đầu bằng `http.server.requests` và có loại `TIMER`, trong khi một quy tắc khác áp dụng cho meter `orders.payload.size` có loại `DISTRIBUTION_SUMMARY`. Điều kiện theo loại giúp tránh vô tình áp dụng cấu hình thời gian cho một meter đo kích thước.

Filter chỉ cấu hình thống kê phân phối. Nó không tự tạo meter, không ghi thêm quan sát và không biến `Counter` hoặc `Gauge` thành meter phân phối.

## 3. Cấu hình histogram cho nhóm Timer HTTP

Ví dụ sau bật histogram và SLO cho các timer HTTP do Spring Boot tạo. Với `Timer`, các giá trị trong `DistributionStatisticConfig` dùng đơn vị nội bộ nanosecond, vì vậy phải chuyển `Duration` sang nanosecond trước khi truyền vào cấu hình.

```java
import io.micrometer.core.instrument.Meter;
import io.micrometer.core.instrument.config.MeterFilter;
import io.micrometer.core.instrument.distribution.DistributionStatisticConfig;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.time.Duration;

@Configuration
public class MetricsConfiguration {

    @Bean
    MeterFilter httpRequestDistributionConfig() {
        DistributionStatisticConfig httpConfig =
            DistributionStatisticConfig.builder()
                .percentilesHistogram(true)
                .serviceLevelObjectives(
                    Duration.ofMillis(100).toNanos(),
                    Duration.ofMillis(300).toNanos(),
                    Duration.ofSeconds(1).toNanos())
                .minimumExpectedValue(Duration.ofMillis(1).toNanos())
                .maximumExpectedValue(Duration.ofSeconds(10).toNanos())
                .build();

        return new MeterFilter() {
            @Override
            public DistributionStatisticConfig configure(
                    Meter.Id id,
                    DistributionStatisticConfig config) {
                if (id.getName().startsWith("http.server.requests")
                        && id.getType() == Meter.Type.TIMER) {
                    return httpConfig.merge(config);
                }
                return config;
            }
        };
    }
}
```

Trong cấu hình này:

- Chỉ meter có tên bắt đầu bằng `http.server.requests` được chọn.
- Điều kiện `Meter.Type.TIMER` giới hạn filter vào timer.
- Histogram được bật để backend có thể nhận bucket.
- SLO 100 ms, 300 ms và 1 giây tạo các ngưỡng có ý nghĩa vận hành.
- Miền 1 ms đến 10 giây giới hạn phạm vi histogram cho request HTTP.

Các giá trị trên là ví dụ. Hãy chọn SLO và miền min/max theo đặc tính endpoint của ứng dụng. Nếu hệ thống có request hợp lệ kéo dài hơn 10 giây, cần tăng giới hạn trên để không làm mất độ phân giải cần thiết ở vùng giá trị đó.

## 4. Cấu hình nhóm DistributionSummary theo đại lượng nghiệp vụ

`DistributionSummary` đo giá trị số không phải thời gian. Ví dụ, payload được ghi nhận theo byte. Vì vậy, các giá trị SLO, min và max truyền vào filter phải dùng cùng đơn vị mà ứng dụng ghi vào summary.

```java
@Bean
MeterFilter payloadDistributionConfig() {
    DistributionStatisticConfig payloadConfig =
        DistributionStatisticConfig.builder()
            .percentilesHistogram(true)
            .serviceLevelObjectives(1024, 4096, 8192)
            .minimumExpectedValue(1.0)
            .maximumExpectedValue(65536.0)
            .build();

    return new MeterFilter() {
        @Override
        public DistributionStatisticConfig configure(
                Meter.Id id,
                DistributionStatisticConfig config) {
            if (id.getName().startsWith("orders.payload.size")
                    && id.getType() == Meter.Type.DISTRIBUTION_SUMMARY) {
                return payloadConfig.merge(config);
            }
            return config;
        }
    };
}
```

Meter được đăng ký trong ứng dụng:

```java
DistributionSummary payloadSize =
    DistributionSummary.builder("orders.payload.size")
        .baseUnit("bytes")
        .tag("format", "json")
        .register(registry);

payloadSize.record(requestBody.length);
```

Builder của meter không cần lặp lại histogram và SLO; filter sẽ bổ sung cấu hình cho mọi meter thuộc nhóm tên và loại đã chọn. Tuy nhiên, `baseUnit("bytes")` vẫn có ích để mô tả đơn vị metric, còn code ghi nhận phải nhất quán với byte.

## 5. Gộp nhiều nhóm trong một filter

Khi có một số nhóm meter rõ ràng, có thể quản lý chúng trong cùng một `MeterFilter`. Cách này giúp đọc được toàn bộ chính sách thống kê tại một vị trí:

```java
@Bean
MeterFilter distributionConfigByGroup() {
    DistributionStatisticConfig httpTimers =
        DistributionStatisticConfig.builder()
            .percentilesHistogram(true)
            .serviceLevelObjectives(
                Duration.ofMillis(100).toNanos(),
                Duration.ofMillis(300).toNanos(),
                Duration.ofSeconds(1).toNanos())
            .minimumExpectedValue(Duration.ofMillis(1).toNanos())
            .maximumExpectedValue(Duration.ofSeconds(10).toNanos())
            .build();

    DistributionStatisticConfig payloadSummaries =
        DistributionStatisticConfig.builder()
            .percentilesHistogram(true)
            .serviceLevelObjectives(1024, 4096, 8192)
            .minimumExpectedValue(1.0)
            .maximumExpectedValue(65536.0)
            .build();

    return new MeterFilter() {
        @Override
        public DistributionStatisticConfig configure(
                Meter.Id id,
                DistributionStatisticConfig config) {
            if (id.getType() == Meter.Type.TIMER
                    && id.getName().startsWith("http.server.requests")) {
                return httpTimers.merge(config);
            }

            if (id.getType() == Meter.Type.DISTRIBUTION_SUMMARY
                    && id.getName().startsWith("orders.payload.size")) {
                return payloadSummaries.merge(config);
            }

            return config;
        }
    };
}
```

Các nhóm có đơn vị khác nhau nên dùng cấu hình riêng. Không dùng chung một mảng SLO cho HTTP timer và payload summary: 100 ms có ý nghĩa với thời lượng, còn 100 byte là một ngưỡng kích thước hoàn toàn khác.

## 6. Merge cấu hình để giữ phần mặc định

Trong ví dụ, filter trả về `customConfig.merge(config)`. Cách merge này đặt các trường đã khai báo trong `customConfig` làm chính sách cho nhóm meter, đồng thời giữ lại các giá trị chưa được chỉ định từ cấu hình hiện có.

Không nên thay toàn bộ cấu hình hiện có bằng một object chỉ chứa một trường nếu điều đó vô tình làm mất các thiết lập khác như expiry, buffer length hoặc percentile precision. Dùng `merge` giúp filter chỉ ghi đè những thuộc tính mà nó chủ động cấu hình.

Nếu nhiều filter cùng cấu hình một meter, thứ tự áp dụng và các trường được merge có thể ảnh hưởng kết quả cuối. Hãy tránh nhiều filter cùng sở hữu một chính sách histogram cho một nhóm meter. Tập trung cấu hình ở một nơi hoặc thiết lập thứ tự rõ ràng và kiểm tra kết quả sau khi tất cả filter đã được áp dụng.

## 7. Phân nhóm bằng tên, loại meter và tag

Tên meter là cách phổ biến để xác định nhóm. Có thể dùng prefix khi một nhóm gồm nhiều meter liên quan, hoặc dùng tên chính xác nếu chỉ muốn cấu hình một meter.

Tag có thể giúp chia nhỏ một nhóm. Ví dụ, nếu chỉ muốn áp dụng histogram cho route API có tag `uri`, có thể thêm điều kiện:

```java
if (id.getType() == Meter.Type.TIMER
        && id.getName().equals("http.server.requests")
        && id.getTag("uri") != null
        && id.getTag("uri").startsWith("/api/")) {
    return httpConfig.merge(config);
}
```

Chỉ dùng điều kiện này nếu instrumentation thực tế có tag `uri` chứa route pattern. Với Spring Boot, tag URI thường nên là route template như `/api/orders/{id}` thay vì URL có ID thực tế. Tránh dùng tag chứa dữ liệu tùy ý hoặc giá trị duy nhất cho mỗi request để phân nhóm filter.

Khi cần áp dụng cùng một chính sách cho nhiều tên meter, có thể dùng `startsWith` hoặc tập tên đã định nghĩa. Không nên dùng prefix quá rộng như `http` nếu trong registry có những meter HTTP khác với mục đích, đơn vị hoặc yêu cầu SLO khác nhau.

## 8. Filter phải được đăng ký trước khi meter hình thành

`MeterFilter` tham gia vào quá trình đăng ký meter. Khi meter đã tồn tại với cùng định danh trong registry, gọi đăng ký lại thường trả về meter hiện có; filter mới không phải cơ chế cập nhật cấu hình thống kê của meter đó.

Trong Spring Boot, khai báo `MeterFilter` dưới dạng bean cấu hình để registry nhận filter trong quá trình khởi tạo. Tránh tạo meter quá sớm trong static initializer hoặc trước khi cấu hình registry được áp dụng.

Nếu histogram không xuất hiện dù filter đã được thêm, hãy kiểm tra:

1. Filter bean có được Spring tạo và gắn vào registry cần dùng không.
2. Meter được đăng ký sau khi filter đã được áp dụng không.
3. Điều kiện tên, loại và tag có khớp `Meter.Id` thực tế không.
4. Meter có bị một filter khác từ chối hoặc cấu hình lại không.
5. Registry/exporter đang dùng có hỗ trợ kiểu thống kê được yêu cầu không.

## 9. Ảnh hưởng của histogram và percentile đến cardinality

Histogram tạo nhiều time series cho mỗi meter và mỗi tổ hợp tag. Khi áp dụng filter cho một prefix rộng, số lượng series có thể tăng nhanh vì nhiều meter được bật histogram cùng lúc.

Ví dụ, một timer có 20 route pattern, 4 method và 5 nhóm status đã có thể tạo nhiều tổ hợp tag. Nếu mỗi meter còn có hàng chục bucket, số series sẽ tăng theo tích của các chiều này và số bucket.

Để kiểm soát chi phí:

- Chọn nhóm meter cụ thể bằng tên và loại.
- Chỉ bật histogram cho các phép đo cần percentile tổng hợp hoặc SLO.
- Giới hạn `minimumExpectedValue` và `maximumExpectedValue` theo miền dữ liệu thực tế.
- Chọn số ngưỡng SLO vừa đủ để phân tích.
- Giữ tag có cardinality thấp; không dùng ID, email, URL thô hoặc trace ID.
- Tránh vừa bật client-side percentiles vừa bật histogram nếu backend không cần cả hai hoặc không hỗ trợ kết hợp.

Filter giúp tập trung cấu hình, nhưng không tự giảm cardinality. Quy mô dữ liệu vẫn phụ thuộc số meter khớp điều kiện, số tổ hợp tag và số bucket của từng meter.

## 10. Xác minh cấu hình qua Prometheus exposition

Sau khi cấu hình filter, hãy kiểm tra dữ liệu xuất thay vì chỉ nhìn code. Với Spring Boot Actuator và Prometheus registry, endpoint thường dùng là `/actuator/prometheus` nếu đã được expose và bảo vệ phù hợp.

Với classic histogram, có thể tìm các series dạng:

```text
# TYPE http_server_requests_seconds histogram
http_server_requests_seconds_bucket{le="0.1",...} ...
http_server_requests_seconds_bucket{le="0.3",...} ...
http_server_requests_seconds_bucket{le="1.0",...} ...
http_server_requests_seconds_bucket{le="+Inf",...} ...
http_server_requests_seconds_count{...} ...
http_server_requests_seconds_sum{...} ...
```

Đây là ví dụ minh họa tên đã chuẩn hóa; tên chính xác tùy phiên bản Micrometer và Prometheus registry. Đối với payload summary, tìm series có tên tương ứng và hậu tố `_bucket`, `_count`, `_sum`. Nếu chỉ có `_count` và `_sum`, histogram có thể chưa được bật hoặc registry không xuất bucket.

Có thể dùng PromQL để tính p95 cho HTTP request từ classic histogram:

```promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(http_server_requests_seconds_bucket[5m])
  )
)
```

Để giữ phân tách theo method hoặc route, thêm các label đó vào `sum by`, nhưng chỉ khi chúng có tập giá trị hữu hạn và hữu ích cho vận hành. Với SLO, có thể theo dõi tỷ lệ request nằm dưới một bucket cụ thể bằng cách chia rate của bucket tương ứng cho rate của `_count`.

## 11. Kiểm thử chính sách MeterFilter

Nên kiểm tra cả meter thuộc nhóm và meter ngoài nhóm. Một kịch bản tích hợp có thể đăng ký timer HTTP, timer nghiệp vụ và distribution summary, sau đó kiểm tra exposition:

| Meter được đăng ký | Kết quả mong đợi |
| --- | --- |
| `http.server.requests` loại `TIMER` | Có histogram và các SLO HTTP |
| `orders.create.duration` loại `TIMER` | Không nhận cấu hình HTTP nếu không khớp nhóm |
| `orders.payload.size` loại `DISTRIBUTION_SUMMARY` | Có histogram và SLO theo byte |
| `orders.payload.size` nếu không phải `DISTRIBUTION_SUMMARY` | Không nhận cấu hình payload |
| `orders.created` loại `COUNTER` | Không bị thay đổi bởi cấu hình phân phối |

Unit test với `SimpleMeterRegistry` hữu ích để kiểm tra meter vẫn ghi nhận count và giá trị cơ bản, nhưng không đủ để chứng minh Prometheus exporter đã tạo bucket đúng. Để xác minh histogram, hãy dùng registry Prometheus của phiên bản dự án trong test tích hợp hoặc kiểm tra endpoint exposition khi ứng dụng chạy.

Khi kiểm thử filter, nên tạo registry mới cho mỗi test để tránh meter đã đăng ký từ test trước làm sai kết quả. Đăng ký filter trước khi tạo meter và dùng đúng tên/tag/loại như instrumentation trong ứng dụng.

## 12. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân nên kiểm tra |
| --- | --- |
| Không thấy bucket dù filter đã khai báo | Điều kiện `Meter.Id` không khớp, filter đăng ký quá muộn hoặc registry không xuất histogram |
| SLO HTTP sai theo hệ số lớn | Truyền millisecond trực tiếp thay vì nanosecond cho cấu hình Timer |
| SLO payload sai đơn vị | Ghi payload theo byte nhưng cấu hình ngưỡng theo KiB hoặc ngược lại |
| Meter ngoài nhóm cũng có histogram | Prefix hoặc điều kiện loại meter quá rộng |
| Meter cùng tên vẫn dùng cấu hình cũ | Meter đã được đăng ký trước filter; đăng ký lặp không cập nhật cấu hình cũ |
| Số time series tăng mạnh | Histogram bật cho quá nhiều meter, quá nhiều bucket hoặc tag có cardinality cao |
| Cấu hình filter bị ghi đè | Nhiều filter cùng thay đổi các trường phân phối; cần thống nhất thứ tự và chính sách |
| Có `_count` và `_sum` nhưng thiếu `_bucket` | Histogram chưa được bật hoặc backend/exporter không hỗ trợ cấu hình yêu cầu |

Khi điều tra, hãy in hoặc kiểm tra `Meter.Id` thực tế của meter, xác minh filter có chạy cho ID đó, kiểm tra đơn vị của SLO, rồi đọc exposition. Truy vấn PromQL chỉ nên được chỉnh sau khi tên metric và label trong dữ liệu xuất đã được xác nhận.

## 13. Nguyên tắc áp dụng

Dùng `MeterFilter.configure(...)` để áp dụng chính sách thống kê phân phối nhất quán cho nhóm `Timer` hoặc `DistributionSummary`. Chọn nhóm dựa trên tên, loại meter và khi cần thì tag. Mỗi nhóm phải có cấu hình riêng phù hợp với đại lượng đo: Timer dùng đơn vị thời gian nội bộ nanosecond trong `DistributionStatisticConfig`, còn DistributionSummary dùng đơn vị số mà ứng dụng ghi nhận.

Đăng ký filter sớm, dùng `merge` để giữ các cấu hình hiện có chưa bị thay thế, tránh nhiều filter cùng sở hữu một chính sách và xác minh histogram ở endpoint export. Cuối cùng, chỉ bật bucket, percentile và SLO thực sự phục vụ câu hỏi vận hành; số lượng meter, tag và bucket quyết định chi phí quan sát mà hệ thống phải gánh.
