# Thời hạn thống kê phân bố, bộ đệm và giá trị cực đại

Một yêu cầu HTTP mất 800 ms. Sau đó dịch vụ không nhận thêm yêu cầu, nhưng biểu đồ vẫn hiện `max = 800 ms` trong vài lần lấy mẫu rồi hạ về 0. Đây có thể là hành vi bình thường của một giá trị cực đại theo cửa sổ thời gian. Để đọc biểu đồ, cần xác định thống kê giữ mẫu trong bao lâu, registry xuất số liệu theo kiểu nào và hệ thống giám sát lấy mẫu khi nào.

## Từ một lần đo đến các thống kê có thời hạn khác nhau

Micrometer dùng `Timer` cho thời lượng và `DistributionSummary` cho độ lớn không phải thời gian, chẳng hạn kích thước phản hồi tính bằng byte. Mỗi meter được xác định theo tên và bộ tag. Một lần ghi vào `Timer` có thể cập nhật số lần đo (`count`), tổng thời gian (`totalTime`), cực đại (`max`) và dữ liệu phân bố nếu đã bật cấu hình tương ứng.

- **Cực đại theo cửa sổ thời gian** giữ đỉnh gần đây. Khi đỉnh cũ hết hạn, `max` có thể hạ xuống một mẫu nhỏ hơn còn trong cửa sổ, hoặc về 0 nếu cửa sổ đã trống.
- **Percentile tính trong ứng dụng** dựa trên histogram nội bộ có xoay bộ đệm. Sau khi mẫu cũ hết hạn, nó hết ảnh hưởng tới percentile. Giá trị percentile là ước lượng và có thể khác giá trị mẫu ngay cả khi chỉ có một quan sát.
- **Số đếm, tổng và bucket xuất ra ngoài** tuân theo cách registry biểu diễn. Chẳng hạn với Prometheus, bucket của histogram `Timer` thông thường là bộ đếm tích lũy. Việc hết hạn của `max` diễn ra độc lập với bộ đếm này.

## Hai tham số điều khiển bộ đệm

`expiry` là thời lượng mà thuật toán xoay dùng để định kỳ bỏ dữ liệu cũ. `buffer-length` là số ngăn trong vòng đệm. Các ngăn được tái sử dụng lần lượt. Khi quay lại một ngăn, dữ liệu cũ của ngăn đó được xóa. Vị trí thời điểm ghi so với ranh giới xoay ảnh hưởng đến thời gian một mẫu còn đóng góp vào thống kê.

Với các `Timer` cơ bản của Micrometer 1.13, hai triển khai dùng cùng cấu hình nhưng diễn giải thời gian xoay khác nhau.

| Thống kê | Cơ chế | Với `expiry=10s` và `buffer-length=3` |
| --- | --- | --- |
| `max()` dùng `TimeWindowMax` | Xoay một ngăn sau mỗi `expiry`. Một vòng xóa hết dữ liệu cũ mất `expiry × buffer-length`. | Xoay mỗi 10 giây. Toàn vòng là 30 giây. Đỉnh ghi gần cuối một ngăn có thể hết hạn trước khi đủ 30 giây kể từ lúc ghi. |
| Percentile nội bộ dùng `TimeWindowPercentileHistogram` | Trong Micrometer 1.13.0, histogram nội bộ xoay một ngăn theo `expiry / buffer-length`. | Xoay khoảng mỗi 3,33 giây. Toàn vòng khoảng 10 giây. |

`buffer-length` mặc định là 3 trong cấu hình phân bố lõi. Giá trị `expiry` hiệu lực còn phụ thuộc registry. Ví dụ, Prometheus registry trong Micrometer 1.13 lấy `step` của registry làm `expiry` mặc định. `step` này là cấu hình trong ứng dụng. Khoảng cách giữa các lần Prometheus scrape do máy chủ Prometheus cấu hình riêng.

## Đọc cực đại theo registry

