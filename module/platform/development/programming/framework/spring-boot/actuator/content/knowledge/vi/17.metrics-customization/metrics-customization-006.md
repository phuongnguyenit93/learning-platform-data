# Cấu hình histogram, percentile và ranh giới mục tiêu mức dịch vụ

Một dịch vụ thanh toán có độ trễ trung bình 180 ms vẫn có thể bỏ lỡ mục tiêu **ít nhất 95% lượt thanh toán hoàn tất trong 250 ms hoặc ít hơn**. Trung bình cho biết thời gian bình quân trên mỗi lượt. Để biết có bao nhiêu lượt đạt ngưỡng, cần đếm các quan sát đến 250 ms. Để biết độ trễ ở đuôi phân phối, có thể xem p95 hoặc p99.

## Ba cách biểu diễn phân phối

| Cấu hình Micrometer trong Spring Boot | Dữ liệu thu được | Câu hỏi phù hợp |
| --- | --- | --- |
| `percentiles» | Phân vị do ứng dụng ước lượng cho từng bộ tên meter và tag. `0.95» là p95, giá trị quanh vị trí 95% của phân phối đã sắp xếp. | p95 của riêng một bản sao hoặc một bộ tag là bao nhiêu? |
| `percentiles-histogram» | Các bộ đếm theo ngưỡng do Micrometer chọn. Hệ thống giám sát có thể cộng các bộ đếm tương ứng rồi ước lượng phân vị của cả nhóm. | p95 của tất cả bản sao phục vụ thanh toán là bao nhiêu? |
| `slo» | Bộ đếm tích lũy tại các ranh giới cụ thể, chẳng hạn `250ms». Khi bật histogram phân vị trên Prometheus, các ranh giới này được thêm vào tập bucket. | Có bao nhiêu lượt hoàn tất trong 250 ms hoặc ít hơn? |

Một **bucket tích lũy** có nhãn `le="0.25"» đếm mọi quan sát có thời lượng **≤ 0,25 giây**. Vì vậy, một lượt mất đúng 100 ms được tính vào cả bucket 100 ms lẫn bucket 250 ms. Lấy số đếm ở 250 ms trừ số đếm ở 100 ms sẽ cho số lượt trong khoảng (100 ms, 250 ms]. Bucket `+Inf» bao gồm toàn bộ quan sát và có cùng số đếm với `_count» trong một histogram Prometheus kiểu cổ điển.

Ngưỡng `250ms» chỉ tạo ranh giới đo. Mục tiêu mức dịch vụ (SLO) cần thêm **tỷ lệ đích**, **tập yêu cầu đủ điều kiện** và **cửa sổ đánh giá**. Ví dụ này coi mỗi lượt do timer ghi nhận là đủ điều kiện. Nếu mục tiêu thực tế chỉ coi giao dịch thành công và nhanh là đạt, tử số phải chọn cả trạng thái thành công lẫn bucket độ trễ. Mẫu số phải bám theo định nghĩa lượt đủ điều kiện.

## Cấu hình Spring Boot Actuator cho Prometheus

Ví dụ dùng Spring Boot 3.3, Micrometer 1.13 và histogram Prometheus kiểu cổ điển. Trong một ứng dụng Spring Boot Web, dùng `spring-boot-starter-actuator» và `io.micrometer:micrometer-registry-prometheus» theo bộ quản lý phiên bản của Spring Boot. Với máy thử cục bộ, thêm các dòng sau vào `application.properties»:

~~~properties
management.endpoints.web.exposure.include=health,metrics,prometheus
management.metrics.distribution.percentiles-histogram.checkout.duration=true
management.metrics.distribution.minimum-expected-value.checkout.duration=5ms
management.metrics.distribution.maximum-expected-value.checkout.duration=2s
management.metrics.distribution.slo.checkout.duration=100ms,250ms,500ms
~~~

