# Phân biệt tổng hợp theo instance với tổng hợp theo service

Giả sử dịch vụ `checkout` có hai bản sao. Bản sao A xử lý phần lớn lưu lượng và chỉ có 1% lỗi. Bản sao B xử lý ít yêu cầu hơn nhưng có 20% lỗi. Nếu bảng theo dõi chỉ hiển thị tỷ lệ lỗi của cả dịch vụ, lỗi ở B có thể khó nhận ra. Nếu chỉ xem từng bản sao, người trực vận hành phải tự tính dịch vụ đang phục vụ bao nhiêu lượt và bao nhiêu lượt thất bại.

## Chọn nhãn theo câu hỏi

| Phạm vi | Giữ nhãn nào khi gộp? | Câu hỏi trả lời được |
| --- | --- | --- |
| Theo instance | `service` và `instance` trong phạm vi job đã chọn. | Bản sao nào nhận ít lưu lượng, có nhiều lỗi hoặc có độ trễ cao? |
| Theo service | `service` và các nhãn cần thiết để tách môi trường. | Toàn dịch vụ nhận bao nhiêu lưu lượng? Tỷ lệ lỗi người dùng gặp là bao nhiêu? |

Trong Prometheus, một `instance` là một đích thu thập, thường tương ứng với một tiến trình. Theo mặc định, nhãn `instance` lấy phần `host:port` của đích. Nhãn `job` xác định nhóm thu thập, còn `service` trong bài là nhãn do người vận hành gán để nhận diện dịch vụ. Một job có thể thu thập nhiều dịch vụ. Chỉ dùng `job` làm nhãn đại diện cho dịch vụ khi hệ thống duy trì ánh xạ phù hợp giữa hai khái niệm.

Ví dụ này dùng các đích Actuator được gán nhãn `service` ngay trong cấu hình Prometheus:

~~~yaml
scrape_configs:
  - job_name: spring-apps
    metrics_path: /actuator/prometheus
    static_configs:
      - targets: ['checkout-a:8080', 'checkout-b:8080']
        labels:
          service: checkout
      - targets: ['catalog-a:8080']
        labels:
          service: catalog
~~~

Giả sử các tên đích phân giải được từ Prometheus và ứng dụng dùng đường dẫn Actuator mặc định. Nếu hệ thống gộp nhiều cụm, thêm nhãn như `cluster` vào khóa nhóm khi cần giữ kết quả từng cụm riêng biệt. Trong truy vấn dưới đây, `service!=""` giới hạn tập dữ liệu vào những đích có nhãn dịch vụ.

## So sánh hai cách tính lưu lượng

Ví dụ dùng bộ đếm số lượt từ `http.server.requests` của Spring Boot, xuất sang Prometheus dưới tên `http_server_requests_seconds_count`. Một instance có thể xuất nhiều chuỗi cho cùng meter do khác `uri`, `method` hoặc `status`.

**Theo instance**. Tính số lượt mỗi giây cho từng chuỗi rồi gộp các nhãn phụ, giữ mỗi bản sao thành một kết quả:

~~~promql
sum by (service, instance) (
  rate(http_server_requests_seconds_count{job="spring-apps", service!=""}[5m])
)
~~~

**Theo service**. Dùng cùng cửa sổ và cùng bộ lọc, nhưng chỉ giữ `service`. Kết quả cộng lưu lượng của các bản sao trong từng dịch vụ:

~~~promql
sum by (service) (
  rate(http_server_requests_seconds_count{job="spring-apps", service!=""}[5m])
)
~~~

Áp dụng `rate` trước `sum` để Prometheus nhận ra lần đặt lại bộ đếm ở riêng instance vừa khởi động lại. Giả sử ở một thời điểm, hai bản sao `checkout` có lưu lượng 90 và 10 lượt mỗi giây, còn `catalog` có 40 lượt mỗi giây. Truy vấn theo instance trả ba kết quả. Truy vấn theo service trả `checkout = 100` và `catalog = 40`.

## Tỷ lệ lỗi của service phải tính từ số lượt

Giả sử trong cùng cửa sổ đo, hai bản sao `checkout` có số lượt như sau:

| Instance | Tổng lượt | Lượt trả 5xx | Tỷ lệ 5xx |
| --- | ---: | ---: | ---: |
| `checkout-a:8080` | 900 | 9 | 1% |
| `checkout-b:8080` | 100 | 20 | 20% |
| `checkout`, gộp hai instance | 1.000 | 29 | 2,9% |