| Registry và kiểu xuất | Số đếm và tổng của `Timer` | Ý nghĩa của cực đại |
| --- | --- | --- |
| `SimpleMeterRegistry` ở chế độ `CUMULATIVE` | Tích lũy từ khi meter được tạo. | `Timer.max(unit)` đọc đỉnh còn trong `TimeWindowMax` và đổi sang đơn vị được yêu cầu. |
| `SimpleMeterRegistry` ở chế độ `STEP` với `StepTimer` | Trả về số liệu của kỳ đã kết thúc gần nhất. | `max()` dùng cửa sổ xoay riêng. Kỳ vừa kết thúc có thể có `count = 0` trong lúc một đỉnh từ kỳ trước vẫn còn. |
| Prometheus registry với `Timer` thông thường | `_count` và `_sum` tích lũy. Khi xuất histogram cổ điển, các chuỗi `_bucket` cũng tích lũy qua các lần scrape. | `_seconds_max` là gauge tính bằng giây. Mỗi lần scrape lấy đỉnh còn trong cửa sổ của ứng dụng tại thời điểm đó. |
| OTLP registry 1.13 với điểm dữ liệu Histogram | Với kiểu thời gian tích lũy (`CUMULATIVE`), điểm dữ liệu tích lũy từ mốc bắt đầu. Với kiểu chênh lệch theo kỳ (`DELTA`), điểm dữ liệu mô tả kỳ xuất tương ứng. | Micrometer 1.13 chỉ hỗ trợ trường `max` của điểm Histogram ở chế độ `DELTA`. Vì vậy, khi đổi từ Prometheus sang OTLP, cần kiểm tra kiểu xuất và trường thực tế mà bộ thu nhận được. |

Các chế độ xuất theo kỳ có thể khác nhau giữa các registry. Bảng mô tả từng triển khai nêu tên, với `Timer` đo các công việc đã hoàn thành. Với `DistributionSummary`, khi registry có xuất cực đại, đọc đơn vị theo giá trị được ghi và cấu hình đơn vị hoặc tỉ lệ của meter.

## Cấu hình trong Spring Boot

Ví dụ đặt trong `application.properties` để áp dụng cho meter HTTP `http.server.requests` của ứng dụng web dùng Actuator.

```properties
management.metrics.distribution.expiry.http.server.requests=10s
management.metrics.distribution.buffer-length.http.server.requests=3
```

Hậu tố là tên meter Micrometer trong ứng dụng. Các thuộc tính phân bố của Spring Boot áp dụng theo tiền tố tên meter và ưu tiên tiền tố khớp dài nhất. Chỉ đặt hai thuộc tính trên sẽ thay đổi cách xoay các thống kê dùng cửa sổ. Muốn xuất percentile cục bộ hoặc histogram, bật riêng kiểu thống kê cần dùng. `maximum-expected-value` điều chỉnh dải bucket được công bố với histogram percentile, còn `expiry` và `buffer-length` điều chỉnh thời gian của bộ đệm xoay.

Khi chọn thời hạn cho `max`, cân nhắc nhịp scrape hoặc nhịp gửi dữ liệu, khoảng ngắt do tải cao và tần suất phát sinh quan sát. Giữ đỉnh lâu hơn giúp lần thu thập sau có cơ hội thấy đỉnh, đồng thời khiến đỉnh cũ còn hiện lâu hơn. Tăng số ngăn có thể tăng bộ nhớ cho các thống kê phân bố dùng vòng đệm, nhất là khi meter có nhiều tổ hợp tag. Thay đổi hai thuộc tính này cũng độc lập với thời hạn lưu các điểm đã thu ở hệ thống giám sát.

## Kiểm chứng bằng đồng hồ mô phỏng

Ví dụ chạy độc lập trên Java 17+ với `io.micrometer:micrometer-core:1.13.0` và các phụ thuộc lúc chạy. Lưu tệp `TimerWindows.java`. Chương trình ghi đúng một mẫu 800 ms cho mỗi registry, rồi tiến đồng hồ để xem `count`, tổng thời gian, `max` và p95 thay đổi.

```java
import io.micrometer.core.instrument.MockClock;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.CountingMode;
import io.micrometer.core.instrument.simple.SimpleConfig;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

import java.time.Duration;
import java.util.Locale;
import java.util.concurrent.TimeUnit;

public class TimerWindows {
    public static void main(String[] args) {
        run(CountingMode.CUMULATIVE);
        run(CountingMode.STEP);
    }

    private static void run(CountingMode countingMode) {
        MockClock clock = new MockClock();
        SimpleConfig config = new SimpleConfig() {
            @Override
            public String get(String key) {
                return null;
            }

            @Override
            public CountingMode mode() {
                return countingMode;
            }

            @Override
            public Duration step() {
                return Duration.ofSeconds(10);
            }
        };

        SimpleMeterRegistry registry = new SimpleMeterRegistry(config, clock);
        try {
            Timer timer = Timer.builder("demo.latency")
                    .distributionStatisticExpiry(Duration.ofSeconds(10))
                    .distributionStatisticBufferLength(3)
                    .publishPercentiles(0.95)
                    .register(registry);

            timer.record(Duration.ofMillis(800));

            clock.add(Duration.ofSeconds(1));
            print(countingMode, 1, timer);

            clock.add(Duration.ofSeconds(10));
            print(countingMode, 11, timer);

            clock.add(Duration.ofSeconds(10));
            print(countingMode, 21, timer);

            clock.add(Duration.ofSeconds(10));
            print(countingMode, 31, timer);
        } finally {
            registry.close();
        }
    }

    private static void print(CountingMode mode, int elapsedSeconds, Timer timer) {
        double p95 = timer.takeSnapshot().percentileValues()[0].value(TimeUnit.MILLISECONDS);
        System.out.printf(Locale.ROOT, "%s t=%ds count=%d total=%.0fms max=%.0fms p95=%.0fms%n",
                mode, elapsedSeconds, timer.count(), timer.totalTime(TimeUnit.MILLISECONDS),
                timer.max(TimeUnit.MILLISECONDS), p95);
    }
}
```

