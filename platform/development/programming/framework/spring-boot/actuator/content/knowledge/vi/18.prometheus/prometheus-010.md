## Kết nối dashboard Grafana và kiểm tra dữ liệu trước khi tạo cảnh báo

Một panel hiển thị trống có thể do Prometheus không thu thập được dữ liệu, ứng dụng chưa phát sinh meter, bộ lọc chọn sai nhãn hoặc cửa sổ tính tốc độ có quá ít mẫu. Trước khi dùng panel làm cơ sở cho cảnh báo, hãy xác định tầng nào cung cấp giá trị, kiểm tra giá trị khi dịch vụ chạy bình thường và quan sát giá trị thay đổi khi có lỗi thử nghiệm.

### 1. Xác minh đường đi của dữ liệu

Ứng dụng Spring Boot xuất dữ liệu qua Actuator. Prometheus định kỳ đọc endpoint, lưu chuỗi thời gian và xử lý PromQL. Grafana gửi truy vấn tới Prometheus để vẽ dashboard và, với quy tắc do Grafana quản lý, đánh giá điều kiện cảnh báo.

Trong ứng dụng web Spring Boot 3.3 có `spring-boot-starter-actuator` và `io.micrometer:micrometer-registry-prometheus`, có thể mở endpoint bằng `application.yml` dưới đây. Ví dụ dùng đường dẫn Actuator mặc định.

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,prometheus
```

Ví dụ `prometheus.yml` dành cho môi trường thử nghiệm có dịch vụ tên `checkout`, cổng `8080`, cùng mạng với Prometheus. `targets` chứa địa chỉ mà **Prometheus** có thể truy cập.

```yaml
scrape_configs:
  - job_name: checkout
    metrics_path: /actuator/prometheus
    scrape_interval: 15s
    static_configs:
      - targets: ["checkout:8080"]
```

Kiểm tra theo thứ tự sau.

1. **Actuator.** Từ mạng của Prometheus, đọc `http://checkout:8080/actuator/prometheus`. Sau khi gửi yêu cầu tới ứng dụng, tìm dòng `http_server_requests_seconds_count` hoặc tên thực tế mà ứng dụng xuất. Đọc `status` và `uri` ở ngay dòng đó. Nếu metric chưa có, xác nhận ứng dụng đã xử lý yêu cầu và registry Prometheus đang hoạt động.
2. **Prometheus.** Trong trang **Targets** của Prometheus hoặc qua `/api/v1/targets`, đối chiếu địa chỉ thu thập, thời điểm thu thập gần nhất và lỗi gần nhất. Chạy `up{job="checkout"}`. `1` là lần thu thập gần nhất thành công, `0` là thất bại. Không có chuỗi `up` có thể do sai `job`, target chưa được phát hiện hoặc đã biến mất. So số target trả về với danh sách bản sao dự kiến. Một target thành công không xác nhận mọi bản sao đều có dữ liệu.
3. **Grafana.** Vào **Connections → Add new connection**, chọn **Prometheus** rồi **Add new data source**. Đặt tên như `Prometheus checkout` và nhập URL của **máy chủ Prometheus**, chẳng hạn `http://prometheus:9090` nếu hai dịch vụ ở cùng mạng Docker Compose. Trong container Grafana, `localhost` trỏ về chính container đó. Đặt **Scrape interval** của data source khớp với `15s` trong ví dụ, rồi chọn **Save & test**. Sau đó vào **Explore**, chọn đúng nguồn và chạy lại `up{job="checkout"}`. Kết nối thành công xác nhận Grafana truy cập được Prometheus. Truy vấn `up` mới cho biết trạng thái thu thập của các target cụ thể.

Nếu cần đối chiếu trực tiếp với API, chạy lệnh sau từ nơi truy cập được cổng Prometheus đã công bố trên máy cục bộ. `status="success"` xác nhận truy vấn được xử lý. Đọc thêm `data.result` để biết có chuỗi nào trả về và xem nhãn `instance` của từng chuỗi.

```bash
curl -fsS -G 'http://localhost:9090/api/v1/query' \
  --data-urlencode 'query=up{job="checkout"}'
```

### 2. Dựng panel và đối chiếu số gốc

