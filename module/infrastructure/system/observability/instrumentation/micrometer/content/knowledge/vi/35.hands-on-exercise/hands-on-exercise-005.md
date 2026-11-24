# Bật histogram có ngưỡng dịch vụ và kiểm chứng trên dữ liệu mô phỏng

Trong bài thực hành này, bạn sẽ instrument thời gian xử lý thanh toán bằng Micrometer Timer, bật histogram có các ngưỡng dịch vụ cụ thể và kiểm tra kết quả trên một tập độ trễ mô phỏng. Mục tiêu là đi từ cấu hình bucket đến dữ liệu có thể truy vấn: biết bao nhiêu request hoàn tất trong 100 ms, 300 ms, 500 ms và 1 giây; tính tỷ lệ đáp ứng mục tiêu; sau đó xác minh bucket được xuất qua Prometheus.

Một histogram có hai vai trò cần phân biệt. Các bucket SLO là ranh giới thời gian mà đội vận hành muốn theo dõi rõ ràng. Percentile histogram tạo thêm bucket phù hợp để backend như Prometheus tính percentile có thể tổng hợp giữa nhiều instance. Cả hai giúp trả lời câu hỏi về phân phối độ trễ, nhưng chúng không tự tạo cảnh báo hoặc tự quyết định dịch vụ đạt SLO.

Bài thuộc module **OBSERVABILITY_INSTRUMENTATION_MICROMETER**. Bạn sẽ thực hành Timer, histogram, service-level objective boundaries, dữ liệu mô phỏng, Prometheus exposition và truy vấn tỷ lệ request đáp ứng ngưỡng.

## 1. Mục tiêu và tình huống thực hành

Giả sử một dịch vụ thanh toán có endpoint:

~~~text
POST /payments/{id}/authorize
~~~

Đội vận hành muốn theo dõi thời gian authorize và đánh giá mục tiêu:

**Ít nhất 95% request phải hoàn tất trong 300 ms.**

Để điều tra phân phối, ta chọn các ranh giới histogram:

| Ranh giới | Ý nghĩa |
|---:|---|
| 100 ms | Rất nhanh |
| 300 ms | Ngưỡng SLO cần đánh giá |
| 500 ms | Chậm hơn mục tiêu |
| 1.000 ms | Chậm rõ rệt |

Tập dữ liệu mô phỏng gồm 10 request:

~~~text
45, 80, 120, 180, 240, 260, 280, 310, 420, 900 ms
~~~

Sau bài thực hành, bạn cần làm được các việc sau:

- Tạo Timer có tên và tag ổn định.
- Cấu hình explicit SLO buckets.
- Bật percentile histogram để backend có thể tính percentile tổng hợp.
- Ghi một tập dữ liệu mô phỏng có thể lặp lại.
- Kiểm tra count, total time và max bằng SimpleMeterRegistry.
- Kiểm tra các bucket được xuất qua Prometheus.
- Tính tỷ lệ request hoàn tất trong 300 ms và đánh giá mục tiêu 95%.
- Giải thích vì sao bucket boundaries không đồng nghĩa với alert hay SLO policy tự động.

## 2. Phân biệt các cấu hình phân phối

Micrometer Timer hỗ trợ nhiều cách công bố thống kê:

| Cấu hình | Tác dụng | Có thể tổng hợp giữa instance? |
|---|---|---|
| serviceLevelObjectives(...) | Thêm bucket tại các ranh giới do đội vận hành chọn | Có, với backend hỗ trợ histogram |
| publishPercentileHistogram() | Xuất bucket được Micrometer tạo để backend tính percentile | Có, với backend hỗ trợ |
| publishPercentiles(0.95) | Tính percentile trong ứng dụng và xuất giá trị đó | Không nên cộng/gộp percentile giữa instance |
| minimumExpectedValue / maximumExpectedValue | Giới hạn khoảng bucket tự động và phạm vi thống kê | Không phải SLO; là giới hạn phân phối |

Trong bài này, ta kết hợp serviceLevelObjectives và publishPercentileHistogram:

- SLO boundaries tạo bucket đúng tại 100 ms, 300 ms, 500 ms và 1 giây.
- Percentile histogram thêm các bucket tự động để truy vấn percentile linh hoạt hơn.
- Minimum/maximum expected value giới hạn phạm vi histogram tự động, giúp kiểm soát số bucket và bộ nhớ.

