# Chọn cảnh báo có cửa sổ thời gian và hướng dẫn xử lý rõ ràng

## 1. Cảnh báo phải dẫn tới một quyết định

Trong vận hành production, một chỉ số vượt ngưỡng chưa đủ để gọi người trực. Cảnh báo hữu ích phải nói được **dịch vụ nào bị ảnh hưởng, tín hiệu đã xấu trong khoảng nào, ai chịu trách nhiệm và người nhận nên làm gì tiếp theo**. Nếu mỗi dao động nhỏ đều tạo thông báo nhưng không có hành động rõ ràng, người trực sẽ khó nhận ra sự cố quan trọng.

Hãy bắt đầu từ triệu chứng tác động tới người dùng: tỷ lệ yêu cầu thất bại, độ trễ không đáp ứng mục tiêu, tác vụ quan trọng không hoàn thành hoặc hàng đợi chậm tới mức vi phạm thời hạn. CPU hay số luồng là bằng chứng chẩn đoán; chúng chỉ nên trực tiếp đánh thức người trực khi đã có lý do và hành động tương ứng. [Nguyên tắc cảnh báo của Prometheus](https://prometheus.io/docs/practices/alerting/).

Bài này dùng dịch vụ minh họa `orders`, Spring Boot Actuator/Micrometer làm nguồn metric, Prometheus đánh giá điều kiện và Alertmanager định tuyến thông báo. Ngưỡng 5%, cửa sổ 5 phút và thời gian 2 phút là lựa chọn cho bài thực hành, không phải cấu hình tối ưu cho mọi production.

Chuỗi trách nhiệm cần hiểu:

```text
Ứng dụng ghi metric
  → Prometheus thu mẫu và tính biểu thức theo thời gian
  → Rule chuyển trạng thái inactive / pending / firing
  → Alertmanager gom nhóm, định tuyến và gửi thông báo
  → Người phụ trách dùng runbook để xác minh, giảm ảnh hưởng và theo dõi phục hồi
```

**Cửa sổ thời gian** quyết định dữ liệu nào được dùng để đo. **Thời gian duy trì điều kiện** quyết định khi nào rule đủ điều kiện firing. **Lịch gửi thông báo** quyết định người trực nhận tin lúc nào. **Runbook** là hướng dẫn xử lý dựa trên bằng chứng. Bốn thành phần này phải khớp với nhau.

## 2. Chọn tín hiệu và mức phản ứng

Trước khi viết PromQL, điền một hợp đồng ngắn cho từng cảnh báo:

| Thành phần | Câu hỏi phải trả lời | Ví dụ |
| --- | --- | --- |
| Ảnh hưởng | Người dùng không làm được việc gì? | Một phần yêu cầu đặt hàng trả HTTP 5xx |
| Phạm vi | Môi trường, dịch vụ và nhóm nghiệp vụ nào? | `job=orders`, `env=prod` |
| Phép đo | Tử số, mẫu số, đơn vị và dữ liệu bị loại là gì? | Tốc độ 5xx / tốc độ mọi HTTP request, bỏ Actuator |
| Thời gian | Đo trên cửa sổ nào, đánh giá mỗi bao lâu? | Cửa sổ 5m, đánh giá 30s/lần |
| Ngưỡng | Vì sao con số này biểu thị ảnh hưởng đáng xử lý? | Hơn 5%, lưu lượng ít nhất 1 request/giây trong ví dụ |
| Chủ sở hữu | Nhóm nào nhận và chịu trách nhiệm? | Nhóm Orders |
| Hành động | Người trực thực hiện bước nào đầu tiên? | Kiểm tra phạm vi lỗi, thay đổi gần đây và phụ thuộc liên quan |
| Phục hồi | Điều gì chứng minh sự cố đã hết? | Metric còn mới, tỷ lệ lỗi giảm và nghiệp vụ kiểm tra thành công |

Phân biệt mức độ cần xử lý:

- **Page:** cần phản ứng sớm, có ảnh hưởng hoặc rủi ro nghiêm trọng và có người trực chịu trách nhiệm.
- **Warning/ticket:** cần điều tra nhưng chưa nhất thiết đánh thức người trực ngay, ví dụ mất metric của một bản sao khi dịch vụ vẫn còn hoạt động.
- **Dashboard/log:** phục vụ quan sát và tìm nguyên nhân; không phải mọi thay đổi đều cần thông báo.

`severity` là nhãn do nhóm định nghĩa; gán `severity: page` không tự tạo cuộc gọi hay gửi tin. Alertmanager phải có route và receiver tương ứng.

Không cộng trung bình tỷ lệ lỗi của các bản sao một cách ngang nhau. Một bản sao có 1 lỗi/1 request không có cùng trọng số với một bản sao có 1 lỗi/10.000 request. Tính tổng số/tốc độ lỗi rồi chia tổng số/tốc độ request trong cùng phạm vi.

## 3. Không nhầm các loại thời gian

| Tham số | Vai trò | Ví dụ |
| --- | --- | --- |
| `scrape_interval` | Khoảng cách giữa các lần Prometheus lấy mẫu | 15s |
| Cửa sổ `[5m]` | Khoảng lịch sử đưa vào phép đo tại mỗi lần đánh giá | `rate(counter[5m])` |
| Khoảng đánh giá rule | Bao lâu tính lại điều kiện một lần | 30s |
| `for: 2m` | Cùng một bộ nhãn phải tiếp tục thỏa điều kiện qua các lần đánh giá đủ 2m | Pending rồi mới firing |
| `group_wait` | Chờ gom một nhóm thông báo mới | 30s minh họa |
| `group_interval` | Nhịp xem xét gửi cập nhật cho nhóm đã tồn tại | 5m minh họa |
| `repeat_interval` | Khoảng nhắc lại khi nhóm vẫn chưa thay đổi đáng kể | 4h minh họa |

`for` không phải cửa sổ lấy trung bình. `rate(...[5m]) > 0.05` kết hợp `for: 2m` nghĩa là kết quả đo theo cửa sổ trượt phải tiếp tục thỏa điều kiện đủ thời gian; không phải “có lỗi liên tục trong 7 phút”. Một đợt lỗi ngắn nhưng lớn vẫn có thể giữ tỷ lệ của cửa sổ 5m vượt ngưỡng đủ 2m. [Ngữ nghĩa alerting rule](https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/).

Ví dụ với `up == 0` và `for: 2m`, không có cửa sổ `rate`:

| Thời điểm | Dữ liệu đầu vào | Trạng thái mong đợi |
| --- | --- | --- |
| 0m | `up=1` | Inactive |
| 1m | `up=0` lần đầu | Pending |
| 2m | Vẫn `up=0` | Pending |
| 3m | Điều kiện giữ đủ 2m | Firing |
| 4m | `up=1` | Hết firing nếu không cấu hình giữ firing thêm |

Nếu điều kiện mất ở giữa giai đoạn pending, thời gian `for` phải bắt đầu lại khi nó xuất hiện lại. Đây là sự liên tục của **kết quả biểu thức tại các lần đánh giá**, không phải quan sát liên tục mọi thời điểm giữa hai lần lấy mẫu.

Các tham số `group_wait/group_interval/repeat_interval` thuộc Alertmanager, không thay đổi cửa sổ PromQL hay thay thế `for`. Thời điểm nhận tin còn chịu ảnh hưởng của gom nhóm, route, ức chế, tạm tắt thông báo và lỗi giao nhận. Đừng hứa thời gian phát hiện chính xác bằng phép cộng 5m + 2m + 30s. [Lịch thông báo trong Alertmanager](https://prometheus.io/docs/alerting/latest/configuration/).

Một số phiên bản hỗ trợ `keep_firing_for` để giữ firing thêm sau khi điều kiện không còn thỏa. Đó là chính sách chống dao động khi kết thúc cảnh báo, không chứng minh dịch vụ đã phục hồi. Ví dụ ở đây không dùng tùy chọn này; phải kiểm tra phiên bản công cụ trước khi bổ sung.

## 4. Xác nhận nguồn metric của Actuator

Với ứng dụng web Spring Boot hiện có, cần Actuator và registry Prometheus. Trong Gradle dùng các dependency do Spring Boot quản lý phiên bản:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
```

Cho phép endpoint cần thiết trong cấu hình ứng dụng:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,prometheus
```

Spring Boot ghi nhận HTTP request với tên Micrometer `http.server.requests`; Prometheus thường nhận bộ đếm `http_server_requests_seconds_count`. Phải kiểm tra tên và nhãn thực tế tại `/actuator/prometheus` vì ứng dụng có thể tùy chỉnh chúng. `/actuator/metrics` là công cụ chẩn đoán, không phải kho lịch sử để rule tính cửa sổ thời gian. [Metrics của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html).

Ví dụ này giả định nhãn `status` chứa mã HTTP và `uri` dùng mẫu đường dẫn. Lọc `uri!~"/actuator.*"` bỏ các đường quản trị có tiền tố đó. Nếu ứng dụng đổi base path hoặc tên nhãn, phải sửa cả tử số và mẫu số cùng nhau.

`job` và `instance` là các nhãn Prometheus gắn theo đích thu thập. Nhãn `env` trong ví dụ được khai báo ở cấu hình scrape; không giả định Spring Boot tự thêm nó. `up=0` có nghĩa lần scrape thất bại, không tự chứng minh nghiệp vụ hỏng hay readiness đang từ chối tải. [Job, instance và chuỗi tự sinh](https://prometheus.io/docs/concepts/jobs_instances/).

Tệp `prometheus.yml` tối thiểu cho thí nghiệm cục bộ:

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 30s
rule_files:
  - alerts.yml
scrape_configs:
  - job_name: orders
    metrics_path: /actuator/prometheus
    static_configs:
      - targets: ["127.0.0.1:8080"]
        labels:
          env: prod
```

Nhãn `prod` ở đây chỉ để mô phỏng bộ lọc production; địa chỉ vẫn là máy cục bộ. Cấu hình này nạp rule nhưng chưa khai báo Alertmanager, nên chưa phải tuyến gửi thông báo hoàn chỉnh. Endpoint phải truy cập được theo cơ chế xác thực/mạng của ứng dụng; không lấy lỗi 401/403 của scrape làm bằng chứng request nghiệp vụ thất bại.

## 5. Bộ rule có hợp đồng rõ ràng

Lưu nội dung sau vào `alerts.yml`. Ba rule tách ba câu hỏi: request đã xử lý có lỗi cao không, một đích còn thu được dữ liệu không, và toàn bộ job còn có mẫu `up` không.

```yaml
groups:
  - name: orders-production
    interval: 30s
    rules:
      - alert: OrdersHigh5xxRatio
        expr: |
          (
            sum by (job, env) (
              rate(http_server_requests_seconds_count{
                job="orders", env="prod", status=~"5..",
                uri!~"/actuator.*"
              }[5m])
            )
            /
            sum by (job, env) (
              rate(http_server_requests_seconds_count{
                job="orders", env="prod", uri!~"/actuator.*"
              }[5m])
            )
          ) > 0.05
          and on (job, env)
          sum by (job, env) (
            rate(http_server_requests_seconds_count{
              job="orders", env="prod", uri!~"/actuator.*"
            }[5m])
          ) >= 1
        for: 2m
        labels:
          service: orders
          team: orders
          severity: page
        annotations:
          summary: "Orders có tỷ lệ HTTP 5xx cao"
          description: "Tỷ lệ 5xx vượt 5% trong 5m, lưu lượng ít nhất 1 req/s, điều kiện giữ 2m."
          runbook_id: "orders-high-5xx"

      - alert: OrdersMetricsUnreachable
        expr: up{job="orders", env="prod"} == 0
        for: 2m
        labels:
          service: orders
          team: orders
          severity: warning
        annotations:
          summary: "Không lấy được metric của một bản sao Orders"
          description: "Scrape thất bại liên tục 2m; chưa kết luận nghiệp vụ ngừng hoạt động."
          runbook_id: "orders-metrics-unreachable"

      - alert: OrdersMetricsMissing
        expr: absent_over_time(up{job="orders", env="prod"}[5m])
        for: 1m
        labels:
          service: orders
          team: orders
          severity: warning
        annotations:
          summary: "Mất toàn bộ chuỗi up của job Orders"
          description: "Không có mẫu up trong cửa sổ 5m và điều kiện thiếu mẫu giữ thêm 1m."
          runbook_id: "orders-metrics-missing"
```

### 5.1. Tỷ lệ 5xx và điều kiện lưu lượng

Rule đầu tính tốc độ tăng của từng chuỗi counter bằng `rate` rồi mới cộng. Cách này giữ khả năng xử lý counter reset ở từng bản sao. Tử số và mẫu số có cùng bộ lọc phạm vi, trừ điều kiện `status` của tử số. [Hàm rate của Prometheus](https://prometheus.io/docs/prometheus/latest/querying/functions/#rate).

`sum by (job, env)` gom các bản sao, đường dẫn và trạng thái trong cùng dịch vụ/môi trường. `and on (job, env)` ghép điều kiện đủ lưu lượng với đúng tỷ lệ của phạm vi đó. Biểu thức so sánh không dùng `bool` nên nó lọc những phần tử không thỏa điều kiện.

Không đổi thành `ratio > bool 0.05` rồi dùng trực tiếp làm alert: kết quả có giá trị 0 vẫn là phần tử tồn tại trong vector, trong khi alert xét sự tồn tại của phần tử. Nếu dùng kết quả boolean trung gian, phải có phép lọc cuối phù hợp. [So sánh và phép ghép vector](https://prometheus.io/docs/prometheus/latest/querying/operators/).

Một request lỗi trong một request là 100%, nhưng chưa chắc đủ bằng chứng để page theo cùng chính sách với hàng nghìn request. Điều kiện ít nhất 1 req/s giảm nhiễu cho ví dụ; nó cũng tạo điểm mù cho dịch vụ ít lưu lượng hoặc khi request không tới được ứng dụng. Các dịch vụ đó cần kiểm tra tổng hợp từ bên ngoài, tín hiệu nghiệp vụ hoặc chính sách lưu lượng thấp riêng.

Không áp dụng “mọi 4xx đều là lỗi hệ thống”. Nếu nghiệp vụ coi một số mã 4xx là thất bại của dịch vụ, định nghĩa tập request tốt/xấu phù hợp trước khi viết rule. HTTP 5xx cũng chưa phản ánh mọi lỗi nghiệp vụ trả nhầm 200 hoặc lỗi xảy ra trước khi request tới ứng dụng.

### 5.2. Không có dữ liệu khác với giá trị bằng 0

`OrdersMetricsUnreachable` chỉ hoạt động khi chuỗi `up` còn tồn tại và có giá trị 0. Nếu đích bị loại khỏi service discovery, chuỗi có thể biến mất; `up == 0` không còn phần tử để phát cảnh báo.

`OrdersMetricsMissing` kiểm tra không có mẫu `up` của toàn job trong cửa sổ 5m rồi yêu cầu điều kiện giữ thêm 1m. Nó phát hiện mất toàn bộ job, không phát hiện riêng một bản sao mất khỏi danh sách nếu các bản sao khác vẫn có mẫu. Muốn kiểm tra từng đích dự kiến phải có nguồn kiểm kê đáng tin cậy để đối chiếu. [Hàm absent_over_time](https://prometheus.io/docs/prometheus/latest/querying/functions/#absent_over_time).

Bộ đếm đứng yên, không có chuỗi 5xx và mất mọi metric là ba trường hợp khác nhau. Không thay mọi dữ liệu thiếu bằng số 0 để làm dashboard xanh. Các rule này cũng không giám sát được việc chính Prometheus ngừng đánh giá; cần tuyến giám sát độc lập cho hệ thống cảnh báo.

## 6. Kiểm thử cửa sổ và vòng đời cảnh báo

Cú pháp đúng chưa chứng minh thời gian đúng. Lưu tệp tiếp theo thành `alerts.test.yml`. Dữ liệu giả được lấy mỗi 1m để dễ đọc; rule vẫn đánh giá mỗi 30s. Nó không thay thế giá trị `scrape_interval=15s` của ví dụ chạy thật.

```yaml
rule_files:
  - alerts.yml
evaluation_interval: 30s
tests:
  - name: sustained-errors-and-recovery
    interval: 1m
    input_series:
      - series: "http_server_requests_seconds_count{job=\"orders\",env=\"prod\",instance=\"orders-1:8080\",uri=\"/orders\",status=\"200\"}"
        values: "0+540x10 6000+600x10"
      - series: "http_server_requests_seconds_count{job=\"orders\",env=\"prod\",instance=\"orders-1:8080\",uri=\"/orders\",status=\"500\"}"
        values: "0+60x10 600+0x10"
    alert_rule_test:
      - eval_time: 2m
        alertname: OrdersHigh5xxRatio
        exp_alerts: []
      - eval_time: 3m
        alertname: OrdersHigh5xxRatio
        exp_alerts:
          - exp_labels:
              job: "orders"
              env: "prod"
              service: "orders"
              team: "orders"
              severity: "page"
            exp_annotations:
              summary: "Orders có tỷ lệ HTTP 5xx cao"
              description: "Tỷ lệ 5xx vượt 5% trong 5m, lưu lượng ít nhất 1 req/s, điều kiện giữ 2m."
              runbook_id: "orders-high-5xx"
      - eval_time: 10m
        alertname: OrdersHigh5xxRatio
        exp_alerts:
          - exp_labels:
              job: "orders"
              env: "prod"
              service: "orders"
              team: "orders"
              severity: "page"
            exp_annotations:
              summary: "Orders có tỷ lệ HTTP 5xx cao"
              description: "Tỷ lệ 5xx vượt 5% trong 5m, lưu lượng ít nhất 1 req/s, điều kiện giữ 2m."
              runbook_id: "orders-high-5xx"
      - eval_time: 16m
        alertname: OrdersHigh5xxRatio
        exp_alerts: []
  - name: low-traffic-is-not-paged
    interval: 1m
    input_series:
      - series: "http_server_requests_seconds_count{job=\"orders\",env=\"prod\",instance=\"orders-1:8080\",uri=\"/orders\",status=\"500\"}"
        values: "0+1x15"
    alert_rule_test:
      - eval_time: 10m
        alertname: OrdersHigh5xxRatio
        exp_alerts: []
  - name: healthy-without-a-5xx-series
    interval: 1m
    input_series:
      - series: "http_server_requests_seconds_count{job=\"orders\",env=\"prod\",instance=\"orders-1:8080\",uri=\"/orders\",status=\"200\"}"
        values: "0+600x15"
    alert_rule_test:
      - eval_time: 10m
        alertname: OrdersHigh5xxRatio
        exp_alerts: []
  - name: zero-traffic-is-not-success-evidence
    interval: 1m
    input_series:
      - series: "http_server_requests_seconds_count{job=\"orders\",env=\"prod\",instance=\"orders-1:8080\",uri=\"/orders\",status=\"200\"}"
        values: "0+0x15"
      - series: "http_server_requests_seconds_count{job=\"orders\",env=\"prod\",instance=\"orders-1:8080\",uri=\"/orders\",status=\"500\"}"
        values: "0+0x15"
    alert_rule_test:
      - eval_time: 10m
        alertname: OrdersHigh5xxRatio
        exp_alerts: []
  - name: brief-scrape-failure-resets-pending
    interval: 1m
    input_series:
      - series: "up{job=\"orders\",env=\"prod\",instance=\"orders-1:8080\"}"
        values: "1 0 1 1 1"
    alert_rule_test:
      - eval_time: 2m
        alertname: OrdersMetricsUnreachable
        exp_alerts: []
      - eval_time: 3m
        alertname: OrdersMetricsUnreachable
        exp_alerts: []
  - name: sustained-scrape-failure-and-recovery
    interval: 1m
    input_series:
      - series: "up{job=\"orders\",env=\"prod\",instance=\"orders-1:8080\"}"
        values: "1 0 0 0 1"
    alert_rule_test:
      - eval_time: 2m
        alertname: OrdersMetricsUnreachable
        exp_alerts: []
      - eval_time: 3m
        alertname: OrdersMetricsUnreachable
        exp_alerts:
          - exp_labels:
              job: "orders"
              env: "prod"
              instance: "orders-1:8080"
              service: "orders"
              team: "orders"
              severity: "warning"
            exp_annotations:
              summary: "Không lấy được metric của một bản sao Orders"
              description: "Scrape thất bại liên tục 2m; chưa kết luận nghiệp vụ ngừng hoạt động."
              runbook_id: "orders-metrics-unreachable"
      - eval_time: 4m
        alertname: OrdersMetricsUnreachable
        exp_alerts: []
  - name: target-disappears-from-discovery
    interval: 1m
    input_series:
      - series: "up{job=\"orders\",env=\"prod\",instance=\"orders-1:8080\"}"
        values: "1 1 stale _ _ _ _ _ _"
    alert_rule_test:
      - eval_time: 5m
        alertname: OrdersMetricsMissing
        exp_alerts: []
      - eval_time: 7m
        alertname: OrdersMetricsMissing
        exp_alerts:
          - exp_labels:
              job: "orders"
              env: "prod"
              service: "orders"
              team: "orders"
              severity: "warning"
            exp_annotations:
              summary: "Mất toàn bộ chuỗi up của job Orders"
              description: "Không có mẫu up trong cửa sổ 5m và điều kiện thiếu mẫu giữ thêm 1m."
              runbook_id: "orders-metrics-missing"
      - eval_time: 7m
        alertname: OrdersMetricsUnreachable
        exp_alerts: []
      - eval_time: 7m
        alertname: OrdersHigh5xxRatio
        exp_alerts: []
```

### 6.1. Chạy kiểm tra

Dùng `promtool` cùng phiên bản với Prometheus dự kiến nạp rule; bộ ví dụ này được kiểm tra bằng promtool 3.2.1. Không cần khởi động Prometheus, ứng dụng Java hoặc gửi thông báo để chạy các unit test này.

Trên Linux/macOS, khi `promtool` có trong PATH:

```shell
promtool check config prometheus.yml
promtool check rules alerts.yml
promtool test rules alerts.test.yml
```

Trên PowerShell, nếu `promtool.exe` nằm trong thư mục hiện tại:

```powershell
.\promtool.exe check config prometheus.yml
.\promtool.exe check rules alerts.yml
.\promtool.exe test rules alerts.test.yml
```

Kết quả kiểm tra tệp rule:

```text
Checking alerts.yml
  SUCCESS: 3 rules found
```

Kết quả chạy tệp test:

```text
  SUCCESS
```

Các lệnh phải trả exit code 0. Test kiểm tra cả nhãn và annotation mong đợi, nên nếu đổi nội dung mô tả hay nhóm sở hữu phải cập nhật kỳ vọng có chủ đích. Cách khai báo dữ liệu và kiểm tra rule được mô tả trong [tài liệu unit test Prometheus](https://prometheus.io/docs/prometheus/latest/configuration/unit_testing_rules/).

### 6.2. Đọc bảy tình huống

| Kịch bản | Bằng chứng mong đợi |
| --- | --- |
| Lỗi kéo dài rồi phục hồi | 2m chưa firing; 3m và 10m firing; 16m đã hết |
| Lưu lượng thấp | Dù toàn bộ request là lỗi, không page theo chính sách có điều kiện lưu lượng này |
| Không có chuỗi 5xx | Chỉ có request tốt thì không phát cảnh báo tỷ lệ lỗi |
| Không có request | Không phát cảnh báo tỷ lệ; không diễn giải đó là bằng chứng dịch vụ khỏe |
| Scrape lỗi ngắn | Pending bị ngắt, không firing |
| Scrape lỗi kéo dài | 2m còn pending, 3m firing, 4m phục hồi |
| Đích biến mất | Rule mất mẫu firing; rule `up == 0` không thay thế được nó |

`0+540x10` biểu diễn 11 mẫu, bắt đầu từ 0 và tăng 540 mỗi phút. Cùng chuỗi lỗi tăng 60/phút, đó là 600 request/phút, trong đó 10% là 5xx. Sau giai đoạn lỗi, chuỗi 5xx đứng yên còn request thành công tiếp tục tăng để kiểm tra phục hồi.

`stale` biểu diễn chuỗi đã không còn hiện hành; `_` biểu diễn thiếu mẫu. Trong kịch bản cuối, mẫu `up` thật cuối cùng ở 1m. Đến 6m, cửa sổ 5m không còn mẫu thật đó; sau `for: 1m`, test kiểm tra firing ở 7m. Đây không phải lời hứa “luôn chờ 6 phút từ lúc bắt đầu Prometheus”: nếu mới khởi động và chưa từng có lịch sử, biểu thức thiếu mẫu có thể thỏa ngay. Chính sách khởi tạo/bảo trì phải được xác định riêng.

Bảy nhóm test có tổng cộng 16 điểm kiểm tra. Chúng xác minh phép tính, nhãn, annotation và trạng thái firing tại các mốc đã chọn; không chứng minh service discovery thật, scrape thực tế, route Alertmanager hoặc người trực đã nhận tin. Tuyến thông báo cần một kiểm thử tích hợp riêng trong kênh thử nghiệm, với người nhận và nội dung đã được xác định.

## 7. Runbook phải cụ thể tới bước tiếp theo

Trong ví dụ, `runbook_id` trỏ tới ba hướng dẫn ngay dưới đây. Khi đưa vào hệ thống của nhóm, lưu chúng ở nơi người trực truy cập được rồi thêm `runbook_url` bằng đường dẫn thực tế. Không gắn một URL chỉ trông giống tài liệu nhưng chưa có nội dung hoặc người trực không có quyền đọc.

### 7.1. `orders-high-5xx` — tỷ lệ lỗi cao

**Chủ sở hữu:** nhóm Orders; người đang trực tiếp nhận xử lý. **Mức độ:** page theo chính sách ví dụ. **Ý nghĩa:** trong `job=orders, env=prod`, tỷ lệ HTTP 5xx trên cửa sổ 5m vượt 5%, với lưu lượng ít nhất 1 request/giây, và kết quả biểu thức giữ đủ 2m.

**Bước đầu, trong 5 phút kể từ khi tiếp nhận:**

1. Ghi thời điểm bắt đầu, nhãn của cảnh báo và phạm vi người dùng bị ảnh hưởng. Kiểm tra có cảnh báo từ gateway/đường gọi bên ngoài hay không; đừng chỉ nhìn ứng dụng tự báo.
2. Mở cùng khoảng thời gian trên dashboard. Xem riêng tử số 5xx, tổng lưu lượng và tỷ lệ. Xác minh mẫu còn mới và những đích dự kiến vẫn được scrape.
3. Tách theo đường dẫn, trạng thái và bản sao để biết lỗi tập trung hay lan rộng. Đối chiếu thời điểm triển khai, thay đổi cấu hình và sự cố phụ thuộc.
4. Kiểm tra một thao tác nghiệp vụ đại diện. Ưu tiên thao tác đọc hoặc tài khoản kiểm thử phù hợp; không lặp lại tác vụ có thể tạo đơn hàng/giao dịch trùng chỉ để xác nhận lỗi.

Biểu thức chẩn đoán có thể chạy trong Prometheus:

```promql
sum by (instance, uri, status) (
  rate(http_server_requests_seconds_count{
    job="orders", env="prod", status=~"5..", uri!~"/actuator.*"
  }[5m])
)
```

Đây là tốc độ lỗi để tìm phạm vi, không phải tỷ lệ lỗi và không thay thế rule chính. Chỉ thêm các chiều có số lượng giá trị được kiểm soát; không tạo nhãn theo user ID, order ID hay URL chứa định danh.

**Chọn hành động theo bằng chứng:**

| Bằng chứng | Hành động tiếp theo |
| --- | --- |
| Lỗi bắt đầu sau bản phát hành và tập trung ở phiên bản mới | Đối chiếu thay đổi; chỉ rollback theo quy trình đã có khi xác nhận tương thích dữ liệu/cấu hình và phiên bản trước còn phù hợp |
| Nhiều bản sao cùng lỗi khi gọi một phụ thuộc | Xác minh phụ thuộc, chuyển cho nhóm phụ trách; dùng cơ chế xử lý thay thế đã được thiết kế nếu đáp ứng yêu cầu nghiệp vụ |
| Pool/kết nối/luồng bị bão hòa | Xác định nút thắt trước khi tăng tải hoặc số bản sao; thêm ứng dụng có thể làm phụ thuộc quá tải hơn |
| Chỉ một đường dẫn gặp lỗi | Ưu tiên phạm vi đó; kiểm tra mã lỗi, đầu vào và phiên bản liên quan thay vì thay đổi toàn hệ thống |
| Chưa xác định được nguyên nhân sau 5 phút hoặc ảnh hưởng tăng nhanh | Chuyển cho trưởng ca/đầu mối sự cố của nhóm Orders, kèm thời điểm, phạm vi, số liệu và các bước đã thử |

Không dùng restart đồng loạt như bước mặc định: nó có thể làm mất bằng chứng và không xử lý được nguyên nhân chung. Mỗi thay đổi giảm ảnh hưởng cần có người chịu trách nhiệm, thời điểm thực hiện, kết quả đo sau thay đổi và cách quay lại nếu xấu hơn.

**Điều kiện xác nhận phục hồi:**

- Mẫu metric còn mới và đích thu thập dự kiến vẫn tồn tại.
- Tỷ lệ 5xx giảm trong khi có đủ lưu lượng để đánh giá; nghiệp vụ kiểm tra hoạt động.
- Không có tín hiệu độc lập cho thấy gateway hoặc người dùng vẫn lỗi.
- Theo dõi thêm ít nhất 10 phút trong bài thực hành này; production phải chọn khoảng theo rủi ro và chu kỳ tải của dịch vụ.

Rule hết firing chưa đủ: nó có thể hết vì tổng lưu lượng tụt dưới điều kiện tối thiểu hoặc dữ liệu biến mất. Nếu traffic biến mất cùng lỗi, chuyển sang điều tra truy cập từ ngoài/đường thu metric thay vì kết luận đã khỏe.

Sau sự cố, lưu diễn biến, nguyên nhân, hành động có hiệu quả và điểm cần sửa trong rule/runbook. Đừng tăng ngưỡng chỉ để giảm số lần bị gọi mà chưa đánh giá ảnh hưởng bị bỏ sót.

### 7.2. `orders-metrics-unreachable` — scrape thất bại

**Chủ sở hữu:** nhóm Orders, phối hợp nhóm vận hành hệ thống giám sát khi lỗi nằm ở đường thu thập. **Mức độ:** warning trong ví dụ; nâng mức nếu mất khả năng quan sát nghiêm trọng hoặc có bằng chứng nghiệp vụ cũng hỏng.

1. Xác nhận `instance` bị ảnh hưởng và xem lỗi lần scrape trong trang Targets của Prometheus.
2. Phân biệt lỗi kết nối/quá hạn, mã 401/403, sai đường dẫn hoặc định dạng metric không hợp lệ. Kiểm tra từ cùng môi trường mạng của bộ thu; gọi thành công từ máy cá nhân chưa chứng minh đường scrape hoạt động.
3. Kiểm tra cổng ứng dụng, cấu hình endpoint, thay đổi xác thực/TLS và mức bão hòa. Không bỏ cơ chế xác thực để làm `up` chuyển thành 1.
4. Đối chiếu request nghiệp vụ và các bản sao còn lại. Nếu có ảnh hưởng người dùng, chuyển sang runbook tỷ lệ lỗi/không truy cập được phù hợp, không chỉ sửa dashboard.
5. Chuyển cho nhóm sở hữu mạng/giám sát khi đã xác định lỗi thuộc tầng đó, kèm target, thời điểm và lỗi scrape cụ thể.

**Phục hồi:** `up=1` qua nhiều lần scrape liên tiếp, metric cần thiết thực sự có lại và dữ liệu còn mới. Trong thí nghiệm có thể dùng ít nhất ba lần scrape thành công; khoảng theo dõi production phải được nhóm thống nhất. Một lần lấy được HTTP 200 nhưng mất metric nghiệp vụ chưa hoàn tất việc phục hồi quan sát.

### 7.3. `orders-metrics-missing` — toàn job không có mẫu

**Chủ sở hữu:** nhóm Orders phối hợp nhóm giám sát. **Ý nghĩa:** không có mẫu `up` cho toàn bộ bộ lọc job/môi trường trong cửa sổ đã chọn; không phải kết luận mọi máy chủ đều tắt.

1. Kiểm tra job có còn trong cấu hình và service discovery không, nhãn `job/env` có đổi không, và Prometheus có đang đánh giá rule bình thường không.
2. Đối chiếu số lượng bản sao được mong đợi từ nguồn kiểm kê/triển khai. Phân biệt dịch vụ cố ý dừng với bị mất khỏi khám phá đích.
3. Nếu có remote write hoặc tầng truy vấn trung gian, kiểm tra độ trễ dữ liệu và bộ lọc nhãn ở đúng nơi rule chạy. Dữ liệu ở một Prometheus khác không tự xuất hiện tại nơi đang đánh giá.
4. Kiểm tra nghiệp vụ qua tuyến độc lập; nếu cả tuyến quan sát và tuyến phục vụ đều lỗi, nâng mức theo chính sách sự cố.
5. Sửa đúng cấu hình/đường truyền có bằng chứng, sau đó xác nhận cả danh sách đích và chuỗi metric đã trở lại.

**Phục hồi:** có đủ đích theo kiểm kê, mẫu `up` mới và metric nghiệp vụ cập nhật. Một chuỗi bất kỳ xuất hiện làm `absent_over_time` không còn thỏa chưa chứng minh mọi bản sao dự kiến đã được khôi phục.

## 8. Chọn cửa sổ phù hợp rủi ro

Cửa sổ ngắn phản ứng nhanh nhưng dễ bị dao động; cửa sổ dài làm mượt dữ liệu nhưng có thể phát hiện chậm và giữ kết quả xấu sau khi sự cố đã hết. Tăng `for` vô hạn để giảm nhiễu cũng có thể trì hoãn cả sự cố nghiêm trọng. Hãy kiểm thử trên các dạng tải và sự cố thực tế, không chỉ một đường tăng tuyến tính.

| Tình huống | Hướng lựa chọn |
| --- | --- |
| Lỗi người dùng rõ và nhiều request | Cửa sổ đủ ngắn để phản ứng, có ngưỡng gắn với ảnh hưởng |
| Dịch vụ rất ít request | Không phụ thuộc duy nhất vào tỷ lệ; thêm kiểm tra nghiệp vụ/tổng hợp từ ngoài |
| Xử lý lô chạy mỗi vài giờ | Dựa vào lần hoàn thành gần nhất và hạn nghiệp vụ, không page vì tốc độ HTTP bằng 0 |
| Sắp hết dung lượng | Ước lượng thời gian còn lại và hành động mở rộng/dọn dẹp có thể thực hiện |
| Mất đường đo | Cảnh báo chất lượng dữ liệu/đường thu riêng với cảnh báo hiệu năng |

Nếu đã có mục tiêu độ tin cậy (SLO), có thể chọn cảnh báo dựa trên tốc độ tiêu thụ ngân sách lỗi (burn rate). Với mục tiêu 99,9%, tỷ lệ lỗi cho phép là 0,001; nếu tỷ lệ lỗi thực tế 1% thì burn rate bằng `0,01 / 0,001 = 10`. Đây là phép so sánh với ngân sách, không phải “10% lỗi”.

Một chính sách có thể yêu cầu cùng ngưỡng burn rate ở cửa sổ dài để xác nhận mức tiêu thụ đáng kể và cửa sổ ngắn để xác nhận sự cố vẫn đang diễn ra. Điều đó khác việc dùng một cửa sổ rồi thêm `for`. Phải chọn cặp cửa sổ, ngưỡng và mức page/ticket theo SLO, chi phí phản ứng và lưu lượng; không thay rule minh họa 5% bằng một con số sao chép mà chưa định nghĩa tập sự kiện tốt/xấu. [Google SRE: cảnh báo theo SLO](https://sre.google/workbook/alerting-on-slos/).

Với độ trễ, xác định rõ mục tiêu là trung bình, phân vị hay tỷ lệ request đáp ứng thời hạn. Không lấy trung bình các p95 của từng bản sao làm p95 toàn dịch vụ. Chọn dữ liệu histogram phù hợp và kiểm tra có đủ mẫu trước khi đặt cảnh báo phân vị; tên cửa sổ “5m” không tự làm một phép đo ít dữ liệu trở nên đáng tin.

## 9. Giữ thông báo ít nhiễu nhưng không che sự cố

- Giữ nhãn định tuyến/định danh ổn định: môi trường, dịch vụ, nhóm, mức độ và phạm vi cần xử lý. Đưa giá trị đo, mô tả dài và liên kết runbook vào annotation. Giá trị biến đổi liên tục trong label có thể tạo các cảnh báo mới và phá tính liên tục của `for`.
- Gom nhóm theo phạm vi có chung hành động, ví dụ `alertname, job, env`; không gom production và môi trường thử nghiệm thành một thông báo thiếu ngữ cảnh.
- Dùng ức chế (inhibition) khi một sự cố gốc đã giải thích các cảnh báo phụ, với bộ lọc nhãn đủ hẹp. Không ức chế luôn tín hiệu độc lập về ảnh hưởng người dùng chỉ vì CPU cao.
- Tạm tắt thông báo (silence) cần phạm vi, người sở hữu, lý do và thời hạn. Silence không sửa điều kiện, không biến firing thành phục hồi và không thay thế việc theo dõi sự cố.
- Theo dõi chính tuyến cảnh báo: lần đánh giá thành công, dữ liệu đầu vào, Prometheus, Alertmanager và kết quả giao nhận. Không thể dựa hoàn toàn vào một hệ thống để tự báo khi chính nó ngừng chạy.

Trong bài này, các mốc nhóm thông báo chỉ dùng để giải thích vai trò. Muốn kiểm thử tuyến gửi thật phải có cấu hình receiver, kênh thử nghiệm và bằng chứng nhận thành công. Một unit test PromQL PASS chưa chứng minh người trực nhận được page.

## 10. Kiểm tra trước khi đưa rule vào vận hành

1. Đối chiếu tên metric, kiểu dữ liệu, nhãn và phạm vi với scrape thực tế; xác nhận tử số/mẫu số cùng đo một tập request.
2. Chạy kiểm tra cú pháp và test điều kiện ngưỡng, pending, firing, phục hồi, lưu lượng thấp và thiếu dữ liệu. Thêm tình huống reset counter, nhiều bản sao và lỗi theo từng đường dẫn khi áp dụng cho dịch vụ thật.
3. Đánh giá trên lịch sử tải có sẵn và giai đoạn quan sát có người phụ trách để biết số thông báo, tốc độ phát hiện và sự cố bị bỏ sót. Chọn độ dài quan sát đủ chứa chu kỳ tải quan trọng.
4. Kiểm tra route/receiver bằng kênh thử nghiệm đã xác định; xác nhận đúng nhóm nhận, thời điểm, nội dung và thông báo phục hồi khi được cấu hình.
5. Để người trực thử làm theo runbook mà không cần người viết giải thích miệng. Sửa bước nào thiếu điều kiện, đường dẫn không truy cập được hoặc tiêu chí kết thúc mơ hồ.
6. Chỉ thay đổi ngưỡng/cửa sổ sau khi nêu được ảnh hưởng tới nhiễu, thời gian phát hiện và điểm mù; lưu thay đổi cùng kết quả kiểm thử.

## 11. Bài tập áp dụng

1. Thay `for: 2m` bằng `for: 3m` và dự đoán mốc firing của hai rule có thời gian duy trì 2m trước khi chạy test. Không sửa test chỉ để làm xanh; giải thích lại hợp đồng thời gian.
2. Thêm một burst lỗi ngắn vào dữ liệu đã có đủ lịch sử. Kiểm tra tỷ lệ 5m còn vượt ngưỡng bao lâu và liệu `for` có ngăn firing hay không.
3. Thêm hai bản sao có lưu lượng chênh lệch lớn. So sánh tỷ lệ tính từ tổng với trung bình hai tỷ lệ và chọn kết quả phù hợp ảnh hưởng người dùng.
4. Tạo tình huống chỉ một bản sao biến mất khỏi discovery. Chứng minh rule thiếu toàn job không phát hiện được nó rồi thiết kế phép đối chiếu với nguồn kiểm kê dự kiến.
5. Đọc ba runbook và ghi rõ dữ liệu nào cần thu trước mỗi hành động giảm ảnh hưởng. Thử tình huống cảnh báo tỷ lệ hết firing vì lưu lượng tụt về 0 để tránh kết luận phục hồi sai.

Một cảnh báo có chất lượng nối được phép đo, cửa sổ thời gian, hành động và điều kiện phục hồi. Khi người nhận hiểu vì sao họ được gọi và có thể bắt đầu xử lý bằng bằng chứng cụ thể, cảnh báo mới thực hiện đúng vai trò trong vận hành production.