Trong Explore, bắt đầu bằng `http_server_requests_seconds_count{job="checkout"}` để xem nhãn và giá trị tích lũy của từng chuỗi. Với chuỗi đã tồn tại ổn định, `count_over_time(http_server_requests_seconds_count{job="checkout"}[5m])` cho biết số mẫu thực tế trong cửa sổ. Khi chu kỳ thu thập là 15 giây, một chuỗi được thu thập đều có khoảng 20 mẫu trong 5 phút. `rate` cần ít nhất hai mẫu cho mỗi chuỗi. Số mẫu thấp ở một chuỗi `5xx` mới xuất hiện có thể khiến tốc độ lỗi tạm thời chưa tính được.

Tạo một dashboard với ba panel dùng cùng data source. Panel **Thu thập theo bản sao** dùng `up{job="checkout"}`, hiển thị theo `instance` để nhận ra đích bị thiếu hoặc bị lỗi. Hai panel nghiệp vụ có thể dùng **Time series** và kiểu truy vấn **Range**. Khi đối chiếu với cảnh báo, giữ cửa sổ `[5m]` cố định để hai nơi tính cùng một chỉ số.

**Yêu cầu mỗi giây**

```promql
sum by (job) (
  rate(http_server_requests_seconds_count{job="checkout"}[5m])
)
```

**Phần trăm yêu cầu trả về HTTP 5xx**

```promql
100 *
sum by (job) (
  rate(http_server_requests_seconds_count{job="checkout",status=~"5[0-9][0-9]"}[5m])
)
/
(
  sum by (job) (
    rate(http_server_requests_seconds_count{job="checkout"}[5m])
  ) > 0
)
```

Đặt đơn vị panel đầu là yêu cầu/giây. Panel thứ hai nhận giá trị theo thang **0–100** vì PromQL đã nhân 100. Bộ lọc `> 0` bỏ mẫu số bằng 0 và giữ nguyên các tốc độ dương. Nếu chưa có chuỗi 5xx hoặc chuỗi đó có quá ít mẫu để tính `rate`, truy vấn phần trăm có thể trả rỗng dù có yêu cầu. Hãy kiểm tra tử số và mẫu số riêng trước khi quyết định trường hợp nào được biểu diễn bằng 0%.

Nếu thay đổi phạm vi sang một tuyến hay phương thức, dùng cùng bộ lọc ở cả tử và mẫu. Để so panel với Explore hoặc giao diện Prometheus, chọn cùng nguồn, cùng thời điểm đánh giá, cùng truy vấn đã thay biến và cùng bước thời gian khi so cả đường biểu diễn. Mở **Inspect → Query** để kiểm tra yêu cầu thực tế và **Inspect → Data** để đọc giá trị. Kiểm tra các phép biến đổi và tùy chọn hiển thị nếu số trên hình khác số từ truy vấn gốc. Với panel khám phá cần tự điều chỉnh khi thu phóng, có thể dùng `$__rate_interval` trong Grafana. Khoảng này phụ thuộc vào độ phân giải của panel và chu kỳ thu thập được cấu hình trong data source hoặc `Min step` của truy vấn. Xem giá trị đã thay ở Query Inspector khi cần đối chiếu. Khi chuyển sang truy vấn cảnh báo, dùng cửa sổ cố định như `[5m]`.

### 3. Chạy thử các trạng thái dữ liệu

Trong môi trường thử nghiệm, tạo lưu lượng ổn định và quan sát đủ số lần thu thập. Sau đó tạo một đoạn lưu lượng có phản hồi 5xx kiểm soát được, xác nhận mã HTTP phía gọi rồi đợi Prometheus thu được ít nhất hai mẫu cho chuỗi lỗi. Đối chiếu thời điểm gửi tải với dashboard. Khi cần đo trạng thái bình thường sau lần thử lỗi, duy trì lưu lượng thành công đủ lâu để giai đoạn lỗi ra khỏi cửa sổ `[5m]`.

Bảng sau dùng số minh họa để kiểm tra đơn vị và cách đọc truy vấn. Tốc độ đo được thực tế có thể lệch nhẹ theo nhịp thu thập và ngoại suy của `rate`.

