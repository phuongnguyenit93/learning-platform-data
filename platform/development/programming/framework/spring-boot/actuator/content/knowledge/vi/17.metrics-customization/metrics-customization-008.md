## Giới hạn miền giá trị để kiểm soát số bucket và chi phí lưu trữ

Một `Timer` đo thời gian thanh toán thường thấy kết quả từ vài chục đến vài trăm mili giây. Nếu biểu đồ phân bố (histogram) xuất thêm nhiều ngưỡng ở những vùng ít có ích cho truy vấn, Prometheus vẫn thu thập chuỗi thời gian tương ứng ở mỗi lần quét. `minimum-expected-value` và `maximum-expected-value` cho phép chọn miền ngưỡng hữu ích cho một đồng hồ đo (meter). Đổi lại, vùng dưới ngưỡng thấp nhất và vùng trên ngưỡng hữu hạn cao nhất có ít thông tin hơn về hình dạng phân bố.

### Miền giá trị kỳ vọng giới hạn điều gì?

Khi bật `percentiles-histogram` trên một bộ đăng ký hỗ trợ histogram có thể tổng hợp, Micrometer lấy các mốc tự sinh nằm trong miền kỳ vọng, thêm hai đầu mút và hợp nhất với các mốc mục tiêu mức dịch vụ (`slo`). Mốc trùng nhau chỉ xuất hiện một lần. `slo` có thể bổ sung mốc **ngoài miền kỳ vọng**, nên khi dự trù số bucket cần tính cả các mốc này. Nếu chỉ xuất bucket theo `slo` và tắt `percentiles-histogram`, hai đầu mút kỳ vọng sẽ không tự tạo thêm mốc bucket.

Với histogram cổ điển của Prometheus, nhãn `le` là ngưỡng trên **bao gồm cả giá trị bằng ngưỡng**. Các bộ đếm là lũy tích. Một lần đo 80 ms được tính vào `le="0.3"`, `le="1.0"` và `le="+Inf"` vì nó nằm dưới cả ba mốc. Dữ liệu quan sát vẫn được ghi theo giá trị thật:

- Lần đo 2 ms vẫn góp vào bucket `le="0.01"` nếu 10 ms là mốc hữu hạn đầu tiên. Ta đếm được số lần đo từ 10 ms trở xuống nhưng thiếu chi tiết bên trong vùng này.
- Lần đo 2,3 s vẫn góp vào `_count`, `_sum` và `le="+Inf"` nếu mốc hữu hạn cao nhất là 1 s. Nó không góp vào `le="1.0"`. Hiệu giữa `+Inf` và mốc hữu hạn cuối cho biết có bao nhiêu lần đo vượt mốc đó, nhưng các bucket không cho biết chúng chậm hơn bao nhiêu.

Nếu nhiều lần đo rơi vào bucket cao nhất `+Inf` đến mức p99 nằm trong bucket ấy, `histogram_quantile` của Prometheus trả về mốc hữu hạn cao nhất. Dashboard có thể hiện p99 bằng 1 s dù p99 thực sự nằm trên 1 s. Với một ngưỡng vận hành cụ thể như 300 ms, giữ bucket `le="0.3"` cho phép đếm trực tiếp số lần đo đạt ngưỡng, không cần nội suy từ các bucket lân cận.

### Cấu hình trong Spring Boot Actuator

Ví dụ sau áp dụng cho một ứng dụng web Spring Boot 3.3 đã có `spring-boot-starter-actuator`, `micrometer-registry-prometheus` và đăng ký một `Timer` tên `demo.checkout.duration`. Đoạn YAML mở endpoint Prometheus để kiểm tra trong môi trường thử nghiệm.

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,prometheus
  metrics:
    distribution:
      percentiles-histogram:
        "[demo.checkout.duration]": true
      minimum-expected-value:
        "[demo.checkout.duration]": 10ms
      maximum-expected-value:
        "[demo.checkout.duration]": 1s
      slo:
        "[demo.checkout.duration]": 300ms
