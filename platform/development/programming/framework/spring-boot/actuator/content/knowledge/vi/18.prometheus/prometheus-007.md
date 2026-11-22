## Tính tốc độ yêu cầu và tỷ lệ lỗi từ counter theo cửa sổ thời gian

Một dịch vụ vừa khởi động lại có thể báo tổng số yêu cầu thấp hơn một dịch vụ đã chạy cả ngày, dù hiện tại xử lý nhiều yêu cầu hơn mỗi giây. Counter ghi nhận số lần tích lũy. Để biết dịch vụ đang xử lý bao nhiêu yêu cầu và bao nhiêu phần trăm kết thúc bằng lỗi, hãy đo mức tăng của counter trong cùng một cửa sổ thời gian.

### Chọn đúng counter trong Spring Boot Actuator

Spring Boot Actuator thường ghi thời gian xử lý HTTP vào `Timer` có tên Micrometer là `http.server.requests`. Với cách xuất Prometheus mặc định của Micrometer 1.13, `http_server_requests_seconds_count` là số lần Timer ghi nhận yêu cầu. Dù tên chứa `seconds`, giá trị của chuỗi `_count` là **số lần**. Chuỗi `_sum` thuộc cùng họ đo tổng thời lượng, tính bằng giây.

Đọc `/actuator/prometheus` để xác nhận tên và các nhãn được xuất. Trong ví dụ này, `status` là mã HTTP dạng chuỗi, còn `job` được Prometheus gắn theo cấu hình thu thập. Counter thường được tách thành nhiều chuỗi theo bản sao, mã trạng thái, phương thức và tuyến đường. Mỗi chuỗi có lịch sử tích lũy riêng.

### Tốc độ yêu cầu trong 5 phút

```promql
sum by (job) (
  rate(http_server_requests_seconds_count[5m])
)
```

Tại mỗi thời điểm đánh giá, `[5m]` lấy các mẫu nằm trong 5 phút trước đó, loại mẫu đúng biên trái và giữ mẫu đúng biên phải. `rate` ước lượng mức tăng trung bình **mỗi giây** của từng chuỗi trong cửa sổ. Nó điều chỉnh khi counter giảm do đặt lại và ngoại suy ở hai đầu cửa sổ. Cần ít nhất hai mẫu trong cửa sổ để tính tốc độ cho một chuỗi. Sau đó `sum by (job)` cộng tốc độ của các bản sao và các bộ nhãn khác, giữ lại một kết quả cho mỗi `job`. Đơn vị cuối cùng là yêu cầu/giây, tính trên các lần xử lý đã được Timer ghi nhận.

Thứ tự có ý nghĩa khi một bản sao khởi động lại. Nếu cộng giá trị counter của các bản sao trước, phần tăng ở một bản sao có thể che phần giảm của bản sao khác. Nếu tổng vẫn giảm, Prometheus cũng không biết phần counter nào đã đặt lại. Tính `rate` khi mỗi chuỗi còn riêng biệt giúp Prometheus nhận ra lần đặt lại đúng chỗ. Một lần thu thập bị bỏ lỡ có thể khiến Prometheus không thấy hết số lần đặt lại hoặc số yêu cầu đã xảy ra trước lúc khởi động lại.

Khi cần ước lượng **số yêu cầu trong cả cửa sổ** thay vì tốc độ, dùng `sum by (job) (increase(http_server_requests_seconds_count[5m]))`. `increase` tương đương `rate` nhân với số giây trong cửa sổ, nên kết quả có thể là số lẻ do ngoại suy. `irate` dựa vào hai mẫu gần nhất trong cửa sổ và có thể hữu ích khi xem dao động ngắn. `rate` trên cửa sổ đủ mẫu phù hợp hơn khi cần giá trị ổn định để theo dõi hoặc cảnh báo.

### Tỷ lệ lỗi HTTP 5xx

Tử số là tốc độ yêu cầu có mã từ `500` đến `599`. Mẫu số là tốc độ của **tất cả** yêu cầu trong cùng phạm vi và cùng cửa sổ, bao gồm cả những yêu cầu trong tử số. Chọn `5xx` khi chỉ số cần phản ánh phản hồi lỗi máy chủ. Nếu định nghĩa nghiệp vụ tính thêm mã cụ thể khác, sửa bộ lọc tử số theo định nghĩa đó. Yêu cầu thất bại ở tầng mạng hoặc cổng vào trước khi đến ứng dụng có thể không xuất hiện trong counter phía ứng dụng.

