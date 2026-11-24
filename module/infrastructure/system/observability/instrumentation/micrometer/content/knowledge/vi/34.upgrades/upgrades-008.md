# Cập nhật kiểm thử hợp đồng dữ liệu và tài liệu phép đo sau thay đổi

Metrics là một giao diện dữ liệu giữa ứng dụng và những thành phần sử dụng dữ liệu đó: dashboard, alert, recording rule, SLO, báo cáo vận hành và hệ thống phân tích. Khi đổi tên meter, loại meter, đơn vị, tag hoặc bucket, code Java có thể vẫn chạy bình thường nhưng các truy vấn ở phía sau có thể sai hoặc mất dữ liệu. Vì vậy, một thay đổi instrumentation cần cập nhật cả kiểm thử hợp đồng metrics và tài liệu phép đo.

Hợp đồng metrics mô tả ý nghĩa và hình dạng dữ liệu mà ứng dụng cam kết xuất ra. Hợp đồng không chỉ là tên metric. Nó còn bao gồm loại meter, đơn vị, ý nghĩa của một lần tăng/ghi nhận, tag key và miền giá trị, cardinality dự kiến, cách tổng hợp, phân phối histogram và thời điểm ghi nhận. Các thuộc tính này cần được kiểm thử ở mức phù hợp và được ghi lại trong catalog để người vận hành hiểu đúng dữ liệu.

Trong module `OBSERVABILITY_INSTRUMENTATION_MICROMETER`, việc quản lý hợp đồng giúp thay đổi instrumentation có thể review và triển khai an toàn. Một thay đổi đo lường chỉ hoàn tất khi code, contract test, dashboard/alert và tài liệu phép đo cùng phản ánh một semantics thống nhất.

## 1. Vì sao metrics cần hợp đồng?

Giả sử ứng dụng đang xuất:

```text
business.order.results{outcome="success"}
business.order.processing.duration
```

Dashboard dùng `business.order.results` để tính tỷ lệ đơn hàng thành công. Alert dùng `business.order.processing.duration` để theo dõi p95 dưới 500 ms. Một thay đổi tưởng nhỏ có thể phá vỡ hai consumer này:

- Đổi `outcome=success` thành `result=ok`: truy vấn cũ không còn khớp tag.
- Đổi Counter thành Gauge: truy vấn `rate()` không còn mang cùng ý nghĩa.
- Đổi đơn vị duration từ milliseconds sang seconds nhưng giữ nguyên tên: dashboard có thể sai hệ số 1000.
- Bỏ percentile histogram: truy vấn `histogram_quantile()` không còn bucket để tính.
- Thêm `customerId` vào tag: số time series có thể tăng theo số khách hàng.
- Chuyển điểm ghi nhận từ mỗi lần thử sang một kết quả cuối cùng: count thay đổi semantics dù tên metric không đổi.

Hợp đồng giúp reviewer phát hiện các thay đổi như vậy trước khi triển khai. Nó cũng cho phép nhóm vận hành biết metric nào có thể dùng cho throughput, tỷ lệ lỗi, latency hoặc SLO.

## 2. Những phần tạo nên metrics contract

Với mỗi meter quan trọng, ghi rõ các thuộc tính sau:

| Thành phần | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| Name | Tên ổn định của meter là gì? | `business.order.results` |
| Type | Counter, Gauge, Timer, DistributionSummary hay LongTaskTimer? | Counter |
| Unit | Giá trị có đơn vị gì? | `orders`, `seconds`, `bytes` |
| Description | Meter mô tả điều gì? | Số kết quả cuối cùng của command đặt hàng |
| Semantics | Một lần tăng/record đại diện cho sự kiện nào? | Một logical command có outcome cuối cùng |
| Tag keys | Các chiều phân loại nào được xuất? | `outcome` |
| Tag values | Mỗi key có vocabulary nào? | `success`, `rejected`, `timeout`, `error` |
| Cardinality | Số giá trị và tổ hợp series dự kiến? | 4 outcome |
| Distribution | Có percentile, histogram hay SLO buckets? | Buckets 100 ms, 300 ms, 1 s |
| Lifecycle | Meter được cập nhật ở thời điểm nào? | Một lần khi command hoàn tất |
| Consumers | Dashboard, alert, SLO hoặc team nào sử dụng? | Order success rate, latency SLO |
| Owner | Ai chịu trách nhiệm khi contract thay đổi? | Order Platform team |