```

Dùng tên meter gốc trong Micrometer ở khóa cấu hình. Trong Prometheus, `Timer` ví dụ xuất các dòng bắt đầu bằng `demo_checkout_duration_seconds_`, với các mốc `10ms`, `300ms` và `1s` được biểu diễn theo giây. Cấu hình Spring Boot tra cứu theo tên hoặc tiền tố theo từng đoạn phân tách bằng dấu chấm, ưu tiên khóa cụ thể hơn cho từng thuộc tính. Chọn tiền tố đủ hẹp để tránh bật histogram cho nhiều meter ngoài dự kiến. Với `DistributionSummary`, đặt mốc bằng số theo đơn vị của dữ liệu ghi nhận (sau khi nhân hệ số `scale`, nếu có), chẳng hạn `512` và `65536` cho kích thước tính bằng byte.

Nếu dashboard chỉ cần tỷ lệ thanh toán trong 300 ms, có thể đặt `percentiles-histogram` thành `false` và giữ mốc `300ms` trong `slo` cho meter này. Khi đó, histogram cổ điển vẫn có mốc 300 ms và `+Inf`. Chỉ một mốc hữu hạn như vậy cho rất ít thông tin để ước lượng p95 hoặc p99.

### Thí nghiệm với cùng năm lần đo

Lưu chương trình sau thành `BucketRangeDemo.java`. Ví dụ dùng trực tiếp bộ đếm histogram trong Micrometer Core 1.13.0 để quan sát các mốc hữu hạn trước khi xuất sang Prometheus. Các mốc đưa vào `DistributionStatisticConfig` trong chương trình dùng nano giây vì đồng hồ đo là `Timer`.

```java
import io.micrometer.core.instrument.Clock;
import io.micrometer.core.instrument.Meter;
import io.micrometer.core.instrument.Tags;
import io.micrometer.core.instrument.cumulative.CumulativeTimer;
import io.micrometer.core.instrument.distribution.CountAtBucket;
import io.micrometer.core.instrument.distribution.DistributionStatisticConfig;
import io.micrometer.core.instrument.distribution.pause.NoPauseDetector;

import java.time.Duration;
import java.util.Arrays;

import static java.util.concurrent.TimeUnit.MILLISECONDS;

public class BucketRangeDemo {
    public static void main(String[] args) {
        run("wide", Duration.ofMillis(1), Duration.ofSeconds(30));
        run("narrow", Duration.ofMillis(10), Duration.ofSeconds(1));
    }

    private static void run(String label, Duration min, Duration max) {
        var config = DistributionStatisticConfig.builder()
                .percentilesHistogram(true)
                .minimumExpectedValue((double) min.toNanos())
                .maximumExpectedValue((double) max.toNanos())
                .serviceLevelObjectives((double) Duration.ofMillis(300).toNanos())
                .build()
                .merge(DistributionStatisticConfig.DEFAULT);
        var id = new Meter.Id("demo.checkout.duration", Tags.empty(),
                null, null, Meter.Type.TIMER);
        var timer = new CumulativeTimer(
                id, Clock.SYSTEM, config, new NoPauseDetector(), MILLISECONDS, true);

        for (long sample : new long[] {2, 80, 220, 900, 2300}) {
            timer.record(sample, MILLISECONDS);
        }

        var snapshot = timer.takeSnapshot();
        var buckets = snapshot.histogramCounts();
        System.out.printf("%s buckets=%d count=%d totalMs=%d le300=%d%n",
                label, buckets.length, snapshot.count(),
                (long) snapshot.total(MILLISECONDS), countAt(buckets, 300));
        if ("narrow".equals(label)) {
            System.out.printf("narrow le10=%d le1000=%d above1000=%d%n",
                    countAt(buckets, 10), countAt(buckets, 1000),
                    snapshot.count() - countAt(buckets, 1000));
        }
    }

