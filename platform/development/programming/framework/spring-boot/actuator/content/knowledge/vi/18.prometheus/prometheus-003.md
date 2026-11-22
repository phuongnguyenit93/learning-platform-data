## Đọc tên metric, label, đơn vị và hậu tố sau khi chuyển đổi

Một meter mang tên `http.server.requests` trong Spring Boot có thể xuất hiện ở Prometheus dưới nhiều tên, chẳng hạn `http_server_requests_seconds_count` và `http_server_requests_seconds_sum`. Hai dòng này mô tả hai số đo khác nhau của cùng một `Timer`. Muốn đọc đúng một dòng, hãy xác định tên meter gốc, bộ nhãn, đơn vị của giá trị và ý nghĩa của hậu tố.

### Từ ID trong Micrometer đến chuỗi thời gian

Với cấu hình mặc định của `micrometer-registry-prometheus` trong Micrometer 1.13, tên meter dạng có dấu chấm thường được chuyển thành dạng phân tách bằng dấu gạch dưới. Quy tắc xuất còn phụ thuộc vào loại meter và đơn vị. Ví dụ, `Timer` `demo.checkout.duration` có họ metric `demo_checkout_duration_seconds`. Gauge `demo.checkout.queue.memory` có đơn vị cơ sở `bytes` có thể xuất thành `demo_checkout_queue_memory_bytes`. Các bộ lọc đổi tên hoặc quy tắc đặt tên tùy chỉnh có thể thay đổi kết quả. Hãy đọc tên thật trên endpoint trước khi viết truy vấn.

Nhãn (label) là một cặp khóa–giá trị trong dấu ngoặc nhọn. Micrometer có thể chuẩn hóa khóa tag `payment.channel` thành `payment_channel` khi xuất. Giá trị `web` vẫn là giá trị của chiều đo đó. Với Prometheus, tên chuỗi cộng với toàn bộ bộ nhãn xác định một chuỗi thời gian. Hai dòng cùng tên có `payment_channel="web"` và `payment_channel="mobile"` là hai chuỗi khác nhau. Đảo thứ tự nhãn trong cùng một dòng không tạo ra chuỗi mới. Mỗi giá trị nhãn mới có thể tăng số chuỗi, nên ưu tiên giá trị hữu hạn như kênh thanh toán hoặc mẫu tuyến đường thay vì mã đơn hàng hay URL chứa ID.

Các nhãn `job` và `instance` thường được Prometheus gắn khi thu thập dữ liệu theo cấu hình đích. Chúng có thể có mặt trong kết quả PromQL dù ứng dụng không in chúng trong `/actuator/prometheus`. Nhãn `le` và `quantile` có ý nghĩa do kiểu histogram hoặc summary quy định, khác với các nhãn nghiệp vụ.

### Đơn vị và hậu tố nói lên điều gì?

| Tên hoặc hậu tố | Giá trị cần đọc | Ví dụ |
| --- | --- | --- |
| `_total` | Giá trị tích lũy của Counter. Bộ đếm có thể đặt lại khi tiến trình khởi động lại. | `demo_checkout_attempts_total 3` là ba lần thử tích lũy. |
| `_count` | Số lần quan sát tích lũy của Timer hoặc phân bố. Đơn vị là số lần dù tên họ có `_seconds` hoặc `_bytes`. | `demo_checkout_duration_seconds_count 2` là hai lần đo. |
| `_sum` | Tổng các giá trị đã quan sát, theo đơn vị của họ metric. | `demo_checkout_duration_seconds_sum 0.2` là tổng cộng 0,2 giây. |
| `_bucket{le="..."}` | Số lần đo nhỏ hơn hoặc bằng ngưỡng trên của bucket trong histogram cổ điển. Ngưỡng `le` dùng đơn vị của đại lượng đo, còn giá trị dòng là số lần. | Với `le="0.1"`, giá trị `1` nghĩa là một lần đo không quá 100 ms. |
| `_max` | Gauge do registry Prometheus của Micrometer xuất cho các meter phân bố như Timer. Đây là giá trị cực đại theo cửa sổ thống kê của meter. | `demo_checkout_duration_seconds_max 0.16` là 160 ms. |
| `{quantile="..."}` trên tên họ summary | Phân vị do ứng dụng tính khi cấu hình xuất phân vị theo cách này. Giá trị dòng có đơn vị của đại lượng đo. | `quantile="0.95"` chọn ước lượng p95. Trung bình cộng p95 của nhiều bản sao không cho p95 toàn hệ thống. |
| Hậu tố đơn vị như `_bytes` | Với một Gauge bộ nhớ, giá trị là số byte tại thời điểm đọc. Gauge có thể tăng hoặc giảm. | `demo_checkout_queue_memory_bytes 2048` là 2.048 byte, tương đương 2 KiB. |

