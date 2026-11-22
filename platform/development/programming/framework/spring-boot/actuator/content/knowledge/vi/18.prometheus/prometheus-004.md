# Hiểu count, sum và bucket của Timer hoặc DistributionSummary

Bốn lượt gọi mất lần lượt 100, 200, 500 và 800 ms. Từ đó có thể trả lời ba câu hỏi. Đã đo bao nhiêu lượt? Tổng thời lượng là bao nhiêu? Bao nhiêu lượt nằm trong ngưỡng? Trong Prometheus, đọc các chuỗi `_count», `_sum» và `_bucket» của histogram kiểu cổ điển để trả lời từng câu hỏi.

## Chọn meter theo đại lượng cần đo

| Meter Micrometer | Mỗi quan sát là gì? | `_count» đếm gì? | `_sum» cộng gì? |
| --- | --- | --- | --- |
| `Timer» | Thời lượng của một thao tác. Ghi bằng `Duration» hoặc kèm `TimeUnit». | Số thời lượng đã ghi nhận. | Tổng thời lượng. Registry Prometheus xuất theo giây. |
| `DistributionSummary» | Một giá trị số như kích thước phản hồi tính bằng byte. | Số giá trị đã ghi nhận. | Tổng giá trị theo đơn vị đang đo, chẳng hạn tổng byte. |

`_count» chỉ đếm các lần meter nhận quan sát. Ví dụ, nếu chương trình ghi kích thước một lần cho mỗi phản hồi, `_count» là số phản hồi đã được đo. `_sum» của timer là tổng thời lượng từng lượt, nên khi các lượt chạy đồng thời, tổng có thể lớn hơn thời gian trôi qua theo đồng hồ.

`DistributionSummary» là tên kiểu meter trong Micrometer. Khi xuất các bucket sang Prometheus, meter này có thể xuất dưới dạng histogram. Dùng `Timer» khi đo thời lượng để Micrometer chuyển đúng đơn vị cho hệ thống giám sát.

## Đọc các chuỗi của histogram kiểu cổ điển

Giả sử `demo.request.duration» là timer đã ghi bốn thời lượng trên và cấu hình hai ranh giới 200 ms và 500 ms. Phần liên quan trong dữ liệu xuất Prometheus có dạng:

~~~text
demo_request_duration_seconds_count 4
demo_request_duration_seconds_sum 1.6
demo_request_duration_seconds_bucket{le="0.2"} 2
demo_request_duration_seconds_bucket{le="0.5"} 3
demo_request_duration_seconds_bucket{le="+Inf"} 4
~~~

`le» nghĩa là *less than or equal*, tức **nhỏ hơn hoặc bằng**. Bucket `le="0.5"» đếm cả ba lượt 100, 200 và 500 ms. Vì các bucket lồng nhau, hãy **lấy hiệu** hai bucket liền kề để đếm số lượt trong khoảng giữa hai ranh giới.

| Câu hỏi | Cách đọc | Kết quả |
| --- | --- | --- |
| Bao nhiêu lượt mất tối đa 200 ms? | Bucket `le="0.2"». | 2 lượt |
| Bao nhiêu lượt mất hơn 200 ms và tối đa 500 ms? | Bucket `le="0.5"» trừ bucket `le="0.2"». | 3 − 2 = 1 lượt |
| Bao nhiêu lượt mất hơn 500 ms? | `_count» trừ bucket `le="0.5"». | 4 − 3 = 1 lượt |
| Độ trễ trung bình của bốn lượt? | `_sum / _count». | 1,6 s / 4 = 0,4 s, tức 400 ms |

Bucket `+Inf» bao phủ toàn bộ quan sát. Trong cùng một histogram và cùng bộ nhãn, giá trị của nó bằng `_count». Với `DistributionSummary» đo byte, cách đọc giống hệt. Nếu có bốn mẫu 256, 1024, 1024 và 4096 byte thì `_count» là 4, `_sum» là 6400 byte, còn bucket `le="1024"» là 3.

`_count» và `_sum» vẫn có thể xuất hiện khi chưa bật bucket. Nếu cần đếm tại ranh giới cụ thể, cấu hình `serviceLevelObjectives(...)» khi đăng ký meter hoặc `management.metrics.distribution.slo» theo tên meter trong Spring Boot. Truy vấn theo `le» cần dùng ranh giới thực sự được xuất và đúng đơn vị. Chẳng hạn, ranh giới timer `200ms» xuất thành `le="0.2"».

## Thực hành với hai meter và dữ liệu cố định

Ví dụ Java chạy độc lập với `micrometer-core». Nó dùng `SimpleMeterRegistry» để in số đo và các bucket hữu hạn ngay trong tiến trình. Ở registry Prometheus, cùng các quan sát và ranh giới sẽ cho phần số đo tương ứng như ví dụ trên, cùng bucket `+Inf» của định dạng xuất.

Tạo `build.gradle» trong thư mục thử riêng:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'io.micrometer:micrometer-core:1.13.0'
}