- `checkout.duration» là tên `Timer» trong Micrometer. Dùng tên đó trong cấu hình và khi xem `/actuator/metrics/checkout.duration». Khi xuất sang Prometheus, timer có tên cơ sở `checkout_duration_seconds» và bucket dùng đơn vị giây.
- Spring Boot áp dụng từng thuộc tính phân phối theo tiền tố tên meter và ưu tiên tiền tố khớp dài nhất. Với timer, viết rõ `ms» hoặc `s». Với `DistributionSummary», ranh giới là số theo đơn vị của đại lượng ghi nhận, chẳng hạn byte.
- `minimum-expected-value» và `maximum-expected-value» giới hạn phạm vi sinh bucket tự động, giúp kiểm soát số chuỗi thời gian. Chúng không loại bỏ mẫu nằm ngoài phạm vi; mẫu vượt ranh giới hữu hạn cao nhất vẫn xuất hiện trong `+Inf» và `_count». Đặt phạm vi quá hẹp làm mất khả năng phân biệt các giá trị ở đuôi khi tính phân vị.
- Nếu chỉ theo dõi tỷ lệ tại các ngưỡng đã chốt, đặt `percentiles-histogram.checkout.duration=false» và giữ `slo» để chỉ xuất các bucket hữu hạn đã khai báo. Nếu cần thử riêng phân vị do ứng dụng tính, tắt histogram, bỏ `slo» cho meter và đặt `management.metrics.distribution.percentiles.checkout.duration=0.95,0.99». Với registry Prometheus trong ví dụ, khi xuất histogram, meter được biểu diễn bằng bucket; tính phân vị bằng truy vấn trên bucket.

Với độ trễ HTTP tự động của Actuator, có thể áp dụng cùng cách cấu hình cho tên meter mặc định `http.server.requests». Khi truy vấn, chọn tập tuyến và trạng thái phù hợp với định nghĩa mục tiêu. Trong môi trường triển khai, cấu hình quyền truy cập endpoint theo phạm vi của hệ thống giám sát.

## Thử với năm quan sát có kết quả kiểm tra được

Trong ứng dụng thử đã có lớp `@SpringBootApplication», đặt lớp dưới đây cùng package với lớp khởi động hoặc trong package con mà Spring quét. Đổi `package example;» theo package của ứng dụng. Khi chạy ứng dụng, `ApplicationRunner» ghi năm thời lượng giả lập vào `Timer» để kết quả có thể lặp lại mà không phụ thuộc tốc độ mạng hay `Thread.sleep».

~~~java
package example;

import java.time.Duration;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class CheckoutMetricsSample {
    @Bean
    ApplicationRunner recordCheckoutSamples(MeterRegistry registry) {
        return args -> {
            Timer timer = registry.timer("checkout.duration");
            for (long millis : new long[] {80, 100, 250, 400, 700}) {
                timer.record(Duration.ofMillis(millis));
            }
        };
    }
}
~~~

Sau khi ứng dụng chạy ở cổng 8080, lấy bản ghi thu thập:

~~~bash
curl -fsS http://localhost:8080/actuator/prometheus
~~~

Tìm các dòng sau. Histogram còn có bucket tự động, nên đây chỉ là phần cần đối chiếu. Thứ tự dòng và cách biểu diễn số có thể khác.

~~~text
checkout_duration_seconds_bucket{le="0.1"} 2
checkout_duration_seconds_bucket{le="0.25"} 3
checkout_duration_seconds_bucket{le="0.5"} 4
checkout_duration_seconds_bucket{le="+Inf"} 5
checkout_duration_seconds_count 5
checkout_duration_seconds_sum 1.53
~~~

Có **3/5 = 60%** lượt hoàn tất trong 250 ms hoặc ít hơn. Hai mẫu ở đúng ranh giới 100 ms và 250 ms xác nhận quy tắc `≤». Năm mẫu đủ để kiểm tra cơ chế đếm. Đánh giá phân vị hoặc SLO cần nhiều quan sát hơn.