`_seconds` mô tả đơn vị của thời lượng. Ví dụ, khi ghi `Duration.ofMillis(160)` vào `Timer`, thời lượng này tương ứng với 0,16 giây khi xuất. Với Gauge hoặc `DistributionSummary` tự tạo, `baseUnit("bytes")` khai báo đơn vị. Giá trị do mã ứng dụng cung cấp cần thực sự là byte. Nếu mã đưa vào 2 với ý nghĩa 2 KiB, chỉ thêm `baseUnit("bytes")` sẽ khiến đầu ra bị hiểu thành 2 byte.

Xem dòng `# TYPE` để phân biệt `counter`, `gauge`, `summary` và `histogram`. `# HELP` giải thích metric khi mô tả được xuất. Các dòng này là siêu dữ liệu. Một Timer có thể xuất `_count` và `_sum` ngay cả khi không có bucket. Dòng `_bucket` trong ví dụ dưới đến từ các mốc SLO được cấu hình. Với histogram cổ điển, `le="+Inf"` bao gồm mọi lần đo nên có giá trị bằng `_count` nếu các nhãn còn lại giống nhau.

### Đối chiếu bằng hai lần đo

Lưu chương trình sau thành `MetricReadingDemo.java`. Chương trình chạy trong bộ đăng ký Micrometer đơn giản để kiểm tra tên và nhãn gốc cùng các giá trị trước khi xuất.

```java
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

import java.time.Duration;
import java.util.Locale;
import java.util.concurrent.atomic.AtomicLong;

import static java.util.concurrent.TimeUnit.SECONDS;

public class MetricReadingDemo {
    public static void main(String[] args) {
        var registry = new SimpleMeterRegistry();
        try {
            var timer = Timer.builder("demo.checkout.duration")
                    .tag("payment.channel", "web")
                    .serviceLevelObjectives(Duration.ofMillis(100), Duration.ofMillis(250))
                    .register(registry);
            timer.record(Duration.ofMillis(40));
            timer.record(Duration.ofMillis(160));

            var attempts = registry.counter("demo.checkout.attempts", "payment.channel", "web");
            attempts.increment(3);
            var queuedBytes = new AtomicLong(2048);
            var gauge = Gauge.builder("demo.checkout.queue.memory", queuedBytes, AtomicLong::get)
                    .baseUnit("bytes")
                    .register(registry);

            var snapshot = timer.takeSnapshot();
            System.out.printf(Locale.ROOT, "%s %s=%s count=%d sumSeconds=%.3f maxSeconds=%.3f%n",
                    timer.getId().getName(), "payment.channel", timer.getId().getTag("payment.channel"),
                    snapshot.count(), snapshot.total(SECONDS), snapshot.max(SECONDS));
            for (var bucket : snapshot.histogramCounts()) {
                System.out.printf(Locale.ROOT, "boundarySeconds=%.3f count=%.0f%n",
                        bucket.bucket(SECONDS), bucket.count());
            }
            System.out.printf(Locale.ROOT, "%s=%.0f%n", attempts.getId().getName(), attempts.count());
            System.out.printf(Locale.ROOT, "%s=%.0f %s%n",
                    gauge.getId().getName(), gauge.value(), gauge.getId().getBaseUnit());
        } finally {
            registry.close();
        }
    }
}
```

Dùng JDK 17 trở lên. Phân giải `io.micrometer:micrometer-core:1.13.0` và các thư viện phụ thuộc bằng Maven hoặc Gradle, rồi đặt `CP` thành classpath chứa các tệp JAR. Các lệnh sau dùng Bash. Trong PowerShell, tham chiếu biến bằng `$env:CP` và dùng dấu `;` để phân tách classpath.

```bash
javac -cp "$CP" MetricReadingDemo.java
java -cp ".:$CP" MetricReadingDemo
```

Kết quả chương trình:

```text
demo.checkout.duration payment.channel=web count=2 sumSeconds=0.200 maxSeconds=0.160
boundarySeconds=0.100 count=1
boundarySeconds=0.250 count=2
demo.checkout.attempts=3
demo.checkout.queue.memory=2048 bytes
```

Nếu đăng ký cùng các meter và ghi cùng dữ liệu vào registry Prometheus mặc định của Micrometer 1.13, có thể đọc đầu ra theo mẫu minh họa sau. Mẫu lược bớt siêu dữ liệu để tập trung vào các chuỗi.