Khi dùng Prometheus, histogram có thể được tổng hợp giữa nhiều instance bằng cách cộng các bucket tương ứng rồi tính percentile bằng histogram_quantile. Percentile tính riêng trong từng instance không có tính chất này. [Micrometer: Histograms and Percentiles](https://docs.micrometer.io/micrometer/reference/concepts/histogram-quantiles.html).

## 3. Chuẩn bị dependency và endpoint Prometheus

Nếu dùng Spring Boot với Maven, cần Actuator và registry Prometheus tương thích với phiên bản Spring Boot của dự án:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-registry-prometheus</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Ví dụ endpoint và MockMvc trong bài giả định ứng dụng Spring MVC. Nếu dự án dùng WebFlux, dùng web starter và test client tương ứng của WebFlux.

Để expose endpoint scrape, thêm cấu hình:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,prometheus
~~~

Cấu hình exposure chỉ đưa endpoint vào web layer. Nếu ứng dụng có Spring Security hoặc chạy trong môi trường mạng được bảo vệ, hãy cho phép Prometheus scraper truy cập bằng cơ chế xác thực và network policy phù hợp.

Phiên bản Micrometer nên được quản lý bởi Spring Boot dependency management/BOM tương thích. Không ép riêng một phiên bản Micrometer mới hơn hoặc cũ hơn mà chưa kiểm tra tương thích.

## 4. Tạo Timer với SLO boundaries

Tạo component giữ một Timer cho route authorize. Tag route dùng route template và method có tập giá trị hữu hạn:

~~~java
import java.time.Duration;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Component;

@Component
public class PaymentAuthorizationMetrics {

    public static final String TIMER_NAME =
            "payment.authorization.duration";

    private final Timer authorizationTimer;

    public PaymentAuthorizationMetrics(MeterRegistry registry) {
        this.authorizationTimer = Timer.builder(TIMER_NAME)
                .description("Time spent authorizing a payment")
                .tags(
                        "route", "/payments/{id}/authorize",
                        "method", "POST"
                )
                .publishPercentileHistogram()
                .serviceLevelObjectives(
                        Duration.ofMillis(100),
                        Duration.ofMillis(300),
                        Duration.ofMillis(500),
                        Duration.ofSeconds(1)
                )
                .minimumExpectedValue(Duration.ofMillis(1))
                .maximumExpectedValue(Duration.ofSeconds(5))
                .register(registry);
    }

    public void record(Duration elapsed) {
        authorizationTimer.record(elapsed);
    }
}
~~~

Một số điểm cần chú ý:

- Timer được đăng ký một lần khi component khởi tạo và được tái sử dụng.
- route là route template, không chứa payment ID.
- Không thêm customerId, requestId hoặc transactionId vào tag.
- serviceLevelObjectives nhận Duration, nên đơn vị trong code rõ ràng.
- minimumExpectedValue và maximumExpectedValue giới hạn histogram tự động; chúng không loại bỏ các SLO boundary đã khai báo.
- publishPercentileHistogram phù hợp khi backend có thể tính percentile từ bucket, ví dụ Prometheus.

Nếu chỉ cần các bucket SLO cố định và không cần percentile histogram tự động, có thể bỏ publishPercentileHistogram. Các ranh giới được khai báo bằng serviceLevelObjectives vẫn là cấu hình bucket tường minh cho registry hỗ trợ histogram. Khi bật cả hai, SLO boundaries được thêm bên cạnh các bucket tự động.

## 5. Ghi dữ liệu mô phỏng

Tạo một runner để ghi tập độ trễ cố định khi ứng dụng khởi động:

~~~java
import java.time.Duration;
import java.util.List;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public class PaymentLatencySimulation implements ApplicationRunner {

    private final PaymentAuthorizationMetrics metrics;

    private static final List<Duration> SAMPLES = List.of(
            Duration.ofMillis(45),
            Duration.ofMillis(80),
            Duration.ofMillis(120),
            Duration.ofMillis(180),
            Duration.ofMillis(240),
            Duration.ofMillis(260),
            Duration.ofMillis(280),
            Duration.ofMillis(310),
            Duration.ofMillis(420),
            Duration.ofMillis(900)
    );

    public PaymentLatencySimulation(
            PaymentAuthorizationMetrics metrics) {
        this.metrics = metrics;
    }

    @Override
    public void run(ApplicationArguments args) {
        SAMPLES.forEach(metrics::record);
    }
}
~~~

Runner chỉ phục vụ bài thực hành. Trong hệ thống thật, gọi metrics.record(elapsed) tại nơi đo thời gian xử lý request, hoặc dùng Timer.Sample/Observation để đo trực tiếp lifecycle của thao tác.

Không dùng dữ liệu mô phỏng để kết luận hiệu năng production. Nó chỉ giúp xác minh cấu hình bucket và cách diễn giải số liệu một cách xác định.

## 6. Kiểm tra Timer bằng SimpleMeterRegistry

Trước khi kiểm tra endpoint, hãy xác nhận instrumentation ghi đúng số mẫu. SimpleMeterRegistry phù hợp với unit test vì không cần Prometheus server.

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;
import java.util.List;
import java.util.concurrent.TimeUnit;

import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

class PaymentAuthorizationMetricsTest {

    @Test
    void recordsSimulatedDurations() {
        try (SimpleMeterRegistry registry = new SimpleMeterRegistry()) {
            Timer timer = Timer.builder(
                    "payment.authorization.duration"
            )
            .tags(
                    "route", "/payments/{id}/authorize",
                    "method", "POST"
            )
            .publishPercentileHistogram()
            .serviceLevelObjectives(
                    Duration.ofMillis(100),
                    Duration.ofMillis(300),
                    Duration.ofMillis(500),
                    Duration.ofSeconds(1)
            )
            .minimumExpectedValue(Duration.ofMillis(1))
            .maximumExpectedValue(Duration.ofSeconds(5))
            .register(registry);

            List.of(45L, 80L, 120L, 180L, 240L,
                    260L, 280L, 310L, 420L, 900L)
                    .forEach(ms -> timer.record(
                            Duration.ofMillis(ms)
                    ));

            assertThat(timer.count()).isEqualTo(10);
            assertThat(timer.totalTime(TimeUnit.MILLISECONDS))
                    .isEqualTo(2835.0);
            assertThat(timer.max(TimeUnit.MILLISECONDS))
                    .isEqualTo(900.0);
        }
    }
}
~~~

Kết quả mong đợi:

| Giá trị | Kết quả |
|---|---:|
| Count | 10 |
| Total time | 2 835 ms |
| Mean time | 283,5 ms |
| Max | 900 ms |

SimpleMeterRegistry xác nhận Timer nhận đủ dữ liệu và các thống kê cơ bản. Để xác minh bucket exposition theo định dạng Prometheus, cần chạy integration test hoặc ứng dụng có PrometheusMeterRegistry; không dùng assertion count/total ở SimpleMeterRegistry thay cho kiểm tra endpoint histogram.

## 7. Tính bucket counts từ dữ liệu mô phỏng

Histogram bucket của Prometheus là bucket tích lũy. Bucket le="0.3" chứa tất cả quan sát có thời gian nhỏ hơn hoặc bằng 300 ms, bao gồm cả các quan sát đã nằm trong bucket le="0.1".

Đếm dữ liệu mẫu:

| SLO boundary | Các mẫu nằm trong bucket | Count tích lũy |
|---:|---|---:|
| 100 ms | 45, 80 | 2 |
| 300 ms | 45, 80, 120, 180, 240, 260, 280 | 7 |
| 500 ms | Các mẫu đến 420 ms | 9 |
| 1.000 ms | Tất cả mẫu đến 900 ms | 10 |
| +Inf | Tất cả quan sát | 10 |

Tổng thời gian:

\[
45+80+120+180+240+260+280+310+420+900=2835\text{ ms}
\]

Tỷ lệ request hoàn tất trong 300 ms:

\[
\frac{7}{10}\times100\%=70\%
\]

Mục tiêu đặt ra là 95% request hoàn tất trong 300 ms. Tập dữ liệu mô phỏng chỉ đạt 70%, nên không đạt mục tiêu.

Lưu ý: serviceLevelObjectives chỉ khai báo ranh giới để thu thập dữ liệu. Nó không tự đặt mục tiêu 95%, không tự đánh dấu pass/fail và không tự tạo alert. Phần đánh giá mục tiêu được thực hiện bằng truy vấn hoặc hệ thống SLO/alerting.

## 8. Xác minh histogram trên Prometheus endpoint

Khởi động ứng dụng rồi đọc endpoint:

~~~powershell
$response = Invoke-WebRequest -Uri "http://localhost:8080/actuator/prometheus"
$response.Content | Select-String "payment_authorization_duration_seconds"
~~~

Với Prometheus classic histogram, tên Timer được chuẩn hóa thành metric có hậu tố đơn vị seconds. Các dòng sau minh họa những bucket SLO trong exposition; percentile histogram có thể tạo thêm các bucket khác:

~~~text
payment_authorization_duration_seconds_bucket{method="POST",route="/payments/{id}/authorize",le="0.1"} 2.0
payment_authorization_duration_seconds_bucket{method="POST",route="/payments/{id}/authorize",le="0.3"} 7.0
payment_authorization_duration_seconds_bucket{method="POST",route="/payments/{id}/authorize",le="0.5"} 9.0
payment_authorization_duration_seconds_bucket{method="POST",route="/payments/{id}/authorize",le="1.0"} 10.0
payment_authorization_duration_seconds_bucket{method="POST",route="/payments/{id}/authorize",le="+Inf"} 10.0
payment_authorization_duration_seconds_count{method="POST",route="/payments/{id}/authorize"} 10.0
payment_authorization_duration_seconds_sum{method="POST",route="/payments/{id}/authorize"} 2.835
~~~

Khi kiểm tra output thực tế:

- Có sample _bucket với le="0.1", le="0.3", le="0.5" và le="1.0".
- Count của bucket tăng dần vì bucket tích lũy.
- Bucket +Inf bằng tổng count.
- _count bằng 10.
- _sum bằng 2.835 giây.
- Label route và method giữ đúng giá trị cố định.

Nếu không thấy bucket SLO, kiểm tra Timer có được tạo bằng serviceLevelObjectives hay không, registry/exporter có hỗ trợ histogram không và MeterFilter có loại meter hoặc tag không. Nếu không thấy bất kỳ sample nào, kiểm tra endpoint, dependency registry và việc simulation runner đã chạy.

### Tự động kiểm tra endpoint bằng MockMvc

Với ứng dụng Spring Boot có starter test và MockMvc, có thể kiểm tra exposition trong integration test:

Các import MockMvc dưới đây theo cách tổ chức package của Spring Boot 3.x. Khi dùng Spring Boot major version khác, kiểm tra package test auto-configuration và starter tương ứng trong tài liệu phiên bản đó.

~~~java
import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class PrometheusHistogramIntegrationTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void exposesSloBucketsAndTimerCount() throws Exception {
        mockMvc.perform(get("/actuator/prometheus"))
                .andExpect(status().isOk())
                .andExpect(content().string(containsString(
                        "payment_authorization_duration_seconds_bucket"
                )))
                .andExpect(content().string(containsString("le=\"0.3\"")))
                .andExpect(content().string(containsString(
                        "payment_authorization_duration_seconds_count"
                )));
    }
}
~~~

