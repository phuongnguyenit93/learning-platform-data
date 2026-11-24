# Thiết kế cảnh báo gắn với chất lượng phục vụ và cách xử lý

## 1. Bối cảnh và mục tiêu

Trong module **SPRING_CLOUD_PROVIDER_INTEGRATION**, chúng ta thực hành tích hợp Spring Boot với các dịch vụ managed của **AWS, Azure và Google Cloud** qua các thư viện Spring Cloud và SDK tương ứng. Khi ứng dụng chạy trên cloud, metrics, logs và traces chỉ thật sự hữu ích khi chúng giúp đội vận hành nhận ra suy giảm chất lượng phục vụ, biết mức độ ảnh hưởng và hành động kịp thời.

Một cảnh báo như “CPU trên 80%” có thể hữu ích trong một số tình huống, nhưng chưa nói rõ người dùng có đang gặp lỗi hay không. Ngược lại, cảnh báo “tỷ lệ request lỗi vượt ngân sách SLO và đang tiêu hao error budget với tốc độ 14 lần” gắn trực tiếp với chất lượng dịch vụ và mức độ khẩn cấp.

Bài học này trình bày cách thiết kế cảnh báo dựa trên **Service Level Indicator (SLI), Service Level Objective (SLO), error budget và burn rate**. Sau đó, chúng ta áp dụng các nguyên tắc này cho Prometheus/Alertmanager, Amazon CloudWatch, Azure Monitor và Google Cloud Monitoring.

Sau bài này, bạn có thể:

- Chọn SLI phản ánh availability, latency, throughput và chất lượng xử lý bất đồng bộ.
- Đặt SLO theo request hoặc time window và tính error budget.
- Tính burn rate và thiết kế cảnh báo fast-burn/slow-burn.
- Viết alert rule có thời gian duy trì, severity, owner và runbook.
- Giảm alert noise bằng grouping, inhibition, composite conditions và maintenance windows.
- Ánh xạ cùng một SLO sang CloudWatch, Azure Monitor và Google Cloud Monitoring.
- Kiểm thử cảnh báo, diễn tập incident và cải tiến ngưỡng từ dữ liệu thực tế.

## 2. Alert tốt phải bắt đầu từ trải nghiệm người dùng

Một alert nên trả lời bốn câu hỏi:

1. **Điều gì đang suy giảm?** Availability, latency, message age, backlog hay một luồng nghiệp vụ.
2. **Ai bị ảnh hưởng và ở phạm vi nào?** Một operation, một region, một dependency hay toàn service.
3. **Mức độ khẩn cấp ra sao?** Người dùng đang gặp lỗi ngay hay error budget đang bị tiêu hao dần.
4. **Người nhận cần làm gì?** Kiểm tra dashboard nào, chạy runbook nào, liên hệ team nào và khi nào cần escalate.

Ví dụ cảnh báo kém:

~~~text
CPU > 80%
~~~

Thông tin này không có service, thời gian duy trì, tác động người dùng hoặc hướng xử lý.

Ví dụ cảnh báo tốt hơn:

~~~text
Service: document-api
Signal: availability SLO burn rate
Condition: burn rate > 14.4 trong cửa sổ 1 giờ và 5 phút
Severity: page
Impact: error budget 30 ngày đang bị tiêu hao rất nhanh
Owner: team-document-platform
Runbook: /runbooks/document-api/availability
~~~

CPU vẫn có thể là tín hiệu chẩn đoán hoặc cảnh báo saturation, nhưng chỉ nên page khi có bằng chứng nó đang đe dọa khả năng phục vụ hoặc cần hành động ngay.

## 3. Phân biệt SLI, SLO, SLA và error budget

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| **SLI** | Chỉ số đo chất lượng thực tế | Tỷ lệ request thành công, p95 latency |
| **SLO** | Mục tiêu chất lượng trong một cửa sổ thời gian | 99,9% request thành công trong 30 ngày |
| **SLA** | Cam kết dịch vụ với khách hàng, thường có hệ quả hợp đồng | 99,5% availability theo tháng |
| **Error budget** | Phần chất lượng được phép không đạt mà vẫn đáp ứng SLO | 0,1% request được phép lỗi với SLO 99,9% |

SLO là công cụ quản lý độ tin cậy nội bộ; SLA là cam kết với khách hàng. SLO thường được đặt nghiêm ngặt hơn SLA để đội kỹ thuật có thời gian xử lý trước khi vi phạm cam kết.