## Tính p95 và tỷ lệ đạt SLO trên nhiều bản sao

Giả sử các bản sao thuộc cùng một Prometheus job `checkout», xuất cùng tập ranh giới bucket và có lưu lượng trong cửa sổ đo. Để xem p95 của toàn bộ job trong 5 phút gần nhất:

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(checkout_duration_seconds_bucket{job="checkout"}[5m])
  )
)
~~~

Dùng `rate» trên từng chuỗi trước khi cộng để Prometheus xử lý lần đặt lại bộ đếm khi ứng dụng khởi động lại. Giữ nhãn `le» để hàm biết ranh giới từng bucket. Kết quả tính bằng giây và là **ước lượng**, vì Prometheus nội suy trong bucket hữu hạn chứa phân vị. Cần cùng một bộ ranh giới giữa các bản sao được gộp. Khi đổi ranh giới theo từng đợt triển khai, kiểm tra các phiên bản đã đồng nhất trước khi diễn giải p95 tổng hợp.

Để tính tỷ lệ đạt theo ranh giới đã chọn, lấy tốc độ tăng số lượt `≤ 250 ms» chia cho tốc độ tăng tổng số lượt, với cùng bộ lọc và cửa sổ:

~~~promql
sum(rate(checkout_duration_seconds_bucket{job="checkout", le="0.25"}[5m]))
/
sum(rate(checkout_duration_seconds_count{job="checkout"}[5m]))
~~~

Kết quả là tỷ lệ từ 0 đến 1. Bucket ở đúng ranh giới cho biết số lượt đạt. `rate` ước lượng tốc độ tăng của số đếm từ các lần thu thập trong cửa sổ. Nếu mẫu số bằng 0 hoặc chưa đủ mẫu thu thập, hiển thị trạng thái thiếu dữ liệu. Cửa sổ 5 phút phù hợp để quan sát nhanh; để đánh giá SLO theo kỳ, dùng cửa sổ mà mục tiêu quy định và so sánh tỷ lệ với `0.95».

Chẳng hạn, một bản sao có 90/100 lượt đạt ngưỡng và bản sao khác có 10/10. Cả nhóm đạt 100/110 ≈ **90,9%**. Trung bình hai tỷ lệ cho 95% vì cách tính đó gán cùng trọng số cho hai bản sao dù số lượt khác nhau. Tương tự, trung bình các giá trị p95 do từng ứng dụng xuất ra không tái lập p95 của tập quan sát gộp.

## Kiểm tra chi phí và lỗi cấu hình

- **Không thấy bucket**. Kiểm tra registry Prometheus, quyền truy cập endpoint, tên meter và việc timer đã ghi quan sát. Dùng `/actuator/metrics/checkout.duration» để xác nhận meter, rồi kiểm tra bucket và đơn vị ở `/actuator/prometheus».
- **Không thấy chuỗi ngưỡng mong muốn trong truy vấn**. Kiểm tra nhãn `le» thực tế trong Prometheus. `250ms» trong cấu hình timer tương ứng với 0,25 giây khi xuất; truy vấn ví dụ dùng `le="0.25"».
- **Số chuỗi thời gian tăng nhanh**. Mỗi bucket tạo thêm một chuỗi cho mỗi tổ hợp nhãn. Ưu tiên bật theo nhóm meter cần đo, dùng nhãn có số giá trị hữu hạn và tránh mã giao dịch trong tag. Kiểm tra mức phân giải của bucket quanh vùng quan tâm trước khi thu hẹp phạm vi hoặc chuyển sang chỉ xuất các ngưỡng SLO.

### Tài liệu tham khảo

- [Spring Boot 3.3 – Cấu hình metrics theo meter](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html)
- [Micrometer 1.13 – Histogram và percentile](https://docs.micrometer.io/micrometer/reference/1.13/concepts/histogram-quantiles.html)
- [Prometheus – Histogram và summary](https://prometheus.io/docs/practices/histograms/)