Test này xác nhận endpoint có histogram bucket tại ngưỡng 300 ms và có sample count. Nếu ứng dụng bật Spring Security, cấu hình test authentication phù hợp hoặc kiểm thử bằng tài khoản/role scraper được phép; không tắt bảo mật endpoint chỉ để làm test pass.

## 9. Tính tỷ lệ đáp ứng SLO bằng PromQL

Với dữ liệu mô phỏng đã được ghi một lần, có thể xem trực tiếp tỷ lệ tích lũy:

~~~promql
payment_authorization_duration_seconds_bucket{
  route="/payments/{id}/authorize",
  method="POST",
  le="0.3"
}
/
payment_authorization_duration_seconds_count{
  route="/payments/{id}/authorize",
  method="POST"
}
~~~

Kết quả mong đợi là 0.7, tương ứng 70%.

Trong production, nên tính tỷ lệ trên một cửa sổ thời gian bằng rate:

~~~promql
sum by (route, method) (
  rate(payment_authorization_duration_seconds_bucket{
    le="0.3"
  }[5m])
)
/
sum by (route, method) (
  rate(payment_authorization_duration_seconds_count[5m])
)
~~~

Để đánh giá mục tiêu 95%, so sánh kết quả với 0.95. Ví dụ, nếu tỷ lệ thấp hơn 0.95 liên tục trong khoảng thời gian đã thống nhất, SLO đang bị vi phạm trong cửa sổ đó. Chính sách alert cần thêm điều kiện thời gian, xử lý dữ liệu thiếu và quy tắc loại trừ traffic phù hợp.

