# Percentile tính tại ứng dụng và percentile tính từ histogram

Khi theo dõi độ trễ HTTP, p95 trả lời câu hỏi «Ngưỡng thời gian nào bao phủ khoảng 95% số yêu cầu trong tập đang xét?». Nếu p95 của dịch vụ trong 5 phút là khoảng 300 ms, khoảng 95% yêu cầu được ghi nhận trong cửa sổ đó hoàn thành trong 300 ms trở xuống. Muốn hiểu con số này, hãy xác định tập yêu cầu gồm những bản sao ứng dụng, đường dẫn và khoảng thời gian nào.

Spring Boot Actuator dùng Micrometer để đo độ trễ. Với cùng một `Timer`, có hai cách đưa thông tin về phân bố độ trễ tới Prometheus.

| Câu hỏi | Percentile tính tại ứng dụng | Percentile tính từ histogram |
| --- | --- | --- |
| Ai tính? | Micrometer ước lượng percentile trong từng tiến trình, cho từng tên meter và bộ tag. | Prometheus ước lượng percentile khi chạy truy vấn. |
| Ứng dụng xuất gì? | Giá trị đã tính cho mỗi percentile cấu hình, ví dụ một chuỗi có nhãn `quantile="0.95"`. | Bộ đếm tích lũy cho từng ngưỡng, ví dụ một chuỗi `_bucket` có nhãn `le="0.3"`. |
| Cửa sổ thời gian nằm ở đâu? | Cửa sổ thống kê phía Micrometer, điều chỉnh qua `expiry` và `buffer-length`. | Cửa sổ truy vấn, ví dụ `[5m]` trong `rate()` trên các bộ đếm được scrape. |
| Gộp nhiều bản sao thế nào? | Có thể xem hoặc so sánh p95 của từng bản sao. Chỉ từ các p95 riêng lẻ thì không tính được p95 chung, kể cả khi biết số yêu cầu. | Cộng số quan sát tại từng ngưỡng tương ứng rồi tính percentile trên phân bố đã gộp. Các chuỗi đem cộng cần dùng cùng đơn vị và bộ ngưỡng tương thích. |

## Tính tại ứng dụng

Cấu hình sau xuất p50 và p95 của meter `http.server.requests` do Spring Boot ghi nhận cho các yêu cầu HTTP. Đặt trong `application.properties` của một ứng dụng web có Actuator và dependency `io.micrometer:micrometer-registry-prometheus`.

```properties
management.endpoints.web.exposure.include=health,prometheus
management.metrics.distribution.percentiles.http.server.requests=0.50,0.95
```

Sau khi ứng dụng ghi nhận yêu cầu, một mẫu xuất ra có thể trông như sau. Các nhãn khác của meter được lược bớt để tập trung vào percentile.

```text
http_server_requests_seconds{method="GET",uri="/orders",quantile="0.95"} 0.1
```

Giá trị `0.1` là độ trễ ước lượng tính bằng giây, tức 100 ms. Mỗi tổ hợp tag được đo riêng. Prometheus còn gắn nhãn đích scrape như `job` và `instance`, nhờ đó có thể xem p95 của từng bản sao cho cùng một đường dẫn. Thay đổi khoảng thời gian hiển thị trên biểu đồ chỉ thay đổi các điểm p95 đã lưu mà người xem nhìn thấy. Nó không khiến Micrometer tính lại p95 từ toàn bộ yêu cầu trong khoảng thời gian đó.

## Tính tại Prometheus từ histogram

Để xem p95 chung của dịch vụ, thử cấu hình sau trong một lần chạy riêng. `percentiles-histogram` bật các bucket mà Micrometer chọn cho meter. `slo` thêm ngưỡng 300 ms để đếm trực tiếp số yêu cầu đạt ngưỡng đó.

```properties
management.endpoints.web.exposure.include=health,prometheus
management.metrics.distribution.percentiles-histogram.http.server.requests=true
management.metrics.distribution.slo.http.server.requests=300ms
```

Trong histogram cổ điển của Prometheus, `le` là giới hạn trên có tính cả điểm biên. Với timer HTTP, `le="0.3"` đếm mọi yêu cầu mất tối đa 0,3 giây. Một yêu cầu 100 ms xuất hiện trong mọi bucket có ngưỡng từ 100 ms trở lên, nên không cộng các bucket có `le` khác nhau để tìm tổng số yêu cầu. Bucket `le="+Inf"` chứa toàn bộ quan sát và bằng `_count` của cùng tổ hợp nhãn.

Khi Prometheus đã scrape các bản sao của dịch vụ dưới `job="orders"`, truy vấn sau cho một giá trị p95 của các yêu cầu `GET /orders` trên toàn bộ các bản sao trong cửa sổ 5 phút. Giả sử `/orders` là giá trị nhãn `uri` được xuất thực tế.

```promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(http_server_requests_seconds_bucket{job="orders", method="GET", uri="/orders"}[5m])
  )
)
```