Error budget không có nghĩa đội ngũ được phép gây lỗi. Nó là cách định lượng mức rủi ro còn lại trong một kỳ đánh giá. Khi budget gần cạn, đội có thể giảm tốc độ thay đổi rủi ro cao, ưu tiên reliability work hoặc tăng kiểm soát release.

## 4. Chọn SLI phù hợp với ứng dụng Spring Boot

Không nên dùng một SLI duy nhất cho mọi loại hệ thống. Chọn chỉ số dựa trên điều người dùng hoặc hệ thống phụ thuộc thực sự cần.

### 4.1. Availability

Định nghĩa request tốt là request được xử lý thành công theo contract. Ví dụ:

\[
Availability = \frac{GoodRequests}{EligibleRequests}
\]

Với HTTP API, có thể xem 2xx và một số 3xx là thành công tùy contract; 5xx thường là lỗi service. 4xx do người dùng gửi dữ liệu sai thường không được tính là lỗi availability của service. Tuy nhiên, một số 4xx như 429 do service rate-limit có thể cần SLI riêng nếu người dùng không thể hoàn thành tác vụ.

Định nghĩa phải nhất quán giữa metric, SLO và dashboard. Không để một service tính 429 là lỗi, service khác lại bỏ qua mà không ghi rõ.

### 4.2. Latency

Latency SLI có thể là tỷ lệ request hoàn tất dưới ngưỡng:

\[
LatencySLI = \frac{GoodRequestsWithinThreshold}{EligibleRequests}
\]

Ví dụ: 99% request GET tài liệu hoàn tất dưới 300 ms trong 30 ngày.

Không chỉ dùng average latency vì một nhóm nhỏ request rất chậm có thể bị che khuất. Dùng histogram để theo dõi p95/p99 hoặc tỷ lệ request dưới một ngưỡng phục vụ SLO.

### 4.3. Throughput và saturation

Throughput (requests/second, messages/second) và saturation (CPU, memory, thread pool, connection pool, queue capacity) thường là tín hiệu chẩn đoán hoặc capacity alert. Chúng trở thành SLI khi tốc độ hoặc khả năng tiếp nhận là một phần của contract, ví dụ API cần xử lý tối thiểu 500 giao dịch/giây.

Không đặt SLO kiểu “CPU dưới 70%” nếu người dùng không quan tâm trực tiếp tới con số CPU. Hãy nối saturation với request latency, error rate hoặc backlog.

### 4.4. Luồng bất đồng bộ

Với worker xử lý message, các SLI phù hợp gồm:

- Tỷ lệ job hoàn tất thành công.
- Tỷ lệ job hoàn tất trong thời hạn nghiệp vụ.
- Tuổi message cũ nhất chưa được xử lý.
- Tỷ lệ message chuyển vào DLQ.
- Thời gian từ lúc nhận job đến lúc kết quả sẵn sàng.

Đối với queue, “message được broker nhận” không đồng nghĩa “nghiệp vụ đã hoàn tất”. Nếu người dùng chờ kết quả tạo preview, hãy đo thời gian từ lúc API nhận job tới lúc preview sẵn sàng.

## 5. Xác định good event và eligible event

Trước khi tính SLI, phải định nghĩa mẫu số và tử số:

- **Eligible event:** request/job đủ điều kiện được tính vào SLI.
- **Good event:** eligible event đạt tiêu chí chất lượng.
- **Bad event:** eligible event không đạt tiêu chí.

Ví dụ SLI availability cho document API:

| Trường hợp | Eligible? | Good? |
|---|---:|---:|
| GET trả 200 | Có | Có |
| GET trả 500 do lỗi ứng dụng | Có | Không |
| GET trả 503 do dependency unavailable | Có | Không |
| GET trả 404 cho document không tồn tại | Có | Theo contract; thường là response hợp lệ |
| POST trả 400 do payload sai | Có thể có | Theo contract; thường không phải lỗi availability |
| Health check nội bộ | Thường không | Không áp dụng |
| Request bị chặn tại WAF trước service | Tùy SLO và ranh giới đo | Không tự động tính là lỗi ứng dụng |

Không loại mọi request lỗi khỏi mẫu số chỉ vì chúng là 4xx. Hãy xác định rõ lỗi do caller, lỗi do quota/rate-limit, lỗi xác thực và lỗi do service. Nếu một request bị từ chối vì chính sách của sản phẩm, có thể cần SLI riêng cho tỷ lệ từ chối hợp lệ.

Đối với latency SLI, request lỗi có thể được xem là bad event mà không cần đo latency thành công. Tránh cách tính chỉ lấy các request thành công làm mẫu số vì khi service lỗi nhiều, latency SLI có thể trông tốt giả tạo.