Không phải mọi meter đều cần tài liệu dài như nhau. Các meter được dùng trong alert, SLO hoặc báo cáo cấp dịch vụ cần contract rõ ràng hơn meter debug tạm thời.

## 3. Phân biệt thay đổi implementation và thay đổi contract

Một số thay đổi không ảnh hưởng đến dữ liệu được xuất; số khác là thay đổi contract và cần kế hoạch tương thích.

| Thay đổi | Có thể là breaking change? | Vì sao? |
| --- | --- | --- |
| Refactor class ghi meter nhưng giữ nguyên name/type/tags/semantics | Thường không | Consumer vẫn đọc cùng dữ liệu |
| Đổi tên metric | Có | Dashboard và alert tham chiếu tên cũ |
| Đổi Counter thành Gauge hoặc Timer | Có | Kiểu dữ liệu và phép truy vấn thay đổi |
| Đổi unit hoặc scale giá trị | Có | So sánh và ngưỡng cảnh báo không còn đúng |
| Đổi tag key hoặc vocabulary | Có | Series identity và filter thay đổi |
| Thêm tag có cardinality lớn | Có, kể cả khi query cũ vẫn chạy | Chi phí và số series tăng mạnh |
| Thêm một tag key bắt buộc cho mọi series | Có thể | Schema series và truy vấn downstream thay đổi |
| Thay đổi bucket/SLO boundaries | Có thể | Quantile hoặc SLO query có thể thay đổi độ chính xác |
| Đổi thời điểm record hoặc semantics count | Có | Số đo không còn đại diện cùng sự kiện |
| Chỉ đổi description | Thường không | Ý nghĩa máy đọc không đổi, nhưng tài liệu vẫn cần cập nhật |

Một metric name nên giữ một semantics ổn định trong suốt thời gian tồn tại. Không tái sử dụng tên cũ cho một phép đo khác chỉ vì tên đó đã có trong dashboard.

## 4. Viết contract test cho meter name, type và unit

Unit test có thể dùng `SimpleMeterRegistry` để xác nhận instrumentation tạo đúng meter. Registry trong test nên độc lập, tránh phụ thuộc meter tự động của Spring Boot hoặc backend bên ngoài.

Ví dụ service ghi số kết quả và thời lượng xử lý:

```java
import java.time.Duration;
import java.util.concurrent.TimeUnit;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

enum OrderOutcome {
    SUCCESS("success"),
    REJECTED("rejected"),
    TIMEOUT("timeout"),
    ERROR("error");

    private final String tagValue;

    OrderOutcome(String tagValue) {
        this.tagValue = tagValue;
    }

    String tagValue() {
        return tagValue;
    }
}

public final class OrderMetrics {
    private final Counter accepted;
    private final MeterRegistry registry;

    public OrderMetrics(MeterRegistry registry) {
        this.registry = registry;
        this.accepted = Counter.builder("business.order.commands.accepted")
                .description("Number of newly accepted order commands")
                .baseUnit("orders")
                .register(registry);
    }

    public void recordAccepted() {
        accepted.increment();
    }

    public void recordResult(OrderOutcome outcome) {
        registry.counter("business.order.results", "outcome", outcome.tagValue()).increment();
    }

    public void recordDuration(long amount, TimeUnit unit, OrderOutcome outcome) {
        Timer.builder("business.order.processing.duration")
                .description("Time spent processing one logical order command")
                .tag("outcome", outcome.tagValue())
                .publishPercentileHistogram()
                .serviceLevelObjectives(
                        Duration.ofMillis(100),
                        Duration.ofMillis(300),
                        Duration.ofSeconds(1))
                .register(registry)
                .record(amount, unit);
    }
}
```

Contract test xác nhận tên, type, base unit, tag key và dữ liệu:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.concurrent.TimeUnit;

import io.micrometer.core.instrument.Meter;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