Tỷ lệ theo service là `(9 + 20) / (900 + 100)`. Lấy trung bình của 1% và 20% cho ra 10,5% vì phép tính đó gán cùng trọng số cho hai bản sao. Tỷ lệ người dùng gặp lỗi cần mỗi lượt có cùng trọng số, nên hãy **gộp tử số và mẫu số riêng rồi mới chia**.

Truy vấn sau trả tỷ lệ 5xx theo service dưới dạng số từ 0 đến 1. Để xem phần trăm, nhân kết quả với 100.

~~~promql
sum by (service) (
  rate(http_server_requests_seconds_count{
    job="spring-apps", service!="", status=~"5[0-9][0-9]"
  }[5m])
)
/
sum by (service) (
  rate(http_server_requests_seconds_count{job="spring-apps", service!=""}[5m])
)
~~~

Để tìm bản sao gặp lỗi, đổi cả hai `sum by (service)` thành `sum by (service, instance)`. Hai vế sẽ ghép theo cùng bộ nhãn. Với cả hai cách, áp dụng cùng phạm vi đo cho tử và mẫu, ngoại trừ bộ lọc `status` dành riêng cho tử số.

Nếu chưa có chuỗi 5xx, biểu thức có thể thiếu kết quả cho dịch vụ đó. Khi đã xác nhận dữ liệu thu thập đầy đủ và sự vắng mặt của chuỗi 5xx nghĩa là chưa phát sinh lỗi, có thể bổ sung số 0 theo đúng nhãn nhóm bằng `or on(service)` với `0 *` tổng lưu lượng ở mẫu số. Khi không có lưu lượng hoặc không đủ mẫu thu thập, hiển thị trạng thái thiếu dữ liệu thay vì diễn giải tỷ lệ là 0%.

## Với độ trễ, gộp dữ liệu làm đầu vào cho phép tính

- **Độ trễ trung bình**. Gộp tốc độ tăng của `_sum` và `_count` riêng theo cùng khóa, rồi chia. `_sum` của timer Prometheus tính bằng giây. Trọng số của mỗi bản sao là số lượt mà nó phục vụ.
- **p95**. Nếu các bản sao xuất histogram kiểu cổ điển với cùng ranh giới, gộp tốc độ tăng của bucket theo nhãn nhóm và giữ `le` để Prometheus biết ranh giới của từng bucket.

~~~promql
histogram_quantile(
  0.95,
  sum by (service, le) (
    rate(http_server_requests_seconds_bucket{job="spring-apps", service!=""}[5m])
  )
)
~~~

Kết quả là p95 ước lượng của các lượt đo trong từng service, tính bằng giây. Để xem p95 từng bản sao, dùng `sum by (service, instance, le)`. Giá trị p95 đã tính riêng ở mỗi bản sao thiếu thông tin phân phối cần để tính p95 của tập lượt gộp. Nếu chưa có chuỗi `_bucket`, cần kiểm tra cấu hình histogram trước khi dùng truy vấn.

## Đọc cả hai mức khi kiểm tra sự cố

1. Dùng lưu lượng và tỷ lệ 5xx theo service để xác định dịch vụ chịu ảnh hưởng.
2. Giữ `instance` trong khóa nhóm để tìm bản sao đóng góp vào lỗi. So sánh cả tỷ lệ lẫn số lượt để phân biệt tỷ lệ cao trên ít yêu cầu với lỗi ảnh hưởng nhiều người dùng.
3. Xem `up{job="spring-apps"}` theo đích để phát hiện lượt thu thập thất bại. Dịch vụ vẫn có thể trả kết quả tổng hợp từ các bản sao còn dữ liệu. Khi tổng lưu lượng cao bất thường, kiểm tra xem cùng một đích có được thu thập hai lần qua các job hoặc nguồn đã gộp hay không.

### Tài liệu tham khảo

- [Prometheus – Job, instance và nhãn của đích thu thập](https://prometheus.io/docs/concepts/jobs_instances/)
- [Prometheus – Toán tử tổng hợp và cách ghép nhãn](https://prometheus.io/docs/prometheus/latest/querying/operators/)
- [Prometheus – Hàm rate và histogram_quantile](https://prometheus.io/docs/prometheus/latest/querying/functions/)
- [Spring Boot 3.3 – Metrics của Spring MVC](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html)