## 6. Tính SLO và error budget

Với request-based SLO:

\[
ErrorBudget = 1 - SLOGoal
\]

Số bad events được phép trong kỳ:

\[
AllowedBadEvents = EligibleEvents \times ErrorBudget
\]

Ví dụ service có 99,9% availability trong 30 ngày và nhận 2.000.000 request đủ điều kiện:

\[
ErrorBudget = 1 - 0,999 = 0,001 = 0,1\%
\]

\[
AllowedBadEvents = 2.000.000 \times 0,001 = 2.000
\]

Service được phép có tối đa khoảng 2.000 bad requests trong kỳ đánh giá để đạt SLO.

Với time-based SLO, nếu mục tiêu là 99,9% số phút trong kỳ healthy:

\[
AllowedBadTime = TotalTime \times (1 - SLOGoal)
\]

Trong 30 ngày có 43.200 phút:

\[
43.200 \times 0,001 = 43,2\text{ phút}
\]

Request-based và time-based SLO có semantics khác nhau. Một phút có traffic rất cao có thể chứa hàng nghìn bad requests nhưng chỉ là một bad minute trong time-based SLO. Chọn loại phù hợp với trải nghiệm và cách đo của service.

## 7. Burn rate: tốc độ tiêu hao error budget

Burn rate cho biết tốc độ lỗi hiện tại so với tốc độ lỗi tối đa để vừa đủ đạt SLO:

\[
BurnRate = \frac{ObservedErrorRate}{AllowedErrorRate}
\]

Với SLO 99,9%, allowed error rate là 0,1%.

| Error rate quan sát | Burn rate | Diễn giải |
|---:|---:|---|
| 0,05% | 0,5x | Tiêu hao chậm hơn mức ngân sách cho phép |
| 0,1% | 1x | Đang tiêu hao đúng tốc độ tối đa để đạt SLO |
| 0,5% | 5x | Ngân sách bị tiêu hao nhanh gấp 5 lần |
| 1,44% | 14,4x | Ngân sách bị tiêu hao rất nhanh |
| 5% | 50x | Sự cố nghiêm trọng nếu kéo dài |

Burn rate 1x không có nghĩa service đang đạt chất lượng tốt trong ngắn hạn; nó có nghĩa nếu duy trì mức lỗi này trong toàn bộ kỳ đánh giá thì vừa dùng hết error budget.

Thời gian ước lượng để tiêu hao hết budget khi còn 100%:

\[
TimeToExhaustion \approx \frac{SLOWindow}{BurnRate}
\]

Với SLO 30 ngày và burn rate 14,4x:

\[
30 / 14,4 \approx 2,08\text{ ngày}
\]

Nếu budget đã bị tiêu hao trước đó, thời gian thực tế còn lại ngắn hơn.

## 8. Multi-window, multi-burn-rate alert

Một alert chỉ nhìn cửa sổ ngắn có thể phản ứng với spike thoáng qua. Một alert chỉ nhìn cửa sổ dài có thể phát hiện quá muộn. Kết hợp hai cửa sổ giúp xác nhận lỗi vừa đủ lớn vừa đang tiếp diễn.

Ví dụ với SLO 99,9% trong 30 ngày:

| Mức | Cửa sổ dài | Cửa sổ ngắn | Burn rate gợi ý | Mục tiêu |
|---|---|---|---:|---|
| Fast burn | 1 giờ | 5 phút | 14,4x | Page nhanh khi sự cố nghiêm trọng |
| Medium burn | 6 giờ | 30 phút | 6x | Page/urgent ticket tùy service |
| Slow burn | 24 giờ | 2 giờ | 3x | Ticket ưu tiên cao hoặc cảnh báo team |
| Very slow burn | 3 ngày | 6 giờ | 1x | Theo dõi budget và kế hoạch cải thiện |

Đây là bộ giá trị khởi đầu minh họa dựa trên error budget 30 ngày. Hãy điều chỉnh theo SLO window, traffic, độ nhạy và khả năng phản ứng của đội.

Điều kiện multi-window thường có dạng:

~~~text
burn_rate_long_window > threshold
AND
burn_rate_short_window > threshold
~~~

Hai điều kiện cùng đúng giúp loại bỏ spike đã kết thúc trước khi alert được gửi. Nếu traffic quá thấp, error ratio có thể biến động mạnh; cần thêm minimum request volume hoặc dùng time-based SLI phù hợp.

## 9. Thiết kế severity và loại thông báo

Không phải mọi alert đều cần page người trực.