| Trạng thái thử | Kết quả cần đối chiếu |
| --- | --- |
| Có lưu lượng, chuỗi lỗi đã có đủ mẫu và counter lỗi đứng yên | Tốc độ tổng dương, tốc độ lỗi bằng 0 và tỷ lệ là 0%. |
| Có lỗi thử nghiệm | Nếu tổng là 12 yêu cầu/giây và lỗi là 0,6 yêu cầu/giây, panel hiển thị 5%. Kiểm tra nhãn `status` và phạm vi `job` khi kết quả khác dự kiến. |
| Dừng gửi yêu cầu và đợi hết cửa sổ | Nếu counter vẫn được xuất, tốc độ tổng về 0. Truy vấn tỷ lệ ở trên trả rỗng vì mẫu số bằng 0. |
| Một bản sao ngừng được thu thập | `up` của target có thể về 0 hoặc chuỗi biến mất nếu target bị gỡ. Hai panel nghiệp vụ vẫn có thể hiện số từ các bản sao còn lại. Đối chiếu riêng số bản sao có dữ liệu. |
| Grafana truy vấn thất bại | Kiểm tra thông báo lỗi, quyền truy cập, URL và tình trạng của Prometheus. Kết quả lỗi truy vấn khác với truy vấn thành công nhưng không trả dữ liệu. |

Đối với trường hợp 0%, cần có số đo đủ để xác nhận không phát sinh lỗi, hoặc một quy ước bù 0 có điều kiện dựa trên lưu lượng và độ đầy đủ của dữ liệu. Việc biến mọi khoảng trống của panel thành 0 sẽ che mất sự khác biệt giữa lỗi thu thập, thiếu mẫu và không có lưu lượng.

### 4. Xem trước điều kiện cảnh báo

Chỉ chuyển truy vấn đã kiểm tra sang quy tắc cảnh báo khi biết rõ giá trị, đơn vị, phạm vi nhãn và hành vi khi thiếu dữ liệu. Với cảnh báo do Grafana quản lý, chọn cùng data source và thử truy vấn kiểu **Instant** để mỗi bộ nhãn trả về một giá trị tại lúc đánh giá. Nếu dùng **Range**, chọn phép **Reduce** phù hợp trước khi so ngưỡng, chẳng hạn **Last** để lấy giá trị cuối của từng chuỗi. **Last** và **Mean** trả lời hai câu hỏi khác nhau. Giữ các bộ lọc xác định như `job="checkout"` và dùng `[5m]` thay cho các biến phụ thuộc dashboard như `$job` hoặc `$__rate_interval`.

Trong trình chỉnh sửa quy tắc, dùng **Preview** để xem chuỗi và giá trị đi vào điều kiện. Với ngưỡng thử lớn hơn 4 trên thang 0–100, giá trị 5 phải vượt ngưỡng và 0 phải ở dưới ngưỡng. Chọn ngưỡng vận hành dựa trên lưu lượng, tỷ lệ lỗi bình thường và yêu cầu dịch vụ. Nếu cần bỏ qua biến động khi chỉ có vài yêu cầu, xác định ngưỡng lưu lượng tối thiểu trên cùng cửa sổ. Xem trước cũng là lúc kiểm tra nhãn còn lại có đủ để nhận ra dịch vụ hay tuyến đường gây lỗi.

Cửa sổ PromQL quyết định dữ liệu được dùng ở mỗi lần đánh giá. **Evaluation interval** quyết định Grafana kiểm tra bao lâu một lần. **Pending period** quyết định điều kiện phải duy trì bao lâu trước khi phát cảnh báo. Preview cho biết kết quả điều kiện ở lần đánh giá thử. Đối với quy tắc do Grafana quản lý, quyết định riêng cách xử lý **No Data** và **Error**. Nếu một chuỗi biến mất trong khi các chuỗi khác còn dữ liệu, quy tắc vẫn có thể trả kết quả. Dùng tín hiệu thu thập như `up` và số bản sao dự kiến để phát hiện mất dữ liệu cục bộ.

### Tài liệu tham khảo

- [Spring Boot 3.3 Actuator — thu thập metrics bằng Prometheus](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html)
- [Prometheus — API truy vấn và kiểm tra target](https://prometheus.io/docs/prometheus/latest/querying/api/)
- [Grafana — kết nối nguồn dữ liệu Prometheus](https://grafana.com/docs/grafana/latest/datasources/prometheus/configure/)
- [Grafana — kiểm tra truy vấn và dữ liệu của panel](https://grafana.com/docs/grafana/latest/visualizations/panels-visualizations/panel-inspector/)
- [Grafana — truy vấn và điều kiện cảnh báo](https://grafana.com/docs/grafana/latest/alerting/fundamentals/alert-rules/queries-conditions/)