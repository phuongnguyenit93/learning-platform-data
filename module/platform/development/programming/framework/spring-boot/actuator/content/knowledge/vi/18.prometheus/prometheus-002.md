# JSON từ endpoint metrics và định dạng thu thập của Prometheus

Trong Spring Boot Actuator, `/actuator/metrics` giúp người vận hành khám phá meter và kiểm tra giá trị hiện tại. `/actuator/prometheus` phục vụ một công việc khác. Máy chủ Prometheus gọi endpoint này định kỳ để thu thập các mẫu theo giao thức mà nó hiểu. Cả hai có thể phản ánh cùng phép đo của Micrometer, nhưng cách đặt tên, lọc và biểu diễn dữ liệu khác nhau.

| Điểm so sánh | `/actuator/metrics` | `/actuator/prometheus` |
| --- | --- | --- |
| Mục đích | Chẩn đoán trong một bản sao ứng dụng. | Cung cấp dữ liệu để máy chủ Prometheus thu thập định kỳ (scrape). |
| Phản hồi thường gặp trong Spring Boot 3.3 | JSON, thường với `Content-Type: application/vnd.spring-boot.actuator.v3+json`. | Dạng văn bản Prometheus `text/plain;version=0.0.4` theo mặc định. Có thể trả OpenMetrics 1.0 khi thương lượng qua `Accept`. |
| Tên | Tên meter trong Micrometer, ví dụ `jvm.memory.used`. | Tên chuỗi sau khi registry áp dụng quy ước xuất, ví dụ `jvm_memory_used_bytes`. |
| Cấu trúc | Danh sách tên hoặc chi tiết một tên meter, gồm thống kê, đơn vị và các tag còn có thể lọc. | Các dòng mẫu chứa tên, nhãn và giá trị. Nhiều bộ nhãn của một họ chỉ số xuất hiện riêng. |
| Thời gian | Giá trị tại lúc gọi, theo cách meter đang ghi nhận. | Mỗi phản hồi cung cấp các mẫu cho một lần scrape. Prometheus tạo lịch sử bằng cách lưu mẫu qua nhiều lần scrape. |

## Đọc JSON để kiểm tra ứng dụng

`GET /actuator/metrics` trả đối tượng có mảng `names`. Để xem chi tiết, thêm tên Micrometer vào đường dẫn. Tham số `tag` nhận một cặp `khóa:giá trị`. Lặp tham số để lọc theo nhiều tag.

```bash
curl -i 'http://localhost:8080/actuator/metrics'
curl -i --get 'http://localhost:8080/actuator/metrics/jvm.memory.used' --data-urlencode 'tag=area:nonheap' --data-urlencode 'tag=id:Metaspace'
```

Dưới đây là thân JSON minh họa khi chọn vùng Metaspace. Giá trị bộ nhớ thực tế phụ thuộc JVM và thời điểm gọi.

```json
{
  "name": "jvm.memory.used",
  "description": "The amount of used memory",
  "baseUnit": "bytes",
  "measurements": [
    {
      "statistic": "VALUE",
      "value": 67108864
    }
  ],
  "availableTags": []
}
```

`measurements` cho biết thống kê và giá trị tương ứng. Ở đây `VALUE` là giá trị hiện tại của gauge. `baseUnit` cho biết số đo tính bằng byte. `availableTags` liệt kê các tag còn có thể dùng để thu hẹp kết quả. Mảng rỗng trong ví dụ vì cả hai tag của meter đã được chọn.

Nếu chỉ lọc `area:nonheap`, nhiều vùng nhớ có thể cùng khớp. Với gauge bộ nhớ này, endpoint cộng các giá trị `VALUE` phù hợp. Khi hai vùng có lần lượt 67.108.864 và 8.388.608 byte, JSON cho bộ lọc `area:nonheap` trả giá trị tổng 75.497.472 byte. Lọc thêm theo `id` để so sánh đúng một vùng nhớ với một chuỗi Prometheus.

## Đọc phản hồi scrape

```bash
curl -i 'http://localhost:8080/actuator/prometheus'
```

Trong phản hồi văn bản Prometheus 0.0.4, trích đoạn minh họa của cùng hai vùng nhớ có dạng sau.

```text
# HELP jvm_memory_used_bytes The amount of used memory
# TYPE jvm_memory_used_bytes gauge
jvm_memory_used_bytes{area="nonheap",id="Metaspace"} 67108864
jvm_memory_used_bytes{area="nonheap",id="Compressed Class Space"} 8388608
```

`# HELP` mô tả họ chỉ số và `# TYPE` xác định kiểu. Mỗi dòng dữ liệu biểu diễn một mẫu có tên, bộ nhãn và giá trị số. Đặc tả cho phép dấu thời gian tùy chọn. Trong trích đoạn này không có dấu thời gian kèm mẫu, nên máy chủ dùng thời điểm scrape để lưu mẫu. Tên chỉ số kết hợp với toàn bộ bộ nhãn xác định một chuỗi thời gian. Khi lưu, Prometheus thường thêm nhãn của đích thu thập như `job` và `instance`.