1. `rate(...[5m])` ước lượng tốc độ tăng trung bình của từng bộ đếm bucket. Tính trên từng chuỗi trước để Prometheus xử lý được việc bộ đếm về 0 khi một bản sao khởi động lại.
2. `sum by (le)` cộng tốc độ theo cùng ngưỡng và gộp các nhãn còn lại. Nếu cần p95 riêng theo đường dẫn, bỏ bộ lọc `uri` và giữ cả `uri` lẫn `le` trong `sum by (uri, le)`.
3. `histogram_quantile` tìm bucket chứa mốc 95% rồi nội suy tuyến tính trong bucket hữu hạn. Kết quả có đơn vị giây. Bucket rộng quanh mốc cần đo làm tăng sai số có thể gặp. Nếu mốc nằm trong bucket `+Inf`, hàm trả về giới hạn hữu hạn cao nhất, nên có thể không phản ánh được phần đuôi chậm vượt giới hạn đó.

## Ví dụ hai bản sao có lưu lượng chênh lệch

Trong cùng cửa sổ, bản sao A xử lý 1.000 yêu cầu đều mất 100 ms, còn B xử lý 10 yêu cầu đều mất 900 ms. Xét trực tiếp các mẫu đã sắp xếp, p95 của A là 100 ms và của B là 900 ms. Trung bình hai p95 là 500 ms, trong khi 1.000 trong 1.010 yêu cầu đã hoàn thành trong 100 ms. P95 chung tính theo hạng gần nhất là quan sát thứ 960 và bằng 100 ms. Trung bình có trọng số theo số yêu cầu cũng chỉ là trung bình của hai ngưỡng, không khôi phục được thứ tự các quan sát.

Đây là các **số đếm tích lũy theo ngưỡng trong cửa sổ** với một bộ bucket minh họa. Bảng biểu diễn số quan sát để dễ tính tay. Truy vấn thực tế dùng tốc độ trên từng bucket.

| Ngưỡng trên | A | B | Tổng |
| --- | ---: | ---: | ---: |
| 80 ms | 0 | 0 | 0 |
| 120 ms | 1.000 | 0 | 1.000 |
| 300 ms | 1.000 | 0 | 1.000 |
| 1.000 ms | 1.000 | 10 | 1.010 |
| `+Inf` | 1.000 | 10 | 1.010 |

Prometheus nội suy tại mốc `0,95 × 1.010 = 959,5`, nằm trong khoảng (80 ms, 120 ms]. Với giả định các mẫu phân bố đều trong khoảng đó, kết quả là `80 + (120 − 80) × (959,5 − 0) / (1.000 − 0) = 118,38 ms`. Các mẫu thật trong bucket đều nằm tại 100 ms. Histogram giữ số đếm theo khoảng, nên Prometheus gộp được hai bản sao nhưng chỉ ước lượng được p95 bên trong khoảng.

Nếu câu hỏi là «Bao nhiêu phần trăm yêu cầu hoàn thành trong tối đa 300 ms?», dùng trực tiếp bucket tại 300 ms và tổng số yêu cầu. Với dữ liệu trong bảng, tỷ lệ là `1.000 / 1.010 ≈ 99,01%`.

```promql
sum(rate(http_server_requests_seconds_bucket{job="orders", method="GET", uri="/orders", le="0.3"}[5m]))
/
sum(rate(http_server_requests_seconds_count{job="orders", method="GET", uri="/orders"}[5m]))
```

Truy vấn trả về tỷ lệ từ 0 đến 1 khi có yêu cầu. Cả tử và mẫu cần cùng phạm vi nhãn và thời gian. Khi không có yêu cầu, tỷ lệ không xác định.

## Cách kiểm tra khi áp dụng

- Xem `/actuator/prometheus` sau khi đã tạo lưu lượng. Tìm `quantile="0.95"` trong cấu hình tính tại ứng dụng hoặc `http_server_requests_seconds_bucket` với các nhãn `le` trong cấu hình histogram. Kiểm tra nhãn thực tế ở Prometheus trước khi áp dụng bộ lọc.
- Nếu p95 bất ngờ, kiểm tra số yêu cầu trong cửa sổ, các bản sao được scrape và các ngưỡng quanh p95. Cửa sổ ít dữ liệu dễ dao động. Histogram cổ điển cần chuỗi `+Inf` để tính percentile.
- Khi đổi cấu hình bucket, kiểm tra sự nhất quán giữa các bản sao trước khi gộp. Nếu một ngưỡng chỉ tồn tại ở vài bản sao, tổng tại ngưỡng đó chỉ tính những bản sao có chuỗi tương ứng. Mỗi bucket thêm một chuỗi thời gian cho mỗi tổ hợp nhãn, vì vậy nên bật histogram cho meter cần đo và chọn dải ngưỡng phù hợp với độ trễ cần quan sát.
- Dùng percentile tại ứng dụng khi cần quan sát riêng từng bản sao hoặc khi hệ thống giám sát chỉ nhận được giá trị đã tính. Dùng histogram khi cần gộp nhiều bản sao, đổi cửa sổ truy vấn hoặc tính tỷ lệ đạt một ngưỡng đã cấu hình.

## Tài liệu tham khảo

- [Spring Boot 3.3 — Metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html)
- [Micrometer 1.13 — Histograms and Percentiles](https://docs.micrometer.io/micrometer/reference/1.13/concepts/histogram-quantiles.html)
- [Micrometer 1.13 — Timers](https://docs.micrometer.io/micrometer/reference/1.13/concepts/timers.html)
- [Prometheus — histogram_quantile](https://prometheus.io/docs/prometheus/latest/querying/functions/#histogram_quantile)
- [Prometheus — rate](https://prometheus.io/docs/prometheus/latest/querying/functions/#rate)