| Severity | Khi nào dùng | Kênh thường dùng | Kỳ vọng phản hồi |
|---|---|---|---|
| SEV1 / page | Người dùng diện rộng bị ảnh hưởng, fast burn nghiêm trọng | On-call paging | Phản hồi ngay |
| SEV2 / urgent | Một luồng quan trọng suy giảm, budget tiêu hao nhanh nhưng chưa outage diện rộng | On-call/incident channel | Phản hồi trong thời gian ngắn theo policy |
| SEV3 / ticket | Slow burn, capacity risk hoặc lỗi có workaround | Ticket/engineering queue | Xử lý trong giờ làm việc |
| INFO | Deployment, threshold warning hoặc tín hiệu cần theo dõi | Dashboard/chat | Không cần phản hồi ngay |

Severity cần dựa trên impact, urgency và phạm vi. Không page chỉ vì một metric hạ tầng vượt ngưỡng nếu chưa có hành động khẩn cấp rõ ràng.

## 10. Alert phải có owner và runbook

Một alert production nên có:

- **Tên ổn định:** ví dụ `DocumentApiAvailabilityFastBurn`.
- **Service/team:** ai chịu trách nhiệm.
- **Signal và condition:** SLI nào, cửa sổ nào, threshold nào.
- **Severity:** page, urgent, ticket hoặc info.
- **Summary:** mô tả ngắn, có thể đọc trên điện thoại.
- **Description:** giá trị hiện tại, threshold, affected resource và thời gian.
- **Runbook URL:** bước chẩn đoán và khôi phục.
- **Dashboard URL:** panel liên quan.
- **Escalation:** khi nào chuyển sang incident commander hoặc team dependency.

Runbook nên đưa người trực qua các bước:

1. Xác nhận alert còn firing và kiểm tra thời gian bắt đầu.
2. Xác định SLI/SLO bị ảnh hưởng, region và operation.
3. Kiểm tra deployment gần nhất, traffic, dependency latency và error class.
4. Dùng trace/log để tìm request hoặc job lỗi đại diện.
5. Thực hiện hành động giảm tác động có kiểm soát: rollback, disable feature, giảm concurrency hoặc fail over nếu runbook cho phép.
6. Xác minh SLI phục hồi và error budget burn rate trở về mức an toàn.
7. Ghi timeline, nguyên nhân và follow-up sau incident.

Nếu người nhận không biết phải làm gì sau khi đọc alert, alert đó cần được thiết kế lại.

## 11. Prometheus: alert rule theo SLI

Ví dụ metric Spring Boot Micrometer export qua Prometheus. Tên metric sau khi chuyển đổi thường là `http_server_requests_seconds_count` và histogram bucket tương ứng; cần xác minh tên thực tế ở `/actuator/prometheus`. Label `service` trong ví dụ phải được thêm bằng common tag hoặc target relabeling; nếu chưa có label này, hãy lọc theo label target như `job` hoặc bỏ điều kiện service.

### 11.1. Availability error ratio

~~~promql
sum(rate(http_server_requests_seconds_count{
  service="document-api",
  status=~"5.."
}[5m]))
/
sum(rate(http_server_requests_seconds_count{
  service="document-api"
}[5m]))
~~~

Biểu thức này tính tỷ lệ 5xx trong 5 phút. Trong hệ thống thực tế, cần lọc route/operation đủ điều kiện, loại health check và xác định rõ 429/4xx có được xem là bad event hay không.

### 11.2. Latency p95

~~~promql
histogram_quantile(
  0.95,
  sum by (le, uri) (
    rate(http_server_requests_seconds_bucket{
      service="document-api",
      uri!~"/actuator/.*"
    }[5m])
  )
)
~~~

Không đưa raw path có ID vào label. Dùng URI template do instrumentation cung cấp để tránh tạo alert instance cho từng resource.

### 11.3. Alert rule minh họa

~~~yaml
groups:
  - name: document-api-slo
    rules:
      - alert: DocumentApiHighErrorRate
        expr: |
          (
            sum(rate(http_server_requests_seconds_count{
              service="document-api",
              status=~"5.."
            }[5m]))
            /
            sum(rate(http_server_requests_seconds_count{
              service="document-api"
            }[5m]))
          ) > 0.02
        for: 5m
        labels:
          severity: page
          team: document-platform
          service: document-api
        annotations:
          summary: "Document API error rate is above 2%"
          description: "5xx ratio has remained above 2% for 5 minutes."
          runbook_url: "https://runbooks.example/document-api/availability"
~~~

Ví dụ dùng threshold tĩnh để minh họa cú pháp. Với SLO production, nên ưu tiên burn-rate alert theo error budget và bổ sung minimum traffic để tránh cảnh báo do mẫu quá nhỏ.

