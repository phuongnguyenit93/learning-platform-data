# Chu kỳ scrape và thời gian thực hiện phép đo trong ứng dụng

Prometheus thu thập số liệu mỗi 15 giây. Trong khoảng đó, một yêu cầu HTTP có thể hoàn thành sau 80 ms, còn một yêu cầu khác có thể bắt đầu trước lần thu thập và hoàn thành sau lần thu thập. Để đọc đúng biểu đồ, cần tách thời gian ứng dụng đo một công việc, nhịp Prometheus lấy mẫu và thời gian chính lần lấy mẫu đó diễn ra.

| Đại lượng | Đo điều gì | Do đâu quyết định |
| --- | --- | --- |
| Thời lượng của một quan sát | Khoảng từ lúc bắt đầu đến lúc kết thúc phần công việc được đo. | Điểm đặt mã đo. Ví dụ `Timer.Sample` lấy thời điểm bắt đầu từ đồng hồ của registry và ghi thời lượng khi gọi `stop(timer)`. |
| Chu kỳ scrape (`scrape_interval`) | Khoảng cách được lên lịch giữa các lần Prometheus thu thập từ một đích. | Cấu hình máy chủ Prometheus, theo mặc định toàn cục hoặc theo job. |
| Thời lượng một lần scrape (`scrape_duration_seconds`) | Lần thu thập từ đích đã mất bao lâu. | Prometheus tự đo lần thu thập. `scrape_timeout` đặt giới hạn chờ cho lần này. |
| Cửa sổ truy vấn, ví dụ `[1m]` | Khoảng dữ liệu đã lưu mà hàm PromQL dùng tại mỗi thời điểm đánh giá. | Biểu thức truy vấn. |

Với Spring MVC được Spring Boot tự cấu hình, phép đo HTTP phía máy chủ thường mang tên Micrometer `http.server.requests`. `Timer` của ứng dụng cập nhật số lần đo và tổng thời lượng khi quan sát hoàn thành. Khi Prometheus gọi `/actuator/prometheus`, nó đọc các thống kê mà registry đang xuất. Tăng tần suất scrape giúp hệ thống giám sát thấy cập nhật sớm hơn trong điều kiện thu thập thành công. Thời lượng của từng quan sát vẫn do đoạn công việc được đo quyết định.

## Theo dõi một yêu cầu đi qua ranh giới scrape

Giả sử cùng một bản sao và cùng một bộ nhãn, bộ đếm còn nguyên, không có lần khởi động lại. Prometheus lấy mẫu ở giây 0, 15 và 30. Ứng dụng ghi ba yêu cầu sau.

| Yêu cầu | Bắt đầu | Kết thúc | Thời lượng được ghi |
| --- | ---: | ---: | ---: |
| A | 2,00 s | 2,12 s | 120 ms |
| B | 6,00 s | 6,08 s | 80 ms |
| C | 14,00 s | 17,00 s | 3 s |

| Thời điểm scrape | Số lần đo tích lũy | Tổng thời lượng tích lũy | Điều Prometheus đọc được |
| --- | ---: | ---: | --- |
| 0 s | 0 | 0,000 s | Chưa có quan sát nào. |
| 15 s | 2 | 0,200 s | A và B đã được cộng. C đang chạy nên chưa đóng góp vào thống kê của `Timer` cho công việc đã hoàn thành. |
| 30 s | 3 | 3,200 s | Có thêm một quan sát dài 3 giây, đã được ghi khi C hoàn thành ở giây 17. |

Giữa lần đọc ở giây 0 và giây 15, tổng thời lượng tăng 0,200 giây qua hai quan sát. Độ trễ trung bình của hai yêu cầu đó là 0,100 giây. Mốc 15 giây là thời điểm lấy mẫu. Từ hai giá trị tích lũy, Prometheus biết số lượng và tổng thời lượng đã tăng bao nhiêu, nhưng không suy ra riêng từng yêu cầu mất 120 ms hay 80 ms. Histogram nếu được bật cung cấp thêm số quan sát trong các khoảng giá trị, còn dấu thời gian từng yêu cầu cần nguồn dữ liệu chi tiết như dấu vết theo yêu cầu (trace).

### Khi một biến động xảy ra giữa hai lần scrape

- **Bộ đếm tích lũy và tổng thời lượng** giữ phần tăng từ các yêu cầu đã ghi. Cả A và B vẫn xuất hiện trong số liệu tổng hợp dù mỗi yêu cầu bắt đầu và kết thúc giữa hai lần scrape. Nếu tiến trình khởi động lại giữa hai lần lấy mẫu, các cập nhật chưa từng được thu có thể bị mất.
- **Gauge đọc trạng thái hiện tại** cho biết giá trị tại thời điểm được lấy mẫu. Nếu hàng đợi tăng lên 100 mục ở giây 7 rồi về 0 ở giây 9, hai lần scrape ở giây 0 và 15 có thể đều thấy 0.
- **Công việc đang chạy** cần một phép đo phù hợp nếu muốn quan sát trước lúc hoàn thành. Micrometer có `LongTaskTimer` cho số công việc đang chạy và thời gian chúng đã chạy. Nó trả lời câu hỏi khác với `Timer` đếm công việc đã hoàn thành.

## Kiểm chứng bằng Micrometer và đồng hồ mô phỏng

Chương trình sau mô phỏng ba thời điểm đọc trong bảng bằng `SimpleMeterRegistry` ở chế độ tích lũy mặc định. Đồng hồ mô phỏng tiến ngay theo lệnh, nên ví dụ chạy nhanh mà vẫn đo đúng thời lượng theo đồng hồ của registry. Hàm `sampleAt` đọc thống kê trong bộ nhớ để mô phỏng lần scrape.