Có thể ước lượng p95 từ histogram:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, route, method) (
    rate(payment_authorization_duration_seconds_bucket[5m])
  )
)
~~~

Giữ label le trong phép tổng hợp để histogram_quantile có thể nội suy percentile. Không cộng trực tiếp các giá trị p95 client-side của nhiều instance.

## 10. Cấu hình tương đương bằng Spring Boot properties

Thay vì cấu hình distribution trên Timer.Builder, Spring Boot có thể cấu hình theo meter name trong application.yml:

~~~yaml
management:
  metrics:
    distribution:
      percentiles-histogram:
        payment.authorization.duration: true
      slo:
        payment.authorization.duration: 100ms,300ms,500ms,1s
      minimum-expected-value:
        payment.authorization.duration: 1ms
      maximum-expected-value:
        payment.authorization.duration: 5s
~~~

Nếu dùng cách cấu hình này, Timer có thể được đăng ký bằng name và tag bình thường:

~~~java
Timer timer = Timer.builder("payment.authorization.duration")
        .tags(
                "route", "/payments/{id}/authorize",
                "method", "POST"
        )
        .register(registry);
~~~

Chọn một nơi quản lý cấu hình phân phối làm nguồn chính: Timer.Builder hoặc Spring Boot properties. Tránh khai báo hai bộ ngưỡng khác nhau cho cùng meter rồi khó xác định cấu hình cuối cùng được áp dụng.