## 12. Prometheus: alert burn rate và Alertmanager

Giả sử recording rules đã tạo hai series:

- `document_api:error_ratio:rate5m`
- `document_api:error_ratio:rate1h`

Với SLO 99,9%, allowed error ratio là 0,001. Burn rate là error ratio chia 0,001.

~~~yaml
groups:
  - name: document-api-burn-rate
    rules:
      - alert: DocumentApiFastBurn
        expr: |
          (
            document_api:error_ratio:rate1h / 0.001 > 14.4
          )
          and
          (
            document_api:error_ratio:rate5m / 0.001 > 14.4
          )
        for: 2m
        labels:
          severity: page
          team: document-platform
          service: document-api
        annotations:
          summary: "Document API is burning its error budget rapidly"
          description: "1h and 5m error-budget burn rates are both above 14.4x."
          runbook_url: "https://runbooks.example/document-api/availability"
~~~

Để tránh chia cho 0 hoặc cảnh báo khi không có traffic, recording rule cần có denominator hợp lệ và có thể kết hợp minimum request rate. Không dùng `or vector(0)` một cách máy móc nếu điều đó biến “không có dữ liệu” thành “không có lỗi”.

Alertmanager đảm nhiệm:

- **Grouping:** gộp nhiều alert cùng service/cluster/alertname thành một notification.
- **Routing:** gửi tới team/on-call phù hợp theo label.
- **Inhibition:** tạm suppress alert phụ khi alert gốc lớn hơn đang firing.
- **Silence:** tắt alert có thời hạn trong maintenance hoặc khi đã có incident.
- **Deduplication:** tránh gửi lặp cùng một alert fingerprint.

Ví dụ cấu hình route:

~~~yaml
route:
  receiver: platform-ticket
  group_by: [alertname, service, cluster]
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 4h
  routes:
    - matchers:
        - severity="page"
      receiver: document-oncall
    - matchers:
        - severity="ticket"
      receiver: document-platform-ticket
~~~

Tên receiver là cấu hình tích hợp notification của môi trường, không phải tên dịch vụ mặc định. Cần khai báo receiver tương ứng trong phần receivers và bảo vệ credential của webhook/paging integration.

## 13. Alert cho latency, traffic và saturation

SLO alert không loại bỏ các alert kỹ thuật. Chúng bổ sung nhau:

| Tín hiệu | Câu hỏi | Alert phù hợp |
|---|---|---|
| Error ratio | Người dùng có nhận lỗi không? | Burn rate / error budget |
| Latency p95/p99 | Request có chậm hơn mục tiêu không? | Latency SLI burn rate |
| Traffic | Lưu lượng có bất thường hoặc mất hẳn không? | Traffic anomaly / no-traffic với service vốn phải có traffic |
| Saturation | Tài nguyên có gần cạn không? | CPU, heap, thread pool, connection pool |
| Dependency | DB/storage/API bên ngoài có chậm/lỗi không? | Dependency latency/error rate |
| Queue age/backlog | Job có chờ quá lâu không? | Oldest age, backlog growth và job completion SLO |
| DLQ | Message lỗi có tích tụ không? | DLQ arrival rate/count/age |

Alert saturation thường nên là warning/ticket nếu chưa ảnh hưởng SLI. Nếu CPU, thread pool và latency cùng tăng, có thể dùng composite condition hoặc runbook để ưu tiên xử lý.

Không dùng một threshold chung cho mọi workload. API latency 200 ms có thể là bình thường với một service và nghiêm trọng với service khác. Đặt threshold theo SLO và baseline thực tế.

## 14. AWS CloudWatch: alarms, composite alarms và SLO

CloudWatch hỗ trợ metric alarms, anomaly detection, composite alarms và SLO thông qua CloudWatch Application Signals.

### 14.1. Metric alarm

Metric alarm đánh giá metric hoặc metric math expression theo threshold trong một chuỗi evaluation periods. Có thể cấu hình:

- Metric và dimensions.
- Statistic/period.
- Threshold hoặc anomaly detection band.
- Evaluation periods và datapoints to alarm (M-out-of-N).
- Missing data treatment.
- Alarm actions, ví dụ SNS topic.

M-out-of-N giúp tránh alert do một datapoint bất thường. Ví dụ 3 trong 5 datapoints vượt threshold mới chuyển ALARM. Chọn period và số datapoints dựa trên độ trễ metric và thời gian phản ứng cần thiết.

### 14.2. Composite alarm

Composite alarm kết hợp trạng thái nhiều alarm con bằng AND/OR/NOT. Ví dụ:

~~~text
ALARM(DocumentApiHighErrorRate)
AND ALARM(DocumentApiHighLatency)
AND NOT ALARM(MaintenanceWindow)
~~~

Composite alarm giúp giảm notification noise và tạo health indicator tổng hợp. Alarm con vẫn cần tồn tại để chẩn đoán; có thể chỉ gắn action ở composite level để tránh gửi nhiều thông báo cho cùng một incident.

Composite alarms chỉ đánh giá trạng thái các alarm được tham chiếu, không trực tiếp tính metric. Các alarm con và composite alarm cần đáp ứng điều kiện account/region theo tài liệu CloudWatch.

### 14.3. Application Signals SLO và burn rate

CloudWatch Application Signals có thể tạo SLO cho service/operation dựa trên latency hoặc availability. Có thể chọn request-based hoặc period-based SLO, theo dõi attainment/error budget và tạo burn-rate alarms với nhiều lookback windows.

Burn rate:

\[
BurnRate = \frac{ObservedErrorRate}{1 - SLOGoal}
\]

Ví dụ SLO 99,9% có baseline error rate 0,1%. Nếu error rate trong cửa sổ 1 giờ là 1,44%, burn rate là 14,4x.

CloudWatch hỗ trợ cảnh báo burn rate với nhiều cửa sổ. Một cách thiết kế là kết hợp cửa sổ dài và ngắn để xác nhận lỗi vẫn đang diễn ra. Alarm có thể gửi SNS notification hoặc tích hợp incident workflow theo khả năng của môi trường.

### 14.4. Missing data và metric delay

Không mặc định missing data là zero. Nếu ứng dụng ngừng publish metric, alarm có thể cần chuyển sang INSUFFICIENT_DATA hoặc treat missing data theo semantics phù hợp. Với metric ít traffic, dùng metric availability/heartbeat riêng để phân biệt service không có request với exporter bị lỗi.

## 15. Azure Monitor: metric alerts, SLI và action groups

Azure Monitor hỗ trợ metric alert rules, log search alerts, dynamic thresholds, multi-condition alerts và action groups.

### 15.1. Metric alert rule

Một metric alert rule gồm:

- Resource hoặc resource scope cần giám sát.
- Metric và aggregation.
- Condition/threshold.
- Evaluation frequency và lookback window.
- Severity và description.
- Action group để gửi notification hoặc chạy automation.

Có thể dùng static threshold khi SLO rõ ràng, hoặc dynamic threshold khi metric có seasonality và baseline lịch sử đủ tin cậy.

### 15.2. Dynamic threshold

Dynamic threshold dùng lịch sử metric để học pattern và xác định vùng bất thường. Nó hữu ích khi traffic/CPU có chu kỳ ngày/tuần. Tuy nhiên:

- Cần đủ dữ liệu lịch sử để học baseline.
- Sau deployment hoặc thay đổi traffic lớn, mô hình có thể cần thời gian thích nghi.
- Dynamic threshold phát hiện bất thường so với lịch sử, không tự hiểu SLO business.
- Không thay thế burn-rate alert khi mục tiêu là bảo vệ error budget.

### 15.3. SLI/SLO và fast/slow burn

Azure Monitor có thể định nghĩa SLI theo availability hoặc latency, đặt baseline target (SLO), evaluation period và bật alert. Có thể tạo:

- Baseline alert khi SLI dưới SLO.
- Fast burn rate để phát hiện error budget bị tiêu hao nhanh.
- Slow burn rate để phát hiện suy giảm kéo dài.

Action groups xác định ai được thông báo và hành động nào chạy khi alert firing. Sử dụng common alert schema để webhook/Logic App/Function nhận payload nhất quán hơn giữa các loại alert.

### 15.4. Dimension splitting và alert noise

Metric alert có thể split theo dimensions. Mỗi time series dimension có thể tạo alert riêng và phát sinh chi phí riêng. Chỉ split theo dimension cần thiết như region hoặc operation; tránh split theo ID duy nhất hoặc dimension không cần cho phản ứng.

Alert processing rules có thể suppress hoặc route notifications trong maintenance window. Ghi rõ phạm vi và thời gian hết hạn để không vô tình tắt cảnh báo production vô thời hạn.

## 16. Google Cloud Monitoring: SLO-based alerting policies

Cloud Monitoring hỗ trợ alerting policies dựa trên metric conditions hoặc SLO service monitoring.

### 16.1. SLO burn-rate policy