class OrderMetricsContractTest {
    @Test
    void exposesExpectedOrderMetricContract() {
        try (SimpleMeterRegistry registry = new SimpleMeterRegistry()) {
            OrderMetrics metrics = new OrderMetrics(registry);
            metrics.recordAccepted();
            metrics.recordResult(OrderOutcome.SUCCESS);
            metrics.recordDuration(120, TimeUnit.MILLISECONDS, OrderOutcome.SUCCESS);

            assertThat(registry.find("business.order.commands.accepted").counter())
                    .isNotNull();
            assertThat(registry.find("business.order.commands.accepted")
                    .counter().getId().getType()).isEqualTo(Meter.Type.COUNTER);
            assertThat(registry.find("business.order.commands.accepted")
                    .counter().getId().getBaseUnit()).isEqualTo("orders");
            assertThat(registry.find("business.order.commands.accepted")
                    .counter().count()).isEqualTo(1.0);

            Meter result = registry.find("business.order.results")
                    .tag("outcome", "success")
                    .meter();
            assertThat(result).isNotNull();
            assertThat(result.getId().getType()).isEqualTo(Meter.Type.COUNTER);

            var timer = registry.find("business.order.processing.duration")
                    .tag("outcome", "success")
                    .timer();
            assertThat(timer).isNotNull();
            assertThat(timer.getId().getType()).isEqualTo(Meter.Type.TIMER);
            assertThat(timer.getId().getBaseUnit()).isEqualTo("seconds");
            assertThat(timer.count()).isEqualTo(1L);
            assertThat(timer.totalTime(TimeUnit.MILLISECONDS)).isEqualTo(120.0);
            assertThat(timer.getId().getTags())
                    .extracting(tag -> tag.getKey())
                    .containsExactly("outcome");
        }
    }
}
```

Ví dụ dùng `var` để giữ code test gọn; nếu dự án chưa dùng Java hỗ trợ local variable type inference, khai báo `Timer` tường minh. `Timer` xuất thời gian theo base unit mà registry hỗ trợ; trong contract của ứng dụng, ghi rõ đơn vị chuẩn là giây và dùng `TimeUnit` khi record.

Không chỉ kiểm tra meter tồn tại. Hãy kiểm tra `Meter.Type`, base unit, tag key và phép đo thực tế. Nếu một metric name vô tình đổi từ Timer sang Gauge, test chỉ kiểm tra tên sẽ không phát hiện semantics đã thay đổi.

## 5. Kiểm thử vocabulary và cardinality của tag

Tag value là một phần của contract. Một tag `outcome` nên có miền giá trị hữu hạn được tài liệu hóa, ví dụ `success`, `rejected`, `error`. Không để exception message, user ID hoặc input tự do trở thành tag value.

Ví dụ kiểm tra tập outcome sau khi thực thi các trường hợp:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.Set;
import java.util.stream.Collectors;

import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

class OrderOutcomeTagContractTest {
    @Test
    void usesOnlyDocumentedOutcomeValues() {
        try (SimpleMeterRegistry registry = new SimpleMeterRegistry()) {
            OrderMetrics metrics = new OrderMetrics(registry);
            metrics.recordResult(OrderOutcome.SUCCESS);
            metrics.recordResult(OrderOutcome.REJECTED);
            metrics.recordResult(OrderOutcome.TIMEOUT);
            metrics.recordResult(OrderOutcome.ERROR);

            Set<String> outcomes = registry.getMeters().stream()
                    .filter(meter -> meter.getId().getName()
                            .equals("business.order.results"))
                    .map(meter -> meter.getId().getTag("outcome"))
                    .collect(Collectors.toSet());

            assertThat(outcomes)
                    .containsExactlyInAnyOrder("success", "rejected", "timeout", "error");
            assertThat(outcomes).hasSizeLessThanOrEqualTo(4);
        }
    }
}
```

Test chỉ thấy các giá trị đã được kích hoạt trong kịch bản. Nếu cần kiểm tra toàn bộ vocabulary, phải chạy đủ nhánh nghiệp vụ hoặc kiểm tra hằng số/enum dùng để ánh xạ tag. Không thể suy ra giá trị chưa từng được phát ra chỉ từ registry rỗng.

Có thể đặt giới hạn phòng vệ bằng `MeterFilter.maximumAllowableTags(...)`, nhưng filter không thay thế thiết kế vocabulary. Khi đạt giới hạn, meter mới có thể bị từ chối và dữ liệu mất; contract test nên phát hiện trường hợp đó trước production.