Lưu tệp `ScrapeVsTimer.java`. Ví dụ dùng Java 17+ và `io.micrometer:micrometer-core:1.13.0` cùng các phụ thuộc lúc chạy.

```java
import io.micrometer.core.instrument.MockClock;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleConfig;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

import java.time.Duration;
import java.util.Locale;
import java.util.concurrent.TimeUnit;

public class ScrapeVsTimer {
    public static void main(String[] args) {
        MockClock clock = new MockClock();
        SimpleMeterRegistry registry = new SimpleMeterRegistry(SimpleConfig.DEFAULT, clock);
        try {
            Timer timer = registry.timer("demo.requests");
            sampleAt(0, timer);

            clock.add(Duration.ofSeconds(2));
            recordRequest(registry, timer, clock, 120);
            clock.add(Duration.ofMillis(3_880));
            recordRequest(registry, timer, clock, 80);

            clock.add(Duration.ofMillis(7_920));
            Timer.Sample inFlight = Timer.start(registry); // t = 14 s
            clock.add(Duration.ofSeconds(1));
            sampleAt(15, timer);

            clock.add(Duration.ofSeconds(2));
            inFlight.stop(timer); // t = 17 s
            clock.add(Duration.ofSeconds(13));
            sampleAt(30, timer);
        } finally {
            registry.close();
        }
    }

    private static void recordRequest(
            SimpleMeterRegistry registry, Timer timer, MockClock clock, long durationMillis) {
        Timer.Sample sample = Timer.start(registry);
        clock.add(Duration.ofMillis(durationMillis));
        sample.stop(timer);
    }

    private static void sampleAt(int seconds, Timer timer) {
        System.out.printf(Locale.ROOT, "t=%ds count=%d total=%.3fs%n",
                seconds, timer.count(), timer.totalTime(TimeUnit.SECONDS));
    }
}
```

Trên Bash, đặt `MICROMETER_CP` thành classpath chứa các JAR lúc chạy mà Maven hoặc Gradle giải quyết cho dependency trên.

```bash
javac --release 17 -cp "$MICROMETER_CP" ScrapeVsTimer.java
java -cp ".:$MICROMETER_CP" ScrapeVsTimer
```

Kết quả với Micrometer 1.13.0.

```text
t=0s count=0 total=0.000s
t=15s count=2 total=0.200s
t=30s count=3 total=3.200s
```

## Đặt lịch scrape và đọc kết quả trong Prometheus

Giả sử ứng dụng đã xuất `/actuator/prometheus` ở cổng 8080 và Prometheus chạy trực tiếp trên cùng máy. Trong `prometheus.yml`, có thể cấu hình một job như sau.

```yaml
scrape_configs:
  - job_name: spring-app
    scrape_interval: 15s
    scrape_timeout: 5s
    metrics_path: /actuator/prometheus
    static_configs:
      - targets: ['localhost:8080']
```

Ở đây Prometheus lên lịch thu thập mỗi 15 giây và giới hạn mỗi lần chờ thu thập ở 5 giây. Giới hạn này áp dụng cho lần thu thập số liệu. Một yêu cầu nghiệp vụ vẫn có thể chạy lâu hơn 5 giây và được ghi nhận sau khi hoàn thành. Khi cần phân biệt ứng dụng xử lý chậm với đích thu thập trả lời chậm, xem độ trễ HTTP của ứng dụng cùng `up{job="spring-app"}` và `scrape_duration_seconds{job="spring-app"}`.

Với tên chuỗi thông thường do Micrometer Prometheus xuất cho `http.server.requests`, truy vấn sau ước lượng thời lượng trung bình tính bằng giây trên toàn job trong cửa sổ một phút.

```promql
sum(rate(http_server_requests_seconds_sum{job="spring-app"}[1m]))
/
sum(rate(http_server_requests_seconds_count{job="spring-app"}[1m]))
```

Tử số ước lượng số giây xử lý tích lũy tăng mỗi giây. Mẫu số ước lượng số yêu cầu hoàn thành mỗi giây. Tính `rate()` trên từng chuỗi trước khi gộp để xử lý bộ đếm đặt lại khi một bản sao khởi động lại. Khi không có quan sát trong cửa sổ, mẫu số bằng 0 nếu các chuỗi vẫn có dữ liệu, và phép chia không cho một độ trễ trung bình có ý nghĩa. Khi thiếu mẫu scrape, truy vấn có thể không có kết quả. Hãy chọn cửa sổ đủ chứa nhiều lần lấy mẫu thành công cho chu kỳ thu thập thực tế.

## Tài liệu tham khảo

- [Spring Boot 3.3 — Metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html)
- [Micrometer 1.13 — Timers](https://docs.micrometer.io/micrometer/reference/1.13/concepts/timers.html)
- [Micrometer 1.13 — Gauges](https://docs.micrometer.io/micrometer/reference/1.13/concepts/gauges.html)
- [Micrometer 1.13 — Long Task Timers](https://docs.micrometer.io/micrometer/reference/1.13/concepts/long-task-timers.html)
- [Prometheus — Cấu hình thu thập](https://prometheus.io/docs/prometheus/latest/configuration/configuration/#scrape_config)
- [Prometheus — Job, đích và chỉ số của lần scrape](https://prometheus.io/docs/concepts/jobs_instances/)
- [Prometheus — Hàm rate](https://prometheus.io/docs/prometheus/latest/querying/functions/#rate)