```text
# TYPE demo_checkout_duration_seconds histogram
demo_checkout_duration_seconds_bucket{payment_channel="web",le="0.1"} 1
demo_checkout_duration_seconds_bucket{payment_channel="web",le="0.25"} 2
demo_checkout_duration_seconds_bucket{payment_channel="web",le="+Inf"} 2
demo_checkout_duration_seconds_count{payment_channel="web"} 2
demo_checkout_duration_seconds_sum{payment_channel="web"} 0.2
# TYPE demo_checkout_duration_seconds_max gauge
demo_checkout_duration_seconds_max{payment_channel="web"} 0.16
demo_checkout_attempts_total{payment_channel="web"} 3
# TYPE demo_checkout_queue_memory_bytes gauge
demo_checkout_queue_memory_bytes 2048
```

Trong hai mẫu 40 ms và 160 ms, chỉ mẫu 40 ms thỏa `le="0.1"` và cả hai thỏa `le="0.25"`. Bucket lũy tích nên phép trừ `2 − 1` cho biết có một mẫu thuộc khoảng trên 100 ms đến hết 250 ms. Tổng thời lượng 0,2 giây chia cho 2 lần đo cho trung bình 0,1 giây mỗi lần. `_max` cho biết giá trị lớn nhất còn trong cửa sổ thống kê. Nó có thể giảm theo thời gian, nên đọc nó như Gauge.

### Tìm đúng chuỗi trong ứng dụng Spring Boot

Với Actuator và `io.micrometer:micrometer-registry-prometheus` đã có trong ứng dụng web, mở hai endpoint để đối chiếu trong môi trường thử nghiệm:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
```

Sau khi đã tạo dữ liệu cho meter cần xem, truy vấn tên gốc ở endpoint chẩn đoán và tìm họ metric ở đầu ra thu thập. Ví dụ với bộ nhớ đệm JVM và đường dẫn Actuator mặc định:

```bash
curl -fsS 'http://localhost:8080/actuator/metrics/jvm.buffer.memory.used?tag=id:direct'
curl -fsS 'http://localhost:8080/actuator/prometheus' | grep '^jvm_buffer_memory_used_bytes'
```

Tài liệu API Spring Boot 3.3 có dòng `jvm_buffer_memory_used_bytes{id="direct"} 45056.0`. Đọc dòng đó là vùng đệm `direct` đang dùng 45.056 byte ở lần thu thập mẫu. Giá trị trên ứng dụng đang chạy thay đổi theo trạng thái JVM. Với metric nghiệp vụ, dùng cùng cách đối chiếu và giữ các khóa tag nhất quán cho những meter cùng tên. Nếu thiếu một tổ hợp nhãn, kiểm tra meter đã được đăng ký hay chưa và liệu các khóa tag của nó có khác với các meter cùng tên hay không.

Trong PromQL, chọn đúng chuỗi theo mục tiêu. Ví dụ, trung bình thời gian thanh toán trong 5 phút của kênh web trên các bản sao của một dịch vụ:

```promql
sum(rate(demo_checkout_duration_seconds_sum{job="checkout",payment_channel="web"}[5m]))
/
sum(rate(demo_checkout_duration_seconds_count{job="checkout",payment_channel="web"}[5m]))
```

Lấy `rate` trên từng chuỗi trước khi cộng để xử lý việc bộ đếm đặt lại. Tử số là số giây thời lượng ghi nhận mỗi giây và mẫu số là số lần đo mỗi giây, nên tỷ số là giây mỗi lần đo khi có lưu lượng. Nếu dashboard cần mili giây, nhân toàn bộ tỷ số với 1.000. Nếu mục tiêu là tỷ lệ hoàn tất trong 250 ms, dùng tốc độ tăng của chuỗi `_bucket` có `le="0.25"` ở tử số và giữ tốc độ tăng của `_count` ở mẫu số. Giá trị của `le` trong truy vấn cần khớp với nhãn mà Prometheus lưu.

### Tài liệu tham khảo

- [Spring Boot 3.3 — ví dụ đầu ra endpoint Prometheus](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/prometheus.html)
- [Spring Boot 3.3 — endpoint tra cứu tên và nhãn meter](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/metrics.html)
- [Micrometer 1.13 — tích hợp Prometheus và các kiểu meter](https://docs.micrometer.io/micrometer/reference/1.13/implementations/prometheus.html)
- [Micrometer 1.13.0 — mã nguồn quy tắc đặt tên cho Prometheus](https://github.com/micrometer-metrics/micrometer/blob/v1.13.0/implementations/micrometer-registry-prometheus/src/main/java/io/micrometer/prometheusmetrics/PrometheusNamingConvention.java)
- [Prometheus — tên metric, nhãn và đơn vị](https://prometheus.io/docs/practices/naming/)