Các property trên áp dụng cho meter ID bắt đầu bằng tên đã chỉ định; tên cụ thể và cách bind cần được kiểm tra theo phiên bản Spring Boot của dự án. [Spring Boot: Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html).

## 11. So sánh ba cấu hình histogram

Hãy thử chạy cùng dữ liệu mô phỏng với ba cấu hình:

| Cấu hình | Kết quả mong đợi | Khi nên dùng |
|---|---|---|
| Không histogram, không SLO | Count, sum và các thống kê Timer cơ bản | Chỉ cần throughput và tổng thời gian |
| Chỉ serviceLevelObjectives | Bucket tại các ngưỡng dịch vụ đã chọn | Cần đo tỷ lệ đáp ứng một số ngưỡng cố định |
| serviceLevelObjectives + publishPercentileHistogram | Bucket SLO cộng bucket tự động | Cần cả SLO ratio và percentile tổng hợp linh hoạt |

Percentile histogram có thể tạo thêm nhiều bucket cho mỗi meter identity. Giới hạn minimum/maximum expected value và số tag để kiểm soát bộ nhớ, số series và payload export. Không bật histogram cho mọi meter chỉ vì có thể bật.

## 12. Những lỗi thường gặp trong bài thực hành

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Có Timer nhưng không có bucket | Chưa bật SLO/histogram hoặc registry không hỗ trợ | Kiểm tra Timer.Builder và exporter |
| Chỉ thấy _count và _sum | Histogram chưa được publish hoặc output bị filter | Kiểm tra cấu hình phân phối |
| Bucket le="0.3" có count lớn hơn số mẫu dưới 300 ms | Có thể đang đọc bucket tích lũy nhưng diễn giải như bucket riêng | Nhớ le là nhỏ hơn hoặc bằng |
| p95 không xuất hiện | Chỉ bật histogram; percentile được tính ở backend chứ không xuất client-side | Dùng histogram_quantile trong Prometheus |
| p95 không thể tổng hợp đúng giữa instance | Đang dùng publishPercentiles client-side | Dùng publishPercentileHistogram |
| Timer không có dữ liệu mô phỏng | ApplicationRunner chưa chạy hoặc component không được scan | Kiểm tra Spring context và log khởi động |
| Không truy cập được /actuator/prometheus | Chưa expose endpoint hoặc security chặn | Kiểm tra Actuator, exposure và quyền scraper |
| Tên metric khác dự kiến | Naming convention của registry chuẩn hóa tên | Tìm tên đã export trong endpoint |
| Số series tăng mạnh | Quá nhiều tag hoặc histogram bật trên meter cardinality cao | Giảm tag và giới hạn histogram theo meter |