Biểu thức sau tính phần trăm theo từng `job`.

```promql
100 *
(
  sum by (job) (
    rate(http_server_requests_seconds_count{status=~"5[0-9][0-9]"}[5m])
  )
  or on (job)
  0 * sum by (job) (
    rate(http_server_requests_seconds_count[5m])
  )
)
/
(
  sum by (job) (
    rate(http_server_requests_seconds_count[5m])
  ) > 0
)
```

Hai phần của biểu thức xử lý việc thiếu chuỗi lỗi và việc không có lưu lượng.

- `or on (job) 0 * ...` giữ nguyên tốc độ 5xx khi có chuỗi tương ứng. Nếu một `job` có tốc độ tổng đo được nhưng chưa từng xuất chuỗi 5xx, biểu thức dùng 0 cho tử số. Cách này phù hợp khi việc gắn đo và thu thập hoạt động bình thường. Nếu chuỗi 5xx biến mất do thiếu mẫu hoặc do đổi nhãn, giá trị 0 có thể che lỗi thu thập. Kiểm tra trạng thái đích bằng `up` và xác nhận các chuỗi cần thiết vẫn được xuất.
- So sánh `> 0` ở mẫu số lọc bỏ các `job` có tốc độ tổng bằng 0. Phép so sánh dùng làm bộ lọc nên vẫn giữ tốc độ gốc của các `job` còn lại. Khi không có yêu cầu, tỷ lệ không xác định. Nếu cả tốc độ tổng cũng vắng do thiếu dữ liệu, truy vấn không trả tỷ lệ cho `job` đó.

Để tính theo tuyến đường, dùng `sum by (job, uri)` ở các phép cộng và `or on (job, uri)` để khớp đúng tử số với mẫu số. Khi lọc theo `job`, `uri` hoặc `method`, áp dụng các bộ lọc phạm vi giống nhau ở mọi nhánh. Chỉ nhánh đếm lỗi có thêm điều kiện `status`.

### Kiểm chứng với hai bản sao và một lần đặt lại counter

Giả sử Prometheus thu thập mỗi phút. Trong phần dữ liệu từ phút 1 đến phút 5, bản sao `a` xử lý 120 yêu cầu/phút, gồm 3 lỗi/phút. Bản sao `b` xử lý 30 yêu cầu/phút, gồm 6 lỗi/phút, và khởi động lại giữa phút 2 và phút 3. Counter mã `200` của `b` lần lượt là `300, 324, 24, 48, 72`. Mức tăng đã điều chỉnh giữa mẫu đầu và mẫu cuối là `72 − 300 + 324 = 96` trong 4 phút, tức 24 phản hồi `200` mỗi phút. Thêm 6 phản hồi `500` mỗi phút cho đúng 30 yêu cầu/phút.

| Bản sao | Yêu cầu/giây | Lỗi/giây | Tỷ lệ lỗi |
| --- | ---: | ---: | ---: |
| `a` | 2 | 0,05 | 2,5% |
| `b` | 0,5 | 0,10 | 20% |
| Cả `checkout` | 2,5 | 0,15 | 6% |

Tỷ lệ của cả dịch vụ là `100 × 0,15 / 2,5 = 6%`. Lấy trung bình cộng hai tỷ lệ riêng cho ra 11,25% vì phép tính đó cho mỗi bản sao cùng trọng số, dù `a` xử lý lượng yêu cầu gấp bốn lần `b`.

Lưu dữ liệu sau thành `request-rate.test.yml` để kiểm tra hai truy vấn bằng `promtool`. Chuỗi `catalog` có lưu lượng nhưng không có mẫu 5xx. Chuỗi `idle` có counter đứng yên. Chuỗi `late` chỉ có một mẫu, ký hiệu `_` đánh dấu những lần thu thập không có mẫu. Biểu thức phần trăm được làm tròn trong phép kiểm tra để tránh sai số biểu diễn số thực.