Ví dụ giới hạn số giá trị tag `outcome`:

```java
import io.micrometer.core.instrument.config.MeterFilter;

registry.config().meterFilter(MeterFilter.maximumAllowableTags(
        "business.order.results",
        "outcome",
        4,
        MeterFilter.deny()));
```

Hãy kiểm tra API của phiên bản Micrometer đang dùng và đặt filter trước khi meter được đăng ký. Nếu tag có cardinality cao như `customerId`, giới hạn 1000 giá trị vẫn có thể quá lớn; cách đúng là bỏ dimension đó khỏi metrics hoặc chuyển chi tiết sang log/trace.

## 6. Kiểm thử histogram và SLO bucket ở tầng registry

Unit test với `SimpleMeterRegistry` không xác nhận được định dạng Prometheus bucket. Khi contract có percentile histogram, hãy kiểm tra raw exposition bằng `PrometheusMeterRegistry`:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;
import java.util.concurrent.TimeUnit;

import io.micrometer.core.instrument.Timer;
import io.micrometer.prometheusmetrics.PrometheusConfig;
import io.micrometer.prometheusmetrics.PrometheusMeterRegistry;
import org.junit.jupiter.api.Test;

class OrderLatencyHistogramContractTest {
    @Test
    void exportsDocumentedSloBuckets() {
        try (PrometheusMeterRegistry registry =
                new PrometheusMeterRegistry(PrometheusConfig.DEFAULT)) {
            Timer timer = Timer.builder("business.order.processing.duration")
                    .publishPercentileHistogram()
                    .serviceLevelObjectives(
                            Duration.ofMillis(100),
                            Duration.ofMillis(300),
                            Duration.ofSeconds(1))
                    .register(registry);

            timer.record(80, TimeUnit.MILLISECONDS);
            timer.record(250, TimeUnit.MILLISECONDS);
            timer.record(700, TimeUnit.MILLISECONDS);

            String exposition = registry.scrape();
            assertThat(exposition)
                    .contains("business_order_processing_duration_seconds_bucket")
                    .contains("le=\"0.1\"")
                    .contains("le=\"0.3\"")
                    .contains("le=\"1.0\"")
                    .contains("business_order_processing_duration_seconds_count");
        }
    }
}
```

Package `io.micrometer.prometheusmetrics` thuộc adapter Prometheus Java Client 1.x. Nếu dự án dùng adapter legacy, thay package và kiểu registry theo dependency thực tế. Contract test cần cố định các ngưỡng SLO mà dashboard/alert phụ thuộc; không nhất thiết khóa toàn bộ bucket tự động do Micrometer sinh ra vì chúng có thể thay đổi theo phiên bản hoặc cấu hình miền.

Nếu thay đổi SLO từ 300 ms sang 500 ms, cập nhật test bucket, measurement catalog, PromQL, dashboard và alert trong cùng thay đổi. Một test chỉ xác nhận có `_bucket` sẽ không phát hiện ngưỡng quan trọng đã bị xóa.

## 7. Chọn đúng tầng kiểm thử

Không nên dùng một test duy nhất để xác minh toàn bộ pipeline. Chia kiểm thử theo trách nhiệm:

| Tầng test | Thành phần | Điều cần xác minh |
| --- | --- | --- |
| Unit/contract test | `SimpleMeterRegistry` | Name, type, base unit, description, tag keys/values, count và total time |
| Distribution test | Registry tương ứng | Percentile, histogram config, SLO boundaries và expected value range |
| Exposition test | `PrometheusMeterRegistry.scrape()` hoặc output registry đích | Tên sau chuẩn hóa, unit, bucket, label và metric family |
| Spring integration test | Application context và Actuator endpoint | Properties, auto-configuration, customizer, filter và endpoint export |
| Dashboard/query test | Recording rule hoặc query validation | Query vẫn trả dữ liệu đúng semantics và đơn vị |
| Operational test | Backend/collector thử nghiệm | Scrape, ingest, retention, alert và quyền truy cập |

Unit test nên nhanh và không cần backend. Integration test kiểm tra adapter và Spring wiring. Test dashboard/alert có thể dùng fixture exposition hoặc môi trường staging. Không cần chạy toàn bộ backend trong mọi lần chạy unit test.

## 8. Hợp đồng phải kiểm tra semantics, không chỉ hình dạng

Hai meter có cùng name/type/tag vẫn có thể mang semantics khác nhau. Ví dụ, `business.order.results` trước đây tăng một lần cho mỗi logical command hoàn tất; sau refactor nó tăng một lần cho mỗi dependency attempt. Hình dạng meter không đổi nhưng count không còn trả lời cùng câu hỏi.

Hãy ghi semantics rõ ràng:

| Thuộc tính | Mô tả cần ghi |
| --- | --- |
| Start boundary | Thời điểm nào được xem là command mới được chấp nhận? |
| Record boundary | Counter tăng ở mỗi delivery, mỗi attempt hay mỗi logical command? |
| Completion boundary | Timer dừng khi method trả về, transaction commit hay workflow kết thúc? |
| Failure semantics | Exception nào được xem là `error`, `rejected` hay `timeout`? |
| Retry semantics | Retry có làm tăng business counter hay chỉ dependency counter? |
| Async semantics | Timer kết thúc khi tạo Future hay khi CompletionStage hoàn tất? |
| Deduplication | Request/message redelivery có được tính lại không? |

Nếu semantics thay đổi, cần đổi tên metric hoặc cung cấp metric mới trong giai đoạn chuyển tiếp. Không giữ nguyên tên chỉ vì code vẫn dùng cùng một builder.

## 9. Tài liệu phép đo nên là catalog có cấu trúc

Một catalog metrics giúp developer, SRE và nhóm phân tích cùng hiểu dữ liệu. Có thể lưu trong tài liệu module hoặc hệ thống tài liệu nội bộ, miễn là có owner và quy trình cập nhật.

Ví dụ một mục catalog:

```yaml
name: business.order.processing.duration
type: timer
unit: seconds
description: Time spent processing one logical order command
semantics:
  record_boundary: one completed logical command
  includes_retry_backoff: true