## 13. Bài tập mở rộng

Sau khi hoàn thành phần chính, thực hiện các thử nghiệm sau:

**Thử nghiệm A — Thay đổi ngưỡng**

Đổi SLO boundaries thành 100 ms, 250 ms, 400 ms và 800 ms. Tính lại bucket counts từ tập mẫu. Giải thích vì sao tỷ lệ request dưới 250 ms khác tỷ lệ dưới 300 ms.

**Thử nghiệm B — Cải thiện dữ liệu mô phỏng**

Thay ba mẫu chậm nhất bằng 180 ms, 220 ms và 250 ms. Ghi lại dữ liệu và xác định tỷ lệ dưới 300 ms có đạt 95% không. Đừng quên reset registry hoặc khởi động lại ứng dụng để không trộn hai lần mô phỏng.

**Thử nghiệm C — So sánh percentile**

Chạy một instance với publishPercentiles(0.95), sau đó chạy nhiều instance và so sánh cách tổng hợp với publishPercentileHistogram(). Giải thích vì sao không thể lấy trung bình các giá trị p95 của từng instance để có p95 toàn hệ thống.

**Thử nghiệm D — Kiểm soát chi phí**

Tăng số route tag hoặc thêm một tag có nhiều giá trị. Quan sát số meter và series khi histogram bật. Sau đó loại dimension không cần thiết và so sánh lại.

**Thử nghiệm E — Thiết kế alert**

Viết điều kiện cảnh báo khi tỷ lệ request dưới 300 ms thấp hơn 95% trong một cửa sổ liên tục. Nêu cách xử lý khi tổng request quá thấp hoặc không có dữ liệu.

## 14. Tiêu chí hoàn thành

Bài thực hành đạt yêu cầu khi bạn có thể cung cấp:

- Code đăng ký Timer với tên ổn định và tag có cardinality thấp.
- Cấu hình histogram có bốn SLO boundaries.
- Tập dữ liệu mô phỏng gồm 10 độ trễ.
- Test xác nhận count = 10, total time = 2 835 ms và max = 900 ms.
- Bảng bucket counts tích lũy: 2, 7, 9, 10 và +Inf = 10.
- Kết quả tỷ lệ dưới 300 ms là 70%, thấp hơn mục tiêu 95%.
- Bằng chứng endpoint Prometheus có bucket, count và sum.
- PromQL tính tỷ lệ SLO và p95.
- Giải thích được khác biệt giữa SLO boundaries, percentile histogram và client-side percentiles.
- Giải thích được tác động của histogram đến số bucket, bộ nhớ và time series.

## 15. Tổng kết thực hành

Bạn đã cấu hình Timer để thu thập độ trễ thanh toán, thêm các bucket tại 100 ms, 300 ms, 500 ms và 1 giây, rồi ghi dữ liệu mô phỏng để kiểm chứng. Từ bucket tích lũy, có thể tính trực tiếp tỷ lệ request đáp ứng ngưỡng 300 ms; tập mẫu cho kết quả 70%, thấp hơn mục tiêu 95%.

Khi triển khai thực tế, hãy chọn ranh giới phù hợp với SLO của dịch vụ, dùng percentile histogram nếu cần tổng hợp percentile giữa các instance, giữ tag cardinality thấp và kiểm tra dữ liệu ở cả MeterRegistry lẫn endpoint export. Histogram cung cấp dữ liệu để đánh giá; chính sách SLO, truy vấn và alerting mới quyết định khi nào dịch vụ được xem là đạt hoặc vi phạm mục tiêu.

## Tài liệu tham khảo

- [Micrometer - Histograms and Percentiles](https://docs.micrometer.io/micrometer/reference/concepts/histogram-quantiles.html)
- [Micrometer - Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html)
- [Micrometer - Meter Filters](https://docs.micrometer.io/micrometer/reference/concepts/meter-filters.html)
- [Spring Boot - Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Spring Boot - Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/index.html)
- [Prometheus - Histograms and Summaries](https://prometheus.io/docs/practices/histograms/)