Trên Bash, đặt biến `MICROMETER_CP` thành classpath chứa các JAR lúc chạy mà Maven hoặc Gradle giải quyết cho `micrometer-core:1.13.0`, rồi chạy hai lệnh sau.

```bash
javac --release 17 -cp "$MICROMETER_CP" TimerWindows.java
java -cp ".:$MICROMETER_CP" TimerWindows
```

Kết quả của chương trình với Micrometer 1.13.0.

```text
CUMULATIVE t=1s count=1 total=800ms max=800ms p95=772ms
CUMULATIVE t=11s count=1 total=800ms max=800ms p95=0ms
CUMULATIVE t=21s count=1 total=800ms max=800ms p95=0ms
CUMULATIVE t=31s count=1 total=800ms max=0ms p95=0ms
STEP t=1s count=0 total=0ms max=800ms p95=772ms
STEP t=11s count=1 total=800ms max=800ms p95=0ms
STEP t=21s count=0 total=0ms max=800ms p95=0ms
STEP t=31s count=0 total=0ms max=0ms p95=0ms
```

- Ở giây 1, `STEP` vẫn trả số đếm của kỳ trước vì kỳ 10 giây đầu đang diễn ra. `max` và p95 đã nhận mẫu. Giá trị `772 ms` là ước lượng từ histogram nội bộ, làm tròn đến mili giây khi in.
- Ở giây 11, mẫu đã rời cửa sổ percentile nhưng vẫn góp vào `max`. `STEP` lúc này báo một lần đo thuộc kỳ đầu vừa hoàn thành.
- Ở giây 21, `STEP` báo kỳ đã hoàn thành không có mẫu, còn `max` vẫn là 800 ms. Đến giây 31, `max` về 0 ở cả hai chế độ. `CUMULATIVE` vẫn giữ số lần đo và tổng thời gian. Giá trị 0 của `max` hoặc p95 trong lần chạy này phản ánh cửa sổ tương ứng đã trống.

## Kiểm tra trên Prometheus

Với Actuator đã mở endpoint Prometheus và đã có lưu lượng, đối chiếu `http_server_requests_seconds_max` và `http_server_requests_seconds_count` trên cùng tập nhãn. `max_over_time(http_server_requests_seconds_max[5m])` lấy giá trị gauge cao nhất **trong các điểm đã scrape** của từng chuỗi trong 5 phút. Một đỉnh có thể đã hết hạn trước lần scrape tiếp theo, hoặc còn nằm trong cửa sổ ứng dụng từ trước khoảng truy vấn. Do đó, thời điểm quan sát gauge và thời điểm xảy ra yêu cầu chậm có thể khác nhau.

Khi thấy `_max` bằng 0, xem mức tăng của `_count` trên cửa sổ phù hợp để phân biệt giai đoạn ít hoặc không có yêu cầu với độ trễ thực sự thấp. Nếu cả chuỗi biến mất, kiểm tra trạng thái scrape và sự tồn tại của meter. Với `_max`, dùng phép so sánh hoặc lấy cực đại trên các mẫu gauge. `rate()` trên `_count` dùng để đo tốc độ phát sinh yêu cầu.

## Tài liệu tham khảo

- [Spring Boot 3.3 — Metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html)
- [Micrometer 1.13 — Timers](https://docs.micrometer.io/micrometer/reference/1.13/concepts/timers.html)
- [Micrometer — Khác biệt giữa thời hạn của max và percentile](https://github.com/micrometer-metrics/micrometer/issues/3298)
- [Micrometer 1.13.15 — PrometheusMeterRegistry](https://github.com/micrometer-metrics/micrometer/blob/v1.13.15/implementations/micrometer-registry-prometheus/src/main/java/io/micrometer/prometheusmetrics/PrometheusMeterRegistry.java)
- [Micrometer 1.13 — OTLP](https://docs.micrometer.io/micrometer/reference/1.13/implementations/otlp)
- [Prometheus — Các phép tổng hợp theo thời gian](https://prometheus.io/docs/prometheus/latest/querying/functions/#aggregation_over_time)