Google Cloud Monitoring có thể tạo alert policy theo burn rate của SLO. Burn rate lớn hơn 1 nghĩa là nếu tốc độ tiêu hao đó kéo dài trong kỳ compliance thì service sẽ không đạt SLO.

Có thể tạo hai loại policy:

- **Fast burn:** cửa sổ ngắn, threshold cao; cảnh báo sự cố lớn cần phản ứng nhanh.
- **Slow burn:** cửa sổ dài, threshold thấp hơn; cảnh báo suy giảm kéo dài đang ăn dần error budget.

Tài liệu Google đưa ra điểm khởi đầu minh họa khoảng 10x với lookback 1–2 giờ cho fast burn và 2x với lookback 24 giờ cho slow burn. Đây không phải threshold bắt buộc; cần điều chỉnh theo SLO, traffic và khả năng phản ứng.

Cloud Monitoring SLO burn-rate alert hiện có giới hạn compliance period/lookback cho một số selector; tài liệu nêu không thể dùng compliance period lớn hơn 24 giờ cho burn-rate alert selector này. Nếu cần theo dõi SLO dài 28/30 ngày, có thể dùng lookback ngắn hơn để điều khiển phản ứng ngắn hạn và theo dõi budget dài hạn trên dashboard.

### 16.2. Notification channels và documentation

Alerting policy có thể gửi tới email, Pub/Sub, webhook, PagerDuty hoặc notification channel được hỗ trợ. Phần documentation nên chứa:

- Tóm tắt điều kiện đã firing.
- Service/SLO bị ảnh hưởng.
- Link dashboard và trace/log query.
- Hướng dẫn xử lý và escalation.

Notification channel chỉ là phương tiện truyền tin. Cần kiểm thử endpoint, quyền truy cập và người nhận trước khi phụ thuộc vào nó trong production.

## 17. Alert cho message processing và cloud dependency

Với Spring Cloud Provider Integration, service có thể phụ thuộc SQS, Service Bus, Pub/Sub, S3, Blob Storage, database hoặc API khác. Cần tách SLI của API và SLI của công việc bất đồng bộ.

Ví dụ cho luồng tạo preview:

| SLI | Mục tiêu ví dụ | Alert |
|---|---|---|
| API acceptance availability | 99,9% request nhận job hợp lệ được chấp nhận | Fast burn nếu API không nhận job |
| Job completion availability | 99,5% job hoàn tất thành công | Burn rate theo job outcome |
| Job completion latency | 99% job hoàn tất dưới 2 phút | SLO latency alert |
| Queue age | 99% message bắt đầu xử lý dưới 60 giây | Fast/slow age alert |
| DLQ rate | Dưới 0,1% job | Alert nếu rate/count tăng |
| Storage dependency | 99,9% thao tác đọc/ghi thành công | Dependency SLO hoặc error-rate alert |

Không page cho mọi message vào DLQ nếu DLQ chứa loại lỗi có thể xử lý theo batch. Hãy page khi DLQ ảnh hưởng job quan trọng, arrival rate tăng bất thường hoặc oldest DLQ age vượt thời gian xử lý cam kết.

Nếu queue backlog tăng nhưng job completion SLO vẫn đạt, có thể chỉ cần warning. Nếu backlog và oldest age cùng tăng, job completion latency sắp vi phạm và alert nên nâng severity.

## 18. Alert fatigue, deduplication và maintenance

Alert fatigue xuất hiện khi người trực nhận quá nhiều thông báo không có hành động rõ ràng. Một hệ thống alert tốt cần:

- Group alert theo service/cluster/region thay vì gửi từng instance.
- Deduplicate cùng một condition.
- Inhibit alert phụ khi đã có alert gốc giải thích sự cố.
- Có silence/maintenance window với thời gian hết hạn.
- Dùng for/evaluation periods để lọc spike ngắn.
- Chỉ page khi có tác động người dùng hoặc nguy cơ lớn cần phản ứng ngay.
- Tách notification và incident creation khỏi metric alarm đơn lẻ khi cần.

Không đặt for quá dài khiến phát hiện sự cố muộn. Không đặt quá ngắn khiến alert flapping. Chọn dựa trên scrape/export interval, độ trễ backend và thời gian phản ứng.

Sau mỗi incident, review:

- Alert có phát hiện đúng thời điểm không?
- Có alert nào dư thừa hoặc đến sau alert gốc?
- Runbook có giúp giảm thời gian khôi phục không?
- Threshold có phản ánh SLO thực tế không?
- Có thể thay alert hạ tầng bằng SLI user-facing không?

## 19. Kiểm thử, diễn tập và vận hành alert

Không nên chờ production outage mới biết alert có hoạt động.

