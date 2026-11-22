# Ước lượng độ trễ phân vị từ histogram và chọn bucket

Khi biểu đồ báo p95 là 416 ms, đó có thể là kết quả nội suy trong một bucket rộng. Cùng lượng truy cập và cùng độ trễ thực tế, đặt thêm ngưỡng quanh mốc 300 ms có thể đưa ước lượng về gần 292 ms. Sự khác biệt nằm ở mức chi tiết mà histogram giữ lại.

Các ví dụ dưới đây dùng histogram cổ điển (classic histogram) của Prometheus cho `Timer` đo thời lượng HTTP trong Spring Boot.

## Histogram giữ lại thông tin gì?

Mỗi chuỗi `_bucket` có nhãn `le` cho giới hạn trên, tính cả điểm biên. Ví dụ `le="0.3"` đếm các yêu cầu hoàn thành trong tối đa 0,3 giây. Các bucket là **tích lũy theo ngưỡng**. Yêu cầu 80 ms được tính trong cả bucket 100 ms và 300 ms. Lấy hiệu giữa hai bộ đếm này cho biết số quan sát trong khoảng (100 ms, 300 ms].

Bucket `le="+Inf"` chứa tổng số quan sát, bằng `_count` của cùng tổ hợp nhãn. Các chuỗi này cũng **tích lũy theo thời gian** trong quá trình ứng dụng chạy. Để phân tích một cửa sổ, Prometheus có thể dùng `rate()` để ước lượng tốc độ tăng của từng bộ đếm trong cửa sổ đó.

## Tính p95 từ hai ngưỡng bao quanh

Với tổng số quan sát `N`, hàm `histogram_quantile(0.95, …)` tìm bucket đầu tiên có số đếm tích lũy chạm mốc `0,95 × N`. Gọi `L` và `U` là ngưỡng dưới và trên của bucket hữu hạn chứa mốc đó. `C(L)` và `C(U)` là các số đếm tích lũy tương ứng. Hàm nội suy tuyến tính, tương đương giả định các quan sát trải đều trong khoảng.

```text
p95 ≈ L + (U − L) × (0,95 × N − C(L)) / (C(U) − C(L))
```

Với độ trễ không âm và mốc nằm trong bucket đầu tiên có ngưỡng dương, Prometheus lấy 0 làm giới hạn dưới. Khi p95 rơi vào bucket `+Inf`, hàm trả về ngưỡng hữu hạn cao nhất. Nếu biểu đồ thường dừng ở đúng ngưỡng đó, hãy kiểm tra tỷ lệ yêu cầu vượt ngưỡng để biết histogram còn đủ độ phân giải ở phần đuôi hay không.

## Cùng một phân bố, hai bộ ngưỡng

Giả sử có 100 yêu cầu trong cửa sổ. Trong đó có 80 yêu cầu mất 80 ms, 10 yêu cầu mất 240 ms, 6 yêu cầu mất 280 ms, 3 yêu cầu mất 420 ms và 1 yêu cầu mất 900 ms. Sắp xếp dữ liệu gốc theo độ trễ thì quan sát thứ 95 là 280 ms. Đây là giá trị đối chiếu theo cách lấy hạng gần nhất.

| Ngưỡng trên | Bộ ngưỡng thưa | Bộ ngưỡng dày quanh 300 ms |
| --- | ---: | ---: |
| 100 ms | 80 | 80 |
| 250 ms | — | 90 |
| 300 ms | — | 96 |
| 500 ms | 99 | 99 |
| 1.000 ms | 100 | 100 |
| `+Inf` | 100 | 100 |

Dấu gạch ngang biểu thị ngưỡng không được cấu hình. Các cột là số đếm tích lũy theo ngưỡng của quan sát trong cửa sổ, dùng để tính tay.

- **Bộ ngưỡng thưa.** Mốc 95 rơi trong (100 ms, 500 ms]. Trong khoảng có 19 yêu cầu, cần đi thêm 15 vị trí kể từ mốc 100 ms. Nội suy `100 + 400 × 15 / 19 ≈ 415,79 ms`.
- **Bộ ngưỡng dày.** Mốc 95 rơi trong (250 ms, 300 ms]. Trong khoảng có 6 yêu cầu, cần đi thêm 5 vị trí kể từ mốc 250 ms. Nội suy `250 + 50 × 5 / 6 ≈ 291,67 ms`.

Thu hẹp bucket chứa p95 làm hẹp khoảng có thể chứa phân vị thật, từ 400 ms xuống còn 50 ms trong ví dụ này. Mức sai lệch cụ thể vẫn phụ thuộc cách các quan sát phân bố bên trong khoảng. Trong dữ liệu gốc, cả 6 yêu cầu giữa hai ngưỡng 250 và 300 ms đều nằm tại 280 ms.

Với mục tiêu «ít nhất 95% yêu cầu hoàn thành trong 300 ms», bucket 300 ms còn trả lời trực tiếp câu hỏi về tỷ lệ. Có 96 yêu cầu đạt ngưỡng trên tổng số 100, tức 96%. Khi ngưỡng mục tiêu trùng với biên bucket, phép chia số đếm này không cần giả định về phân bố bên trong bucket.

## Cấu hình và truy vấn trên Spring Boot