Quy tắc đổi tên còn phụ thuộc kiểu meter và đơn vị. Với `Timer` `http.server.requests`, chẳng hạn, registry Prometheus có thể xuất `http_server_requests_seconds_count` cho số lần đo và `http_server_requests_seconds_sum` cho tổng thời gian theo giây. Các chuỗi `_bucket` xuất hiện khi cấu hình histogram tương ứng. Vì thế, hãy lấy tên chuỗi thực tế từ phản hồi scrape khi viết truy vấn.

Để xem biến thể OpenMetrics của Spring Boot 3.3, yêu cầu kiểu nội dung tương ứng.

```bash
curl -i -H 'Accept: application/openmetrics-text; version=1.0.0' 'http://localhost:8080/actuator/prometheus'
```

Kiểm tra `Content-Type` của phản hồi. OpenMetrics 1.0 dùng `application/openmetrics-text` và đánh dấu cuối thân dữ liệu bằng `# EOF`. Khi Prometheus tự scrape, máy chủ gửi `Accept` theo các giao thức thu thập đã cấu hình. Hai biến thể đều phục vụ việc thu thập mẫu và có quy tắc định dạng riêng.

## Kết nối Spring Boot với Prometheus

Trong ứng dụng web Spring Boot dùng cơ chế tự cấu hình, thêm `spring-boot-starter-actuator` và `io.micrometer:micrometer-registry-prometheus`. Ví dụ sau mở cả hai endpoint để quan sát chúng trong cùng một lần chạy.

```properties
management.endpoints.web.exposure.include=health,metrics,prometheus
```

Với ứng dụng ở cổng 8080 và Prometheus chạy trực tiếp trên cùng máy, thêm job vào `prometheus.yml`.

```yaml
scrape_configs:
  - job_name: spring-app
    metrics_path: /actuator/prometheus
    static_configs:
      - targets: ['localhost:8080']
```

Nếu máy chủ Prometheus chạy trong container hoặc trên máy khác, dùng địa chỉ ứng dụng mà máy chủ đó truy cập được. Nếu ứng dụng dùng cổng quản trị hoặc đường dẫn quản trị riêng, chỉnh `targets` và `metrics_path` theo URL thực tế.

Sau khi job thu thập thành công, truy vấn chuỗi đã lưu bằng PromQL.

```promql
jvm_memory_used_bytes{job="spring-app", area="nonheap", id="Metaspace"}
```

Prometheus cũng có API truy vấn trả JSON, chẳng hạn `/api/v1/query` trên **máy chủ Prometheus**. JSON đó chứa kết quả truy vấn dữ liệu đã thu thập. JSON từ `/actuator/metrics` trên **ứng dụng Spring Boot** chứa dữ liệu chẩn đoán tại lúc gọi.

## Chẩn đoán khi hai phía cho kết quả khác nhau

- **`/actuator/metrics` trả HTTP 200 nhưng job báo lỗi scrape.** Kiểm tra `metrics_path` và `Content-Type` của đích. JSON Actuator có thể là phản hồi hợp lệ của ứng dụng nhưng không đúng định dạng đầu vào của trình scrape.
- **`/actuator/prometheus` trả 404.** Kiểm tra dependency registry, cấu hình mở endpoint qua HTTP, cổng quản trị và đường dẫn thực tế. Với 401 hoặc 403, kiểm tra quyền của đích thu thập.
- **Cùng tên gốc nhưng giá trị lệch.** So sánh cùng đơn vị, cùng bộ tag hoặc nhãn và cùng bản sao ứng dụng. JSON có thể đã gộp nhiều vùng nhớ, trong khi truy vấn PromQL đang chọn một vùng. Hai yêu cầu HTTP cũng có thể quan sát JVM vào các thời điểm khác nhau.
- **Phản hồi scrape có mẫu nhưng truy vấn chưa thấy.** Kiểm tra trạng thái đích thu thập, tên chuỗi và nhãn thực tế ở máy chủ. Phản hồi ứng dụng tại lúc gọi và mẫu gần nhất Prometheus lưu có thể thuộc hai thời điểm khác nhau.

## Tài liệu tham khảo

- [Spring Boot 3.3 — Actuator Metrics API](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/metrics.html)
- [Spring Boot 3.3 — Actuator Prometheus API](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/prometheus.html)
- [Spring Boot 3.3 — Cấu hình Micrometer và Prometheus](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html)
- [Prometheus — Định dạng công bố số liệu](https://prometheus.io/docs/instrumenting/exposition_formats/)
- [Prometheus — Cấu hình thu thập](https://prometheus.io/docs/prometheus/latest/configuration/configuration/#scrape_config)
- [Prometheus — HTTP API truy vấn](https://prometheus.io/docs/prometheus/latest/querying/api/)
