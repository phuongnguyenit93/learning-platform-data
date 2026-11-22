# Nhận diện counter reset, nhãn không ổn định và dữ liệu gián đoạn

Khi biểu đồ số yêu cầu tụt xuống hoặc đột nhiên đứt đoạn, hãy xem **chuỗi gốc theo từng đích thu thập**. Một bộ đếm có thể giảm trong cùng chuỗi, một lần triển khai có thể tạo chuỗi mới do đổi nhãn, hoặc Prometheus có thể thiếu mẫu. Ba hiện tượng này cần cách xác minh khác nhau.

Các ví dụ dùng `http_server_requests_seconds_count`, chuỗi số lần đo của `Timer` HTTP mà Micrometer thường xuất cho Spring Boot. `job="orders"` chỉ nhóm đích của dịch vụ và `instance` chỉ từng đích. Thay bộ lọc theo nhãn thực tế của môi trường đang kiểm tra.

| Quan sát | Dấu hiệu ở chuỗi gốc | Điểm cần kiểm tra |
| --- | --- | --- |
| Counter reset | Giá trị giảm giữa hai mẫu số liên tiếp của cùng tên và cùng bộ nhãn. | `resets()`, thời điểm tiến trình khởi động hoặc meter được tạo lại. |
| Nhãn thay đổi | Chuỗi cũ và chuỗi mới có ít nhất một nhãn khác nhau. Mỗi chuỗi có lịch sử riêng. | Tập nhãn trước và sau sự kiện, cấu hình đặt tag và cấu hình khám phá đích. |
| Dữ liệu gián đoạn | Một hoặc nhiều thời điểm thiếu mẫu cho chuỗi cần xem. | `up`, lỗi scrape, số mẫu trong cửa sổ và việc ứng dụng còn xuất metric đó hay không. |

## Counter reset trong cùng chuỗi

Counter tích lũy số lần xảy ra sự kiện. Khi tiến trình khởi động lại, counter trong bộ nhớ có thể bắt đầu lại từ 0, nhưng mẫu đầu tiên sau đó có thể đã lớn hơn 0. Ví dụ chuỗi của `app-a:8080` có bốn mẫu `100 → 112 → 5 → 18`. Prometheus diễn giải đoạn `112 → 5` là một lần đặt lại khi dùng hàm dành cho counter.

```promql
resets(http_server_requests_seconds_count{job="orders"}[15m])
```

Truy vấn trả số lần giảm quan sát được cho từng chuỗi trong cửa sổ 15 phút. Số dương là dấu hiệu để đối chiếu với thời gian khởi động, nhật ký triển khai hoặc việc tạo lại meter. Nếu counter khởi động lại rồi tăng vượt giá trị trước đó giữa hai lần scrape, hai mẫu số có thể vẫn tăng và `resets()` không thấy lần đặt lại đó.

Để tính tốc độ yêu cầu của toàn job, xử lý reset trên từng chuỗi rồi mới gộp.

```promql
sum by (job) (
  rate(http_server_requests_seconds_count{job="orders"}[5m])
)
```

`rate()` trả tốc độ trung bình tính bằng yêu cầu mỗi giây. `increase()` dùng cùng nguyên tắc xử lý reset để ước lượng mức tăng trong cửa sổ. Với bốn mẫu trên, phần tăng đã hiệu chỉnh giữa mẫu đầu và cuối là `(112 − 100) + 5 + (18 − 5) = 30` theo mô hình đặt lại về 0. Kết quả `increase()` thực tế còn phụ thuộc mốc lấy mẫu và phép ngoại suy tới ranh giới cửa sổ. Nó có thể cho số lẻ, đồng thời không khôi phục được các lượt tăng chưa được scrape trước lúc reset.

Cộng giá trị thô trước khi tính tốc độ có thể che giấu reset. Nếu một bản sao giảm 107 nhưng bản sao khác tăng 150 giữa hai lần lấy mẫu, tổng vẫn tăng 43. Tính `rate()` trên từng chuỗi giữ được dấu hiệu giảm của bản sao thứ nhất.

## Nhãn thay đổi tạo chuỗi mới

Danh tính của một chuỗi gồm **tên metric và toàn bộ bộ nhãn**. Giả sử cùng địa chỉ `app-b:8080`, trước khi triển khai có `release="v1"` với các mẫu `200 → 208`, sau đó có `release="v2"` với các mẫu `4 → 12`. Đây là hai chuỗi. `resets()` có thể trả 0 cho cả hai vì từng chuỗi đều tăng. Nếu tiến trình cũng đã khởi động lại, đó là một sự kiện cần kiểm tra độc lập với kết quả PromQL.

Để quan sát hai bộ nhãn, truy vấn tại thời điểm có sự kiện hoặc xem phạm vi thời gian bao trùm giai đoạn trước và sau.

```promql
http_server_requests_seconds_count{job="orders", instance="app-b:8080"}
```

- Với tag HTTP, dùng mẫu đường dẫn như `/orders/{id}` cho chiều phân tích `uri`. Đưa từng ID cụ thể hoặc mã yêu cầu vào nhãn làm tăng số lượng chuỗi và thường khiến mỗi chuỗi có rất ít mẫu.
- Xác định nhãn nào cần để phân biệt nguồn, như `instance`, và chiều nào cần giữ trong kết quả, như `uri`. Có thể gộp theo `job` và `uri` **sau** `rate()` nếu các chuỗi đo cùng loại yêu cầu.
- Kiểm tra cả tag do ứng dụng xuất lẫn nhãn do Prometheus gắn. Thay địa chỉ đích cũng có thể đổi `instance`. Một chuỗi mới cần có đủ mẫu để tính tốc độ, nên khi chuyển đích biểu đồ có thể gián đoạn ngắn.