Với ứng dụng web dùng Actuator và `io.micrometer:micrometer-registry-prometheus`, có thể tái tạo bộ ngưỡng hữu hạn của ví dụ trong `application.properties`. Cấu hình dưới đây chọn các biên tường minh cho `http.server.requests` và tắt bộ biên sinh tự động cho meter đó.

```properties
management.endpoints.web.exposure.include=health,prometheus
management.metrics.distribution.percentiles-histogram.http.server.requests=false
management.metrics.distribution.slo.http.server.requests=100ms,250ms,300ms,500ms,1s
```

Nếu muốn dùng bộ ngưỡng do Micrometer sinh, bật `percentiles-histogram` và dùng `minimum-expected-value` cùng `maximum-expected-value` để giới hạn dải biên tự sinh. Giữ `slo` cho các ngưỡng nghiệp vụ cần xuất chính xác. Các giá trị kỳ vọng dùng để chọn biên histogram. Quan sát vượt biên hữu hạn cao nhất vẫn đóng góp vào `+Inf` và tổng số quan sát.

Sau khi tạo lưu lượng và cho Prometheus scrape, kiểm tra các nhãn `le` trong dữ liệu thực tế. Giả sử job `orders` scrape các bản sao của cùng dịch vụ và `uri="/orders"` là nhãn đường dẫn được xuất. Truy vấn sau ước lượng p95 trong 5 phút.

```promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(http_server_requests_seconds_bucket{job="orders", method="GET", uri="/orders"}[5m])
  )
)
```

`rate()` chạy trên từng chuỗi trước để Prometheus xử lý lần đặt lại bộ đếm của từng bản sao. `sum by (le)` cộng các bucket có cùng giới hạn trên rồi mới tính một p95 chung. Giữ thêm `uri` trong mệnh đề `by` khi cần một kết quả cho mỗi đường dẫn và đã bỏ bộ lọc đường dẫn cố định. Với bộ số đếm hoặc tốc độ đều tỉ lệ với bảng trên, kết quả p95 của bộ ngưỡng dày là khoảng 0,292 giây.

Truy vấn tỷ lệ hoàn thành trong 300 ms dùng bucket tương ứng chia cho tổng số yêu cầu. Cùng phạm vi nhãn và cửa sổ ở tử và mẫu để hai vế nói về cùng một tập yêu cầu.

```promql
sum(rate(http_server_requests_seconds_bucket{job="orders", method="GET", uri="/orders", le="0.3"}[5m]))
/
sum(rate(http_server_requests_seconds_count{job="orders", method="GET", uri="/orders"}[5m]))
```

Truy vấn trả một tỷ lệ từ 0 đến 1 khi có dữ liệu và mẫu số dương. Kiểm tra nhãn biên thực tế trong Prometheus trước khi dùng điều kiện `le="0.3"`. Khi chưa có quan sát, xem thêm số lượng yêu cầu và trạng thái scrape trước khi diễn giải biểu đồ. Histogram cổ điển thiếu bucket `+Inf` sẽ khiến `histogram_quantile()` trả `NaN` cho histogram đó.

## Chọn bucket cho dịch vụ thực tế

1. **Bắt đầu từ ngưỡng cần ra quyết định.** Nếu SLO đặt ở 300 ms, cấu hình biên đúng 300 ms. Nếu cần biết p95 còn cách ngưỡng bao xa, đặt thêm biên hai phía, chẳng hạn 250 ms và 350 ms. Nếu chỉ đo tỷ lệ đạt 300 ms thì riêng biên 300 ms đã cung cấp tử số.
2. **Dành độ phân giải cho vùng quan trọng.** Quan sát phạm vi độ trễ dưới tải đại diện. Đặt biên dày hơn quanh phân vị đang theo dõi, giãn khoảng ở vùng ít ảnh hưởng đến quyết định. Chọn biên hữu hạn cao nhất đủ bao phủ phần đuôi cần phân tích. Nếu hơn 5% yêu cầu vượt biên này thì p95 rơi vào `+Inf` và giá trị hiển thị bị giới hạn bởi biên hữu hạn cao nhất.
3. **Tính chi phí theo tổ hợp nhãn.** Với 5 biên hữu hạn và `+Inf`, mỗi tổ hợp nhãn có 6 chuỗi `_bucket`, chưa tính `_count`, `_sum` và các thống kê khác. Nếu có 20 tổ hợp nhãn ở mỗi đích và 4 đích, riêng bucket đã tạo 480 chuỗi. Thêm biên khi mức phân giải cao hơn thực sự thay đổi cách đọc số liệu.
4. **Giữ cùng bộ biên cho các chuỗi đem gộp.** Khi một biên chỉ có ở vài bản sao, tổng ở biên đó chỉ phản ánh các bản sao có chuỗi tương ứng. Sau khi đổi cấu hình, kiểm tra các đích và cửa sổ truy vấn trước khi so sánh p95 với giai đoạn dùng bộ biên cũ.

## Tài liệu tham khảo

- [Spring Boot 3.3 — Metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html)
- [Micrometer 1.13 — Histograms and Percentiles](https://docs.micrometer.io/micrometer/reference/1.13/concepts/histogram-quantiles.html)
- [Prometheus — histogram_quantile](https://prometheus.io/docs/prometheus/latest/querying/functions/#histogram_quantile)
- [Prometheus — Histograms and summaries](https://prometheus.io/docs/practices/histograms/)