tags:
  outcome:
    values: [success, rejected, timeout, error]
cardinality:
  max_series_per_instance: 4
distribution:
  histogram: true
  slo_buckets: [100ms, 300ms, 1s]
consumers:
  - order-processing-dashboard
  - order-latency-slo
owner: order-platform
```

Đây là cấu trúc minh họa cho measurement catalog, không phải định dạng cấu hình Micrometer tự đọc. Không copy nội dung này vào `application.yml` rồi kỳ vọng Spring Boot tự tạo meter. Catalog mô tả contract để người review và công cụ kiểm tra sử dụng.

Một mục catalog nên trả lời tối thiểu:

- Metric đại diện cho sự kiện hoặc đại lượng nào?
- Đơn vị chuẩn và kiểu meter là gì?
- Tag nào được phép, miền giá trị và cardinality dự kiến ra sao?
- Histogram/percentile/SLO boundary nào được cấu hình?
- Metric được ghi ở ranh giới nào và có tính retry hay không?
- Consumer nào phụ thuộc và ai sở hữu contract?
- Khi metric thay đổi, dashboard/alert/runbook nào phải cập nhật?

## 10. Cập nhật tài liệu khi code thay đổi

Mỗi thay đổi instrumentation cần cập nhật các tài liệu có liên quan:

| Artifact | Khi nào phải cập nhật? | Nội dung cần sửa |
| --- | --- | --- |
| Metrics catalog | Name/type/unit/tag/semantics/distribution thay đổi | Định nghĩa contract mới và trạng thái deprecated |
| Code comments/Javadoc | API instrumentation hoặc ý nghĩa method thay đổi | Ranh giới record và mục đích đo |
| Dashboard | Name, tag hoặc query thay đổi | Panel, legend, filter, đơn vị và grouping |
| Alert/recording rule | Metric hoặc threshold thay đổi | Query, cửa sổ, ngưỡng và no-data behavior |
| SLO document | Latency boundary hoặc denominator thay đổi | Target, bucket và cách tính compliance |
| Runbook | Metric/alert mới hoặc sự cố thay đổi | Cách đọc tín hiệu và bước điều tra |
| Release note | Có breaking change hoặc migration | Tác động, thời gian dual-publish và ngày xóa metric cũ |

Đừng chỉ cập nhật code và cho rằng dashboard sẽ tự thích ứng. Các consumer thường được quản lý ở repository hoặc nền tảng khác, do đó PR cần liệt kê rõ các thay đổi phối hợp và người chịu trách nhiệm.

## 11. Migration khi đổi tên, tag, unit hoặc semantics

Metrics không có cơ chế versioning tự động cho consumer. Khi một contract đã được dashboard hoặc alert sử dụng, hãy thay đổi theo quy trình tương thích:

1. **Inventory:** tìm tất cả dashboard, alert, recording rule, SLO và báo cáo đang dùng metric cũ.
2. **Classify:** xác định thay đổi chỉ là implementation hay làm thay đổi semantics/schema.
3. **Define new contract:** nếu name/type/unit/semantics thay đổi, định nghĩa metric mới với tên và tài liệu rõ ràng.
4. **Dual-publish:** trong thời gian chuyển tiếp, ghi cả metric cũ và mới nếu chi phí cho phép và hai phép đo có semantics tương đương hoặc được giải thích rõ.
5. **Migrate consumers:** cập nhật query, dashboard, alert, runbook và tài liệu.
6. **Compare:** so sánh hai metric trong staging/production để phát hiện khác biệt không dự kiến.
7. **Deprecate:** thông báo metric cũ sẽ bị loại bỏ, ghi ngày dự kiến và owner.
8. **Remove:** chỉ xóa metric cũ khi consumer đã chuyển và thời gian tương thích kết thúc.

Không dual-publish cùng một metric name với hai đơn vị hoặc hai semantics khác nhau. Nếu metric mới là cùng dữ liệu nhưng cách đặt tên khác, có thể ghi hai tên trong giai đoạn chuyển tiếp. Nếu semantics khác, phải mô tả rõ hai metric và không giả vờ chúng tương đương.

Với thay đổi tag key, dual-publish có thể cần tạo meter cũ và meter mới hoặc duy trì cả hai tag schema tạm thời. Hãy kiểm tra cardinality và tránh tạo hai chiều tag không cần thiết. Với thay đổi bucket, giữ các ngưỡng cũ trong giai đoạn chuyển tiếp nếu dashboard/alert cũ còn phụ thuộc; bucket mới không làm dữ liệu lịch sử được tái tạo.

## 12. Kiểm tra contract trong CI

Một pipeline CI có thể kiểm tra theo thứ tự:

1. Chạy unit tests cho instrumentation và contract của meter.
2. Chạy tests kiểm tra tag vocabulary/cardinality.
3. Chạy exposition tests cho registry được hỗ trợ chính thức.
4. Chạy Spring integration test cho properties và endpoint nếu thay đổi auto-configuration.
5. Kiểm tra catalog được cập nhật khi contract snapshot thay đổi.
6. Kiểm tra dashboard/alert fixtures hoặc query lint nếu repository quản lý chúng.
7. Yêu cầu review từ owner khi có breaking change.

Không nên tạo snapshot exposition quá lớn và khóa mọi chi tiết implementation. Snapshot dễ vỡ khi registry thêm metadata hoặc đổi formatting. Ưu tiên assertion vào các phần contract quan trọng: metric family name, type, unit, tag keys, vocabulary và SLO boundaries.

Nếu dùng snapshot test, chuẩn hóa thứ tự series và loại bỏ timestamp hoặc metadata không ổn định. Khi snapshot thay đổi, reviewer cần xem diff và xác nhận đó là thay đổi contract có chủ đích.

## 13. Checklist review cho một thay đổi metrics

Trước khi merge một thay đổi instrumentation, reviewer có thể kiểm tra:

- [ ] Tên metric phản ánh đúng đại lượng và ổn định.
- [ ] Meter type phù hợp với semantics.
- [ ] Unit được khai báo và nhất quán từ code đến dashboard.
- [ ] Description giải thích đúng một observation đại diện cho điều gì.
- [ ] Tag keys ổn định; tag values thuộc vocabulary hữu hạn.
- [ ] Không có ID hoặc dữ liệu tự do trong metric tags.
- [ ] Cardinality dự kiến và số series được đánh giá.
- [ ] Percentile/histogram/SLO buckets được cấu hình có chủ đích.
- [ ] Contract test kiểm tra name, type, unit, tags và dữ liệu.
- [ ] Exposition test xác nhận format mà backend nhận thực sự sử dụng.
- [ ] Dashboard, alert, SLO, recording rule và runbook được cập nhật.
- [ ] Breaking change có migration plan, owner và thời gian deprecation.
- [ ] Có cách so sánh dữ liệu trước/sau khi triển khai.

## 14. Các lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Chỉ test meter có tồn tại | Không phát hiện đổi type, unit hoặc tag | Kiểm tra toàn bộ contract quan trọng |
| Đổi tên metric mà không tìm consumer | Dashboard/alert mất dữ liệu | Inventory consumer và migration có thời hạn |
| Giữ tên nhưng đổi semantics | Query vẫn chạy nhưng kết quả sai ý nghĩa | Tạo metric mới hoặc version hóa tên theo quy ước |
| Thêm tag động | Cardinality và chi phí tăng | Dùng vocabulary hữu hạn hoặc chuyển chi tiết sang trace/log |
| Thay SLO bucket nhưng không sửa query | Tỷ lệ compliance sai hoặc không có dữ liệu | Đồng bộ config, exposition test và PromQL |
| Chỉ test SimpleMeterRegistry cho Prometheus histogram | Không phát hiện adapter không xuất bucket như kỳ vọng | Thêm Prometheus exposition test |
| Khóa toàn bộ raw exposition bằng snapshot | Test vỡ do metadata/format không liên quan | Assert các trường contract quan trọng |
| Tài liệu ghi milliseconds nhưng Timer xuất seconds | Dashboard sai scale | Ghi rõ unit chuẩn và kiểm tra conversion |
| Dual-publish metric có semantics khác nhau nhưng không chú thích | Người dùng so sánh hai số không tương đương | Tách contract và giải thích khác biệt |
| Xóa metric cũ ngay khi code mới merge | Consumer chưa kịp migrate | Dùng giai đoạn deprecation và theo dõi usage |

## 15. Quy trình cập nhật contract và measurement documentation

Khi thay đổi instrumentation, hãy thực hiện theo trình tự:

1. Xác định meter và consumer đang bị ảnh hưởng.
2. Ghi lại contract hiện tại: name, type, unit, semantics, tags, cardinality và distribution.
3. Phân loại thay đổi có tương thích hay phá vỡ contract.
4. Cập nhật instrumentation và bổ sung contract test cho schema mới.
5. Kiểm tra raw exposition bằng registry adapter phù hợp.
6. Cập nhật measurement catalog, dashboard, alert, SLO và runbook.
7. Nếu breaking, triển khai dual-publish/deprecation theo kế hoạch.
8. Chạy CI và review diff contract cùng owner.
9. Sau rollout, so sánh metric cũ/mới và kiểm tra consumer thực tế.
10. Gỡ metric cũ sau khi hết thời gian tương thích và xác nhận không còn consumer.

Kiểm thử hợp đồng metrics bảo vệ ý nghĩa dữ liệu khi code thay đổi. Tài liệu phép đo giúp các consumer hiểu và sử dụng dữ liệu đúng cách. Khi hai phần được cập nhật cùng instrumentation, thay đổi Micrometer có thể được triển khai có kiểm soát mà không làm dashboard, alert hoặc SLO âm thầm sai lệch.

## Tài liệu tham khảo

- [Micrometer: Meter Registry](https://docs.micrometer.io/micrometer/reference/concepts/registry.html)
- [Micrometer: Meters and Meter Types](https://docs.micrometer.io/micrometer/reference/concepts/meters.html)
- [Micrometer: Meter Filters](https://docs.micrometer.io/micrometer/reference/concepts/meter-filters.html)
- [Micrometer: Histograms and Percentiles](https://docs.micrometer.io/micrometer/reference/concepts/histogram-quantiles.html)
- [Prometheus: Metric and label naming](https://prometheus.io/docs/practices/naming/)
- [Prometheus: Histograms and summaries](https://prometheus.io/docs/practices/histograms/)