```yaml
rule_files: []
evaluation_interval: 1m
tests:
  - interval: 1m
    input_series:
      - series: 'http_server_requests_seconds_count{job="checkout",instance="a",status="200"}'
        values: '900 1017 1134 1251 1368 1485'
      - series: 'http_server_requests_seconds_count{job="checkout",instance="a",status="500"}'
        values: '20 23 26 29 32 35'
      - series: 'http_server_requests_seconds_count{job="checkout",instance="b",status="200"}'
        values: '276 300 324 24 48 72'
      - series: 'http_server_requests_seconds_count{job="checkout",instance="b",status="500"}'
        values: '24 30 36 6 12 18'
      - series: 'http_server_requests_seconds_count{job="catalog",instance="c",status="200"}'
        values: '100 160 220 280 340 400'
      - series: 'http_server_requests_seconds_count{job="idle",instance="d",status="200"}'
        values: '100 100 100 100 100 100'
      - series: 'http_server_requests_seconds_count{job="late",instance="e",status="200"}'
        values: '_ _ _ _ _ 42'
    promql_expr_test:
      - expr: >-
          sum by (job) (
            rate(http_server_requests_seconds_count[5m])
          )
        eval_time: 5m
        exp_samples:
          - labels: '{job="checkout"}'
            value: 2.5
          - labels: '{job="catalog"}'
            value: 1
          - labels: '{job="idle"}'
            value: 0
      - expr: >-
          round(
            100 *
            (
              sum by (job) (
                rate(http_server_requests_seconds_count{status=~"5[0-9][0-9]"}[5m])
              )
              or on (job)
              0 * sum by (job) (
                rate(http_server_requests_seconds_count[5m])
              )
            )
            /
            (
              sum by (job) (
                rate(http_server_requests_seconds_count[5m])
              ) > 0
            ),
            0.000001
          )
        eval_time: 5m
        exp_samples:
          - labels: '{job="checkout"}'
            value: 6
          - labels: '{job="catalog"}'
            value: 0
```

```bash
promtool test rules request-rate.test.yml
```

Kết quả kỳ vọng là `checkout` có 2,5 yêu cầu/giây và 6% lỗi, `catalog` có 1 yêu cầu/giây và 0% lỗi, `idle` có tốc độ 0 nhưng không có tỷ lệ, còn `late` không có đủ mẫu để tính tốc độ.

### Chọn cửa sổ và kiểm tra khi vận hành

- Cửa sổ cần chứa nhiều lần thu thập dự kiến. Nếu chu kỳ là 15 giây, `[5m]` bao phủ khoảng 20 lần thu thập theo lịch. Cửa sổ ngắn phát hiện thay đổi nhanh hơn nhưng dễ nhiễu hoặc thiếu mẫu. Cửa sổ dài làm mượt hơn và giữ ảnh hưởng của một đợt lỗi lâu hơn. Cửa sổ `[5m]` là khoảng dữ liệu tại mỗi điểm truy vấn, độc lập với bước thời gian giữa các điểm trên biểu đồ.
- Quan sát tốc độ yêu cầu và tỷ lệ lỗi cạnh nhau. Một lỗi trên một yêu cầu cho 100%, nhưng số liệu có ít lưu lượng. Khi điều kiện cảnh báo cần đủ bằng chứng, có thể kết hợp tỷ lệ lỗi với ngưỡng số yêu cầu trong cùng cửa sổ.
- Nếu biểu đồ có khoảng trống hoặc tụt bất thường, kiểm tra `up` theo đích, số mẫu và các nhãn của chuỗi thực tế. Có thể dùng `resets(http_server_requests_seconds_count[5m])` để xem counter của chuỗi nào đã giảm. Kiểm tra riêng mức độ đầy đủ của các đích, vì phép cộng vẫn có thể trả số từ các bản sao còn dữ liệu khi một bản sao bị mất.

### Tài liệu tham khảo

- [Spring Boot 3.3 Actuator — metrics HTTP và endpoint Prometheus](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html)
- [Prometheus — hàm rate, increase, irate và resets](https://prometheus.io/docs/prometheus/3.10/querying/functions/)
- [Prometheus — phép toán và khớp nhãn giữa các vector](https://prometheus.io/docs/prometheus/latest/querying/operators/)
- [Prometheus — kiểm thử biểu thức PromQL bằng promtool](https://prometheus.io/docs/prometheus/latest/configuration/unit_testing_rules/)