    private static long countAt(CountAtBucket[] buckets, long millis) {
        double nanos = Duration.ofMillis(millis).toNanos();
        return (long) Arrays.stream(buckets)
                .filter(bucket -> bucket.bucket() == nanos)
                .findFirst()
                .orElseThrow()
                .count();
    }
}
```

Dùng JDK 17 trở lên. Đặt `CP` là classpath chứa `io.micrometer:micrometer-core:1.13.0` và các thư viện phụ thuộc lúc chạy do Maven hoặc Gradle phân giải. Từ thư mục chứa tệp nguồn, biên dịch và chạy bằng Bash với các lệnh sau. Trên PowerShell, dùng `$env:CP` và dấu `;` để phân tách các mục trong classpath.

```bash
javac -cp "$CP" BucketRangeDemo.java
java -cp ".:$CP" BucketRangeDemo
```

Kết quả với năm lần đo 2, 80, 220, 900 và 2.300 ms:

```text
wide buckets=69 count=5 totalMs=3502 le300=3
narrow buckets=34 count=5 totalMs=3502 le300=3
narrow le10=1 le1000=4 above1000=1
```

Thu hẹp miền từ 1 ms–30 s xuống 10 ms–1 s làm số bucket hữu hạn giảm từ 69 xuống 34, còn số lần đo và tổng thời gian vẫn lần lượt là 5 và 3.502 ms. Cả hai miền đều đếm được 3/5 lần đo đạt ngưỡng 300 ms. Trong miền hẹp, hiệu `5 − 4 = 1` cho biết có một lần đo vượt 1 s. Khi xuất sang Prometheus, 34 bucket hữu hạn trong thí nghiệm tương ứng với 35 dòng `_bucket` nếu tính cả `+Inf`.

### Ước lượng chi phí và chọn giới hạn

Với histogram cổ điển có **B mốc hữu hạn**, mỗi bộ nhãn của meter trên một đích thu thập tạo **B + 3** chuỗi cho histogram: B chuỗi mốc hữu hạn, một chuỗi `+Inf`, một `_count` và một `_sum`. Tính riêng chuỗi bổ sung nếu bộ xuất còn công bố số đo như `_max`. Ví dụ, 20 tổ hợp nhãn thực tế trên mỗi đích và 15 đích tạo 300 bộ nhãn sau khi tính cả nhãn đích. Giảm từ 69 xuống 34 mốc hữu hạn giúp giảm `(69 − 34) × 300 = 10.500` chuỗi đang thu thập cho meter đó. Với cùng chu kỳ thu thập, số mẫu ghi vào hệ thống mỗi chu kỳ cũng giảm tương ứng. Mức tiết kiệm tính theo byte còn phụ thuộc vào thời gian lưu, cơ chế nén và hệ thống lưu trữ. Số mốc và số tổ hợp nhãn là hai yếu tố riêng biệt. Thu hẹp miền không làm giảm số tổ hợp nhãn.

1. **Chọn mốc cần trả lời.** Dựa vào dữ liệu trong giờ bình thường lẫn lúc tải cao, ngưỡng cảnh báo, mục tiêu mức dịch vụ và thời gian chờ tối đa. Đặt cận thấp đủ để phân biệt vùng phản hồi nhanh có ý nghĩa. Đặt cận cao đủ để quan sát vùng chậm mà dashboard cần phân biệt. Giữ mốc SLO rõ ràng bằng `slo`.
2. **Đếm trước và sau trên cùng tải, cùng bộ nhãn.** Đọc `/actuator/prometheus` trên một đích thử nghiệm, lọc `demo_checkout_duration_seconds_bucket` và đếm số dòng cho cùng một bộ nhãn. Kiểm tra `+Inf`, `_count`, `_sum` và mốc 300 ms với dữ liệu đã biết. Endpoint `/actuator/metrics/demo.checkout.duration` hữu ích để xem meter nhưng không liệt kê các dòng bucket Prometheus.
3. **Kiểm tra vùng đuôi bằng chênh lệch số lần đo.** Lấy tốc độ tăng của bucket `+Inf` trừ tốc độ tăng của bucket hữu hạn cuối để biết số lần vượt mốc đó mỗi giây. Chia chênh lệch cho tốc độ tăng của `_count` để ra tỷ lệ khi có lưu lượng. Nếu tỷ lệ vượt 1 s thường lớn hơn 1% và p99 là chỉ số vận hành, cần mốc hữu hạn cao hơn để p99 có thể phân biệt các lần đo chậm ấy.
4. **Tổng hợp các bản sao dùng cùng tập mốc.** Khi đổi cấu hình cuốn chiếu, mỗi mốc có thể được báo cáo bởi một tập bản sao khác nhau. Chỉ gộp histogram của các bản sao có cùng tập mốc. Đánh giá p95 hoặc p99 sau khi cấu hình đã đồng nhất, hoặc tách hai tập bản sao trong lúc so sánh.

Ví dụ truy vấn tỷ lệ lần thanh toán hoàn tất trong 300 ms trên các bản sao của cùng một ứng dụng. Lấy `rate` cho từng chuỗi trước khi cộng để xử lý việc bộ đếm đặt lại khi ứng dụng khởi động lại. Dùng đúng giá trị nhãn `le` mà Prometheus lưu cho mốc 0,3 s.

```promql
sum(rate(demo_checkout_duration_seconds_bucket{job="checkout",le="0.3"}[5m]))
/
sum(rate(demo_checkout_duration_seconds_count{job="checkout"}[5m]))
```

### Tài liệu tham khảo

- [Spring Boot 3.3 Actuator — cấu hình theo meter](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html#actuator.metrics.customizing.per-meter-properties)
- [Micrometer 1.13.0 — cách ghép các mốc histogram và SLO](https://github.com/micrometer-metrics/micrometer/blob/v1.13.0/micrometer-core/src/main/java/io/micrometer/core/instrument/distribution/DistributionStatisticConfig.java)
- [Prometheus — histogram cổ điển và cách tính phân vị](https://prometheus.io/docs/practices/histograms/)