application {
    mainClass = 'example.MeterSnapshotDemo'
}
~~~

Tạo `src/main/java/example/MeterSnapshotDemo.java»:

~~~java
package example;

import java.time.Duration;
import java.util.Locale;
import java.util.concurrent.TimeUnit;

import io.micrometer.core.instrument.DistributionSummary;
import io.micrometer.core.instrument.MockClock;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleConfig;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

public class MeterSnapshotDemo {
    public static void main(String[] args) {
        var registry = new SimpleMeterRegistry(SimpleConfig.DEFAULT, new MockClock());
        try {
            Timer timer = Timer.builder("demo.request.duration")
                    .serviceLevelObjectives(Duration.ofMillis(200), Duration.ofMillis(500))
                    .register(registry);

            DistributionSummary payload = DistributionSummary.builder("demo.response.size")
                    .baseUnit("bytes")
                    .serviceLevelObjectives(512, 1024)
                    .register(registry);

            for (long millis : new long[] {100, 200, 500, 800}) {
                timer.record(Duration.ofMillis(millis));
            }
            for (int bytes : new int[] {256, 1024, 1024, 4096}) {
                payload.record(bytes);
            }

            System.out.printf(Locale.ROOT, "Timer count=%d sum=%.3f s%n",
                    timer.count(), timer.totalTime(TimeUnit.SECONDS));
            for (var bucket : timer.takeSnapshot().histogramCounts()) {
                System.out.printf(Locale.ROOT, "  le=%.3f s count=%.0f%n",
                        bucket.bucket(TimeUnit.SECONDS), bucket.count());
            }

            System.out.printf(Locale.ROOT, "Summary count=%d sum=%.0f bytes%n",
                    payload.count(), payload.totalAmount());
            for (var bucket : payload.takeSnapshot().histogramCounts()) {
                System.out.printf(Locale.ROOT, "  le=%.0f bytes count=%.0f%n",
                        bucket.bucket(), bucket.count());
            }
        } finally {
            registry.close();
        }
    }
}
~~~

Với JDK 17 trở lên và Gradle tương thích, chạy `gradle -q run». Kết quả của chương trình:

~~~text
Timer count=4 sum=1.600 s
  le=0.200 s count=2
  le=0.500 s count=3
Summary count=4 sum=6400 bytes
  le=512 bytes count=1
  le=1024 bytes count=3
~~~

Để tự kiểm tra, thêm một lượt đúng 500 ms. `Timer count» tăng lên 5, `sum» lên 2,100 giây và bucket 500 ms tăng lên 4. Bucket 200 ms vẫn đếm 2 lượt.

## Từ số đo tích lũy sang câu hỏi theo cửa sổ

Trên Prometheus, đọc trực tiếp `_sum / _count» là tính bình quân của số đo tích lũy trong chuỗi đang xem. Nếu ứng dụng đã chạy nhiều giờ và câu hỏi chỉ liên quan đến 5 phút gần nhất, dùng tốc độ tăng của hai chuỗi trong cùng cửa sổ. Ví dụ dưới đây gộp các bản sao thuộc cùng job `demo»:

~~~promql
sum(rate(demo_request_duration_seconds_sum{job="demo"}[5m]))
/
sum(rate(demo_request_duration_seconds_count{job="demo"}[5m]))
~~~

Tử số là số giây thời lượng ghi nhận mỗi giây. Mẫu số là số lượt ghi nhận mỗi giây. Kết quả là **giây trên mỗi lượt**. Cộng số đo của từng bản sao trước khi chia để bản sao xử lý nhiều lượt có trọng số tương ứng. Áp dụng `rate» cho từng chuỗi trước khi cộng để xử lý việc bộ đếm đặt lại khi tiến trình khởi động lại.

Để tính tỷ lệ lượt mất tối đa 200 ms trong cùng cửa sổ, dùng bucket làm tử số:

~~~promql
sum(rate(demo_request_duration_seconds_bucket{job="demo", le="0.2"}[5m]))
/
sum(rate(demo_request_duration_seconds_count{job="demo"}[5m]))
~~~

Hai vế phải chọn cùng phạm vi lượt đo. Khi gộp nhiều bản sao, mọi chuỗi ở mẫu số cần có bucket tương ứng ở tử số. Nếu mẫu số bằng 0 hoặc cửa sổ thiếu mẫu để tính tốc độ, hiển thị trạng thái thiếu dữ liệu. Cả hai truy vấn dùng cùng nguyên tắc cho meter đo kích thước, nhưng kết quả của phép tính trung bình lúc đó mang đơn vị byte mỗi lượt.

### Tài liệu tham khảo

- [Micrometer 1.13 – Timer và đơn vị thời lượng](https://docs.micrometer.io/micrometer/reference/1.13/concepts/timers.html)
- [Micrometer 1.13 – Ranh giới histogram](https://docs.micrometer.io/micrometer/reference/1.13/concepts/histogram-quantiles.html)
- [Prometheus – Histogram và summary](https://prometheus.io/docs/practices/histograms/)