### 19.1. Kiểm thử rule

Với Prometheus, có thể dùng `promtool test rules` để kiểm tra expression và thời gian chuyển trạng thái. Với CloudWatch/Azure/Google, tạo resource test và dùng metric/query mẫu để xác minh condition, notification channel và runbook.

Kiểm tra:

- Alert firing khi SLI vi phạm.
- Alert không firing khi chỉ có một spike ngắn dưới thời gian duy trì.
- Fast burn và slow burn phân biệt đúng.
- Không có traffic được xử lý theo policy rõ ràng.
- Alert group/inhibit không che mất sự cố độc lập.
- Notification tới đúng team và có link dashboard/runbook.
- Resolved notification được gửi khi condition hồi phục.

### 19.2. Diễn tập incident

Trong staging:

1. Tạo lỗi dependency có kiểm soát để tăng error rate.
2. Tăng latency handler để làm p95 vượt SLO.
3. Giảm consumer capacity để backlog và message age tăng.
4. Kiểm tra alert fast burn/slow burn và routing.
5. Người trực làm theo runbook, xác định nguyên nhân và khôi phục.
6. Xác minh alert resolved và error budget burn rate trở lại bình thường.

Không gây lỗi có chủ ý trên production nếu chưa có quy trình game day được phê duyệt và giới hạn blast radius.

### 19.3. Theo dõi chất lượng của hệ thống alert

Đo chính hệ thống alert:

- Alert delivery success/failure.
- Thời gian từ metric breach tới notification.
- Tỷ lệ alert được xác nhận và tỷ lệ false positive.
- Số page ngoài giờ không dẫn tới hành động.
- Thời gian trung bình từ alert tới acknowledge và mitigation.
- Số incident được phát hiện bởi người dùng trước alert.

Nếu sự cố thường được người dùng báo trước hệ thống alert, SLI/threshold hoặc telemetry coverage cần cải thiện.

## 20. Tổng kết

Thiết kế cảnh báo gắn với chất lượng phục vụ bắt đầu từ **SLI và SLO**, không phải từ danh sách metric có sẵn. Xác định good/eligible events, tính error budget, theo dõi burn rate và dùng multi-window alert để phân biệt sự cố nghiêm trọng với suy giảm kéo dài.

Prometheus/Alertmanager cung cấp rule, grouping, routing, inhibition và silence. CloudWatch có metric/composite alarms và SLO burn-rate alarms qua Application Signals. Azure Monitor hỗ trợ metric alerts, dynamic thresholds, SLI/SLO fast/slow burn và action groups. Google Cloud Monitoring hỗ trợ SLO-based burn-rate alerting policies cùng notification channels và documentation.

Mỗi alert cần có severity, owner, điều kiện rõ ràng, dashboard và runbook. Kiểm thử notification, diễn tập khôi phục, review false positives và đo alert delivery để bảo đảm cảnh báo thực sự giúp đội vận hành bảo vệ trải nghiệm người dùng.

### Tài liệu tham khảo chính thức

- [Google SRE Workbook — Alerting on SLOs](https://sre.google/workbook/alerting-on-slos/)
- [Google Cloud — Alerting on budget burn rate](https://docs.cloud.google.com/stackdriver/docs/solutions/slo-monitoring/alerting-on-budget-burn-rate)
- [Google Cloud — Creating an SLO alerting policy](https://docs.cloud.google.com/stackdriver/docs/solutions/slo-monitoring/ui/create-alert)
- [Prometheus — Alerting rules](https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/)
- [Prometheus — Alertmanager](https://prometheus.io/docs/alerting/latest/alertmanager/)
- [Amazon CloudWatch — Service level objectives](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch-ServiceLevelObjectives.html)
- [Amazon CloudWatch — Using alarms](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch_Alarms.html)
- [Amazon CloudWatch — Composite alarms](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/alarm-combining.html)
- [Azure Monitor — Create service level indicators](https://learn.microsoft.com/azure/azure-monitor/fundamentals/service-level-indicators-create)
- [Azure Monitor — Create metric alert rules](https://learn.microsoft.com/en-us/azure/monitoring-and-diagnostics/alert-metric)
- [Azure Monitor — Dynamic thresholds](https://learn.microsoft.com/en-us/azure/azure-monitor/alerts/alerts-dynamic-thresholds)
- [Azure Monitor — Alert types](https://learn.microsoft.com/en-us/azure/azure-monitor/alerts/alerts-types)
- [Azure Monitor — Common alert schema](https://learn.microsoft.com/en-us/azure/azure-monitor/platform/alerts-common-schema-definitions)