## Dữ liệu gián đoạn và số 0

Giá trị 0 là một mẫu hợp lệ. Chẳng hạn một counter vẫn được scrape đều nhưng đứng yên thì tốc độ bằng 0. Khi dữ liệu bị thiếu, truy vấn có thể trả một vector rỗng. Với chuỗi được đánh dấu đã cũ (stale), bộ chọn tức thời sẽ bỏ chuỗi đó cho đến khi có mẫu mới. Một cửa sổ dài hơn đôi khi vẫn chứa các mẫu trước sự cố và còn tính được tốc độ. Điều đó chỉ cho biết cửa sổ vẫn có dữ liệu để tính.

Bắt đầu bằng tình trạng của đích. `up=1` là scrape thành công, `up=0` là lần scrape thất bại. Khi đích rời cấu hình khám phá, chuỗi `up` của nó có thể biến mất. Một lần scrape thành công chỉ xác nhận Prometheus thu được phản hồi hợp lệ từ đích. Nếu thiếu riêng một metric, kiểm tra phản hồi `/actuator/prometheus`, bộ lọc nhãn trong truy vấn và các quy tắc lọc metric khi thu thập.

```promql
up{job="orders", instance="app-a:8080"}
```

Đếm số mẫu trong cửa sổ và phát hiện khi bộ lọc cụ thể hoàn toàn thiếu mẫu.

```promql
count_over_time(http_server_requests_seconds_count{job="orders", instance="app-a:8080"}[5m])
```

```promql
absent_over_time(http_server_requests_seconds_count{job="orders", instance="app-a:8080"}[5m])
```

`count_over_time()` đếm mẫu đã lưu theo từng chuỗi. Khi bộ lọc có ít nhất một mẫu trong cửa sổ, `absent_over_time()` trả vector rỗng. Nếu toàn bộ bộ lọc thiếu mẫu, hàm trả một mẫu có giá trị 1. Khi cần phát hiện từng đích mất metric, dùng bộ lọc cho đích cụ thể hoặc đối chiếu với tập đích dự kiến. Một bộ lọc theo cả job có thể vẫn có dữ liệu từ những đích khác. Hãy giữ khoảng trống hiển thị để phân biệt thiếu dữ liệu với lưu lượng bằng 0.

## Thực hành với dữ liệu mô phỏng

Lưu cấu hình dưới đây vào `counter-series-test.yml`. Mỗi vị trí cách nhau một phút. `_` biểu thị thiếu mẫu và `stale` biểu thị dấu đánh dấu chuỗi đã cũ trong dữ liệu kiểm thử.

```yaml
rule_files: []
evaluation_interval: 1m

tests:
  - interval: 1m
    input_series:
      - series: 'http_server_requests_seconds_count{job="orders",instance="app-a:8080"}'
        values: '100 112 5 18 stale _'
      - series: 'http_server_requests_seconds_count{job="orders",instance="app-b:8080",release="v1"}'
        values: '200 208 stale _ _ _'
      - series: 'http_server_requests_seconds_count{job="orders",instance="app-b:8080",release="v2"}'
        values: '_ _ 4 12 21 30'
      - series: 'up{job="orders",instance="app-a:8080"}'
        values: '1 1 1 1 0 0'

    promql_expr_test:
      - expr: 'resets(http_server_requests_seconds_count{job="orders"}[4m])'
        eval_time: 3m
        exp_samples:
          - labels: '{instance="app-a:8080",job="orders"}'
            value: 1
          - labels: '{instance="app-b:8080",job="orders",release="v1"}'
            value: 0
          - labels: '{instance="app-b:8080",job="orders",release="v2"}'
            value: 0
      - expr: 'absent_over_time(http_server_requests_seconds_count{job="orders",instance="app-a:8080"}[90s])'
        eval_time: 5m
        exp_samples:
          - labels: '{instance="app-a:8080",job="orders"}'
            value: 1
      - expr: 'up{job="orders",instance="app-a:8080"}'
        eval_time: 5m
        exp_samples:
          - labels: 'up{instance="app-a:8080",job="orders"}'
            value: 0
```

Chạy bằng `promtool` từ bộ phân phối Prometheus.

```bash
promtool test rules counter-series-test.yml
```

Kết quả mong đợi là cả ba kiểm tra đều đạt. Ở phút 3, `app-a` có một lần giảm trong cùng chuỗi. `app-b` có hai chuỗi đều tăng dù giá trị ở đầu bản phát hành v2 thấp hơn cuối v1. Ở phút 5, cửa sổ 90 giây của `app-a` không có mẫu counter hợp lệ, còn chuỗi `up` vẫn có mẫu số 0 để ghi nhận scrape thất bại.

## Tài liệu tham khảo

- [Spring Boot 3.3 — Metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html)
- [Prometheus — Mô hình dữ liệu và bộ nhãn](https://prometheus.io/docs/concepts/data_model/)
- [Prometheus — Hàm PromQL](https://prometheus.io/docs/prometheus/latest/querying/functions/)
- [Prometheus — Dữ liệu đã cũ trong truy vấn](https://prometheus.io/docs/prometheus/latest/querying/basics/#staleness)
- [Prometheus — Job, đích thu thập và up](https://prometheus.io/docs/concepts/jobs_instances/)
- [Prometheus — Kiểm thử quy tắc và biểu thức](https://prometheus.io/docs/prometheus/latest/configuration/unit_testing_rules/)
